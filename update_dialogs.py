"""自动升级对话框：版本列表（含**更新说明**）与「发现新版本」确认框。

**为什么独立成模块**：`main_gui.py` 已 14000+ 行，而这两个对话框只依赖 PySide6
与纯展示逻辑 —— 拆出来后可以脱离 `MainWindow` 单独 offscreen 测试
（`test/test_update_notes_gui.py`）。

**契约**：本模块**不发任何网络请求**（网络 IO 由调用方的 QThread 做完，把结果传进来），
也不读写配置；`latest` / `releases` 的字段口径与 `auto_updater._extract_release_info`
一致：`version / url / notes / sha256 / html_url / asset_name / created_at / prerelease`。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from auto_updater import summarize_notes

NOTES_EMPTY_HINT = "（该版本未填写更新说明）"


def set_release_notes(browser: QTextBrowser, notes: str) -> None:
    """把 Release 说明渲染进只读文本区：**Markdown 优先**，渲染失败退回纯文本。

    说明为空时写一句占位提示（而不是留白 —— 让用户知道是「作者没写」，
    不是「程序没取到」）。渲染异常不能让对话框打不开，故整体兜底。
    """
    text = str(notes or "").strip()
    if not text:
        browser.setPlainText(NOTES_EMPTY_HINT)
        return
    setter = getattr(browser, "setMarkdown", None)
    if callable(setter):
        try:
            setter(text)
            return
        except Exception:  # Qt 版本/异常输入 → 退回纯文本
            pass
    browser.setPlainText(text)


def _open_url(parent, url: str) -> None:
    """打开外部链接；失败时把地址留给用户（不静默无反应）。"""
    from PySide6.QtWidgets import QMessageBox

    target = str(url or "").strip()
    if not target:
        QMessageBox.information(parent, "打开发布页", "该版本没有可打开的发布页地址。")
        return
    if not QDesktopServices.openUrl(QUrl(target)):
        QMessageBox.information(
            parent, "打开发布页", f"未能调起浏览器，请手动访问：\n{target}"
        )


def _version_cell(release: Dict, index: int, current_version: str) -> str:
    """列表项文案：`[最新] 1.23.86  (2026-10-18) ← 当前`。"""
    ver = str(release.get("version", "?") or "?")
    created = str(release.get("created_at", "") or "")[:10]
    tags = []
    if index == 0:
        tags.append("[最新]")
    if release.get("prerelease"):
        tags.append("[预发布]")
    cell = f"{' '.join(tags)} {ver}" if tags else ver
    if created:
        cell += f"  ({created})"
    if ver.strip().lower().lstrip("v") == str(current_version or "").strip().lower():
        cell += "  ← 当前"
    return cell.strip()


class VersionListDialog(QDialog):
    """「检查更新」版本列表：左列表 + 右**更新说明**，可下载任意版本。

    用法（调用方负责网络与下载）：

        dlg = VersionListDialog(self, releases, APP_VERSION, source_label=...)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._start_download(dlg.selected_release())
    """

    def __init__(
        self,
        parent,
        releases: List[Dict],
        current_version: str,
        source_label: str = "",
        release_page_url: str = "",
    ):
        super().__init__(parent)
        self._releases = list(releases or [])
        self._current_version = current_version
        self._release_page_url = release_page_url
        self.setWindowTitle("检查更新 - 版本列表")
        self.setMinimumSize(760, 480)

        layout = QVBoxLayout(self)

        tip_text = f"当前版本：{current_version}"
        if source_label:
            tip_text += f"\n更新源：{source_label}"
        tip_text += "\n选择任意版本查看更新说明并下载（默认最新版）："
        tip = QLabel(tip_text)
        tip.setWordWrap(True)
        layout.addWidget(tip)

        body = QHBoxLayout()

        self.listw = QListWidget()
        self.listw.setMinimumWidth(300)
        for i, rel in enumerate(self._releases):
            item = QListWidgetItem(_version_cell(rel, i, current_version))
            item.setData(Qt.ItemDataRole.UserRole, rel)
            item.setToolTip(summarize_notes(rel.get("notes") or "", 300))
            self.listw.addItem(item)
        if self.listw.count():
            self.listw.setCurrentRow(0)
        body.addWidget(self.listw, 1)

        right = QVBoxLayout()
        notes_title = QLabel("更新说明")
        notes_title.setStyleSheet("font-weight: bold;")
        right.addWidget(notes_title)

        self.notes_browser = QTextBrowser()
        self.notes_browser.setOpenExternalLinks(True)
        self.notes_browser.setMinimumWidth(380)
        right.addWidget(self.notes_browser, 1)
        body.addLayout(right, 2)

        layout.addLayout(body, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.page_btn = QPushButton("查看发布页")
        self.page_btn.setFixedWidth(110)
        self.page_btn.clicked.connect(self._open_selected_page)
        btn_row.addWidget(self.page_btn)

        self.download_btn = QPushButton("下载选中版本")
        self.download_btn.setObjectName("update_download_btn")
        self.download_btn.setFixedWidth(130)
        self.download_btn.clicked.connect(self._accept_selection)
        btn_row.addWidget(self.download_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.listw.currentRowChanged.connect(self._on_row_changed)
        self.listw.itemDoubleClicked.connect(lambda _item: self._accept_selection())
        self._on_row_changed(self.listw.currentRow())

    # ── 展示 ──────────────────────────────────────────────
    def selected_release(self) -> Dict:
        """当前选中的版本信息（无选中返回 {}）。"""
        item = self.listw.currentItem()
        if item is None:
            return {}
        return item.data(Qt.ItemDataRole.UserRole) or {}

    def _on_row_changed(self, row: int) -> None:
        rel = self.selected_release()
        set_release_notes(self.notes_browser, rel.get("notes") or "")
        has_url = bool(rel.get("url"))
        self.download_btn.setEnabled(bool(rel) and has_url)
        self.download_btn.setToolTip("" if has_url else "该版本没有安装包资产")
        self.page_btn.setEnabled(bool(rel.get("html_url") or self._release_page_url))

    def _open_selected_page(self) -> None:
        rel = self.selected_release()
        _open_url(self, rel.get("html_url") or self._release_page_url)

    def _accept_selection(self) -> None:
        rel = self.selected_release()
        if rel and rel.get("url"):
            self.accept()


class UpdateAvailableDialog(QDialog):
    """「发现新版本」确认框：版本对比 + **更新说明**（可滚动）+ 发布页入口。"""

    def __init__(
        self,
        parent,
        current_version: str,
        latest: Dict,
        release_page_url: str = "",
    ):
        super().__init__(parent)
        self._latest = dict(latest or {})
        self._release_page_url = release_page_url
        remote = str(self._latest.get("version", "?") or "?")
        self.setWindowTitle("发现新版本")
        self.setMinimumSize(640, 460)

        layout = QVBoxLayout(self)

        head = QLabel(f"发现新版本：{current_version} → {remote}")
        head.setStyleSheet("font-weight: bold;")
        layout.addWidget(head)

        asset = str(self._latest.get("asset_name") or "").strip()
        size_hint = f"安装包：{asset}" if asset else ""
        notes_hint = "以下为发布说明，可直接在下方查看："
        sub = QLabel(f"{size_hint}\n{notes_hint}" if size_hint else notes_hint)
        sub.setStyleSheet("color: #888;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self.notes_browser = QTextBrowser()
        self.notes_browser.setOpenExternalLinks(True)
        set_release_notes(self.notes_browser, self._latest.get("notes") or "")
        layout.addWidget(self.notes_browser, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.page_btn = QPushButton("查看发布页")
        self.page_btn.setFixedWidth(110)
        self.page_btn.setEnabled(
            bool(self._latest.get("html_url") or self._release_page_url)
        )
        self.page_btn.clicked.connect(self._open_page)
        btn_row.addWidget(self.page_btn)

        self.download_btn = QPushButton("下载并更新")
        self.download_btn.setObjectName("update_confirm_download_btn")
        self.download_btn.setFixedWidth(120)
        self.download_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.download_btn)

        self.later_btn = QPushButton("稍后")
        self.later_btn.setObjectName("update_confirm_later_btn")
        self.later_btn.setFixedWidth(80)
        self.later_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.later_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _open_page(self) -> None:
        _open_url(
            self, self._latest.get("html_url") or self._release_page_url
        )


def ask_update_available(
    parent,
    current_version: str,
    latest: Dict,
    release_page_url: str = "",
) -> bool:
    """弹「发现新版本」确认框，用户点「下载并更新」返回 True。"""
    dlg = UpdateAvailableDialog(
        parent, current_version, latest, release_page_url=release_page_url
    )
    return dlg.exec() == QDialog.DialogCode.Accepted


def ask_version_list(
    parent,
    releases: List[Dict],
    current_version: str,
    source_label: str = "",
    release_page_url: str = "",
) -> Optional[Dict]:
    """弹版本列表，用户确认下载则返回选中的版本信息（取消返回 None）。"""
    dlg = VersionListDialog(
        parent,
        releases,
        current_version,
        source_label=source_label,
        release_page_url=release_page_url,
    )
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.selected_release() or None
    return None


__all__ = [
    "NOTES_EMPTY_HINT",
    "VersionListDialog",
    "UpdateAvailableDialog",
    "ask_update_available",
    "ask_version_list",
    "set_release_notes",
]
