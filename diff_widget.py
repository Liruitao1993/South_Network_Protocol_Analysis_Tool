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
from gui_utils import ZoomableTableWidget, set_btn, set_btn_icon


# ---- 主题调色板（浅色 / 暗色） ----
_PALETTES = {
    False: {  # 浅色
        "panel_bg": "#f7f7f7", "border": "#dcdcdc", "swatch_border": "#ccc",
        "title": "#333", "dim": "#999", "mid": "#666",
        "header_bg": "#f0f0f0", "header_fg": "#444",
        "same_bg": "#f5f5f5",
        "mod_bg": "#ffebee", "mod_fg": "#c62828",
        "add_bg": "#fff8e1", "add_fg": "#b06800",
        "del_bg": "#eceff1", "del_fg": "#90a4ae",
        "explain_bg": "#fffdf5", "code_bg": "#f5f5f5",
    },
    True: {  # 暗色
        "panel_bg": "#2b2b2b", "border": "#4a4a4a", "swatch_border": "#666",
        "title": "#e0e0e0", "dim": "#9a9a9a", "mid": "#c0c0c0",
        "header_bg": "#3a3a3a", "header_fg": "#d0d0d0",
        "same_bg": "#3a3a3a",
        "mod_bg": "#4a2b2b", "mod_fg": "#ef9a9a",
        "add_bg": "#4a3a1f", "add_fg": "#ffcc80",
        "del_bg": "#3a4750", "del_fg": "#90a4ae",
        "explain_bg": "#2e2a24", "code_bg": "#3c3c3c",
    },
}


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
        btn_close.setMinimumWidth(80)
        set_btn(btn_close, "secondary")
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
        self._dark = False
        self._legend_swatches = []   # [(QLabel, 调色板键)]
        self._legend_labels = []
        self._init_ui()

    def _pal(self) -> Dict[str, str]:
        return _PALETTES[self._dark]

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
        self._placeholder.setStyleSheet(f"color: {self._pal()['dim']}; font-size: 14px; padding: 40px;")
        self._result_layout.addWidget(self._placeholder)

    def _build_toolbar(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        title = QLabel("报文对比 Diff")
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        self.btn_compare = QPushButton("开始对比")
        set_btn(self.btn_compare, "success")
        set_btn_icon(self.btn_compare, "play")
        self.btn_compare.clicked.connect(self._on_compare)
        layout.addWidget(self.btn_compare)

        self.btn_swap = QPushButton("交换 A↔B")
        set_btn(self.btn_swap, "secondary")
        set_btn_icon(self.btn_swap, "refresh")
        self.btn_swap.clicked.connect(self._on_swap)
        layout.addWidget(self.btn_swap)

        self.btn_load_a = QPushButton("从单帧解析载入 A")
        set_btn(self.btn_load_a, "secondary")
        set_btn_icon(self.btn_load_a, "open")
        self.btn_load_a.clicked.connect(self._on_load_a)
        layout.addWidget(self.btn_load_a)

        self.btn_load_b = QPushButton("从单帧解析载入 B")
        set_btn(self.btn_load_b, "secondary")
        set_btn_icon(self.btn_load_b, "open")
        self.btn_load_b.clicked.connect(self._on_load_b)
        layout.addWidget(self.btn_load_b)

        layout.addStretch()

        # 图例
        p = self._pal()
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(12)
        for text, key in [("相同", "same_bg"), ("修改", "mod_bg"), ("B新增", "add_bg")]:
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(f"background-color: {p[key]}; border: 1px solid {p['swatch_border']}; border-radius: 2px;")
            self._legend_swatches.append((swatch, key))
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {p['mid']}; font-size: 11px;")
            self._legend_labels.append(lbl)
            legend_layout.addWidget(swatch)
            legend_layout.addWidget(lbl)
        layout.addLayout(legend_layout)

        self.btn_export = QPushButton("导出对比报告")
        set_btn(self.btn_export, "secondary")
        set_btn_icon(self.btn_export, "export")
        self.btn_export.clicked.connect(self._on_export)
        layout.addWidget(self.btn_export)

        return w

    def _build_input_area(self) -> QWidget:
        p = self._pal()
        w = QWidget()
        w.setStyleSheet(f"background-color: {p['panel_bg']}; border: 1px solid {p['border']}; border-radius: 4px;")
        self._input_panel = w
        layout = QHBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # 报文 A
        group_a = QGroupBox()
        group_a.setStyleSheet(self._group_qss(p))
        self._group_a = group_a
        va = QVBoxLayout(group_a)
        va.setContentsMargins(4, 4, 4, 4)
        va.setSpacing(2)

        header_a = QHBoxLayout()
        self.lbl_title_a = QLabel("<b>报文 A（基准）</b>")
        self.lbl_title_a.setStyleSheet(f"color: {p['title']};")
        header_a.addWidget(self.lbl_title_a)
        header_a.addStretch()
        self.lbl_info_a = QLabel("")
        self.lbl_info_a.setStyleSheet(f"color: {p['dim']}; font-size: 11px;")
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
        group_b.setStyleSheet(self._group_qss(p))
        self._group_b = group_b
        vb = QVBoxLayout(group_b)
        vb.setContentsMargins(4, 4, 4, 4)
        vb.setSpacing(2)

        header_b = QHBoxLayout()
        self.lbl_title_b = QLabel("<b>报文 B（对比）</b>")
        self.lbl_title_b.setStyleSheet(f"color: {p['title']};")
        header_b.addWidget(self.lbl_title_b)
        header_b.addStretch()
        self.lbl_info_b = QLabel("")
        self.lbl_info_b.setStyleSheet(f"color: {p['dim']}; font-size: 11px;")
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
        p = self._pal()
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(f"color: {p['title']}; font-size: 12px;")
        layout.addWidget(self.lbl_summary)

        layout.addStretch()

        # 选项
        self.chk_field_align = QCheckBox("字段感知对齐")
        self.chk_field_align.setChecked(True)
        self.chk_field_align.setStyleSheet(f"color: {p['mid']}; font-size: 12px;")
        layout.addWidget(self.chk_field_align)

        self.chk_ignore_cs = QCheckBox("忽略校验和字节")
        self.chk_ignore_cs.setStyleSheet(f"color: {p['mid']}; font-size: 12px;")
        layout.addWidget(self.chk_ignore_cs)

        self.chk_ignore_seq = QCheckBox("忽略序列号")
        self.chk_ignore_seq.setStyleSheet(f"color: {p['mid']}; font-size: 12px;")
        layout.addWidget(self.chk_ignore_seq)

        self.chk_only_diff = QCheckBox("仅显示差异")
        self.chk_only_diff.setStyleSheet(f"color: {p['mid']}; font-size: 12px;")
        layout.addWidget(self.chk_only_diff)

        return w

    # =========================================================================
    # 主题适配
    # =========================================================================

    @staticmethod
    def _group_qss(p: Dict[str, str]) -> str:
        return (f"QGroupBox {{ border: 1px solid {p['border']}; border-radius: 4px; margin-top: 8px; }}"
                f"QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}")

    @staticmethod
    def _table_qss(p: Dict[str, str], item_padding: str, table_extra: str = "") -> str:
        return (f"QTableWidget {{ border: 1px solid {p['border']}; border-radius: 4px; {table_extra}}}"
                f"QTableWidget::item {{ {item_padding} }}"
                f"QHeaderView::section {{ background-color: {p['header_bg']}; color: {p['header_fg']}; "
                f"padding: 4px 8px; border: 1px solid {p['border']}; font-weight: bold; }}")

    def restyle_for_theme(self, dark: bool):
        """主题切换后重设本页所有硬编码样式（浅色/暗色）"""
        self._dark = bool(dark)
        p = self._pal()
        try:
            self._placeholder.setStyleSheet(f"color: {p['dim']}; font-size: 14px; padding: 40px;")
        except RuntimeError:
            pass  # 对比过后占位标签已被销毁
        self._input_panel.setStyleSheet(
            f"background-color: {p['panel_bg']}; border: 1px solid {p['border']}; border-radius: 4px;")
        grp = self._group_qss(p)
        self._group_a.setStyleSheet(grp)
        self._group_b.setStyleSheet(grp)
        self.lbl_title_a.setStyleSheet(f"color: {p['title']};")
        self.lbl_title_b.setStyleSheet(f"color: {p['title']};")
        self.lbl_info_a.setStyleSheet(f"color: {p['dim']}; font-size: 11px;")
        self.lbl_info_b.setStyleSheet(f"color: {p['dim']}; font-size: 11px;")
        self.lbl_summary.setStyleSheet(f"color: {p['title']}; font-size: 12px;")
        for chk in (self.chk_field_align, self.chk_ignore_cs, self.chk_ignore_seq, self.chk_only_diff):
            chk.setStyleSheet(f"color: {p['mid']}; font-size: 12px;")
        for swatch, key in self._legend_swatches:
            swatch.setStyleSheet(
                f"background-color: {p[key]}; border: 1px solid {p['swatch_border']}; border-radius: 2px;")
        for lbl in self._legend_labels:
            lbl.setStyleSheet(f"color: {p['mid']}; font-size: 11px;")
        if self._last_result is not None:
            self._render_result(self._last_result, emit=False)

    # =========================================================================
    # 对比结果渲染
    # =========================================================================

    def _clear_result_area(self):
        """清除结果区域的所有内容"""
        while self._result_layout.count():
            item = self._result_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_result(self, result: Dict[str, Any], emit: bool = True):
        """渲染对比结果到界面"""
        self._clear_result_area()
        self._last_result = result

        if not result.get('success'):
            err = QLabel(f"  对比失败：{result.get('error', '未知错误')}")
            err.setStyleSheet(f"color: {self._pal()['mod_fg']}; font-size: 13px; padding: 10px;")
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

        if emit:
            self.diff_completed.emit(result)

    def _build_byte_diff_section(self, byte_diff: list) -> QWidget:
        """构建字节级对比区"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 标题行（含最大化按钮）
        p = self._pal()
        title_row = QHBoxLayout()
        title = QLabel("字节级对比（按字段对齐）")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {p['title']}; padding: 2px 0;")
        title_row.addWidget(title)
        title_row.addStretch()

        btn_max = QPushButton("⊞")
        btn_max.setFixedSize(24, 24)
        btn_max.setToolTip("最大化显示表格")
        set_btn(btn_max, "ghost", "sm")
        btn_max.clicked.connect(lambda: self._open_table_popup(
            "字节级对比详情", lambda: self._build_byte_diff_table(byte_diff)
        ))
        title_row.addWidget(btn_max)
        layout.addLayout(title_row)

        subtitle = QLabel('— 协议感知：长度不同的帧也能把"校验和"对"校验和"、"结束符"对"结束符"')
        subtitle.setStyleSheet(f"color: {p['dim']}; font-size: 11px;")
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
        table.setStyleSheet(self._table_qss(
            self._pal(), "padding: 3px;", "font-family: Consolas, monospace; font-size: 12px; "))

        for row, bd in enumerate(byte_diff):
            # 字段名
            name_item = QTableWidgetItem(bd['field_name'])
            name_item.setFont(QFont("Microsoft YaHei", 9))
            name_item.setBackground(QColor(self._pal()['header_bg']))
            name_item.setForeground(QColor(self._pal()['header_fg']))
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
        p = self._pal()
        dim, mod_bg, mod_fg = p["dim"], p["mod_bg"], p["mod_fg"]
        add_bg, add_fg = p["add_bg"], p["add_fg"]
        del_bg, del_fg = p["del_bg"], p["del_fg"]
        parts = []
        for d in byte_details:
            byte_val = d.get(f'byte_{side}')
            status = d['status']
            if byte_val is None:
                parts.append(f'<span style="color:{dim};">—</span>')
            elif status == 'modified':
                parts.append(f'<span style="background:{mod_bg}; color:{mod_fg}; font-weight:bold; '
                             f'padding:1px 3px; border-radius:2px;">{byte_val:02X}</span>')
            elif status == 'added':
                parts.append(f'<span style="background:{add_bg}; color:{add_fg}; font-weight:bold; '
                             f'padding:1px 3px; border-radius:2px;">{byte_val:02X}</span>')
            elif status == 'removed':
                parts.append(f'<span style="background:{del_bg}; color:{del_fg}; '
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
        p = self._pal()
        title_row = QHBoxLayout()
        title = QLabel("字段级语义对比")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {p['title']}; padding: 2px 0;")
        title_row.addWidget(title)
        title_row.addStretch()

        btn_max = QPushButton("⊞")
        btn_max.setFixedSize(24, 24)
        btn_max.setToolTip("最大化显示表格")
        set_btn(btn_max, "ghost", "sm")
        btn_max.clicked.connect(lambda: self._open_table_popup(
            "字段级对比详情", lambda: self._build_field_diff_table(field_diff)
        ))
        title_row.addWidget(btn_max)
        layout.addLayout(title_row)

        subtitle = QLabel('— 直接告诉你"哪个字段的含义变了"，而不只是看字节')
        subtitle.setStyleSheet(f"color: {p['dim']}; font-size: 11px;")
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
        table.setStyleSheet(self._table_qss(self._pal(), "padding: 4px 6px;", "font-size: 12px; "))

        p = self._pal()
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
                diff_item.setBackground(QColor(p['del_bg']))
                diff_item.setForeground(QColor(96, 125, 139))
            elif diff_type == '修改':
                diff_item.setBackground(QColor(p['mod_bg']))
                diff_item.setForeground(QColor(p['mod_fg']))
                diff_item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            elif diff_type == 'B新增':
                diff_item.setBackground(QColor(p['add_bg']))
                diff_item.setForeground(QColor(p['add_fg']))
                diff_item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            elif diff_type == 'A独有':
                diff_item.setBackground(QColor(p['del_bg']))
                diff_item.setForeground(QColor(p['del_fg']))
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
        title.setStyleSheet(f"color: {self._pal()['title']}; padding: 2px 0;")
        layout.addWidget(title)

        # 用 QTextEdit 展示，带左侧橙色竖线装饰
        p = self._pal()
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Microsoft YaHei", 10))
        text_edit.setFrameShape(QFrame.Shape.StyledPanel)
        text_edit.setStyleSheet(
            f"QTextEdit {{ border: 1px solid {p['border']}; border-left: 3px solid #FF9800; "
            f"border-radius: 4px; background-color: {p['explain_bg']}; padding: 8px 12px; }}"
        )

        html = "<ul style='margin: 4px 0; padding-left: 20px;'>"
        for line in explanation:
            # 将 code 部分用 <code> 标签包裹
            line = line.replace('0x', f'<code style="background:{p["code_bg"]}; padding:0 4px; border-radius:2px; color:{p["mod_fg"]};">0x')
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
