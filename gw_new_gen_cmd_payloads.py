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


# ── 通用工具：追加字段 ──
def _f(table: list, name: str, raw: str, parsed: str, desc: str, start: int, end: int):
    table.append((name, raw, parsed, desc, start, end))


def _remaining(table: list, data: bytes, offset: int, base_offset: int):
    if offset < len(data):
        rem = data[offset:]
        _f(table, "剩余数据", _hex(rem)[:80], f"{len(rem)}字节", "未解析数据",
           base_offset + offset, base_offset + len(data) - 1)


# ── 抄表报文公共解析 ──
_PROTOCOL_TYPE_MAP = {
    0x00: "透明传输",
    0x01: "DL/T 645-1997",
    0x02: "DL/T 645-2007",
    0x03: "DL/T 698.45",
}


def _parse_meter_common_header(payload: bytes, offset: int, base_offset: int, direction: int) -> int:
    """解析抄表/注册类报文的公共报文头（协议版本号+报文头长度+控制字段+序号等）"""
    table = []
    if offset + 4 > len(payload):
        return offset

    # 字节0: 协议版本号(6bit) + 报文头长度高2位(2bit)
    b0 = payload[offset]
    version = b0 & 0x3F
    header_len_high = (b0 >> 6) & 0x03
    _f(table, "协议版本号", f"{version}", str(version), "取值固定为1",
       base_offset + offset, base_offset + offset)
    offset += 1

    # 字节1: 报文头长度低4位(4bit) + 控制字段(4bit)
    if offset < len(payload):
        b1 = payload[offset]
        header_len_low = b1 & 0x0F
        header_len = (header_len_high << 4) | header_len_low
        ctrl_high = (b1 >> 4) & 0x0F
        _f(table, "报文头长度", f"0x{header_len:02X}", str(header_len), "报文头（除数据域外）的长度",
           base_offset + offset, base_offset + offset)

        # 控制字段高4位的含义因报文类型不同而不同
        if direction == 0:  # 下行
            _f(table, "控制字段", f"0x{ctrl_high:02X}", str(ctrl_high), "下行控制",
               base_offset + offset, base_offset + offset)
        else:  # 上行
            # bit4=方向位, bit5=启动位/确认位, bit6-7=功能码
            direction_bit = (ctrl_high >> 3) & 0x01
            start_bit = (ctrl_high >> 2) & 0x01
            func_code = ctrl_high & 0x03
            _f(table, "控制字段", f"D[7:4]={ctrl_high:04b}",
               f"方向={'上行' if direction_bit else '下行'} 启动={'启动站' if start_bit else '从动站'} 功能码={func_code}",
               "方向位/启动位/功能码",
               base_offset + offset, base_offset + offset)
        offset += 1

    # 字节2-3: 保留/数据长度(12bit) + 控制(4bit)
    if offset + 2 <= len(payload):
        b2 = payload[offset]
        b3 = payload[offset + 1] if offset + 1 < len(payload) else 0
        data_len = ((b2 & 0x0F) << 8) | b3
        ctrl_low = (b2 >> 4) & 0x0F
        _f(table, "数据长度", f"0x{data_len:03X}", str(data_len), "数据域的长度",
           base_offset + offset, base_offset + offset + 1)
        offset += 2

    return offset, table


