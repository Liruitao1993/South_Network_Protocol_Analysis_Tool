# -*- coding: utf-8 -*-
"""698.45 从站响应 APDU/链路帧构造（全部字节操作）。

APDU 布局对齐标准与开源实测：
- Get-Response Normal:      85 01 PIID-ACD OAD(4) Get-Result [TimeTag=00]
- Get-Response NormalList: 85 02 PIID-ACD count OAD(4) Get-Result ×n [TimeTag=00]
- Get-Response Record:     85 03 PIID-ACD OAD(4) RCSD...（见 build_get_response_record）
- Get-Result::= CHOICE { 错误信息[0] DAR(1B枚举), 数据[1] Data(A-XDR) }
- 链接响应: 81/82 + PIID；SET/ACTION 响应: 86/87
- 安全明文+MAC: 90 00 [len] APDU 01 00 04 0A0B0C0D
链路帧统一由 DLT69845FrameGenerator._assemble_frame 组装（HCS/FCS 自动计算）。
"""
from typing import List, Optional, Tuple

from dl_t698_45_frame_gen import DLT69845FrameGenerator

DAR_OK = 0x00
DAR_OBJECT_UNDEFINED = 0x09  # 对象不存在

_frame_gen = DLT69845FrameGenerator()


def _get_result(data: Optional[bytes], dar: Optional[int]) -> bytes:
    if data is not None:
        return b"\x01" + data
    return b"\x00" + bytes([dar if dar is not None else DAR_OBJECT_UNDEFINED])


def build_get_response_normal(piid: int, oad: bytes,
                              data: Optional[bytes] = None,
                              dar: Optional[int] = None) -> bytes:
    apdu = bytes([0x85, 0x01, piid & 0xFF]) + oad + _get_result(data, dar)
    return apdu + b"\x00"  # TimeTag 无


def build_get_response_normal_list(piid: int,
                                   items: List[Tuple[bytes, Optional[bytes],
                                                     Optional[int]]]) -> bytes:
    """items: [(oad, data|None, dar|None), ...]"""
    body = b""
    for oad, data, dar in items:
        body += oad + _get_result(data, dar)
    apdu = bytes([0x85, 0x02, piid & 0xFF, len(items)]) + body
    return apdu + b"\x00"  # TimeTag 无


def build_get_response_record(piid: int, frozen_oad: bytes,
                              col_oads: List[bytes],
                              col_data: Optional[List[bytes]] = None) -> bytes:
    """记录型响应（对齐开源实测布局）：

    85 03 PIID OAD(冻结OAD4) colCount [00 colOAD(4)]×n
        01 <行数> [每行数据拼接...] 00 00
    col_data 为 None 或空 → 0 行（漏点时段）。
    """
    n = len(col_oads)
    apdu = bytes([0x85, 0x03, piid & 0xFF]) + frozen_oad + bytes([n])
    for col in col_oads:
        apdu += b"\x00" + col
    if col_data:
        apdu += b"\x01\x01" + b"".join(col_data)
    else:
        apdu += b"\x01\x00"  # 0 行
    apdu += b"\x00\x00"
    return apdu


def build_link_response(link_service: int, piid: int) -> bytes:
    """链接响应：link_service 为 0x81（预链接）或 0x82（应用链接）。"""
    return bytes([link_service, piid & 0xFF, 0x00])


def build_set_action_response(service: int, piid: int,
                              oads: List[bytes], dar: int = DAR_OK) -> bytes:
    """SET/ACTION 响应（Normal/NormalList 简化为成功 DAR）。

    service: 0x86(SET-Response) / 0x87(ACTION-Response)。
    """
    if len(oads) <= 1:
        oad = oads[0] if oads else b"\x00\x00\x00\x00"
        return bytes([service, 0x01, piid & 0xFF]) + oad + bytes([dar, 0x00])
    body = b"".join(o + bytes([dar]) for o in oads)
    return bytes([service, 0x02, piid & 0xFF, len(oads)]) + body + b"\x00"


def wrap_security_plain_mac(apdu: bytes) -> bytes:
    """安全请求（10 00 明文）响应封装：90 00 len APDU 01 00 04 MAC(0A0B0C0D)。"""
    n = len(apdu)
    if n > 255:
        len_bytes = bytes([0x82, (n >> 8) & 0xFF, n & 0xFF])
    elif n > 127:
        len_bytes = bytes([0x81, n & 0xFF])
    else:
        len_bytes = bytes([n & 0x7F])
    return b"\x90\x00" + len_bytes + apdu + b"\x01\x00\x04\x0A\x0B\x0C\x0D"


def assemble_link_frame(sa: bytes, ca: int, apdu: bytes,
                        control: int = 0xC3) -> bytes:
    """组装完整链路帧（control=0xC3：DIR=1 PRM=1 服务器响应，func=3 用户数据）。"""
    return _frame_gen._assemble_frame(sa, ca, control, apdu)
