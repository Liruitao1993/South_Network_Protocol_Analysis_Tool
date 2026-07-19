# -*- coding: utf-8 -*-
"""
国网新一代双模通信互联互通 应用层命令帧业务数据单元解析
依据《双模通信互联互通技术规范 第4-3部分：应用层通信协议》

报文ID含义依赖方向(上行/下行):
  - 同一报文ID，上行和下行可能有不同业务含义
  - 例如 0x0011: 下行=查询从节点主动注册, 上行=从节点注册结果上报
"""
from typing import List, Tuple, Optional


def _hex(data: bytes) -> str:
    return ' '.join(f'{b:02X}' for b in data)


def _uint16_le(data: bytes, offset: int) -> int:
    if offset + 2 > len(data):
        return 0
    return int.from_bytes(data[offset:offset + 2], 'little')


def _uint32_le(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        return 0
    return int.from_bytes(data[offset:offset + 4], 'little')


def _bcd_time(data: bytes, offset: int) -> Tuple[str, str]:
    """解析 BCD 时间（秒在低位）"""
    if offset + 6 > len(data):
        return "", ""
    raw_bytes = data[offset:offset + 6]
    raw = _hex(raw_bytes)
    dt = raw_bytes[::-1]
    bcd = ''.join(f'{b:02X}' for b in dt)
    if len(bcd) == 12 and all(c in '0123456789' for c in bcd):
        parsed = f"20{bcd[0:2]}-{bcd[2:4]}-{bcd[4:6]} {bcd[6:8]}:{bcd[8:10]}:{bcd[10:12]}"
    else:
        parsed = f"非标准BCD: {raw}"
    return raw, parsed


def _mac_addr(data: bytes, offset: int) -> Tuple[str, str]:
    """解析 6 字节 MAC 地址"""
    if offset + 6 > len(data):
        return "", ""
    addr = data[offset:offset + 6]
    raw = _hex(addr)
    colon = ':'.join(f'{b:02X}' for b in addr)
    return raw, colon


def _meter_addr(data: bytes, offset: int) -> Tuple[str, str]:
    """解析 6 字节电能表表号地址（低字节在前，显示时逆序）"""
    if offset + 6 > len(data):
        return "", ""
    addr = data[offset:offset + 6]
    raw = _hex(addr)
    colon = ':'.join(f'{b:02X}' for b in reversed(addr))
    return raw, colon


# ── 通用工具：追加字段 ──
def _f(table: list, name: str, raw: str, parsed: str, desc: str, start: int, end: int):
    table.append((name, raw, parsed, desc, start, end))


def _remaining(table: list, data: bytes, offset: int, base_offset: int):
    if offset < len(data):
        rem = data[offset:]
        _f(table, "剩余数据", _hex(rem)[:80], f"{len(rem)}字节", "未解析数据",
           base_offset + offset, base_offset + len(data) - 1)


# ── 协议常量 ──
_PROTOCOL_TYPE_MAP = {
    0x00: "透明传输",
    0x01: "DL/T 645-1997",
    0x02: "DL/T 645-2007",
    0x03: "DL/T 698.45",
}

_DEVICE_TYPE_MAP = {
    1: "抄控器",
    2: "终端本地通信单元",
    3: "单相电表通信单元",
    4: "中继器",
    5: "II型采集器",
    6: "I型采集器单元",
    7: "三相电表通信单元",
}

_UPGRADE_STATUS_MAP = {
    0: "空闲态",
    1: "接收进行态",
    2: "接收完成态",
    3: "升级进行态",
    4: "试运行态",
}

_SITE_INFO_ELEM_MAP = {
    0x00: "厂商编号(2B ASCII)",
    0x01: "版本信息(2B BCD)",
    0x02: "Bootloader(1B BIN)",
    0x03: "CRC-32(4B)",
    0x04: "文件长度(4B)",
    0x05: "产品类型",
}


# ═══════════════════════════════════════════════════════════
# 公共报文头解析（按协议文档精确实现）
# ═══════════════════════════════════════════════════════════

def _parse_header_meter_down(payload: bytes, base_offset: int) -> Tuple[int, list]:
    """抄表下行报文头(表3): 8字节
    字节0: 协议版本(6b) + 报文头长度高2位(2b)
    字节1: 报文头长度低4位(4b) + 未应答重试(1b) + 否认重试(1b) + 最大重试次数(2b)
    字节2: 规约类型(4b) + 转发数据长度高4位(4b)
    字节3: 转发数据长度低8位(8b)
    字节4-5: 报文序号(16b)
    字节6: 设备超时时间(8b)
    字节7: 选项字(8b)
    """
    table = []
    if len(payload) < 8:
        return 0, table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    retry_no_resp = (b1 >> 4) & 0x01
    retry_deny = (b1 >> 5) & 0x01
    max_retry = (b1 >> 6) & 0x03
    b2 = payload[2]
    proto_type = b2 & 0x0F
    data_len_high = (b2 >> 4) & 0x0F
    b3 = payload[3]
    data_len = (data_len_high << 8) | b3
    seq = _uint16_le(payload, 4)
    timeout = payload[6]
    option = payload[7]

    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "固定为8", base_offset, base_offset + 1)
    _f(table, "未应答重试标志", f"{retry_no_resp}", "重试" if retry_no_resp else "不重试",
       "仅并发抄表有效", base_offset + 1, base_offset + 1)
    _f(table, "否认重试标志", f"{retry_deny}", "重试" if retry_deny else "不重试",
       "仅并发抄表有效", base_offset + 1, base_offset + 1)
    _f(table, "最大重试次数", f"{max_retry}", str(max_retry), "仅并发抄表有效",
       base_offset + 1, base_offset + 1)
    proto_name = _PROTOCOL_TYPE_MAP.get(proto_type, f"保留({proto_type})")
    _f(table, "规约类型", f"{proto_type}", proto_name, "转发数据的规约类型",
       base_offset + 2, base_offset + 2)
    _f(table, "转发数据长度", f"0x{data_len:03X}", f"{data_len}字节", "实际数据域长度",
       base_offset + 2, base_offset + 3)
    _f(table, "报文序号", f"0x{seq:04X}", str(seq), "STA应答时使用该序号返回",
       base_offset + 4, base_offset + 5)
    _f(table, "设备超时时间", f"0x{timeout:02X}", f"{timeout * 100}ms",
       "STA单位100ms, 采集器单位200ms", base_offset + 6, base_offset + 6)
    # 选项字解析依赖报文类型，由调用者进一步解析
    _f(table, "选项字", f"0x{option:02X}", f"0x{option:02X}",
       "bit0:方向位, bit1-7:报文间间隔(并发抄表)", base_offset + 7, base_offset + 7)
    return 8, table


