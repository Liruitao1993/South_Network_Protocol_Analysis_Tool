# -*- coding: utf-8 -*-
"""南网光伏协议转换单元 · 无线模组接口手册（V1.6）扩展 —— DI 表与数据域解码。

来源：``协议文档/6.645协议/南网光伏协议转换单元无线接口手册-V1.6.md``
（由同名 PDF 转换；PDF 为 WPS 文字导出的文本层 PDF）

帧基座与 DL/T 645-2007 完全一致（数据域每字节 +33H 上线、-33H 后解析），
本模块只负责**本手册扩展的那批 DI** 与**扩展控制码语义**，不重复实现 645 帧结构。

与 ``dlt645_pv_ext.py``（附件1《协议转换单元技术规范书》§D.1）的关系：
- 两者都是"光伏协议转换单元"体系的 645 扩展，DI 命名空间重叠；
- **``04E60001`` 两边都有**：附件1 给的"长度列 16"无法自洽切分（见 pv_ext 的歧义行说明），
  本手册给出明确模型 ``1 + 6×M``，且 4.4.3 有实测报文可验证 ⇒ **本模块优先**接管该 DI。
"""

from typing import Dict, List, Optional, Tuple

# ── 常量：手册 §4 的位/枚举定义 ──────────────────────────────────────────

#: 通信速率特征字（§4.1.3，调制型/接触式/通信口1/2/3 共用）
BAUD_MASK_BITS: Tuple[Tuple[int, int], ...] = (
    (0, 115200), (1, 600), (2, 1200), (3, 2400),
    (4, 4800), (5, 9600), (6, 19200), (7, 38400),
)

#: 校验方式（§4.1.3）
PARITY_NAMES = {0: "无校验", 1: "奇校验", 2: "偶校验"}

#: 无线调制方式（§4.2.1）
MODULATION_NAMES = {
    1: "备用（保留）",
    2: "2 — 500kHz（信道 1~79）",
    3: "3 — 200kHz（信道 1~200）",
}

#: 升级状态码（§4.2.4 注 2）
UPGRADE_STATUS = {
    0: "初始状态（出厂默认）",
    1: "启动传输成功，待下载",
    2: "下载中",
    3: "下载成功",
    4: "真实性、完整性校验成功",
    5: "定时升级等待中",
    6: "升级成功",
    20: "硬件版本不匹配",
    21: "软件版本不匹配",
    22: "写外部 Flash 错",
    23: "读取外部 Flash 错",
    24: "写程序 Flash 错",
    25: "完整性校验错",
    26: "真实性校验错",
    27: "定时升级时间异常",
    255: "升级失败其它原因",
}

#: 错误信息字 ERR 位（§4.1.3 表；本手册把 Bit7 扩展为"无线接口转换器未入网"）
ERR_BITS: Tuple[Tuple[int, str], ...] = (
    (7, "从站不在线（本手册扩展：无线接口转换器未入网，示例值 0x80）"),
    (6, "费率数超"),
    (5, "日时段数超"),
    (4, "年时区数超"),
    (3, "通信速率不能更改"),
    (2, "密码错/未授权"),
    (1, "无请求数据"),
    (0, "其他错误"),
)

#: 在网状态（§4.3.1）
ONLINE_STATE = {0: "离网", 1: "在网"}

# ── DI 表 ────────────────────────────────────────────────────────────

