"""模组化终端功能模块接口协议解析/组帧/校验/静态表测试。

运行：
    pwshu '$env:PYTHONIOENCODING="utf-8"; python -u test/test_modular_iface.py'

约定：
* 静态表断言**逐条对拍协议文档**（附录 C / G.3 / J.3 / K.3 / L.3 / M / D~L / 表2/表11/表13/表18）；
* A-XDR 的字节级依据在 `test/test_modular_iface_axdr.py`（含 698 附录 H.1.1 独立 oracle）；
* 解析器容错契约：长度不符 / FCS 不符 / 截断 / A-XDR 解不动 ⇒ 仍输出已解析字段 + 醒目 `⚠` 行，
  **绝不返回空表**（AGENTS.md §8 陷阱 23）。
"""

import os
import sys

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import protocol_registry  # noqa: E402
from modular_iface_data import (  # noqa: E402
    APDU_NAMES,
    ARRAY_FIELDS,
    CTRL_CODE_NAMES,
    DAR_NAMES,
    DEVICE_SUBIFACE_ALIASES,
    DEVICE_SUBIFACES,
    DIR_PRM_MEANINGS,
    DTA1_NAMES,
    DTA2_NAMES,
    DT_DEFINITIONS,
    DT_NAMES,
    GENERIC_DT,
    IFACE_TYPE_NAMES,
    LINK_RESPONSE_FUNC_CONFIG,
    MODULE_DT,
    PHYSICAL_UNITS,
    PRODUCT_ID,
    STRUCTURE_FIELDS,
    VENDOR_ID,
    decode_dt,
    dt_name,
    unit_text,
)
from modular_iface_frame_gen import (  # noqa: E402
    DT_MODULE_INFO,
    FRAME_TEMPLATES,
    ModularIfaceFrameGenerator,
    build_ack,
    build_frame,
    build_from_template,
    build_get_request,
    build_info,
    build_link_request,
    build_nak,
    dt_code,
    frame_to_hex,
    template_keys,
)
from modular_iface_parser import (  # noqa: E402
    GENERIC_DT_NAMES,
    ModularIfaceParser,
    data_total_len,
    frame_layout,
    is_frame,
    verify_frame,
)
from validator import ModularIfaceValidator  # noqa: E402

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


def blob(rows):
    """行名=解析值的紧凑串（不含说明列）。"""
    return " | ".join(f"{r[0]}={r[2]}" for r in rows)


def has(rows, needle):
    """在整行（6 列全含说明）里找子串。"""
    return any(needle in str(r) for r in rows)


def row_named(rows, name):
    return next((r for r in rows if str(r[0]).strip() == name), None)


PARSER = ModularIfaceParser()
VALIDATOR = ModularIfaceValidator()


# ── 注册表 ────────────────────────────────────────────────────────────


def test_registry():
    section("注册表")
    check(
        "protocol_count >= 13",
        protocol_registry.protocol_count() >= 13,
        str(protocol_registry.protocol_count()),
    )
    spec = protocol_registry.get_protocol(12)
    check("index12 short_name", spec.short_name == "模组化接口", spec.short_name)
    check("parser_key", spec.parser_key == "modular", spec.parser_key)
    check("extract_strategy", spec.extract_strategy == "modular", spec.extract_strategy)
    check(
        "validator_class 含 ModularIface",
        "ModularIfaceValidator" in (spec.validator_class or ""),
        spec.validator_class,
    )
    labels = protocol_registry.combo_labels()
    check("combo 含模组化", any("模组化" in x for x in labels), labels[-1])
    check(
        "lookup_kind",
        protocol_registry.lookup_builder_method(spec.lookup_kind)
        == "_create_modular_iface_lookup_content",
        protocol_registry.lookup_builder_method(spec.lookup_kind),
    )
    check("frame_gen_mode", spec.frame_gen_mode == "modular", spec.frame_gen_mode)
    check("preset_mode", spec.preset_mode == "modular", spec.preset_mode)
    check(
        "protocols_with_frame_gen 含 12",
        12 in protocol_registry.protocols_with_frame_gen(),
        str(protocol_registry.protocols_with_frame_gen()),
    )


# ── 静态表：逐条对拍协议文档 ─────────────────────────────────────────


