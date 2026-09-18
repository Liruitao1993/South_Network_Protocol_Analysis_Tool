# -*- coding: utf-8 -*-
"""单帧解析结果「字段树」视图（Wireshark 风格）。

纯逻辑 build_tree_from_table_data：把扁平 table_data（缩进表示层级）
转成嵌套树；GUI 用 QTreeWidget 展示，点击节点传出字节范围供高亮。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


def _leading(name: str) -> int:
    return len(name) - len(name.lstrip(" "))


def _level_map(names) -> dict:
    depths = sorted({_leading(n) for n in names if _leading(n) > 0})
    return {d: i + 1 for i, d in enumerate(depths)}


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


def build_tree_from_table_data(table_data: list) -> List[FieldNode]:
    """table_data 行： (字段, 原始值, 解析值, 说明[, start[, end]])。

    字段名前导空格深度 → 父子关系；同级依次挂到最近的更浅节点下。
    """
    if not table_data:
        return []
    names = [str(it[0]) if it and it[0] is not None else "" for it in table_data]
    lmap = _level_map(names)

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
    """前序展开，便于测试/复制。"""
    out: List[Tuple[int, FieldNode]] = []
    for n in nodes:
        out.append((depth, n))
        out.extend(flatten_tree(n.children, depth + 1))
    return out


def build_ui_tree(QTreeWidget_cls, QTreeWidgetItem_cls, QHeaderView_cls, QColor=None):
    """工厂：返回已配置好的 QTreeWidget（延迟 import Qt 类，避免模块级重依赖）。"""

    class ParseResultTree(QTreeWidget_cls):
        headers = ["字段", "原始值", "解析值", "说明"]

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setColumnCount(4)
            self.setHeaderLabels(self.headers)
            self.setEditTriggers(QTreeWidget_cls.NoEditTriggers)
            self.setSelectionBehavior(QTreeWidget_cls.SelectRows)
            self.setAlternatingRowColors(True)
            self.setUniformRowHeights(True)
            self.header().setSectionResizeMode(
                0, QHeaderView_cls.ResizeMode.Interactive
            )
            self.header().setStretchLastSection(True)
            self.setColumnWidth(0, 180)
            self.setColumnWidth(1, 100)
            self.setColumnWidth(2, 100)
            self._node_map = {}  # QTreeWidgetItem id -> FieldNode
            self.itemClicked.connect(self._on_item_clicked)
            self.byte_range_clicked = None  # callable(start, end)

        def populate(self, table_data: list):
            self.clear()
            self._node_map.clear()
            roots = build_tree_from_table_data(table_data)
            for node in roots:
                self._add_node(None, node)
            self.expandToDepth(1)

        def _add_node(self, parent_item, node: FieldNode):
            item = QTreeWidgetItem_cls(
                parent_item if parent_item is not None else self.invisibleRootItem(),
                [node.name, node.raw, node.parsed, node.comment],
            )
            if node.byte_start is not None and node.byte_end is not None:
                item.setToolTip(
                    0, f"字节 {node.byte_start}-{node.byte_end}｜{node.comment or node.name}"
                )
            if QColor is not None and node.children:
                item.setForeground(0, QColor("#1a5f7a"))
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
]
