"""

主题与字体设置测试（test_theme_settings.py）
运行：python test_theme_settings.py
覆盖：
- 7 套内置主题 apply 不崩溃，style/QSS 正确切换（毛玻璃/云母为参数化动态 QSS；
  apply 在主题 QSS 末尾追加统一按钮 QSS，断言用前缀匹配）
- 字体族/字号设置生效
- ThemeSettingsDialog：创建、取值、恢复默认、取消还原
使用 offscreen 平台，无需显示器。
"""

import os
import sys
import traceback

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 本测试会 show 主窗口并关闭各对话框 → 退出路径会写 config.json；
# 沙箱到临时目录，避免把 offscreen 合成几何写进开发机真实配置。
# 放在 import 块**之后**：install() 是语句，插在 import 之间会让后续 import 触发 E402。
import _config_sandbox  # noqa: E402
from PySide6.QtWidgets import QApplication, QStyleFactory

from theme_settings import (
    GLASS_DEFAULTS,
    THEMES,
    ThemeManager,
    ThemeSettingsDialog,
    build_glass_qss,
    build_mica_qss,
    button_qss_for_theme,
    get_theme,
    is_dark,
)

_config_sandbox.install()

app = QApplication(sys.argv)

# offscreen 平台下 app.style().objectName() 为空，用 className 判定
_STYLE_CLASS = {
    "Fusion": "QFusionStyle",
    "windows": "QWindowsStyle",
    "windowsvista": "QWindowsVistaStyle",
}

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {detail}")


def section(title):
    print(f"\n== {title} ==")


# ---------------- 1. 主题应用 ----------------
section("主题应用 (apply)")
for t in THEMES:
    try:
        # 风格名在平台可创建（PySide6 将带 QSS 的风格包装为私有 QStyleSheetStyle，无法检查类名）
        s = QStyleFactory.create(t["style"])
        ThemeManager.apply(app, t["id"], "Microsoft YaHei", 10)
        # 毛玻璃/云母 QSS 由 build_*_qss 按默认参数动态生成（含主窗口背景覆盖段）；
        # 所有主题末尾追加统一按钮 QSS → 前缀匹配而非全等
        if t.get("win_blur"):
            expect_qss = build_glass_qss()
        elif t.get("mica"):
            expect_qss = build_mica_qss()
        else:
            expect_qss = t["qss"] or ""
        sheet = app.styleSheet()
        qss_ok = sheet.startswith(expect_qss) and "QPushButton" in sheet
        check(
            f"{t['id']} 应用",
            s is not None and qss_ok,
            f"style={t['style']} qss_len={len(sheet)}",
        )
    except Exception:
        failed += 1
        print(f"  [FAIL] {t['id']} 应用抛异常")
        traceback.print_exc()

