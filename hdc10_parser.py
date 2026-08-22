"""
HDC 1.0 双模互联互通协议解析器 (Q/GDW 12087.42-2020)

帧结构:
  MPDU = FC(16B) + 物理块PB x N
  PB = PBH(1B) + PB体 + PBCS(3B, CRC-24)
  MAC帧 = MAC帧头 + MSDU + ICV(4B, CRC-32)

MAC帧头两种形态:
  - 标准帧(版本=0, 长帧头): 16B固定域 + 可选12B MAC地址
  - 单跳帧(版本=1, 短帧头): 4B (仅无线信道)

约定:
  - 多字节字段默认小端
  - MAC地址大端
"""

from typing import List, Tuple, Optional

try:
    import crcmod
    _CRC24_FUN = crcmod.mkCrcFun(0x1800063, initCrc=0x000000, rev=True, xorOut=0x000000)
except ImportError:
    _CRC24_FUN = None

import zlib


# ── 常量映射 ──────────────────────────────────────────────────────

# 定界符类型
DELIMITER_TYPES = {
    0: "信标帧",
    1: "SOF帧",
    2: "选择确认帧(SACK)",
    3: "网间协调帧",
}

# 网络类型
NETWORK_TYPES = {
    0: "用电信息采集系统",
}

# 标准版本号
STANDARD_VERSIONS = {
    0: "HDC 1.0 (本标准)",
}

# 分集拷贝基本模式（载波）
PLC_DIVERSITY_MODES = {
    0: "模式0: 520B, 4分集, QPSK, 1/2",
    1: "模式1: 520B, 2分集, QPSK, 1/2",
    4: "模式4: 136B, 7分集, BPSK, 1/2",
    6: "模式6: 136B, 7分集, QPSK, 1/2",
    9: "模式9: 520B, 7分集, QPSK, 1/2",
    10: "模式10: 520B, 2分集, BPSK, 1/2",
    12: "模式12: 264B, 7分集, BPSK, 1/2",
    14: "模式14: 72B, 7分集, BPSK, 1/2",
    15: "扩展模式",
}

# 相线
PHASE_TYPES = {
    0: "未知",
    1: "A相",
    2: "B相",
    3: "C相",
}

# 无线PB大小编码
HRF_PB_SIZES = {
    0: (16, "16字节"),
    1: (40, "40字节"),
    2: (72, "72字节"),
    3: (136, "136字节"),
    4: (264, "264字节"),
    5: (520, "520字节"),
}

# 无线MCS
HRF_MCS = {
    0: "MCS0: PB16, BPSK, 1/2",
    1: "MCS1: PB40, BPSK, 1/2",
    2: "MCS2: PB72, BPSK, 1/2",
    3: "MCS3: PB136, BPSK, 1/2",
    4: "MCS4: PB136, QPSK, 1/2",
    5: "MCS5: PB264, BPSK, 1/2",
    6: "MCS6: PB264, QPSK, 1/2",
    7: "MCS7: PB520, BPSK, 1/2",
    8: "MCS8: PB520, QPSK, 1/2",
    9: "MCS9: PB520, QPSK, 4/5",
}

# 接收结果
SACK_RESULTS = {
    0: "全部接收成功",
    1: "存在CRC失败",
}

# MAC帧头版本
MAC_VERSIONS = {
    0: "标准帧协议(长帧头)",
    1: "单跳帧协议(短帧头)",
}

# 发送类型
TX_TYPES = {
    0: "单播",
    1: "全网广播",
    2: "本地广播",
    3: "代理广播",
}

# MSDU类型
MSDU_TYPES = {
    0: "网络管理消息",
    48: "应用层报文",
    49: "IP报文",
}

# 广播方向
BROADCAST_DIRS = {
    0: "双向广播",
    1: "下行广播(CCO→STA)",
    2: "上行广播(STA→CCO)",
}

# 单跳消息类型
SINGLEHOP_MSG_TYPES = {
    0: "发现列表消息",
    128: "应用层报文",
    129: "IPV4报文",
}

# 报文端口号
APP_PORTS = {
    0x11: "普通业务(抄表/校时/事件/注册等)",
    0x12: "升级业务",
    0x1A: "鉴权安全",
}

# 安全模式（报文ID高4位）
SECURITY_MODES = {
    0: "明文传输",
    1: "数据机密性保护",
    2: "数据完整性保护",
    3: "数据全面保护",
}

# 转发数据规约类型
PROTOCOL_TYPES = {
    0: "透明传输",
    1: "DL/T645-1997",
    2: "DL/T645-2007",
    3: "DL/T698.45",
}

# 报文ID名称映射（业务ID低12位）
MSG_ID_NAMES = {
    0x001: "终端主动抄表",
    0x002: "路由主动抄表",
    0x003: "终端主动并发抄表",
    0x004: "校时",
    0x006: "通信测试",
    0x008: "事件上报",
    0x011: "查询从节点主动注册",
    0x012: "启动从节点主动注册",
    0x013: "停止从节点注册",
    0x020: "确认/否认",
    0x030: "开始升级",
    0x031: "停止升级",
    0x032: "传输文件数据(单播)",
    0x033: "传输文件数据(单播转本地广播)",
    0x034: "查询站点升级状态",
    0x035: "执行升级",
    0x036: "查询站点信息",
    0x040: "抄控器CCO",
    0x041: "抄控器数据透传串口转发",
    0x0A0: "鉴权安全",
    0x0A1: "台区户变关系识别",
    0x0A2: "查询ID信息",
    0x0A3: "精准校时",
    0x0A4: "配电信息上报",
}


# ── CRC 工具 ──────────────────────────────────────────────────────

def _crc24(data: bytes) -> int:
    """CRC-24 (poly 0x800063, 反射模式, init=0, xorOut=0)"""
    if _CRC24_FUN is not None:
        return _CRC24_FUN(data)
    # 纯Python回退
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x800063 >> 1  # TODO: 验证
            else:
                crc >>= 1
    return crc


def _crc32(data: bytes) -> int:
    """CRC-32 (IEEE 802.3, 与zlib一致)"""
    return zlib.crc32(data) & 0xFFFFFFFF


# ── 主解析器类 ────────────────────────────────────────────────────

