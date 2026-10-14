# -*- coding: utf-8 -*-
"""依瓦定制645协议（协议13）—— 附录A 数据项表 **单一来源**（纯 stdlib，零 Qt）。

依据：``协议文档/13.依瓦定制645协议/依瓦定制645协议.md``「附录A 通用参数类」——
**全表仅 2 条数据项**（缺陷 D5）：``00 10`` 设备类型、``00 20`` 设备号。

⚠ 双索引（文档缺陷 D2）——两条互不兼容的读法都必须支持
=====================================================
* **主索引（字面字节）**：X2 示例线上数据为 ``00 10`` / ``00 20``，且该示例未被混淆，
  按字面即读出「设备类型」「设备号」⇒ 附录A 的 ``00 10``/``00 20`` 是**线上字面字节**。
* **备选索引（字节交换）**：透传示例 X3/X6/X8 的数据域减 0x33 后得到 ``04 E0``/``04 E1``，
  文档却注为「E004」「E003」（按**小端 u16** 读）。作者本人用的是字节交换读法，
  但附录A 与 X2 又只能是字面读法 ⇒ 两种读法并存，字面优先、不命中再试字节交换。

⇒ ``di_lookup`` 返回 ``(条目, "literal"/"swapped"/"unknown")``，命中方式由调用方写入解析结果。

本表**只定义一次**：桌面查询页 / 解析器 / 组帧下拉 / Web 查询页全部 import 本模块，
**禁止**在任何一端再抄第二份（项目既有约定，见 AGENTS.md 陷阱 48/55/61）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from yw645_wire import bcd_to_digits

__all__ = [
    "DI_TABLE",
    "DI_INDEX_LITERAL",
    "DI_INDEX_SWAPPED",
    "DI_BY_ID",
    "di_lookup",
    "di_exists",
    "di_id_bytes",
    "di_payload_note",
]

# ── 附录A「通用参数类」（逐条抄录，仅 2 条）────────────────────────────
#
# 列：标识 DI(2B) / 长度 / 数据类型 / 读·写 / 数据项名称 / 说明
DI_TABLE: List[Dict[str, Any]] = [
    {
        "id": "0010",
        "name": "设备类型",
        "length": "变长",
        "dtype": "BCD",
        "rw": "读",
        "note": "01：电表",
        "enum": {"01": "电表"},
    },
    {
        "id": "0020",
        "name": "设备号",
        "length": "变长",
        "dtype": "BCD",
        "rw": "读",
        "note": "最大12个字节",
        "enum": {},
    },
]

#: 按线上字面 ID 文本 → 条目
DI_BY_ID: Dict[str, Dict[str, Any]] = {entry["id"]: entry for entry in DI_TABLE}

#: 主索引：线上字面字节（``b"\x00\x10"``）
DI_INDEX_LITERAL: Dict[bytes, Dict[str, Any]] = {
    bytes.fromhex(entry["id"]): entry for entry in DI_TABLE
}

#: 备选索引：字节交换（``b"\x10\x00"``）——覆盖文档 D2 的小端读法
DI_INDEX_SWAPPED: Dict[bytes, Dict[str, Any]] = {
    bytes.fromhex(entry["id"])[::-1]: entry for entry in DI_TABLE
}


def di_id_bytes(entry: Dict[str, Any]) -> bytes:
    """条目 → 2 字节 ID。"""
    return bytes.fromhex(entry["id"])


def di_lookup(raw_id: bytes) -> Tuple[Optional[Dict[str, Any]], str]:
    """2 字节 ID → ``(条目, 命中方式)``；命中方式 ∈ ``{"literal", "swapped", "unknown"}``。

    字面优先；字面不命中再试字节交换（文档 D2）。
    """
    if raw_id is None or len(raw_id) != 2:
        return None, "unknown"
    key = bytes(raw_id)
    hit = DI_INDEX_LITERAL.get(key)
    if hit is not None:
        return hit, "literal"
    hit = DI_INDEX_SWAPPED.get(key)
    if hit is not None:
        return hit, "swapped"
    return None, "unknown"


def di_exists(raw_id: bytes) -> bool:
    """2 字节 ID 是否命中数据项表（字面或字节交换）——供 ``yw645_wire`` 形态打分加权。"""
    return di_lookup(raw_id)[0] is not None


def di_payload_note(entry: Optional[Dict[str, Any]], payload: bytes) -> str:
    """已识别数据项的数据内容业务说明（枚举 / 表号）。

    - ``00 10`` 设备类型：首字节枚举（``01`` → 电表），未知值给 ``未知设备类型(0xNN)`` 并标 ⚠。
    - ``00 20`` 设备号：按 BCD 拼成表号数字串（与地址域同口径，高字节在前），超 12 字节截断并标 ⚠。
    """
    data = bytes(payload or b"")
    if not entry:
        return ""
    did = entry.get("id")
    if did == "0010":
        if not data:
            return "⚠ 设备类型数据为空"
        val = f"{data[0]:02X}"
        enum = entry.get("enum") or {}
        if val in enum:
            return enum[val]
        return f"⚠ 未知设备类型(0x{val})"
    if did == "0020":
        if not data:
            return "⚠ 设备号数据为空"
        note = ""
        if len(data) > 12:
            note = f"⚠ 设备号 {len(data)} 字节超过 12 字节上限，按低 12 位截断；"
            data = data[-12:]
        return f"{note}设备号（BCD）= {bcd_to_digits(data)}"
    return ""
