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


if __name__ == "__main__":
    test_proc_stats_sampler()
    test_gui_statusbar()
    test_thread_detail_menu()
    test_cpu_color_threshold()
    print("\n=== test_statusbar_stats 全部通过 ===")
