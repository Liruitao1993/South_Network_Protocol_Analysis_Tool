# -*- coding: utf-8 -*-
"""DL/T 698.45 APDU 数据内容业务解码模块

将 APDU 数据内容（A-XDR 原始解码结果）按 698.45 对象属性定义解码为业务值：
- 电能量数组（array of long-unsigned/double-long-unsigned + Scaler_Unit 换算）→ kWh
- 最大需量数组（array of structure {需量值, 发生时间}）→ 值 @ 时间
- 分相数值数组（array，A/B/C 相）→ 逐相值 + 单位
- 时间类型（date_time / date_time_s / date / time）→ 可读字符串
- 枚举 → 说明

依据：面向对象的用电信息数据交换协议(20210910).md §7.2/§7.3/§8.2
"""

from typing import Any, Dict, Optional, Tuple

# ═══════════════════════════════════════════════════════════════
# 类属性 → 数据格式模板
# class_id 来自 OILookup.OI_TO_CLASS_ID，attr_id 为属性编号（OAD 字节2 低5位）
# ═══════════════════════════════════════════════════════════════

#: 表191 属性3「版本信息」的 6 个字段名 —— **单一来源**：标准对象（OI 0x4300 属性3）与
#: 厂家扩展的同类对象（如「内部版本」OAD `FF 10 04 00`，实机回同样 6 项同长度结构）共用；
#: 不要在别处再抄一份字段名/顺序。
VERSION_FIELDS: Tuple[str, ...] = (
    "厂商代码", "软件版本号", "软件版本日期", "硬件版本号", "硬件版本日期", "厂商扩展信息",
)

#: 表191 为上述 6 个字段声明的**字节长度**（结构自证用：实发长度逐项一致才算「确是本结构」）。
VERSION_FIELD_BYTES: Tuple[int, ...] = (4, 4, 6, 4, 6, 8)

CLASS_ATTR_TEMPLATES: Dict[Tuple[int, int], Dict[str, Any]] = {
    # ---- 电能量类 (class_id=1) ----
    (1, 2): {"type": "energy_array", "name": "总及费率电能量数组"},
    (1, 4): {"type": "energy_array", "name": "扩展精度总及费率电能量数组", "extended": True},
    (1, 30): {"type": "energy_array_q", "name": "带品质的总及费率电能量数组"},
    # ---- 最大需量类 (class_id=2) ----
    (2, 2): {"type": "demand_array", "name": "总及费率最大需量数组"},
    (2, 31): {"type": "demand_array_q", "name": "带品质的总及费率最大需量数组"},
    # ---- 分相变量类 (class_id=3) ----
    (3, 2): {"type": "phase_array", "name": "分相数值数组"},
    (3, 31): {"type": "phase_array_q", "name": "带品质的分相数值数组"},
    # ---- 功率类 (class_id=4) ----
    (4, 2): {"type": "phase_array", "name": "总及分相数值数组"},
    (4, 31): {"type": "phase_array_q", "name": "带品质的总及分相数值数组"},
    # ---- 谐波变量类 (class_id=5) ----
    (5, 2): {"type": "phase_array", "name": "谐波含量数值数组"},
    # ---- 数据变量类 (class_id=7) ----
    (7, 2): {"type": "data_value", "name": "数据"},
    (7, 30): {"type": "data_value_q", "name": "带品质的数据"},
    # ---- 设备管理类 (class_id=19，表191) ----
    (19, 2): {"type": "visible_string", "name": "设备描述符"},
    (19, 3): {"type": "version_structure", "name": "版本信息",
              "fields": list(VERSION_FIELDS)},
    (19, 4): {"type": "date_time_s", "name": "生产日期"},
}

