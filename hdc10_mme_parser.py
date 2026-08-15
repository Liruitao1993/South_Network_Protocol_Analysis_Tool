"""
HDC 1.0 网络管理消息 (MME) 解析器

管理消息头:
  - MMTYPE: 2字节小端
  - 保留: 1字节
  - 报文内容
"""

from typing import List, Tuple


# MME 消息类型（表42）
MME_TYPE_NAMES = {
    0x0000: "关联请求",
    0x0001: "关联确认",
    0x0002: "关联汇总",
    0x0003: "代理变更请求",
    0x0004: "代理变更确认",
    0x0005: "代理变更确认(位图版)",
    0x0006: "离线指示",
    0x0007: "心跳检测",
    0x0008: "发现列表",
    0x0009: "通信成功率",
    0x000A: "网络冲突",
    0x000B: "过零NTB采集",
    0x000C: "过零NTB上报",
    0x004F: "网络诊断",
    0x0080: "无线信道冲突",
}


def parse_management_message(data: bytes, offset: int = 0) -> List[Tuple]:
    """解析网络管理消息 (MSDU类型0时调用"""
    table = []
    if len(data) - offset < 3:
        table.append(("❌ 管理消息解析失败", "", "", "长度不足3字节",
                      offset, offset + len(data) - offset - 1))
        return table

    # MMTYPE (2字节小端)
    mmtype = int.from_bytes(data[offset:offset + 2], 'little')
    # 保留字段（1字节）
    reserved = data[offset + 2]

    name = MME_TYPE_NAMES.get(mmtype, f"保留(0x{mmtype:04X})")

    table.append((
        "── 网络管理消息 ──",
        "",
        f"{len(data) - offset}字节",
        f"MMTYPE: 0x{mmtype:04X} ({name})",
        offset, offset + len(data) - offset - 1,
    ))
    table.append((
        "  消息类型(MMTYPE)",
        ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
        f"0x{mmtype:04X}",
        name,
        offset, offset + 1,
    ))
    table.append((
        "  保留",
        f"0x{reserved:02X}",
        str(reserved),
        "保留字段",
        offset + 2, offset + 2,
    ))

    # 报文内容
    content_offset = offset + 3
    content = data[content_offset:]

    if content:
        content_table = _parse_mme_content(content, content_offset, mmtype)
        table.extend(content_table)

    return table


def _parse_mme_content(data: bytes, offset: int, mmtype: int) -> List[Tuple]:
    """按消息类型解析报文内容"""
    table = []

    if mmtype == 0x0000:
        table = _parse_associate_req(data, offset)
    elif mmtype == 0x0001:
        table = _parse_associate_cnf(data, offset)
    elif mmtype == 0x0006:
        table = _parse_leave_ind(data, offset)
    elif mmtype == 0x0007:
        table = _parse_heartbeat(data, offset)
    elif mmtype == 0x0008:
        table = _parse_discovery_list(data, offset)
    elif mmtype == 0x0002:
        table = _parse_associate_summary(data, offset)
    elif mmtype == 0x0009:
        table = _parse_comm_success_rate(data, offset)
    elif mmtype == 0x000A:
        table = _parse_network_conflict(data, offset)
    else:
        # 未知类型
        show = data[:24]
        table.append((
            "  消息内容",
            ' '.join(f'{b:02X}' for b in show) + ("..." if len(data) > 24 else ""),
            f"{len(data)}字节",
            f"未解析的管理消息内容(0x{mmtype:04X})",
            offset, offset + min(len(data), 24) - 1,
        ))

    return table


def _parse_associate_req(data: bytes, offset: int) -> List[Tuple]:
    """关联请求 (0x0000)"""
    table = []
    if len(data) < 8:
        return [("  关联请求(过短)", "", "", "长度不足", offset, offset + len(data) - 1)]

    # 简化实现: TEI(2) + MAC(6) + 能力(...)
    tei = int.from_bytes(data[0:2], 'little')
    mac = data[2:8]

    table.append(("  关联请求", "", "", "STA向CCO请求关联", offset, offset + len(data) - 1))
    table.append(("    请求TEI", f"0x{tei:04X}", str(tei),
                  f"请求的TEI: {tei}", offset, offset + 1))
    table.append(("    站点MAC地址",
                  ' '.join(f'{b:02X}' for b in mac),
                  ':'.join(f'{b:02X}' for b in mac),
                  "站点MAC地址(大端)", offset + 2, offset + 7))

    if len(data) > 8:
        rest = data[8:]
        table.append(("    其他信息",
                      ' '.join(f'{b:02X}' for b in rest[:16]) + ("..." if len(rest) > 16 else ""),
                      f"{len(rest)}字节", "关联请求附加信息",
                      offset + 8, offset + 8 + len(rest) - 1))

    return table


def _parse_associate_cnf(data: bytes, offset: int) -> List[Tuple]:
    """关联确认 (0x0001)"""
    table = []
    if len(data) < 2:
        return [("  关联确认(过短)", "", "", "长度不足", offset, offset + len(data) - 1)]

    result = data[0]
    result_names = {0: "成功", 1: "拒绝"}
    tei = int.from_bytes(data[0:2], 'little') & 0x0FFF  # 假设低12位是TEI，高4位是结果
    # 更可能的结构：结果码 + TEI，需要参考文档
    table.append(("  关联确认", "", "", "CCO对关联请求的确认", offset, offset + len(data) - 1))
    table.append(("    结果", f"0x{result:02X}", str(result),
                  result_names.get(result, f"未知({result})"), offset, offset))
    if len(data) >= 2:
        info = data[1:]
        table.append(("    确认信息",
                      ' '.join(f'{b:02X}' for b in info[:16]) + ("..." if len(info) > 16 else ""),
                      f"{len(info)}字节", "关联确认详细信息",
                      offset + 1, offset + 1 + len(info) - 1))
    return table


