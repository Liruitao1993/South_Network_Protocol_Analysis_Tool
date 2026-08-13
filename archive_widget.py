"""档案管理Widget

提供从节点（电能表）白名单档案管理界面，支持南网协议和国网协议。
包含档案表格、操作按钮、串口交互和响应解析。
"""

import json
import struct
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QTextEdit, QMessageBox, QSplitter, QMenu, QCheckBox, QGridLayout,
    QFileDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from send_frame_lib import ProtocolFrameGenerator
from gdw_send_frame_lib import GDWFrameGenerator
from protocol_parser import ProtocolFrameParser
from gdw10376_parser import GDW10376Parser
from dlt645_parser import DLT645Parser
from lme_info_entry_parser import parse_lme_info_entries, format_lme_info_summary
from gui_utils import ZoomableTableWidget

ARCHIVE_FILE = "archive_data.json"


def _crc16_x25(data: bytes) -> int:
    """X-25 CRC16 (多项式0x1021, 初始值0xFFFF, 输入/输出反转, 输出异或0xFFFF)"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408  # 0x1021 bit-reversed
            else:
                crc >>= 1
    return crc ^ 0xFFFF


class AddNodesDialog(QDialog):
    """添加从节点对话框"""

    def __init__(self, protocol_mode: str = "south", parent=None):
        super().__init__(parent)
        self.protocol_mode = protocol_mode
        self.setWindowTitle("添加从节点")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("请输入从节点地址（每行一个，12位十进制或HEX）："))

        self.addr_input = QTextEdit()
        self.addr_input.setPlaceholderText("例如：\n123456789012\n000000000022")
        self.addr_input.setMaximumHeight(150)
        layout.addWidget(self.addr_input)

        if self.protocol_mode == "gdw":
            proto_layout = QHBoxLayout()
            proto_layout.addWidget(QLabel("通信协议类型："))
            self.proto_combo = QComboBox()
            self.proto_combo.addItem("0-透明传输", 0)
            self.proto_combo.addItem("1-DL/T 645-1997", 1)
            self.proto_combo.addItem("2-DL/T 645-2007", 2)
            self.proto_combo.addItem("3-DL/T 698.45", 3)
            self.proto_combo.addItem("4-Wrapper", 4)
            proto_layout.addWidget(self.proto_combo)
            proto_layout.addStretch()
            layout.addLayout(proto_layout)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def get_nodes(self) -> List[Dict[str, Any]]:
        """返回节点列表，每项包含 address 和 protocol"""
        text = self.addr_input.toPlainText().strip()
        nodes = []
        for line in text.splitlines():
            line = line.strip().replace(" ", "").replace("\t", "")
            if not line:
                continue
            # 统一处理为12位字符串
            if len(line) > 12:
                line = line[:12]
            elif len(line) < 12:
                line = line.zfill(12)
            node = {"address": line}
            if self.protocol_mode == "gdw":
                node["protocol"] = self.proto_combo.currentData()
            nodes.append(node)
        return nodes


class AddMeterDialog(QDialog):
    """添加电能表对话框（支持连续添加模式）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加电表")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 电表信息分组
        info_group = QGroupBox("电表信息")
        grid = QGridLayout(info_group)
        grid.setSpacing(8)

        grid.addWidget(QLabel("电 表 号："), 0, 0)
        self.meter_id = QLineEdit()
        self.meter_id.setMaxLength(12)
        grid.addWidget(self.meter_id, 0, 1)

        grid.addWidget(QLabel("采集模块："), 0, 2)
        self.module_id = QLineEdit()
        grid.addWidget(self.module_id, 0, 3)

        grid.addWidget(QLabel("抄收方式："), 1, 0)
        self.comm_type = QComboBox()
        self.comm_type.addItems(["电力载波", "微功率无线", "以太网", "RS485", "双模"])
        grid.addWidget(self.comm_type, 1, 1)

        grid.addWidget(QLabel("抄表协议："), 1, 2)
        self.proto_type = QComboBox()
        self.proto_type.addItems(["DL/T698.45", "DL/T645-2007", "DL/T645-1997", "Wrapper", "HDLC", "透明传输"])
        grid.addWidget(self.proto_type, 1, 3)

        grid.addWidget(QLabel("载波相位："), 2, 0)
        self.phase = QComboBox()
        self.phase.addItems(["未知", "A相", "B相", "C相"])
        grid.addWidget(self.phase, 2, 1)

        grid.addWidget(QLabel("电表类型："), 2, 2)
        self.meter_type = QComboBox()
        self.meter_type.addItems(["电压采集终端", "电流采集终端", "电能表", "集中器", "采集器"])
        grid.addWidget(self.meter_type, 2, 3)

        grid.addWidget(QLabel("备注信息："), 3, 0)
        self.remark = QTextEdit()
        self.remark.setMaximumHeight(60)
        grid.addWidget(self.remark, 3, 1, 1, 3)

        layout.addWidget(info_group)

        # 底部按钮行
        bottom_layout = QHBoxLayout()

        self.continuous_cb = QCheckBox("连续添加模式")
        bottom_layout.addWidget(self.continuous_cb)
        bottom_layout.addStretch()

        self.add_btn = QPushButton("添加(A)")
        self.add_btn.clicked.connect(self._on_add)
        bottom_layout.addWidget(self.add_btn)

        self.apply_btn = QPushButton("应用(O)")
        self.apply_btn.clicked.connect(self._on_apply)
        bottom_layout.addWidget(self.apply_btn)

        cancel_btn = QPushButton("取消(C)")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)

        layout.addLayout(bottom_layout)

    def _on_add(self):
        if not self.meter_id.text().strip():
            QMessageBox.warning(self, "警告", "电表号不能为空！")
            return
        self.done(100)  # 自定义返回码：添加但不关闭

    def _on_apply(self):
        if not self.meter_id.text().strip():
            QMessageBox.warning(self, "警告", "电表号不能为空！")
            return
        self.accept()

    def get_meter_info(self) -> Dict[str, Any]:
        return {
            "meter_id": self.meter_id.text().strip().zfill(12),
            "module_id": self.module_id.text().strip(),
            "comm_type": self.comm_type.currentText(),
            "protocol": self.proto_type.currentText(),
            "phase": self.phase.currentText(),
            "meter_type": self.meter_type.currentText(),
            "remark": self.remark.toPlainText().strip(),
        }

    def clear_fields(self):
        self.meter_id.clear()
        self.module_id.clear()
        self.remark.clear()
        self.meter_id.setFocus()