# ═══════════════════════════════════════════════════════════════
# 安徽分布式电源接入单元补充规约（2025）专属属性模板
# 键为完整 OI（非 (class_id, attr_id)），decode_oad_data 优先匹配此表
# ═══════════════════════════════════════════════════════════════
ANHUI_ATTR_TEMPLATES: Dict[int, Dict[str, Any]] = {
    # ---- 发电量 2801 (class_id=6 数据变量类) ----
    0x2801: {"attrs": {
        2: {"type": "long64_value", "name": "总发电量", "unit": "kWh", "scale": -4},
        4: {"type": "long64_value", "name": "当日发电量", "unit": "kWh", "scale": -4},
        5: {"type": "long64_value", "name": "当月发电量", "unit": "kWh", "scale": -4},
        6: {"type": "long64_value", "name": "当年发电量", "unit": "kWh", "scale": -4},
    }},
    # ---- 发电时间 2802 (class_id=6) ----
    0x2802: {"attrs": {
        2: {"type": "double_long_unsigned_value", "name": "总发电时间", "unit": "分", "scale": 0},
        4: {"type": "double_long_unsigned_value", "name": "当日发电时间", "unit": "分", "scale": 0},
        5: {"type": "double_long_unsigned_value", "name": "当月发电时间", "unit": "分", "scale": 0},
        6: {"type": "double_long_unsigned_value", "name": "当年发电时间", "unit": "分", "scale": 0},
    }},
    # ---- 光伏逆变器控制事件 3060-3063 / 通信异常 3065-3066 / 3095-3096 (class_id=7 事件对象类) ----
    0x3060: {"attrs": {2: {"type": "control_event_array", "name": "事件记录表"}},
             "event_name": "光伏逆变器开关机控制事件"},
    0x3061: {"attrs": {2: {"type": "control_event_array", "name": "事件记录表"}}},
    0x3062: {"attrs": {2: {"type": "control_event_array", "name": "事件记录表"}}},
    0x3063: {"attrs": {2: {"type": "control_event_array", "name": "事件记录表"}}},
    0x3065: {"attrs": {2: {"type": "std_event_array", "name": "事件记录表"}}},
    0x3066: {"attrs": {2: {"type": "std_event_array", "name": "事件记录表"}}},
    0x3095: {"attrs": {2: {"type": "std_event_array", "name": "事件记录表"}}},
    0x3096: {"attrs": {2: {"type": "std_event_array", "name": "事件记录表"}}},
    # ---- 光伏越限事件单元 3097 / 控制事件记录单元 3361 / 控制指令事件单元 3363 (class_id=8 参数变量类) ----
    0x3097: {"attrs": {2: {"type": "struct_decode", "name": "光伏越限事件单元",
                           "spec": "pv_overturn"}}},
    0x3361: {"attrs": {2: {"type": "struct_decode", "name": "逆变器控制事件记录单元",
                            "spec": "ctrl_event_unit"}}},
    0x3363: {"attrs": {2: {"type": "struct_decode", "name": "控制指令事件单元",
                            "spec": "cmd_event_unit"}}},
    # ---- 逆变器档案单元 4039 (class_id=8) ----
    0x4039: {"attrs": {2: {"type": "struct_decode", "name": "逆变器档案单元",
                            "spec": "inverter_archive"}}},
    # ---- 光伏逆变器 4820 (class_id=19 设备管理类) ----
    0x4820: {"attrs": {
        2: {"type": "struct_decode", "name": "光伏电站基础信息", "spec": "pv_basic_info"},
        3: {"type": "enum_decode", "name": "逆变器运行状态",
            "enum_map": {0: "正常运行", 1: "关机", 2: "充电", 3: "放电", 4: "故障停机",
                         5: "紧急停机", 6: "降额运行", 7: "限额运行"}},
        5: {"type": "double_long_unsigned_value", "name": "逆变器额定容量", "unit": "kW", "scale": -1},
        6: {"type": "struct_decode", "name": "本地调控参数", "spec": "pv_local_ctrl"},
    }},
    # ---- 分布式电源调控调度计划表 4822 / 单元 4823 (class_id=8) ----
    0x4822: {"attrs": {2: {"type": "array_struct", "name": "分布式电源调控调度计划表",
                            "spec": "dispatch_plan_unit"}}},
    0x4823: {"attrs": {2: {"type": "struct_decode", "name": "分布式电源调控调度计划单元",
                            "spec": "dispatch_plan_unit"}}},
}

def is_null_member(item: Any) -> bool:
    """成员是否为 A-XDR ``null``（表191 的「无此信息」现场写法）。"""
    if not isinstance(item, dict):
        return item is None
    return (item.get("tag_name") == "null" or item.get("类型") == "null"
            or item.get("解析值") is None and item.get("tag_name") in (None, "null"))


def version_like_members(data_dict: Any) -> Optional[list]:
    """若 ``data_dict`` 是「版本信息形状」的 structure ⇒ 返回其 6 个成员，否则 ``None``。

    形状判据（宽松档）：`structure` + **恰好 6 个**成员 + 每个成员是 `visible-string`
    **或 `null`**。
    更严的「长度是否与表191 声明一致」由 :func:`version_lengths_match` 单独回答 ——
    命名可以照给（值/原始字节一起展示），但长度不符时调用方**必须**把这一点说出来。

    ⚠ **为什么允许 `null`**（1.23.93 现场修正，改前必读）：表191 声明 6 项都是定长
    visible-string(4/4/6/4/6/8)，但现场设备把「厂商扩展信息」回成 `00`（A-XDR null）。
    早先这里要求**全部**是 visible-string ⇒ 整条结构被判成「非版本形状」，界面于是
    退化成一行 `数据 = 0206...`（现场看到的就是「版本信息变成原始内容」）。
    既然 :func:`_decode_version_structure` 本就容忍非字符串成员，判定就应与之一致：
    **命名照给，缺失另报**（`version_rows` 会追加「⚠ 字段缺失」行）。
    """
    if not isinstance(data_dict, dict):
        return None
    if data_dict.get("tag_name") != "structure" and data_dict.get("类型") != "structure":
        return None
    items = data_dict.get("解析值")
    if not isinstance(items, list) or len(items) != len(VERSION_FIELDS):
        return None
    for item in items:
        if is_null_member(item):
            continue
        if not isinstance(item, dict):
            return None
        if item.get("tag_name") != "visible-string" and item.get("类型") != "visible-string":
            return None
    return items


