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


def is_wildcard_sa(header: dict) -> bool:
    """通配地址判定：地址类型=1 且 SA 地址字节全 0xAA。"""
    if header["addr_type"] != 1:
        return False
    body = header["sa"][1:]
    return len(body) > 0 and all(b == 0xAA for b in body)
