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
- **每条命令的参数各自存档**（:mod:`gdw_test_store` 的 ``ParamStore``）：切换命令时自动存/取，
  与默认值相同即删除条目，所以「清理所有参数」不会被立刻写回。发送队列**必须**用
  ``_values_for(key)`` 取该命令自己的存档值 —— 用当前控件值会把上一条命令的参数套给所有命令。
- **支持统计**（同文件的 ``stats`` 段）：``evaluate_response`` 的结果经
  :func:`gdw_test_store.classify_result` 归一成五态，「支持统计」页只看这份记录。
- **日志落盘**（``SessionLog``）：每条日志按 ``[时间] 文本`` 追加到 ``logs/gdw_test_YYYYMMDD.log``；
  面板只显示本次会话，历史靠「导出日志」「打开日志目录」。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QTextCharFormat,
                          QTextCursor)
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

import app_icons
import app_paths
import channel_link as ch
import collapsible_section
import frame_deframe
import gdw_test_core as core
import gdw_test_expect as expect_mod
import gdw_test_network as net_mod
import gdw_test_report as report_mod
import gdw_test_store as store
from atomic_io import atomic_write_json
from gui_utils import fit_btn_width

CONFIG_NAME = "gdw_testbench.json"
CONFIG_VERSION = 1
DEFRAME_STRATEGY = "ft12_68"
RX_BUF_MAX = 64 * 1024
RAW_ROW_LIMIT = 2000
LOG_MAX_BLOCKS = 4000
#: 测试系统回确认帧（00H F1）时填的「等待时间」，单位 s（表 9 注：应不超过 5s；用户口径 1s）
ACK_WAIT_SECONDS = 1
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
    #: 折叠区展开状态 {key: bool}（``collapsible_section.collect_state``）
    "sections": {},
    #: 从节点模拟（虚拟表）的串口参数 —— 现场一般固定，随配置存档
    "sta_port": "",
    "sta_baud": "115200",
    "sta_parity": "N",
    "sta_stop": "1",
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
        #: 渲染后控件的「默认态」——判断用户是否改过参数（改过才落存档）
        self._fresh_ui: Dict[str, Any] = {}
        self._fresh_eb_ui: Dict[str, Any] = {}
        #: 每条命令的参数存档 + 支持统计（同一份 JSON），本次会话日志落盘
        self._params = store.ParamStore(app_paths.data_path(store.PARAMS_NAME))
        self._session_log = store.SessionLog(app_paths.data_path(store.LOG_DIR))
        #: 组网参数（1 对 2 测试网络）—— 随存档落盘
        self._net = net_mod.NetworkConfig.from_dict(self._params.get_network())
        #: 交互明细（报告用）与本次遍历开始时间
        self._interactions: List[Dict[str, Any]] = []
        self._session_started = ""
        self._pending_node = ""
        self._pending_confirmed = False   # 抄表类已收到确认，正在等数据
        self._pending_saw_other = False    # 等待期间收到过无关帧
        self._last_summary: Dict[str, Any] = {}
        self._trees: Dict[str, QTreeWidget] = {}
        self._queue_commands: List[Tuple[str, str]] = []
        self._queue_overrides: Dict[str, Dict[str, Any]] = {}
        self._preflight: Optional[Dict[str, Any]] = None
        self._joined_addrs: List[str] = []
        self._archive_seen: List[str] = []
        self._flow_runner = None
        self._flow_action = None
        self._flow_case = None
        self._flow_sent = False
        self._flow_queue: List[Any] = []
        #: 流程用例的测试结果 {fid: "通过"/"失败"/"跳过"/"进行中"/"未执行"}（左树第三列）
        self._flow_results: Dict[str, str] = {}
        #: 每条用例的**逐步执行快照** {fid: {states, notes, current}}：跑完再点回去能看记录
        self._flow_history: Dict[str, Dict[str, Any]] = {}
        #: KIND_SERVE 步已自动应答的次数（14H F1 回抄读内容 / 14H F2 回时间）
        self._flow_served = 0
        self._flow_overrides: Dict[str, Dict[str, Any]] = {}
        #: STA 复位下发通道（由主程序注入：协议8 虚拟表页的串口）；None 时退回本页串口
        self._sta_reset_provider = None
        #: 本页内建的从节点模拟服务（虚拟表 645 / 698，独立串口）
        self._sta_sim = None
        self._flow_poll_step = None
        self._flow_poll_deadline = 0.0
        #: 流程期间的收帧缓存 [(时间, afn, fn, 已消费)] —— 早到的上行（如 01H F1 后
        #: CCO 立刻上报 03H F10）必须在进入 wait 时能被认到，否则会「一直等不到」
        self._flow_rx_buffer: List[List[Any]] = []
        #: 最近一条 14H F3 上行（延时修正请求）→ {addr, delay_ms, content}
        self._flow_delay_req: Optional[Dict[str, Any]] = None
        self._flow_timer = QTimer(self)
        self._flow_timer.setSingleShot(True)
        self._flow_timer.timeout.connect(self._on_flow_timeout)
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
        self._refresh_stats()
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

    def set_sta_reset_provider(self, provider) -> None:
        """注入「下发 STA 复位」的通道：``provider(frame: bytes) -> bool``。

        主程序把协议8 虚拟表页的串口发帧能力包一层传进来（那才是 STA 总线）；
        未注入或返回 False 时，流程页退回本页串口下发。
        """
        self._sta_reset_provider = provider

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
        """通道状态：只用一个串口图标 + 颜色表示（完整文案放 tooltip）。

        用户口径（2026-10-28）：串口状态不需要那么多文字，图标 + 颜色足够，
        细节（端口/波特率在哪设、蓝牙要连哪）留在悬浮提示里，不占版面。
        """
        self._channel_state_text = str(text or "")
        self.lbl_channel_state.setPixmap(self._channel_state_pixmap(ready))
        self.lbl_channel_state.setToolTip(self._channel_state_text or "通道状态")
        self.lbl_channel_state.setAccessibleName(text or "")

    @staticmethod
    def _channel_state_pixmap(ready: bool):
        """通道状态图标：已连接=绿色插头，未连接=红色断头 + 断线标记。"""
        name = "plug" if ready else "unplug"
        color = "#1A7F37" if ready else "#B42318"
        size = 14
        try:
            return app_icons.render_pixmap(name, size, color)
        except Exception:                            # noqa: BLE001
            from PySide6.QtGui import QPixmap

            return QPixmap(size, size)               # 图标缺失时留空位，不影响功能

    def _on_channel_switched(self, _channel: str) -> None:
        self._rx_buf.clear()

    # ── UI ─────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self._build_top_bar())
        root.addWidget(self._build_network_bar())

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
        """顶部参数区：**常用项常驻一行**，固定项收进折叠区（用户口径 2026-10-28）。

        常驻：通道图标 + 发送通道 + 序列号 / 超时 / 重试 + 两个清理按钮；
        「地址与重发」这类装好一次就不用再动的，折进 ``CollapsibleSection``，
        默认收起 —— 折叠状态随存档恢复。
        """
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self._build_common_row())

        self._sections: List[collapsible_section.CollapsibleSection] = []
        sec = collapsible_section.CollapsibleSection(
            "地址与模块标识（装好后一般不用改）", expanded=False,
            key="gdw_params_addr")
        sec.set_title_suffix("源地址 / 目的地址 / 模块标识 / 中继级别")
        sec.content_layout().addWidget(self._build_addr_grid())
        sec.toggled.connect(self._schedule_save)
        self._sections.append(sec)
        lay.addWidget(sec)
        return host

    def _build_common_row(self) -> QWidget:
        """常驻行：通道（含状态图标）+ 重发参数 + 清理按钮，全部一行对齐。"""
        box = QGroupBox("测试参数")
        grid = QGridLayout(box)
        grid.setContentsMargins(8, 4, 8, 4)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)

        self.combo_channel = QComboBox()
        self.combo_channel.addItem("串口", ch.SERIAL)
        self.combo_channel.addItem("蓝牙", ch.BLUETOOTH)
        self.combo_channel.currentIndexChanged.connect(self._on_channel_combo_changed)
        self.combo_channel.setFixedWidth(88)
        self.lbl_channel_state = QLabel("")
        self.lbl_channel_state.setFixedWidth(18)
        self.lbl_channel_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._channel_state_text = ""

        self.spin_seq = QSpinBox(); self.spin_seq.setRange(0, 255)
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(100, 60000)
        self.spin_timeout.setSuffix(" ms")
        self.spin_retries = QSpinBox(); self.spin_retries.setRange(0, 10)
        # 宽度按实际内容给足：过窄会把数字压在步进按钮下面（曾裁掉「181」）
        for w, width in ((self.spin_seq, 106), (self.spin_timeout, 112), (self.spin_retries, 76)):
            w.setFixedWidth(width)
            w.valueChanged.connect(self._schedule_save)

        self.btn_clear = QPushButton("清空日志/报文")
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_clear_params = QPushButton("清理所有参数")
        self.btn_clear_params.setToolTip(
            "清掉所有命令已记录的数据单元参数、附加数据与 EB 数据内容\n"
            "（全局测试参数：源/目的地址、序列号、超时、重试、通道，以及勾选与支持统计均保留）"
        )
        self.btn_clear_params.clicked.connect(self._on_clear_params)

        col = 0
        grid.addWidget(QLabel("发送通道"), 0, col); col += 1
        grid.addWidget(self.combo_channel, 0, col); col += 1
        grid.addWidget(self.lbl_channel_state, 0, col); col += 1
        grid.addWidget(QLabel("序列号"), 0, col); col += 1
        grid.addWidget(self.spin_seq, 0, col); col += 1
        grid.addWidget(QLabel("超时"), 0, col); col += 1
        grid.addWidget(self.spin_timeout, 0, col); col += 1
        grid.addWidget(QLabel("重试"), 0, col); col += 1
        grid.addWidget(self.spin_retries, 0, col); col += 1
        grid.setColumnStretch(col, 1)                      # 中间留白，按钮贴右
        col += 1
        grid.addWidget(self.btn_clear, 0, col); col += 1
        grid.addWidget(self.btn_clear_params, 0, col)
        for b in (self.btn_clear, self.btn_clear_params):
            fit_btn_width(b)
        return box

    def _build_addr_grid(self) -> QWidget:
        """折叠区内容：源/目的地址、模块标识、中继级别（2 列 × 2 行，整齐对齐）。"""
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        self.edit_src = QLineEdit(); self.edit_src.setMaxLength(12)
        self.edit_dst = QLineEdit(); self.edit_dst.setMaxLength(12)
        self.combo_module = QComboBox()
        self.combo_module.addItem("1（含地址域）", 1)
        self.combo_module.addItem("0（无地址域）", 0)
        self.spin_relay = QSpinBox(); self.spin_relay.setRange(0, 15)

        for w in (self.edit_src, self.edit_dst):
            w.setMinimumWidth(130)
            w.editingFinished.connect(self._schedule_save)
        self.combo_module.currentIndexChanged.connect(self._schedule_save)
        self.spin_relay.valueChanged.connect(self._schedule_save)

        grid.addWidget(QLabel("源地址"), 0, 0)
        grid.addWidget(self.edit_src, 0, 1)
        grid.addWidget(QLabel("目的地址"), 0, 2)
        grid.addWidget(self.edit_dst, 0, 3)
        grid.addWidget(QLabel("模块标识"), 1, 0)
        grid.addWidget(self.combo_module, 1, 1)
        grid.addWidget(QLabel("中继级别"), 1, 2)
        grid.addWidget(self.spin_relay, 1, 3)
        grid.setColumnStretch(4, 1)
        return host

    def _build_network_bar(self) -> QWidget:
        """组网参数（可折叠，默认展开）：从节点分行 + 网络参数一行 + 操作行。

        用户口径 2026-10-28：这些是要现场改的（表号/协议/启用/频段），保持展开；
        每行只用一条水平带，标签左对齐、控件等宽，避免上一条那种「一行塞 13 列」的挤。
        """
        self._sections = getattr(self, "_sections", [])
        sec = collapsible_section.CollapsibleSection(
            "组网参数（1 对 2 测试网络）", expanded=True, key="gdw_params_network")
        sec.set_title_suffix("从节点 / CCO 地址 / 载波与无线频段 · 建档与入网")
        sec.toggled.connect(self._schedule_save)
        self.network_section = sec

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(4)

        def _row() -> QHBoxLayout:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            return row

        def _add(row: QHBoxLayout, label: str, widget: QWidget) -> None:
            row.addWidget(QLabel(label))
            row.addWidget(widget)

        # ── 从节点（每个一行：地址 + 协议 + 启用，行内自带标签，不跨行对齐）──
        self.node_widgets: List[Dict[str, Any]] = []
        for idx in range(net_mod.MAX_SLAVES):
            addr = QLineEdit()
            addr.setMaxLength(net_mod.ADDR_LEN)
            addr.setPlaceholderText("12 位地址")
            addr.setFixedWidth(120)
            addr.editingFinished.connect(self._on_network_edited)
            proto = QComboBox()
            for key, label in net_mod.PROTO_LABELS.items():
                proto.addItem(label, key)
            proto.setFixedWidth(132)
            proto.currentIndexChanged.connect(self._on_network_edited)
            use = QCheckBox("启用")
            use.setChecked(True)
            use.toggled.connect(self._on_network_edited)
            row = _row()
            _add(row, f"从节点 {idx + 1}", addr)
            row.addWidget(proto)
            row.addWidget(use)
            row.addStretch(1)
            lay.addLayout(row)
            self.node_widgets.append({"addr": addr, "proto": proto, "use": use})

        # ── 网络参数（一行：CCO 地址 / 载波频段 / 无线调制 / 信道号 / 协商）──
        self.edit_cco_addr = QLineEdit()
        self.edit_cco_addr.setMaxLength(net_mod.ADDR_LEN)
        self.edit_cco_addr.setPlaceholderText("12 位")
        self.edit_cco_addr.setFixedWidth(120)
        self.edit_cco_addr.editingFinished.connect(self._on_network_edited)
        self.combo_carrier_band = QComboBox()
        for key, label in net_mod.CARRIER_BANDS.items():
            self.combo_carrier_band.addItem(f"{label}", key)
        self.combo_carrier_band.setFixedWidth(140)
        self.combo_carrier_band.currentIndexChanged.connect(self._on_network_edited)
        self.combo_radio_mod = QComboBox()
        for key, label in net_mod.RADIO_MODS.items():
            self.combo_radio_mod.addItem(f"{label}", key)
        self.combo_radio_mod.setFixedWidth(96)
        self.combo_radio_mod.currentIndexChanged.connect(self._on_network_edited)
        self.spin_radio_ch = QSpinBox()
        self.spin_radio_ch.setRange(0, 255)
        self.spin_radio_ch.setFixedWidth(66)
        self.spin_radio_ch.valueChanged.connect(self._on_network_edited)
        self.check_radio_neg = QCheckBox("信道协商")
        self.check_radio_neg.setChecked(True)
        self.check_radio_neg.toggled.connect(self._on_network_edited)

        net_row = _row()
        _add(net_row, "CCO 地址", self.edit_cco_addr)
        _add(net_row, "载波频段", self.combo_carrier_band)
        _add(net_row, "无线调制", self.combo_radio_mod)
        _add(net_row, "信道号", self.spin_radio_ch)
        net_row.addWidget(self.check_radio_neg)
        net_row.addStretch(1)
        lay.addLayout(net_row)

        # ── 选项 + 操作（一行，按钮贴右）──
        self.check_autofill = QCheckBox("按组网参数自动填充")
        self.check_autofill.setChecked(True)
        self.check_autofill.setToolTip(
            "把从节点/CCO/频段自动填进对应的命令字段（手改过的字段不受影响）")
        self.check_autofill.toggled.connect(self._on_network_edited)
        self.check_fanout = QCheckBox("按从节点展开")
        self.check_fanout.setChecked(True)
        self.check_fanout.setToolTip(
            "含单个节点地址字段的命令（如 52H F11 并发抄表、52H F1 转发、10H F3 路由查询）"
            "按启用的从节点各发一帧")
        self.check_fanout.toggled.connect(self._on_network_edited)

        # 前置流程：给被测 CCO 建档 → 查从节点信息 → 判入网（缺档案时多数路由命令只会被否认）
        self.btn_preflight = QPushButton("准备测试网络")
        self.btn_preflight.setToolTip(
            "① 01H F2 参数区初始化（清旧档案，避免 11H F1 回「表号重复」）\n"
            "② 11H F1 添加从节点（按组网参数建档）\n"
            "③ 10H F1 查模块档案总数\n"
            "④ 10H F2 查从节点信息（只核对档案加得对不对）\n"
            "⑤ 10H F20 查双模网络拓扑（**入网只看这个**）")
        self.btn_preflight.clicked.connect(self._on_preflight)
        self.lbl_join_state = QLabel("入网：未查询")
        self.lbl_join_state.setStyleSheet("color:#6E7781;")
        self.lbl_join_state.setToolTip(
            "入网 n/N 来自 10H F20 双模网络拓扑（角色有效才算在网）；\n"
            "档案 m/N 来自 10H F2，只表示模块里下装了哪些表，不代表已入网")

        opt_row = _row()
        opt_row.addWidget(self.check_autofill)
        opt_row.addWidget(self.check_fanout)
        opt_row.addStretch(1)
        opt_row.addWidget(self.lbl_join_state)
        opt_row.addWidget(self.btn_preflight)
        fit_btn_width(self.btn_preflight)
        lay.addLayout(opt_row)

        self.lbl_network_hint = QLabel("")
        self.lbl_network_hint.setStyleSheet("color:#6E7781;")
        self.lbl_network_hint.setWordWrap(True)
        lay.addWidget(self.lbl_network_hint)

        sec.content_layout().addWidget(host)
        self._sections.append(sec)
        return sec

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
            tree.setHeaderLabels(["命令 (AFN/Fn)", "方向", "测试结果"])
            tree.setColumnWidth(0, 250)
            tree.setColumnWidth(1, 56)
            tree.setColumnWidth(2, 84)
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
        self.btn_all_pages = QPushButton("全选所有页")
        self.btn_none_pages = QPushButton("清空所有页")
        self.btn_all_pages.setToolTip("五个页签（读取/设置/上报/EB/自定义）全部勾选")
        self.btn_none_pages.setToolTip("五个页签全部取消勾选")
        self.lbl_checked = QLabel("已选 0")
        self.btn_all.clicked.connect(lambda: self._set_all_checked(True))
        self.btn_none.clicked.connect(lambda: self._set_all_checked(False))
        self.btn_all_pages.clicked.connect(lambda: self._set_all_pages(True))
        self.btn_none_pages.clicked.connect(lambda: self._set_all_pages(False))
        self.lbl_checked.setStyleSheet("color:#6E7781;")
        for b in (self.btn_all, self.btn_none, self.btn_all_pages, self.btn_none_pages):
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
        self.center_stack.addWidget(self._build_flow_page())
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
        self.btn_log_export = QPushButton("导出日志")
        self.btn_log_export.setToolTip("把本次会话日志（含时间戳）另存为 txt")
        self.btn_log_export.clicked.connect(self._on_export_log)
        self.btn_log_dir = QPushButton("打开日志目录")
        self.btn_log_dir.setToolTip(
            f"每次日志都会自动追加到 {store.LOG_DIR}/gdw_test_YYYYMMDD.log")
        self.btn_log_dir.clicked.connect(self._on_open_log_dir)
        for b in (self.btn_log_export, self.btn_log_dir):
            fit_btn_width(b)
            row.addWidget(b)
        lay.addLayout(row)
        return box

    def _build_detail(self) -> QWidget:
        self.detail_tabs = QTabWidget()
        self.detail_tabs.setMaximumHeight(DETAIL_MAX_HEIGHT)
        self.info_table = self._make_table(["时间", "命令", "从节点", "结果", "说明"])
        self.raw_table = self._make_table(["时间", "方向", "命令", "长度", "报文"])
        self.raw_table.cellDoubleClicked.connect(self._on_raw_row_activated)
        self.detail_tabs.addTab(self.info_table, "信息表")
        self.detail_tabs.addTab(self.raw_table, "报文表")
        self.detail_tabs.addTab(self._build_stats_page(), "支持统计")
        return self.detail_tabs

    def _build_stats_page(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(3)
        self.lbl_stats = QLabel("尚未统计")
        self.lbl_stats.setWordWrap(True)
        self.lbl_stats.setToolTip(
            "判定口径（Q/GDW 10376.2）：\n"
            "· 01H/04H/05H/11H/12H（及福建 51H/54H/55H）：收到 AFN=00H F1 确认即判支持；\n"
            "· 02H/03H/10H/13H/14H/15H、52H/53H、F0H/F1H 等抄读查询类：必须收到同 AFN/Fn 的上行数据；\n"
            "  只收到确认就超时的记「仅确认·无数据」，不算支持；\n"
            "· 否认帧按表 10 错误状态字判：4（信息类不存在）/10（主节点不支持此命令）→ 不支持；\n"
            "  其余（0 通信超时、9 主节点忙、11 从节点不应答、12 不在网内、109/110/111…）→ 支持但执行报错。\n"
            "· 上行命令（确认/否认应答、06H/56H 主动上报）由被测设备自己发出，本页不下发、"
            "不给支持结论，只在报告附录列出。")
        row = QHBoxLayout()
        row.addWidget(self.lbl_stats, 1)
        self.btn_stats_refresh = QPushButton("刷新")
        self.btn_stats_export = QPushButton("导出 CSV")
        self.btn_stats_report = QPushButton("生成报告")
        self.btn_stats_clear = QPushButton("清空统计")
        self.btn_stats_refresh.setToolTip("按当前存档重新汇总（AFN/Fn 支持情况）")
        self.btn_stats_export.setToolTip("把支持统计导出为 CSV（带 BOM，Excel 可直接打开）")
        self.btn_stats_report.setToolTip(
            "导出遍历测试报告（单文件 HTML）：测试环境 + AFN 支持汇总 + 逐条结果 + 交互报文")
        self.btn_stats_clear.setToolTip("只清支持统计记录，不动命令参数与日志")
        self.btn_stats_refresh.clicked.connect(self._refresh_stats)
        self.btn_stats_export.clicked.connect(self._on_export_stats)
        self.btn_stats_report.clicked.connect(self._on_export_report)
        self.btn_stats_clear.clicked.connect(self._on_clear_stats)
        for b in (self.btn_stats_refresh, self.btn_stats_export,
                  self.btn_stats_report, self.btn_stats_clear):
            fit_btn_width(b)
            row.addWidget(b)
        lay.addLayout(row)
        self.stats_table = self._make_table(list(store.STATS_HEADERS))
        lay.addWidget(self.stats_table, 1)
        return host

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
        self.center_stack.setCurrentIndex(
            2 if page == core.PAGE_FLOW else 1 if page == core.PAGE_EB else 0)
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
                    self.center_stack.setCurrentIndex(
            2 if page == core.PAGE_FLOW else 1 if page == core.PAGE_EB else 0)
                return

    def _ensure_tree(self, page: str) -> None:
        tree = self._trees.get(page)
        if tree is None or tree.topLevelItemCount():
            return
        tree.blockSignals(True)
        cats = core.catalog(page)
        if not cats:
            empty = QTreeWidgetItem([
                "（暂无自定义 AFN+Fn —— 可在「查询 → AFN查询」添加后回到本页刷新）", "", ""])
            empty.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tree.addTopLevelItem(empty)
            tree.blockSignals(False)
            self._apply_filter(self.edit_filter.text())
            return
        for cat in cats:
            c = QTreeWidgetItem([cat.name, "", ""])
            c.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            c.setCheckState(0, Qt.CheckState.Unchecked)
            font = QFont(); font.setBold(True); c.setFont(0, font)
            tree.addTopLevelItem(c)
            for grp in cat.groups:
                g = QTreeWidgetItem([f"{grp.name}（{len(grp.items)}）", "", ""])
                g.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                g.setCheckState(0, Qt.CheckState.Unchecked)
                c.addChild(g)
                for item in grp.items:
                    if isinstance(item, core.FlowItem):
                        # 第三列 = 该流程的测试结果（整条用例的结论，执行时实时更新）
                        leaf = QTreeWidgetItem([item.label, "流程", self._flow_result_of(item.key)])
                        leaf.setData(0, LEAF_KEY_ROLE, ("flow", item.key))
                        leaf.setToolTip(0, f"{item.name}\n{item.desc}")
                        leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        leaf.setCheckState(0, Qt.CheckState.Unchecked)
                    elif isinstance(item, core.EbItem):
                        leaf = QTreeWidgetItem([item.label, "读/写", ""])
                        leaf.setData(0, LEAF_KEY_ROLE, ("eb", item.di))
                        leaf.setToolTip(0, f"{item.name}\n{item.usage}")
                        leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        leaf.setCheckState(0, Qt.CheckState.Unchecked)
                    else:
                        leaf = QTreeWidgetItem([item.label,
                                                "下行" if item.direction == "down" else "上行", ""])
                        leaf.setData(0, LEAF_KEY_ROLE, ("cmd", item.key))
                        if item.direction == "down":
                            leaf.setToolTip(0, _strip_html(item.doc) or item.name)
                            leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                            leaf.setCheckState(0, Qt.CheckState.Unchecked)
                        else:
                            # 上行帧（确认/否认应答、主动上报）由被测设备自己发出，
                            # 测试系统只接收 —— 不允许勾选下发（否则是测试方法错误）
                            leaf.setToolTip(0, f"{_strip_html(item.doc) or item.name}\n"
                                               f"{expect_mod.UPLINK_REASON}")
                            leaf.setFlags((leaf.flags() | Qt.ItemFlag.ItemIsEnabled)
                                          & ~Qt.ItemFlag.ItemIsUserCheckable
                                          & ~Qt.ItemFlag.ItemIsSelectable)
                            try:
                                leaf.setForeground(0, QBrush(QColor("#8C959F")))
                            except Exception:      # noqa: BLE001 - 主题异常不影响可用性
                                pass
                    g.addChild(leaf)
            c.setExpanded(page in (core.PAGE_EB, core.PAGE_CUSTOM))
        # 回归上次勾选（上行命令不可勾选，历史存档里的残留直接忽略）
        for key in self._checked.get(page, []):
            leaf = self._find_leaf(tree, key)
            if leaf is not None and (leaf.flags() & Qt.ItemFlag.ItemIsUserCheckable):
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
        """按**树的自上而下顺序**遍历叶子（QTreeWidget 的 item 索引序）。

        以前用 LIFO 栈（`stack.pop()`）导致遍历顺序反向 —— 「全选本页」勾出来的
        顺序就是自下而上，流程测试会从最后一条开始跑（用户报障）。改成倒序压栈、
        正序弹出，保证与界面看到的顺序一致。
        """
        stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount() - 1, -1, -1)]
        while stack:
            node = stack.pop()
            if node.data(0, LEAF_KEY_ROLE):
                yield node
            else:
                stack.extend(node.child(i) for i in range(node.childCount() - 1, -1, -1))

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
        # 切走之前先把上一条命令的控件值存进存档（含「与默认值相同就删条目」的判定）
        self._persist_current_params()
        kind, key = data
        if kind == "flow":
            self._on_flow_case_selected(key)
            return
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
        if column != 0:
            return
        tree = self._trees.get(self._page)
        if tree is None:
            return
        data = item.data(0, LEAF_KEY_ROLE)
        if data is None:
            # 组节点（功能域 / AFN / 子组）：勾父 = 整组子命令全选，取消同理
            if item.childCount() == 0:
                return
            checked = item.checkState(0) == Qt.CheckState.Checked
            tree.blockSignals(True)
            try:
                self._set_subtree_checked(item, checked)
            finally:
                tree.blockSignals(False)
        self._sync_parent_states(tree)
        self._rebuild_checked_from_tree()

    @staticmethod
    def _set_subtree_checked(item: QTreeWidgetItem, checked: bool) -> None:
        """把勾选态递归传到所有后代叶子（组节点自身的状态随后由父级汇总算出）。"""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(0, LEAF_KEY_ROLE) or child.childCount():
                child.setCheckState(0, state)
            if child.childCount():
                GdwTestWidget._set_subtree_checked(child, checked)

    @staticmethod
    def _sync_one(item: QTreeWidgetItem) -> None:
        if item.childCount() == 0:
            return
        states = []
        for i in range(item.childCount()):
            child = item.child(i)
            GdwTestWidget._sync_one(child)
            states.append(child.checkState(0))
        if all(s == Qt.CheckState.Checked for s in states):
            item.setCheckState(0, Qt.CheckState.Checked)
        elif all(s == Qt.CheckState.Unchecked for s in states):
            item.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            item.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def _sync_parent_states(self, tree: QTreeWidget) -> None:
        """子节点变动后自下而上汇总父节点（全选=勾、全不选=不勾、混合=半勾）。"""
        tree.blockSignals(True)
        try:
            for i in range(tree.topLevelItemCount()):
                self._sync_one(tree.topLevelItem(i))
        finally:
            tree.blockSignals(False)

    def _rebuild_checked_from_tree(self) -> None:
        tree = self._trees.get(self._page)
        if tree is None:
            return
        self._checked[self._page] = [
            leaf.data(0, LEAF_KEY_ROLE)[1] for leaf in self._iter_leaves(tree)
            if leaf.checkState(0) == Qt.CheckState.Checked
        ]
        self._update_checked_label()
        self._schedule_save()

    def _sendable_leaves(self, tree: QTreeWidget):
        """可下发的叶子（排除上行命令 —— 它们是应答/主动上报，不能由本页发送）。"""
        for leaf in self._iter_leaves(tree):
            if leaf.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                yield leaf

    def _set_all_checked(self, checked: bool) -> None:
        tree = self._trees.get(self._page)
        if tree is None:
            return
        tree.blockSignals(True)
        for leaf in self._sendable_leaves(tree):
            leaf.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        tree.blockSignals(False)
        self._checked[self._page] = ([leaf.data(0, LEAF_KEY_ROLE)[1]
                                      for leaf in self._sendable_leaves(tree)] if checked else [])
        self._update_checked_label()
        self._schedule_save()

    def _set_all_pages(self, checked: bool) -> None:
        """多页全选/全清：五个页签一起勾或一起取消（上行命令不在其列）。"""
        for key, _label in core.PAGES:
            self._ensure_tree(key)          # 未建过的页先建（勾选态才会落到树上）
        for key, _label in core.PAGES:
            tree = self._trees.get(key)
            if tree is None:
                continue
            tree.blockSignals(True)
            for leaf in self._sendable_leaves(tree):
                leaf.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            tree.blockSignals(False)
            self._checked[key] = ([leaf.data(0, LEAF_KEY_ROLE)[1]
                                   for leaf in self._sendable_leaves(tree)] if checked else [])
        self._update_checked_label()
        self._schedule_save()

    def _update_checked_label(self) -> None:
        n = len(self._checked.get(self._page, []))
        total = self._sendable_count(self._page)
        # 流程页是脚本化用例，勾选数不进「可下发命令」合计
        all_n = sum(len(v) for k, v in self._checked.items() if k != core.PAGE_FLOW)
        all_total = sum(self._sendable_count(key) for key, _label in core.PAGES)
        text = f"已选 {n} / {total}（本页）· 合计 {all_n} / {all_total}"
        if self._page == core.PAGE_FLOW:
            text = f"已选 {n} 条流程（本页）· 合计 {all_n} / {all_total}"
        # 上行命令（确认/否认应答、主动上报）不计入可下发数，单独说明
        uplink = self._uplink_count(self._page)
        if uplink:
            text += f" · 另有 {uplink} 条仅接收"
        self.lbl_checked.setText(text)

    def _sendable_count(self, page: str) -> int:
        if page == core.PAGE_FLOW:
            return 0            # 流程页是脚本化用例，不进命令队列/合计
        if page == core.PAGE_EB:
            return core.leaf_count(page)
        return len(expect_mod.sendable_commands(core.commands_for_page(page)
                                                if page != core.PAGE_CUSTOM
                                                else core.custom_commands()))

    def _uplink_count(self, page: str) -> int:
        if page in (core.PAGE_EB, core.PAGE_FLOW):
            return 0
        cmds = (core.commands_for_page(page) if page != core.PAGE_CUSTOM
                else core.custom_commands())
        return len(expect_mod.uplink_commands(cmds))

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
        # 记录「默认态」后套用该命令的存档值（存档只存改过的命令，取不到就是默认态）
        self._fresh_ui = self._collect_ui()
        self._apply_saved_cmd_params(cmd.key)

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
        self._fresh_eb_ui = self._collect_eb_ui()
        self._apply_saved_eb_params(item.di)

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

    # ── 命令参数存档 ────────────────────────────────────────────────────
    def _collect_ui(self) -> Dict[str, Any]:
        """控件的「可回填」值（和 ``_collect_values`` 的区别：这里保留原始文本）。"""
        ui: Dict[str, Any] = {}
        for fld, widget, _default in self._field_widgets:
            name = fld.get("name")
            if isinstance(widget, QComboBox):
                ui[name] = widget.currentData()
            elif isinstance(widget, QSpinBox):
                ui[name] = widget.value()
            else:
                ui[name] = widget.text()
        return ui

    def _collect_eb_ui(self) -> Dict[str, Any]:
        return self._collect_eb_values()

    @staticmethod
    def _set_widget_ui(widget: QWidget, value: Any) -> None:
        """回填一个控件（屏蔽信号，避免回填过程中反复组帧预览）。"""
        widget.blockSignals(True)
        try:
            if isinstance(widget, QComboBox):
                idx = widget.findData(value)
                if idx < 0:
                    idx = widget.findText(str(value if value is not None else ""))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(value))
                except (TypeError, ValueError):
                    pass
            else:
                widget.setText("" if value is None else str(value))
        finally:
            widget.blockSignals(False)

    def _apply_saved_cmd_params(self, key: str) -> None:
        """把该命令存档里的「控件值 + 附加数据」回填；无存档则保持默认态。"""
        rec = self._params.get_command(key)
        ui = rec.get("ui")
        if isinstance(ui, dict):
            for fld, widget, _default in self._field_widgets:
                name = fld.get("name")
                if name in ui:
                    self._set_widget_ui(widget, ui[name])
        self._set_raw_data_text(str(rec.get("raw") or ""))

    def _apply_saved_eb_params(self, di: str) -> None:
        rec = self._params.get_eb(di)
        ui = rec.get("ui")
        if isinstance(ui, dict):
            for fld, widget in self._eb_widgets:
                name = fld.get("name")
                if name in ui:
                    self._set_widget_ui(widget, ui[name])
        self._set_eb_raw_text(str(rec.get("raw") or ""))

    def _set_raw_data_text(self, text: str) -> None:
        self.edit_raw_data.blockSignals(True)
        try:
            self.edit_raw_data.setText(text)
        finally:
            self.edit_raw_data.blockSignals(False)

    def _set_eb_raw_text(self, text: str) -> None:
        self.edit_eb_raw.blockSignals(True)
        try:
            self.edit_eb_raw.setText(text)
        finally:
            self.edit_eb_raw.blockSignals(False)

    def _persist_current_params(self) -> None:
        """把当前显示的控件值写进存档；与默认态一致且无附加数据时删除该条。"""
        if self._page == core.PAGE_EB:
            item = self._current_eb
            if item is None:
                return
            ui = self._collect_eb_ui()
            raw = self.edit_eb_raw.text().strip()
            if ui == self._fresh_eb_ui and not raw:
                self._params.drop_eb(item.di)
            else:
                self._params.set_eb(item.di, self._collect_eb_values(), ui, self.edit_eb_raw.text())
            self._schedule_save()
            return
        cmd = self._current
        if cmd is None:
            return
        ui = self._collect_ui()
        raw = self.edit_raw_data.text().strip()
        dirty = [name for name, value in ui.items()
                 if name not in self._fresh_ui or value != self._fresh_ui.get(name)]
        if ui == self._fresh_ui and not raw:
            self._params.drop_command(cmd.key)
        else:
            self._params.set_command(cmd.key, self._collect_values(), ui,
                                     self.edit_raw_data.text(), dirty)
        self._schedule_save()

    def _values_for(self, page: str, key: str, node_addr: str = "") -> Dict[str, Any]:
        """组帧要用的字段值 —— 该命令自己的存档 + 组网参数绑定（手改优先）。"""
        if page == core.PAGE_EB:
            rec = self._params.get_eb(key)
            values = rec.get("values")
            return dict(values) if isinstance(values, dict) else {}
        rec = self._params.get_command(key)
        values = rec.get("values")
        cmd = self._find_cmd(key)
        if not (isinstance(values, dict) and values):
            values = core.default_values(cmd) if cmd is not None else {}
        if cmd is None:
            return dict(values)
        node = self._net.find_slave(node_addr) if node_addr else None
        if node is None and not node_addr and len(self._net.active_slaves()) == 1:
            node = self._net.active_slaves()[0]
        bound, _applied = net_mod.apply_binding(
            values, cmd, self._net, node, self._params.dirty_fields(key))
        return bound

    def _raw_for(self, page: str, key: str) -> str:
        rec = self._params.get_eb(key) if page == core.PAGE_EB else self._params.get_command(key)
        return str(rec.get("raw") or "")

    def _find_cmd(self, key: str) -> Optional[core.GdwCommand]:
        cmd = next((c for c in core.all_commands() if c.key == key), None)
        if cmd is None:
            cmd = next((c for c in core.custom_commands() if c.key == key), None)
        return cmd

    def _cmd_label(self, key: str) -> str:
        """命令的可读名（日志/信息表/报文表统一用它显示「发送的命令」）。"""
        cmd = self._find_cmd(key)
        if cmd is not None:
            src = f"[{cmd.source}] " if cmd.source and cmd.source != "标准" else ""
            return f"{cmd.afn:02X}H F{cmd.fn} {src}{cmd.name}"
        item = next((e for e in core.eb_items() if e.di == key), None)
        if item is not None:
            return f"EB {item.di} {item.name}"
        return str(key)

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

    def _preview_node(self) -> str:
        """预览用哪个从节点：默认第一个启用的节点（展开时界面会另行提示）。"""
        nodes = self._collect_network().active_slaves()
        return nodes[0].addr if nodes else ""

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
        node = self._preview_node()
        values = self._collect_values()
        # dirty 必须按「控件值」判定：列表字段在 _collect_values 里是 []，与控件里的 ""
        # 不相等，误判成手改就会把整列绑定量掉。
        bound, _applied = net_mod.apply_binding(
            values, cmd, self._collect_network(),
            self._collect_network().find_slave(node) if node else None,
            self._current_dirty_fields(self._collect_ui()),
        )
        return core.build_frame(
            cmd, bound,
            src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
            relay=self._relay_addrs(), info=self._info_config(), raw_data=raw,
        )

    def _current_dirty_fields(self, ui: Mapping[str, Any]) -> List[str]:
        """当前面板上相对默认态被改过的字段（预览与实际发送用同一口径：手改优先）。"""
        return [name for name, value in ui.items()
                if name not in self._fresh_ui or value != self._fresh_ui.get(name)]

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
        note = self._preview_note()
        target.setPlainText(f"({len(frame)} 字节)\n{_fmt(frame)}" + (f"\n{note}" if note else ""))

    def _preview_note(self) -> str:
        """预览附注：这帧套了哪些组网参数、会不会按从节点展开。"""
        cmd = self._current
        if cmd is None or self._page == core.PAGE_EB:
            return ""
        net = self._collect_network()
        nodes = net.active_slaves()
        lines: List[str] = []
        bound, applied = net_mod.apply_binding(
            self._collect_values(), cmd, net,
            net.find_slave(self._preview_node()) if nodes else None,
            self._current_dirty_fields(self._collect_ui()),
        )
        if applied:
            pairs = []
            for name in applied:
                value = bound.get(name)
                if isinstance(value, list):
                    value = f"{len(value)} 项"
                pairs.append(f"{name}={value}")
            line = "组网参数自动填充：" + "、".join(pairs)
            if len(nodes) > 1 and net_mod.is_node_scoped(cmd):
                line += f"（按 {len(nodes)} 个从节点展开）"
            lines.append(line)
        # 手改过的字段不套组网参数 —— 现场「表号不存在」多半是这里：旧值/线序值还在
        skipped = self._dirty_bind_fields(cmd)
        if skipped:
            shown = "、".join(f"{n}={self._collect_values().get(n)}" for n in skipped[:4])
            lines.append("⚠ 以下字段被手改，未套用组网参数：" + shown
                         + "（要重新绑定请点「清空所有参数」）")
        if nodes and net.fanout and net_mod.is_node_scoped(cmd):
            first = nodes[0]
            lines.append(
                f"上方帧 = 从节点 {first.addr}（{net_mod.proto_label(first.proto)}）那一帧；"
                "按从节点展开：" + "、".join(
                    f"{n.addr}（{net_mod.proto_label(n.proto)}）" for n in nodes)
                + " 各发一帧")
        elif nodes and net_mod.is_node_scoped(cmd):
            lines.append("按从节点展开已关闭：只发当前预览这一帧")
        raw_text = (self.edit_raw_data.text() or "").strip()
        if raw_text:
            lines.extend(self._raw_data_warnings(cmd, raw_text))
        return "\n".join(lines)

    def _dirty_bind_fields(self, cmd) -> List[str]:
        """该命令里「本可套组网参数、但被手改过」的字段名。"""
        if cmd is None:
            return []
        dirty = set(self._params.dirty_fields(cmd.key))
        if not dirty:
            return []
        names = [str(f.get("name")) for f in (getattr(cmd, "fields", ()) or ())]
        return [n for n in names if n in dirty and net_mod.bind_source(n)]

    @staticmethod
    def _raw_data_warnings(cmd, raw_text: str) -> List[str]:
        """附加数据填了整帧 / 与该命令字段冲突时的提示（不拦截，只提醒）。"""
        compact = "".join(ch for ch in raw_text.upper() if ch not in " \t\r\n")
        lines: List[str] = []
        if len(compact) >= 6 and compact.startswith("68") and compact.endswith("16"):
            lines.append("⚠ 附加数据看起来是整帧报文（68…16）：这里只填『数据单元』，"
                         "贴整帧会多出一段数据单元 → CCO 回「长度错误」")
        if cmd is not None and not cmd.fields:
            lines.append("该命令协议上无数据单元；确需补数据单元才填附加数据，否则留空")
        return lines

    def _on_edit_raw_focus(self) -> None:
        self.edit_raw_data.setFocus()

    # ── 发送队列 ────────────────────────────────────────────────────────
    def _targets(self) -> List[Tuple[str, str, str]]:
        """勾选清单 → ``(页, key, 从节点地址)``；单节点地址类命令按从节点各一帧。

        上行命令（确认/否认应答、主动上报）不在下发范围内：跳过并记一条日志，
        不给「支持/不支持」结论（那是被测设备自己发的内容）。
        """
        checked = self._checked.get(self._page, [])
        base: List[Tuple[str, str]] = []
        if checked:
            base = [(self._page, key) for key in checked]
        elif self._page == core.PAGE_EB and self._current_eb is not None:
            base = [(self._page, self._current_eb.di)]
        elif self._current is not None:
            base = [(self._page, self._current.key)]
        if not base:
            return []
        plan, skipped = net_mod.plan_targets(base, self._find_cmd, self._collect_network())
        if skipped:
            names = "、".join(self._cmd_label(key) for _page, key in skipped[:6])
            more = f" 等 {len(skipped)} 条" if len(skipped) > 6 else ""
            self._log(f"[跳过] 上行命令不下发（由被测设备主动发出/应答）：{names}{more}", "warn")
        return plan

    # ── 前置流程：建档 → 核对档案 → 查拓扑判入网 ────────────────────────
    #: 查拓扑最多轮询几次（每轮间隔 PREFLIGHT_POLL_GAP_MS）
    PREFLIGHT_POLLS = 3
    PREFLIGHT_POLL_GAP_MS = 2000

    def _on_preflight(self) -> None:
        """一键准备测试网络：建档 → 核对档案（10H F2）→ 查拓扑判入网（10H F20）。"""
        if self._awaiting or self._next_timer.isActive():
            self._log("[提示] 正在等待上一帧应答，稍后再试", "warn")
            return
        if not self._channel.ready():
            reason = self._channel.state_text() or "通道未就绪"
            self._log(f"[失败] {reason}", "fail")
            QMessageBox.warning(self, "通道未就绪", reason)
            return
        net = self._collect_network()
        targets, overrides, notes = net_mod.build_preflight(net, self._find_cmd)
        if not targets:
            self._log("[提示] " + "；".join(notes), "warn")
            QMessageBox.information(self, "准备测试网络", "；".join(notes))
            return
        self._persist_current_params()
        self._preflight = {"archive": [], "topology": [], "polls": 0}
        self._queue_overrides = dict(overrides)
        self._session_started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._interactions.clear()
        self._log("[信息] 前置流程开始：参数区初始化 → 添加从节点档案 → 查从节点数量 → "
                  "查从节点信息（核对档案）→ 查双模拓扑（判入网）", "info")
        for note in notes:
            self._log(f"  · {note}", "info")
        self._start_queue(targets, reset_counter=True)

    def _note_preflight_rows(self, key: str, rows: Sequence[Tuple]) -> None:
        """按来源分别记录：F2 是档案、F20 才是入网拓扑（多轮轮询取并集）。"""
        if self._preflight is None:
            return
        if key == net_mod.PREFLIGHT_TOPOLOGY:
            bucket, addrs = "topology", net_mod.topology_addrs_from_rows(rows)
            detail = net_mod.topology_detail(rows)
            if detail:
                merged = self._preflight.setdefault("detail", {})
                for addr, info in detail.items():
                    merged.setdefault(addr, {}).update(info)
        elif key in (net_mod.PREFLIGHT_NODE_INFO, net_mod.PREFLIGHT_NODE_COUNT):
            bucket, addrs = "archive", net_mod.slave_addrs_from_rows(rows)
        else:
            return
        if not addrs:
            return
        seen = self._preflight.setdefault(bucket, [])
        for addr in addrs:
            if addr not in seen:
                seen.append(addr)

    def _finish_preflight(self) -> None:
        """收尾：档案核对结论 + 拓扑入网结论；未入网则再查拓扑。"""
        ctx = self._preflight
        if ctx is None:
            return
        archive = self._collect_network().active_slaves()
        topo = ctx.get("topology") or []
        report = net_mod.join_report(archive, topo)
        polls = int(ctx.get("polls") or 0)
        if not report["all_joined"] and polls + 1 < self.PREFLIGHT_POLLS:
            ctx["polls"] = polls + 1
            self._log(f"[前置] 拓扑里还差 {len(report['missing'])} 个档案节点，"
                      f"{self.PREFLIGHT_POLL_GAP_MS // 1000}s 后重查拓扑"
                      f"（第 {polls + 2} 次）", "warn")
            QTimer.singleShot(self.PREFLIGHT_POLL_GAP_MS, self._repreflight_query)
            return

        self._joined_addrs = list(report["joined"])
        self._archive_seen = list(ctx.get("archive") or [])
        self._preflight = None
        self._refresh_join_label()

        # ① 档案核对（10H F2）：只说明档案加没加对，不代表入网
        arch = net_mod.archive_report(archive, ctx.get("archive") or [])
        if arch["all_matched"]:
            self._log(f"[前置] 档案核对通过：{arch['archive']} 个从节点均已下装"
                      f"（{'、'.join(arch['matched'])}）", "ok")
        else:
            self._log(f"[前置] 档案核对不一致：缺 {'、'.join(arch['missing']) or '无'}"
                      f"；模块多出 {'、'.join(arch['extra']) or '无'}", "warn")
            self._log("  档案只是「模块里下装了哪些表」，不代表已入网；"
                      "缺档案可重发 11H F1，多出的用 11H F2 删除", "info")

        # ② 入网判定（10H F20 拓扑）
        detail = ctx.get("detail") or {}
        if report["all_joined"]:
            self._log(f"[前置] 入网完成：拓扑内档案节点 {len(report['joined'])}/{report['archive']} 全部在网", "ok")
        else:
            self._log(f"[前置] 未全部入网：拓扑里只有 {len(report['joined'])}/{report['archive']}"
                      f"，未入网 {'、'.join(report['missing']) or '无'}", "warn")
            self._log("  可下发 11H F102 启动组网后重试；仍不入网则查射频/信号与表侧上电", "info")
        for addr in report["joined"]:
            info = detail.get(addr) or {}
            if info:
                self._log(f"  · {addr}：角色={info.get('角色', '?')}、层级={info.get('层级', '?')}、"
                          f"信道={info.get('信道', '?')}", "info")
        if report["extra"]:
            self._log(f"  拓扑里还有档案外的节点：{'、'.join(report['extra'])}", "info")

    def _repreflight_query(self) -> None:
        if self._preflight is None:
            return
        # 覆盖值必须在开跑前就位：_start_queue 会同步组帧；字段名按 schema 取
        _, overrides, _ = net_mod.build_preflight(self._collect_network(), self._find_cmd)
        self._queue_overrides = dict(overrides)
        self._log("[前置] 重新查询双模拓扑…", "info")
        self._start_queue([("cmd", net_mod.PREFLIGHT_TOPOLOGY, "")])

    def _refresh_join_label(self) -> None:
        """组网栏状态：入网按 10H F20 拓扑判定；另附档案核对结果（10H F2）。"""
        net = self._collect_network()
        archive = [n.addr for n in net.active_slaves()]
        if not self._joined_addrs and not self._archive_seen:
            self.lbl_join_state.setText("入网：未查询")
            self.lbl_join_state.setStyleSheet("color:#6E7781;")
            return
        joined = [a for a in archive if a.upper() in {x.upper() for x in self._joined_addrs}]
        total = len(archive)
        if not joined:
            text, color = f"入网：0/{total} ✗", "#B35900"
        elif len(joined) < total:
            text, color = f"入网：{len(joined)}/{total}（缺 {total - len(joined)}）", "#B35900"
        else:
            text, color = f"入网：{len(joined)}/{total} ✓", "#1A7F37"
        matched = [a for a in archive if a.upper() in {x.upper() for x in self._archive_seen}]
        self.lbl_join_state.setText(f"{text}｜档案 {len(matched)}/{total}")
        self.lbl_join_state.setStyleSheet(f"color:{color};")

    # ── 流程测试页 ──────────────────────────────────────────────────────
    #: 组网轮询间隔（秒）：轮询拓扑时每次等应答的上限
    JOIN_POLL_INTERVAL_S = 15.0

    def _build_sta_sim_bar(self) -> QWidget:
        """从节点模拟（虚拟表）：串口独立配置 + 按组网参数自动启 645/698 引擎。"""
        box = QGroupBox("从节点模拟（虚拟表）—— 本页独立串口，按勾选用例的从节点协议自动启 645 / 698")
        grid = QGridLayout(box)
        grid.setContentsMargins(6, 4, 6, 4)

        self.combo_sta_port = QComboBox()
        self.combo_sta_port.setMinimumWidth(110)
        self.combo_sta_port.currentTextChanged.connect(self._on_sta_serial_edited)
        self.combo_sta_baud = QComboBox()
        self.combo_sta_baud.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.combo_sta_baud.setCurrentText("115200")
        self.combo_sta_baud.currentTextChanged.connect(self._on_sta_serial_edited)
        self.combo_sta_parity = QComboBox()
        self.combo_sta_parity.addItems(["N", "E", "O"])
        self.combo_sta_parity.currentTextChanged.connect(self._on_sta_serial_edited)
        self.combo_sta_stop = QComboBox()
        self.combo_sta_stop.addItems(["1", "2"])
        self.combo_sta_stop.currentTextChanged.connect(self._on_sta_serial_edited)
        self.btn_sta_ports = QPushButton("刷新")
        self.btn_sta_sim = QPushButton("启动从节点模拟")
        self.btn_sta_sim.setToolTip(
            "按「组网参数」里从节点的协议自动启用：\n"
            "· 有 DL/T 645-2007 从节点 → 启 645 虚拟表\n"
            "· 有 DL/T 698.45 从节点 → 启 698.45 虚拟表\n"
            "两者可以同时启用（同一串口按帧结构分流）")
        self.btn_sta_ports.clicked.connect(self._refresh_sta_ports)
        self.btn_sta_sim.clicked.connect(self._toggle_sta_sim)
        self.lbl_sta_sim = QLabel("○ 未启动")
        self.lbl_sta_sim.setStyleSheet("color:#6E7781;")
        self.lbl_sta_proto = QLabel("协议：—")
        self.lbl_sta_proto.setStyleSheet("color:#6E7781;")

        grid.addWidget(QLabel("端口"), 0, 0)
        grid.addWidget(self.combo_sta_port, 0, 1)
        grid.addWidget(QLabel("波特率"), 0, 2)
        grid.addWidget(self.combo_sta_baud, 0, 3)
        grid.addWidget(QLabel("校验"), 0, 4)
        grid.addWidget(self.combo_sta_parity, 0, 5)
        grid.addWidget(QLabel("停止位"), 0, 6)
        grid.addWidget(self.combo_sta_stop, 0, 7)
        grid.addWidget(self.btn_sta_ports, 0, 8)
        grid.addWidget(self.btn_sta_sim, 0, 9)
        grid.addWidget(self.lbl_sta_sim, 0, 10, 1, 2)
        grid.addWidget(self.lbl_sta_proto, 1, 0, 1, 6)
        grid.setColumnStretch(11, 1)
        self._refresh_sta_ports()
        return box

    def _on_sta_serial_edited(self, *_args) -> None:
        """从节点模拟串口参数变化 → 落盘（下次打开还是这套参数）。"""
        self._schedule_save()

    def _refresh_sta_ports(self) -> None:
        """刷新串口列表；**保留当前选择**，没有当前选择就回落到存档里的端口。

        现场串口是固定的（COM5 / 9600 / E / 1），刷新按钮不该把它重置成第一个口。
        """
        current = self.combo_sta_port.currentText().strip()
        if not current or current.startswith("（"):
            current = str(self._saved_sta_port() or "")
        self.combo_sta_port.blockSignals(True)
        self.combo_sta_port.clear()
        ports: List[str] = []
        try:
            import serial.tools.list_ports as list_ports

            ports = [p.device for p in list_ports.comports()]
        except Exception:
            ports = []
        self.combo_sta_port.addItems(ports or ["（未检测到串口）"])
        if current:
            idx = self.combo_sta_port.findText(current)
            if idx >= 0:
                self.combo_sta_port.setCurrentIndex(idx)
            elif current not in ("", "（未检测到串口）"):
                # 存档里的口当前没插上：也显示出来，插上后不用再选
                self.combo_sta_port.addItem(current)
                self.combo_sta_port.setCurrentIndex(self.combo_sta_port.count() - 1)
        self.combo_sta_port.blockSignals(False)

    def _saved_sta_port(self) -> str:
        """存档里的从节点模拟端口（未加载过配置时返回空串）。"""
        try:
            path = self._config_path()
            if not os.path.exists(path):
                return ""
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return str((data or {}).get("sta_port") or "")
        except Exception:                      # noqa: BLE001 - 配置坏了就按没存过处理
            return ""

    def _sta_protocols(self) -> set:
        """按组网参数里启用的从节点，决定要启哪些虚拟表协议。"""
        net = self._collect_network()
        protos = set()
        for node in net.active_slaves():
            if int(node.proto) == net_mod.PROTO_698_45:
                protos.add(2)   # 698.45 → 见 sta_sim_service.PROTO_698
            elif int(node.proto) in (net_mod.PROTO_645_2007, net_mod.PROTO_645_1997):
                protos.add(1)
        return protos

    def _toggle_sta_sim(self) -> None:
        if self._sta_sim is not None and self._sta_sim.isRunning():
            self._sta_sim.stop()
            self._sta_sim.wait(1500)
            self._sta_sim = None
            self.btn_sta_sim.setText("启动从节点模拟")
            self.lbl_sta_sim.setText("○ 未启动")
            self.lbl_sta_sim.setStyleSheet("color:#6E7781;")
            return
        port = self.combo_sta_port.currentText().strip()
        if not port or port.startswith("（"):
            QMessageBox.information(self, "从节点模拟", "请先选择一个串口")
            return
        self._start_sta_sim(port)

    def _start_sta_sim(self, port: str) -> bool:
        import sta_sim_service as sim

        if not port or port.startswith("（"):
            self._log("[提示] 未选择可用的从节点模拟串口", "warn")
            return False
        protos = self._sta_protocols()
        if not protos:
            self._log("[提示] 组网参数里没有启用的从节点，无法确定虚拟表协议", "warn")
            return False
        proto_set = set()
        if 1 in protos:
            proto_set.add(sim.PROTO_645)
        if 2 in protos:
            proto_set.add(sim.PROTO_698)
        addr = ""
        slaves = self._collect_network().active_slaves()
        if slaves:
            addr = slaves[0].addr
        try:
            stopbits = float(self.combo_sta_stop.currentText())
        except ValueError:
            stopbits = 1.0
        svc = sim.StaSimService(
            port, int(self.combo_sta_baud.currentText() or 115200),
            self.combo_sta_parity.currentText(), stopbits, proto_set, addr)
        svc.log.connect(lambda msg: self._log(f"[从节点模拟] {msg}", "info"))
        self._sta_sim = svc
        svc.start()
        self.btn_sta_sim.setText("停止从节点模拟")
        self.lbl_sta_sim.setText("● 监听中")
        self.lbl_sta_sim.setStyleSheet("color:#1A7F37;")
        self.lbl_sta_proto.setText(f"协议：{svc.protocol_text()}｜虚拟表地址：{addr or '按档案'}")
        self._log(f"[从节点模拟] 启动 {port}（{svc.protocol_text()}）", "ok")
        return True

    def _ensure_sta_sim_for_flow(self) -> None:
        """开始跑流程前：若勾选用例需要从节点，按组网参数自动起虚拟表。"""
        case = self._flow_case
        if case is None or not case.needs_slave:
            return
        if self._sta_sim is not None and self._sta_sim.isRunning():
            return
        port = self.combo_sta_port.currentText().strip()
        if not port or port.startswith("（"):
            self._log("[提示] 本用例需要从节点配合，但未配置从节点模拟串口；"
                      "可在上方选端口后点「启动从节点模拟」", "warn")
            return
        self._start_sta_sim(port)

    def _build_flow_page(self) -> QWidget:
        """流程测试：左侧用例树（复用主树），这里是步骤表 + 运行控制。"""
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)

        self.lbl_flow_title = QLabel("未选择流程用例")
        font = QFont()
        font.setBold(True)
        self.lbl_flow_title.setFont(font)
        lay.addWidget(self.lbl_flow_title)

        self.lbl_flow_desc = QLabel("在左侧勾选流程用例后点「开始执行」；"
                                   "带 ⚙ 的用例需要下面的「从节点模拟」配合（按组网参数自动启 645/698 虚拟表）。")
        self.lbl_flow_desc.setWordWrap(True)
        self.lbl_flow_desc.setStyleSheet("color:#6E7781;")
        lay.addWidget(self.lbl_flow_desc)

        lay.addWidget(self._build_sta_sim_bar())

        self.flow_table = QTableWidget(0, 4)
        self.flow_table.setHorizontalHeaderLabels(["#", "步骤", "状态", "说明"])
        self.flow_table.verticalHeader().setVisible(False)
        self.flow_table.setColumnWidth(0, 36)
        self.flow_table.setColumnWidth(1, 420)
        self.flow_table.setColumnWidth(2, 70)
        self.flow_table.horizontalHeader().setStretchLastSection(True)
        self.flow_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.flow_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self.flow_table, 1)

        row = QHBoxLayout()
        self.btn_flow_start = QPushButton("开始执行")
        self.btn_flow_stop = QPushButton("停止")
        self.btn_flow_stop.setEnabled(False)
        self.btn_flow_skip = QPushButton("跳过本步")
        self.btn_flow_skip.setEnabled(False)
        self.btn_flow_start.clicked.connect(self._on_flow_start)
        self.btn_flow_stop.clicked.connect(self._on_flow_stop)
        self.btn_flow_skip.clicked.connect(lambda: self._flow_done(True, "人工跳过"))
        row.addWidget(self.btn_flow_start)
        row.addWidget(self.btn_flow_stop)
        row.addWidget(self.btn_flow_skip)
        self.lbl_flow_state = QLabel("")
        self.lbl_flow_state.setStyleSheet("color:#6E7781;")
        row.addWidget(self.lbl_flow_state, 1)
        lay.addLayout(row)
        return box

    def _flow_case_by_key(self, key: str):
        import gdw_test_flows as flows

        return flows.flow_case(key)

    def _on_flow_case_selected(self, key: str) -> None:
        case = self._flow_case_by_key(key)
        self._flow_case = case
        # 选中已跑过的用例：恢复它**上一次的逐步结果**（用户口径：跑完点回去要能看到记录）
        history = self._flow_history.get(key) if case is not None else None
        runner = self._flow_runner
        if runner is not None and runner.case is case:
            self._render_flow_runner()          # 正在跑的用例：直接用实时状态
            return
        if history:
            self._render_flow_steps(case, states=history.get("states"),
                                    notes=history.get("notes"),
                                    current=history.get("current"))
            return
        self._render_flow_steps(case)

    def _render_flow_steps(self, case, states=None, notes=None, current=None) -> None:
        """渲染步骤表。

        ``states``/``notes`` 为空 → 全新（全部「待执行」）；传历史 → 回显上次执行结果，
        这样点回已跑完（尤其失败）的用例还能看到每一步的结论。
        步骤数对不上（流程定义改过）时按序号对齐，多出的记「待执行」。
        """
        self.flow_table.setRowCount(0)
        if case is None:
            self.lbl_flow_title.setText("未选择流程用例")
            self.lbl_flow_desc.setText("在左侧勾选流程用例后点「开始执行」。")
            return
        self.lbl_flow_title.setText(f"{case.name}（{len(case.steps)} 步）")
        desc = case.desc
        if case.source:
            desc += f"\n出处：{case.source}"
        if case.needs_slave:
            desc += "\n⚙ 本用例部分步骤需要从节点配合：请在「协议8 虚拟表」页模拟电能表/从节点，"
            desc += "或按提示在设备上操作。"
        self.lbl_flow_desc.setText(desc)

        import gdw_test_flows as flows

        labels = {flows.STEP_PENDING: "待执行", flows.STEP_RUNNING: "执行中",
                  flows.STEP_OK: "✓ 通过", flows.STEP_FAIL: "✗ 失败", flows.STEP_SKIP: "跳过"}
        for idx, step in enumerate(case.steps, 1):
            row = self.flow_table.rowCount()
            self.flow_table.insertRow(row)
            self.flow_table.setItem(row, 0, QTableWidgetItem(str(idx)))
            mark = "⚙ " if step.needs_slave else ""
            self.flow_table.setItem(row, 1, QTableWidgetItem(mark + step.title))
            state = states[idx - 1] if states and idx - 1 < len(states) else flows.STEP_PENDING
            note = notes[idx - 1] if notes and idx - 1 < len(notes) else ""
            self.flow_table.setItem(row, 2, QTableWidgetItem(labels.get(state, state)))
            self.flow_table.setItem(row, 3, QTableWidgetItem(note or step.hint))
            # 历史里标「执行中」的，只在它仍是当前 runner 的那一步时保留，其余按待执行
            if state == flows.STEP_RUNNING and current != idx - 1:
                self.flow_table.item(row, 2).setText(labels[flows.STEP_PENDING])

    def _flow_selected_cases(self) -> List[Any]:
        """流程页勾选的用例，**按树里自上而下的顺序**返回；没勾选就用当前选中项。

        不能直接用 `self._checked` 的顺序：那是历史勾选记录的堆叠顺序（旧版还是反向的），
        存档里可能残留乱序。这里以树的位置为准，保证与界面看到的顺序一致。
        """
        import gdw_test_flows as flows

        checked = set(self._checked.get(core.PAGE_FLOW, []))
        out: List[Any] = []
        tree = self._trees.get(core.PAGE_FLOW)
        if tree is not None:
            for leaf in self._iter_leaves(tree):
                data = leaf.data(0, LEAF_KEY_ROLE)
                if not data or data[0] != "flow" or data[1] not in checked:
                    continue
                case = flows.flow_case(data[1])
                if case is not None:
                    out.append(case)
        if not out:                        # 树还没建 / 记录与树不同步时退回记录顺序
            for fid in self._checked.get(core.PAGE_FLOW, []):
                case = flows.flow_case(fid)
                if case is not None and case not in out:
                    out.append(case)
        if not out and self._flow_case is not None:
            out.append(self._flow_case)
        return out

    def _on_flow_start(self) -> None:
        if self._flow_runner is not None:
            self._log("[提示] 流程正在执行中，先停止", "warn")
            return
        if not self._channel.ready():
            reason = self._channel.state_text() or "通道未就绪"
            self._log(f"[失败] {reason}", "fail")
            QMessageBox.warning(self, "通道未就绪", reason)
            return
        cases = self._flow_selected_cases()
        if not cases:
            QMessageBox.information(self, "流程测试", "请先在左侧勾选流程用例")
            return
        net = self._collect_network()
        overrides: Dict[str, Dict[str, Any]] = {}
        # 建档/拓扑类步骤的查询范围按组网参数算
        if net.active_slaves():
            _, ov, _ = net_mod.build_preflight(net, self._find_cmd)
            overrides.update(ov)
        self._persist_current_params()
        self._flow_overrides = overrides
        self._flow_queue = list(cases)
        self._flow_rx_buffer = []          # 新一轮流程：清空上行缓存
        for case in cases:                 # 第三列先标「排队中」，执行时再改「进行中」
            self._set_flow_result(case.fid, "排队中")
        # 需要从节点的用例：先按组网参数把虚拟表（645/698）拉起来
        self._ensure_sta_sim_for_flow()
        self.btn_flow_start.setEnabled(False)
        self.btn_flow_stop.setEnabled(True)
        self.btn_flow_skip.setEnabled(True)
        if len(cases) > 1:
            self._log(f"[信息] 依次执行 {len(cases)} 条流程：" +
                      "、".join(c.name for c in cases), "info")
        self._start_next_flow()

    def _start_next_flow(self) -> None:
        import gdw_test_flows as flows

        if not self._flow_queue:
            self.btn_flow_start.setEnabled(True)
            self.btn_flow_stop.setEnabled(False)
            self.btn_flow_skip.setEnabled(False)
            self.lbl_flow_state.setText("全部流程执行完毕")
            return
        case = self._flow_queue.pop(0)
        self._flow_case = case
        self._render_flow_steps(case)
        self._set_flow_result(case.fid, "进行中")
        self._flow_served = 0
        self._flow_runner = flows.FlowRunner(case, self._flow_overrides)
        self._flow_rx_buffer = []          # 每条用例独立缓存，互不串台
        self._log(f"[信息] 流程开始：{case.name}（{len(case.steps)} 步）", "info")
        action = self._flow_runner.start()
        self._render_flow_runner()
        self._run_flow_action(action)

    def _on_flow_stop(self) -> None:
        if self._flow_runner is None:
            return
        self._flow_queue = []
        self._flow_runner.stop()
        self._flow_timer.stop()
        self._flow_action = None
        self._log("[信息] 流程已停止", "warn")
        self._render_flow_runner()
        self._finish_flow()

    def _finish_flow(self) -> None:
        runner = self._flow_runner
        # 收尾时先把最终状态写进快照并刷新表格，再清空 runner ——
        # 否则跑完这一步表格会停在「执行中」，点回来也看不到结论
        if runner is not None:
            self._flow_history[runner.case.fid] = {
                "states": list(runner.states), "notes": list(runner.notes),
                "current": -1,
            }
            self._render_flow_steps(runner.case, states=runner.states,
                                    notes=runner.notes, current=-1)
        self._flow_runner = None
        self._flow_action = None
        self._flow_poll_step = None
        self._flow_rx_buffer = []
        self._flow_timer.stop()
        queued = bool(self._flow_queue)
        if not queued:
            self.btn_flow_start.setEnabled(True)
            self.btn_flow_stop.setEnabled(False)
            self.btn_flow_skip.setEnabled(False)
        if runner is not None:
            ok, bad, skip = runner.summary()
            verdict = "通过" if runner.passed else ("失败" if bad else "已停止")
            self.lbl_flow_state.setText(f"{verdict}｜通过 {ok} 步，失败 {bad} 步，跳过 {skip} 步")
            kind = "ok" if runner.passed else ("fail" if bad else "warn")
            self._log(f"[流程] {runner.case.name}：{verdict}"
                      f"（通过 {ok} / 失败 {bad} / 跳过 {skip}）", kind)
            # 左树第三列：整条用例的测试结果（停止的记「已停止」，不算通过）
            self._set_flow_result(runner.case.fid,
                                  "通过" if runner.passed else ("失败" if bad else "已停止"))
            if bad:
                import gdw_test_flows as flows

                for i, st in enumerate(runner.states):
                    if st == flows.STEP_FAIL:
                        self._log(f"  ✗ 第 {i+1} 步 {runner.case.steps[i].title}"
                                  f"：{runner.notes[i] or '未通过'}", "fail")
        if queued:
            QTimer.singleShot(300, self._start_next_flow)

    # ── 流程测试结果（左树第三列）──────────────────────────────────────────
    #: 结果 → (显示文字, 颜色)
    FLOW_RESULT_STYLES = {
        "未执行": ("—", "#6E7781"),
        "排队中": ("排队中", "#6E7781"),
        "进行中": ("进行中…", "#0969DA"),
        "通过": ("✓ 通过", "#1A7F37"),
        "失败": ("✗ 失败", "#B42318"),
        "已停止": ("■ 已停止", "#9A6700"),
        "跳过": ("－ 跳过", "#6E7781"),
    }

    def _flow_result_of(self, fid: str) -> str:
        """该用例当前的结果文字（左树第三列显示值）。"""
        state = self._flow_results.get(fid, "未执行")
        return self.FLOW_RESULT_STYLES.get(state, (state, ""))[0]

    def _set_flow_result(self, fid: str, state: str) -> None:
        """记一条用例的测试结果并刷新左树对应行（找不到行就只记状态）。"""
        if not fid:
            return
        self._flow_results[fid] = state
        text, color = self.FLOW_RESULT_STYLES.get(state, (state, ""))
        for leaf in self._iter_leaves(self._trees.get(core.PAGE_FLOW)) \
                if self._trees.get(core.PAGE_FLOW) is not None else ():
            data = leaf.data(0, LEAF_KEY_ROLE)
            if not data or data[0] != "flow" or data[1] != fid:
                continue
            leaf.setText(2, text)
            try:
                leaf.setForeground(2, QBrush(QColor(color)))
            except Exception:              # noqa: BLE001 - 主题异常不影响可用性
                pass
            leaf.setToolTip(2, f"{fid}：{state}")
            break

    def _render_flow_runner(self) -> None:
        import gdw_test_flows as flows

        runner = self._flow_runner
        if runner is None:
            return
        labels = {flows.STEP_PENDING: "待执行", flows.STEP_RUNNING: "执行中",
                  flows.STEP_OK: "✓ 通过", flows.STEP_FAIL: "✗ 失败", flows.STEP_SKIP: "跳过"}
        # 快照：用例跑完（或中途切走再点回来）要能回显每一步的结论
        self._flow_history[runner.case.fid] = {
            "states": list(runner.states), "notes": list(runner.notes),
            "current": self._flow_action.index if self._flow_action else -1,
        }
        for i, state in enumerate(runner.states):
            if i >= self.flow_table.rowCount():
                break
            cell = self.flow_table.item(i, 2)
            if cell is not None:
                cell.setText(labels.get(state, state))
            note = self.flow_table.item(i, 3)
            if note is not None and runner.notes[i]:
                note.setText(runner.notes[i])

    def _run_flow_action(self, action) -> None:
        import gdw_test_flows as flows

        self._flow_action = action
        self._render_flow_runner()
        if action.kind == "done":
            self._finish_flow()
            return
        step = action.step
        self.lbl_flow_state.setText(f"第 {action.index + 1}/{len(self._flow_runner.case.steps)} 步："
                                    f"{step.title}")
        if action.kind == flows.KIND_SLEEP:
            self._log(f"[流程] 等待 {step.timeout:.0f}s：{step.title}", "info")
            self._flow_timer.start(int(max(0.1, step.timeout) * 1000))
            return
        if action.kind == flows.KIND_RESET_STA:
            self._run_sta_reset(step)
            return
        if action.kind == flows.KIND_POLL:
            self._flow_poll_begin(step)
            return
        if action.kind == flows.KIND_MANUAL:
            self._log(f"[流程] 需要人工配合：{step.title}（{step.hint}）", "warn")
            self.btn_flow_skip.setEnabled(True)
            self._flow_timer.start(int(max(1.0, step.timeout) * 1000))
            return
        if action.kind == flows.KIND_SERVE:
            served = "、".join(f"{a:02X}H F{f}" for a, f in (step.serve or ()))
            until = (f"直到收到 {step.until[0]:02X}H F{step.until[1]}"
                     if step.until and step.until[0] >= 0 else "直到超时")
            self._log(f"[流程] 开始服务路由请求（{step.timeout:.0f}s）：收到 {served} 就回业务应答，"
                      f"{until}", "info")
            self._log("  14H F1 → 回该从节点协议的正向有功总电能读报文；"
                      "14H F2 → 回测试系统当前时间", "info")
            self._flow_served = 0
            # 窗口内可能已经有 06H F2 提前到了：先查缓存，命中直接完成
            hit = self._flow_consume_buffered(step)
            if hit is not None and step.until and hit == step.until:
                self._log("  → 命中缓存：抄读数据已提前上报，本步完成", "ok")
                self._flow_done(True, "抄读数据已提前上报")
                return
            self._flow_timer.start(int(max(0.1, step.timeout) * 1000))
            return
        if action.kind == flows.KIND_WAIT:
            extra = "".join(f"（兼容 {a:02X}H F{f}）" for a, f in (step.accept or ()))
            self._log(f"[流程] 等待模块上行 {step.afn:02X}H F{step.fn}{extra}"
                      f"（{step.timeout:.0f}s）：{step.title}", "info")
            if step.needs_slave:
                self._log("  ⚙ 本步依赖从节点/虚拟表配合（协议8 虚拟表页）", "warn")
            # 先查缓存：硬件初始化后 CCO 常常「立刻」上报，帧可能在本步开始之前就到了
            hit = self._flow_consume_buffered(step)
            if hit is not None:
                note = self._flow_note_uplink(step, *hit)
                self._log("  → 命中缓存（该上行已在本步开始前收到），直接判通过", "ok")
                self._flow_done(True, f"缓存命中：{note}" if note else "缓存命中：上行已提前收到")
                return
            self._flow_timer.start(int(max(0.1, step.timeout) * 1000))
            return
        # send
        try:
            frames = self._build_flow_frames(step)
        except Exception as exc:            # 组帧失败按本步失败处理，不中断整个流程
            self._log(f"[失败] 第 {action.index + 1} 步组帧失败：{exc}", "fail")
            self._flow_done(False, f"组帧失败：{exc}")
            return
        sent_any = False
        for frame, node_addr in frames:
            ok, reason = self._channel.send(frame)
            if not ok:
                self._log(f"[失败] 第 {action.index + 1} 步发送失败：{reason}", "fail")
                self._flow_done(False, f"发送失败：{reason}")
                return
            sent_any = True
            self.spin_seq.setValue((self.spin_seq.value() + 1) & 0xFF)
            label = self._with_node(self._cmd_label(step.key), node_addr)
            self._add_raw_row("TX", frame, label)
            self._log(f"[TX] {label} ({len(frame)}B) {_fmt(frame)}", "tx")
            self._interactions.append({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "direction": "TX", "label": self._cmd_label(step.key), "node": node_addr,
                "result": "已发送", "reason": f"流程：{self._flow_runner.case.name}",
                "frame": core.format_hex(frame),
            })
        if not sent_any:
            self._flow_done(False, "没有可发送的帧")
            return
        self._flow_sent = True
        # 不等应答的步骤（如 14H F3 下行回延时修正）：发完立即推进，
        # 被测收到后会自己继续抄表并上报 13H F1，干等只会白超时判失败
        if getattr(step, "no_reply", False):
            self._log(f"  → 已下发（本步不等应答，直接进入下一步）", "ok")
            self._flow_done(True, "已下发（不等应答）")
            return
        self._flow_timer.start(int(max(0.2, step.timeout) * 1000))

    def _run_sta_reset(self, step) -> None:
        """下发 STA 硬件初始化（645 广播），让从节点重新入网并主动上报。

        优先走「协议8 虚拟表」页的串口（那才是 STA 总线）；虚拟表页没建/没监听时，
        退回本页串口下发并提示 —— 现场同一工装总线的情况下也能生效。
        """
        import sta_reset

        frame = sta_reset.build_frame()
        sent_by = ""
        # ① 优先本页内建的从节点模拟服务（645/698 独立串口，最贴合流程测试）
        if self._sta_sim is not None and self._sta_sim.isRunning():
            if self._sta_sim.send_frame(frame):
                sent_by = "本页从节点模拟串口"
        # ② 再由主程序注入的协议8 虚拟表通道
        provider = self._sta_reset_provider
        if not sent_by and provider is not None:
            try:
                if provider(frame):
                    sent_by = "协议8 虚拟表串口"
            except Exception as exc:            # 虚拟表页异常不应打断流程
                self._log(f"  （虚拟表下发失败：{exc}，改用本页串口）", "warn")
        if not sent_by:
            ok, reason = self._channel.send(frame)
            if not ok:
                self._log(f"[流程] STA 复位下发失败：{reason}", "fail")
                self._flow_done(False, f"复位下发失败：{reason}")
                return
            sent_by = "本页串口"
        self.spin_seq.setValue((self.spin_seq.value() + 1) & 0xFF)
        self._add_raw_row("TX", frame, "STA 复位")
        self._log(f"[流程] 已通过{sent_by}下发 STA 复位：{core.format_hex(frame)}", "tx")
        self._log("  645 广播复位不要求应答；等 STA 重新入网后会主动上报「从节点信息」", "info")
        self._flow_done(True, f"已下发 STA 复位（{sent_by}）")

    def _ack_uplink(self, frame: bytes, rows: Sequence[Tuple]) -> bool:
        """对模块主动上报回确认帧（AFN=00H F1），避免被测 CCO 反复重发同一帧。

        **只对「主动上报类」回确认**（06H/56H 整类 + 03H F10/F11 + 14H F3）；
        `14H F1`（路由请求抄读内容）与 `14H F2`（请求集中器时钟）不确认 ——
        它们要的是**业务应答**（回抄读内容 / 回当前时间），见 `_serve_router_request`。
        """
        table = {str(r[0]).strip(): r for r in rows if r}
        afn = _row_int(table, "应用功能码(AFN)")
        dt = table.get("数据单元标识(DT)")
        fn = _fn_from_dt_row(dt) if dt else None
        if afn is None or fn is None:
            return False
        import gdw_test_flows as flows

        if not flows.needs_confirm(afn, fn):
            return False
        cmd = self._find_cmd("00-1")
        if cmd is None:
            return False
        # 地址与序列号取原帧：源/目的互换，序列号沿用，模块标识沿用（原帧无地址域就别硬加）
        src = _row_value(table, "源地址(A1)") or self.edit_src.text().strip()
        dst = _row_value(table, "目的地址(A3)") or self.edit_dst.text().strip()
        info = dict(self._info_config())
        seq = _row_int(table, "报文序列号")
        if seq is not None:
            info["报文序列号"] = seq
        if "源地址(A1)" not in table and "地址域" not in table:
            info["通信模块标识"] = 0          # 原帧无地址域（对主节点操作）→ 确认帧同样不带
        info["dir"] = 0
        info["prm"] = 1
        # 确认帧数据单元（表 9，共 6 字节）= 4B BS + 2B 等待时间：
        #   BS：D0 = 命令状态（0 未处理 / 1 已处理）；D1~D31 = 信道 1~31（0 忙 / 1 闲）
        #   等待时间：BIN 2B，单位 s，协议要求 ≤5s —— 这里按用户口径填 1s
        # 低字节在前：全空闲 + 未处理 = FE FF FF FF，再跟 等待时间 01 00。
        # 空数据单元、只填 1 字节、或漏了 2 字节等待时间，都是不合规的确认帧。
        ack_data = bytes([0xFE, 0xFF, 0xFF, 0xFF]) + ACK_WAIT_SECONDS.to_bytes(2, "little")
        try:
            ack = core.build_frame(cmd, {}, src=dst or "000000000000",
                                   dst=src or "000000000000", info=info,
                                   raw_data=ack_data)
        except Exception as exc:
            self._log(f"  （确认帧组帧失败：{exc}）", "warn")
            return False
        ok, reason = self._channel.send(ack)
        if not ok:
            self._log(f"  （确认帧发送失败：{reason}）", "warn")
            return False
        self._add_raw_row("TX", ack, "确认（应答主动上报）")
        self._log(f"[TX] 确认帧（应答 {afn:02X}H F{fn} 主动上报；"
                  f"命令状态=未处理，等待时间={ACK_WAIT_SECONDS}s）"
                  f" {core.format_hex(ack)}", "tx")
        return True

    def _serve_router_request(self, frame: bytes, rows: Sequence[Tuple]) -> bool:
        """路由请求的**业务应答**（不是确认帧）。返回 True 表示已处理并发出应答。

        - `14H F1` 路由请求抄读内容 → 回 `14H F1` 下行：抄读标志=02H（可以抄读）+
          该从节点的正向有功总电能读报文（按组网档案里的协议：645-2007 / 698.45）；
          路由每请求一次就回一次，直到测试完成（流程里用 `12H F2` 暂停收尾）。
        - `14H F2` 路由请求集中器时钟 → 回 `14H F2` 下行：**当前系统时间**
          （秒/分/时/日/月/年，BCD），让被测 CCO 完成对时。
        """
        table = {str(r[0]).strip(): r for r in rows if r}
        afn = _row_int(table, "应用功能码(AFN)")
        dt = table.get("数据单元标识(DT)")
        fn = _fn_from_dt_row(dt) if dt else None
        if afn != 0x14 or fn not in (1, 2):
            return False

        if fn == 2:
            return self._reply_router_clock(table)
        return self._reply_router_read(table)

    def _reply_router_read(self, table: Dict[str, Any]) -> bool:
        """回 14H F1：可以抄读 + 按从节点协议的正向有功总电能读报文。"""
        import gdw_meter_request as req

        cmd = self._find_cmd("14-1")
        if cmd is None:
            return False
        addr = _row_value(table, "从节点地址")
        proto = self._node_proto_for(addr)
        payload = req.read_request_for(proto, addr)
        values = {
            "抄读标志": 2,                    # 02H = 可以抄读
            "通信延时相关性标志": 0,
            # 报文内容交给 schema 字段（长度由 length_field 自动派生），不要另拼 raw_data，
            # 否则数据长度字段会按 raw 算成 0
            "路由请求数据内容": payload.hex().upper(),
            # 附属节点：表 125 明确「02H 可以抄读时 n ≥ 0」，抄读内容里已带表地址，
            # **不需要再填从节点附属节点地址**（n=0 即可，填了反而可能与请求不匹配）
            "从节点附属节点数量": 0,
            "从节点附属节点列表": [],
        }
        # 报文序列号必须回显请求帧的序号（用户口径），不能用自己的自增序号
        seq = _row_int(table, "报文序列号")
        frame = core.build_frame(
            cmd, values,
            src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
            relay=self._relay_addrs(), info=self._router_reply_info(seq),
        )
        ok, reason = self._channel.send(frame)
        if not ok:
            self._log(f"  （回 14H F1 抄读内容失败：{reason}）", "warn")
            return False
        # 序列号沿用请求帧，界面上的自增序号不参与，也不递增（避免与请求序列脱节）
        self._flow_served += 1
        self._add_raw_row("TX", frame, "14H F1 回抄读内容")
        self._log(f"[TX] 14H F1 回抄读内容（从节点 {addr or '?'}，"
                  f"序列号={seq if seq is not None else '默认'}，"
                  f"{'698.45' if proto == 3 else '645-2007'} 正向有功总电能）"
                  f" {core.format_hex(frame)}", "tx")
        return True

    def _router_reply_info(self, seq: Any = None) -> Dict[str, Any]:
        """路由应答类下行（14H F1 回抄读内容）的外层 1376.2 头部。

        照现场参考报文的 13 字节头部填充（用户口径 2026-10-30）::

            68 3c 00 | 01 | 08 00 00 00 00 0e | 14 01 00 | 02 00 29 | <抄读内容> | CS 16
                       └控制域  └信息域(6B)      └AFN+DT     └标志/延时/L

        - 控制域 `01H`：DIR=0（下行）、**PRM=0（从动站，本帧是对模块请求的应答）**、
          通信方式=1（窄带电力线载波）；
        - 信息域首字节 `08H`：**D3 冲突检测=1**，其余位（路由标识/附属节点/通信模块标识/中继级别）为 0；
        - **报文序列号沿用请求帧的序号**（用户口径：回复的序列号要和请求匹配上），
          传 ``seq=None`` 时才退回界面上的序号；
        - 预计应答字节数 0、通信速率 0。
        """
        info = dict(self._info_config())
        info.update({"dir": 0, "prm": 0, "通信方式": 1, "冲突检测": 1,
                     # 参考报文信息域首字节就是 08H：D2 通信模块标识=0 ⇒ 不带地址域
                     "通信模块标识": 0,
                     "预计应答字节数": 0, "通信速率": 0})
        if seq is not None:
            info["报文序列号"] = int(seq) & 0xFF
        return info

    def _reply_router_clock(self, table: Dict[str, Any]) -> bool:
        """回 14H F2：把测试系统（集中器）的当前系统时间发给被测设备。"""
        cmd = self._find_cmd("14-2")
        if cmd is None:
            return False
        now = datetime.now()
        values = {
            "当前时间 秒": f"{now.second:02d}",
            "当前时间 分": f"{now.minute:02d}",
            "当前时间 时": f"{now.hour:02d}",
            "当前时间 日": f"{now.day:02d}",
            "当前时间 月": f"{now.month:02d}",
            "当前时间 年": f"{now.year % 100:02d}",
        }
        # 14H F2 同样回显请求帧的序列号
        seq = _row_int(table, "报文序列号")
        frame = core.build_frame(
            cmd, values,
            src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
            relay=self._relay_addrs(), info=self._router_reply_info(seq),
        )
        ok, reason = self._channel.send(frame)
        if not ok:
            self._log(f"  （回 14H F2 系统时间失败：{reason}）", "warn")
            return False
        self._flow_served += 1
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        self._add_raw_row("TX", frame, "14H F2 回系统时间")
        self._log(f"[TX] 14H F2 回系统时间 {stamp}（序列号="
                  f"{seq if seq is not None else '默认'}） {core.format_hex(frame)}", "tx")
        return True

    def _node_proto_for(self, addr: str) -> int:
        """按从节点地址在组网参数里找协议；找不到时退回第一个启用节点，再退回 645。"""
        key = net_mod.normalize_addr(addr)
        net = self._collect_network()
        for node in net.active_slaves():
            if key and node.addr == key:
                return int(node.proto)
        slaves = net.active_slaves()
        if slaves:
            return int(slaves[0].proto)
        return net_mod.PROTO_645_2007

    def _flow_consume_buffered(self, step) -> Optional[Tuple[int, int]]:
        """在收帧缓存里找一个满足该步等待（含 ``accept`` 兼容项）且未被消费的上行。

        命中即标记已消费并返回 ``(afn, fn)``；未命中返回 ``None``。
        """
        import gdw_test_flows as flows

        if step is None:
            return None
        if step.kind == flows.KIND_SERVE:
            # 服务步只关心 until（如 06H F2）：缓存里提前到的抄读数据直接算完成
            if not step.until or step.until[0] < 0:
                return None
            for item in self._flow_rx_buffer:
                _ts, afn, fn, used = item
                if used:
                    continue
                if (afn, fn) == tuple(step.until):
                    item[3] = True
                    return (afn, fn)
            return None
        if step.afn < 0:
            return None
        for item in self._flow_rx_buffer:
            _ts, afn, fn, used = item
            if used:
                continue
            if flows.step_accepts(step, afn, fn):
                item[3] = True
                return (afn, fn)
        return None

    def _flow_note_uplink(self, step, afn: int, fn: int) -> str:
        """收到期望上行后的附加说明。

        命中 ``accept`` 兼容项（如注册流程的 06H F1）时告警并说明新标准要求；
        主判据命中返回空串。
        """
        import gdw_test_flows as flows

        if flows.is_primary_uplink(step, afn, fn):
            return ""
        note = (f"收到 {afn:02X}H F{fn}（兼容旧标准），"
                f"新标准应报 {step.afn:02X}H F{step.fn}")
        self._log(f"  ⚠ {note}", "warn")
        return note

    def _flow_buffer_frame(self, afn: int, fn: int) -> None:
        self._flow_rx_buffer.append([datetime.now(), afn, fn, False])
        # 只留最近 200 条，避免长时间流程把内存堆起来
        if len(self._flow_rx_buffer) > 200:
            del self._flow_rx_buffer[:-200]

    def _flow_poll_begin(self, step) -> None:
        """轮询步骤：在 step.timeout 秒内重复下发同一条命令，直到 check 通过。"""
        import time as _time

        self._flow_poll_step = step
        self._flow_poll_deadline = _time.monotonic() + max(1.0, step.timeout)
        self._log(f"[流程] 轮询开始（最长 {step.timeout / 60:.1f} 分钟，"
                  f"每 {self.JOIN_POLL_INTERVAL_S:.0f}s 一次）：{step.title}", "info")
        self._flow_poll_send()

    def _flow_poll_send(self) -> None:
        import gdw_test_flows as flows
        import time as _time

        step = self._flow_poll_step
        if step is None or self._flow_runner is None:
            return
        remaining = self._flow_poll_deadline - _time.monotonic()
        if remaining <= 0:
            self._log(f"[流程] 轮询超时：{step.title}", "fail")
            self._flow_poll_step = None
            self._flow_done(False, f"轮询超时（{step.timeout / 60:.1f} 分钟）")
            return
        try:
            frame = self._build_flow_frame(step)
        except Exception as exc:
            self._flow_poll_step = None
            self._flow_done(False, f"组帧失败：{exc}")
            return
        ok, reason = self._channel.send(frame)
        if not ok:
            self._flow_poll_step = None
            self._flow_done(False, f"发送失败：{reason}")
            return
        self.spin_seq.setValue((self.spin_seq.value() + 1) & 0xFF)
        label = self._cmd_label(step.key) + "（轮询）"
        self._add_raw_row("TX", frame, label)
        self._log(f"[TX] {label} ({len(frame)}B) {_fmt(frame)}", "tx")
        # 等应答：单次等待不超过轮询间隔
        wait_ms = int(min(self.JOIN_POLL_INTERVAL_S, max(1.0, remaining)) * 1000)
        self._flow_timer.start(wait_ms)

    def _flow_poll_result(self, ok: bool) -> bool:
        """轮询命令的应答处理：通过则收尾，否则等间隔后再发。"""
        import gdw_test_flows as flows

        step = self._flow_poll_step
        if step is None:
            return False
        if ok:
            self._flow_poll_step = None
            self._flow_done(True, "轮询到全部入网")
            return True
        # 未通过：按间隔重发（由定时器触发 _on_flow_timeout → 这里会被再次调用）
        return False

    def _capture_delay_request(self, table: Dict[str, Any]) -> None:
        """记录 14H F3 上行：从节点地址 + 预计延迟时间 + 抄读数据内容。"""
        addr = _row_value(table, "从节点地址")
        delay = 0
        delay_row = table.get("预计延迟时间")
        if delay_row:
            # 原始值形如 "0xDC05"（2 字节），解析值才是十进制
            try:
                delay = int(str(delay_row[2]).strip())
            except (TypeError, ValueError):
                text = str(delay_row[1] or "").replace("0x", "").replace(" ", "")
                try:
                    delay = int(text, 16)
                except ValueError:
                    delay = 0
        content = b""
        content_row = table.get("抄读数据内容")
        if content_row:
            # 这一行的「解析值」是 "24字节"，真正的 hex 在「原始值」
            for candidate in (content_row[1], content_row[2]):
                try:
                    content = _parse_hex(str(candidate))
                    break
                except Exception:
                    continue
        self._flow_delay_req = {"addr": addr, "delay_ms": delay, "content": content}
        self._log(f"[流程] 收到 14H F3 上行：从节点 {addr or '?'}、预计延迟 {delay}ms、"
                  f"待修正报文 {len(content)}B", "info")

    def _sta_recent_responses(self) -> List[bytes]:
        """虚拟表最近发出的应答帧（用于「上报数据是否与应答一致」的判定）。"""
        svc = self._sta_sim
        if svc is None:
            return []
        return list(getattr(svc, "recent_responses", []) or [])

    def _build_flow_frames(self, step) -> List[Tuple[bytes, str]]:
        """流程发帧：抄表类步骤按从节点协议填报文，并按节点各发一帧。

        - `13H F1`/`14H F1` 等带「报文内容」的命令：报文内容 = 该从节点协议的
          读正向有功总电能报文（645 → 68…11 04 33 33 34 33 CS 16；698 → GET 00100200），
          报文长度由生成器自动派生；地址按节点填、协议类型按节点填。
        - 「按组网参数展开」开启且命令是单节点类 → 每个从节点各发一帧。
        """
        cmd = self._find_cmd(step.key)
        if cmd is None:
            raise core.FrameBuildError(f"未找到命令 {step.key}")
        field_names = [str(f.get("name")) for f in (cmd.fields or ())]
        needs_request = any(n in field_names for n in ("报文内容", "修正通信数据内容"))
        data_field = ("报文内容" if "报文内容" in field_names else
                      "修正通信数据内容" if "修正通信数据内容" in field_names else "")
        net = self._collect_network()
        nodes = net.active_slaves()

        targets = [None]
        if nodes and needs_request:
            # 抄表类：一份报文只能对应一块表 → 每个从节点各发一帧（无论是否列表型命令）
            targets = list(nodes)
        elif nodes and net.fanout and net_mod.is_node_scoped(cmd):
            targets = list(nodes)

        frames: List[Tuple[bytes, str]] = []
        for node in targets:
            values = dict(self._values_for(core.PAGE_READ, step.key,
                                           node.addr if node is not None else ""))
            runner = self._flow_runner
            if runner is not None:
                values.update(runner.values_for(step))
            if needs_request:
                import gdw_meter_request as req

                addr = node.addr if node is not None else values.get("从节点附属节点地址", "")
                proto = int(node.proto) if node is not None else 0
                payload = req.read_request_for(proto, str(addr or ""))
                # 14H F3 下行：优先用模块在 14H F3 上行里请求「待修正」的那份报文
                captured = self._flow_delay_req if step.key == "14-3" else None
                if captured and captured.get("content"):
                    payload, note = req.apply_delay_correction(
                        captured["content"], int(captured.get("delay_ms") or 0))
                    if captured.get("addr"):
                        addr = captured["addr"]
                    self._log(f"[流程] 14H F3 下行按上行请求回送：{note}", "info")
                values[data_field] = payload.hex().upper()
                if "通信协议类型" in field_names:
                    values["通信协议类型"] = req.msg_proto_for_node(proto)
                # 05H F3 启动广播用的是「控制字」（表 43）：00H 透明传输 / 01H 645-1997 /
                # 02H 645-2007 / 03H 相位识别功能。**03H 不是 698.45** —— 表 43 没有 698 的
                # 编码，698 表按 00H 透明传输发原始报文。
                if "控制字" in field_names:
                    code = int(proto)
                    if code == net_mod.PROTO_645_2007:
                        values["控制字"] = 2
                    elif code == net_mod.PROTO_645_1997:
                        values["控制字"] = 1
                    else:
                        values["控制字"] = 0
                # 14H F1 下行（表 125）：抄读内容里已带表地址，附属节点数量 n=0 即可，
                # 不再填附属节点地址（用户口径）
                if (node is not None and "从节点附属节点列表" in field_names
                        and step.key != "14-1"):
                    values["从节点附属节点列表"] = [{"从节点附属节点地址": node.addr}]
                self._log(f"[流程] 报文内容按 {('698.45' if proto == 3 else '645-2007')}"
                          f" 填：{req.describe_request(payload)}", "info")
            raw_text = (self._raw_for(core.PAGE_READ, step.key).strip()
                        or self._raw_for(core.PAGE_WRITE, step.key).strip())
            raw = _parse_hex(raw_text) if raw_text else b""
            frame = core.build_frame(
                cmd, values,
                src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
                relay=self._relay_addrs(), info=self._info_config(), raw_data=raw,
            )
            frames.append((frame, node.addr if node is not None else ""))
        return frames

    def _build_flow_frame(self, step) -> bytes:
        values = {}
        runner = self._flow_runner
        if runner is not None:
            values.update(runner.values_for(step))
        from_widget = self._values_for(core.PAGE_WRITE if step.key.startswith("1") else core.PAGE_READ,
                                       step.key, "")
        merged = dict(from_widget)
        merged.update(values)
        cmd = self._find_cmd(step.key)
        if cmd is None:
            raise core.FrameBuildError(f"未找到命令 {step.key}")
        raw_text = self._raw_for(core.PAGE_READ, step.key).strip() or \
            self._raw_for(core.PAGE_WRITE, step.key).strip()
        raw = _parse_hex(raw_text) if raw_text else b""
        return core.build_frame(
            cmd, merged,
            src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
            relay=self._relay_addrs(), info=self._info_config(), raw_data=raw,
        )

    def _flow_done(self, ok: bool, note: str = "") -> None:
        if self._flow_runner is None:
            return
        self._flow_timer.stop()
        action = self._flow_runner.advance(ok, note)
        self._render_flow_runner()
        self._run_flow_action(action)

    def _on_flow_timeout(self) -> None:
        if self._flow_runner is None or self._flow_action is None:
            return
        step = self._flow_action.step
        if self._flow_poll_step is not None:
            # 轮询窗口内没等到应答 → 直接按间隔重发（不判失败）
            self._flow_poll_send()
            return
        if self._flow_action.kind == "sleep":
            self._flow_done(True, "等待结束")
            return
        if self._flow_action.kind == "manual":
            self._flow_done(False, "未人工确认（按跳过处理）")
            return
        if self._flow_action.kind == "serve":
            # 服务窗口内一直在回抄读内容/时间，但始终没等到 06H F2 抄读数据
            served = getattr(self, "_flow_served", 0)
            if served:
                self._log(f"[流程] 服务窗口结束：已回 {served} 次路由请求，但未收到抄读数据上报",
                          "warn")
                self._flow_done(False, f"已服务 {served} 次，未收到 06H F2 抄读数据")
            else:
                self._flow_done(False, "窗口内没有收到 14H F1 请求抄读内容")
            return
        kind = "wait" if self._flow_action.kind == "wait" else "send"
        self._log(f"[流程] 超时（{kind}）：{step.title if step else ''}", "warn")
        self._flow_done(step.optional if step else False, "超时")

    def _flow_on_frame(self, frame: bytes) -> bool:
        """流程执行期间的收帧处理；返回 True 表示已被流程消费。"""
        runner = self._flow_runner
        if runner is None or self._flow_action is None:
            return False
        action = self._flow_action
        rows = core.parse_table(frame)
        info = {r[0].strip(): r for r in rows}
        afn = _row_int(info, "应用功能码(AFN)")
        fn = None
        dt = info.get("数据单元标识(DT)")
        if dt is not None:
            fn = _fn_from_dt_row(dt)
        if afn is None:
            return False
        # 流程期间的每一帧都进缓存：早到的上行（如硬件初始化后立刻上报的 03H F10）
        # 在进入对应 wait 步时还能被认到，不会「一直等不到」
        self._flow_buffer_frame(afn, fn if fn is not None else -1)
        # 14H F3 上行 = 模块请求「按延时修正通信数据」，记下地址/延迟/报文，
        # 等下发 14H F3 下行时按它回送（而不是自己新造一帧）
        if afn == 0x14 and fn == 3:
            self._capture_delay_request(info)
        if action.kind == "serve":
            # 服务步：收到 until 指定的上行（06H F2 抄读数据）即完成并做数据校验
            step = action.step
            if step.until and step.until[0] >= 0 and (afn, fn) == tuple(step.until):
                check_name = getattr(step, "check", "") or ""
                if check_name:
                    import gdw_test_flows as flows

                    ok, note = flows.run_check(check_name, rows, (),
                                               self._sta_recent_responses())
                    self._log(f"  → 数据判定：{note}", "ok" if ok else "fail")
                    self._flow_done(ok, note or f"已服务 {self._flow_served} 次路由请求")
                    return True
                self._flow_done(True, f"已服务 {self._flow_served} 次路由请求")
                return True
            # 其它帧（14H F1/F2 的业务应答已在 _serve_router_request 里回过）继续服务
            return True
        if action.kind == "wait":
            step = action.step
            import gdw_test_flows as flows

            if not flows.step_accepts(step, afn, fn):
                wait_extra = "".join(f"/{a:02X}H F{f}" for a, f in (step.accept or ()))
                self._log(f"  → 流程未匹配（收到 {afn:02X}H F{fn}，等 "
                          f"{step.afn:02X}H F{step.fn}{wait_extra}）", "warn")
                return False
            extra_note = self._flow_note_uplink(step, afn, fn)
            self._log(f"  → 流程第 {action.index + 1} 步：收到期望上行", "ok")
            check_name = getattr(step, "check", "") or ""
            if check_name:
                ok, note = flows.run_check(check_name, rows, (), self._sta_recent_responses())
                self._log(f"  → 数据判定：{note}", "ok" if ok else "fail")
                self._flow_done(ok, note)
                return True
            self._flow_done(True, extra_note or "收到期望上行")
            return True
        if action.kind == "send" or action.kind == "poll":
            step = action.step
            cmd = self._find_cmd(step.key)
            verdict = expect_mod.judge(cmd, frame) if cmd is not None else {}
            code = verdict.get("verdict")
            if code in (expect_mod.V_DENY_FAIL, expect_mod.V_UNSUPPORTED, expect_mod.V_BAD):
                if action.kind == "poll" and self._flow_poll_step is not None:
                    # 轮询期间的否认/坏帧不立即判失败，等窗口内重试
                    self._log(f"  → 轮询应答异常（{verdict.get('reason')}），继续等待", "warn")
                    return True
                self._flow_done(False, str(verdict.get("reason") or "否认/坏帧"))
                return True
            # 确认帧、同命令数据帧、步骤显式声明可接受的应答（如 13H F1 延时相关时先回 14H F3）都算完成
            accept = tuple(getattr(step, "accept", ()) or ())
            accepted = any(afn == a and (f < 0 or fn == f) for a, f in accept)
            if afn == 0x00 or (cmd is not None and afn == cmd.afn) or accepted:
                import gdw_test_flows as flows

                check_name = getattr(step, "check", "") or ""
                ok, note = True, str(verdict.get("reason") or "已应答")
                if check_name:
                    archive = flows.default_archive_addrs(self._collect_network())
                    ok, detail = flows.run_check(check_name, rows, archive,
                                                 self._sta_recent_responses())
                    note = detail or note
                if action.kind == "poll" and self._flow_poll_step is not None:
                    if ok:
                        self._flow_poll_result(True)
                    else:
                        self._log(f"  → 轮询第 N 次未达标：{note}", "warn")
                    return True
                self._flow_done(ok, note)
                return True
            return False
        return False

    def _on_send(self) -> None:
        if self._awaiting or self._next_timer.isActive():
            self._log("[提示] 正在等待上一帧应答，稍后再发", "warn")
            return
        if not self._channel.ready():
            reason = self._channel.state_text() or "通道未就绪"
            self._log(f"[失败] {reason}", "fail")
            QMessageBox.warning(self, "通道未就绪", reason)
            return
        self._persist_current_params()          # 发送前把当前面板的改动落到存档
        targets = self._targets()
        if not targets:
            QMessageBox.information(self, "提示", "请先在左侧选择（或勾选）要发送的命令")
            return
        if not self._joined_addrs:
            self._log("[提示] 还没确认从节点入网：路由/查询类命令（如 10H F104、10H F2）"
                      "多数只会回否认。建议先点「准备测试网络」建档并查拓扑", "warn")
        self._preflight = None
        self._queue_overrides = {}
        self._session_started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._interactions.clear()
        self._log(f"[信息] 开始发送 {len(targets)} 条命令（含按从节点展开）", "info")
        self._start_queue(targets, reset_counter=True)

    def _start_queue(self, targets: List[Tuple[str, str, str]], *,
                     reset_counter: bool = False) -> None:
        self._queue_commands = targets
        self._queue_idx = 0
        if reset_counter:
            self._sent = 0
        self._set_running(True)
        self._send_next()

    def _send_next(self) -> None:
        if self._awaiting:
            return
        if self._queue_idx >= len(self._queue_commands):
            self._finish_queue()
            return
        page, key, node_addr = self._queue_commands[self._queue_idx]
        try:
            frame = self._build_frame_for(page, key, node_addr)
        except core.FrameBuildError as exc:
            label = self._cmd_label(key)
            self._log(f"[失败] {self._with_node(label, node_addr)} 组帧失败：{exc}", "fail")
            self._add_info_row("组帧失败", str(exc), label, node_addr)
            self._record_stat(key, store.STATE_UNTESTED, f"组帧失败：{exc}", node_addr)
            self._advance()
            return
        self._awaiting = True
        self._attempt = 0
        self._pending_frame = frame
        self._pending_key = key
        self._pending_page = page
        self._pending_node = node_addr
        self._pending_confirmed = False
        self._pending_saw_other = False
        self._send_frame(frame, key, node_addr)

    @staticmethod
    def _with_node(label: str, node_addr: str) -> str:
        return f"{label} [从节点 {node_addr}]" if node_addr else label

    def _build_frame_for(self, page: str, key: str, node_addr: str = "") -> bytes:
        if self._current is not None and self._current.key == key:
            self._persist_current_params()      # 正在显示这条命令：先落一次最新控件值
        if page == core.PAGE_EB and self._current_eb is not None and self._current_eb.di == key:
            self._persist_current_params()
        if page == core.PAGE_EB:
            item = next((e for e in core.eb_items() if e.di == key), None)
            if item is None:
                raise core.FrameBuildError(f"未找到 EB 数据标识 {key}")
            data = b""
            raw_text = self._raw_for(page, key).strip()
            if self.combo_eb_ctrl.currentData() == 0x14 and item.fields:
                # 存档里没有该 DI 的参数时交给 encode_eb_data 用字段默认值，绝不复用当前显示的 DI
                data = core.encode_eb_data(item.di, self._values_for(page, key))
            elif raw_text:
                data = _parse_hex(raw_text)
            return core.build_eb_frame(
                item.di, addr=self.edit_eb_addr.text().strip(),
                ctrl=self.combo_eb_ctrl.currentData(), data=data,
                wrap=bool(self.combo_eb_wrap.currentData()),
                src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
                info=self._info_config(),
            )
        cmd = self._find_cmd(key)
        if cmd is None:
            raise core.FrameBuildError(f"未找到命令 {key}")
        raw = b""
        raw_text = self._raw_for(page, key).strip()
        if raw_text:
            raw = _parse_hex(raw_text)
        values = self._values_for(page, key, node_addr)
        override = self._queue_overrides.get(key)      # 前置流程按需覆盖（如 10H F2 的查询数量）
        if override:
            values = dict(values)
            values.update(override)
        return core.build_frame(
            cmd, values,
            src=self.edit_src.text().strip(), dst=self.edit_dst.text().strip(),
            relay=self._relay_addrs(), info=self._info_config(), raw_data=raw,
        )

    def _send_frame(self, frame: bytes, key: str, node_addr: str = "") -> None:
        ok, reason = self._channel.send(frame)
        label = self._with_node(self._cmd_label(key), node_addr)
        if not ok:
            self._log(f"[失败] {label} 发送失败：{reason}", "fail")
            self._add_info_row("发送失败", f"{reason}", self._cmd_label(key), node_addr)
            self._record_stat(key, store.STATE_UNTESTED, f"发送失败：{reason}", node_addr)
            self._awaiting = False
            self._advance()
            return
        self._sent += 1
        self.spin_seq.setValue((self.spin_seq.value() + 1) & 0xFF)
        self._add_raw_row("TX", frame, label)
        self._log(f"[TX] {label} ({len(frame)}B) {_fmt(frame)}", "tx")
        self._interactions.append({
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "direction": "TX", "label": self._cmd_label(key),
            "node": node_addr, "result": "已发送", "reason": "",
            "frame": core.format_hex(frame),
        })
        self._timeout_timer.start(max(100, self.spin_timeout.value()))
        self._update_txrx()

    def _advance(self) -> None:
        self._timeout_timer.stop()
        self._queue_idx += 1
        self._next_timer.start()

    def _finish_queue(self) -> None:
        self._set_running(False)
        self._log(f"[信息] 本轮结束：共发送 {self._sent} 帧", "info")
        if self._preflight is not None:
            self._finish_preflight()

    def _on_reply_timeout(self) -> None:
        if not self._awaiting:
            return
        retries = self.spin_retries.value()
        node = self._pending_node
        label = self._with_node(self._cmd_label(self._pending_key), node)
        if self._attempt < retries:
            self._attempt += 1
            self._log(f"[超时] {label} 未收到应答，重试 {self._attempt}/{retries}", "warn")
            # 重发同一帧（不重新组帧，避免上一轮定时器把新一轮提前发出）
            self._send_frame(self._pending_frame, self._pending_key, node)
            return
        self._log(f"[超时] {label} 重试用尽（{retries} 次）", "fail")
        if self._pending_confirmed:
            # 抄表/查询类：设备确认收到但没有回同命令数据 ⇒ 按用户口径不算支持
            state = store.STATE_CONFIRM_ONLY
            reason = "设备已确认受理，但未收到同 AFN/Fn 的上行数据"
        elif self._pending_saw_other:
            state = store.STATE_MISMATCH
            reason = "收到过报文，但没有一条属于该命令"
        else:
            state = store.STATE_NO_REPLY
            reason = f"{self.spin_timeout.value()}ms 内无应答（重试 {retries} 次）"
        self._add_info_row("超时", reason, self._cmd_label(self._pending_key), node)
        self._record_stat(self._pending_key, state, reason, node)
        self._pending_confirmed = False
        self._pending_saw_other = False
        self._awaiting = False
        self._advance()

    def _finish_response(self, key: str, node: str, text: str, kind: str,
                         reason: str, rows: Sequence[Tuple], frame: bytes,
                         state: Optional[str]) -> None:
        """一次应答终结：停表 → 日志/信息表/交互明细 → 记录状态 → 推进队列。"""
        self._timeout_timer.stop()
        label = self._with_node(self._cmd_label(key), node)
        self._log(f"  → {text}：{reason}", kind)
        self._add_info_row(text, reason, self._cmd_label(key), node)
        if key in (net_mod.PREFLIGHT_NODE_INFO, net_mod.PREFLIGHT_NODE_COUNT,
                   net_mod.PREFLIGHT_TOPOLOGY):
            self._note_preflight_rows(key, rows)
        self._interactions.append({
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "direction": "RX", "label": self._cmd_label(key), "node": node,
            "result": text, "reason": reason, "frame": core.format_hex(frame),
        })
        if state:
            self._record_stat(key, state, reason, node)
        self._show_detail(rows)
        self._awaiting = False
        self._pending_confirmed = False
        self._pending_saw_other = False
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
        node = self._pending_node if self._awaiting else ""
        pending_label = self._cmd_label(self._pending_key) if self._awaiting and self._pending_key else ""
        self._add_raw_row("RX", frame, pending_label)
        self._log(f"[RX] ({len(frame)}B) {_fmt(frame)}", "ok")
        # 模块主动上报：先按协议「业务应答」，再回确认帧（否则被测 CCO 会一直重发同一条）
        rows = core.parse_table(frame)
        try:
            # 14H F1（请求抄读内容）/14H F2（请求集中器时钟）要的是业务应答，不是确认帧
            if not self._serve_router_request(frame, rows):
                self._ack_uplink(frame, rows)
        except Exception as exc:
            self._log(f"  （自动应答/确认失败：{exc}）", "warn")
        # 流程测试执行期间，收帧优先交给流程引擎（流程里既有 send 也有被动 wait）
        if self._flow_runner is not None and self._flow_on_frame(frame):
            return
        if not self._awaiting or not self._queue_commands:
            self._log("  → 忽略（当前没有在等应答）", "warn")
            return
        page, key = self._pending_page, self._pending_key
        label = self._with_node(self._cmd_label(key), node)
        if page == core.PAGE_EB:
            # EB 命令是 645 帧（可包在 AFN=02H F1 里）：本页只确认「收到了一帧」，
            # 业务含义交给解析器/单帧解析页 —— 没有可自证的字段级成功判据。
            rows = core.parse_table(frame)
            result = {"ok": None, "matched": bool(frame),
                      "reason": "已接收 EB 响应（未做字段级判定）", "rows": rows}
            self._timeout_timer.stop()
            if not result.get("matched"):
                self._log(f"  → 忽略（{result.get('reason')}）", "warn")
                self._timeout_timer.start(max(100, self.spin_timeout.value()))
                return
            self._finish_response(key, node, "已接收（未做字段级判定）", "info",
                                  str(result.get("reason") or ""), rows, frame, None)
            return

        cmd = self._find_cmd(key)
        if cmd is None:
            return
        verdict = expect_mod.judge(cmd, frame)
        code = verdict["verdict"]
        reason = str(verdict.get("reason") or "")

        # ① 抄表/查询类先收到确认：设备已受理，继续等同 AFN/Fn 的数据，不推进队列
        if code == expect_mod.V_WAITING:
            self._timeout_timer.stop()
            self._pending_confirmed = True
            self._log(f"  → {reason}", "info")
            self._timeout_timer.start(max(100, self.spin_timeout.value()))
            return
        # ② 无关帧 / 坏帧：记一笔，继续等本命令的应答
        if not verdict["final"]:
            self._pending_saw_other = True
            self._log(f"  → 忽略（{reason}）", "warn")
            self._interactions.append({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "direction": "RX", "label": self._cmd_label(key), "node": node,
                "result": "忽略", "reason": reason, "frame": core.format_hex(frame),
            })
            self._timeout_timer.start(max(100, self.spin_timeout.value()))
            return

        state = expect_mod.verdict_state(code)
        text = {
            expect_mod.V_CONFIRM: "支持（确认）",
            expect_mod.V_DATA: "成功",
            expect_mod.V_DENY_FAIL: "支持但执行报错",
            expect_mod.V_UNSUPPORTED: "不支持",
        }.get(code, "已接收")
        hint = str(verdict.get("hint") or "")
        if hint:
            self._log(f"  → 处置建议：{hint}", "warn")
        kind = "ok" if verdict.get("ok") is True else (
            "fail" if verdict.get("ok") is False else "info")
        self._finish_response(key, node, text, kind, reason,
                              verdict.get("rows") or [], frame, state)

    # ── 展示 ────────────────────────────────────────────────────────────
    def _update_txrx(self) -> None:
        rx = self.raw_table.rowCount() - self._sent
        self.lbl_txrx.setText(f"TX {self._sent} 帧 / RX {max(0, rx)} 帧")

    def _add_raw_row(self, direction: str, frame: bytes, label: str = "") -> None:
        if self.raw_table.rowCount() >= RAW_ROW_LIMIT:
            self.raw_table.removeRow(0)
            if self._frame_rows:
                self._frame_rows.pop(0)
        row = self.raw_table.rowCount()
        self.raw_table.insertRow(row)
        self.raw_table.setItem(row, 0, QTableWidgetItem(self._now()))
        self.raw_table.setItem(row, 1, QTableWidgetItem(direction))
        cmd_item = QTableWidgetItem(label or "")
        cmd_item.setToolTip(label or "")
        self.raw_table.setItem(row, 2, cmd_item)
        self.raw_table.setItem(row, 3, QTableWidgetItem(str(len(frame))))
        item = QTableWidgetItem(_fmt(frame, limit=0))
        item.setData(Qt.ItemDataRole.UserRole, len(self._frame_rows))
        self.raw_table.setItem(row, 4, item)
        self._frame_rows.append(bytes(frame))
        self.raw_table.scrollToBottom()

    def _on_raw_row_activated(self, row: int, _col: int) -> None:
        item = self.raw_table.item(row, 4)
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

    def _add_info_row(self, result: str, detail: str, label: str = "",
                      node_addr: str = "") -> None:
        row = self.info_table.rowCount()
        self.info_table.insertRow(row)
        self.info_table.setItem(row, 0, QTableWidgetItem(self._now()))
        cmd_item = QTableWidgetItem(label or "")
        cmd_item.setToolTip(label or "")
        self.info_table.setItem(row, 1, cmd_item)
        node_item = QTableWidgetItem(node_addr or "—")
        node_item.setToolTip(node_addr or "")
        self.info_table.setItem(row, 2, node_item)
        self.info_table.setItem(row, 3, QTableWidgetItem(result))
        detail_item = QTableWidgetItem(detail)
        detail_item.setToolTip(detail)
        self.info_table.setItem(row, 4, detail_item)
        self.info_table.scrollToBottom()

    def _show_detail(self, rows: Sequence[Tuple]) -> None:
        if not rows:
            return
        for line in core.detail_lines(rows)[:60]:
            self._log("   " + line.strip(), "hint")

    def _log(self, text: str, kind: str = "info") -> None:
        """按类别着色追加一行（QPlainTextEdit 不认 QSS 颜色，必须走字符格式）。

        同一份文本带时间戳写进 ``logs/gdw_test_YYYYMMDD.log``（本次会话缓冲也留一份，
        供「导出日志」用——面板上不带时间戳，导出的文件带）。
        """
        self._session_log.append(text)
        palette = LOG_PALETTES[self._dark]
        color = {"ok": palette["ok"], "fail": palette["fail"], "warn": palette["warn"],
                 "tx": palette["tx"], "hint": palette["hint"]}.get(kind, palette["info"])
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(Qt.GlobalColor.black)
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
        self._session_log.clear()          # 只清本次会话缓冲，落盘的历史文件不动
        self._update_txrx()

    def _on_clear_params(self) -> None:
        """清理所有命令参数（全局测试参数、勾选、支持统计都保留）。"""
        if QMessageBox.question(
            self, "清理所有参数",
            "将清掉所有命令已记录的数据单元参数、附加数据与 EB 数据内容。\n"
            "全局测试参数（地址/序列号/超时/重试/通道）、勾选状态与支持统计不受影响。\n\n"
            "确定继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        removed = self._params.clear_params()
        self._params.save()
        # 当前面板也打回默认态：重建字段 → 默认值 → 清附加数据
        if self._page == core.PAGE_EB and self._current_eb is not None:
            self._render_eb_fields()
            self._set_eb_raw_text("")
        elif self._current is not None:
            self._render_cmd_fields()
            self._set_raw_data_text("")
        self._refresh_preview()
        self._log(f"[信息] 已清理所有命令参数（{removed} 条记录）", "info")

    # ── 支持统计 ────────────────────────────────────────────────────────
    def _record_stat(self, key: str, state: str, reason: str, node_addr: str = "") -> None:
        if not key:
            return
        self._params.set_stat(store.stat_key(key, node_addr), state, reason,
                              datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self._schedule_save()
        self._refresh_stats()

    def _stats_commands(self) -> List[core.GdwCommand]:
        """参与支持统计的命令：**只算可下发的下行命令**。

        上行命令（00H/50H 确认否认应答、06H/56H 主动上报）由被测设备自己发出，
        本页不下发，因此不给支持结论 —— 它们单独列在报告附录，不参与分母。
        EB 页是 DI 口径且无字段级判据，也不计入。
        """
        cmds = list(core.all_commands())
        edited = {c.key for c in cmds}
        cmds.extend(c for c in core.custom_commands() if c.key not in edited)
        return expect_mod.sendable_commands(cmds)

    def _uplink_command_rows(self) -> List[Tuple[str, str, str]]:
        """上行命令清单（AFN 文本, Fn 文本, 名称）—— 报告附录用。"""
        cmds = list(core.all_commands())
        edited = {c.key for c in cmds}
        cmds.extend(c for c in core.custom_commands() if c.key not in edited)
        return [(f"{c.afn:02X}H", f"F{c.fn}", c.name)
                for c in expect_mod.uplink_commands(cmds)]

    def _stats_summary(self) -> Dict[str, Any]:
        return store.summarize(self._stats_commands(), self._params.stats(),
                               self._collect_network().nodes_or_placeholder())

    def _refresh_stats(self, *_args) -> None:
        summary = self._stats_summary()
        self._last_summary = summary
        self.lbl_stats.setText(store.summary_text(summary))
        self.lbl_stats.setToolTip(store.per_afn_text(summary))
        table = self.stats_table
        scroll = table.verticalScrollBar().value()
        table.setRowCount(0)
        for row_values in summary["rows"]:
            row = table.rowCount()
            table.insertRow(row)
            for col, value in enumerate(row_values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if col == 5:                    # 状态列着色：支持绿、不匹配/无响应红
                    state = next((k for k, v in store.STATE_LABELS.items()
                                  if v == str(value)), "")
                    palette = LOG_PALETTES[self._dark]
                    if state in store.SUPPORTED_STATES:
                        item.setForeground(QColor(palette["ok"]))
                    elif state in (store.STATE_NO_REPLY, store.STATE_MISMATCH):
                        item.setForeground(QColor(palette["fail"]))
                table.setItem(row, col, item)
        table.verticalScrollBar().setValue(scroll)   # 跑批时别把用户正在看的行冲掉

    def _on_clear_stats(self) -> None:
        if QMessageBox.question(
            self, "清空统计",
            "只清支持统计记录（命令参数与日志不动）。确定继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        removed = self._params.clear_stats()
        self._params.save()
        self._refresh_stats()
        self._log(f"[信息] 已清空支持统计（{removed} 条）", "info")

    def _on_export_stats(self) -> None:
        summary = self._stats_summary()
        path, _flt = QFileDialog.getSaveFileName(
            self, "导出支持统计",
            str(app_paths.data_path(f"国网AFN_Fn支持统计_{datetime.now():%Y%m%d_%H%M%S}.csv")),
            "CSV 文件 (*.csv);;所有文件 (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                fh.write(store.stats_csv(summary))
        except Exception as exc:               # noqa: BLE001
            QMessageBox.warning(self, "导出失败", f"{type(exc).__name__}: {exc}")
            return
        self._log(f"[信息] 支持统计已导出：{path}", "info")

    def _on_export_report(self) -> None:
        """导出遍历测试报告（单文件 HTML，含环境/支持汇总/逐条结果/交互报文）。"""
        summary = self._stats_summary()
        net = self._collect_network()
        path, _flt = QFileDialog.getSaveFileName(
            self, "生成遍历测试报告",
            str(app_paths.data_path(f"国网AFN遍历测试报告_{datetime.now():%Y%m%d_%H%M%S}.html")),
            "HTML 文件 (*.html);;所有文件 (*)",
        )
        if not path:
            return
        try:
            body = report_mod.build_report(
                env_rows=report_mod.report_env_rows(
                    net,
                    channel=self.combo_channel.currentText(),
                    src=self.edit_src.text().strip(),
                    dst=self.edit_dst.text().strip(),
                    module_flag=self.combo_module.currentData(),
                    timeout_ms=self.spin_timeout.value(),
                    retries=self.spin_retries.value(),
                    started=self._session_started,
                    finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tx=self._sent,
                    rx=max(0, self.raw_table.rowCount() - self._sent),
                ),
                summary=summary,
                extra_rows=[("命令参数存档", f"{self._params.param_count()} 条"),
                            ("判定口径", "确认即支持：01H/04H/05H/11H/12H（含福建 51H/54H/55H）与主动上报；"
                                        "必须同命令数据：02H/03H/10H/13H/14H/15H、52H/53H、F0H/F1H；"
                                        "否认按表 10：4/10 不支持，其余支持但报错")],
                interactions=self._interactions,
                uplink_rows=self._uplink_command_rows(),
                log_path=str(self._session_log.path()),
            )
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
        except Exception as exc:               # noqa: BLE001
            QMessageBox.warning(self, "报告生成失败", f"{type(exc).__name__}: {exc}")
            return
        self._log(f"[信息] 遍历测试报告已生成：{path}", "info")

    # ── 日志存储 ────────────────────────────────────────────────────────
    def _on_export_log(self) -> None:
        lines = self._session_log.lines()
        if not lines:
            QMessageBox.information(self, "提示", "本次会话还没有日志可导出")
            return
        path, _flt = QFileDialog.getSaveFileName(
            self, "导出日志",
            str(app_paths.data_path(f"国网协议测试日志_{datetime.now():%Y%m%d_%H%M%S}.txt")),
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if not path:
            return
        try:
            self._session_log.export(path)
        except Exception as exc:               # noqa: BLE001
            QMessageBox.warning(self, "导出失败", f"{type(exc).__name__}: {exc}")
            return
        self._log(f"[信息] 日志已导出（{len(lines)} 行）：{path}", "info")

    def _on_open_log_dir(self) -> None:
        directory = app_paths.data_path(store.LOG_DIR)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "打开失败", f"无法创建日志目录：{exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    # ── 组网参数 ────────────────────────────────────────────────────────
    def _collect_network(self) -> net_mod.NetworkConfig:
        """界面 → NetworkConfig（地址做 12 位归一，非法地址按未填处理）。"""
        net = net_mod.NetworkConfig()
        slaves: List[net_mod.SlaveNode] = []
        for item in self.node_widgets:
            slaves.append(net_mod.SlaveNode(
                addr=net_mod.normalize_addr(item["addr"].text()),
                proto=int(item["proto"].currentData() or 0),
                enabled=bool(item["use"].isChecked()),
            ))
        net.slaves = slaves
        net.cco_addr = net_mod.normalize_addr(self.edit_cco_addr.text())
        net.carrier_band = int(self.combo_carrier_band.currentData() or 0)
        net.radio_mod = int(self.combo_radio_mod.currentData() or 2)
        net.radio_channel = int(self.spin_radio_ch.value())
        net.radio_negotiate = 1 if self.check_radio_neg.isChecked() else 0
        net.auto_fill = bool(self.check_autofill.isChecked())
        net.fanout = bool(self.check_fanout.isChecked())
        return net

    def _apply_network_to_widgets(self, net: net_mod.NetworkConfig) -> None:
        widgets = (self.edit_cco_addr, self.combo_carrier_band, self.combo_radio_mod,
                   self.spin_radio_ch, self.check_radio_neg, self.check_autofill,
                   self.check_fanout,
                   *[item[key] for item in self.node_widgets
                     for key in ("addr", "proto", "use")])
        for w in widgets:
            w.blockSignals(True)
        try:
            for idx, item in enumerate(self.node_widgets):
                node = net.slaves[idx] if idx < len(net.slaves) else net_mod.SlaveNode()
                item["addr"].setText(node.addr)
                proto_idx = item["proto"].findData(int(node.proto))
                item["proto"].setCurrentIndex(max(0, proto_idx))
                item["use"].setChecked(bool(node.enabled))
            self.edit_cco_addr.setText(net.cco_addr)
            for combo, value in ((self.combo_carrier_band, net.carrier_band),
                                 (self.combo_radio_mod, net.radio_mod)):
                idx = combo.findData(int(value))
                combo.setCurrentIndex(max(0, idx))
            self.spin_radio_ch.setValue(int(net.radio_channel))
            self.check_radio_neg.setChecked(bool(net.radio_negotiate))
            self.check_autofill.setChecked(bool(net.auto_fill))
            self.check_fanout.setChecked(bool(net.fanout))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._refresh_network_hint()

    def _refresh_network_hint(self) -> None:
        net = self._collect_network()
        nodes = net.active_slaves()
        if not net.auto_fill:
            text = "自动填充已关闭：命令字段不会套用组网参数"
        elif not nodes:
            text = "尚未填写可用的从节点地址：单节点命令将不经展开、主要由手填参数决定"
        else:
            text = ("将按 " + "、".join(n.addr for n in nodes)
                    + f" 共 {len(nodes)} 个从节点组帧"
                    + ("（单节点命令按节点各发一帧）" if net.fanout else "（不展开）"))
        self.lbl_network_hint.setText(text)

    def _on_network_edited(self, *_args) -> None:
        self._net = self._collect_network()
        self._refresh_network_hint()
        self._refresh_join_label()     # 档案改了 ⇒ 入网分母跟着变
        self._refresh_preview()
        self._refresh_stats()      # 节点列表变了 ⇒ 统计的「命令×从节点」行数也跟着变
        self._schedule_save()

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
            "sections": collapsible_section.collect_state(self._sections),
            # 从节点模拟（虚拟表）串口：现场固定参数，随配置一起记住
            "sta_port": self.combo_sta_port.currentText().strip(),
            "sta_baud": self.combo_sta_baud.currentText().strip(),
            "sta_parity": self.combo_sta_parity.currentText().strip(),
            "sta_stop": self.combo_sta_stop.currentText().strip(),
        }

    def _schedule_save(self, *_args) -> None:
        if self._save_timer is not None:
            self._save_timer.start()

    def _save_persisted(self) -> None:
        try:
            atomic_write_json(self._config_path(), self._collect_settings())
        except Exception as exc:
            self._log(f"[警告] 保存配置失败：{exc}", "warn")
        self._params.set_network(self._collect_network().as_dict())
        if not self._params.save() and self._params.last_error:
            self._log(f"[警告] 保存命令参数失败：{self._params.last_error}", "warn")

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
        # 折叠区状态（坏数据由 apply_state 内部容错跳过，不会导致界面打不开）
        collapsible_section.apply_state(self._sections, merged.get("sections"))
        self._apply_sta_serial_settings(merged)
        self._page = merged["page"]
        # 组网参数：来自参数存档（commands/eb/stats/network 同文件），灌进控件
        self._net = net_mod.NetworkConfig.from_dict(self._params.get_network())
        self._apply_network_to_widgets(self._net)

    def _apply_sta_serial_settings(self, settings: Mapping[str, Any]) -> None:
        """恢复从节点模拟的串口参数（端口/波特率/校验/停止位）。

        端口可能当前没插上：`_refresh_sta_ports` 已把它补进下拉框，这里再兜一次，
        避免「换个 USB 口就丢掉配置」。
        """
        def _pick(combo: QComboBox, value: Any) -> None:
            text = str(value or "").strip()
            if not text:
                return
            combo.blockSignals(True)
            idx = combo.findText(text)
            if idx < 0:
                combo.addItem(text)
                idx = combo.count() - 1
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        _pick(self.combo_sta_baud, settings.get("sta_baud"))
        _pick(self.combo_sta_parity, settings.get("sta_parity"))
        _pick(self.combo_sta_stop, settings.get("sta_stop"))
        port = str(settings.get("sta_port") or "").strip()
        if port:
            _pick(self.combo_sta_port, port)

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
        self._flow_timer.stop()
        self._awaiting = False
        self._persist_current_params()
        self._save_persisted()
        self._session_log.close()
        # 本页内建的从节点模拟线程要回收，否则关窗后串口仍被占用
        if self._sta_sim is not None:
            try:
                self._sta_sim.stop()
                self._sta_sim.wait(1500)
            except Exception:
                pass
            self._sta_sim = None
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



def _row_int(rows: Dict[str, Any], name: str) -> Optional[int]:
    """从解析行字典里取整数值（原始值形如 `0x10` 或 `0x80 0x0C`）。"""
    row = rows.get(name)
    if not row:
        return None
    for value in (row[1], row[2]):
        text = str(value or "").strip()
        head = text.split(" ")[0]
        m = re.match(r"^0x([0-9A-Fa-f]{1,2})$", head)
        if m:
            return int(m.group(1), 16)
    return None


def _row_value(rows: Dict[str, Any], name: str) -> str:
    """取解析行的「解析值」（没有则原始值），去空白。"""
    row = rows.get(name)
    if not row:
        return ""
    return str(row[2] or row[1] or "").strip()


def _fn_from_dt_row(row: Tuple) -> Optional[int]:
    """DT 行 → Fn（解析值形如 `DT1=128, DT2=12`；取首个置位的 Fn）。"""
    text = str(row[2] or "")
    m = re.match(r"DT1=(\d+),\s*DT2=(\d+)", text)
    if not m:
        return None
    dt1, dt2 = int(m.group(1)), int(m.group(2))
    for bit in range(8):
        if dt1 & (1 << bit):
            return dt2 * 8 + bit + 1
    return None