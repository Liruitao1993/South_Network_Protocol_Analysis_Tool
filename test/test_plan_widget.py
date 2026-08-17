"""测试方案Widget

提供测试方案管理页面：
- 帧列表管理（增删改、上下移动）
- 支持从协议组帧页面添加帧
- 支持导出/导入帧列表（JSON）
- 顺序发送并匹配响应帧
- 匹配规则支持 HEX/ASCII 模式，XX 为通配符
- 支持逐行超时设置（默认 2000ms）
- 测试结果：通过 / 失败 / 超时
"""



import _path_setup  # noqa: E402

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QComboBox, QSpinBox, QMessageBox, QFileDialog, QTextEdit,
    QDialog, QLineEdit, QGroupBox, QMenu, QPlainTextEdit
)
from PySide6.QtCore import Qt, Signal, QTimer, QObject
from PySide6.QtGui import (
    QFont, QColor, QTextCursor, QKeySequence,
    QSyntaxHighlighter, QTextCharFormat, QBrush
)

from gui_utils import apply_chinese_context_menus, setup_chinese_context_menu, ZoomableTableWidget

try:
    from lua_script_engine import LuaScriptEngine, LUA_TEMPLATES
    LUA_AVAILABLE = True
except ImportError:
    LUA_AVAILABLE = False

# 自动持久化文件路径
TEST_PLAN_PATH = Path(__file__).parent / "test_plan.json"


# ------------------------------------------------------------------------------
# 轻量 Vim 模式处理器（QPlainTextEdit Vim 键绑定）
# ------------------------------------------------------------------------------
class VimHandler(QObject):
    """轻量 Vim 模式处理器

    支持模式:
      - INSERT: 正常输入（默认）
      - NORMAL: Vim 命令模式
      - VISUAL: 可视化选择模式

    NORMAL 模式快捷键:
      h/j/k/l  左/下/上/右
      w/b      下一个单词/上一个单词
      0/$      行首/行尾
      gg/G     文首/文末
      i/a/I/A  进入插入模式
      o/O      下方/上方新建行
      dd       删除当前行
      yy       复制当前行
      p/P      粘贴到下方/上方
      u        撤销
      Ctrl+r   重做
      x        删除字符
      :w       保存（发信号）
      :q       退出（发信号）
    """

    mode_changed = Signal(str)   # 模式变化信号
    command = Signal(str)        # 命令信号（如 :w, :q）

    def __init__(self, editor: QPlainTextEdit, parent=None):
        super().__init__(parent)
        self._editor = editor
        self._mode = "INSERT"     # 默认插入模式
        self._pending = ""        # 待处理按键序列（如 dd, gg）
        self._yank_buffer = ""    # 复制缓冲区
        self._command_buffer = "" # :命令缓冲区
        self._in_command_line = False  # 是否正在输入 : 命令
        editor.installEventFilter(self)
        self._update_cursor_style()

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        if mode != self._mode:
            self._mode = mode
            self._pending = ""
            self._in_command_line = False
            self._command_buffer = ""
            self._update_cursor_style()
            self.mode_changed.emit(mode)

    def _update_cursor_style(self):
        """根据模式更新光标样式"""
        base = (
            "background-color: #1E1E1E; color: #D4D4D4; "
            "border-radius: 3px; selection-background-color: #264F78;"
        )
        if self._mode == "INSERT":
            self._editor.setCursorWidth(2)
            self._editor.setStyleSheet(f"QPlainTextEdit {{ {base} border: 1px solid #555; }}")
        elif self._mode == "NORMAL":
            self._editor.setCursorWidth(8)
            self._editor.setStyleSheet(f"QPlainTextEdit {{ {base} border: 2px solid #4FC3F7; }}")
        elif self._mode == "VISUAL":
            self._editor.setCursorWidth(2)
            self._editor.setStyleSheet(f"QPlainTextEdit {{ {base} border: 2px solid #FFB74D; }}")

    def eventFilter(self, obj, event):
        """事件过滤器，拦截键盘事件"""
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        if obj != self._editor:
            return False

        if event.type() == QEvent.Type.KeyPress:
            key_event = event
            return self._handle_key_press(key_event)

        return False

    def _handle_key_press(self, event) -> bool:
        """处理按键事件，返回 True 表示已处理"""
        key = event.key()
        modifiers = event.modifiers()
        text = event.text()

        # ---- : 命令输入模式 ----
        if self._in_command_line:
            return self._handle_command_input(key, text)

        # ---- INSERT 模式 ----
        if self._mode == "INSERT":
            if key == Qt.Key.Key_Escape:
                self.set_mode("NORMAL")
                return True
            # Ctrl+[ 也退出到 NORMAL
            if key == Qt.Key.Key_BracketLeft and modifiers & Qt.KeyboardModifier.ControlModifier:
                self.set_mode("NORMAL")
                return True
            return False  # 其他按键正常输入

        # ---- VISUAL 模式 ----
        if self._mode == "VISUAL":
            return self._handle_visual_key(key, text)

        # ---- NORMAL 模式 ----
        return self._handle_normal_key(key, modifiers, text)

    def _handle_normal_key(self, key, modifiers, text: str) -> bool:
        """处理 NORMAL 模式按键"""
        cursor = self._editor.textCursor()

        # Ctrl 快捷键
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_R:
                self._editor.redo()
                return True
            if key == Qt.Key.Key_C:
                # Ctrl+C 退出到 NORMAL（不复制）
                self.set_mode("NORMAL")
                return True
            return False

        # 待处理序列（dd, gg 等）
        if self._pending:
            pending = self._pending + text
            self._pending = ""
            if pending == "dd":
                cursor.select(QTextCursor.SelectionType.LineUnderCursor)
                self._yank_buffer = cursor.selectedText().replace("\u2029", "\n")
                cursor.removeSelectedText()
                cursor.deleteChar()  # 删除换行符
                self._editor.setTextCursor(cursor)
                return True
            elif pending == "yy":
                cursor.select(QTextCursor.SelectionType.LineUnderCursor)
                self._yank_buffer = cursor.selectedText().replace("\u2029", "\n")
                cursor.clearSelection()
                self._editor.setTextCursor(cursor)
                return True
            # 未识别的双键序列，忽略
            return True

        # 单键命令
        if text == "h":
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "j":
            cursor.movePosition(QTextCursor.MoveOperation.Down)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "k":
            cursor.movePosition(QTextCursor.MoveOperation.Up)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "l":
            cursor.movePosition(QTextCursor.MoveOperation.Right)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "w":
            cursor.movePosition(QTextCursor.MoveOperation.NextWord)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "b":
            cursor.movePosition(QTextCursor.MoveOperation.PreviousWord)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "0":
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "$":
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "G":
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "g":
            self._pending = "g"
            return True
        elif text == "i":
            self.set_mode("INSERT")
            return True
        elif text == "a":
            cursor.movePosition(QTextCursor.MoveOperation.Right)
            self._editor.setTextCursor(cursor)
            self.set_mode("INSERT")
            return True
        elif text == "I":
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            self._editor.setTextCursor(cursor)
            self.set_mode("INSERT")
            return True
        elif text == "A":
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
            self._editor.setTextCursor(cursor)
            self.set_mode("INSERT")
            return True
        elif text == "o":
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
            cursor.insertText("\n")
            self._editor.setTextCursor(cursor)
            self.set_mode("INSERT")
            return True
        elif text == "O":
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cursor.insertText("\n")
            cursor.movePosition(QTextCursor.MoveOperation.Up)
            self._editor.setTextCursor(cursor)
            self.set_mode("INSERT")
            return True
        elif text == "d":
            self._pending = "d"
            return True
        elif text == "y":
            self._pending = "y"
            return True
        elif text == "p":
            if self._yank_buffer:
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                cursor.insertText("\n" + self._yank_buffer.rstrip("\n"))
                self._editor.setTextCursor(cursor)
            return True
        elif text == "P":
            if self._yank_buffer:
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                cursor.insertText(self._yank_buffer.rstrip("\n") + "\n")
                self._editor.setTextCursor(cursor)
            return True
        elif text == "x":
            cursor.deleteChar()
            self._editor.setTextCursor(cursor)
            return True
        elif text == "u":
            self._editor.undo()
            return True
        elif text == "v":
            self.set_mode("VISUAL")
            return True
        elif text == "V":
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            self._editor.setTextCursor(cursor)
            self.set_mode("VISUAL")
            return True
        elif text == ":":
            self._in_command_line = True
            self._command_buffer = ""
            self.mode_changed.emit(":")
            return True
        elif text == "/":
            # 简单搜索：暂不实现，避免复杂化
            return True

        # 数字前缀（如 3j, 5l）
        if text.isdigit() and text != "0":
            # 暂不实现数字重复，忽略
            return True

        return True  # NORMAL 模式下吞掉所有按键

    def _handle_visual_key(self, key, text: str) -> bool:
        """处理 VISUAL 模式按键"""
        cursor = self._editor.textCursor()

        if key == Qt.Key.Key_Escape:
            cursor.clearSelection()
            self._editor.setTextCursor(cursor)
            self.set_mode("NORMAL")
            return True

        if text == "h":
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "j":
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "k":
            cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.KeepAnchor)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "l":
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "w":
            cursor.movePosition(QTextCursor.MoveOperation.NextWord, QTextCursor.MoveMode.KeepAnchor)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "b":
            cursor.movePosition(QTextCursor.MoveOperation.PreviousWord, QTextCursor.MoveMode.KeepAnchor)
            self._editor.setTextCursor(cursor)
            return True
        elif text == "y":
            self._yank_buffer = cursor.selectedText().replace("\u2029", "\n")
            cursor.clearSelection()
            self._editor.setTextCursor(cursor)
            self.set_mode("NORMAL")
            return True
        elif text == "d" or text == "x":
            self._yank_buffer = cursor.selectedText().replace("\u2029", "\n")
            cursor.removeSelectedText()
            self._editor.setTextCursor(cursor)
            self.set_mode("NORMAL")
            return True
        elif text == ">":
            # 缩进
            selected = cursor.selectedText().replace("\u2029", "\n")
            indented = "  " + selected.replace("\n", "\n  ")
            cursor.insertText(indented)
            self.set_mode("NORMAL")
            return True
        elif text == "<":
            # 反缩进
            selected = cursor.selectedText().replace("\u2029", "\n")
            dedented = "\n".join(
                line[2:] if line.startswith("  ") else line
                for line in selected.split("\n")
            )
            cursor.insertText(dedented)
            self.set_mode("NORMAL")
            return True

        return True  # 吞掉其他按键

    def _handle_command_input(self, key, text: str) -> bool:
        """处理 : 命令输入"""
        if key == Qt.Key.Key_Escape:
            self._in_command_line = False
            self._command_buffer = ""
            self.mode_changed.emit(self._mode)
            return True
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            cmd = self._command_buffer.strip()
            self._in_command_line = False
            self._command_buffer = ""
            if cmd in ("w", "write"):
                self.command.emit("w")
            elif cmd in ("q", "quit"):
                self.command.emit("q")
            elif cmd in ("wq", "x"):
                self.command.emit("wq")
            self.mode_changed.emit(self._mode)
            return True
        elif key == Qt.Key.Key_Backspace:
            if self._command_buffer:
                self._command_buffer = self._command_buffer[:-1]
                self.mode_changed.emit(":" + self._command_buffer)
            else:
                self._in_command_line = False
                self.mode_changed.emit(self._mode)
            return True
        elif text and text.isprintable():
            self._command_buffer += text
            self.mode_changed.emit(":" + self._command_buffer)
            return True
        return True

