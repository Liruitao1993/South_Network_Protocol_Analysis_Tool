"""GUI通用工具：中文右键菜单、可缩放表格等"""

from PySide6.QtWidgets import QLineEdit, QTextEdit, QTableWidget
from PySide6.QtCore import Qt
from typing import Optional


class ZoomableTableWidget(QTableWidget):
    """支持 Ctrl+滚轮整体缩放的表格（类 Excel）。

    缩放 = 字号 + 行高同步（列宽保持，避免破坏固定列布局）；
    Ctrl+0 恢复缩放前基准。缩放为 per-table 覆盖，
    全局字体设置变更后表格回到基准字号。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._zoom_base: Optional[tuple] = None  # (pointSizeF, defaultSectionSize)

    def _zoom_start(self):
        """首次缩放前记录基准（缩放前字体为基准字号）"""
        if self._zoom_base is None:
            self._zoom_base = (self.font().pointSizeF() or 9.0,
                               self.verticalHeader().defaultSectionSize() or 20)

    def _apply_zoom(self, factor: float):
        self._zoom_start()
        f = self.font()
        f.setPointSizeF(max(5.0, min(24.0, (f.pointSizeF() or 9.0) * factor)))
        self.setFont(f)
        vh = self.verticalHeader()
        vh.setDefaultSectionSize(max(6, int(vh.defaultSectionSize() * factor)))

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            y = e.angleDelta().y()
            if y != 0:
                self._apply_zoom(1.1 if y > 0 else 0.9)
                e.accept()
                return
        super().wheelEvent(e)

    def keyPressEvent(self, e):
        if (e.modifiers() & Qt.KeyboardModifier.ControlModifier
                and e.key() == Qt.Key.Key_0 and self._zoom_base is not None):
            base_pt, base_row = self._zoom_base
            f = self.font()
            f.setPointSizeF(base_pt)
            self.setFont(f)
            self.verticalHeader().setDefaultSectionSize(base_row)
            self._zoom_base = None
            e.accept()
            return
        super().keyPressEvent(e)


def setup_chinese_context_menu(widget):
    """为单行/多行文本输入控件设置中文右键菜单"""
    if not isinstance(widget, (QLineEdit, QTextEdit)):
        return
    # 若已有自定义右键菜单，则不覆盖
    if widget.contextMenuPolicy() == Qt.CustomContextMenu:
        return

    def _show_menu(pos):
        menu = widget.createStandardContextMenu()
        menu.setStyleSheet("QMenu { background-color: white; color: black; } QMenu::item:selected { background-color: #e3f2fd; }")
        text_map = {
            "Undo": "撤销",
            "Redo": "恢复",
            "Cut": "剪切",
            "Copy": "复制",
            "Paste": "粘贴",
            "Delete": "删除",
            "Select All": "全选",
            "Undo\tCtrl+Z": "撤销\tCtrl+Z",
            "Redo\tCtrl+Y": "恢复\tCtrl+Y",
            "Cut\tCtrl+X": "剪切\tCtrl+X",
            "Copy\tCtrl+C": "复制\tCtrl+C",
            "Paste\tCtrl+V": "粘贴\tCtrl+V",
            "Delete": "删除",
            "Select All\tCtrl+A": "全选\tCtrl+A",
        }
        for action in menu.actions():
            original = action.text().replace("&", "")
            if original in text_map:
                action.setText(text_map[original])
        menu.exec(widget.mapToGlobal(pos))

    widget.setContextMenuPolicy(Qt.CustomContextMenu)
    widget.customContextMenuRequested.connect(_show_menu)


def apply_chinese_context_menus(parent_widget):
    """为parent_widget及其子控件中所有QLineEdit/QTextEdit设置中文右键菜单"""
    seen = set()
    for cls in (QLineEdit, QTextEdit):
        for widget in parent_widget.findChildren(cls):
            wid = id(widget)
            if wid not in seen:
                seen.add(wid)
                setup_chinese_context_menu(widget)
