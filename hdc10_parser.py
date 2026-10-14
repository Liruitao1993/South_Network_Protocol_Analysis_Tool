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

# 应用层报文的 MSDU 类型值域（单一来源）：表10 标准MAC头=48(0x30)，
# 表13 单跳帧头=128(0x80)。值是用 MAC 头类型字段判「是否应用层」的唯一依据，
# 首字节启发式只作无 MAC 头上下文(msdu_type=None)时的回退。
APP_MSDU_TYPES = frozenset({48, 128})

# IP 报文的 MSDU 类型值域：表10 标准MAC头=49(0x31)，表13 单跳帧头=129(0x81)
IPV4_MSDU_TYPES = frozenset({49, 129})

# 报文端口号
APP_PORTS = {
    0x11: "普通业务(抄表/校时/事件/注册等)",
    0x12: "升级业务",
    0x1A: "鉴权安全",
}

# 无 PBH 物理块的探测阈值（见 HDC10Parser._probe_pb_form）：
# 必要条件「MSDU 长度合理」+「MSDU 类型已知」各 1 分；
# 强证据「应用层端口/报文ID 命中」或「ICV 自校验通过」各 2 分。
# 达阈值才判该 PB 省略了 PBH，否则维持原判（防末尾 PB 被误判）。
_PB_PROBE_MIN_SCORE = 4

# FCCS **留空**（全 0）时的结构判定阈值（见 HDC10Parser._looks_like_fc_payload）。
# 台体/模拟器把报文内容组好直接落日志，FCCS/PBCS/ICV 由硬件发射机在发射时
# 填校验，日志里留空为全 0；此时不能再拿「校验不过」当「不是完整 MPDU」。
# 复用 _probe_pb_form 的打分（同一把尺子），要求「MSDU 长度/类型合理」之外
# 至少再有一条强证据（应用层端口/报文ID 命中 或 ICV 自校验通过）。
_FC_BLANK_FCCS_MIN_SCORE = _PB_PROBE_MIN_SCORE

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

