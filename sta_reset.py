# -*- coding: utf-8 -*-
"""STA 硬件初始化（复位）命令 —— 645 广播写数据帧（纯逻辑，无 Qt）。

现场用途：被测模组（STA）固定在工装底座上无法断电，模组异常时用这条命令代替
上下电把它复位；645 与 698.45 两个虚拟表都支持「识别 + 下发」。

帧格式（DL/T 645-2007 写数据 C=14H，地址域 = 广播 AAH×6）::

    68 AA AA AA AA AA AA 68 14 0C  <数据域 12B，+33H 加扰>  CS  16

数据域去扰后 = DI(4B) + 密码(4B) + 操作者代码(4B)::

    01 04 A0 04 | 00 37 0A A0 | 00 00 00 00
    → DI（线上低字节在前，书写序 04A00401）、密码 00370AA0、操作者 00000000

现场实测帧（与 :func:`build_frame` 逐字节一致，见 test/test_sta_reset.py）::

    68 AA AA AA AA AA AA 68 14 0C 34 37 D3 37 33 6A 3D D3 33 33 33 33 DA 16
"""
from typing import List, Optional

from dlt645_frame_gen import DLT645FrameGenerator, encode_addr, encode_di

#: 厂家约定的「STA 硬件初始化（复位）」数据标识（书写序）
STA_RESET_DI = "04A00401"
#: 现场帧里的固定密码 / 操作者代码（去扰后的明文）
DEFAULT_PASSWORD = bytes.fromhex("00370AA0")
DEFAULT_OPERATOR = bytes(4)
#: 广播地址（AAH×6，非合法 BCD，按 hex 处理）
BROADCAST_AA = "AAAAAAAAAAAA"
#: 广播地址（999999999999，645-2007 广播口径）
BROADCAST_99 = "999999999999"
#: 现场实测帧，供文档与测试对照
REFERENCE_FRAME = bytes.fromhex(
    "68AAAAAAAAAAAA68140C3437D337336A3DD333333333DA16")

_gen = DLT645FrameGenerator()


def build_frame(address: str = BROADCAST_AA,
                password: bytes = DEFAULT_PASSWORD,
                operator: bytes = DEFAULT_OPERATOR) -> bytes:
    """组「STA 硬件初始化（复位）」帧（地址默认广播 AA×6）。"""
    if len(password) != 4 or len(operator) != 4:
        raise ValueError("密码 / 操作者代码各须 4 字节")
    payload = encode_di(STA_RESET_DI) + bytes(password) + bytes(operator)
    ctrl = _gen.build_control(0x14, dir_bit=0, err=False)  # 主站→从站 写数据
    return _gen.build_frame(address, ctrl, payload)


def build_ack_frame(request: bytes, meter_address: str = "") -> bytes:
    """单播复位请求的正常应答（94H，L=00）。地址默认回请求里的地址。"""
    if meter_address:
        addr = meter_address
    elif len(request) >= 7:
        addr = request[1:7][::-1].hex().upper()
    else:
        raise ValueError("请求帧过短，无法确定地址")
    ctrl = _gen.build_control(0x14, dir_bit=1, err=False)
    return _gen.build_frame(addr, ctrl, b"")


def is_broadcast(frame: bytes) -> bool:
    """地址域是否为广播（AA×6 或 99×6）。"""
    if len(frame) < 8:
        return False
    body = frame[1:7]
    return all(b == 0xAA for b in body) or all(b == 0x99 for b in body)


def parse_frame(frame: bytes) -> Optional[dict]:
    """解析复位帧；不是「写数据 + 该 DI」返回 None。"""
    if len(frame) < 16 or frame[0] != 0x68 or frame[7] != 0x68:
        return None
    ctrl = frame[8]
    if (ctrl & 0x80) or (ctrl & 0x1F) != 0x14:      # 非主站写数据
        return None
    length = frame[9]
    if length < 4 or len(frame) < 10 + length + 2:
        return None
    data = bytes((b - 0x33) & 0xFF for b in frame[10:10 + length])
    di = data[:4][::-1].hex().upper()
    if di != STA_RESET_DI:
        return None
    return {
        "di": di,
        "password": data[4:8].hex().upper(),
        "operator": data[8:12].hex().upper() if len(data) >= 12 else "",
        "broadcast": is_broadcast(frame),
        "address": frame[1:7][::-1].hex().upper(),
        "length": length,
    }


def is_sta_reset_frame(frame: bytes) -> bool:
    return parse_frame(frame) is not None


def describe(frame: bytes) -> str:
    """一句话说明（供日志）。"""
    info = parse_frame(frame)
    if info is None:
        return "非 STA 硬件初始化帧"
    kind = "广播" if info["broadcast"] else f"单播 {info['address']}"
    return (f"STA 硬件初始化（复位）· {kind} · DI={info['di']} "
            f"密码={info['password']} 操作者={info['operator']}")


def scan(buf: bytes) -> List[bytes]:
    """从字节流里挑出合法的 645 帧中命中复位命令的那些（CS 校验通过）。"""
    found: List[bytes] = []
    for frame in iter_645_frames(buf):
        if is_sta_reset_frame(frame):
            found.append(frame)
    return found


def iter_645_frames(buf: bytes):
    """遍历字节流中的完整 645 帧（68 + 6B 地址 + 68 + C + L + 数据 + CS + 16）。

    与 698 帧共存时用 ``buf[i + 7] == 0x68`` 作 645 头特征，并要求 CS 求和匹配，
    避免把 698 帧误当 645。
    """
    i, n = 0, len(buf)
    while i + 10 <= n:
        if buf[i] != 0x68 or buf[i + 7] != 0x68:
            i += 1
            continue
        length = buf[i + 9]
        total = 10 + length + 2
        if i + total > n:
            return
        if buf[i + total - 1] != 0x16:
            i += 1
            continue
        if (sum(buf[i:i + total - 2]) & 0xFF) != buf[i + total - 2]:
            i += 1
            continue
        yield bytes(buf[i:i + total])
        i += total
