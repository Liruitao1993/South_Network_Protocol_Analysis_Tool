# -*- coding: utf-8 -*-
"""GitHub Issue 反馈对话框（PySide6 GUI 客户端）。

从「帮助 → 提交问题到 GitHub」进入，把用户的现场信息整理成一条 issue：

- **Bug / 功能建议**两种形态（对应仓库里的 ``bug.yml`` / ``feature.yml`` 两张表单）；
- 自动收集**运行环境**（版本 / 系统 / 是否 exe），**不含**用户名等个人信息；
- 可一键带入**当前协议**与**最近一次解析的报文 hex**（现场复现最关键的两样）；
- 两种提交通道：
  1. **直接建单**（有令牌时）：调 GitHub REST API，issue 立刻出现在仓库里，
     弹窗给出编号与链接 —— 这是真正的「自动提交」，不需要用户碰浏览器；
  2. **浏览器预填**（无令牌时）：按 Issue Form 的字段 id 预填好表单，
     打开浏览器让用户点一次提交 —— 不需要任何令牌，也不会把令牌存进 exe。

设计约束：
- **不 import ``main_gui``**（主程序 14000+ 行，反向依赖会循环导入）；
  协议名、报文 hex 由主窗口传入。
- 网络请求走 QtNetwork（异步，不卡界面）；令牌与仓库地址由主窗口注入。
- **令牌不写进 exe**：只落本机 config.json 的 ``github_issue.token`` 段，
  ``diagnostics.redact`` 会把它脱敏；环境变量 ``GITHUB_TOKEN`` 优先级更高。

测试：test/test_github_issue.py（纯逻辑 + offscreen 冒烟）。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import github_issue as gi

SUBMIT_TIMEOUT_MS = 20000
MAX_TEXT_LEN = 4000


class GitHubIssueDialog(QDialog):
    """提交问题到 GitHub 的对话框。"""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        owner: str = "",
        repo: str = "",
        token: str = "",
        app_version: str = "",
        build_date: str = "",
        protocol_option: str = "",
        frame_hex: str = "",
        config_path: Any = None,
        crash_summary: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("提交问题到 GitHub")
        self.setMinimumWidth(620)

        self._owner = str(owner or "").strip()
        self._repo = str(repo or "").strip()
        self._token = str(token or "").strip()
        self._config_path = config_path
        self._app_version = app_version
        self._build_date = build_date
        self._protocol_option = protocol_option
        self._frame_hex = str(frame_hex or "").strip()
        self._crash_summary = str(crash_summary or "").strip()
        self._reply: Optional[QNetworkReply] = None
        self._created_url = ""

        self._nam = QNetworkAccessManager(self)
        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)

        # 仓库 + 令牌状态行
        repo_row = QHBoxLayout()
        repo_row.addWidget(QLabel("目标仓库:"))
        self.repo_label = QLabel(self._repo_text())
        self.repo_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.repo_label.setStyleSheet("color: #2563eb;")
        repo_row.addWidget(self.repo_label, 1)
        root.addLayout(repo_row)

        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("令牌:"))
        self.token_edit = QLineEdit(self._token)
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText(
            "GitHub Token（可留空，改用浏览器提交）"
        )
        self.token_edit.setMaxLength(300)
        token_row.addWidget(self.token_edit, 1)
        self.show_token_btn = QPushButton("显示")
        self.show_token_btn.setFixedWidth(56)
        self.show_token_btn.clicked.connect(self._toggle_token)
        token_row.addWidget(self.show_token_btn)
        root.addLayout(token_row)

        self.token_hint = QLabel(
            f"{gi.TOKEN_SCOPE_HINT}；令牌只保存在本机 config.json"
            "（诊断包会自动脱敏），不会随程序分发。"
        )
        self.token_hint.setWordWrap(True)
        self.token_hint.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self.token_hint)

        # 类型 + 协议
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.kind_combo = QComboBox()
        self.kind_combo.addItem(gi.ISSUE_KINDS["bug"]["label"], "bug")
        self.kind_combo.addItem(gi.ISSUE_KINDS["feature"]["label"], "feature")
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        form.addRow("类型:", self.kind_combo)

        self.protocol_combo = QComboBox()
        for text in gi.FORM_PROTOCOL_OPTIONS:
            self.protocol_combo.addItem(text)
        self._select_protocol(self._protocol_option)
        form.addRow("相关协议:", self.protocol_combo)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("一句话描述问题，例如：698.45 帧解析时长度域越界")
        self.title_edit.setMaxLength(200)
        form.addRow("标题:", self.title_edit)

        root.addLayout(form)

        # 正文各段（Bug 与建议的字段不同，用 QStackedWidget 切换）
        from PySide6.QtWidgets import QStackedWidget

        self.stack = QStackedWidget(self)

        bug_page = QWidget(self)
        bug_form = QFormLayout(bug_page)
        bug_form.setLabelAlignment(Qt.AlignRight)

        self.frame_edit = QPlainTextEdit()
        self.frame_edit.setPlaceholderText(
            "可复现的最小报文（十六进制，空格分隔）。敏感地址可替换为等长字节，"
            "但请保持长度与校验可复现"
        )
        self.frame_edit.setPlainText(self._frame_hex)
        self.frame_edit.setMaximumHeight(80)
        bug_form.addRow("报文:", self.frame_edit)

        self.expected_edit = QTextEdit()
        self.expected_edit.setPlaceholderText("你认为正确的解析 / 校验结论（可引用协议条款）")
        self.expected_edit.setMaximumHeight(64)
        bug_form.addRow("期望结果:", self.expected_edit)

        self.actual_edit = QTextEdit()
        self.actual_edit.setPlaceholderText("工具给出的实际结果（可粘贴解析结果表格）")
        if self._crash_summary:
            # 崩溃现场较长：给足高度，否则用户看不到关键行（traceback 在中后段）
            self.actual_edit.setMaximumHeight(200)
            self.actual_edit.setPlainText(
                gi.sanitize_crash_summary(self._crash_summary)
            )
        else:
            self.actual_edit.setMaximumHeight(64)
        bug_form.addRow("实际结果:", self.actual_edit)

        self.steps_edit = QTextEdit()
        self.steps_edit.setPlaceholderText("1. 选择协议 X\n2. 粘贴报文\n3. 看到 …")
        self.steps_edit.setMaximumHeight(72)
        bug_form.addRow("复现步骤:", self.steps_edit)

        self.env_edit = QTextEdit()
        self.env_edit.setReadOnly(True)
        self.env_edit.setMaximumHeight(56)
        self.env_edit.setPlainText(
            gi.collect_env_info(self._app_version, self._build_date)
        )
        bug_form.addRow("运行环境:", self.env_edit)

        self.contact_edit = QLineEdit()
        self.contact_edit.setMaxLength(120)
        self.contact_edit.setPlaceholderText("选填，便于回访（如 QQ / 微信 / 邮箱）")
        bug_form.addRow("联系方式:", self.contact_edit)

        self.stack.addWidget(bug_page)

        feature_page = QWidget(self)
        feature_form = QFormLayout(feature_page)
        feature_form.setLabelAlignment(Qt.AlignRight)

        self.scenario_edit = QTextEdit()
        self.scenario_edit.setPlaceholderText(
            "谁在什么环节用、现在的痛点是什么（现场要解决什么问题、现在绕路怎么做）"
        )
        self.scenario_edit.setMaximumHeight(88)
        feature_form.addRow("使用场景:", self.scenario_edit)

        self.proposal_edit = QTextEdit()
        self.proposal_edit.setPlaceholderText(
            "你期望的样子（报文示例、协议条款、截图或同类工具的做法都可以贴）"
        )
        self.proposal_edit.setMaximumHeight(88)
        feature_form.addRow("期望的样子:", self.proposal_edit)

        self.samples_edit = QPlainTextEdit()
        self.samples_edit.setPlaceholderText("选填：报文 / 协议资料（可脱敏）")
        self.samples_edit.setMaximumHeight(72)
        feature_form.addRow("报文/资料:", self.samples_edit)

        self.stack.addWidget(feature_page)
        root.addWidget(self.stack)

        # 状态
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        # 按钮
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.browser_btn = QPushButton("在浏览器中提交")
        self.browser_btn.setToolTip(
            "不需要令牌：把内容按 Issue Form 字段预填好，打开网页后点一次提交"
        )
        self.browser_btn.clicked.connect(self._on_open_browser)
        buttons.addWidget(self.browser_btn)

        self.submit_btn = QPushButton("直接提交到 GitHub")
        self.submit_btn.setDefault(True)
        self.submit_btn.clicked.connect(self._on_submit)
        buttons.addWidget(self.submit_btn)

        self.cancel_btn = QPushButton("关闭")
        self.cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_btn)
        root.addLayout(buttons)

    # ── 辅助 ────────────────────────────────────────────────────────
    def _repo_text(self) -> str:
        if self._owner and self._repo:
            return f"{self._owner}/{self._repo}"
        return "（未配置仓库地址）"

    def _select_protocol(self, option: str):
        """按协议选项文本选中下拉项；找不到则保持第一项。"""
        idx = self.protocol_combo.findText(option or "")
        self.protocol_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _toggle_token(self):
        echo = (
            QLineEdit.Normal if self.token_edit.echoMode() == QLineEdit.Password
            else QLineEdit.Password
        )
        self.token_edit.setEchoMode(echo)
        self.show_token_btn.setText("隐藏" if echo == QLineEdit.Normal else "显示")

    def _on_kind_changed(self):
        self.stack.setCurrentIndex(1 if self.kind_combo.currentData() == "feature" else 0)

    def current_kind(self) -> str:
        return str(self.kind_combo.currentData() or "bug")

    def _form_values(self) -> Dict[str, str]:
        """收集表单字段（键 = Issue Form 字段 id，与仓库 yml 模板一致）。"""
        kind = self.current_kind()
        if kind == "feature":
            return {
                "kind": "新增协议 / 协议子集",
                "scenario": self.scenario_edit.toPlainText().strip(),
                "proposal": self.proposal_edit.toPlainText().strip(),
                "samples": self.samples_edit.toPlainText().strip(),
            }
        return {
            "version": str(self._app_version or ""),
            "protocol": self.protocol_combo.currentText(),
            "frame": self.frame_edit.toPlainText().strip(),
            "expected": self.expected_edit.toPlainText().strip(),
            "actual": self.actual_edit.toPlainText().strip(),
            "steps": self.steps_edit.toPlainText().strip(),
            "env": self.env_edit.toPlainText().strip(),
            "contact": self.contact_edit.text().strip(),
        }

    def _summary(self) -> str:
        """标题摘要：Bug 取实际结果首行，建议取场景首行；都没有就用用户填的标题。"""
        kind = self.current_kind()
        if kind == "feature":
            source = self.scenario_edit.toPlainText()
        else:
            source = self.actual_edit.toPlainText() or self.expected_edit.toPlainText()
        for line in (source or "").splitlines():
            text = line.strip()
            if text:
                return gi.truncate(text, 80)
        return self.title_edit.text().strip()

    def _build_title(self) -> str:
        summary = self._summary()
        if not summary:
            summary = self.title_edit.text().strip()
        if not summary:
            summary = "未填写摘要"
        return gi.build_issue_title(self.current_kind(), summary)

    def _build_body(self) -> str:
        values = self._form_values()
        title = self.title_edit.text().strip()
        if title:
            values["expected"] = (
                f"{values.get('expected', '')}\n\n补充说明：{title}".strip()
            )
        return gi.build_issue_body(self.current_kind(), **values)

    def _set_status(self, text: str, ok: bool = False):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            "color: #16a34a;" if ok else "color: #dc2626;"
        )

    # ── 提交：浏览器预填（兜底） ───────────────────────────────────
    def _on_open_browser(self):
        if not self._owner or not self._repo:
            self._set_status("未配置仓库地址，无法生成提交链接")
            return
        try:
            url = gi.build_prefill_url(
                self._owner, self._repo, self.current_kind(), self._form_values()
            )
        except Exception as exc:                          # noqa: BLE001
            self._set_status(f"生成提交链接失败：{exc}")
            return
        if len(url) > gi.MAX_PREFILL_URL:
            self._set_status(
                f"内容过长（链接 {len(url)} 字符），请删减后重试 —— "
                "或改用「直接提交到 GitHub」"
            )
            return
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(
                self,
                "提交问题到 GitHub",
                f"未能调起浏览器，请手动访问：\n{url}",
            )
            return
        self._set_status(
            "已打开 GitHub 表单（内容已按字段预填），请在网页上补充后点「Submit new issue」",
            ok=True,
        )

    # ── 提交：API 直连（真自动） ───────────────────────────────────
    def _on_submit(self):
        token = self.token_edit.text().strip()
        if not token:
            self._set_status(
                "请先填入 GitHub 令牌；没有令牌可改用「在浏览器中提交」"
            )
            return
        if not self._owner or not self._repo:
            self._set_status("未配置仓库地址，无法提交")
            return

        title = self._build_title()
        body = self._build_body()
        kind = self.current_kind()
        labels = list(gi.ISSUE_KINDS.get(kind, gi.ISSUE_KINDS["bug"])["labels"])

        self._set_submitting(True)
        self._set_status("正在提交…")

        request = QNetworkRequest(
            QUrl(f"{gi.GITHUB_API_BASE}/repos/{self._owner}/{self._repo}/issues")
        )
        request.setHeader(
            QNetworkRequest.KnownHeaders.AuthorizationHeader, f"Bearer {token}"
        )
        request.setHeader(
            QNetworkRequest.KnownHeaders.AcceptHeader, "application/vnd.github+json"
        )
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader,
            "nw-protocol-parser-issue-reporter",
        )
        request.setRawHeader(b"X-GitHub-Api-Version", b"2022-11-28")
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/json; charset=utf-8",
        )
        request.setTransferTimeout(SUBMIT_TIMEOUT_MS)

        payload = json.dumps(
            {"title": title, "body": body, "labels": labels}, ensure_ascii=False
        ).encode("utf-8")

        self._reply = self._nam.post(request, payload)
        self._reply.finished.connect(self._on_reply_finished)

    def _set_submitting(self, busy: bool):
        self.submit_btn.setEnabled(not busy)
        self.submit_btn.setText("提交中…" if busy else "直接提交到 GitHub")

    def _on_reply_finished(self):
        reply = self._reply
        if reply is None:
            return
        try:
            status = reply.attribute(
                QNetworkRequest.Attribute.HttpStatusCodeAttribute
            )
            data = bytes(reply.readAll().data())
            try:
                obj = json.loads(data.decode("utf-8", errors="replace")) or {}
            except Exception:                             # noqa: BLE001
                obj = {}

            if reply.error() != QNetworkReply.NetworkError.NoError:
                reason = gi.describe_http_status(int(status or 0))
                detail = str(obj.get("message") or "") if isinstance(obj, dict) else ""
                if detail:
                    reason = f"{reason} —— {detail}"
                self._set_status(f"提交失败：{reason}")
                return

            if int(status or 0) != 201 or not isinstance(obj, dict) or not obj.get("number"):
                reason = gi.describe_http_status(int(status or 0))
                self._set_status(f"提交失败：{reason}")
                return

            number = obj.get("number")
            url = str(obj.get("html_url") or "")
            self._created_url = url
            self._set_status(f"提交成功（#{number}），感谢反馈！", ok=True)

            box = QMessageBox(self)
            box.setWindowTitle("提交成功")
            box.setIcon(QMessageBox.Icon.Information)
            box.setText(
                f"已创建 issue #{number}\n{url}\n\n"
                "作者可以在仓库的 Issues 页面看到你的反馈。"
            )
            view_btn = None
            if url:
                view_btn = box.addButton("查看 issue", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if view_btn is not None and box.clickedButton() is view_btn:
                try:
                    QDesktopServices.openUrl(QUrl(url))
                except Exception:                         # noqa: BLE001
                    pass
            self.accept()
        finally:
            reply.deleteLater()
            self._reply = None
            self._set_submitting(False)

    # ── 对外接口 ────────────────────────────────────────────────────
    def created_url(self) -> str:
        """成功提交后的 issue 链接（未提交返回空串）。"""
        return self._created_url

    def persist_token(self) -> bool:
        """把令牌写回本机 config.json（由调用方在用户填了令牌后决定是否调用）。

        令牌只落**本机** config.json 的 ``github_issue.token`` 段，不随程序分发；
        ``diagnostics.redact`` 会把它脱敏，诊断包不会泄露。
        """
        if not self._config_path:
            return False
        section = gi.load_issue_config(self._config_path)
        section["token"] = self.token_edit.text().strip()
        return gi.save_issue_config(self._config_path, section)


__all__ = ["GitHubIssueDialog", "SUBMIT_TIMEOUT_MS", "MAX_TEXT_LEN"]
