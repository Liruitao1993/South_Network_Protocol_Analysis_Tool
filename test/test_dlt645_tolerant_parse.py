# -*- coding: utf-8 -*-
"""协议6（DL/T645-2007）容错解析回归测试（2026-09-17，任务 09-17-dlt645-tolerant-parse）

用户原话：「协议6，如果提供的645帧校验不正确的话，你没有进行解析，我需要的是你**正常进行解析**，
并把**校验和计算好，提示我正确的校验是什么**，而不是不解析」

问题根因（已复现）：`check_frame()` 把「结构判据」（长度≥12 / 双 68H / 结束 16H）与
「校验判据」（CS）混在一个返回值里，`parse()` 用它**提前 return** ⇒ CS 写错时结果表为空。
依据 AGENTS.md §8 陷阱 23（不得因字段不符而返回空白结果）与同仓先例
`protocol_parser.py`（南网：照常解析 + `校验和: {校验值, 计算值, 校验结果}` + 失败提示）。

覆盖（对应 prd.md 验收 A1~A11）：
  A1/A2/A3  CS 错帧：完整字段 + 「⚠ 校验和错误」行（帧内值/应为值/计算规则）+ valid False
  A4        合法帧与改动前**逐行一致**（快照比对，13 行、无新增提示行、valid True）
  A5        数据长度声明不符：完整解析 + 提示含「应声明 N 字节」
  A6        结构不符（第 1/8 字节、末字节）：仍解析 + 「❌ 帧结构错误」指明具体字节
  A7        帧长 <12：不抛异常 + 帧长不足说明 + 原始 hex
  A8        valid 语义不变（虚拟表依赖）；`dlt645_sim` 既有套件另跑
  A9        GUI 链路（DLT645GuiParser）非空 + 「校验和」行映射到 CS 字节 total_len-2
  +  单一来源/不变式守卫：check_frame 语义不变、check_structure 不含 CS、
     calc_checksum 唯一实现、R7 行名含「校验和」、结果行元组形状、Web 侧接线

直接运行: python test/test_dlt645_tolerant_parse.py
"""

import _path_setup  # noqa: E402,F401

import sys
from pathlib import Path

from dlt645_frame_gen import DLT645FrameGenerator  # noqa: E402
from dlt645_parser import DLT645Parser  # noqa: E402
import protocol_registry  # noqa: E402

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


GEN = DLT645FrameGenerator()
ADDR = "000000000001"
# 电压块读应答：DI=02E60101（光伏扩展协议变量类）+ 3×2 字节 BCD 电压
GOOD = GEN.build_frame(ADDR, 0x91, bytes.fromhex("0101E602") + b"\x00" * 6)


def _re_cs(frame: bytes) -> bytes:
    """重算 CS（用于构造「仅长度/结构不符」的帧，隔离出单一变量）"""
    b = bytearray(frame)
    b[-2] = sum(b[0:-2]) & 0xFF
    return bytes(b)


BAD_CS = bytes(bytearray(GOOD)[:-2] + bytes([(GOOD[-2] + 1) & 0xFF]) + bytes([GOOD[-1]]))

LEN_MISMATCH = _re_cs(bytes(bytearray(GOOD)[:9] + bytes([0x0C]) + bytearray(GOOD)[10:]))

STRUCT_B1 = _re_cs(bytes(bytearray(GOOD)[:7] + bytes([0x67]) + bytearray(GOOD)[8:]))
STRUCT_B0 = _re_cs(bytes(bytearray(GOOD)[:0] + bytes([0x69]) + bytearray(GOOD)[1:]))
STRUCT_END = _re_cs(bytes(bytearray(GOOD)[:-1] + bytes([0x17])))

