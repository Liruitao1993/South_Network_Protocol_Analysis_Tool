"""模组化终端功能模块接口协议组帧（纯逻辑，无 Qt）。

帧：68 | L(2B LE, 数据域长度) | C(2B LE) | Data | FCS(2B LE) | 16
FCS = CRC-16/PPP(x-25)(L+C+Data)
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Union

from modular_iface_parser import calc_fcs


def axdr_uint(val: int, unsigned8: bool = False) -> bytes:
    """long-unsigned(0x12) 或 unsigned(0x11)，大端 BER 长度。"""
    if val < 0:
        raise ValueError("unsigned 不能为负")
    if unsigned8:
        if val > 0xFF:
            raise ValueError("unsigned 超出 0~255")
        return bytes((0x11, 0x01, val))
    if val <= 0xFF:
        body = bytes((val,))
    elif val <= 0xFFFF:
        body = val.to_bytes(2, "big")
    elif val <= 0xFFFFFFFF:
        body = val.to_bytes(4, "big")
    else:
        body = val.to_bytes(8, "big")
    return bytes((0x12, len(body))) + body


def axdr_visible(s: Union[str, bytes]) -> bytes:
    raw = s.encode("ascii") if isinstance(s, str) else bytes(s)
    if len(raw) > 0x7F:
        raise ValueError("visible-string 过长")
    return bytes((0x0A, len(raw))) + raw


def encode_dt(dta1: int, dta2: int, dtb: int) -> bytes:
    """DT 2 字节 LE：bit15~11=DTA1, bit10~8=DTA2, bit7~0=DTB。"""
    if not (0 <= dta1 <= 0x1F and 0 <= dta2 <= 0x07 and 0 <= dtb <= 0xFF):
        raise ValueError("DT 字段超范围")
    val = ((dta1 & 0x1F) << 11) | ((dta2 & 0x07) << 8) | (dtb & 0xFF)
    return val.to_bytes(2, "little")


def encode_control(dir_bit: int, prm: int, func: int, fid: int) -> bytes:
    c0 = ((dir_bit & 1) << 7) | ((prm & 1) << 6) | (func & 0x3F)
    c1 = fid & 0xFF
    return bytes((c0, c1))


def build_link_request(
    version: int = 1,
    model: str = "TERMINAL",
    dev_id: str = "T0001",
    max_tx: int = 256,
    max_rx: int = 256,
    window: int = 1,
) -> bytes:
    return (
        bytes((0x01,))
        + axdr_uint(version)
        + axdr_visible(model)
        + axdr_visible(dev_id)
        + axdr_uint(max_tx)
        + axdr_uint(max_rx)
        + axdr_uint(window, unsigned8=True)
    )


def build_get_request(dta1: int = 0, dta2: int = 0, dtb: int = 0x00) -> bytes:
    return bytes((0x02,)) + encode_dt(dta1, dta2, dtb)


def build_set_request(dta1: int, dta2: int, dtb: int, data_axdr: bytes) -> bytes:
    return bytes((0x03,)) + encode_dt(dta1, dta2, dtb) + bytes(data_axdr)


def build_report_notification(
    dta1: int, dta2: int, dtb: int, data_axdr: bytes
) -> bytes:
    return bytes((0x04,)) + encode_dt(dta1, dta2, dtb) + bytes(data_axdr)


def build_link_response(
    version: int = 1,
    model: str = "MODULE",
    dev_id: str = "M0001",
    max_tx: int = 256,
    max_rx: int = 256,
    window: int = 1,
    channels: Optional[Sequence[bytes]] = None,
) -> bytes:
    body = (
        bytes((0x81,))
        + axdr_uint(version)
        + axdr_visible(model)
        + axdr_visible(dev_id)
        + axdr_uint(max_tx)
        + axdr_uint(max_rx)
        + axdr_uint(window, unsigned8=True)
    )
    if channels:
        for item in channels:
            body += bytes(item)
    return body


def build_get_response_ok(dta1, dta2, dtb, data_axdr: bytes) -> bytes:
    return bytes((0x82,)) + encode_dt(dta1, dta2, dtb) + bytes((0x01,)) + bytes(
        data_axdr
    )


def build_get_response_dar(dta1, dta2, dtb, dar: int) -> bytes:
    return bytes((0x82,)) + encode_dt(dta1, dta2, dtb) + bytes((0x00, 0x16, dar & 0xFF))


def build_set_response(dta1, dta2, dtb, dar: int = 0) -> bytes:
    return bytes((0x83,)) + encode_dt(dta1, dta2, dtb) + bytes((0x16, dar & 0xFF))


def build_report_response(dta1, dta2, dtb) -> bytes:
    return bytes((0x84,)) + encode_dt(dta1, dta2, dtb)


def build_nak(error_code: int) -> bytes:
    return (error_code & 0xFFFF).to_bytes(2, "little")


def build_frame(
    data_domain: bytes,
    dir_bit: int = 0,
    prm: int = 1,
    func: int = 0x02,
    fid: int = 0,
) -> bytes:
    data_domain = bytes(data_domain)
    if len(data_domain) > 0x0FFF:
        raise ValueError("数据域超过 4095 字节")
    length = len(data_domain)
    length_field = length.to_bytes(2, "little")
    ctrl = encode_control(dir_bit, prm, func, fid)
    mid = length_field + ctrl + data_domain
    fcs = calc_fcs(mid)
    return b"\x68" + mid + fcs.to_bytes(2, "little") + b"\x16"


def build_info_frame(
    apdu: bytes, dir_bit: int = 0, prm: int = 1, fid: int = 0
) -> bytes:
    return build_frame(apdu, dir_bit=dir_bit, prm=prm, func=0x02, fid=fid)


def build_ack_frame(dir_bit: int = 0, prm: int = 0, fid: int = 0) -> bytes:
    return build_frame(b"", dir_bit=dir_bit, prm=prm, func=0x00, fid=fid)


def build_nak_frame(
    error_code: int, dir_bit: int = 0, prm: int = 0, fid: int = 0
) -> bytes:
    return build_frame(build_nak(error_code), dir_bit=dir_bit, prm=prm, func=0x01, fid=fid)


def frame_to_hex(frame: bytes) -> str:
    return " ".join(f"{b:02X}" for b in frame)


FRAME_TEMPLATES: List[dict] = [
    {
        "key": "link_req",
        "label": "链路协商请求 (LinkRequest)",
        "dir": 0,
        "prm": 1,
        "func": 0x02,
        "build": lambda: build_link_request(),
    },
    {
        "key": "get_module_info",
        "label": "读取·通用-模块信息 (Get 0000)",
        "dir": 0,
        "prm": 1,
        "func": 0x02,
        "build": lambda: build_get_request(0, 0, 0x00),
    },
    {
        "key": "get_link_neg",
        "label": "读取·通用-链路协商信息 (Get 0001)",
        "dir": 0,
        "prm": 1,
        "func": 0x02,
        "build": lambda: build_get_request(0, 0, 0x01),
    },
    {
        "key": "get_proto_ver",
        "label": "读取·通用-协议版本 (Get 0002)",
        "dir": 0,
        "prm": 1,
        "func": 0x02,
        "build": lambda: build_get_request(0, 0, 0x02),
    },
    {
        "key": "get_clock",
        "label": "读取·通用-时钟 (DTA2=1 DTB=00)",
        "dir": 0,
        "prm": 1,
        "func": 0x02,
        "build": lambda: build_get_request(0, 1, 0x00),
    },
    {
        "key": "ack",
        "label": "确认帧 (ACK)",
        "dir": 1,
        "prm": 1,
        "func": 0x00,
        "build": lambda: b"",
    },
    {
        "key": "nak",
        "label": "否认帧 (NAK 错误码0)",
        "dir": 1,
        "prm": 1,
        "func": 0x01,
        "build": lambda: build_nak(0),
    },
    {
        "key": "link_rsp",
        "label": "链路协商响应 (LinkResponse)",
        "dir": 1,
        "prm": 0,
        "func": 0x02,
        "build": lambda: build_link_response(),
    },
]


def build_from_template(key: str, fid: int = 0) -> bytes:
    for t in FRAME_TEMPLATES:
        if t["key"] == key:
            payload = t["build"]()
            return build_frame(
                payload, dir_bit=t["dir"], prm=t["prm"], func=t["func"], fid=fid
            )
    raise KeyError(f"未知模板: {key}")
