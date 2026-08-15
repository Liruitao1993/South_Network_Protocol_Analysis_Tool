"""报文工具组件

提供协议报文处理的常用工具：
- ASCII <-> HEX 转换
- HEX +/- 0x33（DLT645 协议偏移）
- 字节逆序 / 倒序+/-0x33 组合
- 报文 <-> Pn / Fn 转换（DLT645 数据标识符）
- 格式化：大小写、去空格、加空格、统计
- CRC / 校验和
- HEX <-> bitstring 转换
"""

import re
import crcmod
import crcmod.predefined
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QCheckBox, QGridLayout, QMessageBox, QGroupBox, QComboBox,
)


# CRC 算法（与协议解析器一致）
_crc24_func = crcmod.mkCrcFun(0x1800063, initCrc=0x000000, rev=True, xorOut=0x000000)
_crc32_func = crcmod.mkCrcFun(0x104C11DB7, initCrc=0x00000000, rev=True, xorOut=0xFFFFFFFF)


class MessageToolWidget(QWidget):
    """报文工具标签页 — 对齐截图布局（两行按钮 + 16进制复选框）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---------- 输入区 ----------
        input_header = QHBoxLayout()
        input_header.setContentsMargins(0, 0, 0, 0)
        input_header.addWidget(QLabel("输入"))
        self.hex_mode_cb = QCheckBox("16进制")
        self.hex_mode_cb.setChecked(True)
        self.hex_mode_cb.setToolTip("勾选时按十六进制解析输入；取消勾选时按纯文本(ASCII)解析")
        input_header.addWidget(self.hex_mode_cb)
        input_header.addStretch()
        layout.addLayout(input_header)

        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText(
            "输入十六进制报文，如：68 01 00 00 00 00 00 68 11 04 33 33 33 33 ..."
        )
        self.input_text.setMaximumHeight(100)
        layout.addWidget(self.input_text)

        # ---------- 操作按钮区 ----------
        layout.addWidget(QLabel("操作"))

        tools_grid = QGridLayout()
        tools_grid.setSpacing(6)

        # 第一行
        row = 0
        tools_grid.addWidget(self._btn("按字节倒序", self._byte_reverse), row, 0)
        tools_grid.addWidget(self._btn("+0x33H", self._hex_add_33), row, 1)
        tools_grid.addWidget(self._btn("倒序+0x33H", self._reverse_add_33), row, 2)
        tools_grid.addWidget(self._btn("ASCII→字符", self._hex_to_ascii), row, 3)
        tools_grid.addWidget(self._btn("字节长度", self._byte_length), row, 4)
        tools_grid.addWidget(self._btn("转大写", self._to_upper), row, 5)
        tools_grid.addWidget(self._btn("去空格", self._remove_spaces), row, 6)
        tools_grid.addWidget(self._btn("报文转Pn", self._msg_to_pn), row, 7)
        tools_grid.addWidget(self._btn("Pn转报文", self._pn_to_msg), row, 8)

        # 第二行
        row = 1
        tools_grid.addWidget(self._btn("和校验", self._checksum8), row, 0)
        tools_grid.addWidget(self._btn("-0x33H", self._hex_sub_33), row, 1)
        tools_grid.addWidget(self._btn("倒序-0x33H", self._reverse_sub_33), row, 2)
        tools_grid.addWidget(self._btn("字符→ASCII", self._ascii_to_hex), row, 3)
        tools_grid.addWidget(self._btn("字符个数", self._char_count), row, 4)
        tools_grid.addWidget(self._btn("转小写", self._to_lower), row, 5)
        tools_grid.addWidget(self._btn("字节间加空格", self._add_spaces), row, 6)
        tools_grid.addWidget(self._btn("报文转Fn", self._msg_to_fn), row, 7)
        tools_grid.addWidget(self._btn("Fn转报文", self._fn_to_msg), row, 8)

        layout.addLayout(tools_grid)

        # ---------- 扩展工具（CRC / bitstring 等） ----------
        ext_group = QGroupBox("扩展工具")
        ext_grid = QGridLayout(ext_group)
        ext_grid.setSpacing(6)

        ext_grid.addWidget(self._btn("HEX → bitstring", self._hex_to_bitstring), 0, 0)
        ext_grid.addWidget(self._btn("bitstring → HEX", self._bitstring_to_hex), 0, 1)
        ext_grid.addWidget(self._btn("字节正序", self._byte_normal), 0, 2)
        ext_grid.addWidget(self._btn("CRC-16 (698.45)", self._crc16_698), 0, 3)
        ext_grid.addWidget(self._btn("CRC-32 (新一代)", self._crc32_newgen), 0, 4)
        ext_grid.addWidget(self._btn("CRC-24 (新一代)", self._crc24_newgen), 1, 0)
        ext_grid.addWidget(self._btn("清空", self._clear_all), 1, 1)
        ext_grid.addWidget(self._btn("复制输出", self._copy_output), 1, 2)

        # 第三行：HEX→十进制（字节序选择）
        row = 2
        self.endian_combo = QComboBox()
        self.endian_combo.addItems(["小端(低字节在前)", "大端(高字节在前)"])
        self.endian_combo.setCurrentIndex(0)          # 默认小端，对齐本项目 9/11 协议小端惯例
        self.endian_combo.setFixedHeight(28)          # 与 _btn 高度一致
        self.endian_combo.setToolTip("HEX→十进制 时按此字节序解释字节序列")
        ext_grid.addWidget(self.endian_combo, row, 0)
        ext_grid.addWidget(self._btn("HEX→十进制", self._hex_to_decimal), row, 1)

        layout.addWidget(ext_group)

        # ---------- 输出区 ----------
        layout.addWidget(QLabel("输出"))
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(140)
        layout.addWidget(self.output_text)

        layout.addStretch()

    # ------------------------------------------------------------- helpers
    def _btn(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        btn.setFixedHeight(28)
        return btn

    def _parse_hex(self) -> list[int] | None:
        """从输入区解析十六进制字节列表，失败返回 None 并弹窗提示"""
        raw = self.input_text.toPlainText().strip()
        if not raw:
            QMessageBox.information(self, "提示", "请先输入报文")
            return None
        # 去除常见分隔符和前缀
        cleaned = raw.replace(",", " ").replace("0x", "").replace("0X", "").replace(" ", "")
        if len(cleaned) % 2 == 0 and all(c in '0123456789ABCDEFabcdef' for c in cleaned):
            tokens = [cleaned[i:i + 2] for i in range(0, len(cleaned), 2)]
        else:
            tokens = raw.split()
        try:
            return [int(t, 16) for t in tokens if t]
        except ValueError:
            QMessageBox.warning(self, "格式错误", "输入包含非十六进制字符，请检查")
            return None

    def _get_input_text(self) -> str:
        return self.input_text.toPlainText().strip()

    def _set_output(self, text: str):
        self.output_text.setPlainText(text)

    def _clear_all(self):
        self.input_text.clear()
        self.output_text.clear()

    def _copy_output(self):
        text = self.output_text.toPlainText()
        if text:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)

    # -------------------------------------------------------- 转换方法
    def _hex_to_ascii(self):
        """ASCII→字符：将 HEX 字节转为可读字符（不可打印显示为 .）"""
        data = self._parse_hex()
        if data is None:
            return
        chars = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
        self._set_output(chars)

    def _ascii_to_hex(self):
        """字符→ASCII：将文本转为 HEX"""
        raw = self._get_input_text()
        if not raw:
            QMessageBox.information(self, "提示", "请先输入文本")
            return
        hex_str = " ".join(f"{ord(c):02X}" for c in raw)
        self._set_output(hex_str)

    def _hex_add_33(self):
        """+0x33H：每个字节加 0x33（DLT645 数据加密 / Pn→报文）"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{(b + 0x33) & 0xFF:02X}" for b in data)
        self._set_output(result)

    def _hex_sub_33(self):
        """-0x33H：每个字节减 0x33（DLT645 数据解密 / 报文→Pn）"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{(b - 0x33) & 0xFF:02X}" for b in data)
        self._set_output(result)

    def _reverse_add_33(self):
        """倒序+0x33H：先按字节倒序，再每个字节+0x33"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{(b + 0x33) & 0xFF:02X}" for b in reversed(data))
        self._set_output(result)

    def _reverse_sub_33(self):
        """倒序-0x33H：先按字节倒序，再每个字节-0x33"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{(b - 0x33) & 0xFF:02X}" for b in reversed(data))
        self._set_output(result)

    def _byte_reverse(self):
        """按字节倒序：反转字节序列"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{b:02X}" for b in reversed(data))
        self._set_output(result)

    def _byte_normal(self):
        """字节正序：原样输出 HEX（不做反转，用于确认输入已是正序）"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{b:02X}" for b in data)
        self._set_output(result)

    def _hex_to_decimal(self):
        """HEX→十进制：按大端/小端字节序将输入字节序列解释为无符号整数"""
        data = self._parse_hex()
        if data is None:
            return
        little = "小端" in self.endian_combo.currentText()
        value = int.from_bytes(bytes(data), 'little' if little else 'big')
        self._set_output(
            f"十进制: {value}\n"
            f"十六进制: 0x{value:X}\n"
            f"字节序: {'小端(低字节在前)' if little else '大端(高字节在前)'}"
        )

    def _byte_length(self):
        """字节长度：统计 HEX 字节数"""
        data = self._parse_hex()
        if data is None:
            return
        self._set_output(str(len(data)))

    def _char_count(self):
        """字符个数：统计输入文本的字符数"""
        raw = self._get_input_text()
        if not raw:
            QMessageBox.information(self, "提示", "请先输入文本")
            return
        self._set_output(str(len(raw)))

    def _to_upper(self):
        """转大写：将 HEX 输出转为大写"""
        raw = self._get_input_text()
        if not raw:
            QMessageBox.information(self, "提示", "请先输入文本")
            return
        self._set_output(raw.upper())

    def _to_lower(self):
        """转小写：将 HEX 输出转为小写"""
        raw = self._get_input_text()
        if not raw:
            QMessageBox.information(self, "提示", "请先输入文本")
            return
        self._set_output(raw.lower())

    def _remove_spaces(self):
        """去空格：去除所有空格"""
        raw = self._get_input_text()
        if not raw:
            QMessageBox.information(self, "提示", "请先输入文本")
            return
        self._set_output(raw.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", ""))

    def _add_spaces(self):
        """字节间加空格：将连续 HEX 字符串按 2 字节插入空格"""
        raw = self._get_input_text().replace(" ", "").replace("\n", "").replace("\r", "")
        if not raw:
            QMessageBox.information(self, "提示", "请先输入文本")
            return
        # 清理 0x 前缀
        cleaned = raw.replace("0x", "").replace("0X", "")
        if len(cleaned) % 2 != 0:
            QMessageBox.warning(self, "格式错误", "HEX 字符串长度为奇数，无法按字节分割")
            return
        result = " ".join(cleaned[i:i + 2] for i in range(0, len(cleaned), 2))
        self._set_output(result.upper())

    def _msg_to_pn(self):
        """报文转Pn：DLT645 数据域解码，每个字节 -0x33"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{(b - 0x33) & 0xFF:02X}" for b in data)
        self._set_output(result)

    def _pn_to_msg(self):
        """Pn转报文：DLT645 数据域编码，每个字节 +0x33"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{(b + 0x33) & 0xFF:02X}" for b in data)
        self._set_output(result)

    def _msg_to_fn(self):
        """报文转Fn：DLT645 功能码解码，每个字节 -0x33"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{(b - 0x33) & 0xFF:02X}" for b in data)
        self._set_output(result)

    def _fn_to_msg(self):
        """Fn转报文：DLT645 功能码编码，每个字节 +0x33"""
        data = self._parse_hex()
        if data is None:
            return
        result = " ".join(f"{(b + 0x33) & 0xFF:02X}" for b in data)
        self._set_output(result)

    # -------------------------------------------------------- bitstring
    def _hex_to_bitstring(self):
        data = self._parse_hex()
        if data is None:
            return
        bits = " ".join(f"{b:08b}" for b in data)
        self._set_output(bits)

    def _bitstring_to_hex(self):
        raw = self._get_input_text().replace(" ", "")
        if not raw:
            QMessageBox.information(self, "提示", "请先输入二进制位串")
            return
        if not re.fullmatch(r"[01]+", raw):
            QMessageBox.warning(self, "格式错误", "输入包含非 0/1 字符")
            return
        padded = raw.zfill((len(raw) + 7) // 8 * 8)
        hex_str = " ".join(
            f"{int(padded[i:i + 8], 2):02X}" for i in range(0, len(padded), 8)
        )
        self._set_output(hex_str)

    # -------------------------------------------------------- CRC / 校验
    def _crc16_698(self):
        """CRC-16 X-25（698.45 协议）"""
        data = self._parse_hex()
        if data is None:
            return
        crc_obj = crcmod.predefined.Crc('x-25')
        crc_obj.update(bytes(data))
        crc_val = crc_obj.crcValue
        self._set_output(
            f"CRC-16 (X-25): 0x{crc_val:04X}\n"
            f"低字节在前: {crc_val & 0xFF:02X} {(crc_val >> 8) & 0xFF:02X}\n"
            f"高字节在前: {(crc_val >> 8) & 0xFF:02X} {crc_val & 0xFF:02X}"
        )

    def _crc32_newgen(self):
        """CRC-32 IEEE 802.3（南网/国网新一代载波协议）"""
        data = self._parse_hex()
        if data is None:
            return
        crc_val = _crc32_func(bytes(data))
        le_bytes = crc_val.to_bytes(4, 'little')
        self._set_output(
            f"CRC-32 (IEEE 802.3): 0x{crc_val:08X}\n"
            f"小端存储: {' '.join(f'{b:02X}' for b in le_bytes)}\n"
            f"大端存储: {' '.join(f'{b:02X}' for b in reversed(le_bytes))}"
        )

    def _crc24_newgen(self):
        """CRC-24（南网/国网新一代载波协议）"""
        data = self._parse_hex()
        if data is None:
            return
        crc_val = _crc24_func(bytes(data))
        le_bytes = crc_val.to_bytes(3, 'little')
        self._set_output(
            f"CRC-24: 0x{crc_val:06X}\n"
            f"小端存储: {' '.join(f'{b:02X}' for b in le_bytes)}\n"
            f"大端存储: {' '.join(f'{b:02X}' for b in reversed(le_bytes))}"
        )

    def _checksum8(self):
        """和校验：8位字节累加和（南网/国网协议）"""
        data = self._parse_hex()
        if data is None:
            return
        cs = sum(data) & 0xFF
        self._set_output(f"0x{cs:02X}\n十进制: {cs}")