def _parse_meter_reading_downlink(payload: bytes, base_offset: int) -> list:
    """抄表下行报文数据域解析 (0x0001/0x0002/0x0003)"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "下行抄表数据域不足4字节", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    # 报文头
    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=0)
    table.extend(hdr)

    # 报文序号 (2字节)
    if offset + 2 <= len(payload):
        seq = _uint16_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:04X}", str(seq), "STA应答时使用该序号返回",
           base_offset + offset, base_offset + offset + 1)
        offset += 2

    # 设备超时时间 (1字节)
    if offset < len(payload):
        timeout = payload[offset]
        _f(table, "设备超时时间", f"0x{timeout:02X}", f"{timeout * 100}ms" if timeout else "0",
           "CCO指定超时，单位100ms", base_offset + offset, base_offset + offset)
        offset += 1

    # 选项字 (1字节)
    if offset < len(payload):
        opt = payload[offset]
        direction_bit = opt & 0x01
        interval = (opt >> 1) & 0x7F
        _f(table, "选项字", f"0x{opt:02X}",
           f"方向={'上行' if direction_bit else '下行'} 报文间间隔={interval * 10}ms" if interval else
           f"方向={'上行' if direction_bit else '下行'}",
           "bit0:方向位, bit1-7:报文间间隔(并发抄表时)", base_offset + offset, base_offset + offset)
        offset += 1

    # 转发数据
    if offset < len(payload):
        fwd_data = payload[offset:]
        _f(table, "转发数据(抄表报文)", _hex(fwd_data)[:80], f"{len(fwd_data)}字节",
           "终端下发给STA的抄表报文数据",
           base_offset + offset, base_offset + len(payload) - 1)

    return table


def _parse_meter_reading_uplink(payload: bytes, base_offset: int) -> list:
    """抄表上行报文数据域解析 (0x0001/0x0002/0x0003 上行应答)"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "上行抄表数据域不足4字节", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    # 报文头
    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=1)
    table.extend(hdr)

    # 报文序号 (2字节)
    if offset + 2 <= len(payload):
        seq = _uint16_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:04X}", str(seq), "与下行报文一致",
           base_offset + offset, base_offset + offset + 1)
        offset += 2

    # 应答状态 (1字节)
    if offset < len(payload):
        status = payload[offset]
        status_map = {
            0x00: "成功",
            0x01: "失败",
            0x02: "不支持",
            0x03: "参数错误",
        }
        _f(table, "应答状态", f"0x{status:02X}", status_map.get(status, f"未知({status})"),
           "抄表应答状态", base_offset + offset, base_offset + offset)
        offset += 1

    # 转发数据(抄表结果)
    if offset < len(payload):
        fwd_data = payload[offset:]
        _f(table, "转发数据(抄表结果)", _hex(fwd_data)[:80], f"{len(fwd_data)}字节",
           "STA应答的抄表结果数据",
           base_offset + offset, base_offset + len(payload) - 1)

    return table


# ── 0x0001: 终端主动抄表 ──
def _parse_terminal_meter_reading(payload: bytes, direction: int, base_offset: int) -> list:
    """终端主动抄表: 下行=抄表命令, 上行=抄表结果"""
    if direction == 0:
        return _parse_meter_reading_downlink(payload, base_offset)
    else:
        return _parse_meter_reading_uplink(payload, base_offset)


# ── 0x0002: 路由主动抄表 ──
def _parse_route_meter_reading(payload: bytes, direction: int, base_offset: int) -> list:
    """路由主动抄表: 下行=抄表命令, 上行=抄表结果"""
    if direction == 0:
        return _parse_meter_reading_downlink(payload, base_offset)
    else:
        return _parse_meter_reading_uplink(payload, base_offset)


# ── 0x0003: 终端主动并发抄表 ──
def _parse_parallel_meter_reading(payload: bytes, direction: int, base_offset: int) -> list:
    """终端主动并发抄表: 下行=抄表命令, 上行=抄表结果"""
    if direction == 0:
        return _parse_meter_reading_downlink(payload, base_offset)
    else:
        return _parse_meter_reading_uplink(payload, base_offset)