class ArchiveWidget(QWidget):
    """档案管理页面Widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.protocol_mode = "south"
        self.serial_worker = None
        self.generator = ProtocolFrameGenerator()
        self.gdw_generator = GDWFrameGenerator()
        self.parser = ProtocolFrameParser()
        self.gdw_parser = GDW10376Parser()
        self._node_data: List[Dict[str, Any]] = []
        self.setup_ui()
        self._load_archive()  # 启动时自动加载上次档案

        # 版本查询队列
        self._version_query_queue: List[Tuple[int, str]] = []  # [(row, addr), ...]
        self._version_query_mode: str = ""  # "simple" | "detail"
        self._version_query_timer = None
        self._version_query_timeout_ms: int = 5000  # 默认5秒超时
        self._is_querying_version: bool = False
        self._version_query_current_row: int = -1
        self._version_query_current_addr: str = ""
        self._gdw_seq_counter: int = 0  # 1376.2 报文序列号，每次发送+1

        # 抄表测试
        self._copy_test_queue: List[Tuple[int, str, str, int]] = []
        self._copy_test_timer = None
        self._copy_test_timeout_ms: int = 3000
        self._is_copy_testing: bool = False
        self._copy_test_mode: str = ""  # "sequential" | "concurrent"
        self._copy_test_stats: Dict[str, Dict[str, int]] = {}
        self._copy_test_count: int = 3
        self._copy_test_concurrent_responses: Dict[str, int] = {}
        self._copy_test_remaining_rounds: int = 0

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # === 配置栏 ===
        self._setup_config_bar(main_layout)

        # === 状态标签 ===
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        main_layout.addWidget(self.status_label)

        # === 档案表格 ===
        table_group = QGroupBox("从节点档案列表")
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(6, 4, 6, 4)
        table_layout.setSpacing(4)

        self.table = ZoomableTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(["选择", "序号", "电表号/从节点地址", "电表协议", "相位/相序", "状态", "版本信息", "详细版本", "抄读结果", "其他信息"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 50)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 200)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        table_font = QFont()
        table_font.setPointSize(8)
        self.table.setFont(table_font)
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        table_layout.addWidget(self.table)
        main_layout.addWidget(table_group, 1)

        # === 操作按钮 ===
        self._setup_buttons(main_layout)

        # === 串口日志 ===
        log_group = QGroupBox("操作日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 4, 6, 4)
        self.serial_log = QTextEdit()
        self.serial_log.setReadOnly(True)
        self.serial_log.setMaximumHeight(100)
        self.serial_log.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.serial_log)
        main_layout.addWidget(log_group)

    def _setup_config_bar(self, parent_layout):
        # ---- 南网帧配置 ----
        self.south_config_group = QGroupBox("南网帧配置")
        south_layout = QHBoxLayout(self.south_config_group)
        south_layout.setContentsMargins(6, 4, 6, 4)
        south_layout.setSpacing(6)

        south_layout.addWidget(QLabel("源地址:"))
        self.src_addr = QLineEdit("000000000000")
        self.src_addr.setMaxLength(12)
        self.src_addr.setFixedWidth(120)
        south_layout.addWidget(self.src_addr)

        south_layout.addWidget(QLabel("目的地址:"))
        self.dst_addr = QLineEdit("000000000000")
        self.dst_addr.setMaxLength(12)
        self.dst_addr.setFixedWidth(120)
        south_layout.addWidget(self.dst_addr)

        south_layout.addWidget(QLabel("DIR:"))
        self.dir_combo = QComboBox()
        self.dir_combo.addItem("0-下行", 0)
        self.dir_combo.addItem("1-上行", 1)
        south_layout.addWidget(self.dir_combo)

        south_layout.addWidget(QLabel("PRM:"))
        self.prm_combo = QComboBox()
        self.prm_combo.addItem("1-启动站", 1)
        self.prm_combo.addItem("0-从动站", 0)
        south_layout.addWidget(self.prm_combo)

        south_layout.addWidget(QLabel("ADD:"))
        self.add_combo = QComboBox()
        self.add_combo.addItem("0-不带地址域", 0)
        self.add_combo.addItem("1-带地址域", 1)
        south_layout.addWidget(self.add_combo)

        south_layout.addStretch()
        parent_layout.addWidget(self.south_config_group)

        # ---- 国网帧配置 ----
        self.gdw_config_group = QGroupBox("国网帧配置")
        gdw_layout = QVBoxLayout(self.gdw_config_group)
        gdw_layout.setContentsMargins(6, 4, 6, 4)
        gdw_layout.setSpacing(4)

        info_layout = QHBoxLayout()
        info_layout.setSpacing(6)

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

        info_layout.addWidget(QLabel("通信模块标识:"))
        self.gdw_comm_module = QComboBox()
        self.gdw_comm_module.addItem("0-对主节点", 0)
        self.gdw_comm_module.addItem("1-对从节点", 1)
        info_layout.addWidget(self.gdw_comm_module)

        info_layout.addWidget(QLabel("中继级别:"))
        self.gdw_relay_level = QComboBox()
        for i in range(16):
            self.gdw_relay_level.addItem(f"{i}", i)
        info_layout.addWidget(self.gdw_relay_level)

        info_layout.addStretch()
        gdw_layout.addLayout(info_layout)

        addr_layout = QHBoxLayout()
        addr_layout.setSpacing(6)
        addr_layout.addWidget(QLabel("源地址(A1):"))
        self.gdw_src_addr = QLineEdit("000000000000")
        self.gdw_src_addr.setMaxLength(12)
        self.gdw_src_addr.setFixedWidth(120)
        addr_layout.addWidget(self.gdw_src_addr)

        addr_layout.addWidget(QLabel("目的地址(A3):"))
        self.gdw_dst_addr = QLineEdit("000000000000")
        self.gdw_dst_addr.setMaxLength(12)
        self.gdw_dst_addr.setFixedWidth(120)
        addr_layout.addWidget(self.gdw_dst_addr)
        addr_layout.addStretch()
        gdw_layout.addLayout(addr_layout)

        # 抄读配置
        copy_config_layout = QHBoxLayout()
        copy_config_layout.setSpacing(6)
        copy_config_layout.addWidget(QLabel("抄读次数:"))
        self.copy_count_input = QLineEdit("3")
        self.copy_count_input.setFixedWidth(40)
        copy_config_layout.addWidget(self.copy_count_input)
        copy_config_layout.addWidget(QLabel("超时(ms):"))
        self.copy_timeout_input = QLineEdit("3000")
        self.copy_timeout_input.setFixedWidth(50)
        copy_config_layout.addWidget(self.copy_timeout_input)
        copy_config_layout.addStretch()
        gdw_layout.addLayout(copy_config_layout)

        self.gdw_config_group.setVisible(False)
        parent_layout.addWidget(self.gdw_config_group)

    def _setup_buttons(self, parent_layout):
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        # 档案操作
        archive_group = QGroupBox("档案操作")
        archive_layout = QHBoxLayout(archive_group)
        archive_layout.setSpacing(6)
        archive_layout.setContentsMargins(6, 4, 6, 4)

        self.add_node_btn = QPushButton("添加从节点")
        self.add_node_btn.clicked.connect(self._on_add_nodes)
        archive_layout.addWidget(self.add_node_btn)

        self.del_node_btn = QPushButton("删除从节点")
        self.del_node_btn.clicked.connect(self._on_delete_nodes)
        archive_layout.addWidget(self.del_node_btn)

        self.init_archive_btn = QPushButton("参数初始化")
        self.init_archive_btn.clicked.connect(self._on_init_archive)
        archive_layout.addWidget(self.init_archive_btn)

        archive_layout.addWidget(QLabel("|"))

        self.export_archive_btn = QPushButton("导出档案")
        self.export_archive_btn.clicked.connect(self._on_export_archive)
        archive_layout.addWidget(self.export_archive_btn)

        self.import_archive_btn = QPushButton("导入档案")
        self.import_archive_btn.clicked.connect(self._on_import_archive)
        archive_layout.addWidget(self.import_archive_btn)

        btn_layout.addWidget(archive_group)

        # 查询操作
        query_group = QGroupBox("查询操作")
        query_layout = QHBoxLayout(query_group)
        query_layout.setSpacing(6)
        query_layout.setContentsMargins(6, 4, 6, 4)

        self.query_count_btn = QPushButton("查询从节点数量")
        self.query_count_btn.clicked.connect(self._on_query_node_count)
        query_layout.addWidget(self.query_count_btn)

        self.query_info_btn = QPushButton("查询从节点信息")
        self.query_info_btn.clicked.connect(self._on_query_node_info)
        query_layout.addWidget(self.query_info_btn)

        self.query_version_btn = QPushButton("查询从节点版本")
        self.query_version_btn.clicked.connect(self._on_query_node_version)
        query_layout.addWidget(self.query_version_btn)

        self.query_version_detail_btn = QPushButton("查询从节点详细版本")
        self.query_version_detail_btn.clicked.connect(self._on_query_node_version_detail)
        query_layout.addWidget(self.query_version_detail_btn)

        query_layout.addWidget(QLabel("|"))

        self.copy_test_btn = QPushButton("点抄测试")
        self.copy_test_btn.clicked.connect(self._on_copy_test)
        query_layout.addWidget(self.copy_test_btn)

        self.concurrent_copy_btn = QPushButton("并发抄表")
        self.concurrent_copy_btn.clicked.connect(self._on_concurrent_copy)
        query_layout.addWidget(self.concurrent_copy_btn)

        btn_layout.addWidget(query_group)

        # 任务操作
        task_group = QGroupBox("任务操作")
        task_layout = QHBoxLayout(task_group)
        task_layout.setSpacing(6)
        task_layout.setContentsMargins(6, 4, 6, 4)

        self.init_task_btn = QPushButton("初始化任务")
        self.init_task_btn.clicked.connect(self._on_init_task)
        task_layout.addWidget(self.init_task_btn)

        self.start_task_btn = QPushButton("启动任务")
        self.start_task_btn.clicked.connect(self._on_start_task)
        task_layout.addWidget(self.start_task_btn)

        self.pause_task_btn = QPushButton("暂停任务")
        self.pause_task_btn.clicked.connect(self._on_pause_task)
        task_layout.addWidget(self.pause_task_btn)

        btn_layout.addWidget(task_group)
        self.task_group = task_group  # ref for visibility toggle

        btn_layout.addStretch()
        parent_layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # Serial worker
    # ------------------------------------------------------------------
    def set_serial_worker(self, worker):
        """设置串口工作线程实例"""
        self.serial_worker = worker
        if worker:
            worker.frame_received.connect(self._on_frame_received)
            worker.log_message.connect(self._on_serial_log)
            worker.connection_changed.connect(self._update_button_state)

    def _update_button_state(self, connected: bool):
        for btn in [
            self.add_node_btn, self.del_node_btn, self.init_archive_btn,
            self.query_count_btn, self.query_info_btn,
            self.query_version_btn, self.query_version_detail_btn,
            self.copy_test_btn, self.concurrent_copy_btn,
            self.init_task_btn, self.start_task_btn, self.pause_task_btn
        ]:
            btn.setEnabled(connected)

    # ------------------------------------------------------------------
    # Protocol mode
    # ------------------------------------------------------------------
    def set_protocol_mode(self, mode: str):
        if mode not in ("south", "gdw"):
            return
        self.protocol_mode = mode
        self.south_config_group.setVisible(mode == "south")
        self.gdw_config_group.setVisible(mode == "gdw")
        self.task_group.setVisible(mode == "south")
        self.init_archive_btn.setText("档案初始化" if mode == "south" else "参数初始化")
        # 切换协议时不清空档案数据，档案可在南网/国网间共享

    def reset(self):
        self.table.setRowCount(0)
        self._node_data.clear()
        self.status_label.setText("就绪")
        if hasattr(self, 'serial_log'):
            self.serial_log.clear()
        self._save_archive()

    # ------------------------------------------------------------------
    # JSON 持久化
    # ------------------------------------------------------------------
    def _save_archive(self):
        """将当前档案数据保存到 JSON 文件"""
        try:
            with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._node_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 静默失败，不影响主流程

    def _load_archive(self):
        """从 JSON 文件加载档案数据并填充表格"""
        import os
        if not os.path.exists(ARCHIVE_FILE):
            return
        try:
            with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            self.table.setRowCount(0)
            self._node_data.clear()
            for info in data:
                if not isinstance(info, dict):
                    continue
                # 向后兼容：确保必要字段存在
                info.setdefault("meter_id", "")
                info.setdefault("module_id", "")
                info.setdefault("comm_type", "电力载波")
                info.setdefault("protocol", "DL/T698.45")
                info.setdefault("phase", "未知")
                info.setdefault("meter_type", "电能表")
                info.setdefault("remark", "")
                self._add_meter_to_table(info)
            self._log(f"[本地] 已加载 {len(self._node_data)} 条档案记录")
        except Exception:
            pass

    def _on_export_archive(self):
        """导出档案到指定 JSON 文件"""
        path, _ = QFileDialog.getSaveFileName(self, "导出档案", "archive_export.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._node_data, f, ensure_ascii=False, indent=2)
            self._log(f"[本地] 档案已导出: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_import_archive(self):
        """从 JSON 文件导入档案"""
        path, _ = QFileDialog.getOpenFileName(self, "导入档案", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("文件格式错误：应为 JSON 数组")
            reply = QMessageBox.question(
                self, "确认导入",
                f"确定导入 {len(data)} 条档案记录？\n当前表格中的记录将被覆盖。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.table.setRowCount(0)
            self._node_data.clear()
            for info in data:
                if isinstance(info, dict):
                    info.setdefault("meter_id", "")
                    info.setdefault("module_id", "")
                    info.setdefault("comm_type", "电力载波")
                    info.setdefault("protocol", "DL/T698.45")
                    info.setdefault("phase", "未知")
                    info.setdefault("meter_type", "电能表")
                    info.setdefault("remark", "")
                    self._add_meter_to_table(info)
            self._save_archive()
            self._log(f"[本地] 已导入 {len(self._node_data)} 条档案记录")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    # ------------------------------------------------------------------
    # Frame helpers
    # ------------------------------------------------------------------
    def _build_south_frame(self, di_key: Tuple[int, int, int, int], field_values: Dict[str, Any]) -> bytes:
        src = bytes.fromhex(self.src_addr.text().strip().zfill(12))
        dst = bytes.fromhex(self.dst_addr.text().strip().zfill(12))
        return self.generator.generate_frame(
            di_key, field_values,
            src_addr=src, dst_addr=dst,
            dir_flag=self.dir_combo.currentData(),
            prm=self.prm_combo.currentData(),
            add_flag=self.add_combo.currentData()
        )

    def _build_gdw_frame(self, afn: int, fn: int, field_values: Dict[str, Any]) -> bytes:
        seq = self._gdw_seq_counter
        self._gdw_seq_counter = (self._gdw_seq_counter + 1) & 0xFF
        self.gdw_seq.setText(str(self._gdw_seq_counter))
        info_config = {
            "dir": self.gdw_dir.currentData(),
            "prm": self.gdw_prm.currentData(),
            "通信方式": 4,  # 双模
            "报文序列号": seq,
            "通信模块标识": self.gdw_comm_module.currentData(),
            "中继级别": self.gdw_relay_level.currentData(),
            "路由标识": 0,
            "附属节点标识": 0,
            "冲突检测": 0,
            "纠错编码标识": 0,
            "信道标识": 0,
            "预计应答字节数": 0,
            "通信速率": 0,
            "速率单位标识": 0,
        }
        return self.gdw_generator.generate_frame(
            afn, fn, field_values, info_config,
            src_addr=self.gdw_src_addr.text().strip(),
            dst_addr=self.gdw_dst_addr.text().strip()
        )

    def _send_hex(self, hex_str: str, cmd_name: str):
        if not self.serial_worker:
            QMessageBox.warning(self, "警告", "串口未连接！")
            return
        self.serial_worker.send_hex_string(hex_str)
        self._log(f"[发送] {cmd_name}: {hex_str}")

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------
    def _on_add_nodes(self):
        checked_rows = self._get_checked_rows()
        if not checked_rows:
            QMessageBox.warning(self, "警告", "请先在表格中勾选要添加的从节点！")
            return

        if self.protocol_mode == "south":
            node_list = []
            for row in checked_rows:
                addr_str = self.table.item(row, 2).text().strip().zfill(12)
                # Schema 已定义 reverse=True，直接传字符串即可自动小端序填充
                node_list.append({"从节点地址": addr_str})
            frame = self._build_south_frame(
                (0xE8, 0x02, 0x04, 0x02),
                {"从节点地址列表": node_list}
            )
        else:
            node_list = []
            for row in checked_rows:
                addr_str = self.table.item(row, 2).text().strip().zfill(12)
                proto = self.table.item(row, 3).text().strip()
                proto_map = {
                    "DL/T645-1997": 1, "DL/T645-2007": 2,
                    "DL/T698.45": 3, "Wrapper": 4,
                    "透明传输": 0, "HDLC": 0,
                }
                node_list.append({
                    "从节点地址": addr_str,
                    "通信协议类型": proto_map.get(proto, 0)
                })
            frame = self._build_gdw_frame(0x11, 1, {"从节点列表": node_list})

        self._send_hex(frame.hex().upper(), "添加从节点")

    def _on_delete_nodes(self):
        checked_rows = self._get_checked_rows()
        if not checked_rows:
            QMessageBox.warning(self, "警告", "请先在表格中勾选要删除的从节点！")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除选中的 {len(checked_rows)} 个从节点？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.protocol_mode == "south":
            node_list = []
            for row in checked_rows:
                addr_str = self.table.item(row, 2).text().strip()
                node_list.append({"从节点地址": addr_str.zfill(12)})
            frame = self._build_south_frame(
                (0xE8, 0x02, 0x04, 0x03),
                {"从节点地址列表": node_list}
            )
        else:
            node_list = []
            for row in checked_rows:
                addr_str = self.table.item(row, 2).text().strip()
                node_list.append({"从节点地址": addr_str.zfill(12)})
            frame = self._build_gdw_frame(0x11, 2, {"从节点列表": node_list})

        self._send_hex(frame.hex().upper(), "删除从节点")

    def _on_init_archive(self):
        if self.protocol_mode == "south":
            frame = self._build_south_frame((0xE8, 0x02, 0x01, 0x02), {})
            self._send_hex(frame.hex().upper(), "档案初始化")
        else:
            frame = self._build_gdw_frame(0x01, 2, {})
            self._send_hex(frame.hex().upper(), "参数区初始化")

    def _on_query_node_count(self):
        if self.protocol_mode == "south":
            frame = self._build_south_frame((0xE8, 0x00, 0x03, 0x05), {})
        else:
            frame = self._build_gdw_frame(0x10, 1, {})
        self._send_hex(frame.hex().upper(), "查询从节点数量")

    def _on_query_node_info(self):
        if self.protocol_mode == "south":
            frame = self._build_south_frame(
                (0xE8, 0x03, 0x03, 0x06),
                {"从节点起始序号": 0, "从节点数量": 50}
            )
        else:
            frame = self._build_gdw_frame(
                0x10, 2,
                {"从节点起始序号": 1, "从节点数量": 50}
            )
        self._send_hex(frame.hex().upper(), "查询从节点信息")

    def _on_query_node_version(self):
        """查询从节点版本（AFN=03 F1 厂商代码和版本信息）"""
        checked_rows = self._get_checked_rows()
        if not checked_rows:
            QMessageBox.warning(self, "警告", "请先在表格中勾选要查询的从节点！")
            return
        if self.protocol_mode != "gdw":
            QMessageBox.warning(self, "警告", "版本查询仅在国网协议模式下支持！")
            return
        self._start_version_query(checked_rows, "simple")

    def _on_query_node_version_detail(self):
        """查询从节点详细版本信息（AFN=13 F1 + DLT645内层）"""
        checked_rows = self._get_checked_rows()
        if not checked_rows:
            QMessageBox.warning(self, "警告", "请先在表格中勾选要查询的从节点！")
            return
        if self.protocol_mode != "gdw":
            QMessageBox.warning(self, "警告", "版本查询仅在国网协议模式下支持！")
            return
        self._start_version_query(checked_rows, "detail")

    # ------------------------------------------------------------------
    # 抄表测试
    # ------------------------------------------------------------------
    def _on_copy_test(self):
        """点抄测试（AFN=13 F1，依次抄读）"""
        checked_rows = self._get_checked_rows()
        if not checked_rows:
            QMessageBox.warning(self, "警告", "请先在表格中勾选要抄读的电表！")
            return
        if self.protocol_mode != "gdw":
            QMessageBox.warning(self, "警告", "抄表测试仅在国网协议模式下支持！")
            return
        self._start_copy_test(checked_rows, "sequential")

    def _on_concurrent_copy(self):
        """并发抄表测试（AFN=F1 F1）"""
        checked_rows = self._get_checked_rows()
        if not checked_rows:
            QMessageBox.warning(self, "警告", "请先在表格中勾选要抄读的电表！")
            return
        if self.protocol_mode != "gdw":
            QMessageBox.warning(self, "警告", "抄表测试仅在国网协议模式下支持！")
            return
        self._start_copy_test(checked_rows, "concurrent")

    def _build_dlt645_read_energy_frame(self, addr: str) -> bytes:
        """构建DLT645-2007读正向有功总电能帧"""
        addr_bytes = bytes.fromhex(addr.zfill(12))[::-1]
        di_bytes = (0x00010000).to_bytes(4, 'little')
        data_field = bytes([(b + 0x33) & 0xFF for b in di_bytes])
        frame = bytearray()
        frame.append(0x68)
        frame.extend(addr_bytes)
        frame.append(0x68)
        frame.append(0x11)
        frame.append(len(data_field))
        frame.extend(data_field)
        cs = sum(frame) & 0xFF
        frame.append(cs)
        frame.append(0x16)
        return bytes(frame)

    def _build_dlt698_read_energy_frame(self, addr: str) -> bytes:
        """构建DL/T 698.45读正向有功总电能帧（基于用户参考报文模板）

        参考报文: 68 2C 00 43 05 25 01 00 00 03 02 00 7B E3
                  10 00 08 05 01 7D 00 10 02 01 00 01 10 00 01 02 03 04
                  05 06 07 08 09 0A 0B 0C 0D 0E 0F 84 66 16
        HCS: X-25 CRC(frame[1:12]), 小端序存储
        FCS: X-25 CRC(frame[1:-3]), 小端序存储
        """
        # 地址BCD编码（12位十进制→6字节，小端序）
        addr_bytes = bytes.fromhex(addr.zfill(12))[::-1]

        # 模板报文（地址和校验先填00）
        frame = bytearray(bytes.fromhex(
            '68'          # 起始符
            '2C00'        # L = 44 (小端)
            '43'          # C
            '000000000000'  # 地址占位（6字节）
            '0200'        # CA + SA
            '0000'        # HCS占位
            '1000'        # 数据长度 = 16
            '0805017D00100201000110000102'  # APDU前14字节
            '030405060708090A0B0C0D0E0F'    # APDU后2字节 + 其他数据
            '0000'        # FCS占位
            '16'          # 结束符
        ))

        # 替换地址（索引4-9）
        frame[4:10] = addr_bytes

        # 计算HCS：从L1到SA（索引1到11，含），X-25 CRC，小端序
        hcs_raw = _crc16_x25(bytes(frame[1:12]))
        frame[12] = hcs_raw & 0xFF
        frame[13] = (hcs_raw >> 8) & 0xFF

        # 计算FCS：从L1到DATA末尾（索引1到-3，不含FCS和16），X-25 CRC，小端序
        fcs_raw = _crc16_x25(bytes(frame[1:-3]))
        frame[-3] = fcs_raw & 0xFF
        frame[-2] = (fcs_raw >> 8) & 0xFF

        return bytes(frame)

    def _start_copy_test(self, rows: List[int], mode: str):
        """启动抄表测试"""
        try:
            self._copy_test_count = max(1, int(self.copy_count_input.text() or "3"))
        except ValueError:
            self._copy_test_count = 3
        try:
            self._copy_test_timeout_ms = max(500, int(self.copy_timeout_input.text() or "3000"))
        except ValueError:
            self._copy_test_timeout_ms = 3000
        self._copy_test_queue = []
        self._copy_test_stats = {}
        self._copy_test_concurrent_responses = {}

        for row in rows:
            addr = self.table.item(row, 2).text().strip().zfill(12)
            proto = self.table.item(row, 3).text().strip()
            self._copy_test_stats[addr] = {"sent": 0, "success": 0, "total": self._copy_test_count}
            self._copy_test_queue.append((row, addr, proto, self._copy_test_count))
            self.table.setItem(row, 8, QTableWidgetItem("抄读中..."))

        self._copy_test_mode = mode
        self._is_copy_testing = True

        if mode == "sequential":
            self._log(f"[点抄测试] 开始依次抄读 {len(rows)} 个电表，每表{self._copy_test_count}次")
            self._send_next_copy_test()
        else:
            self._copy_test_remaining_rounds = self._copy_test_count
            self._log(f"[并发抄表] 开始并发抄读 {len(rows)} 个电表，共{self._copy_test_count}轮")
            self._send_concurrent_copy()

    def _send_next_copy_test(self):
        """发送队列中的下一个点抄"""
        if not self._copy_test_queue:
            self._is_copy_testing = False
            self._log("[点抄测试] 所有电表抄读完成")
            return
        row, addr, proto, remaining = self._copy_test_queue[0]

        if "645" in proto:
            inner_frame = self._build_dlt645_read_energy_frame(addr)
            proto_type = 2
        elif "698" in proto:
            inner_frame = self._build_dlt698_read_energy_frame(addr)
            proto_type = 3
        else:
            inner_frame = self._build_dlt645_read_energy_frame(addr)
            proto_type = 2

        field_values = {
            "通信协议类型": proto_type,
            "通信延时相关性标志": 0,
            "从节点附属节点数量": 0,
            "报文长度": len(inner_frame),
            "报文内容": inner_frame.hex().upper(),
        }
        seq = self._gdw_seq_counter
        self._gdw_seq_counter = (self._gdw_seq_counter + 1) & 0xFF
        self.gdw_seq.setText(str(self._gdw_seq_counter))
        info_config = {
            "dir": 0, "prm": 1, "通信方式": 4,
            "报文序列号": seq,
            "通信模块标识": 1, "中继级别": 0,
            "路由标识": 0, "附属节点标识": 0,
            "冲突检测": 0, "纠错编码标识": 0,
            "信道标识": 0, "预计应答字节数": 0,
            "通信速率": 0, "速率单位标识": 0,
        }
        frame = self.gdw_generator.generate_frame(
            0x13, 1, field_values, info_config,
            src_addr=self.gdw_src_addr.text().strip(),
            dst_addr=addr
        )
        self._copy_test_stats[addr]["sent"] += 1
        current = self._copy_test_count - remaining + 1
        self._send_hex(frame.hex().upper(), f"点抄 [{addr}] 第{current}/{self._copy_test_count}次")

        if self._copy_test_timer is None:
            from PySide6.QtCore import QTimer
            self._copy_test_timer = QTimer(self)
            self._copy_test_timer.setSingleShot(True)
            self._copy_test_timer.timeout.connect(self._on_copy_test_timeout)
        self._copy_test_timer.start(self._copy_test_timeout_ms)

    def _send_concurrent_copy(self):
        """发送并发抄表帧（AFN=F1 F1）"""
        node_list = []
        for row, addr, proto, _ in self._copy_test_queue:
            if "645" in proto:
                inner_frame = self._build_dlt645_read_energy_frame(addr)
                proto_type = 2
            elif "698" in proto:
                inner_frame = self._build_dlt698_read_energy_frame(addr)
                proto_type = 3
            else:
                inner_frame = self._build_dlt645_read_energy_frame(addr)
                proto_type = 2
            node_list.append({
                "从节点地址": addr,
                "通信协议类型": proto_type,
                "报文长度": len(inner_frame),
                "报文内容": inner_frame.hex().upper(),
            })
            self._copy_test_concurrent_responses[addr] = 0

        field_values = {
            "从节点数量": len(node_list),
            "从节点列表": node_list,
        }
        self._copy_test_concurrent_responses = {}
        seq = self._gdw_seq_counter
        self._gdw_seq_counter = (self._gdw_seq_counter + 1) & 0xFF
        self.gdw_seq.setText(str(self._gdw_seq_counter))
        info_config = {
            "dir": 0, "prm": 1, "通信方式": 4,
            "报文序列号": seq,
            "通信模块标识": 1, "中继级别": 0,
            "路由标识": 0, "附属节点标识": 0,
            "冲突检测": 0, "纠错编码标识": 0,
            "信道标识": 0, "预计应答字节数": 0,
            "通信速率": 0, "速率单位标识": 0,
        }
        frame = self.gdw_generator.generate_frame(
            0xF1, 1, field_values, info_config,
            src_addr=self.gdw_src_addr.text().strip(),
            dst_addr="000000000000"
        )
        for addr in self._copy_test_stats:
            self._copy_test_stats[addr]["sent"] = self._copy_test_stats[addr]["total"]
        self._send_hex(frame.hex().upper(), f"并发抄表 {len(node_list)} 个电表")

        if self._copy_test_timer is None:
            from PySide6.QtCore import QTimer
            self._copy_test_timer = QTimer(self)
            self._copy_test_timer.setSingleShot(True)
            self._copy_test_timer.timeout.connect(self._on_copy_test_timeout)
        timeout = self._copy_test_timeout_ms * max(len(node_list), 1)
        self._copy_test_timer.start(timeout)

    def _on_copy_test_timeout(self):
        """抄表测试超时处理"""
        if not self._is_copy_testing:
            return
        if self._copy_test_mode == "sequential":
            row, addr, proto, remaining = self._copy_test_queue.pop(0)
            remaining -= 1
            if remaining > 0:
                self._copy_test_queue.append((row, addr, proto, remaining))
            else:
                self._update_copy_test_result(row, addr)
            self._send_next_copy_test()
        else:
            self._copy_test_remaining_rounds -= 1
            if self._copy_test_remaining_rounds > 0:
                self._log(f"[并发抄表] 本轮超时，剩余{self._copy_test_remaining_rounds}轮")
                self._send_concurrent_copy()
            else:
                for row, addr, proto, _ in self._copy_test_queue:
                    self._update_copy_test_result(row, addr)
                self._is_copy_testing = False
                self._copy_test_queue = []
                self._log("[并发抄表] 超时，抄读结束")

    def _update_copy_test_result(self, row: int, addr: str):
        """更新抄读结果到表格"""
        stats = self._copy_test_stats.get(addr, {"sent": 0, "success": 0, "total": 0})
        sent = stats["sent"]
        success = stats["success"]
        total = stats["total"]
        rate = (success / total * 100) if total > 0 else 0
        result_text = f"发送{sent} 成功{success}/{total} ({rate:.0f}%)"
        self.table.setItem(row, 8, QTableWidgetItem(result_text))
        self._log(f"[抄读结果] {addr}: {result_text}")

    def _extract_src_addr_from_frame(self, frame: bytes) -> str:
        """从1376.2上行帧中提取源地址A1"""
        if len(frame) < 22 or frame[0] != 0x68:
            return ""
        comm_module = (frame[4] >> 2) & 0x01
        relay_level = (frame[4] >> 4) & 0x0F
        if comm_module == 0:
            return ""
        addr_start = 10
        src_addr_bytes = frame[addr_start:addr_start + 6][::-1]
        return src_addr_bytes.hex().upper()

    def _extract_inner_meter_addr(self, frame: bytes) -> str:
        """从AFN=13/F1上行帧的内层报文中提取电表地址"""
        try:
            table_data = self.gdw_parser.parse_to_table(frame)
        except Exception:
            return ""
        inner_frame = None
        for name, raw, parsed, comment, bs, be in table_data:
            if "报文内容" in name and "原始报文数据" in comment:
                try:
                    inner_frame = bytes.fromhex(raw.replace(" ", ""))
                except ValueError:
                    pass
                break
        if not inner_frame or len(inner_frame) < 10:
            return ""
        if inner_frame[0] == 0x68 and len(inner_frame) >= 7:
            addr_bytes = inner_frame[1:7][::-1]
            return addr_bytes.hex().upper()
        return ""

    def _start_version_query(self, rows: List[int], mode: str):
        """启动版本查询队列"""
        self._version_query_queue = []
        for row in rows:
            addr = self.table.item(row, 2).text().strip().zfill(12)
            self._version_query_queue.append((row, addr))
            # 清空对应模式的列
            col = 6 if mode == "simple" else 7
            self.table.setItem(row, col, QTableWidgetItem("查询中..."))
        self._version_query_mode = mode
        self._is_querying_version = True
        self._log(f"[版本查询] 开始查询 {len(rows)} 个从节点，模式={mode}")
        self._send_next_version_query()

    def _send_next_version_query(self):
        """发送队列中的下一个版本查询"""
        if not self._version_query_queue:
            self._is_querying_version = False
            self._log("[版本查询] 所有从节点查询完成")
            return
        row, addr = self._version_query_queue[0]
        self._version_query_current_row = row
        self._version_query_current_addr = addr

        seq = self._gdw_seq_counter
        self._gdw_seq_counter = (self._gdw_seq_counter + 1) & 0xFF
        self.gdw_seq.setText(str(self._gdw_seq_counter))

        if self._version_query_mode == "simple":
            # AFN=03 F1 厂商代码和版本信息
            info_config = {
                "dir": self.gdw_dir.currentData(),
                "prm": self.gdw_prm.currentData(),
                "通信方式": 4,  # 双模
                "报文序列号": seq,
                "通信模块标识": 1,  # 对从节点
                "中继级别": 0,
                "路由标识": 0,
                "附属节点标识": 0,
                "冲突检测": 0,
                "纠错编码标识": 0,
                "信道标识": 0,
                "预计应答字节数": 0,
                "通信速率": 0,
                "速率单位标识": 0,
            }
            frame = self.gdw_generator.generate_frame(
                0x03, 1, {}, info_config,
                src_addr=self.gdw_src_addr.text().strip(),
                dst_addr=addr
            )
            frame_hex = frame.hex().upper()
            self._send_hex(frame_hex, f"查询从节点版本 [{addr}] seq={seq}")
        else:
            # AFN=13 F1 扩展监控从节点 + DLT645内层
            inner_frame = self._build_detail_version_inner_frame(addr)
            field_values = {
                "通信协议类型": 2,  # DL/T 645-2007
                "通信延时相关性标志": 0,
                "从节点附属节点数量": 0,
                "报文长度": len(inner_frame),
                "报文内容": inner_frame.hex().upper()
            }
            info_config = {
                "dir": self.gdw_dir.currentData(),
                "prm": self.gdw_prm.currentData(),
                "通信方式": 4,  # 双模
                "报文序列号": seq,
                "通信模块标识": 1,  # 对从节点
                "中继级别": 0,
                "路由标识": 0,
                "附属节点标识": 0,
                "冲突检测": 0,
                "纠错编码标识": 0,
                "信道标识": 0,
                "预计应答字节数": 0,
                "通信速率": 0,
                "速率单位标识": 0,
            }
            frame = self.gdw_generator.generate_frame(
                0x13, 1, field_values, info_config,
                src_addr=self.gdw_src_addr.text().strip(),
                dst_addr=addr
            )
            frame_hex = frame.hex().upper()
            self._send_hex(frame_hex, f"查询从节点详细版本 [{addr}]")

        # 启动超时定时器
        from PySide6.QtCore import QTimer
        if self._version_query_timer is None:
            self._version_query_timer = QTimer(self)
            self._version_query_timer.setSingleShot(True)
            self._version_query_timer.timeout.connect(self._on_version_timeout)
        self._version_query_timer.start(self._version_query_timeout_ms)

    def _build_detail_version_inner_frame(self, addr: str) -> bytes:
        """构建查询详细版本信息的内层DLT645帧（基于用户参考报文模板）"""
        # 参考报文内层: 68 99 99 99 99 99 99 68 11 3C [60字节数据] B2 16
        addr_bytes = bytes.fromhex(addr)
        # 60字节数据域（使用参考报文中的原始数据域）
        data_field = bytes([
            0x34, 0x10, 0x33, 0x32, 0x33, 0x4E, 0x34, 0x33, 0x35, 0x33,
            0x36, 0x33, 0x37, 0x33, 0x38, 0x33, 0x39, 0x33, 0x3C, 0x33,
            0x74, 0x33, 0x75, 0x33, 0x76, 0x33, 0x77, 0x33, 0x78, 0x33,
            0x79, 0x33, 0x7A, 0x33, 0x7B, 0x33, 0x7C, 0x33, 0x7D, 0x33,
            0x7E, 0x33, 0x7F, 0x33, 0x80, 0x33, 0x81, 0x33, 0x87, 0x33,
            0x88, 0x33, 0x89, 0x33, 0x8A, 0x33, 0x8B, 0x33, 0x91, 0x33
        ])
        data_len = len(data_field)
        # 构建DLT645帧
        frame = bytearray()
        frame.append(0x68)
        frame.extend(addr_bytes[::-1])  # DLT645地址低字节在前
        frame.append(0x68)
        frame.append(0x11)  # 控制码: 读数据
        frame.append(data_len)
        frame.extend(data_field)
        # 计算校验和
        cs = sum(frame) & 0xFF
        frame.append(cs)
        frame.append(0x16)
        return bytes(frame)

    def _on_version_timeout(self):
        """版本查询超时处理"""
        if not self._is_querying_version or not self._version_query_queue:
            return
        row, addr = self._version_query_queue.pop(0)
        col = 6 if self._version_query_mode == "simple" else 7
        self.table.setItem(row, col, QTableWidgetItem("超时"))
        self._log(f"[版本查询] 从节点 {addr} 查询超时")
        self._send_next_version_query()

    def _on_init_task(self):
        frame = self._build_south_frame((0xE8, 0x02, 0x01, 0x03), {})
        self._send_hex(frame.hex().upper(), "初始化任务")

    def _on_start_task(self):
        frame = self._build_south_frame((0xE8, 0x02, 0x02, 0x08), {})
        self._send_hex(frame.hex().upper(), "启动任务")

    def _on_pause_task(self):
        frame = self._build_south_frame((0xE8, 0x02, 0x02, 0x09), {})
        self._send_hex(frame.hex().upper(), "暂停任务")

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Table context menu
    # ------------------------------------------------------------------
    def _on_table_context_menu(self, pos):
        menu = QMenu(self)
        add_action = menu.addAction("添加电能表")
        del_action = menu.addAction("删除电能表")
        menu.addSeparator()
        select_all_action = menu.addAction("批量选中")
        deselect_all_action = menu.addAction("批量反选")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == add_action:
            self._on_add_meter_dialog()
        elif action == del_action:
            self._on_delete_meters_from_table()
        elif action == select_all_action:
            self._set_all_checkboxes(True)
        elif action == deselect_all_action:
            self._set_all_checkboxes(False)

    def _on_add_meter_dialog(self):
        dialog = AddMeterDialog(self)
        while True:
            rc = dialog.exec()
            if rc == QDialog.DialogCode.Rejected:
                break
            info = dialog.get_meter_info()
            self._add_meter_to_table(info)
            self._log(f"[本地] 添加电能表: {info['meter_id']}")
            if rc == QDialog.DialogCode.Accepted or not dialog.continuous_cb.isChecked():
                break
            dialog.clear_fields()

    def _add_meter_to_table(self, info: Dict[str, Any]):
        row = self.table.rowCount()
        self.table.insertRow(row)

        chk_item = QTableWidgetItem()
        chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        chk_item.setCheckState(Qt.CheckState.Unchecked)
        self.table.setItem(row, 0, chk_item)

        self.table.setItem(row, 1, QTableWidgetItem(str(row + 1)))
        self.table.setItem(row, 2, QTableWidgetItem(info["meter_id"]))
        self.table.setItem(row, 3, QTableWidgetItem(info.get("protocol", "-")))
        self.table.setItem(row, 4, QTableWidgetItem(info.get("phase", "-")))
        status = info.get("status", "本地添加")
        self.table.setItem(row, 5, QTableWidgetItem(status))
        self.table.setItem(row, 6, QTableWidgetItem(""))
        self.table.setItem(row, 7, QTableWidgetItem(""))
        self.table.setItem(row, 8, QTableWidgetItem(""))
        self.table.setItem(row, 9, QTableWidgetItem(""))

        self._node_data.append(info)
        self._save_archive()

    def _on_delete_meters_from_table(self):
        checked = self._get_checked_rows()
        if not checked:
            QMessageBox.warning(self, "警告", "请先在表格中勾选要删除的电能表！")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定从表格中删除选中的 {len(checked)} 个电能表？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        # delete from bottom to top to keep indices valid
        for row in sorted(checked, reverse=True):
            self.table.removeRow(row)
            if 0 <= row < len(self._node_data):
                self._node_data.pop(row)
        # renumber rows
        for row in range(self.table.rowCount()):
            self.table.item(row, 1).setText(str(row + 1))
        self._save_archive()
        self._log(f"[本地] 从表格删除 {len(checked)} 个电能表")

    def _set_all_checkboxes(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(state)

    def _get_checked_rows(self) -> List[int]:
        rows = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                rows.append(row)
        return rows

    def _add_table_row(self, idx: int, addr: str, proto: str, phase: str, status: str):
        row = self.table.rowCount()
        self.table.insertRow(row)

        chk_item = QTableWidgetItem()
        chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        chk_item.setCheckState(Qt.CheckState.Unchecked)
        self.table.setItem(row, 0, chk_item)

        self.table.setItem(row, 1, QTableWidgetItem(str(idx)))
        self.table.setItem(row, 2, QTableWidgetItem(addr))
        self.table.setItem(row, 3, QTableWidgetItem(proto))
        self.table.setItem(row, 4, QTableWidgetItem(phase))
        self.table.setItem(row, 5, QTableWidgetItem(status))
        self.table.setItem(row, 6, QTableWidgetItem(""))
        self.table.setItem(row, 7, QTableWidgetItem(""))
        self.table.setItem(row, 8, QTableWidgetItem(""))
        self.table.setItem(row, 9, QTableWidgetItem(""))

    def _clear_table(self):
        self.table.setRowCount(0)
        self._node_data.clear()
        self._save_archive()

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------
    def _on_frame_received(self, frame: bytes):
        if self.protocol_mode == "south":
            self._handle_south_response(frame)
        else:
            self._handle_gdw_response(frame)

    def _handle_south_response(self, frame: bytes):
        if len(frame) < 8 or frame[0] != 0x68:
            return
        # 用解析器获取DI和AFN信息
        try:
            result = self.parser.parse(frame)
        except Exception:
            return

        user_data = self._extract_south_user_data(frame)
        if not user_data:
            return

        di_info = result.get("用户数据区", {}).get("数据标识", {})
        di_key = (
            di_info.get("DI3", 0),
            di_info.get("DI2", 0),
            di_info.get("DI1", 0),
            di_info.get("DI0", 0)
        )
        afn = di_info.get("AFN", result.get("用户数据区", {}).get("应用功能码", 0))

        # 查询从节点数量响应
        if di_key == (0xE8, 0x00, 0x03, 0x05):
            if len(user_data) >= 2:
                count = int.from_bytes(user_data[0:2], 'little')
                self.status_label.setText(f"从节点总数量: {count}")
                self._log(f"[应答] 从节点总数量: {count}")
            return

        # 返回查询从节点信息 (E8 04 03 06)
        if di_key == (0xE8, 0x04, 0x03, 0x06):
            if len(user_data) < 3:
                return
            total = int.from_bytes(user_data[0:2], 'little')
            count = user_data[2]
            self._clear_table()
            offset = 3
            for i in range(count):
                if offset + 6 > len(user_data):
                    break
                addr_bytes = user_data[offset:offset+6]
                addr_str = addr_bytes[::-1].hex().upper()  # reverse for display
                info = {
                    "meter_id": addr_str, "module_id": "",
                    "comm_type": "电力载波", "protocol": "-",
                    "phase": "-", "meter_type": "电能表",
                    "remark": "", "status": "在线"
                }
                self._add_meter_to_table(info)
                offset += 6
            self.status_label.setText(f"从节点总数量: {total}, 本次应答: {count}")
            self._log(f"[应答] 返回查询从节点信息: 总数{total}, 本次{count}")
            return

        # 确认/否认响应 (AFN=00)
        if afn == 0x00:
            self._log("[应答] 确认/否认")
            return

        # 通用日志
        self._log(f"[应答] 收到上行帧 DI={di_key[0]:02X} {di_key[1]:02X} {di_key[2]:02X} {di_key[3]:02X}")

    def _handle_gdw_response(self, frame: bytes):
        try:
            table_data = self.gdw_parser.parse_to_table(frame)
        except Exception:
            return

        # 提取AFN/FN（直接从字节解析，避免字符串转换错误）
        afn, fn = self._extract_gdw_afn_fn(frame)

        # 查询从节点数量 AFN=10 F1
        if afn == 0x10 and fn == 1:
            for name, raw, parsed, comment, bs, be in table_data:
                if "从节点总数量" in name or "从节点数量" in name:
                    self.status_label.setText(f"从节点总数量: {parsed}")
                    self._log(f"[应答] 从节点总数量: {parsed}")
                    return
            return

        # 查询从节点信息 AFN=10 F2
        if afn == 0x10 and fn == 2:
            self._clear_table()
            row_idx = 1
            addr = None
            phase = "-"
            proto = "-"
            for name, raw, parsed, comment, bs, be in table_data:
                if "从节点" in name and "地址" in name:
                    if addr is not None:
                        info = {
                            "meter_id": addr, "module_id": "",
                            "comm_type": "电力载波", "protocol": proto,
                            "phase": phase, "meter_type": "电能表",
                            "remark": "", "status": "在线"
                        }
                        self._add_meter_to_table(info)
                        row_idx += 1
                    addr = str(parsed)
                    phase = "-"
                    proto = "-"
                elif "相位" in name or "相序" in name:
                    phase = str(parsed)
                elif "通信协议" in name or "协议类型" in name:
                    proto = str(parsed)
            if addr is not None:
                info = {
                    "meter_id": addr, "module_id": "",
                    "comm_type": "电力载波", "protocol": proto,
                    "phase": phase, "meter_type": "电能表",
                    "remark": "", "status": "在线"
                }
                self._add_meter_to_table(info)
            self._log(f"[应答] 返回查询从节点信息, 共{row_idx-1}条")
            return

        # 抄表测试响应 AFN=13 F1 (点抄) / AFN=F1 F1 (并发)
        if self._is_copy_testing:
            if afn == 0x13 and fn == 1 and self._copy_test_mode == "sequential":
                self._handle_copy_test_response(frame, table_data)
                return
            if afn == 0xF1 and fn == 1 and self._copy_test_mode == "concurrent":
                self._handle_concurrent_copy_response(frame, table_data)
                return

        # 版本查询响应 AFN=03 F1
        if afn == 0x03 and fn == 1 and self._is_querying_version and self._version_query_mode == "simple":
            self._handle_version_response_simple(frame, table_data)
            return

        # 详细版本查询响应 AFN=13 F1/F2
        if afn == 0x13 and fn in (1, 2) and self._is_querying_version and self._version_query_mode == "detail":
            self._handle_version_response_detail(frame)
            return

        # 添加/删除从节点响应 AFN=00
        if afn == 0x00:
            self._log("[应答] 确认/否认")
            return

        self._log(f"[应答] 收到上行帧 AFN={afn:02X} F{fn}")

    def _handle_version_response_simple(self, frame: bytes, table_data: list):
        """处理AFN=03 F1版本查询响应"""
        if self._version_query_timer:
            self._version_query_timer.stop()
        vendor = ""
        chip = ""
        ver_date = ""
        ver = ""
        for name, raw, parsed, comment, bs, be in table_data:
            if "厂商代码" in name:
                vendor = str(parsed)
            elif "芯片代码" in name:
                chip = str(parsed)
            elif "版本日期" in name:
                ver_date = str(parsed)
            elif "版本" == name.strip() or "  版本" in name:
                ver = str(parsed)
        parts = [f"厂商:{vendor}", f"芯片:{chip}"]
        if ver_date:
            parts.append(f"日期:{ver_date}")
        parts.append(f"版本:{ver}")
        result_text = " ".join(parts)
        if not vendor and not ver:
            result_text = "无版本数据"
        self._set_version_query_result(result_text, col=6)

    def _handle_version_response_detail(self, frame: bytes):
        """处理AFN=13 F1/F2详细版本查询响应"""
        if self._version_query_timer:
            self._version_query_timer.stop()
        try:
            table_data = self.gdw_parser.parse_to_table(frame)
        except Exception:
            self._set_version_query_result("解析失败")
            return
        # 提取内层DLT645报文
        inner_frame = None
        for name, raw, parsed, comment, bs, be in table_data:
            if "报文内容" in name and "原始报文数据" in comment:
                try:
                    inner_frame = bytes.fromhex(raw.replace(" ", ""))
                except ValueError:
                    pass
                break
        if not inner_frame:
            self._set_version_query_result("无内层数据")
            return
        # 解析内层DLT645帧
        try:
            dlt_parser = DLT645Parser()
            dlt_result = dlt_parser.parse(inner_frame)
            if dlt_result.get('valid'):
                di_desc = dlt_result.get('di_desc', '未知')
                # 提取数据域的原始字节（已减0x33）
                data = dlt_result.get('data', b'')
                if data and di_desc == "未知数据标识":
                    # 尝试按LME信息条目格式解析（DI=0xFF00DD01等自定义DI）
                    try:
                        entries = parse_lme_info_entries(data)
                        if entries:
                            result_text = format_lme_info_summary(entries)
                        else:
                            result_text = f"DI:{di_desc} 数据:{data.hex().upper()}"
                    except Exception as e:
                        result_text = f"DI:{di_desc} 数据:{data.hex().upper()} 解析异常:{e}"
                elif data:
                    result_text = f"DI:{di_desc} 数据:{data.hex().upper()}"
                else:
                    result_text = f"DI:{di_desc}"
            else:
                result_text = f"DLT645无效帧:{dlt_result.get('error', '未知错误')}"
        except Exception as e:
            result_text = f"DLT645解析异常:{e}"
        self._set_version_query_result(result_text, col=7)

    def _handle_copy_test_response(self, frame: bytes, table_data: list):
        """处理点抄测试响应 (AFN=13 F1)"""
        if self._copy_test_timer:
            self._copy_test_timer.stop()
        if not self._copy_test_queue:
            return
        row, addr, proto, remaining = self._copy_test_queue.pop(0)
        # 尝试从内层报文判断是否成功
        success = self._parse_copy_inner_success(frame, proto)
        if success:
            self._copy_test_stats[addr]["success"] += 1
        remaining -= 1
        if remaining > 0:
            self._copy_test_queue.insert(0, (row, addr, proto, remaining))
        else:
            self._update_copy_test_result(row, addr)
        self._send_next_copy_test()

    def _handle_concurrent_copy_response(self, frame: bytes, table_data: list):
        """处理并发抄表响应 (AFN=F1 F1)"""
        # 从上行帧提取源地址A1
        src_addr = self._extract_src_addr_from_frame(frame)
        if not src_addr:
            # 尝试从内层报文提取电表地址
            src_addr = self._extract_inner_meter_addr(frame)
        if not src_addr:
            return
        # 查找匹配的电表并统计
        found = False
        for row, addr, proto, _ in self._copy_test_queue:
            if addr == src_addr:
                self._copy_test_stats[addr]["success"] += 1
                self._copy_test_concurrent_responses[addr] = self._copy_test_concurrent_responses.get(addr, 0) + 1
                found = True
                break
        if not found:
            return
        # 检查本轮是否所有电表都已响应
        all_responded = all(
            self._copy_test_concurrent_responses.get(addr, 0) > 0
            for _, addr, _, _ in self._copy_test_queue
        )
        if all_responded:
            if self._copy_test_timer:
                self._copy_test_timer.stop()
            self._copy_test_remaining_rounds -= 1
            if self._copy_test_remaining_rounds > 0:
                self._log(f"[并发抄表] 本轮完成，剩余{self._copy_test_remaining_rounds}轮")
                self._send_concurrent_copy()
            else:
                for row, addr, proto, _ in self._copy_test_queue:
                    self._update_copy_test_result(row, addr)
                self._is_copy_testing = False
                self._copy_test_queue = []
                self._log("[并发抄表] 所有轮次完成")

    def _parse_copy_inner_success(self, frame: bytes, proto: str) -> bool:
        """从AFN=13 F1上行帧中提取内层报文并判断是否抄读成功"""
        try:
            table_data = self.gdw_parser.parse_to_table(frame)
        except Exception:
            return False
        inner_frame = None
        for name, raw, parsed, comment, bs, be in table_data:
            if "报文内容" in name and "原始报文数据" in comment:
                try:
                    inner_frame = bytes.fromhex(raw.replace(" ", ""))
                except ValueError:
                    pass
                break
        if not inner_frame or len(inner_frame) < 10:
            return False
        # DLT645: 控制码应答位bit3=1表示成功 (0x91等)
        if "645" in proto:
            if inner_frame[0] == 0x68 and len(inner_frame) >= 8:
                ctrl = inner_frame[8]
                return (ctrl & 0x80) != 0
        # DLT698: 看APDU第一个字节是否为应答类型
        if "698" in proto:
            if inner_frame[0] == 0x68 and len(inner_frame) > 14:
                apdu_offset = 14
                if apdu_offset < len(inner_frame):
                    apdu_tag = inner_frame[apdu_offset]
                    return (apdu_tag & 0x80) != 0
        return False

    def _set_version_query_result(self, text: str, col: int = 6):
        """设置当前查询行的回读信息并继续下一个"""
        if not self._version_query_queue:
            self._is_querying_version = False
            return
        row, addr = self._version_query_queue.pop(0)
        self.table.setItem(row, col, QTableWidgetItem(text))
        self._log(f"[版本查询] 从节点 {addr} 结果: {text}")
        self._send_next_version_query()

    @staticmethod
    def _extract_gdw_afn_fn(frame: bytes) -> Tuple[Optional[int], Optional[int]]:
        """从国网帧中直接提取 AFN 和 FN"""
        if len(frame) < 13 or frame[0] != 0x68:
            return None, None
        comm_module_flag = (frame[4] >> 2) & 0x01
        relay_level = (frame[4] >> 4) & 0x0F
        if comm_module_flag:
            addr_len = 12 + 6 * relay_level
        else:
            addr_len = 0
        afn_pos = 4 + 6 + addr_len
        if afn_pos + 3 > len(frame) - 2:
            return None, None
        afn = frame[afn_pos]
        dt1 = frame[afn_pos + 1]
        dt2 = frame[afn_pos + 2]
        fn = None
        for i in range(8):
            if dt1 & (1 << i):
                fn = dt2 * 8 + i + 1
                break
        return afn, fn

    @staticmethod
    def _extract_south_user_data(frame: bytes) -> bytes:
        if len(frame) < 8 or frame[0] != 0x68:
            return b""
        length = int.from_bytes(frame[1:3], 'little')
        user_data_len = length - 6
        return frame[4:4+user_data_len]

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def _on_serial_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.serial_log.append(f"[{ts}] {msg}")
        scrollbar = self.serial_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _log(self, msg: str):
        self._on_serial_log(msg)
