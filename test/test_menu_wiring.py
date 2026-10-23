"""主菜单接线守卫：每个菜单项 trigger() 后必须真的调用到对应方法。

**真实回归（本测试由此而来）**：`配置→模型API管理(&M)...` 的
`.triggered.connect(self._show_llm_api_manager)` 在提交 `e1dd85e`
（2026-08-21，一个协议11 解析功能提交）被误删 —— 菜单项从此**点了没反应**，
而 `_show_llm_api_manager` 因为「零引用」几乎被
`09-15-gui-dead-code-cleanup` 当死代码删掉（复核时才发现）。

**为什么用行为断言而不是 `QObject.receivers()`**：PySide6 的 `receivers()`
只接受 C++ 字符串签名（`"2triggered()"`），传 Signal 对象直接抛 TypeError（实测）。
本测试把目标方法整体打成记录器再 `action.trigger()`，断言记录器被调用 ——
「connect 被删」必然变红，而不是「不抛异常」那种假绿。

**为什么经 `findChildren(QMenu)` 拿菜单**：实测 `[a.menu() for a in menubar.actions()]`
取到的 QMenu 包装对象会**当场失效**（`shiboken6.isValid() == False`，而 C++ 对象其实
还活着，重新取又有效），后续 `menu.actions()` / `action.trigger()` 会抛
`RuntimeError: Internal C++ object ... already deleted`。改为持有
`menubar.findChildren(QMenu)` 的强引用即可稳定。

运行: QT_QPA_PLATFORM=offscreen python -u test/test_menu_wiring.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

# 构造 MainWindow 之前必须屏蔽模态框（否则 offscreen 下永久阻塞）
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

# 本测试会构造主窗口并触发「恢复默认窗口布局」；沙箱避免写进开发机真实 config.json
_config_sandbox.install()

import main_gui  # noqa: E402

# 菜单项文本 → 它必须调用到的 MainWindow 方法名
EXPECTED = {
    "配置文件路径(&P)...": "_show_config_dialog",
    "主题与字体(&T)...": "_show_theme_settings_dialog",
    "系统集成设置(&S)...": "_show_system_settings_dialog",
    "模型API管理(&M)...": "_show_llm_api_manager",  # ← 曾因 connect 被误删而失效
    "更新设置(&U)...": "_show_update_settings_dialog",
    "下载进度(&D)...": "_show_download_panel",
    "恢复默认窗口布局(&W)": "_reset_window_layout",
    "检查更新(&C)": "_check_update_manual",
    "问题反馈(&F)...": "_show_feedback_dialog",
    "提交问题到 GitHub(&G)...": "_show_github_issue_dialog",
    "生成诊断包(&D)...": "_export_diagnostics",
    "关于(&A)": "_show_about_dialog",
}

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


def leaf_actions(menubar):
    """菜单栏下全部叶子 action：{显示文本: QAction}（跳过分隔符与子菜单父项）。

    必须持有 `findChildren(QMenu)` 返回的强引用再迭代（见模块 docstring）。
    """
    found = {}
    menus = menubar.findChildren(QMenu)
    for menu in menus:
        for act in menu.actions():
            if act.isSeparator() or act.menu() is not None:
                continue
            found[act.text()] = act
    return found


def no_duplicate_methods():
    """用 ast 校验 main_gui.MainWindow 内无重名方法（与死代码清理任务同一口径）"""
    import ast
    import collections
    import pathlib

    src = pathlib.Path(main_gui.__file__).read_text(encoding="utf-8", errors="replace")
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            names = [
                n.name
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            return not {k: v for k, v in collections.Counter(names).items() if v > 1}
    return False


def main():
    print("=" * 64)
    print("主菜单接线守卫（09-15-gui-dead-code-cleanup 复核时发现的回归）")
    print("=" * 64)

    app = QApplication.instance() or QApplication([])

    # 类级打桩：`_setup_menu_bar` 里的 `self._show_xxx` 在构造时解析成绑定方法，
    # 所以必须在构造 MainWindow **之前**替换类属性（事后 setattr 实例无效）
    calls = []
    patchers = []
    for method in sorted(set(EXPECTED.values())):

        def make(m=method):
            def _rec(*a, **k):
                calls.append(m)

            return _rec

        patchers.append(patch.object(main_gui.MainWindow, method, make()))

    for p in patchers:
        p.start()
    try:
        win = main_gui.MainWindow()
    finally:
        # 连接在构造时已绑定到记录器，恢复类属性不影响本测试
        for p in patchers:
            p.stop()
    app.processEvents()

    section("[1] 菜单项集合与契约一致（新增菜单项必须同时加入 EXPECTED）")
    found = leaf_actions(win.menuBar())
    missing = sorted(set(EXPECTED) - set(found))
    extra = sorted(set(found) - set(EXPECTED))
    check("EXPECTED 里每个菜单项都真实存在", not missing, f"缺失={missing}")
    check(
        "没有未被断言的菜单项（新增菜单项要加进 EXPECTED）",
        not extra,
        f"未覆盖={extra}",
    )

    section("[2] 每个菜单项 trigger() 后确实调用到对应方法（接线存在）")
    for label, method in EXPECTED.items():
        act = found.get(label)
        if act is None:
            check(f"{label} → {method}", False, "菜单项不存在")
            continue
        before = len(calls)
        act.trigger()
        fired = calls[before:]
        check(
            f"{label} → {method}",
            fired == [method],
            f"触发后调用={fired or '（无 → 该菜单项点了没反应）'}",
        )

    section("[3] 反例自检：未接线的 action.trigger() 不应产生任何调用")
    probe = QMenu()
    orphan = probe.addAction("孤儿项")
    before = len(calls)
    orphan.trigger()
    check(
        "未接线的 action 触发后无调用（证明本测试的判据有效）",
        len(calls) == before,
        f"calls={calls[before:]}",
    )

    section("[4] 死代码清理的 AST 不变量")
    check("MainWindow 无重名方法定义", no_duplicate_methods())

    win.close()
    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        # 不用 ✓：Windows 控制台默认 GBK，打印它会 UnicodeEncodeError 把进程带崩
        # （测试全绿却以 exit=1 结束，看起来像真失败）
        print(f"全部通过（{PASS} 项）")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
