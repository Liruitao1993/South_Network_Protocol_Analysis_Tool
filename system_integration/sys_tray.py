"""
系统托盘模块（系统集成）
========================
- 关闭主窗口 → 最小化到托盘（不退出）
- 托盘左键单击 → 显示/隐藏主窗口
- 托盘右键菜单：显示主窗口 / 开机自启开关 / 退出
"""
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from system_integration import registry_menu


class SystemTrayManager(QObject):
    """管理系统托盘图标与菜单"""

    exit_requested = Signal()          # 托盘菜单"退出"触发
    show_requested = Signal()          # 托盘"显示主窗口"触发
    autostart_toggled = Signal(bool)   # 托盘内自启开关切换
    message_clicked = Signal()         # 气泡通知被点击（用于剪贴板解析确认）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._window = parent  # MainWindow（也用于判断是否可用）
        self._tray = None
        self._autostart_action = None
        self._startup_hint_shown = False

    def create(self, icon_path: str = None):
        """创建托盘图标。返回是否成功（无托盘支持时 False）"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False

        self._tray = QSystemTrayIcon(self)

        # 图标：优先应用图标文件，否则用主窗口图标
        icon = QIcon()
        if icon_path and os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            app_icon = QApplication.instance().windowIcon()
            if not app_icon.isNull():
                icon = app_icon
            else:
                icon = self._window.windowIcon()
        self._tray.setIcon(icon)
        self._tray.setToolTip("协议解析工具")

        # 右键菜单
        menu = QMenu()
        show_action = QAction("显示主窗口", menu)
        show_action.triggered.connect(self.show_requested.emit)
        menu.addAction(show_action)

        self._autostart_action = QAction("开机自启", menu)
        self._autostart_action.setCheckable(True)
        self._autostart_action.setChecked(registry_menu.get_autostart())
        self._autostart_action.toggled.connect(self.autostart_toggled.emit)
        menu.addAction(self._autostart_action)

        menu.addSeparator()
        exit_action = QAction("退出", menu)
        exit_action.triggered.connect(self.exit_requested.emit)
        menu.addAction(exit_action)

        self._tray.setContextMenu(menu)

        # 左键单击：显示/隐藏
        self._tray.activated.connect(self._on_activated)
        # 气泡通知点击（Windows 托盘消息点击触发 MessageClicked）
        self._tray.messageClicked.connect(self.message_clicked.emit)

        self._tray.show()
        return True

    def show_message(self, title: str, body: str, timeout_ms: int = 5000):
        """显示气泡通知（用于剪贴板检测提示）"""
        if self._tray is not None:
            self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, timeout_ms)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # 左键单击
            if self._window.isVisible():
                self._window.hide()
            else:
                self._window.showNormal()
                self._window.raise_()
                self._window.activateWindow()

    def show_hint_once(self, text: str = "已最小化到系统托盘，双击图标可恢复主界面"):
        """首次最小化到托盘时显示气泡通知（仅一次）"""
        if self._startup_hint_shown or self._tray is None:
            return
        self._startup_hint_shown = True
        self._tray.showMessage("协议解析工具", text, QSystemTrayIcon.MessageIcon.Information, 3000)

    def update_autostart_state(self):
        """刷新托盘菜单中的自启开关状态（设置对话框改动后调用）"""
        if self._autostart_action is not None:
            self._autostart_action.setChecked(registry_menu.get_autostart())

    def hide_tray(self):
        """隐藏托盘图标（退出时调用）"""
        if self._tray is not None:
            self._tray.hide()