def test_static_tables():
    section("静态表：附录 C 通用信息类（10 条逐条对拍）")
    doc_generic = {
        0x0000: "模块信息",
        0x0001: "链路协商信息",
        0x0002: "协议版本",
        0x0003: "电源状态",
        0x0004: "文件传输状态",
        0x0100: "时钟",
        0x0200: "硬件初始化",
        0x0201: "参数初始化",
        0x0202: "数据初始化",
        0x0203: "文件传输",
    }
    check("条数 = 10", len(GENERIC_DT) == 10, str(len(GENERIC_DT)))
    check(
        "DT 码与名称逐条一致",
        {dt: v["name"] for dt, v in GENERIC_DT.items()} == doc_generic,
        str({dt: v["name"] for dt, v in GENERIC_DT.items()}),
    )
    check("所属模块均为通用信息类", all(v["module"] == "通用信息类" for v in GENERIC_DT.values()))
    check("0002 定义 = long-unsigned", GENERIC_DT[0x0002]["definition"] == "long-unsigned")
    check("0100 定义 = date_time", GENERIC_DT[0x0100]["definition"] == "date_time")
    check("0200 定义 = NULL", GENERIC_DT[0x0200]["definition"] == "NULL")
    check(
        "0000 定义含 7 个成员名",
        all(k in GENERIC_DT[0x0000]["definition"] for k in ("模块设备型号", "模块设备ID", "厂商编码")),
        GENERIC_DT[0x0000]["definition"][:40],
    )

    section("静态表：附录 G.3 / J.3 / K.3 / L.3 模块信息类（11 条）")
    doc_module = {
        0x4000: ("遥信状态", "遥信脉冲模块"),
        0x4001: ("上一次脉冲计数和时间", "遥信脉冲模块"),
        0x4002: ("脉冲计数及统计时间", "遥信脉冲模块"),
        0x4100: ("遥信脉冲功能配置", "遥信脉冲模块"),
        0x4101: ("遥信防抖时间", "遥信脉冲模块"),
        0x7100: ("继电器输出模式", "控制模块"),
        0x7101: ("继电器输出脉冲宽度", "控制模块"),
        0x8000: ("模拟量采样", "模拟量采集模块"),
        0x9000: ("回路状态巡检模块工况信息", "回路状态巡检模块"),
        0x9001: ("回路状态巡检模块事件发生时工况信息", "回路状态巡检模块"),
        0x9002: ("回路状态巡检模块运行信息", "回路状态巡检模块"),
    }
    check("条数 = 11", len(MODULE_DT) == 11, str(len(MODULE_DT)))
    check(
        "(DT, 名称, 所属模块) 逐条一致",
        {dt: (v["name"], v["module"]) for dt, v in MODULE_DT.items()} == doc_module,
        str({dt: (v["name"], v["module"]) for dt, v in MODULE_DT.items()}),
    )
    check("DT_NAMES 合并 21 条", len(DT_NAMES) == 21, str(len(DT_NAMES)))
    check("DT_DEFINITIONS 合并 21 条", len(DT_DEFINITIONS) == 21, str(len(DT_DEFINITIONS)))
    check("7100 定义 = enum{脉冲模式/电平模式}", "脉冲模式" in MODULE_DT[0x7100]["definition"])
    check("4101 单位 = ms", "ms" in MODULE_DT[0x4101]["definition"])
    check("8000 含 Scaler_Unit", "Scaler_Unit" in MODULE_DT[0x8000]["definition"])

    section("静态表：表11 DAR（**只 4 个值**，勿从其它协议借表）")
    check(
        "DAR_NAMES 恰为表11 的 4 项",
        DAR_NAMES == {0: "成功", 1: "拒绝读写", 2: "信息类未定义", 255: "其它"},
        str(DAR_NAMES),
    )
    check("键集合 = {0,1,2,255}", set(DAR_NAMES) == {0, 1, 2, 255}, str(sorted(DAR_NAMES)))

    section("静态表：表2 控制码 / 表1 DIR+PRM / 表13 APDU（8 类）")
    check("控制码名称", CTRL_CODE_NAMES == {0x00: "确认帧", 0x01: "否认帧", 0x02: "信息帧"}, str(CTRL_CODE_NAMES))
    check("DIR/PRM 组合 4 种", len(DIR_PRM_MEANINGS) == 4 and set(DIR_PRM_MEANINGS) == {(0, 0), (0, 1), (1, 0), (1, 1)})
    check("(0,1) = 终端发起的请求", DIR_PRM_MEANINGS[(0, 1)] == "终端发起的请求")
    check("(1,1) = 功能模块对终端请求或通知的响应", DIR_PRM_MEANINGS[(1, 1)] == "功能模块对终端请求或通知的响应")
    check("APDU 8 类", len(APDU_NAMES) == 8 and sorted(APDU_NAMES) == [1, 2, 3, 4, 129, 130, 131, 132])
    check("APDU[1] 含 LinkRequest", "LinkRequest" in APDU_NAMES[1], APDU_NAMES[1])
    check("APDU[132] 含 ReportResponse", "ReportResponse" in APDU_NAMES[132], APDU_NAMES[132])

    section("静态表：附录 M 物理单位（1~75 + 254 + 255）")
    check("条数 = 77", len(PHYSICAL_UNITS) == 77, str(len(PHYSICAL_UNITS)))
    check("代码覆盖 1..75", all(i in PHYSICAL_UNITS for i in range(1, 76)))
    doc_units = {
        1: ("a", "时间", "年"),
        5: ("h", "时间", "小时"),
        7: ("s", "时间（t）", "秒"),
        9: ("℃", "温度（T）", "摄氏度"),
        24: ("bar", "压力（p）", "巴"),
        27: ("W", "有功功率（P）", "瓦"),
        28: ("kW", "有功功率（P）", "千瓦"),
        33: ("kWh", "有功能量；rw，有功电能表常数或脉冲值", "千瓦·时"),
        36: ("A", "电流（I）", "安培"),
        38: ("V", "电压（U）", "伏特"),
        41: ("Ω", "电阻（R）", "欧姆"),
        42: ("Ωm2/m", "电阻率（ρ）", "欧姆米"),
        51: ("%", "百分比", "百分之"),
        53: ("dBm", "分贝毫瓦", ""),
        56: ("ms", "毫秒", "毫秒"),
        58: ("V2h", "电压平方小时；rU2h，电压平方小时表计常数或脉冲值", "电压平方·时"),
        67: ("S, mho", "电导系数", "欧姆的倒数"),
        73: ("Wh", "有功能量；rw，有功电能表常数或脉冲值", "瓦·时"),
    }
    for code, want in doc_units.items():
        check(f"单位 {code} 逐条一致", PHYSICAL_UNITS[code] == want, str(PHYSICAL_UNITS[code]))
    check("254 = 其他单位", PHYSICAL_UNITS[254] == ("其他单位", "", ""), str(PHYSICAL_UNITS[254]))
    check(
        "255 = 无单位、缺单位、计数",
        PHYSICAL_UNITS[255] == ("无单位、缺单位、计数", "", ""),
        str(PHYSICAL_UNITS[255]),
    )
    check("unit_text(5) = h（小时）", unit_text(5) == "h（小时）", unit_text(5))
    check("unit_text(38) = V（伏特）", unit_text(38) == "V（伏特）", unit_text(38))
    check("unit_text(255) = 无单位、缺单位、计数", unit_text(255) == "无单位、缺单位、计数", unit_text(255))
    check("unit_text(未知) 有提示", "未定义" in unit_text(200), unit_text(200))

    section("静态表：附录 D/E/F/G/J/K/L 设备子接口 + 附录 B VID/PID + 表18")
    expected_rows = {
        "远程通信模块（附录D·表24）": 4,
        "本地通信模块（附录E·表25）": 3,
        "RS-485通信模块（附录F·表26）": 4,
        "遥信脉冲模块（附录G·表27）": 2,
        "控制模块（附录J·表28）": 2,
        "模拟量采集模块（附录K·表29）": 2,
        "回路状态巡检模块（附录L·表30）": 2,
    }
    check("子接口表 7 张", set(DEVICE_SUBIFACES) == set(expected_rows), str(sorted(DEVICE_SUBIFACES)))
    for key, rows_n in expected_rows.items():
        check(f"{key} 行数 = {rows_n}", len(DEVICE_SUBIFACES[key]) == rows_n, str(len(DEVICE_SUBIFACES[key])))
    check(
        "附录D 第4行 = 4/CDC-ECM/网络数据通信通道",
        DEVICE_SUBIFACES["远程通信模块（附录D·表24）"][3] == (4, "CDC-ECM", "网络数据通信通道"),
        str(DEVICE_SUBIFACES["远程通信模块（附录D·表24）"][3]),
    )
    check(
        "附录F 含 N+1 可变行",
        DEVICE_SUBIFACES["RS-485通信模块（附录F·表26）"][3] == ("N+1", "CDC-ACM", "485-N通道"),
        str(DEVICE_SUBIFACES["RS-485通信模块（附录F·表26）"][3]),
    )
    check("附录 H/I 记为「见附录 F」", len(DEVICE_SUBIFACE_ALIASES) == 2, str(DEVICE_SUBIFACE_ALIASES))
    check("VID = 0x3C93", VENDOR_ID == 0x3C93, hex(VENDOR_ID))
    check("PID = 0xFFFF", PRODUCT_ID == 0xFFFF, hex(PRODUCT_ID))
    check("接口类型 3 种", IFACE_TYPE_NAMES == {1: "CDC-ACM", 2: "CDC-ECM", 3: "HID"}, str(IFACE_TYPE_NAMES))
    check("功能配置 10 种（0~9）", sorted(LINK_RESPONSE_FUNC_CONFIG) == list(range(10)))
    check("功能配置 2 = PLC/RF通信", LINK_RESPONSE_FUNC_CONFIG[2] == "PLC/RF通信")
    check("功能配置 9 = RS232通信", LINK_RESPONSE_FUNC_CONFIG[9] == "RS232通信")
    check("DTA1 0~9 名称齐全", sorted(DTA1_NAMES) == list(range(10)))
    check("DTA2 0/1/2", DTA2_NAMES == {0: "只读", 1: "读-写", 2: "只写"}, str(DTA2_NAMES))
    check("STRUCTURE_FIELDS[0000] = 7 成员", len(STRUCTURE_FIELDS[0x0000]) == 7)
    check("STRUCTURE_FIELDS[9000] = 2 + 30", len(STRUCTURE_FIELDS[0x9000]) == 32, str(len(STRUCTURE_FIELDS[0x9000])))
    check("STRUCTURE_FIELDS[9001] = 64", len(STRUCTURE_FIELDS[0x9001]) == 64, str(len(STRUCTURE_FIELDS[0x9001])))
    check("ARRAY_FIELDS[8000] = 模拟量数值/单位", ARRAY_FIELDS[0x8000] == ("模拟量数值", "模拟量单位及换算"))
    check(
        "main_gui 兼容视图 GENERIC_DT_NAMES 键为 (DTA2, DTB)",
        GENERIC_DT_NAMES[(1, 0)] == "时钟" and GENERIC_DT_NAMES[(0, 0)] == "模块信息",
        str(GENERIC_DT_NAMES),
    )


