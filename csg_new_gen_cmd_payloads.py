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
}


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
    if data_len > 0 and offset + data_len <= len(payload):
        data = payload[offset:offset + data_len]
        band = data[0] if data else None
        band_desc = f"通信频段: 0x{band:02X}" if band is not None else ""
        _f(table, "测试数据区", _hex(data)[:80] + ("..." if data_len > 40 else ""),
           f"{data_len}字节", band_desc,
           base_offset + offset, base_offset + offset + data_len - 1)
        offset += data_len
    _remaining(table, payload, offset, base_offset)
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
