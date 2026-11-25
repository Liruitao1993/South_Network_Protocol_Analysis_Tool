"""档案管理Widget

提供从节点（电能表）白名单档案管理界面，支持南网协议和国网协议。
包含档案表格、操作按钮、串口交互和响应解析。
"""

from atomic_io import atomic_write_json

import json
import struct
import time
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QTextEdit, QMessageBox, QSplitter, QMenu, QCheckBox, QGridLayout,
    QFileDialog, QTabWidget, QFormLayout, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from send_frame_lib import ProtocolFrameGenerator
from gdw_send_frame_lib import GDWFrameGenerator
from protocol_parser import ProtocolFrameParser
from gdw10376_parser import GDW10376Parser
from dlt645_parser import DLT645Parser
from lme_info_entry_parser import (
    parse_lme_info_entries,
    format_lme_info_summary,
    format_lme_info_detail,
)
import archive_copy_items as C
from gui_utils import ZoomableTableWidget, set_btn_icon
from app_paths import data_path

ARCHIVE_FILE = str(data_path("archive_data.json"))

#: 「查询从节点信息」（10H F2）每页请求条数 —— 被测模块单帧实测上限就是 20 条
#: （现场请求 50 只回 20，30 个节点永远只显示 20 个），故按 20 分页、按响应推进。
NODE_INFO_PAGE_SIZE = 20
#: 单页等待上限（ms）：超时即停止翻页但保留已收节点，不无限等待
NODE_INFO_PAGE_TIMEOUT_MS = 5000
#: 翻页页数上限（防御设备一直回「还有更多」）
NODE_INFO_MAX_PAGES = 200


def _fmt_elapsed(seconds: float) -> str:
    """耗时格式化：<1s 显示毫秒，<60s 显示秒，否则 分+秒"""
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "-"
    if seconds <= 0:
        return "0ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    return f"{minutes}分{seconds - minutes * 60:.1f}秒"



def _spin_width_for(digits: int, minimum: int = 3, line_edit=None) -> int:
    """数字输入框按「位数」算宽度（字体实测数字宽 + 内边距 + 一位余量）。

    为什么不用固定宽度：现场把「抄读次数」填成 1000 时只显示成 `100`（QLineEdit
    固定 40px 装不下 4~5 位数字 + 内边距），看起来像输入没生效。这里按位数给宽度，
    并留出一位余量（编辑时先多显示一位，光标不会把数字挤出可视区）。
    """
    digits = max(int(minimum), int(digits) + 1)
    per_digit = 9
    try:
        metrics = (line_edit.fontMetrics() if line_edit is not None else None)
        if metrics is None:
            from PySide6.QtGui import QFontMetrics
            metrics = QFontMetrics(QFont())
        per_digit = max(7, metrics.horizontalAdvance("0"))
    except Exception:                                      # noqa: BLE001
        per_digit = 9
    # +16：左右内边距与光标留白
    return max(44, per_digit * digits + 16)


def _field_triple(row) -> Tuple[str, str, str]:
    """把解析器的「字段行」规整成 ``(名称, 原始值, 解析值)``。

    **各解析器的行长度并不统一**（这是本次崩溃的根因）：645 的 fields 常见
    3 元组 ``(名称, 原始值, 解析值)``，带说明的行是 4 元组；而 698/国网等用
    6 元组 ``(名称, 原始值, 解析值, 说明, 起, 止)``。以前这里硬解 6 元组，
    只要来一行 3 元组就直接 ``ValueError: not enough values to unpack``，
    整个「抄读测试」收到应答就崩。

    这里按位取值、缺位补空串，任何长度都不抛异常。
    """
    try:
        cells = tuple(row)
    except TypeError:
        return str(row), "", ""
    name = str(cells[0]) if len(cells) > 0 and cells[0] is not None else ""
    raw = str(cells[1]) if len(cells) > 1 and cells[1] is not None else ""
    parsed = str(cells[2]) if len(cells) > 2 and cells[2] is not None else ""
    return name, raw, parsed


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


