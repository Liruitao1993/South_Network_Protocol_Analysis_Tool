"""本进程资源占用采样（CPU% / 内存 MB）——纯标准库，无 Qt、无 psutil 依赖。

- Windows：ctypes 调 kernel32.GetProcessTimes + psapi.GetProcessMemoryInfo
- Linux：读 /proc/self/stat（utime/stime/rss）与 /proc/self/status（VmHWM 峰值）
- macOS / 其他平台：返回 None（状态栏显示 "--"），安全降级不报错

CPU 百分比说明：以「整机」为基准（进程 CPU 秒 / 墙钟秒 / 逻辑核数 × 100），
与 Windows 任务管理器默认口径一致，值域 0~100%。首次采样因无基线返回 None。

采样本身为一次系统调用/读小文件，微秒级开销，适合 3~5 秒慢刷新定时器。
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass


@dataclass
class ProcSample:
    """一次进程资源采样结果。取不到的字段为 None（UI 显示 --）。"""

    cpu_pct: float | None  # 整机口径 CPU 占用百分比（0~100），首次采样为 None
    mem_mb: float | None  # 当前物理内存（工作集 / RSS），MB
    mem_peak_mb: float | None  # 峰值物理内存，MB


class ProcessStats:
    """进程资源采样器。保留上一次 CPU 时间基线，sample() 间隔调用即可得 CPU%。"""

    def __init__(self):
        self._last_cpu_sec: float | None = None
        self._last_wall: float | None = None
        self._ncpu: int = os.cpu_count() or 1

    def sample(self) -> ProcSample:
        """采样一次。CPU% 需要两次采样之间的差值，首次调用 cpu_pct=None。"""
        cpu_sec = _read_cpu_seconds()
        mem_mb, peak_mb = _read_memory_mb()
        now = time.monotonic()

        cpu_pct: float | None = None
        if (
            cpu_sec is not None
            and self._last_cpu_sec is not None
            and self._last_wall is not None
        ):
            dwall = max(now - self._last_wall, 1e-6)
            dcpu = max(cpu_sec - self._last_cpu_sec, 0.0)
            # 整机口径：单核满负载 = 100%/核数
            pct = dcpu / dwall / self._ncpu * 100.0
            cpu_pct = max(0.0, min(pct, 100.0))
        self._last_cpu_sec = cpu_sec
        self._last_wall = now

        return ProcSample(cpu_pct=cpu_pct, mem_mb=mem_mb, mem_peak_mb=peak_mb)


# ----------------------------- 平台适配 -----------------------------


def _read_cpu_seconds() -> float | None:
    """进程累计 CPU 时间（用户+内核），单位秒。"""
    if sys.platform.startswith("win"):
        return _win_cpu_seconds()
    if sys.platform.startswith("linux"):
        return _linux_cpu_seconds()
    return None


def _read_memory_mb():
    """返回 (当前物理内存MB, 峰值物理内存MB)。"""
    if sys.platform.startswith("win"):
        return _win_memory_mb()
    if sys.platform.startswith("linux"):
        return _linux_memory_mb()
    return None, None


# ---- Windows ----

if sys.platform.startswith("win"):
    import ctypes
    from ctypes import wintypes

    class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]


def _win_cpu_seconds() -> float | None:
    import ctypes
    from ctypes import wintypes

    class _FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    h = kernel32.GetCurrentProcess()
    creation, exit_t, kernel, user = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
    ok = kernel32.GetProcessTimes(
        h,
        ctypes.byref(creation),
        ctypes.byref(exit_t),
        ctypes.byref(kernel),
        ctypes.byref(user),
    )
    if not ok:
        return None

    def _ft(ft) -> int:
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

    # kernel 时间含空闲时间；GetProcessTimes 的 kernel 对本进程即内核态时间。
    # FILETIME 单位 = 100 纳秒，1e7 个单位 = 1 秒。
    return (_ft(kernel) + _ft(user)) / 1e7


def _win_memory_mb():
    import ctypes
    from ctypes import wintypes

    pmc = _PROCESS_MEMORY_COUNTERS()
    pmc.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
    kernel32 = ctypes.windll.kernel32
    # GetProcessMemoryInfo：Win7+ 同时在 kernel32(K32...) 与 psapi 导出
    get_mem_info = (
        getattr(kernel32, "K32GetProcessMemoryInfo", None)
        or ctypes.windll.psapi.GetProcessMemoryInfo
    )
    get_mem_info.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
        wintypes.DWORD,
    ]
    get_mem_info.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    h = kernel32.GetCurrentProcess()
    if not get_mem_info(h, ctypes.byref(pmc), pmc.cb):
        return None, None
    mb = 1024 * 1024
    return pmc.WorkingSetSize / mb, pmc.PeakWorkingSetSize / mb


# ---- Linux ----


def _linux_stat_fields():
    """读 /proc/self/stat，返回 comm 之后的字段列表（fields[0]=state）。失败返回 []。"""
    try:
        with open("/proc/self/stat") as f:
            data = f.read()
    except OSError:
        return []
    # 进程名在括号内且可能含空格/括号：取最后一个 ')' 之后切分
    rparen = data.rfind(")")
    fields = data[rparen + 2 :].split()
    # 字段编号从 comm 之后开始：fields[0] 对应标准第 3 字段 state
    return fields


def _linux_clk_tck() -> float:
    """sysconf(SC_CLK_TCK)：每秒时钟滴答数（Linux 专用，Windows 无此属性）。"""
    sysconf = getattr(os, "sysconf", None)
    sysconf_names = getattr(os, "sysconf_names", None)
    if sysconf is None or sysconf_names is None or "SC_CLK_TCK" not in sysconf_names:
        return 100.0  # Linux 标准默认值
    try:
        return float(sysconf(sysconf_names["SC_CLK_TCK"]))
    except (OSError, ValueError):
        return 100.0


def _linux_page_size() -> int:
    """sysconf(SC_PAGE_SIZE)：内存页字节数（Linux 专用，Windows 无此属性）。"""
    sysconf = getattr(os, "sysconf", None)
    sysconf_names = getattr(os, "sysconf_names", None)
    if sysconf is None or sysconf_names is None:
        return 4096
    for key in ("SC_PAGE_SIZE", "SC_PAGESIZE"):
        if key in sysconf_names:
            try:
                return int(sysconf(sysconf_names[key]))
            except (OSError, ValueError):
                return 4096
    return 4096


def _linux_cpu_seconds() -> float | None:
    try:
        fields = _linux_stat_fields()
        # 第 14 字段 utime、第 15 字段 stime（1-based，含 comm 前两字段）
        # rparen 后 fields[0]=state(第3字段)，故 utime=fields[11], stime=fields[12]
        utime = int(fields[11])
        stime = int(fields[12])
        clk_tck = _linux_clk_tck()
        return (utime + stime) / clk_tck
    except Exception:
        return None


def _linux_memory_mb():
    try:
        fields = _linux_stat_fields()
        # 第 24 字段 rss（页数）→ rparen 后 fields[21]
        page_size = _linux_page_size()
        rss_mb = int(fields[21]) * page_size / (1024 * 1024)
    except Exception:
        rss_mb = None
    peak_mb = None
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    peak_mb = float(line.split()[1]) / 1024.0  # kB → MB
                    break
    except Exception:
        pass
    return rss_mb, peak_mb
