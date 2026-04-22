"""南网协议组帧Widget

提供基于DI_FIELD_SCHEMA的动态表单和通用组帧界面，
支持预定义schema和自定义字段模板两种模式。
可嵌入main_gui.py作为独立标签页使用。
"""

from typing import Dict, Any, List, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QGroupBox, QScrollArea, QCheckBox, QMessageBox, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeyEvent

from send_frame_lib import ProtocolFrameGenerator
from frame_generator_schema import DI_FIELD_SCHEMA
from protocol_parser import ProtocolFrameParser


# =============================================================================
# 通用字段模板类型定义
# =============================================================================

class CustomFieldTemplate:
    """通用字段模板项（参考图2模式）"""
    def __init__(self, name: str = "", length: int = 1, ftype: str = "uint8",
                 endian: str = "big", display: str = "hex", reverse: bool = False):
        self.name = name
        self.length = length
        self.ftype = ftype      # uint8/uint16/uint32/bytes/checksum
        self.endian = endian    # big/little
        self.display = display  # hex/dec
        self.reverse = reverse  # 字节反转（地址类）


class FrameGenWidget(QWidget):
    """协议组帧页面Widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.generator = ProtocolFrameGenerator()
        self.parser = ProtocolFrameParser()
        self._field_widgets: Dict[str, Dict[str, Any]] = {}
        self._current_di_key: Tuple[int, int, int, int] = None
        self._form_container: QWidget = None
        self._custom_templates: List[CustomFieldTemplate] = []
        self._custom_mode = False
        self._update_timer: QTimer = None
        self.serial_worker = None
        self.setup_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)

        # ================== 左侧面板 ==================
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(6)

        # ---- DI 选择 ----
        di_group = QGroupBox("DI 选择")
        di_layout = QHBoxLayout(di_group)
        di_layout.setContentsMargins(6, 4, 6, 4)
        di_layout.setSpacing(6)
        di_layout.addWidget(QLabel("选择命令："))
        self.di_combo = QComboBox()
        self.di_combo.setMinimumWidth(360)
        self.di_combo.setEditable(True)
        self.di_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.di_combo.completer().setCompletionMode(self.di_combo.completer().CompletionMode.PopupCompletion)
        self.di_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self._populate_di_combo()
        self.di_combo.currentIndexChanged.connect(self._on_di_changed)
        di_layout.addWidget(self.di_combo)

        self.cmd_help_btn = QPushButton("命令说明")
        self.cmd_help_btn.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; "
            "border-radius: 3px; padding: 2px 10px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.cmd_help_btn.setEnabled(False)
        self.cmd_help_btn.clicked.connect(self._on_cmd_help_clicked)
        di_layout.addWidget(self.cmd_help_btn)
        di_layout.addStretch()
        left_layout.addWidget(di_group)

        # ---- 帧配置（地址、控制域） ----
        config_group = QGroupBox("帧配置")
        config_layout = QHBoxLayout(config_group)
        config_layout.setContentsMargins(6, 4, 6, 4)
        config_layout.setSpacing(6)

        config_layout.addWidget(QLabel("源地址:"))
        self.src_addr_input = QLineEdit("000000000000")
        self.src_addr_input.setMaxLength(12)
        config_layout.addWidget(self.src_addr_input)

        config_layout.addWidget(QLabel("目的地址:"))
        self.dst_addr_input = QLineEdit("000000000000")
        self.dst_addr_input.setMaxLength(12)
        config_layout.addWidget(self.dst_addr_input)

        config_layout.addWidget(QLabel("DIR:"))
        self.dir_combo = QComboBox()
        self.dir_combo.addItem("0-下行(集中器→模块)", 0)
        self.dir_combo.addItem("1-上行(模块→集中器)", 1)
        config_layout.addWidget(self.dir_combo)

        config_layout.addWidget(QLabel("PRM:"))
        self.prm_combo = QComboBox()
        self.prm_combo.addItem("0-从动站", 0)
        self.prm_combo.addItem("1-启动站", 1)
        config_layout.addWidget(self.prm_combo)

        config_layout.addWidget(QLabel("ADD:"))
        self.add_combo = QComboBox()
        self.add_combo.addItem("0-不带地址域", 0)
        self.add_combo.addItem("1-带地址域", 1)
        config_layout.addWidget(self.add_combo)

        config_layout.addStretch()
        left_layout.addWidget(config_group)

        # ---- 模式切换 ----
        self.mode_group = QGroupBox("字段模式")
        mode_layout = QHBoxLayout(self.mode_group)
        mode_layout.setContentsMargins(6, 4, 6, 4)
        mode_layout.setSpacing(6)
        self.mode_predefined_rb = QCheckBox("使用预定义字段")
        self.mode_predefined_rb.setChecked(True)
        self.mode_predefined_rb.stateChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_predefined_rb)

        self.mode_custom_rb = QCheckBox("使用自定义字段模板")
        self.mode_custom_rb.stateChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_custom_rb)
        mode_layout.addStretch()
        left_layout.addWidget(self.mode_group)

        # ---- 动态表单区 ----
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        self._form_container = QWidget()
        self._form_layout = QVBoxLayout(self._form_container)
        self._form_layout.setAlignment(Qt.AlignTop)
        form_scroll.setWidget(self._form_container)
        left_layout.addWidget(form_scroll, 1)

        # ---- 生成按钮 ----
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        self.generate_btn = QPushButton("生成帧")
        self.generate_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "border-radius: 4px; padding: 2px 14px; font-weight: bold; }"
        )
        self.generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.generate_btn)
        btn_layout.addStretch()
        left_layout.addLayout(btn_layout)

        # ---- 结果显示 ----
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)
        result_layout.setContentsMargins(6, 4, 6, 4)
        result_layout.setSpacing(4)
        self.result_hex = QTextEdit()
        self.result_hex.setReadOnly(True)
        self.result_hex.setMaximumHeight(36)
        self.result_hex.setFont(QFont("Consolas", 10))
        result_layout.addWidget(self.result_hex)
        left_layout.addWidget(result_group)

        # ---- 串口发送按钮 ----
        serial_btn_layout = QHBoxLayout()
        serial_btn_layout.setSpacing(6)
        self.send_serial_btn = QPushButton("发送到串口")
        self.send_serial_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "border-radius: 4px; padding: 2px 12px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.send_serial_btn.clicked.connect(self._on_send_to_serial)
        serial_btn_layout.addWidget(self.send_serial_btn)

        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.setStyleSheet(
            "QPushButton { padding: 2px 12px; }"
        )
        self.clear_log_btn.clicked.connect(self._on_clear_serial_log)
        serial_btn_layout.addWidget(self.clear_log_btn)
        serial_btn_layout.addStretch()
        left_layout.addLayout(serial_btn_layout)

        # ---- 串口日志 ----
        log_group = QGroupBox("串口日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 4, 6, 4)
        log_layout.setSpacing(4)
        self.serial_log = QTextEdit()
        self.serial_log.setReadOnly(True)
        self.serial_log.setMaximumHeight(120)
        self.serial_log.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.serial_log)
        left_layout.addWidget(log_group)

        splitter.addWidget(left_widget)

        # ================== 右侧面板（实时解析预览） ==================
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(6)

        preview_group = QGroupBox("实时解析预览")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 4, 6, 4)
        preview_layout.setSpacing(4)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(4)
        self.preview_table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        header = self.preview_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.preview_table.setColumnWidth(0, 130)
        self.preview_table.setColumnWidth(1, 100)
        self.preview_table.setColumnWidth(2, 100)
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().hide()
        table_font = QFont()
        table_font.setPointSize(7)
        self.preview_table.setFont(table_font)
        self.preview_table.verticalHeader().setDefaultSectionSize(10)

        preview_layout.addWidget(self.preview_table)
        right_layout.addWidget(preview_group, 1)

        # ---- 响应帧解析 ----
        resp_group = QGroupBox("响应帧解析")
        resp_layout = QVBoxLayout(resp_group)
        resp_layout.setContentsMargins(6, 4, 6, 4)
        resp_layout.setSpacing(4)

        self.response_table = QTableWidget()
        self.response_table.setColumnCount(4)
        self.response_table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        resp_header = self.response_table.horizontalHeader()
        resp_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        resp_header.setStretchLastSection(True)
        self.response_table.setColumnWidth(0, 130)
        self.response_table.setColumnWidth(1, 100)
        self.response_table.setColumnWidth(2, 100)
        self.response_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.response_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.response_table.setAlternatingRowColors(True)
        self.response_table.verticalHeader().hide()
        resp_font = QFont()
        resp_font.setPointSize(7)
        self.response_table.setFont(resp_font)
        self.response_table.verticalHeader().setDefaultSectionSize(10)

        resp_layout.addWidget(self.response_table)
        right_layout.addWidget(resp_group, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([700, 500])
        main_layout.addWidget(splitter)

        # ---- 连接固定控件的实时更新信号 ----
        self.src_addr_input.textChanged.connect(self._schedule_realtime_update)
        self.dst_addr_input.textChanged.connect(self._schedule_realtime_update)
        self.dir_combo.currentIndexChanged.connect(self._schedule_realtime_update)
        self.prm_combo.currentIndexChanged.connect(self._schedule_realtime_update)
        self.add_combo.currentIndexChanged.connect(self._schedule_realtime_update)

    # ------------------------------------------------------------------
    # 模式切换
    # ------------------------------------------------------------------
    def _on_mode_changed(self, state):
        sender = self.sender()
        if sender == self.mode_predefined_rb and self.mode_predefined_rb.isChecked():
            self.mode_custom_rb.setChecked(False)
            self._custom_mode = False
        elif sender == self.mode_custom_rb and self.mode_custom_rb.isChecked():
            self.mode_predefined_rb.setChecked(False)
            self._custom_mode = True
        else:
            # 确保至少选中一个
            if not self.mode_predefined_rb.isChecked() and not self.mode_custom_rb.isChecked():
                self.mode_predefined_rb.setChecked(True)
                self._custom_mode = False
        # 仅重新构建字段表单区（不清空模式切换控件本身）
        self._rebuild_field_form(self._current_di_key)

    # ------------------------------------------------------------------
    # DI 下拉框
    # ------------------------------------------------------------------
    def _populate_di_combo(self):
        self.di_combo.clear()
        self.di_combo.addItem("-- 请选择DI --", None)
        for di_key, schema in DI_FIELD_SCHEMA.items():
            direction = schema.get("direction", "both")
            # 组帧页面只显示下行命令（上行响应帧由解析功能处理）
            if direction != "down":
                continue
            name = schema.get("name", "未知")
            label = f"【下行】 {name}  ({di_key[0]:02X} {di_key[1]:02X} {di_key[2]:02X} {di_key[3]:02X})"
            self.di_combo.addItem(label, di_key)

    def _on_di_changed(self, index: int):
        di_key = self.di_combo.currentData()
        self._current_di_key = di_key
        self.cmd_help_btn.setEnabled(di_key is not None)
        self._rebuild_form(di_key)

    def _on_cmd_help_clicked(self):
        """显示命令说明弹窗"""
        if not self._current_di_key:
            return
        schema = DI_FIELD_SCHEMA.get(self._current_di_key)
        if not schema:
            return
        doc = schema.get("doc", "暂无说明")
        name = schema.get("name", "未知命令")

        dialog = QDialog(self)
        dialog.setWindowTitle(f"命令说明 - {name}")
        dialog.setMinimumSize(520, 360)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(doc)
        text_edit.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(text_edit, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setMinimumWidth(80)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._help_dialog = dialog
        dialog.show()

    # ------------------------------------------------------------------
    # 动态表单
    # ------------------------------------------------------------------
    def _rebuild_form(self, di_key: Tuple[int, int, int, int]):
        # 清空旧表单
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_widgets.clear()

        if not di_key:
            self.mode_group.setVisible(True)
            return

        schema = DI_FIELD_SCHEMA.get(di_key)
        if not schema:
            self.mode_group.setVisible(True)
            return

        fields = schema.get("fields")
        if fields is not None and len(fields) == 0:
            # 无数据单元：隐藏模式切换，显示提示
            self.mode_group.setVisible(False)
            self._custom_mode = False
            hint = QLabel("<b>该命令无数据单元，无需添加用户数据</b>")
            hint.setStyleSheet("color: #2196F3; font-size: 13px; padding: 20px;")
            hint.setAlignment(Qt.AlignCenter)
            self._form_layout.addWidget(hint)
            self._schedule_realtime_update()
            return

        # 有数据单元：显示模式切换
        self.mode_group.setVisible(True)

        # 如果没有预定义字段，自动切换到自定义模式
        has_predefined = bool(fields)
        if not has_predefined:
            self.mode_custom_rb.setChecked(True)
            self.mode_predefined_rb.setChecked(False)
            self._custom_mode = True
        elif not self._custom_mode:
            self.mode_predefined_rb.setChecked(True)
            self.mode_custom_rb.setChecked(False)

        self._rebuild_field_form(di_key)

    def _rebuild_field_form(self, di_key: Tuple[int, int, int, int]):
        """仅重建字段表单区（模式切换时调用，不清空模式控件）"""
        # 清空旧表单（保留模式切换控件，因为它们不在 _form_layout 中）
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_widgets.clear()

        if not di_key:
            return

        schema = DI_FIELD_SCHEMA.get(di_key)
        if not schema:
            return

        fields = schema.get("fields")
        if fields is not None and len(fields) == 0:
            return

        if self._custom_mode:
            self._build_custom_template_ui()
            self._connect_template_signals()
        else:
            for field in schema.get("fields", []):
                widget = self._create_field_widget(field)
                if widget:
                    self._form_layout.addWidget(widget)
            self._connect_field_signals()
        self._schedule_realtime_update()

    # ------------------------------------------------------------------
    # 自定义字段模板 UI（参考图2）
    # ------------------------------------------------------------------
    def _build_custom_template_ui(self):
        # ---- 模板表格 ----
        table_group = QGroupBox("字段模板定义（参考协议文档填写）")
        table_layout = QVBoxLayout(table_group)
        table_layout.setSpacing(4)
        table_layout.setContentsMargins(8, 8, 8, 8)

        # 说明标签
        hint = QLabel("添加字段：定义名称、长度、类型、字节序，并在右侧填写字段值。组帧时按顺序打包。")
        hint.setStyleSheet("color: #666; font-size: 11px;")
        table_layout.addWidget(hint)

        self.template_table = QTableWidget()
        self.template_table.setColumnCount(7)
        self.template_table.setHorizontalHeaderLabels([
            "序号", "名称", "长度(字节)", "数据类型", "字节序", "显示进制", "字段值填充"
        ])
        header = self.template_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setFixedHeight(22)
        self.template_table.setColumnWidth(0, 45)
        self.template_table.setColumnWidth(1, 120)
        self.template_table.setColumnWidth(2, 70)
        self.template_table.setColumnWidth(3, 90)
        self.template_table.setColumnWidth(4, 70)
        self.template_table.setColumnWidth(5, 70)
        self.template_table.setColumnWidth(6, 160)
        self.template_table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
        self.template_table.setAlternatingRowColors(True)
        # 紧凑行高，隐藏垂直表头（序号列已自带行号）
        self.template_table.verticalHeader().setVisible(False)
        self.template_table.verticalHeader().setDefaultSectionSize(20)
        self.template_table.setStyleSheet("QTableWidget::item { padding: 1px 3px; } QComboBox { min-height: 18px; max-height: 22px; padding: 1px 4px; } QLineEdit { min-height: 18px; max-height: 22px; padding: 1px 4px; }")
        self.template_table.setMinimumHeight(140)
        table_layout.addWidget(self.template_table, 1)

        # 模板操作按钮
        tpl_btn_layout = QHBoxLayout()
        tpl_btn_layout.setSpacing(6)
        add_row_btn = QPushButton("添加字段")
        add_row_btn.setStyleSheet("QPushButton { padding: 2px 10px; }")
        add_row_btn.clicked.connect(self._add_template_row)
        del_row_btn = QPushButton("删除选中字段")
        del_row_btn.setStyleSheet("QPushButton { padding: 2px 10px; }")
        del_row_btn.clicked.connect(self._del_template_row)
        load_tpl_btn = QPushButton("加载默认模板")
        load_tpl_btn.setStyleSheet("QPushButton { padding: 2px 10px; }")
        load_tpl_btn.clicked.connect(self._load_default_template)
        tpl_btn_layout.addWidget(add_row_btn)
        tpl_btn_layout.addWidget(del_row_btn)
        tpl_btn_layout.addWidget(load_tpl_btn)
        tpl_btn_layout.addStretch()
        table_layout.addLayout(tpl_btn_layout)

        self._form_layout.addWidget(table_group, 1)

        # 初始化默认模板（如果空）
        if not self._custom_templates:
            self._load_default_template()
        else:
            self._refresh_template_table()

    def _load_default_template(self):
        """加载默认的通用字段模板"""
        self._custom_templates = [
            CustomFieldTemplate("用户数据", 1, "bytes", "big", "hex", False)
        ]
        self._refresh_template_table()

    def _refresh_template_table(self):
        """刷新模板表格显示"""
        self.template_table.setRowCount(len(self._custom_templates))
        for row, tpl in enumerate(self._custom_templates):
            self.template_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.template_table.setItem(row, 1, QTableWidgetItem(tpl.name))
            self.template_table.setItem(row, 2, QTableWidgetItem(str(tpl.length)))

            type_combo = QComboBox()
            type_combo.addItems(["uint8", "uint16", "uint32", "bytes", "checksum"])
            type_combo.setCurrentText(tpl.ftype)
            type_combo.setFixedHeight(20)
            self.template_table.setCellWidget(row, 3, type_combo)

            endian_combo = QComboBox()
            endian_combo.addItems(["big", "little"])
            endian_combo.setCurrentText(tpl.endian)
            endian_combo.setFixedHeight(20)
            self.template_table.setCellWidget(row, 4, endian_combo)

            display_combo = QComboBox()
            display_combo.addItems(["hex", "dec"])
            display_combo.setCurrentText(tpl.display)
            display_combo.setFixedHeight(20)
            self.template_table.setCellWidget(row, 5, display_combo)

            # 字段值输入列
            if tpl.ftype == "checksum":
                cs_label = QLabel("自动计算")
                cs_label.setStyleSheet("color: #2196F3; font-size: 11px;")
                cs_label.setFixedHeight(20)
                cs_label.setAlignment(Qt.AlignCenter)
                self.template_table.setCellWidget(row, 6, cs_label)
            else:
                val_edit = QLineEdit()
                val_edit.setFixedHeight(20)
                if tpl.display == "hex":
                    val_edit.setPlaceholderText("hex")
                else:
                    val_edit.setPlaceholderText("decimal")
                self.template_table.setCellWidget(row, 6, val_edit)
        self._connect_template_signals()
        self._schedule_realtime_update()

    def _add_template_row(self):
        """添加一行模板字段"""
        self._sync_templates_from_table()
        self._custom_templates.append(CustomFieldTemplate("新字段", 1, "bytes", "big", "hex", False))
        self._refresh_template_table()

    def _del_template_row(self):
        """删除选中的模板字段"""
        row = self.template_table.currentRow()
        if row >= 0 and row < len(self._custom_templates):
            self._sync_templates_from_table()
            del self._custom_templates[row]
            self._refresh_template_table()

    def _sync_templates_from_table(self):
        """从表格同步模板数据到内存"""
        new_templates = []
        for row in range(self.template_table.rowCount()):
            name_item = self.template_table.item(row, 1)
            len_item = self.template_table.item(row, 2)
            type_combo = self.template_table.cellWidget(row, 3)
            endian_combo = self.template_table.cellWidget(row, 4)
            display_combo = self.template_table.cellWidget(row, 5)

            name = name_item.text() if name_item else f"字段{row+1}"
            try:
                length = int(len_item.text()) if len_item else 1
            except ValueError:
                length = 1
            ftype = type_combo.currentText() if type_combo else "bytes"
            endian = endian_combo.currentText() if endian_combo else "big"
            display = display_combo.currentText() if display_combo else "hex"

            new_templates.append(CustomFieldTemplate(name, length, ftype, endian, display, False))
        self._custom_templates = new_templates

    # ------------------------------------------------------------------
    # 预定义字段控件
    # ------------------------------------------------------------------
    def _create_field_widget(self, field: Dict[str, Any]) -> QWidget:
        name = field["name"]
        ftype = field["type"]
        desc = field.get("description", "")
        default = field.get("default")
        optional = field.get("optional", False)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)

        label_text = name
        if desc:
            label_text += f"  [{desc}]"
        label = QLabel(label_text)
        label.setMinimumWidth(180)
        label.setToolTip(desc)
        layout.addWidget(label)

        if optional:
            cb = QCheckBox("启用")
            cb.setChecked(True)
            layout.addWidget(cb)
            self._field_widgets[name] = {"checkbox": cb, "widget": None}
        else:
            self._field_widgets[name] = {"widget": None}

        if ftype in ("uint8", "uint16", "uint32"):
            edit = QLineEdit()
            if default is not None:
                edit.setText(str(default))
            layout.addWidget(edit)
            self._field_widgets[name]["widget"] = edit

        elif ftype == "bytes":
            edit = QLineEdit()
            if default is not None:
                edit.setText(str(default))
            if field.get("reverse"):
                edit.setPlaceholderText("正常顺序hex，自动反转")
            layout.addWidget(edit)
            self._field_widgets[name]["widget"] = edit

        elif ftype == "enum":
            combo = QComboBox()
            enum_map = field.get("enum_map", {})
            for val, text in enum_map.items():
                combo.addItem(f"{text}  (0x{val:02X})", val)
            if default is not None:
                idx = combo.findData(default)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            layout.addWidget(combo)
            self._field_widgets[name]["widget"] = combo

        elif ftype == "list":
            list_widget = self._create_list_widget(field)
            layout.addWidget(list_widget, 1)
            self._field_widgets[name]["widget"] = list_widget

        else:
            edit = QLineEdit()
            if default is not None:
                edit.setText(str(default))
            layout.addWidget(edit)
            self._field_widgets[name]["widget"] = edit

        layout.addStretch()
        return container

    def _create_list_widget(self, field: Dict[str, Any]) -> QWidget:
        item_fields = field["item_fields"]
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel(f"<b>{field['name']}</b>")
        layout.addWidget(header)

        items_widget = QWidget()
        items_layout = QVBoxLayout(items_widget)
        items_layout.setAlignment(Qt.AlignTop)
        layout.addWidget(items_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加")
        del_btn = QPushButton("删除最后一项")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        container._items_layout = items_layout
        container._items: List[Tuple[QWidget, Dict[str, Any]]] = []
        container._item_fields = item_fields

        def add_item():
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(2, 2, 2, 2)
            item_widgets: Dict[str, Any] = {}
            for item_field in item_fields:
                item_name = item_field["name"]
                item_type = item_field["type"]
                lbl = QLabel(item_name)
                lbl.setStyleSheet("font-size: 11px; color: #555;")
                row_layout.addWidget(lbl)
                if item_type == "bytes":
                    edit = QLineEdit()
                    dft = item_field.get("default", "")
                    edit.setText(str(dft))
                    if item_field.get("reverse"):
                        edit.setPlaceholderText("hex, 自动反转")
                    edit.textChanged.connect(self._schedule_realtime_update)
                    row_layout.addWidget(edit)
                    item_widgets[item_name] = edit
                elif item_type in ("uint8", "uint16", "uint32"):
                    edit = QLineEdit()
                    dft = item_field.get("default", 0)
                    edit.setText(str(dft))
                    edit.textChanged.connect(self._schedule_realtime_update)
                    row_layout.addWidget(edit)
                    item_widgets[item_name] = edit
                elif item_type == "enum":
                    combo = QComboBox()
                    for val, text in item_field.get("enum_map", {}).items():
                        combo.addItem(f"{text} (0x{val:02X})", val)
                    dft = item_field.get("default")
                    if dft is not None:
                        idx = combo.findData(dft)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                    combo.currentIndexChanged.connect(self._schedule_realtime_update)
                    row_layout.addWidget(combo)
                    item_widgets[item_name] = combo
                else:
                    edit = QLineEdit()
                    edit.textChanged.connect(self._schedule_realtime_update)
                    row_layout.addWidget(edit)
                    item_widgets[item_name] = edit
            row_layout.addStretch()
            items_layout.addWidget(row_widget)
            container._items.append((row_widget, item_widgets))
            self._schedule_realtime_update()

        def del_item():
            if container._items:
                row_widget, _ = container._items.pop()
                row_widget.deleteLater()

        add_btn.clicked.connect(add_item)
        del_btn.clicked.connect(del_item)
        add_item()
        return container

    # ------------------------------------------------------------------
    # 收集字段值并组帧
    # ------------------------------------------------------------------
    def _collect_values(self) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        if not self._current_di_key:
            return values

        if self._custom_mode:
            self._sync_templates_from_table()
            for row, tpl in enumerate(self._custom_templates):
                if tpl.ftype == "checksum":
                    continue
                val_widget = self.template_table.cellWidget(row, 6)
                if not isinstance(val_widget, QLineEdit):
                    continue
                text = val_widget.text().strip()
                if tpl.ftype in ("uint8", "uint16", "uint32"):
                    if tpl.display == "hex":
                        values[tpl.name] = int(text, 16) if text else 0
                    else:
                        values[tpl.name] = int(text, 10) if text else 0
                else:
                    values[tpl.name] = text
        else:
            schema = DI_FIELD_SCHEMA.get(self._current_di_key, {})
            for field in schema.get("fields", []):
                name = field["name"]
                widget_info = self._field_widgets.get(name)
                if not widget_info:
                    continue
                if "checkbox" in widget_info:
                    if not widget_info["checkbox"].isChecked():
                        continue
                widget = widget_info["widget"]
                ftype = field["type"]

                if ftype in ("uint8", "uint16", "uint32"):
                    text = widget.text().strip()
                    values[name] = int(text, 0) if text else 0
                elif ftype == "bytes":
                    values[name] = widget.text().strip()
                elif ftype == "enum":
                    values[name] = widget.currentData()
                elif ftype == "list":
                    items = []
                    for _, item_widgets in widget._items:
                        item_values: Dict[str, Any] = {}
                        for item_name, item_widget in item_widgets.items():
                            if isinstance(item_widget, QComboBox):
                                item_values[item_name] = item_widget.currentData()
                            else:
                                item_values[item_name] = item_widget.text().strip()
                        items.append(item_values)
                    values[name] = items
                else:
                    values[name] = widget.text().strip()

        return values

    def _generate_custom_data(self) -> bytes:
        """根据自定义模板生成用户数据区字节"""
        import struct
        self._sync_templates_from_table()
        data = b""
        checksum_idx = -1

        for row, tpl in enumerate(self._custom_templates):
            if tpl.ftype == "checksum":
                checksum_idx = row
                data += b"\x00" * tpl.length  # 占位，后面回填
                continue

            val_widget = self.template_table.cellWidget(row, 6)
            if isinstance(val_widget, QLineEdit):
                text = val_widget.text().strip().replace(" ", "")
            else:
                text = ""

            if tpl.ftype == "bytes":
                if text:
                    try:
                        raw = bytes.fromhex(text)
                    except ValueError:
                        raw = b""
                else:
                    raw = b""
                if len(raw) < tpl.length:
                    raw = raw + b"\x00" * (tpl.length - len(raw))
                elif len(raw) > tpl.length:
                    raw = raw[:tpl.length]
            elif tpl.ftype in ("uint8", "uint16", "uint32"):
                try:
                    if tpl.display == "hex":
                        val = int(text, 16) if text else 0
                    else:
                        val = int(text, 10) if text else 0
                except ValueError:
                    val = 0
                if tpl.ftype == "uint8":
                    raw = struct.pack("B", val & 0xFF)
                elif tpl.ftype == "uint16":
                    if tpl.endian == "little":
                        raw = struct.pack("<H", val & 0xFFFF)
                    else:
                        raw = struct.pack(">H", val & 0xFFFF)
                else:  # uint32
                    if tpl.endian == "little":
                        raw = struct.pack("<I", val & 0xFFFFFFFF)
                    else:
                        raw = struct.pack(">I", val & 0xFFFFFFFF)
            else:
                raw = b"\x00" * tpl.length

            data += raw

        # 回填校验和
        if checksum_idx >= 0:
            cs = sum(data) & 0xFF
            # 校验和字段在data中的偏移量
            offset = 0
            for i, tpl in enumerate(self._custom_templates):
                if i == checksum_idx:
                    data = data[:offset] + struct.pack("B", cs) + data[offset+1:]
                    break
                offset += tpl.length

        return data

    # ------------------------------------------------------------------
    # 实时解析预览
    # ------------------------------------------------------------------
    def _schedule_realtime_update(self):
        """调度实时更新（200ms debounce）"""
        if self._update_timer is not None:
            self._update_timer.stop()
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._do_realtime_update)
        self._update_timer.start(200)

    def _do_realtime_update(self):
        """执行实时组帧与解析"""
        if not self._current_di_key:
            self.preview_table.setRowCount(0)
            return

        src_text = self.src_addr_input.text().strip().replace(" ", "")
        dst_text = self.dst_addr_input.text().strip().replace(" ", "")
        if len(src_text) != 12 or len(dst_text) != 12:
            self.preview_table.setRowCount(0)
            return
        try:
            src_addr = bytes.fromhex(src_text)
            dst_addr = bytes.fromhex(dst_text)
        except ValueError:
            self.preview_table.setRowCount(0)
            return

        try:
            di_key = self._current_di_key
            dir_flag = self.dir_combo.currentData()
            prm = self.prm_combo.currentData()
            add_flag = self.add_combo.currentData()

            if self._custom_mode:
                data = self._generate_custom_data()
                di3, di2, di1, di0 = di_key
                frame = self.generator._build_frame(
                    di3, di2, di1, di0,
                    src_addr=src_addr, dst_addr=dst_addr, data=data,
                    dir_flag=dir_flag, prm=prm, add_flag=add_flag
                )
            else:
                field_values = self._collect_values()
                frame = self.generator.generate_frame(
                    di_key, field_values,
                    src_addr=src_addr, dst_addr=dst_addr,
                    dir_flag=dir_flag, prm=prm, add_flag=add_flag
                )

            # 解析帧
            table_data = self.parser.parse_to_table(frame)
            self._populate_preview_table(table_data)

            # 同时更新底部结果hex显示
            hex_str = frame.hex().upper()
            formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
            self.result_hex.setText(formatted)
        except Exception:
            # 实时更新失败静默处理，不清空表格以免闪烁
            pass

    def _populate_preview_table(self, table_data: list):
        """填充实时预览表格"""
        self.preview_table.setRowCount(0)
        for row, item in enumerate(table_data):
            field_name = item[0]
            raw_value = item[1]
            parsed_value = item[2]
            comment = item[3]
            self.preview_table.insertRow(row)
            self.preview_table.setItem(row, 0, QTableWidgetItem(str(field_name)))
            self.preview_table.setItem(row, 1, QTableWidgetItem(str(raw_value)))
            self.preview_table.setItem(row, 2, QTableWidgetItem(str(parsed_value)))
            self.preview_table.setItem(row, 3, QTableWidgetItem(str(comment)))

    def _connect_field_signals(self):
        """连接预定义字段widget的实时更新信号"""
        for widget_info in self._field_widgets.values():
            widget = widget_info.get("widget")
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._schedule_realtime_update)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._schedule_realtime_update)
            elif widget is not None and hasattr(widget, '_items'):
                # list widget: connect add/del buttons indirectly via _schedule
                # 子字段的lineedits/combos在add_item时已创建，这里无法提前连接
                # 因此list类型实时更新依赖用户点击生成按钮，或者我们在add_item里连接
                pass
            cb = widget_info.get("checkbox")
            if isinstance(cb, QCheckBox):
                cb.stateChanged.connect(self._schedule_realtime_update)

    def _connect_template_signals(self):
        """连接自定义模板表格的实时更新信号"""
        if not hasattr(self, 'template_table'):
            return
        self.template_table.itemChanged.connect(self._schedule_realtime_update)
        for row in range(self.template_table.rowCount()):
            for col in (3, 4, 5):
                cw = self.template_table.cellWidget(row, col)
                if isinstance(cw, QComboBox):
                    cw.currentIndexChanged.connect(self._schedule_realtime_update)
            cw6 = self.template_table.cellWidget(row, 6)
            if isinstance(cw6, QLineEdit):
                cw6.textChanged.connect(self._schedule_realtime_update)

    def _on_generate(self):
        if not self._current_di_key:
            QMessageBox.warning(self, "警告", "请先选择一个DI命令")
            return

        src_text = self.src_addr_input.text().strip().replace(" ", "")
        dst_text = self.dst_addr_input.text().strip().replace(" ", "")
        if len(src_text) != 12 or len(dst_text) != 12:
            QMessageBox.warning(self, "警告", "源地址和目的地址必须为12位十六进制字符（6字节）")
            return
        try:
            src_addr = bytes.fromhex(src_text)
            dst_addr = bytes.fromhex(dst_text)
        except ValueError:
            QMessageBox.warning(self, "警告", "地址格式错误，请输入有效的十六进制字符串")
            return

        try:
            di_key = self._current_di_key
            dir_flag = self.dir_combo.currentData()
            prm = self.prm_combo.currentData()
            add_flag = self.add_combo.currentData()

            if self._custom_mode:
                data = self._generate_custom_data()
                di3, di2, di1, di0 = di_key
                frame = self.generator._build_frame(
                    di3, di2, di1, di0,
                    src_addr=src_addr, dst_addr=dst_addr, data=data,
                    dir_flag=dir_flag, prm=prm, add_flag=add_flag
                )
            else:
                field_values = self._collect_values()
                frame = self.generator.generate_frame(
                    di_key, field_values,
                    src_addr=src_addr, dst_addr=dst_addr,
                    dir_flag=dir_flag, prm=prm, add_flag=add_flag
                )

            hex_str = frame.hex().upper()
            formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
            self.result_hex.setText(formatted)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"组帧失败：{str(e)}")

    # ------------------------------------------------------------------
    # 串口功能
    # ------------------------------------------------------------------
    def set_serial_worker(self, worker):
        """设置串口工作线程实例"""
        self.serial_worker = worker
        if worker:
            worker.log_message.connect(self._on_serial_log)
            worker.frame_received.connect(self._on_serial_frame_received)
            worker.connection_changed.connect(self._update_send_button_state)

    def _update_send_button_state(self, connected: bool):
        """根据串口连接状态更新发送按钮"""
        self.send_serial_btn.setEnabled(connected)

    def _on_send_to_serial(self):
        """将当前生成的帧发送到串口"""
        if not self.serial_worker or not self.serial_worker.is_open():
            QMessageBox.warning(self, "警告", "串口未打开，请先打开串口")
            return
        hex_text = self.result_hex.toPlainText().strip()
        if not hex_text:
            QMessageBox.warning(self, "警告", "当前没有可发送的帧，请先生成帧")
            return
        self.serial_worker.send_hex_string(hex_text)

    def _on_clear_serial_log(self):
        """清空串口日志"""
        self.serial_log.clear()

    def _on_serial_log(self, msg: str):
        """串口日志消息回调"""
        self.serial_log.append(msg)
        # 自动滚动到底部
        scrollbar = self.serial_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_serial_frame_received(self, frame: bytes):
        """收到串口帧后的解析与显示"""
        try:
            table_data = self.parser.parse_to_table(frame)
            # 填充响应帧解析表格
            self._populate_response_table(table_data)
            # 在日志中追加解析摘要
            summary_parts = []
            for item in table_data:
                field_name = item[0].strip()
                if field_name in ("应用功能码 (AFN)", "数据标识 (DI)", "传输方向"):
                    parsed = str(item[2]) if item[2] else str(item[3])
                    summary_parts.append(f"{field_name}: {parsed}")
            if summary_parts:
                self.serial_log.append(f"[解析] {' | '.join(summary_parts)}")
            else:
                self.serial_log.append("[解析] 帧结构识别成功")
        except Exception as e:
            self.serial_log.append(f"[解析失败] {e}")

    def _populate_response_table(self, table_data: list):
        """填充响应帧解析表格"""
        self.response_table.setRowCount(0)
        for row, item in enumerate(table_data):
            field_name = item[0]
            raw_value = item[1]
            parsed_value = item[2]
            comment = item[3]
            self.response_table.insertRow(row)
            self.response_table.setItem(row, 0, QTableWidgetItem(str(field_name)))
            self.response_table.setItem(row, 1, QTableWidgetItem(str(raw_value)))
            self.response_table.setItem(row, 2, QTableWidgetItem(str(parsed_value)))
            self.response_table.setItem(row, 3, QTableWidgetItem(str(comment)))

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def reset(self):
        self.di_combo.setCurrentIndex(0)
        self.src_addr_input.setText("000000000000")
        self.dst_addr_input.setText("000000000000")
        self.dir_combo.setCurrentIndex(0)
        self.prm_combo.setCurrentIndex(0)
        self.add_combo.setCurrentIndex(0)
        self.result_hex.clear()
        if hasattr(self, 'preview_table'):
            self.preview_table.setRowCount(0)
        if hasattr(self, 'response_table'):
            self.response_table.setRowCount(0)
        self._custom_templates = []
        self._custom_mode = False
        self.mode_predefined_rb.setChecked(True)
        self.mode_custom_rb.setChecked(False)
        self._rebuild_form(None)
