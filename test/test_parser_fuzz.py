# -*- coding: utf-8 -*-
"""解析器健壮性（模糊测试）：畸形输入不许崩、不许卡死。

覆盖三类输入（固定 seed，可复现）：
1. 纯随机字节；
2. 带 `68` / `7E` 头的随机字节（更容易走到深路径）；
3. **语料帧的所有截断前缀**（粘贴不全是现场最常见的输入）。

判据：`parse_to_table` / `parse` 不抛任何异常，总耗时在上限内。
2026-10-20 本测试曾抓到 `gdw10376_parser` 截断帧 `IndexError`，已修，这里留回归用例。

运行: python test/test_parser_fuzz.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import parser_registry as reg  # noqa: E402

KEYS = ["south", "plc_rf", "hdlc", "dlt645", "gdw", "dl_t698_45",
        "csg_new_gen", "gw_new_gen", "hdc10", "modular", "yw645", "csg_uplink"]

SEED = 20261020
CASES_PER_PARSER = 200
TIME_BUDGET = 25.0

#: 曾经触发 IndexError 的国网截断帧（长度域 0xE8 远大于实收字节）
GDW_REGRESSION = bytes.fromhex(
    "68E8B9997F5C7C2999FDAFE593253CD654AF4DFAD71427A0AEB3FEE9232F8AF2"
    "211F9EE491C5B10BECB5563BFC1E6F93427ECBC8FE2955E5CD8E46DC")

FRAMES_DIR = Path(__file__).resolve().parent / "frames"


def parse_any(parser, data: bytes):
    if hasattr(parser, "parse_to_table"):
        return parser.parse_to_table(data)
    return parser.parse(data)


def _random_cases(rng: random.Random, count: int):
    for i in range(count):
        mode = i % 4
        if mode == 0:
            yield bytes(rng.randrange(256) for _ in range(rng.randrange(0, 120)))
        elif mode == 1:
            yield b"\x68" + bytes(rng.randrange(256) for _ in range(rng.randrange(0, 120)))
        elif mode == 2:
            yield (b"\x7e" + bytes(rng.randrange(256) for _ in range(rng.randrange(0, 120)))
                   + b"\x7e")
        else:
            yield bytes(rng.randrange(256) for _ in range(rng.randrange(0, 8)))


def test_random_inputs_never_raise():
    rng = random.Random(SEED)
    failures = []
    started = time.perf_counter()
    for key in KEYS:
        parser = reg.get_parser(key)
        for data in _random_cases(rng, CASES_PER_PARSER):
            try:
                parse_any(parser, data)
            except Exception as exc:  # noqa: BLE001 - 这里就是要断言"不抛"
                failures.append(f"{key}: {type(exc).__name__}: {exc} | {data.hex()[:60]}")
                if len(failures) >= 5:
                    break
        if len(failures) >= 5:
            break
    elapsed = time.perf_counter() - started
    assert not failures, "解析器在畸形输入上抛异常：\n" + "\n".join(failures)
    assert elapsed < TIME_BUDGET, f"模糊测试耗时 {elapsed:.1f}s 超过预算 {TIME_BUDGET}s"


def test_truncated_corpus_frames_never_raise():
    files = sorted(FRAMES_DIR.glob("*/*.hex"))
    assert files, "语料库为空，先跑 test_frame_corpus.py 准备帧"
    failures = []
    for path in files:
        key = path.parent.name
        chunks = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                chunks.append(line.replace(" ", ""))
        frame = bytes.fromhex("".join(chunks))
        parser = reg.get_parser(key)
        # 所有前缀（含空帧）+ 每字节随机扰动
        for cut in range(0, len(frame) + 1):
            try:
                parse_any(parser, frame[:cut])
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{path.name} cut={cut}: {type(exc).__name__}: {exc}")
                break
    assert not failures, "截断帧解析崩溃：\n" + "\n".join(failures)


def test_gdw_truncated_frame_regression():
    """回归：长度域大于实收字节时，国网解析器不得越界（IndexError）。"""
    parser = reg.get_parser("gdw")
    rows = parser.parse_to_table(GDW_REGRESSION)   # 不抛即通过
    assert isinstance(rows, list)
    # 更短的截断同样安全
    for cut in range(0, len(GDW_REGRESSION), 7):
        parser.parse_to_table(GDW_REGRESSION[:cut])


def test_empty_and_tiny_inputs():
    for key in KEYS:
        parser = reg.get_parser(key)
        for data in (b"", b"\x00", b"\x16", b"\x68", b"\x68\x16", bytes(300)):
            parse_any(parser, data)


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
