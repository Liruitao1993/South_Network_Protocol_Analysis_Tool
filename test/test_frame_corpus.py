# -*- coding: utf-8 -*-
"""真实帧语料库回归：`test/frames/<registry_key>/*.hex` 每帧都必须能解析出内容。

这是「解析准确性」最便宜也最有效的一道护栏：
新增/修改解析器后，把现场脱敏实帧丢进对应目录，跑这个脚本——一条都不能回归。

运行: python test/test_frame_corpus.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import parser_registry as reg  # noqa: E402

FRAMES_DIR = Path(__file__).resolve().parent / "frames"
MIN_TOTAL_FRAMES = 3


def load_frame(path: Path) -> bytes:
    """读取一帧：忽略 `#` 注释与空行，去掉空白后按 hex 解析。"""
    chunks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            chunks.append(line.replace(" ", "").replace("\t", ""))
    return bytes.fromhex("".join(chunks))


def parse_any(parser, data: bytes):
    """兼容两种解析器接口：大多数是 parse_to_table，DLT645 是 parse(dict)。"""
    if hasattr(parser, "parse_to_table"):
        return parser.parse_to_table(data)
    return parser.parse(data)


def test_corpus_dirs_match_registry():
    keys = {p.name for p in FRAMES_DIR.iterdir() if p.is_dir()}
    known = set(reg._PARSER_SPECS)
    unknown = sorted(keys - known)
    assert not unknown, f"目录名必须是 parser_registry 的 key，未知：{unknown}"


def test_every_frame_parses():
    files = sorted(FRAMES_DIR.glob("*/*.hex"))
    assert len(files) >= MIN_TOTAL_FRAMES, f"语料太少（{len(files)} 帧）"
    failures = []
    for path in files:
        key = path.parent.name
        try:
            frame = load_frame(path)
        except ValueError as exc:
            failures.append(f"{path}: 不是合法 HEX（{exc}）")
            continue
        assert frame, f"{path}: 空帧"
        parser = reg.get_parser(key)
        try:
            result = parse_any(parser, frame)
        except Exception as exc:  # noqa: BLE001 - 语料必须全部能解析
            failures.append(f"{path}: {type(exc).__name__}: {exc}")
            continue
        if not result:
            failures.append(f"{path}: 解析结果为空")
    assert not failures, "以下语料回归：\n" + "\n".join(failures)


def test_corpus_frames_are_self_consistent():
    """同一帧解析两次结果一致（防随机/全局状态污染）。"""
    for path in sorted(FRAMES_DIR.glob("*/*.hex")):
        key = path.parent.name
        frame = load_frame(path)
        parser = reg.get_parser(key)
        first = parse_any(parser, frame)
        second = parse_any(parser, frame)
        assert first == second, f"{path}: 两次解析结果不一致"


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
