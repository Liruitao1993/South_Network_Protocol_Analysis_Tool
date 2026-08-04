# -*- coding: utf-8 -*-
"""国网新一代双模协议 — 网络管理消息(MME)解析模块

依据《双模通信互联互通技术规范 第4-2部分：数据链路层通信协议》:
  表42  管理消息报文头格式: MMTYPE(2B小端) + 保留(1B)（实测验证，非文档标注的2B）
  表43  管理消息类型
  表44  关联请求报文(MMeAssocReq)
  表47  关联确认报文(MMeAssocCnf)
  表52  关联汇总指示报文(MMeAssocGatherInd) + 表54 站点信息
  表55  代理变更请求报文(MMeChangeProxyReq)
  表56  代理变更请求确认报文(MMeChangeProxyCnf) + 表57 子站点条目
  表58  代理变更请求确认报文-位图版(MMeChangeProxyBitMapCnf)
  表59  离线指示报文(MMeLeaveInd) + 表60 MAC列表
  表61  心跳检测报文(MMeHeartBeatCheck)
  表62  发现列表报文(MMeDiscoverNodeList) + 表63/65/67/76 信息单元
  表78  通信成功率上报报文(MMeSuccessRateReport) + 表79 STA条目
  表80  网络冲突上报报文(MMeNetworkConflictReport) + 表81 邻居网络条目
  表82  过零NTB采集指示报文(MMeZeroCrossNTBCollectInd)
  表85  过零NTB告知报文(MMeZeroCrossNTBReport) + 表86 差值格式
  表87  网络诊断报文(MMeDiagnose) + 表88 芯片厂商ID
  表89  无线信道冲突上报报文(MMeRFChannelConflictReport) + 表90 条目
  表91  无线发现列表报文(MMeRF DiscoverNodeList) + 表92/93 信息单元(单跳帧用)

注: 表43 中 0x0008 标注为"保留"，但发现列表报文(表62)在文档中紧邻
    心跳检测(0x0007)定义且未单独分配类型标识符，按报文定义顺序
    (单模10376.3顺延) 0x0008 应为发现列表报文。

返回格式与 gw_new_gen_parser 一致:
  List[(字段, 原始值, 解析值, 说明, 起始字节, 结束字节, 是否子项)]
"""
from typing import List, Tuple

# ── 表43 管理消息类型 ─────────────────────────────────────────
MMETYPE_NAMES = {
    0x0000: "关联请求(MMeAssocReq)",
    0x0001: "关联确认(MMeAssocCnf)",
    0x0002: "关联汇总指示(MMeAssocGatherInd)",
    0x0003: "代理变更请求(MMeChangeProxyReq)",
    0x0004: "代理变更确认(MMeChangeProxyCnf)",
    0x0005: "代理变更确认-位图版(MMeChangeProxyBitMapCnf)",
    0x0006: "离线指示(MMeLeaveInd)",
    0x0007: "心跳检测(MMeHeartBeatCheck)",
    0x0008: "发现列表(MMeDiscoverNodeList)",
    0x0009: "通信成功率上报(MMeSuccessRateReport)",
    0x000A: "网络冲突上报(MMeNetworkConflictReport)",
    0x000B: "过零NTB采集指示(MMeZeroCrossNTBCollectInd)",
    0x000C: "过零NTB上报(MMeZeroCrossNTBReport)",
    0x0011: "Bitloading训练请求(MMeBitloadingTrainReq)",
    0x0012: "Bitloading训练请求拒绝(MMeBitloadingTrainReqReject)",
    0x0013: "分组请求(MMeGroupReq)",
    0x0014: "分组确认(MMeGroupCnf)",
    0x004F: "网络诊断报文(MMeDiagnose)",
    0x0080: "无线信道冲突上报(MMeRFChannelConflictReport)",
}

ROLE_NAMES = {0: "未知", 1: "STA", 2: "PCO", 4: "CCO"}
LINK_TYPES = {0: "高速载波", 1: "无线"}
ROUTE_TYPES = {0: "错误的路由", 1: "同级路由", 2: "上级路由", 3: "代理主路径路由", 4: "上上级路由"}
PHASE_NAMES = {0: "未知", 1: "A相", 2: "B相", 3: "C相"}
BAND_NAMES = {
    0: "1.953~11.96MHz", 1: "2.441~5.615MHz", 2: "0.781~2.930MHz",
    3: "保留", 4: "0.781~5.615MHz", 5: "0.781~11.96MHz",
    6: "6.08~11.96MHz", 7: "保留",
}
DEVICE_TYPES = {
    1: "抄控器", 2: "集中器本地通信单元", 3: "电表通信单元",
    4: "中继器", 5: "II型采集器", 6: "I型采集器", 7: "三相电表通信单元",
}
MAC_ADDR_TYPES = {0: "电能表地址", 1: "通信模块地址"}
MODULE_TYPES = {0: "高速载波单模模块", 1: "高速载波和无线双模模块", 2: "无线单模模块"}
VENDOR_IDS = {
    0x0000: "保留", 0x0001: "HS", 0x0002: "ES", 0x0003: "TC", 0x0004: "LH",
    0x0005: "HT", 0x0006: "RS", 0x0007: "SW", 0x0008: "SC", 0x0009: "YM",
    0x000A: "QJ", 0x000B: "HZ", 0x000C: "ZC", 0x000D: "SP", 0x000E: "PE",
    0x000F: "NR", 0x0010: "SL", 0x0011: "MT", 0x0012: "SI", 0x0013: "RS",
    0x0014: "XY",
}


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def _tei12(lo: int, hi: int) -> int:
    """12bit TEI: 低字节 + 高字节低4位（小端nibble组合）"""
    return lo | ((hi & 0x0F) << 8)


def _raw(data: bytes, start: int, end: int) -> str:
    return _hex(data[start:end])


