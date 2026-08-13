# -*- coding: utf-8 -*-
"""LLM 模型 API 管理对话框

支持多供应商预设、多配置增删改、测试连接、活跃配置选择。
配置持久化到 config.json 的 llm_profiles 段。
"""
import json
import os
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QComboBox, QGroupBox,
    QMessageBox, QHeaderView, QAbstractItemView, QDialogButtonBox,
    QFormLayout, QFrame, QSpacerItem, QSizePolicy, QCheckBox,
)
from PySide6.QtCore import Qt, QThread, Signal as QtSignal
from PySide6.QtGui import QFont, QColor
from gui_utils import ZoomableTableWidget


def _style_action_btn(btn: QPushButton, height: int = 28, min_width: int = 0):
    """统一操作按钮尺寸。"""
    btn.setMinimumHeight(height)
    if min_width:
        btn.setMinimumWidth(min_width)


# ═══════════════════════════════════════════════════════════
# 供应商预设
# ═══════════════════════════════════════════════════════════

PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    "OpenAI": {
        "endpoint": "https://api.openai.com/v1",
        "models": "gpt-4o,gpt-4o-mini,gpt-3.5-turbo",
    },
    "OpenCode Zen": {
        "endpoint": "https://api.opencode.ai/v1",
        "models": "gpt-4o,claude-3.5-sonnet,gpt-4o-mini",
    },
    "DeepSeek": {
        "endpoint": "https://api.deepseek.com/v1",
        "models": "deepseek-chat,deepseek-coder",
    },
    "Google Gemini": {
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": "gemini-2.0-flash,gemini-1.5-pro,gemini-1.5-flash",
    },
    "Groq": {
        "endpoint": "https://api.groq.com/openai/v1",
        "models": "llama-3.1-70b-versatile,llama-3.1-8b-instant,mixtral-8x7b-32768",
    },
    "SiliconFlow": {
        "endpoint": "https://api.siliconflow.cn/v1",
        "models": "Qwen/Qwen2.5-7B-Instruct,deepseek-ai/DeepSeek-V3",
    },
    "Together AI": {
        "endpoint": "https://api.together.xyz/v1",
        "models": "meta-llama/Llama-3-70b-chat-hf,mistralai/Mixtral-8x22B-Instruct-v0.1",
    },
    "Ollama (本地)": {
        "endpoint": "http://localhost:11434/v1",
        "models": "llama3,qwen2,codellama,mistral",
    },
    "LM Studio (本地)": {
        "endpoint": "http://localhost:1234/v1",
        "models": "",
    },
    "OpenRouter (免费)": {
        "endpoint": "https://openrouter.ai/api/v1",
        "models": "meta-llama/llama-3.1-8b-instruct:free,google/gemma-2-9b-it:free,qwen/qwen-2.5-7b-instruct:free,mistralai/mistral-7b-instruct:free",
    },
    "自定义": {
        "endpoint": "",
        "models": "",
    },
}


def _config_path() -> str:
    return os.path.join(os.path.dirname(__file__), "config.json")


