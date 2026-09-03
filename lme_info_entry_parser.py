"""LME HPLC双模模块信息条目解析器

基于《LME产品相关信息生产运维接口手册_V2.4_251115》实现：
- 4.2 查询HPLC单模STA详细信息（DI=0x04FFAAF9，DL/T645-2007框架，固定布局251B数据单元）
- 4.6 查询/4.7 设置HPLC双模STA详细信息（DI=0xFF00DD01，信息条目TLV格式）

输入数据域均为DLT645减0x33后的真实数据，且包含前4字节DI（小端）。
"""

import re
from typing import Dict, List, Tuple, Optional


# LME自定义数据标识（解析后编码，即 int.from_bytes(DI4字节, 'little') 的 %08X）
DI_STA_VERSION_SINGLE = "04FFAAF9"  # 手册4.2 单模STA详细信息
DI_DUAL_ENTRY = "FF00DD01"          # 手册4.6/4.7 双模STA详细信息查询/设置


# 信息条目定义: {分类ID: {数据ID: (名称, 编码, 长度说明, 格式化函数)}}
# 编码: 1=ASCII, 2=BIN, 3=BCD
LME_INFO_ENTRIES: Dict[int, Dict[int, Tuple[str, int, str, Optional[str]]]] = {
    0: {  # 基本信息
        1: ("外部厂商代码", 1, "2", "ascii_rev"),
        2: ("外部芯片代码", 1, "2", "ascii_rev"),
        3: ("外部版本日期", 3, "3", "bcd_date"),
        4: ("外部版本号", 3, "2", "bcd_ver"),
        5: ("内部厂商代码", 1, "2", "ascii_rev"),
        6: ("内部芯片代码", 1, "2", "ascii_rev"),
        7: ("应用省份", 2, "1", "bin"),
        8: ("应用方案", 2, "1", "bin"),
        9: ("模块功能开关", 2, "8", "bin"),
        11: ("模块类型", 2, "1", "module_type"),
        12: ("模块生产信息", 3, "6", "bcd"),
        13: ("最后升级时间", 3, "6", "bcd_datetime"),
        14: ("程序CRC32", 2, "4", "hex"),
        15: ("本地接口默认信息", 2, "2", "bin"),
        16: ("默认HPLC频段", 2, "1", "bin"),
        17: ("默认HPLC参数", 2, "2", "bin"),
        18: ("默认HRF信道", 2, "2", "bin"),
        19: ("默认HRF参数", 2, "2", "bin"),
        30: ("继电器控制及反馈", 2, "2", "bin"),
    },
    1: {  # 程序信息
        1: ("编译时间", 1, "20", "compile_time"),
        2: ("模块生产时间", 3, "2", "bcd"),
        3: ("总工程版本", 2, "2", "bin_ver"),
        4: ("boot程序版本", 2, "2", "bin_ver"),
        5: ("芯片程序版本", 2, "2", "bin_ver"),
        6: ("驱动层版本", 2, "2", "bin_ver"),
        7: ("载波接口层版本", 2, "2", "bin_ver"),
        8: ("无线PHY层版本", 2, "2", "bin_ver"),
        9: ("载波MAC层版本", 2, "2", "bin_ver"),
        10: ("无线MAC层版本", 2, "2", "bin_ver"),
        11: ("网络层版本", 2, "2", "bin_ver"),
        12: ("APS层版本", 2, "2", "bin_ver"),
        13: ("APP层版本", 2, "2", "bin_ver"),
        14: ("应用接口层版本", 2, "2", "bin_ver"),
        15: ("以太网驱动版本", 2, "2", "bin_ver"),
        16: ("USB驱动版本", 2, "2", "bin_ver"),
        17: ("USB芯片版本", 2, "2", "bin_ver"),
        20: ("加密库版本", 2, "2", "bin_ver"),
        21: ("时钟管理库版本", 2, "2", "bin_ver"),
        22: ("VSS版本", 2, "2", "bin_ver"),
        23: ("台区识别库版本", 2, "2", "bin_ver"),
        24: ("通用数据采集库版本", 2, "2", "bin_ver"),
        30: ("深化应用库版本", 2, "2", "bin_ver"),
    },
    2: {  # 硬件信息
        1: ("芯片ID", 2, "11", "hex"),
        2: ("模块ID", 2, "11", "hex"),
        3: ("硬件型号", 1, "24", "ascii_trim"),
        4: ("芯片型号", 2, "1", "chip_type"),
        5: ("Flash型号及容量", 2, "4", "hex"),
        9: ("载波PA功放型号", 2, "1", "bin"),
        10: ("特征电流拓扑类型", 2, "1", "bin"),
        11: ("无线射频开关类型", 2, "1", "bin"),
        12: ("功能模块设备ID", 2, "24", "hex"),
        15: ("模块时钟信息", 3, "26", "bcd"),
        16: ("模块MAC地址", 2, "6", "hex"),
        17: ("模块资产编码", 2, "32", "hex"),
        18: ("模块备案信息", 2, "30", "hex"),
        20: ("过零检测信息", 2, "13", "zero_cross_info"),
        21: ("NTB采样信息", 2, "12", "ntb_info"),
        22: ("载波接收信息", 2, "2", "bin"),
        23: ("无线接收信息", 2, "2", "bin"),
        24: ("USB频偏信息", 2, "6", "bin"),
        25: ("无线校准信息", 2, "3", "bin"),
        26: ("温度校准信息", 2, "4", "bin"),
    },
    3: {  # 网络信息
        1: ("节点网络信息", 2, "27", "bin"),
        2: ("软件信息组", 2, "3", "sw_info_group"),
        3: ("硬件信息组", 2, "31", "hw_info_group"),
    },
    7: {  # OTP信息（现场固件复用分类3信息组结构，官方上位机同结构解码）
        1: ("硬件信息组", 2, "31", "hw_info_group"),
        2: ("软件信息组", 2, "3", "sw_info_group"),
    },
    4: {  # 运行信息
        1: ("复位计数", 2, "2", "u16"),
        2: ("停电计数", 2, "2", "u16"),
        3: ("复电计数", 2, "2", "u16"),
        4: ("过零计数", 2, "2", "u16"),
        5: ("主串口发送次数", 2, "2", "u16"),
        6: ("主串口接收次数", 2, "2", "u16"),
        7: ("广播校时次数", 2, "2", "u16"),
        8: ("精准校时次数", 2, "2", "u16"),
        9: ("MAC接收HPLC帧总数", 2, "4", "u32"),
        10: ("MAC接收RF帧总数", 2, "4", "u32"),
        11: ("MAC接收HPLC信标帧", 2, "4", "u32"),
        12: ("MAC接收RF信标帧", 2, "4", "u32"),
        13: ("MAC接收网络帧", 2, "4", "u32"),
        14: ("MAC接收应用帧", 2, "4", "u32"),
        15: ("接收本地广播帧", 2, "4", "u32"),
        16: ("接收代理广播帧", 2, "4", "u32"),
        17: ("作为代理处理转发", 2, "2", "u16"),
        18: ("节点离线次数", 2, "2", "u16"),
        19: ("节点发送帧总数", 2, "4", "u32"),
        20: ("节点发送成功次数", 2, "4", "u32"),
        21: ("节点发送失败次数", 2, "4", "u32"),
        22: ("节点发送失败原因1", 2, "2", "u16"),
        23: ("节点发送失败原因2", 2, "2", "u16"),
        24: ("节点发送失败原因3", 2, "2", "u16"),
        25: ("节点发送失败原因4", 2, "2", "u16"),
        26: ("节点发送失败原因5", 2, "2", "u16"),
        27: ("节点发送失败原因6", 2, "2", "u16"),
        28: ("节点发送失败原因7", 2, "2", "u16"),
        29: ("节点发送失败原因8", 2, "2", "u16"),
        30: ("节点发送失败原因9", 2, "2", "u16"),
        31: ("节点发送失败原因10", 2, "2", "u16"),
        32: ("复位原因1次数", 2, "1", "u8"),
        33: ("复位原因2次数", 2, "1", "u8"),
        34: ("复位原因3次数", 2, "1", "u8"),
        35: ("复位原因4次数", 2, "1", "u8"),
        36: ("复位原因5次数", 2, "1", "u8"),
        37: ("复位原因6次数", 2, "1", "u8"),
        38: ("最近一次复位原因", 2, "1", "u8"),
        39: ("无线接收报文次数", 2, "4", "u32"),
        40: ("载波接收报文次数", 2, "4", "u32"),
        41: ("电表接口交互发送", 2, "4", "u32"),
        42: ("电表接口交互接收", 2, "4", "u32"),
    },
    5: {  # CCO运行信息
        1: ("开关信息", 2, "4", "bin"),
        2: ("本地串口当前通信参数", 2, "2", "bin"),
        3: ("以太网参数", 2, "12", "bin"),
        4: ("复位信息", 2, "14", "bin"),
        5: ("电压跌落信息", 2, "4", "bin"),
        6: ("组网完成标识", 2, "1", "bin"),
    },
}


