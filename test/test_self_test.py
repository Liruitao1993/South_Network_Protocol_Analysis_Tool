# -*- coding: utf-8 -*-
"""`exe --self-test` 自检入口回归：正常返回 0，坏模块能被报出来。

运行: python test/test_self_test.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import parser_registry  # noqa: E402
import self_test  # noqa: E402


def test_run_ok_and_reports():
    buf = io.StringIO()
    code = self_test.run(buf)
    text = buf.getvalue()
    assert code == 0, text
    assert "解析器：12 个已加载" in text
    assert "75 字节样例一致" in text
    assert text.strip().endswith("OK")


def test_run_detects_broken_parser(monkeypatch=None):
    saved = dict(parser_registry._PARSER_SPECS)
    try:
        parser_registry._PARSER_SPECS["__broken__"] = ("module_that_does_not_exist", "Nope")
        buf = io.StringIO()
        code = self_test.run(buf)
        text = buf.getvalue()
        assert code == 1, text
        assert "__broken__" in text and "FAIL" in text
    finally:
        parser_registry._PARSER_SPECS.clear()
        parser_registry._PARSER_SPECS.update(saved)
        # 清掉可能被缓存的空实例
        parser_registry._INSTANCES.pop("__broken__", None)
        parser_registry._MODULES.pop("__broken__", None)


def test_cli_flag_exits_without_qt():
    """`python main_gui.py --self-test` 应在建窗之前退出（不阻塞、不写文件）。"""
    import subprocess

    # 显式按 UTF-8 解码：子进程输出是中文（self_test 里已 reconfigure 成 UTF-8），
    # 而 Windows CI runner 的默认 locale 是 cp1252，用 text=True 会 UnicodeDecodeError。
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "main_gui.py"), "--self-test"],
        cwd=str(Path(__file__).resolve().parent.parent),
        capture_output=True, encoding="utf-8", errors="replace", timeout=120,
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8", "QT_QPA_PLATFORM": "offscreen"},
    )
    assert proc.returncode == 0, (proc.returncode, proc.stdout[-500:], proc.stderr[-500:])
    assert "[self-test] OK" in (proc.stdout or "")


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
