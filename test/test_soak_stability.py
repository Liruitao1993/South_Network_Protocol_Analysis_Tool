# -*- coding: utf-8 -*-
"""短时长稳（soak）回归：反复切页 + 高频收包，不许崩、不许内存失控。

这类测试不是替代 8 小时长稳，而是在提交前用 10~20 秒把最容易出问题的两条路径压一遍：
1. **反复切换全部标签页**（页面创建/销毁、定时器、信号重连）；
2. **高频接收**（生产测试架日志合并刷新、块数上限、UI 事件处理）。

判据（本机实测留有余量）：
- 切页 1000 次 < 60 s，RSS 增长 < 80 MB；
- 灌 5000 帧 < 30 s，日志块数 ≤ `LOG_MAX_BLOCKS`，RSS 增长 < 120 MB。

运行: python test/test_soak_stability.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

SANDBOX = _config_sandbox.install()

import main_gui  # noqa: E402


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


try:
    _psapi = ctypes.WinDLL("psapi")
    _psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    _psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    _k32 = ctypes.WinDLL("kernel32")
    _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _HPROC = _k32.GetCurrentProcess()
except Exception:  # noqa: BLE001 - 非 Windows 退化为 None
    _psapi = None
    _HPROC = None


def rss_mb():
    if _psapi is None:
        return 0.0
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    _psapi.GetProcessMemoryInfo(_HPROC, ctypes.byref(pmc), pmc.cb)
    return pmc.WorkingSetSize / 1048576.0


class _FakeWorker(QObject):
    raw_data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def is_open(self):
        return True

    def write_raw(self, data):
        return True


def test_tab_switching_soak(app, win):
    count = win.tab_widget.count()
    assert count >= 15, count
    # 先热两遍：首/次遍会创建页面并填充 Qt 的绘制/字体缓存（一次性内存），不算泄漏
    for _ in range(2):
        for i in range(count):
            win.tab_widget.setCurrentIndex(i)
            app.processEvents()
    import gc
    gc.collect()
    app.processEvents()
    import gc

    base = rss_mb()
    started = time.perf_counter()
    marks = []
    # 分 3 段各 200 次：最后一段必须基本不涨（前面涨的是 Qt 绘制缓存填充，会饱和）
    for _block in range(3):
        for _round in range(10):
            for i in range(count):
                win.tab_widget.setCurrentIndex(i)
                app.processEvents()
        gc.collect()
        app.processEvents()
        marks.append(rss_mb())
    elapsed = time.perf_counter() - started
    grow = marks[-1] - base
    tail_grow = marks[-1] - marks[-2]
    print(f"    切页 600 次：{elapsed:.1f}s，RSS {base:.0f} → "
          f"{marks[0]:.0f} → {marks[1]:.0f} → {marks[2]:.0f} MB")
    assert elapsed < 45.0, f"切页耗时 {elapsed:.1f}s 超过 45s"
    assert tail_grow < 15.0, f"最后 200 次切页内存仍涨 {tail_grow:.0f} MB（疑似泄漏）"
    assert grow < 70.0, f"切页总内存增长 {grow:.0f} MB 超过 70MB"


def test_log_flood_soak(app, win):
    from production_testbench_widget import LOG_MAX_BLOCKS

    win.tab_widget.setCurrentIndex(win._testbench_tab_index)
    app.processEvents()
    tab = win.testbench_tab
    fake = _FakeWorker()
    tab.set_serial_worker(fake)
    tab.chk_timestamp.setChecked(False)       # 时间戳不是本测试要验证的点，省点开销

    payload = bytes.fromhex("68AAAAAAAAAAAA68940455AA55AA000016")
    frames = 5000
    base = rss_mb()
    started = time.perf_counter()
    for i in range(frames):
        fake.raw_data_received.emit(payload)
        if i % 500 == 0:
            app.processEvents()
    tab._flush_log()
    app.processEvents()
    elapsed = time.perf_counter() - started
    grow = rss_mb() - base
    blocks = tab.log_text.blockCount()
    print(f"    灌 {frames} 帧：{elapsed:.1f}s，日志块 {blocks}，RSS {base:.0f} → {rss_mb():.0f} MB")
    assert elapsed < 30.0, f"高频收包耗时 {elapsed:.1f}s 超过 30s"
    assert blocks <= LOG_MAX_BLOCKS + 5, f"日志块数 {blocks} 超过上限 {LOG_MAX_BLOCKS}"
    assert grow < 120.0, f"高频收包后内存增长 {grow:.0f} MB 超过 120MB"
    # 队列必须已清空（不丢尾、也不积压）
    assert not tab._pending_log, f"仍有 {len(tab._pending_log)} 行未刷出"


def run_all():
    app = QApplication.instance() or QApplication([])
    win = main_gui.MainWindow()
    win.resize(1400, 900)
    win.show()
    app.processEvents()
    tests = [test_tab_switching_soak, test_log_flood_soak]
    failures = 0
    for fn in tests:
        try:
            fn(app, win)
            print(f"  OK  {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERR   {fn.__name__}: {type(exc).__name__}: {exc}")
    try:
        win.close()
    except Exception:  # noqa: BLE001
        pass
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    code = run_all()
    sys.stdout.flush()
    os._exit(code)
