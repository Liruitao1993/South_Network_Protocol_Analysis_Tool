# -*- coding: utf-8 -*-
"""645虚拟表「事件状态字」测试（DI 04001501 主动上报状态字，BS96 = 12 字节）

覆盖：
- 类型/长度修复：04001501 应答 L=0x10（4 字节 DI + 12 字节数据），此前被当 4 字节数值截断
- 默认不变化：档案默认 12 字节全 0，连读多次逐字节相同
- 随机产生事件：连读 20 次相邻不同、长度合法、可被解析器读回
- RandomEventWord 单测：24 位 hex、与上次不同（注入碰撞桩验证重抽）、reset
- 异常容错：随机源抛异常/返回非法值 → 回落档案值 + last_error，不抛栈
- offscreen GUI：模拟设置小节与勾选框、勾选注入生效、离线两次响应不同、持久化重载
- 串口回环（有 COM1↔COM2 时）：勾选后连读两次应答数据不同

运行：python test/test_dlt645_sim_event_word.py
"""

import io
import os
import random
import sys
import time

import _path_setup  # noqa: E402  （把项目根加入 sys.path 并切 cwd）

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # Windows 控制台中文
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dlt645_frame_gen import DLT645FrameGenerator, encode_di  # noqa: E402
from dlt645_parser import DLT645Parser  # noqa: E402
from dlt645_sim import DLT645MeterSim  # noqa: E402
from dlt645_sim.archive import DEFAULT_ARCHIVE, DLT645Archive  # noqa: E402
from dlt645_sim.dynamic_data import (  # noqa: E402
    EVENT_WORD_BYTES,
    EVENT_WORD_DI,
    RandomEventWord,
)

PASS = 0
FAILURES = []

GEN = DLT645FrameGenerator()
ADDR = "000000000033"
REQ = GEN.build_frame(ADDR, GEN.build_control(0x11), encode_di(EVENT_WORD_DI))


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append(f"{name} :: {detail}")
        print(f"[FAIL] {name} :: {detail}")


def payload_of(frame):
    """响应帧 → 未加扰数据域。"""
    return GEN.descramble(frame[10:-2])


# ---------------------------------------------------------------------------
# 1. 类型/长度修复（04001501 不再被截断成 4 字节）
# ---------------------------------------------------------------------------

def t_type_length_fix():
    print("\n== 1. 类型/长度修复 ==")
    check("默认档案含事件状态字", DEFAULT_ARCHIVE.get(EVENT_WORD_DI) == "00" * 12,
          repr(DEFAULT_ARCHIVE.get(EVENT_WORD_DI)))

    sim = DLT645MeterSim(address=ADDR, archive=DLT645Archive())
    dt, length = sim._di_info_for(EVENT_WORD_DI)
    check("DI 类型解析 = BS96", dt == "BS96", repr(dt))
    check("DI 声明长度 = 12", length == 12, repr(length))
    check("_data_type_for 兼容接口仍可用", sim._data_type_for(EVENT_WORD_DI) == "BS96",
          repr(sim._data_type_for(EVENT_WORD_DI)))
    for di, want in (("00010000", "XXXXXX.XX"), ("02010100", "XXX.X"),
                     ("04000201", "hhmmss")):
        check(f"常规 DI {di} 类型不变", sim._data_type_for(di) == want,
              f"{sim._data_type_for(di)!r} != {want!r}")

    rsp = sim.handle_frame(REQ)[0]
    d = payload_of(rsp)
    check("应答 L=0x10（4 + 12 字节）", rsp[9] == 0x10, f"L={rsp[9]:#04x}")
    check("应答数据域 = DI + 12 字节", len(d) == 16 and d[:4] == bytes.fromhex("01150004"),
          d.hex(" ").upper())
    check("帧首尾与控制码", rsp[0] == 0x68 and rsp[-1] == 0x16 and rsp[8] == 0x91,
          f"{rsp[0]:#x} {rsp[8]:#x} {rsp[-1]:#x}")
    check("CS 与帧内容自洽", (sum(rsp[:10 + rsp[9]]) & 0xFF) == rsp[-2],
          f"{rsp[-2]:#x}")

    parsed = DLT645Parser().parse(rsp)
    check("解析器识别 04001501", parsed.get("di_code") == EVENT_WORD_DI,
          str(parsed.get("di_code")))
    check("解析器标为 BS96", "BS96" in str(parsed.get("di_desc", ""))
          or "BS96" in " ".join(str(r) for r in parsed.get("fields", [])),
          str(parsed.get("di_desc")))
    value_row = [r for r in parsed.get("fields", []) if str(r[0]) == "数据值"]
    check("解析器读回 12 字节数据值（24 hex）",
          bool(value_row) and len(str(value_row[0][1]).replace(" ", "")) == 24,
          str(value_row[:1]))


