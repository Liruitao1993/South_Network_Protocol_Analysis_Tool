"""报文对比 Diff 标签页

功能：
  - 双报文输入（A 基准 / B 对比），支持从单帧解析载入
  - 字节级对比（字段感知对齐，差异高亮）
  - 字段级语义对比（表格展示偏移、长度、值及差异类型）
  - 差异人话解读（自然语言解释业务含义）
  - 配置选项（字段感知对齐、忽略校验和/序列号、仅显示差异）
  - 导出对比报告
"""

from typing import Dict, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QGroupBox, QSplitter, QFrame, QScrollArea,
    QSizePolicy,
)
from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QBrush, QTextCursor, QIcon

from frame_diff_engine import FrameDiffEngine, _format_bytes
from gui_utils import ZoomableTableWidget


# ---- 颜色常量 ----
_COLOR_SAME_BG = QColor(245, 245, 245)
_COLOR_MOD_BG = QColor(255, 235, 238)
_COLOR_MOD_FG = QColor(198, 40, 40)
_COLOR_ADD_BG = QColor(255, 248, 225)
_COLOR_ADD_FG = QColor(176, 104, 0)
_COLOR_DEL_BG = QColor(236, 239, 241)
_COLOR_DEL_FG = QColor(144, 164, 174)
_COLOR_HEADER_BG = QColor(240, 240, 240)
_COLOR_BORDER = QColor(220, 220, 220)


