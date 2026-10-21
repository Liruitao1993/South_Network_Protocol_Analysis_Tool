# -*- coding: utf-8 -*-
"""698.45 容错解析回归（勾掉「校验该帧」时的行为）。

真实场景：现场抓到半截帧（长度域声明 534 字节、实收 256 字节），旧逻辑直接报
「❌ 解析失败」不做任何拆解；容错模式要求按实收字节继续拆，拆不动的原样输出。

运行: python test/test_dl698_tolerant_parse.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import parser_registry as reg  # noqa: E402

PARSER = reg.get_parser("dl_t698_45")

#: 用户现场的半截帧（长度域 L=532，整帧应为 534，实收 256）
PARTIAL_HEX = (
    "6814024305111111111111109790070100F00108000202120000098201F4F85D0920693300085DED0008AD340008E5E90008"
    "E5810008F1250108000000000000000000000000000000008D010108B993000800000000FB33000829120108953300089533"
    "000895330008BDF60008953300089533000825CC0008B9CC0008D1CC0008DDCC0008E9CC0008AD8D0008B98D0008C58D0008"
    "D18D0008DD8D0008E98D0008F58D00089533000895330008F98100080000000000000000F5CC000895330008953300089533"
    "00089533000831160108591601088D160108953300089533000895330008953300089533000895330008B11F0108BD1F0108"
    "C91F010831CC"
)
PARTIAL = bytes.fromhex(PARTIAL_HEX)

#: 完整合法帧（L=23，整帧 25 字节，HCS/FCS 均通过）
VALID = bytes.fromhex("6817004305AAAAAAAAAAAA00AA2A05010143000300006D5C16")


def _names(rows):
    return [str(row[0]) for row in rows]


def test_strict_mode_still_fails_on_partial():
    rows = PARSER.parse_to_table(PARTIAL)
    assert rows, "严格模式也要给出行"
    assert rows[0][0].startswith("❌"), rows[0][0]
    assert "解析失败" in rows[0][0]


def test_tolerant_mode_parses_header_to_last_byte():
    rows = PARSER.parse_to_table(PARTIAL, verify=False)
    names = _names(rows)
    assert not any(n.startswith("❌") for n in names), names
    for expected in ("起始字符", "长度域", "控制域", "地址特征", "服务器地址SA",
                     "客户机地址CA", "原始报文"):
        assert expected in names, expected
    # 必须明确给出「按实收字节继续」的原因
    notes = [row[3] for row in rows if row[0] == "⚠ 容错提示"]
    assert any("实收 256" in str(n) for n in notes), notes
    # 原始报文行给出完整长度
    raw_row = next(row for row in rows if row[0] == "原始报文")
    assert raw_row[2] == f"{len(PARTIAL)}字节", raw_row[2]


def test_tolerant_handles_every_prefix():
    for cut in range(len(PARTIAL) + 1):
        rows = PARSER.parse_to_table(PARTIAL[:cut], verify=False)
        assert rows, f"cut={cut} 无任何行"
        assert "原始报文" in _names(rows), f"cut={cut} 缺少原始报文行"


def test_tolerant_valid_frame_has_no_warning():
    rows = PARSER.parse_to_table(VALID, verify=False)
    names = _names(rows)
    assert "⚠ 容错提示" not in names, [r for r in rows if r[0] == "⚠ 容错提示"]
    assert "原始报文" in names
    hcs = next(row for row in rows if row[0] == "帧头校验HCS")
    fcs = next(row for row in rows if row[0] == "帧校验FCS")
    assert hcs[2] == "0x2AAA" and hcs[3] == "通过", hcs
    assert fcs[3] == "通过", fcs


def test_tolerant_missing_end_char_is_reported_not_fatal():
    rows = PARSER.parse_to_table(VALID[:-1], verify=False)   # 去掉 0x16
    names = _names(rows)
    assert "结束符" in names
    end = next(row for row in rows if row[0] == "结束符")
    assert ("未找到" in str(end[3]) or "0x16" in str(end[3])), end
    assert "原始报文" in names


def test_tolerant_bad_fcs_continues():
    broken = bytearray(VALID)
    broken[-3] ^= 0xFF          # 破坏 FCS 低字节
    rows = PARSER.parse_to_table(bytes(broken), verify=False)
    fcs = next(row for row in rows if row[0] == "帧校验FCS")
    assert "失败" in str(fcs[3]), fcs
    assert "原始报文" in _names(rows)
    assert "链路用户数据" in _names(rows)


def test_tolerant_tiny_inputs_do_not_raise():
    for data in (b"", b"\x68", b"\x68\x00", b"\x68\x01\x00", b"\x00\x01\x02"):
        rows = PARSER.parse_to_table(data, verify=False)
        assert rows
        assert "原始报文" in _names(rows)


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
