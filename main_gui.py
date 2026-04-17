"""
南网协议解析工具 - PySide6 GUI版
简洁界面，支持单帧解析和批量解析
"""

import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QHeaderView, QSplitter, QGroupBox, QDialog, QTabWidget, QComboBox,
    QListView, QFrame, QMenuBar
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor, QTextCharFormat, QColor

from protocol_parser import ProtocolFrameParser
from plc_rf_parser import PLCRFProtocolParser
from hdlc_parser import HDLCParser
from dlt645_parser import DLT645Parser
from obis_lookup import OBISLookup, get_obis_lookup
from command_lookup import CommandLookup, get_command_lookup
from dlt645_di_lookup import DLT645DILookup, get_dlt645_di_lookup


APP_VERSION = "1.4.0"

CHANGELOG = [
    ("1.4.0", "2026-04-16", [
        "修复表格交替行颜色失效的问题（stylesheet优化）",
        "新增AGENTS.md项目指南文件，便于AI辅助开发",
        "PyInstaller打包配置修复：添加custom_di.json和dlt645_di.json到datas",
    ]),
    ("1.3.0", "2026-04-16", [
        "修复查询页面切换时按钮残留问题（递归清理layout）",
        "修复命令字查询页缺失的4个方法（_load_command_map_data等）",
        "修复命令字表格\"十六进制\"列显示十进制的bug，简化为2列",
        "新增菜单栏与\"关于\"对话框",
    ]),
    ("1.2.0", "2026-04-16", [
        "优化HDLC解析器，修复APDU数据解析中的索引错误",
        "新增Wrapper帧提取功能",
    ]),
    ("1.1.0", "2026-04-15", [
        "优化HDLC解析器，增强对返回数据和未知响应类型的处理",
        "更新主界面，改善协议选择和输入提示",
    ]),
    ("1.0.1", "2026-04-15", [
        "新增README文档",
        "更新编译后的二进制文件",
    ]),
    ("1.0.0", "2026-04-14", [
        "初始版本发布",
        "支持南网协议/PLC RF/HDLC/DLMS多协议解析",
        "单帧解析与批量解析功能",
        "DI/命令字/OBIS查询功能",
    ]),
]


