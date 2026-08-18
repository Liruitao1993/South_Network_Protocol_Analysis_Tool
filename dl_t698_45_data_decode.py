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
    # ---- 参数变量类 (class_id=8) ----
    (8, 2): {"type": "data_value", "name": "参数值"},
}

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
    except Exception:
        return None
    return None