WIRELESS_DI_MAP: Dict[str, dict] = {
    "02EB0000": {
        "name": "光伏逆变器数据转发",
        "unit": "",
        "data_type": "Z|C|T|DATA",
        "length": -1,
        "group": "数据转发",
        "note": "L=07H+DATA：DI + 波特率Z(1) + 校验C(1) + 超时T(1) + 逆变器协议数据",
    },
    "04E60001": {
        "name": "下挂光伏逆变器地址列表",
        "unit": "",
        "data_type": "M|addr×M",
        "length": -1,
        "group": "无线参数",
        "note": "L=01H+6×M：有效数量 M(≤12) + M 个 6 字节通信地址（BCD 低位在前）",
    },
    "04E60002": {
        "name": "无线频段信息",
        "unit": "",
        "data_type": "NN|NNNN|NN",
        "length": 4,
        "group": "无线参数",
        "note": "调制方式(1) + 信道编号(2, BCD 低位在前) + 信道协商使能(1)",
    },
    "04900100": {
        "name": "模组组网拓扑信息",
        "unit": "",
        "data_type": "N|record×N",
        "length": -1,
        "group": "拓扑",
        "note": "数量 N(≤12) + N×(地址6 + 信号质量1 + 父节点地址6 + 保留2)=15N+1",
    },
    "04900101": {
        "name": "无线模组升级块状态字",
        "unit": "",
        "data_type": "XX…XX",
        "length": -1,
        "group": "升级",
        "note": "BIN 位图：bitN=1 表示第 N 块传输成功（N 从 0 起）",
    },
    "04900102": {
        "name": "无线模组升级状态信息",
        "unit": "",
        "data_type": "ascii32|crc32|status",
        "length": 37,
        "group": "升级",
        "note": "升级文件名(ASCII 32) + 文件校验 CRC32(BIN 4) + 升级状态(BIN 1)",
    },
    "04900103": {
        "name": "无线模组升级文件信息",
        "unit": "",
        "data_type": "ascii32|size4|crc32|chunk2|rsv32|rsv32",
        "length": 108,
        "group": "升级",
        "note": "文件名(32) + 文件大小(4) + CRC32(4) + 升级块大小(2) + 保留(32) + 保留(32)",
    },
    "04900104": {
        "name": "无线模组升级块数据",
        "unit": "",
        "data_type": "seq2|data",
        "length": -1,
        "group": "升级",
        "note": "升级块序号(BIN 2) + 升级块数据（写入方向）",
    },
    "04900105": {
        "name": "无线模组支持最大升级块大小",
        "unit": "字节",
        "data_type": "NNNN",
        "length": 2,
        "group": "升级",
        "note": "BIN 2 字节，最大 241（最小 128）",
    },
    "04900106": {
        "name": "无线模组执行升级时间",
        "unit": "",
        "data_type": "YYMMDDhhmm",
        "length": 5,
        "group": "升级",
        "note": "BCD 5 字节（645 惯例低字节在前）；全 FF = 立即执行",
    },
    "04900107": {
        "name": "无线模组版本信息",
        "unit": "",
        "data_type": "ascii",
        "length": -1,
        "group": "版本",
        "note": "ASCII 字符串，长度不定",
    },
    "028100FF": {
        "name": "无线模组在网状态",
        "unit": "",
        "data_type": "NN",
        "length": 1,
        "group": "在网状态",
        "note": "0=离网、1=在网（控制码 1EH 上报 / 9EH 确认）",
    },
}

WIRELESS_DI_CODES = tuple(WIRELESS_DI_MAP)


def is_wireless_di(di_code: str) -> bool:
    """该 DI 是否属于本手册（无线模组接口）扩展。"""
    return str(di_code or "").upper() in WIRELESS_DI_MAP


def merge_wireless_di_map(base: Optional[dict]) -> dict:
    """把无线扩展 DI 并入通用 DI 表（覆盖同名键 —— 见模块头的 04E60001 说明）。"""
    merged = dict(base or {})
    for code, info in WIRELESS_DI_MAP.items():
        merged[code] = {
            "name": info["name"],
            "unit": info["unit"],
            "data_type": info["data_type"],
            "length": info["length"],
        }
    return merged


# ── 控制码扩展语义 ───────────────────────────────────────────────────


