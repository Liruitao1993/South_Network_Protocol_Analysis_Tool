# -*- coding: utf-8 -*-
"""Wireshark 风格字段树：纯逻辑 + offscreen 控件测试。"""

import _path_setup  # noqa: E402

from parse_result_view import (  # noqa: E402
    build_tree_from_table_data,
    extract_bit_range,
    flatten_tree,
    format_field_label,
    format_field_value,
    is_structure_like,
    build_ui_tree,
)


def test_nested_and_value_format():
    data = [
        ("控制域（原值）", "80 01", "0x0180", "应用层控制域", 10, 11),
        ("  传输方向位(D15)", "0x1", "1", "1-上行", 10, 11),
        ("  启动标志位(D14)", "0x0", "0", "", 10, 11),
        ("校验和", "EF", "0xEF", "正确", 20, 20),
    ]
    roots = build_tree_from_table_data(data)
    assert len(roots) == 2
    assert is_structure_like(roots[0])
    assert not is_structure_like(roots[1])
    assert roots[0].children[0].display_name.endswith("[D15]")
    assert "1" in roots[0].children[0].display_value
    # 结构节点显示原值/解析值
    assert "0x0180" in roots[0].display_value or "80" in roots[0].display_value


def test_bit_and_value_helpers():
    assert extract_bit_range("帧长(bit0-11)") == "bit0-11"
    assert extract_bit_range("方向(D15)") == "D15"
    assert format_field_label("传输方向位(D15)") == "传输方向位 [D15]"
    assert format_field_value("1", "0b1") in ("1", "1  (0b1)")
    assert format_field_value("", "A0 B0") == "A0 B0"


def test_gui_tree_two_columns():
    from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QHeaderView

    app = QApplication.instance() or QApplication([])
    ParseResultTree = build_ui_tree(QTreeWidget, QTreeWidgetItem, QHeaderView, QColor)
    tree = ParseResultTree()
    assert tree.columnCount() == 2
    tree.populate(
        [
            ("FC", "00 00", "帧控制", "", 0, 1),
            ("  版本号(bit0-1)", "0", "2", "", 0, 0),
            ("MSDU", "11", "0x11", "", 2, 2),
        ]
    )
    assert tree.topLevelItemCount() == 2
    top = tree.topLevelItem(0)
    assert top.childCount() == 1
    assert "bit0-1" in top.child(0).text(0).lower() or "bit0-1" in top.child(0).text(0)
    hits = []
    tree.byte_range_clicked = lambda a, b: hits.append((a, b))
    tree._on_item_clicked(top.child(0), 0)
    assert hits == [(0, 0)]
    print("parse_result_view tests OK")


if __name__ == "__main__":
    test_nested_and_value_format()
    test_bit_and_value_helpers()
    test_gui_tree_two_columns()
    print("all OK")
