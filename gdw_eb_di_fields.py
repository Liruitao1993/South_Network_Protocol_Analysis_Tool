# -*- coding: utf-8 -*-
"""EB 数据标识 数据内容字段定义与编码（附件1 V3.42 本地通信模块扩展协议）

为每个 EB 数据项定义「数据内容」的字段结构（读/写/上报时数据域的格式），
Web EB 生成器选中 OAD 后按字段渲染表单，自动组装数据字节（698 A-XDR octet-string 内容）。

字段类型：
- uint8/uint16/uint24/uint32: 无符号整数（小端，与 645/698 多字节一致）
- enum: 下拉选择（枚举值 → uint8）
- bcd: 十六进制 BCD 字节（hex 字符串）
- bcd_time: YYMMDD hhmmss → 6 字节 BCD
- ascii: ASCII 字符串（定长右补空格）
- hex: 原始 hex 字节
- bs8: 位组合（1 字节）
- list: 列表（count 前置）

依据：协议文档/7.国网本地接口协议/附件1.md / 附件1_v342.md 表 1.1
"""

from typing import Any, Dict, List


# ═══════════════════════════════════════════════════════════════
# EB 数据项字段定义
# ═══════════════════════════════════════════════════════════════

EB_DI_FIELDS: Dict[str, Dict[str, Any]] = {
    # ── 事件配置管理 ──
    "EB040001": {
        "名称": "从节点模块事件引脚变位主动上报方式",
        "fields": [
            {"name": "事件上报方式(BS8)", "type": "bs8", "bits": {
                "D7 引脚变位上报": 7, "D6 变位信息": 6,
                "D1~D0 事件上报方式": 0},
             "bit_enums": {"D1~D0 事件上报方式": {0: "国网标准", 1: "福建扩展"}}},
        ],
    },
    "EB030001": {
        "名称": "从节点模块事件引脚状态变位",
        "fields": [
            {"name": "引脚状态", "type": "enum", "enum_map": {0: "恢复", 1: "发生"}},
        ],
    },
    "EB030002": {
        "名称": "从节点模块停上电事件",
        "fields": [
            {"name": "停上电类型", "type": "enum", "enum_map": {0: "模块停电", 1: "模块上电"}},
            {"name": "本次上报数量", "type": "uint8"},
            {"name": "模块地址列表", "type": "list",
             "item_fields": [{"name": "模块地址", "type": "bcd", "length": 6}]},
        ],
    },

    # ── 台区识别 ──
    "EB030101": {
        "名称": "从节点档案异常",
        "fields": [
            {"name": "档案异常类型", "type": "enum", "enum_map": {1: "未注册表计", 2: "跨台区表计"}},
            {"name": "模块隶属主节点地址", "type": "bcd", "length": 6},
            {"name": "识别准确性概率", "type": "uint8"},
        ],
    },
    "EB030110": {
        "名称": "台区识别_任务启动",
        "fields": [
            {"name": "台区识别方法", "type": "enum",
             "enum_map": {0: "自动", 1: "工频电压特征", 2: "工频频率特征", 3: "工频周期特征"}},
            {"name": "识别时长(分钟)", "type": "uint16"},
        ],
    },
    "EB030111": {
        "名称": "台区识别_结果概况",
        "fields": [
            {"name": "本次识别耗时(分钟)", "type": "uint16"},
            {"name": "本台区表计数量", "type": "uint16"},
            {"name": "非本台区表计数量", "type": "uint16"},
        ],
    },
    "EB030112": {
        "名称": "台区识别_非本台区从节点清单",
        "fields": [
            {"name": "请求清单开始序号", "type": "uint16"},
            {"name": "本次请求数量", "type": "uint8"},
        ],
    },
    "EB030113": {
        "名称": "从节点主动注册_未注册从节点清单",
        "fields": [
            {"name": "请求清单开始序号", "type": "uint16"},
            {"name": "本次请求数量", "type": "uint8"},
        ],
    },
    "EB030115": {
        "名称": "从节点主动注册_任务启动",
        "fields": [
            {"name": "允许注册时长(分钟)", "type": "uint16", "note": "FFFF=一直注册"},
        ],
    },

    # ── 设备基础信息 ──
    "EB030201": {
        "名称": "芯片ID",
        "fields": [{"name": "芯片ID", "type": "hex", "length": 24}],
    },
    "EB030202": {
        "名称": "通信模块资产管理编码",
        "fields": [{"name": "资产编码", "type": "ascii", "length": 32}],
    },
    "EB030301": {
        "名称": "单相表零火线接反/三相表逆相序",
        "fields": [
            {"name": "接线情况", "type": "enum", "enum_map": {0: "正常", 1: "零火线接反/逆相序"}},
        ],
    },
    "EB030302": {
        "名称": "通信模块所在相位",
        "fields": [
            {"name": "相位", "type": "enum", "enum_map": {0: "未知", 1: "A相", 2: "B相", 3: "C相"}},
        ],
    },
    "EB030303": {
        "名称": "通信模块软硬件版本",
        "fields": [
            {"name": "版本", "type": "bcd", "length": 2},
            {"name": "版本日期-年月日", "type": "bcd", "length": 3},
            {"name": "芯片代码", "type": "ascii", "length": 2},
            {"name": "厂商代码", "type": "ascii", "length": 2},
        ],
    },
    "EB030304": {
        "名称": "从节点模块工作电源电压(V)",
        "fields": [{"name": "电压", "type": "bcd", "length": 2}],
    },
    "EB030305": {
        "名称": "通信模块过零NTB差值",
        "fields": [
            {"name": "第1元件NTB差值", "type": "uint32"},
            {"name": "第2元件NTB差值", "type": "uint32"},
            {"name": "第3元件NTB差值", "type": "uint32"},
        ],
    },
    "EB030306": {
        "名称": "CCO载波接口过零信号状态",
        "fields": [
            {"name": "状态", "type": "bs8", "bits": {"Bit0 A相": 0, "Bit1 B相": 1, "Bit2 C相": 2}},
        ],
    },
    "EB030308": {
        "名称": "过零NTB值数据更新周期和上报点数",
        "fields": [
            {"name": "更新周期(分钟)", "type": "uint8", "note": "0/1/2/5/10/15/30/60,默认15"},
            {"name": "主动上报点数", "type": "uint8", "note": "0~10(STA)/0~200(CCO),默认0/100"},
        ],
    },
    "EB030310": {
        "名称": "从节点模块载波接口电压",
        "fields": [
            {"name": "A相电压", "type": "bcd", "length": 2},
            {"name": "B相电压", "type": "bcd", "length": 2},
            {"name": "C相电压", "type": "bcd", "length": 2},
        ],
    },
    "EB030311": {
        "名称": "环境温度(℃)",
        "fields": [{"name": "温度", "type": "bcd", "length": 2}],
    },
    "EB030312": {
        "名称": "响应超时时间(秒)",
        "fields": [{"name": "超时时间", "type": "uint8", "note": "5~90,默认30"}],
    },

    # ── 通信模块时钟管理 ──
    "EB030501": {
        "名称": "通信模块时钟",
        "fields": [{"name": "时钟 YYMMDDhhmmss", "type": "bcd_time"}],
    },
    "EB030502": {
        "名称": "校时允许周期(分钟)",
        "fields": [{"name": "校时周期", "type": "bcd", "length": 2, "note": "默认1400,最小5"}],
    },
    "EB030503": {
        "名称": "最近1次校时记录",
        "fields": [
            {"name": "校时时刻 YYMMDDhhmmss", "type": "bcd_time"},
            {"name": "时间差(40ns)", "type": "uint32"},
        ],
    },
    "EB030505": {
        "名称": "NTB校时",
        "fields": [
            {"name": "校时时刻 YYMMDDhhmmss", "type": "bcd_time"},
            {"name": "NTB时间(40ns)", "type": "uint32"},
        ],
    },
    "EB030506": {
        "名称": "NTB校时_698方式专用",
        "fields": [
            {"name": "前缀", "type": "uint8", "default": 0x1C},
            {"name": "校时时刻 YYYYMMDDhhmmss", "type": "bcd_time"},
            {"name": "NTB时间(40ns)", "type": "uint32"},
        ],
    },
    "EB030510": {
        "名称": "通信模块时钟源",
        "fields": [
            {"name": "时钟源", "type": "enum", "enum_map": {0: "网络时钟", 1: "电能表类时钟"}},
        ],
    },
    "EB030520": {
        "名称": "CCO自动NTB校时模式",
        "fields": [
            {"name": "校时模式", "type": "enum",
             "enum_map": {0: "停用", 1: "启用(645格式EB030505)", 2: "启用(698格式EB030505)", 3: "启用(698格式EB030506)"}},
        ],
    },

    # ── 档案/抄控器/主节点地址 ──
    "EB031101": {
        "名称": "从节点档案清单管理",
        "fields": [
            {"name": "操作类型", "type": "enum", "enum_map": {0: "删除", 1: "添加"}},
            {"name": "删除/添加数量", "type": "uint8"},
            {"name": "表计地址列表", "type": "list",
             "item_fields": [{"name": "表计地址", "type": "bcd", "length": 6}]},
        ],
    },
    "EB031102": {
        "名称": "从节点档案清单管理(指令)",
        "fields": [
            {"name": "操作", "type": "enum", "enum_map": {0: "删除从节点档案", 1: "添加从节点档案"}},
        ],
    },
    "EB031201": {
        "名称": "抄控器接入主节点模块事件",
        "fields": [
            {"name": "接入情况", "type": "enum", "enum_map": {0: "断开", 1: "接入"}},
            {"name": "抄控器MAC地址", "type": "hex", "length": 6},
        ],
    },
    "EB032001": {
        "名称": "主节点地址",
        "fields": [{"name": "主节点地址", "type": "bcd", "length": 6}],
    },
    "EB032101": {
        "名称": "上N次精准停电记录",
        "fields": [
            {"name": "停电时刻 YYMMDDhhmmss", "type": "bcd_time"},
            {"name": "缺失过零点数量", "type": "uint16"},
        ],
    },

    # ── 复位/停电 ──
    "EB040201": {
        "名称": "模块复位总次数",
        "fields": [{"name": "复位总次数", "type": "uint16"}],
    },
    "EB040202": {
        "名称": "模块停电总次数",
        "fields": [{"name": "停电总次数", "type": "uint16"}],
    },
    "EB040203": {
        "名称": "模块停电事件有效时长(秒)",
        "fields": [{"name": "有效时长", "type": "uint8", "note": "默认5,范围1~15"}],
    },
    "EB040302": {
        "名称": "上N次停上电记录",
        "fields": [
            {"name": "停上电记录列表", "type": "list",
             "item_fields": [
                 {"name": "停电时刻 YYMMDDhhmmss", "type": "bcd_time"},
                 {"name": "上电时刻 YYMMDDhhmmss", "type": "bcd_time"},
             ]},
        ],
    },

    # ── 上报/通信接口 ──
    "EB040501": {
        "名称": "事件主动上报路径",
        "fields": [
            {"name": "上报路径", "type": "enum",
             "enum_map": {0: "福建56H-F2", 1: "1字节上报06H-F5", 2: "双字节上报06H-F55"}},
        ],
    },
    "EB040502": {
        "名称": "CCO与集中器当前通信接口",
        "fields": [
            {"name": "通信接口", "type": "enum", "enum_map": {0: "串口", 1: "以太网口"}},
        ],
    },
    "EB040602": {
        "名称": "清除CCO任务队列",
        "fields": [
            {"name": "清除类型", "type": "enum", "enum_map": {2: "智能补采", 3: "本地定时", 0xFF: "全部"}},
        ],
    },

    # ── 通信测距（V3.40）──
    "EB030320": {
        "名称": "启动通信测距",
        "fields": [
            {"name": "测距类型", "type": "enum", "enum_map": {0: "有直接通信的上下级节点", 1: "能直接侦听到的节点"}},
            {"name": "允许时间(分钟)", "type": "uint8"},
            {"name": "结果是否主动上报", "type": "enum", "enum_map": {0: "不上报", 1: "上报"}},
            {"name": "测距对象数量", "type": "uint8", "note": "0=按类型自动选择"},
            {"name": "对象地址列表", "type": "list",
             "item_fields": [{"name": "对象地址", "type": "bcd", "length": 6}]},
        ],
    },
    "EB030321": {
        "名称": "测距结果情况表",
        "fields": [
            {"name": "测试开始时间 YYMMDDhhmmss", "type": "bcd_time"},
            {"name": "测试结束时间 YYMMDDhhmmss", "type": "bcd_time"},
            {"name": "测距结果列表", "type": "list",
             "item_fields": [
                 {"name": "目的地址", "type": "bcd", "length": 6},
                 {"name": "载波测距值(ns)", "type": "uint16"},
                 {"name": "无线测距值(ns)", "type": "uint16"},
             ]},
        ],
    },
}

