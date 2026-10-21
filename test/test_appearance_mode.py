# -*- coding: utf-8 -*-
"""外观模式（浅色 / 深色 / 跟随系统）纯逻辑回归。

对应需求：主界面右上角太阳/月亮按钮要对**所有主题**都能切深浅，包括
「Fusion 经典」「Windows 原生」这类没有暗色 QSS 的调色板型主题。

运行: python test/test_appearance_mode.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from theme_settings import (APPEARANCE_LABELS, APPEARANCE_MODES,  # noqa: E402
                            PALETTE_DARK_THEMES, THEME_IDS, ThemeManager,
                            build_dark_palette, resolve_appearance)


def test_constants():
    assert APPEARANCE_MODES == ("light", "dark", "system")
    assert set(APPEARANCE_LABELS) == set(APPEARANCE_MODES)
    assert set(PALETTE_DARK_THEMES) <= set(THEME_IDS)


def test_light_keeps_theme():
    for theme in ("default", "glass", "mica", "fusion", "windows", "windowsvista"):
        assert resolve_appearance(theme, "light", False) == (theme, False)
        assert resolve_appearance(theme, "light", True) == (theme, False)


def test_dark_falls_back_for_qss_themes():
    # 没有暗色 QSS 的主题 → 用 dark 主题渲染，但「是否深色」必须为真
    for theme in ("default", "glass", "mica"):
        assert resolve_appearance(theme, "dark", False) == ("dark", True)


def test_dark_keeps_palette_themes():
    # 经典 / 原生主题：保留主题 id，靠 QPalette 变深（这正是用户要的）
    for theme in PALETTE_DARK_THEMES:
        assert resolve_appearance(theme, "dark", False) == (theme, True)


def test_system_mode_follows_system():
    for theme in ("default", "fusion", "windowsvista", "glass"):
        light_id, light_dark = resolve_appearance(theme, "system", False)
        dark_id, dark_dark = resolve_appearance(theme, "system", True)
        assert light_dark is False
        assert dark_dark is True
        assert light_id == theme
    # 深色解析：调色板主题保留 id，其余落 dark
    assert resolve_appearance("fusion", "system", True) == ("fusion", True)
    assert resolve_appearance("default", "system", True) == ("dark", True)


def test_explicit_dark_theme_wins():
    for mode in APPEARANCE_MODES:
        assert resolve_appearance("dark", mode, False) == ("dark", True)
        assert resolve_appearance("dark", mode, True) == ("dark", True)


def test_unknown_inputs_fall_back():
    assert resolve_appearance(None, "light") == ("default", False)
    assert resolve_appearance("nonexistent", "light") == ("nonexistent", False)
    assert resolve_appearance("fusion", "bogus", False) == ("fusion", False)


def test_load_mode_fallbacks():
    assert ThemeManager.load_mode({"ui": {"appearance": "dark"}}) == "dark"
    assert ThemeManager.load_mode({"ui": {"appearance": "SYSTEM"}}) == "system"
    # 旧配置没有 appearance：按主题推断
    assert ThemeManager.load_mode({"ui": {"theme": "dark"}}) == "dark"
    assert ThemeManager.load_mode({"ui": {"theme": "fusion"}}) == "light"
    assert ThemeManager.load_mode({}) == "light"
    assert ThemeManager.load_mode("bad") == "light"
    assert ThemeManager.load_mode({"ui": {"appearance": "nope"}}) == "light"


def test_to_config_includes_appearance():
    cfg = ThemeManager.to_config("fusion", "Microsoft YaHei", 10, mode="system")
    assert cfg["appearance"] == "system"
    # 非法模式不写入（保持旧配置兼容）
    assert "appearance" not in ThemeManager.to_config("fusion", "x", 10, mode="bogus")
    assert "appearance" not in ThemeManager.to_config("fusion", "x", 10)


def test_dark_palette_is_dark():
    p = build_dark_palette()
    from PySide6.QtGui import QPalette

    window = p.color(QPalette.ColorRole.Window)
    text = p.color(QPalette.ColorRole.WindowText)
    base = p.color(QPalette.ColorRole.Base)
    # 背景明显暗、文字明显亮（用亮度加权判断，避免只看单通道）
    def lum(c):
        return 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()

    assert lum(window) < 80 and lum(base) < 80, (lum(window), lum(base))
    assert lum(text) > 180, lum(text)
    assert lum(text) - lum(window) > 100, "深色盘对比度不足"
    # 选中态可读
    hl = p.color(QPalette.ColorRole.Highlight)
    hlt = p.color(QPalette.ColorRole.HighlightedText)
    assert lum(hlt) - lum(hl) > 80


def run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERR   {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)