class CopyItemsDialog(QDialog):
    """抄读数据项配置（点抄 / 并发抄表用）

    三个页签按归属分开：645 表数据项 / 698 表数据项 / STA 模块数据项。
    模块数据项由 STA 模块自己应答（不用电表参与），对 698 表按国网《附件1 V3.42》
    的 `EB55XXXX` 规则映射成 OAD。
    """

    def __init__(self, parent=None, items=None):
        super().__init__(parent)
        self.setWindowTitle("抄读数据项配置")
        self.setMinimumSize(760, 460)
        self._items = [dict(it) for it in (items if items is not None else C.load_items())]
        self._setup_ui()
        self._reload()

    # ---- UI ----
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        hint = QLabel(
            "勾选的项就是点抄时要抄的数据项：645 表按 DI 逐项下发，698 表把多项合成一帧 "
            "GetRequestNormalList。「从节点版本信息」是**公司扩展协议**（与「查询从节点详细版本」"
            "同一份报文，DI=FF00DD01），STA 模块自己应答，**不区分表协议**；"
            "其它 STA 模块项（EB03xxxx）也由模块应答。并发抄表每块表只能带一个报文内容，取第一项。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666;font-size:12px;")
        layout.addWidget(hint)

        self.tabs = QTabWidget()
        self._tables: Dict[str, QTableWidget] = {}
        for proto in (C.PROTO_MODULE, C.PROTO_645, C.PROTO_698):
            table = QTableWidget(0, 5)
            table.setHorizontalHeaderLabels(["选择", "数据项名称", "标识", "698 标识 / 适用", "备注"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(0, 46)
            table.setColumnWidth(1, 190)
            table.setColumnWidth(2, 100)
            table.setColumnWidth(3, 130)
            table.verticalHeader().hide()
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setAlternatingRowColors(True)
            self._tables[proto] = table
            self.tabs.addTab(table, C.PROTO_LABELS[proto])
        layout.addWidget(self.tabs, 1)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("新增自定义项…")
        set_btn_icon(self.add_btn, "add")
        self.add_btn.clicked.connect(self._on_add_custom)
        btn_row.addWidget(self.add_btn)

        self.del_btn = QPushButton("删除选中项")
        set_btn_icon(self.del_btn, "delete")
        self.del_btn.clicked.connect(self._on_delete_current)
        btn_row.addWidget(self.del_btn)

        btn_row.addStretch()
        self.restore_btn = QPushButton("恢复内置默认")
        set_btn_icon(self.restore_btn, "refresh")
        self.restore_btn.clicked.connect(self._on_restore_defaults)
        btn_row.addWidget(self.restore_btn)
        layout.addLayout(btn_row)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._on_accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _reload(self):
        for proto, table in self._tables.items():
            rows = [it for it in self._items if it["proto"] == proto]
            table.setRowCount(len(rows))
            for r, it in enumerate(rows):
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Checked if it["enabled"] == "1"
                                  else Qt.CheckState.Unchecked)
                table.setItem(r, 0, chk)
                table.setItem(r, 1, QTableWidgetItem(it["name"]))
                table.setItem(r, 2, QTableWidgetItem(it["di"] or it["oad"]))
                mapping = ""
                if it.get("kind") == C.KIND_MODULE_VERSION:
                    mapping = "不区分协议（645 帧）"
                elif it.get("kind") == C.KIND_MODULE_QUERY:
                    mapping = f"不区分协议（645 帧 / {len(it.get('entries') or [])} 条）"
                elif proto == C.PROTO_MODULE:
                    mapping = it.get("oad") or C.module_di_to_oad(it["di"])
                elif it.get("oad"):
                    mapping = it["oad"]
                table.setItem(r, 3, QTableWidgetItem(mapping))
                table.setItem(r, 4, QTableWidgetItem(it.get("note", "")))
                table.item(r, 4).setToolTip(it.get("note", ""))
            table.resizeColumnToContents(4)

    # ---- 操作 ----
    def _collect(self):
        """把表里的勾选状态写回 self._items"""
        out = []
        for proto, table in self._tables.items():
            rows = [it for it in self._items if it["proto"] == proto]
            for r, it in enumerate(rows):
                item = table.item(r, 0)
                it = dict(it)
                it["enabled"] = "1" if (item and item.checkState() == Qt.CheckState.Checked) else "0"
                out.append(it)
        return out

    def _on_add_custom(self):
        proto = C.PROTO_698 if self.tabs.currentIndex() == 2 else (
            C.PROTO_645 if self.tabs.currentIndex() == 1 else C.PROTO_MODULE)
        dialog = QDialog(self)
        dialog.setWindowTitle("新增自定义数据项")
        form = QFormLayout(dialog)
        name_edit = QLineEdit()
        id_edit = QLineEdit()
        id_edit.setPlaceholderText("645/模块：8 位 DI（如 EB030303）；698：8 位 OAD（如 00100200）")
        proto_combo = QComboBox()
        proto_combo.addItem(C.PROTO_LABELS[C.PROTO_645], C.PROTO_645)
        proto_combo.addItem(C.PROTO_LABELS[C.PROTO_698], C.PROTO_698)
        proto_combo.addItem(C.PROTO_LABELS[C.PROTO_MODULE], C.PROTO_MODULE)
        proto_combo.setCurrentIndex(proto_combo.findData(proto))
        form.addRow("名称：", name_edit)
        form.addRow("归属：", proto_combo)
        form.addRow("标识：", id_edit)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        form.addRow(box)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        p = proto_combo.currentData()
        raw = {"name": name_edit.text().strip(), "proto": p, "enabled": "1"}
        if p == C.PROTO_698:
            raw["oad"] = id_edit.text().strip().upper()
        else:
            raw["di"] = id_edit.text().strip().upper()
        item = C.normalize_item(raw)
        if not item:
            QMessageBox.warning(self, "格式不对",
                                "标识必须是 8 位十六进制（645/模块填 DI，698 填 OAD）。")
            return
        self._items = self._collect()
        self._items.append(item)
        self._reload()

    def _on_delete_current(self):
        proto = (C.PROTO_MODULE, C.PROTO_645, C.PROTO_698)[self.tabs.currentIndex()]
        table = self._tables[proto]
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "先在表里选中要删除的一行。")
            return
        if QMessageBox.question(self, "确认删除", "删除这个数据项？") != QMessageBox.StandardButton.Yes:
            return
        self._items = self._collect()
        rows = [it for it in self._items if it["proto"] == proto]
        target = rows[row]
        self._items = [it for it in self._items if it is not target
                       and not (it["proto"] == target["proto"] and it["name"] == target["name"])]
        self._reload()

    def _on_restore_defaults(self):
        if QMessageBox.question(self, "确认", "恢复内置默认数据项（覆盖当前勾选）？") \
                != QMessageBox.StandardButton.Yes:
            return
        self._items = [C.normalize_item(dict(it)) for it in C.BUILTIN_ITEMS]
        self._items = [it for it in self._items if it]
        self._reload()

    def _on_accept(self):
        items = self._collect()
        if not C.enabled_items(items):
            QMessageBox.warning(self, "至少勾一项", "点抄需要至少勾选一个数据项。")
            return
        self._items = items
        try:
            C.save_items(items)
        except Exception as e:                      # noqa: BLE001
            QMessageBox.warning(self, "保存失败", f"数据项配置没写进磁盘：{e}")
            return
        self.accept()

    def result_items(self):
        return self._items


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
        self._version_query_queue: List[Tuple[int, str, int]] = []  # [(row, addr, 剩余次数), ...]
        self._version_query_mode: str = ""  # "simple" | "detail"
        self._version_query_timer = None
        self._version_query_timeout_ms: int = 5000  # 默认5秒超时
        self._is_querying_version: bool = False
        self._version_query_current_row: int = -1
        self._version_query_current_addr: str = ""
        self._version_query_attempts: int = 1
        self._version_query_stats: Dict[str, Dict[str, int]] = {}
        self._version_query_tooltip: str = ""  # 本帧的逐条明细，随结果一起写到单元格 tooltip
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
        self._copy_test_round_ok: Dict[str, bool] = {}   # 本轮「全部数据项都成功」标记
        self._copy_test_content: Dict[str, str] = {}     # 抄读内容（单行摘要）
        self._copy_test_content_full: Dict[str, str] = {}  # 抄读内容（逐条明细，tooltip）
        self._copy_items: List[Dict[str, str]] = C.load_items()  # 抄读数据项配置（点抄/并发共用）
        self._copy_test_started_at: float = 0.0      # 本轮抄读开始时刻（monotonic）
        self._copy_test_current_send_ts: float = 0.0  # 当前这一帧的发送时刻，用于算单次耗时
        self._copy_test_round_started_at: float = 0.0  # 并发抄表本轮发送时刻

        # 查询从节点信息：翻页状态（模块单帧只回 NODE_INFO_PAGE_SIZE 条，
        # 必须按响应里的「从节点总数量 / 本次应答数量」推进起始序号才能取全）
        self._node_query: Dict[str, Any] = {}
        self._node_query_timer = None

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
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels(["选择", "序号", "电表号/从节点地址", "电表协议", "相位/相序", "状态", "版本信息", "详细版本", "抄读结果", "其他信息", "抄读耗时", "抄读内容"])
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
        self.table.setColumnWidth(7, 420)
        self.table.setColumnWidth(8, 170)
        self.table.setColumnWidth(9, 120)
        self.table.setColumnWidth(10, 150)
        self.table.setColumnWidth(11, 320)
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
        # 宽度按位数自适应：固定 40px 时 4~5 位数字会被裁掉（现场填 1000 只看到 "100"）
        self.copy_count_input.setFixedWidth(
            _spin_width_for(3, line_edit=self.copy_count_input))
        self.copy_count_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.copy_count_input.setToolTip("每个表各抄读几次（点抄 / 并发 / 版本查询共用）")
        self.copy_count_input.textChanged.connect(
            lambda _t: self.copy_count_input.setFixedWidth(
                _spin_width_for(len(self.copy_count_input.text()),
                                line_edit=self.copy_count_input)))
        copy_config_layout.addWidget(self.copy_count_input)
        copy_config_layout.addWidget(QLabel("超时(ms):"))
        self.copy_timeout_input = QLineEdit("3000")
        # 同上：超时也可能填 4~5 位（如 10000ms）
        self.copy_timeout_input.setFixedWidth(
            _spin_width_for(4, line_edit=self.copy_timeout_input))
        self.copy_timeout_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.copy_timeout_input.textChanged.connect(
            lambda _t: self.copy_timeout_input.setFixedWidth(
                _spin_width_for(len(self.copy_timeout_input.text()),
                                line_edit=self.copy_timeout_input)))
        copy_config_layout.addWidget(self.copy_timeout_input)
        copy_config_layout.addWidget(QLabel("|"))
        self.copy_summary_label = QLabel("总成功率: -")
        self.copy_summary_label.setStyleSheet("color: #666; font-size: 12px;")
        self.copy_summary_label.setToolTip("本次抄读：成功次数 / 计划总次数")
        copy_config_layout.addWidget(self.copy_summary_label)
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
        set_btn_icon(self.add_node_btn, "add")
        self.add_node_btn.clicked.connect(self._on_add_nodes)
        archive_layout.addWidget(self.add_node_btn)

        self.del_node_btn = QPushButton("删除从节点")
        set_btn_icon(self.del_node_btn, "delete")
        self.del_node_btn.clicked.connect(self._on_delete_nodes)
        archive_layout.addWidget(self.del_node_btn)

        self.init_archive_btn = QPushButton("参数初始化")
        set_btn_icon(self.init_archive_btn, "settings")
        self.init_archive_btn.clicked.connect(self._on_init_archive)
        archive_layout.addWidget(self.init_archive_btn)

        archive_layout.addWidget(QLabel("|"))

        self.export_archive_btn = QPushButton("导出档案")
        set_btn_icon(self.export_archive_btn, "export")
        self.export_archive_btn.clicked.connect(self._on_export_archive)
        archive_layout.addWidget(self.export_archive_btn)

        self.import_archive_btn = QPushButton("导入档案")
        set_btn_icon(self.import_archive_btn, "open_file")
        self.import_archive_btn.clicked.connect(self._on_import_archive)
        archive_layout.addWidget(self.import_archive_btn)

        btn_layout.addWidget(archive_group)

        # 查询操作
        query_group = QGroupBox("查询操作")
        query_layout = QHBoxLayout(query_group)
        query_layout.setSpacing(6)
        query_layout.setContentsMargins(6, 4, 6, 4)

        self.query_count_btn = QPushButton("查询从节点数量")
        set_btn_icon(self.query_count_btn, "search")
        self.query_count_btn.clicked.connect(self._on_query_node_count)
        query_layout.addWidget(self.query_count_btn)

        self.query_info_btn = QPushButton("查询从节点信息")
        set_btn_icon(self.query_info_btn, "search")
        self.query_info_btn.clicked.connect(self._on_query_node_info)
        query_layout.addWidget(self.query_info_btn)

        self.query_version_btn = QPushButton("查询从节点版本")
        set_btn_icon(self.query_version_btn, "search")
        self.query_version_btn.clicked.connect(self._on_query_node_version)
        query_layout.addWidget(self.query_version_btn)

        self.query_version_detail_btn = QPushButton("查询从节点详细版本")
        set_btn_icon(self.query_version_detail_btn, "search")
        self.query_version_detail_btn.clicked.connect(self._on_query_node_version_detail)
        query_layout.addWidget(self.query_version_detail_btn)

        query_layout.addWidget(QLabel("|"))

        self.copy_items_btn = QPushButton("抄读数据项…")
        set_btn_icon(self.copy_items_btn, "settings")
        self.copy_items_btn.setToolTip("配置点抄/并发抄表要抄的数据项（含 STA 模块的从节点版本信息）")
        self.copy_items_btn.clicked.connect(self._on_config_copy_items)
        query_layout.addWidget(self.copy_items_btn)

        self.copy_test_btn = QPushButton("点抄测试")
        set_btn_icon(self.copy_test_btn, "down")
        self.copy_test_btn.clicked.connect(self._on_copy_test)
        query_layout.addWidget(self.copy_test_btn)

        self.concurrent_copy_btn = QPushButton("并发抄表")
        set_btn_icon(self.concurrent_copy_btn, "down")
        self.concurrent_copy_btn.clicked.connect(self._on_concurrent_copy)
        query_layout.addWidget(self.concurrent_copy_btn)

        self.stop_copy_btn = QPushButton("停止")
        set_btn_icon(self.stop_copy_btn, "stop")
        self.stop_copy_btn.setToolTip("中断正在进行的点抄/并发抄表（已发出的帧不回收）")
        self.stop_copy_btn.setEnabled(False)
        self.stop_copy_btn.clicked.connect(self._on_stop_copy_test)
        query_layout.addWidget(self.stop_copy_btn)

        self.clear_records_btn = QPushButton("清除记录")
        set_btn_icon(self.clear_records_btn, "delete")
        self.clear_records_btn.setToolTip("清空表格中的版本信息、详细版本、抄读结果列及本次统计")
        self.clear_records_btn.clicked.connect(self._on_clear_test_records)
        query_layout.addWidget(self.clear_records_btn)
        btn_layout.addWidget(query_group)

        # 任务操作
        task_group = QGroupBox("任务操作")
        task_layout = QHBoxLayout(task_group)
        task_layout.setSpacing(6)
        task_layout.setContentsMargins(6, 4, 6, 4)

        self.init_task_btn = QPushButton("初始化任务")
        set_btn_icon(self.init_task_btn, "apply")
        self.init_task_btn.clicked.connect(self._on_init_task)
        task_layout.addWidget(self.init_task_btn)

        self.start_task_btn = QPushButton("启动任务")
        set_btn_icon(self.start_task_btn, "play")
        self.start_task_btn.clicked.connect(self._on_start_task)
        task_layout.addWidget(self.start_task_btn)

        self.pause_task_btn = QPushButton("暂停任务")
        set_btn_icon(self.pause_task_btn, "pause")
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
        if not connected:
            # 串口断开：停掉翻页查询，别让定时器在「按钮已禁用」时继续触发
            self._stop_node_info_query()
            # 抄读/查询任务同理：串口断了没人应答，留着队列只会一路超时刷屏
            if self._is_copy_testing or self._is_querying_version:
                self._on_stop_copy_test()
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
        if mode != self.protocol_mode:
            self._stop_node_info_query()          # 两套响应对不上，别把旧翻页续下去
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
        self._stop_node_info_query()
        if hasattr(self, 'serial_log'):
            self.serial_log.clear()
        self._save_archive()

    # ------------------------------------------------------------------
    # JSON 持久化
    # ------------------------------------------------------------------
    def _save_archive(self):
        """将当前档案数据保存到 JSON 文件"""
        try:
            atomic_write_json(ARCHIVE_FILE, self._node_data)
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
            atomic_write_json(path, self._node_data)
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
        self._stop_node_info_query()          # 档案要清空重建，翻页查询就此打住
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
        """查询从节点信息（国网 10H F2）：**按响应里的总数翻页取全**。

        模块单帧最多回 `NODE_INFO_PAGE_SIZE` 条（现场请求 50 只回 20），
        所以必须：发第 1 页 → 读响应的「从节点总数量/本次应答数量」→ 用
        「上一页起始 + 本次数量」发下一页 → 直到取全 / 本次为 0 / 超时。
        """
        if self.protocol_mode == "south":
            frame = self._build_south_frame(
                (0xE8, 0x03, 0x03, 0x06),
                {"从节点起始序号": 0, "从节点数量": 50}
            )
            self._send_hex(frame.hex().upper(), "查询从节点信息")
            return
        self._start_node_info_query()

    # ------------------------------------------------------------------
    # 查询从节点信息：翻页状态机
    # ------------------------------------------------------------------
    def _start_node_info_query(self) -> None:
        """开始一轮翻页查询（会先停掉上一轮并清表）。"""
        self._stop_node_info_query()
        self._clear_table()                     # 清表只在这里做一次，翻页过程中只追加
        self._node_query = {"total": 0, "received": 0, "page_start": 1, "pages": 0,
                            "seen": set()}
        self.status_label.setText("从节点信息 0/…")
        self._send_node_info_page(1)

    def _send_node_info_page(self, start: int) -> None:
        """发送一页 `10H F2`：起始序号 = start，数量 = min(每页, 剩余)。"""
        state = self._node_query
        if not state:
            return
        total = int(state.get("total") or 0)
        received = int(state.get("received") or 0)
        count = NODE_INFO_PAGE_SIZE
        if total > received:
            count = min(NODE_INFO_PAGE_SIZE, total - received)
        try:
            frame = self._build_gdw_frame(
                0x10, 2, {"从节点起始序号": int(start), "从节点数量": int(count)})
        except Exception as exc:                # noqa: BLE001 - 组帧失败按查询失败收尾
            self._finish_node_info_query(f"组帧失败：{exc}", ok=False)
            return
        state["page_start"] = int(start)
        state["pages"] = int(state.get("pages") or 0) + 1
        self._send_hex(frame.hex().upper(),
                       f"查询从节点信息（第 {state['pages']} 页，起始 {start}，数量 {count}）")
        self._arm_node_query_timer()

    def _arm_node_query_timer(self) -> None:
        from PySide6.QtCore import QTimer

        if self._node_query_timer is None:
            self._node_query_timer = QTimer(self)
            self._node_query_timer.setSingleShot(True)
            self._node_query_timer.timeout.connect(self._on_node_query_timeout)
        self._node_query_timer.start(NODE_INFO_PAGE_TIMEOUT_MS)

    def _stop_node_info_query(self) -> None:
        """停掉翻页（停定时器 + 清状态），已收的数据保持不动。"""
        if self._node_query_timer is not None:
            self._node_query_timer.stop()
        self._node_query = {}

    def _on_node_query_timeout(self) -> None:
        state = self._node_query
        if not state:
            return
        received = int(state.get("received") or 0)
        total = int(state.get("total") or 0)
        page = int(state.get("pages") or 0)
        self._finish_node_info_query(
            f"第 {page} 页超时（已收 {received}/{total or '?'} 个从节点）", ok=False)

    def _finish_node_info_query(self, note: str, ok: bool = True) -> None:
        """收尾：打结论日志 + 状态栏，清状态（表格数据保留）。"""
        state = self._node_query
        self._stop_node_info_query()
        received = int(state.get("received") or 0)
        total = int(state.get("total") or 0)
        pages = int(state.get("pages") or 0)
        if ok and total:
            self.status_label.setText(f"从节点信息 {received}/{total}")
        elif received:
            self.status_label.setText(f"从节点信息 {received}/{total or '?'}（未取全）")
        else:
            self.status_label.setText("从节点信息：未取到数据")
        self._save_archive()
        self._log(f"[查询] 从节点信息{'完成' if ok else '中止'}：{note}"
                  f"（共 {received} 个 / 总数 {total or '?'}，{pages} 页）")

    def _handle_node_info_response(self, table_data: list) -> None:
        """处理一帧 `10H F2` 上行：追加本页节点，再决定是否继续翻页。"""
        total, count, nodes = self._extract_node_info_page(table_data)
        state = self._node_query
        if not state:
            # 不是本按钮触发的上报（如设备主动上报）：按老口径清表重铺
            self._clear_table()
            for node in nodes:
                self._add_meter_to_table(self._node_row(node), save=False)
            self._save_archive()
            self._log(f"[应答] 从节点信息 {count} 条（非翻页查询，已直接刷新）")
            return

        # 去重：设备可能跨页重复返回同一些节点（现场就出现过 20 条从第 11 个开始），
        # 重复的既不进表也不算进度，否则会「看起来收满了、其实缺号」。
        seen: set = state.setdefault("seen", set())
        added = 0
        for node in nodes:
            addr = str(node.get("addr") or "")
            if not addr or addr in seen:
                continue
            seen.add(addr)
            added += 1
            self._add_meter_to_table(self._node_row(node), save=False)

        if self._node_query_timer is not None:
            self._node_query_timer.stop()
        state["total"] = max(int(state.get("total") or 0), total)
        state["received"] = len(seen)
        received = int(state["received"])
        known_total = int(state.get("total") or 0)
        self.status_label.setText(f"从节点信息 {received}/{known_total or '…'}")
        self._log(f"[查询] 第 {state.get('pages')} 页：本次 {count} 条"
                  f"（新增 {added}），已收 {received}/{known_total or '?'}")

        if count <= 0:
            self._finish_node_info_query(
                f"设备本次返回 0 条，已收 {received}/{known_total or '?'}", ok=False)
            return
        if added == 0:
            # 本次全是重复节点：再按「起始+数量」问下去只会无限重复，就此收尾并告警
            self._finish_node_info_query(
                f"设备本次返回的 {count} 条与已收完全重复（设备可能不按起始序号翻页），"
                f"已收 {received}/{known_total or '?'}", ok=False)
            return
        if known_total and received >= known_total:
            self._finish_node_info_query(f"已取全 {received} 个从节点")
            return
        if int(state.get("pages") or 0) >= NODE_INFO_MAX_PAGES:
            self._finish_node_info_query(
                f"翻页达到上限 {NODE_INFO_MAX_PAGES} 页，已收 {received}", ok=False)
            return
        self._send_node_info_page(int(state["page_start"]) + count)

    @staticmethod
    def _extract_node_info_page(table_data: list) -> Tuple[int, int, List[Dict[str, Any]]]:
        """从 `10H F2` 解析行里取出 (总数, 本次数量, 节点明细)。

        节点明细字段来自解析器的 `从节点N地址` / `从节点N中继级别` /
        `从节点N侦听信号品质` / `从节点N相位` / `从节点N通信协议类型`
        （位域口径的**唯一实现**在 `gdw10376_parser._parse_slave_node_info_2byte`）。
        """
        total = 0
        count = 0
        nodes: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        for row in table_data or ():
            try:
                name, _raw, parsed = str(row[0]).strip(), row[1], row[2]
            except (TypeError, IndexError):
                continue
            if name == "从节点总数量":
                try:
                    total = int(str(parsed).split("(")[0])
                except (TypeError, ValueError):
                    total = 0
                continue
            if name == "本次应答数量":
                try:
                    count = int(str(parsed).split("(")[0])
                except (TypeError, ValueError):
                    count = 0
                continue
            if "从节点" not in name:
                continue
            if name.endswith("地址"):
                if current is not None:
                    nodes.append(current)
                current = {"addr": str(parsed or "").strip(),
                           "relay": None, "signal": None,
                           "phase": "-", "protocol": "-"}
                continue
            if current is None:
                continue
            value = str(parsed if parsed not in (None, "") else "-").strip()
            if name.endswith("中继级别"):
                current["relay"] = value
            elif name.endswith("侦听信号品质"):
                current["signal"] = value
            elif name.endswith("相位"):
                current["phase"] = value or "-"
            elif name.endswith("通信协议类型"):
                current["protocol"] = value or "-"
        if current is not None:
            nodes.append(current)
        if not count:
            count = len(nodes)
        return total, count, [n for n in nodes if n["addr"]]

    @staticmethod
    def _node_row(node: Dict[str, Any]) -> Dict[str, Any]:
        """节点明细 → 表格行字典（与本地添加的行保持同一形状）。"""
        relay = node.get("relay")
        signal = node.get("signal")
        extra_parts = []
        if relay not in (None, "", "-"):
            extra_parts.append(f"中继级别={relay}")
        if signal not in (None, "", "-"):
            extra_parts.append(f"侦听信号品质={signal}")
        return {
            "meter_id": node.get("addr", ""),
            "module_id": node.get("addr", ""),
            "comm_type": "电力载波",
            "protocol": node.get("protocol") or "-",
            "phase": node.get("phase") or "-",
            "meter_type": "电能表",
            "remark": "",
            "status": "在线",
            "relay": relay,
            "signal": signal,
            "extra": "，".join(extra_parts),
        }

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

    def _on_config_copy_items(self):
        """配置抄读数据项（点抄 / 并发抄表共用）"""
        dialog = CopyItemsDialog(self, self._copy_items)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._copy_items = dialog.result_items()
            chosen = C.enabled_items(self._copy_items)
            self._log("[抄读数据项] 已保存：" + "、".join(
                f"{it['name']}({it['di'] or it['oad']})" for it in chosen))

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
        """构建DLT645-2007读正向有功总电能帧（正确实现，待收编到 dlt645_frame_gen，见父任务 X1）"""
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
        self._copy_test_content = {}
        self._copy_test_content_full = {}
        self._copy_test_started_at = time.monotonic()
        self._copy_test_current_send_ts = time.monotonic()

        meters = []
        for row in rows:
            addr = self.table.item(row, 2).text().strip().zfill(12)
            proto = self.table.item(row, 3).text().strip()
            # sent=已完成轮次 / success=成功轮次 / total=计划轮次
            # elapsed_last=单轮抄读耗时 / elapsed_sum+elapsed_n=单轮均耗时
            self._copy_test_stats[addr] = {
                "sent": 0, "success": 0, "total": self._copy_test_count,
                "elapsed_last": 0, "elapsed_sum": 0, "elapsed_n": 0,
            }
            meters.append({
                "row": row, "addr": addr, "proto": proto,
                "frames": self._frames_for(addr, proto),
            })
            self.table.setItem(row, 8, QTableWidgetItem("抄读中..."))
            self.table.setItem(row, 10, QTableWidgetItem(""))
            self.table.setItem(row, 11, QTableWidgetItem(""))

        # **调度 = 按表号顺序抄 N 轮**：第 1 轮 表1→表N，第 2 轮 表1→表N，……
        # 队列项是「某表某一轮」的读任务（dict，字段固定，避免元组解包错位）
        for round_no in range(1, self._copy_test_count + 1):
            for m in meters:
                self._copy_test_queue.append({
                    "row": m["row"], "addr": m["addr"], "proto": m["proto"],
                    "round": round_no,
                    "frames": list(m["frames"]),   # 本轮剩余待发数据项
                    "ok": True,                    # 本轮是否全部成功
                    "started": 0.0,                # 本轮首帧发送时刻
                })

        self._copy_test_mode = mode
        self._is_copy_testing = True
        self.stop_copy_btn.setEnabled(True)
        self._refresh_copy_summary()

        items_desc = "、".join(it["name"] for it in C.enabled_items(self._copy_items))
        if mode == "sequential":
            self._log(f"[点抄测试] 开始按表号顺序抄读 {self._copy_test_count} 轮 × "
                      f"{len(meters)} 个电表；数据项：{items_desc}")
            self._send_next_copy_test()
        else:
            self._copy_test_remaining_rounds = self._copy_test_count
            self._log(f"[并发抄表] 开始并发抄读 {len(rows)} 个电表，共{self._copy_test_count}轮；"
                      f"并发每表只带第一项：{C.enabled_items(self._copy_items)[0]['name']}")
            self._send_concurrent_copy()

    # ---- 数据项 → 内层报文 ----
    def _table_is_698(self, proto_text: str) -> bool:
        """表协议文本 → 是否 698 表"""
        text = str(proto_text or "").upper()
        return "698" in text or "D/T 698" in text

    def _frames_for(self, addr: str, proto_text: str):
        """按勾选的数据项与表协议生成内层报文列表"""
        frames, skipped = C.frames_for_meter(addr, self._table_is_698(proto_text),
                                            self._copy_items)
        if skipped:
            self._log(f"[抄读数据项] {addr} 跳过不适用项：" + "、".join(skipped))
        if not frames:
            self._log(f"[抄读数据项] {addr} 没有可用的数据项（表协议={proto_text}），请到"
                      f"「抄读数据项…」里勾选对应归属的项")
        return frames

    def _send_next_copy_test(self):
        """发送队列中的下一个点抄任务（一项 = 某表某一轮的一个数据项帧）"""
        if not self._is_copy_testing:
            return
        if not self._copy_test_queue:
            self._finish_copy_test("所有轮次抄读完成")
            return
        task = self._copy_test_queue[0]
        row, addr = task["row"], task["addr"]
        if not task["frames"]:
            # 该表没有可用数据项：跳过这个任务，别卡住队列
            self._copy_test_queue.pop(0)
            self.table.setItem(row, 8, QTableWidgetItem("无可用数据项"))
            self._send_next_copy_test()
            return

        name, inner_frame, proto_type = task["frames"][0]
        if not task["started"]:
            task["started"] = time.monotonic()
            self._copy_test_stats[addr]["sent"] += 1      # 本轮开始即计入「已抄轮次」
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
        self._copy_test_current_send_ts = time.monotonic()
        self._send_hex(frame.hex().upper(),
                       f"点抄 [{addr}] 第{task['round']}/{self._copy_test_count}轮 · {name}")

        if self._copy_test_timer is None:
            from PySide6.QtCore import QTimer
            self._copy_test_timer = QTimer(self)
            self._copy_test_timer.setSingleShot(True)
            self._copy_test_timer.timeout.connect(self._on_copy_test_timeout)
        self._copy_test_timer.start(self._copy_test_timeout_ms)

    def _send_concurrent_copy(self):
        """发送并发抄表帧（AFN=F1H F1，表 135：规约类型+保留+报文长度(2B)+报文内容）

        **一帧一块表**（表地址填 376.2 的「目的地址 A3」），所以本轮按表逐帧连发、不逐帧等应答。
        每块表只能带一个报文内容 → 取勾选项里第一个适用于该表的数据项
        （默认「从节点版本信息」，STA 模块自己应答，最稳）。
        """
        chosen = C.enabled_items(self._copy_items)
        sent_count = 0
        self._copy_test_concurrent_responses = {}
        self._copy_test_round_started_at = time.monotonic()
        # 并发抄表每轮对每个表只发一帧：队列里同一块表可能有多轮任务，按地址去重
        seen_addrs = set()
        for task in self._copy_test_queue:
            addr = task["addr"]
            proto = task["proto"]
            if addr in seen_addrs:
                continue
            seen_addrs.add(addr)
            is698 = self._table_is_698(proto)
            item = None
            for it in chosen:
                if it.get("kind") == C.KIND_MODULE_VERSION:
                    item = it          # 公司扩展协议项对任何表都适用
                    break
                if is698 and it["proto"] in (C.PROTO_698, C.PROTO_MODULE):
                    item = it
                    break
                if not is698 and it["proto"] in (C.PROTO_645, C.PROTO_MODULE):
                    item = it
                    break
            if item is None:
                self._log(f"[并发抄表] {addr} 没有适用的数据项，跳过")
                continue
            if item.get("kind") == C.KIND_MODULE_VERSION:
                # 公司扩展协议：不区分表协议，恒为 645 帧
                inner_frame = C.build_module_version_frame(addr)
                proto_type = 2
            elif is698:
                oad = item.get("oad") or C.module_di_to_oad(item.get("di", ""))
                inner_frame = C.build_698_get_list(addr, [oad])
                proto_type = 3
            else:
                inner_frame = C.build_645_read(addr, item["di"])
                proto_type = 2

            field_values = {
                "规约类型": proto_type,
                "保留": 0,
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
                0xF1, 1, field_values, info_config,
                src_addr=self.gdw_src_addr.text().strip(),
                dst_addr=addr
            )
            self._copy_test_stats[addr]["sent"] = self._copy_test_stats[addr]["total"]
            self._copy_test_concurrent_responses[addr] = 0
            self._send_hex(frame.hex().upper(),
                           f"并发抄表 [{addr}] {len(self._copy_test_queue)} 表连发 · {item['name']}")
            sent_count += 1

        if not sent_count:
            self._finish_copy_test("没有可发的从节点（数据项不适用）")
            return

        if self._copy_test_timer is None:
            from PySide6.QtCore import QTimer
            self._copy_test_timer = QTimer(self)
            self._copy_test_timer.setSingleShot(True)
            self._copy_test_timer.timeout.connect(self._on_copy_test_timeout)
        timeout = self._copy_test_timeout_ms * max(sent_count, 1)
        self._copy_test_timer.start(timeout)

    def _on_copy_test_timeout(self):
        """抄表测试超时处理"""
        if not self._is_copy_testing:
            return
        if self._copy_test_mode == "sequential":
            if not self._copy_test_queue:
                return
            task = self._copy_test_queue.pop(0)
            row, addr = task["row"], task["addr"]
            elapsed = time.monotonic() - task["started"] if task["started"] else \
                self._copy_test_timeout_ms / 1000.0
            if len(task["frames"]) > 1:
                # 本轮还没发完的项：本帧按超时计，继续发本轮下一项
                self._record_copy_elapsed(addr, elapsed)
                task["ok"] = False
                task["frames"] = task["frames"][1:]
                self._copy_test_queue.insert(0, task)
                self._update_copy_test_progress(row, addr)
                self._send_next_copy_test()
                return
            # 本轮失败收尾
            self._record_copy_elapsed(addr, elapsed)
            self._update_copy_test_progress(row, addr)
            self._send_next_copy_test()
        else:
            self._copy_test_remaining_rounds -= 1
            if self._copy_test_remaining_rounds > 0:
                self._log(f"[并发抄表] 本轮超时，剩余{self._copy_test_remaining_rounds}轮")
                self._send_concurrent_copy()
            else:
                for task in self._copy_test_queue:
                    self._update_copy_test_result(task["row"], task["addr"])
                self._copy_test_queue = []
                self._finish_copy_test("超时，抄读结束")

    def _finish_copy_test(self, reason: str = ""):
        """统一收尾：停定时器、复位状态、关停止按钮、刷新成功率"""
        self._is_copy_testing = False
        if self._copy_test_timer:
            self._copy_test_timer.stop()
        self._sync_stop_button()
        self._refresh_copy_summary()
        if reason:
            self._log(f"[抄表测试] {reason}（{self._format_copy_summary(final=True)}）")

    def _copy_rate_text(self, addr: str) -> str:
        """单个电表的抄读统计文本：次数 / 成功数 / 成功率"""
        stats = self._copy_test_stats.get(addr, {})
        sent = stats.get("sent", 0)
        success = stats.get("success", 0)
        rate = (success / sent * 100) if sent > 0 else 0.0
        return f"抄读{sent}次 成功{success}次 ({rate:.0f}%)"

    def _copy_elapsed_text(self, addr: str) -> str:
        """单个电表的耗时文本：单次耗时 + 平均耗时"""
        stats = self._copy_test_stats.get(addr, {})
        last = stats.get("elapsed_last", 0)
        n = stats.get("elapsed_n", 0)
        if not last and not n:
            return ""
        avg = (stats.get("elapsed_sum", 0) / n) if n else 0
        return f"单次{_fmt_elapsed(last)} 平均{_fmt_elapsed(avg)}"

    def _record_copy_elapsed(self, addr: str, seconds: float):
        """记录一次抄读耗时（应答或超时都算一次）"""
        stats = self._copy_test_stats.get(addr)
        if not stats:
            return
        stats["elapsed_last"] = seconds
        stats["elapsed_sum"] = stats.get("elapsed_sum", 0.0) + seconds
        stats["elapsed_n"] = stats.get("elapsed_n", 0) + 1

    def _format_copy_summary(self, final: bool = False) -> str:
        """总成功率：**成功次数 / 总抄读次数**（用户口径），另附总耗时"""
        if not self._copy_test_stats:
            return ""
        success = sum(s.get("success", 0) for s in self._copy_test_stats.values())
        sent = sum(s.get("sent", 0) for s in self._copy_test_stats.values())
        planned = sum(s.get("total", 0) for s in self._copy_test_stats.values())
        rate = (success / sent * 100) if sent > 0 else 0.0
        meters = len(self._copy_test_stats)
        state = "已完成" if final or not self._is_copy_testing else "进行中"
        text = f"抄表{meters}表 成功{success}/{sent} ({rate:.1f}%)"
        if sent < planned:
            text += f" 计划{planned}"
        if self._copy_test_started_at:
            elapsed = time.monotonic() - self._copy_test_started_at
            text += f" 用时{_fmt_elapsed(elapsed)}"
        return text + f" [{state}]"

    def _format_version_query_summary(self, final: bool = False) -> str:
        """本次版本查询统计：成功节点数 / 已发送次数（有重试，按发送次数算）"""
        if not self._version_query_stats:
            return ""
        success = sum(s.get("success", 0) for s in self._version_query_stats.values())
        sent = sum(s.get("sent", 0) for s in self._version_query_stats.values())
        rate = (success / sent * 100) if sent > 0 else 0.0
        meters = len(self._version_query_stats)
        state = "已完成" if final or not self._is_querying_version else "进行中"
        return f"版本{meters}表 成功{success}/{sent} ({rate:.1f}%) [{state}]"

    def _refresh_copy_summary(self):
        """刷新「成功率」标签：抄表与版本查询各占一段，谁有统计显示谁"""
        parts = []
        copy_text = self._format_copy_summary()
        ver_text = self._format_version_query_summary()
        if copy_text:
            parts.append(copy_text)
        if ver_text:
            parts.append(ver_text)
        if not parts:
            self.copy_summary_label.setText("成功率: -")
            self.copy_summary_label.setStyleSheet("color: #666; font-size: 12px;")
            return
        self.copy_summary_label.setText("成功率 " + "  ".join(parts))
        if self._is_copy_testing or self._is_querying_version:
            color = "#1a73e8"
        else:
            rates = []
            if self._copy_test_stats:
                ok = sum(s.get("success", 0) for s in self._copy_test_stats.values())
                plan = sum(s.get("total", 0) for s in self._copy_test_stats.values())
                rates.append(ok / plan * 100 if plan else 0)
            if self._version_query_stats:
                ok = sum(s.get("success", 0) for s in self._version_query_stats.values())
                sent = sum(s.get("sent", 0) for s in self._version_query_stats.values())
                rates.append(ok / sent * 100 if sent else 0)
            rate = min(rates) if rates else 0
            color = "#1e8e3e" if rate >= 90 else ("#e8710a" if rate >= 50 else "#d93025")
        self.copy_summary_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")

    def _sync_stop_button(self):
        """停止按钮只在有任务运行时可用"""
        self.stop_copy_btn.setEnabled(self._is_copy_testing or self._is_querying_version)

    def _on_stop_copy_test(self):
        """停止按钮：中断正在进行的抄表 / 版本查询"""
        if not (self._is_copy_testing or self._is_querying_version):
            self._log("[测试] 当前没有正在进行的抄读/查询任务")
            return
        if self._is_copy_testing:
            if self._copy_test_timer:
                self._copy_test_timer.stop()
            pending = list(self._copy_test_queue)
            self._is_copy_testing = False
            self._copy_test_queue = []
            # 把未完成的电表补上「已抄到的部分统计」，别让结果列停在「抄读中...」
            done_addrs = set()
            for task in pending:
                addr, row = task["addr"], task["row"]
                if addr in done_addrs:
                    continue
                done_addrs.add(addr)
                stats = self._copy_test_stats.get(addr)
                if stats and stats.get("sent", 0) > 0:
                    self._update_copy_test_result(row, addr)
                else:
                    self.table.setItem(row, 8, QTableWidgetItem("已停止（未发送）"))
            self._log(f"[抄表测试] 已停止，中断 {len(pending)} 个未完成项"
                      f"（{self._format_copy_summary(final=True)}）")
        if self._is_querying_version:
            if self._version_query_timer:
                self._version_query_timer.stop()
            pending = list(self._version_query_queue)
            col = 6 if self._version_query_mode == "simple" else 7
            self._version_query_queue = []
            self._is_querying_version = False
            for row, addr, _remaining in pending:
                item = self.table.item(row, col)
                if item is None or item.text() in ("查询中...", ""):
                    self.table.setItem(row, col, QTableWidgetItem("已停止"))
            self._log(f"[版本查询] 已停止，中断 {len(pending)} 个未完成项"
                      f"（{self._format_version_query_summary(final=True)}）")
        self._sync_stop_button()
        self._refresh_copy_summary()

    def _on_clear_test_records(self):
        """清除测试记录：版本信息 / 详细版本 / 抄读结果 / 耗时 / 抄读内容 + 本次统计"""
        cols = (6, 7, 8, 10, 11)
        has_text = False
        for row in range(self.table.rowCount()):
            for col in cols:
                item = self.table.item(row, col)
                if item and item.text().strip():
                    has_text = True
                    break
            if has_text:
                break
        running = self._is_copy_testing or self._is_querying_version
        if not has_text and not running and not self._copy_test_stats and not self._version_query_stats:
            self._log("[测试] 没有可清除的测试记录")
            return
        if running:
            reply = QMessageBox.question(
                self, "确认清除",
                "抄读/查询任务正在进行，清除记录会先停止当前任务。确定继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            if self._copy_test_timer:
                self._copy_test_timer.stop()
            self._is_copy_testing = False
            self._copy_test_queue = []
            if self._version_query_timer:
                self._version_query_timer.stop()
            self._is_querying_version = False
            self._version_query_queue = []
        for row in range(self.table.rowCount()):
            for col in cols:
                item = self.table.item(row, col)
                if item:
                    item.setText("")
        self._copy_test_stats = {}
        self._copy_test_concurrent_responses = {}
        self._copy_test_remaining_rounds = 0
        self._version_query_stats = {}
        self._sync_stop_button()
        self._refresh_copy_summary()
        self._log("[测试] 测试记录已清除（版本信息/详细版本/抄读结果）")

    # ---- 抄读内容（解析后的关键字段）----
    @staticmethod
    def _lme_value_readable(name: str, value: str) -> str:
        """把个别条目的原始 HEX 换成可读口径（现在只处理载波接收信息）。

        《LME产品相关信息生产运维接口手册》分类2/数据22「载波接收信息」：
        B0 = 信号强度 RSSI，B1 = 信噪比 SNR（长度为 2 字节，HEX 显示）。
        """
        text = str(value or "").strip()
        if name == "载波接收信息" and len(text) == 4:
            try:
                rssi, snr = int(text[0:2], 16), int(text[2:4], 16)
            except ValueError:
                return text
            return f"信号强度RSSI={rssi} 信噪比SNR={snr}（原始 {text}）"
        return text

    def _extract_inner_frame(self, frame: bytes) -> bytes:
        """从 13H F1 / F1H F1 上行帧里取出内层报文（645/698 原始帧）"""
        try:
            table_data = self.gdw_parser.parse_to_table(frame)
        except Exception:                                      # noqa: BLE001
            return b""
        for row in table_data:
            if "报文内容" in str(row[0]):
                try:
                    return bytes.fromhex(str(row[1]).replace(" ", ""))
                except ValueError:
                    return b""
        return b""

    def _copy_content_from_inner(self, inner: bytes, proto_type: int) -> Tuple[str, str]:
        """从内层报文解析出**关键内容**：返回 (单行摘要, 逐条明细)

        - 645 + DI=FF00DD01（公司扩展/LME）：按条目解析，优先取
          载波接收信息（信号强度）、版本、工程版本等关键项；
        - 其它 645 DI：取解析出的第一个数据值；
        - 698：取应答数据域的数值/字节摘要。
        解析失败不抛异常，按原始 HEX 兜底。
        """
        if not inner:
            return "", ""
        hex_text = inner.hex().upper()
        if proto_type == 3:
            try:
                from dl_t698_45_apdu_parser import DLT69845APDUParser
                from dl_t698_45_parser import DLT69845Parser
                frame = DLT69845Parser().parse(inner)
                data = frame.get("用户数据") or b""
                apdu = DLT69845APDUParser().parse(data) if data else {}
                detail = " · ".join(
                    f"{k}:{v.get('解析值', v.get('原始值', ''))}"
                    for k, v in apdu.items() if isinstance(v, dict)
                )[:400]
                return (detail or hex_text[:60]), (detail or hex_text)
            except Exception:                                  # noqa: BLE001
                return hex_text[:60], hex_text

        try:
            res = DLT645Parser().parse(inner)
        except Exception:                                      # noqa: BLE001
            return hex_text[:60], hex_text
        if not res.get("valid"):
            return f"无效帧:{res.get('error', '')}"[:60], str(res.get("error") or hex_text)
        di = str(res.get("di_code") or "").upper()
        data = res.get("data", b"")
        if di == "FF00DD01":
            try:
                entries = parse_lme_info_entries(data) or []
            except Exception:                                  # noqa: BLE001
                entries = []
            if entries:
                priority = ("载波接收信息", "外部版本号", "总工程版本", "网络层版本",
                            "外部厂商代码", "外部芯片代码", "环境温度", "模块类型")
                picked = [f"{n}:{self._lme_value_readable(n, v)}"
                          for n, v in entries if n in priority and v]
                short = " ".join(picked[:5]) or format_lme_info_detail(entries)[:80]
                return short, "\n".join(
                    f"{n}: {self._lme_value_readable(n, v)}" for n, v in entries)
        # 普通 DI：取业务数据值
        # ⚠ 行长度各家不同（645=3/4 元，698/国网=6 元）⇒ 一律走 _field_triple，
        #   不要在这里硬解元组（曾导致抄读测试崩溃，见函数注释）
        triples = [_field_triple(row) for row in (res.get("fields") or [])]
        # 摘要取「业务值」而不是「最后一个有值的字段」：645 的 fields 末尾是
        # 校验和/结束符（解析值恰为「CS校验」「结束符」），取末尾会显示成
        # 「当前正向有功总电能:结束符」。优先「数据值」行，其次 DI 行之后
        # 第一个非结构行（跳过帧起始符/控制码/数据长度/校验和/结束符）。
        _structural = ("帧起始符", "从站地址", "控制码", "数据长度", "数据标识 DI",
                       "校验和", "帧结束符", "数据域")
        value = next((p for (n, _r, p) in triples
                      if n.startswith("数据值") and p.strip()), "")
        if not value:
            value = next((p for (n, _r, p) in triples
                          if p.strip() and not n.startswith(_structural)), "")
        short = (f"{res.get('di_desc', '')}:{value}" if value
                 else (res.get("di_desc") or ""))
        return short[:80], "\n".join(f"{n}: {p}" for (n, _r, p) in triples)

    def _update_copy_test_result(self, row: int, addr: str):
        """更新抄读结果（成功率）+ 抄读内容 + 耗时到表格"""
        result_text = self._copy_rate_text(addr)
        self.table.setItem(row, 8, QTableWidgetItem(result_text))
        self.table.setItem(row, 10, QTableWidgetItem(self._copy_elapsed_text(addr)))
        short = self._copy_test_content.get(addr, "")
        item = QTableWidgetItem(short)
        full = self._copy_test_content_full.get(addr, "")
        if full:
            item.setToolTip(full)
        self.table.setItem(row, 11, item)
        self._refresh_copy_summary()
        self._log(f"[抄读结果] {addr}: {result_text} {self._copy_elapsed_text(addr)}"
                  + (f" | {short}" if short else ""))

    def _update_copy_test_progress(self, row: int, addr: str):
        """抄读过程中的实时进度（不停留在「抄读中...」；该表最后一轮完成后收尾）"""
        if self._meter_finished(addr):
            self._update_copy_test_result(row, addr)
            return
        self.table.setItem(row, 8, QTableWidgetItem(self._copy_rate_text(addr) + " 抄读中"))
        self.table.setItem(row, 10, QTableWidgetItem(self._copy_elapsed_text(addr)))
        short = self._copy_test_content.get(addr, "")
        item = QTableWidgetItem(short)
        full = self._copy_test_content_full.get(addr, "")
        if full:
            item.setToolTip(full)
        self.table.setItem(row, 11, item)
        self._refresh_copy_summary()

    def _meter_finished(self, addr: str) -> bool:
        """队列里已经没有该表的任务 → 这块表本轮测试结束"""
        return not any(t.get("addr") == addr for t in self._copy_test_queue)

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

    def _read_copy_count(self) -> int:
        """抄读次数（点抄/并发/版本查询共用同一个输入框）"""
        try:
            return max(1, int(self.copy_count_input.text().strip() or "3"))
        except ValueError:
            return 3

    def _start_version_query(self, rows: List[int], mode: str):
        """启动版本查询队列（每节点最多尝试「抄读次数」次）"""
        attempts = self._read_copy_count()
        self._version_query_attempts = attempts
        self._version_query_queue = []
        self._version_query_stats = {}
        for row in rows:
            addr = self.table.item(row, 2).text().strip().zfill(12)
            self._version_query_queue.append((row, addr, attempts))
            self._version_query_stats[addr] = {"sent": 0, "success": 0, "total": attempts}
            # 清空对应模式的列
            col = 6 if mode == "simple" else 7
            self.table.setItem(row, col, QTableWidgetItem("查询中..."))
        self._version_query_mode = mode
        self._is_querying_version = True
        self._sync_stop_button()
        self._refresh_copy_summary()
        self._log(f"[版本查询] 开始查询 {len(rows)} 个从节点，模式={mode}，每节点最多{attempts}次")
        self._send_next_version_query()

    def _send_next_version_query(self):
        """发送队列中的下一个版本查询"""
        if not self._version_query_queue:
            self._is_querying_version = False
            self._sync_stop_button()
            self._refresh_copy_summary()
            self._log(f"[版本查询] 所有从节点查询完成"
                      f"（{self._format_version_query_summary(final=True)}）")
            return
        row, addr, _remaining = self._version_query_queue[0]
        self._version_query_current_row = row
        self._version_query_current_addr = addr
        if addr in self._version_query_stats:
            self._version_query_stats[addr]["sent"] += 1
        self._refresh_copy_summary()

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
        """查询详细版本信息的内层 DLT645 帧（公司扩展协议 LME 4.6，DI=FF00DD01）

        与「抄读数据项 → 从节点版本信息」**共用同一份实现**
        （`archive_copy_items.build_module_version_frame`），避免两条路径的报文漂移。
        """
        return C.build_module_version_frame(addr)

    def _on_version_timeout(self):
        """版本查询超时处理：还有剩余次数就重试，用尽才判超时"""
        if not self._is_querying_version or not self._version_query_queue:
            return
        row, addr, remaining = self._version_query_queue.pop(0)
        col = 6 if self._version_query_mode == "simple" else 7
        remaining -= 1
        if remaining > 0:
            self._version_query_queue.insert(0, (row, addr, remaining))
            self._log(f"[版本查询] 从节点 {addr} 超时，重试（剩余{remaining}次）")
            self._send_next_version_query()
            return
        self.table.setItem(row, col, QTableWidgetItem("超时"))
        self._log(f"[版本查询] 从节点 {addr} 查询超时（{self._version_query_attempts}次尝试已用尽）")
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

    def _add_meter_to_table(self, info: Dict[str, Any], save: bool = True):
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
        # 第 10 列「其他信息」：中继级别 / 侦听信号品质（10H F2 的 2 字节节点信息）
        self.table.setItem(row, 9, QTableWidgetItem(str(info.get("extra") or "")))
        self.table.setItem(row, 10, QTableWidgetItem(""))
        self.table.setItem(row, 11, QTableWidgetItem(""))

        self._node_data.append(info)
        if save:
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
        self.table.setItem(row, 10, QTableWidgetItem(""))
        self.table.setItem(row, 11, QTableWidgetItem(""))

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

        # 查询从节点信息 AFN=10 F2：按响应总数翻页（见 _handle_node_info_response）
        if afn == 0x10 and fn == 2:
            self._handle_node_info_response(table_data)
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

    @staticmethod
    def _lme_entries_usable(entries, di_code: str, di_desc: str) -> bool:
        """判断 LME 条目解析结果是否可信，避免把普通 645 数据误当 TLV 条目

        - 已知 LME DI（FF00DD01 双模 4.6/4.7、04FFAAF9 单模 4.2）：解出条目即可用
        - 未知 DI：按 TLV 解出的条目 ≥2 条才算数（单条基本都是误判）
        - 有名字的标准 DI（如 00010000 电能）：至少 2 条才认，否则回原文
        """
        if not entries:
            return False
        if di_code in ("FF00DD01", "04FFAAF9") or di_desc == "未知数据标识":
            return True
        return len(entries) >= 2

    def _handle_version_response_detail(self, frame: bytes):
        """处理AFN=13 F1/F2详细版本查询响应"""
        if self._version_query_timer:
            self._version_query_timer.stop()
        try:
            table_data = self.gdw_parser.parse_to_table(frame)
        except Exception:
            self._set_version_query_result("解析失败", col=7)
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
            self._set_version_query_result("无内层数据", col=7)
            return
        # 解析内层DLT645帧
        try:
            dlt_parser = DLT645Parser()
            dlt_result = dlt_parser.parse(inner_frame)
            if dlt_result.get('valid'):
                di_code = str(dlt_result.get('di_code') or '').upper()
                di_desc = dlt_result.get('di_desc', '未知')
                # 提取数据域的原始字节（已减0x33）
                data = dlt_result.get('data', b'')
                # LME 4.6 / 4.7（双模 STA 内部详细信息）以及任何能按 TLV 条目解出来的 DI，
                # 都要走条目解析 —— 以前只在「未知数据标识」时才尝试，而 FF00DD01 在
                # dlt645_di.json 里有名字，于是永远落到原文兜底（用户报障：详细版本列是原始 hex）
                entries = None
                if data:
                    try:
                        entries = parse_lme_info_entries(data)
                    except Exception:
                        entries = None
                    if not self._lme_entries_usable(entries, di_code, di_desc):
                        entries = None
                if entries:
                    # 「详细版本」列显示**全量**条目（含总工程版本/各层版本），原文只作兜底；
                    # 「版本信息」列留给 AFN=03 F1「查询从节点版本」，这里不再写它
                    result_text = format_lme_info_detail(entries)
                    detail_lines = "\n".join(f"{n}: {v}" for n, v in entries)
                elif data:
                    result_text = f"DI:{di_desc} 数据:{data.hex().upper()}"
                    detail_lines = ""
                else:
                    result_text = f"DI:{di_desc}"
                    detail_lines = ""
            else:
                result_text = f"DLT645无效帧:{dlt_result.get('error', '未知错误')}"
                detail_lines = ""
        except Exception as e:
            result_text = f"DLT645解析异常:{e}"
            detail_lines = ""
        # 列宽放不下时靠悬浮看全文（每条一行）
        self._version_query_tooltip = detail_lines
        self._set_version_query_result(result_text, col=7)

    def _handle_copy_test_response(self, frame: bytes, table_data: list):
        """处理点抄测试响应 (AFN=13 F1)

        一个任务 = 某表某一轮里的一个数据项；**该轮全部项都成功**才算这一轮成功。
        """
        if self._copy_test_timer:
            self._copy_test_timer.stop()
        if not self._copy_test_queue:
            return
        task = self._copy_test_queue.pop(0)
        row, addr = task["row"], task["addr"]
        # 成功判定按**实际发出的内层报文协议**（版本信息项恒为 645 帧，即使表是 698）
        sent_proto_type = task["frames"][0][2] if task["frames"] else 2
        success = self._parse_copy_inner_success(
            frame, "698" if sent_proto_type == 3 else "645")
        # 解析内层报文的**关键内容**（信号强度/版本/电量等），写进「抄读内容」列
        inner = self._extract_inner_frame(frame)
        if inner:
            short, full = self._copy_content_from_inner(inner, sent_proto_type)
            if short:
                self._copy_test_content[addr] = short
                self._copy_test_content_full[addr] = full
        task["ok"] = bool(task["ok"]) and success
        if len(task["frames"]) > 1:
            # 本轮还有下一项：继续这一轮，不结算
            task["frames"] = task["frames"][1:]
            self._copy_test_queue.insert(0, task)
            self._update_copy_test_progress(row, addr)
            self._send_next_copy_test()
            return
        # 本轮结束：结算一次（耗时按「本轮首帧 → 末帧应答」）
        if task["ok"]:
            self._copy_test_stats[addr]["success"] += 1
        self._record_copy_elapsed(addr, time.monotonic() - task["started"])
        self._update_copy_test_progress(row, addr)
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
        for task in self._copy_test_queue:
            if task["addr"] == src_addr:
                self._copy_test_stats[src_addr]["success"] += 1
                self._copy_test_concurrent_responses[src_addr] = \
                    self._copy_test_concurrent_responses.get(src_addr, 0) + 1
                # 并发抄表：耗时按「本轮发出 → 本表应答」计
                round_start = getattr(self, "_copy_test_round_started_at", 0.0)
                if round_start:
                    self._record_copy_elapsed(src_addr, time.monotonic() - round_start)
                inner = self._extract_inner_frame(frame)
                if inner:
                    proto_type = 3 if self._table_is_698(task["proto"]) else 2
                    short, full = self._copy_content_from_inner(inner, proto_type)
                    if short:
                        self._copy_test_content[src_addr] = short
                        self._copy_test_content_full[src_addr] = full
                self._update_copy_test_progress(task["row"], src_addr)
                found = True
                break
        if not found:
            return
        # 检查本轮是否所有电表都已响应（按地址去重）
        unique_addrs = {t["addr"] for t in self._copy_test_queue}
        all_responded = all(
            self._copy_test_concurrent_responses.get(addr, 0) > 0
            for addr in unique_addrs
        )
        if all_responded:
            if self._copy_test_timer:
                self._copy_test_timer.stop()
            self._copy_test_remaining_rounds -= 1
            if self._copy_test_remaining_rounds > 0:
                self._log(f"[并发抄表] 本轮完成，剩余{self._copy_test_remaining_rounds}轮")
                self._send_concurrent_copy()
            else:
                for task in self._copy_test_queue:
                    self._update_copy_test_result(task["row"], task["addr"])
                self._copy_test_queue = []
                self._finish_copy_test("所有轮次完成")

    def _parse_copy_inner_success(self, frame: bytes, proto: str) -> bool:
        """从AFN=13 F1上行帧中提取内层报文并判断是否抄读成功"""
        try:
            table_data = self.gdw_parser.parse_to_table(frame)
        except Exception:
            return False
        inner_frame = None
        for row in table_data:
            cells = tuple(row)
            name = str(cells[0]) if len(cells) > 0 else ""
            comment = str(cells[3]) if len(cells) > 3 else ""
            if "报文内容" in name and "原始报文数据" in comment:
                try:
                    inner_frame = bytes.fromhex(str(cells[1]).replace(" ", ""))
                except ValueError:
                    pass
                break
        if not inner_frame or len(inner_frame) < 10:
            # 表格口径拿不到时，直接按 376.1 的「上行时长(2)+协议(1)+长度(1)+内容」兜底，
            # 免得解析器分支变化又把成功率判成 0（现场 0% 故障即此类耦合）
            inner_frame = self._scan_inner_frame(frame) or inner_frame
        if not inner_frame or len(inner_frame) < 10:
            return False
        # ---- DLT645：先跳过前导码 0xFE，再按 68 A0..A5 68 C 定位控制码 ----
        # 现场帧的内层报文以 **0xFE 前导** 开头（645 允许 FE FE .. 68），旧实现直接
        # 取 inner_frame[0]==0x68 判定 → 一见到 FE 就判失败：抄读内容明明解出来了
        # （645 解析器支持前导），成功率却是 0%（用户报障）。这里统一跳过前导、
        # 按结构找第二个 0x68 的下一字节作控制码，不依赖固定下标。
        if "645" in proto:
            ctrl = self._dlt645_ctrl_of(inner_frame)
            if ctrl is not None:
                # D7=1 从站应答；D6=1 异常应答（带错误码，抄读并未成功）
                # 旧实现只看 D7，把异常应答也算成功 ⇒ 成功率虚高；这里两者都要判。
                return (ctrl & 0x80) != 0 and (ctrl & 0x40) == 0
        # DLT698: 看APDU第一个字节是否为应答类型
        if "698" in proto:
            frame_698 = self._skip_prefix(inner_frame, (0xFE,))
            if frame_698 and frame_698[0] == 0x68 and len(frame_698) > 14:
                apdu_tag = frame_698[14]
                return (apdu_tag & 0x80) != 0
        return False

    @staticmethod
    def _skip_prefix(data: bytes, prefixes: Tuple[int, ...]) -> bytes:
        """跳过报文前导字节（645/698 的 0xFE 前导可重复出现）。"""
        pos = 0
        while pos < len(data) and data[pos] in prefixes:
            pos += 1
        return data[pos:]

    @staticmethod
    def _dlt645_ctrl_of(data: bytes) -> Optional[int]:
        """从（可能带 FE 前导的）645 帧里取控制码；结构不符返回 None。

        帧结构：``68 A0..A5 68 C ...`` ⇒ 控制码 = 第 2 个 ``0x68`` 之后 1 字节。
        """
        start = 0
        while start < len(data) and data[start] == 0xFE:
            start += 1
        if start + 9 >= len(data):
            return None
        if data[start] != 0x68:
            return None
        if data[start + 7] != 0x68:          # 地址 6 字节之后必须还是 68
            return None
        return data[start + 8]

    def _scan_inner_frame(self, frame: bytes) -> bytes:
        """从 376.1 上行帧里直接按「上行时长(2)+协议类型(1)+长度(1)+内容」取内层报文。

        只在表格取不到「报文内容」时兜底；数据单元位置由 AFN/DT 定位，
        找不到返回 ``b""``（不猜）。
        """
        try:
            afn, fn = self._extract_gdw_afn_fn(frame)
        except Exception:                                      # noqa: BLE001
            return b""
        if afn != 0x13 or fn not in (1, 2):
            return b""
        # 数据单元起点：AFN(1) + DT(2) 之前的部分按 376.1 头长度推算
        # 直接用解析器已识别到的「数据单元」行取原始 HEX 更稳（表格结构见 gdw 解析器）
        try:
            table_data = self.gdw_parser.parse_to_table(frame)
        except Exception:                                      # noqa: BLE001
            return b""
        for row in table_data:
            cells = tuple(row)
            if len(cells) > 1 and str(cells[0]).strip() == "数据单元":
                try:
                    unit = bytes.fromhex(str(cells[1]).replace(" ", ""))
                except ValueError:
                    return b""
                if fn == 1 and len(unit) >= 4:
                    msg_len = unit[3]
                    content = unit[4:4 + msg_len]
                    return content if len(content) == msg_len else b""
        return b""

    def _set_version_query_result(self, text: str, col: Optional[int] = None):
        """设置当前查询行的回读信息并继续下一个（收到应答即记一次成功）"""
        if col is None:
            col = 6 if self._version_query_mode == "simple" else 7
        if not self._version_query_queue:
            self._is_querying_version = False
            self._sync_stop_button()
            self._refresh_copy_summary()
            return
        row, addr, _remaining = self._version_query_queue.pop(0)
        if addr in self._version_query_stats:
            self._version_query_stats[addr]["success"] += 1
        item = QTableWidgetItem(text)
        tip = getattr(self, "_version_query_tooltip", "")
        if tip:
            item.setToolTip(tip)
        self.table.setItem(row, col, item)
        self._version_query_tooltip = ""
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
