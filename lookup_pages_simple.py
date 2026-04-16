"""
简化版查询页面管理模块
直接使用函数创建页面
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor


def create_base_table(headers, column_widths):
    """创建基础表格"""
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

    font = QFont()
    font.setPointSize(8)
    table.setFont(font)

    return table


def create_command_lookup_page(parent):
    """创建命令字查询页面"""
    from command_lookup import get_command_lookup

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setSpacing(10)

    lookup = get_command_lookup()

    # 搜索栏
    search_layout = QHBoxLayout()
    search_label = QLabel("搜索：")
    search_label.setFixedWidth(45)
    search_input = QLineEdit()
    search_input.setPlaceholderText("输入命令字编码(如1001)或关键词搜索...")
    search_layout.addWidget(search_label)
    search_layout.addWidget(search_input)
    layout.addLayout(search_layout)

    # 统计标签
    stats_label = QLabel()
    stats_label.setStyleSheet("color: #666; font-size: 12px;")
    layout.addWidget(stats_label)

    # 表格
    table = create_base_table(
        ["命令字", "十六进制", "功能描述", "详细说明"],
        [100, 100, 250, 300]
    )
    layout.addWidget(table)

    # 加载数据
    def load_data():
        data = lookup._data
        table.setRowCount(len(data))
        for row, (code, name, desc, is_custom) in enumerate(data):
            table.setItem(row, 0, QTableWidgetItem(f"0x{code:04X}"))
            table.setItem(row, 1, QTableWidgetItem(f"{code}"))

            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            table.setItem(row, 2, name_item)

            table.setItem(row, 3, QTableWidgetItem(desc))

        stats_label.setText(f"共 {len(data)} 条记录")

    # 过滤功能
    def filter_table(text):
        keyword = text.strip().upper()
        if not keyword:
            load_data()
            return

        results = lookup.search(keyword)
        table.setRowCount(len(results))
        for row, (code, name, desc, is_custom) in enumerate(results):
            table.setItem(row, 0, QTableWidgetItem(f"0x{code:04X}"))
            table.setItem(row, 1, QTableWidgetItem(f"{code}"))

            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            table.setItem(row, 2, name_item)

            table.setItem(row, 3, QTableWidgetItem(desc))

        stats_label.setText(f"匹配 {len(results)} / {len(lookup._data)} 条记录")

    search_input.textChanged.connect(filter_table)

    # 初始加载
    load_data()

    return widget


def create_obis_lookup_page(parent):
    """创建OBIS查询页面"""
    from obis_lookup import get_obis_lookup

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setSpacing(10)

    lookup = get_obis_lookup()

    # 搜索栏
    search_layout = QHBoxLayout()
    search_label = QLabel("搜索：")
    search_label.setFixedWidth(45)
    search_input = QLineEdit()
    search_input.setPlaceholderText("输入OBIS码(如0.0.96.1.0.255)或关键词搜索...")
    search_layout.addWidget(search_label)
    search_layout.addWidget(search_input)
    layout.addLayout(search_layout)

    # 统计标签
    stats_label = QLabel()
    stats_label.setStyleSheet("color: #666; font-size: 12px;")
    layout.addWidget(stats_label)

    # 表格
    table = create_base_table(
        ["OBIS码", "对象名称", "对象类型", "访问属性", "详细说明"],
        [150, 200, 120, 100, 250]
    )
    layout.addWidget(table)

    # 加载数据
    def load_data():
        data = lookup._data
        table.setRowCount(len(data))
        for row, (obis, name, desc, is_custom) in enumerate(data):
            # OBIS码
            obis_str = f"{obis[0]}.{obis[1]}.{obis[2]}.{obis[3]}.{obis[4]}.{obis[5]}"
            table.setItem(row, 0, QTableWidgetItem(obis_str))

            # 对象名称
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            table.setItem(row, 1, name_item)

            # 对象类型（从desc推断）
            obj_type = _infer_object_type(obis)
            table.setItem(row, 2, QTableWidgetItem(obj_type))

            # 访问属性
            access = "Read/Write" if is_custom else "Read"
            table.setItem(row, 3, QTableWidgetItem(access))

            # 详细说明
            table.setItem(row, 4, QTableWidgetItem(desc))

        stats_label.setText(f"共 {len(data)} 条记录")

    def _infer_object_type(obis):
        """根据OBIS推断对象类型"""
        a = obis[0]
        type_map = {
            0: "General",
            1: "Register",
            2: "ExtendedRegister",
            3: "DemandRegister",
            4: "RegisterActivation",
            5: "ProfileGeneric",
            7: "ScriptTable",
            8: "Schedule",
            10: "Association LN",
            17: "ActivityCalendar",
            20: "DisconnectControl",
        }
        return type_map.get(a, f"Unknown_{a}")

    # 过滤功能
    def filter_table(text):
        keyword = text.strip().upper()
        if not keyword:
            load_data()
            return

        results = lookup.search(keyword)
        table.setRowCount(len(results))
        for row, (obis, name, desc, is_custom) in enumerate(results):
            obis_str = f"{obis[0]}.{obis[1]}.{obis[2]}.{obis[3]}.{obis[4]}.{obis[5]}"
            table.setItem(row, 0, QTableWidgetItem(obis_str))

            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            table.setItem(row, 1, name_item)

            obj_type = _infer_object_type(obis)
            table.setItem(row, 2, QTableWidgetItem(obj_type))

            access = "Read/Write" if is_custom else "Read"
            table.setItem(row, 3, QTableWidgetItem(access))

            table.setItem(row, 4, QTableWidgetItem(desc))

        stats_label.setText(f"匹配 {len(results)} / {len(lookup._data)} 条记录")

    search_input.textChanged.connect(filter_table)

    # 初始加载
    load_data()

    return widget