# -*- coding: utf-8 -*-
"""协议6 位域语义解析测试：主动上报状态字/模式字位表 + 电表运行状态字1~7 位号纠错

覆盖（对应任务 09-17-dlt645-report-status-word 的验收项）：
  U1  补遗三个报文示例 golden（96 位状态字，字节序自证）
  U2  用户现场帧完整解析链（DI 04001501 → Bit76 保留位；不再出现「见附录C」）
  U3  主动上报模式字（64 位；含置位与「未开启任何事件主动上报」文案）
  U4  两表条数 + 保留位集合 + R2 不变量（状态字 Bit(32+n) ≡ 模式字 Bit(n)）
  U5  状态字 1~7 逐位对拍（**独立字面量**清单一，与被测常量无关）
  U6  状态字4 = 0x0002 → A相欠压（旧实现报「A相潮流方向异常」）
  U7  状态字3 供电方式两位域（Bit2~Bit1，LSB 为 Bit1）
  U8  保留位占位：Bit8~Bit15 置位必须点名字号，未置位不进列表（避免噪声）
  U9  位表完整性：状态字 1~7 每字显式覆盖 Bit0~Bit15（防整体错位类回归）
  U10 边界：空/短数据、未知位域、名称不匹配 → 不抛异常且有兜底文案
  U11 桌面与 Web 输出逐字符一致（同一 codec 单一来源，实测断言非假设）

依据（双源）：
  - `协议文档/6.645协议/国网计量中心电能表全性能试验检测公告-第4号补遗-事件记录采集-远程费控功能和负荷曲线抄读功能.md`（96/64 位表 + 三示例）
  - `DLT645-2007.md:1658-1730`（DL/T 645-2007 附录C，状态字 1~7）

运行：python test/test_dlt645_status_word_bits.py
"""
import _path_setup  # noqa: E402,F401

from pathlib import Path  # noqa: E402

import dlt645_data_codec as codec  # noqa: E402
import dlt645_parser as dp  # noqa: E402
import protocol_registry as pr  # noqa: E402

# reflex_web/reflex_web/（源码守卫备用路径）
_ROOT_REFLEX = Path(__file__).resolve().parent.parent / "reflex_web" / "reflex_web"

PASS = 0
FAIL = 0
FAILED = []


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  ✗ {msg}")


def section(title):
    print(f"\n=== {title} ===")


def _covered_bits(table):
    """位表实际覆盖的位号集合（两位域展开为它的全部位）"""
    out = set()
    for bit, entry in table.items():
        if isinstance(entry, tuple):
            width = entry[1] if len(entry) > 1 else 1
            out.update(range(bit, bit + width))
        else:
            out.add(bit)
    return out


# ──────────────────────────────────────────────────────────────────────────
# U5 的独立期望清单：从 DL/T645-2007 附录C 原文逐位抄录（**不得从被测常量派生**，
# 否则断言恒真，抓不住「位号被改回去」这类退化）。None = 保留位。
# ──────────────────────────────────────────────────────────────────────────
EXPECTED_STATUS_BITS = {
    1: {7: None, 6: None, 5: "无功功率方向(0正向1反向)", 4: "有功功率方向(0正向1反向)",
        3: "停电抄表电池(0正常1欠压)", 2: "时钟电池(0正常1欠压)",
        1: "需量积算方式(0滑差1区间)", 0: None},
    2: {7: None, 6: "C相无功方向(0正向1反向)", 5: "B相无功方向(0正向1反向)",
        4: "A相无功方向(0正向1反向)", 3: None, 2: "C相有功方向(0正向1反向)",
        1: "B相有功方向(0正向1反向)", 0: "A相有功方向(0正向1反向)"},
    3: {7: None, 6: None, 5: None, 4: "继电器状态(0通1断)", 3: "编程允许(0禁止1许可)",
        0: "当前运行时段(0第一套1第二套)"},           # Bit2~Bit1 为两位域，U7 单独测
    4: {7: "断相", 6: "潮流方向", 5: "过载", 4: "过流", 3: "失流", 2: "过压",
        1: "欠压", 0: "失压", 8: "断流"},
    5: {7: "断相", 6: "潮流方向", 5: "过载", 4: "过流", 3: "失流", 2: "过压",
        1: "欠压", 0: "失压", 8: "断流"},
    6: {7: "断相", 6: "潮流方向", 5: "过载", 4: "过流", 3: "失流", 2: "过压",
        1: "欠压", 0: "失压", 8: "断流"},
    7: {7: None, 6: "需量超限", 5: "掉电", 4: "辅助电源失电", 3: "电流不平衡",
        2: "电压不平衡", 1: "电流逆相序", 0: "电压逆相序"},
}

