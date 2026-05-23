"""LME HPLC双模模块信息条目解析器

基于《LME产品相关信息生产运维接口手册》附录C和附录E实现。
解析DI=0xFF00DD01（双模STA内部详细信息查询）的响应数据域。
"""

from typing import Dict, List, Tuple, Optional


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
        2: ("程序总版本", 2, "2", "bin_ver"),
        3: ("总工程版本", 2, "2", "bin_ver"),
        4: ("boot版本", 2, "2", "bin_ver"),
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
        20: ("过零检测信息", 2, "13", "bin"),
        21: ("NTB采样信息", 2, "12", "bin"),
        22: ("载波接收信息", 2, "2", "bin"),
        23: ("无线接收信息", 2, "2", "bin"),
        24: ("USB频偏信息", 2, "6", "bin"),
        25: ("无线校准信息", 2, "3", "bin"),
        26: ("温度校准信息", 2, "4", "bin"),
    },
    3: {  # 网络信息
        1: ("节点网络信息", 2, "27", "bin"),
        2: ("软件信息组", 2, "3", "bin"),
        3: ("硬件信息组", 2, "31", "bin"),
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

    if fmt == "module_type":
        return MODULE_TYPE_MAP.get(data[0], f"未知({data[0]})") if data else "未知"

    if fmt == "chip_type":
        return CHIP_TYPE_MAP.get(data[0], f"未知({data[0]})") if data else "未知"

    if fmt == "bin":
        return data.hex().upper()

    return data.hex().upper()


def parse_lme_info_entries(data: bytes) -> List[Tuple[str, str]]:
    """解析LME双模STA信息条目响应数据域

    参数:
        data: DLT645解析后的数据域（已减0x33），包含DI本身

    返回:
        列表，每项为 (条目名称, 格式化值)
    """
    results: List[Tuple[str, str]] = []
    if len(data) < 5:
        return results

    # DLT645数据域前4字节为DI（小端），第5字节为M（条目数）
    idx = 4
    m = data[idx]
    idx += 1

    # 如果M=0，表示读取模块支持的所有信息
    if m == 0:
        pass

    entry_count = 0
    while idx + 2 <= len(data) and entry_count < (m if m > 0 else 255):
        # 读取2字节头部（小端）
        header_lo = data[idx]
        header_hi = data[idx + 1]
        header = header_lo | (header_hi << 8)

        data_id = header & 0x3F
        category_id = (header >> 6) & 0x07
        encoding = (header >> 9) & 0x03
        length = (header >> 11) & 0x1F

        idx += 2

        if length == 0:
            entry_count += 1
            continue

        if idx + length > len(data):
            break

        entry_data = data[idx:idx + length]
        idx += length

        # 查找条目定义
        entry_def = LME_INFO_ENTRIES.get(category_id, {}).get(data_id)
        if entry_def:
            name = entry_def[0]
            fmt = entry_def[3] or "hex"
        else:
            # 未定义条目，使用头部中的编码和长度显示原始数据
            name = f"分类{category_id}数据{data_id}"
            fmt = "hex"

        value = _format_value(entry_data, fmt)
        results.append((name, value))
        entry_count += 1

    return results


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
