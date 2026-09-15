"""
查询页面管理模块
简化版本 - 直接使用函数创建页面
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from gui_utils import setup_chinese_context_menu, ZoomableTableWidget, set_btn
import custom_di_store


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
    table = ZoomableTableWidget()
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
    """创建DI查询页面（自定义DI 增删按钮为真实功能，读写走 custom_di_store）"""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setSpacing(10)

    state = {"data": []}  # 当前表格数据；增删后重建，搜索过滤读它

    # 搜索栏
    def on_search(text):
        _filter_di_table(table, state["data"], text, stats_label)

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
    table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)  # 支持多选批量删除
    layout.addWidget(table)

    def reload_data():
        """重新读取解析器 DI 表 + 自定义条目，并刷新表格"""
        state["data"] = _load_di_data(parser, table, stats_label)

    # 按钮栏（真实增删：对话框 → 校验 → 落盘 custom_di.json → 表格刷新）
    def do_add():
        add_custom_di_interactive(parent, on_changed=reload_data)

    def do_del():
        delete_selected_custom_di_interactive(
            parent, table, state["data"], on_changed=reload_data
        )

    btn_layout = QHBoxLayout()
    add_btn = QPushButton("添加自定义DI")
    set_btn(add_btn, "primary")
    add_btn.clicked.connect(do_add)
    btn_layout.addWidget(add_btn)

    del_btn = QPushButton("删除选中自定义DI")
    set_btn(del_btn, "danger")
    del_btn.clicked.connect(do_del)
    btn_layout.addWidget(del_btn)

    btn_layout.addStretch()
    layout.addLayout(btn_layout)

    # 加载数据
    reload_data()

    return widget, table, state["data"], stats_label


def _load_di_data(parser, table, stats_label):
    """加载DI数据"""
    from PySide6.QtWidgets import QTableWidgetItem
    from PySide6.QtGui import QColor

    di_data = []
    di_map = parser.DI_COMBINATION_MAP
    afn_map = parser.AFN_MAP
    custom_keys = custom_di_store.custom_key_set()

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


# ============ 自定义DI 增删（与 main_gui 共用 custom_di_store）============

def _south_di_map() -> dict:
    """南网解析器单例的 DI_COMBINATION_MAP（增删后同步，单帧解析即时生效）"""
    from parser_registry import get_parser

    return get_parser("south").DI_COMBINATION_MAP


def add_custom_di_interactive(parent, on_changed=None) -> bool:
    """弹出「添加自定义DI」对话框 → 校验 → 落盘 → 刷新回调。

    Returns:
        是否真的写入了 custom_di.json（取消 / 校验失败 / 放弃覆盖均为 False）。
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle("添加自定义DI")
    dialog.setMinimumWidth(360)
    form = QVBoxLayout(dialog)

    row1 = QHBoxLayout()
    row1.addWidget(QLabel("DI3:"))
    di3_input = QLineEdit()
    di3_input.setPlaceholderText("如 E8 或 EA")
    di3_input.setMaxLength(2)
    row1.addWidget(di3_input)
    form.addLayout(row1)

    row2 = QHBoxLayout()
    row2.addWidget(QLabel("DI2:"))
    di2_input = QLineEdit()
    di2_input.setMaxLength(2)
    row2.addWidget(di2_input)
    row2.addWidget(QLabel("DI1:"))
    di1_input = QLineEdit()
    di1_input.setMaxLength(2)
    row2.addWidget(di1_input)
    row2.addWidget(QLabel("DI0:"))
    di0_input = QLineEdit()
    di0_input.setMaxLength(2)
    row2.addWidget(di0_input)
    form.addLayout(row2)

    row3 = QHBoxLayout()
    row3.addWidget(QLabel("含义:"))
    desc_input = QLineEdit()
    desc_input.setPlaceholderText("如：查询XX信息")
    row3.addWidget(desc_input)
    form.addLayout(row3)

    btns = QHBoxLayout()
    ok_btn = QPushButton("添加")
    cancel_btn = QPushButton("取消")
    btns.addStretch()
    btns.addWidget(ok_btn)
    btns.addWidget(cancel_btn)
    form.addLayout(btns)
    ok_btn.clicked.connect(dialog.accept)
    cancel_btn.clicked.connect(dialog.reject)

    if dialog.exec() != QDialog.Accepted:
        return False

    return apply_custom_di_add(
        parent,
        di3_input.text(),
        di2_input.text(),
        di1_input.text(),
        di0_input.text(),
        desc_input.text(),
        on_changed=on_changed,
    )


