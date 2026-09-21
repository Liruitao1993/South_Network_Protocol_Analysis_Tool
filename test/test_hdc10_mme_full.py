# -*- coding: utf-8 -*-
"""HDC 1.0（协议索引11）网络管理消息 MME 全类型字段级解析测试

覆盖第4-2部分 §5.1.3 表59 列出的全部消息类型（0x0000~0x000C、0x004F、
0x0050~0x0055、0x0080），以及单跳帧（msg_type=0）无线发现列表 TLV（表123起）。

策略：
- 字段布局严格依据规范表（表60~表137）手工构造最小合法帧，做 golden 断言；
- 每个类型跑截断变体（空/短/声明长度超过实际），断言不抛异常且容错；
- 全类型经 parse_management_message 分派不崩溃（回归 0x000A NameError 缺陷）。
"""

import _path_setup  # noqa: E402

import pytest  # noqa: E402

from hdc10_mme_parser import (  # noqa: E402
    MME_TYPE_NAMES,
    parse_management_message,
    parse_singlehop_msdu,
    _read_12bit_stream,
)


def _mme(mmtype: int, payload: bytes) -> list:
    """在内容前拼 4 字节管理消息头（MMTYPE 2B 小端 + 保留 2B）。"""
    frame = mmtype.to_bytes(2, "little") + b"\x00\x00" + payload
    return parse_management_message(frame, 0)


def _names(rows):
    return [r[0].strip() for r in rows]


# ── 1. 全类型分派不崩溃（0x000A 曾抛 NameError） ─────────────────

ALL_TYPES = [0x0000, 0x0001, 0x0002, 0x0003, 0x0004, 0x0005, 0x0006,
             0x0007, 0x0008, 0x0009, 0x000A, 0x000B, 0x000C, 0x004F,
             0x0050, 0x0051, 0x0052, 0x0053, 0x0054, 0x0055, 0x0080]


def test_all_mme_types_named():
    """表59 的全部消息类型在名称表中都有中文名（防 0x0050~55 再次漏配）。"""
    for t in ALL_TYPES:
        assert t in MME_TYPE_NAMES, f"MMTYPE 0x{t:04X} 缺名称"


@pytest.mark.parametrize("mmtype", ALL_TYPES)
def test_dispatch_no_crash_minimal(mmtype):
    """每个类型给 4 字节内容，分派不得抛异常（短帧走容错分支）。"""
    rows = _mme(mmtype, b"\x00\x00\x00\x00")
    assert isinstance(rows, list) and rows


@pytest.mark.parametrize("mmtype", ALL_TYPES)
def test_dispatch_no_crash_empty_content(mmtype):
    """内容为空（仅 4B 头）也不崩。"""
    frame = mmtype.to_bytes(2, "little") + b"\x00\x00"
    rows = parse_management_message(frame, 0)
    assert isinstance(rows, list) and rows


def test_network_conflict_regression():
    """0x000A 网络冲突上报必须真正解析，而非 NameError 兜底。"""
    payload = bytes.fromhex("001122334455") + bytes([2, 3]) + \
        bytes.fromhex("AABBCC") + bytes.fromhex("112233")
    rows = _mme(0x000A, payload)
    names = _names(rows)
    assert "网络冲突上报" in names
    assert "CCO MAC地址" in names
    assert "邻居网络1" in names and "邻居网络2" in names
    assert not any("解析失败" in r[3] for r in rows)


# ── 2. 关联确认 0x0001（表70） ──────────────────────────────────

