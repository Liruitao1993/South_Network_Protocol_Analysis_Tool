"""可视化测试项编辑器

提供图形化界面让测试工程师不写代码就能配置测试项。
支持从解析结果导入、模板导入、协议字段表单配置。
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QLineEdit, QComboBox, QSpinBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFormLayout, QMessageBox, QFileDialog, QTextEdit,
    QSplitter
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class VisualTestItemEditor(QDialog):
    """可视化测试项编辑器对话框"""

    def __init__(self, parent=None, edit_data: Optional[Dict] = None,
                 protocol: str = "south"):
        """
        参数:
            parent: 父窗口
            edit_data: 编辑模式下的测试项数据
            protocol: 当前协议类型
        """
        super().__init__(parent)
        self._edit_mode = edit_data is not None
        self._edit_data = edit_data or {}
        self._protocol = protocol
        self._result = None

        self.setWindowTitle("编辑测试项" if self._edit_mode else "添加测试项")
        self.setMinimumSize(700, 600)
        self._setup_ui()

        if self._edit_mode:
            self._load_edit_data()

    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 标签页
        tab_widget = QTabWidget()

        # 基本模式标签页
        basic_tab = self._create_basic_tab()
        tab_widget.addTab(basic_tab, "基本模式")

        # 高级模式标签页（从解析结果导入）
        advanced_tab = self._create_advanced_tab()
        tab_widget.addTab(advanced_tab, "从解析导入")

        # 模板标签页
        template_tab = self._create_template_tab()
        tab_widget.addTab(template_tab, "从模板导入")

        layout.addWidget(tab_widget, 1)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        ok_btn = QPushButton("确定")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _create_basic_tab(self) -> QWidget:
        """创建基本模式标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # 性质选择
        nature_group = QGroupBox("测试项性质")
        nature_layout = QHBoxLayout(nature_group)
        nature_layout.addWidget(QLabel("性质:"))
        self._nature_combo = QComboBox()
        self._nature_combo.addItem("发送帧 - 发送帧并等待匹配响应", "send")
        self._nature_combo.addItem("后台监听 - 持续监听匹配收到的帧", "listen")
        self._nature_combo.addItem("纯等待 - 仅等待指定时间", "wait")
        self._nature_combo.currentIndexChanged.connect(self._on_nature_changed)
        nature_layout.addWidget(self._nature_combo, 1)
        layout.addWidget(nature_group)

        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_form = QFormLayout(basic_group)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("输入测试项名称，如：查询厂商代码")
        basic_form.addRow("名称:", self._name_edit)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(100, 600000)
        self._timeout_spin.setValue(2000)
        self._timeout_spin.setSuffix(" ms")
        basic_form.addRow("超时:", self._timeout_spin)

        layout.addWidget(basic_group)

        # 帧内容
        frame_group = QGroupBox("帧内容")
        frame_layout = QVBoxLayout(frame_group)

        frame_layout.addWidget(QLabel("发送帧 (HEX):"))
        self._frame_edit = QLineEdit()
        self._frame_edit.setPlaceholderText("输入十六进制报文，如：68 0C 00 00 03 00 01 03 00 E8 EF 16")
        frame_layout.addWidget(self._frame_edit)

        # 匹配规则
        match_layout = QHBoxLayout()
        match_layout.addWidget(QLabel("匹配规则:"))
        self._match_edit = QLineEdit()
        self._match_edit.setPlaceholderText("XX 为通配符，如：68 XX 00 88 03 00 01 03 00 E8 XX XX 16")
        match_layout.addWidget(self._match_edit, 1)

        self._match_mode_combo = QComboBox()
        self._match_mode_combo.addItems(["HEX", "ASCII"])
        match_layout.addWidget(self._match_mode_combo)

        frame_layout.addLayout(match_layout)

        # 启用匹配
        self._match_enabled_check = QCheckBox("启用匹配")
        self._match_enabled_check.setChecked(True)
        frame_layout.addWidget(self._match_enabled_check)

        layout.addWidget(frame_group)

        # 响应帧
        response_group = QGroupBox("响应帧 (可选)")
        response_layout = QVBoxLayout(response_group)

        response_layout.addWidget(QLabel("匹配成功后自动发送的响应帧:"))
        self._response_edit = QLineEdit()
        self._response_edit.setPlaceholderText("支持动态标记：【\"time\",6,Y-M-D-h-m-s,\"little\"】【\"CS\",1,3:-2】")
        response_layout.addWidget(self._response_edit)

        layout.addWidget(response_group)

        return tab

    def _create_advanced_tab(self) -> QWidget:
        """创建高级模式标签页（从解析导入）"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # 说明
        info_label = QLabel("在此粘贴一个完整的 HEX 报文，系统会自动解析并生成测试项。\n"
                           "您可以选择需要匹配的字段，其他字段自动设为通配符。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; padding: 8px;")
        layout.addWidget(info_label)

        # 输入区
        input_group = QGroupBox("输入报文")
        input_layout = QVBoxLayout(input_group)

        self._import_hex_edit = QLineEdit()
        self._import_hex_edit.setPlaceholderText("粘贴 HEX 报文，如：68 0E 00 88 03 00 01 03 00 E8 XX XX 16")
        input_layout.addWidget(self._import_hex_edit)

        import_btn_layout = QHBoxLayout()
        parse_btn = QPushButton("解析")
        parse_btn.clicked.connect(self._on_parse_import)
        import_btn_layout.addWidget(parse_btn)

        from_file_btn = QPushButton("从文件导入")
        from_file_btn.clicked.connect(self._on_import_from_file)
        import_btn_layout.addWidget(from_file_btn)

        import_btn_layout.addStretch()
        input_layout.addLayout(import_btn_layout)

        layout.addWidget(input_group)

        # 解析结果
        result_group = QGroupBox("解析结果 - 勾选需要匹配的字段")
        result_layout = QVBoxLayout(result_group)

        self._import_result_table = QTableWidget()
        self._import_result_table.setColumnCount(5)
        self._import_result_table.setHorizontalHeaderLabels(["匹配", "字段", "原始值", "解析值", "说明"])
        header = self._import_result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self._import_result_table.setColumnWidth(0, 50)
        self._import_result_table.setColumnWidth(1, 120)
        self._import_result_table.setColumnWidth(2, 100)
        self._import_result_table.setColumnWidth(3, 100)
        result_layout.addWidget(self._import_result_table)

        # 全选/全不选
        select_btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(self._on_select_all_fields)
        select_btn_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("全不选")
        deselect_all_btn.clicked.connect(self._on_deselect_all_fields)
        select_btn_layout.addWidget(deselect_all_btn)

        select_btn_layout.addStretch()

        apply_btn = QPushButton("应用到测试项")
        apply_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; padding: 6px 16px; border-radius: 3px; }"
        )
        apply_btn.clicked.connect(self._on_apply_import)
        select_btn_layout.addWidget(apply_btn)

        result_layout.addLayout(select_btn_layout)
        layout.addWidget(result_group, 1)

        return tab

    def _create_template_tab(self) -> QWidget:
        """创建模板标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # 说明
        info_label = QLabel("从预置模板中选择测试项，快速添加到测试方案。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; padding: 8px;")
        layout.addWidget(info_label)

        # 模板选择
        template_group = QGroupBox("选择模板")
        template_layout = QVBoxLayout(template_group)

        # 模板列表
        self._template_table = QTableWidget()
        self._template_table.setColumnCount(4)
        self._template_table.setHorizontalHeaderLabels(["模板名称", "协议", "分类", "步骤数"])
        header = self._template_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._template_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._template_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._template_table.doubleClicked.connect(self._on_template_double_clicked)
        template_layout.addWidget(self._template_table)

        # 加载模板按钮
        btn_layout = QHBoxLayout()

        load_template_btn = QPushButton("加载选中模板")
        load_template_btn.clicked.connect(self._on_load_template)
        btn_layout.addWidget(load_template_btn)

        from_file_btn = QPushButton("从文件加载模板")
        from_file_btn.clicked.connect(self._on_load_template_from_file)
        btn_layout.addWidget(from_file_btn)

        btn_layout.addStretch()
        template_layout.addLayout(btn_layout)

        layout.addWidget(template_group, 1)

        # 加载模板数据
        self._load_template_list()

        return tab

    def _on_nature_changed(self, index):
        """性质变化"""
        nature = self._nature_combo.currentData()
        if nature == "listen":
            self._frame_edit.setEnabled(False)
            self._match_enabled_check.setChecked(True)
            self._match_enabled_check.setEnabled(False)
        elif nature == "wait":
            self._frame_edit.setEnabled(False)
            self._match_enabled_check.setChecked(False)
            self._match_enabled_check.setEnabled(False)
        else:
            self._frame_edit.setEnabled(True)
            self._match_enabled_check.setChecked(True)
            self._match_enabled_check.setEnabled(True)

    def _on_parse_import(self):
        """解析导入的 HEX"""
        hex_text = self._import_hex_edit.text().strip()
        if not hex_text:
            QMessageBox.warning(self, "警告", "请输入 HEX 报文")
            return

        # 清理 HEX
        clean_hex = hex_text.replace(" ", "").replace("\n", "")
        if len(clean_hex) % 2 != 0:
            QMessageBox.warning(self, "警告", "HEX 长度必须是偶数")
            return

        try:
            frame_bytes = bytes.fromhex(clean_hex)
        except ValueError as e:
            QMessageBox.critical(self, "错误", f"无效的 HEX 格式: {e}")
            return

        # 尝试解析
        parse_result = self._try_parse(frame_bytes)
        if not parse_result:
            QMessageBox.warning(self, "警告", "无法解析此报文，请检查格式")
            return

        # 填充表格
        self._import_result_table.setRowCount(len(parse_result))
        for row_idx, row_data in enumerate(parse_result):
            # 匹配复选框
            check_item = QTableWidgetItem()
            check_item.setCheckState(Qt.Checked)
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            self._import_result_table.setItem(row_idx, 0, check_item)

            # 字段名
            self._import_result_table.setItem(row_idx, 1, QTableWidgetItem(str(row_data[0])))

            # 原始值
            self._import_result_table.setItem(row_idx, 2, QTableWidgetItem(str(row_data[1])))

            # 解析值
            self._import_result_table.setItem(row_idx, 3, QTableWidgetItem(str(row_data[2])))

            # 说明
            self._import_result_table.setItem(row_idx, 4, QTableWidgetItem(str(row_data[3])))

    def _try_parse(self, frame_bytes: bytes) -> Optional[List]:
        """尝试解析帧"""
        try:
            from protocol_parser import ProtocolFrameParser
            from gdw10376_parser import GDW10376Parser
            from hdlc_parser import HDLCParser
            from plc_rf_parser import PLCRFProtocolParser
            from dlt645_parser import DLT645Parser

            # 识别协议并解析
            if frame_bytes[0] == 0x68 and frame_bytes[-1] == 0x16:
                parser = ProtocolFrameParser()
                return parser.parse_to_table(frame_bytes)
            elif frame_bytes[0] == 0x7E:
                parser = HDLCParser()
                return parser.parse_to_table(frame_bytes)
            elif frame_bytes[0] == 0x02:
                parser = PLCRFProtocolParser()
                return parser.parse_to_table(frame_bytes)
        except Exception as e:
            print(f"解析失败: {e}")
        return None

    def _on_import_from_file(self):
        """从文件导入"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入报文", "", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            self._import_hex_edit.setText(content)
            self._on_parse_import()
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def _on_select_all_fields(self):
        """全选字段"""
        for row in range(self._import_result_table.rowCount()):
            item = self._import_result_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)

    def _on_deselect_all_fields(self):
        """全不选字段"""
        for row in range(self._import_result_table.rowCount()):
            item = self._import_result_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)

    def _on_apply_import(self):
        """应用导入结果到测试项"""
        hex_text = self._import_hex_edit.text().strip()
        if not hex_text:
            QMessageBox.warning(self, "警告", "请先解析报文")
            return

        clean_hex = hex_text.replace(" ", "")

        # 生成匹配规则
        match_rule = self._generate_match_rule(clean_hex)

        # 设置到基本模式
        self._frame_edit.setText(self._format_hex(clean_hex))
        self._match_edit.setText(self._format_hex(match_rule))

        # 生成名称
        if not self._name_edit.text():
            self._name_edit.setText(f"导入的帧-{datetime.now().strftime('%H%M%S')}")

        QMessageBox.information(self, "成功", "已应用到测试项，请切换到基本模式查看")

    def _generate_match_rule(self, hex_str: str) -> str:
        """根据字段选择生成匹配规则"""
        # 如果没有解析结果，返回全通配
        if self._import_result_table.rowCount() == 0:
            return hex_str

        # 构建匹配规则
        rule_chars = list(hex_str)

        for row in range(self._import_result_table.rowCount()):
            check_item = self._import_result_table.item(row, 0)
            if not check_item or check_item.checkState() != Qt.Checked:
                # 未选中的字段设为通配符
                # 获取原始值的字节位置
                original = self._import_result_table.item(row, 2)
                if original:
                    orig_hex = original.text().replace(" ", "")
                    # 在 hex_str 中查找并替换为 XX
                    pos = hex_str.find(orig_hex)
                    if pos >= 0:
                        for i in range(len(orig_hex)):
                            if pos + i < len(rule_chars):
                                rule_chars[pos + i] = 'X' if i % 2 == 0 else 'X'

        return "".join(rule_chars)

    def _on_load_template(self):
        """加载选中的模板"""
        current_row = self._template_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "警告", "请先选择一个模板")
            return

        # 获取模板名称
        name_item = self._template_table.item(current_row, 0)
        if not name_item:
            return

        template_name = name_item.text()

        # 加载模板
        from templates.test_templates import get_template_by_name
        template = get_template_by_name(template_name)
        if template:
            self._loaded_template = template
            QMessageBox.information(self, "成功", f"已加载模板: {template_name}\n共 {len(template.items)} 个步骤")

    def _on_load_template_from_file(self):
        """从文件加载模板"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载模板", "", "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if not file_path:
            return

        from templates.test_templates import load_template_from_json
        template = load_template_from_json(file_path)
        if template:
            self._loaded_template = template
            QMessageBox.information(self, "成功", f"已加载模板: {template.name}")
        else:
            QMessageBox.critical(self, "错误", "无法加载模板文件")

    def _on_template_double_clicked(self, index):
        """双击模板"""
        self._on_load_template()

    def _load_template_list(self):
        """加载模板列表"""
        from templates.test_templates import get_templates

        templates = get_templates()
        self._template_table.setRowCount(len(templates))

        for idx, template in enumerate(templates):
            self._template_table.setItem(idx, 0, QTableWidgetItem(template.name))
            self._template_table.setItem(idx, 1, QTableWidgetItem(template.protocol))
            self._template_table.setItem(idx, 2, QTableWidgetItem(template.category))
            self._template_table.setItem(idx, 3, QTableWidgetItem(str(len(template.items))))

    def _load_edit_data(self):
        """加载编辑数据"""
        self._name_edit.setText(self._edit_data.get('name', ''))

        nature = 'send'
        if self._edit_data.get('persistent'):
            nature = 'listen'
        elif not self._edit_data.get('send_enabled', True):
            nature = 'wait'

        for i in range(self._nature_combo.count()):
            if self._nature_combo.itemData(i) == nature:
                self._nature_combo.setCurrentIndex(i)
                break

        self._frame_edit.setText(self._format_hex(self._edit_data.get('frame_hex', '')))
        self._match_edit.setText(self._format_hex(self._edit_data.get('match_rule', '')))

        mode = self._edit_data.get('match_mode', 'HEX')
        self._match_mode_combo.setCurrentText(mode)

        self._timeout_spin.setValue(self._edit_data.get('timeout_ms', 2000))
        self._match_enabled_check.setChecked(self._edit_data.get('match_enabled', True))
        self._response_edit.setText(self._format_hex(self._edit_data.get('response_frame', '')))

    def _on_ok(self):
        """确定"""
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "警告", "请输入测试项名称")
            return

        nature = self._nature_combo.currentData()

        self._result = {
            'name': name,
            'frame_hex': self._frame_edit.text().replace(" ", ""),
            'match_rule': self._match_edit.text().replace(" ", ""),
            'match_mode': self._match_mode_combo.currentText(),
            'timeout_ms': self._timeout_spin.value(),
            'send_enabled': nature == 'send',
            'match_enabled': nature in ('send', 'listen'),
            'response_frame': self._response_edit.text().replace(" ", ""),
            'persistent': nature == 'listen',
        }

        self.accept()

    def get_result(self) -> Optional[Dict[str, Any]]:
        """获取编辑结果"""
        return self._result

    def _format_hex(self, hex_str: str) -> str:
        """格式化 HEX 字符串"""
        if not hex_str:
            return ""
        clean = hex_str.replace(" ", "").upper()
        return " ".join(clean[i:i+2] for i in range(0, len(clean), 2))