# ---------------------------------------------------------------------------
# 2. 默认：不变化（12 字节全 0）
# ---------------------------------------------------------------------------

def t_default_unchanged():
    print("\n== 2. 默认不变化 ==")
    sim = DLT645MeterSim(address=ADDR, archive=DLT645Archive())
    outs = [sim.handle_frame(REQ)[0] for _ in range(3)]
    check("连读 3 次应答完全相同", len(set(outs)) == 1,
          " | ".join(o.hex(" ").upper() for o in outs))
    check("数据部分全 0（无事件）", payload_of(outs[0])[4:] == b"\x00" * EVENT_WORD_BYTES,
          payload_of(outs[0]).hex(" ").upper())

    sim2 = DLT645MeterSim(address=ADDR, archive=DLT645Archive(
        {EVENT_WORD_DI: "FF" * 12}))
    rsp = sim2.handle_frame(REQ)[0]
    check("档案值非 0 时按档案回（不随机）",
          payload_of(rsp)[4:] == b"\xff" * EVENT_WORD_BYTES,
          payload_of(rsp).hex(" ").upper())
    check("同一档案值连读 2 次一致", sim2.handle_frame(REQ)[0] == rsp)


# ---------------------------------------------------------------------------
# 3. 随机产生事件
# ---------------------------------------------------------------------------

def t_random_mode():
    print("\n== 3. 随机产生事件 ==")
    rng = RandomEventWord()
    sim = DLT645MeterSim(address=ADDR, archive=DLT645Archive(),
                         event_word_source=rng.next_value)
    datas = []
    for _ in range(20):
        rsp = sim.handle_frame(REQ)[0]
        check_len = rsp[9] == 0x10
        d = payload_of(rsp)
        if not check_len or len(d) != 16:
            check("随机应答长度合法", False, f"L={rsp[9]} data={d.hex(' ')}")
            return
        datas.append(d[4:])
    check("连读 20 次长度均为 12 字节", all(len(x) == EVENT_WORD_BYTES for x in datas),
          str({len(x) for x in datas}))
    check("相邻两次互不相同",
          all(datas[i] != datas[i + 1] for i in range(len(datas) - 1)),
          " | ".join(x.hex().upper() for x in datas[:3]))
    check("至少一次非全 0", any(any(x) for x in datas))
    check("20 次共 20 个不同值", len({x.hex() for x in datas}) == 20,
          str(len({x.hex() for x in datas})))
    check("last_note 标注随机", "随机事件状态字" in (sim.last_note or ""),
          repr(sim.last_note))

    rsp = sim.handle_frame(REQ)[0]
    parsed = DLT645Parser().parse(rsp)
    check("随机帧可被解析器读回",
          parsed.get("valid") and parsed.get("di_code") == EVENT_WORD_DI,
          f"valid={parsed.get('valid')} di={parsed.get('di_code')}")

    # 其它 DI 不受随机影响
    other = GEN.build_frame(ADDR, GEN.build_control(0x11), encode_di("00010000"))
    r_other = sim.handle_frame(other)[0]
    check("随机模式不影响其它 DI（00010000 仍按档案）",
          payload_of(r_other)[4:] == bytes.fromhex("78563412"),
          payload_of(r_other).hex(" ").upper())


# ---------------------------------------------------------------------------
# 4. RandomEventWord 单测
# ---------------------------------------------------------------------------

def t_generator():
    print("\n== 4. RandomEventWord 单测 ==")
    g = RandomEventWord()
    v = g.next_value()
    check("返回值 24 位 hex", len(v) == 24 and all(c in "0123456789ABCDEF" for c in v), v)
    check("返回值 = 12 字节", len(bytes.fromhex(v)) == EVENT_WORD_BYTES)
    vs = [g.next_value() for _ in range(30)]
    check("连续 30 次互不相同", len(set(vs)) == 30, str(len(set(vs))))
    check("last_value 记录末次", g.last_value == vs[-1], f"{g.last_value} != {vs[-1]}")
    g.reset()
    check("reset 清空记忆", g.last_value is None, repr(g.last_value))

    # 注入「必定与上次碰撞一次」的桩：验证重抽
    class _StubRng:
        """前 nbytes 次调用返回 0（第一遍），随后返回 1（重抽后不同）。"""

        def __init__(self):
            self.calls = 0

        def randrange(self, _stop):
            self.calls += 1
            return 0 if self.calls <= EVENT_WORD_BYTES else 1

    stub = _StubRng()
    g2 = RandomEventWord(rng=stub)
    first = g2.next_value()
    second = g2.next_value()   # 第一遍全 0 会与 first 相同 → 必须重抽
    check("碰撞时重抽（不返回与上次相同的值）", first != second, f"{first} == {second}")
    check("重抽后取到新值（全 1 字节）",
          second == "01" * EVENT_WORD_BYTES, second)
    check("注入 rng 生效（确定性）",
          RandomEventWord(rng=random.Random(7)).next_value()
          == RandomEventWord(rng=random.Random(7)).next_value())
    check("字节数为 0 报错",
          _raises(lambda: RandomEventWord(nbytes=0)))


