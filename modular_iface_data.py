"""模组化终端功能模块接口协议 —— 静态表「单源」。

**每一张表都从协议文档现场抄录**（`协议文档/12.模组化功能协议/模组化终端功能模块接口协议.md`），
并在 `test/test_modular_iface.py` 里逐条对拍；**不要**从其它协议搬表（历史教训：
本仓库曾把别的协议的 21 项 DAR 表搬进来，与本文档表11 的 4 个值直接矛盾）。

| 表 | 文档出处 |
| --- | --- |
| `DTA1_NAMES` | §7.3~§7.11 + 附录 D~L 模块名 |
| `DTA2_NAMES` | §7.1（0H 只读 / 1H 读-写 / 2H 只写） |
| `GENERIC_DT` | 附录 C.1（DTA1=0H） |
| `MODULE_DT` | 附录 G.3 / J.3 / K.3 / L.3 |
| `DAR_NAMES` | 表11（**只 0/1/2/255 四个值**） |
| `APDU_*` | 表13 |
| `CTRL_CODE_NAMES` | 表2 |
| `DIR_PRM_MEANINGS` | 表1 |
| `PHYSICAL_UNITS` | 附录 M 表31（1~75 + 254 + 255） |
| `DEVICE_SUBIFACES` | 附录 D.1/E.1/F.1/G.1/J.1/K.1/L.1 |
| `VENDOR_ID`/`PRODUCT_ID` | 附录 B.1 |
| `IFACE_TYPE_NAMES`/`LINK_RESPONSE_FUNC_CONFIG` | 表18 |

⚠ DT 的位段划分存在**文档内部矛盾**（见 `decode_dt` 的文档字符串）：表22 写「bit15…bit11 = DTA1」，
而附录 G/J/K/L 的 DT 标识（4000/7100/8000/9000）只与「bit15…bit12 = DTA1」自洽。本模块按附录取
**4+4+8**（DTA1/DTA2/DTB），与 §7.3~§7.11 的「DTA1=4H 遥信脉冲 / 7H 控制 / 8H 模拟量采集 /
9H 回路状态巡检」逐一吻合。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ── 表22 / §7：信息类标识 ─────────────────────────────────────────────

#: DTA1（DT 的最高 4 位 = 标识的第一个十六进制位）
DTA1_NAMES: Dict[int, str] = {
    0x0: "通用信息类",
    0x1: "远程通信模块",
    0x2: "本地通信模块",
    0x3: "RS-485通信模块",
    0x4: "遥信脉冲模块",
    0x5: "CAN通信模块",
    0x6: "M-Bus通信模块",
    0x7: "控制模块",
    0x8: "模拟量采集模块",
    0x9: "回路状态巡检模块",
}

#: DTA2（§7.1）
DTA2_NAMES: Dict[int, str] = {
    0x0: "只读",
    0x1: "读-写",
    0x2: "只写",
}

# ── 附录 C.1：DTA1=0H 通用信息类（10 条，逐条抄录）────────────────────

GENERIC_DT: Dict[int, Dict[str, str]] = {
    0x0000: {
        "name": "模块信息",
        "module": "通用信息类",
        "definition": "structure{模块设备型号 visible-string，模块设备ID visible-string，软件版本 double-long-unsigned，"
        "软件发布日期 date，硬件版本 double-long-unsigned，硬件发布日期 date，厂商编码 visible-string}",
    },
    0x0001: {
        "name": "链路协商信息",
        "module": "通用信息类",
        "definition": "structure{协议版本号 long-unsigned，功能模块设备型号 visible-string，功能模块设备ID visible-string，"
        "最大发送缓冲区长度（字节） long-unsigned，最大接收缓冲区长度（字节） long-unsigned，并发传输窗口数 unsigned，"
        "虚拟通道工作模式 array structure{接口类型 enum{CDC-ACM（1），CDC-ECM（2），HID（3）}，功能配置 unsigned}}",
    },
    0x0002: {"name": "协议版本", "module": "通用信息类", "definition": "long-unsigned"},
    0x0003: {"name": "电源状态", "module": "通用信息类", "definition": "enum{上电（0），掉电（1）}"},
    0x0004: {
        "name": "文件传输状态",
        "module": "通用信息类",
        "definition": "structure{总包数 double-long-unsigned，包传输状态 bit-string}",
    },
    0x0100: {"name": "时钟", "module": "通用信息类", "definition": "date_time"},
    0x0200: {"name": "硬件初始化", "module": "通用信息类", "definition": "NULL"},
    0x0201: {"name": "参数初始化", "module": "通用信息类", "definition": "NULL"},
    0x0202: {"name": "数据初始化", "module": "通用信息类", "definition": "NULL"},
    0x0203: {
        "name": "文件传输",
        "module": "通用信息类",
        "definition": "structure{文件标识 unsigned，段序号 double-long-unsigned，总段数 double-long-unsigned，文件数据 octet-string}",
    },
}

# ── 附录 G.3 / J.3 / K.3 / L.3：模块信息类（11 条，逐条抄录）──────────

MODULE_DT: Dict[int, Dict[str, str]] = {
    0x4000: {
        "name": "遥信状态",
        "module": "遥信脉冲模块",
        "definition": "structure{遥信状态 bit-string，遥信变位状态 bit-string，遥信变位时间 array date_time}"
        "；遥信状态 bit0 表示第一路（0 合 / 1 分）；变位状态 bit0 表示第一路（0 无变位 / 1 有变位）",
    },
    0x4001: {
        "name": "上一次脉冲计数和时间",
        "module": "遥信脉冲模块",
        "definition": "array 脉冲计数；脉冲计数∷=structure{脉冲个数 double-long-unsigned，统计时间 double-long-unsigned（单位：ms）}"
        "；脉冲数为统计周期内的脉冲数量，读取后清零",
    },
    0x4002: {
        "name": "脉冲计数及统计时间",
        "module": "遥信脉冲模块",
        "definition": "array 脉冲计数；脉冲计数∷=structure{脉冲个数 double-long-unsigned，统计时间 double-long-unsigned（单位：ms）}"
        "；脉冲数为累计脉冲数量",
    },
    0x4100: {
        "name": "遥信脉冲功能配置",
        "module": "遥信脉冲模块",
        "definition": "bit-string；bit0 表示第 1 路的功能配置（0 遥信功能 / 1 脉冲功能），依次类推",
    },
    0x4101: {"name": "遥信防抖时间", "module": "遥信脉冲模块", "definition": "long-unsigned（单位：ms）"},
    0x7100: {
        "name": "继电器输出模式",
        "module": "控制模块",
        "definition": "enum{脉冲模式（1），电平模式（2）}",
    },
    0x7101: {"name": "继电器输出脉冲宽度", "module": "控制模块", "definition": "long-unsigned（单位：ms）"},
    0x8000: {
        "name": "模拟量采样",
        "module": "模拟量采集模块",
        "definition": "array 模拟量；模拟量∷=structure{模拟量数值 double-long，模拟量单位及换算 Scaler_Unit}",
    },
    0x9000: {
        "name": "回路状态巡检模块工况信息",
        "module": "回路状态巡检模块",
        "definition": "structure{状态量 array octet-string，标识量 array octet-string，第1组模拟量~第30组模拟量 array double-long-unsigned}",
    },
    0x9001: {
        "name": "回路状态巡检模块事件发生时工况信息",
        "module": "回路状态巡检模块",
        "definition": "structure{发生时状态量 array octet-string，标识量 array octet-string，"
        "发生时第1组模拟量~发生时第30组模拟量 array double-long-unsigned，发生前状态量 array octet-string，标识量 array octet-string，"
        "发生前第1组模拟量~发生前第30组模拟量 array double-long-unsigned}",
    },
    0x9002: {
        "name": "回路状态巡检模块运行信息",
        "module": "回路状态巡检模块",
        "definition": "structure{状态量 array octet-string，标识量 array octet-string，模拟量采样 array double-long-unsigned}",
    },
}

#: DT 标识 → 信息类名称（附录 C + 附录 G/J/K/L，共 21 条）
DT_NAMES: Dict[int, str] = {dt: item["name"] for dt, item in {**GENERIC_DT, **MODULE_DT}.items()}
#: DT 标识 → ASN.1 定义文本
DT_DEFINITIONS: Dict[int, str] = {
    dt: item["definition"] for dt, item in {**GENERIC_DT, **MODULE_DT}.items()
}
#: DT 标识 → 所属模块名
DT_MODULES: Dict[int, str] = {dt: item["module"] for dt, item in {**GENERIC_DT, **MODULE_DT}.items()}

#: 附录 C 0000「模块信息」的 7 个成员名（表6~表9 / structure 成员顺序）
MODULE_INFO_FIELDS: Tuple[str, ...] = (
    "模块设备型号",
    "模块设备ID",
    "软件版本",
    "软件发布日期",
    "硬件版本",
    "硬件发布日期",
    "厂商编码",
)

#: DT → structure 成员名（A-XDR 的 `structure` 成员自带类型标签，只需补名字）
STRUCTURE_FIELDS: Dict[int, Tuple[str, ...]] = {
    0x0000: MODULE_INFO_FIELDS,
    0x0001: (
        "协议版本号",
        "功能模块设备型号",
        "功能模块设备ID",
        "最大发送缓冲区长度",
        "最大接收缓冲区长度",
        "并发传输窗口数",
        "虚拟通道工作模式",
    ),
    0x0004: ("总包数", "包传输状态"),
    0x0203: ("文件标识", "段序号", "总段数", "文件数据"),
    0x4000: ("遥信状态", "遥信变位状态", "遥信变位时间"),
    0x9000: ("状态量", "标识量") + tuple(f"第{i}组模拟量" for i in range(1, 31)),
    0x9001: (
        ("发生时状态量", "标识量")
        + tuple(f"发生时第{i}组模拟量" for i in range(1, 31))
        + ("发生前状态量", "标识量")
        + tuple(f"发生前第{i}组模拟量" for i in range(1, 31))
    ),
    0x9002: ("状态量", "标识量", "模拟量采样"),
}

#: DT → array 元素名（元素为 structure 时给出其成员名；见附录 G.3 / K.3）
ARRAY_FIELDS: Dict[int, Tuple[str, ...]] = {
    0x4001: ("脉冲个数", "统计时间"),
    0x4002: ("脉冲个数", "统计时间"),
    0x8000: ("模拟量数值", "模拟量单位及换算"),
}

# ── 表11：数据访问结果 DAR（**只 4 个值**）────────────────────────────

DAR_NAMES: Dict[int, str] = {
    0: "成功",
    1: "拒绝读写",
    2: "信息类未定义",
    255: "其它",
}

# ── 表13：APDU CHOICE ────────────────────────────────────────────────

APDU_EN_NAMES: Dict[int, str] = {
    1: "LinkRequest",
    2: "GetRequest",
    3: "SetRequest",
    4: "ReportNotification",
    129: "LinkResponse",
    130: "GetResponse",
    131: "SetResponse",
    132: "ReportResponse",
}

APDU_SHORT_NAMES: Dict[int, str] = {
    1: "链路协商请求",
    2: "数据读取请求",
    3: "设置请求",
    4: "上报通知",
    129: "链路协商响应",
    130: "数据读取响应",
    131: "设置响应",
    132: "上报通知响应",
}

#: 兼容既有调用方（`main_gui` 查询页按 `APDU_NAMES` 取显示名）
APDU_NAMES: Dict[int, str] = {
    tag: f"{APDU_EN_NAMES[tag]} {APDU_SHORT_NAMES[tag]}" for tag in APDU_EN_NAMES
}

# ── 表2 / 表1：控制域 ────────────────────────────────────────────────

CTRL_CODE_NAMES: Dict[int, str] = {
    0x00: "确认帧",
    0x01: "否认帧",
    0x02: "信息帧",
}

DIR_PRM_MEANINGS: Dict[Tuple[int, int], str] = {
    (0, 0): "终端对功能模块上报的响应",
    (0, 1): "终端发起的请求",
    (1, 0): "功能模块发起的请求或上报",
    (1, 1): "功能模块对终端请求或通知的响应",
}

# ── 附录 M 表31：物理单位枚举（1~75 + 254 + 255）─────────────────────

#: 代码 → (单位符号, 量, 单位名称)
PHYSICAL_UNITS: Dict[int, Tuple[str, str, str]] = {
    1: ("a", "时间", "年"),
    2: ("mo", "时间", "月"),
    3: ("wk", "时间", "周"),
    4: ("d", "时间", "日"),
    5: ("h", "时间", "小时"),
    6: ("min.", "时间", "分"),
    7: ("s", "时间（t）", "秒"),
    8: ("°", "角度", "度"),
    9: ("℃", "温度（T）", "摄氏度"),
    10: ("CNY", "（当地）货币", ""),
    11: ("m", "长度（l）", "米"),
    12: ("m/s", "速度（v）", "米/秒"),
    13: ("m3", "体积（V）；rV，仪表常数或脉冲值（体积）", "立方米"),
    14: ("m3", "修正的体积", "立方米"),
    15: ("m3/h", "流量", "立方米/小时"),
    16: ("m3/h", "修正的流量", "立方米/小时"),
    17: ("m3/d", "流量", "立方米/天"),
    18: ("m3/d", "修正的流量", "立方米/天"),
    19: ("l", "容积", "升"),
    20: ("kg", "质量（m）", "千克"),
    21: ("N", "力（F）", "牛顿"),
    22: ("Nm", "扭矩", "牛顿米"),
    23: ("Pa", "压强（p）", "帕斯卡"),
    24: ("bar", "压力（p）", "巴"),
    25: ("J", "能量", "焦耳"),
    26: ("J/h", "热功", "焦每小时"),
    27: ("W", "有功功率（P）", "瓦"),
    28: ("kW", "有功功率（P）", "千瓦"),
    29: ("VA", "视在功率（S）", "伏安"),
    30: ("kVA", "视在功率（S）", "千伏安"),
    31: ("var", "无功功率（Q）", "乏"),
    32: ("kvar", "无功功率（Q）", "千乏"),
    33: ("kWh", "有功能量；rw，有功电能表常数或脉冲值", "千瓦·时"),
    34: ("kVAh", "视在能量；rS，视在电能表常数或脉冲值", "千伏·安·小时"),
    35: ("kvarh", "无功能量；rB，无功电能表常数或脉冲", "千乏·时"),
    36: ("A", "电流（I）", "安培"),
    37: ("C", "电量（Q）", "库仑"),
    38: ("V", "电压（U）", "伏特"),
    39: ("V/m", "电场强度（E）", "伏/米"),
    40: ("F", "电容（C）", "法拉"),
    41: ("Ω", "电阻（R）", "欧姆"),
    42: ("Ωm2/m", "电阻率（ρ）", "欧姆米"),
    43: ("Wb", "磁通量（Φ）", "韦伯"),
    44: ("T", "磁通密度（T）", "特斯拉"),
    45: ("A/m", "磁场强度（H）", "安培/米"),
    46: ("H", "电感（L）", "亨利"),
    47: ("Hz", "频率", "赫兹"),
    48: ("1/(Wh)", "有功能量表常数或脉冲", ""),
    49: ("1/(varh)", "无功能量表常数或脉冲", ""),
    50: ("1/(VAh)", "视在能量表常数或脉冲", ""),
    51: ("%", "百分比", "百分之"),
    52: ("byte", "字节", "字节"),
    53: ("dBm", "分贝毫瓦", ""),
    54: ("CNY/kWh", "电价", ""),
    55: ("Ah", "安时", "安时"),
    56: ("ms", "毫秒", "毫秒"),
    57: ("dbμV", "发射电平", ""),
    58: ("V2h", "电压平方小时；rU2h，电压平方小时表计常数或脉冲值", "电压平方·时"),
    59: ("A2h", "电流平方小时；rU2h，电流平方小时表计常数或脉冲值", "电流平方·时"),
    60: ("Wh/m3", "单位体积能量", "3.6*103 J/m3"),
    61: ("J/m3", "热量，沃泊", ""),
    62: ("Mol%", "气体成分摩尔分数", "摩尔百分比"),
    63: ("g/m3", "质量密度，材料数量", ""),
    64: ("Pa s", "动态粘度", "帕斯卡秒"),
    65: ("J/kg", "每单位质量的能量", "焦耳/千克"),
    66: ("kg/s", "质量流量", "千克/秒"),
    67: ("S, mho", "电导系数", "欧姆的倒数"),
    68: ("K", "温度 (T)", "开尔文"),
    69: ("1/(V2h)", "RU2h，电压平方小时表计常数或脉冲值", ""),
    70: ("1/(A2h)", "RI2h，电流平方小时表计常数或脉冲值", ""),
    71: ("1/m3", "RV，表计常数或脉冲值 (容量)", ""),
    72: ("dB", "表示物理量的两个值之比的对数单位", ""),
    73: ("Wh", "有功能量；rw，有功电能表常数或脉冲值", "瓦·时"),
    74: ("VAh", "视在能量；rS，视在电能表常数或脉冲值", "伏·安·小时"),
    75: ("varh", "无功能量；rB，无功电能表常数或脉冲", "乏·时"),
    254: ("其他单位", "", ""),
    255: ("无单位、缺单位、计数", "", ""),
}


def unit_text(code: Any) -> str:
    """单位代码 → ``V（伏特）`` 形式；未知代码原样返回。"""
    if code is None:
        return "未定义"
    try:
        code_i = int(code)
    except (TypeError, ValueError):
        return str(code)
    item = PHYSICAL_UNITS.get(code_i)
    if item is None:
        return f"未定义({code_i})"
    symbol, _quantity, name = item
    if name and name != symbol:
        return f"{symbol}（{name}）"
    return symbol


# ── 附录 D/E/F/G/J/K/L：设备子接口 ───────────────────────────────────

DEVICE_SUBIFACES: Dict[str, List[Tuple[Any, str, str]]] = {
    "远程通信模块（附录D·表24）": [
        (1, "CDC-ACM", "管理通道"),
        (2, "CDC-ACM", "AT交互通道"),
        (3, "CDC-ACM", "PPP拨号通道"),
        (4, "CDC-ECM", "网络数据通信通道"),
    ],
    "本地通信模块（附录E·表25）": [
        (1, "CDC-ACM", "管理通道"),
        (2, "CDC-ACM", "数据传输通道"),
        (3, "CDC-ECM", "数据传输通道"),
    ],
    "RS-485通信模块（附录F·表26）": [
        (1, "CDC-ACM", "管理通道"),
        (2, "CDC-ACM", "485-1通道"),
        ("…", "CDC-ACM", "…"),
        ("N+1", "CDC-ACM", "485-N通道"),
    ],
    "遥信脉冲模块（附录G·表27）": [
        (1, "CDC-ACM", "管理通道"),
        (2, "CDC-ACM", "数据传输通道"),
    ],
    "控制模块（附录J·表28）": [
        (1, "CDC-ACM", "管理通道"),
        (2, "CDC-ACM", "数据传输通道"),
    ],
    "模拟量采集模块（附录K·表29）": [
        (1, "CDC-ACM", "管理通道"),
        (2, "CDC-ACM", "数据传输通道"),
    ],
    "回路状态巡检模块（附录L·表30）": [
        (1, "CDC-ACM", "管理通道"),
        (2, "CDC-ACM", "数据传输通道"),
    ],
}

#: 附录 H/I 只写「子接口定义见附录 F」，不另立表
DEVICE_SUBIFACE_ALIASES: Dict[str, str] = {
    "CAN通信模块（附录H）": "RS-485通信模块（附录F·表26）",
    "M-Bus通信模块（附录I）": "RS-485通信模块（附录F·表26）",
}

# ── 附录 B：VID/PID ─────────────────────────────────────────────────

VENDOR_ID = 0x3C93
PRODUCT_ID = 0xFFFF

# ── 表18：链路协商响应的枚举 ────────────────────────────────────────

IFACE_TYPE_NAMES: Dict[int, str] = {1: "CDC-ACM", 2: "CDC-ECM", 3: "HID"}

LINK_RESPONSE_FUNC_CONFIG: Dict[int, str] = {
    0: "管理通道",
    1: "远程通信",
    2: "PLC/RF通信",
    3: "RS-485通信",
    4: "遥信脉冲",
    5: "CAN通信",
    6: "M-Bus通信",
    7: "控制",
    8: "模拟量采集",
    9: "RS232通信",
}

#: 附录 C 0003 / J.3 7100 的枚举 ────────────────────────────────────

POWER_STATE_NAMES: Dict[int, str] = {0: "上电", 1: "掉电"}

RELAY_OUTPUT_MODE_NAMES: Dict[int, str] = {1: "脉冲模式", 2: "电平模式"}

#: DT → 其枚举值名称表（解析行把裸 enum 值翻成中文）
DT_ENUM_NAMES: Dict[int, Dict[int, str]] = {
    0x0003: POWER_STATE_NAMES,
    0x7100: RELAY_OUTPUT_MODE_NAMES,
}


# ── DT 解码 ──────────────────────────────────────────────────────────


def decode_dt(raw: bytes) -> Dict[str, Any]:
    """信息类标识 DT（**大端** 2 字节，A-XDR long-unsigned）→ 字段字典。

    返回 ``{raw, dt, dta1, dta2, dtb, dta1_name, dta2_name, name, module, definition, text}``。

    ⚠ 位段划分的文档内部矛盾（本实现取 4+4+8，依据见模块文档）：
      * 表22 写「bit15…bit11 = DTA1 / bit10…bit8 = DTA2 / bit7…bit0 = DTB」（5+3+8）；
      * 但附录 G/J/K/L 的 DT 标识 4000/7100/8000/9000 只与
        「bit15…bit12 = DTA1 / bit11…bit8 = DTA2 / bit7…bit0 = DTB」（4+4+8）自洽：
        附录 G 的 4000 对应 §7.6 的「DTA1=4H 遥信脉冲」，附录 J 的 7100 对应 §7.9 的
        「DTA1=7H 控制」，附录 K 的 8000 对应 §7.10 的「DTA1=8H 模拟量采集」，
        附录 L 的 9000 对应 §7.11 的「DTA1=9H 回路状态巡检」。
        按 5+3+8 读则 0x4000 会解成 DTA1=8H（模拟量采集），与附录 G 直接冲突。
      两份取值的差异只体现在 bit11；文档所有 DT 标识的 bit11 均为 0，故 4+4+8 与
      5+3+8 在**全部文档取值上等价**，仅当实机把 DTA1∈{8,9} 的 bit11 用起来才会分歧。
    """
    data = bytes(raw or b"")
    info: Dict[str, Any] = {
        "raw": data,
        "dt": None,
        "dta1": None,
        "dta2": None,
        "dtb": None,
        "dta1_name": "",
        "dta2_name": "",
        "name": "",
        "module": "",
        "definition": "",
        "text": "",
    }
    if len(data) < 2:
        info["text"] = f"DT 长度不足（{len(data)} 字节，需 2 字节大端）"
        return info
    dt = int.from_bytes(data[:2], "big")
    dta1 = (dt >> 12) & 0x0F
    dta2 = (dt >> 8) & 0x0F
    dtb = dt & 0xFF
    info.update(
        {
            "dt": dt,
            "dta1": dta1,
            "dta2": dta2,
            "dtb": dtb,
            "dta1_name": DTA1_NAMES.get(dta1, "保留"),
            "dta2_name": DTA2_NAMES.get(dta2, "保留"),
            "name": DT_NAMES.get(dt, ""),
            "module": DT_MODULES.get(dt, ""),
            "definition": DT_DEFINITIONS.get(dt, ""),
        }
    )
    info["text"] = dt_text(info)
    return info


def dt_text(info: Dict[str, Any]) -> str:
    """把 `decode_dt` 的结果拼成表格「说明」列文本。"""
    if info.get("dt") is None:
        return str(info.get("text") or "DT 未知")
    dt = int(info["dt"])
    parts = [
        f"DT=0x{dt:04X}",
        f"DTA1={int(info['dta1']):X}H({info['dta1_name']})",
        f"DTA2={int(info['dta2']):X}H({info['dta2_name']})",
        f"DTB={int(info['dtb']):02X}H",
    ]
    if info.get("name"):
        parts.append(f"信息类：{info['name']}（{info.get('module') or '模块'}）")
    elif int(info["dta1"]) in DTA1_NAMES:
        parts.append("信息类：文档未定义（保留）")
    else:
        parts.append("信息类：未定义（保留模块号）")
    return "，".join(parts)


def dt_name(dt: Optional[int]) -> str:
    """DT 数值 → 可读名（无定义时回退 ``0xXXXX``）。"""
    if dt is None:
        return "未知"
    name = DT_NAMES.get(int(dt))
    return f"{name}(0x{int(dt):04X})" if name else f"0x{int(dt):04X}"
