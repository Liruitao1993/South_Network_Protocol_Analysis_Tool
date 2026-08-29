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