def control_extra(di_code: str, ctrl: int) -> str:
    """本手册扩展的控制码语义（不污染通用 FUNC_NAMES，因为方向语义相反）。

    - ``06H`` / ``86H``：``0x1F`` 都是 0x06 —— 主站确认（06H）与从站主动上报（86H）
    - ``1EH`` / ``9EH``：模组在网状态上报 / 确认
    - ``11H`` / ``91H`` / ``D1H``：数据转发请求 / 应答 / 异常应答（仅当 DI 是本手册的）
    """
    func = ctrl & 0x1F
    up = bool(ctrl & 0x80)          # D7：1 = 从站/模组方向
    exc = bool(ctrl & 0x40)         # D6：1 = 异常应答
    if func == 0x06:
        return ("主动上报（从站上报数据，手册 §4.1.2）" if up
                else "主动上报确认应答（主站确认，手册 §4.1.2）")
    if func == 0x1E:
        return ("模组在网状态确认（手册 §4.3.1）" if up
                else "模组在网状态上报（手册 §4.3.1）")
    if func in (0x11, 0x12) and is_wireless_di(di_code):
        code = str(di_code or "").upper()
        if code == "02EB0000":
            if exc:
                return "数据转发异常应答（手册 §4.1.3）"
            return ("数据转发应答（手册 §4.1.3）" if up
                    else "数据转发送达请求（手册 §4.1.3）")
        # 其余无线 DI 走标准「读数据」语义（04E6000x / 049001xx 都是读模组参数）
        return ("读模组数据应答（手册 §4.2）" if up else "读模组数据请求（手册 §4.2）")
    return ""


# ── 小工具 ───────────────────────────────────────────────────────────

def _bcd_str(raw: bytes) -> Optional[str]:
    """BCD 字节 → 数字串（低字节在前，645 惯例）。含非 BCD nibble 返回 None。"""
    digits = ""
    for b in reversed(raw):
        hi, lo = b >> 4, b & 0x0F
        if hi > 9 or lo > 9:
            return None
        digits += f"{hi}{lo}"
    return digits


def _rev_bcd_addr(raw: bytes) -> str:
    """6 字节通信地址（BCD 低位在前）→ 展示用字符串；非 BCD 时退回 HEX。"""
    text = _bcd_str(raw)
    return text if text else raw[::-1].hex().upper()


def _hex(raw: bytes) -> str:
    return raw.hex().upper()


def _u(raw: bytes) -> Optional[int]:
    """BIN 小端整数（645 惯例；手册未另注字节序时按低字节在前）。"""
    if not raw:
        return None
    return int.from_bytes(raw, "little")


def baud_text(mask: int) -> str:
    """通信速率特征字 → 文本（仅置位的那一位有效）。"""
    names = [f"{rate}bps" for bit, rate in BAUD_MASK_BITS if mask & (1 << bit)]
    if len(names) == 1:
        return names[0]
    if not names:
        return "无（特征字为 0，手册注：仅某一位为 1 时有效）"
    return "多位同时置位（非法）：" + " / ".join(names)


def parity_text(value: int) -> str:
    return PARITY_NAMES.get(value, f"保留值 {value}（手册仅定义 0/1/2）")


def err_bits_text(err: int) -> str:
    hits = [name for bit, name in ERR_BITS if err & (1 << bit)]
    return "｜".join(hits) if hits else "无错误位置位"


def upgrade_status_text(code: int) -> str:
    return UPGRADE_STATUS.get(code, f"未定义状态（0x{code:02X}）")


# ── 各 DI 的解码 ─────────────────────────────────────────────────────

