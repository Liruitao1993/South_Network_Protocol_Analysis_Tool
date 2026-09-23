"""按钮文字被裁回归测试（`gui_utils.fit_btn_width` + 工具栏/筛选栏按钮）。

现场现象（2026-09-23）：TCP 监控「应用层帧」工具栏 4 个按钮（开始记录 / 加载记录 /
打开位置 / 记录目录）**文字显示不全** —— 截图上「记录目录」只显示成「记录目」。
根因：这 4 个按钮被写死 `setFixedWidth(80)`，而 QSS 主题下它们「16px 图标 + 4 个汉字」
的 `sizeHint().width()` 已是 **92**（带菜单下拉箭头的「记录目录」**104**）⇒ **默认字号
就裁字**；本项目字号可配置（`theme_settings`，7 套主题 × 任意字号），12 / 14 号时
需 104 / 116~128。同一根因的第二处：在线监控器「帧类型 / MSDU类型」按钮写死
100 / 120px，默认 10 号字下只要单选「选择确认帧(SACK)」就显示成「选择确认帧(」。

判据（本测试的 oracle）：**布局后的实际宽度 >= 该按钮的 sizeHint 宽度**。
`sizeHint` 是 Qt 按「图标 + 文字 + QSS 内边距 + 菜单箭头」算出的**最小不裁字宽度**，
窄于它必然裁字（QPushButton 不会省略号缩排，只会截断）。
**必须在 `show()` 之后量**：headless 下未 show 的 widget 没有 geometry，`width()`
恒为默认 640，量出来永远是「不裁」（假绿）。

覆盖：
  [1] `fit_btn_width` / `fit_btn_width_for_texts` 纯逻辑：空输入 / None 忽略 / 取最大值 /
      extra / **只设下限不设上限** / 不静默降掉调用方已有的更大下限 / 恢复原文案
  [2] 真机布局：TCP 监控工具栏 4 个按钮在 10 / 12 / 14 字号下均不裁字、等宽，且
      `minimumWidth >= sizeHint`、`maximumWidth` 未被写死（判据与布局余量无关）
  [3] 反例自检：把这 4 个按钮改回 `setFixedWidth(80)`，[2] 的判据必须变红
  [4] 动态文案按钮：在线监控器「帧类型 / MSDU类型」走**真实勾选动作**后不裁字
  [5] 运行中切字号 / 切主题（不重建控件）后仍不裁字
  [6] 静态守卫（AST）：`monitor/tcp_monitor.py` 与 `monitor_widget.py` 内 **QPushButton
      不得被 setFixedWidth / setMaximumWidth / setFixedSize 限制宽度**，并自带正负样例
      自检（不误伤 QLineEdit、不漏多行构造与局部变量名）

运行: python test/test_btn_width_fit.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QMessageBox, QPushButton,
)

# 控制台为 GBK 时收尾行的 “✓” 会抛 UnicodeEncodeError；只放宽 errors（不动 encoding）。
try:
    sys.stdout.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import app_paths  # noqa: E402

# QWidget 默认 maximumWidth（Qt 的 QWIDGETSIZE_MAX）—— PySide6 未从 QtWidgets 导出该常量。
# 用它断言「只设下限、没设上限」，即**没有**把宽度写死。
_QWIDGETSIZE_MAX = 16777215

# 沙箱：数据目录 / 配置文件目录都指向临时目录（必须在 import 被测模块前安装），
# 否则读 tcp_monitor_config.json 会落到开发机真实数据目录。
_SANDBOX = Path(tempfile.mkdtemp(prefix="nw_btnfit_"))
patch.object(app_paths, "data_path", lambda name: _SANDBOX / str(name)).start()
patch.object(app_paths, "app_data_dir", lambda: _SANDBOX).start()

import gui_utils  # noqa: E402
from monitor import tcp_monitor as tm  # noqa: E402
import monitor_widget as mw  # noqa: E402
from theme_settings import ThemeManager  # noqa: E402

PASS = 0
FAIL = 0

# 现场截图中出问题的 4 个按钮：**名称 + 期望文字**（文字是最小宽度判据的一部分，
# 改文案必须同步改这里 —— 否则等宽断言会静默失真）。
_TOOLBAR_BUTTONS = ("开始记录", "加载记录", "打开位置", "记录目录")

# 动态文案按钮：属性名 -> (菜单动作列表属性, 勾选后文案**最长**的那一项)
# 单选最长项就是最坏情况（按钮会显示它的截断形式）。
_DYNAMIC_BUTTONS = {
    "frame_type_btn": ("_frame_type_actions", "选择确认帧(SACK)"),
    "msdu_type_btn": ("_msdu_type_actions", "网络管理消息"),
}


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


def _size_hint_for(btn, text):
    """把 `text` 临时设到按钮上量 sizeHint（量完恢复原文案）。"""
    keep = btn.text()
    try:
        btn.setText(text)
        return btn.sizeHint().width()
    finally:
        btn.setText(keep)


def _toolbar_buttons(w):
    """按文字取出工具栏那 4 个按钮（含局部变量 load_btn，故不能用实例属性）。"""
    found = {}
    for b in w.findChildren(QPushButton):
        if b.text() in _TOOLBAR_BUTTONS and b.text() not in found:
            found[b.text()] = b
    return found


def _layout(w, app, size=(1760, 900)):
    """真正跑一遍布局：headless 下不 show() 就没有 geometry（width() 是默认 640）。"""
    w.resize(*size)
    w.show()
    app.processEvents()
    return w


def _clipped(btn):
    """按钮是否裁字：布局后实际宽度 < sizeHint（sizeHint = 不裁字所需最小宽度）。"""
    return btn.width() < btn.sizeHint().width()


# ── [1] 纯逻辑：fit_btn_width / fit_btn_width_for_texts ───────────────
def test_helper_logic(app):
    section("[1] fit_btn_width / fit_btn_width_for_texts 纯逻辑")

    check("空输入返回 0", gui_utils.fit_btn_width() == 0)
    check("全是 None 返回 0，且不抛", gui_utils.fit_btn_width(None, None) == 0)

    a = QPushButton("短")
    b = QPushButton("很长的一个按钮名字")
    c = QPushButton("中等名字")
    for btn in (a, b, c):
        gui_utils.set_btn(btn, "secondary")

    widest = max(x.sizeHint().width() for x in (a, b, c))
    got = gui_utils.fit_btn_width(a, None, b, c)
    check("返回值为最宽者的 sizeHint", got == widest, f"{got} vs {widest}")
    check("统一等宽（传入的 None 不影响）",
          a.minimumWidth() == b.minimumWidth() == c.minimumWidth() == widest,
          f"{a.minimumWidth()}/{b.minimumWidth()}/{c.minimumWidth()}")

    # 关键区别：只设下限，**不设上限** —— 字号变大时 sizeHint 增长仍能被布局满足。
    check("未设上限（maxWidth 仍是 QWIDGETSIZE_MAX，即没有写死宽度）",
          max(a.maximumWidth(), b.maximumWidth(), c.maximumWidth()) == _QWIDGETSIZE_MAX,
          str([a.maximumWidth(), b.maximumWidth(), c.maximumWidth()]))

    d = QPushButton("加留白")
    gui_utils.set_btn(d, "secondary")
    raw = d.sizeHint().width()
    gui_utils.fit_btn_width(d, extra=17)
    check("extra 生效", d.minimumWidth() == raw + 17, f"{d.minimumWidth()} vs {raw + 17}")
    check("负 extra 被夹到 0（返回值不会低于 sizeHint）",
          gui_utils.fit_btn_width(d, extra=-5) == raw, f"{raw}")

    # 调用方刻意设过更大的下限时不得被静默降掉（main_gui 的「Star」按钮就是这种用法）
    e = QPushButton("短")
    gui_utils.set_btn(e, "secondary")
    e.setMinimumWidth(500)
    gui_utils.fit_btn_width(e)
    check("不静默降掉调用方已有的更大下限", e.minimumWidth() == 500, str(e.minimumWidth()))

    # 动态文案：按候选**全集**取宽，且不改变当前文案
    dyn = QPushButton("全部")
    gui_utils.set_btn(dyn, "secondary")
    candidates = ["全部", "无", "选择确认帧(", "9项"]
    before = dyn.text()
    need_each = {t: _size_hint_for(dyn, t) for t in candidates}
    got_dyn = gui_utils.fit_btn_width_for_texts(dyn, candidates)
    check("返回候选全集的最宽值", got_dyn == max(need_each.values()),
          f"{got_dyn} vs {max(need_each.values())}  {need_each}")
    check("每个候选文案都被下限覆盖（与当前文案无关）",
          all(dyn.minimumWidth() >= w_ for w_ in need_each.values()),
          f"minW={dyn.minimumWidth()} 需 {need_each}")
    check("不改变当前文案", dyn.text() == before, dyn.text())
    check("空候选回落为按当前文案取宽",
          gui_utils.fit_btn_width_for_texts(dyn, []) == dyn.sizeHint().width(),
          f"{dyn.minimumWidth()} vs {dyn.sizeHint().width()}")

    for btn in (a, b, c, d, e, dyn):
        btn.deleteLater()
    app.processEvents()


# ── [2] 真机布局：不裁字 + 等宽 + 不变量 ──────────────────────────────
def test_toolbar_fits(app):
    section("[2] TCP 监控工具栏：10 / 12 / 14 字号下 4 个按钮均不裁字")
    for size in (10, 12, 14):
        ThemeManager.apply(app, "default", "Microsoft YaHei", size)
        w = tm.TCPMonitorWidget()
        _layout(w, app)
        btns = _toolbar_buttons(w)
        check(f"{size} 号字：4 个按钮都在（文案未漂移）",
              sorted(btns) == sorted(_TOOLBAR_BUTTONS), str(sorted(btns)))
        if sorted(btns) != sorted(_TOOLBAR_BUTTONS):
            w.deleteLater()
            continue
        for text in _TOOLBAR_BUTTONS:
            btn = btns[text]
            check(f"{size} 号字：「{text}」不裁字",
                  not _clipped(btn),
                  f"实际 {btn.width()}px，不裁字需 ≥{btn.sizeHint().width()}px")
        widths = {btns[t].width() for t in _TOOLBAR_BUTTONS}
        check(f"{size} 号字：4 个按钮等宽", len(widths) == 1, str(sorted(widths)))
        # 与「布局有没有余量」无关的不变量：下限不低于各自 sizeHint，上限没被写死
        floors = {t: (btns[t].minimumWidth(), btns[t].sizeHint().width())
                  for t in _TOOLBAR_BUTTONS}
        check(f"{size} 号字：下限 >= 各自 sizeHint（不依赖布局余量）",
              all(m >= s for m, s in floors.values()), str(floors))
        check(f"{size} 号字：上限未被写死",
              all(btns[t].maximumWidth() == _QWIDGETSIZE_MAX for t in _TOOLBAR_BUTTONS),
              str({t: btns[t].maximumWidth() for t in _TOOLBAR_BUTTONS}))
        w.deleteLater()
        app.processEvents()


# ── [3] 反例自检：退回到写死 80px，判据必须变红 ────────────────────────
def test_reverse_check(app):
    section("[3] 反例自检：改回 setFixedWidth(80) 后判据必须变红")
    ThemeManager.apply(app, "default", "Microsoft YaHei", 10)
    w = tm.TCPMonitorWidget()
    _layout(w, app)
    btns = _toolbar_buttons(w)
    check("反例自检前置：4 个按钮找齐", len(btns) == 4, str(sorted(btns)))
    for btn in btns.values():                     # 模拟修复前
        btn.setFixedWidth(80)
    _layout(w, app, size=(1759, 900))             # 换尺寸强制重排
    clipped = [t for t in _TOOLBAR_BUTTONS if t in btns and _clipped(btns[t])]
    check("写死 80px → 4 个按钮**全部**被判为裁字（判据有效，不是恒真）",
          sorted(clipped) == sorted(_TOOLBAR_BUTTONS), str(clipped))
    if btns:
        sample = btns[_TOOLBAR_BUTTONS[0]]
        print(f"    （实测：写死 80px 时「{sample.text()}」实际 {sample.width()}px，"
              f"需要 {sample.sizeHint().width()}px）")
    w.deleteLater()
    app.processEvents()


# ── [4] 动态文案按钮：在线监控器（走真实勾选动作）─────────────────────
def test_dynamic_text_buttons(app):
    section("[4] 动态文案按钮：在线监控器「帧类型 / MSDU类型」")
    for size in (10, 12):
        ThemeManager.apply(app, "default", "Microsoft YaHei", size)
        w = mw.RealtimeMonitorWidget()
        _layout(w, app, size=(1500, 900))
        for attr, (actions_attr, longest) in _DYNAMIC_BUTTONS.items():
            btn = getattr(w, attr, None)
            actions = getattr(w, actions_attr, None)
            if btn is None or not actions:
                check(f"{size} 号字：{attr} 与菜单动作齐备", False,
                      f"btn={btn is not None} actions={len(actions or [])}")
                continue
            for action in actions:                # 只勾最长项 = 最坏情况
                action.setChecked(action.text() == longest)
            app.processEvents()
            check(f"{size} 号字：{attr} 单选「{longest}」后不裁字",
                  not _clipped(btn),
                  f"文案={btn.text()!r} 实际 {btn.width()}px，需 ≥{btn.sizeHint().width()}px")
            check(f"{size} 号字：{attr} 下限按候选全集取（与当前勾选无关）",
                  btn.minimumWidth() >= btn.sizeHint().width(),
                  f"minW={btn.minimumWidth()} 最长候选需 {btn.sizeHint().width()}")
            check(f"{size} 号字：{attr} 上限未被写死",
                  btn.maximumWidth() == _QWIDGETSIZE_MAX, str(btn.maximumWidth()))
        w.deleteLater()
        app.processEvents()


# ── [5] 运行中切字号 / 切主题（不重建控件）────────────────────────────
def test_runtime_theme_switch(app):
    section("[5] 运行中切字号 / 切主题（不重建控件）后仍不裁字")
    ThemeManager.apply(app, "default", "Microsoft YaHei", 10)
    w = tm.TCPMonitorWidget()
    _layout(w, app)
    btns = _toolbar_buttons(w)

    def clipped_now():
        return [t for t in _TOOLBAR_BUTTONS if t in btns and _clipped(btns[t])]

    for size in (12, 14, 9):
        ThemeManager.apply(app, "default", "Microsoft YaHei", size)
        app.processEvents()
        check(f"运行中切到 {size} 号字后不裁字", not clipped_now(), str(clipped_now()))
    for theme in ("dark", "glass"):
        ThemeManager.apply(app, theme, "Microsoft YaHei", 14)
        app.processEvents()
        check(f"运行中切主题 {theme}（14 号字）后不裁字", not clipped_now(), str(clipped_now()))

    ThemeManager.apply(app, "default", "Microsoft YaHei", 10)
    w.deleteLater()
    app.processEvents()


# ── [6] 静态守卫（AST）：QPushButton 不得被限制宽度 ───────────────────
_WIDTH_CAP_METHODS = ("setFixedWidth", "setMaximumWidth", "setFixedSize")

# 自检样例：源码 / 期望命中数 / 说明。**必须同时有正例与负例** ——
# 之前的正则版守卫在这三条上分别「漏多行构造」「漏非 *_btn 变量名」「误伤 QLineEdit」。
_GUARD_SAMPLES = (
    ('b = QPushButton("x")\nb.setFixedWidth(80)\n',
     1, "命中：局部变量名不带 _btn 也要抓"),
    ('self.x = QPushButton(\n    "很长的文案")\nself.x.setFixedWidth(80)\n',
     1, "命中：多行构造也要抓"),
    ('self.x = QPushButton("x")\nself.y = QLineEdit()\nself.y.setFixedWidth(120)\n',
     0, "不误伤：QLineEdit 的固定宽度是正常用法"),
    ('self.x = QPushButton("x")\nself.x.setMinimumWidth(80)\n',
     0, "不误报：minimumWidth 正是正确写法"),
    ('self.x = QPushButton("x")\nself.x.setMaximumWidth(80)\n',
     1, "命中：setMaximumWidth 同样会裁字（真正裁字的就是上限）"),
)


def _dotted(node):
    """把表达式还原成点号串（self.x / QtWidgets.QPushButton）；不能还原则 None。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _is_pushbutton_call(node):
    return (isinstance(node, ast.Call)
            and _dotted(node.func) in ("QPushButton", "QtWidgets.QPushButton"))


