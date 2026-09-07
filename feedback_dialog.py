"""问题反馈对话框（PySide6 GUI 客户端）

帮助菜单「问题反馈」入口。用户填写类型/协议/描述/联系方式、可选附截图，
通过 QNetworkAccessManager 以 multipart/form-data POST 到 Reflex Web
服务端的 /api/feedback 接口，与 Web 页面共用同一个 feedback.db ——
桌面端提交的反馈在 Web 反馈列表中实时可见（带「桌面端」徽章）。

设计要点：
- 不 import 任何 reflex/web 模块（GUI 独立运行，reflex 可能未安装）；
  问题类型/协议选项/长度限制等常量在本文件内置，与 Web 端保持一致。
- 网络用 PySide6 自带 QtNetwork（QNetworkAccessManager + QHttpMultiPart），
  异步回调不阻塞 UI，无需新增第三方依赖。
- 自动收集环境信息（软件版本/OS/Python/机器名/当前协议）随 sys_info 字段提交。
- 服务器地址持久化在 config.json 的 "feedback" 段。
"""

from __future__ import annotations

import getpass
import json
import platform
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QJsonDocument, Qt, QUrl
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtNetwork import (
    QHttpMultiPart,
    QHttpPart,
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ── 常量（与 Web 端 feedback_model 对齐）────────────────────
ISSUE_TYPES = ["功能异常", "解析错误", "界面体验", "新功能建议", "其他"]
PROTOCOL_OPTIONS = [
    "不确定",
    "南网协议",
    "PLC RF协议",
    "HDLC/国网DLMS",
    "DLMS-APDU(国网)",
    "DLMS Wrapper裸报文",
    "DLMS-APDU裸报文",
    "DLT645-2007 电表协议",
    "国网协议",
    "698.45协议",
    "新一代载波协议",
    "国网新一代双模",
    "HDC 1.0 双模",
]
MAX_DESC_LEN = 2000
MAX_CONTACT_LEN = 100
MAX_SCREENSHOTS = 3
MAX_SHOT_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
SUBMIT_TIMEOUT_MS = 20000

_CONFIG_PATH: Path | None = None  # 由 main_gui 注入 config.json 路径；None 时不持久化


def set_config_path(path) -> None:
    """由主窗口注入 config.json 路径（app_paths.data_path("config.json")）。"""
    global _CONFIG_PATH
    try:
        _CONFIG_PATH = Path(path)
    except Exception:
        _CONFIG_PATH = None


def _config_path() -> Path | None:
    return _CONFIG_PATH


def normalize_server_url(url: str) -> str:
    """规范化服务器地址：去空白、去尾部斜杠、补 http:// 前缀。"""
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "http://" + u
    return u


def load_feedback_server_url() -> str:
    """读 config.json 的 "feedback"."server_url"；缺失返回默认值。"""
    p = _config_path()
    if p and p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            url = (data.get("feedback", {}) or {}).get("server_url", "")
            return normalize_server_url(url) or DEFAULT_SERVER_URL
        except Exception:
            pass
    return DEFAULT_SERVER_URL


def save_feedback_server_url(url: str) -> bool:
    """写 config.json 的 "feedback"."server_url"；成功返回 True。"""
    p = _config_path()
    if p is None:
        return False
    try:
        data = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        fb = data.get("feedback")
        if not isinstance(fb, dict):
            fb = {}
        fb["server_url"] = normalize_server_url(url)
        data["feedback"] = fb
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def collect_sys_info(app_version: str, build_date: str, protocol_name: str) -> str:
    """自动收集客户端环境信息（随 sys_info 字段提交，便于远程排查）。"""
    py_ver = sys.version.split()[0]
    lines = [
        f"软件版本: {app_version} ({build_date})",
        f"操作系统: {platform.platform()}",
        f"Python: {py_ver}",
        f"机器名: {platform.node()}",
        f"用户: {getpass.getuser()}",
        f"当前协议: {protocol_name or '不确定'}",
        "提交渠道: 桌面客户端(GUI)",
    ]
    return "\n".join(lines)


def validate_fields(
    issue_type: str,
    protocol: str,
    description: str,
    contact: str,
    shot_count: int,
    server_url: str,
) -> tuple[bool, str]:
    """提交前本地校验，返回 (ok, 错误消息)。"""
    if not normalize_server_url(server_url):
        return False, "请先设置反馈服务器地址（点击地址旁的「修改」按钮）"
    if issue_type not in ISSUE_TYPES:
        return False, "请选择有效的问题类型"
    if not protocol:
        return False, "请选择涉及协议"
    if not (description or "").strip():
        return False, "请填写问题描述"
    if len(description) > MAX_DESC_LEN:
        return False, f"问题描述不能超过 {MAX_DESC_LEN} 字"
    if len(contact or "") > MAX_CONTACT_LEN:
        return False, f"联系方式不能超过 {MAX_CONTACT_LEN} 字"
    if shot_count > MAX_SCREENSHOTS:
        return False, f"截图最多 {MAX_SCREENSHOTS} 张"
    return True, ""


def image_bytes_from_qimage(
    img: QImage, name_hint: str = "clipboard.png"
) -> tuple[str, bytes]:
    """把 QImage 编码为 PNG 字节，返回 (filename, bytes)。"""
    ba = QByteArray()
    buffer = __import__("PySide6.QtCore", fromlist=["QBuffer"]).QBuffer(ba)
    buffer.open(
        __import__("PySide6.QtCore", fromlist=["QIODevice"]).QIODevice.WriteOnly
    )
    img.save(buffer, "PNG")
    buffer.close()
    return ("clipboard.png", bytes(ba))


class FeedbackDialog(QDialog):
    """问题反馈对话框。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        app_version: str = "",
        build_date: str = "",
        protocol_name: str = "不确定",
    ):
        super().__init__(parent)
        self.setWindowTitle("问题反馈")
        self.setMinimumWidth(560)
        self._app_version = app_version
        self._build_date = build_date
        self._protocol_name = protocol_name
        self._shots: list[tuple[str, bytes]] = []  # (filename, bytes)
        self._nam = QNetworkAccessManager(self)
        self._reply = None
        self._build_ui()
        self._refresh_shots()

    # ── UI ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)

        # 类型 + 协议
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.type_combo = QComboBox()
        self.type_combo.addItems(ISSUE_TYPES)
        type_row = QHBoxLayout()
        type_row.addWidget(self.type_combo)
        type_row.addStretch()
        type_w = QWidget()
        type_w.setLayout(type_row)
        form.addRow("问题类型:", type_w)

        self.proto_combo = QComboBox()
        self.proto_combo.addItems(PROTOCOL_OPTIONS)
        # 自动带入当前协议（按名称模糊匹配）
        idx = 0
        for i in range(self.proto_combo.count()):
            if self._protocol_name and (
                self._protocol_name.split()[0] in self.proto_combo.itemText(i)
                or self.proto_combo.itemText(i) in self._protocol_name
            ):
                idx = i
                break
        self.proto_combo.setCurrentIndex(idx)
        proto_w = QWidget()
        proto_row = QHBoxLayout(proto_w)
        proto_row.setContentsMargins(0, 0, 0, 0)
        proto_row.addWidget(self.proto_combo)
        proto_row.addStretch()
        form.addRow("涉及协议:", proto_w)
        root.addLayout(form)

        # 描述
        root.addWidget(QLabel("问题描述（必填）:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText(
            "请描述遇到的问题：做了什么操作、预期结果、实际结果（可粘贴报文样例）"
        )
        self.desc_edit.setMinimumHeight(110)
        self.desc_edit.textChanged.connect(self._update_desc_count)
        root.addWidget(self.desc_edit)
        self.desc_count = QLabel(f"0 / {MAX_DESC_LEN}")
        self.desc_count.setAlignment(Qt.AlignRight)
        root.addWidget(self.desc_count)

        # 联系方式
        root.addWidget(QLabel("联系方式（选填，便于回访）:"))
        self.contact_edit = QLineEdit()
        self.contact_edit.setMaxLength(MAX_CONTACT_LEN)
        self.contact_edit.setPlaceholderText("如 QQ / 微信 / 邮箱")
        root.addWidget(self.contact_edit)

        # 截图
        shot_head = QHBoxLayout()
        shot_head.addWidget(
            QLabel(f"截图（选填，最多 {MAX_SCREENSHOTS} 张，jpg/png/webp，单张 ≤5MB）:")
        )
        shot_head.addStretch()
        self.paste_btn = QPushButton("粘贴截图")
        self.paste_btn.clicked.connect(self._paste_shot)
        self.add_file_btn = QPushButton("添加图片文件")
        self.add_file_btn.clicked.connect(self._add_file_shot)
        self.remove_shot_btn = QPushButton("移除选中")
        self.remove_shot_btn.clicked.connect(self._remove_shot)
        shot_head.addWidget(self.paste_btn)
        shot_head.addWidget(self.add_file_btn)
        shot_head.addWidget(self.remove_shot_btn)
        root.addLayout(shot_head)
        self.shot_list = QListWidget()
        self.shot_list.setMaximumHeight(96)
        root.addWidget(self.shot_list)

        # 自动环境信息（只读）
        self.sys_info = collect_sys_info(
            self._app_version, self._build_date, self._protocol_name
        )
        root.addWidget(QLabel("自动附带的环境信息:"))
        self.sys_edit = QTextEdit()
        self.sys_edit.setReadOnly(True)
        self.sys_edit.setPlainText(self.sys_info)
        self.sys_edit.setMaximumHeight(96)
        root.addWidget(self.sys_edit)

        # 服务器地址
        srv_row = QHBoxLayout()
        srv_row.addWidget(QLabel("反馈服务器:"))
        self.server_url = load_feedback_server_url()
        self.server_label = QLabel(self.server_url)
        self.server_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.server_label.setStyleSheet("color: #2563eb;")
        srv_row.addWidget(self.server_label, 1)
        self.edit_srv_btn = QPushButton("修改")
        self.edit_srv_btn.clicked.connect(self._edit_server_url)
        srv_row.addWidget(self.edit_srv_btn)
        root.addLayout(srv_row)

        # 状态提示
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        # 按钮
        buttons = QDialogButtonBox()
        self.submit_btn = buttons.addButton("提交反馈", QDialogButtonBox.AcceptRole)
        self.cancel_btn = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        self.submit_btn.clicked.connect(self._on_submit)
        self.cancel_btn.clicked.connect(self.reject)
        root.addWidget(buttons)

    def _update_desc_count(self):
        n = len(self.desc_edit.toPlainText())
        self.desc_count.setText(f"{n} / {MAX_DESC_LEN}")

    # ── 截图管理 ────────────────────────────────────────
    def _refresh_shots(self):
        self.shot_list.clear()
        for name, data in self._shots:
            item = QListWidgetItem(f"{name}  （{len(data) / 1024:.0f} KB）")
            pix = QPixmap()
            if pix.loadFromData(data):
                item.setIcon(
                    pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            self.shot_list.addItem(item)

    def _paste_shot(self):
        if len(self._shots) >= MAX_SCREENSHOTS:
            QMessageBox.warning(self, "提示", f"最多 {MAX_SCREENSHOTS} 张截图")
            return
        from PySide6.QtWidgets import QApplication

        img = QApplication.clipboard().image()
        if img.isNull():
            QMessageBox.information(self, "提示", "剪贴板中没有图片，请先复制截图")
            return
        name, data = image_bytes_from_qimage(img)
        self._shots.append((name, data))
        self._refresh_shots()

    def _add_file_shot(self):
        if len(self._shots) >= MAX_SCREENSHOTS:
            QMessageBox.warning(self, "提示", f"最多 {MAX_SCREENSHOTS} 张截图")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择截图", "", "图片文件 (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() not in ALLOWED_IMG_EXTS:
            QMessageBox.warning(self, "提示", "仅支持 jpg/png/webp 格式")
            return
        data = p.read_bytes()
        if len(data) > MAX_SHOT_SIZE:
            QMessageBox.warning(self, "提示", "单张截图不能超过 5MB")
            return
        self._shots.append((p.name, data))
        self._refresh_shots()

    def _remove_shot(self):
        row = self.shot_list.currentRow()
        if 0 <= row < len(self._shots):
            del self._shots[row]
            self._refresh_shots()

    # ── 服务器地址 ──────────────────────────────────────
    def _edit_server_url(self):
        url, ok = QInputDialog.getText(
            self,
            "反馈服务器地址",
            "请输入 Web 反馈服务器地址（含端口）：",
            text=self.server_url,
        )
        if ok:
            url = normalize_server_url(url)
            if not url:
                return
            self.server_url = url
            self.server_label.setText(url)
            if save_feedback_server_url(url):
                self._set_status(f"服务器地址已保存：{url}", ok=True)
            else:
                self._set_status("地址已应用（config.json 不可写，未持久化）", ok=True)

    def _set_status(self, text: str, ok: bool = False):
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #16a34a;" if ok else "color: #dc2626;")

    # ── 提交 ────────────────────────────────────────────
    def _on_submit(self):
        issue_type = self.type_combo.currentText()
        protocol = self.proto_combo.currentText()
        description = self.desc_edit.toPlainText()
        contact = self.contact_edit.text().strip()

        ok, msg = validate_fields(
            issue_type,
            protocol,
            description,
            contact,
            len(self._shots),
            self.server_url,
        )
        if not ok:
            self._set_status(msg)
            return

        self._set_submitting(True)
        url = normalize_server_url(self.server_url) + "/api/feedback"

        multi = QHttpMultiPart(QHttpMultiPart.FormDataType)

        def add_text_part(key: str, value: str):
            part = QHttpPart()
            part.setHeader(
                QNetworkRequest.ContentDispositionHeader, f'form-data; name="{key}"'
            )
            part.setBody(QByteArray(value.encode("utf-8")))
            multi.append(part)

        add_text_part("issue_type", issue_type)
        add_text_part("protocol", protocol)
        add_text_part("description", description)
        add_text_part("contact", contact)
        add_text_part("sys_info", self.sys_info)
        add_text_part("source", "gui")

        for i, (name, data) in enumerate(self._shots):
            part = QHttpPart()
            part.setHeader(
                QNetworkRequest.ContentDispositionHeader,
                f'form-data; name="screenshots"; filename="{name}"',
            )
            part.setHeader(QNetworkRequest.ContentTypeHeader, "image/png")
            ba = QByteArray(data)
            part.setBody(ba)
            multi.append(part)

        req = QNetworkRequest(QUrl(url))
        req.setTransferTimeout(SUBMIT_TIMEOUT_MS)
        self._reply = self._nam.post(req, multi)
        multi.setParent(self._reply)  # 随 reply 释放
        self._reply.finished.connect(self._on_reply_finished)

    def _set_submitting(self, busy: bool):
        self.submit_btn.setEnabled(not busy)
        self.submit_btn.setText("提交中..." if busy else "提交反馈")

    def _on_reply_finished(self):
        reply = self._reply
        if reply is None:
            return
        err = reply.error()
        try:
            if err == QNetworkReply.NoError:
                data = bytes(reply.readAll())
                doc = QJsonDocument.fromJson(QByteArray(data))
                obj = doc.object()
                if obj.get("ok"):
                    rid = obj.get("id", "?")
                    self._submit_success(rid)
                else:
                    self._submit_failed(f"服务器拒绝：{obj.get('error', '未知错误')}")
            else:
                # 尝试读错误 body 中的中文原因
                reason = ""
                try:
                    data = bytes(reply.readAll())
                    doc = QJsonDocument.fromJson(QByteArray(data))
                    reason = str(doc.object().get("error", ""))
                except Exception:
                    pass
                if reason:
                    self._submit_failed(f"服务器返回错误：{reason}")
                elif err in (QNetworkReply.OperationCanceledError,):
                    self._submit_failed("请求被取消")
                elif reply.errorString() and (
                    "timeout" in reply.errorString().lower()
                    or "timed out" in reply.errorString().lower()
                ):
                    self._submit_failed("提交超时，请检查网络后重试")
                else:
                    self._submit_failed(
                        "无法连接反馈服务器，请检查地址或网络后重试"
                        f"（{self.server_url}）"
                    )
        finally:
            reply.deleteLater()
            self._reply = None
            self._set_submitting(False)

    def _submit_success(self, rid):
        self._set_status(f"反馈提交成功（编号 #{rid}），感谢您的支持！", ok=True)
        box = QMessageBox(self)
        box.setWindowTitle("提交成功")
        box.setIcon(QMessageBox.Information)
        box.setText(f"反馈已提交（编号 #{rid}）。\n可在 Web 反馈页查看处理进度。")
        open_btn = box.addButton("在浏览器打开反馈页", QMessageBox.AcceptRole)
        box.addButton("关闭", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(
                QUrl(normalize_server_url(self.server_url) + "/feedback")
            )
        self.accept()

    def _submit_failed(self, msg: str):
        self._set_status(msg)
        QMessageBox.warning(self, "提交失败", msg)
