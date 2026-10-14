# -*- coding: utf-8 -*-
"""依瓦定制645协议（协议13）—— **组帧器**（纯逻辑，零 Qt）。

依据：``协议文档/13.依瓦定制645协议/依瓦定制645协议.md``；
设计见 ``.trellis/tasks/10-09-yiwa-645-protocol/design.md §7``。

本模块**只负责**「模式推导 / 数据项与模板这一层」，整帧编码（地址域高字节在前、
12 bit 长度拼接、数据域 +0x33、CS、帧尾 16H）**一律经** :mod:`yw645_wire` 的
:func:`yw645_wire.encode_frame` —— **禁止第二份编码逻辑**（项目既有约定，
见 AGENTS.md 陷阱 48/55/61）。

⚠ 文档缺陷 D1（写模式命令码缺失）
================================
文档只有一句「COMMAND 有 3 种模式，分别是读模式，写模式，透传模式」，**全文没有任何
章节/表格/示例给出写模式的命令码**。故 :data:`MODE_OPTIONS` 只含文档明确给出的 4 个
命令码（0x10/0x20/0x30/0x40），写模式以 ``code=None`` 显式占位、默认**禁用生成**并给出
可读提示；如现场实测到命令码，可经 ``cmd_override`` 手动传入（**绝不内置猜测值 0x50/0x60**）。

⚠ 数据域混淆方向（文档缺陷 D3）
==============================
组帧按**规范形态**处理：数据域 +0x33（文档 L113 注1「发送方在传输时需要加 0x33」）。
文档示例中读模式两条（X1/X2）是「为可读性未加 0x33」的展示形态，透传类示例（X3/X5/X6/
X7/X8/X9）才是线上形态 —— 故组帧输出**不会**逐字节等于 X1/X2，但一定等于 X3/X5/X6/X9
（见 ``test/test_yw645_frame_gen.py`` 的 oracle）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import yw645_wire as W

__all__ = [
    "YW645BuildError",
    "MODE_OPTIONS",
    "MODE_CODES",
    "MODE_LABELS",
    "WRITE_MODE_KEY",
    "mode_code",
    "with_fl_for_mode",
    "build_frame",
    "describe_frame",
    "FRAME_TEMPLATES",
    "template_keys",
    "template_labels",
    "templates",
    "build_from_template",
    "template_state",
    "YW645FrameGenerator",
]


class YW645BuildError(ValueError):
    """组帧参数非法（面向用户的中文原因，供 GUI 直接展示）。"""


# ── 模式（COMMAND 高 4 位）────────────────────────────────────────────
#
# (模式键, 命令码 或 None, 中文说明)。命令码 **只含文档明确给出的 4 个**；
# 写模式 code=None（缺陷 D1：文档未定义，禁用生成）。
MODE_OPTIONS: Tuple[Tuple[str, Optional[int], str], ...] = (
    ("read_req", W.MODE_READ_REQUEST, "读模式请求 (0x10)"),
    ("read_rsp", W.MODE_READ_RESPONSE, "读模式返回 (0x20)"),
    ("pass_req", W.MODE_PASS_REQUEST, "透传模式请求 (0x30)"),
    ("pass_rsp", W.MODE_PASS_RESPONSE, "透传模式返回 (0x40)"),
    ("write", None, "写模式（文档未定义命令码）"),
)

#: 模式键 → 命令码（None = 文档未定义）
MODE_CODES: Dict[str, Optional[int]] = {k: c for k, c, _ in MODE_OPTIONS}
#: 模式键 → 中文说明
MODE_LABELS: Dict[str, str] = {k: lab for k, _c, lab in MODE_OPTIONS}
#: 写模式键（占位，禁用生成）
WRITE_MODE_KEY = "write"

#: 请求类模式（不带 FL）
_REQUEST_MODES = ("read_req", "pass_req")
#: 返回类模式（带 FL）
_RESPONSE_MODES = ("read_rsp", "pass_rsp")
#: 数据域由「数据项 ID+FL+数据」构成（可切分）的模式
_ITEM_MODES = ("read_req", "read_rsp")


def mode_code(mode: str) -> int:
    """模式键 → 命令码；未定义（写模式）或未知键抛 :class:`YW645BuildError`。"""
    if mode not in MODE_CODES:
        raise YW645BuildError(
            f"未知模式：{mode!r}，可选：{'、'.join(MODE_CODES)}"
        )
    code = MODE_CODES[mode]
    if code is None:
        raise YW645BuildError(
            "写模式的命令码在《依瓦定制645协议》中未定义"
            "（文档仅写「COMMAND 有 3 种模式」，只给出读/透传两类的 4 个命令码）。\n"
            "本工具不推测 0x50/0x60：请在「写模式命令码」处填写现场实测值，"
            "或联系协议作者补充定义。"
        )
    return code


def with_fl_for_mode(mode: str, with_fl: Optional[bool] = None) -> bool:
    """模式 → 是否携带 ``FL + 数据项``（文档 L120「请求不带数据长度，回复时带」）。

    ``with_fl`` 显式给定时优先（供少数异常场景覆盖）。请求模式 ``read_req``/``pass_req``
    不带 FL；返回模式 ``read_rsp``/``pass_rsp`` 带 FL；写模式无法推导，须显式指定。
    """
    if with_fl is not None:
        return bool(with_fl)
    if mode in _RESPONSE_MODES:
        return True
    if mode in _REQUEST_MODES:
        return False
    raise YW645BuildError(
        f"模式 {mode!r} 无法推导是否携带数据长度 FL，请显式指定 with_fl（True=带 FL / False=不带）"
    )


def _coerce_addr(addr: Any) -> bytes:
    """地址：``bytes``（须 6 字节，可含广播）或十进制数字串（走 ``encode_addr12``）。"""
    if isinstance(addr, (bytes, bytearray)):
        raw = bytes(addr)
        if len(raw) != W.ADDR_LEN:
            raise YW645BuildError(
                f"地址域必须为 {W.ADDR_LEN} 字节，实际 {len(raw)} 字节"
            )
        return raw
    try:
        return W.encode_addr12(addr)
    except ValueError as exc:
        raise YW645BuildError(str(exc)) from exc


def _coerce_body(body: Any) -> bytes:
    """透传数据域（**未混淆**原样字节）：``bytes`` 或 hex 串（容忍空格/``0x``）。"""
    if body is None:
        return b""
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    if isinstance(body, str):
        text = "".join(body.split()).replace("0x", "").replace("0X", "")
        if not text:
            return b""
        if len(text) % 2:
            raise YW645BuildError(
                f"数据域十六进制必须是偶数长度，实际 {len(text)} 个字符：{body!r}"
            )
        try:
            return bytes.fromhex(text)
        except ValueError as exc:
            raise YW645BuildError(f"数据域不是合法十六进制：{body!r}") from exc
    raise YW645BuildError(f"数据域类型不支持：{type(body).__name__}")


def _is_valid_id(raw_id: Any) -> bool:
    """ID 预校验：2 字节（``bytes`` 或 4 位 hex 串）。"""
    if isinstance(raw_id, (bytes, bytearray)):
        return len(bytes(raw_id)) == 2
    if isinstance(raw_id, str):
        text = "".join(raw_id.split())
        return len(text) == 4 and all(c in "0123456789abcdefABCDEF" for c in text)
    return False


def _check_items(items: Sequence[dict], with_fl: bool) -> None:
    """数据项预校验（ID 合法、带 FL 时不得为空、显式 FL 须与实际字节数一致）。"""
    for idx, item in enumerate(items or []):
        raw_id = item.get("id") if isinstance(item, dict) else item
        if not _is_valid_id(raw_id):
            raise YW645BuildError(
                f"第 {idx + 1} 个数据项 ID 必须是 2 字节十六进制（如 0010），实际 {raw_id!r}"
            )
        if not with_fl:
            continue
        data = item.get("data") if isinstance(item, dict) else None
        if data is None or data == "" or data == b"":
            raise YW645BuildError(
                f"第 {idx + 1} 个数据项（ID={raw_id!r}）带 FL 形态却没有数据："
                "FL=0 无意义，请填写数据项值。"
            )
        data_len = len(_coerce_body(data))
        declared = item.get("fl") if isinstance(item, dict) else None
        if declared not in (None, ""):
            try:
                declared_int = int(str(declared), 0)
            except (TypeError, ValueError) as exc:
                raise YW645BuildError(
                    f"第 {idx + 1} 个数据项的 FL 不是整数：{declared!r}"
                ) from exc
            if declared_int != data_len:
                raise YW645BuildError(
                    f"第 {idx + 1} 个数据项的 FL={declared_int} 与数据项值 {data_len} 字节不一致"
                )


def build_frame(
    *,
    addr: Any,
    mode: str,
    items: Optional[List[Dict[str, Any]]] = None,
    with_fl: Optional[bool] = None,
    body: Any = None,
    cmd_override: Optional[int] = None,
) -> bytes:
    """按线格式生成一整帧（**全部编码经** :func:`yw645_wire.encode_frame`）。

    :param addr: 12 位表号数字串（>12 取低 12 位、<12 高位补 0，走 ``encode_addr12``）
                 或 6 字节地址（广播用 ``yw645_wire.BROADCAST_ADDR``）。
    :param mode: 模式键，见 :data:`MODE_OPTIONS`。
    :param items: 数据项列表 ``[{"id": "0010", "data": "01"}, ...]``；``id``/``data`` 接受
                  2 字节 hex 串或 ``bytes``。请求模式只拼 ID；返回模式拼 ``ID + FL + 数据``。
    :param with_fl: ``None``（默认）按模式推导；``True``/``False`` 显式覆盖。
    :param body: 透传/写模式的数据域（**未混淆** hex 串或 ``bytes``）；给出时忽略 ``items``。
    :param cmd_override: 手动命令码（仅用于文档未定义的写模式；高 4 位为模式，低 4 位由长度填充）。
    :raises YW645BuildError: 地址非法、数据域超 12 bit 上限、返回模式数据项为空等。
    """
    addr_bytes = _coerce_addr(addr)

    if mode not in MODE_CODES:
        raise YW645BuildError(
            f"未知模式：{mode!r}，可选：{'、'.join(MODE_CODES)}"
        )

    # 读模式（0x10/0x20）且未显式给 body ⇒ 走「数据项 ID(+FL+数据)」结构；
    # 透传/写模式的数据域是不透明载荷，一律走 body（未给则为空）。
    if body is None and mode in _ITEM_MODES:
        wf = with_fl_for_mode(mode, with_fl)
        _check_items(items or [], wf)
        try:
            payload = W.encode_items(items or [], with_fl=wf)
        except ValueError as exc:
            raise YW645BuildError(str(exc)) from exc
    else:
        payload = _coerce_body(body)

    if len(payload) > W.MAX_DATA_LEN:
        raise YW645BuildError(
            f"数据域 {len(payload)} 字节超出 12 bit 上限 {W.MAX_DATA_LEN}（0xFFF），不截断"
            "（文档「最大可传输 4096 个数据」按 12 bit 实现，见缺陷 D4）"
        )

    if cmd_override is not None:
        try:
            cmd = int(cmd_override)
        except (TypeError, ValueError) as exc:
            raise YW645BuildError(f"命令码不是整数：{cmd_override!r}") from exc
        if not 0 <= cmd <= 0xFF:
            raise YW645BuildError(f"命令码越界（0~255）：{cmd_override!r}")
    else:
        cmd = mode_code(mode)

    try:
        return W.encode_frame(addr_bytes, cmd, payload)
    except ValueError as exc:  # 长度/地址越界等（理论上已被上面拦住）
        raise YW645BuildError(str(exc)) from exc


def describe_frame(frame: bytes) -> str:
    """整帧摘要注记：``数据域n字节 | COMMAND=0xNN L=0xNN | CS=0xNN | 整帧m字节 | 数据域已+0x33``。"""
    data = bytes(frame or b"")
    if len(data) < W.MIN_FRAME_LEN:
        return "帧长不足"
    cmd, low = data[8], data[9]
    n = W.len_from_cmd(cmd, low)
    cs = data[-2] if len(data) >= 2 else 0
    parts = [
        f"数据域 {n} 字节",
        f"COMMAND=0x{cmd:02X} L=0x{low:02X}",
        f"CS=0x{cs:02X}",
        f"整帧 {len(data)} 字节",
        "数据域已 +0x33",
    ]
    return " | ".join(parts)


# ── 模板（与 YW645_command.json 预设种子同源）──────────────────────────
#
# 每条模板 = 一份「组帧参数」。``build_from_template`` 直接调 ``build_frame``，
# 保证模板与手工组帧走**同一条**编码路径。

FRAME_TEMPLATES: List[Dict[str, Any]] = [
    {
        "key": "read_dev_type",
        "label": "读取·设备类型（广播，读模式请求）",
        "group": "读模式",
        "mode": "read_req",
        "addr": "",
        "broadcast": True,
        "items": [{"id": "0010", "data": ""}],
        "body": "",
        "description": "广播读取设备类型（附录A ID 0010，长度 1 字节，01=电表）",
    },
    {
        "key": "read_dev_id",
        "label": "读取·设备号（广播，读模式请求）",
        "group": "读模式",
        "mode": "read_req",
        "addr": "",
        "broadcast": True,
        "items": [{"id": "0020", "data": ""}],
        "body": "",
        "description": "广播读取设备号（附录A ID 0020，最大 12 字节，BCD 表号）",
    },
    {
        "key": "read_batch",
        "label": "批量读取·设备类型+设备号（广播）",
        "group": "读模式",
        "mode": "read_req",
        "addr": "",
        "broadcast": True,
        "items": [{"id": "0010", "data": ""}, {"id": "0020", "data": ""}],
        "body": "",
        "description": "文档示例：读设备类型和设备号（数据域 00 10 00 20，长度 4 字节）",
    },
    {
        "key": "read_rsp_sample",
        "label": "读模式返回·设备类型+设备号（表号 103000000010）",
        "group": "读模式",
        "mode": "read_rsp",
        "addr": "103000000010",
        "broadcast": False,
        "items": [
            {"id": "0010", "data": "01"},
            {"id": "0020", "data": "103000000010"},
        ],
        "body": "",
        "description": "文档示例 X2 的回复内容（ID 0010=01 电表、ID 0020=6 字节表号）",
    },
    {
        "key": "pass_req",
        "label": "透传模式请求（CIU→表计，表号 45000000013）",
        "group": "透传模式",
        "mode": "pass_req",
        "addr": "45000000013",
        "broadcast": False,
        "items": [],
        "body": "04E1",
        "description": "文档示例 X3：数据域线上为 37 14（未混淆 04 E1）",
    },
    {
        "key": "pass_rsp",
        "label": "透传模式返回（表计→CIU，表号 103000000010）",
        "group": "透传模式",
        "mode": "pass_rsp",
        "addr": "103000000010",
        "broadcast": False,
        "items": [],
        "body": "04E0",
        "description": "文档示例 X9：数据域线上为 37 13（未混淆 04 E0）",
    },
]


def _template(key: str) -> Dict[str, Any]:
    for item in FRAME_TEMPLATES:
        if item["key"] == key:
            return item
    raise YW645BuildError(f"未知模板：{key!r}")


def template_keys() -> List[str]:
    return [item["key"] for item in FRAME_TEMPLATES]


def template_labels() -> List[Tuple[str, str]]:
    return [(item["key"], item["label"]) for item in FRAME_TEMPLATES]


def templates() -> List[Dict[str, Any]]:
    return list(FRAME_TEMPLATES)


def template_state(key: str) -> Dict[str, Any]:
    """模板 → 组帧页状态（``YW645FrameGenWidget.apply_state`` 可直接套用）。"""
    item = _template(key)
    return {
        "template_key": item["key"],
        "addr": item.get("addr", ""),
        "broadcast": bool(item.get("broadcast")),
        "mode": item.get("mode", "read_req"),
        "with_fl": None,
        "items": [dict(it) for it in item.get("items", [])],
        "body": item.get("body", ""),
        "write_cmd": "",
    }


def build_from_template(key: str, addr: Any = None, **kwargs: Any) -> bytes:
    """按模板名生成整帧；``addr`` 给出时覆盖模板默认地址（``None`` 用模板值）。"""
    item = _template(key)
    addr_value: Any
    if addr is not None:
        addr_value = addr
    elif item.get("broadcast"):
        addr_value = W.BROADCAST_ADDR
    else:
        addr_value = item.get("addr", "")
    kwargs.setdefault("mode", item["mode"])
    if item.get("body"):
        kwargs.setdefault("body", item["body"])
    else:
        kwargs.setdefault("items", [dict(it) for it in item.get("items", [])])
    return build_frame(addr=addr_value, **kwargs)


# ── 面向 GUI 的类封装（薄壳，逻辑全在上面）───────────────────────────


class YW645FrameGenerator:
    """组帧入口类（``frame_gen_widget`` 的 ``yw645`` 模式用）。

    所有方法都是模块级函数的**薄封装**，不重复实现任何编码逻辑。
    """

    max_data_len = W.MAX_DATA_LEN
    mode_options = MODE_OPTIONS
    mode_codes = MODE_CODES
    mode_labels = MODE_LABELS
    frame_templates = FRAME_TEMPLATES

    @staticmethod
    def mode_code(mode: str) -> int:
        return mode_code(mode)

    @staticmethod
    def with_fl_for_mode(mode: str, with_fl: Optional[bool] = None) -> bool:
        return with_fl_for_mode(mode, with_fl)

    @staticmethod
    def build_frame(**kwargs: Any) -> bytes:
        return build_frame(**kwargs)

    @staticmethod
    def describe_frame(frame: bytes) -> str:
        return describe_frame(frame)

    @staticmethod
    def build_from_template(key: str, addr: Any = None, **kwargs: Any) -> bytes:
        return build_from_template(key, addr, **kwargs)

    @staticmethod
    def templates() -> List[Dict[str, Any]]:
        return templates()

    @staticmethod
    def template_labels() -> List[Tuple[str, str]]:
        return template_labels()

    @staticmethod
    def template_state(key: str) -> Dict[str, Any]:
        return template_state(key)