def test_decode_dt():
    section("DT 解码（**大端**，A-XDR long-unsigned）")
    info = decode_dt(b"\x00\x00")
    check("DT 0000 = 模块信息", info["dt"] == 0 and info["name"] == "模块信息", str(info["name"]))
    check("DTA1 = 0 通用信息类", info["dta1"] == 0 and info["dta1_name"] == "通用信息类")
    check("DTA2 = 0 只读", info["dta2"] == 0 and info["dta2_name"] == "只读")
    info = decode_dt(b"\x01\x00")
    check(
        "DT 0100（大端）= 时钟（旧实现按小端读会解成 0001）",
        (info["dta1"], info["dta2"], info["dtb"], info["name"]) == (0, 1, 0x00, "时钟"),
        info["text"],
    )
    check("说明含 DTA2=1H(读-写)", "DTA2=1H(读-写)" in info["text"], info["text"])
    info = decode_dt(b"\x40\x00")
    check(
        "DT 4000 = 遥信脉冲模块/遥信状态",
        (info["dta1"], info["dta2"], info["dtb"], info["name"]) == (4, 0, 0x00, "遥信状态"),
        info["text"],
    )
    info = decode_dt(b"\x80\x00")
    check("DT 8000 = 模拟量采集模块/模拟量采样", info["dta1"] == 8 and info["name"] == "模拟量采样", info["text"])
    info = decode_dt(b"\x90\x00")
    check("DT 9000 = 回路状态巡检模块", info["dta1"] == 9, info["text"])
    info = decode_dt(b"\x71\x00")
    check("DT 7100 = 控制模块/继电器输出模式", info["dta1"] == 7 and info["name"] == "继电器输出模式", info["text"])
    info = decode_dt(b"\x0A\x00")
    check("未定义 DT 不臆造名称", info["name"] == "" and "文档未定义" in info["text"], info["text"])
    info = decode_dt(b"\x00")
    check("DT 长度不足有提示", "长度不足" in info["text"], info["text"])
    check("dt_name(0x0000)", dt_name(0x0000) == "模块信息(0x0000)", dt_name(0x0000))
    check("dt_name(None)", dt_name(None) == "未知", dt_name(None))


