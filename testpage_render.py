# -*- coding: utf-8 -*-
"""测试页的表格文本渲染（纯逻辑，禁止 import Qt / 任何协议模块）。

`dlt698_test_core` 与 `dlt645_test_core` 共用这一份实现（四列对齐、CJK 宽度、截断），
**不要在各协议 core 里再写第二份**：两个测试页的收发日志必须用同一套排版口径，
否则同一帧在 698 页和 645 页的缩进/截断行为会漂移。

约定
----
- 解析行形态：``(字段, 原始值, 解析值, 说明[, …])`` —— 只取前三列 + 说明列，多余列忽略。
- 字段名的前导空格表示层级，**原样保留**（缩进层次照旧可读）。
- CJK / 全角按 2 列宽计算；超宽按显示列宽截断，并标注原始字符数。
"""

from __future__ import annotations

import unicodedata
from typing import List, Sequence

#: 前三列的显示宽度（字段 / 原始值 / 解析值），说明列吃掉剩余
COL_FIELD, COL_RAW, COL_PARSED = 22, 24, 30

#: 单元格最大显示宽度：超出截断并标「共 N 字符」（结构化数据一行能撑到屏幕外几千列）
CELL_MAX = 72


def display_width(text: str) -> int:
    """字符串显示宽度：CJK/全角算 2 列，用于日志里对齐四列。"""
    width = 0
    for ch in str(text):
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def pad(text: str, width: int) -> str:
    """按显示宽度左对齐补空格（超宽则原样返回，不截断）。"""
    text = str(text)
    gap = width - display_width(text)
    return text + (" " * gap if gap > 0 else "")


def cell_text(value) -> str:
    """「解析值」单元格文本化：dict/list 打成 `k=v, …` / `[a, b]`，其余原样。"""
    if value is None:
        return ""
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            if isinstance(val, (dict, list)):
                continue                     # 嵌套结构交给「说明」列，别把格子撑爆
            parts.append(f"{key}={val}")
        return ", ".join(parts)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(cell_text(v) for v in value) + "]"
    text = str(value)
    return "" if text in ("", "-", "None") else text


def compact_hex_like(text: str, keep_chars: int = 32) -> str:
    """长 hex 串压成「前 N 个字符 …（共 M 字符）」，避免一行撑到屏幕外。

    只对**纯十六进制**下手（解析器会把 A-XDR 数据的原始编码直接塞进原始值/解析值列）；
    文字说明不受影响。**不要求长度为偶数** —— 解析器偶尔给出被截断的奇数长度编码，
    早先按「偶数才是 hex」判定会整段漏压、一行撑到屏幕外。
    """
    text = str(text or "").strip()
    compact = text.replace(" ", "")
    if len(compact) < keep_chars + 16:
        return text
    if any(c not in "0123456789abcdefABCDEF" for c in compact):
        return text
    return f"{compact[:keep_chars].upper()} … （共 {len(compact)} 字符）"


def clip(text: str, limit: int = CELL_MAX) -> str:
    """按显示宽度截断（CJK 算 2 列），超出补 `…` 与原始长度。"""
    text = str(text)
    if display_width(text) <= limit:
        return text
    kept, width = [], 0
    for ch in text:
        w = 2 if display_width(ch) == 2 else 1
        if width + w > limit:
            break
        kept.append(ch)
        width += w
    return "".join(kept) + f"…（共 {len(text)} 字符）"


def format_table_rows(rows: Sequence[Sequence], header: str = "") -> List[str]:
    """解析行 → 对齐的四列文本（`字段 | 原始值 | 解析值 | 说明`）。

    字段名里的前导空格（解析器用它表示层级）保留，因此缩进层次照旧可读。
    """
    out: List[str] = []
    if header:
        out.append(header)
    for row in rows:
        if not row or len(row) < 4:
            continue
        field, raw, parsed, desc = row[0], row[1], row[2], row[3]
        raw = "" if str(raw) in ("", "-", "None") else str(raw)
        raw = clip(compact_hex_like(raw), COL_RAW + 8)
        parsed = cell_text(parsed)
        desc = "" if str(desc) in ("", "None") else str(desc)
        parsed = clip(compact_hex_like(parsed))
        desc = clip(desc, 110)
        # 解析器对结构化字段（OAD/OMD/结构体）把解析值拼成 `{'OI': …}` 字符串；
        # 「说明」列已经是同一信息的人话版，两列都印等于刷屏 ⇒ 有说明时省略该串。
        if desc and parsed.startswith(("{'", "['")):
            parsed = ""
        line = (f"  {pad(field, COL_FIELD)} {pad(raw, COL_RAW)}"
                f" {pad(parsed, COL_PARSED)}")
        out.append((line + " " + desc).rstrip())
    return out


__all__ = [
    "CELL_MAX",
    "COL_FIELD",
    "COL_PARSED",
    "COL_RAW",
    "cell_text",
    "clip",
    "compact_hex_like",
    "display_width",
    "format_table_rows",
    "pad",
]
