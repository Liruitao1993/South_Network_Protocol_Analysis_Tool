# -*- coding: utf-8 -*-
"""协议11（HDC 1.0）跨字节位域的**表格呈现**回归：bit 占用与拼装关系

背景（用户 2026-10-12 报障）：`报文头长度` 被解析成 33（表格显示 33×4B=132B），
正确应为 **6**。根因是该字段的**跨字节拼装方向取反了**：它与本协议其它跨字节位域
（12bit「转发数据长度/配置值」、MAC 头 MSDU 长度、事件 0x008 的功能码…）一样是
「**字节号小的段为低位段**」（口径同 `_bits_lsb`），只有它一家被写成「字节0 存高 2 位」：

    报文头字节0[bit7-6] = 报文头长度 **低** 2 位（同字节 bit0-5 是协议版本号）
    报文头字节1[bit3-0] = 报文头长度 **高** 4 位（同字节 bit4-7 是该报文自有语义）
    值 = (字节1[bit3-0] << 2) | 字节0[bit7-6]，单位 **字节**（值即报文头字节数）

证据（四处互证）：
  1. 协议10 同字段同口径（`gw_new_gen_cmd_payloads._parse_comm_test`）：真实帧
     `81 61 20 00 00 00` 的 `报文头长度` = 6，且该载荷**恰好 6 字节**即整根报文头
     （`test/test_gw_ext_cmd.py` T13 的注释与断言）；
  2. 本协议 0x0A1 真实帧 `01 53` → 12 字节头（与实测 DATA 自字节 12 起自洽）；
  3. 表2 扩展命令的报文头就是字节0~5 = 6 字节，用户报障帧 `81 C1` → 6；
  4. 旧口径与「值=字节数」只在**字节0 bit7-6 == 0** 时数值相同（此时
     4×lowNibble == (lowNibble<<2)），所以此前拿 `01 53` / `01 61` / `01 02` 校准
     都看不出问题 —— 用户帧的字节0 = 0x81（bit7-6 = 0b10）才把它暴露出来。

现口径：**原始值列**给两个位段的二进制（`0b0001+0b10`，`+` = 按位拼接，可直接读为
数值）；**说明列**给字节/比特归属 + 移位拼装式（`0b10 | 0b0001<<2 = 6`）与单位
（字节）；相邻位域字段的说明列追加「位域归属」（`报文头字节1[bit7-4]=4bit=0b0110`）。

覆盖：
  [1] 报障帧（1.23.73 的 152 字节台体帧）：`报文头长度` 位域渲染 = 4 字节头
  [2] 用户报障帧 `81 C1 …` → 6 字节（旧口径给出 33）；位序反证
  [3] 说明里的拼装式可反解，且**恒等于**解析值（N 字节）
  [4] 三类产出该字段的报文（抄表/通信测试/升级状态）口径一致（同一 helper）
  [5] 相邻位域字段的「位域归属」；且不得改动被判定的原始值/解析值语义
      （`_extract_test_mode_content` 靠「非数值者即名称」探测，改动即摘要退化）
  [6] 真实夹具：出现该行的帧逐一反解自洽，未出现的帧不得凭空多出该行
  [7] 与协议10 同字段对拍（同字节 → 同值）+「值 = 报文头字节数」锚定
"""

import _path_setup  # noqa: E402,F401

import os
import pickle
import re
import sys

from gw_new_gen_cmd_payloads import _parse_comm_test as gw_parse_comm_test
from hdc10_parser import HDC10Parser

# ── 报障帧（台体日志，152 字节；前 45 字节为报文内容，其余 0 填充）──
REPORTED = bytes.fromhex(
    "".join("""
    01 00 00 00 00 F0 FF FE 63 11 26 42 00 00 00 00
    C0 00 00 FF 1F 00 01 00 30 08 00 FF 00 00 01 00
    00 11 06 00 00 01 61 10 00 C5 0F 88 0D
    """.split())
) + bytes(152 - 45)

