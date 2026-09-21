"""
HDC 1.0 网络管理消息 (MME) 解析器

管理消息头:
  - MMTYPE: 2字节小端
  - 保留: 1字节
  - 报文内容
"""

from typing import List, Tuple


# MME 消息类型（表59，Q/GDW 12087.42 第4-2部分 §5.1.3）
MME_TYPE_NAMES = {
    0x0000: "关联请求",
    0x0001: "关联确认",
    0x0002: "关联汇总指示",
    0x0003: "代理变更请求",
    0x0004: "代理变更确认",
    0x0005: "代理变更确认(位图版)",
    0x0006: "离线指示",
    0x0007: "心跳检测",
    0x0008: "发现列表",
    0x0009: "通信成功率上报",
    0x000A: "网络冲突上报",
    0x000B: "过零NTB采集指示",
    0x000C: "过零NTB告知",
    0x004F: "网络诊断",
    0x0050: "路由请求",
    0x0051: "路由回复",
    0x0052: "路由错误",
    0x0053: "路由应答",
    0x0054: "链路确认请求",
    0x0055: "链路确认回应",
    0x0080: "无线信道冲突上报",
}

# 无线发现列表（单跳帧 MSDU 类型 0，表123 起），仅在单跳通道出现，
# 无独立 MMTYPE；解析入口 parse_singlehop_msdu。

# ── 通用枚举（逐字摘自规范） ─────────────────────────────────────
_LINK_TYPE_NAMES = {0: "高速载波链路", 1: "无线链路"}
_BAND_NAMES = {0: "1.953~11.96MHz", 1: "2.441~5.615MHz",
               2: "0.781~2.930MHz", 3: "1.758~2.930MHz"}
_ROUTE_TYPE_NAMES = {0: "错误路由", 1: "同级路由", 2: "上级路由",
                     3: "代理主路径", 4: "上上级路由"}

# 关联确认结果（表71）
_ASSOC_CNF_RESULT_NAMES = {
    0x00: "关联请求成功",
    0x01: "站点不在白名单中",
    0x02: "站点在黑名单中",
    0x03: "加入站点个数超过上限",
    0x04: "未设置白名单列表",
    0x05: "代理站点个数超过上限",
    0x06: "子站点个数超过上限",
    0x08: "重复的MAC地址",
    0x09: "超过拓扑层级",
    0x0A: "站点再次关联请求入网成功",
    0x0B: "新站点试图以自己的子站点为代理入网",
    0x0C: "组网拓扑中存在环路",
    0x0D: "CCO端未知原因出错",
    0x0E: "无线代理达到上限",
}

# 代理变更结果（表85/表89）
_CHANGE_RESULT_NAMES = {0: "变更成功"}

# 代理变更原因（表82）
_CHANGE_REASON_NAMES = {0: "未知", 1: "周期代理变更"}

# 离线原因（表92）
_LEAVE_REASON_NAMES = {
    0: "CCO通知站点立即离线",
    1: "网络拓扑层级超过上限",
    2: "站点不在最新白名单中",
}

# 过零NTB采集站点（表105）/采集周期（表106）
_NTB_COLLECT_SITE_NAMES = {0: "指定单站点采集", 1: "指定全网站点采集"}
_NTB_COLLECT_PERIOD_NAMES = {0: "二分之一电力线周期(10ms)", 1: "一个电力线周期(20ms)"}

# 网络诊断芯片厂商ID（表110）
_CHIP_VENDOR_NAMES = {
    0x0000: "保留", 0x0001: "HS", 0x0002: "ES", 0x0003: "TC", 0x0004: "LH",
    0x0005: "HT", 0x0006: "RS", 0x0007: "SW", 0x0008: "SC", 0x0009: "YM",
    0x000A: "QJ", 0x000B: "HZ", 0x000C: "ZC", 0x000D: "SP", 0x000E: "PE",
    0x000F: "NR", 0x0010: "SL", 0x0011: "MT", 0x0012: "SI", 0x0013: "RS",
    0x0014: "XY",
}

# 路由类负载数据类型（表112/表115）
_PAYLOAD_TYPE_NAMES = {0: "未携带负载数据", 1: "传播路径列表"}

