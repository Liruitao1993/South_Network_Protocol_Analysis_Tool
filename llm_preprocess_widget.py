# -*- coding: utf-8 -*-
"""LLM 日志预处理面板 UI

提供日志预处理工作台的完整 UI：输入/输出、prompt 编辑、模板选择、
异步 LLM 调用。集成到 MainWindow 的批量解析标签页。
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel,
    QPushButton, QComboBox, QGroupBox, QLineEdit, QFileDialog,
    QMessageBox, QSplitter, QProgressBar, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor

import os

from llm_preprocess import (
    LLMAPIClient, LLMChunker, LLMWorker,
    DEFAULT_PROMPT_TEMPLATES,
)


class LLMPreprocessWidget(QWidget):
    """LLM 日志预处理面板

    布局:
    ┌─────────────────────────────────────────────┐
    │ API 配置 [endpoint] [key] [model] [测试]    │
    ├─────────────────────────────────────────────┤
    │ 模板选择 [下拉]  分块大小 [输入]  行/块     │
    ├─────────────────────────────────────────────┤
    │ 原始日志输入                    预处理输出   │
    │ ┌──────────────────────┐ ┌──────────────┐  │
    │ │                      │ │              │  │
    │ │                      │ │              │  │
    │ └──────────────────────┘ └──────────────┘  │
    ├─────────────────────────────────────────────┤
    │ Prompt: [编辑框]                             │
    ├─────────────────────────────────────────────┤
    │ [执行预处理] [取消] [加载到批量解析] [保存]  │
    └─────────────────────────────────────────────┘
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build_ui()
        self._load_config()

    # ── UI 构建 ─────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(4, 4, 4, 4)

        # ─ API 配置栏 ─
        api_group = QGroupBox("LLM API 配置")
        api_layout = QHBoxLayout(api_group)
        api_layout.setSpacing(6)

        api_layout.addWidget(QLabel("Endpoint:"))
        self.endpoint_edit = QLineEdit("https://api.opencode.ai/v1")
        self.endpoint_edit.setPlaceholderText("https://api.opencode.ai/v1  (不含 /chat/completions)")
        self.endpoint_edit.setToolTip(
            "API 基础 URL，只需填到 /v1\n"
            "OpenCode Zen: https://api.opencode.ai/v1\n"
            "OpenAI: https://api.openai.com/v1\n"
            "DeepSeek: https://api.deepseek.com/v1\n"
            "本地 Ollama: http://localhost:11434/v1\n"
            "错误示例: .../v1/chat/completions（不要带这个后缀）"
        )
        self.endpoint_edit.setMaximumWidth(280)
        api_layout.addWidget(self.endpoint_edit)

        api_layout.addWidget(QLabel("Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("sk-...")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setMaximumWidth(220)
        api_layout.addWidget(self.api_key_edit)

        api_layout.addWidget(QLabel("模型:"))
        self.model_edit = QLineEdit("gpt-4o")
        self.model_edit.setMaximumWidth(140)
        api_layout.addWidget(self.model_edit)

        self.test_btn = QPushButton("测试连接")
        self.test_btn.setMaximumWidth(80)
        self.test_btn.clicked.connect(self._test_connection)
        api_layout.addWidget(self.test_btn)

        api_layout.addStretch()
        root.addWidget(api_group)

        # ─ Prompt / 模板 / 分块 ─
        prompt_bar = QHBoxLayout()
        prompt_bar.setSpacing(6)

        prompt_bar.addWidget(QLabel("模板:"))
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(160)
        for t in DEFAULT_PROMPT_TEMPLATES:
            self.template_combo.addItem(t["name"], t["prompt"])
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        prompt_bar.addWidget(self.template_combo)

        prompt_bar.addWidget(QLabel("分块:"))
        self.chunk_spin = QLineEdit("200")
        self.chunk_spin.setMaximumWidth(50)
        self.chunk_spin.setAlignment(Qt.AlignCenter)
        prompt_bar.addWidget(self.chunk_spin)
        prompt_bar.addWidget(QLabel("行/块"))

        prompt_bar.addStretch()
        root.addLayout(prompt_bar)

        # ─ 输入 / 输出分栏 ─
        splitter = QSplitter(Qt.Horizontal)

        # 左：原始日志输入
        in_group = QGroupBox("原始日志输入")
        in_layout = QVBoxLayout(in_group)
        in_toolbar = QHBoxLayout()
        self.load_file_btn = QPushButton("从文件加载")
        self.load_file_btn.clicked.connect(self._load_file)
        in_toolbar.addWidget(self.load_file_btn)
        self.paste_btn = QPushButton("从剪贴板粘贴")
        self.paste_btn.clicked.connect(self._paste_from_clipboard)
        in_toolbar.addWidget(self.paste_btn)
        self.clear_input_btn = QPushButton("清空")
        self.clear_input_btn.clicked.connect(lambda: self.input_edit.clear())
        in_toolbar.addWidget(self.clear_input_btn)
        in_toolbar.addStretch()
        self.input_line_count = QLabel("0 行")
        self.input_line_count.setStyleSheet("color:#666;")
        in_toolbar.addWidget(self.input_line_count)
        in_layout.addLayout(in_toolbar)
        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("粘贴原始日志内容...\n支持监控日志、串口输出、TCP 抓包等多种格式")
        in_layout.addWidget(self.input_edit)
        self.input_edit.textChanged.connect(self._update_line_count)
        splitter.addWidget(in_group)

        # 右：预处理输出
        out_group = QGroupBox("预处理输出")
        out_layout = QVBoxLayout(out_group)
        out_toolbar = QHBoxLayout()
        self.copy_output_btn = QPushButton("复制")
        self.copy_output_btn.clicked.connect(self._copy_output)
        out_toolbar.addWidget(self.copy_output_btn)
        self.clear_output_btn = QPushButton("清空")
        self.clear_output_btn.clicked.connect(lambda: self.output_edit.clear())
        out_toolbar.addWidget(self.clear_output_btn)
        out_toolbar.addStretch()
        self.output_line_count = QLabel("0 行")
        self.output_line_count.setStyleSheet("color:#666;")
        out_toolbar.addWidget(self.output_line_count)
        out_layout.addLayout(out_toolbar)
        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("预处理结果将显示在这里...\n可再次编辑后进行多轮预处理")
        out_layout.addWidget(self.output_edit)
        splitter.addWidget(out_group)

        splitter.setSizes([500, 500])
        root.addWidget(splitter, 1)  # stretch=1

        # ─ Prompt 编辑 ─
        prompt_group = QGroupBox("Prompt 指令")
        prompt_layout = QVBoxLayout(prompt_group)
        prompt_layout.setContentsMargins(4, 6, 4, 4)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setMaximumHeight(100)
        self.prompt_edit.setPlaceholderText("输入 LLM 预处理指令...")
        # 加载第一个模板
        if DEFAULT_PROMPT_TEMPLATES:
            self.prompt_edit.setPlainText(DEFAULT_PROMPT_TEMPLATES[0]["prompt"])
        prompt_layout.addWidget(self.prompt_edit)
        root.addWidget(prompt_group)

        # ─ 操作栏 ─
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.run_btn = QPushButton("▶ 执行预处理")
        self.run_btn.setMinimumHeight(32)
        self.run_btn.clicked.connect(self._run_preprocess)
        action_bar.addWidget(self.run_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_preprocess)
        action_bar.addWidget(self.cancel_btn)

        action_bar.addSpacing(16)

        self.load_to_batch_btn = QPushButton("加载到批量解析")
        self.load_to_batch_btn.setMinimumHeight(32)
        self.load_to_batch_btn.setEnabled(False)
        self.load_to_batch_btn.clicked.connect(self._load_to_batch)
        action_bar.addWidget(self.load_to_batch_btn)

        self.save_output_btn = QPushButton("保存结果")
        self.save_output_btn.setMinimumHeight(32)
        self.save_output_btn.setEnabled(False)
        self.save_output_btn.clicked.connect(self._save_output)
        action_bar.addWidget(self.save_output_btn)

        action_bar.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        action_bar.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#666;")
        action_bar.addWidget(self.status_label)

        root.addLayout(action_bar)

        # ─ 进度条引用 ─
        self._last_result = ""

    # ── 槽函数 ─────────────────────────────────────────

    def _update_line_count(self):
        text = self.input_edit.toPlainText()
        count = len(text.splitlines()) if text else 0
        self.input_line_count.setText(f"{count} 行")

    def _update_output_line_count(self):
        text = self.output_edit.toPlainText()
        count = len(text.splitlines()) if text else 0
        self.output_line_count.setText(f"{count} 行")

    def _on_template_changed(self, index):
        if 0 <= index < len(DEFAULT_PROMPT_TEMPLATES):
            self.prompt_edit.setPlainText(DEFAULT_PROMPT_TEMPLATES[index]["prompt"])

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "加载日志文件", "",
            "日志文件 (*.log *.txt *.hex *.bin *.csv);;所有文件 (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.input_edit.setPlainText(content)
            self.status_label.setText(f"已加载: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "加载失败", str(e))

    def _paste_from_clipboard(self):
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard:
            text = clipboard.text()
            if text:
                self.input_edit.setPlainText(text)
                self.status_label.setText("已从剪贴板粘贴")

    def _copy_output(self):
        text = self.output_edit.toPlainText()
        if text:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self.status_label.setText("已复制到剪贴板")

    def _save_output(self):
        text = self.output_edit.toPlainText()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存预处理结果", "",
            "文本文件 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.status_label.setText(f"已保存: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _test_connection(self):
        endpoint = self.endpoint_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        if not endpoint or not api_key:
            QMessageBox.warning(self, "配置不完整", "请填写 Endpoint 和 API Key")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")
        try:
            client = LLMAPIClient(endpoint, api_key, "gpt-4o", timeout=10)
            result = client.test_connection()
            QMessageBox.information(self, "连接成功", result)
            self.status_label.setText("API 连接正常")
        except Exception as e:
            QMessageBox.warning(self, "连接失败", str(e))
            self.status_label.setText("连接失败")
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("测试连接")

    def _run_preprocess(self):
        endpoint = self.endpoint_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        model = self.model_edit.text().strip()
        prompt = self.prompt_edit.toPlainText().strip()

        if not endpoint or not api_key:
            QMessageBox.warning(self, "配置不完整", "请填写 API Endpoint 和 Key")
            return
        if not prompt:
            QMessageBox.warning(self, "Prompt 为空", "请输入预处理指令")
            return

        # 输入来源：优先用 output_edit（多轮），其次 input_edit
        content = self.output_edit.toPlainText().strip()
        if not content:
            content = self.input_edit.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "输入为空", "请加载或粘贴日志内容")
            return

        # 分块大小
        try:
            chunk_lines = int(self.chunk_spin.text())
        except ValueError:
            chunk_lines = 200

        client = LLMAPIClient(endpoint, api_key, model, timeout=120)
        chunker = LLMChunker(chunk_lines)

        self._worker = LLMWorker(client, chunker, prompt, content)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)

        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.status_label.setText("LLM 预处理中...")

        self._worker.start()

    def _cancel_preprocess(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.status_label.setText("已取消")
        self._cleanup_worker()

    def _on_progress(self, msg):
        self.status_label.setText(msg)

    def _on_finished(self, result):
        self._cleanup_worker()
        self.output_edit.setPlainText(result)
        self._update_output_line_count()
        self._last_result = result
        self.load_to_batch_btn.setEnabled(bool(result.strip()))
        self.save_output_btn.setEnabled(bool(result.strip()))
        self.status_label.setText(f"预处理完成（{len(result.splitlines())} 行）")

    def _on_error(self, msg):
        self._cleanup_worker()
        self.status_label.setText(f"错误: {msg}")
        QMessageBox.warning(self, "LLM 预处理失败", msg)

    def _cleanup_worker(self):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.hide()
        self._worker = None

    def _load_to_batch(self):
        """将预处理结果传递给父窗口的批量解析输入框"""
        text = self.output_edit.toPlainText()
        if not text:
            return
        # 向上查找 MainWindow 的 batch_input
        parent = self.parent()
        while parent:
            if hasattr(parent, "batch_input"):
                parent.batch_input.setPlainText(text)
                self.status_label.setText("已加载到批量解析输入框")
                return
            parent = parent.parent()
        QMessageBox.information(self, "提示", "未找到批量解析输入框，请手动复制粘贴")

    # ── 配置持久化 ─────────────────────────────────────

    def _load_config(self):
        """从 config.json 加载 LLM 配置"""
        try:
            import json
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f).get("llm", {})
            self.endpoint_edit.setText(cfg.get("endpoint", "https://api.opencode.ai/v1"))
            self.api_key_edit.setText(cfg.get("api_key", ""))
            self.model_edit.setText(cfg.get("model", "gpt-4o"))
            self.chunk_spin.setText(str(cfg.get("chunk_lines", 200)))
        except Exception:
            pass

    def save_config(self):
        """保存 LLM 配置到 config.json"""
        import json
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg["llm"] = {
            "endpoint": self.endpoint_edit.text().strip(),
            "api_key": self.api_key_edit.text().strip(),
            "model": self.model_edit.text().strip(),
            "chunk_lines": int(self.chunk_spin.text() or 200),
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
