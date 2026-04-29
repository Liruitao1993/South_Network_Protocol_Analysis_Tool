"""实时帧监听 Widget

提供串口数据实时监听、自动解析、历史记录功能。
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import deque

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QComboBox, QSplitter, QMessageBox, QFileDialog, QGroupBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor


class FrameMonitorWidget(QWidget):
    """实时帧监听 Widget"""

    # 信号
    frame_selected = Signal(bytes)  # 用户选中帧时发出
    add_to_test_plan = Signal(str, str)  # 添加到测试方案 (name, frame_hex)

    # 最大历史记录数
    MAX_HISTORY = 1000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._serial_worker = None
        self._frame_history: deque = deque(maxlen=self.MAX_HISTORY)
        self._parsers = {}  # 协议解析器映射
        self._auto_parse = True
        self._setup_ui()
        self._init_parsers()

    def _init_parsers(self):
        """初始化协议解析器"""
        try:
            from protocol_parser import ProtocolFrameParser
            from gdw10376_parser import GDW10376Parser
            from hdlc_parser import HDLCParser
            from plc_rf_parser import PLCRFProtocolParser
            from dlt645_parser import DLT645Parser

            self._parsers = {
                '南网': ProtocolFrameParser(),
                '国网': GDW10376Parser(),
                'HDLC': HDLCParser(),
                'PLC RF': PLCRFProtocolParser(),
                'DLT645': DLT645Parser(),
            }
        except Exception as e:
            print(f"初始化解析器失败: {e}")

    def _setup_ui(self):
        """设置 UI 布局"""
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(6, 6, 6, 6)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._auto_parse_check = QCheckBox("自动解析")
        self._auto_parse_check.setChecked(True)
        self._auto_parse_check.toggled.connect(self._on_auto_parse_toggled)
        toolbar.addWidget(self._auto_parse_check)

        toolbar.addWidget(QLabel("协议过滤:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["全部", "南网", "国网", "HDLC", "PLC RF", "DLT645"])
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._filter_combo)

        self._clear_btn = QPushButton("清空历史")
        self._clear_btn.clicked.connect(self._on_clear_history)
        toolbar.addWidget(self._clear_btn)

        self._export_btn = QPushButton("导出历史")
        self._export_btn.clicked.connect(self._on_export_history)
        toolbar.addWidget(self._export_btn)

        toolbar.addStretch()

        self._count_label = QLabel("共 0 帧")
        self._count_label.setStyleSheet("color: #666; font-size: 12px;")
        toolbar.addWidget(self._count_label)

        self._pause_check = QCheckBox("暂停接收")
        self._pause_check.toggled.connect(self._on_pause_toggled)
        toolbar.addWidget(self._pause_check)

        layout.addLayout(toolbar)

        # ---- 主内容区（左右分割）----
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：帧历史列表
        left_group = QGroupBox("帧历史")
        left_layout = QVBoxLayout(left_group)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self._history_table = QTableWidget()
        self._history_table.setColumnCount(6)
        self._history_table.setHorizontalHeaderLabels(["序号", "时间", "协议", "方向", "长度", "摘要"])
        header = self._history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self._history_table.setColumnWidth(0, 50)
        self._history_table.setColumnWidth(1, 80)
        self._history_table.setColumnWidth(2, 70)
        self._history_table.setColumnWidth(3, 50)
        self._history_table.setColumnWidth(4, 50)
        self._history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.verticalHeader().hide()
        self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._history_table.currentCellChanged.connect(self._on_history_row_changed)
        table_font = QFont()
        table_font.setPointSize(8)
        self._history_table.setFont(table_font)
        left_layout.addWidget(self._history_table)

        splitter.addWidget(left_group)

        # 右侧：选中帧的解析结果 + 校验结果
        right_group = QGroupBox("解析结果")
        right_layout = QVBoxLayout(right_group)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self._parse_result_table = QTableWidget()
        self._parse_result_table.setColumnCount(4)
        self._parse_result_table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        header = self._parse_result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self._parse_result_table.setColumnWidth(0, 120)
        self._parse_result_table.setColumnWidth(1, 100)
        self._parse_result_table.setColumnWidth(2, 100)
        self._parse_result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._parse_result_table.setAlternatingRowColors(True)
        self._parse_result_table.verticalHeader().hide()
        self._parse_result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._parse_result_table.setFont(table_font)
        right_layout.addWidget(self._parse_result_table)

        # 校验结果区域
        self._verify_group = QGroupBox("校验结果")
        verify_layout = QVBoxLayout(self._verify_group)
        verify_layout.setContentsMargins(4, 4, 4, 4)
        self._verify_label = QLabel("等待解析...")
        self._verify_label.setWordWrap(True)
        self._verify_label.setFont(QFont("Consolas", 9))
        verify_layout.addWidget(self._verify_label)
        right_layout.addWidget(self._verify_group)

        splitter.addWidget(right_group)
        splitter.setSizes([400, 500])

        layout.addWidget(splitter, 1)

        # ---- 底部按钮 ----
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(6)

        self._add_to_test_btn = QPushButton("添加到测试方案")
        self._add_to_test_btn.setEnabled(False)
        self._add_to_test_btn.clicked.connect(self._on_add_to_test_plan)
        self._add_to_test_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 12px; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        bottom_layout.addWidget(self._add_to_test_btn)

        self._copy_hex_btn = QPushButton("复制HEX")
        self._copy_hex_btn.setEnabled(False)
        self._copy_hex_btn.clicked.connect(self._on_copy_hex)
        bottom_layout.addWidget(self._copy_hex_btn)

        self._verify_btn = QPushButton("校验选中帧")
        self._verify_btn.setEnabled(False)
        self._verify_btn.clicked.connect(self._on_verify_selected)
        self._verify_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; border-radius: 3px; padding: 4px 12px; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        bottom_layout.addWidget(self._verify_btn)

        bottom_layout.addStretch()

        self._hex_display = QLabel("")
        self._hex_display.setStyleSheet("color: #333; font-family: Consolas; font-size: 10px;")
        self._hex_display.setWordWrap(True)
        bottom_layout.addWidget(self._hex_display, 1)

        layout.addLayout(bottom_layout)

    def set_serial_worker(self, worker):
        """设置串口工作线程"""
        self._serial_worker = worker
        if worker:
            worker.frame_received.connect(self._on_frame_received)

    def _on_frame_received(self, frame: bytes):
        """收到串口帧的回调"""
        if self._pause_check.isChecked():
            return

        if not self._auto_parse:
            return

        # 识别协议
        protocol = self._identify_protocol(frame)

        # 过滤检查
        filter_text = self._filter_combo.currentText()
        if filter_text != "全部" and filter_text != protocol:
            return

        # 解析帧
        parse_result = self._parse_frame(frame, protocol)

        # 添加到历史
        now = datetime.now()
        entry = {
            'time': now,
            'frame': frame,
            'protocol': protocol,
            'direction': '接收',
            'parse_result': parse_result,
            'hex': frame.hex().upper()
        }
        self._frame_history.append(entry)

        # 更新表格
        self._update_history_table()

    def _identify_protocol(self, frame: bytes) -> str:
        """识别帧的协议类型"""
        if len(frame) == 0:
            return "未知"

        # 南网/国网: 起始符 0x68, 结束符 0x16
        if frame[0] == 0x68 and frame[-1] == 0x16:
            # 通过长度域区分：南网长度域占2字节，国网格式域更复杂
            if len(frame) >= 3:
                length = int.from_bytes(frame[1:3], 'little')
                if length + 6 == len(frame):
                    return "南网"
            return "国网"

        # HDLC: 起始标志 0x7E
        if frame[0] == 0x7E:
            return "HDLC"

        # PLC RF: 起始符 0x02
        if frame[0] == 0x02 and len(frame) >= 8:
            return "PLC RF"

        # DLT645: 两个 0x68
        if len(frame) >= 12 and frame[0] == 0x68 and frame[7] == 0x68:
            return "DLT645"

        return "未知"

    def _parse_frame(self, frame: bytes, protocol: str) -> Optional[List]:
        """解析帧"""
        parser = self._parsers.get(protocol)
        if parser and hasattr(parser, 'parse_to_table'):
            try:
                return parser.parse_to_table(frame)
            except Exception:
                pass
        return None

    def _update_history_table(self):
        """更新历史表格"""
        self._history_table.setRowCount(len(self._frame_history))
        for idx, entry in enumerate(reversed(self._frame_history)):
            row = len(self._frame_history) - 1 - idx
            if row < 0:
                continue

            # 序号
            self._history_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            # 时间
            time_str = entry['time'].strftime("%H:%M:%S")
            self._history_table.setItem(row, 1, QTableWidgetItem(time_str))

            # 协议
            protocol_item = QTableWidgetItem(entry['protocol'])
            if entry['protocol'] == "南网":
                protocol_item.setForeground(QColor("#1565C0"))
            elif entry['protocol'] == "国网":
                protocol_item.setForeground(QColor("#2E7D32"))
            elif entry['protocol'] == "HDLC":
                protocol_item.setForeground(QColor("#E65100"))
            self._history_table.setItem(row, 2, protocol_item)

            # 方向
            self._history_table.setItem(row, 3, QTableWidgetItem(entry['direction']))

            # 长度
            self._history_table.setItem(row, 4, QTableWidgetItem(str(len(entry['frame']))))

            # 摘要
            summary = self._get_frame_summary(entry)
            self._history_table.setItem(row, 5, QTableWidgetItem(summary))

        # 更新计数
        self._count_label.setText(f"共 {len(self._frame_history)} 帧")

    def _get_frame_summary(self, entry: Dict) -> str:
        """获取帧摘要"""
        frame = entry['frame']
        protocol = entry['protocol']

        if protocol in ("南网", "国网") and len(frame) >= 7:
            afn = frame[6]
            return f"AFN=0x{afn:02X}"
        elif protocol == "HDLC" and len(frame) >= 3:
            return f"控制域=0x{frame[2]:02X}"
        elif protocol == "PLC RF" and len(frame) >= 5:
            cmd = int.from_bytes(frame[3:5], 'little')
            return f"CMD=0x{cmd:04X}"
        elif protocol == "DLT645" and len(frame) >= 12:
            ctrl = frame[8]
            return f"控制码=0x{ctrl:02X}"

        return frame[:8].hex().upper() + "..."

    def _on_history_row_changed(self, row, col, prev_row, prev_col):
        """历史表格行选中变化"""
        if row < 0 or row >= len(self._frame_history):
            self._add_to_test_btn.setEnabled(False)
            self._copy_hex_btn.setEnabled(False)
            self._verify_btn.setEnabled(False)
            return

        # 获取选中的帧（注意表格是倒序显示的）
        idx = len(self._frame_history) - 1 - row
        if idx < 0 or idx >= len(self._frame_history):
            return

        entry = list(self._frame_history)[idx]
        self._selected_frame = entry['frame']
        self._selected_hex = entry['hex']

        # 更新解析结果
        self._update_parse_result(entry)

        # 启用按钮
        self._add_to_test_btn.setEnabled(True)
        self._copy_hex_btn.setEnabled(True)
        self._verify_btn.setEnabled(True)

        # 显示 HEX
        formatted = " ".join(self._selected_hex[i:i+2] for i in range(0, len(self._selected_hex), 2))
        self._hex_display.setText(formatted[:100] + "..." if len(formatted) > 100 else formatted)

    def _update_parse_result(self, entry: Dict):
        """更新解析结果表格"""
        parse_result = entry.get('parse_result')
        if not parse_result:
            self._parse_result_table.setRowCount(0)
            self._verify_label.setText("无法解析此帧")
            return

        self._parse_result_table.setRowCount(len(parse_result))
        for row_idx, row_data in enumerate(parse_result):
            if len(row_data) >= 4:
                self._parse_result_table.setItem(row_idx, 0, QTableWidgetItem(str(row_data[0])))
                self._parse_result_table.setItem(row_idx, 1, QTableWidgetItem(str(row_data[1])))
                self._parse_result_table.setItem(row_idx, 2, QTableWidgetItem(str(row_data[2])))
                self._parse_result_table.setItem(row_idx, 3, QTableWidgetItem(str(row_data[3])))

    def _on_auto_parse_toggled(self, checked):
        self._auto_parse = checked

    def _on_filter_changed(self, text):
        """过滤条件变化"""
        # 重新过滤显示
        self._update_history_table()

    def _on_pause_toggled(self, checked):
        """暂停接收"""
        if checked:
            self._pause_check.setText("继续接收")
            self._pause_check.setStyleSheet("color: red;")
        else:
            self._pause_check.setText("暂停接收")
            self._pause_check.setStyleSheet("")

    def _on_clear_history(self):
        """清空历史"""
        self._frame_history.clear()
        self._history_table.setRowCount(0)
        self._parse_result_table.setRowCount(0)
        self._verify_label.setText("等待解析...")
        self._count_label.setText("共 0 帧")
        self._add_to_test_btn.setEnabled(False)
        self._copy_hex_btn.setEnabled(False)
        self._verify_btn.setEnabled(False)

    def _on_export_history(self):
        """导出历史记录"""
        if not self._frame_history:
            QMessageBox.information(self, "提示", "历史记录为空")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出历史记录", "frame_history.txt", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for entry in self._frame_history:
                    time_str = entry['time'].strftime("%Y-%m-%d %H:%M:%S")
                    hex_str = entry['hex']
                    protocol = entry['protocol']
                    f.write(f"[{time_str}] [{protocol}] {hex_str}\n")
            QMessageBox.information(self, "成功", f"已导出 {len(self._frame_history)} 条记录")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_copy_hex(self):
        """复制 HEX"""
        if hasattr(self, '_selected_hex'):
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(self._selected_hex)
            QMessageBox.information(self, "成功", "已复制到剪贴板")

    def _on_add_to_test_plan(self):
        """添加到测试方案"""
        if hasattr(self, '_selected_frame') and hasattr(self, '_selected_hex'):
            # 生成名称
            idx = self._history_table.currentRow()
            if idx >= 0:
                history_idx = len(self._frame_history) - 1 - idx
                if 0 <= history_idx < len(self._frame_history):
                    entry = list(self._frame_history)[history_idx]
                    name = f"{entry['protocol']}帧-{entry['time'].strftime('%H%M%S')}"
                    self.add_to_test_plan.emit(name, self._selected_hex)
                    QMessageBox.information(self, "成功", f"已添加到测试方案: {name}")

    def _on_verify_selected(self):
        """校验选中帧"""
        if not hasattr(self, '_selected_frame'):
            return

        frame = self._selected_frame
        protocol = self._identify_protocol(frame)

        # 调用对应的验证器
        try:
            from validator import (
                NWValidator, GDWValidator, HDLCValidator, PLCRFValidator, DLT645Validator
            )

            validators = {
                '南网': NWValidator(),
                '国网': GDWValidator(),
                'HDLC': HDLCValidator(),
                'PLC RF': PLCRFValidator(),
                'DLT645': DLT645Validator(),
            }

            validator = validators.get(protocol)
            if validator:
                result = validator.verify(frame)
                self._display_verify_result(result)
            else:
                self._verify_label.setText(f"不支持 {protocol} 协议的校验")
        except Exception as e:
            self._verify_label.setText(f"校验失败: {str(e)}")

    def _display_verify_result(self, result):
        """显示校验结果"""
        from validator.base import CheckLevel

        lines = []
        lines.append(f"协议: {result.protocol}")
        lines.append(f"整体结果: {'✅ 通过' if result.valid else '❌ 失败'}")
        lines.append("")

        for check in result.checks:
            icon = "✅" if check.level == CheckLevel.PASS else "❌" if check.level == CheckLevel.FAIL else "⚠️"
            lines.append(f"{icon} {check.name}: {check.message}")

        if result.warnings:
            lines.append("")
            lines.append("⚠️ 警告:")
            for w in result.warnings:
                lines.append(f"  - {w}")

        if result.errors:
            lines.append("")
            lines.append("❌ 错误:")
            for e in result.errors:
                lines.append(f"  - {e}")

        self._verify_label.setText("\n".join(lines))

        # 设置颜色
        if result.valid:
            self._verify_group.setStyleSheet("QGroupBox { border: 2px solid #4CAF50; }")
        else:
            self._verify_group.setStyleSheet("QGroupBox { border: 2px solid #f44336; }")
