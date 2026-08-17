"""

主题与字体设置测试（test_theme_settings.py）
运行：python test_theme_settings.py
覆盖：
- 5 套内置主题 apply 不崩溃，style/QSS 正确切换
- 字体族/字号设置生效
- ThemeSettingsDialog：创建、取值、恢复默认、取消还原
- MainWindow 集成：实例化、主题切换后 _restyle_for_theme 不崩溃
使用 offscreen 平台，无需显示器。
"""

import _path_setup  # noqa: E402

import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QStyleFactory, QDialog

from theme_settings import (
    THEMES, get_theme, is_dark,
    ThemeManager, ThemeSettingsDialog,
)

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
        qss_ok = (app.styleSheet() == (t["qss"] or ""))
        check(f"{t['id']} 应用", s is not None and qss_ok,
              f"style={t['style']} qss_len={len(app.styleSheet())}")
    except Exception:
        failed += 1
        print(f"  [FAIL] {t['id']} 应用抛异常")
        traceback.print_exc()

# 未知主题回退默认（回退到带 QSS 的 default 主题）
ThemeManager.apply(app, "not_exist_theme")
check("未知主题回退默认", app.styleSheet() == get_theme("default")["qss"])

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
check("空配置回退默认", (theme_id2, fam2, size2) ==
      (ThemeManager.DEFAULT_THEME_ID, ThemeManager.DEFAULT_FONT_FAMILY, ThemeManager.DEFAULT_FONT_SIZE))

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
    check("切换主题即时应用", app.styleSheet() == get_theme("dark")["qss"])
    check("is_dark 判定", is_dark(dlg.theme_combo.currentData()))

    # 恢复默认
    dlg._reset_defaults()
    check("恢复默认主题", dlg.theme_combo.currentData() == ThemeManager.DEFAULT_THEME_ID)
    check("恢复默认字号", dlg.size_spin.value() == ThemeManager.DEFAULT_FONT_SIZE)
    check("恢复默认应用", app.styleSheet() == get_theme("default")["qss"])

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
    check("取消还原主题", app.styleSheet() == "")
    check("取消还原字体", app.font().family() == "SimSun" and app.font().pointSize() == 9)
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
    check("暗色下统计标签重设", w._stats_labels[0][0].styleSheet().startswith("color: #aaa"))
    check("暗色下串口状态提亮", "#bbb" in w.serial_status_label.styleSheet())
    check("暗色下批量状态重设", "#333333" in w.batch_status_bar.styleSheet())

    w._theme_id = "default"
    w._restyle_for_theme()
    check("浅色下统计标签重设", w._stats_labels[0][0].styleSheet().startswith("color: #666"))
    w.close()
except Exception:
    failed += 1
    print("  [FAIL] MainWindow 集成测试抛异常")
    traceback.print_exc()

print(f"\n结果: {passed} 通过, {failed} 失败")
sys.exit(1 if failed else 0)
