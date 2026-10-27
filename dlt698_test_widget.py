# -*- coding: utf-8 -*-
"""协议 8（DL/T 698.45）**协议测试页** —— 按 OAD 分类的预置测试库 + 一键组帧下发。

与「协议组帧」页的分工：组帧页临时、任意填；本页是**预先做好**的测试项库，按协议的对象
标识（OI）把 777 个对象分成十类（电能量/需量/变量/事件/参变量/冻结数据/采集/文件与应用/
控制/厂家扩展），勾选即下发，用来做设备一致性/功能测试。

页面结构（对齐现场同类工具的用法）
--------------------------------
    顶部  读地址 / 读时间 / 系统时间 / 建立应用连接 ‖ 写地址 / 写时间 ‖ 发送 终止 清空
          + Lst发送（合成一帧 GET-Normal-List）/ 循环发送
    左栏  报文参数（地址类型/逻辑地址/地址长度/SA/CA/服务序号/优先级/超时/重试）+ 地址簿
    中栏  读取属性 | 设置属性 | 读取记录 | 设置方法 四页，每页「分类树 + 当前项参数 + 帧预览」
    右栏  收发日志（逐条：时间/地址/操作/结果/字段行）
    底部  信息表（时间/结果/信息）+ 报文表（时间/方向/长度/报文）

设计约束（改本页前先读）
--------------------
- **不自建串口**：端口生命周期归主窗口顶部「串口配置」，本页经
  :meth:`Dlt698TestWidget.set_serial_worker` 借用共享 :class:`serial_worker.SerialWorker`。
  发送只用 ``write_raw``（静默），TX/RX 日志本页自己写 —— 不用 ``send_frame``，否则每条
  测试都刷一行 ``[发送]``（AGENTS §8 陷阱 58）。
- **RX 只用 ``raw_data_received`` 自组帧**：``frame_received`` 由 ``SerialWorker`` 的
  645/FT1.2 判据产生，698 整帧 = ``L + 2`` 会被它截断（见陷阱 77）。组帧判据复用分帧单一
  来源 :mod:`frame_deframe`，切不出整帧时按「68H/FEH 才是帧起点」重同步丢噪声。
- **``crcmod`` 是可选依赖**：`dlt698_test_core` 顶层 import 了 frame_gen/parser ⇒ 本页对它
  一律**函数内惰性 import**，失败给「请 pip install crcmod」提示，绝不连带打不开其它页。
- **不冒充判定**：CONNECT-Response 与记录型的二维数据体没有做字段级解析（协议文档没给可
  自证的字段布局）⇒ 结果列给「已收到/未做字段级解析」，不写「成功」。见
  :func:`dlt698_test_core.evaluate_response` 的 ``ok=None``。
- 状态机不用 QThread：单发 :class:`QTimer` + 标志位（照 ``test_plan_widget`` / 升级页的既有范式）。
- 分类树按页**惰性构建**（777 项 × 4 页全建会拖慢切页）；筛选框对已建好的树做显隐。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

import app_paths
import channel_link as ch
import frame_deframe

CONFIG_NAME = "dlt698_testbench.json"
CONFIG_VERSION = 1
DEFRAME_STRATEGY = "dlt698_45"
RX_BUF_MAX = 64 * 1024
#: 报文表最多保留的行数（超出丢最旧；行号映射随之重建）
RAW_ROW_LIMIT = 2000
LOG_MAX_BLOCKS = 4000
#: 兼容旧引用：串口未就绪的统一提示（通道相关的提示由 controller 给）
TIP_NOT_CONNECTED = ch.TIP_SERIAL_DOWN

#: 日志配色（浅/暗双调；与升级页同一套色卡，避免两页观感不一致）
LOG_PALETTES = {
    False: {"bg": "#FFFFFF", "fg": "#1F2328", "border": "#D0D7DE",
            "ok": "#0A7D28", "fail": "#B42318", "info": "#1F6FEB",
            "warn": "#9A6700", "tx": "#6639BA", "hint": "#6E7781"},
    True: {"bg": "#1E1E1E", "fg": "#D4D4D4", "border": "#3C3C3C",
           "ok": "#4EC9B0", "fail": "#F48771", "info": "#569CD6",
           "warn": "#DCDCAA", "tx": "#C586C0", "hint": "#8A8A8A"},
}

#: 页面分页定义：键 / 标题 / 说明（说明进树的 tooltip）
PAGES: Tuple[Tuple[str, str], ...] = (
    ("read", "读取属性"),
    ("set", "设置属性"),
    ("record", "读取记录"),
    ("action", "设置方法"),
)

#: RSD 选择方法（与 `dlt698_test_core.RSD_CHOICES` 一致，这里带界面短名）
RSD_ITEMS: Tuple[Tuple[int, str], ...] = (
    (0, "不选择（全部记录）"),
    (1, "方法1：属性 = 指定值"),
    (2, "方法2：属性区间 + 间隔"),
    (9, "方法9：上第 n 次"),
    (10, "方法10：最新 n 条"),
)

ADDR_TYPES: Tuple[Tuple[int, str], ...] = (
    (0, "单地址"),
    (1, "通配地址"),
    (2, "组地址"),
    (3, "广播地址"),
)

#: 默认落盘值
DEFAULTS = {
    "version": CONFIG_VERSION,
    "sa_type": 0,
    "sa_logic": 0,
    "sa_len": 6,
    "sa_text": "111111111111",
    "write_text": "",
    "ca": 0,
    "piid": 0,
    "priority": 0,
    "timeout_ms": 2000,
    "retries": 1,
    "channel": ch.DEFAULT_CHANNEL,
    "list_mode": False,
    "loop_mode": False,
    "detail": True,
    "page": "read",
    "read_time_text": "",
    "write_time_text": "",
    "use_system_time": True,
    "address_book": [],
    "attr": 2,
    "index": 0,
    "set_data": "",
    "rsd_choice": 0,
    "rsd_oad": "",
    "rsd_value": "",
    "rsd_start": "",
    "rsd_end": "",
    "rsd_interval": "",
    "rsd_n": 1,
    "rcsd": "",
    "action_data": "",
}


def _parse_hex(text: str) -> bytes:
    """宽松十六进制（去空格/逗号/0x）；非法抛 ValueError。"""
    core = _core()
    return core.parse_hex(text)


def _fmt(data: bytes, limit: int = 0) -> str:
    core = _core()
    return core.format_hex(data, limit)


def _core():
    """惰性 import 逻辑层（`crcmod` 可选依赖，见模块 docstring）。"""
    import dlt698_test_core

    return dlt698_test_core


def tree_leaf_count(state: dict) -> int:
    """某页分类树里**已建出**的叶子数（= 该类下可下发的对象数）。"""
    tree = state.get("tree")
    if tree is None:
        return 0
    total = 0
    for i in range(tree.topLevelItemCount()):
        cat = tree.topLevelItem(i)
        for j in range(cat.childCount()):
            total += cat.child(j).childCount()
    return total


class Dlt698TestWidget(QWidget):
    """698.45 协议测试页（仅协议 8 可见；复用主窗口共享串口）。"""

    #: 请求主窗口切到「光伏升级」页（远程升级入口，避免重复实现升级流程）
    open_upgrade = Signal()
    #: 请求主窗口把一帧 hex 送进「单帧解析」页（双击报文表触发）
    frame_to_single_parse = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._config_path = str(app_paths.data_path(CONFIG_NAME))
        self._dark = False
        self._palette = LOG_PALETTES[False]

        self._serial_worker = None
        self._bt_provider = None
        self._rx_buf = bytearray()

        # 发送通道（串口 / 蓝牙）：控制器管收发与状态，分帧/判定仍在本页
        self._channel = ch.ChannelController(self)
        self._channel.rx.connect(self._on_rx_data)
        self._channel.state_changed.connect(self._on_channel_state)
        self._channel.channel_changed.connect(self._on_channel_switched)
        self._channel.error.connect(lambda msg: self._log(f"[失败] {msg}", "fail"))

        # 发送队列状态
        self._queue: List[dict] = []
        self._current: Optional[dict] = None
        self._awaiting = False
        self._stopped = False
        self._tx_count = 0
        self._rx_count = 0
        #: 报文表行号 → 原始字节（表格里放的是可能被截断的文本，双击要用原字节）
        self._raw_frames: Dict[int, bytes] = {}

        # 每页的界面元素（惰性构建）
        self._pages: Dict[str, dict] = {}
        self._counter = 0

        # 落盘防抖（必须先于 _build_ui / _load_persisted 建好：载入会触发 valueChanged）
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_persisted)

        # 等待响应定时器（单发）
        self._reply_timer = QTimer(self)
        self._reply_timer.setSingleShot(True)
        self._reply_timer.timeout.connect(self._on_reply_timeout)

        # 队列推进定时器（收到响应后稍等再发下一条，给设备留处理时间）
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._send_next)

        self._build_ui()
        self._load_persisted()
        self._apply_theme_style(self._dark)

    # ==================================================================
    # 界面
    # ==================================================================

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        root.addWidget(self._build_top_bar())

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._build_left_panel())
        split.addWidget(self._build_center())
        split.addWidget(self._build_log_panel())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 1)
        split.setSizes([300, 520, 460])
        root.addWidget(split, 1)

        root.addWidget(self._build_bottom())

    # ── 顶部：地址 / 时间 / 连接 / 发送控制 ─────────────────────────────
    def _build_top_bar(self) -> QWidget:
        box = QGroupBox("设备操作")
        grid = QVBoxLayout(box)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setSpacing(3)

        row1 = QHBoxLayout()
        row1.setSpacing(4)
        row1.addWidget(QLabel("读地址"))
        self.edit_read_addr = QLineEdit()
        self.edit_read_addr.setPlaceholderText("读到的设备地址（6 字节 hex，如 111111111111）")
        self.edit_read_addr.setMinimumWidth(180)
        self.edit_read_addr.editingFinished.connect(self._on_read_addr_edited)
        row1.addWidget(self.edit_read_addr)

        self.btn_read_addr = QPushButton("读地址")
        self.btn_read_addr.setToolTip("GET-Request Normal，OAD=40010200（通信地址）")
        self.btn_read_addr.clicked.connect(self._on_read_address)
        row1.addWidget(self.btn_read_addr)

        row1.addSpacing(6)
        row1.addWidget(QLabel("读时间"))
        self.edit_read_time = QLineEdit()
        self.edit_read_time.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        self.edit_read_time.setMinimumWidth(150)
        row1.addWidget(self.edit_read_time)
        self.btn_read_time = QPushButton("读时间")
        self.btn_read_time.setToolTip("GET-Request Normal，OAD=40000200（日期时间）")
        self.btn_read_time.clicked.connect(self._on_read_datetime)
        row1.addWidget(self.btn_read_time)

        self.chk_system_time = QCheckBox("系统时间")
        self.chk_system_time.setToolTip("勾选后写时间用本机当前时间")
        row1.addWidget(self.chk_system_time)

        self.btn_connect = QPushButton("建立应用连接")
        self.btn_connect.setToolTip("CONNECT-Request（协议文档附录 H.2 的字段默认值）")
        self.btn_connect.clicked.connect(self._on_connect)
        row1.addWidget(self.btn_connect)

        row1.addSpacing(6)
        row1.addWidget(self._vline())
        row1.addWidget(QLabel("写地址"))
        self.edit_write_addr = QLineEdit()
        self.edit_write_addr.setPlaceholderText("要写入的地址（hex）")
        self.edit_write_addr.setMinimumWidth(160)
        row1.addWidget(self.edit_write_addr)
        self.btn_write_addr = QPushButton("写地址")
        self.btn_write_addr.setToolTip("SET-Request Normal，OAD=40010200（通信地址）")
        self.btn_write_addr.clicked.connect(self._on_write_address)
        row1.addWidget(self.btn_write_addr)

        row1.addSpacing(6)
        row1.addWidget(QLabel("写时间"))
        self.edit_write_time = QLineEdit()
        self.edit_write_time.setPlaceholderText("YYYY-MM-DD HH:MM:SS（留空=系统时间）")
        self.edit_write_time.setMinimumWidth(170)
        row1.addWidget(self.edit_write_time)
        self.btn_write_time = QPushButton("写时间")
        self.btn_write_time.setToolTip("SET-Request Normal，OAD=40000200（日期时间）")
        self.btn_write_time.clicked.connect(self._on_write_datetime)
        row1.addWidget(self.btn_write_time)
        row1.addStretch(1)
        grid.addLayout(row1)

        row_channel = QHBoxLayout()
        row_channel.setSpacing(4)
        row_channel.addWidget(QLabel("发送通道"))
        self.combo_channel = QComboBox()
        for label, key in ch.CHANNELS:
            self.combo_channel.addItem(label, key)
        self.combo_channel.setToolTip(
            "串口 = 顶部「串口配置」的共享连接；蓝牙 = 「蓝牙工具」页已建立的连接"
            "（协议帧整帧一次 ATT 写，超过一次写上限会明确报错）")
        self.combo_channel.currentIndexChanged.connect(self._on_channel_combo_changed)
        row_channel.addWidget(self.combo_channel)
        self.lbl_state = QLabel("")
        self.lbl_state.setWordWrap(True)
        row_channel.addWidget(self.lbl_state, 1)
        grid.addLayout(row_channel)

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        self.btn_send = QPushButton("发送")
        self.btn_send.setMinimumWidth(80)
        self.btn_send.setToolTip("把当前页勾选的测试项逐条下发（未勾选则发当前项）")
        self.btn_send.clicked.connect(self._on_send)
        row2.addWidget(self.btn_send)

        self.btn_stop = QPushButton("终止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        row2.addWidget(self.btn_stop)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setToolTip("清空日志、信息表与报文表（不改参数）")
        self.btn_clear.clicked.connect(self._on_clear)
        row2.addWidget(self.btn_clear)

        row2.addSpacing(8)
        self.chk_list = QCheckBox("Lst发送")
        self.chk_list.setToolTip(
            "勾选后把本页勾选的多个 OAD 合成**一帧** GET-Request Normal-List（05 02）下发；"
            "不勾则每个 OAD 各发一帧")
        row2.addWidget(self.chk_list)

        self.chk_loop = QCheckBox("循环发送")
        self.chk_loop.setToolTip("一轮发完后自动重来，直到点「终止」")
        row2.addWidget(self.chk_loop)

        row2.addSpacing(8)
        self.btn_edit = QPushButton("编辑")
        self.btn_edit.setToolTip("把当前项的 OAD/OMD 填进覆盖框就地修改（清空覆盖框即回到按属性生成）")
        self.btn_edit.clicked.connect(self._on_edit_current)
        row2.addWidget(self.btn_edit)

        self.btn_upgrade = QPushButton("远程升级")
        self.btn_upgrade.setToolTip("切到「光伏升级」页（文件传输升级流程）")
        self.btn_upgrade.clicked.connect(self.open_upgrade.emit)
        row2.addWidget(self.btn_upgrade)

        row2.addStretch(1)
        grid.addLayout(row2)
        return box

    @staticmethod
    def _vline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    # ── 左栏：报文参数 + 地址簿 ────────────────────────────────────────
    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        grp = QGroupBox("报文参数")
        form = QFormLayout(grp)
        form.setContentsMargins(8, 6, 8, 6)
        form.setSpacing(4)

        self.combo_sa_type = QComboBox()
        for value, name in ADDR_TYPES:
            self.combo_sa_type.addItem(name, value)
        self.combo_sa_type.currentIndexChanged.connect(self._on_sa_type_changed)
        form.addRow("地址类型", self.combo_sa_type)

        self.combo_sa_logic = QComboBox()
        for value in range(4):
            self.combo_sa_logic.addItem(f"{value}", value)
        self.combo_sa_logic.currentIndexChanged.connect(lambda *_a: self._refresh_preview())
        form.addRow("逻辑地址", self.combo_sa_logic)

        self.combo_sa_len = QComboBox()
        for value in range(1, 17):
            self.combo_sa_len.addItem(f"{value}", value)
        self.combo_sa_len.currentIndexChanged.connect(self._on_sa_len_changed)
        form.addRow("地址长度", self.combo_sa_len)

        self.edit_sa = QLineEdit()
        self.edit_sa.setPlaceholderText("按书写顺序的地址，如 111111111111")
        self.edit_sa.textChanged.connect(lambda *_a: self._refresh_preview())
        self.edit_sa.textChanged.connect(lambda *_a: self._schedule_save())
        form.addRow("服务器地址", self.edit_sa)

        self.lbl_sa_wire = QLabel("—")
        self.lbl_sa_wire.setStyleSheet("color:#6E7781;")
        self.lbl_sa_wire.setWordWrap(True)
        form.addRow("线上 SA", self.lbl_sa_wire)

        self.spin_ca = QSpinBox()
        self.spin_ca.setRange(0, 255)
        self.spin_ca.setToolTip("客户机地址 CA（1 字节）")
        self.spin_ca.valueChanged.connect(lambda *_a: self._refresh_preview())
        self.spin_ca.valueChanged.connect(lambda *_a: self._schedule_save())
        form.addRow("客户端地址", self.spin_ca)

        piid_row = QHBoxLayout()
        self.spin_piid = QSpinBox()
        self.spin_piid.setRange(0, 63)
        self.spin_piid.setToolTip("服务序号（0~63）")
        self.spin_piid.valueChanged.connect(self._on_piid_changed)
        self.spin_piid.valueChanged.connect(lambda *_a: self._schedule_save())
        piid_row.addWidget(self.spin_piid)
        self.combo_priority = QComboBox()
        self.combo_priority.addItem("普通优先级", 0)
        self.combo_priority.addItem("高优先级", 1)
        self.combo_priority.currentIndexChanged.connect(self._on_piid_changed)
        self.combo_priority.currentIndexChanged.connect(lambda *_a: self._schedule_save())
        piid_row.addWidget(self.combo_priority)
        wrap = QWidget()
        wrap.setLayout(piid_row)
        piid_row.setContentsMargins(0, 0, 0, 0)
        form.addRow("服务序号/优先级", wrap)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(100, 60000)
        self.spin_timeout.setSingleStep(100)
        self.spin_timeout.setSuffix(" ms")
        self.spin_timeout.valueChanged.connect(lambda *_a: self._schedule_save())
        form.addRow("等待响应", self.spin_timeout)

        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(0, 5)
        self.spin_retries.setToolTip("超时后重发次数（0 = 不重发，直接记超时）")
        self.spin_retries.valueChanged.connect(lambda *_a: self._schedule_save())
        form.addRow("超时重发", self.spin_retries)
        lay.addWidget(grp)

        grp_book = QGroupBox("地址簿")
        book_lay = QVBoxLayout(grp_book)
        book_lay.setContentsMargins(8, 6, 8, 6)
        book_lay.setSpacing(3)
        self.tree_book = QTreeWidget()
        self.tree_book.setHeaderHidden(True)
        self.tree_book.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree_book.itemDoubleClicked.connect(self._on_book_activated)
        book_lay.addWidget(self.tree_book, 1)
        book_row = QHBoxLayout()
        btn_add = QPushButton("添加当前")
        btn_add.setToolTip("把「服务器地址」加入地址簿（单地址组）")
        btn_add.clicked.connect(self._on_book_add)
        book_row.addWidget(btn_add)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._on_book_remove)
        book_row.addWidget(btn_del)
        book_lay.addLayout(book_row)
        hint = QLabel("双击地址簿条目 → 设为当前服务器地址")
        hint.setStyleSheet("color:#6E7781;")
        hint.setWordWrap(True)
        book_lay.addWidget(hint)
        lay.addWidget(grp_book, 1)
        return panel

    # ── 中栏：四个测试分页 ─────────────────────────────────────────────
    def _build_center(self) -> QWidget:
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        for _key, title in PAGES:
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 2, 0, 0)
            placeholder = QLabel("（首次切到本页时构建分类树）")
            placeholder.setStyleSheet("color:#6E7781;")
            lay.addWidget(placeholder)
            page._placeholder = placeholder
            self.tabs.addTab(page, title)
        return self.tabs

    def _ensure_page(self, key: str) -> dict:
        """惰性构建某页的「筛选 + 分类树 + 当前项参数 + 帧预览」。"""
        if key in self._pages:
            return self._pages[key]
        title = dict(PAGES)[key]
        index = [k for k, _t in PAGES].index(key)
        page = self.tabs.widget(index)
        lay = page.layout()
        placeholder = getattr(page, "_placeholder", None)
        if placeholder is not None:
            lay.removeWidget(placeholder)
            placeholder.deleteLater()

        split = QSplitter(Qt.Horizontal)

        # 左：筛选 + 分类树
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(3)
        filter_row = QHBoxLayout()
        edit_filter = QLineEdit()
        edit_filter.setPlaceholderText("筛选：名称 / OI 十六进制（如 2000）/ 接口类")
        edit_filter.setClearButtonEnabled(True)
        filter_row.addWidget(edit_filter, 1)
        btn_check_all = QPushButton("全选")
        btn_check_all.setToolTip("把当前可见项全部勾上")
        filter_row.addWidget(btn_check_all)
        btn_uncheck_all = QPushButton("清空勾选")
        filter_row.addWidget(btn_uncheck_all)
        left_lay.addLayout(filter_row)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setColumnCount(1)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setUniformRowHeights(True)
        tree.itemChanged.connect(lambda *_a, k=key: self._refresh_preview(k))
        tree.itemSelectionChanged.connect(lambda *_: self._on_tree_selection(key))
        left_lay.addWidget(tree, 1)

        counter = QLabel("0 项")
        counter.setStyleSheet("color:#6E7781;")
        left_lay.addWidget(counter)
        split.addWidget(left)

        # 右：当前项参数
        detail = self._build_detail(key)
        split.addWidget(detail["widget"])
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([300, 330])
        lay.addWidget(split, 1)

        state = {
            "key": key, "title": title, "tree": tree, "filter": edit_filter,
            "counter": counter, "built": False, "split": split, **detail,
        }
        self._pages[key] = state

        edit_filter.textChanged.connect(lambda text, k=key: self._apply_filter(k, text))
        btn_check_all.clicked.connect(lambda _c=False, k=key: self._set_all_checked(k, True))
        btn_uncheck_all.clicked.connect(lambda _c=False, k=key: self._set_all_checked(k, False))
        self._build_tree(key)
        return state

    def _build_detail(self, key: str) -> dict:
        """当前项参数面板（各页共用的骨架 + 本页专属参数区）。"""
        box = QGroupBox("当前项")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)

        lbl_name = QLabel("（未选择）")
        font = lbl_name.font()
        font.setBold(True)
        lbl_name.setFont(font)
        lbl_name.setWordWrap(True)
        lay.addWidget(lbl_name)

        lbl_cls = QLabel("")
        lbl_cls.setStyleSheet("color:#6E7781;")
        lbl_cls.setWordWrap(True)
        lay.addWidget(lbl_cls)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(3)

        # 属性/方法由**选中的叶子**决定（叶子已是具体 OAD/OMD），这里只做回显
        combo_attr = QComboBox()
        combo_attr.setEnabled(False)
        combo_attr.setToolTip("由选中的树节点决定（节点已是具体 OAD）")
        if key != "action":
            form.addRow("属性", combo_attr)
        else:
            form.addRow("方法", combo_attr)

        spin_index = QSpinBox()
        spin_index.setRange(0, 255)
        spin_index.setToolTip("元素索引：0 = 全部内容")
        spin_index.valueChanged.connect(lambda *_a, k=key: self._refresh_preview(k))
        if key != "action":
            form.addRow("元素索引", spin_index)

        if key == "set":
            edit_data = QLineEdit()
            edit_data.setPlaceholderText("A-XDR 数据（含类型 tag），如 1C 07 E0 01 14 10 1B 0B")
            edit_data.textChanged.connect(lambda *_, k=key: self._refresh_preview(k))
            form.addRow("数据", edit_data)
            edit_extra = edit_data
        elif key == "action":
            edit_extra = QLineEdit()
            edit_extra.setPlaceholderText("参数 A-XDR（可空；如 0F 00 = integer 0）")
            edit_extra.textChanged.connect(lambda *_, k=key: self._refresh_preview(k))
            form.addRow("参数", edit_extra)
        elif key == "record":
            edit_extra = QLineEdit()
            edit_extra.setPlaceholderText("RCSD 列 OAD（可空；多列用空格分隔）")
            edit_extra.textChanged.connect(lambda *_, k=key: self._refresh_preview(k))
            form.addRow("RCSD 列", edit_extra)
        else:
            edit_extra = None

        lay.addLayout(form)

        # 记录型专属：RSD
        rsd_box = QWidget()
        rsd_form = QFormLayout(rsd_box)
        rsd_form.setContentsMargins(0, 0, 0, 0)
        rsd_form.setSpacing(3)
        combo_rsd = QComboBox()
        for value, name in RSD_ITEMS:
            combo_rsd.addItem(name, value)
        combo_rsd.currentIndexChanged.connect(lambda *_a: self._sync_rsd(key))
        rsd_form.addRow("记录选择", combo_rsd)

        edit_rsd_oad = QLineEdit()
        edit_rsd_oad.setPlaceholderText("选择依据的 OAD（4 字节 hex）")
        edit_rsd_oad.textChanged.connect(lambda *_, k=key: self._refresh_preview(k))
        rsd_form.addRow("依据 OAD", edit_rsd_oad)

        edit_rsd_value = QLineEdit()
        edit_rsd_value.setPlaceholderText("指定值 A-XDR（如 1C 07 E0 01 14 00 00 00）")
        edit_rsd_value.textChanged.connect(lambda *_, k=key: self._refresh_preview(k))
        rsd_form.addRow("指定值", edit_rsd_value)

        edit_rsd_start = QLineEdit()
        edit_rsd_start.setPlaceholderText("起始值 A-XDR")
        edit_rsd_start.textChanged.connect(lambda *_, k=key: self._refresh_preview(k))
        rsd_form.addRow("起始值", edit_rsd_start)

        edit_rsd_end = QLineEdit()
        edit_rsd_end.setPlaceholderText("结束值 A-XDR（区间前闭后开）")
        edit_rsd_end.textChanged.connect(lambda *_, k=key: self._refresh_preview(k))
        rsd_form.addRow("结束值", edit_rsd_end)

        edit_rsd_interval = QLineEdit()
        edit_rsd_interval.setPlaceholderText("间隔 A-XDR（空 = 00 = 区间内全部）")
        edit_rsd_interval.textChanged.connect(lambda *_, k=key: self._refresh_preview(k))
        rsd_form.addRow("间隔", edit_rsd_interval)

        spin_rsd_n = QSpinBox()
        spin_rsd_n.setRange(1, 255)
        spin_rsd_n.valueChanged.connect(lambda *_a, k=key: self._refresh_preview(k))
        rsd_form.addRow("n", spin_rsd_n)

        if key == "record":
            lay.addWidget(rsd_box)
        else:
            rsd_box.setVisible(False)

        # OAD/OMD 覆盖：预置项之外的厂家对象、或临时改一两个字节时用（留空=按属性/索引生成）
        edit_oad = QLineEdit()
        edit_oad.setPlaceholderText("OAD/OMD 覆盖（留空 = 按上方属性/索引生成）")
        edit_oad.setToolTip("填 4 字节十六进制即整项替换；点「编辑」把当前值填进来就地改")
        edit_oad.textChanged.connect(lambda *_, k=key: self._refresh_preview(k))
        lay.addWidget(edit_oad)

        lbl_oid = QLabel("—")
        lbl_oid.setStyleSheet("color:#6E7781;")
        lbl_oid.setWordWrap(True)
        lay.addWidget(lbl_oid)

        lbl_frame = QLabel("帧预览")
        lbl_frame.setStyleSheet("color:#6E7781;")
        lay.addWidget(lbl_frame)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setMaximumHeight(96)
        preview.setFont(QFont("Consolas", 9))
        preview.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        lay.addWidget(preview)
        lay.addStretch(1)

        return {
            "widget": box, "lbl_name": lbl_name, "lbl_cls": lbl_cls,
            "combo_attr": combo_attr,
            "spin_index": spin_index, "edit_extra": edit_extra,
            "combo_rsd": combo_rsd, "rsd_box": rsd_box,
            "edit_rsd_oad": edit_rsd_oad, "edit_rsd_value": edit_rsd_value,
            "edit_rsd_start": edit_rsd_start, "edit_rsd_end": edit_rsd_end,
            "edit_rsd_interval": edit_rsd_interval, "spin_rsd_n": spin_rsd_n,
            "lbl_oid": lbl_oid, "edit_oad": edit_oad, "preview": preview, "item": None,
        }

    def _build_tree(self, key: str) -> None:
        """建立某页的分类树（页 → 类 → 子类 → **每个属性一条具体 OAD**）。

        层次与现场同类工具一致：
        - 顶层 `4H: 参变量`（OI 高字节）
        - 子层 `3H: 设备`（该高字节的低 4 位）
        - 叶子 `43000300_（版本信息）_(索引=0)_(优先级及序号=00)`

        叶子是**具体 OAD**（不是 OI），勾选即代表「这一条报文」，无需再去挑属性；
        「设置方法」页的叶子是具体 OMD（`00100100_（复位）_(优先级及序号=00)`）。
        4500 余条叶子全建约 20ms（实测），故不做惰性展开 —— 惰性会让「全选/筛选/计数」变复杂。
        """
        state = self._pages[key]
        if state["built"]:
            return
        tree = state["tree"]
        tree.blockSignals(True)
        tree.clear()
        core = _core()
        try:
            cats = core.catalog()
        except ImportError as exc:
            QMessageBox.warning(self, "缺少依赖",
                                f"无法加载 698.45 测试库：{exc}\n\n请执行：pip install crcmod")
            tree.blockSignals(False)
            return

        piid = self.spin_piid.value() | (int(self.combo_priority.currentData() or 0) << 7)
        for cat in cats:
            cat_item = QTreeWidgetItem([core.category_label(
                cat.groups[0].hbyte if cat.groups else 0, cat.name)])
            cat_item.setFlags(Qt.ItemIsEnabled)
            tree.addTopLevelItem(cat_item)
            for group in cat.groups:
                group_item = QTreeWidgetItem([core.group_label(group.hbyte, group.name)])
                group_item.setFlags(Qt.ItemIsEnabled)
                cat_item.addChild(group_item)
                for item in group.items:
                    if key == "action":
                        entries = [(0, mid, mname, omd)
                                   for mid, mname, omd in core.omd_entries(item)]
                    elif key == "record":
                        entries = [(0, aid, core.record_leaf_name(item, aname), oad)
                                   for aid, aname, oad in core.record_entries(item)]
                    else:
                        # (元素索引, 属性号, 叶子名, OAD)：名字自带对象语义（A相电压 / 版本信息）
                        entries = list(core.leaf_entries(item))
                    for index, ident, name, raw in entries:
                        if key == "action":
                            text = core.omd_label(raw, name, piid)
                        else:
                            text = core.leaf_label(raw, name, index, piid)
                        leaf = QTreeWidgetItem([text])
                        leaf.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable
                                      | Qt.ItemIsUserCheckable)
                        leaf.setCheckState(0, Qt.Unchecked)
                        # 叶子自带完整报文标识 → 选中/下发都不必再推算
                        leaf.setData(0, Qt.UserRole, raw)
                        leaf.setData(0, Qt.UserRole + 1, item.oi)
                        leaf.setData(0, Qt.UserRole + 2, int(ident))
                        leaf.setData(0, Qt.UserRole + 3, name)
                        leaf.setData(0, Qt.UserRole + 4, int(index))
                        leaf.setToolTip(0, self._leaf_tip(item, ident, name, raw))
                        group_item.addChild(leaf)
                if group_item.childCount() == 0:
                    cat_item.removeChild(group_item)
            if cat_item.childCount() == 0:
                tree.takeTopLevelItem(tree.indexOfTopLevelItem(cat_item))

        tree.blockSignals(False)
        state["built"] = True
        state["counter"].setText(f"{tree_leaf_count(state)} 条 OAD")
        tree.expandItem(tree.topLevelItem(0))

    @staticmethod
    def _leaf_tip(item, ident: int, name: str, raw: bytes) -> str:
        kind = "OMD" if len(raw) == 4 and name in dict(item.methods) else "OAD"
        attrs = "、".join(f"{aid}={aname}" for aid, aname in item.attrs) or "（无属性表）"
        return (f"OI 0x{item.oi:04X} {item.name} · 接口类：{item.class_name}\n"
                f"{kind} = {raw.hex().upper()}（{ident} {name}）\n"
                f"该类全部属性：{attrs}")

    # ── 右栏：日志 ────────────────────────────────────────────────────
    def _build_log_panel(self) -> QWidget:
        box = QGroupBox("收发日志")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMaximumBlockCount(LOG_MAX_BLOCKS)
        self.log_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        lay.addWidget(self.log_text, 1)

        row = QHBoxLayout()
        self.chk_detail = QCheckBox("详细解析")
        self.chk_detail.setToolTip(
            "勾选后在日志里逐字段列出收发帧的结构（与「单帧解析」页同一张表）；"
            "取消只看摘要，日志更短")
        self.chk_detail.setChecked(True)
        self.chk_detail.toggled.connect(lambda *_a: self._schedule_save())
        row.addWidget(self.chk_detail)
        self.lbl_txrx = QLabel("TX 0 · RX 0")
        self.lbl_txrx.setStyleSheet("color:#6E7781;")
        row.addWidget(self.lbl_txrx)
        row.addStretch(1)
        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.clicked.connect(self.log_text.clear)
        row.addWidget(btn_clear_log)
        lay.addLayout(row)
        return box

    # ── 底部：信息表 / 报文表 ─────────────────────────────────────────
    def _build_bottom(self) -> QWidget:
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.setMaximumHeight(200)

        self.table_info = QTableWidget(0, 3)
        self.table_info.setHorizontalHeaderLabels(["时间", "结果", "信息"])
        self.table_info.verticalHeader().setVisible(False)
        self.table_info.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_info.setSelectionBehavior(QAbstractItemView.SelectRows)
        head = self.table_info.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(2, QHeaderView.Stretch)
        self.bottom_tabs.addTab(self.table_info, "信息")

        self.table_raw = QTableWidget(0, 4)
        self.table_raw.setHorizontalHeaderLabels(["时间", "方向", "长度", "报文"])
        self.table_raw.verticalHeader().setVisible(False)
        self.table_raw.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_raw.setSelectionBehavior(QAbstractItemView.SelectRows)
        head2 = self.table_raw.horizontalHeader()
        head2.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        head2.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        head2.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        head2.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_raw.setToolTip("双击一行 → 送到「单帧解析」页看完整解析树")
        self.table_raw.cellDoubleClicked.connect(self._on_raw_row_activated)
        self.bottom_tabs.addTab(self.table_raw, "报文")
        return self.bottom_tabs

    def _on_raw_row_activated(self, row: int, _column: int) -> None:
        """双击报文表：把那一帧的 hex 送给主窗口的「单帧解析」页。"""
        item = self.table_raw.item(row, 3)
        if item is None:
            return
        frame = self._raw_frames.get(int(row))
        if frame is None:
            return
        self.frame_to_single_parse.emit(frame.hex(" ").upper())
        self._log("[信息] 已把该帧送到「单帧解析」页", "info")

    # ==================================================================
    # 主题
    # ==================================================================

    def restyle_for_theme(self, dark: bool) -> None:
        self._dark = bool(dark)
        self._apply_theme_style(self._dark)

    def _apply_theme_style(self, dark: bool) -> None:
        p = LOG_PALETTES[bool(dark)]
        self._palette = p
        qss = (f"QPlainTextEdit {{ background-color: {p['bg']}; color: {p['fg']};"
               f" border: 1px solid {p['border']}; }}")
        self.log_text.setStyleSheet(qss)
        for state in self._pages.values():
            state["preview"].setStyleSheet(qss)

    # ==================================================================
    # 串口接线（复用主窗口共享 worker）
    # ==================================================================

    def set_serial_worker(self, worker) -> None:
        """注入主窗口共享串口线程（只记引用并转交控制器，订阅由控制器负责）。"""
        self._serial_worker = worker
        self._channel.set_serial_worker(worker)
        self._refresh_channel_ui()

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
        self._log(f"[系统] 发送通道已切换为{('蓝牙' if key == 'bluetooth' else '串口')}", "info")
        self._refresh_channel_ui()

    def _on_channel_state(self, text: str, ready: bool) -> None:
        self.lbl_state.setText(text)
        self.lbl_state.setStyleSheet(f"color:{'#0A7D28' if ready else '#B42318'};")
        for btn in (self.btn_read_addr, self.btn_read_time, self.btn_write_addr,
                    self.btn_write_time, self.btn_connect):
            btn.setEnabled(bool(ready))
            btn.setToolTip("" if ready else text)
        # 「发送」始终可点：未就绪时点击给**当前通道**的具体原因（灰按钮说不出原因）
        self.btn_send.setEnabled(True)

    def _refresh_channel_ui(self) -> None:
        """把控制器当前状态刷到界面（注入 provider / 加载配置后调用）。"""
        text = self._channel.state_text()
        ok, _reason = self._channel.ready()
        self._on_channel_state(text, ok)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """切回本页时重新对齐蓝牙 worker（蓝牙页可能在之后才连接/重建线程）。"""
        super().showEvent(event)
        self._channel.rebind_bluetooth()
        self._refresh_channel_ui()

    def cleanup(self) -> None:
        """页面销毁：停定时器、断通道订阅、落盘（**不关端口、不断蓝牙**）。"""
        for timer in (self._reply_timer, self._next_timer, self._save_timer):
            try:
                timer.stop()
            except RuntimeError:
                pass
        self._channel.cleanup()                 # 只断订阅，不断开串口/蓝牙连接
        self._serial_worker = None
        self._save_persisted()

    def _send_frame(self, frame: bytes) -> tuple:
        """经当前通道发送一帧 → ``(成功, 可读原因)``（蓝牙超限在这里被拦下）。"""
        return self._channel.send(frame)

    # ==================================================================
    # RX：原始字节 → 698 帧
    # ==================================================================

    def _on_rx_data(self, data: bytes) -> None:
        """当前通道收到的字节（控制器已按通道过滤）；698 分帧仍在本页。"""
        if not data:
            return
        self._rx_buf.extend(data)
        while True:
            need = self._complete_frame_len(self._rx_buf)
            if need:
                frame = bytes(self._rx_buf[:need])
                del self._rx_buf[:need]
                self._on_frame(frame)
                continue
            if self._resync_junk():
                continue
            break
        if len(self._rx_buf) > RX_BUF_MAX and not frame_deframe.frame_incomplete(
                DEFRAME_STRATEGY, self._rx_buf):
            dropped = len(self._rx_buf)
            self._rx_buf.clear()
            self._log(f"[信息] 丢弃 {dropped} 字节无法组帧的数据（缓冲上限 {RX_BUF_MAX}）", "info")

    # 旧名别名：外部/测试可能按串口时代的名字调用（行为不变）
    _on_serial_raw_data = _on_rx_data

    def _complete_frame_len(self, buf) -> int:
        """首部是否一帧完整且末字节 16H 的 698 帧；是则返回整帧长，否则 0。"""
        need = frame_deframe.frame_length_for(DEFRAME_STRATEGY, buf)
        if need and len(buf) >= need and buf[need - 1] == 0x16:
            return need
        return 0

    def _resync_junk(self) -> int:
        """丢掉确定不可能是帧起点的前导字节（698 帧只以 68H 开头，FEH 是唤醒前导）。"""
        buf = self._rx_buf
        k = 0
        while k < len(buf):
            if buf[k] not in (0x68, 0xFE):
                k += 1
                continue
            rest = buf[k:]
            if self._complete_frame_len(rest) or frame_deframe.frame_incomplete(
                    DEFRAME_STRATEGY, rest):
                break
            k += 1
        if k:
            del buf[:k]
            self._log(f"[信息] 丢弃 {k} 字节非帧起点数据（重同步：698 帧以 68H 开头）", "info")
        return k

    def _on_frame(self, frame: bytes) -> None:
        self._rx_count += 1
        self._update_txrx()
        self._add_raw_row("RX", frame)
        try:
            info = _core().evaluate_response(frame)
        except ImportError as exc:
            self._log(f"[失败] 解析库不可用：{exc}", "fail")
            return

        if not self._awaiting or self._current is None:
            # 非本页请求的响应（主动上报 / 别的页在收发）—— 记一条，不动队列
            self._log(f"[RX] {_fmt(frame, 200)}", "tx")
            self._log(f"     ↑ 未请求的帧：{info.get('title') or info.get('kind') or '未识别'}", "info")
            for line in (info.get("lines") or []):
                self._log(f"      {line}", "info")
            self._log_detail(frame, "帧结构")
            return

        self._reply_timer.stop()
        entry = self._current
        ok = info.get("ok")
        if ok is True:
            result, level = "成功", "ok"
        elif ok is False:
            result, level = "失败", "fail"
        else:
            result, level = "无法判定", "warn"

        self._mark_info_row(entry.get("row"), result, info)
        self._log_transaction(entry, frame, info, level)
        entry["attempt"] = 0
        self._handle_special(entry, frame, info)
        self._awaiting = False
        self._current = None
        self._next_timer.start(60)

    # ==================================================================
    # 发送队列
    # ==================================================================

    def _on_send(self) -> None:
        ok, reason = self._channel.ready()
        if not ok:
            QMessageBox.information(self, "发送通道未就绪", reason)
            return
        try:
            entries = self._build_entries()
        except ImportError as exc:
            QMessageBox.warning(self, "缺少依赖",
                                f"无法组帧：{exc}\n\n请执行：pip install crcmod")
            return
        except ValueError as exc:
            QMessageBox.warning(self, "参数不完整", str(exc))
            return
        if not entries:
            QMessageBox.information(
                self, "没有可发的项",
                "请先在分类树里勾选测试项（或选中一行作为当前项），再点「发送」。")
            return
        self._stopped = False
        self._queue = list(entries)
        self._set_running(True)
        self._send_next()

    def _build_entries(self) -> List[dict]:
        """按当前页 + 勾选项 + Lst发送 生成待发队列。"""
        key = self._active_key()
        state = self._pages.get(key)
        if not state:
            raise ValueError("当前页尚未构建，请稍后再试")
        core = _core()
        sa, ca, piid = self._sa_bytes(), self.spin_ca.value(), self._piid_byte()
        targets = self._targets(key)

        if key == "read" and self.chk_list.isChecked():
            oads = [self._current_ref(key, leaf) for leaf in targets]
            if not oads:
                raise ValueError("Lst发送 需要至少勾选 1 个测试项")
            frame = core.build_get_list(sa, ca, piid, oads)
            label = f"列表读取 {len(oads)} 项"
            row = self._add_info_row("等待中", label)
            return [{"frame": frame, "label": label, "row": row, "attempt": 0,
                     "kind": key, "specials": ()}]

        entries = []
        for leaf in targets:
            entries.append(self._entry_for(key, leaf, sa, ca, piid))
        return entries

    def _entry_for(self, key: str, leaf: dict, sa: bytes, ca: int, piid: int) -> dict:
        core = _core()
        item = leaf["item"]
        ref = self._current_ref(key, leaf)
        if key == "read":
            frame = core.build_get(sa, ca, piid, ref)
            label = f"{ref.hex().upper()} {core.describe_oad(ref)}"
        elif key == "set":
            data = _parse_hex(self._page_edit("set").text())
            if not data:
                raise ValueError(f"「{leaf['name']}」要设置属性，请先填「数据」（A-XDR 十六进制）")
            frame = core.build_set(sa, ca, piid, ref, data)
            label = f"{ref.hex().upper()} {core.describe_oad(ref)}"
        elif key == "record":
            rsd = self._build_rsd()
            rcsd = None
            text = self._page_edit("record").text().strip()
            if text:
                rcsd = core.build_rcsd([_parse_hex(tok) for tok in text.split()])
            frame = core.build_get_record(sa, ca, piid, ref, rsd, rcsd)
            label = f"{ref.hex().upper()} {core.describe_oad(ref)}"
        elif key == "action":
            data = _parse_hex(self._page_edit("action").text())
            frame = core.build_action(sa, ca, piid, ref, data)
            label = f"{item.oi:04X}H {item.name} - {leaf['name']}"
        else:
            raise ValueError(f"未知分页 {key}")

        row = self._add_info_row("等待中", label)
        return {"frame": frame, "label": label, "row": row, "attempt": 0,
                "kind": key, "specials": ()}

    def _build_rsd(self) -> bytes:
        core = _core()
        state = self._pages["record"]
        choice = int(state["combo_rsd"].currentData() or 0)
        kwargs = {
            "oad": _parse_hex(state["edit_rsd_oad"].text()),
            "value": _parse_hex(state["edit_rsd_value"].text()),
            "start": _parse_hex(state["edit_rsd_start"].text()),
            "end": _parse_hex(state["edit_rsd_end"].text()),
            "interval": _parse_hex(state["edit_rsd_interval"].text()),
            "n": state["spin_rsd_n"].value(),
        }
        return core.build_rsd(choice, **kwargs)

    def _send_next(self) -> None:
        if self._stopped:
            return
        if not self._queue:
            if self.chk_loop.isChecked() and self._channel.ready()[0]:
                try:
                    self._queue = list(self._build_entries())
                except (ImportError, ValueError) as exc:
                    self._log(f"[失败] 循环重发组帧失败：{exc}", "fail")
                    self._set_running(False)
                    return
                if self._queue:
                    self._next_timer.start(60)
                    return
            self._log("[信息] 本轮发送完成", "info")
            self._set_running(False)
            return

        entry = self._queue.pop(0)
        frame = entry["frame"]
        sent, reason = self._send_frame(frame)
        if not sent:
            # 单帧发不出去（如蓝牙一次写上限超限）：记失败并继续下一条，
            # 不静默、不中止整批（现场常见某几条超长、其余能发）。
            self._mark_info_row(entry.get("row"), "失败", {"reason": reason})
            self._log(f"[失败] {entry['label']}：{reason}", "fail")
            self._next_timer.start(60)
            return

        self._tx_count += 1
        self._update_txrx()
        self._add_raw_row("TX", frame)
        self._log(f"[TX] {_fmt(frame, 200)}", "tx")
        self._log(f"     {entry['label']}", "hint")
        self._log_detail(frame, "发送帧结构")
        self._current = entry
        self._awaiting = True
        self._reply_timer.start(max(100, self.spin_timeout.value()))

    def _on_reply_timeout(self) -> None:
        if not self._awaiting or self._current is None:
            return
        entry = self._current
        retries = self.spin_retries.value()
        entry["attempt"] = int(entry.get("attempt", 0)) + 1
        if entry["attempt"] <= retries:
            self._log(f"[超时] {entry['label']} 无响应，第 {entry['attempt']} 次重发", "warn")
            resent, reason = self._send_frame(entry["frame"])
            if not resent:
                self._mark_info_row(entry.get("row"), "失败", {"reason": reason})
                self._log(f"[失败] 重发不出去：{reason}", "fail")
                self._awaiting = False
                self._current = None
                self._next_timer.start(60)
                return
            self._tx_count += 1
            self._update_txrx()
            self._add_raw_row("TX", entry["frame"])
            self._reply_timer.start(max(100, self.spin_timeout.value()))
            return
        self._mark_info_row(entry.get("row"), "超时",
                            {"reason": f"{self.spin_timeout.value()}ms 内无响应"})
        self._log(f"[超时] {entry['label']} 无响应（已重发 {retries} 次）", "fail")
        self._awaiting = False
        self._current = None
        self._next_timer.start(60)

    def _on_stop(self) -> None:
        self._stopped = True
        self._queue.clear()
        self._reply_timer.stop()
        self._next_timer.stop()
        if self._current is not None and self._awaiting:
            self._mark_info_row(self._current.get("row"), "已终止", {"reason": "用户终止"})
        self._awaiting = False
        self._current = None
        self._set_running(False)
        self._log("[信息] 已终止发送", "warn")

    def _set_running(self, running: bool) -> None:
        self.btn_send.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.chk_loop.setEnabled(not running)
        self.chk_list.setEnabled(not running)

    # ==================================================================
    # 顶部固定动作（读/写地址、读/写时间、建立连接）
    # ==================================================================

    def _run_single(self, frame: bytes, label: str, specials: Sequence[str] = ()) -> None:
        """把一个固定动作塞进队列发出去（与「发送」同一套状态机）。"""
        ok, reason = self._channel.ready()
        if not ok:
            QMessageBox.information(self, "发送通道未就绪", reason)
            return
        self._stopped = False
        row = self._add_info_row("等待中", label)
        self._queue = [{"frame": frame, "label": label, "row": row, "attempt": 0,
                        "kind": "quick", "specials": tuple(specials)}]
        self._set_running(True)
        self._send_next()

    def _on_read_address(self) -> None:
        try:
            core = _core()
            frame = core.quick_read_address(self._sa_bytes(), self.spin_ca.value(), self._piid_byte())
        except (ImportError, ValueError) as exc:
            self._warn_build(exc)
            return
        self._run_single(frame, "读通信地址（OAD 40010200）", ("read_addr",))

    def _on_write_address(self) -> None:
        text = self.edit_write_addr.text().strip()
        if not text:
            QMessageBox.information(self, "缺少参数", "请先填「写地址」（要写入的地址，hex）。")
            return
        try:
            core = _core()
            new_addr = core.address_hex_to_bytes(text, self._sa_len())
            frame = core.quick_write_address(
                self._sa_bytes(), self.spin_ca.value(), self._piid_byte(), new_addr)
        except (ImportError, ValueError) as exc:
            self._warn_build(exc)
            return
        self._run_single(frame, f"写通信地址 → {new_addr.hex().upper()}", ("write_addr",))

    def _on_read_datetime(self) -> None:
        try:
            core = _core()
            frame = core.quick_read_datetime(self._sa_bytes(), self.spin_ca.value(), self._piid_byte())
        except (ImportError, ValueError) as exc:
            self._warn_build(exc)
            return
        self._run_single(frame, "读日期时间（OAD 40000200）", ("read_time",))

    def _on_write_datetime(self) -> None:
        when = self._write_datetime()
        if when is None:
            return
        try:
            core = _core()
            frame = core.quick_write_datetime(
                self._sa_bytes(), self.spin_ca.value(), self._piid_byte(), when)
        except (ImportError, ValueError) as exc:
            self._warn_build(exc)
            return
        self._run_single(frame, f"写日期时间 → {core.date_time_text(when)}", ("write_time",))

    def _on_connect(self) -> None:
        try:
            core = _core()
            frame = core.quick_connect(self._sa_bytes(), self.spin_ca.value(), 0)
        except (ImportError, ValueError) as exc:
            self._warn_build(exc)
            return
        self._run_single(frame, "建立应用连接（CONNECT-Request）", ())

    def _write_datetime(self) -> Optional[datetime]:
        """写时间的目标时刻：勾了「系统时间」或留空 ⇒ 本机当前时间。"""
        if self.chk_system_time.isChecked():
            return datetime.now()
        text = self.edit_write_time.text().strip()
        if not text:
            return datetime.now()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        QMessageBox.warning(self, "时间格式不对",
                            f"「写时间」= {text}\n请用 YYYY-MM-DD HH:MM:SS 格式（留空=系统时间）。")
        return None

    def _handle_special(self, entry: dict, frame: bytes, info: dict) -> None:
        """固定动作的响应副作用：回填读到的地址/时间。"""
        specials = entry.get("specials") or ()
        if not specials:
            return
        try:
            core = _core()
        except ImportError:
            return
        if "read_addr" in specials and info.get("ok") is True:
            addr = core.extract_address(frame)
            if addr:
                self.edit_read_addr.setText(addr)
                self.edit_sa.setText(addr)
                self._log(f"      → 设备地址 = {addr}（已回填「服务器地址」）", "ok")
                if not self.edit_write_addr.text().strip():
                    self.edit_write_addr.setText(addr)
                self._schedule_save()
            else:
                self._log("      → 响应里没找到通信地址（OAD 不是 40010200？）", "warn")
        if "read_time" in specials and info.get("ok") is True:
            when = core.extract_date_time(frame)
            if when:
                self.edit_read_time.setText(core.date_time_text(when))
                self._log(f"      → 设备时间 = {core.date_time_text(when)}", "ok")

    def _warn_build(self, exc: Exception) -> None:
        if isinstance(exc, ImportError):
            QMessageBox.warning(self, "缺少依赖",
                                f"无法组帧：{exc}\n\n请执行：pip install crcmod")
        else:
            QMessageBox.warning(self, "参数不完整", str(exc))

    # ==================================================================
    # 树 / 参数联动
    # ==================================================================

    def _active_key(self) -> str:
        index = self.tabs.currentIndex()
        if 0 <= index < len(PAGES):
            return PAGES[index][0]
        return PAGES[0][0]

    def _page_edit(self, key: str) -> QLineEdit:
        state = self._ensure_page(key)
        return state["edit_extra"]

    def _current_item(self, key: str):
        state = self._pages.get(key)
        if not state:
            return None
        return state.get("item")

    def _leaf_from_node(self, key: str, node) -> Optional[dict]:
        """树节点 → 叶子描述（无报文标识的分类节点返回 None）。"""
        raw = node.data(0, Qt.UserRole) if node is not None else None
        if raw is None:
            return None
        core = _core()
        item = core.find_item(int(node.data(0, Qt.UserRole + 1) or 0))
        if item is None:
            return None
        return {"item": item,
                "ident": int(node.data(0, Qt.UserRole + 2) or 0),
                "name": str(node.data(0, Qt.UserRole + 3) or ""),
                "index": int(node.data(0, Qt.UserRole + 4) or 0),
                "raw": bytes(raw), "node": node}

    def _targets(self, key: str) -> List[dict]:
        """待发目标：所有**勾选**的叶子（一个都没勾则用当前选中叶子）。"""
        state = self._pages.get(key)
        if not state:
            raise ValueError("当前页尚未构建")
        out: List[dict] = []
        tree = state["tree"]
        for i in range(tree.topLevelItemCount()):
            cat = tree.topLevelItem(i)
            for j in range(cat.childCount()):
                group = cat.child(j)
                for k in range(group.childCount()):
                    leaf = group.child(k)
                    if leaf.checkState(0) == Qt.Checked:
                        desc = self._leaf_from_node(key, leaf)
                        if desc is not None:
                            out.append(desc)
        if out:
            return out
        cur = state.get("leaf")
        return [cur] if cur else []

    def _current_ref(self, key: str, leaf) -> bytes:
        """当前叶子要下发的标识：OAD（read/set/record）或 OMD（action）。

        优先级：**覆盖框** > 叶子自带字节（索引取「元素索引」spin，仅 OAD 有意义）。
        覆盖不合法（非 4 字节）直接抛 —— 预览与发送都会显示 ⚠，不静默退回。
        """
        state = self._pages.get(key) or {}
        edit = state.get("edit_oad")
        text = edit.text().strip() if edit is not None else ""
        if text:
            raw = _core().parse_hex(text)
            if len(raw) != 4:
                raise ValueError(f"OAD/OMD 覆盖必须是 4 字节，当前 {len(raw)} 字节")
            return raw
        if isinstance(leaf, dict):
            core = _core()
            base = bytes(leaf["raw"])
            if key != "action":
                spin = state.get("spin_index")
                index = int(spin.value()) if spin is not None else int(leaf.get("index", 0))
                # 索引以 spin 为准（选中叶子时它已被同步成该叶子的元素索引）
                return core.make_oad(int.from_bytes(base[:2], "big"), base[2], index)
            return base
        return leaf.oad()

    def _current_ref(self, key: str, leaf) -> bytes:
        """当前叶子要下发的标识：OAD（read/set/record）或 OMD（action）。

        优先级：**覆盖框** > 叶子自带字节（索引取「元素索引」spin，仅 OAD 有意义）。
        覆盖不合法（非 4 字节）直接抛 —— 预览与发送都会显示 ⚠，不静默退回。
        """
        state = self._pages.get(key) or {}
        edit = state.get("edit_oad")
        text = edit.text().strip() if edit is not None else ""
        if text:
            raw = _core().parse_hex(text)
            if len(raw) != 4:
                raise ValueError(f"OAD/OMD 覆盖必须是 4 字节，当前 {len(raw)} 字节")
            return raw
        if isinstance(leaf, dict):
            core = _core()
            base = bytes(leaf["raw"])
            if key != "action":
                spin = state.get("spin_index")
                index = int(spin.value()) if spin is not None else int(leaf.get("index", 0))
                # 索引以 spin 为准（选中叶子时它已被同步成该叶子的元素索引）
                return core.make_oad(int.from_bytes(base[:2], "big"), base[2], index)
            return base
        return leaf.oad()

    def _attr_of(self, key: str, item) -> int:
        state = self._pages.get(key) or {}
        combo = state.get("combo_attr")
        if combo is not None and combo.count():
            value = combo.currentData()
            if value is not None:
                return int(value)
        return item.default_attr

    def _index_of(self, key: str, item) -> int:
        state = self._pages.get(key) or {}
        spin = state.get("spin_index")
        return int(spin.value()) if spin is not None else 0

    def _on_tree_selection(self, key: str) -> None:
        """选中一个叶子 → 回填「当前项」（叶子自带具体 OAD/OMD + 属性/方法名）。"""
        state = self._pages.get(key)
        if not state:
            return
        picks = state["tree"].selectedItems()
        node = picks[0] if picks else None
        raw = node.data(0, Qt.UserRole) if node is not None else None
        if raw is None:
            return                       # 选到的是分类/子类节点（没有报文标识）
        core = _core()
        item = core.find_item(int(node.data(0, Qt.UserRole + 1) or 0))
        if item is None:
            return
        ident = int(node.data(0, Qt.UserRole + 2) or 0)
        name = str(node.data(0, Qt.UserRole + 3) or "")
        state["item"] = item
        state["leaf"] = {"item": item, "ident": ident, "name": name,
                         "index": int(node.data(0, Qt.UserRole + 4) or 0),
                         "raw": bytes(raw), "node": node}

        state["lbl_name"].setText(f"{item.oi:04X}H  {item.name}")
        state["lbl_cls"].setText(
            f"接口类：{item.class_name}（class {item.class_id}）· "
            f"{'方法' if key == 'action' else '属性'} {ident}：{name}")

        combo = state["combo_attr"]
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(f"{ident}  {name}", ident)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

        # 「元素索引」跟着叶子走：A相电压那条是索引 1（§7.3.5 01H=第一个元素），
        # 其它页仍可手改（只影响选中这一条，并同步改写叶子文案）
        if state.get("spin_index") is not None:
            state["spin_index"].blockSignals(True)
            state["spin_index"].setValue(int(state["leaf"].get("index", 0)))
            state["spin_index"].blockSignals(False)
        self._refresh_preview(key)

    def _on_tab_changed(self, index: int) -> None:
        if not (0 <= index < len(PAGES)):
            return
        key = PAGES[index][0]
        self._ensure_page(key)
        self._schedule_save()
        self._refresh_preview()

    def _apply_filter(self, key: str, text: str) -> None:
        """按「名称 / OI 十六进制 / 接口类名 / 叶子文案（OAD·属性名）」显隐叶子。

        叶子是具体 OAD，所以「4001」既命中 OI 0x4001 的所有属性，也命中 4001xxxx 的 OAD；
        直接查叶子文案而不只查 OI —— 现场常按 OAD 前 4 位或属性名找项。
        """
        state = self._pages.get(key)
        if not state or not state["built"]:
            return
        core = _core()
        kw = str(text or "").strip().lower()
        try:
            matched = {it.oi for it in core.filter_items(text)}
        except Exception:                      # noqa: BLE001 —— 筛选绝不能把界面弄崩
            matched = set()
        tree = state["tree"]
        visible = 0
        for i in range(tree.topLevelItemCount()):
            cat = tree.topLevelItem(i)
            cat_hit = False
            for j in range(cat.childCount()):
                group = cat.child(j)
                group_hit = False
                for k in range(group.childCount()):
                    leaf = group.child(k)
                    if not kw:
                        hit = True
                    else:
                        oi = int(leaf.data(0, Qt.UserRole + 1) or 0)
                        hit = (oi in matched) or (kw in leaf.text(0).lower())
                    leaf.setHidden(not hit)
                    if hit:
                        group_hit = True
                        visible += 1
                group.setHidden(not group_hit)
                cat_hit = cat_hit or group_hit
            cat.setHidden(not cat_hit)
        state["counter"].setText(f"{visible} / {tree_leaf_count(state)} 条 OAD")

    def _set_all_checked(self, key: str, checked: bool) -> None:
        state = self._pages.get(key)
        if not state or not state["built"]:
            return
        tree = state["tree"]
        tree.blockSignals(True)
        for i in range(tree.topLevelItemCount()):
            cat = tree.topLevelItem(i)
            if cat.isHidden():
                continue
            for j in range(cat.childCount()):
                group = cat.child(j)
                if group.isHidden():
                    continue
                for k in range(group.childCount()):
                    leaf = group.child(k)
                    if leaf.isHidden():
                        continue
                    leaf.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        tree.blockSignals(False)
        self._refresh_preview()

    def _sync_rsd(self, key: str) -> None:
        state = self._pages.get(key)
        if not state:
            return
        choice = int(state["combo_rsd"].currentData() or 0)
        need_oad = choice in (1, 2)
        need_value = choice == 1
        need_range = choice == 2
        need_n = choice in (9, 10)
        state["edit_rsd_oad"].setEnabled(need_oad)
        state["edit_rsd_value"].setEnabled(need_value)
        state["edit_rsd_start"].setEnabled(need_range)
        state["edit_rsd_end"].setEnabled(need_range)
        state["edit_rsd_interval"].setEnabled(need_range)
        state["spin_rsd_n"].setEnabled(need_n)
        self._refresh_preview(key)

    def _refresh_preview(self, key: Optional[str] = None) -> None:
        """重算某一页的「当前 OAD + 帧预览」，并同步该叶子的简要信息文案。"""
        # 「线上 SA」与本页无关，**先**刷新：不能因为目标页还没建好就连地址回显都不更新
        self._refresh_sa_wire()
        key = key or self._active_key()
        state = self._pages.get(key)
        if not state:
            return
        leaf = state.get("leaf")
        if not leaf:
            state["preview"].setPlainText("（在左侧分类树里选一个对象）")
            state["lbl_oid"].setText("—")
            return
        try:
            core = _core()
        except ImportError as exc:
            state["preview"].setPlainText(f"缺少依赖：{exc}")
            return

        sa = self._sa_bytes()
        ca = self.spin_ca.value()
        piid = self._piid_byte()
        item = leaf["item"]
        lines: List[str] = []
        try:
            ref = self._current_ref(key, leaf)
            if key != "action":
                state["lbl_oid"].setText(f"OAD {ref.hex().upper()} · {core.describe_oad(ref)}")
            else:
                state["lbl_oid"].setText(
                    f"OMD {ref.hex().upper()} · {item.oi:04X}H {item.name} - {leaf['name']}")
            self._sync_leaf_text(key, state, leaf, ref, piid)
            if key == "read":
                lines.append(_fmt(core.build_get(sa, ca, piid, ref)))
            elif key == "set":
                data = _parse_hex(state["edit_extra"].text()) if state["edit_extra"] else b""
                if not data:
                    lines.append("（填「数据」后显示可下发的整帧）")
                else:
                    lines.append(_fmt(core.build_set(sa, ca, piid, ref, data)))
            elif key == "record":
                rsd = self._build_rsd()
                rcsd = None
                text = state["edit_extra"].text().strip()
                if text:
                    rcsd = core.build_rcsd([_parse_hex(tok) for tok in text.split()])
                lines.append(_fmt(core.build_get_record(sa, ca, piid, ref, rsd, rcsd)))
            else:
                data = _parse_hex(state["edit_extra"].text()) if state["edit_extra"] else b""
                lines.append(_fmt(core.build_action(sa, ca, piid, ref, data)))
        except ValueError as exc:
            lines.append(f"⚠ {exc}")
        except Exception as exc:                    # noqa: BLE001 —— 预览不能把界面弄崩
            lines.append(f"⚠ {type(exc).__name__}: {exc}")
        state["preview"].setPlainText("\n".join(lines) or "—")

    def _sync_leaf_text(self, key: str, state: dict, leaf: dict, ref: bytes,
                        piid: int) -> None:
        """把「元素索引 / PIID」的变化同步到该叶子的简要信息（只改选中这一条）。"""
        node = leaf.get("node")
        if node is None:
            return
        core = _core()
        try:
            if key == "action":
                node.setText(0, core.omd_label(ref, leaf["name"], piid))
                return
            spin = state.get("spin_index")
            index = int(spin.value()) if spin is not None else 0
            node.setText(0, core.leaf_label(ref, leaf["name"], index, piid))
        except Exception:                            # noqa: BLE001 —— 文案失败不影响发送
            pass

    def _refresh_sa_wire(self) -> None:
        """回显线上 SA 字节（地址体逆序 + 特征字节）—— 输入非法时给 ⚠ 而不是抛异常。"""
        try:
            sa = self._sa_bytes()
        except (ImportError, ValueError) as exc:
            self.lbl_sa_wire.setText(f"⚠ {exc}")
            return
        self.lbl_sa_wire.setText(f"{sa.hex(' ').upper()}（{len(sa)}B）")

    def _on_piid_changed(self) -> None:
        """服务序号 / 优先级变了：**所有已建树**的叶子文案都要跟着改。

        叶子文案里写着「优先级及序号=XX」，它表示「点这条会用什么 PIID 发出」——
        不跟着改就是对用户撒谎。4500 余条 setText 约 30ms（实测），可以接受。
        """
        piid = self._piid_byte()
        core = _core()
        try:
            for key, state in self._pages.items():
                tree = state.get("tree")
                if tree is None or not state.get("built"):
                    continue
                for i in range(tree.topLevelItemCount()):
                    cat = tree.topLevelItem(i)
                    for j in range(cat.childCount()):
                        group = cat.child(j)
                        for k in range(group.childCount()):
                            leaf = group.child(k)
                            raw = leaf.data(0, Qt.UserRole)
                            name = str(leaf.data(0, Qt.UserRole + 3) or "")
                            if not raw or not name:
                                continue
                            if key == "action":
                                leaf.setText(0, core.omd_label(bytes(raw), name, piid))
                            else:
                                leaf.setText(0, core.leaf_label(bytes(raw), name, 0, piid))
        except Exception:                       # noqa: BLE001 —— 文案失败不影响发送
            pass
        self._refresh_preview()
        self._schedule_save()

    def _on_sa_type_changed(self) -> None:
        addr_type = int(self.combo_sa_type.currentData() or 0)
        is_broadcast = addr_type == 3
        self.edit_sa.setEnabled(not is_broadcast)
        self.combo_sa_len.setEnabled(not is_broadcast)
        self.combo_sa_logic.setEnabled(not is_broadcast)
        if is_broadcast:
            self.edit_sa.setText("AA")
        elif self.edit_sa.text().strip().upper() == "AA":
            self.edit_sa.setText("11" * max(1, self._sa_len()))
        self._refresh_preview()
        self._schedule_save()

    def _on_sa_len_changed(self) -> None:
        addr_len = self._sa_len()
        text = self.edit_sa.text().strip()
        try:
            data = _core().address_hex_to_bytes(text, addr_len)
        except ValueError:
            data = b""
        if data:
            self.edit_sa.setText(data.hex().upper())
        self._refresh_preview()
        self._schedule_save()

    def _on_read_addr_edited(self) -> None:
        text = self.edit_read_addr.text().strip()
        if text:
            self.edit_sa.setText(text)
            if not self.edit_write_addr.text().strip():
                self.edit_write_addr.setText(text)

    def _sa_len(self) -> int:
        return int(self.combo_sa_len.currentData() or 6)

    def _sa_bytes(self) -> bytes:
        core = _core()
        addr_type = int(self.combo_sa_type.currentData() or 0)
        if addr_type == 3:
            return core.BROADCAST_SA
        return core.sa_from_text(addr_type, int(self.combo_sa_logic.currentData() or 0),
                                 self._sa_len(), self.edit_sa.text())

    def _piid_byte(self) -> int:
        return _core().build_piid(self.spin_piid.value(), int(self.combo_priority.currentData() or 0))

    # ==================================================================
    # 地址簿
    # ==================================================================

    def _refresh_book(self) -> None:
        """地址簿：单地址（可增删）+ 广播/组/通配（固定条目）。"""
        self.tree_book.clear()
        single = QTreeWidgetItem(["单地址"])
        single.setFlags(Qt.ItemIsEnabled)
        self.tree_book.addTopLevelItem(single)
        for text in self._book_entries():
            leaf = QTreeWidgetItem([text])
            leaf.setData(0, Qt.UserRole, text)
            single.addChild(leaf)
        for name, text in (("广播地址", "AA"), ("组地址", "组地址（需在左侧设逻辑地址）"),
                           ("通配地址", "45AAAAAAAAAAAA")):
            node = QTreeWidgetItem([name])
            node.setFlags(Qt.ItemIsEnabled)
            self.tree_book.addTopLevelItem(node)
            leaf = QTreeWidgetItem([text])
            leaf.setData(0, Qt.UserRole, text)
            node.addChild(leaf)
        self.tree_book.expandAll()

    def _book_entries(self) -> List[str]:
        data = getattr(self, "_book", [])
        return [str(x) for x in data if str(x).strip()]

    def _on_book_add(self) -> None:
        text = self.edit_sa.text().strip().upper()
        if not text:
            return
        book = self._book_entries()
        if text not in book:
            book.append(text)
            self._book = book
            self._refresh_book()
            self._schedule_save()

    def _on_book_remove(self) -> None:
        items = self.tree_book.selectedItems()
        if not items:
            return
        text = items[0].data(0, Qt.UserRole)
        if not text:
            return
        book = [x for x in self._book_entries() if x != str(text)]
        self._book = book
        self._refresh_book()
        self._schedule_save()

    def _on_book_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        text = item.data(0, Qt.UserRole)
        if not text:
            return
        text = str(text)
        if text == "AA":
            self.combo_sa_type.setCurrentIndex(self.combo_sa_type.findData(3))
            return
        if text.startswith("组地址") or len(text) == 14:
            self.combo_sa_type.setCurrentIndex(self.combo_sa_type.findData(1))
        else:
            self.combo_sa_type.setCurrentIndex(self.combo_sa_type.findData(0))
        self.edit_sa.setText(text)
        self._refresh_preview()

    # ==================================================================
    # 信息表 / 报文表 / 日志
    # ==================================================================

    def _add_info_row(self, result: str, message: str) -> int:
        row = self.table_info.rowCount()
        self.table_info.insertRow(row)
        self.table_info.setItem(row, 0, QTableWidgetItem(self._now()))
        self.table_info.setItem(row, 1, QTableWidgetItem(result))
        self.table_info.setItem(row, 2, QTableWidgetItem(message))
        if self.table_info.rowCount() > 2000:
            self.table_info.removeRow(0)
            row -= 1
        self.table_info.scrollToBottom()
        return row

    def _mark_info_row(self, row: Optional[int], result: str, info: dict) -> None:
        if row is None or not (0 <= row < self.table_info.rowCount()):
            return
        self.table_info.setItem(row, 1, QTableWidgetItem(str(result)))
        reason = str(info.get("reason") or "")
        title = str(info.get("title") or "")
        extra = reason or title
        base_item = self.table_info.item(row, 2)
        base = base_item.text() if base_item else ""
        if extra and extra not in base:
            self.table_info.setItem(row, 2, QTableWidgetItem(f"{base}｜{extra}"))
        color = {"成功": "#0A7D28", "失败": "#B42318", "超时": "#B42318",
                 "无法判定": "#9A6700"}.get(str(result))
        if color:
            item = self.table_info.item(row, 1)
            if item is not None:
                item.setForeground(QColor(color))

    def _add_raw_row(self, direction: str, frame: bytes) -> None:
        row = self.table_raw.rowCount()
        self._raw_frames[int(row)] = bytes(frame)
        self.table_raw.insertRow(row)
        self.table_raw.setItem(row, 0, QTableWidgetItem(self._now()))
        self.table_raw.setItem(row, 1, QTableWidgetItem(direction))
        self.table_raw.setItem(row, 2, QTableWidgetItem(str(len(frame))))
        self.table_raw.setItem(row, 3, QTableWidgetItem(_fmt(frame, 200)))
        if self.table_raw.rowCount() > RAW_ROW_LIMIT:
            self.table_raw.removeRow(0)
            # 行号整体前移 1：映射必须重建（否则双击会送上一帧，现场极难发现）
            self._raw_frames = {i - 1: v for i, v in self._raw_frames.items() if i > 0}
        self.table_raw.scrollToBottom()

    def _log_transaction(self, entry: dict, frame: bytes, info: dict, level: str) -> None:
        self._log(f"[RX] {_fmt(frame, 200)}", "tx")
        title = info.get("title") or "（未识别）"
        self._log(f"  → {entry['label']}：{title}", level)
        for line in (info.get("lines") or []):
            self._log(f"      {line}", "info")
        self._log_detail(frame, "帧结构")
        self._log_dar(entry, info)

    def _log_detail(self, frame: bytes, title: str = "帧结构") -> None:
        """逐字段打印整帧结构（= 单帧解析页那张表，解析全部由解析器给）。"""
        if not self.chk_detail.isChecked():
            return
        try:
            core = _core()
            lines = core.detail_lines(frame, title=title)
        except ImportError as exc:
            self._log(f"  （明细不可用：{exc}）", "warn")
            return
        for line in lines:
            self._log(f"    {line}", "hint")

    def _log_dar(self, entry: dict, info: dict) -> None:
        """DAR 非 0 时补一行可读原因（解析器已给中文说明，直接透传）。"""
        dar = info.get("dar")
        reason = str(info.get("reason") or "")
        if dar not in (None, 0) and reason:
            self._log(f"  DAR={dar}：{reason}", "fail")

    def _log(self, text: str, level: str = "info") -> None:
        palette = self._palette
        color = palette.get(level, palette["fg"])
        safe = (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        self.log_text.appendHtml(
            f'<span style="color:{color};white-space:pre;">{safe}</span>')

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _update_txrx(self) -> None:
        self.lbl_txrx.setText(f"TX {self._tx_count} · RX {self._rx_count}")

    def _on_clear(self) -> None:
        self.log_text.clear()
        self.table_info.setRowCount(0)
        self.table_raw.setRowCount(0)
        self._raw_frames.clear()

    def _on_edit_current(self) -> None:
        """「编辑」：把当前项的 OAD/OMD 填进覆盖字段，就地改一两个字节再发。

        预置库覆盖不了厂家自定义对象，但现场常只需改属性号/索引；把当前值填进可编辑
        字段比「去另一页重新组帧」快得多（真要自由组帧仍走「协议组帧」页）。
        """
        key = self._active_key()
        state = self._pages.get(key)
        leaf = (state or {}).get("leaf")
        if not state or not leaf:
            QMessageBox.information(self, "未选择", "请先在分类树里选一条 OAD。")
            return
        try:
            ref = self._current_ref(key, leaf)
        except ValueError as exc:
            QMessageBox.warning(self, "无法取值", str(exc))
            return
        text = ref.hex().upper()
        state["edit_oad"].setText(text)
        state["edit_oad"].setFocus()
        state["edit_oad"].selectAll()
        self._log(f"[信息] 已把 {text} 填入覆盖框 —— 改完直接「发送」；清空则回到按属性生成",
                  "info")

    # ==================================================================
    # 落盘
    # ==================================================================

    def _schedule_save(self) -> None:
        if hasattr(self, "_save_timer"):
            self._save_timer.start()

    def _collect_settings(self) -> dict:
        data = dict(DEFAULTS)
        data.update({
            "sa_type": int(self.combo_sa_type.currentData() or 0),
            "sa_logic": int(self.combo_sa_logic.currentData() or 0),
            "sa_len": self._sa_len(),
            "sa_text": self.edit_sa.text(),
            "write_text": self.edit_write_addr.text(),
            "ca": self.spin_ca.value(),
            "piid": self.spin_piid.value(),
            "priority": int(self.combo_priority.currentData() or 0),
            "timeout_ms": self.spin_timeout.value(),
            "retries": self.spin_retries.value(),
            "channel": self._channel.channel,
            "list_mode": self.chk_list.isChecked(),
            "loop_mode": self.chk_loop.isChecked(),
            "detail": self.chk_detail.isChecked(),
            "page": self._active_key(),
            "read_time_text": self.edit_read_time.text(),
            "write_time_text": self.edit_write_time.text(),
            "use_system_time": self.chk_system_time.isChecked(),
            "address_book": self._book_entries(),
            "version": CONFIG_VERSION,
        })
        for key in self._pages:
            state = self._pages[key]
            prefix = f"{key}_"
            combo = state["combo_attr"]
            if combo.count():
                data[prefix + "attr"] = int(combo.currentData() or 0)
            data[prefix + "index"] = state["spin_index"].value()
            if state["edit_extra"] is not None:
                data[prefix + "extra"] = state["edit_extra"].text()
            data[prefix + "oad"] = state["edit_oad"].text()
        state = self._pages.get("record")
        if state:
            data.update({
                "rsd_choice": int(state["combo_rsd"].currentData() or 0),
                "rsd_oad": state["edit_rsd_oad"].text(),
                "rsd_value": state["edit_rsd_value"].text(),
                "rsd_start": state["edit_rsd_start"].text(),
                "rsd_end": state["edit_rsd_end"].text(),
                "rsd_interval": state["edit_rsd_interval"].text(),
                "rsd_n": state["spin_rsd_n"].value(),
            })
        return data

    def _save_persisted(self) -> bool:
        try:
            payload = json.dumps(self._collect_settings(), ensure_ascii=False, indent=2)
        except (TypeError, ValueError, RuntimeError):
            return False
        tmp = f"{self._config_path}.tmp"
        try:
            parent = os.path.dirname(self._config_path) or "."
            os.makedirs(parent, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self._config_path)
            return True
        except OSError:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            return False

    def _load_persisted(self) -> None:
        raw = None
        try:
            with open(self._config_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            raw = None
        if not isinstance(raw, dict):
            raw = {}
        data = dict(DEFAULTS)
        data.update({k: v for k, v in raw.items() if k in data or k.endswith(("_attr", "_index", "_extra"))})

        widgets = [
            self.combo_sa_type, self.combo_sa_logic, self.combo_sa_len,
            self.edit_sa, self.spin_ca, self.spin_piid, self.combo_priority,
            self.spin_timeout, self.spin_retries, self.chk_list, self.chk_loop,
            self.edit_read_time, self.edit_write_time, self.chk_system_time,
            self.edit_write_addr, self.edit_read_addr,
        ]
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.combo_sa_type.setCurrentIndex(
                max(0, self.combo_sa_type.findData(int(data.get("sa_type", 0)))))
            self.combo_sa_logic.setCurrentIndex(
                max(0, self.combo_sa_logic.findData(int(data.get("sa_logic", 0)))))
            self.combo_sa_len.setCurrentIndex(
                max(0, self.combo_sa_len.findData(int(data.get("sa_len", 6)))))
            self.edit_sa.setText(str(data.get("sa_text") or DEFAULTS["sa_text"]))
            self.edit_write_addr.setText(str(data.get("write_text") or ""))
            self.edit_read_addr.setText(str(data.get("sa_text") or DEFAULTS["sa_text"]))
            self.spin_ca.setValue(_bounded(data.get("ca"), 0, 0, 255))
            self.spin_piid.setValue(_bounded(data.get("piid"), 0, 0, 63))
            self.combo_priority.setCurrentIndex(
                max(0, self.combo_priority.findData(int(data.get("priority", 0)))))
            self.spin_timeout.setValue(_bounded(data.get("timeout_ms"), 2000, 100, 60000))
            self.spin_retries.setValue(_bounded(data.get("retries"), 1, 0, 5))
            self.chk_list.setChecked(bool(data.get("list_mode")))
            self.chk_loop.setChecked(bool(data.get("loop_mode")))
            self.chk_detail.setChecked(bool(data.get("detail", True)))
            self.edit_read_time.setText(str(data.get("read_time_text") or ""))
            self.edit_write_time.setText(str(data.get("write_time_text") or ""))
            self.chk_system_time.setChecked(bool(data.get("use_system_time", True)))
        finally:
            for widget in widgets:
                widget.blockSignals(False)

        book = data.get("address_book")
        self._book = [str(x) for x in book] if isinstance(book, list) else []
        self._refresh_book()
        self._on_sa_type_changed()

        channel = ch.normalize_channel(data.get("channel"))
        index = self.combo_channel.findData(channel)
        if index >= 0:
            self.combo_channel.setCurrentIndex(index)      # 触发 set_channel
        self._refresh_channel_ui()

        page = str(data.get("page") or "read")
        for i, (key, _title) in enumerate(PAGES):
            if key == page:
                self.tabs.setCurrentIndex(i)
                break
        if "record" in self._pages:
            self._sync_rsd("record")


def _bounded(value, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return int(default)
