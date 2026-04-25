"""
查询页面管理模块
简化版本 - 直接使用函数创建页面
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from gui_utils import setup_chinese_context_menu


def create_search_bar(parent, placeholder="输入关键词搜索...", on_text_changed=None):
    """创建搜索栏"""
    layout = QHBoxLayout()
    label = QLabel("搜索：")
    label.setFixedWidth(45)
    search_input = QLineEdit()
    search_input.setPlaceholderText(placeholder)
    if on_text_changed:
        search_input.textChanged.connect(on_text_changed)
    setup_chinese_context_menu(search_input)
    layout.addWidget(label)
    layout.addWidget(search_input)
    return layout, search_input


def create_table_widget(headers, column_widths):
    """创建表格"""
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)

    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)

    for i, width in enumerate(column_widths):
        table.setColumnWidth(i, width)

    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()

    table_font = QFont()
    table_font.setPointSize(8)
    table.setFont(table_font)

    return table


def create_stats_label():
    """创建统计标签"""
    label = QLabel()
    label.setStyleSheet("color: #666; font-size: 12px;")
    return label


# ============ DI查询页面创建函数 ============

def create_di_lookup_page(parent, parser):
    """创建DI查询页面"""
    from PySide6.QtWidgets import QTableWidgetItem

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setSpacing(10)

    # 搜索栏
    def on_search(text):
        _filter_di_table(table, di_data, text, stats_label)

    search_layout, search_input = create_search_bar(
        parent,
        "输入DI编码(如E8020201)或中文关键词搜索...",
        on_search
    )
    layout.addLayout(search_layout)

    # 统计标签
    stats_label = create_stats_label()
    layout.addWidget(stats_label)

    # 表格
    table = create_table_widget(
        ["DI3", "DI2", "DI1", "DI0", "AFN", "中文含义"],
        [60, 60, 60, 60, 200, 300]
    )
    layout.addWidget(table)

    # 按钮栏
    btn_layout = QHBoxLayout()
    add_btn = QPushButton("添加自定义DI")
    add_btn.clicked.connect(lambda: QMessageBox.information(parent, "提示", "添加自定义DI功能待实现"))
    btn_layout.addWidget(add_btn)

    del_btn = QPushButton("删除选中自定义DI")
    del_btn.clicked.connect(lambda: QMessageBox.information(parent, "提示", "删除自定义DI功能待实现"))
    btn_layout.addWidget(del_btn)

    btn_layout.addStretch()
    layout.addLayout(btn_layout)

    # 加载数据
    di_data = _load_di_data(parser, table, stats_label)

    return widget, table, di_data, stats_label


def _load_di_data(parser, table, stats_label):
    """加载DI数据"""
    from PySide6.QtWidgets import QTableWidgetItem
    from PySide6.QtGui import QColor

    di_data = []
    di_map = parser.DI_COMBINATION_MAP
    afn_map = parser.AFN_MAP
    custom_list = parser.load_custom_di_list()
    custom_keys = {(e["di3"], e["di2"], e["di1"], e["di0"]) for e in custom_list}

    for (di3, di2, di1, di0), desc in di_map.items():
        afn_val = di1
        afn_name = afn_map.get(afn_val, f"未知({afn_val:02X})")
        is_custom = (di3, di2, di1, di0) in custom_keys
        di_data.append((di3, di2, di1, di0, afn_val, afn_name, desc, is_custom))

    _populate_di_table(table, di_data, stats_label)
    return di_data


def _populate_di_table(table, data, stats_label):
    """填充DI表格"""
    from PySide6.QtWidgets import QTableWidgetItem
    from PySide6.QtGui import QColor

    table.setRowCount(len(data))
    for row, (di3, di2, di1, di0, afn_val, afn_name, desc, is_custom) in enumerate(data):
        table.setItem(row, 0, QTableWidgetItem(f"{di3:02X}"))
        table.setItem(row, 1, QTableWidgetItem(f"{di2:02X}"))
        table.setItem(row, 2, QTableWidgetItem(f"{di1:02X}"))
        table.setItem(row, 3, QTableWidgetItem(f"{di0:02X}"))
        table.setItem(row, 4, QTableWidgetItem(f"{afn_val:02X}H {afn_name}"))
        desc_item = QTableWidgetItem(("★ " if is_custom else "") + desc)
        if is_custom:
            desc_item.setForeground(QColor("#1976D2"))
        table.setItem(row, 5, desc_item)

    stats_label.setText(f"共 {len(data)} 条记录")


def _filter_di_table(table, di_data, text, stats_label):
    """过滤DI表格"""
    keyword = text.strip().upper()
    if not keyword:
        _populate_di_table(table, di_data, stats_label)
        return

    filtered = []
    for di3, di2, di1, di0, afn_val, afn_name, desc, is_custom in di_data:
        di_str = f"{di3:02X}{di2:02X}{di1:02X}{di0:02X}"
        search_text = f"{di_str} {afn_name} {desc}".upper()
        if keyword in search_text:
            filtered.append((di3, di2, di1, di0, afn_val, afn_name, desc, is_custom))

    _populate_di_table(table, filtered, stats_label)