# 无线发现列表信息单元类型（表124）/长度类型（表125）
_RF_IE_TYPE_NAMES = {
    0: "站点属性信息", 1: "站点路由信息",
    2: "邻居节点信道信息(非位图)", 3: "邻居节点信道信息(位图)",
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
        # content 已切片；子解析器 offset 传 0（相对），
        # 产出的行偏移必须加上 content_offset，才能与原帧字节高亮对齐。
        content_table = _parse_mme_content(content, 0, mmtype)
        adjusted = []
        for row in content_table:
            cells = list(row)
            if len(cells) >= 6 and cells[4] is not None and cells[5] is not None:
                cells[4] = cells[4] + content_offset
                cells[5] = cells[5] + content_offset
            adjusted.append(tuple(cells))
        table.extend(adjusted)

    return table


def _parse_mme_content(data: bytes, offset: int, mmtype: int) -> List[Tuple]:
    """按消息类型解析报文内容"""
    table = []

    dispatch = {
        0x0000: _parse_associate_req,
        0x0001: _parse_associate_cnf,
        0x0002: _parse_associate_summary,
        0x0003: _parse_change_proxy_req,
        0x0004: _parse_change_proxy_cnf,
        0x0005: _parse_change_proxy_bitmap_cnf,
        0x0006: _parse_leave_ind,
        0x0007: _parse_heartbeat,
        0x0008: _parse_discovery_list,
        0x0009: _parse_comm_success_rate,
        0x000A: _parse_network_conflict,
        0x000B: _parse_ntb_collect_ind,
        0x000C: _parse_ntb_report,
        0x004F: _parse_diagnose,
        0x0050: _parse_route_request,
        0x0051: _parse_route_reply,
        0x0052: _parse_route_error,
        0x0053: _parse_route_ack,
        0x0054: _parse_link_confirm_req,
        0x0055: _parse_link_confirm_rsp,
        0x0080: _parse_rf_channel_conflict,
    }
    handler = dispatch.get(mmtype)
    if handler is not None:
        table = handler(data, offset)
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


_DEVICE_TYPE_NAMES = {
    1: "抄控器", 2: "集中器本地通信单元", 3: "电表通信单元", 4: "中继器",
    5: "II型采集器", 6: "I型采集器单元", 7: "三相电表通信单元",
}
_MAC_ADDR_TYPE_NAMES = {0: "电能表地址作为入网MAC", 1: "通信模块本身MAC作为入网MAC"}
_MODULE_TYPE_NAMES = {0: "高速载波单模模块", 1: "双模高速载波和无线模块", 2: "无线单模模块"}
_BOOT_REASON_NAMES = {0: "正常启动", 1: "断电重启", 2: "看门狗复位", 3: "程序指针异常"}
_PHASE_NAMES = {0: "未知", 1: "A相", 2: "B相", 3: "C相"}


def _parse_version_info(ver: bytes, base_offset: int) -> List[Tuple]:
    """解析站点版本信息字(表66, 10B):
    启动原因(1) + BOOT版本(1) + 软件版本(2,BCD) + 版本时间(2,BIN) + 厂商代码(2,ASCII) + 芯片代码(2)
    """
    rows: List[Tuple] = []
    reason = ver[0]
    rows.append(("      系统启动原因", f"0x{reason:02X}",
                 _BOOT_REASON_NAMES.get(reason, f"保留({reason})"),
                 "表67", base_offset, base_offset))
    rows.append(("      BOOT版本号", f"0x{ver[1]:02X}", str(ver[1]),
                 "BOOT版本", base_offset + 1, base_offset + 1))
    # 软件版本号 BCD: 高字节主版本, 低字节次版本
    sw_major = (ver[2] >> 4) * 10 + (ver[2] & 0x0F)
    sw_minor = (ver[3] >> 4) * 10 + (ver[3] & 0x0F)
    rows.append(("      软件版本号", ' '.join(f'{b:02X}' for b in ver[2:4]),
                 f"V{sw_major}.{sw_minor}", "BCD码(与本地通信模块接口协议一致)",
                 base_offset + 2, base_offset + 3))
    # 版本时间(表68): 年7b(byte0 bit0-6), 月4b(byte0 bit7 + byte1 bit0-2), 日5b(byte1 bit3-7)
    y = ver[4] & 0x7F
    m = ((ver[4] >> 7) << 3) | (ver[5] & 0x07)
    d = (ver[5] >> 3) & 0x1F
    rows.append(("      版本时间", ' '.join(f'{b:02X}' for b in ver[4:6]),
                 f"20{y:02d}-{m:02d}-{d:02d}", f"年={y} 月={m} 日={d}(BIN, 表68)",
                 base_offset + 4, base_offset + 5))
    # 厂商代码/芯片代码: 2字节小端(多字节字段统一小端), 显示时高字节在前
    vendor_raw = int.from_bytes(ver[6:8], 'little')
    vendor = bytes([(vendor_raw >> 8) & 0xFF, vendor_raw & 0xFF]).decode(
        'ascii', errors='replace')
    rows.append(("      厂商代码", ' '.join(f'{b:02X}' for b in ver[6:8]),
                 vendor, "ASCII码(2字节小端, 高字节在前显示)",
                 base_offset + 6, base_offset + 7))
    chip_raw = int.from_bytes(ver[8:10], 'little')
    chip = bytes([(chip_raw >> 8) & 0xFF, chip_raw & 0xFF]).decode(
        'ascii', errors='replace')
    rows.append(("      芯片代码", ' '.join(f'{b:02X}' for b in ver[8:10]),
                 chip, "芯片标识(2字节小端)",
                 base_offset + 8, base_offset + 9))
    return rows


def _parse_associate_req(data: bytes, offset: int) -> List[Tuple]:
    """关联请求 (0x0000, 表60):
    站点MAC(6) + 候选代理TEI×5(各2B: TEI12b+链路类型1b+保留3b)
    + 相线(1) + 设备类型(1) + MAC地址类型(1) + 模块类型(1)
    + 站点关联随机数(4) + 厂家自定义信息(18) + 站点版本信息(10)
    + 硬复位累积次数(2) + 软复位累积次数(2) + 代理类型(1) + 保留(3)
    + 端到端序列号(4) + 管理ID信息(24)
    """
    table = []
    end = len(data)
    table.append(("  关联请求", "", "", "STA向CCO请求关联(表60)", offset, offset + end - 1))
    if end < 6:
        table.append(("    数据不足", "", f"{end}字节", "站点MAC需6字节",
                      offset, offset + max(end - 1, 0)))
        return table

    mac = data[0:6]
    table.append(("    站点MAC地址",
                  ' '.join(f'{b:02X}' for b in mac),
                  ':'.join(f'{b:02X}' for b in mac),
                  "请求关联的站点MAC(大端)", offset, offset + 5))

    # 候选代理 ×5 (offset 6-15)
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
                      f"链路类型={'无线' if link else '高速载波'}",
                      offset + pos, offset + pos + 1))
        pos += 2

    if pos >= end:
        return table

    # ── 字节16: 相线 (主2b + 备选1 2b + 备选2 2b + 保留2b) ──
    ph = data[pos]
    ph_main = ph & 0x03
    ph_alt1 = (ph >> 2) & 0x03
    ph_alt2 = (ph >> 4) & 0x03
    table.append(("    相线", f"0x{ph:02X}",
                  f"主:{_PHASE_NAMES.get(ph_main, ph_main)} "
                  f"备选1:{_PHASE_NAMES.get(ph_alt1, ph_alt1)} "
                  f"备选2:{_PHASE_NAMES.get(ph_alt2, ph_alt2)}",
                  "最低2b为评估所属相线, 其余依次备选(表62)",
                  offset + pos, offset + pos))
    pos += 1

    # ── 字节17: 设备类型 ──
    if pos < end:
        dt = data[pos]
        table.append(("    设备类型", f"0x{dt:02X}",
                      _DEVICE_TYPE_NAMES.get(dt, f"保留({dt})"), "表63",
                      offset + pos, offset + pos))
        pos += 1

    # ── 字节18: MAC地址类型 ──
    if pos < end:
        mt = data[pos]
        table.append(("    MAC地址类型", f"0x{mt:02X}",
                      _MAC_ADDR_TYPE_NAMES.get(mt, f"保留({mt})"), "表64",
                      offset + pos, offset + pos))
        pos += 1

    # ── 字节19: 模块类型(低2b) + 保留(高6b) ──
    if pos < end:
        mbt = data[pos] & 0x03
        table.append(("    模块类型", f"0x{data[pos]:02X}",
                      _MODULE_TYPE_NAMES.get(mbt, f"保留({mbt})"), "低2bit, 表65",
                      offset + pos, offset + pos))
        pos += 1

    # ── 字节20-23: 站点关联随机数 (4B, 出厂首次上电随机值) ──
    if pos + 4 <= end:
        rand = int.from_bytes(data[pos:pos + 4], 'little')
        table.append(("    站点关联随机数",
                      ' '.join(f'{b:02X}' for b in data[pos:pos + 4]),
                      f"0x{rand:08X}", "32bit随机数, 掉电保持(表5.1.3.2.9)",
                      offset + pos, offset + pos + 3))
        pos += 4
    elif pos < end:
        pos = end

    # ── 字节24-41: 厂家自定义信息 (18B) ──
    vendor_len = min(18, end - pos)
    if vendor_len > 0:
        seg = data[pos:pos + vendor_len]
        ascii_hint = ''.join(chr(b) if 32 <= b < 127 else '.' for b in seg)
        table.append(("    厂家自定义信息",
                      ' '.join(f'{b:02X}' for b in seg[:18]) +
                      ("..." if vendor_len > 18 else ""),
                      f"{vendor_len}字节" + (f" [{ascii_hint}]" if ascii_hint.strip('.') else ""),
                      "厂家自定义, 按需使用(表5.1.3.2.10)",
                      offset + pos, offset + pos + vendor_len - 1))
        pos += vendor_len

    # ── 字节42-51: 站点版本信息 (10B, 表66) ──
    if pos + 10 <= end:
        table.append(("    站点版本信息",
                      ' '.join(f'{b:02X}' for b in data[pos:pos + 10]),
                      "10字节", "版本信息字(表66)",
                      offset + pos, offset + pos + 9))
        table.extend(_parse_version_info(data[pos:pos + 10], offset + pos))
        pos += 10
    elif pos < end:
        # 不足10B, 显示原始
        seg = data[pos:]
        table.append(("    站点版本信息(截断)",
                      ' '.join(f'{b:02X}' for b in seg), f"{len(seg)}字节",
                      "表66需10字节", offset + pos, offset + end - 1))
        pos = end

    # ── 字节52-53: 硬复位累积次数 (2B 小端) ──
    if pos + 2 <= end:
        hard = int.from_bytes(data[pos:pos + 2], 'little')
        table.append(("    硬复位累积次数",
                      ' '.join(f'{b:02X}' for b in data[pos:pos + 2]),
                      str(hard), "硬件复位累计次数",
                      offset + pos, offset + pos + 1))
        pos += 2

    # ── 字节54-55: 软复位累积次数 (2B 小端) ──
    if pos + 2 <= end:
        soft = int.from_bytes(data[pos:pos + 2], 'little')
        table.append(("    软复位累积次数",
                      ' '.join(f'{b:02X}' for b in data[pos:pos + 2]),
                      str(soft), "软件复位累计次数",
                      offset + pos, offset + pos + 1))
        pos += 2

    # ── 字节56: 代理类型 ──
    if pos < end:
        pt = data[pos]
        table.append(("    代理类型", f"0x{pt:02X}",
                      "站点动态选择的代理" if pt == 0 else f"保留({pt})",
                      "表69", offset + pos, offset + pos))
        pos += 1

    # ── 字节57-59: 保留 (3B) ──
    if pos + 3 <= end:
        table.append(("    保留",
                      ' '.join(f'{b:02X}' for b in data[pos:pos + 3]),
                      "3字节", "保留字段",
                      offset + pos, offset + pos + 2))
        pos += 3

    # ── 字节60-63: 端到端序列号 (4B 小端) ──
    if pos + 4 <= end:
        e2e = int.from_bytes(data[pos:pos + 4], 'little')
        table.append(("    端到端序列号",
                      ' '.join(f'{b:02X}' for b in data[pos:pos + 4]),
                      str(e2e), "端到端管理报文序列号(关联确认需回填)",
                      offset + pos, offset + pos + 3))
        pos += 4

    # ── 字节64-87: 管理ID信息 (24B) ──
    if pos < end:
        remain = data[pos:]
        table.append(("    管理ID信息",
                      ' '.join(f'{b:02X}' for b in remain[:24]) +
                      ("..." if len(remain) > 24 else ""),
                      f"{len(remain)}字节",
                      f"管理ID信息(标准24B, 表5.1.3.2.16){'; 超出' if len(remain) > 24 else ''}",
                      offset + pos, offset + end - 1))

    return table




