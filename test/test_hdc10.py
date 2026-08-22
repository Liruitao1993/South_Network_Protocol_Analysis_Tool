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
    """0xC0 条目长度字段2字节; 实机声明35B偏小, 内容按锚点延伸到管理区末尾(BPCS前)"""
    rows = parse_rows()
    raw, val, _ = find(rows, "    条目4: 时隙分配条目")
    assert raw == "头=0xC0 长=35B", f"条目4 长度字段: {raw}"
    assert val == "内容66B", f"条目4 内容应延伸到BPCS前(66B), 实际: {val}"


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
    """时隙条目延伸到管理区末尾后, 声明条目之外不应再有剩余数据(17条信标时隙+3条CSMA全部消化)"""
    rows = parse_rows()
    names = [r[0] for r in rows]
    assert "    未解析剩余数据" not in names, "不应再有未解析剩余数据"
    assert "      未解析剩余" not in names, "时隙条目内不应有未解析剩余"
    # 17条信标时隙明细(2代理+15发现)
    slots = [n for n in names if n.startswith("      信标时隙") and n[-1].isdigit()]
    assert len(slots) == 17, f"信标时隙明细: {len(slots)}条"


# ====== 查询站点升级状态上行报文(表45): 升级位图解析 ======
UPGRADE_STATUS_UP = (
    "12 34 00 00 01 23 8A 04 00 00 00 00 B2 D6 D3 93 "
    + "FF " * 152 + "03"
)


def parse_upgrade_rows():
    data = bytes.fromhex(UPGRADE_STATUS_UP)
    return HDC10Parser().parse_to_table(data)


def test_upgrade_status_uplink_bitmap():
    """0x034 上行应答应解出 升级状态/有效块数/起始块号/升级ID/升级位图"""
    rows = parse_upgrade_rows()
    _, val, _ = find(rows, "    方向")
    assert val == "上行(STA→CCO)", f"方向: {val}"
    _, status, _ = find(rows, "    升级状态")
    assert status == "接收完成态", f"升级状态: {status}"
    _, blocks, _ = find(rows, "    有效块数")
    assert blocks == "1162", f"有效块数: {blocks}"
    _, uid, _ = find(rows, "    升级ID")
    assert uid == "2480133810", f"升级ID: {uid}"
    raw, recv, desc = find(rows, "    升级位图")
    # 位图153字节(1224bit >= 1162块), 全FF+末字节03 → 1162/1162 已接收
    assert recv == "1162/1162块已接收", f"位图统计: {recv}"
    assert "153字节" in desc, f"位图长度说明: {desc}"


def test_upgrade_status_downlink():
    """0x034 下行查询(表40, 恰12字节)仍按下行格式解析, 无位图行"""
    down = bytes([0x01, 0x03, 0xFF, 0xFF, 0, 0, 0, 0, 0x11, 0x22, 0x33, 0x44])
    rows = HDC10Parser()._parse_upgrade(down, 100, 0x034)
    names = [r[0] for r in rows]
    assert "    连续查询块数" in names, f"缺少下行字段: {names}"
    assert "    升级位图" not in names and "    升级状态" not in names
    for r in rows:
        if r[0] == "    连续查询块数":
            assert r[1] == "0xFFFF" and r[2] == "查询所有块状态"
        if r[0] == "    升级ID":
            assert r[1] == "0x44332211"


def test_upgrade_bitmap_lost_blocks():
    """丢包场景: bit=0 的块应标 [✕n], 统计与明细一致"""
    bm = bytearray([0xFF] * 146)
    bm[0] &= ~(1 << 5)     # 块5
    bm[12] &= ~(1 << 4)    # 块100
    bm[145] &= ~(1 << 0)   # 块1160
    payload = (bytes([0x01, 0x23]) + (1162).to_bytes(2, 'little')
               + (0).to_bytes(4, 'little') + (0x93D3D6B2).to_bytes(4, 'little')
               + bytes(bm))
    rows = HDC10Parser()._parse_upgrade(payload, 0, 0x034)
    _, recv, _ = find(rows, "    升级位图")
    assert recv == "1159/1162块已接收", f"统计: {recv}"
    detail = ''.join(r[2] for r in rows if r[0].startswith("      位图明细"))
    import re
    lost = re.findall(r"\[✕(\d+)\]", detail)
    assert lost == ["5", "100", "1160"], f"丢包编号: {lost}"
    assert "[✓0]" in detail and "[✓1161]" in detail


