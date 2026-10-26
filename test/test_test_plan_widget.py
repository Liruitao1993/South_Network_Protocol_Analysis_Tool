# -*- coding: utf-8 -*-
"""「测试方案」页（`test_plan_widget.TestPlanWidget`）的真实冒烟测试。

背景：本仓曾有一份 `test/test_plan_widget.py`，它是**产品模块的过期副本**（2600 行、
零断言、无 `__main__`，跑起来什么都不做），而且因为 `test/` 目录常被插到 `sys.path`
前面，它会**遮蔽**真正的 `test_plan_widget` 模块 —— 主程序在测试里拿到的其实是旧控件。
本文件因此额外守住「无同名副本遮蔽」这一条。

覆盖：
1. 模块来源是项目根（不是 test/ 下的同名副本）；
2. 基本控件就位（表格/勾选框/后台徽章/工具按钮）；
3. `restyle_for_theme` 深浅两套样式：勾选框未勾选非白底、徽章非浅灰底，且可来回切；
4. `add_item` 真的进表（行数 +1，序号列有值）。

运行: python test/test_test_plan_widget.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 项目根在前
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import _config_sandbox  # noqa: E402

SANDBOX = Path(_config_sandbox.install())

import test_plan_widget as tpmod  # noqa: E402
from theme_settings import ThemeManager  # noqa: E402

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def test_module_not_shadowed():
    """产品模块必须来自项目根：test/ 下同名文件会遮蔽它（历史踩过）。"""
    root = Path(__file__).resolve().parent.parent
    mod_path = Path(tpmod.__file__).resolve()
    check("test_plan_widget 来自项目根", mod_path.parent == root, str(mod_path))
    check("test/ 下没有同名副本（否则会遮蔽产品模块）",
          not (root / "test" / "test_plan_widget.py").exists())
    check("TestPlanWidget 有 restyle_for_theme", hasattr(tpmod.TestPlanWidget, "restyle_for_theme"))


def test_widget_smoke(app):
    """控件就位 + 深浅主题样式 + 添加条目进表。"""
    ThemeManager.apply(app, "dark", font_family="Microsoft YaHei", font_size=10,
                       glass={}, mode="dark", system_dark=True)
    w = tpmod.TestPlanWidget()
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    w.show()
    app.processEvents()

    check("表格存在且有列", w.table is not None and w.table.columnCount() >= 6)
    check("「失败时停止」勾选框存在", hasattr(w, "chk_stop_on_fail"))
    check("后台状态徽章存在", hasattr(w, "lbl_bg_status"))

    # 深色：未勾选勾选框不能是白块，徽章不能是浅灰块
    w.restyle_for_theme(True)
    qss = w.chk_stop_on_fail.styleSheet().lower()
    check("深色下勾选框未勾选非白底", "#ffffff" not in qss and "#1e1e1e" in qss, qss)
    check("深色下表格勾选框非白底", "#ffffff" not in w.table.styleSheet().lower(),
          w.table.styleSheet())
    w._update_bg_status()
    badge = w.lbl_bg_status.styleSheet().lower()
    check("深色下后台徽章非浅灰底", "#f5f5f5" not in badge, badge)

    # 浅色：回到浅色样式（可来回切）
    w.restyle_for_theme(False)
    qss_light = w.chk_stop_on_fail.styleSheet().lower()
    check("浅色下勾选框回到白底", "#ffffff" in qss_light, qss_light)
    w._update_bg_status()
    check("浅色下后台徽章回到浅灰底",
          "#f5f5f5" in w.lbl_bg_status.styleSheet().lower(),
          w.lbl_bg_status.styleSheet())

    # 加一条进表
    before = w.table.rowCount()
    w.add_item("冒烟帧", "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16")
    app.processEvents()
    check("add_item 后表格行数 +1", w.table.rowCount() == before + 1,
          (before, w.table.rowCount()))
    check("新行序号列有内容",
          w.table.item(w.table.rowCount() - 1, 0) is not None
          and str(w.table.item(w.table.rowCount() - 1, 0).text()).strip() != "")
    w.close()
    w.deleteLater()


def run_all():
    app = QApplication.instance() or QApplication([])
    tests = [test_module_not_shadowed, test_widget_smoke]
    failures = 0
    for fn in tests:
        try:
            fn(app) if fn is test_widget_smoke else fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERR   {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    return 1 if (FAIL or failures) else 0


if __name__ == "__main__":
    code = run_all()
    sys.stdout.flush()
    os._exit(code)
