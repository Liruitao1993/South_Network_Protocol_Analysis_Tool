# -*- coding: utf-8 -*-
"""协议6 光伏协议转换单元 DL/T 645-2007 扩展协议解析测试（2026-09-17，任务 09-17-dlt645-pv-ext）

规范来源：`协议文档/6.645协议/附件1：协议转换单元【低压分布式光伏协议转换单元】-技术规范书0625.md`
  §D.1（一）变量类 /（二）参数类 /（三）事件类 三张数据标识表；附录 I.3.3.1（0FH/8FH 透传）

覆盖：
  1. DI 表规模/单一来源/合并幂等/冲突集为空（R5、R6）
  2. 表驱动全覆盖：PV_DI_MAP 每个 key 均可解析出非空行（防漏项）
  3. golden：电压/电流/功率（正、负、±7999.9999 边界）/功率因数/全变量块 18 值
  4. 单相 FF（A2）、DI0=FF 下挂全部（A4）、DI0 双语义（A7）
  5. 事件块逆变器 12→1 字节序（A6）、调控结果枚举、03E60132 = 第 50 次
  6. 扩展控制码 0FH/8FH 透传 + 命中扩展 DI 的二次展开（A8）
  7. 参数类枚举与「数量 + 12 路通信地址」（A5）、歧义行存疑呈现不臆造
  8. 两端（桌面 / Reflex Web）关键字段一致（A9/A10）
  9. 兜底不回归：未知 DI、未知控制码、既有标准 DI（R7）
 10. 功率符号位算法（用文档示例 0111=+7 / 1111=-7 先验证再落地）

直接运行: python test/test_dlt645_pv_ext.py
"""

import _path_setup  # noqa: E402,F401

import json
import sys
from pathlib import Path

from dlt645_frame_gen import DLT645FrameGenerator, encode_di
from dlt645_data_codec import FUNC_NAMES, bcd_pack
from dlt645_parser import DLT645Parser

import dlt645_pv_ext as pv
from dlt645_di_lookup import DLT645DILookup

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


def build_frame(decoded: bytes, ctrl: int = 0x91) -> bytes:
    """decoded = 减 0x33 后的逻辑数据域（含 4 字节 DI）"""
    return GEN.build_frame(ADDR, ctrl, decoded)


def parse(data: bytes, ctrl: int = 0x91) -> dict:
    return DLT645Parser.parse(build_frame(data, ctrl))


def field_map(result: dict) -> dict:
    """归一化字段表：{字段名: (解析值或原始值, 说明, 原始值)}，兼容 3/4 元组"""
    m = {}
    for item in result["fields"]:
        if len(item) == 4:
            name, raw, parsed, desc = item
        else:
            name, raw, desc = item
            parsed = ""
        key = name.replace("  └ ", "").strip()
        m[key] = (parsed if parsed else raw, desc, raw)
    return m


def row_for(fm: dict, keyword: str):
    """按字段名关键字取行（返回 (值, 说明, 原始值) 或 None）"""
    for k, v in fm.items():
        if keyword in k:
            return v
    return None


def be_power(big4) -> bytes:
    """逻辑 4 字节（高位在前）→ 线上低字节在前"""
    return bytes(big4)[::-1]


# ═══════════════════════════════════════════════════════════════
# 1. DI 表与合并（R5 / R6）
# ═══════════════════════════════════════════════════════════════

def test_di_map_and_merge():
    print("\n[1] DI 表规模 / 单一来源 / 合并幂等 / 冲突集")
    total = len(pv.PV_DI_MAP)
    groups = {}
    for info in pv.PV_DI_MAP.values():
        groups[info["group"]] = groups.get(info["group"], 0) + 1
    check("PV_DI_MAP 键数 = 682（文档三张表展开）", total == 682, f"实际 {total}")
    check("分组键数 = 变量77 / 参数172 / 事件433",
          groups == {"变量": 77, "参数": 172, "事件": 433}, str(groups))

    base = {"00010000": {"name": "当前正向有功总电能"}}
    merged = pv.merge_pv_di_map(base)
    check("merge 保留 base 键", "00010000" in merged and merged["00010000"]["name"] == "当前正向有功总电能",
          str(merged.get("00010000")))
    check("merge 并入全部扩展 DI", len(merged) == len(base) + total,
          f"{len(merged)} vs {len(base) + total}")
    check("merge 不改写入参", list(base) == ["00010000"], str(list(base)))
    check("冲突集为空（与既有 1099 条标准 DI 无撞键）", pv._merge_conflicts == [],
          str(pv._merge_conflicts))
    again = pv.merge_pv_di_map(base)
    check("merge 幂等（重复调用结果一致）", again == merged, "两次结果不同")
    check("is_pv_di 判定", pv.is_pv_di("02e60101") and not pv.is_pv_di("00010000"))

    # 解析器/查询页与模块同源
    parser_map = DLT645Parser._load_di_map()
    check("解析器 DI 表含扩展 DI", parser_map.get("02E60101", {}).get("name") == "光伏逆变器1的电压数据块",
          str(parser_map.get("02E60101")))
    check("解析器 DI 表仍含标准 DI", parser_map.get("00010000", {}).get("name") == "当前正向有功总电能",
          str(parser_map.get("00010000")))

    lookup = DLT645DILookup()
    _pv_info = lookup.get_di_info("02E60101")
    check("查询页（桌面/Web 共用）可检索扩展 DI",
          _pv_info is not None and "光伏" in _pv_info["name"],
          str(_pv_info))
    check("查询页 search 可按中文检索扩展 DI",
          len(lookup.search("光伏逆变器1的电压")) == 1, str(len(lookup.search("光伏逆变器1的电压"))))
    check("查询页仍含 1099 条标准 DI 数据", len(lookup.data) == 1099 + total,
          f"{len(lookup.data)} vs {1099 + total}")

    # 扩展 DI 不得写入生成物
    import json
    with open(Path(__file__).resolve().parent.parent / "dlt645_di.json", encoding="utf-8") as f:
        raw = json.load(f)
    leaked = [k for k in raw.get("di_map", {}) if k[:4] in ("02E6", "03E6", "04E6")]
    check("dlt645_di.json（生成物）未被写入扩展 DI", not leaked, str(leaked[:5]))


