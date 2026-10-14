# -*- coding: utf-8 -*-
"""依瓦定制645协议（协议13）—— **线格式编解码唯一来源**（纯 stdlib，零 Qt）。

依据：``协议文档/13.依瓦定制645协议/依瓦定制645协议.md``（依瓦定制645协议 V1.0，2026-06-24 陈工）。
逐字节证据见 ``.trellis/tasks/10-09-yiwa-645-protocol/research/yiwa-645-protocol-facts.md``。

帧结构（图1 / 数据帧结构表）::

    偏移  0       1..6        7       8         9        10..10+n-1   10+n   11+n
         68H    A0..A5(6B)   68H   COMMAND      L       DATA(n)       CS     16H
                               bit7-4 = 模式
                               bit3-0 = 数据域长度高 4 位
    n = ((COMMAND & 0x0F) << 8) | L            （12 bit，0x000 ~ 0xFFF）
    整帧长度 = n + 12

本模块是**全部下游的地基**（解析器 / 组帧器 / 批量提取 / Web 端都 import 它）：
地址编解码、长度拼接、CS、±0x33 混淆、数据项序列**只在这里实现一次**，
**禁止**在任何调用方再写第二份（项目既有约定，见 AGENTS.md 陷阱 48/55/61）。

⚠ 文档与示例的三处已验证事实（不得凭记忆改写）
=============================================
1. **地址域高字节在前**：文档 L57 明写「A0-A5 为通讯目标地址，高字节在前，例如通讯表计表号为
   123456789012，则 A0..A5 = ``12 34 56 78 90 12``」。三条示例独立自证：
   ``12 34 56 78 90 12``→123456789012、``10 30 00 00 00 10``→103000000010、
   ``04 50 00 00 00 13``→45000000013（文档 L204 明写「表号 45000000013」）。
   注意这与标准 DL/T 645-2007（**低字节在前**）相反，故**不复用**协议 6 的任何代码。
2. **数据域 ±0x33 混淆**：文档 L113 注1 称「数据域内数据发送方加 0x33、接收方减 0x33」
   （本模块 ``apply_mask``：``invert=True`` 为 +0x33 / ``invert=False`` 为 −0x33）。
   ⚠ **文档自相矛盾**：同一条注还说「本标准中的示例为了提高可读性，**都未加 0x33 显示**」，
   但实测**只有读模式示例（X1/X2）是未混淆形态**；透传示例 X3/X5/X6/X8/X9 给出的**已是线上
   混淆后的字节**——证据：X6 ``36 13`` −0x33 = ``03 E0``（文档 L220 明写「减33后可看出E003」），
   X5 中间 12 字节 −0x33 恰为 ASCII ``"123456789:0;"``。故本模块两种形态都支持，
   由 ``resolve_mask`` 按「DI 命中加权 + 同分优先 −0x33（规范形态）」判别，**并输出判定依据**。
3. **帧尾 0x16 不是定界符**：数据域已 +0x33，0x16 是合法数据字节（0x16−0x33 为合法数据）。
   ⇒ 任何切帧逻辑**必须按长度域定位帧尾**（``frame_total_len``），禁止 ``find("16")`` /
   按 ``16H`` 扫描。

⚠ 文档缺陷 D1（写模式命令码缺失）：文档只有一句「COMMAND 有 3 种模式，分别是读模式，写模式，
透传模式」，全文**没有任何章节/表格/示例给出写模式的命令码**。故本模块**只定义文档明确给出的
4 个命令码**（0x10/0x20/0x30/0x40），写模式以 ``MODE_WRITE_REQUEST = None`` 显式占位，
**绝不推测 0x50/0x60**（有测试守卫）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    # 常量
    "FRAME_START",
    "FRAME_END",
    "ADDR_LEN",
    "MASK",
    "MAX_DATA_LEN",
    "HEADER_LEN",
    "TRAILER_LEN",
    "MIN_FRAME_LEN",
    "BROADCAST_ADDR",
    # 模式
    "MODE_READ_REQUEST",
    "MODE_READ_RESPONSE",
    "MODE_PASS_REQUEST",
    "MODE_PASS_RESPONSE",
    "MODE_WRITE_REQUEST",
    "MODE_WRITE_RESPONSE",
    "MODE_NAMES",
    "mode_name",
    # 地址
    "bcd_to_digits",
    "encode_addr12",
    "decode_addr12",
    "is_broadcast_addr",
    # 长度
    "len_from_cmd",
    "cmd_from_len",
    # 校验 / 混淆
    "calc_cs",
    "apply_mask",
    "mask_data",
    "unmask_data",
    # 数据项
    "DataItem",
    "encode_items",
    "decode_items",
    "score_form",
    "best_items_score",
    "MaskResolution",
    "resolve_mask",
    # 整帧
    "encode_frame",
    "frame_total_len",
    "is_frame",
    "extract_yw645_frames",
]

# ── 常量 ──────────────────────────────────────────────────────────────

#: 帧起始符 / 结束符
FRAME_START = 0x68
FRAME_END = 0x16
#: 地址域字节数
ADDR_LEN = 6
#: 广播地址（AA AA AA AA AA AA）
BROADCAST_ADDR = b"\xAA" * ADDR_LEN
#: 数据域混淆常量
MASK = 0x33
#: 12 bit 数据域长度上限（文档写「最大可传输 4096 个数据」，实为 0x000~0xFFF；见缺陷 D4）
MAX_DATA_LEN = 0xFFF
#: 帧头字节数 = 68 + 6B 地址 + 68 + CMD + L
HEADER_LEN = 10
#: 帧尾字节数 = CS + 16H
TRAILER_LEN = 2
#: 最短帧 = 空数据域（n=0）
MIN_FRAME_LEN = HEADER_LEN + TRAILER_LEN

# ── 模式（COMMAND 高 4 位）────────────────────────────────────────────

MODE_READ_REQUEST = 0x10   #: 读模式请求（读模块工作参数）
MODE_READ_RESPONSE = 0x20  #: 读模式返回
MODE_PASS_REQUEST = 0x30   #: 透传模式请求（针对 CIU）
MODE_PASS_RESPONSE = 0x40  #: 透传模式返回

#: 写模式：**文档未定义命令码**（缺陷 D1）。显式占位为 None，禁止推测 0x50/0x60。
MODE_WRITE_REQUEST: Optional[int] = None
MODE_WRITE_RESPONSE: Optional[int] = None

#: 命令码 → 中文名（**只含文档明确给出的 4 个命令码**）
MODE_NAMES: Dict[int, str] = {
    MODE_READ_REQUEST: "读模式请求",
    MODE_READ_RESPONSE: "读模式返回",
    MODE_PASS_REQUEST: "透传模式请求",
    MODE_PASS_RESPONSE: "透传模式返回",
}


def mode_name(cmd: int) -> str:
    """COMMAND 字节 → 模式名；未知高 4 位返回「未知模式(0xN0)」而不抛错。"""
    mode = cmd & 0xF0
    return MODE_NAMES.get(mode, f"未知模式(0x{mode:02X})")


# ── 地址域（高字节在前，BCD 数字 0~9）───────────────────────────────────


def bcd_to_digits(data: bytes) -> str:
    """把 BCD 字节串按「每字节 = 2 个十进制位」拼成数字串并去掉前导 0。

    例：``04 50 00 00 00 13`` → ``"45000000013"``；``AA AA AA AA AA AA`` → ``"AAAAAA..."``。
    """
    text = "".join(f"{b:02X}" for b in data)
    return text.lstrip("0") or "0"


def encode_addr12(text: str) -> bytes:
    """12 位表号文本 → 6 字节地址域（**高字节在前**）。

    - 去空白；仅允许十进制数字 0~9。
    - >12 位取**低 12 位**；<12 位**高位补 0**（文档 L65/L67）。
    - 广播地址请在组帧层用 ``BROADCAST_ADDR`` 传入（本函数只接受数字）。
    """
    if text is None:
        raise ValueError("地址不能为空")
    s = "".join(str(text).split())
    if not s:
        raise ValueError("地址不能为空")
    if not s.isdigit():
        bad = next((c for c in s if not c.isdigit()), "?")
        raise ValueError(f"地址必须为数字（BCD），含非法字符 {bad!r}：{text!r}")
    s = s[-12:]
    s = s.rjust(12, "0")
    return bytes.fromhex(s)


def decode_addr12(raw: bytes) -> str:
    """6 字节地址域 → 12 位表号数字串（**去前导 0**）。广播 ``AA×6`` 会返回 ``"AAAAAA…"``。"""
    if len(raw) != ADDR_LEN:
        raise ValueError(f"地址域必须为 {ADDR_LEN} 字节，实际 {len(raw)} 字节")
    return bcd_to_digits(raw)


def is_broadcast_addr(raw: bytes) -> bool:
    """是否为广播地址（``AA AA AA AA AA AA``）。"""
    return len(raw) == ADDR_LEN and bytes(raw) == BROADCAST_ADDR


# ── 数据域长度（12 bit = COMMAND 低 4 位 + L）──────────────────────────


def len_from_cmd(cmd: int, low: int) -> int:
    """``((COMMAND & 0x0F) << 8) | L`` → 数据域字节数（12 bit）。"""
    return ((cmd & 0x0F) << 8) | (low & 0xFF)


def cmd_from_len(mode: int, n: int) -> Tuple[int, int]:
    """数据域长度 ``n`` + 模式高 4 位 ``mode`` → ``(COMMAND, L)``。

    ``n`` 超出 12 bit 上限 ``0xFFF`` 时抛 ``ValueError``（可读中文），**不静默截断**（缺陷 D4）。
    """
    if not isinstance(n, int):
        raise ValueError(f"数据域长度必须为整数，实际 {type(n).__name__}")
    if n < 0:
        raise ValueError(f"数据域长度不能为负：{n}")
    if n > MAX_DATA_LEN:
        raise ValueError(
            f"数据域长度 {n} 超出 12 bit 上限 {MAX_DATA_LEN}（0xFFF）"
        )
    if not (0 <= mode <= 0xFF):
        raise ValueError(f"模式字节越界：{mode}")
    cmd = (mode & 0xF0) | ((n >> 8) & 0x0F)
    return cmd, (n & 0xFF)


# ── 校验码 CS ─────────────────────────────────────────────────────────


def calc_cs(body: bytes) -> int:
    """CS = 从第一个 68H 起、到 CS 之前所有字节的模 256 算术和（`sum & 0xFF`）。

    ``body`` 必须是「帧头 … 数据域末字节」这一段（含已 +0x33 的 DATA **原样字节**）。
    ⚠ 混淆判别与 CS **正交**——CS 永远按帧内原样字节计算。
    """
    return sum(body) & 0xFF


# ── 数据域 ±0x33 混淆 ─────────────────────────────────────────────────


def apply_mask(data: bytes, invert: bool = False) -> bytes:
    """数据域混淆。

    - ``invert=True``  → 逐字节 +0x33（发送方向；发送方加 0x33）
    - ``invert=False`` → 逐字节 −0x33（接收方向；接收方减 0x33，文档 L113 注1 默认）
    """
    d = MASK if invert else -MASK
    return bytes((b + d) & 0xFF for b in data)


def mask_data(data: bytes) -> bytes:
    """``apply_mask(data, invert=True)`` 的显式别名（+0x33）。"""
    return apply_mask(data, invert=True)


def unmask_data(data: bytes) -> bytes:
    """``apply_mask(data, invert=False)`` 的显式别名（−0x33）。"""
    return apply_mask(data, invert=False)


# ── 数据项序列（ID(2B) | FL(1B) | 数据(FL) 重复）────────────────────────

#: ID 存在性回调（供形态打分加权）：``id_bytes (2) -> bool``
IdExists = Callable[[bytes], bool]

FORM_REPLY = "reply"        #: 模块回复形态（带 FL + 数据）
FORM_REQUEST = "request"    #: 主站请求形态（只有 ID，无 FL）
FORM_AMBIGUOUS = "ambiguous"  #: 两种形态同分，按 reply 呈现
FORM_MALFORMED = "malformed"  #: 无法按任一形态自洽切分


@dataclass
class DataItem:
    """一个数据项。``fl`` 为 None 表示请求形态（无 FL / 无数据）。"""

    id: bytes
    fl: Optional[int]
    data: bytes
    offset: int

    @property
    def id_hex(self) -> str:
        return self.id.hex().upper()

    @property
    def data_hex(self) -> str:
        return self.data.hex().upper()

    @property
    def length(self) -> int:
        """本项在数据域中占用的字节数（请求 2B；回复 3B + FL）。"""
        return len(self.id) if self.fl is None else len(self.id) + 1 + len(self.data)


def _coerce_id(value) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, str):
        try:
            raw = bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError(f"数据项 ID 不是合法十六进制：{value!r}") from exc
    else:
        raise ValueError(f"数据项 ID 类型不支持：{type(value).__name__}")
    if len(raw) != 2:
        raise ValueError(f"数据项 ID 必须为 2 字节，实际 {len(raw)} 字节：{value!r}")
    return raw


def _coerce_data(value) -> bytes:
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        try:
            return bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError(f"数据项内容不是合法十六进制：{value!r}") from exc
    raise ValueError(f"数据项内容类型不支持：{type(value).__name__}")


def encode_items(items: Sequence[dict], *, with_fl: bool) -> bytes:
    """数据项列表 → 数据域（**未混淆**原样字节）。

    - ``with_fl=False``：主站请求形态，只拼 ``ID(2B)``（文档 L120「请求参数时不带数据长度」）。
    - ``with_fl=True`` ：模块回复形态，拼 ``ID(2B) + FL(1B) + 数据``。

    每项为 ``{"id": b"\\x00\\x10", "data": b"\\x01"}``（``id``/``data`` 也接受 ``"0010"`` 十六进制串）。
    FL 为 1 字节，故单项数据最长 255 字节，超出抛 ``ValueError``。
    """
    out = bytearray()
    for item in items or []:
        raw_id = _coerce_id(item.get("id") if isinstance(item, dict) else item)
        out += raw_id
        if with_fl:
            data = _coerce_data(item.get("data") if isinstance(item, dict) else None)
            if len(data) > 0xFF:
                raise ValueError(f"数据项 {raw_id.hex().upper()} 内容 {len(data)} 字节，FL 上限 255")
            out.append(len(data))
            out += data
    return bytes(out)


def _parse_items(payload: bytes, with_fl: bool) -> Optional[List[DataItem]]:
    """按指定形态切分；必须完整消费全部字节，否则返回 None。"""
    items: List[DataItem] = []
    pos = 0
    total = len(payload)
    if not with_fl:
        if total % 2 != 0:
            return None
        while pos < total:
            items.append(DataItem(id=payload[pos:pos + 2], fl=None, data=b"", offset=pos))
            pos += 2
        return items
    while pos < total:
        if pos + 3 > total:
            return None
        raw_id = payload[pos:pos + 2]
        fl = payload[pos + 2]
        if pos + 3 + fl > total:
            return None
        # 缺陷防护：FL=0 且其后仍有数据 → 该形态不自洽（多为另一种形态被误读）
        if fl == 0 and pos + 3 < total:
            return None
        items.append(DataItem(id=raw_id, fl=fl, data=payload[pos + 3:pos + 3 + fl], offset=pos))
        pos += 3 + fl
    return items


def score_form(payload: bytes, with_fl: bool, *, id_exists: Optional[IdExists] = None) -> Optional[int]:
    """某一切分形态的得分；``None`` 表示该形态不自洽（不合法）。

    打分（design.md §2.6）：完整消费全部字节 +4；每个 ID 命中数据项表 +2；有数据项 +1。
    """
    items = _parse_items(payload, with_fl)
    if items is None:
        return None
    score = 4  # 能完整消费全部字节（_parse_items 保证了这一点）
    if items:
        score += 1
    if id_exists is not None:
        score += 2 * sum(1 for it in items if id_exists(it.id))
    return score


def _best_form(payload: bytes, *, id_exists: Optional[IdExists] = None) -> Tuple[List[DataItem], str, int]:
    """返回 ``(项列表, 形态, 得分)``；两形态皆不合法时返回 ``([], malformed, 0)``。"""
    score_reply = score_form(payload, True, id_exists=id_exists)
    score_request = score_form(payload, False, id_exists=id_exists)
    if score_reply is None and score_request is None:
        return [], FORM_MALFORMED, 0
    if score_request is None:
        return _parse_items(payload, True) or [], FORM_REPLY, score_reply or 0
    if score_reply is None:
        return _parse_items(payload, False) or [], FORM_REQUEST, score_request or 0
    if score_reply > score_request:
        return _parse_items(payload, True) or [], FORM_REPLY, score_reply
    if score_request > score_reply:
        return _parse_items(payload, False) or [], FORM_REQUEST, score_request
    # 同分：回复是业务常态（文档 L120），按 reply 呈现但标记 ambiguous
    return _parse_items(payload, True) or [], FORM_AMBIGUOUS, score_reply


def decode_items(
    payload: bytes,
    with_fl: Optional[bool] = None,
    *,
    id_exists: Optional[IdExists] = None,
) -> Tuple[List[DataItem], str]:
    """数据域 → ``(项列表, 形态)``。

    - ``with_fl`` 给定（``True``/``False``）时只按该形态切分。
    - ``with_fl=None``（默认）时自动判别：请求（无 FL）与回复（带 FL）两种形态**互不误判**，
      同分时按「回复」呈现并标记 ``ambiguous``；皆不合法返回 ``malformed`` 且**不抛错**
      （交给上层插 ``⚠``，陷阱 23：宁可解释也不空白）。

    ``id_exists`` 为可选的数据项存在性回调（``id_bytes -> bool``），命中者加权 —— 用于
    在有 DI 表命中时把「未混淆形态」（如 ``00 10 00 20``）从「−0x33 同分候选」中救出。
    """
    if with_fl is True:
        items = _parse_items(payload, True)
        return (items or []), (FORM_REPLY if items is not None else FORM_MALFORMED)
    if with_fl is False:
        items = _parse_items(payload, False)
        return (items or []), (FORM_REQUEST if items is not None else FORM_MALFORMED)
    items, form, _score = _best_form(payload, id_exists=id_exists)
    return items, form


def best_items_score(payload: bytes, *, id_exists: Optional[IdExists] = None) -> int:
    """两种形态里的最高得分（皆不合法为 0）。供 ``resolve_mask`` 判别混淆形态。"""
    return _best_form(payload, id_exists=id_exists)[2]


# ── ±0x33 形态自动判别（文档 D3 / R3.1）────────────────────────────────


@dataclass
class MaskResolution:
    """``resolve_mask`` 的结果。``mode`` ∈ ``{"raw", "unmasked", "unknown"}``。"""

    payload: bytes
    mode: str
    detail: str
    raw_score: int = 0
    unmasked_score: int = 0
    items: List[DataItem] = field(default_factory=list)
    form: str = FORM_MALFORMED

    @property
    def masked(self) -> bool:
        """是否判定为「线上已混淆」（即需要 −0x33 才能得到原样数据）。"""
        return self.mode == "unmasked"


def resolve_mask(raw: bytes, *, id_exists: Optional[IdExists] = None) -> MaskResolution:
    """判别数据域是「未混淆（文档可读性示例）」还是「已混淆（线上规范形态）」。

    依据 prd R3.1 / design.md §3：以 ``ID(2B)+FL+数据`` 能否自洽切分（并按 DI 命中加权）打分，
    **同分优先 −0x33（规范形态，文档 L113 注1）**；两形态皆不合法则 ``mode="unknown"``、
    原样返回、交由上层出 ``⚠``（不猜）。

    ⚠ 已知边界：当两种形态都「自洽且 ID 均不在数据项表中」（如透传载荷 ``37 14``）时，
    只有 DI 命中或显式覆盖（``assume_masked``）能区分——本函数给出打分依据供上层解释。
    """
    unmasked = apply_mask(raw, invert=False)
    raw_score = best_items_score(raw, id_exists=id_exists)
    unmasked_score = best_items_score(unmasked, id_exists=id_exists)

    if raw_score == 0 and unmasked_score == 0:
        return MaskResolution(
            payload=bytes(raw),
            mode="unknown",
            detail=(
                "⚠ 按原样与减 0x33 均无法自洽切分数据项，未判定混淆形态，保留原始字节："
                f"原样得分={raw_score}，减0x33得分={unmasked_score}"
            ),
            raw_score=raw_score,
            unmasked_score=unmasked_score,
            items=[],
            form=FORM_MALFORMED,
        )

    if raw_score > unmasked_score:
        items, form, _ = _best_form(raw, id_exists=id_exists)
        return MaskResolution(
            payload=bytes(raw),
            mode="raw",
            detail=(
                "按原样解析（未减 0x33）：原文能自洽切分且得分更高"
                f"（原样={raw_score} > 减0x33={unmasked_score}）"
            ),
            raw_score=raw_score,
            unmasked_score=unmasked_score,
            items=items,
            form=form,
        )

    items, form, _ = _best_form(unmasked, id_exists=id_exists)
    tie = raw_score == unmasked_score
    detail = (
        "已按规范减 0x33 还原"
        + ("（两种形态同分，按规范形态优先减 0x33）" if tie else f"（减0x33={unmasked_score} > 原样={raw_score}）")
    )
    return MaskResolution(
        payload=bytes(unmasked),
        mode="unmasked",
        detail=detail,
        raw_score=raw_score,
        unmasked_score=unmasked_score,
        items=items,
        form=form,
    )


# ── 整帧组帧 / 切帧 ───────────────────────────────────────────────────


def encode_frame(addr: bytes, mode: int, data: bytes) -> bytes:
    """``addr(6B) + COMMAND(由 mode/长度反推) + DATA(+0x33) + CS + 16H`` → 整帧。

    这是**整帧组帧的唯一实现**（组帧器 / GUI / 测试全部走它）。``data`` 是**未混淆**的数据域
    原样字节；内部按 ``cmd_from_len`` 反推 COMMAND 低 4 位与 L，并逐字节 +0x33。

    ``mode`` 只取高 4 位有效（``mode & 0xF0``）。地址长度、数据长度越界一律抛 ``ValueError``。
    """
    if len(addr) != ADDR_LEN:
        raise ValueError(f"地址域必须为 {ADDR_LEN} 字节，实际 {len(addr)} 字节")
    payload = bytes(data or b"")
    cmd, low = cmd_from_len(mode, len(payload))
    body = bytes([FRAME_START]) + bytes(addr) + bytes([FRAME_START, cmd, low]) + mask_data(payload)
    return body + bytes([calc_cs(body), FRAME_END])


def frame_total_len(data: bytes) -> Optional[int]:
    """按长度域探测整帧总长（``n + 12``）；结构不自洽返回 ``None``。

    **自证条件**：``data[0] == 0x68`` 且 ``data[7] == 0x68``，且已有到 L 的字节。
    返回值可能大于 ``len(data)``（帧未收全）——调用方据此等待更多字节。
    ⚠ **不得**改用「搜索 0x16」定位帧尾（见模块头 F5）。
    """
    if data is None or len(data) < HEADER_LEN:
        return None
    if data[0] != FRAME_START or data[7] != FRAME_START:
        return None
    n = len_from_cmd(data[8], data[9])
    total = n + HEADER_LEN + TRAILER_LEN
    if total < MIN_FRAME_LEN:
        return None
    return total


def is_frame(data: bytes) -> bool:
    """结构完整自证：长度够 + 双 68H + 末字节 16H + 实际长度等于长度域声明值。

    不含 CS 校验（CS 由解析器/校验器单独判定，二者正交）。
    """
    total = frame_total_len(data)
    if total is None or len(data) != total:
        return False
    return data[-1] == FRAME_END


# ── 批量 / 串口帧提取（唯一实现，桌面 main_gui 与 Web 端同源 import）──────
#
# ⚠ **不得**改用「搜索 0x16」定位帧尾（prd F5 / 模块头第 3 条）：数据域已 +0x33，
# 0x16 是合法数据字节，帧尾只能按**长度域** ``((COMMAND & 0x0F) << 8) | L`` 定位。
# 两道自证缺一不可（与南网/国网/698.45/645 的互斥判据）：
#   ① ``data[7] == 0x68``（地址域之后的第二定界符）；
#   ② 按长度域落位后**末字节为 16H**。
# 南网/国网 byte7 恒为 0x00（被 ① 排除）；698.45 无第二个 68H（被 ① 排除）；
# 645 虽同以 ``68 + 6B 地址 + 68`` 开头，但其第 8 字节是控制码、会把 L 拼成很大的
# 长度从而越界（被 ② 排除）—— 实测四条混合日志互斥，详见 ``test/test_yw645_extract.py``。


def extract_yw645_frames(text: str) -> List[str]:
    """从文本中提取依瓦定制645（协议13）帧（**返回大写无分隔 hex，每帧一条**）。

    入参契约与 ``main_gui._extract_modular_frames`` **一致**（清洗后的纯 hex，大小写不限）；
    为方便 Web 端与单元测试直接调用，这里**额外宽容**：非 hex 字符（空格/日志前缀/中文/时间戳）
    一律先剥离再匹配（幂等：已清洗的 hex 结果不变）。

    算法（design.md §6）：逐位置找 ``68`` → 校验第二个 68H → 读 ``COMMAND``/``L`` →
    按长度域算出整帧长（``数据域长度 + 12``）→ 落位后校验末字节 ``16H`` → 命中则整帧产出、
    游标跳到帧尾；否则游标 +2 继续。
    """
    clean = re.sub(r"[^0-9A-Fa-f]", "", text or "").upper()
    frames: List[str] = []
    n = len(clean)
    i = 0
    while i + MIN_FRAME_LEN * 2 <= n:
        pos = clean.find("68", i)
        if pos == -1:
            break
        # 需要读到 byte9（L）：共 20 个字符（HEADER_LEN=10 字节）
        if pos + HEADER_LEN * 2 > n:
            i = pos + 2
            continue
        # 自证①：地址域之后的第二个 68H（byte7）
        if clean[pos + 14 : pos + 16] != "68":
            i = pos + 2
            continue
        try:
            cmd = int(clean[pos + 16 : pos + 18], 16)
            low = int(clean[pos + 18 : pos + 20], 16)
        except ValueError:  # 理论上不可达（已限 hex），保守兜底
            i = pos + 2
            continue
        data_len = len_from_cmd(cmd, low)
        total = data_len + MIN_FRAME_LEN  # ⚠ 整帧长 = 数据域长度 + 12，L 不是整帧长
        hex_len = total * 2
        if pos + hex_len > n:
            i = pos + 2
            continue
        candidate = clean[pos : pos + hex_len]
        # 自证②：按长度域落位后末字节必须是 16H
        if candidate[-2:] != "16":
            i = pos + 2
            continue
        frames.append(candidate)
        i = pos + hex_len
    return frames