# ====== 台区户变关系识别(0x0A1) DATA 深度解析 ======

def test_phase_ident_header_len():
    """报文头长度6bit(byte0[6:7]+byte1[0:3])×4字节: 0x01,0x53 → 12字节头"""
    biz = bytes.fromhex('01537C8A1139702500220303' + '01' + '00' + '14' + '00000000' + '2A00' * 20)
    rows = HDC10Parser()._parse_phase_ident(biz, 0)
    hdr = [r for r in rows if r[0] == "  台区户变关系识别报文"][0]
    assert hdr[2] == "12字节头", f"头长: {hdr[2]}"
    data_row = [r for r in rows if r[0] == "    数据(DATA)"][0]
    assert data_row[2] == "47字节", f"DATA长度: {data_row[2]}"

def test_phase_ident_period_series():
    """采集类型3告知+特征类型3工频周期: TEI/方式/序号/总数/NTB1 + 三相周期值"""
    biz = bytes.fromhex('01537C8A1139702500220303'   # 头12B: 特征3 采集3
                        + '01000114'                  # TEI=1 方式=保留 序号1 总数20
                        + 'B0D6A192'                  # NTB1
                        + '2A002A002A002A002B00290029002B00'   # 第一出线10个
                        + '2A002A002A002A002B00290029002B002A00')  # 第二出线10个
    rows = HDC10Parser()._parse_phase_ident(biz, 0)
    _, tei, _ = find(rows, "      TEI")
    assert tei == "1", f"TEI: {tei}"
    _, total, _ = find(rows, "      告知总数量")
    assert total == "20", f"告知总数量: {total}"
    _, ntb, _ = find(rows, "      起始采集NTB1")
    assert ntb == "2460079792", f"NTB1: {ntb}"
    series = [r for r in rows if r[0].startswith("      特征序列")]
    assert len(series) == 1 and "工频周期偏差" in series[0][0]
    phases = [r for r in rows if r[0].startswith("        第")][0]
    assert "+42 (13.4μs)" in phases[2], f"周期值: {phases[2]}"


def test_phase_ident_voltage_bcd():
    """特征类型1工频电压: BCD XXX.X 大端解码 220.5V"""
    data = bytes.fromhex('0103000600000000') + bytes([0x00, 1, 1, 1]) \
        + bytes.fromhex('2205') + bytes.fromhex('2306') + bytes.fromhex('2407')
    rows = HDC10Parser()._parse_phase_ident_data(data, 100, 1, 3)
    vals = {r[0]: r[2] for r in rows if r[0].startswith("        第")}
    assert vals["        第一出线"] == "220.5V", vals
    assert vals["        第二出线"] == "230.6V"
    assert vals["        第三出线"] == "240.7V"


def test_phase_ident_freq_bcd():
    """特征类型2工频频率: BCD XX.XX 大端解码 50.00Hz"""
    data = bytes.fromhex('0103000400000000') + bytes([0x00, 2, 1, 1]) \
        + bytes.fromhex('5000') + bytes.fromhex('4999') + bytes.fromhex('5002')
    rows = HDC10Parser()._parse_phase_ident_data(data, 100, 2, 3)
    vals = {r[0]: r[2] for r in rows if r[0].startswith("        第")}
    assert vals["        第一出线"] == "50.00Hz 49.99Hz", vals
    assert vals["        第二出线"] == "50.02Hz"


def test_phase_ident_dual_edge():
    """双沿采集(方式3): NTB1+序列1(下降沿)+NTB2+序列2(上升沿)"""
    data = bytes([0x03, 0x30]) + bytes([0x00, 0x02]) + bytes([0, 0, 0, 0]) \
        + bytes([0x00, 1, 1, 0]) + bytes.fromhex('2A002B00') \
        + bytes([0, 0, 0, 0]) + bytes([0x00, 1, 1, 0]) + bytes.fromhex('2C002D00')
    rows = HDC10Parser()._parse_phase_ident_data(data, 100, 3, 3)
    _, method, _ = find(rows, "      采集方式")
    assert method == "双沿采集", method
    s1 = [r for r in rows if r[0] == "      特征序列1(工频周期偏差)"]
    s2 = [r for r in rows if r[0] == "      特征序列2(工频周期偏差)"]
    assert s1 and s2, "缺少双沿两组序列"
    _, ntb2, _ = find(rows, "      起始采集NTB2")
    assert ntb2 == "0"