# ═══════════════════════════════════════════════════════════════
# 2. 表驱动全覆盖（R-4 防漏项）
# ═══════════════════════════════════════════════════════════════

def test_table_driven_coverage():
    print("\n[2] 表驱动全覆盖：PV_DI_MAP 每个 key 均可解析出非空行")
    empty = []
    for code, info in sorted(pv.PV_DI_MAP.items()):
        body = bytes([0x00] * max(info["length"], 4))
        rows, name = pv.parse_pv_di(code, 0x91, encode_di(code) + body)
        if not rows or not name:
            empty.append(code)
            continue
        if len(rows) < 2:
            empty.append(f"{code}(仅{len(rows)}行)")
    check(f"{len(pv.PV_DI_MAP)} 个 DI 键全部返回非空解析行", not empty, str(empty[:10]))

    # 同一 key 走完整解析器路径也必须展开出子字段
    no_detail = []
    for code in list(sorted(pv.PV_DI_MAP))[::37]:     # 抽样 19 个（步长 37）
        info = pv.PV_DI_MAP[code]
        r = parse(encode_di(code) + bytes(max(info["length"], 1)))
        if not any(str(item[0]).startswith("  └") for item in r["fields"]):
            no_detail.append(code)
    check("抽样 19 个 DI 经解析器展开出子字段行", not no_detail, str(no_detail))


# ═══════════════════════════════════════════════════════════════
# 3. 变量类 golden（A1 / A2 / A3）
# ═══════════════════════════════════════════════════════════════

def test_variable_golden():
    print("\n[3] 变量类 golden：电压 / 电流 / 功率符号位 / 功率因数")
    # 功率符号位算法（用文档示例先验证）
    v_plus, _ = pv._power_value(be_power([0x70, 0x00, 0x00, 0x00]))
    v_minus, _ = pv._power_value(be_power([0xF0, 0x00, 0x00, 0x00]))
    check("文档示例 最高半字节 0111 → +7（本实现 +7000.0000）", v_plus == "+7000.0000", str(v_plus))
    check("文档示例 最高半字节 1111 → -7（本实现 -7000.0000）", v_minus == "-7000.0000", str(v_minus))
    check("边界 +7999.9999", pv._power_value(be_power([0x79, 0x99, 0x99, 0x99]))[0] == "+7999.9999")
    check("边界 -7999.9999", pv._power_value(be_power([0xF9, 0x99, 0x99, 0x99]))[0] == "-7999.9999")
    check("非 BCD 半字节回退（返回 None）", pv._power_value(bytes([0x00, 0x00, 0x00, 0x8A]))[0] is None)

    # A1 电压块 02E60101
    body = encode_di("02E60101") + bcd_pack("2200", 2) + bcd_pack("2211", 2) + b"\xff\xff"
    r = parse(body)
    fm = field_map(r)
    check("A1 DI 名称", r["di_desc"] == "光伏逆变器1的电压数据块", r["di_desc"])
    check("A1 A相电压 = 220.0", fm.get("A相电压", ("",))[0] == "220.0", str(fm.get("A相电压")))
    check("A1 B相电压 = 221.1", fm.get("B相电压", ("",))[0] == "221.1", str(fm.get("B相电压")))
    check("A1 原始值列为 hex", fm.get("A相电压", ("", "", ""))[2] == "0022", str(fm.get("A相电压")))
    check("A1 四列齐全（字段/原始值/解析值/说明）",
          all(all(isinstance(x, str) for x in item) and len(item) == 4
              for item in r["fields"] if len(item) == 4)
          and fm.get("A相电压", ("", "", ""))[1] != "", "说明列为空")
    # A2 单相设备 B/C 相 FF
    check("A2 C相 FF 标注为单相无该相", "单相设备无C相" in fm.get("C相电压", ("",))[0],
          str(fm.get("C相电压")))
    check("A2 FF 不被当成数值（解析值为 FF 标注文本，非数字）",
          fm.get("C相电压", ("",))[0] == "FF（单相设备无C相，文档 §D.1 表下注）",
          str(fm.get("C相电压")))

    # 电流块 02E60201（3 字节/值，2 位小数）
    body = encode_di("02E60201") + bcd_pack("1234", 3) + bcd_pack("5678", 3) + b"\xff" * 3
    fm = field_map(parse(body))
    check("电流块 A相电流 = 12.34", fm.get("A相电流", ("",))[0] == "12.34", str(fm.get("A相电流")))
    check("电流块 B相电流 = 56.78", fm.get("B相电流", ("",))[0] == "56.78", str(fm.get("B相电流")))

    # A3 功率符号位
    body = (encode_di("02E60301") + be_power([0x00, 0x07, 0x00, 0x00])
            + be_power([0x80, 0x07, 0x00, 0x00])
            + be_power([0x79, 0x99, 0x99, 0x99]) + be_power([0xF9, 0x99, 0x99, 0x99]))
    r = parse(body)
    fm = field_map(r)
    check("A3 总有功 +7.0000（符号位 0 = 发电）",
          fm.get("瞬时总有功功率", ("",))[0] == "+7.0000", str(fm.get("瞬时总有功功率")))
    check("A3 A有功 -7.0000（符号位 1 = 用电）",
          fm.get("瞬时A有功功率", ("",))[0] == "-7.0000", str(fm.get("瞬时A有功功率")))
    check("A3 B有功 边界 +7999.9999",
          fm.get("瞬时B有功功率", ("",))[0] == "+7999.9999", str(fm.get("瞬时B有功功率")))
    check("A3 C有功 边界 -7999.9999",
          fm.get("瞬时C有功功率", ("",))[0] == "-7999.9999", str(fm.get("瞬时C有功功率")))
    check("A3 说明含符号位依据", "符号位" in fm.get("瞬时总有功功率", ("", ""))[1],
          str(fm.get("瞬时总有功功率")))

    # 功率因数块 02E60501
    body = encode_di("02E60501") + bcd_pack("0999", 2) + bcd_pack("1000", 2) \
        + bcd_pack("1000", 2) + bcd_pack("1000", 2)
    fm = field_map(parse(body))
    check("功率因数 总 = 0.999", fm.get("总功率因数", ("",))[0] == "0.999", str(fm.get("总功率因数")))
    check("功率因数 A = 1.000", fm.get("A功率因数", ("",))[0] == "1.000", str(fm.get("A功率因数")))