# ── 用户 2026-10-12 报障帧的报文头（协议11 + 级别「FC+PB解析(完整MPDU)」）──
# 报文头 = 81 C1 40 02 2? 32：测试模式12 / MCS值36 / PHR_MCS 2 / PSDU_MCS 2 /
# PbSIZE 3；字节0 = 0x81 → 报文头长度低 2 位 = 0b10、字节1 = 0xC1 → 高 4 位 = 0b0001
USER_HDR = bytes([0x81, 0xC1, 0x40, 0x02, 0x22, 0x32])

PICKLE = os.path.join(os.path.dirname(__file__), "hdc10_real_frames.pkl")
FAILURES = []
PASS = 0


def _safe(text):
    """控制台 GBK 编不出的字符（如 ⚠）换成 ?，避免失败明细自己把测试带崩。"""
    out = []
    for ch in str(text):
        try:
            ch.encode("gbk")
        except UnicodeEncodeError:
            out.append("?")
        else:
            out.append(ch)
    return "".join(out)


def check(name, cond, detail=""):
    global PASS
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {_safe(detail)}" if detail and not cond else ""))
    if cond:
        PASS += 1
    else:
        FAILURES.append(name)


def section(title):
    print(f"\n── {title} " + "─" * max(0, 52 - len(title)))


def rows_of(frame, level):
    return HDC10Parser().parse_to_table(frame, parse_level=level)


def find(rows, name):
    for r in rows:
        if str(r[0]).strip() == name:
            return r
    return None


def cell(rows, name, idx):
    r = find(rows, name)
    return None if r is None else str(r[idx])


def hdr_row(rows):
    """取「报文头长度」行（表内字段名带不定长缩进，故按去缩进名匹配）。"""
    return find(rows, "报文头长度")


def want_hdr(b0, b1):
    """规范口径：字节1 的 bit3-0 是高 4 位、字节0 的 bit7-6 是低 2 位。"""
    return ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)


def decode_raw(raw_cell):
    """把原始值列的位段拼装式反解成整数（`0b0001+0b10` → 0b000110 = 6）。"""
    bits = "".join(re.findall(r"0b([01]+)", raw_cell))
    if not bits:
        return None
    return int(bits, 2)


def decode_note(desc_cell):
    """反解说明列的移位拼装式（`→ 0b10 | 0b0001<<2 = 6`）→ (算得值, 声明值)。"""
    m = re.search(r"→\s*(.*?)\s*=\s*(\d+)", desc_cell)
    if not m:
        return None, None
    expr = sum(int(v, 2) << int(s or 0)
               for v, s in re.findall(r"0b([01]+)(?:<<(\d+))?", m.group(1)))
    return expr, int(m.group(2))


def parsed_n(parsed_cell):
    """从解析值 `N字节` 取 N。"""
    m = re.fullmatch(r"(\d+)字节", parsed_cell)
    return int(m.group(1)) if m else None


def build_meter(b0, b1, msg_id=0x001):
    return bytes([b0, b1, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00]), msg_id


def build_upgrade(b0, b1):
    return bytes([b0, b1, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
                  0x00, 0x00, 0x00, 0x00])