MODULE_TYPE_MAP = {
    0: "无效", 1: "抄控器", 2: "集中器本地通信单元", 3: "电表通信单元",
    4: "中继器", 5: "II型采集器", 6: "I型采集器", 7: "三相表通信单元",
    12: "户内显示单元", 15: "能源控制器模块", 16: "智能融合终端模块",
    17: "智慧能源单元模块", 20: "采集器ESIF接口模块", 21: "光伏转换器采集器模块",
    22: "湖南四可装置双模模块", 23: "湖南四可装置无线模块",
    24: "光伏转换器表模式模块", 25: "量测单元即装即采模块",
    30: "导轨表通用标准模块", 31: "导轨表特征电流模块",
    35: "分布式电源接入单元模块", 50: "光伏协议转换器",
    51: "智能光伏感知终端", 52: "智能量测开关终端",
    53: "导轨式电能表", 54: "湖南四可融合装置", 55: "充电桩协议转换器",
}

CHIP_TYPE_MAP = {
    4: "LME3960C", 5: "LME3960A1", 6: "LME3960A13",
    7: "LME3960B0-80pin", 8: "LME3960B0-88pin",
}

# 分类名称（手册4.3 信息条目分类ID）
CATEGORY_NAMES = {
    0: "基本信息", 1: "程序信息", 2: "硬件信息",
    3: "网络信息", 4: "运行信息", 5: "CCO运行信息",
}

# 手册4.3.3 波特率信息
BAUD_MAP = {
    0: "BR_300", 1: "BR_600", 2: "BR_1200", 3: "BR_2400",
    4: "BR_4800", 5: "BR_9600", 6: "BR_19200", 7: "BR_38400",
    8: "BR_57600", 9: "BR_115200", 10: "BR_230400",
    11: "BR_460800", 12: "BR_921600",
}

# 手册4.3.4 校验位
PARITY_MAP = {0: "无校验", 1: "奇校验", 2: "偶校验"}