def test_all_vars_block():
    print("\n[3b] 全变量块 02E60F01（18 值 / 55 字节）")
    info = pv.PV_DI_MAP["02E60F01"]
    check("值定义 18 项", len(info["values"]) == 18, str(len(info["values"])))
    check("声明总长 55 字节", info["length"] == 55, str(info["length"]))
    body = (encode_di("02E60F01")
            + bcd_pack("2200", 2) + bcd_pack("2211", 2) + bcd_pack("2222", 2)
            + bcd_pack("111", 3) + bcd_pack("222", 3) + bcd_pack("333", 3)
            + be_power([0x79, 0x99, 0x99, 0x99]) + be_power([0x00, 0x07, 0x00, 0x00])
            + be_power([0x80, 0x07, 0x00, 0x00]) + be_power([0xF9, 0x99, 0x99, 0x99])
            + be_power([0x00, 0x00, 0x00, 0x01]) * 4
            + bcd_pack("0999", 2) + bcd_pack("1000", 2) + bcd_pack("1000", 2) + bcd_pack("1000", 2))
    check("测试帧长度 = 4 + 55", len(body) == 59, str(len(body)))
    r = parse(body)
    fm = field_map(r)
    check("全变量块 名称", r["di_desc"] == "光伏逆变器1所有变量的数据块", r["di_desc"])
    check("无长度不符告警行", "⚠ 数据长度不符" not in " ".join(fm), str([k for k in fm if "⚠" in k]))
    check("C相电压 = 222.2", fm.get("C相电压", ("",))[0] == "222.2", str(fm.get("C相电压")))
    check("C相电流 = 3.33", fm.get("C相电流", ("",))[0] == "3.33", str(fm.get("C相电流")))
    check("总有功 +7999.9999", fm.get("瞬时总有功功率", ("",))[0] == "+7999.9999")
    check("C有功 -7999.9999", fm.get("瞬时C有功功率", ("",))[0] == "-7999.9999",
          str(fm.get("瞬时C有功功率")))
    check("总无功 +0.0001", fm.get("瞬时总无功功率", ("",))[0] == "+0.0001",
          str(fm.get("瞬时总无功功率")))
    check("A功率因数 1.000", fm.get("A功率因数", ("",))[0] == "1.000", str(fm.get("A功率因数")))
    # 长度不符时尽力解析并标注（陷阱 23）
    fm2 = field_map(parse(encode_di("02E60F01") + body[4:4 + 55 - 3]))
    check("长度不符时标注并尽力解析",
          any("数据长度不符" in k for k in fm2) and fm2.get("A相电压", ("",))[0] == "220.0",
          str([k for k in fm2 if "⚠" in k]))


# ═══════════════════════════════════════════════════════════════
# 4. DI0 语义（A4 / A7）
# ═══════════════════════════════════════════════════════════════

def test_di0_semantics():
    print("\n[4] DI0 双语义（A4 / A7）")
    body = encode_di("02E601FF") + bcd_pack("2200", 2) + bcd_pack("2211", 2) + bcd_pack("2222", 2)
    r = parse(body)
    check("A4 02E601FF → 下挂所有光伏逆变器",
          r["di_desc"] == "下挂所有光伏逆变器的电压数据块", r["di_desc"])
    check("A4 说明标注 DI0=FF 语义",
          "DI0=FF" in field_map(r).get("数据块", ("", ""))[1], str(field_map(r).get("数据块")))

    r = parse(encode_di("04E6040C") + bytes([0x01]))
    check("参数类 DI0=0C → 光伏逆变器12", r["di_desc"] == "光伏逆变器12的运行状态", r["di_desc"])

    # A7 事件序号 03E60132 = 第 50 次
    r = parse(encode_di("03E60132") + bytes(36))
    check("A7 03E60132 → 第 50 次", "上50次" in r["di_desc"], r["di_desc"])
    r = parse(encode_di("03E60101") + bytes(36))
    check("A7 03E60101 → 上1次", "上1次" in r["di_desc"], r["di_desc"])
    r = parse(encode_di("03E61100") + bcd_pack("123", 3))
    fm = field_map(r)
    check("A7 03E61100 电压越限事件总次数（DI0=00 不是逆变器号）",
          r["di_desc"] == "电压越限事件总次数", r["di_desc"])
    check("A7 次数值 = 123", fm.get("电压越限事件总次数", ("",))[0] == "123",
          str(fm.get("电压越限事件总次数")))
    # 事件总次数块（按逆变器）
    r = parse(encode_di("03E60003") + bcd_pack("9", 3))
    check("事件总次数 03E60003 → 光伏逆变器3", r["di_desc"] == "光伏逆变器3的开关机控制事件总次数",
          r["di_desc"])
    r = parse(encode_di("03E600FF") + bcd_pack("9", 3))
    check("事件总次数 DI0=FF → 下挂所有",
          r["di_desc"] == "下挂所有光伏逆变器的开关机控制事件总次数", r["di_desc"])


# ═══════════════════════════════════════════════════════════════
# 5. 事件块（A6）
# ═══════════════════════════════════════════════════════════════

