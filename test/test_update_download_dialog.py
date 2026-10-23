# -*- coding: utf-8 -*-
"""自动升级下载面板回归（1.23.95）。

用户口径（本文件逐条守卫）：
  1. **不挡操作** —— 面板必须是**非模态**（此前是 WindowModal，下载时整个程序不能动）；
  2. **看得见线程数** —— 顶部显示「N 线程并发」；
  3. **看得见每个子线程的进度** —— 表格逐行显示每个分段的进度与已下载量；
  4. **看得见速率** —— 当前 MB/s + 已下载/总量 + 剩余时间估算；
  5. **能暂停 / 继续** —— 暂停发出信号且按钮变「继续」；
  6. **能取消** —— 取消发出信号，终态提示「临时文件已清理」；
  7. **能后台运行** —— 「后台运行」收起面板（下载继续）。

另覆盖 `downloader` 的暂停/取消/速率/清理缓存纯逻辑（无 Qt 部分）。

运行: QT_QPA_PLATFORM=offscreen python -u test/test_update_download_dialog.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import downloader as dl  # noqa: E402


def _make_progress(total=100, done=45, threads=8, speed=1.5 * 1024 * 1024,
                   state="running", segs=None):
    if segs is None:
        segs = tuple(
            dl.SegmentSnapshot(i, i * 10, i * 10 + 9,
                               done=5 if i < 4 else 10, length=10)
            for i in range(threads)
        )
    return dl.DownloadProgress(
        percent=done * 100.0 / total if total else 0.0,
        completed_bytes=done,
        total_size=total,
        speed_bps=speed,
        threads=threads,
        segments=segs,
        state=state,
    )


# ── 纯逻辑：暂停 / 取消 / 速率 / 清理 ─────────────────────────────

def test_control_pause_resume_cancel():
    c = dl.DownloadControl()
    assert not c.paused and not c.cancelled
    c.pause()
    assert c.paused
    c.resume()
    assert not c.paused
    c.cancel()
    assert c.cancelled
    # 取消必须能穿透「已暂停」，否则线程卡在暂停等待里退不出来
    c2 = dl.DownloadControl()
    c2.pause()
    c2.cancel()
    assert c2.cancelled and not c2.paused
    c.reset()
    assert not c.cancelled and not c.paused


def test_format_speed_and_bytes():
    assert dl.format_speed(1.5 * 1024 * 1024) == "1.50 MB/s"
    assert dl.format_speed(512 * 1024) == "512.00 KB/s"
    assert dl.format_speed(0) == "—"
    assert dl.format_speed(-1) == "—"
    assert dl.format_bytes(104854861).startswith("100.0 MB")
    assert dl.format_bytes(0) == "0 B"


def test_speed_meter():
    m = dl._SpeedMeter()
    assert m.update(0, now=100.0) == 0.0
    # 1 秒下了 1 MB ⇒ 约 1 MB/s
    speed = m.update(1024 * 1024, now=101.0)
    assert 900 * 1024 < speed < 1100 * 1024, speed


def test_cleanup_partial_removes_cache():
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "x.exe"
        part = dest.with_name(dest.name + dl.PART_SUFFIX)
        prog = dest.with_name(dest.name + dl.PROGRESS_SUFFIX)
        part.write_bytes(b"x" * 100)
        prog.write_text("{}", encoding="utf-8")
        assert dl.partial_size(dest) == 100
        assert dl.cleanup_partial(dest) is True
        assert not part.exists() and not prog.exists()
        assert dl.partial_size(dest) == 0
        # 没有缓存时返回 False（不报错）
        assert dl.cleanup_partial(dest) is False


def test_progress_snapshot_has_per_segment_detail():
    p = _make_progress()
    assert p.threads == 8
    assert len(p.segments) == 8
    assert all(0 <= s.percent <= 100 for s in p.segments)
    assert p.segments[0].percent == 50.0
    assert p.segments[7].complete


# ── GUI：面板 ────────────────────────────────────────────────────

def test_dialog_is_non_modal():
    """核心诉求：下载面板不能挡住主程序操作。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import UpdateDownloadDialog

    _app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="1.23.95")
    try:
        assert dlg.windowModality() == Qt.WindowModality.NonModal, \
            "下载面板必须是非模态（否则下载时整个程序不能操作）"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_shows_threads_speed_and_table():
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import (COL_DONE, COL_PROGRESS, COL_RANGE,
                                        COL_STATE, COL_THREAD, HEADERS,
                                        UpdateDownloadDialog)

    _app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="1.23.95")
    try:
        assert HEADERS == ("线程", "区间（字节）", "进度", "已下载", "状态")
        dlg.update_progress(_make_progress())

        # 线程数可见
        assert "8 线程并发" in dlg.threads_label.text(), dlg.threads_label.text()
        # 速率可见
        assert "MB/s" in dlg.speed_label.text(), dlg.speed_label.text()
        # 总量 / 已下载可见
        assert "/" in dlg.size_label.text()
        # 百分比
        assert "45.0%" in dlg.percent_label.text(), dlg.percent_label.text()
        # 逐线程表格：行数 = 段数
        assert dlg.table.rowCount() == 8
        assert dlg.table.item(0, COL_THREAD).text() == "#1"
        assert "–" in dlg.table.item(0, COL_RANGE).text()
        assert "%" in dlg.table.item(0, COL_PROGRESS).text()
        assert dlg.table.item(0, COL_DONE).text() != ""
        # 完成态与下载中要能区分
        assert "完成" in dlg.table.item(7, COL_STATE).text()
        assert "下载中" in dlg.table.item(0, COL_STATE).text()
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_pause_toggles_and_signals():
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import UpdateDownloadDialog

    _app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="x")
    events = []
    dlg.pause_requested.connect(lambda: events.append("pause"))
    dlg.resume_requested.connect(lambda: events.append("resume"))
    try:
        dlg.update_progress(_make_progress())
        dlg.pause_btn.click()
        assert events == ["pause"]
        assert dlg.is_paused()
        assert dlg.pause_btn.text() == "继续", "暂停后按钮应变「继续」"
        dlg.pause_btn.click()
        assert events == ["pause", "resume"]
        assert not dlg.is_paused()
        assert dlg.pause_btn.text() == "暂停"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_cancel_signal_and_terminal_state():
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import UpdateDownloadDialog

    _app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="x")
    events = []
    dlg.cancel_requested.connect(lambda: events.append("cancel"))
    try:
        dlg.update_progress(_make_progress())
        dlg.cancel_btn.click()
        assert events == ["cancel"]
        dlg.mark_cancelled()
        assert dlg.is_done()
        assert "已取消" in dlg.hint_label.text()
        assert "已清理" in dlg.hint_label.text(), "取消后要告诉用户缓存已清理"
        assert not dlg.pause_btn.isEnabled()
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_background_hides_but_keeps_running():
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import UpdateDownloadDialog

    _app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="x")
    events = []
    dlg.background_requested.connect(lambda: events.append("bg"))
    try:
        dlg.update_progress(_make_progress())
        dlg.background_btn.click()
        assert events == ["bg"]
        assert not dlg.isVisible(), "「后台运行」应收起面板"
        assert not dlg.is_done(), "收起面板不等于结束下载"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_marks_completed():
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import UpdateDownloadDialog

    _app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="x")
    try:
        dlg.update_progress(_make_progress())
        dlg.mark_completed()
        assert dlg.is_done()
        assert dlg.bar.value() == 1000
        assert "完成" in dlg.hint_label.text()
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_state_text_follows_progress_state():
    """标题 / 行状态由 `progress.state` 驱动（R11）。

    不靠 percent 猜：服务端不认 Range 时进度会从 80% 回到 0%，旧实现会把
    这种「重新开始」显成「卡住」或干脆什么都不变。
    """
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import COL_STATE, UpdateDownloadDialog

    _app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="1.23.96")
    try:
        dlg.update_progress(_make_progress(state="running"))
        assert "正在下载" in dlg.title_label.text(), dlg.title_label.text()
        assert dlg.table.item(0, COL_STATE).text() == "⏳ 下载中"

        dlg.update_progress(_make_progress(state="paused"))
        assert "已暂停" in dlg.title_label.text(), dlg.title_label.text()
        assert dlg.pause_btn.text() == "继续"
        assert dlg.table.item(0, COL_STATE).text() == "⏸ 已暂停"
        assert dlg.discard_btn.isEnabled(), "暂停态应当允许清理缓存"

        dlg.update_progress(_make_progress(done=0, state="restart"))
        assert "重新开始" in dlg.title_label.text(), dlg.title_label.text()
        assert "不支持断点续传" in dlg.hint_label.text()
        assert dlg.table.item(0, COL_STATE).text() == "↻ 重新开始"

        dlg.update_progress(_make_progress(done=100, state="completed"))
        assert "下载完成" in dlg.title_label.text()
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_buttons_not_clipped_at_large_fonts():
    """按钮宽度必须 >= sizeHint（字号可配置，写死必裁字，R10）。

    **必须 show() 后再量**：未 show 的 widget 没有 geometry，量出来永远是假绿。
    """
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import UpdateDownloadDialog

    app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="1.23.96")
    original = app.font()
    try:
        for size in (10, 14, 16, 24):
            f = app.font()
            f.setPointSize(size)
            app.setFont(f)
            dlg.show()
            app.processEvents()
            for name in ("pause_btn", "background_btn", "cancel_btn", "discard_btn"):
                btn = getattr(dlg, name)
                btn.ensurePolished()
                assert btn.width() >= btn.sizeHint().width(), (
                    f"{size} 号字下 {name} 文字被裁："
                    f"{btn.width()} < {btn.sizeHint().width()}")
                assert btn.maximumWidth() > 10000, \
                    f"{name} 不得写死宽度（maximumWidth 被限制）"
    finally:
        app.setFont(original)
        dlg.close()
        dlg.deleteLater()


