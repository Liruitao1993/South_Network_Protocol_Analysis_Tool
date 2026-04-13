"""
南网协议解析工具 - PySide6 GUI版
简洁界面，支持单帧解析和批量解析
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QHeaderView, QSplitter, QGroupBox, QDialog, QTabWidget, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor, QTextCharFormat, QColor

from protocol_parser import ProtocolFrameParser
from plc_rf_parser import PLCRFProtocolParser
from hdlc_parser import HDLCParser


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("南网本地通信接口协议解析工具260409")
        self.setMinimumSize(1000, 700)

        # 协议选择：0=南网协议，1=PLC RF协议，2=HDLC/DLMS协议
        self.current_protocol = 0

        # 初始化解析器
        self.parser = ProtocolFrameParser()
        self.plc_rf_parser = PLCRFProtocolParser()
        self.hdlc_parser = HDLCParser()

        # 批量解析结果缓存
        self.batch_results: List[Dict[str, Any]] = []

        # 字节高亮映射
        self._byte_ranges: list = []

        self.setup_ui()
        self.apply_styles()

    def setup_ui(self):
        """设置UI布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # 标题和协议选择行
        title_layout = QHBoxLayout()

        title_label = QLabel("南网本地通信接口协议解析工具含深化应用解析")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_layout.addWidget(title_label, 1)

        # 协议选择
        proto_layout = QHBoxLayout()
        proto_label = QLabel("选择协议：")
        proto_label.setFont(QFont("", 12, QFont.Bold))
        proto_layout.addWidget(proto_label)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem("南网协议 (Q/CSG1209021-2019)")
        self.protocol_combo.addItem("PLC RF协议 (万胜海外 V1_04)")
        self.protocol_combo.addItem("HDLC/DLMS协议 (IEC 62056-46)")
        self.protocol_combo.setMinimumWidth(300)
        self.protocol_combo.setFont(QFont("Microsoft YaHei", 11))
        # 移除焦点边框，保持简洁原生外观
        self.protocol_combo.currentIndexChanged.connect(self._on_protocol_changed)
        proto_layout.addWidget(self.protocol_combo)

        title_layout.addLayout(proto_layout)
        main_layout.addLayout(title_layout)

        # 选项卡
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.create_single_parse_tab(), "单帧解析")
        self.tab_widget.addTab(self.create_di_lookup_tab(), "DI查询")
        self.tab_widget.addTab(self.create_batch_parse_tab(), "批量解析")
        main_layout.addWidget(self.tab_widget)

    def create_single_parse_tab(self) -> QWidget:
        """创建单帧解析标签页 - 上下布局"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # === 上方：输入区 ===
        input_group = QGroupBox("输入报文")
        input_layout = QVBoxLayout(input_group)

        self.single_input = QTextEdit()
        self.single_input.setPlaceholderText("请输入十六进制报文，例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16")
        self.single_input.setMaximumHeight(80)
        input_layout.addWidget(self.single_input)

        # 按钮行
        btn_layout = QHBoxLayout()
        self.parse_btn = QPushButton("解析报文")
        self.parse_btn.setMinimumHeight(32)
        self.parse_btn.clicked.connect(self.parse_single)
        btn_layout.addWidget(self.parse_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setMinimumHeight(32)
        clear_btn.clicked.connect(self.clear_single)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()
        input_layout.addLayout(btn_layout)

        layout.addWidget(input_group)

        # === 下方：解析结果表格 ===
        result_group = QGroupBox("解析结果")
        result_layout = QVBoxLayout(result_group)

        self.result_table_widget = QTableWidget()
        self.result_table_widget.setColumnCount(4)
        self.result_table_widget.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        # 允许用户拖拽调整列宽
        header = self.result_table_widget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        # 设置默认列宽
        self.result_table_widget.setColumnWidth(0, 160)
        self.result_table_widget.setColumnWidth(1, 120)
        self.result_table_widget.setColumnWidth(2, 180)
        self.result_table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table_widget.setAlternatingRowColors(False)

        # 表格字体缩小，长帧时显示更多信息
        table_font = QFont()
        table_font.setPointSize(9)
        self.result_table_widget.setFont(table_font)
        # 行高紧凑
        self.result_table_widget.verticalHeader().setDefaultSectionSize(22)
        self.result_table_widget.verticalHeader().hide()

        # 选中行时高亮报文字节
        self.result_table_widget.currentCellChanged.connect(self._highlight_bytes)
        # 存储每行对应的字节范围
        self._byte_ranges: list = []

        result_layout.addWidget(self.result_table_widget)

        layout.addWidget(result_group, 1)

        return tab

    def create_di_lookup_tab(self) -> QWidget:
        """创建DI查询标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.di_search_input = QLineEdit()
        self.di_search_input.setPlaceholderText("输入DI编码(如E8020201)或中文关键词(如添加任务)搜索...")
        self.di_search_input.setClearButtonEnabled(True)
        self.di_search_input.textChanged.connect(self._filter_di_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.di_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.di_stats_label = QLabel()
        self.di_stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.di_stats_label)

        # 表格
        self.di_table = QTableWidget()
        self.di_table.setColumnCount(6)
        self.di_table.setHorizontalHeaderLabels(["DI3", "DI2", "DI1", "DI0", "AFN", "中文含义"])
        header = self.di_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.di_table.setColumnWidth(0, 60)
        self.di_table.setColumnWidth(1, 60)
        self.di_table.setColumnWidth(2, 60)
        self.di_table.setColumnWidth(3, 60)
        self.di_table.setColumnWidth(4, 200)
        self.di_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.di_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.di_table.setAlternatingRowColors(False)
        self.di_table.verticalHeader().hide()
        self.di_table.verticalHeader().setDefaultSectionSize(22)
        table_font = QFont()
        table_font.setPointSize(9)
        self.di_table.setFont(table_font)
        layout.addWidget(self.di_table)

        # 按钮栏
        btn_layout = QHBoxLayout()
        add_di_btn = QPushButton("添加自定义DI")
        add_di_btn.clicked.connect(self._add_custom_di)
        btn_layout.addWidget(add_di_btn)

        del_di_btn = QPushButton("删除选中自定义DI")
        del_di_btn.clicked.connect(self._del_custom_di)
        btn_layout.addWidget(del_di_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 加载数据
        self._load_di_map_data()

        return tab

    def _load_di_map_data(self):
        """从解析器加载DI组合MAP数据到表格（含自定义标记）"""
        self._di_data = []
        di_map = self.parser.DI_COMBINATION_MAP
        afn_map = self.parser.AFN_MAP
        custom_list = ProtocolFrameParser.load_custom_di_list()
        custom_keys = {(e["di3"], e["di2"], e["di1"], e["di0"]) for e in custom_list}

        for (di3, di2, di1, di0), desc in di_map.items():
            afn_val = di1
            afn_name = afn_map.get(afn_val, f"未知({afn_val:02X})")
            is_custom = (di3, di2, di1, di0) in custom_keys
            self._di_data.append((di3, di2, di1, di0, afn_val, afn_name, desc, is_custom))

        self.di_table.setRowCount(len(self._di_data))
        for row, (di3, di2, di1, di0, afn_val, afn_name, desc, is_custom) in enumerate(self._di_data):
            self.di_table.setItem(row, 0, QTableWidgetItem(f"{di3:02X}"))
            self.di_table.setItem(row, 1, QTableWidgetItem(f"{di2:02X}"))
            self.di_table.setItem(row, 2, QTableWidgetItem(f"{di1:02X}"))
            self.di_table.setItem(row, 3, QTableWidgetItem(f"{di0:02X}"))
            self.di_table.setItem(row, 4, QTableWidgetItem(f"{afn_val:02X}H {afn_name}"))
            desc_item = QTableWidgetItem(("★ " if is_custom else "") + desc)
            if is_custom:
                desc_item.setForeground(QColor("#1976D2"))
            self.di_table.setItem(row, 5, desc_item)

        self.di_stats_label.setText(f"共 {len(self._di_data)} 条记录（其中自定义 {len(custom_keys)} 条）")

    def _filter_di_table(self, text: str):
        """根据搜索文本过滤DI表格"""
        keyword = text.strip().upper()
        match_count = 0

        for row in range(self.di_table.rowCount()):
            if not keyword:
                self.di_table.setRowHidden(row, False)
                match_count += 1
                continue

            # 构建该行的搜索文本：DI拼接 + AFN + 中文含义
            di3 = self.di_table.item(row, 0).text()
            di2 = self.di_table.item(row, 1).text()
            di1 = self.di_table.item(row, 2).text()
            di0 = self.di_table.item(row, 3).text()
            afn_text = self.di_table.item(row, 4).text()
            desc_text = self.di_table.item(row, 5).text()

            di_str = f"{di3}{di2}{di1}{di0}"
            di_spaced = f"{di3} {di2} {di1} {di0}"
            search_text = f"{di_str} {di_spaced} {afn_text} {desc_text}".upper()

            if keyword in search_text:
                self.di_table.setRowHidden(row, False)
                match_count += 1
            else:
                self.di_table.setRowHidden(row, True)

        if keyword:
            self.di_stats_label.setText(f"匹配 {match_count} / {self.di_table.rowCount()} 条记录")
        else:
            self.di_stats_label.setText(f"共 {self.di_table.rowCount()} 条记录")

    def _add_custom_di(self):
        """添加自定义DI对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("添加自定义DI")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)

        # DI3
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("DI3:"))
        di3_input = QLineEdit()
        di3_input.setPlaceholderText("如 E8 或 EA")
        di3_input.setMaxLength(2)
        h1.addWidget(di3_input)
        layout.addLayout(h1)

        # DI2 DI1 DI0 同一行
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("DI2:"))
        di2_input = QLineEdit()
        di2_input.setMaxLength(2)
        h2.addWidget(di2_input)
        h2.addWidget(QLabel("DI1:"))
        di1_input = QLineEdit()
        di1_input.setMaxLength(2)
        h2.addWidget(di1_input)
        h2.addWidget(QLabel("DI0:"))
        di0_input = QLineEdit()
        di0_input.setMaxLength(2)
        h2.addWidget(di0_input)
        layout.addLayout(h2)

        # 中文含义
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("含义:"))
        desc_input = QLineEdit()
        desc_input.setPlaceholderText("如：查询XX信息")
        h3.addWidget(desc_input)
        layout.addLayout(h3)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("添加")
        cancel_btn = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() != QDialog.Accepted:
            return

        # 验证输入
        try:
            di3 = int(di3_input.text().strip(), 16)
            di2 = int(di2_input.text().strip(), 16)
            di1 = int(di1_input.text().strip(), 16)
            di0 = int(di0_input.text().strip(), 16)
        except ValueError:
            QMessageBox.warning(self, "错误", "DI字段必须为十六进制（00-FF）！")
            return

        desc = desc_input.text().strip()
        if not desc:
            QMessageBox.warning(self, "错误", "请填写中文含义！")
            return

        # 检查重复
        custom_list = ProtocolFrameParser.load_custom_di_list()
        key = (di3, di2, di1, di0)
        for e in custom_list:
            if (e["di3"], e["di2"], e["di1"], e["di0"]) == key:
                QMessageBox.warning(self, "重复", "该DI已存在于自定义列表中！")
                return

        # 保存到 JSON
        custom_list.append({"di3": di3, "di2": di2, "di1": di1, "di0": di0, "desc": desc})
        ProtocolFrameParser.save_custom_di(custom_list)

        # 合并到解析器（单帧解析也能识别）
        if key not in self.parser.DI_COMBINATION_MAP:
            self.parser.DI_COMBINATION_MAP[key] = desc

        # 刷新表格
        self._load_di_map_data()
        QMessageBox.information(self, "成功", f"已添加自定义DI: {di3:02X} {di2:02X} {di1:02X} {di0:02X} → {desc}")

    def _del_custom_di(self):
        """删除选中的自定义DI"""
        row = self.di_table.currentRow()
        if row < 0 or row >= len(self._di_data):
            QMessageBox.warning(self, "提示", "请先选中一条记录！")
            return

        di3, di2, di1, di0, afn_val, afn_name, desc, is_custom = self._di_data[row]

        if not is_custom:
            QMessageBox.warning(self, "提示", "只能删除自定义DI（蓝色★标记的记录）！")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除自定义DI：{di3:02X} {di2:02X} {di1:02X} {di0:02X} ({desc})？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 从 JSON 移除
        custom_list = ProtocolFrameParser.load_custom_di_list()
        key = (di3, di2, di1, di0)
        custom_list = [e for e in custom_list
                       if (e["di3"], e["di2"], e["di1"], e["di0"]) != key]
        ProtocolFrameParser.save_custom_di(custom_list)

        # 从解析器移除
        if key in self.parser.DI_COMBINATION_MAP:
            del self.parser.DI_COMBINATION_MAP[key]

        self._load_di_map_data()
        QMessageBox.information(self, "成功", "已删除自定义DI")

    def create_batch_parse_tab(self) -> QWidget:
        """创建批量解析标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        # 工具栏
        toolbar = QHBoxLayout()

        self.load_file_btn = QPushButton("从文件加载")
        self.load_file_btn.setToolTip("支持每行一帧的文本文件")
        self.load_file_btn.clicked.connect(self.load_from_file)
        toolbar.addWidget(self.load_file_btn)

        self.paste_btn = QPushButton("从剪贴板粘贴")
        self.paste_btn.clicked.connect(self.paste_from_clipboard)
        toolbar.addWidget(self.paste_btn)

        toolbar.addStretch()

        self.batch_parse_btn = QPushButton("开始批量解析")
        self.batch_parse_btn.setMinimumHeight(35)
        self.batch_parse_btn.clicked.connect(self.parse_batch)
        toolbar.addWidget(self.batch_parse_btn)

        self.clear_batch_btn = QPushButton("清空")
        self.clear_batch_btn.clicked.connect(self.clear_batch)
        toolbar.addWidget(self.clear_batch_btn)

        layout.addLayout(toolbar)

        # 输入区
        input_group = QGroupBox("输入报文列表（每行一帧）")
        input_layout = QVBoxLayout(input_group)

        self.batch_input = QTextEdit()
        self.batch_input.setPlaceholderText("粘贴或输入报文数据，支持混杂格式，例如：\n2024-01-01 12:00:00 [RX] 68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16\n[INFO] 68 0C 00 40 01 00 01 01 02 E8 2D 16")
        self.batch_input.setMaximumHeight(150)
        input_layout.addWidget(self.batch_input)

        layout.addWidget(input_group)

        # 结果统计
        self.stats_label = QLabel("状态：待解析")
        self.stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.stats_label)

        # 结果表格
        result_group = QGroupBox("解析结果")
        result_layout = QVBoxLayout(result_group)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels([
            "序号", "原始数据", "长度", "方向", "业务摘要", "状态"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.result_table.setColumnWidth(0, 50)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.cellClicked.connect(self.show_detail_dialog)
        result_layout.addWidget(self.result_table)

        # 批量导出按钮
        export_batch_btn = QPushButton("导出全部结果(JSON)")
        export_batch_btn.clicked.connect(self.export_batch)
        result_layout.addWidget(export_batch_btn)

        layout.addWidget(result_group, 1)

        return tab

    def apply_styles(self):
        """应用样式表 - 全局白色背景黑色字体"""
        self.setStyleSheet("""
            /* ========== 全局基础 ========== */
            * {
                color: #000000;
            }
            QWidget {
                background-color: #ffffff;
                color: #000000;
            }
            QMainWindow {
                background-color: #f5f5f5;
            }

            /* ========== 对话框 / 弹窗 ========== */
            QDialog {
                background-color: #ffffff;
                color: #000000;
            }
            QMessageBox {
                background-color: #ffffff;
                color: #000000;
            }
            QMessageBox QLabel {
                color: #000000;
                background-color: transparent;
            }
            QMessageBox QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #1976D2;
            }

            /* ========== 右键菜单 ========== */
            QMenu {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 30px 6px 20px;
                background-color: #ffffff;
                color: #000000;
            }
            QMenu::item:selected {
                background-color: #e3f2fd;
                color: #000000;
            }
            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 4px 8px;
            }

            /* ========== 工具提示 ========== */
            QToolTip {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 4px;
            }

            /* ========== 滚动条 ========== */
            QScrollBar:vertical {
                background-color: #f5f5f5;
                width: 10px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background-color: #f5f5f5;
                height: 10px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background-color: #c0c0c0;
                min-width: 30px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #a0a0a0;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }

            /* ========== 分组框 ========== */
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #ffffff;
                color: #000000;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #000000;
            }

            /* ========== 按钮 ========== */
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QPushButton#secondary {
                background-color: #757575;
            }

            /* ========== 文本编辑框 ========== */
            QTextEdit {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px;
                background-color: #ffffff;
                font-family: Consolas, Monaco, monospace;
                color: #000000;
            }

            /* ========== 行编辑框 ========== */
            QLineEdit {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px;
                background-color: #ffffff;
                color: #000000;
            }

            /* ========== 表格 ========== */
            QTableWidget {
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: #ffffff;
                gridline-color: #e0e0e0;
                color: #000000;
                font-size: 9pt;
            }
            QTableWidget::item {
                background-color: #ffffff;
                color: #000000;
                padding: 2px 4px;
            }
            QTableWidget::item:selected {
                background-color: #2196F3;
                color: white;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                padding: 4px 8px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
                color: #000000;
                font-size: 9pt;
            }

            /* ========== 标签 ========== */
            QLabel {
                color: #000000;
                background-color: transparent;
            }

            /* ========== 选项卡 ========== */
            QTabWidget::pane {
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                padding: 10px 20px;
                margin-right: 2px;
                border: 1px solid #cccccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                background-color: #f5f5f5;
                color: #000000;
            }
            QTabBar::tab:selected {
                background-color: #2196F3;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e0e0e0;
            }

            /* ========== 下拉框 ========== */
            QComboBox {
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: #ffffff;
                color: #000000;
            }
            QComboBox:hover {
                border: 1px solid #aaaaaa;
            }
            QComboBox:focus {
                border: 2px solid #2196F3;
                outline: none;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QListView {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                selection-background-color: #e3f2fd;
                selection-color: #000000;
                outline: none;
                min-width: 150px;
                padding: 2px;
            }
            QComboBox QListView::item {
                min-height: 24px;
                padding: 4px 8px;
                background-color: #ffffff;
                color: #000000;
                border: none;
            }
            QComboBox QListView::item:hover {
                background-color: #e3f2fd;
                color: #000000;
            }
            QComboBox QListView::item:selected {
                background-color: #e3f2fd;
                color: #000000;
            }

            /* ========== 复选框 / 单选框 ========== */
            QCheckBox, QRadioButton {
                color: #000000;
                background-color: transparent;
            }

            /* ========== 文件对话框 ========== */
            QFileDialog {
                background-color: #ffffff;
                color: #000000;
            }

            /* ========== 输入对话框 ========== */
            QInputDialog {
                background-color: #ffffff;
                color: #000000;
            }
        """)

    # ==================== 单帧解析功能 ====================

    def _on_protocol_changed(self, index: int):
        """协议选择改变时的回调"""
        self.current_protocol = index
        # 更新占位符提示
        if index == 0:
            self.single_input.setPlaceholderText("请输入十六进制报文，例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16")
            # 南网协议：显示DI查询标签页
            self.tab_widget.setTabVisible(1, True)
            self._load_di_map_data()
        elif index == 1:
            self.single_input.setPlaceholderText("请输入PLC RF报文，例如：02 00 05 C0 20 01 00 99")
            # PLC RF协议：隐藏DI查询标签页，显示命令字列表
            self.tab_widget.setTabVisible(1, False)
        else:  # index == 2, HDLC/DLMS协议
            self.single_input.setPlaceholderText("请输入HDLC报文，例如：7E A0 07 01 01 93 ... 7E")
            # HDLC协议：隐藏DI查询标签页
            self.tab_widget.setTabVisible(1, False)
        # 清空当前结果
        self.clear_single()

    def _get_current_parser(self):
        """获取当前选中的解析器"""
        if self.current_protocol == 0:
            return self.parser
        elif self.current_protocol == 1:
            return self.plc_rf_parser
        else:  # index == 2, HDLC/DLMS协议
            return self.hdlc_parser

    def load_example(self, data: str):
        """加载示例数据"""
        self.single_input.setText(data)

    def parse_single(self):
        """解析单帧报文"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 清理输入
        clean_input = input_text.replace(" ", "").replace("\n", "").replace("\t", "").strip()

        # 验证输入
        if not all(c in '0123456789abcdefABCDEF' for c in clean_input):
            QMessageBox.critical(self, "错误", "输入包含非法字符，请只输入十六进制字符（0-9, A-F）！")
            return

        if len(clean_input) % 2 != 0:
            QMessageBox.critical(self, "错误", "输入长度为奇数，十六进制字符串必须是偶数长度！")
            return

        try:
            # 转换为字节
            frame_bytes = bytes.fromhex(clean_input)

            # 格式化为空格分隔的 hex，方便高亮
            hex_display = ' '.join(f'{b:02X}' for b in frame_bytes)
            self.single_input.setPlainText(hex_display)

            # 使用当前选中的解析器
            current_parser = self._get_current_parser()
            table_data = current_parser.parse_to_table(frame_bytes)
            self._populate_table_from_data(table_data)

            # 保存当前结果
            self.current_result = frame_bytes

        except Exception as e:
            QMessageBox.critical(self, "解析错误", f"解析失败：{str(e)}")

    def clear_single(self):
        """清空单帧解析输入和结果"""
        self.single_input.clear()
        self.result_table_widget.setRowCount(0)
        self.current_result = None
        self._byte_ranges = []

    def export_single(self):
        """导出单帧解析结果"""
        if not hasattr(self, 'current_result') or not self.current_result:
            QMessageBox.warning(self, "警告", "没有可导出的解析结果！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存解析结果", "parse_result.txt", "文本文件 (*.txt)"
        )

        if file_path:
            try:
                # 使用当前选中的解析器
                current_parser = self._get_current_parser()
                table_data = current_parser.parse_to_table(self.current_result)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("字段\t原始值\t解析值\t说明\n")
                    for field_name, raw_value, parsed_value, comment, _, _ in table_data:
                        f.write(f"{field_name}\t{raw_value}\t{parsed_value}\t{comment}\n")
                QMessageBox.information(self, "成功", f"结果已保存到：{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败：{str(e)}")

    # ==================== 批量解析功能 ====================

    def load_from_file(self):
        """从文件加载报文列表"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择报文文件", "", "文本文件 (*.txt *.csv *.log);;所有文件 (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                self.batch_input.setPlainText(content)
                frames = self._extract_frames(content)
                self.update_stats(f"已从文件加载，识别到 {len(frames)} 帧报文（点击\"开始批量解析\"执行）")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"读取文件失败：{str(e)}")

    def paste_from_clipboard(self):
        """从剪贴板粘贴"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.batch_input.setPlainText(text)
            frames = self._extract_frames(text)
            self.update_stats(f"已粘贴，识别到 {len(frames)} 帧报文（点击\"开始批量解析\"执行）")

    @staticmethod
    def _extract_frames(text: str) -> list:
        """从混杂文本中提取完整的68起始帧

        预处理规则：
        1. 剔除时间戳、特殊符号前缀（[]、<>等非hex字符）
        2. 从hex字符串中按68H起始、16H结束提取完整帧
        3. 利用长度域校验帧完整性
        """
        import re
        # 将所有非hex字符替换为空
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()

        frames = []
        i = 0
        while i < len(clean) - 3:
            # 找下一个68起始
            pos = clean.find('68', i)
            if pos == -1:
                break

            # 尝试按长度域解析帧边界（小端序：低字节在前）
            if pos + 6 <= len(clean):
                try:
                    low_byte = int(clean[pos+2:pos+4], 16)
                    high_byte = int(clean[pos+4:pos+6], 16)
                    length = low_byte | (high_byte << 8)  # 小端序
                    frame_hex_len = length * 2

                    if pos + frame_hex_len <= len(clean):
                        candidate = clean[pos:pos+frame_hex_len]
                        if candidate[-2:] == '16':
                            frames.append(candidate)
                            i = pos + frame_hex_len
                            continue
                except (ValueError, IndexError):
                    pass

            # 长度解析失败，找最近的16结束符
            end = clean.find('16', pos + 6)
            if end != -1 and end - pos <= 2000:
                candidate = clean[pos:end+2]
                if len(candidate) >= 8:
                    frames.append(candidate)
                i = end + 2
            else:
                i = pos + 2

        return frames

    def parse_batch(self):
        """批量解析"""
        input_text = self.batch_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 智能提取帧
        frames = self._extract_frames(input_text)
        if not frames:
            QMessageBox.warning(self, "警告", "未识别到有效的68起始帧！")
            return

        # 清空之前的结果
        self.batch_results = []
        self.result_table.setRowCount(0)

        success_count = 0
        fail_count = 0

        for i, frame_hex in enumerate(frames):
            try:
                frame_bytes = bytes.fromhex(frame_hex)
                result = self.parser.parse(frame_bytes)

                # 提取摘要信息
                afn = "-"
                desc = "-"
                direction = "-"
                if "用户数据区" in result:
                    user_data = result["用户数据区"]
                    if "应用功能码(AFN)" in user_data:
                        afn_info = user_data["应用功能码(AFN)"]
                        afn = afn_info.get("名称", afn_info.get("原始值", "-"))
                    if "数据标识(DI)" in user_data:
                        di_info = user_data["数据标识(DI)"]
                        desc = di_info.get("业务说明", "-")

                if "控制域" in result:
                    ctrl = result["控制域"]
                    if "传输方向(DIR)" in ctrl:
                        d = ctrl["传输方向(DIR)"]["值"]
                        direction = "↑上行" if d == 1 else "↓下行"

                if result.get("解析状态") == "失败":
                    status = "解析失败"
                    fail_count += 1
                else:
                    status = "成功"
                    success_count += 1

                result["_input"] = frame_hex
                result["_status"] = status
                self.batch_results.append(result)

            except Exception as e:
                status = "异常"
                afn = "-"
                desc = str(e)[:30]
                direction = "-"
                fail_count += 1
                self.batch_results.append({"_input": frame_hex, "_status": status, "错误": str(e)})

            # 添加到表格
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem(str(i + 1)))

            hex_display = ' '.join(frame_hex[j:j+2] for j in range(0, len(frame_hex), 2))
            if len(hex_display) > 50:
                hex_display = hex_display[:50] + "..."
            self.result_table.setItem(row, 1, QTableWidgetItem(hex_display))
            self.result_table.setItem(row, 2, QTableWidgetItem(str(len(frame_hex) // 2)))
            self.result_table.setItem(row, 3, QTableWidgetItem(direction))
            self.result_table.setItem(row, 4, QTableWidgetItem(f"{afn} | {desc}"))

            status_item = QTableWidgetItem(status)
            if status == "成功":
                status_item.setForeground(Qt.darkGreen)
            else:
                status_item.setForeground(Qt.red)
            self.result_table.setItem(row, 5, status_item)

        self.update_stats(f"解析完成：成功 {success_count} 帧，失败 {fail_count} 帧，共 {len(frames)} 帧")

    def clear_batch(self):
        """清空批量解析内容"""
        self.batch_input.clear()
        self.result_table.setRowCount(0)
        self.batch_results = []
        self.update_stats("待解析")

    def export_batch(self):
        """导出批量解析结果"""
        if not self.batch_results:
            QMessageBox.warning(self, "警告", "没有可导出的解析结果！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存批量解析结果", "batch_parse_result.json", "JSON文件 (*.json)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.batch_results, f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, "成功", f"结果已保存到：{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败：{str(e)}")

    def show_detail_dialog(self, row, col):
        """单击列表行时弹出详细解析窗口（表格形式）"""
        if row < 0 or row >= len(self.batch_results):
            return

        result = self.batch_results[row]

        dialog = QDialog(self)
        dialog.setWindowTitle(f"解析详情 - 第 {row + 1} 帧")
        dialog.setMinimumSize(800, 500)

        layout = QVBoxLayout(dialog)

        # 原始数据
        raw_hex = result.get("_input", result.get("原始数据", ""))
        if raw_hex:
            hex_display = ' '.join(raw_hex[j:j+2] for j in range(0, len(raw_hex), 2))
            raw_label = QLabel(f"原始报文：{hex_display}")
            raw_label.setFont(QFont("Consolas", 10))
            raw_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            raw_label.setWordWrap(True)
            layout.addWidget(raw_label)

        # 用表格显示解析结果（复用单帧解析逻辑）
        if "_input" in result and result.get("_status") != "异常":
            try:
                frame_bytes = bytes.fromhex(result["_input"])
                table_data = self.parser.parse_to_table(frame_bytes)

                detail_table = QTableWidget()
                detail_table.setColumnCount(4)
                detail_table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
                header = detail_table.horizontalHeader()
                header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                header.setStretchLastSection(True)
                detail_table.setColumnWidth(0, 160)
                detail_table.setColumnWidth(1, 120)
                detail_table.setColumnWidth(2, 180)
                detail_table.setEditTriggers(QTableWidget.NoEditTriggers)
                detail_table.setSelectionBehavior(QTableWidget.SelectRows)
                detail_table.verticalHeader().hide()
                detail_table.verticalHeader().setDefaultSectionSize(22)
                table_font = QFont()
                table_font.setPointSize(9)
                detail_table.setFont(table_font)

                detail_table.setRowCount(len(table_data))
                for r, item in enumerate(table_data):
                    detail_table.setItem(r, 0, QTableWidgetItem(str(item[0])))
                    detail_table.setItem(r, 1, QTableWidgetItem(str(item[1])))
                    detail_table.setItem(r, 2, QTableWidgetItem(str(item[2])))
                    detail_table.setItem(r, 3, QTableWidgetItem(str(item[3])))

                layout.addWidget(detail_table)
            except Exception:
                # 回退到JSON显示
                text_edit = QTextEdit()
                text_edit.setReadOnly(True)
                text_edit.setFont(QFont("Consolas", 10))
                text_edit.setText(json.dumps(result, ensure_ascii=False, indent=2))
                layout.addWidget(text_edit)
        else:
            # 异常帧，显示错误信息
            error_text = result.get("错误", json.dumps(result, ensure_ascii=False, indent=2))
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setFont(QFont("Consolas", 10))
            text_edit.setText(error_text)
            layout.addWidget(text_edit)

        dialog.exec()

    def update_stats(self, text: str):
        """更新状态标签"""
        self.stats_label.setText(f"状态：{text}")
    
    # ==================== 表格结果填充与字节高亮 ====================

    def _populate_table_from_data(self, table_data: list):
        """从解析器生成的表格数据填充表格（6元组：含字节范围）"""
        self.result_table_widget.setRowCount(0)
        self._byte_ranges = []

        for row, item in enumerate(table_data):
            field_name, raw_value, parsed_value, comment = item[0], item[1], item[2], item[3]
            byte_start = item[4] if len(item) > 4 else None
            byte_end = item[5] if len(item) > 5 else None

            self.result_table_widget.insertRow(row)
            self.result_table_widget.setItem(row, 0, QTableWidgetItem(field_name))
            self.result_table_widget.setItem(row, 1, QTableWidgetItem(str(raw_value)))
            self.result_table_widget.setItem(row, 2, QTableWidgetItem(str(parsed_value)))
            self.result_table_widget.setItem(row, 3, QTableWidgetItem(str(comment)))
            self._byte_ranges.append((byte_start, byte_end))

    def _highlight_bytes(self, row: int, col: int, prev_row: int, prev_col: int):
        """选中表格行时，高亮输入框中对应的报文字节"""
        if not self._byte_ranges:
            return

        doc = self.single_input.document()
        cursor = QTextCursor(doc)

        # 先清除所有高亮，恢复默认格式
        cursor.select(QTextCursor.SelectionType.Document)
        default_fmt = QTextCharFormat()
        default_fmt.setFontFamily("Consolas, Monaco, monospace")
        default_fmt.setForeground(QColor("#000000"))
        default_fmt.setBackground(QColor("#FFFFFF"))
        cursor.setCharFormat(default_fmt)

        # 检查行有效性
        if row < 0 or row >= len(self._byte_ranges):
            return

        byte_start, byte_end = self._byte_ranges[row]
        if byte_start is None or byte_end is None:
            return

        # 在 "XX XX XX ..." 格式中，第 i 个字节对应字符位置 i*3 ~ i*3+1
        char_start = byte_start * 3
        char_end = byte_end * 3 + 2

        # 边界保护
        text_len = len(self.single_input.toPlainText())
        if char_end > text_len:
            char_end = text_len

        # 选中对应字符，应用高亮
        highlight_cursor = QTextCursor(doc)
        highlight_cursor.setPosition(char_start)
        highlight_cursor.setPosition(char_end, QTextCursor.MoveMode.KeepAnchor)

        hl_fmt = QTextCharFormat()
        hl_fmt.setFontFamily("Consolas, Monaco, monospace")
        hl_fmt.setForeground(QColor("#000000"))
        hl_fmt.setBackground(QColor(255, 235, 59, 160))  # 黄色半透明高亮
        highlight_cursor.setCharFormat(hl_fmt)


def main():
    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle('Fusion')

    # 设置字体
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