# ── 0x0004: 校时 ──
def _parse_time_sync(payload: bytes, direction: int, base_offset: int) -> list:
    """校时报文"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "校时数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    # 报文头
    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)

    # 报文序号 (2字节)
    if offset + 2 <= len(payload):
        seq = _uint16_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:04X}", str(seq), "",
           base_offset + offset, base_offset + offset + 1)
        offset += 2

    # 校时数据
    if offset < len(payload):
        time_data = payload[offset:]
        time_raw, time_parsed = _bcd_time(time_data, 0)
        if time_parsed and not time_parsed.startswith("非标准"):
            _f(table, "校时数据", time_raw, time_parsed, "BCD时间(秒在低位)",
               base_offset + offset, base_offset + len(payload) - 1)
        else:
            _f(table, "校时数据", _hex(time_data), f"{len(time_data)}字节", "校时时间数据",
               base_offset + offset, base_offset + len(payload) - 1)

    return table


# ── 0x0005: 单相业务下发 ──
def _parse_single_phase(payload: bytes, direction: int, base_offset: int) -> list:
    """单相业务下发"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4  # 跳过公共头

    # 报文序号
    if offset + 2 <= len(payload):
        seq = _uint16_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:04X}", str(seq), "",
           base_offset + offset, base_offset + offset + 1)
        offset += 2

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0006: 通信测试 ──
def _parse_comm_test(payload: bytes, direction: int, base_offset: int) -> list:
    """通信测试报文"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    # 报文序号
    if offset + 2 <= len(payload):
        seq = _uint16_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:04X}", str(seq), "",
           base_offset + offset, base_offset + offset + 1)
        offset += 2

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0008: 事件上报 ──
_EVENT_TYPE_MAP = {
    0x01: "电能表事件",
    0x02: "停复电事件(位图)",
    0x03: "停复电事件(地址)",
    0x04: "即装即采事件",
}

_FUNC_CODE_MAP = {
    (0, 1): "CCO应答确认",
    (0, 2): "CCO下发允许事件主动上报",
    (0, 3): "CCO下发禁止事件主动上报",
    (0, 4): "CCO应答事件缓存区满",
    (1, 1): "STA主动上报事件(电表触发)",
    (1, 2): "STA主动上报事件(模块触发)",
    (1, 3): "STA主动上报事件(采集器触发)",
}


def _parse_event_report(payload: bytes, direction: int, base_offset: int) -> list:
    """事件上报报文"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "事件数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    # 报文头
    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4  # 跳过4字节公共头

    # 报文序号 (2字节)
    if offset + 2 <= len(payload):
        seq = _uint16_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:04X}", str(seq), "STA分配，递增",
           base_offset + offset, base_offset + offset + 1)
        offset += 2

    # 电能表地址 (6字节)
    if offset + 6 <= len(payload):
        addr_raw, addr = _mac_addr(payload, offset)
        _f(table, "电能表地址", addr_raw, addr, "发生事件的电能表地址",
           base_offset + offset, base_offset + offset + 5)
        offset += 6

    # 事件数据
    if offset < len(payload):
        evt_data = payload[offset:]
        _f(table, "事件数据", _hex(evt_data)[:80], f"{len(evt_data)}字节", "事件上报数据内容",
           base_offset + offset, base_offset + len(payload) - 1)

    return table


# ── 0x0011: 查询从节点主动注册 ──
_UPLINK_HEADER_LEN = 36  # 表7: 上行固定头长度
_DOWNLINK_HEADER_LEN = 20  # 表6: 下行固定头长度