# ── 通信测试命令(0x006)「检测扩展命令」：测试模式/配置操作 ───────────────
#
# 依据：A-HS-11-03《国网双模通信测试用例提案》1.2 节 表2（转换稿见
# ``协议文档/11.HDC协议/A-HS-11-03 国网双模通信测试用例提案_20210414.md``）。
# 规范表32 的通信测试下行报文里，字节1 高4位是「保留」、字节2 高4位+字节3 是
# 「转发数据长度(12bit)」；测试场景下这两处被扩展为「测试模式/配置操作」与
# 「模式持续时间/配置值」。测试模式=0 即未扩展（普通通信测试，走表32 原义）。
#
# 注：协议10（gw_new_gen_cmd_payloads._EXT_TEST_MODES）与协议9
# （csg_new_gen_cmd_payloads._LEGACY_TEST_MODE_MAP）各有一份同内容表，
# 改本表时三处需同步。
EXT_TEST_MODES = {
    1: "转发应用层报文至应用层串口信道测试模式(暂未使用)",
    2: "转发应用层报文至载波信道测试模式(暂未使用)",
    3: "HPLC物理层透传测试模式",
    4: "HPLC物理层回传测试模式",
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

# 安全测试模式（字节4 低4位，仅测试模式=13 生效；表2 第9条：≠13 时应为0）
EXT_SEC_MODES = {
    1: "SHA256算法测试", 2: "SM3算法测试",
    3: "ECC签名测试", 4: "ECC验签测试",
    5: "SM2签名测试", 6: "SM2验签测试",
    7: "AES-CBC加密测试", 8: "AES-CBC解密测试",
    9: "AES-GCM加密测试", 10: "AES-GCM解密测试",
    11: "SM4-CBC加密测试", 12: "SM4-CBC解密测试",
}

# 频段切换操作（测试模式=6）的目标频段取值（表2 第6条原文）
EXT_BAND_RANGES = {
    0: "通信频段0（1.953~11.96MHz）",
    1: "通信频段1（2.441~5.615MHz）",
    2: "通信频段2（0.781~2.930MHz）",
    3: "通信频段3（1.758~2.930MHz）",
}

# 模式持续时间上限（表2 注意事项第10条：超过则限定到最大时长）
EXT_MAX_DURATION_MIN = 60

# ── 事件上报(0x008) 数据域：STA上报事件类型 ────────────────────────────
#
# 1/2 位图方式（停电/上电）与 3/4 地址方式（停电/上电）出自 HDC 第4-3部分
# 表30 / 表31；51 出自 A-HS-11-03 附件3《Q/GDW 11612.43 协议扩增》
# （2024年第二批HDC模块即装即采增补协议要求，山东）。
EVENT_TYPES = {
    1: ("停电事件（位图方式）", "bitmap"),
    2: ("上电事件（位图方式）", "bitmap"),
    3: ("停电事件（地址方式）", "addr"),
    4: ("上电事件（地址方式）", "addr"),
    51: ("设备信息（上报下挂设备）", "device"),
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

# 规范表2 列出、但第4-3部分**未给出字段格式定义**的业务ID。
# 依据（已全文核实 HDC 第1/4-1/4-2/4-3 部分）：`鉴权安全`(0x00A0)、`配电信息上报`(0x00A4)
# 仅出现在「表2 报文ID」与「应用层报文优先级表」，规范无其字段格式章节
# → 只能报业务名 + 原始数据，不得臆造字段。
# 注：本表是**规范文档事实**的显式建模，不是分派链的第二份清单——哪个「端口+业务ID」
# 组合有解析由 _parse_app_payload 的 if/elif 链权威决定，本表只影响 fallback 的措辞。
MSG_ID_NO_FORMAT_DEFINED = frozenset({0x0A0, 0x0A4})


# ── CRC 工具 ──────────────────────────────────────────────────────

def _crc24(data: bytes) -> int:
    """CRC-24 (poly 0x800063, 反射模式, init=0, xorOut=0)

    纯 Python 回退与 crcmod.mkCrcFun(0x1800063, initCrc=0, rev=True, xorOut=0)
    结果一致(4000 组随机数据 + 真实帧 FCCS 双重验证)。反射算法须用多项式
    0x800063 的 24 位位反转值 0xC60001；旧代码 `0x800063 >> 1` 因 >> 优先级
    高于 ^ 实际等价于 0x400031, 结果错误——未安装 crcmod 时 FCCS/PBCS 校验
    全部失败, _detect_fc 会把信标帧误判为无 FC 的裸 MAC 帧。
    """
    if _CRC24_FUN is not None:
        return _CRC24_FUN(data)
    # 纯Python回退: 反射多项式 = 0x800063 的 24 位位反转
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xC60001
            else:
                crc >>= 1
    return crc & 0xFFFFFF


def _crc32(data: bytes) -> int:
    """CRC-32 (IEEE 802.3, 与zlib一致)"""
    return zlib.crc32(data) & 0xFFFFFFFF


def _ascii_text(buf: bytes) -> str:
    """ASCII 字段解码（非 ASCII 字节按原样以 hex 展示，不抛异常）"""
    try:
        text = buf.decode("ascii")
    except UnicodeDecodeError:
        return " ".join(f"{b:02X}" for b in buf)
    return text if text.isprintable() else " ".join(f"{b:02X}" for b in buf)


def _bits_lsb(data: bytes, byte_off: int, bit_off: int, nbits: int) -> int:
    """按规范各表的「字节号 / 比特位」列读跨字节位域（**位号小的一端是低位**）。

    规范把跨字节字段写成「字节N 比特0-7」+「字节N+1 比特0-3」这类形式，含义是
    **LSB-first 位流**：位号小的比特是该字段的低位。同字节内的单比特标志已由
    实测实证同一口径——SOF 帧 `0x42` 的「广播标志位=比特1」→ ``(0x42>>1)&1 = 1``
    且该帧目的TEI 确为广播地址 4095；「分集拷贝基本模式=比特4-7」→ ``4`` 且该帧
    物理块恰为 136 字节（模式4 = 136B）。

    **不能**按「首字节=高位」组装：现场帧 ``02 F0 FF`` 的源TEI 曾被解成 32，
    而正确值是 2（与该帧 MAC 头「原始源TEI」一致）。

    Args:
        data: 帧字节；byte_off: 字段起始字节；bit_off: 起始字节内的起始比特号；
        nbits: 字段位宽。
    """
    value = 0
    for i in range(nbits):
        pos = byte_off * 8 + bit_off + i
        if pos >> 3 >= len(data):
            break
        if data[pos >> 3] & (1 << (pos & 7)):
            value |= 1 << i
    return value


def _bit_slice(byte_val: int, hi: int, lo: int) -> int:
    """取**单字节内**的位段（闭区间位号，bit0 为最低位；口径同 ``_bits_lsb``）。

    规范各表把字段写成「字节N 比特a-b」，表格上只给十进制值看不出落在哪几位、
    也看不出跨字节字段是怎么拼的，故用它把取值摆到说明列。
    """
    return (byte_val >> lo) & ((1 << (hi - lo + 1)) - 1)


def _bit_span_note(*spans: Tuple[int, int, int, int]) -> str:
    """拼「位域归属」片段，追加到说明列（把 bit 占用摆到台面上）。

    Args:
        spans: 依次给 ``(报文头内字节号, 高比特位, 低比特位, 该字节原值)``，
            **按该字段在规范表里的书写顺序**（通常字节号升序）。跨字节位域的
            打包口径本协议只有一种：「**字节号小的段是低位段**」（口径同
            ``_bits_lsb``；12bit「转发数据长度/配置值」、6bit「报文头长度」皆如此），
            故多段时末尾直接给出移位拼装式，方向不用读者自己猜。
    """
    parts = []
    widths = []
    values = []
    for byte_no, hi, lo, byte_val in spans:
        width = hi - lo + 1
        value = _bit_slice(byte_val, hi, lo)
        widths.append(width)
        values.append(value)
        parts.append(
            f"报文头字节{byte_no}[bit{hi}-{lo}]={width}bit=0b{value:0{width}b}"
        )
    note = "；位域归属: " + " + ".join(parts)
    if len(spans) > 1:
        shifts = []
        acc = 0
        for width in widths:
            shifts.append(acc)
            acc += width
        expr = " | ".join(
            f"0b{v:0{w}b}" + (f"<<{s}" if s else "")
            for v, w, s in zip(values, widths, shifts)
        )
        total = sum(v << s for v, s in zip(values, shifts))
        note += f"（低位段在前）→ {expr} = {total}"
    return note


# 应用报文头前两字节的位布局（表2/表32/表3/表26/表37 等各应用报文头一致）：
#   字节0: 协议版本号(bit0-5, 6bit) | 报文头长度低2位(bit6-7)
#   字节1: 报文头长度高4位(bit0-3) | 该报文自有语义(bit4-7)
# 口径：字节号小的段是低位段（同 _bits_lsb，也与 12bit「转发数据长度/配置值」一致）。


def _hdr_len_cells(b0: int, b1: int, hdr_len: int) -> Tuple[str, str]:
    """「报文头长度」行的 (原始值, 说明) 两列。

    ``报文头长度`` 是**跨字节位域**：字节0 的 bit7-6 是**低 2 位**、字节1 的 bit3-0
    是**高 4 位**，拼出的 6bit 数值就是**报文头的字节数**（不是 4 字节字）。表格若
    只给「4 字节」，就看不出这个 4 是从哪两个字节的哪几位拼出来的，故：

      - 原始值列给两个位段的二进制（``0b0001+0b10``，``+`` = 按位拼接，直接可读为数值）；
      - 说明列给字节/比特归属与移位拼装式 + 单位口径（报文头字节数）。
    """
    low2 = _bit_slice(b0, 7, 6)
    high4 = _bit_slice(b1, 3, 0)
    return (
        f"0b{high4:04b}+0b{low2:02b}",
        "位域6bit（字节号小的段是低位段）"
        + _bit_span_note((0, 7, 6, b0), (1, 3, 0, b1))
        + f"；单位 字节，报文头长度 = {hdr_len} 字节",
    )


# ── 帧类型/协议归属的**证据判定**（自动识别用，纯函数）────────────────

# detect_hdc_frame_kind 复用解析器做 MAC 头长度判定（无状态，仅调用纯解析方法）
_KIND_PROBE_PARSER = None


def looks_like_hdc_fc(data: bytes) -> bool:
    """输入是否 HDC 1.0 的 MPDU 帧控制(FC)：定界符0~3 + 网络类型0 + 标准版本号0 + FCCS 校验通过。

    这是**互斥证据**，不只是「像」：
      - 南网新一代(CSG) 的 FC 低4位为 0x8~0xB（bit3=接入指示=1），其
        ``(b0 >> 3) & 0x1F`` 恒 ≥ 1 → 被「网络类型=0」排除；
      - 协议10 的 HDC 2.0 帧标准版本号非 0 → 被「标准版本号=0」排除；
      - FCCS 是 CRC-24 校验（对前 13 字节），误判概率 1/2^24。
    实测 TMI 真实日志 1305 个 ED 包装帧的业务帧全部命中本判据（dt=0/1/2/3 四类齐全）。
    """
    if len(data) < 16:
        return False
    if (data[0] & 0x07) > 3:            # 定界符类型 = 信标/SOF/SACK/网间协调
        return False
    if ((data[0] >> 3) & 0x1F) != 0:    # 网络类型 = 用电信息采集系统（表15）
        return False
    if ((data[12] >> 4) & 0x0F) != 0:   # 标准版本号 = 0（HDC 1.0 本标准）
        return False
    return _crc24(data[:13]) == int.from_bytes(data[13:16], "little")


def detect_hdc_frame_kind(data: bytes) -> str:
    """判定输入属于哪一类 HDC 帧（自动识别用），返回：

      ``"fc"``  —— MPDU（FC 校验通过）：信标帧 / SOF 帧 / 选择确认帧(SACK) / 网间协调帧
      ``"mac"`` —— MAC 帧（标准 16/28B 或单跳 4B 头，MSDU 长度自洽、MSDU 类型已知）
      ``"app"`` —— 应用层报文（首字节命中应用层端口号表）
      ``""``    —— 无 HDC 证据

    用于「自动识别协议」时给候选解析器排序：拿到 ``fc``/``mac``/``app`` 证据说明
    输入确定是国网双模帧，应先按 HDC/国网新一代解析，而不是被南网新一代的宽松
    启发式先行接管（实测 TCP 监控下四类 HDC 帧全部被误判为南网新一代）。
    """
    if len(data) < 4:
        return ""
    if looks_like_hdc_fc(data):
        return "fc"
    if data[0] in APP_PORTS:
        return "app"
    ver = data[0] & 0x0F
    if ver not in (0, 1):
        return ""
    global _KIND_PROBE_PARSER
    if _KIND_PROBE_PARSER is None:
        _KIND_PROBE_PARSER = HDC10Parser()
    hdr_len, _rows = _KIND_PROBE_PARSER._parse_mac_header(data, 0)
    if ver == 1:
        if hdr_len != 4 or len(data) < 8:
            return ""
        msdu_type = data[1]
        msdu_len = (data[2] << 3) | (data[3] & 0x07)
    else:
        if hdr_len not in (16, 28) or len(data) < hdr_len + 4:
            return ""
        msdu_type = data[7]
        msdu_len = data[8] | ((data[9] & 0x07) << 8)
    # MSDU 长度必须与剩余字节自洽（MAC头 + MSDU + ICV(4B)）
    if not 0 < msdu_len <= len(data) - hdr_len - 4:
        return ""
    if msdu_type in APP_MSDU_TYPES or msdu_type in IPV4_MSDU_TYPES or msdu_type == 0:
        return "mac"
    return ""


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
        # ED..EE 监控封装头声明的 PB 大小/个数（parse_to_table kwargs 注入）
        self._pb_size_hint = None
        self._pb_count_hint = None

    # ─── 主入口 ────────────────────────────────────────────────

    def parse_to_table(self, frame_bytes: bytes, parse_level: str = "auto",
                       **kwargs) -> List[Tuple]:
        """
        主入口：解析帧为表格数据

        parse_level:
          auto    - 自动识别，完整解析
          fc_pb   - 解析 FC + 完整物理块 PB
          fc_only - 仅解析帧控制 FC
          mac_only- 仅解析 MAC 帧（输入即 MAC 帧，不含 PBH，从字节0解析）
          pb_only - 仅解析物理块 PB，需 frame_type
          fc_mac  - 解析 FC + PBH + MAC 帧头
          app     - 仅解析应用层报文

        kwargs:
          channel: "plc"（默认）/ "hrf" —— 决定 FC 可变区域按载波表还是无线表解析
          frame_type: pb_only 的帧类型（0=信标 1=SOF 2=SACK 3=网间协调）
          pb_size / pb_count: **ED..EE 监控封装头声明的物理块大小与个数**（可选）。
            多 PB 聚合帧据此做确定性切分（切分前逐块校验 PBH 序列号与起止标志，
            校验不过则回落启发式扫描），见 ``_split_pb_by_hint``。
        """
        self._channel = kwargs.get('channel', 'plc')
        frame_type = kwargs.get('frame_type', 1)  # 默认SOF
        self._pb_size_hint = kwargs.get('pb_size')
        self._pb_count_hint = kwargs.get('pb_count')
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
        # 用户显式声明「完整 MPDU」（fc_pb / fc_mac）时尊重声明：级别名即契约，
        # 不因 FCCS 校验不过就偷偷改走 MAC 帧路径（那会吐一屏错位臆造）。
        # 只对 **SOF 帧** 放开：信标/SACK/网间协调帧的 FC 之后不是「PBH+MAC」布局，
        # 而开头为 PBH 的物理块帧（0x40/0xC0）其 byte0 低 3 位同样是 0，
        # 按 DT 全放开会把 PB 级输入劫持进 FC 路径（回归实测：夹具帧结果全变）。
        # 末条是规范硬条件（表37）：完整 MPDU 的偏移 16 必是**置了帧起始位**的首块
        # PBH——首块不带帧起始标志即自相矛盾。裸 PB 输入的 frame_bytes[16] 落在
        # MAC 头/MSDU 体内（实测 60 条夹具里唯一低 3 位为 1 的 0xC1 帧，其
        # frame_bytes[16]=0x06 无帧起始位），据此把 PB 级输入挡在外面。
        forced_fc = False
        if (
            not has_fc
            and parse_level in ("fc_pb", "fc_mac")
            and flen >= 26
            and (frame_bytes[0] & 0x07) == 1
            and ((frame_bytes[12] >> 4) & 0x0F) == 0
            and ((frame_bytes[16] >> 6) & 0x01) == 1
        ):
            has_fc = True
            forced_fc = True

        if not has_fc:
            # 无 FC，尝试按 MAC 帧解析
            if self._detect_mac_header(frame_bytes):
                return self._parse_mac_only(frame_bytes, frame_type)
            # 信标启发式：DT=0 且 HDC1.0 版本位，FCCS 失败时仍按 FC+信标载荷解析
            # （ED 监控解包后的业务帧可能因帧长/填充导致 FCCS 对不上，但 DT=0 是信标）
            if (
                flen >= 20
                and (frame_bytes[0] & 0x07) == 0
                and ((frame_bytes[12] >> 4) & 0x0F) == 0
            ):
                table = self._parse_fc(frame_bytes, 0)
                table.append((
                    "⚠ 推测信标帧",
                    "",
                    "DT=0",
                    "FCCS 未通过或未检出完整 MPDU，按信标帧(FC+信标载荷)解析",
                    None, None,
                ))
                if flen > 16:
                    table.extend(self._parse_pb_block(frame_bytes[16:], 16, 0))
                return table
            # 尝试按应用层解析
            return self._parse_app_only(frame_bytes)

        # 有 FC
        fc_table = self._parse_fc(frame_bytes, 0)
        table.extend(fc_table)

        # FCCS 未通过仍按 FC 解析时，把依据写明——台体/模拟器日志把校验位留空为
        # 全 0（发射时由硬件填充）是现场常态，不能让用户以为解析器在瞎猜。
        _fccs_stored = int.from_bytes(frame_bytes[13:16], 'little')
        if _crc24(frame_bytes[:13]) != _fccs_stored:
            if _fccs_stored == 0:
                _why = ("FCCS 留空(全 0)：校验位由硬件发射机在发射时填充，"
                        "台体/模拟器输出的日志帧常见")
            else:
                _why = (f"FCCS 有值但校验不过(计算值=0x{_crc24(frame_bytes[:13]):06X})")
            table.append((
                "⚠ FCCS 未通过",
                ' '.join(f'{b:02X}' for b in frame_bytes[13:16]),
                f"0x{_fccs_stored:06X}",
                _why + ("；按指定的「完整MPDU」级别继续解析" if forced_fc
                        else "；帧体结构自洽，按完整 MPDU 继续解析"),
                None, None,
            ))

        if parse_level == "fc_only":
            return table

        if flen <= 16:
            return table

        # 获取定界符类型
        dt = frame_bytes[0] & 0x07

        if dt == 2:  # SACK帧无载荷（选择确认帧只有 FC）
            return table

        if dt == 3:
            # 网间协调帧：表26 只定义 FC 可变区域，无物理块载荷。
            # 真实抓包常在 FC 后带填充/冗余字节 → 只提示，**禁止**按 SOF 的 PB 解析
            # （否则 PBH/序列号等字段全是错位臆造）。
            extra = frame_bytes[16:]
            if extra:
                table.append((
                    "  尾部数据",
                    ' '.join(f'{b:02X}' for b in extra),
                    f"{len(extra)}字节",
                    "网间协调帧不含物理块载荷（超出 FC 16字节的部分按填充/冗余展示）",
                    16, len(frame_bytes) - 1,
                ))
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
        """检测是否为完整MPDU帧（含16字节FC头）

        判据：
          1. 定界符 0~3、标准版本号 0（HDC 1.0）；
          2. FCCS 校验通过 → 确定性完整 MPDU；
          3. FCCS **留空（全 0）** → 改判帧体结构，见 ``_looks_like_fc_payload``；
          4. FCCS 有值但校验不过 → 不是 MPDU（保持严格，防误判）。
        """
        if len(data) < 16:
            return False
        dt = data[0] & 0x07
        if dt > 3:
            return False
        # 标准版本号应为0（HDC 1.0）
        std_ver = (data[12] >> 4) & 0x0F
        if std_ver != 0:
            return False
        # FCCS校验
        fc_body = data[:13]
        fccs = int.from_bytes(data[13:16], 'little')
        calc = _crc24(fc_body)
        if calc == fccs:
            return True
        if fccs != 0:
            return False
        # FCCS 留空（全 0）：台体/模拟器日志里校验位由硬件发射机填充 →
        # 不能拿「校验不过」当「不是 MPDU」，改判帧体结构。
        return self._looks_like_fc_payload(data)

    def _looks_like_fc_payload(self, data: bytes) -> bool:
        """FCCS 留空（全 0）时，改用帧体结构判定「FC(16B) + 物理块」是否成立。

        背景：台体/模拟器把报文内容组好直接落日志，FCCS/PBCS/ICV 由硬件发射机
        在发射时填充，日志里留空为全 0。此时若仍以 FCCS 为唯一判据，整帧会掉进
        「无 FC → 按裸 MAC 帧解析」分支，吐一屏错位臆造（版本=1 单跳帧协议、
        MSDU长度=0、ICV 取值错位且校验失败）。

        只对 **SOF 帧（DT=1）** 生效，不做泛化：信标帧 FC 之后是信标载荷而非
        PBH，而开头为 PBH（0x40/0xC0）的物理块帧其 byte0 低 3 位同样是 0，
        按 DT=0 统一放开会把 PB 级输入误判成信标帧。

        判据（全部满足）：
          S1 ``data[16]`` 是合法 PBH 且置了**帧起始**位（首块不带帧起始标志即自相矛盾）；
          S2 ``data[17:]``（PBH 之后即 MAC 帧头）按 ``_probe_pb_form`` 打分
             ≥ ``_FC_BLANK_FCCS_MIN_SCORE``，即「MSDU 长度/类型合理」之外还必须
             至少再有一条强证据（应用层端口/报文ID 命中 或 ICV 自校验通过）。

        防误判标定（实测依据）：真实单 PB 现场帧 44 条（``test/hdc10_real_frames.pkl``）
        若被误当「FC 在偏移 0」来解，``data[17:]`` 打分分布为 {0: 28, 1: 16}
        （最高 1）；而真实 FC 帧（台体 152 字节日志帧）打分 6 → 阈值 4 余量充足。
        """
        if len(data) < 26:
            return False
        if (data[0] & 0x07) != 1:
            return False
        if not (data[16] >> 6) & 0x01:
            return False
        _pbh_len, score = self._probe_pb_form(data[17:])
        return score >= _FC_BLANK_FCCS_MIN_SCORE

    def _detect_mac_header(self, data: bytes) -> bool:
        """检测是否为MAC帧起始（裸MAC 或 PBH+MAC）"""
        if len(data) < 4:
            return False
        ver = data[0] & 0x0F
        if ver in (0, 1):
            return len(data) >= 16 if ver == 0 else True
        # PBH 前缀(表37: bit7=帧结束,bit6=帧起始): 起始PB 后跟 MAC头
        if (data[0] >> 6) & 0x03:  # sof/eof 至少一个置位
            inner = data[1:]
            if len(inner) >= 16 and (inner[0] & 0x0F) in (0, 1):
                return True
        return False

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
        if calc_fccs == fccs:
            status = "✓ 校验正确"
        elif fccs == 0:
            # 台体/模拟器把报文内容组好直接落日志，校验位由硬件发射机填充
            status = ("⚠ 未填充(全 0)：台体/模拟器日志由硬件发射机在发射时填校验，"
                      f"此处计算值应为 0x{calc_fccs:06X}")
        else:
            status = f"✗ 校验错误(计算值=0x{calc_fccs:06X})"
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
            elif dt == 3:  # 网间协调帧（表26）
                table = self._parse_fc_vf_net(data, offset, "plc")
        else:  # hrf
            if dt == 0:
                table = self._parse_fc_vf_beacon_hrf(data, offset)
            elif dt == 1:
                table = self._parse_fc_vf_sof_hrf(data, offset)
            elif dt == 2:
                table = self._parse_fc_vf_sack_hrf(data, offset)
            elif dt == 3:
                # 规范 5.1.2.8「无线可变区域」（表27~36）未定义网间协调帧，
                # 只有 5.1.2.7（载波）给出表26 → 按表26 解释并显式标注依据
                table = self._parse_fc_vf_net(data, offset, "hrf")

        return table

    def _parse_fc_vf_net(self, data: bytes, offset: int, channel: str) -> List[Tuple]:
        """网间协调帧可变区域（表26，规范 5.1.2.7「载波可变区域」）

        表26 字段（跨字节位域按 LSB-first 读，见 ``_bits_lsb``）：
          持续时间(字节4-5, 16bit, 单位1ms) / 带宽开始偏移(字节6-7, 16bit, 单位1ms) /
          接收到的邻居网络号(字节8-10, 24bit) / 本网络无线信道编号(字节11, 8bit) /
          保留(字节12 比特0-3) —— 保留位不单列行（与表17/19/23 的既有风格一致）。

        ``channel="hrf"`` 时规范无对应表，仍按表26 解释并附「依据」行说明，
        不臆造无线专有字段（试验证：真实帧的本网络无线信道编号与同网络信标一致）。
        """
        table = []
        base = offset

        duration = _bits_lsb(data, offset + 4, 0, 16)
        table.append((
            "  持续时间",
            f"0x{duration:04X}",
            f"{duration}ms",
            "本网络需要申请占用的时隙长度（单位1ms）",
            base + 4, base + 5,
        ))

        bw_start = _bits_lsb(data, offset + 6, 0, 16)
        table.append((
            "  带宽开始偏移",
            f"0x{bw_start:04X}",
            f"{bw_start}ms",
            "下个带宽时隙开始时刻的时间偏移（单位1ms）；该时隙已开始时取0",
            base + 6, base + 7,
        ))

        neighbor_nid = _bits_lsb(data, offset + 8, 0, 24)
        table.append((
            "  接收到的邻居网络号",
            ' '.join(f'{b:02X}' for b in data[offset + 8:offset + 11]),
            str(neighbor_nid),
            "能够接收到邻居网络的网络号(NID)；每次只携带一个，多次发送后拼出邻居网络集",
            base + 8, base + 10,
        ))

        ch_no = data[offset + 11]
        table.append((
            "  本网络无线信道编号",
            f"0x{ch_no:02X}",
            str(ch_no),
            "告知邻居网络本网络使用的无线信道编号",
            base + 11, base + 11,
        ))

        if channel != "plc":
            table.append((
                "  依据",
                "",
                "表26(载波)",
                "规范第4-2部分 5.1.2.8「无线可变区域」(表27~36) 未定义网间协调帧，"
                "此处按 5.1.2.7 表26 解释",
                base + 4, base + 11,
            ))

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

        # 源TEI: 字节4 比特0-7(低8位) + 字节5 比特0-3(高4位) = 12bit（表19，LSB-first 位流）
        src_tei = _bits_lsb(data, offset + 4, 0, 12)
        table.append((
            "  源TEI",
            f"0x{src_tei:03X}",
            str(src_tei),
            "源站点TEI",
            base + 4, base + 5,
        ))

        # 目的TEI: 字节5 比特4-7(低4位) + 字节6 比特0-7(高8位) = 12bit（表19）
        dst_tei = _bits_lsb(data, offset + 5, 4, 12)
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

        # 帧长: 字节8 比特0-7(低8位) + 字节9 比特0-3(高4位) = 12bit, 单位10us（表19）
        frame_len = _bits_lsb(data, offset + 8, 0, 12)
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

        # 符号数: 字节10 比特0-7(低8位) + 字节11 比特0(高1位) = 9bit（表19）
        sym_count = _bits_lsb(data, offset + 10, 0, 9)
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

        # 源TEI: 字节8 比特0-7(低8位) + 字节9 比特0-3(高4位) = 12bit（表27）
        src_tei = _bits_lsb(data, offset + 8, 0, 12)
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

        # 符号数: 字节10 比特0-7(低8位) + 字节11 比特0(高1位) = 9bit（表27）
        sym_count = _bits_lsb(data, offset + 10, 0, 9)
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

        # 源TEI: 字节8 比特0-7(低8位) + 字节9 比特0-3(高4位) = 12bit（无线信标表）
        src_tei = _bits_lsb(data, offset + 8, 0, 12)
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

        # 源TEI: 字节5 比特0-7(低8位) + 字节6 比特0-3(高4位) = 12bit（表23）
        src_tei = _bits_lsb(data, offset + 5, 0, 12)
        table.append((
            "  源TEI",
            f"0x{src_tei:03X}",
            str(src_tei),
            "发送SACK的站点TEI",
            base + 5, base + 6,
        ))

        # 目的TEI: 字节6 比特4-7(低4位) + 字节7 比特0-7(高8位) = 12bit（表23）
        dst_tei = _bits_lsb(data, offset + 6, 4, 12)
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

        # 源TEI: 字节4 比特0-7(低8位) + 字节5 比特0-3(高4位) = 12bit（表30）
        src_tei = _bits_lsb(data, offset + 4, 0, 12)
        table.append(("  源TEI", f"0x{src_tei:03X}", str(src_tei), "源站点TEI", base + 4, base + 5))

        # 目的TEI: 字节5 比特4-7(低4位) + 字节6 比特0-7(高8位) = 12bit（表30）
        dst_tei = _bits_lsb(data, offset + 5, 4, 12)
        table.append(("  目的TEI", f"0x{dst_tei:03X}", str(dst_tei), "目的站点TEI", base + 5, base + 6))

        # 链路标识符
        table.append(("  链路标识符(LID)", f"0x{b7:02X}", str(b7), "优先级/业务分类", base + 7, base + 7))

        # 帧长: 字节8 比特0-7(低8位) + 字节9 比特0-3(高4位) = 12bit, 单位100us（表30）
        frame_len = _bits_lsb(data, offset + 8, 0, 12)
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

        # 源TEI(表34: 字节5 比特0-7 + 字节6 比特0-3) / 目的TEI(字节6 比特4-7 + 字节7 比特0-7)
        src_tei = _bits_lsb(data, offset + 5, 0, 12)
        dst_tei = _bits_lsb(data, offset + 6, 4, 12)
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

            # PB体 = MAC帧 = MAC头 + MSDU + ICV, 紧跟 PBH 之后(无保留字节)
            # PBCS在末尾3字节
            if len(data) > 20:
                # PBCS 存在性检测: 尾3B 若为合法 CRC-24(PBH+PB体) 则有 PBCS;
                # 否则视为日志截断/无PBCS帧, 全部剩余数据归 MAC 帧(尾4B 为 ICV)
                tail3 = int.from_bytes(data[-3:], 'little')
                has_pbcs = (_crc24(data[:-3]) == tail3)

                pb_body = data[1:-3] if has_pbcs else data[1:]
                mac_table = self._parse_mac_frame(pb_body, base_offset + 1)
                table.extend(mac_table)

                if has_pbcs:
                    table.append((
                        "  PBCS",
                        ' '.join(f'{b:02X}' for b in data[-3:]),
                        f"0x{tail3:06X}",
                        "✓ 校验正确",
                        base_offset + len(data) - 3, base_offset + len(data) - 1,
                    ))
                elif tail3 == 0:
                    table.append((
                        "  ⚠ PBCS未填充",
                        ' '.join(f'{b:02X}' for b in data[-3:]),
                        "全 0",
                        "尾部3字节为全 0 → PBCS 未填充（台体/模拟器日志由硬件发射机"
                        "在发射时填校验），已并入MAC帧解析",
                        base_offset + len(data) - 3, base_offset + len(data) - 1,
                    ))
                else:
                    table.append((
                        "  ⚠ 无PBCS",
                        ' '.join(f'{b:02X}' for b in data[-3:]),
                        "CRC-24不匹配",
                        "尾部3字节非合法PBCS(日志截断或无PBCS格式), 已并入MAC帧解析",
                        base_offset + len(data) - 3, base_offset + len(data) - 1,
                    ))
        elif sof and not eof:
            # 多PB聚合的首块 - 需要重组
            # 优先用 ED 监控封装头声明的 PB 大小/个数做确定性切分（逐块校验 PBH），
            # 声明缺失或校验不过时回落启发式扫描
            pb_list = self._split_pb_by_hint(data) or self._scan_all_pb(data)
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
            # 不是SOF帧起始（中间PB或末尾PB）
            # 先探测该 PB 是否**省略了 PBH**（PB体直接以 MAC 帧头起始）：
            # 规范（HDC 1.0 表37 / HDC 2.0 表21）要求每 PB 必含 PBH，但现场存在
            # 无 PBH 的 PB；硬按 PBH 解析会整体错位 1 字节，只剩「非帧起始PB，
            # 原始数据」——与协议10 同帧结果不一致。判据见 _probe_pb_form。
            pbh_len, probe_score = self._probe_pb_form(data)
            if pbh_len == 0:
                table.append((
                    "物理块(PB) - 未检测到合法物理块头",
                    '',
                    f"{len(data)}字节",
                    f"data[0]=0x{data[0]:02X} 不满足 PBH 判据(帧起始/帧结束位均为0、"
                    f"PBCS 不匹配)；按「PB体直接起始于 MAC 帧头」解析(探测得分 {probe_score})",
                    base_offset, base_offset,
                ))
                table.extend(self._parse_mac_frame(data, base_offset))
                tail3 = int.from_bytes(data[-3:], 'little')
                has_pbcs = (len(data) > 3 and _crc24(data[:-3]) == tail3)
                table.append((
                    "  PBCS",
                    ' '.join(f'{b:02X}' for b in data[-3:]),
                    f"0x{tail3:06X}",
                    "✓ 校验正确" if has_pbcs else
                    "无 PBCS（尾3字节非合法 CRC-24，可能为日志填充）",
                    base_offset + len(data) - 3, base_offset + len(data) - 1,
                ))
            else:
                table.append((
                    "物理块数据(部分)",
                    ' '.join(f'{b:02X}' for b in data[:20]) + ("..." if len(data) > 20 else ""),
                    f"{len(data)}字节",
                    "非帧起始PB，原始数据",
                    base_offset, base_offset + min(len(data), 20) - 1,
                ))

        return table

    def _probe_pb_form(self, data: bytes) -> Tuple[int, int]:
        """探测物理块形态，返回 (pbh_len, score)。

        pbh_len：0 = 检测到「无 PBH」（PB体直接以 MAC 帧头起始）；1 = 按有 PBH 处理。

        背景：规范（HDC 1.0 表37 / HDC 2.0 表21）规定 PB = PBH(1B) + PB体 + PBCS(3B)，
        每块必含 PBH；但现场存在**无 PBH** 的 PB。硬按 PBH 解析会让 MAC 头整体错位
        1 字节（MSDU 类型/长度荒谬、端口与报文ID 全错），最终只剩「非帧起始PB，
        原始数据」，且与协议10 同帧结果不一致。

        判据（必要条件 + 强证据，不足则判「有 PBH」）：
          必要条件
            C2 MSDU 长度合理：0 < msdu_len <= 剩余长度 - 4(ICV)
            C3 MSDU 类型在已知集合（APP_MSDU_TYPES / IPV4_MSDU_TYPES / 0=管理类）
          强证据（各 2 分，至少一条）
            C5 应用层端口命中 APP_PORTS，或报文ID 命中 MSG_ID_NAMES
            C6 ICV 自校验：尾部 ICV == crc32(MSDU)，或 ICV 全 0（明文填充）

        判据中的常量一律取自模块既有单一来源，不另立清单。
        """
        if len(data) < 16:
            return 1, 0

        # MAC 版本（标准头=0 / 单跳头=1）；其余值说明 data[0] 不是 MAC 头首字节
        ver = data[0] & 0x0F
        if ver not in (0, 1):
            return 1, 0

        # 头长与 MSDU 类型/长度均与 _parse_mac_frame 同口径
        mac_hdr_len, _ = self._parse_mac_header(data, 0)
        msdu_start = mac_hdr_len
        if mac_hdr_len < 4 or msdu_start >= len(data):
            return 1, 0
        if ver == 0:
            msdu_type = data[7]
            msdu_len = data[8] | ((data[9] & 0x07) << 8)
        else:
            msdu_type = data[1]
            msdu_len = (data[2] << 3) | (data[3] & 0x07)

        score = 0
        if 0 < msdu_len <= len(data) - msdu_start - 4:
            score += 1                                    # C2
            if (msdu_type in APP_MSDU_TYPES or msdu_type in IPV4_MSDU_TYPES
                    or msdu_type == 0):
                score += 1                                # C3
                msdu_end = msdu_start + msdu_len
                if msdu_type in APP_MSDU_TYPES and msdu_len >= 3:
                    port = data[msdu_start]
                    msg_id = int.from_bytes(data[msdu_start + 1:msdu_start + 3], 'little')
                    if port in APP_PORTS or msg_id in MSG_ID_NAMES:
                        score += 2                        # C5
                if msdu_end + 4 <= len(data):
                    icv = int.from_bytes(data[msdu_end:msdu_end + 4], 'little')
                    if icv == 0 or icv == _crc32(data[msdu_start:msdu_end]):
                        score += 2                        # C6

        return (0 if score >= _PB_PROBE_MIN_SCORE else 1), score

    def _split_pb_by_hint(self, data: bytes) -> Optional[List[Tuple[int, int]]]:
        """按 ED 监控封装头声明的 PB 大小/个数**确定性**切分 PB 区域。

        声明值来自包装头的「单个物理块长度 / 物理块个数」（TCP 监控、批量解析路径注入）。
        只在以下条件全部成立时才采信（否则返回 ``None`` 让调用方回落启发式扫描）：

          1. ``pb_size`` ∈ 16..520（规范物理块规格），``pb_count`` ≥ 2（单块无需切分）；
          2. 区域长度恰好 = ``pb_count × pb_size``（真实日志里个数偶尔填 0 → 不采信）；
          3. 每块的 PBH（表37）序列号 = 块序号，且帧起始标志只置在首块、帧结束标志
             只置在末块（这是「切分正确」的自证，错位即判失败）。

        依据：5.1.2.3「物理块头为 1 字节…序列号初始值为 0」+ 表37 帧起始/结束标志。
        """
        pb_size = self._pb_size_hint
        pb_count = self._pb_count_hint
        try:
            pb_size = int(pb_size) if pb_size is not None else 0
            pb_count = int(pb_count) if pb_count is not None else 0
        except (TypeError, ValueError):
            return None
        if not (16 <= pb_size <= 520) or pb_count < 2:
            return None
        if len(data) != pb_size * pb_count:
            return None
        for i in range(pb_count):
            pbh = data[i * pb_size]
            if (pbh & 0x3F) != i:                     # 序列号必须等于块序号
                return None
            if ((pbh >> 6) & 0x01) != (1 if i == 0 else 0):        # 帧起始标志仅首块
                return None
            if ((pbh >> 7) & 0x01) != (1 if i == pb_count - 1 else 0):  # 帧结束标志仅末块
                return None
        return [(i * pb_size, (i + 1) * pb_size) for i in range(pb_count)]

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
                if cand < len(data):
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
            # bcsha_phases 初始化：使用点位于 `if ln > 20:` 的「绑定CSMA时隙信息」循环，
            # 而赋值点在 `if ln >= 7:`（ln > 20 蕴含 ln >= 7）⇒ 运行时必然已赋值，此处
            # 初始化**不改变任何行为**，仅消除静态分析对跨条件数值蕴含的误报
            # （AGENTS.md §8 陷阱 45）。
            bcsha_phases = 0
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

    def _parse_mac_frame(self, data: bytes, base_offset: int,
                         hdr_start: int = 0) -> List[Tuple]:
        """解析完整 MAC 帧（MAC头 + MSDU + ICV）

        hdr_start: MAC头在 data 内的解析起点(默认0)。
        base_offset: 原帧显示偏移(=切片在原帧中的绝对位置)。
        """
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
        mac_header_len, mac_header_table = self._parse_mac_header(data[hdr_start:], 0)
        table.extend(mac_header_table)

        # MSDU类型: 标准头@byte7; 单跳头@byte1(表11/13)
        tpos = hdr_start + (7 if mac_header_len >= 16 else 1)
        msdu_type = data[tpos] if len(data) > tpos else None

        # 从 MAC 头读取 MSDU 长度，用于精确定位 ICV
        # 标准长帧头(版本=0): byte8[0:7] + byte9[0:2] = 11bit 小端
        # 单跳短帧头(版本=1): byte2[0:7] + byte3[0:2] = 11bit
        msdu_len = None
        ver = data[hdr_start] & 0x0F if len(data) > hdr_start else 0
        if ver == 0 and len(data) - hdr_start >= 10:
            b8 = data[hdr_start + 8]
            b9 = data[hdr_start + 9]
            msdu_len = b8 | ((b9 & 0x07) << 8)
        elif ver == 1 and len(data) - hdr_start >= 4:
            b2 = data[hdr_start + 2]
            b3 = data[hdr_start + 3]
            msdu_len = (b2 << 3) | (b3 & 0x07)

        # MSDU + ICV
        msdu_abs = hdr_start + mac_header_len
        if len(data) > msdu_abs:
            msdu_data = data[msdu_abs:]
            table.append((
                "── MSDU + ICV ──",
                "",
                f"{len(msdu_data)}字节",
                "MSDU载荷 + 完整性校验值",
                base_offset + msdu_abs, base_offset + len(data) - 1,
            ))

            # 定位 ICV：优先按 MSDU长度字段定位（帧尾可能有填充/多余数据）
            # ICV = CRC-32(MSDU载荷), 小端, 共 4 字节
            icv_pos = -1  # 在 msdu_data 中的起始偏移
            icv_bytes = b''
            msdu_body = msdu_data
            extra_bytes = b''

            if msdu_len is not None and len(msdu_data) >= msdu_len + 4:
                # 按头中声明的长度精确切割
                icv_pos = msdu_len
                icv_bytes = msdu_data[msdu_len:msdu_len + 4]
                msdu_body = msdu_data[:msdu_len]
                extra_bytes = msdu_data[msdu_len + 4:]
            elif len(msdu_data) >= 4:
                # 回退：取数据最后 4 字节作为 ICV（截断帧 / 无 MSDU 长度字段）
                icv_pos = len(msdu_data) - 4
                icv_bytes = msdu_data[-4:]
                msdu_body = msdu_data[:-4]

            if icv_bytes:
                icv = int.from_bytes(icv_bytes, 'little')
                calc_icv = _crc32(msdu_body)
                if icv == 0:
                    icv_status = "明文填充(ICV=0, 不校验)"
                elif calc_icv == icv:
                    icv_status = "✓ 校验正确"
                else:
                    icv_status = f"✗ 校验错误(计算=0x{calc_icv:08X}, 可能为多PB分片/加密帧)"

                # MSDU解析
                msdu_table = self._parse_msdu_payload(msdu_body, base_offset + msdu_abs,
                                                      msdu_type=msdu_type)
                table.extend(msdu_table)

                table.append((
                    "完整性校验值(ICV)",
                    ' '.join(f'{b:02X}' for b in icv_bytes),
                    f"0x{icv:08X}",
                    icv_status,
                    base_offset + msdu_abs + icv_pos,
                    base_offset + msdu_abs + icv_pos + 3,
                ))

                # 帧尾多余字节（填充/日志噪声）
                # `msdu_len is not None` 显式判断：extra_bytes 仅在其为 None 之外的
                # 分支被赋值（见上文 `if msdu_len is not None and …`）⇒ 运行时必然成立，
                # 显式写出不改变任何行为，仅消除静态分析对跨变量关联的误报
                # （AGENTS.md §8 陷阱 45）。
                if extra_bytes and msdu_len is not None:
                    preview = ' '.join(f'{b:02X}' for b in extra_bytes[:16])
                    if len(extra_bytes) > 16:
                        preview += ' ...'
                    table.append((
                        "  帧尾多余数据",
                        preview,
                        f"{len(extra_bytes)}字节",
                        "MSDU+ICV 之后的多余字节(填充/尾标/日志噪声)",
                        base_offset + msdu_abs + msdu_len + 4,
                        base_offset + len(data) - 1,
                    ))
            else:
                table.append((
                    "MSDU数据",
                    ' '.join(f'{b:02X}' for b in msdu_data),
                    f"{len(msdu_data)}字节",
                    "MSDU载荷(过短，无ICV)",
                    base_offset + msdu_abs, base_offset + len(data) - 1,
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

        # 原始源TEI: byte0[4:7](低4bit) + byte1(高8bit) = 12bit 小端
        src_tei = ((b0 >> 4) & 0x0F) | (b1 << 4)
        table.append((
            "  原始源TEI",
            f"0x{src_tei:03X}",
            str(src_tei),
            "创建报文站点的TEI",
            base, base + 1,
        ))

        # 原始目的TEI: byte2(低8bit) + byte3[0:3](高4bit) = 12bit 小端
        dst_tei = b2 | ((b3 & 0x0F) << 8)
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

        # MSDU长度: 表22 11bit = byte8[0:7]低8b + byte9[0:2]低2b(小端bit序)
        msdu_len = b8 | ((b9 & 0x07) << 8)
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

    def _parse_msdu_payload(self, data: bytes, base_offset: int,
                            msdu_type: Optional[int] = None) -> List[Tuple]:
        """解析MSDU载荷（按类型分发）

        msdu_type: MAC头中的 MSDU类型字段（表10 标准头 / 表13 单跳头）。
                   APP_MSDU_TYPES / IPV4_MSDU_TYPES 据此判据；None 时才按首字节启发式。
        """
        table = []
        if not data:
            return table

        first = data[0]
        if msdu_type == 0 or (msdu_type is None and first == 0x00):
            # 网络管理消息(MME)
            try:
                from hdc10_mme_parser import parse_management_message
                # data 已按 MSDU 切片 → offset 传 0（值索引相对切片）；
                # 行偏移再整体加上 base_offset，与原帧字节高亮对齐。
                mme_table = parse_management_message(data, 0)
                shifted = []
                for row in mme_table:
                    cells = list(row)
                    if len(cells) >= 6 and cells[4] is not None and cells[5] is not None:
                        cells[4] = cells[4] + base_offset
                        cells[5] = cells[5] + base_offset
                    shifted.append(tuple(cells))
                table.extend(shifted)
            except Exception:
                table.append((
                    "  网络管理消息",
                    ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
                    f"{len(data)}字节",
                    "管理消息解析失败, 显示原始数据",
                    base_offset, base_offset + min(len(data), 16) - 1,
                ))
            return table

        if msdu_type in APP_MSDU_TYPES:
            # MAC 头已声明为应用层报文（表10=48 / 表13=128）→ 直接按应用层解析。
            # 判据只取 MAC 头字段，**不再**看首字节：旧实现用首字节启发式，
            # 曾导致「声明 48 却按未定义处理」与「声明 47 却按应用层解析」双向误判。
            table.extend(self._parse_application_layer(data, base_offset))
            return table

        if msdu_type in IPV4_MSDU_TYPES:
            # 名称取自类型表（表10=49「IP报文」/ 表13=129「IPV4报文」），不另写字面量
            type_label = MSDU_TYPES.get(msdu_type) or SINGLEHOP_MSG_TYPES.get(msdu_type, "IP报文")
            table.append((
                f"  {type_label}",
                ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
                f"{len(data)}字节",
                f"类型{msdu_type}: {type_label}(表10/表13), 本解析器暂不展开IP载荷, 显示原始数据",
                base_offset, base_offset + min(len(data), 16) - 1,
            ))
            return table

        if msdu_type is None and first in APP_PORTS:
            # 回退判据（仅无 MAC 头上下文时）：首字节命中应用层端口表
            table.extend(self._parse_application_layer(data, base_offset))
            return table

        # 未知/厂商扩展类型: 原始hex + 可读ASCII片段提示
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
        import re as _re
        segs = [s for s in _re.split(r'[^A-Za-z0-9_\-]', printable) if len(s) >= 3]
        ascii_hint = ' '.join(segs)[:48]
        type_name = (f"类型{msdu_type}" if msdu_type is not None else f"首字节0x{first:02X}")
        table.append((
            "  MSDU数据",
            ' '.join(f'{b:02X}' for b in data[:16]) + ("..." if len(data) > 16 else ""),
            f"{len(data)}字节",
            f"{type_name}: 未定义(厂商扩展/待扩展), 原始数据" +
            (f"; 含ASCII标记[{ascii_hint}]" if ascii_hint else ""),
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
        if sec_mode:
            # 报文ID 高4位非0 = 数据域受信道安全机制保护（第4-3部分 §5.2.3）。
            # 不能因此跳过业务解析（陷阱23：点解析就必须看到内容），但必须醒目提示：
            # 以下按明文逐字段解出的数值可能是「看起来正常」的错误值。
            table.append((
                "  ⚠ 安全保护",
                f"0x{sec_mode:X}",
                SECURITY_MODES.get(sec_mode, f"保留({sec_mode})"),
                "数据域受信道安全机制保护, 以下按明文解析的字段可能无效",
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
            # 未实现字段级解析的报文：**先查报文ID名称表**（单一来源 MSG_ID_NAMES）。
            # 名字表与分派链曾是两份手写清单，0x0A0/0x0A4 有名字却无分支 → 静默显示
            # 「未识别的业务数据」。查表后规范已命名的业务自动受益，也不再二次遗漏。
            name = MSG_ID_NAMES.get(msg_id)
            show = data[:32]
            if name:
                table.append((
                    f"  {name}",
                    "",
                    f"{len(data)}字节",
                    f"业务ID 0x{msg_id:03X}：{name}",
                    offset, offset + len(data) - 1,
                ))
                if msg_id in MSG_ID_NO_FORMAT_DEFINED:
                    # 规范确实未定义格式（如 0x00A0/0x00A4）：只能报名字 + 原始数据
                    table.append((
                        "    ⚠ 格式未定义",
                        ' '.join(f'{b:02X}' for b in show) + ("..." if len(data) > 32 else ""),
                        f"{len(data)}字节",
                        "本规范（第4-3部分）未给出该报文的字段格式，以下为原始数据",
                        offset, offset + min(len(data), 32) - 1,
                    ))
                else:
                    # 规范**有**格式定义，只是本次未命中已实现分支（多为端口不匹配）。
                    # 旧文案在此会声称「规范未给出字段格式」→ 事实错误（R1 要求依据必须成立）。
                    table.append((
                        "    ⚠ 未按业务格式解析",
                        ' '.join(f'{b:02X}' for b in show) + ("..." if len(data) > 32 else ""),
                        f"{len(data)}字节",
                        f"本解析器未对「端口 0x{port:02X} + 业务ID 0x{msg_id:03X}」组合实现字段解析"
                        "（该业务的字段格式见规范第4-3部分对应章节），以下为原始数据",
                        offset, offset + min(len(data), 32) - 1,
                    ))
            else:
                table.append((
                    "  原始数据",
                    ' '.join(f'{b:02X}' for b in show) + ("..." if len(data) > 32 else ""),
                    f"{len(data)}字节",
                    f"未识别的业务数据(0x{msg_id:03X})：未在本规范报文ID表中定义",
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

        # 报文头长度: byte0[6:7](低2b)+byte1[0:3](高4b)=6bit, 值 = 报文头字节数
        hdr_len = ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)
        # 协议版本号: byte0[0:5] = 6bit（文档第4-3部分 §5.3.1.2：本版本取值固定为 1）。
        # 原实现漏了本行赋值，却在下方三处引用 proto_ver → app 级别解析抄表报文
        # （0x001/0x002/0x003）时抛 NameError（现场弹「解析失败」）。
        # 写法与同文件 _parse_confirm / _parse_timesync 等 6 处保持一致。
        proto_ver = b0 & 0x3F

        table.append((
            f"  {name}报文头",
            "",
            f"{hdr_len}字节",
            f"头长: {hdr_len}字节",
            offset, offset + hdr_len - 1,
        ))
        table.append((
            "    协议版本号",
            f"0x{proto_ver:02X}",
            str(proto_ver),
            f"协议版本: {proto_ver}",
            offset, offset,
        ))
        hdr_raw, hdr_note = _hdr_len_cells(b0, b1, hdr_len)
        table.append((
            "    报文头长度",
            hdr_raw,
            f"{hdr_len}字节",
            hdr_note,
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

        # 字节6~7：下行 = 设备超时时间 + 选项字（第4-3部分 表3）；
        # 上行 = 选项字 16bit（同部分 表10「抄表上行报文格式说明」）
        # 方向位 = 选项字(byte7) bit0（0=下行 CCO→STA, 1=上行 STA→CCO，表9）；
        # 终端主动并发抄表方式下字节7 为「报文间间隔」而非方向位（表8），
        # 且 CCO 下发的并发抄表报文恒为下行（表3 为请求报文头），故不参与上行判定。
        opt_byte = data[7]
        is_uplink = (msg_id != 0x003) and bool(opt_byte & 0x01)
        if is_uplink:
            opt16 = data[6] | (data[7] << 8)
            table.append((
                "    选项字(应答状态)",
                f"0x{opt16:04X}",
                f"0x{opt16:04X}",
                f"上行应答报文头(第4-3部分 表10)：选项字 16bit = 报文应答状态 0x{opt16:04X}",
                offset + 6, offset + 7,
            ))
        else:
            # 设备超时时间：byte6, 8bit, 单位 100ms（文档 §5.3.1.8）
            timeout_raw = data[6]
            table.append((
                "    设备超时时间",
                f"0x{timeout_raw:02X}",
                f"{timeout_raw * 100}ms",
                f"STA 与设备(电能表/采集器)通信超时: {timeout_raw} × 100ms "
                f"= {timeout_raw * 100}ms（依据 §5.3.1.8）",
                offset + 6, offset + 6,
            ))
            # 选项字：byte7, 8bit（文档 §5.3.1.9 / 表8 / 表9）
            if msg_id == 0x003:
                opt_desc = (f"报文间间隔: {opt_byte} × 10ms = {opt_byte * 10}ms"
                            "（终端主动并发抄表方式, 表8）")
            else:
                opt_desc = ("方向: 上行(STA→CCO)" if (opt_byte & 0x01)
                            else "方向: 下行(CCO→STA)")
                if opt_byte & 0xFE:
                    opt_desc += f"; bit7~bit1 保留(非0: 0x{opt_byte & 0xFE:02X})"
            table.append((
                "    选项字",
                f"0x{opt_byte:02X}",
                f"0x{opt_byte:02X}",
                opt_desc,
                offset + 7, offset + 7,
            ))

        # DATA 域
        if hdr_len < len(data):
            payload = data[hdr_len:hdr_len + data_len] if hdr_len + data_len <= len(data) else data[hdr_len:]
            table.append((
                "    数据(DATA)",
                ' '.join(f'{b:02X}' for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
                f"{len(payload)}字节",
                "抄表应用报文数据",
                offset + hdr_len, offset + hdr_len + len(payload) - 1,
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
        hdr_len = ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)  # 6bit, 报文头字节数

        direction = (b1 >> 4) & 0x01
        ack_bit = (b1 >> 5) & 0x01
        seq = int.from_bytes(data[2:4], 'little') if len(data) >= 4 else 0

        table.append((
            "  确认/否认报文",
            "",
            f"{hdr_len}字节头",
            "确认/否认应答报文",
            offset, offset + min(len(data), hdr_len) - 1,
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
        hdr_len = ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)  # 6bit, 报文头字节数

        # 转发数据长度: byte2[4:7] + byte3[0:7] = 12bit
        data_len = ((b2 >> 4) & 0x0F) | (b3 << 4)

        table.append((
            "  校时报文",
            "",
            f"{hdr_len}字节头",
            "校时命令",
            offset, offset + min(len(data), hdr_len) - 1,
        ))
        table.append(("    转发数据长度", f"0x{data_len:03X}", f"{data_len}字节",
                      f"校时报文数据长度: {data_len}字节", offset + 2, offset + 3))

        if len(data) > hdr_len:
            payload = data[hdr_len:hdr_len + data_len] if hdr_len + data_len <= len(data) else data[hdr_len:]
            table.append(("    数据(DATA)",
                          ' '.join(f'{b:02X}' for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
                          f"{len(payload)}字节", "校时应用报文数据",
                          offset + hdr_len, offset + hdr_len + len(payload) - 1))
        return table

    def _parse_event(self, data: bytes, offset: int) -> List[Tuple]:
        """事件上报报文（0x008）"""
        table = []
        if len(data) < 12:
            return [("  事件报文(过短)", "", "", f"需至少12字节", offset, offset + len(data) - 1)]

        b0 = data[0]
        b1 = data[1]

        proto_ver = b0 & 0x3F
        hdr_len = ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)  # 6bit, 报文头字节数

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
            f"{hdr_len}字节头",
            "事件主动上报",
            offset, offset + hdr_len - 1,
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

        # 数据（DATA）域：字节12 起（表30/表31/附件3 的字节号以报文头为基准）
        data_off = hdr_len if 12 <= hdr_len <= len(data) else 12
        if len(data) > data_off:
            table.extend(self._parse_event_data(data, data_off, offset))
        return table

    def _parse_event_data(self, data: bytes, pos: int, offset: int) -> List[Tuple]:
        """事件上报数据（DATA）域：位图方式 / 地址方式 / 设备信息

        依据 HDC 第4-3部分 §5.6.1.10：
          表30 位图方式 —— 事件类型 1=停电(位图) / 2=上电(位图)：
            字节12 事件类型 + 字节13-14 发生事件站点起始TEI(16bit) + 可变长节点位图
          表31 地址方式 —— 事件类型 3=停电(地址) / 4=上电(地址)：
            字节12 事件类型 + 字节13-14 发生事件电表个数(16bit)
            + N × (电表地址 6B + 带电状态 1B)
        依据 A-HS-11-03 附件3《Q/GDW 11612.43 协议扩增》（即装即采）：
          事件类型 51 = 设备信息：设备地址/协议类型/描述符 + M 台下挂设备清单
        """
        table = []
        ev_type = data[pos]
        name, kind = EVENT_TYPES.get(ev_type, (f"保留({ev_type})", ""))
        table.append(("    事件类型", f"0x{ev_type:02X}", name,
                      "STA上报事件类型（表30/表31/即装即采附件3）",
                      offset + pos, offset + pos))
        if not kind:
            rem = data[pos + 1:]
            if rem:
                table.append(("    事件数据",
                              ' '.join(f'{b:02X}' for b in rem[:16])
                              + ("..." if len(rem) > 16 else ""),
                              f"{len(rem)}字节", "未定义事件类型的原始数据",
                              offset + pos + 1, offset + pos + len(rem)))
            return table
        if kind == "bitmap":
            table.extend(self._parse_event_bitmap(data, pos + 1, offset))
        elif kind == "addr":
            table.extend(self._parse_event_addr(data, pos + 1, offset))
        elif kind == "device":
            table.extend(self._parse_event_device(data, pos + 1, offset))
        return table

    def _parse_event_bitmap(self, data: bytes, pos: int, offset: int) -> List[Tuple]:
        """位图方式数据域（表30）：起始TEI(16bit) + 可变长节点位图"""
        if len(data) < pos + 2:
            return [("    事件数据", "", "", "位图方式数据不足（需起始TEI 2字节）",
                     offset + pos, offset + len(data) - 1)]
        start_tei = int.from_bytes(data[pos:pos + 2], 'little')
        table = [("    发生事件站点起始TEI", f"0x{start_tei:04X}", str(start_tei),
                  "第1个bit代表该TEI，后续依次类推", offset + pos, offset + pos + 1)]
        bitmap = data[pos + 2:]
        if bitmap:
            set_bits = [start_tei + i * 8 + b
                        for i, byte in enumerate(bitmap)
                        for b in range(8) if byte & (1 << b)]
            table.append(("    发生事件的节点位图",
                          ' '.join(f'{b:02X}' for b in bitmap[:16])
                          + ("..." if len(bitmap) > 16 else ""),
                          f"{len(bitmap)}字节 / {len(set_bits)}个节点",
                          "置位TEI: " + (', '.join(str(t) for t in set_bits[:12])
                                        + ("..." if len(set_bits) > 12 else "")),
                          offset + pos + 2, offset + pos + 1 + len(bitmap)))
        return table
    def _parse_event_addr(self, data: bytes, pos: int, offset: int) -> List[Tuple]:
        """地址方式数据域（表31）：电表个数(16bit) + N × (地址6B + 带电状态1B)"""
        if len(data) < pos + 2:
            return [("    事件数据", "", "", "地址方式数据不足（需电表个数 2字节）",
                     offset + pos, offset + len(data) - 1)]
        count = int.from_bytes(data[pos:pos + 2], 'little')
        table = [("    发生事件的电表个数", f"0x{count:04X}", str(count),
                  f"发生事件电表个数: {count}", offset + pos, offset + pos + 1)]
        p = pos + 2
        for i in range(count):
            if p + 7 > len(data):
                table.append((f"    电表{i + 1}", "", "",
                              "数据不足（需地址6B+状态1B）",
                              offset + p, offset + len(data) - 1))
                break
            addr = data[p:p + 6]
            state = data[p + 6]
            table.append((f"    电表{i + 1}地址",
                          ' '.join(f'{b:02X}' for b in addr),
                          ''.join(f'{b:02X}' for b in reversed(addr)),
                          "BCD码(6字节)", offset + p, offset + p + 5))
            table.append((f"    电表{i + 1}带电状态", f"0x{state:02X}", str(state),
                          "0-停电 1-未停电", offset + p + 6, offset + p + 6))
            p += 7
        return table

    def _parse_event_device(self, data: bytes, pos: int, offset: int) -> List[Tuple]:
        """设备信息数据域（即装即采附件3 事件类型=51）

        设备地址(BCD 6B) + 设备通信协议类型(1B) + 设备描述符长度N(1B)
        + 设备描述符(ASCII N B) + 下挂设备数量M(1B)
        + M × (通信地址长度N1(1B) + 通信地址(BCD N1 B)
               + 设备描述符长度N2(1B) + 设备描述符(ASCII N2 B) + 通信协议类型(1B))
        """
        table = []
        if len(data) < pos + 9:
            table.append(("    设备信息", "", "",
                          "数据不足（需设备地址6B+协议1B+描述符长度1B+数量1B）",
                          offset + pos, offset + len(data) - 1))
            return table
        dev_addr = data[pos:pos + 6]
        proto_type = data[pos + 6]
        desc_len = data[pos + 7]
        table.append(("    设备地址", ' '.join(f'{b:02X}' for b in dev_addr),
                      ''.join(f'{b:02X}' for b in reversed(dev_addr)),
                      "BCD码(6字节)：STA模块通信地址", offset + pos, offset + pos + 5))
        table.append(("    设备通信协议类型", f"0x{proto_type:02X}", str(proto_type),
                      PROTOCOL_TYPES.get(proto_type, f"保留({proto_type})"),
                      offset + pos + 6, offset + pos + 6))
        table.append(("    设备描述符长度", f"0x{desc_len:02X}", f"{desc_len}字节",
                      f"设备描述符长度 N={desc_len}", offset + pos + 7, offset + pos + 7))
        p = pos + 8
        if p + desc_len > len(data):
            table.append(("    设备描述符", "", "", "数据不足（描述符长度超出报文）",
                          offset + p, offset + len(data) - 1))
            return table
        table.append(("    设备描述符", _ascii_text(data[p:p + desc_len]),
                      f"{desc_len}字节", "ASCII 设备描述符",
                      offset + p, offset + p + desc_len - 1))
        p += desc_len
        if p >= len(data):
            return table
        dev_count = data[p]
        table.append(("    下挂设备数量M", f"0x{dev_count:02X}", str(dev_count),
                      f"下挂设备数量: {dev_count}（不应超过32）", offset + p, offset + p))
        p += 1
        for i in range(dev_count):
            if p + 2 > len(data):
                table.append((f"    下挂设备{i + 1}", "", "", "数据不足",
                              offset + p, offset + len(data) - 1))
                break
            a_len = data[p]
            table.append((f"    下挂设备{i + 1}通信地址长度", f"0x{a_len:02X}",
                          f"{a_len}字节", f"N1={a_len}", offset + p, offset + p))
            p += 1
            if p + a_len + 1 > len(data):
                table.append((f"    下挂设备{i + 1}", "", "",
                              "数据不足（通信地址超出报文）",
                              offset + p, offset + len(data) - 1))
                break
            addr = data[p:p + a_len]
            table.append((f"    下挂设备{i + 1}通信地址",
                          ' '.join(f'{b:02X}' for b in addr),
                          ''.join(f'{b:02X}' for b in reversed(addr)),
                          f"BCD码({a_len}字节)", offset + p, offset + p + a_len - 1))
            p += a_len
            d_len = data[p]
            table.append((f"    下挂设备{i + 1}设备描述符长度", f"0x{d_len:02X}",
                          f"{d_len}字节", f"N2={d_len}", offset + p, offset + p))
            p += 1
            if p + d_len + 1 > len(data):
                table.append((f"    下挂设备{i + 1}", "", "",
                              "数据不足（描述符超出报文）",
                              offset + p, offset + len(data) - 1))
                break
            table.append((f"    下挂设备{i + 1}设备描述符",
                          _ascii_text(data[p:p + d_len]),
                          f"{d_len}字节", "ASCII 设备描述符",
                          offset + p, offset + p + d_len - 1))
            p += d_len
            pt = data[p]
            table.append((f"    下挂设备{i + 1}通信协议类型", f"0x{pt:02X}", str(pt),
                          PROTOCOL_TYPES.get(pt, f"保留({pt})"), offset + p, offset + p))
            p += 1
        if p < len(data):
            rem = data[p:]
            table.append(("    剩余数据",
                          ' '.join(f'{b:02X}' for b in rem[:16])
                          + ("..." if len(rem) > 16 else ""),
                          f"{len(rem)}字节", "下挂设备清单之后的剩余字节",
                          offset + p, offset + len(data) - 1))
        return table
    def _parse_comm_test(self, data: bytes, offset: int) -> List[Tuple]:
        """通信测试命令（0x006）：表32 普通通信测试 + 检测扩展命令（A-HS-11-03 表2）

        域布局（字节号 / 比特位）：
          字节0 bit0-5        协议版本号（本版本固定为1）
          字节0 bit6-7（低2位）+ 字节1 bit0-3（高4位）  报文头长度（6bit，值 = 报文头字节数）
          字节1 bit4-7        保留 / 测试模式·配置操作
          字节2 bit0-3        转发数据的规约类型
          字节2 bit4-7 + 字节3 bit0-7   12bit 转发数据长度 / 模式持续时间 / 配置值
          字节4 bit0-3        安全测试模式（仅测试模式=13 生效）
          字节4 bit4-7、字节5  保留（模式12 时为 PHR_MCS / PSDU_MCS / PbSIZE）

        字节1 高4位 = 0 → 普通通信测试（按表32 原义：转发数据长度 = 12bit）；
        ≠ 0 → 检测扩展命令，该 12bit 按测试模式分别解释为
        频段值(6) / ToneMask值(7) / 无线信道号(8) / MCS值(12) / 模式持续时间(其余)。

        扩展命令的链路层约定（表2 注意事项第7条）：nid=0、源TEI=0、目的TEI=0xFFF。
        """
        table = []
        if len(data) < 4:
            return table

        b0 = data[0]
        b1 = data[1]
        ver = b0 & 0x3F
        # 报文头长度: byte0[6:7](低2b)+byte1[0:3](高4b)=6bit, 值 = 报文头字节数
        # （协议10 同字段同口径：gw_new_gen_cmd_payloads 也是 (b1&0xF)<<2 | b0>>6；
        #  旧写法按「字节0 存高 2 位」拼，遇上 b0 bit7-6≠0 的帧会给出荒谬值）
        hdr_len = ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)
        test_mode = (b1 >> 4) & 0x0F
        b2 = data[2]
        b3 = data[3]
        proto_type = b2 & 0x0F
        config_val = ((b2 >> 4) & 0x0F) | (b3 << 4)

        table.append(("  通信测试报文", "", "", "通信测试命令",
                      offset, offset + len(data) - 1))
        table.append(("    协议版本号", f"0x{ver:02X}", str(ver),
                      "本版本固定为1（同字节高2位归报文头长度）"
                      + _bit_span_note((0, 5, 0, b0)),
                      offset, offset))
        hdr_raw, hdr_note = _hdr_len_cells(b0, b1, hdr_len)
        table.append(("    报文头长度", hdr_raw,
                      f"{hdr_len}字节",
                      "报文头(除数据域外)的长度；" + hdr_note,
                      offset, offset + 1))

        if test_mode == 0:
            table.extend(self._parse_comm_test_plain(data, offset, proto_type, config_val))
        else:
            table.extend(self._parse_comm_test_ext(
                data, offset, test_mode, proto_type, b2, b3, config_val))
        return table

    def _parse_comm_test_plain(self, data: bytes, offset: int,
                               proto_type: int, data_len: int) -> List[Tuple]:
        """普通通信测试（测试模式=0，表32 原义）

        槽位约定与协议9/10 同构 ``(字段, 原始值, 解析值, 说明, 起, 止)``；
        纯元数据行的解析值**留空**——摘要按「解析值非空」过滤，留空即不留噪声。
        """
        table = [
            ("    保留", "0", "", "保留(=0 为普通通信测试)"
             + _bit_span_note((1, 7, 4, data[1])),
             offset + 1, offset + 1),
            ("    转发数据规约类型", f"0x{proto_type:01X}", str(proto_type),
             PROTOCOL_TYPES.get(proto_type, f"保留({proto_type})"),
             offset + 2, offset + 2),
            ("    转发数据长度", f"0x{data_len:03X}", f"{data_len}字节",
             f"实际数据(DATA)域长度: {data_len}字节"
             + _bit_span_note((2, 7, 4, data[2]), (3, 7, 0, data[3])),
             offset + 2, offset + 3),
        ]
        if len(data) > 4:
            payload = data[4:4 + data_len] if 4 + data_len <= len(data) else data[4:]
            table.append(("    测试数据",
                          ' '.join(f'{b:02X}' for b in payload[:16])
                          + ("..." if len(payload) > 16 else ""),
                          f"{len(payload)}字节", "通信测试数据",
                          offset + 4, offset + 4 + len(payload) - 1))
        return table

    def _parse_comm_test_ext(self, data: bytes, offset: int, test_mode: int,
                             proto_type: int, b2: int, b3: int,
                             config_val: int) -> List[Tuple]:
        """检测扩展命令（测试模式≠0，A-HS-11-03 表2）

        槽位约定与协议10 ``_parse_comm_test_ext`` 一致：**名称放解析值槽**。
        ``main_gui._extract_test_mode_content`` 按「非数值者即名称」探测
        （协议9 名称在说明槽、协议10 在解析值槽，两种都要能读），故解析值槽
        放名称、原始值槽放数值，摘要才不会退化成「测试模式:6 (频段切换操作)」。
        """
        mode_name = EXT_TEST_MODES.get(test_mode, f"保留({test_mode})")
        b1 = data[1] if len(data) > 1 else 0
        # 说明列补「位域归属」，把跨字节字段的 bit 占用摆到台面上：
        #   byte1[bit7-4] = 测试模式/配置操作；byte2[bit7-4]+byte3 = 12bit 值
        #   （12bit 与 6bit 报文头长度都是「字节号小的端为低位」，口径同 _bits_lsb）；
        #   byte2[bit3-0] = 转发数据规约类型（该行说明被测试逐字断言，故不加尾注）。
        span12 = _bit_span_note((2, 7, 4, b2), (3, 7, 0, b3))
        span_sec = _bit_span_note((4, 3, 0, data[4] if len(data) > 4 else 0))
        table = [
            ("    测试模式/配置操作", str(test_mode), mode_name,
             "检测扩展命令: 测试模式/配置操作(A-HS-11-03 表2)"
             + _bit_span_note((1, 7, 4, b1)),
             offset + 1, offset + 1),
            ("    转发数据规约类型", f"0x{proto_type:01X}", str(proto_type),
             PROTOCOL_TYPES.get(proto_type, f"保留({proto_type})"),
             offset + 2, offset + 2),
        ]

        # 12bit 配置值：按测试模式取用（表2 该行字段名
        # 「转发数据长度/测试模式持续时间/频段值/ToneMask值/无线信道号/MCS值」）
        if test_mode == 6:
            table.append(("    频段值(目标频段)", str(config_val),
                          EXT_BAND_RANGES.get(config_val, f"保留({config_val})"),
                          "频段切换操作的目标频段（表2 第6条）" + span12,
                          offset + 2, offset + 3))
        elif test_mode == 7:
            table.append(("    ToneMask值(目标ToneMask)", str(config_val),
                          f"目标ToneMask: {config_val}",
                          "ToneMask配置操作的目标值（表2 第7条）" + span12,
                          offset + 2, offset + 3))
        elif test_mode == 8:
            table.append(("    无线信道号", str(config_val),
                          f"目标无线信道号: {config_val}",
                          "无线信道切换操作的目标信道（表2 第8条）" + span12,
                          offset + 2, offset + 3))
        elif test_mode == 12:
            table.append(("    MCS值", str(config_val), f"MCS值: {config_val}",
                          "PLC到RF物理层回传测试模式的MCS（表2）" + span12,
                          offset + 2, offset + 3))
        elif test_mode in (1, 2):
            table.append(("    模式持续时间/配置值", str(config_val), "填0即可",
                          "该模式转发完成首帧后即退出（表2 第1/2条）" + span12,
                          offset + 2, offset + 3))
        else:
            parsed = f"{config_val}分钟"
            if config_val > EXT_MAX_DURATION_MIN:
                parsed += f"(超限,限定{EXT_MAX_DURATION_MIN}分钟)"
            table.append(("    模式持续时间/配置值", str(config_val), parsed,
                          f"测试模式持续时间(单位:分钟,最大{EXT_MAX_DURATION_MIN})"
                          + span12,
                          offset + 2, offset + 3))

        # 字节4：安全测试模式(bit0-3) + 保留/PHR_MCS(bit4-7)
        b4 = data[4] if len(data) > 4 else 0
        sec_mode = b4 & 0x0F
        hi4 = (b4 >> 4) & 0x0F
        if test_mode == 13:
            table.append(("    安全测试模式", str(sec_mode),
                          EXT_SEC_MODES.get(sec_mode, f"保留({sec_mode})"),
                          "标识不同的安全测试模式（表2 第13条）" + span_sec,
                          offset + 4, offset + 4))
        elif test_mode == 12:
            table.append(("    PHR_MCS", str(hi4), f"MCS {hi4}",
                          "仅模式12生效" + _bit_span_note((4, 7, 4, b4)),
                          offset + 4, offset + 4))
        else:
            # 字段名带「字段」后缀：非 13 时该域是保留位，不应被摘要的
            # 「安全测试模式」哨兵当成子模式渲染（与协议10 同名同义）。
            table.append(("    安全测试模式字段", str(sec_mode), "应为0",
                          "测试模式≠13时该字段应为0（表2 注意事项第9条）"
                          + span_sec,
                          offset + 4, offset + 4))

        # 字节5：模式12 时为 PSDU_MCS(bit0-3) + PbSIZE(bit4-7)
        if len(data) > 5 and test_mode == 12:
            b5 = data[5]
            psdu = b5 & 0x0F
            pbsize = (b5 >> 4) & 0x0F
            table.append(("    PSDU_MCS", str(psdu), f"MCS {psdu}",
                          "仅模式12生效" + _bit_span_note((5, 3, 0, b5)),
                          offset + 5, offset + 5))
            table.append(("    PbSIZE", str(pbsize), f"PbSIZE {pbsize}",
                          "仅模式12生效" + _bit_span_note((5, 7, 4, b5)),
                          offset + 5, offset + 5))
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
        hdr_len = ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)  # 6bit, 报文头字节数

        force_ack = (b1 >> 4) & 0x01
        reg_param = (b1 >> 5) & 0x07
        param_names = {0: "查询结果", 1: "启动注册"}

        seq = int.from_bytes(data[4:8], 'little') if len(data) >= 8 else 0

        table.append((
            f"  {name}",
            "",
            f"{hdr_len}字节头",
            f"从节点注册: {name}",
            offset, offset + min(len(data), hdr_len) - 1,
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
            hdr_len = ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)  # 6bit, 报文头字节数
            status_nib = (b1 >> 4) & 0x0F
            blk_count = int.from_bytes(data[2:4], 'little')
            start_blk = int.from_bytes(data[4:8], 'little')
            upgrade_id = int.from_bytes(data[8:12], 'little')
            # 方向判定: 上行带接收位图(len>12); 恰12字节按表40下行处理
            # (表45上行的升级状态占字节1高4位, 表40同位置为保留0)
            is_uplink = len(data) > 12 or status_nib in (1, 2, 3, 4)

            table.append(("    协议版本号", f"0x{version:02X}", str(version),
                          "固定为1（同字节高2位归报文头长度）"
                          + _bit_span_note((0, 5, 0, b0)),
                          offset, offset))
            hdr_raw, hdr_note = _hdr_len_cells(b0, b1, hdr_len)
            table.append(("    报文头长度", hdr_raw,
                          f"{hdr_len}字节",
                          "报文头(除数据域外)长度；" + hdr_note,
                          offset, offset + 1))

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
        hdr_len = ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)  # 6bit, 报文头字节数

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
            f"{hdr_len}字节头",
            "台区户变关系识别",
            offset, offset + hdr_len - 1,
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

        if len(data) > hdr_len:
            payload = data[hdr_len:]
            table.append(("    数据(DATA)",
                          ' '.join(f'{b:02X}' for b in payload[:16]) + ("..." if len(payload) > 16 else ""),
                          f"{len(payload)}字节", "特征采集数据",
                          offset + hdr_len, offset + hdr_len + len(payload) - 1))
            table.extend(self._parse_phase_ident_data(
                payload, offset + hdr_len, feat_type, coll_type))

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
        """app 模式：用户已显式声明输入即应用层报文，不再由端口值二次否决。

        判据顺序：
          ① 长度 < 4：通用头都不完整 → 明确报错 + 原始数据；
          ② 端口命中端口表，或报文控制字合规（§5.2.4「默认设置为0」）
             且不是完整 MPDU → 按应用层通用头解析（任意端口都能解，见 R2）；
          ③ 完整 MPDU（FCCS 校验通过）→ 交回完整帧解析（误粘整帧的既有兜底）；
          ④ 其余 → 仍按应用层解释，并注明为推测。
        """
        if len(data) < 4:
            return [(
                "❌ 应用层数据",
                ' '.join(f'{b:02X}' for b in data),
                f"{len(data)}字节",
                "长度不足4字节（端口1B+报文ID2B+控制字1B），非完整应用层报文",
                0, max(len(data) - 1, 0),
            )]
        # ② 的「完整 MPDU 排除」是必需的：FC 的 byte3 是网络标识(NID)高字节，
        # 取 0 的概率约 1/256；没有该排除时，NID 高字节为 0 的完整 MPDU
        # 会被当成应用层错位解析（A6：完整 MPDU 必须仍走 FC 路径）。
        has_fc = self._detect_fc(data)
        if data[0] in APP_PORTS or (data[3] == 0 and not has_fc):
            return self._parse_application_layer(data, 0)
        if has_fc and len(data) > 16:
            return self.parse_to_table(data, parse_level="auto")
        table = self._parse_application_layer(data, 0)
        table.append((
            "  ⚠ 推测解析",
            "",
            "",
            "端口未在端口表中且报文控制字非0，按应用层通用头推测解析，字段可能无效",
            None, None,
        ))
        return table

    def _parse_mac_only(self, data: bytes, frame_type: int) -> List[Tuple]:
        """mac_only 模式：输入即 MAC 帧，从字节 0 直接解析。

        契约（AGENTS §8 陷阱19 / 协议9 同口径）：mac_only 不探测、不剥离 PBH。
        需要带 PBH 的输入请改用 pb_only / auto。
        """
        return self._parse_mac_frame(data, 0)

    def _parse_pb_only(self, data: bytes, frame_type: int) -> List[Tuple]:
        """pb_only 模式：解析物理块"""
        return self._parse_pb_block(data, 0, frame_type)

    def _parse_pb_and_mac_header(self, data: bytes, base_offset: int, dt: int) -> List[Tuple]:
        """fc_mac 模式：解析 PBH + MAC帧头"""
        table = []
        if not data or dt in (2, 3):
            # SACK / 网间协调帧无物理块载荷（网间协调见表26）
            return table
        # 先取第一个PB
        if len(data) < 2:
            return table
        # SOF 帧首块已置**帧起始位**时，规范（表37）保证 data[0] 就是 PBH，直接采信；
        # 只有「首字节无帧起始位」的物理块才需要探测是否省略了 PBH。
        # 该门控与 _parse_pb_block 的分支条件一致（它在 sof 置位时也无条件把
        # data[0] 当 PBH 读），否则两条路径对同一帧会给出不同结论。
        # 不加门控的实测后果：帧尾 0 填充使 _probe_pb_form 的「ICV 全 0」强证据
        # 误命中，合法 PBH 被当 MAC 头解析（用户报障留空帧：PB头=无、MSDU类型=0）。
        if dt == 1 and (data[0] >> 6) & 0x01:
            pbh_len, probe_score = 1, 0
        else:
            # 探测该 PB 是否省略了 PBH（与 _parse_pb_block 同一判据，防两处漂移）
            pbh_len, probe_score = self._probe_pb_form(data)
        if pbh_len == 0:
            table.append((
                "PB头",
                f"0x{data[0]:02X}",
                "无",
                "未检测到合法物理块头(PBH)，PB体直接起始于 MAC 帧头"
                f"（探测得分 {probe_score}）",
                base_offset, base_offset,
            ))
            hdr_len, mac_table = self._parse_mac_header(data, 0)
            table.extend(mac_table)
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
            # 注意：_parse_mac_header 的第二参数是 data 内的**相对**索引，
            # 不是原帧绝对偏移（旧代码误传 base_offset+1，使 MAC 头整体错位解析）
            hdr_len, mac_table = self._parse_mac_header(mac_data, 0)
            table.extend(mac_table)
        return table