# ── 组帧 → 解析闭环 ──────────────────────────────────────────────────


def test_roundtrip_templates():
    section("模板组帧 → 解析闭环（逐模板 axdr_tail = 0 且 FCS 通过）")
    check("模板 >= 8 条", len(FRAME_TEMPLATES) >= 8, str(len(FRAME_TEMPLATES)))
    for key in template_keys():
        fr = build_from_template(key, fid=7)
        check(f"[{key}] 68H 起 / 16H 止", fr[0] == 0x68 and fr[-1] == 0x16, frame_to_hex(fr)[:44])
        check(f"[{key}] 整帧 = L + 8", data_total_len(fr) == len(fr), f"{data_total_len(fr)}/{len(fr)}")
        check(f"[{key}] is_frame", is_frame(fr))
        rows = PARSER.parse(fr)
        meta = PARSER.last_meta
        check(f"[{key}] 非空表", len(rows) >= 6, str(len(rows)))
        check(f"[{key}] FCS 通过（meta.fcs_ok）", meta["fcs_ok"] is True)
        check(f"[{key}] structure_ok", meta["structure_ok"] is True)
        check(f"[{key}] meta.valid", meta["valid"] is True, str(meta))
        check(f"[{key}] axdr_tail = 0（编码假设自洽）", meta["axdr_tail"] in (0, None), str(meta["axdr_tail"]))
        check(f"[{key}] 无 ⚠ 行", not has(rows, "⚠"), blob(rows)[-120:])
        check(f"[{key}] FID = 7", "FID=7" in blob(rows), "")
        summary = PARSER.get_summary(fr)
        check(f"[{key}] 摘要非空且含方向", ("终端" in summary or "模块" in summary) and len(summary) > 6, summary)


def test_roundtrip_fields():
    section("模板字段逐项回读")
    rows = PARSER.parse(build_from_template("get_module_info", fid=3))
    check("DT = 0x0000", "0x0000" in blob(rows), blob(rows))
    check("信息类名称 = 模块信息", has(rows, "模块信息"), "")
    check("APDU = 数据读取请求", "数据读取请求" in blob(rows), "")
    check("方向 终端→模块", "终端→模块" in PARSER.get_summary(build_from_template("get_module_info")), "")

    rows = PARSER.parse(build_from_template("get_link_neg"))
    check("DT 0001 = 链路协商信息", has(rows, "链路协商信息"), "")

    rows = PARSER.parse(build_from_template("get_clock"))
    check("DT 0100 = 时钟", has(rows, "时钟"), "")

    rows = PARSER.parse(build_from_template("link_req", fid=0))
    txt = blob(rows)
    for field in ("协议版本号", "终端设备型号", "终端设备ID", "最大发送缓冲区长度", "最大接收缓冲区长度", "并发传输窗口数"):
        check(f"LinkRequest 含 {field}", field in txt, "")
    check("LinkRequest 型号 = TERMINAL", "TERMINAL" in txt, "")
    check("LinkRequest 版本 = 1", "协议版本号=1" in txt, txt[:160])

    rows = PARSER.parse(build_from_template("link_rsp"))
    txt = blob(rows)
    check("LinkResponse 含虚拟通道工作模式", "虚拟通道工作模式" in txt, "")
    check("LinkResponse 通道1 = CDC-ACM", "CDC-ACM" in txt, "")
    check("LinkResponse 功能配置 = PLC/RF通信", "PLC/RF通信" in txt, "")
    check("LinkResponse 型号 = MODULE", "MODULE" in txt, "")

    rows = PARSER.parse(build_from_template("get_rsp_module_info"))
    txt = blob(rows)
    for field, value in (
        ("模块设备型号", "MOD-TEST"),
        ("模块设备ID", "ID0001"),
        ("软件版本", "16909060"),
        ("硬件版本", "168496141"),
        ("厂商编码", "CREEP"),
    ):
        check(f"模块信息成员 {field}", field in txt and value in txt, "")
    check("软件发布日期 = 2024-01-15", "2024-01-15" in txt, "")
    check("硬件发布日期 = 2023-06-20", "2023-06-20" in txt, "")
    check("结构成员名取自 STRUCTURE_FIELDS（不是「成员1」）", "成员1=" not in txt, "")

    rows = PARSER.parse(build_from_template("get_rsp_dar"))
    check("DAR = 信息类未定义", "信息类未定义" in blob(rows), blob(rows))
    check("DAR 说明指向表11", has(rows, "表11"), "")

    rows = PARSER.parse(build_from_template("set_clock"))
    check("SetRequest 含 date_time 值", "2026-09-23 10:30:00.000" in blob(rows), blob(rows))

    rows = PARSER.parse(build_from_template("report_power"))
    check("枚举值翻中文：1（掉电）", "1（掉电）" in blob(rows), blob(rows))
    check("ReportNotification 说明含 DT 0003", has(rows, "电源状态"), "")

    rows = PARSER.parse(build_from_template("report_rsp"))
    check("ReportResponse DT = 电源状态", has(rows, "电源状态"), blob(rows))