def test_dialog_close_means_background():
    """点 X = 后台运行（发 background_requested），不是默默隐藏（R8）。"""
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import UpdateDownloadDialog

    _app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="1.23.96")
    seen = []
    dlg.background_requested.connect(lambda: seen.append(1))
    try:
        dlg.show()
        dlg.close()
        assert seen, "关窗口必须发 background_requested"

        seen.clear()
        dlg.mark_completed()
        dlg.show()
        dlg.close()
        assert not seen, "已结束时不应再发后台信号"
    finally:
        dlg.deleteLater()


def test_dialog_discard_signal_and_failed_state():
    """「清理缓存」只在可清理时可用；失败态也要禁用「后台运行」。"""
    from PySide6.QtWidgets import QApplication

    from update_download_dialog import UpdateDownloadDialog

    _app = QApplication.instance() or QApplication([])
    dlg = UpdateDownloadDialog(None, version="1.23.96")
    seen = []
    dlg.discard_requested.connect(lambda: seen.append(1))
    try:
        assert not dlg.discard_btn.isEnabled(), "下载进行中不得清理缓存"

        dlg.update_progress(_make_progress())
        assert not dlg.discard_btn.isEnabled()

        dlg.mark_cancelled()
        assert dlg.discard_btn.isEnabled(), "取消后应可回收磁盘"
        dlg.discard_btn.click()
        assert seen, "点「清理缓存」必须发 discard_requested"

        dlg2 = UpdateDownloadDialog(None, version="1.23.96")
        try:
            dlg2.mark_failed("HTTP 404")
            assert not dlg2.background_btn.isEnabled(), \
                "失败态不得再提供「后台运行」"
        finally:
            dlg2.deleteLater()
    finally:
        dlg.deleteLater()