# 改动前基线（HEAD 版本实测输出，合法帧 13 行；A4 逐行快照）
LEGAL_SNAPSHOT = [
    ('帧起始符 1', '68H', '起始符'),
    ('从站地址', '000000000001', '表地址，BCD编码，低位在前'),
    ('帧起始符 2', '68H', '起始符'),
    ('控制码', '91H', '从站应答 | 读数据应答'),
    ('数据长度', '10 字节', '数据域字节数'),
    ('数据标识 DI', '02E60101', '光伏逆变器1的电压数据块'),
    ('  └ 数据块', '', '光伏逆变器1的电压数据块',
     '光伏协议转换单元 DL/T645-2007 扩展协议（变量类）；DI0=01：光伏逆变器1；'
     '数据长度列 222，数据格式 XXX.XXXX.XXXX.X'),
    ('  └ A相电压', '0000', '0.0', 'BCD 低字节在前，格式 XXX.X（2 字节）'),
    ('  └ B相电压', '0000', '0.0', 'BCD 低字节在前，格式 XXX.X（2 字节）'),
    ('  └ C相电压', '0000', '0.0', 'BCD 低字节在前，格式 XXX.X（2 字节）'),
    ('数据内容(原始)', '000000000000', '减33H后原始数据（备查）'),
    ('校验和', '54H', 'CS校验'),
    ('帧结束符', '16H', '结束符'),
]


def rows_containing(result, keyword):
    """所有「字段名含 keyword」的行（3/4 元组通用）"""
    return [r for r in (result.get("fields") or []) if keyword in str(r[0])]


def row_text(row):
    return " | ".join(str(x) for x in row)


# ═══════════════════════════════════════════════════════════════
# A1/A2/A3：CS 错帧仍完整解析 + 提示正确校验和
# ═══════════════════════════════════════════════════════════════

def test_cs_error_parses_fully():
    print("\n[1] A1/A2/A3 CS 错帧：完整解析 + 正确校验和提示")
    r = DLT645Parser.parse(BAD_CS)
    fields = r["fields"]
    check("A1 fields 非空（不再返回空白结果）", len(fields) > 0, f"字段数={len(fields)}")
    check("A1 业务字段齐全：数据标识 DI = 02E60101",
          any(row[0] == "数据标识 DI" and row[1] == "02E60101" for row in fields),
          str([x for x in fields if x[0] == "数据标识 DI"]))
    check("A1 深度解析行齐全：光伏逆变器1的电压数据块",
          any("光伏逆变器1的电压数据块" in row_text(row) for row in fields))
    check("A1 A/B/C 相电压行齐全",
          all(any(f"  └ {p}相电压" == row[0] for row in fields) for p in "ABC"),
          str([row[0] for row in fields]))
    check("A1 行数 = 合法帧 13 行 + 1 条校验提示",
          len(fields) == len(LEGAL_SNAPSHOT) + 1, f"实际 {len(fields)}")
    check("A1 di_code / di_desc 已解析",
          r.get("di_code") == "02E60101" and r.get("di_desc") == "光伏逆变器1的电压数据块",
          f"{r.get('di_code')} / {r.get('di_desc')!r}")

    warn = rows_containing(r, "校验和错误")
    check("A2 出现「⚠ 校验和错误」行", len(warn) == 1, str(warn))
    if warn:
        txt = row_text(warn[0])
        check("A2 行内给出帧内值（55H）", "55H" in txt, txt)
        check("A2 行内给出正确值（应为 54H）", "应为 54H" in txt, txt)
        check("A2 行内含计算规则（起始符 68H 到数据域最后 1 字节的算术和 & 0xFF）",
              "起始符 68H 到数据域最后 1 字节的算术和 & 0xFF" in txt, txt)
        check("A2 行名以 ⚠ 开头（醒目提示）", str(warn[0][0]).startswith("⚠"), str(warn[0][0]))
    check("A2 提示行位于业务字段之前",
          fields.index(warn[0]) < [i for i, row in enumerate(fields)
                                   if row[0] == "数据标识 DI"][0], str(fields))

    check("A3 valid is False（语义未变）", r.get("valid") is False, repr(r.get("valid")))
    check("A3 checksum_valid is False", r.get("checksum_valid") is False, repr(r.get("checksum_valid")))
    check("A3 checksum = 帧内值 0x55", r.get("checksum") == BAD_CS[-2], repr(r.get("checksum")))
    check("A3 checksum_expected = 计算值 0x54",
          r.get("checksum_expected") == DLT645Parser.calc_checksum(BAD_CS) == 0x54,
          repr(r.get("checksum_expected")))
    check("A3 checksum_expected == calc_checksum(frame)（同一来源）",
          r.get("checksum_expected") == DLT645Parser.calc_checksum(BAD_CS))
    check("A3 error 文案含期望/实际值",
          "0x54" in (r.get("error") or "") and "0x55" in (r.get("error") or ""),
          repr(r.get("error")))
    check("A2/A3 校验和字段行同时给出应为值",
          all(rows_containing(r, "校验和")), str(rows_containing(r, "校验和")))
    cs_rows = [row for row in rows_containing(r, "校验和") if row[0] == "校验和"]
    check("校验和行（字段级）显示应为 54H（帧内值错误）",
          cs_rows and "应为 54H" in row_text(cs_rows[0]), str(cs_rows))


