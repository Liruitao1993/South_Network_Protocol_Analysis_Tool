# -*- coding: utf-8 -*-
"""批量解析工具栏布局回归（offscreen）：两行工具栏不重叠、够宽即一行、瞬态控件不占工具栏。

布局现状（2026-09-30 定稿，两个会话的改动已统一）：

- **第 0 行**（`FlowLayout(stretch=True)`）：从文件加载 / 导入 pcap / 剪贴板 / 开始批量解析 /
  清空 → `addStretch()` 弹性空隙 → 竖线 → 导出 Excel / JSON / 选中 / 时序图 → 帧计数徽章；
- **第 1 行**（`FlowLayout(stretch=True)`）：`预处理:` + 命令框 + 保存/删除/执行/帮助 ｜
  `脚本:` + 脚本框 + 加载/运行/移除/帮助；宽屏下两个下拉框按权重吃满行内剩余宽度；
- **进度条与「取消」移到页面底部状态行**（只在解析中出现，不占工具栏、不挤按钮）。

为什么用 `FlowLayout` 而不是 `QHBoxLayout`：够宽时排一行（省纵向空间），窄窗 / 高DPI 下
自动折行 —— 折行后正好退回多行样子，不会重演早期「单行流式布局把按钮挤到重叠」。
`stretch=True` 则补上"宽屏吃满整行"，两者合起来才能既省行高又不留一大撮靠左的控件。

本测试守住的不变量（**刻意不绑定"哪个按钮在哪一行"**，只守布局性质，避免改排布就假红）：

1. 工具栏恰好两行，且两行都是 FlowLayout（可折行）；
2. `stretch` 真的生效：宽屏下第 1 行的两个下拉框宽于各自 `sizeHint`；
3. **任何宽度都不重叠**（2560→760 逐个扫）—— 这条正是 2026-09-30 抓到的真实缺陷：
   拉伸只改宽度、而 x 仍按原始 `hint` 排，被拉宽的下拉框会盖住右侧按钮（1920/2560 宽下
   9~10 处重叠）。修复靠"被拉宽的项把同行后面的项一起往右推"（`_do_layout` 里的 `shift`）。
   回归这条就能防住同类问题；
4. 宽窗下每行都是一行；窄窗下才折行；
5. 瞬态控件（进度条 / 取消）不在工具栏行里，避免又挤占按钮位置。

坐标系注意：**不能用 `mapTo(win)`** —— 跨 QTabWidget 页面在 offscreen 下会给出离谱坐标
（实测跑出 x=2563 而窗口只有 1920），一律用 `layout.itemAt(i).geometry()`。
行数还要按**容差聚类**：同一行内各项高度不同，`top()` 会差几像素（55/57/61），
直接 `set()` 会误判成多行。

运行：``python test/test_batch_toolbar_layout.py``（offscreen，无需显示器）。
"""

import _path_setup  # noqa: E402,F401

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

_FAILURES = []
_CHECKS = []
_CTX = {"win": None}

#: 同一行内各项 top() 的正常抖动（按行高居中），超过它就认为是换行了
_ROW_TOL = 12
#: 重叠检查的宽度表（含超宽屏与极窄窗）
_WIDTHS = (2560, 2200, 1920, 1800, 1600, 1440, 1366, 1200, 1100, 1000, 900, 800, 760)


def check(name, condition, detail=""):
    _CHECKS.append(name)
    if not condition:
        _FAILURES.append(f"{name} —— {detail}")


def app():
    return QApplication.instance() or QApplication([])


def window():
    if _CTX["win"] is None:
        import main_gui

        win = main_gui.MainWindow()
        win.resize(1920, 950)
        win.show()
        app().processEvents()
        index = next(i for i in range(win.tab_widget.count())
                     if "批量" in win.tab_widget.tabText(i))
        win.tab_widget.setCurrentIndex(index)
        app().processEvents()
        _CTX["win"] = win
    return _CTX["win"]


def toolbar_rows():
    """返回工具栏各行 layout 列表（批量输入分组框内 toolbar_box 的子项）。"""
    win = window()
    group = win.batch_input.parentWidget()
    box = group.layout().itemAt(0).layout()
    rows = []
    for i in range(box.count()):
        item = box.itemAt(i)
        rows.append(item.layout() if item is not None else None)
    return box, rows