def test_frame_sizes():
    section("ACK / NAK / 超长数据域")
    ack = build_ack(fid=1)
    check("ACK 整帧 = 8 字节", len(ack) == 8, str(len(ack)))
    check("ACK L = 0", ack[1] == 0 and ack[2] == 0, f"{ack[1]:02X}{ack[2]:02X}")
    check("ACK 控制码 = 00H", (ack[3] & 0x3F) == 0x00, hex(ack[3] & 0x3F))
    rows = PARSER.parse(ack)
    check("ACK 无「数据域」内容", row_named(rows, "数据域")[1] == "-", str(row_named(rows, "数据域")))
    check("ACK 摘要含确认帧", "确认帧" in PARSER.get_summary(ack), PARSER.get_summary(ack))

    nak = build_nak(2, fid=2)
    rows = PARSER.parse(nak)
    check("NAK L = 2", (nak[1] | (nak[2] << 8)) == 2, str(nak[1] | (nak[2] << 8)))
    check("NAK 错误信息码 = 0x0002", "0x0002" in blob(rows), blob(rows))
    check("NAK 摘要含错误码", "错误码=0x0002" in PARSER.get_summary(nak), PARSER.get_summary(nak))

    try:
        build_frame(b"\x00" * 4096)
        check("超长数据域应报错（不截断）", False)
    except ValueError as exc:
        check("超长数据域报错（不截断）", "4095" in str(exc), str(exc))

    gen = ModularIfaceFrameGenerator()
    check("类封装 build_ack 与函数一致", gen.build_ack(fid=1) == ack)
    check("类封装 build_get_request 一致", gen.build_get_request(DT_MODULE_INFO) == build_get_request(DT_MODULE_INFO))
    check("类封装模板数一致", len(gen.templates()) == len(FRAME_TEMPLATES))
    check(
        "dt_code 与 decode_dt 互逆",
        decode_dt(dt_code(4, 1, 0x01).to_bytes(2, "big"))["dtb"] == 0x01,
        hex(dt_code(4, 1, 0x01)),
    )


# ── 控制域 ────────────────────────────────────────────────────────────


def test_control_field():
    section("控制域：表1 四种 DIR/PRM 组合 + 表2 控制码 + FID")
    for (dir_bit, prm), meaning in DIR_PRM_MEANINGS.items():
        fr = build_frame(b"", dir_bit=dir_bit, prm=prm, func=0x00, fid=9)
        rows = PARSER.parse(fr)
        ctrl = row_named(rows, "控制域")
        check(f"DIR={dir_bit} PRM={prm} 说明含表1 文案", meaning in str(ctrl[3]), str(ctrl[3]))
        check(f"DIR={dir_bit} PRM={prm} 解析值含 FID=9", "FID=9" in str(ctrl[2]), str(ctrl[2]))
    rows = PARSER.parse(build_info(build_get_request(0), dir_bit=0, prm=1, fid=5))
    check("子行 传输方向(DIR) = 0", row_named(rows, "传输方向(DIR)")[2] == "0")
    check("子行 启动标志(PRM) = 1", row_named(rows, "启动标志(PRM)")[2] == "1")
    check("子行 控制码 = 信息帧", row_named(rows, "控制码")[2] == "信息帧")
    check("子行 帧序号(FID) = 5", row_named(rows, "帧序号(FID)")[2] == "5")
    check("控制域说明含表2 文案", "信息帧" in str(row_named(rows, "控制域")[3]))
    # 保留控制码
    fr = build_frame(b"", dir_bit=1, prm=0, func=0x3F)
    rows = PARSER.parse(fr)
    check("保留控制码有提示", "保留(3FH)" in blob(rows), blob(rows)[:200])


# ── 容错（AGENTS.md §8 陷阱 23）──────────────────────────────────────