def version_lengths_match(members: list) -> bool:
    """6 个成员的**字节长度**是否逐项等于表191 声明（4/4/6/4/6/8）—— 结构自证的强判据。"""
    try:
        return tuple(len(str(m.get("原始值", ""))) // 2 for m in members) == VERSION_FIELD_BYTES
    except Exception:                                   # 缺字段/非预期形状 ⇒ 视为不自证
        return False


def _decode_visible_string_field(data_dict: Dict[str, Any], name: str = "设备描述符") -> Dict[str, str]:
    """单 visible-string 解码（如 设备描述符）"""
    val = data_dict.get("解析值") if isinstance(data_dict, dict) else None
    if isinstance(val, str) and val:
        return {name: val}
    return {}

def _decode_version_structure(data_dict: Dict[str, Any],
                              field_names: list = None) -> Dict[str, str]:
    """版本信息结构解码（表191 属性3）：structure of 6×visible-string

    厂商代码/软件版本号/软件版本日期/硬件版本号/硬件版本日期/厂商扩展信息
    软件版本日期、硬件版本日期为 YYMMDD → 补全年份显示。`field_names` 缺省取
    :data:`VERSION_FIELDS`（单一来源）。
    """
    field_names = list(field_names) if field_names else list(VERSION_FIELDS)
    result: Dict[str, str] = {}
    items = data_dict.get("解析值") if isinstance(data_dict, dict) else None
    if not isinstance(items, list):
        return result
    for i, item in enumerate(items):
        name = field_names[i] if i < len(field_names) else f"字段{i + 1}"
        if is_null_member(item):
            # 设备回 null（= 无此信息）：仍然给出字段名，别让整条塌成 hex
            result[name] = "NULL"
            continue
        val = item.get("解析值") if isinstance(item, dict) else item
        if not isinstance(val, str):
            continue
        # 定长 visible-string 常用 NUL 补齐（表191 的 SIZE(4)/(6)/(8)）⇒ 显示前去掉尾部 NUL，
        # 否则界面上是一串不可见字符，粘到别处还会带上 \x00
        val = val.rstrip("\x00")
        if "日期" in name and len(val) == 6 and val.isdigit():
            # YYMMDD → 20YY-MM-DD
            try:
                mm, dd = int(val[2:4]), int(val[4:6])
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    val = f"20{val[0:2]}-{val[2:4]}-{val[4:6]}"
            except ValueError:
                pass
        result[name] = val
    return result


def decode_version_info(data_dict: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """按表191「版本信息」解码任意**同形**结构（标准 OI 0x4300 属性3 / 厂家扩展内部版本同用）。

    形状不符（不是 6×visible-string 的 structure）⇒ ``None``（调用方自行决定如何标注）。
    """
    if version_like_members(data_dict) is None:
        return None
    decoded = _decode_version_structure(data_dict)
    return decoded or None

def _decode_date_time_s_value(data_dict: Dict[str, Any], name: str = "生产日期") -> Dict[str, str]:
    """date_time_s 单值可读化（表191 属性4）"""
    raw = data_dict.get("原始编码", "") if isinstance(data_dict, dict) else ""
    t = _decode_time(data_dict)
    return {name: t}

# 时间相关 OAD 属性（OI 高字节 = 对象类型，常见时间属性）
# date_time / date_time_s 等由 A-XDR 类型决定，解码器按解析值 dict 结构判断

# ═══════════════════════════════════════════════════════════════
# OI 单位提示（仅当响应未携带属性3 Scaler_Unit 时作为默认）
# 格式: OI -> (单位, 默认scaler)
# ═══════════════════════════════════════════════════════════════

OI_UNIT_HINT: Dict[int, Tuple[str, int]] = {
    # ---- 电能量 (0x00xx, 0x01xx) ----
    0x0000: ("kWh", -3), 0x0001: ("kWh", -3), 0x0002: ("kWh", -3), 0x0003: ("kWh", -3),
    0x0004: ("kWh", -3), 0x0005: ("kWh", -3), 0x0006: ("kWh", -3), 0x0007: ("kWh", -3),
    0x0010: ("kWh", -3), 0x0011: ("kWh", -3), 0x0012: ("kWh", -3), 0x0013: ("kWh", -3),
    0x0019: ("kWh", -3), 0x0020: ("kWh", -3), 0x0021: ("kWh", -3), 0x0022: ("kWh", -3),
    0x0023: ("kWh", -3), 0x0030: ("kWh", -3), 0x0031: ("kWh", -3), 0x0032: ("kWh", -3),
    0x0033: ("kWh", -3), 0x0040: ("kWh", -3), 0x0041: ("kWh", -3), 0x0042: ("kWh", -3),
    0x0043: ("kWh", -3), 0x0100: ("kWh", -3), 0x0110: ("kWh", -3),
    # ---- 分相变量 (0x20xx) ----
    0x2000: ("V", -1), 0x2001: ("A", -3), 0x2002: ("°", -2), 0x2003: ("°", -2),
    0x200B: ("%", -1), 0x200C: ("%", -1), 0x200D: ("%", -1), 0x200E: ("%", -1),
    0x200F: ("Hz", -2), 0x2011: ("V", -2), 0x2012: ("V", -2), 0x2026: ("%", -1),
    0x2027: ("%", -1), 0x2033: ("%", -1),
    # ---- 功率 (0x30xx 部分为事件, 0x40xx 功率) ----
    0x4000: ("W", -3), 0x4001: ("W", -3), 0x4002: ("var", -3), 0x4003: ("VA", -3),
    0x4010: ("W", -3), 0x4011: ("W", -3), 0x4012: ("var", -3), 0x4013: ("VA", -3),
    # ---- 需量 (0x01xx 部分) ----
    0x1000: ("W", -3), 0x1010: ("W", -3),
    # ---- 安徽分布式电源接入单元补充规约（2025）手动追加 ----
    0x2004: ("W", -1), 0x2005: ("var", -1), 0x200A: ("", -3),
    0x2801: ("kWh", -4), 0x2802: ("min", 0),
}

# 单位码 → 单位文本（Scaler_Unit 的 unit 字段）
UNIT_CODE_MAP = {
    1: "Wh", 2: "kWh", 3: "MWh", 4: "varh", 5: "kvarh", 6: "Mvarh",
    7: "VAh", 8: "kVAh", 9: "MVAh", 10: "W", 11: "kW", 12: "MW",
    13: "var", 14: "kvar", 15: "Mvar", 16: "VA", 17: "kVA", 18: "MVA",
    19: "V", 20: "A", 21: "°", 22: "Hz", 23: "%", 24: "s", 25: "min",
    26: "h", 27: "d", 28: "Wh", 29: "℃",
}


# ═══════════════════════════════════════════════════════════════
# 业务解码
# ═══════════════════════════════════════════════════════════════

def _apply_scaler(value: int, scaler: int) -> float:
    """按 10^scaler 换算数值"""
    return value * (10 ** scaler)


def _format_number(value: float) -> str:
    """格式化数值（去掉多余小数位）"""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _decode_time(value: Any) -> str:
    """时间类型解码（date_time / date_time_s / date / time）

    date_time_s 为 7 字节十六进制: 年(2B) 月 日 时 分 秒
    date_time 为 structure: year month day_of_month day_of_week hour minute second ms
    """
    if isinstance(value, dict):
        ttype = value.get("类型", "")
        pv = value.get("解析值")
        if isinstance(pv, dict):
            # date_time: 按字段名
            year = pv.get("year", pv.get("年", 0))
            month = pv.get("month", pv.get("月", 0))
            day = pv.get("day_of_month", pv.get("日", 0))
            hour = pv.get("hour", pv.get("时", 0))
            minute = pv.get("minute", pv.get("分", 0))
            second = pv.get("second", pv.get("秒", 0))
            if year and month and day:
                return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        # octet-string / UTF8-string / visible-string: hex 字符串
        raw = pv if isinstance(pv, str) else value.get("原始值", "")
        if isinstance(raw, str):
            hex_str = raw.replace(" ", "")
            # 尝试解析 hex 为日期时间（date_time_s=7字节14hex, date=5字节10hex, time=3字节6hex）
            try:
                b = bytes.fromhex(hex_str)
                if len(b) >= 7 and ttype in ("date_time_s", "octet-string", "UTF8-string", "visible-string"):
                    year = int.from_bytes(b[0:2], 'big')
                    month, day, hour, minute, second = b[2], b[3], b[4], b[5], b[6]
                    if 0 < month <= 12 and 0 < day <= 31:
                        return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
                if len(b) == 5 and ttype in ("date", "octet-string", "UTF8-string"):
                    year = int.from_bytes(b[0:2], 'big')
                    return f"{year:04d}-{b[2]:02d}-{b[3]:02d}"
                if len(b) == 3 and ttype in ("time", "octet-string", "UTF8-string"):
                    return f"{b[0]:02d}:{b[1]:02d}:{b[2]:02d}"
            except (ValueError, TypeError):
                pass
            return hex_str
    if isinstance(value, str):
        return value
    return str(value)


def _decode_quality(value: Any) -> str:
    """VQDS 品质解码（bit0 无效, bit1 非当前, bit2 被取代, bit3 被闭锁）"""
    if isinstance(value, dict):
        pv = value.get("解析值")
        if isinstance(pv, dict) and "品质" in pv:
            q = pv["品质"]
            if isinstance(q, dict):
                q = q.get("解析值", q.get("值", 0))
            if isinstance(q, int):
                parts = []
                if q & 0x01: parts.append("无效")
                if q & 0x02: parts.append("非当前")
                if q & 0x04: parts.append("被取代")
                if q & 0x08: parts.append("被闭锁")
                return "|".join(parts) if parts else "有效"
    return ""


def _decode_energy_array(data_dict: Dict[str, Any], unit_hint: Tuple[str, int],
                         extended: bool = False) -> Dict[str, str]:
    """电能量数组解码：array of 数值，费率0=总，后续为费率1..N"""
    items = data_dict.get("解析值", []) if isinstance(data_dict, dict) else data_dict
    if not isinstance(items, list):
        return {"原始": str(data_dict)}
    unit, default_scaler = unit_hint
    result = {}
    for i, item in enumerate(items):
        val = item.get("解析值", 0) if isinstance(item, dict) else item
        if isinstance(val, dict):
            val = val.get("解析值", val.get("值", 0))
        try:
            val = int(val)
        except (ValueError, TypeError):
            result[f"元素{i}"] = str(item)
            continue
        scaled = _apply_scaler(val, default_scaler)
        label = "总" if i == 0 else f"费率{i}"
        result[label] = f"{_format_number(scaled)} {unit}"
    return result


def _decode_energy_array_q(data_dict: Dict[str, Any], unit_hint: Tuple[str, int]) -> Dict[str, str]:
    """带品质的电能量数组：array of structure {值, 品质VQDS}"""
    items = data_dict.get("解析值", []) if isinstance(data_dict, dict) else data_dict
    if not isinstance(items, list):
        return {"原始": str(data_dict)}
    unit, default_scaler = unit_hint
    result = {}
    for i, item in enumerate(items):
        val = 0
        quality = ""
        if isinstance(item, dict):
            pv = item.get("解析值", item)
            if isinstance(pv, dict):
                for k in ("值", "数值", "电能量", "value"):
                    if k in pv:
                        val = pv[k]
                        if isinstance(val, dict):
                            val = val.get("解析值", val.get("值", 0))
                        break
                for k in ("品质", "质量", "quality", "VQDS"):
                    if k in pv:
                        quality = _decode_quality(pv[k])
                        break
        else:
            val = item
        try:
            val = int(val)
        except (ValueError, TypeError):
            result[f"元素{i}"] = str(item)
            continue
        scaled = _apply_scaler(val, default_scaler)
        label = "总" if i == 0 else f"费率{i}"
        q_suffix = f"[{quality}]" if quality else ""
        result[label] = f"{_format_number(scaled)} {unit}{q_suffix}"
    return result


def _decode_demand_array(data_dict: Dict[str, Any], unit_hint: Tuple[str, int]) -> Dict[str, str]:
    """最大需量数组解码：array of structure {需量值, 发生时间 date_time_s}"""
    items = data_dict.get("解析值", []) if isinstance(data_dict, dict) else data_dict
    if not isinstance(items, list):
        return {"原始": str(data_dict)}
    unit, default_scaler = unit_hint
    result = {}
    for i, item in enumerate(items):
        val = 0
        time_str = ""
        if isinstance(item, dict):
            pv = item.get("解析值", item)
            if isinstance(pv, list):
                # structure 解析值为成员列表: [0]=需量值, [1]=发生时间
                if len(pv) >= 1:
                    v0 = pv[0]
                    val = v0.get("解析值", v0.get("值", 0)) if isinstance(v0, dict) else v0
                if len(pv) >= 2:
                    time_str = _decode_time(pv[1])
            elif isinstance(pv, dict):
                # 可能按字段名映射
                for k in ("需量值", "值", "value", "最大需量"):
                    if k in pv:
                        v = pv[k]
                        val = v.get("解析值", v.get("值", 0)) if isinstance(v, dict) else v
                        break
                for k in ("发生时间", "时间", "date_time_s", "time"):
                    if k in pv:
                        time_str = _decode_time(pv[k])
                        break
        try:
            val = int(val)
        except (ValueError, TypeError):
            result[f"元素{i}"] = str(item)
            continue
        scaled = _apply_scaler(val, default_scaler)
        label = "总" if i == 0 else f"费率{i}"
        if time_str:
            result[label] = f"{_format_number(scaled)} {unit} @ {time_str}"
        else:
            result[label] = f"{_format_number(scaled)} {unit}"
    return result


def _decode_demand_array_q(data_dict: Dict[str, Any], unit_hint: Tuple[str, int]) -> Dict[str, str]:
    """带品质的最大需量数组"""
    result = _decode_demand_array(data_dict, unit_hint)
    return result


def _decode_phase_array(data_dict: Dict[str, Any], unit_hint: Tuple[str, int],
                        oi_name: str = "") -> Dict[str, str]:
    """分相数值数组解码：array，顺序 A/B/C 相（或 总/A/B/C）"""
    items = data_dict.get("解析值", []) if isinstance(data_dict, dict) else data_dict
    if not isinstance(items, list):
        return {"原始": str(data_dict)}
    unit, default_scaler = unit_hint
    labels = ["A相", "B相", "C相"]
    result = {}
    for i, item in enumerate(items):
        val = item.get("解析值", 0) if isinstance(item, dict) else item
        if isinstance(val, dict):
            val = val.get("解析值", val.get("值", 0))
        try:
            val = int(val)
        except (ValueError, TypeError):
            result[labels[i] if i < 3 else f"元素{i}"] = str(item)
            continue
        scaled = _apply_scaler(val, default_scaler)
        label = labels[i] if i < 3 else f"元素{i}"
        result[label] = f"{_format_number(scaled)} {unit}"
    return result


def _decode_phase_array_q(data_dict: Dict[str, Any], unit_hint: Tuple[str, int]) -> Dict[str, str]:
    """带品质的分相数值数组"""
    return _decode_phase_array(data_dict, unit_hint)


def _decode_data_value(data_dict: Dict[str, Any], unit_hint: Tuple[str, int]) -> Dict[str, str]:
    """单数值解码"""
    val = data_dict.get("解析值", data_dict) if isinstance(data_dict, dict) else data_dict
    if isinstance(val, dict):
        val = val.get("解析值", val.get("值", val))
    unit, default_scaler = unit_hint
    try:
        val = int(val)
    except (ValueError, TypeError):
        return {"值": str(val)}
    scaled = _apply_scaler(val, default_scaler)
    return {"值": f"{_format_number(scaled)} {unit}"}


def _decode_data_value_q(data_dict: Dict[str, Any], unit_hint: Tuple[str, int]) -> Dict[str, str]:
    """带品质的单数值"""
    result = _decode_data_value(data_dict, unit_hint)
    return result


# ═══════════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 安徽分布式电源接入单元补充规约（2025）结构成员规格
# 每项: (名称, 类型, 附加参数{enum_map/unit/scale/struct_spec/array_spec})
# ═══════════════════════════════════════════════════════════════
ANHUI_STRUCT_SPECS: Dict[str, list] = {
    "pv_overturn": [
        ("事件记录序号", "double_long_unsigned"),
        ("事件发生时间", "date_time_s"),
        ("事件结束时间", "date_time_s"),
        ("事件发生源", "tsa"),
        ("事件上报状态", "array", {"items": "channel_report", "elem_name": "通道上报状态"}),
        ("越限类型", "enum", {"enum_map": {1: "电压越限", 2: "有功功率越限", 3: "无功功率越限", 4: "功率因数越限"}}),
        ("关联对象数据", "array", {"items": "data", "elem_name": "关联对象属性数据"}),
    ],
    "ctrl_event_unit": [
        ("事件记录序号", "double_long_unsigned"),
        ("事件发生时间", "date_time_s"),
        ("事件结束时间", "date_time_s"),
        ("事件发生源", "instance_specific"),
        ("事件上报状态", "array", {"items": "channel_report", "elem_name": "通道上报状态"}),
        ("调节类型", "enum", {"enum_map": {0: "远程", 1: "自动调节", 2: "电压越限调节", 3: "过容调节",
                                           4: "预测曲线调节", 5: "调控计划调节", 6: "孤岛保护",
                                           7: "正向过载", 8: "反向重过载"}}),
        ("调节方式", "enum", {"enum_map": {1: "有功功率", 2: "无功功率", 3: "功率因数", 4: "有功功率百分比",
                                           5: "无功功率百分比", 6: "开机", 7: "关机"}}),
        ("调节值", "data"),
        ("关联对象数据", "array", {"items": "data", "elem_name": "关联对象属性数据"}),
    ],
    "cmd_event_unit": [
        ("事件记录序号", "double_long_unsigned"),
        ("事件发生时间", "date_time_s"),
        ("事件结束时间", "date_time_s"),
        ("事件发生源", "instance_specific"),
        ("事件上报状态", "array", {"items": "channel_report", "elem_name": "通道上报状态"}),
        ("指令类型", "oad"),
        ("指令执行结果", "enum", {"enum_map": {0: "无应答", 1: "异常应答", 2: "正常应答"}}),
    ],
    "inverter_archive": [
        ("接入模式", "enum", {"enum_map": {0: "无接口转接器接入", 1: "有接口转接器接入"}}),
        ("逆变器地址", "unsigned"),
        ("逆变器品牌", "visible_string"),
        ("协议版本", "long_unsigned"),
        ("接入端口", "unsigned"),
    ],
    "pv_basic_info": [
        ("数据采集器编号", "visible_string"),
        ("设备类型", "visible_string"),
        ("设备SN号", "visible_string"),
        ("额定有功功率", "double_long", {"unit": "W", "scale": -1}),
        ("额定无功功率", "double_long", {"unit": "Var", "scale": -1}),
        ("输出类型", "enum", {"enum_map": {0: "单相", 1: "三相", 2: "未知"}}),
    ],
    "pv_local_ctrl": [
        ("逆变器报装容量", "double_long", {"unit": "W", "scale": -1}),
        ("电压调控阈值", "long_unsigned", {"unit": "V", "scale": -1}),
        ("电压恢复阈值", "long_unsigned", {"unit": "V", "scale": -1}),
    ],
    "dispatch_plan_unit": [
        ("序号", "long_unsigned"),
        ("接入端口", "unsigned"),
        ("计划来源", "enum", {"enum_map": {1: "调度系统", 2: "主站", 3: "集中器", 255: "其他"}}),
        ("光伏调控计划执行日期", "date"),
        ("光伏出力调控时段表", "array", {"items": "dispatch_period", "elem_name": "光伏出力调控时段"}),
        ("调控数据表", "array", {"items": "dispatch_data", "elem_name": "调控数据"}),
    ],
    "dispatch_period": [
        ("类型", "enum", {"enum_map": {0: "前闭后开", 1: "前开后闭", 2: "前闭后闭", 3: "前开后开"}}),
        ("起始小时", "unsigned"),
        ("起始分钟", "unsigned"),
        ("结束小时", "unsigned"),
        ("结束分钟", "unsigned"),
    ],
    "dispatch_data": [
        ("调节方式", "enum", {"enum_map": {1: "有功功率", 2: "无功功率", 3: "功率因数",
                                           4: "有功功率百分比", 5: "无功功率百分比"}}),
        ("调节值", "data"),
    ],
}


def _anhui_member_value(member: Dict[str, Any], spec: tuple) -> str:
    """按 spec 解码 structure 单个成员为可读字符串"""
    name, mtype = spec[0], spec[1]
    opts = spec[2] if len(spec) > 2 else {}
    val = member.get("解析值") if isinstance(member, dict) else member
    if mtype == "enum":
        emap = opts.get("enum_map", {})
        return emap.get(val, emap.get(int(val) if isinstance(val, str) and val.isdigit() else val, str(val)))
    if mtype in ("unsigned", "long_unsigned", "long", "double_long", "double_long_unsigned"):
        unit = opts.get("unit", "")
        scale = opts.get("scale", 0)
        if scale:
            n = float(val) * (10 ** scale)
            text = _format_number(n)
        else:
            text = str(val)
        return f"{text} {unit}".strip()
    if mtype == "date_time_s":
        return _decode_time(val) if val is not None else ""
    if mtype == "date":
        return _decode_time(val) if val is not None else ""
    if mtype in ("visible_string", "utf8_string"):
        return str(val) if val is not None else ""
    if mtype in ("oad",):
        return str(val) if val is not None else ""
    if mtype == "tsa":
        return str(val) if val is not None else ""
    if mtype == "instance_specific":
        return str(val) if val is not None else ""
    if mtype == "data":
        return _decode_data_value(member, ("", 0)).get("值", str(val)) if isinstance(member, dict) else str(val)
    if mtype == "array":
        # array 元素按 items spec 递归
        items_spec = opts.get("items")
        arr = val if isinstance(val, list) else []
        parts = []
        for i, el in enumerate(arr):
            if isinstance(el, dict) and items_spec in ANHUI_STRUCT_SPECS:
                parts.append(f"[{i+1}] " + _decode_struct_by_spec(el, ANHUI_STRUCT_SPECS[items_spec]))
            else:
                parts.append(f"[{i+1}] " + _decode_data_value(el, ("", 0)).get("值", str(el)))
        return "; ".join(parts)
    return str(val) if val is not None else ""


def _decode_struct_by_spec(data_dict: Any, spec: list) -> str:
    """按成员规格解码 structure（data_dict 解析值为成员 dict 列表）"""
    if not isinstance(data_dict, dict):
        return ""
    members = data_dict.get("解析值")
    if not isinstance(members, list):
        return ""
    result = []
    for i, member in enumerate(members):
        if i < len(spec):
            spec_item = spec[i]
            text = _anhui_member_value(member, spec_item)
            if text:
                result.append(f"{spec_item[0]}: {text}")
        else:
            # 超出 spec 的成员保留原始值
            v = member.get("解析值") if isinstance(member, dict) else member
            result.append(f"{i+1}: {v}")
    return "，".join(result)


def _decode_anhui_attr(oi: int, attr_id: int, attr_tpl: Dict[str, Any],
                       data_dict: Any) -> Optional[Dict[str, str]]:
    """按安徽专属模板解码单个属性"""
    ttype = attr_tpl["type"]
    name = attr_tpl.get("name", "")
    try:
        if ttype == "long64_value":
            val = data_dict.get("解析值") if isinstance(data_dict, dict) else None
            scale = attr_tpl.get("scale", 0)
            unit = attr_tpl.get("unit", "")
            n = float(val) * (10 ** scale) if scale else float(val)
            return {name: f"{_format_number(n)} {unit}".strip()}
        if ttype == "double_long_unsigned_value":
            val = data_dict.get("解析值") if isinstance(data_dict, dict) else None
            scale = attr_tpl.get("scale", 0)
            unit = attr_tpl.get("unit", "")
            n = float(val) * (10 ** scale) if scale else float(val)
            return {name: f"{_format_number(n)} {unit}".strip()}
        if ttype == "enum_decode":
            val = data_dict.get("解析值") if isinstance(data_dict, dict) else None
            emap = attr_tpl.get("enum_map", {})
            return {name: emap.get(val, emap.get(int(val) if isinstance(val, str) and val.isdigit() else val, str(val)))}
        if ttype == "struct_decode":
            spec = attr_tpl.get("spec")
            text = _decode_struct_by_spec(data_dict, ANHUI_STRUCT_SPECS.get(spec, []))
            return {name: text} if text else None
        if ttype in ("control_event_array", "std_event_array"):
            events = data_dict.get("解析值") if isinstance(data_dict, dict) else None
            if not isinstance(events, list):
                return None
            parts = []
            for i, ev in enumerate(events):
                if isinstance(ev, dict) and ev.get("类型") == "structure":
                    unit_spec = "ctrl_event_unit" if ttype == "control_event_array" else "cmd_event_unit"
                    parts.append(f"[{i+1}] " + _decode_struct_by_spec(ev, ANHUI_STRUCT_SPECS.get(unit_spec, [])))
                else:
                    parts.append(f"[{i+1}] " + str(ev))
            return {name: "; ".join(parts)} if parts else None
        if ttype == "array_struct":
            elems = data_dict.get("解析值") if isinstance(data_dict, dict) else None
            spec = attr_tpl.get("spec")
            if not isinstance(elems, list):
                return None
            parts = []
            for i, el in enumerate(elems):
                if isinstance(el, dict) and el.get("类型") == "structure":
                    parts.append(f"[{i+1}] " + _decode_struct_by_spec(el, ANHUI_STRUCT_SPECS.get(spec, [])))
                else:
                    parts.append(f"[{i+1}] " + str(el.get("解析值", el)))
            return {name: "; ".join(parts)} if parts else None
    except Exception:
        return None
    return None


def infer_unit_hint(oi: int) -> Tuple[str, int]:
    """根据 OI 推断单位与默认 scaler（OILookup 名称辅助）"""
    hint = OI_UNIT_HINT.get(oi)
    if hint:
        return hint
    # 按 OI 名称推断
    try:
        from dl_t698_45_oi_lookup import OILookup
        name = OILookup().OI_NAME_MAP.get(oi, "")
        if "电压" in name:
            return ("V", -1)
        if "电流" in name:
            return ("A", -3)
        if "功率" in name and "因数" not in name:
            return ("W", -3)
        if "频率" in name:
            return ("Hz", -2)
        if "电能" in name:
            return ("kWh", -3)
        if "需量" in name:
            return ("W", -3)
        if "相角" in name:
            return ("°", -2)
        if "温度" in name:
            return ("℃", -1)
        if "失真" in name or "含有率" in name or "不平衡" in name:
            return ("%", -1)
    except Exception:
        pass
    return ("", 0)


def decode_oad_data(oi: int, attr_id: int, data_dict: Any) -> Optional[Dict[str, str]]:
    """按 OAD（OI + 属性）解码数据内容为业务值

    Args:
        oi: 对象标识（OAD 前 2 字节）
        attr_id: 属性编号（OAD 字节2 低 5 位）
        data_dict: AXDRCoder.decode 得到的 A-XDR 数据（dict 含 类型/解析值）

    Returns:
        业务值 dict（如 {总: "1234.56 kWh", 费率1: ...}），无模板或失败返回 None
    """
    if data_dict is None:
        return None
    try:
        from dl_t698_45_oi_lookup import OILookup
        lookup = OILookup()
        class_id = lookup.OI_TO_CLASS_ID.get(oi)
        if class_id is None:
            return None
        # 安徽补充规约专属模板：按完整 OI 优先匹配（避免与标准 (class_id, attr_id) 冲突）
        anhui_tpl = ANHUI_ATTR_TEMPLATES.get(oi)
        if anhui_tpl is not None:
            attr_tpl = anhui_tpl.get("attrs", {}).get(attr_id)
            if attr_tpl is not None:
                return _decode_anhui_attr(oi, attr_id, attr_tpl, data_dict)
        template = CLASS_ATTR_TEMPLATES.get((class_id, attr_id))
        if not template:
            return None
        ttype = template["type"]
        unit_hint = infer_unit_hint(oi)

        if ttype == "energy_array":
            return _decode_energy_array(data_dict, unit_hint, template.get("extended", False))
        if ttype == "energy_array_q":
            return _decode_energy_array_q(data_dict, unit_hint)
        if ttype == "demand_array":
            return _decode_demand_array(data_dict, unit_hint)
        if ttype == "demand_array_q":
            return _decode_demand_array_q(data_dict, unit_hint)
        if ttype == "phase_array":
            return _decode_phase_array(data_dict, unit_hint)
        if ttype == "phase_array_q":
            return _decode_phase_array_q(data_dict, unit_hint)
        if ttype == "data_value":
            return _decode_data_value(data_dict, unit_hint)
        if ttype == "data_value_q":
            return _decode_data_value_q(data_dict, unit_hint)
        if ttype == "visible_string":
            return _decode_visible_string_field(data_dict, template["name"]) or None
        if ttype == "version_structure":
            return _decode_version_structure(data_dict, template["fields"]) or None
        if ttype == "date_time_s":
            return _decode_date_time_s_value(data_dict, template["name"]) or None
    except Exception:
        return None
    return None


# ═══════════════════════════════════════════════════════════════
# 安徽分布式电源接入单元补充规约（2025）方法参数解码（ACTION-Request）
# 键 (oi, method_id) → 参数结构定义
# ═══════════════════════════════════════════════════════════════
ACTION_METHOD_SPECS: Dict[Tuple[int, int], Dict[str, Any]] = {
    # 4820 光伏逆变器 方法127 开关机 / 方法128 控制负荷
    (0x4820, 127): {"type": "enum", "name": "开关机",
                    "enum_map": {0: "开机", 1: "关机"}},
    (0x4820, 128): {"type": "struct", "name": "控制逆变器负荷",
                    "spec": "inv_ctrl_load"},
    # 4822 调控调度计划表 方法127 添加 / 128 删除 / 129 清除
    (0x4822, 127): {"type": "array_struct", "name": "添加调控计划",
                    "spec": "dispatch_plan_unit"},
    (0x4822, 128): {"type": "array_scalar", "name": "删除调控计划", "elem_type": "long_unsigned"},
    (0x4822, 129): {"type": "null", "name": "清除调控计划"},
    # 8000 远程控制 方法129 跳闸 / 130 合闸
    (0x8000, 129): {"type": "array_struct", "name": "跳闸",
                    "spec": "trip_cmd"},
    (0x8000, 130): {"type": "array_struct", "name": "合闸",
                    "spec": "close_cmd"},
}

# 方法参数专用 structure 规格
ACTION_STRUCT_SPECS: Dict[str, list] = {
    "inv_ctrl_load": [
        ("调节方式", "enum", {"enum_map": {0: "不调节", 1: "有功功率", 2: "无功功率", 3: "功率因数",
                                           4: "有功功率百分比", 5: "无功功率百分比", 6: "本地调控"}}),
        ("调节值", "data"),
    ],
    "trip_cmd": [
        ("遥控单元", "oad"),
        ("告警延时", "unsigned", {"unit": "分钟"}),
        ("限电时间", "long_unsigned", {"unit": "分钟"}),
        ("自动合闸", "bool"),
    ],
    "close_cmd": [
        ("遥控单元", "oad"),
        ("命令", "enum", {"enum_map": {0: "合闸允许", 1: "直接合闸"}}),
    ],
    "dispatch_plan_unit": [
        ("序号", "long_unsigned"),
        ("接入端口", "unsigned"),
        ("计划来源", "enum", {"enum_map": {1: "调度系统", 2: "主站", 3: "集中器", 255: "其他"}}),
        ("光伏调控计划执行日期", "date"),
        ("光伏出力调控时段表", "array", {"items": "dispatch_period", "elem_name": "光伏出力调控时段"}),
        ("调控数据表", "array", {"items": "dispatch_data", "elem_name": "调控数据"}),
    ],
}


def decode_action_parameter(oi: int, method_id: int, data_dict: Any) -> Optional[Dict[str, str]]:
    """按 ACTION 方法参数解码为业务值（安徽补充规约）

    Args:
        oi: 对象标识（OMD 前 2 字节）
        method_id: 方法标识（OMD 字节3）
        data_dict: AXDRCoder.decode 得到的参数 A-XDR 数据

    Returns:
        业务值 dict（如 {开关机: "关机"}），无匹配 spec 或失败返回 None
    """
    spec = ACTION_METHOD_SPECS.get((oi, method_id))
    if spec is None or data_dict is None:
        return None
    name = spec.get("name", "参数")
    try:
        ttype = spec["type"]
        if ttype == "enum":
            val = data_dict.get("解析值") if isinstance(data_dict, dict) else None
            emap = spec.get("enum_map", {})
            return {name: emap.get(val, emap.get(int(val) if isinstance(val, str) and val.isdigit() else val, str(val)))}
        if ttype == "null":
            return {name: "无参数"}
        if ttype == "struct":
            sp = spec.get("spec")
            text = _decode_struct_by_spec(data_dict, ACTION_STRUCT_SPECS.get(sp, []))
            return {name: text} if text else {name: "无参数"}
        if ttype == "array_struct":
            elems = data_dict.get("解析值") if isinstance(data_dict, dict) else None
            sp = spec.get("spec")
            if not isinstance(elems, list):
                return {name: "空"}
            parts = []
            for i, el in enumerate(elems):
                if isinstance(el, dict) and el.get("类型") == "structure":
                    parts.append(f"[{i+1}] " + _decode_struct_by_spec(el, ACTION_STRUCT_SPECS.get(sp, [])))
                else:
                    parts.append(f"[{i+1}] " + str(el.get("解析值", el)))
            return {name: "; ".join(parts)} if parts else {name: "空"}
        if ttype == "array_scalar":
            elems = data_dict.get("解析值") if isinstance(data_dict, dict) else None
            if not isinstance(elems, list):
                return {name: "空"}
            vals = [str(el.get("解析值", el)) if isinstance(el, dict) else str(el) for el in elems]
            return {name: ", ".join(vals)}
    except Exception:
        return None
    return None