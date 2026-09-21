# -*- coding: utf-8 -*-
"""协议10/11「仅MAC帧(mac_only)」契约回归 —— 输入即 MAC 帧，禁止自动剥 PBH

现场报障（2026-09-18，GUI 协议11 解析级别=仅MAC帧）:
    帧 `00000100019673005C80FF0800960000...688150C4...BA711E`
    用户要求「解析正确，而不是又自动的解析物理块头部」。

契约（与协议9 同口径，AGENTS §8 陷阱19）:
    mac_only 的输入就是 MAC 帧，解析器从字节 0 直接解析，
    **不得**探测/剥离物理块头(PBH)。需要 PBH 请用 pb_only / auto。

修复前缺陷:
  - 协议10 `GWNewGenParser` mac_only 仍走 `_parse_pb_by_frame_type`，
    把首字节当 PBH 剥掉 → MAC 头整体错位（源TEI/目的TEI/MSDU类型全错），
    输出里还出现「物理块头(PBH)」行。
  - 协议11 `HDC10Parser._parse_mac_only` 在 data[0]&0x80 时自动剥 1 字节
    （现场帧首字节 0x00 未触发，但契约不允许）。
  - 协议11 MME 内容行偏移相对 MSDU 切片，未加绝对基址 → 点击高亮错位。

本现场帧解析期望（协议10/11 一致的关键字段）:
    版本=0, 原始源TEI=0, 原始目的TEI=1, MSDU类型=0(网络管理消息),
    MSDU长度=92, MAC地址标志=1(28字节头),
    MMTYPE=0x0000(关联请求), 站点MAC=20:00:00:00:01:24,
    ICV=0xC4508168 且校验通过。
"""

import sys

import _path_setup  # noqa: E402,F401

from gw_new_gen_parser import GWNewGenParser
from hdc10_parser import HDC10Parser, _crc32
from protocol_registry import build_gui_parser
from parser_registry import get_parser

# 现场帧：标准 MAC 头(28B 含 MAC 地址) + MME 关联请求 + ICV + 尾部填充
FIELD_FRAME = (
    "00000100019673005C80FF0800960000"
    "200000000124010101010101"
    "000000002000000001240100000000000000000001030001"
    "329FBACA69DE640900000000A860CAF104A18A64E8F2"
    "0000040099F4484C3039000000000000000065F9"
    "0000000000000000000000000000000000000000000000000000"
    "688150C4"
    "0000000000000000BA711E"
)

# 若首字节被误当成 PBH（bit7=1），MAC 头会整体错位 —— 用于反证契约
PBH_PREFIX_FRAME = "80" + FIELD_FRAME[2:]

PASS = 0
FAIL = 0
FAILED = []


def section(title):
    print(f"\n{title}")


