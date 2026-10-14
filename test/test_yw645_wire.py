# -*- coding: utf-8 -*-
"""协议13（依瓦定制645）**线格式核心**测试：`yw645_wire` + `yw645_di`。

运行（本机 console 默认 GBK，需 UTF-8；参见 test_modular_iface_axdr.py 同款约定）：
    pwshu '$env:PYTHONIOENCODING="utf-8"; python test/test_yw645_wire.py'

oracle 来源
==========
本文件全部 oracle 帧**程序化抽取自** `协议文档/13.依瓦定制645协议/依瓦定制645协议.md`，
抽取脚本见 `.trellis/tasks/10-09-yiwa-645-protocol/research/yiwa-645-protocol-facts.md §6`，
并在此由 `test_doc_oracle_consistency()` 于运行时对文档原文再校验一次（防手抄漂移）。

文档仅对 5 条示例给出了 CS 字面值（X3/X6/X7/X8/X9），其余 4 条文档写 `CS` 占位、
CS 由 `sum(帧头..DATA末) & 0xFF` 算出——5 条字面值全部与计算值吻合，已在下方逐个断言。
"""

import os
import re
import sys

import _path_setup  # noqa: E402,F401

from yw645_wire import (  # noqa: E402
    ADDR_LEN,
    BROADCAST_ADDR,
    FRAME_END,
    FRAME_START,
    HEADER_LEN,
    MASK,
    MAX_DATA_LEN,
    MIN_FRAME_LEN,
    MODE_NAMES,
    MODE_PASS_REQUEST,
    MODE_PASS_RESPONSE,
    MODE_READ_REQUEST,
    MODE_READ_RESPONSE,
    MODE_WRITE_REQUEST,
    TRAILER_LEN,
    DataItem,
    apply_mask,
    best_items_score,
    bcd_to_digits,
    calc_cs,
    cmd_from_len,
    decode_addr12,
    decode_items,
    encode_addr12,
    encode_frame,
    encode_items,
    frame_total_len,
    is_broadcast_addr,
    is_frame,
    len_from_cmd,
    mask_data,
    mode_name,
    resolve_mask,
    score_form,
    unmask_data,
)
from yw645_di import (  # noqa: E402
    DI_BY_ID,
    DI_INDEX_LITERAL,
    DI_INDEX_SWAPPED,
    DI_TABLE,
    di_exists,
    di_id_bytes,
    di_lookup,
    di_payload_note,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n== {title} ==")


def raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


# ── 9 条文档示例（程序化抽取 + CS 补齐；CS 已与文档字面值交叉验证）─────────
# 结构：(名称, 文档行, 完整帧hex, 地址文本, COMMAND, 数据域长, CS来源)
# CS来源 "doc" = 文档自己给出了 CS；"calc" = 文档写 CS 占位、此处为计算值。
ORACLE = [
    ("X1", 137, "68AAAAAAAAAAAA681004001000201016", "广播", 0x10, 4, "calc"),
    ("X2", 153, "6810300000001068200D00100101002006103000000010D516", "103000000010", 0x20, 13, "calc"),
    ("X3", 171, "680450000000136830023714B416", "45000000013", 0x30, 2, "doc"),
    ("X4", 176, "6810300000001068300237149D16", "103000000010", 0x30, 2, "calc"),
    ("X5", 196, "6810300000001068400E37146465666768696A6B6C6D636E9F16", "103000000010", 0x40, 14, "calc"),
    ("X6", 215, "680450000000136830023613B216", "45000000013", 0x30, 2, "doc"),
    ("X7", 236, "68045000000013684024361343C33333333395F6435A3333B4F456883834434338B3F63373B0F692B1F634B2F6333116",
     "45000000013", 0x40, 36, "doc"),
    ("X8", 251, "6810300000001068300237139C16", "103000000010", 0x30, 2, "doc"),
    ("X9", 269, "681030000000106840023713AC16", "103000000010", 0x40, 2, "doc"),
]

#: 透传类示例减 0x33 后的真实数据域（文档明写「减33后可看出 E003/E004」）
PASS_THROUGH_UNMASKED = {
    "X3": "04E1",
    "X4": "04E1",
    "X5": "04E13132333435363738393A303B",
    "X6": "03E0",
    "X8": "04E0",
    "X9": "04E0",
}


def frame_bytes(idx):
    return bytes.fromhex(ORACLE[idx][2])


# ── 1. 常量与模式（含 D1 守卫）────────────────────────────────────────


def test_constants_and_modes():
    section("1. 常量与模式")
    check("FRAME_START=0x68", FRAME_START == 0x68)
    check("FRAME_END=0x16", FRAME_END == 0x16)
    check("ADDR_LEN=6", ADDR_LEN == 6)
    check("MASK=0x33", MASK == 0x33)
    check("MAX_DATA_LEN=0xFFF", MAX_DATA_LEN == 0xFFF)
    check("HEADER_LEN=10 / TRAILER_LEN=2 / MIN_FRAME_LEN=12",
          (HEADER_LEN, TRAILER_LEN, MIN_FRAME_LEN) == (10, 2, 12))
    check("文档四命令码", (MODE_READ_REQUEST, MODE_READ_RESPONSE, MODE_PASS_REQUEST, MODE_PASS_RESPONSE)
          == (0x10, 0x20, 0x30, 0x40))
    check("MODE_NAMES 恰为文档 4 码",
          sorted(MODE_NAMES.keys()) == [0x10, 0x20, 0x30, 0x40], str(sorted(MODE_NAMES.keys())))
    check("mode_name 0x30 → 透传模式请求", mode_name(0x30) == "透传模式请求")
    check("mode_name 0x51 → 未知模式(0x50)", "未知模式" in mode_name(0x51), mode_name(0x51))

    # D1 守卫：写模式命令码文档未定义 → 必须显式 None，且源码不得出现推测值
    check("写模式占位为 None（D1）", MODE_WRITE_REQUEST is None)
    src = open(os.path.join(os.path.dirname(__file__), "..", "yw645_wire.py"), encoding="utf-8").read()
    # 只查「赋值形态」，避免把注释里解说 D1 的 `0x50/0x60` 字样误判为常量
    check("源码无 0x50 推测常量", not re.search(r"=\s*0x50\b", src, re.I))
    check("源码无 0x60 推测常量", not re.search(r"=\s*0x60\b", src, re.I))


# ── 2. 地址域（高字节在前）─────────────────────────────────────────────


def test_address():
    section("2. 地址域（高字节在前）")
    check("123456789012 → 12 34 56 78 90 12",
          encode_addr12("123456789012") == bytes.fromhex("123456789012"))
    check("103000000010 → 10 30 00 00 00 10",
          encode_addr12("103000000010") == bytes.fromhex("103000000010"))
    check("45000000013（11 位）→ 04 50 00 00 00 13",
          encode_addr12("45000000013") == bytes.fromhex("045000000013"))
    check("13 位取低 12 位", encode_addr12("1234567890123") == bytes.fromhex("234567890123"),
          encode_addr12("1234567890123").hex().upper())
    check("0255240500017 → 25 52 40 50 00 17（文档 L146 示例）",
          encode_addr12("0255240500017") == bytes.fromhex("255240500017"))
    check("5 位补 0", encode_addr12("12345") == bytes.fromhex("000000012345"),
          encode_addr12("12345").hex().upper())
    check("去空白", encode_addr12(" 12 34 56 78 90 12 ") == bytes.fromhex("123456789012"))
    check("非数字报错", raises(lambda: encode_addr12("12345678901A")))
    check("空地址报错", raises(lambda: encode_addr12("   ")))

    check("decode 123456789012", decode_addr12(bytes.fromhex("123456789012")) == "123456789012")
    check("decode 103000000010", decode_addr12(bytes.fromhex("103000000010")) == "103000000010")
    check("decode 045000000013 → 45000000013（去前导 0）",
          decode_addr12(bytes.fromhex("045000000013")) == "45000000013")
    check("decode 长度错报错", raises(lambda: decode_addr12(b"\x00" * 5)))

    check("广播识别 AA×6", is_broadcast_addr(BROADCAST_ADDR) is True)
    check("广播常量 = AA×6", BROADCAST_ADDR == b"\xAA" * 6)
    check("非广播", is_broadcast_addr(bytes.fromhex("123456789012")) is False)

    check("bcd_to_digits 045000000013 → 45000000013",
          bcd_to_digits(bytes.fromhex("045000000013")) == "45000000013")
    check("bcd_to_digits 全 0 → '0'", bcd_to_digits(b"\x00\x00") == "0")

    # 往返
    for txt in ("123456789012", "103000000010", "45000000013", "000000000001"):
        expected = txt.lstrip("0") or "0"
        check(f"地址往返 {txt} → {expected}", decode_addr12(encode_addr12(txt)) == expected)


# ── 3. 长度域（12 bit = CMD 低 4 位 + L）───────────────────────────────


def test_length():
    section("3. 长度域拼接")
    check("len_from_cmd(0x10,0x04)=4", len_from_cmd(0x10, 0x04) == 4)
    check("len_from_cmd(0x20,0x0D)=13", len_from_cmd(0x20, 0x0D) == 13)
    check("len_from_cmd(0x30,0x02)=2", len_from_cmd(0x30, 0x02) == 2)
    check("len_from_cmd(0x40,0x24)=36", len_from_cmd(0x40, 0x24) == 36)
    check("len_from_cmd 高 4 位参与(0x1F,0xFF)=0xFFF", len_from_cmd(0x1F, 0xFF) == 0xFFF)

    check("cmd_from_len(0x10,4)=(0x10,0x04)", cmd_from_len(0x10, 4) == (0x10, 0x04))
    check("cmd_from_len(0x20,13)=(0x20,0x0D)", cmd_from_len(0x20, 13) == (0x20, 0x0D))
    check("cmd_from_len(0x40,36)=(0x40,0x24)", cmd_from_len(0x40, 36) == (0x40, 0x24))
    check("cmd_from_len(0x10,0xFFF)=(0x1F,0xFF)", cmd_from_len(0x10, 0xFFF) == (0x1F, 0xFF))
    check("cmd_from_len(0x20,0x123)=(0x21,0x23)", cmd_from_len(0x20, 0x123) == (0x21, 0x23))
    check("0x1000 超限报错", raises(lambda: cmd_from_len(0x10, 0x1000)))
    check("负长度报错", raises(lambda: cmd_from_len(0x10, -1)))

    # 往返
    for mode in (0x10, 0x20, 0x30, 0x40):
        for n in (0, 1, 2, 13, 36, 255, 256, 0xFFF):
            cmd, low = cmd_from_len(mode, n)
            check(f"长度往返 mode={mode:#04x} n={n}", len_from_cmd(cmd, low) == n)
    # 示例逐条
    for name, _ln, hexs, _addr, cmd, n, _src in ORACLE:
        b = bytes.fromhex(hexs)
        check(f"{name} 长度域 {b[8]:02X} {b[9]:02X} → {n}", len_from_cmd(b[8], b[9]) == n)


# ── 4. CS 校验码（范围反证）───────────────────────────────────────────


def test_cs():
    section("4. CS 校验码")
    for name, _ln, hexs, _addr, _cmd, _n, src in ORACLE:
        b = bytes.fromhex(hexs)
        expect = b[-2]
        calc = calc_cs(b[:-2])
        check(f"{name} CS 0x{expect:02X}（{src}）== calc 0x{calc:02X}", calc == expect)

    # 5 条文档字面 CS 逐一显式断言
    doc_cs = {"X3": 0xB4, "X6": 0xB2, "X7": 0x31, "X8": 0x9C, "X9": 0xAC}
    for name, _ln, hexs, _addr, _cmd, _n, src in ORACLE:
        if src != "doc":
            continue
        b = bytes.fromhex(hexs)
        check(f"{name} 文档给出 CS=0x{doc_cs[name]:02X}", b[-2] == doc_cs[name])

    # 范围反证：范围从 byte1 起 / 含 CS 自身 都不等于正确值
    b = bytes.fromhex("680450000000136830023714B416")  # X3, CS=0xB4
    right = calc_cs(b[:-2])
    check("范围反证：body[1:] ≠ 正确值", calc_cs(b[1:-2]) != right,
          f"{calc_cs(b[1:-2]):02X} vs {right:02X}")
    check("范围反证：含 CS ≠ 正确值", calc_cs(b[:-1]) != right,
          f"{calc_cs(b[:-1]):02X} vs {right:02X}")
    # 空 body
    check("CS 空 body = 0", calc_cs(b"") == 0)


# ── 5. ±0x33 混淆 ─────────────────────────────────────────────────────


def test_mask():
    section("5. ±0x33 混淆")
    check("36 13 −0x33 = 03 E0", apply_mask(bytes.fromhex("3613"), invert=False) == bytes.fromhex("03E0"))
    check("37 13 −0x33 = 04 E0", apply_mask(bytes.fromhex("3713"), invert=False) == bytes.fromhex("04E0"))
    check("37 14 −0x33 = 04 E1", apply_mask(bytes.fromhex("3714"), invert=False) == bytes.fromhex("04E1"))
    x5_masked = "37146465666768696A6B6C6D636E"
    x5_unmasked = "04E13132333435363738393A303B"
    check("X5 14B −0x33 = 04 E1 + ASCII \"123456789:0;\"",
          apply_mask(bytes.fromhex(x5_masked), invert=False) == bytes.fromhex(x5_unmasked),
          apply_mask(bytes.fromhex(x5_masked), invert=False).hex().upper())

    check("mask_data = +0x33", mask_data(bytes.fromhex("0000")) == bytes.fromhex("3333"))
    check("unmask_data = −0x33", unmask_data(bytes.fromhex("3333")) == bytes.fromhex("0000"))
    check("apply_mask 默认 −0x33", apply_mask(bytes.fromhex("3613")) == bytes.fromhex("03E0"))

    data = bytes(range(256))
    check("往返 +0x33 → −0x33", apply_mask(apply_mask(data, True), False) == data)
    check("往返 −0x33 → +0x33", apply_mask(apply_mask(data, False), True) == data)

    # 所有透传示例的混淆还原
    for name, want in PASS_THROUGH_UNMASKED.items():
        b = bytes.fromhex(ORACLE[[o[0] for o in ORACLE].index(name)][2])
        got = apply_mask(b[10:-2], invert=False).hex().upper()
        check(f"{name} 数据域 −0x33 = {want}", got == want, got)


# ── 6. 数据项序列（请求/回复互不误判）──────────────────────────────────


def test_items():
    section("6. 数据项序列")
    # 编码
    check("请求形态只拼 ID",
          encode_items([{"id": b"\x00\x10", "data": b"\x01"}], with_fl=False) == b"\x00\x10")
    x1_payload = bytes.fromhex("00100020")
    check("请求形态两 ID",
          encode_items([{"id": "0010"}, {"id": "0020"}], with_fl=False) == x1_payload)
    x2_payload = bytes.fromhex("00100101002006103000000010")
    check("回复形态 ID+FL+数据",
          encode_items([{"id": "0010", "data": "01"}, {"id": "0020", "data": "103000000010"}],
                       with_fl=True) == x2_payload)
    check("FL 超 255 报错",
          raises(lambda: encode_items([{"id": "0010", "data": bytes(256)}], with_fl=True)))
    check("ID 非 2 字节报错", raises(lambda: encode_items([{"id": b"\x00"}], with_fl=False)))
    check("ID 非法 hex 报错", raises(lambda: encode_items([{"id": "ZZZZ"}], with_fl=False)))

    # X2 回复：2 项，ID 0010/0020
    items, form = decode_items(x2_payload, id_exists=di_exists)
    check("X2 解出 2 项", len(items) == 2, str(len(items)))
    check("X2 形态=reply", form == "reply", form)
    check("X2 项1 ID=0010 数据=01",
          items and items[0].id_hex == "0010" and items[0].data_hex == "01" and items[0].fl == 1,
          f"{items[0].id_hex}/{items[0].fl}/{items[0].data_hex}" if items else "-")
    check("X2 项2 ID=0020 FL=6 数据=103000000010",
          len(items) > 1 and items[1].id_hex == "0020" and items[1].fl == 6
          and items[1].data_hex == "103000000010",
          f"{items[1].id_hex}/{items[1].fl}/{items[1].data_hex}" if len(items) > 1 else "-")
    check("X2 偏移 0 / 4", items and items[0].offset == 0 and items[1].offset == 4,
          str([it.offset for it in items]))

    # X1 请求：2 项，无 FL
    items, form = decode_items(x1_payload, id_exists=di_exists)
    check("X1 形态=request", form == "request", form)
    check("X1 2 项 ID 0010/0020",
          [it.id_hex for it in items] == ["0010", "0020"], str([it.id_hex for it in items]))
    check("X1 项无 FL", all(it.fl is None for it in items))
    check("项类型为 DataItem", all(isinstance(it, DataItem) for it in items))
    check("X1 offset 0/2", [it.offset for it in items] == [0, 2])

    # 互相不误判（显式形态）
    check("X1 按回复形态不自洽", decode_items(x1_payload, with_fl=True)[1] == "malformed")
    check("X2 按请求形态不自洽（奇数长）", decode_items(x2_payload, with_fl=False)[1] == "malformed")

    # FL=0 且其后仍有数据 → 回复形态不自洽
    check("FL=0 带尾随 → malformed", decode_items(bytes.fromhex("00100020"), with_fl=True)[1] == "malformed")
    # FL=0 恰在结尾 → 合法
    it_last, fm_last = decode_items(bytes.fromhex("001000"), with_fl=True)
    check("FL=0 结尾合法", fm_last == "reply" and len(it_last) == 1 and it_last[0].fl == 0)

    # 空 payload
    it_e, fm_e = decode_items(b"")
    check("空 payload → 空项不抛错", it_e == [] and fm_e in ("reply", "ambiguous"), fm_e)

    # score_form
    check("score_form 请求 5", score_form(x1_payload, False) == 5, str(score_form(x1_payload, False)))
    s_with_di = score_form(x2_payload, True, id_exists=di_exists) or 0
    s_without = score_form(x2_payload, True, id_exists=None) or 0
    check("score_form 带 DI 加权更高", s_with_di > s_without, f"{s_with_di} > {s_without}")
    check("best_items_score(malformed)=0", best_items_score(b"\x00") == 0)


# ── 7. ±0x33 自动判别（resolve_mask）──────────────────────────────────


def test_resolve_mask():
    section("7. resolve_mask 形态判别")
    # X1/X2 未混淆形态（DI 命中 → 判 raw）
    r1 = resolve_mask(bytes.fromhex("00100020"), id_exists=di_exists)
    check("X1 判 raw（DI 命中救回）", r1.mode == "raw", r1.detail)
    check("X1 payload 保持", r1.payload == bytes.fromhex("00100020"))
    check("X1 得分 raw>unmasked", r1.raw_score > r1.unmasked_score,
          f"{r1.raw_score}>{r1.unmasked_score}")

    r2 = resolve_mask(bytes.fromhex("00100101002006103000000010"), id_exists=di_exists)
    check("X2 判 raw", r2.mode == "raw", r2.detail)

    # X3 透传（ID 未知 → 同分，按规范形态减 0x33）
    r3 = resolve_mask(bytes.fromhex("3714"), id_exists=di_exists)
    check("X3 判 unmasked（同分优先 −0x33）", r3.mode == "unmasked", r3.detail)
    check("X3 还原为 04 E1", r3.payload == bytes.fromhex("04E1"), r3.payload.hex().upper())

    r3b = resolve_mask(bytes.fromhex("3714"))
    check("X3 无 DI 时仍判 unmasked", r3b.mode == "unmasked")
    check("X3 masked 属性 True", r3.masked is True)

    # 两形态皆不合法 → unknown，不猜
    r4 = resolve_mask(b"\x00")
    check("畸形 → unknown", r4.mode == "unknown", r4.detail)
    check("畸形 → 保留原始字节", r4.payload == b"\x00")

    # 透传 14 字节
    r5 = resolve_mask(bytes.fromhex("37146465666768696A6B6C6D636E"), id_exists=di_exists)
    check("X5 payload 判 unmasked", r5.mode == "unmasked", r5.detail)
    check("X5 还原 = 04E1+ASCII",
          r5.payload == bytes.fromhex("04E13132333435363738393A303B"), r5.payload.hex().upper())


# ── 8. 整帧：encode_frame / frame_total_len / is_frame ────────────────


def test_frame():
    section("8. 整帧组帧与切帧")
    # encode_frame 字节级命中透传示例（数据域为「未混淆」语义值，内部 +0x33）
    cases = [
        ("X3", "45000000013", MODE_PASS_REQUEST, "04E1"),
        ("X4", "103000000010", MODE_PASS_REQUEST, "04E1"),
        ("X5", "103000000010", MODE_PASS_RESPONSE, "04E13132333435363738393A303B"),
        ("X6", "45000000013", MODE_PASS_REQUEST, "03E0"),
        ("X8", "103000000010", MODE_PASS_REQUEST, "04E0"),
        ("X9", "103000000010", MODE_PASS_RESPONSE, "04E0"),
    ]
    oracle_by_name = {o[0]: o for o in ORACLE}
    for name, addr, mode, payload in cases:
        want = bytes.fromhex(oracle_by_name[name][2])
        got = encode_frame(encode_addr12(addr), mode, bytes.fromhex(payload))
        check(f"encode_frame 命中 {name}", got == want, f"{got.hex().upper()} vs {want.hex().upper()}")

    # 结构性重建：全部 9 帧都能由 (addr, mode, unmask(DATA)) 重建
    for name, _ln, hexs, _addr, _cmd, _n, _src in ORACLE:
        b = bytes.fromhex(hexs)
        rebuilt = encode_frame(b[1:7], b[8] & 0xF0, apply_mask(b[10:-2], invert=False))
        check(f"{name} 结构重建一致", rebuilt == b,
              f"{rebuilt.hex().upper()} vs {hexs}")

    # 报错
    check("地址长度错报错", raises(lambda: encode_frame(b"\x00" * 5, 0x10, b"")))
    check("数据域超 0xFFF 报错", raises(lambda: encode_frame(BROADCAST_ADDR, 0x10, bytes(0x1000))))

    # frame_total_len / is_frame
    for name, _ln, hexs, _addr, _cmd, n, _src in ORACLE:
        b = bytes.fromhex(hexs)
        check(f"{name} frame_total_len = {n + 12}", frame_total_len(b) == n + 12,
              str(frame_total_len(b)))
        check(f"{name} is_frame True", is_frame(b) is True)
        check(f"{name} 截断帧 is_frame False", is_frame(b[:-1]) is False)
        check(f"{name} 声明总长不变", frame_total_len(b[:-1]) == n + 12)

    check("短帧 frame_total_len=None", frame_total_len(b"\x68\x00") is None)
    check("byte7 非 68H → None",
          frame_total_len(bytes.fromhex("68AAAAAAAAAAAA001004001000201016")) is None)
    check("空 → None", frame_total_len(b"") is None)
    check("空 → is_frame False", is_frame(b"") is False)


# ── 9. DI 表（附录A 单源 + 双索引）────────────────────────────────────


def test_di():
    section("9. 附录A 数据项表")
    check("DI_TABLE 恰 2 项（缺陷 D5）", len(DI_TABLE) == 2, str(len(DI_TABLE)))
    check("DI_BY_ID 键 = {0010,0020}", sorted(DI_BY_ID.keys()) == ["0010", "0020"],
          str(sorted(DI_BY_ID.keys())))
    e10 = DI_BY_ID["0010"]
    e20 = DI_BY_ID["0020"]
    check("0010 名称=设备类型", e10["name"] == "设备类型")
    check("0010 枚举 01=电表", e10["enum"].get("01") == "电表")
    check("0020 名称=设备号", e20["name"] == "设备号")
    check("0020 说明含 12 字节", "12" in e20["note"], e20["note"])
    check("di_id_bytes(0010)=b'\\x00\\x10'", di_id_bytes(e10) == b"\x00\x10")

    check("字面索引 00 10", DI_INDEX_LITERAL.get(b"\x00\x10") is e10)
    check("交换索引 10 00", DI_INDEX_SWAPPED.get(b"\x10\x00") is e10)

    hit, mode = di_lookup(b"\x00\x10")
    check("di_lookup(00 10) literal", hit is e10 and mode == "literal", mode)
    hit, mode = di_lookup(b"\x10\x00")
    check("di_lookup(10 00) swapped", hit is e10 and mode == "swapped", mode)
    hit, mode = di_lookup(b"\x00\x20")
    check("di_lookup(00 20) literal", hit is e20 and mode == "literal", mode)
    hit, mode = di_lookup(b"\x20\x00")
    check("di_lookup(20 00) swapped", hit is e20 and mode == "swapped", mode)
    hit, mode = di_lookup(b"\x04\xE1")
    check("di_lookup(04 E1) unknown", hit is None and mode == "unknown", mode)
    hit, mode = di_lookup(b"\x03\xE0")
    check("di_lookup(03 E0) unknown", hit is None, str((hit, mode)))

    check("di_exists(00 10) True", di_exists(b"\x00\x10") is True)
    check("di_exists(10 00) True（交换）", di_exists(b"\x10\x00") is True)
    check("di_exists(04 E1) False", di_exists(b"\x04\xE1") is False)

    check("设备类型 01 → 电表", di_payload_note(e10, b"\x01") == "电表")
    check("设备类型 02 → 未知+⚠", "未知" in di_payload_note(e10, b"\x02"),
          di_payload_note(e10, b"\x02"))
    check("设备类型空 → ⚠", "⚠" in di_payload_note(e10, b""))
    check("设备号 BCD 103000000010",
          di_payload_note(e20, bytes.fromhex("103000000010")) == "设备号（BCD）= 103000000010",
          di_payload_note(e20, bytes.fromhex("103000000010")))
    check("设备号 >12 字节截断+⚠",
          "⚠" in di_payload_note(e20, bytes(13)) and "截断" in di_payload_note(e20, bytes(13)))


# ── 10. 文档 oracle 运行时一致性（防手抄漂移）──────────────────────────


def test_doc_oracle_consistency():
    section("10. 文档 oracle 运行时校验")
    doc = os.path.join(os.path.dirname(__file__), "..", "协议文档", "13.依瓦定制645协议", "依瓦定制645协议.md")
    if not os.path.exists(doc):
        check("文档存在", False, doc)
        return
    raw = open(doc, encoding="utf-8").read()
    compact = re.sub(r"[^0-9A-Fa-f]", "", raw).upper()  # 去空白/中文/CS 占位等非 hex 字符
    for name, _ln, hexs, _addr, _cmd, n, _src in ORACLE:
        # 帧体（去掉 CS+16H）必须在文档里逐字节出现
        body = hexs[:-(TRAILER_LEN * 2)]
        check(f"{name} 帧体在文档中", body in compact, body[:24] + "…")
        # 文档给出 CS 的：完整帧（含 CS+16）也必须在文档中
        if _src == "doc":
            check(f"{name} 完整帧在文档中", hexs in compact)


def main():
    test_constants_and_modes()
    test_address()
    test_length()
    test_cs()
    test_mask()
    test_items()
    test_resolve_mask()
    test_frame()
    test_di()
    test_doc_oracle_consistency()

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