# ═════════════════════════════════════════════════════════════
#  入口：标准帧 MSDU类型=0 网络管理消息
# ═════════════════════════════════════════════════════════════
def parse_management_message(data: bytes, offset: int) -> List[Tuple]:
    """解析网络管理消息（表42: MMTYPE(2B小端) + 保留(1B) + 报文内容）

    实测验证：保留字段实际为1字节（非文档标注的2字节），
    content_off = offset + 3。

    Args:
        data: 包含 MSDU 的完整帧数据（MSDU 结尾即为 data 结尾）
        offset: MSDU 起始偏移
    """
    result: List[Tuple] = []
    end = len(data)
    if end < offset + 3:
        if end > offset:
            result.append(("  管理消息(数据不足)", _raw(data, offset, end),
                           f"{end - offset}字节", "管理消息头至少需3字节",
                           offset, end, True))
        return result

    # MMTYPE 按文档表42/表43 小端存储（如 0x0080 对应字节 80 00）
    mmtype = data[offset] | (data[offset + 1] << 8)
    name = MMETYPE_NAMES.get(mmtype)
    if name is None:
        name = f"保留/未知(0x{mmtype:04X})"
    elif mmtype == 0x0008:
        name += " [表43标注保留,按定义顺序推断]"

    result.append(("  管理消息类型(MMTYPE)", _raw(data, offset, offset + 2),
                   f"0x{mmtype:04X}", name, offset, offset + 2, True))
    result.append(("  保留", _raw(data, offset + 2, offset + 4), "",
                   "管理消息报文头保留字段", offset + 2, offset + 4, True))

    content_off = offset + 4
    parser = _MME_CONTENT_PARSERS.get(mmtype)
    if parser is not None and content_off < end:
        parser(data, content_off, result)
    elif content_off < end:
        result.append(("  报文内容", _raw(data, content_off, end),
                       f"{end - content_off}字节", "未实现解析的消息类型,原始数据",
                       content_off, end, True))
    return result


# ═════════════════════════════════════════════════════════════
#  入口：单跳帧（表3）MSDU 消息
# ═════════════════════════════════════════════════════════════
def parse_singlehop_msdu(data: bytes, offset: int, msg_type: int) -> List[Tuple]:
    """解析单跳帧 MSDU（表3 消息类型字段）

    消息类型: 0=无线发现列表报文 1=信道评估参数更新报文
              2=载波发现列表报文 128=应用层报文 129=IPV4报文
    """
    result: List[Tuple] = []
    end = len(data)
    if end <= offset:
        return result

    if msg_type == 0:
        result.append(("  无线发现列表报文", "", "MMeRF DiscoverNodeList",
                       "单跳帧消息类型0(表91)", offset, end, True))
        _parse_discover_list(data, offset, result, rf=True)
    elif msg_type == 2:
        result.append(("  载波发现列表报文", "", "MMeDiscoverNodeList",
                       "单跳帧消息类型2(表62)", offset, end, True))
        _parse_discover_list(data, offset, result, rf=False)
    elif msg_type == 1:
        result.append(("  信道评估参数更新报文", _raw(data, offset, end),
                       f"{end - offset}字节", "单跳帧消息类型1", offset, end, True))
    elif msg_type == 129:
        result.append(("  IPV4报文", _raw(data, offset, end),
                       f"{end - offset}字节", "单跳帧消息类型129", offset, end, True))
    else:
        result.append((f"  单跳消息(类型{msg_type})", _raw(data, offset, end),
                       f"{end - offset}字节", "未识别消息类型", offset, end, True))
    return result