def test_tolerance():
    section("容错：长度不符 / FCS 不符 / 截断 / A-XDR 解不动 → 仍输出字段 + ⚠ 行（不空白）")
    # 1) 长度域比实际大 2 字节（尾部仍完整）
    good = build_from_template("get_module_info", fid=1)
    apdu = good[5:-3]
    mid = (len(apdu) + 2).to_bytes(2, "little") + good[3:5] + apdu
    from modular_iface_axdr import calc_fcs as _fcs

    short = b"\x68" + mid + _fcs(mid).to_bytes(2, "little") + b"\x16"
    rows = PARSER.parse(short)
    check("长度不符：表非空", len(rows) >= 8, str(len(rows)))
    check("长度不符：给出 ⚠ 行", has(rows, "⚠ 帧长度与长度域不符"), blob(rows)[:200])
    check("长度不符：仍解析出 APDU", "数据读取请求" in blob(rows), "")
    check("长度不符：meta.structure_ok False", PARSER.last_meta["structure_ok"] is False)
    check("长度不符：meta.valid False", PARSER.last_meta["valid"] is False)
    check("长度不符：FCS 仍按实际帧尾校验", PARSER.last_meta["fcs_ok"] is True, str(PARSER.last_meta))

    # 2) FCS 写错
    bad = bytearray(good)
    bad[-2] ^= 0xFF
    rows = PARSER.parse(bytes(bad))
    check("FCS 不符：表非空", len(rows) >= 8)
    check("FCS 不符：说明给「校验错误」与期望值", has(rows, "校验错误") and has(rows, "期望0x"), "")
    check("FCS 不符：meta.fcs_ok False", PARSER.last_meta["fcs_ok"] is False)
    check("FCS 不符：structure_ok 仍 True", PARSER.last_meta["structure_ok"] is True)
    check("FCS 不符：valid False", PARSER.last_meta["valid"] is False)
    check("FCS 不符：仍能读出 DT 名称", has(rows, "模块信息"), "")

    # 3) APDU 被截断但帧结构自洽（L/FCS/结束符都对，只有 APDU 内部缺字节）
    full = build_link_request()
    cut = full[:-1]  # 少最后一个「并发传输窗口数」
    mid2 = len(cut).to_bytes(2, "little") + b"\x42\x01" + cut
    trunc = b"\x68" + mid2 + _fcs(mid2).to_bytes(2, "little") + b"\x16"
    rows = PARSER.parse(trunc)
    check("APDU 截断：表非空", len(rows) >= 8, str(len(rows)))
    check("APDU 截断：有 APDU 行", "应用层数据单元(APDU)" in blob(rows), "")
    check("APDU 截断：给出 ⚠ 未解完行", has(rows, "⚠ APDU 字段未解完"), blob(rows)[-200:])
    check("APDU 截断：已解出的字段仍保留", has(rows, "协议版本号") and has(rows, "终端设备型号"), blob(rows))
    check("APDU 截断：帧结构本身自洽", PARSER.last_meta["structure_ok"] is True and PARSER.last_meta["fcs_ok"] is True)
    check("APDU 截断：meta.apdu_ok False", PARSER.last_meta["apdu_ok"] is False, str(PARSER.last_meta))
    check("APDU 截断：meta.valid False", PARSER.last_meta["valid"] is False)

    # 4) 确认帧带数据域 / 否认帧数据域不完整
    fr = build_frame(b"\x01", dir_bit=1, prm=1, func=0x00)
    rows = PARSER.parse(fr)
    check("确认帧带数据域 → ⚠ 行", has(rows, "⚠ 确认帧不应有数据域"), blob(rows)[:200])
    fr = build_frame(b"\x05", dir_bit=1, prm=1, func=0x01)
    rows = PARSER.parse(fr)
    check("否认帧数据域 1 字节 → ⚠ 行", has(rows, "⚠ 否认帧数据域不完整"), blob(rows)[:200])
    fr = build_frame(b"", dir_bit=0, prm=1, func=0x02)
    rows = PARSER.parse(fr)
    check("信息帧无 APDU → ⚠ 行", has(rows, "⚠ 信息帧缺少 APDU"), blob(rows)[:200])

    # 5) 空帧 / 起始符错 / 过短
    rows = PARSER.parse(b"")
    check("空帧 → 单行 ⚠ 空帧", len(rows) == 1 and has(rows, "⚠ 空帧"), str(rows))
    rows = PARSER.parse(b"\x00\x01\x02\x03\x04\x05\x06\x07\x16")
    check("起始符错 → ⚠ 帧结构错误", has(rows, "⚠ 帧结构错误"), blob(rows)[:120])
    rows = PARSER.parse(b"\x68\x00\x00")
    check("3 字节 → ⚠ 帧不完整", has(rows, "⚠ 帧不完整"), blob(rows)[:120])
    check("空帧 meta.valid False", PARSER.last_meta["valid"] is False)

    # 6) 长度域保留位非 0
    mid3 = bytes.fromhex("0010") + b"\x40\x01"
    fr = b"\x68" + mid3 + _fcs(mid3).to_bytes(2, "little") + b"\x16"
    rows = PARSER.parse(fr)
    check("保留位非 0 → 长度域说明提示", has(rows, "保留位非 0"), blob(rows)[:160])
    check("保留位非 0 → meta 标记", PARSER.last_meta["reserved_bits_nonzero"] is True)
    check("保留位非 0 → valid False", PARSER.last_meta["valid"] is False)


def test_meta_not_dead_code():
    section("parse() 收尾的 meta 不再是死代码")
    fr = build_from_template("get_module_info")
    PARSER.parse(fr)
    meta = PARSER.last_meta
    check(
        "last_meta 含 valid/fcs_ok/structure_ok/length_ok",
        all(k in meta for k in ("valid", "fcs_ok", "structure_ok", "length_ok")),
        str(sorted(meta)),
    )
    check("合法帧 fcs_ok True", meta["fcs_ok"] is True)
    check("合法帧 valid True", meta["valid"] is True)
    check("合法帧 axdr_tail 0", meta["axdr_tail"] == 0)
    bad = bytearray(fr)
    bad[-2] ^= 0xFF
    PARSER.parse(bytes(bad))
    check("坏帧 fcs_ok 可被读到（抓「死代码」回归）", PARSER.last_meta["fcs_ok"] is False)


