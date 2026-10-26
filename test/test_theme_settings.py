"""

主题与字体设置测试（test_theme_settings.py）
运行：python test_theme_settings.py
覆盖：
- 7 套内置主题 apply 不崩溃，style/QSS 正确切换（毛玻璃/云母为参数化动态 QSS；
  apply 在主题 QSS 末尾追加统一按钮 QSS，断言用前缀匹配）
- **QListWidget 必须与表格同款覆盖**（静态选择器断言 + 分别注入深色/浅色系统调色板后的
  实际渲染文字对比度断言）——见 1c 节注释
- 字体族/字号设置生效
- ThemeSettingsDialog：创建、取值、恢复默认、取消还原
使用 offscreen 平台，无需显示器。
"""

import os
import sys
import traceback
from collections import Counter

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 本测试会 show 主窗口并关闭各对话框 → 退出路径会写 config.json；
# 沙箱到临时目录，避免把 offscreen 合成几何写进开发机真实配置。
# 放在 import 块**之后**：install() 是语句，插在 import 之间会让后续 import 触发 E402。
import _config_sandbox  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QListWidget,
    QStyle,
    QStyleFactory,
    QTreeWidget,
    QTreeWidgetItem,
)

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

# ---------------- 1c. 列表（QListWidget）主题覆盖 ----------------
# 回归缺陷：QListWidget 原先未纳入任何主题的「表格 / 字段树」选择器组。在**深色系统**
# 下（实测本机 Windows 深色模式 colorScheme=Dark），未主题化的交替行会取调色板的
# AlternateBase（深色），而浅色主题又用 `* { color: #000000 }` 强制黑字 →
# 「特征码」对话框隔行黑字压深底，读数时才看得见（对比度实测 1.35）。
# 两道防线：① 静态 —— 凡主题给 QTableWidget 的规则必须同时给 QListWidget；
#           ② 渲染 —— 分别注入深色/浅色系统调色板，实测交替行与普通行文字对比度。
section("列表主题覆盖 (QListWidget)")


def _theme_qss(t):
    """主题的**有效** QSS（毛玻璃/云母为参数化生成；原生主题返回空串）。"""
    if t.get("win_blur"):
        return build_glass_qss()
    if t.get("mica"):
        return build_mica_qss()
    return t["qss"] or ""


def _rel_lum(rgb):
    def _c(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * _c(rgb[0]) + 0.7152 * _c(rgb[1]) + 0.0722 * _c(rgb[2])


def _contrast(a, b):
    la, lb = _rel_lum(a), _rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _row_text(lw, row):
    """返回 (行底色, 文字色估计, 对比度)。

    只取**文字区**（跳过勾选框，否则勾选框图元的高对比像素会掩盖文字问题），
    文字色 = 该区域内偏离底色最大的像素。
    """
    img = lw.viewport().grab().toImage()
    dpr = img.devicePixelRatio() or 1.0
    rect = lw.visualItemRect(lw.item(row))
    st = lw.style()
    skip = (
        st.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, lw)
        + st.pixelMetric(QStyle.PixelMetric.PM_CheckBoxLabelSpacing, None, lw)
        + 4
    )
    x0 = max(0, int((rect.left() + skip) * dpr))
    x1 = min(img.width() - 1, int((rect.right() - 1) * dpr))
    y0 = max(0, int((rect.top() + 2) * dpr))
    y1 = min(img.height() - 1, int((rect.bottom() - 2) * dpr))
    colors = [
        img.pixelColor(x, y).getRgb()[:3]
        for y in range(y0, y1 + 1)
        for x in range(x0, x1 + 1)
    ]
    if not colors:
        return None, None, None
    bg = Counter(colors).most_common(1)[0][0]
    text = max(colors, key=lambda c: _contrast(c, bg))
    return bg, text, _contrast(text, bg)


