# -*- coding: utf-8 -*-
"""Wireshark 风格字节视图组件。

每行 16 字节，格式为::

    00000000  68 0E 00 00 00 00 01 00  01 E8 00 05 EF 16 00 00  |h...........o...|

用途：TCP 监控的「原始报文」与「解析结果」两个 Tab 展示载荷/帧字节，
并支持按字段的字节范围高亮（与主窗口 ``MainWindow._apply_byte_highlight``
同色同字体，见 ``main_gui.py`` 的高亮实现）。

为什么单独成组件（而不是继续用裸 ``QTextEdit`` 贴 hex 文本）：
  1. 需要**偏移列 + ASCII 列**，Wireshark 用户一眼能定位字节；
  2. 需要**按字节下标高亮**，而高亮位置依赖行内布局，必须由组件自己算
     （裸 ``QTextEdit`` 只能按「每字节 3 字符」线性映射，有偏移列就错位）；
  3. 主窗口单帧界面后续也可迁移到本组件，避免第二份 hex 渲染实现。

字节下标 ↔ 文档字符位置（供测试锚定）：
  每行长度固定 77 字符 + 1 换行 = 78；
  行内布局 = 偏移(8) + 2 空格 + 16×3 hex + 1 空格 + '|' + 16 ASCII + '|'，
  故第 ``i`` 字节的两个 hex 字符位于 ``(i//16)*78 + 10 + (i%16)*3``。
"""

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

import canvas_theme

# 每行字节数（Wireshark 默认 16）
BYTES_PER_ROW = 16
# 行内固定前缀：8 位偏移 + 2 空格
_PREFIX_LEN = 10
# hex 区长度：16 字节 × 3 字符（"XX "）
_HEX_AREA_LEN = BYTES_PER_ROW * 3
# 整行长度（不含换行）
ROW_LEN = _PREFIX_LEN + _HEX_AREA_LEN + 1 + 1 + BYTES_PER_ROW + 1  # = 77
# 含换行的步长
ROW_STRIDE = ROW_LEN + 1  # = 78

# 高亮底色与主窗口 _apply_byte_highlight 保持一致（黄底半透明）
HIGHLIGHT_COLOR = QColor(255, 235, 59, 160)
# 默认前景/背景（清除高亮时恢复；浅色主题的取值，深色走 canvas_theme.palette(True)）
DEFAULT_FG = QColor("#000000")
DEFAULT_BG = QColor("#FFFFFF")


def build_dump_text(data: bytes) -> str:
    """把字节渲染成 hex dump 文本（纯函数，便于单测）。"""
    if not data:
        return ""
    lines = []
    for offset in range(0, len(data), BYTES_PER_ROW):
        row = data[offset:offset + BYTES_PER_ROW]
        hex_part = "".join(f"{b:02X} " for b in row).ljust(_HEX_AREA_LEN)
        ascii_part = "".join(
            chr(b) if 0x20 <= b <= 0x7E else "." for b in row
        ).ljust(BYTES_PER_ROW)
        lines.append(f"{offset:08X}  {hex_part} |{ascii_part}|")
    return "\n".join(lines)


class HexDumpView(QTextEdit):
    """只读字节视图：偏移 + 16 进制 + ASCII，支持按字节范围高亮。

    前后景**必须自己跟着主题**：字符格式里显式设过背景色，会盖掉 QSS 给 QTextEdit
    的底色（深色主题下不清掉就是整块白底）。
    """

    def __init__(self, parent=None, max_height: int | None = None):
        super().__init__(parent)
        self._byte_length = 0
        self._dark = False
        self._fg = QColor(DEFAULT_FG)
        self._bg = QColor(DEFAULT_BG)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(9)
        self.setFont(font)
        self.setPlaceholderText("选中帧或 segment 以查看原始字节…")
        if max_height is not None:
            self.setMaximumHeight(max_height)

    # ── 数据 ────────────────────────────────────────────────

    def set_bytes(self, data: bytes) -> None:
        """填充字节（空字节清空视图，不崩）。"""
        data = bytes(data or b"")
        self._byte_length = len(data)
        self.setPlainText(build_dump_text(data))
        self._apply_default_format()

    @property
    def byte_length(self) -> int:
        """当前展示的字节数。"""
        return self._byte_length

    # ── 字节下标 ↔ 字符位置 ─────────────────────────────────

    def char_pos_of_byte(self, index: int) -> int | None:
        """第 ``index`` 字节在文档中的起始字符位置（越界返回 None）。

        返回的是该字节**两个 hex 字符的第一个**的位置，便于测试用
        ``toPlainText()[pos:pos+2]`` 直接核对是哪个字节。
        """
        if index < 0 or index >= self._byte_length:
            return None
        row, col = divmod(index, BYTES_PER_ROW)
        return row * ROW_STRIDE + _PREFIX_LEN + col * 3

    # ── 高亮 ────────────────────────────────────────────────

    def restyle_for_theme(self, dark: bool) -> None:
        """切深浅主题：换默认前后景并重刷（深色下不能再用白底黑字）。"""
        self._dark = bool(dark)
        p = canvas_theme.palette(self._dark)
        self._fg = QColor(p["text"])
        self._bg = QColor(p["bg"])
        self._apply_default_format()

    def _apply_default_format(self) -> None:
        """把全文恢复成默认字体/配色（清除历史高亮）。"""
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setFontFamily("Consolas")
        fmt.setForeground(self._fg)
        fmt.setBackground(self._bg)
        cursor.setCharFormat(fmt)

    def clear_highlight(self) -> None:
        """清除高亮。"""
        self._apply_default_format()

    def highlight_range(self, start: int | None, end: int | None) -> None:
        """高亮 ``[start, end]`` 字节区间（闭区间；None 或非法则清除）。

        跨行区间由单个 QTextCursor 选区一次完成，视觉上连续。
        """
        self._apply_default_format()
        if start is None or end is None:
            return
        if start < 0 or end < 0 or start > end:
            return
        if start >= self._byte_length:
            return
        end = min(end, self._byte_length - 1)
        pos_start = self.char_pos_of_byte(start)
        pos_end = self.char_pos_of_byte(end)
        if pos_start is None or pos_end is None:
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(pos_start)
        # +2：包含该字节的两个 hex 字符
        cursor.setPosition(pos_end + 2, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setFontFamily("Consolas")
        fmt.setForeground(DEFAULT_FG)
        fmt.setBackground(HIGHLIGHT_COLOR)
        cursor.setCharFormat(fmt)
