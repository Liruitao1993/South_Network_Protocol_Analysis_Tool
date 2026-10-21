# -*- coding: utf-8 -*-
"""协议9 ED 包装与测试装置控制协议的 Web 预处理回归。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from csg_new_gen_parser import CSGNewGenParser
from reflex_web.reflex_web.web_utils import (
    clean_hex_input,
    extract_frames_for_protocol,
    get_frame_summary,
    strip_csg_new_gen_prefix,
)


def wrap_ed_control(payload: bytes, ctrl2: int = 0x10) -> bytes:
    body = bytes([0x01, ctrl2, 0xEF]) + payload
    frame_len = len(body) + 1
    head = bytes([0xED, frame_len & 0xFF, frame_len >> 8]) + body
    return head + bytes([sum(head) & 0xFF, 0xEE])


def test_web_prefix_keeps_ed_wrapper():
    ed = wrap_ed_control(bytes.fromhex("05010280000000000083"))
    text = strip_csg_new_gen_prefix(ed.hex(" "), "auto")
    clean = clean_hex_input(text, keep_newlines=True)
    frames = extract_frames_for_protocol(clean, 9)

    assert frames == [ed.hex().upper()]


def test_web_parser_expands_ed_control_payload():
    ed = wrap_ed_control(bytes.fromhex("05010280000000000083"))
    table = CSGNewGenParser().parse_to_table(ed)
    fields = {row[0]: row for row in table}

    assert "── PLC2.0 监控包装头 ──" in fields
    assert "CCO仓模块电源状态" in fields
    assert "STA1模块=上电" in fields["CCO仓模块电源状态"][2]


def test_web_summary_contains_control_state():
    ed = wrap_ed_control(bytes.fromhex("05010280000000000083"))
    table = CSGNewGenParser().parse_to_table(ed)
    summary = get_frame_summary(table, 9)

    assert "ED监控包装" in summary
    assert "STA1模块=上电" in summary


def test_web_prefix_keeps_bare_test_device_frame():
    """裸工装板/功能驱动板控制帧（无 ED 包装、无 FC 签名）Web 侧同样必须保留。

    与桌面 `main_gui._strip_csg_new_gen_frame_prefix` / 共享 `batch_core` 同口径：
    此前 FC 扫描把整行丢弃 → 批量「预处理后未保留有效报文内容！」（1.23.87 修）。
    """
    for hex_str in (
        "FEFEFE0501051400000000001AAA0D0A",   # 功能驱动板·衰减器（用户报障帧）
        "05010280000000000083",               # 工装板·无 FE 前导
        "FEFEFEFE05010300030000000007",       # 工装板·4×FE 前导
    ):
        text = strip_csg_new_gen_prefix(hex_str, "auto")
        assert text == hex_str, f"Web 应保留 {hex_str}, 实际: {text!r}"

    # 反例：非帧行仍被丢弃
    assert strip_csg_new_gen_prefix("15:50:23 186 HPLC_STA_test", "auto") == ""
    assert strip_csg_new_gen_prefix("abc def", "auto") == ""


def test_web_bare_test_device_frame_end_to_end():
    """裸控制帧经 Web 批量链路（剥离 → 清洗 → 提取）后应能解析成控制协议字段。"""
    hex_str = "FEFEFE0501051400000000001AAA0D0A"
    text = strip_csg_new_gen_prefix(hex_str, "auto")
    clean = clean_hex_input(text, keep_newlines=True)
    frames = extract_frames_for_protocol(clean, 9)
    assert frames == [hex_str], f"应提取到 1 帧, 实际: {frames}"

    table = CSGNewGenParser().parse_to_table(bytes.fromhex(frames[0]))
    fields = {row[0]: row for row in table}
    assert "命令码" in fields and fields["命令码"][2] == "衰减器C"


def test_web_bare_test_device_summary_has_core_value():
    """Web 摘要同样要给出控制帧的核心解析值（衰减值），与桌面同口径。"""
    for hex_str, want in (
        ("FEFEFE0501051400000000001AAA0D0A", "衰减器C衰减值=20 dB"),
        ("FEFEFE0501030800000000000CAA0D0A", "衰减器A衰减值=8 dB"),
        ("05010280000000000083", "CCO仓模块电源状态=STA1模块=上电"),
    ):
        table = CSGNewGenParser().parse_to_table(bytes.fromhex(hex_str))
        summary = get_frame_summary(table, 9)
        assert want in summary, f"{hex_str}: Web 摘要缺 {want} -> {summary}"

    # 反例：普通载波帧摘要不被污染
    mf = bytes.fromhex(
        "19012000030000417804005B1000000000000000030045000210004111"
        "0805000301110101000160020109003700640198900000011100682119"
        "70051E0025000210006801110068211968110433333433661610006801"
        "1100682119681104343433376B16A89D0543" + "00" * 44 + "0B8F8D"
    )
    plain = get_frame_summary(CSGNewGenParser().parse_to_table(mf), 9)
    assert "衰减" not in plain and "工装板" not in plain, plain