def visible_entries(lay):
    """[(控件, 标签, geometry)]，跳过不可见项。"""
    out = []
    for i in range(lay.count()):
        item = lay.itemAt(i)
        widget = item.widget()
        if widget is None or not widget.isVisible():
            continue
        label = getattr(widget, "text", lambda: "")() or widget.__class__.__name__
        out.append((widget, label, item.geometry()))
    return out


def row_count(lay):
    tops = sorted(g.top() for _, _, g in visible_entries(lay))
    rows, last = 0, None
    for top in tops:
        if last is None or top - last > _ROW_TOL:
            rows += 1
        last = top
    return rows


def overlapping_pairs(lay):
    entries = visible_entries(lay)
    bad = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            _, n1, a = entries[i]
            _, n2, b = entries[j]
            if (a.left() < b.right() and b.left() < a.right()
                    and a.top() < b.bottom() and b.top() < a.bottom()):
                bad.append(f"{n1}×{n2}")
    return bad


def all_texts(lay):
    return [label for _, label, _ in visible_entries(lay)]


# ----------------------------------------------------------------------
def test_toolbar_is_two_wrap_safe_rows():
    box, rows = toolbar_rows()
    check("工具栏恰好两行", len(rows) == 2, f"实际 {len(rows)} 行")
    for index, lay in enumerate(rows):
        check(f"第 {index} 行是 FlowLayout（可折行）", lay is not None
              and type(lay).__name__ == "FlowLayout",
              type(lay).__name__ if lay is not None else "None")


def test_rows_hold_expected_groups():
    """只断言"控件确实在这两行里"，不断言坐标/顺序细节。"""
    box, rows = toolbar_rows()
    if len(rows) != 2:
        return
    texts = all_texts(rows[0]) + all_texts(rows[1])
    for must in ("从文件加载", "开始批量解析", "清空", "导出 Excel", "导出 JSON",
                 "导出选中", "时序图", "预处理:", "脚本:", "保存", "删除", "执行",
                 "加载", "运行", "移除", "帮助"):
        check(f"工具栏两行内含「{must}」", must in texts, str(texts))


def test_transient_controls_not_in_toolbar():
    """进度条 / 取消是瞬态控件，应留在底部状态行，不该占工具栏按钮位。"""
    win = window()
    box, rows = toolbar_rows()
    widgets = set()
    for lay in rows:
        for widget, _, _ in visible_entries(lay):
            widgets.add(widget)
    check("进度条不在工具栏行内", win.batch_progress_bar not in widgets)
    check("取消按钮不在工具栏行内", win.batch_cancel_btn not in widgets)
    check("帧计数徽章在工具栏行内", win.batch_frame_count_label in widgets)


def test_stretch_fills_row_when_wide():
    """stretch=True 的用意：宽屏把剩余宽度分给下拉框，不留一大撮靠左控件。"""
    win = window()
    box, rows = toolbar_rows()
    if len(rows) != 2:
        return
    win.resize(2560, 950)
    app().processEvents()
    for combo, name in ((win._pp_cmd_combo, "预处理命令框"),
                        (win._py_script_combo, "脚本下拉框")):
        geom = combo.geometry()
        check(f"宽屏下{name}被拉伸（宽于 sizeHint）",
              geom.width() > combo.sizeHint().width(),
              f"实际 {geom.width()} vs sizeHint {combo.sizeHint().width()}")
        check(f"宽屏下{name}可见", combo.isVisible())


def test_wide_window_single_line_per_row():
    win = window()
    box, rows = toolbar_rows()
    win.resize(2560, 950)
    app().processEvents()
    for index, lay in enumerate(rows):
        check(f"宽窗 2560：第 {index} 行排成一行", row_count(lay) == 1,
              f"{row_count(lay)} 行")


def test_1366_baseline_both_rows_single_line():
    """1366×768 是「省下一行」的判据基准：两行必须各自一行，否则合并等于白做。

    （合并行若把 4 个导出按钮也算进去，单行需 ~1700px，1366 下会折回两行 —— 这正是
    第一版的失败原因，故把导出按钮留在核心行、并用本例钉住。）
    """
    win = window()
    box, rows = toolbar_rows()
    win.resize(1366, 768)
    app().processEvents()
    counts = [row_count(lay) for lay in rows]
    check("1366×768 基准：两行各自排成一行", counts == [1, 1], str(counts))