# ── 接线守卫 ─────────────────────────────────

def test_main_gui_uses_non_modal_panel():
    """主程序必须用新面板（而不是模态 QProgressDialog），且接上暂停/取消。"""
    src = (Path(__file__).resolve().parent.parent / "main_gui.py").read_text(
        encoding="utf-8")
    assert "update_download_dialog" in src, "未接入新下载面板"
    assert "UpdateDownloadDialog" in src
    # 暂停 / 继续 / 取消 三条接线都要在
    assert "pause_requested.connect(thread.pause)" in src
    assert "resume_requested.connect(thread.resume)" in src
    assert "cancel_requested.connect(thread.cancel)" in src
    # 不能再残留模态进度框（只查**实际使用**：实例化/导入；
    # CHANGELOG 里提到旧实现的名字不算 —— 那是文档，不是代码）
    assert "QProgressDialog(" not in src, "旧的模态进度框应已移除（仍有实例化）"
    assert "import QProgressDialog" not in src, "不应再导入 QProgressDialog"


def test_worker_supports_pause_cancel():
    """下载线程必须提供 pause / resume / cancel 并持有 control。"""
    import main_gui

    w = main_gui._UpdateDownloadWorker("https://x/a.exe", Path(tempfile.gettempdir()) / "t.exe", "")
    assert hasattr(w.control, "pause") and hasattr(w.control, "cancel")
    w.pause()
    assert w.control.paused
    w.resume()
    assert not w.control.paused
    w.cancel()
    assert w.control.cancelled


def test_panel_in_hiddenimports():
    meta = Path(__file__).resolve().parent.parent / "pyinstaller_meta.py"
    text = meta.read_text(encoding="utf-8")
    assert "update_download_dialog" in text


def test_main_gui_hands_panel_the_new_entry_points():
    """主程序要把面板的 `background_requested` / `discard_requested` 接上（R8/R12）。"""
    src = (Path(__file__).resolve().parent.parent / "main_gui.py").read_text(
        encoding="utf-8")
    assert "background_requested.connect" in src, "「后台运行」/关窗口未接线"
    assert "discard_requested.connect" in src, "「清理缓存」未接线"
    assert "def _show_download_panel" in src
    assert "下载进度(&D)" in src, "配置菜单缺少把面板叫回来的入口"


def test_main_gui_no_duplicate_download_thread():
    """重入守卫：已有下载在跑时不再起第二个线程（会抢同一个 .part）。"""
    src = (Path(__file__).resolve().parent.parent / "main_gui.py").read_text(
        encoding="utf-8")
    assert 'running = getattr(self, "_download_thread", None)' in src
    assert "已有下载任务在进行中" in src