def test_event_block():
    print("\n[5] 事件块：逆变器 12→1 字节序 / 调控结果枚举（A6）")
    # 开关机控制事件块：发生/结束时刻 + 事件类型12B + 调控结果12B
    onoff = bytes([0x00] * 11 + [0x01])                # [0]=逆变器12 ... [11]=逆变器1
    result_bytes = bytes([0x02, 0x03] + [0x00] * 8 + [0x00, 0x01])
    body = (encode_di("03E60101")
            + bcd_pack("260917120000", 6) + bcd_pack("260917123000", 6)
            + onoff + result_bytes)
    r = parse(body)
    fm = field_map(r)
    check("A6 发生时刻 = 2026-09-17 12:00:00",
          fm.get("发生时刻", ("",))[0] == "2026-09-17 12:00:00", str(fm.get("发生时刻")))
    check("A6 结束时刻 = 2026-09-17 12:30:00",
          fm.get("结束时刻", ("",))[0] == "2026-09-17 12:30:00", str(fm.get("结束时刻")))
    check("A6 字节序说明行（逆变器12→1）",
          "逆变器12、11" in str(fm.get("※ 事件类型字节序", ("", ""))),
          str(fm.get("※ 事件类型字节序")))
    # 事件类型：首字节 00 → 逆变器12 开机；末字节 01 → 逆变器1 关机
    check("A6 事件类型 首字节 → 逆变器12 = 开机",
          fm.get("事件类型（逆变器12）", ("",))[0] == "开机",
          str(fm.get("事件类型（逆变器12）")))
    check("A6 事件类型 末字节 → 逆变器1 = 关机",
          fm.get("事件类型（逆变器1）", ("",))[0] == "关机",
          str(fm.get("事件类型（逆变器1）")))
    # 调控结果：首字节 02 → 逆变器12 调控失败；末字节 01 → 逆变器1 未调
    check("A6 调控结果 首字节 → 逆变器12 = 调控失败",
          fm.get("调控结果（逆变器12）", ("",))[0] == "调控失败",
          str(fm.get("调控结果（逆变器12）")))
    check("A6 调控结果 末字节 → 逆变器1 = 未调",
          fm.get("调控结果（逆变器1）", ("",))[0] == "未调",
          str(fm.get("调控结果（逆变器1）")))
    check("A6 调控结果 FF → 不存在该项信息",
          "FF" in field_map(parse(encode_di("03E60101") + bytes(12)
                                  + bytes(12) + b"\xff" * 12))["调控结果（逆变器12）"][0],
          "FF 未按不存在处理")
    # 枚举全覆盖（00~04）
    enum_map = {"00": "调控成功", "01": "未调", "02": "调控失败", "03": "调控不支持", "04": "其他问题"}
    bad = []
    for code, text in enum_map.items():
        b = bytes([int(code, 16)]) + bytes(11)
        got = field_map(parse(encode_di("03E60101") + bytes(12) + bytes(12) + b)) \
            .get("调控结果（逆变器12）", ("",))[0]
        if got != text:
            bad.append((code, got, text))
    check("调控结果枚举 00~04 全覆盖", not bad, str(bad))
    # 有功功率控制事件块（73 字节）：事件类型 1B + 调控结果 12B + 12×4B 调控值
    body = (encode_di("03E60301") + bcd_pack("260917120000", 6) + bcd_pack("260917123000", 6)
            + bytes([0x01]) + bytes(12)
            + b"".join(bcd_pack(f"{i:08d}", 4) for i in range(1, 13)))
    check("03E60301 帧长 = 4 + 73", len(body) == 77, str(len(body)))
    fm = field_map(parse(body))
    check("03E60301 事件类型 = 百分比调节", fm.get("事件类型", ("",))[0] == "01（百分比调节）",
          str(fm.get("事件类型")))
    check("03E60301 光伏逆变器1调控值 = 0.0001",
          fm.get("光伏逆变器1调控值", ("",))[0] == "0.0001",
          str(fm.get("光伏逆变器1调控值")))
    check("03E60301 光伏逆变器12调控值 = 0.0012",
          fm.get("光伏逆变器12调控值", ("",))[0] == "0.0012",
          str(fm.get("光伏逆变器12调控值")))
    # 功率因数控制事件块（48 字节，无事件类型）
    body = (encode_di("03E60701") + bcd_pack("260917120000", 6) + bcd_pack("260917123000", 6)
            + bytes(12) + b"".join(bcd_pack("0999", 2) for _ in range(12)))
    check("03E60701 帧长 = 4 + 48", len(body) == 52, str(len(body)))
    fm = field_map(parse(body))
    check("03E60701 无事件类型行", "事件类型" not in " ".join(
        k for k in fm if "调控结果" not in k and "字节序" not in k), str(list(fm)))
    check("03E60701 调控值 0.999", fm.get("光伏逆变器1调控值", ("",))[0] == "0.999",
          str(fm.get("光伏逆变器1调控值")))
    # 电压越限事件记录（24 字节）
    body = (encode_di("03E61105") + bcd_pack("260917120000", 6) + bcd_pack("260917123000", 6)
            + bcd_pack("2300", 2) + b"\xff\xff" + bcd_pack("2310", 2)
            + bcd_pack("2200", 2) + b"\xff\xff" + bcd_pack("2210", 2))
    fm = field_map(parse(body))
    check("03E61105 → 上5次", "上5次" in parse(body)["di_desc"], parse(body)["di_desc"])
    check("电压越限 B相 FF = 单相无该相", "单相设备无B相" in fm.get("越限B相电压", ("",))[0],
          str(fm.get("越限B相电压")))
    check("恢复A相电压 = 220.0", fm.get("恢复A相电压", ("",))[0] == "220.0",
          str(fm.get("恢复A相电压")))
    # 通信异常事件记录（13 字节）
    body = encode_di("03E6130A") + bcd_pack("260917120000", 6) + bcd_pack("260917123000", 6) + bytes([0x03])
    fm = field_map(parse(body))
    check("通信异常记录逆变器号 = 光伏逆变器3", "光伏逆变器3" in fm.get("逆变器号", ("",))[0],
          str(fm.get("逆变器号")))


# ═══════════════════════════════════════════════════════════════
# 6. 控制码 0FH / 8FH 透传（A8）
# ═══════════════════════════════════════════════════════════════

