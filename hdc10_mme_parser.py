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




def _tei_bitmap_rows(bitmap: bytes, base_offset: int,
                     label: str = "发现站点位图") -> List[Tuple]:
    """TEI 位图 → 统计行 + 逐 TEI 编号明细行

    bit i 置1 ↔ TEI=i (LSB 在前)。每行16个TEI, [✓n]有效。
    返回行列表(可能为空, 位图为空时不产生行)。
    """
    rows: List[Tuple] = []
    total_bits = len(bitmap) * 8
    if total_bits == 0:
        return rows
    teis = [i for i in range(total_bits) if bitmap[i >> 3] & (1 << (i & 7))]
    rows.append((
        f"    {label}",
        ' '.join(f'{b:02X}' for b in bitmap[:12]) + ("..." if len(bitmap) > 12 else ""),
        f"{len(teis)}个站点",
        f"{len(bitmap)}字节, 每bit对应一个TEI(bit n=TEI n, LSB在前)",
        base_offset, base_offset + len(bitmap) - 1,
    ))
    per_row = 16
    for start in range(0, total_bits, per_row * 4):
        chunk_teis = [t for t in teis if start <= t < start + per_row * 4]
        if not chunk_teis:
            continue
        cells = "".join(f"[✓{t}]" for t in chunk_teis)
        rows.append((
            f"      位图明细TEI{chunk_teis[0]}-{chunk_teis[-1]}",
            "",
            cells,
            f"{len(chunk_teis)}个可发现站点",
            base_offset + (chunk_teis[0] >> 3),
            base_offset + (chunk_teis[-1] >> 3),
        ))
    return rows


def _tei12(data: bytes, pos: int) -> int:
    """读12bit小端TEI: data[pos]低8b | data[pos+1]低4b<<8"""
    return data[pos] | ((data[pos + 1] & 0x0F) << 8)


 
def parse_management_message(data: bytes, offset: int = 0) -> List[Tuple]:
    """解析网络管理消息 (MSDU类型0时调用"""
    table = []
    if len(data) - offset < 3:
        table.append(("❌ 管理消息解析失败", "", "", "长度不足3字节",
                      offset, offset + len(data) - offset - 1))
        return table

    # MMTYPE (2字节小端)
    mmtype = int.from_bytes(data[offset:offset + 2], 'little')
    # 保留字段（2字节, 表58: MMTYPE 2B + 保留 2B = 4字节头）
    reserved = int.from_bytes(data[offset + 2:offset + 4], 'little')

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
        ' '.join(f'{b:02X}' for b in data[offset + 2:offset + 4]),
        f"0x{reserved:04X}",
        "保留字段(2字节)",
        offset + 2, offset + 3,
    ))

    # 报文内容 (表58: MME头4字节)
    content_offset = offset + 4
    content = data[content_offset:]

    if content:
        # content 已切片, 子解析器 offset 传 0(相对), 行偏移由 content_offset 统一加在显示列
        content_table = _parse_mme_content(content, 0, mmtype)
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
    """关联请求 (0x0000, 表60): 站点MAC(6B) + 候选代理TEI×5(每条2B: TEI12b+链路类型1b+保留3b)"""
    table = []
    end = len(data)
    table.append(("  关联请求", "", "", "STA向CCO请求关联(表60)", offset, offset + end - 1))
    if end < 6:
        table.append(("    数据不足", "", f"{end}字节", "站点MAC需6字节",
                      offset, offset + max(end - 1, offset)))
        return table

    mac = data[0:6]
    table.append(("    站点MAC地址",
                  ' '.join(f'{b:02X}' for b in mac),
                  ':'.join(f'{b:02X}' for b in mac),
                  "请求关联的站点MAC(大端)", offset, offset + 5))

    pos = 6
    for i in range(5):
        if pos + 2 > end:
            break
        tei = _tei12(data, pos)
        link = (data[pos + 1] >> 4) & 0x01
        if tei == 0 and i > 0:
            pos += 2
            continue
        table.append((f"    候选代理{i + 1}",
                      ' '.join(f'{b:02X}' for b in data[pos:pos + 2]),
                      f"TEI={tei}",
                      f"链路类型={'无线' if link else '载波'}",
                      offset + pos, offset + pos + 1))
        pos += 2

    if pos < end:
        rest = data[pos:]
        table.append(("    其他信息",
                      ' '.join(f'{b:02X}' for b in rest[:16]) + ("..." if len(rest) > 16 else ""),
                      f"{len(rest)}字节", "厂商扩展/附加信息",
                      offset + pos, offset + end - 1))

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