# ── 校验器 ────────────────────────────────────────────────────────────


def test_validator():
    section("校验器")
    fr = build_from_template("get_module_info", fid=1)
    vr = VALIDATOR.verify(fr)
    by_name = {i.name: i for i in vr.checks}
    check("整体通过", vr.valid is True, vr.summary())
    for want in ("起始字符", "长度域", "帧长度", "结束字符", "帧校验FCS", "控制码", "APDU解析"):
        check(f"含检查项 {want}", want in by_name, str(list(by_name)))
    check("FCS PASS", by_name["帧校验FCS"].level.name == "PASS", str(by_name["帧校验FCS"]))
    check("APDU解析 PASS", by_name["APDU解析"].level.name == "PASS", str(by_name["APDU解析"]))
    check("帧长度含整帧字节数", "整帧" in by_name["帧长度"].message, by_name["帧长度"].message)

    bad = bytearray(fr)
    bad[-2] ^= 0xFF
    vr_bad = VALIDATOR.verify(bytes(bad))
    check("坏 FCS → 整体 FAIL", vr_bad.valid is False, vr_bad.summary())
    check(
        "坏 FCS → FCS 项 FAIL 且给出期望值",
        {i.name: i for i in vr_bad.checks}["帧校验FCS"].level.name == "FAIL",
        str({i.name: i for i in vr_bad.checks}["帧校验FCS"]),
    )

    # 保留位非 0 → WARN（不是 FAIL）
    from modular_iface_axdr import calc_fcs as _fcs

    mid = bytes.fromhex("0010") + b"\x40\x01"
    fr_r = b"\x68" + mid + _fcs(mid).to_bytes(2, "little") + b"\x16"
    vr_r = VALIDATOR.verify(fr_r)
    by_r = {i.name: i for i in vr_r.checks}
    check("保留位非 0 → 有 WARN 项", "长度域保留位" in by_r and by_r["长度域保留位"].level.name == "WARN", str(by_r))
    check("保留位非 0 → 整体 FAIL", vr_r.valid is False)

    # 结束符错
    fr_e = bytearray(fr)
    fr_e[-1] = 0x17
    vr_e = VALIDATOR.verify(bytes(fr_e))
    by_e = {i.name: i for i in vr_e.checks}
    check("结束符错 → FAIL", by_e["结束字符"].level.name == "FAIL", str(by_e["结束字符"]))

    vr_empty = VALIDATOR.verify(b"")
    check("空帧 → 整体 FAIL", vr_empty.valid is False and vr_empty.checks[0].name == "起始字符")

    # 与解析器 meta 同源
    PARSER.parse(fr)
    vr2 = VALIDATOR.verify(fr)
    check(
        "structure_ok 与解析器 meta 同源",
        frame_layout(fr)["structure_ok"] == PARSER.last_meta["structure_ok"] == True,  # noqa: E712
    )
    check("validator.valid == frame_layout.ok ∧ APDU 自洽", vr2.valid == frame_layout(fr)["ok"])


# ── verify_frame / 基础工具 ──────────────────────────────────────────


def test_verify_frame_and_utils():
    section("verify_frame / is_frame / data_total_len")
    fr = build_from_template("get_clock")
    v = verify_frame(fr)
    check("verify_frame ok", v["ok"] is True, str(v))
    check("verify_frame apdu_name", v["apdu_name"] == "GetRequest", str(v["apdu_name"]))
    check("verify_frame axdr_tail = 0", v["axdr_tail"] == 0, str(v["axdr_tail"]))
    check("verify_frame fcs_ok", v["fcs_ok"] is True)
    check("verify_frame l_matches", v["l_matches"] is True)
    check("verify_frame control.code = 2", v["control"]["code"] == 0x02, str(v["control"]))
    v_empty = verify_frame(b"")
    check("空帧 verify_frame 给原因", v_empty["ok"] is False and "空帧" in v_empty["reason"], v_empty["reason"])
    v_short = verify_frame(build_ack(fid=1))
    check("ACK verify_frame ok", v_short["ok"] is True, str(v_short))
    check("非68 verify_frame 给原因", verify_frame(b"\x00" * 9)["ok"] is False)

    check("data_total_len 非68 → 0", data_total_len(b"\x00\x00\x00") == 0)
    check("data_total_len 过短 → 0", data_total_len(b"\x68") == 0)
    check("is_frame 对合法帧 True", is_frame(fr) is True)
    check("is_frame 对缺尾 False", is_frame(fr[:-1]) is False)
    check("is_frame 对非68 False", is_frame(b"\x00" * len(fr)) is False)