# ---------------- 1b. 毛玻璃参数 ----------------
section("毛玻璃参数 (build_glass_qss)")
try:
    import re as _re

    q30 = build_glass_qss(opacity=30)
    # 缩放作用面 = 主窗口表面层 alpha（110→55）；基础 QWidget 极低 alpha 不参与断言
    m = _re.search(
        r"QMainWindow \{\s*background-color: rgba\(240, 245, 255, (\d+)\)", q30
    )
    check(
        "透明度缩放",
        m is not None and int(m.group(1)) == 55,
        m.group(1) if m else "未匹配",
    )
    check("近不透明弹窗保持", "rgba(248, 250, 255, 230)" in q30)
    check("玻璃着色", "rgba(255, 136, 0," in build_glass_qss(tint="#ff8800"))
    check(
        "无效背景图回退着色",
        "border-image" not in build_glass_qss(bg_image=r"C:\nonexistent\x.jpg"),
    )
    import tempfile as _tf

    _img = os.path.join(_tf.gettempdir(), "glass_test_bg.png")
    with open(_img, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    qb = build_glass_qss(tint="#ff8800", bg_image=_img)
    check(
        "背景图 border-image", "border-image: url(" in qb and "glass_test_bg.png" in qb
    )
    check("背景图叠加色", "rgba(255, 136, 0," in qb)
    ThemeManager.apply(app, "glass", glass={"opacity": 40, "tint": "#00ff00"})
    check("apply 传参生效", "rgba(0, 255, 0," in app.styleSheet())
    dlg = ThemeSettingsDialog("glass", "Microsoft YaHei", 10, glass={"opacity": 40})
    check("对话框玻璃选项可见", dlg.glass_group.isVisibleTo(dlg))
    dlg.glass_opacity_slider.setValue(80)
    g = dlg.get_glass_settings()
    check(
        "对话框取值",
        g["opacity"] == 80
        and g["tint"] == GLASS_DEFAULTS["tint"]
        and g["bg_image"] == "",
    )
    dlg2 = ThemeSettingsDialog("default", "Microsoft YaHei", 10)
    # 透明度全局可用（组框常显）；玻璃专属行（颜色/背景图）仅玻璃主题显示
    check(
        "非玻璃主题隐藏玻璃专属行",
        dlg2.glass_group.isVisibleTo(dlg2)
        and not dlg2.glass_tint_btn.isVisibleTo(dlg2)
        and not dlg2.glass_bg_edit.isVisibleTo(dlg2)
        and dlg2.glass_opacity_slider.isVisibleTo(dlg2),
    )
    cfg = ThemeManager.to_config(
        "glass",
        "Microsoft YaHei",
        10,
        glass={"opacity": 33, "tint": "#112233", "bg_image": _img},
    )
    check(
        "配置读写往返",
        ThemeManager.load_glass_config({"ui": cfg})
        == {"opacity": 33, "tint": "#112233", "bg_image": _img},
    )
except Exception:
    failed += 1
    print("  [FAIL] 毛玻璃参数抛异常")
    traceback.print_exc()

# 未知主题回退默认（回退到带 QSS 的 default 主题）
ThemeManager.apply(app, "not_exist_theme")
check("未知主题回退默认", app.styleSheet().startswith(get_theme("default")["qss"]))

# ---------------- 2. 字体设置 ----------------
section("字体设置")
ThemeManager.apply(app, "default", "SimSun", 12)
f = app.font()
check("字体族生效", f.family() == "SimSun", f"family={f.family()}")
check("字号生效", f.pointSize() == 12, f"size={f.pointSize()}")

# 默认值兜底
ThemeManager.apply(app, "default", "", 0)
check("空参数回退默认字体", app.font().family() == ThemeManager.DEFAULT_FONT_FAMILY)

# ---------------- 3. 配置读写 ----------------
section("配置读写")
cfg_in = {"ui": {"theme": "dark", "font_family": "SimHei", "font_size": 14}}
theme_id, fam, size = ThemeManager.load_from_config(cfg_in)
check("load_from_config", (theme_id, fam, size) == ("dark", "SimHei", 14))
out = ThemeManager.to_config("dark", "SimHei", 14)
check("to_config", out == cfg_in["ui"])
theme_id2, fam2, size2 = ThemeManager.load_from_config({})
check(
    "空配置回退默认",
    (theme_id2, fam2, size2)
    == (
        ThemeManager.DEFAULT_THEME_ID,
        ThemeManager.DEFAULT_FONT_FAMILY,
        ThemeManager.DEFAULT_FONT_SIZE,
    ),
)

# ---------------- 4. ThemeSettingsDialog ----------------
section("ThemeSettingsDialog")
try:
    dlg = ThemeSettingsDialog("default", "Microsoft YaHei", 10)
    check("对话框创建", dlg is not None)
    check("主题下拉项数", dlg.theme_combo.count() == len(THEMES))
    check("字号范围", dlg.size_spin.minimum() == 8 and dlg.size_spin.maximum() == 24)

    # 切换主题即时预览
    dark_idx = next(i for i, t in enumerate(THEMES) if t["id"] == "dark")
    dlg.theme_combo.setCurrentIndex(dark_idx)
    check("切换主题即时应用", app.styleSheet().startswith(get_theme("dark")["qss"]))
    check("is_dark 判定", is_dark(dlg.theme_combo.currentData()))

    # 恢复默认
    dlg._reset_defaults()
    check(
        "恢复默认主题", dlg.theme_combo.currentData() == ThemeManager.DEFAULT_THEME_ID
    )
    check("恢复默认字号", dlg.size_spin.value() == ThemeManager.DEFAULT_FONT_SIZE)
    check("恢复默认应用", app.styleSheet().startswith(get_theme("default")["qss"]))

    # 修改后 get_settings
    dlg.theme_combo.setCurrentIndex(dark_idx)
    dlg.size_spin.setValue(16)
    tid, famd, sz = dlg.get_settings()
    check("get_settings", tid == "dark" and sz == 16, f"{tid} {famd} {sz}")

    # 取消还原
    dlg.theme_combo.setCurrentIndex(0)
    ThemeManager.apply(app, "windows", "SimSun", 9)  # 进入对话框前配置
    dlg2 = ThemeSettingsDialog("windows", "SimSun", 9)
    dlg2.theme_combo.setCurrentIndex(dark_idx)  # 改成暗色
    dlg2.reject()
    # windows 主题无自定义 QSS，apply 产出 = 换行 + 统一按钮 QSS
    check("取消还原主题", app.styleSheet() == "\n" + button_qss_for_theme("windows"))
    check(
        "取消还原字体", app.font().family() == "SimSun" and app.font().pointSize() == 9
    )

    # ── 云母主题 ──
    mica_idx = next(i for i, t in enumerate(THEMES) if t["id"] == "mica")
    check(
        "云母主题已注册",
        get_theme("mica").get("mica") is True and 0 <= mica_idx < len(THEMES),
    )
    # 云母为全不透明静态配色（透明底衬会在本 GUI 产生容器表面重影）：
    # 所有关键表面必须实色，不得含 alpha 混合
    import re as _re2

    qm = build_mica_qss(opacity=45)
    check("云母 QSS 静态不随透明度缩放", qm == get_theme("mica")["qss"])
    _surfaces = [
        "QWidget",
        "QMainWindow",
        "QStackedWidget",
        "QDialog",
        "QMenu",
        "QGroupBox",
        "QMenuBar",
        "QStatusBar",
    ]
    _bad = [
        s
        for s in _surfaces
        if _re2.search(s + r"[^\n]*\{\s*[^}]*?background-color:\s*rgba", qm)
    ]
    check("云母关键表面全不透明", not _bad, f"半透明表面: {_bad}")
    check("云母底色正确", "background-color: #f3f3f3" in qm)
    check("云母滚动条 handle 允许半透明", "rgba(0, 0, 0, 95)" in qm)
    dm = ThemeSettingsDialog("mica", "Microsoft YaHei", 10)
    check(
        "云母选中时隐藏玻璃专属行",
        dm.glass_group.isVisibleTo(dm)
        and not dm.glass_tint_btn.isVisibleTo(dm)
        and not dm.glass_bg_edit.isVisibleTo(dm),
    )
    dm.reject()
    del mica_idx
    dlg2.deleteLater()
    dlg.deleteLater()
except Exception:
    failed += 1
    print("  [FAIL] 对话框测试抛异常")
    traceback.print_exc()

# ---------------- 5. MainWindow 集成 ----------------
section("MainWindow 集成")
try:
    from main_gui import MainWindow

    ThemeManager.apply(app, "default", "Microsoft YaHei", 10)
    w = MainWindow()
    w.show()
    check("MainWindow 实例化", w is not None)
    check("统计标签注册", len(w._stats_labels) > 0, f"n={len(w._stats_labels)}")

    # 模拟主题切换后的动态控件重设
    w._theme_id = "dark"
    w._restyle_for_theme()
    check(
        "暗色下统计标签重设",
        w._stats_labels[0][0].styleSheet().startswith("color: #aaa"),
    )
    check("暗色下串口状态提亮", "#bbb" in w.serial_status_label.styleSheet())
    check("暗色下批量状态重设", "#333333" in w.batch_status_bar.styleSheet())

    w._theme_id = "default"
    w._restyle_for_theme()
    check(
        "浅色下统计标签重设",
        w._stats_labels[0][0].styleSheet().startswith("color: #666"),
    )
    w.close()
except Exception:
    failed += 1
    print("  [FAIL] MainWindow 集成测试抛异常")
    traceback.print_exc()

print(f"\n结果: {passed} 通过, {failed} 失败")
sys.exit(1 if failed else 0)
