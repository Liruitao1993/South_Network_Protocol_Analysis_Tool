"""GUI通用工具：中文右键菜单等"""

from PySide6.QtWidgets import QLineEdit, QTextEdit
from PySide6.QtCore import Qt


def setup_chinese_context_menu(widget):
    """为单行/多行文本输入控件设置中文右键菜单"""
    if not isinstance(widget, (QLineEdit, QTextEdit)):
        return
    # 若已有自定义右键菜单，则不覆盖
    if widget.contextMenuPolicy() == Qt.CustomContextMenu:
        return

    def _show_menu(pos):
        menu = widget.createStandardContextMenu()
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