def test_worker_waits_with_event_not_polling():
    """暂停后用事件阻塞等 resume/cancel，不是 sleep(0.1) 轮询（R2）。"""
    src = (Path(__file__).resolve().parent.parent / "main_gui.py").read_text(
        encoding="utf-8")
    assert "self.control.wait_resumed()" in src
    assert "_time.sleep(0.1)" not in src, "不应回退成轮询等待"
    # 退出时保留分片（否则关一次程序白下几百 MB）
    assert 'qt.on_cancel = "keep"' in src
    assert "on_cancel=self.on_cancel" in src, "worker 必须把 on_cancel 传给下载器"


def test_worker_has_no_dead_progress_signal():
    """删掉没人连接的 `progress` 信号（R14：别留看似有用的死通道）。"""
    src = (Path(__file__).resolve().parent.parent / "main_gui.py").read_text(
        encoding="utf-8")
    head = src.split("class _UpdateDownloadWorker", 1)[1][:2000]
    assert "progress = Signal(int)" not in head, "已无人连接，应删除避免误导"
    assert "progress_cb=lambda p: self.progress.emit" not in src


def test_statusbar_message_cleared_after_download():
    """下载结束后必须撤掉状态栏进度（否则一直挂着 100% 旧值）。"""
    src = (Path(__file__).resolve().parent.parent / "main_gui.py").read_text(
        encoding="utf-8")
    seg = src.split("def _on_download_done(", 1)[1][:600]
    assert "clearMessage()" in seg


class _FakeHost:
    """最小宿主：假装是 MainWindow，只提供被调用到的那几个能力。

    这样可以直接跑 `MainWindow._start_download` / `_show_download_panel` /
    `_on_download_done` 的**真实实现**（不是复制一份逻辑），又不用建整个主窗口
    （建一次 ~2s，且退出期有本机已知的 fastfix 风险）。
    """

    def __init__(self):
        from PySide6.QtWidgets import QMainWindow

        self._win = QMainWindow()
        self._download_ctx = {"sentinel": 1}
        self._download_thread = None
        self._download_dlg = None
        self._update_settings = {}

    def statusBar(self):
        return self._win.statusBar()


class _FakeRunningThread:
    def __init__(self):
        self.cancel_calls = 0

    def isRunning(self):
        return True

    def cancel(self):
        self.cancel_calls += 1


def test_start_download_refuses_second_task():
    """R3/AC3：已有下载在跑 → 不起第二个线程、不改写 ctx，并把旧面板叫到前面。"""
    import main_gui

    host = _FakeHost()
    busy = _FakeRunningThread()
    host._download_thread = busy
    shown = []
    host._show_download_panel = lambda *a: shown.append(1)

    main_gui.MainWindow._start_download(host, {"url": "https://x/a.exe", "version": "9.9.9"})

    assert host._download_thread is busy, "不得把运行中的线程换掉"
    assert host._download_ctx == {"sentinel": 1}, "不得覆盖 _download_ctx"
    assert shown, "应把已有下载面板唤到前台"
    assert "已有下载任务" in host.statusBar().currentMessage()


def test_download_panel_reopen_from_menu():
    """R8/AC8：面板关掉后能从菜单入口重新显示（下载仍在跑）。"""
    from PySide6.QtWidgets import QApplication

    import main_gui
    from update_download_dialog import UpdateDownloadDialog

    _app = QApplication.instance() or QApplication([])
    host = _FakeHost()
    dlg = UpdateDownloadDialog(None, version="1.23.96")
    host._download_dlg = dlg
    host._download_thread = _FakeRunningThread()
    try:
        dlg.show()
        dlg.hide()
        assert not dlg.isVisible()
        main_gui.MainWindow._show_download_panel(host)
        assert dlg.isVisible(), "菜单入口应能重新打开面板"
    finally:
        dlg.close()
        dlg.deleteLater()
        host._win.deleteLater()


def test_download_done_clears_statusbar():
    """R9/AC9：下载结束后状态栏不再挂着进度。"""
    from unittest import mock

    import main_gui

    host = _FakeHost()
    host.statusBar().showMessage("下载更新 100% · 3.0 MB/s · 8 线程")
    assert host.statusBar().currentMessage()

    with mock.patch.object(main_gui.QMessageBox, "warning", return_value=None):
        main_gui.MainWindow._on_download_done(
            host, False, "网络错误", "", "", None, {})

    assert host.statusBar().currentMessage() == "",         f"下载结束后状态栏应清空，实际：{host.statusBar().currentMessage()!r}"
    host._win.deleteLater()


def run_all():
    tests = [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERR   {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)