def load_profiles() -> Dict[str, Any]:
    """从 config.json 加载 LLM profiles 配置

    自动迁移：如果 llm_profiles 为空但旧 llm 段有 endpoint/key/model，
    自动创建一个默认配置。
    """
    try:
        with open(_config_path(), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return {"profiles": [], "active": ""}

    data = cfg.get("llm_profiles", {"profiles": [], "active": ""})

    # 自动迁移旧配置
    if not data.get("profiles"):
        old_llm = cfg.get("llm", {})
        ep = old_llm.get("endpoint", "")
        key = old_llm.get("api_key", "")
        model = old_llm.get("model", "")
        if ep and key:
            profile = {
                "name": "默认配置",
                "provider": "自定义",
                "endpoint": ep,
                "api_key": key,
                "model": model,
            }
            data["profiles"] = [profile]
            data["active"] = "默认配置"
            # 回写，下次不再迁移
            save_profiles(data)

    return data


def save_profiles(data: Dict[str, Any]):
    """保存 LLM profiles 到 config.json"""
    try:
        with open(_config_path(), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg["llm_profiles"] = data
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_active_profile() -> Optional[Dict[str, str]]:
    """获取当前活跃的 API 配置"""
    data = load_profiles()
    active_name = data.get("active", "")
    for p in data.get("profiles", []):
        if p.get("name") == active_name:
            return p
    # 如果没有活跃配置，返回第一个
    profiles = data.get("profiles", [])
    return profiles[0] if profiles else None


# ═══════════════════════════════════════════════════════════
# 测试连接线程
# ═══════════════════════════════════════════════════════════

class _TestThread(QThread):
    """后台测试 API 连接"""
    result = QtSignal(str)
    error = QtSignal(str)

    def __init__(self, endpoint: str, api_key: str, model: str):
        super().__init__()
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model

    def run(self):
        try:
            from llm_preprocess import LLMAPIClient
            client = LLMAPIClient(self.endpoint, self.api_key, self.model, timeout=30)
            msg = client.test_connection()
            self.result.emit(msg)
        except TimeoutError as e:
            self.error.emit(f"超时: {e}")
        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════════════════════
# 编辑对话框
# ═══════════════════════════════════════════════════════════

class _ProfileEditDialog(QDialog):
    """新增/编辑单个 API 配置"""

    def __init__(self, parent=None, profile: Optional[Dict[str, str]] = None):
        super().__init__(parent)
        self.setWindowTitle("编辑 API 配置" if profile else "新增 API 配置")
        self.setMinimumWidth(520)
        self._profile = profile or {}
        self._test_thread = None
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # 供应商预设
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("供应商预设:"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(200)
        for name in PROVIDER_PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self.preset_combo)
        preset_row.addStretch()
        root.addLayout(preset_row)

        root.addWidget(self._separator())

        # 表单
        form = QFormLayout()
        form.setSpacing(8)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("给这个配置起个名字，如 'DeepSeek V3'")
        form.addRow("配置名称:", self.name_edit)

        self.endpoint_edit = QLineEdit()
        self.endpoint_edit.setPlaceholderText("https://api.deepseek.com/v1")
        self.endpoint_edit.setToolTip(
            "API 基础 URL，填到 /v1 即可\n"
            "不要包含 /chat/completions 后缀"
        )
        form.addRow("Endpoint:", self.endpoint_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("sk-...")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow("API Key:", self.api_key_edit)

        # 显示/隐藏 key
        self.show_key_cb = QCheckBox("显示")
        self.show_key_cb.toggled.connect(
            lambda on: self.api_key_edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password
            )
        )
        key_row = QHBoxLayout()
        key_row.addWidget(self.api_key_edit)
        key_row.addWidget(self.show_key_cb)
        key_row.addStretch()
        form.addRow("", key_row)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setPlaceholderText("选择或输入模型名")
        form.addRow("模型:", self.model_combo)

        root.addLayout(form)

        root.addWidget(self._separator())

        # 测试连接
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("🔗 测试连接")
        _style_action_btn(self.test_btn, min_width=100)
        self.test_btn.clicked.connect(self._test_connection)
        test_row.addWidget(self.test_btn)
        self.test_status = QLabel("")
        test_row.addWidget(self.test_status)
        test_row.addStretch()
        root.addLayout(test_row)

        # 按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    def _separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def _load_data(self):
        """加载已有配置数据"""
        if not self._profile:
            return
        self.name_edit.setText(self._profile.get("name", ""))
        self.endpoint_edit.setText(self._profile.get("endpoint", ""))
        self.api_key_edit.setText(self._profile.get("api_key", ""))
        model = self._profile.get("model", "")
        # 尝试匹配预设
        for i in range(self.model_combo.count()):
            if self.model_combo.itemText(i) == model:
                self.model_combo.setCurrentIndex(i)
                return
        self.model_combo.setEditText(model)
        # 尝试匹配供应商
        provider = self._profile.get("provider", "")
        idx = self.preset_combo.findText(provider)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)

    def _on_preset_changed(self, name: str):
        preset = PROVIDER_PRESETS.get(name, {})
        endpoint = preset.get("endpoint", "")
        models_str = preset.get("models", "")
        if endpoint:
            self.endpoint_edit.setText(endpoint)
        # 填充模型下拉
        self.model_combo.clear()
        if models_str:
            for m in models_str.split(","):
                m = m.strip()
                if m:
                    self.model_combo.addItem(m)
        # 自动填充配置名（仅新增时）
        if not self._profile and name != "自定义":
            self.name_edit.setText(name)

    def _test_connection(self):
        endpoint = self.endpoint_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        model = self.model_combo.currentText().strip()
        if not endpoint or not api_key:
            QMessageBox.warning(self, "配置不完整", "请填写 Endpoint 和 API Key")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")
        self.test_status.setText("")
        self._test_thread = _TestThread(endpoint, api_key, model)
        self._test_thread.result.connect(self._on_test_ok)
        self._test_thread.error.connect(self._on_test_err)
        self._test_thread.finished.connect(
            lambda: self.test_btn.setEnabled(True) or self.test_btn.setText("🔗 测试连接")
        )
        self._test_thread.start()

    def _on_test_ok(self, msg: str):
        self.test_status.setText(f"✅ {msg}")
        self.test_status.setStyleSheet("color: green; font-weight: bold;")

    def _on_test_err(self, msg: str):
        self.test_status.setText(f"❌ {msg[:80]}")
        self.test_status.setStyleSheet("color: red;")
        self.test_status.setToolTip(msg)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "名称为空", "请填写配置名称")
            return
        self.accept()

    def get_profile(self) -> Dict[str, str]:
        return {
            "name": self.name_edit.text().strip(),
            "provider": self.preset_combo.currentText(),
            "endpoint": self.endpoint_edit.text().strip(),
            "api_key": self.api_key_edit.text().strip(),
            "model": self.model_combo.currentText().strip(),
        }