def _parse_associate_cnf(data: bytes, offset: int) -> List[Tuple]:
    """关联确认 (0x0001, 表70)。

    站点MAC(6) + CCO MAC(6) + 结果(1) + 站点层级(1)
    + 站点TEI(12b)/链路类型(1b)/载波频段(2b)/保留(1b) 占2B
    + 代理TEI(12b)/保留(4b) 占2B + 总分包数(1) + 分包序号(1)
    + 站点关联随机数(4) + 重新关联时间(4) + 端到端序列号(4) + 路径序号(4)
    + 保留(4) + 路由表信息(可变, 表74/75)
    """
    table = []
    end = len(data)
    table.append(("  关联确认", "", "", "CCO对关联请求的确认(表70)",
                  offset, offset + max(end - 1, 0)))
    if end < 12:
        table.append(("    数据不足", "", f"{end}字节", "表70至少需MAC+CCMAC共12字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    mac = data[0:6]
    _r("站点MAC地址", " ".join(f"{b:02X}" for b in mac),
       ":".join(f"{b:02X}" for b in mac), "目的终端MAC(大端)", 0, 5)
    cco = data[6:12]
    _r("CCO MAC地址", " ".join(f"{b:02X}" for b in cco),
       ":".join(f"{b:02X}" for b in cco), "本网络CCO MAC(大端)", 6, 11)

    if end <= 12:
        return table
    result = data[12]
    _r("结果", f"0x{result:02X}",
       _ASSOC_CNF_RESULT_NAMES.get(result, f"保留({result})"),
       "关联确认结果(表71)", 12, 12)
    if end > 13:
        _r("站点层级", f"0x{data[13]:02X}", str(data[13]), "入网后拓扑层级", 13, 13)
    if end > 15:
        stei = _tei12(data, 14)
        link = (data[15] >> 4) & 0x01
        band = (data[15] >> 5) & 0x03
        _r("站点TEI", " ".join(f"{b:02X}" for b in data[14:16]), str(stei),
           "CCO分配的TEI(12b)", 14, 15)
        _r("链路类型", f"0b{link}", _LINK_TYPE_NAMES.get(link, str(link)),
           "与代理的通信链路(bit4, 表72)", 15, 15)
        _r("载波频段", f"0b{band:02b}", _BAND_NAMES.get(band, f"保留({band})"),
           "bit5-6(表73)", 15, 15)
    if end > 17:
        ptei = _tei12(data, 16)
        _r("代理TEI", " ".join(f"{b:02X}" for b in data[16:18]), str(ptei),
           "CCO选定代理TEI(12b)", 16, 17)
    if end > 18:
        _r("总分包数", f"0x{data[18]:02X}", str(data[18]), "关联回复分包总数", 18, 18)
    if end > 19:
        _r("分包序号", f"0x{data[19]:02X}", str(data[19]),
           "分包索引, 首包为1", 19, 19)
    if end >= 24:
        rand = int.from_bytes(data[20:24], "little")
        _r("站点关联随机数", " ".join(f"{b:02X}" for b in data[20:24]),
           f"0x{rand:08X}", "回带请求报文中的随机数", 20, 23)
    if end >= 28:
        rejoin = int.from_bytes(data[24:28], "little")
        _r("重新关联时间", " ".join(f"{b:02X}" for b in data[24:28]),
           f"{rejoin}ms", "被拒后可重新关联的间隔(毫秒)", 24, 27)
    if end >= 32:
        e2e = int.from_bytes(data[28:32], "little")
        _r("端到端序列号", " ".join(f"{b:02X}" for b in data[28:32]),
           str(e2e), "回带原始请求的端到端序列号", 28, 31)
    if end >= 36:
        pseq = int.from_bytes(data[32:36], "little")
        _r("路径序号", " ".join(f"{b:02X}" for b in data[32:36]),
           str(pseq), "路径通知序列号, 递增", 32, 35)

    # 路由表信息（表74: 直连站点数2B + 直连代理数2B + 路由表大小2B + 保留2B + 路由表）
    if end > 40:
        rt = data[40:]
        if len(rt) >= 8:
            n_sta = int.from_bytes(rt[0:2], "little")
            n_pco = int.from_bytes(rt[2:4], "little")
            rt_size = int.from_bytes(rt[4:6], "little")
            table.append(("    路由表信息", "", f"{len(rt)}字节",
                          f"直连站点{n_sta}个, 直连代理{n_pco}个, 路由表{rt_size}字节(表74)",
                          offset + 40, offset + end - 1))
            # 路由表：直连STA条目每2B(TEI12b+链路1b+保留3b)，
            # 直连代理每4B(TEI12b+链路1b+保留3b + 该代理下子站点数2B)，
            # 其后跟随该代理的子站点TEI(每2b? 否:每子站点2B, TEI12b+保留4b)。
            pos = 8
            for i in range(min(n_sta, 64)):
                if pos + 2 > len(rt):
                    break
                tei = _tei12(rt, pos)
                lk = (rt[pos + 1] >> 4) & 0x01
                table.append((f"      直连站点{i + 1}",
                              " ".join(f"{b:02X}" for b in rt[pos:pos + 2]),
                              f"TEI={tei}",
                              f"链路={_LINK_TYPE_NAMES.get(lk, lk)}(表75)",
                              offset + 40 + pos, offset + 40 + pos + 1))
                pos += 2
            for i in range(min(n_pco, 32)):
                if pos + 4 > len(rt):
                    break
                ptei2 = _tei12(rt, pos)
                lk = (rt[pos + 1] >> 4) & 0x01
                sub_n = int.from_bytes(rt[pos + 2:pos + 4], "little")
                table.append((f"      直连代理{i + 1}",
                              " ".join(f"{b:02X}" for b in rt[pos:pos + 4]),
                              f"TEI={ptei2}, 子站点{sub_n}个",
                              f"链路={_LINK_TYPE_NAMES.get(lk, lk)}(表75)",
                              offset + 40 + pos, offset + 40 + pos + 3))
                pos += 4
                for j in range(min(sub_n, 128)):
                    if pos + 2 > len(rt):
                        break
                    stei2 = _tei12(rt, pos)
                    table.append((f"        子站点TEI",
                                  " ".join(f"{b:02X}" for b in rt[pos:pos + 2]),
                                  f"TEI={stei2}", "该PCO下子站点(12b)",
                                  offset + 40 + pos, offset + 40 + pos + 1))
                    pos += 2
        else:
            _r("路由表信息(过短)",
               " ".join(f"{b:02X}" for b in rt), f"{len(rt)}字节",
               "表74路由信息头需8字节", 40, end - 1)
    return table


def _parse_associate_summary(data: bytes, offset: int) -> List[Tuple]:
    """关联汇总指示 (0x0002, 表76)。

    结果(1, 固定0) + 站点层级(1) + CCO MAC(6)
    + 代理TEI(12b)/载波频段(2b)/保留(2b) 占2B + 保留(1)
    + 汇总站点数(1) + 保留(4) + 站点信息[N×8B, 表78]
    """
    table = []
    end = len(data)
    table.append(("  关联汇总指示", "", "", "新入网站点汇总(表76)",
                  offset, offset + max(end - 1, 0)))
    if end < 16:
        table.append(("    数据不足", "", f"{end}字节", "表76固定头需16字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    _r("结果", f"0x{data[0]:02X}",
       "允许加入网络" if data[0] == 0 else f"非0({data[0]})",
       "固定值0(5.1.3.4.2)", 0, 0)
    _r("站点层级", f"0x{data[1]:02X}", str(data[1]), "所有新入网站点层级", 1, 1)
    cco = data[2:8]
    _r("CCO MAC地址", " ".join(f"{b:02X}" for b in cco),
       ":".join(f"{b:02X}" for b in cco), "本网络CCO MAC(大端)", 2, 7)
    ptei = _tei12(data, 8)
    band = (data[9] >> 4) & 0x03
    _r("代理TEI", " ".join(f"{b:02X}" for b in data[8:10]), str(ptei),
       "新入网站点共同代理(12b)", 8, 9)
    _r("载波频段", f"0b{band:02b}", _BAND_NAMES.get(band, f"保留({band})"),
       "bit4-5(表77)", 9, 9)
    n = data[11]
    _r("汇总站点数", f"0x{n:02X}", str(n),
       "站点信息条目数N(长帧头≤58/短帧头≤59)", 11, 11)

    # 站点信息自字节16起, 每条8B: MAC(6)+TEI(12b)+保留(4b)
    pos = 16
    for i in range(n):
        if pos + 8 > end:
            table.append(("    ⚠ 站点信息数据不足", "", f"需{n}条×8B",
                          f"第{i + 1}条起超出报文(实际到{end}字节)",
                          offset + pos, offset + end - 1))
            break
        emac = data[pos:pos + 6]
        etei = _tei12(data, pos + 6)
        table.append((f"    站点{i + 1}",
                      ":".join(f"{b:02X}" for b in emac) +
                      f" TEI={etei}",
                      f"TEI={etei}",
                      "MAC(6B)+TEI(12b)+保留(4b), 表78",
                      offset + pos, offset + pos + 7))
        pos += 8
    return table


def _parse_leave_ind(data: bytes, offset: int) -> List[Tuple]:
    """离线指示 (0x0006, 表91)。

    原因(2) + 站点总数(2) + 延迟时间(2, 秒) + 保留(10) + 站点MAC[N×6B, 表93]
    注: 表91无字节号列, 偏移按字段顺序与大小累计(2+2+2+10=16B固定头)。
    """
    table = []
    end = len(data)
    table.append(("  离线指示", "", "", "CCO通知站点离线(表91)",
                  offset, offset + max(end - 1, 0)))
    if end < 6:
        table.append(("    数据不足", "", f"{end}字节", "固定头需6字节",
                      offset, offset + max(end - 1, 0)))
        return table

    reason = int.from_bytes(data[0:2], "little")
    total = int.from_bytes(data[2:4], "little")
    delay = int.from_bytes(data[4:6], "little")
    table.append(("    原因", " ".join(f"{b:02X}" for b in data[0:2]),
                  _LEAVE_REASON_NAMES.get(reason, f"保留({reason})"),
                  "离线原因(表92)", offset, offset + 1))
    table.append(("    站点总数", " ".join(f"{b:02X}" for b in data[2:4]),
                  str(total), "需要离线的站点个数N", offset + 2, offset + 3))
    table.append(("    延迟时间", " ".join(f"{b:02X}" for b in data[4:6]),
                  f"{delay}秒", "到期后离线(单位秒)", offset + 4, offset + 5))

    # 站点MAC自字节16起, 每条6B
    pos = 16
    for i in range(total):
        if pos + 6 > end:
            table.append(("    ⚠ 站点MAC数据不足", "", f"需{total}个×6B",
                          f"第{i + 1}个起超出报文(实际到{end}字节)",
                          offset + pos, offset + end - 1))
            break
        emac = data[pos:pos + 6]
        table.append((f"    离线站点{i + 1}",
                      " ".join(f"{b:02X}" for b in emac),
                      ":".join(f"{b:02X}" for b in emac),
                      "离线站点MAC(表93)", offset + pos, offset + pos + 5))
        pos += 6
    return table


def _parse_comm_success_rate(data: bytes, offset: int) -> List[Tuple]:
    """通信成功率上报 (0x0009, 表100)。

    TEI(12b)+保留(4b) 占2B + 站点总数(2) + 成功率信息[N×4B, 表101]
    仅由代理站点发送。
    """
    table = []
    end = len(data)
    table.append(("  通信成功率上报", "", "", "代理上报子站点成功率(表100)",
                  offset, offset + max(end - 1, 0)))
    if end < 4:
        table.append(("    数据不足", "", f"{end}字节", "固定头需4字节",
                      offset, offset + max(end - 1, 0)))
        return table

    tei = _tei12(data, 0)
    total = int.from_bytes(data[2:4], "little")
    table.append(("    代理TEI", " ".join(f"{b:02X}" for b in data[0:2]),
                  str(tei), "发送代理自身TEI(12b)", offset, offset + 1))
    table.append(("    站点总数", " ".join(f"{b:02X}" for b in data[2:4]),
                  str(total), "子站点个数=STA表项数N", offset + 2, offset + 3))

    pos = 4
    for i in range(total):
        if pos + 4 > end:
            table.append(("    ⚠ 成功率信息数据不足", "", f"需{total}条×4B",
                          f"第{i + 1}条起超出报文(实际到{end}字节)",
                          offset + pos, offset + end - 1))
            break
        stei = _tei12(data, pos)
        down = data[pos + 2]
        up = data[pos + 3]
        table.append((f"    子站点{i + 1}",
                      " ".join(f"{b:02X}" for b in data[pos:pos + 4]),
                      f"TEI={stei} 下行{down} 上行{up}",
                      f"TEI={stei}, 下行成功率={down}%, 上行成功率={up}%(表101)",
                      offset + pos, offset + pos + 3))
        pos += 4
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

# ── 代理变更系列（表79~表90） ───────────────────────────────────

def _parse_change_proxy_req(data: bytes, offset: int) -> List[Tuple]:
    """代理变更请求 (0x0003, 表79), 定长24字节。

    站点TEI(12b)+保留(4b)
    + 候选新代理×5(各2B: TEI12b+链路1b+保留3b, 固定5槽)
    + 旧代理TEI(12b)+保留(4b) + 代理类型(1) + 原因(1)
    + 端到端序列号(4) + 站点相线(3×2b+保留2b, 1B) + 保留(3)
    """
    table = []
    end = len(data)
    table.append(("  代理变更请求", "", "", "站点申请变更代理(表79)",
                  offset, offset + max(end - 1, 0)))
    if end < 14:
        table.append(("    数据不足", "", f"{end}字节", "表79至少需14字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    stei = _tei12(data, 0)
    _r("站点TEI", " ".join(f"{b:02X}" for b in data[0:2]), str(stei),
       "发起变更站点TEI(12b)", 0, 1)
    # 候选新代理 ×5, 字节2-11
    for i in range(5):
        p = 2 + i * 2
        if p + 2 > end:
            break
        ctei = _tei12(data, p)
        lk = (data[p + 1] >> 4) & 0x01
        _r(f"新代理候选{i + 1}", " ".join(f"{b:02X}" for b in data[p:p + 2]),
           f"TEI={ctei}", f"链路={_LINK_TYPE_NAMES.get(lk, lk)}(表80)",
           p, p + 1)
    if end >= 14:
        old = _tei12(data, 12)
        _r("旧代理TEI", " ".join(f"{b:02X}" for b in data[12:14]), str(old),
           "原代理站点TEI(12b)", 12, 13)
    if end > 14:
        pt = data[14]
        _r("代理类型", f"0x{pt:02X}",
           "站点动态选择的代理" if pt == 0 else f"保留({pt})", "表81", 14, 14)
    if end > 15:
        rsn = data[15]
        _r("原因", f"0x{rsn:02X}",
           _CHANGE_REASON_NAMES.get(rsn, f"保留({rsn})"), "表82", 15, 15)
    if end >= 20:
        e2e = int.from_bytes(data[16:20], "little")
        _r("端到端序列号", " ".join(f"{b:02X}" for b in data[16:20]),
           str(e2e), "端到端管理报文序列号", 16, 19)
    if end > 20:
        ph = data[20]
        p = [ph & 0x03, (ph >> 2) & 0x03, (ph >> 4) & 0x03]
        _r("站点相线", f"0x{ph:02X}",
           f"主:{_PHASE_NAMES.get(p[0], p[0])} 备选1:{_PHASE_NAMES.get(p[1], p[1])} "
           f"备选2:{_PHASE_NAMES.get(p[2], p[2])}",
           "3个2b相线槽, 最低为主(表83, 其他=无效)", 20, 20)
    return table


def _parse_change_proxy_cnf(data: bytes, offset: int) -> List[Tuple]:
    """代理变更确认 (0x0004, 表84), 固定头20B + 子站点条目[N×2B, 表87]。"""
    table = []
    end = len(data)
    table.append(("  代理变更确认", "", "", "CCO确认代理变更(表84)",
                  offset, offset + max(end - 1, 0)))
    if end < 18:
        table.append(("    数据不足", "", f"{end}字节", "表84固定头需20字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    result = data[0]
    _r("结果", f"0x{result:02X}",
       _CHANGE_RESULT_NAMES.get(result, f"保留({result})"), "表85", 0, 0)
    _r("总分包数", f"0x{data[1]:02X}", str(data[1]), "分包总个数", 1, 1)
    _r("分包序号", f"0x{data[2]:02X}", str(data[2]), "分包索引, 首包为1", 2, 2)
    stei = _tei12(data, 4)
    lk1 = (data[5] >> 4) & 0x01
    _r("站点TEI", " ".join(f"{b:02X}" for b in data[4:6]), str(stei),
       "申请变更站点TEI(12b)", 4, 5)
    _r("链路类型", f"0b{lk1}", _LINK_TYPE_NAMES.get(lk1, str(lk1)),
       "与新代理链路(bit4, 表86)", 5, 5)
    ptei = _tei12(data, 6)
    _r("代理TEI", " ".join(f"{b:02X}" for b in data[6:8]), str(ptei),
       "新代理TEI(12b)", 6, 7)
    e2e = int.from_bytes(data[8:12], "little")
    _r("端到端序列号", " ".join(f"{b:02X}" for b in data[8:12]),
       str(e2e), "回带请求序列号", 8, 11)
    pseq = int.from_bytes(data[12:16], "little")
    _r("路径序号", " ".join(f"{b:02X}" for b in data[12:16]),
       str(pseq), "路径通知序列号", 12, 15)
    sub_n = int.from_bytes(data[16:18], "little")
    _r("子站点数", " ".join(f"{b:02X}" for b in data[16:18]), str(sub_n),
       "变更站点所有子站点数N", 16, 17)

    # 子站点条目自字节20起(字节18-19保留), 每条2B(TEI12b+保留4b)
    pos = 20
    for i in range(sub_n):
        if pos + 2 > end:
            _r(f"⚠ 子站点数据不足", "", f"需{sub_n}条×2B",
               f"第{i + 1}条起超出报文", pos, end - 1)
            break
        tei = _tei12(data, pos)
        _r(f"子站点{i + 1}", " ".join(f"{b:02X}" for b in data[pos:pos + 2]),
           f"TEI={tei}", "子站点TEI(12b, 表87)", pos, pos + 1)
        pos += 2
    return table


def _parse_change_proxy_bitmap_cnf(data: bytes, offset: int) -> List[Tuple]:
    """代理变更确认位图版 (0x0005, 表88), 固定头20B + 子站点位图。"""
    table = []
    end = len(data)
    table.append(("  代理变更确认(位图版)", "", "", "CCO确认代理变更(表88)",
                  offset, offset + max(end - 1, 0)))
    if end < 16:
        table.append(("    数据不足", "", f"{end}字节", "表88固定头需20字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    result = data[0]
    _r("结果", f"0x{result:02X}",
       _CHANGE_RESULT_NAMES.get(result, f"保留({result})"), "表89", 0, 0)
    bmp_size = int.from_bytes(data[2:4], "little")
    _r("位图大小", " ".join(f"{b:02X}" for b in data[2:4]),
       f"{bmp_size}字节", "子站点位图字节数", 2, 3)
    stei = _tei12(data, 4)
    lk1 = (data[5] >> 4) & 0x01
    _r("站点TEI", " ".join(f"{b:02X}" for b in data[4:6]), str(stei),
       "申请变更站点TEI(12b)", 4, 5)
    _r("链路类型", f"0b{lk1}", _LINK_TYPE_NAMES.get(lk1, str(lk1)),
       "与新代理链路(bit4, 表90)", 5, 5)
    ptei = _tei12(data, 6)
    _r("代理TEI", " ".join(f"{b:02X}" for b in data[6:8]), str(ptei),
       "新代理TEI(12b)", 6, 7)
    e2e = int.from_bytes(data[8:12], "little")
    _r("端到端序列号", " ".join(f"{b:02X}" for b in data[8:12]),
       str(e2e), "回带请求序列号", 8, 11)
    pseq = int.from_bytes(data[12:16], "little")
    _r("路径序号", " ".join(f"{b:02X}" for b in data[12:16]),
       str(pseq), "路径通知序列号", 12, 15)

    # 子站点位图自字节20起(字节16-19保留)
    bmp = data[20:20 + bmp_size]
    if len(bmp) < bmp_size:
        _r("⚠ 位图数据不足", "", f"声明{bmp_size}字节",
           f"实际仅{len(bmp)}字节", 20, end - 1)
    table.extend(_tei_bitmap_rows(bmp, offset + 20, "子站点位图"))
    return table


# ── 网络冲突 / 过零NTB / 网络诊断 ───────────────────────────────

def _parse_network_conflict(data: bytes, offset: int) -> List[Tuple]:
    """网络冲突上报 (0x000A, 表102)。

    CCO MAC(6) + 邻居网络个数(1) + 网络号字节宽度(1, 默认3)
    + 邻居网络条目[每个宽度W字节的网络号, 表103]
    """
    table = []
    end = len(data)
    table.append(("  网络冲突上报", "", "", "STA发现NID重复上报CCO(表102)",
                  offset, offset + max(end - 1, 0)))
    if end < 8:
        table.append(("    数据不足", "", f"{end}字节", "固定头需8字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    mac = data[0:6]
    _r("CCO MAC地址", " ".join(f"{b:02X}" for b in mac),
       ":".join(f"{b:02X}" for b in mac), "冲突邻居网络CCO MAC(大端)", 0, 5)
    n = data[6]
    width = data[7] if data[7] else 3
    _r("邻居网络个数", f"0x{data[6]:02X}", str(n), "周边冲突邻居网络数N", 6, 6)
    _r("网络号字节宽度", f"0x{data[7]:02X}", f"{width}字节",
       f"网络号宽度W, 协议默认3(表102)", 7, 7)

    pos = 8
    for i in range(n):
        if pos + width > end:
            _r(f"⚠ 邻居网络数据不足", "", f"需{n}个×{width}B",
               f"第{i + 1}个起超出报文", pos, end - 1)
            break
        nid = data[pos:pos + width]
        _r(f"邻居网络{i + 1}",
           " ".join(f"{b:02X}" for b in nid),
           "0x" + "".join(f"{b:02X}" for b in nid),
           f"邻居网络号({width}B, 字节串, 表103)", pos, pos + width - 1)
        pos += width
    return table


def _parse_ntb_collect_ind(data: bytes, offset: int) -> List[Tuple]:
    """过零NTB采集指示 (0x000B, 表104), 定长8字节。"""
    table = []
    end = len(data)
    table.append(("  过零NTB采集指示", "", "", "CCO指示站点采集过零NTB(表104)",
                  offset, offset + max(end - 1, 0)))
    if end < 5:
        table.append(("    数据不足", "", f"{end}字节", "表104需8字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    tei = _tei12(data, 0)
    _r("TEI", " ".join(f"{b:02X}" for b in data[0:2]), str(tei),
       "被指示采集站点TEI(单站点采集时有效, 12b)", 0, 1)
    site = data[2]
    _r("采集站点", f"0x{site:02X}",
       _NTB_COLLECT_SITE_NAMES.get(site, f"保留({site})"), "表105", 2, 2)
    period = data[3]
    _r("采集周期", f"0x{period:02X}",
       _NTB_COLLECT_PERIOD_NAMES.get(period, f"保留({period})"), "表106", 3, 3)
    _r("采集数量", f"0x{data[4]:02X}", str(data[4]),
       "下发后连续采集过零点NTB的数量", 4, 4)
    return table


def _read_12bit_stream(buf: bytes, count: int) -> List[int]:
    """连续12比特小端位流 → 整数值列表（每2个值占3字节, 表108）。

    值k: 起始比特 = k*12; 低8位在 floor(bit/8), 高4位在次字节低半。
    """
    vals = []
    for k in range(count):
        bit = k * 12
        b0i = bit >> 3
        sh = bit & 7
        if sh == 0:
            if b0i + 1 >= len(buf):
                break
            v = buf[b0i] | ((buf[b0i + 1] & 0x0F) << 8)
        else:  # sh == 4
            if b0i + 1 >= len(buf):
                break
            v = (buf[b0i] >> 4) | (buf[b0i + 1] << 4)
        vals.append(v & 0x0FFF)
    return vals


def _parse_ntb_report(data: bytes, offset: int) -> List[Tuple]:
    """过零NTB告知 (0x000C, 表107)。

    TEI(12b)+保留(4b) + 告知总数量(1) + 相线1/2/3差值数量(各1)
    + 基准NTB(4, 原始高24b) + 三段12b紧凑差值流（按相线1→2→3）
    """
    table = []
    end = len(data)
    table.append(("  过零NTB告知", "", "", "站点上报过零NTB及差值(表107)",
                  offset, offset + max(end - 1, 0)))
    if end < 10:
        table.append(("    数据不足", "", f"{end}字节", "固定头需10字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    tei = _tei12(data, 0)
    _r("TEI", " ".join(f"{b:02X}" for b in data[0:2]), str(tei),
       "告知站点TEI(12b)", 0, 1)
    total = data[2]
    n1, n2, n3 = data[3], data[4], data[5]
    _r("告知总数量", f"0x{total:02X}", str(total), "过零NTB总数量", 2, 2)
    _r("相线1差值数量", f"0x{n1:02X}", str(n1), "相线1差值数", 3, 3)
    _r("相线2差值数量", f"0x{n2:02X}", str(n2), "相线2差值数", 4, 4)
    _r("相线3差值数量", f"0x{n3:02X}", str(n3), "相线3差值数", 5, 5)
    base = int.from_bytes(data[6:10], "little")
    _r("基准NTB", " ".join(f"{b:02X}" for b in data[6:10]),
       f"0x{base:08X}", "首个过零点NTB(原始32b右移8, 有效高24b)", 6, 9)

    # 三段差值, 每段 n 个12b值 = ceil(n*12/8) 字节
    pos = 10
    for pi, (pname, cnt) in enumerate((("相线1", n1), ("相线2", n2), ("相线3", n3))):
        if cnt == 0:
            continue
        seg_bytes = (cnt * 12 + 7) // 8
        seg = data[pos:pos + seg_bytes]
        if len(seg) < seg_bytes:
            _r(f"⚠ {pname}差值数据不足", "", f"需{seg_bytes}B",
               f"声明{cnt}个差值, 实际剩{len(seg)}B", pos, end - 1)
            break
        vals = _read_12bit_stream(seg, cnt)
        _r(f"{pname}过零NTB差值",
           " ".join(f"{b:02X}" for b in seg[:12]) + ("..." if seg_bytes > 12 else ""),
           " ".join(str(v) for v in vals[:16]) + ("..." if len(vals) > 16 else ""),
           f"{cnt}个12b差值(右移8后), 每2个占3B, 表108",
           pos, pos + seg_bytes - 1)
        pos += seg_bytes
    return table


def _parse_diagnose(data: bytes, offset: int) -> List[Tuple]:
    """网络诊断 (0x004F, 表109): 芯片厂商ID(2) + 厂家自定义(不透明)。"""
    table = []
    end = len(data)
    table.append(("  网络诊断", "", "", "厂商自定义故障定位报文(表109)",
                  offset, offset + max(end - 1, 0)))
    if end < 2:
        table.append(("    数据不足", "", f"{end}字节", "需芯片厂商ID 2字节",
                      offset, offset + max(end - 1, 0)))
        return table
    vid = int.from_bytes(data[0:2], "little")
    table.append(("    芯片厂商ID", " ".join(f"{b:02X}" for b in data[0:2]),
                  f"0x{vid:04X}",
                  _CHIP_VENDOR_NAMES.get(vid, f"待扩展(0x{vid:04X})") + "(表110)",
                  offset, offset + 1))
    if end > 2:
        payload = data[2:]
        ascii_hint = ''.join(chr(b) if 32 <= b < 127 else '.' for b in payload[:32])
        table.append(("    厂家自定义",
                      " ".join(f"{b:02X}" for b in payload[:24]) +
                      ("..." if len(payload) > 24 else ""),
                      f"{len(payload)}字节",
                      "格式不做统一要求, 显示原始数据" +
                      (f" [{ascii_hint}]" if ascii_hint.strip('.') else ""),
                      offset + 2, offset + end - 1))
    return table

# ── 路由修复系列（表111~表122） ─────────────────────────────────

def _parse_path_list(payload: bytes, base: int, table: List[Tuple]) -> None:
    """传播路径列表（表113/116）: 每条4B = TEI(12b)+保留4b+成功率1B+信道质量1B。"""
    n = len(payload) // 4
    for i in range(n):
        p = i * 4
        tei = _tei12(payload, p)
        rate = payload[p + 2]
        qual = payload[p + 3]
        table.append((f"      途经站点{i + 1}",
                      " ".join(f"{b:02X}" for b in payload[p:p + 4]),
                      f"TEI={tei}",
                      f"上下行成功率={rate}%(百分比), 信道质量={qual}(原始信噪比)",
                      base + p, base + p + 3))
    rem = len(payload) % 4
    if rem:
        p = n * 4
        table.append(("      ⚠ 路径剩余",
                      " ".join(f"{b:02X}" for b in payload[p:]),
                      f"{rem}字节", "非4字节整数倍的剩余数据",
                      base + p, base + len(payload) - 1))


def _parse_route_request(data: bytes, offset: int) -> List[Tuple]:
    """路由请求 (0x0050, 表111), 头7B + 负载。

    版本(1) + 请求序列号(4) + 字节5[保留高3b/路径优选1b/负载类型低4b]
    + 负载长度(1) + 负载
    """
    return _parse_route_common(data, offset, "路由请求", 0x0050, prefer_flag=True)


def _parse_route_reply(data: bytes, offset: int) -> List[Tuple]:
    """路由回复 (0x0051, 表114), 头7B + 负载（无路径优选标志）。"""
    return _parse_route_common(data, offset, "路由回复", 0x0051, prefer_flag=False)


def _parse_route_common(data: bytes, offset: int, title: str,
                        mmtype: int, prefer_flag: bool) -> List[Tuple]:
    table = []
    end = len(data)
    table.append((f"  {title}", "", "", f"{title}(表111/114)",
                  offset, offset + max(end - 1, 0)))
    if end < 7:
        table.append(("    数据不足", "", f"{end}字节", "路由报文固定头需7字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    ver = data[0]
    _r("版本", f"0x{ver:02X}", str(ver), "路由修复算法版本号, 默认0", 0, 0)
    seq = int.from_bytes(data[1:5], "little")
    _r("路由请求序列号", " ".join(f"{b:02X}" for b in data[1:5]),
       f"0x{seq:08X}", "高16b=业务报文原始源地址, 低16b=MSDU序列号", 1, 4)
    b5 = data[5]
    if prefer_flag:
        pref = (b5 >> 4) & 0x01
        ptype = b5 & 0x0F
        _r("路径优选标志", f"0b{pref}", "具有优选地位" if pref else "无优选地位",
           "bit4(表111)", 5, 5)
    else:
        ptype = b5 & 0x0F
    _r("负载数据类型", f"0x{ptype:02X}",
       _PAYLOAD_TYPE_NAMES.get(ptype, f"保留({ptype})"),
       "字节5低4b(表112/115)", 5, 5)
    plen = data[6]
    _r("负载数据长度", f"0x{plen:02X}", f"{plen}字节", "可为0", 6, 6)

    payload = data[7:7 + plen]
    if len(payload) < plen:
        _r("⚠ 负载数据不足", "", f"声明{plen}B",
           f"实际仅{len(payload)}B", 7, end - 1)
    if ptype == 1 and payload:
        table.append(("    传播路径列表", "", f"{len(payload)}字节",
                      "每途经站点一组(表113/116)", offset + 7,
                      offset + 7 + len(payload) - 1))
        _parse_path_list(payload, offset + 7, table)
    elif payload:
        _r("负载数据",
           " ".join(f"{b:02X}" for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
           f"{len(payload)}字节", "原始负载数据", 7, 7 + len(payload) - 1)
    return table


def _parse_route_error(data: bytes, offset: int) -> List[Tuple]:
    """路由错误 (0x0052, 表117): 版本1+序列号4+保留1+不可达数量1+列表[N×2B]。"""
    table = []
    end = len(data)
    table.append(("  路由错误", "", "", "路由错误报文(表117)",
                  offset, offset + max(end - 1, 0)))
    if end < 7:
        table.append(("    数据不足", "", f"{end}字节", "固定头需7字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    _r("版本", f"0x{data[0]:02X}", str(data[0]), "路由修复算法版本", 0, 0)
    seq = int.from_bytes(data[1:5], "little")
    _r("路由请求序列号", " ".join(f"{b:02X}" for b in data[1:5]),
       f"0x{seq:08X}", "对应路由请求序列号", 1, 4)
    n = data[6]
    _r("不可达站点数量", f"0x{n:02X}", str(n), "列表条目数N", 6, 6)
    pos = 7
    for i in range(n):
        if pos + 2 > end:
            _r("⚠ 不可达列表数据不足", "", f"需{n}条×2B",
               f"第{i + 1}条起超出报文", pos, end - 1)
            break
        tei = int.from_bytes(data[pos:pos + 2], "little")
        _r(f"不可达站点{i + 1}",
           " ".join(f"{b:02X}" for b in data[pos:pos + 2]),
           f"TEI={tei}", "不可达站点TEI(2B, 表117)", pos, pos + 1)
        pos += 2
    return table


def _parse_route_ack(data: bytes, offset: int) -> List[Tuple]:
    """路由应答 (0x0053, 表118), 定长8B: 版本1+保留3+序列号4。"""
    table = []
    end = len(data)
    table.append(("  路由应答", "", "", "路由应答报文(表118)",
                  offset, offset + max(end - 1, 0)))
    if end < 8:
        table.append(("    数据不足", "", f"{end}字节", "定长8字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    _r("版本", f"0x{data[0]:02X}", str(data[0]), "路由修复算法版本", 0, 0)
    seq = int.from_bytes(data[4:8], "little")
    _r("路由请求序列号", " ".join(f"{b:02X}" for b in data[4:8]),
       f"0x{seq:08X}", "对应路由请求序列号(字节1-3保留)", 4, 7)
    return table


def _parse_link_confirm_req(data: bytes, offset: int) -> List[Tuple]:
    """链路确认请求 (0x0054, 表119): 版本1+序列号4+保留1+确认站点数1+列表[N×2B]。"""
    table = []
    end = len(data)
    table.append(("  链路确认请求", "", "", "链路确认请求报文(表119)",
                  offset, offset + max(end - 1, 0)))
    if end < 7:
        table.append(("    数据不足", "", f"{end}字节", "固定头需7字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    _r("版本", f"0x{data[0]:02X}", str(data[0]), "路由修复算法版本", 0, 0)
    seq = int.from_bytes(data[1:5], "little")
    _r("路由请求序列号", " ".join(f"{b:02X}" for b in data[1:5]),
       f"0x{seq:08X}", "对应路由请求序列号", 1, 4)
    n = data[6]
    _r("确认站点数量", f"0x{n:02X}", str(n), "需链路确认站点数N", 6, 6)
    pos = 7
    for i in range(n):
        if pos + 2 > end:
            _r("⚠ 确认站点列表数据不足", "", f"需{n}条×2B",
               f"第{i + 1}条起超出报文", pos, end - 1)
            break
        tei = int.from_bytes(data[pos:pos + 2], "little")
        _r(f"确认站点{i + 1}",
           " ".join(f"{b:02X}" for b in data[pos:pos + 2]),
           f"TEI={tei}", "确认站点TEI(2B, 表119)", pos, pos + 1)
        pos += 2
    return table


def _parse_link_confirm_rsp(data: bytes, offset: int) -> List[Tuple]:
    """链路确认回应 (0x0055, 表120), 定长8B。

    版本1 + 层级1 + 信道质量1 + 字节3[路径优选1b+保留7b] + 序列号4
    """
    table = []
    end = len(data)
    table.append(("  链路确认回应", "", "", "链路确认回应报文(表120)",
                  offset, offset + max(end - 1, 0)))
    if end < 8:
        table.append(("    数据不足", "", f"{end}字节", "定长8字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    _r("版本", f"0x{data[0]:02X}", str(data[0]), "路由修复算法版本", 0, 0)
    _r("层级", f"0x{data[1]:02X}", str(data[1]), "本站点网络层级", 1, 1)
    _r("信道质量", f"0x{data[2]:02X}", str(data[2]),
       "接收请求时信道质量(原始信噪比)", 2, 2)
    pref = (data[3] >> 0) & 0x01  # 规范未给位序号, 按1b标志+7b保留, 置最低位
    _r("路径优选标志", f"0b{pref}", "具有优选地位" if pref else "无优选地位",
       "1b标志(规范未定位序号, 按低位解析)", 3, 3)
    seq = int.from_bytes(data[4:8], "little")
    _r("路由请求序列号", " ".join(f"{b:02X}" for b in data[4:8]),
       f"0x{seq:08X}", "对应路由请求序列号", 4, 7)
    return table


def _parse_rf_channel_conflict(data: bytes, offset: int) -> List[Tuple]:
    """无线信道冲突上报 (0x0080, 表121)。

    CCO MAC(6) + 邻居网络个数(1) + 邻居网络条目[N×1B 无线信道号, 表122]
    """
    table = []
    end = len(data)
    table.append(("  无线信道冲突上报", "", "", "无线邻居网络冲突(表121)",
                  offset, offset + max(end - 1, 0)))
    if end < 7:
        table.append(("    数据不足", "", f"{end}字节", "固定头需7字节",
                      offset, offset + max(end - 1, 0)))
        return table

    def _r(name, raw, val, desc, s, e):
        table.append((f"    {name}", raw, val, desc,
                      offset + s, offset + min(e, end - 1)))

    mac = data[0:6]
    _r("CCO MAC地址", " ".join(f"{b:02X}" for b in mac),
       ":".join(f"{b:02X}" for b in mac), "冲突邻居网络CCO MAC(大端)", 0, 5)
    n = data[6]
    _r("邻居网络个数", f"0x{n:02X}", str(n), "周边冲突邻居网络数N", 6, 6)
    pos = 7
    for i in range(n):
        if pos >= end:
            _r("⚠ 邻居网络数据不足", "", f"需{n}个×1B",
               f"第{i + 1}个起超出报文", pos, end - 1)
            break
        ch = data[pos]
        _r(f"邻居网络{i + 1}信道号", f"0x{ch:02X}", str(ch),
           "邻居网络无线信道号(1B, 表122)", pos, pos)
        pos += 1
    return table

# ── 无线发现列表（表123~137, 单跳帧 MSDU 类型0） ─────────────────

_RF_ROLE_NAMES = {0: "未知", 1: "STA", 2: "PCO", 3: "保留", 4: "CCO"}

# 非位图信道信息组合类型（表129）: 类型 -> (接收率b, 平均信噪比b, 信号强度b, 总b)
_RF_NONBITMAP_COMBO = {
    0: (8, 0, 0, 20), 1: (0, 4, 0, 16), 2: (0, 0, 8, 20), 3: (0, 0, 4, 16),
    4: (8, 4, 0, 24), 5: (6, 0, 6, 24), 6: (0, 6, 6, 24), 7: (8, 6, 6, 32),
    8: (0, 4, 4, 20), 9: (8, 0, 4, 24),
}
# 位图信道信息组合类型（表137）
_RF_BITMAP_COMBO = {
    0: (8, 0, 0, 8), 1: (0, 4, 0, 4), 2: (0, 0, 8, 8), 3: (0, 0, 4, 4),
    4: (8, 4, 0, 12), 5: (8, 0, 8, 16), 6: (0, 6, 6, 12), 7: (8, 6, 6, 20),
    8: (8, 4, 4, 16), 9: (0, 4, 4, 8), 10: (8, 0, 4, 12),
}


class _BitReader:
    """从字节串按 LSB-first 顺序读任意位宽整数。"""
    def __init__(self, buf: bytes):
        self.buf = buf
        self.bitpos = 0

    def read(self, n: int):
        if n <= 0:
            return 0
        v = 0
        for i in range(n):
            bi = self.bitpos + i
            if bi >= len(self.buf) * 8:
                return None
            if self.buf[bi >> 3] & (1 << (bi & 7)):
                v |= 1 << i
        self.bitpos += n
        return v


def _parse_rf_ie(ie_type: int, content: bytes, base: int) -> List[Tuple]:
    """按信息单元类型解析 TLV 内容（表126~137）。"""
    rows: List[Tuple] = []

    def _r(name, raw, val, desc, s, e):
        rows.append((f"        {name}", raw, val, desc, base + s,
                     base + min(e, len(content) - 1)))

    if ie_type == 0:
        # 站点属性信息（表126）, 定长14B
        if len(content) < 14:
            _r("⚠ 站点属性信息过短", "", f"{len(content)}B", "表126需14B", 0, len(content) - 1)
            return rows
        cco = content[0:6]
        ptei = _tei12(content, 6)
        role = content[7] >> 4
        level = content[8] & 0x0F
        hops = (content[8] >> 4) & 0x0F
        _r("CCO MAC地址", ":".join(f"{b:02X}" for b in cco),
           ":".join(f"{b:02X}" for b in cco), "本网络CCO(6B)", 0, 5)
        _r("代理TEI", "", str(ptei), "代理TEI(12b)", 6, 7)
        _r("角色", "", _RF_ROLE_NAMES.get(role, f"保留({role})"), "高4b", 7, 7)
        _r("层级", "", str(level), "低4b", 8, 8)
        _r("链路RF跳数", "", str(hops), "高4b", 8, 8)
        _r("代理上行接收率", "", f"{content[9]}%", "1B", 9, 9)
        _r("代理下行接收率", "", f"{content[10]}%", "1B", 10, 10)
        _r("链路最小接收率", "", f"{content[11]}%", "1B", 11, 11)
        _r("无线发现列表周期", "", str(content[12]), "1B", 12, 12)
        _r("无线接收率老化周期个数", "", str(content[13]), "1B", 13, 13)

    elif ie_type == 1:
        # 站点路由信息（表127）, 每条2B: TEI12b+路由类型4b
        n = len(content) // 2
        for i in range(n):
            p = i * 2
            tei = _tei12(content, p)
            rt = (content[p + 1] >> 4) & 0x0F
            _r(f"下一跳{i + 1}", "", f"TEI={tei}",
               _ROUTE_TYPE_NAMES.get(rt, f"保留({rt})") + "(表98)", p, p + 1)

    elif ie_type == 2:
        # 邻居节点信道信息非位图（表128/129）
        if not content:
            return rows
        combo = content[0] & 0x0F
        spec = _RF_NONBITMAP_COMBO.get(combo)
        _r("信道信息组合类型", "", str(combo),
           f"表129类型{combo}" + ("" if spec else "(保留)"), 0, 0)
        if not spec:
            _r("原始内容", content[1:].hex(" "), "", "未识别组合类型", 1, len(content) - 1)
            return rows
        rb, sb, ib, total = spec
        br = _BitReader(content[1:])
        i = 0
        while br.bitpos + total <= len(content[1:]) * 8 and i < 256:
            tei = br.read(12)
            rate = br.read(rb) if rb else None
            snr = br.read(sb) if sb else None
            rssi = br.read(ib) if ib else None
            if tei is None:
                break
            desc = f"TEI={tei}"
            if rate is not None:
                desc += f", 接收率={rate}" + ("(实际=报文×2)" if rb == 6 else "")
            if snr is not None:
                desc += f", SNR量化={snr}"
            if rssi is not None:
                desc += f", RSSI量化={rssi}"
            rows.append((f"        邻居{i + 1}", "", desc,
                         f"表129类型{combo}, 共{total}b",
                         base + 1 + (br.bitpos - total) // 8,
                         base + 1 + (br.bitpos - 1) // 8))
            i += 1

    elif ie_type == 3:
        # 邻居节点信道信息位图（表136/137）, 多段: 组合类型1B+起始TEI12b+位图大小1B+位图+条目
        pos = 0
        seg = 0
        while pos + 4 <= len(content):
            combo = content[pos] & 0x0F
            spec = _RF_BITMAP_COMBO.get(combo)
            start_tei = _tei12(content, pos + 1)
            bsize = content[pos + 3]
            _r(f"段{seg + 1}组合类型", "", str(combo),
               f"起始TEI={start_tei}, 位图{bsize}B, 表137" +
               ("" if spec else "(保留)"), pos, pos + 3)
            bmp_start = pos + 4
            bmp = content[bmp_start:bmp_start + bsize]
            entry_start = bmp_start + bsize
            if not spec:
                break
            rb, sb, ib, item_bits = spec
            set_teis = [start_tei + i for i in range(bsize * 8)
                        if i < len(bmp) * 8 and bmp[i >> 3] & (1 << (i & 7))]
            br = _BitReader(content[entry_start:])
            for i, tei in enumerate(set_teis):
                vals = []
                rate = br.read(rb) if rb else None
                snr = br.read(sb) if sb else None
                rssi = br.read(ib) if ib else None
                if rate is None and rb:
                    break
                if rate is not None:
                    vals.append(f"接收率={rate}")
                if snr is not None:
                    vals.append(f"SNR={snr}")
                if rssi is not None:
                    vals.append(f"RSSI={rssi}")
                rows.append((f"          位图TEI{tei}", "",
                             ", ".join(vals) or f"TEI={tei}",
                             f"表137类型{combo}, 条目{item_bits}b",
                             base + entry_start, base + len(content) - 1))
            consumed_items_bits = len(set_teis) * item_bits
            pos = entry_start + (consumed_items_bits + 7) // 8
            seg += 1
            if seg > 16:
                break
    else:
        _r("未识别信息单元", content.hex(" "), "", f"类型{ie_type}保留",
           0, len(content) - 1)
    return rows


def _parse_rf_discover_list(data: bytes, offset: int) -> List[Tuple]:
    """无线发现列表（单跳帧类型0, 表123）: MAC(6)+统计序号(1)+ TLV序列。"""
    table = []
    end = len(data)
    table.append(("  无线发现列表", "", "", "无线发现列表报文(表123)",
                  offset, offset + max(end - 1, 0)))
    if end < 7:
        table.append(("    数据不足", "", f"{end}字节", "需MAC(6)+统计序号(1)",
                      offset, offset + max(end - 1, 0)))
        return table
    mac = data[0:6]
    table.append(("    站点MAC地址", " ".join(f"{b:02X}" for b in mac),
                  ":".join(f"{b:02X}" for b in mac), "发送节点MAC(大端)",
                  offset, offset + 5))
    table.append(("    统计序号", f"0x{data[6]:02X}", str(data[6]),
                  "每报文递增, 255环回0", offset + 6, offset + 6))

    pos = 7
    ie_idx = 0
    while pos < end:
        hdr = data[pos]
        ie_type = hdr & 0x7F
        len_type = (hdr >> 7) & 0x01
        pos += 1
        if len_type == 0:
            if pos >= end:
                break
            ilen = data[pos]
            pos += 1
        else:
            if pos + 2 > end:
                break
            ilen = int.from_bytes(data[pos:pos + 2], "little")
            pos += 2
        content = data[pos:pos + ilen]
        ie_idx += 1
        table.append((f"    信息单元{ie_idx}",
                      f"类型{ie_type} 长度{ilen}",
                      _RF_IE_TYPE_NAMES.get(ie_type, f"保留({ie_type})"),
                      f"长度类型={'2B' if len_type else '1B'}, 内容{ilen}B(表124/125)",
                      offset + pos - (2 if len_type else 1) - 1,
                      offset + min(pos + ilen, end) - 1))
        if len(content) < ilen:
            table.append(("      ⚠ 内容数据不足", "", f"声明{ilen}B",
                          f"实际仅{len(content)}B", offset + pos, offset + end - 1))
        if content:
            table.extend(_parse_rf_ie(ie_type, content, offset + pos))
        pos += ilen
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
        # 无线发现列表消息(表123): MAC+统计序号+信息单元TLV序列
        table.extend(_parse_rf_discover_list(data[offset:], offset))
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
