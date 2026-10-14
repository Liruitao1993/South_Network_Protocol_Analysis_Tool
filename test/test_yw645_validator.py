# -*- coding: utf-8 -*-
"""协议13（依瓦定制645）**校验器**测试：`validator.yw645_validator.YW645Validator`。

运行（本机 console 默认 GBK，需 UTF-8）:
    pwshu '$env:PYTHONIOENCODING="utf-8"; python test/test_yw645_validator.py'

要点
====
* 校验器与解析器**同一份判据**（校验器直接读 ``YW645Parser.last_meta``），因此本文件同时钉住
  「判据不漂移」与「校验 FAIL 但解析仍完整」（prd R8.3 / AC11）。
* 阶段 3 之前**不依赖** ``protocol_registry.make_validator(13)``（注册表尚未追加协议13）；
  仅断言「按 ``validator:<Class>`` 路径 import 可构造」这条未来接线。
"""

import importlib
import sys

import _path_setup  # noqa: E402,F401

from validator import YW645Validator as ExportedValidator  # noqa: E402
from validator.base import CheckLevel  # noqa: E402
from validator.yw645_validator import YW645Validator  # noqa: E402
from yw645_parser import YW645Parser  # noqa: E402
from yw645_wire import calc_cs  # noqa: E402

PASS = 0
FAIL = 0

CHECK_NAMES = ["帧长度", "起始字符", "地址域定界符", "结束字符", "数据域长度", "校验和", "模式", "数据域切分"]

ORACLE = [
    ("X1", "68AAAAAAAAAAAA681004001000201016"),
    ("X2", "6810300000001068200D00100101002006103000000010D516"),
    ("X3", "680450000000136830023714B416"),
    ("X4", "6810300000001068300237149D16"),
    ("X5", "6810300000001068400E37146465666768696A6B6C6D636E9F16"),
    ("X6", "680450000000136830023613B216"),
    ("X7", "68045000000013684024361343C33333333395F6435A3333B4F456883834434338B3F63373B0F692B1F634B2F6333116"),
    ("X8", "6810300000001068300237139C16"),
    ("X9", "681030000000106840023713AC16"),
]


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


def frame_bytes(name):
    for n, hexs in ORACLE:
        if n == name:
            return bytes.fromhex(hexs)
    raise KeyError(name)


def item(result, name):
    """取指定校验项；缺失即断言失败（避免 Optional 下标）。"""
    for c in result.checks:
        if c.name == name:
            return c
    raise AssertionError(f"缺少校验项：{name}")


def level_of(result, name):
    return item(result, name).level


def build_frame(cmd, payload_hex, addr_hex="045000000013"):
    payload = bytes.fromhex(payload_hex)
    body = bytes.fromhex("68") + bytes.fromhex(addr_hex) + bytes.fromhex("68") + bytes([cmd]) + bytes([len(payload)]) + payload
    return body + bytes([calc_cs(body), 0x16])


# ── 1. 导入与构造 ────────────────────────────────────────────────────


def test_export():
    section("1. 导入与构造")
    check("validator 包导出 YW645Validator", ExportedValidator is YW645Validator)
    mod = importlib.import_module("validator.yw645_validator")
    check("按 module:Class 路径可取类", getattr(mod, "YW645Validator") is YW645Validator)
    check("可无参构造", isinstance(YW645Validator(), YW645Validator))
    check("protocol 名", YW645Validator().verify(frame_bytes("X1")).protocol == "依瓦定制645")


# ── 2. 9 条 golden 全项 PASS ─────────────────────────────────────────


def test_golden_all_pass():
    section("2. 9 条 golden 全项 PASS")
    v = YW645Validator()
    for name, hexs in ORACLE:
        result = v.verify(bytes.fromhex(hexs))
        check(f"{name} valid=True", result.valid is True, result.summary())
        check(f"{name} FAIL=0", result.fail_count == 0, result.summary())
        check(f"{name} WARN=0", result.warn_count == 0, result.summary())
        got = [c.name for c in result.checks]
        missing = [n for n in CHECK_NAMES if n not in got]
        check(f"{name} 检查项齐备（{len(CHECK_NAMES)} 项）", not missing, str(missing))


# ── 3. 检查项级别与判据 ──────────────────────────────────────────────


def test_check_levels():
    section("3. 检查项级别与判据")
    v = YW645Validator()
    r = v.verify(frame_bytes("X2"))
    check("起始字符 PASS", level_of(r, "起始字符") == CheckLevel.PASS)
    check("地址域定界符 PASS", level_of(r, "地址域定界符") == CheckLevel.PASS)
    check("结束字符 PASS", level_of(r, "结束字符") == CheckLevel.PASS)
    check("数据域长度 PASS", level_of(r, "数据域长度") == CheckLevel.PASS)
    check("校验和 PASS", level_of(r, "校验和") == CheckLevel.PASS)
    check("模式 PASS", level_of(r, "模式") == CheckLevel.PASS)
    check("数据域切分 PASS", level_of(r, "数据域切分") == CheckLevel.PASS)
    cs_item = item(r, "校验和")
    check("校验和项给出期望与实际", cs_item.expected == "0xD5" and cs_item.actual == "0xD5",
          f"{cs_item.expected}/{cs_item.actual}")
    len_item = item(r, "数据域长度")
    check("数据域长度项给出期望整帧 25 字节", "25字节" in len_item.expected, len_item.expected)


