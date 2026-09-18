# -*- coding: utf-8 -*-
"""parse_result_view 纯逻辑 + offscreen 树控件测试。"""

import _path_setup  # noqa: E402

from parse_result_view import (  # noqa: E402
    FieldNode,
    build_tree_from_table_data,
    flatten_tree,
    build_ui_tree,
)


def test_build_tree_nested():
    data = [
        ("帧头", "68", "68", "起始", 0, 0),
        ("  长度", "0E 00", "14", "小端", 1, 2),
        ("  地址", "01", "1", "", 3, 3),
        ("用户数据", "E8", "E8", "", 4, 4),
        ("  DI", "00", "DI0", "", 4, 4),
        ("校验", "EF", "EF", "", 5, 5),
    ]
    roots = build_tree_from_table_data(data)
    assert len(roots) == 3
    assert roots[0].name == "帧头"
    assert len(roots[0].children) == 2
    assert roots[0].children[0].name == "长度"
    assert roots[0].children[0].byte_start == 1
    assert roots[1].name == "用户数据"
    assert roots[1].children[0].name == "DI"
    flat = flatten_tree(roots)
    assert len(flat) == 6
    assert flat[0][0] == 0
    assert flat[1][0] == 1


def test_build_tree_flat_no_indent():
    data = [("A", "1", "2", "", 0, 0), ("B", "3", "4", "", 1, 1)]
    roots = build_tree_from_table_data(data)
    assert len(roots) == 2
    assert not roots[0].children


def test_empty():
    assert build_tree_from_table_data([]) == []


def test_gui_tree_offscreen():
    from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QHeaderView

    app = QApplication.instance() or QApplication([])
    ParseResultTree = build_ui_tree(QTreeWidget, QTreeWidgetItem, QHeaderView, QColor)
    tree = ParseResultTree()
    tree.populate(
        [
            ("帧头", "68", "", "", 0, 0),
            ("  长度", "0E", "14", "", 1, 2),
            ("校验", "EF", "", "", 3, 3),
        ]
    )
    assert tree.topLevelItemCount() == 2
    top = tree.topLevelItem(0)
    assert top.text(0) == "帧头"
    assert top.childCount() == 1
    assert top.child(0).text(0) == "长度"

    hits = []
    tree.byte_range_clicked = lambda a, b: hits.append((a, b))
    tree.setCurrentItem(top.child(0))
    # simulate click handler
    tree._on_item_clicked(top.child(0), 0)
    assert hits == [(1, 2)]
    print("parse_result_view tests OK")


if __name__ == "__main__":
    test_build_tree_nested()
    test_build_tree_flat_no_indent()
    test_empty()
    test_gui_tree_offscreen()
    print("all parse_result_view tests OK")