# ------------------------------------------------------------------------------
# 响应帧动态处理引擎（时间填充 / 校验自动计算）
# ------------------------------------------------------------------------------
# 标记语法：【...】
#   时间：【"time",字节数,格式,"big|little"】  例：【"time",6,Y-M-D-h-m-s,"big"】
#   校验：【"CS",占用字节数,起始:结束】        例：【"CS",1,2:-2】
#   CRC：【"CRC16",占用字节数,起始:结束】     例：【"CRC16",2,3:-3】
# ------------------------------------------------------------------------------

# CRC16-CCITT 查表（与 plc_rf_parser.py 一致）
_CRC16_TABLE = [
    0x0000, 0x1189, 0x2312, 0x329b, 0x4624, 0x57ad, 0x6536, 0x74bf,
    0x8c48, 0x9dc1, 0xaf5a, 0xbed3, 0xca6c, 0xdbe5, 0xe97e, 0xf8f7,
    0x1081, 0x0108, 0x3393, 0x221a, 0x56a5, 0x472c, 0x75b7, 0x643e,
    0x9cc9, 0x8d40, 0xbfdb, 0xae52, 0xdaed, 0xcb64, 0xf9ff, 0xe876,
    0x2102, 0x308b, 0x0210, 0x1399, 0x6726, 0x76af, 0x4434, 0x55bd,
    0xad4a, 0xbcc3, 0x8e58, 0x9fd1, 0xeb6e, 0xfae7, 0xc87c, 0xd9f5,
    0x3183, 0x200a, 0x1291, 0x0318, 0x77a7, 0x662e, 0x54b5, 0x453c,
    0xbdcb, 0xac42, 0x9ed9, 0x8f50, 0xfbef, 0xea66, 0xd8fd, 0xc974,
    0x4204, 0x538d, 0x6116, 0x709f, 0x0420, 0x15a9, 0x2732, 0x36bb,
    0xce4c, 0xdfc5, 0xed5e, 0xfcd7, 0x8868, 0x99e1, 0xab7a, 0xbaf3,
    0x5285, 0x430c, 0x7197, 0x601e, 0x14a1, 0x0528, 0x37b3, 0x263a,
    0xdecd, 0xcf44, 0xfddf, 0xec56, 0x98e9, 0x8960, 0xbbfb, 0xaa72,
    0x6306, 0x728f, 0x4014, 0x519d, 0x2522, 0x34ab, 0x0630, 0x17b9,
    0xef4e, 0xfec7, 0xcc5c, 0xddd5, 0xa96a, 0xb8e3, 0x8a78, 0x9bf1,
    0x7387, 0x620e, 0x5095, 0x411c, 0x35a3, 0x242a, 0x16b1, 0x0738,
    0xffcf, 0xee46, 0xdcdd, 0xcd54, 0xb9eb, 0xa862, 0x9af9, 0x8b70,
    0x8408, 0x9581, 0xa71a, 0xb693, 0xc22c, 0xd3a5, 0xe13e, 0xf0b7,
    0x0840, 0x19c9, 0x2b52, 0x3adb, 0x4e64, 0x5fed, 0x6d76, 0x7cff,
    0x9489, 0x8500, 0xb79b, 0xa612, 0xd2ad, 0xc324, 0xf1bf, 0xe036,
    0x18c1, 0x0948, 0x3bd3, 0x2a5a, 0x5ee5, 0x4f6c, 0x7df7, 0x6c7e,
    0xa50a, 0xb483, 0x8618, 0x9791, 0xe32e, 0xf2a7, 0xc03c, 0xd1b5,
    0x2942, 0x38cb, 0x0a50, 0x1bd9, 0x6f66, 0x7eef, 0x4c74, 0x5dfd,
    0xb58b, 0xa402, 0x9699, 0x8710, 0xf3af, 0xe226, 0xd0bd, 0xc134,
    0x39c3, 0x284a, 0x1ad1, 0x0b58, 0x7fe7, 0x6e6e, 0x5cf5, 0x4d7c,
    0xc60c, 0xd785, 0xe51e, 0xf497, 0x8028, 0x91a1, 0xa33a, 0xb2b3,
    0x4a44, 0x5bcd, 0x6956, 0x78df, 0x0c60, 0x1de9, 0x2f72, 0x3efb,
    0xd68d, 0xc704, 0xf59f, 0xe416, 0x90a9, 0x8120, 0xb3bb, 0xa232,
    0x5ac5, 0x4b4c, 0x79d7, 0x685e, 0x1ce1, 0x0d68, 0x3ff3, 0x2e7a,
    0xe70e, 0xf687, 0xc41c, 0xd595, 0xa12a, 0xb0a3, 0x8238, 0x93b1,
    0x6b46, 0x7acf, 0x4854, 0x59dd, 0x2d62, 0x3ceb, 0x0e70, 0x1ff9,
    0xf78f, 0xe606, 0xd49d, 0xc514, 0xb1ab, 0xa022, 0x92b9, 0x8330,
    0x7bc7, 0x6a4e, 0x58d5, 0x495c, 0x3de3, 0x2c6a, 0x1ef1, 0x0f78
]


def _calc_crc16(data: bytes) -> int:
    """CRC16-CCITT (0xFFFF初始, 0xFFFF最终异或)"""
    fcs = 0xFFFF
    for byte in data:
        fcs = ((fcs >> 8) ^ _CRC16_TABLE[(fcs ^ byte) & 0xFF]) & 0xFFFF
    return fcs ^ 0xFFFF


def _split_bracket_params(content: str) -> List[str]:
    """按逗号分割标记参数，支持引号包裹"""
    parts: List[str] = []
    current = ""
    in_quote = False
    quote_char = None
    for ch in content:
        if ch in ('"', "'"):
            if not in_quote:
                in_quote = True
                quote_char = ch
            elif quote_char == ch:
                in_quote = False
                quote_char = None
            else:
                current += ch
        elif ch == "," and not in_quote:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


def _parse_byte_range(range_str: str, total: int) -> Tuple[int, int]:
    """解析字节范围（1-based索引，支持负数倒数）"""
    if ":" in range_str:
        start_str, end_str = range_str.split(":", 1)
        start = int(start_str) - 1 if start_str else 0
        end = int(end_str) if end_str else total
        if end < 0:
            end = total + end
    else:
        start = int(range_str) - 1
        end = total
    return max(0, start), min(total, end)


def _fill_time(params: List[str]) -> str:
    """填充系统时间（BCD码）"""
    byte_count = int(params[1])
    fmt = params[2].strip('"\'')
    endian = params[3].strip('"\'').lower() if len(params) > 3 else "big"

    now = datetime.now()
    mapping = {
        "Y": now.year % 100,
        "M": now.month,
        "D": now.day,
        "h": now.hour,
        "m": now.minute,
        "s": now.second,
    }

    parts = fmt.split("-")
    bcd_bytes = []
    for p in parts:
        val = mapping.get(p, 0)
        # 十进制直接映射为 BCD 字节：26 -> 0x26
        bcd_bytes.append(int(f"{val:02d}", 16))

    if endian == "little":
        bcd_bytes = bcd_bytes[::-1]

    result = "".join(f"{b:02X}" for b in bcd_bytes)
    # 如果生成的长度超过需求，截断；不足则补 00
    if len(result) // 2 > byte_count:
        result = result[: byte_count * 2]
    return result


def _calc_checksum(frame_hex: str, match_start: int, match_end: int, params: List[str]) -> str:
    """计算校验并返回 HEX 字符串"""
    algo = params[0].strip('"\'')
    size = int(params[1])
    range_str = params[2].strip('"\'')

    # 将帧中所有 【】 标记（包括当前正在计算的）临时替换为等长占位符，
    # 保证总字节数正确，便于范围计算。
    placeholder_pattern = re.compile(r"【([^】]+)】")

    def _ph_repl(m: Any) -> str:
        p = _split_bracket_params(m.group(1))
        a = p[0].strip('"\'')
        if a in ("CS", "CRC16"):
            s = int(p[1]) if len(p) > 1 else 0
        elif a == "time":
            s = int(p[1]) if len(p) > 1 else 0
        else:
            s = 0
        return "00" * s

    clean_hex = placeholder_pattern.sub(_ph_repl, frame_hex)
    clean_hex = clean_hex.replace(" ", "")

    try:
        data = bytes.fromhex(clean_hex)
    except ValueError:
        return "00" * size

    total = len(data)
    start, end = _parse_byte_range(range_str, total)
    calc_bytes = data[start:end]

    if algo == "CS":
        val = sum(calc_bytes) & 0xFF
        return f"{val:0{size * 2}X}"
    elif algo == "CRC16":
        val = _calc_crc16(calc_bytes)
        return f"{val:0{size * 2}X}"
    return "00" * size


def process_response_frame(frame_hex: str) -> str:
    """处理响应帧中的动态标记，返回可发送的纯 HEX 字符串（无空格）"""
    if not frame_hex:
        return ""

    # 1) 先替换所有时间标记
    time_pattern = re.compile(r"【([^】]+)】")

    def _repl_time(m: Any) -> str:
        content = m.group(1)
        params = _split_bracket_params(content)
        if params and params[0].strip('"\'') == "time":
            return _fill_time(params)
        return m.group(0)

    result = time_pattern.sub(_repl_time, frame_hex)

    # 2) 再替换所有校验标记（逐个，支持多标记互相独立）
    for _ in range(20):  # 安全上限
        m = time_pattern.search(result)
        if not m:
            break
        content = m.group(1)
        params = _split_bracket_params(content)
        algo = params[0].strip('"\'') if params else ""
        if algo in ("CS", "CRC16"):
            replacement = _calc_checksum(result, m.start(), m.end(), params)
            result = result[: m.start()] + replacement + result[m.end() :]
        else:
            # 未知标记直接移除
            result = result[: m.start()] + result[m.end() :]

    return result.replace(" ", "")


