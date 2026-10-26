# -*- coding: utf-8 -*-
"""协议 7（国网 Q/GDW 10376.2—2024）**协议测试页** —— 按 AFN/Fn 分类的预置命令树 + 组帧下发。

与「协议组帧」页的分工：组帧页临时、任意填；本页是**预先做好**的测试项库，按功能域 → AFN → Fn
把 122 条命令（含福建增补 50H~56H、F0/F1 扩展）分成五页；另含附件1 的 **EB 数据标识**（75 条）
与用户自定义 AFN+Fn。勾选即按顺序下发，用来做模块一致性/功能测试。

设计约束（改本页前先读）
--------------------
- **不自建串口**：端口生命周期归主窗口顶部「串口配置」，本页经 :meth:`set_serial_worker`
  借用共享 ``SerialWorker``；发送只用 ``write_raw``，TX/RX 日志本页自己写。
- **通道走 ``channel_link.ChannelController``**（串口 / 蓝牙）：蓝牙复用「蓝牙工具」页连接，
  整帧一次 ATT 写、超限报错不发送；两个通道的字节严格隔离（见 AGENTS 陷阱 92）。
- **组帧/判定的单一来源**全部在 :mod:`gdw_test_core`（生成器 + 解析器），本页**不手拼帧、不新写判据**。
- **不冒充判定**：``evaluate_response`` 的 ``ok=None`` 表示「收到了同命令响应但没有可自证的成功字段」，
  界面显示「已接收（未做字段级判定）」，不写「成功」。
- **发送队列用单发 QTimer + 标志位**（无 QThread），并且 ``_send_next`` 有 ``_awaiting`` 守卫 ——
  否则上一轮遗留定时器会在等应答期间提前发下一条。
- RX 自组帧用 :mod:`frame_deframe` 的 ``ft12_68``（国网 L = 整帧长、末字节 16H）；只有末字节
  确为 16H 才切帧，切不出时按「68H / FEH 才是帧起点」重同步丢噪声。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

import app_paths
import channel_link as ch
import frame_deframe
import gdw_test_core as core
from atomic_io import atomic_write_json
from gui_utils import fit_btn_width

CONFIG_NAME = "gdw_testbench.json"
CONFIG_VERSION = 1
DEFRAME_STRATEGY = "ft12_68"
RX_BUF_MAX = 64 * 1024
RAW_ROW_LIMIT = 2000
LOG_MAX_BLOCKS = 4000
#: 树/日志/底部 tabs 的空间下限（照 698 页 1000×700 实测值，低于它会压掉内容）
TREE_MIN_HEIGHT = 160
LOG_MIN_HEIGHT = 120
DETAIL_MAX_HEIGHT = 200

LOG_PALETTES = {
    False: {"bg": "#FFFFFF", "fg": "#1F2328", "border": "#D0D7DE",
            "ok": "#0A7D28", "fail": "#B42318", "info": "#1F6FEB",
            "warn": "#9A6700", "tx": "#6639BA", "hint": "#6E7781"},
    True: {"bg": "#1E1E1E", "fg": "#D4D4D4", "border": "#3C3C3C",
           "ok": "#4EC9B0", "fail": "#F48771", "info": "#569CD6",
           "warn": "#DCDCAA", "tx": "#C586C0", "hint": "#8A8A8A"},
}

#: 数据单元标识列宽之外的默认值
DEFAULTS: Dict[str, Any] = {
    "version": CONFIG_VERSION,
    "src": "000000000001",
    "dst": "123456789012",
    "module_flag": 1,
    "relay_level": 0,
    "relay_addrs": ["000000000000"] * 3,
    "seq": 1,
    "timeout_ms": 1500,
    "retries": 1,
    "channel": ch.DEFAULT_CHANNEL,
    "page": core.PAGE_READ,
    "detail": True,
    "eb_addr": "000000000001",
    "eb_ctrl": 0x11,
    "eb_wrap": True,
    # 三栏宽度（左树 / 中参数 / 右收发日志）——与 698 协议测试页同布局
    "split_sizes": [300, 520, 460],
}

LEAF_KEY_ROLE = Qt.ItemDataRole.UserRole
CHECKED_ROLE = Qt.ItemDataRole.UserRole + 1


def _fmt(data: bytes, limit: int = 200) -> str:
    """帧 hex 显示：≤limit 整帧；超过则头尾各半 + 总长（与升级页同一口径）。"""
    data = bytes(data or b"")
    if not limit or len(data) <= limit:
        return core.format_hex(data)
    half = limit // 2
    return (core.format_hex(data[:half]) + " ... " + core.format_hex(data[-half:])
            + f"  (共 {len(data)} 字节)")


def _parse_hex(text: str) -> bytes:
    return core.parse_hex(text)


class GdwTestWidget(QWidget):
    """国网协议测试页（仅协议7 可见；懒加载）。"""

    frame_to_single_parse = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._core = core
        self._channel = ch.ChannelController(self)
        self._serial_worker = None
        self._bt_provider = None
        self._single_handler = None
        self._dark = False
        self._rx_buf = bytearray()
        self._page = core.PAGE_READ
        self._current: Optional[core.GdwCommand] = None
        self._current_eb: Optional[core.EbItem] = None
        self._queues: Dict[str, List[Tuple[str, float]]] = {}
        self._checked: Dict[str, List[str]] = {}
        self._field_widgets: List[Tuple[dict, QWidget, Any]] = []
        self._eb_widgets: List[Tuple[dict, QWidget]] = []
        self._trees: Dict[str, QTreeWidget] = {}
        self._queue_commands: List[Tuple[str, str]] = []
        self._queue_idx = 0
        self._awaiting = False
        self._attempt = 0
        self._sent = 0
        self._pending_frame = b""
        self._pending_key = ""
        self._pending_page = ""
        self._frame_rows: List[bytes] = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_persisted)
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_reply_timeout)
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.setInterval(10)
        self._next_timer.timeout.connect(self._send_next)

        self._connect_channel()
        self._build_ui()
        self._load_persisted()
        self._select_page(self._page, notify=False)
        self.restyle_for_theme(False)

    # ── 通道 ────────────────────────────────────────────────────────────
    def _connect_channel(self) -> None:
        self._channel.rx.connect(self._on_rx_data)
        self._channel.state_changed.connect(self._on_channel_state)
        self._channel.channel_changed.connect(self._on_channel_switched)
        self._channel.error.connect(lambda msg: self._log(f"[通道] {msg}", "warn"))

    def set_serial_worker(self, worker) -> None:
        self._serial_worker = worker
        self._channel.set_serial_worker(worker)

    def set_bluetooth_provider(self, provider) -> None:
        self._bt_provider = provider
        self._channel.set_bluetooth_provider(provider)

    def set_send_to_single_handler(self, handler) -> None:
        self._single_handler = handler

    def showEvent(self, event):  # noqa: N802 - Qt 命名
        super().showEvent(event)
        self._channel.rebind_bluetooth()
        if self._page == core.PAGE_CUSTOM:
            # 自定义 AFN+Fn 可能在「查询 → AFN查询」刚加过 ⇒ 每次回到本页重建（惰性页常态）
            self.refresh()

    def refresh(self) -> None:
        """重建当前页的树（自定义页增删后调用；其它页无副作用）。"""
        tree = self._trees.get(self._page)
        if tree is None:
            return
        tree.blockSignals(True)
        tree.clear()
        tree.blockSignals(False)
        self._ensure_tree(self._page)

    def _on_channel_state(self, text: str, ready: bool) -> None:
        self.lbl_channel_state.setText(text or "")
        self.lbl_channel_state.setStyleSheet(
            "" if ready else "color:#B42318;")

    def _on_channel_switched(self, _channel: str) -> None:
        self._rx_buf.clear()

    # ── UI ─────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self._build_top_bar())

        # 布局对齐协议8「协议测试」页：左 = 命令树，中 = 参数/预览/发送，右 = 收发日志；
        # 信息表/报文表横跨底部。**日志必须在最右**（用户口径，别放回底部）。
        self.main_split = QSplitter(Qt.Orientation.Horizontal)
        self.main_split.addWidget(self._build_left_panel())
        self.main_split.addWidget(self._build_center())
        self.main_split.addWidget(self._build_log_panel())
        self.main_split.setStretchFactor(0, 0)
        self.main_split.setStretchFactor(1, 1)
        self.main_split.setStretchFactor(2, 1)
        self.main_split.setSizes(DEFAULTS["split_sizes"])
        root.addWidget(self.main_split, 1)

        root.addWidget(self._build_detail())

    def _vline(self) -> QFrame:
        ln = QFrame()
        ln.setFrameShape(QFrame.Shape.VLine)
        ln.setFrameShadow(QFrame.Shadow.Sunken)
        return ln

    def _build_top_bar(self) -> QWidget:
        box = QGroupBox("测试参数")
        grid = QGridLayout(box)
        grid.setContentsMargins(8, 4, 8, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(3)

        self.combo_channel = QComboBox()
        self.combo_channel.addItem("串口", ch.SERIAL)
        self.combo_channel.addItem("蓝牙", ch.BLUETOOTH)
        self.combo_channel.currentIndexChanged.connect(self._on_channel_combo_changed)
        self.lbl_channel_state = QLabel("")
        self.lbl_channel_state.setWordWrap(True)

        self.edit_src = QLineEdit(); self.edit_src.setMaxLength(12)
        self.edit_dst = QLineEdit(); self.edit_dst.setMaxLength(12)
        self.combo_module = QComboBox()
        self.combo_module.addItem("1（含地址域）", 1)
        self.combo_module.addItem("0（无地址域）", 0)
        self.spin_relay = QSpinBox(); self.spin_relay.setRange(0, 15)
        self.spin_seq = QSpinBox(); self.spin_seq.setRange(0, 255)
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(100, 60000)
        self.spin_timeout.setSuffix(" ms")
        self.spin_retries = QSpinBox(); self.spin_retries.setRange(0, 10)

        for w in (self.edit_src, self.edit_dst):
            w.setMinimumWidth(130)
            w.editingFinished.connect(self._schedule_save)
        for w in (self.combo_module, self.spin_relay, self.spin_seq,
                  self.spin_timeout, self.spin_retries):
            w.currentIndexChanged.connect(self._schedule_save) if isinstance(w, QComboBox) else w.valueChanged.connect(self._schedule_save)

        grid.addWidget(QLabel("发送通道"), 0, 0)
        grid.addWidget(self.combo_channel, 0, 1)
        grid.addWidget(self.lbl_channel_state, 0, 2, 1, 3)
        grid.addWidget(QLabel("源地址"), 0, 5)
        grid.addWidget(self.edit_src, 0, 6)
        grid.addWidget(QLabel("目的地址"), 0, 7)
        grid.addWidget(self.edit_dst, 0, 8)
        grid.addWidget(QLabel("模块标识"), 0, 9)
        grid.addWidget(self.combo_module, 0, 10)
        grid.addWidget(QLabel("中继级别"), 1, 0)
        grid.addWidget(self.spin_relay, 1, 1)
        grid.addWidget(QLabel("序列号"), 1, 2)
        grid.addWidget(self.spin_seq, 1, 3)
        grid.addWidget(QLabel("超时"), 1, 4)
        grid.addWidget(self.spin_timeout, 1, 5)
        grid.addWidget(QLabel("重试"), 1, 6)
        grid.addWidget(self.spin_retries, 1, 7)
        self.btn_clear = QPushButton("清空日志/报文")
        self.btn_clear.clicked.connect(self._on_clear)
        grid.addWidget(self.btn_clear, 1, 8, 1, 2)
        grid.setColumnStretch(11, 1)
        fit_btn_width(self.btn_clear)
        return box

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(4)

        row = QHBoxLayout()
        row.addWidget(QLabel("搜索"))
        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("AFN / Fn / 命令名 / 数据标识")
        self.edit_filter.textChanged.connect(self._apply_filter)
        row.addWidget(self.edit_filter, 1)
        lay.addLayout(row)

        self.page_tabs = QTabWidget()
        for key, label in core.PAGES:
            tree = QTreeWidget()
            tree.setHeaderLabels(["命令 (AFN/Fn)", "方向"])
            tree.setColumnWidth(0, 250)
            tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            tree.setMinimumHeight(TREE_MIN_HEIGHT)
            tree.setAlternatingRowColors(True)
            tree.itemSelectionChanged.connect(self._on_tree_selection)
            tree.itemChanged.connect(self._on_item_changed)
            tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
            self._trees[key] = tree
            self.page_tabs.addTab(tree, label)
        self.page_tabs.currentChanged.connect(self._on_page_changed)
        lay.addWidget(self.page_tabs, 1)

        row2 = QHBoxLayout()
        self.btn_all = QPushButton("全选本页")
        self.btn_none = QPushButton("清空选择")
        self.lbl_checked = QLabel("已选 0")
        self.btn_all.clicked.connect(lambda: self._set_all_checked(True))
        self.btn_none.clicked.connect(lambda: self._set_all_checked(False))
        self.lbl_checked.setStyleSheet("color:#6E7781;")
        for b in (self.btn_all, self.btn_none):
            fit_btn_width(b)
            row2.addWidget(b)
        row2.addWidget(self.lbl_checked, 1)
        lay.addLayout(row2)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setMinimumHeight(56)
        self.info_label.setStyleSheet("color:#6E7781; font-size:12px;")
        lay.addWidget(self.info_label)
        return panel

    def _build_center(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(6)
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self._build_command_page())
        self.center_stack.addWidget(self._build_eb_page())
        lay.addWidget(self.center_stack, 1)
        return panel

    def _build_command_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.lbl_cmd = QLabel("未选择命令")
        self.lbl_cmd.setWordWrap(True)
        f = QFont(); f.setBold(True); self.lbl_cmd.setFont(f)
        lay.addWidget(self.lbl_cmd)

        self.cmd_fields_host = QWidget()
        self.cmd_fields_layout = QVBoxLayout(self.cmd_fields_host)
        self.cmd_fields_layout.setContentsMargins(0, 0, 0, 0)
        self.cmd_fields_layout.setSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.cmd_fields_host)
        lay.addWidget(scroll, 1)

        self.edit_raw_data = QLineEdit()
        self.edit_raw_data.setPlaceholderText(
            "数据单元附加字节 HEX（仅上行模拟命令需要；下行命令留空）")
        self.edit_raw_data.textChanged.connect(self._refresh_preview)
        raw_row = QHBoxLayout()
        raw_row.addWidget(QLabel("附加数据"))
        raw_row.addWidget(self.edit_raw_data, 1)
        lay.addLayout(raw_row)

        self.plain_cmd_preview = QPlainTextEdit()
        self.plain_cmd_preview.setReadOnly(True)
        self.plain_cmd_preview.setMaximumHeight(70)
        self.plain_cmd_preview.setPlaceholderText("帧预览")
        lay.addWidget(self.plain_cmd_preview)

        row = QHBoxLayout()
        self.btn_send = QPushButton("发送")
        self.btn_send.clicked.connect(self._on_send)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        self.btn_edit_raw = QPushButton("编辑数据单元…")
        self.btn_edit_raw.clicked.connect(self._on_edit_raw_focus)
        for b in (self.btn_send, self.btn_stop, self.btn_edit_raw):
            fit_btn_width(b)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        return page

    def _build_eb_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.lbl_eb = QLabel("未选择 EB 数据标识")
        f = QFont(); f.setBold(True); self.lbl_eb.setFont(f)
        self.lbl_eb.setWordWrap(True)
        lay.addWidget(self.lbl_eb)

        box = QGroupBox("645 帧与传输方式")
        grid = QGridLayout(box)
        grid.setContentsMargins(8, 4, 8, 4)
        self.edit_eb_addr = QLineEdit(); self.edit_eb_addr.setMaxLength(12)
        self.edit_eb_addr.editingFinished.connect(self._schedule_save)
        self.combo_eb_ctrl = QComboBox()
        self.combo_eb_ctrl.addItem("11H 读数据", 0x11)
        self.combo_eb_ctrl.addItem("14H 写数据", 0x14)
        self.combo_eb_wrap = QComboBox()
        self.combo_eb_wrap.addItem("转发帧（AFN=02H F1）", True)
        self.combo_eb_wrap.addItem("裸 645 帧", False)
        grid.addWidget(QLabel("645 地址"), 0, 0)
        grid.addWidget(self.edit_eb_addr, 0, 1)
        grid.addWidget(QLabel("控制码"), 0, 2)
        grid.addWidget(self.combo_eb_ctrl, 0, 3)
        grid.addWidget(QLabel("外层"), 0, 4)
        grid.addWidget(self.combo_eb_wrap, 0, 5)
        grid.setColumnStretch(6, 1)
        lay.addWidget(box)

        self.eb_fields_host = QWidget()
        self.eb_fields_layout = QVBoxLayout(self.eb_fields_host)
        self.eb_fields_layout.setContentsMargins(0, 0, 0, 0)
        self.eb_fields_layout.setSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.eb_fields_host)
        lay.addWidget(scroll, 1)

        self.edit_eb_raw = QLineEdit()
        self.edit_eb_raw.setPlaceholderText("数据内容 HEX（无字段定义的 DI 用这个）")
        self.edit_eb_raw.textChanged.connect(self._refresh_preview)
        raw_row = QHBoxLayout()
        raw_row.addWidget(QLabel("数据内容"))
        raw_row.addWidget(self.edit_eb_raw, 1)
        lay.addLayout(raw_row)

        self.plain_eb_preview = QPlainTextEdit()
        self.plain_eb_preview.setReadOnly(True)
        self.plain_eb_preview.setMaximumHeight(70)
        lay.addWidget(self.plain_eb_preview)

        row = QHBoxLayout()
        self.btn_eb_send = QPushButton("发送")
        self.btn_eb_send.clicked.connect(self._on_send)
        self.btn_eb_stop = QPushButton("停止")
        self.btn_eb_stop.clicked.connect(self._on_stop)
        self.btn_eb_stop.setEnabled(False)
        for b in (self.btn_eb_send, self.btn_eb_stop):
            fit_btn_width(b)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        return page

    def _build_log_panel(self) -> QWidget:
        box = QGroupBox("收发日志")
        box.setMinimumWidth(280)
        self.log_group = box
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(LOG_MIN_HEIGHT)
        self.log_text.setMaximumBlockCount(LOG_MAX_BLOCKS)
        self.log_text.setFont(QFont("Consolas", 9))
        lay.addWidget(self.log_text, 1)
        row = QHBoxLayout()
        self.lbl_txrx = QLabel("TX 0 帧 / RX 0 帧")
        row.addWidget(self.lbl_txrx)
        row.addStretch(1)
        lay.addLayout(row)
        return box

    def _build_detail(self) -> QWidget:
        self.detail_tabs = QTabWidget()
        self.detail_tabs.setMaximumHeight(DETAIL_MAX_HEIGHT)
        self.info_table = self._make_table(["时间", "结果", "说明"])
        self.raw_table = self._make_table(["时间", "方向", "长度", "报文"])
        self.raw_table.cellDoubleClicked.connect(self._on_raw_row_activated)
        self.detail_tabs.addTab(self.info_table, "信息表")
        self.detail_tabs.addTab(self.raw_table, "报文表")
        return self.detail_tabs

    @staticmethod
    def _make_table(headers: Sequence[str]) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(list(headers))
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        t.setAlternatingRowColors(True)
        return t

    # ── 主题 ────────────────────────────────────────────────────────────
    def restyle_for_theme(self, dark: bool) -> None:
        self._dark = bool(dark)
        p = LOG_PALETTES[self._dark]
        self.log_text.setStyleSheet(
            f"QPlainTextEdit{{background:{p['bg']};color:{p['fg']};"
            f"border:1px solid {p['border']};}}")
        for prev in (getattr(self, "plain_cmd_preview", None),
                     getattr(self, "plain_eb_preview", None)):
            if prev is not None:
                prev.setStyleSheet(
                    f"QPlainTextEdit{{background:{p['bg']};color:{p['fg']};"
                    f"border:1px solid {p['border']};}}")

    # ── 页面/树 ─────────────────────────────────────────────────────────
    def _on_page_changed(self, index: int) -> None:
        if index < 0:
            return
        page = core.PAGES[index][0]
        self._page = page
        self._ensure_tree(page)
        self.center_stack.setCurrentIndex(1 if page == core.PAGE_EB else 0)
        self._refresh_preview()
        self._update_checked_label()
        self._schedule_save()

    def _select_page(self, page: str, notify: bool = True) -> None:
        for i, (key, _label) in enumerate(core.PAGES):
            if key == page:
                if notify:
                    self.page_tabs.setCurrentIndex(i)
                else:
                    self.page_tabs.blockSignals(True)
                    self.page_tabs.setCurrentIndex(i)
                    self.page_tabs.blockSignals(False)
                    self._page = page
                    self._ensure_tree(page)
                    self.center_stack.setCurrentIndex(1 if page == core.PAGE_EB else 0)
                return

    def _ensure_tree(self, page: str) -> None:
        tree = self._trees.get(page)
        if tree is None or tree.topLevelItemCount():
            return
        tree.blockSignals(True)
        cats = core.catalog(page)
        if not cats:
            empty = QTreeWidgetItem([
                "（暂无自定义 AFN+Fn —— 可在「查询 → AFN查询」添加后回到本页刷新）", ""])
            empty.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tree.addTopLevelItem(empty)
            tree.blockSignals(False)
            self._apply_filter(self.edit_filter.text())
            return
        for cat in cats:
            c = QTreeWidgetItem([cat.name, ""])
            c.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = QFont(); font.setBold(True); c.setFont(0, font)
            tree.addTopLevelItem(c)
            for grp in cat.groups:
                g = QTreeWidgetItem([f"{grp.name}（{len(grp.items)}）", ""])
                g.setFlags(Qt.ItemFlag.ItemIsEnabled)
                c.addChild(g)
                for item in grp.items:
                    if isinstance(item, core.EbItem):
                        leaf = QTreeWidgetItem([item.label, "读/写"])
                        leaf.setData(0, LEAF_KEY_ROLE, ("eb", item.di))
                        leaf.setToolTip(0, f"{item.name}\n{item.usage}")
                        leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        leaf.setCheckState(0, Qt.CheckState.Unchecked)
                    else:
                        leaf = QTreeWidgetItem([item.label,
                                                "下行" if item.direction == "down" else "上行"])
                        leaf.setData(0, LEAF_KEY_ROLE, ("cmd", item.key))
                        leaf.setToolTip(0, _strip_html(item.doc) or item.name)
                        leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        leaf.setCheckState(0, Qt.CheckState.Unchecked)
                    g.addChild(leaf)
            c.setExpanded(page in (core.PAGE_EB, core.PAGE_CUSTOM))
        # 回归上次勾选
        for key in self._checked.get(page, []):
            leaf = self._find_leaf(tree, key)
            if leaf is not None:
                leaf.setCheckState(0, Qt.CheckState.Checked)
        tree.blockSignals(False)
        self._apply_filter(self.edit_filter.text())

    def _find_leaf(self, tree: QTreeWidget, key: str) -> Optional[QTreeWidgetItem]:
        it = QTreeWidgetItemIteratorHelper(tree)
        for node in it:
            data = node.data(0, LEAF_KEY_ROLE)
            if data and data[1] == key:
                return node
        return None

    def _iter_leaves(self, tree: QTreeWidget):
        stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
        while stack:
            node = stack.pop()
            if node.data(0, LEAF_KEY_ROLE):
                yield node
            else:
                stack.extend(node.child(i) for i in range(node.childCount()))

    def _on_tree_selection(self) -> None:
        tree = self._trees.get(self._page)
        if tree is None:
            return
        items = tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, LEAF_KEY_ROLE)
        if not data:
            return
        kind, key = data
        if kind == "eb":
            self._current_eb = next((e for e in core.eb_items() if e.di == key), None)
            self._current = None
            self._render_eb_fields()
        else:
            self._current = None
            for cmd in core.all_commands():
                if cmd.key == key:
                    self._current = cmd
                    break
            if self._current is None:
                self._current = next((c for c in core.custom_commands() if c.key == key), None)
            self._current_eb = None
            self._render_cmd_fields()
        self._refresh_preview()

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        if item and item.data(0, LEAF_KEY_ROLE):
            self._on_send()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0 or not item.data(0, LEAF_KEY_ROLE):
            return
        key = item.data(0, LEAF_KEY_ROLE)[1]
        lst = self._checked.setdefault(self._page, [])
        if item.checkState(0) == Qt.CheckState.Checked:
            if key not in lst:
                lst.append(key)
        else:
            if key in lst:
                lst.remove(key)
        self._update_checked_label()
        self._schedule_save()

    def _set_all_checked(self, checked: bool) -> None:
        tree = self._trees.get(self._page)
        if tree is None:
            return
        tree.blockSignals(True)
        for leaf in self._iter_leaves(tree):
            leaf.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        tree.blockSignals(False)
        self._checked[self._page] = ([leaf.data(0, LEAF_KEY_ROLE)[1]
                                      for leaf in self._iter_leaves(tree)] if checked else [])
        self._update_checked_label()
        self._schedule_save()

    def _update_checked_label(self) -> None:
        n = len(self._checked.get(self._page, []))
        total = core.leaf_count(self._page)
        self.lbl_checked.setText(f"已选 {n} / {total}")

    def _apply_filter(self, text: str) -> None:
        keyword = (text or "").strip().lower()
        tree = self._trees.get(self._page)
        if tree is None:
            return

        def visit(node: QTreeWidgetItem) -> bool:
            if node.data(0, LEAF_KEY_ROLE):
                hit = not keyword or keyword in node.text(0).lower() or keyword in node.toolTip(0).lower()
                node.setHidden(not hit)
                return hit
            hit = False
            for i in range(node.childCount()):
                hit = visit(node.child(i)) or hit
            node.setHidden(not hit and bool(keyword))
            if keyword and hit:
                node.setExpanded(True)
            return hit

        for i in range(tree.topLevelItemCount()):
            visit(tree.topLevelItem(i))

    # ── 动态字段 ────────────────────────────────────────────────────────
    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _render_cmd_fields(self) -> None:
        self._clear_layout(self.cmd_fields_layout)
        self._field_widgets = []
        cmd = self._current
        if cmd is None:
            self.lbl_cmd.setText("未选择命令")
            return
        src = f"[{cmd.source}] " if cmd.source != "标准" else ""
        self.lbl_cmd.setText(f"{src}{cmd.afn:02X}H F{cmd.fn} {cmd.name}"
                             f"（{'下行' if cmd.direction == 'down' else '上行'}）")
        self.info_label.setText(_strip_html(cmd.doc) or cmd.name)
        if not cmd.fields:
            tip = QLabel("该命令在 Schema 中没有数据单元字段。\n"
                         "下行命令可直接发送；模拟上行应答请在「附加数据」填数据单元 HEX。")
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#6E7781;")
            self.cmd_fields_layout.addWidget(tip)
        else:
            box = QGroupBox("数据单元")
            form = QFormLayout(box)
            form.setContentsMargins(8, 4, 8, 4)
            for fld in cmd.fields:
                w = self._make_field_widget(fld)
                self._field_widgets.append((fld, w, fld.get("default")))
                form.addRow(QLabel(str(fld.get("name"))), w)
            self.cmd_fields_layout.addWidget(box)
        self.cmd_fields_layout.addStretch(1)

    def _render_eb_fields(self) -> None:
        self._clear_layout(self.eb_fields_layout)
        self._eb_widgets = []
        item = self._current_eb
        if item is None:
            self.lbl_eb.setText("未选择 EB 数据标识")
            return
        self.lbl_eb.setText(f"{item.di} {item.name}（{item.fmt}/{item.length or '不定长'}B）")
        self.info_label.setText(item.usage or item.name)
        if item.fields:
            box = QGroupBox("数据内容（写入时编码；读请求忽略）")
            form = QFormLayout(box)
            form.setContentsMargins(8, 4, 8, 4)
            for fld in item.fields:
                w = self._make_eb_widget(fld)
                self._eb_widgets.append((fld, w))
                form.addRow(QLabel(str(fld.get("name"))), w)
            self.eb_fields_layout.addWidget(box)
        else:
            tip = QLabel("该 EB 数据标识没有字段定义，写入时请在「数据内容」填 HEX。")
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#6E7781;")
            self.eb_fields_layout.addWidget(tip)
        self.eb_fields_layout.addStretch(1)

    def _make_field_widget(self, fld: dict) -> QWidget:
        ftype = fld.get("type")
        default = fld.get("default")
        if ftype == "enum":
            combo = QComboBox()
            for k, label in (fld.get("enum_map") or {}).items():
                combo.addItem(f"{k} {label}", k)
            idx = combo.findData(str(default)) if default is not None else -1
            combo.setCurrentIndex(max(0, idx))
            combo.currentIndexChanged.connect(self._refresh_preview)
            return combo
        if ftype in ("uint8", "uint16", "uint32"):
            spin = QSpinBox()
            spin.setRange(0, 0xFF if ftype == "uint8" else (0xFFFF if ftype == "uint16" else 0x7FFFFFFF))
            try:
                spin.setValue(int(default or 0))
            except (TypeError, ValueError):
                pass
            spin.valueChanged.connect(self._refresh_preview)
            return spin
        if ftype == "list":
            edit = QLineEdit()
            edit.setPlaceholderText("列表字段：按「地址,地址…」逐行逗号分隔（留空=空列表）")
            edit.textChanged.connect(self._refresh_preview)
            return edit
        edit = QLineEdit()
        if ftype == "bcd":
            edit.setPlaceholderText(f"BCD {fld.get('length', '')} 字节（十六进制）")
        elif ftype == "bytes":
            edit.setPlaceholderText("HEX 字节（可带空格）")
        edit.setText("" if default is None else str(default))
        edit.textChanged.connect(self._refresh_preview)
        return edit

    def _make_eb_widget(self, fld: dict) -> QWidget:
        ftype = str(fld.get("type") or "")
        if ftype == "enum":
            combo = QComboBox()
            for k, label in (fld.get("enum_map") or {}).items():
                combo.addItem(f"{k} {label}", k)
            combo.currentIndexChanged.connect(self._refresh_preview)
            return combo
        if ftype == "bs8":
            edit = QLineEdit()
            edit.setPlaceholderText("位组合：hex 1 字节（如 C0）")
            edit.textChanged.connect(self._refresh_preview)
            return edit
        if ftype == "list":
            edit = QLineEdit()
            edit.setPlaceholderText("列表：每行一项，字段用逗号分隔（如 000000000001）")
            edit.textChanged.connect(self._refresh_preview)
            return edit
        edit = QLineEdit()
        hint = {"uint8": "0~255", "uint16": "0~65535", "uint24": "0~16777215",
                "uint32": "0~4294967295", "bcd": "hex BCD", "bcd_time": "YYMMDDhhmmss",
                "ascii": "ASCII", "hex": "HEX"}.get(ftype, ftype)
        edit.setPlaceholderText(f"{fld.get('name')}（{hint}）")
        edit.textChanged.connect(self._refresh_preview)
        return edit

    def _collect_values(self) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for fld, widget, _default in self._field_widgets:
            name = fld.get("name")
            ftype = fld.get("type")
            if isinstance(widget, QComboBox):
                values[name] = widget.currentData()
            elif isinstance(widget, QSpinBox):
                values[name] = widget.value()
            else:
                text = widget.text().strip()
                if ftype == "list":
                    items = []
                    for line in text.replace("；", "\n").splitlines():
                        parts = [p.strip() for p in line.replace("，", ",").split(",") if p.strip()]
                        if not parts:
                            continue
                        row = {}
                        for sub, val in zip(fld.get("item_fields") or (), parts):
                            row[sub.get("name")] = val
                        items.append(row)
                    values[name] = items
                else:
                    values[name] = text
        return values

    def _collect_eb_values(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for fld, widget in self._eb_widgets:
            name = fld.get("name")
            if isinstance(widget, QComboBox):
                out[name] = widget.currentData()
            elif isinstance(widget, QLineEdit):
                out[name] = widget.text().strip()
        return out

    # ── 组帧 ────────────────────────────────────────────────────────────
    def _info_config(self) -> Dict[str, Any]:
        return {
            "通信模块标识": self.combo_module.currentData() or 0,
            "中继级别": self.spin_relay.value(),
            "报文序列号": self.spin_seq.value(),
        }

    def _relay_addrs(self) -> List[str]:
        level = self.spin_relay.value()
        return [DEFAULTS["relay_addrs"][0]] * level

    def _build_current_frame(self) -> bytes:
        if self._page == core.PAGE_EB:
            return self._build_eb_frame()
        cmd = self._current
        if cmd is None:
            raise core.FrameBuildError("未选择命令")
        raw = b""
        text = self.edit_raw_data.text().strip()
        if text:
            raw = _parse_hex(text)
        return core.build_frame(
            cmd, self._collect_values(),
            src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
            relay=self._relay_addrs(), info=self._info_config(), raw_data=raw,
        )

    def _build_eb_frame(self) -> bytes:
        item = self._current_eb
        if item is None:
            raise core.FrameBuildError("未选择 EB 数据标识")
        data = b""
        ctrl = self.combo_eb_ctrl.currentData()
        raw_text = self.edit_eb_raw.text().strip()
        if raw_text:
            data = _parse_hex(raw_text)
        elif item.fields:
            data = core.encode_eb_data(item.di, self._collect_eb_values())
        return core.build_eb_frame(
            item.di, addr=self.edit_eb_addr.text().strip(), ctrl=ctrl, data=data,
            wrap=bool(self.combo_eb_wrap.currentData()),
            src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
            info=self._info_config(),
        )

    def _refresh_preview(self, *_args) -> None:
        target = self.plain_eb_preview if self._page == core.PAGE_EB else self.plain_cmd_preview
        try:
            frame = self._build_current_frame()
        except core.FrameBuildError as exc:
            target.setPlainText(f"⚠ {exc}")
            return
        except Exception as exc:                       # 生成器未知异常也不崩页面
            target.setPlainText(f"⚠ 组帧异常：{type(exc).__name__}: {exc}")
            return
        target.setPlainText(f"({len(frame)} 字节)\n{_fmt(frame)}")

    def _on_edit_raw_focus(self) -> None:
        self.edit_raw_data.setFocus()

    # ── 发送队列 ────────────────────────────────────────────────────────
    def _targets(self) -> List[Tuple[str, str]]:
        checked = self._checked.get(self._page, [])
        if checked:
            return [(self._page, key) for key in checked]
        if self._page == core.PAGE_EB and self._current_eb is not None:
            return [(self._page, self._current_eb.di)]
        if self._current is not None:
            return [(self._page, self._current.key)]
        return []

    def _on_send(self) -> None:
        if self._awaiting or self._next_timer.isActive():
            self._log("[提示] 正在等待上一帧应答，稍后再发", "warn")
            return
        if not self._channel.ready():
            reason = self._channel.state_text() or "通道未就绪"
            self._log(f"[失败] {reason}", "fail")
            QMessageBox.warning(self, "通道未就绪", reason)
            return
        targets = self._targets()
        if not targets:
            QMessageBox.information(self, "提示", "请先在左侧选择（或勾选）要发送的命令")
            return
        self._queue_commands = targets
        self._queue_idx = 0
        self._sent = 0
        self._set_running(True)
        self._log(f"[信息] 开始发送 {len(targets)} 条命令", "info")
        self._send_next()

    def _send_next(self) -> None:
        if self._awaiting:
            return
        if self._queue_idx >= len(self._queue_commands):
            self._finish_queue()
            return
        page, key = self._queue_commands[self._queue_idx]
        try:
            frame = self._build_frame_for(page, key)
        except core.FrameBuildError as exc:
            self._log(f"[失败] {key} 组帧失败：{exc}", "fail")
            self._add_info_row("组帧失败", str(exc))
            self._advance()
            return
        self._awaiting = True
        self._attempt = 0
        self._pending_frame = frame
        self._pending_key = key
        self._pending_page = page
        self._send_frame(frame, key)

    def _build_frame_for(self, page: str, key: str) -> bytes:
        if page == core.PAGE_EB:
            item = next((e for e in core.eb_items() if e.di == key), None)
            if item is None:
                raise core.FrameBuildError(f"未找到 EB 数据标识 {key}")
            data = b""
            if self.combo_eb_ctrl.currentData() == 0x14 and item.fields:
                data = core.encode_eb_data(item.di, self._collect_eb_values())
            elif self.edit_eb_raw.text().strip():
                data = _parse_hex(self.edit_eb_raw.text())
            return core.build_eb_frame(
                item.di, addr=self.edit_eb_addr.text().strip(),
                ctrl=self.combo_eb_ctrl.currentData(), data=data,
                wrap=bool(self.combo_eb_wrap.currentData()),
                src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
                info=self._info_config(),
            )
        cmd = next((c for c in core.all_commands() if c.key == key), None)
        if cmd is None:
            cmd = next((c for c in core.custom_commands() if c.key == key), None)
        if cmd is None:
            raise core.FrameBuildError(f"未找到命令 {key}")
        raw = b""
        if self.edit_raw_data.text().strip():
            raw = _parse_hex(self.edit_raw_data.text())
        return core.build_frame(
            cmd, self._collect_values(),
            src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
            relay=self._relay_addrs(), info=self._info_config(), raw_data=raw,
        )

    def _send_frame(self, frame: bytes, key: str) -> None:
        ok, reason = self._channel.send(frame)
        if not ok:
            self._log(f"[失败] {key} 发送失败：{reason}", "fail")
            self._add_info_row("发送失败", f"{key}：{reason}")
            self._awaiting = False
            self._advance()
            return
        self._sent += 1
        self.spin_seq.setValue((self.spin_seq.value() + 1) & 0xFF)
        self._add_raw_row("TX", frame)
        self._log(f"[TX] {key} ({len(frame)}B) {_fmt(frame)}", "tx")
        self._timeout_timer.start(max(100, self.spin_timeout.value()))
        self._update_txrx()

    def _advance(self) -> None:
        self._timeout_timer.stop()
        self._queue_idx += 1
        self._next_timer.start()

    def _finish_queue(self) -> None:
        self._set_running(False)
        self._log(f"[信息] 本轮结束：共发送 {self._sent} 帧", "info")

    def _on_reply_timeout(self) -> None:
        if not self._awaiting:
            return
        retries = self.spin_retries.value()
        if self._attempt < retries:
            self._attempt += 1
            self._log(f"[超时] {self._pending_key} 未收到应答，"
                      f"重试 {self._attempt}/{retries}", "warn")
            # 重发同一帧（不重新组帧，避免上一轮定时器把新一轮提前发出）
            self._send_frame(self._pending_frame, self._pending_key)
            return
        self._log(f"[超时] {self._pending_key} 重试用尽（{retries} 次）", "fail")
        self._add_info_row("超时", f"{self._pending_key}：{self.spin_timeout.value()}ms 内无应答")
        self._awaiting = False
        self._advance()

    def _on_stop(self) -> None:
        if not (self._awaiting or self._next_timer.isActive()):
            return
        self._timeout_timer.stop()
        self._next_timer.stop()
        self._awaiting = False
        self._log("[信息] 已停止发送", "info")
        self._add_info_row("已停止", f"已发送 {self._sent} 帧")
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self.btn_send.setEnabled(not running)
        self.btn_eb_send.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_eb_stop.setEnabled(running)

    # ── 接收 ────────────────────────────────────────────────────────────
    def _on_rx_data(self, data: bytes) -> None:
        if not data:
            return
        self._rx_buf.extend(data)
        if len(self._rx_buf) > RX_BUF_MAX:
            self._log("[警告] 接收缓冲超限，已丢弃旧数据", "warn")
            del self._rx_buf[:len(self._rx_buf) - RX_BUF_MAX]
        while self._rx_buf:
            need = frame_deframe.frame_length_for(DEFRAME_STRATEGY, bytes(self._rx_buf))
            if need and len(self._rx_buf) >= need:
                frame = bytes(self._rx_buf[:need])
                del self._rx_buf[:need]
                if frame[-1] != 0x16:
                    continue
                self._on_frame(frame)
                continue
            if need:
                if frame_deframe.frame_incomplete(DEFRAME_STRATEGY, bytes(self._rx_buf)):
                    return
            # 无法成帧：丢到下一个可能的帧起点（68 / FE）
            drop = 1
            for i in range(1, len(self._rx_buf)):
                if self._rx_buf[i] in (0x68, 0xFE):
                    drop = i
                    break
            else:
                drop = len(self._rx_buf)
            del self._rx_buf[:drop]
            if not self._rx_buf:
                return

    def _on_frame(self, frame: bytes) -> None:
        self._add_raw_row("RX", frame)
        self._log(f"[RX] ({len(frame)}B) {_fmt(frame)}", "ok")
        if not self._awaiting or not self._queue_commands:
            self._log("  → 忽略（当前没有在等应答）", "warn")
            return
        page, key = self._pending_page, self._pending_key
        if page == core.PAGE_EB:
            # EB 命令是 645 帧（可包在 AFN=02H F1 里）：本页只确认「收到了一帧」，
            # 业务含义交给解析器/单帧解析页 —— 没有可自证的字段级成功判据。
            rows = core.parse_table(frame)
            result = {"ok": None, "matched": bool(frame),
                      "reason": "已接收 EB 响应（未做字段级判定）", "rows": rows}
        else:
            cmd = next((c for c in core.all_commands() if c.key == key), None) \
                or next((c for c in core.custom_commands() if c.key == key), None)
            if cmd is None:
                return
            result = core.evaluate_response(cmd, frame)
        self._timeout_timer.stop()
        if not result.get("matched"):
            self._log(f"  → 忽略（{result.get('reason')}）", "warn")
            self._timeout_timer.start(max(100, self.spin_timeout.value()))
            return
        ok = result.get("ok")
        text = "成功" if ok is True else ("失败" if ok is False else "已接收（未做字段级判定）")
        kind = "ok" if ok is True else ("fail" if ok is False else "info")
        self._log(f"  → {text}：{result.get('reason')}", kind)
        self._add_info_row(text, f"{key}：{result.get('reason')}")
        self._show_detail(result.get("rows") or [])
        self._awaiting = False
        self._advance()

    # ── 展示 ────────────────────────────────────────────────────────────
    def _update_txrx(self) -> None:
        rx = self.raw_table.rowCount() - self._sent
        self.lbl_txrx.setText(f"TX {self._sent} 帧 / RX {max(0, rx)} 帧")

    def _add_raw_row(self, direction: str, frame: bytes) -> None:
        if self.raw_table.rowCount() >= RAW_ROW_LIMIT:
            self.raw_table.removeRow(0)
            if self._frame_rows:
                self._frame_rows.pop(0)
        row = self.raw_table.rowCount()
        self.raw_table.insertRow(row)
        self.raw_table.setItem(row, 0, QTableWidgetItem(self._now()))
        self.raw_table.setItem(row, 1, QTableWidgetItem(direction))
        self.raw_table.setItem(row, 2, QTableWidgetItem(str(len(frame))))
        item = QTableWidgetItem(_fmt(frame, limit=0))
        item.setData(Qt.ItemDataRole.UserRole, len(self._frame_rows))
        self.raw_table.setItem(row, 3, item)
        self._frame_rows.append(bytes(frame))
        self.raw_table.scrollToBottom()

    def _on_raw_row_activated(self, row: int, _col: int) -> None:
        item = self.raw_table.item(row, 3)
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._frame_rows):
            return
        frame = self._frame_rows[idx]
        self.frame_to_single_parse.emit(core.format_hex(frame))
        if self._single_handler is not None:
            try:
                self._single_handler(core.format_hex(frame))
            except Exception:
                pass

    def _add_info_row(self, result: str, detail: str) -> None:
        row = self.info_table.rowCount()
        self.info_table.insertRow(row)
        self.info_table.setItem(row, 0, QTableWidgetItem(self._now()))
        self.info_table.setItem(row, 1, QTableWidgetItem(result))
        self.info_table.setItem(row, 2, QTableWidgetItem(detail))
        self.info_table.scrollToBottom()

    def _show_detail(self, rows: Sequence[Tuple]) -> None:
        if not rows:
            return
        for line in core.detail_lines(rows)[:60]:
            self._log("   " + line.strip(), "hint")

    def _log(self, text: str, kind: str = "info") -> None:
        """按类别着色追加一行（QPlainTextEdit 不认 QSS 颜色，必须走字符格式）。"""
        palette = LOG_PALETTES[self._dark]
        color = {"ok": palette["ok"], "fail": palette["fail"], "warn": palette["warn"],
                 "tx": palette["tx"], "hint": palette["hint"]}.get(kind, palette["info"])
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(Qt.GlobalColor.black)
        from PySide6.QtGui import QColor
        fmt.setForeground(QColor(color))
        cursor.insertText(text + "\n", fmt)
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _on_clear(self) -> None:
        self.log_text.clear()
        self.info_table.setRowCount(0)
        self.raw_table.setRowCount(0)
        self._frame_rows.clear()
        self._sent = 0
        self._update_txrx()

    # ── 通道下拉 ────────────────────────────────────────────────────────
    def _on_channel_combo_changed(self, index: int) -> None:
        value = self.combo_channel.itemData(index)
        if self._channel.channel != value:
            self._channel.set_channel(value)
        self._schedule_save()

    # ── 持久化 ──────────────────────────────────────────────────────────
    def _config_path(self):
        return app_paths.data_path(CONFIG_NAME)

    def _collect_settings(self) -> Dict[str, Any]:
        return {
            "version": CONFIG_VERSION,
            "src": self.edit_src.text().strip(),
            "dst": self.edit_dst.text().strip(),
            "module_flag": int(self.combo_module.currentData() or 0),
            "relay_level": self.spin_relay.value(),
            "seq": self.spin_seq.value(),
            "timeout_ms": self.spin_timeout.value(),
            "retries": self.spin_retries.value(),
            "channel": self._channel.channel,
            "page": self._page,
            "eb_addr": self.edit_eb_addr.text().strip(),
            "eb_ctrl": int(self.combo_eb_ctrl.currentData() or 0x11),
            "eb_wrap": bool(self.combo_eb_wrap.currentData()),
            "checked": {k: list(v) for k, v in self._checked.items() if v},
            "split_sizes": list(self.main_split.sizes()) or list(DEFAULTS["split_sizes"]),
        }

    def _schedule_save(self, *_args) -> None:
        if self._save_timer is not None:
            self._save_timer.start()

    def _save_persisted(self) -> None:
        try:
            atomic_write_json(self._config_path(), self._collect_settings())
        except Exception as exc:
            self._log(f"[警告] 保存配置失败：{exc}", "warn")

    def _load_persisted(self) -> None:
        data: Dict[str, Any] = {}
        try:
            path = self._config_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception:
            data = {}
        merged = dict(DEFAULTS)
        for k, v in data.items():
            if k in DEFAULTS and v is not None:
                if k in ("module_flag", "relay_level", "seq", "timeout_ms", "retries",
                         "eb_ctrl"):
                    try:
                        v = int(v)
                    except (TypeError, ValueError):
                        continue
                if k in ("eb_wrap", "detail"):
                    v = bool(v)
                merged[k] = v
        if merged.get("channel") not in (ch.SERIAL, ch.BLUETOOTH):
            merged["channel"] = ch.DEFAULT_CHANNEL
        if merged.get("page") not in core.PAGE_LABELS:
            merged["page"] = core.PAGE_READ

        self.edit_src.setText(str(merged["src"]))
        self.edit_dst.setText(str(merged["dst"]))
        idx = self.combo_module.findData(int(merged["module_flag"]))
        self.combo_module.setCurrentIndex(max(0, idx))
        self.spin_relay.setValue(int(merged["relay_level"]))
        self.spin_seq.setValue(int(merged["seq"]))
        self.spin_timeout.setValue(int(merged["timeout_ms"]))
        self.spin_retries.setValue(int(merged["retries"]))
        self.edit_eb_addr.setText(str(merged["eb_addr"]))
        cidx = self.combo_eb_ctrl.findData(int(merged["eb_ctrl"]))
        self.combo_eb_ctrl.setCurrentIndex(max(0, cidx))
        self.combo_eb_wrap.setCurrentIndex(0 if merged["eb_wrap"] else 1)
        ch_idx = self.combo_channel.findData(merged["channel"])
        self.combo_channel.setCurrentIndex(max(0, ch_idx))
        if self._channel.channel != merged["channel"]:
            self._channel.set_channel(merged["channel"])
        checked = merged.get("checked")
        self._checked = {k: list(v) for k, v in checked.items() if isinstance(v, list)} \
            if isinstance(checked, dict) else {}
        sizes = merged.get("split_sizes")
        if not (isinstance(sizes, list) and len(sizes) == 3):
            sizes = list(DEFAULTS["split_sizes"])
        else:
            try:
                sizes = [int(v) for v in sizes]
            except (TypeError, ValueError):
                sizes = list(DEFAULTS["split_sizes"])
        QTimer.singleShot(0, lambda: self._apply_splits(sizes))
        self._page = merged["page"]

    def _apply_splits(self, sizes: Sequence[int]) -> None:
        total = max(sum(sizes), self.main_split.width())
        sizes = [max(200, int(v)) for v in sizes[:3]]
        grow = max(0, total - sum(sizes))
        sizes[-1] += grow                      # 余量给日志（最右）
        self.main_split.setSizes(sizes)

    # ── 收尾 ────────────────────────────────────────────────────────────
    def cleanup(self) -> None:
        self._timeout_timer.stop()
        self._next_timer.stop()
        self._awaiting = False
        self._save_persisted()
        self._channel.cleanup()


# ── 小工具 ─────────────────────────────────────────────────────────────
class QTreeWidgetItemIteratorHelper:
    """宽优先遍历 QTreeWidget（Qt 自带迭代器在 PySide6 下容易被 GC 掉）。"""

    def __init__(self, tree: QTreeWidget):
        self._nodes = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]

    def __iter__(self):
        while self._nodes:
            node = self._nodes.pop(0)
            yield node
            self._nodes.extend(node.child(i) for i in range(node.childCount()))


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text or "").replace("&nbsp;", " ").strip()
