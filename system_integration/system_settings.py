"""
系统集成设置（system_integration 包）
=====================================
- SettingsState：config.json "system" 段读写
- SystemIntegrationSettings：设置面板（嵌入 ThemeSettingsDialog）

设置项：
- auto_start        开机自启
- close_to_tray     关闭行为（true=最小化到托盘）
- hotkey_enabled    全局热键开关
- hotkey            热键字符串（默认 Ctrl+Alt+P）
- context_menu      文件右键菜单是否注册
"""
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

from system_integration import registry_menu

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULT_SYSTEM_SETTINGS = {
    "auto_start": False,
    "close_to_tray": True,
    "hotkey_enabled": True,
    "hotkey": "Ctrl+Alt+X",  # 默认热键（Ctrl+Alt+P 常被输入法/其它软件占用）
    "context_menu": False,
    "npp_integrated": False,
    "clipboard_monitor": False,  # 剪贴板报文自动检测（默认关，避免干扰日常复制粘贴）
}


class SettingsState:
    """读取/保存 config.json 的 "system" 段"""

    @staticmethod
    def load() -> dict:
        settings = dict(DEFAULT_SYSTEM_SETTINGS)
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
                sys_cfg = config.get("system", {})
                if isinstance(sys_cfg, dict):
                    settings.update({k: sys_cfg[k] for k in sys_cfg if k in settings})
        except Exception:
            pass
        return settings

    @staticmethod
    def save(settings: dict) -> None:
        try:
            config = {}
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
            config["system"] = settings
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[系统设置保存失败] {e}")