def _parse_comm_success_rate(data: bytes, offset: int) -> List[Tuple]:
    """通信成功率 (0x0009)"""
    table = []
    table.append(("  通信成功率", "", "", "通信成功率统计", offset, offset + len(data) - 1))
    table.append(("    原始数据",
                  ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
                  f"{len(data)}字节", "通信成功率数据",
                  offset, offset + min(len(data), 16) - 1))
    return table


def _parse_heartbeat(data: bytes, offset: int) -> List[Tuple]:
    """心跳检测 (0x0007, 表94)

    原始源TEI(12b) | 发现站点数最大站点TEI(12b) | 最大发现站点数(2B) | 位图大小(2B) | 发现站点位图
    """
    table = []
    end = len(data)
    table.append(("  心跳检测", "", "", "心跳检测报文(表94)", offset, offset + end - 1))
    if end < 8:
        if end:
            table.append(("    数据不足", "", f"{end}字节", "表94固定头需8字节",
                          offset, offset + end - 1))
        return table

    ostei = _tei12(data, 0)
    max_tei = _tei12(data, 2)
    table.append(("    原始源TEI", ' '.join(f'{b:02X}' for b in data[0:2]), str(ostei),
                  "初始产生报文的站点TEI(转发时不变)", offset, offset + 1))
    table.append(("    发现站点数最大站点TEI", ' '.join(f'{b:02X}' for b in data[2:4]),
                  str(max_tei), "沿途转发站点中周围站点数最多的站点", offset + 2, offset + 3))

    import struct
    max_cnt = struct.unpack('<H', data[4:6])[0]
    bmp_size = struct.unpack('<H', data[6:8])[0]
    table.append(("    最大的发现站点数", ' '.join(f'{b:02X}' for b in data[4:6]),
                  str(max_cnt), "最多站点发现的周围站点数量", offset + 4, offset + 5))
    table.append(("    位图大小", ' '.join(f'{b:02X}' for b in data[6:8]),
                  f"{bmp_size}字节", "发现站点位图字段大小", offset + 6, offset + 7))

    bmp_start = offset + 8
    bmp = data[8:8 + bmp_size]
    if len(bmp) < bmp_size:
        table.append(("    ⚠ 位图数据不足", "", f"声明{bmp_size}字节",
                      f"实际仅{len(bmp)}字节", bmp_start, offset + end - 1))
    table.extend(_tei_bitmap_rows(bmp, bmp_start, "发现站点位图"))
    return table


_ROUTE_TYPE_NAMES = {0: "错误路由", 1: "同级路由", 2: "上级路由",
                     3: "代理主路径", 4: "上上级路由"}


