# -*- coding: utf-8 -*-
"""645 协议测试页（仅协议 6 可见）—— 界面与串口，不含任何 645 字节细节。

与 698 版「协议测试」页（``dlt698_test_widget``）同构：

```
设备操作（表地址 / 读地址 / 写地址 / 广播校时 / 连接态 / 超时 / 循环 / 发送·停止）
├─ 左：公共参数（密码权限 PA / 密码 / 操作者代码 + 提示）
├─ 中：读数据(11H) / 写数据(14H) / 特殊命令 —— 筛选 + 分类树 + 当前项 + 帧预览
├─ 右：收发日志（整帧 + 逐字段明细 + 判定结论）
└─ 底：信息表（每条请求的结果）/ 报文表（双击 → 主窗口单帧解析）
```

字节层面的东西**全部**在 ``dlt645_test_core``（分类库 / 组帧 / 判定），本文件只做：
渲染控件、把控件值交给 core、把 core 的帧写到共享串口、把收到的帧交回 core 判定。

串口约定（与其它页一致）：**复用主窗口共享串口**，只订阅 ``raw_data_received`` /
``connection_changed`` / ``error_occurred``，经 ``write_raw`` 静默发送；``cleanup()``
只停自己的定时器与信号，**不关端口**（端口生命周期归主窗口）。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import app_paths
import channel_link as ch
import frame_deframe
import gui_utils
import wakeup_prefix

#: 落盘文件名（数据目录由 app_paths 决定；已 gitignore）
CONFIG_NAME = "dlt645_testbench.json"
#: 断帧策略（645：68+地址6+68+…+16，整帧 = L + 12；认前导 FEH）
DEFRAME_STRATEGY = "dlt645"
#: 三个分页（key, 标题）
PAGES = (("read", "读数据 (11H)"), ("write", "写数据 (14H)"), ("command", "特殊命令"))
#: 收发日志/帧预览的配色（深浅各一套；不在页面里写死白色）
LOG_PALETTES = {
    False: {"bg": "#FFFFFF", "fg": "#1F2328", "muted": "#57606A", "ok": "#0A7D28",
            "fail": "#B42318", "sys": "#0B5CAD"},
    True: {"bg": "#1E1E1E", "fg": "#D4D4D4", "muted": "#9DA0A4", "ok": "#66BB6A",
           "fail": "#EF5350", "sys": "#64B5F6"},
}
#: 单页最多保留的日志块（超出由 Qt 自动滚动丢弃最旧）
LOG_MAX_BLOCKS = 2000


def _core():
    """惰性 import 逻辑层（保持页面启动轻量）。"""
    import dlt645_test_core

    return dlt645_test_core


class Dlt645TestWidget(QWidget):
    """DL/T 645-2007 协议测试页。"""

    #: 双击报文表 → 主窗口「单帧解析」页（与监控器/698 测试页同一注入点）
    frame_to_single_parse = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._config_path = str(app_paths.data_path(CONFIG_NAME))
        self._dark = False
        self._palette = LOG_PALETTES[False]

        self._serial_worker = None
        self._bt_provider = None
        self._rx_buf = bytearray()
        self._pages: Dict[str, dict] = {}
        self._queue: List[dict] = []
        self._current: Optional[dict] = None
        self._awaiting = False
        self._stopped = True
        self._seq = 0
        self._tx_count = 0
        self._rx_count = 0
        self._last_values: Dict[str, str] = {}

        self._reply_timer = QTimer(self)
        self._reply_timer.setSingleShot(True)
        self._reply_timer.timeout.connect(self._on_reply_timeout)
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._send_next)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_config)

        # 发送通道（串口 / 蓝牙）：控制器只负责收发与状态，分帧/判定仍在本页
        self._channel = ch.ChannelController(self)
        self._channel.rx.connect(self._on_rx_data)
        self._channel.state_changed.connect(self._on_channel_state)
        self._channel.channel_changed.connect(self._on_channel_switched)
        self._channel.error.connect(lambda msg: self._log(f"[失败] {msg}", "fail"))

        self._build_ui()
        self._load_persisted()

    # ══════════════════════════════════════════════════════════════════ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)
        root.addWidget(self._build_top_bar())

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_left_panel())
        split.addWidget(self._build_center())
        split.addWidget(self._build_log_panel())
        split.setSizes([210, 720, 420])
        self._split = split
        root.addWidget(split, 1)
        root.addWidget(self._build_bottom())

        gui_utils.apply_chinese_context_menus(self)

    # ── 顶部：设备操作 ────────────────────────────────────────────────
    def _build_top_bar(self) -> QWidget:
        box = QGroupBox("设备操作")
        grid = QGridLayout(box)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)

        # 行 0：地址读写 + 校时
        grid.addWidget(QLabel("表地址："), 0, 0)
        self.edit_addr = QLineEdit("000000000000")
        self.edit_addr.setMaxLength(12)
        self.edit_addr.setPlaceholderText("12 位十六进制（书写序）")
        self.edit_addr.setToolTip("DL/T645 表地址：12 位十六进制（高位在前书写），线上低字节在前")
        self.edit_addr.textChanged.connect(self._on_params_changed)
        grid.addWidget(self.edit_addr, 0, 1)

        self.btn_read_addr = QPushButton("读地址")
        gui_utils.set_btn(self.btn_read_addr, "secondary")
        gui_utils.set_btn_icon(self.btn_read_addr, "copy")
        self.btn_read_addr.setToolTip("发 13H（地址域 AA×6）读取表地址，收到 93H 应答自动回填")
        self.btn_read_addr.clicked.connect(self._on_read_address)
        grid.addWidget(self.btn_read_addr, 0, 2)

        grid.addWidget(QLabel("写入地址："), 0, 3)
        self.edit_write_addr = QLineEdit("")
        self.edit_write_addr.setMaxLength(12)
        self.edit_write_addr.setPlaceholderText("要写入的新地址（12 位）")
        grid.addWidget(self.edit_write_addr, 0, 4)

        self.btn_write_addr = QPushButton("写入地址")
        gui_utils.set_btn(self.btn_write_addr, "warning")
        self.btn_write_addr.setToolTip("发 15H（地址域 AA×6）把新地址写入表计；需编程键")
        self.btn_write_addr.clicked.connect(self._on_write_address)
        grid.addWidget(self.btn_write_addr, 0, 5)

        self.btn_broadcast_time = QPushButton("广播校时")
        gui_utils.set_btn(self.btn_broadcast_time, "secondary")
        self.btn_broadcast_time.setToolTip("发 08H（地址域 99×6），数据域为本机当前时间；无应答")
        self.btn_broadcast_time.clicked.connect(self._on_broadcast_time)
        grid.addWidget(self.btn_broadcast_time, 0, 6)

        # 行 1：发送通道（串口 / 蓝牙）+ 通道状态
        grid.addWidget(QLabel("发送通道："), 1, 0)
        self.combo_channel = QComboBox()
        for label, key in ch.CHANNELS:
            self.combo_channel.addItem(label, key)
        self.combo_channel.setToolTip(
            "串口 = 顶部「串口配置」的共享连接；蓝牙 = 「蓝牙工具」页已建立的连接"
            "（协议帧整帧一次 ATT 写，超过一次写上限会明确报错）")
        self.combo_channel.currentIndexChanged.connect(self._on_channel_combo_changed)
        grid.addWidget(self.combo_channel, 1, 1)
        self.lbl_state = QLabel("")
        self.lbl_state.setWordWrap(True)
        grid.addWidget(self.lbl_state, 1, 2, 1, 6)

        # 行 2：超时 / 循环 / 发送控制
        grid.addWidget(QLabel("读取超时(ms)："), 2, 0)
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(300, 60000)
        self.spin_timeout.setSingleStep(100)
        self.spin_timeout.setValue(3000)
        self.spin_timeout.setToolTip("发出请求后等待应答的时间；超时记「超时」并继续下一条")
        grid.addWidget(self.spin_timeout, 2, 1)

        self.chk_loop = QCheckBox("循环发送")
        self.chk_loop.setToolTip("一轮队列发完后从头再来，直到点「停止」")
        grid.addWidget(self.chk_loop, 2, 2)

        self.btn_send = QPushButton("发送")
        gui_utils.set_btn(self.btn_send, "primary")
        gui_utils.set_btn_icon(self.btn_send, "play")
        self.btn_send.setToolTip("发送当前勾选的叶子（一个都没勾 = 当前选中项）")
        self.btn_send.clicked.connect(self._on_send)
        grid.addWidget(self.btn_send, 2, 3)

        self.btn_stop = QPushButton("停止")
        gui_utils.set_btn(self.btn_stop, "danger")
        self.btn_stop.setIcon(self.style().standardIcon(
            self.style().StandardPixmap.SP_MediaStop))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        grid.addWidget(self.btn_stop, 2, 4)

        self.lbl_count = QLabel("TX 0 / RX 0")
        self.lbl_count.setStyleSheet("color: #57606A;")
        grid.addWidget(self.lbl_count, 2, 5)
        grid.setColumnStretch(6, 1)

        gui_utils.fit_btn_width(
            self.btn_read_addr, self.btn_write_addr, self.btn_broadcast_time,
            self.btn_send, self.btn_stop,
        )
        return box

    # ── 左栏：公共参数 ────────────────────────────────────────────────
    def _build_left_panel(self) -> QWidget:
        panel = QGroupBox("公共参数")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        form = QFormLayout()
        form.setSpacing(4)
        self.edit_pa = QLineEdit("02")
        self.edit_pa.setMaxLength(2)
        self.edit_pa.setToolTip("密码权限 PA：00 最高权限 / 02 清零级 / 04 写数据级（hex）")
        form.addRow("密码权限 PA：", self.edit_pa)
        self.edit_pwd = QLineEdit("000000")
        self.edit_pwd.setMaxLength(6)
        self.edit_pwd.setToolTip("密码 P0P1P2（3 字节 hex），出厂默认 000000")
        form.addRow("密码 P0P1P2：", self.edit_pwd)
        self.edit_operator = QLineEdit("00000000")
        self.edit_operator.setMaxLength(8)
        self.edit_operator.setToolTip("操作者代码 C0~C3（4 字节 hex），记录操作人员信息")
        form.addRow("操作者代码：", self.edit_operator)
        lay.addLayout(form)

        hint = QLabel(
            "写数据 / 清零 / 改密码类命令需要**编程键**与对应权限；\n"
            "读数据只填表地址即可。\n"
            "「读地址」用 AA×6 广播地址，只支持点对点。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #57606A; font-size: 12px;")
        lay.addWidget(hint)
        lay.addStretch()

        for edit in (self.edit_pa, self.edit_pwd, self.edit_operator):
            edit.textChanged.connect(self._on_params_changed)
        return panel

    # ── 中栏：三个分页 ────────────────────────────────────────────────
    def _build_center(self) -> QWidget:
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        for index, (_key, title) in enumerate(PAGES):
            page = QWidget()
            page.setLayout(QVBoxLayout())
            page.layout().setContentsMargins(2, 2, 2, 2)
            page.layout().setSpacing(4)
            self.tabs.addTab(page, title)
            if index == 0:
                self._ensure_page(PAGES[0][0])
        return self.tabs

    def _ensure_page(self, key: str) -> dict:
        """惰性构建某页：筛选 + 分类树 + 当前项 + 帧预览。"""
        if key in self._pages:
            return self._pages[key]
        index = [k for k, _t in PAGES].index(key)
        host = self.tabs.widget(index)
        lay = host.layout()

        row = QHBoxLayout()
        row.addWidget(QLabel("筛选："))
        edit_filter = QLineEdit()
        edit_filter.setPlaceholderText("DI / 名称 / 命令名（留空显示全部）")
        edit_filter.textChanged.connect(lambda text, k=key: self._apply_filter(k, text))
        row.addWidget(edit_filter, 1)
        btn_uncheck = QPushButton("全部不勾")
        gui_utils.set_btn(btn_uncheck, "secondary", "sm")
        btn_uncheck.clicked.connect(lambda _c=False, k=key: self._set_all_checked(k, False))
        row.addWidget(btn_uncheck)
        lay.addLayout(row)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setColumnCount(1)
        # 最小高度：窗口压到 1000×700 时树仍要能看到 6~7 行（实测不给下限只剩 ~98px）
        tree.setMinimumHeight(160)
        tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        tree.itemSelectionChanged.connect(lambda k=key: self._on_selection(k))
        lay.addWidget(tree, 1)

        detail = QGroupBox("当前项")
        detail_lay = QVBoxLayout(detail)
        detail_lay.setContentsMargins(6, 4, 6, 4)
        detail_lay.setSpacing(3)
        lay.addWidget(detail)

        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("帧预览："))
        edit_preview = QLineEdit()
        edit_preview.setReadOnly(True)
        edit_preview.setFont(QFont("Consolas", 9))
        preview_row.addWidget(edit_preview, 1)
        lay.addLayout(preview_row)

        state = {
            "built": True,
            "tree": tree,
            "filter": edit_filter,
            "detail": detail,
            "detail_layout": detail_lay,
            "detail_host": None,
            "preview": edit_preview,
            "fields": {},
            "warn": None,
            "value_label": None,
        }
        self._pages[key] = state
        self._build_tree(key)
        return state

    def _build_tree(self, key: str) -> None:
        """建立分类树：读/写页 = DI 大类 → 子类 → DI；特殊命令页 = 命令分组 → 命令。"""
        core = _core()
        state = self._pages[key]
        tree = state["tree"]
        tree.clear()
        if key in ("read", "write"):
            for cat in core.catalog():
                cat_item = QTreeWidgetItem([f"{cat.name}（{cat.item_count}）"])
                cat_item.setFlags(Qt.ItemIsEnabled)
                for sub in cat.subgroups:
                    sub_item = QTreeWidgetItem([f"{sub.name}（{len(sub.items)}）"])
                    sub_item.setFlags(Qt.ItemIsEnabled)
                    for item in sub.items:
                        text = f"{item.di}  {item.name}"
                        leaf = QTreeWidgetItem([text])
                        leaf.setData(0, Qt.UserRole, {"kind": "di", "di": item.di})
                        leaf.setFlags(leaf.flags() | Qt.ItemIsUserCheckable)
                        leaf.setCheckState(0, Qt.Unchecked)
                        leaf.setToolTip(0, self._di_tooltip(item))
                        sub_item.addChild(leaf)
                    cat_item.addChild(sub_item)
                tree.addTopLevelItem(cat_item)
        else:
            for group in core.command_groups():
                group_item = QTreeWidgetItem([group.name])
                group_item.setFlags(Qt.ItemIsEnabled)
                for cmd in group.commands:
                    leaf = QTreeWidgetItem([f"0x{cmd.func:02X}H  {cmd.name}"])
                    leaf.setData(0, Qt.UserRole, {"kind": "cmd", "func": cmd.func})
                    leaf.setFlags(leaf.flags() | Qt.ItemIsUserCheckable)
                    leaf.setCheckState(0, Qt.Unchecked)
                    leaf.setToolTip(0, cmd.hint or cmd.name)
                    group_item.addChild(leaf)
                tree.addTopLevelItem(group_item)
        tree.expandAll()

    @staticmethod
    def _di_tooltip(item) -> str:
        unit = f" · 单位 {item.unit}" if item.unit else ""
        length = f"{item.length} 字节" if item.length else "不定长"
        extra = " · 光伏扩展" if item.pv else ""
        return f"DI {item.di} {item.name}\n格式 {item.data_type or '未声明'} · {length}{unit}{extra}"

    # ── 右栏：收发日志 ────────────────────────────────────────────────
    def _build_log_panel(self) -> QWidget:
        box = QGroupBox("收发日志")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(6, 6, 6, 6)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setMaximumBlockCount(LOG_MAX_BLOCKS)
        self.log_view.setMinimumHeight(120)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        lay.addWidget(self.log_view)
        self._apply_theme_style(False)
        return box

    # ── 底部：信息表 / 报文表 ─────────────────────────────────────────
    def _build_bottom(self) -> QWidget:
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.setMaximumHeight(180)

        self.table_info = QTableWidget(0, 6)
        self.table_info.setHorizontalHeaderLabels(
            ["#", "时间", "动作", "DI / 命令", "结果", "摘要"])
        self.table_info.verticalHeader().setVisible(False)
        self.table_info.setEditTriggers(QTableWidget.NoEditTriggers)
        head = self.table_info.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(5, QHeaderView.Stretch)
        self.bottom_tabs.addTab(self.table_info, "信息表")

        self.table_raw = QTableWidget(0, 4)
        self.table_raw.setHorizontalHeaderLabels(["时间", "方向", "长度", "帧"])
        self.table_raw.verticalHeader().setVisible(False)
        self.table_raw.setEditTriggers(QTableWidget.NoEditTriggers)
        raw_head = self.table_raw.horizontalHeader()
        raw_head.setSectionResizeMode(QHeaderView.ResizeToContents)
        raw_head.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_raw.cellDoubleClicked.connect(self._on_raw_row_activated)
        self.bottom_tabs.addTab(self.table_raw, "报文表")
        return self.bottom_tabs

    # ═══════════════════════════════════════════════════════════════ 状态
    def _addr(self) -> str:
        return self.edit_addr.text().strip()

    def _common_params(self) -> Dict[str, str]:
        return {
            "密码权限 PA": self.edit_pa.text().strip() or "00",
            "密码 P0P1P2": self.edit_pwd.text().strip() or "000000",
            "操作者代码 C0~C3": self.edit_operator.text().strip() or "00000000",
        }

    def _active_key(self) -> str:
        index = self.tabs.currentIndex()
        return PAGES[index][0] if 0 <= index < len(PAGES) else PAGES[0][0]

    def _leaf_of(self, node: Optional[QTreeWidgetItem]) -> Optional[dict]:
        if node is None:
            return None
        raw = node.data(0, Qt.UserRole)
        if isinstance(raw, dict):
            return raw
        return None

    def _current_leaf(self, key: str) -> Optional[dict]:
        state = self._pages.get(key)
        if not state:
            return None
        return self._leaf_of(state["tree"].currentItem())

    def _iter_leaves(self, item: QTreeWidgetItem):
        """递归遍历树里的叶子（带 UserRole 字典的节点）。"""
        if isinstance(item.data(0, Qt.UserRole), dict):
            yield item
            return
        for i in range(item.childCount()):
            yield from self._iter_leaves(item.child(i))

    def _checked_leaves(self, key: str) -> List[dict]:
        state = self._pages.get(key)
        out: List[dict] = []
        if not state:
            return out
        tree = state["tree"]
        for i in range(tree.topLevelItemCount()):
            for leaf in self._iter_leaves(tree.topLevelItem(i)):
                if leaf.checkState(0) == Qt.Checked:
                    info = self._leaf_of(leaf)
                    if info:
                        out.append(info)
        return out

    def _set_all_checked(self, key: str, checked: bool) -> None:
        state = self._pages.get(key)
        if not state:
            return
        tree = state["tree"]
        state_ = Qt.Checked if checked else Qt.Unchecked
        for i in range(tree.topLevelItemCount()):
            for leaf in self._iter_leaves(tree.topLevelItem(i)):
                leaf.setCheckState(0, state_)

    # ═══════════════════════════════════════════════════ 当前项 / 预览
    def _on_selection(self, key: str) -> None:
        info = self._current_leaf(key)
        if info is None:
            return
        if key == "read":
            self._show_read_detail(info["di"])
        elif key == "write":
            self._show_write_detail(info["di"])
        else:
            self._show_command_detail(int(info["func"]))
        self._refresh_preview(key)

    def _swap_detail_host(self, key: str, host: QWidget) -> None:
        state = self._pages[key]
        old = state.get("detail_host")
        if old is not None:
            state["detail_layout"].removeWidget(old)
            old.setParent(None)
            old.deleteLater()
        state["detail_layout"].addWidget(host)
        state["detail_host"] = host

    def _show_read_detail(self, di: str) -> None:
        core = _core()
        state = self._pages["read"]
        item = core.find_di(di)
        host = QWidget()
        form = QFormLayout(host)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(2)
        name = item.name if item else "（不在 DI 表）"
        form.addRow("数据标识：", QLabel(f"{di}  {name}"))
        if item:
            form.addRow("格式 / 长度：",
                        QLabel(f"{item.data_type or '未声明'} · "
                               f"{str(item.length) + ' 字节' if item.length else '不定长'}"))
            form.addRow("单位：", QLabel(item.unit or "—"))
        self._last_values.setdefault(di, "")
        value_label = QLabel(self._last_values.get(di) or "（尚未读到）")
        value_label.setWordWrap(True)
        form.addRow("最近读数：", value_label)
        state["value_label"] = value_label
        self._swap_detail_host("read", host)

    def _show_write_detail(self, di: str) -> None:
        core = _core()
        state = self._pages["write"]
        state["fields"] = {}
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        item = core.find_di(di)
        head = QLabel(f"{di}  {item.name if item else '（不在 DI 表）'}")
        head.setStyleSheet("font-weight: bold;")
        lay.addWidget(head)
        form = QFormLayout()
        form.setSpacing(2)
        for spec in core.write_fields(di):
            edit = QLineEdit(str(spec.get("default") or ""))
            edit.setPlaceholderText(str(spec.get("hint") or ""))
            edit.setToolTip(str(spec.get("hint") or ""))
            edit.textChanged.connect(
                lambda _t="", k="write": self._refresh_preview(k))
            self._pages["write"]["fields"][str(spec.get("name")).rstrip("：:")] = edit
            form.addRow(f"{spec.get('name')}：", edit)
        if form.rowCount():
            lay.addLayout(form)
        else:
            lay.addWidget(QLabel("该 DI 无数据域（读请求只发 DI）"))
        warn = QLabel("")
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #B26A00;")
        lay.addWidget(warn)
        state["warn"] = warn
        self._swap_detail_host("write", host)

    def _show_command_detail(self, func: int) -> None:
        core = _core()
        state = self._pages["command"]
        state["fields"] = {}
        cmd = core.find_command(func)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        head = QLabel(f"0x{func:02X}H  {cmd.name if cmd else ''}")
        head.setStyleSheet("font-weight: bold;")
        lay.addWidget(head)
        if cmd and cmd.hint:
            hint = QLabel(cmd.hint)
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #57606A; font-size: 12px;")
            lay.addWidget(hint)
        if cmd and cmd.addr_is_fixed:
            note = QLabel(f"地址域固定为 {cmd.addr_default}（协议规定，忽略上面的表地址）")
            note.setWordWrap(True)
            note.setStyleSheet("color: #B26A00; font-size: 12px;")
            lay.addWidget(note)
        form = QFormLayout()
        form.setSpacing(2)
        for spec in (cmd.fields if cmd else ()):
            if str(spec.get("type")) == "di":
                # 带 DI 的特殊命令（12H 读后续 / 18H 改密码等）：DI 也必须可填。
                # 默认取「读数据」页当前选中的 DI，减少手抄。
                edit = QLineEdit(self._default_di())
                edit.setPlaceholderText("8 位数据标识 DI，如 00010000")
                edit.setToolTip("该命令的数据域以 DI 开头；默认取读数据页当前选中的 DI")
                edit.textChanged.connect(
                    lambda _t="", k="command": self._refresh_preview(k))
                state["fields"]["数据标识 DI"] = edit
                form.addRow("数据标识 DI：", edit)
                continue
            edit = QLineEdit(str(spec.get("default") or ""))
            edit.setPlaceholderText(str(spec.get("hint") or ""))
            edit.setToolTip(str(spec.get("hint") or ""))
            edit.textChanged.connect(
                lambda _t="", k="command": self._refresh_preview(k))
            state["fields"][str(spec.get("name")).rstrip("：:")] = edit
            form.addRow(f"{spec.get('name')}：", edit)
        lay.addLayout(form)
        self._swap_detail_host("command", host)

    def _default_di(self) -> str:
        leaf = self._current_leaf("read")
        return str(leaf.get("di") or "") if leaf else ""

    def _field_values(self, key: str) -> Dict[str, str]:
        state = self._pages.get(key) or {}
        return {name: edit.text().strip()
                for name, edit in (state.get("fields") or {}).items()}

    def _build_preview(self, key: str) -> tuple:
        """当前选中项 → ``(帧字节, 错误)``（错误非空 = 不能发）。"""
        core = _core()
        leaf = self._current_leaf(key)
        if leaf is None:
            return b"", "请先在左侧树里选择一条命令"
        try:
            if key == "read":
                return core.build_read(leaf["di"], self._addr()), ""
            if key == "write":
                fv = dict(self._field_values("write"))
                fv.update(self._common_params())
                return core.build_write(leaf["di"], fv, self._addr()), ""
            return core.build_command(int(leaf["func"]),
                                      self._field_values("command"),
                                      self._addr()), ""
        except Exception as exc:                   # noqa: BLE001 —— 组帧失败给可读提示
            return b"", str(exc)

    def _refresh_preview(self, key: str) -> None:
        if key not in self._pages:
            return
        state = self._pages[key]
        frame, error = self._build_preview(key)
        if error:
            state["preview"].setText(f"⚠ {error}")
        else:
            state["preview"].setText(_core().format_hex(frame))
        if key == "write" and state.get("warn") is not None:
            leaf = self._current_leaf("write")
            warn = ""
            if leaf:
                try:
                    fv = dict(self._field_values("write"))
                    fv.update(self._common_params())
                    warn = _core().length_warning(leaf["di"], fv)
                except Exception:              # noqa: BLE001
                    warn = ""
            state["warn"].setText(warn)

    def _on_params_changed(self, *_args) -> None:
        # 表地址 / 公共参数可能被**任何**页的预览用到（读数据页也用表地址），
        # 所以刷新「当前页 + 已建出来的其它页」，别只刷写数据/特殊命令。
        current = self._active_key()
        for key in {current, *self._pages.keys()}:
            if key in self._pages:
                self._refresh_preview(key)
        self._schedule_save()

    def _on_tab_changed(self, index: int) -> None:
        if not (0 <= index < len(PAGES)):
            return
        key = PAGES[index][0]
        self._ensure_page(key)
        self._refresh_preview(key)
        self._schedule_save()

    def _apply_filter(self, key: str, text: str) -> None:
        state = self._pages.get(key)
        if not state:
            return
        kw = str(text or "").strip().lower()
        tree = state["tree"]
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            top_visible = 0
            for j in range(top.childCount()):
                child = top.child(j)
                visible = 0
                for k in range(child.childCount()):
                    leaf = child.child(k)
                    hit = (not kw or kw in leaf.text(0).lower()
                           or kw in str(leaf.toolTip(0)).lower())
                    leaf.setHidden(not hit)
                    visible += 1 if hit else 0
                child.setHidden(visible == 0)
                top_visible += visible
            top.setHidden(top_visible == 0 and bool(kw))
            if kw and top_visible:
                top.setExpanded(True)

    # ═════════════════════════════════════════════════════════════ 发送
    def _on_send(self) -> None:
        ok, reason = self._channel.ready()
        if not ok:
            QMessageBox.information(self, "发送通道未就绪", reason)
            return
        try:
            queue = self._build_queue()
        except Exception as exc:                   # noqa: BLE001
            QMessageBox.warning(self, "无法组帧", str(exc))
            return
        if not queue:
            QMessageBox.information(self, "没有可发送的命令",
                                    "请在树里勾选叶子，或先选中一条。")
            return
        # 先清掉上一轮遗留的「下一条/超时」定时器，避免它们把新一轮的队列提前消费
        self._reply_timer.stop()
        self._next_timer.stop()
        self._awaiting = False
        self._current = None
        self._queue = queue
        self._stopped = False
        self._set_running(True)
        self._log(f"[系统] 开始发送 {len(queue)} 条命令", "sys")
        self._send_next()

    def _build_queue(self) -> List[dict]:
        core = _core()
        key = self._active_key()
        leaves = self._checked_leaves(key) or [self._current_leaf(key)]
        leaves = [leaf for leaf in leaves if leaf]
        entries: List[dict] = []
        if key == "command":
            # 特殊命令的字段随命令变化，多选没有意义 ⇒ 只发当前这一条
            leaves = leaves[:1]
        for leaf in leaves:
            if key == "read":
                di = leaf["di"]
                entries.append({
                    "label": f"读数据 {di}",
                    "ident": di,
                    "frame": core.build_read(di, self._addr()),
                    "expect": {"func": 0x11, "di": di, "kind": "read"},
                })
            elif key == "write":
                di = leaf["di"]
                fv = dict(self._field_values("write"))
                fv.update(self._common_params())
                entries.append({
                    "label": f"写数据 {di}",
                    "ident": di,
                    "frame": core.build_write(di, fv, self._addr()),
                    "expect": {"func": 0x14, "di": di, "kind": "write"},
                })
            else:
                func = int(leaf["func"])
                cmd = core.find_command(func)
                kind = "address" if func == 0x13 else "command"
                entries.append({
                    "label": f"{cmd.name if cmd else leaf['func']}",
                    "ident": f"0x{func:02X}H",
                    "frame": core.build_command(func, self._field_values("command"),
                                                self._addr()),
                    "expect": {"func": func, "kind": kind,
                               "no_reply": func == 0x08},
                })
        return entries

    def _send_next(self) -> None:
        if self._stopped or self._awaiting:
            # `_awaiting` 守卫：上一轮遗留的 `_next_timer` 可能在「已发出、等应答」期间
            # 触发，若放行会把队列里的下一条提前发出去（响应配对全错）。
            return
        if not self._queue:
            if self.chk_loop.isChecked():
                self._queue = self._build_queue()
                if self._queue:
                    self._log("[系统] 循环发送：开始新一轮", "sys")
                    self._next_timer.start(10)
                    return
            self._finish_run()
            return
        entry = self._queue.pop(0)
        sent, reason = self._channel.send(entry["frame"])
        if not sent:
            # 单帧发不出去（如蓝牙一次写上限超限）：记一条失败并继续下一条，
            # **不静默、不中止整批**（现场更常见的是某几条超长、其余能发）。
            # `row` 要在 `_record_result` 之前存在，保持与成功路径同一行号语义。
            entry["row"] = self._add_info_row(entry["label"], entry["ident"], "失败")
            self._record_result(entry, {
                "status": _core().RESULT_FAIL, "summary": reason, "lines": [],
                "address": "", "di": "", "value_text": "",
            })
            self._log(f"[失败] {entry['label']}：{reason}", "fail")
            self._next_timer.start(10)
            return
        self._seq += 1
        self._tx_count += 1
        self._update_txrx()
        self._current = entry
        self._add_raw_row("TX", entry["frame"])
        self._log(f"[{self._time()}] [TX] {entry['label']}  {_core().format_hex(entry['frame'])}")
        for line in _core().detail_lines(entry["frame"], title="发送帧结构"):
            self._log("  " + line.lstrip())
        entry["row"] = self._add_info_row(entry["label"], entry["ident"], "已发送")
        if entry["expect"].get("no_reply"):
            self._record_result(entry, _core().evaluate_response(b"", entry["expect"]))
            self._current = None
            self._next_timer.start(10)
            return
        self._awaiting = True
        self._reply_timer.start(int(self.spin_timeout.value()))

    def _finish_run(self) -> None:
        if self._current is not None:
            self._current = None
        self._awaiting = False
        self._queue = []
        self._stopped = True
        self._set_running(False)
        self._log("[系统] 发送结束", "sys")

    def _on_stop(self) -> None:
        self._reply_timer.stop()
        self._next_timer.stop()
        if self._current is not None:
            self._record_result(self._current, {
                "status": _core().RESULT_FAIL, "summary": "用户停止", "lines": [],
                "address": "", "di": "", "value_text": "",
            })
        self._finish_run()

    def _set_running(self, running: bool) -> None:
        self.btn_send.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.chk_loop.setEnabled(not running)

    def _on_reply_timeout(self) -> None:
        if not self._awaiting or self._current is None:
            return
        entry = self._current
        self._awaiting = False
        self._record_result(entry, {
            "status": _core().RESULT_TIMEOUT,
            "summary": f"{int(self.spin_timeout.value())} ms 内未收到应答",
            "lines": [], "address": "", "di": "", "value_text": "",
        })
        self._log(f"[{self._time()}] [超时] {entry['label']}：未收到应答", "fail")
        self._current = None
        self._next_timer.start(10)

    # ═══════════════════════════════════════════════════════════ 接收
    def _on_rx_data(self, data: bytes) -> None:
        """当前通道收到的字节（控制器已按通道过滤）；分帧仍在本页。"""
        if not data:
            return
        self._rx_buf.extend(data)
        while True:
            need = frame_deframe.frame_length_for(DEFRAME_STRATEGY, self._rx_buf)
            if need and len(self._rx_buf) >= need and self._rx_buf[need - 1] == 0x16:
                frame = bytes(self._rx_buf[:need])
                del self._rx_buf[:need]
                self._on_frame(frame)
                continue
            if frame_deframe.frame_incomplete(DEFRAME_STRATEGY, self._rx_buf):
                return
            # 切不出帧且没有半帧在等 → 丢掉不可能成为帧头的字节（噪声重同步）
            skip = self._resync_junk()
            if not skip:
                return

    # 旧名别名：外部/测试可能按串口时代的名字调用（行为不变）
    _on_serial_raw_data = _on_rx_data

    def _resync_junk(self) -> int:
        """丢掉确定不可能是帧起点的字节（返回丢掉的字节数）。

        645 帧只以 `68H` 开头，帧前允许连续 `FEH` 唤醒前导（DL/T645-2007 §5.3.1）：
        - 前导后面是 `68H` → 合法前导，**不丢**，交给 `frame_length_for`；
        - 前导后面不是 `68H` → 前导不成立，丢掉这段 FE（否则缓冲头会永久卡住，
          现场一次线噪就让后面所有应答都收不到 —— 与升级页同一判据）。
        """
        buf = self._rx_buf
        if not buf:
            return 0
        fe = wakeup_prefix.wakeup_prefix_len(buf)
        if fe:
            if len(buf) == fe:
                return 0                        # 只有前导：等更多字节
            if buf[fe] == 0x68:
                return 0                        # 合法前导
            del buf[:fe]
            return fe
        if buf[0] == 0x68:
            return 0
        for index, byte in enumerate(buf):
            if byte in (0x68, 0xFE):
                if index:
                    del buf[:index]
                return index
        # 整段都没有可能的帧头：全部丢弃
        count = len(buf)
        del buf[:count]
        return count

    def _on_frame(self, frame: bytes) -> None:
        core = _core()
        self._rx_count += 1
        self._update_txrx()
        self._add_raw_row("RX", frame)
        self._log(f"[{self._time()}] [RX] {core.format_hex(frame)}")
        for line in core.detail_lines(frame, title="接收帧结构"):
            self._log("  " + line.lstrip())
        if not self._awaiting or self._current is None:
            self._log("[系统] 未请求的应答（已记录，不参与本次判定）", "sys")
            return
        entry = self._current
        self._awaiting = False
        self._reply_timer.stop()
        result = core.evaluate_response(frame, entry["expect"])
        self._record_result(entry, result)
        if result.get("status") == core.RESULT_OK and result.get("address"):
            self._apply_read_address(str(result["address"]))
        self._current = None
        self._next_timer.start(10)

    def _apply_read_address(self, address: str) -> None:
        """读地址成功 → 回填表地址（12 位书写序）。"""
        text = str(address or "").strip().upper()
        if len(text) == 12:
            self.edit_addr.setText(text)
            self._log(f"[系统] 已回填表地址：{text}", "sys")

    # ═══════════════════════════════════════════════════════ 固定动作
    def _on_read_address(self) -> None:
        try:
            frame = _core().quick_read_address()
        except Exception as exc:                   # noqa: BLE001
            QMessageBox.warning(self, "无法组帧", str(exc))
            return
        self._run_single(frame, "读通信地址", {"func": 0x13, "kind": "address"})

    def _on_write_address(self) -> None:
        text = self.edit_write_addr.text().strip()
        if not text:
            QMessageBox.information(self, "缺少参数", "请先填「写入地址」（12 位十六进制）。")
            return
        try:
            frame = _core().quick_write_address(text)
        except Exception as exc:                   # noqa: BLE001
            QMessageBox.warning(self, "无法组帧", str(exc))
            return
        self._run_single(frame, f"写通信地址 {text}", {"func": 0x15, "kind": "command"})

    def _on_broadcast_time(self) -> None:
        try:
            frame = _core().build_broadcast_time(datetime.now())
        except Exception as exc:                   # noqa: BLE001
            QMessageBox.warning(self, "无法组帧", str(exc))
            return
        self._run_single(frame, "广播校时", {"func": 0x08, "kind": "command",
                                            "no_reply": True})

    def _run_single(self, frame: bytes, label: str, expect: dict) -> None:
        """把一个固定动作塞进队列（与「发送」同一套状态机）。"""
        ok, reason = self._channel.ready()
        if not ok:
            QMessageBox.information(self, "发送通道未就绪", reason)
            return
        if self._queue or self._awaiting:
            QMessageBox.information(self, "正在发送",
                                    "上一批命令还没发完，请先等待或点「停止」。")
            return
        self._queue = [{"label": label, "ident": label, "frame": frame,
                        "expect": dict(expect)}]
        self._stopped = False
        self._set_running(True)
        self._send_next()

    # ═════════════════════════════════════════════════════ 结果/日志
    def _record_result(self, entry: dict, result: dict) -> None:
        status = str(result.get("status") or "")
        summary = str(result.get("summary") or "")
        tone = "ok" if status in (_core().RESULT_OK, _core().RESULT_NO_REPLY) else "fail"
        self._update_info_row(int(entry.get("row", -1)), status, summary)
        if entry.get("expect", {}).get("kind") == "read" and _core().RESULT_OK == status:
            di = str(result.get("di") or entry.get("ident") or "")
            value = str(result.get("value_text") or "")
            if di:
                self._last_values[di] = value
                state = self._pages.get("read")
                if state and self._current_leaf("read") == {"kind": "di", "di": di}:
                    label = state.get("value_label")
                    if label is not None:
                        label.setText(value or "（应答无数据值）")
        self._log(f"[判定] {status}：{summary}", tone)

    def _log(self, text: str, tone: str = "") -> None:
        color = {"ok": self._palette["ok"], "fail": self._palette["fail"],
                 "sys": self._palette["sys"]}.get(tone)
        if color:
            self.log_view.appendHtml(
                f'<span style="color:{color};">{_html_escape(text)}</span>')
        else:
            self.log_view.appendPlainText(text)

    def _add_info_row(self, action: str, ident: str, status: str) -> int:
        row = self.table_info.rowCount()
        self.table_info.insertRow(row)
        values = [str(row + 1), self._time(with_date=False), action, ident, status, ""]
        for col, text in enumerate(values):
            self.table_info.setItem(row, col, QTableWidgetItem(text))
        self.table_info.scrollToBottom()
        return row

    def _update_info_row(self, row: int, status: str, summary: str) -> None:
        if row < 0 or row >= self.table_info.rowCount():
            return
        ok = status in (_core().RESULT_OK, _core().RESULT_NO_REPLY)
        for col, text in ((4, status), (5, summary)):
            item = QTableWidgetItem(str(text))
            if col == 4:
                item.setForeground(Qt.darkGreen if ok else Qt.darkRed)
            self.table_info.setItem(row, col, item)
        self.table_info.scrollToBottom()

    def _add_raw_row(self, direction: str, frame: bytes) -> None:
        core = _core()
        # 行号 → 原字节：过滤/裁剪后仍能取回整帧（双击送单帧解析）
        row = self.table_raw.rowCount()
        self.table_raw.insertRow(row)
        for col, text in enumerate([
            self._time(with_date=False), direction, str(len(frame)),
            core.format_hex(frame),
        ]):
            self.table_raw.setItem(row, col, QTableWidgetItem(text))
        self.table_raw.setVerticalHeaderItem(row, QTableWidgetItem(str(row)))
        self.table_raw.item(row, 3).setData(Qt.UserRole, bytes(frame))
        self.table_raw.scrollToBottom()

    def _on_raw_row_activated(self, row: int, _column: int) -> None:
        item = self.table_raw.item(row, 3)
        if item is None:
            return
        raw = item.data(Qt.UserRole)
        if isinstance(raw, (bytes, bytearray)):
            self.frame_to_single_parse.emit(bytes(raw).hex().upper())

    @staticmethod
    def _time(with_date: bool = True) -> str:
        fmt = "%H:%M:%S.%f" if not with_date else "%Y-%m-%d %H:%M:%S"
        text = datetime.now().strftime(fmt)
        return text[:-3] if not with_date else text

    def _update_txrx(self) -> None:
        self.lbl_count.setText(f"TX {self._tx_count} / RX {self._rx_count}")

    # ══════════════════════════════ 通道（串口 / 蓝牙，收发统一走控制器）
    def set_serial_worker(self, worker) -> None:
        """注入主窗口共享串口线程（只记引用并转交控制器，订阅由控制器负责）。"""
        self._serial_worker = worker
        self._channel.set_serial_worker(worker)

    def set_bluetooth_provider(self, provider) -> None:
        """注入「取蓝牙通信线程」的回调（主窗口接到「蓝牙工具」页；本页不建/不断连接）。"""
        self._bt_provider = provider
        self._channel.set_bluetooth_provider(provider)
        self._refresh_channel_ui()

    def _on_channel_combo_changed(self, *_args) -> None:
        self._channel.set_channel(self.combo_channel.currentData())
        self._schedule_save()

    def _on_channel_switched(self, key: str) -> None:
        """切通道：清分帧缓冲（半帧绝不跨通道拼接）+ 记日志。"""
        self._rx_buf.clear()
        self._log(f"[系统] 发送通道已切换为{('蓝牙' if key == 'bluetooth' else '串口')}", "sys")
        self._refresh_channel_ui()

    def _on_channel_state(self, text: str, ready: bool) -> None:
        self.lbl_state.setText(text)
        self.lbl_state.setStyleSheet(
            "color: #0A7D28;" if ready else "color: #B42318;")
        for btn in (self.btn_read_addr, self.btn_write_addr, self.btn_broadcast_time):
            btn.setEnabled(bool(ready))
        # 「发送」始终可点：未就绪时点击给**当前通道**的具体原因（灰按钮说不出原因）
        self.btn_send.setEnabled(True)

    def _refresh_channel_ui(self) -> None:
        """把控制器的当前状态刷到界面（注入 provider / 加载配置后调用）。"""
        text = self._channel.state_text()
        ok, _reason = self._channel.ready()
        self._on_channel_state(text, ok)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """切回本页时重新对齐蓝牙 worker（蓝牙页可能在之后才连接/重建线程）。"""
        super().showEvent(event)
        self._channel.rebind_bluetooth()
        self._refresh_channel_ui()

    # ═════════════════════════════════════════════════ 主题 / 落盘 / 收尾
    def restyle_for_theme(self, dark: bool) -> None:
        self._dark = bool(dark)
        self._apply_theme_style(self._dark)

    def _apply_theme_style(self, dark: bool) -> None:
        p = LOG_PALETTES[bool(dark)]
        self._palette = p
        self.log_view.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {p['bg']}; color: {p['fg']};"
            f" border: 1px solid {'#3C3C3C' if dark else '#D0D7DE'}; }}")

    def _config_values(self) -> dict:
        return {
            "addr": self.edit_addr.text(),
            "write_addr": self.edit_write_addr.text(),
            "pa": self.edit_pa.text(),
            "pwd": self.edit_pwd.text(),
            "operator": self.edit_operator.text(),
            "timeout_ms": int(self.spin_timeout.value()),
            "loop": bool(self.chk_loop.isChecked()),
            "page": int(self.tabs.currentIndex()),
            "channel": self._channel.channel,
        }

    def _load_persisted(self) -> None:
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        try:
            self.edit_addr.setText(str(data.get("addr") or "000000000000"))
            self.edit_write_addr.setText(str(data.get("write_addr") or ""))
            self.edit_pa.setText(str(data.get("pa") or "02"))
            self.edit_pwd.setText(str(data.get("pwd") or "000000"))
            self.edit_operator.setText(str(data.get("operator") or "00000000"))
            self.spin_timeout.setValue(int(data.get("timeout_ms") or 3000))
            self.chk_loop.setChecked(bool(data.get("loop")))
            page = int(data.get("page") or 0)
            if 0 <= page < len(PAGES):
                self.tabs.setCurrentIndex(page)
            channel = ch.normalize_channel(data.get("channel"))
            index = self.combo_channel.findData(channel)
            if index >= 0:
                self.combo_channel.setCurrentIndex(index)   # 触发 set_channel
            self._refresh_channel_ui()
        except (TypeError, ValueError):
            pass

    def _schedule_save(self) -> None:
        self._save_timer.start(400)

    def _save_config(self) -> None:
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config_values(), f, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._log(f"[失败] 保存参数失败：{exc}", "fail")

    def cleanup(self) -> None:
        """页面销毁：停定时器、断串口订阅、落盘（**不关端口**）。"""
        for timer in (self._reply_timer, self._next_timer, self._save_timer):
            try:
                timer.stop()
            except RuntimeError:
                pass
        self._channel.cleanup()                 # 只断订阅，不断开串口/蓝牙连接
        self._serial_worker = None
        try:
            self._save_config()
        except Exception:                          # noqa: BLE001
            pass


def _html_escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


__all__ = ["CONFIG_NAME", "DEFRAME_STRATEGY", "Dlt645TestWidget", "PAGES"]
