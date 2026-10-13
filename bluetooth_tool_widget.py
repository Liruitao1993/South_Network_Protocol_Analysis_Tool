# -*- coding: utf-8 -*-
"""蓝牙工具页（集成自工程内的「蓝牙转串口工具02」）。

能力（与源工具一致）：
  - **扫描 / 连接 BLE 设备**：按信号强度排序的设备表，可选只显示有名称的设备、
    扫描完成后自动重新扫描（间隔可配）；连接失败自动重试 3 次
  - **特征码选择**：连接后列出全部服务/特征码，分别勾选「接收（notify/indicate）」
    与「发送（write / write-without-response）」；选择结果随配置持久化，下次连接自动回填
  - **接收**：BLE 通知按**静默超时**（默认 500ms，可配）重组为完整报文再显示，
    跨分包的一帧不会被拆成多行；窗口内可切 HEX / ASCII 显示
  - **发送**：手动输入（HEX 或 ASCII）或点自定义报文按钮发送；写入**按协商 MTU 分包**
    （低 MTU 设备也能发），包间延迟可配
  - **解析联动**：收到的完整报文按**当前协议**解析并在日志输出摘要 + 缩进字段行，
    与单帧页/批量解析共用同一套分派（与串口工具同一口径）
  - **虚拟模式（蓝牙 ⇄ 串口透传）**：BLE 收到的数据写入串口、串口收到的数据写入 BLE，
    用一台蓝牙模块当无线串口延长线
  - **自定义报文按钮**：增删改 + 批量导入 + 导出，随配置持久化
  - **彩色日志 + 自动保存到文件**：文件是日志窗口内容的**完整镜像**，目录可选、一键打开

与源工具的差异（**有意为之**，均记录在 README/AGENTS/CHANGELOG）：
  - 写入分包按「特征码免响应写上限 / 协商 MTU」计算（源工具硬编码 200 字节）
  - 分包重组只有「静默超时切帧」一种语义（源工具的实现里「立即单包直发」与「分包
    重组」自相矛盾，其 README 只承诺后者）
  - 断开/掉线前会把未成帧的残包交出来（不静默丢数据）
  - 串口侧**复用主窗口共享的 :class:`serial_worker.SerialWorker`**（`set_serial_worker`），
    不另开第二个 COM 口 —— 一个 COM 口只能被打开一次
  - 主题/字号走本项目主题系统（源工具自带两套硬编码样式），并提供
    :meth:`BluetoothToolWidget.restyle_for_theme` 只重设动态标签色
  - 形态是主窗口的一个标签页，不是独立 ``QMainWindow``

分层：
  - `bluetooth_core.py` —— 纯逻辑（重组 / 分包 / 配置持久化），不依赖 Qt 与 bleak
  - `bluetooth_worker.py` —— BLE 通信线程（`QObject` + 私有 asyncio 循环线程）
  - 本模块 —— 界面与对话框（**不** import `main_gui`，能力一律由注入提供）
"""

import os
import re
from collections import deque
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import app_icons
import app_paths
import bluetooth_core as core
from bluetooth_worker import BLEAK_MISSING_HINT, BluetoothWorker
from gui_utils import (
    ZoomableTableWidget,
    fit_btn_width,
    set_btn,
    set_btn_icon,
)
from serial_tool_widget import (
    LogFileWriter,
    bytes_to_hex,
    default_log_dir,
    format_log_time,
    format_parse_rows,
    hex_input_error,
    hex_str_to_bytes,
    write_log_text,
)

# ── 常量 ────────────────────────────────────────────────────────────────────

# 配置文件（app_paths.data_path 下，与 serial_tool_config.json 同级）
CONFIG_NAME = core.SETTINGS_NAME

# 日志窗口保留行数（超出后裁掉最旧的；文件不截断）
WINDOW_KEEP_LINES = core.DEFAULT_LOG_LINES
LOG_TRIM_STEP = core.LOG_LINE_TRIM_STEP

# 日志批量刷出（高速收发时避免逐行重绘）
LOG_FLUSH_MS = 100
LOG_FLUSH_BURST = 40

# 自定义报文按钮网格列数
BUTTON_GRID_COLUMNS = 3

# 设备表列
DEVICE_COLUMNS = ("名称", "地址", "信号", "状态")

# 日志文件
LOG_FILE_PREFIX = "bluetooth_log"
LOG_HEADER_TITLE = "蓝牙工具日志"

# 日志配色（与项目其它日志页风格一致）
_LOG_COLORS: Dict[str, str] = {
    "ble": "#00897B",     # 蓝牙事件
    "serial": "#F57C00",  # 串口事件（虚拟模式）
    "tx": "#C00000",      # 发送
    "rx": "#008000",      # 接收
    "parse": "#1565C0",   # 解析
    "sys": "#616161",     # 系统
    "warn": "#EF6C00",    # 提醒
    "fail": "#C00000",    # 失败
}

# 信号强度分档阈值（RSSI dBm → 4/3/2/1 档）
_RSSI_THRESHOLDS = ((4, -55), (3, -67), (2, -80), (1, -90))

# HEX 意图判定用的字符集（分隔符与 serial_tool_widget 同一套）
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")
_HEX_SEPARATORS = frozenset(" \t\r\n\u3000,，、;；/|-")
_HEX_SPLIT_RE = re.compile(
    "[" + re.escape("".join(sorted(_HEX_SEPARATORS))) + "]+"
)

# 发送格式下拉的取值（与 parse_plain_text 的 mode 参数一一对应）
SEND_FORMATS: Tuple[Tuple[str, str], ...] = (
    ("自动（HEX 优先）", "auto"),
    ("HEX 字节", "hex"),
    ("ASCII 文本", "ascii"),
)



# ── 纯助手（便于 offscreen 单测）────────────────────────────────────────────


def rssi_level(rssi) -> int:
    """信号强度 → 0..4 档（0 = 未知/极弱）；与信号格显示一一对应。"""
    try:
        value = int(rssi)
    except (TypeError, ValueError):
        return 0
    # bleak 未知 RSSI 报 0，而 0 比任何负阈值都「大」—— 不拦的话未知信号会显示成满格，
    # 与 rssi_text(0) 的 "--" 自相矛盾。真机 RSSI 不可能 ≥ 0，一律按未知处理。
    if value >= 0:
        return 0
    for level, threshold in _RSSI_THRESHOLDS:
        if value >= threshold:
            return level
    return 0


def rssi_bars(rssi) -> str:
    """信号格文字（``▂▄▆█`` 风格的 4 格；0 档显示 ``·``）。"""
    level = rssi_level(rssi)
    if level <= 0:
        return "·"
    return "▁▃▅█"[:level]


def rssi_text(rssi) -> str:
    """``-57 dBm █`` 形式（未知 RSSI 只显示 ``--``）。"""
    try:
        value = int(rssi)
    except (TypeError, ValueError):
        return "--"
    if value == 0:
        return "--"
    return f"{value} dBm {rssi_bars(value)}"


def format_payload(data, as_hex: bool = True) -> str:
    """载荷显示：HEX（空格分隔）或 ASCII（不可打印字符回落 ``.``）。"""
    raw = bytes(data or b"")
    if as_hex:
        return bytes_to_hex(raw)
    text = raw.decode("utf-8", errors="replace")
    return "".join(ch if ch.isprintable() else "." for ch in text)


def looks_like_hex(text: str) -> bool:
    """内容是否为「HEX 意图」（供「自动」格式判定）。

    判据：按常见分隔符切分后，**存在一个长度 ≥ 2 且全为 hex 字符的片段**。

    为什么用这个判据（都是实测过的现场形态）：

    - ``68 12 0G`` → 有 ``68`` 这个纯 hex 片段 ⇒ 判为 HEX 意图 ⇒ 解析失败会**报错**，
      不会被悄悄改按文本发出去（这正是最危险的误发：把 8 个字符的 UTF-8 字节写到设备上）；
    - ``AT+INFO?`` / ``hello`` → 没有任何长度 ≥2 的纯 hex 片段 ⇒ 文本意图；
    - ``4``（单字符）→ 判为文本：单字符既可能是 ``0x04`` 也可能是字符 ``4``，
      要发单字节请在「格式」里显式选 HEX。
    """
    raw = str(text or "").strip()
    if not raw:
        return False
    body = re.sub(r"0[xX](?=[0-9A-Fa-f])", "", raw)
    for token in _HEX_SPLIT_RE.split(body):
        if len(token) >= 2 and all(ch in _HEX_CHARS for ch in token):
            return True
    return False


def hex_odd_nibble_error(text: str) -> str:
    """「悬空半字节」报错文案；没有则返回空串。

    为什么要单独拦这一条：``serial_tool_widget.hex_str_to_bytes`` 对奇数长度的 HEX 是
    **静默补 0** 的（``68 12 0`` → ``68 12 00``）—— 现场少打或多打一个字符，发出去的
    就是另一串字节，而且没有任何提示。发送路径上这种「猜」不能接受。
    """
    body = re.sub(r"0[xX](?=[0-9A-Fa-f])", "", str(text or ""))
    for token in _HEX_SPLIT_RE.split(body):
        if len(token) % 2 and all(ch in _HEX_CHARS for ch in token):
            return f"HEX 位数不成对（{token}）"
    return ""


def parse_plain_text(text: str, mode: str = "auto") -> Tuple[Optional[bytes], str]:
    """发送输入框内容 → ``(载荷, 错误说明)``；``错误说明`` 非空表示**不要发送**。

    ``mode``：
      - ``auto``（默认）：像 HEX 就按 HEX（**解析失败即报错**，绝不静默改按文本发），
        否则按 UTF-8 文本；
      - ``hex``：强制 HEX，解析失败报错；
      - ``ascii``：强制 UTF-8 文本。

    为什么不「HEX 失败就回落文本」：现场把 ``68 12 0G`` 误当成 HEX 时，回落会把
    这 8 个字符的 UTF-8 字节发到设备上 —— 静默发错比报错危险得多。

    另：HEX 路径下**位数不成对**（``68 12 0``）同样报错，不让底层静默补 0
    （见 :func:`hex_odd_nibble_error`）。
    """
    raw = str(text or "")
    if not raw.strip():
        return None, "内容为空"
    key = str(mode or "auto").strip().lower()
    if key == "ascii":
        return raw.strip().encode("utf-8"), ""
    if key == "hex":
        odd = hex_odd_nibble_error(raw)
        if odd:
            return None, odd
        decoded = hex_str_to_bytes(raw)
        if decoded is None:
            return None, f"HEX 无效：{hex_input_error(raw)}"
        return decoded, ""
    if looks_like_hex(raw):
        odd = hex_odd_nibble_error(raw)
        if odd:
            return None, odd
        decoded = hex_str_to_bytes(raw)
        if decoded is None:
            return None, f"HEX 无效：{hex_input_error(raw)}"
        return decoded, ""
    return raw.strip().encode("utf-8"), ""



def _mono_font() -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(9)
    return font


def _props_text(properties) -> str:
    """特征码属性列表 → 中文可读文字。"""
    mapping = {
        "read": "读",
        "write": "写",
        "write-without-response": "免响应写",
        "notify": "通知",
        "indicate": "指示",
        "broadcast": "广播",
        "authenticated-signed-writes": "签名写",
        "reliable-write": "可靠写",
        "writable-auxiliaries": "可写辅助",
    }
    parts = []
    for prop in properties or []:
        key = str(prop)
        parts.append(mapping.get(key, key))
    return " / ".join(parts)


# ── 特征码选择对话框 ────────────────────────────────────────────────────────