def _parse_associate_summary(data: bytes, offset: int) -> List[Tuple]:
    """关联汇总 (0x0002)"""
    table = []
    table.append(("  关联汇总", "", "", "关联汇总消息", offset, offset + len(data) - 1))
    table.append(("    原始数据",
                  ' '.join(f'{b:02X}' for b in data[:24]) + ("..." if len(data) > 24 else ""),
                  f"{len(data)}字节", "关联汇总数据",
                  offset, offset + min(len(data), 24) - 1))
    return table


def _parse_leave_ind(data: bytes, offset: int) -> List[Tuple]:
    """离线指示 (0x0006)"""
    table = []
    table.append(("  离线指示", "", "", "站点离线指示", offset, offset + len(data) - 1))
    if len(data) >= 2:
        tei = int.from_bytes(data[0:2], 'little')
        table.append(("    离线站点TEI", f"0x{tei:04X}", str(tei),
                      f"离线站点TEI: {tei}", offset, offset + 1))
    if len(data) > 2:
        rest = data[2:]
        table.append(("    原因/信息",
                      ' '.join(f'{b:02X}' for b in rest[:16]) + ("..." if len(rest) > 16 else ""),
                      f"{len(rest)}字节", "离线原因等信息",
                      offset + 2, offset + 2 + len(rest) - 1))
    return table


def _parse_heartbeat(data: bytes, offset: int) -> List[Tuple]:
    """心跳检测 (0x0007)"""
    table = []
    table.append(("  心跳检测", "", "", "心跳检测报文", offset, offset + len(data) - 1))
    if data:
        table.append(("    心跳数据",
                      ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
                      f"{len(data)}字节", "心跳检测内容",
                      offset, offset + min(len(data), 16) - 1))
    return table


def _parse_discovery_list(data: bytes, offset: int) -> List[Tuple]:
    """发现列表 (0x0008)"""
    table = []
    table.append(("  发现列表", "", "", "发现列表消息", offset, offset + len(data) - 1))
    if len(data) >= 1:
        count = data[0]
        table.append(("    站点数量", f"0x{count:02X}", str(count),
                      f"发现站点数: {count}", offset, offset))
        # 每个站点条目
        pos = 1
        idx = 0
        while pos + 8 <= len(data) and idx < count:
            entry = data[pos:pos + 8]
            table.append((f"    站点[{idx}]",
                          ' '.join(f'{b:02X}' for b in entry),
                          "", f"站点{idx}: TEI/MAC信息", offset + pos, offset + pos + 7))
            pos += 8
            idx += 1
    return table


def _parse_comm_success_rate(data: bytes, offset: int) -> List[Tuple]:
    """通信成功率 (0x0009)"""
    table = []
    table.append(("  通信成功率", "", "", "通信成功率统计", offset, offset + len(data) - 1))
    table.append(("    原始数据",
                  ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
                  f"{len(data)}字节", "通信成功率数据",
                  offset, offset + min(len(data), 16) - 1))
    return table


def _parse_network_conflict(data: bytes, offset: int) -> List[Tuple]:
    """网络冲突 (0x000A)"""
    table = []
    table.append(("  网络冲突", "", "", "网络冲突检测", offset, offset + len(data) - 1))
    table.append(("    冲突信息",
                  ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
                  f"{len(data)}字节", "冲突网络冲突信息",
                  offset, offset + min(len(data), 16) - 1))
    return table


def parse_singlehop_msdu(data: bytes, offset: int, msg_type: int) -> List[Tuple]:
    """解析单跳帧MSDU（无线发现列表等）"""
    table = []
    type_names = {
        0: "发现列表消息",
        128: "应用层报文",
        129: "IPV4报文",
    }
    name = type_names.get(msg_type, f"保留({msg_type})")

    table.append((
        "── 单跳MSDU ──",
        "",
        f"{len(data) - offset}字节",
        f"类型: 0x{msg_type:02X} ({name})",
        offset, offset + len(data) - offset - 1,
    ))

    if msg_type == 0:
        # 发现列表消息
        table.append(("  发现列表",
                   ' '.join(f'{b:02X}' for b in data[offset:offset+16]) +
                   ("..." if len(data) - offset > 16 else ""),
                   f"{len(data) - offset}字节",
                   "无线发现列表",
                   offset, offset + min(len(data) - offset, 16) - 1))
    elif msg_type == 128:
        # 应用层报文，复用应用层解析
        from hdc10_parser import HDC10Parser
        parser = HDC10Parser()
        app_data = data[offset:]
        app_table = parser._parse_application_layer(app_data, offset)
        table.extend(app_table)
    else:
        table.append(("  数据",
                      ' '.join(f'{b:02X}' for b in data[offset:offset+16]) +
                      ("..." if len(data) - offset > 16 else ""),
                      f"{len(data) - offset}字节",
                      f"单跳MSDU数据",
                      offset, offset + min(len(data) - offset, 16) - 1))

    return table