# 应用省份（手册4.1 注2）
PROVINCE_MAP = {
    0: "国网标志", 1: "江苏Ⅰ", 2: "山西", 3: "四川", 4: "宁夏",
    5: "陕西", 6: "湖南", 7: "安徽", 8: "重庆", 9: "辽宁",
    10: "水投", 11: "北京",
}

# 默认HPLC频段（手册4.1 注：频段 0=10M；1=3M；2=2.2M；3=1.2M）
BAND_MAP = {0: "10M", 1: "3M", 2: "2.2M", 3: "1.2M"}

# 模块功能开关位（分类0/数据9，B0~B7，手册4.3）
FUNC_SWITCH_BITS = {
    0: "即装即采功能开关",
    1: "万年历启动开关",
    2: "低功耗使能开关",
    3: "白名单启动开关",
}

# 4.7 设置结果码
SET_RESULT_MAP = {
    0: "设置成功",
    1: "参数不支持设置",
    2: "参数内容格式错误",
    3: "参数保存失败",
}

# 4.6/4.7 头部编码格式
ENCODING_NAMES = {1: "ASCII", 2: "BIN", 3: "BCD"}

# 组网完成标识（分类5/数据6）
NETWORK_DONE_MAP = {0: "未完成", 1: "阶段完成", 2: "白名单全部入网"}


def _format_value(data: bytes, fmt: str) -> str:
    """根据格式化类型将原始字节转换为可读字符串"""
    if not data:
        return "空"

    if fmt == "ascii":
        try:
            return data.decode("ascii", errors="replace").strip()
        except Exception:
            return data.hex().upper()

    if fmt == "ascii_rev":
        # 2字节ASCII逆序显示（如传输[H,L]显示为LH）
        try:
            rev = data[::-1]
            return rev.decode("ascii", errors="replace").strip()
        except Exception:
            return data.hex().upper()

    if fmt == "ascii_trim":
        try:
            s = data.decode("ascii", errors="replace").rstrip("\x00")
            return s if s else "未写入"
        except Exception:
            return data.hex().upper()

    if fmt == "bcd":
        # 通用BCD：逐字节转为两位十六进制字符串
        return "".join(f"{b:02X}" for b in data)

    if fmt == "bcd_date":
        # BCD日期: DD MM YY -> YYMMDD
        if len(data) >= 3:
            return f"{data[2]:02X}{data[1]:02X}{data[0]:02X}"
        return data.hex().upper()

    if fmt == "bcd_ver":
        # BCD版本: YY XX -> XX.YY
        if len(data) >= 2:
            return f"{data[1]:02X}.{data[0]:02X}"
        return data.hex().upper()

    if fmt == "bcd_datetime":
        # BCD: YYMMDDHHmmSS
        return "".join(f"{b:02X}" for b in data)

    if fmt == "bin_ver":
        # BIN版本: 低字节在前，显示为 VXXYY 或 PXXXX 等
        if len(data) >= 2:
            low, high = data[0], data[1]
            # 尝试识别前缀字符（大写ASCII字母）
            prefix = ""
            if 0x41 <= high <= 0x5A:
                prefix = chr(high)
                return f"{prefix}{low:02X}"
            # 否则显示为 VXXYY
            return f"V{high:02X}{low:02X}"
        return data.hex().upper()

    if fmt == "compile_time":
        try:
            s = data.decode("ascii", errors="replace").strip()
            return s
        except Exception:
            return data.hex().upper()

    if fmt == "hex":
        return data.hex().upper()

    if fmt == "u8":
        return str(data[0]) if data else "0"

    if fmt == "u16":
        if len(data) >= 2:
            return str(data[0] | (data[1] << 8))
        return str(data[0]) if data else "0"

    if fmt == "u32":
        if len(data) >= 4:
            return str(data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24))
        return str(sum((data[i] << (8 * i)) for i in range(len(data)))) if data else "0"

    if fmt == "sw_info_group":
        return _fmt_sw_info_group(data)

    if fmt == "hw_info_group":
        return _fmt_hw_info_group(data)

    if fmt == "ntb_info":
        return _fmt_ntb_info(data)

    if fmt == "zero_cross_info":
        return _fmt_zero_cross_info(data)

    if fmt == "module_type":
        return MODULE_TYPE_MAP.get(data[0], f"未知({data[0]})") if data else "未知"

    if fmt == "chip_type":
        return CHIP_TYPE_MAP.get(data[0], f"未知({data[0]})") if data else "未知"

    if fmt == "bin":
        return data.hex().upper()

    return data.hex().upper()


def _entry_display_name(category_id: int, data_id: int) -> str:
    """条目显示名：已知条目用字典名，未知条目用 分类x/数据y"""
    entry_def = LME_INFO_ENTRIES.get(category_id, {}).get(data_id)
    if entry_def:
        cat = CATEGORY_NAMES.get(category_id)
        return f"[{cat}] {entry_def[0]}" if cat else entry_def[0]
    cat = CATEGORY_NAMES.get(category_id, f"分类{category_id}")
    return f"[{cat}] 数据{data_id}"


def _entry_raw_name(category_id: int, data_id: int) -> str:
    """条目简短名（兼容旧格式输出）"""
    entry_def = LME_INFO_ENTRIES.get(category_id, {}).get(data_id)
    return entry_def[0] if entry_def else f"分类{category_id}数据{data_id}"