# ═══════════════════════════════════════════════════════════
# 主管理对话框
# ═══════════════════════════════════════════════════════════

class LLMApiManagerDialog(QDialog):
    """LLM 模型 API 管理对话框"""

    # 信号：活跃配置变更时发出
    active_changed = QtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM 模型 API 管理")
        self.setMinimumSize(700, 450)
        self._data = load_profiles()
        self._test_thread = None
        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # 标题
        title = QLabel("管理 LLM API 配置 — 支持多供应商、多模型，可随时切换")
        title.setStyleSheet("font-size: 11px; color: #666;")
        root.addWidget(title)

        # 配置表格
        self.table = ZoomableTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["名称", "供应商", "Endpoint", "模型", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_edit)
        self.table.currentCellChanged.connect(self._on_selection_changed)
        root.addWidget(self.table, 1)

        # 按钮栏
        btn_layout = QHBoxLayout()

        self.add_btn = QPushButton("➕ 新增")
        _style_action_btn(self.add_btn, min_width=70)
        self.add_btn.clicked.connect(self._on_add)
        btn_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton("✏️ 编辑")
        _style_action_btn(self.edit_btn, min_width=70)
        self.edit_btn.clicked.connect(self._on_edit)
        self.edit_btn.setEnabled(False)
        btn_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("🗑️ 删除")
        _style_action_btn(self.delete_btn, min_width=70)
        self.delete_btn.clicked.connect(self._on_delete)
        self.delete_btn.setEnabled(False)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addSpacing(20)

        self.test_btn = QPushButton("🔗 测试连接")
        _style_action_btn(self.test_btn, min_width=100)
        self.test_btn.clicked.connect(self._on_test)
        self.test_btn.setEnabled(False)
        btn_layout.addWidget(self.test_btn)

        btn_layout.addStretch()

        self.set_active_btn = QPushButton("⭐ 设为当前使用")
        _style_action_btn(self.set_active_btn, min_width=110)
        self.set_active_btn.clicked.connect(self._on_set_active)
        self.set_active_btn.setEnabled(False)
        btn_layout.addWidget(self.set_active_btn)

        root.addLayout(btn_layout)

        # 状态栏
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-size: 10px;")
        root.addWidget(self.status_label)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        _style_action_btn(close_btn, min_width=80)
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn, 0, Qt.AlignRight)

    def _refresh_table(self):
        profiles = self._data.get("profiles", [])
        active = self._data.get("active", "")
        self.table.setRowCount(len(profiles))
        for i, p in enumerate(profiles):
            self.table.setItem(i, 0, QTableWidgetItem(p.get("name", "")))
            self.table.setItem(i, 1, QTableWidgetItem(p.get("provider", "")))
            self.table.setItem(i, 2, QTableWidgetItem(p.get("endpoint", "")))
            self.table.setItem(i, 3, QTableWidgetItem(p.get("model", "")))
            # 状态标记
            is_active = p.get("name") == active
            status_item = QTableWidgetItem("⭐ 当前使用" if is_active else "")
            if is_active:
                status_item.setForeground(QColor("#FF9800"))
                status_item.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            self.table.setItem(i, 4, status_item)
        self._update_status()

    def _update_status(self):
        profiles = self._data.get("profiles", [])
        active = self._data.get("active", "")
        if not profiles:
            self.status_label.setText("尚未配置任何 API。点击「新增」添加。")
        elif not active:
            self.status_label.setText(f"共 {len(profiles)} 个配置，未选择活跃配置。")
        else:
            self.status_label.setText(f"共 {len(profiles)} 个配置，当前使用: {active}")

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _on_selection_changed(self):
        row = self._selected_row()
        has = row >= 0
        self.edit_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        self.test_btn.setEnabled(has)
        self.set_active_btn.setEnabled(has)

    def _on_add(self):
        dlg = _ProfileEditDialog(self)
        if dlg.exec() == QDialog.Accepted:
            profile = dlg.get_profile()
            self._data["profiles"].append(profile)
            # 如果是第一个配置，自动设为活跃
            if len(self._data["profiles"]) == 1:
                self._data["active"] = profile["name"]
            save_profiles(self._data)
            self._refresh_table()

    def _on_edit(self):
        row = self._selected_row()
        if row < 0:
            return
        profiles = self._data.get("profiles", [])
        if row >= len(profiles):
            return
        old_name = profiles[row].get("name", "")
        dlg = _ProfileEditDialog(self, profile=profiles[row])
        if dlg.exec() == QDialog.Accepted:
            new_profile = dlg.get_profile()
            profiles[row] = new_profile
            # 如果编辑的是活跃配置，更新活跃名称
            if self._data.get("active") == old_name:
                self._data["active"] = new_profile["name"]
            save_profiles(self._data)
            self._refresh_table()

    def _on_delete(self):
        row = self._selected_row()
        if row < 0:
            return
        profiles = self._data.get("profiles", [])
        if row >= len(profiles):
            return
        name = profiles[row].get("name", "")
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除配置「{name}」？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            profiles.pop(row)
            if self._data.get("active") == name:
                self._data["active"] = profiles[0]["name"] if profiles else ""
            save_profiles(self._data)
            self._refresh_table()

    def _on_test(self):
        row = self._selected_row()
        if row < 0:
            return
        profiles = self._data.get("profiles", [])
        if row >= len(profiles):
            return
        p = profiles[row]
        endpoint = p.get("endpoint", "")
        api_key = p.get("api_key", "")
        model = p.get("model", "")
        if not endpoint or not api_key:
            QMessageBox.warning(self, "配置不完整", "该配置缺少 Endpoint 或 API Key")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")
        self._test_thread = _TestThread(endpoint, api_key, model)
        self._test_thread.result.connect(
            lambda msg: self._on_test_result(row, True, msg)
        )
        self._test_thread.error.connect(
            lambda msg: self._on_test_result(row, False, msg)
        )
        self._test_thread.finished.connect(
            lambda: self.test_btn.setEnabled(True) or self.test_btn.setText("🔗 测试连接")
        )
        self._test_thread.start()

    def _on_test_result(self, row: int, ok: bool, msg: str):
        status_item = self.table.item(row, 4)
        if ok:
            status_item.setText(f"✅ {msg}")
            status_item.setForeground(QColor("#4CAF50"))
            status_item.setToolTip(msg)
        else:
            status_item.setText(f"❌ {msg[:40]}")
            status_item.setForeground(QColor("#F44336"))
            status_item.setToolTip(msg)

    def _on_set_active(self):
        row = self._selected_row()
        if row < 0:
            return
        profiles = self._data.get("profiles", [])
        if row >= len(profiles):
            return
        name = profiles[row].get("name", "")
        self._data["active"] = name
        save_profiles(self._data)
        self._refresh_table()
        self.active_changed.emit(name)
        self.status_label.setText(f"已切换到: {name}")