# ═══════════════════════════════════════════════════════════════
# A4：合法帧逐行一致
# ═══════════════════════════════════════════════════════════════

def test_legal_frame_unchanged():
    print("\n[2] A4 合法帧与改动前逐行一致")
    r = DLT645Parser.parse(GOOD)
    check("A4 valid True", r.get("valid") is True, repr(r.get("valid")))
    check("A4 字段数 = 13（无新增行）", len(r["fields"]) == 13, f"实际 {len(r['fields'])}")
    check("A4 与基线快照逐行完全一致", r["fields"] == LEGAL_SNAPSHOT,
          "\n".join(f"     旧 {a}\n     新 {b}"
                    for a, b in zip(LEGAL_SNAPSHOT, r["fields"]) if a != b))
    check("A4 无 ⚠/❌ 提示行",
          not any(str(row[0]).startswith(("⚠", "❌")) for row in r["fields"]),
          str([row[0] for row in r["fields"]]))
    check("A4 校验和行保持原文案（CS校验）", r["fields"][11] == ('校验和', '54H', 'CS校验'),
          str(r["fields"][11]))
    check("A4 帧结束符行保持原文案（结束符）", r["fields"][12] == ('帧结束符', '16H', '结束符'),
          str(r["fields"][12]))
    check("A4 checksum_valid True", r.get("checksum_valid") is True)
    check("A4 structure_valid True / structure_error 空",
          r.get("structure_valid") is True and r.get("structure_error") == "",
          f"{r.get('structure_valid')} / {r.get('structure_error')!r}")
    check("A4 合法帧不新增 error 键（与改动前键集一致）", "error" not in r, str(sorted(r.keys())))


# ═══════════════════════════════════════════════════════════════
# A5：数据长度声明不符
# ═══════════════════════════════════════════════════════════════

def test_length_mismatch():
    print("\n[3] A5 数据长度声明不符：仍完整解析 + 应声明 N 字节")
    r = DLT645Parser.parse(LEN_MISMATCH)
    fields = r["fields"]
    check("A5 fields 非空", len(fields) > 0, f"字段数={len(fields)}")
    check("A5 业务字段齐全（DI + 深度解析行）",
          any(row[0] == "数据标识 DI" and row[1] == "02E60101" for row in fields)
          and any("光伏逆变器1的电压数据块" in row_text(row) for row in fields))
    row = rows_containing(r, "数据长度错误")
    check("A5 出现「⚠ 数据长度错误」行", len(row) == 1, str(row))
    check("A5 提示含「应声明 10 字节」",
          row and "应声明 10 字节" in row_text(row[0]), row_text(row[0]) if row else "")
    check("A5 valid False（长度不符仍判无效）", r.get("valid") is False, repr(r.get("valid")))
    check("A5 data_length_mismatch True", r.get("data_length_mismatch") is True)
    check("A5 checksum 正确时不追加校验和错误行",
          r.get("checksum_valid") is True and not rows_containing(r, "校验和错误"),
          f"checksum_valid={r.get('checksum_valid')}")


# ═══════════════════════════════════════════════════════════════
# A6：结构不符（第 1/8 字节、末字节）
# ═══════════════════════════════════════════════════════════════