# ---- 表格弹窗 ----
class TablePopupDialog(QDialog):
    """表格详情弹窗：以独立窗口展示完整的对比表格"""

    def __init__(self, title: str, table_builder, parent=None):
        """
        Args:
            title: 窗口标题
            table_builder: 可调用对象，返回填充好的 QTableWidget
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1200, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        table = table_builder()
        layout.addWidget(table)

        # 关闭按钮
        btn_close = QPushButton("关闭")
        btn_close.setFixedSize(80, 28)
        btn_close.setStyleSheet(
            "QPushButton { background-color: #fff; color: #666; border: 1px solid #dcdcdc; "
            "border-radius: 3px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #f0f0f0; }"
        )
        btn_close.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class DiffWidget(QWidget):
    """报文对比标签页"""

    diff_completed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = FrameDiffEngine()
        self._last_result: Optional[Dict[str, Any]] = None
        self._protocol_index = 0
        self._init_ui()

    # =========================================================================
    # UI 构建
    # =========================================================================

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ---- 工具栏 ----
        layout.addWidget(self._build_toolbar())

        # ---- 双报文输入区 ----
        layout.addWidget(self._build_input_area())

        # ---- 统计摘要 + 选项 ----
        layout.addWidget(self._build_summary_bar())

        # ---- 对比结果区（可滚动） ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._result_container = QWidget()
        self._result_layout = QVBoxLayout(self._result_container)
        self._result_layout.setContentsMargins(0, 0, 0, 0)
        self._result_layout.setSpacing(10)
        scroll.setWidget(self._result_container)
        layout.addWidget(scroll, 1)

        # ---- 占位提示 ----
        self._placeholder = QLabel("请输入报文 A 和 B，然后点击「开始对比」")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #999; font-size: 14px; padding: 40px;")
        self._result_layout.addWidget(self._placeholder)

    def _build_toolbar(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        title = QLabel("报文对比 Diff")
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        self.btn_compare = QPushButton("开始对比")
        self.btn_compare.setMinimumHeight(28)
        self.btn_compare.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border: none; "
            "border-radius: 3px; padding: 4px 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #43A047; }"
        )
        self.btn_compare.clicked.connect(self._on_compare)
        layout.addWidget(self.btn_compare)

        self.btn_swap = QPushButton("交换 A↔B")
        self.btn_swap.setMinimumHeight(28)
        self.btn_swap.setStyleSheet(
            "QPushButton { background-color: #fff; color: #666; border: 1px solid #dcdcdc; "
            "border-radius: 3px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #f0f0f0; }"
        )
        self.btn_swap.clicked.connect(self._on_swap)
        layout.addWidget(self.btn_swap)

        self.btn_load_a = QPushButton("从单帧解析载入 A")
        self.btn_load_a.setMinimumHeight(28)
        self.btn_load_a.setStyleSheet(
            "QPushButton { background-color: #fff; color: #666; border: 1px solid #dcdcdc; "
            "border-radius: 3px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #f0f0f0; }"
        )
        self.btn_load_a.clicked.connect(self._on_load_a)
        layout.addWidget(self.btn_load_a)

        self.btn_load_b = QPushButton("从单帧解析载入 B")
        self.btn_load_b.setMinimumHeight(28)
        self.btn_load_b.setStyleSheet(
            "QPushButton { background-color: #fff; color: #666; border: 1px solid #dcdcdc; "
            "border-radius: 3px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #f0f0f0; }"
        )
        self.btn_load_b.clicked.connect(self._on_load_b)
        layout.addWidget(self.btn_load_b)

        layout.addStretch()

        # 图例
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(12)
        for text, color in [("相同", _COLOR_SAME_BG), ("修改", _COLOR_MOD_BG), ("B新增", _COLOR_ADD_BG)]:
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; border-radius: 2px;")
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #666; font-size: 11px;")
            legend_layout.addWidget(swatch)
            legend_layout.addWidget(lbl)
        layout.addLayout(legend_layout)

        self.btn_export = QPushButton("导出对比报告")
        self.btn_export.setMinimumHeight(28)
        self.btn_export.setStyleSheet(
            "QPushButton { background-color: #9e9e9e; color: white; border: none; "
            "border-radius: 3px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #757575; }"
        )
        self.btn_export.clicked.connect(self._on_export)
        layout.addWidget(self.btn_export)

        return w

    def _build_input_area(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background-color: #f7f7f7; border: 1px solid #dcdcdc; border-radius: 4px;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # 报文 A
        group_a = QGroupBox()
        group_a.setStyleSheet("QGroupBox { border: 1px solid #dcdcdc; border-radius: 4px; margin-top: 8px; }"
                              "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }")
        va = QVBoxLayout(group_a)
        va.setContentsMargins(4, 4, 4, 4)
        va.setSpacing(2)

        header_a = QHBoxLayout()
        self.lbl_title_a = QLabel("<b>报文 A（基准）</b>")
        self.lbl_title_a.setStyleSheet("color: #333;")
        header_a.addWidget(self.lbl_title_a)
        header_a.addStretch()
        self.lbl_info_a = QLabel("")
        self.lbl_info_a.setStyleSheet("color: #999; font-size: 11px;")
        header_a.addWidget(self.lbl_info_a)
        va.addLayout(header_a)

        self.input_a = QTextEdit()
        self.input_a.setFont(QFont("Consolas", 11))
        self.input_a.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.input_a.setPlaceholderText("请输入报文 A 的十六进制数据，例如：68 14 00 14 00 4D 01 01 E8 03 03 74 00 00 02 00 7B 16")
        self.input_a.setMinimumHeight(40)
        self.input_a.setMaximumHeight(80)
        va.addWidget(self.input_a)

        layout.addWidget(group_a)

        # 报文 B
        group_b = QGroupBox()
        group_b.setStyleSheet("QGroupBox { border: 1px solid #dcdcdc; border-radius: 4px; margin-top: 8px; }"
                              "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }")
        vb = QVBoxLayout(group_b)
        vb.setContentsMargins(4, 4, 4, 4)
        vb.setSpacing(2)

        header_b = QHBoxLayout()
        self.lbl_title_b = QLabel("<b>报文 B（对比）</b>")
        self.lbl_title_b.setStyleSheet("color: #333;")
        header_b.addWidget(self.lbl_title_b)
        header_b.addStretch()
        self.lbl_info_b = QLabel("")
        self.lbl_info_b.setStyleSheet("color: #999; font-size: 11px;")
        header_b.addWidget(self.lbl_info_b)
        vb.addLayout(header_b)

        self.input_b = QTextEdit()
        self.input_b.setFont(QFont("Consolas", 11))
        self.input_b.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.input_b.setPlaceholderText("请输入报文 B 的十六进制数据，例如：68 16 00 16 00 8D 01 01 E8 03 03 74 00 00 02 00 9A 8C 16")
        self.input_b.setMinimumHeight(40)
        self.input_b.setMaximumHeight(80)
        vb.addWidget(self.input_b)

        layout.addWidget(group_b)

        return w

    def _build_summary_bar(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("color: #333; font-size: 12px;")
        layout.addWidget(self.lbl_summary)

        layout.addStretch()

        # 选项
        self.chk_field_align = QCheckBox("字段感知对齐")
        self.chk_field_align.setChecked(True)
        self.chk_field_align.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.chk_field_align)

        self.chk_ignore_cs = QCheckBox("忽略校验和字节")
        self.chk_ignore_cs.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.chk_ignore_cs)

        self.chk_ignore_seq = QCheckBox("忽略序列号")
        self.chk_ignore_seq.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.chk_ignore_seq)

        self.chk_only_diff = QCheckBox("仅显示差异")
        self.chk_only_diff.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.chk_only_diff)

        return w

    # =========================================================================
    # 对比结果渲染
    # =========================================================================

    def _clear_result_area(self):
        """清除结果区域的所有内容"""
        while self._result_layout.count():
            item = self._result_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_result(self, result: Dict[str, Any]):
        """渲染对比结果到界面"""
        self._clear_result_area()
        self._last_result = result

        if not result.get('success'):
            err = QLabel(f"  对比失败：{result.get('error', '未知错误')}")
            err.setStyleSheet("color: #c62828; font-size: 13px; padding: 10px;")
            self._result_layout.addWidget(err)
            return

        # 更新摘要
        stats = result['stats']
        self.lbl_summary.setText(
            f"  A: {stats['bytes_a_len']} 字节 / B: {stats['bytes_b_len']} 字节    "
            f"修改 {stats['field_modified']} 处    "
            f"B 新增 {stats['field_added']} 字节    "
            f"A 独有 {stats['field_removed']}"
        )

        # 更新输入区信息
        self.lbl_info_a.setText(f"{stats['bytes_a_len']} 字节")
        self.lbl_info_b.setText(f"{stats['bytes_b_len']} 字节")

        # ---- 字节级对比 ----
        self._result_layout.addWidget(self._build_byte_diff_section(result['byte_diff']))

        # ---- 字段级语义对比 ----
        self._result_layout.addWidget(self._build_field_diff_section(result['field_diff']))

        # ---- 差异说明 ----
        self._result_layout.addWidget(self._build_explanation_section(result['explanation']))

        self.diff_completed.emit(result)

    def _build_byte_diff_section(self, byte_diff: list) -> QWidget:
        """构建字节级对比区"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 标题行（含最大化按钮）
        title_row = QHBoxLayout()
        title = QLabel("字节级对比（按字段对齐）")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #333; padding: 2px 0;")
        title_row.addWidget(title)
        title_row.addStretch()

        btn_max = QPushButton("⊞")
        btn_max.setFixedSize(24, 24)
        btn_max.setToolTip("最大化显示表格")
        btn_max.setStyleSheet(
            "QPushButton { background-color: #fff; color: #666; border: 1px solid #dcdcdc; "
            "border-radius: 3px; font-size: 14px; padding: 0; }"
            "QPushButton:hover { background-color: #e3f2fd; border-color: #42a5f5; color: #1976d2; }"
        )
        btn_max.clicked.connect(lambda: self._open_table_popup(
            "字节级对比详情", lambda: self._build_byte_diff_table(byte_diff)
        ))
        title_row.addWidget(btn_max)
        layout.addLayout(title_row)

        subtitle = QLabel('— 协议感知：长度不同的帧也能把"校验和"对"校验和"、"结束符"对"结束符"')
        subtitle.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(subtitle)

        # 用 QTableWidget 展示
        table = self._build_byte_diff_table(byte_diff)
        layout.addWidget(table)

        return container

    def _build_byte_diff_table(self, byte_diff: list) -> QTableWidget:
        """构建字节级对比表格（可复用）"""
        table = ZoomableTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["字段", "报文 A 字节", "报文 B 字节"])
        table.setRowCount(len(byte_diff))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setStyleSheet(
            "QTableWidget { border: 1px solid #dcdcdc; border-radius: 4px; font-family: Consolas, monospace; font-size: 12px; }"
            "QTableWidget::item { padding: 3px; }"
            "QHeaderView::section { background-color: #f0f0f0; color: #444; padding: 4px 8px; "
            "border: 1px solid #dcdcdc; font-weight: bold; }"
        )

        for row, bd in enumerate(byte_diff):
            # 字段名
            name_item = QTableWidgetItem(bd['field_name'])
            name_item.setFont(QFont("Microsoft YaHei", 9))
            name_item.setBackground(_COLOR_HEADER_BG)
            table.setItem(row, 0, name_item)

            # A 字节 — 用 QLabel 渲染 HTML
            a_widget = self._make_byte_label(bd['byte_details'], side='a')
            table.setCellWidget(row, 1, a_widget)

            # B 字节 — 用 QLabel 渲染 HTML
            b_widget = self._make_byte_label(bd['byte_details'], side='b')
            table.setCellWidget(row, 2, b_widget)

        # 设置行高
        table.verticalHeader().setDefaultSectionSize(28)
        return table

    def _make_byte_label(self, byte_details: list, side: str) -> QLabel:
        """创建带颜色高亮的字节 QLabel（用于 QTableWidget.setCellWidget）"""
        label = QLabel()
        label.setFont(QFont("Consolas", 11))
        label.setStyleSheet("padding: 2px 4px;")
        html = self._build_byte_detail_html(byte_details, side)
        label.setText(html)
        label.setTextFormat(Qt.TextFormat.RichText)
        return label

    def _build_byte_detail_html(self, byte_details: list, side: str) -> str:
        """构建字节详情 HTML"""
        parts = []
        for d in byte_details:
            byte_val = d.get(f'byte_{side}')
            status = d['status']
            if byte_val is None:
                parts.append('<span style="color:#999;">—</span>')
            elif status == 'modified':
                parts.append(f'<span style="background:#ffebee; color:#c62828; font-weight:bold; '
                             f'padding:1px 3px; border-radius:2px;">{byte_val:02X}</span>')
            elif status == 'added':
                parts.append(f'<span style="background:#fff8e1; color:#b06800; font-weight:bold; '
                             f'padding:1px 3px; border-radius:2px;">{byte_val:02X}</span>')
            elif status == 'removed':
                parts.append(f'<span style="background:#eceff1; color:#90a4ae; '
                             f'padding:1px 3px; border-radius:2px; text-decoration:line-through;">'
                             f'{byte_val:02X}</span>')
            else:
                parts.append(f'{byte_val:02X}')
        return ' '.join(parts)

    def _build_field_diff_section(self, field_diff: list) -> QWidget:
        """构建字段级语义对比区"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 标题行（含最大化按钮）
        title_row = QHBoxLayout()
        title = QLabel("字段级语义对比")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #333; padding: 2px 0;")
        title_row.addWidget(title)
        title_row.addStretch()

        btn_max = QPushButton("⊞")
        btn_max.setFixedSize(24, 24)
        btn_max.setToolTip("最大化显示表格")
        btn_max.setStyleSheet(
            "QPushButton { background-color: #fff; color: #666; border: 1px solid #dcdcdc; "
            "border-radius: 3px; font-size: 14px; padding: 0; }"
            "QPushButton:hover { background-color: #e3f2fd; border-color: #42a5f5; color: #1976d2; }"
        )
        btn_max.clicked.connect(lambda: self._open_table_popup(
            "字段级对比详情", lambda: self._build_field_diff_table(field_diff)
        ))
        title_row.addWidget(btn_max)
        layout.addLayout(title_row)

        subtitle = QLabel('— 直接告诉你"哪个字段的含义变了"，而不只是看字节')
        subtitle.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(subtitle)

        table = self._build_field_diff_table(field_diff)
        layout.addWidget(table)

        return container

    def _build_field_diff_table(self, field_diff: list) -> QTableWidget:
        """构建字段级语义对比表格（可复用）"""
        table = ZoomableTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["字段", "偏移", "长度", "报文 A", "报文 B", "差异"])
        table.setRowCount(len(field_diff))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        table.setStyleSheet(
            "QTableWidget { border: 1px solid #dcdcdc; border-radius: 4px; font-size: 12px; }"
            "QTableWidget::item { padding: 4px 6px; }"
            "QHeaderView::section { background-color: #f0f0f0; color: #444; padding: 4px 8px; "
            "border: 1px solid #dcdcdc; font-weight: bold; }"
        )

        for row, fd in enumerate(field_diff):
            table.setItem(row, 0, QTableWidgetItem(fd['field_name']))
            table.setItem(row, 1, QTableWidgetItem(str(fd['offset_a'] if fd['offset_a'] >= 0 else '-')))
            table.setItem(row, 2, QTableWidgetItem(str(fd['length_a'] if fd['length_a'] > 0 else fd['length_b'])))

            val_a_item = QTableWidgetItem(fd['value_a'])
            val_a_item.setFont(QFont("Consolas", 10))
            table.setItem(row, 3, val_a_item)

            val_b_item = QTableWidgetItem(fd['value_b'])
            val_b_item.setFont(QFont("Consolas", 10))
            table.setItem(row, 4, val_b_item)

            # 差异标签
            diff_type = fd['diff_type']
            diff_item = QTableWidgetItem(diff_type)
            if diff_type == '相同':
                diff_item.setBackground(QColor(236, 239, 241))
                diff_item.setForeground(QColor(96, 125, 139))
            elif diff_type == '修改':
                diff_item.setBackground(QColor(255, 235, 238))
                diff_item.setForeground(QColor(198, 40, 40))
                diff_item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            elif diff_type == 'B新增':
                diff_item.setBackground(QColor(255, 248, 225))
                diff_item.setForeground(QColor(176, 104, 0))
                diff_item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            elif diff_type == 'A独有':
                diff_item.setBackground(QColor(236, 239, 241))
                diff_item.setForeground(QColor(144, 164, 174))
            table.setItem(row, 5, diff_item)

        table.verticalHeader().setDefaultSectionSize(26)
        return table

    def _build_explanation_section(self, explanation: list) -> QWidget:
        """构建差异说明区"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("差异说明（人话解读）")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #333; padding: 2px 0;")
        layout.addWidget(title)

        # 用 QTextEdit 展示，带左侧橙色竖线装饰
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Microsoft YaHei", 10))
        text_edit.setFrameShape(QFrame.Shape.StyledPanel)
        text_edit.setStyleSheet(
            "QTextEdit { border: 1px solid #dcdcdc; border-left: 3px solid #FF9800; "
            "border-radius: 4px; background-color: #fffdf5; padding: 8px 12px; }"
        )

        html = "<ul style='margin: 4px 0; padding-left: 20px;'>"
        for line in explanation:
            # 将 code 部分用 <code> 标签包裹
            line = line.replace('0x', '<code style="background:#f5f5f5; padding:0 4px; border-radius:2px; color:#c62828;">0x')
            line = line.replace('</code>', '</code>')
            # 简单处理：将括号中的内容也高亮
            html += f"<li style='margin: 3px 0; line-height: 1.6;'>{line}</li>"
        html += "</ul>"
        text_edit.setHtml(html)
        text_edit.setMinimumHeight(80)
        layout.addWidget(text_edit)

        return container

    # =========================================================================
    # 事件处理
    # =========================================================================

    def _open_table_popup(self, title: str, table_builder):
        """打开表格详情弹窗"""
        dialog = TablePopupDialog(title, table_builder, self)
        dialog.exec()

    def _on_compare(self):
        """开始对比"""
        hex_a = self.input_a.toPlainText().strip()
        hex_b = self.input_b.toPlainText().strip()

        if not hex_a or not hex_b:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "警告", "请输入报文 A 和报文 B！")
            return

        result = self._engine.compare(
            hex_a, hex_b,
            field_aware_align=self.chk_field_align.isChecked(),
            ignore_checksum=self.chk_ignore_cs.isChecked(),
            ignore_sequence=self.chk_ignore_seq.isChecked(),
            show_only_diff=self.chk_only_diff.isChecked(),
        )
        self._render_result(result)

    def _on_swap(self):
        """交换 A 和 B"""
        text_a = self.input_a.toPlainText()
        text_b = self.input_b.toPlainText()
        self.input_a.setPlainText(text_b)
        self.input_b.setPlainText(text_a)

    def _on_load_a(self):
        """从主窗口单帧解析结果载入 A"""
        main = self._get_main_window()
        if main and hasattr(main, '_last_parsed_hex') and main._last_parsed_hex:
            self.input_a.setPlainText(main._last_parsed_hex)
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "请先在「单帧解析」标签页解析一帧报文")

    def _on_load_b(self):
        """从主窗口单帧解析结果载入 B"""
        main = self._get_main_window()
        if main and hasattr(main, '_last_parsed_hex') and main._last_parsed_hex:
            self.input_b.setPlainText(main._last_parsed_hex)
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "请先在「单帧解析」标签页解析一帧报文")

    def _on_export(self):
        """导出对比报告"""
        if not self._last_result or not self._last_result.get('success'):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "警告", "请先执行对比再导出报告")
            return

        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出对比报告", "", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if path:
            report = self._engine.export_report(self._last_result)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(report)

    def _get_main_window(self):
        """获取主窗口引用"""
        w = self.parent()
        while w is not None:
            from PySide6.QtWidgets import QMainWindow
            if isinstance(w, QMainWindow):
                return w
            w = w.parent()
        return None

    # =========================================================================
    # 公共接口
    # =========================================================================

    def set_protocol(self, index: int):
        """设置当前协议索引（由主窗口在协议切换时调用）"""
        self._protocol_index = index

    def set_parser(self, parser):
        """设置对比引擎使用的解析器"""
        self._engine.set_parser(parser)

    def load_frame_a(self, hex_str: str):
        """外部调用：载入报文 A"""
        self.input_a.setPlainText(hex_str)

    def load_frame_b(self, hex_str: str):
        """外部调用：载入报文 B"""
        self.input_b.setPlainText(hex_str)
