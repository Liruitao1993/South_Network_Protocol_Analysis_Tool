"""模组化终端功能模块接口协议组帧（纯逻辑，无 Qt）。

帧（§5.2.1，**小端**）：``68H | L(2B, 数据域字节数) | C(2B) | 数据域 | FCS(2B) | 16H``，
整帧 = L + 8；FCS 覆盖 ``L + C + 数据域``（§5.2.5 / 附录 A）。

APDU 编码**一律走 `modular_iface_axdr` 单源**（大端 A-XDR），本模块只负责：
① 控制域逐位拼装；② 帧封装与长度/超长校验；③ 模板与便捷构造器。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from modular_iface_axdr import calc_fcs, encode_apdu

MAX_DATA_DOMAIN = 0x0FFF  # 长度域 bit0~bit11

#: 控制码（表2）
CTRL_ACK = 0x00
CTRL_NAK = 0x01
CTRL_INFO = 0x02

#: 表1 的 DIR/PRM 组合（便于 GUI 下拉）
DIR_PRM_OPTIONS: Tuple[Tuple[int, int, str], ...] = (
    (0, 1, "终端发起的请求"),
    (0, 0, "终端对功能模块上报的响应"),
    (1, 0, "功能模块发起的请求或上报"),
    (1, 1, "功能模块对终端请求或通知的响应"),
)


def dt_code(dta1: int, dta2: int, dtb: int) -> int:
    """把 (DTA1, DTA2, DTB) 拼成 DT 数值（**4+4+8**，依据见 `modular_iface_data.decode_dt`）。"""
    for name, val, bits in (("DTA1", dta1, 4), ("DTA2", dta2, 4), ("DTB", dtb, 8)):
        if not isinstance(val, int) or not (0 <= val < (1 << bits)):
            raise ValueError(f"{name} 必须是 0~{(1 << bits) - 1} 的整数，实得 {val!r}")
    return ((dta1 & 0x0F) << 12) | ((dta2 & 0x0F) << 8) | (dtb & 0xFF)


# ── 链路层 ────────────────────────────────────────────────────────────


def build_control(control_code: int, *, dir_bit: int = 0, prm: int = 1, fid: int = 0) -> bytes:
    """控制域 2 字节（**小端**）：低字节 = DIR|PRM|控制码，高字节 = FID。"""
    if not 0 <= int(control_code) <= 0x3F:
        raise ValueError(f"控制码必须 0~63（6 bit），实得 {control_code!r}")
    c0 = ((int(dir_bit) & 1) << 7) | ((int(prm) & 1) << 6) | (int(control_code) & 0x3F)
    return bytes((c0, int(fid) & 0xFF))


def build_frame(
    data_domain: bytes,
    *,
    dir_bit: int = 0,
    prm: int = 1,
    func: int = CTRL_INFO,
    fid: int = 0,
    control: Optional[bytes] = None,
) -> bytes:
    """按 §5.2.1 封装整帧；``control`` 显式给出时忽略 dir/prm/func/fid。"""
    domain = bytes(data_domain or b"")
    if len(domain) > MAX_DATA_DOMAIN:
        raise ValueError(
            f"数据域 {len(domain)} 字节超过长度域上限 {MAX_DATA_DOMAIN} 字节"
            "（§5.2.2 图5：bit0~bit11 只有 12 位），不截断"
        )
    ctrl = bytes(control) if control is not None else build_control(func, dir_bit=dir_bit, prm=prm, fid=fid)
    if len(ctrl) != 2:
        raise ValueError(f"控制域必须是 2 字节，实得 {len(ctrl)}")
    mid = len(domain).to_bytes(2, "little") + ctrl + domain
    return b"\x68" + mid + calc_fcs(mid).to_bytes(2, "little") + b"\x16"


def build_ack(*, dir_bit: int = 0, prm: int = 0, fid: int = 0) -> bytes:
    """确认帧：控制码 00H，**无数据域**（§5.2.4.1）⇒ 整帧 8 字节。"""
    return build_frame(b"", dir_bit=dir_bit, prm=prm, func=CTRL_ACK, fid=fid)


def build_nak(error_code: int, *, dir_bit: int = 0, prm: int = 0, fid: int = 0) -> bytes:
    """否认帧：控制码 01H，数据域 = 错误信息码 BIN 2 字节（表3）。"""
    return build_frame(
        encode_nak_domain(error_code), dir_bit=dir_bit, prm=prm, func=CTRL_NAK, fid=fid
    )


def encode_nak_domain(error_code: int) -> bytes:
    """否认帧数据域 = 错误信息码（BIN，2 字节，低字节在前）。"""
    if not 0 <= int(error_code) <= 0xFFFF:
        raise ValueError(f"错误信息码必须 0~65535，实得 {error_code!r}")
    return int(error_code).to_bytes(2, "little")


def build_info(apdu: bytes, *, dir_bit: int = 0, prm: int = 1, fid: int = 0) -> bytes:
    """信息帧：控制码 02H，数据域 = 一个完整 APDU（§5.2.4.3）。"""
    return build_frame(apdu, dir_bit=dir_bit, prm=prm, func=CTRL_INFO, fid=fid)


def frame_to_hex(frame: bytes) -> str:
    return " ".join(f"{b:02X}" for b in frame)


# ── 8 类 APDU（表13~表21，编码走 modular_iface_axdr）─────────────────


def build_link_request(
    version: int = 1,
    model: str = "TERMINAL",
    dev_id: str = "T0001",
    max_tx: int = 256,
    max_rx: int = 256,
    window: int = 1,
) -> bytes:
    """表14 LinkRequest：6 个成员（协议版本号/终端设备型号/终端设备ID/发送缓冲区/接收缓冲区/窗口数）。"""
    return encode_apdu(
        "LinkRequest",
        fields=[version, model, dev_id, max_tx, max_rx, window],
    )


def build_link_response(
    version: int = 1,
    model: str = "MODULE",
    dev_id: str = "M0001",
    max_tx: int = 256,
    max_rx: int = 256,
    window: int = 1,
    channels: Iterable[Any] = ((1, 0),),
) -> bytes:
    """表18 LinkResponse：6 成员 + 虚拟通道工作模式。"""
    return encode_apdu(
        "LinkResponse",
        fields=[version, model, dev_id, max_tx, max_rx, window],
        channels=channels,
    )


def build_get_request(dt: int) -> bytes:
    """表15 GetRequestNormal：仅一个信息类标识 DT。"""
    return encode_apdu("GetRequest", dt=dt)


def build_set_request(dt: int, value: Any = None, type_name: str = "NULL") -> bytes:
    """表16 SetRequest：DT + Data。"""
    return encode_apdu("SetRequest", dt=dt, data_value=value, data_type=type_name)


def build_report_notification(dt: int, value: Any = None, type_name: str = "NULL") -> bytes:
    """表17 ReportNotification：A-ResultNormal = DT + Get-Result（按数据分支）。"""
    return encode_apdu("ReportNotification", dt=dt, data_value=value, data_type=type_name)


def build_get_response_data(dt: int, value: Any = None, type_name: str = "NULL") -> bytes:
    """表19 GetResponse 的「数据」分支：DT + Get-Result[1] Data。"""
    return encode_apdu("GetResponse", dt=dt, data_value=value, data_type=type_name)


def build_get_response_dar(dt: int, dar: int = 0) -> bytes:
    """表19 GetResponse 的「错误信息」分支：DT + Get-Result[0] DAR。"""
    return encode_apdu("GetResponse", dt=dt, dar=dar)


def build_set_response(dt: int, dar: int = 0) -> bytes:
    """表20 SetResponse：DT + 设置执行结果 DAR（1 字节）。"""
    return encode_apdu("SetResponse", dt=dt, dar=dar)


def build_report_response(dt: int) -> bytes:
    """表21 ReportResponse：对应上报的信息类标识 DT。"""
    return encode_apdu("ReportResponse", dt=dt)


#: 中文名别名（模块内/测试常用）
build_ack_frame = build_ack
build_nak_frame = build_nak
build_info_frame = build_info
build_get_response_ok = build_get_response_data


# ── 模板 ──────────────────────────────────────────────────────────────

_STRUCTURE_MODULE_INFO = [
    ("visible-string", "MOD-TEST"),
    ("visible-string", "ID0001"),
    ("double-long-unsigned", 0x01020304),
    ("date", {"year": 2024, "month": 1, "day_of_month": 15, "day_of_week": 1}),
    ("double-long-unsigned", 0x0A0B0C0D),
    ("date", {"year": 2023, "month": 6, "day_of_month": 20, "day_of_week": 2}),
    ("visible-string", "CREEP"),
]

_TEMPLATES: List[Dict[str, Any]] = [
    {
        "key": "ack",
        "label": "确认帧 ACK（无数据域，整帧8字节）",
        "dir": 1,
        "prm": 1,
        "func": CTRL_ACK,
        "build": lambda: b"",
    },
    {
        "key": "nak",
        "label": "否认帧 NAK（错误信息码 0x0002）",
        "dir": 1,
        "prm": 1,
        "func": CTRL_NAK,
        "build": lambda: encode_nak_domain(2),
    },
    {
        "key": "get_module_info",
        "label": "读取·模块信息 (GetRequest DT=0000)",
        "dir": 0,
        "prm": 1,
        "func": CTRL_INFO,
        "build": lambda: build_get_request(DT_MODULE_INFO),
    },
    {
        "key": "get_link_neg",
        "label": "读取·链路协商信息 (GetRequest DT=0001)",
        "dir": 0,
        "prm": 1,
        "func": CTRL_INFO,
        "build": lambda: build_get_request(DT_LINK_NEGOTIATION),
    },
    {
        "key": "get_proto_ver",
        "label": "读取·协议版本 (GetRequest DT=0002)",
        "dir": 0,
        "prm": 1,
        "func": CTRL_INFO,
        "build": lambda: build_get_request(DT_PROTOCOL_VERSION),
    },
    {
        "key": "get_clock",
        "label": "读取·时钟 (GetRequest DT=0100)",
        "dir": 0,
        "prm": 1,
        "func": CTRL_INFO,
        "build": lambda: build_get_request(DT_CLOCK),
    },
    {
        "key": "get_rsp_module_info",
        "label": "读取响应·模块信息 (GetResponse DT=0000 + 结构)",
        "dir": 1,
        "prm": 0,
        "func": CTRL_INFO,
        "build": lambda: build_get_response_data(
            DT_MODULE_INFO, list(_STRUCTURE_MODULE_INFO), "structure"
        ),
    },
    {
        "key": "get_rsp_dar",
        "label": "读取响应·信息类未定义 (GetResponse DT=0000 + DAR=2)",
        "dir": 1,
        "prm": 0,
        "func": CTRL_INFO,
        "build": lambda: build_get_response_dar(DT_MODULE_INFO, 2),
    },
    {
        "key": "set_clock",
        "label": "设置·时钟 (SetRequest DT=0100 + date_time)",
        "dir": 0,
        "prm": 1,
        "func": CTRL_INFO,
        "build": lambda: build_set_request(
            DT_CLOCK,
            {
                "year": 2026,
                "month": 9,
                "day_of_month": 23,
                "day_of_week": 3,
                "hour": 10,
                "minute": 30,
                "second": 0,
                "milliseconds": 0,
            },
            "date_time",
        ),
    },
    {
        "key": "report_power",
        "label": "上报·电源状态 (ReportNotification DT=0003 + enum 掉电)",
        "dir": 1,
        "prm": 0,
        "func": CTRL_INFO,
        "build": lambda: build_report_notification(DT_POWER_STATE, 1, "enum"),
    },
    {
        "key": "report_rsp",
        "label": "上报响应 (ReportResponse DT=0003)",
        "dir": 0,
        "prm": 0,
        "func": CTRL_INFO,
        "build": lambda: build_report_response(DT_POWER_STATE),
    },
    {
        "key": "link_req",
        "label": "链路协商请求 (LinkRequest)",
        "dir": 0,
        "prm": 1,
        "func": CTRL_INFO,
        "build": build_link_request,
    },
    {
        "key": "link_rsp",
        "label": "链路协商响应 (LinkResponse)",
        "dir": 1,
        "prm": 0,
        "func": CTRL_INFO,
        "build": lambda: build_link_response(channels=((1, 0), (2, 2))),
    },
]

DT_MODULE_INFO = dt_code(0, 0, 0x00)
DT_LINK_NEGOTIATION = dt_code(0, 0, 0x01)
DT_PROTOCOL_VERSION = dt_code(0, 0, 0x02)
DT_POWER_STATE = dt_code(0, 0, 0x03)
DT_CLOCK = dt_code(0, 1, 0x00)

#: 模板表（与 `templates()` 同源）
FRAME_TEMPLATES: List[Dict[str, Any]] = _TEMPLATES


def _template(key: str) -> Dict[str, Any]:
    for item in _TEMPLATES:
        if item["key"] == key:
            return item
    raise KeyError(f"未知模板：{key}")


def template_keys() -> List[str]:
    return [item["key"] for item in _TEMPLATES]


def template_labels() -> List[Tuple[str, str]]:
    return [(item["key"], item["label"]) for item in _TEMPLATES]


def build_from_template(key: str, fid: int = 0) -> bytes:
    """按模板名生成整帧。"""
    item = _template(key)
    return build_frame(
        item["build"](),
        dir_bit=item["dir"],
        prm=item["prm"],
        func=item["func"],
        fid=fid,
    )


def templates() -> List[Dict[str, Any]]:
    return list(_TEMPLATES)


# ── 面向 GUI 的类封装（薄壳，逻辑全在上面）─────────────────────────


class ModularIfaceFrameGenerator:
    """组帧入口类（`frame_gen_widget` 的 modular 模式用）。

    所有方法都是上面模块级函数的**薄封装**，不重复实现任何编码逻辑。
    """

    max_data_domain = MAX_DATA_DOMAIN

    #: 模板 → 默认值（与 `_TEMPLATES` 同源）
    frame_templates = _TEMPLATES

    @staticmethod
    def dt_code(dta1: int, dta2: int, dtb: int) -> int:
        return dt_code(dta1, dta2, dtb)

    @staticmethod
    def build_control(
        control_code: int, *, dir_bit: int = 0, prm: int = 1, fid: int = 0
    ) -> bytes:
        return build_control(control_code, dir_bit=dir_bit, prm=prm, fid=fid)

    @staticmethod
    def build_frame(
        data_domain: bytes,
        *,
        dir_bit: int = 0,
        prm: int = 1,
        func: int = CTRL_INFO,
        fid: int = 0,
        control: Optional[bytes] = None,
    ) -> bytes:
        return build_frame(
            data_domain, dir_bit=dir_bit, prm=prm, func=func, fid=fid, control=control
        )

    @staticmethod
    def build_ack(*, dir_bit: int = 0, prm: int = 0, fid: int = 0) -> bytes:
        return build_ack(dir_bit=dir_bit, prm=prm, fid=fid)

    @staticmethod
    def build_nak(error_code: int, *, dir_bit: int = 0, prm: int = 0, fid: int = 0) -> bytes:
        return build_nak(error_code, dir_bit=dir_bit, prm=prm, fid=fid)

    @staticmethod
    def build_info(apdu: bytes, *, dir_bit: int = 0, prm: int = 1, fid: int = 0) -> bytes:
        return build_info(apdu, dir_bit=dir_bit, prm=prm, fid=fid)

    @staticmethod
    def build_link_request(**kwargs: Any) -> bytes:
        return build_link_request(**kwargs)

    @staticmethod
    def build_link_response(**kwargs: Any) -> bytes:
        return build_link_response(**kwargs)

    @staticmethod
    def build_get_request(dt: int) -> bytes:
        return build_get_request(dt)

    @staticmethod
    def build_get_response_data(dt: int, value: Any = None, type_name: str = "NULL") -> bytes:
        return build_get_response_data(dt, value, type_name)

    @staticmethod
    def build_get_response_dar(dt: int, dar: int = 0) -> bytes:
        return build_get_response_dar(dt, dar)

    @staticmethod
    def build_set_request(dt: int, value: Any = None, type_name: str = "NULL") -> bytes:
        return build_set_request(dt, value, type_name)

    @staticmethod
    def build_set_response(dt: int, dar: int = 0) -> bytes:
        return build_set_response(dt, dar)

    @staticmethod
    def build_report_notification(dt: int, value: Any = None, type_name: str = "NULL") -> bytes:
        return build_report_notification(dt, value, type_name)

    @staticmethod
    def build_report_response(dt: int) -> bytes:
        return build_report_response(dt)

    @staticmethod
    def build_from_template(key: str, fid: int = 0) -> bytes:
        return build_from_template(key, fid)

    @staticmethod
    def templates() -> List[Dict[str, Any]]:
        return templates()
