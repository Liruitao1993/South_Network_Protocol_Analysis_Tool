# -*- coding: utf-8 -*-
"""收发机控制页（协议9 · 通感一体化 SPLC 双模监控器/发射机）。

页面形态（对齐现场工具的使用习惯）：

- **公共参数区**（顶部，**可折叠、默认收起**）：发射机串口 / 接收机串口 / 工装板串口 + 无线模式、频点、
  PHR-MCS、载波DSP/3450、无线功率、载波频段、通信协议、发送次数/间隔/持续时间，
  以及「设置发送功率 / 查询发送功率 / 设置发射机模式 / 查询工作模式 / 查询无线信道 /
  查询HPLC频段 / 设置HPLC频段」等一键命令按钮。
- **左侧用例列表**：``splc_transceiver_cases/*.json``，双击载入；可新建 / 另存 / 删除。
- **右侧用例步骤表**：类别 / 名称 / 类型 / 参数 / 发送次数 / 发送间隔 / 信道端口 / 发送数据。
  一条「大流程」就是一个用例文件，步骤按顺序执行。
- **浮动收发日志窗**：``QDockWidget``，默认**浮在主窗口外**（不占页面空间），可拖回主窗口
  停靠。内含「收发日志」（可保存 / 停止滚动 / 原始 / 解析 / 两者）与「接收监控」
  （复用 :class:`monitor_widget.RealtimeMonitorWidget`，帧列表 + 逐字段解析 + 字节高亮）。

步骤类型：
- ``data``：业务数据帧（协议9 测试帧 / MPDU / 任意业务报文）→ 包 96..16 发给发射机；
- ``command``：设备命令（01~0A）→ 组 68..16 命令帧；
- ``wait``：等待若干毫秒；
- ``raw``：透传报文（原样发到工装板串口或发射机串口，不封帧）。

「复制报文改参数」的入口有两处：步骤对话框里的「从组帧页生成…」直接复用
:class:`csg_test_frame_gen_widget.CsgTestFrameGenWidget`（内含「⓪ 仿照报文 / 模板」
反解区与本地模板存档），以及「粘贴报文」按原样入用例。

协议依据：``南网新一代20260226校对/SPLC双模监控器_发射机_接口协议20260725(1).docx``。
屏幕上的「PSDU-MCS / PBSIZE / 频谱仪 / 网口」等字段属于《PLC2.0收发机报文格式》台体
工具，本接口协议里没有对应命令，故**不做成死控件**。
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableWidgetItem, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

import app_icons
import collapsible_section
import splc_transceiver_core as core
from gui_utils import FlowLayout, ZoomableTableWidget, set_btn_icon
from monitor_widget import RealtimeMonitorWidget
from splc_transceiver_worker import SplcSerialPort

BAUD_CHOICES = ("921600", "460800", "230400", "115200", "57600", "38400", "19200", "9600")
PARITY_CHOICES = ("无", "偶", "奇")
VIEW_MODES = (("both", "原始 + 解析"), ("raw", "仅原始 HEX"), ("parsed", "仅解析"))
MAX_LOG_RECORDS = 20000

# 解析行的排版：不分行，整条记录的解析并成一行，超宽靠横向滚动条看（现场/官方日志的形态）
PARSED_INDENT = "    "        # 解析行的行首缩进
PARSED_GAP = "    "           # 同一行内两个字段之间的间隔

# 摘要（解析出来的业务要点）在日志里用绿色标出来：现场要在长行里一眼找到「这帧是什么」
SUMMARY_COLOR = "#1B8A3A"
SUMMARY_LABEL = "摘要: "

STEP_COLUMNS = ("类别", "名称", "类型", "参数", "发送次数", "发送间隔", "信道端口", "发送数据")
COL_CATEGORY, COL_NAME, COL_TYPE, COL_PARAM = 0, 1, 2, 3
COL_COUNT, COL_INTERVAL, COL_PORT, COL_DATA = 4, 5, 6, 7


def _mono_font() -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def _fmt_time() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class U32Edit(QLineEdit):
    """32 位无符号字段输入（``QSpinBox`` 只到 int32，装不下 0xFFFFFFFF）。

    PLC2.0 里「时间偏移/帧间隔/接收 NTB 间隔」这些字段是 4 字节无符号，
    用 ``QSpinBox`` 会在 ``setRange(0, 0xFFFFFFFF)`` 处直接抛 ``OverflowError``
    （实测：整个指令的后续字段都没建出来，命令帧少一半数据）。
    这里用文本框接受十进制或 ``0x`` 十六进制，越界由 :meth:`value` 夹紧。
    """

    def __init__(self, maximum: int = 0xFFFFFFFF, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._maximum = int(maximum)
        self.setMaximumWidth(120)
        self.setFont(_mono_font())
        self.setPlaceholderText("0 或 0xFFFFFFFF")
        self.setText("0")

    def setValue(self, value: int) -> None:
        self.setText(str(max(0, min(self._maximum, int(value)))))

    def value(self) -> int:
        text = self.text().strip()
        if not text:
            return 0
        try:
            number = int(text, 0) if text.lower().startswith("0x") else int(text)
        except ValueError:
            return 0
        return max(0, min(self._maximum, number))

    def valueChangedSignal(self):  # 便于与 QSpinBox 的 valueChanged 并列接线
        return self.textChanged


class FlowArea(QWidget):
    """承载 :class:`FlowLayout` 的一行容器（自动折行，高度由页面显式算）。

    为什么不能直接把 `FlowLayout` 塞进页面的 `QVBoxLayout`：`QTabWidget`/`QStackedWidget`
    **不向上传播 `heightForWidth`**，嵌入主窗口后这些行只按一行的 `sizeHint` 给高度，
    实际排 3~4 行时被压成一条缝（实测：整个公共参数区几乎不可见）。
    这里只提供 :meth:`height_for_width`，由 :meth:`SplcTransceiverWidget._update_config_height`
    在每次 resize / 显示时把高度写成固定值 —— 比依赖 HfW 传播稳定（那条路在两个宿主里
    行为不一致）。
    """

    def __init__(self, spacing: int = 6, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._flow = FlowLayout(self, margin=0, spacing=spacing)
        # 本页所有控件恒定可见，量高度时不要按 isVisible() 跳过（早期调用时子控件
        # 尚未 visible，会算出 0 高度把整块参数区压扁）
        self._flow._ignore_visibility = True
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    # ---- 转发 FlowLayout 的 API（页面只关心这几个）----
    def addWidget(self, widget: QWidget, stretch: int = 0):
        self._flow.addWidget(widget, stretch)
        return widget

    def addStretch(self, stretch: int = 1):
        self._flow.addStretch(stretch)

    def addSpacing(self, spacing: int):
        return self._flow.addSpacing(spacing)

    def flow(self) -> FlowLayout:
        return self._flow

    def height_for_width(self, width: int) -> int:
        return max(0, int(self._flow.heightForWidth(max(1, int(width)))))


# ======================================================================
# 日志窗
# ======================================================================

class LogWindow(QWidget):
    """收发日志面板：原始 HEX / 解析结果 / 两者，可暂停滚动、可保存。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: List[Dict[str, object]] = []
        self._view_mode = "both"
        self._build_ui()

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("显示:"))
        self.view_combo = QComboBox()
        for key, label in VIEW_MODES:
            self.view_combo.addItem(label, key)
        self.view_combo.currentIndexChanged.connect(
            lambda _i: self.set_view_mode(self.view_combo.currentData()))
        bar.addWidget(self.view_combo)

        self.pause_chk = QCheckBox("停止滚动")
        self.pause_chk.setToolTip("勾选后新日志仍然记录，但视图不再自动滚到底部（方便回看）")
        bar.addWidget(self.pause_chk)

        self.save_btn = QPushButton("保存日志")
        set_btn_icon(self.save_btn, "save")
        self.save_btn.clicked.connect(self.save_to_file)
        bar.addWidget(self.save_btn)

        clear_btn = QPushButton("清空")
        set_btn_icon(clear_btn, "clear")
        clear_btn.clicked.connect(self.clear_log)
        bar.addWidget(clear_btn)

        bar.addStretch(1)
        self.count_label = QLabel("0 条")
        bar.addWidget(self.count_label)
        layout.addLayout(bar)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(_mono_font())
        self.log_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_text.setMaximumBlockCount(MAX_LOG_RECORDS * 6)
        self.log_text.setPlaceholderText(
            "收发记录会按时间顺序追加在这里。\n"
            "「显示」可切换 仅原始 HEX / 仅解析 / 两者。"
        )
        layout.addWidget(self.log_text, 1)

    # ------------------------------------------------------------ 记录
    def set_view_mode(self, mode: str):
        if mode not in ("both", "raw", "parsed"):
            mode = "both"
        self._view_mode = mode
        idx = self.view_combo.findData(mode)
        if idx >= 0 and self.view_combo.currentIndex() != idx:
            self.view_combo.blockSignals(True)
            self.view_combo.setCurrentIndex(idx)
            self.view_combo.blockSignals(False)
        self.rerender()

    def append_tx(self, port_label: str, frame: bytes, note: str = "",
                  rows: Optional[List[Tuple[str, str, str]]] = None,
                  summary: str = ""):
        self._append("TX", port_label, frame, note, rows, summary)

    def append_rx(self, port_label: str, frame: bytes, note: str = "",
                  rows: Optional[List[Tuple[str, str, str]]] = None,
                  summary: str = ""):
        self._append("RX", port_label, frame, note, rows, summary)

    def append_note(self, text: str, level: str = "info"):
        """非报文类事件（打开串口、开始/结束流程、错误）。"""
        record = {
            "time": _fmt_time(), "dir": level.upper(), "port": "",
            "hex": "", "note": text, "rows": [], "summary": "",
        }
        self._records.append(record)
        if len(self._records) > MAX_LOG_RECORDS:
            del self._records[:len(self._records) - MAX_LOG_RECORDS]
            self.rerender()
            return
        self._append_text(self._format_record(record))

    def _append(self, direction: str, port_label: str, frame: bytes, note: str,
                rows, summary: str = ""):
        if rows is None:
            rows = self._auto_rows(frame)
        record = {
            "time": _fmt_time(),
            "dir": direction,
            "port": port_label,
            "hex": core.bytes_to_hex(frame),
            "note": note or "",
            "rows": list(rows or []),
            "bytes": bytes(frame),
            "summary": str(summary or ""),
        }
        self._records.append(record)
        if len(self._records) > MAX_LOG_RECORDS:
            del self._records[:len(self._records) - MAX_LOG_RECORDS]
            self.rerender()
            return
        self._append_text(self._format_record(record))

    @staticmethod
    def _auto_rows(frame: bytes) -> List[Tuple[str, str, str]]:
        """没有调用方解析行时，按帧头自行展开一层（ED..EE / 96H / 68H）。"""
        data = bytes(frame)
        rows: List[Tuple[str, str, str]] = []
        if data[:1] == bytes([core.TX_HEAD]):
            info = core.parse_tx_frame(data)
            rows.append(("控制域1", f"0x{info.get('ctrl1', 0):02X}",
                         str(info.get("ctrl1_name", ""))))
            rows.append(("控制域2", f"0x{info.get('ctrl2', 0):02X}",
                         str(info.get("ctrl2_name", ""))))
            rows.append(("帧长域", str(info.get("frame_len", "")),
                         str(info.get("frame_len", 0))))
            rows.append(("数据域长度", str(info.get("data_len", "")),
                         str(info.get("data_len", 0))))
            rows.append(("CS", f"0x{info.get('cs', 0):02X}",
                         "固定 0xFF（保留）" if info.get("cs_reserved")
                         else ("✓ 正确" if info.get("ok")
                               else f"✗ 应为 0x{info.get('cs_calc', 0):02X}")))
            if info.get("ctrl1") == core.CTRL1_DATA:
                payload_rows, _note = core.decode_tx_data_payload(
                    int(info.get("ctrl2") or 0), bytes(info.get("data") or b""))
                rows.extend(payload_rows)
            elif info.get("ctrl1") == core.CTRL1_CONTROL:
                payload_rows, _note = core.decode_tx_control_payload(
                    int(info.get("ctrl2") or 0), bytes(info.get("data") or b""))
                rows.extend(payload_rows)
            if info.get("error"):
                rows.append(("问题", "", str(info["error"])))
            return rows
        if data[:1] == bytes([core.FRAME_HEAD_DATA]):
            info = core.parse_data_frame(data)
            if not info.get("error") or info.get("data_len") is not None:
                rows.append(("协议类型", str(info.get("proto_type", "")),
                             str(info.get("proto_name", ""))))
                rows.append(("信道", str(info.get("channel", "")),
                             str(info.get("channel_name", ""))))
                rows.append(("业务帧长度", str(info.get("data_len", "")),
                             str(info.get("data_len", 0))))
                rows.append(("CS", f"0x{info.get('cs', 0):02X}",
                             "✓ 正确" if info.get("ok")
                             else f"✗ 应为 0x{info.get('cs_calc', 0):02X}"))
                if info.get("error"):
                    rows.append(("问题", "", str(info["error"])))
                return rows
        if data[:1] == bytes([core.FRAME_HEAD_CMD]):
            info = core.parse_command_frame(data)
            rows.append(("命令", f"0x{info.get('cmd_id', 0):02X}",
                         str(info.get("cmd_name", ""))))
            if info.get("rw") is not None:
                rows.append(("读写", str(info.get("rw")),
                             "设置" if info.get("rw") else "查询"))
            rows.extend(info.get("fields") or [])
            rows.append(("CS", f"0x{info.get('cs', 0):02X}",
                         "✓ 正确" if info.get("ok")
                         else f"✗ 应为 0x{info.get('cs_calc', 0):02X}"))
            return rows
        return rows

    def _summary_format(self) -> QTextCharFormat:
        """摘要运行的格式（绿色）：现场要在长行里一眼认出「这帧是什么」。"""
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(SUMMARY_COLOR))
        return fmt

    def _append_runs(self, runs: List[Tuple[str, bool]]):
        """按 (文本, 是否摘要) 运行段写入：摘要段用绿色，其余用默认色。"""
        if not runs:
            return
        summary_fmt = self._summary_format()
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for text, is_summary in runs:
            if not text:
                continue
            cursor.insertText(text, summary_fmt if is_summary else QTextCharFormat())
        if not self.pause_chk.isChecked():
            self.log_text.moveCursor(QTextCursor.MoveOperation.End)
            bar = self.log_text.verticalScrollBar()
            bar.setValue(bar.maximum())
        self.count_label.setText(f"{len(self._records)} 条")

    def _append_text(self, text: str):
        if not text:
            return
        self._append_runs([(text, False)])

    def _record_runs(self, record: Dict[str, object]) -> List[Tuple[str, bool]]:
        """一条记录 → 带「是否摘要」标记的文本段（渲染与纯文本共用一份口径）。"""
        direction = str(record.get("dir", ""))
        if direction in ("INFO", "ERROR", "WARN"):
            return [(f"[{record['time']}] {record.get('note', '')}\n", False)]
        arrow = "→" if direction == "TX" else "←"
        head = f"[{record['time']}] {record.get('port', '')} {arrow}"
        mode = self._view_mode
        runs: List[Tuple[str, bool]] = []
        hex_text = str(record.get("hex", ""))
        note = str(record.get("note", "") or "")
        summary = str(record.get("summary", "") or "")
        if mode in ("both", "raw"):
            suffix = f"   {note}" if note and mode == "raw" else ""
            runs.append((f"{head} {hex_text}{suffix}\n", False))
        if mode in ("both", "parsed"):
            rows = record.get("rows") or []
            if not rows:
                if mode == "parsed":
                    runs.append((f"{head} {note or '（无解析）'}\n", False))
            else:
                if mode == "parsed":
                    runs.append((f"{head} {note}\n", False))
                segments = [self._row_segment(row) for row in rows]
                segments = [seg for seg in segments if seg]
                if segments or summary:
                    runs.append((PARSED_INDENT, False))
                if summary:
                    runs.append((f"{SUMMARY_LABEL}{summary}", True))
                    if segments:
                        runs.append((PARSED_GAP, False))
                if segments:
                    runs.append((PARSED_GAP.join(segments), False))
                if segments or summary:
                    runs.append(("\n", False))
        return runs

    def _format_record(self, record: Dict[str, object]) -> str:
        """纯文本形态（保存日志 / 旧调用方用）；颜色只在界面渲染时体现。"""
        return "".join(text for text, _ in self._record_runs(record)).rstrip("\n")

    # ---------------------------------------------------- 解析行横向排版
    @staticmethod
    def _row_segment(row) -> str:
        """一行解析结果压成 ``字段: 解析值`` 的单行片段。

        **只输出解析结果**（用户口径：不要 ``原始值 → 解析值`` 那种回声，官方日志
        也是「字段: 含义/值」）；解析值为空时才退回原始值，避免出现只有字段名的半行。
        """
        try:
            name, raw, parsed = row[0], row[1], row[2]
        except (TypeError, IndexError):
            return str(row)
        name = str(name or "")
        raw = str(raw or "")
        parsed = str(parsed or "")
        detail = parsed or raw
        if not name:
            return detail
        # 分段标题（"── 业务帧（协议9 解析）──"）本身的冒号是装饰，不重复补
        if name.endswith(":"):
            return f"{name} {detail}".strip()
        return f"{name}: {detail}".strip() if detail else name

    def _rows_line(self, rows) -> str:
        """把一条记录的全部解析字段并成**一行**（不折行，超宽靠横向滚动条）。

        现场工具（以及官方日志）就是「一条记录一行」的形态：纵向一行一个字段
        浪费宽度，按窗口宽度折行又会把同一条记录拆成好几行、难以对照。这里只
        用 :data:`PARSED_GAP` 把各字段片段横向拼起来，「── 业务帧（协议9 解析）──」
        这类分段标题也留在同一行内（作为并排的分隔标题）。
        """
        segments: List[str] = []
        for row in rows:
            segment = self._row_segment(row)
            if segment:
                segments.append(segment)
        if not segments:
            return ""
        return PARSED_INDENT + PARSED_GAP.join(segments)

    def _render_text(self) -> str:
        return "".join(
            text for record in self._records for text, _ in self._record_runs(record)
        ).rstrip("\n")

    def rerender(self):
        # 逐条重排：摘要仍要带绿色，所以不能用 setPlainText（会丢掉字符格式）
        self.log_text.clear()
        summary_fmt = self._summary_format()
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for record in self._records:
            for text, is_summary in self._record_runs(record):
                if not text:
                    continue
                cursor.insertText(text, summary_fmt if is_summary else QTextCharFormat())
        if not self.pause_chk.isChecked():
            self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.count_label.setText(f"{len(self._records)} 条")

    def clear_log(self):
        self._records.clear()
        self.log_text.clear()
        self.count_label.setText("0 条")

    # ------------------------------------------------------------ 保存
    def save_to_file(self, path: Optional[str] = None) -> Optional[Path]:
        text = self._render_text()
        if not text:
            QMessageBox.information(self, "保存日志", "当前没有日志内容。")
            return None
        if not path:
            default = Path.cwd() / f"收发日志_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            path, _ = QFileDialog.getSaveFileName(
                self, "保存收发日志", str(default), "文本文件 (*.txt);;所有文件 (*.*)")
            if not path:
                return None
        target = Path(path)
        try:
            target.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "保存日志", f"写入失败：{exc}")
            return None
        return target


