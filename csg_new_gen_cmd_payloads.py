# -*- coding: utf-8 -*-
"""
新一代载波协议（通感一体化）应用层命令帧业务数据单元解析
依据《通感一体化低压电力线宽带载波通信规约 第5部分 应用层通信协议》
"""
from typing import List, Tuple


def _hex(data: bytes) -> str:
    return ' '.join(f'{b:02X}' for b in data)


def _mac_addr(data: bytes, offset: int) -> Tuple[str, str]:
    """解析 6 字节 MAC 地址（小端序存储 -> 显示按传输顺序）"""
    if offset + 6 > len(data):
        return "", ""
    addr = data[offset:offset + 6]
    raw = _hex(addr)
    colon = ':'.join(f'{b:02X}' for b in addr)
    return raw, colon


def _mac_addr_be(data: bytes, offset: int) -> Tuple[str, str]:
    """解析 6 字节 MAC 地址（大端序存储）"""
    if offset + 6 > len(data):
        return "", ""
    addr = data[offset:offset + 6]
    raw = _hex(addr)
    colon = ':'.join(f'{b:02X}' for b in addr)
    return raw, colon


def _uint16_le(data: bytes, offset: int) -> int:
    if offset + 2 > len(data):
        return 0
    return int.from_bytes(data[offset:offset + 2], 'little')


