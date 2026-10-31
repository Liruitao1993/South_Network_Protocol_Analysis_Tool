# -*- coding: utf-8 -*-
"""698.45 链路层：字节流帧提取与帧头解析。

帧结构：68 L L C SA... CA HCS(2) APDU FCS(2) 16
- L 为小端 2 字节，帧总长 = L + 2（不含起始符 68 和结束符 16 的说法以解析器实现为准：
  DLT69845Parser 校验 L = 帧长 - 2）
- C 控制域：D7 DIR / D6 PRM / D5 分帧 / D4 / D3 扰码 / D2~D0 功能码
- SA 首字节为地址标志：D7~D6 地址类型(0单/1通配/2组/3广播)、D5 逻辑地址、D4~D0 地址长度 N-1
"""
from typing import List, Tuple

FRAME_START = 0x68
FRAME_END = 0x16

# 地址类型（地址特征字节 bit6~bit7，DL/T 698.45 §6.2.4.2）
ADDR_SINGLE = 0     # 单地址
ADDR_WILD = 1       # 通配地址（每字节高低 4 位可为通配符 AH）
ADDR_GROUP = 2      # 组地址（对群组内服务器有效，无需应答）
ADDR_BROADCAST = 3  # 广播地址（长度固定 1 字节 = AAH，无需应答）

# 主站把「全 99 / 全 AA」当广播/通配用的两种常见写法（非标准但实测存在）
BROADCAST_BYTES = (0x99, 0xAA)


def extract_frames(buf: bytes) -> Tuple[List[bytes], int, bytes]:
    """从字节流中提取完整 698 帧。

    返回 (完整帧列表, 已消费字节数, 剩余未消费字节)。
    - 跳过 FE 前缀与杂字节（在 68 之前同步）
    - 长度域声明未到齐时保留剩余（分片/粘包处理）
    - 结束符不符时丢弃该 68 继续找下一个
    """
    frames: List[bytes] = []
    pos = 0
    n = len(buf)
    while pos < n:
        # 找下一个 68
        i = buf.find(FRAME_START, pos)
        if i < 0:
            return frames, n - pos, b""
        if i + 3 > n:
            # 长度域不完整，保留
            return frames, i, buf[i:]
        if _is_645_frame(buf, i):
            pos = i + _645_total(buf, i)
            continue
        length = int.from_bytes(buf[i + 1:i + 3], "little") & 0x3FFF
        total = length + 2  # 帧总长含 68 与 16
        if i + total > n:
            # 帧未收全，保留
            return frames, i, buf[i:]
        if buf[i + total - 1] != FRAME_END:
            # 结束符不符，跳过这个 68 继续找
            pos = i + 1
            continue
        frames.append(buf[i:i + total])
        pos = i + total
    return frames, n - pos, b""


def _645_total(buf: bytes, i: int) -> int:
    """645 帧总长（68 + 6B 地址 + 68 + C + L + 数据 + CS + 16）。"""
    return 10 + buf[i + 9] + 2


def _is_645_frame(buf: bytes, i: int) -> bool:
    """判断 buf[i:] 是否是完整且校验正确的 645 帧（DL/T 645-2007）。

    698 虚拟表与 645 虚拟表可能挂在同一条总线上：被测模组会发 645 广播（如
    「STA 硬件初始化」68 AA×6 68 14 0C ... 16）。这类帧若按 698 长度域解析
    （AA AA & 0x3FFF = 0x2AAA）会被当成 10924 字节的巨帧，缓冲一直等不齐，
    后续所有 698 请求都被卡住 —— 所以这里必须显式识别并跳过。
    """
    if i + 10 > len(buf) or buf[i + 7] != FRAME_START:
        return False
    total = _645_total(buf, i)
    if i + total > len(buf):
        return False
    if buf[i + total - 1] != FRAME_END:
        return False
    return (sum(buf[i:i + total - 2]) & 0xFF) == buf[i + total - 2]


