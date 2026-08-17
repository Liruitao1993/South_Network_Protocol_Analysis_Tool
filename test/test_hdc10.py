# -*- coding: utf-8 -*-
"""HDC 1.0 (协议索引11) 时隙分配条目解析测试

覆盖:
- 信标管理信息条目长度字段: 0xC0 条目长度字段2字节, 内容 = total_len - 3 (头1B+长度2B开销)
  修复前代码用 total_len - 2 导致多算1字节(0x81 混入条目4内容, 可变部分显示13字节无法分解)
- 时隙分配条目(0xC0)可变部分解析: 
  发现信标省略非中央信标信息(表50), 可变部分 = CSMA时隙信息(4B/条)
  + 绑定CSMA时隙信息(4B/条)
- BPCS(4B, CRC-32) + PBCS(3B, CRC-24) 帧尾位置与校验范围
"""


import _path_setup  # noqa: E402

import sys

from hdc10_parser import HDC10Parser

# 用户实际帧: 142字节 HDC 1.0 发现信标 (FC 16B + 信标载荷 126B)
USER_FRAME = (
    "00 3A CF 9E E0 A8 12 69 A7 A0 BE 06 00 42 6D 29 "
    "C8 42 00 01 02 21 45 19 53 2D 01 00 B7 03 00 00 00 00 00 00 "
    "04 00 0F A7 A0 01 5E 01 01 59 51 94 88 21 00 03 01 0A "
    "F0 00 3C 00 14 00 18 00 03 04 78 05 "
    "C0 23 00 19 33 00 09 1E 32 00 00 00 00 80 A4 66 68 10 27 00 00 2E 00 "
    "ED 0B 00 01 ED 0B 00 02 EE 0B 00 03 "
    "81 10 A7 70 4B 00 1F 00 53 00 51 00 4C 00 38 00 79 00 8E 00 "
    "A0 00 78 00 70 00 3A 00 6E 00 89 00 9A 00 88 00 "
    "F7 0B 00 01 F7"
)


def parse_rows():
    data = bytes.fromhex(USER_FRAME.replace(" ", ""))
    return HDC10Parser().parse_to_table(data, parse_level="auto")


def find(rows, name):
    """按行名查找, 返回 (原始值, 解析值, 说明)"""
    for r in rows:
        if r[0] == name:
            return r[1], r[2], r[3]
    raise AssertionError(f"未找到行: {name}")


def test_entry4_content_length():
    """0xC0 条目长度字段2字节, 内容 = total_len - 3 = 32B (修复 total_len-2 bug)"""
    rows = parse_rows()
    raw, val, _ = find(rows, "    条目4: 时隙分配条目")
    assert raw == "头=0xC0 长=35B", f"条目4 长度字段: {raw}"
    assert val == "内容32B", f"条目4 内容应为32B (35-3), 实际: {val}"


def test_fixed_header_fields():
    """时隙分配条目固定头字段解析"""
    rows = parse_rows()
    _, v25, _ = find(rows, "      非中央信标时隙总数")
    assert v25 == "25", f"非中央信标时隙总数: {v25}"
    _, v3, _ = find(rows, "      中央信标时隙总数")
    assert v3 == "3", f"中央信标时隙总数: {v3}"
    _, v9, _ = find(rows, "      代理信标时隙总数")
    assert v9 == "9", f"代理信标时隙总数: {v9}"
    _, v30, _ = find(rows, "      信标时隙长度")
    assert v30 == "30ms", f"信标时隙长度: {v30}"
    _, v46, _ = find(rows, "      RF信标时隙长度")
    assert v46 == "46", f"RF信标时隙长度: {v46}"


def test_csma_slot_info_parsed():
    """发现信标省略非中央信标信息(表50), 可变部分 = 3条CSMA时隙信息(CSHA相线=3)"""
    rows = parse_rows()
    csma = [r for r in rows if r[0] == "      CSMA时隙信息"]
    assert len(csma) == 3, f"应解析3条CSMA时隙信息, 实际: {len(csma)}"
    # 3条: 长度3053/3053/3054ms, 相线 A/B/C (byte3 = 01/02/03)
    lens = [r[2] for r in csma]
    assert lens[0] == "长度=3053ms 相线=A相线", f"CSMA[0]: {lens[0]}"
    assert lens[1] == "长度=3053ms 相线=B相线", f"CSMA[1]: {lens[1]}"
    assert lens[2] == "长度=3054ms 相线=C相线", f"CSMA[2]: {lens[2]}"


def test_discovery_beacon_skips_non_ccn():
    """发现信标(类型0)省略非中央信标信息字段, 不解析 TEI 条目"""
    rows = parse_rows()
    non_ccn = [r for r in rows if r[0].startswith("      非中央信标信息") and "总数" not in r[0]]
    assert len(non_ccn) == 0, f"发现信标不应解析非中央信标信息条目, 实际: {len(non_ccn)}"


def test_bpcs_pbcs_position():
    """BPCS(4B, CRC-32) + PBCS(3B, CRC-24) 位于帧尾"""
    rows = parse_rows()
    r = find(rows, "  帧载荷校验序列(BPCS)")
    assert r[0] == "88 00 F7 0B", f"BPCS值: {r[0]}"
    r2 = find(rows, "  物理块校验序列(PBCS)")
    assert r2[0] == "00 01 F7", f"PBCS值: {r2[0]}"
    # BPCS 偏移 135-138, PBCS 偏移 139-141
    for row in rows:
        if row[0] == "  帧载荷校验序列(BPCS)":
            assert row[4] == 135 and row[5] == 138, f"BPCS偏移: {row[4]}-{row[5]}"
        if row[0] == "  物理块校验序列(PBCS)":
            assert row[4] == 139 and row[5] == 141, f"PBCS偏移: {row[4]}-{row[5]}"


def test_remaining_data_shown():
    """条目数声明之外的剩余数据应透明显示, 不静默丢弃"""
    rows = parse_rows()
    raw, val, _ = find(rows, "    未解析剩余数据")
    assert val == "34字节", f"剩余数据: {val}"


def test_fccs_valid():
    """FC 帧头校验(FCCS)仍应正确"""
    rows = parse_rows()
    raw, val, desc = find(rows, "帧控制校验序列(FCCS)")
    assert val == "0x296D42", f"FCCS: {val}"
    assert "校验正确" in desc, f"FCCS状态: {desc}"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())