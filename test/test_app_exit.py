"""主程序退出回归测试（对应「关闭GUI + 托盘退出后进程残留」修复）。

根因：Qt 仅在“最后一个可见顶层窗口”关闭时才发 lastWindowClosed 并结束
app.exec()。X 按钮最小化到托盘后窗口已 hide()，托盘「退出」调用 self.close()
时 closeEvent 虽被 accept，但没有可见窗口关闭 → 事件循环不退出 → 进程残留。
修复：closeEvent 真正退出路径 event.accept() 后 QTimer.singleShot(0, QApplication.quit)。

另含虚拟表串口从站线程（SerialSlaveThread）在 thread_registry 登记的断言，
保证关闭兜底回收能覆盖该线程。

运行（offscreen，无需真实桌面）：
    python test/test_app_exit.py
"""

import os

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time  # noqa: E402

# 本测试会 show/close 主窗口（测托盘与关闭路径）→ 退出路径会写 config.json；
# 沙箱到临时目录，避免把 offscreen 合成几何写进开发机真实配置
import _config_sandbox  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main_gui  # noqa: E402

_config_sandbox.install()


class _FakeTray:
    """无桌面环境下无真实托盘，伪造一个以强制走「最小化到托盘」分支。"""

    def __init__(self):
        self.hidden = False
        self.shown_hint = False

    def show_hint_once(self):
        self.shown_hint = True

    def hide_tray(self):
        self.hidden = True

    def update_autostart_state(self):
        pass


_app = None


def _get_app():
    global _app
    if _app is None:
        _app = QApplication([])
    return _app


def test_tray_exit_quits_event_loop():
    """X→最小化到托盘→托盘「退出」：app.exec() 必须在数秒内返回。"""
    app = _get_app()
    win = main_gui.MainWindow()
    win.show()
    time.sleep(0.3)

    win._tray_manager = _FakeTray()
    win._system_settings["close_to_tray"] = True

    def click_x_minimize():
        ev = QCloseEvent()
        win.closeEvent(ev)
        # 最小化到托盘：事件被 ignore（程序继续运行），窗口隐藏
        assert not ev.isAccepted(), "最小化到托盘时 closeEvent 应 ignore"
        assert not win.isVisible(), "最小化后窗口应隐藏"
        assert win._tray_manager.shown_hint

    def tray_exit():
        win._tray_exit_app()

    def fail_if_alive():
        raise AssertionError("托盘退出后 app.exec() 未返回，事件循环残留")

    QTimer.singleShot(800, click_x_minimize)
    QTimer.singleShot(1800, tray_exit)
    QTimer.singleShot(6000, app.quit)  # 兜底，触发后 AssertionError 判定失败

    t0 = time.time()
    app.exec()
    dt = time.time() - t0
    assert dt < 5.0, f"托盘退出耗时 {dt:.1f}s 过长，疑似进程残留"
    assert win._tray_manager.hidden, "退出时应隐藏托盘图标"
    print("[OK] 托盘退出事件循环正常结束")


def test_x_exit_quits_when_tray_absent():
    """无托盘（或关闭直接退出）场景：X → closeEvent accept → app.exec() 返回。"""
    app = _get_app()
    win = main_gui.MainWindow()
    win.show()
    time.sleep(0.3)
    # offscreen 下无真实托盘，_tray_manager 为 None，closeEvent 走真正退出路径

    def click_x():
        ev = QCloseEvent()
        win.closeEvent(ev)
        assert ev.isAccepted(), "真正退出时 closeEvent 应 accept"

    QTimer.singleShot(800, click_x)
    QTimer.singleShot(6000, app.quit)

    t0 = time.time()
    app.exec()
    dt = time.time() - t0
    assert dt < 5.0, f"X 退出耗时 {dt:.1f}s 过长"
    print("[OK] 直接关闭事件循环正常结束")


def test_meter_sim_serial_thread_registered():
    """虚拟表串口从站 QThread 必须登记到 thread_registry（关闭兜底回收依赖）。"""
    from meter_sim_widget import SerialSlaveThread

    _get_app()

    def _factory():
        return None

    t = SerialSlaveThread("COM999", 115200, "N", 1, _factory)
    assert t.objectName() == "MeterSimSerialSlave", (
        f"SerialSlaveThread 未登记 objectName: {t.objectName()!r}"
    )
    t.start()
    t.wait(3000)
    t.stop()
    t.wait(2000)
    print("[OK] 虚拟表串口线程已登记 thread_registry")


def test_meter_sim_serial_log_full_frame():
    """虚拟表串口日志必须整帧打印（含 HCS/FCS 与 16 帧尾），不得截断。

    用户现场：应答 34 字节，日志只到 `1c 07 ea 0a 1b`（`.hex(' ')[:80]` 截断），
    看不到校验位与帧尾，无法核对回包。
    """
    import meter_sim_widget as mw
    from dl_t698_45_frame_gen import DLT69845FrameGenerator

    app = _get_app()
    req = DLT69845FrameGenerator().generate_get_request_normal(
        bytes([0x45]) + b"\xAA" * 6, 0, 0x01, bytes.fromhex("40020200"))
    written = []

    class _FakeSerial:
        def __init__(self, *a, **k):
            self._buf = bytearray(req)

        def open(self):
            pass

        @property
        def in_waiting(self):
            return len(self._buf)

        def read(self, n):
            out = bytes(self._buf[:n])
            del self._buf[:n]
            return out

        def write(self, data):
            written.append(bytes(data))
            return len(data)

        def close(self):
            pass

    real = mw.serial.Serial
    mw.serial.Serial = _FakeSerial
    try:
        from meter_sim import MeterSimEngine, SimOptions, load_archive
        factory = lambda: MeterSimEngine(load_archive(), SimOptions())
        logs = []
        t = mw.SerialSlaveThread("FAKE", 9600, "N", 1, factory)
        t.log.connect(logs.append)
        t.start()
        for _ in range(60):          # 跨线程日志排队，需泵事件循环
            app.processEvents()
            time.sleep(0.02)
        t.stop()
        t.wait(2000)
        app.processEvents()
    finally:
        mw.serial.Serial = real

    req_lines = [x for x in logs if x.startswith("← 收到请求")]
    resp_lines = [x for x in logs if x.startswith("→ 回复")]
    assert req_lines, f"未捕获请求日志: {logs}"
    assert resp_lines, f"未捕获应答日志: {logs}"
    assert req_lines[0].split(": ", 1)[1] == req.hex(" "), req_lines[0]
    resp = written[0]
    assert resp[-1] == 0x16, f"应答帧尾不是 16: {resp.hex(' ')}"
    assert resp_lines[0].split(": ", 1)[1] == resp.hex(" "), (
        f"日志应答被截断: {resp_lines[0]}")
    print(f"[OK] 虚拟表串口日志整帧打印（{len(resp)}B 含 FCS 与 16 帧尾）")


def main():
    print("=" * 50)
    print("主程序退出/线程回收回归测试")
    print("=" * 50)
    test_tray_exit_quits_event_loop()
    test_x_exit_quits_when_tray_absent()
    test_meter_sim_serial_thread_registered()
    test_meter_sim_serial_log_full_frame()
    print("=" * 50)
    print("[OK] 全部测试通过 ✓")


if __name__ == "__main__":
    main()