def extract_645_frames(buf: bytes) -> List[bytes]:
    """从字节流中取出全部完整 645 帧（供 698 虚拟表处理 645 厂家命令）。"""
    out: List[bytes] = []
    i, n = 0, len(buf)
    while i < n:
        j = buf.find(FRAME_START, i)
        if j < 0:
            break
        if not _is_645_frame(buf, j):
            i = j + 1
            continue
        total = _645_total(buf, j)
        out.append(bytes(buf[j:j + total]))
        i = j + total
    return out


def parse_header(frame: bytes) -> dict:
    """解析帧头。返回 dict：
    control, dir, prm, func, sa_feature, addr_type(0单/1通配/2组/3广播),
    sa_len, sa(bytes, 含特征字节), ca, apdu(bytes)
    """
    control = frame[3]
    feature = frame[4]
    sa_len = (feature & 0x1F) + 1
    addr_type = (feature >> 6) & 0x03
    sa = frame[4:5 + sa_len]
    ca = frame[5 + sa_len]
    # CA(1) + HCS(2) 后为 APDU，FCS 2 字节在尾
    apdu = frame[6 + sa_len + 2:-3]
    return {
        "control": control,
        "dir": (control >> 7) & 1,
        "prm": (control >> 6) & 1,
        "seg": (control >> 5) & 1,
        "func": control & 0x07,
        "sa_feature": feature,
        "addr_type": addr_type,
        "sa_len": sa_len,
        "sa": sa,
        "ca": ca,
        "apdu": apdu,
    }


def sa_body(header: dict) -> bytes:
    """SA 地址体（去掉 1 字节地址特征），线序即帧内顺序（低字节在前）。"""
    return header["sa"][1:]


def is_wildcard_sa(header: dict) -> bool:
    """通配地址判定：地址类型=1。地址体是否覆盖本机另由 wildcard_matches 判断。"""
    return header["addr_type"] == ADDR_WILD


def is_all_aa(header: dict) -> bool:
    """全 AA 通配（6 字节 AAH）——最常见的「读通信地址」发现式请求。"""
    body = sa_body(header)
    return len(body) > 0 and all(b == 0xAA for b in body)


def is_broadcast_sa(header: dict) -> bool:
    """广播类地址：标准广播（类型=3，1 字节 AAH）/ 全 99 / 全 AA 单地址写法。

    类型=1 的全 AA 属通配（见 is_all_aa），这里不吞掉它。
    """
    if header["addr_type"] == ADDR_WILD:
        return False
    if header["addr_type"] == ADDR_BROADCAST:
        return True
    body = sa_body(header)
    return bool(body) and all(b in BROADCAST_BYTES for b in body)


def nibble_match(pattern: bytes, addr: bytes) -> bool:
    """逐半字节比对通配地址（AH 表示该十进制位可为 0~9 任意值）。"""
    n = min(len(pattern), len(addr))
    if n == 0:
        return False
    for i in range(n):
        p_hi, p_lo = pattern[i] >> 4, pattern[i] & 0x0F
        a_hi, a_lo = addr[i] >> 4, addr[i] & 0x0F
        if p_hi != 0xA and p_hi != a_hi:
            return False
        if p_lo != 0xA and p_lo != a_lo:
            return False
    return True


def wildcard_matches(pattern_body: bytes, own_body: bytes) -> bool:
    """通配地址是否命中本机地址。

    - 全 AA / 全 99 → 视为全通配（主站发现式请求）；
    - 其余按半字节通配比对本机地址体（线序一致，均为低字节在前）。
    """
    if not pattern_body or not own_body:
        return False
    if all(b in BROADCAST_BYTES for b in pattern_body):
        return True
    return nibble_match(pattern_body, own_body)


def classify_address(header: dict, own_body: bytes,
                     strict: bool) -> Tuple[str, bool]:
    """判定请求寻址类别与本机是否应答。

    返回 ``(类别, 是否应答)``，类别 ∈ single/wildcard/group/broadcast。
    组地址按协议「无需应答」直接判否（由上层记日志）。
    """
    addr_type = header["addr_type"]
    body = sa_body(header)
    if addr_type == ADDR_GROUP:
        return "group", False
    if is_broadcast_sa(header):
        return "broadcast", True
    if addr_type == ADDR_WILD:
        return "wildcard", wildcard_matches(body, own_body)
    if not strict:
        return "single", True
    return "single", body == own_body