def _extract_ascii_runs(data: bytes, min_len: int = 4) -> List[Tuple[int, int, str]]:
    """提取连续可打印ASCII片段，返回 [(起始偏移, 结束偏移, 字符串)]，按长度降序"""
    runs = []
    start = None
    for i, b in enumerate(data):
        if 0x20 <= b < 0x7F:
            if start is None:
                start = i
        else:
            if start is not None and i - start >= min_len:
                runs.append((start, i, data[start:i].decode("ascii")))
            start = None
    if start is not None and len(data) - start >= min_len:
        runs.append((start, len(data), data[start:].decode("ascii")))
    runs.sort(key=lambda r: -(r[1] - r[0]))
    return runs


def _format_by_encoding(entry_data: bytes, encoding: int) -> str:
    """未知条目按头部编码格式解码：1=ASCII 2=BIN 3=BCD

    BIN 数据（常见于厂商扩展分类6/7）会进一步挖掘内嵌 ASCII 串与整数值。
    """
    if encoding == 1:
        try:
            s = entry_data.decode("ascii", errors="replace").rstrip("\x00")
            if s and all(0x20 <= ord(c) < 0x7F or c in "\r\n\t" for c in s):
                return s
        except Exception:
            pass
        return entry_data.hex().upper()
    if encoding == 3:
        return "".join(f"{b:02X}" for b in entry_data)

    # BIN：挖掘内嵌 ASCII（型号/版本字符串）
    runs = _extract_ascii_runs(entry_data)
    if runs:
        s_off, e_off, text = runs[0]
        prefix = entry_data[:s_off]
        suffix = entry_data[e_off:]
        parts = []
        if prefix.strip(b"\x00"):
            parts.append(f"二进制{prefix.hex().upper()}")
        parts.append(f'ASCII"{text}"')
        if suffix.strip(b"\x00"):
            parts.append(f"尾部{suffix.hex().upper()}")
        return " + ".join(parts)

    # 纯二进制短数据：附小端/大端数值
    if 1 <= len(entry_data) <= 8:
        le = int.from_bytes(entry_data, "little")
        be = int.from_bytes(entry_data, "big")
        if le == be and len(entry_data) == 1:
            return f"{entry_data.hex().upper()}（数值 {le}）"
        return f"{entry_data.hex().upper()}（小端 {le} / 大端 {be}）"
    return entry_data.hex().upper()


def _format_semantic(category_id: int, data_id: int, entry_data: bytes) -> Optional[str]:
    """已知条目的语义增强展开；返回None表示无特殊语义，走通用格式化"""
    # 本地接口默认信息 / 本地串口当前通信参数：B0波特率 B1校验位
    if (category_id == 0 and data_id == 15) or (category_id == 5 and data_id == 2):
        if len(entry_data) >= 2:
            baud = BAUD_MAP.get(entry_data[0], f"未知({entry_data[0]})")
            parity = PARITY_MAP.get(entry_data[1], f"未知({entry_data[1]})")
            return f"波特率 {baud} bps；{parity}"
        return None
    # 模块功能开关：8字节，每1位一个开关（手册仅定义b0~b3）
    if category_id == 0 and data_id == 9:
        flags = int.from_bytes(entry_data[:8], "little") if entry_data else 0
        parts = []
        for bit, label in FUNC_SWITCH_BITS.items():
            parts.append(f"{label}:{'打开' if flags & (1 << bit) else '关闭'}")
        return "；".join(parts)
    # 应用省份
    if category_id == 0 and data_id == 7 and entry_data:
        return PROVINCE_MAP.get(entry_data[0], f"备用({entry_data[0]})")
    # 应用方案：1=双模，其他=单模
    if category_id == 0 and data_id == 8 and entry_data:
        v = entry_data[0]
        return f"{v}（{'双模' if v == 1 else '单模/其他'}）"
    # 默认HPLC频段
    if category_id == 0 and data_id == 16 and entry_data:
        return BAND_MAP.get(entry_data[0], f"备用({entry_data[0]})")
    # 继电器控制及反馈：B0 bit0控制(0合1断)，B1 bit0反馈(0通路1断路)
    if category_id == 0 and data_id == 30 and len(entry_data) >= 2:
        ctrl = "断开" if entry_data[0] & 1 else "闭合"
        fb = "断路" if entry_data[1] & 1 else "通路"
        return f"控制:{ctrl}；反馈检测:{fb}"
    # 组网完成标识
    if category_id == 5 and data_id == 6 and entry_data:
        return NETWORK_DONE_MAP.get(entry_data[0], f"备用({entry_data[0]})")
    return None


def _decode_sw_info_group(b: bytes) -> List[Tuple[str, bytes, str]]:
    """软件信息组（3B，OTP）：B0应用省份 B1应用方案 B2模块类型 → 子字段列表"""
    if len(b) < 3:
        return []
    prov = PROVINCE_MAP.get(b[0], f"备用({b[0]})")
    scheme = "双模" if b[1] == 1 else f"单模/其他({b[1]})"
    mtype = MODULE_TYPE_MAP.get(b[2], f"未知({b[2]})")
    return [
        ("应用省份", b[0:1], f"{b[0]}（{prov}）"),
        ("应用方案", b[1:2], f"{b[1]}（{scheme}）"),
        ("模块类型", b[2:3], f"{b[2]}（{mtype}）"),
    ]