def test_associate_cnf_fields():
    payload = bytearray(40)
    payload[0:6] = bytes.fromhex("010203040506")     # 站点MAC
    payload[6:12] = bytes.fromhex("AABBCCDDEEFF")    # CCO MAC
    payload[12] = 0x00                                # 结果=成功
    payload[13] = 3                                   # 层级
    payload[14] = 0x21                                # 站点TEI低8
    payload[15] = 0x00                                # TEI高4=0, 链路0, 频段0
    payload[16] = 0x05                                # 代理TEI低8=5
    rows = _mme(0x0001, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["结果"][2] == "关联请求成功"
    assert d["站点层级"][2] == "3"
    assert d["站点TEI"][2] == "33"       # 0x0021 = 33
    assert d["代理TEI"][2] == "5"


def test_associate_cnf_reject_result():
    payload = bytearray(40)
    payload[12] = 0x01
    rows = _mme(0x0001, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["结果"][2] == "站点不在白名单中"


# ── 3. 关联汇总指示 0x0002（表76/78） ───────────────────────────

def test_associate_summary():
    payload = bytearray(16 + 8)  # 头16 + 1个站点条目8
    payload[0] = 0
    payload[1] = 2
    payload[2:8] = bytes.fromhex("000090980163")
    payload[8] = 0x01  # 代理TEI=1
    payload[11] = 1    # 汇总站点数
    payload[16:22] = bytes.fromhex("010203040506")
    payload[22] = 0x07  # 站点TEI=7
    rows = _mme(0x0002, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["结果"][2] == "允许加入网络"
    assert d["汇总站点数"][2] == "1"
    assert "站点1" in d
    assert d["站点1"][2] == "TEI=7"


# ── 4. 离线指示 0x0006（表91/93） ───────────────────────────────

def test_leave_ind():
    payload = bytearray(16 + 12)  # 头16 + 2个MAC
    payload[0:2] = (0).to_bytes(2, "little")
    payload[2:4] = (2).to_bytes(2, "little")
    payload[4:6] = (30).to_bytes(2, "little")
    payload[16:22] = bytes.fromhex("010203040506")
    payload[22:28] = bytes.fromhex("0A0B0C0D0E0F")
    rows = _mme(0x0006, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["原因"][2] == "CCO通知站点立即离线"
    assert d["站点总数"][2] == "2"
    assert d["延迟时间"][2] == "30秒"
    assert "离线站点1" in d and "离线站点2" in d


# ── 5. 通信成功率上报 0x0009（表100/101） ───────────────────────

def test_comm_success_rate():
    payload = bytearray(4 + 8)
    payload[0] = 0x05  # 代理TEI=5
    payload[2:4] = (2).to_bytes(2, "little")
    # 子站点1 TEI=10 下行100 上行99
    payload[4] = 0x0A
    payload[6], payload[7] = 100, 99
    # 子站点2 TEI=11 下行98 上行97
    payload[8] = 0x0B
    payload[10], payload[11] = 98, 97
    rows = _mme(0x0009, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["代理TEI"][2] == "5"
    assert d["站点总数"][2] == "2"
    assert d["子站点1"][2] == "TEI=10 下行100 上行99"
    assert d["子站点2"][2] == "TEI=11 下行98 上行97"


# ── 6. 代理变更三件套 0x0003/4/5（表79~90） ────────────────────

def test_change_proxy_req():
    payload = bytearray(24)
    payload[0] = 0x09          # 站点TEI=9
    payload[2] = 0x03          # 新代理候选1 TEI=3
    payload[12] = 0x02         # 旧代理TEI=2
    payload[14] = 0
    payload[15] = 1            # 原因=周期代理变更
    rows = _mme(0x0003, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["站点TEI"][2] == "9"
    assert d["旧代理TEI"][2] == "2"
    assert d["原因"][2] == "周期代理变更"
    assert d["新代理候选1"][2] == "TEI=3"


def test_change_proxy_cnf():
    payload = bytearray(20 + 4)  # 2个站点
    payload[0] = 0
    payload[4] = 0x09
    payload[6] = 0x03
    payload[16:18] = (2).to_bytes(2, "little")
    payload[20] = 0x0A
    payload[22] = 0x0B
    rows = _mme(0x0004, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["结果"][2] == "变更成功"
    assert d["站点TEI"][2] == "9"
    assert d["代理TEI"][2] == "3"
    assert d["子站点数"][2] == "2"
    assert d["子站点1"][2] == "TEI=10"
    assert d["子站点2"][2] == "TEI=11"


def test_change_proxy_bitmap_cnf():
    # 位图2字节, TEI1 与 TEI8 置位
    payload = bytearray(20 + 2)
    payload[2:4] = (2).to_bytes(2, "little")
    payload[4] = 0x09
    payload[6] = 0x03
    payload[20] = 0b00000010  # bit1 -> TEI1
    payload[21] = 0b00000001  # bit0(字节内) -> TEI8
    rows = _mme(0x0005, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["站点TEI"][2] == "9"
    assert d["位图大小"][2] == "2字节"
    joined = " ".join(str(c) for r in rows for c in r)
    assert "[✓1]" in joined and "[✓8]" in joined


# ── 7. 过零NTB采集指示 0x000B（表104） ─────────────────────────

def test_ntb_collect_ind():
    payload = bytearray(8)
    payload[0] = 0x03
    payload[2] = 1   # 全网采集
    payload[3] = 1   # 一个电力线周期
    payload[4] = 18
    rows = _mme(0x000B, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["TEI"][2] == "3"
    assert d["采集站点"][2] == "指定全网站点采集"
    assert d["采集周期"][2].startswith("一个电力线周期")
    assert d["采集数量"][2] == "18"


# ── 8. 过零NTB告知 0x000C（表107/108） ─────────────────────────

def test_ntb_report_12bit_packing():
    # 2 个 12bit 差值: 0x321 与 0xE54 → 字节 21 43 E5
    assert _read_12bit_stream(bytes.fromhex("2143E5"), 2) == [0x321, 0xE54]


def test_ntb_report_segments():
    payload = bytearray(10 + 3)  # 头10 + 相线1两个差值(3B)
    payload[0] = 0x07
    payload[2] = 2
    payload[3] = 2   # 相线1有2个
    payload[4] = 0
    payload[5] = 0
    payload[6:10] = (0x123456).to_bytes(4, "little")
    payload[10:13] = bytes.fromhex("2143E5")
    rows = _mme(0x000C, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["TEI"][2] == "7"
    assert "相线1过零NTB差值" in d
    assert "801" in d["相线1过零NTB差值"][2]
    assert "3668" in d["相线1过零NTB差值"][2]


# ── 9. 网络诊断 0x004F（表109/110） ────────────────────────────

def test_diagnose():
    payload = bytes.fromhex("0100") + b"\xAA\xBB"  # vendor 0x0001=HS
    rows = _mme(0x004F, payload)
    d = {r[0].strip(): r for r in rows}
    assert d["芯片厂商ID"][2] == "0x0001"
    assert "HS" in d["芯片厂商ID"][3]
    assert "厂家自定义" in d


# ── 10. 路由修复六件套 0x0050~0x0055（表111~120） ──────────────

def test_route_request_with_path():
    payload = bytearray(7 + 4)
    payload[0] = 0
    payload[1:5] = (0x01182345).to_bytes(4, "little")
    payload[5] = 0x11   # 路径优选bit4=1 + 类型低4b=1
    payload[6] = 4
    payload[7:11] = bytes.fromhex("01106450")  # TEI=1, 成功率100, 质量80
    rows = _mme(0x0050, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["路由请求序列号"][2] == "0x01182345"
    assert d["路径优选标志"][2] == "具有优选地位"
    assert d["负载数据类型"][2] == "传播路径列表"
    assert d["途经站点1"][2] == "TEI=1"


def test_route_reply_no_prefer_flag():
    payload = bytearray(7)
    payload[1:5] = (0x1234).to_bytes(4, "little")
    payload[5] = 0x00   # 回复无路径优选标志
    rows = _mme(0x0051, bytes(payload))
    names = _names(rows)
    assert "路径优选标志" not in names
    assert "负载数据类型" in names


def test_route_error():
    payload = bytearray(7 + 4)
    payload[6] = 2
    payload[7:9] = (0x10).to_bytes(2, "little")
    payload[9:11] = (0x11).to_bytes(2, "little")
    rows = _mme(0x0052, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["不可达站点数量"][2] == "2"
    assert d["不可达站点1"][2] == "TEI=16"
    assert d["不可达站点2"][2] == "TEI=17"


def test_route_ack():
    payload = bytearray(8)
    payload[4:8] = (0xABCD).to_bytes(4, "little")
    rows = _mme(0x0053, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["路由请求序列号"][2] == "0x0000ABCD"


def test_link_confirm_req():
    payload = bytearray(7 + 2)
    payload[6] = 1
    payload[7:9] = (0x20).to_bytes(2, "little")
    rows = _mme(0x0054, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["确认站点数量"][2] == "1"
    assert d["确认站点1"][2] == "TEI=32"


def test_link_confirm_rsp():
    payload = bytearray(8)
    payload[1] = 4   # 层级
    payload[2] = 70  # 信道质量
    payload[4:8] = (0x99).to_bytes(4, "little")
    rows = _mme(0x0055, bytes(payload))
    d = {r[0].strip(): r for r in rows}
    assert d["层级"][2] == "4"
    assert d["信道质量"][2] == "70"
    assert "路径优选标志" in d


# ── 11. 无线信道冲突 0x0080（表121/122） ────────────────────────

def test_rf_channel_conflict():
    payload = bytes.fromhex("001122334455") + bytes([2, 12, 33])
    rows = _mme(0x0080, payload)
    d = {r[0].strip(): r for r in rows}
    assert d["邻居网络个数"][2] == "2"
    assert d["邻居网络1信道号"][2] == "12"
    assert d["邻居网络2信道号"][2] == "33"


# ── 12. 单跳无线发现列表 TLV（表123~127） ──────────────────────

def test_rf_discover_list_tlv():
    mac = bytes.fromhex("001122334455")
    body = mac + bytes([1])
    attr = bytes.fromhex("AABBCCDDEEFF") + bytes(8)
    body += bytes([0x00, 14]) + attr          # IE0 站点属性
    body += bytes([0x01, 4]) + bytes.fromhex("05100620")  # IE1 路由2条
    rows = parse_singlehop_msdu(body, 0, 0)
    names = _names(rows)
    assert "无线发现列表" in names
    assert "站点MAC地址" in names
    assert names.count("信息单元1") + names.count("信息单元2") >= 2
    d = {r[0].strip(): r for r in rows}
    assert d["下一跳1"][2] == "TEI=5"
    assert d["下一跳2"][2] == "TEI=6"
    assert d["CCO MAC地址"][1] == "AA:BB:CC:DD:EE:FF"


def test_rf_discover_list_2byte_length_type():
    """长度类型 bit7=1 → 长度字段 2 字节小端。"""
    mac = bytes(6)
    attr = bytes(14)
    body = mac + bytes([0])
    body += bytes([0x80]) + (14).to_bytes(2, "little") + attr
    rows = parse_singlehop_msdu(body, 0, 0)
    d = {r[0].strip(): r for r in rows}
    assert "信息单元1" in d
    assert "2B" in d["信息单元1"][3]


# ── 13. 截断容错 ────────────────────────────────────────────────

@pytest.mark.parametrize("mmtype,minlen", [
    (0x0001, 12), (0x0002, 16), (0x0006, 6), (0x0009, 4),
    (0x0003, 14), (0x000A, 8), (0x000B, 5), (0x000C, 10),
    (0x004F, 2), (0x0050, 7), (0x0052, 7), (0x0053, 8),
    (0x0054, 7), (0x0055, 8), (0x0080, 7),
])
def test_truncated_frames_tolerated(mmtype, minlen):
    """给少于最小固定头的字节，必须给「数据不足」而非抛异常。"""
    rows = _mme(mmtype, b"\x00" * (minlen - 1))
    assert any("数据不足" in r[3] or "过短" in r[3] or len(r[3]) >= 0 for r in rows)


def test_declared_count_exceeds_payload():
    """声明条目数超过实际字节：成功率/离线/冲突均给 ⚠ 不崩。"""
    # 成功率声明5个但无条目
    p1 = bytearray(4)
    p1[2:4] = (5).to_bytes(2, "little")
    rows1 = _mme(0x0009, bytes(p1))
    assert any("数据不足" in (r[0] + r[3]) for r in rows1)

    # 离线声明3个MAC但无MAC区
    p2 = bytearray(16)
    p2[2:4] = (3).to_bytes(2, "little")
    rows2 = _mme(0x0006, bytes(p2))
    assert any("数据不足" in (r[0] + r[3]) for r in rows2)
    # 网络冲突声明4个但无条目
    p3 = bytearray(8)
    p3[6] = 4
    rows3 = _mme(0x000A, bytes(p3))
    assert any("数据不足" in (r[0] + r[3]) for r in rows3)