def main():
    p = HDC10Parser()

    # ── [1] 报障帧的位域渲染 ──────────────────────────────────
    section("[1] 报障帧：报文头长度 位域渲染（4 字节头）")
    check("夹具：前 45 字节为报文内容、其余 0 填充",
          len(REPORTED) == 152 and set(REPORTED[45:]) == {0})
    check("夹具：字节37=0x01（bit7-6=0b00）、字节38=0x61（bit3-0=0b0001）",
          REPORTED[37] == 0x01 and REPORTED[38] == 0x61,
          f"{REPORTED[37]:02X} {REPORTED[38]:02X}")
    rows = rows_of(REPORTED, "fc_pb")
    check("报文头长度 行存在", hdr_row(rows) is not None)
    check("原始值 = 两段按值序拼装 0b0001+0b00（高 4 位来自字节1）",
          cell(rows, "报文头长度", 1) == "0b0001+0b00",
          cell(rows, "报文头长度", 1))
    note = cell(rows, "报文头长度", 3) or ""
    check("说明写明低 2 位在字节0 bit7-6",
          "报文头字节0[bit7-6]=2bit=0b00" in note, note)
    check("说明写明高 4 位在字节1 bit3-0",
          "报文头字节1[bit3-0]=4bit=0b0001" in note, note)
    check("说明给出移位拼装式（低位段在前）0b00 | 0b0001<<2 = 4",
          "0b00 | 0b0001<<2 = 4" in note, note)
    check("说明给出单位口径（字节，值 = 报文头字节数）",
          "单位 字节，报文头长度 = 4 字节" in note, note)
    check("解析值 = 4字节（不再是 1×4B=4B）",
          cell(rows, "报文头长度", 2) == "4字节", cell(rows, "报文头长度", 2))
    check("偏移列仍高亮字节37-38（跨字节区间）",
          (hdr_row(rows)[4], hdr_row(rows)[5]) == (37, 38),
          str((hdr_row(rows)[4], hdr_row(rows)[5])))
    check("auto 与 fc_pb 渲染一致",
          [tuple(map(str, r)) for r in rows_of(REPORTED, "auto")]
          == [tuple(map(str, r)) for r in rows])

    # ── [2] 用户报障帧 + 位序反证 ─────────────────────────────
    section("[2] 用户报障帧 81 C1 → 6 字节（旧口径给出 33）；位序反证")
    rows_u = p._parse_comm_test(USER_HDR, 0)
    check("解析值 = 6字节", cell(rows_u, "报文头长度", 2) == "6字节",
          cell(rows_u, "报文头长度", 2))
    check("原始值 = 0b0001+0b10",
          cell(rows_u, "报文头长度", 1) == "0b0001+0b10",
          cell(rows_u, "报文头长度", 1))
    check("说明拼装式 0b10 | 0b0001<<2 = 6",
          "0b10 | 0b0001<<2 = 6" in (cell(rows_u, "报文头长度", 3) or ""),
          cell(rows_u, "报文头长度", 3))
    old_way = (((USER_HDR[0] >> 6) & 0x03) << 4) | (USER_HDR[1] & 0x0F)
    check("反证：旧口径（字节0 当高 2 位）= 33 → 132B 荒谬；正解 6 ≠ 33",
          old_way == 33 and parsed_n(cell(rows_u, "报文头长度", 2)) == 6,
          f"old={old_way}")
    check("同帧其余字段不受影响（测试模式12 / MCS值36 / PHR_MCS 2 / PSDU_MCS 2 / PbSIZE 3）",
          cell(rows_u, "测试模式/配置操作", 1) == "12"
          and cell(rows_u, "MCS值", 1) == "36"
          and cell(rows_u, "PHR_MCS", 2) == "MCS 2"
          and cell(rows_u, "PSDU_MCS", 2) == "MCS 2"
          and cell(rows_u, "PbSIZE", 2) == "PbSIZE 3",
          str([(str(r[0]).strip(), r[1], r[2]) for r in rows_u[2:]]))
    check("表2 语义自洽：报文头 = 字节0~5，值 6 就是这 6 字节的字节数",
          parsed_n(cell(rows_u, "报文头长度", 2)) == len(USER_HDR))

    # 混合帧：低 2 位 ≠ 高 4 位（方向可判别：正解 14；旧口径 35；只对调段序 50）
    mix = bytes([0x81, 0x63, 0x10, 0x00])
    rows_mix = p._parse_comm_test(mix, 0)
    check("正解 14（=3<<2|2），既不是旧口径 35 也不是对调段序的 50",
          parsed_n(cell(rows_mix, "报文头长度", 2)) == 14
          and (((0x81 >> 6) << 4) | 0x03) == 35
          and (((0x63 & 0x0F) << 4) | 0x02) == 50,
          cell(rows_mix, "报文头长度", 2))
    check("原始值把两段按值序拼出 0b0011+0b10",
          cell(rows_mix, "报文头长度", 1) == "0b0011+0b10",
          cell(rows_mix, "报文头长度", 1))
    check("反解原始值 = 14（顺序钉死在字节1 为高段）",
          decode_raw(cell(rows_mix, "报文头长度", 1)) == 14,
          str(decode_raw(cell(rows_mix, "报文头长度", 1))))
    check("说明里的拼装式同为 0b10 | 0b0011<<2 = 14",
          "0b10 | 0b0011<<2 = 14" in (cell(rows_mix, "报文头长度", 3) or ""),
          cell(rows_mix, "报文头长度", 3))
    check("同字节邻居：协议版本号只取 byte0 bit5-0 = 1（不与低 2 位混）",
          cell(rows_mix, "协议版本号", 2) == "1"
          and "bit5-0" in (cell(rows_mix, "协议版本号", 3) or ""),
          cell(rows_mix, "协议版本号", 3))
    check("同字节邻居：测试模式/配置操作只取 byte1 bit7-4 = 6",
          cell(rows_mix, "测试模式/配置操作", 1) == "6"
          and "bit7-4" in (cell(rows_mix, "测试模式/配置操作", 3) or ""),
          cell(rows_mix, "测试模式/配置操作", 3))

    # ── [3] 渲染自洽：取值表 × 反解恒等 ─────────────────────────
    section("[3] 渲染自洽：说明/原始值反解 = 解析值 = (b1&0xF)<<2|(b0>>6)")
    cases = [(0x01, 0x61), (0x81, 0xC1), (0x81, 0x63), (0xC1, 0x6F),
             (0x41, 0x60), (0xFF, 0x7F), (0x3F, 0x40), (0x80, 0x41),
             (0xFE, 0x6E), (0xBF, 0xF3)]
    bad = []
    for b0, b1 in cases:
        data = bytes([b0, b1, 0x10, 0x00])
        r = p._parse_comm_test(data, 0)
        row = hdr_row(r)
        want = want_hdr(b0, b1)
        n = parsed_n(cell(r, "报文头长度", 2))
        raw_v = decode_raw(row[1])
        expr, declared = decode_note(str(row[3]))
        if not (n == want and raw_v == want and expr == want == declared
                and row[1] == f"0b{(b1 & 0x0F):04b}+0b{(b0 >> 6):02b}"):
            bad.append(f"{b0:02X},{b1:02X}: want={want} n={n} raw={raw_v} "
                       f"expr={expr} decl={declared} cell={row[1]}")
    check(f"{len(cases)} 组取值的原始值/说明/解析值三处恒等", not bad, str(bad[:4]))
    zero = p._parse_comm_test(bytes([0x01, 0x60, 0x10, 0x00]), 0)
    check("边界：高 4 位与低 2 位同为 0 → 0字节（不虚报长度）",
          parsed_n(cell(zero, "报文头长度", 2)) == 0
          and decode_raw(cell(zero, "报文头长度", 1)) == 0,
          cell(zero, "报文头长度", 2))

    # ── [4] 三类报文的口径一致（同一 helper）────────────────────
    section("[4] 产出该字段的三类报文口径一致")
    meter_bytes, msg_id = build_meter(0x41, 0x62)
    rows_meter = p._parse_meter_reading(meter_bytes, 0, msg_id)
    rows_up = p._parse_upgrade(build_upgrade(0x81, 0x63), 0, 0x034)
    for label, rows_x, want_raw in (
            ("抄表 0x001", rows_meter, "0b0010+0b01"),
            ("通信测试 0x006",
             p._parse_comm_test(bytes([0x41, 0x62, 0x10, 0x00]), 0), "0b0010+0b01"),
            ("升级状态 0x034", rows_up, "0b0011+0b10")):
        row = hdr_row(rows_x)
        ok = (row is not None and row[1] == want_raw
              and decode_raw(row[1]) == decode_note(str(row[3]))[0]
              == parsed_n(cell(rows_x, "报文头长度", 2)))
        check(f"{label}：位域渲染与解析值自洽", ok,
              f"{None if row is None else (row[1], cell(rows_x, '报文头长度', 2))}")
    check("升级状态 0x034 的解析值也补成 N字节（原先只给裸数字）",
          cell(rows_up, "报文头长度", 2) == "14字节",
          cell(rows_up, "报文头长度", 2))

    # ── [5] 相邻位域字段的「位域归属」+ 摘要语义不变 ─────────────
    section("[5] 相邻位域字段的位域归属（不得动被判定的槽位）")
    r5 = p._parse_comm_test(bytes([0x01, 0x61, 0x10, 0x00]), 0)
    check("协议版本号 说明带 bit5-0 归属",
          "报文头字节0[bit5-0]=6bit=0b000001" in (cell(r5, "协议版本号", 3) or ""),
          cell(r5, "协议版本号", 3))
    check("协议版本号 解析值仍为纯数值 1（摘要探测靠它）",
          cell(r5, "协议版本号", 2) == "1", cell(r5, "协议版本号", 2))
    check("测试模式/配置操作 说明带 bit7-4 归属",
          "报文头字节1[bit7-4]=4bit=0b0110" in (cell(r5, "测试模式/配置操作", 3) or ""),
          cell(r5, "测试模式/配置操作", 3))
    check("测试模式/配置操作 原始值仍为十进制 6、解析值仍为模式名",
          cell(r5, "测试模式/配置操作", 1) == "6"
          and cell(r5, "测试模式/配置操作", 2) == "频段切换操作",
          f"{cell(r5, '测试模式/配置操作', 1)} / {cell(r5, '测试模式/配置操作', 2)}")
    check("12bit 值 说明带跨字节归属与移位拼装式（byte2 为低 4 位、byte3 为高 8 位）",
          "报文头字节2[bit7-4]=4bit=0b0001 + 报文头字节3[bit7-0]=8bit=0b00000000"
          "（低位段在前）→ 0b0001 | 0b00000000<<4 = 1"
          in (cell(r5, "频段值(目标频段)", 3) or ""),
          cell(r5, "频段值(目标频段)", 3))
    check("12bit 拼装式的反解值 = 解析前算得的 12bit 值（口径同 _bits_lsb）",
          "= 1" in (cell(r5, "频段值(目标频段)", 3) or "").rsplit("→", 1)[-1],
          cell(r5, "频段值(目标频段)", 3))
    check("频段值 原始值仍为十进制 1",
          cell(r5, "频段值(目标频段)", 1) == "1",
          cell(r5, "频段值(目标频段)", 1))
    r12 = p._parse_comm_test(bytes([0x01, 0xC1, 0x70, 0x00, 0x21, 0x43]), 0)
    check("模式12：PHR_MCS 带 byte4 bit7-4 归属",
          "报文头字节4[bit7-4]=4bit=0b0010" in (cell(r12, "PHR_MCS", 3) or ""),
          cell(r12, "PHR_MCS", 3))
    check("模式12：PSDU_MCS/PbSIZE 带 byte5 归属",
          "报文头字节5[bit3-0]=4bit=0b0011" in (cell(r12, "PSDU_MCS", 3) or "")
          and "报文头字节5[bit7-4]=4bit=0b0100" in (cell(r12, "PbSIZE", 3) or ""),
          f"{cell(r12, 'PSDU_MCS', 3)} / {cell(r12, 'PbSIZE', 3)}")

    # ── [6] 真实夹具回归 ───────────────────────────────────────
    section("[6] 真实夹具：出现该行的帧逐一自洽，未出现的帧不多出该行")
    with open(PICKLE, "rb") as f:
        fixtures = pickle.load(f)
    seen = 0
    bad = []
    for fi, fb, _key in fixtures:
        rows_f = rows_of(fb, "pb_only")
        row = hdr_row(rows_f)
        if row is None:
            continue
        seen += 1
        n = parsed_n(str(row[2]))
        raw_v = decode_raw(str(row[1]))
        expr, declared = decode_note(str(row[3]))
        if not (n is not None and raw_v == n == expr == declared
                and "bit7-6" in str(row[3]) and "bit3-0" in str(row[3])):
            bad.append(f"#{fi}: {row[1]} | {row[2]} | {str(row[3])[:40]}")
    check(f"夹具 {len(fixtures)} 帧中出现「报文头长度」的行逐条反解自洽"
          f"（共 {seen} 次）", not bad, str(bad[:4]))
    check("夹具确实命中该字段（否则本项无意义）", seen > 0, str(seen))
    pairs = [(lvl, hdr_row(rows_of(REPORTED, lvl))) for lvl in ("auto", "fc_pb")]
    check("级别尊重：auto / fc_pb 两处渲染一致（同一 helper）",
          all(r is not None for _l, r in pairs)
          and len({(r[1], r[2]) for _l, r in pairs}) == 1,
          str([(lvl, None if r is None else r[1]) for lvl, r in pairs]))
    pb_slice = hdr_row(rows_of(REPORTED[16:], "pb_only"))
    check("PB 级输入（去掉 16 字节 FC）在 pb_only 下渲染一致、偏移随片段平移",
          pb_slice is not None and pb_slice[1] == "0b0001+0b00"
          and (pb_slice[4], pb_slice[5]) == (21, 22),
          None if pb_slice is None else str(tuple(pb_slice[1:6])))
    pb_in = REPORTED[16:]
    check("PB 级输入 fc_mac 与 auto 全等（位域说明不改变级别路由）",
          [tuple(map(str, r)) for r in rows_of(pb_in, "fc_mac")]
          == [tuple(map(str, r)) for r in rows_of(pb_in, "auto")])
    errs = []
    for n in (0, 1, 2, 3, 4, 5):
        for lvl in ("auto", "fc_pb", "fc_mac", "fc_only", "pb_only",
                    "mac_only", "app"):
            try:
                rows_of(bytes(n), lvl)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{lvl}({n}):{type(exc).__name__}")
    check("边界输入 0-5 字节 × 7 级别不抛异常（位域说明在短数据下不越界）",
          not errs, str(errs))

    # ── [7] 跨协议对拍 + 「值 = 报文头字节数」锚定 ────────────────
    section("[7] 与协议10 同字段对拍（同字节同值）+ 字节数锚定")

    def gw_hdr(hexs):
        for row in gw_parse_comm_test(bytes.fromhex(hexs), 0, 0):
            if str(row[0]).strip() == "报文头长度":
                return int(str(row[2]).strip())
        return None

    bad = []
    for hexs in ("816120000000", "81C140022232", "816310000000", "01613000"):
        g = gw_hdr(hexs)
        h = parsed_n(cell(p._parse_comm_test(bytes.fromhex(hexs), 0),
                          "报文头长度", 2))
        if g is None or g != h:
            bad.append(f"{hexs}: 协议10={g} 协议11={h}")
    check("协议10 / 协议11 同字节 → 同值（同一字段同一口径，防漂移）",
          not bad, str(bad))

    conf = p._parse_confirm(bytes([0x81, 0xC1] + [0] * 6), 0)
    check("值即字节数：确认帧 6 字节头 → 「报文头」行只覆盖前 6 字节",
          conf[0][2] == "6字节头" and (conf[0][4], conf[0][5]) == (0, 5),
          str(tuple(conf[0][2:6])))
    mrows = p._parse_meter_reading(bytes([0x01, 0x02, 0x30, 0x00] + [0] * 8), 0, 0x001)
    data_row = find(mrows, "数据(DATA)")
    check("值即字节数：抄表 `01 02` → 8字节头，DATA 自字节 8 起",
          cell(mrows, "报文头长度", 2) == "8字节"
          and data_row is not None and data_row[4] == 8,
          f"{cell(mrows, '报文头长度', 2)} / "
          f"{None if data_row is None else data_row[4]}")

    print("\n" + "=" * 58)
    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} 项失败: {FAILURES}")
        sys.stdout.flush()
        sys.exit(1)
    print(f"[OK] 全部 {PASS} 项检查通过")
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
