# -*- coding: utf-8 -*-
"""自动升级的下载面板（非模态、可后台运行、可暂停 / 取消）。

为什么独立成模块：`main_gui.py` 已 14000+ 行，而这块只依赖 PySide6 与
`downloader.DownloadProgress`，拆出来可以脱离 `MainWindow` 单独 offscreen 测试
（`test/test_update_download_dialog.py`）。

界面要点（用户口径）：
- **看得见线程**：顶部显示「N 线程并发」，表格逐行显示每个分段的实时进度；
- **看得见速率**：当前速度（MB/s）、已下载 / 总量、剩余时间；
- **不挡操作**：``setWindowModality(NonModal)`` —— 下载期间可以继续用主程序，
  还可以「后台运行」把面板收起来（进度仍在跑，状态栏可见）；
- **能暂停**：暂停后各线程在 64 KB 块边界停下，已完成字节保留（可断点续传）；
- **能取消**：取消会**真正停下来**（不等待卡住的分段）并清理缓存；
- **能回收磁盘**：另有一个「清理缓存」按钮——关窗口 / 退出程序时保留 ``.part``
  供下次续传，想现在腾空间就点它（1.23.96）。

本模块**不做网络 IO**：下载在 `main_gui._UpdateDownloadWorker` 里跑，
通过 ``update_progress(DownloadProgress)`` 把快照喂进来。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import downloader as dl
from gui_utils import fit_btn_width

#: 分段行在每种全局状态下的显示文案（表状态列）
_STATE_TEXT = {
    "paused": "⏸ 已暂停",
    "restart": "↻ 重新开始",
    "cancelled": "✖ 已取消",
    "completed": "✔ 完成",
    "running": "⏳ 下载中",
}

#: 表格列（线程 / 区间 / 进度 / 已下载 / 状态）
COL_THREAD = 0
COL_RANGE = 1
COL_PROGRESS = 2
COL_DONE = 3
COL_STATE = 4
HEADERS = ("线程", "区间（字节）", "进度", "已下载", "状态")


def _format_eta(remaining_bytes: float, speed_bps: float) -> str:
    """剩余时间估算（速率未知时给「—」）。"""
    if speed_bps <= 0 or remaining_bytes <= 0:
        return "—"
    seconds = int(remaining_bytes / speed_bps)
    if seconds < 60:
        return f"约 {seconds} 秒"
    if seconds < 3600:
        return f"约 {seconds // 60} 分 {seconds % 60} 秒"
    return f"约 {seconds // 3600} 小时 {(seconds % 3600) // 60} 分"


class UpdateDownloadDialog(QDialog):
    """下载进度面板：逐线程进度 + 速率 + 暂停/取消/后台。"""

    pause_requested = Signal()
    resume_requested = Signal()
    cancel_requested = Signal()
    background_requested = Signal()
    discard_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None, *, version: str = "",
                 total_size: int = 0, threads: int = 0):
        super().__init__(parent)
        self.setWindowTitle(f"下载更新 {version}".strip())
        # **非模态**：下载期间主程序照常可用（此前是 WindowModal，挡住一切操作）
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(720, 420)
        self._version = version
        self._total_size = total_size
        self._threads = threads
        self._paused = False
        self._done = False
        self._state = "running"
        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # 标题行：版本 + 线程数
        head = QHBoxLayout()
        self.title_label = QLabel(f"正在下载 {self._version}".strip())
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        head.addWidget(self.title_label)
        head.addStretch()
        self.threads_label = QLabel("等待开始…")
        self.threads_label.setStyleSheet("color: #888;")
        head.addWidget(self.threads_label)
        root.addLayout(head)

        # 总进度条
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)          # 千分位精度，进度更平滑
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(18)
        root.addWidget(self.bar)

        # 统计行：百分比 / 已下载 / 速率 / 剩余
        stats = QHBoxLayout()
        self.percent_label = QLabel("0.0%")
        self.percent_label.setStyleSheet("font-weight: bold;")
        self.size_label = QLabel("— / —")
        self.speed_label = QLabel("—")
        self.eta_label = QLabel("剩余 —")
        for w in (self.percent_label, self.size_label, self.speed_label, self.eta_label):
            stats.addWidget(w)
            stats.addSpacing(12)
        stats.addStretch()
        root.addLayout(stats)

        # 逐线程明细表
        self.table = QTableWidget(0, len(HEADERS), self)
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_THREAD, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_RANGE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_PROGRESS, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_DONE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_STATE, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)

        # 底部按钮
        buttons = QHBoxLayout()
        self.hint_label = QLabel("下载在后台进行，可以继续使用主程序")
        self.hint_label.setStyleSheet("color: #888;")
        buttons.addWidget(self.hint_label)
        buttons.addStretch()

        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setObjectName("update_dl_pause_btn")
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        buttons.addWidget(self.pause_btn)

        self.background_btn = QPushButton("后台运行")
        self.background_btn.setObjectName("update_dl_background_btn")
        self.background_btn.setToolTip(
            "收起本面板，下载继续（可从「配置 → 下载进度…」或状态栏查看进度）")
        self.background_btn.clicked.connect(self._on_background)
        buttons.addWidget(self.background_btn)

        self.cancel_btn = QPushButton("取消并清理")
        self.cancel_btn.setObjectName("update_dl_cancel_btn")
        self.cancel_btn.setToolTip("停止下载，并删除已下载的临时文件")
        self.cancel_btn.clicked.connect(self._on_cancel)
        buttons.addWidget(self.cancel_btn)

        self.discard_btn = QPushButton("清理缓存")
        self.discard_btn.setObjectName("update_dl_discard_btn")
        self.discard_btn.setToolTip(
            "删掉已下载的临时文件（.part 与进度记录）。下载进行中不可用；\n"
            "取消后想继续下载就别点它——保留临时文件才能断点续传")
        self.discard_btn.setEnabled(False)
        self.discard_btn.clicked.connect(self._on_discard)
        buttons.addWidget(self.discard_btn)
        root.addLayout(buttons)

        # **不写死宽度**：本项目字号可配置（7 套主题 × 任意字号），写死必裁字。
        # 详见 AGENTS.md 陷阱 63。
        fit_btn_width(self.pause_btn, self.background_btn,
                      self.cancel_btn, self.discard_btn)

    # ── 外部驱动 ────────────────────────────────────────────────────
    def update_progress(self, progress) -> None:
        """接收 `downloader.DownloadProgress` 快照并刷新界面。

        ``progress.state`` 是**界面文案的唯一驱动**（R11）：不拿 ``percent`` 猜
        「暂停 / 重来 / 完成」，否则「服务端不认 Range、从 0 重写」这类
        进度回退的路径会被显成“卡住”或“已完成”。
        """
        if progress is None:
            return
        state = str(getattr(progress, "state", "running") or "running")
        self._state = state
        pct = float(getattr(progress, "percent", 0.0) or 0.0)
        self.bar.setValue(int(round(pct * 10)))
        self.percent_label.setText(f"{pct:.1f}%")

        total = int(getattr(progress, "total_size", 0) or 0) or self._total_size
        done = int(getattr(progress, "completed_bytes", 0) or 0)
        self._total_size = total
        self.size_label.setText(f"{dl.format_bytes(done)} / {dl.format_bytes(total)}")

        speed = float(getattr(progress, "speed_bps", 0.0) or 0.0)
        self.speed_label.setText(dl.format_speed(speed))
        self.eta_label.setText(f"剩余 {_format_eta(max(0, total - done), speed)}")

        self._apply_state_text(state, done, total)

        threads = int(getattr(progress, "threads", 0) or 0)
        segments = tuple(getattr(progress, "segments", ()) or ())
        active = sum(1 for s in segments if not s.complete)
        if segments:
            self.threads_label.setText(
                f"{threads} 线程并发 · 进行中 {active} / {len(segments)}")
        elif threads:
            self.threads_label.setText(f"{threads} 线程（单流模式）")
        self._threads = threads

        self._refresh_table(segments, state)
        self._update_discard_state()

    def _apply_state_text(self, state: str, done: int, total: int) -> None:
        """标题 / 百分比 / 提示行随 ``state`` 变化（单一实现）。"""
        base = f"下载 {self._version}".strip()
        if state == "paused":
            self.title_label.setText(f"已暂停：{base}")
            self.hint_label.setText(
                "已暂停（已完成的部分会保留，继续时从断点接着下）")
            self.pause_btn.setText("继续")
            self._paused = True
        elif state == "restart":
            self.title_label.setText(f"{base}（从头重新开始）")
            self.hint_label.setText(
                "服务端不支持断点续传，已从头重新下载（进度回到 0）")
        elif state == "completed":
            self.title_label.setText(f"下载完成：{base}")
        elif state == "cancelled":
            self.title_label.setText(f"已取消：{base}")
        else:
            if self._paused:
                self._paused = False
                self.pause_btn.setText("暂停")
            self.title_label.setText(f"正在下载 {self._version}".strip())

    def _refresh_table(self, segments, state: str = "running") -> None:
        """重建/更新逐线程表（段数变化时重建行，否则只改单元格）。"""
        if not segments:
            return
        if self.table.rowCount() != len(segments):
            self.table.setRowCount(len(segments))
            for row in range(len(segments)):
                for col in range(len(HEADERS)):
                    item = QTableWidgetItem("")
                    if col in (COL_THREAD, COL_DONE, COL_STATE):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(row, col, item)
        pending_text = _STATE_TEXT.get(state, _STATE_TEXT["running"])
        for seg in segments:
            row = seg.index
            if row >= self.table.rowCount():
                continue
            self._cell(row, COL_THREAD, f"#{seg.index + 1}")
            self._cell(row, COL_RANGE, f"{seg.start:,} – {seg.end:,}")
            pct = seg.percent
            filled = int(round(pct / 100.0 * 20))
            bar = "█" * filled + "░" * (20 - filled)
            self._cell(row, COL_PROGRESS, f"{bar} {pct:5.1f}%")
            self._cell(row, COL_DONE, f"{dl.format_bytes(seg.done)}")
            self._cell(row, COL_STATE,
                       "✔ 完成" if seg.complete else pending_text)

    def _cell(self, row: int, col: int, text: str) -> None:
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem(text)
            self.table.setItem(row, col, item)
        elif item.text() != text:
            item.setText(text)

    # ── 状态切换 ────────────────────────────────────────────────────
    def _on_pause_clicked(self) -> None:
        if self._done:
            return
        if self._paused:
            self._paused = False
            self.pause_btn.setText("暂停")
            self.hint_label.setText("已继续下载…")
            self.resume_requested.emit()
        else:
            self._paused = True
            self.pause_btn.setText("继续")
            self.hint_label.setText("已暂停（已完成的部分会保留，继续时从断点接着下）")
            self.pause_requested.emit()

    def _on_cancel(self) -> None:
        if self._done:
            return
        self.cancel_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.hint_label.setText("正在取消并清理临时文件…")
        self.cancel_requested.emit()

    def _on_background(self) -> None:
        self.background_requested.emit()
        self.hide()

    def _on_discard(self) -> None:
        """「清理缓存」——只删临时文件，不动下载状态（下载中禁用）。"""
        if not self._done and not self._paused:
            return
        self.discard_requested.emit()
        self.hint_label.setText("已清理临时文件（下次将重新下载）")
        self._update_discard_state()

    def _update_discard_state(self) -> None:
        """下载进行中禁用清理：删了正在写的 ``.part`` 会直接损坏下载。"""
        self.discard_btn.setEnabled(self._done or self._paused)

    def changeEvent(self, event) -> None:
        """字号/主题变化后**重算按钮下限**。

        ``fit_btn_width`` 只设 ``minimumWidth``，按理布局会按更大的 ``sizeHint`` 放宽；
        但本行左侧还有一条长提示文本，实测 14 号字下布局会把按钮压回旧下限
        （80 < 90）⇒ 当场裁字。在 ``FontChange`` 时重取一次即可。
        """
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and hasattr(self, "pause_btn"):
            fit_btn_width(self.pause_btn, self.background_btn,
                          self.cancel_btn, self.discard_btn)

    def closeEvent(self, event: QCloseEvent) -> None:
        """关窗口 = **后台运行**，不是取消。

        此前点 X 只是 ``hide()``，但没有任何地方能再把它叫出来（用户无法确认
        下载是否还在跑）；现在 X 与「后台运行」同义，并发出 ``background_requested``
        让主窗口把进度接到状态栏 + 菜单项（R8）。真正停止请点「取消并清理」。
        """
        if not self._done:
            self.background_requested.emit()
        event.accept()
        super().closeEvent(event)

    # ── 终态 ────────────────────────────────────────────────────────
    def mark_completed(self) -> None:
        self._done = True
        self.bar.setValue(1000)
        self.percent_label.setText("100.0%")
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.background_btn.setEnabled(False)
        self.hint_label.setText("下载完成")
        self.threads_label.setText("已完成")
        self._update_discard_state()

    def mark_failed(self, message: str) -> None:
        self._done = True
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        # 失败时也不该再「后台运行」：没有在跑的东西可收起来（此前面板会留着
        # 一个仍可点的后台按钮，点完窗口消失、用户不确定到底还下不下）
        self.background_btn.setEnabled(False)
        self.hint_label.setText(f"下载失败：{message}")
        self.threads_label.setText("已停止")
        self._update_discard_state()

    def mark_cancelled(self) -> None:
        self._done = True
        self.bar.setValue(0)
        self.percent_label.setText("已取消")
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.background_btn.setEnabled(False)
        self.hint_label.setText("已取消，临时文件已清理")
        self.threads_label.setText("已取消")
        self._update_discard_state()

    def set_kept_cache_note(self) -> None:
        """取消但临时文件**留着**（``on_cancel="keep"``）时的文案。

        不区分这两种情况会让用户以为磁盘已释放，实际还占着几十 MB。
        """
        self.hint_label.setText("已取消，临时文件已保留（可继续；点「清理缓存」可删除）")
        self._update_discard_state()

    def is_paused(self) -> bool:
        return self._paused

    def is_done(self) -> bool:
        return self._done


__all__ = ["UpdateDownloadDialog", "HEADERS"]