def _system_palette(base: str, alt: str, text: str, window: str, btn: str):
    """构造「系统调色板」：QSS 未覆盖处（如列表交替行底色）由它兜底。"""
    p = QPalette()
    for role, name in (
        (QPalette.ColorRole.Window, window),
        (QPalette.ColorRole.WindowText, text),
        (QPalette.ColorRole.Base, base),
        (QPalette.ColorRole.AlternateBase, alt),
        (QPalette.ColorRole.Text, text),
        (QPalette.ColorRole.Button, btn),
        (QPalette.ColorRole.ButtonText, text),
        (QPalette.ColorRole.Highlight, "#0078d4"),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
    ):
        p.setColor(role, QColor(name))
    return p


# 两个方向都要过：主题与系统调色板不一致时，未覆盖的交替行会取到「另一侧」的底色
# （实测本机 Windows 深色模式的 AlternateBase = #001a68 是个深色，浅色主题下黑字压深底）。
_INJECTED = (
    (
        "深色系统",
        _system_palette("#2d2d2d", "#001a68", "#ffffff", "#1e1e1e", "#3c3c3c"),
    ),
    (
        "浅色系统",
        _system_palette("#ffffff", "#f7f7f7", "#000000", "#efefef", "#f0f0f0"),
    ),
)

_palette_backup = app.palette()
for _t in THEMES:
    _q = _theme_qss(_t)
    if not _q:
        continue  # 原生主题（fusion / windows）无 QSS，配色完全由调色板自洽给出
    # ① 静态：表格规则必须同时覆盖列表（新主题漏写会在本条变红）
    _missing = [
        line.strip()
        for line in _q.splitlines()
        if "QTableWidget" in line and "QListWidget" not in line
    ]
    check(
        f"{_t['id']} 列表与表格同款覆盖",
        not _missing,
        f"缺 QListWidget 的表格规则 {len(_missing)} 条: {_missing[:2]}",
    )
    # ② 渲染：两种系统调色板下，交替行/普通行文字都必须可读
    for _sys_name, _sys_pal in _INJECTED:
        ThemeManager.apply(app, _t["id"], "Microsoft YaHei", 10)
        app.setPalette(_sys_pal)
        _lw = QListWidget()
        _lw.setAlternatingRowColors(True)
        for _i in range(4):
            _lw.addItem(f"0000fff{_i}  notify/write 长度 {_i}0")
        _lw.resize(360, 150)
        _lw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        _lw.show()
        app.processEvents()
        for _row, _kind in ((1, "交替行"), (0, "普通行")):
            _bg, _tx, _cr = _row_text(_lw, _row)
            check(
                f"{_t['id']} {_sys_name} {_kind}文字可读",
                _cr is not None and _cr >= 4.5,
                f"底色={_bg} 文字={_tx} 对比度={None if _cr is None else round(_cr, 2)}",
            )
        _lw.close()
        _lw.deleteLater()
app.setPalette(_palette_backup)
del _palette_backup

# ---------------- 1d. 行内复选框（item view indicator） ----------------
section("行内复选框可见性 (QAbstractItemView::indicator)")

import re as _re4  # noqa: E402

#: 只匹配基态规则块（`:checked`/`:indeterminate` 不匹配 `indicator\s*{`）
_IND_BASE_BLOCK = _re4.compile(r"QAbstractItemView::indicator\s*\{[^}]*\}", _re4.S)
_IND_ANY_BLOCK = _re4.compile(r"QAbstractItemView::indicator[^{]*\{[^}]*\}", _re4.S)