def apply_custom_di_add(
    parent, di3_text, di2_text, di1_text, di0_text, desc, on_changed=None
) -> bool:
    """校验并写入一条自定义DI（对话框 UI 之外的全部逻辑，供 GUI 复用）。

    - 校验失败 / 含义为空 → 提示并返回 False；
    - 重复 DI → 二次确认后覆盖其含义（条目上的其它字段由 store 保留）；
    - 成功 → 落盘 + 同步解析器 DI 表 + 刷新回调 + 提示。

    Returns:
        是否已写入 custom_di.json。
    """
    key, err = custom_di_store.validate_key_text(
        di3_text, di2_text, di1_text, di0_text
    )
    if key is None:
        QMessageBox.warning(parent, "错误", err)
        return False

    desc = (desc or "").strip()
    if not desc:
        QMessageBox.warning(parent, "错误", "请填写中文含义！")
        return False

    entries = custom_di_store.load_custom_di()
    if custom_di_store.find_entry(entries, key) is not None:
        reply = QMessageBox.question(
            parent,
            "DI 已存在",
            f"自定义DI {custom_di_store.format_key(key)} 已存在，是否覆盖其含义？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False

    entries, replaced = custom_di_store.upsert_entry(entries, key, desc)
    custom_di_store.save_custom_di(entries)
    _south_di_map()[key] = desc
    if on_changed:
        on_changed()
    QMessageBox.information(
        parent,
        "成功",
        f"已{'覆盖' if replaced else '添加'}自定义DI: "
        f"{custom_di_store.format_key(key)} → {desc}",
    )
    return True


def delete_selected_custom_di_interactive(
    parent, table, di_data, on_changed=None
) -> int:
    """删除表格中选中的自定义DI（支持多选）；内置 DI 拒绝删除。

    Returns:
        实际删除的条目数（取消 / 无选中 / 仅内置均为 0）。
    """
    rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()})
    if not rows:
        QMessageBox.warning(parent, "提示", "请先选中要删除的记录！")
        return 0

    picked = [di_data[r] for r in rows if 0 <= r < len(di_data)]
    custom = [item for item in picked if item[7]]
    builtin = [item for item in picked if not item[7]]
    if not custom:
        QMessageBox.warning(
            parent,
            "提示",
            f"选中的 {len(builtin)} 条均为内置DI（蓝色★标记的才是自定义DI），不可删除！",
        )
        return 0

    keys = [custom_di_store.make_key(i[0], i[1], i[2], i[3]) for i in custom]
    preview = "、".join(custom_di_store.format_key(k) for k in keys[:5])
    if len(keys) > 5:
        preview += f" 等 {len(keys)} 条"
    extra = f"\n（另有 {len(builtin)} 条内置DI将被忽略）" if builtin else ""
    reply = QMessageBox.question(
        parent,
        "确认删除",
        f"确定删除 {len(keys)} 条自定义DI：{preview}？{extra}",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return 0

    entries, removed = custom_di_store.remove_keys(
        custom_di_store.load_custom_di(), keys
    )
    custom_di_store.save_custom_di(entries)
    di_map = _south_di_map()
    for key in keys:
        di_map.pop(key, None)
    if on_changed:
        on_changed()
    QMessageBox.information(parent, "成功", f"已删除 {removed} 条自定义DI")
    return removed