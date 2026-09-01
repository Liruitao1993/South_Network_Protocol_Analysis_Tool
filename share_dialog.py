"""GUI 报文分享对话框（share_dialog.py）

单帧解析后把有价值的命令帧分享到 Web 服务端（与 Web /share 页共享
frameshare.db）。复用 feedback_dialog 的服务器地址配置（同一台服务器），
提交走 POST /api/frameshare（JSON，QtNetwork 异步，零新增依赖）。

约定：
- frame_hex 由 main_gui 传入（self._last_parsed_hex，空格分隔大写）；
- 分享人记忆在 config.json "share"."last_sharer"；
- 服务器地址读写复用 feedback_dialog.load/save_feedback_server_url；
- 发送成功后可一键在浏览器打开 /share 页查看。

测试：test/test_frame_share.py（纯逻辑 + offscreen 冒烟）。
"""

from __future__ import annotations

import json
import platform

from PySide6.QtCore import QUrl
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
)

import feedback_dialog as fd

# 分享协议选项（与 Web share_model.SHARE_PROTOCOLS 同源语义）
SHARE_PROTOCOLS = [
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
MAX_SHARER_LEN = 50
MAX_NOTE_LEN = 500
SUBMIT_TIMEOUT_MS = 20000


# ── config 读写（分享人记忆；config 路径由 main_gui 注入 feedback_dialog） ──


def _read_config() -> dict:
    p = fd._config_path()
    if p and p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_last_sharer() -> str:
    """读 config.json "share"."last_sharer"；缺失返回空。"""
    data = _read_config()
    val = (data.get("share", {}) or {}).get("last_sharer", "")
    return str(val) if isinstance(val, str) else ""


def save_last_sharer(name: str) -> bool:
    """写 config.json "share"."last_sharer"；成功返回 True。"""
    p = fd._config_path()
    if p is None:
        return False
    try:
        data = _read_config()
        if not isinstance(data, dict):
            data = {}
        sh = data.get("share")
        if not isinstance(sh, dict):
            sh = {}
        sh["last_sharer"] = (name or "").strip()
        data["share"] = sh
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def build_payload(frame_hex: str, protocol: str, sharer: str, note: str) -> bytes:
    """构造提交 JSON body（纯函数，单测覆盖字段名与来源标记）。"""
    payload = {
        "frame_hex": (frame_hex or "").strip(),
        "protocol": (protocol or "不确定").strip(),
        "sharer": (sharer or "").strip(),
        "note": (note or "").strip(),
        "source": "gui",
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def validate_fields(
    sharer: str, protocol: str, server_url: str, frame_hex: str
) -> tuple[bool, str]:
    """提交前本地校验，返回 (ok, 错误消息)。与 Web submit_share 口径一致。"""
    if not fd.normalize_server_url(server_url):
        return False, "请先设置反馈服务器地址（反馈对话框中可修改）"
    if not (frame_hex or "").strip():
        return False, "没有可分享的报文"
    if protocol not in SHARE_PROTOCOLS:
        return False, "请选择有效协议"
    if not (sharer or "").strip():
        return False, "请填写分享人"
    if len(sharer.strip()) > MAX_SHARER_LEN:
        return False, f"分享人不能超过 {MAX_SHARER_LEN} 字"
    return True, ""


def collect_sys_info(app_version: str, protocol_name: str) -> str:
    """自动收集环境信息（作为说明默认值的一部分，仅展示用）。"""
    return (
        f"GUI v{app_version} | {platform.system()} {platform.release()} | "
        f"Python {platform.python_version()} | {protocol_name}"
    )


class ShareDialog(QDialog):
    """报文分享对话框：展示帧 + 分享人/协议/说明 → POST /api/frameshare。"""

    def __init__(
        self,
        parent=None,
        frame_hex: str = "",
        protocol_name: str = "",
        app_version: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("分享此帧")
        self.setMinimumWidth(520)
        self._nam = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        # 服务端返回的分享页 URL（dev 前后端分端口时与 API 地址不同端口）；
        # 空则兜底 server_url + /share（旧服务端无 share_url 字段）
        self._share_url = ""
        self._frame_hex = (frame_hex or "").strip()
        self._app_version = app_version
        self.server_url = fd.load_feedback_server_url()

        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        # ── 报文（只读展示）──
        self.hex_view = QPlainTextEdit()
        self.hex_view.setPlainText(self._frame_hex)
        self.hex_view.setReadOnly(True)
        self.hex_view.setFont(self._mono_font())
        self.hex_view.setMaximumHeight(96)
        form.addRow("报文:", self.hex_view)

        # ── 协议 ──
        self.proto_combo = QComboBox()
        self.proto_combo.addItems(SHARE_PROTOCOLS)
        idx = self.proto_combo.findText(protocol_name or "")
        self.proto_combo.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("协议:", self.proto_combo)

        # ── 分享人（必填，记住上次）──
        self.sharer_edit = QLineEdit()
        self.sharer_edit.setMaxLength(MAX_SHARER_LEN)
        self.sharer_edit.setText(load_last_sharer())
        self.sharer_edit.setPlaceholderText(f"你的名字/昵称（≤{MAX_SHARER_LEN} 字）")
        form.addRow("分享人*:", self.sharer_edit)

        # ── 说明（选填，预填环境信息）──
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("这帧报文的用途/场景，方便他人理解")
        self.note_edit.setPlainText(f"来自桌面端 {collect_sys_info(app_version, self.proto_combo.currentText())}")
        self.note_edit.setMaximumHeight(72)
        form.addRow("说明:", self.note_edit)

        lay.addLayout(form)

        # ── 服务器地址行 ──
        srv_row = QHBoxLayout()
        srv_row.addWidget(QLabel("服务器:"))
        self.server_edit = QLineEdit()
        self.server_edit.setText(self.server_url)
        srv_row.addWidget(self.server_edit, 1)
        self._save_srv_btn = QPushButton("保存")
        self._save_srv_btn.setMaximumWidth(56)
        self._save_srv_btn.clicked.connect(self._on_save_server)
        srv_row.addWidget(self._save_srv_btn)
        lay.addLayout(srv_row)

        # ── 提示条 ──
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        lay.addWidget(self.status_label)

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._browser_btn = QPushButton("在浏览器查看分享页")
        self._browser_btn.clicked.connect(self._open_share_page)
        self._browser_btn.setVisible(False)
        btn_row.addWidget(self._browser_btn)
        self._submit_btn = QPushButton("分享")
        self._submit_btn.setDefault(True)
        self._submit_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(self._submit_btn)
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)
        lay.addLayout(btn_row)

    # ── 工具 ──

    @staticmethod
    def _mono_font():
        from PySide6.QtGui import QFont

        f = QFont("Consolas")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(9)
        return f

    def _open_share_page(self):
        # 优先用服务端下发的分享页 URL（dev 模式指向前端端口）；旧服务端兜底
        url = self._share_url or (self.server_url + "/share")
        QDesktopServices.openUrl(QUrl(url))

    def _on_save_server(self):
        url = self.server_edit.text()
        ok = fd.save_feedback_server_url(url)
        self.server_url = fd.normalize_server_url(url)
        self.status_label.setText(
            "服务器地址已保存" if ok else "配置未就绪（本次会话内有效）"
        )

    # ── 提交 ──

    def _on_submit(self):
        ok, msg = validate_fields(
            self.sharer_edit.text(),
            self.proto_combo.currentText(),
            self.server_edit.text(),
            self._frame_hex,
        )
        if not ok:
            self.status_label.setText(msg)
            return

        body = build_payload(
            self._frame_hex,
            self.proto_combo.currentText(),
            self.sharer_edit.text(),
            self.note_edit.toPlainText(),
        )
        req = QNetworkRequest(QUrl(self.server_url + "/api/frameshare"))
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        req.setTransferTimeout(SUBMIT_TIMEOUT_MS)

        self._submit_btn.setEnabled(False)
        self._submit_btn.setText("提交中...")
        self.status_label.setText("正在提交...")

        self._reply = self._nam.post(req, body)
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self):
        reply = self._reply
        if reply is None:
            return
        self._submit_btn.setEnabled(True)
        self._submit_btn.setText("分享")
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.status_label.setText(
                    f"提交失败: {reply.errorString()}（请检查服务器地址与网络）"
                )
                return
            status = reply.attribute(
                QNetworkRequest.Attribute.HttpStatusCodeAttribute
            )
            data = bytes(reply.readAll().data())
            try:
                resp = json.loads(data.decode("utf-8"))
            except Exception:
                self.status_label.setText(f"响应解析失败（HTTP {status}）")
                return
            if status == 200 and resp.get("ok"):
                save_last_sharer(self.sharer_edit.text())
                sid = resp.get("id", "?")
                # 服务端按自身部署模式给出浏览器可访问的页面地址
                self._share_url = str(resp.get("share_url") or "") or (
                    self.server_url + "/share"
                )
                self.status_label.setText(f"分享成功（#{sid}）")
                self._browser_btn.setVisible(True)
                ret = QMessageBox.information(
                    self,
                    "分享成功",
                    f"报文已分享（#{sid}），所有用户可在「报文分享」页查看。\n\n"
                    "是否立即在浏览器打开分享页？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ret == QMessageBox.StandardButton.Yes:
                    self._open_share_page()
                self.accept()
            else:
                self.status_label.setText(str(resp.get("error", f"HTTP {status}")))
        except Exception as e:  # noqa: BLE001 - 网络回调不应抛出
            self.status_label.setText(f"提交异常: {e}")
        finally:
            reply.deleteLater()
            self._reply = None



