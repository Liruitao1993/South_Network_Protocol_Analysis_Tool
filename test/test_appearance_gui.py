# -*- coding: utf-8 -*-
"""主界面「太阳/月亮/跟随系统」外观按钮的 GUI 回归。

验证：
1. 右上角有外观按钮且图标非空；
2. 点一次从浅色 → 深色，实际深浅（`_is_dark_theme`）与图标都变；
3. **Fusion 经典 / Windows 原生主题在深色下真的变深**（QPalette 生效），切回浅色能恢复；
4. 「跟随系统」模式下由系统深浅决定，系统变化时实时跟随；
5. 选择持久化到 `config.json` 的 `ui.appearance`。

运行: python test/test_appearance_gui.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

for _n in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _n, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

SANDBOX = Path(_config_sandbox.install())

import main_gui  # noqa: E402
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


def _window_color(app):
    return app.palette().color(QPalette.ColorRole.Window).name()


def test_appearance_ui(app):
    win = main_gui.MainWindow()
    win.resize(1280, 860)
    win.show()
    for _ in range(4):
        app.processEvents()

    check("右上角有外观按钮", hasattr(win, "appearance_btn"))
    check("外观按钮图标非空", not win.appearance_btn.icon().isNull())
    check("默认外观为浅色",
          win._appearance_mode == "light" and not win._is_dark_theme(),
          f"{win._appearance_mode}/{win._is_dark_theme()}")
    check("提示含三种模式",
          all(s in win.appearance_btn.toolTip() for s in ("浅色", "深色", "跟随系统")),
          win.appearance_btn.toolTip())

    key_light = win.appearance_btn.icon().cacheKey()
    win._cycle_appearance()
    app.processEvents()
    key_dark = win.appearance_btn.icon().cacheKey()
    check("点击一次 → 深色", win._appearance_mode == "dark" and win._is_dark_theme())
    check("深色图标与浅色不同", key_dark != key_light)

    # ── 经典主题（Fusion）+ 深色：必须真的变深（QPalette） ──
    win._theme_id = "fusion"
    win._appearance_mode = "dark"
    win._apply_appearance()
    app.processEvents()
    dark_color = _window_color(app)
    check("Fusion 经典主题深色生效", dark_color.lower() == "#202225", dark_color)
    check("Fusion 深色下仍显示月亮", win.appearance_btn.icon().cacheKey() != key_light)

    win._appearance_mode = "light"
    win._apply_appearance()
    app.processEvents()
    light_color = _window_color(app)
    check("Fusion 切回浅色恢复出厂调色板",
          light_color.lower() != "#202225" and light_color.lower() == "#efefef", light_color)

    # ── 毛玻璃：浅色是半透明（opacity 生效），深色必须整窗不透明 ──
    win._theme_id = "glass"
    win._appearance_mode = "light"
    win._apply_appearance()
    light_op = win.windowOpacity()
    win._appearance_mode = "dark"
    win._apply_appearance()
    dark_op = win.windowOpacity()
    # 浅色毛玻璃的半透明是 QSS alpha（windowOpacity 仍为 1）；
    # 深色必须也是 1 —— 否则会把 opacity=60 当成整窗透明，整页发灰发透。
    check("毛玻璃切深色后整窗不透明", dark_op > 0.99,
          f"light={light_op:.2f}/dark={dark_op:.2f}")

    # ── 跟随系统（_apply_appearance 会重新探测系统深浅，必须 patch 探测函数） ──
    from unittest.mock import patch as _patch

    win._appearance_mode = "system"
    with _patch.object(ThemeManager, "detect_system_dark", staticmethod(lambda: True)):
        win._apply_appearance()
    check("跟随系统（系统深色）→ 深色", win._is_dark_theme())
    with _patch.object(ThemeManager, "detect_system_dark", staticmethod(lambda: False)):
        win._apply_appearance()
    check("跟随系统（系统浅色）→ 浅色", not win._is_dark_theme())

    # 系统信号：非 system 模式不应改变外观
    win._appearance_mode = "light"
    win._apply_appearance()
    win._on_system_color_scheme_changed()
    check("浅色模式不受系统深浅影响", not win._is_dark_theme())

    # ── 持久化 ──
    win._appearance_mode = "system"
    win._apply_appearance()
    cfg = json.loads((SANDBOX / "config.json").read_text(encoding="utf-8"))
    check("外观模式写入 config.json", cfg.get("ui", {}).get("appearance") == "system",
          str(cfg.get("ui")))
    check("load_mode 能读回", ThemeManager.load_mode(cfg) == "system")

    # ── 显式暗色主题 + 浅色模式：点一下要能回到浅色（不能"点了没反应"） ──
    win._theme_id = "dark"
    win._appearance_mode = "light"
    win._apply_appearance()
    check("暗色主题在浅色模式下仍为深色", win._is_dark_theme())
    win._cycle_appearance()
    app.processEvents()
    check("暗色主题点一下回到浅色",
          win._theme_id == "default" and not win._is_dark_theme(),
          f"{win._theme_id}/{win._appearance_mode}")

    win.close()
    return win


def test_dark_canvas_follows_theme(app):
    """自绘画布必须跟着主题走（拓扑图曾整块 #FAFAFA 白底，深色主题下 65.6% 亮底色块）。

    覆盖：画布配色单源 / 拓扑视图（底色·节点轮廓·角色名·空态提示·切回浅色）/
    字节视图字符格式前后景 / 原始日志快照行号槽与状态行 / 测试方案勾选框与徽章 /
    **全页像素扫描**（深色下任何页的亮底占比都不得超阈值）。
    """
    import canvas_theme

    # ① 单源：两套键位一致，深浅底色差别明显
    light, dark = canvas_theme.CANVAS_PALETTES[False], canvas_theme.CANVAS_PALETTES[True]
    check("画布配色两套键位一致", set(light) == set(dark), (set(light) ^ set(dark)))
    check("必备键齐全",
          {"bg", "border", "text", "muted", "hint", "line"} <= set(dark))
    check("深色画布底色明显更暗",
          dark["bg"].lower() != light["bg"].lower()
          and int(dark["bg"][1:3], 16) < 0x40 and int(light["bg"][1:3], 16) > 0xC0,
          (light["bg"], dark["bg"]))

    # ② 拓扑视图：底色 / 节点轮廓 / 角色名 / 空态提示
    from topology_widget import TopologyGraphicsView, TopoNode

    view = TopologyGraphicsView()
    view.restyle_for_theme(True)
    style = view.styleSheet().lower()
    check("拓扑视图深色底色", dark["bg"].lower() in style and light["bg"].lower() not in style,
          view.styleSheet())
    node = TopoNode(address="000000000001", tei=1, proxy_tei=-1, level=0,
                    role="CCO", phase="-", channel="载波")
    view.build_tree({1: node})
    item = view._node_items[1]
    check("节点轮廓用深色主题前景色（浅轮廓才看得见）",
          item.pen().color().name().lower() == dark["text"].lower(),
          (item.pen().color().name(), dark["text"]))
    check("角色名用深色主题次要色",
          item.role_label.defaultTextColor().name().lower() == dark["muted"].lower(),
          item.role_label.defaultTextColor().name())
    view.restyle_for_theme(False)
    empty_pen_ok = view._palette["hint"].lower() == light["hint"].lower()
    check("切回浅色后配色恢复", light["bg"].lower() in view.styleSheet().lower() and empty_pen_ok,
          view.styleSheet())
    view.restyle_for_theme(True)
    check("切主题后按上次数据重画（节点仍在）", 1 in view._node_items)

    # ③ 字节视图：字符格式里显式设过背景，必须跟着主题（否则盖掉 QSS 变白底）
    from hex_dump_view import HexDumpView

    hv = HexDumpView()
    hv.restyle_for_theme(True)
    hv.set_bytes(bytes(range(32)))
    check("字节视图深色前后景", hv._bg.name().lower() == dark["bg"].lower()
          and hv._fg.name().lower() == dark["text"].lower(),
          (hv._fg.name(), hv._bg.name()))
    hv.restyle_for_theme(False)
    check("字节视图浅色恢复", hv._bg.name().lower() == light["bg"].lower(), hv._bg.name())

    # ④ 原始日志快照：行号槽 + 状态行
    import batch_source_view

    if getattr(batch_source_view, "_QT_AVAILABLE", False):
        dlg = batch_source_view.SourceViewerDialog()
        dlg.restyle_for_theme(True)
        check("快照行号槽深色", dlg.view._ln_bg.name().lower() == dark["bg_alt"].lower(),
              dlg.view._ln_bg.name())
        check("快照状态行深色底", dark["bg"].lower() in dlg.status_label.styleSheet().lower(),
              dlg.status_label.styleSheet())
        dlg.deleteLater()
    else:
        check("快照对话框 Qt 层可用（跳过）", True)

    # ⑤ 测试方案：勾选框未勾选底色不能是白块 + 后台徽章
    from test_plan_widget import TestPlanWidget

    tp = TestPlanWidget()
    tp.restyle_for_theme(True)
    qss = tp.chk_stop_on_fail.styleSheet().lower()
    check("「失败时停止」勾选框深色样式", "#ffffff" not in qss and dark["bg"].lower() in qss,
          qss)
    table_qss = tp.table.styleSheet().lower()
    check("表格勾选框未勾选非白底", "#ffffff" not in table_qss, table_qss)
    tp._update_bg_status()
    check("后台徽章深色底", "#f5f5f5" not in tp.lbl_bg_status.styleSheet().lower(),
          tp.lbl_bg_status.styleSheet())
    tp.deleteLater()

    # ⑥ 全页像素扫描：深色下任何一页都不允许出现成片亮底（拓扑原本 65.6%）
    win = main_gui.MainWindow()
    win.resize(1500, 880)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    win._theme_id = "dark"
    win._appearance_mode = "dark"
    ThemeManager.apply(app, "dark", font_family=win._font_family,
                       font_size=win._font_size, glass=win._glass_settings,
                       mode="dark", system_dark=True)
    win._restyle_for_theme()
    for _ in range(4):
        app.processEvents()

    worst = []
    for i in range(win.tab_widget.count()):
        win.tab_widget.setCurrentIndex(i)
        for _ in range(2):
            app.processEvents()
        page = win.tab_widget.widget(i)
        if page is None:
            continue
        img = page.grab().toImage()
        bright = total = 0
        step = 12
        for y in range(0, img.height(), step):
            for x in range(0, img.width(), step):
                c = img.pixelColor(x, y)
                total += 1
                if 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue() > 190:
                    bright += 1
        ratio = bright / max(1, total)
        worst.append((ratio, win.tab_widget.tabText(i)))
    worst.sort(reverse=True)
    top = worst[0] if worst else (0, "-")
    check(f"深色主题下无成片亮底（最多 {top[1]} {top[0] * 100:.1f}%）",
          bool(worst) and top[0] < 0.05,
          [(n, round(r * 100, 1)) for r, n in worst[:3]])
    win.close()
    return win


def run_all():
    app = QApplication.instance() or QApplication([])
    tests = [test_appearance_ui, test_dark_canvas_follows_theme]
    failures = 0
    for fn in tests:
        try:
            fn(app)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERR   {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    return 1 if (FAIL or failures) else 0


if __name__ == "__main__":
    code = run_all()
    sys.stdout.flush()
    os._exit(code)