# ------------------------------------------------------------------------------
# Lua 语法高亮器
# ------------------------------------------------------------------------------
class LuaSyntaxHighlighter(QSyntaxHighlighter):
    """Lua 语法高亮器

    支持：关键字、内置函数、字符串、注释（单行/多行）、数字、运算符
    """

    # Lua 关键字
    LUA_KEYWORDS = (
        'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for',
        'function', 'goto', 'if', 'in', 'local', 'nil', 'not', 'or',
        'repeat', 'return', 'then', 'true', 'until', 'while',
    )

    # Lua 内置函数
    LUA_BUILTINS = (
        'print', 'type', 'tostring', 'tonumber', 'error', 'pcall', 'xpcall',
        'select', 'unpack', 'rawget', 'rawset', 'rawequal', 'rawlen',
        'setmetatable', 'getmetatable', 'require', 'dofile', 'loadfile',
        'load', 'next', 'pairs', 'ipairs', 'assert', 'collectgarbage',
        'coroutine', 'string', 'table', 'math', 'io', 'os', 'debug',
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules: List[Tuple['re.Pattern', QTextCharFormat]] = []
        self._build_rules()

    # ---- 格式工厂 ----
    @staticmethod
    def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QBrush(QColor(color)))
        if bold:
            f.setFontWeight(QFont.Weight.Bold)
        if italic:
            f.setFontItalic(True)
        return f

    def _build_rules(self):
        kw_fmt  = self._fmt('#569CD6', bold=True)   # 关键字：蓝
        bi_fmt  = self._fmt('#4EC9B0')               # 内置函数：青绿
        num_fmt = self._fmt('#B5CEA8')               # 数字：浅绿
        str_fmt = self._fmt('#CE9178')               # 字符串：橙棕
        op_fmt  = self._fmt('#D4D4D4')               # 运算符：浅灰

        # 关键字（全词匹配）
        kw_pat = r'\b(' + '|'.join(self.LUA_KEYWORDS) + r')\b'
        self._rules.append((re.compile(kw_pat), kw_fmt))

        # 内置函数
        bi_pat = r'\b(' + '|'.join(self.LUA_BUILTINS) + r')\s*(?=\()'
        self._rules.append((re.compile(bi_pat), bi_fmt))

        # 数字：十六进制 / 浮点 / 整数
        self._rules.append((re.compile(r'\b0[xX][0-9a-fA-F]+\b'), num_fmt))
        self._rules.append((re.compile(r'\b\d+\.?\d*(?:[eE][+-]?\d+)?\b'), num_fmt))

        # 双引号字符串（含转义）
        self._rules.append((re.compile(r'"(?:\\.|[^"\\])*"'), str_fmt))
        # 单引号字符串（含转义）
        self._rules.append((re.compile(r"'(?:\\.|[^'\\])*'"), str_fmt))

        # 运算符
        self._rules.append((re.compile(r'[+\-*/%^#=<>~:;,.\(\)\{\}\[\]]'), op_fmt))

    # ---- 多行注释状态 ----
    # userState: 0 = 正常, 1 = 在多行注释内
    def highlightBlock(self, text: str):
        comment_fmt = self._fmt('#6A9955', italic=True)  # 注释：绿色斜体

        # 处理多行注释延续
        if self.previousBlockState() == 1:
            end_idx = text.find(']]')
            if end_idx == -1:
                self.setFormat(0, len(text), comment_fmt)
                self.setCurrentBlockState(1)
                return
            else:
                self.setFormat(0, end_idx + 2, comment_fmt)
                start = end_idx + 2
                self.setCurrentBlockState(0)
        else:
            start = 0

        # 单行规则
        remaining = text[start:]
        for pat, fmt in self._rules:
            for m in pat.finditer(remaining):
                self.setFormat(start + m.start(), m.end() - m.start(), fmt)

        # 单行注释 --（需在其他规则之后处理，避免被覆盖）
        single_comment_fmt = self._fmt('#6A9955', italic=True)
        idx = self._find_single_comment(text, start)
        if idx != -1:
            self.setFormat(idx, len(text) - idx, single_comment_fmt)

        # 多行注释开始 --[[ 或 --[=..=[
        ml_start = self._find_multiline_comment_start(text, start)
        if ml_start != -1:
            # 检查同一行是否有结束 ]]
            content_start = text.find('[[', ml_start)
            if content_start == -1:
                # --[==[ 形式，找 [[ 之前的位置
                content_start = ml_start + 2
            else:
                content_start += 2
            end_idx = text.find(']]', content_start)
            if end_idx == -1:
                self.setFormat(ml_start, len(text) - ml_start, single_comment_fmt)
                self.setCurrentBlockState(1)
            else:
                self.setFormat(ml_start, end_idx + 2 - ml_start, single_comment_fmt)

    @staticmethod
    def _find_single_comment(text: str, start_from: int = 0) -> int:
        """查找单行注释 -- 的位置（排除字符串内的）"""
        idx = start_from
        in_str = None
        while idx < len(text):
            ch = text[idx]
            if in_str:
                if ch == '\\':
                    idx += 2
                    continue
                if ch == in_str:
                    in_str = None
            else:
                if ch in ('"', "'"):
                    in_str = ch
                elif ch == '-' and idx + 1 < len(text) and text[idx + 1] == '-':
                    return idx
            idx += 1
        return -1

    @staticmethod
    def _find_multiline_comment_start(text: str, start_from: int = 0) -> int:
        """查找多行注释 --[[ 或 --[==[ 的开始位置"""
        idx = start_from
        in_str = None
        while idx < len(text) - 1:
            ch = text[idx]
            if in_str:
                if ch == '\\':
                    idx += 2
                    continue
                if ch == in_str:
                    in_str = None
            else:
                if ch in ('"', "'"):
                    in_str = ch
                elif ch == '-' and text[idx + 1] == '-':
                    # 检查后面是否跟 [=[ 或 [[
                    rest = text[idx + 2:]
                    if rest.startswith('[[') or re.match(r'=+\[', rest):
                        return idx
            idx += 1
        return -1