# ── 4. 坏帧：对应项 FAIL，但解析器仍完整输出 ─────────────────────────


def test_bad_frames():
    section("4. 坏帧对应项 FAIL（解析仍完整）")
    v = YW645Validator()
    p = YW645Parser()

    # 4.1 坏 CS（X3 的 B4 → B5）
    x3 = frame_bytes("X3")
    bad_cs = x3[:12] + bytes([0xB5]) + x3[13:]
    r = v.verify(bad_cs)
    check("坏CS 校验和 FAIL", level_of(r, "校验和") == CheckLevel.FAIL)
    check("坏CS 整体 valid=False", r.valid is False)
    check("坏CS errors 非空", bool(r.errors), str(r.errors))
    rows = p.parse(bad_cs)
    check("坏CS 解析器仍完整输出（非空表）", len(rows) > 0, f"{len(rows)} 行")
    check("坏CS 解析器 valid=False", p.last_meta["valid"] is False)
    check("坏CS 解析器含 ⚠", any(str(x[0]).startswith("⚠") for x in rows))

    # 4.2 长度域改大（02 → 03）
    r = v.verify(bytes.fromhex("680450000000136830033714B416"))
    check("长度不符 数据域长度 FAIL", level_of(r, "数据域长度") == CheckLevel.FAIL)
    check("长度不符 valid=False", r.valid is False)
    check("长度不符 解析器仍非空表", len(p.parse(bytes.fromhex("680450000000136830033714B416"))) > 0)

    # 4.3 末字节非 16H
    r = v.verify(x3[:-1] + bytes([0x15]))
    check("缺16H 结束字符 FAIL", level_of(r, "结束字符") == CheckLevel.FAIL)
    check("缺16H valid=False", r.valid is False)

    # 4.4 起始符非 68H
    r = v.verify(bytes([0x67]) + x3[1:])
    check("非68H 起始字符 FAIL", level_of(r, "起始字符") == CheckLevel.FAIL)
    check("非68H valid=False", r.valid is False)

    # 4.5 地址域定界符非 68H
    r = v.verify(x3[:7] + bytes([0x69]) + x3[8:])
    check("定界符错 地址域定界符 FAIL", level_of(r, "地址域定界符") == CheckLevel.FAIL)
    check("定界符错 valid=False", r.valid is False)

    # 4.6 空帧
    r = v.verify(b"")
    check("空帧 帧长度 FAIL", level_of(r, "帧长度") == CheckLevel.FAIL)
    check("空帧 valid=False", r.valid is False)
    check("空帧只 1 项检查", len(r.checks) == 1, str(len(r.checks)))

    # 4.7 数据域无法切分（5 字节奇数长 → 两形态皆不合法）
    r = v.verify(build_frame(0x10, "0102030405"))
    check("无法切分 数据域切分 FAIL", level_of(r, "数据域切分") == CheckLevel.FAIL)
    check("无法切分 valid=False", r.valid is False)


# ── 5. 未知模式：WARN 而非 FAIL（文档缺陷 D1）────────────────────────


def test_unknown_mode_warn():
    section("5. 未知模式 = WARN（文档 D1：写模式无命令码）")
    v = YW645Validator()
    r = v.verify(build_frame(0x50, "3714"))
    check("未知模式 模式项 WARN", level_of(r, "模式") == CheckLevel.WARN)
    check("未知模式 不被判错", level_of(r, "模式") != CheckLevel.FAIL)
    check("未知模式 整体 valid=True（仅 WARN）", r.valid is True, r.summary())
    check("未知模式 警告计数=1", r.warn_count == 1, str(r.warn_count))
    check("未知模式 说明点名文档缺陷", "D1" in item(r, "模式").message, item(r, "模式").message)

    # 透传模式与读模式都是文档定义的合法模式
    for cmd, want in ((0x10, CheckLevel.PASS), (0x20, CheckLevel.PASS),
                      (0x30, CheckLevel.PASS), (0x40, CheckLevel.PASS)):
        rr = v.verify(build_frame(cmd, "3714"))
        check(f"模式 0x{cmd:02X} PASS", level_of(rr, "模式") == want, rr.summary())


# ── 6. to_dict / summary 结构 ────────────────────────────────────────


def test_result_shape():
    section("6. ValidationResult 结构")
    v = YW645Validator()
    r = v.verify(frame_bytes("X6"))
    d = r.to_dict()
    check("to_dict 含协议名", d["协议"] == "依瓦定制645", str(d.get("协议")))
    check("to_dict 整体结果=通过", d["整体结果"] == "通过")
    check("to_dict 校验项数 = 8", len(d["校验项"]) == 8, str(len(d["校验项"])))
    check("to_dict 校验项含名称/状态", all("名称" in c and "状态" in c for c in d["校验项"]))
    check("summary 含通过项数", "通过8项" in r.summary(), r.summary())

    bad = v.verify(frame_bytes("X3")[:12] + bytes([0xB5]) + frame_bytes("X3")[13:])
    check("坏帧 summary 标注失败", bad.summary().startswith("[失败]"), bad.summary())


def main():
    test_export()
    test_golden_all_pass()
    test_check_levels()
    test_bad_frames()
    test_unknown_mode_warn()
    test_result_shape()

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