def _get_git_changelog() -> list:
    """从git日志获取变更记录，用于动态追加到CHANGELOG"""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ai | %s", "-30"],
            capture_output=True, timeout=5,
            cwd=str(Path(__file__).parent),
        )
        if result.returncode != 0:
            return []
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                output = result.stdout.decode(enc)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        else:
            output = result.stdout.decode("utf-8", errors="replace")
        entries = []
        for line in output.strip().splitlines():
            if " | " in line:
                date_msg = line.split(" | ", 1)
                date = date_msg[0][:10]
                msg = date_msg[1]
                entries.append((date, msg))
        return entries
    except Exception:
        return []


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"协议解析工具 v{APP_VERSION}")
        self.setMinimumSize(1000, 700)

        # 协议选择：0=南网协议，1=PLC RF协议，2=HDLC/DLMS协议
        self.current_protocol = 0

        # 初始化解析器
        self.parser = ProtocolFrameParser()
        self.plc_rf_parser = PLCRFProtocolParser()
        self.hdlc_parser = HDLCParser()
        self.dlt645_parser = DLT645Parser()

        # 初始化查询器
        self.obis_lookup = get_obis_lookup()
        self.command_lookup = get_command_lookup()

        # 批量解析结果缓存
        self.batch_results: List[Dict[str, Any]] = []

        # 字节高亮映射
        self._byte_ranges: list = []

        self.setup_ui()
        self._setup_menu_bar()
        self.apply_styles()

    def setup_ui(self):
        """设置UI布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # 协议选择分组
        proto_group = QGroupBox("协议选择")
        proto_layout = QHBoxLayout(proto_group)
        proto_layout.setContentsMargins(10, 8, 10, 10)
        proto_layout.setSpacing(10)

        proto_label = QLabel("当前协议：")
        proto_label.setFont(QFont("", 10, QFont.Bold))
        proto_label.setFixedWidth(65)
        proto_layout.addWidget(proto_label)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem("南网协议 (Q/CSG1209021-2019)")
        self.protocol_combo.addItem("PLC RF协议 (万胜海外 V1_04)")
        self.protocol_combo.addItem("HDLC/DLMS协议 (IEC 62056-46)")
        self.protocol_combo.addItem("DLMS Wrapper裸报文")
        self.protocol_combo.addItem("DLMS-APDU裸报文")
        self.protocol_combo.addItem("DLT645-2007 电表协议")
        self.protocol_combo.setMinimumWidth(280)
        self.protocol_combo.setFont(QFont("Microsoft YaHei", 10))
        # 让弹出菜单宽度自动适应最宽的文字
        self.protocol_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.protocol_combo.currentIndexChanged.connect(self._on_protocol_changed)
        proto_layout.addWidget(self.protocol_combo)
        proto_layout.addStretch()

        main_layout.addWidget(proto_group)

        # 选项卡
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.create_single_parse_tab(), "单帧解析")
        # 查询页面根据协议动态创建
        self.protocol_lookup_tab = QWidget()
        self.protocol_lookup_tab_layout = QVBoxLayout(self.protocol_lookup_tab)
        self.tab_widget.addTab(self.protocol_lookup_tab, "查询")
        self.tab_widget.addTab(self.create_batch_parse_tab(), "批量解析")
        main_layout.addWidget(self.tab_widget)

        # 初始化查询页面内容
        self._update_protocol_lookup_tab()

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
        self.result_table_widget.setColumnWidth(0, 130)
        self.result_table_widget.setColumnWidth(1, 100)
        self.result_table_widget.setColumnWidth(2, 100)
        self.result_table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table_widget.setAlternatingRowColors(True)
        self.result_table_widget.verticalHeader().hide()
        self.result_table_widget.verticalHeader().setDefaultSectionSize(13)
        table_font = QFont()
        table_font.setPointSize(7)
        self.result_table_widget.setFont(table_font)
        # 行高更紧凑
        self.result_table_widget.verticalHeader().setDefaultSectionSize(10)
        self.result_table_widget.verticalHeader().hide()

        # 选中行时高亮报文字节
        self.result_table_widget.currentCellChanged.connect(self._highlight_bytes)
        # 双击行时，提取该区域字节作为DLMS-APDU重新解析
        self.result_table_widget.doubleClicked.connect(self._extract_apdu_reparse)
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
        self.di_table.setAlternatingRowColors(True)
        self.di_table.verticalHeader().hide()
        self.di_table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
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
        input_group = QGroupBox("输入报文列表（每行一帧，自动根据当前协议识别）")
        input_layout = QVBoxLayout(input_group)

        self.batch_input = QTextEdit()
        self.batch_input.setPlaceholderText("粘贴或输入报文数据，支持多种协议：\n南网协议：68开头，16结束\nHDLC协议：7E开头，7E结束\n其他协议：每行一帧直接解析")
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
        self.result_table.setAlternatingRowColors(True)
        # 紧凑字体和行高
        table_font = QFont()
        table_font.setPointSize(8)
        self.result_table.setFont(table_font)
        self.result_table.verticalHeader().setDefaultSectionSize(20)
        self.result_table.verticalHeader().hide()
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
            QTableWidget::item:!alternate {
                background-color: #ffffff;
                color: #000000;
                padding: 2px 4px;
            }
            QTableWidget::item:alternate {
                background-color: #e8e8e8;
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
                border: 1px solid #888;
                border-radius: 2px;
                padding: 4px 22px 4px 6px;
                background-color: #ffffff;
                color: #000000;
                min-height: 18px;
            }
            QComboBox:hover {
                border: 1px solid #666;
            }
            QComboBox:focus {
                border: 1px solid #6699cc;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #666;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #888;
                background-color: #ffffff;
                selection-background-color: #80b8e8;
                selection-color: #000000;
            }
            QComboBox QListView::item {
                padding: 3px 6px;
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

            /* ========== 菜单栏 ========== */
            QMenuBar {
                background-color: #f5f5f5;
                color: #000000;
                border-bottom: 1px solid #d0d0d0;
                padding: 2px;
            }
            QMenuBar::item {
                padding: 4px 10px;
                background-color: transparent;
            }
            QMenuBar::item:selected {
                background-color: #e0e0e0;
            }
            QMenu {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 30px 6px 20px;
            }
            QMenu::item:selected {
                background-color: #e3f2fd;
            }
        """)

    # ==================== 单帧解析功能 ====================

    def _on_protocol_changed(self, index: int):
        """协议选择改变时的回调"""
        self.current_protocol = index
        # 更新占位符提示
        if index == 0:
            self.single_input.setPlaceholderText("请输入十六进制报文，例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16")
        elif index == 1:
            self.single_input.setPlaceholderText("请输入PLC RF报文，例如：02 00 05 C0 20 01 00 99")
        elif index == 2:
            self.single_input.setPlaceholderText("请输入HDLC报文，例如：7E A0 07 01 01 93 ... 7E")
        elif index == 3:
            self.single_input.setPlaceholderText("请输入Wrapper报文，例如：00 01 00 02 00 1E ...")
        elif index == 4:  # DLMS-APDU裸报文
            self.single_input.setPlaceholderText("请输入APDU报文，例如：C0 01 C1 00 ...")
        else:  # index == 5, DLT645-2007
            self.single_input.setPlaceholderText("请输入DLT645报文，例如：68 AA AA AA AA AA AA 68 11 04 33 33 33 33 CS 16")

        # 更新查询页面
        self._update_protocol_lookup_tab()

        # 清空当前结果
        self.clear_single()

    def _update_protocol_lookup_tab(self):
        """根据当前协议更新查询页面内容"""
        # 清空当前查询页面内容（递归清除所有子layout和widget）
        self._clear_layout(self.protocol_lookup_tab_layout)

        # 更新选项卡标签
        lookup_tab_index = self.tab_widget.indexOf(self.protocol_lookup_tab)

        if self.current_protocol == 0:
            # 南网协议：DI查询
            self.tab_widget.setTabText(lookup_tab_index, "DI查询")
            self._create_di_lookup_content(self.protocol_lookup_tab_layout)

        elif self.current_protocol == 1:
            # 万胜PLC RF协议：命令字查询
            self.tab_widget.setTabText(lookup_tab_index, "命令字查询")
            self._create_command_lookup_content(self.protocol_lookup_tab_layout)

        elif self.current_protocol in (2, 3, 4):
            # HDLC/Wrapper/DLMS-APDU：OBIS查询
            self.tab_widget.setTabText(lookup_tab_index, "OBIS查询")
            self._create_obis_lookup_content(self.protocol_lookup_tab_layout)
            
        elif self.current_protocol == 5:
            # DLT645-2007协议：DI查询
            self.tab_widget.setTabText(lookup_tab_index, "DI查询")
            self._create_dlt645_di_lookup_content(self.protocol_lookup_tab_layout)

    def _create_di_lookup_content(self, layout):
        """创建南网协议DI查询页面内容"""
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
        self.di_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.di_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.di_table.setAlternatingRowColors(True)
        self.di_table.verticalHeader().hide()
        self.di_table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
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

    def _create_obis_lookup_content(self, layout):
        """创建OBIS查询页面（HDLC/Wrapper/APDU协议）"""
        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(30)
        self.obis_search_input = QLineEdit()
        self.obis_search_input.setPlaceholderText("输入OBIS码(如0.0.96.1.0.255)或关键词搜索...")
        self.obis_search_input.setClearButtonEnabled(True)
        self.obis_search_input.textChanged.connect(self._filter_obis_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.obis_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.obis_stats_label = QLabel()
        self.obis_stats_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.obis_stats_label)

        # 表格
        self.obis_table = QTableWidget()
        self.obis_table.setColumnCount(4)
        self.obis_table.setHorizontalHeaderLabels(["OBIS码", "对象名称", "对象类型", "访问属性"])
        header = self.obis_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.obis_table.setColumnWidth(0, 100)
        self.obis_table.setColumnWidth(1, 130)
        self.obis_table.setColumnWidth(2, 90)
        self.obis_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.obis_table.setAlternatingRowColors(True)
        self.obis_table.verticalHeader().hide()
        self.obis_table.verticalHeader().setDefaultSectionSize(14)
        table_font = QFont()
        table_font.setPointSize(7)
        self.obis_table.setFont(table_font)

        layout.addWidget(self.obis_table)

        # 加载数据
        self._load_obis_map_data()

    def _create_dlt645_di_lookup_content(self, layout):
        """创建DLT645-2007 DI查询页面"""
        # 初始化DI查询器
        self.dlt645_di_lookup = get_dlt645_di_lookup()

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.dlt645_di_search_input = QLineEdit()
        self.dlt645_di_search_input.setPlaceholderText("输入DI编码(如04000101)或中文关键词搜索...")
        self.dlt645_di_search_input.setClearButtonEnabled(True)
        self.dlt645_di_search_input.textChanged.connect(self._filter_dlt645_di_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.dlt645_di_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.dlt645_di_stats_label = QLabel()
        self.dlt645_di_stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.dlt645_di_stats_label)

        # 表格
        self.dlt645_di_table = QTableWidget()
        self.dlt645_di_table.setColumnCount(5)
        self.dlt645_di_table.setHorizontalHeaderLabels(["DI编码", "名称", "单位", "数据类型", "说明"])
        header = self.dlt645_di_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.dlt645_di_table.setColumnWidth(0, 90)
        self.dlt645_di_table.setColumnWidth(1, 180)
        self.dlt645_di_table.setColumnWidth(2, 60)
        self.dlt645_di_table.setColumnWidth(3, 80)
        self.dlt645_di_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dlt645_di_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.dlt645_di_table.setAlternatingRowColors(True)
        self.dlt645_di_table.verticalHeader().hide()
        self.dlt645_di_table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
        self.dlt645_di_table.setFont(table_font)

        layout.addWidget(self.dlt645_di_table)

        # 按钮栏
        btn_layout = QHBoxLayout()
        add_dlt645_di_btn = QPushButton("添加自定义DI")
        add_dlt645_di_btn.clicked.connect(self._add_dlt645_custom_di)
        btn_layout.addWidget(add_dlt645_di_btn)

        del_dlt645_di_btn = QPushButton("删除选中自定义DI")
        del_dlt645_di_btn.clicked.connect(self._del_dlt645_custom_di)
        btn_layout.addWidget(del_dlt645_di_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 加载数据
        self._load_dlt645_di_map_data()

    def _load_dlt645_di_map_data(self):
        """从DLT645 DI查询器加载数据到表格"""
        data = self.dlt645_di_lookup.data
        self._dlt645_di_data = data
        self.dlt645_di_table.setRowCount(len(data))
        for row, (di_code, di_name, unit, data_type, desc, is_custom) in enumerate(data):
            self.dlt645_di_table.setItem(row, 0, QTableWidgetItem(di_code))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + di_name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.dlt645_di_table.setItem(row, 1, name_item)
            self.dlt645_di_table.setItem(row, 2, QTableWidgetItem(unit))
            self.dlt645_di_table.setItem(row, 3, QTableWidgetItem(data_type))
            self.dlt645_di_table.setItem(row, 4, QTableWidgetItem(desc))
        custom_count = sum(1 for item in data if item[5])
        self.dlt645_di_stats_label.setText(f"共 {len(data)} 条记录（其中自定义 {custom_count} 条）")

    def _filter_dlt645_di_table(self, text: str):
        """根据搜索文本过滤DLT645 DI表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_dlt645_di_map_data()
            return
        results = self.dlt645_di_lookup.search(keyword)
        self.dlt645_di_table.setRowCount(len(results))
        for row, (di_code, di_name, unit, data_type, desc, is_custom) in enumerate(results):
            self.dlt645_di_table.setItem(row, 0, QTableWidgetItem(di_code))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + di_name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.dlt645_di_table.setItem(row, 1, name_item)
            self.dlt645_di_table.setItem(row, 2, QTableWidgetItem(unit))
            self.dlt645_di_table.setItem(row, 3, QTableWidgetItem(data_type))
            self.dlt645_di_table.setItem(row, 4, QTableWidgetItem(desc))
        custom_count = sum(1 for item in results if item[5])
        self.dlt645_di_stats_label.setText(f"匹配 {len(results)} / {len(self._dlt645_di_data)} 条记录（其中自定义 {custom_count} 条）")

    def _add_dlt645_custom_di(self):
        """添加DLT645自定义DI对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("添加自定义DI (DLT645)")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)

        # DI编码
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("DI编码:"))
        di_code_input = QLineEdit()
        di_code_input.setPlaceholderText("如 04000101")
        di_code_input.setMaxLength(8)
        h1.addWidget(di_code_input)
        layout.addLayout(h1)

        # 名称
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("名称:"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("如：当前正向有功总电能")
        h2.addWidget(name_input)
        layout.addLayout(h2)

        # 单位
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("单位:"))
        unit_input = QLineEdit()
        unit_input.setPlaceholderText("如：kWh（可留空）")
        h3.addWidget(unit_input)
        layout.addLayout(h3)

        # 数据类型
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("数据类型:"))
        data_type_input = QLineEdit()
        data_type_input.setPlaceholderText("如：XX（可留空）")
        h4.addWidget(data_type_input)
        layout.addLayout(h4)

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

        di_code = di_code_input.text().strip().upper()
        name = name_input.text().strip()
        unit = unit_input.text().strip()
        data_type = data_type_input.text().strip()

        if not di_code or not name:
            QMessageBox.warning(self, "错误", "DI编码和名称不能为空！")
            return

        success = self.dlt645_di_lookup.add_custom_di(di_code, name, unit, data_type)
        if success:
            self._load_dlt645_di_map_data()
            QMessageBox.information(self, "成功", f"已添加自定义DI: {di_code} → {name}")
        else:
            QMessageBox.warning(self, "错误", "添加失败，请检查DI编码格式（8位十六进制）")

    def _del_dlt645_custom_di(self):
        """删除选中的DLT645自定义DI"""
        row = self.dlt645_di_table.currentRow()
        if row < 0 or row >= len(self._dlt645_di_data):
            QMessageBox.warning(self, "提示", "请先选中一条记录！")
            return

        di_code, di_name, unit, data_type, desc, is_custom = self._dlt645_di_data[row]

        if not is_custom:
            QMessageBox.warning(self, "提示", "只能删除自定义DI（蓝色★标记的记录）！")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除自定义DI：{di_code} ({di_name})？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success = self.dlt645_di_lookup.delete_custom_di(di_code)
        if success:
            self._load_dlt645_di_map_data()
            QMessageBox.information(self, "成功", "已删除自定义DI")
        else:
            QMessageBox.warning(self, "错误", "删除失败")

    def _create_command_lookup_content(self, layout):
        """创建万胜PLC RF协议命令字查询页面"""
        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(30)
        self.cmd_search_input = QLineEdit()
        self.cmd_search_input.setPlaceholderText("输入命令字编码或中文关键词搜索...")
        self.cmd_search_input.setClearButtonEnabled(True)
        self.cmd_search_input.textChanged.connect(self._filter_command_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.cmd_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.cmd_stats_label = QLabel()
        self.cmd_stats_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.cmd_stats_label)

        # 表格
        self.cmd_table = QTableWidget()
        self.cmd_table.setColumnCount(2)
        self.cmd_table.setHorizontalHeaderLabels(["命令字", "名称"])
        header = self.cmd_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.cmd_table.setColumnWidth(0, 80)
        self.cmd_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cmd_table.setAlternatingRowColors(True)
        self.cmd_table.verticalHeader().hide()
        self.cmd_table.verticalHeader().setDefaultSectionSize(14)
        table_font = QFont()
        table_font.setPointSize(7)
        self.cmd_table.setFont(table_font)

        layout.addWidget(self.cmd_table)

        # 加载数据
        self._load_command_map_data()

    def _load_command_map_data(self):
        """从命令字查询器加载数据到表格"""
        data = self.command_lookup._data
        self.cmd_table.setRowCount(len(data))
        for row, (code, name, desc, is_custom) in enumerate(data):
            self.cmd_table.setItem(row, 0, QTableWidgetItem(f"{code:04X}"))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.cmd_table.setItem(row, 1, name_item)
        self.cmd_stats_label.setText(f"共 {len(data)} 条记录")

    def _filter_command_table(self, text: str):
        """根据搜索文本过滤命令字表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_command_map_data()
            return
        results = self.command_lookup.search(keyword)
        self.cmd_table.setRowCount(len(results))
        for row, (code, name, desc, is_custom) in enumerate(results):
            self.cmd_table.setItem(row, 0, QTableWidgetItem(f"{code:04X}"))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.cmd_table.setItem(row, 1, name_item)
        self.cmd_stats_label.setText(f"匹配 {len(results)} / {len(self.command_lookup._data)} 条记录")

    def _load_obis_map_data(self):
        """从OBIS查询器加载数据到表格"""
        data = self.obis_lookup._data
        self.obis_table.setRowCount(len(data))
        for row, (obis, name, desc, is_custom) in enumerate(data):
            obis_str = f"{obis[0]}.{obis[1]}.{obis[2]}.{obis[3]}.{obis[4]}.{obis[5]}"
            self.obis_table.setItem(row, 0, QTableWidgetItem(obis_str))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.obis_table.setItem(row, 1, name_item)
            # 根据OBIS A值推断对象类型
            a = obis[0]
            type_map = {
                0: "General", 1: "Register", 2: "ExtendedRegister",
                3: "DemandRegister", 5: "ProfileGeneric", 7: "ScriptTable",
                10: "Association LN", 17: "ActivityCalendar",
                20: "DisconnectControl",
            }
            self.obis_table.setItem(row, 2, QTableWidgetItem(type_map.get(a, f"Type_{a}")))
            self.obis_table.setItem(row, 3, QTableWidgetItem("Read/Write" if is_custom else "Read"))
        self.obis_stats_label.setText(f"共 {len(data)} 条记录")

    def _filter_obis_table(self, text: str):
        """根据搜索文本过滤OBIS表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_obis_map_data()
            return
        results = self.obis_lookup.search(keyword)
        self.obis_table.setRowCount(len(results))
        for row, (obis, name, desc, is_custom) in enumerate(results):
            obis_str = f"{obis[0]}.{obis[1]}.{obis[2]}.{obis[3]}.{obis[4]}.{obis[5]}"
            self.obis_table.setItem(row, 0, QTableWidgetItem(obis_str))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.obis_table.setItem(row, 1, name_item)
            a = obis[0]
            type_map = {
                0: "General", 1: "Register", 2: "ExtendedRegister",
                3: "DemandRegister", 5: "ProfileGeneric", 7: "ScriptTable",
                10: "Association LN", 17: "ActivityCalendar",
                20: "DisconnectControl",
            }
            self.obis_table.setItem(row, 2, QTableWidgetItem(type_map.get(a, f"Type_{a}")))
            self.obis_table.setItem(row, 3, QTableWidgetItem("Read/Write" if is_custom else "Read"))
        self.obis_stats_label.setText(f"匹配 {len(results)} / {len(self.obis_lookup._data)} 条记录")

    def _get_current_parser(self):
        """获取当前选中的解析器"""
        if self.current_protocol == 0:
            return self.parser
        elif self.current_protocol == 1:
            return self.plc_rf_parser
        elif self.current_protocol == 2:  # HDLC/DLMS协议 (完整HDLC帧)
            return self.hdlc_parser
        elif self.current_protocol == 3:  # DLMS Wrapper裸报文 (直接解析Wrapper+APDU)
            # 返回一个匿名对象，调用parse_wrapper_to_table
            class WrapperParser:
                def __init__(self, hdlc_parser):
                    self.hdlc_parser = hdlc_parser
                def parse_to_table(self, data):
                    return self.hdlc_parser.parse_wrapper_to_table(data)
            return WrapperParser(self.hdlc_parser)
        elif self.current_protocol == 4:  # DLMS-APDU裸报文 (直接解析APDU)
            # 返回一个匿名对象，调用parse_apdu_to_table
            class APDUParser:
                def __init__(self, hdlc_parser):
                    self.hdlc_parser = hdlc_parser
                def parse_to_table(self, data):
                    return self.hdlc_parser.parse_apdu_to_table(data)
            return APDUParser(self.hdlc_parser)
        else:  # self.current_protocol == 5, DLT645-2007
            class DLT645GuiParser:
                def __init__(self, parser):
                    self.parser = parser
                def parse_to_table(self, data):
                    result = self.parser.parse(data)
                    table = []
                    # DLT645 帧结构计算字节范围
                    data_len = result.get('data_length', 0)
                    total_len = 10 + data_len + 2

                    for field, raw, desc in result['fields']:
                        byte_start = 0
                        byte_end = 0
                        parsed_value = ''

                        if '帧起始符 1' in field:
                            byte_start, byte_end = 0, 0
                        elif '从站地址' in field:
                            byte_start, byte_end = 1, 6
                        elif '帧起始符 2' in field:
                            byte_start, byte_end = 7, 7
                        elif '控制码' in field:
                            byte_start, byte_end = 8, 8
                            parsed_value = result.get('control_parsed', '')
                        elif '数据长度' in field:
                            byte_start, byte_end = 9, 9
                        elif '数据标识 DI' in field:
                            byte_start, byte_end = 10, 13
                            di_code = result.get('di_code', '')
                            di_desc = result.get('di_desc', '')
                            parsed_value = f"{di_code} ({di_desc})" if di_code and di_desc else di_code
                        elif '数据内容' in field:
                            byte_start, byte_end = 14, 10 + data_len - 1
                        elif '数据域' in field:
                            byte_start, byte_end = 10, 10 + data_len - 1
                        elif '校验和' in field:
                            byte_start, byte_end = total_len - 2, total_len - 2
                        elif '帧结束符' in field:
                            byte_start, byte_end = total_len - 1, total_len - 1

                        table.append((field, raw, parsed_value, desc, byte_start, byte_end))

                    return table
            return DLT645GuiParser(self.dlt645_parser)

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

    @staticmethod
    def _clear_layout(layout):
        """递归清除layout中的所有子layout和widget"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                MainWindow._clear_layout(child.layout())

    def _setup_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        help_menu = menubar.addMenu("帮助(&H)")

        about_action = help_menu.addAction("关于(&A)")
        about_action.triggered.connect(self._show_about_dialog)

    def _show_about_dialog(self):
        """显示"关于"对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("关于")
        dialog.setMinimumSize(520, 480)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        title_label = QLabel(f"协议解析工具")
        title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        version_label = QLabel(f"版本 2.0")
        version_label.setFont(QFont("Microsoft YaHei", 11))
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #666;")
        layout.addWidget(version_label)

        desc_label = QLabel("支持南网协议 / PLC RF / HDLC/DLMS 多协议报文解析")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        changelog_label = QLabel("版本更新记录")
        changelog_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        layout.addWidget(changelog_label)

        changelog_text = QTextEdit()
        changelog_text.setReadOnly(True)
        changelog_text.setFont(QFont("Microsoft YaHei", 9))

        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        html_parts = []
        html_parts.append(f"<b>v2.0 ({today})</b><ul>")
        html_parts.append("<li>优化界面布局，提高信息密度</li>")
        html_parts.append("<li>统一表格字体为7pt，行高压缩至13px</li>")
        html_parts.append("</ul>")
        html_parts.append("<b>v1.0</b><ul>")
        html_parts.append("<li>初始版本发布</li>")
        html_parts.append("<li>支持南网、PLC RF、HDLC/DLMS、DLT645协议</li>")
        html_parts.append("</ul>")

        changelog_text.setHtml("".join(html_parts))
        layout.addWidget(changelog_text)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        dialog.exec()

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
    def _clear_layout(layout):
        """递归清除layout中的所有子layout和widget"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                MainWindow._clear_layout(child.layout())

    @staticmethod
    def _extract_frames(text: str) -> list:
        """从混杂文本中提取完整的68起始帧（南网协议）

        预处理规则：
        1. 剔除时间戳、特殊符号前缀（[]、<>等非hex字符）
        2. 从hex字符串中按68H起始、利用长度域+校验和验证帧完整性
        """
        import re
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()

        frames = []
        i = 0
        while i < len(clean) - 7:
            pos = clean.find('68', i)
            if pos == -1:
                break

            if pos + 6 > len(clean):
                break

            try:
                low_byte = int(clean[pos + 2:pos + 4], 16)
                high_byte = int(clean[pos + 4:pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue

            if length < 8 or length > 2048:
                i = pos + 2
                continue

            frame_hex_len = length * 2
            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue

            candidate = clean[pos:pos + frame_hex_len]
            if candidate[-2:] != '16':
                i = pos + 2
                continue

            try:
                frame_bytes = bytes.fromhex(candidate)
                cs_expected = sum(frame_bytes[3:length - 1]) & 0xFF
                cs_actual = frame_bytes[length - 1]
                if cs_expected == cs_actual:
                    frames.append(candidate)
                    i = pos + frame_hex_len
                    continue
            except ValueError:
                pass

            i = pos + 2

        return frames

    def parse_batch(self):
        """批量解析 - 支持所有协议"""
        input_text = self.batch_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 根据当前协议选择帧提取方式
        frames = self._extract_frames_for_protocol(input_text, self.current_protocol)
        if not frames:
            QMessageBox.warning(self, "警告", f"未识别到有效帧！")
            return

        # 清空之前的结果
        self.batch_results = []
        self.result_table.setRowCount(0)

        success_count = 0
        fail_count = 0

        for i, frame_hex in enumerate(frames):
            table_data = []
            direction = "-"
            try:
                frame_bytes = bytes.fromhex(frame_hex)
                # 使用当前协议对应的解析器
                current_parser = self._get_current_parser()
                # 调用parse_to_table生成表格数据
                table_data = current_parser.parse_to_table(frame_bytes)

                # 南网协议提取方向
                if self.current_protocol == 0:
                    direction = self._extract_direction_from_table(table_data)

                # 从表格数据生成摘要（取前3个字段作为摘要）
                summary = self._get_summary_from_table_data(table_data)

                status = "成功"
                success_count += 1

                # 保存结果（表格数据可以在详情查看时使用）
                self.batch_results.append({
                    "_input": frame_hex,
                    "_status": status,
                    "_table_data": table_data,
                    "摘要": summary
                })

            except Exception as e:
                status = "异常"
                summary = str(e)[:50]
                fail_count += 1
                # 异常时 table_data 为空，方向保持 "-"
                self.batch_results.append({
                    "_input": frame_hex,
                    "_status": status,
                    "错误": str(e),
                    "摘要": summary
                })

            # 添加到表格
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem(str(i + 1)))

            hex_display = ' '.join(frame_hex[j:j+2] for j in range(0, len(frame_hex), 2))
            if len(hex_display) > 50:
                hex_display = hex_display[:50] + "..."
            self.result_table.setItem(row, 1, QTableWidgetItem(hex_display))
            self.result_table.setItem(row, 2, QTableWidgetItem(str(len(frame_hex) // 2)))

            # 方向：南网协议从控制域DIR位解析，其他协议暂无
            direction = "-"
            if self.current_protocol == 0:
                direction = self._extract_direction_from_table(table_data)
            self.result_table.setItem(row, 3, QTableWidgetItem(direction))

            # 业务摘要
            self.result_table.setItem(row, 4, QTableWidgetItem(summary))

            # 状态
            status_item = QTableWidgetItem(status)
            if status == "成功":
                status_item.setForeground(Qt.darkGreen)
            else:
                status_item.setForeground(Qt.red)
            self.result_table.setItem(row, 5, status_item)

        self.update_stats(f"解析完成：成功 {success_count} 帧，失败 {fail_count} 帧，共 {len(frames)} 帧")

    def _extract_direction_from_table(self, table_data: list) -> str:
        """从南网协议表格数据中提取传输方向"""
        # table_data 格式: (field_name, raw_value, parsed_value, comment, byte_start, byte_end)
        # 控制域子字段"传输方向"的 field_name 为"  传输方向"（带前缀空格）
        for item in table_data:
            field_name = item[0]
            parsed_val = item[2]
            # 查找传输方向字段（去除空格后匹配）
            if "传输方向" in field_name or "DIR" in field_name:
                dir_code = str(parsed_val).strip()
                if dir_code == "0":
                    return "下行帧(集中器→模块)"
                elif dir_code == "1":
                    return "上行帧(模块→集中器)"
                else:
                    return f"未知({dir_code})"
        return "-"

    def _get_summary_from_table_data(self, table_data: list) -> str:
        """从表格数据中提取摘要信息，取重要的前几个字段拼接"""
        if not table_data:
            return "-"

        summary_parts = []

        if self.current_protocol == 0:
            # 南网协议：提取 AFN 名称（comment）、SEQ 值、DI 业务说明（comment）
            afn_val = None
            seq_val = None
            di_desc = None
            for item in table_data:
                field_name = item[0]
                parsed_val = item[2]
                comment = item[3]
                if field_name == "应用功能码 (AFN)":
                    # AFN 的 parsed_val 为空，说明在 comment 中
                    afn_val = comment if comment else parsed_val
                elif field_name == "帧序列号 (SEQ)":
                    seq_val = parsed_val
                elif field_name == "数据标识 (DI)":
                    # DI 的业务说明在 comment 中
                    if comment and not di_desc:
                        di_desc = comment
            if di_desc:
                summary_parts.insert(0, f"DI:{di_desc}")
            if afn_val is not None:
                summary_parts.append(f"AFN:{afn_val}")
            if seq_val is not None:
                summary_parts.append(f"SEQ:{seq_val}")
            return " | ".join(summary_parts) if summary_parts else "-"

        else:
            # 其他协议：取前几个非冗余字段
            for i, item in enumerate(table_data):
                if i >= 4:
                    break
                field_name = item[0]
                parsed_val = item[2]
                if any(k in field_name for k in ["帧起始", "格式", "长度", "校验", "结束标志"]):
                    continue
                summary_parts.append(f"{parsed_val}")
            return " | ".join(summary_parts) if summary_parts else "-"

    def _extract_frames_for_protocol(self, text: str, protocol_index: int) -> list:
        """根据协议提取对应格式的帧"""
        import re

        if protocol_index == 0:
            # 南网协议：68开头，16结束
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            return self._extract_68_frames(clean)
        elif protocol_index == 1:
            # PLC RF协议：尝试通用提取
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            return self._extract_generic_frames(clean, min_len=4, max_len=256)
        elif protocol_index == 2:
            # HDLC/DLMS协议：7E开头，7E结束
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            return self._extract_hdlc_frames(clean)
        elif protocol_index == 3:
            # DLMS Wrapper裸报文：识别Wrapper头部(8字节)并分割
            return self._extract_wrapper_frames(text)
        elif protocol_index == 4:
            # DLMS-APDU裸报文：按行分割，每行一帧
            return [f.strip() for f in text.splitlines() if f.strip()]
        else:
            # 通用：每行一帧
            return [f.strip() for f in text.splitlines() if f.strip()]

    def _extract_wrapper_frames(self, text: str) -> list:
        """
        从文本中提取Wrapper帧
        Wrapper格式: 版本(2B) + 源端口(2B) + 目的端口(2B) + 长度(2B) = 8字节头部
        版本固定为 0x0001
        支持处理带日志前缀的格式，如 "WRAPPER[1] Sent 0001000000010000003B ..."
        """
        import re
        frames = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # 提取连续的长串十六进制数据（至少16个字符）
            # 这样 WRAPPER 中的零散字母不会被误认为数据
            hex_matches = re.findall(r'[0-9A-Fa-f]{16,}', line)
            if not hex_matches:
                continue

            for hex_pattern in hex_matches:
                hex_pattern = hex_pattern.upper()

                # 扫描整个十六进制字符串，寻找Wrapper头部 (0001xxxx)
                i = 0
                while i <= len(hex_pattern) - 16:  # 至少需要8字节(16字符)头部
                    # 检查是否是Wrapper头部: 版本=0001
                    if hex_pattern[i:i+4] == '0001':
                        # 解析Wrapper头部的长度字段
                        apdu_len = int(hex_pattern[i+12:i+16], 16)

                        # 验证长度合理性（允许apdu_len=0，因为数据可能被截断）
                        if 0 <= apdu_len <= 8192:
                            # 计算完整帧长度: 8字节头部 + apdu_len
                            frame_len = 16 + apdu_len * 2

                            if i + frame_len <= len(hex_pattern):
                                # 提取完整帧
                                frame_hex = hex_pattern[i:i+frame_len]
                                frames.append(frame_hex)
                                i += frame_len
                                continue
                            else:
                                # 数据被截断，但仍提取可用的头部+部分数据
                                frame_hex = hex_pattern[i:]
                                frames.append(frame_hex)
                                break
                    i += 2

        return frames if frames else [re.sub(r'[^0-9A-Fa-f]', '', text).upper()]

    def _extract_hdlc_frames(self, clean: str) -> list:
        """提取HDLC帧（7E开头，7E结束）"""
        frames = []
        i = 0
        while i < len(clean) - 3:
            # 找下一个7E起始
            pos = clean.find('7E', i)
            if pos == -1:
                break
            # 找下一个7E结束
            end = clean.find('7E', pos + 2)
            if end == -1:
                # 如果没找到结束，直接取到结尾或者最大长度
                end = min(pos + 512, len(clean))
            candidate = clean[pos:end + 2]
            if len(candidate) >= 6:  # 至少3字节
                frames.append(candidate)
            i = end + 2
        return frames

    def _extract_68_frames(self, clean: str) -> list:
        """提取南网68格式帧（Q/CSG1209021-2019 FT1.2）

        帧格式: 68H | L(2B小端) | C(1B) | 用户数据(L-6字节) | CS(1B) | 16H
        L = 帧总字节数（含起始符、长度域、控制域、校验和、结束符）
        验证规则:
          1. 起始字符 = 68H
          2. L >= 8（最小帧长度）
          3. 帧末尾 = 16H
          4. 校验和：从控制域到用户数据末尾的所有字节累加和 mod 256
        """
        frames = []
        i = 0
        while i < len(clean) - 7:
            # 找下一个 68 起始
            pos = clean.find('68', i)
            if pos == -1:
                break

            # 尝试按长度域解析帧边界
            if pos + 6 > len(clean):
                i = pos + 2
                continue

            try:
                low_byte = int(clean[pos + 2:pos + 4], 16)
                high_byte = int(clean[pos + 4:pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue

            # L 至少为 8（起始1 + 长度2 + 控制1 + 校验1 + 结束1 + 用户数据至少3）
            if length < 8 or length > 2048:
                i = pos + 2
                continue

            frame_hex_len = length * 2

            # 检查数据是否足够
            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue

            candidate = clean[pos:pos + frame_hex_len]

            # 验证结束符 = 16H
            if candidate[-2:] != '16':
                i = pos + 2
                continue

            # 通过长度域和结束符验证，接受此帧（不校验CS，由解析器负责校验）
            frames.append(candidate)
            i = pos + frame_hex_len
            continue

        return frames

    def _extract_generic_frames(self, clean: str, min_len: int = 4, max_len: int = 512) -> list:
        """通用帧提取：按行或直接提取完整有效hex字符串"""
        if len(clean) >= min_len * 2 and len(clean) <= max_len * 2:
            return [clean] if len(clean) % 2 == 0 else []
        return []

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

        # 用表格显示解析结果
        if "_input" in result and result.get("_status") != "异常":
            try:
                # 优先使用批量解析时已保存的表格数据
                if "_table_data" in result:
                    table_data = result["_table_data"]
                else:
                    # 否则重新用当前协议解析器解析
                    frame_bytes = bytes.fromhex(result["_input"])
                    current_parser = self._get_current_parser()
                    table_data = current_parser.parse_to_table(frame_bytes)

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
                detail_table.setAlternatingRowColors(True)
                detail_table.verticalHeader().hide()
                detail_table.verticalHeader().setDefaultSectionSize(20)
                table_font = QFont()
                table_font.setPointSize(8)
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

    def _extract_apdu_reparse(self, index):
        """双击表格行时，提取该行对应字节范围，弹窗深度解析DLMS-APDU"""
        row = index.row()
        if not self._byte_ranges or row < 0 or row >= len(self._byte_ranges):
            return

        byte_start, byte_end = self._byte_ranges[row]
        if byte_start is None or byte_end is None:
            return

        # 获取完整原始报文（从输入框解析得到）
        if not hasattr(self, 'current_result'):
            QMessageBox.information(self, "提示", "无法获取原始报文数据，请先解析")
            return

        full_bytes = self.current_result
        # 提取对应范围字节（byte_end 包含在内）
        extracted_bytes = full_bytes[byte_start : byte_end + 1]

        if len(extracted_bytes) == 0:
            QMessageBox.information(self, "提示", "选中区域字节为空")
            return

        # 自动识别协议类型
        extracted_bytes = bytes(extracted_bytes)
        dialog_title = ""
        try:
            # 先检测是否是DLT645协议帧
            if len(extracted_bytes) >=12 and extracted_bytes[0] == 0x68 and extracted_bytes[7] == 0x68 and extracted_bytes[-1] == 0x16:
                # DLT645协议
                result = self.dlt645_parser.parse(extracted_bytes)
                parsed_data = []
                for field, raw, desc in result['fields']:
                    parsed_data.append((field, raw, '', desc, 0, 0))
                dialog_title = f"深度解析DLT645-2007 (提取 {len(extracted_bytes)} 字节)"
            else:
                # 默认DLMS APDU协议
                parsed_data = self.hdlc_parser.parse_apdu_to_table(extracted_bytes)
                dialog_title = f"深度解析DLMS-APDU (提取 {len(extracted_bytes)} 字节)"
        except Exception as e:
            QMessageBox.critical(self, "解析错误", f"解析失败:\n{str(e)}")
            return

        # 创建弹窗显示解析结果
        dialog = QDialog(self)
        dialog.setWindowTitle(dialog_title)
        dialog.resize(900, 600)

        layout = QVBoxLayout(dialog)

        # 显示提取的十六进制
        hex_text = QTextEdit()
        hex_text.setReadOnly(True)
        hex_text.setFont(QFont("Consolas", 10))
        hex_text.setMaximumHeight(80)
        hex_str = ' '.join(f'{b:02X}' for b in extracted_bytes)
        hex_text.setText(f"提取字节: {hex_str}")
        layout.addWidget(hex_text)

        # 解析结果表格
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["字段", "十六进制", "解析值", "说明"])
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        table.setColumnWidth(0, 160)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 180)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
        table.setFont(table_font)

        for r, item in enumerate(parsed_data):
            field_name = item[0]
            raw_hex = item[1]
            parsed_val = str(item[2])
            comment = item[3]
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(field_name))
            table.setItem(r, 1, QTableWidgetItem(raw_hex))
            table.setItem(r, 2, QTableWidgetItem(parsed_val))
            table.setItem(r, 3, QTableWidgetItem(comment))

        layout.addWidget(table)
        dialog.setLayout(layout)
        dialog.exec()


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