# 用户现场帧（DI 04001501 读应答）：12 字节数据去 33H 后 = 00×9,10,00×2 → 置位 Bit76
FIELD_FRAME = ("68 66 51 11 07 25 20 68 91 10 34 48 33 37 33 33 33 33 33 33 33 "
               "33 33 43 33 33 DF 16").replace(" ", "")
FIELD_DATA = bytes.fromhex("00" * 9 + "10" + "00" * 2)


def main():
    # ── U1 补遗三示例 golden ──────────────────────────────────────────────
    section("U1 补遗三示例 golden（96 位状态字）")
    for raw, want, note in (
        ("01" + "00" * 11, "负荷开关误动或拒动", "示例1 首字节 01H → Bit0"),
        ("02" + "00" * 11, "ESAM错误", "示例2 首字节 02H → Bit1"),
        ("00" * 10 + "01" + "00", "编程", "示例3 字节[10] 01H → Bit80"),
    ):
        out = codec.decode_report_status_word("主动上报状态字", bytes.fromhex(raw))
        check(out is not None and want in out, f"{note} 输出含「{want}」")
    # 三示例的字节序自证：不是「高字节在前」，否则示例1 会命中 Bit88 节假日编程
    out1 = codec.decode_report_status_word("主动上报状态字", bytes.fromhex("01" + "00" * 11))
    check("节假日编程" not in out1, "示例1 不得命中 Bit88（字节序非高字节在前）")

    # ── U2 用户现场帧（完整解析链）───────────────────────────────────────
    section("U2 用户现场帧（DI 04001501）")
    result = dp.DLT645Parser().parse(bytes.fromhex(FIELD_FRAME))
    values = [f[2] for f in result["fields"] if str(f[0]) == "数据值"]
    val = values[0] if values else ""
    check(bool(val), "解析出「数据值」行")
    check("Bit76" in val, "输出点名 Bit76")
    check("保留" in val, "Bit76 标注为保留位（不臆造事件名）")
    check("见附录C" not in val, "不再出现错误出处「见附录C」")
    check("无事件" in val, "未置位已定义事件 → 明确「无事件」")
    # 与直接调用一致（完整链未做二次改写）
    check(val == codec.decode_report_status_word("主动上报状态字", FIELD_DATA),
          "解析链输出 == codec 直接输出")

    # ── U3 模式字 ───────────────────────────────────────────────────────
    section("U3 主动上报模式字（64 位）")
    out = codec.decode_report_mode_word("主动上报模式字", bytes(8))
    check(out is not None and "未开启任何事件主动上报" in out, "全 0 → 明确未使能")
    out = codec.decode_report_mode_word("主动上报模式字", bytes.fromhex("01" + "00" * 7))
    check(out is not None and "负荷开关误动或拒动" in out, "Bit0=1 → 负荷开关误动或拒动")
    out = codec.decode_report_mode_word("主动上报模式字", bytes.fromhex("00" * 7 + "80"))
    check(out is not None and "密钥更新" in out, "Bit63=1 → 密钥更新")
    # 名称不匹配（非主动上报的模式字）→ None，交由兜底处理
    check(codec.decode_report_mode_word("某模式字", bytes(8)) is None,
          "名称不含「主动上报」→ None")

    # ── U4 条数 / 保留位 / R2 不变量 ─────────────────────────────────────
    section("U4 位表结构与 R2 不变量")
    check(len(codec.REPORT_STATUS_BITS) == 96, f"状态字表 96 位（实际 {len(codec.REPORT_STATUS_BITS)}）")
    check(len(codec.REPORT_MODE_BITS) == 64, f"模式字表 64 位（实际 {len(codec.REPORT_MODE_BITS)}）")
    check(set(codec.REPORT_STATUS_BITS) == set(range(96)), "状态字表位号 0~95 无空洞")
    check(set(codec.REPORT_MODE_BITS) == set(range(64)), "模式字表位号 0~63 无空洞")
    res_status = [b for b, v in codec.REPORT_STATUS_BITS.items() if v is None]
    res_mode = [b for b, v in codec.REPORT_MODE_BITS.items() if v is None]
    check(sorted(res_status) == sorted([6] + list(range(25, 32)) + list(range(41, 48))
                                       + list(range(57, 64)) + list(range(75, 80))),
          f"状态字保留位集合与文档一致（实际 {sorted(res_status)}）")
    check(sorted(res_mode) == sorted([6] + list(range(25, 32)) + list(range(43, 48))),
          f"模式字保留位集合与文档一致（实际 {sorted(res_mode)}）")
    # R2：两表新增段同源 —— n=32..63 逐位相等（独立双源互证）
    mismatch = [n for n in range(32, 64)
                if codec.REPORT_STATUS_BITS.get(32 + n) != codec.REPORT_MODE_BITS.get(n)]
    check(not mismatch, f"不变量 状态字Bit(32+n) ≡ 模式字Bit(n)（n=32..63）不一致位={mismatch}")

    # ── U5 状态字 1~7 逐位对拍（独立字面量）──────────────────────────────
    section("U5 状态字 1~7 逐位对拍（附录C 独立清单）")
    for word_no, expected in EXPECTED_STATUS_BITS.items():
        for bit, name in expected.items():
            actual = codec.STATUS_WORD_BITS[word_no].get(bit, "<<缺失>>")
            check(actual == name,
                  f"状态字{word_no} Bit{bit}: 期望 {name!r}，实际 {actual!r}")
    # 反向：被测表不得含期望清单之外的「非保留」位（防错位残留）
    for word_no in EXPECTED_STATUS_BITS:
        allowed = set(EXPECTED_STATUS_BITS[word_no]) | ({1, 2} if word_no == 3 else set())
        extra = {b: v for b, v in codec.STATUS_WORD_BITS[word_no].items()
                 if b not in allowed and v is not None}
        check(not extra, f"状态字{word_no} 无错位残留位（多余={extra}）")

    # ── U6 状态字4 具体取值 ─────────────────────────────────────────────
    section("U6 状态字4 = 0x0002（旧实现报「A相潮流方向异常」）")
    out = codec.decode_status_word("电表运行状态字4", bytes.fromhex("02 00")) or ""
    check("A相欠压" in out, f"0x0002 → A相欠压（实际 {out}）")
    check("潮流方向异常" not in out, "不再出现错误名「潮流方向异常」")
    check("无故障" not in out, "有置位时不写「无故障」")
    out = codec.decode_status_word("电表运行状态字4", bytes.fromhex("40 00")) or ""
    check("A相潮流方向" in out, f"0x0040(Bit6) → A相潮流方向（实际 {out}）")
    out = codec.decode_status_word("电表运行状态字4", bytes.fromhex("00 01")) or ""
    check("A相断流" in out, f"0x0100(Bit8) → A相断流（实际 {out}）")
    out = codec.decode_status_word("电表运行状态字5", bytes.fromhex("02 00")) or ""
    check("B相欠压" in out, "状态字5 相位前缀为 B 相")
    out = codec.decode_status_word("电表运行状态字6", bytes.fromhex("02 00")) or ""
    check("C相欠压" in out, "状态字6 相位前缀为 C 相")

    # ── U7 状态字3 供电方式两位域 ───────────────────────────────────────
    section("U7 状态字3 供电方式（Bit2~Bit1 两位域，LSB 为 Bit1）")
    for value, want in ((0, "主电源"), (2, "辅助电源"), (4, "电池供电")):
        out = codec.decode_status_word("电表运行状态字3", value.to_bytes(2, "little")) or ""
        dom = out.split("位域: ")[-1]
        check(dom == f"供电方式={want}", f"位值 {value} → {want}（实际 {dom}）")
    out = codec.decode_status_word("电表运行状态字3", (6).to_bytes(2, "little")) or ""
    check("供电方式=3" in out, "未定义取值(0b11) → 输出十进制而非臆造文案")
    out = codec.decode_status_word("电表运行状态字3", bytes.fromhex("02 00")) or ""
    check("继电器状态" in out and "供电方式=辅助电源" in out,
          "两位域与单 bit 共存（Bit4 继电器 + 位域）")

    # ── U8 保留位占位 ──────────────────────────────────────────────────
    section("U8 保留位：置位点名 / 未置位不占列表")
    for word_no, bit in ((4, 9), (1, 9), (3, 9), (7, 15), (1, 8), (3, 8)):
        out = codec.decode_status_word(f"电表运行状态字{word_no}",
                                       (1 << bit).to_bytes(2, "little")) or ""
        check(f"Bit{bit}" in out and "保留" in out,
              f"状态字{word_no} Bit{bit} 置位 → 点名保留位")
    out = codec.decode_status_word("电表运行状态字4", b"\x00\x00") or ""
    check("保留" not in out, "全 0 时未置位保留位不进列表（避免成串噪声）")
    check("无故障" in out, "故障类全 0 → 无故障")
    out = codec.decode_status_word("电表运行状态字1", b"\x00\x00") or ""
    check("保留" not in out, "非故障类全 0 时未置位保留位同样不进列表")
    check("未置位:" in out, "非故障类保留「未置位」列表（维持既有观感）")

    # ── U9 位表完整性 ─────────────────────────────────────────────────
    section("U9 位表完整性：状态字 1~7 覆盖 Bit0~Bit15")
    for word_no in range(1, 8):
        # 用「实际覆盖位」而非 raw keys：两位域（状态字3 供电方式）的 key 为 LSB 位号
        covered = _covered_bits(codec.STATUS_WORD_BITS[word_no])
        check(covered == set(range(16)),
              f"状态字{word_no} 覆盖 16 位（缺失={sorted(set(range(16)) - covered)}）")
    check(codec.STATUS_WORD_BITS[3].get(1) == ("供电方式", 2, codec.SUPPLY_MODE_NAMES),
          "状态字3 供电方式以两位域项（key=LSB 位号 1）声明")
    check(codec.STATUS_WORD_BITS[3].get(8) is None,
          "状态字3 Bit8 按保留占位（附录C 未提及则不臆造事件）")
    check(codec.SUPPLY_MODE_NAMES == {0: "主电源", 1: "辅助电源", 2: "电池供电"},
          "供电方式枚举与附录C 一致")

    # ── U10 边界 ──────────────────────────────────────────────────────
    section("U10 边界：空/短/未知")
    check(codec.decode_status_word(None, b"\x01\x02") is None,  # type: ignore[arg-type]
          "name=None → None，不抛异常")
    check(codec.decode_status_word("电表运行状态字4", b"") is None, "空数据 → None")
    check(codec.decode_status_word("某状态字", b"\x01\x02") is None, "未知名 → None")
    check(codec.decode_report_status_word("主动上报状态字", b"") is None, "模式/状态字空数据 → None")
    short = codec.decode_report_status_word("主动上报状态字", b"\x01") or ""
    check("长度不符" in short, "短数据仍尽力解析并提示长度不符")
    short = codec.decode_report_mode_word("主动上报模式字", b"\x01") or ""
    check("长度不符" in short and "负荷开关误动或拒动" in short, "模式字短数据同样尽力解析")
    out = codec.decode_value(bytes.fromhex("01 02 03"), "BS24", "", "未知位域") or ""
    check("该位域位定义未收录" in out, "未知位域给出「未收录」文案")
    check("附录C" in out and "第4号补遗" in out, "兜底文案并列两个出处（不再单一错误出处）")
    out = codec.decode_value(bytes.fromhex("01" + "00" * 11), "BS96", "", "某个未知BS96DI") or ""
    check("未收录" in out, "名称不匹配的 BS96 不误按主动上报状态字解析")

    # ── U11 桌面 vs Web ───────────────────────────────────────────────
    section("U11 桌面与 Web 输出逐字符一致")
    desktop = pr.DLT645GuiParser(dp.DLT645Parser()).parse_to_table(bytes.fromhex(FIELD_FRAME))
    desktop_vals = [row[2] for row in desktop if "数据值" in str(row[0])]
    check(len(desktop_vals) == 1, "桌面转表含唯一「数据值」行")
    check(desktop_vals and desktop_vals[0] == val, "桌面转表值 == 解析器输出")
    try:
        from reflex_web import reflex_web as web_app  # noqa: E402
        st = getattr(web_app, "State")(_reflex_internal_init=True)
        rows = st._safe_parse_to_table(dp.DLT645Parser(), bytes.fromhex(FIELD_FRAME))
        web_vals = [r[2] for r in rows if "数据值" in str(r[0])]
        check(web_vals == desktop_vals, "Web 转表值与桌面逐字符一致")
        # 全部行（含字节定位）逐行一致 → 两端口径未漂移
        check([tuple(r[:4]) for r in rows] == [tuple(r[:4]) for r in desktop],
              f"Web 与桌面全部 {len(rows)} 行一致（字段/原始值/解析值/说明）")
    except ImportError as exc:
        # 本机无 reflex（如 WSL 解释器未装）→ 退化为源码守卫：Web 侧转表必须消费
        # 同一 parse() 输出（即同一 dlt645_data_codec），不得有第二份位表实现。
        print(f"  [SKIP] Web 真实对拍（{exc}）→ 退化为源码守卫")
        src = (_ROOT_REFLEX / "reflex_web.py").read_text(encoding="utf-8")
        check('dlt645_result.get("fields"' in src,
              "源码守卫：Web 转表消费 parse() 的 fields（同一 codec 单一来源）")
        check("REPORT_STATUS_BITS" not in src and "STATUS_WORD_BITS" not in src,
              "源码守卫：Web 侧不存在第二份位表")

    print(f"\n{'=' * 60}\nPASS={PASS} FAIL={FAIL}")
    if FAILED:
        print("\n失败项：")
        for m in FAILED:
            print(f"  - {m}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
