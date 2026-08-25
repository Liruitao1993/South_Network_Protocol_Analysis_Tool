"""
主题与字体设置模块（1.10.0 新增）
=================================
- THEMES         内置主题注册表（Qt 原生风格 + QSS 自定义主题）
- ThemeManager   主题/字体应用与 config.json 读写
- ThemeSettingsDialog  主题与字体设置对话框（修改即时预览，确定保存 / 取消还原）

主题 id：
- default      默认（浅色）：Fusion + 白色样式表（1.10.0 前的原主题，作为默认）
- fusion       Fusion 经典：纯 Qt 内置 Fusion，无自定义样式表
- dark         Fusion 暗色：完整暗色样式表
- glass        毛玻璃：半透明磨砂面板样式 + Windows 亚克力背景模糊（仅 Win10/11）
- windows      Windows 原生风格
- windowsvista Windows Vista 原生风格

约定：QSS 应用在 QApplication 级（弹窗/文件对话框等顶级窗口跟随主题）。
组件内部的对象级 setStyleSheet 优先于应用级 QSS，暗色下部分组件保留自身配色。
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QColorDialog, QDialog, QFileDialog, QFontComboBox,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox,
    QStyleFactory, QVBoxLayout,
)

from system_integration.system_settings import SystemIntegrationSettings

# ---------------------------------------------------------------------------
# 浅色主题样式表（原 MainWindow.apply_styles 内容，迁移至应用级）
# ---------------------------------------------------------------------------
LIGHT_QSS = """
    /* ========== 全局基础 ========== */
    * {
        color: #000000;
    }
    QWidget {
        background-color: #ffffff;
        color: #000000;
    }
    QMainWindow {
        background-color: #f5f5f5;
    }

    /* ========== 对话框 / 弹窗 ========== */
    QDialog {
        background-color: #ffffff;
        color: #000000;
    }
    QMessageBox {
        background-color: #ffffff;
        color: #000000;
    }
    QMessageBox QLabel {
        color: #000000;
        background-color: transparent;
    }
    QMessageBox QPushButton {
        background-color: #2196F3;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 20px;
        font-weight: bold;
        min-width: 80px;
    }
    QMessageBox QPushButton:hover {
        background-color: #1976D2;
    }

    /* ========== 右键菜单 ========== */
    QMenu {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #cccccc;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 30px 6px 20px;
        background-color: #ffffff;
        color: #000000;
    }
    QMenu::item:selected {
        background-color: #e3f2fd;
        color: #000000;
    }
    QMenu::separator {
        height: 1px;
        background-color: #e0e0e0;
        margin: 4px 8px;
    }

    /* ========== 工具提示 ========== */
    QToolTip {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #cccccc;
        padding: 4px;
    }

    /* ========== 滚动条 ========== */
    QScrollBar:vertical {
        background-color: #f5f5f5;
        width: 10px;
        border: none;
    }
    QScrollBar::handle:vertical {
        background-color: #c0c0c0;
        min-height: 30px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #a0a0a0;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
    QScrollBar:horizontal {
        background-color: #f5f5f5;
        height: 10px;
        border: none;
    }
    QScrollBar::handle:horizontal {
        background-color: #c0c0c0;
        min-width: 30px;
        border-radius: 5px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #a0a0a0;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
    }

    /* ========== 分组框 ========== */
    QGroupBox {
        font-weight: bold;
        border: 1px solid #cccccc;
        border-radius: 4px;
        margin-top: 6px;
        padding-top: 6px;
        background-color: #ffffff;
        color: #000000;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: #000000;
    }

    /* ========== 按钮 ========== */
    QPushButton {
        background-color: #2196F3;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 4px 12px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #1976D2;
    }
    QPushButton:pressed {
        background-color: #0D47A1;
    }
    QPushButton:disabled {
        background-color: #cccccc;
        color: #888888;
    }
    QPushButton#secondary {
        background-color: #757575;
    }

    /* ========== 文本编辑框 ========== */
    QTextEdit {
        border: 1px solid #cccccc;
        border-radius: 4px;
        padding: 5px;
        background-color: #ffffff;
        font-family: Consolas, Monaco, monospace;
        color: #000000;
    }
    QPlainTextEdit {
        border: 1px solid #cccccc;
        border-radius: 4px;
        padding: 5px;
        background-color: #ffffff;
        color: #000000;
    }

    /* ========== 行编辑框 ========== */
    QLineEdit {
        border: 1px solid #cccccc;
        border-radius: 4px;
        padding: 2px 6px;
        background-color: #ffffff;
        color: #000000;
    }

    /* ========== 表格 ========== */
    QTableWidget {
        border: 1px solid #cccccc;
        border-radius: 4px;
        background-color: #ffffff;
        gridline-color: #e0e0e0;
        color: #000000;
        font-size: 9pt;
    }
    QTableWidget::item:!alternate {
        background-color: #ffffff;
        color: #000000;
        padding: 2px 4px;
    }
    QTableWidget::item:alternate {
        background-color: #e8e8e8;
        color: #000000;
        padding: 2px 4px;
    }
    QTableWidget::item:selected {
        background-color: #2196F3;
        color: white;
    }
    QHeaderView::section {
        background-color: #f5f5f5;
        padding: 4px 8px;
        border: 1px solid #d0d0d0;
        font-weight: bold;
        color: #000000;
        font-size: 9pt;
    }

    /* ========== 标签 ========== */
    QLabel {
        color: #000000;
        background-color: transparent;
    }

    /* ========== 选项卡 ========== */
    QTabWidget::pane {
        border: 1px solid #cccccc;
        border-radius: 4px;
        background-color: #ffffff;
    }
    QTabBar::tab {
        padding: 3px 10px;
        margin-right: 2px;
        border: 1px solid #cccccc;
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        background-color: #f5f5f5;
        color: #000000;
    }
    QTabBar::tab:selected {
        background-color: #2196F3;
        color: white;
    }
    QTabBar::tab:hover:!selected {
        background-color: #e0e0e0;
    }

    /* ========== 下拉框 ========== */
    QComboBox {
        border: 1px solid #888;
        border-radius: 2px;
        padding: 2px 18px 2px 6px;
        background-color: #ffffff;
        color: #000000;
        min-height: 18px;
    }
    QComboBox:hover {
        border: 1px solid #666;
    }
    QComboBox:focus {
        border: 1px solid #6699cc;
    }
    QComboBox::drop-down {
        border: none;
        width: 18px;
    }
    QComboBox::down-arrow {
        width: 0;
        height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid #666;
    }
    QComboBox QAbstractItemView {
        border: 1px solid #888;
        background-color: #ffffff;
        selection-background-color: #80b8e8;
        selection-color: #000000;
    }
    QComboBox QListView::item {
        background-color: #ffffff;
        color: #000000;
        padding: 3px 6px;
    }
    QComboBox QListView::item:selected {
        background-color: #80b8e8;
        color: #000000;
    }
    QComboBox QListView::item:hover {
        background-color: #e3f2fd;
        color: #000000;
    }

    /* ========== 数值输入框 ========== */
    QSpinBox, QDoubleSpinBox {
        border: 1px solid #888;
        border-radius: 2px;
        padding: 2px 6px;
        background-color: #ffffff;
        color: #000000;
    }

    /* ========== 复选框 / 单选框 ========== */
    QCheckBox, QRadioButton {
        color: #000000;
        background-color: transparent;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 1px solid black;
        background-color: white;
    }
    QCheckBox::indicator:checked {
        background-color: #2196F3;
        border: 1px solid black;
    }
    QCheckBox::indicator:indeterminate {
        background-color: #90CAF9;
        border: 1px solid black;
    }

    /* ========== 文件对话框 ========== */
    QFileDialog {
        background-color: #ffffff;
        color: #000000;
    }

    /* ========== 输入对话框 ========== */
    QInputDialog {
        background-color: #ffffff;
        color: #000000;
    }

    /* ========== 菜单栏 ========== */
    QMenuBar {
        background-color: #f5f5f5;
        color: #000000;
        border-bottom: 1px solid #d0d0d0;
        padding: 2px;
    }
    QMenuBar::item {
        padding: 4px 10px;
        background-color: transparent;
    }
    QMenuBar::item:selected {
        background-color: #e0e0e0;
    }