def _parse_query_node_registration(payload: bytes, direction: int, base_offset: int) -> list:
    """查询从节点主动注册:
    下行(表6): CCO查询STA注册结果, 头20字节
    上行(表7): STA上报注册结果, 头36字节 + 电能表列表
    """
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    # 字节0: 协议版本号(6bit) + 报文头长度高2位(2bit)
    b0 = payload[0]
    version = b0 & 0x3F
    _f(table, "协议版本号", f"{version}", str(version), "取值固定为1",
       base_offset, base_offset)

    # 字节1: 报文头长度低4位(4bit) + 控制(4bit)
    b1 = payload[1]
    ctrl = (b1 >> 4) & 0x0F  # 高4位=控制
    offset = 2

    # --- 根据方向使用协议固定头长度 ---
    if direction == 0:  # 下行 (表6)
        # 协议版本号 + 报文头长度 = 20
        force_resp = (ctrl >> 3) & 0x01
        reg_param = ctrl & 0x07
        _f(table, "强制应答标志", f"{'1' if force_resp else '0'}",
           "强制应答" if force_resp else "STA搜表完成应答", "",
           base_offset + 1, base_offset + 1)
        _f(table, "从节点注册参数", f"0x{reg_param:02X}", str(reg_param), "取值固定为0",
           base_offset + 1, base_offset + 1)

        # 保留 (2字节)
        hdr_end = base_offset + _DOWNLINK_HEADER_LEN
        if offset + 2 <= len(payload):
            _f(table, "保留", _hex(payload[offset:offset + 2]), "2字节", "保留",
               base_offset + offset, base_offset + offset + 1)
            offset += 2

        # 报文序号 (4字节, 小端)
        if offset + 4 <= len(payload):
            seq = _uint32_le(payload, offset)
            _f(table, "报文序号", f"0x{seq:08X}", str(seq), "序号递增，重发不变",
               base_offset + offset, base_offset + offset + 3)
            offset += 4

        # 源MAC地址 (6字节)
        if offset + 6 <= len(payload):
            addr_raw, addr = _mac_addr(payload, offset)
            _f(table, "源MAC地址", addr_raw, addr, "CCO的MAC地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6

        # 目的MAC地址 (6字节)
        if offset + 6 <= len(payload):
            addr_raw, addr = _mac_addr(payload, offset)
            _f(table, "目的MAC地址", addr_raw, addr, "待查询站点的MAC地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6

    else:  # 上行 (表7)
        # 状态字段(bit4) + 从节点注册参数(bit5-7)
        searching = (ctrl >> 3) & 0x01
        reg_param = ctrl & 0x07
        _f(table, "状态字段", f"{'1' if searching else '0'}",
           "STA正在搜表" if searching else "STA搜表完成", "",
           base_offset + 1, base_offset + 1)
        _f(table, "从节点注册参数", f"0x{reg_param:02X}", str(reg_param), "取值固定为0",
           base_offset + 1, base_offset + 1)

        # 电能表数量 (1字节)
        if offset < len(payload):
            meter_count = payload[offset]
            _f(table, "电能表数量", f"0x{meter_count:02X}", str(meter_count), "STA搜到的电表数量",
               base_offset + offset, base_offset + offset)
            offset += 1

        # 产品类型 (1字节)
        if offset < len(payload):
            prod_type = payload[offset]
            prod_map = {0: "电能表", 1: "I型采集器", 2: "II型采集器"}
            _f(table, "产品类型", f"0x{prod_type:02X}", prod_map.get(prod_type, f"保留({prod_type})"),
               "", base_offset + offset, base_offset + offset)
            offset += 1

        # 设备地址 (6字节)
        if offset + 6 <= len(payload):
            addr_raw, addr = _mac_addr(payload, offset)
            _f(table, "设备地址", addr_raw, addr, "电能表/采集器地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6

        # 设备ID (6字节)
        if offset + 6 <= len(payload):
            addr_raw, addr = _mac_addr(payload, offset)
            _f(table, "设备ID", addr_raw, addr, "STA本身唯一地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6

        # 报文序号 (4字节, 小端)
        if offset + 4 <= len(payload):
            seq = _uint32_le(payload, offset)
            _f(table, "报文序号", f"0x{seq:08X}", str(seq), "应与下行报文一致",
               base_offset + offset, base_offset + offset + 3)
            offset += 4

        # 保留 (4字节)
        if offset + 4 <= len(payload):
            _f(table, "保留", _hex(payload[offset:offset + 4]), "4字节", "保留",
               base_offset + offset, base_offset + offset + 3)
            offset += 4

        # 源MAC地址 (6字节)
        if offset + 6 <= len(payload):
            addr_raw, addr = _mac_addr(payload, offset)
            _f(table, "源MAC地址", addr_raw, addr, "发送站点MAC地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6

        # 目的MAC地址 (6字节)
        if offset + 6 <= len(payload):
            addr_raw, addr = _mac_addr(payload, offset)
            _f(table, "目的MAC地址", addr_raw, addr, "CCO的MAC地址",
               base_offset + offset, base_offset + offset + 5)
            offset += 6

        # 剩余数据：电能表列表（每表8字节: 6字节地址+1字节协议+1字节保留）
        if offset < len(payload):
            remaining = payload[offset:]
            rem_count = len(remaining) // 8
            if rem_count > 0:
                _f(table, "电能表列表", f"{len(remaining)}字节", f"{rem_count}个电能表",
                   "", base_offset + offset, base_offset + len(payload) - 1)
                for i in range(rem_count):
                    ent_offset = offset + i * 8
                    if ent_offset + 8 <= len(payload):
                        entry = payload[ent_offset:ent_offset + 8]
                        addr_raw, addr = _mac_addr(entry, 0)
                        proto = entry[6]
                        proto_map = {0x00: "透明传输", 0x01: "DL/T645-1997", 0x02: "DL/T645-2007", 0x03: "DL/T698.45"}
                        proto_name = proto_map.get(proto, f"0x{proto:02X}")
                        status = entry[7]
                        _f(table, f"  电能表{i+1}", f"{addr_raw} 协议={proto_name}",
                           addr, f"协议:{proto_name} 状态:0x{status:02X}",
                           base_offset + ent_offset, base_offset + ent_offset + 7)
                offset += rem_count * 8  # 更新offset跳过已解析的列表

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0012: 启动从节点主动注册 ──
def _parse_start_node_registration(payload: bytes, direction: int, base_offset: int) -> list:
    """启动从节点主动注册: 下行=启动命令, 上行=确认/否认"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    # 报文头
    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    # 报文序号
    if offset + 4 <= len(payload):
        seq = _uint32_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:08X}", str(seq), "序号递增，重发不变",
           base_offset + offset, base_offset + offset + 3)
        offset += 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0013: 停止从节点主动注册 ──
def _parse_stop_node_registration(payload: bytes, direction: int, base_offset: int) -> list:
    """停止从节点主动注册: 下行=停止命令, 上行=确认"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    # 报文头
    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    # 报文序号
    if offset + 4 <= len(payload):
        seq = _uint32_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:08X}", str(seq), "序号递增，重发不变",
           base_offset + offset, base_offset + offset + 3)
        offset += 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0020: 确认/否认 ──
def _parse_confirm_deny(payload: bytes, direction: int, base_offset: int) -> list:
    """确认/否认报文"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "确认/否认数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    # 报文头
    b0 = payload[0]
    version = b0 & 0x3F
    _f(table, "协议版本号", f"{version}", str(version), "取值固定为1",
       base_offset, base_offset)

    b1 = payload[1]
    header_len_low = b1 & 0x0F
    header_len_high = (b0 >> 6) & 0x03
    header_len = (header_len_high << 4) | header_len_low
    ctrl_high = (b1 >> 4) & 0x0F

    _f(table, "报文头长度", f"{header_len}", str(header_len), "报文头长度",
       base_offset + 1, base_offset + 1)

    # 方向位 + 确认位
    direction_bit = (ctrl_high >> 3) & 0x01
    confirm_bit = (ctrl_high >> 2) & 0x01
    _f(table, "方向位", f"{direction_bit}", "上行" if direction_bit else "下行", "",
       base_offset + 1, base_offset + 1)
    _f(table, "确认位", f"{confirm_bit}", "确认" if confirm_bit else "否认", "",
       base_offset + 1, base_offset + 1)
    offset = 2

    # 保留 (2字节)
    if offset + 2 <= len(payload):
        _f(table, "保留", _hex(payload[offset:offset+2]), "2字节", "保留",
           base_offset + offset, base_offset + offset + 1)
        offset += 2

    # 报文序号 (2字节)
    if offset + 2 <= len(payload):
        seq = _uint16_le(payload, offset)
        _f(table, "报文序号", f"0x{seq:04X}", str(seq), "应答时使用该序号返回",
           base_offset + offset, base_offset + offset + 1)
        offset += 2

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0030: 开始升级 ──
def _parse_start_upgrade(payload: bytes, direction: int, base_offset: int) -> list:
    """开始升级报文"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    # 报文头
    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    # 升级ID (4字节)
    if offset + 4 <= len(payload):
        upgrade_id = _uint32_le(payload, offset)
        _f(table, "升级ID", f"0x{upgrade_id:08X}", str(upgrade_id),
           "区分每次升级，不应重复且不为0", base_offset + offset, base_offset + offset + 3)
        offset += 4

    # 升级时间窗 (2字节)
    if offset + 2 <= len(payload):
        time_window = _uint16_le(payload, offset)
        _f(table, "升级时间窗", f"0x{time_window:04X}", f"{time_window}分钟",
           "升级过程最长时间", base_offset + offset, base_offset + offset + 1)
        offset += 2

    # 升级块大小 (2字节)
    if offset + 2 <= len(payload):
        block_size = _uint16_le(payload, offset)
        _f(table, "升级块大小", f"0x{block_size:04X}", f"{block_size}字节",
           "允许取值: 100/200/300/400", base_offset + offset, base_offset + offset + 1)
        offset += 2

    # 升级文件大小 (4字节)
    if offset + 4 <= len(payload):
        file_size = _uint32_le(payload, offset)
        _f(table, "升级文件大小", f"0x{file_size:08X}", f"{file_size}字节",
           "升级文件包含的字节数", base_offset + offset, base_offset + offset + 3)
        offset += 4

    # 文件CRC校验 (4字节)
    if offset + 4 <= len(payload):
        crc = _uint32_le(payload, offset)
        _f(table, "文件CRC校验", f"0x{crc:08X}", f"0x{crc:08X}",
           "文件所有内容的CRC-32校验", base_offset + offset, base_offset + offset + 3)
        offset += 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0031: 停止升级 ──
def _parse_stop_upgrade(payload: bytes, direction: int, base_offset: int) -> list:
    """停止升级报文"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    # 升级ID (4字节)
    if offset + 4 <= len(payload):
        upgrade_id = _uint32_le(payload, offset)
        _f(table, "升级ID", f"0x{upgrade_id:08X}", str(upgrade_id),
           "使用0作为通用升级ID终止本次升级", base_offset + offset, base_offset + offset + 3)
        offset += 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0032: 传输文件数据 ──
def _parse_file_transfer(payload: bytes, direction: int, base_offset: int) -> list:
    """传输文件数据报文"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    # 升级ID (4字节)
    if offset + 4 <= len(payload):
        upgrade_id = _uint32_le(payload, offset)
        _f(table, "升级ID", f"0x{upgrade_id:08X}", str(upgrade_id), "",
           base_offset + offset, base_offset + offset + 3)
        offset += 4

    # 块序号 (4字节)
    if offset + 4 <= len(payload):
        block_seq = _uint32_le(payload, offset)
        _f(table, "块序号", f"0x{block_seq:08X}", str(block_seq), "当前数据块序号",
           base_offset + offset, base_offset + offset + 3)
        offset += 4

    # 文件数据
    if offset < len(payload):
        file_data = payload[offset:]
        _f(table, "文件数据", _hex(file_data)[:80], f"{len(file_data)}字节",
           "升级文件数据块", base_offset + offset, base_offset + len(payload) - 1)

    return table


# ── 0x0033: 传输文件数据(单播转本地广播) ──
def _parse_file_transfer_broadcast(payload: bytes, direction: int, base_offset: int) -> list:
    """传输文件数据(单播转本地广播) - 同 0x0032"""
    return _parse_file_transfer(payload, direction, base_offset)


# ── 0x0034: 查询站点升级状态 ──
def _parse_query_upgrade_status(payload: bytes, direction: int, base_offset: int) -> list:
    """查询站点升级状态"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    # 升级ID (4字节)
    if offset + 4 <= len(payload):
        upgrade_id = _uint32_le(payload, offset)
        _f(table, "升级ID", f"0x{upgrade_id:08X}", str(upgrade_id),
           "STA不在升级状态时回复0", base_offset + offset, base_offset + offset + 3)
        offset += 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0035: 执行升级 ──
def _parse_execute_upgrade(payload: bytes, direction: int, base_offset: int) -> list:
    """执行升级报文"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    # 升级ID (4字节)
    if offset + 4 <= len(payload):
        upgrade_id = _uint32_le(payload, offset)
        _f(table, "升级ID", f"0x{upgrade_id:08X}", str(upgrade_id), "",
           base_offset + offset, base_offset + offset + 3)
        offset += 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x0036: 查询站点信息 ──
def _parse_query_site_info(payload: bytes, direction: int, base_offset: int) -> list:
    """查询站点信息"""
    table = []
    offset = 0

    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, offset, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x00A0: 鉴权安全 ──
def _parse_auth_security(payload: bytes, direction: int, base_offset: int) -> list:
    """鉴权安全报文"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x00A1: 台区户变关系识别 ──
def _parse_district_transformer(payload: bytes, direction: int, base_offset: int) -> list:
    """台区户变关系识别"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x00A2: 查询ID信息 ──
def _parse_query_id_info(payload: bytes, direction: int, base_offset: int) -> list:
    """查询ID信息"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x00A3: 精准校时 ──
def _parse_precise_time_sync(payload: bytes, direction: int, base_offset: int) -> list:
    """精准校时报文"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    # 精准校时数据
    if offset < len(payload):
        time_data = payload[offset:]
        time_raw, time_parsed = _bcd_time(time_data, 0)
        if time_parsed and not time_parsed.startswith("非标准"):
            _f(table, "校时数据", time_raw, time_parsed, "BCD时间",
               base_offset + offset, base_offset + len(payload) - 1)
        else:
            _f(table, "校时数据", _hex(time_data)[:80], f"{len(time_data)}字节", "校时数据",
               base_offset + offset, base_offset + len(payload) - 1)

    return table


# ── 0x00A4: 配电信息上报 ──
def _parse_power_distribution_report(payload: bytes, direction: int, base_offset: int) -> list:
    """配电信息上报"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x00E2: 分钟采集任务配置 ──
def _parse_minute_task_config(payload: bytes, direction: int, base_offset: int) -> list:
    """分钟采集任务配置"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x00E3: 分钟采集任务数据读取 ──
def _parse_minute_task_read(payload: bytes, direction: int, base_offset: int) -> list:
    """分钟采集任务数据读取"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x00E5: 多用户应用聚合帧 ──
def _parse_multi_user_aggregation(payload: bytes, direction: int, base_offset: int) -> list:
    """多用户应用聚合帧"""
    table = []
    if len(payload) < 4:
        _f(table, "❌ 数据不足", "", "", "数据域不足", base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table

    offset, hdr = _parse_meter_common_header(payload, 0, base_offset, direction=direction)
    table.extend(hdr)
    offset = 4

    _remaining(table, payload, offset, base_offset)
    return table


# ── 公共入口 ──
def parse_command_payload(
    payload: bytes,
    msg_id: int,
    direction: int,
    msg_port: int,
    base_offset: int
) -> list:
    """解析应用层业务数据单元

    Args:
        payload: 业务数据（不含报文端口号/报文ID/报文控制字）
        msg_id: 报文ID (已解码)
        direction: 方向 (0=下行, 1=上行)
        msg_port: 报文端口号
        base_offset: 基础偏移量（用于高亮定位）

    Returns:
        [(field, raw, parsed, desc, byte_start, byte_end), ...]
    """
    parsers = {
        0x0001: _parse_terminal_meter_reading,
        0x0002: _parse_route_meter_reading,
        0x0003: _parse_parallel_meter_reading,
        0x0004: _parse_time_sync,
        0x0005: _parse_single_phase,
        0x0006: _parse_comm_test,
        0x0008: _parse_event_report,
        0x0011: _parse_query_node_registration,
        0x0012: _parse_start_node_registration,
        0x0013: _parse_stop_node_registration,
        0x0020: _parse_confirm_deny,
        0x0030: _parse_start_upgrade,
        0x0031: _parse_stop_upgrade,
        0x0032: _parse_file_transfer,
        0x0033: _parse_file_transfer_broadcast,
        0x0034: _parse_query_upgrade_status,
        0x0035: _parse_execute_upgrade,
        0x0036: _parse_query_site_info,
        0x00A0: _parse_auth_security,
        0x00A1: _parse_district_transformer,
        0x00A2: _parse_query_id_info,
        0x00A3: _parse_precise_time_sync,
        0x00A4: _parse_power_distribution_report,
        0x00E2: _parse_minute_task_config,
        0x00E3: _parse_minute_task_read,
        0x00E5: _parse_multi_user_aggregation,
    }
    parser = parsers.get(msg_id)
    if parser:
        return parser(payload, direction, base_offset)
    return []