def test_transparent_code():
    print("\n[6] 扩展控制码 0FH / 8FH 无线转发（透传）（A8）")
    check("FUNC_NAMES 含 0x0F 无线转发(透传)", FUNC_NAMES.get(0x0F) == "无线转发(透传)",
          str(FUNC_NAMES.get(0x0F)))
    check("0x8F 取 func=0x0F 同一条目", (0x8F & 0x1F) == 0x0F, hex(0x8F & 0x1F))

    # 8FH 透传 + 命中扩展 DI → 二次展开
    body = encode_di("02E60101") + bcd_pack("2200", 2) + bcd_pack("2211", 2) + bcd_pack("2222", 2)
    r = parse(body, ctrl=0x8F)
    fm = field_map(r)
    check("8FH 控制码显示无线转发(透传)", "无线转发(透传)" in r["control_desc"], r["control_desc"])
    check("8FH 透传数据标识 DI 行", fm.get("透传数据标识 DI", ("",))[2] == "02E60101",
          str(fm.get("透传数据标识 DI")))
    check("8FH 透传数据行（6 字节）", fm.get("透传数据", ("",))[0] == "6 字节",
          str(fm.get("透传数据")))
    check("8FH 透传内容按扩展协议二次展开", "透传内容按扩展协议展开" in " ".join(fm),
          str(list(fm)))
    check("8FH 二次展开后的 A相电压 = 220.0", fm.get("A相电压", ("",))[0] == "220.0",
          str(fm.get("A相电压")))
    check("8FH 不落入「读数据应答」单值解码分支", "数据值" not in " ".join(fm), str(list(fm)))

    # 0FH 主站请求 + 未知 DI：仍呈现 DI + 透传数据（R7 兜底）
    r = parse(encode_di("12345678") + bytes([0x01, 0x02]), ctrl=0x0F)
    fm = field_map(r)
    check("0FH 控制码显示无线转发(透传)（主站请求）",
          "主站请求" in r["control_desc"] and "无线转发(透传)" in r["control_desc"],
          r["control_desc"])
    check("0FH 未知 DI 仍呈现透传数据", fm.get("透传数据", ("",))[2] == "0102",
          str(fm.get("透传数据")))
    check("0FH 未知 DI 仍标未知数据标识", r["di_desc"] == "未知数据标识", r["di_desc"])

    # 0FH + 扩展 DI（写/透传请求）
    r = parse(encode_di("04E60401") + bytes([0x00]), ctrl=0x0F)
    check("0FH 命中扩展 DI → 二次展开", "运行状态" in " ".join(field_map(r)),
          str(list(field_map(r))))
    check("0FH 运行状态 = 开机", field_map(r).get("运行状态", ("",))[0] == "00（开机）",
          str(field_map(r).get("运行状态")))

    # 透明传输长度契约：L = 04H + N
    frame = build_frame(body, ctrl=0x8F)
    check("L = 04H + N（6 字节透传 → L=0x0A）", frame[9] == 0x0A, hex(frame[9]))


# ═══════════════════════════════════════════════════════════════
# 7. 参数类与歧义行（A5）
# ═══════════════════════════════════════════════════════════════

