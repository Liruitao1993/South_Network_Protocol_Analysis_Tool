# -*- coding: utf-8 -*-
"""单帧解析结果「Wireshark 风格字段树」。

与表格视图的差异（研发工具视角）：
- **三列**：字段 | 值 | 说明（说明列给出中文含义，结构树仍可展开）
- **协议结构树**：按解析行缩进还原层级；有子级的节点是可展开结构节点
  （类似 Wireshark 的 bitfield / header / struct），叶子才是字段+值
- **值列**：优先「解析值」，必要时附原始 hex；说明进 tooltip
- **位段标注**：从字段名提取 bit/D 位范围，以 Wireshark 习惯展示
  （如 `传输方向位 [D15]`）
- 点击节点 → 高亮输入框对应报文字节

数据源仍是 GUI 既有的 table_data 六元组（字段/原始/解析/说明/起/止），
不改各协议 parser。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


def _leading(name: str) -> int:
    return len(name) - len(name.lstrip(" "))


def _level_map(names) -> dict:
    depths = sorted({_leading(n) for n in names if _field_leading_exists(n)})
    return {d: i + 1 for i, d in enumerate(depths)}


def _field_leading_exists(name: str) -> bool:
    return _leading(name) > 0


@dataclass
class FieldNode:
    name: str
    raw: str
    parsed: str
    comment: str
    byte_start: Optional[int] = None
    byte_end: Optional[int] = None
    children: List["FieldNode"] = field(default_factory=list)

    @property
    def byte_range(self) -> Tuple[Optional[int], Optional[int]]:
        return self.byte_start, self.byte_end

    @property
    def is_structure(self) -> bool:
        """有子级 = 结构节点（可展开），对应 Wireshark 的 header/bitfield/struct。"""
        return bool(self.children)

    @property
    def display_name(self) -> str:
        return format_field_label(self.name)

    @property
    def display_value(self) -> str:
        return format_field_value(self.parsed, self.raw)


_BIT_PATTERNS = (
    re.compile(r"[（(]\s*(bit\s*\d+\s*[-~～]\s*\d+|bit\s*\d+|D\d+\s*[-~～]\s*D?\d+|D\d+)\s*[)）]", re.I),
    re.compile(r"\b(bit\s*\d+\s*[-~～]\s*\d+|bit\s*\d+|D\d+\s*[-~～]\s*D?\d+|D\d+)\b", re.I),
)

_STRUCTURE_HINT = re.compile(r"位域|bitfield|控制域|帧头|报文头|可变区域|管理信息|MAC|FC|PB|结构|区域", re.I)


def extract_bit_range(name: str) -> Optional[str]:
    for pat in _BIT_PATTERNS:
        m = pat.search(name or "")
        if m:
            return re.sub(r"\s+", "", m.group(1))
    return None


def format_field_label(name: str) -> str:
    """Wireshark 风格字段标签：名称 + [位段]（若已识别）。"""
    n = (name or "").lstrip(" ")
    if not n:
        return ""
    br = extract_bit_range(n)
    if not br:
        return n
    # 去掉原括号位段，避免重复
    stripped = n
    for pat in _BIT_PATTERNS:
        stripped = pat.sub("", stripped).strip()
    stripped = stripped.strip("()（） 　")
    br_up = br.replace(" ", "").replace("～", "-").replace("~", "-")
    return f"{stripped} [{br_up}]" if stripped else f"[{br_up}]"


def format_field_value(parsed: str, raw: str) -> str:
    """叶子节点值列：解析值优先，原始 hex 不同则并列。"""
    p = (parsed or "").strip()
    r = (raw or "").strip()
    if p and r and p != r and _looks_useful_raw(r, p):
        return f"{p}  ({r})"
    return p or r


def _looks_useful_raw(raw: str, parsed: str) -> bool:
    """原始值是否值得单独展示（hex / 与解析值不同的编码）。"""
    if not raw:
        return False
    if raw in ("-", "—"):
        return False
    # 纯 hex 块
    compact = re.sub(r"[^0-9A-Fa-f]", "", raw)
    return len(compact) >= 2 and bool(compact)


def build_tree_from_table_data(table_data: list) -> List[FieldNode]:
    """table_data 行 → Wireshark 风格嵌套树（缩进 = 层级）。"""
    if not table_data:
        return []
    names = [str(it[0]) if it and it[0] is not None else "" for it in table_data]
    depths = sorted({_leading(n) for n in names if _leading(n) > 0})
    lmap = {d: i + 1 for i, d in enumerate(depths)}

    roots: List[FieldNode] = []
    stack: List[Tuple[int, FieldNode]] = []

    for item in table_data:
        raw_name = str(item[0]) if item and item[0] is not None else ""
        level = lmap.get(_leading(raw_name), 0)
        name = raw_name.lstrip(" ")
        raw_v = str(item[1]) if len(item) > 1 and item[1] is not None else ""
        parsed = str(item[2]) if len(item) > 2 and item[2] is not None else ""
        comment = str(item[3]) if len(item) > 3 and item[3] is not None else ""
        b0 = item[4] if len(item) > 4 else None
        b1 = item[5] if len(item) > 5 else None
        node = FieldNode(
            name=name,
            raw=raw_v,
            parsed=parsed,
            comment=comment,
            byte_start=b0,
            byte_end=b1,
        )
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            stack[-1][1].children.append(node)
        else:
            roots.append(node)
        stack.append((level, node))
    return roots


def flatten_tree(nodes: List[FieldNode], depth: int = 0) -> List[Tuple[int, FieldNode]]:
    out: List[Tuple[int, FieldNode]] = []
    for n in nodes:
        out.append((depth, n))
        out.extend(flatten_tree(n.children, depth + 1))
    return out


def is_structure_like(node: FieldNode) -> bool:
    if node.is_structure:
        return True
    return bool(_STRUCTURE_HINT.search(node.name or ""))


def build_ui_tree(QTreeWidget_cls, QTreeWidgetItem_cls, QHeaderView_cls, QColor=None):
    """Wireshark 风格两列字段树（延迟注入 Qt 类便于测试）。"""

    class ParseResultTree(QTreeWidget_cls):
        # 字段 + 值 + 说明：结构树保留层级，说明列给出中文含义
        headers = ["字段", "值", "说明"]
        col_widths = (260, 280, 280)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("result_tree_widget")
            self.setColumnCount(3)
            self.setHeaderLabels(self.headers)
            self.setEditTriggers(QTreeWidget_cls.NoEditTriggers)
            self.setSelectionBehavior(QTreeWidget_cls.SelectRows)
            # 结构树不使用表格交替色，保持 Wireshark 清爽感（配色仍由主题 QSS 提供）
            self.setAlternatingRowColors(False)
            self.setUniformRowHeights(True)
            self.setRootIsDecorated(True)
            self.setIndentation(16)
            self.setAnimated(False)
            self.header().setSectionResizeMode(0, QHeaderView_cls.ResizeMode.Interactive)
            self.header().setSectionResizeMode(1, QHeaderView_cls.ResizeMode.Interactive)
            self.header().setSectionResizeMode(2, QHeaderView_cls.ResizeMode.Stretch)
            self.header().setDefaultSectionSize(20)
            for i, w in enumerate(self.col_widths):
                self.header().resizeSection(i, w)
            self._node_map = {}
            self._structure_color = QColor("#1a5276") if QColor else None
            self._leaf_color = None
            self.itemClicked.connect(self._on_item_clicked)
            self.byte_range_clicked = None
            self.apply_table_style(None)

        def apply_table_style(self, table_font=None):
            """字号/行高与结果表一致；树自身两列结构，不套用表格交替色。"""
            if table_font is not None:
                self.setFont(table_font)
            self.setStyleSheet("")
            fm = self.fontMetrics()
            self.header().setDefaultSectionSize(max(10, fm.height() + 4))

        def populate(self, table_data: list):
            self.clear()
            self._node_map.clear()
            roots = build_tree_from_table_data(table_data)
            for node in roots:
                self._add_node(None, node)
            self.expandAll()

        def _add_node(self, parent_item, node: FieldNode):
            structure = is_structure_like(node)
            val = node.display_value
            comment = (node.comment or "").strip()
            item = QTreeWidgetItem_cls(
                parent_item if parent_item is not None else self.invisibleRootItem(),
                [node.display_name, val, comment],
            )
            tip_parts = []
            if node.comment:
                tip_parts.append(node.comment)
            if node.parsed and node.raw and node.parsed != node.raw:
                tip_parts.append(f"解析: {node.parsed}")
                tip_parts.append(f"原始: {node.raw}")
            if node.byte_start is not None and node.byte_end is not None:
                tip_parts.append(f"字节 {node.byte_start}-{node.byte_end}")
            if tip_parts:
                for col in range(3):
                    item.setToolTip(col, "｜".join(tip_parts))
            # 结构节点字段名用主题深色强调（Wireshark 里 header 更醒目）
            if structure and self._structure_color is not None:
                item.setForeground(0, self._structure_color)
            self._node_map[id(item)] = node
            for child in node.children:
                self._add_node(item, child)
            return item

        def _on_item_clicked(self, item, _col):
            node = self._node_map.get(id(item))
            if node is None:
                return
            b0, b1 = node.byte_range
            if b0 is None or b1 is None:
                return
            if callable(self.byte_range_clicked):
                self.byte_range_clicked(b0, b1)

        def current_byte_range(self):
            item = self.currentItem()
            if item is None:
                return None, None
            node = self._node_map.get(id(item))
            if node is None:
                return None, None
            return node.byte_range

    return ParseResultTree


__all__ = [
    "FieldNode",
    "build_tree_from_table_data",
    "flatten_tree",
    "build_ui_tree",
    "format_field_label",
    "format_field_value",
    "extract_bit_range",
    "is_structure_like",
]
