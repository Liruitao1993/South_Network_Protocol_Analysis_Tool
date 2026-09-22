"""协议下拉框启动被裁剪（显示空白）的回归测试。

背景（1.23.44 修复）：
  顶部「协议选择」组用自定义 `FlowLayout` 自动换行。原 `FlowLayout.sizeHint()` 返回
  `minimumSize()`，而它是「各子项最小尺寸的逐分量最大值」（≈最宽单项 276px），不是单行
  总宽。父布局照此只给 276px → FlowLayout 被迫换行成两行 → 分组框高 75px 而顶栏容器只有
  49px → 第二行的**协议下拉框被裁成一条缝**（实测 geometry (5,44)、visibleRegion 仅
  266x5）→ 启动后该控件显示为空白，点一下（触发重排）才恢复。
  另外 `_reflow_proto_group()` 只重排了内层布局，没有让外层顶栏重排，分组框拿不到最终
  宽度，内层 FlowLayout 也不会被重新调用，子项就停在旧的换行位置。

本测试断言：
  [1] FlowLayout.sizeHint() = 单行总宽（不是最宽单项）；minimumSize() 语义不变
  [2] 窗口够宽时不换行；窗口窄时仍会换行（换行能力不能被修掉）
  [3] 启动 reflow 之后，协议下拉框**完整落在顶栏容器高度内**（不被裁剪）
  [4] 反例自检：把 sizeHint 换回旧实现，[3] 的判据必须变红（证明判据有效）

运行: QT_QPA_PLATFORM=offscreen python -u test/test_flow_layout_proto_group.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QMessageBox,
    QWidget,
)

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

_config_sandbox.install()

import main_gui  # noqa: E402

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


def make_flow(margin=4, spacing=6, sizes=((65, 20), (266, 26))):
    """构造一个 FlowLayout + 若干固定尺寸 QLabel，返回 (宿主控件, 布局)。"""
    host = QWidget()
    lay = main_gui.FlowLayout(host, margin=margin, spacing=spacing)
    for w, h in sizes:
        lb = QLabel("x")
        lb.setFixedSize(w, h)
        lay.addWidget(lb)
    return host, lay


def combo_clipped(win) -> tuple:
    """返回 (是否被顶栏裁剪, 说明)。判据：下拉框必须完整落在顶栏容器高度内。"""
    bar = win.top_bar_widget
    combo = win.protocol_combo
    top_left = combo.mapTo(bar, QPoint(0, 0))
    bottom = top_left.y() + combo.height()
    group_overflow = win.proto_group.height() > bar.height()
    clipped = bottom > bar.height() or group_overflow
    detail = (
        f"combo 在顶栏内 y={top_left.y()}..{bottom}（顶栏高 {bar.height()}）, "
        f"分组框 {win.proto_group.width()}x{win.proto_group.height()}"
    )
    return clipped, detail


def fresh_window(app, size=(1400, 900)):
    """建主窗口并给足宽度：宽度不够时 FlowLayout 换行是**设计行为**，
    本测试要验的是「宽度足够时不该因首轮布局没定宽而误换行并被裁剪」。"""
    win = main_gui.MainWindow()
    win.resize(*size)
    win.show()
    app.processEvents()
    return win


def main():
    print("=" * 64)
    print("协议下拉框启动裁剪回归（1.23.44）")
    print("=" * 64)

    app = QApplication.instance() or QApplication([])

    section("[1] FlowLayout.sizeHint 语义")
    host, lay = make_flow()
    # 必须 show()：sizeHint/minimumSize 会跳过不可见子项（协议组按协议显隐控件的既定行为）
    host.resize(1000, 200)
    host.show()
    app.processEvents()
    hint = lay.sizeHint()
    check(
        "sizeHint().width() = 单行总宽 65+6+266+8 = 345",
        hint.width() == 345,
        f"实际 {hint.width()}",
    )
    check(
        "sizeHint().height() = 单行最高 26+8 = 34",
        hint.height() == 34,
        f"实际 {hint.height()}",
    )
    check(
        "sizeHint 不是「最宽单项」274（旧的错误语义）",
        hint.width() != 274,
        f"实际 {hint.width()}",
    )
    mins = lay.minimumSize()
    check(
        "minimumSize().width() 仍是「最宽单项」274（可被压缩的最小宽度，语义不变）",
        mins.width() == 274,
        f"实际 {mins.width()}",
    )

    section("[2] 换行能力不能被修掉")
    check("窗口够宽（1000）→ 单行高 34", lay.heightForWidth(1000) == 34, f"{lay.heightForWidth(1000)}")
    check(
        "窗口很窄（200）→ 仍换行（高 > 34）",
        lay.heightForWidth(200) > 34,
        f"{lay.heightForWidth(200)}",
    )

    section("[3] 启动 reflow 后协议下拉框不被裁剪")
    win = fresh_window(app)
    win._reflow_proto_group()  # showEvent 里 QTimer.singleShot(0, ...) 走的同一条路径
    clipped, detail = combo_clipped(win)
    check("协议下拉框完整落在顶栏容器内", not clipped, detail)
    check(
        "协议下拉框在分组框第一行（不是被挤到第二行）",
        win.protocol_combo.mapTo(win.proto_group, QPoint(0, 0)).y()
        < win.proto_group.height() // 2,
        f"y={win.protocol_combo.mapTo(win.proto_group, QPoint(0, 0)).y()}",
    )
    check(
        "协议下拉框宽度 = 其设定宽度（未被压窄）",
        win.protocol_combo.width() == win.protocol_combo.maximumWidth(),
        f"{win.protocol_combo.width()}/{win.protocol_combo.maximumWidth()}",
    )
    check(
        "分组框不高于顶栏容器",
        win.proto_group.height() <= win.top_bar_widget.height(),
        f"分组框 {win.proto_group.height()} vs 顶栏 {win.top_bar_widget.height()}",
    )
    win.close()

    section("[4] 反例自检：还原修复前的两处实现，[3] 的判据必须变红")
    # 修复前：sizeHint 返回最宽单项 + reflow 只重排内层（不重排外层顶栏）
    def legacy_reflow(self):
        group = getattr(self, "proto_group", None)
        if group is None:
            return
        lay = group.layout()
        if lay is not None:
            lay.invalidate()
        group.updateGeometry()
        group.adjustSize()

    orig_hint = main_gui.FlowLayout.sizeHint
    orig_reflow = main_gui.MainWindow._reflow_proto_group
    try:
        main_gui.FlowLayout.sizeHint = lambda self: self.minimumSize()
        main_gui.MainWindow._reflow_proto_group = legacy_reflow
        win2 = fresh_window(app)
        win2._reflow_proto_group()
        clipped_old, detail_old = combo_clipped(win2)
        check(
            "修复前实现下协议下拉框确实被裁剪（判据有效，不是恒真）",
            clipped_old,
            detail_old,
        )
        win2.close()
    finally:
        main_gui.FlowLayout.sizeHint = orig_hint
        main_gui.MainWindow._reflow_proto_group = orig_reflow

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
