"""「关于」对话框的 GitHub Star 按钮（1.23.43）。

覆盖点：
  1. 地址单一来源 —— `main_gui.AUTHOR_GITHUB_URL` 是全仓唯一一份 URL 字面量
  2. 对话框结构 —— 按钮存在（objectName）、图标非空、文案含 Star、提示行存在
  3. 与「检查更新」「确定」在**同一个按钮行**（不是被塞到别处）
  4. 点击行为 —— 调用 `QDesktopServices.openUrl` 且 URL 与常量一致
  5. 兜底 —— `openUrl` 返回 False 时弹窗给出可复制地址；地址为空时不跳转只提示
  6. `_show_about_dialog()` 仍然 exec 由 `_build_about_dialog()` 构造的对话框
  7. 反例自检 —— 未接线的按钮点击不产生任何 openUrl 调用（证明判据有效）

运行: QT_QPA_PLATFORM=offscreen python -u test/test_about_github_star.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib  # noqa: E402
import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

# GBK 控制台容错：按钮/提示文案含 ⭐ 等非 GBK 字符，直接 print 会 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
)

# 构造 MainWindow 之前必须屏蔽模态框（否则 offscreen 下永久阻塞）
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

# 本测试会构造主窗口；沙箱避免写进开发机真实 config.json
_config_sandbox.install()

import main_gui  # noqa: E402

EXPECTED_URL = "https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool"

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


def row_layout_of(dialog, target):
    """返回包含 target 控件的那个子布局（用于断言「同排」）。找不到返回 None。"""
    root = dialog.layout()
    if root is None:
        return None
    for i in range(root.count()):
        sub = root.itemAt(i).layout()
        if sub is None:
            continue
        for j in range(sub.count()):
            if sub.itemAt(j).widget() is target:
                return sub
    return None


def find_button(dialog, text_fragment):
    for btn in dialog.findChildren(QPushButton):
        if text_fragment in btn.text():
            return btn
    return None


def main():
    print("=" * 64)
    print("「关于」对话框 GitHub Star 按钮（1.23.43）")
    print("=" * 64)

    app = QApplication.instance() or QApplication([])

    section("[1] 地址单一来源")
    check(
        "AUTHOR_GITHUB_URL 常量值正确",
        main_gui.AUTHOR_GITHUB_URL == EXPECTED_URL,
        main_gui.AUTHOR_GITHUB_URL,
    )
    src = pathlib.Path(main_gui.__file__).read_text(encoding="utf-8", errors="replace")
    check(
        "main_gui.py 内 URL 字面量只有一处（没有第二份硬编码）",
        src.count("github.com/Liruitao1993") == 1,
        f"出现 {src.count('github.com/Liruitao1993')} 次",
    )

    win = main_gui.MainWindow()
    app.processEvents()

    section("[2] 对话框结构")
    dlg = win._build_about_dialog()
    check("构造返回 QDialog", isinstance(dlg, QDialog), type(dlg).__name__)
    check("标题为「关于」", dlg.windowTitle() == "关于", dlg.windowTitle())

    star_btn = dlg.findChild(QPushButton, "about_star_btn")
    check("star 按钮存在（objectName=about_star_btn）", star_btn is not None)
    if star_btn is None:
        print("\n按钮缺失，后续断言无法进行")
        sys.stdout.flush()
        os._exit(1)
    check("按钮文案含 GitHub 与 Star", "GitHub" in star_btn.text() and "Star" in star_btn.text(), star_btn.text())
    check("按钮带图标（star.svg 存在）", not star_btn.icon().isNull())
    check(
        "按钮 tooltip 指向作者仓库",
        EXPECTED_URL in star_btn.toolTip(),
        star_btn.toolTip(),
    )

    tips = [
        w.text()
        for w in dlg.findChildren(QLabel)
        if "Star" in w.text()
    ]
    check("存在提示用户点 Star 的文案行", bool(tips), tips[:1])
    check(
        "提示行同时提到 GitHub",
        any("GitHub" in t for t in tips),
        tips[:1],
    )
    check("提示行不是按钮文案本身（是独立 QLabel）", all(t != star_btn.text() for t in tips))

    section("[3] 与「检查更新」「确定」同排")
    check_btn = find_button(dlg, "检查更新")
    ok_btn = find_button(dlg, "确定")
    check("「检查更新」按钮仍在", check_btn is not None)
    check("「确定」按钮仍在", ok_btn is not None)
    star_row = row_layout_of(dlg, star_btn)
    check("star 按钮所在行可定位", star_row is not None)
    if check_btn is not None and ok_btn is not None and star_row is not None:
        check(
            "三个按钮同属一行",
            row_layout_of(dlg, check_btn) is star_row
            and row_layout_of(dlg, ok_btn) is star_row,
        )
    check(
        "star 按钮排在「检查更新」之前",
        star_row is not None
        and check_btn is not None
        and star_row.indexOf(star_btn) < star_row.indexOf(check_btn),
    )

    section("[4] 点击跳转")
    opened = []
    orig_open = main_gui.QDesktopServices.openUrl
    try:
        main_gui.QDesktopServices.openUrl = lambda u: opened.append(u.toString()) or True
        star_btn.click()
        check(
            "点击后打开作者仓库",
            opened == [EXPECTED_URL],
            f"opened={opened}",
        )
        # 反例自检：未接线的按钮点击不应产生调用（证明上面的判据不是恒真）
        orphan = QPushButton("孤儿按钮")
        before = len(opened)
        orphan.click()
        check("未接线按钮点击无调用（判据有效）", len(opened) == before)

        section("[5] 兜底")
        main_gui.QDesktopServices.openUrl = lambda u: False
        shown = []
        with patch.object(
            QMessageBox,
            "information",
            lambda *a, **k: shown.append(a[2] if len(a) > 2 else "") or 0,
        ):
            win._open_author_github()
        check(
            "openUrl 失败时弹窗给出可复制地址",
            bool(shown) and EXPECTED_URL in shown[-1],
            shown[-1] if shown else "（未弹窗）",
        )

        with patch.object(main_gui, "AUTHOR_GITHUB_URL", ""):
            opened.clear()
            shown.clear()
            with patch.object(
                QMessageBox,
                "information",
                lambda *a, **k: shown.append(a[2] if len(a) > 2 else "") or 0,
            ):
                win._open_author_github()
            check("地址为空时不跳转", not opened, f"opened={opened}")
            check("地址为空时给出提示", bool(shown), shown[-1] if shown else "（未弹窗）")
    finally:
        main_gui.QDesktopServices.openUrl = orig_open

    section("[6] _show_about_dialog 仍 exec 构造出的对话框")
    execs = []

    class _StubDialog:
        def exec(self):
            execs.append(True)
            return 0

    with patch.object(
        main_gui.MainWindow, "_build_about_dialog", lambda self: _StubDialog()
    ):
        win._show_about_dialog()
    check("_show_about_dialog 调用 exec 一次", execs == [True], f"execs={execs}")

    dlg.close()
    win.close()
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