def _raises(fn):
    try:
        fn()
    except ValueError:
        return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# 5. 异常容错
# ---------------------------------------------------------------------------

def t_error_tolerance():
    print("\n== 5. 异常容错 ==")

    def boom():
        raise RuntimeError("模拟产生器故障")

    sim = DLT645MeterSim(address=ADDR, archive=DLT645Archive(), event_word_source=boom)
    rsp = sim.handle_frame(REQ)
    check("产生器抛异常不崩且有响应帧", len(rsp) == 1, str(rsp))
    check("失败时回落档案值（12 字节全 0）",
          payload_of(rsp[0])[4:] == b"\x00" * EVENT_WORD_BYTES,
          payload_of(rsp[0]).hex(" ").upper())
    check("last_error 记录失败原因", "随机事件状态字" in (sim.last_error or ""),
          repr(sim.last_error))
    check("失败时不置 last_note", not sim.last_note, repr(sim.last_note))

    sim2 = DLT645MeterSim(address=ADDR, archive=DLT645Archive(),
                          event_word_source=lambda: "XYZ")
    rsp2 = sim2.handle_frame(REQ)
    check("非法随机值回落档案且报错",
          payload_of(rsp2[0])[4:] == b"\x00" * EVENT_WORD_BYTES
          and "非法" in (sim2.last_error or ""),
          f"{payload_of(rsp2[0]).hex(' ')} | {sim2.last_error}")

    sim3 = DLT645MeterSim(address=ADDR, archive=DLT645Archive(),
                          event_word_source=lambda: "")
    rsp3 = sim3.handle_frame(REQ)
    check("空串随机值回落档案",
          payload_of(rsp3[0])[4:] == b"\x00" * EVENT_WORD_BYTES, sim3.last_error)

    sim5 = DLT645MeterSim(address=ADDR, archive=DLT645Archive(),
                          event_word_source=lambda: "AB12")
    rsp5 = sim5.handle_frame(REQ)
    check("长度不符的随机值回落档案（而非异常应答）",
          len(rsp5) == 1 and rsp5[0][8] == 0x91
          and payload_of(rsp5[0])[4:] == b"\x00" * EVENT_WORD_BYTES
          and "长度非法" in (sim5.last_error or ""),
          f"{rsp5[0].hex(' ').upper()} | {sim5.last_error}")

    # 未知 DI 仍回异常应答（既有行为不变）
    unknown = GEN.build_frame(ADDR, GEN.build_control(0x11), encode_di("1234ABCD"))
    sim4 = DLT645MeterSim(address=ADDR, archive=DLT645Archive())
    r4 = sim4.handle_frame(unknown)
    check("未知 DI 仍回异常应答 D1H",
          bool(r4) and r4[0][8] == 0xD1, r4[0].hex(" ").upper() if r4 else "无响应")


# ---------------------------------------------------------------------------
# 6. offscreen GUI
# ---------------------------------------------------------------------------

class _FakeMB:
    warned = []
    criticals = []
    questions = 0
    answer = True

    class StandardButton:
        Yes = 1
        No = 0

    @classmethod
    def warning(cls, *a, **k):
        cls.warned.append(a[2] if len(a) > 2 else "")

    @classmethod
    def critical(cls, *a, **k):
        cls.criticals.append(a[2] if len(a) > 2 else "")

    @classmethod
    def question(cls, *a, **k):
        cls.questions += 1
        return cls.StandardButton.Yes if cls.answer else cls.StandardButton.No

    @classmethod
    def reset(cls):
        cls.warned, cls.criticals, cls.questions = [], [], 0
        cls.answer = True


def t_gui():
    print("\n== 6. offscreen GUI ==")
    from PySide6.QtWidgets import QApplication

    import dlt645_meter_sim_widget as mw

    app = QApplication.instance() or QApplication([])
    real_mb = mw.QMessageBox
    mw.QMessageBox = _FakeMB
    with _SandboxPaths():
        w = mw.Dlt645VirtualMeterWidget()
        _gui_checks(w, app, mw)
        w.shutdown()
        app.processEvents()
    mw.QMessageBox = real_mb