# ═════════════════════════════════════════════════════════════
#  0x0000 关联请求（表44, 88字节）
# ═════════════════════════════════════════════════════════════
def _parse_assoc_req(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 6:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    result.append(("  站点MAC地址", _raw(data, off, off + 6), "",
                   "请求站点的MAC地址", off, off + 6, True))
    # 候选代理0~4: 每个2字节(TEI 12bit + 链路类型 1bit)
    pos = off + 6
    for i in range(5):
        if pos + 2 > end:
            return
        tei = _tei12(data[pos], data[pos + 1])
        link = (data[pos + 1] >> 4) & 0x01
        link_name = LINK_TYPES.get(link, str(link))
        result.append((f"  候选代理{i} TEI", _raw(data, pos, pos + 2), str(tei),
                       f"候选代理站点{i}的TEI(12bit)", pos, pos + 2, True))
        result.append((f"  候选代理{i} 链路类型", f"D4={link}", link_name,
                       f"与候选代理{i}的通信链路类型", pos + 1, pos + 2, True))
        pos += 2
    if pos + 14 > end:
        return
    # 相线(1B, 3×2bit)
    ph = data[pos]
    phases = [PHASE_NAMES.get((ph >> s) & 0x03, "?") for s in (0, 2, 4)]
    result.append(("  相线", f"0x{ph:02X}", "/".join(phases),
                   "站点评估所属相线(按优先顺序)", pos, pos + 1, True))
    # 设备类型(1B)
    dev = data[pos + 1]
    dev_name = DEVICE_TYPES.get(dev, f"保留({dev})")
    result.append(("  设备类型", f"0x{dev:02X}", dev_name,
                   "终端设备类型", pos + 1, pos + 2, True))
    # MAC地址类型(1B)
    mt = data[pos + 2]
    result.append(("  MAC地址类型", f"0x{mt:02X}", MAC_ADDR_TYPES.get(mt, str(mt)),
                   "入网使用的MAC地址来源", pos + 2, pos + 3, True))
    # 模块类型(2bit)
    md = data[pos + 3] & 0x03
    result.append(("  模块类型", f"D[1:0]={md:02b}", MODULE_TYPES.get(md, str(md)),
                   "模块类型", pos + 3, pos + 4, True))
    pos += 4  # off+20
    # 站点关联随机数(4B)
    rand = int.from_bytes(data[pos:pos + 4], 'little')
    result.append(("  站点关联随机数", _raw(data, pos, pos + 4), f"0x{rand:08X}",
                   "初次上电获取的32bit随机值", pos, pos + 4, True))
    pos += 4  # off+24
    # 厂家自定义信息(18B)
    if pos + 18 > end:
        return
    result.append(("  厂家自定义信息", _raw(data, pos, pos + 18), "18字节",
                   "根据实际需要使用", pos, pos + 18, True))
    pos += 18  # off+42
    # 站点版本信息(10B, 表45)
    if pos + 10 > end:
        return
    ver = data[pos:pos + 10]
    boot = ver[0]
    boot_reasons = {0: "正常启动", 1: "断电重启", 2: "看门狗复位", 3: "程序指针异常"}
    result.append(("  系统启动原因", f"0x{boot:02X}", boot_reasons.get(boot, f"保留({boot})"),
                   "站点版本信息[表45]", pos, pos + 1, True))
    result.append(("  BOOT版本号", f"0x{ver[1]:02X}", str(ver[1]), "",
                   pos + 1, pos + 2, True))
    result.append(("  软件版本号", _hex(ver[2:4]), f"{ver[3]:02X}{ver[2]:02X}",
                   "BCD码", pos + 2, pos + 4, True))
    result.append(("  版本时间", _hex(ver[4:6]), "", "BIN码(年7bit+月4bit+日5bit)",
                   pos + 4, pos + 6, True))
    vendor = ver[6:8].decode('ascii', errors='replace')
    result.append(("  厂商代码", _hex(ver[6:8]), vendor, "ASCII码",
                   pos + 6, pos + 8, True))
    result.append(("  芯片代码", _hex(ver[8:10]), "", "芯片的代码",
                   pos + 8, pos + 10, True))
    pos += 10  # off+52
    if pos + 8 > end:
        return
    hard = int.from_bytes(data[pos:pos + 2], 'little')
    soft = int.from_bytes(data[pos + 2:pos + 4], 'little')
    result.append(("  硬复位累积次数", _raw(data, pos, pos + 2), str(hard),
                   "设备硬件复位累计次数", pos, pos + 2, True))
    result.append(("  软复位累积次数", _raw(data, pos + 2, pos + 4), str(soft),
                   "软件复位累计次数", pos + 2, pos + 4, True))
    proxy_type = data[pos + 4]
    result.append(("  代理类型", f"0x{proxy_type:02X}",
                   "站点动态选择的代理" if proxy_type == 0 else f"保留({proxy_type})",
                   "", pos + 4, pos + 5, True))
    result.append(("  保留", _raw(data, pos + 5, pos + 8), "", "",
                   pos + 5, pos + 8, True))
    pos += 8  # off+60
    if pos + 4 > end:
        return
    seq = int.from_bytes(data[pos:pos + 4], 'little')
    result.append(("  端到端序列号", _raw(data, pos, pos + 4), f"0x{seq:08X}",
                   "CCO确认关联入网时需携带", pos, pos + 4, True))
    pos += 4  # off+64
    if pos + 24 > end:
        return
    result.append(("  管理ID信息", _raw(data, pos, pos + 24), "24字节",
                   "通信芯片唯一性标识", pos, pos + 24, True))


# ═════════════════════════════════════════════════════════════
#  0x0001 关联确认（表47）
# ═════════════════════════════════════════════════════════════
def _parse_assoc_cnf(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 20:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    result.append(("  站点MAC地址", _raw(data, off, off + 6), "",
                   "关联确认报文的目的终端设备MAC", off, off + 6, True))
    result.append(("  CCO MAC地址", _raw(data, off + 6, off + 12), "",
                   "本网络的CCO MAC地址", off + 6, off + 12, True))
    res = data[off + 12]
    result.append(("  结果", f"0x{res:02X}", str(res), "关联确认结果",
                   off + 12, off + 13, True))
    level = data[off + 13]
    result.append(("  站点层级", f"0x{level:02X}", str(level),
                   "站点入网后所处拓扑层级", off + 13, off + 14, True))
    tei = _tei12(data[off + 14], data[off + 15])
    link = (data[off + 15] >> 4) & 0x01
    band = (data[off + 15] >> 5) & 0x07
    result.append(("  站点TEI", _raw(data, off + 14, off + 16), str(tei),
                   "CCO分配的设备标识TEI(12bit)", off + 14, off + 16, True))
    result.append(("  链路类型", f"D4={link}", LINK_TYPES.get(link, str(link)),
                   "0=高速载波链路 1=无线链路", off + 15, off + 16, True))
    result.append(("  载波频段", f"D[7:5]={band:03b}", BAND_NAMES.get(band, str(band)),
                   "网络采用的载波频段", off + 15, off + 16, True))
    ptei = _tei12(data[off + 16], data[off + 17])
    result.append(("  代理TEI", _raw(data, off + 16, off + 18), str(ptei),
                   "CCO选定的代理站点TEI(12bit)", off + 16, off + 18, True))
    total = data[off + 18]
    sub = data[off + 19]
    result.append(("  总分包数", f"0x{total:02X}", str(total),
                   "关联回复消息分包总个数", off + 18, off + 19, True))
    result.append(("  分包序号", f"0x{sub:02X}", str(sub),
                   "分包索引值,首个分包为1", off + 19, off + 20, True))
    pos = off + 20
    if pos + 20 > end:
        return
    rand = int.from_bytes(data[pos:pos + 4], 'little')
    result.append(("  站点关联随机数", _raw(data, pos, pos + 4), f"0x{rand:08X}",
                   "请求入网站点在关联请求中携带的随机数", pos, pos + 4, True))
    reassoc = int.from_bytes(data[pos + 4:pos + 8], 'little')
    result.append(("  重新关联时间", _raw(data, pos + 4, pos + 8), f"{reassoc}毫秒",
                   "STA可重新发起关联请求的时间间隔", pos + 4, pos + 8, True))
    seq = int.from_bytes(data[pos + 8:pos + 12], 'little')
    result.append(("  端到端序列号", _raw(data, pos + 8, pos + 12), f"0x{seq:08X}",
                   "端到端管理报文序列号", pos + 8, pos + 12, True))
    path = int.from_bytes(data[pos + 12:pos + 16], 'little')
    result.append(("  路径序号", _raw(data, pos + 12, pos + 16), f"0x{path:08X}",
                   "路径通知序列号,递增", pos + 12, pos + 16, True))
    result.append(("  保留", _raw(data, pos + 16, pos + 20), "", "",
                   pos + 16, pos + 20, True))
    pos += 20  # off+40
    if pos < end:
        result.append(("  路由表信息", _raw(data, pos, end), f"{end - pos}字节",
                       "关联入网站点相关的路由信息", pos, end, True))


# ═════════════════════════════════════════════════════════════
#  0x0002 关联汇总指示（表52 + 表54站点信息）
# ═════════════════════════════════════════════════════════════
def _parse_assoc_gather(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 16:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    res = data[off]
    result.append(("  结果", f"0x{res:02X}", "允许加入网络" if res == 0 else str(res),
                   "固定值为0", off, off + 1, True))
    level = data[off + 1]
    result.append(("  站点层级", f"0x{level:02X}", str(level),
                   "所有新入网站点所处的网络层级", off + 1, off + 2, True))
    result.append(("  CCO MAC地址", _raw(data, off + 2, off + 8), "",
                   "本网络中CCO的设备MAC地址", off + 2, off + 8, True))
    ptei = _tei12(data[off + 8], data[off + 9])
    band = (data[off + 9] >> 4) & 0x07
    result.append(("  代理TEI", _raw(data, off + 8, off + 10), str(ptei),
                   "所通知新入网站点的代理站点TEI(12bit)", off + 8, off + 10, True))
    result.append(("  载波频段", f"D[6:4]={band:03b}", BAND_NAMES.get(band, str(band)),
                   "网络采用的载波频段", off + 9, off + 10, True))
    result.append(("  保留", f"0x{data[off + 10]:02X}", "", "", off + 10, off + 11, True))
    count = data[off + 11]
    result.append(("  汇总站点数", f"0x{count:02X}", str(count),
                   "通知的新入网站点个数", off + 11, off + 12, True))
    result.append(("  保留", _raw(data, off + 12, off + 16), "", "",
                   off + 12, off + 16, True))
    # 站点信息: 表54, 每站点8字节(MAC 6B + TEI 2B)
    pos = off + 16
    for i in range(count):
        if pos + 8 > end:
            result.append(("  站点信息(截断)", _raw(data, pos, end), "",
                           f"声明{count}个站点,仅解析到{i}个", pos, end, True))
            return
        mac = _raw(data, pos, pos + 6)
        tei = _tei12(data[pos + 6], data[pos + 7])
        result.append((f"  站点{i + 1} MAC地址", mac, "", "站点MAC地址",
                       pos, pos + 6, True))
        result.append((f"  站点{i + 1} TEI", _raw(data, pos + 6, pos + 8), str(tei),
                       "分配给站点的TEI(12bit)", pos + 6, pos + 8, True))
        pos += 8
    if pos < end:
        result.append(("  剩余数据", _raw(data, pos, end), f"{end - pos}字节",
                       "", pos, end, True))


# ═════════════════════════════════════════════════════════════
#  0x0003 代理变更请求（表55, 24字节）
# ═════════════════════════════════════════════════════════════
def _parse_change_proxy_req(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 24:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    tei = _tei12(data[off], data[off + 1])
    result.append(("  站点TEI", _raw(data, off, off + 2), str(tei),
                   "申请代理变更站点的设备标识(12bit)", off, off + 2, True))
    pos = off + 2
    for i in range(5):
        t = _tei12(data[pos], data[pos + 1])
        link = (data[pos + 1] >> 4) & 0x01
        result.append((f"  新代理TEI{i}", _raw(data, pos, pos + 2), str(t),
                       f"第{i + 1}个候选代理站点TEI(12bit)", pos, pos + 2, True))
        result.append((f"  新代理{i} 链路类型", f"D4={link}",
                       LINK_TYPES.get(link, str(link)), "", pos + 1, pos + 2, True))
        pos += 2
    old = _tei12(data[pos], data[pos + 1])
    result.append(("  旧代理TEI", _raw(data, pos, pos + 2), str(old),
                   "原代理站点TEI(12bit)", pos, pos + 2, True))
    ptype = data[pos + 2]
    result.append(("  代理类型", f"0x{ptype:02X}",
                   "站点动态选择的代理" if ptype == 0 else f"保留({ptype})",
                   "", pos + 2, pos + 3, True))
    reason = data[pos + 3]
    reason_names = {0: "未知", 1: "周期代理变更"}
    result.append(("  原因", f"0x{reason:02X}", reason_names.get(reason, f"保留({reason})"),
                   "站点发起代理变更原因", pos + 3, pos + 4, True))
    seq = int.from_bytes(data[pos + 4:pos + 8], 'little')
    result.append(("  端到端序列号", _raw(data, pos + 4, pos + 8), f"0x{seq:08X}",
                   "请求站点维护的端到端报文序列号", pos + 4, pos + 8, True))
    ph = data[pos + 8]
    phases = [PHASE_NAMES.get((ph >> s) & 0x03, "?") for s in (0, 2, 4)]
    result.append(("  站点相线", f"0x{ph:02X}", "/".join(phases),
                   "发起代理变更请求站点的相线信息", pos + 8, pos + 9, True))
    result.append(("  保留", _raw(data, pos + 9, pos + 12), "", "",
                   pos + 9, pos + 12, True))


# ═════════════════════════════════════════════════════════════
#  0x0004 代理变更确认（表56 + 表57子站点条目）
# ═════════════════════════════════════════════════════════════
def _parse_change_proxy_cnf(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 20:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    res = data[off]
    result.append(("  结果", f"0x{res:02X}", "变更成功" if res == 0 else f"保留({res})",
                   "代理变更结果", off, off + 1, True))
    result.append(("  总分包数", f"0x{data[off + 1]:02X}", str(data[off + 1]),
                   "", off + 1, off + 2, True))
    result.append(("  分包序号", f"0x{data[off + 2]:02X}", str(data[off + 2]),
                   "分包索引,首个为1", off + 2, off + 3, True))
    result.append(("  保留", f"0x{data[off + 3]:02X}", "", "", off + 3, off + 4, True))
    tei = _tei12(data[off + 4], data[off + 5])
    link = (data[off + 5] >> 4) & 0x01
    result.append(("  站点TEI", _raw(data, off + 4, off + 6), str(tei),
                   "申请代理变更的站点TEI(12bit)", off + 4, off + 6, True))
    result.append(("  链路类型", f"D4={link}", LINK_TYPES.get(link, str(link)),
                   "", off + 5, off + 6, True))
    ptei = _tei12(data[off + 6], data[off + 7])
    result.append(("  代理TEI", _raw(data, off + 6, off + 8), str(ptei),
                   "新代理站点TEI(12bit)", off + 6, off + 8, True))
    seq = int.from_bytes(data[off + 8:off + 12], 'little')
    result.append(("  端到端序列号", _raw(data, off + 8, off + 12), f"0x{seq:08X}",
                   "", off + 8, off + 12, True))
    path = int.from_bytes(data[off + 12:off + 16], 'little')
    result.append(("  路径序号", _raw(data, off + 12, off + 16), f"0x{path:08X}",
                   "路径通知序列号,递增", off + 12, off + 16, True))
    count = int.from_bytes(data[off + 16:off + 18], 'little')
    result.append(("  子站点数", _raw(data, off + 16, off + 18), str(count),
                   "申请代理变更站点的所有子站点数目", off + 16, off + 18, True))
    result.append(("  保留", _raw(data, off + 18, off + 20), "", "",
                   off + 18, off + 20, True))
    # 子站点条目: 表57, 每条2字节
    pos = off + 20
    for i in range(count):
        if pos + 2 > end:
            result.append(("  子站点条目(截断)", _raw(data, pos, end), "",
                           f"声明{count}个,仅解析到{i}个", pos, end, True))
            return
        t = _tei12(data[pos], data[pos + 1])
        result.append((f"  子站点TEI[{i}]", _raw(data, pos, pos + 2), str(t),
                       "", pos, pos + 2, True))
        pos += 2
    if pos < end:
        result.append(("  剩余数据", _raw(data, pos, end), f"{end - pos}字节",
                       "", pos, end, True))


# ═════════════════════════════════════════════════════════════
#  0x0005 代理变更确认-位图版（表58）
# ═════════════════════════════════════════════════════════════
def _parse_change_proxy_bitmap_cnf(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 20:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    res = data[off]
    result.append(("  结果", f"0x{res:02X}", "变更成功" if res == 0 else f"保留({res})",
                   "代理变更结果", off, off + 1, True))
    result.append(("  保留", f"0x{data[off + 1]:02X}", "", "", off + 1, off + 2, True))
    bmp_size = int.from_bytes(data[off + 2:off + 4], 'little')
    result.append(("  位图大小", _raw(data, off + 2, off + 4), f"{bmp_size}字节",
                   "子站点位图字段大小", off + 2, off + 4, True))
    tei = _tei12(data[off + 4], data[off + 5])
    link = (data[off + 5] >> 4) & 0x01
    result.append(("  站点TEI", _raw(data, off + 4, off + 6), str(tei),
                   "申请代理变更的站点TEI(12bit)", off + 4, off + 6, True))
    result.append(("  链路类型", f"D4={link}", LINK_TYPES.get(link, str(link)),
                   "", off + 5, off + 6, True))
    ptei = _tei12(data[off + 6], data[off + 7])
    result.append(("  代理TEI", _raw(data, off + 6, off + 8), str(ptei),
                   "新代理站点TEI(12bit)", off + 6, off + 8, True))
    seq = int.from_bytes(data[off + 8:off + 12], 'little')
    result.append(("  端到端序列号", _raw(data, off + 8, off + 12), f"0x{seq:08X}",
                   "", off + 8, off + 12, True))
    path = int.from_bytes(data[off + 12:off + 16], 'little')
    result.append(("  路径序号", _raw(data, off + 12, off + 16), f"0x{path:08X}",
                   "路径通知序列号", off + 12, off + 16, True))
    result.append(("  保留", _raw(data, off + 16, off + 20), "", "",
                   off + 16, off + 20, True))
    pos = off + 20
    if pos < end:
        bmp_end = min(pos + bmp_size, end)
        result.append(("  子站点位图", _raw(data, pos, bmp_end), f"{bmp_end - pos}字节",
                       "位图表示子站点TEI,bit=1对应TEI有效", pos, bmp_end, True))
        if bmp_end < end:
            result.append(("  剩余数据", _raw(data, bmp_end, end),
                           f"{end - bmp_end}字节", "", bmp_end, end, True))


# ═════════════════════════════════════════════════════════════
#  0x0006 离线指示（表59 + 表60 MAC列表）
# ═════════════════════════════════════════════════════════════
def _parse_leave_ind(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 16:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    reason = int.from_bytes(data[off:off + 2], 'little')
    reason_names = {0: "CCO通知站点立即离线", 1: "网络拓扑层级超过上限", 2: "站点不在最新白名单中"}
    result.append(("  原因", _raw(data, off, off + 2),
                   reason_names.get(reason, f"保留({reason})"),
                   "CCO告知站点需要离线的原因", off, off + 2, True))
    count = int.from_bytes(data[off + 2:off + 4], 'little')
    result.append(("  站点总数", _raw(data, off + 2, off + 4), str(count),
                   "需要离线的站点个数", off + 2, off + 4, True))
    delay = int.from_bytes(data[off + 4:off + 6], 'little')
    result.append(("  延迟时间", _raw(data, off + 4, off + 6), f"{delay}秒",
                   "延迟时间到期后离线", off + 4, off + 6, True))
    result.append(("  保留", _raw(data, off + 6, off + 16), "10字节", "",
                   off + 6, off + 16, True))
    # 站点MAC列表: 表60, 每站点6字节
    pos = off + 16
    for i in range(count):
        if pos + 6 > end:
            result.append(("  站点MAC列表(截断)", _raw(data, pos, end), "",
                           f"声明{count}个,仅解析到{i}个", pos, end, True))
            return
        result.append((f"  离线站点MAC[{i}]", _raw(data, pos, pos + 6), "",
                       "", pos, pos + 6, True))
        pos += 6
    if pos < end:
        result.append(("  剩余数据", _raw(data, pos, end), f"{end - pos}字节",
                       "", pos, end, True))


# ═════════════════════════════════════════════════════════════
#  0x0007 心跳检测（表61）
# ═════════════════════════════════════════════════════════════
def _parse_heartbeat(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 8:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    otei = _tei12(data[off], data[off + 1])
    result.append(("  原始源TEI", _raw(data, off, off + 2), str(otei),
                   "初始产生心跳检测报文的站点TEI,转发不变更(12bit)", off, off + 2, True))
    mtei = _tei12(data[off + 2], data[off + 3])
    result.append(("  发现站点数最大的站点TEI", _raw(data, off + 2, off + 4), str(mtei),
                   "沿途转发站点中发现周围站点数量最多的站点TEI(12bit)",
                   off + 2, off + 4, True))
    max_cnt = int.from_bytes(data[off + 4:off + 6], 'little')
    result.append(("  最大的发现站点数", _raw(data, off + 4, off + 6), str(max_cnt),
                   "沿途站点中最大的发现站点数量", off + 4, off + 6, True))
    bmp_size = int.from_bytes(data[off + 6:off + 8], 'little')
    result.append(("  位图大小", _raw(data, off + 6, off + 8), f"{bmp_size}字节",
                   "发现站点位图字段大小", off + 6, off + 8, True))
    pos = off + 8
    if pos < end:
        bmp_end = min(pos + bmp_size, end)
        result.append(("  发现站点位图", _raw(data, pos, bmp_end), f"{bmp_end - pos}字节",
                       "位图表示可发现站点TEI,bit=1对应TEI有效", pos, bmp_end, True))
        if bmp_end < end:
            result.append(("  剩余数据", _raw(data, bmp_end, end),
                           f"{end - bmp_end}字节", "", bmp_end, end, True))


# ═════════════════════════════════════════════════════════════
#  0x0008 发现列表（表62 + 信息单元）/ 单跳载波发现列表
#  无线发现列表（表91, rf=True）
# ═════════════════════════════════════════════════════════════
def _parse_discover_list(data: bytes, off: int, result: List[Tuple], rf: bool = False) -> None:
    """发现列表报文内容解析（不含 MMTYPE 头）

    表62/表91: 站点MAC(6B) + 统计序号(1B) + 信息单元TLV×N
    rf=True 时使用表92 无线站点属性(14B)，否则表63 站点属性(23B)
    """
    end = len(data)
    if end < off + 7:
        result.append(("    报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    result.append(("    站点MAC地址", _raw(data, off, off + 6), "",
                   "发送发现列表报文节点的MAC地址", off, off + 6, True))
    seq = data[off + 6]
    result.append(("    统计序号", f"0x{seq:02X}", str(seq),
                   "每次发送递增1,255后环回为0", off + 6, off + 7, True))
    _parse_info_units(data, off + 7, end, result, rf)


def _looks_like_discover_list(data: bytes, off: int) -> bool:
    """表62格式合理性检查: 站点MAC非全0/全F 且首个信息单元类型∈{0,1,2,3}"""
    end = len(data)
    if end < off + 8:
        return False
    mac = data[off:off + 6]
    if all(x == 0x00 for x in mac) or all(x == 0xFF for x in mac):
        return False
    unit_type = data[off + 7] & 0x7F
    return unit_type in (0, 1, 2, 3)


def _parse_discover_list_mme(data: bytes, off: int, result: List[Tuple]) -> None:
    """0x0008 MME 入口：发现列表报文（表62）

    表43标注0x0008为保留，发现列表标识符为推断值；
    若内容不符合表62格式(可能为厂商自定义/双模扩展消息)，降级为原始显示。
    """
    if not _looks_like_discover_list(data, off):
        result.append(("  报文内容", _raw(data, off, len(data)),
                       f"{len(data) - off}字节",
                       "内容与表62发现列表格式不符,可能为厂商自定义/双模扩展消息,原始显示",
                       off, len(data), True))
        return
    result.append(("  发现列表报文内容", "", "MMeDiscoverNodeList",
                   "表62", off, len(data), True))
    _parse_discover_list(data, off, result, rf=False)


def _parse_info_units(data: bytes, pos: int, end: int, result: List[Tuple], rf: bool) -> None:
    """信息单元 TLV 循环解析（表62/91 共用）

    单元头: 类型(7bit) + 长度类型(1bit) + 长度(1/2B) + 内容
    类型: 0=站点属性信息 1=站点路由信息 2=邻居节点信道信息非位图版 3=位图版
    """
    unit_names = {0: "站点属性信息", 1: "站点路由信息",
                  2: "邻居节点信道信息(非位图版)", 3: "邻居节点信道信息(位图版)"}
    idx = 1
    while pos + 2 <= end:
        b = data[pos]
        utype = b & 0x7F
        ltype = (b >> 7) & 0x01
        uname = unit_names.get(utype, f"保留({utype})")
        if ltype == 0:
            ulen = data[pos + 1]
            hdr = 2
        else:
            if pos + 3 > end:
                return
            ulen = data[pos + 1] | (data[pos + 2] << 8)
            hdr = 3
        result.append((f"    信息单元{idx}类型", f"0x{b:02X}", f"{utype} ({uname})",
                       f"长度位宽={'2字节' if ltype else '1字节'}", pos, pos + 1, True))
        result.append((f"    信息单元{idx}长度", _raw(data, pos + 1, pos + hdr),
                       f"{ulen}字节", "信息单元内容长度(不含类型/长度字段)",
                       pos + 1, pos + hdr, True))
        c_start = pos + hdr
        c_end = min(c_start + ulen, end)
        if utype == 0:
            if rf:
                _parse_rf_station_attr(data, c_start, c_end, result)
            else:
                _parse_station_attr(data, c_start, c_end, result)
        elif utype == 1:
            _parse_route_info(data, c_start, c_end, result)
        elif utype in (2, 3) and c_start < c_end:
            combo = data[c_start] & 0x0F
            result.append((f"    信息单元{idx}内容", _raw(data, c_start, c_end),
                           f"组合类型={combo}", "邻居节点信道信息(组合类型+条目原始数据)",
                           c_start, c_end, True))
        elif c_start < c_end:
            result.append((f"    信息单元{idx}内容", _raw(data, c_start, c_end),
                           f"{c_end - c_start}字节", "保留类型,原始数据",
                           c_start, c_end, True))
        if c_end <= pos:  # 防止死循环
            break
        pos = c_end
        idx += 1
    if pos < end:
        result.append(("    剩余数据", _raw(data, pos, end), f"{end - pos}字节",
                       "", pos, end, True))


def _parse_station_attr(data: bytes, off: int, end: int, result: List[Tuple]) -> None:
    """站点属性信息（表63, 23字节）"""
    if end < off + 23:
        result.append(("      站点属性(数据不足23字节)", _raw(data, off, end), "",
                       "", off, end, True))
        return
    tei = _tei12(data[off], data[off + 1])
    ptei = (data[off + 1] >> 4) | (data[off + 2] << 4)
    role = data[off + 3] & 0x0F
    level = (data[off + 3] >> 4) & 0x0F
    result.append(("      TEI", _raw(data, off, off + 2), str(tei),
                   "发送发现列表报文站点的TEI(12bit)", off, off + 2, True))
    result.append(("      代理TEI", _raw(data, off + 1, off + 3), str(ptei),
                   "该站点的代理站点TEI(12bit)", off + 1, off + 3, True))
    result.append(("      角色", f"D[3:0]={role:04b}", ROLE_NAMES.get(role, f"保留({role})"),
                   "", off + 3, off + 4, True))
    result.append(("      层级", f"D[7:4]={level:04b}", str(level),
                   "网络层级", off + 3, off + 4, True))
    result.append(("      CCO MAC地址", _raw(data, off + 4, off + 10), "",
                   "本网络CCO的MAC地址", off + 4, off + 10, True))
    ph = data[off + 10] & 0x3F
    result.append(("      相线", f"0x{data[off + 10]:02X}", f"0x{ph:02X}",
                   "站点评估所属相线(按优先顺序)", off + 10, off + 11, True))
    result.append(("      代理站点信道质量", f"0x{data[off + 11]:02X}", str(data[off + 11]),
                   "原始信噪比数据", off + 11, off + 12, True))
    result.append(("      代理站点通信成功率", f"0x{data[off + 12]:02X}",
                   f"{data[off + 12]}%", "与代理站点上下行通信成功率(百分比)",
                   off + 12, off + 13, True))
    result.append(("      代理站点下行通信成功率", f"0x{data[off + 13]:02X}",
                   f"{data[off + 13]}%", "接收代理站点下行报文成功率",
                   off + 13, off + 14, True))
    remain = int.from_bytes(data[off + 14:off + 16], 'little')
    result.append(("      路由周期到期剩余时间", _raw(data, off + 14, off + 16),
                   f"{remain}秒", "距当前路由周期到期剩余时间", off + 14, off + 16, True))
    result.append(("      最小通信成功率", f"0x{data[off + 16]:02X}",
                   f"{data[off + 16]}%", "到CCO路径中最弱连接的通信成功率",
                   off + 16, off + 17, True))
    result.append(("      发现列表周期", f"0x{data[off + 17]:02X}",
                   f"{data[off + 17]}秒", "发送发现列表报文间隔周期",
                   off + 17, off + 18, True))
    result.append(("      接收率老化周期个数", f"0x{data[off + 18]:02X}",
                   str(data[off + 18]), "", off + 18, off + 19, True))
    # 代理BRU SNR信息(4B, 表64): 8个BRU各4bit, 0=-10dB步进3dB
    bru = data[off + 19:off + 23]
    vals = []
    for i in range(8):
        v = (bru[i // 2] >> (4 * (i % 2))) & 0x0F
        vals.append(f"BRU{i}={-10 + v * 3}dB")
    result.append(("      代理BRU SNR信息", _hex(bru), " ".join(vals),
                   "BRU0~BRU7,0代表-10dB,3dB步进", off + 19, off + 23, True))


def _parse_rf_station_attr(data: bytes, off: int, end: int, result: List[Tuple]) -> None:
    """无线站点属性信息（表92, 14字节）"""
    if end < off + 14:
        result.append(("      站点属性(数据不足14字节)", _raw(data, off, end), "",
                       "", off, end, True))
        return
    result.append(("      CCO MAC地址", _raw(data, off, off + 6), "",
                   "", off, off + 6, True))
    ptei = _tei12(data[off + 6], data[off + 7])
    role = (data[off + 7] >> 4) & 0x0F
    result.append(("      代理TEI", _raw(data, off + 6, off + 8), str(ptei),
                   "发送无线发现列表站点的代理站点TEI(12bit)", off + 6, off + 8, True))
    result.append(("      角色", f"D[7:4]={role:04b}", ROLE_NAMES.get(role, f"保留({role})"),
                   "", off + 7, off + 8, True))
    level = data[off + 8] & 0x0F
    rf_hops = (data[off + 8] >> 4) & 0x0F
    result.append(("      层级", f"D[3:0]={level:04b}", str(level),
                   "网络层级", off + 8, off + 9, True))
    result.append(("      链路RF跳数", f"D[7:4]={rf_hops:04b}", str(rf_hops),
                   "站点所在路径上无线的跳数", off + 8, off + 9, True))
    result.append(("      代理上行接收率", f"0x{data[off + 9]:02X}", f"{data[off + 9]}%",
                   "接收代理站点上行报文成功率", off + 9, off + 10, True))
    result.append(("      代理下行接收率", f"0x{data[off + 10]:02X}", f"{data[off + 10]}%",
                   "接收代理站点下行报文成功率", off + 10, off + 11, True))
    result.append(("      链路最小接收率", f"0x{data[off + 11]:02X}", f"{data[off + 11]}%",
                   "到CCO路径中最弱连接的通信成功率", off + 11, off + 12, True))
    result.append(("      无线发现列表周期", f"0x{data[off + 12]:02X}",
                   f"{data[off + 12]}秒", "无线发现列表周期长度", off + 12, off + 13, True))
    result.append(("      无线接收率老化周期个数", f"0x{data[off + 13]:02X}",
                   str(data[off + 13]), "单位:无线发现列表周期", off + 13, off + 14, True))


def _parse_route_info(data: bytes, off: int, end: int, result: List[Tuple]) -> None:
    """站点路由信息（表65/93, 每条目2字节）"""
    pos = off
    idx = 1
    while pos + 2 <= end:
        tei = _tei12(data[pos], data[pos + 1])
        rtype = (data[pos + 1] >> 4) & 0x0F
        rname = ROUTE_TYPES.get(rtype, f"保留({rtype})")
        result.append((f"      下一跳站点TEI[{idx}]", _raw(data, pos, pos + 2), str(tei),
                       f"路由类型: {rname}", pos, pos + 2, True))
        pos += 2
        idx += 1
    if pos < end:
        result.append(("      路由信息(剩余)", _raw(data, pos, end), "", "", pos, end, True))


# ═════════════════════════════════════════════════════════════
#  0x0009 通信成功率上报（表78 + 表79）
# ═════════════════════════════════════════════════════════════
def _parse_success_rate(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 4:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    tei = _tei12(data[off], data[off + 1])
    result.append(("  TEI", _raw(data, off, off + 2), str(tei),
                   "代理站点自身的设备标识TEI(12bit)", off, off + 2, True))
    count = int.from_bytes(data[off + 2:off + 4], 'little')
    result.append(("  站点总数", _raw(data, off + 2, off + 4), str(count),
                   "代理站点的子站点个数/STA表项数目", off + 2, off + 4, True))
    # STA条目: 表79, 每条4字节
    pos = off + 4
    for i in range(count):
        if pos + 4 > end:
            result.append(("  通信成功率信息(截断)", _raw(data, pos, end), "",
                           f"声明{count}个,仅解析到{i}个", pos, end, True))
            return
        t = _tei12(data[pos], data[pos + 1])
        down = data[pos + 2]
        up = data[pos + 3]
        result.append((f"  子站点[{i}] TEI", _raw(data, pos, pos + 2), str(t),
                       f"下行成功率={down}% 上行成功率={up}%", pos, pos + 4, True))
        pos += 4
    if pos < end:
        result.append(("  剩余数据", _raw(data, pos, end), f"{end - pos}字节",
                       "", pos, end, True))


# ═════════════════════════════════════════════════════════════
#  0x000A 网络冲突上报（表80 + 表81）
# ═════════════════════════════════════════════════════════════
def _parse_network_conflict(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 8:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    result.append(("  CCO MAC地址", _raw(data, off, off + 6), "",
                   "与本网络冲突的邻居网络CCO MAC", off, off + 6, True))
    count = data[off + 6]
    result.append(("  邻居网络个数", f"0x{count:02X}", str(count),
                   "周边可见邻居网络个数", off + 6, off + 7, True))
    width = data[off + 7]
    result.append(("  网络号字节宽度", f"0x{width:02X}", str(width),
                   "单位:字节,默认3", off + 7, off + 8, True))
    pos = off + 8
    for i in range(count):
        if pos + width > end:
            result.append(("  邻居网络条目(截断)", _raw(data, pos, end), "",
                           "", pos, end, True))
            return
        nid = int.from_bytes(data[pos:pos + width], 'little')
        result.append((f"  邻居网络[{i}]", _raw(data, pos, pos + width), f"0x{nid:X}",
                       "", pos, pos + width, True))
        pos += width
    if pos < end:
        result.append(("  剩余数据", _raw(data, pos, end), f"{end - pos}字节",
                       "", pos, end, True))


# ═════════════════════════════════════════════════════════════
#  0x000B 过零NTB采集指示（表82, 8字节）
# ═════════════════════════════════════════════════════════════
def _parse_zc_collect(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 8:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    tei = _tei12(data[off], data[off + 1])
    result.append(("  TEI", _raw(data, off, off + 2), str(tei),
                   "需进行过零NTB采集的站点TEI(12bit,单站点采集时有效)", off, off + 2, True))
    site = data[off + 2]
    site_names = {0: "指定单站点采集", 1: "指定全网站点采集"}
    result.append(("  采集站点", f"0x{site:02X}", site_names.get(site, f"保留({site})"),
                   "", off + 2, off + 3, True))
    period = data[off + 3]
    period_names = {0: "二分之一电力线周期", 1: "一个电力线周期"}
    result.append(("  采集周期", f"0x{period:02X}", period_names.get(period, f"保留({period})"),
                   "电力线周期20毫秒", off + 3, off + 4, True))
    cnt = data[off + 4]
    result.append(("  采集数量", f"0x{cnt:02X}", str(cnt),
                   "连续采集过零点NTB的数量", off + 4, off + 5, True))
    result.append(("  保留", _raw(data, off + 5, off + 8), "", "", off + 5, off + 8, True))


# ═════════════════════════════════════════════════════════════
#  0x000C 过零NTB上报（表85 + 表86差值）
# ═════════════════════════════════════════════════════════════
def _read_packed_12bit(buf: bytes, index: int) -> int:
    """读取第 index 个 12bit 差值（LSB-first 紧凑比特流, 表86）"""
    bitpos = index * 12
    val = 0
    for k in range(12):
        bp = bitpos + k
        if (bp // 8) >= len(buf):
            break
        if (buf[bp // 8] >> (bp % 8)) & 1:
            val |= 1 << k
    return val


def _parse_zc_report(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 10:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    tei = _tei12(data[off], data[off + 1])
    result.append(("  TEI", _raw(data, off, off + 2), str(tei),
                   "告知过零NTB信息的站点TEI(12bit)", off, off + 2, True))
    total = data[off + 2]
    result.append(("  告知总数量", f"0x{total:02X}", str(total),
                   "站点告知的过零NTB数量", off + 2, off + 3, True))
    counts = [data[off + 3], data[off + 4], data[off + 5]]
    for i, c in enumerate(counts):
        result.append((f"  相线{i + 1}差值告知数量", f"0x{c:02X}", str(c),
                       "", off + 3 + i, off + 4 + i, True))
    ntb = int.from_bytes(data[off + 6:off + 10], 'little')
    result.append(("  基准NTB", _raw(data, off + 6, off + 10), f"0x{ntb:08X}",
                   "第一个过零点NTB值(原始32bit右移8bit后的高24bit)",
                   off + 6, off + 10, True))
    # 各相线差值: 表86, 每差值12bit紧凑打包
    pos = off + 10
    for i, c in enumerate(counts):
        blen = (c * 12 + 7) // 8
        if pos + blen > end:
            if pos < end:
                result.append((f"  相线{i + 1}过零NTB差值(截断)", _raw(data, pos, end),
                               "", f"声明{c}个差值", pos, end, True))
            return
        buf = data[pos:pos + blen]
        diffs = [_read_packed_12bit(buf, j) for j in range(c)]
        result.append((f"  相线{i + 1}过零NTB差值", _hex(buf),
                       " ".join(str(d) for d in diffs),
                       f"{c}个差值(12bit/个)", pos, pos + blen, True))
        pos += blen
    if pos < end:
        result.append(("  剩余数据", _raw(data, pos, end), f"{end - pos}字节",
                       "", pos, end, True))


# ═════════════════════════════════════════════════════════════
#  0x004F 网络诊断报文（表87 + 表88）
# ═════════════════════════════════════════════════════════════
def _parse_diagnose(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    if end < off + 2:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "", "",
                       off, end, True))
        return
    vid = data[off] | (data[off + 1] << 8)
    vname = VENDOR_IDS.get(vid, f"待扩展(0x{vid:04X})")
    result.append(("  芯片厂商ID", _raw(data, off, off + 2), f"0x{vid:04X} ({vname})",
                   "各厂商非标准自定义报文", off, off + 2, True))
    if off + 2 < end:
        result.append(("  厂家自定义", _raw(data, off + 2, end), f"{end - off - 2}字节",
                       "厂商自定义内容,格式不做统一要求", off + 2, end, True))


# ═════════════════════════════════════════════════════════════
#  0x0080 无线信道冲突上报（表89 + 表90）
# ═════════════════════════════════════════════════════════════
def _parse_rf_channel_conflict(data: bytes, off: int, result: List[Tuple]) -> None:
    end = len(data)
    # 表89: CCO MAC(6B) + 邻居网络个数(1B) = 7 字节
    if end < off + 7:
        result.append(("  报文内容(数据不足)", _raw(data, off, end), "",
                       f"需至少7字节(CCO MAC 6B+个数 1B), 实际{end - off}字节",
                       off, end, True))
        return
    result.append(("  CCO MAC地址", _raw(data, off, off + 6), "",
                   "与本网络发生冲突的邻居网络CCO MAC", off, off + 6, True))
    # 表89: CCO MAC(6B) + 邻居网络个数(1B) + 条目(表90)
    count = data[off + 6]
    result.append(("  邻居网络个数", f"0x{count:02X}", str(count),
                   "周边可见邻居网络个数", off + 6, off + 7, True))
    # 邻居网络条目(表90): 分组布局, 先N个无线信道号再N个option
    #   邻居网络(0)信道号 ... 邻居网络(N-1)信道号 | 邻居网络(0)option ... 邻居网络(N-1)option
    pos = off + 7
    channels = []
    for i in range(count):
        if pos >= end:
            result.append((f"  邻居网络[{i}]信道号(截断)", _raw(data, pos, end), "",
                           "", pos, end, True))
            return
        channels.append(data[pos])
        pos += 1
    for i in range(count):
        if pos >= end:
            result.append((f"  邻居网络[{i}]option(截断)", _raw(data, pos, end), "",
                           "", pos, end, True))
            return
        opt = data[pos]
        result.append((f"  邻居网络[{i}]", f"信道号=0x{channels[i]:02X} option=0x{opt:02X}",
                       f"信道号={channels[i]} option=0x{opt:02X}",
                       "先信道号后option(表90)", off + 7 + i, pos, True))
        pos += 1
    if pos < end:
        result.append(("  剩余数据", _raw(data, pos, end), f"{end - pos}字节",
                       "", pos, end, True))


# ── MMTYPE → 报文内容解析器 映射 ─────────────────────────────
_MME_CONTENT_PARSERS = {
    0x0000: _parse_assoc_req,
    0x0001: _parse_assoc_cnf,
    0x0002: _parse_assoc_gather,
    0x0003: _parse_change_proxy_req,
    0x0004: _parse_change_proxy_cnf,
    0x0005: _parse_change_proxy_bitmap_cnf,
    0x0006: _parse_leave_ind,
    0x0007: _parse_heartbeat,
    0x0008: _parse_discover_list_mme,
    0x0009: _parse_success_rate,
    0x000A: _parse_network_conflict,
    0x000B: _parse_zc_collect,
    0x000C: _parse_zc_report,
    0x004F: _parse_diagnose,
    0x0080: _parse_rf_channel_conflict,
}