def test_phase_ident_result():
    """采集类型5判别结果信息: TEI/结束标志/识别结果/CCO地址"""
    data = bytes([0x07, 0x00, 0x01, 0x02]) + bytes.fromhex('AABBCCDDEEFF')
    rows = HDC10Parser()._parse_phase_ident_data(data, 100, 0, 5)
    _, done, _ = find(rows, "      判别结束标志")
    assert done == "已结束", done
    _, result, _ = find(rows, "      台区识别结果")
    assert result == "不是本台区", result
    _, cco, _ = find(rows, "      正确隶属CCO地址")
    assert cco == "AA:BB:CC:DD:EE:FF", cco


def test_fccs_valid():
    """FC 帧头校验(FCCS)仍应正确"""
    rows = parse_rows()
    raw, val, desc = find(rows, "帧控制校验序列(FCCS)")
    assert val == "0x296D42", f"FCCS: {val}"
    assert "校验正确" in desc, f"FCCS状态: {desc}"


# ====== 时隙分配条目可变区(实机顺序) + 心跳检测(表94) + 发现列表(表95) ======
def test_slot_entry_var_region():
    """时隙条目可变区: CSMA先行 + 非中央信标信息到边界(17条全解无剩余)"""
    rows = parse_rows()
    names = [r[0] for r in rows]
    csma = [n for n in names if n == "      CSMA时隙信息"]
    assert len(csma) == 3, f"CSMA时隙: {len(csma)}条"
    slots = [r for r in rows if r[0].startswith("      信标时隙") and r[0].strip()[-1].isdigit()]
    assert len(slots) == 17, f"信标时隙明细: {len(slots)}条"
    assert "TEI=129 代理信标" in slots[0][2], f"首条: {slots[0][2]}"
    assert "载波+无线精简信标" in slots[1][3], f"第2条无线标志: {slots[1][3]}"
    assert "    未解析剩余数据" not in names


def test_heartbeat_table94():
    """心跳检测表94: OSTEI/最大站点TEI/数量/位图大小 + 位图TEI明细"""
    import struct
    from hdc10_mme_parser import _parse_heartbeat, parse_management_message
    bmp = bytearray(3)
    for t in (1, 8, 9, 20):
        bmp[t >> 3] |= (1 << (t & 7))
    hb = bytes([0x05, 0x00, 0x09, 0x00]) + struct.pack('<HH', 12, 3) + bytes(bmp)
    frame = struct.pack('<HB', 7, 0) + hb
    rows = parse_management_message(frame, 0)
    _, ostei, _ = find(rows, "    原始源TEI")
    assert ostei == "5", ostei
    _, max_tei, _ = find(rows, "    发现站点数最大站点TEI")
    assert max_tei == "9", max_tei
    detail = [r for r in rows if r[0].startswith("      位图明细")]
    assert detail and "[✓1]" in detail[0][2] and "[✓20]" in detail[0][2]


def test_discovery_list_table95():
    """发现列表表95: 固定头32B + 路由条目 + 位图 + 接收计数与位图配对"""
    import struct
    from hdc10_mme_parser import parse_management_message
    d = bytearray(32)
    d[0] = 5; d[1] = 0x10            # TEI=5, 代理TEI=1
    d[3] = 2 | (1 << 4)              # 角色2 层级1
    d[16] = 0 | (1 << 2) | (2 << 4)  # 相线 A/B/C
    d[17] = 30; d[18] = 95; d[19] = 90
    struct.pack_into('<H', d, 20, 2)
    d[22] = 3; d[23] = 1             # 发送个数3, 路由条目1
    struct.pack_into('<H', d, 24, 100)
    struct.pack_into('<H', d, 26, 2)
    d[28] = 95
    bmp = bytearray(2); bmp[1] = 0x03   # TEI 8, 9
    dl = bytes(d) + bytes([0x03, 0x30]) + bytes(bmp) + bytes([4, 6])
    rows = parse_management_message(struct.pack('<HB', 8, 0) + dl, 0)
    _, tei, _ = find(rows, "    TEI")
    assert tei == "5", tei
    _, ptei, _ = find(rows, "    代理TEI")
    assert ptei == "1", ptei
    route = [r for r in rows if r[0] == "    上行路由1"][0]
    assert "下一跳TEI=3" in route[2] and "代理主路径" in route[3]
    recv = [r for r in rows if r[0] == "    接收发现列表信息"][0]
    assert "[TEI8←4]" in recv[2] and "[TEI9←6]" in recv[2], recv[2]


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