def _gui_checks(w, app, mw):
    check("模拟设置小节存在",
          any("模拟设置" in g.title() for g in w.findChildren(mw.QGroupBox)),
          str([g.title() for g in w.findChildren(mw.QGroupBox)]))
    check("勾选框存在且默认不勾",
          hasattr(w, "chk_random_event") and not w.chk_random_event.isChecked())
    check("未勾选时引擎不注入随机源",
          w._make_engine().event_word_source is None)

    # 勾选 → 注入生效 + 持久化（写的是临时目录，见 _SandboxPaths）
    w.chk_random_event.setChecked(True)
    app.processEvents()
    check("勾选后引擎注入随机源", w._make_engine().event_word_source is not None)
    check("勾选写入日志", "随机产生事件：开启" in w.log_view.toPlainText(),
          w.log_view.toPlainText()[-120:])

    # 离线连点两次「生成响应」→ 两次响应不同（随机事件生效）
    w.req_input.setPlainText(REQ.hex(" ").upper())
    w._offline_generate()
    first = w._last_response_hex
    w._offline_generate()
    second = w._last_response_hex
    check("离线两次响应不同（随机生效）", first != second, f"{first} == {second}")
    check("离线日志标注随机事件状态字",
          "随机事件状态字" in w.log_view.toPlainText(),
          w.log_view.toPlainText()[-200:])
    check("两次响应长度均为 28 字节（L=0x10）",
          len(first.split()) == 28 and len(second.split()) == 28,
          f"{len(first.split())} / {len(second.split())}")

    w.chk_random_event.setChecked(False)
    app.processEvents()
    w._offline_generate()
    third = w._last_response_hex
    w._offline_generate()
    check("取消勾选后恢复不变化（两次相同）",
          third == w._last_response_hex, f"{third} != {w._last_response_hex}")


def t_gui_persistence():
    print("\n== 7. 勾选状态持久化 ==")
    import tempfile
    from PySide6.QtWidgets import QApplication

    import app_paths
    import dlt645_meter_sim_widget as mw

    app = QApplication.instance() or QApplication([])
    real_mb, real_path = mw.QMessageBox, app_paths.data_path
    mw.QMessageBox = _FakeMB
    tmp = tempfile.mkdtemp(prefix="dlt645_sim_")
    fake = os.path.join(tmp, mw.SETTINGS_FILE)
    app_paths.data_path = lambda name: __import__("pathlib").Path(fake)  # noqa: E731
    try:
        w = mw.Dlt645VirtualMeterWidget()
        w.chk_random_event.setChecked(True)      # 触发 _archive_save_quiet
        app.processEvents()
        w.shutdown()
        check("持久化文件已写出", os.path.exists(fake), fake)
        check("文件含 random_event=true",
              '"random_event": true' in io.open(fake, encoding="utf-8").read(),
              io.open(fake, encoding="utf-8").read()[:200])

        w2 = mw.Dlt645VirtualMeterWidget()       # 新建组件读回
        check("重载后勾选状态保持", w2.chk_random_event.isChecked())
        check("重载后引擎注入随机源", w2._make_engine().event_word_source is not None)
        check("重载后档案含 04001501",
              w2.archive.get(EVENT_WORD_DI) == "00" * 12,
              repr(w2.archive.get(EVENT_WORD_DI)))
        w2.shutdown()

        # 旧格式（无 random_event 字段）向后兼容
        io.open(fake, "w", encoding="utf-8").write(
            '{"address": "000000000001", "values": {"04001501": "00"}}')
        w3 = mw.Dlt645VirtualMeterWidget()
        check("旧 JSON 无该字段 → 默认不勾", not w3.chk_random_event.isChecked())
        check("旧 JSON 地址仍读回", w3.address == "000000000001", w3.address)

        # 导入旧格式（无 random_event 字段）→ 勾选必须回落 False（不保留上一个文件的状态）
        from PySide6.QtWidgets import QFileDialog
        legacy = os.path.join(tmp, "legacy_import.json")
        io.open(legacy, "w", encoding="utf-8").write(
            '{"address": "000000000002", "values": {"04001501": "00"}}')
        w3.chk_random_event.setChecked(True)   # 先打开勾选（会重写沙箱数据文件，故用独立文件导入）
        app.processEvents()
        real_open = QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (legacy, "JSON (*.json)"))
        try:
            w3._archive_import()
            app.processEvents()
        finally:
            QFileDialog.getOpenFileName = real_open
        check("导入旧 JSON（无该字段）勾选回落 False",
              not w3.chk_random_event.isChecked()
              and w3._make_engine().event_word_source is None,
              f"checked={w3.chk_random_event.isChecked()}")
        check("导入确实生效（地址取自导入文件）", w3.address == "000000000002", w3.address)
        w3.shutdown()
    finally:
        mw.QMessageBox = real_mb
        app_paths.data_path = real_path
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 8. 串口回环（可选）
# ---------------------------------------------------------------------------

