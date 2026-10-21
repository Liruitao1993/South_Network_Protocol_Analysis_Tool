# -*- coding: utf-8 -*-
"""崩溃兜底回归：异常必须落盘、回调异常不外泄、SystemExit 不误报、旧日志会被清理。

运行: python test/test_crash_handler.py
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crash_handler  # noqa: E402
from crash_handler import (format_crash_report, install, write_crash_report)  # noqa: E402


def _reset():
    crash_handler._installed = False


def test_format_contains_context():
    try:
        raise ValueError("坏帧")
    except ValueError:
        exc_type, exc, tb = sys.exc_info()
        text = format_crash_report(exc_type, exc, tb, app_version="1.23.90",
                                   build_date="2026-10-20", thread_name="主线程")
    assert "1.23.90" in text and "2026-10-20" in text
    assert "ValueError" in text and "坏帧" in text
    assert "Traceback" in text and "主线程" in text
    assert "崩溃报告" in text


def test_write_creates_file_and_prunes():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            raise RuntimeError("第一次")
        except RuntimeError:
            info = sys.exc_info()
            path = write_crash_report(*info, tmp, app_version="1.0", max_keep=3)
        assert path is not None and path.exists()
        assert path.parent.name == "logs"
        assert "RuntimeError" in path.read_text(encoding="utf-8")

        # 再造 5 份，只保留最新 3 份
        for i in range(5):
            write_crash_report(*info, tmp, app_version="1.0", max_keep=3)
            time.sleep(0.01)
        files = list((Path(tmp) / "logs").glob("crash_*.log"))
        assert len(files) == 3, [f.name for f in files]


def test_write_never_raises_on_bad_dir():
    # 用一个"文件"当目录：mkdir 失败也不能抛
    with tempfile.TemporaryDirectory() as tmp:
        blocker = Path(tmp) / "logs"
        blocker.write_text("not a dir", encoding="utf-8")
        try:
            raise ValueError("x")
        except ValueError:
            info = sys.exc_info()
            assert write_crash_report(*info, tmp) is None


def test_install_hook_writes_and_calls_back():
    saved_sys, saved_thread = sys.excepthook, threading.excepthook
    _reset()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            install("1.23.90", "2026-10-20", tmp,
                    on_crash=lambda path, summary: calls.append((path, summary)))
            # 子线程里的未捕获异常 → threading.excepthook
            def boom():
                raise KeyError("线程炸了")

            t = threading.Thread(target=boom, name="worker-7")
            t.start()
            t.join()
            files = list((Path(tmp) / "logs").glob("crash_*.log"))
            assert len(files) == 1, files
            text = files[0].read_text(encoding="utf-8")
            assert "KeyError" in text and "worker-7" in text
            assert calls and calls[0][0] is not None

            # 主线程钩子：直接调用，且 SystemExit 不产生新文件
            before = len(list((Path(tmp) / "logs").glob("crash_*.log")))
            sys.excepthook(SystemExit, SystemExit("quit"), None)
            assert len(list((Path(tmp) / "logs").glob("crash_*.log"))) == before
            sys.excepthook(ValueError, ValueError("主线程"), None)
            assert len(list((Path(tmp) / "logs").glob("crash_*.log"))) == before + 1
    finally:
        sys.excepthook, threading.excepthook = saved_sys, saved_thread
        _reset()


def test_callback_exception_is_swallowed():
    saved_sys = sys.excepthook
    _reset()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            def bad_cb(path, summary):
                raise RuntimeError("回调也炸")

            install("1.0", "", tmp, on_crash=bad_cb)
            sys.excepthook(ValueError, ValueError("原始错误"), None)   # 不应抛出
    finally:
        sys.excepthook = saved_sys
        _reset()


def test_install_is_idempotent():
    saved_sys, saved_thread = sys.excepthook, threading.excepthook
    _reset()
    try:
        install("1.0", "", None)
        first = sys.excepthook
        install("1.0", "", None)
        assert sys.excepthook is first, "重复安装应保持同一个钩子"
    finally:
        sys.excepthook, threading.excepthook = saved_sys, saved_thread
        _reset()


def run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERR   {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)
