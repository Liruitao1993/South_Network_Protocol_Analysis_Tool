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


def run_all():
    app = QApplication.instance() or QApplication([])
    tests = [test_appearance_ui]
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