"""

# ---------------------------------------------------------------------------
# 暗色主题样式表（Fusion 暗色）
# ---------------------------------------------------------------------------
DARK_QSS = """
    /* ========== 全局基础 ========== */
    * {
        color: #e0e0e0;
    }
    QWidget {
        background-color: #2b2b2b;
        color: #e0e0e0;
    }
    QMainWindow {
        background-color: #252526;
    }

    /* ========== 对话框 / 弹窗 ========== */
    QDialog {
        background-color: #2b2b2b;
        color: #e0e0e0;
    }
    QMessageBox {
        background-color: #2b2b2b;
        color: #e0e0e0;
    }
    QMessageBox QLabel {
        color: #e0e0e0;
        background-color: transparent;
    }
    QMessageBox QPushButton {
        background-color: #42a5f5;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 20px;
        font-weight: bold;
        min-width: 80px;
    }
    QMessageBox QPushButton:hover {
        background-color: #1e88e5;
    }

    /* ========== 右键菜单 ========== */
    QMenu {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border: 1px solid #555555;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 30px 6px 20px;
        background-color: transparent;
        color: #e0e0e0;
    }
    QMenu::item:selected {
        background-color: #4a4a4a;
        color: #e0e0e0;
    }
    QMenu::separator {
        height: 1px;
        background-color: #555555;
        margin: 4px 8px;
    }

    /* ========== 工具提示 ========== */
    QToolTip {
        background-color: #3a3a3a;
        color: #e0e0e0;
        border: 1px solid #555555;
        padding: 4px;
    }

    /* ========== 滚动条 ========== */
    QScrollBar:vertical {
        background-color: #2b2b2b;
        width: 10px;
        border: none;
    }
    QScrollBar::handle:vertical {
        background-color: #666666;
        min-height: 30px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #808080;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
    QScrollBar:horizontal {
        background-color: #2b2b2b;
        height: 10px;
        border: none;
    }
    QScrollBar::handle:horizontal {
        background-color: #666666;
        min-width: 30px;
        border-radius: 5px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #808080;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
    }

    /* ========== 分组框 ========== */
    QGroupBox {
        font-weight: bold;
        border: 1px solid #555555;
        border-radius: 4px;
        margin-top: 6px;
        padding-top: 6px;
        background-color: #2b2b2b;
        color: #e0e0e0;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: #e0e0e0;
    }

    /* ========== 按钮 ========== */
    QPushButton {
        background-color: #42a5f5;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 4px 12px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #1e88e5;
    }
    QPushButton:pressed {
        background-color: #1565c0;
    }
    QPushButton:disabled {
        background-color: #444444;
        color: #888888;
    }
    QPushButton#secondary {
        background-color: #616161;
    }

    /* ========== 文本编辑框 ========== */
    QTextEdit {
        border: 1px solid #555555;
        border-radius: 4px;
        padding: 5px;
        background-color: #1e1e1e;
        font-family: Consolas, Monaco, monospace;
        color: #e0e0e0;
    }
    QPlainTextEdit {
        border: 1px solid #555555;
        border-radius: 4px;
        padding: 5px;
        background-color: #1e1e1e;
        color: #e0e0e0;
    }

    /* ========== 行编辑框 ========== */
    QLineEdit {
        border: 1px solid #555555;
        border-radius: 4px;
        padding: 2px 6px;
        background-color: #1e1e1e;
        color: #e0e0e0;
    }

    /* ========== 表格 ========== */
    QTableWidget {
        border: 1px solid #555555;
        border-radius: 4px;
        background-color: #2b2b2b;
        gridline-color: #444444;
        color: #e0e0e0;
        font-size: 9pt;
    }
    QTableWidget::item:!alternate {
        background-color: #2b2b2b;
        color: #e0e0e0;
        padding: 2px 4px;
    }
    QTableWidget::item:alternate {
        background-color: #333333;
        color: #e0e0e0;
        padding: 2px 4px;
    }
    QTableWidget::item:selected {
        background-color: #42a5f5;
        color: white;
    }
    QHeaderView::section {
        background-color: #3c3c3c;
        padding: 4px 8px;
        border: 1px solid #555555;
        font-weight: bold;
        color: #e0e0e0;
        font-size: 9pt;
    }

    /* ========== 标签 ========== */
    QLabel {
        color: #e0e0e0;
        background-color: transparent;
    }

    /* ========== 选项卡 ========== */
    QTabWidget::pane {
        border: 1px solid #555555;
        border-radius: 4px;
        background-color: #2b2b2b;
    }
    QTabBar::tab {
        padding: 3px 10px;
        margin-right: 2px;
        border: 1px solid #555555;
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        background-color: #3c3c3c;
        color: #b0b0b0;
    }
    QTabBar::tab:selected {
        background-color: #42a5f5;
        color: white;
    }
    QTabBar::tab:hover:!selected {
        background-color: #4a4a4a;
    }

    /* ========== 下拉框 ========== */
    QComboBox {
        border: 1px solid #555555;
        border-radius: 2px;
        padding: 2px 18px 2px 6px;
        background-color: #1e1e1e;
        color: #e0e0e0;
        min-height: 18px;
    }
    QComboBox:hover {
        border: 1px solid #777777;
    }
    QComboBox:focus {
        border: 1px solid #42a5f5;
    }
    QComboBox::drop-down {
        border: none;
        width: 18px;
    }
    QComboBox::down-arrow {
        width: 0;
        height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid #aaaaaa;
    }
    QComboBox QAbstractItemView {
        border: 1px solid #555555;
        background-color: #2d2d2d;
        selection-background-color: #42a5f5;
        selection-color: #ffffff;
    }
    QComboBox QListView::item {
        background-color: #2d2d2d;
        color: #e0e0e0;
        padding: 3px 6px;
    }
    QComboBox QListView::item:selected {
        background-color: #42a5f5;
        color: #ffffff;
    }
    QComboBox QListView::item:hover {
        background-color: #4a4a4a;
        color: #e0e0e0;
    }

    /* ========== 数值输入框 ========== */
    QSpinBox, QDoubleSpinBox {
        border: 1px solid #555555;
        border-radius: 2px;
        padding: 2px 6px;
        background-color: #1e1e1e;
        color: #e0e0e0;
    }

    /* ========== 复选框 / 单选框 ========== */
    QCheckBox, QRadioButton {
        color: #e0e0e0;
        background-color: transparent;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 1px solid #888888;
        background-color: #2d2d2d;
    }
    QCheckBox::indicator:checked {
        background-color: #42a5f5;
        border: 1px solid #888888;
    }
    QCheckBox::indicator:indeterminate {
        background-color: #555555;
        border: 1px solid #888888;
    }

    /* ========== 文件对话框 ========== */
    QFileDialog {
        background-color: #2b2b2b;
        color: #e0e0e0;
    }

    /* ========== 输入对话框 ========== */
    QInputDialog {
        background-color: #2b2b2b;
        color: #e0e0e0;
    }

    /* ========== 菜单栏 ========== */
    QMenuBar {
        background-color: #252526;
        color: #e0e0e0;
        border-bottom: 1px solid #444444;
        padding: 2px;
    }
    QMenuBar::item {
        padding: 4px 10px;
        background-color: transparent;
    }
    QMenuBar::item:selected {
        background-color: #4a4a4a;
    }
