# -*- coding: utf-8 -*-
"""batch_source_view.py — 批量解析「原始日志快照」查看器 + 帧定位纯逻辑

任务 09-10-batch-snapshot-locate：批量输入日志经回填式预处理（hex_clean
脚本 / CLI 预处理会覆写输入框）后原文丢失，摘要表帧无法回看原始位置。
main_gui 在拖入/打开/粘贴时建立不可变快照，右键摘要表帧弹出本查看器：
Notepad++ 式只读窗口（行号边栏、等宽、NoWrap、黄底定位+滚动居中、
内嵌 Ctrl+F 查找条），展示与定位永远基于快照，与输入框当前内容无关。

文件分两层（.trellis/spec/frontend/component-guidelines.md 套路）：
  前半纯逻辑不依赖 Qt（可无 GUI 脚本测试）；后半 UI 层 Qt import。
"""

import re

# ============================ 纯逻辑层 ============================

_HEX_STRIP_RE = re.compile(r"[^0-9A-Fa-f]")


def normalize_hex(text: str) -> str:
    """去除非 hex 字符并大写化（帧与快照行共用同一归一化）。"""
    return _HEX_STRIP_RE.sub("", text).upper()


# 行首时间戳（含毫秒）与时间戳间夹的非 hex 日志标签 —— 移植自
# scripts/hex_clean.py：跨行帧的每条续行都带独立时间戳，若整文件直接
# 归一化，时间戳数字会插进帧体中间打断连续性，必须逐行先剥。
_TS_RE = re.compile(
    r'^\s*\[?'
    r'(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T])?'
    r'\d{1,2}:\d{2}:\d{2}'
    r'(?:[\s:.,]\d{3})?'
    r'\]?:?\s*'
)
_NONHEX_PREFIX_RE = re.compile(r'^[^0-9a-fA-F]+')
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


def _strip_leading_ts(line: str) -> str:
    """剥离行首的一个或多个时间戳（时间戳之间允许夹日志标签文本）。"""
    stripped = _NONHEX_PREFIX_RE.sub("", line)
    if stripped != line and _TS_RE.match(stripped):
        line = stripped
    while True:
        m = _TS_RE.match(line)
        if not m:
            break
        line = line[m.end():]
        line = _NONHEX_PREFIX_RE.sub("", line)
    return line


def hex_stream(text: str):
    """把多行文本归一化为连续 hex 字符流，并保留每个字符的源行号。

    每行先剥行首时间戳/标签再取 hex 字符（监控日志逐行时间戳不污染帧体），
    行间直接拼接 —— 单行帧与跨行帧体在流中都是连续子串，一次 find 统一覆盖。

    Returns:
        (stream, line_of): stream 为大写 hex 字符串；line_of 是等长 list，
        line_of[i] = stream[i] 所在行（0-based）。
    """
    chars = []
    line_of = []
    app_c = chars.append
    app_l = line_of.append
    for ln_no, raw in enumerate(text.split("\n")):
        for ch in _strip_leading_ts(raw):
            if ch in _HEX_CHARS:
                app_c(ch.upper())
                app_l(ln_no)
    return "".join(chars), line_of


def find_frame_in_stream(stream: str, line_of: list, frame_hex: str):
    """在归一化流中非重叠查找帧 hex 的所有出现。

    Args:
        stream/line_of: hex_stream() 产物
        frame_hex: 帧 hex（可含空格/大小写混排，内部归一化）

    Returns:
        [(起行, 止行), ...]（0-based，升序，不重叠）。少于 2 字节的
        frame_hex 视为无意义，返回 []。
    """
    needle = normalize_hex(frame_hex)
    if len(needle) < 4:
        return []
    hits = []
    pos = stream.find(needle)
    while pos != -1:
        end = pos + len(needle) - 1
        hits.append((line_of[pos], line_of[end]))
        pos = stream.find(needle, pos + len(needle))  # 非重叠，与提取顺序一致
    return hits


def find_frame_in_text(text: str, frame_hex: str):
    """find_frame_in_stream 的一次性包装（纯函数测试入口）。"""
    stream, line_of = hex_stream(text)
    return find_frame_in_stream(stream, line_of, frame_hex)


# ============================ UI 层 ============================

try:
    from PySide6.QtCore import Qt, QRect, QSize
    from PySide6.QtGui import (
        QColor,
        QFont,
        QPainter,
        QPen,
        QTextCharFormat,
        QTextCursor,
    )
    from PySide6.QtWidgets import (
        QCheckBox,
        QDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QPlainTextEdit,
        QTextEdit,  # ExtraSelection 载体（QPlainTextEdit 不直接暴露该类）
        QVBoxLayout,
        QWidget,
    )

    _QT_AVAILABLE = True
except ImportError:  # 无 Qt 环境仍可导入纯逻辑层
    _QT_AVAILABLE = False