def _decode_transfer(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """02EB0000：波特率 Z + 校验 C + 超时 T + 逆变器数据。"""
    if len(body) < 3:
        rows.append(("  └ ⚠ 数据域不足", _hex(body), f"{len(body)} 字节",
                     "数据转发应含 3 字节参数（波特率/校验/超时）+ 逆变器数据"))
        return
    z, c, t = body[0], body[1], body[2]
    rows.append(("  └ 波特率特征字 Z", f"{z:02X}H", baud_text(z),
                 "§4.1.3 通信速率特征字：bit0=115200、bit1=600、bit2=1200、bit3=2400、"
                 "bit4=4800、bit5=9600、bit6=19200、bit7=38400；仅某一位为 1 时有效"))
    rows.append(("  └ 校验方式 C", f"{c:02X}H", parity_text(c),
                 "§4.1.3：0=无校验、1=奇校验、2=偶校验"))
    # 手册 §3.1：「超时字段 T（BCD 码）」—— 0x10 表示 10（1000ms），不是 16
    _t_digits = _bcd_str(bytes([t]))
    t_value = int(_t_digits) if _t_digits else t
    rows.append(("  └ 超时 T", f"{t:02X}H",
                 (f"{t_value * 100} ms（BCD 值 {t_value} × 100ms）" if t_value
                  else "0（手册：T=0 时模组默认 5 秒超时）"),
                 "§4.1.3 + §3.1：单位 100ms，字段为 BCD 码（0x10 → 10 → 1000ms）；T=0 → 默认 5s"))
    data_part = body[3:]
    rows.append(("  └ 逆变器协议数据", _hex(data_part) if data_part else "（无）",
                 f"{len(data_part)} 字节" if data_part else "无转发数据",
                 "透传给光伏逆变器的 DL/T645（或厂家）报文原文，未做二次解码"))


def _decode_addr_list(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04E60001：数量 M + M×6 地址。"""
    if not body:
        rows.append(("  └ ⚠ 数据域不足", "", "0 字节", "应含 1 字节数量 M"))
        return
    m = body[0]
    rows.append(("  └ 有效数量 M", f"{m}", f"{m} 台" if m else "0 台（无下挂）",
                 "§4.2.2：M≤12，地址按顺序对应光伏接入单元逻辑地址 01、02、03…"))
    payload = body[1:]
    need = m * 6
    if len(payload) < need:
        rows.append(("  └ ⚠ 地址数据不足", _hex(payload), f"{len(payload)} 字节",
                     f"按数量 M={m} 应带 {need} 字节地址数据"))
    for i in range(min(m, len(payload) // 6)):
        chunk = payload[i * 6:(i + 1) * 6]
        rows.append((f"  └ 光伏接入单元{i + 1} 地址", _hex(chunk),
                     _rev_bcd_addr(chunk),
                     f"逻辑地址 {i + 1:02d}；BCD 低位在前"))
    extra = len(payload) - need
    if extra > 0:
        rows.append(("  └ ※ 多余字节", _hex(payload[need:]), f"{extra} 字节",
                     "超出 M×6 的尾部数据（手册未定义，原样展示）"))


def _decode_band(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04E60002：调制方式 + 信道（BCD 2 字节）+ 协商使能。"""
    if len(body) < 4:
        rows.append(("  └ ⚠ 数据域不足", _hex(body), f"{len(body)} 字节",
                     "无线频段信息应含 4 字节（调制 1 + 信道 2 + 使能 1）"))
        return
    mod = body[0]
    chan_raw = body[1:3]
    chan = _bcd_str(chan_raw)
    enable = body[3]
    rows.append(("  └ 无线调制方式", f"{mod}", MODULATION_NAMES.get(mod, f"保留值 {mod}"),
                 "§4.2.1：2=500kHz、3=200kHz；1 备用"))
    rows.append(("  └ 无线信道编号", _hex(chan_raw),
                 (f"{int(chan)}（BCD，低字节在前）" if chan and chan.isdigit()
                  else "非 BCD（原样展示）"),
                 "§4.2.1 v1.3：信道为 2 字节 BCD；调制 3 → 1~200，调制 2 → 1~79"))
    rows.append(("  └ 信道协商使能", f"{enable}",
                 ("允许信道协商" if enable == 1 else
                  "禁止信道协商" if enable == 0 else f"保留值 {enable}"),
                 "§4.2.1：0=禁止、1=允许（默认 1）"))


def _decode_topology(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04900100：数量 N + N×(地址6 + 质量1 + 父节点6 + 保留2)。"""
    if not body:
        rows.append(("  └ ⚠ 数据域不足", "", "0 字节", "应含 1 字节数量 N"))
        return
    n = body[0]
    rows.append(("  └ 光伏接入单元数量 N", f"{n}", f"{n} 个" if n else "0 个（无节点）",
                 "§4.2.3：N≤12，每节点 15 字节（地址6 + 信号质量1 + 父节点6 + 保留2）"))
    payload = body[1:]
    rec = 15
    for i in range(min(n, len(payload) // rec)):
        chunk = payload[i * rec:(i + 1) * rec]
        addr, quality, parent, rsv = chunk[0:6], chunk[6], chunk[7:13], chunk[13:15]
        rows.append((f"  └ 节点{i + 1} 地址", _hex(addr), _rev_bcd_addr(addr),
                     "光伏接入单元通信地址（BCD 低位在前）"))
        rows.append((f"  └ 节点{i + 1} 信号质量", f"{quality}", str(quality),
                     "§4.2.3 信号质量（手册未给换算公式，按原值展示）"))
        parent_hex = _hex(parent)
        if parent_hex == "FFFFFFFFFFFF":
            rows.append((f"  └ 节点{i + 1} 父节点", parent_hex, "未入网",
                         "§4.2.3 说明：未入网时父节点地址为 FFFFFFFFFFFF"))
        else:
            rows.append((f"  └ 节点{i + 1} 父节点", parent_hex, _rev_bcd_addr(parent),
                         "§4.2.3 父节点通信地址（BCD 低位在前）"))
        rows.append((f"  └ 节点{i + 1} 保留", _hex(rsv), f"{len(rsv)} 字节", "手册定义为保留备用"))
    if len(payload) < n * rec:
        rows.append(("  └ ⚠ 拓扑数据不足", _hex(payload), f"{len(payload)} 字节",
                     f"按 N={n} 应带 {n * rec} 字节（每节点 15 字节）"))


def _decode_block_bitmap(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04900101：升级块状态字（BIN 位图）。"""
    total_bits = len(body) * 8
    done = [i for i in range(total_bits) if body[i // 8] & (1 << (i % 8))]
    rows.append(("  └ 状态字原始值", _hex(body), f"{len(body)} 字节（{total_bits} 位）",
                 "§4.2.4 注1：bitN=0 未传输、bitN=1 传输成功"))
    if not done:
        rows.append(("  └ 传输进度", "0", "0 / " + str(total_bits) + " 块已传输",
                     "尚无可确认的数据块"))
        return
    tail = done[-1]
    rows.append(("  └ 传输进度", f"{len(done)} 块置位",
                 f"最高置位 bit{tail}（共 {total_bits} 位可表达）",
                 "手册未给总块数的独立字段，只能按最高置位位推断已传输范围"))
    contiguous = all(i in set(done) for i in range(tail + 1))
    rows.append(("  └ 连续性", "", "连续" if contiguous else "存在空洞（中间有未传输块）",
                 "逐块核对的结论；空洞意味着中间的块缺传"))


def _decode_upgrade_status(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04900102：文件名(32 ASCII) + CRC32(4) + 状态(1)。"""
    if len(body) < 37:
        rows.append(("  └ ⚠ 数据域不足", _hex(body), f"{len(body)} 字节",
                     "升级状态信息应为 37 字节（文件名 32 + CRC32 4 + 状态 1）"))
        return
    name = body[0:32]
    crc = body[32:36]
    status = body[36]
    rows.append(("  └ 升级文件名", _hex(name),
                 name.split(b"\x00")[0].decode("ascii", "replace").strip() or "（空）",
                 "ASCII 32 字节，遇 0x00 截断"))
    rows.append(("  └ 文件校验 CRC32", _hex(crc), f"0x{_u(crc):08X}",
                 "BIN 4 字节（低字节在前）"))
    rows.append(("  └ 升级状态", f"{status}", upgrade_status_text(status),
                 "§4.2.4 注2 状态码表"))


def _decode_upgrade_file_info(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04900103：文件名(32) + 大小(4) + CRC32(4) + 块大小(2) + 保留(32) + 保留(32)。"""
    if len(body) < 108:
        rows.append(("  └ ⚠ 数据域不足", _hex(body), f"{len(body)} 字节",
                     "升级文件信息应为 108 字节（32+4+4+2+32+32）"))
        # 尽量按已有字节展示前半部分
        if len(body) >= 32:
            rows.append(("  └ 升级文件名（截断展示）", _hex(body[0:32]),
                         body[0:32].split(b"\x00")[0].decode("ascii", "replace").strip() or "（空）",
                         "数据域不足 108 字节，仅按偏移展示"))
        return
    name = body[0:32]
    size = body[32:36]
    crc = body[36:40]
    chunk = body[40:42]
    rows.append(("  └ 升级文件名", _hex(name),
                 name.split(b"\x00")[0].decode("ascii", "replace").strip() or "（空）",
                 "ASCII 32 字节"))
    rows.append(("  └ 文件大小", _hex(size), f"{_u(size)} 字节",
                 "BIN 4 字节（低字节在前）"))
    rows.append(("  └ 文件校验 CRC32", _hex(crc), f"0x{_u(crc):08X}", "BIN 4 字节"))
    chunk_size = _u(chunk)
    rows.append(("  └ 升级块大小", _hex(chunk), f"{chunk_size} 字节",
                 "BIN 2 字节；手册：最大 241、最小 128"))
    rows.append(("  └ 保留段 1", _hex(body[42:74]), "32 字节", "手册定义为保留"))
    rows.append(("  └ 保留段 2", _hex(body[74:106]) if len(body) >= 106 else "（不足）",
                 f"{len(body[74:106])} 字节", "手册定义为保留"))
    if len(body) > 106:
        rows.append(("  └ ※ 尾部多余字节", _hex(body[106:]), f"{len(body) - 106} 字节",
                     "超出 108 字节定义长度的数据，原样展示"))


def _decode_upgrade_block(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04900104：块序号(2 BIN) + 块数据。"""
    if len(body) < 2:
        rows.append(("  └ ⚠ 数据域不足", _hex(body), f"{len(body)} 字节",
                     "升级块数据应含 2 字节序号 + 块数据"))
        return
    seq = body[0:2]
    data = body[2:]
    rows.append(("  └ 升级块序号", _hex(seq), f"{_u(seq)}", "BIN 2 字节（低字节在前）"))
    rows.append(("  └ 升级块数据", _hex(data) if data else "（无）",
                 f"{len(data)} 字节" if data else "无块数据",
                 "手册原文标注「无需到装」（疑为「无需到账/无需应答」笔误，按原意即写入即可）"))


def _decode_max_block(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04900105：最大升级块大小（2 BIN）。"""
    if len(body) < 2:
        rows.append(("  └ ⚠ 数据域不足", _hex(body), f"{len(body)} 字节", "应为 2 字节"))
        return
    size = _u(body[0:2])
    rows.append(("  └ 支持最大升级块大小", _hex(body[0:2]), f"{size} 字节",
                 "BIN 2 字节（低字节在前）；手册：最大 241、最小 128"))


def _decode_upgrade_time(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04900106：执行升级时间（BCD 5 字节，YYMMDDhhmm）。"""
    if len(body) < 5:
        rows.append(("  └ ⚠ 数据域不足", _hex(body), f"{len(body)} 字节", "应为 5 字节 BCD"))
        return
    raw = body[0:5]
    if all(b == 0xFF for b in raw):
        rows.append(("  └ 执行升级时间", _hex(raw), "立即执行（全 FF）",
                     "§4.2.4 注4：全 FF 表示立即执行升级"))
        return
    digits = _bcd_str(raw)
    if not digits or len(digits) < 10:
        rows.append(("  └ 执行升级时间", _hex(raw), "非 BCD（原样展示）",
                     "手册要求 YYMMDDhhmm 的 BCD 编码"))
        return
    rows.append(("  └ 执行升级时间", _hex(raw),
                 f"20{digits[0:2]}-{digits[2:4]}-{digits[4:6]} "
                 f"{digits[6:8]}:{digits[8:10]}",
                 "BCD 5 字节 YYMMDDhhmm（低字节在前，645 惯例）；"
                 "小于设备当前时间则立即升级（§4.2.4 注4）"))


def _decode_version(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """04900107：版本信息（ASCII，不定长）。"""
    text = body.split(b"\x00")[0].decode("ascii", "replace").strip()
    rows.append(("  └ 版本信息", _hex(body) if body else "（无）",
                 text or "（空）",
                 "ASCII 不定长（§4.2.5）"))


def _decode_online(body: bytes, rows: List[Tuple[str, str, str, str]]) -> None:
    """028100FF：在网状态（1 字节）。"""
    if not body:
        rows.append(("  └ ⚠ 数据域不足", "", "0 字节", "在网状态上报应含 1 字节状态"))
        return
    state = body[0]
    rows.append(("  └ 在网状态", f"{state:02X}H",
                 ONLINE_STATE.get(state, f"保留值 {state}"),
                 "§4.3.1：0=离网、1=在网；控制码 1EH 上报、9EH 确认"))


_HANDLERS = {
    "02EB0000": _decode_transfer,
    "04E60001": _decode_addr_list,
    "04E60002": _decode_band,
    "04900100": _decode_topology,
    "04900101": _decode_block_bitmap,
    "04900102": _decode_upgrade_status,
    "04900103": _decode_upgrade_file_info,
    "04900104": _decode_upgrade_block,
    "04900105": _decode_max_block,
    "04900106": _decode_upgrade_time,
    "04900107": _decode_version,
    "028100FF": _decode_online,
}


def parse_wireless_di(
    di_code: str, ctrl: int, data: bytes
) -> Tuple[Optional[List[Tuple[str, str, str, str]]], str]:
    """无线模组接口手册扩展 DI 解析总入口。

    参数：
        di_code: 8 位 HEX DI 编码（小端解析后的文档写法，如 02EB0000）
        ctrl: 控制码字节（D7=方向，D6=异常，D0~D4=功能码）
        data: 减 0x33 后的完整数据域（含 4 字节 DI）
    返回：
        (fields 行列表, 业务名)；非本手册 DI 返回 (None, "")
    """
    code = str(di_code or "").upper()
    info = WIRELESS_DI_MAP.get(code)
    if not info:
        return None, ""

    name = info["name"]
    dir_bit = (ctrl >> 7) & 1
    func = ctrl & 0x1F
    rows: List[Tuple[str, str, str, str]] = []
    rows.append(("  └ 数据块", "", name,
                 f"南网光伏无线模组接口手册 V1.6（{info['group']}）；{info['note']}"))

    if len(data) < 4:
        rows.append(("  └ ⚠ 数据域不足", _hex(data), f"{len(data)} 字节",
                     "数据域不足 4 字节（DI 本身），无法解析"))
        return rows, name

    body = data[4:]
    # 读请求（DIR=0 + 11H）没有数据单元；但 02EB0000 的请求本身**带**参数（Z/C/T + DATA）
    if dir_bit == 0 and func == 0x11 and code != "02EB0000":
        rows.append(("  └ 数据单元", "", "无（读请求）",
                     "读数据请求不带数据单元，应答应含对应数据块"))
        return rows, name

    handler = _HANDLERS.get(code)
    if handler:
        handler(body, rows)
    else:                                  # pragma: no cover - 防御：表内新增但没接 handler
        rows.append(("  └ 数据内容(原始)", _hex(body), f"{len(body)} 字节",
                     "该 DI 尚未实现解码，原样展示"))
    return rows, name


def di_summary() -> str:
    """DI 表规模摘要（测试/自检用）。"""
    groups: Dict[str, int] = {}
    for info in WIRELESS_DI_MAP.values():
        groups[info["group"]] = groups.get(info["group"], 0) + 1
    return f"无线扩展 DI 总数 {len(WIRELESS_DI_MAP)}（" + "、".join(
        f"{k}类 {v}" for k, v in groups.items()) + "）"