class HDC10Parser:
    """HDC 1.0 双模互联互通协议解析器"""

    # 信标条目类型映射 (HDC 1.0 与 HDC 2.0 通用)
    BEACON_ENTRY_NAMES = {
        0x00: "站点能力条目",
        0x01: "路由参数条目",
        0x02: "频段变更条目",
        0x03: "无线路由参数条目",
        0x04: "无线信道变更条目",
        0x05: "精简信标站点信息及时隙条目",
        0x06: "万年历条目",
        0x07: "信道评估参数条目",
        0x08: "信标机制切换条目",
        0xC0: "时隙分配条目",
        0xC1: "代理角色条目",
        0xC2: "发现列表条目",
        0xF0: "时隙分配条目",  # HDC 1.0
    }

    def __init__(self):
        self._channel = "plc"  # "plc" 或 "hrf"
        self._aggregated = False
        self._std_version = 0  # 0=HDC 1.0, 1=HDC 2.0

    # ─── 主入口 ────────────────────────────────────────────────

    def parse_to_table(self, frame_bytes: bytes, parse_level: str = "auto",
                       **kwargs) -> List[Tuple]:
        """
        主入口：解析帧为表格数据

        parse_level:
          auto    - 自动识别，完整解析
          fc_pb   - 解析 FC + 完整物理块 PB
          fc_only - 仅解析帧控制 FC
          mac_only- 仅解析 MAC 帧（输入即PB体中的MAC帧）
          pb_only - 仅解析物理块 PB，需 frame_type
          fc_mac  - 解析 FC + PBH + MAC 帧头
          app     - 仅解析应用层报文
        """
        self._channel = kwargs.get('channel', 'plc')
        frame_type = kwargs.get('frame_type', 1)  # 默认SOF
        table = []
        flen = len(frame_bytes)

        if flen < 2:
            table.append(("❌ 解析失败", "", "", "帧长度不足", None, None))
            return table

        # ── 模式分派 ──
        if parse_level == "fc_only":
            return self._parse_fc(frame_bytes, 0)

        if parse_level == "app":
            return self._parse_app_only(frame_bytes)

        if parse_level == "mac_only":
            return self._parse_mac_only(frame_bytes, frame_type)

        if parse_level == "pb_only":
            return self._parse_pb_only(frame_bytes, frame_type)

        # auto / fc_pb / fc_mac: 检测是否有 FC
        has_fc = self._detect_fc(frame_bytes)

        if not has_fc:
            # 无 FC，尝试按 MAC 帧解析
            if self._detect_mac_header(frame_bytes):
                return self._parse_mac_only(frame_bytes, frame_type)
            # 尝试按应用层解析
            return self._parse_app_only(frame_bytes)

        # 有 FC
        fc_table = self._parse_fc(frame_bytes, 0)
        table.extend(fc_table)

        if parse_level == "fc_only":
            return table

        if flen <= 16:
            return table

        # 获取定界符类型
        dt = frame_bytes[0] & 0x07

        if dt == 2:  # SACK帧无载荷
            return table

        # 解析物理块 + MAC
        payload = frame_bytes[16:]

        if parse_level == "fc_mac":
            # FC + PBH + MAC头
            pb_table = self._parse_pb_and_mac_header(payload, 16, dt)
            table.extend(pb_table)
            return table

        # auto / fc_pb: 完整解析
        pb_table = self._parse_pb_block(payload, 16, dt)
        table.extend(pb_table)
        return table

    # ─── 检测函数 ──────────────────────────────────────────────

    def _detect_fc(self, data: bytes) -> bool:
        """检测是否为完整MPDU帧（含16字节FC头）"""
        if len(data) < 16:
            return False
        dt = data[0] & 0x07
        if dt > 3:
            return False
        net_type = (data[0] >> 3) & 0x1F
        # 标准版本号应为0（HDC 1.0）
        std_ver = (data[12] >> 4) & 0x0F
        if std_ver != 0:
            return False
        # FCCS校验
        fc_body = data[:13]
        fccs = int.from_bytes(data[13:16], 'little')
        calc = _crc24(fc_body)
        return calc == fccs

    def _detect_mac_header(self, data: bytes) -> bool:
        """检测是否为MAC帧起始"""
        if len(data) < 4:
            return False
        ver = data[0] & 0x0F
        if ver not in (0, 1):
            return False
        if ver == 0:  # 标准帧
            return len(data) >= 16
        return True  # 单跳帧4字节即有效

    # ─── FC 解析 ──────────────────────────────────────────────

    def _parse_fc(self, data: bytes, offset: int) -> List[Tuple]:
        """解析 16 字节 FC 帧控制"""
        if len(data) - offset < 16:
            return [("❌ FC解析失败", "", "", "长度不足16字节", offset, offset + len(data) - 1)]

        table = []
        base = offset
        b0 = data[offset]

        # 定界符类型
        dt = b0 & 0x07
        table.append((
            "定界符类型(DT)",
            f"0b{dt:03b}",
            str(dt),
            DELIMITER_TYPES.get(dt, f"保留({dt})"),
            base, base,
        ))

        # 网络类型
        net_type = (b0 >> 3) & 0x1F
        table.append((
            "网络类型",
            f"0x{net_type:02X}",
            str(net_type),
            NETWORK_TYPES.get(net_type, f"保留({net_type})"),
            base, base,
        ))

        # 网络标识 NID (24bit, 小端: byte1=低8bit, byte2=中8bit, byte3=高8bit)
        nid = int.from_bytes(data[offset + 1:offset + 4], 'little')
        table.append((
            "网络标识(NID)",
            ' '.join(f'{b:02X}' for b in data[offset + 1:offset + 4]),
            str(nid),
            f"网络标识: {nid}",
            base + 1, base + 3,
        ))

        # 可变区域
        vf_table = self._parse_fc_variable(data, offset, dt)
        table.extend(vf_table)

        # 标准版本号
        std_ver = (data[offset + 12] >> 4) & 0x0F
        self._std_version = std_ver  # 存储供信标载荷解析使用
        table.append((
            "标准版本号",
            f"0x{std_ver:01X}",
            str(std_ver),
            STANDARD_VERSIONS.get(std_ver, f"待演进({std_ver})"),
            base + 12, base + 12,
        ))

        # FCCS
        fccs = int.from_bytes(data[offset + 13:offset + 16], 'little')
        calc_fccs = _crc24(data[offset:offset + 13])
        status = "✓ 校验正确" if calc_fccs == fccs else f"✗ 校验错误(计算值=0x{calc_fccs:06X})"
        table.append((
            "帧控制校验序列(FCCS)",
            ' '.join(f'{b:02X}' for b in data[offset + 13:offset + 16]),
            f"0x{fccs:06X}",
            status,
            base + 13, base + 15,
        ))

        return table

    def _parse_fc_variable(self, data: bytes, offset: int, dt: int) -> List[Tuple]:
        """解析 FC 可变区域（字节4~11 + 字节12低4bit = 68bit）"""
        table = []
        base = offset + 4  # 可变区域起始

        if self._channel == "plc":
            if dt == 0:   # 信标帧
                table = self._parse_fc_vf_beacon_plc(data, offset)
            elif dt == 1:  # SOF帧
                table = self._parse_fc_vf_sof_plc(data, offset)
            elif dt == 2:  # SACK帧
                table = self._parse_fc_vf_sack_plc(data, offset)
            elif dt == 3:  # 网间协调帧
                table = [("  可变区域(网间协调)", "", "", "待实现", base, offset + 12)]
        else:  # hrf
            if dt == 0:
                table = self._parse_fc_vf_beacon_hrf(data, offset)
            elif dt == 1:
                table = self._parse_fc_vf_sof_hrf(data, offset)
            elif dt == 2:
                table = self._parse_fc_vf_sack_hrf(data, offset)
            elif dt == 3:
                table = [("  可变区域(无线网间协调)", "", "", "待实现", base, offset + 12)]

        return table

    def _parse_fc_vf_sof_plc(self, data: bytes, offset: int) -> List[Tuple]:
        """载波 SOF 帧可变区域（68bit = 字节4~11 + 字节12低4bit）"""
        table = []
        base = offset
        b4 = data[offset + 4]
        b5 = data[offset + 5]
        b6 = data[offset + 6]
        b7 = data[offset + 7]
        b8 = data[offset + 8]
        b9 = data[offset + 9]
        b10 = data[offset + 10]
        b11 = data[offset + 11]
        b12 = data[offset + 12]

        # 源TEI: byte4(高8bit) + byte5[0:3](低4bit) = 12bit
        src_tei = (b4 << 4) | (b5 & 0x0F)
        table.append((
            "  源TEI",
            f"0x{src_tei:03X}",
            str(src_tei),
            "源站点TEI",
            base + 4, base + 5,
        ))

        # 目的TEI: byte5[4:7](高4bit) + byte6(低8bit) = 12bit
        dst_tei = ((b5 >> 4) << 8) | b6
        table.append((
            "  目的TEI",
            f"0x{dst_tei:03X}",
            str(dst_tei),
            "目的站点TEI",
            base + 5, base + 6,
        ))

        # 链路标识符 LID
        table.append((
            "  链路标识符(LID)",
            f"0x{b7:02X}",
            str(b7),
            "优先级/业务分类(LID值越大优先级越高)",
            base + 7, base + 7,
        ))

        # 帧长: byte8(高8bit) + byte9[0:3](低4bit) = 12bit, 单位10us
        frame_len = (b8 << 4) | (b9 & 0x0F)
        table.append((
            "  帧长(FL)",
            f"0x{frame_len:03X}",
            f"{frame_len * 10}us",
            f"信道占用时长: {frame_len} × 10us = {frame_len * 10}us",
            base + 8, base + 9,
        ))

        # 物理块个数: byte9[4:7]
        pb_count = (b9 >> 4) & 0x0F
        table.append((
            "  物理块个数",
            f"0x{pb_count:01X}",
            str(pb_count),
            f"本帧包含 {pb_count} 个物理块",
            base + 9, base + 9,
        ))

        # 符号数: byte10(高8bit) + byte11[0](最低bit) = 9bit
        sym_count = (b10 << 1) | (b11 & 0x01)
        table.append((
            "  符号数",
            f"0x{sym_count:03X}",
            str(sym_count),
            f"OFDM符号数: {sym_count}",
            base + 10, base + 11,
        ))

        # 广播标志
        bc_flag = (b11 >> 1) & 0x01
        table.append((
            "  广播标志",
            f"0b{bc_flag}",
            str(bc_flag),
            "广播帧" if bc_flag else "非广播帧",
            base + 11, base + 11,
        ))

        # 重传标志
        rt_flag = (b11 >> 2) & 0x01
        table.append((
            "  重传标志",
            f"0b{rt_flag}",
            str(rt_flag),
            "重传帧" if rt_flag else "非重传帧",
            base + 11, base + 11,
        ))

        # 加密标志
        enc_flag = (b11 >> 3) & 0x01
        table.append((
            "  加密标志",
            f"0b{enc_flag}",
            str(enc_flag),
            "加密" if enc_flag else "未加密(预留)",
            base + 11, base + 11,
        ))

        # 分集拷贝基本模式
        div_mode = (b11 >> 4) & 0x0F
        table.append((
            "  分集拷贝基本模式",
            f"0x{div_mode:01X}",
            str(div_mode),
            PLC_DIVERSITY_MODES.get(div_mode, f"保留({div_mode})"),
            base + 11, base + 11,
        ))

        # 分集拷贝扩展模式
        ext_mode = b12 & 0x0F
        table.append((
            "  分集拷贝扩展模式",
            f"0x{ext_mode:01X}",
            str(ext_mode),
            "基本模式=15时有效" if div_mode == 15 else "无效(基本模式≠15)",
            base + 12, base + 12,
        ))

        return table

    def _parse_fc_vf_beacon_plc(self, data: bytes, offset: int) -> List[Tuple]:
        """载波信标帧可变区域"""
        table = []
        base = offset
        b8 = data[offset + 8]
        b9 = data[offset + 9]
        b10 = data[offset + 10]
        b11 = data[offset + 11]

        # 信标时间戳 (32bit, byte4~7)
        ts = int.from_bytes(data[offset + 4:offset + 8], 'little')
        table.append((
            "  信标时间戳",
            ' '.join(f'{b:02X}' for b in data[offset + 4:offset + 8]),
            str(ts),
            f"信标时间戳: {ts}",
            base + 4, base + 7,
        ))

        # 源TEI: byte8(高8bit) + byte9[0:3](低4bit)
        src_tei = (b8 << 4) | (b9 & 0x0F)
        table.append((
            "  源TEI",
            f"0x{src_tei:03X}",
            str(src_tei),
            "信标源站点TEI",
            base + 8, base + 9,
        ))

        # 分集拷贝基本模式: byte9[4:7]
        div_mode = (b9 >> 4) & 0x0F
        table.append((
            "  分集拷贝基本模式",
            f"0x{div_mode:01X}",
            str(div_mode),
            PLC_DIVERSITY_MODES.get(div_mode, f"保留({div_mode})"),
            base + 9, base + 9,
        ))

        # 符号数: byte10(高8bit) + byte11[0] = 9bit
        sym_count = (b10 << 1) | (b11 & 0x01)
        table.append((
            "  符号数",
            f"0x{sym_count:03X}",
            str(sym_count),
            f"OFDM符号数: {sym_count}",
            base + 10, base + 11,
        ))

        # 相线: byte11[1:2]
        phase = (b11 >> 1) & 0x03
        table.append((
            "  相线",
            f"0x{phase:01X}",
            str(phase),
            PHASE_TYPES.get(phase, f"保留({phase})"),
            base + 11, base + 11,
        ))

        return table

    def _parse_fc_vf_beacon_hrf(self, data: bytes, offset: int) -> List[Tuple]:
        """无线信标帧可变区域（表27）"""
        table = []
        base = offset
        b8 = data[offset + 8]
        b9 = data[offset + 9]
        b10 = data[offset + 10]

        # 信标时间戳 (32bit, byte4~7)
        ts = int.from_bytes(data[offset + 4:offset + 8], 'little')
        table.append((
            "  信标时间戳",
            ' '.join(f'{b:02X}' for b in data[offset + 4:offset + 8]),
            str(ts),
            f"信标时间戳: {ts}",
            base + 4, base + 7,
        ))

        # 源TEI: byte8(高8bit) + byte9[0:3](低4bit) = 12bit
        src_tei = (b8 << 4) | (b9 & 0x0F)
        table.append((
            "  源TEI",
            f"0x{src_tei:03X}",
            str(src_tei),
            "信标源站点TEI",
            base + 8, base + 9,
        ))

        # MCS: byte9[4:7]
        mcs = (b9 >> 4) & 0x0F
        table.append((
            "  MCS",
            f"0x{mcs:01X}",
            str(mcs),
            HRF_MCS.get(mcs, f"保留({mcs})"),
            base + 9, base + 9,
        ))

        # 载荷PB大小: byte10[0:3]
        pb_size_code = b10 & 0x0F
        pb_size_info = HRF_PB_SIZES.get(pb_size_code, (0, "保留"))
        table.append((
            "  载荷PB大小",
            f"0x{pb_size_code:01X}",
            str(pb_size_code),
            pb_size_info[1],
            base + 10, base + 10,
        ))

        return table

    def _parse_fc_vf_sack_plc(self, data: bytes, offset: int) -> List[Tuple]:
        """载波SACK帧可变区域"""
        table = []
        base = offset
        b4 = data[offset + 4]
        b5 = data[offset + 5]
        b6 = data[offset + 6]
        b7 = data[offset + 7]
        b8 = data[offset + 8]
        b9 = data[offset + 9]
        b10 = data[offset + 10]

        # 接收结果: byte4[0:3]
        rx_result = b4 & 0x0F
        table.append((
            "  接收结果",
            f"0x{rx_result:01X}",
            str(rx_result),
            SACK_RESULTS.get(rx_result, f"保留({rx_result})"),
            base + 4, base + 4,
        ))

        # 接收状态: byte4[4:7] (4bit位图)
        rx_status = (b4 >> 4) & 0x0F
        bits = [str((rx_status >> i) & 1) for i in range(4)]
        table.append((
            "  接收状态",
            f"0b{rx_status:04b}",
            f"PB3={bits[3]} PB2={bits[2]} PB1={bits[1]} PB0={bits[0]}",
            "bit=1表示对应物理块校验成功",
            base + 4, base + 4,
        ))

        # 源TEI: byte5(高8bit) + byte6[0:3](低4bit)
        src_tei = (b5 << 4) | (b6 & 0x0F)
        table.append((
            "  源TEI",
            f"0x{src_tei:03X}",
            str(src_tei),
            "发送SACK的站点TEI",
            base + 5, base + 6,
        ))

        # 目的TEI: byte6[4:7](高4bit) + byte7(低8bit)
        dst_tei = ((b6 >> 4) << 8) | b7
        table.append((
            "  目的TEI",
            f"0x{dst_tei:03X}",
            str(dst_tei),
            "SACK目的站点TEI",
            base + 6, base + 7,
        ))

        # 接收物理块个数: byte8[0:2]
        rx_pb_count = b8 & 0x07
        table.append((
            "  接收物理块个数",
            f"0x{rx_pb_count:01X}",
            str(rx_pb_count),
            f"已接收物理块数: {rx_pb_count}",
            base + 8, base + 8,
        ))

        # 信道质量: byte9
        table.append((
            "  信道质量",
            f"0x{b9:02X}",
            str(b9),
            f"信道质量指示: {b9}",
            base + 9, base + 9,
        ))

        # 站点负载: byte10
        table.append((
            "  站点负载",
            f"0x{b10:02X}",
            str(b10),
            f"站点负载: {b10}",
            base + 10, base + 10,
        ))

        return table

    def _parse_fc_vf_sof_hrf(self, data: bytes, offset: int) -> List[Tuple]:
        """无线 SOF 帧可变区域"""
        table = []
        base = offset
        b4 = data[offset + 4]
        b5 = data[offset + 5]
        b6 = data[offset + 6]
        b7 = data[offset + 7]
        b8 = data[offset + 8]
        b9 = data[offset + 9]
        b11 = data[offset + 11]

        # 源TEI
        src_tei = (b4 << 4) | (b5 & 0x0F)
        table.append(("  源TEI", f"0x{src_tei:03X}", str(src_tei), "源站点TEI", base + 4, base + 5))

        # 目的TEI
        dst_tei = ((b5 >> 4) << 8) | b6
        table.append(("  目的TEI", f"0x{dst_tei:03X}", str(dst_tei), "目的站点TEI", base + 5, base + 6))

        # 链路标识符
        table.append(("  链路标识符(LID)", f"0x{b7:02X}", str(b7), "优先级/业务分类", base + 7, base + 7))

        # 帧长(单位100us)
        frame_len = (b8 << 4) | (b9 & 0x0F)
        table.append(("  帧长(FL)", f"0x{frame_len:03X}", f"{frame_len * 100}us",
                      f"信道占用时长: {frame_len} × 100us = {frame_len * 100}us",
                      base + 8, base + 9))

        # 载荷PB大小
        pb_size_code = (b9 >> 4) & 0x0F
        pb_sizes = {0: "16B", 1: "40B", 2: "72B", 3: "136B", 4: "264B", 5: "520B"}
        table.append(("  载荷PB大小", f"0x{pb_size_code:01X}", str(pb_size_code),
                      pb_sizes.get(pb_size_code, f"保留({pb_size_code})"),
                      base + 9, base + 9))

        # 广播/重传/加密标志
        bc_flag = (b11 >> 1) & 0x01
        rt_flag = (b11 >> 2) & 0x01
        enc_flag = (b11 >> 3) & 0x01
        table.append(("  广播标志", f"0b{bc_flag}", str(bc_flag), "广播帧" if bc_flag else "非广播帧", base + 11, base + 11))
        table.append(("  重传标志", f"0b{rt_flag}", str(rt_flag), "重传帧" if rt_flag else "非重传帧", base + 11, base + 11))
        table.append(("  加密标志", f"0b{enc_flag}", str(enc_flag), "加密" if enc_flag else "未加密(预留)", base + 11, base + 11))

        # MCS
        mcs = (b11 >> 4) & 0x0F
        table.append(("  MCS", f"0x{mcs:01X}", str(mcs), f"调制编码方案: {mcs}", base + 11, base + 11))

        return table

    def _parse_fc_vf_sack_hrf(self, data: bytes, offset: int) -> List[Tuple]:
        """无线SACK帧可变区域"""
        table = []
        base = offset
        b4 = data[offset + 4]
        b5 = data[offset + 5]
        b6 = data[offset + 6]
        b7 = data[offset + 7]
        b9 = data[offset + 9]
        b10 = data[offset + 10]

        # 接收结果
        rx_result = b4 & 0x0F
        table.append(("  接收结果", f"0x{rx_result:01X}", str(rx_result),
                      SACK_RESULTS.get(rx_result, f"保留({rx_result})"),
                      base + 4, base + 4))

        # 源TEI / 目的TEI
        src_tei = (b5 << 4) | (b6 & 0x0F)
        dst_tei = ((b6 >> 4) << 8) | b7
        table.append(("  源TEI", f"0x{src_tei:03X}", str(src_tei), "发送SACK的站点TEI", base + 5, base + 6))
        table.append(("  目的TEI", f"0x{dst_tei:03X}", str(dst_tei), "SACK目的站点TEI", base + 6, base + 7))

        # 信道质量 / 站点负载
        table.append(("  信道质量", f"0x{b9:02X}", str(b9), f"信道质量指示: {b9}", base + 9, base + 9))
        table.append(("  站点负载", f"0x{b10:02X}", str(b10), f"站点负载: {b10}", base + 10, base + 10))

        return table

    # ─── 物理块解析 ────────────────────────────────────────────

    def _parse_pb_block(self, data: bytes, base_offset: int, dt: int) -> List[Tuple]:
        """解析物理块（单PB或多PB聚合，重组MAC帧）"""
        table = []
        if not data:
            return table

        if dt == 0:  # 信标帧：信标载荷 + BPCS + PBCS
            return self._parse_beacon_payload(data, base_offset)

        # SOF帧：PBH(1B) + PB体 + PBCS(3B)
        # 尝试解析第一个PB，判断是否多PB
        # 注意：如果是单PB且MAC帧完整包含在内，直接解析
        # 如果是多PB，需重组

        # 先试探：第一个PB的PBH
        pbh = data[0]
        seq = pbh & 0x3F
        sof = (pbh >> 6) & 0x01  # 帧起始
        eof = (pbh >> 7) & 0x01  # 帧结束

        if sof and eof:
            # 单PB完整MAC帧
            table.append((
                "物理块(PB)",
                f"序列号:{seq}, 起始:{sof}, 结束:{eof}",
                f"{len(data)}字节",
                "单PB承载完整MAC帧",
                base_offset, base_offset + len(data) - 1,
            ))
            table.append((
                "  PB头(PBH)",
                f"0x{pbh:02X}",
                f"seq={seq}",
                f"序列号:{seq}, 帧起始:{sof}, 帧结束:{eof}",
                base_offset, base_offset,
            ))
            # PB体 = MAC帧 = MAC头 + MSDU + ICV
            # PBCS在末尾3字节
            if len(data) > 4:
                pb_body = data[1:-3]
                pbcs = int.from_bytes(data[-3:], 'little')
                calc_pbcs = _crc24(data[:-3])
                status = "✓ 校验正确" if calc_pbcs == pbcs else f"✗ 校验错误(计算=0x{calc_pbcs:06X})"
                mac_table = self._parse_mac_frame(pb_body, base_offset + 1)
                table.extend(mac_table)
                table.append((
                    "  PBCS",
                    ' '.join(f'{b:02X}' for b in data[-3:]),
                    f"0x{pbcs:06X}",
                    status,
                    base_offset + len(data) - 3, base_offset + len(data) - 1,
                ))
        elif sof and not eof:
            # 多PB聚合的首块 - 需要重组
            # 简化处理：递归解析所有PB，拼接PB体后解析MAC
            # 先扫描所有PB边界
            pb_list = self._scan_all_pb(data)
            if len(pb_list) > 1:
                table.append((
                    f"── 物理块聚合(共{len(pb_list)}个PB) ──",
                    "",
                    f"{len(data)}字节",
                    "多PB承载分片MAC帧",
                    base_offset, base_offset + len(data) - 1,
                ))
                # 拼接所有PB体
                concat_body = b''
                for i, (pb_start, pb_end) in enumerate(pb_list):
                    pb_data = data[pb_start:pb_end]
                    pbh_i = pb_data[0]
                    seq_i = pbh_i & 0x3F
                    sof_i = (pbh_i >> 6) & 0x01
                    eof_i = (pbh_i >> 7) & 0x01
                    body_i = pb_data[1:-3]
                    concat_body += body_i
                    table.append((
                        f"  PB[{i}]",
                        f"0x{pbh_i:02X}",
                        f"seq={seq_i}",
                        f"起始:{sof_i} 结束:{eof_i} 体长度:{len(body_i)}B",
                        base_offset + pb_start, base_offset + pb_end - 1,
                    ))
                # 解析重组后的完整MAC帧
                if concat_body:
                    mac_offset = base_offset + 1  # 首PB体起始偏移（近似）
                    table.append((
                        "  重组MAC帧",
                        f"{len(concat_body)}字节",
                        "",
                        "多PB分片重组后完整MAC帧",
                        base_offset + 1, base_offset + 1 + len(concat_body) - 1,
                    ))
                    mac_table = self._parse_mac_frame(concat_body, base_offset + 1)
                    table.extend(mac_table)
            else:
                # 只有一个起始PB（数据不全）
                table.append((
                    "物理块(PB) - 不完整",
                    f"序列号:{seq}",
                    f"{len(data)}字节",
                    "只有帧起始标志，无结束标志，数据可能不完整",
                    base_offset, base_offset + len(data) - 1,
                ))
                if len(data) > 4:
                    pb_body = data[1:-3]
                    mac_table = self._parse_mac_frame(pb_body, base_offset + 1)
                    table.extend(mac_table)
        else:
            # 不是SOF帧起始（中间PB或末尾PB），直接显示hex
            table.append((
                "物理块数据(部分)",
                ' '.join(f'{b:02X}' for b in data[:20]) + ("..." if len(data) > 20 else ""),
                f"{len(data)}字节",
                "非帧起始PB，原始数据",
                base_offset, base_offset + min(len(data), 20) - 1,
            ))

        return table

    def _scan_all_pb(self, data: bytes) -> List[Tuple[int, int]]:
        """扫描所有PB边界，返回 [(start, end), ...]"""
        # 假设所有PB大小相同，从第一个PB推断
        # 简化实现：尝试用 PBH 帧结束标志来寻找边界
        result = []
        pos = 0
        while pos + 4 <= len(data):
            pbh = data[pos]
            eof = (pbh >> 7) & 0x01
            # 试探下一个PB起始位置
            # 常见PB大小: 72, 136, 264, 520
            next_pos = None
            for pb_size in (72, 136, 264, 520, 16, 40):
                cand = pos + pb_size
                if cand <= len(data):
                    # 检查下一个PBH是否合理
                    next_pbh = data[cand]
                    next_seq = next_pbh & 0x3F
                    if next_seq == (pbh & 0x3F) + 1 or next_seq == 0:
                        next_pos = cand
                        break
            if eof or next_pos is None:
                # 当前PB到末尾（或最后一个PB）
                result.append((pos, len(data)))
                break
            result.append((pos, next_pos))
            pos = next_pos
        return result

    def _parse_beacon_payload(self, data: bytes, base_offset: int) -> List[Tuple]:
        """解析信标帧载荷

        结构(表22/表38): 信标固定头(20B) + 信标管理信息(变长) +
                         BPCS(4B, CRC-32) + PBCS(3B, CRC-24)
        信标帧无物理块头(PBH): data[0] 即信标类型字节(表22字段从字节0开始)
        依据: HDC 1.0 5.1.2.4 "PBCS校验以帧载荷和BPCS两部分为目标"(不含PBH);
              表22字段从字节0即信标类型, 无PBH位置
        校验: BPCS = CRC-32(载荷内容, 从帧第17字节即FC后起, 不含自身)
              PBCS = CRC-24(载荷内容+BPCS, 从帧第17字节起, 不含自身, poly 0x1800063)
        """
        table = []
        if len(data) < 5:  # 至少 1B 信标头 + 4B BPCS
            table.append(("信标载荷(过短)", "", "", "长度不足", base_offset, base_offset + len(data) - 1))
            return table

        std_version = self._std_version  # 0=HDC 1.0, 1=HDC 2.0

        # 信标帧无 PBH, data[0] 即信标类型字节
        table.append(("信标帧(无PBH)", "", f"HDC {'1.0' if std_version == 0 else '2.0'}",
                       "信标帧无物理块头, data[0]即信标类型(表22字节0)",
                       base_offset, base_offset, False))

        beacon = data
        b_offset = base_offset

        if len(beacon) < 4:  # 至少 1B 信标头 + 3B (无 BPCS)
            table.append(("信标载荷(过短)", "", "", "信标内容不足", b_offset, b_offset + len(beacon) - 1))
            return table

        b0 = beacon[0]
        # 信标类型: bit0-2
        bc_type = b0 & 0x07
        bc_types = {0: "发现信标", 1: "代理信标", 2: "中央信标"}
        # 组网标志: bit3
        net_flag = (b0 >> 3) & 0x01
        # 精简信标标志: bit4
        slim_flag = (b0 >> 4) & 0x01
        # 开始关联标志: bit6
        assoc_flag = (b0 >> 6) & 0x01
        # 信标使用标志: bit7
        use_flag = (b0 >> 7) & 0x01

        table.append((
            "信标帧载荷",
            f"0x{b0:02X}",
            f"类型{bc_type}",
            bc_types.get(bc_type, f"保留({bc_type})"),
            b_offset, b_offset + len(beacon) - 1, False,
        ))
        table.append((
            "  信标类型",
            f"0x{bc_type:01X}",
            str(bc_type),
            bc_types.get(bc_type, f"保留({bc_type})"),
            b_offset, b_offset, True,
        ))
        table.append((
            "  组网标志位",
            f"0b{net_flag}",
            str(net_flag),
            "已组网" if net_flag else "未组网",
            b_offset, b_offset, True,
        ))
        table.append((
            "  精简信标标志",
            f"0b{slim_flag}",
            str(slim_flag),
            "精简信标" if slim_flag else "完整信标",
            b_offset, b_offset, True,
        ))
        table.append((
            "  开始关联标志",
            f"0b{assoc_flag}",
            str(assoc_flag),
            "允许关联" if assoc_flag else "禁止关联",
            b_offset, b_offset, True,
        ))
        table.append((
            "  信标使用标志",
            f"0b{use_flag}",
            str(use_flag),
            "信标已使用" if use_flag else "信标未使用",
            b_offset, b_offset, True,
        ))

        # 组网序列号(字节1)
        if len(beacon) >= 2:
            table.append((
                "  组网序列号",
                f"0x{beacon[1]:02X}",
                str(beacon[1]),
                f"CCO重新组网后+1",
                b_offset + 1, b_offset + 1, True,
            ))

        # CCO MAC地址(字节2~7)
        if len(beacon) >= 8:
            mac = ':'.join(f'{b:02X}' for b in beacon[2:8])
            table.append((
                "  CCO MAC地址",
                ' '.join(f'{b:02X}' for b in beacon[2:8]),
                mac,
                "本网络CCO的MAC地址",
                b_offset + 2, b_offset + 7, True,
            ))

        # 信标周期计数(字节8~11, 小端)
        if len(beacon) >= 12:
            cnt = int.from_bytes(beacon[8:12], 'little')
            table.append((
                "  信标周期计数",
                ' '.join(f'{b:02X}' for b in beacon[8:12]),
                f"0x{cnt:08X} ({cnt})",
                "CCO维护的信标周期递增计数(小端)",
                b_offset + 8, b_offset + 11, True,
            ))

        # 本网络无线信道编号(字节12)
        if len(beacon) >= 13:
            table.append((
                "  本网络无线信道编号",
                f"0x{beacon[12]:02X}",
                str(beacon[12]),
                "网络无线信道号",
                b_offset + 12, b_offset + 12, True,
            ))

        # ── 字节13及之后: 版本相关的保留/扩展字段 ──
        if len(beacon) >= 14 and not slim_flag:
            b13 = beacon[13]
            if std_version == 1:
                # HDC 2.0: 字节13 bit0-1=option模式 bit2=信标机制 bit3=发现信标使能 bit4-7=保留
                opt_mode = b13 & 0x03
                bc_mech = (b13 >> 2) & 0x01
                disc_en = (b13 >> 3) & 0x01
                table.append(("  无线option模式", f"bit0-1={opt_mode:02b}",
                              str(opt_mode), "0=option1 1=option2 2=option3 3=option4",
                              b_offset + 13, b_offset + 14, True))
                table.append(("  信标机制状态", f"bit2={bc_mech}",
                              str(bc_mech), "竞争信标机制" if bc_mech else "固定信标机制",
                              b_offset + 13, b_offset + 14, True))
                table.append(("  发现信标发送使能", f"bit3={disc_en}",
                              str(disc_en), "使能" if disc_en else "未使能",
                              b_offset + 13, b_offset + 14, True))
            else:
                # HDC 1.0: 字节13字段未明确定义，作为保留显示
                table.append(("  字节13", f"0x{b13:02X}",
                              f"0x{b13:02X}", "保留(HDC 1.0)",
                              b_offset + 13, b_offset + 14, True))

            # 字节14起: 保留区域(字节14-19, 共6字节, 表22/表38)
            rsv_start = 14
            rsv_end = min(len(beacon), 20)

            if rsv_end > rsv_start:
                rsv_bytes = beacon[rsv_start:rsv_end]
                table.append(("  保留",
                              " ".join(f"{x:02X}" for x in rsv_bytes),
                              f"{len(rsv_bytes)}字节",
                              "保留字段(字节14-19)",
                              b_offset + rsv_start, b_offset + rsv_end, True))

        # ── 信标管理信息 (TLV 条目数组) ──
        # 标准信标: HDC 1.0/2.0 均从字节20开始(表22/表38: 字节0-19为固定头)
        # 精简信标: 从字节12开始
        if slim_flag:
            mgmt_start = 12
        else:
            mgmt_start = 20

        # 信标帧尾部: BPCS(4B, CRC-32) + PBCS(3B, CRC-24)
        content_end = max(0, len(beacon) - 7) if len(beacon) >= 7 else len(beacon)

        if mgmt_start < content_end:
            mgmt_table = self._parse_beacon_management_info(
                beacon, mgmt_start, content_end, b_offset,
                discovery=(bc_type == 0))
            table.extend(mgmt_table)

        # ── BPCS (信标帧载荷CRC-32, 4字节) ──
        if len(beacon) >= 7:
            # BPCS = 倒数第7~4字节; 校验范围 = 载荷内容(不含BPCS自身, 从FC后第17字节起)
            bpcs = int.from_bytes(beacon[-7:-3], 'little')
            bpcs_off = b_offset + len(beacon) - 7
            calc_bpcs = _crc32(beacon[:-7])
            bpcs_status = "✓ 校验正确" if calc_bpcs == bpcs else f"✗ 校验错误(计算=0x{calc_bpcs:08X})"

            table.append((
                "  帧载荷校验序列(BPCS)",
                ' '.join(f'{b:02X}' for b in beacon[-7:-3]),
                f"0x{bpcs:08X}",
                bpcs_status,
                bpcs_off, bpcs_off + 3, True,
            ))

            # ── PBCS (物理块校验CRC-24, 3字节) ──
            # 校验范围 = 载荷内容 + BPCS(不含PBCS自身)
            pbcs = int.from_bytes(beacon[-3:], 'little')
            pbcs_off = b_offset + len(beacon) - 3
            calc_pbcs = _crc24(beacon[:-3])
            pbcs_status = "✓ 校验正确" if calc_pbcs == pbcs else f"✗ 校验错误(计算=0x{calc_pbcs:06X})"

            table.append((
                "  物理块校验序列(PBCS)",
                ' '.join(f'{b:02X}' for b in beacon[-3:]),
                f"0x{pbcs:06X}",
                pbcs_status,
                pbcs_off, pbcs_off + 2, True,
            ))

        return table

    def _parse_beacon_management_info(self, data: bytes, start: int, end: int,
                                      base_offset: int,
                                      discovery: bool = False) -> List[Tuple]:
        """解析信标管理信息 (条目数组)

        结构: 条目数(1B) + [条目头(1B) + 条目长度(1B或2B) + 条目内容] * N
        条目长度 = 总长度(含头和长度字段)，即内容长度 = 总长度 - 2
        条目头 >= 0xC0 且 HDC 2.0 时长度为2字节
        """
        result = []
        avail = end - start
        if avail < 1:
            return result

        num = data[start]
        idx = start + 1
        result.append(("  信标管理信息", "", f"{num}个条目",
                        "信标条目数组",
                        base_offset + start, base_offset + end, False))
        result.append(("    信标条目数", f"0x{num:02X}", str(num),
                        "Beacon条目总数",
                        base_offset + start, base_offset + start + 1, True))

        for i in range(num):
            if idx + 1 >= end:
                break
            hdr = data[idx]
            idx += 1

            # 判断长度字段大小(表46):
            # 0xC0/0xC1/0xC2/0xF0: 长度字段2字节(HDC 1.0 和 HDC 2.0 通用)
            # 其他: 长度字段1字节
            if hdr in (0xC0, 0xC1, 0xC2, 0xF0):
                # 2字节长度字段: 头1B + 长度字段2B = 3B开销, 内容 = total_len - 3
                if idx + 1 >= end:
                    break
                total_len = data[idx] | (data[idx + 1] << 8)
                idx += 2
                content_len = total_len - 3
            else:
                # 1字节长度字段: 头1B + 长度字段1B = 2B开销, 内容 = total_len - 2
                if idx >= end:
                    break
                total_len = data[idx]
                idx += 1
                content_len = total_len - 2
            # 容错: 声明长度超出剩余数据时截断并标记
            if content_len < 0:
                content_len = 0
            content_start = idx
            content_end = min(idx + content_len, end)
            # 时隙分配条目(0xC0/F0): 实机声明 total_len 常偏小(不含非中央信标信息数组),
            # 且无独立尾部锚点 → 内容直接延伸到管理区可用边界(end = BPCS 前)
            if hdr in (0xC0, 0xF0) and content_end < end:
                content_len = end - content_start
                content_end = end
            content = data[content_start:content_end]
            truncated = False

            entry_name = self.BEACON_ENTRY_NAMES.get(hdr, f"保留(0x{hdr:02X})")
            warn = " ⚠声明长度超出数据(已截断)" if truncated else ""
            result.append((f"    条目{i+1}: {entry_name}",
                            f"头=0x{hdr:02X} 长={total_len}B",
                            f"内容{len(content)}B",
                            f"条目类型0x{hdr:02X}{warn}",
                            base_offset + content_start - 2, base_offset + content_end, False))

            # 解析已知条目内容
            entry_rows = self._parse_beacon_entry_content(hdr, content, content_start,
                                                           base_offset, discovery)
            result.extend(entry_rows)

            idx = content_end

        # 声明条目数解析完后, 剩余数据(超出声明的条目, 可能为设备扩展条目)
        if idx < end:
            remain = data[idx:end]
            result.append(("    未解析剩余数据",
                           ' '.join(f'{x:02X}' for x in remain[:16]) + ('...' if len(remain) > 16 else ''),
                           f"{len(remain)}字节",
                           "超出信标条目数声明的剩余数据(可能为设备扩展条目)",
                           base_offset + idx, base_offset + end, True))

        return result

    def _parse_beacon_entry_content(self, hdr: int, content: bytes,
                                    pos: int, base_offset: int,
                                    discovery: bool = False) -> List[Tuple]:
        """解析单个信标条目的内容

        discovery: 发现信标(表50: 发现信标省略非中央信标信息字段)
        """
        result = []
        ln = len(content)
        bo = base_offset + pos  # 条目内容在帧中的绝对偏移

        if hdr == 0x00 and ln >= 13:
            # 站点能力条目: TEI(12b) + 代理站点TEI(12b) + 路径最低成功率(8b) +
            #   发送信标站点MAC(6B) + 角色(4b) + 层级数(8b) + 代理信道质量(8b) + 相线(2b) + RF跳数(6b)
            tei = content[0] | ((content[1] & 0x0F) << 8)
            proxy_tei = ((content[1] >> 4) | (content[2] << 4)) & 0xFFF
            result.append(("      TEI", f"0x{tei:03X}", str(tei),
                           "站点TEI(12bit)", bo, bo + 2, True))
            result.append(("      代理站点TEI", f"0x{proxy_tei:03X}", str(proxy_tei),
                           "发送信标站点的代理TEI(12bit)", bo + 1, bo + 3, True))
            if ln >= 4:
                result.append(("      路径最低通信成功率", f"0x{content[3]:02X}", str(content[3]),
                               "站点到CCO路径最低成功率", bo + 3, bo + 4, True))
            if ln >= 10:
                mac = ':'.join(f'{b:02X}' for b in content[4:10])
                result.append(("      发送信标站点MAC地址",
                               ' '.join(f'{b:02X}' for b in content[4:10]),
                               mac, "信标发送站点MAC", bo + 4, bo + 10, True))
            if ln >= 11:
                role = content[10] & 0x0F
                role_names = {0: "CCO", 1: "Proxy", 2: "STA"}
                result.append(("      角色", f"0x{role}", str(role),
                               role_names.get(role, f"保留({role})"), bo + 10, bo + 11, True))
            if ln >= 12:
                result.append(("      层级数", str(content[11]), str(content[11]),
                               "站点到CCO路径层级数", bo + 11, bo + 12, True))
            if ln >= 13:
                result.append(("      代理站点信道质量", f"0x{content[12]:02X}", str(content[12]),
                               "与代理站点信道质量", bo + 12, bo + 13, True))
            # 字节13: 相线(2b) + RF跳数(6b)
            if ln >= 14:
                b13 = content[13]
                phase = b13 & 0x03
                phase_names = {0: "A相线", 1: "B相线", 2: "C相线", 3: "未确定"}
                rf_hops = (b13 >> 2) & 0x3F
                result.append(("      相线", str(phase), phase_names.get(phase, f"保留({phase})"),
                               "站点所属相线", bo + 13, bo + 14, True))
                result.append(("      链路上RF跳数", str(rf_hops), str(rf_hops),
                               "站点到CCO路径RF跳数", bo + 13, bo + 14, True))
        elif hdr == 0x01 and ln >= 8:
            # 路由参数条目: 路由周期(16b LE) + 路由评估剩余时间(16b LE) +
            #   代理站点发现列表周期(16b LE) + 发现站点发现列表周期(16b LE)
            route_period = int.from_bytes(content[0:2], 'little')
            route_remain = int.from_bytes(content[2:4], 'little')
            proxy_disc = int.from_bytes(content[4:6], 'little')
            disc_disc = int.from_bytes(content[6:8], 'little')
            result.append(("      路由周期", f"0x{route_period:04X}", f"{route_period}秒",
                           "路由评估时间周期(小端)", bo, bo + 2, True))
            result.append(("      路由评估剩余时间", f"0x{route_remain:04X}", f"{route_remain}秒",
                           "距离下次路由评估剩余时间(小端)", bo + 2, bo + 4, True))
            result.append(("      代理站点发现列表周期", f"0x{proxy_disc:04X}", f"{proxy_disc}秒",
                           "代理站点发送发现列表间隔(小端)", bo + 4, bo + 6, True))
            result.append(("      发现站点发现列表周期", f"0x{disc_disc:04X}", f"{disc_disc}秒",
                           "发现站点发送发现列表间隔(小端)", bo + 6, bo + 8, True))
        elif hdr == 0x03 and ln >= 2:
            # 无线路由参数条目: 无线发现列表周期(8b) + 无线接收率老化周期个数(8b)
            result.append(("      无线发现列表周期", f"0x{content[0]:02X}", f"{content[0]}秒",
                           "无线发现列表周期长度", bo, bo + 1, True))
            if ln >= 2:
                result.append(("      无线接收率老化周期个数", f"0x{content[1]:02X}", str(content[1]),
                               "无线接收率老化周期个数", bo + 1, bo + 2, True))
        elif hdr in (0xC0, 0xF0) and ln >= 10:
            # 时隙分配条目(表50): 0xC0(HDC 2.0) / 0xF0(HDC 1.0)
            # 字段对照表50及官方工具:
            #   byte0: 非中央信标时隙总数(8b)
            #   byte1: 中央信标时隙总数(4b) + CSHA相线(2b) + 保留(2b)
            #   byte2: 保留(8b)
            #   byte3: 代理信标时隙总数(8b)
            #   byte4: 信标时隙长度(8b, 单位1ms)
            #   byte5: CSHA长度(8b, 单位10ms)
            #   byte6: BCSHA相线(8b)
            #   byte7: BCSHA业务号(8b)
            #   byte8: TDHA长度(8b, 单位1ms)
            #   byte9: TDHA业务号(8b)
            #   byte10-13: 信标基准时间/NTB(32b 小端)
            #   byte14-17: 信标周期长度(32b, 单位1ms)
            #   byte18-19: RF信标时隙长度(10b) + 保留(6b)
            #   byte20+: 非中央信标信息(变长) + CSHA时隙信息(变长) + BCSHA时隙信息(变长)
            non_ccn_beacon = content[0]
            cco_beacon = content[1] & 0x0F
            csha_phases = (content[1] >> 4) & 0x03
            result.append(("      非中央信标时隙总数", f"0x{non_ccn_beacon:02X}",
                           str(non_ccn_beacon), "代理+发现信标时隙总数", bo, bo + 1, True))
            result.append(("      中央信标时隙总数", str(cco_beacon), str(cco_beacon),
                           "中央信标时隙总数", bo + 1, bo + 2, True))
            result.append(("      CSHA相线", str(csha_phases), str(csha_phases + 1) + "相",
                           "CSMA时隙支持相线个数(取值1~3)", bo + 1, bo + 2, True))
            if ln >= 3:
                result.append(("      保留", f"0x{content[2]:02X}", "1字节",
                               "保留字段(byte2)", bo + 2, bo + 3, True))
            if ln >= 4:
                proxy_beacon = content[3]
                result.append(("      代理信标时隙总数", f"0x{proxy_beacon:02X}", str(proxy_beacon),
                               "代理信标时隙总数", bo + 3, bo + 4, True))
            if ln >= 5:
                beacon_slot_len = content[4]
                result.append(("      信标时隙长度", f"0x{beacon_slot_len:02X}",
                               f"{beacon_slot_len}ms", "每个信标时隙长度(单位1ms)", bo + 4, bo + 5, True))
            if ln >= 6:
                csha_len = content[5]
                result.append(("      CSHA长度", f"0x{csha_len:02X}",
                               f"{csha_len * 10}ms", "CSMA时隙分片长度(单位10ms)", bo + 5, bo + 6, True))
            if ln >= 7:
                bcsha_phases = content[6]
                result.append(("      BCSHA相线", f"0x{bcsha_phases:02X}",
                               str(bcsha_phases), "绑定CSMA时隙相线个数", bo + 6, bo + 7, True))
            if ln >= 8:
                bcsha_lid = content[7]
                result.append(("      BCSHA业务号", f"0x{bcsha_lid:02X}",
                               str(bcsha_lid), "绑定CSMA业务报文LID", bo + 7, bo + 8, True))
            if ln >= 9:
                tdha_len = content[8]
                result.append(("      TDHA长度", f"0x{tdha_len:02X}",
                               f"{tdha_len}ms", "TDMA时隙长度(单位1ms)", bo + 8, bo + 9, True))
            if ln >= 10:
                tdha_lid = content[9]
                result.append(("      TDHA业务号", f"0x{tdha_lid:02X}",
                               str(tdha_lid), "TDMA业务报文LID", bo + 9, bo + 10, True))
            # 可选字段: 信标基准时间(NTB) + 信标周期长度 + RF信标时隙长度
            if ln >= 14:
                bp_start_ntb = int.from_bytes(content[10:14], 'little')
                result.append(("      信标基准时间",
                               ' '.join(f'{x:02X}' for x in content[10:14]),
                               str(bp_start_ntb),
                               "信标周期起始NTB(小端)", bo + 10, bo + 14, True))
            if ln >= 18:
                bp_length = int.from_bytes(content[14:18], 'little')
                result.append(("      信标周期长度",
                               ' '.join(f'{x:02X}' for x in content[14:18]),
                               str(bp_length),
                               f"信标周期时间长度={bp_length}ms(单位1ms)", bo + 14, bo + 18, True))
            if ln >= 20:
                rf_bcn_len = content[18] | ((content[19] & 0x03) << 8)
                result.append(("      RF信标时隙长度",
                               ' '.join(f'{x:02X}' for x in content[18:20]),
                               str(rf_bcn_len),
                               f"RF链路上信标时隙长度={rf_bcn_len}ms", bo + 18, bo + 20, True))
            # 可变部分: HDC 1.0 实机顺序与表50声明不同(实测帧验证):
            #   [CSMA时隙信息 × csha_phases (4B/条)] →
            #   [非中央信标信息 × 代理信标时隙总数 (2B/条)] →
            #   [绑定CSMA时隙信息 × bcsha_phases (4B/条)]
            # 注意: 非中央信标信息条数锚定"代理信标时隙总数"(byte3),
            #       非"非中央信标时隙总数"(byte0, =代理+发现总时隙数, 发现时隙不占描述条目)
            if ln > 20:
                var_data = content[20:]
                var_pos = 0
                parsed_any = False

                def _csma_slot_row(prefix, seg, abs_pos):
                    c_len = int.from_bytes(seg[0:3], 'little')
                    phase = seg[3] & 0x03
                    phase_names = {0: "全相线", 1: "A相线", 2: "B相线", 3: "C相线"}
                    return (prefix, ' '.join(f'{x:02X}' for x in seg),
                            f"长度={c_len}ms 相线={phase_names.get(phase, phase)}",
                            "时隙长度(24b)+相线(2b)", abs_pos, abs_pos + 4, True)

                # 1) CSMA时隙信息(表52): 每条4B = 时隙长度(24b LE) + 相线(2b) + 保留(6b)
                for i in range(csha_phases):
                    if var_pos + 4 > len(var_data):
                        break
                    result.append(_csma_slot_row(
                        "      CSMA时隙信息", var_data[var_pos:var_pos + 4],
                        bo + 20 + var_pos))
                    var_pos += 4
                    parsed_any = True

                # 2) 非中央信标信息(表51): 每条2B = TEI(12b) + 信标类型(1b) + 无线信标标志(3b)
                #    条数不预设: 实机声明值与实际条目数常不一致, 按剩余数据逐2B解析到耗尽
                #    注: HDC 1.0 实测发现信标同样携带非中央信标信息, 不做表50的省略假设
                n_non_ccn = (len(var_data) - var_pos) // 2
                n_parsed = 0
                for i in range(n_non_ccn):
                    if var_pos + 2 > len(var_data):
                        break
                    b0, b1 = var_data[var_pos], var_data[var_pos + 1]
                    tei = b0 | ((b1 & 0x0F) << 8)
                    btype = (b1 >> 4) & 0x01
                    wflag = (b1 >> 5) & 0x07
                    btype_names = {0: "发现信标", 1: "代理信标"}
                    wflag_names = {0: "仅载波信标", 1: "仅无线标准信标", 2: "载波+无线标准信标",
                                   3: "载波+无线精简信标", 4: "载波+CSMA无线精简信标"}
                    result.append((f"      信标时隙{i + 1}", f"{b0:02X} {b1:02X}",
                                   f"TEI={tei} {btype_names.get(btype, btype)}",
                                   f"无线={wflag_names.get(wflag, f'保留({wflag})')}",
                                   bo + 20 + var_pos, bo + 20 + var_pos + 2, True))
                    var_pos += 2
                    parsed_any = True
                    n_parsed += 1
                if n_parsed < n_non_ccn and n_non_ccn > 0:
                    result.append(("      ⚠ 非中央信标信息不足",
                                   f"声明{n_non_ccn}条",
                                   f"数据仅够{n_parsed}条",
                                   "代理信标时隙总数与实际数据不符",
                                   bo + 20 + var_pos, bo + ln, True))

                # 3) 绑定CSMA时隙信息(表53): 每条4B, 结构同CSMA
                for i in range(bcsha_phases):
                    if var_pos + 4 > len(var_data):
                        break
                    result.append(_csma_slot_row(
                        "      绑定CSMA时隙", var_data[var_pos:var_pos + 4],
                        bo + 20 + var_pos))
                    var_pos += 4
                    parsed_any = True

                # 剩余未解析字节
                if var_pos < len(var_data):
                    remain = var_data[var_pos:]
                    result.append(("      未解析剩余",
                                   ' '.join(f'{x:02X}' for x in remain) + ('...' if len(remain) > 12 else ''),
                                   f"{len(remain)}字节",
                                   "超出声明条数的剩余数据", bo + 20 + var_pos, bo + ln, True))
                elif not parsed_any:
                    result.append(("      CSHA/非中央信标/BCSHA时隙信息",
                                   ' '.join(f'{x:02X}' for x in var_data[:12]) + ('...' if len(var_data) > 12 else ''),
                                   f"{len(var_data)}字节",
                                   "变长时隙描述(CSMA+非中央信标+绑定CSMA)", bo + 20, bo + ln, True))
        elif ln > 0:
            # 未知条目: 显示原始内容
            result.append(("      内容(原始)",
                           ' '.join(f'{b:02X}' for b in content[:12]) + ('...' if ln > 12 else ''),
                           f"{ln}字节", f"条目0x{hdr:02X}原始内容",
                           bo, bo + ln, True))

        return result

    # ─── MAC 帧解析 ──────────────────────────────────────────

    def _parse_mac_frame(self, data: bytes, base_offset: int) -> List[Tuple]:
        """解析完整 MAC 帧（MAC头 + MSDU + ICV）"""
        table = []
        if len(data) < 4:
            table.append(("❌ MAC帧解析失败", "", "", "长度不足", base_offset, base_offset + len(data) - 1))
            return table

        table.append((
            "── MAC帧 ──",
            "",
            f"{len(data)}字节",
            "MAC帧头 + MSDU + ICV",
            base_offset, base_offset + len(data) - 1,
        ))

        # 解析MAC头
        mac_header_len, mac_header_table = self._parse_mac_header(data, base_offset)
        table.extend(mac_header_table)

        # MSDU + ICV
        if len(data) > mac_header_len:
            msdu_data = data[mac_header_len:]
            table.append((
                "── MSDU + ICV ──",
                "",
                f"{len(msdu_data)}字节",
                "MSDU载荷 + 完整性校验值",
                base_offset + mac_header_len, base_offset + len(data) - 1,
            ))

            # 尝试定位 ICV（最后4字节）
            if len(msdu_data) >= 4:
                icv = int.from_bytes(msdu_data[-4:], 'little')
                msdu_body = msdu_data[:-4]
                calc_icv = _crc32(msdu_body)
                icv_status = "✓ 校验正确" if calc_icv == icv else f"✗ 校验错误(计算=0x{calc_icv:08X})"

                # MSDU解析
                msdu_table = self._parse_msdu_payload(msdu_body, base_offset + mac_header_len)
                table.extend(msdu_table)

                table.append((
                    "完整性校验值(ICV)",
                    ' '.join(f'{b:02X}' for b in msdu_data[-4:]),
                    f"0x{icv:08X}",
                    icv_status,
                    base_offset + len(data) - 4, base_offset + len(data) - 1,
                ))
            else:
                table.append((
                    "MSDU数据",
                    ' '.join(f'{b:02X}' for b in msdu_data),
                    f"{len(msdu_data)}字节",
                    "MSDU载荷(过短，无ICV)",
                    base_offset + mac_header_len, base_offset + len(data) - 1,
                ))

        return table

    def _parse_mac_header(self, data: bytes, offset: int) -> Tuple[int, List[Tuple]]:
        """解析MAC帧头，返回 (帧头长度, 解析表)"""
        ver = data[offset] & 0x0F
        if ver == 1:
            return self._parse_mac_singlehop_header(data, offset)
        return self._parse_mac_std_header(data, offset)

    def _parse_mac_std_header(self, data: bytes, offset: int) -> Tuple[int, List[Tuple]]:
        """标准MAC帧头（版本=0，长帧头，16字节固定域）"""
        table = []
        if len(data) - offset < 16:
            table.append(("❌ 标准MAC头", "", "", "长度不足16字节", offset, offset + len(data) - 1))
            return len(data) - offset, table

        base = offset
        b0 = data[offset]
        b1 = data[offset + 1]
        b2 = data[offset + 2]
        b3 = data[offset + 3]
        b4 = data[offset + 4]
        b5 = data[offset + 5]
        b6 = data[offset + 6]
        b7 = data[offset + 7]
        b8 = data[offset + 8]
        b9 = data[offset + 9]
        b10 = data[offset + 10]
        b11 = data[offset + 11]
        b12 = data[offset + 12]
        b13 = data[offset + 13]

        # 版本 (bit0-3)
        ver = b0 & 0x0F
        table.append((
            "  版本",
            f"0x{ver:01X}",
            str(ver),
            MAC_VERSIONS.get(ver, f"保留({ver})"),
            base, base,
        ))

        # 原始源TEI: byte0[4:7](高4bit) + byte1(低8bit) = 12bit
        src_tei = ((b0 >> 4) << 8) | b1
        table.append((
            "  原始源TEI",
            f"0x{src_tei:03X}",
            str(src_tei),
            "创建报文站点的TEI",
            base, base + 1,
        ))

        # 原始目的TEI: byte2(高8bit) + byte3[0:3](低4bit) = 12bit
        dst_tei = (b2 << 4) | (b3 & 0x0F)
        table.append((
            "  原始目的TEI",
            f"0x{dst_tei:03X}",
            str(dst_tei),
            "MSDU最终目的终端设备标识",
            base + 2, base + 3,
        ))

        # 发送类型: byte3[4:7]
        tx_type = (b3 >> 4) & 0x0F
        table.append((
            "  发送类型",
            f"0x{tx_type:01X}",
            str(tx_type),
            TX_TYPES.get(tx_type, f"保留({tx_type})"),
            base + 3, base + 3,
        ))

        # 发送次数限值: byte4[0:4] (5bit?)
        # 文档: 发送次数限值 5bit(byte4 bit0-4)
        tx_limit = b4 & 0x1F
        table.append((
            "  发送次数限值",
            f"0x{tx_limit:02X}",
            str(tx_limit),
            f"最大发送次数: {tx_limit}",
            base + 4, base + 4,
        ))

        # MSDU序列号: byte5~6 (16bit 小端)
        msdu_seq = int.from_bytes(data[offset + 5:offset + 7], 'little')
        table.append((
            "  MSDU序列号",
            ' '.join(f'{b:02X}' for b in data[offset + 5:offset + 7]),
            str(msdu_seq),
            f"MSDU递增序列号: {msdu_seq}",
            base + 5, base + 6,
        ))

        # MSDU类型: byte7
        msdu_type = b7
        table.append((
            "  MSDU类型",
            f"0x{msdu_type:02X}",
            str(msdu_type),
            MSDU_TYPES.get(msdu_type, f"保留({msdu_type})"),
            base + 7, base + 7,
        ))

        # MSDU长度: byte8 + byte9[0:2] = 11bit
        msdu_len = (b8 << 3) | (b9 & 0x07)
        table.append((
            "  MSDU长度",
            f"0x{msdu_len:03X}",
            f"{msdu_len}字节",
            f"MSDU长度: {msdu_len}字节",
            base + 8, base + 9,
        ))

        # 重启次数: byte9[3:6] (4bit)
        reset_cnt = (b9 >> 3) & 0x0F
        table.append((
            "  重启次数",
            f"0x{reset_cnt:01X}",
            str(reset_cnt),
            f"站点重启次数: {reset_cnt}",
            base + 9, base + 9,
        ))

        # 代理主路径标识: byte9[7]
        proxy_flag = (b9 >> 7) & 0x01
        table.append((
            "  代理主路径标识",
            f"0b{proxy_flag}",
            str(proxy_flag),
            "主路径" if proxy_flag else "非主路径",
            base + 9, base + 9,
        ))

        # 路由总跳数: byte10[0:3]
        total_hops = b10 & 0x0F
        table.append((
            "  路由总跳数",
            f"0x{total_hops:01X}",
            str(total_hops),
            f"路由总跳数: {total_hops}",
            base + 10, base + 10,
        ))

        # 路由剩余跳数: byte10[4:7]
        remain_hops = (b10 >> 4) & 0x0F
        table.append((
            "  路由剩余跳数",
            f"0x{remain_hops:01X}",
            str(remain_hops),
            f"剩余可转发跳数: {remain_hops}",
            base + 10, base + 10,
        ))

        # 广播方向: byte11[0:1]
        bc_dir = b11 & 0x03
        table.append((
            "  广播方向",
            f"0x{bc_dir:01X}",
            str(bc_dir),
            BROADCAST_DIRS.get(bc_dir, f"保留({bc_dir})"),
            base + 11, base + 11,
        ))

        # 路径修复标志: byte11[2]
        repair_flag = (b11 >> 2) & 0x01
        table.append((
            "  路径修复标志",
            f"0b{repair_flag}",
            str(repair_flag),
            "路径修复中" if repair_flag else "正常转发",
            base + 11, base + 11,
        ))

        # MAC地址标志: byte11[3]
        mac_flag = (b11 >> 3) & 0x01
        table.append((
            "  MAC地址标志",
            f"0b{mac_flag}",
            str(mac_flag),
            "携带MAC地址" if mac_flag else "未携带MAC地址",
            base + 11, base + 11,
        ))

        # 组网序列号: byte13
        net_sn = b13
        table.append((
            "  组网序列号",
            f"0x{net_sn:02X}",
            str(net_sn),
            f"组网序列号: {net_sn}",
            base + 13, base + 13,
        ))

        # 帧头长度
        header_len = 16
        if mac_flag == 1 and len(data) - offset >= 28:
            # 携带MAC地址：源MAC(6B) + 目的MAC(6B)
            src_mac = data[offset + 16:offset + 22]
            dst_mac = data[offset + 22:offset + 28]
            table.append((
                "  原始源MAC地址",
                ' '.join(f'{b:02X}' for b in src_mac),
                ':'.join(f'{b:02X}' for b in src_mac),
                "源站点MAC地址(大端)",
                base + 16, base + 21,
            ))
            table.append((
                "  原始目的MAC地址",
                ' '.join(f'{b:02X}' for b in dst_mac),
                ':'.join(f'{b:02X}' for b in dst_mac),
                "目的站点MAC地址(大端)",
                base + 22, base + 27,
            ))
            header_len = 28

        return header_len, table

    def _parse_mac_singlehop_header(self, data: bytes, offset: int) -> Tuple[int, List[Tuple]]:
        """单跳MAC帧头（版本=1，短帧头，4字节）- 仅无线"""
        table = []
        if len(data) - offset < 4:
            table.append(("❌ 单跳MAC头", "", "", "长度不足4字节", offset, offset + len(data) - 1))
            return len(data) - offset, table

        base = offset
        b0 = data[offset]
        b1 = data[offset + 1]
        b2 = data[offset + 2]
        b3 = data[offset + 3]

        # 版本 (bit0-3)
        ver = b0 & 0x0F
        table.append((
            "  版本",
            f"0x{ver:01X}",
            str(ver),
            MAC_VERSIONS.get(ver, f"保留({ver})"),
            base, base,
        ))

        # 消息类型: byte1
        msg_type = b1
        table.append((
            "  消息类型",
            f"0x{msg_type:02X}",
            str(msg_type),
            SINGLEHOP_MSG_TYPES.get(msg_type, f"保留({msg_type})"),
            base + 1, base + 1,
        ))

        # MSDU长度: byte2 + byte3[0:2] = 11bit
        msdu_len = (b2 << 3) | (b3 & 0x07)
        table.append((
            "  MSDU长度",
            f"0x{msdu_len:03X}",
            f"{msdu_len}字节",
            f"MSDU长度: {msdu_len}字节",
            base + 2, base + 3,
        ))

        return 4, table

    # ─── MSDU 解析 ────────────────────────────────────────────

    def _parse_msdu_payload(self, data: bytes, base_offset: int) -> List[Tuple]:
        """解析MSDU载荷（按类型分发）"""
        table = []
        if not data:
            return table

        # 从MAC头获知类型需传参，这里尝试自动检测
        # 首字节判断：0x00=管理消息, 0x30=应用层(端口0x11在另一个位置)...
        # 简化：直接按应用层尝试检测
        # 应用层特征：首字节=端口号(0x11/0x12/0x1A)
        first = data[0]
        if first in (0x11, 0x12, 0x1A):
            app_table = self._parse_application_layer(data, base_offset)
            table.extend(app_table)
        elif first == 0x00:
            # 可能是管理消息(MMTYPE低8位=0, 但MMTYPE是2字节小端)
            # 尝试解析管理消息
            try:
                from hdc10_mme_parser import parse_management_message
                mme_table = parse_management_message(data, base_offset)
                table.extend(mme_table)
            except (ImportError, Exception):
                table.append((
                    "  网络管理消息",
                    f"0x{first:02X}",
                    "",
                    "管理消息(hdc10_mme_parser未加载)",
                    base_offset, base_offset + min(len(data), 4) - 1,
                ))
        else:
            # 未知类型，显示原始数据
            table.append((
                "  MSDU数据",
                ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
                f"{len(data)}字节",
                f"MSDU载荷({len(data)}字节)",
                base_offset, base_offset + min(len(data), 16) - 1,
            ))

        return table

    # ─── 应用层解析 ────────────────────────────────────────────

    def _parse_application_layer(self, data: bytes, base_offset: int) -> List[Tuple]:
        """解析应用层报文：通用头 + 业务数据"""
        table = []
        if len(data) < 4:
            table.append(("❌ 应用层解析失败", "", "", "长度不足", base_offset, base_offset + len(data) - 1))
            return table

        table.append((
            "── 应用层报文 ──",
            "",
            f"{len(data)}字节",
            "通用报文头 + 业务报文体",
            base_offset, base_offset + len(data) - 1,
        ))

        port = data[0]
        msg_id = int.from_bytes(data[1:3], 'little')
        ctrl = data[3]

        # 安全模式（高4位）+ 业务ID（低12位）
        sec_mode = (msg_id >> 12) & 0x0F
        biz_id = msg_id & 0x0FFF

        table.append((
            "  报文端口号",
            f"0x{port:02X}",
            str(port),
            APP_PORTS.get(port, f"保留(0x{port:02X})"),
            base_offset, base_offset,
        ))
        table.append((
            "  报文ID",
            ' '.join(f'{b:02X}' for b in data[1:3]),
            f"0x{msg_id:04X}",
            f"安全模式: {SECURITY_MODES.get(sec_mode, sec_mode)}, 业务ID: 0x{biz_id:03X}",
            base_offset + 1, base_offset + 2,
        ))
        table.append((
            "  安全模式",
            f"0x{sec_mode:01X}",
            str(sec_mode),
            SECURITY_MODES.get(sec_mode, f"保留({sec_mode})"),
            base_offset + 1, base_offset + 2,
        ))
        table.append((
            "  业务报文ID",
            f"0x{biz_id:03X}",
            str(biz_id),
            f"业务类型ID: 0x{biz_id:03X}",
            base_offset + 1, base_offset + 2,
        ))
        table.append((
            "  报文控制字",
            f"0x{ctrl:02X}",
            str(ctrl),
            f"控制字: 0x{ctrl:02X}",
            base_offset + 3, base_offset + 3,
        ))

        # 业务数据
        if len(data) > 4:
            payload = data[4:]
            biz_table = self._parse_app_payload(payload, base_offset + 4, biz_id, port)
            table.extend(biz_table)

        return table

    def _parse_app_payload(self, data: bytes, offset: int, msg_id: int, port: int) -> List[Tuple]:
        """业务报文数据解析（按报文ID分派）"""
        table = []
        if not data:
            return table

        table.append((
            "── 业务数据 ──",
            "",
            f"{len(data)}字节",
            f"报文ID: 0x{msg_id:03X}",
            offset, offset + len(data) - 1,
        ))

        # 抄表类
        if msg_id in (0x001, 0x002, 0x003) and port == 0x11:
            table.extend(self._parse_meter_reading(data, offset, msg_id))
        elif msg_id == 0x020 and port == 0x11:
            table.extend(self._parse_confirm(data, offset))
        elif msg_id == 0x004 and port == 0x11:
            table.extend(self._parse_timesync(data, offset))
        elif msg_id == 0x008 and port == 0x11:
            table.extend(self._parse_event(data, offset))
        elif msg_id == 0x006 and port == 0x11:
            table.extend(self._parse_comm_test(data, offset))
        elif msg_id in (0x011, 0x012, 0x013) and port == 0x11:
            table.extend(self._parse_registration(data, offset, msg_id))
        elif msg_id in (0x030, 0x031, 0x032, 0x033, 0x034, 0x035, 0x036) and port == 0x12:
            table.extend(self._parse_upgrade(data, offset, msg_id))
        elif msg_id == 0x0A1 and port == 0x11:
            table.extend(self._parse_phase_ident(data, offset))
        elif msg_id == 0x0A2 and port == 0x11:
            table.extend(self._parse_query_id(data, offset))
        elif msg_id == 0x0A3 and port == 0x11:
            table.extend(self._parse_precise_timesync(data, offset))
        elif msg_id == 0x040 and port == 0x11:
            table.extend(self._parse_meter_reader_cco(data, offset))
        elif msg_id == 0x041 and port == 0x11:
            table.extend(self._parse_meter_reader_passthrough(data, offset))
        else:
            # 未知类型，显示原始hex
            show = data[:32]
            table.append((
                "  原始数据",
                ' '.join(f'{b:02X}' for b in show) + ("..." if len(data) > 32 else ""),
                f"{len(data)}字节",
                f"未识别的业务数据(0x{msg_id:03X})",
                offset, offset + min(len(data), 32) - 1,
            ))

        return table

    def _parse_meter_reading(self, data: bytes, offset: int, msg_id: int) -> List[Tuple]:
        """抄表报文解析（0x001/0x002/0x003）"""
        table = []
        if len(data) < 8:
            return [("  抄表报文(过短)", "", "", f"需至少8字节，仅{len(data)}字节", offset, offset + len(data) - 1)]

        names = {0x001: "终端主动抄表", 0x002: "路由主动抄表", 0x003: "终端主动并发抄表"}
        name = names.get(msg_id, "抄表")

        b0 = data[0]
        b1 = data[1]
        b2 = data[2]
        b3 = data[3]

        # 报文头长度: byte0[6:7](高2b)+byte1[0:3](低4b)=6bit, 单位4字节字(类IPv4 IHL)
        hdr_len = (((b0 >> 6) & 0x03) << 4) | (b1 & 0x0F)
        hdr_bytes = hdr_len * 4

        table.append((
            f"  {name}报文头",
            "",
            f"{hdr_bytes}字节",
            f"头长: {hdr_len}×4B = {hdr_bytes}B",
            offset, offset + hdr_bytes - 1,
        ))
        table.append((
            "    协议版本号",
            f"0x{proto_ver:02X}",
            str(proto_ver),
            f"协议版本: {proto_ver}",
            offset, offset,
        ))
        table.append((
            "    报文头长度",
            f"0x{hdr_len:02X}",
            f"{hdr_len}×4B={hdr_bytes}B",
            f"报文头长度: {hdr_len}个4字节块",
            offset, offset + 1,
        ))

        # 配置字/应答状态: byte1[4:7]
        cfg = (b1 >> 4) & 0x0F
        if msg_id == 0x003:  # 并发抄表配置字
            retry_una = cfg & 0x01
            retry_nak = (cfg >> 1) & 0x01
            max_retry = (cfg >> 2) & 0x03
            table.append((
                "    配置字",
                f"0b{cfg:04b}",
                str(cfg),
                f"未应答重试:{retry_una} 否认重试:{retry_nak} 最大重试:{max_retry}",
                offset + 1, offset + 1,
            ))
        else:
            direction = None
            # 选项字判断方向
            if len(data) >= 8:
                opt = data[7]
                direction = "下行" if (opt & 0x01) == 0 else "上行"
            table.append((
                "    配置字/状态",
                f"0x{cfg:01X}",
                str(cfg),
                f"{'正常应答' if cfg == 0 else f'状态:{cfg}'}",
                offset + 1, offset + 1,
            ))

        # 转发数据规约类型: byte2[0:3]
        proto_type = b2 & 0x0F
        table.append((
            "    转发数据规约类型",
            f"0x{proto_type:01X}",
            str(proto_type),
            PROTOCOL_TYPES.get(proto_type, f"保留({proto_type})"),
            offset + 2, offset + 2,
        ))

        # 转发数据长度: byte2[4:7] + byte3[0:7] = 12bit
        data_len = ((b2 >> 4) & 0x0F) | (b3 << 4)
        table.append((
            "    转发数据长度",
            f"0x{data_len:03X}",
            f"{data_len}字节",
            f"DATA域长度: {data_len}字节",
            offset + 2, offset + 3,
        ))

        # 报文序号: byte4~5
        seq = int.from_bytes(data[4:6], 'little')
        table.append((
            "    报文序号",
            ' '.join(f'{b:02X}' for b in data[4:6]),
            str(seq),
            f"序号: {seq}",
            offset + 4, offset + 5,
        ))

        # DATA 域
        if hdr_bytes < len(data):
            payload = data[hdr_bytes:hdr_bytes + data_len] if hdr_bytes + data_len <= len(data) else data[hdr_bytes:]
            table.append((
                "    数据(DATA)",
                ' '.join(f'{b:02X}' for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
                f"{len(payload)}字节",
                "抄表应用报文数据",
                offset + hdr_bytes, offset + hdr_bytes + len(payload) - 1,
            ))

        return table

    def _parse_confirm(self, data: bytes, offset: int) -> List[Tuple]:
        """确认/否认报文（0x020）"""
        table = []
        if len(data) < 4:
            return table

        b0 = data[0]
        b1 = data[1]

        proto_ver = b0 & 0x3F
        hdr_len = (((b0 >> 6) & 0x03) << 4) | (b1 & 0x0F)  # 6bit, ×4字节
        hdr_bytes = hdr_len * 4

        direction = (b1 >> 4) & 0x01
        ack_bit = (b1 >> 5) & 0x01
        seq = int.from_bytes(data[2:4], 'little') if len(data) >= 4 else 0

        table.append((
            "  确认/否认报文",
            "",
            f"{hdr_bytes}字节头",
            "确认/否认应答报文",
            offset, offset + min(len(data), hdr_bytes) - 1,
        ))
        table.append(("    方向位", f"0b{direction}", str(direction), "上行" if direction else "下行", offset + 1, offset + 1))
        table.append(("    确认位", f"0b{ack_bit}", str(ack_bit), "确认" if ack_bit else "否认", offset + 1, offset + 1))
        table.append(("    报文序号", f"0x{seq:04X}", str(seq), f"被确认/否认的报文序号: {seq}", offset + 2, offset + 3))
        return table

    def _parse_timesync(self, data: bytes, offset: int) -> List[Tuple]:
        """校时报文（0x004）"""
        table = []
        if len(data) < 4:
            return table

        b0 = data[0]
        b1 = data[1]
        b2 = data[2]
        b3 = data[3]

        proto_ver = b0 & 0x3F
        hdr_len = (((b0 >> 6) & 0x03) << 4) | (b1 & 0x0F)  # 6bit, ×4字节
        hdr_bytes = hdr_len * 4

        # 转发数据长度: byte2[4:7] + byte3[0:7] = 12bit
        data_len = ((b2 >> 4) & 0x0F) | (b3 << 4)

        table.append((
            "  校时报文",
            "",
            f"{hdr_bytes}字节头",
            "校时命令",
            offset, offset + min(len(data), hdr_bytes) - 1,
        ))
        table.append(("    转发数据长度", f"0x{data_len:03X}", f"{data_len}字节",
                      f"校时报文数据长度: {data_len}字节", offset + 2, offset + 3))

        if len(data) > hdr_bytes:
            payload = data[hdr_bytes:hdr_bytes + data_len] if hdr_bytes + data_len <= len(data) else data[hdr_bytes:]
            table.append(("    数据(DATA)",
                          ' '.join(f'{b:02X}' for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
                          f"{len(payload)}字节", "校时应用报文数据",
                          offset + hdr_bytes, offset + hdr_bytes + len(payload) - 1))
        return table

    def _parse_event(self, data: bytes, offset: int) -> List[Tuple]:
        """事件上报报文（0x008）"""
        table = []
        if len(data) < 12:
            return [("  事件报文(过短)", "", "", f"需至少12字节", offset, offset + len(data) - 1)]

        b0 = data[0]
        b1 = data[1]

        proto_ver = b0 & 0x3F
        hdr_len = (((b0 >> 6) & 0x03) << 4) | (b1 & 0x0F)  # 6bit, ×4字节
        hdr_bytes = hdr_len * 4

        dir_bit = (b1 >> 4) & 0x01
        start_bit = (b1 >> 5) & 0x01
        # 功能码: byte1[6:7] + byte2[0:3] = 6bit
        func_code = ((b1 >> 6) & 0x03) | ((data[2] & 0x07) << 2)

        # 转发数据长度: byte2[4:7] + byte3[0:7]
        data_len = ((data[2] >> 4) & 0x0F) | (data[3] << 4)

        seq = int.from_bytes(data[4:6], 'little')
        meter_addr = data[6:12]  # 48bit BCD

        table.append((
            "  事件上报报文",
            "",
            f"{hdr_bytes}字节头",
            "事件主动上报",
            offset, offset + hdr_bytes - 1,
        ))
        table.append(("    方向位", f"0b{dir_bit}", str(dir_bit), "上行" if dir_bit else "下行", offset + 1, offset + 1))
        table.append(("    启动位", f"0b{start_bit}", str(start_bit), "启动站" if start_bit else "从动站", offset + 1, offset + 1))
        table.append(("    功能码", f"0x{func_code:02X}", str(func_code), f"事件功能码: {func_code}", offset + 1, offset + 2))
        table.append(("    报文序号", f"0x{seq:04X}", str(seq), f"序号: {seq}", offset + 4, offset + 5))
        table.append(("    电能表地址",
                      ' '.join(f'{b:02X}' for b in meter_addr),
                      ''.join(f'{b:02X}' for b in reversed(meter_addr)),
                      "BCD码(6字节)",
                      offset + 6, offset + 11))

        if len(data) > hdr_bytes:
            payload = data[hdr_bytes:]
            table.append(("    事件数据",
                          ' '.join(f'{b:02X}' for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
                          f"{len(payload)}字节", "事件数据内容",
                          offset + hdr_bytes, offset + hdr_bytes + len(payload) - 1))

        return table

    def _parse_comm_test(self, data: bytes, offset: int) -> List[Tuple]:
        """通信测试命令（0x006）"""
        table = []
        if len(data) < 4:
            return table

        b2 = data[2]
        b3 = data[3]
        proto_type = b2 & 0x0F
        data_len = ((b2 >> 4) & 0x0F) | (b3 << 4)

        table.append(("  通信测试报文", "", "", "通信测试命令", offset, offset + len(data) - 1))
        table.append(("    转发数据规约类型", f"0x{proto_type:01X}", str(proto_type),
                      PROTOCOL_TYPES.get(proto_type, f"保留({proto_type})"), offset + 2, offset + 2))
        table.append(("    转发数据长度", f"0x{data_len:03X}", f"{data_len}字节",
                      f"测试数据长度: {data_len}字节", offset + 2, offset + 3))

        if len(data) > 4:
            payload = data[4:4 + data_len] if 4 + data_len <= len(data) else data[4:]
            table.append(("    测试数据",
                          ' '.join(f'{b:02X}' for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
                          f"{len(payload)}字节", "通信测试数据",
                          offset + 4, offset + 4 + len(payload) - 1))
        return table

    def _parse_registration(self, data: bytes, offset: int, msg_id: int) -> List[Tuple]:
        """从节点注册报文（0x011/0x012/0x013）"""
        table = []
        if len(data) < 8:
            return table

        names = {0x011: "查询从节点注册结果", 0x012: "启动从节点注册", 0x013: "停止从节点注册"}
        name = names.get(msg_id, "注册报文")

        b0 = data[0]
        b1 = data[1]

        proto_ver = b0 & 0x3F
        hdr_len = (((b0 >> 6) & 0x03) << 4) | (b1 & 0x0F)  # 6bit, ×4字节
        hdr_bytes = hdr_len * 4

        force_ack = (b1 >> 4) & 0x01
        reg_param = (b1 >> 5) & 0x07
        param_names = {0: "查询结果", 1: "启动注册"}

        seq = int.from_bytes(data[4:8], 'little') if len(data) >= 8 else 0

        table.append((
            f"  {name}",
            "",
            f"{hdr_bytes}字节头",
            f"从节点注册: {name}",
            offset, offset + min(len(data), hdr_bytes) - 1,
        ))
        table.append(("    强制应答标志", f"0b{force_ack}", str(force_ack),
                      "强制应答" if force_ack else "不需强制应答", offset + 1, offset + 1))
        table.append(("    从节点注册参数", f"0x{reg_param:01X}", str(reg_param),
                      param_names.get(reg_param, f"保留({reg_param})"), offset + 1, offset + 1))
        table.append(("    报文序号", f"0x{seq:08X}", str(seq),
                      f"序号: {seq}", offset + 4, offset + 7))

        return table

    def _parse_upgrade(self, data: bytes, offset: int, msg_id: int) -> List[Tuple]:
        """升级系列报文（0x030~0x036）"""
        table = []
        names = {
            0x030: "开始升级", 0x031: "停止升级",
            0x032: "传输文件数据(单播)", 0x033: "传输文件数据(单播转本地广播)",
            0x034: "查询站点升级状态", 0x035: "执行升级", 0x036: "查询站点信息",
        }
        name = names.get(msg_id, f"升级报文(0x{msg_id:03X})")

        table.append((
            f"  {name}",
            "",
            f"{len(data)}字节",
            f"升级业务: {name}",
            offset, offset + len(data) - 1,
        ))

        # 解析公共字段
        if msg_id == 0x030 and len(data) >= 20:
            # 开始升级: 20字节头
            upgrade_id = int.from_bytes(data[4:8], 'little')
            time_win = int.from_bytes(data[8:10], 'little')
            blk_size = int.from_bytes(data[10:12], 'little')
            file_size = int.from_bytes(data[12:16], 'little')
            file_crc = int.from_bytes(data[16:20], 'little')
            table.append(("    升级ID", f"0x{upgrade_id:08X}", str(upgrade_id), f"升级标识: {upgrade_id}", offset + 4, offset + 7))
            table.append(("    升级时间窗", f"0x{time_win:04X}", f"{time_win}分钟", f"升级窗口: {time_win}分钟", offset + 8, offset + 9))
            table.append(("    升级块大小", f"0x{blk_size:04X}", f"{blk_size}字节", f"每块大小: {blk_size}字节", offset + 10, offset + 11))
            table.append(("    升级文件大小", f"0x{file_size:08X}", f"{file_size}字节", f"文件总长度: {file_size}字节", offset + 12, offset + 15))
            table.append(("    文件CRC校验", f"0x{file_crc:08X}", str(file_crc), f"文件CRC-32: 0x{file_crc:08X}", offset + 16, offset + 19))

        elif msg_id in (0x032, 0x033) and len(data) >= 12:
            # 传输文件数据
            blk_size = int.from_bytes(data[2:4], 'little')
            upgrade_id = int.from_bytes(data[4:8], 'little')
            blk_num = int.from_bytes(data[8:12], 'little')
            table.append(("    数据块大小", f"0x{blk_size:04X}", f"{blk_size}字节", f"数据块长度: {blk_size}字节", offset + 2, offset + 3))
            table.append(("    升级ID", f"0x{upgrade_id:08X}", str(upgrade_id), f"升级标识: {upgrade_id}", offset + 4, offset + 7))
            table.append(("    数据块编号", f"0x{blk_num:08X}", str(blk_num), f"块号: {blk_num}", offset + 8, offset + 11))
            if len(data) > 12:
                blk_data = data[12:12 + blk_size] if 12 + blk_size <= len(data) else data[12:]
                table.append(("    数据块",
                              ' '.join(f'{b:02X}' for b in blk_data[:16]) + ("..." if len(blk_data) > 16 else ""),
                              f"{len(blk_data)}字节", "文件数据块内容",
                              offset + 12, offset + 12 + len(blk_data) - 1))

        elif msg_id == 0x034 and len(data) >= 12:
            # 查询站点升级状态: 下行(表40, 12字节) / 上行(表45, 12字节+接收位图)
            b0, b1 = data[0], data[1]
            version = b0 & 0x3F
            hdr_len = (((b0 >> 6) & 0x03) << 4) | (b1 & 0x0F)  # 6bit, ×4字节
            status_nib = (b1 >> 4) & 0x0F
            blk_count = int.from_bytes(data[2:4], 'little')
            start_blk = int.from_bytes(data[4:8], 'little')
            upgrade_id = int.from_bytes(data[8:12], 'little')
            # 方向判定: 上行带接收位图(len>12); 恰12字节按表40下行处理
            # (表45上行的升级状态占字节1高4位, 表40同位置为保留0)
            is_uplink = len(data) > 12 or status_nib in (1, 2, 3, 4)

            table.append(("    协议版本号", f"0x{version:02X}", str(version),
                          "固定为1", offset, offset))
            table.append(("    报文头长度", str(hdr_len), str(hdr_len),
                          "报文头(除数据域外)长度", offset, offset + 1))

            if is_uplink:
                status_names = {0: "空闲态", 1: "接收进行态", 2: "接收完成态",
                                3: "升级进行态", 4: "试运行态"}
                table.append(("    方向", "", "上行(STA→CCO)",
                              "升级状态查询应答(表45)", offset, offset + 1))
                table.append(("    升级状态", str(status_nib),
                              status_names.get(status_nib, f"保留({status_nib})"),
                              "升级进展状态", offset + 1, offset + 1))
                table.append(("    有效块数", f"0x{blk_count:04X}", str(blk_count),
                              f"位图中有效块数: {blk_count}", offset + 2, offset + 3))
                table.append(("    起始块号", f"0x{start_blk:08X}", str(start_blk),
                              f"起始块号: {start_blk}", offset + 4, offset + 7))
                table.append(("    升级ID", f"0x{upgrade_id:08X}", str(upgrade_id),
                              f"升级标识: {upgrade_id}", offset + 8, offset + 11))
                if len(data) > 12:
                    bitmap = data[12:]
                    # 块i ↔ 第i//8字节的第i%8比特(LSB在前), 实际块号 = 起始块号 + i
                    total_bits = min(blk_count, len(bitmap) * 8)
                    recv = sum(
                        1 for i in range(total_bits)
                        if bitmap[i >> 3] & (1 << (i & 7))
                    )
                    table.append((
                        "    升级位图",
                        ' '.join(f'{b:02X}' for b in bitmap[:16]) + ("..." if len(bitmap) > 16 else ""),
                        f"{recv}/{blk_count}块已接收",
                        f"{len(bitmap)}字节, 每bit对应一个文件块(1=已接收)",
                        offset + 12, offset + 12 + len(bitmap) - 1,
                    ))
                    # 逐块编号明细: 每行32个块, [✓n]=已接收 [✕n]=丢包
                    per_row = 32
                    for base in range(0, total_bits, per_row):
                        end = min(base + per_row, total_bits)
                        cells = []
                        lost = 0
                        for i in range(base, end):
                            ok = bitmap[i >> 3] & (1 << (i & 7))
                            if ok:
                                cells.append(f"[✓{start_blk + i}]")
                            else:
                                cells.append(f"[✕{start_blk + i}]")
                                lost += 1
                        table.append((
                            f"      位图明细{start_blk + base}-{start_blk + end - 1}",
                            "",
                            "".join(cells),
                            "全部已接收" if lost == 0 else f"{lost}个丢包",
                            offset + 12 + (base >> 3), offset + 12 + ((end - 1) >> 3),
                        ))
            else:
                table.append(("    方向", "", "下行(CCO→STA)",
                              "升级状态查询(表40)", offset, offset + 1))
                table.append(("    连续查询块数", f"0x{blk_count:04X}",
                              "查询所有块状态" if blk_count == 0xFFFF else str(blk_count),
                              "0xFFFF=查询所有", offset + 2, offset + 3))
                table.append(("    起始块号", f"0x{start_blk:08X}", str(start_blk),
                              f"起始块号: {start_blk}", offset + 4, offset + 7))
                table.append(("    升级ID", f"0x{upgrade_id:08X}", str(upgrade_id),
                              f"升级标识: {upgrade_id}", offset + 8, offset + 11))

        elif msg_id == 0x035 and len(data) >= 12:
            # 执行升级
            wait_time = int.from_bytes(data[2:4], 'little')
            upgrade_id = int.from_bytes(data[4:8], 'little')
            trial_time = int.from_bytes(data[8:12], 'little')
            table.append(("    等待复位时间", f"0x{wait_time:04X}", f"{wait_time}秒", f"等待复位: {wait_time}秒", offset + 2, offset + 3))
            table.append(("    升级ID", f"0x{upgrade_id:08X}", str(upgrade_id), f"升级标识: {upgrade_id}", offset + 4, offset + 7))
            table.append(("    试运行时间", f"0x{trial_time:08X}", f"{trial_time}秒", f"试运行: {trial_time}秒", offset + 8, offset + 11))

        return table

    def _parse_phase_ident(self, data: bytes, offset: int) -> List[Tuple]:
        """台区户变关系识别（0x0A1）"""
        table = []
        if len(data) < 12:
            return table

        b0 = data[0]
        b1 = data[1]

        proto_ver = b0 & 0x3F
        hdr_len = (((b0 >> 6) & 0x03) << 4) | (b1 & 0x0F)  # 6bit, ×4字节
        hdr_bytes = hdr_len * 4

        dir_bit = (b1 >> 4) & 0x01
        start_bit = (b1 >> 5) & 0x01
        phase = (b1 >> 6) & 0x03

        seq = int.from_bytes(data[2:4], 'little')
        mac = data[4:10]
        feat_type = data[10]
        coll_type = data[11]

        phase_names = {0: "默认/三相", 1: "第一出线", 2: "第二出线", 3: "第三出线"}

        table.append((
            "  台区户变关系识别报文",
            "",
            f"{hdr_bytes}字节头",
            "台区户变关系识别",
            offset, offset + hdr_bytes - 1,
        ))
        table.append(("    方向位", f"0b{dir_bit}", str(dir_bit), "上行" if dir_bit else "下行", offset + 1, offset + 1))
        table.append(("    启动位", f"0b{start_bit}", str(start_bit), "启动站" if start_bit else "从动站", offset + 1, offset + 1))
        table.append(("    采集相位", f"0x{phase:01X}", str(phase),
                      phase_names.get(phase, f"保留({phase})"), offset + 1, offset + 1))
        table.append(("    报文序号", f"0x{seq:04X}", str(seq), f"序号: {seq}", offset + 2, offset + 3))
        table.append(("    MAC地址",
                      ' '.join(f'{b:02X}' for b in mac),
                      ':'.join(f'{b:02X}' for b in mac),
                      "MAC地址(大端)",
                      offset + 4, offset + 9))
        table.append(("    特征类型", f"0x{feat_type:02X}", str(feat_type),
                      f"特征类型: {feat_type}", offset + 10, offset + 10))
        table.append(("    采集类型", f"0x{coll_type:02X}", str(coll_type),
                      f"采集类型: {coll_type}", offset + 11, offset + 11))

        if len(data) > hdr_bytes:
            payload = data[hdr_bytes:]
            table.append(("    数据(DATA)",
                          ' '.join(f'{b:02X}' for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
                          f"{len(payload)}字节", "特征采集数据",
                          offset + hdr_bytes, offset + hdr_bytes + len(payload) - 1))
            table.extend(self._parse_phase_ident_data(
                payload, offset + hdr_bytes, feat_type, coll_type))

        return table

    def _parse_query_id(self, data: bytes, offset: int) -> List[Tuple]:
        """查询ID信息（0x0A2）"""
        table = []
        if len(data) < 4:
            return table

        b1 = data[1]
        direction = (b1 >> 4) & 0x01
        id_type = (b1 >> 5) & 0x07
        seq = int.from_bytes(data[2:4], 'little')

        type_names = {0: "模块ID", 1: "芯片ID", 2: "模块ID"}

        table.append((
            "  查询ID信息报文",
            "",
            "",
            "查询模块/芯片ID信息",
            offset, offset + min(len(data), 4) - 1,
        ))
        table.append(("    方向位", f"0b{direction}", str(direction),
                      "上行" if direction else "下行", offset + 1, offset + 1))
        table.append(("    ID类型", f"0x{id_type:01X}", str(id_type),
                      type_names.get(id_type, f"保留({id_type})"), offset + 1, offset + 1))
        table.append(("    报文序号", f"0x{seq:04X}", str(seq),
                      f"序号: {seq}", offset + 2, offset + 3))

        # 上行可能有更多字段(ID长度/ID信息/设备类型)
        if len(data) > 4 and direction == 1:
            id_len = data[4]
            table.append(("    ID长度", f"0x{id_len:02X}", str(id_len),
                          f"ID数据长度: {id_len}字节", offset + 4, offset + 4))
            if 5 + id_len <= len(data):
                id_data = data[5:5 + id_len]
                table.append(("    ID信息",
                              ' '.join(f'{b:02X}' for b in id_data),
                              f"{id_len}字节",
                              "模块/芯片ID数据",
                              offset + 5, offset + 4 + id_len))
            if 5 + id_len < len(data):
                dev_type = data[5 + id_len]
                table.append(("    设备类型", f"0x{dev_type:02X}", str(dev_type),
                              f"设备类型: {dev_type}", offset + 5 + id_len, offset + 5 + id_len))

        return table

    def _parse_precise_timesync(self, data: bytes, offset: int) -> List[Tuple]:
        """精准校时（0x0A3）"""
        table = []
        if len(data) < 8:
            return table

        b1 = data[1]
        b2 = data[2]
        # 转发数据长度: byte1[4:7] + byte2[0:7] = 12bit
        data_len = ((b1 >> 4) & 0x0F) | (b2 << 4)
        seq = data[3]
        ntb = int.from_bytes(data[4:8], 'little')

        table.append((
            "  精准校时报文",
            "",
            "",
            "精准校时",
            offset, offset + min(len(data), 8) - 1,
        ))
        table.append(("    转发数据长度", f"0x{data_len:03X}", f"{data_len}字节",
                      f"校时报文数据长度: {data_len}字节", offset + 1, offset + 2))
        table.append(("    报文序号", f"0x{seq:02X}", str(seq),
                      f"序号: {seq}", offset + 3, offset + 3))
        table.append(("    NTB", f"0x{ntb:08X}", str(ntb),
                      f"校时NTB时间: {ntb}", offset + 4, offset + 7))

        if len(data) > 8:
            payload = data[8:8 + data_len] if 8 + data_len <= len(data) else data[8:]
            table.append(("    数据(DATA)",
                          ' '.join(f'{b:02X}' for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
                          f"{len(payload)}字节", "校时应用报文",
                          offset + 8, offset + 8 + len(payload) - 1))

        return table

    def _parse_phase_ident_data(self, data: bytes, offset: int,
                                feat_type: int, coll_type: int) -> List[Tuple]:
        """台区户变 DATA 域按采集类型深度解析

        表56 采集启动(0x01): 起始NTB(4B)+采集周期(1B)+采集数量(1B)+采集序列号(1B)+保留(1B)
        表57 特征信息告知(0x03): TEI(12b)+采集方式(2b)+保留(2b) + 序号(1B)+总数(1B)
                                + 起始NTB1(4B) + 特征序列1 [+ NTB2(4B)+序列2(双沿)]
        表61 判别结果信息(0x05): TEI(2B)+结束标志(1B)+识别结果(1B)+CCO地址(6B)
        """
        table = []
        if not data:
            return table

        if coll_type == 0x01 and len(data) >= 8:
            # 表56: 台区特征采集启动命令
            ntb = int.from_bytes(data[0:4], 'little')
            period = data[4]
            count = data[5]
            seq = data[6]
            table.append(("      起始NTB", f"0x{ntb:08X}", str(ntb),
                          "全网开始采集时刻NTB", offset, offset + 3))
            table.append(("      采集周期", f"0x{period:02X}", f"{period}秒",
                          "工频周期特征时忽略; 其它特征单位秒", offset + 4, offset + 4))
            table.append(("      采集数量", f"0x{count:02X}", str(count),
                          "连续采集数量", offset + 5, offset + 5))
            table.append(("      采集序列号", f"0x{seq:02X}", str(seq),
                          "全网第几次启动采集(0-255循环)", offset + 6, offset + 6))

        elif coll_type == 0x03 and len(data) >= 8:
            # 表57: 台区特征信息告知 (上行 STA→CCO)
            tei12 = int.from_bytes(data[0:2], 'little') & 0x0FFF
            method = (data[1] >> 4) & 0x03
            seq_no = data[2]
            total = data[3]
            ntb1 = int.from_bytes(data[4:8], 'little')
            method_names = {0: "保留", 1: "下降沿采集", 2: "上升沿采集", 3: "双沿采集"}
            table.append(("      TEI", f"0x{tei12:03X}", str(tei12),
                          "STA地址(CCO通知自身特征时为1)", offset, offset + 1))
            table.append(("      采集方式", f"0b{method:02b}",
                          method_names.get(method, f"保留({method})"),
                          "仅工频周期特征有效", offset + 1, offset + 1))
            table.append(("      采集序列号", f"0x{seq_no:02X}", str(seq_no),
                          "第几次采集活动", offset + 2, offset + 2))
            table.append(("      告知总数量", f"0x{total:02X}", str(total),
                          "特征信息序列包含的数据个数", offset + 3, offset + 3))
            table.append(("      起始采集NTB1", f"0x{ntb1:08X}", str(ntb1),
                          "第一个特征数据的采集时刻", offset + 4, offset + 7))
            table.extend(self._parse_phase_feature_series(
                data[8:], offset + 8, feat_type, total, "1"))
            # 双沿采集: 第二组 NTB2 + 序列2
            if method == 3:
                rest = len(data) - 8 - self._phase_series_len(feat_type, total)
                if rest >= 4:
                    pos = 8 + self._phase_series_len(feat_type, total)
                    ntb2 = int.from_bytes(data[pos:pos + 4], 'little')
                    table.append(("      起始采集NTB2", f"0x{ntb2:08X}", str(ntb2),
                                  "上升沿起始时刻(双沿)", offset + pos, offset + pos + 3))
                    table.extend(self._parse_phase_feature_series(
                        data[pos + 4:], offset + pos + 4, feat_type, total, "2"))

        elif coll_type == 0x05 and len(data) >= 10:
            # 表61: 台区判别结果信息
            tei = int.from_bytes(data[0:2], 'little')
            done = data[2]
            result = data[3]
            cco = data[4:10]
            result_names = {0: "识别结果未知", 1: "是本台区", 2: "不是本台区"}
            table.append(("      TEI", f"0x{tei:04X}", str(tei),
                          "STA的TEI标识", offset, offset + 1))
            table.append(("      判别结束标志", f"0x{done:02X}",
                          "已结束" if done == 1 else ("进行中" if done == 0 else f"保留({done})"),
                          "台区判别过程结束标志", offset + 2, offset + 2))
            table.append(("      台区识别结果", f"0x{result:02X}",
                          result_names.get(result, f"保留({result})"),
                          "" if done == 1 else "未结束时无意义",
                          offset + 3, offset + 3))
            table.append(("      正确隶属CCO地址",
                          ' '.join(f'{b:02X}' for b in cco),
                          ':'.join(f'{b:02X}' for b in cco),
                          "非本台区时填充正确隶属CCO地址(大端)",
                          offset + 4, offset + 9))

        elif coll_type in (0x02, 0x04):
            # 收集/结果查询命令: DATA 为空
            pass

        if not table and any(data):
            table.append((
                "      未解析DATA",
                ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
                f"{len(data)}字节",
                f"采集类型0x{coll_type:02X}暂不支持深度解析",
                offset, offset + len(data) - 1,
            ))
        return table

    def _phase_series_len(self, feat_type: int, total: int) -> int:
        """单条特征序列的字节长度: 4字节报告数量头 + N×每项长度"""
        per_item = {1: 2, 2: 2, 3: 2}.get(feat_type, 2)
        return 4 + total * per_item

    def _parse_phase_feature_series(self, data: bytes, offset: int,
                                    feat_type: int, total: int, series_idx: str) -> List[Tuple]:
        """特征序列解析: 表58电压/表59频率/表60周期
        头4字节: 保留(1B)+第一出线数量(1B)+第二出线数量(1B)+第三出线数量(1B)
        随后按相线顺序排列各出线的值(每项2字节)
        """
        table = []
        type_names = {1: "工频电压(V)", 2: "工频频率(Hz)", 3: "工频周期偏差"}
        name = type_names.get(feat_type, f"特征类型{feat_type}")
        if len(data) < 4:
            return table
        reserved = data[0]
        cnt = [data[1], data[2], data[3]]
        phase_names = ["第一出线", "第二出线", "第三出线"]
        table.append((f"      特征序列{series_idx}({name})", "",
                      f"{sum(cnt)}个值/{total}告知",
                      f"保留0x{reserved:02X}, 数量={cnt}", offset, offset + 3))
        pos = 4
        for ph in range(3):
            if cnt[ph] == 0:
                continue
            vals = []
            for i in range(cnt[ph]):
                if pos + 2 > len(data):
                    break
                raw = int.from_bytes(data[pos:pos + 2], 'little')
                if feat_type == 1:
                    # BCD XXX.X 伏(大端): 高字节=百十个位, 低字节=个位.小数位
                    hi, lo = data[pos], data[pos + 1]
                    val = f"{hi >> 4}{hi & 0x0F}{lo >> 4}.{lo & 0x0F}V"
                elif feat_type == 2:
                    # BCD XX.XX Hz(大端): 高字节=十位.个位, 低字节=小数两位
                    hi, lo = data[pos], data[pos + 1]
                    val = f"{hi >> 4}{hi & 0x0F}.{lo >> 4}{lo & 0x0F}Hz"
                else:
                    # 有符号 HEX, 单位 1/3125000 秒, 与20ms理想周期偏差
                    dev_us = raw * 1000000 / 3125000 - 20000 * 1000 / 1000
                    dev_us = raw / 3125000 * 1e6  # 原始计数转微秒
                    val = f"{raw:+d} ({dev_us:.1f}μs)"
                vals.append(val)
                pos += 2
            table.append((f"        {phase_names[ph]}", "",
                          " ".join(vals) if vals else "-",
                          f"{cnt[ph]}个值", offset + 4 + sum(cnt[:ph]) * 2,
                          offset + 4 + (sum(cnt[:ph]) + cnt[ph]) * 2 - 1))
        return table

    def _parse_meter_reader_cco(self, data: bytes, offset: int) -> List[Tuple]:
        """抄控器CCO报文（0x040）"""
        table = []
        if len(data) < 3:
            return table

        proto_type = data[0]
        msg_len = int.from_bytes(data[1:3], 'little')

        table.append((
            "  抄控器CCO报文",
            "",
            f"{msg_len}字节内容",
            "抄控器协议透传",
            offset, offset + min(len(data), 3 + msg_len) - 1,
        ))
        table.append(("    协议类型", f"0x{proto_type:02X}", str(proto_type),
                      f"协议类型: {proto_type} (0=Q/GDW10376.2-2019)", offset, offset))
        table.append(("    报文长度", f"0x{msg_len:04X}", f"{msg_len}字节",
                      f"报文内容长度: {msg_len}字节", offset + 1, offset + 2))

        if len(data) > 3:
            content = data[3:3 + msg_len] if 3 + msg_len <= len(data) else data[3:]
            table.append(("    报文内容",
                          ' '.join(f'{b:02X}' for b in content[:16]) + ("..." if len(content) > 16 else ""),
                          f"{len(content)}字节", "透传报文内容",
                          offset + 3, offset + 3 + len(content) - 1))

        return table

    def _parse_meter_reader_passthrough(self, data: bytes, offset: int) -> List[Tuple]:
        """抄控器数据透传串口转发（0x041）"""
        table = []
        if len(data) < 12:
            return table

        proto_type = data[0]
        start_flag = data[1] & 0x01
        baud = int.from_bytes(data[2:6], 'little')
        msg_len = int.from_bytes(data[10:12], 'little')

        table.append((
            "  抄控器数据透传",
            "",
            "",
            "串口数据透传转发",
            offset, offset + min(len(data), 12) - 1,
        ))
        table.append(("    协议类型", f"0x{proto_type:02X}", str(proto_type),
                      "透明传输" if proto_type == 0 else f"类型:{proto_type}", offset, offset))
        table.append(("    启动标志", f"0b{start_flag}", str(start_flag),
                      "主动报文(需转发)" if start_flag else "应答报文", offset + 1, offset + 1))
        table.append(("    串口波特率", f"0x{baud:08X}", f"{baud}bps",
                      f"波特率: {baud if baud else '默认'} bps", offset + 2, offset + 5))
        table.append(("    报文长度", f"0x{msg_len:04X}", f"{msg_len}字节",
                      f"转发数据长度: {msg_len}字节", offset + 10, offset + 11))

        if len(data) > 12:
            content = data[12:12 + msg_len] if 12 + msg_len <= len(data) else data[12:]
            table.append(("    转发内容",
                          ' '.join(f'{b:02X}' for b in content[:16]) + ("..." if len(content) > 16 else ""),
                          f"{len(content)}字节", "串口转发数据",
                          offset + 12, offset + 12 + len(content) - 1))

        return table

    # ─── 便捷模式 ──────────────────────────────────────────────

    def _parse_app_only(self, data: bytes) -> List[Tuple]:
        """app 模式：直接解析应用层"""
        if len(data) >= 1 and data[0] in (0x11, 0x12, 0x1A):
            return self._parse_application_layer(data, 0)
        # 尝试剥离FC
        if self._detect_fc(data) and len(data) > 16:
            return self.parse_to_table(data, parse_level="auto")
        return [("应用层数据",
                 ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
                 f"{len(data)}字节",
                 "未识别格式的应用层数据", 0, min(len(data), 16) - 1)]

    def _parse_mac_only(self, data: bytes, frame_type: int) -> List[Tuple]:
        """mac_only 模式：直接解析MAC帧"""
        return self._parse_mac_frame(data, 0)

    def _parse_pb_only(self, data: bytes, frame_type: int) -> List[Tuple]:
        """pb_only 模式：解析物理块"""
        return self._parse_pb_block(data, 0, frame_type)

    def _parse_pb_and_mac_header(self, data: bytes, base_offset: int, dt: int) -> List[Tuple]:
        """fc_mac 模式：解析 PBH + MAC帧头"""
        table = []
        if not data or dt == 2:
            return table
        # 先取第一个PB
        if len(data) < 2:
            return table
        pbh = data[0]
        table.append((
            "PB头",
            f"0x{pbh:02X}",
            f"seq={pbh & 0x3F}",
            f"序列号:{pbh & 0x3F} 起始:{(pbh>>6)&1} 结束:{(pbh>>7)&1}",
            base_offset, base_offset,
        ))
        # MAC帧头
        if len(data) > 1:
            mac_data = data[1:]
            hdr_len, mac_table = self._parse_mac_header(mac_data, base_offset + 1)
            table.extend(mac_table)
        return table