class SystemIntegrationSettings(QWidget):
    """系统集成设置面板（嵌入 ThemeSettingsDialog 底部）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = SettingsState.load()
        self._build_ui()
        self._load_ui()

    # ---- UI ----
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("系统集成")
        box_layout = QVBoxLayout(box)

        # 开机自启
        self.auto_start_chk = QCheckBox("开机自动启动")
        box_layout.addWidget(self.auto_start_chk)

        # 关闭行为
        close_row = QHBoxLayout()
        close_row.addWidget(QLabel("关闭主窗口时："))
        self.tray_radio = QRadioButton("最小化到系统托盘")
        self.exit_radio = QRadioButton("直接退出程序")
        self._close_group = QButtonGroup(self)
        self._close_group.addButton(self.tray_radio)
        self._close_group.addButton(self.exit_radio)
        close_row.addWidget(self.tray_radio)
        close_row.addWidget(self.exit_radio)
        close_row.addStretch()
        box_layout.addLayout(close_row)

        # 全局热键
        hotkey_row = QHBoxLayout()
        self.hotkey_enabled_chk = QCheckBox("启用全局热键")
        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("如 Ctrl+Alt+P")
        self.hotkey_edit.setMaximumWidth(160)
        hotkey_row.addWidget(self.hotkey_enabled_chk)
        hotkey_row.addWidget(self.hotkey_edit)
        hotkey_row.addStretch()
        box_layout.addLayout(hotkey_row)

        hotkey_hint = QLabel("热键可跨任意软件使用：复制报文后按热键直接解析弹出结果")
        hotkey_hint.setStyleSheet("color: gray;")
        box_layout.addWidget(hotkey_hint)

        # 剪贴板报文自动检测
        self.clipboard_monitor_chk = QCheckBox("剪贴板报文自动检测")
        self.clipboard_monitor_chk.setToolTip(
            "在任何软件中选中报文并按 Ctrl+C 复制，自动弹出提示框，"
            "点击「解析」即转入解析器。全局生效，无需在解析器中操作。"
        )
        box_layout.addWidget(self.clipboard_monitor_chk)

        clip_hint = QLabel("推荐：在任意软件（记事本/NPP/UE/浏览器/PDF）选中报文 → Ctrl+C → 自动弹提示框")
        clip_hint.setWordWrap(True)
        clip_hint.setStyleSheet("color: gray;")
        box_layout.addWidget(clip_hint)

        # 文件右键菜单
        menu_row = QHBoxLayout()
        self.menu_status_label = QLabel("未注册")
        self.register_menu_btn = QPushButton("注册文件右键菜单")
        self.unregister_menu_btn = QPushButton("取消注册")
        menu_row.addWidget(self.menu_status_label)
        menu_row.addStretch()
        menu_row.addWidget(self.register_menu_btn)
        menu_row.addWidget(self.unregister_menu_btn)
        box_layout.addLayout(menu_row)

        menu_hint = QLabel("注册后，在 .log/.txt/.hex/.bin 文件上右键可选择协议直接解析")
        menu_hint.setStyleSheet("color: gray;")
        box_layout.addWidget(menu_hint)

        # Notepad++ 集成
        npp_row = QHBoxLayout()
        self.npp_status_label = QLabel("未注册")
        self.register_npp_btn = QPushButton("注册 Notepad++ 集成")
        self.unregister_npp_btn = QPushButton("取消注册")
        npp_row.addWidget(self.npp_status_label)
        npp_row.addStretch()
        npp_row.addWidget(self.register_npp_btn)
        npp_row.addWidget(self.unregister_npp_btn)
        box_layout.addLayout(npp_row)

        npp_hint = QLabel("注册后：在 Notepad++ 中选中报文按 Ctrl+C 复制，右键「用协议解析工具解析」或按快捷键直接弹出解析窗口")
        npp_hint.setWordWrap(True)
        npp_hint.setStyleSheet("color: gray;")
        box_layout.addWidget(npp_hint)

        layout.addWidget(box)

        # 信号
        self.register_menu_btn.clicked.connect(self._register_menu)
        self.unregister_menu_btn.clicked.connect(self._unregister_menu)
        self.register_npp_btn.clicked.connect(self._register_npp)
        self.unregister_npp_btn.clicked.connect(self._unregister_npp)

    def _load_ui(self):
        s = self._settings
        self.auto_start_chk.setChecked(bool(s.get("auto_start")))
        if s.get("close_to_tray"):
            self.tray_radio.setChecked(True)
        else:
            self.exit_radio.setChecked(True)
        self.hotkey_enabled_chk.setChecked(bool(s.get("hotkey_enabled")))
        self.hotkey_edit.setText(s.get("hotkey", "Ctrl+Alt+P"))
        self.hotkey_edit.setEnabled(bool(s.get("hotkey_enabled")))
        self.hotkey_enabled_chk.toggled.connect(self.hotkey_edit.setEnabled)
        self.clipboard_monitor_chk.setChecked(bool(s.get("clipboard_monitor", True)))
        self._refresh_menu_status()
        self._refresh_npp_status()

    # ---- 右键菜单 ----
    def _refresh_menu_status(self):
        registered = registry_menu.is_context_menu_registered()
        self.menu_status_label.setText("已注册" if registered else "未注册")
        self.menu_status_label.setStyleSheet(
            "color: #2e7d32;" if registered else "color: gray;"
        )

    def _register_menu(self):
        if registry_menu.register_context_menu():
            self._settings["context_menu"] = True
            QMessageBox.information(self, "注册成功", "文件右键菜单已注册。")
            self._refresh_menu_status()
        else:
            QMessageBox.critical(self, "注册失败", "注册右键菜单失败，请查看控制台日志。")

    def _unregister_menu(self):
        if registry_menu.unregister_context_menu():
            self._settings["context_menu"] = False
            QMessageBox.information(self, "取消成功", "文件右键菜单已取消注册。")
            self._refresh_menu_status()
        else:
            QMessageBox.critical(self, "取消失败", "取消注册右键菜单失败，请查看控制台日志。")

    # ---- Notepad++ 集成 ----
    def _refresh_npp_status(self):
        try:
            from system_integration import npp_integration
            registered = npp_integration.is_npp_registered()
        except Exception:
            registered = False
        self.npp_status_label.setText("已注册" if registered else "未注册")
        self.npp_status_label.setStyleSheet(
            "color: #2e7d32;" if registered else "color: gray;"
        )

    def _register_npp(self):
        try:
            from system_integration import npp_integration
            if npp_integration.register_npp():
                self._settings["npp_integrated"] = True
                QMessageBox.information(
                    self, "注册成功",
                    "Notepad++ 集成已注册。\n\n使用方式：在 NPP 中选中报文 → Ctrl+C 复制 → "
                    "右键「用协议解析工具解析」或按快捷键（F5 运行菜单中可见）。\n\n"
                    "提示：NPP 需重启或重开文档后生效。"
                )
                self._refresh_npp_status()
            else:
                QMessageBox.critical(self, "注册失败", "注册失败，请确认已安装 Notepad++。")
        except Exception as e:
            QMessageBox.critical(self, "注册失败", f"注册失败：{str(e)}")

    def _unregister_npp(self):
        try:
            from system_integration import npp_integration
            if npp_integration.unregister_npp():
                self._settings["npp_integrated"] = False
                QMessageBox.information(self, "取消成功", "Notepad++ 集成已取消。")
                self._refresh_npp_status()
            else:
                QMessageBox.critical(self, "取消失败", "取消失败，请查看控制台日志。")
        except Exception as e:
            QMessageBox.critical(self, "取消失败", f"取消失败：{str(e)}")

    # ---- 对外接口 ----
    def get_settings(self) -> dict:
        """收集当前设置（对话框确定时调用）"""
        return {
            "auto_start": self.auto_start_chk.isChecked(),
            "close_to_tray": self.tray_radio.isChecked(),
            "hotkey_enabled": self.hotkey_enabled_chk.isChecked(),
            "hotkey": self.hotkey_edit.text().strip() or "Ctrl+Alt+P",
            "context_menu": self._settings.get("context_menu", False),
            "npp_integrated": self._settings.get("npp_integrated", False),
            "clipboard_monitor": self.clipboard_monitor_chk.isChecked(),
        }

    def save_settings(self) -> dict:
        """保存并返回设置（供 MainWindow 应用）"""
        settings = self.get_settings()
        SettingsState.save(settings)
        self._settings = settings
        return settings
