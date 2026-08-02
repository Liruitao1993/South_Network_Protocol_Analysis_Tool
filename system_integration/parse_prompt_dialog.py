"""
剪贴板报文解析提示框（系统集成）
================================
检测到剪贴板有 hex 报文后弹出的确认对话框：
- 显示报文摘要 + 自动识别协议 + 协议下拉切换
- 点击"解析" → 打开解析窗口

独立 QDialog，可置顶（WindowStaysOnTopHint），不阻塞主窗口。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout,
)


class ParsePromptDialog(QDialog):
    """剪贴板报文解析确认框"""

    def __init__(self, frame_bytes: bytes, hex_str: str, detected_protocol, parent=None):
        super().__init__(parent)
        self.frame_bytes = frame_bytes
        self.hex_str = hex_str
        self.selected_protocol = detected_protocol

        self.setWindowTitle("检测到报文")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 提示语
        tip = QLabel("检测到剪贴板中的十六进制报文，点击「解析」立即转入协议解析工具：")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 报文 hex 显示
        hex_text = QTextEdit()
        hex_text.setReadOnly(True)
        hex_text.setFont(self.font())
        hex_text.setMaximumHeight(90)
        hex_display = ' '.join(f'{b:02X}' for b in frame_bytes)
        hex_text.setPlainText(hex_display)
        layout.addWidget(hex_text)

        # 协议选择行
        proto_row = QHBoxLayout()
        proto_row.addWidget(QLabel("协议:"))
        self.proto_combo = QComboBox()
        # 由外部填充（main_gui 注入协议列表）
        self.proto_combo.setMinimumWidth(280)
        proto_row.addWidget(self.proto_combo)
        proto_row.addStretch()
        layout.addLayout(proto_row)

        # 提示：未识别或需切换协议时可选择
        auto_hint = QLabel()
        auto_hint.setStyleSheet("color: gray;")
        if detected_protocol is None:
            auto_hint.setText("未自动识别协议类型，请选择：")
        else:
            auto_hint.setText(f"自动识别为：{detected_protocol}")
        self._auto_hint = auto_hint
        layout.addWidget(auto_hint)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        parse_btn = QPushButton("解析")
        parse_btn.setDefault(True)
        parse_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(parse_btn)
        layout.addLayout(btn_row)

        self.proto_combo.currentIndexChanged.connect(self._on_proto_changed)

    def add_protocols(self, items):
        """填充协议下拉（items: [(显示文本, 协议索引), ...]）"""
        self.proto_combo.blockSignals(True)
        self.proto_combo.clear()
        for text, idx in items:
            self.proto_combo.addItem(text, idx)
        if self.selected_protocol is not None:
            fi = self.proto_combo.findData(self.selected_protocol)
            if fi >= 0:
                self.proto_combo.setCurrentIndex(fi)
        self.proto_combo.blockSignals(False)
        self._update_hint()

    def _on_proto_changed(self, _):
        self.selected_protocol = self.proto_combo.currentData()
        self._update_hint()

    def _update_hint(self):
        if self._auto_hint is None:
            return
        idx = self.selected_protocol
        if idx is None:
            self._auto_hint.setText("未自动识别协议类型，请选择：")
        else:
            text = self.proto_combo.currentText()
            self._auto_hint.setText(f"当前协议：{text}")

    def get_selection(self):
        """返回 (frame_bytes, protocol_index)"""
        return self.frame_bytes, self.selected_protocol