def test_structure_error():
    print("\n[4] A6 帧结构不符：仍解析 + ❌ 帧结构错误指明具体字节")
    for tag, frame, must in (("第 8 字节 0x67", STRUCT_B1, ("第 8 字节", "67H")),
                             ("第 1 字节 0x69", STRUCT_B0, ("第 1 字节", "69H")),
                             ("末字节 0x17", STRUCT_END, ("16H", "17H"))):
        r = DLT645Parser.parse(frame)
        fields = r["fields"]
        check(f"A6[{tag}] fields 非空", len(fields) > 0, f"字段数={len(fields)}")
        check(f"A6[{tag}] 仍解析出业务字段（DI + 深度解析行）",
              any(row[0] == "数据标识 DI" and row[1] == "02E60101" for row in fields)
              and any("光伏逆变器1的电压数据块" in row_text(row) for row in fields),
              str([row[0] for row in fields])[:120])
        err = rows_containing(r, "帧结构错误")
        check(f"A6[{tag}] 出现「❌ 帧结构错误」行", len(err) == 1, str(err))
        if err:
            txt = row_text(err[0])
            check(f"A6[{tag}] 指明具体字节 {must}", all(m in txt for m in must), txt)
            check(f"A6[{tag}] 说明「字段归属可能不准」", "字段归属可能不准" in txt, txt)
        check(f"A6[{tag}] structure_valid False / structure_error 非空",
              r.get("structure_valid") is False and r.get("structure_error"),
              f"{r.get('structure_valid')} / {r.get('structure_error')!r}")
        check(f"A6[{tag}] valid False", r.get("valid") is False, repr(r.get("valid")))
        check(f"A6[{tag}] structure_error 与提示行同源",
              str(r.get("structure_error") or "") in row_text(err[0]) if err else False,
              str(err))
    r = DLT645Parser.parse(STRUCT_END)
    check("A6 末字节错误时「帧结束符」行给出实际值",
          any(row[0] == "帧结束符" and "17H" in row_text(row) for row in r["fields"]),
          str(rows_containing(r, "帧结束符")))


# ═══════════════════════════════════════════════════════════════

def test_short_frame():
    print("\n[5] A7 帧长 <12：不抛异常 + 帧长不足说明 + 原始 hex")
    for tag, frame in (("8 字节", GOOD[:8]), ("0 字节", b""), ("1 字节", b"\x68"),
                       ("11 字节", GOOD[:11])):
        try:
            r = DLT645Parser.parse(frame)
        except Exception as e:  # noqa: BLE001
            check(f"A7[{tag}] 不抛异常", False, f"{type(e).__name__}: {e}")
            continue
        check(f"A7[{tag}] 不抛异常", True)
        fields = r["fields"]
        check(f"A7[{tag}] 给出帧长不足说明", any("帧长度不足" in row_text(row) for row in fields),
              str(fields))
        check(f"A7[{tag}] 给出原始 hex 行",
              any(row[0] == "原始数据" and row[1] == frame.hex().upper() for row in fields),
              str(fields))
        check(f"A7[{tag}] valid False", r.get("valid") is False)
        check(f"A7[{tag}] structure_valid False 且原因说明帧长",
              r.get("structure_valid") is False and "帧长度不足 12 字节" in (r.get("structure_error") or ""),
              repr(r.get("structure_error")))
        check(f"A7[{tag}] error 与 structure_error 同源（单一来源文案）",
              str(r.get("structure_error") or "") in str(r.get("error") or "")
              and "最短帧" in str(r.get("error") or ""), repr(r.get("error")))


# ═══════════════════════════════════════════════════════════════
# A8：valid 语义不变 + 虚拟表不回归
# ═══════════════════════════════════════════════════════════════