class SummaryLogWindow(QWidget):
    """摘要日志：**只输出解析后的收发摘要**（一条一行，绿色）。

    为什么单独开一页：现场联调时要在一堆帧里看「谁发了什么、回的什么」，
    收发日志里的长行（HEX + 全字段）太密；这里只留时间/端口/方向 + 摘要，
    对不上的帧一眼就能发现。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines: List[str] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.pause_chk = QCheckBox("停止滚动")
        self.pause_chk.setToolTip("勾选后新摘要仍然记录，但视图不再自动滚到底部")
        bar.addWidget(self.pause_chk)

        self.save_btn = QPushButton("保存摘要")
        set_btn_icon(self.save_btn, "save")
        self.save_btn.clicked.connect(self.save_to_file)
        bar.addWidget(self.save_btn)

        clear_btn = QPushButton("清空")
        set_btn_icon(clear_btn, "clear")
        clear_btn.clicked.connect(self.clear_log)
        bar.addWidget(clear_btn)

        bar.addStretch(1)
        self.count_label = QLabel("0 条")
        bar.addWidget(self.count_label)
        layout.addLayout(bar)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(_mono_font())
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.setPlaceholderText(
            "这里只显示「解析后的收发摘要」：时间 + 端口/方向 + 摘要。\n"
            "摘要取协议9 解析器的业务要点（测试ID/扩展ID/测量值/信标/MPDU 等）。"
        )
        layout.addWidget(self.text, 1)

    # ------------------------------------------------------------ 记录
    def append(self, time_text: str, port_label: str, direction: str,
               summary: str, note: str = ""):
        """一条摘要；没有解析摘要时退回帧级 note，两者都没有就明说无摘要。"""
        text = (summary or "").strip() or (note or "").strip() or "（无摘要）"
        arrow = "→" if direction == "TX" else "←"
        line = f"[{time_text}] {port_label} {arrow} {text}"
        self._lines.append(line)
        if len(self._lines) > MAX_LOG_RECORDS:
            del self._lines[:len(self._lines) - MAX_LOG_RECORDS]
            self.rerender()
            return
        self.text.appendPlainText(line)
        if not self.pause_chk.isChecked():
            self.text.moveCursor(QTextCursor.MoveOperation.End)
            bar = self.text.verticalScrollBar()
            bar.setValue(bar.maximum())
        self.count_label.setText(f"{len(self._lines)} 条")

    def set_summary_color(self, enabled: bool = True):
        """整页都是摘要，默认整体用绿色；保留开关便于将来只高亮部分。"""
        color = SUMMARY_COLOR if enabled else ""
        self.text.setStyleSheet(f"color: {color};" if color else "")

    def rerender(self):
        self.text.setPlainText("\n".join(self._lines))
        if not self.pause_chk.isChecked():
            self.text.moveCursor(QTextCursor.MoveOperation.End)
        self.count_label.setText(f"{len(self._lines)} 条")

    def clear_log(self):
        self._lines.clear()
        self.text.clear()
        self.count_label.setText("0 条")

    def _render_text(self) -> str:
        return "\n".join(self._lines)

    def save_to_file(self, path: Optional[str] = None) -> Optional[Path]:
        text = self._render_text()
        if not text:
            QMessageBox.information(self, "保存摘要", "当前没有摘要内容。")
            return None
        if not path:
            default = Path.cwd() / f"收发摘要_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            path, _ = QFileDialog.getSaveFileName(
                self, "保存收发摘要", str(default), "文本文件 (*.txt);;所有文件 (*.*)")
            if not path:
                return None
        target = Path(path)
        try:
            target.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "保存摘要", f"写入失败：{exc}")
            return None
        return target


class TransceiverLogDock(QDockWidget):
    """浮动日志窗：收发日志 + 摘要日志 + 接收监控三个页签。"""

    def __init__(self, parent=None):
        super().__init__("收发日志 / 摘要日志 / 接收监控", parent)
        self.setObjectName("SplcTransceiverLogDock")
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.log_panel = LogWindow(self)
        self.summary_panel = SummaryLogWindow(self)
        self.summary_panel.set_summary_color(True)
        self.monitor = RealtimeMonitorWidget(self)
        self.monitor.set_splc_header_split(True)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.log_panel, app_icons.load_icon("terminal"), "收发日志")
        self.tabs.addTab(self.summary_panel, app_icons.load_icon("summary"), "摘要日志")
        self.tabs.addTab(self.monitor, app_icons.load_icon("activity"), "接收监控")
        self.setWidget(self.tabs)
        # 日志窗默认浮在主窗口外：页面本身要留给用例与步骤表
        self.setMinimumSize(720, 320)

    def append_summary(self, time_text: str, port_label: str, direction: str,
                       summary: str, note: str = ""):
        self.summary_panel.append(time_text, port_label, direction, summary, note)


# ======================================================================
# 组帧对话框（复用协议9 组帧面板：含「仿照报文 / 模板」反解区）
# ======================================================================

class FrameGenDialog(QDialog):
    """嵌入 :class:`CsgTestFrameGenWidget` 生成测试帧，返回 HEX 文本。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成测试帧（协议9 · 通感一体化）")
        self.resize(1180, 860)
        self._hex = ""

        from csg_test_frame_gen_widget import CsgTestFrameGenWidget
        import csg_new_gen_frame_gen as fg

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        hint = QLabel(
            "「生成并填入」会把当前「输出」层次的报文写进步骤的发送数据。"
            "需要「粘贴现场报文 → 回填参数 → 微调再生成」时，用面板里的"
            "「⓪ 仿照报文 / 模板」折叠区（与协议9 组帧页同一套反解与模板存档）。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.widget = CsgTestFrameGenWidget(link_layer_default=True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.widget)
        layout.addWidget(scroll, 1)

        self.preview = QLabel("—")
        self.preview.setFont(_mono_font())
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.preview)

        buttons = QDialogButtonBox()
        self.ok_btn = buttons.addButton("生成并填入", QDialogButtonBox.ButtonRole.AcceptRole)
        copy_btn = buttons.addButton("复制 HEX", QDialogButtonBox.ButtonRole.ActionRole)
        cancel_btn = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        copy_btn.clicked.connect(self._copy)
        layout.addWidget(buttons)

        try:
            self.widget.changed.connect(self._update_preview)
        except Exception:  # noqa: BLE001 - 信号缺失不影响主功能
            pass
        self._fg_error = fg.FrameBuildError
        self._update_preview()

    def _build_hex(self) -> Tuple[str, str]:
        """返回 (hex, 错误)。"""
        try:
            result = self.widget.build()
        except self._fg_error as exc:
            return "", str(exc)
        except Exception as exc:  # noqa: BLE001 - 组帧参数异常统一提示
            return "", f"组帧失败：{exc}"
        if result is None:
            return "", "未选择测试模式"
        data = self.widget.output_bytes(result)
        if not data:
            return "", "当前输出层次没有内容"
        return core.bytes_to_hex(data), ""

    def _update_preview(self):
        text, error = self._build_hex()
        if error:
            self.preview.setText(f"⚠ {error}")
            self.ok_btn.setEnabled(False)
            return
        self.ok_btn.setEnabled(True)
        length = len(text.split())
        self.preview.setText(f"共 {length} 字节：{text}")

    def _accept(self):
        text, error = self._build_hex()
        if error:
            QMessageBox.warning(self, "生成测试帧", error)
            return
        self._hex = text
        self.accept()

    def _copy(self):
        text, error = self._build_hex()
        if error:
            QMessageBox.warning(self, "生成测试帧", error)
            return
        QGuiApplication.clipboard().setText(text)
        self.preview.setText(f"已复制到剪贴板：{text}")

    def frame_hex(self) -> str:
        return self._hex


# ======================================================================
# 步骤编辑对话框
# ======================================================================