"""


# ---------------------------------------------------------------------------
# 毛玻璃主题样式表（Frosted Glass）
# ---------------------------------------------------------------------------
# 主要表面用 rgba 半透明白，配合 Windows 亚克力背景模糊（ThemeManager 通过
# SetWindowCompositionAttribute 开启）呈现毛玻璃效果；非 Windows / 开启失败时
# 退化为柔和的半透明浅色面板，仍然可用。
GLASS_QSS = """
    /* ========== 全局基础 ========== */
    * {
        color: #1f2937;
    }
    QWidget {
        background-color: rgba(255, 255, 255, 150);
        color: #1f2937;
    }
    QMainWindow {
        background-color: rgba(240, 245, 255, 110);
    }

    /* ========== 对话框 / 弹窗 ========== */
    QDialog {
        background-color: rgba(248, 250, 255, 230);
        color: #1f2937;
    }
    QMessageBox {
        background-color: rgba(248, 250, 255, 235);
        color: #1f2937;
    }
    QMessageBox QLabel {
        color: #1f2937;
        background-color: transparent;
    }
    QMessageBox QPushButton {
        background-color: rgba(59, 130, 246, 220);
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 20px;
        font-weight: bold;
        min-width: 80px;
    }
    QMessageBox QPushButton:hover {
        background-color: rgba(37, 99, 235, 230);
    }

    /* ========== 右键菜单 ========== */
    QMenu {
        background-color: rgba(250, 251, 255, 235);
        color: #1f2937;
        border: 1px solid rgba(180, 200, 235, 200);
        border-radius: 8px;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 30px 6px 20px;
        background-color: transparent;
        color: #1f2937;
        border-radius: 5px;
    }
    QMenu::item:selected {
        background-color: rgba(59, 130, 246, 60);
        color: #1f2937;
    }
    QMenu::separator {
        height: 1px;
        background-color: rgba(160, 180, 220, 140);
        margin: 4px 8px;
    }

    /* ========== 工具提示 ========== */
    QToolTip {
        background-color: rgba(250, 251, 255, 245);
        color: #1f2937;
        border: 1px solid rgba(160, 180, 220, 200);
        border-radius: 4px;
        padding: 4px;
    }

    /* ========== 滚动条 ========== */
    QScrollBar:vertical {
        background-color: rgba(255, 255, 255, 60);
        width: 10px;
        border: none;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background-color: rgba(120, 150, 200, 150);
        min-height: 30px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: rgba(90, 120, 180, 190);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
    QScrollBar:horizontal {
        background-color: rgba(255, 255, 255, 60);
        height: 10px;
        border: none;
        border-radius: 5px;
    }
    QScrollBar::handle:horizontal {
        background-color: rgba(120, 150, 200, 150);
        min-width: 30px;
        border-radius: 5px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: rgba(90, 120, 180, 190);
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
    }

    /* ========== 分组框 ========== */
    QGroupBox {
        font-weight: bold;
        border: 1px solid rgba(200, 215, 240, 190);
        border-radius: 8px;
        margin-top: 6px;
        padding-top: 6px;
        background-color: rgba(255, 255, 255, 120);
        color: #1f2937;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: #2563eb;
    }

    /* ========== 按钮 ========== */
    QPushButton {
        background-color: rgba(59, 130, 246, 210);
        color: white;
        border: none;
        border-radius: 6px;
        padding: 4px 12px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: rgba(37, 99, 235, 225);
    }
    QPushButton:pressed {
        background-color: rgba(29, 78, 216, 235);
    }
    QPushButton:disabled {
        background-color: rgba(203, 213, 225, 180);
        color: #64748b;
    }
    QPushButton#secondary {
        background-color: rgba(100, 116, 139, 200);
    }

    /* ========== 文本编辑框 ========== */
    QTextEdit {
        border: 1px solid rgba(160, 180, 220, 180);
        border-radius: 6px;
        padding: 5px;
        background-color: rgba(255, 255, 255, 190);
        font-family: Consolas, Monaco, monospace;
        color: #1f2937;
    }
    QPlainTextEdit {
        border: 1px solid rgba(160, 180, 220, 180);
        border-radius: 6px;
        padding: 5px;
        background-color: rgba(255, 255, 255, 190);
        color: #1f2937;
    }

    /* ========== 行编辑框 ========== */
    QLineEdit {
        border: 1px solid rgba(160, 180, 220, 180);
        border-radius: 6px;
        padding: 2px 6px;
        background-color: rgba(255, 255, 255, 190);
        color: #1f2937;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 1px solid rgba(59, 130, 246, 200);
    }

    /* ========== 表格 ========== */
    QTableWidget {
        border: 1px solid rgba(180, 200, 235, 180);
        border-radius: 6px;
        background-color: rgba(255, 255, 255, 170);
        gridline-color: rgba(200, 214, 235, 160);
        color: #1f2937;
        font-size: 9pt;
    }
    QTableWidget::item:!alternate {
        background-color: rgba(255, 255, 255, 40);
        color: #1f2937;
        padding: 2px 4px;
    }
    QTableWidget::item:alternate {
        background-color: rgba(219, 234, 254, 100);
        color: #1f2937;
        padding: 2px 4px;
    }
    QTableWidget::item:selected {
        background-color: rgba(59, 130, 246, 200);
        color: white;
    }
    QHeaderView::section {
        background-color: rgba(226, 236, 252, 190);
        padding: 4px 8px;
        border: 1px solid rgba(180, 200, 235, 160);
        font-weight: bold;
        color: #1f2937;
        font-size: 9pt;
    }

    /* ========== 标签 ========== */
    QLabel {
        color: #1f2937;
        background-color: transparent;
    }

    /* ========== 选项卡 ========== */
    QTabWidget::pane {
        border: 1px solid rgba(180, 200, 235, 180);
        border-radius: 6px;
        background-color: rgba(255, 255, 255, 110);
    }
    QTabBar::tab {
        padding: 3px 10px;
        margin-right: 2px;
        border: 1px solid rgba(180, 200, 235, 160);
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        background-color: rgba(255, 255, 255, 90);
        color: #475569;
    }
    QTabBar::tab:selected {
        background-color: rgba(59, 130, 246, 210);
        color: white;
    }
    QTabBar::tab:hover:!selected {
        background-color: rgba(219, 234, 254, 150);
    }

    /* ========== 下拉框 ========== */
    QComboBox {
        border: 1px solid rgba(160, 180, 220, 180);
        border-radius: 6px;
        padding: 2px 18px 2px 6px;
        background-color: rgba(255, 255, 255, 190);
        color: #1f2937;
        min-height: 18px;
    }
    QComboBox:hover {
        border: 1px solid rgba(120, 150, 200, 200);
    }
    QComboBox:focus {
        border: 1px solid rgba(59, 130, 246, 200);
    }
    QComboBox::drop-down {
        border: none;
        width: 18px;
    }
    QComboBox::down-arrow {
        width: 0;
        height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid #64748b;
    }
    QComboBox QAbstractItemView {
        border: 1px solid rgba(160, 180, 220, 200);
        background-color: rgba(250, 251, 255, 240);
        selection-background-color: rgba(59, 130, 246, 160);
        selection-color: #1f2937;
    }
    QComboBox QListView::item {
        background-color: transparent;
        color: #1f2937;
        padding: 3px 6px;
    }
    QComboBox QListView::item:selected {
        background-color: rgba(59, 130, 246, 120);
        color: #1f2937;
    }
    QComboBox QListView::item:hover {
        background-color: rgba(219, 234, 254, 150);
        color: #1f2937;
    }

    /* ========== 数值输入框 ========== */
    QSpinBox, QDoubleSpinBox {
        border: 1px solid rgba(160, 180, 220, 180);
        border-radius: 6px;
        padding: 2px 6px;
        background-color: rgba(255, 255, 255, 190);
        color: #1f2937;
    }

    /* ========== 复选框 / 单选框 ========== */
    QCheckBox, QRadioButton {
        color: #1f2937;
        background-color: transparent;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 1px solid #94a3b8;
        border-radius: 3px;
        background-color: rgba(255, 255, 255, 220);
    }
    QCheckBox::indicator:checked {
        background-color: rgba(59, 130, 246, 220);
        border: 1px solid #2563eb;
    }
    QCheckBox::indicator:indeterminate {
        background-color: rgba(147, 197, 253, 220);
        border: 1px solid #2563eb;
    }

    /* ========== 文件对话框 ========== */
    QFileDialog {
        background-color: rgba(248, 250, 255, 230);
        color: #1f2937;
    }

    /* ========== 输入对话框 ========== */
    QInputDialog {
        background-color: rgba(248, 250, 255, 230);
        color: #1f2937;
    }

    /* ========== 菜单栏 ========== */
    QMenuBar {
        background-color: rgba(255, 255, 255, 90);
        color: #1f2937;
        border-bottom: 1px solid rgba(200, 214, 235, 160);
        padding: 2px;
    }
    QMenuBar::item {
        padding: 4px 10px;
        background-color: transparent;
        border-radius: 4px;
    }
    QMenuBar::item:selected {
        background-color: rgba(219, 234, 254, 180);
    }

    /* ========== 状态栏 ========== */
    QStatusBar {
        background-color: rgba(255, 255, 255, 90);
        color: #1f2937;
        border-top: 1px solid rgba(200, 214, 235, 160);
    }