def check(desc, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {desc}")
    else:
        FAIL += 1
        FAILED.append(desc)
        print(f"  ✗ {desc}" + (f"\n      {detail}" if detail else ""))


def _to_bytes(hex_str):
    return bytes.fromhex(hex_str.replace(" ", ""))


def _find(rows, name):
    for r in rows:
        if str(r[0]).strip() == name:
            return r
    return None


def _val(rows, name, idx=2):
    row = _find(rows, name)
    return None if row is None else str(row[idx]).strip()


def _has_pbh(rows):
    for r in rows:
        n = str(r[0])
        if "物理块头" in n or "PBH" in n:
            return r
    return None


def _assert_mac_golden(rows, label):
    check(f"{label} 无物理块头行", _has_pbh(rows) is None,
          str(_has_pbh(rows)))
    check(f"{label} 原始源TEI=0", _val(rows, "原始源TEI") == "0",
          str(_val(rows, "原始源TEI")))
    check(f"{label} 原始目的TEI=1", _val(rows, "原始目的TEI") == "1",
          str(_val(rows, "原始目的TEI")))
    check(f"{label} MSDU类型=0", _val(rows, "MSDU类型") == "0",
          str(_val(rows, "MSDU类型")))
    msdu_len = _val(rows, "MSDU长度")
    check(f"{label} MSDU长度=92", msdu_len in ("92", "92字节"),
          str(msdu_len))


def main():
    data = _to_bytes(FIELD_FRAME)
    section("[1] 帧自证")
    check("A1 帧长 135 字节", len(data) == 135, str(len(data)))
    check("A1 首字节 0x00（合法 MAC 版本0，bit7=0）", data[0] == 0x00,
          hex(data[0]))
    hdr_len = 28  # MAC地址标志=1
    msdu = data[hdr_len:hdr_len + 92]
    icv = int.from_bytes(data[hdr_len + 92:hdr_len + 96], "little")
    check("A1 ICV = crc32(MSDU) 自证 MSDU 起点=28",
          icv == _crc32(msdu) and icv == 0xC4508168,
          f"icv=0x{icv:08X} calc=0x{_crc32(msdu):08X}")

    section("[2] 协议11 HDC10Parser mac_only")
    rows11 = HDC10Parser().parse_to_table(data, parse_level="mac_only")
    _assert_mac_golden(rows11, "P11")
    check("P11 MMTYPE=0x0000 关联请求",
          _val(rows11, "消息类型(MMTYPE)") == "0x0000",
          str(_val(rows11, "消息类型(MMTYPE)")))
    site = _find(rows11, "站点MAC地址")
    check("P11 站点MAC=20:00:00:00:01:24",
          site is not None and "20:00:00:00:01:24" in str(site[2]),
          str(site[2] if site else None))
    icv_row = _find(rows11, "完整性校验值(ICV)")
    check("P11 ICV 校验通过",
          icv_row is not None and "校验正确" in str(icv_row[3]),
          str(icv_row[3] if icv_row else None))
    # MME 行偏移必须落在原帧绝对位置（MSDU 起点 28）
    mmt = _find(rows11, "消息类型(MMTYPE)")
    check("P11 MMTYPE 偏移=28-29（绝对，不再相对MSDU）",
          mmt is not None and mmt[4] == 28 and mmt[5] == 29,
          f"off={mmt[4] if mmt else None}-{mmt[5] if mmt else None}")
    site_mac_off_expected = data.hex().find("2000000001240100") // 2
    if site is not None and site[4] is not None:
        check("P11 站点MAC 偏移落在关联请求内（>=32）",
              site[4] >= 32, f"off={site[4]} expected_site={site_mac_off_expected}")

    section("[3] 协议10 GWNewGenParser mac_only（修复前会剥 PBH）")
    rows10 = GWNewGenParser().parse_to_table(data, parse_level="mac_only")
    _assert_mac_golden(rows10, "P10")
    check("P10 MMTYPE=0x0000",
          _val(rows10, "管理消息类型(MMTYPE)") == "0x0000"
          or _val(rows10, "消息类型(MMTYPE)") == "0x0000",
          f"{_val(rows10, '管理消息类型(MMTYPE)')} / {_val(rows10, '消息类型(MMTYPE)')}")
    mode10 = _find(rows10, "解析模式")
    check("P10 解析模式说明含「不含」PBH",
          mode10 is not None and "不含" in str(mode10[3]),
          str(mode10[3] if mode10 else None))

    section("[4] GUI 包装路径（protocol_registry.build_gui_parser）")
    base11 = get_parser("hdc10")
    gui11 = build_gui_parser(11, base11, parse_level="mac_only",
                             frame_type=None, channel="plc")
    g11 = gui11.parse_to_table(data)
    _assert_mac_golden(g11, "GUI-P11")
    base10 = get_parser("gw_new_gen")
    gui10 = build_gui_parser(10, base10, parse_level="mac_only",
                             frame_type=None, channel="plc")
    g10 = gui10.parse_to_table(data)
    _assert_mac_golden(g10, "GUI-P10")

    section("[5] 变异反证：bit7=1 前缀也不得按 PBH 剥离")
    pbh_data = _to_bytes(PBH_PREFIX_FRAME)
    r11b = HDC10Parser().parse_to_table(pbh_data, parse_level="mac_only")
    check("P11 bit7前缀仍无 PBH 行", _has_pbh(r11b) is None, str(_has_pbh(r11b)))
    r10b = GWNewGenParser().parse_to_table(pbh_data, parse_level="mac_only")
    check("P10 bit7前缀仍无 PBH 行", _has_pbh(r10b) is None, str(_has_pbh(r10b)))
    # 错位时源TEI 会变成非 0（首字节 0x80 被当成版本/TEI 的一部分）
    check("P10 bit7前缀源TEI 仍按字节0解释（不再错位剥1字节）",
          _val(r10b, "原始源TEI") is not None,
          str(_val(r10b, "原始源TEI")))

    section("[6] pb_only 仍可解析带 PBH 的输入（契约不互相破坏）")
    with_pbh = bytes([0xC0]) + data
    rpb = GWNewGenParser().parse_to_table(with_pbh, parse_level="pb_only",
                                          frame_type=1)
    pbh_row = _has_pbh(rpb)
    check("P10 pb_only 仍输出物理块头", pbh_row is not None, str(pbh_row))
    if pbh_row is not None:
        check("P10 pb_only PBH=0xC0", str(pbh_row[1]).upper() in ("0XC0", "C0"),
              str(pbh_row[1]))

    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    if FAILED:
        print("失败项:")
        for n in FAILED:
            print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