def _parse_header_meter_up(payload: bytes, base_offset: int) -> Tuple[int, list]:
    """抄表上行报文头(表4): 8字节
    字节0: 协议版本(6b) + 报文头长度高2位(2b)
    字节1: 报文头长度低4位(4b) + 应答状态(4b)
    字节2: 规约类型(4b) + 转发数据长度高4位(4b)
    字节3: 转发数据长度低8位(8b)
    字节4-5: 报文序号(16b)
    字节6-7: 选项字(16b)
    """
    table = []
    if len(payload) < 8:
        return 0, table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    resp_status = (b1 >> 4) & 0x0F
    b2 = payload[2]
    proto_type = b2 & 0x0F
    data_len_high = (b2 >> 4) & 0x0F
    b3 = payload[3]
    data_len = (data_len_high << 8) | b3
    seq = _uint16_le(payload, 4)
    option = _uint16_le(payload, 6)

    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "固定为8", base_offset, base_offset + 1)
    _f(table, "应答状态", f"{resp_status}", "固定为0(成功)" if resp_status == 0 else f"状态={resp_status}",
       "上行固定为0", base_offset + 1, base_offset + 1)
    proto_name = _PROTOCOL_TYPE_MAP.get(proto_type, f"保留({proto_type})")
    _f(table, "规约类型", f"{proto_type}", proto_name, "转发数据的规约类型",
       base_offset + 2, base_offset + 2)
    _f(table, "转发数据长度", f"0x{data_len:03X}", f"{data_len}字节", "抄表结果数据长度",
       base_offset + 2, base_offset + 3)
    _f(table, "报文序号", f"0x{seq:04X}", str(seq), "应与下行报文一致",
       base_offset + 4, base_offset + 5)
    _f(table, "选项字", f"0x{option:04X}", f"0x{option:04X}",
       "并发抄表:bit0-15报文应答状态", base_offset + 6, base_offset + 7)
    return 8, table


def _parse_header_generic(payload: bytes, base_offset: int, direction: int) -> Tuple[int, list]:
    """通用报文头(校时/通信测试/升级等): 4字节
    字节0: 协议版本(6b) + 报文头长度高2位(2b)
    字节1: 报文头长度低4位(4b) + 保留/控制(4b)
    字节2-3: 保留(4b或12b) + 数据长度(12b) 或 保留(16b)
    """
    table = []
    if len(payload) < 4:
        return 0, table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    ctrl = (b1 >> 4) & 0x0F
    b2 = payload[2]
    b3 = payload[3]
    data_len = ((b2 & 0x0F) << 8) | b3
    reserved_high = (b2 >> 4) & 0x0F

    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "报文头(除数据域外)的长度",
       base_offset, base_offset + 1)
    _f(table, "控制/保留", f"0x{ctrl:X}", f"0x{ctrl:X}", "保留或控制字段",
       base_offset + 1, base_offset + 1)
    _f(table, "数据长度", f"0x{data_len:03X}", f"{data_len}字节", "数据域长度",
       base_offset + 2, base_offset + 3)
    return 4, table


# ═══════════════════════════════════════════════════════════
# 0x0001/0x0002/0x0003: 抄表报文
# ═══════════════════════════════════════════════════════════

def _parse_meter_reading_downlink(payload: bytes, base_offset: int) -> list:
    """抄表下行报文(表3)"""
    table = []
    if len(payload) < 8:
        _f(table, "❌ 数据不足", "", "", "下行抄表数据域不足8字节",
           base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset, hdr = _parse_header_meter_down(payload, base_offset)
    table.extend(hdr)
    # 数据域
    if offset < len(payload):
        fwd_data = payload[offset:]
        _f(table, "转发数据(抄表报文)", _hex(fwd_data)[:80], f"{len(fwd_data)}字节",
           "终端下发给STA的抄表报文数据", base_offset + offset, base_offset + len(payload) - 1)
    return table


def _parse_meter_reading_uplink(payload: bytes, base_offset: int) -> list:
    """抄表上行报文(表4)"""
    table = []
    if len(payload) < 8:
        _f(table, "❌ 数据不足", "", "", "上行抄表数据域不足8字节",
           base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset, hdr = _parse_header_meter_up(payload, base_offset)
    table.extend(hdr)
    # 数据域
    if offset < len(payload):
        fwd_data = payload[offset:]
        _f(table, "转发数据(抄表结果)", _hex(fwd_data)[:80], f"{len(fwd_data)}字节",
           "STA应答的抄表结果数据", base_offset + offset, base_offset + len(payload) - 1)
    return table


def _parse_terminal_meter_reading(payload: bytes, direction: int, base_offset: int) -> list:
    """0x0001 终端主动抄表"""
    if direction == 0:
        return _parse_meter_reading_downlink(payload, base_offset)
    return _parse_meter_reading_uplink(payload, base_offset)


def _parse_route_meter_reading(payload: bytes, direction: int, base_offset: int) -> list:
    """0x0002 路由主动抄表"""
    if direction == 0:
        return _parse_meter_reading_downlink(payload, base_offset)
    return _parse_meter_reading_uplink(payload, base_offset)


def _parse_parallel_meter_reading(payload: bytes, direction: int, base_offset: int) -> list:
    """0x0003 终端主动并发抄表"""
    if direction == 0:
        return _parse_meter_reading_downlink(payload, base_offset)
    return _parse_meter_reading_uplink(payload, base_offset)


# ═══════════════════════════════════════════════════════════
# 0x0004: 校时
# ═══════════════════════════════════════════════════════════

def _parse_time_sync(payload: bytes, direction: int, base_offset: int) -> list:
    """校时报文(表9): 通用头(4B) + 报文序号(2B) + 数据"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "校时数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset, hdr = _parse_header_generic(payload, base_offset, direction)
    table.extend(hdr)
    # 报文序号(2字节)
    if offset + 2 <= len(payload):
        seq = _uint16_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:04X}", str(seq), "", base_offset + offset, base_offset + offset + 1)
        offset += 2
    # 校时数据
    if offset < len(payload):
        time_data = payload[offset:]
        time_raw, time_parsed = _bcd_time(time_data, 0)
        if time_parsed and not time_parsed.startswith("非标准"):
            _f(table, "校时数据", time_raw, time_parsed, "BCD时间(秒在低位)",
               base_offset + offset, base_offset + len(payload) - 1)
        else:
            _f(table, "校时数据", _hex(time_data)[:80], f"{len(time_data)}字节", "校时时间数据",
               base_offset + offset, base_offset + len(payload) - 1)
    return table


# ═══════════════════════════════════════════════════════════
# 0x0005: 单相业务下发
# ═══════════════════════════════════════════════════════════

def _parse_single_phase(payload: bytes, direction: int, base_offset: int) -> list:
    """单相业务下发(表50): 通用头(4B) + 报文序号(2B) + 数据"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset, hdr = _parse_header_generic(payload, base_offset, direction)
    table.extend(hdr)
    if offset + 2 <= len(payload):
        seq = _uint16_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:04X}", str(seq), "STA应答时使用该序号",
           base_offset + offset, base_offset + offset + 1)
        offset += 2
    if offset < len(payload):
        data = payload[offset:]
        _f(table, "业务数据", _hex(data)[:80], f"{len(data)}字节", "单相业务下发数据",
           base_offset + offset, base_offset + len(payload) - 1)
    return table


# ═══════════════════════════════════════════════════════════
# 0x0006: 通信测试
# ═══════════════════════════════════════════════════════════