def test_parameter_and_ambiguous():
    print("\n[7] 参数类枚举 / 数量+地址表 / 歧义行存疑（A5）")
    fm = field_map(parse(encode_di("04E60401") + bytes([0x00])))
    check("A5 运行状态 00 = 开机", fm.get("运行状态", ("",))[0] == "00（开机）",
          str(fm.get("运行状态")))
    fm = field_map(parse(encode_di("04E60402") + bytes([0x01])))
    check("A5 运行状态 01 = 关机（逆变器2）", fm.get("运行状态", ("",))[0] == "01（关机）",
          str(fm.get("运行状态")))
    fm = field_map(parse(encode_di("04E60301") + bytes([0x00])))
    check("A5 输出类型 00 = 单相", fm.get("输出类型", ("",))[0] == "00（单相）",
          str(fm.get("输出类型")))
    fm = field_map(parse(encode_di("04E60301") + bytes([0x01])))
    check("A5 输出类型 01 = 三相", fm.get("输出类型", ("",))[0] == "01（三相）",
          str(fm.get("输出类型")))
    fm = field_map(parse(encode_di("04E60A01") + bcd_pack("12345678", 4)))
    check("A5 日发电量 = 123456.78 kWh", fm.get("日发电量", ("",))[0] == "123456.78",
          str(fm.get("日发电量")))

    # A5 数量 + 12 路通信地址（歧义行，按文字描述切分）
    # ⚠ 该 DI 现由《南网光伏无线模组接口手册 V1.6》接管（模型 1+6×M，有实测报文自证，
    #    见 test_dlt645_pv_wireless）：这里直接调 pv 模块层，锁住附件1「歧义行」的切分契约。
    body = encode_di("04E60001") + bytes([0x03]) + bytes(range(0x11, 0x1D)) + b"\xff\xff\xff"
    _rows, _ = pv.parse_pv_di("04E60001", 0x91, body)
    fm = field_map({"fields": _rows or []})
    check("A5 数量 M = 3", "3" in fm.get("有效下挂光伏逆变器数量 M（M<=12）", ("",))[0],
          str(fm.get("有效下挂光伏逆变器数量 M（M<=12）")))
    addrs = [k for k in fm if "的通信地址" in k]
    check("A5 12 路通信地址逐条呈现", len(addrs) == 12, str(len(addrs)))
    check("A5 第 1/12 路地址值", fm.get("光伏接入单元1的通信地址", ("",))[0] == "11"
          and fm.get("光伏接入单元12的通信地址", ("",))[0] == "1C",
          str(fm.get("光伏接入单元1的通信地址")) + str(fm.get("光伏接入单元12的通信地址")))
    check("A5 无归属的 3 字节按保留 + 存疑标注",
          "保留（存疑）" in " ".join(fm) and "不臆造字段" in str(fm.get("保留（存疑）")),
          str(fm.get("保留（存疑）")))

    # 档案（长度列 13221，5 段 vs 描述 4 项）
    body = encode_di("04E62101") + bytes([0x02]) + b"HW1" + bytes([0x12, 0x01]) \
        + bytes([0x02, 0x00]) + b"\x00"
    fm = field_map(parse(body))
    check("档案 品牌 ASCII = HW1", fm.get("逆变器品牌", ("",))[0] == "HW1",
          str(fm.get("逆变器品牌")))
    check("档案 端口 = 端口2（RJ45-II）", "端口2" in fm.get("接入端口", ("",))[0],
          str(fm.get("接入端口")))
    check("档案 末段按保留（存疑）",
          "保留" in " ".join(fm) and "无从归属" in fm.get("保留", ("", "", ""))[1],
          str(fm.get("保留")))

    # 03E61401/02/04 动态记录切分
    rec = bcd_pack("260917120000", 6) + bcd_pack("2200", 2) * 2
    body = encode_di("03E61401") + bcd_pack("7", 3) + rec + rec
    fm = field_map(parse(body))
    check("03E61401 总次数 = 7", fm.get("总次数", ("",))[0] == "7", str(fm.get("总次数")))
    check("03E61401 动态解出 2 条记录（上1/上2次）",
          "（上1次）发生时刻" in " ".join(fm) and "（上2次）发生时刻" in " ".join(fm),
          str([k for k in fm if "发生时刻" in k]))
    body = encode_di("03E61402") + bcd_pack("2", 3) + bcd_pack("260917120000", 6)
    fm = field_map(parse(body))
    check("03E61402（上1次）事件清零的发生时刻",
          fm.get("（上1次）事件清零的发生时刻", ("",))[0] == "2026-09-17 12:00:00",
          str(fm.get("（上1次）事件清零的发生时刻")))
    body = encode_di("03E61404") + bcd_pack("1", 3) + bcd_pack("260917120000", 6) \
        + bcd_pack("260917121000", 6)
    fm = field_map(parse(body))
    check("03E61404 校时前后时刻",
          fm.get("（上1次）校时前的时刻", ("",))[0] == "2026-09-17 12:00:00"
          and fm.get("（上1次）校时后的时刻", ("",))[0] == "2026-09-17 12:10:00",
          str(fm.get("（上1次）校时前的时刻")) + str(fm.get("（上1次）校时后的时刻")))
    # 03E61403 存疑行：保留原始 hex、不臆造字段
    body = encode_di("03E61403") + bcd_pack("5", 3) + bytes(range(20))
    r = parse(body)
    fm = field_map(r)
    check("03E61403 总次数 = 5", fm.get("总次数", ("",))[0] == "5", str(fm.get("总次数")))
    check("03E61403 记录段保留原始 hex + 存疑标注",
          "升级记录数据段（存疑）" in " ".join(fm)
          and "不臆造字段" in str(fm.get("升级记录数据段（存疑）")),
          str(fm.get("升级记录数据段（存疑）")))

    # 写请求（14H）：DI + 密码 + 操作者 + 写入值
    body = (encode_di("04E60B01") + bytes([0x04, 0x11, 0x11, 0x11, 0x00, 0x00, 0x00, 0x01])
            + bcd_pack("09171200", 4) + b"\xff" * 4
            + b"\xff" * 4 + b"\xff" * 4
            + bcd_pack("50000000", 4) + b"\xff" * 4)
    fm = field_map(parse(body, ctrl=0x14))
    check("写请求 密码/操作者代码行", fm.get("密码与操作者代码", ("",))[0].startswith("PA=04"),
          str(fm.get("密码与操作者代码")))
    check("写请求 按参数设置呈现写入值", fm.get("第1次调节的开始时间", ("",))[0] == "09-17 12:00",
          str(fm.get("第1次调节的开始时间")))
    check("写请求 第1次调控值 = 5000.0000", fm.get("第1次调控值", ("",))[0] == "5000.0000",
          str(fm.get("第1次调控值")))
    check("写请求 未调时段 FF 标注", "本时段不调节" in fm.get("第2次调控值", ("",))[0],
          str(fm.get("第2次调控值")))

    # 读请求无数据单元
    fm = field_map(parse(encode_di("02E60101"), ctrl=0x11))
    check("读请求无数据单元提示", "读请求" in str(fm.get("数据单元", ("",))),
          str(fm.get("数据单元")))


# ═══════════════════════════════════════════════════════════════
# 8. 兜底不回归（R7）
# ═══════════════════════════════════════════════════════════════

def test_fallback_no_regression():
    print("\n[8] 兜底不回归（R7）")
    # 既有标准 DI：读应答走单值解码
    r = parse(encode_di("00010000") + bcd_pack("12345678", 4))
    fm = field_map(r)
    check("标准 DI 00010000 名称/单位不回归",
          r["di_desc"] == "当前正向有功总电能" and fm.get("数据值", ("",))[0] == "123456.78 kWh",
          str(fm.get("数据值")))
    # 未知 DI（非 02E6/03E6/04E6）
    r = parse(encode_di("12345678") + bytes([0x01, 0x02]))
    check("未知 DI 保持「未知数据标识」", r["di_desc"] == "未知数据标识", r["di_desc"])
    check("未知 DI 走通用数据值分支（读应答，格式未知按裸 hex）",
          field_map(r).get("数据值", ("",))[0] == "0102", str(field_map(r)))
    r = parse(encode_di("12345678") + bytes([0x01, 0x02]), ctrl=0x16)
    check("未知 DI + 非读应答控制码走「数据内容」通用分支",
          field_map(r).get("数据内容", ("",))[2] == "0102", str(field_map(r)))
    # 未知控制码
    # 未知控制码：1EH 在标准 645 里没有定义，现按《无线模组接口手册 V1.6》§4.3.1 解释
    r = parse(encode_di("00010000") + bcd_pack("1", 4), ctrl=0x1E)
    check("1EH 按手册 V1.6 解释为模组在网状态上报",
          "模组在网状态上报" in r["control_desc"], r["control_desc"])
    # 既有 LME 接口不回归（DI 分派互不干扰）
    r = parse(encode_di("FF00DD01") + bytes([0x00, 0x00]), ctrl=0x11)
    check("LME 双模查询请求仍走 LME 解析",
          "HPLC双模STA内部详细信息查询请求" in r["di_desc"], r["di_desc"])
    # 扩展 DI 但控制码为异常应答（D6=1，数据域仅 ERR）
    r = parse(bytes([0x01]), ctrl=0xD1)
    check("异常应答（D6=1，1 字节 ERR）不被扩展 DI 分派抢走",
          "错误信息字 ERR" in " ".join(field_map(r)), str(list(field_map(r))))
    # 非扩展 DI 的 0FH 帧（走透传呈现，不报错）
    r = parse(encode_di("00010000") + bcd_pack("1", 4), ctrl=0x0F)
    check("标准 DI + 0FH 透传不报错且不二次展开",
          r["valid"] and "透传数据" in " ".join(field_map(r)), str(list(field_map(r))))


