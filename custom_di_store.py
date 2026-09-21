# -*- coding: utf-8 -*-
"""南网自定义 DI 存储（纯逻辑，无 Qt）。

职责单一：`custom_di.json` 的读写、校验与列表增删。被三处复用，避免第二份 JSON
读写逻辑散落各文件：

- `protocol_parser.ProtocolFrameParser` —— 构造时合并进 `DI_COMBINATION_MAP`（单帧解析能识别）
- `main_gui.MainWindow` —— 南网查询页「添加自定义DI / 删除选中自定义DI」按钮
- `lookup_pages.create_di_lookup_page` —— 简化版查询页的同名按钮

条目结构沿用既有 schema（AGENTS.md §4.5），**整体读改写，未知字段不丢**：:

    [
      {"di3": 232, "di2": 0, "di1": 8, "di0": 3, "desc": "查询采集任务号"}
    ]

「是否自定义」的唯一判据 = 条目是否存在于本文件；内置 DI 只存在于
`DI_COMBINATION_MAP`，所以不需要另存一份内置清单做对比。

路径经 `app_paths.data_path`（frozen → exe 所在目录；dev → 项目根）。模块内以
`app_paths.data_path(...)` 属性形式调用（每次调用时才查属性），因此测试可以直接
`app_paths.data_path = lambda name: ...` 沙箱到临时目录。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import app_paths

#: 数据文件名（与 `ProtocolFrameParser.CUSTOM_DI_FILE` 同源）
CUSTOM_DI_FILE = "custom_di.json"

#: DI 四字节字段名，顺序与 GUI 表格列 DI3/DI2/DI1/DI0 一致
DI_FIELDS: Tuple[str, ...] = ("di3", "di2", "di1", "di0")

#: DI 键类型：(DI3, DI2, DI1, DI0)，每个 0~255
DIKey = Tuple[int, int, int, int]


# ── 校验 / 格式化（纯函数）───────────────────────────────────────────


def parse_hex_byte(text: str) -> Optional[int]:
    """把单个 DI 字节的文本解析为 0~255；非法返回 None。

    接受 1~2 位十六进制（大小写与空白随意），如 ``"e8"`` / ``"E8"`` / ``" 8 "``。
    """
    raw = (text or "").strip()
    if not raw or len(raw) > 2:
        return None
    try:
        value = int(raw, 16)
    except ValueError:
        return None
    if 0 <= value <= 0xFF:
        return value
    return None


def make_key(di3: int, di2: int, di1: int, di0: int) -> DIKey:
    """构造 DI 键（不做范围校验，调用方走 `validate_key_text`）。"""
    return (int(di3), int(di2), int(di1), int(di0))


def format_key(key: DIKey) -> str:
    """DI 键 → 显示文本，如 ``"E8 00 08 03"``。"""
    return " ".join(f"{b:02X}" for b in key)


def key_of(entry: dict) -> Optional[DIKey]:
    """从 JSON 条目取 DI 键；缺字段/非法/非 dict 返回 None（不抛异常）。"""
    if not isinstance(entry, dict):
        return None
    values: List[int] = []
    for field in DI_FIELDS:
        value = entry.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if not 0 <= value <= 0xFF:
            return None
        values.append(value)
    return make_key(*values)


def validate_key_text(
    di3_text: str, di2_text: str, di1_text: str, di0_text: str
) -> Tuple[Optional[DIKey], str]:
    """校验四个 DI 输入框文本。

    Returns:
        (key, error)：合法时 ``error`` 为空串；非法时 ``key`` 为 None，
        ``error`` 为可直接展示给用户的中文提示。
    """
    texts = (di3_text, di2_text, di1_text, di0_text)
    for field, text in zip(DI_FIELDS, texts):
        if parse_hex_byte(text) is None:
            return None, f"{field.upper()} 必须为十六进制（00-FF）！"
    return make_key(*[parse_hex_byte(t) or 0 for t in texts]), ""


# ── JSON 读写 ────────────────────────────────────────────────────────


def load_custom_di(path: Optional[Path] = None) -> List[dict]:
    """读取 `custom_di.json` 返回条目列表。

    文件缺失时先经 `app_paths.ensure_data_file` 尝试从内置种子复制；内容非法
    （非列表 / JSON 解析失败）返回空列表，绝不抛异常打断解析器构造。

    ``path`` 显式传入时直接用该路径（不查 `app_paths`）：Reflex Web 版的数据根
    与桌面不同（见 `reflex_web.app_data`），需要各自读写各自的 `custom_di.json`。
    默认 ``None`` 时行为与历史完全一致。
    """
    if path is None:
        app_paths.ensure_data_file(CUSTOM_DI_FILE)
        path = app_paths.data_path(CUSTOM_DI_FILE)
    try:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    # 只滤掉非 dict 项；缺字段的 dict 原样保留，避免丢用户数据
    return [item for item in data if isinstance(item, dict)]


def save_custom_di(entries: Sequence[dict], path: Optional[Path] = None) -> None:
    """整体写回 `custom_di.json`（UTF-8、保留中文、缩进 2）。

    ``path`` 语义同 `load_custom_di`：显式传入则写该路径，默认写
    `app_paths.data_path(CUSTOM_DI_FILE)`（桌面行为不变）。
    """
    if path is None:
        path = app_paths.data_path(CUSTOM_DI_FILE)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(list(entries), fp, ensure_ascii=False, indent=2)


# ── 列表增删（纯函数，不碰磁盘）──────────────────────────────────────


def custom_key_set(
    entries: Optional[Sequence[dict]] = None, path: Optional[Path] = None
) -> Set[DIKey]:
    """自定义 DI 键集合；``entries`` 为 None 时从磁盘读取（``path`` 透传）。"""
    source = load_custom_di(path) if entries is None else entries
    keys: Set[DIKey] = set()
    for entry in source:
        key = key_of(entry)
        if key is not None:
            keys.add(key)
    return keys


def find_entry(entries: Sequence[dict], key: DIKey) -> Optional[dict]:
    """在条目列表中查找 DI 键对应的条目（找不到返回 None）。"""
    for entry in entries:
        if key_of(entry) == key:
            return entry
    return None


def upsert_entry(
    entries: Sequence[dict], key: DIKey, desc: str
) -> Tuple[List[dict], bool]:
    """新增或覆盖一个自定义 DI 条目。

    - 键已存在 → 只改 ``desc``，该条目上的其它（未知）字段原样保留；
    - 键不存在 → 追加 ``{"di3","di2","di1","di0","desc"}``。

    Returns:
        (new_entries, replaced)：新列表与「是否为覆盖已有条目」。
    """
    new_entries: List[dict] = [dict(item) for item in entries]
    desc = (desc or "").strip()
    existing = find_entry(new_entries, key)
    if existing is not None:
        existing["desc"] = desc
        return new_entries, True
    entry: Dict[str, object] = {field: value for field, value in zip(DI_FIELDS, key)}
    entry["desc"] = desc
    new_entries.append(entry)
    return new_entries, False


def remove_keys(
    entries: Sequence[dict], keys: Sequence[DIKey] | Set[DIKey]
) -> Tuple[List[dict], int]:
    """按 DI 键批量删除条目。

    Returns:
        (remaining, removed)：剩余条目与被删除的条目数。
    """
    target = set(keys)
    remaining = [dict(item) for item in entries]
    removed = 0
    for key in target:
        entry = find_entry(remaining, key)
        if entry is not None:
            remaining.remove(entry)
            removed += 1
    return remaining, removed


__all__ = [
    "CUSTOM_DI_FILE",
    "DI_FIELDS",
    "DIKey",
    "parse_hex_byte",
    "make_key",
    "format_key",
    "key_of",
    "validate_key_text",
    "load_custom_di",
    "save_custom_di",
    "custom_key_set",
    "find_entry",
    "upsert_entry",
    "remove_keys",
]