def _parse_comm_test(payload: bytes, direction: int, base_offset: int) -> list:
    """通信测试(表16): 协议版本+头长度+保留(4b)+规约类型(4b)+数据长度(12b)+数据"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    reserved = (b1 >> 4) & 0x0F
    b2 = payload[2]
    proto_type = b2 & 0x0F
    data_len_high = (b2 >> 4) & 0x0F
    b3 = payload[3]
    data_len = (data_len_high << 8) | b3

    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "报文头(除数据域外)的长度",
       base_offset, base_offset + 1)
    _f(table, "保留", f"0x{reserved:X}", "", "保留", base_offset + 1, base_offset + 1)
    proto_name = _PROTOCOL_TYPE_MAP.get(proto_type, f"保留({proto_type})")
    _f(table, "规约类型", f"{proto_type}", proto_name, "转发数据的规约类型",
       base_offset + 2, base_offset + 2)
    _f(table, "转发数据长度", f"0x{data_len:03X}", f"{data_len}字节", "实际数据域长度",
       base_offset + 2, base_offset + 3)
    offset = 4
    if offset < len(payload):
        data = payload[offset:]
        _f(table, "测试数据", _hex(data)[:80], f"{len(data)}字节", "通信测试数据内容",
           base_offset + offset, base_offset + len(payload) - 1)
    return table


# ═══════════════════════════════════════════════════════════
# 0x0008: 事件上报
# ═══════════════════════════════════════════════════════════

_FUNC_CODE_DOWN = {1: "CCO应答确认", 2: "CCO下发允许事件主动上报",
                   3: "CCO下发禁止事件主动上报", 4: "CCO应答事件缓存区满"}
_FUNC_CODE_UP = {1: "STA主动上报(电表触发)", 2: "STA主动上报(模块触发)",
                 3: "STA主动上报(采集器触发)"}


def _parse_event_report(payload: bytes, direction: int, base_offset: int) -> list:
    """事件上报(表10): 协议版本+头长度+方向位+启动位+功能码+数据长度+序号+表地址+数据"""
    table = []
    if len(payload) < 12:
        _f(table, "❌ 数据不足", "", "", "事件数据域不足12字节",
           base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    dir_bit = (b1 >> 4) & 0x01
    start_bit = (b1 >> 5) & 0x01
    func_code = (b1 >> 6) & 0x03
    # 功能码实际是6bit: b1[7:6] + b2[3:0]
    b2 = payload[2]
    func_code_full = (func_code << 4) | (b2 & 0x0F)
    data_len_high = (b2 >> 4) & 0x0F
    b3 = payload[3]
    data_len = (data_len_high << 8) | b3
    seq = _uint16_le(payload, 4)

    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "报文头(除数据域外)的长度",
       base_offset, base_offset + 1)
    _f(table, "方向位", f"{dir_bit}", "上行" if dir_bit else "下行", "",
       base_offset + 1, base_offset + 1)
    _f(table, "启动位", f"{start_bit}", "来自启动站" if start_bit else "来自从动站", "",
       base_offset + 1, base_offset + 1)
    # 功能码解析
    if dir_bit:
        func_name = _FUNC_CODE_UP.get(func_code_full, f"保留({func_code_full})")
    else:
        func_name = _FUNC_CODE_DOWN.get(func_code_full, f"保留({func_code_full})")
    _f(table, "功能码", f"{func_code_full}", func_name, "事件报文功能码",
       base_offset + 1, base_offset + 2)
    _f(table, "转发数据长度", f"0x{data_len:03X}", f"{data_len}字节", "数据域长度",
       base_offset + 2, base_offset + 3)
    _f(table, "报文序号", f"0x{seq:04X}", str(seq), "STA分配,递增",
       base_offset + 4, base_offset + 5)
    # 电能表地址(6字节)
    addr_raw, addr = _meter_addr(payload, 6)
    _f(table, "电能表地址", addr_raw, addr, "发生事件的电能表地址",
       base_offset + 6, base_offset + 11)
    offset = 12
    # 事件数据解析
    if offset < len(payload):
        evt_data = payload[offset:]
        evt_type = evt_data[0] if evt_data else 0
        _parse_event_data(table, evt_data, evt_type, base_offset + offset)
    return table


def _parse_event_data(table: list, evt_data: bytes, evt_type: int, base_offset: int):
    """解析事件数据域"""
    if not evt_data:
        return
    if evt_type in (1, 2):
        # 停复电事件-位图方式(表12)
        type_name = "停电事件(位图)" if evt_type == 1 else "上电事件(位图)"
        _f(table, "STA上报事件类型", f"0x{evt_type:02X}", type_name, "", base_offset, base_offset)
        if len(evt_data) >= 3:
            tei = _uint16_le(evt_data, 1)
            _f(table, "起始TEI", f"0x{tei:04X}", str(tei), "发生事件站点起始TEI",
               base_offset + 1, base_offset + 2)
            bitmap = evt_data[3:]
            if bitmap:
                _f(table, "节点位图", _hex(bitmap)[:60], f"{len(bitmap)}字节",
                   "对应位置1标志该TEI节点发生事件", base_offset + 3, base_offset + len(evt_data) - 1)
    elif evt_type in (3, 4):
        # 停复电事件-地址方式(表13)
        type_name = "停电事件(地址)" if evt_type == 3 else "上电事件(地址)"
        _f(table, "STA上报事件类型", f"0x{evt_type:02X}", type_name, "", base_offset, base_offset)
        if len(evt_data) >= 3:
            count = _uint16_le(evt_data, 1)
            _f(table, "电表个数", f"0x{count:04X}", str(count), "发生事件电表个数",
               base_offset + 1, base_offset + 2)
            off = 3
            for i in range(min(count, 16)):
                if off + 7 > len(evt_data):
                    break
                addr_raw, addr = _meter_addr(evt_data, off)
                status = evt_data[off + 6]
                status_str = "未停电" if status else "停电"
                _f(table, f"  电表{i+1}", f"{addr_raw} [{status_str}]", addr,
                   f"带电状态:{status_str}", base_offset + off, base_offset + off + 6)
                off += 7
            if off < len(evt_data):
                _remaining(table, evt_data, off, base_offset)
    elif evt_type == 0x33:
        # 即装即采事件(表14)
        _f(table, "STA上报事件类型", f"0x{evt_type:02X}", "即装即采(设备信息)", "",
           base_offset, base_offset)
        off = 1
        if off + 6 <= len(evt_data):
            addr_raw, addr = _mac_addr(evt_data, off)
            _f(table, "设备地址", addr_raw, addr, "STA模块通信地址",
               base_offset + off, base_offset + off + 5)
            off += 6
        if off < len(evt_data):
            proto = evt_data[off]
            proto_name = _PROTOCOL_TYPE_MAP.get(proto, f"保留(0x{proto:02X})")
            _f(table, "设备通信协议类型", f"0x{proto:02X}", proto_name, "",
               base_offset + off, base_offset + off)
            off += 1
        if off < len(evt_data):
            desc_len = evt_data[off]
            _f(table, "设备描述符长度", f"{desc_len}", str(desc_len), "",
               base_offset + off, base_offset + off)
            off += 1
            if off + desc_len <= len(evt_data):
                desc = evt_data[off:off + desc_len]
                try:
                    desc_str = desc.decode('ascii')
                except Exception:
                    desc_str = _hex(desc)
                _f(table, "设备描述符", _hex(desc)[:40], desc_str, "ASCII格式",
                   base_offset + off, base_offset + off + desc_len - 1)
                off += desc_len
        if off < len(evt_data):
            dev_count = evt_data[off]
            _f(table, "下挂设备数量", f"{dev_count}", str(dev_count), "不超过32",
               base_offset + off, base_offset + off)
            off += 1
            for i in range(min(dev_count, 8)):
                if off >= len(evt_data):
                    break
                addr_len = evt_data[off]
                off += 1
                if off + addr_len > len(evt_data):
                    break
                dev_addr = evt_data[off:off + addr_len]
                off += addr_len
                if off >= len(evt_data):
                    break
                dev_desc_len = evt_data[off]
                off += 1
                if off + dev_desc_len > len(evt_data):
                    break
                dev_desc = evt_data[off:off + dev_desc_len]
                off += dev_desc_len
                dev_proto = evt_data[off] if off < len(evt_data) else 0
                off += 1
                try:
                    dev_desc_str = dev_desc.decode('ascii')
                except Exception:
                    dev_desc_str = _hex(dev_desc)
                proto_name = _PROTOCOL_TYPE_MAP.get(dev_proto, f"0x{dev_proto:02X}")
                _f(table, f"  下挂设备{i+1}", f"{_hex(dev_addr)} [{dev_desc_str}]",
                   f"协议:{proto_name}", f"地址长度={addr_len}",
                   base_offset + off - addr_len - dev_desc_len - 3, base_offset + off - 1)
    else:
        # 电能表事件或其他
        _f(table, "事件数据", _hex(evt_data)[:80], f"{len(evt_data)}字节",
           f"事件类型=0x{evt_type:02X}", base_offset, base_offset + len(evt_data) - 1)


# ═══════════════════════════════════════════════════════════
# 0x0011: 查询从节点主动注册
# ═══════════════════════════════════════════════════════════

def _parse_query_node_registration(payload: bytes, direction: int, base_offset: int) -> list:
    """查询从节点主动注册: 下行(表6)头20字节, 上行(表7)头36字节"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    ctrl = (b1 >> 4) & 0x0F
    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "下行=20, 上行=36",
       base_offset, base_offset + 1)

    offset = 2
    if direction == 0:  # 下行(表6)
        force_resp = (ctrl >> 3) & 0x01
        reg_param = ctrl & 0x07
        _f(table, "强制应答标志", f"{force_resp}", "强制应答" if force_resp else "搜表完成应答",
           "", base_offset + 1, base_offset + 1)
        _f(table, "从节点注册参数", f"{reg_param}", str(reg_param), "固定为0",
           base_offset + 1, base_offset + 1)
        # 保留(2B)
        if offset + 2 <= len(payload):
            _f(table, "保留", _hex(payload[offset:offset + 2]), "2字节", "",
               base_offset + offset, base_offset + offset + 1)
            offset += 2
        # 报文序号(4B)
        if offset + 4 <= len(payload):
            seq = _uint32_le(payload, offset)
            _f(table, "报文序号", f"0x{seq:08X}", str(seq), "序号递增,重发不变",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
        # 源MAC(6B)
        if offset + 6 <= len(payload):
            raw, addr = _mac_addr(payload, offset)
            _f(table, "源MAC地址", raw, addr, "CCO的MAC地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6
        # 目的MAC(6B)
        if offset + 6 <= len(payload):
            raw, addr = _mac_addr(payload, offset)
            _f(table, "目的MAC地址", raw, addr, "待查询站点MAC",
               base_offset + offset, base_offset + offset + 5)
            offset += 6
    else:  # 上行(表7)
        searching = (ctrl >> 3) & 0x01
        reg_param = ctrl & 0x07
        _f(table, "状态字段", f"{searching}", "STA正在搜表" if searching else "STA搜表完成",
           "", base_offset + 1, base_offset + 1)
        _f(table, "从节点注册参数", f"{reg_param}", str(reg_param), "固定为0",
           base_offset + 1, base_offset + 1)
        # 电能表数量(1B)
        if offset < len(payload):
            cnt = payload[offset]
            _f(table, "电能表数量", f"0x{cnt:02X}", str(cnt), "STA搜到的电表数量",
               base_offset + offset, base_offset + offset)
            offset += 1
        # 产品类型(1B)
        if offset < len(payload):
            pt = payload[offset]
            pt_map = {0: "电能表", 1: "I型采集器", 2: "II型采集器"}
            _f(table, "产品类型", f"0x{pt:02X}", pt_map.get(pt, f"保留({pt})"), "",
               base_offset + offset, base_offset + offset)
            offset += 1
        # 设备地址(6B)
        if offset + 6 <= len(payload):
            raw, addr = _meter_addr(payload, offset)
            _f(table, "设备地址", raw, addr, "电能表/采集器地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6
        # 设备ID(6B)
        if offset + 6 <= len(payload):
            raw, addr = _mac_addr(payload, offset)
            _f(table, "设备ID", raw, addr, "STA本身唯一地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6
        # 报文序号(4B)
        if offset + 4 <= len(payload):
            seq = _uint32_le(payload, offset)
            _f(table, "报文序号", f"0x{seq:08X}", str(seq), "应与下行一致",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
        # 保留(4B)
        if offset + 4 <= len(payload):
            _f(table, "保留", _hex(payload[offset:offset + 4]), "4字节", "",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
        # 源MAC(6B)
        if offset + 6 <= len(payload):
            raw, addr = _mac_addr(payload, offset)
            _f(table, "源MAC地址", raw, addr, "发送站点MAC",
               base_offset + offset, base_offset + offset + 5)
            offset += 6
        # 目的MAC(6B)
        if offset + 6 <= len(payload):
            raw, addr = _mac_addr(payload, offset)
            _f(table, "目的MAC地址", raw, addr, "CCO的MAC地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6
        # 电能表列表(每表8B)
        if offset < len(payload):
            remaining = payload[offset:]
            rem_count = len(remaining) // 8
            if rem_count > 0:
                _f(table, "电能表列表", f"{len(remaining)}字节", f"{rem_count}个电能表", "",
                   base_offset + offset, base_offset + len(payload) - 1)
                for i in range(rem_count):
                    ent_off = offset + i * 8
                    if ent_off + 8 <= len(payload):
                        entry = payload[ent_off:ent_off + 8]
                        raw, addr = _meter_addr(entry, 0)
                        proto = entry[6]
                        proto_name = _PROTOCOL_TYPE_MAP.get(proto, f"0x{proto:02X}")
                        status = entry[7]
                        _f(table, f"  电能表{i+1}", f"{raw} 协议={proto_name}", addr,
                           f"协议:{proto_name} 状态:0x{status:02X}",
                           base_offset + ent_off, base_offset + ent_off + 7)
                offset += rem_count * 8
    _remaining(table, payload, offset, base_offset)
    return table


# ═══════════════════════════════════════════════════════════
# 0x0012: 启动从节点主动注册
# ═══════════════════════════════════════════════════════════

def _parse_start_node_registration(payload: bytes, direction: int, base_offset: int) -> list:
    """启动从节点注册(表5): 协议版本+头长度+强制应答+注册参数+保留(2B)+序号(4B)"""
    table = []
    if len(payload) < 8:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    ctrl = (b1 >> 4) & 0x0F
    force_resp = (ctrl >> 3) & 0x01
    reg_param = ctrl & 0x07
    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "固定为8", base_offset, base_offset + 1)
    _f(table, "强制应答标志", f"{force_resp}", "非强制应答" if force_resp == 0 else "强制应答",
       "固定为0", base_offset + 1, base_offset + 1)
    _f(table, "从节点注册参数", f"{reg_param}", str(reg_param), "固定为1",
       base_offset + 1, base_offset + 1)
    _f(table, "保留", _hex(payload[2:4]), "2字节", "", base_offset + 2, base_offset + 3)
    seq = _uint32_le(payload, 4)
    _f(table, "报文序号", f"0x{seq:08X}", str(seq), "序号递增,重发不变",
       base_offset + 4, base_offset + 7)
    _remaining(table, payload, 8, base_offset)
    return table


# ═══════════════════════════════════════════════════════════
# 0x0013: 停止从节点主动注册
# ═══════════════════════════════════════════════════════════

def _parse_stop_node_registration(payload: bytes, direction: int, base_offset: int) -> list:
    """停止从节点注册(表8): 协议版本+头长度+保留(4b)+保留(2B)+序号(4B)"""
    table = []
    if len(payload) < 8:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "固定为8", base_offset, base_offset + 1)
    _f(table, "保留", _hex(payload[2:4]), "2字节", "", base_offset + 2, base_offset + 3)
    seq = _uint32_le(payload, 4)
    _f(table, "报文序号", f"0x{seq:08X}", str(seq), "序号递增,重发不变",
       base_offset + 4, base_offset + 7)
    _remaining(table, payload, 8, base_offset)
    return table


# ═══════════════════════════════════════════════════════════
# 0x0020: 确认/否认
# ═══════════════════════════════════════════════════════════

def _parse_confirm_deny(payload: bytes, direction: int, base_offset: int) -> list:
    """确认/否认(表17): 协议版本+头长度+方向位+确认位+保留(2b)+报文序号(16b)"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "确认/否认数据域不足",
           base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    dir_bit = (b1 >> 4) & 0x01
    confirm_bit = (b1 >> 5) & 0x01
    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "", base_offset, base_offset + 1)
    _f(table, "方向位", f"{dir_bit}", "上行" if dir_bit else "下行", "",
       base_offset + 1, base_offset + 1)
    _f(table, "确认位", f"{confirm_bit}", "确认" if confirm_bit else "否认", "",
       base_offset + 1, base_offset + 1)
    seq = _uint16_le(payload, 2)
    _f(table, "报文序号", f"0x{seq:04X}", str(seq), "用于判断确认/否认是否过期",
       base_offset + 2, base_offset + 3)
    _remaining(table, payload, 4, base_offset)
    return table


# ═══════════════════════════════════════════════════════════
# 0x0030~0x0036: 升级报文
# ═══════════════════════════════════════════════════════════

def _parse_start_upgrade(payload: bytes, direction: int, base_offset: int) -> list:
    """开始升级: 下行(表18), 上行(表24)"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset, hdr = _parse_header_generic(payload, base_offset, direction)
    table.extend(hdr)
    if direction == 0:  # 下行
        if offset + 4 <= len(payload):
            uid = _uint32_le(payload, offset)
            _f(table, "升级ID", f"0x{uid:08X}", str(uid), "区分每次升级,不为0",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
        if offset + 2 <= len(payload):
            tw = _uint16_le(payload, offset)
            _f(table, "升级时间窗", f"0x{tw:04X}", f"{tw}分钟", "升级最长时间",
               base_offset + offset, base_offset + offset + 1)
            offset += 2
        if offset + 2 <= len(payload):
            bs = _uint16_le(payload, offset)
            _f(table, "升级块大小", f"0x{bs:04X}", f"{bs}字节", "允许:100/200/300/400",
               base_offset + offset, base_offset + offset + 1)
            offset += 2
        if offset + 4 <= len(payload):
            fs = _uint32_le(payload, offset)
            _f(table, "升级文件大小", f"0x{fs:08X}", f"{fs}字节", "升级文件字节数",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
        if offset + 4 <= len(payload):
            crc = _uint32_le(payload, offset)
            _f(table, "文件CRC校验", f"0x{crc:08X}", f"0x{crc:08X}", "CRC-32校验",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
    else:  # 上行(表24)
        if offset < len(payload):
            _f(table, "保留", f"0x{payload[offset]:02X}", "", "",
               base_offset + offset, base_offset + offset)
            offset += 1
        if offset < len(payload):
            code = payload[offset]
            _f(table, "开始升级结果码", f"0x{code:02X}", "成功" if code == 0 else f"失败({code})",
               "0=成功,其他=失败", base_offset + offset, base_offset + offset)
            offset += 1
        if offset + 4 <= len(payload):
            uid = _uint32_le(payload, offset)
            _f(table, "升级ID", f"0x{uid:08X}", str(uid), "", base_offset + offset, base_offset + offset + 3)
            offset += 4
    _remaining(table, payload, offset, base_offset)
    return table


def _parse_stop_upgrade(payload: bytes, direction: int, base_offset: int) -> list:
    """停止升级(表19)"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset, hdr = _parse_header_generic(payload, base_offset, direction)
    table.extend(hdr)
    if offset + 4 <= len(payload):
        uid = _uint32_le(payload, offset)
        _f(table, "升级ID", f"0x{uid:08X}", str(uid), "使用0终止本次升级",
           base_offset + offset, base_offset + offset + 3)
        offset += 4
    _remaining(table, payload, offset, base_offset)
    return table


def _parse_file_transfer(payload: bytes, direction: int, base_offset: int) -> list:
    """传输文件数据(表20)"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    block_size = _uint16_le(payload, 2)
    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "", base_offset, base_offset + 1)
    _f(table, "数据块大小", f"0x{block_size:04X}", f"{block_size}字节", "数据块包含的字节数",
       base_offset + 2, base_offset + 3)
    offset = 4
    if offset + 4 <= len(payload):
        uid = _uint32_le(payload, offset)
        _f(table, "升级ID", f"0x{uid:08X}", str(uid), "", base_offset + offset, base_offset + offset + 3)
        offset += 4
    if offset + 4 <= len(payload):
        blk_seq = _uint32_le(payload, offset)
        _f(table, "数据块编号", f"0x{blk_seq:08X}", str(blk_seq), "递增",
           base_offset + offset, base_offset + offset + 3)
        offset += 4
    if offset < len(payload):
        file_data = payload[offset:]
        _f(table, "数据块", _hex(file_data)[:80], f"{len(file_data)}字节", "升级文件数据",
           base_offset + offset, base_offset + len(payload) - 1)
    return table


def _parse_file_transfer_broadcast(payload: bytes, direction: int, base_offset: int) -> list:
    """传输文件数据(单播转本地广播) - 同0x0032"""
    return _parse_file_transfer(payload, direction, base_offset)


def _parse_query_upgrade_status(payload: bytes, direction: int, base_offset: int) -> list:
    """查询站点升级状态: 下行(表21), 上行(表25)"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset, hdr = _parse_header_generic(payload, base_offset, direction)
    table.extend(hdr)
    if direction == 0:  # 下行(表21)
        if offset + 2 <= len(payload):
            block_cnt = _uint16_le(payload, offset)
            desc = "查询所有块状态" if block_cnt == 0xFFFF else f"{block_cnt}个块"
            _f(table, "连续查询块数", f"0x{block_cnt:04X}", desc, "0xFFFF=查询所有",
               base_offset + offset, base_offset + offset + 1)
            offset += 2
        if offset + 4 <= len(payload):
            start_blk = _uint32_le(payload, offset)
            _f(table, "起始块号", f"0x{start_blk:08X}", str(start_blk), "",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
        if offset + 4 <= len(payload):
            uid = _uint32_le(payload, offset)
            _f(table, "升级ID", f"0x{uid:08X}", str(uid), "",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
    else:  # 上行(表25)
        b_ctrl = payload[1] if len(payload) > 1 else 0
        status = (b_ctrl >> 4) & 0x0F
        status_name = _UPGRADE_STATUS_MAP.get(status, f"保留({status})")
        _f(table, "升级状态", f"{status}", status_name, "", base_offset + 1, base_offset + 1)
        if offset + 2 <= len(payload):
            valid_blocks = _uint16_le(payload, offset)
            _f(table, "有效块数", f"0x{valid_blocks:04X}", str(valid_blocks), "位图中有效块数",
               base_offset + offset, base_offset + offset + 1)
            offset += 2
        if offset + 4 <= len(payload):
            start_blk = _uint32_le(payload, offset)
            _f(table, "起始块号", f"0x{start_blk:08X}", str(start_blk), "",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
        if offset + 4 <= len(payload):
            uid = _uint32_le(payload, offset)
            _f(table, "升级ID", f"0x{uid:08X}", str(uid), "空闲态回复0",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
        if offset < len(payload):
            bitmap = payload[offset:]
            _f(table, "位图", _hex(bitmap)[:60], f"{len(bitmap)}字节",
               "0=未收到, 1=已收到", base_offset + offset, base_offset + len(payload) - 1)
            offset = len(payload)
    _remaining(table, payload, offset, base_offset)
    return table


def _parse_execute_upgrade(payload: bytes, direction: int, base_offset: int) -> list:
    """执行升级(表22): 等待复位时间(16b)+升级ID(32b)+试运行时间(32b)"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset, hdr = _parse_header_generic(payload, base_offset, direction)
    table.extend(hdr)
    if offset + 4 <= len(payload):
        uid = _uint32_le(payload, offset)
        _f(table, "升级ID", f"0x{uid:08X}", str(uid), "", base_offset + offset, base_offset + offset + 3)
        offset += 4
    if offset + 4 <= len(payload):
        trial = _uint32_le(payload, offset)
        _f(table, "试运行时间", f"0x{trial:08X}", f"{trial}秒", "0=不需要试运行",
           base_offset + offset, base_offset + offset + 3)
        offset += 4
    _remaining(table, payload, offset, base_offset)
    return table


def _parse_query_site_info(payload: bytes, direction: int, base_offset: int) -> list:
    """查询站点信息: 下行(表23), 上行(表26)"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "", base_offset, base_offset + 1)

    if direction == 0:  # 下行(表23)
        reserved = _uint16_le(payload, 1) & 0x0FFF
        elem_count = payload[3] if len(payload) > 3 else 0
        _f(table, "保留", f"0x{reserved:03X}", "", "", base_offset + 1, base_offset + 2)
        _f(table, "信息列表元素个数", f"{elem_count}", str(elem_count), "",
           base_offset + 3, base_offset + 3)
        offset = 4
        for i in range(min(elem_count, 16)):
            if offset >= len(payload):
                break
            elem_id = payload[offset]
            elem_name = _SITE_INFO_ELEM_MAP.get(elem_id, f"保留(0x{elem_id:02X})")
            _f(table, f"  元素{i+1} ID", f"0x{elem_id:02X}", elem_name, "",
               base_offset + offset, base_offset + offset)
            offset += 1
    else:  # 上行(表26)
        reserved = (payload[1] >> 4) & 0x0F
        elem_count = payload[3] if len(payload) > 3 else 0
        _f(table, "保留", f"0x{reserved:X}", "", "", base_offset + 1, base_offset + 1)
        _f(table, "信息数据列表元素个数", f"{elem_count}", str(elem_count), "",
           base_offset + 3, base_offset + 3)
        offset = 4
        if offset + 4 <= len(payload):
            uid = _uint32_le(payload, offset)
            _f(table, "升级ID", f"0x{uid:08X}", str(uid), "",
               base_offset + offset, base_offset + offset + 3)
            offset += 4
        for i in range(min(elem_count, 16)):
            if offset + 2 > len(payload):
                break
            elem_id = payload[offset]
            elem_len = payload[offset + 1]
            elem_name = _SITE_INFO_ELEM_MAP.get(elem_id, f"0x{elem_id:02X}")
            offset += 2
            elem_data = payload[offset:offset + elem_len] if offset + elem_len <= len(payload) else b''
            _f(table, f"  元素{i+1}", f"ID=0x{elem_id:02X} 长度={elem_len}",
               f"{elem_name}: {_hex(elem_data)[:40]}", "",
               base_offset + offset - 2, base_offset + offset + elem_len - 1)
            offset += elem_len
    _remaining(table, payload, offset, base_offset)
    return table


# ═══════════════════════════════════════════════════════════
# 0x0040: 抄控器CCO (表40)
# ═══════════════════════════════════════════════════════════

def _parse_meter_controller_cco(payload: bytes, base_offset: int, direction: int) -> list:
    """抄控器-CCO报文(表40): 协议类型(8b) + 报文长度(16b) + 报文内容"""
    table = []
    if len(payload) < 3:
        _f(table, "❌ 数据不足", "", "", "抄控器CCO数据域不足3字节",
           base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset = 0
    proto_type = payload[offset]
    proto_name = "Q/GDW10376.2-2019" if proto_type == 0 else f"备用({proto_type})"
    _f(table, "协议类型", f"0x{proto_type:02X}", proto_name, "", base_offset, base_offset)
    offset += 1
    msg_len = _uint16_le(payload, offset)
    _f(table, "报文长度", f"0x{msg_len:04X}", f"{msg_len}字节", "交互报文内容长度",
       base_offset + offset, base_offset + offset + 1)
    offset += 2
    if offset < len(payload):
        content = payload[offset:]
        _f(table, "报文内容", _hex(content)[:80], f"{len(content)}字节",
           "参考Q/GDW10376.2-2019协议", base_offset + offset, base_offset + len(payload) - 1)
    return table


# ═══════════════════════════════════════════════════════════
# 0x0041: 抄控器数据透传串口转发 (表41)
# ═══════════════════════════════════════════════════════════

def _parse_meter_controller_serial(payload: bytes, base_offset: int, direction: int) -> list:
    """抄控器数据透传串口转发(表41):
    协议类型(8b) + 启动标志(1b)+保留(7b) + 串口波特率(32b) + 保留(32b) + 报文长度(16b) + 报文内容
    """
    table = []
    if len(payload) < 12:
        _f(table, "❌ 数据不足", "", "", "抄控器串口转发数据域不足12字节",
           base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset = 0
    proto_type = payload[offset]
    proto_name = "透明传输" if proto_type == 0 else f"备用({proto_type})"
    _f(table, "协议类型", f"0x{proto_type:02X}", proto_name, "", base_offset, base_offset)
    offset += 1
    b1 = payload[offset]
    start_flag = b1 & 0x01
    _f(table, "启动标志", f"{start_flag}", "需要转发到串口" if start_flag else "无需转发到串口",
       "", base_offset + offset, base_offset + offset)
    offset += 1
    baud = _uint32_le(payload, offset)
    baud_desc = "默认波特率" if baud == 0 else f"{baud}bps"
    _f(table, "串口波特率", f"0x{baud:08X}", baud_desc, "非0按此波特率设置",
       base_offset + offset, base_offset + offset + 3)
    offset += 4
    _f(table, "保留", _hex(payload[offset:offset+4]), "", "",
       base_offset + offset, base_offset + offset + 3)
    offset += 4
    msg_len = _uint16_le(payload, offset)
    _f(table, "报文长度", f"0x{msg_len:04X}", f"{msg_len}字节", "交互报文内容长度",
       base_offset + offset, base_offset + offset + 1)
    offset += 2
    if offset < len(payload):
        content = payload[offset:]
        _f(table, "报文内容", _hex(content)[:80], f"{len(content)}字节",
           "转发到终端/电表串口的数据", base_offset + offset, base_offset + len(payload) - 1)
    return table


# ═══════════════════════════════════════════════════════════
# 0x00A0: 鉴权安全
# ═══════════════════════════════════════════════════════════

def _parse_auth_security(payload: bytes, base_offset: int, direction: int) -> list:
    """鉴权安全报文(端口号0x1A)"""
    table = []
    if len(payload) < 1:
        return table
    _f(table, "鉴权安全数据", _hex(payload)[:80], f"{len(payload)}字节",
       "鉴权安全业务数据", base_offset, base_offset + len(payload) - 1)
    return table


# ═══════════════════════════════════════════════════════════
# 0x00A1: 台区户变关系识别 (表29-36)
# ═══════════════════════════════════════════════════════════

_FEATURE_TYPE_MAP = {
    0x01: "工频电压特征",
    0x02: "工频频率特征",
    0x03: "工频周期特征",
}

_COLLECT_TYPE_MAP = {
    0x01: "台区特征采集启动",
    0x02: "台区特征信息收集",
    0x03: "台区特征信息告知",
    0x04: "台区判别结果查询",
    0x05: "台区判别结果信息",
}


def _parse_district_transformer(payload: bytes, base_offset: int, direction: int) -> list:
    """台区户变关系识别(表29): 12字节报文头 + DATA"""
    table = []
    if len(payload) < 12:
        _f(table, "❌ 数据不足", "", "", "台区识别数据域不足12字节",
           base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset = 0
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    dir_bit = (b1 >> 4) & 0x01
    start_bit = (b1 >> 5) & 0x01
    phase = (b1 >> 6) & 0x03
    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "", base_offset, base_offset + 1)
    _f(table, "方向位", f"{dir_bit}", "上行(STA→CCO)" if dir_bit else "下行(CCO→STA)",
       "", base_offset + 1, base_offset + 1)
    _f(table, "启动位", f"{start_bit}", "来自启动站" if start_bit else "来自从动站",
       "", base_offset + 1, base_offset + 1)
    phase_names = {0: "默认相位", 1: "第一出线", 2: "第二出线", 3: "第三出线"}
    _f(table, "采集相位", f"{phase}", phase_names.get(phase, str(phase)),
       "", base_offset + 1, base_offset + 1)
    seq = _uint16_le(payload, 2)
    _f(table, "报文序号", f"0x{seq:04X}", str(seq), "", base_offset + 2, base_offset + 3)
    mac_raw, mac_str = _mac_addr(payload, 4)
    _f(table, "MAC地址", mac_raw, mac_str, "大端序", base_offset + 4, base_offset + 9)
    feature_type = payload[10]
    _f(table, "特征类型", f"0x{feature_type:02X}",
       _FEATURE_TYPE_MAP.get(feature_type, f"保留(0x{feature_type:02X})"),
       "", base_offset + 10, base_offset + 10)
    collect_type = payload[11]
    _f(table, "采集类型", f"0x{collect_type:02X}",
       _COLLECT_TYPE_MAP.get(collect_type, f"保留(0x{collect_type:02X})"),
       "", base_offset + 11, base_offset + 11)
    offset = 12
    # 根据采集类型解析DATA
    if collect_type == 0x01:  # 台区特征采集启动(表31)
        if offset + 8 <= len(payload):
            ntb = _uint32_le(payload, offset)
            _f(table, "起始NTB", f"0x{ntb:08X}", str(ntb), "全网开始采集时刻",
               base_offset + offset, base_offset + offset + 3)
            period = payload[offset + 4]
            _f(table, "采集周期", f"0x{period:02X}", f"{period}秒", "", base_offset + offset + 4, base_offset + offset + 4)
            count = payload[offset + 5]
            _f(table, "采集数量", f"0x{count:02X}", str(count), "连续采集特征信息数量",
               base_offset + offset + 5, base_offset + offset + 5)
            seq_no = payload[offset + 6]
            _f(table, "采集序列号", f"0x{seq_no:02X}", str(seq_no), "第几次启动采集",
               base_offset + offset + 6, base_offset + offset + 6)
            offset += 8
    elif collect_type == 0x03:  # 台区特征信息告知(表32)
        if offset + 8 <= len(payload):
            b_teI = _uint16_le(payload, offset)
            tei = b_teI & 0x0FFF
            collect_method = (payload[offset + 1] >> 4) & 0x03
            _f(table, "TEI", f"0x{tei:03X}", str(tei), "", base_offset + offset, base_offset + offset + 1)
            method_map = {0: "保留", 1: "下降沿采集", 2: "上升沿采集", 3: "双沿采集"}
            _f(table, "采集方式", f"{collect_method}", method_map.get(collect_method, str(collect_method)),
               "仅工频周期特征有效", base_offset + offset + 1, base_offset + offset + 1)
            collect_seq = payload[offset + 2]
            _f(table, "采集序列号", f"0x{collect_seq:02X}", str(collect_seq), "第几次采集活动",
               base_offset + offset + 2, base_offset + offset + 2)
            total_count = payload[offset + 3]
            _f(table, "告知总数量", f"0x{total_count:02X}", str(total_count), "特征信息序列数据个数",
               base_offset + offset + 3, base_offset + offset + 3)
            ntb1 = _uint32_le(payload, offset + 4)
            _f(table, "起始采集NTB1", f"0x{ntb1:08X}", str(ntb1), "第一个特征数据采集时刻",
               base_offset + offset + 4, base_offset + offset + 7)
            offset += 8
            # 特征序列
            if offset < len(payload):
                feat_data = payload[offset:]
                _f(table, "台区特征信息序列", _hex(feat_data)[:80], f"{len(feat_data)}字节",
                   f"{_FEATURE_TYPE_MAP.get(feature_type, '特征')}数据",
                   base_offset + offset, base_offset + len(payload) - 1)
                offset = len(payload)
    elif collect_type == 0x05:  # 台区判别结果信息(表36)
        if offset + 10 <= len(payload):
            tei = _uint16_le(payload, offset)
            _f(table, "TEI", f"0x{tei:04X}", str(tei), "STA的TEI标识",
               base_offset + offset, base_offset + offset + 1)
            end_flag = payload[offset + 2]
            _f(table, "结束标志", f"0x{end_flag:02X}",
               "识别过程结束" if end_flag == 1 else ("识别进行中" if end_flag == 0 else f"保留({end_flag})"),
               "", base_offset + offset + 2, base_offset + offset + 2)
            result = payload[offset + 3]
            result_map = {0: "识别结果未知", 1: "是本台区", 2: "不是本台区"}
            _f(table, "台区识别结果", f"0x{result:02X}", result_map.get(result, f"保留({result})"),
               "", base_offset + offset + 3, base_offset + offset + 3)
            cco_raw, cco_str = _mac_addr(payload, offset + 4)
            _f(table, "正确隶属CCO地址", cco_raw, cco_str, "非本台区时填充",
               base_offset + offset + 4, base_offset + offset + 9)
            offset += 10
    _remaining(table, payload, offset, base_offset)
    return table


# ═══════════════════════════════════════════════════════════
# 0x00A2: 查询ID信息 (表38/39)
# ═══════════════════════════════════════════════════════════

_ID_TYPE_MAP = {
    0: "模块ID(兼容历史)",
    1: "芯片ID(24字节)",
    2: "模块ID(11字节)",
}


def _parse_query_id_info(payload: bytes, base_offset: int, direction: int) -> list:
    """查询ID信息 下行(表38)/上行(表39)"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "查询ID数据域不足4字节",
           base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset = 0
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    dir_bit = (b1 >> 4) & 0x01
    id_type = (b1 >> 5) & 0x07
    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "帧头长度", f"{hdr_len}", str(hdr_len), "", base_offset, base_offset + 1)
    _f(table, "方向位", f"{dir_bit}", "上行(STA→CCO)" if dir_bit else "下行(CCO→STA)",
       "", base_offset + 1, base_offset + 1)
    _f(table, "ID类型", f"{id_type}", _ID_TYPE_MAP.get(id_type, f"保留({id_type})"),
       "", base_offset + 1, base_offset + 1)
    seq = _uint16_le(payload, 2)
    _f(table, "报文序号", f"0x{seq:04X}", str(seq), "", base_offset + 2, base_offset + 3)
    offset = 4
    # 上行报文有额外字段
    if dir_bit == 1 and offset < len(payload):
        id_len = payload[offset]
        _f(table, "ID长度", f"0x{id_len:02X}", f"{id_len}字节",
           "芯片ID=24, 模块ID=11", base_offset + offset, base_offset + offset)
        offset += 1
        if offset + id_len <= len(payload):
            id_data = payload[offset:offset + id_len]
            _f(table, "ID信息", _hex(id_data)[:80], f"{id_len}字节",
               "芯片/模块ID信息", base_offset + offset, base_offset + offset + id_len - 1)
            offset += id_len
        if offset < len(payload):
            dev_type = payload[offset]
            _f(table, "设备类型", f"0x{dev_type:02X}",
               _DEVICE_TYPE_MAP.get(dev_type, f"保留({dev_type})"),
               "", base_offset + offset, base_offset + offset)
            offset += 1
    _remaining(table, payload, offset, base_offset)
    return table


# ═══════════════════════════════════════════════════════════
# 0x00A3: 精准校时 (表37)
# ═══════════════════════════════════════════════════════════

def _parse_precise_time_sync(payload: bytes, base_offset: int, direction: int) -> list:
    """精准校时下行(表37): 协议版本+头长度+转发数据长度(12b)+报文序号(8b)+NTB(32b)+DATA"""
    table = []
    if len(payload) < 8:
        _f(table, "❌ 数据不足", "", "", "精准校时数据域不足8字节",
           base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset = 0
    b0 = payload[0]
    version = b0 & 0x3F
    hdr_len_high = (b0 >> 6) & 0x03
    b1 = payload[1]
    hdr_len_low = b1 & 0x0F
    hdr_len = (hdr_len_high << 4) | hdr_len_low
    b2 = payload[2]
    data_len_high = b2 & 0x0F
    b3 = payload[3]
    data_len = (data_len_high << 8) | b3
    _f(table, "协议版本号", f"{version}", str(version), "固定为1", base_offset, base_offset)
    _f(table, "报文头长度", f"{hdr_len}", str(hdr_len), "", base_offset, base_offset + 1)
    _f(table, "转发数据长度", f"0x{data_len:03X}", f"{data_len}字节", "DATA长度",
       base_offset + 2, base_offset + 3)
    seq = payload[3] if len(payload) > 3 else 0
    # 表37: 字节3=报文序号(8b), 字节4-7=NTB(32b)
    seq_no = payload[3]
    _f(table, "报文序号", f"0x{seq_no:02X}", str(seq_no), "CCO分配,依次递增",
       base_offset + 3, base_offset + 3)
    ntb = _uint32_le(payload, 4)
    _f(table, "NTB", f"0x{ntb:08X}", str(ntb), "CCO当前的NTB",
       base_offset + 4, base_offset + 7)
    offset = 8
    if offset < len(payload):
        data = payload[offset:]
        _f(table, "数据(DATA)", _hex(data)[:80], f"{len(data)}字节",
           "终端下发的校时报文", base_offset + offset, base_offset + len(payload) - 1)
    return table


# ═══════════════════════════════════════════════════════════
# 0x00A4: 配电信息上报
# ═══════════════════════════════════════════════════════════

def _parse_power_distribution_report(payload: bytes, base_offset: int, direction: int) -> list:
    """配电信息上报"""
    table = []
    if len(payload) < 4:
        _f(table, "配电信息数据", _hex(payload)[:80], f"{len(payload)}字节",
           "配电信息上报数据", base_offset, base_offset + max(len(payload) - 1, 0))
        return table
    offset, hdr = _parse_header_generic(payload, base_offset, direction)
    table.extend(hdr)
    if offset < len(payload):
        data = payload[offset:]
        _f(table, "数据(DATA)", _hex(data)[:80], f"{len(data)}字节",
           "配电信息数据", base_offset + offset, base_offset + len(payload) - 1)
    return table
