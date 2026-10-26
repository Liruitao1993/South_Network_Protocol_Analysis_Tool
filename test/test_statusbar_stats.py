"""状态栏资源占用（CPU/内存）与线程明细弹窗测试。

覆盖：
- proc_stats.ProcessStats 纯逻辑采样（平台相关字段合理、CPU 两次采样后有值、取值范围）
- MainWindow 状态栏 CPU/内存/线程标签初始化与刷新
- 点击线程标签弹出的明细 QMenu 结构（分组标题/条目数/复制动作）

运行：python test/test_statusbar_stats.py
"""

import os
import sys
import time

# Windows 控制台默认 GBK，重配 stdout/stderr 为 UTF-8 以输出中文/✓
for _stream in (sys.stdout, sys.stderr):
    _reconf = getattr(_stream, "reconfigure", None)
    if callable(_reconf):
        try:
            _reconf(encoding="utf-8")
        except Exception:
            pass

import _path_setup  # noqa: E402,F401  路径引导：切到项目根

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 无 GUI 环境也能跑

import proc_stats  # noqa: E402
import thread_registry  # noqa: E402


def test_proc_stats_sampler():
    """纯逻辑：采样器首次无 CPU%，第二次起有值且在 0~100，内存为正数。"""
    ps = proc_stats.ProcessStats()
    s1 = ps.sample()
    # 首次无基线，CPU% 为 None
    assert s1.cpu_pct is None
    # 内存：支持的平台（Windows/Linux）应为正数；macOS 等为 None
    if sys.platform.startswith(("win", "linux")):
        assert s1.mem_mb is not None and s1.mem_mb > 1
        assert s1.mem_peak_mb is not None and s1.mem_peak_mb >= s1.mem_mb
    # 制造 CPU 负载后第二次采样
    x = 0
    for i in range(20_000_000):
        x += i
    time.sleep(0.05)
    s2 = ps.sample()
    if sys.platform.startswith(("win", "linux")):
        assert s2.cpu_pct is not None, "第二次采样应有 CPU%"
        assert 0.0 <= s2.cpu_pct <= 100.0
    assert x > 0
    print(
        "✓ proc_stats 采样：首帧无 CPU 基线，二帧 CPU=%.2f%% 内存=%.1fMB 峰值=%.1fMB"
        % (s2.cpu_pct or -1, s2.mem_mb or -1, s2.mem_peak_mb or -1)
    )