class CharacteristicSelectDialog(QDialog):
    """特征码选择：左「接收（notify/indicate）」、右「发送（write）」。

    - 两侧都列出设备的**全部**特征码，但不可用于该侧的特征码**勾选框置灰**
      （避免把「只读特征码」选成发送目标这类静默失败）；
    - 「全选 / 全不选 / 自动选择」只作用于各自一侧；
    - 上次的选择（若仍在列表中）会被回填并勾选。
    """

    def __init__(self, characteristics, recv_uuids=None, send_uuids=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择特征码")
        self.resize(760, 470)
        self._chars = [dict(c) for c in (characteristics or []) if isinstance(c, dict)]
        # 打分优选结果：作为「预选 + 置顶 + 顶部推荐说明」的唯一来源（1.23.79）
        self._recv_recommended, self._send_recommended, self._recommend_reason = \
            core.pick_auto(self._chars)
        self._recv_list = QListWidget()
        self._send_list = QListWidget()
        self._detail = QLabel("选择左侧/右侧的条目可查看详情")
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._build_ui()
        # 没传选择时**预选优选结果**（用户点开就是可用状态，直接确定即可）
        self._fill(self._recv_list, "can_recv", recv_uuids or self._recv_recommended)
        self._fill(self._send_list, "can_send", send_uuids or self._send_recommended)
        self._sync_detail()

    # ── 构建 ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        hint = QLabel(
            "接收侧订阅设备的通知/指示；发送侧是写入目标。"
            "不可用方向在条目文字里直接标注（如「（不可写）」）。"
            "条目已按「像业务透传通道」的打分排序，可直接用预选结果点确定。"
            + (f"\n推荐：{self._recommend_reason}" if self._recommend_reason else "")
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        columns = QHBoxLayout()
        columns.setSpacing(8)
        columns.addWidget(self._build_column("接收（notify / indicate）", self._recv_list), 1)
        columns.addWidget(self._build_column("发送（write）", self._send_list), 1)
        layout.addLayout(columns, 1)

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(6, 4, 6, 4)
        frame_layout.addWidget(self._detail)
        layout.addWidget(frame)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        set_btn(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        set_btn(buttons.button(QDialogButtonBox.StandardButton.Cancel), "secondary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_column(self, title: str, list_widget: QListWidget) -> QWidget:
        box = QGroupBox(title)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(6, 8, 6, 6)
        box_layout.setSpacing(4)

        list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        list_widget.setAlternatingRowColors(True)
        list_widget.currentRowChanged.connect(lambda _row: self._sync_detail())
        box_layout.addWidget(list_widget, 1)

        row = QHBoxLayout()
        row.setSpacing(4)
        btn_all = QPushButton("全选")
        set_btn(btn_all, "secondary", "sm")
        set_btn_icon(btn_all, "apply")
        btn_all.clicked.connect(lambda: self._set_all(list_widget, True))
        row.addWidget(btn_all)

        btn_none = QPushButton("全不选")
        set_btn(btn_none, "secondary", "sm")
        set_btn_icon(btn_none, "clear")
        btn_none.clicked.connect(lambda: self._set_all(list_widget, False))
        row.addWidget(btn_none)

        btn_auto = QPushButton("自动选择")
        set_btn(btn_auto, "secondary", "sm")
        btn_auto.setToolTip("选中第一个可用的特征码（接收优先 notify，发送优先免响应写）")
        btn_auto.clicked.connect(lambda: self._auto_select(list_widget))
        row.addWidget(btn_auto)
        row.addStretch()
        box_layout.addLayout(row)
        return box

    # ── 填充与操作 ───────────────────────────────────────────────────────

    def _fill(self, list_widget: QListWidget, capability: str, selected):
        selected_set = {str(u or "").strip().lower() for u in (selected or [])}
        list_widget.clear()
        # 排序：**打分优选在前**（同分保持设备枚举顺序），不可用项沉底 —— 第一眼就是最优通道
        ordered = sorted(
            core.rank_characteristics(self._chars),
            key=lambda c: (0 if c.get(capability) else 1, -int(c.get("score") or 0)),
        )
        for index, char in enumerate(ordered):
            uuid = str(char.get("uuid", ""))
            short = str(char.get("short") or core.short_uuid(uuid) or uuid)
            desc = str(char.get("description") or "").strip()
            props = _props_text(char.get("properties"))
            capable = bool(char.get(capability))
            # 不可用方向**必须文字标注**：QSS 主题下置灰看不出来（AGENTS §8 陷阱 71）
            suffix = "" if capable else (
                "（不可写）" if capability == "can_send" else "（不可通知）"
            )
            label = f"{short}  {desc or props}{suffix}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, uuid)
            capable = bool(char.get(capability))
            item.setToolTip(
                f"{uuid}\n服务：{char.get('service_short') or ''} "
                f"({char.get('service_uuid') or ''})\n"
                f"属性：{props or '（无）'}\n"
                f"免响应写上限：{char.get('max_write') or 0} 字节\n"
                + ("" if capable else "\n⚠ 该特征码不支持此方向")
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if capable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(
                Qt.CheckState.Checked
                if (uuid.lower() in selected_set and capable)
                else Qt.CheckState.Unchecked
            )
            list_widget.addItem(item)
            if uuid.lower() in selected_set:
                list_widget.setCurrentRow(index)
        if list_widget.currentRow() < 0 and list_widget.count():
            list_widget.setCurrentRow(0)

    def _set_all(self, list_widget: QListWidget, checked: bool):
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item.flags() & Qt.ItemFlag.ItemIsEnabled:
                item.setCheckState(
                    Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )

    def _auto_select(self, list_widget: QListWidget):
        self._set_all(list_widget, False)
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item.flags() & Qt.ItemFlag.ItemIsEnabled:
                item.setCheckState(Qt.CheckState.Checked)
                list_widget.setCurrentRow(row)
                return

    def _sync_detail(self):
        widget = self.sender()
        if not isinstance(widget, QListWidget):
            widget = self._recv_list
        item = widget.currentItem()
        if item is None:
            self._detail.setText("选择左侧/右侧的条目可查看详情")
            return
        uuid = str(item.data(Qt.ItemDataRole.UserRole) or "")
        char = next(
            (c for c in self._chars if str(c.get("uuid", "")) == uuid), None
        )
        if char is None:
            self._detail.setText(uuid or "（无）")
            return
        self._detail.setText(
            f"UUID：{uuid}\n"
            f"服务：{char.get('service_short') or ''}  {char.get('service_uuid') or ''}\n"
            f"名称：{char.get('description') or '（无）'}\n"
            f"属性：{_props_text(char.get('properties')) or '（无）'}\n"
            f"免响应写上限：{char.get('max_write') or 0} 字节"
        )

    # ── 结果 ─────────────────────────────────────────────────────────────

    def selected_recv(self) -> List[str]:
        return self._checked(self._recv_list)

    def selected_send(self) -> List[str]:
        return self._checked(self._send_list)

    @staticmethod
    def _checked(list_widget: QListWidget) -> List[str]:
        out: List[str] = []
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                uuid = str(item.data(Qt.ItemDataRole.UserRole) or "")
                if uuid:
                    out.append(uuid)
        return out


# ── 自定义报文按钮：批量导入的纯解析 ────────────────────────────────────────

# 一行格式：``名称,内容[,HEX|ASCII]``；内容里可能含逗号，故只有**首个**逗号切名称


def parse_button_lines(text: str, limit: int = core.MAX_CUSTOM_BUTTONS
                       ) -> Tuple[List[dict], List[str]]:
    """批量导入文本 → ``(按钮列表, 错误行说明)``。

    每行 ``名称,内容[,HEX|ASCII]``：

    - 名称缺失时用 ``报文N``；内容为空的行跳过并记一条错误说明；
    - 第三个字段为 ``HEX`` / ``ASCII``（大小写不敏感，也接受 ``hex``/``文本``），
      缺省按 **HEX**（源工具默认值）；
    - 以 ``#`` 或 ``//`` 开头的行为注释；
    - 空行忽略；超过 ``limit`` 条的剩余行**记一条错误说明**而不是静默丢弃。
    """
    buttons: List[dict] = []
    errors: List[str] = []
    for index, raw in enumerate(str(text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if len(buttons) >= limit:
            errors.append(f"第 {index} 行：超过上限 {limit} 条，已忽略")
            continue
        parts = [p.strip() for p in line.split(",")]
        name = parts[0] if parts else ""
        data = parts[1] if len(parts) > 1 else ""
        fmt = parts[2] if len(parts) > 2 else "HEX"
        if not name and not data:
            errors.append(f"第 {index} 行：名称与内容都为空")
            continue
        if not data:
            errors.append(f"第 {index} 行：内容为空")
            continue
        is_hex = fmt.lower() not in ("ascii", "文本")
        button = core.normalize_button(
            {"name": name or f"报文{index}", "data": data, "isHex": is_hex},
            f"报文{index}",
        )
        if button is None:
            errors.append(f"第 {index} 行：内容无效")
            continue
        if is_hex and hex_str_to_bytes(data) is None:
            errors.append(f"第 {index} 行：HEX 内容无效（{hex_input_error(data)}）")
            continue
        buttons.append(button)
    return buttons, errors


# ── 自定义报文按钮对话框 ────────────────────────────────────────────────────


class ButtonEditDialog(QDialog):
    """新增 / 编辑一个自定义报文按钮（名称 + 内容 + HEX/ASCII）。"""

    def __init__(self, parent=None, button=None):
        super().__init__(parent)
        source = dict(button or {})
        self.setWindowTitle("编辑报文按钮" if button else "新增报文按钮")
        self.resize(480, 250)

        self.edit_name = QLineEdit(str(source.get("name") or ""))
        self.edit_name.setMaxLength(core.BUTTON_NAME_MAX)
        self.edit_name.setPlaceholderText("按钮上显示的名称")

        self.edit_content = QPlainTextEdit(str(source.get("data") or ""))
        self.edit_content.setFixedHeight(90)
        self.edit_content.setFont(_mono_font())
        self.edit_content.setPlaceholderText("HEX：68 12 00 41 16    或    ASCII：AT+INFO?")

        self.radio_hex = QRadioButton("HEX 字节")
        self.radio_ascii = QRadioButton("ASCII 文本")
        self.radio_hex.setToolTip("内容按十六进制字节解析（支持空格/连续/0x 前缀）")
        self.radio_ascii.setToolTip("内容按 UTF-8 文本发送")
        if source.get("isHex", True):
            self.radio_hex.setChecked(True)
        else:
            self.radio_ascii.setChecked(True)
        self.radio_hex.toggled.connect(self._refresh_hint)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        form = QFormLayout()
        form.setSpacing(6)
        form.addRow("名称：", self.edit_name)
        layout.addLayout(form)

        layout.addWidget(QLabel("内容："))
        layout.addWidget(self.edit_content, 1)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("格式："))
        fmt_row.addWidget(self.radio_hex)
        fmt_row.addWidget(self.radio_ascii)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)
        layout.addWidget(self.lbl_hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        set_btn(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        set_btn(buttons.button(QDialogButtonBox.StandardButton.Cancel), "secondary")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_hint()
        self.edit_content.textChanged.connect(self._refresh_hint)

    def _refresh_hint(self):
        """实时回显「按什么格式、解析成几个字节」，避免发出去才发现写错。"""
        text = self.edit_content.toPlainText()
        if not text.strip():
            self.lbl_hint.setText("")
            return
        if self.radio_hex.isChecked():
            decoded = hex_str_to_bytes(text)
            if decoded is None:
                self.lbl_hint.setText(f"⚠ HEX 无效：{hex_input_error(text)}")
            else:
                self.lbl_hint.setText(f"✓ HEX {len(decoded)} 字节")
        else:
            self.lbl_hint.setText(f"✓ ASCII {len(text.strip().encode('utf-8'))} 字节")

    def _on_accept(self):
        if not self.edit_name.text().strip():
            QMessageBox.warning(self, "名称为空", "请填写按钮名称。")
            return
        text = self.edit_content.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "内容为空", "请填写报文内容。")
            return
        if self.radio_hex.isChecked() and hex_str_to_bytes(text) is None:
            QMessageBox.warning(
                self, "HEX 无效", f"内容不是有效的 HEX：\n{hex_input_error(text)}"
            )
            return
        self.accept()

    def value(self) -> dict:
        """对话框结果（已规范化的按钮字典）。"""
        return core.normalize_button(
            {
                "name": self.edit_name.text().strip(),
                "data": self.edit_content.toPlainText().strip(),
                "isHex": self.radio_hex.isChecked(),
            },
            "未命名",
        ) or {}


class BatchButtonDialog(QDialog):
    """批量新增自定义报文按钮：每行 ``名称,内容[,HEX|ASCII]``。"""

    def __init__(self, parent=None, default_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("批量新增报文按钮")
        self.resize(560, 380)
        self._buttons: List[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        hint = QLabel(
            "每行一条：<b>名称,内容[,HEX|ASCII]</b>　"
            "（第三个字段缺省为 HEX；行内首个逗号切分名称，内容里可含逗号；"
            "<code>#</code> 开头为注释）"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.edit_lines = QPlainTextEdit(
            default_text or "示例报文,68 12 00 41 16,HEX\n文本报文,AT+INFO?,ASCII"
        )
        self.edit_lines.setFont(_mono_font())
        layout.addWidget(self.edit_lines, 1)

        row = QHBoxLayout()
        btn_preview = QPushButton("预检")
        set_btn(btn_preview, "secondary")
        set_btn_icon(btn_preview, "apply")
        btn_preview.setToolTip("解析并显示结果，不关闭对话框")
        btn_preview.clicked.connect(self._preview)
        row.addWidget(btn_preview)
        self.lbl_result = QLabel("")
        self.lbl_result.setWordWrap(True)
        row.addWidget(self.lbl_result, 1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        set_btn(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        set_btn(buttons.button(QDialogButtonBox.StandardButton.Cancel), "secondary")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _preview(self) -> Tuple[List[dict], List[str]]:
        buttons, errors = parse_button_lines(self.edit_lines.toPlainText())
        parts = [f"解析出 {len(buttons)} 条"]
        if errors:
            parts.append("；".join(errors[:5]))
            if len(errors) > 5:
                parts.append(f"（另有 {len(errors) - 5} 条问题）")
        self.lbl_result.setText("；".join(parts))
        return buttons, errors

    def _on_accept(self):
        buttons, errors = self._preview()
        if not buttons:
            QMessageBox.warning(self, "没有可导入的报文", "请检查内容格式。")
            return
        if errors:
            answer = QMessageBox.question(
                self, "存在问题的行",
                "以下行无法导入：\n" + "\n".join(errors[:10])
                + (f"\n…另有 {len(errors) - 10} 条" if len(errors) > 10 else "")
                + f"\n\n继续导入其余 {len(buttons)} 条？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._buttons = buttons
        self.accept()

    def buttons(self) -> List[dict]:
        return list(self._buttons)


# ── 主页面 ──────────────────────────────────────────────────────────────────


class BluetoothToolWidget(QWidget):
    """蓝牙工具页：扫描 / 连接 BLE、收发、解析联动、虚拟模式透传、自定义报文按钮。

    接线约定（与 `serial_tool_widget` 一致，本页**不** import `main_gui`）：

    - :meth:`set_bluetooth_worker` —— 注入 BLE 通信线程（缺省由本页自建）；
    - :meth:`set_serial_worker` —— 注入主窗口**共享**的串口线程（虚拟模式透传用）；
    - :meth:`set_parse_provider` —— 注入解析回调 ``(frame, protocol) -> (摘要, 表)``；
    - :meth:`set_protocol_provider` —— 注入「当前协议索引」回调；
    - :meth:`set_send_to_single_handler` —— 注入「送入单帧解析」回调。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # 用属性访问（不是 from ... import data_path）：便于测试用
        # `_config_sandbox` patch `app_paths.data_path` 把落盘重定向到沙箱
        self._config_path = str(app_paths.data_path(CONFIG_NAME))
        self._settings: Dict[str, object] = dict(core.DEFAULT_SETTINGS)
        self._buttons: List[dict] = []

        # BLE 通信线程：与串口不同，蓝牙设备不存在「全局唯一句柄」的约束，
        # 本页自持即可；仍提供注入入口（测试用假 worker、或主窗口想统一托管）。
        self._worker = None
        self._worker_connections: List[Tuple[object, object]] = []

        # 串口：**复用主窗口共享的 SerialWorker**（虚拟模式透传），不另开 COM 口
        self._serial_worker = None
        self._serial_connected = False

        # 注入的能力（本页不 import main_gui，避免循环依赖）
        self._parse_provider = None
        self._protocol_provider = None
        self._send_to_single_handler = None

        # 设备表：地址 → {name, address, rssi}
        self._devices: Dict[str, dict] = {}
        self._scanning = False
        self._scan_stop = False
        # 连接中的设备（用于日志与失败提示）
        self._pending_connect: Dict[str, str] = {}
        # 已发现的特征码（连接后由 worker 投递）
        self._chars: List[dict] = []
        self._recv_uuids: List[str] = []
        self._send_uuids: List[str] = []
        # 载入配置期间屏蔽「开启虚拟模式」之类的提示（避免每次启动都刷一条 warn）
        self._loading = False
        self._dark = False

        # 日志
        self._log_queue: deque = deque()
        self._log_writer: Optional[LogFileWriter] = None
        self._log_last_path = ""
        self._log_last_lines = 0
        self._log_line_count = 0        # 窗口当前行数（超限裁剪用）

        # 收发字节（虚拟模式下串口侧的字节另计，不混入蓝牙统计）
        self._rx_bytes = 0
        self._tx_bytes = 0

        # 自定义报文按钮控件（重建时逐个销毁）
        self._custom_buttons: List[QPushButton] = []

        # 一键探测会话（纯逻辑状态机；None = 没有进行中的探测）
        self._probe = None
        # 探测前的收发选择（全败时原样恢复，不让「最后一个试过的候选」留在界面上）
        self._probe_restore = ([], [])

        # 落盘定时器必须**先于** `_build_ui()/_load_persisted()` 建好：
        # 载入持久化参数会触发控件的 `toggled` → `_schedule_save()`，那时若还没有
        # `_save_timer`，信号槽里会抛 AttributeError（Qt 会吞掉，但配置保存随之失效）。
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_persisted)

        self._build_ui()
        self._load_persisted()

        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._flush_log_queue)
        self._log_timer.start(LOG_FLUSH_MS)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status_line)
        self._status_timer.start(300)

        # 一键探测的单步计时（订阅/写入/等回包三个阶段共用同一个兜底定时器）
        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.timeout.connect(self._probe_timeout)

        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh_tick)

        self._ensure_worker()
        self._log("[系统] 蓝牙工具就绪：点「扫描设备」→ 选中设备 → 「连接」→「特征码…」选择通道",
                  "sys")
        if not self._bleak_ready():
            self._log(f"[提醒] {BLEAK_MISSING_HINT}", "warn")
            self.btn_scan.setEnabled(False)
            self.btn_connect.setEnabled(False)

    # ── 接线（由 main_gui 调用）───────────────────────────────────────────

    def _ensure_worker(self):
        """惰性创建本页自持的 BLE 通信线程并接好信号。"""
        if self._worker is not None:
            return self._worker
        self._worker = BluetoothWorker()
        self._connect_worker()
        return self._worker

    def set_bluetooth_worker(self, worker):
        """注入 BLE 通信线程（默认本页自建；测试可注入假 worker）。

        替换时**先断开旧信号再 `shutdown()` 旧线程**，避免旧线程的信号继续投到本页。
        """
        if worker is self._worker:
            return
        old = self._worker
        self._disconnect_worker()
        if old is not None:
            try:
                old.shutdown()
            except Exception:
                pass
        self._worker = worker
        self._connect_worker()
        self._on_connection_changed(bool(worker is not None and worker.is_connected()))

    def bluetooth_worker(self):
        """当前 BLE 通信线程（可能为 None —— 本页销毁后）。"""
        return self._worker

    def _connect_worker(self):
        worker = self._worker
        if worker is None:
            return
        pairs = (
            (worker.scan_started, self._on_scan_started),
            (worker.device_found, self._on_device_found),
            (worker.scan_finished, self._on_scan_finished),
            (worker.scan_error, self._on_scan_error),
            (worker.connecting, self._on_connecting),
            (worker.connected, self._on_connected),
            (worker.connect_error, self._on_connect_error),
            (worker.disconnected, self._on_disconnected),
            (worker.connection_changed, self._on_connection_changed),
            (worker.characteristics_updated, self._on_characteristics_updated),
            (worker.subscribe_finished, self._probe_subscribed),
            (worker.frame_received, self._on_frame_received),
            (worker.send_progress, self._on_send_progress),
            (worker.data_sent, self._on_data_sent),
            (worker.log_message, self._on_worker_log),
            (worker.error_occurred, self._on_worker_error),
            (worker.stats_changed, self._on_stats_changed),
        )
        for signal, slot in pairs:
            try:
                signal.connect(slot)
                self._worker_connections.append((signal, slot))
            except (TypeError, RuntimeError):
                pass

    def _disconnect_worker(self):
        for signal, slot in self._worker_connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._worker_connections.clear()

    def set_serial_worker(self, worker):
        """绑定主窗口共享的串口线程（与组帧页/监控器页同一约定）。

        只订阅信号，**不负责打开/关闭端口**：端口生命周期归顶部「串口配置」。
        """
        old = self._serial_worker
        if old is not None:
            for signal, slot in (
                (old.raw_data_received, self._on_serial_data),
                (old.connection_changed, self._on_serial_connection_changed),
                (old.error_occurred, self._on_serial_error),
            ):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        self._serial_worker = worker
        if worker is None:
            self._on_serial_connection_changed(False)
            return
        worker.raw_data_received.connect(self._on_serial_data)
        worker.connection_changed.connect(self._on_serial_connection_changed)
        worker.error_occurred.connect(self._on_serial_error)
        self._on_serial_connection_changed(worker.is_open())

    def set_parse_provider(self, provider):
        """注入解析回调 ``provider(frame_bytes, protocol_index) -> (摘要, table_data)``。"""
        self._parse_provider = provider
        if hasattr(self, "combo_protocol"):
            self._rebuild_protocol_combo()

    def set_protocol_provider(self, provider):
        """注入「当前协议索引」回调 ``provider() -> Optional[int]``（用户手选优先）。"""
        self._protocol_provider = provider

    def set_send_to_single_handler(self, handler):
        """注入「送入单帧解析」回调 ``handler(hex_str)``（与监控器页同一约定）。"""
        self._send_to_single_handler = handler

    def _bleak_ready(self) -> bool:
        worker = self._worker
        try:
            return bool(worker is not None and worker.bleak_available())
        except Exception:
            return False

    # ── UI 构建 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        self._build_toolbar(layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([430, 740])
        layout.addWidget(splitter, 1)

        self._build_status_line(layout)

    def _build_toolbar(self, layout):
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.btn_scan = QPushButton("扫描设备")
        set_btn(self.btn_scan, "primary")
        self.btn_scan.setIcon(app_icons.load_icon("bluetooth-searching"))
        self.btn_scan.setToolTip("扫描周边 BLE 设备（结果按信号强度排序）")
        self.btn_scan.clicked.connect(self._on_scan_clicked)
        bar.addWidget(self.btn_scan)

        self.btn_stop_scan = QPushButton("停止扫描")
        set_btn(self.btn_stop_scan, "secondary")
        self.btn_stop_scan.setIcon(app_icons.load_icon("x"))
        self.btn_stop_scan.clicked.connect(self._on_stop_scan)
        bar.addWidget(self.btn_stop_scan)

        self.btn_connect = QPushButton("连接")
        set_btn(self.btn_connect, "success")
        self.btn_connect.setIcon(app_icons.load_icon("bluetooth-connected"))
        self.btn_connect.setToolTip("连接设备表中选中的设备（双击设备行等效）")
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        bar.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("断开")
        set_btn(self.btn_disconnect, "danger")
        self.btn_disconnect.setIcon(app_icons.load_icon("bluetooth-off"))
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        bar.addWidget(self.btn_disconnect)

        self.btn_chars = QPushButton("特征码…")
        set_btn(self.btn_chars, "secondary")
        self.btn_chars.setIcon(app_icons.load_icon("settings-2"))
        self.btn_chars.setToolTip("选择接收（notify/indicate）与发送（write）特征码")
        self.btn_chars.clicked.connect(self._on_choose_characteristics)
        bar.addWidget(self.btn_chars)

        self.btn_probe_chars = QPushButton("自动探测")
        set_btn(self.btn_probe_chars, "secondary")
        self.btn_probe_chars.setIcon(app_icons.load_icon("bluetooth-searching"))
        self.btn_probe_chars.setToolTip(
            "一键探测收发通道：按属性打分顺序逐个试「订阅 → 写一帧 → 等回包」，命中即锁定。\n"
            "⚠ 会**真的向设备写入**一帧 —— 默认用发送框里的报文；\n"
            "发送框为空时用配置的默认探测帧（probe_frame，默认 AT）"
        )
        self.btn_probe_chars.clicked.connect(self._start_probe)
        bar.addWidget(self.btn_probe_chars)

        self.btn_reset_stats = QPushButton("统计清零")
        set_btn(self.btn_reset_stats, "secondary")
        self.btn_reset_stats.setIcon(app_icons.load_icon("refresh-cw"))
        self.btn_reset_stats.clicked.connect(self._on_reset_stats)
        bar.addWidget(self.btn_reset_stats)

        bar.addStretch()
        fit_btn_width(
            self.btn_scan, self.btn_stop_scan, self.btn_connect,
            self.btn_disconnect, self.btn_chars, self.btn_reset_stats,
        )
        layout.addLayout(bar)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # ① 设备列表
        dev_group = QGroupBox("设备列表")
        dev_layout = QVBoxLayout(dev_group)
        dev_layout.setContentsMargins(6, 8, 6, 6)
        dev_layout.setSpacing(4)

        self.device_table = ZoomableTableWidget()
        self.device_table.setColumnCount(len(DEVICE_COLUMNS))
        self.device_table.setHorizontalHeaderLabels(list(DEVICE_COLUMNS))
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.device_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.device_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.device_table.setAlternatingRowColors(True)
        self.device_table.verticalHeader().hide()
        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.device_table.setColumnWidth(1, 140)
        self.device_table.setColumnWidth(2, 110)
        self.device_table.setColumnWidth(3, 76)
        self.device_table.verticalHeader().setDefaultSectionSize(20)
        self.device_table.itemDoubleClicked.connect(self._on_device_double_clicked)
        dev_layout.addWidget(self.device_table, 1)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.chk_named_only = QCheckBox("只显示有名称的设备")
        self.chk_named_only.setToolTip("无名设备多为随机地址，现场通常不关心")
        self.chk_named_only.toggled.connect(self._on_named_only_toggled)
        filter_row.addWidget(self.chk_named_only)

        self.chk_auto_refresh = QCheckBox("扫描后自动重扫")
        self.chk_auto_refresh.toggled.connect(self._on_auto_refresh_toggled)
        filter_row.addWidget(self.chk_auto_refresh)

        self.spin_refresh = QSpinBox()
        self.spin_refresh.setRange(*core.SCAN_INTERVAL_RANGE)
        self.spin_refresh.setSuffix(" s")
        self.spin_refresh.setToolTip("自动重扫间隔")
        self.spin_refresh.valueChanged.connect(lambda _v: self._schedule_save())
        filter_row.addWidget(self.spin_refresh)
        filter_row.addStretch()
        dev_layout.addLayout(filter_row)
        outer.addWidget(dev_group, 1)

        # ② 连接信息
        info_group = QGroupBox("连接信息")
        info_form = QFormLayout(info_group)
        info_form.setContentsMargins(6, 8, 6, 6)
        info_form.setSpacing(4)
        self.lbl_info_device = self._info_label()
        self.lbl_info_address = self._info_label()
        self.lbl_info_mtu = self._info_label()
        self.lbl_info_chars = self._info_label()
        info_form.addRow("设备：", self.lbl_info_device)
        info_form.addRow("地址：", self.lbl_info_address)
        info_form.addRow("MTU：", self.lbl_info_mtu)
        info_form.addRow("特征码：", self.lbl_info_chars)
        outer.addWidget(info_group)

        # ③ 参数
        param_group = QGroupBox("参数")
        param_form = QFormLayout(param_group)
        param_form.setContentsMargins(6, 8, 6, 6)
        param_form.setSpacing(4)

        self.spin_timeout = QDoubleSpinBox()
        self.spin_timeout.setRange(*core.PACKET_TIMEOUT_RANGE)
        self.spin_timeout.setSingleStep(0.05)
        self.spin_timeout.setDecimals(3)
        self.spin_timeout.setSuffix(" s")
        self.spin_timeout.setToolTip(
            "BLE 通知静默多久算「一帧完整报文」\n"
            "设备把一帧拆成多个通知时，按此超时重组后再显示与解析"
        )
        self.spin_timeout.valueChanged.connect(self._on_timeout_changed)
        param_form.addRow("切帧超时：", self.spin_timeout)

        self.spin_packet_delay = QDoubleSpinBox()
        self.spin_packet_delay.setRange(*core.SEND_PACKET_DELAY_RANGE)
        self.spin_packet_delay.setSingleStep(0.01)
        self.spin_packet_delay.setDecimals(3)
        self.spin_packet_delay.setSuffix(" s")
        self.spin_packet_delay.setToolTip("写入分包之间的间隔（部分设备需要留出处理时间）")
        self.spin_packet_delay.valueChanged.connect(self._on_packet_delay_changed)
        param_form.addRow("包间延迟：", self.spin_packet_delay)
        outer.addWidget(param_group)

        return panel

    @staticmethod
    def _info_label() -> QLabel:
        label = QLabel("—")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.addWidget(self._build_log_group(), 1)
        outer.addWidget(self._build_send_group())
        outer.addWidget(self._build_custom_group())
        return panel

    # ── 日志区 ──────────────────────────────────────────────────────────

    def _build_log_group(self) -> QGroupBox:
        group = QGroupBox("日志")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(4)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(_mono_font())
        self.log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_text.setToolTip("蓝牙收发/解析日志（窗口只保留最近若干行，文件不截断）")
        layout.addWidget(self.log_text, 1)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.chk_show_hex = QCheckBox("HEX 显示")
        self.chk_show_hex.setToolTip("载荷按十六进制显示（取消则按 ASCII）；对之后的行生效")
        self.chk_show_hex.toggled.connect(lambda _c: self._schedule_save())
        row1.addWidget(self.chk_show_hex)

        self.chk_auto_scroll = QCheckBox("自动滚动")
        self.chk_auto_scroll.toggled.connect(lambda _c: self._schedule_save())
        row1.addWidget(self.chk_auto_scroll)

        self.chk_parse = QCheckBox("解析收到的报文")
        self.chk_parse.setToolTip("收到的完整报文按下面选定的协议解析，输出摘要 + 字段行")
        self.chk_parse.toggled.connect(self._on_parse_toggled)
        row1.addWidget(self.chk_parse)

        row1.addWidget(QLabel("协议："))
        self.combo_protocol = QComboBox()
        self.combo_protocol.setToolTip("解析用协议；跟随主窗口当前协议（此处可临时改写）")
        self.combo_protocol.currentIndexChanged.connect(self._on_parse_protocol_changed)
        row1.addWidget(self.combo_protocol)

        row1.addWidget(QLabel("行数上限："))
        self.spin_parse_lines = QSpinBox()
        self.spin_parse_lines.setRange(*core.PARSE_MAX_LINES_RANGE)
        self.spin_parse_lines.setToolTip("0 = 不限制（一条应答帧常有上百行字段）")
        self.spin_parse_lines.valueChanged.connect(lambda _v: self._schedule_save())
        row1.addWidget(self.spin_parse_lines)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.btn_clear_log = QPushButton("清空日志")
        set_btn(self.btn_clear_log, "secondary", "sm")
        set_btn_icon(self.btn_clear_log, "clear")
        self.btn_clear_log.clicked.connect(self._on_clear_log)
        row2.addWidget(self.btn_clear_log)

        self.btn_save_log = QPushButton("保存当前日志…")
        set_btn(self.btn_save_log, "secondary", "sm")
        set_btn_icon(self.btn_save_log, "save")
        self.btn_save_log.setToolTip(
            "把日志窗口当前内容另存为一个文件（不影响「自动保存日志」）\n"
            f"注意：窗口只保留最近 {WINDOW_KEEP_LINES} 行，需要完整日志请用「自动保存日志」"
        )
        self.btn_save_log.clicked.connect(self._save_log_now)
        row2.addWidget(self.btn_save_log)

        self.chk_auto_save_log = QCheckBox("自动保存日志")
        self.chk_auto_save_log.setToolTip("实时把日志窗口内容写入文件（文件是窗口内容的完整镜像）")
        self.chk_auto_save_log.toggled.connect(self._on_auto_save_toggled)
        row2.addWidget(self.chk_auto_save_log)

        self.chk_log_stamp = QCheckBox("行首时间戳")
        self.chk_log_stamp.toggled.connect(self._on_log_stamp_toggled)
        row2.addWidget(self.chk_log_stamp)

        self.btn_log_dir = QPushButton("选择目录…")
        set_btn(self.btn_log_dir, "secondary", "sm")
        set_btn_icon(self.btn_log_dir, "open")
        self.btn_log_dir.clicked.connect(self._choose_log_dir)
        row2.addWidget(self.btn_log_dir)

        self.btn_open_log_dir = QPushButton("打开目录")
        set_btn(self.btn_open_log_dir, "secondary", "sm")
        set_btn_icon(self.btn_open_log_dir, "open_file")
        self.btn_open_log_dir.setToolTip("在资源管理器中打开日志目录")
        self.btn_open_log_dir.clicked.connect(self._open_log_directory)
        row2.addWidget(self.btn_open_log_dir)
        row2.addStretch()
        layout.addLayout(row2)

        self.lbl_log_state = QLabel("未开启自动保存")
        self.lbl_log_state.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.lbl_log_state)
        self._rebuild_protocol_combo()
        return group

    # ── 发送区 ──────────────────────────────────────────────────────────

    def _build_send_group(self) -> QGroupBox:
        group = QGroupBox("发送")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel("内容："))
        self.edit_send = QLineEdit()
        self.edit_send.setFont(_mono_font())
        self.edit_send.setPlaceholderText("HEX（68 12 00 41 16）或 ASCII 文本（AT+INFO?）")
        self.edit_send.setToolTip(
            "格式由右侧「格式」决定：自动 = 像 HEX 就按 HEX（写错会报错，不会误按文本发）"
        )
        self.edit_send.textChanged.connect(self._refresh_send_hint)
        self.edit_send.returnPressed.connect(self._on_send_clicked)
        row.addWidget(self.edit_send, 1)

        self.combo_send_format = QComboBox()
        for label, value in SEND_FORMATS:
            self.combo_send_format.addItem(label, value)
        self.combo_send_format.setToolTip(
            "自动：内容只含 hex 字符与分隔符时按 HEX，否则按 UTF-8 文本\n"
            "HEX 字节：强制按 HEX（无效则报错）\n"
            "ASCII 文本：强制按 UTF-8 文本发送"
        )
        self.combo_send_format.currentIndexChanged.connect(self._on_send_format_changed)
        row.addWidget(self.combo_send_format)

        self.btn_send = QPushButton("发送")
        set_btn(self.btn_send, "primary")
        self.btn_send.setIcon(app_icons.load_icon("send"))
        self.btn_send.clicked.connect(self._on_send_clicked)
        row.addWidget(self.btn_send)

        self.btn_send_parse = QPushButton("送入单帧解析")
        set_btn(self.btn_send_parse, "secondary")
        self.btn_send_parse.setToolTip("把输入框内容送进主窗口的「单帧解析」页逐字段解析")
        self.btn_send_parse.clicked.connect(self._on_send_to_parse)
        row.addWidget(self.btn_send_parse)
        fit_btn_width(self.btn_send, self.btn_send_parse)
        layout.addLayout(row)

        self.lbl_send_hint = QLabel("")
        self.lbl_send_hint.setWordWrap(True)
        layout.addWidget(self.lbl_send_hint)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.chk_virtual = QCheckBox("虚拟模式（蓝牙 ⇄ 串口透传）")
        self.chk_virtual.setToolTip(
            "打开后：BLE 收到的数据原样写入串口，串口收到的数据原样写入 BLE\n"
            "（把蓝牙模块当成无线串口延长线）\n"
            "串口的连接/波特率在顶部「串口配置」里设置"
        )
        self.chk_virtual.toggled.connect(self._on_virtual_toggled)
        row2.addWidget(self.chk_virtual)

        self.lbl_serial_state = QLabel("串口：未连接")
        row2.addWidget(self.lbl_serial_state)
        row2.addStretch()
        layout.addLayout(row2)
        return group

    # ── 自定义报文 ──────────────────────────────────────────────────────

    def _build_custom_group(self) -> QGroupBox:
        self.custom_group = QGroupBox("自定义报文")
        layout = QVBoxLayout(self.custom_group)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(4)

        self.custom_host = QWidget()
        self.custom_grid = QGridLayout(self.custom_host)
        self.custom_grid.setContentsMargins(0, 0, 0, 0)
        self.custom_grid.setSpacing(4)
        layout.addWidget(self.custom_host)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_custom_add = QPushButton("新增…")
        set_btn(self.btn_custom_add, "secondary", "sm")
        set_btn_icon(self.btn_custom_add, "add")
        self.btn_custom_add.clicked.connect(self._on_custom_add)
        row.addWidget(self.btn_custom_add)

        self.btn_custom_batch = QPushButton("批量新增…")
        set_btn(self.btn_custom_batch, "secondary", "sm")
        self.btn_custom_batch.setIcon(app_icons.load_icon("list-plus"))
        self.btn_custom_batch.setToolTip("每行一条：名称,内容[,HEX|ASCII]")
        self.btn_custom_batch.clicked.connect(self._on_custom_batch)
        row.addWidget(self.btn_custom_batch)

        self.btn_custom_export = QPushButton("导出…")
        set_btn(self.btn_custom_export, "secondary", "sm")
        set_btn_icon(self.btn_custom_export, "export")
        self.btn_custom_export.clicked.connect(self._on_custom_export)
        row.addWidget(self.btn_custom_export)

        self.btn_custom_import = QPushButton("导入…")
        set_btn(self.btn_custom_import, "secondary", "sm")
        set_btn_icon(self.btn_custom_import, "open")
        self.btn_custom_import.setToolTip("从 JSON 文件导入自定义报文按钮（追加到现有列表）")
        self.btn_custom_import.clicked.connect(self._on_custom_import)
        row.addWidget(self.btn_custom_import)

        self.btn_custom_clear = QPushButton("全部清除")
        set_btn(self.btn_custom_clear, "secondary", "sm")
        set_btn_icon(self.btn_custom_clear, "delete")
        self.btn_custom_clear.clicked.connect(self._on_custom_clear)
        row.addWidget(self.btn_custom_clear)
        row.addStretch()

        hint = QLabel("提示：报文按钮上点右键可编辑 / 删除 / 移位")
        row.addWidget(hint)
        layout.addLayout(row)
        fit_btn_width(self.btn_custom_add, self.btn_custom_batch,
                      self.btn_custom_export, self.btn_custom_import,
                      self.btn_custom_clear)
        return self.custom_group

    # ── 状态行 ──────────────────────────────────────────────────────────

    def _build_status_line(self, layout):
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)
        self._refresh_status_line()

    # ── 扫描 ────────────────────────────────────────────────────────────

    def _on_scan_clicked(self):
        worker = self._ensure_worker()
        if worker is None:
            return
        if not self._bleak_ready():
            self._log(f"[提醒] {BLEAK_MISSING_HINT}", "warn")
            return
        if worker.is_connected():
            # 已连接时扫描不影响连接（bleak 支持并发扫描），这里只提示一下
            self._log("[蓝牙] 已连接状态下重新扫描设备…", "ble")
        self._devices.clear()
        self._refresh_device_table()
        self._on_scan_started()
        if not worker.start_scan():
            self._scanning = False
            self.btn_scan.setEnabled(True)
            self.btn_stop_scan.setEnabled(False)
            self._log("[提醒] 扫描未启动（可能已有扫描在进行）", "warn")

    def _on_stop_scan(self):
        """请求停止本次扫描。

        说明：bleak 的 ``discover(timeout=...)`` 无法中途取消，这里**只停止收结果**
        （界面立刻可用），扫描在超时后自然结束。不假装已经取消。
        """
        if not self._scanning:
            return
        self._scan_stop = True
        self._log("[蓝牙] 已停止接收扫描结果（本次扫描将在超时后结束）", "sys")

    def _on_scan_started(self):
        self._scanning = True
        self._scan_stop = False
        self.btn_scan.setEnabled(False)
        self.btn_stop_scan.setEnabled(True)
        self.lbl_status.setText("正在扫描 BLE 设备…")

    def _on_device_found(self, name: str, address: str, rssi: int):
        if getattr(self, "_scan_stop", False):
            return
        self._devices[str(address)] = {
            "name": str(name or ""), "address": str(address), "rssi": int(rssi or 0),
        }
        self._refresh_device_table()

    def _on_scan_finished(self, count: int):
        self._scanning = False
        if getattr(self, "_scan_stop", False):
            self._scan_stop = False
            self._log(f"[蓝牙] 扫描已结束（本次共收到 {len(self._devices)} 个设备）", "sys")
        else:
            self._log(f"[蓝牙] 扫描完成：发现 {count} 个设备", "ble")
        self.btn_scan.setEnabled(True)
        self.btn_stop_scan.setEnabled(False)
        self._refresh_device_table()
        self._refresh_status_line()
        self._maybe_auto_refresh()

    def _on_scan_error(self, message: str):
        self._scanning = False
        self.btn_scan.setEnabled(True)
        self.btn_stop_scan.setEnabled(False)
        self._log(f"[蓝牙] {message}", "fail")
        self._refresh_status_line()

    def _on_named_only_toggled(self, _checked: bool):
        self._refresh_device_table()
        self._schedule_save()

    def _refresh_device_table(self):
        """按当前设置重建设备表（保持选中行）。"""
        selected = self._selected_address()
        connected = ""
        worker = self._worker
        if worker is not None:
            try:
                if worker.is_connected():
                    connected = worker.device_address()
            except Exception:
                connected = ""
        last = str(self._settings.get("last_device") or "")
        named_only = bool(self.chk_named_only.isChecked())

        rows = sorted(
            self._devices.values(),
            key=lambda d: (-int(d.get("rssi") or 0), not bool(d.get("name"))),
        )
        self.device_table.setUpdatesEnabled(False)
        try:
            self.device_table.setRowCount(0)
            for device in rows:
                name = str(device.get("name") or "")
                if named_only and not name:
                    continue
                address = str(device.get("address") or "")
                if address == connected:
                    status = "已连接"
                elif address == last:
                    status = "上次"
                else:
                    status = ""
                row = self.device_table.rowCount()
                self.device_table.insertRow(row)
                for col, text in enumerate(
                    (name or "（无名）", address, rssi_text(device.get("rssi")), status)
                ):
                    item = QTableWidgetItem(str(text))
                    if col == 3 and status:
                        item.setForeground(QColor(
                            self._theme_color(status == "已连接")
                        ))
                    if col == 0:
                        item.setToolTip(f"{name or '（无名设备）'}\n{address}")
                    self.device_table.setItem(row, col, item)
            if selected:
                self._select_address(selected)
        finally:
            self.device_table.setUpdatesEnabled(True)

    def _selected_address(self) -> str:
        row = self.device_table.currentRow()
        if row < 0:
            return ""
        item = self.device_table.item(row, 1)
        return item.text() if item is not None else ""

    def _select_address(self, address: str):
        for row in range(self.device_table.rowCount()):
            item = self.device_table.item(row, 1)
            if item is not None and item.text() == address:
                self.device_table.selectRow(row)
                return

    def _selected_device(self) -> Optional[dict]:
        address = self._selected_address()
        if not address:
            return None
        device = self._devices.get(address)
        if device is not None:
            return device
        return {"name": "", "address": address, "rssi": 0}

    def _on_device_double_clicked(self, item):
        if item is None:
            return
        self._on_connect_clicked()

    # ── 自动重扫 ────────────────────────────────────────────────────────

    def _on_auto_refresh_toggled(self, checked: bool):
        if checked and not self._scanning:
            self._auto_refresh_timer.start(int(self.spin_refresh.value()) * 1000)
        elif not checked:
            self._auto_refresh_timer.stop()
        self._schedule_save()

    def _maybe_auto_refresh(self):
        """手动扫描结束后，若勾选了自动重扫则启动下一次。"""
        if self.chk_auto_refresh.isChecked():
            self._auto_refresh_timer.start(int(self.spin_refresh.value()) * 1000)
        else:
            self._auto_refresh_timer.stop()

    def _on_auto_refresh_tick(self):
        if self._scanning or self._worker is None:
            return
        if not self.chk_auto_refresh.isChecked():
            self._auto_refresh_timer.stop()
            return
        if not self._bleak_ready():
            self._auto_refresh_timer.stop()
            return
        self._devices.clear()
        self._on_scan_started()
        if not self._worker.start_scan():
            self._scanning = False
            self.btn_scan.setEnabled(True)
            self.btn_stop_scan.setEnabled(False)
        self._auto_refresh_timer.start(int(self.spin_refresh.value()) * 1000)

    # ── 连接 / 断开 ─────────────────────────────────────────────────────

    def _on_connect_clicked(self):
        worker = self._ensure_worker()
        if worker is None:
            return
        if worker.is_connected():
            self._log("[提醒] 已连接，请先「断开」再连接其它设备", "warn")
            return
        device = self._selected_device()
        if device is None:
            QMessageBox.information(self, "未选择设备", "请先扫描并在设备表中选中一台设备。")
            return
        address = str(device.get("address") or "")
        if not address:
            return
        self._pending_connect = {"address": address, "name": str(device.get("name") or "")}
        if not worker.connect_device(address, device.get("name") or ""):
            self._pending_connect = {}

    def _on_disconnect_clicked(self):
        worker = self._worker
        if worker is None:
            return
        if not worker.is_connected():
            self._log("[提醒] 当前未连接蓝牙设备", "warn")
            return
        worker.disconnect_device()

    def _on_connecting(self, address: str, name: str):
        self.btn_connect.setEnabled(False)
        self.lbl_status.setText(f"正在连接 {name or address} …")
        self.lbl_info_device.setText(name or address)
        self.lbl_info_address.setText(address)

    def _on_connected(self, name: str, address: str):
        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(True)
        self.btn_chars.setEnabled(True)
        self.lbl_info_device.setText(name or address)
        self.lbl_info_address.setText(address)
        worker = self._worker
        mtu = 0
        if worker is not None:
            try:
                mtu = int(worker.mtu_size() or 0)
            except Exception:
                mtu = 0
        self.lbl_info_mtu.setText(
            f"{mtu} 字节（单包上限 {core.chunk_size_for_mtu(mtu)}）" if mtu
            else "未知（按 ATT 最小值 20 字节分包）"
        )
        # 换到一台**没记过**的设备：清掉上一台的选择（否则会压住自动优选 ——
        # `_on_characteristics_updated` 只在「未选过」时才优选）。同设备重连或首次连接不清。
        previous_device = str(self._settings.get("last_device") or "").strip()
        address_key = str(address or "").strip()
        if (address_key and previous_device and address_key != previous_device
                and core.recall_choice(self._settings, address_key) is None):
            self._recv_uuids, self._send_uuids = [], []
        # 记住本次连接的设备（下次启动在设备表里高亮）
        self._settings["last_device"] = address_key or str(address)
        self._settings["last_device_name"] = str(name or "")
        self._schedule_save()
        self._refresh_device_table()
        self._refresh_status_line()

    def _on_connect_error(self, message: str):
        self._pending_connect = {}
        self.btn_connect.setEnabled(True)
        self._log(f"[蓝牙] 连接失败：{message}", "fail")
        self.lbl_status.setText("连接失败")
        QMessageBox.critical(self, "连接失败", message)

    def _on_disconnected(self):
        self.btn_disconnect.setEnabled(False)
        self.btn_chars.setEnabled(False)
        self.btn_connect.setEnabled(True)
        self.lbl_info_mtu.setText("—")
        self.lbl_info_chars.setText("—")
        self._refresh_device_table()
        self._refresh_status_line()

    def _on_connection_changed(self, connected: bool):
        self.btn_connect.setEnabled(not connected)
        self.btn_disconnect.setEnabled(bool(connected))
        self.btn_chars.setEnabled(bool(connected))
        self.btn_probe_chars.setEnabled(bool(connected) and self._probe is None)
        if not connected and self._probe is not None:
            # 连接断了：探测无法继续，明确收尾（不留下半截状态）
            self._finish_probe()
        if connected:
            self._log("[蓝牙] 已连接", "ble")
        self._refresh_status_line()

    # ── 特征码 ──────────────────────────────────────────────────────────

    def _on_characteristics_updated(self, characteristics):
        self._chars = [dict(c) for c in (characteristics or []) if isinstance(c, dict)]
        recv_ready = sum(1 for c in self._chars if c.get("can_recv"))
        send_ready = sum(1 for c in self._chars if c.get("can_send"))
        self.lbl_info_chars.setText(
            f"{len(self._chars)} 个（可接收 {recv_ready} / 可发送 {send_ready}）"
        )
        # ① 该**设备地址**记过 → 直接沿用（省去重新优选；换设备自然走 ②）
        remembered = core.recall_choice(self._settings, self._current_address())
        if remembered and (remembered.get("recv") or remembered.get("send")):
            self._apply_characteristics(remembered.get("recv"), remembered.get("send"),
                                        source="recall", announce=True)
            return
        # ② 打分优选（**不是**「取第一个可用」—— 那条路常落到设备名/电量/DFU 特征码上）
        if not self._recv_uuids or not self._send_uuids:
            recv, send, reason = core.pick_auto(self._chars)
            if recv or send:
                self._apply_characteristics(recv, send, source="auto", announce=True,
                                            reason=reason)
                return
        if not self._chars:
            self._log("[提醒] 未发现可用特征码，无法收发", "warn")
        else:
            self._log(
                f"[蓝牙] 发现 {len(self._chars)} 个特征码；未选择时会**按属性自动优选**收发通道，"
                "可用「特征码…」手工改，或点「自动探测」实测一遍",
                "sys",
            )

    @staticmethod
    def _auto_pick(characteristics) -> Tuple[List[str], List[str]]:
        """自动优选（委托 `core.pick_auto`：按属性 + 厂商族谱打分排序，同分保持枚举顺序）。"""
        recv, send, _reason = core.pick_auto(characteristics)
        return recv, send

    def _current_address(self) -> str:
        """当前设备地址（未连接 / 假 worker 时回落「上次连接」）。"""
        worker = self._worker
        address = ""
        if worker is not None:
            try:
                address = str(worker.device_address() or "").strip()
            except Exception:  # noqa: BLE001 - 未实现该方法的假 worker
                address = ""
        return address or str(self._settings.get("last_device") or "").strip()

    def _short_uuid_join(self, uuids) -> str:
        return "、".join(core.short_uuid(u) for u in (uuids or []) if str(u or "").strip())

    def _apply_characteristics(self, recv_uuids, send_uuids, announce: bool = False,
                               source: str = "manual", reason: str = ""):
        """把选择结果下发给 worker，并**按设备地址**记忆（同时保留旧全局键兼容旧配置）。"""
        self._recv_uuids = [str(u) for u in (recv_uuids or []) if str(u or "").strip()]
        self._send_uuids = [str(u) for u in (send_uuids or []) if str(u or "").strip()]
        worker = self._worker
        if worker is not None:
            worker.set_characteristics(self._recv_uuids, self._send_uuids)
        self._settings["recv_uuids"] = list(self._recv_uuids)
        self._settings["send_uuids"] = list(self._send_uuids)
        core.remember_choice(self._settings, self._current_address(),
                             self._recv_uuids, self._send_uuids, source)
        self._schedule_save()
        self._refresh_status_line()
        if announce:
            lead = {
                "recall": "[蓝牙] 特征码（沿用上次该设备）",
                "auto": "[蓝牙] 自动选择特征码（按属性优选）",
                "probe": "[蓝牙] 特征码（一键探测已确认）",
            }.get(source, "[蓝牙] 特征码已更新")
            text = (f"{lead} —— 接收：{self._short_uuid_join(self._recv_uuids) or '无'}"
                    f"；发送：{self._short_uuid_join(self._send_uuids) or '无'}")
            if reason:
                text += f"（依据：{reason}）"
            self._log(text, "ble")

    # ── 一键探测（1.23.79）─────────────────────────────────────────────

    def _probe_payload(self):
        """探测载荷：优先发送框内容；空则用配置的默认探测帧（坏值回落内置默认并明确告知）。"""
        default_hex = str((self._settings or {}).get("probe_frame")
                          or core.DEFAULT_SETTINGS["probe_frame"])
        payload, error, source = core.resolve_probe_payload(
            self.edit_send.text(), self._send_mode(), default_hex, parse_plain_text)
        if payload is None and source == "default":
            fallback = str(core.DEFAULT_SETTINGS["probe_frame"])
            self._log(f"[提醒] 配置的默认探测帧无效（{error}）→ 本次改用内置默认 {fallback}", "warn")
            payload, error, source = core.resolve_probe_payload(
                "", "auto", fallback, parse_plain_text)
        if payload is None:
            return None, error
        if source == "default":
            self._log(f"[蓝牙] 发送框为空 → 使用默认探测帧 {default_hex}", "sys")
        return payload, ""

    def _start_probe(self):
        """一键探测：对打分排序的候选逐个「订阅 → 写 → 等回包」，命中即锁定。"""
        worker = self._worker
        if worker is None or not worker.is_connected():
            QMessageBox.information(self, "未连接", "请先连接蓝牙设备，再自动探测特征码。")
            return
        if self._probe is not None:
            self._log("[提醒] 上一次探测仍在进行，忽略重复点击", "warn")
            return
        chars = getattr(self, "_chars", None) or worker.characteristics()
        candidates = core.probe_candidates(chars)
        if not candidates:
            QMessageBox.information(self, "没有候选", "设备未提供可发送的特征码，无法探测。")
            return
        payload, error = self._probe_payload()
        if payload is None:
            self._log(f"[提醒] 探测载荷无效，未写入任何数据：{error}", "fail")
            QMessageBox.warning(self, "探测载荷无效", error)
            return
        timeout_ms = int((self._settings or {}).get("probe_timeout_ms", core.PROBE_TIMEOUT_MS))
        self._probe = core.ProbeSession(candidates, payload, timeout_ms)
        self._probe_restore = (list(self._recv_uuids), list(self._send_uuids))
        self.btn_probe_chars.setEnabled(False)
        self.btn_send.setEnabled(False)
        self._log(f"[探测] 开始：{len(candidates)} 个候选，单项超时 {self._probe.timeout_ms} ms，"
                  f"载荷 {len(payload)} 字节；失败会逐个给出原因", "sys")
        self._probe_step()

    def _probe_event(self, event: str, value=None):
        """把 worker 事件喂给探测会话；**仅当阶段真的前进时才推进**（避免重复下发同一意图）。"""
        session = self._probe
        if session is None:
            return
        before = session.step
        if event == "subscribed":
            session.on_subscribed(bool(value))
        elif event == "written":
            session.on_written(bool(value))
        elif event == "frame":
            session.on_frame(int(value or 0))
        elif event == "timeout":
            session.on_timeout()
        if session.step != before:
            self._probe_step()

    def _probe_step(self):
        """执行当前意图（select / write / wait）；意图为 None 时收尾。"""
        session = self._probe
        if session is None:
            return
        intent = session.next()
        if intent is None:
            self._finish_probe()
            return
        action = intent.get("action")
        index, total = session.position
        if action == "select":
            self._probe_timer.stop()
            send_uuid = (intent.get("send") or [""])[0]
            recv_uuid = ((intent.get("recv") or [""])[0] if intent.get("recv") else "")
            self._log(
                f"[探测] {index}/{total}：试写 {core.short_uuid(send_uuid)}"
                + (f"，接收 {core.short_uuid(recv_uuid)}" if recv_uuid else "（该候选无接收通道）"),
                "ble",
            )
            worker = self._worker
            if worker is None:
                session.stop()
                self._finish_probe()
                return
            # 先起表再调 worker：假 worker（或同线程快速路径）会**同步**回 subscribe_finished，
            # 重入的 _probe_step 会把表停掉并按新阶段重起 —— 顺序反了就会被外层覆盖
            self._probe_timer.start(session.timeout_ms)        # 订阅超时兜底
            worker.set_characteristics(intent.get("recv") or [], intent.get("send") or [])
        elif action == "write":
            self._probe_timer.stop()
            # 同理：先起表，再写入（同步 data_sent 的重入不会被覆盖）
            self._probe_timer.start(session.timeout_ms)        # data_sent / 回包 兜底
            worker = self._worker
            ok = False
            try:
                ok = bool(worker.send_data(intent.get("payload") or b""))
            except Exception as exc:  # noqa: BLE001 - 写入异常按失败处理，不炸界面
                self._log(f"[探测] 写入异常：{type(exc).__name__}: {exc}", "fail")
                ok = False
            if not ok:
                self._probe_event("written", False)
        elif action == "wait":
            self._probe_timer.start(int(intent.get("timeout_ms") or session.timeout_ms))
        else:
            self._finish_probe()

    def _probe_subscribed(self, uuids, ok: bool):
        """worker 订阅完成信号（没有探测在进行时是空操作）。"""
        self._probe_event("subscribed", ok)

    def _probe_timeout(self):
        """单步兜底超时（订阅 / 写入确认 / 等回包 三阶段共用）。"""
        self._probe_event("timeout")

    def _finish_probe(self):
        """收尾：恢复按钮、逐条汇报失败原因、命中则锁定并按设备记忆。"""
        session, self._probe = self._probe, None
        self._probe_timer.stop()
        worker = self._worker
        connected = False
        if worker is not None:
            try:
                connected = bool(worker.is_connected())
            except Exception:  # noqa: BLE001 - 假 worker 未实现时按未连接
                connected = False
        self.btn_probe_chars.setEnabled(connected)
        self.btn_send.setEnabled(True)
        if session is None:
            return
        result = session.result()
        for item in result.get("attempts", []):
            if item.get("status") == "ok":
                continue
            self._log(f"[探测] ✗ {item.get('label')}：{item.get('detail')}", "warn")
        winner = result.get("winner")
        if winner:
            self._apply_characteristics([winner["recv"]] if winner.get("recv") else [],
                                        [winner["send"]] if winner.get("send") else [],
                                        source="probe", announce=True,
                                        reason=str(result.get("detail") or ""))
        else:
            # 全败 → 恢复探测前的选择（否则界面上会停留在「最后一个试过的候选」，
            # 用户以为选对了，实际什么都没验证通过）
            recv, send = self._probe_restore
            self._recv_uuids, self._send_uuids = list(recv), list(send)
            worker2 = self._worker
            if worker2 is not None:
                worker2.set_characteristics(self._recv_uuids, self._send_uuids)
            self._refresh_status_line()
            self._log("[探测] 全部候选都未通过（原因见上）→ 已恢复探测前的选择；"
                      "可点「特征码…」手工选，或先在发送框填入该模块真正会响应的报文再探测", "warn")

    def _on_choose_characteristics(self):
        worker = self._worker
        if worker is None or not worker.is_connected():
            QMessageBox.information(self, "未连接", "请先连接蓝牙设备，再选择特征码。")
            return
        characteristics = getattr(self, "_chars", None) or worker.characteristics()
        if not characteristics:
            QMessageBox.information(self, "没有特征码", "设备未提供可用的特征码。")
            return
        dialog = CharacteristicSelectDialog(
            characteristics, self._recv_uuids, self._send_uuids, self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        recv = dialog.selected_recv()
        send = dialog.selected_send()
        self._apply_characteristics(recv, send)
        self._log(
            "[蓝牙] 特征码已更新 —— 接收："
            + ("、".join(core.short_uuid(u) for u in recv) or "无")
            + "；发送："
            + ("、".join(core.short_uuid(u) for u in send) or "无"),
            "ble",
        )
        if not recv and not send:
            self._log("[提醒] 接收与发送都没选，将无法收发数据", "warn")
        elif not recv:
            self._log("[提醒] 未选接收特征码，收不到设备上报", "warn")
        elif not send:
            self._log("[提醒] 未选发送特征码，发送会失败（会自动回落接收通道）", "warn")

    # ── 发送 ────────────────────────────────────────────────────────────

    def _send_mode(self) -> str:
        data = self.combo_send_format.currentData()
        return str(data or "auto")

    def _refresh_send_hint(self):
        """实时回显「按什么格式、发几个字节 / 哪里写错了」。

        用富文本而不是 setStyleSheet：内容每次按键都变，反复 polish 样式表会拖慢输入。
        """
        text = self.edit_send.text()
        if not text.strip():
            self.lbl_send_hint.clear()
            return
        payload, error = parse_plain_text(text, self._send_mode())
        if error:
            self.lbl_send_hint.setText(
                f'<span style="color:{_LOG_COLORS["fail"]}">⚠ {error}（不会发送）</span>'
            )
        else:
            self.lbl_send_hint.setText(
                f'<span style="color:{_LOG_COLORS["rx"]}">✓ 将发送 {len(payload)} 字节</span>'
            )

    def _on_send_format_changed(self, _index: int):
        self._refresh_send_hint()
        self._schedule_save()

    def _payload_from_edit(self) -> Optional[bytes]:
        payload, error = parse_plain_text(self.edit_send.text(), self._send_mode())
        if error:
            # 弹框是一次性的：用户一点确定就没了，日志里必须留一条（现场排查靠日志）。
            self._log(f"[提醒] 内容无效，未发送：{error}", "fail")
            QMessageBox.warning(self, "内容无效", error)
            return None
        return payload

    def _on_send_clicked(self):
        self._send_payload(self._payload_from_edit())


    def _send_payload(self, payload: Optional[bytes]):
        if payload is None:
            return
        worker = self._worker
        if worker is None or not worker.is_connected():
            self._log("[提醒] 未连接蓝牙设备，发送已取消（请先「扫描设备」并连接）", "warn")
            QMessageBox.information(self, "未连接", "请先连接蓝牙设备再发送。")
            return
        self._log(f"[TX] {format_payload(payload, self.chk_show_hex.isChecked())}"
                  f"（{len(payload)} 字节）", "tx")
        if not worker.send_data(payload):
            self._log("[提醒] 发送未被受理（检查连接与发送特征码）", "warn")

    def _on_send_to_parse(self):
        payload = self._payload_from_edit()
        if payload is None:
            return
        handler = self._send_to_single_handler
        if handler is None:
            self._log("[提醒] 「送入单帧解析」不可用：主窗口未注入回调", "warn")
            QMessageBox.information(
                self, "不可用", "「送入单帧解析」需要主窗口提供回调（当前环境未注入）。"
            )
            return
        try:
            handler(bytes_to_hex(payload))
        except Exception as exc:  # noqa: BLE001 - 主窗口回调异常不该让本页崩
            self._log(f"[提醒] 送入单帧解析失败：{type(exc).__name__}: {exc}", "fail")

    def _on_send_progress(self, index: int, total: int, chunk: bytes):
        self._log(
            f"[TX] 分包 {index}/{total}："
            f"{format_payload(chunk, self.chk_show_hex.isChecked())}",
            "tx",
        )

    def _on_data_sent(self, payload: bytes):
        self._log(f"[TX] 已发送 {len(payload)} 字节", "tx")
        # 探测中的写入确认（会话只在 write 阶段响应，其它情况自动忽略）
        self._probe_event("written", True)

    # ── 接收 ────────────────────────────────────────────────────────────

    def _on_frame_received(self, uuid: str, frame: bytes):
        tag = core.short_uuid(uuid) or "?"
        self._log(
            f"[RX·{tag}] {format_payload(frame, self.chk_show_hex.isChecked())}"
            f"（{len(frame)} 字节）",
            "rx",
        )
        # 探测中：任何回包都算「这个候选通了」（会话只在 wait 阶段响应）
        self._probe_event("frame", len(frame or b""))
        # 虚拟模式：原样转发到串口（缺串口连接时明确提示，不静默丢）
        self._forward_to_serial(frame)
        self._parse_and_log(frame)


    def _parse_and_log(self, frame: bytes):
        if not self.chk_parse.isChecked():
            return
        provider = self._parse_provider
        if provider is None:
            return
        protocol = self._current_protocol()
        if protocol is None:
            return
        short = self._protocol_short(protocol)
        try:
            summary, table_data = provider(frame, protocol)
        except Exception as exc:  # noqa: BLE001 - 解析失败不该让本页崩
            self._log(f"[解析·{short}] 失败：{type(exc).__name__}: {exc}", "fail")
            return
        if not table_data:
            self._log(f"[解析·{short}] 失败：无法按该协议解析此报文", "fail")
            return
        self._log(f"[解析·{short}] {summary}", "parse")
        for line in format_parse_rows(table_data, int(self.spin_parse_lines.value())):
            self._log(line, "parse")

    def _current_protocol(self) -> Optional[int]:
        data = self.combo_protocol.currentData()
        return None if data is None else int(data)

    def _on_parse_toggled(self, checked: bool):
        self.combo_protocol.setEnabled(bool(checked))
        self.spin_parse_lines.setEnabled(bool(checked))
        if checked and self.combo_protocol.currentData() is None:
            protocol = self._protocol_from_main()
            if protocol is not None:
                self._select_protocol(protocol)
        self._schedule_save()

    def _on_parse_protocol_changed(self, _index: int):
        self._schedule_save()

    def _protocol_from_main(self) -> Optional[int]:
        provider = self._protocol_provider
        if provider is None:
            return None
        try:
            value = provider()
        except Exception:
            return None
        return None if value is None else int(value)

    def _select_protocol(self, protocol: Optional[int]):
        index = self.combo_protocol.findData(None if protocol is None else int(protocol))
        if index >= 0:
            self.combo_protocol.blockSignals(True)
            self.combo_protocol.setCurrentIndex(index)
            self.combo_protocol.blockSignals(False)

    @staticmethod
    def _protocol_short(protocol: Optional[int]) -> str:
        try:
            from serial_tool_widget import protocol_short_name

            return protocol_short_name(protocol)
        except Exception:
            return "?"

    # ── 统计 ────────────────────────────────────────────────────────────

    def _on_stats_changed(self, rx_bytes: int, tx_bytes: int):
        self._rx_bytes = int(rx_bytes or 0)
        self._tx_bytes = int(tx_bytes or 0)
        # 立即刷新：状态行本来有 300ms 定时器兜底，但统计是「发完就想看到」的数字，
        # 让用户盯着旧值等半秒没有意义。
        self._refresh_status_line()

    # ── worker 通用日志 / 错误 ───────────────────────────────────────────

    @staticmethod
    def _classify_worker_log(message: str) -> str:
        """把 worker 的文字日志归到一个配色（只影响颜色，不改内容）。"""
        text = str(message or "")
        for token in ("失败", "错误", "无法", "异常"):
            if token in text:
                return "fail"
        for token in ("已连接", "已断开", "扫描", "订阅"):
            if token in text:
                return "ble"
        return "sys"

    def _on_worker_log(self, message: str):
        self._log(f"[蓝牙] {message}", self._classify_worker_log(message))

    def _on_worker_error(self, message: str):
        text = str(message or "")
        self._log(f"[错误] {text}", "fail")
        # 探测中的写入失败（会话只在 write 阶段响应）
        self._probe_event("written", False)
        # bleak 缺失是「装一次就好」的问题：弹一次对话框，别让用户只看到日志里一行
        if text == BLEAK_MISSING_HINT and not getattr(self, "_bleak_dialog_shown", False):
            self._bleak_dialog_shown = True
            QMessageBox.critical(self, "缺少 bleak 库", text)

    def _on_reset_stats(self):
        worker = self._worker
        if worker is not None:
            worker.reset_stats()
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._refresh_status_line()
        self._log("[系统] 收发统计已清零", "sys")

    # ── 参数 ────────────────────────────────────────────────────────────

    def _on_timeout_changed(self, value: float):
        worker = self._worker
        if worker is not None:
            worker.set_packet_timeout(float(value))
        self._schedule_save()

    def _on_packet_delay_changed(self, value: float):
        worker = self._worker
        if worker is not None:
            worker.set_send_options(packet_delay=float(value))
        self._schedule_save()

    # ── 虚拟模式（BLE ⇄ 串口透传）────────────────────────────────────────

    def _on_virtual_toggled(self, checked: bool):
        self._settings["virtual_mode"] = bool(checked)
        loading = bool(getattr(self, "_loading", False))
        if checked:
            if not loading and (self._serial_worker is None or not self._serial_connected):
                self._log(
                    "[提醒] 虚拟模式已开启，但串口**未连接**：请到顶部「串口配置」连接串口，"
                    "否则数据无法透传",
                    "warn",
                )
            elif not loading:
                self._log("[虚拟] 已开启：BLE 收到的数据写入串口，串口收到的数据写入 BLE", "sys")
        elif not loading:
            self._log("[虚拟] 已关闭", "sys")
        self._schedule_save()

    def _on_serial_connection_changed(self, connected: bool):
        self._serial_connected = bool(connected)
        self.lbl_serial_state.setText("串口：已连接" if connected else "串口：未连接")
        if connected and self.chk_virtual.isChecked():
            self._log("[虚拟] 串口已连接，透传就绪", "serial")

    def _on_serial_error(self, message: str):
        self._log(f"[串口] {message}", "fail")

    def _on_serial_data(self, data: bytes):
        """串口收到的数据 → 写入 BLE（仅虚拟模式）。"""
        if not self.chk_virtual.isChecked():
            return
        worker = self._worker
        if worker is None or not worker.is_connected():
            self._log("[虚拟] 串口数据到达，但蓝牙未连接，已丢弃", "warn")
            return
        if not self._serial_connected:
            self._log("[虚拟] 串口数据到达，但串口未连接，已丢弃", "warn")
            return
        payload = bytes(data or b"")
        if not payload:
            return
        self._log(f"[串口→BLE] {format_payload(payload, self.chk_show_hex.isChecked())}", "serial")
        worker.send_data(payload)

    def _forward_to_serial(self, frame: bytes) -> bool:
        """把一帧数据写入串口（仅虚拟模式）；返回是否写出。"""
        if not self.chk_virtual.isChecked():
            return False
        worker = self._serial_worker
        if worker is None or not self._serial_connected:
            self._log("[虚拟] 蓝牙数据到达，但串口未连接，已丢弃", "warn")
            return False
        try:
            ok = bool(worker.write_raw(bytes(frame)))
        except Exception as exc:  # noqa: BLE001
            self._log(f"[虚拟] 写入串口失败：{type(exc).__name__}: {exc}", "fail")
            return False
        if ok:
            self._log(
                f"[BLE→串口] {format_payload(frame, self.chk_show_hex.isChecked())}", "serial"
            )
        return ok

    # ── 日志 ────────────────────────────────────────────────────────────

    def _log(self, text: str, color: str = "sys"):
        """写一行日志（进队列，由 `_flush_log_queue` 批量落进窗口）。

        **不要**直接往 ``log_text`` 里插 —— 高速收发时逐行重绘会把界面拖死；
        日志文件的唯一写入点是 `_append_log`（窗口显示什么、文件就有什么）。
        """
        self._log_queue.append((str(color or "sys"), str(text)))

    def _flush_log_queue(self):
        """批量刷出日志；一批超过 ``LOG_FLUSH_BURST`` 时只留首尾（防刷屏）。"""
        if not self._log_queue:
            return
        burst = len(self._log_queue)
        if burst > LOG_FLUSH_BURST:
            first = self._log_queue[0]
            last = self._log_queue[-1]
            self._log_queue.clear()
            self._append_log(f"…本批 {burst} 条日志已省略（仅显示首尾）", "sys")
            self._append_log(first[1], first[0])
            self._append_log(last[1], last[0])
            return
        while self._log_queue:
            color, text = self._log_queue.popleft()
            self._append_log(text, color)

    def _append_log(self, text: str, color: str = "sys"):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(_LOG_COLORS.get(color, _LOG_COLORS["sys"])))
        cursor.insertText(text + "\n", fmt)
        self._log_line_count = max(0, self.log_text.document().blockCount() - 1)
        if self._log_line_count > WINDOW_KEEP_LINES:
            self._trim_log_window()
        self._save_log_line(text)
        if self.chk_auto_scroll.isChecked():
            bar = self.log_text.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _trim_log_window(self):
        """裁掉窗口里最旧的行（文件不裁，见 `_save_log_line`）。"""
        excess = self._log_line_count - WINDOW_KEEP_LINES + LOG_TRIM_STEP
        if excess <= 0:
            return
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextBlock,
            QTextCursor.MoveMode.KeepAnchor,
            int(excess),
        )
        cursor.removeSelectedText()
        self._log_line_count = max(0, self.log_text.document().blockCount() - 1)

    def _on_clear_log(self):
        self.log_text.clear()
        self._log_line_count = 0

    # ── 日志文件（自动保存）────────────────────────────────────────────

    def log_dir(self) -> str:
        """当前日志目录：用户选择的优先，默认 = 数据目录下的 ``Output/``。

        默认目录由本页**配置文件所在目录**派生（而不是直接问 `app_paths`）：数据目录
        已被测试沙箱重定向时，日志目录随之进沙箱，绝不会写到开发机的真实目录。
        """
        chosen = str(self._settings.get("log_dir") or "").strip()
        if chosen:
            return chosen
        return default_log_dir(os.path.dirname(self._config_path))

    def _log_header_lines(self) -> List[str]:
        worker = self._worker
        device = "未连接"
        if worker is not None:
            try:
                if worker.is_connected():
                    device = f"{worker.device_name()}（{worker.device_address()}，MTU={worker.mtu_size() or '未知'}）"
            except Exception:
                device = "未连接"
        return [
            f"# {LOG_HEADER_TITLE}",
            f"# 开始时间: {format_log_time()}",
            f"# 蓝牙设备: {device}",
            f"# 切帧超时: {self.spin_timeout.value():.3f} s",
            "# 说明: 本文件是「蓝牙工具」日志窗口内容的完整镜像；"
            f"窗口只保留最近 {WINDOW_KEEP_LINES} 行，文件不截断（一直追加）",
        ]

    def _stats_comment(self) -> str:
        return (f"# 收发统计: 接收 {self._rx_bytes} B / 发送 {self._tx_bytes} B")

    def _on_auto_save_toggled(self, checked: bool):
        if checked:
            if not self._start_log_file():
                # 开不了文件就回到未勾选（blockSignals 防重入 → 只提示一次）
                self.chk_auto_save_log.blockSignals(True)
                self.chk_auto_save_log.setChecked(False)
                self.chk_auto_save_log.blockSignals(False)
                self._update_log_state_label()
        else:
            self._close_log_file()
        self._schedule_save()

    def _start_log_file(self) -> bool:
        """开始写日志文件；失败**明确提示**并返回 False（不静默）。"""
        if self._log_writer is not None:
            return True
        writer = LogFileWriter(timestamp=bool(self.chk_log_stamp.isChecked()))
        if not writer.open(self.log_dir(), header=self._log_header_lines()):
            reason = writer.error or "未知错误"
            self._append_log(f"[日志] 无法创建日志文件：{reason}", "fail")
            self._update_log_state_label()
            QMessageBox.critical(
                self, "日志保存失败",
                f"无法创建日志文件：\n{reason}\n\n目录：{self.log_dir()}",
            )
            return False
        self._log_writer = writer
        self._append_log(f"[日志] 开始保存到 {writer.path}", "sys")
        self._update_log_state_label()
        return True

    def _close_log_file(self):
        """停止写日志文件：写统计尾 + 关闭（幂等）。"""
        writer = self._log_writer
        if writer is None:
            self._update_log_state_label()
            return
        # 先摘掉引用：下面写的「已保存」行不该再进这个（已收尾的）文件
        self._log_writer = None
        self._log_last_path = writer.path
        writer.write_raw(f"# 停止时间: {format_log_time()}")
        writer.write_raw(self._stats_comment())
        ok = writer.close()
        self._log_last_lines = writer.line_count
        if ok:
            self._append_log(f"[日志] 已保存 {writer.line_count} 行到 {writer.path}", "sys")
        else:
            self._append_log(
                f"[日志] 收尾写日志文件失败：{writer.error or '未知错误'}", "fail"
            )
        self._update_log_state_label()

    def _on_log_stamp_toggled(self, checked: bool):
        """「行首时间戳」开关：对当前已打开的文件**立即生效**（下一行起）。"""
        if self._log_writer is not None:
            self._log_writer.timestamp = bool(checked)
        self._schedule_save()

    def _save_log_line(self, text: str):
        """把一行日志写进文件（由 `_append_log` 调用，文件的**唯一**写入点）。

        写失败（目录被删 / 磁盘满 / 权限）：**必须告诉用户**并把自动保存关掉，
        否则日志会静默丢失。这里先把引用摘掉 —— 下面那条提示不能再往坏文件里写。
        """
        writer = self._log_writer
        if writer is None or not writer.is_open:
            return
        if writer.write_line(text):
            return
        reason = writer.error or "未知错误"
        self._log_writer = None
        try:
            writer.close()
        except Exception:
            pass
        self.chk_auto_save_log.blockSignals(True)
        self.chk_auto_save_log.setChecked(False)
        self.chk_auto_save_log.blockSignals(False)
        self._update_log_state_label()
        self._append_log(f"[日志] 写日志文件失败，已关闭自动保存：{reason}", "fail")
        QMessageBox.critical(
            self, "日志写入失败",
            f"写日志文件失败，已关闭「自动保存日志」：\n{reason}",
        )

    def _update_log_state_label(self):
        if self._log_writer is not None:
            path = self._log_writer.path
            self.lbl_log_state.setText(
                f"● 正在保存：{os.path.basename(path)}（{self._log_writer.line_count} 行）"
            )
            self.lbl_log_state.setStyleSheet(f"color: {_LOG_COLORS['rx']}; font-size: 11px;")
            self.lbl_log_state.setToolTip(path)
        elif self._log_last_path:
            self.lbl_log_state.setText(
                f"○ 已保存 {self._log_last_lines} 行：{os.path.basename(self._log_last_path)}"
            )
            self.lbl_log_state.setStyleSheet(f"color: {_LOG_COLORS['sys']}; font-size: 11px;")
            self.lbl_log_state.setToolTip(self._log_last_path)
        else:
            self.lbl_log_state.setText("未开启自动保存")
            self.lbl_log_state.setStyleSheet(f"color: {_LOG_COLORS['sys']}; font-size: 11px;")
            self.lbl_log_state.setToolTip("")

    def _choose_log_dir(self):
        current = self.log_dir()
        chosen = QFileDialog.getExistingDirectory(self, "选择日志目录", current)
        if not chosen:
            return
        self._settings["log_dir"] = chosen
        self._schedule_save()
        self._append_log(f"[日志] 日志目录改为 {chosen}", "sys")

    def _open_log_directory(self):
        path = self.log_dir()
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "无法创建目录", f"{path}\n\n{exc}")
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)          # noqa: S606 - Windows 平台专用
            else:
                import subprocess
                import sys as _sys

                opener = "open" if _sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, path])  # noqa: S603,S607
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "打开目录失败", f"{path}\n\n{exc}")

    def _save_log_now(self):
        """把日志窗口当前内容另存为一个文件（不影响「自动保存日志」）。"""
        default_name = f"{LOG_FILE_PREFIX}_{format_log_time().replace(':', '').replace('-', '').replace(' ', '_')}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存当前日志", os.path.join(self.log_dir(), default_name),
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".txt"
        text = self.log_text.toPlainText()
        if write_log_text(path, text):
            self._append_log(f"[日志] 已另存 {path}", "sys")
        else:
            QMessageBox.warning(self, "保存失败", f"无法写入文件：\n{path}")

    # ── 自定义报文按钮 ──────────────────────────────────────────────────

    def _rebuild_custom_buttons(self):
        """按 ``self._buttons`` 重建按钮网格（右键可编辑/删除/移位）。"""
        for button in self._custom_buttons:
            try:
                button.setParent(None)
                button.deleteLater()
            except RuntimeError:
                pass
        self._custom_buttons = []
        while self.custom_grid.count():
            item = self.custom_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        for index, spec in enumerate(self._buttons):
            button = QPushButton(str(spec.get("name") or f"报文{index + 1}"))
            set_btn(button, "accent", "sm")
            button.setToolTip(
                f"{spec.get('data') or ''}\n"
                f"格式：{'HEX' if spec.get('isHex', True) else 'ASCII'}\n"
                "单击发送；右键可编辑 / 删除 / 移位"
            )
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, i=index, b=button: self._on_custom_context_menu(pos, i, b)
            )
            button.clicked.connect(lambda _c=False, i=index: self._on_custom_clicked(i))
            self.custom_grid.addWidget(
                button, index // BUTTON_GRID_COLUMNS, index % BUTTON_GRID_COLUMNS
            )
            self._custom_buttons.append(button)

        if not self._buttons:
            placeholder = QLabel("（暂无自定义报文按钮，点「新增…」或「批量新增…」添加）")
            self.custom_grid.addWidget(placeholder, 0, 0, 1, BUTTON_GRID_COLUMNS)
        self.custom_group.setTitle(f"自定义报文（{len(self._buttons)}）")

    def _on_custom_clicked(self, index: int):
        if not 0 <= index < len(self._buttons):
            return
        spec = self._buttons[index]
        payload, error = parse_plain_text(
            str(spec.get("data") or ""), "hex" if spec.get("isHex", True) else "ascii"
        )
        if error:
            QMessageBox.warning(self, "报文无效", f"「{spec.get('name')}」{error}")
            return
        self.edit_send.setText(str(spec.get("data") or ""))
        self._send_payload(payload)

    def _on_custom_context_menu(self, pos, index: int, button: QPushButton):
        from PySide6.QtWidgets import QMenu

        if not 0 <= index < len(self._buttons):
            return
        menu = QMenu(self)
        act_edit = menu.addAction("编辑…")
        act_send = menu.addAction("填入发送框")
        menu.addSeparator()
        act_up = menu.addAction("上移")
        act_down = menu.addAction("下移")
        menu.addSeparator()
        act_delete = menu.addAction("删除")
        chosen = menu.exec(button.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_edit:
            self._edit_custom_button(index)
        elif chosen is act_send:
            self.edit_send.setText(str(self._buttons[index].get("data") or ""))
            self._refresh_send_hint()
        elif chosen is act_up:
            self._move_custom_button(index, -1)
        elif chosen is act_down:
            self._move_custom_button(index, 1)
        elif chosen is act_delete:
            self._delete_custom_button(index)

    def _set_buttons(self, buttons, announce: str = ""):
        self._buttons = core.normalize_buttons(buttons)
        self._rebuild_custom_buttons()
        self._schedule_save()
        if announce:
            self._log(announce, "sys")

    def _on_custom_add(self):
        if len(self._buttons) >= core.MAX_CUSTOM_BUTTONS:
            QMessageBox.information(
                self, "已达上限", f"自定义报文按钮最多 {core.MAX_CUSTOM_BUTTONS} 个。"
            )
            return
        dialog = ButtonEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.value()
        if not value:
            return
        self._set_buttons(self._buttons + [value], f"[系统] 已新增报文按钮「{value['name']}」")

    def _edit_custom_button(self, index: int):
        if not 0 <= index < len(self._buttons):
            return
        dialog = ButtonEditDialog(self, self._buttons[index])
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.value()
        if not value:
            return
        buttons = list(self._buttons)
        buttons[index] = value
        self._set_buttons(buttons, f"[系统] 已更新报文按钮「{value['name']}」")

    def _delete_custom_button(self, index: int):
        if not 0 <= index < len(self._buttons):
            return
        spec = self._buttons[index]
        answer = QMessageBox.question(
            self, "删除报文按钮",
            f"确定删除「{spec.get('name')}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        buttons = list(self._buttons)
        buttons.pop(index)
        self._set_buttons(buttons, f"[系统] 已删除报文按钮「{spec.get('name')}」")

    def _move_custom_button(self, index: int, delta: int):
        target = index + delta
        if not (0 <= index < len(self._buttons) and 0 <= target < len(self._buttons)):
            return
        buttons = list(self._buttons)
        buttons[index], buttons[target] = buttons[target], buttons[index]
        self._set_buttons(buttons)

    def _on_custom_batch(self):
        dialog = BatchButtonDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        incoming = dialog.buttons()
        if not incoming:
            return
        merged = core.normalize_buttons(list(self._buttons) + incoming)
        added = len(merged) - len(self._buttons)
        self._set_buttons(merged, f"[系统] 已批量新增 {added} 个报文按钮")
        if added < len(incoming):
            self._log(
                f"[提醒] 受上限 {core.MAX_CUSTOM_BUTTONS} 限制，"
                f"{len(incoming) - added} 条未加入",
                "warn",
            )

    def _on_custom_export(self):
        if not self._buttons:
            QMessageBox.information(self, "没有可导出的按钮", "请先新增自定义报文按钮。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出自定义报文", os.path.join(self.log_dir(), "bluetooth_buttons.json"),
            "JSON 文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".json"
        import json

        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self._buttons, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", f"{path}\n\n{exc}")
            return
        self._log(f"[系统] 已导出 {len(self._buttons)} 个报文按钮到 {path}", "sys")

    def _on_custom_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入自定义报文", self.log_dir(), "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        import json

        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "导入失败", f"{path}\n\n{exc}")
            return
        if isinstance(raw, dict):
            raw = raw.get("custom_buttons", raw.get("buttons", []))
        incoming = core.normalize_buttons(raw)
        if not incoming:
            QMessageBox.information(self, "没有可用内容", "文件里没有可识别的报文按钮。")
            return
        merged = core.normalize_buttons(list(self._buttons) + incoming)
        added = len(merged) - len(self._buttons)
        self._set_buttons(merged, f"[系统] 已从 {os.path.basename(path)} 导入 {added} 个报文按钮")
        if added < len(incoming):
            self._log(
                f"[提醒] 受上限 {core.MAX_CUSTOM_BUTTONS} 限制，{len(incoming) - added} 条未导入",
                "warn",
            )

    def _on_custom_clear(self):
        if not self._buttons:
            return
        answer = QMessageBox.question(
            self, "全部清除",
            f"确定清除全部 {len(self._buttons)} 个自定义报文按钮？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._set_buttons([], "[系统] 已清除全部自定义报文按钮")

    # ── 持久化 ──────────────────────────────────────────────────────────

    def _load_persisted(self):
        """载入配置（坏文件宽容，回落默认值）并套用到界面。"""
        buttons, settings = core.load_settings(self._config_path)
        self._buttons = buttons
        self._settings = settings
        self._recv_uuids = list(settings.get("recv_uuids") or [])
        self._send_uuids = list(settings.get("send_uuids") or [])
        self._apply_settings_to_ui()

    def _apply_settings_to_ui(self):
        """把 ``self._settings`` 套用到控件（载入期间屏蔽提示型日志）。"""
        settings = self._settings
        self._loading = True
        try:
            self.chk_show_hex.setChecked(bool(settings.get("show_hex", True)))
            self.chk_auto_scroll.setChecked(bool(settings.get("auto_scroll", True)))
            self.chk_parse.setChecked(bool(settings.get("parse_enabled", True)))
            self.spin_parse_lines.setValue(
                int(settings.get("parse_max_lines", core.DEFAULT_PARSE_MAX_LINES))
            )
            self.chk_named_only.setChecked(bool(settings.get("filter_named_only", False)))
            self.chk_auto_refresh.setChecked(bool(settings.get("auto_refresh", False)))
            self.spin_refresh.setValue(int(settings.get("auto_refresh_interval", 10)))
            self.spin_timeout.setValue(
                float(settings.get("packet_timeout", core.DEFAULT_PACKET_TIMEOUT))
            )
            self.spin_packet_delay.setValue(
                float(settings.get("send_packet_delay", core.DEFAULT_SEND_PACKET_DELAY))
            )
            self.chk_log_stamp.setChecked(bool(settings.get("log_timestamp", True)))

            index = self.combo_send_format.findData(str(settings.get("send_format", "auto")))
            self.combo_send_format.setCurrentIndex(index if index >= 0 else 0)

            self._rebuild_custom_buttons()
            self._update_log_state_label()
            self._refresh_send_hint()

            # 下面两项会触发信号槽（写日志 / 开文件），放最后
            self.chk_virtual.setChecked(bool(settings.get("virtual_mode", False)))
            if bool(settings.get("log_auto_save", False)):
                self.chk_auto_save_log.setChecked(True)
        finally:
            self._loading = False
        # 协议下拉在载入**之后**重设：`_protocol_from_main` 需要主窗口已注入回调
        self._rebuild_protocol_combo()
        saved_protocol = settings.get("parse_protocol")
        if saved_protocol is not None:
            self._select_protocol(int(saved_protocol))

    def _rebuild_protocol_combo(self):
        """协议下拉：首项「不解析」，其余为当前工程注册的协议。"""
        from serial_tool_widget import protocol_options

        current = self.combo_protocol.currentData()
        self.combo_protocol.blockSignals(True)
        self.combo_protocol.clear()
        for label, data in protocol_options():
            self.combo_protocol.addItem(label, data)
        wanted = current
        if wanted is None:
            wanted = self._protocol_from_main()
        index = self.combo_protocol.findData(wanted)
        self.combo_protocol.setCurrentIndex(index if index >= 0 else 0)
        self.combo_protocol.blockSignals(False)
        self.combo_protocol.setEnabled(bool(self.chk_parse.isChecked()))
        self.spin_parse_lines.setEnabled(bool(self.chk_parse.isChecked()))

    def _collect_settings(self) -> dict:
        settings = dict(self._settings)
        settings.update({
            "show_hex": self.chk_show_hex.isChecked(),
            "auto_scroll": self.chk_auto_scroll.isChecked(),
            "parse_enabled": self.chk_parse.isChecked(),
            "parse_max_lines": int(self.spin_parse_lines.value()),
            "virtual_mode": self.chk_virtual.isChecked(),
            "packet_timeout": round(float(self.spin_timeout.value()), 3),
            "send_packet_delay": round(float(self.spin_packet_delay.value()), 3),
            "send_format": self._send_mode(),
            "parse_protocol": self._current_protocol(),
            "filter_named_only": self.chk_named_only.isChecked(),
            "auto_refresh": self.chk_auto_refresh.isChecked(),
            "auto_refresh_interval": int(self.spin_refresh.value()),
            "log_auto_save": self.chk_auto_save_log.isChecked(),
            "log_timestamp": self.chk_log_stamp.isChecked(),
            "recv_uuids": list(self._recv_uuids),
            "send_uuids": list(self._send_uuids),
        })
        return settings

    def _schedule_save(self):
        self._save_timer.start(400)

    def _save_persisted(self):
        self._settings = self._collect_settings()
        core.save_settings(self._config_path, self._buttons, self._settings)

    # ── 状态行 / 主题 ───────────────────────────────────────────────────

    def _refresh_status_line(self):
        parts = []
        worker = self._worker
        connected = False
        if worker is not None:
            try:
                connected = worker.is_connected()
            except Exception:
                connected = False
        if connected:
            parts.append(f"已连接 {worker.device_name()}")
        else:
            parts.append("未连接")
        parts.append(f"设备 {len(self._devices)} 个")
        parts.append(f"接收 {self._rx_bytes} B / 发送 {self._tx_bytes} B")
        if worker is not None:
            try:
                pending = int(worker.pending_bytes())
            except Exception:
                pending = 0
            if pending:
                parts.append(f"等待重组 {pending} B")
        if self.chk_virtual.isChecked():
            parts.append("虚拟模式：" + ("串口已连接" if self._serial_connected else "串口未连接"))
        # 特征码摘要（1.23.79）：一眼看到「往哪发、从哪收」，不必打开对话框
        parts.append("发送 → " + (self._short_uuid_join(self._send_uuids) or "未选")
                     + " ｜ 接收 → " + (self._short_uuid_join(self._recv_uuids) or "未选"))
        self.lbl_status.setText("　·　".join(parts))

    @staticmethod
    def _theme_color(active: bool) -> str:
        """设备表状态列的颜色（深浅主题下都能看清；不随主题 QSS 走）。"""
        return "#1B5E20" if active else "#757575"

    def restyle_for_theme(self, dark: bool = False):
        """主题切换钩子：只刷新**动态**颜色（静态样式全部由主题 QSS 接管）。

        本页没有自带样式表，所以这里只需重建设备表（状态列颜色）与日志状态行。
        """
        self._dark = bool(dark)
        self._refresh_device_table()
        self._update_log_state_label()
        self._refresh_status_line()
        self._refresh_send_hint()

    # ── 收尾 ────────────────────────────────────────────────────────────

    def cleanup(self):
        """停止定时器、刷出残留日志、收尾日志文件并落盘（幂等）。

        **不关闭串口**：端口是主窗口共享的 `serial_worker` 的，本页只借用。
        **会关闭蓝牙连接**：蓝牙线程由本页自持（或注入），页面收尾时一并停掉。
        """
        for timer_name in ("_log_timer", "_status_timer", "_auto_refresh_timer", "_save_timer",
                           "_probe_timer"):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                try:
                    timer.stop()
                except RuntimeError:
                    pass
        try:
            self._flush_log_queue()
        except Exception:
            pass
        try:
            self._close_log_file()
        except Exception:
            pass
        try:
            self._save_persisted()
        except Exception:
            pass
        worker = self._worker
        if worker is not None:
            try:
                worker.shutdown()
            except Exception:
                pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)