def _decode_hw_info_group(b: bytes) -> List[Tuple[str, bytes, str]]:
    """硬件信息组（31B，OTP）→ 子字段列表"""
    if len(b) < 11:
        return []
    chip = CHIP_TYPE_MAP.get(b[0], f"未知({b[0]})")
    subs = [
        ("芯片型号", b[0:1], f"{b[0]}（{chip}）"),
        ("Flash型号及容量", b[1:5], b[1:5].hex().upper()),
        ("电容容量", b[5:6], str(b[5])),
        ("过零电路类型", b[6:7], str(b[6])),
        ("天线类型", b[7:8], str(b[7])),
        ("载波PA功放型号", b[8:9], str(b[8])),
        ("特征电流拓扑类型", b[9:10], str(b[9])),
        ("无线射频开关类型", b[10:11], str(b[10])),
    ]
    code = b[11:31].decode("ascii", errors="replace").rstrip("\x00 ").strip()
    if code:
        subs.append(("硬件编码", b[11:31], f'"{code}"'))
    return subs


def _decode_ntb_info(b: bytes) -> List[Tuple[str, bytes, str]]:
    """NTB采样信息（12B）→ 子字段列表"""
    if len(b) < 12:
        return []
    direction = "加快本地时间计数" if b[2] == 1 else ("减慢本地时间计数" if b[2] == 0 else f"未知({b[2]})")
    return [
        ("采样偏差补偿", b[0:2], str(int.from_bytes(b[0:2], "little"))),
        ("本地误差补偿方向", b[2:3], f"{b[2]}（{direction}）"),
        ("保留", b[3:4], f"0x{b[3]:02X}"),
        ("评估计数偏差", b[4:8], str(int.from_bytes(b[4:8], "little"))),
        ("本地时钟计数修正", b[8:12], str(int.from_bytes(b[8:12], "little"))),
    ]


