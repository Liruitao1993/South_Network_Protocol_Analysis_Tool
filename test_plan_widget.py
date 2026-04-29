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

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QComboBox, QSpinBox, QMessageBox, QFileDialog, QTextEdit,
    QDialog, QLineEdit, QGroupBox, QMenu
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor

from gui_utils import apply_chinese_context_menus, setup_chinese_context_menu

# 自动持久化文件路径
TEST_PLAN_PATH = Path(__file__).parent / "test_plan.json"

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
        elif nature == "后台监听":
            self._set_nature_state(send=False, match=True, persistent=True)
        elif nature == "纯等待":
            self._set_nature_state(send=False, match=False, persistent=False)

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
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ---- 性质 ----
        row = QHBoxLayout()
        row.addWidget(QLabel("性质:"))
        self.nature_combo = QComboBox()
        self.nature_combo.addItems(["发送帧", "后台监听", "纯等待"])
        self.nature_combo.setCurrentText(nature)
        self.nature_combo.currentTextChanged.connect(self._apply_nature)
        nature_help = QLabel("发送帧→发后匹配置  后台→全时监听匹配回复  纯等待→忽略帧仅等超时")
        nature_help.setStyleSheet("color: #888; font-size: 11px;")
        row.addWidget(self.nature_combo)
        row.addWidget(nature_help)
        row.addStretch()
        layout.addLayout(row)

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
        if not name:
            QMessageBox.warning(self, "输入错误", "名称不能为空")
            return
        if send_enabled and not frame:
            QMessageBox.warning(self, "输入错误", "发送帧模式下帧内容不能为空")
            return
        self._result = {
            "name": name,
            "frame_hex": frame,
            "match_rule": self.match_input.text().strip(),
            "match_mode": self.mode_combo.currentText(),
            "timeout_ms": self.timeout_spin.value(),
            "send_enabled": send_enabled,
            "match_enabled": match_enabled,
            "response_frame": self.response_input.text().strip(),
            "persistent": nature == "后台监听",
        }
        self.accept()

    def get_result(self) -> Optional[Dict[str, Any]]:
        return self._result


class TestPlanWidget(QWidget):
    """测试方案页面Widget"""

    # 当帧被添加到测试方案时发出（供外部日志或联动）
    item_added = Signal(str, str)  # name, frame_hex

    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.table = QTableWidget()
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
            # 序号（不可编辑）
            no_item = QTableWidgetItem(str(row + 1))
            no_item.setFlags(no_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, no_item)
            # 名称
            self.table.setItem(row, 1, QTableWidgetItem(item["name"]))
            # 帧内容
            self.table.setItem(row, 2, QTableWidgetItem(self._fmt_hex(item["frame_hex"])))
            persistent = item.get("persistent", False)
            # 操作按钮
            if persistent:
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
            if persistent:
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
    def _auto_save(self):
        """自动保存当前方案到 test_plan.json"""
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
                }
                for item in self._items
            ]
            with open(TEST_PLAN_PATH, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[测试方案自动保存失败] {e}")

    def _auto_load(self):
        """自动加载上次保存的方案"""
        if not TEST_PLAN_PATH.exists():
            return
        try:
            with open(TEST_PLAN_PATH, "r", encoding="utf-8") as f:
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
                    "match_count": entry.get("match_count", 0),
                    "test_result": "未测",
                    "status": "待测",
                }
                self._items.append(item)
            self._refresh_table()
            self._log(f"[自动加载] 已从 {TEST_PLAN_PATH.name} 加载 {len(self._items)} 项")
            self._update_bg_status()
        except Exception as e:
            print(f"[测试方案自动加载失败] {e}")