for _t in THEMES:
    _qss = _theme_qss(_t)
    # 原生主题（fusion / windows / windowsvista 主体）不写复选框样式 ⇒ 由系统绘制，跳过；
    # 判据是「该主题是否本来就给 QCheckBox 写了 indicator」，而不是 qss 是否为空
    # （windowsvista 有一段只修输入框的补充 QSS）。
    if "QCheckBox::indicator" not in _qss:
        continue
    _blocks = _IND_BASE_BLOCK.findall(_qss)
    check(f"[1d] {_t['id']} 有行内复选框基态规则", len(_blocks) >= 1,
          f"blocks={len(_blocks)}")
    check(f"[1d] {_t['id']} 基态含边框与底色",
          bool(_blocks) and "border:" in _blocks[0]
          and "background-color:" in _blocks[0],
          _blocks[0][:80] if _blocks else "")
    check(f"[1d] {_t['id']} 勾选/部分勾选态齐备",
          "QAbstractItemView::indicator:checked" in _qss
          and "QAbstractItemView::indicator:indeterminate" in _qss)


def _indicator_metrics(qss: str = ""):
    """渲染一棵树，返回 (未勾选高对比像素数, 勾选态是否可区分, 勾选高对比像素数)。

    qss 非空时临时覆盖样式表（用于变异自检），仅影响本次渲染。
    """
    if qss:
        app.setStyleSheet(qss)
    tree = QTreeWidget()
    tree.setHeaderHidden(True)
    tree.setRootIsDecorated(False)      # 去掉分支箭头，区域里只剩复选框
    for text, state in (("未勾选", Qt.CheckState.Unchecked),
                        ("已勾选", Qt.CheckState.Checked)):
        item = QTreeWidgetItem([text])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, state)
        tree.addTopLevelItem(item)
    tree.resize(220, 70)
    tree.show()
    app.processEvents()
    app.processEvents()
    img = tree.viewport().grab().toImage()
    dpr = img.devicePixelRatio() or 1.0

    def region(item):
        rect = tree.visualItemRect(item)
        x0 = max(0, int((rect.left() + 1) * dpr))
        x1 = min(img.width() - 1, int((rect.left() + 24) * dpr))
        y0 = max(0, int((rect.top() + 1) * dpr))
        y1 = min(img.height() - 1, int((rect.bottom() - 1) * dpr))
        return [img.pixelColor(x, y).getRgb()[:3]
                for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]

    colors_unchecked = region(tree.topLevelItem(0))
    colors_checked = region(tree.topLevelItem(1))
    tree.close()
    tree.deleteLater()
    if not colors_unchecked or not colors_checked:
        return 0, False, 0
    bg_u = Counter(colors_unchecked).most_common(1)[0][0]
    bg_c = Counter(colors_checked).most_common(1)[0][0]
    strong_u = sum(1 for c in colors_unchecked if _contrast(c, bg_u) >= 3.0)
    strong_c = sum(1 for c in colors_checked if _contrast(c, bg_c) >= 3.0)
    return strong_u, set(colors_unchecked) != set(colors_checked), strong_c


for _theme_id in ("default", "dark", "glass", "mica"):
    ThemeManager.apply(app, _theme_id, "Microsoft YaHei", 10)
    _su, _distinct, _sc = _indicator_metrics()
    check(f"[1d] {_theme_id} 未勾选复选框有可见边框（≥3:1 像素 ≥ 20）",
          _su >= 20, f"strong={_su}")
    check(f"[1d] {_theme_id} 勾选/未勾选可区分且勾选态可见",
          bool(_distinct) and _sc >= 20, f"distinct={_distinct} checked={_sc}")

# 反例自检：把行内指示器规则整段删掉后，未勾选「可见边框」判据必须变红
ThemeManager.apply(app, "default", "Microsoft YaHei", 10)
_qss_default = _theme_qss(get_theme("default"))
_stripped = _IND_ANY_BLOCK.sub("", _qss_default)
check("[1d] 反例自检前提：规则确实被删掉",
      "QAbstractItemView::indicator" not in _stripped)
_su_broken, _d_broken, _sc_broken = _indicator_metrics(_stripped)
check("[1d] 反例自检：删掉规则后未勾选框不可见（判据能抓住回退）",
      _su_broken < 20, f"strong={_su_broken}")
ThemeManager.apply(app, "default", "Microsoft YaHei", 10)   # 还原

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