if _QT_AVAILABLE:

    class _LineNumberArea(QWidget):
        """QPlainTextEdit 行号边栏（Qt 官方 recipe）。"""

        def __init__(self, editor):
            super().__init__(editor)
            self._editor = editor

        def sizeHint(self):
            return QSize(self._editor.line_number_area_width(), 0)

        def paintEvent(self, event):
            self._editor.line_number_area_paint_event(event)

    class SourceLogView(QPlainTextEdit):
        """只读 + 行号的日志视图（等宽、NoWrap）。"""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setReadOnly(True)
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            font = QFont("Consolas")
            font.setStyleHint(QFont.StyleHint.Monospace)
            font.setPointSize(10)
            self.setFont(font)
            self._fold_width = 0

            self._ln_area = _LineNumberArea(self)
            self.blockCountChanged.connect(self._update_ln_width)
            self.updateRequest.connect(self._update_ln_area)
            self._update_ln_width(0)

        def line_number_area_width(self):
            digits = max(3, len(str(self.blockCount())))
            return 14 + self.fontMetrics().horizontalAdvance("9") * digits

        def _update_ln_width(self, _count):
            self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

        def _update_ln_area(self, rect, dy):
            if dy:
                self._ln_area.scroll(0, dy)
            else:
                self._ln_area.update(
                    0, rect.y(), self._ln_area.width(), rect.height()
                )
            if rect.contains(self.viewport().rect()):
                self._update_ln_width(0)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            cr = self.contentsRect()
            self._ln_area.setGeometry(
                QRect(
                    cr.left(), cr.top(), self.line_number_area_width(), cr.height()
                )
            )

        def line_number_area_paint_event(self, event):
            painter = QPainter(self._ln_area)
            painter.fillRect(event.rect(), QColor("#F2F2F2"))
            painter.setPen(QPen(QColor("#888888")))
            block = self.firstVisibleBlock()
            block_no = block.blockNumber()
            top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
            bottom = top + round(self.blockBoundingRect(block).height())
            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    painter.drawText(
                        0, top, self._ln_area.width() - 6,
                        self.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight,
                        str(block_no + 1),
                    )
                block = block.next()
                top = bottom
                bottom = top + round(self.blockBoundingRect(block).height())
                block_no += 1
            painter.end()

    _FRAME_BG = QColor(255, 235, 59, 160)  # 帧定位黄底（同 _highlight_bytes 色系）
    _HIT_BG = QColor(255, 165, 0, 110)  # 搜索命中橙底
    _CUR_BG = QColor(220, 60, 40, 150)  # 当前命中红底

    class SourceViewerDialog(QDialog):
        """Notepad++ 式原始日志查看器：只读、行号、黄底定位、Ctrl+F 搜索。

        用法（main_gui 接线）::

            dlg = SourceViewerDialog(parent=win)
            dlg.set_source(snapshot_text, "xxx.log")
            dlg.show_frame((3, 3), frame_no=5)   # 0-based 行范围
            dlg.show()
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("原始日志快照")
            self.setModal(False)
            self.resize(1000, 640)
            self._source_text = None
            self._frame_sel = None
            self._search_sels = []
            self._hits = []  # [(start,end)] 文档偏移
            self._hit_idx = -1

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # ── 查找条（默认隐藏，Ctrl+F 唤起） ──
            self.find_bar = QWidget(self)
            fb = QHBoxLayout(self.find_bar)
            fb.setContentsMargins(8, 4, 8, 4)
            fb.setSpacing(6)
            fb.addWidget(QLabel("查找:", self.find_bar))
            self.find_edit = QLineEdit(self.find_bar)
            self.find_edit.setPlaceholderText("输入关键字  Enter=下一个  Esc=关闭")
            self.find_edit.textChanged.connect(self._reset_search)
            self.find_edit.returnPressed.connect(self.find_next)
            fb.addWidget(self.find_edit, 1)
            self.btn_prev = QPushButton("上一个", self.find_bar)
            self.btn_prev.clicked.connect(self.find_prev)
            fb.addWidget(self.btn_prev)
            self.btn_next = QPushButton("下一个", self.find_bar)
            self.btn_next.clicked.connect(self.find_next)
            fb.addWidget(self.btn_next)
            self.cb_case = QCheckBox("区分大小写", self.find_bar)
            self.cb_case.stateChanged.connect(self._reset_search)
            fb.addWidget(self.cb_case)
            self.find_count = QLabel("", self.find_bar)
            fb.addWidget(self.find_count)
            self.find_bar.setVisible(False)
            layout.addWidget(self.find_bar)

            # ── 日志视图 ──
            self.view = SourceLogView(self)
            layout.addWidget(self.view, 1)

            # ── 状态行 ──
            self.status_label = QLabel("", self)
            self.status_label.setStyleSheet(
                "background:#FAFAFA; border-top:1px solid #DDD; padding:3px 8px;"
            )
            layout.addWidget(self.status_label)

        # ---------- 内容装载 ----------

        def set_source(self, text: str, name: str = ""):
            """装载快照全文；同一文本对象复用时跳过重灌（右键重复点击 O(1)）。"""
            if text is self._source_text:
                return
            self._source_text = text
            self.view.setPlainText(text)
            self._hits = []
            self._hit_idx = -1
            self._search_sels = []
            self.find_count.setText("")
            title = "原始日志快照"
            if name:
                title += f" — {name}"
            self.setWindowTitle(title)

        # ---------- 帧定位 ----------

        def show_frame(self, hit, frame_no: int):
            """黄底高亮第 hit[0]..hit[1] 行（0-based）并滚动居中；hit=None 仅提示。"""
            if hit is None:
                self._frame_sel = None
                self._apply_extras()
                self.status_label.setText(
                    f"帧 #{frame_no}：未能在原始日志中定位到该报文（可能被脚本改写/合成）"
                )
                return
            s_line, e_line = hit
            doc = self.view.document()
            cur = QTextCursor(doc.findBlockByNumber(s_line))
            end_block = doc.findBlockByNumber(e_line)
            cur.setPosition(end_block.position() + end_block.length() - 1,
                            QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(_FRAME_BG)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cur
            sel.format = fmt
            self._frame_sel = sel
            self._apply_extras()
            # 滚动：先置光标到帧头再居中（帧可能比视口高时也能看到开头）
            top_cur = QTextCursor(doc.findBlockByNumber(s_line))
            self.view.setTextCursor(top_cur)
            self.view.centerCursor()
            rng = (
                f"第 {s_line + 1} 行"
                if s_line == e_line
                else f"第 {s_line + 1}–{e_line + 1} 行"
            )
            self.status_label.setText(
                f"帧 #{frame_no} 已定位到原始日志 {rng}   （Ctrl+F 搜索原文，黄底为本帧）"
            )

        # ---------- 搜索 ----------

        def toggle_find_bar(self, visible: bool):
            self.find_bar.setVisible(visible)
            if visible:
                self.find_edit.setFocus()
                self.find_edit.selectAll()
            else:
                self._clear_search()
                self.view.setFocus()

        def _clear_search(self):
            self._search_sels = []
            self._hits = []
            self._hit_idx = -1
            self.find_count.setText("")
            self._apply_extras()

        def _reset_search(self, *_a):
            """输入/大小写变化：作废当前命中集，下次 find_next 重新收集。"""
            self._hits = []
            self._hit_idx = -1
            self._search_sels = []
            self.find_count.setText("")

        def _collect_hits(self):
            needle = self.find_edit.text()
            if not needle:
                return False
            hay = self.view.toPlainText()
            case = self.cb_case.isChecked()
            if case:
                h, n = hay, needle
            else:
                h, n = hay.lower(), needle.lower()
            self._hits = []
            pos = h.find(n)
            while pos != -1:
                self._hits.append((pos, pos + len(n)))
                pos = h.find(n, pos + len(n))
            self._hit_idx = -1
            return bool(self._hits)

        def _jump(self, delta: int):
            if not self._hits and not self._collect_hits():
                self.find_count.setText("无匹配" if self.find_edit.text() else "")
                return
            self._hit_idx = (self._hit_idx + delta) % len(self._hits)
            start, end = self._hits[self._hit_idx]
            doc = self.view.document()
            sels = []
            for i, (s, e) in enumerate(self._hits):
                c = QTextCursor(doc)
                c.setPosition(s)
                c.setPosition(e, QTextCursor.MoveMode.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setBackground(_CUR_BG if i == self._hit_idx else _HIT_BG)
                sel = QTextEdit.ExtraSelection()
                sel.cursor = c
                sel.format = fmt
                sels.append(sel)
            self._search_sels = sels
            self._apply_extras()
            cur = QTextCursor(doc)
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            self.view.setTextCursor(cur)
            self.view.centerCursor()
            self.find_count.setText(f"{self._hit_idx + 1}/{len(self._hits)}")

        def find_next(self):
            self._jump(1)

        def find_prev(self):
            self._jump(-1)

        # ---------- extraSelections 合并 ----------

        def _apply_extras(self):
            extras = []
            if self._frame_sel is not None:
                extras.append(self._frame_sel)
            extras.extend(self._search_sels)
            self.view.setExtraSelections(extras)

        # ---------- 按键 ----------

        def keyPressEvent(self, event):
            if (
                event.modifiers() & Qt.ControlModifier
                and event.key() == Qt.Key.Key_F
            ):
                self.toggle_find_bar(True)
                return
            if event.key() == Qt.Key.Key_Escape and self.find_bar.isVisible():
                self.toggle_find_bar(False)
                return
            super().keyPressEvent(event)