def test_valid_semantics_and_sim():
    print("\n[6] A8 valid 语义不变（结构 OK + 校验 OK + 长度相符）")
    cases = [
        ("合法帧", GOOD, True, True, True),
        ("CS 错", BAD_CS, True, False, False),
        ("长度不符（CS 正确）", LEN_MISMATCH, True, True, False),
        ("结构错（CS 正确）", STRUCT_B1, False, True, False),
        ("结构错 + CS 错", bytes(bytearray(STRUCT_B1)[:-2] + bytes([0x00]) + bytes([STRUCT_B1[-1]])),
         False, False, False),
    ]
    for tag, frame, want_struct, want_cs, want_valid in cases:
        r = DLT645Parser.parse(frame)
        check(f"A8[{tag}] structure_valid={want_struct}", r.get("structure_valid") is want_struct,
              repr(r.get("structure_valid")))
        check(f"A8[{tag}] checksum_valid={want_cs}", r.get("checksum_valid") is want_cs,
              repr(r.get("checksum_valid")))
        check(f"A8[{tag}] valid={want_valid}（三者与运算，语义不变）",
              r.get("valid") is want_valid, repr(r.get("valid")))
        check(f"A8[{tag}] valid == structure_valid and checksum_valid and not mismatch",
              r.get("valid") == bool(r.get("structure_valid") and r.get("checksum_valid")
                                     and not r.get("data_length_mismatch")))

    check("A8 check_frame 语义不变（合法 True / CS 错 False / 结构错 False）",
          DLT645Parser.check_frame(GOOD) is True
          and DLT645Parser.check_frame(BAD_CS) is False
          and DLT645Parser.check_frame(STRUCT_B1) is False
          and DLT645Parser.check_frame(GOOD[:8]) is False)

    # 虚拟表：主站坏 CS 帧不应让引擎抛异常（引擎用 parsed['valid'] 判定，语义不变）
    from dlt645_sim import DLT645MeterSim
    from dlt645_frame_gen import encode_di
    sim = DLT645MeterSim(address=ADDR)
    req = GEN.build_frame(ADDR, GEN.build_control(0x11, dir_bit=0), encode_di("00010000"))
    bad_req = bytes(bytearray(req)[:-2] + bytes([(req[-2] + 1) & 0xFF]) + bytes([req[-1]]))
    parsed_bad = DLT645Parser.parse(bad_req)
    check("A8 虚拟表输入：坏 CS 主站帧 valid False（引擎据此判无效）",
          parsed_bad.get("valid") is False, repr(parsed_bad.get("valid")))
    try:
        sim.handle_frame(bad_req)
        check("A8 虚拟表输入：引擎不抛异常", True)
    except Exception as e:  # noqa: BLE001
        check("A8 虚拟表输入：引擎不抛异常", False, f"{type(e).__name__}: {e}")
    resp = sim.handle_frame(req)
    check("A8 虚拟表输入：合法帧仍正常应答", len(resp) == 1 and resp[0][-1] == 0x16, str(resp))


# ═══════════════════════════════════════════════════════════════
# A9：GUI 链路（DLT645GuiParser）
# ═══════════════════════════════════════════════════════════════

def test_gui_wrapper():
    print("\n[7] A9 GUI/Web 链路：非空表 + 「校验和」行映射到 CS 字节")
    gui = protocol_registry.build_gui_parser(6, DLT645Parser())
    table = gui.parse_to_table(BAD_CS)
    check("A9 parse_to_table 非空", len(table) > 0, f"行数={len(table)}")
    check("A9 表内保留业务字段", any(row[0] == "数据标识 DI" for row in table)
          and any("A相电压" in row[0] for row in table), str([r[0] for r in table])[:150])
    total_len = 10 + GOOD[9] + 2
    warn_rows = [row for row in table if "校验和错误" in row[0]]
    check("A9 「⚠ 校验和错误」行进入表格", len(warn_rows) == 1, str(warn_rows))
    if warn_rows:
        row = warn_rows[0]
        check("A9 该行字节区间落在 CS 字节（total_len-2）",
              row[4] == total_len - 2 and row[5] == total_len - 2, f"{row[4]}~{row[5]}")
        check("A9 解析值列为「应为 54H」", row[2] == "应为 54H", repr(row[2]))
    cs_rows = [row for row in table if row[0] == "校验和"]
    check("A9 校验和字段行同样映射到 CS 字节",
          cs_rows and cs_rows[0][4] == total_len - 2 and cs_rows[0][5] == total_len - 2,
          str(cs_rows))
    check("A9 表内每行 6 列（GUI/Web 同一形状）", all(len(row) == 6 for row in table),
          str([len(r) for r in table]))

    # 结构错帧同样能出表（路由不依赖 CS）
    table2 = gui.parse_to_table(STRUCT_B1)
    check("A9 结构错帧同样返回非空表", len(table2) > 0 and any("帧结构错误" in r[0] for r in table2),
          str([r[0] for r in table2])[:120])

    # Web 侧接线守卫（同一份 fields 的行名映射，改行名会失效 → 由源码守卫钉住）
    web_src = (Path(__file__).resolve().parent.parent
               / "reflex_web" / "reflex_web" / "reflex_web.py").read_text(encoding="utf-8")
    check("A9 Web 侧仍按「校验和」子串映射到 total_len-2",
          'elif "校验和" in field:' in web_src
          and "byte_start, byte_end = total_len - 2, total_len - 2" in web_src)
    check("A9 Web 侧仍消费同一份 fields",
          'dlt645_result.get("fields", [])' in web_src)