def test_gui_statusbar():
    """GUI：状态栏三标签初始化、刷新、线程数与 registry 一致、CPU/内存标签有内容。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from main_gui import MainWindow

    w = MainWindow()

    # CPU/内存标签：首帧（内存应有，CPU 可能 -- 或 0）
    w._refresh_cpu_mem()
    txt = w._cpu_mem_lbl.text()
    assert "CPU:" in txt and "内存:" in txt
    # 线程标签
    w._refresh_thread_count()
    py, qt = thread_registry.snapshot()
    total = len(py) + len(qt)
    assert w._thread_count_lbl.text() == f"线程: {total}"
    # 点击交互：手型光标 + mousePressEvent 绑定
    assert w._thread_count_lbl.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert callable(w._thread_count_lbl.mousePressEvent)
    # 慢刷新定时器间隔应为 4 秒（避免高频影响 GUI）
    assert w._cpu_mem_timer.interval() == 4000
    print(
        f"✓ 状态栏：CPU/内存标签='{txt}'，线程='{w._thread_count_lbl.text()}'，"
        f"CPU 定时器 {w._cpu_mem_timer.interval()}ms"
    )
    return w, app


def test_thread_detail_menu():
    """线程明细菜单构建：含两个分组标题、条目数与快照一致、含复制动作（不弹模态）。"""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from main_gui import MainWindow

    w = MainWindow()

    # 直接构建菜单（纯构建，不调用 exec 模态弹出）
    menu, py, qt, copy_act = w._build_thread_detail_menu()
    texts = [a.text() for a in menu.actions()]
    py2, qt2 = thread_registry.snapshot()
    assert len(py) == len(py2) and len(qt) == len(qt2)
    # 含两个分组标题
    assert any(f"Python 线程（{len(py)}）" in t for t in texts), texts
    assert any(f"QThread 工作线程（{len(qt)}）" in t for t in texts), texts
    # 含复制动作且可点击（enabled）
    assert copy_act is not None and "复制线程列表" in copy_act.text()
    assert copy_act.isEnabled()
    # 复制动作：验证 _copy_thread_list 会写剪贴板
    w._copy_thread_list(py, qt)
    clip = QApplication.clipboard().text()
    assert "Python 线程" in clip and "QThread" in clip
    print(
        f"✓ 线程明细菜单：{len(texts)} 个动作项，"
        f"Python {len(py)} / QThread {len(qt)}，含复制动作，剪贴板 {len(clip)} 字"
    )


def test_cpu_color_threshold():
    """CPU 着色逻辑：构造假采样验证 <30 灰 / 30-60 橙 / >=60 红。"""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from main_gui import MainWindow
    from proc_stats import ProcSample

    w = MainWindow()

    def color_for(cpu):
        w._cpu_mem_lbl.setStyleSheet("color: #607D8B;")
        # 直接构造一个假样本替换采样
        orig = w._proc_stats.sample
        w._proc_stats.sample = lambda: ProcSample(
            cpu_pct=cpu, mem_mb=100.0, mem_peak_mb=120.0
        )
        w._refresh_cpu_mem()
        style = w._cpu_mem_lbl.styleSheet()
        w._proc_stats.sample = orig
        return style

    grey = color_for(10.0)
    orange = color_for(45.0)
    red = color_for(80.0)
    assert "#607D8B" in grey, grey
    assert "#FB8C00" in orange, orange
    assert "#E53935" in red, red
    print("✓ CPU 着色阈值：<30% 灰、30-60% 橙、≥60% 红")


def test_conn_indicators():
    """状态栏串口/蓝牙连接指示：常驻、图标按状态染色、tooltip 给细节、点击可用。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from main_gui import MainWindow

    w = MainWindow()
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    w.show()
    app.processEvents()
    w._ui_ready = False          # 本用例会点顶栏开关，禁止顺手写真实 config.json
    # 配色断言必须与「当前外观」解耦：用户真实 config.json 可能是深色外观，
    # 那样状态栏取的是 CONN_INDICATOR_COLORS[True]。本用例先固定浅色（④ 再单独测深色）。
    w._theme_id = "default"
    w._appearance_mode = "light"
    w._refresh_conn_indicators()

    serial_btn, bt_btn = w._serial_conn_btn, w._bt_conn_btn
    colors = MainWindow.CONN_INDICATOR_COLORS
    gray = colors[False]["off"]
    green = colors[False]["on"]

    def icon_color(btn):
        """取图标里出现最多的不透明像素颜色（抗锯齿边缘会偏色，取实心线条处）。"""
        img = btn.icon().pixmap(btn.iconSize()).toImage()
        counts = {}
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                if c.alpha() >= 200:
                    counts[c.name()] = counts.get(c.name(), 0) + 1
        return max(counts.items(), key=lambda kv: kv[1])[0] if counts else ""

    def near(a, b, tol=10):
        if not a or not b:
            return False
        return all(
            abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) <= tol for i in (1, 3, 5)
        )

    # ① 常驻 + 文案 + 图标来自项目 icons
    assert serial_btn.parent() is w.statusBar() and bt_btn.parent() is w.statusBar()
    assert serial_btn.text() == "串口" and bt_btn.text() == "蓝牙"
    assert not serial_btn.icon().isNull() and not bt_btn.icon().isNull()

    # ② 未连接 ⇒ 灰
    class FakeSerial:
        """只提供串口线程**真实**的连接方法 `is_open()`（不提供 is_connected）。

        回归：主窗口曾只调 `worker.is_connected()` 并吞掉 AttributeError ⇒ 状态栏永远显示
        「未连接」（现场报障 2026-10-26）。这个假对象让「只认 is_connected」的实现直接变红。
        """

        def __init__(self, connected):
            self._c = connected

        def is_open(self):
            return self._c

    class FakeBtWorker:
        def is_connected(self):
            return True

        def device_name(self):
            return "NW-METER-01"

    class FakeBtTab:
        def bluetooth_worker(self):
            return FakeBtWorker()

    w.serial_worker = FakeSerial(False)
    w._refresh_conn_indicators()
    assert near(icon_color(serial_btn), gray), icon_color(serial_btn)
    assert near(icon_color(bt_btn), gray), icon_color(bt_btn)
    assert "未连接" in serial_btn.toolTip() and "未连接" in bt_btn.toolTip()

    # ②b 真实 SerialWorker：is_connected 是 is_open 的别名（未打开时为 False）
    from serial_worker import SerialWorker
    real = SerialWorker()
    assert real.is_open() is False and real.is_connected() is False
    assert MainWindow._worker_connected(real) is False
    assert MainWindow._worker_connected(FakeSerial(True)) is True

    # ③ 已连接 ⇒ 绿（串口带端口/波特率，蓝牙带设备名）
    w.serial_worker = FakeSerial(True)
    w.bluetooth_tool_tab = FakeBtTab()
    w._refresh_conn_indicators()
    assert near(icon_color(serial_btn), green), icon_color(serial_btn)
    assert near(icon_color(bt_btn), green), icon_color(bt_btn)
    assert "已连接" in serial_btn.toolTip()
    assert "NW-METER-01" in bt_btn.toolTip()

    # ④ 深色主题用深色那套绿
    w._theme_id = "dark"
    w._appearance_mode = "light"
    w._refresh_conn_indicators()
    assert near(icon_color(bt_btn), colors[True]["on"]), icon_color(bt_btn)
    w._theme_id = "default"

    # ⑤ 断开回落灰
    w.serial_worker = FakeSerial(False)
    w.bluetooth_tool_tab = None
    w._refresh_conn_indicators()
    assert near(icon_color(serial_btn), gray) and near(icon_color(bt_btn), gray)

    # ⑥ 点串口指示：顶栏折叠时展开（端口/波特率在顶栏）
    w.topbar_toggle_btn.setChecked(False)
    w._toggle_top_bar()
    app.processEvents()
    assert not w.top_bar_widget.isVisible()
    w._on_serial_indicator_clicked()
    app.processEvents()
    assert w.topbar_toggle_btn.isChecked() and w.top_bar_widget.isVisible()

    # ⑦ 蓝牙页的信号驱动（真页 + 假 worker，走真实接线）
    del w.bluetooth_tool_tab
    real_serial, w.serial_worker = w.serial_worker, None
    tab = w._ensure_bluetooth_tool_tab()
    tab._worker = FakeBtWorker()
    tab.connection_state_changed.emit(True)
    app.processEvents()
    assert near(icon_color(bt_btn), green), icon_color(bt_btn)
    tab._worker = None
    tab.connection_state_changed.emit(False)
    app.processEvents()
    assert near(icon_color(bt_btn), gray), icon_color(bt_btn)
    w.serial_worker = real_serial
    print(
        f"✓ 连接指示：串口/蓝牙常驻状态栏，灰={gray} 绿={green}，"
        f"点串口展开顶栏、蓝牙信号即时同步"
    )


if __name__ == "__main__":
    test_proc_stats_sampler()
    test_gui_statusbar()
    test_thread_detail_menu()
    test_cpu_color_threshold()
    test_conn_indicators()
    print("\n=== test_statusbar_stats 全部通过 ===")
