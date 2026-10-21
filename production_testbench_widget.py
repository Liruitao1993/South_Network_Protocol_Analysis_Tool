# -*- coding: utf-8 -*-
"""生产测试架页（类串口助手 + 测试架参数报文）。

页面构成（**三栏**，左右两栏可折叠、三栏宽度都可拖动；见
:meth:`ProductionTestbenchWidget._build_ui`）：

1. **发送配置（左栏，可折叠）**：5 条发送框，每条独立选 HEX / ASCII、独立勾选 checksum8
   并选落位方式（追加 / 覆盖末字节 / 插在 16H 前），一键发送；内容落盘。
2. **接收日志（中栏）**：HEX / ASCII 显示切换、时间戳开关、自动滚动、清空；窗口变宽时
   只有中栏跟着变宽（折叠左右栏也是把宽度让给它）。
3. **测试架参数（右栏，可折叠）**：47 项参数 + 6 字节地址域（现场参数表共 49 项，另 2 项在帧头），
   改动即时生成 75 字节整帧预览，可直接发送 / 复制；「恢复现场示例」一键回到现场样例帧的取值。

折叠交互：左右两栏标题行的**外沿**各有一个折叠按钮（左栏在左、右栏在右），折叠后只留
30 px 窄条（按钮 + 竖排栏名），再点一次展开并还原折叠前的三栏宽度；折叠状态与三栏宽度
一起落盘，重开程序保持。

约定（与 `serial_tool_widget` / `dlt698_upgrade_widget` 一致）：

- 串口**只借用主窗口共享的那一个** ``SerialWorker``（:meth:`set_serial_worker`），
  本页绝不开/关端口 —— 一个 COM 口只能被打开一次，各页各持句柄会互相抢口；
  端口与波特率在顶部「串口配置」设置。
- 落盘走 ``app_paths.data_path``（属性访问，便于测试 patch 到沙箱）。
- 组帧 / 校验 / 编解码全部在 :mod:`production_testbench_core`（纯逻辑、无 Qt），
  本模块只做界面与信号接线，便于 offscreen 单测。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QRegularExpression, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QRegularExpressionValidator, QTextCharFormat,
                           QTextCursor)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QScrollArea,
                               QSplitter, QToolButton, QVBoxLayout, QWidget)

import app_paths
import app_icons
import production_testbench_core as core

CONFIG_NAME = "production_testbench.json"

#: 日志配色（浅色 / 深色）。只影响此后写入的行（历史行保持写入时的颜色）。
LOG_PALETTES = {
    False: {
        "bg": "#FFFFFF", "fg": "#1F2328", "border": "#D0D7DE",
        "info": "#57606A", "tx": "#0969DA", "rx": "#1A7F37",
        "fail": "#CF222E", "hint": "#6E7781", "error": "#B35900",
    },
    True: {
        "bg": "#1E1E1E", "fg": "#D4D4D4", "border": "#3C3C3C",
        "info": "#9DA5B4", "tx": "#4FC1FF", "rx": "#4EC9B0",
        "fail": "#F48771", "hint": "#8B949E", "error": "#E3B341",
    },
}

#: 单行日志最多显示的字节数（超出只显示头尾，避免一条 4KB 回包刷屏）
LOG_BYTES_LIMIT = 512
LOG_MAX_BLOCKS = 5000
#: 日志合并刷新：收包密集时（10 kbps ≈ 1000 行/秒）逐行 insertText 会拖慢界面，
#: 先入队、每 100 ms 合并写一次；超过 300 行立即刷（避免高吞吐时延迟可见）。
LOG_FLUSH_MS = 100
LOG_FLUSH_MAX = 300

TIP_NOT_CONNECTED = "串口未连接：请在顶部「串口配置」中选择端口并连接（本页复用同一个串口）"
TIP_NO_SERIAL = "未接入串口线程（页面未初始化完成）"

#: 折叠后窄条宽度 / 展开时左右两栏的最小宽度（三栏可拖动，但不会窄到挤坏内容）
SIDE_COLLAPSED_WIDTH = 30
SIDE_MIN_LEFT = 330
SIDE_MIN_RIGHT = 360
#: 三栏初始宽度（左发送配置 / 中接收日志 / 右测试架参数）——与落盘默认值同源
SIDE_DEFAULT_SIZES = list(core.DEFAULT_LAYOUT_SIZES)

_MONO_FAMILIES = ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Courier New")

#: checksum8 落位方式在下拉框里的短标签（左栏较窄；完整文案见 core.CS_MODES 与 tooltip）
_CS8_SHORT_LABELS = {
    core.CS_MODE_APPEND: "追加",
    core.CS_MODE_REPLACE_LAST: "覆盖末字节",
    core.CS_MODE_BEFORE_END: "16H 前",
}


def _mono_font(point_size: int = 9, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies(list(_MONO_FAMILIES))
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(point_size)
    font.setBold(bold)
    return font


# ======================================================================
# 基础控件
# ======================================================================


class HexField(QLineEdit):
    """定长 HEX 输入框（1/2/3/4 字节）。

    - 只接受 HEX 字符与空格（其余按键被 validator 挡掉）
    - 失焦时自动重排成 ``AA BB CC`` 形式，短于/长于目标长度不做修补（由组帧时报具体字段）
    """

    changed = Signal()

    def __init__(self, size: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._size = max(1, int(size))
        self.setFont(_mono_font(9))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMaxLength(self._size * 3 - 1)
        unit_width = 20 if self._size <= 2 else 17
        self.setFixedWidth(26 + self._size * unit_width)
        self.setPlaceholderText(" ".join(["00"] * self._size))
        pattern = r"^[0-9A-Fa-f ]{0,%d}$" % (self._size * 3 - 1)
        self.setValidator(QRegularExpressionValidator(QRegularExpression(pattern), self))
        self.editingFinished.connect(self._normalize)
        self.textChanged.connect(lambda *_: self.changed.emit())

    # ── 取值 ──
    def hex_value(self) -> str:
        """紧凑大写 HEX（去空格）；可能短于/长于字段长度（组帧时校验）。"""
        return core.clean_hex(self.text()).upper()

    def is_complete(self) -> bool:
        return len(self.hex_value()) == self._size * 2

    def set_hex(self, text: object) -> None:
        value = core.clean_hex(str(text or "")).upper()
        self.setText(" ".join(value[i:i + 2] for i in range(0, len(value), 2)))

    # ── 内部 ──
    def _normalize(self) -> None:
        value = self.hex_value()
        formatted = " ".join(value[i:i + 2] for i in range(0, len(value), 2))
        if formatted != self.text():
            self.setText(formatted)


class SendBox(QGroupBox):
    """一条发送配置：名称 + 内容 + HEX/ASCII + checksum8 + 发送。

    ``send_requested`` 携带本框配置（:class:`production_testbench_core.SendBoxConfig`），
    由页面统一做「串口是否就绪 → 写串口 → 记日志」——本控件不碰串口。
    """

    send_requested = Signal(object)

    def __init__(self, index: int, parent: Optional[QWidget] = None):
        super().__init__(f"发送 {index + 1}", parent)
        self.index = index
        self._palette = LOG_PALETTES[False]
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText(f"名称（可选），如「读版本」")
        self.name_edit.setClearButtonEnabled(True)
        self.btn_clear_text = QPushButton("清空", self)
        self.btn_clear_text.setFixedWidth(52)
        self.btn_clear_text.clicked.connect(lambda: self.text_edit.clear())
        top.addWidget(self.name_edit, 1)
        top.addWidget(self.btn_clear_text)
        layout.addLayout(top)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setFont(_mono_font(9))
        self.text_edit.setPlaceholderText("HEX：68 AA 00 …（可带空格/换行）    ASCII：AT+CSQ")
        self.text_edit.setFixedHeight(46)
        self.text_edit.setTabChangesFocus(True)
        layout.addWidget(self.text_edit)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem("HEX", core.SEND_MODE_HEX)
        self.mode_combo.addItem("ASCII", core.SEND_MODE_ASCII)
        self.mode_combo.setFixedWidth(66)      # 左栏可拖窄，下拉不参与"最小宽度"竞争
        self.cs8_check = QCheckBox("CS8", self)
        self.cs8_check.setToolTip("勾选后发送前自动计算 8 位算术和并写入报文")
        self.cs8_mode = QComboBox(self)
        for key, label in core.CS_MODES:
            self.cs8_mode.addItem(_CS8_SHORT_LABELS.get(key, label), key)
            self.cs8_mode.setItemData(self.cs8_mode.count() - 1, label, Qt.ItemDataRole.ToolTipRole)
        self.cs8_mode.setFixedWidth(98)
        self.cs8_mode.setToolTip("校验字节的落位方式")
        self.cs8_mode.setEnabled(False)
        self.cs8_check.toggled.connect(self.cs8_mode.setEnabled)
        self.btn_send = QPushButton("发送", self)
        self.btn_send.setObjectName("PrimaryButton")
        self.btn_send.setFixedWidth(64)
        self.btn_send.clicked.connect(self._on_send)
        self.status = QLabel("就绪", self)
        self.status.setMinimumWidth(0)
        self.status.setStyleSheet("color: #6E7781;")

        bottom.addWidget(self.mode_combo)
        bottom.addWidget(self.cs8_check)
        bottom.addWidget(self.cs8_mode, 1)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.btn_send)
        layout.addLayout(bottom)

    # ── 配置读写 ──
    def config(self) -> core.SendBoxConfig:
        return core.SendBoxConfig(
            name=self.name_edit.text().strip(),
            text=self.text_edit.toPlainText(),
            mode=str(self.mode_combo.currentData() or core.SEND_MODE_HEX),
            cs8=self.cs8_check.isChecked(),
            cs8_mode=str(self.cs8_mode.currentData() or core.CS_MODE_APPEND),
        )

    def set_config(self, cfg: core.SendBoxConfig) -> None:
        self.name_edit.setText(cfg.name)
        self.text_edit.setPlainText(cfg.text)
        idx = self.mode_combo.findData(cfg.mode)
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.cs8_check.setChecked(bool(cfg.cs8))
        idx = self.cs8_mode.findData(cfg.cs8_mode)
        self.cs8_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self.cs8_mode.setEnabled(self.cs8_check.isChecked())

    def set_status(self, text: str, color: Optional[str] = None) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color or self._palette['hint']};")

    def set_connected(self, connected: bool) -> None:
        self.btn_send.setEnabled(bool(connected))
        self.btn_send.setToolTip("" if connected else TIP_NOT_CONNECTED)

    def restyle_for_theme(self, dark: bool) -> None:
        self._palette = LOG_PALETTES[bool(dark)]
        self.set_status(self.status.text())

    # ── 事件 ──
    def _on_send(self) -> None:
        self.send_requested.emit(self.config())


# ======================================================================
# 主页面
# ======================================================================


class SidePanel(QWidget):
    """可横向折叠的一栏（左/右）：标题 + 折叠按钮 + 内容区。

    折叠后只留一条 ``SIDE_COLLAPSED_WIDTH`` 宽的窄条（只剩折叠按钮），
    把宽度让给中间的接收日志；展开/折叠状态通过 ``collapsed_changed(True=已折叠)``
    通知页面调整三栏宽度（页面再调 ``QSplitter.setSizes``）。

    最小宽度由本控件自己管：折叠时 ``setFixedWidth`` 会同时压住 min/max，
    展开时必须把 min 恢复成 ``expanded_min_width``（页面不再二次设置，避免打架）。
    """

    collapsed_changed = Signal(bool)

    def __init__(self, title: str, side: str = "left",
                 parent: Optional[QWidget] = None, expanded: bool = True,
                 expanded_min_width: int = 320):
        super().__init__(parent)
        self._side = side if side in ("left", "right") else "left"
        self._collapsed = not expanded
        self._min_width = max(220, int(expanded_min_width))
        self._title = str(title)
        # 折叠窄条上竖排显示的短标题（取标题里括号前的部分，如「发送配置（5 条）」→「发送配置」）
        self._short_title = self._title.split("（")[0].split("(")[0].strip()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # 标题行放在固定高度的容器里：折叠后内容区隐藏时它也不会被拉高（否则按钮会跑到竖直中间）
        header_wrap = QWidget(self)
        header_wrap.setFixedHeight(26)
        header = QHBoxLayout(header_wrap)
        header.setContentsMargins(2, 0, 2, 0)
        header.setSpacing(4)
        self.btn_toggle = QToolButton(header_wrap)
        self.btn_toggle.setAutoRaise(True)
        self.btn_toggle.setFixedSize(24, 24)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle)
        self.title_label = QLabel(self._title, header_wrap)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        if self._side == "left":
            # 折叠按钮贴**外沿**（左栏在最左），避免看起来像中间日志栏的按钮
            header.addWidget(self.btn_toggle)
            header.addWidget(self.title_label, 1)
        else:
            header.addWidget(self.title_label, 1)
            header.addWidget(self.btn_toggle)
        root.addWidget(header_wrap)

        # 折叠窄条上的竖排短标题（一行一个字）
        self.vertical_label = QLabel("\n".join(self._short_title), self)
        self.vertical_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.vertical_label.setStyleSheet("color: #7A7A7A;")
        root.addWidget(self.vertical_label)

        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(4)
        root.addWidget(self.body, 1)

        self._apply(emit=False)

    # ── 对外 ──
    def toggle(self) -> None:
        self.set_expanded(self._collapsed)

    def is_expanded(self) -> bool:
        return not self._collapsed

    def set_expanded(self, expanded: bool, emit: bool = True) -> None:
        collapsed = not bool(expanded)
        changed = collapsed != self._collapsed
        self._collapsed = collapsed
        self._apply(emit=emit and changed)

    # ── 内部 ──
    def _apply(self, emit: bool) -> None:
        self.body.setVisible(not self._collapsed)
        self.title_label.setVisible(not self._collapsed)
        self.vertical_label.setVisible(self._collapsed)
        if self._collapsed:
            self.setFixedWidth(SIDE_COLLAPSED_WIDTH)
            icon = "chevron-right" if self._side == "left" else "chevron-left"
            action = "展开" if self._side == "left" else "展开"
        else:
            self.setMinimumWidth(self._min_width)
            self.setMaximumWidth(16777215)
            icon = "chevron-left" if self._side == "left" else "chevron-right"
            action = "折叠"
        self.btn_toggle.setIcon(app_icons.load_icon(icon))
        self.btn_toggle.setToolTip(f"{action}「{self._title}」")
        if emit:
            self.collapsed_changed.emit(self._collapsed)


class ProductionTestbenchWidget(QWidget):
    """生产测试架页。

    对外接口（主窗口只调这四个）：

    - :meth:`set_serial_worker` —— 注入共享串口线程（只订阅信号，不开/关端口）
    - :meth:`cleanup` —— 停表 + 断信号 + 落盘（幂等；不关串口）
    - :meth:`restyle_for_theme` —— 主题切换后刷新本页自定义配色
    - :meth:`current_frame_hex` —— 当前参数帧（测试/调试用；无 Qt 依赖的组帧在 core）
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._dark = False
        self._palette = LOG_PALETTES[False]
        self._serial_worker = None
        self._connected = False
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._param_widgets: Dict[str, object] = {}
        # 折叠前的三栏宽度（展开时还原；两侧都展开后清空，下次折叠重新记）
        self._sizes_before_collapse: Optional[List[int]] = None

        # 落盘路径用**属性访问**（测试可 patch `app_paths.data_path` 到沙箱）
        self._config_path = str(app_paths.data_path(CONFIG_NAME))
        self._config = core.default_config()

        # 落盘定时器必须先于控件创建（载入配置会触发 toggled/textChanged → schedule）
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_now)

        # 日志合并刷新队列（见 LOG_FLUSH_MS）
        self._pending_log: List[tuple] = []
        self._log_timer = QTimer(self)
        self._log_timer.setSingleShot(True)
        self._log_timer.setInterval(LOG_FLUSH_MS)
        self._log_timer.timeout.connect(self._flush_log)

        # 预览刷新防抖（49 个字段，逐键刷新会重复组帧）
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self._build_ui()
        self._load_now()
        self._apply_theme_style(self._dark)
        self._set_connected(False)      # 未注入串口前一律禁用发送（含 5 个发送框）
        self._refresh_preview()

    # ==================================================================
    # UI
    # ==================================================================
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ── 顶部状态条 ──
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.lbl_serial_state = QLabel("串口：未连接（端口/波特率在顶部「串口配置」设置）", self)
        self.lbl_serial_state.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_counters = QLabel("收 0 B / 发 0 B", self)
        self.lbl_counters.setStyleSheet("color: #6E7781;")
        status_row.addWidget(self.lbl_serial_state, 1)
        status_row.addWidget(self.lbl_counters)
        outer.addLayout(status_row)

        # ── 主体：左（发送配置）/ 中（接收日志）/ 右（测试架参数），三栏可拖动 ──
        self.split_columns = QSplitter(Qt.Orientation.Horizontal, self)
        self.split_columns.setChildrenCollapsible(False)   # 关掉「拖到 0」，折叠只走按钮

        self.left_panel = SidePanel("发送配置（5 条）", side="left", parent=self,
                                    expanded_min_width=SIDE_MIN_LEFT)
        self.left_panel.body_layout.addWidget(self._build_send_body(), 1)
        self.left_panel.collapsed_changed.connect(self._on_left_collapsed)

        self.log_group = self._build_log_panel()

        self.right_panel = SidePanel("测试架参数", side="right", parent=self,
                                     expanded_min_width=SIDE_MIN_RIGHT)
        self.right_panel.body_layout.addWidget(self._build_params_body(), 1)
        self.right_panel.collapsed_changed.connect(self._on_right_collapsed)

        self.split_columns.addWidget(self.left_panel)
        self.split_columns.addWidget(self.log_group)
        self.split_columns.addWidget(self.right_panel)
        self.split_columns.setStretchFactor(0, 0)
        self.split_columns.setStretchFactor(1, 1)          # 日志吃掉窗口变宽的余量
        self.split_columns.setStretchFactor(2, 0)
        self.split_columns.setSizes(list(SIDE_DEFAULT_SIZES))
        self.split_columns.splitterMoved.connect(lambda *_: self._schedule_save())
        outer.addWidget(self.split_columns, 1)

    # ── 左栏内容：5 条发送配置 ──
    def _build_send_body(self) -> QWidget:
        self.send_boxes: List[SendBox] = []
        inner = QWidget(self)
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(2, 2, 2, 2)
        inner_layout.setSpacing(6)
        for i in range(core.SEND_BOX_COUNT):
            sb = SendBox(i, inner)
            sb.send_requested.connect(self._on_send_box)
            inner_layout.addWidget(sb)
            self.send_boxes.append(sb)
        inner_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(inner)
        self.send_scroll = scroll
        return scroll

    # ── 中栏内容：接收日志 ──
    def _build_log_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 0, 2, 2)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.lbl_log_title = QLabel("接收日志", panel)
        font = self.lbl_log_title.font()
        font.setBold(True)
        self.lbl_log_title.setFont(font)
        bar.addWidget(self.lbl_log_title)
        bar.addSpacing(8)

        bar.addWidget(QLabel("显示", panel))
        self.combo_display = QComboBox(panel)
        self.combo_display.addItem("HEX", core.SEND_MODE_HEX)
        self.combo_display.addItem("ASCII", core.SEND_MODE_ASCII)
        self.combo_display.setFixedWidth(84)
        bar.addWidget(self.combo_display)

        self.chk_timestamp = QCheckBox("时间戳", panel)
        self.chk_timestamp.setToolTip("每行前加 YYYY-MM-DD HH:MM:SS.mmm")
        self.chk_timestamp.setChecked(True)
        bar.addWidget(self.chk_timestamp)

        self.chk_autoscroll = QCheckBox("自动滚动", panel)
        self.chk_autoscroll.setChecked(True)
        bar.addWidget(self.chk_autoscroll)

        bar.addStretch(1)
        self.btn_clear_log = QPushButton("清空", panel)
        self.btn_clear_log.setFixedWidth(64)
        self.btn_clear_log.clicked.connect(self._on_clear_log)
        bar.addWidget(self.btn_clear_log)
        layout.addLayout(bar)

        self.log_text = QPlainTextEdit(panel)
        self.log_text.setReadOnly(True)
        self.log_text.setFont(_mono_font(9))
        self.log_text.setMaximumBlockCount(LOG_MAX_BLOCKS)
        self.log_text.setPlaceholderText(
            "收到的报文会显示在这里。发送框与「测试架参数」发出的报文以 [TX] 开头。")
        layout.addWidget(self.log_text, 1)
        return panel

    # ── 右栏内容：测试架参数 ──
    def _build_params_body(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 0, 2, 2)
        layout.setSpacing(4)

        # 地址域（6 字节，默认广播）——放在滚动区外，始终可见
        addr_row = QHBoxLayout()
        addr_row.setSpacing(6)
        addr_label = QLabel("地址域（6 字节，AA×6 = 广播）", panel)
        self.addr_field = HexField(6, panel)
        self.addr_field.setToolTip("现场样例为广播地址 AA AA AA AA AA AA")
        self.addr_field.changed.connect(self._schedule_preview)
        addr_row.addWidget(addr_label)
        addr_row.addWidget(self.addr_field)
        addr_row.addStretch(1)
        layout.addLayout(addr_row)

        # 参数分组（滚动）
        inner = QWidget(panel)
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(6)
        # 帧头里的两个测试开关（不在 53 字节参数区内，但同属现场参数表）
        inner_layout.addWidget(self._build_field_group(
            "⓪ 测试开关（帧头）", [spec.key for spec in core.HEADER_FIELDS], inner))
        for title, keys in core.FIELD_GROUPS:
            inner_layout.addWidget(self._build_field_group(title, keys, inner))
        inner_layout.addStretch(1)

        scroll = QScrollArea(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(inner)
        self.params_scroll = scroll
        layout.addWidget(scroll, 1)

        # 预览 + 状态 + 操作（右栏较窄，状态单独一行、按钮一行）
        self.preview_edit = QLineEdit(panel)
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setFont(_mono_font(9))
        self.preview_edit.setPlaceholderText("参数报文预览")
        layout.addWidget(self.preview_edit)

        self.lbl_preview_state = QLabel("", panel)
        self.lbl_preview_state.setWordWrap(True)
        layout.addWidget(self.lbl_preview_state)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.btn_defaults = QPushButton("恢复示例", panel)
        self.btn_defaults.setToolTip("把全部参数恢复到现场样例帧的取值")
        self.btn_defaults.clicked.connect(self._on_restore_defaults)
        self.btn_copy = QPushButton("复制报文", panel)
        self.btn_copy.clicked.connect(self._on_copy_frame)
        # 发送形态：与左侧发送框同一语义（HEX = 二进制帧；ASCII = 报文按 HEX 文本字符发送）
        self.combo_params_mode = QComboBox(panel)
        self.combo_params_mode.addItem("HEX", core.SEND_MODE_HEX)
        self.combo_params_mode.addItem("ASCII", core.SEND_MODE_ASCII)
        self.combo_params_mode.setFixedWidth(66)
        self.combo_params_mode.setToolTip(
            "HEX：发送 75 字节二进制帧（现场测试架用这个）\n"
            "ASCII：把报文按 HEX 文本字符发送（如 68AAAAAAAA…），给接文本协议的工装用")
        self.combo_params_mode.currentIndexChanged.connect(lambda *_: self._schedule_save())
        self.btn_send_params = QPushButton("发送参数帧", panel)
        self.btn_send_params.setObjectName("PrimaryButton")
        self.btn_send_params.clicked.connect(self._on_send_params)
        actions.addWidget(self.btn_defaults)
        actions.addWidget(self.btn_copy)
        actions.addWidget(self.combo_params_mode)
        actions.addWidget(self.btn_send_params)
        layout.addLayout(actions)
        return panel

    def _build_field_group(self, title: str, keys, parent: QWidget) -> QWidget:
        """一个参数分组：**一行一组「标签 + 编辑器」**（右栏可拖窄，单列不会出横向滚动条）。"""
        box = QGroupBox(title, parent)
        grid = QGridLayout(box)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(3)
        for i, key in enumerate(keys):
            spec = core.FIELD_MAP[key]
            label = QLabel(spec.label, box)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            editor = self._build_field_editor(spec, box)
            grid.addWidget(label, i, 0)
            grid.addWidget(editor, i, 1)
            self._param_widgets[key] = editor
        grid.setColumnStretch(2, 1)      # 编辑器靠左，余量给右侧
        return box

    def _build_field_editor(self, spec: core.FieldSpec, parent: QWidget):
        if spec.choices:
            combo = QComboBox(parent)
            for value, text in spec.choices:
                combo.addItem(text, value)
            combo.setFixedWidth(186)
            default = int(spec.default, 16)
            idx = combo.findData(default)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.setToolTip(spec.tip or spec.label)
            combo.currentIndexChanged.connect(lambda *_: self._schedule_preview())
            return combo
        field = HexField(spec.size, parent)
        field.set_hex(spec.default)
        field.setToolTip(spec.tip or spec.label)
        field.changed.connect(self._schedule_preview)
        return field

    # ==================================================================
    # 三栏折叠 / 拖动
    # ==================================================================
    def _on_left_collapsed(self, collapsed: bool) -> None:
        self._apply_column_sizes("left", bool(collapsed))

    def _on_right_collapsed(self, collapsed: bool) -> None:
        self._apply_column_sizes("right", bool(collapsed))

    def _apply_column_sizes(self, which: str, collapsed: bool) -> None:
        """折叠时把该栏压成窄条、把宽度让给日志；展开时还原折叠前的三栏宽度。

        只在「两侧都展开」时清空 ``_sizes_before_collapse``（下一次折叠重新记录），
        这样「左折 → 右折 → 左展」不会把右栏的折叠前宽度丢掉。
        """
        index = 0 if which == "left" else 2
        sizes = list(self.split_columns.sizes())
        if len(sizes) != 3:                       # 未布局完（极端尺寸）时不硬算
            return
        if collapsed:
            if self._sizes_before_collapse is None:
                self._sizes_before_collapse = list(sizes)
            sizes[index] = SIDE_COLLAPSED_WIDTH
            self.split_columns.setSizes(sizes)
        else:
            target = list(self._sizes_before_collapse or SIDE_DEFAULT_SIZES)
            if not self.left_panel.is_expanded():
                target[0] = SIDE_COLLAPSED_WIDTH
            if not self.right_panel.is_expanded():
                target[2] = SIDE_COLLAPSED_WIDTH
            self.split_columns.setSizes(target)
            if self.left_panel.is_expanded() and self.right_panel.is_expanded():
                self._sizes_before_collapse = None
        self._schedule_save()

    def _apply_layout_config(self, layout: dict) -> None:
        """从落盘配置恢复折叠状态与三栏宽度（``layout`` 缺失/脏值走默认）。"""
        raw = layout if isinstance(layout, dict) else {}
        left_collapsed = bool(raw.get("left_collapsed", False))
        right_collapsed = bool(raw.get("right_collapsed", False))
        sizes = raw.get("sizes")
        target = None
        if isinstance(sizes, (list, tuple)) and len(sizes) == 3:
            try:
                target = [max(1, int(v)) for v in sizes]
            except (TypeError, ValueError):
                target = None
        if target is None:
            target = list(SIDE_DEFAULT_SIZES)
        # 先设折叠状态（不触发信号），再一次性套宽度，避免折开两次抖动
        self.left_panel.set_expanded(not left_collapsed, emit=False)
        self.right_panel.set_expanded(not right_collapsed, emit=False)
        if left_collapsed:
            target[0] = SIDE_COLLAPSED_WIDTH
        if right_collapsed:
            target[2] = SIDE_COLLAPSED_WIDTH
        self.split_columns.setSizes(target)
        self._sizes_before_collapse = (list(target)
                                       if (left_collapsed or right_collapsed) else None)

    # ==================================================================
    # 串口订阅（只订阅，绝不开/关端口）
    # ==================================================================
    def set_serial_worker(self, worker) -> None:
        old = self._serial_worker
        if old is not None:
            self._detach(old)
        self._serial_worker = worker
        if worker is None:
            self._set_connected(False)
            return
        worker.raw_data_received.connect(self._on_serial_raw_data)
        worker.connection_changed.connect(self._set_connected)
        worker.error_occurred.connect(self._on_serial_error)
        self._set_connected(bool(worker.is_open()))

    def _detach(self, worker) -> None:
        for signal, slot in (
            (worker.raw_data_received, self._on_serial_raw_data),
            (worker.connection_changed, self._set_connected),
            (worker.error_occurred, self._on_serial_error),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _set_connected(self, connected: bool) -> None:
        self._connected = bool(connected)
        state = "已连接" if connected else "未连接"
        self.lbl_serial_state.setText(
            f"串口：{state}（端口/波特率在顶部「串口配置」设置；本页与其它页共用同一个串口）")
        for sb in self.send_boxes:
            sb.set_connected(self._connected)
        self.btn_send_params.setEnabled(self._connected)
        self.btn_send_params.setToolTip("" if self._connected else TIP_NOT_CONNECTED)

    def _on_serial_error(self, message: str) -> None:
        self._log(f"[失败] 串口错误：{message}", "fail")

    def _on_serial_raw_data(self, data: bytes) -> None:
        raw = bytes(data or b"")
        if not raw:
            return
        self._rx_bytes += len(raw)
        self._update_counters()
        self._log(self._render_payload(raw, "RX"), "rx")

    # ==================================================================
    # 发送
    # ==================================================================
    def _worker(self):
        w = self._serial_worker
        if w is None or not w.is_open():
            return None
        return w

    def _send_bytes(self, payload: bytes, label: str, box: Optional[SendBox] = None) -> bool:
        """统一发送出口：写串口 + 记日志 + 计数（``box`` 用于回写该框状态）。"""
        w = self._worker()
        if w is None:
            tip = TIP_NO_SERIAL if self._serial_worker is None else TIP_NOT_CONNECTED
            self._log(f"[失败] {label} 未发送：{tip}", "fail")
            if box is not None:
                box.set_status("未发送", self._palette["fail"])
                box.setToolTip(tip)
            return False
        ok = bool(w.write_raw(payload))
        if not ok:
            self._log(f"[失败] {label} 未发送（串口写入失败，详见上方错误）", "fail")
            if box is not None:
                box.set_status("写入失败", self._palette["fail"])
            return False
        self._tx_bytes += len(payload)
        self._update_counters()
        self._log(self._render_payload(payload, "TX"), "tx")
        if box is not None:
            box.set_status(f"已发 {len(payload)} B", self._palette["tx"])
            box.setToolTip("")
        return True

    def _on_send_box(self, cfg: core.SendBoxConfig) -> None:
        # 信号是同步直连，``sender()`` 一定是发出该信号的 SendBox（用它回写状态最稳）
        sender = self.sender()
        box = sender if isinstance(sender, SendBox) else None
        title = cfg.name or (f"发送 {box.index + 1}" if box is not None else "发送")
        try:
            payload = core.build_send_payload(cfg)
        except core.ParamError as exc:
            self._log(f"[失败] {title} 内容非法：{exc}", "fail")
            if box is not None:
                box.set_status(str(exc)[:24], self._palette["fail"])
            return
        self._send_bytes(payload, title, box)

    def _on_send_params(self) -> None:
        frame = self._current_frame()
        if frame is None:
            return
        mode = str(self.combo_params_mode.currentData() or core.SEND_MODE_HEX)
        payload = core.frame_payload(frame, mode)
        label = ("测试架参数" if mode == core.SEND_MODE_HEX
                 else "测试架参数（ASCII 文本）")
        if self._send_bytes(payload, label) and mode == core.SEND_MODE_ASCII:
            # ASCII 形态发出去是 150 个可打印字符，与 75 字节二进制帧看着不同 —— 明确记一行
            self._log(f"[信息] 参数帧按 ASCII 文本发送（{len(payload)} 字符）", "info")

    def current_frame_hex(self) -> str:
        """当前参数帧的紧凑 HEX（参数非法时返回空串；供测试/外部使用）。"""
        frame = self._current_frame(log_errors=False)
        return core.format_hex_field(frame) if frame else ""

    def _on_copy_frame(self) -> None:
        frame = self._current_frame()
        if frame is None:
            return
        QApplication.clipboard().setText(core.format_hex(frame))
        self.lbl_preview_state.setText(f"已复制 {len(frame)} 字节到剪贴板")
        self._log(f"[信息] 已复制测试架参数帧（{len(frame)} 字节）", "info")

    def _on_restore_defaults(self) -> None:
        for spec in (*core.HEADER_FIELDS, *core.BODY_FIELDS):
            self._set_param(spec.key, spec.default)
        self.addr_field.set_hex(core.DEFAULT_ADDR_HEX)
        self._refresh_preview()
        self._log("[信息] 已恢复现场示例参数（75 字节样例帧）", "info")

    # ==================================================================
    # 参数帧
    # ==================================================================
    def _set_param(self, key: str, value: object) -> None:
        widget = self._param_widgets.get(key)
        if widget is None:
            return
        spec = core.FIELD_MAP[key]
        if spec.choices:
            idx = widget.findData(int(value, 16) if isinstance(value, str) else int(value))
            if idx >= 0:
                widget.setCurrentIndex(idx)
        else:
            widget.set_hex(value)

    def _param_values(self) -> Dict[str, object]:
        """界面当前值 → ``{key: HEX 字符串}``（下拉字段也统一成两位 HEX，便于落盘与比对）。"""
        values: Dict[str, object] = {}
        for key, widget in self._param_widgets.items():
            spec = core.FIELD_MAP[key]
            values[key] = (f"{int(widget.currentData()):02X}" if spec.choices
                           else widget.hex_value())
        return values

    def _current_frame(self, log_errors: bool = True) -> Optional[bytes]:
        """按当前界面参数组帧；非法时在预览行给具体字段（不弹框）。"""
        try:
            return core.build_bench_frame(self._param_values(), self.addr_field.hex_value())
        except core.ParamError as exc:
            self.lbl_preview_state.setText(f"⚠ {exc}")
            self.lbl_preview_state.setStyleSheet(f"color: {self._palette['fail']};")
            self.preview_edit.clear()
            if log_errors:
                self._log(f"[失败] 参数校验未通过：{exc}", "fail")
            return None

    def _schedule_preview(self) -> None:
        self._preview_timer.start()
        self._schedule_save()

    def _refresh_preview(self) -> None:
        frame = self._current_frame(log_errors=False)
        if frame is None:
            return
        self.preview_edit.setText(core.format_hex(frame))
        self.preview_edit.setCursorPosition(0)
        self.lbl_preview_state.setText(
            f"{len(frame)} 字节 · 参数区 {core.BODY_LEN} 字节 · CS8 = 0x{frame[-2]:02X}")
        self.lbl_preview_state.setStyleSheet(f"color: {self._palette['hint']};")
        self.btn_copy.setEnabled(True)
        self.btn_send_params.setEnabled(self._connected)

    # ==================================================================
    # 日志
    # ==================================================================
    def _render_payload(self, data: bytes, tag: str) -> str:
        """``RX``/``TX`` 行：显示模式取下拉框；超长只显示头尾。"""
        mode = str(self.combo_display.currentData() or core.SEND_MODE_HEX)
        shown = data
        suffix = ""
        if len(data) > LOG_BYTES_LIMIT:
            head = LOG_BYTES_LIMIT // 2
            tail = LOG_BYTES_LIMIT - head
            shown = data[:head]
            suffix = f" … {core.render_display(data[-tail:], mode)}（共 {len(data)} 字节）"
        return f"[{tag}] {core.render_display(shown, mode)}{suffix}"

    def _log(self, text: str, kind: str = "info") -> None:
        """入队一行日志；由 :meth:`_flush_log` 每 100 ms 合并写入（时间戳按入队时刻）。"""
        prefix = ""
        if self.chk_timestamp.isChecked():
            prefix = core.timestamp_text(datetime.now()) + "  "
        self._pending_log.append((prefix + text + "\n", kind))
        if len(self._pending_log) >= LOG_FLUSH_MAX:
            self._flush_log()
        elif not self._log_timer.isActive():
            self._log_timer.start()

    def _flush_log(self) -> None:
        """把排队中的日志一次写进窗口（相邻同色行合并成一次 insertText）。"""
        self._log_timer.stop()
        if not self._pending_log:
            return
        pending, self._pending_log = self._pending_log, []
        palette = self._palette
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        def _emit(chunk: str, kind: str) -> None:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(palette.get(kind, palette["info"])))
            cursor.insertText(chunk, fmt)

        chunk, chunk_kind = [], pending[0][1]
        for line, kind in pending:
            if kind != chunk_kind:
                _emit("".join(chunk), chunk_kind)
                chunk = []
                chunk_kind = kind
            chunk.append(line)
        if chunk:
            _emit("".join(chunk), chunk_kind)
        if self.chk_autoscroll.isChecked():
            self.log_text.moveCursor(QTextCursor.MoveOperation.End)
            self.log_text.ensureCursorVisible()

    def _on_clear_log(self) -> None:
        self._log_timer.stop()
        self._pending_log.clear()
        self.log_text.clear()
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._update_counters()

    def _update_counters(self) -> None:
        self.lbl_counters.setText(f"收 {self._rx_bytes} B / 发 {self._tx_bytes} B")

    # ==================================================================
    # 主题
    # ==================================================================
    def restyle_for_theme(self, dark: bool) -> None:
        self._dark = bool(dark)
        self._apply_theme_style(self._dark)

    def _apply_theme_style(self, dark: bool) -> None:
        self._palette = LOG_PALETTES[bool(dark)]
        p = self._palette
        self.log_text.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {p['bg']}; color: {p['fg']};"
            f" border: 1px solid {p['border']}; border-radius: 3px; }}")
        for box in self.send_boxes:
            box.restyle_for_theme(dark)
        self.lbl_counters.setStyleSheet(f"color: {p['hint']};")
        self.lbl_preview_state.setStyleSheet(f"color: {p['hint']};")
        for panel in (self.left_panel, self.right_panel):
            panel.vertical_label.setStyleSheet(f"color: {p['hint']};")
        self._refresh_preview()

    # ==================================================================
    # 落盘
    # ==================================================================
    def _collect_config(self) -> dict:
        return {
            "version": core.CONFIG_VERSION,
            "params": self._param_values(),
            "addr_hex": self.addr_field.hex_value() or core.DEFAULT_ADDR_HEX,
            "send_boxes": [sb.config().to_dict() for sb in self.send_boxes],
            "display": {
                "mode": str(self.combo_display.currentData() or core.SEND_MODE_HEX),
                "timestamp": self.chk_timestamp.isChecked(),
                "autoscroll": self.chk_autoscroll.isChecked(),
            },
            "layout": {
                "left_collapsed": not self.left_panel.is_expanded(),
                "right_collapsed": not self.right_panel.is_expanded(),
                "sizes": [int(v) for v in self.split_columns.sizes()],
            },
            "params_mode": str(self.combo_params_mode.currentData() or core.SEND_MODE_HEX),
        }

    def _load_now(self) -> None:
        cfg = core.load_config(self._config_path)
        self._config = cfg
        for key, value in cfg.get("params", {}).items():
            if key in self._param_widgets:
                self._set_param(key, value)
        self.addr_field.set_hex(cfg.get("addr_hex", core.DEFAULT_ADDR_HEX))
        for box, data in zip(self.send_boxes, cfg.get("send_boxes", [])):
            box.set_config(core.SendBoxConfig.from_dict(data))
        display = cfg.get("display", {})
        idx = self.combo_display.findData(display.get("mode", core.SEND_MODE_HEX))
        self.combo_display.setCurrentIndex(idx if idx >= 0 else 0)
        self.chk_timestamp.setChecked(bool(display.get("timestamp", True)))
        self.chk_autoscroll.setChecked(bool(display.get("autoscroll", True)))
        self.combo_display.currentIndexChanged.connect(lambda *_: self._schedule_save())
        self.chk_timestamp.toggled.connect(lambda *_: self._schedule_save())
        self.chk_autoscroll.toggled.connect(lambda *_: self._schedule_save())
        self._apply_layout_config(cfg.get("layout", {}))
        idx = self.combo_params_mode.findData(cfg.get("params_mode", core.SEND_MODE_HEX))
        self.combo_params_mode.setCurrentIndex(idx if idx >= 0 else 0)
        for sb in self.send_boxes:
            sb.name_edit.textChanged.connect(lambda *_: self._schedule_save())
            sb.text_edit.textChanged.connect(self._schedule_save)
            sb.mode_combo.currentIndexChanged.connect(lambda *_: self._schedule_save())
            sb.cs8_check.toggled.connect(lambda *_: self._schedule_save())
            sb.cs8_mode.currentIndexChanged.connect(lambda *_: self._schedule_save())

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _save_now(self) -> None:
        self._config = self._collect_config()
        core.save_config(self._config_path, self._config)

    # ==================================================================
    # 生命周期
    # ==================================================================
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 页面可能先于串口连接建好：每次切回都对齐一次真实状态（幂等）
        w = self._serial_worker
        self._set_connected(bool(w is not None and w.is_open()))

    def cleanup(self) -> None:
        """停表、断信号、落盘（幂等）。**不关闭串口**（归顶部「串口配置」）。"""
        self._flush_log()
        for timer in (self._save_timer, self._preview_timer, self._log_timer):
            try:
                timer.stop()
            except RuntimeError:
                pass
        worker = self._serial_worker
        if worker is not None:
            self._detach(worker)
        self._serial_worker = None
        self._save_now()


__all__ = ["CONFIG_NAME", "LOG_PALETTES", "HexField", "ProductionTestbenchWidget",
           "SendBox", "TIP_NOT_CONNECTED"]
