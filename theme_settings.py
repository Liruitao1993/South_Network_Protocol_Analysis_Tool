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
- windows      Windows 原生风格
- windowsvista Windows Vista 原生风格

约定：QSS 应用在 QApplication 级（弹窗/文件对话框等顶级窗口跟随主题）。
组件内部的对象级 setStyleSheet 优先于应用级 QSS，暗色下部分组件保留自身配色。
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFontComboBox, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QStyleFactory, QVBoxLayout,
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
        padding: 8px 16px;
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
        padding: 5px;
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
        padding: 6px 14px;
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
        padding: 4px 22px 4px 6px;
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
        padding: 8px 16px;
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
        padding: 5px;
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
        padding: 6px 14px;
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
        padding: 4px 22px 4px 6px;
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
        "qss": None,
        "desc": "Windows Vista 原生控件风格（无自定义样式表）",
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
# ThemeManager
# ---------------------------------------------------------------------------
class ThemeManager:
    """主题与字体应用、配置读写"""

    DEFAULT_THEME_ID = "default"
    DEFAULT_FONT_FAMILY = "Microsoft YaHei"
    DEFAULT_FONT_SIZE = 10

    @staticmethod
    def apply(app: QApplication,
              theme_id: Optional[str] = None,
              font_family: Optional[str] = None,
              font_size: Optional[int] = None) -> None:
        """将主题与字体应用到 QApplication（全局生效）"""
        theme_id = theme_id or ThemeManager.DEFAULT_THEME_ID
        font_family = font_family or ThemeManager.DEFAULT_FONT_FAMILY
        font_size = font_size or ThemeManager.DEFAULT_FONT_SIZE
        theme = get_theme(theme_id)

        style = QStyleFactory.create(theme["style"])
        if style is None:  # 平台不支持时回退 Fusion
            style = QStyleFactory.create("Fusion")
        app.setStyle(style)
        app.setStyleSheet(theme["qss"] or "")
        app.setFont(QFont(font_family, font_size))

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
    def to_config(theme_id: str, font_family: str, font_size: int) -> Dict:
        """构造 config.json 的 ui 段"""
        return {
            "theme": theme_id,
            "font_family": font_family,
            "font_size": font_size,
        }

    @staticmethod
    def apply_from_file(app: QApplication, config_path: Optional[Path] = None) -> None:
        """从 config.json 读取 ui 段并应用（应用启动时调用）"""
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"
        app_config: Dict = {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                app_config = json.load(f)
        except Exception:
            app_config = {}
        ThemeManager.apply(app, *ThemeManager.load_from_config(app_config))


# ---------------------------------------------------------------------------
# ThemeSettingsDialog
# ---------------------------------------------------------------------------
class ThemeSettingsDialog(QDialog):
    """主题与字体设置对话框

    - 主题下拉：5 套内置主题，切换即预览（应用级样式立即生效）
    - 字体：字体族（系统字体列表）+ 字号（8~24pt），切换即预览
    - 确定：MainWindow 保存配置；取消：还原进入对话框前的主题与字体
    """

    def __init__(self, theme_id: str, font_family: str, font_size: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("主题与字体设置")
        self.setMinimumWidth(500)
        self._app = QApplication.instance()
        self._orig = (theme_id, font_family, font_size)

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
        self.theme_combo.currentIndexChanged.connect(self._apply_preview)
        layout.addWidget(self.theme_combo)

        self.theme_desc = QLabel()
        self.theme_desc.setWordWrap(True)
        layout.addWidget(self.theme_desc)

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

    def _apply_preview(self, *_) -> None:
        """将当前选择应用到全局（即时预览）"""
        self._update_desc()
        ThemeManager.apply(
            self._app,
            self.theme_combo.currentData(),
            self.font_combo.currentFont().family(),
            self.size_spin.value(),
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

    def get_system_settings(self) -> dict:
        """返回系统集成设置（对话框接受时调用，不主动保存）"""
        return self.system_panel.get_settings()

    def reject(self) -> None:
        """取消：还原进入对话框前的主题与字体"""
        ThemeManager.apply(self._app, *self._orig)
        super().reject()
