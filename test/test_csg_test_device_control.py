# -*- coding: utf-8 -*-
"""协议9 ED 数据域中的测试装置通信控制协议解析回归。"""

import _path_setup  # noqa: F401

from csg_new_gen_parser import CSGNewGenParser


def find_field(table, name):
    for row in table:
        if row[0] == name:
            return row
    return None


def wrap_ed_control(payload: bytes, ctrl2: int = 0x10) -> bytes:
    body = bytes([0x01, ctrl2, 0xEF]) + payload
    frame_len = len(body) + 1
    head = bytes([0xED]) + frame_len.to_bytes(2, "little") + body
    return head + bytes([sum(head) & 0xFF, 0xEE])


def test_fixture_cco_power():
    table = CSGNewGenParser().parse_to_table(
        bytes.fromhex("05010280000000000083"))
    row = find_field(table, "CCO仓模块电源状态")
    assert row is not None
    assert "STA1模块=上电" in row[2]
    assert "STA2模块=断电" in row[2]
    assert row[4] == 3 and row[5] == 5


def test_fixture_220v_power():
    table = CSGNewGenParser().parse_to_table(
        bytes.fromhex("05010401000000000006"))
    row = find_field(table, "工装板220V电源状态")
    assert row is not None
    assert row[2] == "连接状态"


def test_fixture_sta_pin():
    table = CSGNewGenParser().parse_to_table(
        bytes.fromhex("FEFEFEFE05010300030000000007"))
    row = find_field(table, "STA仓引脚控制")
    assert row is not None
    assert "STA1" in row[2]
    assert "RST=高电平" in row[2]
    assert "EVENT=高电平" in row[2]


def test_function_board_attenuator():
    table = CSGNewGenParser().parse_to_table(
        bytes.fromhex("FEFEFE0501030800000000000CAA0D0A"))
    row = find_field(table, "衰减器A衰减值")
    assert row is not None
    assert row[2] == "8 dB"
    assert find_field(table, "结束符") is not None


def test_ed_wrapper_control_payload():
    ed = wrap_ed_control(bytes.fromhex("05010280000000000083"))
    table = CSGNewGenParser().parse_to_table(ed)
    assert find_field(table, "起始符(ED)") is not None
    assert find_field(table, "控制域1") is not None
    row = find_field(table, "CCO仓模块电源状态")
    assert row is not None
    assert "STA1模块=上电" in row[2]
    assert row[4] == 9 and row[5] == 11


def test_reject_non_test_payload():
    # 普通应用层报文不能因为校验和偶然匹配而被误判为工装板控制帧。
    table = CSGNewGenParser().parse_to_table(
        bytes.fromhex("110101000000000100010000"))
    assert find_field(table, "测试装置工装板控制协议") is None
    assert find_field(table, "报文端口号") is not None


TESTS = [
    test_fixture_cco_power,
    test_fixture_220v_power,
    test_fixture_sta_pin,
    test_function_board_attenuator,
    test_ed_wrapper_control_payload,
    test_reject_non_test_payload,
]


if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"[OK] {test.__name__}")
