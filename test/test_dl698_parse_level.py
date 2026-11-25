# -*- coding: utf-8 -*-
"""698.45（协议8）解析级别回归。

用户报障（2026-11-17）：协议8 没有解析级别，当输入的是**以某个 OAD 开头**的报文
（不含 68…16 链路层帧头）时，被硬按链路层帧拆 → 表格里出现
「起始字符不是 0x68（实际 0x48）」「长度域 L=32（整帧应为 34 字节）」
「结束符 0x16 缺失」等一串假错，真正的 OAD/数据完全没解出来。

现协议8 提供四档解析级别（`parse_level`）：
  auto  自动识别（0x68→帧；已知 APDU 服务码→仅APDU；OAD+可解数据→仅数据域）
  frame 完整链路层帧 68…16（默认，与加入级别前逐字节一致）
  apdu  仅APDU（应用层报文）
  data  仅数据域 = OAD(4B) + A-XDR 数据

运行: python test/test_dl698_parse_level.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import parser_registry as reg  # noqa: E402
import protocol_registry  # noqa: E402
from dl_t698_45_parser import DLT69845Parser  # noqa: E402

PARSER = reg.get_parser("dl_t698_45")

#: 用户现场报文：以 OAD(48 20 80 00) 开头的数据域，非链路层帧
OAD_FRAME = bytes.fromhex("4820800002021601050000038400")
#: 合法链路层帧（L=23，整帧 25 字节，HCS/FCS 均通过）
VALID_FRAME = bytes.fromhex("6817004305AAAAAAAAAAAA00AA2A05010143000300006D5C16")
#: 合法 APDU（GET-Request normal，不含帧头）
APDU_ONLY = bytes.fromhex("050102400102000611010100")

PASSED = 0
FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK  {name}")
    else:
        FAILED += 1
        print(f"  FAIL {name}  {detail}")


def names(rows):
    return [str(row[0]) for row in rows]


def row_by_name(rows, name):
    for row in rows:
        if str(row[0]) == name:
            return row
    return None


# ----------------------------------------------------------------------
# 级别取值与自动判别
# ----------------------------------------------------------------------
def test_normalize_level():
    for raw, expect in [
        (None, "frame"),
        ("", "frame"),
        ("AUTO", "auto"),
        ("apdu", "apdu"),
        ("data", "data"),
        ("frame", "frame"),
        ("乱写", "frame"),
    ]:
        check(f"normalize({raw!r}) → {expect}",
              PARSER.normalize_parse_level(raw) == expect,
              PARSER.normalize_parse_level(raw))


def test_detect_level():
    check("0x68 开头 → frame", PARSER.detect_parse_level(VALID_FRAME) == "frame",
          PARSER.detect_parse_level(VALID_FRAME))
    check("已知 APDU 服务码 → apdu", PARSER.detect_parse_level(APDU_ONLY) == "apdu",
          PARSER.detect_parse_level(APDU_ONLY))
    check("OAD 开头 → data", PARSER.detect_parse_level(OAD_FRAME) == "data",
          PARSER.detect_parse_level(OAD_FRAME))
    check("垃圾短包不臆测层次（回 frame）",
          PARSER.detect_parse_level(bytes.fromhex("14")) == "frame")
    # FE 前导不参与判别
    fe = bytes.fromhex("FEFEFEFE") + OAD_FRAME
    check("带 FE 前导的 OAD 报文 → data", PARSER.detect_parse_level(fe) == "data",
          PARSER.detect_parse_level(fe))


# ----------------------------------------------------------------------
# 用户报障帧：数据域级别必须解出 OAD + 数据，且不再出现假错
# ----------------------------------------------------------------------
def test_data_level_user_frame():
    rows = PARSER.parse_to_table(OAD_FRAME, parse_level="data")
    nm = names(rows)
    check("无「起始字符」假错行", "起始字符" not in nm, nm)
    check("无「长度域」假错行", "长度域" not in nm, nm)
    check("首行声明解析级别", "解析级别" in nm[0] and "数据域" in rows[0][2], rows[0])
    oad = row_by_name(rows, "OAD")
    check("有 OAD 行", oad is not None, nm)
    if oad:
        check("OAD 原始值", oad[1] == "48 20 80 00", oad[1])
        check("OAD 解析出 OI", "0x4820" in str(oad[2]), oad[2])
        check("OAD 有对象名称（OI 库命中）", "光伏逆变器" in str(oad[3]), oad[3])
        check("OAD 字节范围 0~3", (oad[4], oad[5]) == (0, 3), (oad[4], oad[5]))
    # A-XDR 数据：structure{enum 1, double-long 900} + null
    check("展开 1 号数据项（structure，2 成员）",
          any("structure" in str(r[3]) for r in rows), rows)
    check("解出枚举值 1", any(str(r[2]) == "1" and "enum" in str(r[3]) for r in rows))
    check("解出 900", any(str(r[2]) == "900" for r in rows))
    check("数据域标注已完整解码",
          any(r[0] == "数据域" and "完整" in str(r[2]) for r in rows), nm)
    check("末尾给原始报文",
          row_by_name(rows, "原始报文") is not None, nm)
    check("无未解析字节（本帧可完整解码）", "未解析字节" not in nm, nm)


def test_auto_equals_data_for_user_frame():
    auto_rows = PARSER.parse_to_table(OAD_FRAME, parse_level="auto")
    data_rows = PARSER.parse_to_table(OAD_FRAME, parse_level="data")
    check("auto 与 data 输出一致", auto_rows == data_rows)


def test_auto_never_emits_fake_frame_errors():
    rows = PARSER.parse_to_table(OAD_FRAME, parse_level="auto")
    msgs = " ".join(str(r[3]) for r in rows)
    check("auto 下没有「起始字符不是 0x68」", "起始字符不是" not in msgs, msgs)
    check("auto 下没有「长度域 L=32」", "L=32" not in msgs, msgs)
    # 容错开关也无所谓：非帧级别不走容错拆帧
    tol = PARSER.parse_to_table(OAD_FRAME, verify=False, parse_level="auto")
    check("verify=False + auto 同样不产生假错",
          all("起始字符不是" not in str(r[3]) for r in tol), tol)


# ----------------------------------------------------------------------
# APDU / 帧 级别
# ----------------------------------------------------------------------
def test_apdu_level():
    rows = PARSER.parse_to_table(APDU_ONLY, parse_level="apdu")
    nm = names(rows)
    check("APDU 级别首行声明", "APDU" in str(rows[0][2]), rows[0])
    t = row_by_name(rows, "APDU类型")
    check("识别 GET-Request", t is not None and "GET-Request" in str(t[2]), t)
    check("展开 APDU 字段（有 PIID 或 OAD 行）",
          any("OAD" in str(r[0]) or "PIID" in str(r[0]) for r in rows), nm)
    # 未知服务码要给出「切到仅数据域」的建议，而不是空白
    bad = PARSER.parse_to_table(OAD_FRAME, parse_level="apdu")
    check("未知服务码给建议行", any(str(r[0]).strip() == "建议" for r in bad), names(bad))


def test_frame_level_is_default_and_unchanged():
    strict = PARSER.parse_to_table(VALID_FRAME)
    check("默认级别 = frame（严格）",
          strict == PARSER.parse_to_table(VALID_FRAME, parse_level="frame"))
    check("默认级别 = frame（容错）",
          PARSER.parse_to_table(VALID_FRAME, verify=False)
          == PARSER.parse_to_table(VALID_FRAME, verify=False, parse_level="frame"))
    nm = names(strict)
    for expected in ("起始字符", "长度域", "控制域", "地址特征", "服务器地址SA",
                     "客户机地址CA", "帧头校验HCS", "帧校验FCS", "结束符"):
        check(f"帧表含 {expected}", expected in nm, nm)
    # 0x68 帧在 auto 下与 frame 完全一致（逐行对拍）
    check("auto(0x68 帧) == frame",
          PARSER.parse_to_table(VALID_FRAME, parse_level="auto") == strict)


def test_non_frame_still_fails_at_frame_level():
    rows = PARSER.parse_to_table(OAD_FRAME, parse_level="frame")
    check("明确选 frame 时仍报「起始字符错误」",
          rows[0][0].startswith("❌") and "起始字符" in str(rows[0][3]), rows[0])


# ----------------------------------------------------------------------
# 注册表 / GUI 包装
# ----------------------------------------------------------------------
def test_registry_wiring():
    spec = protocol_registry.get_protocol(8)
    check("协议8 parse_level_family = dl698", spec.parse_level_family == "dl698",
          spec.parse_level_family)
    check("协议8 parser_wrapper = dl698", spec.parser_wrapper == "dl698",
          spec.parser_wrapper)

    wrapper = protocol_registry.build_gui_parser(8, PARSER)
    check("未指定级别时包装器保持旧行为（= frame 严格表）",
          wrapper.parse_to_table(VALID_FRAME) == PARSER.parse_to_table(VALID_FRAME))

    auto_wrapper = protocol_registry.build_gui_parser(8, PARSER, parse_level="auto")
    check("包装器透传 parse_level=auto",
          auto_wrapper.parse_to_table(OAD_FRAME)
          == PARSER.parse_to_table(OAD_FRAME, parse_level="auto"))
    check("包装器透传 verify=False",
          auto_wrapper.parse_to_table(VALID_FRAME, verify=False)
          == PARSER.parse_to_table(VALID_FRAME, verify=False, parse_level="auto"))
    # 其余属性透传（py_script_engine 的用户脚本会用 parser.parse）
    check("包装器透传 base parser 的 parse", callable(getattr(wrapper, "parse", None)))
    check("包装器透传 detect_parse_level",
          callable(getattr(wrapper, "detect_parse_level", None)))

    # 其它协议不受影响
    check("协议7 仍为 direct", protocol_registry.get_protocol(7).parser_wrapper == "direct")


def test_fresh_parser_instance():
    """批量 worker 用独立实例：级别参数不应污染实例状态。"""
    p = DLT69845Parser()
    p.parse_to_table(OAD_FRAME, parse_level="data")
    check("级别不改变 frame 解析（同一实例）",
          p.parse_to_table(VALID_FRAME) == PARSER.parse_to_table(VALID_FRAME))


def main():
    for fn in (
        test_normalize_level,
        test_detect_level,
        test_data_level_user_frame,
        test_auto_equals_data_for_user_frame,
        test_auto_never_emits_fake_frame_errors,
        test_apdu_level,
        test_frame_level_is_default_and_unchanged,
        test_non_frame_still_fails_at_frame_level,
        test_registry_wiring,
        test_fresh_parser_instance,
    ):
        print(f"\n[{fn.__name__}]")
        fn()
    print(f"\n{'=' * 50}\n{PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