"""

# 毛玻璃可调参数：透明度（0~100）/ 背景图路径（空=无，用着色）/ 玻璃着色
GLASS_DEFAULTS: Dict = {
    "opacity": 60,       # 基准透明度（GLASS_QSS 各 alpha 即按 60% 设计）
    "bg_image": "",
    "tint": "#f0f5ff",
}


def _hex_to_rgb(tint: str) -> Tuple[int, int, int]:
    """'#rrggbb' → (r, g, b)，非法时回退默认着色"""
    t = str(tint or "").lstrip("#")
    if len(t) == 6:
        try:
            return int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)
        except ValueError:
            pass
    return 240, 245, 255


def build_glass_qss(opacity: int = 60, tint: str = "#f0f5ff", bg_image: str = "") -> str:
    """按用户参数生成毛玻璃 QSS。

    - opacity: 0~100，整体缩放所有 rgba 通道的 alpha（>220 的近不透明弹窗保持原值）
    - tint: 无背景图时主窗口的玻璃着色；有背景图时作为图上叠加色
    - bg_image: 背景图路径（存在且可读时用 border-image 铺满主窗口）
    """
    import re
    opacity = max(0, min(100, int(opacity)))
    factor = opacity / 60.0  # GLASS_QSS 基准 = 60%

    def _scale(m):
        r, g, b, a = (int(m.group(i)) for i in range(1, 5))
        if a > 220:  # 菜单/弹窗等近不透明表面保持可读性
            return m.group(0)
        return f"rgba({r}, {g}, {b}, {min(255, round(a * factor))})"

    qss = re.sub(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", _scale, GLASS_QSS)

    # 主窗口背景：玻璃着色 or 背景图 + 低透明度着色叠加
    tr, tg, tb = _hex_to_rgb(tint)
    overlay_alpha = min(255, round(110 * factor))
    img_path = str(bg_image or "").strip()
    if img_path and Path(img_path).is_file():
        url = Path(img_path).as_posix()
        qss += f"""
    QMainWindow {{
        border-image: url({url}) 0 0 0 0 stretch stretch;
        background-color: rgba({tr}, {tg}, {tb}, {max(30, overlay_alpha // 3)});
    }}
"""
    else:
        qss += f"""
    QMainWindow {{
        background-color: rgba({tr}, {tg}, {tb}, {overlay_alpha});
    }}
"""
    return qss


# ---------------------------------------------------------------------------
# VISTA 原生主题补充：仅输入类控件强制浅色
# ---------------------------------------------------------------------------
# windowsvista 主题 qss 原本为 None（纯原生，跟随系统配色）。
# 系统深色模式下 QLineEdit/QTextEdit/QTableWidget 会渲染成深色背景。
# 此处只覆盖输入/表格控件的背景与文字，其余控件（按钮/菜单/标签等）
# 保持 windowsvista 原生风格不变。
VISTA_INPUT_QSS = """
    /* ===== 单行/多行输入 ===== */
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
        background-color: #ffffff;
        color: #000000;
        selection-background-color: #3399ff;
        selection-color: #ffffff;
    }
    QTextEdit, QPlainTextEdit {
        border: 1px solid #bbbbbb;
        padding: 2px;
    }
    /* ===== 下拉框（含弹出的列表） ===== */
    QComboBox {
        background-color: #ffffff;
        color: #000000;
    }
    QComboBox QAbstractItemView {
        background-color: #ffffff;
        color: #000000;
        selection-background-color: #3399ff;
        selection-color: #ffffff;
    }
    /* ===== 表格 / 列表 ===== */
    QTableWidget, QTableView, QTreeView, QListWidget {
        background-color: #ffffff;
        color: #000000;
        alternate-background-color: #f2f2f2;
        gridline-color: #d0d0d0;
        selection-background-color: #3399ff;
        selection-color: #ffffff;
    }
    QTableWidget::item, QTableView::item {
        padding: 2px;
    }
    QHeaderView::section {
        background-color: #f0f0f0;
        color: #000000;
        border: 1px solid #d0d0d0;
        padding: 4px;
    }
"""


# ---------------------------------------------------------------------------
# 主题注册表
# ---------------------------------------------------------------------------
# style: QStyleFactory 可创建的风格名；qss: 附加样式表（None = 纯原生风格）
THEMES: List[Dict] = [
    {
        "id": "default",
        "name": "默认（浅色）",
        "style": "Fusion",
        "qss": LIGHT_QSS,
        "desc": "当前默认主题：Fusion 浅色 + 白色样式表，与应用级弹窗样式统一",
    },
    {
        "id": "fusion",
        "name": "Fusion 经典",
        "style": "Fusion",
        "qss": None,
        "desc": "Qt 内置 Fusion 跨平台风格（不附加自定义样式表）",
    },
    {
        "id": "dark",
        "name": "Fusion 暗色",
        "style": "Fusion",
        "qss": DARK_QSS,
        "desc": "经典暗色主题：深色背景 + 高对比文字，适合夜间使用",
    },
    {
        "id": "glass",
        "name": "毛玻璃（Frosted Glass）",
        "style": "Fusion",
        "qss": GLASS_QSS,
        "desc": "半透明磨砂面板 + Windows 亚克力背景模糊（仅 Win10/11，其他环境退化为浅色半透明）",
        "win_blur": True,
    },
    {
        "id": "windows",
        "name": "Windows 原生",
        "style": "windows",
        "qss": None,
        "desc": "Windows 原生控件风格（无自定义样式表）",
    },
    {
        "id": "windowsvista",
        "name": "Windows Vista",
        "style": "windowsvista",
        "qss": VISTA_INPUT_QSS,
        "desc": "Windows Vista 原生控件风格（输入/表格控件强制浅色，避免深色系统下黑底）",
    },
]

THEME_IDS: List[str] = [t["id"] for t in THEMES]


def get_theme(theme_id: Optional[str]) -> Dict:
    """按 id 获取主题定义，未知 id 回退默认主题"""
    for t in THEMES:
        if t["id"] == theme_id:
            return t
    return THEMES[0]


def is_dark(theme_id: Optional[str]) -> bool:
    """是否为暗色主题（用于动态控件配色适配）"""
    return theme_id == "dark"


# ---------------------------------------------------------------------------
# Windows 亚克力背景模糊（毛玻璃主题专用）
# ---------------------------------------------------------------------------
def _set_windows_acrylic(win_id: int, enabled: bool, tint: str = "#f0f5ff") -> bool:
    """对单个窗口启用/关闭 Windows 亚克力模糊（SetWindowCompositionAttribute）。

    仅 Win10 1809+ / Win11 有效；失败返回 False（调用方应退化为普通半透明样式）。
    tint 为玻璃着色（#rrggbb），用作亚克力渐变着色。
    """
    import ctypes
    import sys
    if sys.platform != "win32" or not win_id:
        return False
    try:
        class ACCENT_POLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_uint),
                ("AccentFlags", ctypes.c_uint),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_uint),
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_uint),
                ("Data", ctypes.POINTER(ACCENT_POLICY)),
                ("SizeOfData", ctypes.c_size_t),
            ]

        policy = ACCENT_POLICY()
        if enabled:
            tr, tg, tb = _hex_to_rgb(tint)
            policy.AccentState = 4      # ACCENT_ENABLE_ACRYLICBLURBEHIND
            policy.AccentFlags = 2
            # ABGR：约 70% 不透明的玻璃着色
            policy.GradientColor = (0xB3 << 24) | (tb << 16) | (tg << 8) | tr
        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19             # WCA_ACCENT_POLICY
        data.Data = ctypes.pointer(policy)
        data.SizeOfData = ctypes.sizeof(policy)
        ret = ctypes.windll.user32.SetWindowCompositionAttribute(
            ctypes.c_void_p(int(win_id)), ctypes.byref(data))
        return bool(ret)
    except Exception:
        return False


def _apply_glass_blur(app: QApplication, enabled: bool, tint: str = "#f0f5ff") -> None:
    """毛玻璃主题开关：对所有顶级窗口启用/关闭亚克力模糊与透明背景。"""
    from PySide6.QtCore import Qt
    for w in app.topLevelWidgets():
        try:
            if not w.isWindow() or not w.winId():
                continue
            ok = _set_windows_acrylic(int(w.winId()), enabled, tint)
            w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, enabled and ok)
        except RuntimeError:
            pass
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ThemeManager
# ---------------------------------------------------------------------------
class ThemeManager:
    """主题与字体应用、配置读写"""

    DEFAULT_THEME_ID = "default"
    DEFAULT_FONT_FAMILY = "Microsoft YaHei"
    DEFAULT_FONT_SIZE = 10

    @staticmethod
    def _refresh_table_fonts(app: "QApplication") -> None:
        """主题应用后重置所有 ZoomableTableWidget 的缩放基准与行高。"""
        from gui_utils import ZoomableTableWidget
        for w in app.allWidgets():
            if isinstance(w, ZoomableTableWidget):
                try:
                    w.refresh_qss_font()
                except RuntimeError:
                    pass

    @staticmethod
    def apply(app: QApplication,
              theme_id: Optional[str] = None,
              font_family: Optional[str] = None,
              font_size: Optional[int] = None,
              glass: Optional[Dict] = None) -> None:
        """将主题与字体应用到 QApplication（全局生效）

        glass: 毛玻璃参数 {"opacity": 0~100, "bg_image": 路径, "tint": "#rrggbb"}，
        仅毛玻璃主题生效，缺省项用 GLASS_DEFAULTS。
        """
        theme_id = theme_id or ThemeManager.DEFAULT_THEME_ID
        font_family = font_family or ThemeManager.DEFAULT_FONT_FAMILY
        font_size = font_size or ThemeManager.DEFAULT_FONT_SIZE
        theme = get_theme(theme_id)

        style = QStyleFactory.create(theme["style"])
        if style:
            app.setStyle(style)
        qss = theme["qss"] or ""
        g = {**GLASS_DEFAULTS, **(glass or {})}
        if theme.get("win_blur"):
            try:
                qss = build_glass_qss(g["opacity"], g["tint"], g["bg_image"])
            except Exception:
                qss = theme["qss"] or ""
        app.setStyleSheet(qss)
        app.setFont(QFont(font_family, font_size))
        # 毛玻璃主题：启用 Windows 亚克力模糊；其他主题恢复不透明
        try:
            _apply_glass_blur(app, bool(theme.get("win_blur")), g["tint"])
        except Exception:
            pass
        # QSS font-size 不反映到 widget.font()，表格缩放基准需按新样式重置
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: ThemeManager._refresh_table_fonts(app))

    @staticmethod
    def load_from_config(app_config: Dict) -> Tuple[str, str, int]:
        """从应用配置 dict 读取 (theme_id, font_family, font_size)，带默认值"""
        ui = app_config.get("ui", {}) if isinstance(app_config, dict) else {}
        return (
            ui.get("theme", ThemeManager.DEFAULT_THEME_ID),
            ui.get("font_family", ThemeManager.DEFAULT_FONT_FAMILY),
            int(ui.get("font_size", ThemeManager.DEFAULT_FONT_SIZE) or ThemeManager.DEFAULT_FONT_SIZE),
        )

    @staticmethod
    def load_glass_config(app_config: Dict) -> Dict:
        """从应用配置 dict 读取毛玻璃参数，带默认值"""
        ui = app_config.get("ui", {}) if isinstance(app_config, dict) else {}
        g = dict(GLASS_DEFAULTS)
        if isinstance(ui.get("glass"), dict):
            for k in GLASS_DEFAULTS:
                if k in ui["glass"]:
                    g[k] = ui["glass"][k]
        return g

    @staticmethod
    def to_config(theme_id: str, font_family: str, font_size: int,
                  glass: Optional[Dict] = None) -> Dict:
        """构造 config.json 的 ui 段（glass 非空时附带毛玻璃参数）"""
        cfg = {
            "theme": theme_id,
            "font_family": font_family,
            "font_size": font_size,
        }
        if glass is not None:
            cfg["glass"] = {k: glass.get(k, GLASS_DEFAULTS[k]) for k in GLASS_DEFAULTS}
        return cfg

    @staticmethod
    def apply_from_file(app: QApplication, config_path: Optional[Path] = None) -> None:
        """从 config.json 读取 ui 段并应用（应用启动时调用）"""
        if config_path is None:
            from app_paths import data_path
            config_path = data_path("config.json")
        app_config: Dict = {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                app_config = json.load(f)
        except Exception:
            app_config = {}
        ThemeManager.apply(app, *ThemeManager.load_from_config(app_config),
                           glass=ThemeManager.load_glass_config(app_config))


# ---------------------------------------------------------------------------
# ThemeSettingsDialog
# ---------------------------------------------------------------------------
class ThemeSettingsDialog(QDialog):
    """主题与字体设置对话框

    - 主题下拉：6 套内置主题，切换即预览（应用级样式立即生效）
    - 字体：字体族（系统字体列表）+ 字号（8~24pt），切换即预览
    - 确定：MainWindow 保存配置；取消：还原进入对话框前的主题与字体
    """

    def __init__(self, theme_id: str, font_family: str, font_size: int,
                 glass: Optional[Dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("主题与字体设置")
        self.setMinimumWidth(500)
        self._app = QApplication.instance()
        self._orig = (theme_id, font_family, font_size)
        self._orig_glass = {**GLASS_DEFAULTS, **(glass or {})}
        self._glass_tint = str(self._orig_glass.get("tint", GLASS_DEFAULTS["tint"]))

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ---- 主题 ----
        theme_title = QLabel("主题")
        theme_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(theme_title)

        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumHeight(30)
        for t in THEMES:
            self.theme_combo.addItem(t["name"], t["id"])
        self.theme_combo.setCurrentIndex(
            next((i for i, t in enumerate(THEMES) if t["id"] == theme_id), 0)
        )
        self.theme_combo.currentIndexChanged.connect(self._on_theme_index_changed)
        layout.addWidget(self.theme_combo)

        self.theme_desc = QLabel()
        self.theme_desc.setWordWrap(True)
        layout.addWidget(self.theme_desc)

        # ---- 毛玻璃选项（仅毛玻璃主题显示）----
        self.glass_group = QGroupBox("毛玻璃选项")
        g_layout = QVBoxLayout(self.glass_group)
        g_layout.setSpacing(6)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("透明度"))
        self.glass_opacity_slider = QSlider()
        self.glass_opacity_slider.setRange(0, 100)
        try:
            self.glass_opacity_slider.setValue(int(self._orig_glass.get("opacity", 60)))
        except (TypeError, ValueError):
            self.glass_opacity_slider.setValue(60)
        self.glass_opacity_slider.valueChanged.connect(self._on_glass_opacity_changed)
        op_row.addWidget(self.glass_opacity_slider, 1)
        self.glass_opacity_lbl = QLabel()
        self.glass_opacity_lbl.setMinimumWidth(42)
        op_row.addWidget(self.glass_opacity_lbl)
        g_layout.addLayout(op_row)

        tint_row = QHBoxLayout()
        tint_row.addWidget(QLabel("玻璃颜色"))
        self.glass_tint_btn = QPushButton("选择颜色…")
        self.glass_tint_btn.clicked.connect(self._pick_glass_tint)
        tint_row.addWidget(self.glass_tint_btn)
        tint_row.addStretch()
        g_layout.addLayout(tint_row)

        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel("背景图"))
        self.glass_bg_edit = QLineEdit(str(self._orig_glass.get("bg_image", "") or ""))
        self.glass_bg_edit.setPlaceholderText("留空则使用玻璃颜色")
        self.glass_bg_edit.textChanged.connect(self._apply_preview)
        bg_row.addWidget(self.glass_bg_edit, 1)
        bg_browse = QPushButton("浏览…")
        bg_browse.clicked.connect(self._pick_glass_bg)
        bg_row.addWidget(bg_browse)
        bg_clear = QPushButton("清除")
        bg_clear.clicked.connect(lambda: self.glass_bg_edit.setText(""))
        bg_row.addWidget(bg_clear)
        g_layout.addLayout(bg_row)

        self._sync_glass_widgets()
        layout.addWidget(self.glass_group)

        # ---- 字体 ----
        font_title = QLabel("字体")
        font_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(font_title)

        font_row = QHBoxLayout()
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(font_family))
        self.font_combo.currentFontChanged.connect(self._apply_preview)
        font_row.addWidget(self.font_combo, 1)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 24)
        self.size_spin.setValue(font_size)
        self.size_spin.setSuffix(" pt")
        self.size_spin.valueChanged.connect(self._apply_preview)
        font_row.addWidget(self.size_spin)
        layout.addLayout(font_row)

        hint = QLabel("提示：修改立即生效，可在当前窗口实时预览。解析表格为紧凑排版，字号保持固定。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ---- 系统集成（开机自启 / 托盘 / 热键 / 右键菜单）----
        self.system_panel = SystemIntegrationSettings(self)
        layout.addWidget(self.system_panel)

        # ---- 按钮 ----
        btn_row = QHBoxLayout()
        self.reset_btn = QPushButton("恢复默认")
        self.reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch()

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._update_desc()

    # ---- 内部 ----
    def _update_desc(self) -> None:
        theme = get_theme(self.theme_combo.currentData())
        self.theme_desc.setText(f"说明：{theme['desc']}")

    def _is_glass_selected(self) -> bool:
        return bool(get_theme(self.theme_combo.currentData()).get("win_blur"))

    def _sync_glass_widgets(self) -> None:
        """毛玻璃选项仅在毛玻璃主题下可见；同步透明度标签与颜色按钮色块"""
        self.glass_group.setVisible(self._is_glass_selected())
        self.glass_opacity_lbl.setText(f"{self.glass_opacity_slider.value()}%")
        self.glass_tint_btn.setStyleSheet(
            f"background-color: {self._glass_tint}; color: #1f2937;")

    def _on_theme_index_changed(self, *_):
        self._sync_glass_widgets()
        self._apply_preview()

    def _on_glass_opacity_changed(self, *_):
        self.glass_opacity_lbl.setText(f"{self.glass_opacity_slider.value()}%")
        self._apply_preview()

    def _pick_glass_tint(self):
        color = QColorDialog.getColor(QColor(self._glass_tint), self, "选择玻璃颜色")
        if color.isValid():
            self._glass_tint = color.name()
            self._sync_glass_widgets()
            self._apply_preview()

    def _pick_glass_bg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.glass_bg_edit.setText(path)

    def _apply_preview(self, *_) -> None:
        """将当前选择应用到全局（即时预览）"""
        self._update_desc()
        ThemeManager.apply(
            self._app,
            self.theme_combo.currentData(),
            self.font_combo.currentFont().family(),
            self.size_spin.value(),
            glass=self.get_glass_settings(),
        )

    def _reset_defaults(self) -> None:
        """恢复默认主题与字体"""
        self.theme_combo.setCurrentIndex(
            next((i for i, t in enumerate(THEMES) if t["id"] == ThemeManager.DEFAULT_THEME_ID), 0)
        )
        self.font_combo.setCurrentFont(QFont(ThemeManager.DEFAULT_FONT_FAMILY))
        self.size_spin.setValue(ThemeManager.DEFAULT_FONT_SIZE)
        self._apply_preview()

    # ---- 对外接口 ----
    def get_settings(self) -> Tuple[str, str, int]:
        """返回 (theme_id, font_family, font_size)"""
        return (
            self.theme_combo.currentData(),
            self.font_combo.currentFont().family(),
            self.size_spin.value(),
        )

    def get_glass_settings(self) -> Dict:
        """返回毛玻璃参数 {"opacity", "bg_image", "tint"}"""
        return {
            "opacity": int(self.glass_opacity_slider.value()),
            "bg_image": self.glass_bg_edit.text().strip(),
            "tint": self._glass_tint,
        }

    def get_system_settings(self) -> dict:
        """返回系统集成设置（对话框接受时调用，不主动保存）"""
        return self.system_panel.get_settings()

    def reject(self) -> None:
        """取消：还原进入对话框前的主题、字体与毛玻璃参数"""
        ThemeManager.apply(self._app, *self._orig, glass=self._orig_glass)
        super().reject()