def test_frame_gen_gui():
    """组帧页接线冒烟（offscreen）：模式切换 / 模板生成 / 快照。"""
    section("组帧 GUI（offscreen）")
    import frame_gen_widget as fgw

    class _FakeMB:
        calls = []

        @staticmethod
        def warning(*a, **k):
            _FakeMB.calls.append(("warning", a[2] if len(a) > 2 else ""))

        @staticmethod
        def critical(*a, **k):
            _FakeMB.calls.append(("critical", a[2] if len(a) > 2 else ""))

        @staticmethod
        def information(*a, **k):
            _FakeMB.calls.append(("information", a[2] if len(a) > 2 else ""))

    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])  # noqa: F841
    fgw.QMessageBox = _FakeMB
    w = fgw.FrameGenWidget()
    w.set_protocol_mode("modular")
    check("protocol_mode == modular", w.protocol_mode == "modular", w.protocol_mode)
    check("模板下拉可见", not w.modular_combo.isHidden())
    check("帧配置面板可见", not w.modular_config_group.isHidden())
    check("标题=命令模板选择", w.cmd_select_group.title() == "命令模板选择",
          w.cmd_select_group.title())
    check("字段模式区隐藏", w.mode_group.isHidden())
    tpl_count = sum(
        1 for i in range(w.modular_combo.count())
        if w.modular_combo.itemData(i) not in (None, "_custom_")
    )
    check("模板数 >= 8", tpl_count >= 8, str(tpl_count))
    check("含自定义项", any(
        w.modular_combo.itemData(i) == "_custom_" for i in range(w.modular_combo.count())
    ))

    _FakeMB.calls.clear()
    for i in range(w.modular_combo.count()):
        key = w.modular_combo.itemData(i)
        if not key:
            continue
        w.modular_combo.setCurrentIndex(i)
        w._generate_modular_frame()
        hex_s = w.result_hex.toPlainText().replace(" ", "")
        ok = hex_s.startswith("68") and hex_s.endswith("16") and len(hex_s) % 2 == 0
        check(f"模板 {key} 组帧 68…16", ok, hex_s[:40])
        if ok:
            fr = bytes.fromhex(hex_s)
            rows = PARSER.parse(fr)
            check(f"模板 {key} 解析有字段", len(rows) >= 8, str(len(rows)))
            vr = VALIDATOR.verify(fr)
            check(f"模板 {key} 校验通过", vr.valid, vr.summary())
    check("组帧无错误弹窗", not _FakeMB.calls, str(_FakeMB.calls))

    for i in range(w.modular_combo.count()):
        if w.modular_combo.itemData(i) == "_custom_":
            w.modular_combo.setCurrentIndex(i)
            break
    w.modular_dta1.setText("0")
    w.modular_dta2.setText("0")
    w.modular_dtb.setText("00")
    w.modular_data.clear()
    w._generate_modular_frame()
    hex_c = w.result_hex.toPlainText().replace(" ", "")
    check("自定义空 Data → Get 帧", hex_c.startswith("68") and hex_c.endswith("16"), hex_c)

    snap = w.get_config_snapshot()
    check("快照含 modular", "modular" in snap and snap["modular"].get("dir") is not None,
          str(snap.get("modular")))
    w.apply_config_snapshot(snap)
    check("快照回放不抛异常", True)
    w.deleteLater()


def test_summary_wiring():
    section("[S] 批量摘要/类型列接线（协议12 专属分支）")

    # 用未绑定方法宿主（不构建 MainWindow）：两个摘要函数都不读 widget
    import main_gui

    class _Host:
        _get_summary_from_table_data = main_gui.MainWindow._get_summary_from_table_data
        _get_frame_type_name = main_gui.MainWindow._get_frame_type_name
        current_protocol = 12

    host = _Host()
    parser = ModularIfaceParser()

    info = bytes.fromhex("6803004200020000 0C4616".replace(" ", ""))
    td = parser.parse_to_table(info)
    summ = host._get_summary_from_table_data(td, 12)
    check("信息帧摘要含方向", "终端→模块" in summ, summ)
    check("信息帧摘要含控制码", "信息帧" in summ, summ)
    check("信息帧摘要含信息类名（单一来源 dt_name）", "信息类:模块信息" in summ, summ)
    check("信息帧摘要含 APDU 名", "GetRequest" in summ, summ)
    check("信息帧摘要来自专属分支（不再走前 4 字段兜底）",
          "68" not in summ and "起头" not in summ, summ)

    # ACK 帧没有 APDU ⇒ 仍要给出可读结果（AC4.2）
    ack = bytes.fromhex("680000000101004216".replace(" ", ""))
    td_ack = parser.parse_to_table(ack)
    summ_ack = host._get_summary_from_table_data(td_ack, 12)
    check("ACK 摘要非空且可读", bool(summ_ack) and summ_ack != "-", summ_ack)
    check("ACK 摘要含「确认帧」", "确认帧" in summ_ack, summ_ack)

    # 类型列：不能落到兜底分支（注册表展示名以“[12]”开头，split 会得到“[12]”）
    t_info = host._get_frame_type_name(td, "成功", 12)
    check("类型列不出现“[12]”", "[12]" not in t_info, t_info)
    check("类型列为 APDU 名", "GetRequest" in t_info, t_info)
    t_ack = host._get_frame_type_name(td_ack, "成功", 12)
    check("ACK 类型列为控制码名", t_ack == "确认帧", t_ack)
    check("失败态不受影响",
          host._get_frame_type_name(td, "失败", 12) == "解析失败")



def main():
    test_registry()
    test_static_tables()
    test_decode_dt()
    test_roundtrip_templates()
    test_roundtrip_fields()
    test_frame_sizes()
    test_control_field()
    test_tolerance()
    test_meta_not_dead_code()
    test_validator()
    test_verify_frame_and_utils()
    test_frame_gen_gui()
    test_summary_wiring()

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    # 不用 os._exit：Qt 已加载时直接 ExitProcess 会偶发 0xC0000409（DLL 卸载期崩溃），
    # 正常 SystemExit 让解释器按序析构，实测 12/12 稳定。
    raise SystemExit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
