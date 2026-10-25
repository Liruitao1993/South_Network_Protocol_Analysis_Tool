"""「关于」对话框的版本号与更新记录（1.24.1）。

用户报障：**关于里面版本号有误，并且日期随时变**。根因是对话框写死 `版本 2.0`，
更新记录只有伪造的 v2.0 / v1.0 两条，日期还用 `date.today()` 现取。

覆盖点：
  1. 版本行单一来源 —— `APP_VERSION` + `CHANGELOG` 顶部条目日期（纯函数）
  2. 日期静态 —— 源码守卫：`_build_about_dialog` / 三个辅助函数内**不得**出现
     `date.today()` / `datetime.now()`；同进程两次构造文案逐字相同
  3. 更新记录来自 `CHANGELOG` —— 当前版本 + 历史版本，不含伪造的旧文案与 markdown 记号
  4. 纯函数可配置 —— 要点条数 / 摘要字数 / 历史版本条数上限、空 `CHANGELOG` 兜底、
     版本与 `CHANGELOG` 不一致时日期回落 `BUILD_DATE`
  5. 登记守卫 —— 本测试必须在 `release_check.CORE_TESTS` 里
  6. 负例自检 —— 旧实现（`版本 2.0` + 当天日期）会被同一套判据判红

**对话框本身为什么在子进程里跑**（`--child-dialog`）：本机 offscreen（PySide6 6.12 +
无字体目录）下，只要构造出这个对话框，Qt 在**进程收尾阶段**就偶发崩在退出码上
（`release_check` 里既有的一批 GUI 测试同样如此）。断言需要的文案在崩之前已经
`flush` 到 stdout，所以父进程只认子进程 stdout 里的 JSON、**不认它的退出码** ——
这样本测试在任何机器上都能稳定给出「通过/失败」，而不是被环境噪声带红。

运行: python test/test_about_version.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import textwrap  # noqa: E402
from html import unescape as _html_unescape  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

# GBK 控制台容错：断言详情里含 →/★ 等非 GBK 字符时 print 不崩
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import main_gui  # noqa: E402
import release_check  # noqa: E402

PASS = 0
FAIL = 0

#: 「关于」里绝不允许出现的旧伪造文案（1.24.0 及以前写死的占位内容）
FAKE_NOTES = (
    "优化界面布局，提高信息密度",
    "统一表格字体为7pt",
    "初始版本发布",
)

#: 生成「关于」文案的四个函数：不允许自己取系统时间（否则日期又会「随时变」）
TIME_SENSITIVE_FUNCS = (
    "_build_about_dialog",
    "about_release_date",
    "about_version_line",
    "build_about_changelog_html",
)

FORBIDDEN_TIME_CALLS = ("date.today", "datetime.now", "datetime.today", "time.time")

CHILD_FLAG = "--child-dialog"
CHILD_SENTINEL = "ABOUT_DIALOG_JSON="

#: Qt.WindowType 的位值（父进程不 import PySide6，故写字面量 + 注释）
CLOSE_BUTTON_HINT = 0x08000000  # WindowCloseButtonHint
CONTEXT_HELP_HINT = 0x00010000  # WindowContextHelpButtonHint
#: 1.24.1 及以前「关于」对话框的真实标志值（0x3003）：有 WS_SYSMENU 但 ✕ 点不动
LEGACY_FLAGS = 0x00003003


def has_close_button(window_flags: int) -> bool:
    """窗口标志位是否能真正启用标题栏 ✕（有 CloseButtonHint 且无 ContextHelpHint）。"""
    return bool(int(window_flags) & CLOSE_BUTTON_HINT) and not (
        int(window_flags) & CONTEXT_HELP_HINT
    )


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


def _code_without_docstring(func) -> str:
    """函数体源码（**去掉 docstring**）。

    源码守卫要看的是「代码里有没有取系统时间」，而 docstring 里为了说明禁令
    本来就会提到 `date.today()` —— 直接把整段源码拿来匹配会自我误报。
    """
    src = textwrap.dedent(inspect.getsource(func))
    node = ast.parse(src).body[0]
    lines = src.splitlines()
    first = node.body[0] if node.body else None
    is_docstring = (
        isinstance(first, ast.Expr)
        and isinstance(getattr(first, "value", None), ast.Constant)
        and isinstance(first.value.value, str)
    )
    if is_docstring:
        lines = lines[: first.lineno - 1] + lines[first.end_lineno :]
    return "\n".join(lines)


def snapshot_texts(dialog):
    """取出任意「关于」类对话框的 (版本行, 更新记录纯文本)。"""
    from PySide6.QtWidgets import QLabel, QTextEdit

    label = dialog.findChild(QLabel, "about_version_label")
    box = dialog.findChild(QTextEdit, "about_changelog_text")
    return (
        label.text() if label is not None else None,
        box.toPlainText() if box is not None else None,
    )


class _StubWindowMixin:
    """替身父窗口的属性/回调：只提供 `_build_about_dialog` 用到的那几样东西。

    真实 `MainWindow` 会拉起全局热键等后台对象，与本测试无关；真实接线由
    `test/test_about_github_star.py` 的 MainWindow 路径覆盖。
    """

    _font_family = "Microsoft YaHei"
    _font_size = 10

    def _ui_font(self, delta=0, bold=False, family=None):
        from PySide6.QtGui import QFont

        font = QFont(family or self._font_family, self._font_size + delta)
        font.setBold(bold)
        return font

    def _open_author_github(self):  # 对话框里只做信号接线，不点击
        pass

    def _check_update_manual(self):
        pass


def _child_main() -> int:
    """子进程：真造对话框，把两处文案（以及旧实现负例）以 JSON 打到 stdout。"""
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QLabel,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    class _StubWindow(_StubWindowMixin, QWidget):
        pass

    if QApplication.instance() is None:
        QApplication([])
    parent = _StubWindow()
    dialog = main_gui.MainWindow._build_about_dialog(parent)
    version_line, notes_text = snapshot_texts(dialog)
    dialog2 = main_gui.MainWindow._build_about_dialog(parent)
    version_line2, notes_text2 = snapshot_texts(dialog2)

    # 负例：1.24.0 及以前的写死文案（版本 2.0 + 当天日期）
    legacy = QDialog(parent)
    legacy_layout = QVBoxLayout(legacy)
    legacy_label = QLabel("版本 2.0")
    legacy_label.setObjectName("about_version_label")
    legacy_box = QTextEdit()
    legacy_box.setObjectName("about_changelog_text")
    legacy_box.setHtml(
        "<b>v2.0 (2026-01-01)</b><ul><li>优化界面布局，提高信息密度</li></ul>"
    )
    legacy_layout.addWidget(legacy_label)
    legacy_layout.addWidget(legacy_box)
    legacy_version, legacy_notes = snapshot_texts(legacy)

    payload = {
        "version_line": version_line,
        "notes_text": notes_text,
        "version_line_2": version_line2,
        "notes_text_2": notes_text2,
        "legacy_version_line": legacy_version,
        "legacy_notes_text": legacy_notes,
        # 标题栏关闭按钮：只有窗口标志位里真有 WindowCloseButtonHint，Windows 才让 ✕
        # 真正生效（缺了它 ✕ 会画出来但点了没反应 —— 1.24.2 修的坑）
        "window_flags": int(dialog.windowFlags()),
    }
    print(CHILD_SENTINEL + json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()
    # 直接退出、不走 Qt 收尾：本机 offscreen 下收尾阶段偶发崩溃（见文件头说明）
    os._exit(0)
    return 0  # pragma: no cover


def run_dialog_child():
    """父进程：跑子进程取对话框文案；只认 stdout 哨兵，不认子进程退出码。"""
    script = str(Path(__file__).resolve())
    try:
        proc = subprocess.run(
            [sys.executable, script, CHILD_FLAG],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return None, "子进程超时"
    for line in (proc.stdout or "").splitlines():
        if line.startswith(CHILD_SENTINEL):
            try:
                return json.loads(line[len(CHILD_SENTINEL) :]), ""
            except ValueError as exc:
                return None, f"JSON 解析失败：{exc}"
    return None, f"未拿到哨兵（exit={proc.returncode}）"


def about_matches_expectation(version_line, notes_text) -> bool:
    """「关于」文案是否与单一来源一致（负例自检也要走这里）。"""
    if not version_line or notes_text is None:
        return False
    expected_date = main_gui.CHANGELOG[0][1]
    return (
        version_line == main_gui.about_version_line()
        and version_line.startswith(f"版本 {main_gui.APP_VERSION}")
        and expected_date in version_line
        and f"v{main_gui.APP_VERSION}" in notes_text
        and expected_date in notes_text
    )


def main():
    print("=" * 64)
    print("「关于」对话框的版本号与更新记录（1.24.1）")
    print("=" * 64)

    section("[1] 版本行单一来源（纯函数）")
    top_version, top_date = main_gui.CHANGELOG[0][0], main_gui.CHANGELOG[0][1]
    check(
        "CHANGELOG 顶部版本与 APP_VERSION 一致（不一致说明发版流程已漂移）",
        top_version == main_gui.APP_VERSION,
        f"CHANGELOG={top_version} APP_VERSION={main_gui.APP_VERSION}",
    )
    check(
        "about_release_date() 取 CHANGELOG 顶部条目日期",
        main_gui.about_release_date() == top_date,
        f"{main_gui.about_release_date()} vs {top_date}",
    )
    check(
        "发布日期是合法 YYYY-MM-DD 静态串",
        bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", main_gui.about_release_date())),
        main_gui.about_release_date(),
    )
    check(
        "about_version_line() == 「版本 <APP_VERSION>（<日期> 发布）」",
        main_gui.about_version_line() == f"版本 {main_gui.APP_VERSION}（{top_date} 发布）",
        main_gui.about_version_line(),
    )
    check(
        "版本行含 APP_VERSION（不再是写死的 2.0）",
        main_gui.APP_VERSION in main_gui.about_version_line(),
        main_gui.about_version_line(),
    )
    check(
        "版本行不等于旧文案「版本 2.0」",
        main_gui.about_version_line() != "版本 2.0",
        main_gui.about_version_line(),
    )

    section("[2] 日期静态（源码守卫，防回退成 date.today()）")
    for func_name in TIME_SENSITIVE_FUNCS:
        func = getattr(main_gui, func_name, None)
        if func is None and func_name == "_build_about_dialog":
            func = main_gui.MainWindow._build_about_dialog
        check(f"{func_name} 可定位", func is not None)
        if func is None:
            continue
        src = _code_without_docstring(func)
        hits = [token for token in FORBIDDEN_TIME_CALLS if token in src]
        check(f"{func_name} 内不取系统时间", not hits, f"命中 {hits}" if hits else "")

    dialog_src = inspect.getsource(main_gui.MainWindow._build_about_dialog)
    check(
        "版本行直接读 about_version_line()（不是字面量）",
        "QLabel(about_version_line())" in dialog_src,
    )
    check(
        "更新记录直接读 build_about_changelog_html()（不是字面量）",
        "build_about_changelog_html()" in dialog_src,
    )
    check(
        "_build_about_dialog 内不再 import date / datetime",
        "from datetime import" not in dialog_src and "import datetime" not in dialog_src,
    )
    for tag, func in (
        ("「关于」_build_about_dialog", main_gui.MainWindow._build_about_dialog),
        (
            "系统集成设置 _show_system_settings_dialog",
            main_gui.MainWindow._show_system_settings_dialog,
        ),
    ):
        check(
            f"{tag} 显式加回 WindowCloseButtonHint（1.24.2 坑：~flags 会把它清掉）",
            "WindowCloseButtonHint" in _code_without_docstring(func),
        )

    section("[3] 纯函数可配置上限")
    bullets = [it for it in main_gui.CHANGELOG[0][2] if str(it).strip()]
    default_html = main_gui.build_about_changelog_html()
    check(
        "默认列出的要点条数 = min(本版条数, ABOUT_NOTE_ITEMS)",
        default_html.count("<li>") == min(len(bullets), main_gui.ABOUT_NOTE_ITEMS),
        f"{default_html.count('<li>')} 条（本版 {len(bullets)} 条）",
    )
    check(
        "note_items=2 时只列 2 条要点",
        main_gui.build_about_changelog_html(note_items=2).count("<li>") == 2,
    )
    if len(bullets) > 1:
        check(
            "要点被截断时注明「本版共 N 条」",
            "本版共" in main_gui.build_about_changelog_html(note_items=1),
        )
    short = main_gui.build_about_changelog_html(note_items=len(bullets), note_chars=20)
    # 量的是「渲染出来的文字」长度：HTML 里 & < " 会被转义成 &amp; 之类，先还原
    li_texts = [_html_unescape(t) for t in re.findall(r"<li>(.*?)</li>", short, re.S)]
    check(
        f"摘要长度 ≤ note_chars+1（实测最长 {max((len(t) for t in li_texts), default=0)}）",
        all(len(t) <= 21 for t in li_texts),
    )
    check(
        "被截断的摘要以省略号结尾",
        all(t.endswith("…") for t in li_texts if len(t) > 20) or not li_texts,
    )
    one_history = main_gui.build_about_changelog_html(history_versions=1)
    second = f"v{main_gui.CHANGELOG[1][0]}（"
    third = f"v{main_gui.CHANGELOG[2][0]}（"
    check(
        "history_versions=1 时只列第 2 个版本",
        second in one_history and third not in one_history,
        f"含 {second!r} / 不含 {third!r}",
    )
    check(
        "history_versions=0 时不出现「历史版本」分节",
        "<b>历史版本</b>" not in main_gui.build_about_changelog_html(history_versions=0),
    )
    with patch.object(main_gui, "CHANGELOG", []):
        check(
            "CHANGELOG 为空时给占位提示（不崩、不留白）",
            "暂无更新记录" in main_gui.build_about_changelog_html(),
        )
        check(
            "CHANGELOG 为空时日期回落 BUILD_DATE",
            main_gui.about_release_date() == main_gui.BUILD_DATE,
            main_gui.about_release_date(),
        )
    with patch.object(main_gui, "CHANGELOG", [("9.9.9", "2020-01-01", ["假条目"])]):
        check(
            "版本与 CHANGELOG 不一致时日期回落 BUILD_DATE（不冒出古老日期）",
            main_gui.about_release_date() == main_gui.BUILD_DATE,
            main_gui.about_release_date(),
        )
        check(
            "不一致时版本行仍用 APP_VERSION",
            main_gui.APP_VERSION in main_gui.about_version_line(),
        )

    section("[4] 实际对话框（子进程，见文件头说明）")
    payload, err = run_dialog_child()
    check("子进程返回了对话框文案", payload is not None, err)
    if payload is None:
        payload = {}
    version_line = payload.get("version_line")
    notes_text = payload.get("notes_text") or ""
    check("版本行控件存在（objectName=about_version_label）", version_line is not None)
    check("更新记录控件存在（objectName=about_changelog_text）", bool(notes_text))
    check(
        "版本行 == about_version_line()",
        version_line == main_gui.about_version_line(),
        version_line,
    )
    check(
        "版本行含 APP_VERSION 与发布日期",
        bool(version_line)
        and main_gui.APP_VERSION in version_line
        and top_date in version_line,
        version_line,
    )
    check("更新记录含 v{APP_VERSION}", f"v{main_gui.APP_VERSION}" in notes_text)
    check("更新记录含发布日期", top_date in notes_text)
    check(
        "更新记录含第 2 个版本的版本号与日期（历史版本行）",
        main_gui.CHANGELOG[1][0] in notes_text and main_gui.CHANGELOG[1][1] in notes_text,
    )
    check("更新记录含「历史版本」分节", "历史版本" in notes_text)
    check("更新记录不含旧伪造文案", not any(t in notes_text for t in FAKE_NOTES))
    check("更新记录不含原始 markdown 记号 **", "**" not in notes_text)
    check("更新记录不含原始 markdown 反引号", "`" not in notes_text)
    check(
        "更新记录长度有界（不是把整份 CHANGELOG 塞进来）",
        len(notes_text) < 4000,
        f"{len(notes_text)} 字",
    )
    check(
        "文案与单一来源一致（about_matches_expectation）",
        about_matches_expectation(version_line, notes_text),
    )
    window_flags = int(payload.get("window_flags") or 0)
    check(
        "窗口标志位能真正启用标题栏 ✕（含 CloseButtonHint）",
        has_close_button(window_flags),
        f"flags=0x{window_flags:08X}",
    )
    check(
        "窗口标志位不含 ContextHelpButtonHint（问号已去掉）",
        not (window_flags & CONTEXT_HELP_HINT),
        f"flags=0x{window_flags:08X}",
    )
    check(
        "两次构造的版本行完全一致（无时间漂移）",
        payload.get("version_line_2") == version_line,
        payload.get("version_line_2"),
    )
    check(
        "两次构造的更新记录完全一致（无时间漂移）",
        payload.get("notes_text_2") == notes_text,
    )

    section("[5] 登记守卫")
    check(
        "test/test_about_version.py 已进 release_check.CORE_TESTS",
        "test/test_about_version.py" in release_check.CORE_TESTS,
    )

    section("[6] 负例自检（旧实现会被同一套判据判红）")
    legacy_version = payload.get("legacy_version_line")
    legacy_notes = payload.get("legacy_notes_text") or ""
    check("旧实现的版本行能取到（判据可作用于任意对话框）", legacy_version == "版本 2.0")
    check(
        "旧实现被判为不一致",
        not about_matches_expectation(legacy_version, legacy_notes),
        f"{legacy_version} / {legacy_notes[:20]!r}",
    )
    check(
        "旧伪造文案出现在旧实现里（证明 FAKE_NOTES 判据有效）",
        any(t in legacy_notes for t in FAKE_NOTES),
    )
    check(
        "旧标志值 0x3003 会被判为「✕ 点不动」（关闭按钮判据负例自检）",
        not has_close_button(LEGACY_FLAGS),
        f"flags=0x{LEGACY_FLAGS:08X}",
    )

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
    if CHILD_FLAG in sys.argv:
        sys.exit(_child_main())
    main()