# ═══════════════════════════════════════════════════════════════
# 9. 两端一致（A9 / A10）
# ═══════════════════════════════════════════════════════════════

def _web_state():
    import reflex_web.reflex_web as app
    return app.State(_reflex_internal_init=True)


def test_desktop_gui_wrapper():
    print("\n[9b] 桌面 GUI 转表链（protocol_registry.DLT645GuiParser，4 元组展开）")
    import protocol_registry
    from dlt645_parser import DLT645Parser

    gui = protocol_registry.build_gui_parser(6, DLT645Parser())
    check("协议6 GUI 包装器类型", type(gui).__name__ == "DLT645GuiParser", type(gui).__name__)
    body = encode_di("02E60101") + bcd_pack("2200", 2) + bcd_pack("2211", 2) + b"\xff\xff"
    table = gui.parse_to_table(build_frame(body))
    names = [str(r[0]).strip() for r in table]
    check("桌面转表含扩展协议子字段行",
          any("A相电压" in n for n in names) and any("数据块" in n for n in names), str(names))
    a_phase = [r for r in table if "A相电压" in str(r[0])]
    check("桌面转表 A相电压解析值在 parsed 列（4 元组）",
          bool(a_phase) and a_phase[0][2] == "220.0", str(a_phase[:1]))
    check("桌面转表 6 列（字段/原始值/解析值/说明/起/止）",
          all(len(r) == 6 for r in table), str([len(r) for r in table][:3]))
    # 8FH 透传：DI 行 + 透传数据行 + 二次展开
    body = encode_di("02E60101") + bcd_pack("2200", 2) + bcd_pack("2211", 2) + bcd_pack("2222", 2)
    table = gui.parse_to_table(build_frame(body, 0x8F))
    names = " ".join(str(r[0]) for r in table)
    check("桌面转表 8FH 透传行 + 二次展开",
          "  └ 透传数据 " in names.replace("  └ 透传数据标识 DI", "") and "C相电压" in names, names)


def test_two_ends_consistency():
    print("\n[9] 桌面 / Reflex Web 两端一致（A9 / A10）")
    # A9 查询页数据源（Web 与桌面同为 dlt645_di_lookup）
    try:
        from reflex_web import lookup_utils
        rows = lookup_utils._search_dlt645_di("02E60101")
        check("A9 Web 查询页可检索扩展 DI（名称/单位/格式）",
              len(rows) == 1 and rows[0][1] == "光伏逆变器1的电压数据块"
              and rows[0][2] == "V" and rows[0][3] == "XXX.X|XXX.X|XXX.X",
              str(rows[:1]))
        rows = lookup_utils._search_dlt645_di("光伏逆变器12的档案")
        check("A9 Web 查询页中文关键词可检索扩展 DI", len(rows) == 1, str(len(rows)))
    except Exception as e:  # noqa: BLE001
        check("A9 Web 查询页检索", False, f"{type(e).__name__}: {e}")

    # A10 同一帧在两端的关键字段一致
    frames = [
        ("电压块", encode_di("02E60101") + bcd_pack("2200", 2) + bcd_pack("2211", 2) + b"\xff\xff", 0x91),
        ("有功功率负值", encode_di("02E60301") + be_power([0x80, 0x07, 0x00, 0x00]) * 4, 0x91),
        ("开关机事件", encode_di("03E60132") + bcd_pack("260917120000", 6)
         + bcd_pack("260917123000", 6) + bytes(12) + bytes([0x02] + [0x00] * 10 + [0x01]), 0x91),
        ("8FH 透传", encode_di("02E60101") + bcd_pack("2200", 2) * 3, 0x8F),
    ]
    keys = ("A相电压", "B相电压", "瞬时总有功功率", "发生时刻", "调控结果（逆变器1）",
            "透传数据", "数据块", "运行状态")
    try:
        st = _web_state()
        st.current_protocol = 6
        parser = st._get_parser()
    except Exception as e:  # noqa: BLE001
        check("A10 构造 Reflex Web State", False, f"{type(e).__name__}: {e}")
        return

    for title, data, ctrl in frames:
        frame = build_frame(data, ctrl)
        desktop = DLT645Parser.parse(frame)
        web_rows = st._safe_parse_to_table(parser, frame)
        dfm = field_map(desktop)
        wfm = {}
        for row in web_rows:
            name = str(row[0]).replace("  └ ", "").strip()
            wfm[name] = (row[2] if row[2] else row[1], row[3], row[1])
        diff = []
        for k in keys:
            if k in dfm:
                if k not in wfm or wfm[k][0] != dfm[k][0]:
                    diff.append((k, dfm[k][0], wfm.get(k, ("",))[0]))
        check(f"A10 {title}：关键字段两端一致（DI/名称/解析值）",
              not diff and desktop["di_code"] in " ".join(
                  str(r[1]) for r in web_rows if r[0] == "数据标识 DI"),
              f"差异 {diff}")
        check(f"A10 {title}：Web 行含 4 列展开子字段",
              any(str(r[0]).startswith("  └") for r in web_rows),
              str([r[0] for r in web_rows][:3]))


# ═══════════════════════════════════════════════════════════════
# 10. 文档一致性守卫（防表格与代码漂移）
# ═══════════════════════════════════════════════════════════════