# 有字段定义的数据项
FIELDS_DEFINED = set(EB_DI_FIELDS.keys())


# ═══════════════════════════════════════════════════════════════
# 字段值 → 数据字节 编码
# ═══════════════════════════════════════════════════════════════

def _encode_field_value(field: Dict[str, Any], value: Any) -> bytes:
    """编码单个字段值为数据字节"""
    ftype = field.get("type", "hex")
    length = field.get("length")

    if value is None or str(value) == "":
        value = field.get("default", 0 if ftype in ("uint8", "uint16", "uint24", "uint32", "enum") else "")

    if ftype == "enum":
        return bytes([int(value)])
    if ftype in ("uint8",):
        return bytes([int(value) & 0xFF])
    if ftype == "uint16":
        return (int(value) & 0xFFFF).to_bytes(2, 'little')
    if ftype == "uint24":
        return (int(value) & 0xFFFFFF).to_bytes(3, 'little')
    if ftype == "uint32":
        return (int(value) & 0xFFFFFFFF).to_bytes(4, 'little')
    if ftype == "bcd":
        try:
            b = bytes.fromhex(str(value).replace(" ", ""))
        except ValueError:
            b = b""
        if length:
            b = b[:length].ljust(length, b'\x00')
        return b
    if ftype == "bcd_time":
        # YYMMDDhhmmss 或 YYYYMMDDhhmmss → BCD 6 字节（YYMMDDhhmmss）
        digits = str(value).replace(" ", "").replace("-", "").replace(":", "")
        if len(digits) >= 12:
            digits = digits[-12:]  # 取后12位 YYMMDDhhmmss
        elif len(digits) == 14:
            digits = digits[2:]  # YYYYMMDDhhmmss → YYMMDDhhmmss
        try:
            return bytes.fromhex(digits)
        except ValueError:
            return b'\x00' * 6
    if ftype == "ascii":
        s = str(value)
        if length:
            s = s[:length].ljust(length, ' ')
        return s.encode('ascii', errors='ignore')
    if ftype == "bs8":
        return bytes([int(value) & 0xFF])
    if ftype == "hex":
        try:
            b = bytes.fromhex(str(value).replace(" ", ""))
        except ValueError:
            b = b""
        if length:
            b = b[:length].ljust(length, b'\x00')
        return b
    # list
    if ftype == "list":
        return _encode_list_field(field, value)
    # 默认按 hex
    try:
        return bytes.fromhex(str(value).replace(" ", ""))
    except ValueError:
        return b""