def _parse_discovery_list(data: bytes, offset: int) -> List[Tuple]:
    """发现列表 (0x0008, 表95)

    固定头32B + [上行路由条目信息 × 路由条目总数(2B/条)]
             + 发现站点列表位图(位图大小B)
             + 接收发现列表信息(与位图置位TEI一一对应, 1B/个)
    """
    table = []
    end = len(data)
    table.append(("  发现列表", "", "", "发现列表报文(表95)", offset, offset + end - 1))
    if end < 32:
        table.append(("    数据不足", "", f"{end}字节", "表95固定头需32字节",
                      offset, offset + max(end - 1, offset)))
        return table

    tei = _tei12(data, 0)
    # 代理TEI 12b: byte1高4b(低4位) + byte2(高8位), 表95
    ptei = ((data[1] >> 4) & 0x0F) | (data[2] << 4)
    role = data[3] & 0x0F
    level = (data[3] >> 4) & 0x0F
    mac = data[4:10]
    cco_mac = data[10:16]
    phase_bits = data[16]
    ch_quality = data[17]
    up_rate = data[18]
    down_rate = data[19]
    sta_total = int.from_bytes(data[20:22], 'little')
    sent_cnt = data[22]
    route_total = data[23]
    route_remain = int.from_bytes(data[24:26], 'little')
    bmp_size = int.from_bytes(data[26:28], 'little')
    min_rate = data[28]
    phase_names = {0: "A相", 1: "B相", 2: "C相", 3: "保留"}

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    _r("TEI", ' '.join(f'{b:02X}' for b in data[0:2]), str(tei), "发送站点TEI(12b)", 0, 1)
    _r("代理TEI", ' '.join(f'{b:02X}' for b in data[1:3]), str(ptei), "代理站点TEI(12b)", 1, 2)
    _r("角色", f"0x{role:02X}", str(role), "站点角色", 2, 2)
    _r("层级", f"0x{(data[3] >> 4) & 0x0F:01X}", str((data[3] >> 4) & 0x0F),
       "网络层级(高4b)", 3, 3)
    _r("MAC地址", ' '.join(f'{b:02X}' for b in mac),
       ':'.join(f'{b:02X}' for b in mac), "发送站点MAC(大端)", 4, 9)
    _r("CCO MAC地址", ' '.join(f'{b:02X}' for b in cco_mac),
       ':'.join(f'{b:02X}' for b in cco_mac), "本网络CCO MAC(大端)", 10, 15)
    ph = [(phase_bits >> (i * 2)) & 0x03 for i in range(3)]
    _r("相线评估", f"0x{phase_bits:02X}",
       "/".join(phase_names.get(p, "?") for p in ph),
       "按可能性排序的三个相线评估(各2b)", 16, 16)
    _r("代理站点信道质量", f"0x{ch_quality:02X}", str(ch_quality),
       "接收代理报文的原始信噪比", 17, 17)
    _r("代理通信成功率", f"0x{up_rate:02X}", f"{up_rate}%", "与代理上下行成功率", 18, 18)
    _r("代理下行成功率", f"0x{down_rate:02X}", f"{down_rate}%", "接收代理下行报文成功率", 19, 19)
    _r("站点总数", ' '.join(f'{b:02X}' for b in data[20:22]), str(sta_total),
       "携带发现站点信息的站点数量", 20, 21)
    _r("发送发现列表个数", f"0x{sent_cnt:02X}", str(sent_cnt),
       "上个路由周期发送的发现列表总数", 22, 22)
    _r("上行路由条目总数", f"0x{route_total:02X}", str(route_total),
       "到CCO的路由表项数(最大5)", 23, 23)
    _r("路由周期剩余时间", ' '.join(f'{b:02X}' for b in data[24:26]),
       f"{route_remain}s", "距当前路由周期到期剩余秒数", 24, 25)
    _r("位图大小", ' '.join(f'{b:02X}' for b in data[26:28]),
       f"{bmp_size}字节", "发现站点列表位图字段大小", 26, 27)
    _r("最小通信成功率", f"0x{min_rate:02X}", f"{min_rate}%",
       "到CCO路径最弱连接成功率", 28, 28)
    _r("保留", ' '.join(f'{b:02X}' for b in data[29:32]), "3字节", "保留", 29, 31)

    # ── 变长区1: 上行路由条目信息(每条2B: 下一跳TEI 12b + 路由类型 4b, 表97/98) ──
    pos = 32
    for i in range(route_total):
        if pos + 2 > end:
            break
        nh_tei = _tei12(data, pos)
        rt = (data[pos + 1] >> 4) & 0x07
        table.append((f"    上行路由{i + 1}",
                      ' '.join(f'{b:02X}' for b in data[pos:pos + 2]),
                      f"下一跳TEI={nh_tei}",
                      f"类型={_ROUTE_TYPE_NAMES.get(rt, f'保留({rt})')}",
                      offset + pos, offset + pos + 1))
        pos += 2

    # ── 变长区2: 发现站点列表位图(锚点: 位图大小) ──
    bmp = data[pos:pos + bmp_size]
    bmp_short = len(bmp) < bmp_size
    if bmp_short:
        table.append(("    ⚠ 位图数据不足", "", f"声明{bmp_size}字节",
                      f"实际仅{len(bmp)}字节", offset + pos, offset + end - 1))
    teis = [i for i in range(len(bmp) * 8) if bmp[i >> 3] & (1 << (i & 7))]
    table.extend(_tei_bitmap_rows(bmp, offset + pos, "发现站点列表位图"))
    pos += len(bmp)

    # ── 变长3: 接收发现列表信息(与位图置位TEI按顺序一一配对, 表99) ──
    recv = data[pos:]
    n_pair = min(len(recv), len(teis))
    if teis and recv:
        pairs = " ".join(
            f"[TEI{teis[i]}←{recv[i]}]" for i in range(n_pair))
        table.append((
            "    接收发现列表信息",
            ' '.join(f'{b:02X}' for b in recv[:12]) + ("..." if len(recv) > 12 else ""),
            pairs[:120],
            f"{n_pair}项, 按位图置位TEI顺序对应(收到该站点的发现报文数)",
            offset + pos, offset + pos + n_pair - 1,
        ))
        pos += n_pair
    elif not recv and teis:
        table.append(("    ⚠ 接收发现列表信息缺失", "",
                      f"{len(teis)}个置位TEI无对应计数",
                      "数据在位图后结束", offset + pos, offset + end - 1))
    if pos < end:
        remain = data[pos:]
        table.append(("    未解析剩余", ' '.join(f'{b:02X}' for b in remain[:12]),
                      f"{len(remain)}字节", "超出结构的剩余数据",
                      offset + pos, offset + end - 1))
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
        # 发现列表消息(表95): 复用深度解析
        table.extend(_parse_discovery_list(data, offset))
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