# ------------------------------------------------------------------------------
# Lua 代码编辑器（语法高亮 + 列线 + 行号 + 自动缩进 + 括号匹配）
# ------------------------------------------------------------------------------
class LuaCodeEditor(QPlainTextEdit):
    """功能完善的 Lua 代码编辑器

    功能：
      - Lua 语法高亮（关键字/内置函数/字符串/注释/数字）
      - 垂直列线：在指定列位置绘制辅助线（默认 40/80/120 列）
      - 行号栏：左侧显示行号，当前行高亮
      - 自动缩进：回车保持缩进，Tab 插入 4 空格
      - 括号匹配：输入 )] } 时短暂高亮对应左括号
      - 暗色主题：VS Code Dark+ 风格配色
    """

    # 列线位置（字符列号）
    COLUMN_GUIDES = (40, 80, 120)
    # 列线颜色
    _GUIDE_COLOR = QColor(60, 60, 60, 80)
    _GUIDE_80_COLOR = QColor(80, 60, 60, 120)
    _LINE_NUM_COLOR = QColor(100, 100, 100)
    _CURRENT_LINE_COLOR = QColor(40, 40, 40, 100)
    # 括号匹配高亮颜色
    _BRACKET_MATCH_COLOR = QColor(80, 120, 80, 160)
    # 括号不匹配颜色
    _BRACKET_ERROR_COLOR = QColor(180, 60, 60, 180)
    # 配对括号映射
    _BRACKET_PAIRS = {'(': ')', '[': ']', '{': '}'}
    _BRACKET_OPEN = {')': '(', ']': '[', '}': '{'}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_editor_style()
        self._line_num_area = _LineNumberArea(self)
        self._char_width = 0
        self._update_char_width()
        # 语法高亮器
        self._highlighter = LuaSyntaxHighlighter(self.document())
        # 信号连接
        self.blockCountChanged.connect(self._update_line_num_area_width)
        self.updateRequest.connect(self._update_line_num_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_num_area_width()
        # 括号匹配用的额外 selection
        self._bracket_selections: list = []

    # ---- 编辑器基础样式 ----
    def _setup_editor_style(self):
        """设置暗色主题和等宽字体"""
        font = QFont('Consolas', 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # 暗色主题样式表
        self.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #1E1E1E;"
            "  color: #D4D4D4;"
            "  selection-background-color: #264F78;"
            "  selection-color: #FFFFFF;"
            "  border: 1px solid #3C3C3C;"
            "}"
        )

    def setFont(self, font):
        super().setFont(font)
        self._update_char_width()
        self._update_line_num_area_width()
        # 同步 Tab 宽度
        if self._char_width:
            self.setTabStopDistance(self._char_width * 4)

    def _update_char_width(self):
        """计算等宽字体单字符宽度"""
        fm = self.fontMetrics()
        self._char_width = fm.horizontalAdvance("M")

    # ---- 当前行高亮 ----
    def _highlight_current_line(self):
        """光标移动时刷新以更新当前行高亮"""
        self.viewport().update()

    # ---- 行号区域 ----
    def line_num_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 8 + self._char_width * (digits + 1)

    def _update_line_num_area_width(self):
        self.setViewportMargins(self.line_num_area_width(), 0, 0, 0)

    def _update_line_num_area(self, rect: 'QRect', dy: int):
        if dy:
            self._line_num_area.scroll(0, dy)
        else:
            self._line_num_area.update(0, rect.y(), self._line_num_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_num_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_num_area.setGeometry(
            cr.left(), cr.top(), self.line_num_area_width(), cr.height()
        )

    def line_num_area_paint(self, event):
        """绘制行号区域"""
        from PySide6.QtGui import QPainter, QPen
        painter = QPainter(self._line_num_area)
        painter.fillRect(event.rect(), QColor(30, 30, 30))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        current_block = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                if block_number == current_block:
                    painter.setPen(QPen(QColor(200, 200, 200)))
                else:
                    painter.setPen(QPen(self._LINE_NUM_COLOR))
                painter.drawText(
                    0, top, self._line_num_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1
        painter.end()

    # ---- 列线 + 当前行高亮 + 括号匹配绘制 ----
    def paintEvent(self, event):
        """重写绘制事件：先画列线和高亮行，再画文本"""
        from PySide6.QtGui import QPainter, QPen

        painter = QPainter(self.viewport())
        offset = self.contentOffset()

        # 当前行高亮
        cursor_block = self.textCursor().blockNumber()
        block = self.firstVisibleBlock()
        top = int(self.blockBoundingGeometry(block).translated(offset).top())
        viewport_h = self.viewport().height()

        while block.isValid() and top < viewport_h:
            if block.blockNumber() == cursor_block:
                bh = int(self.blockBoundingRect(block).height())
                painter.fillRect(0, top, self.viewport().width(), bh, self._CURRENT_LINE_COLOR)
                break
            block = block.next()
            top += int(self.blockBoundingRect(block).height())

        # 列线
        line_num_w = self.line_num_area_width()
        vp_height = self.viewport().height()
        for col in self.COLUMN_GUIDES:
            x = line_num_w + col * self._char_width + offset.x()
            if x < self.viewport().width():
                color = self._GUIDE_80_COLOR if col == 80 else self._GUIDE_COLOR
                painter.setPen(QPen(color, 1, Qt.PenStyle.DotLine))
                painter.drawLine(x, 0, x, vp_height)
        painter.end()

        # 绘制文本和光标
        super().paintEvent(event)

    # ---- 按键处理：自动缩进 / Tab / 括号自动补全 ----
    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        text = event.text()

        # Enter：自动缩进（保持上一行缩进）
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            block_text = cursor.block().text()
            # 提取当前行的前导空白
            indent = ''
            for ch in block_text:
                if ch in (' ', '\t'):
                    indent += ch
                else:
                    break
            # 如果上一行以 then/do/function/else/elseif/for/if/repeat/while 结尾，增加一级缩进
            stripped = block_text.rstrip()
            indent_increase_keywords = (
                'then', 'do', 'else', 'elseif', 'function', 'for',
                'if', 'repeat', 'while', '{',
            )
            last_word = stripped.split()[-1] if stripped.split() else ''
            if last_word in indent_increase_keywords or stripped.endswith('{'):
                indent += '    '
            cursor.insertText('\n' + indent)
            self.setTextCursor(cursor)
            return

        # Tab：插入 4 空格
        if key == Qt.Key.Key_Tab and modifiers == Qt.KeyboardModifier.NoModifier:
            cursor = self.textCursor()
            if cursor.hasSelection():
                # 选中文本时 Tab = 增加缩进
                self._indent_selection(indent=True)
            else:
                cursor.insertText('    ')
            return

        # Shift+Tab：减少缩进
        if key == Qt.Key.Key_Backtab:
            self._indent_selection(indent=False)
            return

        # 括号自动补全：输入 ( [ { 时自动插入配对
        if text in self._BRACKET_PAIRS and modifiers == Qt.KeyboardModifier.NoModifier:
            cursor = self.textCursor()
            close_ch = self._BRACKET_PAIRS[text]
            cursor.insertText(text + close_ch)
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)
            # 触发括号匹配高亮
            QTimer.singleShot(0, self._update_bracket_match)
            return

        # 输入 ) ] } 时检查匹配
        if text in self._BRACKET_OPEN:
            super().keyPressEvent(event)
            QTimer.singleShot(0, self._update_bracket_match)
            return

        super().keyPressEvent(event)
        # 任何按键后都检查括号匹配
        QTimer.singleShot(0, self._update_bracket_match)

    def _indent_selection(self, indent: bool = True):
        """对选中行增加或减少缩进"""
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.beginEditBlock()
        block = cursor.block()
        while block.isValid() and block.position() <= end:
            cursor.setPosition(block.position())
            text = block.text()
            if indent:
                cursor.insertText('    ')
            else:
                # 移除最多 4 个前导空格
                spaces = 0
                for ch in text:
                    if ch == ' ' and spaces < 4:
                        spaces += 1
                    elif ch == '\t':
                        spaces += 4
                    else:
                        break
                if spaces > 0:
                    cursor.movePosition(
                        QTextCursor.MoveOperation.Right,
                        QTextCursor.MoveMode.KeepAnchor,
                        min(spaces, len(text))
                    )
                    cursor.removeSelectedText()
            block = block.next()
        cursor.endEditBlock()

    # ---- 括号匹配高亮 ----
    def _update_bracket_match(self):
        """查找并高亮当前光标处的配对括号"""
        from PySide6.QtGui import QPlainTextEdit, QTextCharFormat, QTextCursor
        # 清除旧的高亮
        extra = [s for s in self.extraSelections()
                 if not hasattr(s, '_is_bracket') or not s._is_bracket]
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()
        # 检查光标前一个字符
        if pos > 0:
            cursor.setPosition(pos - 1)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            ch = cursor.selectedText()
            if ch in self._BRACKET_OPEN or ch in self._BRACKET_PAIRS:
                match_pos = self._find_matching_bracket(doc, pos - 1, ch)
                if match_pos is not None:
                    sel = QPlainTextEdit.ExtraSelection()
                    sel.cursor = QTextCursor(doc)
                    sel.cursor.setPosition(match_pos)
                    sel.cursor.movePosition(
                        QTextCursor.MoveOperation.Right,
                        QTextCursor.MoveMode.KeepAnchor
                    )
                    sel.format = QTextCharFormat()
                    sel.format.setBackground(self._BRACKET_MATCH_COLOR)
                    sel._is_bracket = True
                    extra.append(sel)
                    # 也高亮当前括号
                    sel2 = QPlainTextEdit.ExtraSelection()
                    sel2.cursor = QTextCursor(doc)
                    sel2.cursor.setPosition(pos - 1)
                    sel2.cursor.movePosition(
                        QTextCursor.MoveOperation.Right,
                        QTextCursor.MoveMode.KeepAnchor
                    )
                    sel2.format = QTextCharFormat()
                    sel2.format.setBackground(self._BRACKET_MATCH_COLOR)
                    sel2._is_bracket = True
                    extra.append(sel2)
                else:
                    # 括号不匹配，标红
                    sel = QPlainTextEdit.ExtraSelection()
                    sel.cursor = QTextCursor(doc)
                    sel.cursor.setPosition(pos - 1)
                    sel.cursor.movePosition(
                        QTextCursor.MoveOperation.Right,
                        QTextCursor.MoveMode.KeepAnchor
                    )
                    sel.format = QTextCharFormat()
                    sel.format.setBackground(self._BRACKET_ERROR_COLOR)
                    sel._is_bracket = True
                    extra.append(sel)
        self.setExtraSelections(extra)

    def _find_matching_bracket(self, doc, pos: int, ch: str) -> Optional[int]:
        """在文档中查找 pos 处括号的配对位置"""
        if ch in self._BRACKET_PAIRS:
            # 向右查找
            open_ch = ch
            close_ch = self._BRACKET_PAIRS[ch]
            direction = 1
        else:
            # 向左查找
            close_ch = ch
            open_ch = self._BRACKET_OPEN[ch]
            direction = -1

        depth = 0
        i = pos
        text = doc.toPlainText()
        length = len(text)
        while 0 <= i < length:
            c = text[i]
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return i
            i += direction
        return None


class _LineNumberArea(QWidget):
    """行号区域控件"""

    def __init__(self, editor: LuaCodeEditor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(self._editor.line_num_area_width(), 0)

    def paintEvent(self, event):
        self._editor.line_num_area_paint(event)


class AddTestItemDialog(QDialog):
    """添加/编辑测试项对话框"""

    def __init__(self, item: Dict[str, Any] = None, parent=None):
        super().__init__(parent)
        self._edit_mode = item is not None
        self.setWindowTitle("编辑测试项" if self._edit_mode else "添加测试项")
        self.setMinimumWidth(480)
        self._result: Optional[Dict[str, Any]] = None
        self._init_ui(item or {})
        self._apply_nature()

    @staticmethod
    def _derive_nature(item: Dict[str, Any]) -> str:
        """从 item 字段推导性质"""
        if item.get("is_lua_script", False):
            return "Lua脚本"
        if item.get("persistent", False):
            return "后台监听"
        if not item.get("send_enabled", True) and not item.get("match_enabled", True):
            return "纯等待"
        return "发送帧"

    def _apply_nature(self):
        """根据性质下拉同步各控件状态"""
        nature = self.nature_combo.currentText()
        if nature == "发送帧":
            self._set_nature_state(send=True, match=True, persistent=False)
            self._apply_lua_mode(False)
        elif nature == "后台监听":
            self._set_nature_state(send=False, match=True, persistent=True)
            self._apply_lua_mode(False)
        elif nature == "纯等待":
            self._set_nature_state(send=False, match=False, persistent=False)
            self._apply_lua_mode(False)
        elif nature == "Lua脚本":
            self._set_nature_state(send=False, match=False, persistent=False)
            self._apply_lua_mode(True)

    def _set_nature_state(self, send: bool, match: bool, persistent: bool):
        """同步控件状态，屏蔽信号避免循环触发"""
        self.send_enabled.blockSignals(True)
        self.send_enabled.setChecked(send)
        self.send_enabled.setEnabled(True)
        self.send_enabled.blockSignals(False)
        self.match_enabled.blockSignals(True)
        self.match_enabled.setChecked(match)
        self.match_enabled.setEnabled(True)
        self.match_enabled.blockSignals(False)
        self.timeout_spin.setEnabled(True)
        if not send:
            self.timeout_spin.setValue(600000)

    def _init_ui(self, data: Dict[str, Any]):
        nature = self._derive_nature(data)
        # Lua 脚本内容（编辑模式）
        self._lua_script = data.get("script", "")
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ---- 性质 ----
        row = QHBoxLayout()
        row.addWidget(QLabel("性质:"))
        self.nature_combo = QComboBox()
        self.nature_combo.addItems(["发送帧", "后台监听", "纯等待", "Lua脚本"])
        self.nature_combo.setCurrentText(nature)
        self.nature_combo.currentTextChanged.connect(self._apply_nature)
        nature_help = QLabel("发送帧→发后匹配  后台→全时监听  纯等待→忽略帧  Lua→脚本控制")
        nature_help.setStyleSheet("color: #888; font-size: 11px;")
        row.addWidget(self.nature_combo)
        row.addWidget(nature_help)
        row.addStretch()
        layout.addLayout(row)

        # Lua 脚本编辑器（仅 Lua 模式下显示）
        script_header = QHBoxLayout()
        self.script_label = QLabel("Lua 脚本:")
        self.script_label.setVisible(False)
        script_header.addWidget(self.script_label)
        script_header.addStretch()
        # Vim 模式指示器
        self.vim_mode_label = QLabel("-- INSERT --")
        self.vim_mode_label.setStyleSheet(
            "QLabel { color: #1E1E1E; background-color: #4FC3F7; padding: 1px 8px; "
            "border-radius: 2px; font-size: 11px; font-weight: bold; font-family: Consolas; }"
        )
        self.vim_mode_label.setVisible(False)
        script_header.addWidget(self.vim_mode_label)
        # Vim 帮助提示
        vim_help = QLabel("<span style='color:#888;font-size:10px'>ESC=普通模式 | hjkl=移动 | i=插入 | :w=保存 | :q=关闭</span>")
        vim_help.setVisible(False)
        self._vim_help_label = vim_help
        script_header.addWidget(vim_help)
        layout.addLayout(script_header)

        self.script_input = LuaCodeEditor()
        self.script_input.setPlaceholderText("-- Lua 脚本代码\nlog('hello')")
        script_font = QFont("Consolas", 10)
        self.script_input.setFont(script_font)
        self.script_input.setMinimumHeight(160)
        self.script_input.setMaximumHeight(400)
        self.script_input.setStyleSheet(
            "QPlainTextEdit { background-color: #1E1E1E; color: #D4D4D4; "
            "border: 1px solid #555; border-radius: 3px; selection-background-color: #264F78; }"
        )
        self.script_input.setVisible(False)
        layout.addWidget(self.script_input)

        # 初始化 Vim 处理器
        self._vim_handler = VimHandler(self.script_input)
        self._vim_handler.mode_changed.connect(self._on_vim_mode_changed)

        layout.addWidget(QLabel("名称:"))
        self.name_input = QLineEdit(data.get("name", ""))
        self.name_input.setPlaceholderText("如：查询厂商代码")
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("帧内容 (十六进制，支持空格):"))
        self.frame_input = QLineEdit(data.get("frame_hex", ""))
        self.frame_input.setPlaceholderText("68 0E 00 00 00 00 ...")
        layout.addWidget(self.frame_input)

        layout.addWidget(QLabel("匹配规则 (HEX/ASCII，XX 为通配符):"))
        self.match_input = QLineEdit(data.get("match_rule", data.get("frame_hex", "")))
        self.match_input.setPlaceholderText("默认与帧内容相同，可修改为 XX 通配...")
        layout.addWidget(self.match_input)

        row = QHBoxLayout()
        row.addWidget(QLabel("匹配模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["HEX", "ASCII"])
        self.mode_combo.setCurrentText(data.get("match_mode", "HEX"))
        row.addWidget(self.mode_combo)
        row.addWidget(QLabel("超时 (ms):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(100, 600000)
        self.timeout_spin.setValue(data.get("timeout_ms", 2000))
        self.timeout_spin.setSingleStep(1000)
        row.addWidget(self.timeout_spin)
        row.addStretch()
        layout.addLayout(row)

        self.send_enabled = QCheckBox("发送帧")
        self.send_enabled.setChecked(data.get("send_enabled", True))
        self.send_enabled.toggled.connect(self._on_manual_toggle)
        layout.addWidget(self.send_enabled)

        self.match_enabled = QCheckBox("启用匹配")
        self.match_enabled.setChecked(data.get("match_enabled", True))
        self.match_enabled.toggled.connect(self._on_manual_toggle)
        layout.addWidget(self.match_enabled)

        layout.addWidget(QLabel("响应帧 (匹配成功后自动发送，留空则不响应):"))
        self.response_input = QLineEdit(data.get("response_frame", ""))
        self.response_input.setPlaceholderText("68 0E 00 00 00 00 ...")
        layout.addWidget(self.response_input)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 4px; padding: 4px 16px; font-weight: bold; }"
        )
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # 初始化 Lua 模式
        if nature == "Lua脚本":
            self.script_input.setPlainText(self._lua_script or "")
            self._apply_lua_mode(True)

    def _apply_lua_mode(self, is_lua: bool):
        """切换 Lua 脚本模式：隐藏/显示帧相关字段"""
        self.script_label.setVisible(is_lua)
        self.script_input.setVisible(is_lua)
        self.vim_mode_label.setVisible(is_lua)
        self._vim_help_label.setVisible(is_lua)
        # 隐藏/显示帧相关字段
        self.frame_input.setVisible(not is_lua)
        self.frame_input.parent()  # label 也需要隐藏
        for widget in self.findChildren(QLabel):
            if "帧内容" in widget.text() or "匹配规则" in widget.text() or "匹配模式" in widget.text():
                widget.setVisible(not is_lua)
            if "响应帧" in widget.text():
                widget.setVisible(not is_lua)
        self.match_input.setVisible(not is_lua)
        self.mode_combo.setVisible(not is_lua)
        self.send_enabled.setVisible(not is_lua)
        self.match_enabled.setVisible(not is_lua)
        self.response_input.setVisible(not is_lua)
        # Lua 模式下禁用超时微调（使用脚本内部等待）
        self.timeout_spin.setVisible(not is_lua)
        for widget in self.findChildren(QLabel):
            if "超时" in widget.text():
                widget.setVisible(not is_lua)

    def _on_vim_mode_changed(self, mode_text: str):
        """更新 Vim 模式指示器"""
        if mode_text == "INSERT":
            self.vim_mode_label.setText("-- INSERT --")
            self.vim_mode_label.setStyleSheet(
                "QLabel { color: #1E1E1E; background-color: #4FC3F7; padding: 1px 8px; "
                "border-radius: 2px; font-size: 11px; font-weight: bold; font-family: Consolas; }"
            )
        elif mode_text == "NORMAL":
            self.vim_mode_label.setText("-- NORMAL --")
            self.vim_mode_label.setStyleSheet(
                "QLabel { color: #FFFFFF; background-color: #616161; padding: 1px 8px; "
                "border-radius: 2px; font-size: 11px; font-weight: bold; font-family: Consolas; }"
            )
        elif mode_text == "VISUAL":
            self.vim_mode_label.setText("-- VISUAL --")
            self.vim_mode_label.setStyleSheet(
                "QLabel { color: #1E1E1E; background-color: #FFB74D; padding: 1px 8px; "
                "border-radius: 2px; font-size: 11px; font-weight: bold; font-family: Consolas; }"
            )
        elif mode_text.startswith(":"):
            self.vim_mode_label.setText(mode_text)
            self.vim_mode_label.setStyleSheet(
                "QLabel { color: #FFFFFF; background-color: #333333; padding: 1px 8px; "
                "border-radius: 2px; font-size: 11px; font-weight: bold; font-family: Consolas; }"
            )

    def _on_manual_toggle(self):
        """用户手动切换发送/匹配复选框时，同步性质下拉为「自定义」"""
        send = self.send_enabled.isChecked()
        match = self.match_enabled.isChecked()
        if send and match:
            current = self.nature_combo.currentText()
            if current not in ("发送帧", "自定义"):
                self.nature_combo.blockSignals(True)
                self.nature_combo.setCurrentText("发送帧")
                self.nature_combo.blockSignals(False)
        elif not send and not match:
            current = self.nature_combo.currentText()
            if current not in ("纯等待", "自定义"):
                self.nature_combo.blockSignals(True)
                self.nature_combo.setCurrentText("纯等待")
                self.nature_combo.blockSignals(False)

    def _on_ok(self):
        name = self.name_input.text().strip()
        frame = self.frame_input.text().strip()
        nature = self.nature_combo.currentText()
        send_enabled = self.send_enabled.isChecked()
        match_enabled = self.match_enabled.isChecked()
        is_lua = (nature == "Lua脚本")
        if not name:
            QMessageBox.warning(self, "输入错误", "名称不能为空")
            return
        if is_lua:
            script = self.script_input.toPlainText().strip()
            if not script:
                QMessageBox.warning(self, "输入错误", "Lua 脚本不能为空")
                return
            if not LUA_AVAILABLE:
                QMessageBox.warning(self, "依赖缺失", "lupa 库未安装，请运行: pip install lupa")
                return
        else:
            script = ""
            if send_enabled and not frame:
                QMessageBox.warning(self, "输入错误", "发送帧模式下帧内容不能为空")
                return
        self._result = {
            "name": name,
            "frame_hex": frame if not is_lua else "",
            "match_rule": self.match_input.text().strip(),
            "match_mode": self.mode_combo.currentText(),
            "timeout_ms": self.timeout_spin.value(),
            "send_enabled": send_enabled if not is_lua else False,
            "match_enabled": match_enabled if not is_lua else False,
            "response_frame": self.response_input.text().strip(),
            "persistent": nature == "后台监听",
            "is_lua_script": is_lua,
            "script": script,
        }
        self.accept()

    def get_result(self) -> Optional[Dict[str, Any]]:
        return self._result


class TestPlanWidget(QWidget):
    """测试方案页面Widget"""

    # 当帧被添加到测试方案时发出（供外部日志或联动）
    item_added = Signal(str, str)  # name, frame_hex

    def __init__(self, parent=None, file_path: Optional[Path] = None):
        super().__init__(parent)
        self._file_path = file_path or TEST_PLAN_PATH
        self._items: List[Dict[str, Any]] = []
        self._serial_worker = None
        self._current_test_index: int = -1
        self._testing: bool = False
        self._stop_requested: bool = False
        self._wait_timer: QTimer = None
        self._waiting_for_response: bool = False
        self._any_frame_received: bool = False
        self._test_start_time: Optional[datetime] = None  # 测试开始时间
        self._test_end_time: Optional[datetime] = None    # 测试结束时间
        self._test_vars: Dict[str, Any] = {}              # Lua 脚本共享变量
        self._lua_engine = None                           # 当前运行的 Lua 引擎
        self.setup_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # ---- 顶部按钮工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_add = QPushButton("添加")
        self.btn_add.setToolTip("手动添加测试项")
        self.btn_add.clicked.connect(self._on_add_item)
        toolbar.addWidget(self.btn_add)

        self.btn_del = QPushButton("删除")
        self.btn_del.setToolTip("删除选中的测试项")
        self.btn_del.clicked.connect(self._on_delete_item)
        toolbar.addWidget(self.btn_del)

        self.btn_up = QPushButton("上移")
        self.btn_up.setToolTip("将选中项上移")
        self.btn_up.clicked.connect(self._on_move_up)
        toolbar.addWidget(self.btn_up)

        self.btn_down = QPushButton("下移")
        self.btn_down.setToolTip("将选中项下移")
        self.btn_down.clicked.connect(self._on_move_down)
        toolbar.addWidget(self.btn_down)

        toolbar.addSpacing(8)

        self.btn_clear_bg = QPushButton("清空后台")
        self.btn_clear_bg.setToolTip("清除所有后台监听项的匹配计数和状态")
        self.btn_clear_bg.clicked.connect(self._on_clear_background)
        self.btn_clear_bg.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; border-radius: 3px; padding: 3px 10px; }"
        )
        toolbar.addWidget(self.btn_clear_bg)

        toolbar.addSpacing(8)

        self.lbl_bg_status = QLabel("后台: 0 项 | 匹配: 0 次")
        self.lbl_bg_status.setStyleSheet(
            "QLabel { background-color: #E8F5E9; border: 1px solid #A5D6A7; border-radius: 3px; "
            "padding: 4px 10px; font-weight: bold; color: #2E7D32; font-size: 12px; }"
        )
        toolbar.addWidget(self.lbl_bg_status)

        self.btn_edit_item = QPushButton("编辑选中")
        self.btn_edit_item.setToolTip("编辑当前选中行的测试项")
        self.btn_edit_item.clicked.connect(self._on_edit_item)
        toolbar.addWidget(self.btn_edit_item)

        toolbar.addSpacing(12)

        self.btn_start = QPushButton("开始测试")
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 14px; font-weight: bold; }"
        )
        self.btn_start.clicked.connect(self._on_start_test)
        toolbar.addWidget(self.btn_start)

        self.btn_stop = QPushButton("停止测试")
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; border-radius: 3px; padding: 4px 14px; font-weight: bold; }"
        )
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop_test)
        toolbar.addWidget(self.btn_stop)

        self.chk_stop_on_fail = QCheckBox("失败时停止")
        self.chk_stop_on_fail.setChecked(True)
        self.chk_stop_on_fail.setStyleSheet(
            "QCheckBox { spacing: 6px; padding: 4px 10px; background-color: #E3F2FD; "
            "border: 1px solid #90CAF9; border-radius: 4px; font-weight: bold; color: #1565C0; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
            "QCheckBox::indicator:checked { background-color: #1565C0; border: 2px solid #1565C0; }"
            "QCheckBox::indicator:unchecked { background-color: #FFFFFF; border: 2px solid #90CAF9; }"
        )
        toolbar.addWidget(self.chk_stop_on_fail)

        toolbar.addStretch()

        self.btn_export = QPushButton("导出")
        self.btn_export.setToolTip("导出帧列表到 JSON")
        self.btn_export.clicked.connect(self._on_export)
        toolbar.addWidget(self.btn_export)

        self.btn_import = QPushButton("导入")
        self.btn_import.setToolTip("从 JSON 导入帧列表")
        self.btn_import.clicked.connect(self._on_import)
        toolbar.addWidget(self.btn_import)

        self.btn_clear_results = QPushButton("清空结果")
        self.btn_clear_results.setToolTip("清空所有测试结果和状态")
        self.btn_clear_results.clicked.connect(self._on_clear_results)
        toolbar.addWidget(self.btn_clear_results)

        self.btn_export_report = QPushButton("导出报告")
        self.btn_export_report.setToolTip("导出 Excel 测试报告")
        self.btn_export_report.clicked.connect(self._on_export_report)
        self.btn_export_report.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; border-radius: 3px; padding: 4px 12px; font-weight: bold; }"
        )
        toolbar.addWidget(self.btn_export_report)

        main_layout.addLayout(toolbar)

        # ---- 提示说明 ----
        hint_label = QLabel("提示：匹配规则中的 <b>XX</b> 表示通配符（不判断该字节），可直接双击编辑规则修改需要匹配的报文内容")
        hint_label.setStyleSheet("color: #666666; font-size: 12px; padding: 2px 4px;")
        main_layout.addWidget(hint_label)

        # ---- 测试项表格 ----
        self.table = ZoomableTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            "序号", "名称", "帧内容", "操作", "发送",
            "状态", "启用匹配", "匹配规则", "匹配模式", "测试结果", "超时(ms)", "响应帧"
        ])
        # 表格复选框样式
        self.table.setStyleSheet(
            "QTableWidget::item { padding: 4px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
            "QCheckBox::indicator:checked { background-color: #1565C0; border: 2px solid #1565C0; }"
            "QCheckBox::indicator:unchecked { background-color: #FFFFFF; border: 2px solid #B0BEC5; }"
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        # 默认列宽
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 50)
        self.table.setColumnWidth(4, 50)
        self.table.setColumnWidth(5, 60)
        self.table.setColumnWidth(6, 70)
        self.table.setColumnWidth(7, 180)
        self.table.setColumnWidth(8, 60)
        self.table.setColumnWidth(9, 60)
        self.table.setColumnWidth(10, 70)
        self.table.setColumnWidth(11, 180)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        table_font = QFont()
        table_font.setPointSize(8)
        self.table.setFont(table_font)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.itemChanged.connect(self._on_table_item_changed)
        main_layout.addWidget(self.table, 1)

        # ---- 日志输出区 ----
        log_group = QGroupBox("测试日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)
        from PySide6.QtWidgets import QPlainTextEdit
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(500)
        self.log_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.log_edit.customContextMenuRequested.connect(self._on_log_context_menu)
        log_font = QFont("Consolas", 9)
        self.log_edit.setFont(log_font)
        log_layout.addWidget(self.log_edit)
        main_layout.addWidget(log_group, 0)
        main_layout.setStretchFactor(log_group, 0)
        main_layout.setStretchFactor(self.table, 1)

        # ---- 超时定时器 ----
        self._wait_timer = QTimer(self)
        self._wait_timer.setSingleShot(True)
        self._wait_timer.timeout.connect(self._on_test_timeout)

        # 自动加载上次方案
        self._auto_load()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def set_serial_worker(self, worker):
        """设置串口工作线程"""
        self._serial_worker = worker
        if worker:
            worker.frame_received.connect(self._on_frame_received)
            worker.log_message.connect(self._on_serial_log)

    def add_item(self, name: str, frame_hex: str):
        """从外部添加测试项（如协议组帧页面）"""
        item = {
            "name": name or "未命名",
            "frame_hex": frame_hex,
            "match_rule": frame_hex,
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False,
            "match_count": 0,
            "test_result": "未测",
            "status": "待测",
        }
        self._items.append(item)
        self._refresh_table()
        self._log(f"[添加] {item['name']}: {self._fmt_hex(item['frame_hex'])}")
        self.item_added.emit(item["name"], item["frame_hex"])
        self._auto_save()
        self._update_bg_status()

    def clear(self):
        """清空所有测试项"""
        self._stop_test()
        self._items.clear()
        self._refresh_table()
        self.log_edit.clear()

    # ------------------------------------------------------------------
    # 表格刷新与控件绑定
    # ------------------------------------------------------------------
    def _refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            is_lua = item.get("is_lua_script", False)
            persistent = item.get("persistent", False)
            # 序号（不可编辑）
            no_item = QTableWidgetItem(str(row + 1))
            no_item.setFlags(no_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, no_item)
            # 名称
            self.table.setItem(row, 1, QTableWidgetItem(item["name"]))
            # 帧内容
            if is_lua:
                script_preview = item.get("script", "")[:60].replace("\n", " ")
                frame_text = f"[Lua] {script_preview}..."
            else:
                frame_text = self._fmt_hex(item["frame_hex"])
            self.table.setItem(row, 2, QTableWidgetItem(frame_text))
            # 操作按钮
            if is_lua:
                send_btn = QPushButton("Lua")
                send_btn.setStyleSheet(
                    "QPushButton { background-color: #9C27B0; color: white; border-radius: 2px; padding: 1px 4px; font-size: 11px; }"
                )
            elif persistent:
                send_btn = QPushButton("后台")
                send_btn.setStyleSheet(
                    "QPushButton { background-color: #4CAF50; color: white; border-radius: 2px; padding: 1px 4px; font-size: 11px; }"
                )
            else:
                send_btn = QPushButton("发送" if item.get("send_enabled", True) else "等待")
                send_btn.setStyleSheet(
                    "QPushButton { background-color: #2196F3; color: white; border-radius: 2px; padding: 1px 4px; font-size: 11px; }"
                )
            send_btn.clicked.connect(lambda checked=False, r=row: self._on_send_single(r))
            self.table.setCellWidget(row, 3, send_btn)
            # 发送（使用复选框项）
            send_chk = QTableWidgetItem()
            if persistent or is_lua:
                send_chk.setFlags(send_chk.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                send_chk.setCheckState(Qt.CheckState.Unchecked)
            else:
                send_chk.setFlags(send_chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                send_chk.setCheckState(
                    Qt.CheckState.Checked if item.get("send_enabled", True) else Qt.CheckState.Unchecked
                )
            self.table.setItem(row, 4, send_chk)
            # 状态（不可编辑）
            if persistent:
                mc = item.get("match_count", 0)
                status_text = f"监听中({mc})" if mc else "监听中"
            else:
                status_text = item.get("status", "待测")
            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._set_status_style(status_item, status_text)
            self.table.setItem(row, 5, status_item)
            # 启用匹配（使用复选框项）
            chk_item = QTableWidgetItem()
            if persistent:
                chk_item.setFlags(chk_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                chk_item.setCheckState(Qt.CheckState.Checked)
            else:
                chk_item.setFlags(chk_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                chk_item.setCheckState(
                    Qt.CheckState.Checked if item.get("match_enabled", True) else Qt.CheckState.Unchecked
                )
            self.table.setItem(row, 6, chk_item)
            # 匹配规则（可编辑，显示带空格的 hex）
            rule_item = QTableWidgetItem(self._fmt_hex(item.get("match_rule", "")))
            rule_item.setFlags(rule_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 7, rule_item)
            # 匹配模式
            mode_combo = QComboBox()
            mode_combo.addItems(["HEX", "ASCII"])
            mode_combo.setCurrentText(item.get("match_mode", "HEX"))
            mode_combo.currentTextChanged.connect(lambda text, r=row: self._on_match_mode_changed(r, text))
            self.table.setCellWidget(row, 8, mode_combo)
            # 测试结果（不可编辑，只设置文字颜色）
            if persistent:
                mc = item.get("match_count", 0)
                result_text = f"匹配: {mc}" if mc > 0 else "监听中"
            else:
                result_text = item.get("test_result", "未测")
            result_item = QTableWidgetItem(result_text)
            result_item.setFlags(result_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._set_result_style(result_item, result_text)
            self.table.setItem(row, 9, result_item)
            # 超时
            spin = QSpinBox()
            spin.setRange(100, 600000)
            spin.setValue(item.get("timeout_ms", 2000))
            spin.setSingleStep(1000)
            if persistent:
                spin.setEnabled(False)
            spin.valueChanged.connect(lambda val, r=row: self._on_timeout_changed(r, val))
            self.table.setCellWidget(row, 10, spin)
            # 响应帧（保留原始内容，方便查看标记）
            resp_item = QTableWidgetItem(item.get("response_frame", ""))
            resp_item.setFlags(resp_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 11, resp_item)
        self.table.blockSignals(False)

    def _set_status_style(self, item: QTableWidgetItem, status: str):
        if status == "测试中":
            item.setForeground(QColor("#FF9800"))
        elif status == "待测":
            item.setForeground(QColor("#666666"))
        elif status == "已测试":
            item.setForeground(QColor("#1565C0"))
        elif "监听中" in status:
            item.setForeground(QColor("#2E7D32"))
        else:
            item.setForeground(QColor("#000000"))

    def _set_result_style(self, item: QTableWidgetItem, result: str):
        """设置测试结果文字颜色"""
        color_map = {
            "通过": "#008800",   # 绿色
            "失败": "#CC0000",   # 红色
            "超时": "#FF6600",   # 橙色
            "延时到": "#4CAF50", # 绿色
            "未测": "#999999",   # 灰色
            "监听中": "#2E7D32",
        }
        if "匹配:" in result:
            item.setForeground(QColor("#2E7D32"))
        else:
            item.setForeground(QColor(color_map.get(result, "#000000")))

    # ------------------------------------------------------------------
    # 表格控件事件
    # ------------------------------------------------------------------
    def _on_table_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._items):
            return
        if col == 1:
            self._items[row]["name"] = item.text()
        elif col == 2:
            self._items[row]["frame_hex"] = item.text().replace(" ", "")
        elif col == 4:
            self._items[row]["send_enabled"] = (item.checkState() == Qt.CheckState.Checked)
            # 刷新操作按钮文字
            self._refresh_table()
        elif col == 6:
            self._items[row]["match_enabled"] = (item.checkState() == Qt.CheckState.Checked)
        elif col == 7:
            self._items[row]["match_rule"] = item.text().replace(" ", "")
        elif col == 11:
            self._items[row]["response_frame"] = item.text().replace(" ", "")
        self._auto_save()

    def _on_match_mode_changed(self, row: int, text: str):
        if 0 <= row < len(self._items):
            self._items[row]["match_mode"] = text
            self._auto_save()

    def _on_timeout_changed(self, row: int, val: int):
        if 0 <= row < len(self._items):
            self._items[row]["timeout_ms"] = val
            self._auto_save()

    # ------------------------------------------------------------------
    # 导出/导入
    # ------------------------------------------------------------------
    # 工具栏按钮
    # ------------------------------------------------------------------
    def _on_add_item(self):
        dlg = AddTestItemDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            if result:
                item = {
                    **result,
                    "match_count": 0,
                    "test_result": "未测",
                    "status": "待测",
                }
                self._items.append(item)
                self._refresh_table()
                if item.get("is_lua_script"):
                    self._log(f"[添加] {item['name']}: [Lua脚本]")
                else:
                    self._log(f"[添加] {item['name']}: {self._fmt_hex(item['frame_hex'])}")
                self._auto_save()
                self._update_bg_status()

    def _on_edit_item(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._items):
            QMessageBox.information(self, "提示", "请先选中要编辑的行")
            return
        dlg = AddTestItemDialog(item=self._items[row], parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            if result:
                self._items[row].update(result)
                self._log(f"[编辑] 第 {row + 1} 行: {result['name']}")
                self._refresh_table()
                self._auto_save()
                self._update_bg_status()

    def _on_clear_background(self):
        """清空所有后台监听项的匹配计数和状态"""
        count = 0
        for p in self._items:
            if p.get("persistent"):
                p["match_count"] = 0
                count += 1
        if count:
            self._log(f"[清空后台] 已清除 {count} 个后台项的匹配计数")
            self._refresh_table()
            self._auto_save()
            self._update_bg_status()
        else:
            QMessageBox.information(self, "提示", "当前没有后台监听项")

    def _on_delete_item(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的行")
            return
        for row in rows:
            if 0 <= row < len(self._items):
                name = self._items[row]["name"]
                del self._items[row]
                self._log(f"[删除] 第 {row + 1} 行: {name}")
        self._refresh_table()
        self._auto_save()
        self._update_bg_status()

    def _on_move_up(self):
        row = self.table.currentRow()
        if row > 0:
            self._items[row], self._items[row - 1] = self._items[row - 1], self._items[row]
            self._refresh_table()
            self.table.selectRow(row - 1)
            self._auto_save()

    def _on_move_down(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._items) - 1:
            self._items[row], self._items[row + 1] = self._items[row + 1], self._items[row]
            self._refresh_table()
            self.table.selectRow(row + 1)
            self._auto_save()

    def _on_clear_results(self):
        for item in self._items:
            item["test_result"] = "未测"
            item["status"] = "待测"
        self._refresh_table()
        self.log_edit.clear()
        self._log("[清空] 所有测试结果已重置")
        self._update_bg_status()

    # ------------------------------------------------------------------
    # 导出/导入
    # ------------------------------------------------------------------
    def _on_export(self):
        if not self._items:
            QMessageBox.information(self, "提示", "当前没有测试项可导出")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出测试方案", "test_plan.json", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            export_data = [
                {
                    "name": item["name"],
                    "frame_hex": item["frame_hex"],
                    "match_rule": item["match_rule"],
                    "match_mode": item["match_mode"],
                    "timeout_ms": item["timeout_ms"],
                    "send_enabled": item.get("send_enabled", True),
                    "match_enabled": item["match_enabled"],
                    "response_frame": item.get("response_frame", ""),
                    "persistent": item.get("persistent", False),
                    "is_lua_script": item.get("is_lua_script", False),
                    "script": item.get("script", ""),
                }
                for item in self._items
            ]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            self._log(f"[导出] 已保存 {len(export_data)} 项到 {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入测试方案", "", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                QMessageBox.warning(self, "导入失败", "文件格式错误：应为 JSON 数组")
                return
            imported = 0
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                item = {
                    "name": entry.get("name", "未命名"),
                    "frame_hex": entry.get("frame_hex", ""),
                    "match_rule": entry.get("match_rule", entry.get("frame_hex", "")),
                    "match_mode": entry.get("match_mode", "HEX"),
                    "timeout_ms": entry.get("timeout_ms", 2000),
                    "send_enabled": entry.get("send_enabled", True),
                    "match_enabled": entry.get("match_enabled", True),
                    "response_frame": entry.get("response_frame", ""),
                    "persistent": entry.get("persistent", False),
                    "is_lua_script": entry.get("is_lua_script", False),
                    "script": entry.get("script", ""),
                    "match_count": entry.get("match_count", 0),
                    "test_result": "未测",
                    "status": "待测",
                }
                self._items.append(item)
                imported += 1
            self._refresh_table()
            self._log(f"[导入] 已从 {path} 导入 {imported} 项")
            self._auto_save()
            self._update_bg_status()
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def _on_export_report(self):
        """导出 Excel 测试报告"""
        if not self._items:
            QMessageBox.warning(self, "警告", "测试方案为空，无法导出报告")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出测试报告", "测试报告.xlsx", "Excel文件 (*.xlsx)"
        )
        if not file_path:
            return

        try:
            from report.excel_reporter import ExcelReporter
            reporter = ExcelReporter()

            # 获取测试日志
            log_text = self.log_edit.toPlainText() if hasattr(self, 'log_edit') else ""

            # 计算测试时间
            start_time = getattr(self, '_test_start_time', None)
            end_time = getattr(self, '_test_end_time', None)

            reporter.export(
                file_path=file_path,
                test_items=self._items,
                test_log=log_text,
                test_start_time=start_time,
                test_end_time=end_time
            )
            self._log(f"[导出报告] 已导出到 {file_path}")
            QMessageBox.information(self, "成功", f"测试报告已导出到:\n{file_path}")
        except ImportError:
            QMessageBox.critical(self, "错误", "需要安装 openpyxl 库：pip install openpyxl")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ------------------------------------------------------------------
    # 单帧发送
    # ------------------------------------------------------------------
    def _on_send_single(self, row: int):
        if self._testing:
            QMessageBox.warning(self, "警告", "当前正在顺序测试中，请先停止测试")
            return
        if not self._serial_worker:
            QMessageBox.warning(self, "错误", "串口未初始化")
            return
        if not self._serial_worker.is_open():
            QMessageBox.warning(self, "错误", "串口未打开，请先打开串口")
            return
        if row < 0 or row >= len(self._items):
            return
        self._current_test_index = row
        item = self._items[row]
        self._run_single_test(row, item, sequential=False)

    # ------------------------------------------------------------------
    # 顺序测试控制
    # ------------------------------------------------------------------
    def _on_start_test(self):
        if not self._items:
            QMessageBox.information(self, "提示", "测试列表为空")
            return
        if not self._serial_worker:
            QMessageBox.warning(self, "错误", "串口未初始化")
            return
        if not self._serial_worker.is_open():
            QMessageBox.warning(self, "错误", "串口未打开，请先打开串口")
            return
        self._testing = True
        self._stop_requested = False
        self._test_start_time = datetime.now()  # 记录测试开始时间
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._current_test_index = 0
        # 重置后台监听计数，强制启用匹配
        for p in self._items:
            if p.get("persistent"):
                p["match_count"] = 0
                p["match_enabled"] = True
        self._log("=" * 40)
        self._log("[测试开始] 顺序执行测试项...")
        self._update_bg_status()
        # 重置 Lua 测试变量
        self._test_vars = {}
        # 列出后台监听项
        bg_items = [f"#{i+1} {p['name']}" for i, p in enumerate(self._items) if p.get("persistent")]
        if bg_items:
            self._log(f"[后台监听] 已激活: {', '.join(bg_items)}")
        bg_no_match = [f"#{i+1} {p['name']}" for i, p in enumerate(self._items) if p.get("persistent") and not p.get("match_enabled", True)]
        if bg_no_match:
            self._log(f"[后台监听] 警告: 已强制启用匹配: {', '.join(bg_no_match)}")
        self._refresh_table()
        self._execute_next()

    def _on_stop_test(self):
        self._stop_requested = True
        if self._wait_timer and self._wait_timer.isActive():
            self._wait_timer.stop()
        # 停止正在运行的 Lua 引擎
        if self._lua_engine:
            self._lua_engine.request_stop()
            self._log("[Lua停止] 已请求停止脚本执行")
        self._testing = False
        self._waiting_for_response = False
        self._any_frame_received = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if 0 <= self._current_test_index < len(self._items):
            self._items[self._current_test_index]["status"] = "待测"
            self._refresh_table_row(self._current_test_index)
        # 停用后台监听项状态刷新
        for p in self._items:
            if p.get("persistent"):
                p["status"] = "待测"
        self._refresh_table()
        self._log("[测试停止] 用户手动停止")
        self._update_bg_status()

    def _execute_next(self):
        if self._stop_requested:
            return
        while self._current_test_index < len(self._items):
            item = self._items[self._current_test_index]
            if item.get("persistent", False):
                self._current_test_index += 1
                continue
            break
        if self._current_test_index >= len(self._items):
            self._finish_test()
            return
        item = self._items[self._current_test_index]
        self._run_single_test(self._current_test_index, item, sequential=True)

    def _finish_test(self):
        self._testing = False
        self._test_end_time = datetime.now()  # 记录测试结束时间
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        # 输出后台监听统计
        for p in self._items:
            if p.get("persistent") and p.get("match_count", 0) > 0:
                self._log(f"[后台统计] {p['name']}: 匹配 {p['match_count']} 次")
        self._log("[测试完成] 所有测试项执行结束")
        self._log("=" * 40)
        self._update_bg_status()

    def _run_single_test(self, row: int, item: Dict[str, Any], sequential: bool = False):
        item["status"] = "测试中"
        item["test_result"] = "未测"
        self._refresh_table_row(row)

        # Lua 脚本项：在子线程中执行
        if item.get("is_lua_script", False):
            self._run_lua_script(row, item)
            return

        send_enabled = item.get("send_enabled", True)
        frame = item["frame_hex"].replace(" ", "")
        timeout = item.get("timeout_ms", 2000)
        if send_enabled:
            self._log(f"[{row + 1}] 发送 -> {item['name']}: {self._fmt_hex(frame)} (超时 {timeout}ms)")
        else:
            self._log(f"[{row + 1}] 等待 -> {item['name']} (仅监听，超时 {timeout}ms)")
        self._waiting_for_response = True
        self._any_frame_received = False
        if send_enabled:
            self._serial_worker.send_hex_string(frame)
        self._wait_timer.start(timeout)

    def _on_test_timeout(self):
        if not self._waiting_for_response:
            return
        self._waiting_for_response = False
        row = self._current_test_index
        if 0 <= row < len(self._items):
            item = self._items[row]
            item["status"] = "已测试"
            is_pure_wait = not item.get("send_enabled", True) and not item.get("match_enabled", True)
            if is_pure_wait:
                item["test_result"] = "延时到"
                self._log(f"[{row + 1}] 结果 -> 延时到 (纯等待 {item.get('timeout_ms', 2000)}ms)")
            elif self._any_frame_received:
                item["test_result"] = "失败"
                self._log(f"[{row + 1}] 结果 -> 失败 (超时时间内收到帧但规则均不匹配)")
            else:
                item["test_result"] = "超时"
                self._log(f"[{row + 1}] 结果 -> 超时 (>{item.get('timeout_ms', 2000)}ms 无响应)")
            self._refresh_table_row(row)
            if self._testing and self.chk_stop_on_fail.isChecked() and item["test_result"] == "失败":
                self._log("[测试停止] 失败时停止已启用")
                self._finish_test()
                return
        self._any_frame_received = False
        if self._testing:
            self._current_test_index += 1
            self._execute_next()

    def _run_lua_script(self, row: int, item: Dict[str, Any]):
        """在子线程中执行 Lua 脚本"""
        if not LUA_AVAILABLE:
            self._log(f"[{row + 1}] Lua错误 -> lupa 库未安装，请运行: pip install lupa")
            item["test_result"] = "失败"
            item["status"] = "已测试"
            self._refresh_table_row(row)
            if self._testing:
                self._current_test_index += 1
                self._execute_next()
            return
        script = item.get("script", "")
        if not script:
            self._log(f"[{row + 1}] Lua错误 -> 脚本内容为空")
            item["test_result"] = "失败"
            item["status"] = "已测试"
            self._refresh_table_row(row)
            if self._testing:
                self._current_test_index += 1
                self._execute_next()
            return
        self._log(f"[{row + 1}] Lua -> 执行脚本: {item['name']}")
        self._lua_engine = LuaScriptEngine()
        self._lua_engine.set_serial_worker(self._serial_worker)
        self._lua_engine.set_test_vars(self._test_vars)
        # 日志信号连接到测试日志
        self._lua_engine.log_signal.connect(self._on_lua_log)
        # 完成信号
        self._lua_engine.finished_signal.connect(
            lambda ok, result: self._on_lua_finished(row, ok, result)
        )
        # 设置脚本最大执行时间超时（使用 item 的 timeout_ms）
        timeout = item.get("timeout_ms", 60000)
        self._wait_timer.start(timeout)
        self._wait_timer.timeout.connect(self._on_lua_timeout)
        # 在子线程中运行
        t = threading.Thread(target=self._lua_engine.run, args=(script,), daemon=True)
        t.start()

    def _on_lua_log(self, msg: str):
        """将 Lua 引擎日志输出到测试日志"""
        self.log_edit.appendPlainText(msg)

    def _on_lua_timeout(self):
        """Lua 脚本超时"""
        if self._lua_engine:
            self._lua_engine.request_stop()
            self._log(f"[Lua超时] 脚本执行超过最大时间，已请求停止")

    def _on_lua_finished(self, row: int, success: bool, result: str):
        """Lua 脚本执行完成回调"""
        # 停止超时计时器
        if self._wait_timer and self._wait_timer.isActive():
            self._wait_timer.stop()
            try:
                self._wait_timer.timeout.disconnect(self._on_lua_timeout)
            except RuntimeError:
                pass
        if 0 <= row < len(self._items):
            item = self._items[row]
            item["status"] = "已测试"
            if success:
                item["test_result"] = "通过"
                self._log(f"[{row + 1}] Lua -> 完成: {result}")
            else:
                item["test_result"] = "失败"
                self._log(f"[{row + 1}] Lua -> 失败: {result}")
            # 同步 Lua 测试变量
            if self._lua_engine:
                self._test_vars = self._lua_engine._test_vars
            self._refresh_table_row(row)
            if self._testing and self.chk_stop_on_fail.isChecked() and item["test_result"] == "失败":
                self._log("[测试停止] 失败时停止已启用")
                self._finish_test()
                return
        self._lua_engine = None
        if self._testing:
            self._current_test_index += 1
            self._execute_next()

    def _on_serial_log(self, msg: str):
        """将串口收发日志同步到测试日志，方便调试等待场景"""
        if "[接收]" in msg or "[发送]" in msg or "[接收(容错)]" in msg:
            self._log(msg)

    def _check_persistent_items(self, received_hex: str):
        """检查所有后台监听项，匹配则自动响应"""
        check_count = 0
        match_count = 0
        for pi_idx, pi in enumerate(self._items):
            if not pi.get("persistent", False):
                continue
            if not pi.get("match_enabled", True):
                self._log(f"[后台 {pi_idx + 1}] 跳过 -> {pi['name']}: 未启用匹配")
                continue
            rule = pi.get("match_rule", "")
            if not rule:
                self._log(f"[后台 {pi_idx + 1}] 跳过 -> {pi['name']}: 匹配规则为空")
                continue
            check_count += 1
            mode = pi.get("match_mode", "HEX")
            if self._match_frame(rule, received_hex, mode):
                match_count += 1
                self._log(f"[后台 {pi_idx + 1}] 匹配 -> {pi['name']}: {self._fmt_hex(received_hex)}")
                resp_raw = pi.get("response_frame", "")
                resp_frame = process_response_frame(resp_raw)
                if resp_frame and self._serial_worker and self._serial_worker.is_open():
                    self._log(f"[后台 {pi_idx + 1}] 响应 -> {self._fmt_hex(resp_frame)}")
                    self._serial_worker.send_hex_string(resp_frame)
                else:
                    self._log(f"[后台 {pi_idx + 1}] 未响应 -> 响应帧为空或串口未打开")
                pi["match_count"] = pi.get("match_count", 0) + 1
                self._refresh_table_row(pi_idx)
                self._update_bg_status()
            else:
                self._log(f"[后台 {pi_idx + 1}] 不匹配 -> {pi['name']} | 规则:{self._fmt_hex(rule)} ≠ 收到:{self._fmt_hex(received_hex)}")
        if check_count > 0 and match_count == 0:
            self._log(f"[后台] 已检查 {check_count} 个后台项，均不匹配")

    def _on_frame_received(self, frame: bytes):
        received_hex = frame.hex().upper()

        # ---- 当前步骤匹配 ----
        if self._waiting_for_response:
            row = self._current_test_index
            if 0 <= row < len(self._items):
                item = self._items[row]
                self._any_frame_received = True
                self._log(f"[{row + 1}] 接收 <- {self._fmt_hex(received_hex)}")

                if not item.get("match_enabled", True):
                    # 未启用匹配
                    if item.get("send_enabled", True):
                        # 发送帧模式：收到任意响应即通过
                        self._waiting_for_response = False
                        if self._wait_timer and self._wait_timer.isActive():
                            self._wait_timer.stop()
                        item["test_result"] = "通过"
                        item["status"] = "已测试"
                        self._log(f"[{row + 1}] 结果 -> 通过 (未启用匹配)")
                        resp_raw = item.get("response_frame", "")
                        resp_frame = process_response_frame(resp_raw)
                        if resp_frame:
                            self._log(f"[{row + 1}] 响应 -> {self._fmt_hex(resp_frame)}")
                            self._serial_worker.send_hex_string(resp_frame)
                        self._refresh_table_row(row)
                        if self._testing:
                            self._current_test_index += 1
                            self._execute_next()
                        return
                    else:
                        # 纯等待模式：忽略帧，仅靠超时结束
                        self._log(f"[{row + 1}] 忽略 -> 纯等待模式，不匹配帧")
                        if self._testing:
                            self._check_persistent_items(received_hex)
                        return

                mode = item.get("match_mode", "HEX")
                rule = item.get("match_rule", "")
                if self._match_frame(rule, received_hex, mode):
                    # 匹配成功：停止等待，标记通过
                    self._waiting_for_response = False
                    if self._wait_timer and self._wait_timer.isActive():
                        self._wait_timer.stop()
                    item["test_result"] = "通过"
                    item["status"] = "已测试"
                    self._log(f"[{row + 1}] 结果 -> 通过")
                    resp_raw = item.get("response_frame", "")
                    resp_frame = process_response_frame(resp_raw)
                    if resp_frame:
                        self._log(f"[{row + 1}] 响应 -> {self._fmt_hex(resp_frame)}")
                        self._serial_worker.send_hex_string(resp_frame)
                    self._refresh_table_row(row)
                    if self._testing:
                        self._current_test_index += 1
                        self._execute_next()
                    return
                else:
                    # 匹配失败 → 转到后台任务检查
                    self._log(f"[{row + 1}] 不匹配 -> 转到后台检查...")
                    if self._testing:
                        self._check_persistent_items(received_hex)
                    return

        # 无等待步骤时，检查后台任务
        if self._testing:
            self._check_persistent_items(received_hex)

    # ------------------------------------------------------------------
    # 匹配引擎
    # ------------------------------------------------------------------
    @staticmethod
    def _match_frame(rule: str, actual: str, mode: str) -> bool:
        """匹配响应帧

        Args:
            rule: 匹配规则，XX 为通配符
            actual: 实际接收到的帧（HEX 字符串无空格）
            mode: "HEX" 或 "ASCII"
        """
        if mode == "HEX":
            expected = rule.replace(" ", "").upper()
            actual_clean = actual.replace(" ", "").upper()
        else:
            expected = rule
            actual_clean = actual

        if len(expected) != len(actual_clean):
            return False

        i = 0
        while i < len(expected):
            if i + 1 < len(expected) and expected[i] == "X" and expected[i + 1] == "X":
                i += 2
            else:
                if expected[i] != actual_clean[i]:
                    return False
                i += 1
        return True

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _refresh_table_row(self, row: int):
        if row < 0 or row >= len(self._items):
            return
        item = self._items[row]
        self.table.blockSignals(True)
        # 序号
        self.table.item(row, 0).setText(str(row + 1))
        # 名称
        self.table.item(row, 1).setText(item["name"])
        # 帧内容
        self.table.item(row, 2).setText(self._fmt_hex(item["frame_hex"]))
        # 发送
        send_chk = self.table.item(row, 4)
        send_chk.setCheckState(
            Qt.CheckState.Checked if item.get("send_enabled", True) else Qt.CheckState.Unchecked
        )
        persistent = item.get("persistent", False)
        # 状态
        status_item = self.table.item(row, 5)
        if persistent:
            mc = item.get("match_count", 0)
            status_text = f"监听中({mc})" if mc else "监听中"
        else:
            status_text = item.get("status", "待测")
        status_item.setText(status_text)
        self._set_status_style(status_item, status_text)
        # 启用匹配
        chk_item = self.table.item(row, 6)
        chk_item.setCheckState(
            Qt.CheckState.Checked if item.get("match_enabled", True) else Qt.CheckState.Unchecked
        )
        # 匹配规则（带空格的 hex）
        self.table.item(row, 7).setText(self._fmt_hex(item.get("match_rule", "")))
        # 测试结果（带颜色）
        result_item = self.table.item(row, 9)
        if persistent:
            mc = item.get("match_count", 0)
            result_text = f"匹配: {mc}" if mc > 0 else "监听中"
        else:
            result_text = item.get("test_result", "未测")
        result_item.setText(result_text)
        self._set_result_style(result_item, result_text)
        # 响应帧（保留原始内容，方便查看标记）
        self.table.item(row, 11).setText(item.get("response_frame", ""))
        self.table.blockSignals(False)

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_edit.appendPlainText(f"[{ts}] {msg}")

    def _update_bg_status(self):
        """更新后台状态标签"""
        bg_items = [p for p in self._items if p.get("persistent")]
        total_matches = sum(p.get("match_count", 0) for p in bg_items)
        count = len(bg_items)
        if count:
            self.lbl_bg_status.setText(f"后台: {count} 项 | 匹配: {total_matches} 次")
            self.lbl_bg_status.setStyleSheet(
                "QLabel { background-color: #E8F5E9; border: 1px solid #A5D6A7; border-radius: 3px; "
                "padding: 4px 10px; font-weight: bold; color: #2E7D32; font-size: 12px; }"
            )
        else:
            self.lbl_bg_status.setText("后台: 0 项 | 匹配: 0 次")
            self.lbl_bg_status.setStyleSheet(
                "QLabel { background-color: #F5F5F5; border: 1px solid #BDBDBD; border-radius: 3px; "
                "padding: 4px 10px; font-weight: bold; color: #757575; font-size: 12px; }"
            )

    def _on_log_context_menu(self, pos):
        """日志区域右键菜单"""
        menu = QMenu(self)
        clear_action = menu.addAction("清空日志")
        copy_action = menu.addAction("复制")
        select_all_action = menu.addAction("全选")
        action = menu.exec(self.log_edit.mapToGlobal(pos))
        if action == clear_action:
            self.log_edit.clear()
        elif action == copy_action:
            self.log_edit.copy()
        elif action == select_all_action:
            self.log_edit.selectAll()

    @staticmethod
    def _fmt_hex(hex_str: str) -> str:
        s = hex_str.replace(" ", "").upper()
        return " ".join(s[i:i + 2] for i in range(0, len(s), 2))

    def _stop_test(self):
        self._stop_requested = True
        if self._wait_timer and self._wait_timer.isActive():
            self._wait_timer.stop()
        self._testing = False
        self._waiting_for_response = False

    # ------------------------------------------------------------------
    # 自动持久化
    # ------------------------------------------------------------------
    def set_file_path(self, file_path: Optional[Path] = None):
        """动态更新配置文件路径并重新加载"""
        self._file_path = file_path or TEST_PLAN_PATH
        self._items.clear()
        self._refresh_table()
        self._auto_load()

    def _auto_save(self):
        """自动保存当前方案到配置指定的文件"""
        try:
            export_data = [
                {
                    "name": item["name"],
                    "frame_hex": item["frame_hex"],
                    "match_rule": item["match_rule"],
                    "match_mode": item["match_mode"],
                    "timeout_ms": item["timeout_ms"],
                    "send_enabled": item.get("send_enabled", True),
                    "match_enabled": item["match_enabled"],
                    "response_frame": item.get("response_frame", ""),
                    "persistent": item.get("persistent", False),
                    "is_lua_script": item.get("is_lua_script", False),
                    "script": item.get("script", ""),
                }
                for item in self._items
            ]
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[测试方案自动保存失败] {e}")

    def _auto_load(self):
        """自动加载配置指定路径的方案"""
        if not self._file_path.exists():
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            self._items = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                item = {
                    "name": entry.get("name", "未命名"),
                    "frame_hex": entry.get("frame_hex", ""),
                    "match_rule": entry.get("match_rule", entry.get("frame_hex", "")),
                    "match_mode": entry.get("match_mode", "HEX"),
                    "timeout_ms": entry.get("timeout_ms", 2000),
                    "send_enabled": entry.get("send_enabled", True),
                    "match_enabled": entry.get("match_enabled", True),
                    "response_frame": entry.get("response_frame", ""),
                    "persistent": entry.get("persistent", False),
                    "is_lua_script": entry.get("is_lua_script", False),
                    "script": entry.get("script", ""),
                    "match_count": entry.get("match_count", 0),
                    "test_result": "未测",
                    "status": "待测",
                }
                self._items.append(item)
            self._refresh_table()
            self._log(f"[自动加载] 已从 {self._file_path.name} 加载 {len(self._items)} 项")
            self._update_bg_status()
        except Exception as e:
            print(f"[测试方案自动加载失败] {e}")
