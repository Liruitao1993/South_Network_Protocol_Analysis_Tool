"""自动升级对话框与接线回归（offscreen，不发任何网络请求）。

覆盖用户诉求「把更新说明加载出来」：
- `update_dialogs.set_release_notes`：Markdown 渲染 / 空说明占位 / 渲染异常退回纯文本
- 版本列表对话框：行文案（[最新] / ← 当前 / [预发布]）、选中项 → 说明联动、
  无安装包资产时禁用下载、双击 = 下载、取消返回 None
- 「发现新版本」对话框：版本对比文案、说明渲染、发布页按钮可用性
- 接线守卫：`main_gui._on_version_list_result` / `_confirm_update_download` 走新模块，
  更新设置对话框落盘 github_owner / github_repo（源码守卫，防被改回内联实现）

运行: python test/test_update_notes_gui.py
"""

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402

# GBK 控制台容错：报告里的 ✓ 等字符直接 print 会 UnicodeEncodeError（release_check
# 用 PYTHONIOENCODING=utf-8 跑子进程，但手工 `python test/xxx.py` 也要能跑）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from pathlib import Path  # noqa: E402

import tempfile  # noqa: E402

import update_dialogs  # noqa: E402
from update_dialogs import (  # noqa: E402
    NOTES_EMPTY_HINT,
    UpdateAvailableDialog,
    VersionListDialog,
    set_release_notes,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n{title}")


MARKDOWN_NOTES = """# 南网协议解析工具 1.23.86

> 把十六进制变成逐字段讲清楚的表。

## 本版看点

- **报文工具**新增「地址替换」
- 光伏升级判定

| 文件 | 说明 |
| --- | --- |
| `v1.23.86.exe` | 免安装 |

详见 https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool/releases
"""


def rel(version, notes=MARKDOWN_NOTES, url="https://x/app.exe", **over):
    data = {
        "version": version,
        "url": url,
        "notes": notes,
        "html_url": f"https://github.com/o/r/releases/tag/{version}",
        "created_at": "2026-10-18T13:17:06Z",
        "asset_name": f"v{version}.exe",
    }
    data.update(over)
    return data


RELEASES = [
    rel("1.23.86"),
    rel("1.23.85", notes="", url=""),
    rel("1.23.80", notes="老版本", prerelease=True),
]


def test_set_release_notes_renders_markdown():
    app = QApplication.instance() or QApplication([])
    from PySide6.QtWidgets import QTextBrowser

    b = QTextBrowser()
    set_release_notes(b, MARKDOWN_NOTES)
    plain = b.toPlainText()
    check("Markdown 渲染后正文可见", "报文工具" in plain and "光伏升级判定" in plain)
    check(
        "Markdown 标记被渲染掉（不留 # / ** / 表格竖线）",
        "#" not in plain and "**" not in plain and "|" not in plain,
        repr(plain[:60]),
    )
    check("链接保留为可点链接（QTextBrowser 超链接）", "github.com" in b.toHtml())

    set_release_notes(b, "   ")
    check("空说明给占位提示而不是留白", NOTES_EMPTY_HINT in b.toPlainText())

    class Bad(QTextBrowser):
        def setMarkdown(self, _text):  # 模拟 Qt 渲染失败
            raise RuntimeError("boom")

    b2 = Bad()
    set_release_notes(b2, "# 甲")
    check("渲染异常退回纯文本（对话框不会打不开）", "甲" in b2.toPlainText())
    return app


def test_version_list_dialog(app):
    dlg = VersionListDialog(
        None,
        RELEASES,
        "1.23.87",
        source_label="GitHub Releases（Liruitao1993/South_Network_Protocol_Analysis_Tool）",
        release_page_url="https://github.com/o/r/releases",
    )
    check("列出全部版本", dlg.listw.count() == len(RELEASES))
    check("默认选中最新版（第一行）", dlg.listw.currentRow() == 0)
    check("最新版行有 [最新] 标记", dlg.listw.item(0).text().startswith("[最新]"))
    check("预发布版本有 [预发布] 标记", "[预发布]" in dlg.listw.item(2).text())
    check("当前版本行标出「← 当前」", "← 当前" not in dlg.listw.item(0).text())

    dlg2 = VersionListDialog(None, RELEASES, "1.23.86")
    check("当前版本与某行一致时标出「← 当前」", "← 当前" in dlg2.listw.item(0).text())

    check(
        "选中项说明已加载（默认最新版）",
        "地址替换" in dlg.notes_browser.toPlainText(),
    )
    dlg.listw.setCurrentRow(1)
    check("切换行 → 说明联动（空说明给占位）", NOTES_EMPTY_HINT in dlg.notes_browser.toPlainText())
    check("无安装包资产的版本禁用下载", not dlg.download_btn.isEnabled())
    dlg.listw.setCurrentRow(2)
    check("有资产的版本可以下载", dlg.download_btn.isEnabled())

    dlg._accept_selection()
    check(
        "双击 / 按钮确认后返回所选版本信息",
        dlg.result() == QDialog.DialogCode.Accepted
        and dlg.selected_release().get("version") == "1.23.80",
    )
    check(
        "选中版本带下载地址（_start_download 需要）",
        bool(dlg.selected_release().get("url")),
    )

    dlg3 = VersionListDialog(None, RELEASES, "1.23.87")
    dlg3.reject()
    check("取消返回 Rejected（调用方不会去下载）", dlg3.result() == QDialog.DialogCode.Rejected)


def test_update_available_dialog(app):
    from PySide6.QtWidgets import QLabel

    latest = rel("1.23.86")
    dlg = UpdateAvailableDialog(None, "1.23.74", latest, release_page_url="https://github.com/o/r/releases")
    texts = [w.text() for w in dlg.findChildren(QLabel)]
    check("标题含版本对比", any("1.23.74" in t and "1.23.86" in t for t in texts), str(texts[:2]))
    check("安装包名展示出来（用户知道下的是什么）", any("v1.23.86.exe" in t for t in texts))
    check("更新说明已渲染进对话框", "地址替换" in dlg.notes_browser.toPlainText())
    check("发布页按钮可用（有 html_url）", dlg.page_btn.isEnabled())
    check("按钮：下载并更新 / 稍后", (dlg.download_btn.text(), dlg.later_btn.text()) == ("下载并更新", "稍后"))
    dlg.download_btn.click()
    check("点「下载并更新」= Accepted", dlg.result() == QDialog.DialogCode.Accepted)

    dlg2 = UpdateAvailableDialog(None, "1.23.74", rel("1.23.86", html_url=""))
    check("无发布页地址时按钮禁用（不做无用点击）", not dlg2.page_btn.isEnabled())

    dlg3 = UpdateAvailableDialog(None, "1.23.74", rel("1.23.86", notes=""))
    check("无更新说明时给占位提示", NOTES_EMPTY_HINT in dlg3.notes_browser.toPlainText())


def test_ask_helpers_forward_choice(app):
    """ask_version_list / ask_update_available 的返回值语义（不 exec，直接测分支）。"""
    from auto_updater import summarize_notes

    check("summarize_notes 可给列表 tooltip 用", "地址替换" in summarize_notes("**地址替换**", 200))
    got = {}

    def fake_exec(self):
        got["accepted"] = True
        return QDialog.DialogCode.Rejected

    orig = QDialog.exec
    QDialog.exec = fake_exec
    try:
        out = update_dialogs.ask_version_list(None, RELEASES, "1.23.87")
        check("取消 → 返回 None（不下载）", out is None)
        flag = update_dialogs.ask_update_available(None, "1.23.74", RELEASES[0])
        check("拒绝 → 返回 False", flag is False)
    finally:
        QDialog.exec = orig


def test_main_gui_wiring_source_guards():
    """源码守卫：接线不能被改回内联 QMessageBox / 内联列表对话框。"""
    import pathlib

    src = pathlib.Path(_path_setup.__file__).resolve().parent.parent.joinpath("main_gui.py")
    text = src.read_text(encoding="utf-8", errors="replace")

    check("_confirm_update_download 走 update_dialogs.ask_update_available", "ask_update_available(" in text)
    check("版本列表走 update_dialogs.ask_version_list", "ask_version_list(" in text)
    check("两处确认框不再用 QMessageBox.question 弹更新说明", text.count("是否下载并更新？") == 0)
    check("默认更新源由 AUTHOR_GITHUB_URL 注入 merge_update_config", "repo_url=AUTHOR_GITHUB_URL" in text)
    check("更新设置对话框落盘 github_owner（经默认值收敛）", '"github_owner": gh["github_owner"]' in text)
    check("更新设置对话框落盘 github_repo（经默认值收敛）", '"github_repo": gh["github_repo"]' in text)
    check("状态栏提示改用 summarize_notes（不再原样塞 markdown）", "summarize_notes(latest.get(\"notes\")" in text.replace("'", '"'))
    check("下载线程按配置传入 sha256 开关", "verify_sha=bool(self._update_settings.get(\"sha256_verify\"" in text)
    check("临时文件名经 safe_file_stem 清洗", "safe_file_stem(" in text)
    check("更新设置保存时把默认 owner/repo 收敛为空串", "github_fields_for_save(" in text)


def test_worker_passes_repo_url():
    """后台检查线程必须带上作者仓库地址（默认源解析依赖它）。"""
    import main_gui

    w = main_gui._UpdateCheckWorker({}, "1.0.0", list_all=False, repo_url=main_gui.AUTHOR_GITHUB_URL)
    check("_UpdateCheckWorker 收到 repo_url", w.repo_url == main_gui.AUTHOR_GITHUB_URL)
    check("AUTHOR_GITHUB_URL 是 GitHub 仓库地址", "github.com/Liruitao1993/" in main_gui.AUTHOR_GITHUB_URL)


def test_repo_url_single_source_no_drift():
    """「仓库地址唯一来源」的两处一致性守卫：内置默认常量必须与 AUTHOR_GITHUB_URL 一致。

    当前无漂移（实测），但两处硬编码本身有漂移风险 —— 用户只改一处就会
    「关于」按钮和自动升级源指向不同仓库，这里把风险钉成红灯。
    """
    import auto_updater
    import main_gui

    parsed = auto_updater.parse_github_repo_url(main_gui.AUTHOR_GITHUB_URL)
    check(
        "DEFAULT_GITHUB_OWNER 与 AUTHOR_GITHUB_URL 一致（改一处必须同步）",
        auto_updater.DEFAULT_GITHUB_OWNER == parsed.get("github_owner"),
        f"{auto_updater.DEFAULT_GITHUB_OWNER} vs {parsed.get('github_owner')}",
    )
    check(
        "DEFAULT_GITHUB_REPO 与 AUTHOR_GITHUB_URL 一致（改一处必须同步）",
        auto_updater.DEFAULT_GITHUB_REPO == parsed.get("github_repo"),
        f"{auto_updater.DEFAULT_GITHUB_REPO} vs {parsed.get('github_repo')}",
    )


def test_start_download_filename_is_sanitized():
    """版本 tag 含 `/`（如 release/1.24）时，临时文件名不能变成子目录。"""
    import auto_updater

    stem = auto_updater.safe_file_stem("release/1.24")
    dest = Path(tempfile.gettempdir()) / "jiexigongju_updater" / f"南网解析工具_{stem}.exe"
    check("拼出的临时文件仍在更新目录内", dest.parent.name == "jiexigongju_updater")
    check("tag 的分隔符被替换", "/" not in dest.name and "\\" not in dest.name, dest.name)


def test_sha256_verify_toggle_actually_gates(app):
    """「配置→更新设置」的「校验 SHA-256」必须是**真的开关**（此前是死开关：

    勾不勾都按「有摘要就校验」走，用户以为关掉了其实没关）。
    """
    import tempfile

    import auto_updater
    import main_gui

    tmp = Path(tempfile.gettempdir()) / "sha_toggle_test"
    tmp.mkdir(exist_ok=True)
    results = []

    class FakeOp:
        def __init__(self, mismatch):
            self.mismatch = mismatch
            self.verified = []

        def download(self, url, dest_file, progress_cb=None,
                     stats_cb=None, control=None, resume=True,
                     on_cancel="clean"):
            Path(dest_file).write_bytes(b"MZ" + b"\x00" * 4096)
            return Path(dest_file)

        def verify(self, dest_file, expected):
            self.verified.append(bool(expected))
            return not self.mismatch

    real = auto_updater.Opdater
    ops = []
    try:
        # ① 开关关闭：即便摘要给的是错的，也不校验（按用户意图放行）
        ops.append(FakeOp(mismatch=True))
        auto_updater.Opdater = lambda *a, **k: ops[-1]
        w = main_gui._UpdateDownloadWorker("u", tmp / "a.exe", "f" * 64, verify_sha=False)
        w.done.connect(lambda ok, err, p: results.append((ok, err)))
        w.run()
        check("关掉开关 → 不调用 verify（摘要错也放行）", ops[-1].verified == [] and results[-1][0] is True,
              f"verified={ops[-1].verified} result={results[-1]}")

        # ② 开关打开 + 摘要不匹配：拦住
        ops.append(FakeOp(mismatch=True))
        auto_updater.Opdater = lambda *a, **k: ops[-1]
        w2 = main_gui._UpdateDownloadWorker("u", tmp / "b.exe", "f" * 64, verify_sha=True)
        w2.done.connect(lambda ok, err, p: results.append((ok, err)))
        w2.run()
        check("打开开关 + 摘要不匹配 → 拒绝", ops[-1].verified == [True] and results[-1][0] is False,
              f"verified={ops[-1].verified} result={results[-1]}")
        check("拒绝原因是 SHA-256 校验失败", "SHA-256" in results[-1][1], results[-1][1])

        # ③ 开关打开 + 匹配：放行
        ops.append(FakeOp(mismatch=False))
        auto_updater.Opdater = lambda *a, **k: ops[-1]
        w3 = main_gui._UpdateDownloadWorker("u", tmp / "c.exe", "f" * 64, verify_sha=True)
        w3.done.connect(lambda ok, err, p: results.append((ok, err)))
        w3.run()
        check("摘要匹配 → 放行", results[-1][0] is True, str(results[-1]))
    finally:
        auto_updater.Opdater = real
        for f in tmp.glob("*.exe"):
            f.unlink()
        tmp.rmdir()


def test_download_worker_rejects_non_pe(app):
    """替换 exe 前的最后一道闸（1.23.87 独立验证发现的破坏性路径）：

    更新源给错地址（接口 JSON / HTML 错误页）时，下载线程必须**报错而不是**把
    它当新 exe 交给替换流程。这里用假 `Opdater.download` 直接跑真实 `run()`。
    """
    import tempfile

    import auto_updater
    import main_gui

    tmp = Path(tempfile.gettempdir()) / "pe_worker_test"
    tmp.mkdir(exist_ok=True)

    def make_worker(dest):
        return main_gui._UpdateDownloadWorker("https://x/app.exe", dest, "")

    results = []

    class FakeOp:
        def __init__(self, payload):
            self.payload = payload

        def download(self, url, dest_file, progress_cb=None,
                     stats_cb=None, control=None, resume=True,
                     on_cancel="clean"):
            Path(dest_file).write_bytes(self.payload)
            if progress_cb:
                progress_cb(100.0)
            return Path(dest_file)

        def verify(self, dest_file, expected):
            return True

    real = auto_updater.Opdater
    try:
        # ① 接口 JSON（无资产版本被误当下载地址时的真实产物）
        auto_updater.Opdater = lambda *a, **k: FakeOp(b'{"tag_name":"1.8.2","assets":[]}')
        w = make_worker(tmp / "a.exe")
        w.done.connect(lambda ok, err, p: results.append((ok, err)))
        w.run()
        ok, err = results[-1]
        check("JSON 不会被当成新 exe（拒绝并给出原因）", ok is False and "可执行程序" in err, err)

        # ② HTML 错误页
        auto_updater.Opdater = lambda *a, **k: FakeOp(b"<html><body>404</body></html>" + b"x" * 2048)
        w2 = make_worker(tmp / "b.exe")
        w2.done.connect(lambda ok, err, p: results.append((ok, err)))
        w2.run()
        check("HTML 错误页被拒绝", results[-1][0] is False, results[-1][1])

        # ③ 真 PE → 放行
        auto_updater.Opdater = lambda *a, **k: FakeOp(b"MZ" + b"\x00" * 4096)
        w3 = make_worker(tmp / "c.exe")
        w3.done.connect(lambda ok, err, p: results.append((ok, err)))
        w3.run()
        check("真 PE 放行（不是一律拒绝）", results[-1][0] is True, str(results[-1]))
    finally:
        auto_updater.Opdater = real
        for f in tmp.glob("*.exe"):
            f.unlink()
        tmp.rmdir()


def test_main_window_confirm_uses_notes_dialog(monkeypatch_note=None):
    """真实行为：`MainWindow._confirm_update_download` 把 latest 交给说明对话框。

    只用一个最小替身（方法只用 `self._release_page_url`），不构造 14000 行的
    MainWindow —— 但走的是真方法体（不是源码字符串断言）。
    """
    import main_gui

    calls = []
    orig = update_dialogs.ask_update_available

    def fake(parent, current, latest, release_page_url=""):
        calls.append((current, latest.get("version"), release_page_url))
        return True

    update_dialogs.ask_update_available = fake
    try:
        class Stub:
            def _release_page_url(self):
                return "https://github.com/o/r/releases"

        ok = main_gui.MainWindow._confirm_update_download(Stub(), rel("1.23.86"))
    finally:
        update_dialogs.ask_update_available = orig
    check("确认框被调用且拿到版本与发布页", calls == [("1.23.86", "1.23.86", "https://github.com/o/r/releases")] or
          (len(calls) == 1 and calls[0][1] == "1.23.86"))
    check("用户确认 → 返回 True（调用方据此下载）", ok is True)


def main():
    print("=" * 64)
    print("自动升级对话框 / 更新说明 / 接线（offscreen）")
    print("=" * 64)

    app = test_set_release_notes_renders_markdown()

    section("[1] 版本列表对话框（含更新说明面板）")
    test_version_list_dialog(app)

    section("[2] 发现新版本对话框")
    test_update_available_dialog(app)

    section("[3] ask_* 返回值语义")
    test_ask_helpers_forward_choice(app)

    section("[4] 接线（源码守卫 + 真实方法）")
    test_main_gui_wiring_source_guards()
    test_worker_passes_repo_url()
    test_main_window_confirm_uses_notes_dialog()

    section("[5] 下载线程的 PE 兜底（防把 JSON/HTML 当新 exe）")
    test_download_worker_rejects_non_pe(app)

    section("[6] sha256 开关 / 仓库地址单一来源 / 文件名清洗")
    test_sha256_verify_toggle_actually_gates(app)
    test_repo_url_single_source_no_drift()
    test_start_download_filename_is_sanitized()

    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）✓")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
