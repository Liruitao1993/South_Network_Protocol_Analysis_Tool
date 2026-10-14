# -*- coding: utf-8 -*-
"""南网上行通信规约（协议14，Q/CSG 11109004-2013）—— **线格式编解码唯一来源**。

依据：``协议文档/14.南网上行通信规约/中国南方电网有限责任公司计量自动化终端上行通信规约(条文解释).md``
（markitdown 由 PDF 转出，131 页；图 2/11/12/13 的版面已用 PyMuPDF 按块坐标复核）。

帧结构（5.1.1 图2 / 6.2.x 图11~15）::

    偏移  0     1..4                 5     6     7..13      14..14+m-1    -2    -1
         68H   L(2B 小端) L(2B 重复) 68H    C     A(7B)      APDU(m)       CS    16H

                                     │     └── 地址域 A = A1(3B BCD) + A2(3B BIN) + A3(1B BIN)
                                     └── 控制域 C：D7 DIR / D6 PRM / D5 FCB|ACD / D4 FCV|保留 / D3~D0 功能码

    L（2 字节，小端，BIN） = 控制域 + 地址域 + 链路用户数据 = 8 + m      （5.1.2）
    长度域 = L 重复一次 ⇒ 线上占 **4 字节**（L1 L2 L1 L2）              （5.1.2 条文解释）
    整帧长度 = L + 8                                                    （5.2.1）
    CS = 控制域 + 地址域 + 链路用户数据 全部字节的模 256 算术和          （5.1.5）

长度域为 4 字节的证据链（2026-10-10 用户指正后按 PDF 块坐标复核版面）::

    1. 5.1.2 + 图3：L 是 **2 字节** 的 16 位值（D15..D8 / D7..D0；网络传输上限 16383 亦需 16 位）。
    2. 图 2 / 图 11 / 图 12 的固定报文头逐行画出 ``68H / L / L / 68H``。图中**一行即一个字段**
       （同一张图里 A(7B)、信息点标识(2B)、数据标识编码(4B) 都各占一行），故两个 L 是**两个字段**、
       每个 2 字节 ⇒ 长度域 4 字节；若按「一行一字节」读则 L 只剩 1 字节，与图 3 直接矛盾。
    3. 【条文解释】「长度L由两个字节组成，两个重复的长度L必需完全一致，否则，此帧为无效帧」；
       5.2.1 校验项「识别2个长度L」—— 都是「2 字节的 L，重复一次」。
    4. 5.2.1「每帧接收的字符数为用户数据长度 L+8」：68H(1) + L(4) + 68H(1) + CS(1) + 16H(1) = 8 ✓
       （长度域若只有 2 字节则整帧应为 L+6，与文档不符）。

容错（AGENTS.md §8 陷阱 23/49）：切帧与解析**兼容**两种历史/异形形态 —— 单个 2 字节小端 L
（``68 Llo Lhi 68``）与 FT1.2 单字节 L 重复两次（``68 LL LL 68``），按「结构 + 能自洽到帧尾 16H + CS」
择优；**规范形态（4 字节 L）始终优先**。组帧（:func:`encode_frame`）只输出规范形态。

以上四条与 DI 字节序（**低字节在前**，表 ``E1 00 60 12`` → 线上 ``12 60 00 E1``）均由
``新一代计量自动化主站通信网络管理技术要求`` 的 13 条实帧（send/rec 成对、CS 全部自洽）实证；
DI 顺序的换算与索引见 ``csg_uplink_di.to_semantic_di`` / ``to_wire_di``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

__all__ = [
    # 常量
    "FRAME_START",
    "FRAME_END",
    "ADDR_LEN",
    "APDU_OFFSET",
    "APDU_OFFSET_L16",
    "HEADER_LEN",
    "TRAILER_LEN",
    "MIN_FRAME_LEN",
    "MIN_FRAME_LEN_L16",
    "MIN_FRAME_LEN_ANY",
    "BROADCAST_TERM_ADDR",
    "MAX_L_WIRELESS",
    "MAX_L_GPRS",
    "MAX_L_NETWORK",
    # 长度域形态
    "FORM_L16X2",
    "FORM_L16",
    "FORM_FT12",
    "FORM_NAMES",
    "FORM_LEN_FIELD",
    # 功能码
    "LINK_FC_NAMES_PRM1",
    "LINK_FC_NAMES_PRM0",
    "DIR_UP",
    "DIR_DOWN",
    # 控制域
    "decode_control",
    # 地址域
    "Addr",
    "parse_addr",
    "encode_addr",
    "format_addr",
    # 长度 / 校验
    "encode_length",
    "decode_length",
    "calc_cs",
    "check_cs",
    # 布局
    "Layout",
    "candidates",
    "resolve_layout",
    "force_layout",
    # 整帧
    "encode_frame",
    "frame_total_len",
    "frame_total_len_alt",
    "looks_like_csg_uplink",
    "split_frame",
    "extract_csg_uplink_frames",
]

# ── 常量 ──────────────────────────────────────────────────────────────

FRAME_START = 0x68
FRAME_END = 0x16
#: 地址域字节数（A1 3B + A2 3B + A3 1B）
ADDR_LEN = 7

#: 长度域形态：规范形态（L 2 字节小端 + 重复一次 ⇒ 4 字节）
FORM_L16X2 = "l16x2"
#: 兼容形态：单个 2 字节小端 L（``68 Llo Lhi 68``）
FORM_L16 = "l16"
#: 兼容形态：FT1.2 单字节 L 重复两次（两字节同值，``68 LL LL 68``）
FORM_FT12 = "ft12"

#: 各形态长度域的线上字节数
FORM_LEN_FIELD: Dict[str, int] = {FORM_L16X2: 4, FORM_L16: 2, FORM_FT12: 2}
#: 各形态的中文说明（解析器直接落表）
FORM_NAMES: Dict[str, str] = {
    FORM_L16X2: "规范形态：L 为 2 字节小端（低字节在前）并重复一次，共 4 字节（5.1.2 图2/图3 + 条文解释）",
    FORM_L16: "兼容形态：单个 2 字节小端 L（非规范形态，仅历史报文/异形设备）",
    FORM_FT12: "兼容形态：FT1.2 单字节 L 重复两次（两字节同值）",
}

#: 应用层（链路用户数据）起始偏移（规范形态）= 68H + L(4B) + 68H + C + A
APDU_OFFSET = 1 + FORM_LEN_FIELD[FORM_L16X2] + 1 + 1 + ADDR_LEN  # = 14
#: 应用层起始偏移（2 字节长度域的兼容形态）= 68H + L(2B) + 68H + C + A
APDU_OFFSET_L16 = 1 + FORM_LEN_FIELD[FORM_L16] + 1 + 1 + ADDR_LEN  # = 12
#: 帧头字节数（规范形态）= 68H + L(4B) + 68H + C + A
HEADER_LEN = APDU_OFFSET
#: 帧尾字节数 = CS + 16H
TRAILER_LEN = 2
#: 最短帧（规范形态，应用层 m=0）
MIN_FRAME_LEN = HEADER_LEN + TRAILER_LEN  # = 16
#: 最短帧（2 字节长度域形态，应用层 m=0）
MIN_FRAME_LEN_L16 = APDU_OFFSET_L16 + TRAILER_LEN  # = 14
#: 切帧/解析入口的绝对下限（任何形态都不会更短）
MIN_FRAME_LEN_ANY = MIN_FRAME_LEN_L16  # = 14

#: 系统广播终端地址（A2=FFFFFFH，5.1.4.3）
BROADCAST_TERM_ADDR = 0xFFFFFF
#: L 上限（5.1.2）
MAX_L_WIRELESS = 255
MAX_L_GPRS = 1024
MAX_L_NETWORK = 16383

#: 传输方向位 DIR
DIR_DOWN = 0  #: 下行（主站 → 终端）
DIR_UP = 1    #: 上行（终端 → 主站）

#: 启动站（PRM=1）功能码（表 2）
LINK_FC_NAMES_PRM1: Dict[int, str] = {
    0: "备用",
    1: "发送/确认（复位命令）",
    2: "备用",
    3: "备用",
    4: "发送/无回答（用户数据）",
    5: "备用",
    6: "备用",
    7: "备用",
    8: "备用",
    9: "请求/响应帧（链路测试）",
    10: "请求/响应帧（请求1级数据）",
    11: "请求/响应帧（请求2级数据）",
    12: "备用",
    13: "备用",
    14: "备用",
    15: "备用",
}
#: 从动站（PRM=0）功能码（表 3）
LINK_FC_NAMES_PRM0: Dict[int, str] = {
    0: "确认（认可）",
    1: "备用",
    2: "备用",
    3: "备用",
    4: "备用",
    5: "备用",
    6: "备用",
    7: "备用",
    8: "响应帧（用户数据）",
    9: "响应帧（否定：无所召唤的数据）",
    10: "备用",
    11: "响应帧（链路状态）",
    12: "备用",
    13: "备用",
    14: "备用",
    15: "备用",
}


# ── 控制域 C（5.1.3 图 4 / 表 2 / 表 3）────────────────────────────────


def decode_control(byte: int) -> Dict[str, object]:
    """控制域 C → 位域字典（保持中文键，供解析器直接落表）。"""
    b = byte & 0xFF
    dir_bit = (b >> 7) & 0x01
    prm = (b >> 6) & 0x01
    d5 = (b >> 5) & 0x01
    d4 = (b >> 4) & 0x01
    fc = b & 0x0F
    names = LINK_FC_NAMES_PRM1 if prm == 1 else LINK_FC_NAMES_PRM0
    return {
        "字节": b,
        "原始值": f"0x{b:02X}",
        "DIR": dir_bit,
        "传输方向": "上行（终端→主站）" if dir_bit == DIR_UP else "下行（主站→终端）",
        "PRM": prm,
        "启动标志": "启动站" if prm else "从动站",
        # D5：PRM=1 时为 FCB，PRM=0 时为 ACD
        "FCB": d5 if prm else None,
        # D4：PRM=1 时为 FCV，PRM=0 时为保留
        "FCV": d4 if prm else None,
        "ACD": None if prm else d5,   # 要求访问位（上行响应）
        "功能码": fc,
        "功能码名称": names.get(fc, "未知"),
    }


# ── 地址域 A（5.1.4 表 4）────────────────────────────────────────────


@dataclass(frozen=True)
class Addr:
    """地址域解析结果。``a1``/``a2``/``a3`` 均为「语义值」（非线上字节序）。"""

    a1: bytes          #: 省地市区县码 3 字节，顺序 [省, 地市, 区县]（每字节 2 位 BCD）
    a2: int            #: 终端地址（BIN，1~16777216）
    a3: int            #: 主站地址（BIN，0~255）

    @property
    def bcd_code(self) -> str:
        """6 位省地市区县码字符串，如 ``"440306"``。"""
        return "".join(f"{b:02X}" for b in self.a1)

    @property
    def is_broadcast(self) -> bool:
        return self.a2 == BROADCAST_TERM_ADDR


def parse_addr(raw: bytes) -> Addr:
    """7 字节线上地址域 → :class:`Addr`。

    线上顺序：``[区县码][地市码][省份码]``（A1 低字节在前）+ A2(3B 小端) + A3(1B)。
    """
    if len(raw) != ADDR_LEN:
        raise ValueError(f"地址域必须为 {ADDR_LEN} 字节，实际 {len(raw)} 字节")
    a1_wire = raw[0:3]
    # 低字节在前 → 语义 [省, 地市, 区县] = 逆序
    a1 = bytes(reversed(a1_wire))
    a2 = int.from_bytes(raw[3:6], "little")
    a3 = raw[6]
    return Addr(a1=a1, a2=a2, a3=a3)


def encode_addr(a1_bcd: str | bytes, a2: int, a3: int = 0) -> bytes:
    """语义地址 → 7 字节线上地址域（A1 低字节在前）。"""
    if isinstance(a1_bcd, str):
        s = a1_bcd.strip().replace(" ", "").replace("-", "")
        if len(s) != 6 or any(c not in "0123456789abcdefABCDEF" for c in s):
            raise ValueError(f"省地市区县码应为 6 位十六进制/BCD 数字，实际 {a1_bcd!r}")
        a1 = bytes.fromhex(s)
    else:
        a1 = bytes(a1_bcd)
        if len(a1) != 3:
            raise ValueError(f"省地市区县码应为 3 字节，实际 {len(a1)} 字节")
    if not (0 <= a2 <= 0xFFFFFF):
        raise ValueError(f"终端地址越界（0~16777215）：{a2}")
    if not (0 <= a3 <= 0xFF):
        raise ValueError(f"主站地址越界（0~255）：{a3}")
    return bytes(reversed(a1)) + a2.to_bytes(3, "little") + bytes([a3])


def format_addr(addr: Addr) -> str:
    """地址域可读串：``省地市区县码=440306 终端地址=1234567 主站地址=0``。"""
    return f"省地市区县码={addr.bcd_code} 终端地址={addr.a2} 主站地址={addr.a3}"


# ── 长度 L 与校验和 CS ────────────────────────────────────────────────


def encode_length(n: int, form: str = FORM_L16X2) -> bytes:
    """用户数据长度 → 长度域线上字节（**小端**，见 5.2「低字节在前，高字节在后」）。

    ``form=FORM_L16X2``（默认，规范形态）→ 4 字节：``Llo Lhi Llo Lhi``（重复一次）；
    ``form=FORM_L16`` → 2 字节；``form=FORM_FT12`` → 2 字节同值（L ≤ 255）。
    """
    if not (0 <= n <= 0xFFFF):
        raise ValueError(f"长度 L 越界（0~65535）：{n}")
    two = n.to_bytes(2, "little")
    if form == FORM_L16X2:
        return two + two
    if form == FORM_L16:
        return two
    if form == FORM_FT12:
        if n > MAX_L_WIRELESS:
            raise ValueError(f"FT1.2 长度形态单字节上限 255，实际 {n}")
        return bytes([n, n])
    raise ValueError(f"未知长度域形态：{form!r}")


def decode_length(lo: int, hi: int) -> int:
    """2 字节（低、高）→ 16 位长度值。"""
    return (lo & 0xFF) | ((hi & 0xFF) << 8)


def calc_cs(body: bytes) -> int:
    """CS = 控制域 + 地址域 + 链路用户数据 的模 256 算术和（5.1.5）。"""
    return sum(body) & 0xFF


# ── 长度域形态与帧布局 ───────────────────────────────────────────────


@dataclass(frozen=True)
class Layout:
    """一帧的「长度域形态 + 各字段偏移」解析结果（偏移均相对帧首）。"""

    form: str            #: FORM_L16X2 / FORM_L16 / FORM_FT12
    value: int           #: L 值（控制域 + 地址域 + 链路用户数据 的字节数）
    length_raw: bytes    #: 长度域线上原始字节（4B 或 2B）
    start2_index: int    #: 第二个起始字符 68H 的下标
    c_index: int         #: 控制域 C 的下标
    addr_index: int      #: 地址域 A 起始下标

    @property
    def len_field(self) -> int:
        """长度域线上字节数（4 或 2）。"""
        return FORM_LEN_FIELD[self.form]

    @property
    def apdu_offset(self) -> int:
        """应用层（链路用户数据）起始偏移。"""
        return self.addr_index + ADDR_LEN

    @property
    def fixed_len(self) -> int:
        """除应用层外的固定开销 = 68H(1) + 长度域 + 68H(1) + CS(1) + 16H(1)。"""
        return self.len_field + 4

    @property
    def total(self) -> int:
        """按长度域推算的整帧字节数（规范形态 = L+8，兼容形态 = L+6）。"""
        return self.value + self.fixed_len

    @property
    def is_canonical(self) -> bool:
        return self.form == FORM_L16X2


def _make_layout(data: bytes, start: int, form: str) -> Layout:
    """按形态与帧首下标构造 :class:`Layout`（不做结构校验，读长度域原始字节）。

    ⚠ 各下标记为**相对帧首**（``start=0`` 时即绝对下标）；``data`` 只用于取长度域字节。
    """
    n = FORM_LEN_FIELD[form]
    raw = bytes(data[start + 1:start + 1 + n])
    lo = raw[0] if len(raw) > 0 else 0
    hi = raw[1] if len(raw) > 1 else 0
    value = lo if form == FORM_FT12 else decode_length(lo, hi)
    start2 = 1 + n
    c_index = start2 + 1
    addr_index = c_index + 1
    return Layout(form=form, value=value, length_raw=raw, start2_index=start2,
                  c_index=c_index, addr_index=addr_index)


def candidates(data: bytes, start: int = 0) -> List[Layout]:
    """列出 ``data[start:]`` 处**结构成立**的长度域形态候选（规范形态优先）。"""
    out: List[Layout] = []
    n = len(data)
    if start >= n or data[start] != FRAME_START:
        return out
    # ① 规范形态：68H L(2B) L(2B 重复) 68H
    if start + 5 < n and data[start + 5] == FRAME_START:
        if data[start + 1] == data[start + 3] and data[start + 2] == data[start + 4]:
            lay = _make_layout(data, start, FORM_L16X2)
            if 8 <= lay.value <= MAX_L_NETWORK:
                out.append(lay)
    # ② 兼容形态：单个 2 字节小端 L（68H Llo Lhi 68H）
    if start + 3 < n and data[start + 3] == FRAME_START:
        lay = _make_layout(data, start, FORM_L16)
        if 8 <= lay.value <= MAX_L_NETWORK:
            out.append(lay)
    # ③ 兼容形态：FT1.2 单字节 L 重复两次（68H LL LL 68H）
    if start + 3 < n and data[start + 1] == data[start + 2]:
        lay = _make_layout(data, start, FORM_FT12)
        if 8 <= lay.value <= MAX_L_WIRELESS:
            out.append(lay)
    return out


def _layout_ok(frame: bytes, lay: Layout) -> bool:
    """CS 是否自洽（不足一帧返回 False）。"""
    if len(frame) < lay.apdu_offset + TRAILER_LEN:
        return False
    return calc_cs(frame[lay.c_index:-TRAILER_LEN]) == frame[-TRAILER_LEN]


def resolve_layout(frame: bytes) -> Optional[Layout]:
    """从结构候选里挑出最可信的布局；无结构候选返回 None。

    打分（高者胜）：① 长度域声明的整帧长 == 实际帧长；② 末字节为 16H；③ CS 自洽；
    ④ 同分时**规范形态优先**（候选顺序即优先级）。
    """
    cands = candidates(frame, 0)
    if not cands:
        return None

    def score(i: int) -> Tuple[int, int, int, int]:
        lay = cands[i]
        return (
            1 if lay.total == len(frame) else 0,
            1 if (frame and frame[-1] == FRAME_END) else 0,
            1 if _layout_ok(frame, lay) else 0,
            -i,
        )

    return cands[max(range(len(cands)), key=score)]


def force_layout(frame: bytes) -> Layout:
    """解析器专用兜底：**永不返回 None**（帧头/长度域异常时按规范形态尽力而为）。"""
    lay = resolve_layout(frame)
    if lay is not None:
        return lay
    if len(frame) >= 1 + FORM_LEN_FIELD[FORM_L16X2]:
        return _make_layout(frame, 0, FORM_L16X2)
    return _make_layout(frame, 0, FORM_L16 if len(frame) >= 3 else FORM_FT12)


def check_cs(frame: bytes, layout: Optional[Layout] = None) -> bool:
    """整帧 CS 是否自洽（帧长不足返回 False）。"""
    lay = layout if layout is not None else resolve_layout(frame)
    if lay is None:
        return False
    return _layout_ok(frame, lay)


# ── 组帧与整帧长度 ───────────────────────────────────────────────────


def encode_frame(c: int, addr: bytes, apdu: bytes, form: str = FORM_L16X2) -> bytes:
    """按线格式组装一整帧（唯一实现；组帧页/预设库/测试共用）。

    ``L = 控制域 + 地址域 + 链路用户数据 = 8 + len(apdu)``；CS 覆盖控制域+地址域+应用层。
    """
    if len(addr) != ADDR_LEN:
        raise ValueError(f"地址域必须为 {ADDR_LEN} 字节，实际 {len(addr)} 字节")
    c &= 0xFF
    value = 8 + len(apdu)
    head = bytes([FRAME_START]) + encode_length(value, form) + bytes([FRAME_START, c]) + bytes(addr)
    return head + bytes(apdu) + bytes([calc_cs(bytes([c]) + bytes(addr) + bytes(apdu)), FRAME_END])


def frame_total_len(frame: bytes) -> Optional[int]:
    """按最可信布局计算整帧长度（规范形态 = L+8，兼容形态 = L+6）；越界返回 None。"""
    lay = resolve_layout(frame)
    if lay is None:
        return None
    n = lay.total
    if not (MIN_FRAME_LEN_L16 <= n <= MAX_L_NETWORK + FORM_LEN_FIELD[FORM_L16X2] + 4):
        return None
    return n


def frame_total_len_alt(frame: bytes) -> Optional[int]:
    """按 FT1.2 形态（两个长度字节相同，取单字节值）计算整帧长度；越界返回 None。"""
    if len(frame) < 4:
        return None
    lo, hi = frame[1], frame[2]
    if lo != hi:
        return None
    n = lo + 6
    return n if MIN_FRAME_LEN_L16 <= n <= MAX_L_NETWORK + 6 else None


def looks_like_csg_uplink(frame: bytes) -> bool:
    """是否为可自洽切帧的南网上行帧（起始 68H、末字节 16H、长度域/CS 自洽）。"""
    if len(frame) < MIN_FRAME_LEN_ANY:
        return False
    if frame[0] != FRAME_START or frame[-1] != FRAME_END:
        return False
    lay = resolve_layout(frame)
    if lay is None:
        return False
    return _layout_ok(frame, lay)


def split_frame(frame: bytes) -> Optional[Dict[str, object]]:
    """把「恰好一帧」的字节切成外层三段（长度/CS 均自洽才返回，否则 None）。

    返回 ``{"l": L 值, "form": 形态, "len_field": 长度域字节数, "c": 控制域字节,
    "addr": Addr, "apdu": bytes, "cs": 帧内 CS, "cs_calc": 计算 CS, "cs_ok": bool,
    "len_form": form}``（``len_form`` 为历史键名，与 ``form`` 同值）。
    """
    if len(frame) < MIN_FRAME_LEN_ANY or frame[-1] != FRAME_END:
        return None
    lay = resolve_layout(frame)
    if lay is None or not _layout_ok(frame, lay):
        return None
    return {
        "l": lay.value,
        "form": lay.form,
        "len_form": lay.form,
        "len_field": lay.len_field,
        "c": frame[lay.c_index],
        "addr": parse_addr(frame[lay.addr_index:lay.apdu_offset]),
        "apdu": frame[lay.apdu_offset:-TRAILER_LEN],
        "cs": frame[-TRAILER_LEN],
        "cs_calc": calc_cs(frame[lay.c_index:-TRAILER_LEN]),
        "cs_ok": True,
    }


def extract_csg_uplink_frames(buf: bytes) -> List[bytes]:
    """从字节流中按帧首 + 长度域定长切出完整帧（**不按 0x16 扫描**）。

    逐候选（规范 4 字节 L → 2 字节 L → FT1.2 双同值）尝试，只收录「结尾为 16H 且 CS 自洽」
    的切法，避免把 698.45/645 之类同前缀帧切进来。
    """
    data = bytes(buf)
    out: List[bytes] = []
    i = 0
    n = len(data)
    while i + MIN_FRAME_LEN_ANY <= n:
        if data[i] != FRAME_START:
            i += 1
            continue
        matched = None
        for lay in candidates(data, i):
            end = i + lay.total
            if end > n:
                continue
            if data[end - 1] == FRAME_END and calc_cs(data[i + lay.c_index:end - TRAILER_LEN]) == data[end - TRAILER_LEN]:
                matched = end
                break
        if matched is None:
            i += 1
            continue
        out.append(data[i:matched])
        i = matched
    return out