def _encode_list_field(field: Dict[str, Any], items: Any) -> bytes:
    """编码 list 字段（每项按 item_fields 顺序拼接）"""
    item_fields = field.get("item_fields", [])
    if not isinstance(items, list):
        items = []
    data = b""
    for item in items:
        if not isinstance(item, dict):
            item = {}
        for it in item_fields:
            iname = it["name"]
            data += _encode_field_value(it, item.get(iname, it.get("default", "")))
    return data


def encode_eb_di_data(di_code: str, field_values: Dict[str, Any]) -> bytes:
    """按字段定义编码 EB 数据项数据内容字节

    Args:
        di_code: EB 数据标识（如 EB030002）
        field_values: {字段名: 值}，list 字段值为 list[dict]

    Returns:
        数据内容字节（698 A-XDR octet-string 的内容部分）
    """
    info = EB_DI_FIELDS.get(di_code)
    if not info:
        raise ValueError(f"EB0300: {di_code} 未定义数据字段")
    fields = info["fields"]
    data = b""
    for field in fields:
        fname = field["name"]
        val = field_values.get(fname, field.get("default", ""))
        if field.get("type") == "list" and field_values.get(fname) is None:
            # list 字段需显式提供列表（可为空）
            val = field_values.get(fname, [])
        data += _encode_field_value(field, val)
    return data
