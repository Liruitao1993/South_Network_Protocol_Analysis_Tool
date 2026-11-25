# -*- coding: utf-8 -*-
"""协议9 ED 数据域中的测试装置通信控制协议解析回归。"""

import _path_setup  # noqa: F401

from csg_new_gen_parser import CSGNewGenParser, is_test_device_control_frame


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


def test_predicate_accepts_bytes_and_hex_str():
    """判据 is_test_device_control_frame：bytes 与纯 hex 字符串**都**认（批量剥离层给的是 str）"""
    cases = (
        "FEFEFE0501051400000000001AAA0D0A",   # 用户报障帧（功能驱动板·衰减器）
        "FEFEFE0501030800000000000CAA0D0A",   # 功能驱动板·衰减器A
        "05010280000000000083",               # 工装板·CCO 仓模块电源（无 FE 前导）
        "FEFEFEFE05010300030000000007",       # 工装板·STA 仓引脚控制
    )
    for hex_str in cases:
        assert is_test_device_control_frame(hex_str) is True, f"hex 字符串应识别: {hex_str}"
        assert is_test_device_control_frame(bytes.fromhex(hex_str)) is True, \
            f"bytes 应识别: {hex_str}"
    # 带分隔符的写法同样认（`bytes.fromhex` 语义：空格可有可无；剥离层传进来的是已清洗的 str）
    assert is_test_device_control_frame(
        "FE FE FE 05 01 05 14 00 00 00 00 00 1A AA 0D 0A") is True
    print("[OK] 判据 bytes/hex 字符串双认通过")


def test_predicate_rejects_non_frames():
    """判据反例：普通业务帧 / 残片 / 非法输入一律 False（不得把噪声留下）"""
    negatives = (
        "19012000030000417804005B1000000000000000030045000210004111",  # FC 业务帧
        "110101000000000100010000",                                    # 应用层报文
        "FEFEFE",                                                      # 太短
        "0501051400000000001BAA0D0A",                                  # 校验和不符（0x1B≠0x1A）
        "FEFEFE0502051400000000001BAA0D0A",                            # 命令码/负载非法
        "abc def",                                                     # 非 hex
        "",                                                            # 空
    )
    for item in negatives:
        assert is_test_device_control_frame(item) is False, f"不应识别: {item!r}"
    for bad in (None, 123, b"\xff\xfe"):
        assert is_test_device_control_frame(bad) is False, f"非法入参不应抛异常: {bad!r}"
    print("[OK] 判据反例（业务帧/残片/非法入参）通过")


def test_command_name_split_by_board_type():
    """命令名必须按**板类型**取：两块板 0x03/0x04/0x05 语义完全不同（用户 2026-11-11 报障）。

    报障现象：同是「设置衰减值」，A/B 显示「设置引脚状态/衰减器A」「设置220V电源/衰减器B」，
    C 却只显示「衰减器C」—— 三种写法并存。根因是旧实现只有**一张**命令名表
    （按工装板口径命名，再把 0x05 硬塞成「衰减器C」），而功能驱动板的 0x03/0x04/0x05
    分别是设置衰减器 A/B/C 的衰减值（《通信控制协议V1.1》§3.3/§3.4/§3.5）。
    """
    ctor = CSGNewGenParser

    # 功能驱动板 0x03/0x04/0x05 必须是同构的「设置衰减器X的衰减值」
    names = [ctor.test_device_command_name(cmd, "function") for cmd in (0x03, 0x04, 0x05)]
    assert names == ["设置衰减器A的衰减值", "设置衰减器B的衰减值", "设置衰减器C的衰减值"], names

    # 工装板 0x03/0x04 是引脚/220V，且**没有** 0x05
    assert ctor.test_device_command_name(0x03, "fixture") == "设置模块SET/RESET/EVENT引脚状态"
    assert ctor.test_device_command_name(0x04, "fixture") == "设置模块工装板220V电源状态"
    assert ctor.test_device_command_name(0x05, "fixture").startswith("未知命令")

    # 不传板类型按工装板口径（向后兼容旧调用）
    assert ctor.test_device_command_name(0x04) == ctor.test_device_command_name(0x04, "fixture")

    # 端到端：功能驱动板 A/B/C 三帧的「命令名 + 摘要格式」必须同构
    frames = {
        "A": "FEFEFE0501030800000000000CAA0D0A",
        "B": "FEFEFE0501040A00000000000FAA0D0A",
        "C": "FEFEFE0501051400000000001AAA0D0A",
    }
    import batch_core
    for letter, hex_frame in frames.items():
        table = CSGNewGenParser().parse_to_table(bytes.fromhex(hex_frame))
        cmd_row = find_field(table, "命令码")
        assert cmd_row is not None and cmd_row[2] == f"设置衰减器{letter}的衰减值", cmd_row
        summary = batch_core.test_device_summary(table)
        assert summary.split(" | ")[0] == f"设置衰减器{letter}的衰减值", summary
        assert f"衰减器{letter}衰减值=" in summary, summary
    print("[OK] 命令名按板类型分表通过（A/B/C 摘要同构）")


TESTS = [
    test_fixture_cco_power,
    test_fixture_220v_power,
    test_fixture_sta_pin,
    test_function_board_attenuator,
    test_ed_wrapper_control_payload,
    test_reject_non_test_payload,
    test_predicate_accepts_bytes_and_hex_str,
    test_predicate_rejects_non_frames,
    test_command_name_split_by_board_type,
]


if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"[OK] {test.__name__}")