def test_command_combo_size_hint_is_bounded():
    """可编辑 QComboBox 会把 placeholderText 算进 sizeHint —— 占位符文案就是布局宽度。

    实测：40 字符长示例 → 481px（比最长的一条命令还宽），足以把合并行顶到折行；
    换短示例后 371 → 250px。**不要**改用 setMaximumWidth 压制，那会让宽屏剩余宽度
    全浪费、下拉框再也不跟着变宽（宽屏吃满整行靠的是 FlowLayout 的权重分配）。
    """
    win = window()
    check("预处理命令框 sizeHint ≤ 320（占位符不得过长）",
          win._pp_cmd_combo.sizeHint().width() <= 320,
          f"{win._pp_cmd_combo.sizeHint().width()}px，占位符={win._pp_cmd_combo.placeholderText()!r}")
    check("预处理命令框未被写死宽度上限",
          win._pp_cmd_combo.maximumWidth() >= 10000,
          str(win._pp_cmd_combo.maximumWidth()))


def test_frame_count_badge_hugs_row_right():
    """`addStretch()` 弹性空隙应把帧计数徽章顶到行右端。"""
    win = window()
    box, rows = toolbar_rows()
    win.resize(1920, 950)
    app().processEvents()
    badge = win.batch_frame_count_label
    layout = rows[0]
    check("帧计数徽章在第一行", layout.itemAt(layout.count() - 1).widget() is badge
          or any(e[0] is badge for e in visible_entries(layout)))
    check("帧计数徽章贴行右端（弹性空隙把它顶过去）",
          abs(badge.geometry().right() - layout.geometry().right()) <= 12,
          f"徽章 right={badge.geometry().right()} vs 行 right={layout.geometry().right()}")


def test_narrow_window_wraps_without_overlap():
    win = window()
    box, rows = toolbar_rows()
    win.resize(1100, 950)
    app().processEvents()
    counts = [row_count(lay) for lay in rows]
    check("窄窗 1100：至少有一行折行了（说明折行生效）", max(counts) >= 1, str(counts))
    for index, lay in enumerate(rows):
        check(f"窄窗 1100：第 {index} 行不重叠", not overlapping_pairs(lay),
              str(overlapping_pairs(lay)))


def test_no_overlap_at_any_width():
    """核心回归：被拉宽的控件必须把同行后面的项一起往右推（`shift`），否则会盖住它们。"""
    win = window()
    box, rows = toolbar_rows()
    bad = []
    for width in _WIDTHS:
        win.resize(width, 950)
        app().processEvents()
        for index, lay in enumerate(rows):
            pairs = overlapping_pairs(lay)
            if pairs:
                bad.append(f"{width}px 第{index}行: {pairs}")
    check(f"{len(_WIDTHS)} 个宽度 × 两行均无重叠", not bad, "; ".join(bad))


def test_zero_size_widgets_are_geometry_initialised():
    """回归：FlowLayout 只按 hint 宽排位时，被拉伸的控件 setGeometry 后不能压到邻居。"""
    win = window()
    box, rows = toolbar_rows()
    win.resize(1920, 950)
    app().processEvents()
    for index, lay in enumerate(rows):
        entries = visible_entries(lay)
        for i in range(len(entries) - 1):
            _, n1, a = entries[i]
            _, n2, b = entries[i + 1]
            if abs(a.top() - b.top()) <= _ROW_TOL:
                check(f"1920 第{index}行相邻项不重叠：{n1} → {n2}",
                      a.right() <= b.left() + 1,
                      f"{n1} right={a.right()} vs {n2} left={b.left()}")


def main():
    app()
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    try:
        for test in tests:
            test()
    finally:
        win = _CTX["win"]
        if win is not None:
            win.close()
    print(f"检查项：{len(_CHECKS)} 项，失败 {len(_FAILURES)} 项")
    if _FAILURES:
        for item in _FAILURES:
            print(f"  [FAIL] {item}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