def _uint32_le(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        return 0
    return int.from_bytes(data[offset:offset + 4], 'little')


def _bcd6(data: bytes, offset: int) -> Tuple[str, str]:
    """解析 6 字节 BCD 时间，秒在低位，返回 (原始hex, 格式化字符串)"""
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


# ── 通用工具：追加字段 ──
def _f(table: list, name: str, raw: str, parsed: str, desc: str, start: int, end: int):
    table.append((name, raw, parsed, desc, start, end))


def _remaining(table: list, data: bytes, offset: int, base_offset: int):
    if offset < len(data):
        rem = data[offset:]
        _f(table, "剩余数据", _hex(rem), f"{len(rem)}字节", "未解析数据",
           base_offset + offset, base_offset + len(data) - 1)


# ── 0x00: 查询终端搜索结果 / 0x01: 下发搜索终端列表 ──
_PROTOCOL_TYPE_MAP = {
    0x01: "DL/T 645-1997",
    0x02: "DL/T 645-2007",
    0x03: "CJ/T 188",
}


def _parse_terminal_info_list(data: bytes, offset: int, base_offset: int, count: int) -> Tuple[int, list]:
    table = []
    for i in range(count):
        if offset + 8 > len(data):
            _f(table, f"  终端{i+1}", "", "", "数据不足", base_offset + offset, base_offset + len(data) - 1)
            break
        addr_raw, addr = _mac_addr(data, offset)
        proto = data[offset + 6]
        proto_desc = _PROTOCOL_TYPE_MAP.get(proto, f"保留(0x{proto:02X})")
        _f(table, f"  终端{i+1}地址", addr_raw, addr, f"终端地址: {addr}",
           base_offset + offset, base_offset + offset + 5)
        _f(table, f"  终端{i+1}规约类型", f"0x{proto:02X}", str(proto), proto_desc,
           base_offset + offset + 6, base_offset + offset + 6)
        _f(table, f"  终端{i+1}保留", f"0x{data[offset+7]:02X}", str(data[offset+7]), "保留",
           base_offset + offset + 7, base_offset + offset + 7)
        offset += 8
    return offset, table


def _parse_cmd_search_result(payload: bytes, direction: int, base_offset: int) -> list:
    """0x00 查询终端搜索结果"""
    table = []
    offset = 0
    if direction == 0:
        _f(table, "下行负载", "", "", "查询终端搜索结果下行业务无数据单元",
           base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table
    if len(payload) < 1:
        _f(table, "❌ 解析失败", "", "", "上行业务数据不足", None, None)
        return table
    count = payload[offset]
    _f(table, "终端数量", f"0x{count:02X}", str(count), "搜索到的终端数量",
       base_offset + offset, base_offset + offset)
    offset += 1
    if offset + 3 <= len(payload):
        _f(table, "保留", _hex(payload[offset:offset+3]), "3字节", "保留，默认填0",
           base_offset + offset, base_offset + offset + 2)
        offset += 3
    offset, sub = _parse_terminal_info_list(payload, offset, base_offset + offset, count)
    table.extend(sub)
    _remaining(table, payload, offset, base_offset)
    return table


def _parse_cmd_send_search_list(payload: bytes, direction: int, base_offset: int) -> list:
    """0x01 下发搜索终端列表"""
    table = []
    offset = 0
    if direction == 1:
        _f(table, "上行负载", "", "", "下发搜索终端列表上行为确认/否认，无数据单元",
           base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table
    if len(payload) < 1:
        _f(table, "❌ 解析失败", "", "", "下行业务数据不足", None, None)
        return table
    count = payload[offset]
    _f(table, "终端数量", f"0x{count:02X}", str(count), "下发的终端数量",
       base_offset + offset, base_offset + offset)
    offset += 1
    if offset + 3 <= len(payload):
        _f(table, "保留", _hex(payload[offset:offset+3]), "3字节", "保留，默认填0",
           base_offset + offset, base_offset + offset + 2)
        offset += 3
    offset, sub = _parse_terminal_info_list(payload, offset, base_offset + offset, count)
    table.extend(sub)
    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x02: 文件传输 ──
_FILE_TRANSFER_INFO_ID_MAP = {
    0x00: "下发文件信息",
    0x01: "下发文件数据",
    0x02: "查询文件数据包接收状态",
    0x03: "文件传输完成通知",
    0x04: "文件数据本地广播转发",
}

_FILE_NATURE_MAP = {
    0x00: "清除下装",
    0x02: "从节点模块文件",
    0x03: "采集器文件",
    0x04: "终端文件",
}

_FILE_STATUS_MAP = {
    0x00: "空闲",
    0x01: "文件正在CCO和STA之间传输",
    0x02: "文件已被STA正确接收",
    0x05: "文件传输成功，文件已传送至最终目的设备",
    0x06: "文件传输失败，文件无法传送至最终目的设备",
}


def _parse_cmd_file_transfer(payload: bytes, direction: int, base_offset: int) -> list:
    """0x02 文件传输"""
    table = []
    if direction == 1:
        # 上行应答/状态：无固定信息ID，按长度做最可能解析
        if len(payload) >= 4:
            file_id = _uint32_le(payload, 0)
            _f(table, "文件传输ID", _hex(payload[0:4]), f"0x{file_id:08X}", "文件传输标识",
               base_offset, base_offset + 3)
            rest = payload[4:]
            if len(rest) == 4:
                # 可能是文件数据应答（结果码4字节）或完成应答
                result = _uint32_le(rest, 0)
                _f(table, "结果码", _hex(rest), f"0x{result:08X}", "0表示成功",
                   base_offset + 4, base_offset + 7)
            elif len(rest) == 4:
                # 文件信息应答：结果码2 + 错误码2
                rc = _uint16_le(rest, 0)
                ec = _uint16_le(rest, 2)
                _f(table, "结果码", _hex(rest[0:2]), str(rc), "0表示成功",
                   base_offset + 4, base_offset + 5)
                _f(table, "错误代码", _hex(rest[2:4]), str(ec), "0表示无错误",
                   base_offset + 6, base_offset + 7)
            elif len(rest) >= 4:
                # 查询包接收状态应答
                start_seg = _uint16_le(rest, 0)
                _f(table, "起始段号", _hex(rest[0:2]), str(start_seg), "与下行报文一致",
                   base_offset + 4, base_offset + 5)
                if len(rest) >= 4:
                    status = rest[2]
                    status_desc = _FILE_STATUS_MAP.get(status, f"保留(0x{status:02X})")
                    _f(table, "文件传输状态", f"0x{status:02X}", str(status), status_desc,
                       base_offset + 6, base_offset + 6)
                    _f(table, "保留", f"0x{rest[3]:02X}", str(rest[3]), "保留字节",
                       base_offset + 7, base_offset + 7)
                    bitmap = rest[4:]
                    if bitmap:
                        _f(table, "连续文件段状态位图", _hex(bitmap), f"{len(bitmap)}字节",
                           "每bit表示一个文件段接收状态（1=已接收）",
                           base_offset + 8, base_offset + 7 + len(bitmap))
            else:
                _remaining(table, payload, 4, base_offset)
        else:
            _remaining(table, payload, 0, base_offset)
        return table

    if len(payload) < 4:
        _f(table, "❌ 解析失败", "", "", "文件传输下行数据不足", None, None)
        return table

    info_id = payload[0]
    info_name = _FILE_TRANSFER_INFO_ID_MAP.get(info_id, f"保留(0x{info_id:02X})")
    _f(table, "文件传输信息ID", f"0x{info_id:02X}", str(info_id), f"文件传输子消息: {info_name}",
       base_offset, base_offset)
    _f(table, "保留", _hex(payload[1:4]), "3字节", "保留，默认填0",
       base_offset + 1, base_offset + 3)
    offset = 4

    if info_id == 0x00:  # 下发文件信息
        if offset + 24 <= len(payload):
            nature = payload[offset]
            _f(table, "文件性质", f"0x{nature:02X}", str(nature),
               _FILE_NATURE_MAP.get(nature, f"保留(0x{nature:02X})"),
               base_offset + offset, base_offset + offset)
            _f(table, "保留", f"0x{payload[offset+1]:02X}", str(payload[offset+1]), "保留",
               base_offset + offset + 1, base_offset + offset + 1)
            addr_raw, addr = _mac_addr(payload, offset + 2)
            _f(table, "目的地址", addr_raw, addr, f"广播时填999999999999: {addr}",
               base_offset + offset + 2, base_offset + offset + 7)
            crc = _uint32_le(payload, offset + 8)
            _f(table, "文件总校验(CRC32)", _hex(payload[offset+8:offset+12]), f"0x{crc:08X}",
               "文件所有内容的CRC32校验和",
               base_offset + offset + 8, base_offset + offset + 11)
            size = _uint32_le(payload, offset + 12)
            _f(table, "文件大小", _hex(payload[offset+12:offset+16]), str(size), "文件总长度，单位字节",
               base_offset + offset + 12, base_offset + offset + 15)
            segs = _uint16_le(payload, offset + 16)
            _f(table, "文件总段数", _hex(payload[offset+16:offset+18]), str(segs), "文件传输内容总段数",
               base_offset + offset + 16, base_offset + offset + 17)
            tw = _uint16_le(payload, offset + 18)
            _f(table, "文件传输时间窗", _hex(payload[offset+18:offset+20]), str(tw), "单位：分钟",
               base_offset + offset + 18, base_offset + offset + 19)
            fid = _uint32_le(payload, offset + 20)
            _f(table, "文件传输ID", _hex(payload[offset+20:offset+24]), f"0x{fid:08X}", "CCO生成的文件传输标识",
               base_offset + offset + 20, base_offset + offset + 23)
            offset += 24
    elif info_id in (0x01, 0x04):  # 下发文件数据 / 本地广播转发
        if offset + 10 <= len(payload):
            seg_no = _uint16_le(payload, offset)
            total = _uint16_le(payload, offset + 2)
            fid = _uint32_le(payload, offset + 4)
            seg_len = _uint16_le(payload, offset + 8)
            _f(table, "文件段号", _hex(payload[offset:offset+2]), str(seg_no), "传输段序号，从0开始",
               base_offset + offset, base_offset + offset + 1)
            _f(table, "文件总段数", _hex(payload[offset+2:offset+4]), str(total), "文件传输内容总段数",
               base_offset + offset + 2, base_offset + offset + 3)
            _f(table, "文件传输ID", _hex(payload[offset+4:offset+8]), f"0x{fid:08X}", "文件传输标识",
               base_offset + offset + 4, base_offset + offset + 7)
            _f(table, "文件段长度", _hex(payload[offset+8:offset+10]), str(seg_len), "该段文件内容长度",
               base_offset + offset + 8, base_offset + offset + 9)
            offset += 10
            if seg_len > 0 and offset + seg_len <= len(payload):
                _f(table, "文件段内容", _hex(payload[offset:offset+seg_len][:30]) + ("..." if seg_len > 30 else ""),
                   f"{seg_len}字节", "传输的文件段数据",
                   base_offset + offset, base_offset + offset + seg_len - 1)
                offset += seg_len
    elif info_id == 0x02:  # 查询文件数据包接收状态
        if offset + 8 <= len(payload):
            fid = _uint32_le(payload, offset)
            start = _uint16_le(payload, offset + 4)
            n = _uint16_le(payload, offset + 6)
            _f(table, "文件传输ID", _hex(payload[offset:offset+4]), f"0x{fid:08X}", "文件传输标识",
               base_offset + offset, base_offset + offset + 3)
            _f(table, "起始段号", _hex(payload[offset+4:offset+6]), str(start), "查询的起始段号，从0开始",
               base_offset + offset + 4, base_offset + offset + 5)
            _f(table, "连续N个文件段状态位", _hex(payload[offset+6:offset+8]), str(n),
               "查询的段个数，0xFFFF表示查询所有包状态",
               base_offset + offset + 6, base_offset + offset + 7)
            offset += 8
    elif info_id == 0x03:  # 文件传输完成通知
        if offset + 6 <= len(payload):
            fid = _uint32_le(payload, offset)
            delay = _uint16_le(payload, offset + 4)
            _f(table, "文件传输ID", _hex(payload[offset:offset+4]), f"0x{fid:08X}", "文件传输标识",
               base_offset + offset, base_offset + offset + 3)
            _f(table, "延时启用时间", _hex(payload[offset+4:offset+6]), str(delay), "单位：秒；0表示立即启用",
               base_offset + offset + 4, base_offset + offset + 5)
            offset += 6

    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x03: 允许/禁止从节点事件 ──
_EVENT_FLAG_MAP = {
    0x00: "禁止主动上报",
    0x01: "允许主动上报",
}


def _parse_cmd_event_control(payload: bytes, direction: int, base_offset: int) -> list:
    table = []
    if direction == 1:
        _f(table, "上行负载", "", "", "允许/禁止从节点事件上行为确认/否认，无数据单元",
           base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table
    if len(payload) < 1:
        _f(table, "❌ 解析失败", "", "", "下行业务数据不足", None, None)
        return table
    flag = payload[0]
    _f(table, "从节点事件标识", f"0x{flag:02X}", str(flag),
       _EVENT_FLAG_MAP.get(flag, f"保留(0x{flag:02X})"),
       base_offset, base_offset)
    if len(payload) >= 4:
        _f(table, "保留", _hex(payload[1:4]), "3字节", "保留，默认填0",
           base_offset + 1, base_offset + 3)
    _remaining(table, payload, 4, base_offset)
    return table


# ── 0x04: 从节点重启 ──
def _parse_cmd_node_restart(payload: bytes, direction: int, base_offset: int) -> list:
    table = []
    if direction == 1:
        _f(table, "上行负载", "", "", "从节点重启上行为确认/否认，无数据单元",
           base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table
    if len(payload) < 1:
        _f(table, "❌ 解析失败", "", "", "下行业务数据不足", None, None)
        return table
    delay = payload[0]
    desc = "立即重启" if delay == 0 else f"延时{delay}秒后重启"
    _f(table, "延时重启时间", f"0x{delay:02X}", str(delay), desc,
       base_offset, base_offset)
    if len(payload) >= 4:
        _f(table, "保留", _hex(payload[1:4]), "3字节", "保留，默认填0",
           base_offset + 1, base_offset + 3)
    _remaining(table, payload, 4, base_offset)
    return table


# ── 0x05: 从节点信息查询 ──
_NODE_INFO_ELEMENT_MAP = {
    0x00: ("厂商代码", 2, "ASCII"),
    0x01: ("软件版本信息(模块)", 2, "BCD"),
    0x02: ("Bootloader版本号", 1, "BIN"),
    0x03: ("升级文件CRC32", 4, "BIN"),
    0x04: ("升级文件长度", 4, "BIN"),
    0x05: ("芯片厂商代码", 2, "ASCII"),
    0x06: ("固件发布日期(模块)", 3, "BIN"),
    0x07: ("文件传输扩展状态字", 8, "BIN"),
    0x08: ("模块出厂MAC地址", 6, "BIN"),
    0x09: ("硬件版本信息(模块)", 2, "BCD"),
    0x0A: ("硬件发布日期(模块)", 3, "BIN"),
    0x0B: ("软件版本号(芯片)", 2, "BCD"),
    0x0C: ("软件发布日期(芯片)", 3, "BIN"),
    0x0D: ("硬件版本号(芯片)", 2, "BCD"),
    0x0E: ("硬件发布日期(芯片)", 3, "BIN"),
    0x0F: ("应用程序版本号", 2, "BCD"),
    0x10: ("通信模块资产编码", 24, "BIN"),
    0x11: ("设备信息", 2, "BIN"),
    0x12: ("新一代特性", 1, "BIN"),
}


def _parse_node_info_element(payload: bytes, offset: int, base_offset: int) -> Tuple[int, list]:
    table = []
    if offset + 2 > len(payload):
        return offset, table
    elem_id = payload[offset]
    elem_len = payload[offset + 1]
    name, default_len, fmt = _NODE_INFO_ELEMENT_MAP.get(elem_id, (f"厂家自定义/保留(0x{elem_id:02X})", elem_len, "BIN"))
    _f(table, "  元素ID", f"0x{elem_id:02X}", str(elem_id), name,
       base_offset + offset, base_offset + offset)
    _f(table, "  元素长度", f"0x{elem_len:02X}", str(elem_len), f"{elem_len}字节",
       base_offset + offset + 1, base_offset + offset + 1)
    offset += 2
    if elem_len > 0 and offset + elem_len <= len(payload):
        data = payload[offset:offset + elem_len]
        raw = _hex(data)
        parsed = raw
        if fmt == "ASCII":
            try:
                parsed = data.decode('ascii', errors='replace')
            except Exception:
                pass
        elif fmt == "BCD" and elem_len == 2:
            parsed = f"BCD: {_hex(data)}"
        elif elem_id == 0x08 and elem_len == 6:
            _, parsed = _mac_addr(data, 0)
        elif elem_id == 0x11 and elem_len == 2:
            proto = data[0]
            dev_type = data[1]
            proto_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45"}
            parsed = f"协议类型:{proto_map.get(proto, f'保留(0x{proto:02X})')}, 设备类型:0x{dev_type:02X}"
        _f(table, "  元素数据", raw if len(raw) <= 30 else raw[:30] + "...", parsed, f"{name}数据",
           base_offset + offset, base_offset + offset + elem_len - 1)
        offset += elem_len
    return offset, table


def _parse_cmd_node_info_query(payload: bytes, direction: int, base_offset: int) -> list:
    table = []
    if len(payload) < 1:
        _f(table, "❌ 解析失败", "", "", "从节点信息查询数据不足", None, None)
        return table
    offset = 0
    count = payload[offset]
    _f(table, "信息列表元素数量", f"0x{count:02X}", str(count), "信息列表中元素数量",
       base_offset + offset, base_offset + offset)
    offset += 1
    if direction == 0:  # 下行：只有ID列表
        for i in range(count):
            if offset >= len(payload):
                break
            elem_id = payload[offset]
            name, _, _ = _NODE_INFO_ELEMENT_MAP.get(elem_id, (f"保留/自定义(0x{elem_id:02X})", 0, "BIN"))
            _f(table, f"  查询元素{i+1}ID", f"0x{elem_id:02X}", str(elem_id), name,
               base_offset + offset, base_offset + offset)
            offset += 1
    else:  # 上行：ID+长度+数据
        for i in range(count):
            if offset >= len(payload):
                break
            offset, sub = _parse_node_info_element(payload, offset, base_offset)
            table.extend(sub)
    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x06: 下发通信地址映射表列表 ──
def _parse_cmd_address_mapping(payload: bytes, direction: int, base_offset: int) -> list:
    table = []
    if direction == 1:
        _f(table, "上行负载", "", "", "下发通信地址映射表列表上行为确认/否认，无数据单元",
           base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table
    if len(payload) < 1:
        _f(table, "❌ 解析失败", "", "", "下行业务数据不足", None, None)
        return table
    offset = 0
    count = payload[offset]
    _f(table, "映射终端数量", f"0x{count:02X}", str(count), "映射表数量",
       base_offset + offset, base_offset + offset)
    offset += 1
    if offset + 3 <= len(payload):
        _f(table, "保留", _hex(payload[offset:offset+3]), "3字节", "保留，默认填0",
           base_offset + offset, base_offset + offset + 2)
        offset += 3
    for i in range(count):
        if offset + 18 > len(payload):
            break
        comm_raw, comm = _mac_addr(payload, offset)
        term_raw, term = _mac_addr(payload, offset + 6)
        # 终端地址实际为12字节，拆成两段显示
        term2_raw = _hex(payload[offset+12:offset+18])
        _f(table, f"  映射{i+1}通信地址", comm_raw, comm, f"通信地址: {comm}",
           base_offset + offset, base_offset + offset + 5)
        _f(table, f"  映射{i+1}终端地址前6字节", term_raw, term, f"终端地址: {term}",
           base_offset + offset + 6, base_offset + offset + 11)
        _f(table, f"  映射{i+1}终端地址后6字节", term2_raw, term2_raw, "终端地址续",
           base_offset + offset + 12, base_offset + offset + 17)
        offset += 18
    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x07: 查询从节点运行状态信息 ──
_RUN_STATUS_ELEMENT_MAP = {
    0x00: ("运行时长", 4, "BIN秒"),
    0x01: ("过零自检结果", 1, "BIN"),
    0x02: ("串口/485不通状态", 1, "BIN"),
    0x03: ("上次离网原因", 1, "BIN"),
    0x04: ("复位原因", 1, "BIN"),
    0x05: ("模块温度", 2, "有符号温度"),
    0x06: ("当前时钟", 6, "BCD时间"),
    0x07: ("串口配置", 7, "串口配置"),
}

_ZERO_CHECK_MAP = {
    0: "未知",
    1: "三相相序为ABC",
    2: "三相相序为ACB",
    3: "存在断相",
    4: "存在相同相位",
}

_UART_STATUS_MAP = {0: "正常", 1: "历史上出现过不通现象", 2: "目前不通"}
_LEAVE_REASON_MAP = {
    0: "未知", 1: "组网序列号变化", 2: "2个路由周期收不到信标帧",
    3: "与代理节点连续四个路由周期的通信成功率都是0", 4: "站点所在层级超过15级",
    5: "收到离线指示",
}
_RESET_REASON_MAP = {0: "掉电复位", 1: "复位引脚复位", 2: "升级完成复位", 3: "CCO控制从节点重启"}


def _parse_run_status_element(payload: bytes, offset: int, base_offset: int) -> Tuple[int, list]:
    table = []
    if offset + 2 > len(payload):
        return offset, table
    elem_id = payload[offset]
    elem_len = payload[offset + 1]
    name, default_len, fmt = _RUN_STATUS_ELEMENT_MAP.get(
        elem_id, (f"保留/自定义(0x{elem_id:02X})", elem_len, "BIN"))
    _f(table, "  元素ID", f"0x{elem_id:02X}", str(elem_id), name,
       base_offset + offset, base_offset + offset)
    _f(table, "  元素长度", f"0x{elem_len:02X}", str(elem_len), f"{elem_len}字节",
       base_offset + offset + 1, base_offset + offset + 1)
    offset += 2
    if elem_len > 0 and offset + elem_len <= len(payload):
        data = payload[offset:offset + elem_len]
        raw = _hex(data)
        parsed = raw
        if elem_id == 0x00 and elem_len == 4:
            parsed = f"{int.from_bytes(data, 'little')}秒"
        elif elem_id == 0x01 and elem_len == 1:
            parsed = _ZERO_CHECK_MAP.get(data[0], f"保留({data[0]})")
        elif elem_id == 0x02 and elem_len == 1:
            parsed = _UART_STATUS_MAP.get(data[0], f"保留({data[0]})")
        elif elem_id == 0x03 and elem_len == 1:
            parsed = _LEAVE_REASON_MAP.get(data[0], f"厂家自定义/保留({data[0]})")
        elif elem_id == 0x04 and elem_len == 1:
            parsed = _RESET_REASON_MAP.get(data[0], f"厂家自定义/保留({data[0]})")
        elif elem_id == 0x05 and elem_len == 2:
            parsed = f"{int.from_bytes(data, 'little', signed=True)}摄氏度"
        elif elem_id == 0x06 and elem_len == 6:
            _, parsed = _bcd6(data, 0)
        elif elem_id == 0x07 and elem_len == 7:
            baud = int.from_bytes(data[0:4], 'little')
            parity = data[4]
            data_bits = data[5]
            stop_bits = data[6]
            parity_map = {0: "无校验", 1: "偶校验", 2: "奇校验"}
            stop_map = {1: "1停止位", 2: "1.5停止位", 3: "2停止位"}
            parsed = (f"速率:{baud}bps 校验:{parity_map.get(parity, str(parity))} "
                      f"数据位:{data_bits} 停止位:{stop_map.get(stop_bits, str(stop_bits))}")
        _f(table, "  元素数据", raw if len(raw) <= 30 else raw[:30] + "...", parsed, f"{name}数据",
           base_offset + offset, base_offset + offset + elem_len - 1)
        offset += elem_len
    return offset, table


def _parse_cmd_node_status_query(payload: bytes, direction: int, base_offset: int) -> list:
    table = []
    if len(payload) < 1:
        _f(table, "❌ 解析失败", "", "", "查询从节点运行状态数据不足", None, None)
        return table
    offset = 0
    count = payload[offset]
    _f(table, "运行信息列表元素数量", f"0x{count:02X}", str(count), "查询的运行信息元素数量",
       base_offset + offset, base_offset + offset)
    offset += 1
    if direction == 0:
        for i in range(count):
            if offset >= len(payload):
                break
            elem_id = payload[offset]
            name, _, _ = _RUN_STATUS_ELEMENT_MAP.get(elem_id, (f"保留/自定义(0x{elem_id:02X})", 0, "BIN"))
            _f(table, f"  查询元素{i+1}ID", f"0x{elem_id:02X}", str(elem_id), name,
               base_offset + offset, base_offset + offset)
            offset += 1
    else:
        for i in range(count):
            if offset >= len(payload):
                break
            offset, sub = _parse_run_status_element(payload, offset, base_offset)
            table.extend(sub)
    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x08: 查询从节点信道信息 ──
def _parse_cmd_channel_info(payload: bytes, direction: int, base_offset: int) -> list:
    table = []
    if direction == 0:
        if len(payload) < 3:
            _f(table, "❌ 解析失败", "", "", "下行业务数据不足", None, None)
            return table
        start = _uint16_le(payload, 0)
        count = payload[2]
        _f(table, "周边节点起始序号", _hex(payload[0:2]), str(start), "在周边节点列表中的起始序号，从0开始",
           base_offset, base_offset + 1)
        _f(table, "查询数量", f"0x{count:02X}", str(count), "查询的周边节点数量(1~6)",
           base_offset + 2, base_offset + 2)
        _remaining(table, payload, 3, base_offset)
        return table
    # 上行
    if len(payload) < 3:
        _f(table, "❌ 解析失败", "", "", "上行业务数据不足", None, None)
        return table
    offset = 0
    total = _uint16_le(payload, 0)
    this_count = payload[2]
    _f(table, "周边节点总数量", _hex(payload[0:2]), str(total), "信息列表中元素数量",
       base_offset, base_offset + 1)
    _f(table, "本次上报的周边节点数量", f"0x{this_count:02X}", str(this_count), "本次上报节点数",
       base_offset + 2, base_offset + 2)
    offset = 3
    for i in range(this_count):
        if offset + 16 > len(payload):
            break
        addr_raw, addr = _mac_addr(payload, offset)
        tei = _uint16_le(payload, offset + 6)
        proxy = _uint16_le(payload, offset + 8)
        level = payload[offset + 10]
        tx_rate = payload[offset + 11]
        rx_rate = payload[offset + 12]
        both_rate = payload[offset + 13]
        snr = payload[offset + 14]
        attenuation = payload[offset + 15]
        _f(table, f"  节点{i+1}地址", addr_raw, addr, f"MAC地址: {addr}",
           base_offset + offset, base_offset + offset + 5)
        _f(table, f"  节点{i+1}TEI", _hex(payload[offset+6:offset+8]), f"0x{tei:04X}", "节点TEI",
           base_offset + offset + 6, base_offset + offset + 7)
        _f(table, f"  节点{i+1}代理TEI", _hex(payload[offset+8:offset+10]), f"0x{proxy:04X}", "代理节点TEI",
           base_offset + offset + 8, base_offset + offset + 9)
        _f(table, f"  节点{i+1}层级", f"0x{level:02X}", str(level), "节点层级",
           base_offset + offset + 10, base_offset + offset + 10)
        _f(table, f"  节点{i+1}上行通信成功率", f"0x{tx_rate:02X}", str(tx_rate), "上行通信成功率",
           base_offset + offset + 11, base_offset + offset + 11)
        _f(table, f"  节点{i+1}下行通信成功率", f"0x{rx_rate:02X}", str(rx_rate), "下行通信成功率",
           base_offset + offset + 12, base_offset + offset + 12)
        _f(table, f"  节点{i+1}上下行通信成功率", f"0x{both_rate:02X}", str(both_rate), "上下行通信成功率",
           base_offset + offset + 13, base_offset + offset + 13)
        _f(table, f"  节点{i+1}信噪比", f"0x{snr:02X}", str(snr), "SNR(dB)，有符号-20~80",
           base_offset + offset + 14, base_offset + offset + 14)
        _f(table, f"  节点{i+1}衰减", f"0x{attenuation:02X}", str(attenuation), "衰减(dB)，0~150",
           base_offset + offset + 15, base_offset + offset + 15)
        offset += 16
    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x09: 查询模块运行参数 ──
_MODULE_RUN_PARAM_ELEMENT_MAP = {
    0x01: ("节点m地址", 6, "MAC地址"),
    0x02: ("节点m标识(TEI)", 2, "BIN"),
    0x03: ("PLC通信成功率", 1, "BIN"),
    0x04: ("PLC信噪比", 1, "BIN"),
    0x05: ("PLC衰减", 1, "BIN"),
    0x06: ("RF通信成功率", 1, "BIN"),
    0x07: ("RF信噪比", 1, "BIN"),
    0x08: ("RF衰减", 1, "BIN"),
    0x09: ("电气线路距离", 2, "HEX米"),
    0x0A: ("空间距离", 2, "HEX米"),
}


def _parse_module_param_element(payload: bytes, offset: int, base_offset: int) -> Tuple[int, list]:
    table = []
    if offset + 2 > len(payload):
        return offset, table
    elem_id = payload[offset]
    elem_len = payload[offset + 1]
    name, default_len, fmt = _MODULE_RUN_PARAM_ELEMENT_MAP.get(
        elem_id, (f"保留/自定义(0x{elem_id:02X})", elem_len, "BIN"))
    _f(table, "  元素ID", f"0x{elem_id:02X}", str(elem_id), name,
       base_offset + offset, base_offset + offset)
    _f(table, "  元素长度", f"0x{elem_len:02X}", str(elem_len), f"{elem_len}字节",
       base_offset + offset + 1, base_offset + offset + 1)
    offset += 2
    if elem_len > 0 and offset + elem_len <= len(payload):
        data = payload[offset:offset + elem_len]
        raw = _hex(data)
        parsed = raw
        if elem_id == 0x01 and elem_len == 6:
            _, parsed = _mac_addr(data, 0)
        elif elem_id == 0x02 and elem_len == 2:
            parsed = f"TEI:0x{int.from_bytes(data, 'little'):04X}"
        elif elem_id in (0x09, 0x0A) and elem_len == 2:
            parsed = f"{int.from_bytes(data, 'little')}m"
        _f(table, "  元素数据", raw if len(raw) <= 30 else raw[:30] + "...", parsed, f"{name}数据",
           base_offset + offset, base_offset + offset + elem_len - 1)
        offset += elem_len
    return offset, table


def _parse_cmd_module_run_params(payload: bytes, direction: int, base_offset: int) -> list:
    table = []
    if direction == 0:
        if len(payload) < 4:
            _f(table, "❌ 解析失败", "", "", "下行业务数据不足", None, None)
            return table
        start = _uint16_le(payload, 0)
        count = payload[2]
        elem_count = payload[3]
        _f(table, "周边节点起始序号", _hex(payload[0:2]), str(start), "本次查询起始序号",
           base_offset, base_offset + 1)
        _f(table, "查询数量", f"0x{count:02X}", str(count), "本次查询周边节点数量",
           base_offset + 2, base_offset + 2)
        _f(table, "信息列表元素数量", f"0x{elem_count:02X}", str(elem_count), "单个节点信息元素数量",
           base_offset + 3, base_offset + 3)
        offset = 4
        for i in range(elem_count):
            if offset >= len(payload):
                break
            elem_id = payload[offset]
            name, _, _ = _MODULE_RUN_PARAM_ELEMENT_MAP.get(elem_id, (f"保留/自定义(0x{elem_id:02X})", 0, "BIN"))
            _f(table, f"  查询元素{i+1}ID", f"0x{elem_id:02X}", str(elem_id), name,
               base_offset + offset, base_offset + offset)
            offset += 1
        _remaining(table, payload, offset, base_offset)
        return table
    # 上行
    if len(payload) < 5:
        _f(table, "❌ 解析失败", "", "", "上行业务数据不足", None, None)
        return table
    offset = 0
    total = _uint16_le(payload, 0)
    start = _uint16_le(payload, 2)
    count = payload[4]
    _f(table, "周边节点总数量", _hex(payload[0:2]), str(total), "周边节点总数量",
       base_offset, base_offset + 1)
    _f(table, "本次上报的起始序号", _hex(payload[2:4]), str(start), "本次上报起始序号",
       base_offset + 2, base_offset + 3)
    _f(table, "本次上报的周边节点数量", f"0x{count:02X}", str(count), "本次上报节点数",
       base_offset + 4, base_offset + 4)
    offset = 5
    for i in range(count):
        if offset >= len(payload):
            break
        node_elem_count = payload[offset]
        _f(table, f"  节点{i+1}信息数据数量", f"0x{node_elem_count:02X}", str(node_elem_count), "该节点信息元素数量",
           base_offset + offset, base_offset + offset)
        offset += 1
        for j in range(node_elem_count):
            if offset >= len(payload):
                break
            offset, sub = _parse_module_param_element(payload, offset, base_offset)
            table.extend(sub)
    _remaining(table, payload, offset, base_offset)
    return table


# ── 0x10: 台区户变关系/相位识别 ──
_FEATURE_TYPE_MAP = {1: "工频电压特征", 2: "工频频率特征", 3: "工频周期特征"}
_COLLECT_TYPE_MAP = {
    1: "台区特征采集启动",
    2: "台区特征信息收集",
    3: "台区特征信息告知",
    4: "台区判别结果查询",
    5: "台区判别结果信息",
    6: "相位特征采集指示",
    7: "相位特征信息告知",
}
_COLLECT_PHASE_MAP = {0: "默认相位", 1: "第一出线相位", 2: "第二出线相位", 3: "第三出线相位"}


def _parse_cmd_district_phase(payload: bytes, direction: int, base_offset: int) -> list:
    """0x10 台区户变关系/相位识别"""
    table = []
    if len(payload) < 12:
        _f(table, "❌ 解析失败", "", "", "台区户变关系/相位识别报文头不足12字节", None, None)
        return table
    b0 = payload[0]
    header_len = b0 & 0x3F
    phase = (b0 >> 6) & 0x03
    _f(table, "报文头长度", f"0x{header_len:02X}", str(header_len), "报文头长度（字节）",
       base_offset, base_offset)
    _f(table, "采集相位", f"0x{phase:02X}", str(phase), _COLLECT_PHASE_MAP.get(phase, "保留"),
       base_offset, base_offset)
    _f(table, "保留", _hex(payload[1:4]), "3字节", "保留",
       base_offset + 1, base_offset + 3)
    addr_raw, addr = _mac_addr_be(payload, 4)
    _f(table, "MAC地址", addr_raw, addr, f"关联MAC地址(大端): {addr}",
       base_offset + 4, base_offset + 9)
    feature = payload[10]
    collect = payload[11]
    _f(table, "特征类型", f"0x{feature:02X}", str(feature),
       _FEATURE_TYPE_MAP.get(feature, f"保留(0x{feature:02X})"),
       base_offset + 10, base_offset + 10)
    _f(table, "采集类型", f"0x{collect:02X}", str(collect),
       _COLLECT_TYPE_MAP.get(collect, f"保留(0x{collect:02X})"),
       base_offset + 11, base_offset + 11)

    data_offset = header_len if header_len >= 12 else 12
    data = payload[data_offset:]
    if not data:
        _f(table, "DATA", "", "", "无数据",
           base_offset + data_offset, base_offset + data_offset)
        return table

    offset = data_offset
    if collect == 0x01:  # 台区特征采集启动
        if len(data) >= 8:
            start_ntb = _uint32_le(payload, offset)
            period = payload[offset + 4]
            count = payload[offset + 5]
            seq = payload[offset + 6]
            _f(table, "起始NTB", _hex(payload[offset:offset+4]), f"0x{start_ntb:08X}", "全网开始采集时刻的NTB",
               base_offset + offset, base_offset + offset + 3)
            _f(table, "采集周期", f"0x{period:02X}", str(period), "单位：秒；工频周期特征时忽略",
               base_offset + offset + 4, base_offset + offset + 4)
            _f(table, "采集数量", f"0x{count:02X}", str(count), "连续采集特征信息数量",
               base_offset + offset + 5, base_offset + offset + 5)
            _f(table, "采集序列号", f"0x{seq:02X}", str(seq), "第几次启动采集",
               base_offset + offset + 6, base_offset + offset + 6)
            _f(table, "保留", f"0x{payload[offset+7]:02X}", str(payload[offset+7]), "保留",
               base_offset + offset + 7, base_offset + offset + 7)
            offset += 8
    elif collect == 0x05:  # 台区判别结果信息
        if len(data) >= 10:
            tei = _uint16_le(payload, offset)
            end_flag = payload[offset + 2]
            result = payload[offset + 3]
            addr_raw2, addr2 = _mac_addr_be(payload, offset + 4)
            result_desc = {0: "未知", 1: "是本台区", 2: "不是本台区"}.get(result, "保留")
            _f(table, "TEI", _hex(payload[offset:offset+2]), f"0x{tei:04X}", "STA的TEI",
               base_offset + offset, base_offset + offset + 1)
            _f(table, "台区判别过程结束标志", f"0x{end_flag:02X}", str(end_flag),
               "1表示识别过程结束" if end_flag == 1 else "识别进行中/保留",
               base_offset + offset + 2, base_offset + offset + 2)
            _f(table, "台区识别结果", f"0x{result:02X}", str(result), result_desc,
               base_offset + offset + 3, base_offset + offset + 3)
            _f(table, "正确隶属CCO地址", addr_raw2, addr2,
               "非本台区时填充正确隶属CCO地址；全0表示未能识别" if result == 2 else "未使用",
               base_offset + offset + 4, base_offset + offset + 9)
            offset += 10
    elif collect == 0x06:  # 相位特征采集指示
        if len(data) >= 4:
            count = payload[offset]
            seq = payload[offset + 1]
            _f(table, "采集数量", f"0x{count:02X}", str(count), "连续采集特征信息数量",
               base_offset + offset, base_offset + offset)
            _f(table, "采集序列号", f"0x{seq:02X}", str(seq), "第几次启动采集",
               base_offset + offset + 1, base_offset + offset + 1)
            _f(table, "保留", _hex(payload[offset+2:offset+4]), "2字节", "保留",
               base_offset + offset + 2, base_offset + offset + 3)
            offset += 4

    elif collect == 0x03:  # 台区特征信息告知
        if len(data) >= 8:
            # TEI(12b) + 采集方式(2b) + 保留(2b) 打包在2字节中
            w0 = _uint16_le(payload, offset)
            tei = w0 & 0x0FFF
            collect_mode = (w0 >> 12) & 0x03
            _f(table, "TEI", _hex(payload[offset:offset+2]), f"0x{tei:03X}",
               "CCO(TEI=1)或STA地址", base_offset + offset, base_offset + offset + 1)
            mode_desc = {0: "保留", 1: "下降沿采集", 2: "上升沿采集", 3: "双沿采集"}.get(collect_mode, "保留")
            _f(table, "采集方式", f"0x{collect_mode:X}", str(collect_mode),
               mode_desc + (" (仅工频周期特征有效)" if feature != 3 else ""),
               base_offset + offset + 1, base_offset + offset + 1)
            seq = payload[offset + 2]
            total = payload[offset + 3]
            _f(table, "采集序列号", f"0x{seq:02X}", str(seq), "第几次采集活动",
               base_offset + offset + 2, base_offset + offset + 2)
            _f(table, "告知总数量", f"0x{total:02X}", str(total), "特征序列数据个数",
               base_offset + offset + 3, base_offset + offset + 3)
            offset += 4

            # 解析第一组: 起始采集NTB1 + 特征序列1
            for group_idx, group_label in enumerate(["1", "2"]):
                if offset + 4 > len(payload):
                    break
                start_ntb = _uint32_le(payload, offset)
                _f(table, f"起始采集NTB{group_label}", _hex(payload[offset:offset+4]),
                   f"0x{start_ntb:08X}", f"第{group_label}组过零点起始时刻",
                   base_offset + offset, base_offset + offset + 3)
                offset += 4

                # 特征序列: 保留(1B) + 三相报告数量(各1B) + 各相数据
                if offset >= len(payload):
                    break
                rsv = payload[offset]
                _f(table, f"保留(序列{group_label})", f"0x{rsv:02X}", str(rsv), "保留",
                   base_offset + offset, base_offset + offset)
                offset += 1

                phase_names = ["第一出线", "第二出线", "第三出线"]
                phase_counts = []
                for pi in range(3):
                    if offset >= len(payload):
                        break
                    pc = payload[offset]
                    phase_counts.append(pc)
                    _f(table, f"{phase_names[pi]}报告数量(序列{group_label})",
                       f"0x{pc:02X}", str(pc), f"{phase_names[pi]}特征数据个数",
                       base_offset + offset, base_offset + offset)
                    offset += 1

                # 解析各相数据值
                for pi, pc in enumerate(phase_counts):
                    if feature == 1:  # 工频电压: BCD XXX.X, 2字节
                        for vi in range(pc):
                            if offset + 2 > len(payload):
                                break
                            val = payload[offset:offset+2]
                            # BCD解码: 低字节在前
                            lo, hi = val[0], val[1]
                            bcd_str = f"{hi >> 4}{hi & 0x0F}{lo >> 4}.{lo & 0x0F}"
                            _f(table, f"{phase_names[pi]}V{vi+1}(序列{group_label})",
                               _hex(val), bcd_str, f"BCD电压值(V)",
                               base_offset + offset, base_offset + offset + 1)
                            offset += 2
                    elif feature == 2:  # 工频频率: BCD XX.XX, 2字节
                        for fi in range(pc):
                            if offset + 2 > len(payload):
                                break
                            val = payload[offset:offset+2]
                            lo, hi = val[0], val[1]
                            bcd_str = f"{hi >> 4}{hi & 0x0F}.{lo >> 4}{lo & 0x0F}"
                            _f(table, f"{phase_names[pi]}F{fi+1}(序列{group_label})",
                               _hex(val), bcd_str, f"BCD频率值(Hz)",
                               base_offset + offset, base_offset + offset + 1)
                            offset += 2
                    elif feature == 3:  # 工频周期: 有符号整数偏差, 2字节
                        for ti in range(pc):
                            if offset + 2 > len(payload):
                                break
                            val = int.from_bytes(payload[offset:offset+2], 'little', signed=True)
                            _f(table, f"{phase_names[pi]}T{ti+1}(序列{group_label})",
                               _hex(payload[offset:offset+2]), f"{val}",
                               f"周期偏差(单位1/3125000s, 相对于20ms)",
                               base_offset + offset, base_offset + offset + 1)
                            offset += 2

                # 双沿采集时才有第二组，否则跳出
                if collect_mode != 3:
                    break

    elif collect == 0x07:  # 相位特征信息告知
        if len(data) >= 12:
            # TEI(12b) + 采集方式(2b) + 保留(2b)
            w0 = _uint16_le(payload, offset)
            tei = w0 & 0x0FFF
            collect_mode = (w0 >> 12) & 0x03
            _f(table, "TEI", _hex(payload[offset:offset+2]), f"0x{tei:03X}",
               "STA的TEI", base_offset + offset, base_offset + offset + 1)
            mode_desc = {0: "保留", 1: "下降沿采集", 2: "上升沿采集"}.get(collect_mode, "保留")
            _f(table, "采集方式", f"0x{collect_mode:X}", str(collect_mode), mode_desc,
               base_offset + offset + 1, base_offset + offset + 1)
            seq = payload[offset + 2]
            total = payload[offset + 3]
            _f(table, "采集序列号", f"0x{seq:02X}", str(seq), "第几次采集活动",
               base_offset + offset + 2, base_offset + offset + 2)
            _f(table, "告知总数量", f"0x{total:02X}", str(total),
               "三相过零NTB差值总数(n1+n2+n3)",
               base_offset + offset + 3, base_offset + offset + 3)
            base_ntb = _uint32_le(payload, offset + 4)
            _f(table, "基准NTB", _hex(payload[offset+4:offset+8]), f"0x{base_ntb:08X}",
               "第一个过零点NTB值", base_offset + offset + 4, base_offset + offset + 7)
            _f(table, "保留", f"0x{payload[offset+8]:02X}", str(payload[offset+8]), "保留",
               base_offset + offset + 8, base_offset + offset + 8)

            # 三相过零NTB差值数量
            phase_counts = []
            phase_names = ["相线1", "相线2", "相线3"]
            for pi in range(3):
                nc = payload[offset + 9 + pi]
                phase_counts.append(nc)
                _f(table, f"{phase_names[pi]}过零NTB差值数量",
                   f"0x{nc:02X}", str(nc), f"{phase_names[pi]}差值个数",
                   base_offset + offset + 9 + pi, base_offset + offset + 9 + pi)
            offset += 12

            # 各相过零NTB差值序列 (每个差值 2B, 无符号整数, 单位1/1562500s)
            for pi, nc in enumerate(phase_counts):
                for di in range(nc):
                    if offset + 2 > len(payload):
                        break
                    diff = _uint16_le(payload, offset)
                    _f(table, f"{phase_names[pi]}差值{di+1}",
                       _hex(payload[offset:offset+2]), str(diff),
                       f"过零NTB差值(单位1/1562500s)",
                       base_offset + offset, base_offset + offset + 1)
                    offset += 2

    if offset < len(payload):
        _f(table, "DATA(原始)", _hex(payload[offset:])[:80] + ("..." if len(payload) - offset > 40 else ""),
           f"{len(payload) - offset}字节", "业务数据（详细格式依特征/采集类型而定）",
           base_offset + offset, base_offset + len(payload) - 1)
    return table


# ── 0xF0: 测试帧 ──
_TEST_ID_MAP = {
    0x00: "进入回环测试模式",
    0x01: "进入透明转发模式",
    0x02: "频段切换命令",
    0x03: "1.0测试",
    0x04: "2.0测试",
}

_TEST_EXT_ID_MAP = {
    0x0001: "Bitloading测试模式",
    0x0002: "Bitloading表下发",
    0x0003: "空间映射测试模式",
    0x0004: "OFDMA测试模式",
    0x0005: "OFDMA多用户下发",
    0x0006: "MAC层OFDMA配置",
    0x0007: "非组网场景TEI配置",
    0x0008: "业务报文Bitloading收发开关",
}


def _bits(data: bytes, offset: int, bit_start: int, bit_width: int) -> int:
    """按小端序从 data 中提取位域（bit_start 为字节内最低位位置）"""
    if offset < 0 or offset >= len(data) or bit_width <= 0:
        return 0
    total_bits = bit_start + bit_width
    end_byte = offset + (total_bits + 7) // 8
    if end_byte > len(data):
        return 0
    val = int.from_bytes(data[offset:end_byte], 'little')
    return (val >> bit_start) & ((1 << bit_width) - 1)


def _parse_test_ext_0001(data: bytes, base_offset: int) -> list:
    """0x0001: Bitloading测试模式，无扩展数据"""
    table = []
    _f(table, "说明", "", "", "进入Bitloading测试模式，无附加数据",
       base_offset, base_offset + len(data) - 1 if data else base_offset)
    _remaining(table, data, 0, base_offset)
    return table


def _parse_test_ext_0002(data: bytes, base_offset: int) -> list:
    """0x0002: Bitloading表下发"""
    table = []
    if len(data) < 12:
        _f(table, "❌ 解析失败", "", "", "Bitloading表下发数据不足12字节", None, None)
        return table
    src_tei = _uint16_le(data, 0)
    dst_tei = _uint16_le(data, 2)
    stream_count = data[4]
    subcarrier_group = data[5]
    cutoff_carrier = _uint16_le(data, 6)
    bl_table_len = _uint16_le(data, 8)
    bps = _uint16_le(data, 10)
    _f(table, "源TEI", _hex(data[0:2]), str(src_tei), "源节点TEI",
       base_offset, base_offset + 1)
    _f(table, "目的TEI", _hex(data[2:4]), str(dst_tei), "目的节点TEI",
       base_offset + 2, base_offset + 3)
    _f(table, "流数", f"0x{stream_count:02X}", str(stream_count),
       "1:1流 2:2流", base_offset + 4, base_offset + 4)
    _f(table, "子载波分组大小", f"0x{subcarrier_group:02X}", str(subcarrier_group),
       "子载波分组大小", base_offset + 5, base_offset + 5)
    _f(table, "截止子载波", _hex(data[6:8]), str(cutoff_carrier),
       "截止子载波编号", base_offset + 6, base_offset + 7)
    _f(table, "比特加载表长度", _hex(data[8:10]), str(bl_table_len),
       "比特加载表字节数", base_offset + 8, base_offset + 9)
    _f(table, "Bps", _hex(data[10:12]), str(bps), "每符号比特数",
       base_offset + 10, base_offset + 11)
    offset = 12
    if bl_table_len > 0 and offset + bl_table_len <= len(data):
        bl_table = data[offset:offset + bl_table_len]
        _BIT_MOD_MAP = {0: "不加载", 1: "BPSK", 2: "QPSK", 4: "16QAM", 6: "64QAM"}
        # 协议定义：每个子载波组占3bit，单流每8组占3字节，双流每8组占6字节(3B流0+3B流1)
        if stream_count <= 1:
            # 单流：每3字节含8个子载波组，每组3bit
            num_entries = (bl_table_len * 8) // 3
            _f(table, "B表总览", _hex(bl_table)[:80] + ("..." if bl_table_len > 40 else ""),
               f"{num_entries}组/{bl_table_len}字节",
               f"3bit/组, 子载波分组大小={subcarrier_group}, 单流",
               base_offset + offset, base_offset + offset + bl_table_len - 1)
            for i in range(num_entries):
                block = i // 8
                idx_in_block = i % 8
                bit_pos = idx_in_block * 3
                byte_in_block = bit_pos // 8
                bit_in_byte = bit_pos % 8
                abs_byte = block * 3 + byte_in_block
                val = 0
                for b in range(3):
                    bi = abs_byte + (bit_in_byte + b) // 8
                    if bi < bl_table_len:
                        val |= ((bl_table[bi] >> ((bit_in_byte + b) % 8)) & 1) << b
                mod = _BIT_MOD_MAP.get(val, f"保留({val})")
                sc_start = i * subcarrier_group
                sc_end = sc_start + subcarrier_group - 1
                entry_byte = offset + abs_byte
                _f(table, f"  组{i} [子载波{sc_start}-{sc_end}]",
                   f"3bit@{abs_byte}B", f"{val} ({mod})",
                   f"流0承载{val}bit",
                   base_offset + entry_byte, base_offset + entry_byte)
        else:
            # 双流：每6字节含8组(3B流0+3B流1)，每组流各3bit
            num_blocks = bl_table_len // 6
            num_entries = num_blocks * 8
            _f(table, "B表总览", _hex(bl_table)[:80] + ("..." if bl_table_len > 40 else ""),
               f"{num_entries}组/{bl_table_len}字节",
               f"3bit/组/流, 子载波分组大小={subcarrier_group}, 双流",
               base_offset + offset, base_offset + offset + bl_table_len - 1)
            for i in range(num_entries):
                block = i // 8
                idx_in_block = i % 8
                bit_pos = idx_in_block * 3
                byte_in_block = bit_pos // 8
                bit_in_byte = bit_pos % 8
                # 流0: block*6 + 0..2, 流1: block*6 + 3..5
                val0 = 0
                val1 = 0
                for b in range(3):
                    bi0 = block * 6 + byte_in_block + (bit_in_byte + b) // 8
                    bi1 = block * 6 + 3 + byte_in_block + (bit_in_byte + b) // 8
                    if bi0 < bl_table_len:
                        val0 |= ((bl_table[bi0] >> ((bit_in_byte + b) % 8)) & 1) << b
                    if bi1 < bl_table_len:
                        val1 |= ((bl_table[bi1] >> ((bit_in_byte + b) % 8)) & 1) << b
                mod0 = _BIT_MOD_MAP.get(val0, f"保留({val0})")
                mod1 = _BIT_MOD_MAP.get(val1, f"保留({val1})")
                sc_start = i * subcarrier_group
                sc_end = sc_start + subcarrier_group - 1
                entry_byte = offset + block * 6
                _f(table, f"  组{i} [子载波{sc_start}-{sc_end}]",
                   f"流0:{val0} 流1:{val1}",
                   f"流0:{val0}({mod0}) 流1:{val1}({mod1})",
                   f"流0承载{val0}bit, 流1承载{val1}bit",
                   base_offset + entry_byte, base_offset + entry_byte + 5)
        offset += bl_table_len
    _remaining(table, data, offset, base_offset)
    return table


def _parse_test_ext_0003(data: bytes, base_offset: int) -> list:
    """0x0003: 空间映射测试模式"""
    table = []
    if len(data) < 1:
        _f(table, "❌ 解析失败", "", "", "空间映射测试模式数据不足", None, None)
        return table
    mode = data[0]
    _f(table, "映射模式", f"0x{mode:02X}", str(mode), "空间映射模式",
       base_offset, base_offset)
    _remaining(table, data, 1, base_offset)
    return table


def _parse_test_ext_0004(data: bytes, base_offset: int) -> list:
    """0x0004: OFDMA测试模式，无扩展数据"""
    table = []
    _f(table, "说明", "", "", "进入OFDMA测试模式，无附加数据",
       base_offset, base_offset + len(data) - 1 if data else base_offset)
    _remaining(table, data, 0, base_offset)
    return table


_OFDMA_FRAME_TYPE_MAP = {
    0: "DL_OFDMA（立即发送）",
    1: "UL_OFDMA（等待触发发送）",
    2: "UL_OFDMA的trigger（立即发送）",
    3: "保留",
}

_EFC_SYM_COUNT_MAP = {
    0: "2个符号",
    1: "4个符号",
    2: "8个符号",
    3: "12个符号",
}

_TX_POWER_BACKOFF_MAP = {
    0: "回退0dB",
    1: "回退4dB",
    2: "回退8dB",
    3: "回退12dB",
    4: "回退16dB",
    5: "回退20dB",
    6: "回退24dB",
    7: "回退28dB",
}


def _parse_test_ext_0005(data: bytes, base_offset: int) -> list:
    """0x0005: OFDMA多用户下发（通感一体物联版）

    数据域结构（data[x] = 文档字节 x+3）:
      字节3 (data[0]): 帧类型(2bit, bit0-1) + 保留(6bit, bit2-7)
      字节4-19 (data[1..16]): FC域 16字节
        - 字节4 (data[1]): 定界符(3bit) + 接入指示(1bit) + SNID低4bit(4bit)
        - 字节5-16 (data[2..13]): FC可变域 12字节（表26, OFDMA帧）
        - 字节17-19 (data[14..16]): FC FCS（24bit CRC）
      字节20-35 (data[17..32]): eFC域 16字节（类型0/2/3才有，类型1无）
        - 字节20-32 (data[17..29]): eFC内容 13字节
        - 字节33-35 (data[30..32]): eFC CRC 24bit

    帧类型: 0=DL_OFDMA(立即发送), 1=UL_OFDMA(等待触发), 2=UL_OFDMA trigger(立即发送), 3=保留
    """
    table = []
    if len(data) < 1:
        _f(table, "❌ 解析失败", "", "", "OFDMA多用户下发数据不足1字节", None, None)
        return table
    # ── 字节3：帧类型 + 保留 ──
    frame_type = _bits(data, 0, 0, 2)
    reserved = _bits(data, 0, 2, 6)
    _f(table, "帧类型", f"0x{frame_type:01X}", str(frame_type),
       _OFDMA_FRAME_TYPE_MAP.get(frame_type, f"保留({frame_type})"),
       base_offset, base_offset)
    _f(table, "保留", f"0x{reserved:02X}", str(reserved),
       "保留字段", base_offset, base_offset)
    # ── FC域（16字节） ──
    fc_start = 1  # data[1] = 字节4 = FC起始
    fc_abs = base_offset + fc_start
    if len(data) < fc_start + 16:
        avail = max(0, len(data) - fc_start)
        if avail > 0:
            _f(table, "FC域（部分）", _hex(data[fc_start:fc_start + avail]),
               f"{avail}字节", "数据不足，FC不完整",
               fc_abs, base_offset + len(data) - 1)
        return table
    fc_data = data[fc_start:fc_start + 16]
    # FC字节0: 定界符 + 接入指示 + SNID低4bit
    delim = _bits(fc_data, 0, 0, 3)
    access = _bits(fc_data, 0, 3, 1)
    snid_lo = _bits(fc_data, 0, 4, 4)
    _DELIM_MAP = {1: "SOF帧", 2: "ACK帧", 3: "NACK帧"}
    _f(table, "FC - 定界符类型", f"0b{delim:03b}", str(delim),
       _DELIM_MAP.get(delim, f"保留({delim})"), fc_abs, fc_abs)
    _f(table, "FC - 接入指示", f"0b{access:01b}", str(access),
       "宽带载波通信接入网络" if access else "窄带", fc_abs, fc_abs)
    _f(table, "FC - SNID低位", f"0x{snid_lo:01X}", str(snid_lo),
       f"SNID低4位: {snid_lo}", fc_abs, fc_abs)
    # FC可变域（表26, 字节1-12 = fc_data[1..12]）
    fcv = fc_data[1:13]
    fcv_abs = fc_abs + 1
    # 源TEI: 字节1(8) + 字节2低4(4) = 12bit
    src_tei = _bits(fcv, 0, 0, 8) | (_bits(fcv, 1, 0, 4) << 8)
    # 目的TEI: 字节2高4(4) + 字节3(8) = 12bit
    dst_tei = _bits(fcv, 1, 4, 4) | (_bits(fcv, 2, 0, 8) << 4)
    # 字节4: 多站点(1) + OFDMA帧类型(2) + 频段(3) + 站点数(2)
    multi_site = _bits(fcv, 3, 0, 1)
    fc_frame_type = _bits(fcv, 3, 1, 2)
    band = _bits(fcv, 3, 3, 3)
    stn_raw = _bits(fcv, 3, 6, 2)
    station_count = stn_raw + 1
    # 字节5: eFC符号数(2) + 保留(6)
    efc_sym = _bits(fcv, 4, 0, 2)
    # 字节6-7bit0: PL符号数(9)
    pl_sym = _bits(fcv, 5, 0, 8) | (_bits(fcv, 6, 0, 1) << 8)
    # 字节8-9低4: 帧长(12)
    frame_len = _bits(fcv, 7, 0, 8) | (_bits(fcv, 8, 0, 4) << 8)
    # 字节12bit0: SNID高位
    snid_hi = _bits(fcv, 11, 0, 1)
    snid = (snid_hi << 4) | snid_lo

    _f(table, "  源TEI", _hex(fcv[0:2]), f"0x{src_tei:03X}",
       f"源站点TEI = {src_tei}", fcv_abs, fcv_abs + 1)
    _f(table, "  目的TEI", _hex(fcv[1:3]), f"0x{dst_tei:03X}",
       f"目的站点TEI = {dst_tei}", fcv_abs + 1, fcv_abs + 2)
    _f(table, "  多站点帧标识", f"0x{multi_site:01X}", str(multi_site),
       "1:多站点(OFDMA帧)", fcv_abs + 3, fcv_abs + 3)
    _f(table, "  OFDMA帧类型", f"0x{fc_frame_type:01X}", str(fc_frame_type),
       _OFDMA_FRAME_TYPE_MAP.get(fc_frame_type, f"保留({fc_frame_type})"),
       fcv_abs + 3, fcv_abs + 3)
    _f(table, "  频段标识", f"0x{band:01X}", str(band),
       f"PL频段 {band}", fcv_abs + 3, fcv_abs + 3)
    _f(table, "  站点数", f"0x{stn_raw:01X}", str(station_count),
       f"{station_count}个站点", fcv_abs + 3, fcv_abs + 3)
    _f(table, "  eFC符号个数", f"0x{efc_sym:01X}", str(efc_sym),
       _EFC_SYM_COUNT_MAP.get(efc_sym, f"保留({efc_sym})"),
       fcv_abs + 4, fcv_abs + 4)
    _f(table, "  PL符号数", f"0x{pl_sym:03X}", str(pl_sym),
       "PL符号数（取多站点最大值）", fcv_abs + 5, fcv_abs + 6)
    _f(table, "  帧长", f"0x{frame_len:03X}", str(frame_len),
       f"占用信道时长: {frame_len * 10}μs", fcv_abs + 7, fcv_abs + 8)
    _f(table, "  SNID", f"0x{snid:02X}", str(snid),
       f"完整SNID = 0x{snid:02X} ({snid})", fcv_abs + 11, fcv_abs + 11)
    # FCS
    fcs_abs = fc_abs + 14
    _f(table, "FC FCS校验", _hex(fc_data[13:16]),
       f"0x{int.from_bytes(fc_data[13:16], 'little'):06X}",
       "FC 24位CRC校验", fcs_abs, fc_abs + 15)
    # ── eFC域（16字节） ──
    efc_start = fc_start + 16  # data[17]
    efc_abs = base_offset + efc_start
    # 帧类型1 (UL_OFDMA / DL_SACK): 无eFC
    if fc_frame_type == 1:
        _f(table, "eFC", "", "",
           "UL_OFDMA帧 / DL-OFDMA SACK帧 不携带eFC",
           efc_abs, efc_abs - 1)
        _remaining(table, data, efc_start, base_offset)
        return table
    # 其他类型: 有eFC
    if len(data) < efc_start + 16:
        avail = max(0, len(data) - efc_start)
        if avail > 0:
            _f(table, "eFC（部分）", _hex(data[efc_start:]), f"{avail}字节",
               "数据不足，eFC不完整", efc_abs, base_offset + len(data) - 1)
        else:
            _f(table, "eFC", "", "", "无eFC数据", efc_abs, efc_abs - 1)
        return table
    efc = data[efc_start:efc_start + 16]
    if fc_frame_type == 0:
        _parse_efc_dl(table, efc, station_count, efc_abs)
    elif fc_frame_type == 2:
        _parse_efc_trigger(table, efc, station_count, efc_abs)
    elif fc_frame_type == 3:
        _parse_efc_sack(table, efc, station_count, efc_abs)
    else:
        _f(table, "eFC", _hex(efc[:13]), "13字节(不含CRC)",
           f"保留帧类型({fc_frame_type})，不解析eFC内容",
           efc_abs, efc_abs + 12)
    # eFC CRC
    _f(table, "eFC CRC校验", _hex(efc[13:16]),
       f"0x{int.from_bytes(efc[13:16], 'little'):06X}",
       "eFC 24位CRC校验", efc_abs + 13, efc_abs + 15)
    _remaining(table, data, efc_start + 16, base_offset)
    return table


def _parse_efc_dl(table: list, efc: bytes, station_count: int, base: int):
    """DL-OFDMA eFC (表27). 每站: PB数(1bit) + TEI(12bit) + TMI(5bit) + RU(4bit) + SACK_RU(3bit)"""
    _f(table, "eFC(DL-OFDMA)", _hex(efc[:13]), "13字节(不含CRC)",
       "DL-OFDMA帧eFC", base, base + 12)
    # TF个数: 字节0 bit0-1
    tf_count = _bits(efc, 0, 0, 2)
    _f(table, "  TF个数", f"0x{tf_count:01X}", str((tf_count + 1) * 2),
       f"实际TF个数 = ({tf_count}+1)*2 = {(tf_count+1)*2}", base, base)
    # 站点信息位偏移表（每站起始bit位置）
    # 站0: bit3开始(PB数1bit+TEI12bit+TMI5bit+RU4bit+SACK_RU3bit = 25bit = 3.125B)
    # 手动按文档表27解析
    stations_bits = [
        # (pb_bit, tei_start_bit, tmi_start_bit, ru_start_bit, sack_ru_start_bit)
        (2, 3, 15, 20, 24),    # 站0: byte0.2 ... byte3.0
        (27, 28, 40, 45, 49),  # 站1: byte3.3 ... byte6.0
        (52, 53, 65, 70, 74),  # 站2: byte6.4 ... byte9.2
        (77, 78, 90, 95, 99),  # 站3: byte9.5 ... byte12.3
    ]
    for i in range(station_count):
        if i >= len(stations_bits):
            break
        pb_bit, tei_s, tmi_s, ru_s, sack_s = stations_bits[i]
        pb = _bits(efc, pb_bit // 8, pb_bit % 8, 1)
        tei = _bits(efc, tei_s // 8, tei_s % 8, 12)
        tmi = _bits(efc, tmi_s // 8, tmi_s % 8, 5)
        ru = _bits(efc, ru_s // 8, ru_s % 8, 4)
        sack_ru = _bits(efc, sack_s // 8, sack_s % 8, 3)
        _f(table, f"  站点{i} PB个数", f"0x{pb:01X}", str(pb + 1),
           f"{pb+1}个PB块", base + pb_bit // 8, base + (pb_bit + 1 - 1) // 8)
        _f(table, f"  站点{i} TEI", "", f"0x{tei:03X}",
           f"站点TEI = {tei}", base + tei_s // 8, base + (tei_s + 12 - 1) // 8)
        _f(table, f"  站点{i} TMI", f"0x{tmi:02X}", str(tmi),
           "TMI调制编码方案", base + tmi_s // 8, base + (tmi_s + 5 - 1) // 8)
        _f(table, f"  站点{i} RU", f"0x{ru:01X}", str(ru),
           f"RU编号{ru}", base + ru_s // 8, base + (ru_s + 4 - 1) // 8)
        _f(table, f"  站点{i} SACK RU", f"0x{sack_ru:01X}", str(sack_ru),
           f"回复SACK使用的RU{sack_ru}", base + sack_s // 8, base + (sack_s + 3 - 1) // 8)


def _parse_efc_trigger(table: list, efc: bytes, station_count: int, base: int):
    """UL-OFDMA trigger eFC (表28). 每站: PB数(1) + TEI(12) + TMI(5) + RU(4) + Tx功率回退(3)"""
    _f(table, "eFC(UL-OFDMA trigger)", _hex(efc[:13]), "13字节(不含CRC)",
       "UL-OFDMA trigger帧eFC", base, base + 12)
    tf_count = _bits(efc, 0, 0, 2)
    _f(table, "  TF个数", f"0x{tf_count:01X}", str((tf_count + 1) * 2),
       f"实际TF个数 = ({tf_count}+1)*2 = {(tf_count+1)*2}", base, base)
    stations_bits = [
        (2, 3, 15, 20, 24),
        (27, 28, 40, 45, 49),
        (52, 53, 65, 70, 74),
        (77, 78, 90, 95, 99),
    ]
    for i in range(station_count):
        if i >= len(stations_bits):
            break
        pb_bit, tei_s, tmi_s, ru_s, pw_s = stations_bits[i]
        pb = _bits(efc, pb_bit // 8, pb_bit % 8, 1)
        tei = _bits(efc, tei_s // 8, tei_s % 8, 12)
        tmi = _bits(efc, tmi_s // 8, tmi_s % 8, 5)
        ru = _bits(efc, ru_s // 8, ru_s % 8, 4)
        pw = _bits(efc, pw_s // 8, pw_s % 8, 3)
        _f(table, f"  站点{i} PB个数", f"0x{pb:01X}", str(pb + 1),
           f"{pb+1}个PB块", base + pb_bit // 8, base + (pb_bit + 1 - 1) // 8)
        _f(table, f"  站点{i} TEI", "", f"0x{tei:03X}",
           f"站点TEI = {tei}", base + tei_s // 8, base + (tei_s + 12 - 1) // 8)
        _f(table, f"  站点{i} TMI", f"0x{tmi:02X}", str(tmi),
           "TMI调制编码方案", base + tmi_s // 8, base + (tmi_s + 5 - 1) // 8)
        _f(table, f"  站点{i} RU", f"0x{ru:01X}", str(ru),
           f"RU编号{ru}", base + ru_s // 8, base + (ru_s + 4 - 1) // 8)
        _f(table, f"  站点{i} Tx功率回退", f"0x{pw:01X}", str(pw),
           _TX_POWER_BACKOFF_MAP.get(pw, f"保留({pw})"),
           base + pw_s // 8, base + (pw_s + 3 - 1) // 8)


def _parse_efc_sack(table: list, efc: bytes, station_count: int, base: int):
    """UL-OFDMA SACK eFC (表29). 每站: TEI(12bit) + 接收状态(4bit) + 保留(8bit)
    每站24bit = 3字节，4站刚好12字节，最后1字节保留 + CRC从13开始。"""
    _f(table, "eFC(UL-OFDMA SACK)", _hex(efc[:13]), "13字节(不含CRC)",
       "UL-OFDMA SACK帧eFC", base, base + 12)
    for i in range(station_count):
        off = i * 3  # 每站3字节
        if off + 2 >= 13:
            break
        tei = _bits(efc, off, 0, 8) | (_bits(efc, off + 1, 0, 4) << 8)
        rx_status = _bits(efc, off + 1, 4, 4)
        pb0_ok = (rx_status >> 0) & 1
        pb1_ok = (rx_status >> 1) & 1
        _f(table, f"  站点{i} TEI", _hex(efc[off:off+2]), f"0x{tei:03X}",
           f"站点TEI = {tei}", base + off, base + off + 1)
        _f(table, f"  站点{i} 接收状态", f"0x{rx_status:01X}",
           f"PB0={'OK' if pb0_ok else 'FAIL'}, PB1={'OK' if pb1_ok else 'FAIL'}",
           "每bit对应一个PB的接收结果", base + off + 1, base + off + 1)


def _parse_test_ext_0006(data: bytes, base_offset: int) -> list:
    """0x0006: MAC层OFDMA配置（通感一体版）

    字节3 (data[0]): bit0=OFDMA类型(0:DL 1:UL), bit1-3=调度节点数, bit4-7=保留
    """
    table = []
    if len(data) < 1:
        _f(table, "❌ 解析失败", "", "", "MAC层OFDMA配置数据不足", None, None)
        return table
    ofdma_type = _bits(data, 0, 0, 1)
    node_count = _bits(data, 0, 1, 3)
    reserved = _bits(data, 0, 4, 4)
    type_name = "DL_OFDMA" if ofdma_type == 0 else "UL_OFDMA"
    _f(table, "OFDMA类型", f"0x{ofdma_type:01X}", str(ofdma_type),
       type_name, base_offset, base_offset)
    _f(table, "OFDMA调度节点数", f"0x{node_count:01X}", str(node_count),
       "调度节点数", base_offset, base_offset)
    _f(table, "保留", f"0x{reserved:01X}", str(reserved), "保留",
       base_offset, base_offset)
    _remaining(table, data, 1, base_offset)
    return table


def _parse_test_ext_0007(data: bytes, base_offset: int) -> list:
    """0x0007: 非组网场景TEI配置（通感一体版）

    字节3 (data[0]): TEI低8位
    字节4 (data[1]): TEI高4位(bit0-3) + 保留(bit4-7)
    TEI共12位，小端：低8位在前，高4位在后一字节低4位。
    """
    table = []
    if len(data) < 2:
        _f(table, "❌ 解析失败", "", "", "非组网场景TEI配置数据不足2字节", None, None)
        return table
    tei_lo = data[0]
    tei_hi = data[1] & 0x0F
    tei = (tei_hi << 8) | tei_lo
    reserved = (data[1] >> 4) & 0x0F
    _f(table, "TEI", _hex(data[0:2]), f"0x{tei:03X}",
       f"配置的TEI = {tei}", base_offset, base_offset + 1)
    _f(table, "保留", f"0x{reserved:01X}", str(reserved), "保留",
       base_offset + 1, base_offset + 1)
    _remaining(table, data, 2, base_offset)
    return table


def _parse_test_ext_0008(data: bytes, base_offset: int) -> list:
    """0x0008: 业务报文Bitloading收发开关（通感一体版）

    字节3 (data[0]): bit0=开关, bit1-7=保留
    """
    table = []
    if len(data) < 1:
        _f(table, "❌ 解析失败", "", "", "Bitloading收发开关数据不足", None, None)
        return table
    enable = _bits(data, 0, 0, 1)
    reserved = _bits(data, 0, 1, 7)
    _f(table, "采用Bitloading传输数据", f"0x{enable:01X}", str(enable),
       "0:退出Bitloading模式 1:使用Bitloading模式",
       base_offset, base_offset)
    _f(table, "保留", f"0x{reserved:02X}", str(reserved), "保留",
       base_offset, base_offset)
    _remaining(table, data, 1, base_offset)
    return table


def _parse_test_ext_payload(ext_id: int, data: bytes, base_offset: int) -> list:
    """根据扩展ID分发解析"""
    parsers = {
        0x0001: _parse_test_ext_0001,
        0x0002: _parse_test_ext_0002,
        0x0003: _parse_test_ext_0003,
        0x0004: _parse_test_ext_0004,
        0x0005: _parse_test_ext_0005,
        0x0006: _parse_test_ext_0006,
        0x0007: _parse_test_ext_0007,
        0x0008: _parse_test_ext_0008,
    }
    parser = parsers.get(ext_id)
    if parser:
        return parser(data, base_offset)
    table = []
    _f(table, "扩展数据", _hex(data)[:80] + ("..." if len(data) > 40 else ""),
       f"{len(data)}字节", f"未识别扩展ID 0x{ext_id:04X}数据",
       base_offset, base_offset + len(data) - 1 if data else base_offset)
    return table


def _parse_cmd_test_frame(payload: bytes, direction: int, base_offset: int) -> list:
    """0xF0 测试帧"""
    table = []
    if direction == 1:
        _f(table, "上行负载", "", "", "测试帧上行为确认/否认，无数据单元",
           base_offset, base_offset + len(payload) - 1 if payload else base_offset)
        return table
    if len(payload) < 4:
        _f(table, "❌ 解析失败", "", "", "测试帧下行业务数据不足", None, None)
        return table
    test_id = payload[0]
    _f(table, "测试ID", f"0x{test_id:02X}", str(test_id),
       _TEST_ID_MAP.get(test_id, f"保留(0x{test_id:02X})"),
       base_offset, base_offset)
    _f(table, "保留", f"0x{payload[1]:02X}", str(payload[1]), "保留",
       base_offset + 1, base_offset + 1)
    data_len = _uint16_le(payload, 2)
    _f(table, "数据区长度", _hex(payload[2:4]), str(data_len), "测试数据区长度",
       base_offset + 2, base_offset + 3)
    offset = 4
    if test_id == 0x04:
        # 2.0测试：APP_TEST_MODE_SPLC 结构
        if data_len < 4:
            _f(table, "❌ 解析失败", "", "", "2.0测试数据区长度不足4字节", None, None)
            return table
        if offset + data_len > len(payload):
            _f(table, "❌ 解析失败", "", "", "2.0测试数据区超出负载", None, None)
            return table
        agreeon_ver = payload[offset]
        file_len = payload[offset + 1]
        ext_id = _uint16_le(payload, offset + 2)
        _f(table, "协议版本号", f"0x{agreeon_ver:02X}", str(agreeon_ver), "协商版本号",
           base_offset + offset, base_offset + offset)
        _f(table, "文件长度", f"0x{file_len:02X}", str(file_len), "文件长度/配置长度",
           base_offset + offset + 1, base_offset + offset + 1)
        _f(table, "扩展ID", _hex(payload[offset + 2:offset + 4]), str(ext_id),
           _TEST_EXT_ID_MAP.get(ext_id, f"保留扩展ID(0x{ext_id:04X})"),
           base_offset + offset + 2, base_offset + offset + 3)
        ext_offset = offset + 4
        ext_data = payload[ext_offset:offset + data_len]
        ext_table = _parse_test_ext_payload(ext_id, ext_data, base_offset + ext_offset)
        table.extend(ext_table)
        offset += data_len
    else:
        if data_len > 0 and offset + data_len <= len(payload):
            data = payload[offset:offset + data_len]
            if test_id in (0x00, 0x01, 0x02) and data_len == 1:
                band = data[0]
                desc = f"通信频段: 0x{band:02X}"
                _f(table, "测试数据区", _hex(data),
                   f"{data_len}字节", desc,
                   base_offset + offset, base_offset + offset + data_len - 1)
            elif test_id == 0x03:
                # 1.0测试数据区（原有扩展命令格式，表61）
                table.extend(_parse_legacy_ext_cmd(data, base_offset + offset))
            else:
                desc = "测试数据区"
                _f(table, "测试数据区", _hex(data)[:80] + ("..." if data_len > 40 else ""),
                   f"{data_len}字节", desc,
                   base_offset + offset, base_offset + offset + data_len - 1)
            offset += data_len
    _remaining(table, payload, offset, base_offset)
    return table


# ── 原有扩展命令格式（表61）：1.0测试数据区 ──

_LEGACY_TEST_MODE_MAP = {
    1: "转发应用层报文至应用层串口信道测试模式",
    2: "转发应用层报文至载波信道测试模式",
    3: "PLC物理层透传测试模式",
    4: "PLC物理层回传测试模式",
    5: "MAC层透传测试模式",
    6: "频段切换操作",
    7: "ToneMask配置操作",
    8: "无线信道切换操作",
    9: "RF物理层回传测试模式",
    10: "RF物理层透传测试模式",
    11: "RF/PLC物理层回传测试模式",
    12: "PLC到RF物理层回传测试模式",
    13: "安全测试模式",
    15: "新一代扩展测试模式",
}


def _parse_legacy_ext_cmd(data: bytes, base: int) -> list:
    """解析原有扩展命令格式数据区（表61，8字节结构）

    域                字节  比特位  大小
    协议版本号        0     0-5     6
    报文头长度        0     6-7     2
    测试模式/配置操作 1     4-7     4
    转发数据规约类型  2     0-3     4
    转发数据长度/持续时间/配置值  2-3  4-7+0-7  12
    安全测试模式      4     0-3     4
    保留/PHR_MCS      4     4-7     4
    保留/PSDU_MCS     5     0-3     4
    保留/PbSIZE       5     4-7     4
    """
    table = []
    if len(data) < 2:
        _f(table, "❌ 解析失败", "", "", "原有扩展命令数据不足（<2字节）", base, base + len(data) - 1)
        return table

    # 字节0: 协议版本号(bit0-5) + 报文头长度(bit6-7)
    ver = data[0] & 0x3F
    hdr_len = (data[0] >> 6) & 0x03
    _f(table, "协议版本号", f"0x{ver:02X}", str(ver), "原有扩展命令协议版本号", base, base)
    _f(table, "报文头长度", f"0x{hdr_len:02X}", str(hdr_len), "报文头长度(2bit)", base, base)

    if len(data) < 6:
        # 数据不足时只解析已存在字段
        _f(table, "剩余数据", _hex(data[1:]), f"{len(data)-1}字节",
           "原有扩展命令数据不足（需6字节），仅显示原始数据", base + 1, base + len(data) - 1)
        return table

    # 字节1: 测试模式/配置操作(bit4-7)，低4位保留
    b1 = data[1]
    test_mode = (b1 >> 4) & 0x0F
    reserved1 = b1 & 0x0F
    mode_name = _LEGACY_TEST_MODE_MAP.get(test_mode, f"保留({test_mode})")
    _f(table, "测试模式/配置操作", f"0x{test_mode:02X}", str(test_mode),
       f"{mode_name}（高4位）", base + 1, base + 1)
    _f(table, "  保留", f"0x{reserved1:01X}", str(reserved1), "字节1低4位保留", base + 1, base + 1)

    # 字节2: 转发数据规约类型(bit0-3) + 数据长度12bit高4位(bit4-7)
    b2 = data[2]
    proto_type = b2 & 0x0F
    _f(table, "转发数据规约类型", f"0x{proto_type:01X}", str(proto_type),
       "转发数据的规约类型（低4位）", base + 2, base + 2)

    # 数据长度 12bit: (字节2 bit4-7)<<8 | 字节3
    b3 = data[3]
    data_len12 = ((b2 >> 4) & 0x0F) << 8 | b3
    # 依据测试模式区分字段含义：3/4/5/9/10/11/12=持续时间(分)，6/8=Option+信道号，7=ToneMask
    len_desc = "转发数据长度/模式持续时间"
    parsed_val = str(data_len12)
    if test_mode in (3, 4, 5, 9, 10, 11, 12):
        len_desc = f"测试模式持续时间: {data_len12} 分钟"
    elif test_mode in (6, 8):
        # 切频(频段切换)/无线信道切换：目标为 Option(字节2 bit4-7) + 信道号(字节3)
        opt = (b2 >> 4) & 0x0F
        ch = b3
        parsed_val = f"Option={opt}, 信道号={ch}"
        len_desc = f"无线信道切换目标: Option={opt}, 信道号={ch}"
        _f(table, "  Option值", f"0x{opt:02X}", str(opt), "无线信道切换Option值", base + 2, base + 2)
        _f(table, "  无线信道号", f"0x{ch:02X}", str(ch), "无线信道切换信道号", base + 3, base + 3)
    elif test_mode == 7:
        len_desc = f"目标ToneMask: {data_len12}"
    else:
        len_desc = f"转发数据长度/模式持续时间: {data_len12}"
    _f(table, "转发数据长度/模式持续时间", f"{b2:02X} {b3:02X}", parsed_val,
       len_desc, base + 2, base + 3)

    # 字节4: 安全测试模式(bit0-3) + PHR_MCS(bit4-7)
    b4 = data[4]
    sec_mode = b4 & 0x0F
    phr_mcs = (b4 >> 4) & 0x0F
    _f(table, "安全测试模式", f"0x{sec_mode:01X}", str(sec_mode),
       "安全测试模式（仅测试模式13生效）", base + 4, base + 4)
    _f(table, "  PHR_MCS", f"0x{phr_mcs:01X}", str(phr_mcs),
       "PHR_MCS（仅测试模式12生效）", base + 4, base + 4)

    # 字节5: PSDU_MCS(bit0-3) + PbSIZE(bit4-7)
    if len(data) >= 6:
        b5 = data[5]
        psdu_mcs = b5 & 0x0F
        pb_size = (b5 >> 4) & 0x0F
        _f(table, "  PSDU_MCS", f"0x{psdu_mcs:01X}", str(psdu_mcs),
           "PSDU_MCS（仅测试模式12生效）", base + 5, base + 5)
        _f(table, "  PbSIZE", f"0x{pb_size:01X}", str(pb_size),
           "PbSIZE（仅测试模式12生效）", base + 5, base + 5)

    # 超过6字节的剩余数据
    if len(data) > 6:
        _f(table, "剩余数据", _hex(data[6:]), f"{len(data)-6}字节",
           "原有扩展命令超出6字节的剩余数据", base + 6, base + len(data) - 1)
    return table


# ── 公共入口 ──
def parse_command_payload(
    payload: bytes,
    service_id: int,
    direction: int,
    msg_port: int,
    base_offset: int
) -> list:
    """解析命令帧业务数据单元"""
    parsers = {
        0x00: _parse_cmd_search_result,
        0x01: _parse_cmd_send_search_list,
        0x02: _parse_cmd_file_transfer,
        0x03: _parse_cmd_event_control,
        0x04: _parse_cmd_node_restart,
        0x05: _parse_cmd_node_info_query,
        0x06: _parse_cmd_address_mapping,
        0x07: _parse_cmd_node_status_query,
        0x08: _parse_cmd_channel_info,
        0x09: _parse_cmd_module_run_params,
        0x10: _parse_cmd_district_phase,
        0xF0: _parse_cmd_test_frame,
    }
    parser = parsers.get(service_id)
    if parser:
        return parser(payload, direction, base_offset)
    return []
