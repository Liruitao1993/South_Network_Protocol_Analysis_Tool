"""app_icons 主题感知图标引擎测试（offscreen）。

覆盖：
- load_icon 返回非空 QIcon；缺失图标返回空 QIcon（不崩）
- 渲染出的 pixmap 有不透明像素（SVG 真正画出来了，不是全透明）
- 颜色跟随调色板：亮色主题画深色、暗色主题画浅色、Disabled 画灰
- 标签页用到的 13 个图标全部存在

运行（项目根）：
    python test/test_app_icons.py
"""

import os
import sys
import warnings
from pathlib import Path

import _path_setup  # noqa: E402

warnings.filterwarnings("ignore")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(_path_setup.__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


TAB_ICONS = [
    "terminal",
    "search",
    "files",
    "wrench",
    "bookmark",
    "clipboard-list",
    "archive",
    "network",
    "file-diff",
    "toolbox",
    "gauge",
    "radar",
    "activity",
    "refresh-cw",
]


def _render_pixels(icon, mode):
    """渲染 32x32，返回非透明像素颜色列表 [(r,g,b,a), ...]。"""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon

    pm = icon.pixmap(QSize(32, 32), mode)
    img = pm.toImage()
    out = []
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0:
                out.append((c.red(), c.green(), c.blue(), c.alpha()))
    return out


def main():
    from PySide6.QtGui import QColor, QIcon, QPalette
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    import app_icons

    print("load_icon basic:")
    icon = app_icons.load_icon("terminal")
    check("known icon not null", not icon.isNull())
    missing = app_icons.load_icon("__not_exist_icon__")
    check("missing icon is null", missing.isNull())
    check("cached same object", app_icons.load_icon("terminal") is icon)

    print("tab icons all available:")
    missing_list = [
        n
        for n in TAB_ICONS
        if (app_icons._ICONS_DIR / f"{n}.svg").exists() is False
    ]
    check("14 tab/refresh icons present", not missing_list)
    if missing_list:
        print("   missing:", missing_list)

    print("rendering (light palette):")
    pal_light = app.style().standardPalette()
    pal_light.setColor(QPalette.ColorGroup.Normal, QPalette.ColorRole.ButtonText,
                       QColor("#1f2937"))
    pal_light.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText,
                       QColor("#9ca3af"))
    app.setPalette(pal_light)
    px = _render_pixels(icon, QIcon.Mode.Normal)
    check("normal mode has pixels", len(px) > 50)
    # 抽样像素颜色接近目标深色（抗锯齿允许容差）
    r, g, b, _ = px[len(px) // 2]
    check(
        "normal color ~ #1f2937",
        abs(r - 0x1F) < 60 and abs(g - 0x29) < 60 and abs(b - 0x37) < 60,
    )
    pxd = _render_pixels(icon, QIcon.Mode.Disabled)
    check("disabled mode has pixels", len(pxd) > 50)
    rd, gd, bd, _ = pxd[len(pxd) // 2]
    check("disabled color ~ gray #9ca3af", abs(rd - 0x9C) < 60 and abs(bd - 0xAF) < 60)

    print("rendering (dark palette):")
    pal_dark = QPalette(pal_light)
    pal_dark.setColor(QPalette.ColorGroup.Normal, QPalette.ColorRole.ButtonText,
                      QColor("#e5e7eb"))
    app.setPalette(pal_dark)
    px2 = _render_pixels(icon, QIcon.Mode.Normal)
    check("dark mode has pixels", len(px2) > 50)
    r2, g2, b2, _ = px2[len(px2) // 2]
    check(
        "dark color ~ #e5e7eb (light)",
        r2 > 0xC0 and g2 > 0xC0 and b2 > 0xC0,
    )

    print(f"\n{'=' * 40}")
    print(f"PASS: {PASS}  FAIL: {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
