"""南网协议组帧Widget

提供基于DI_FIELD_SCHEMA的动态表单和通用组帧界面，
支持预定义schema和自定义字段模板两种模式。
可嵌入main_gui.py作为独立标签页使用。
"""

from typing import Dict, Any, List, Tuple
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QGroupBox, QScrollArea, QCheckBox, QMessageBox, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QDialog
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeyEvent

from send_frame_lib import ProtocolFrameGenerator
from frame_generator_schema import DI_FIELD_SCHEMA
from protocol_parser import ProtocolFrameParser
from gdw_send_frame_lib import GDWFrameGenerator
from gdw_frame_generator_schema import GDW_AFNFN_SCHEMA
from gdw10376_parser import GDW10376Parser
from preset_buttons import PresetButtonManager, AddPresetDialog
from gui_utils import apply_chinese_context_menus, setup_chinese_context_menu


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

    # 当帧被添加到预设时发出（protocol, frame_hex, config_snapshot）
    preset_added = Signal(str, str, dict)
    # 当帧被添加到测试方案时发出（name, frame_hex）
    test_plan_added = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 协议模式: "south"=南网, "gdw"=国网
        self.protocol_mode = "south"
        self.generator = ProtocolFrameGenerator()
        self.parser = ProtocolFrameParser()
        self.gdw_generator = GDWFrameGenerator()
        self.gdw_parser = GDW10376Parser()
        self._field_widgets: Dict[str, Dict[str, Any]] = {}
        self._current_di_key: Tuple[int, int, int, int] = None
        self._current_afn_fn: Tuple[int, int] = None
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
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # ================== 左侧面板 ==================
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(4)

        # ---- 命令选择区（南网DI / 国网AFN+Fn） ----
        self.cmd_select_group = QGroupBox("DI 选择")
        cmd_layout = QHBoxLayout(self.cmd_select_group)
        cmd_layout.setContentsMargins(6, 4, 6, 4)
        cmd_layout.setSpacing(6)
        cmd_layout.addWidget(QLabel("选择命令："))

        # 南网DI选择
        self.di_combo = QComboBox()
        self.di_combo.setMinimumWidth(360)
        self.di_combo.setEditable(True)
        self.di_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.di_combo.completer().setCompletionMode(self.di_combo.completer().CompletionMode.PopupCompletion)
        self.di_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.di_combo.completer().popup().setStyleSheet(
            "background-color: #ffffff; color: #000000; selection-background-color: #2196F3; selection-color: #ffffff;"
        )
        self._populate_di_combo()
        self.di_combo.currentIndexChanged.connect(self._on_di_changed)
        cmd_layout.addWidget(self.di_combo)

        # 国网AFN+Fn选择（默认隐藏）
        self.afn_fn_combo = QComboBox()
        self.afn_fn_combo.setMinimumWidth(360)
        self.afn_fn_combo.setEditable(True)
        self.afn_fn_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.afn_fn_combo.completer().setCompletionMode(self.afn_fn_combo.completer().CompletionMode.PopupCompletion)
        self.afn_fn_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.afn_fn_combo.completer().popup().setStyleSheet(
            "background-color: #ffffff; color: #000000; selection-background-color: #2196F3; selection-color: #ffffff;"
        )
        self._populate_afn_fn_combo()
        self.afn_fn_combo.currentIndexChanged.connect(self._on_afn_fn_changed)
        self.afn_fn_combo.setVisible(False)
        cmd_layout.addWidget(self.afn_fn_combo)

        self.cmd_help_btn = QPushButton("命令说明")
        self.cmd_help_btn.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; "
            "border-radius: 3px; padding: 2px 10px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.cmd_help_btn.setEnabled(False)
        self.cmd_help_btn.clicked.connect(self._on_cmd_help_clicked)
        cmd_layout.addWidget(self.cmd_help_btn)
        cmd_layout.addStretch()
        left_layout.addWidget(self.cmd_select_group)

        # ---- 帧配置（南网模式） ----
        self.south_config_group = QGroupBox("帧配置")
        south_config_layout = QHBoxLayout(self.south_config_group)
        south_config_layout.setContentsMargins(6, 4, 6, 4)
        south_config_layout.setSpacing(6)

        south_config_layout.addWidget(QLabel("源地址:"))
        self.src_addr_input = QLineEdit("000000000000")
        self.src_addr_input.setMaxLength(12)
        south_config_layout.addWidget(self.src_addr_input)

        south_config_layout.addWidget(QLabel("目的地址:"))
        self.dst_addr_input = QLineEdit("000000000000")
        self.dst_addr_input.setMaxLength(12)
        south_config_layout.addWidget(self.dst_addr_input)

        south_config_layout.addWidget(QLabel("DIR:"))
        self.dir_combo = QComboBox()
        self.dir_combo.addItem("0-下行(集中器→模块)", 0)
        self.dir_combo.addItem("1-上行(模块→集中器)", 1)
        south_config_layout.addWidget(self.dir_combo)

        south_config_layout.addWidget(QLabel("PRM:"))
        self.prm_combo = QComboBox()
        self.prm_combo.addItem("0-从动站", 0)
        self.prm_combo.addItem("1-启动站", 1)
        south_config_layout.addWidget(self.prm_combo)

        south_config_layout.addWidget(QLabel("ADD:"))
        self.add_combo = QComboBox()
        self.add_combo.addItem("0-不带地址域", 0)
        self.add_combo.addItem("1-带地址域", 1)
        south_config_layout.addWidget(self.add_combo)

        south_config_layout.addStretch()
        left_layout.addWidget(self.south_config_group)

        # ---- 国网帧配置（信息域R + 地址域A，默认隐藏） ----
        self.gdw_config_group = QGroupBox("国网帧配置")
        gdw_config_layout = QVBoxLayout(self.gdw_config_group)
        gdw_config_layout.setContentsMargins(6, 4, 6, 4)
        gdw_config_layout.setSpacing(4)

        # 信息域R配置
        info_layout = QHBoxLayout()
        info_layout.setSpacing(6)
        info_layout.addWidget(QLabel("通信方式:"))
        self.gdw_comm_type = QComboBox()
        self.gdw_comm_type.addItem("0-保留", 0)
        self.gdw_comm_type.addItem("1-集中式路由载波", 1)
        self.gdw_comm_type.addItem("2-分布式路由载波", 2)
        self.gdw_comm_type.addItem("3-HPLC载波", 3)
        self.gdw_comm_type.addItem("4-双模HDC", 4)
        self.gdw_comm_type.addItem("10-微功率无线", 10)
        self.gdw_comm_type.addItem("20-以太网", 20)
        info_layout.addWidget(self.gdw_comm_type)

        info_layout.addWidget(QLabel("DIR:"))
        self.gdw_dir = QComboBox()
        self.gdw_dir.addItem("0-下行", 0)
        self.gdw_dir.addItem("1-上行", 1)
        info_layout.addWidget(self.gdw_dir)

        info_layout.addWidget(QLabel("PRM:"))
        self.gdw_prm = QComboBox()
        self.gdw_prm.addItem("1-启动站", 1)
        self.gdw_prm.addItem("0-从动站", 0)
        info_layout.addWidget(self.gdw_prm)

        info_layout.addWidget(QLabel("序列号:"))
        self.gdw_seq = QLineEdit("0")
        self.gdw_seq.setFixedWidth(40)
        info_layout.addWidget(self.gdw_seq)
        info_layout.addStretch()
        gdw_config_layout.addLayout(info_layout)

        # 信息域R详细配置
        info_detail_layout = QHBoxLayout()
        info_detail_layout.setSpacing(6)

        info_detail_layout.addWidget(QLabel("路由标识:"))
        self.gdw_route_flag = QComboBox()
        self.gdw_route_flag.addItem("0-带路由", 0)
        self.gdw_route_flag.addItem("1-不带路由", 1)
        info_detail_layout.addWidget(self.gdw_route_flag)

        info_detail_layout.addWidget(QLabel("通信模块标识:"))
        self.gdw_comm_module = QComboBox()
        self.gdw_comm_module.addItem("0-对主节点", 0)
        self.gdw_comm_module.addItem("1-对从节点", 1)
        self.gdw_comm_module.currentIndexChanged.connect(self._on_gdw_comm_module_changed)
        info_detail_layout.addWidget(self.gdw_comm_module)

        info_detail_layout.addWidget(QLabel("中继级别:"))
        self.gdw_relay_level = QComboBox()
        for i in range(16):
            self.gdw_relay_level.addItem(f"{i}", i)
        self.gdw_relay_level.currentIndexChanged.connect(self._on_gdw_relay_level_changed)
        info_detail_layout.addWidget(self.gdw_relay_level)

        info_detail_layout.addWidget(QLabel("信道标识:"))
        self.gdw_channel = QLineEdit("0")
        self.gdw_channel.setFixedWidth(30)
        info_detail_layout.addWidget(self.gdw_channel)

        info_detail_layout.addWidget(QLabel("应答字节数:"))
        self.gdw_resp_bytes = QLineEdit("0")
        self.gdw_resp_bytes.setFixedWidth(40)
        info_detail_layout.addWidget(self.gdw_resp_bytes)

        info_detail_layout.addStretch()
        gdw_config_layout.addLayout(info_detail_layout)

        # 地址域配置
        addr_layout = QHBoxLayout()
        addr_layout.setSpacing(6)
        addr_layout.addWidget(QLabel("源地址(A1):"))
        self.gdw_src_addr = QLineEdit("000000000000")
        self.gdw_src_addr.setMaxLength(12)
        addr_layout.addWidget(self.gdw_src_addr)

        addr_layout.addWidget(QLabel("目的地址(A3):"))
        self.gdw_dst_addr = QLineEdit("000000000000")
        self.gdw_dst_addr.setMaxLength(12)
        addr_layout.addWidget(self.gdw_dst_addr)
        addr_layout.addStretch()
        gdw_config_layout.addLayout(addr_layout)

        # 中继地址（动态）
        self.gdw_relay_container = QWidget()
        self.gdw_relay_layout = QHBoxLayout(self.gdw_relay_container)
        self.gdw_relay_layout.setContentsMargins(0, 0, 0, 0)
        self.gdw_relay_layout.setSpacing(6)
        self.gdw_relay_layout.addWidget(QLabel("中继地址:"))
        self.gdw_relay_inputs: List[QLineEdit] = []
        gdw_config_layout.addWidget(self.gdw_relay_container)
        self.gdw_relay_container.setVisible(False)

        self.gdw_config_group.setVisible(False)
        left_layout.addWidget(self.gdw_config_group)

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

        # ---- 串口发送按钮 + 添加到预设 ----
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

        self.add_preset_btn = QPushButton("添加到预设")
        self.add_preset_btn.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; "
            "border-radius: 4px; padding: 2px 12px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.add_preset_btn.clicked.connect(self._on_add_to_preset_clicked)
        serial_btn_layout.addWidget(self.add_preset_btn)

        self.add_test_plan_btn = QPushButton("添加到测试方案")
        self.add_test_plan_btn.setStyleSheet(
            "QPushButton { background-color: #9C27B0; color: white; "
            "border-radius: 4px; padding: 2px 12px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.add_test_plan_btn.clicked.connect(self._on_add_to_test_plan_clicked)
        serial_btn_layout.addWidget(self.add_test_plan_btn)

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
        self.serial_log.setContextMenuPolicy(Qt.CustomContextMenu)
        self.serial_log.customContextMenuRequested.connect(self._on_serial_log_context_menu)
        log_layout.addWidget(self.serial_log)
        left_layout.addWidget(log_group)

        splitter.addWidget(left_widget)

        # ================== 右侧面板（实时解析预览） ==================
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(4)

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

        # ---- 连接国网控件的实时更新信号 ----
        self.gdw_comm_type.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_dir.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_prm.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_seq.textChanged.connect(self._schedule_realtime_update)
        self.gdw_route_flag.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_comm_module.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_relay_level.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_channel.textChanged.connect(self._schedule_realtime_update)
        self.gdw_resp_bytes.textChanged.connect(self._schedule_realtime_update)
        self.gdw_src_addr.textChanged.connect(self._schedule_realtime_update)
        self.gdw_dst_addr.textChanged.connect(self._schedule_realtime_update)

        apply_chinese_context_menus(self)

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
        if self.protocol_mode == "south":
            self._rebuild_field_form(self._current_di_key)
        else:
            self._rebuild_gdw_field_form(self._current_afn_fn)

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

    def _populate_afn_fn_combo(self):
        """填充国网AFN+Fn下拉框"""
        self.afn_fn_combo.clear()
        self.afn_fn_combo.addItem("-- 请选择AFN+Fn --", None)
        for afn, fn, name in self.gdw_generator.get_supported_afn_fn():
            label = f"【下行】 {name}  (AFN={afn:02X}H Fn=F{fn})"
            self.afn_fn_combo.addItem(label, (afn, fn))

    def _on_di_changed(self, index: int):
        di_key = self.di_combo.currentData()
        self._current_di_key = di_key
        self.cmd_help_btn.setEnabled(di_key is not None)
        self._rebuild_form(di_key)

    def _on_afn_fn_changed(self, index: int):
        afn_fn = self.afn_fn_combo.currentData()
        self._current_afn_fn = afn_fn
        self.cmd_help_btn.setEnabled(afn_fn is not None)
        self._rebuild_gdw_form(afn_fn)

    def _on_cmd_help_clicked(self):
        """显示命令说明弹窗"""
        if self.protocol_mode == "south":
            if not self._current_di_key:
                return
            schema = DI_FIELD_SCHEMA.get(self._current_di_key)
            if not schema:
                return
            doc = schema.get("doc", "暂无说明")
            name = schema.get("name", "未知命令")
        else:
            if not self._current_afn_fn:
                return
            schema = GDW_AFNFN_SCHEMA.get(self._current_afn_fn)
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
        setup_chinese_context_menu(text_edit)
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

    def _rebuild_gdw_form(self, afn_fn: Tuple[int, int]):
        """重建国网模式表单"""
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_widgets.clear()

        if not afn_fn:
            self.mode_group.setVisible(True)
            return

        schema = GDW_AFNFN_SCHEMA.get(afn_fn)
        if not schema:
            self.mode_group.setVisible(True)
            return

        fields = schema.get("fields")
        if fields is not None and len(fields) == 0:
            self.mode_group.setVisible(False)
            self._custom_mode = False
            hint = QLabel("<b>该命令无数据单元，无需添加用户数据</b>")
            hint.setStyleSheet("color: #2196F3; font-size: 13px; padding: 20px;")
            hint.setAlignment(Qt.AlignCenter)
            self._form_layout.addWidget(hint)
            self._schedule_realtime_update()
            return

        self.mode_group.setVisible(True)
        has_predefined = bool(fields)
        if not has_predefined:
            self.mode_custom_rb.setChecked(True)
            self.mode_predefined_rb.setChecked(False)
            self._custom_mode = True
        elif not self._custom_mode:
            self.mode_predefined_rb.setChecked(True)
            self.mode_custom_rb.setChecked(False)

        self._rebuild_gdw_field_form(afn_fn)

    def _rebuild_gdw_field_form(self, afn_fn: Tuple[int, int]):
        """仅重建国网字段表单区"""
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_widgets.clear()

        if not afn_fn:
            return
        schema = GDW_AFNFN_SCHEMA.get(afn_fn)
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
        apply_chinese_context_menus(self._form_container)

    def _on_gdw_comm_module_changed(self, index: int):
        """国网通信模块标识改变：决定是否显示地址域"""
        # 地址域始终显示，但通信模块标识影响组帧时是否包含地址
        pass

    def _on_gdw_relay_level_changed(self, index: int):
        """国网中继级别改变：动态显示中继地址输入框"""
        level = self.gdw_relay_level.currentData()
        # 清除旧的中继输入框
        while self.gdw_relay_layout.count() > 1:
            item = self.gdw_relay_layout.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()
        self.gdw_relay_inputs.clear()

        if level > 0:
            self.gdw_relay_container.setVisible(True)
            for i in range(level):
                lbl = QLabel(f"A2-{i+1}:")
                edit = QLineEdit("000000000000")
                edit.setMaxLength(12)
                edit.setFixedWidth(100)
                edit.textChanged.connect(self._schedule_realtime_update)
                self.gdw_relay_layout.addWidget(lbl)
                self.gdw_relay_layout.addWidget(edit)
                self.gdw_relay_inputs.append(edit)
            self.gdw_relay_layout.addStretch()
            apply_chinese_context_menus(self.gdw_relay_container)
        else:
            self.gdw_relay_container.setVisible(False)

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
        apply_chinese_context_menus(self._form_container)

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
        apply_chinese_context_menus(self.template_table)

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

        if "sub_fields" in field:
            sub_container = QWidget()
            sub_layout = QHBoxLayout(sub_container)
            sub_layout.setContentsMargins(0, 0, 0, 0)
            sub_layout.setSpacing(4)
            sub_widgets: Dict[str, Any] = {}
            for sub in field["sub_fields"]:
                sub_name = sub["name"]
                sub_type = sub.get("type", "bytes")
                sub_default = sub.get("default")
                sub_desc = sub.get("description", "")
                sub_label = QLabel(sub_name)
                sub_label.setStyleSheet("font-size: 11px; color: #555;")
                sub_label.setToolTip(sub_desc)
                sub_layout.addWidget(sub_label)
                if sub_type == "enum":
                    combo = QComboBox()
                    for val, text in sub.get("enum_map", {}).items():
                        combo.addItem(f"{text} (0x{val:02X})", val)
                    if sub_default is not None:
                        idx = combo.findData(sub_default)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                    combo.currentIndexChanged.connect(self._schedule_realtime_update)
                    sub_layout.addWidget(combo)
                    sub_widgets[sub_name] = combo
                elif sub_type in ("uint8", "uint16", "uint32"):
                    edit = QLineEdit()
                    if sub_default is not None:
                        edit.setText(str(sub_default))
                    edit.setFixedWidth(50)
                    edit.textChanged.connect(self._schedule_realtime_update)
                    sub_layout.addWidget(edit)
                    sub_widgets[sub_name] = edit
                elif sub_type == "bytes":
                    edit = QLineEdit()
                    if sub_default is not None:
                        edit.setText(str(sub_default))
                    edit.textChanged.connect(self._schedule_realtime_update)
                    sub_layout.addWidget(edit)
                    sub_widgets[sub_name] = edit
            sub_layout.addStretch()
            layout.addWidget(sub_container)
            self._field_widgets[name]["widget"] = sub_container
            self._field_widgets[name]["sub_widgets"] = sub_widgets

        elif ftype in ("uint8", "uint16", "uint32"):
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
        if self.protocol_mode == "south":
            if not self._current_di_key:
                return values
        else:
            if not self._current_afn_fn:
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
            if self.protocol_mode == "south":
                schema = DI_FIELD_SCHEMA.get(self._current_di_key, {})
            else:
                schema = GDW_AFNFN_SCHEMA.get(self._current_afn_fn, {})
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

                if "sub_widgets" in widget_info:
                    # 收集子字段值
                    for sub_name, sub_widget in widget_info["sub_widgets"].items():
                        sub_field = next((s for s in field.get("sub_fields", []) if s["name"] == sub_name), None)
                        if not sub_field:
                            continue
                        sub_type = sub_field.get("type", "bytes")
                        if sub_type == "enum":
                            values[sub_name] = sub_widget.currentData()
                        elif sub_type in ("uint8", "uint16", "uint32"):
                            text = sub_widget.text().strip()
                            values[sub_name] = int(text, 0) if text else 0
                        elif sub_type == "bytes":
                            values[sub_name] = sub_widget.text().strip()
                    # 计算父字段值
                    if ftype in ("uint8", "enum"):
                        parent_val = 0
                        for sub in field.get("sub_fields", []):
                            sub_name = sub["name"]
                            sub_val = values.get(sub_name, sub.get("default", 0))
                            bit_width = sub.get("bit_width", 1)
                            bit_offset = sub.get("bit_offset", 0)
                            mask = (1 << bit_width) - 1
                            parent_val |= (int(sub_val) & mask) << bit_offset
                        values[name] = parent_val
                    elif ftype == "bytes":
                        parent_val = ""
                        for sub in field.get("sub_fields", []):
                            cond = sub.get("condition")
                            if cond:
                                ref_val = values.get(cond["field"])
                                if ref_val != cond["value"]:
                                    continue
                            sub_name = sub["name"]
                            sub_val = values.get(sub_name, sub.get("default", ""))
                            sub_type = sub.get("type", "bytes")
                            if sub_type in ("uint8", "enum"):
                                parent_val += f"{int(sub_val):02X}"
                            elif sub_type == "bytes":
                                parent_val += str(sub_val)
                        values[name] = parent_val

                elif ftype in ("uint8", "uint16", "uint32"):
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
        try:
            if self.protocol_mode == "south":
                self._do_realtime_update_south()
            else:
                self._do_realtime_update_gdw()
        except Exception:
            pass

    def _do_realtime_update_south(self):
        """南网实时组帧与解析"""
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

        table_data = self.parser.parse_to_table(frame)
        self._populate_preview_table(table_data)

        hex_str = frame.hex().upper()
        formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        self.result_hex.setText(formatted)

    def _do_realtime_update_gdw(self):
        """国网实时组帧与解析"""
        if not self._current_afn_fn:
            self.preview_table.setRowCount(0)
            return

        afn, fn = self._current_afn_fn
        try:
            seq = int(self.gdw_seq.text().strip()) & 0xFF
            channel = int(self.gdw_channel.text().strip()) & 0x0F
            resp_bytes = int(self.gdw_resp_bytes.text().strip()) & 0xFF
        except ValueError:
            self.preview_table.setRowCount(0)
            return

        info_config = {
            "dir": self.gdw_dir.currentData(),
            "prm": self.gdw_prm.currentData(),
            "通信方式": self.gdw_comm_type.currentData(),
            "路由标识": self.gdw_route_flag.currentData(),
            "附属节点标识": 0,
            "通信模块标识": self.gdw_comm_module.currentData(),
            "冲突检测": 0,
            "中继级别": self.gdw_relay_level.currentData(),
            "纠错编码标识": 0,
            "信道标识": channel,
            "预计应答字节数": resp_bytes,
            "通信速率": 0,
            "速率单位标识": 0,
            "报文序列号": seq,
        }

        src_addr = self.gdw_src_addr.text().strip()
        dst_addr = self.gdw_dst_addr.text().strip()
        relay_addrs = [edit.text().strip() for edit in self.gdw_relay_inputs]

        field_values = self._collect_values()

        frame = self.gdw_generator.generate_frame(
            afn, fn, field_values, info_config,
            src_addr=src_addr, dst_addr=dst_addr, relay_addrs=relay_addrs
        )

        table_data = self.gdw_parser.parse_to_table(frame)
        self._populate_preview_table(table_data)

        hex_str = frame.hex().upper()
        formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        self.result_hex.setText(formatted)

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
        try:
            if self.protocol_mode == "south":
                self._generate_south_frame()
            else:
                self._generate_gdw_frame()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"组帧失败：{str(e)}")

    def _generate_south_frame(self):
        """生成南网协议帧"""
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

    def _generate_gdw_frame(self):
        """生成国网协议帧"""
        if not self._current_afn_fn:
            QMessageBox.warning(self, "警告", "请先选择一个AFN+Fn命令")
            return

        afn, fn = self._current_afn_fn

        # 收集信息域配置
        try:
            seq = int(self.gdw_seq.text().strip()) & 0xFF
            channel = int(self.gdw_channel.text().strip()) & 0x0F
            resp_bytes = int(self.gdw_resp_bytes.text().strip()) & 0xFF
        except ValueError:
            QMessageBox.warning(self, "警告", "信息域配置值格式错误")
            return

        info_config = {
            "dir": self.gdw_dir.currentData(),
            "prm": self.gdw_prm.currentData(),
            "通信方式": self.gdw_comm_type.currentData(),
            "路由标识": self.gdw_route_flag.currentData(),
            "附属节点标识": 0,
            "通信模块标识": self.gdw_comm_module.currentData(),
            "冲突检测": 0,
            "中继级别": self.gdw_relay_level.currentData(),
            "纠错编码标识": 0,
            "信道标识": channel,
            "预计应答字节数": resp_bytes,
            "通信速率": 0,
            "速率单位标识": 0,
            "报文序列号": seq,
        }

        src_addr = self.gdw_src_addr.text().strip()
        dst_addr = self.gdw_dst_addr.text().strip()
        relay_addrs = [edit.text().strip() for edit in self.gdw_relay_inputs]

        field_values = self._collect_values()

        frame = self.gdw_generator.generate_frame(
            afn, fn, field_values, info_config,
            src_addr=src_addr, dst_addr=dst_addr, relay_addrs=relay_addrs
        )

        hex_str = frame.hex().upper()
        formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        self.result_hex.setText(formatted)

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

    def _on_add_to_preset_clicked(self):
        """将当前生成的帧添加到预设按钮"""
        frame_hex = self.result_hex.toPlainText().strip()
        if not frame_hex:
            QMessageBox.warning(self, "警告", "当前没有可添加的帧，请先生成帧")
            return

        dialog = AddPresetDialog(frame_hex, self.protocol_mode, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        result = dialog.get_result()
        if not result:
            return

        # 附加当前完整配置快照，方便恢复
        result["config"] = self.get_config_snapshot()

        if PresetButtonManager.add_command(self.protocol_mode, result):
            QMessageBox.information(
                self, "成功",
                f"已添加预设按钮：{result['button_name']}\n分组：{result['group_name']}"
            )
            self.preset_added.emit(self.protocol_mode, frame_hex, result["config"])
        else:
            QMessageBox.critical(self, "错误", "保存预设按钮失败")

    def _on_add_to_test_plan_clicked(self):
        """将当前生成的帧添加到测试方案"""
        frame_hex = self.result_hex.toPlainText().strip()
        if not frame_hex:
            QMessageBox.warning(self, "警告", "当前没有可添加的帧，请先生成帧")
            return
        # 尝试从当前DI/AFN+Fn获取中文名称
        name = ""
        if self.protocol_mode == "south" and self._current_di_key:
            schema = DI_FIELD_SCHEMA.get(self._current_di_key)
            if schema:
                name = schema.get("name", "")
            if not name:
                # 从combo文本解析：【下行】 中文名称  (DI3 DI2 DI1 DI0)
                text = self.di_combo.currentText()
                name = self._extract_name_from_label(text)
        elif self.protocol_mode == "gdw" and self._current_afn_fn:
            text = self.afn_fn_combo.currentText()
            name = self._extract_name_from_label(text)
        if not name:
            name = "测试项"
        self.test_plan_added.emit(name, frame_hex.replace(" ", ""))
        QMessageBox.information(self, "成功", f"已添加到测试方案：{name}")

    @staticmethod
    def _extract_name_from_label(label: str) -> str:
        """从combo标签中提取中文名称
        格式: 【下行】 中文名称  (DI3 DI2 DI1 DI0) 或 【下行】 中文名称  (AFN=XXH Fn=FY)
        """
        if not label or label.startswith("--"):
            return ""
        # 去掉 【下行】 前缀
        if label.startswith("【下行】"):
            label = label[4:]
        # 去掉 (DI码) 或 (AFN=... ) 后缀
        if "(" in label:
            label = label[:label.index("(")]
        return label.strip()

    def get_config_snapshot(self) -> Dict[str, Any]:
        """获取当前组帧页面的完整配置快照"""
        snapshot = {
            "protocol_mode": self.protocol_mode,
            "current_di_key": self._current_di_key,
            "current_afn_fn": self._current_afn_fn,
            "custom_mode": self._custom_mode,
            "south": {
                "src_addr": self.src_addr_input.text(),
                "dst_addr": self.dst_addr_input.text(),
                "dir": self.dir_combo.currentData(),
                "prm": self.prm_combo.currentData(),
                "add": self.add_combo.currentData(),
            },
            "gdw": {
                "comm_type": self.gdw_comm_type.currentData(),
                "dir": self.gdw_dir.currentData(),
                "prm": self.gdw_prm.currentData(),
                "seq": self.gdw_seq.text(),
                "route_flag": self.gdw_route_flag.currentData(),
                "comm_module": self.gdw_comm_module.currentData(),
                "relay_level": self.gdw_relay_level.currentData(),
                "channel": self.gdw_channel.text(),
                "resp_bytes": self.gdw_resp_bytes.text(),
                "src_addr": self.gdw_src_addr.text(),
                "dst_addr": self.gdw_dst_addr.text(),
                "relay_addrs": [e.text() for e in self.gdw_relay_inputs],
            },
        }

        # 收集字段值
        try:
            snapshot["field_values"] = self._collect_values()
        except Exception:
            snapshot["field_values"] = {}

        # 自定义模板
        if self._custom_mode:
            self._sync_templates_from_table()
            snapshot["custom_templates"] = [
                {
                    "name": t.name,
                    "length": t.length,
                    "ftype": t.ftype,
                    "endian": t.endian,
                    "display": t.display,
                    "reverse": t.reverse,
                }
                for t in self._custom_templates
            ]
        else:
            snapshot["custom_templates"] = []

        return snapshot

    def apply_config_snapshot(self, config: Dict[str, Any]):
        """从配置快照恢复组帧页面状态"""
        if not config:
            return

        # 恢复协议模式（由外部先调用 set_protocol_mode，这里只校验）
        mode = config.get("protocol_mode", self.protocol_mode)

        # 恢复南网配置
        south = config.get("south", {})
        if "src_addr" in south:
            self.src_addr_input.setText(south["src_addr"])
        if "dst_addr" in south:
            self.dst_addr_input.setText(south["dst_addr"])
        if "dir" in south:
            idx = self.dir_combo.findData(south["dir"])
            if idx >= 0:
                self.dir_combo.setCurrentIndex(idx)
        if "prm" in south:
            idx = self.prm_combo.findData(south["prm"])
            if idx >= 0:
                self.prm_combo.setCurrentIndex(idx)
        if "add" in south:
            idx = self.add_combo.findData(south["add"])
            if idx >= 0:
                self.add_combo.setCurrentIndex(idx)

        # 恢复国网配置
        gdw = config.get("gdw", {})
        if "comm_type" in gdw:
            idx = self.gdw_comm_type.findData(gdw["comm_type"])
            if idx >= 0:
                self.gdw_comm_type.setCurrentIndex(idx)
        if "dir" in gdw:
            idx = self.gdw_dir.findData(gdw["dir"])
            if idx >= 0:
                self.gdw_dir.setCurrentIndex(idx)
        if "prm" in gdw:
            idx = self.gdw_prm.findData(gdw["prm"])
            if idx >= 0:
                self.gdw_prm.setCurrentIndex(idx)
        if "seq" in gdw:
            self.gdw_seq.setText(str(gdw["seq"]))
        if "route_flag" in gdw:
            idx = self.gdw_route_flag.findData(gdw["route_flag"])
            if idx >= 0:
                self.gdw_route_flag.setCurrentIndex(idx)
        if "comm_module" in gdw:
            idx = self.gdw_comm_module.findData(gdw["comm_module"])
            if idx >= 0:
                self.gdw_comm_module.setCurrentIndex(idx)
        if "relay_level" in gdw:
            idx = self.gdw_relay_level.findData(gdw["relay_level"])
            if idx >= 0:
                self.gdw_relay_level.setCurrentIndex(idx)
        if "channel" in gdw:
            self.gdw_channel.setText(str(gdw["channel"]))
        if "resp_bytes" in gdw:
            self.gdw_resp_bytes.setText(str(gdw["resp_bytes"]))
        if "src_addr" in gdw:
            self.gdw_src_addr.setText(gdw["src_addr"])
        if "dst_addr" in gdw:
            self.gdw_dst_addr.setText(gdw["dst_addr"])

        # 恢复中继地址（需等 relay_level 信号触发后再设置）
        relay_addrs = gdw.get("relay_addrs", [])
        if relay_addrs:
            # 用 QTimer 延迟一帧，让 _on_gdw_relay_level_changed 先完成
            def _fill_relay():
                for i, edit in enumerate(self.gdw_relay_inputs):
                    if i < len(relay_addrs):
                        edit.setText(relay_addrs[i])
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, _fill_relay)

        # 恢复命令选择
        di_key = config.get("current_di_key")
        afn_fn = config.get("current_afn_fn")
        if mode == "south" and di_key:
            # di_key 被 JSON 序列化后变成了 list，需要转回 tuple
            if isinstance(di_key, list):
                di_key = tuple(di_key)
            for i in range(self.di_combo.count()):
                data = self.di_combo.itemData(i)
                if data == di_key:
                    self.di_combo.setCurrentIndex(i)
                    break
        elif mode == "gdw" and afn_fn:
            if isinstance(afn_fn, list):
                afn_fn = tuple(afn_fn)
            for i in range(self.afn_fn_combo.count()):
                data = self.afn_fn_combo.itemData(i)
                if data == afn_fn:
                    self.afn_fn_combo.setCurrentIndex(i)
                    break

        # 恢复自定义模板
        custom_templates_data = config.get("custom_templates", [])
        if custom_templates_data:
            self._custom_templates = [
                CustomFieldTemplate(
                    t["name"], t["length"], t["ftype"],
                    t["endian"], t["display"], t["reverse"]
                )
                for t in custom_templates_data
            ]

        # 恢复模式
        custom_mode = config.get("custom_mode", False)
        if custom_mode:
            self.mode_custom_rb.setChecked(True)
            self.mode_predefined_rb.setChecked(False)
            self._custom_mode = True
        else:
            self.mode_predefined_rb.setChecked(True)
            self.mode_custom_rb.setChecked(False)
            self._custom_mode = False

        # 恢复字段值（在表单重建后）
        field_values = config.get("field_values", {})
        if field_values:
            # 延迟一帧，让表单控件已创建
            def _apply_fields():
                for name, widget_info in self._field_widgets.items():
                    if name not in field_values:
                        continue
                    val = field_values[name]
                    widget = widget_info.get("widget")
                    if "sub_widgets" in widget_info:
                        for sub_name, sub_widget in widget_info["sub_widgets"].items():
                            if sub_name in field_values:
                                sv = field_values[sub_name]
                                if isinstance(sub_widget, QComboBox):
                                    idx = sub_widget.findData(sv)
                                    if idx >= 0:
                                        sub_widget.setCurrentIndex(idx)
                                else:
                                    sub_widget.setText(str(sv))
                    elif isinstance(widget, QComboBox):
                        idx = widget.findData(val)
                        if idx >= 0:
                            widget.setCurrentIndex(idx)
                    elif isinstance(widget, QLineEdit):
                        widget.setText(str(val))
                    elif widget is not None and hasattr(widget, '_items'):
                        # list 类型：先清空再添加
                        items = val if isinstance(val, list) else []
                        # 删除现有项
                        while widget._items:
                            row_widget, _ = widget._items.pop()
                            row_widget.deleteLater()
                        for item_values in items:
                            # 触发 add_item（通过点击按钮太复杂，直接重建）
                            pass  # list 类型暂不支持精确恢复
                self._schedule_realtime_update()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, _apply_fields)

    def _on_clear_serial_log(self):
        """清空串口日志"""
        self.serial_log.clear()

    def _on_serial_log_context_menu(self, pos):
        """串口日志区域右键菜单"""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        clear_action = menu.addAction("清空日志")
        copy_action = menu.addAction("复制选中内容")
        select_all_action = menu.addAction("全选")
        action = menu.exec(self.serial_log.mapToGlobal(pos))
        if action == clear_action:
            self.serial_log.clear()
        elif action == copy_action:
            self.serial_log.copy()
        elif action == select_all_action:
            self.serial_log.selectAll()

    @staticmethod
    def _trim_log(log_widget, max_lines: int = 500):
        """当日志超过max_lines行时，自动删除最早的行"""
        doc = log_widget.document()
        if doc.blockCount() > max_lines:
            cursor = log_widget.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor, doc.blockCount() - max_lines)
            cursor.removeSelectedText()

    def _on_serial_log(self, msg: str):
        """串口日志消息回调"""
        ts = datetime.now().strftime("%H:%M:%S")
        self.serial_log.append(f"[{ts}] {msg}")
        self._trim_log(self.serial_log)
        # 自动滚动到底部
        scrollbar = self.serial_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_serial_frame_received(self, frame: bytes):
        """收到串口帧后的解析与显示"""
        try:
            if self.protocol_mode == "south":
                table_data = self.parser.parse_to_table(frame)
                key_fields = ("应用功能码 (AFN)", "数据标识 (DI)", "传输方向")
            else:
                table_data = self.gdw_parser.parse_to_table(frame)
                key_fields = ("应用功能码(AFN)", "数据单元标识(DT)", "传输方向")
            self._populate_response_table(table_data)
            summary_parts = []
            for item in table_data:
                field_name = item[0].strip()
                if field_name in key_fields:
                    parsed = str(item[2]) if item[2] else str(item[3])
                    summary_parts.append(f"{field_name}: {parsed}")
            ts = datetime.now().strftime("%H:%M:%S")
            if summary_parts:
                self.serial_log.append(f"[{ts}] [解析] {' | '.join(summary_parts)}")
            else:
                self.serial_log.append(f"[{ts}] [解析] 帧结构识别成功")
        except Exception as e:
            ts = datetime.now().strftime("%H:%M:%S")
            self.serial_log.append(f"[{ts}] [解析失败] {e}")

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
    # 协议模式切换
    # ------------------------------------------------------------------
    def set_protocol_mode(self, mode: str):
        """切换协议模式: 'south' 或 'gdw'"""
        if mode not in ("south", "gdw"):
            return
        self.protocol_mode = mode

        # 切换命令选择区
        if mode == "south":
            self.cmd_select_group.setTitle("DI 选择")
            self.di_combo.setVisible(True)
            self.afn_fn_combo.setVisible(False)
            self.south_config_group.setVisible(True)
            self.gdw_config_group.setVisible(False)
        else:
            self.cmd_select_group.setTitle("AFN+Fn 选择")
            self.di_combo.setVisible(False)
            self.afn_fn_combo.setVisible(True)
            self.south_config_group.setVisible(False)
            self.gdw_config_group.setVisible(True)

        # 清空当前选择
        self.di_combo.setCurrentIndex(0)
        self.afn_fn_combo.setCurrentIndex(0)
        self._current_di_key = None
        self._current_afn_fn = None
        self._rebuild_form(None)
        self.result_hex.clear()
        self.preview_table.setRowCount(0)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def reset(self):
        self.di_combo.setCurrentIndex(0)
        self.afn_fn_combo.setCurrentIndex(0)
        self.src_addr_input.setText("000000000000")
        self.dst_addr_input.setText("000000000000")
        self.gdw_src_addr.setText("000000000000")
        self.gdw_dst_addr.setText("000000000000")
        self.dir_combo.setCurrentIndex(0)
        self.prm_combo.setCurrentIndex(0)
        self.add_combo.setCurrentIndex(0)
        self.gdw_dir.setCurrentIndex(0)
        self.gdw_prm.setCurrentIndex(0)
        self.gdw_comm_type.setCurrentIndex(0)
        self.gdw_route_flag.setCurrentIndex(0)
        self.gdw_comm_module.setCurrentIndex(0)
        self.gdw_relay_level.setCurrentIndex(0)
        self.gdw_seq.setText("0")
        self.gdw_channel.setText("0")
        self.gdw_resp_bytes.setText("0")
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