class StepDialog(QDialog):
    """新增/编辑一个步骤（业务数据帧 / 设备命令 / 等待 / 透传）。"""

    def __init__(self, parent=None, step: Optional[core.Step] = None,
                 defaults: Optional[Dict[str, object]] = None):
        super().__init__(parent)
        self.setWindowTitle("步骤")
        self.resize(720, 620)
        self._step = core.Step.from_dict((step or core.Step()).to_dict())
        self._defaults = dict(defaults or {})
        self._field_widgets: List[QWidget] = []
        self._mon_field_widgets: List[QWidget] = []
        self._build_ui()
        self._apply_step(self._step)

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        common = QGroupBox("基本信息")
        grid = QGridLayout(common)
        grid.setContentsMargins(6, 4, 6, 4)
        grid.setSpacing(6)
        grid.addWidget(QLabel("类别:"), 0, 0)
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        for item in ("配置", "发送", "发送10", "发送20", "发送40", "发送50",
                     "等待", "工装板"):
            self.category_combo.addItem(item)
        grid.addWidget(self.category_combo, 0, 1)

        grid.addWidget(QLabel("名称:"), 0, 2)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如：载波初频帧-6-2 / MAC层透传")
        grid.addWidget(self.name_edit, 0, 3)

        grid.addWidget(QLabel("步骤类型:"), 1, 0)
        self.kind_combo = QComboBox()
        for key, label in core.STEP_KINDS.items():
            self.kind_combo.addItem(label, key)
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        grid.addWidget(self.kind_combo, 1, 1)

        grid.addWidget(QLabel("信道/端口:"), 1, 2)
        self.port_combo = QComboBox()
        for key in ("HPLC", "RF", "工装板", "接收机"):
            self.port_combo.addItem(key)
        grid.addWidget(self.port_combo, 1, 3)

        grid.addWidget(QLabel("发送次数:"), 2, 0)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(0, 100000)
        self.count_spin.setToolTip("0 表示沿用顶栏「发送次数」")
        grid.addWidget(self.count_spin, 2, 1)

        grid.addWidget(QLabel("发送间隔:"), 2, 2)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(0, 3600000)
        self.interval_spin.setSuffix(" ms")
        self.interval_spin.setToolTip("0 表示沿用顶栏「发送间隔」")
        grid.addWidget(self.interval_spin, 2, 3)

        grid.addWidget(QLabel("备注:"), 3, 0)
        self.note_edit = QLineEdit()
        grid.addWidget(self.note_edit, 3, 1, 1, 3)
        layout.addWidget(common)

        # ---- 发射机数据报文（PLC2.0，ED..EE）----
        self.data_group = QGroupBox(
            "发射机数据报文（PLC2.0 · ED..EE；业务帧外由硬件按下面参数封装）")
        data_layout = QVBoxLayout(self.data_group)
        data_layout.setContentsMargins(6, 4, 6, 4)
        data_layout.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel("类型:"))
        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.setMinimumWidth(240)
        for name in self._mode_type_names():
            self.type_combo.addItem(name)
        row.addWidget(self.type_combo)
        row.addWidget(QLabel("参数:"))
        self.param_edit = QLineEdit()
        self.param_edit.setPlaceholderText("如：载波初频帧-6-2 / 频点16option2")
        row.addWidget(self.param_edit, 1)
        data_layout.addLayout(row)

        # 控制域2 + 物理信道 + 时间戳
        head_row = QHBoxLayout()
        head_row.setSpacing(6)
        head_row.addWidget(QLabel("数据子类型:"))
        self.ctrl2_combo = QComboBox()
        for value in (0x02, 0x01, 0x03, 0x08, 0x06, 0x07):
            self.ctrl2_combo.addItem(f"0x{value:02X} {core.TX_DATA_SUBTYPES[value]}", value)
        self.ctrl2_combo.setToolTip(
            "0x02 FC+Payload（最常用）/0x01 FC/0x03 Payload/0x08 UL-OFDMA/\n"
            "0x06 双信道、0x07 OFDMA 四用户 结构自由，需勾选「手工数据域」")
        self.ctrl2_combo.currentIndexChanged.connect(self._on_ctrl2_changed)
        head_row.addWidget(self.ctrl2_combo)

        head_row.addWidget(QLabel("物理信道:"))
        self.channel_combo = QComboBox()
        for value, label in ((0x01, "HPLC"), (0x02, "RF"), (0x03, "HPLC+RF"),
                             (0x20, "PLC2.0 OFDMA")):
            self.channel_combo.addItem(f"0x{value:02X} {label}", value)
        for value in range(core.PHY_CHANNEL_MIMO_RANGE[0],
                           core.PHY_CHANNEL_MIMO_RANGE[1] + 1):
            self.channel_combo.addItem(f"0x{value:02X} MIMO", value)
        head_row.addWidget(self.channel_combo)

        head_row.addWidget(QLabel("时间戳:"))
        self.ts_combo = QComboBox()
        self.ts_combo.addItem("立即发送(0)", 0)
        self.ts_combo.addItem("触发发送(FFFFFFFF)", 0xFFFFFFFF)
        self.ts_combo.addItem("定时发送…", -1)
        self.ts_combo.currentIndexChanged.connect(self._on_ts_changed)
        head_row.addWidget(self.ts_combo)
        self.ts_spin = QSpinBox()
        self.ts_spin.setRange(0, 0x7FFFFFFF)
        self.ts_spin.setToolTip("定时发送的预置时间（4 字节小端；0xFFFFFFFF 保留给「触发发送」）")
        self.ts_spin.setVisible(False)
        head_row.addWidget(self.ts_spin)
        head_row.addStretch(1)
        data_layout.addLayout(head_row)

        # 物理块 + CRC + OFDMA 三个小字段
        pb_row = QHBoxLayout()
        pb_row.setSpacing(6)
        pb_row.addWidget(QLabel("物理块个数:"))
        self.pb_count_spin = QSpinBox()
        self.pb_count_spin.setRange(0, 255)
        pb_row.addWidget(self.pb_count_spin)
        pb_row.addWidget(QLabel("单个物理块长度:"))
        self.pb_len_spin = QSpinBox()
        self.pb_len_spin.setRange(0, 65535)
        self.pb_len_spin.setToolTip("0 = 按业务帧长度自动填")
        pb_row.addWidget(self.pb_len_spin)
        self.crc_error_chk = QCheckBox("Payload CRC 错误")
        pb_row.addWidget(self.crc_error_chk)
        self.tmi_label = QLabel("TMI:")
        pb_row.addWidget(self.tmi_label)
        self.tmi_spin = QSpinBox()
        self.tmi_spin.setRange(0, 255)
        pb_row.addWidget(self.tmi_spin)
        self.ru_label = QLabel("RU:")
        pb_row.addWidget(self.ru_label)
        self.ru_spin = QSpinBox()
        self.ru_spin.setRange(0, 255)
        pb_row.addWidget(self.ru_spin)
        self.pad_label = QLabel("pad:")
        pb_row.addWidget(self.pad_label)
        self.pad_spin = QSpinBox()
        self.pad_spin.setRange(0, 255)
        pb_row.addWidget(self.pad_spin)
        self.manual_chk = QCheckBox("手工数据域")
        self.manual_chk.setToolTip(
            "勾选后下面的 HEX 视为**完整数据域**（不再自动拼公共头），"
            "用于 0x06 双信道 / 0x07 OFDMA 四用户等自由结构")
        self.manual_chk.toggled.connect(self._on_manual_toggled)
        pb_row.addWidget(self.manual_chk)
        pb_row.addStretch(1)
        data_layout.addLayout(pb_row)

        self.data_edit = QPlainTextEdit()
        self.data_edit.setFont(_mono_font())
        self.data_edit.setPlaceholderText(
            "业务帧 HEX（FC + Payload；ED..EE 包装与公共头会自动补）")
        self.data_edit.setMinimumHeight(110)
        self.data_edit.textChanged.connect(self._update_data_hint)
        data_layout.addWidget(self.data_edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        gen_btn = QPushButton("从组帧页生成…")
        set_btn_icon(gen_btn, "add")
        gen_btn.setToolTip("打开协议9 组帧面板（含「仿照报文/模板」反解），生成后自动填入")
        gen_btn.clicked.connect(self._open_frame_gen)
        btn_row.addWidget(gen_btn)

        paste_btn = QPushButton("粘贴报文")
        set_btn_icon(paste_btn, "copy")
        paste_btn.clicked.connect(self._paste_clipboard)
        btn_row.addWidget(paste_btn)

        strip_btn = QPushButton("剥离监控包装")
        strip_btn.setToolTip("粘贴的是 96..16 监控包装整帧 / ED..EE 发射机整帧时，"
                             "按键剥掉包装只留业务帧")
        strip_btn.clicked.connect(self._strip_wrapper)
        btn_row.addWidget(strip_btn)

        clear_btn = QPushButton("清空")
        set_btn_icon(clear_btn, "clear")
        clear_btn.clicked.connect(lambda: self.data_edit.setPlainText(""))
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        data_layout.addLayout(btn_row)

        self.data_hint = QLabel("—")
        self.data_hint.setWordWrap(True)
        data_layout.addWidget(self.data_hint)
        layout.addWidget(self.data_group)

        # ---- 发射机控制报文（PLC2.0，控制域1=0x01）----
        self.cmd_group = QGroupBox("发射机控制报文（PLC2.0 · 控制域1=0x01）")
        cmd_layout = QVBoxLayout(self.cmd_group)
        cmd_layout.setContentsMargins(6, 4, 6, 4)
        cmd_layout.setSpacing(4)

        cmd_row = QHBoxLayout()
        cmd_row.setSpacing(6)
        cmd_row.addWidget(QLabel("控制指令:"))
        self.cmd_combo = QComboBox()
        for definition in core.sendable_tx_commands():
            self.cmd_combo.addItem(f"0x{definition.ctrl2:02X} {definition.name}",
                                   f"{definition.ctrl2:02X}")
        self.cmd_combo.currentIndexChanged.connect(self._rebuild_cmd_fields)
        cmd_row.addWidget(self.cmd_combo, 1)
        cmd_layout.addLayout(cmd_row)

        self.cmd_fields_host = QWidget()
        self.cmd_fields_layout = QFormLayout(self.cmd_fields_host)
        self.cmd_fields_layout.setContentsMargins(0, 0, 0, 0)
        self.cmd_fields_layout.setSpacing(4)
        cmd_layout.addWidget(self.cmd_fields_host)

        self.cmd_tail_label = QLabel("附加数据:")
        self.cmd_tail_edit = QPlainTextEdit()
        self.cmd_tail_edit.setFont(_mono_font())
        self.cmd_tail_edit.setMinimumHeight(60)
        self.cmd_tail_edit.textChanged.connect(self._update_cmd_preview)
        self.cmd_tail_row = QWidget()
        tail_layout = QVBoxLayout(self.cmd_tail_row)
        tail_layout.setContentsMargins(0, 0, 0, 0)
        tail_layout.setSpacing(2)
        tail_layout.addWidget(self.cmd_tail_label)
        tail_layout.addWidget(self.cmd_tail_edit)
        cmd_layout.addWidget(self.cmd_tail_row)

        self.cmd_preview = QLabel("—")
        self.cmd_preview.setFont(_mono_font())
        self.cmd_preview.setWordWrap(True)
        self.cmd_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cmd_layout.addWidget(self.cmd_preview)
        layout.addWidget(self.cmd_group)

        # ---- 接收机（监控器）命令（68..16）----
        self.monitor_group = QGroupBox("接收机 · 监控器命令（68H..16H）")
        mon_layout = QVBoxLayout(self.monitor_group)
        mon_layout.setContentsMargins(6, 4, 6, 4)
        mon_layout.setSpacing(4)
        mon_row = QHBoxLayout()
        mon_row.setSpacing(6)
        mon_row.addWidget(QLabel("命令:"))
        self.mon_combo = QComboBox()
        for cmd_id in sorted(core.COMMANDS):
            definition = core.COMMANDS[cmd_id]
            if definition.settable:
                self.mon_combo.addItem(f"0x{cmd_id:02X} {definition.name}",
                                       core.command_ref(cmd_id, 1))
                self.mon_combo.addItem(f"0x{cmd_id:02X} 查询{definition.name}",
                                       core.command_ref(cmd_id, 0))
            else:
                self.mon_combo.addItem(f"0x{cmd_id:02X} {definition.name}",
                                       core.command_ref(cmd_id, 0))
        self.mon_combo.currentIndexChanged.connect(self._rebuild_monitor_fields)
        mon_row.addWidget(self.mon_combo, 1)
        mon_layout.addLayout(mon_row)

        self.mon_fields_host = QWidget()
        self.mon_fields_layout = QFormLayout(self.mon_fields_host)
        self.mon_fields_layout.setContentsMargins(0, 0, 0, 0)
        self.mon_fields_layout.setSpacing(4)
        mon_layout.addWidget(self.mon_fields_host)

        self.mon_preview = QLabel("—")
        self.mon_preview.setFont(_mono_font())
        self.mon_preview.setWordWrap(True)
        mon_layout.addWidget(self.mon_preview)
        layout.addWidget(self.monitor_group)

        # ---- 等待 ----
        self.wait_group = QGroupBox("等待")
        wait_layout = QHBoxLayout(self.wait_group)
        wait_layout.setContentsMargins(6, 4, 6, 4)
        wait_layout.addWidget(QLabel("时长:"))
        self.wait_spin = QSpinBox()
        self.wait_spin.setRange(0, 3600000)
        self.wait_spin.setSuffix(" ms")
        wait_layout.addWidget(self.wait_spin)
        wait_layout.addStretch(1)
        layout.addWidget(self.wait_group)

        # ---- 透传 ----
        self.raw_group = QGroupBox("透传报文（原样写串口，不封帧）")
        raw_layout = QVBoxLayout(self.raw_group)
        raw_layout.setContentsMargins(6, 4, 6, 4)
        raw_layout.setSpacing(4)
        self.raw_edit = QPlainTextEdit()
        self.raw_edit.setFont(_mono_font())
        self.raw_edit.setPlaceholderText("如：AA 55 01 00 …")
        self.raw_edit.setMinimumHeight(90)
        raw_layout.addWidget(self.raw_edit)
        layout.addWidget(self.raw_group)

        layout.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _mode_type_names() -> List[str]:
        names = ["MAC层透传", "业务数据帧", "自定义"]
        try:
            import csg_new_gen_frame_gen as fg

            for mode in fg.test_modes():
                names.append(mode.name)
        except Exception:  # noqa: BLE001 - 组帧模块异常不影响编辑
            pass
        # 去重保序
        seen = set()
        unique = []
        for name in names:
            if name not in seen:
                seen.add(name)
                unique.append(name)
        return unique

    # ------------------------------------------------------------ 状态切换
    def _on_kind_changed(self, _index: int = 0):
        kind = self.kind_combo.currentData()
        self.data_group.setVisible(kind == "data")
        self.cmd_group.setVisible(kind == "command")
        self.monitor_group.setVisible(kind == "monitor")
        self.wait_group.setVisible(kind == "wait")
        self.raw_group.setVisible(kind == "raw")
        if kind == "command":
            self._rebuild_cmd_fields()
        elif kind == "monitor":
            self._rebuild_monitor_fields()
        elif kind == "data":
            self._update_data_hint()
        self.port_combo.setEnabled(kind == "raw")
        if kind == "raw" and self.port_combo.currentText() not in ("工装板", "接收机"):
            self.port_combo.setCurrentText("工装板")

    def _on_ctrl2_changed(self, _index: int = 0):
        """切换数据子类型：0x06/0x07 强制「手工数据域」，0x08 才显示 TMI/RU/pad。"""
        ctrl2 = int(self.ctrl2_combo.currentData() or 0x02)
        structured = ctrl2 in core.TX_STRUCTURED_SUBTYPES
        self.manual_chk.setEnabled(ctrl2 not in (0x06, 0x07))
        if ctrl2 in (0x06, 0x07):
            self.manual_chk.setChecked(True)
        for widget in (self.pb_count_spin, self.pb_len_spin, self.crc_error_chk,
                       self.channel_combo, self.ts_combo):
            widget.setEnabled(structured and not self.manual_chk.isChecked())
        is_ul = ctrl2 == 0x08
        for widget in (self.tmi_label, self.tmi_spin, self.ru_label, self.ru_spin,
                       self.pad_label, self.pad_spin):
            widget.setVisible(is_ul)
        self._update_data_hint()

    def _on_manual_toggled(self, checked: bool):
        ctrl2 = int(self.ctrl2_combo.currentData() or 0x02)
        structured = ctrl2 in core.TX_STRUCTURED_SUBTYPES and not checked
        for widget in (self.pb_count_spin, self.pb_len_spin, self.crc_error_chk,
                       self.channel_combo, self.ts_combo):
            widget.setEnabled(structured)
        self._update_data_hint()

    def _on_ts_changed(self, _index: int = 0):
        custom = int(self.ts_combo.currentData() or 0) < 0
        self.ts_spin.setVisible(custom)
        self._update_data_hint()

    # ---- 发射机控制报文 ----
    def _clear_cmd_fields(self, layout=None):
        layout = layout or self.cmd_fields_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._field_widgets = []

    def _rebuild_cmd_fields(self, *_args):
        """按当前控制指令重建字段控件（指令没变就不重建，避免冲掉回填值）。"""
        ref = self.cmd_combo.currentData()
        if ref == getattr(self, "_fields_ref", None) and self._field_widgets:
            self._update_cmd_preview()
            return
        self._fields_ref = ref
        self._clear_cmd_fields()
        ctrl2 = core._parse_hex_code(ref)
        definition = core.TX_COMMANDS.get(ctrl2)
        if definition is None:
            self.cmd_preview.setText("—")
            self.cmd_tail_row.setVisible(False)
            return
        for spec in definition.fields:
            if spec.kind == "pad":
                continue
            if spec.choices:
                combo = QComboBox()
                for value in sorted(spec.choices):
                    combo.addItem(f"{value}-{spec.choices[value]}", value)
                combo.currentIndexChanged.connect(self._update_cmd_preview)
                self.cmd_fields_layout.addRow(f"{spec.name}:", combo)
                self._field_widgets.append(combo)
            elif spec.kind == "u32le":
                edit = U32Edit(spec.maximum)
                if spec.help:
                    edit.setToolTip(spec.help)
                edit.textChanged.connect(self._update_cmd_preview)
                self.cmd_fields_layout.addRow(f"{spec.name}:", edit)
                self._field_widgets.append(edit)
            else:
                spin = QSpinBox()
                spin.setRange(spec.minimum, min(spec.maximum, 0x7FFFFFFF))
                if spec.suffix:
                    spin.setSuffix(spec.suffix)
                if spec.help:
                    spin.setToolTip(spec.help)
                spin.valueChanged.connect(self._update_cmd_preview)
                self.cmd_fields_layout.addRow(f"{spec.name}:", spin)
                self._field_widgets.append(spin)
        if not definition.fields:
            self.cmd_fields_layout.addRow(QLabel("该指令无数据域"))
        self.cmd_tail_row.setVisible(bool(definition.tail))
        if definition.tail:
            self.cmd_tail_label.setText(f"{definition.tail}（HEX）:")
        self._update_cmd_preview()

    def _cmd_values(self) -> List[int]:
        values: List[int] = []
        for widget in self._field_widgets:
            if isinstance(widget, QComboBox):
                data = widget.currentData()
                values.append(int(data) if data is not None else 0)
            elif isinstance(widget, QSpinBox):
                values.append(int(widget.value()))
            elif isinstance(widget, U32Edit):
                values.append(int(widget.value()))
        return values

    def _cmd_tail_bytes(self) -> bytes:
        text = self.cmd_tail_edit.toPlainText().strip()
        if not text:
            return b""
        return core.hex_to_bytes(text)

    def _update_cmd_preview(self):
        ctrl2 = core._parse_hex_code(self.cmd_combo.currentData() or "")
        definition = core.TX_COMMANDS.get(ctrl2)
        if definition is None:
            self.cmd_preview.setText("—")
            return
        try:
            tail = self._cmd_tail_bytes()
        except ValueError as exc:
            self.cmd_preview.setText(f"⚠ 附加数据 HEX 非法（{exc}）")
            return
        payload = core.tx_command_payload(ctrl2, self._cmd_values(), tail)
        if not payload.ok:
            self.cmd_preview.setText(f"⚠ {payload.error}")
            return
        frame = core.build_tx_frame(core.CTRL1_CONTROL, ctrl2, payload.payload)
        text = f"控制帧：{core.bytes_to_hex(frame)}"
        if definition.note:
            text += f"   （{definition.note}）"
        self.cmd_preview.setText(text)

    # ---- 接收机监控器命令（68..16）----
    def _clear_monitor_fields(self):
        while self.mon_fields_layout.count():
            item = self.mon_fields_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._mon_field_widgets = []

    def _rebuild_monitor_fields(self, *_args):
        ref = self.mon_combo.currentData()
        if ref == getattr(self, "_mon_fields_ref", None) and self._mon_field_widgets:
            self._update_monitor_preview()
            return
        self._mon_fields_ref = ref
        self._clear_monitor_fields()
        parsed = core.parse_command_ref(ref or "")
        if parsed is None:
            self.mon_preview.setText("—")
            return
        cmd_id, rw = parsed
        for spec in core.command_field_specs(cmd_id):
            if spec.choices:
                combo = QComboBox()
                for value in sorted(spec.choices):
                    combo.addItem(f"{value}-{spec.choices[value]}", value)
                combo.currentIndexChanged.connect(self._update_monitor_preview)
                self.mon_fields_layout.addRow(f"{spec.name}:", combo)
                self._mon_field_widgets.append(combo)
            elif spec.kind == "u32le":
                edit = U32Edit(spec.maximum)
                if spec.help:
                    edit.setToolTip(spec.help)
                edit.textChanged.connect(self._update_monitor_preview)
                self.mon_fields_layout.addRow(f"{spec.name}:", edit)
                self._mon_field_widgets.append(edit)
            else:
                spin = QSpinBox()
                spin.setRange(spec.minimum, min(spec.maximum, 0x7FFFFFFF))
                if spec.suffix:
                    spin.setSuffix(spec.suffix)
                if spec.help:
                    spin.setToolTip(spec.help)
                spin.valueChanged.connect(self._update_monitor_preview)
                self.mon_fields_layout.addRow(f"{spec.name}:", spin)
                self._mon_field_widgets.append(spin)
        if not core.command_field_specs(cmd_id):
            self.mon_fields_layout.addRow(QLabel("该命令无数据域"))
        self._update_monitor_preview()

    def _monitor_values(self) -> List[int]:
        values: List[int] = []
        for widget in self._mon_field_widgets:
            if isinstance(widget, QComboBox):
                data = widget.currentData()
                values.append(int(data) if data is not None else 0)
            elif isinstance(widget, QSpinBox):
                values.append(int(widget.value()))
            elif isinstance(widget, U32Edit):
                values.append(int(widget.value()))
        return values

    def _update_monitor_preview(self):
        parsed = core.parse_command_ref(self.mon_combo.currentData() or "")
        if parsed is None:
            self.mon_preview.setText("—")
            return
        cmd_id, rw = parsed
        payload = core.command_payload_from_values(cmd_id, self._monitor_values())
        if not payload.ok:
            self.mon_preview.setText(f"⚠ {payload.error}")
            return
        frame = core.build_command_frame(cmd_id, rw, payload.payload)
        self.mon_preview.setText(f"监控器命令帧：{core.bytes_to_hex(frame)}")

    def _update_data_hint(self):
        text = self.data_edit.toPlainText().strip()
        if not text:
            self.data_hint.setText("—")
            return
        try:
            payload = core.hex_to_bytes(text)
        except ValueError as exc:
            self.data_hint.setText(f"⚠ {exc}")
            return
        ctrl2 = int(self.ctrl2_combo.currentData() or 0x02)
        pieces = [f"{len(payload)} 字节"]
        if payload and payload[0] == core.TX_HEAD:
            info = core.parse_tx_frame(payload)
            if info.get("ok"):
                pieces.append(f"识别为整帧 ED..EE（{info['ctrl1_name']} / "
                              f"{info['ctrl2_name']}，数据域 {info['data_len']} 字节）")
            else:
                pieces.append("EDH 开头但结构不完整（将按业务帧再封装一层）")
        elif payload and core._looks_like_mpdu_fc(payload):
            delimiter = payload[0] & 0x07
            names = {0: "信标帧", 1: "SOF帧", 2: "选择确认帧", 3: "网间协调帧"}
            pieces.append(f"识别为 MPDU（定界符类型 {delimiter}·{names.get(delimiter, '?')}）")
        elif payload and payload[:1] == b"\x11":
            pieces.append("识别为应用层帧（无 MPDU 帧控制）")
        else:
            pieces.append("按业务帧发送")

        if self.manual_chk.isChecked():
            try:
                frame = core.build_tx_frame(core.CTRL1_DATA, ctrl2, payload)
            except ValueError as exc:
                self.data_hint.setText(f"⚠ {exc}")
                return
            pieces.append("手工数据域：不再自动拼公共头")
            pieces.append(f"封装后 {len(frame)} 字节")
        else:
            timestamp = self._timestamp_value()
            try:
                data = core.build_tx_data_payload(
                    ctrl2, payload=payload,
                    channel=int(self.channel_combo.currentData() or 0x01),
                    timestamp=timestamp, pb_count=self.pb_count_spin.value(),
                    pb_len=self.pb_len_spin.value(),
                    crc_error=1 if self.crc_error_chk.isChecked() else 0,
                    tmi=self.tmi_spin.value(), ru=self.ru_spin.value(),
                    pad=self.pad_spin.value())
                frame = core.build_tx_frame(core.CTRL1_DATA, ctrl2, data)
            except ValueError as exc:
                self.data_hint.setText(f"⚠ {exc}")
                return
            pieces.append(f"数据域 {len(data)} 字节")
            pieces.append(f"整帧 {len(frame)} 字节")
        self.data_hint.setText(" · ".join(pieces))

    def _timestamp_value(self) -> int:
        data = self.ts_combo.currentData()
        if data is None:
            return 0
        data = int(data)
        return self.ts_spin.value() if data < 0 else data

    # ------------------------------------------------------------ 按钮动作
    def _open_frame_gen(self):
        dialog = FrameGenDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.frame_hex():
            self.data_edit.setPlainText(dialog.frame_hex())

    def _paste_clipboard(self):
        text = QGuiApplication.clipboard().text()
        if not text.strip():
            QMessageBox.information(self, "粘贴报文", "剪贴板里没有文本。")
            return
        target = self.raw_edit if self.kind_combo.currentData() == "raw" else self.data_edit
        target.setPlainText(text.strip())

    def _strip_wrapper(self):
        """从整帧里剥掉包装，只留业务帧（支持 ED..EE 发射机帧与 96..16 监控帧）。"""
        text = self.data_edit.toPlainText().strip()
        if not text:
            return
        try:
            raw = core.hex_to_bytes(text)
        except ValueError as exc:
            self._notify("剥离包装", str(exc), level="error")
            return

        # ED..EE（发射机帧）：数据报文取「数据域」去掉公共头后的业务帧
        if raw[:1] == bytes([core.TX_HEAD]):
            info = core.parse_tx_frame(raw)
            if not info.get("ok"):
                self._notify("剥离包装", "这不是一帧完整的 ED..EE 帧。")
                return
            data = bytes(info.get("data") or b"")
            ctrl1 = int(info.get("ctrl1") or 0)
            ctrl2 = int(info.get("ctrl2") or 0)
            if ctrl1 == core.CTRL1_DATA:
                offset = {0x01: 9, 0x02: 9, 0x03: 9, 0x08: 12, 0x07: 40}.get(ctrl2)
                if offset and len(data) > offset:
                    data = data[offset:]
            self.data_edit.setPlainText(core.bytes_to_hex(data))
            return

        # 96..16（监控器帧）
        info = core.parse_data_frame(raw)
        if not info.get("ok"):
            self._notify("剥离包装", "这不是一帧完整的 96H 监控帧，也不是 ED..EE 发射机帧。")
            return
        data = bytes(info["data"])
        if info["proto_type"] == core.PROTO_TYPE_SPLC:
            splc_info, rest = core.split_splc_header(data)
            if splc_info is not None:
                data = rest
        self.data_edit.setPlainText(core.bytes_to_hex(data))

    # ------------------------------------------------------------ 取值 / 回填
    def _apply_step(self, step: core.Step):
        idx = self.kind_combo.findData(step.kind)
        self.kind_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.category_combo.setCurrentText(step.category or "发送")
        self.name_edit.setText(step.name)
        port_idx = self.port_combo.findText(step.port or "HPLC")
        self.port_combo.setCurrentIndex(port_idx if port_idx >= 0 else 0)
        self.count_spin.setValue(int(step.count))
        self.interval_spin.setValue(int(step.interval_ms))
        self.note_edit.setText(step.note)
        self.type_combo.setCurrentText(step.type or "业务数据帧")
        self.param_edit.setText(step.param)
        self.wait_spin.setValue(int(step.interval_ms))

        # 数据报文参数（先设控件，再联动可见性）
        ctrl2_index = self.ctrl2_combo.findData(int(step.ctrl2))
        self.ctrl2_combo.setCurrentIndex(ctrl2_index if ctrl2_index >= 0 else 0)
        channel_index = self.channel_combo.findData(int(step.channel))
        self.channel_combo.setCurrentIndex(channel_index if channel_index >= 0 else 0)
        ts = int(step.timestamp)
        if ts == core.TS_TRIGGER:
            self.ts_combo.setCurrentIndex(self.ts_combo.findData(core.TS_TRIGGER))
        elif ts == 0:
            self.ts_combo.setCurrentIndex(0)
        else:
            self.ts_combo.setCurrentIndex(self.ts_combo.findData(-1))
            self.ts_spin.setValue(min(ts, self.ts_spin.maximum()))
        self.pb_count_spin.setValue(int(step.pb_count))
        self.pb_len_spin.setValue(int(step.pb_len))
        self.crc_error_chk.setChecked(bool(step.crc_error))
        self.tmi_spin.setValue(int(step.tmi))
        self.ru_spin.setValue(int(step.ru))
        self.pad_spin.setValue(int(step.pad))
        self.manual_chk.setChecked(bool(step.manual_data))
        self._on_ts_changed()
        self._on_ctrl2_changed()
        self._on_manual_toggled(bool(step.manual_data))

        if step.kind == "command":
            ref = step.command or ""
            cmd_index = self.cmd_combo.findData(ref)
            if cmd_index < 0:
                cmd_index = self.cmd_combo.findData(f"{core._parse_hex_code(ref):02X}")
            self.cmd_combo.setCurrentIndex(max(0, cmd_index))
            # 必须先切换类型（会重建字段控件），再写字段值；反过来会在重建时清掉回填值
            self._on_kind_changed()
            ctrl2 = core._parse_hex_code(self.cmd_combo.currentData() or "")
            definition = core.TX_COMMANDS.get(ctrl2)
            if definition is not None and definition.tail:
                self.cmd_tail_edit.setPlainText(step.data)
            values = list(step.tx_values)
            if not values and definition is not None:
                # 老用例没存 tx_values 时，从数据域反推
                values = core.tx_command_values(ctrl2, core.hex_to_bytes(step.data))
            for widget, value in zip(self._field_widgets, values):
                if isinstance(widget, QComboBox):
                    pos = widget.findData(value)
                    if pos >= 0:
                        widget.setCurrentIndex(pos)
                elif isinstance(widget, (QSpinBox, U32Edit)):
                    widget.setValue(int(value))
            self._update_cmd_preview()
        elif step.kind == "monitor":
            ref = step.command or ""
            mon_index = self.mon_combo.findData(ref)
            if mon_index < 0:
                parsed = core.parse_command_ref(ref)
                if parsed:
                    mon_index = self.mon_combo.findData(core.command_ref(*parsed))
            self.mon_combo.setCurrentIndex(max(0, mon_index))
            self._on_kind_changed()
            parsed = core.parse_command_ref(self.mon_combo.currentData() or "")
            if parsed is not None:
                try:
                    payload = core.hex_to_bytes(step.data)
                except ValueError:
                    payload = b""
                values = core.command_values_from_payload(parsed[0], payload)
                for widget, value in zip(self._mon_field_widgets, values):
                    if isinstance(widget, QComboBox):
                        pos = widget.findData(value)
                        if pos >= 0:
                            widget.setCurrentIndex(pos)
                    elif isinstance(widget, (QSpinBox, U32Edit)):
                        widget.setValue(int(value))
            self._update_monitor_preview()
        elif step.kind == "raw":
            self.raw_edit.setPlainText(step.data)
            self._on_kind_changed()
        else:
            self.data_edit.setPlainText(step.data)
            self._on_kind_changed()

    def step(self) -> core.Step:
        """按当前控件取值生成步骤（**不**做合法性拦截，校验交给 validate_case）。"""
        kind = self.kind_combo.currentData() or "data"
        step = core.Step(
            kind=kind,
            category=self.category_combo.currentText().strip() or "发送",
            name=self.name_edit.text().strip(),
            type=self.type_combo.currentText().strip(),
            param=self.param_edit.text().strip(),
            count=int(self.count_spin.value()),
            interval_ms=int(self.interval_spin.value()),
            port=self.port_combo.currentText(),
            note=self.note_edit.text().strip(),
            enabled=True,
        )
        if kind == "data":
            step.ctrl2 = int(self.ctrl2_combo.currentData() or 0x02)
            step.channel = int(self.channel_combo.currentData() or 0x01)
            step.timestamp = int(self._timestamp_value())
            step.pb_count = int(self.pb_count_spin.value())
            step.pb_len = int(self.pb_len_spin.value())
            step.crc_error = 1 if self.crc_error_chk.isChecked() else 0
            step.tmi = int(self.tmi_spin.value())
            step.ru = int(self.ru_spin.value())
            step.pad = int(self.pad_spin.value())
            step.manual_data = bool(self.manual_chk.isChecked())
            step.data = self.data_edit.toPlainText().strip()
            step.port = "HPLC"
        elif kind == "command":
            ctrl2 = core._parse_hex_code(self.cmd_combo.currentData() or "")
            definition = core.TX_COMMANDS.get(ctrl2)
            step.command = core.tx_command_ref(ctrl2) if definition else ""
            step.tx_values = self._cmd_values()
            if definition is not None and definition.tail:
                step.data = self.cmd_tail_edit.toPlainText().strip()
            else:
                step.data = ""
            if step.count == 0:
                step.count = 1
            step.port = "HPLC"
        elif kind == "monitor":
            ref = self.mon_combo.currentData() or ""
            parsed = core.parse_command_ref(ref)
            step.command = core.command_ref(*parsed) if parsed else ""
            if parsed:
                payload = core.command_payload_from_values(parsed[0], self._monitor_values())
                step.data = core.bytes_to_hex(payload.payload) if payload.payload else ""
            if step.count == 0:
                step.count = 1
            step.port = "接收机"
        elif kind == "raw":
            step.data = self.raw_edit.toPlainText().strip()
        elif kind == "wait":
            step.data = ""
            step.interval_ms = int(self.wait_spin.value())
            step.count = 1
        return step

    def _accept(self):
        step = self.step()
        probe = core.Case(name="校验", steps=[step])
        errors, _warnings = core.validate_case(probe)
        if errors:
            QMessageBox.warning(self, "步骤不合法", "\n".join(errors))
            return
        self._step = step
        self.accept()


# ======================================================================
# 主页面
# ======================================================================

class _Runner:
    """执行状态（纯数据，便于测试与暂停/统计）。"""

    def __init__(self, actions: List[core.Action], duration_s: int):
        self.actions = actions
        self.index = 0
        self.total = len(actions)
        self.sent_ok = 0
        self.failed = 0
        self.started_at = time.monotonic()
        self.deadline = (self.started_at + duration_s) if duration_s > 0 else 0.0
        self.stopped = False


class SplcTransceiverWidget(QWidget):
    """收发机控制页（协议9 专用）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parser = None
        self._summary_fn: Optional[Callable[[list], str]] = None
        self._case = core.Case(name="新建用例")
        self._case_path: Optional[Path] = None
        self._dirty = False
        self._last_json_text = ""      # JSON 视图最近一次生成/应用的内容（判「有无未应用改动」）
        self._runner: Optional[_Runner] = None
        self._log_dock: Optional[TransceiverLogDock] = None
        self._settings = core.load_settings()

        self._tx = SplcSerialPort("tx", self)
        self._rx = SplcSerialPort("rx", self)
        self._fixture = SplcSerialPort("fixture", self)
        for worker in (self._tx, self._rx, self._fixture):
            worker.error_occurred.connect(self._on_serial_error)
            worker.log_message.connect(self._on_serial_log)

        self._run_timer = QTimer(self)
        self._run_timer.setSingleShot(True)
        self._run_timer.timeout.connect(self._run_next)

        self._rx_buffer = bytearray()
        self._tx_buffer = bytearray()

        self._build_ui()
        self._apply_settings()
        self._refresh_port_lists()
        self._refresh_case_tree()
        self._refresh_step_table()

        self._rx.raw_data_received.connect(self._on_rx_bytes)
        self._tx.raw_data_received.connect(self._on_tx_bytes)

    # ================================================================
    # 配置区高度（显式计算，见 FlowArea 说明）
    # ================================================================
    def _refresh_config_header(self) -> None:
        """标题栏摘要：折叠时也能看到「选的哪个口 / 开没开」，不必展开确认。"""
        section = getattr(self, "config_section", None)
        if section is None:
            return
        def _state(combo, btn) -> str:
            port = combo.currentText().strip() or "未选"
            return f"{port}·{'已开' if btn.isChecked() else '关'}"

        parts = [f"发射机 {_state(self.tx_port_combo, self.tx_open_btn)}",
                 f"接收机 {_state(self.rx_port_combo, self.rx_open_btn)}"]
        fixture = self.fixture_port_combo.currentText().strip()
        if fixture:
            parts.append(f"工装板 {_state(self.fixture_port_combo, self.fixture_open_btn)}")
        section.set_title_suffix("｜".join(parts))

    def _on_config_toggled(self, _expanded: bool) -> None:
        """折叠/展开后重算高度：展开时重新按可用宽度排老化区（FlowLayout 需要显式算高）。"""
        self._update_config_height()
        QTimer.singleShot(0, self._update_config_height)

    def _update_config_height(self):
        areas = getattr(self, "_flow_areas", None)
        if not areas:
            return
        section = getattr(self, "config_section", None)
        if section is not None and not section.is_expanded():
            # 折叠时内容区已隐藏：不锁死高度（否则标题栏下方会留一整块空白），
            # 交给布局按「标题栏」的 sizeHint 自适应
            section.setMinimumHeight(0)
            section.setMaximumHeight(16777215)
            return
        margins = self.config_layout.contentsMargins()
        width = max(320, self.width() - margins.left() - margins.right() - 28)
        total = 0
        for area in areas:
            height = area.height_for_width(width)
            if height <= 0:
                # 控件还没 isVisible()（页面刚建好 / 刚切到本页）时 FlowLayout 会跳过
                # 所有子项、算出 0 高度 —— 此时先按「一行」占位，等可见后由
                # showEvent 的 QTimer 再补算一次真实高度
                height = area.sizeHint().height()
            if area.height() != height:
                area.setFixedHeight(height)
            total += height
        spacing = self.config_layout.spacing()
        if spacing > 0:
            total += spacing * max(0, len(areas) - 1)
        header_h = 24
        if section is not None:
            header_h = max(24, section.header_button.sizeHint().height())
        total += margins.top() + margins.bottom() + header_h
        if self.config_group.height() != total:
            self.config_group.setFixedHeight(total)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_config_height()

    # 注意：`showEvent` 在文件末尾（生命周期一节）只定义**一次** —— 那里同时做
    # 「重算参数区高度 / 刷新串口列表 / 首次恢复上次用例」三件事。重复定义会静默覆盖。

    # ================================================================
    # 外部注入
    # ================================================================
    def set_protocol(self, parser, summary_fn: Optional[Callable[[list], str]] = None):
        """注入协议9 解析器与摘要函数（供「接收监控」页签与日志解析用）。"""
        self._parser = parser
        self._summary_fn = summary_fn
        if self._log_dock is not None:
            self._log_dock.monitor.set_protocol(parser, summary_fn, wrapper_format="hplc")

    # ================================================================
    # UI
    # ================================================================
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---------------- 公共参数（可折叠：默认收起把空间让给用例/步骤表）----------------
        self.config_section = collapsible_section.CollapsibleSection(
            "收发机公共参数", parent=self, expanded=False, key="splc_params")
        # `config_group` 保留为同一对象的别名（主程序/旧测试引用的就是这个属性名）
        self.config_group = config_group = self.config_section
        self.config_layout = self.config_section.content_layout()
        self.config_layout.setContentsMargins(6, 2, 6, 4)
        self.config_layout.setSpacing(2)
        self.config_section.toggled.connect(self._on_config_toggled)

        # 第 1 行：发射机串口
        tx_flow = FlowArea(spacing=6, parent=config_group)
        self.config_layout.addWidget(tx_flow)
        tx_flow.addWidget(QLabel("发射机串口:"))
        self.tx_port_combo = QComboBox()
        self.tx_port_combo.setMinimumWidth(110)
        tx_flow.addWidget(self.tx_port_combo)
        refresh_tx = QPushButton("刷新")
        set_btn_icon(refresh_tx, "refresh")
        refresh_tx.clicked.connect(self._refresh_port_lists)
        tx_flow.addWidget(refresh_tx)
        tx_flow.addWidget(QLabel("波特率:"))
        self.tx_baud_combo = QComboBox()
        self.tx_baud_combo.setEditable(True)
        self.tx_baud_combo.addItems(BAUD_CHOICES)
        self.tx_baud_combo.setMinimumWidth(96)
        tx_flow.addWidget(self.tx_baud_combo)
        tx_flow.addWidget(QLabel("校验:"))
        self.tx_parity_combo = QComboBox()
        self.tx_parity_combo.addItems(PARITY_CHOICES)
        self.tx_parity_combo.setToolTip("本协议规定：921600、8bit、1 位停止位、无校验")
        tx_flow.addWidget(self.tx_parity_combo)

        self.tx_open_btn = QPushButton("打开发射机")
        self.tx_open_btn.setCheckable(True)
        set_btn_icon(self.tx_open_btn, "play")
        self.tx_open_btn.toggled.connect(self._on_tx_open_toggled)
        tx_flow.addWidget(self.tx_open_btn)

        version_btn = QPushButton("读发射机版本")
        set_btn_icon(version_btn, "search")
        version_btn.setToolTip("下发 0x03 查询版本（应答含 DSP 版本/监控器版本/日期）")
        version_btn.clicked.connect(lambda: self._send_command(0x03, 0))
        tx_flow.addWidget(version_btn)
        tx_flow.addStretch(1)

        # 第 2 行：接收机串口 + 工装板
        rx_flow = FlowArea(spacing=6, parent=config_group)
        self.config_layout.addWidget(rx_flow)
        rx_flow.addWidget(QLabel("接收机串口:"))
        self.rx_port_combo = QComboBox()
        self.rx_port_combo.setMinimumWidth(110)
        rx_flow.addWidget(self.rx_port_combo)
        refresh_rx = QPushButton("刷新")
        set_btn_icon(refresh_rx, "refresh")
        refresh_rx.clicked.connect(self._refresh_port_lists)
        rx_flow.addWidget(refresh_rx)
        rx_flow.addWidget(QLabel("波特率:"))
        self.rx_baud_combo = QComboBox()
        self.rx_baud_combo.setEditable(True)
        self.rx_baud_combo.addItems(BAUD_CHOICES)
        self.rx_baud_combo.setMinimumWidth(96)
        rx_flow.addWidget(self.rx_baud_combo)
        rx_flow.addWidget(QLabel("校验:"))
        self.rx_parity_combo = QComboBox()
        self.rx_parity_combo.addItems(PARITY_CHOICES)
        rx_flow.addWidget(self.rx_parity_combo)
        self.rx_open_btn = QPushButton("打开接收机")
        self.rx_open_btn.setCheckable(True)
        set_btn_icon(self.rx_open_btn, "play")
        self.rx_open_btn.toggled.connect(self._on_rx_open_toggled)
        rx_flow.addWidget(self.rx_open_btn)

        rx_flow.addSpacing(12)
        rx_flow.addWidget(QLabel("工装板串口:"))
        self.fixture_port_combo = QComboBox()
        self.fixture_port_combo.setMinimumWidth(100)
        rx_flow.addWidget(self.fixture_port_combo)
        self.fixture_open_btn = QPushButton("打开工装板")
        self.fixture_open_btn.setCheckable(True)
        set_btn_icon(self.fixture_open_btn, "play")
        self.fixture_open_btn.toggled.connect(self._on_fixture_open_toggled)
        rx_flow.addWidget(self.fixture_open_btn)
        rx_flow.addStretch(1)

        # 第 3 行：发射机 PLC2.0 配置（频段/相线/物理信道/同步/CRC/Tonemask/RF信道）
        param_flow = FlowArea(spacing=6, parent=config_group)
        self.config_layout.addWidget(param_flow)
        param_flow.addWidget(QLabel("频段TAG:"))
        self.band_combo = QComboBox()
        for value in sorted(core.BAND_TAGS):
            self.band_combo.addItem(f"{value}-{core.BAND_TAGS[value]}", value)
        self.band_combo.setToolTip("控制域2=0x09 频段模式配置；切换后需等 2s")
        param_flow.addWidget(self.band_combo)

        param_flow.addWidget(QLabel("相线:"))
        self.phase_combo = QComboBox()
        for value in sorted(core.PHASE_CHOICES):
            self.phase_combo.addItem(core.PHASE_CHOICES[value], value)
        param_flow.addWidget(self.phase_combo)

        param_flow.addWidget(QLabel("物理信道:"))
        self.phy_mode_combo = QComboBox()
        self.phy_mode_combo.addItem("HPLC", 1)
        self.phy_mode_combo.addItem("RF", 2)
        self.phy_mode_combo.addItem("RF+HPLC", 3)
        self.phy_mode_combo.setToolTip("控制域2=0x23 进入特定物理信道收发模式")
        param_flow.addWidget(self.phy_mode_combo)

        param_flow.addWidget(QLabel("同步SFO:"))
        self.sfo_combo = QComboBox()
        for value in sorted(core.SFO_CHOICES):
            self.sfo_combo.addItem(core.SFO_CHOICES[value], value)
        param_flow.addWidget(self.sfo_combo)

        param_flow.addWidget(QLabel("同步类型:"))
        self.sync_combo = QComboBox()
        for value in sorted(core.SYNC_CHOICES):
            self.sync_combo.addItem(core.SYNC_CHOICES[value], value)
        param_flow.addWidget(self.sync_combo)

        param_flow.addWidget(QLabel("硬件CRC:"))
        self.fill_crc_combo = QComboBox()
        for value in sorted(core.FILL_CRC_CHOICES):
            self.fill_crc_combo.addItem(core.FILL_CRC_CHOICES[value], value)
        param_flow.addWidget(self.fill_crc_combo)

        param_flow.addWidget(QLabel("Tonemask:"))
        self.tonemask_combo = QComboBox()
        for value in sorted(core.TONEMASK_CHOICES):
            self.tonemask_combo.addItem(core.TONEMASK_CHOICES[value], value)
        param_flow.addWidget(self.tonemask_combo)

        param_flow.addWidget(QLabel("RF频点index:"))
        self.rf_index_spin = QSpinBox()
        self.rf_index_spin.setRange(0, 65535)
        param_flow.addWidget(self.rf_index_spin)
        param_flow.addWidget(QLabel("Option:"))
        self.rf_option_spin = QSpinBox()
        self.rf_option_spin.setRange(0, 3)
        param_flow.addWidget(self.rf_option_spin)
        param_flow.addStretch(1)

        # 第 4 行：发射机一键指令 + 运行参数
        action_flow = FlowArea(spacing=6, parent=config_group)
        self.config_layout.addWidget(action_flow)

        tx_btns = (
            ("复位", 0x00, {}, "控制域2=0x00 复位（接口未定义确认指令）"),
            ("读平台时间", 0x03, {}, "控制域2=0x03，应答返回 4 字节时间戳"),
            ("设置频段", 0x09, {"band": True}, "0x09 频段模式配置（TAG + 保留 3 字节）"),
            ("设置相线", 0x0B, {"phase": True}, "0x0B 设置通讯相线（A/B/C）"),
            ("进入物理信道", 0x23, {"phy": True}, "0x23 进入特定物理信道收发模式"),
            ("设置同步", 0x19, {"sfo": True}, "0x19 同步时钟与补偿频偏（SFO + 同步类型）"),
            ("填充CRC", 0x15, {"crc": True}, "0x15 硬件填充/不填充 CRC"),
            ("设置Tonemask", 0x17, {"tm": True}, "0x17 Tonemask 测试模式（切换后等 2s）"),
            ("RF信道切换", 0x25, {"rf": True}, "0x25 频点index + Option"),
            ("启动NTB", 0x31, {}, "0x31 启动 A/B/C 三相过零 NTB 采集"),
            ("停止NTB", 0x33, {}, "0x33 停止 NTB 采集"),
        )
        for label, ctrl2, _flags, tip in tx_btns:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _checked=False, c=ctrl2: self._send_tx_command(c))
            action_flow.addWidget(btn)

        # 第 5 行：运行控制（与指令按钮分开，启动/停止不会被挤到第二行）
        run_flow = FlowArea(spacing=6, parent=config_group)
        self.config_layout.addWidget(run_flow)
        run_flow.addWidget(QLabel("发送次数:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100000)
        run_flow.addWidget(self.count_spin)
        run_flow.addWidget(QLabel("间隔:"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(0, 3600000)
        self.interval_spin.setSuffix(" ms")
        run_flow.addWidget(self.interval_spin)
        run_flow.addWidget(QLabel("持续时间:"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 6000)
        self.duration_spin.setSuffix(" 分钟")
        self.duration_spin.setToolTip("0 = 不限时（按步骤跑完即止）")
        run_flow.addWidget(self.duration_spin)

        self.auto_config_chk = QCheckBox("启动前先下发配置")
        self.auto_config_chk.setToolTip(
            "启动用例前先按上面参数下发：频段(0x09) → 相线(0x0B) → "
            "物理信道(0x23) → 同步(0x19)")
        self.auto_config_chk.setChecked(True)
        run_flow.addWidget(self.auto_config_chk)
        run_flow.addStretch(1)

        # 第 6 行：接收机（监控器）配置 —— 走 68..16 接口协议，发到**接收机串口**
        monitor_flow = FlowArea(spacing=6, parent=config_group)
        self.config_layout.addWidget(monitor_flow)
        monitor_flow.addWidget(QLabel("接收机（监控器）:"))
        self.monitor_band_combo = QComboBox()
        for value in sorted(core.BAND_NAMES):
            self.monitor_band_combo.addItem(f"{value}-{core.BAND_NAMES[value]}", value)
        monitor_flow.addWidget(self.monitor_band_combo)
        mon_band_btn = QPushButton("设置监控器频段")
        mon_band_btn.setToolTip("68..16 命令 0x01（发往接收机串口）")
        mon_band_btn.clicked.connect(self._cmd_monitor_set_band)
        monitor_flow.addWidget(mon_band_btn)
        mon_q_band_btn = QPushButton("查询监控器频段")
        mon_q_band_btn.clicked.connect(lambda: self._send_monitor_command(0x02, 0))
        monitor_flow.addWidget(mon_q_band_btn)

        monitor_flow.addWidget(QLabel("SNID:"))
        self.monitor_snid_spin = QSpinBox()
        self.monitor_snid_spin.setRange(0, 65535)
        self.monitor_snid_spin.setToolTip("0 = 不限制同步 SNID")
        monitor_flow.addWidget(self.monitor_snid_spin)
        mon_snid_btn = QPushButton("设置SNID")
        mon_snid_btn.clicked.connect(self._cmd_monitor_set_snid)
        monitor_flow.addWidget(mon_snid_btn)

        mon_ver_btn = QPushButton("读监控器版本")
        mon_ver_btn.setToolTip("68..16 命令 0x03（应答含 DSP/监控器版本与日期）")
        mon_ver_btn.clicked.connect(lambda: self._send_monitor_command(0x03, 0))
        monitor_flow.addWidget(mon_ver_btn)
        mon_mode_btn = QPushButton("设为监控器模式")
        mon_mode_btn.setToolTip("0x07 工作模式=0(监控器) + 通信协议=4(南网SPLC双模)")
        mon_mode_btn.clicked.connect(self._cmd_monitor_set_mode)
        monitor_flow.addWidget(mon_mode_btn)
        mon_q_mode_btn = QPushButton("查询监控器模式")
        mon_q_mode_btn.clicked.connect(lambda: self._send_monitor_command(0x08, 0))
        monitor_flow.addWidget(mon_q_mode_btn)

        self.crc_mode_chk = QCheckBox("CS 固定 0xFF")
        self.crc_mode_chk.setToolTip(
            "发射机帧 CS：不勾 = 按「帧头到数据域末累加取低 8 位」计算（可自证）；\n"
            "勾选 = 固定 0xFF（文档写「暂且保留，目前填 0xFF」）")
        monitor_flow.addWidget(self.crc_mode_chk)
        monitor_flow.addStretch(1)

        # 日志窗按钮放第 1 行（那行右侧本来就有余量）：留在动作行里会被挤到第 5 行、
        # 白占一整行高度
        log_btn = QPushButton("收发日志窗…")
        set_btn_icon(log_btn, "edit")
        log_btn.setToolTip("显示/隐藏浮动日志窗（可拖到主窗口外，也可拖回停靠）")
        log_btn.clicked.connect(self.show_log_window)
        tx_flow.addWidget(log_btn)
        action_flow.addStretch(1)

        layout.addWidget(config_group)

        # ---------------- 运行控制（**在折叠区之外**：折叠参数区后仍能启动/停止）----------------
        run_bar = QHBoxLayout()
        run_bar.setContentsMargins(0, 0, 0, 0)
        run_bar.setSpacing(6)
        self.start_btn = QPushButton("启动条目测试")
        set_btn_icon(self.start_btn, "play")
        self.start_btn.setToolTip(
            "执行整条用例的全部步骤（按「发送次数/间隔/持续时间」跑，可先下发配置）\n"
            "左侧用例列表可多选：选中多条用例时按列表顺序依次执行")
        self.start_btn.clicked.connect(self._start_run)
        run_bar.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        set_btn_icon(self.stop_btn, "stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("立即停止正在执行的用例（随时可用，不受参数区折叠影响）")
        self.stop_btn.clicked.connect(lambda: self.stop_run("手动停止"))
        run_bar.addWidget(self.stop_btn)

        self.run_target_label = QLabel("")
        self.run_target_label.setStyleSheet("color:#6E7781;")
        run_bar.addWidget(self.run_target_label)
        run_bar.addStretch(1)
        layout.addLayout(run_bar)

        # 折行高度由页面统一计算（见 _update_config_height）：QStackedWidget 不传播
        # heightForWidth，交给 Qt 排会把整个参数区压成一条缝
        self._flow_areas = [tx_flow, rx_flow, param_flow, action_flow, run_flow, monitor_flow]

        # ---------------- 主体：用例树 + 步骤表 ----------------
        splitter = QSplitter(Qt.Orientation.Horizontal)

        case_group = QGroupBox("测试条目列表（双击载入用例）")
        case_layout = QVBoxLayout(case_group)
        case_layout.setContentsMargins(4, 4, 4, 4)
        case_layout.setSpacing(4)
        self.case_tree = QTreeWidget()
        self.case_tree.setHeaderLabels(("用例 / 步骤", "步数"))
        self.case_tree.setColumnWidth(0, 230)
        self.case_tree.setAlternatingRowColors(True)
        self.case_tree.setUniformRowHeights(True)
        # 多选：选中多条用例后「启动条目测试」按列表顺序依次执行（用户口径）
        self.case_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.case_tree.itemDoubleClicked.connect(self._on_case_tree_double_clicked)
        self.case_tree.itemSelectionChanged.connect(self._on_case_tree_selection_changed)
        case_layout.addWidget(self.case_tree, 1)

        case_btns = QHBoxLayout()
        case_btns.setSpacing(4)
        new_btn = QPushButton("新建")
        set_btn_icon(new_btn, "add")
        new_btn.clicked.connect(self._new_case)
        case_btns.addWidget(new_btn)
        dup_btn = QPushButton("复制用例")
        set_btn_icon(dup_btn, "copy")
        dup_btn.setToolTip(
            "把当前用例整份复制成一个新用例文件（名称自动加「副本」），改完再「另存为」不影响原用例")
        dup_btn.clicked.connect(self._duplicate_case)
        case_btns.addWidget(dup_btn)
        open_btn = QPushButton("载入文件…")
        set_btn_icon(open_btn, "open_file")
        open_btn.setToolTip("从任意位置载入用例 JSON（也可以直接双击左上列表里的用例）")
        open_btn.clicked.connect(self._open_case_dialog)
        case_btns.addWidget(open_btn)
        save_btn = QPushButton("保存")
        set_btn_icon(save_btn, "save")
        save_btn.clicked.connect(self._save_case)
        case_btns.addWidget(save_btn)
        saveas_btn = QPushButton("另存为…")
        saveas_btn.clicked.connect(self._save_case_as)
        case_btns.addWidget(saveas_btn)
        delete_btn = QPushButton("删除")
        set_btn_icon(delete_btn, "delete")
        delete_btn.clicked.connect(self._delete_case)
        case_btns.addWidget(delete_btn)
        reload_btn = QPushButton("刷新")
        set_btn_icon(reload_btn, "refresh")
        reload_btn.clicked.connect(self._refresh_case_tree)
        case_btns.addWidget(reload_btn)
        case_layout.addLayout(case_btns)
        splitter.addWidget(case_group)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        info_row = QHBoxLayout()
        info_row.setSpacing(6)
        # 用例名称可直接改：改完「保存」就写进 JSON（另存为时同时跟随新文件名）
        info_row.addWidget(QLabel("用例名称:"))
        self.case_name_edit = QLineEdit()
        self.case_name_edit.setMinimumWidth(220)
        self.case_name_edit.setPlaceholderText("未命名用例")
        self.case_name_edit.setToolTip(
            "在这里改用例名称；点「保存」写回当前文件，点「另存为…」按新文件名另存一份")
        self.case_name_edit.textEdited.connect(self._on_case_name_edited)
        info_row.addWidget(self.case_name_edit, 1)
        self.case_label = QLabel("未载入用例")
        font = self.case_label.font()
        font.setBold(True)
        self.case_label.setFont(font)
        info_row.addWidget(self.case_label, 2)
        self.progress_label = QLabel("")
        info_row.addWidget(self.progress_label)
        right_layout.addLayout(info_row)

        self.step_table = ZoomableTableWidget(0, len(STEP_COLUMNS))
        self.step_table.setHorizontalHeaderLabels(STEP_COLUMNS)
        self.step_table.verticalHeader().setVisible(True)
        self.step_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.step_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.step_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.step_table.horizontalHeader()
        header.setSectionResizeMode(COL_DATA, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Interactive)
        self.step_table.setColumnWidth(COL_NAME, 190)
        header.setSectionResizeMode(COL_CATEGORY, QHeaderView.ResizeMode.Interactive)
        self.step_table.setColumnWidth(COL_CATEGORY, 84)
        for col in (COL_TYPE, COL_PARAM, COL_PORT):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        # 次/数/间/隔 这两个列头是 4 个汉字，ResizeToContents 在窄窗里会被后面
        # 的拉伸列挤掉，改成固定宽度（表头文案不会被裁）
        for col, width in ((COL_COUNT, 92), (COL_INTERVAL, 100)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.step_table.setColumnWidth(col, width)
        # 关掉自动换行：长 HEX 走省略号 + tooltip，避免一帧把行高撑成两行
        self.step_table.setWordWrap(False)
        self.step_table.verticalHeader().setDefaultSectionSize(24)
        self.step_table.doubleClicked.connect(lambda _i: self._edit_step())

        # 两种编辑方式（同一份用例）：表格视图 / JSON 视图
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setDocumentMode(True)
        self.editor_tabs.addTab(self.step_table, "表格视图")

        json_page = QWidget()
        json_layout = QVBoxLayout(json_page)
        json_layout.setContentsMargins(4, 4, 4, 4)
        json_layout.setSpacing(4)
        json_bar = QHBoxLayout()
        json_bar.setSpacing(6)
        self.json_apply_btn = QPushButton("应用 JSON 到用例")
        set_btn_icon(self.json_apply_btn, "save")
        self.json_apply_btn.setToolTip("解析下面的 JSON 并替换当前用例（错误会提示，不会改坏现有用例）")
        self.json_apply_btn.clicked.connect(self._apply_case_json)
        json_bar.addWidget(self.json_apply_btn)
        self.json_reload_btn = QPushButton("从用例重新生成")
        set_btn_icon(self.json_reload_btn, "refresh")
        self.json_reload_btn.setToolTip("丢弃编辑框里的内容，按当前用例重新生成 JSON")
        self.json_reload_btn.clicked.connect(self._reload_case_json)
        json_bar.addWidget(self.json_reload_btn)
        json_bar.addStretch(1)
        self.json_hint_label = QLabel("")
        json_bar.addWidget(self.json_hint_label)
        json_layout.addLayout(json_bar)

        self.case_json_edit = QPlainTextEdit()
        self.case_json_edit.setFont(_mono_font())
        self.case_json_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.case_json_edit.setPlaceholderText(
            "这里是用例文件的 JSON（format/version/name/params/steps）。\n"
            "改完点「应用 JSON 到用例」→ 表格视图同步；点「保存」才落盘。")
        json_layout.addWidget(self.case_json_edit, 1)
        self.editor_tabs.addTab(json_page, "JSON 视图")
        self.editor_tabs.currentChanged.connect(self._on_editor_tab_changed)
        right_layout.addWidget(self.editor_tabs, 1)

        step_btns = QHBoxLayout()
        step_btns.setSpacing(4)
        add_step_btn = QPushButton("新增步骤")
        set_btn_icon(add_step_btn, "add")
        add_step_btn.clicked.connect(self._add_step)
        step_btns.addWidget(add_step_btn)
        edit_step_btn = QPushButton("编辑")
        set_btn_icon(edit_step_btn, "edit")
        edit_step_btn.clicked.connect(self._edit_step)
        step_btns.addWidget(edit_step_btn)
        copy_step_btn = QPushButton("复制")
        set_btn_icon(copy_step_btn, "copy")
        copy_step_btn.clicked.connect(self._copy_step)
        step_btns.addWidget(copy_step_btn)
        del_step_btn = QPushButton("删除")
        set_btn_icon(del_step_btn, "delete")
        del_step_btn.clicked.connect(self._delete_steps)
        step_btns.addWidget(del_step_btn)
        up_btn = QPushButton("上移")
        set_btn_icon(up_btn, "up")
        up_btn.clicked.connect(lambda: self._move_step(-1))
        step_btns.addWidget(up_btn)
        down_btn = QPushButton("下移")
        set_btn_icon(down_btn, "down")
        down_btn.clicked.connect(lambda: self._move_step(1))
        step_btns.addWidget(down_btn)
        gen_btn = QPushButton("生成测试帧…")
        set_btn_icon(gen_btn, "add")
        gen_btn.setToolTip("从协议9 组帧面板生成业务帧，直接追加为新步骤")
        gen_btn.clicked.connect(self._append_generated_frame)
        step_btns.addWidget(gen_btn)
        step_btns.addStretch(1)
        right_layout.addLayout(step_btns)

        # 快捷发送区：把选中步骤立刻发一次，便于单步联调
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        self.quick_hex_edit = QLineEdit()
        self.quick_hex_edit.setFont(_mono_font())
        self.quick_hex_edit.setPlaceholderText(
            "快速发送：裸业务帧自动封 ED..EE（PLC2.0）；ED..EE / 96..16 整帧原样发；68..16 命令帧发到接收机口")
        quick_row.addWidget(self.quick_hex_edit, 1)
        quick_send_btn = QPushButton("发送一次")
        set_btn_icon(quick_send_btn, "play")
        quick_send_btn.clicked.connect(self._send_quick)
        quick_row.addWidget(quick_send_btn)
        sel_send_btn = QPushButton("发送选中步骤")
        sel_send_btn.clicked.connect(self._send_selected_step_once)
        quick_row.addWidget(sel_send_btn)
        right_layout.addLayout(quick_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)

    # ================================================================
    # 配置持久化
    # ================================================================
    def _apply_settings(self):
        s = self._settings
        self.tx_baud_combo.setCurrentText(str(s.get("tx_baud", 921600)))
        self.rx_baud_combo.setCurrentText(str(s.get("rx_baud", 921600)))
        self.tx_parity_combo.setCurrentText(str(s.get("tx_parity", "无")))
        self.rx_parity_combo.setCurrentText(str(s.get("rx_parity", "无")))
        self._set_combo_data(self.band_combo, int(s.get("tx_band", 2)))
        self._set_combo_data(self.phase_combo, int(s.get("tx_phase", 1)))
        self._set_combo_data(self.phy_mode_combo, int(s.get("tx_phy_mode", 1)))
        self._set_combo_data(self.sfo_combo, int(s.get("tx_sfo", 1)))
        self._set_combo_data(self.sync_combo, int(s.get("tx_sync", 1)))
        self._set_combo_data(self.fill_crc_combo, int(s.get("tx_fill_crc", 1)))
        self._set_combo_data(self.tonemask_combo, int(s.get("tx_tonemask", 0)))
        self.rf_index_spin.setValue(int(s.get("tx_rf_index", 0)))
        self.rf_option_spin.setValue(int(s.get("tx_rf_option", 2)))
        self._set_combo_data(self.monitor_band_combo, int(s.get("monitor_band", 2)))
        self.monitor_snid_spin.setValue(int(s.get("monitor_snid", 0)))
        self.crc_mode_chk.setChecked(str(s.get("tx_crc_mode", "sum")) == "xff")
        self.count_spin.setValue(max(1, int(s.get("count", 10))))
        self.interval_spin.setValue(int(s.get("interval_ms", 500)))
        self.duration_spin.setValue(int(s.get("duration_min", 180)))
        self._preferred_ports = {
            "tx": str(s.get("tx_port", "") or ""),
            "rx": str(s.get("rx_port", "") or ""),
            "fixture": str(s.get("fixture_port", "") or ""),
        }
        collapsible_section.apply_state([self.config_section], s.get("sections"))
        self._refresh_config_header()
        self._settings_writable = True

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: int):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _collect_settings(self) -> Dict[str, object]:
        return {
            # 折叠区状态（{key: 是否展开}）—— 与项目其它可折叠页同一口径
            "sections": collapsible_section.collect_state([self.config_section]),
            "tx_port": self.tx_port_combo.currentText().strip(),
            "tx_baud": self._combo_int(self.tx_baud_combo, 921600),
            "tx_parity": self.tx_parity_combo.currentText(),
            "rx_port": self.rx_port_combo.currentText().strip(),
            "rx_baud": self._combo_int(self.rx_baud_combo, 921600),
            "rx_parity": self.rx_parity_combo.currentText(),
            "fixture_port": self.fixture_port_combo.currentText().strip(),
            "fixture_baud": 921600,
            "tx_ctrl2": 0x02,
            "tx_channel": 0x01,
            "tx_timestamp": 0,
            "tx_pb_count": 1,
            "tx_pb_len": 0,
            "tx_crc_mode": "xff" if self.crc_mode_chk.isChecked() else "sum",
            "tx_band": self.band_combo.currentData() or 2,
            "tx_phase": self.phase_combo.currentData() or 1,
            "tx_phy_mode": self.phy_mode_combo.currentData() or 1,
            "tx_sfo": self.sfo_combo.currentData() or 1,
            "tx_sync": self.sync_combo.currentData() or 1,
            "tx_fill_crc": self.fill_crc_combo.currentData() or 1,
            "tx_tonemask": self.tonemask_combo.currentData() or 0,
            "tx_rf_index": self.rf_index_spin.value(),
            "tx_rf_option": self.rf_option_spin.value(),
            "monitor_band": self.monitor_band_combo.currentData() or 2,
            "monitor_snid": self.monitor_snid_spin.value(),
            "count": self.count_spin.value(),
            "interval_ms": self.interval_spin.value(),
            "duration_min": self.duration_spin.value(),
            "last_case": str(self._case_path or ""),
        }

    def _cs_mode(self) -> str:
        return "xff" if self.crc_mode_chk.isChecked() else "sum"

    @staticmethod
    def _combo_int(combo: QComboBox, fallback: int) -> int:
        try:
            return int(str(combo.currentText()).strip())
        except (TypeError, ValueError):
            return fallback

    def save_settings(self):
        if not getattr(self, "_settings_writable", False):
            return
        try:
            core.save_settings(self._collect_settings())
        except OSError as exc:
            print(f"[收发机] 配置保存失败：{exc}")

    # ================================================================
    # 串口
    # ================================================================
    def _refresh_port_lists(self):
        ports = SplcSerialPort.list_ports()
        for combo, key in ((self.tx_port_combo, "tx"),
                           (self.rx_port_combo, "rx"),
                           (self.fixture_port_combo, "fixture")):
            current = combo.currentText().strip() or getattr(
                self, "_preferred_ports", {}).get(key, "")
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(ports)
            combo.setEditable(False)
            if current:
                index = combo.findText(current)
                if index >= 0:
                    combo.setCurrentIndex(index)
                elif current and not combo.isEditable():
                    combo.addItem(current)
                    combo.setCurrentIndex(combo.count() - 1)
            combo.blockSignals(False)
        self._refresh_config_header()

    def _on_tx_open_toggled(self, checked: bool):
        if checked:
            self._tx.configure(self.tx_port_combo.currentText().strip(),
                               self._combo_int(self.tx_baud_combo, 921600),
                               self._parity_code(self.tx_parity_combo.currentText()))
            if not self._tx.open_port():
                self.tx_open_btn.blockSignals(True)
                self.tx_open_btn.setChecked(False)
                self.tx_open_btn.blockSignals(False)
                return
            self.tx_open_btn.setText("关闭发射机")
            self._log_note(f"发射机串口已打开：{self._tx.description()}")
            self._refresh_config_header()
            self.save_settings()
        else:
            self._tx.close_port()
            self.tx_open_btn.setText("打开发射机")
            self._log_note("发射机串口已关闭")
            self._refresh_config_header()

    def _on_rx_open_toggled(self, checked: bool):
        if checked:
            self._rx.configure(self.rx_port_combo.currentText().strip(),
                               self._combo_int(self.rx_baud_combo, 921600),
                               self._parity_code(self.rx_parity_combo.currentText()))
            if not self._rx.open_port():
                self.rx_open_btn.blockSignals(True)
                self.rx_open_btn.setChecked(False)
                self.rx_open_btn.blockSignals(False)
                return
            self.rx_open_btn.setText("关闭接收机")
            self._ensure_log_dock()
            self._log_note(f"接收机串口已打开：{self._rx.description()}")
            self._refresh_config_header()
            self.save_settings()
        else:
            self._rx.close_port()
            self.rx_open_btn.setText("打开接收机")
            self._log_note("接收机串口已关闭")
            self._refresh_config_header()

    def _on_fixture_open_toggled(self, checked: bool):
        if checked:
            self._fixture.configure(self.fixture_port_combo.currentText().strip(), 921600,
                                    self._parity_code(self.tx_parity_combo.currentText()))
            if not self._fixture.open_port():
                self.fixture_open_btn.blockSignals(True)
                self.fixture_open_btn.setChecked(False)
                self.fixture_open_btn.blockSignals(False)
                return
            self.fixture_open_btn.setText("关闭工装板")
            self._log_note(f"工装板串口已打开：{self._fixture.description()}")
            self._refresh_config_header()
            self.save_settings()
        else:
            self._fixture.close_port()
            self.fixture_open_btn.setText("打开工装板")
            self._log_note("工装板串口已关闭")
            self._refresh_config_header()

    @staticmethod
    def _parity_code(text: str) -> str:
        return {"无": "N", "偶": "E", "奇": "O"}.get(str(text).strip(), "N")

    def _on_serial_error(self, message: str):
        self._log_note(f"⚠ {message}", level="error")

    def _on_serial_log(self, message: str):
        self._log_note(message)

    # ================================================================
    # 日志窗
    # ================================================================
    def _ensure_log_dock(self) -> TransceiverLogDock:
        if self._log_dock is None:
            window = self.window()
            parent = window if isinstance(window, QMainWindow) else None
            self._log_dock = TransceiverLogDock(parent)
            self._log_dock.log_panel.set_view_mode("both")
            if self._parser is not None:
                self._log_dock.monitor.set_protocol(
                    self._parser, self._summary_fn, wrapper_format="hplc")
            self._log_dock.monitor.set_serial_worker(self._rx)
            if isinstance(window, QMainWindow):
                window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log_dock)
                # 默认浮在窗口外：页面本身要留给用例树与步骤表
                self._log_dock.setFloating(True)
                self._log_dock.resize(980, 460)
                self._log_dock.move(window.pos().x() + 80, window.pos().y() + 120)
        return self._log_dock

    def show_log_window(self):
        dock = self._ensure_log_dock()
        dock.show()
        dock.raise_()
        dock.activateWindow()

    def _log_note(self, text: str, level: str = "info"):
        dock = self._log_dock
        if dock is None:
            # 日志窗还没建时，先建一个隐藏的，避免早期事件丢失
            dock = self._ensure_log_dock()
        dock.log_panel.append_note(text, level=level)

    # ================================================================
    # 接收 / 发送日志
    # ================================================================
    def _on_rx_bytes(self, data: bytes):
        self._rx_buffer.extend(data)
        frames, consumed = core.deframe_stream(self._rx_buffer)
        if consumed > 0:
            del self._rx_buffer[:consumed]
        if len(self._rx_buffer) > 8192:      # 长时间收不到合法帧头时防止无界增长
            del self._rx_buffer[:len(self._rx_buffer) - 1024]
        dock = self._ensure_log_dock()
        for item in frames:
            rows, note, summary = self._describe_frame(item, received=True)
            dock.log_panel.append_rx("接收机", item["frame"], note, rows, summary)
            dock.append_summary(_fmt_time(), "接收机", "RX", summary, note)

    def _on_tx_bytes(self, data: bytes):
        """发射机串口不该有回包（文档：发射机模式不接收数据），收到就提示。"""
        self._tx_buffer.extend(data)
        frames, consumed = core.deframe_stream(self._tx_buffer)
        if consumed > 0:
            del self._tx_buffer[:consumed]
        dock = self._ensure_log_dock()
        for item in frames:
            rows, note, summary = self._describe_frame(item, received=True)
            dock.log_panel.append_rx("发射机(异常回包)", item["frame"], note, rows, summary)
            dock.append_summary(_fmt_time(), "发射机(异常回包)", "RX", summary, note)

    def _business_rows(self, payload: bytes) -> List[Tuple[str, str, str]]:
        """把业务帧（FC+Payload）交给协议9 解析器展开成日志行（不含摘要文本）。

        发射机侧原来只打「截断 HEX + 字节数」，日志里看不到 MPDU/应用层字段
        （用户报障：解析没把数据 FC+Payload 按协议9 展开）。这里与接收侧共用
        同一个解析器入口，**解析失败只降级成一行提示，不抛异常**。
        """
        return self._business_rows_and_summary(payload)[0]

    def _business_rows_and_summary(
            self, payload: bytes) -> Tuple[List[Tuple[str, str, str]], str]:
        """业务帧 → (日志行, 摘要)。摘要单独返回：日志里用绿色标出、摘要日志直接用它。"""
        rows: List[Tuple[str, str, str]] = []
        if not payload:
            return rows, ""
        if self._parser is None:
            rows.append(("── 业务帧（协议9）──", "", "未注入解析器，无法展开"))
            return rows, ""
        try:
            table = self._parser.parse_to_table(bytes(payload), parse_level="auto") or []
        except Exception as exc:  # noqa: BLE001 - 解析失败不影响发送
            rows.append(("── 业务帧（协议9）──", "", f"解析异常：{exc}"))
            return rows, ""
        summary = ""
        if self._summary_fn is not None:
            try:
                summary = self._summary_fn(table)
            except Exception:  # noqa: BLE001
                summary = ""
        # 分隔标题只做分隔：摘要统一由日志的绿色段/「摘要日志」承载，避免同一句出现两次
        rows.append(("── 业务帧（协议9 解析）──", "", ""))
        for row in table[:60]:
            name = str(row[0]) if len(row) > 0 else ""
            raw = str(row[1]) if len(row) > 1 else ""
            parsed = str(row[2]) if len(row) > 2 else ""
            rows.append((name, raw, parsed))
        if len(table) > 60:
            rows.append((f"…（共 {len(table)} 行）", "", "详细解析见「接收监控」页签"))
        return rows, summary

    def _business_summary(self, payload: bytes) -> str:
        """只要摘要（快速发送等不需要展开日志行的场合）。"""
        return self._business_rows_and_summary(payload)[1]

    def _describe_frame(self, item: Dict[str, object],
                        received: bool) -> Tuple[List[Tuple[str, str, str]], str]:
        """把一帧解出的报文展开成日志行 + 摘要；失败也不抛。

        返回 ``(rows, note, summary)``：``summary`` 是**解析出来的业务要点**（协议9
        摘要函数的结果），日志里用绿色标出、也直接喂给「摘要日志」页签。
        """
        frame = bytes(item.get("frame", b""))
        info = item.get("info") or {}
        rows: List[Tuple[str, str, str]] = []
        note = ""
        summary = ""
        if item.get("kind") == "tx":
            # 发射机帧（ED..EE）：PC 下发或设备回执
            note = (f"{info.get('ctrl1_name', '')} / {info.get('ctrl2_name', '')} "
                    f"{info.get('data_len', 0)} 字节")
            if info.get("cs_reserved"):
                note += "  CS=0xFF(保留)"
            elif not info.get("ok"):
                note += "  ⚠ CS 校验失败"
            rows.append(("整帧长度", str(len(frame)), str(len(frame))))
            rows.append(("控制域1", f"0x{info.get('ctrl1', 0):02X}",
                         str(info.get("ctrl1_name", ""))))
            rows.append(("控制域2", f"0x{info.get('ctrl2', 0):02X}",
                         str(info.get("ctrl2_name", ""))))
            rows.append(("帧长域", str(info.get("frame_len", "")),
                         str(info.get("frame_len", 0))))
            rows.append(("CS", f"0x{info.get('cs', 0):02X}",
                         "固定 0xFF（保留）" if info.get("cs_reserved")
                         else ("✓ 正确" if info.get("ok")
                               else f"✗ 应为 0x{info.get('cs_calc', 0):02X}")))
            ctrl1 = int(info.get("ctrl1") or 0)
            ctrl2 = int(info.get("ctrl2") or 0)
            if ctrl1 == core.CTRL1_DATA:
                data_bytes = bytes(info.get("data") or b"")
                payload_rows, payload_note = core.decode_tx_data_payload(ctrl2, data_bytes)
                rows.extend(payload_rows)
                if payload_note:
                    rows.append(("说明", "", payload_note))
                business = core.tx_business_payload(ctrl2, data_bytes)
                if business is not None:
                    biz_rows, biz_summary = self._business_rows_and_summary(business)
                    rows.extend(biz_rows)
                    summary = biz_summary
            elif ctrl1 == core.CTRL1_CONTROL:
                payload_rows, payload_note = core.decode_tx_control_payload(
                    ctrl2, bytes(info.get("data") or b""))
                rows.extend(payload_rows)
                if payload_note:
                    rows.append(("说明", "", payload_note))
            if info.get("error"):
                rows.append(("问题", "", str(info["error"])))
            return rows, note, summary

        if item.get("kind") == "cmd":
            note = (f"{info.get('cmd_name', '命令')}"
                    f"（{'应答' if info.get('direction') == 'response' else '下行'}）")
            if not info.get("ok"):
                note += "  ⚠ CS 校验失败"
            rows.append(("命令", f"0x{info.get('cmd_id', 0):02X}",
                         info.get("cmd_name", "")))
            if info.get("rw") is not None:
                rows.append(("读写", str(info.get("rw")),
                             "设置" if info.get("rw") else "查询"))
            rows.extend(info.get("fields") or [])
            if info.get("payload_note"):
                rows.append(("说明", "", info["payload_note"]))
            return rows, note, summary

        note = (f"业务数据帧 {info.get('proto_name', '')}/{info.get('channel_name', '')} "
                f"{info.get('data_len', 0)} 字节")
        if not info.get("ok"):
            note += "  ⚠ CS 校验失败"
        rows.append(("整帧长度", str(len(frame)), str(len(frame))))
        rows.append(("协议类型", str(info.get("proto_type", "")), info.get("proto_name", "")))
        rows.append(("信道", str(info.get("channel", "")), info.get("channel_name", "")))
        rows.append(("帧长", str(info.get("data_len", "")), str(info.get("data_len", 0))))
        rows.append(("CS", f"0x{info.get('cs', 0):02X}",
                     "✓ 正确" if info.get("ok") else f"✗ 应为 0x{info.get('cs_calc', 0):02X}"))
        if received and info.get("proto_type") == core.PROTO_TYPE_SPLC:
            splc_info, rest = core.split_splc_header(bytes(info.get("data", b"")))
            if splc_info is not None:
                rows.append(("帧类型", str(splc_info.get("frame_type", "")),
                             splc_info.get("frame_type_name", "")))
                if splc_info.get("sof_kind") is not None:
                    rows.append(("SOF类型", str(splc_info.get("sof_kind", "")),
                                 splc_info.get("sof_kind_name", "")))
                if splc_info.get("users") is not None:
                    rows.append(("用户数", str(splc_info.get("users", "")),
                                 f"TMI={splc_info.get('tmi')} 长度={splc_info.get('user_lens')}"))
                rows.append(("数据头长度", str(splc_info.get("header_len", "")),
                             str(splc_info.get("layout", "帧类型 1 字节"))))
                payload = rest
            else:
                payload = bytes(info.get("data", b""))
        else:
            payload = bytes(info.get("data", b""))

        if self._parser is not None and payload:
            try:
                table = self._parser.parse_to_table(payload, parse_level="auto") or []
                summary = self._summary_fn(table) if self._summary_fn else ""
                if summary:
                    note += f"  |  {summary}"
                for row in table[:40]:
                    name = str(row[0]) if len(row) > 0 else ""
                    raw = str(row[1]) if len(row) > 1 else ""
                    parsed = str(row[2]) if len(row) > 2 else ""
                    rows.append((name, raw, parsed))
                if len(table) > 40:
                    rows.append((f"…（共 {len(table)} 行）", "", "详细解析见「接收监控」页签"))
            except Exception as exc:  # noqa: BLE001 - 解析失败只降级
                rows.append(("解析异常", "", str(exc)))
        return rows, note, summary

    # ================================================================
    # 命令下发
    # ================================================================
    def _send_frame(self, frame: bytes, port: Optional[SplcSerialPort] = None,
                    label: Optional[str] = None, rows=None, note: str = "",
                    summary: str = "") -> bool:
        port = port or self._tx
        label = label or ("发射机" if port is self._tx else
                          ("接收机" if port is self._rx else "工装板"))
        if not port.is_open():
            self._log_note(f"⚠ {label}串口未打开，无法发送", level="error")
            return False
        if not port.write(frame):
            return False
        dock = self._ensure_log_dock()
        dock.log_panel.append_tx(label, frame, note, rows, summary)
        dock.append_summary(_fmt_time(), label, "TX", summary, note)
        return True

    def _send_monitor_command(self, cmd_id: int, rw: int, data: bytes = b"") -> bool:
        """发一条 68..16 监控器命令 —— **发往接收机串口**（监控器挂在那个口上）。"""
        frame = core.build_command_frame(cmd_id, rw, data)
        info = core.parse_command_frame(frame)
        if not self._rx.is_open():
            self._log_note("⚠ 接收机串口未打开，无法下发监控器命令", level="error")
            return False
        rows = [("命令", f"0x{cmd_id:02X}", info.get("cmd_name", "")),
                ("读写", str(rw), "设置" if rw else "查询")]
        rows.extend(info.get("fields") or [])
        return self._send_frame(frame, port=self._rx, label="接收机",
                                rows=rows,
                                note=f"监控器 {info.get('cmd_name', '命令')}"
                                     f"（{'设置' if rw else '查询'}）")

    def _cmd_monitor_set_band(self):
        band = int(self.monitor_band_combo.currentData() or 1)
        payload = core.command_payload_from_values(0x01, [band])
        if not payload.ok:
            self._notify("设置监控器频段", payload.error, level="error")
            return
        self._send_monitor_command(0x01, 1, payload.payload)

    def _cmd_monitor_set_snid(self):
        payload = core.command_payload_from_values(0x06, [self.monitor_snid_spin.value()])
        if not payload.ok:
            self._notify("设置SNID", payload.error, level="error")
            return
        self._send_monitor_command(0x06, 1, payload.payload)

    def _cmd_monitor_set_mode(self):
        payload = core.command_payload_from_values(0x07, [0, 4])   # 监控器模式 + 南网SPLC
        if not payload.ok:
            self._notify("设为监控器模式", payload.error, level="error")
            return
        self._send_monitor_command(0x07, 1, payload.payload)

    # ---- 发射机（PLC2.0）控制报文 ----
    def _tx_command_values(self, ctrl2: int) -> List[int]:
        """从顶栏读该指令的结构化字段值（顺序与 ``TX_COMMANDS[*].fields`` 一致）。"""
        table = {
            0x09: lambda: [int(self.band_combo.currentData() or 0)],
            0x0B: lambda: [int(self.phase_combo.currentData() or 1)],
            0x23: lambda: [int(self.phy_mode_combo.currentData() or 1)],
            0x19: lambda: [int(self.sfo_combo.currentData() or 1),
                           int(self.sync_combo.currentData() or 0)],
            0x15: lambda: [int(self.fill_crc_combo.currentData() or 1)],
            0x17: lambda: [int(self.tonemask_combo.currentData() or 0)],
            0x25: lambda: [self.rf_index_spin.value(), self.rf_option_spin.value()],
        }
        getter = table.get(int(ctrl2))
        if getter is None:
            return []
        return [int(v) for v in getter()]

    def _send_tx_command(self, ctrl2: int, tail: bytes = b"") -> bool:
        """按顶栏参数下发一条发射机控制报文（ED..EE，控制域1=0x01）。"""
        payload = core.tx_command_payload(ctrl2, self._tx_command_values(ctrl2), tail)
        if not payload.ok:
            self._notify(core.tx_command_name(ctrl2), payload.error, level="error")
            return False
        frame = core.build_tx_frame(core.CTRL1_CONTROL, ctrl2, payload.payload,
                                    cs_mode=self._cs_mode())
        rows, note = core.decode_tx_control_payload(ctrl2, payload.payload)
        head = [("控制域2", f"0x{ctrl2:02X}", core.tx_command_name(ctrl2)),
                ("数据域长度", str(len(payload.payload)), str(len(payload.payload)))]
        return self._send_frame(frame, rows=head + rows,
                                note=core.tx_command_name(ctrl2) + ("  " + note if note else ""))

    # ================================================================
    # 用例树 / 步骤表
    # ================================================================
    def _refresh_case_tree(self):
        self.case_tree.clear()
        folder = core.case_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)   # 首次运行就建好目录，用户能找到自己的用例
        except OSError:
            pass
        root = self.case_tree.invisibleRootItem()
        # 只列**已保存的用例文件**（用户口径：左侧不要出现「当前用例未保存」这类条目，
        # 步骤内容本来就在右侧表格/JSON 视图里）
        saved = QTreeWidgetItem(root, ["用例文件（双击载入）", ""])
        items = core.list_cases()
        current = str(self._case_path) if self._case_path else ""
        for entry in items:
            steps = entry["steps"]
            child = QTreeWidgetItem(saved, [str(entry["name"]), str(steps) if steps else ""])
            child.setData(0, Qt.ItemDataRole.UserRole, str(entry["path"]))
            if entry["error"]:
                child.setToolTip(1, str(entry["error"]))
                child.setForeground(0, Qt.GlobalColor.darkRed)
            else:
                child.setToolTip(0, f"{entry['path']}\n{steps} 个步骤")
            if current and str(entry["path"]) == current:
                font = child.font(0)
                font.setBold(True)
                child.setFont(0, font)
                self.case_tree.setCurrentItem(child)
        saved.setExpanded(True)
        if not folder.exists():
            tip = QTreeWidgetItem(root, [f"（用例目录尚未创建：{folder}）", ""])
            tip.setFlags(tip.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self._update_case_label()

    def _open_case_dialog(self):
        """从任意位置载入用例 JSON。"""
        folder = core.case_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        path, _ = QFileDialog.getOpenFileName(
            self, "载入收发机用例", str(folder), "用例文件 (*.json);;所有文件 (*.*)")
        if path:
            self.load_case_file(path)

    def _update_case_label(self):
        name = self._case.name or "未命名用例"
        marker = " *" if self._dirty else ""
        path = f"  ·  {self._case_path}" if self._case_path else "  ·  （未保存到文件）"
        self.case_label.setText(f"{marker}{path}" if marker else path)
        # 名称输入框跟随用例对象（用户正在输入时不要抢光标/覆盖半截输入）
        if self.case_name_edit.text() != name and not self.case_name_edit.hasFocus():
            self.case_name_edit.blockSignals(True)
            self.case_name_edit.setText(name)
            self.case_name_edit.blockSignals(False)
        self._refresh_run_target_label()

    def _on_case_name_edited(self, text: str):
        """名称输入框 → 用例对象（只标记未保存，落盘要用户点保存/另存为）。"""
        name = core.normalize_name(text)
        if name == self._case.name:
            return
        self._case.name = name
        self._mark_dirty()

    def _on_case_tree_double_clicked(self, item, _column: int = 0):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            self.load_case_file(path)

    def _on_case_tree_selection_changed(self):
        items = self.case_tree.selectedItems()
        if items:
            path = items[0].data(0, Qt.ItemDataRole.UserRole)
            self.case_tree.setToolTip(path or "")
        self._refresh_run_target_label()

    def _refresh_step_table(self):
        table = self.step_table
        table.setRowCount(len(self._case.steps))
        for row, step in enumerate(self._case.steps):
            values = [
                step.category,
                step.name,
                step.summary_type(),
                step.summary_param(),
                str(step.count) if step.kind != "wait" else "—",
                f"{step.interval_ms} ms" if step.kind != "wait" else f"{step.interval_ms} ms",
                step.port,
                step.data,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == COL_DATA:
                    item.setFont(_mono_font())
                    item.setToolTip(str(value))
                if not step.enabled:
                    item.setForeground(Qt.GlobalColor.gray)
                table.setItem(row, col, item)
            detail = step.summary_detail()
            if detail:
                for col in (COL_NAME, COL_PARAM):
                    if table.item(row, col) is not None:
                        table.item(row, col).setToolTip(detail)
        self._update_case_label()
        self._refresh_draft_tree()
        self._sync_json_view()

    def _refresh_draft_tree(self):
        """保留接口：左侧不再显示「当前用例」分支（用户口径：只列已保存的用例文件）。

        步骤内容在右侧表格视图 / JSON 视图里编辑，左侧树只负责挑文件。
        """
        return

    def _sync_json_view(self):
        """表格改动用例后，JSON 页跟着刷新（只有 JSON 页是当前页且内容无待应用改动时）。

        判定「有无待应用改动」用与当前 JSON 是否一致：不一致说明用户手改过，
        直接覆盖会把输入吃掉，所以只在一致或当前页不是 JSON 页时刷新。
        """
        try:
            if self.editor_tabs.currentIndex() < 0:
                return
            is_json_tab = self.editor_tabs.tabText(
                self.editor_tabs.currentIndex()).startswith("JSON")
        except Exception:  # noqa: BLE001 - 视图还没建好（构造期）
            return
        if not is_json_tab:
            return
        try:
            current = self.case_json_edit.toPlainText().strip()
            if current and current != self._last_json_text:
                return          # 用户改过、还没应用 → 不覆盖
        except Exception:  # noqa: BLE001
            return
        self._reload_case_json()

    def _selected_step_rows(self) -> List[int]:
        rows = sorted({index.row() for index in self.step_table.selectedIndexes()})
        return [r for r in rows if 0 <= r < len(self._case.steps)]

    # ---------------- JSON 视图（查看 / 编辑同一份用例） ----------------
    def _case_json_text(self) -> str:
        import json
        return json.dumps(self._case.to_dict(), ensure_ascii=False, indent=2)

    def _reload_case_json(self):
        """按当前用例重新生成 JSON 文本（丢弃编辑框里未应用的改动）。"""
        text = self._case_json_text()
        self.case_json_edit.setPlainText(text)
        self._last_json_text = text.strip()
        self.json_hint_label.setText("已按当前用例重新生成")
        self.json_hint_label.setStyleSheet("color: #888;")

    def _on_editor_tab_changed(self, index: int):
        """切到 JSON 页时按当前用例刷新（表格视图是数据的唯一实时镜像）。"""
        if self.editor_tabs.tabText(index).startswith("JSON"):
            if not self.case_json_edit.toPlainText().strip():
                self._reload_case_json()
            else:
                self.json_hint_label.setText("提示：改动需点「应用 JSON 到用例」才生效")
                self.json_hint_label.setStyleSheet("color: #888;")

    def _apply_case_json(self) -> bool:
        """把 JSON 编辑框的内容解析成用例（失败只提示，不动现有用例）。"""
        import json
        text = self.case_json_edit.toPlainText().strip()
        if not text:
            self.json_hint_label.setText("JSON 为空")
            self.json_hint_label.setStyleSheet("color: #c62828;")
            return False
        try:
            obj = json.loads(text)
            case = core.Case.from_dict(obj)
        except ValueError as exc:      # json 的 JSONDecodeError 也是 ValueError
            self.json_hint_label.setText(f"JSON 解析失败：{exc}")
            self.json_hint_label.setStyleSheet("color: #c62828;")
            return False
        except TypeError as exc:
            self.json_hint_label.setText(f"JSON 结构不对：{exc}")
            self.json_hint_label.setStyleSheet("color: #c62828;")
            return False
        if not core.normalize_name(case.name):
            stem = self._case_path.stem if self._case_path else ""
            case.name = stem or self._case.name or "新建用例"
        errors, warnings = core.validate_case(case)
        if errors:
            self.json_hint_label.setText("校验未通过：" + "；".join(errors[:3]))
            self.json_hint_label.setStyleSheet("color: #c62828;")
            return False
        self._case = case
        self._dirty = True
        self._refresh_step_table()
        self._refresh_case_tree()
        self._reload_case_json()
        note = f"已应用 JSON（{len(case.steps)} 个步骤）"
        if warnings:
            note += "；" + "；".join(warnings[:3])
        self.json_hint_label.setText(note)
        self.json_hint_label.setStyleSheet("color: #1B8A3A;")
        self._log_note(note, level="warn" if warnings else "info")
        return True

    def _mark_dirty(self):
        self._dirty = True
        self._update_case_label()

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self, "未保存的修改", "当前用例有未保存的修改，是否保存？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self._save_case()
        return answer == QMessageBox.StandardButton.Discard

    # ---------------- 用例文件操作 ----------------
    def _new_case(self):
        if not self._confirm_discard():
            return
        self._case = core.Case(name="新建用例")
        self._case_path = None
        self._dirty = False
        self._refresh_step_table()
        self._refresh_case_tree()
        self._log_note("已新建空白用例")

    def _duplicate_case(self) -> bool:
        """复制当前用例：深拷贝 → 自动起名「原名 副本」→ 立刻落成新文件并载入它。

        用户流程「在已有用例上复制一份、改完再另存」就靠这个入口：原用例文件不动，
        副本一落地就是独立文件，后续保存只改副本。
        """
        if not self._case.steps:
            self._notify("复制用例", "当前用例没有步骤，没什么可复制的", level="warn")
            return False
        # 不弹「未保存修改」确认框：复制的是**内存里的当前内容**（含未保存的改动），
        # 这正是「在当前编辑基础上复制一份继续改」的用法；原文件本来就不会被写。
        base = core.normalize_name(self._case.name) or "用例"
        if base.endswith(" 副本") or " 副本" in base:
            base = base.split(" 副本")[0] or "用例"
        taken = {str(entry["name"]) for entry in core.list_cases()}
        taken |= {p.stem for p in core.case_dir().glob("*.json")}
        name = f"{base} 副本"
        index = 2
        while name in taken:
            name = f"{base} 副本{index}"
            index += 1

        clone = core.Case.from_dict(self._case.to_dict())
        clone.name = name
        clone.created = ""
        clone.updated = ""
        clone.description = self._case.description
        try:
            target = core.save_case(clone, core.case_dir() / f"{core.normalize_name(name)}.json",
                                    create_only=True)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "复制用例", f"复制失败：{exc}")
            return False
        self._case = clone
        self._case_path = Path(target)
        self._dirty = False
        self._refresh_step_table()
        self._refresh_case_tree()
        self.save_settings()
        self._log_note(f"已复制为新用例「{name}」：{target}（原用例未被修改）")
        return True

    def load_case_file(self, path, quiet: bool = False) -> bool:
        if not quiet and not self._confirm_discard():
            return False
        try:
            case = core.load_case(path)
        except ValueError as exc:
            self._notify("载入用例", f"{path}\n\n{exc}", level="error")
            return False
        self._case = case
        self._case_path = Path(path)
        self._dirty = False
        self._refresh_step_table()
        self._refresh_case_tree()
        self._log_note(f"已载入用例「{case.name}」：{path}（{len(case.steps)} 个步骤）")
        if not quiet:
            self.save_settings()
        return True

    def _save_case(self) -> bool:
        if not self._case_path:
            return self._save_case_as()
        return self._save_case_to(self._case_path)

    def _save_case_as(self) -> bool:
        default_dir = core.case_dir()
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        suggested = default_dir / f"{core.normalize_name(self._case.name) or '新建用例'}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "另存用例", str(suggested), "用例文件 (*.json);;所有文件 (*.*)")
        if not path:
            return False
        return self._save_case_to(path)

    def _save_case_to(self, path) -> bool:
        # 名称与文件名对齐：另存为 bitloading1.json 时必须把 JSON 里的 name 也改成
        # bitloading1，否则下次载入会显示上一条用例的名字（现场报障：加载
        # bitloading1.json，顶栏却仍是「回传模式用例」）。
        # 规则：名称空/「新建用例」→ 跟随文件；另存到**新文件**时也跟随文件；
        # 只有「保存到原文件」且用户已手动改名时，才保留用户输入的名称。
        stem = Path(path).stem.strip()
        target_is_same_file = bool(self._case_path) and Path(path) == Path(self._case_path)
        name = core.normalize_name(self._case.name)
        if stem and (not name or name == "新建用例" or not target_is_same_file):
            if name != stem:
                self._log_note(f"用例名称跟随文件名：{name or '（空）'} → {stem}")
            self._case.name = stem
        errors, warnings = core.validate_case(self._case)
        if errors:
            QMessageBox.warning(self, "无法保存用例", "\n".join(errors[:12]))
            return False
        if warnings:
            self._log_note("；".join(warnings), level="warn")
        try:
            target = core.save_case(self._case, path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "保存用例", str(exc))
            return False
        self._case_path = Path(target)
        self._dirty = False
        self._update_case_label()
        self._refresh_case_tree()
        self._log_note(f"用例已保存：{target}")
        self.save_settings()
        return True

    def _delete_case(self):
        items = self.case_tree.selectedItems()
        path = None
        for item in items:
            candidate = item.data(0, Qt.ItemDataRole.UserRole)
            if candidate:
                path = candidate
                break
        if not path:
            current = self._case_path
            path = str(current) if current else ""
        if not path:
            QMessageBox.information(self, "删除用例", "请先在左侧选中一个用例文件。")
            return
        answer = QMessageBox.question(
            self, "删除用例", f"确定删除用例文件？\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            core.delete_case(path)
        except OSError as exc:
            QMessageBox.warning(self, "删除用例", f"删除失败：{exc}")
            return
        if self._case_path and Path(path) == self._case_path:
            self._case_path = None
            self._dirty = True
        self._refresh_case_tree()
        self._log_note(f"已删除用例文件：{path}")

    # ---------------- 步骤编辑 ----------------
    def _dialog_defaults(self) -> Dict[str, object]:
        return {
            "count": self.count_spin.value(),
            "interval_ms": self.interval_spin.value(),
        }

    def _add_step(self):
        dialog = StepDialog(self, defaults=self._dialog_defaults())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        step = dialog.step()
        if not step.count:
            step.count = self.count_spin.value()
        if not step.interval_ms:
            step.interval_ms = self.interval_spin.value()
        self._case.steps.append(step)
        self._mark_dirty()
        self._refresh_step_table()
        self.step_table.selectRow(len(self._case.steps) - 1)

    def _edit_step(self):
        rows = self._selected_step_rows()
        if not rows:
            QMessageBox.information(self, "编辑步骤", "请先在表格里选中一行。")
            return
        row = rows[0]
        dialog = StepDialog(self, step=self._case.steps[row],
                            defaults=self._dialog_defaults())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._case.steps[row] = dialog.step()
        self._mark_dirty()
        self._refresh_step_table()
        self.step_table.selectRow(row)

    def _copy_step(self):
        rows = self._selected_step_rows()
        if not rows:
            return
        for row in rows:
            clone = core.Step.from_dict(self._case.steps[row].to_dict())
            clone.name = (clone.name + " 副本").strip()
            self._case.steps.insert(row + 1, clone)
        self._mark_dirty()
        self._refresh_step_table()

    def _delete_steps(self):
        rows = self._selected_step_rows()
        if not rows:
            return
        for row in reversed(rows):
            del self._case.steps[row]
        self._mark_dirty()
        self._refresh_step_table()

    def _move_step(self, delta: int):
        rows = self._selected_step_rows()
        if len(rows) != 1:
            QMessageBox.information(self, "移动步骤", "请只选中一行。")
            return
        row = rows[0]
        target = row + delta
        if not 0 <= target < len(self._case.steps):
            return
        steps = self._case.steps
        steps[row], steps[target] = steps[target], steps[row]
        self._mark_dirty()
        self._refresh_step_table()
        self.step_table.selectRow(target)

    def _append_generated_frame(self):
        dialog = FrameGenDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text = dialog.frame_hex()
        if not text:
            return
        step = core.Step(
            kind="data",
            category="发送",
            name="生成的测试帧",
            type="组帧面板",
            param="",
            count=self.count_spin.value(),
            interval_ms=self.interval_spin.value(),
            port="HPLC",
            data=text,
        )
        self._case.steps.append(step)
        self._mark_dirty()
        self._refresh_step_table()
        self.step_table.selectRow(len(self._case.steps) - 1)

    # ================================================================
    # 快捷发送
    # ================================================================
    def _send_quick(self):
        """快速发送：整帧原样发；裸业务帧按顶栏默认参数包成 ED..EE。"""
        text = self.quick_hex_edit.text().strip()
        if not text:
            return
        try:
            raw = core.hex_to_bytes(text)
        except ValueError as exc:
            self._notify("快速发送", str(exc), level="error")
            return
        if not raw:
            return
        if raw[:1] == bytes([core.TX_HEAD]) and raw[-1:] == bytes([core.TX_TAIL]):
            self._send_frame(raw, note="快速发送（原始 ED..EE 帧）")
            return
        if raw[:1] == bytes([core.FRAME_HEAD_CMD]) and raw[-1:] == bytes([core.FRAME_TAIL]):
            self._send_monitor_command_raw(raw, note="快速发送（原始 68..16 命令帧）")
            return
        if raw[:1] == bytes([core.FRAME_HEAD_DATA]):
            self._send_frame(raw, note="快速发送（原始 96..16 监控帧）")
            return
        # 裸业务帧 → 按顶栏默认参数封 ED..EE（FC+Payload / HPLC / 立即发送）
        try:
            frame = core.build_tx_frame(
                core.CTRL1_DATA, 0x02,
                core.build_tx_data_payload(0x02, payload=raw, channel=0x01),
                cs_mode=self._cs_mode())
        except ValueError as exc:
            self._notify("快速发送", str(exc), level="error")
            return
        self._send_frame(frame, note="快速发送（业务帧，已封装 ED..EE）",
                         summary=self._business_summary(raw))

    def _send_monitor_command_raw(self, frame: bytes, note: str = "") -> bool:
        """把一条 68..16 命令帧原样发到**接收机**串口（监控器挂在那个口上）。"""
        if not self._rx.is_open():
            self._log_note("⚠ 接收机串口未打开，无法下发监控器命令", level="error")
            return False
        return self._send_frame(frame, port=self._rx, label="接收机", note=note)

    def _send_selected_step_once(self):
        """把表格里**选中的所有步骤**按表格顺序各发一次（多选必须真的生效）。"""
        rows = self._selected_step_rows()
        if not rows:
            QMessageBox.information(self, "发送选中步骤", "请先在表格里选中一行（可按住 Ctrl/Shift 多选）。")
            return
        failed: List[str] = []
        sent = 0
        for row in rows:
            step = self._case.steps[row]
            if self._dispatch_step(step, 1, 1, quiet=True):
                sent += 1
            else:
                failed.append(f"第 {row + 1} 步「{step.name or step.kind}」")
        if len(rows) > 1:
            self._log_note(f"已发送选中步骤 {sent}/{len(rows)} 个")
        if failed:
            QMessageBox.warning(
                self, "发送选中步骤",
                f"以下 {len(failed)} 个步骤没有发送成功：\n" + "\n".join(failed[:10]))

    # ================================================================
    # 流程执行
    # ================================================================
    def _build_config_actions(self) -> List[core.Action]:
        """「启动前先下发配置」：按顶栏参数发 4 条 PLC2.0 控制报文。"""
        steps = [
            core.Step(kind="command", category="配置", name="频段模式配置",
                      command=core.tx_command_ref(0x09),
                      tx_values=self._tx_command_values(0x09),
                      count=1, interval_ms=120),
            core.Step(kind="command", category="配置", name="设置通讯相线",
                      command=core.tx_command_ref(0x0B),
                      tx_values=self._tx_command_values(0x0B),
                      count=1, interval_ms=120),
            core.Step(kind="command", category="配置", name="进入特定物理信道",
                      command=core.tx_command_ref(0x23),
                      tx_values=self._tx_command_values(0x23),
                      count=1, interval_ms=120),
            core.Step(kind="command", category="配置", name="设置同步时钟与补偿频偏",
                      command=core.tx_command_ref(0x19),
                      tx_values=self._tx_command_values(0x19),
                      count=1, interval_ms=120),
        ]
        actions: List[core.Action] = []
        for step in steps:
            built = core.build_step_tx_command(step, cs_mode=self._cs_mode())
            action = core.Action(0, step, 1, 1, "send_tx_cmd",
                                 built.payload if built.ok else b"", step.interval_ms)
            if not built.ok:
                action.error = built.error
            actions.append(action)
        return actions

    def _selected_case_paths(self) -> List[Path]:
        """左侧列表里选中的用例文件（按树里的顺序；去掉重复）。"""
        out: List[Path] = []
        seen: set = set()
        try:
            items = self.case_tree.selectedItems()
        except RuntimeError:
            return out
        for item in items:
            raw = item.data(0, Qt.ItemDataRole.UserRole)
            if not raw:
                continue
            path = Path(str(raw))
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
        return out

    def _run_targets(self) -> List[core.Case]:
        """本次「启动条目测试」要跑的用例，按顺序返回。

        用户口径：**左侧用例条目支持多选，整个用例条目也能启动/停止** ——
        选中多条时按列表顺序依次执行它们的全部步骤；没选（或选的是当前用例）时
        就跑表格里这条（含未保存的改动）。
        """
        paths = self._selected_case_paths()
        if not paths:
            return [self._case] if self._case.steps else []
        current = str(self._case_path) if self._case_path else ""
        cases: List[core.Case] = []
        for path in paths:
            if current and str(path) == current:
                cases.append(self._case)      # 载入中的那条用内存里的（含未保存改动）
                continue
            try:
                cases.append(core.load_case(path))
            except ValueError as exc:
                self._log_note(f"⚠ 跳过用例 {path.name}：{exc}", level="error")
        return cases

    def _refresh_run_target_label(self) -> None:
        """运行行右侧提示：这次「启动」会跑哪条/哪几条用例。"""
        if not hasattr(self, "run_target_label"):
            return
        paths = self._selected_case_paths()
        if not paths:
            self.run_target_label.setText(
                f"将执行当前用例：{self._case.name}（{len(self._case.steps)} 步）")
        elif len(paths) == 1:
            self.run_target_label.setText(f"将执行：{paths[0].stem}")
        else:
            names = "、".join(p.stem for p in paths[:4])
            more = "" if len(paths) <= 4 else f" 等 {len(paths)} 条"
            self.run_target_label.setText(f"将依次执行 {len(paths)} 条用例：{names}{more}")

    def _start_run(self):
        if self._runner is not None:
            self._notify("启动条目测试", "流程正在执行，请先停止。")
            return
        targets = self._run_targets()
        if not targets or not any(case.steps for case in targets):
            self._notify("启动条目测试", "没有可执行的用例/步骤（左侧选中的用例为空？）")
            return
        if not self._tx.is_open():
            self._notify("启动条目测试", "发射机串口还没打开（见页面顶部「打开发射机」）。",
                         level="error")
            return

        actions: List[core.Action] = []
        for case in targets:
            errors, warnings = core.validate_case(case)
            if errors:
                self._notify(f"用例不合法：{case.name}", "；".join(errors[:12]), level="error")
                return
            for warning in warnings:
                self._log_note(f"{case.name}：{warning}", level="warn")
            case_actions, plan_errors = core.plan_actions(
                case,
                default_count=self.count_spin.value(),
                default_interval_ms=self.interval_spin.value(),
                cs_mode=self._cs_mode())
            for item in plan_errors:
                self._log_note(f"{case.name}：{item}", level="error")
            actions.extend(case_actions)
        if not actions:
            self._notify("启动条目测试", "没有可执行的步骤（可能都被禁用）。")
            return
        if len(targets) > 1:
            self._log_note("执行用例：" + "、".join(c.name for c in targets))

        if self.auto_config_chk.isChecked():
            actions = self._build_config_actions() + actions

        self._ensure_log_dock()
        self._runner = _Runner(actions, self.duration_spin.value() * 60)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        scope = (f"{len(targets)} 条用例" if len(targets) > 1
                 else f"用例「{targets[0].name}」")
        self._log_note(
            f"▶ 开始执行{scope}：{len(actions)} 个动作，"
            f"持续时间 {'不限' if not self._runner.deadline else str(self.duration_spin.value()) + ' 分钟'}")
        self._update_progress()
        self._run_timer.start(0)

    def stop_run(self, reason: str = "已停止"):
        if self._runner is None:
            return
        self._run_timer.stop()
        self._runner.stopped = True
        runner = self._runner
        self._runner = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._log_note(f"■ 流程结束（{reason}）：成功 {runner.sent_ok}，失败 {runner.failed}，"
                       f"共 {runner.total} 个动作")
        self._update_progress()

    def _update_progress(self):
        runner = self._runner
        if runner is None:
            self.progress_label.setText("")
            return
        self.progress_label.setText(
            f"执行中 {runner.index}/{runner.total} · 成功 {runner.sent_ok} · 失败 {runner.failed}")

    def _run_next(self):
        runner = self._runner
        if runner is None:
            return
        if runner.deadline and time.monotonic() >= runner.deadline:
            self.stop_run("达到设定持续时间")
            return
        if runner.index >= runner.total:
            self.stop_run("流程执行完成")
            return

        action = runner.actions[runner.index]
        runner.index += 1
        if action.error:
            runner.failed += 1
            self._log_note(f"⚠ 第 {action.step_index} 步跳过：{action.error}", level="error")
        else:
            self._dispatch_action(action)
        self._update_progress()
        delay = max(0, int(action.delay_ms))
        self._run_timer.start(delay)

    def _dispatch_action(self, action: core.Action) -> bool:
        step = action.step
        label = f"第{action.step_index}步·{action.repeat}/{action.repeat_total}"
        try:
            if action.action == "send_tx_cmd":
                info = core.parse_tx_frame(action.payload)
                rows = [("控制域2", f"0x{info.get('ctrl2', 0):02X}",
                         str(info.get("ctrl2_name", "")))]
                payload_rows, _note = core.decode_tx_control_payload(
                    int(info.get("ctrl2") or 0), bytes(info.get("data") or b""))
                rows.extend(payload_rows)
                ok = self._send_frame(
                    action.payload, rows=rows,
                    note=f"{label} {info.get('ctrl2_name', '控制报文')}")
            elif action.action == "send_monitor":
                info = core.parse_command_frame(action.payload)
                rows = [("命令", f"0x{info.get('cmd_id', 0):02X}", info.get("cmd_name", ""))]
                rows.extend(info.get("fields") or [])
                ok = self._send_frame(action.payload, port=self._rx, label="接收机",
                                      rows=rows,
                                      note=f"{label} 监控器 {info.get('cmd_name', '命令')}")
            elif action.action == "send_raw":
                if step.port == "工装板":
                    ok = self._send_frame(action.payload, port=self._fixture,
                                          note=f"{label} 透传")
                elif step.port == "接收机":
                    ok = self._send_frame(action.payload, port=self._rx,
                                          label="接收机", note=f"{label} 透传")
                else:
                    ok = self._send_frame(action.payload, note=f"{label} 透传")
            elif action.action == "wait":
                self._log_note(f"… 等待 {action.delay_ms} ms（{label}）")
                return True
            else:
                info = core.parse_tx_frame(action.payload)
                rows = [("控制域1", f"0x{info.get('ctrl1', 0):02X}",
                         str(info.get("ctrl1_name", ""))),
                        ("控制域2", f"0x{info.get('ctrl2', 0):02X}",
                         str(info.get("ctrl2_name", ""))),
                        ("帧长域", str(info.get("frame_len", "")),
                         str(info.get("frame_len", 0))),
                        ("数据域长度", str(info.get("data_len", "")),
                         str(info.get("data_len", 0)))]
                summary = ""
                if info.get("ctrl1") == core.CTRL1_DATA:
                    data_bytes = bytes(info.get("data") or b"")
                    ctrl2 = int(info.get("ctrl2") or 0)
                    payload_rows, _note = core.decode_tx_data_payload(ctrl2, data_bytes)
                    rows.extend(payload_rows)
                    business = core.tx_business_payload(ctrl2, data_bytes)
                    if business is not None:
                        biz_rows, summary = self._business_rows_and_summary(business)
                        rows.extend(biz_rows)
                ok = self._send_frame(
                    action.payload, rows=rows,
                    note=f"{label} {step.name or step.summary_type()}",
                    summary=summary)
        except Exception as exc:  # noqa: BLE001 - 单步异常不中断整条流程
            self._log_note(f"⚠ {label} 发送异常：{exc}", level="error")
            ok = False
        if self._runner is not None:
            if ok:
                self._runner.sent_ok += 1
            else:
                self._runner.failed += 1
        return ok

    def _dispatch_step(self, step: core.Step, repeat: int, total: int,
                       quiet: bool = False) -> bool:
        """发一个步骤（``quiet=True`` 时失败只记日志、不弹框 —— 批量发送时统一汇总）。"""
        actions, errors = core.plan_actions(
            core.Case(name="_one", steps=[step]), default_count=1,
            default_interval_ms=self.interval_spin.value(),
            cs_mode=self._cs_mode())
        if errors or not actions:
            message = "；".join(errors) or "该步骤没有可发送内容"
            self._log_note(f"⚠ {message}", level="error")
            if not quiet:
                QMessageBox.warning(self, "发送步骤", message)
            return False
        action = actions[0]
        action.repeat, action.repeat_total = repeat, total
        return self._dispatch_action(action)

    # ================================================================
    # 生命周期
    # ================================================================
    def showEvent(self, event):
        """每次显示：重算参数区高度、刷新串口列表；首次显示再恢复上次用例。

        - 串口是 USB 转串口，用户常「先开程序、后插设备」⇒ 每次显示都刷新列表；
        - 参数区高度必须在这里补算一次：切到本页时控件才真正可见（见 FlowArea 说明）；
        - 自动恢复上次用例只在第一次显示、且当前没有未保存内容时做一次。
        """
        super().showEvent(event)
        self._update_config_height()
        self._refresh_port_lists()
        if getattr(self, "_restored_last_case", False):
            return
        self._restored_last_case = True
        last = str(self._settings.get("last_case", "") or "")
        if not last or self._dirty or self._case.steps:
            return
        if Path(last).exists():
            self.load_case_file(last, quiet=True)

    def shutdown(self):
        """关闭页面前回收串口线程与定时器（可重复调用）。"""
        try:
            self._run_timer.stop()
        except RuntimeError:
            pass
        self._runner = None
        self.save_settings()
        for worker in (self._tx, self._rx, self._fixture):
            try:
                worker.close_port()
            except Exception:  # noqa: BLE001 - 回收失败不阻断退出
                pass
        dock = self._log_dock
        self._log_dock = None
        if dock is not None:
            try:
                dock.monitor.set_serial_worker(None)
            except Exception:  # noqa: BLE001
                pass
            try:
                dock.close()
                dock.deleteLater()
            except Exception:  # noqa: BLE001
                pass

    # ================================================================
    # 提示
    # ================================================================
    def _notify(self, title: str, text: str, level: str = "info"):
        """统一提示：**总是写日志**，弹框只在页面可见时弹。

        页面不可见时（例如自动化测试、或用户停在别的页签）弹模态框会卡住调用方，
        而这条信息在日志窗里照样能查到。
        """
        self._log_note(text, level=level)
        if not self.isVisible():
            return
        if level == "error":
            QMessageBox.warning(self, title, text)
        else:
            QMessageBox.information(self, title, text)