def _decode_zero_cross_info(b: bytes) -> List[Tuple[str, bytes, str]]:
    """过零检测信息 → 子字段列表（标志位 + N对频率/占空比，长度自适应13B/25B）"""
    if len(b) < 1:
        return []
    flag = b[0]
    phases = ["A", "B", "C"]
    flag_parts = []
    for e, edge in enumerate(["下降沿", "上升沿"]):
        for p in range(3):
            if flag & (1 << (e * 3 + p)):
                flag_parts.append(f"{phases[p]}相{edge}有过零")
    subs = [("过零标志", b[0:1],
             "0x%02X（%s）" % (flag, "，".join(flag_parts) if flag_parts else "无过零"))]
    pair_count = min((len(b) - 1) // 4, 6)
    idx = 1
    for i in range(pair_count):
        edge = "下降沿" if i < 3 else "上升沿"
        ph = phases[i % 3]
        freq = int.from_bytes(b[idx:idx + 2], "little")
        duty = int.from_bytes(b[idx + 2:idx + 4], "little")
        subs.append((f"{ph}相({edge})过零检测频率", b[idx:idx + 2], f"{freq * 0.01:.2f} Hz"))
        subs.append((f"{ph}相({edge})过零检测占空比", b[idx + 2:idx + 4], f"{duty * 0.1:.2f} %"))
        idx += 4
    if pair_count < 6:
        subs.append(("注", b"", "仅下降沿数据，上升沿为CCO扩展项"))
    return subs


# 结构化组解码 fmt → 子字段解码函数（TLV 循环中竖排展开）
GROUP_DECODERS = {
    "sw_info_group": _decode_sw_info_group,
    "hw_info_group": _decode_hw_info_group,
    "ntb_info": _decode_ntb_info,
    "zero_cross_info": _decode_zero_cross_info,
}


def _fmt_sw_info_group(b: bytes) -> str:
    return "；".join(f"{label}:{val}" for label, _raw, val in _decode_sw_info_group(b)) or b.hex().upper()


def _fmt_hw_info_group(b: bytes) -> str:
    return "；".join(f"{label}:{val}" for label, _raw, val in _decode_hw_info_group(b)) or b.hex().upper()


def _fmt_ntb_info(b: bytes) -> str:
    return "；".join(f"{label}:{val}" for label, _raw, val in _decode_ntb_info(b)) or b.hex().upper()


def _fmt_zero_cross_info(b: bytes) -> str:
    subs = _decode_zero_cross_info(b)
    return "；".join(f"{label} {val}" if label == "注" else f"{label}:{val}"
                    for label, _raw, val in subs) or b.hex().upper()


def _parse_dual_tlv_rows(data: bytes, with_value: bool, include_info_byte: bool = True
                         ) -> List[Tuple[str, str, str]]:
    """解析4.6应答/4.7设置请求的 TLV 数据体（DI之后）

    结构：[条目信息 1B(填0)] + M 1B + M×(2B头 + L字节数据)
    头部16位（小端）：数据ID b0~5 | 分类ID b6~8 | 编码格式 b9~10 | 长度L b11~15

    with_value=True 时解析数据值（4.6应答/4.7请求）；False 时仅头部（4.7结果应答不用本函数）。
    返回 (名称, 值, 说明) 三元组列表。
    """
    # 行格式：(字段, 原始值hex, 解析值, 说明)
    rows: List[Tuple[str, str, str, str]] = []
    if len(data) < 5:
        return rows

    # 兼容“有条目信息字节”和“无条目信息字节”两种组包：data[4]==0且data[5]>0 视为条目信息字节
    if include_info_byte and len(data) >= 6 and data[4] == 0 and data[5] > 0:
        info_byte = data[4]
        m = data[5]
        idx = 6
        if info_byte != 0:
            rows.append(("  └ ⚠ 条目信息字节", f"{info_byte:02X}", f"0x{info_byte:02X}", "手册规定填0"))
    else:
        m = data[4]
        idx = 5

    if m == 0:
        rows.append(("  └ 条目数 M", f"{m:02X}", "0", "读取模块所支持的全部信息条目"))
        return rows

    rows.append(("  └ 条目数 M", f"{m:02X}", str(m), f"共 {m} 个信息条目"))

    entry_count = 0
    while idx + 2 <= len(data) and entry_count < m:
        header_raw = data[idx:idx + 2]
        header = data[idx] | (data[idx + 1] << 8)
        idx += 2
        data_id = header & 0x3F
        category_id = (header >> 6) & 0x07
        encoding = (header >> 9) & 0x03
        length = (header >> 11) & 0x1F

        name = _entry_display_name(category_id, data_id)
        enc_name = ENCODING_NAMES.get(encoding, f"未知编码({encoding})")
        known = data_id in LME_INFO_ENTRIES.get(category_id, {})
        vendor_note = ("，厂商扩展分类手册未定义语义"
                       if category_id >= 6 and not known else "")
        desc = f"分类{category_id}/数据{data_id}，{enc_name}，{length}字节{vendor_note}"
        row_name = f"  └ 条目{entry_count + 1} {name}"

        if not with_value:
            rows.append((row_name, header_raw.hex().upper(),
                         f"分类{category_id}/数据{data_id}", desc))
            entry_count += 1
            continue

        if length == 0:
            rows.append((row_name, "", "（空）", desc))
            entry_count += 1
            continue

        if idx + length > len(data):
            remain = data[idx:]
            rows.append((row_name, remain.hex().upper(), "⚠ 数据不完整",
                         desc + f" ⚠ 数据不完整（期望{length}字节，剩余{len(remain)}字节）"))
            break

        entry_data = data[idx:idx + length]
        idx += length

        semantic = _format_semantic(category_id, data_id, entry_data)
        if semantic is not None:
            rows.append((row_name, entry_data.hex().upper(), semantic, desc))
        else:
            entry_def = LME_INFO_ENTRIES.get(category_id, {}).get(data_id)
            fmt = entry_def[3] if entry_def else None
            if fmt in GROUP_DECODERS:
                # 结构化组：父行 + 每个子字段一行（竖排）
                subs = GROUP_DECODERS[fmt](entry_data)
                rows.append((row_name, entry_data.hex().upper(),
                             f"展开 {len(subs)} 个子字段", desc))
                for sub_label, sub_raw, sub_val in subs:
                    rows.append((f"    └ {sub_label}",
                                 sub_raw.hex().upper(), sub_val, f"{sub_label}（{fmt}）"))
            elif entry_def:
                value = _format_value(entry_data, fmt or "hex")
                rows.append((row_name, entry_data.hex().upper(), value, desc))
            else:
                value = _format_by_encoding(entry_data, encoding)
                rows.append((row_name, entry_data.hex().upper(), value, desc))
        entry_count += 1

    if entry_count < m:
        rows.append(("  └ ⚠ 条目截断", "", f"已解析{entry_count}/{m}", "数据域长度不足"))
    return rows


def parse_lme_info_entries(data: bytes) -> List[Tuple[str, str]]:
    """解析LME双模STA信息条目响应数据域（archive_widget 兼容接口）

    参数:
        data: DLT645解析后的数据域（已减0x33），包含DI本身

    返回:
        列表，每项为 (条目名称, 格式化值)
    """
    results = []
    for name, _raw, value, _desc in _parse_dual_tlv_rows(data, with_value=True):
        m = re.match(r"^\s*└\s*条目\d+\s*(.*)$", name)
        if not m:
            # 非条目行（条目数M/截断提示）不进入旧接口
            continue
        short = m.group(1)
        if "]" in short:
            short = short.split("]", 1)[1].strip()
        results.append((short, value))
    return results


def parse_dual_entry_query_request(data: bytes) -> List[Tuple[str, str, str, str]]:
    """4.6 下行查询请求：[条目信息 1B=0] + M 1B + M×2B 请求头（数据ID6/分类ID3/保留7）"""
    rows: List[Tuple[str, str, str, str]] = []
    if len(data) < 5:
        return rows
    if len(data) >= 6 and data[4] == 0 and data[5] > 0:
        m = data[5]
        idx = 6
    else:
        m = data[4]
        idx = 5

    if m == 0:
        rows.append(("  └ 条目数 M", f"{m:02X}", "0", "读取模块所支持的全部信息条目"))
        return rows

    rows.append(("  └ 条目数 M", f"{m:02X}", str(m), f"请求 {m} 个指定信息条目"))
    for i in range(m):
        if idx + 2 > len(data):
            rows.append(("  └ ⚠ 请求条目截断", "", f"已解析{i}/{m}", "数据域长度不足"))
            break
        raw = data[idx:idx + 2]
        header = data[idx] | (data[idx + 1] << 8)
        idx += 2
        data_id = header & 0x3F
        category_id = (header >> 6) & 0x07
        reserved = (header >> 9) & 0x7F
        name = _entry_display_name(category_id, data_id)
        resv_note = "" if reserved == 0 else f" ⚠ 保留位=0x{reserved:02X}（应填0）"
        rows.append((f"  └ 请求条目{i + 1} {name}",
                     raw.hex().upper(),
                     f"分类{category_id}/数据{data_id}",
                     f"数据ID={data_id}(6bit)，分类ID={category_id}(3bit){resv_note}"))
    return rows


def parse_dual_entry_response(data: bytes) -> List[Tuple[str, str, str]]:
    """4.6 上行应答：条目信息 + M + TLV条目"""
    return _parse_dual_tlv_rows(data, with_value=True)


def parse_dual_entry_set_request(data: bytes) -> List[Tuple[str, str, str]]:
    """4.7 下行设置请求：条目信息 + M + TLV条目（头 + 设置数据）"""
    return _parse_dual_tlv_rows(data, with_value=True)


def parse_dual_entry_set_response(data: bytes) -> List[Tuple[str, str, str, str]]:
    """4.7 上行设置应答：[条目信息?] + M + M×2B结果头（数据ID6/分类ID3/设置结果7bit）"""
    rows: List[Tuple[str, str, str, str]] = []
    if len(data) < 5:
        return rows

    # 手册表格此处有歧义（"条目信息条目数M"），按长度自适应：5+2M 或 6+2M
    if 5 + 2 * data[4] == len(data):
        m = data[4]
        idx = 5
    elif len(data) >= 6 and 6 + 2 * data[5] == len(data):
        m = data[5]
        idx = 6
    else:
        # 回退：有条目信息字节则从6开始
        if len(data) >= 6 and data[4] == 0:
            m = data[5]
            idx = 6
        else:
            m = data[4]
            idx = 5

    rows.append(("  └ 条目数 M", f"{m:02X}", str(m), f"共 {m} 个设置结果"))
    for i in range(m):
        if idx + 2 > len(data):
            rows.append(("  └ ⚠ 结果截断", "", f"已解析{i}/{m}", "数据域长度不足"))
            break
        raw = data[idx:idx + 2]
        header = data[idx] | (data[idx + 1] << 8)
        idx += 2
        data_id = header & 0x3F
        category_id = (header >> 6) & 0x07
        result = (header >> 9) & 0x7F
        name = _entry_display_name(category_id, data_id)
        result_text = SET_RESULT_MAP.get(result, f"保留({result})")
        mark = "✓" if result == 0 else "✗"
        rows.append((f"  └ 结果{i + 1} {name}",
                     raw.hex().upper(),
                     f"{mark} {result_text}",
                     f"分类{category_id}/数据{data_id}，结果码={result}"))
    return rows


def parse_sta_version_single(data: bytes) -> List[Tuple[str, str, str, str]]:
    """4.2 单模STA软件详细版本信息数据单元（DI之后251字节固定布局）

    字段顺序严格按手册4.2表；硬件信息段为变长（1B长度 + ASCII + CRC16 + Flash容量）。
    行格式：(字段, 原始值hex, 解析值, 说明)
    """
    rows: List[Tuple[str, str, str, str]] = []
    incomplete = [False]

    def take(off: int, n: int):
        avail = len(data) - off
        if avail < n:
            incomplete[0] = True
            return data[off:off + max(avail, 0)]
        return data[off:off + n]

    def add(name: str, raw: bytes, parsed: str, desc: str):
        rows.append((name, raw.hex().upper() if raw else "", parsed, desc))

    def ascii_rev(b: bytes) -> str:
        try:
            return b[::-1].decode("ascii", errors="replace").strip()
        except Exception:
            return b.hex().upper()

    def ascii_str(b: bytes) -> str:
        try:
            return b.decode("ascii", errors="replace").strip()
        except Exception:
            return b.hex().upper()

    # DI占前4字节，字段从偏移4开始
    off = 4
    phases = ["A", "B", "C"]

    b = take(off, 2); off += 2
    add("  └ 外部厂商代码", b, ascii_rev(b), "ASCII 2字节，逆序传输")
    b = take(off, 2); off += 2
    add("  └ 外部芯片代码", b, ascii_rev(b), "ASCII 2字节，逆序传输")
    b = take(off, 2); off += 2
    if len(b) == 2:
        add("  └ 外部版本号", b, f"V{b[1]:02X}{b[0]:02X}", "BIN 2字节，逆序（传输YY XX）")
    b = take(off, 3); off += 3
    if len(b) == 3:
        add("  └ 外部版本日期", b, f"20{b[2]:02X}-{b[1]:02X}-{b[0]:02X}",
            "BCD 3字节，日月年（DD MM YY）")
    b = take(off, 2); off += 2
    if len(b) == 2:
        add("  └ MCU内部版本号", b, f"v{b[1]:02X}{b[0]:02X}",
            "BCD 2字节，1字节次版本+1字节主版本")
    b = take(off, 1); off += 1
    app_major = ascii_str(b) if b else ""
    b = take(off, 2); off += 2
    if len(b) == 2:
        add("  └ 应用层(APS)版本号", b, f"{app_major}{b[1]:02X}{b[0]:02X}",
            "1字节层级标志(固定A) + BCD 2字节（平台/网省/小版本，见手册4.2注2）")
    b = take(off, 1); off += 1
    nwk_flag = ascii_str(b) if b else ""
    b = take(off, 2); off += 2
    if len(b) == 2:
        add("  └ 网络层(NWK)版本号", b, f"{nwk_flag}{b[1]:02X}{b[0]:02X}",
            f"层级标志应为N（实际'{nwk_flag}'）+ BCD 2字节")
    b = take(off, 1); off += 1
    phy_flag = ascii_str(b) if b else ""
    b = take(off, 2); off += 2
    if len(b) == 2:
        add("  └ 物理层(PHY)版本号", b, f"{phy_flag}{b[1]:02X}{b[0]:02X}",
            f"层级标志应为P（实际'{phy_flag}'）+ BCD 2字节")
    b = take(off, 2); off += 2
    if len(b) == 2:
        add("  └ DSP版本号", b, f"V{b[1]:02X}{b[0]:02X}", "BIN 2字节，内部信息")
    b = take(off, 1); off += 1
    if b:
        zc = []
        for p in range(3):
            if b[0] & (1 << p):
                zc.append(f"{phases[p]}相有过零")
        add("  └ 过零标志", b,
            f"0x{b[0]:02X}（{'，'.join(zc) if zc else '无过零'}）",
            "bit0~2=1 分别表示A/B/C相有过零")
    b = take(off, 19); off += 19
    add("  └ 编译时间", b, ascii_str(b).replace("\r", " "), "ASCII 19字节，MCU编译时间")

    for ph in phases:
        b = take(off, 2); off += 2
        if len(b) == 2:
            freq = int.from_bytes(b, "little")
            add(f"  └ {ph}相过零检测频率", b, f"{freq * 0.01:.2f} Hz", "BIN 2字节，单位0.01Hz")
        b = take(off, 2); off += 2
        if len(b) == 2:
            duty = int.from_bytes(b, "little")
            add(f"  └ {ph}相过零检测占空比", b, f"{duty * 0.1:.1f} %", "BIN 2字节，单位0.1%")

    # 硬件信息段：1B长度 + N字节ASCII（正序） + 2B CRC16 + 1B Flash容量
    b = take(off, 1); off += 1
    if b:
        hw_len = b[0]
        add("  └ 硬件信息长度", b, f"{hw_len} 字节", "硬件型号字符数，最大61")
        hb = take(off, hw_len); off += hw_len
        add("  └ 硬件信息", hb, ascii_str(hb).rstrip("\x00"), "ASCII，正序传输，PCB型号")
        b = take(off, 2); off += 2
        add("  └ 硬件信息校验", b, b.hex().upper(),
            "CRC-16校验值（手册未定义多项式，仅展示不验算）")
        b = take(off, 1); off += 1
        if b:
            n = b[0]
            if n == 0xFF:
                cap = "未知容量"
            else:
                cap = f"2^{n + 1} = {1 << (n + 1)}（容量编码n={n}）"
            add("  └ Flash容量", b, cap, "n对应实际容量2^(n+1)，255=未知")

    if incomplete[0]:
        rows.append(("  └ ⚠ 数据不完整", "",
                     f"数据域共{len(data) - 4}字节（完整应为251字节）",
                     "后续字段缺失，解析结果截至此处"))
    return rows


def parse_lme_dlt645(di_code: str, ctrl: int, data: bytes
                     ) -> Tuple[Optional[List[Tuple[str, str, str, str]]], str]:
    """DLT645 LME自定义接口总入口

    参数:
        di_code: 8位HEX DI编码（小端解析后的手册写法，如 FF00DD01）
        ctrl: 控制码字节（D7=DIR方向，D0~D4=功能码）
        data: 减0x33后的完整数据域（含4字节DI）

    返回:
        (fields行列表, 接口中文名)；行格式 (字段, 原始值hex, 解析值, 说明)；
        非LME自定义DI返回 (None, "")
    """
    dir_bit = (ctrl >> 7) & 0x1
    func = ctrl & 0x1F

    if di_code == DI_STA_VERSION_SINGLE:
        if dir_bit == 1 and func == 0x11:
            return parse_sta_version_single(data), "HPLC单模STA详细信息应答（LME自定义 4.2）"
        if dir_bit == 0 and func == 0x11:
            return [("  └ 数据单元", "", "无",
                     "读请求无数据单元，应答为251字节软件详细版本信息（手册4.2）")], \
                   "HPLC单模STA详细信息查询请求（LME自定义 4.2）"

    if di_code == DI_DUAL_ENTRY:
        if dir_bit == 0 and func == 0x11:
            return parse_dual_entry_query_request(data), \
                   "HPLC双模STA内部详细信息查询请求（LME自定义 4.6）"
        if dir_bit == 1 and func == 0x11:
            return parse_dual_entry_response(data), \
                   "HPLC双模STA内部详细信息应答（LME自定义 4.6）"
        if dir_bit == 0 and func == 0x14:
            return parse_dual_entry_set_request(data), \
                   "HPLC双模STA详细信息设置请求（LME自定义 4.7）"
        if dir_bit == 1 and func == 0x14:
            return parse_dual_entry_set_response(data), \
                   "HPLC双模STA详细信息设置应答（LME自定义 4.7）"

    return None, ""


def format_lme_info_summary(results: List[Tuple[str, str]], max_len: int = 120) -> str:
    """将解析结果格式化为适合表格显示的摘要字符串

    优先显示关键信息：厂商代码、芯片代码、版本、编译时间
    """
    if not results:
        return "无数据"

    # 定义优先级和简短显示名称
    priority_keys = {
        "外部厂商代码": "厂商",
        "外部芯片代码": "芯片",
        "外部版本号": "版本",
        "外部版本日期": "日期",
        "编译时间": "编译",
        "网络层版本": "NWK",
        "APS层版本": "APS",
        "APP层版本": "APP",
        "PHY层版本": "PHY",
        "载波MAC层版本": "MAC",
        "芯片程序版本": "DSP",
        "硬件型号": "硬件",
        "芯片型号": "芯片型号",
    }

    parts = []
    for name, value in results:
        short_name = priority_keys.get(name)
        if short_name and value and value != "空" and value != "未写入":
            # 截断过长的值
            display_val = value if len(value) <= 20 else value[:18] + "..."
            parts.append(f"{short_name}:{display_val}")

    if not parts:
        # 如果没有匹配到优先级字段，显示前3个条目
        for name, value in results[:3]:
            display_val = value if len(value) <= 20 else value[:18] + "..."
            parts.append(f"{name}:{display_val}")

    result = " ".join(parts)
    if len(result) > max_len:
        result = result[:max_len - 3] + "..."
    return result if result else "已解析"