# ═══════════════════════════════════════════════════════════════
# 单一来源 / 不变式守卫（防回退与漂移）
# ═══════════════════════════════════════════════════════════════

def test_invariants():
    print("\n[8] 不变式守卫：判据拆分 / 行名契约 / 元组形状 / R7")
    check("守卫 check_structure 不含 CS（合法与 CS 错帧同为结构 OK）",
          DLT645Parser.check_structure(GOOD) == (True, "")
          and DLT645Parser.check_structure(BAD_CS) == (True, ""),
          f"{DLT645Parser.check_structure(GOOD)} / {DLT645Parser.check_structure(BAD_CS)}")
    ok, why = DLT645Parser.check_structure(STRUCT_END)
    check("守卫 check_structure 结构错时给中文原因", ok is False and "16H" in why, why)
    check("守卫 calc_checksum 与既有公式一致（sum(data[0:-2]) & 0xFF）",
          all(DLT645Parser.calc_checksum(f) == (sum(f[0:-2]) & 0xFF)
              for f in (GOOD, BAD_CS, LEN_MISMATCH, STRUCT_B1, STRUCT_END)))
    src = (Path(__file__).resolve().parent.parent / "dlt645_parser.py").read_text(encoding="utf-8")
    check("守卫 parse 内不再有「无效的DLT645帧格式」提前 return",
          "无效的DLT645帧格式" not in src)
    check("守卫 提示行名含「校验和」（R7，GUI 偏移映射依赖）",
          any("校验和" in row[0] for row in DLT645Parser.parse(BAD_CS)["fields"])
          and any("校验和" in row[0] for row in DLT645Parser.parse(BAD_CS)["fields"]
                  if str(row[0]).startswith("⚠")))
    for tag, frame in (("合法", GOOD), ("CS 错", BAD_CS), ("长度不符", LEN_MISMATCH),
                       ("结构错", STRUCT_B1), ("短帧", GOOD[:8])):
        rows = DLT645Parser.parse(frame)["fields"]
        check(f"守卫[{tag}] 字段行均为 3/4 元组且元素为 str（GUI/Web 通用形状）",
              all(isinstance(row, tuple) and len(row) in (3, 4)
                  and all(isinstance(x, str) for x in row) for row in rows),
              str([row for row in rows if not (isinstance(row, tuple) and len(row) in (3, 4))]))
    r = DLT645Parser.parse(BAD_CS)
    check("守卫 新增结果字段齐备（checksum_expected/structure_valid/structure_error）",
          set(("checksum_expected", "structure_valid", "structure_error")) <= set(r.keys()),
          str(sorted(r.keys())))
    for tag, frame in (("合法", GOOD), ("CS 错", BAD_CS), ("长度不符", LEN_MISMATCH),
                       ("结构错", STRUCT_B1)):
        rr = DLT645Parser.parse(frame)
        check(f"守卫[{tag}] checksum_expected 恒为计算值",
              rr.get("checksum_expected") == DLT645Parser.calc_checksum(frame))
    # 非 CS 类输入回归：不因本次改动而丢失既有深度解析路径
    check("守卫 合法帧深度解析行数不变（4 行 └）",
          sum(1 for row in DLT645Parser.parse(GOOD)["fields"] if str(row[0]).startswith("  └")) == 4)


def main():
    print("=" * 74)
    print("协议6 容错解析测试（校验和/长度/结构不符时仍继续解析并提示正确值）")
    print("=" * 74)
    test_cs_error_parses_fully()
    test_legal_frame_unchanged()
    test_length_mismatch()
    test_structure_error()
    test_short_frame()
    test_valid_semantics_and_sim()
    test_gui_wrapper()
    test_invariants()
    print()
    print("=" * 74)
    if FAILURES:
        print(f"✗ 失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for name in FAILURES:
            print(f"   - {name}")
        sys.exit(1)
    print(f"✓ 全部通过：{PASS} 项")
    print("=" * 74)


if __name__ == "__main__":
    main()
