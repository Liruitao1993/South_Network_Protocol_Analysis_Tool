# -*- coding: utf-8 -*-
"""协议13（依瓦定制645）**解析器**测试：`yw645_parser.YW645Parser`。

运行（本机 console 默认 GBK，需 UTF-8；同 test_yw645_wire.py 约定）:
    pwshu '$env:PYTHONIOENCODING="utf-8"; python test/test_yw645_parse.py'

oracle
=====
9 条 golden 帧程序化抽取自 ``协议文档/13.依瓦定制645协议/依瓦定制645协议.md``
（抽取脚本见 research/yiwa-645-protocol-facts.md §6），并在
``test_doc_oracle_consistency`` 于运行时对文档原文再校验一次（防手抄漂移）。

其中：
* X2（L153）是**唯一能自证数据项切分**的示例（DATA 13 字节 = ID 0010/FL 1/值 01 + ID 0020/FL 6/值）；
* X7（L236）作者自述「目前是虚拟，不一定正确」⇒ **只断言地址/长度/CS**，不断言数据项切分。
"""

import os
import re
import sys

import _path_setup  # noqa: E402,F401

from yw645_parser import YW645Parser, calc_checksum, is_frame  # noqa: E402
from yw645_wire import (  # noqa: E402
    MIN_FRAME_LEN,
    MODE_PASS_REQUEST,
    MODE_PASS_RESPONSE,
    MODE_READ_REQUEST,
    MODE_READ_RESPONSE,
    TRAILER_LEN,
    apply_mask,
    calc_cs,
    len_from_cmd,
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


# 结构：(名称, 文档行, 完整帧hex, 地址文本, COMMAND, 数据域长, CS来源)
ORACLE = [
    ("X1", 137, "68AAAAAAAAAAAA681004001000201016", "AAAAAAAAAAAA", 0x10, 4, "calc"),
    ("X2", 153, "6810300000001068200D00100101002006103000000010D516", "103000000010", 0x20, 13, "calc"),
    ("X3", 171, "680450000000136830023714B416", "45000000013", 0x30, 2, "doc"),
    ("X4", 176, "6810300000001068300237149D16", "103000000010", 0x30, 2, "calc"),
    ("X5", 196, "6810300000001068400E37146465666768696A6B6C6D636E9F16", "103000000010", 0x40, 14, "calc"),
    ("X6", 215, "680450000000136830023613B216", "45000000013", 0x30, 2, "doc"),
    ("X7", 236,
     "68045000000013684024361343C33333333395F6435A3333B4F456883834434338B3F63373B0F692B1F634B2F6333116",
     "45000000013", 0x40, 36, "doc"),
    ("X8", 251, "6810300000001068300237139C16", "103000000010", 0x30, 2, "doc"),
    ("X9", 269, "681030000000106840023713AC16", "103000000010", 0x40, 2, "doc"),
]

#: 文档自带 CS（其余 4 条文档写 `CS` 占位、由 sum 算出）
DOC_CS = {"X3": 0xB4, "X6": 0xB2, "X7": 0x31, "X8": 0x9C, "X9": 0xAC}

META_KEYS = [
    "valid", "cs_ok", "cs_expected", "structure_ok", "structure_error",
    "length_ok", "declared_len", "actual_len", "items_form", "mask_mode",
    "di_lookup_mode", "mode_name", "addr", "is_broadcast", "errors",
]

#: X1 / X2 / X3 的逐行字段名 golden（锁定行序，防未来漂移）
ROW_NAMES_X1 = [
    "起始字符", "地址域", "  表号", "  地址定界符", "控制码(COMMAND)", "  模式",
    "  长度高位", "数据长度域(L)", "数据域长度", "数据域", "数据域混淆", "  数据域(还原后)",
    "数据域形态", "数据项1", "数据项2", "校验和(CS)", "结束字符",
]
ROW_NAMES_X2 = [
    "起始字符", "地址域", "  表号", "  地址定界符", "控制码(COMMAND)", "  模式",
    "  长度高位", "数据长度域(L)", "数据域长度", "数据域", "数据域混淆", "  数据域(还原后)",
    "数据域形态", "数据项1", "  长度(FL)", "  数据项值", "数据项2", "  长度(FL)", "  数据项值",
    "校验和(CS)", "结束字符",
]
ROW_NAMES_X3 = [
    "起始字符", "地址域", "  表号", "  地址定界符", "控制码(COMMAND)", "  模式",
    "  长度高位", "数据长度域(L)", "数据域长度", "数据域", "数据域混淆", "  数据域(还原后)",
    "透传载荷（不透明）", "校验和(CS)", "结束字符",
]


def frame_bytes(name):
    for n, _ln, hexs, *_rest in ORACLE:
        if n == name:
            return bytes.fromhex(hexs)
    raise KeyError(name)


def names(rows):
    return [str(r[0]) for r in rows]


def find_row(rows, exact_name):
    for r in rows:
        if str(r[0]) == exact_name:
            return r
    return None


def row(rows, exact_name):
    """取指定行；缺失即断言失败（避免测试脚本里出现 None 下标）。"""
    r = find_row(rows, exact_name)
    assert r is not None, f"缺少行：{exact_name}"
    return r


def ok_row(name, cond, detail=""):
    check(name, cond, detail)


def item_row(rows, index):
    """取第 index 个数据项行（已命中「数据项N」/ 未知 ID「⚠ 数据项N(未知ID)」两种行名）。"""
    target = f"数据项{index}"
    for r in rows:
        nm = str(r[0])
        if nm == target or nm == f"⚠ {target}(未知ID)":
            return r
    raise AssertionError(f"缺少数据项行：{target}")


def offsets_valid(rows, length):
    """每行偏移必须是 0 <= 起 <= 末 < 帧长（闭区间），不得越界/错乱。"""
    for r in rows:
        s, e = r[4], r[5]
        if not isinstance(s, int) or not isinstance(e, int):
            return False, f"{r[0]} 偏移非整数: {s},{e}"
        if not (0 <= s <= e < length):
            return False, f"{r[0]} 偏移 {s}..{e} 越界（帧长 {length}）"
    return True, ""


def masked_frame(hexs):
    """把线上未混淆的示例帧改成「已 +0x33」形态（重算 CS）。"""
    b = bytes.fromhex(hexs)
    n = len_from_cmd(b[8], b[9])
    body = b[:10] + apply_mask(b[10:10 + n], invert=True)
    return body + bytes([calc_cs(body), 0x16])


def item_projection(rows):
    """数据项相关行（名称 + 原始值 + 解析值 + 说明），用于「两种形态结果相同」断言。"""
    out = []
    for r in rows:
        nm = str(r[0])
        if nm.startswith("数据项") or nm.startswith("  长度(FL)") or nm.startswith("  数据项值") \
                or nm.startswith("⚠ 数据项"):
            out.append((nm, r[1], r[2], r[3]))
    return out


def synth_frame(mode, payload):
    """按「12 bit 长度 = COMMAND 低 4 位(高) + L(低)」手工拼一帧（不依赖 wire 的编码器）。"""
    payload = bytes(payload)
    cmd = (mode & 0xF0) | ((len(payload) >> 8) & 0x0F)
    low = len(payload) & 0xFF
    body = (bytes.fromhex("68") + bytes.fromhex("045000000013")
            + bytes.fromhex("68") + bytes([cmd, low]) + payload)
    return body + bytes([calc_cs(body), 0x16])


# ── 1. 常量与工具 ────────────────────────────────────────────────────


def test_helpers():
    section("1. 工具与模块级函数")
    ok_row("MIN_FRAME_LEN=12", MIN_FRAME_LEN == 12, str(MIN_FRAME_LEN))
    ok_row("模块级 is_frame(X1)=True", is_frame(frame_bytes("X1")) is True)
    ok_row("模块级 is_frame(空帧)=False", is_frame(b"") is False)
    ok_row("类静态 is_frame == 模块级", YW645Parser.is_frame(frame_bytes("X2")) is True)
    ok_row("calc_checksum(X3)=0xB4", calc_checksum(frame_bytes("X3")) == 0xB4,
           hex(calc_checksum(frame_bytes("X3"))))
    ok_row("类静态 calc_checksum 一致",
           YW645Parser.calc_checksum(frame_bytes("X6")) == calc_checksum(frame_bytes("X6")))

    p = YW645Parser()
    rows = p.parse(frame_bytes("X2"))
    ok_row("parse_to_table == parse", [tuple(r) for r in p.parse_to_table(frame_bytes("X2"))] == [tuple(r) for r in rows])
    ok_row("parse_to_table 忽略未知 kwargs",
           len(p.parse_to_table(frame_bytes("X2"), parse_level="auto", channel="plc")) == len(rows))
    ok_row("name 属性", YW645Parser.name == "依瓦定制645", YW645Parser.name)


# ── 2. 9 条 golden：地址 / 长度 / CS / 模式 / valid ────────────────────


def test_golden():
    section("2. 9 条 golden（地址/长度/CS/模式/valid/非空表）")
    p = YW645Parser()
    for name, _ln, hexs, addr_text, cmd, n, _src in ORACLE:
        data = bytes.fromhex(hexs)
        rows = p.parse(data)
        m = p.last_meta
        check(f"{name} 非空表", len(rows) > 0, f"{len(rows)} 行")
        check(f"{name} valid=True", m["valid"] is True, str(m["errors"]))
        check(f"{name} structure_ok", m["structure_ok"] is True, m["structure_error"])
        check(f"{name} length_ok", m["length_ok"] is True,
              f"declared={m['declared_len']} actual={m['actual_len']}")
        check(f"{name} 长度域拼接", m["declared_len"] == n, f"{m['declared_len']} vs {n}")
        check(f"{name} cs_ok", m["cs_ok"] is True, f"expected=0x{m['cs_expected']:02X}")
        check(f"{name} 模式名", m["mode_name"] == {
            MODE_READ_REQUEST: "读模式请求",
            MODE_READ_RESPONSE: "读模式返回",
            MODE_PASS_REQUEST: "透传模式请求",
            MODE_PASS_RESPONSE: "透传模式返回",
        }[cmd], m["mode_name"])
        check(f"{name} COMMAND", (data[8] & 0xF0) == cmd, f"0x{data[8]:02X}")
        if addr_text == "AAAAAAAAAAAA":
            check(f"{name} 广播识别", m["is_broadcast"] is True, m["addr"])
        else:
            check(f"{name} 地址(高字节在前)", m["addr"] == addr_text, m["addr"])
            check(f"{name} 非广播", m["is_broadcast"] is False)
        if name in DOC_CS:
            check(f"{name} 帧内 CS == 文档值", data[-2] == DOC_CS[name],
                  f"0x{data[-2]:02X} vs 0x{DOC_CS[name]:02X}")

    # AC4 四条长度域拼接（((COMMAND & 0x0F) << 8) | L）
    for name, want in (("X1", 4), ("X2", 13), ("X3", 2), ("X7", 36)):
        p.parse(frame_bytes(name))
        check(f"AC4 {name} L 拼接={want}", p.last_meta["declared_len"] == want,
              str(p.last_meta["declared_len"]))


# ── 2b. 长度域高 4 位（文档 9 条示例高 4 位恒为 0，必须单独覆盖）─────


def test_length_high_nibble():
    section("2b. 长度域高 4 位（((COMMAND & 0x0F) << 8) | L；示例高 4 位恒 0 故需合成帧）")
    p = YW645Parser()
    for n in (0x100, 0x124, 0x200):
        payload = bytes(n)
        f = synth_frame(MODE_READ_REQUEST, payload)
        rows = p.parse(f)
        m = p.last_meta
        check(f"长度 0x{n:03X} 解析正确", m["declared_len"] == n, str(m["declared_len"]))
        check(f"长度 0x{n:03X} 整帧 = n+12", len(f) == n + MIN_FRAME_LEN, str(len(f)))
        check(f"长度 0x{n:03X} length_ok", m["length_ok"] is True,
              f"帧长{len(f)} vs 期望{n + MIN_FRAME_LEN}")
        check(f"长度 0x{n:03X} valid", m["valid"] is True, str(m["errors"]))
        check(f"长度 0x{n:03X} 数据域长度行", row(rows, "数据域长度")[2] == str(n),
              str(row(rows, "数据域长度")[2]))
        check(f"长度 0x{n:03X} 长度高位行 = (n>>8)&0x0F",
              row(rows, "  长度高位")[2] == str((n >> 8) & 0x0F),
              str(row(rows, "  长度高位")[2]))
        check(f"长度 0x{n:03X} L 行 = n&0xFF",
              row(rows, "数据长度域(L)")[2] == str(n & 0xFF),
              str(row(rows, "数据长度域(L)")[2]))
        ok, why = offsets_valid(rows, len(f))
        check(f"长度 0x{n:03X} 偏移合法", ok, why)

    # 高 4 位与 L 共同构成 12 bit：cmd 0x11 + L 0x24 == 0x124（而不是 0x024 / 0x100）
    f = synth_frame(MODE_READ_REQUEST, bytes(0x124))
    check("COMMAND=0x11 / L=0x24", f[8] == 0x11 and f[9] == 0x24, f"{f[8]:02X} {f[9]:02X}")
    p.parse(f)
    check("0x11 0x24 → 0x124", p.last_meta["declared_len"] == 0x124, str(p.last_meta["declared_len"]))


# ── 3. 逐行行序 golden + 偏移合法性 ──────────────────────────────────


def test_row_golden():
    section("3. 逐行字段名 golden + 偏移区间（闭区间、不越界）")
    p = YW645Parser()
    for name, want in (("X1", ROW_NAMES_X1), ("X2", ROW_NAMES_X2), ("X3", ROW_NAMES_X3)):
        data = frame_bytes(name)
        rows = p.parse(data)
        check(f"{name} 行序 golden", names(rows) == want,
              f"实得 {names(rows)}")
        ok, why = offsets_valid(rows, len(data))
        check(f"{name} 偏移区间合法", ok, why)

    # 9 条 golden 全部偏移合法
    for name, _ln, hexs, *_r in ORACLE:
        data = bytes.fromhex(hexs)
        rows = p.parse(data)
        ok, why = offsets_valid(rows, len(data))
        check(f"{name} 偏移区间合法", ok, why)

    # X2 数据项值偏移逐字节自证
    rows = p.parse(frame_bytes("X2"))
    r10 = row(rows, "数据项1")
    r20 = row(rows, "数据项2")
    v10 = row(rows, "  数据项值")
    value_rows = [r for r in rows if str(r[0]) == "  数据项值"]
    v20 = value_rows[1]
    check("X2 数据项1 偏移 10-11", (r10[4], r10[5]) == (10, 11), f"{r10[4]}-{r10[5]}")
    check("X2 数据项2 偏移 14-15", (r20[4], r20[5]) == (14, 15), f"{r20[4]}-{r20[5]}")
    check("X2 设备类型值偏移 13-13", (v10[4], v10[5]) == (13, 13), f"{v10[4]}-{v10[5]}")
    check("X2 设备号数据偏移 17-22", (v20[4], v20[5]) == (17, 22), f"{v20[4]}-{v20[5]}")

    # 帧级「数据」行的偏移区间必须**精确**为 10..10+n-1（闭区间）——
    # 只验「不越界」会漏掉整体 +1 的错位：实测把 payload_end 的 -1 去掉后，
    # 末偏移落到 CS 字节上，仍满足 0<=起<=末<帧长 ⇒ 边界检查通过但指向错字节。
    for _name, _end in (("X1", 13), ("X2", 22), ("X3", 11)):
        _rows = p.parse(frame_bytes(_name))
        for _nm in ("数据域", "数据域混淆", "  数据域(还原后)", "数据域形态", "透传载荷（不透明）"):
            _r = find_row(_rows, _nm)
            if _r is None:
                continue
            check(f"{_name}「{_nm.strip()}」偏移精确 10-{_end}", (_r[4], _r[5]) == (10, _end),
                  f"实得 {_r[4]}-{_r[5]}")
    # ⚠ 提示行同样不得错位（容错路径的行也要指向正确字节）
    # X3 = 14 字节（0..13），CS 在索引 12、16H 在 13
    _bad = bytearray(frame_bytes("X3"))
    assert len(_bad) == 14 and _bad[-2] == 0xB4, (len(_bad), _bad[-2])
    _bad[-2] ^= 0x01  # 破坏 CS（索引 12）
    _rows = p.parse(bytes(_bad))
    _wr = find_row(_rows, "⚠ 校验和错误")
    check("坏CS ⚠行 偏移指向 CS 字节 12-12", _wr is not None and (_wr[4], _wr[5]) == (12, 12),
          f"实得 {None if _wr is None else (_wr[4], _wr[5])}")


# ── 4. X1/X2 两种 0x33 形态 → 相同字段结果 ───────────────────────────


def test_two_forms():
    section("4. DI 命中帧的两种 0x33 形态 → 相同字段结果")
    p = YW645Parser()
    for name in ("X1", "X2"):
        doc = frame_bytes(name)
        masked = masked_frame(ORACLE[[o[0] for o in ORACLE].index(name)][2])
        rows_doc = p.parse(doc)
        proj_doc = item_projection(rows_doc)
        mode_doc = p.last_meta["mask_mode"]
        di_doc = p.last_meta["di_lookup_mode"]
        ok_doc = p.last_meta["cs_ok"]
        form_doc = p.last_meta["items_form"]

        rows_masked = p.parse(masked)
        proj_masked = item_projection(rows_masked)
        mode_masked = p.last_meta["mask_mode"]
        ok_masked = p.last_meta["cs_ok"]

        check(f"{name}(未混淆) 判 raw", mode_doc == "raw", mode_doc)
        check(f"{name}(已混淆) 判 unmasked", mode_masked == "unmasked", mode_masked)
        check(f"{name} 两形态数据项结果相同", proj_doc == proj_masked,
              f"{proj_doc} vs {proj_masked}")
        check(f"{name} 两形态 DI 命中方式相同", di_doc == p.last_meta["di_lookup_mode"] == "literal")
        check(f"{name} 两形态 items_form 相同", form_doc == p.last_meta["items_form"])
        check(f"{name} 两形态 CS 均通过", ok_doc and ok_masked)

    # X2 关键字段值
    rows = p.parse(frame_bytes("X2"))
    values = [str(r[2]) for r in rows if str(r[0]) == "  数据项值"]
    check("X2 两个数据项值", len(values) == 2, str(values))
    check("X2 设备类型=电表", values and values[0] == "电表", str(values))
    check("X2 设备号 BCD", len(values) > 1 and "103000000010" in values[1], str(values))

    # 字节交换命中索引（ID 10 00 = 设备类型 的字节交换读法）
    payload = bytes.fromhex("1000") + bytes([0x01, 0x01])
    body = bytes.fromhex("68") + bytes.fromhex("045000000013") + bytes.fromhex("6820") + bytes([len(payload)]) + payload
    f = body + bytes([calc_cs(body), 0x16])
    rows = p.parse(f)
    check("字节交换命中 di_lookup_mode", p.last_meta["di_lookup_mode"] == "swapped",
          p.last_meta["di_lookup_mode"])
    check("字节交换命中说明含标记", "字节交换命中" in str(row(rows, "数据项1")[3]),
          str(row(rows, "数据项1")[3]))
    check("字节交换命中名称=设备类型", str(row(rows, "数据项1")[2]) == "设备类型")


# ── 5. X7 只断言地址/长度/CS（作者自述虚拟）──────────────────────────


def test_x7_rules_only():
    section("5. X7（作者自述虚拟）只断言地址/长度/CS")
    p = YW645Parser()
    data = frame_bytes("X7")
    rows = p.parse(data)
    m = p.last_meta
    check("X7 地址=45000000013", m["addr"] == "45000000013", m["addr"])
    check("X7 长度=36", m["declared_len"] == 36, str(m["declared_len"]))
    check("X7 整帧 48 字节", len(data) == 36 + MIN_FRAME_LEN, str(len(data)))
    check("X7 CS=0x31", data[-2] == 0x31 and m["cs_ok"] is True, f"0x{data[-2]:02X}")
    check("X7 模式=透传返回", m["mode_name"] == "透传模式返回", m["mode_name"])
    check("X7 非空表", len(rows) > 0)
    check("X7 len_ok", m["length_ok"] is True)
    ok, why = offsets_valid(rows, len(data))
    check("X7 偏移合法", ok, why)


# ── 6. 容错：非空表 + valid=False + 含 ⚠ ─────────────────────────────


def test_tolerance():
    section("6. 容错（非空表 + valid=False + 含 ⚠）")
    p = YW645Parser()
    x3 = frame_bytes("X3")

    def case(label, data, need_substr=None):
        rows = p.parse(data)
        m = p.last_meta
        warn = [str(r[0]) for r in rows if str(r[0]).startswith("⚠")]
        check(f"{label} 非空表", len(rows) > 0, f"{len(rows)} 行")
        check(f"{label} valid=False", m["valid"] is False)
        check(f"{label} 含 ⚠ 提示行", len(warn) > 0, str(warn))
        if need_substr:
            hit = any(need_substr in str(r[0]) for r in rows)
            check(f"{label} 提示行含 {need_substr}", hit, str(warn))
        return rows, m

    # 6.1 坏 CS（X3 的 B4 → B5）
    bad = x3[:12] + bytes([0xB5]) + x3[13:]
    rows, m = case("坏CS", bad, "校验和")
    cserr = row(rows, "⚠ 校验和错误")
    check("坏CS 给出帧内值与正确值",
          str(cserr[1]) == "B5" and "0xB4" in str(cserr[2]),
          str(cserr))
    check("坏CS cs_expected=0xB4", m["cs_expected"] == 0xB4, hex(m["cs_expected"]))
    check("坏CS 仍完整解析数据域", any(str(r[0]) == "数据域" for r in rows))

    # 6.2 长度域改大（02 → 03）
    case("长度域改大", bytes.fromhex("680450000000136830033714B416"), "帧长度")
    # 6.3 长度域改小（02 → 01）
    case("长度域改小", bytes.fromhex("680450000000136830013714B416"), "帧长度")
    # 6.4 截断帧（保留 10 字节）
    case("截断帧(10B)", x3[:10], "帧长不足")
    # 6.5 末字节非 16H
    case("末字节非16H", x3[:-1] + bytes([0x15]), "结束符")
    # 6.6 空帧
    case("空帧", b"", "帧长不足")
    # 6.7 起始符非 68H
    case("起始符非68H", bytes([0x67]) + x3[1:], "起始符")
    # 6.8 len<12
    case("len<12", x3[:11], "帧长不足")
    # 6.9 地址域定界符非 68H
    case("地址定界符非68H", x3[:7] + bytes([0x69]) + x3[8:], "地址定界符")
    # 6.10 None 输入
    case("None 输入", None, "帧长不足")

    # 所有提示行偏移合法
    for label, data in (("坏CS", bad), ("长度域改小", bytes.fromhex("680450000000136830013714B416"))):
        rows = p.parse(data)
        ok, why = offsets_valid(rows, len(data))
        check(f"{label} 偏移合法", ok, why)


# ── 7. last_meta 全键存在性 ──────────────────────────────────────────


def test_last_meta_keys():
    section("7. last_meta 键齐备")
    p = YW645Parser()
    for name, _ln, hexs, *_r in ORACLE:
        p.parse(bytes.fromhex(hexs))
        missing = [k for k in META_KEYS if k not in p.last_meta]
        check(f"{name} last_meta 全键", not missing, str(missing))
    # 非法帧也要键齐备
    for label, data in (("空帧", b""), ("截断", frame_bytes("X3")[:10])):
        p.parse(data)
        missing = [k for k in META_KEYS if k not in p.last_meta]
        check(f"{label} last_meta 全键", not missing, str(missing))
    check("errors 是 list", isinstance(p.last_meta["errors"], list))


# ── 8. assume_masked 显式覆盖（透传载荷不可判别）────────────────────


def test_assume_masked():
    section("8. assume_masked 显式覆盖（None/True/False）")
    p = YW645Parser()
    x4 = frame_bytes("X4")  # 透传请求，载荷 37 14 ↔ 04 E1（两形态同分，数学不可判别）

    p.parse(x4, assume_masked=None)
    n_none = p.last_meta["mask_mode"]
    p.parse(x4, assume_masked=True)
    n_true = p.last_meta["mask_mode"]
    p.parse(x4, assume_masked=False)
    n_false = p.last_meta["mask_mode"]
    check("X4 None → unmasked（规范形态优先）", n_none == "unmasked", n_none)
    check("X4 True → unmasked", n_true == "unmasked", n_true)
    check("X4 False → raw", n_false == "raw", n_false)

    def restored_hex(data, am):
        rows = p.parse(data, assume_masked=am)
        r = find_row(rows, "  数据域(还原后)")
        return str(r[1]) if r is not None else None

    check("X4 还原后 None = 04 E1", restored_hex(x4, None) == "04 E1", str(restored_hex(x4, None)))
    check("X4 还原后 True = 04 E1", restored_hex(x4, True) == "04 E1")
    check("X4 还原后 False = 37 14", restored_hex(x4, False) == "37 14")

    # 用读模式构造同一载荷，直接看数据项 ID（三态差异）
    def read_frame(payload_hex):
        payload = bytes.fromhex(payload_hex)
        body = bytes.fromhex("68") + bytes.fromhex("045000000013") + bytes.fromhex("6810") + bytes([len(payload)]) + payload
        return body + bytes([calc_cs(body), 0x16])

    f = read_frame("3714")
    ids = {}
    for am in (None, True, False):
        rows = p.parse(f, assume_masked=am)
        r = item_row(rows, 1)
        ids[am] = (p.last_meta["mask_mode"], str(r[1]))
    check("读模式 None → 04E1", ids[None] == ("unmasked", "04E1"), str(ids[None]))
    check("读模式 True → 04E1", ids[True] == ("unmasked", "04E1"), str(ids[True]))
    check("读模式 False → 3714", ids[False] == ("raw", "3714"), str(ids[False]))
    check("三态中 None 与 True 一致、与 False 不同",
          ids[None] == ids[True] and ids[None] != ids[False])
    check("覆盖时 detail 标明显式指定",
          "显式指定" in str(row(p.parse(f, assume_masked=True), "数据域混淆")[3]))


# ── 9. 空数据域 / 形态歧义 / 无法切分 ───────────────────────────────


def test_empty_and_forms():
    section("9. 空数据域 / 形态歧义 / 无法切分")
    p = YW645Parser()

    # 9.1 空数据域：按 request 呈现，不出歧义提示
    body = bytes.fromhex("68") + bytes.fromhex("045000000013") + bytes.fromhex("681000")
    f = body + bytes([calc_cs(body), 0x16])
    rows = p.parse(f)
    m = p.last_meta
    check("空数据域 items_form=request", m["items_form"] == "request", str(m["items_form"]))
    check("空数据域 valid=True", m["valid"] is True, str(m["errors"]))
    check("空数据域 mask_mode=raw", m["mask_mode"] == "raw", str(m["mask_mode"]))
    warn = [str(r[0]) for r in rows if str(r[0]).startswith("⚠")]
    check("空数据域无 ⚠ 行（裸查询帧正常业务）", warn == [], str(warn))
    check("空数据域行显示 0 字节", str(row(rows, "数据域")[2]) == "0字节", str(row(rows, "数据域")[2]))

    # 9.2 形态歧义（两解同分）：01 02 03 04 05 06 同时满足 reply(1项) 与 request(3项)
    amb = bytes.fromhex("010203040506")
    body = bytes.fromhex("68") + bytes.fromhex("045000000013") + bytes.fromhex("6810") + bytes([len(amb)]) + amb
    f = body + bytes([calc_cs(body), 0x16])
    rows = p.parse(f, assume_masked=False)
    m = p.last_meta
    check("歧义 items_form=ambiguous", m["items_form"] == "ambiguous", str(m["items_form"]))
    check("歧义有 ⚠ 提示行", any(str(r[0]) == "⚠ 数据域形态歧义" for r in rows))
    ambrow = row(rows, "⚠ 数据域形态歧义")
    check("歧义行给出另一种解释（请求形态 ID 序列）",
          "0102,0304,0506" in str(ambrow[3]), str(ambrow[3]))

    # 9.3 无法切分（reply 不合法、request 奇数长）
    mal = bytes.fromhex("0102030405")
    body = bytes.fromhex("68") + bytes.fromhex("045000000013") + bytes.fromhex("6810") + bytes([len(mal)]) + mal
    f = body + bytes([calc_cs(body), 0x16])
    rows = p.parse(f, assume_masked=False)
    check("无法切分 items_form=malformed", p.last_meta["items_form"] == "malformed",
          str(p.last_meta["items_form"]))
    check("无法切分有 ⚠ 行", any(str(r[0]) == "⚠ 数据域无法切分" for r in rows))

    # 9.4 未知模式：给 ⚠ 但不判错，且继续解析
    body = bytes.fromhex("68") + bytes.fromhex("045000000013") + bytes.fromhex("685002") + bytes.fromhex("3714")
    f = body + bytes([calc_cs(body), 0x16])
    rows = p.parse(f)
    check("未知模式 有 ⚠ 行", any(str(r[0]) == "⚠ 未知模式" for r in rows))
    check("未知模式下 mode_name 明确未知", p.last_meta["mode_name"].startswith("未知模式"),
          p.last_meta["mode_name"])
    check("未知模式 非空表", len(rows) > 0)

    # 9.5 透传模式：不切数据项（不透明载荷），但仍在表内说明
    rows = p.parse(frame_bytes("X5"))
    check("X5 透传载荷行存在", find_row(rows, "透传载荷（不透明）") is not None)
    check("X5 无 数据项 行", not any(str(r[0]).startswith("数据项") for r in rows),
          str([r[0] for r in rows]))
    check("X5 mask=unmasked（线上已混淆）", p.last_meta["mask_mode"] == "unmasked")
    # 透传载荷按定义不解包 ⇒ 不输出「数据域形态」行。若输出，0x40 返回帧会被标成
    # 「主站请求（无 FL）」，与同行「透传模式返回」自相矛盾（用户可见的误导）。
    check("X5 透传帧无「数据域形态」行", find_row(rows, "数据域形态") is None,
          str([r[0] for r in rows]))
    check("X5 items_form 元数据仍照算（不丢信息）",
          p.last_meta["items_form"] in ("request", "reply", "ambiguous"),
          str(p.last_meta["items_form"]))
    # 反向对照：读模式帧必须仍有该行（防「一刀切删除」式过度修正）
    check("读模式帧仍输出「数据域形态」行",
          find_row(p.parse(frame_bytes("X1")), "数据域形态") is not None)


# ── 10. 摘要 ─────────────────────────────────────────────────────────


def test_summary():
    section("10. get_summary")
    p = YW645Parser()
    s1 = p.get_summary(frame_bytes("X1"))
    check("X1 摘要含广播", "广播" in s1, s1)
    check("X1 摘要含模式", "读模式请求" in s1, s1)
    check("X1 摘要含 CS✓", "CS✓" in s1, s1)
    check("X1 摘要含数据项名", "设备类型" in s1 and "设备号" in s1, s1)

    s2 = p.get_summary(frame_bytes("X2"))
    check("X2 摘要含表号", "103000000010" in s2, s2)
    check("X2 摘要含数据域长度", "数据域:13字节" in s2, s2)

    s3 = p.get_summary(frame_bytes("X3"))
    check("X3 摘要含透传模式", "透传模式请求" in s3, s3)

    check("空输入摘要不抛错", p.get_summary(b"") == "无效帧（长度不足）", p.get_summary(b""))
    check("非法起始符摘要不抛错", "结构错误" in p.get_summary(bytes([0x67]) + frame_bytes("X3")[1:]))

    bad = frame_bytes("X3")[:12] + bytes([0xB5]) + frame_bytes("X3")[13:]
    check("坏CS 摘要 = CS✗", p.get_summary(bad).endswith("CS✗"), p.get_summary(bad))


# ── 11. 文档 oracle 运行时一致性（防手抄漂移）────────────────────────


def test_doc_oracle_consistency():
    section("11. 文档 oracle 运行时校验")
    doc = os.path.join(os.path.dirname(__file__), "..", "协议文档", "13.依瓦定制645协议", "依瓦定制645协议.md")
    if not os.path.exists(doc):
        check("文档存在", False, doc)
        return
    raw = open(doc, encoding="utf-8").read()
    compact = re.sub(r"[^0-9A-Fa-f]", "", raw).upper()
    for name, _ln, hexs, _addr, _cmd, n, src in ORACLE:
        body = hexs[:-(TRAILER_LEN * 2)]
        check(f"{name} 帧体在文档中", body in compact, body[:24] + "…")
        if src == "doc":
            check(f"{name} 完整帧在文档中", hexs in compact)
    # 文档给出的 CS 与我们复算一致
    for name, cs in DOC_CS.items():
        data = frame_bytes(name)
        check(f"{name} 文档 CS 复算吻合", calc_cs(data[:-2]) == cs == data[-2],
              f"calc=0x{calc_cs(data[:-2]):02X} doc=0x{cs:02X}")


def main():
    test_helpers()
    test_golden()
    test_length_high_nibble()
    test_row_golden()
    test_two_forms()
    test_x7_rules_only()
    test_tolerance()
    test_last_meta_keys()
    test_assume_masked()
    test_empty_and_forms()
    test_summary()
    test_doc_oracle_consistency()

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
