# -*- coding: utf-8 -*-
"""未捕获异常兜底：把崩溃现场写进 ``logs/crash_*.log``（纯逻辑 + 可选回调）。

为什么需要：GUI 程序崩溃时用户只会说"闪退了"，控制台又没有（打包后 `console=False`），
没有现场就只能猜。这里把异常类型、消息、完整 traceback、版本与系统信息落到文件，
并保留最近 N 份，用户可以用「帮助 → 生成诊断包」一并带出来。

设计要点：
- **绝不递归**：写日志本身出错时静默（不能再抛一次）；
- **不阻塞**：只写文件，不弹框；是否提示由调用方通过 ``on_crash`` 决定（且回调异常也被吞掉）；
- 兼容主线程（`sys.excepthook`）与子线程（`threading.excepthook`）。
"""

from __future__ import annotations

import os
import platform
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, Mapping, Optional, Type

MAX_KEEP = 20
CRASH_DIR_NAME = "logs"


def crash_dir(base_dir: Path | str) -> Path:
    """崩溃日志目录：``<数据目录>/logs``（不存在则创建）。"""
    path = Path(base_dir) / CRASH_DIR_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path


def format_crash_report(exc_type: Type[BaseException], exc: BaseException,
                        tb: Optional[TracebackType], *, app_version: str = "",
                        build_date: str = "", thread_name: str = "",
                        extra: Optional[Mapping[str, Any]] = None) -> str:
    """把一次异常格式化成可读文本（便于测试，也便于用户直接看）。"""
    lines = [
        "南网协议解析工具 · 崩溃报告",
        "=" * 40,
        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"版本：{app_version}（编译于 {build_date}）",
        f"Python：{sys.version.split()[0]}",
        f"系统：{platform.system()} {platform.release()} ({platform.version()})",
        f"架构：{platform.machine()}",
        f"打包运行：{'是' if getattr(sys, 'frozen', False) else '否'}",
        f"可执行文件：{sys.executable}",
        f"线程：{thread_name or threading.current_thread().name}",
    ]
    if extra:
        for key, value in extra.items():
            lines.append(f"{key}：{value}")
    lines += [
        "",
        f"异常类型：{getattr(exc_type, '__name__', str(exc_type))}",
        f"异常信息：{exc}",
        "",
        "调用栈：",
        "".join(traceback.format_exception(exc_type, exc, tb)).rstrip(),
        "",
    ]
    return "\n".join(lines)


def write_crash_report(exc_type: Type[BaseException], exc: BaseException,
                       tb: Optional[TracebackType], base_dir: Path | str, *,
                       app_version: str = "", build_date: str = "",
                       thread_name: str = "",
                       extra: Optional[Mapping[str, Any]] = None,
                       max_keep: int = MAX_KEEP) -> Optional[Path]:
    """写一份崩溃日志并清理旧文件；任何失败都返回 ``None``（不抛）。"""
    try:
        directory = crash_dir(base_dir)
        # 微秒级时间戳 + pid：同一秒内连续崩溃也不会互相覆盖
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = directory / f"crash_{stamp}_{os.getpid()}.log"
        path.write_text(
            format_crash_report(exc_type, exc, tb, app_version=app_version,
                                build_date=build_date, thread_name=thread_name, extra=extra),
            encoding="utf-8", errors="replace")
        _prune(directory, max_keep)
        return path
    except BaseException:  # noqa: BLE001 - 兜底逻辑自身绝不能再抛
        return None


def _prune(directory: Path, max_keep: int) -> None:
    try:
        items = sorted(directory.glob("crash_*.log"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for old in items[max(0, int(max_keep)):]:
            try:
                old.unlink()
            except OSError:
                pass
    except OSError:
        pass


_installed = False


def install(app_version: str = "", build_date: str = "",
            base_dir: Path | str | None = None,
            on_crash: Optional[Callable[[Optional[Path], str], None]] = None) -> None:
    """安装全局崩溃钩子（重复调用幂等）。

    ``on_crash(path, summary)`` 会在**出事的线程**里被调用：只做轻量提示，
    不要在里面长时间阻塞或直接操作可能已损坏的界面。
    """
    global _installed
    if _installed:
        return
    _installed = True

    def _handle(exc_type, exc, tb, thread_name: str = "") -> None:
        if exc_type is SystemExit:
            return
        path = None
        summary = ""
        try:
            summary = format_crash_report(exc_type, exc, tb, app_version=app_version,
                                          build_date=build_date, thread_name=thread_name)
            if base_dir is not None:
                path = write_crash_report(exc_type, exc, tb, base_dir,
                                          app_version=app_version, build_date=build_date,
                                          thread_name=thread_name)
        except BaseException:  # noqa: BLE001
            pass
        # 控制台版本仍保留原始输出（打包后 stderr 为 None，跳过）
        try:
            stream = sys.__stderr__
            if stream is not None:
                stream.write(summary + "\n")
                stream.flush()
        except BaseException:  # noqa: BLE001
            pass
        if on_crash is not None:
            try:
                on_crash(path, summary)
            except BaseException:  # noqa: BLE001
                pass

    def _sys_hook(exc_type, exc, tb):
        _handle(exc_type, exc, tb)

    def _thread_hook(args):
        _handle(args.exc_type, args.exc_value, args.exc_traceback,
                getattr(getattr(args, "thread", None), "name", ""))

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


__all__ = ["CRASH_DIR_NAME", "MAX_KEEP", "crash_dir", "format_crash_report",
           "write_crash_report", "install"]