def find_capped_buttons(source: str):
    """AST 找出「接收者确实是 QPushButton」却被限制宽度的调用。

    返回 [(行号, 接收者, 方法, 尺寸实参)]。

    为什么不用正则：正则会要求构造与 setter 同行闭合（**漏多行构造**），或靠变量名
    `*_btn` 判断（局部变量叫 btn / load_button 就漏），而 `[\\s\\S]{0,400}?` 的尾巴还会把
    400 字符内任意 `setFixedWidth` 算到前面那个按钮头上（**误伤 QLineEdit 的正常用法**）。
    AST 认的是「这个接收者被赋值为 QPushButton(...)」，多行构造与任意变量名都覆盖。
    """
    tree = ast.parse(source)
    btn_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_pushbutton_call(node.value):
            for target in node.targets:
                name = _dotted(target)
                if name:
                    btn_names.add(name)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in _WIDTH_CAP_METHODS):
            continue
        recv = _dotted(func.value)
        if recv in btn_names or _is_pushbutton_call(func.value):
            args = ",".join(str(getattr(a, "value", "?")) for a in node.args)
            offenders.append((node.lineno, recv, func.attr, args))
    return offenders


def test_static_guard():
    section("[6] 静态守卫（AST）：QPushButton 不得被限制宽度")
    for code, want, why in _GUARD_SAMPLES:
        got = len(find_capped_buttons(code))
        check(f"守卫自检 -- {why}", got == want, f"命中 {got}，期望 {want}")

    for rel in ("monitor/tcp_monitor.py", "monitor_widget.py"):
        src = Path(rel).read_text(encoding="utf-8")
        offenders = find_capped_buttons(src)
        check(f"{rel} 内无被限制宽度的 QPushButton", not offenders, str(offenders))

    src = Path("monitor/tcp_monitor.py").read_text(encoding="utf-8")
    check("TCP 工具栏改为统一走 fit_btn_width",
          "fit_btn_width(self.csv_record_btn" in src)
    check("fit_btn_width 已导入（不是运行时 NameError）",
          re.search(r"from gui_utils import [^\n]*\bfit_btn_width\b", src) is not None)

    mw_src = Path("monitor_widget.py").read_text(encoding="utf-8")
    check("动态文案按钮走 fit_btn_width_for_texts",
          "fit_btn_width_for_texts(" in mw_src)
    check("取宽候选与运行时文案共用同一截断函数（防两处漂移）",
          mw_src.count("_short_label(") >= 4 and "_BTN_TEXT_MAX" in mw_src,
          f"_short_label 出现 {mw_src.count('_short_label(')} 次")


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    test_helper_logic(app)
    test_toolbar_fits(app)
    test_reverse_check(app)
    test_dynamic_text_buttons(app)
    test_runtime_theme_switch(app)
    test_static_guard()
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