#: GUI 用例统一在临时目录上跑：`chk_random_event` 的 toggled 会经
#: `_archive_save_quiet()` 写 dlt645_sim_data.json，绝不能碰用户真身档案
class _SandboxPaths:
    def __enter__(self):
        import pathlib
        import tempfile

        import app_paths

        self._real = app_paths.data_path
        self.tmp = tempfile.mkdtemp(prefix="dlt645_sim_test_")
        self.file = os.path.join(self.tmp, "dlt645_sim_data.json")
        app_paths.data_path = lambda name: pathlib.Path(self.file)
        return self

    def __exit__(self, *exc):
        import shutil

        import app_paths

        app_paths.data_path = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def _ports():
    try:
        import serial.tools.list_ports as lp
        return {p.device.upper() for p in lp.comports()}
    except Exception:
        return set()


def t_serial_loopback():
    print("\n== 8. 串口回环（COM1↔COM2，可选）==")
    ports = _ports()
    if not {"COM1", "COM2"} <= ports:
        print(f"[SKIP] 本机缺少 COM1/COM2 虚拟串口对（现有：{sorted(ports)}）")
        return
    import serial
    from PySide6.QtWidgets import QApplication

    import dlt645_meter_sim_widget as mw

    app = QApplication.instance() or QApplication([])
    real_mb = mw.QMessageBox
    mw.QMessageBox = _FakeMB
    with _SandboxPaths():        # 勾选开关会写档案文件 → 必须走临时目录
        w = mw.Dlt645VirtualMeterWidget()
        _loopback_checks(w, app, mw)
        w.shutdown()
        app.processEvents()
    mw.QMessageBox = real_mb


def _loopback_checks(w, app, mw):
    import serial

    peer = None
    try:
        w.port_combo.clear()
        w.port_combo.addItem("COM1", "COM1")
        w.port_combo.setCurrentIndex(0)
        w._toggle_serial()
        th = w._serial_thread
        t0 = time.time()
        while th is not None and th._ser is None and time.time() - t0 < 3:
            app.processEvents()
            time.sleep(0.05)
        check("串口从站已打开 COM1", th is not None and th._ser is not None, "COM1 未打开")

        peer = serial.Serial("COM2", 9600, timeout=0.3)
        peer.reset_input_buffer()
        w.chk_random_event.setChecked(True)
        app.processEvents()

        def one_round(wait=3.0):
            peer.reset_input_buffer()
            peer.write(REQ)
            t0 = time.time()
            got = b""
            while time.time() - t0 < wait and len(got) < 10 + 0x10 + 2:
                got += peer.read(64)
                app.processEvents()
                time.sleep(0.02)
            return got

        a = one_round()
        b = one_round()
        check("两次应答均收到且长度 28 字节",
              len(a) == 28 and len(b) == 28, f"{len(a)} / {len(b)}")
        check("两次应答功能码 91H 且 L=0x10",
              a[8] == 0x91 and b[8] == 0x91 and a[9] == 0x10 and b[9] == 0x10,
              f"{a.hex(' ')} | {b.hex(' ')}")
        check("两次读到的数据部分不同（随机生效）", a[10:26] != b[10:26],
              f"{a[10:26].hex(' ')} == {b[10:26].hex(' ')}")

        # 关闭随机 → 两次应相同
        w.chk_random_event.setChecked(False)
        app.processEvents()
        c = one_round()
        d = one_round()
        check("取消随机后两次应答完全相同", c == d, f"{c.hex(' ')} | {d.hex(' ')}")
        check("取消随机后数据为全 0",
              GEN.descramble(c[10:26])[4:] == b"\x00" * EVENT_WORD_BYTES,
              GEN.descramble(c[10:26]).hex(" ").upper())
    finally:
        if peer is not None:
            try:
                peer.close()
            except Exception:
                pass


def main():
    t_type_length_fix()
    t_default_unchanged()
    t_random_mode()
    t_generator()
    t_error_tolerance()
    t_gui()
    t_gui_persistence()
    t_serial_loopback()
    print(f"\n=== {PASS} 项通过，{len(FAILURES)} 项失败 ===")
    for f in FAILURES:
        print("  ✗", f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