def test_doc_consistency():
    print("\n[10] 规范文档一致性守卫（DI 表 / 格式列 / 长度列）")
    doc = Path(__file__).resolve().parent.parent / "协议文档" / "6.645协议" / \
        "附件1：协议转换单元【低压分布式光伏协议转换单元】-技术规范书0625.md"
    if not doc.exists():
        check("规范文档存在", False, str(doc))
        return
    text = doc.read_text(encoding="utf-8")
    check("规范文档存在且含三张扩展 DI 表",
          "协议转换单元DL/T 645-2007扩展协议" in text
          and "（一）变量类" in text and "（三）事件类" in text, "章节缺失")
    check("附录 I.3.3.1 透传定义存在", "I.3.3.1 DL/T 645协议帧" in text, "附录缺失")
    # 格式列/长度列原文与代码登记一致（逐 DI1 首行）
    bad = []
    for code, info in sorted(pv.PV_DI_MAP.items()):
        if code[6:8] != "01":
            continue
        if f"`{info['fmt_col']}`" in f"`{info['fmt_col']}`" and info["fmt_col"] not in text:
            bad.append(code)
        if info["len_col"] and info["len_col"] not in text:
            bad.append(f"{code}(len)")
    check("全部 DI1 首行的数据格式列原文出现在规范文档中", not bad, str(bad[:5]))
    # 逐值 fmt 拼接校验（白名单行除外）
    mismatch = []
    for code, info in sorted(pv.PV_DI_MAP.items()):
        if code[6:8] != "01" or code in pv.FMT_JOIN_SKIP:
            continue
        if "".join(v["fmt"] for v in info["values"]) != info["fmt_col"]:
            mismatch.append(code)
    joined = [c for c, i in pv.PV_DI_MAP.items() if c[6:8] == "01" and c not in pv.FMT_JOIN_SKIP]
    check(f"格式列逐值拼接一致（{len(joined)} 个 DI1 首行校验，"
          f"白名单 {len(pv.FMT_JOIN_SKIP)} 行）", not mismatch, str(mismatch))
    check("白名单行均给出理由",
          all(isinstance(v, str) and v for v in pv.FMT_JOIN_SKIP.values()),
          str(pv.FMT_JOIN_SKIP))
    # 声明长度 = 值字节数之和（动态/歧义行除外）
    dyn = {c for c, i in pv.PV_DI_MAP.items() if i["handler"]}
    bad = []
    for code, info in sorted(pv.PV_DI_MAP.items()):
        if code in dyn:
            continue
        if sum(v["nbytes"] for v in info["values"]) != info["length"]:
            bad.append(code)
    check("固定行声明长度 = 各值字节数之和", not bad, str(bad[:5]))
    # 单一来源：解析器与查询页均调用 merge_pv_di_map
    src = (Path(__file__).resolve().parent.parent / "dlt645_parser.py").read_text(encoding="utf-8")
    lookup_src = (Path(__file__).resolve().parent.parent / "dlt645_di_lookup.py").read_text(encoding="utf-8")
    check("解析器 DI 表经 merge_pv_di_map 合并", "merge_pv_di_map" in src, "未合并")
    check("查询页 DI 表经 merge_pv_di_map 合并", "merge_pv_di_map" in lookup_src, "未合并")
    import re
    di_entry = re.compile(r'"0[234]E6[0-9A-F]{4}"\s*:')
    check("无第二份扩展 DI 清单（解析器/查询页不内联 DI 表字面量）",
          not di_entry.search(src) and not di_entry.search(lookup_src),
          "出现重复清单")


def test_frame_gen_guard():
    """组帧守卫：扩展 DI 的多值块不得套用单值模板（时间/日期/通信地址/数值）。

    背景：扩展 DI 进入共享 DI 表后，`dlt645_frame_schema.build_di_fields` 会把
    `data_type` 当**单值掩码**做启发式，而扩展协议的掩码是多值串（`|` 分隔）→
    运行状态 `NN` 被当「通信地址」、时段调节块被当「日期」、事件块被当「时间」。
    本段钉住守卫（组帧支持该扩展协议属范围外，只做兑底不实现结构化组帧）。
    """
    print("\n[11] 组帧侧守卫（扩展 DI 进入组帧下拉后的模板正确性）")
    from dlt645_frame_schema import build_di_fields, _is_multivalue_dt

    def names(di):
        return [str(x.get("name")) for x in build_di_fields(di)]

    check("_is_multivalue_dt 只识别 '|' 多值掩码",
          _is_multivalue_dt("XXX.X|XXX.X|XXX.X") is True
          and _is_multivalue_dt("XXXXXX.XX") is False
          and _is_multivalue_dt("NNNNNNNNNNNN") is False
          and _is_multivalue_dt("NN") is False)

    # 修复前会被错配的三类（组帧 DI 下拉由同一张表驱动）
    for di, why in (("04E60401", "短全N（运行状态）"),
                    ("04E60B01", "多值时段调节块"),
                    ("03E60101", "多值事件块")):
        check(f"{di}（{why}）走裸字节模板而非单值模板",
              names(di) == ["数据内容"], str(names(di)))

    # 标准 DI 模板零误伤（真键 name 比对）
    for di, want in (("04000401", "通信地址"), ("04000101", "日期"), ("04000102", "时间")):
        check(f"标准 DI {di} 仍为「{want}」", want in names(di), str(names(di)))

    with open("dlt645_di.json", encoding="utf-8") as f:
        std_map = json.load(f).get("di_map", {})
    with_pipe = [k for k, v in std_map.items() if "|" in (v.get("data_type") or "")]
    check("标准 DI 表无 '|' 掩码（守卫零误伤的前提，防表变化使断言失真）",
          not with_pipe, str(with_pipe[:3]))
    mismatched = [k for k, v in std_map.items()
                  if _is_multivalue_dt(v.get("data_type") or "")
                  and set(names(k)) & {"通信地址", "日期", "时间", "数据值"}]
    check("全标准表无「多值掩码套单值模板」错配", not mismatched, str(mismatched[:3]))


def main():
    print("=" * 70)
    print("协议6 光伏协议转换单元 DL/T645-2007 扩展协议解析测试")
    print("=" * 70)
    test_di_map_and_merge()
    test_table_driven_coverage()
    test_variable_golden()
    test_all_vars_block()
    test_di0_semantics()
    test_event_block()
    test_transparent_code()
    test_parameter_and_ambiguous()
    test_fallback_no_regression()
    test_desktop_gui_wrapper()
    test_two_ends_consistency()
    test_doc_consistency()
    test_frame_gen_guard()
    print()
    print("=" * 70)
    if FAILURES:
        print(f"✗ 失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for name in FAILURES:
            print(f"   - {name}")
        sys.exit(1)
    print(f"✓ 全部通过：{PASS} 项")
    print("=" * 70)


if __name__ == "__main__":
    main()
