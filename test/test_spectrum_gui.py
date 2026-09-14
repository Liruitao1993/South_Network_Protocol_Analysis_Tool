# -*- coding: utf-8 -*-
"""频谱图 GUI 集成冒烟测试（offscreen）

走真实链路验证 main_gui.py 接线与 spectrum_widget.py 的 Qt 层：
  1. 「频谱图」tab 已注册且**常驻可见**（切换协议不隐藏）
  2. 工具栏/参数区控件齐全
  3. 频率四字段双向联动（含单位切换换算）
  4. 粘贴 trace 数值 → 绘制（点数/状态行/频率步进）
  5. 非法 token 报错且不破坏已有图形
  6. 纵轴自动适配切换改变纵轴口径
  7. 单位换算（50Ω）作用于迹线数值
  8. render_image 双主题尺寸正确且非纯色；导出 PNG 可被 QImage 读回
  9. 主题切换 restyle_for_theme 生效；主窗口 _restyle_for_theme 钩子不抛异常
 10. 清空复位

直接运行: python test/test_spectrum_gui.py
"""

import _path_setup  # noqa: E402

import math
import os
import random
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FAILURES = []
PASS = 0


def check(name, cond, detail=""):
    global PASS
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASS += 1
    else:
        FAILURES.append(name)


def _sample_text(n=100):
    """合成一段带峰值的 trace（dBm），供绘制用例使用。"""
    random.seed(7)
    values = [
        -70.0 + 10 * math.exp(-(((i - 60) / 12.0) ** 2)) + random.uniform(-2, 2)
        for i in range(n)
    ]
    return " ".join(f"{v:.1f}" for v in values)


def _distinct_colors(image, step=17):
    seen = set()
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            seen.add(image.pixel(x, y))
    return len(seen)


def main():
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    import main_gui

    win = main_gui.MainWindow()
    app.processEvents()
    tab = win.spectrum_tab
    index = win._spectrum_tab_index

    # ── 1. tab 注册与常驻可见 ──
    check("频谱图 tab 索引已注册", index >= 0)
    check("tab 标题为「频谱图」", win.tab_widget.tabText(index) == "频谱图")
    check("tab 图标非空", not win.tab_widget.tabIcon(index).isNull())
    always_visible = True
    for proto in (0, 6, 9, 11):
        win.protocol_combo.setCurrentIndex(proto)
        app.processEvents()
        if not win.tab_widget.isTabVisible(index):
            always_visible = False
    check("切换协议 0/6/9/11 后仍常驻可见", always_visible)

    # ── 2. 控件齐全 ──
    for attr in (
        "draw_btn", "paste_btn", "clear_btn", "export_btn", "auto_check",
        "trace_edit", "status_label", "axis_label", "canvas",
        "start_edit", "stop_edit", "center_edit", "span_edit", "freq_unit_combo",
        "rbw_edit", "rbw_unit_combo", "vbw_edit", "vbw_unit_combo",
        "ref_edit", "dbdiv_edit", "ydivs_spin", "unit_combo", "convert_check",
        "detector_combo",
    ):
        check(f"控件存在：{attr}", hasattr(tab, attr))

    # ── 3. 频率四字段双向联动 ──
    tab._write_freq_fields(240e6, 960e6, None, None)
    tab.start_edit.setText("300")
    tab._on_freq_edited("start")
    check(
        "改起始：终止/中心/扫宽联动",
        (tab.stop_edit.text(), tab.center_edit.text(), tab.span_edit.text())
        == ("1020", "660", "720"),
        f"{tab.stop_edit.text()}/{tab.center_edit.text()}/{tab.span_edit.text()}",
    )
    tab.center_edit.setText("500")
    tab._on_freq_edited("center")
    check(
        "改中心：起始/终止按扫宽重算",
        (tab.start_edit.text(), tab.stop_edit.text()) == ("140", "860"),
        f"{tab.start_edit.text()}/{tab.stop_edit.text()}",
    )
    tab.freq_unit_combo.setCurrentText("GHz")
    check(
        "切到 GHz：四字段数值换算",
        (tab.start_edit.text(), tab.stop_edit.text(), tab.span_edit.text())
        == ("0.14", "0.86", "0.72"),
        f"{tab.start_edit.text()}/{tab.stop_edit.text()}/{tab.span_edit.text()}",
    )
    tab.freq_unit_combo.setCurrentText("MHz")
    tab._write_freq_fields(240e6, 960e6, None, None)
    tab.span_edit.setText("-1")
    tab._on_freq_edited("span")
    check(
        "扫宽非法时拒绝联动并提示",
        tab.status_label.text().startswith("⚠") and tab.start_edit.text() == "240",
        f"{tab.status_label.text()} / start={tab.start_edit.text()}",
    )
    tab._write_freq_fields(240e6, 960e6, None, None)

    # ── 4. 绘制 ──
    tab.rbw_edit.setText("100")
    tab.trace_edit.setPlainText(_sample_text(100))
    tab._on_draw()
    trace = tab.current_trace()
    check("绘制后 trace 点数 = 100", trace is not None and trace.n_points == 100)
    check("状态行含点数", "点数 100" in tab.status_label.text(), tab.status_label.text())
    check(
        "状态行含频率步进 7.27273 MHz",
        "频率步进 7.27273 MHz" in tab.status_label.text(),
        tab.status_label.text(),
    )
    check(
        "频率轴端点 = 参数起止",
        trace is not None
        and abs(trace.freqs[0] - 240e6) < 1e-6
        and abs(trace.freqs[-1] - 960e6) < 1e-6,
    )

    # ── 5. 非法输入 ──
    tab.trace_edit.setPlainText("12a3 5")
    tab._on_draw()
    check("非法 token 报「第 1 项」", "第 1 项" in tab.status_label.text(), tab.status_label.text())
    check("非法输入不破坏已有图形", tab.current_trace() is not None)
    check("非法输入状态为错误色", tab._status_error is True)
    tab.trace_edit.setPlainText(_sample_text(100))
    tab._on_draw()

    # ── 6. 纵轴自动适配 ──
    before = tab.axis_label.text()
    tab.auto_check.setChecked(True)
    after = tab.axis_label.text()
    check("自动适配改变纵轴口径", before != after and "自动适配" in after, f"{before} -> {after}")
    check("自动适配下无越界提示", "超出纵轴范围" not in tab.status_label.text(), tab.status_label.text())
    tab.auto_check.setChecked(False)
    check("取消自动适配回到参考电平口径", "参考电平口径" in tab.axis_label.text())

    # ── 7. 单位换算 ──
    raw_levels = tab.current_trace().levels
    tab.unit_combo.setCurrentText("dBμV")
    tab.convert_check.setChecked(True)
    tab._on_draw()
    converted = tab.current_trace().levels
    check(
        "50Ω 换算 +107 dB",
        abs(converted[0] - (raw_levels[0] + 107.0)) < 1e-6,
        f"{raw_levels[0]} -> {converted[0]}",
    )
    tab.convert_check.setChecked(False)
    tab._on_draw()
    check(
        "不勾选换算数值不变（仅标注）",
        abs(tab.current_trace().levels[0] - raw_levels[0]) < 1e-6,
    )
    tab.unit_combo.setCurrentText("dBm")

    # ── 8. 渲染与导出 ──
    image = tab.canvas.render_image(1600, 1000)
    check("渲染尺寸 1600×1000", image.width() == 1600 and image.height() == 1000)
    check("渲染非纯色（网格+迹线）", _distinct_colors(image) > 3, str(_distinct_colors(image)))
    tmpdir = tempfile.mkdtemp(prefix="spectrum_gui_")
    png = os.path.join(tmpdir, "spectrum.png")
    check("导出 PNG 返回成功", tab._save_png(png) is True)
    check("PNG 文件已生成", os.path.exists(png) and os.path.getsize(png) > 0)
    loaded = QImage(png)
    check("PNG 可读回且尺寸正确", not loaded.isNull() and loaded.width() == 1600)
    check("导出后状态行提示路径", "已导出" in tab.status_label.text(), tab.status_label.text())

    # ── 9. 主题 ──
    tab.restyle_for_theme(True)
    check("暗色主题迹线色", tab.canvas._palette["trace"] == "#FFD54F", tab.canvas._palette["trace"])
    check("暗色主题背景色", tab._palette["bg"] == "#1E1E1E")
    dark_colors = _distinct_colors(tab.canvas.render_image(800, 500))
    check("暗色主题渲染非纯色", dark_colors > 3, str(dark_colors))
    tab.restyle_for_theme(False)
    check("浅色主题迹线色", tab.canvas._palette["trace"] == "#1E88E5")
    try:
        win._restyle_for_theme()
        hook_ok = True
    except Exception as exc:  # noqa: BLE001
        hook_ok = False
        print(f"    异常：{type(exc).__name__}: {exc}")
    check("主窗口主题钩子调用不抛异常", hook_ok)

    # ── 10. 清空 ──
    tab._on_clear()
    check("清空后无 trace", tab.current_trace() is None)
    check("清空后状态复位", tab.status_label.text() == "就绪", tab.status_label.text())
    empty_image = tab.canvas.render_image(600, 400)
    check("清空后仍可渲染（空态提示）", _distinct_colors(empty_image) > 1)

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项 / 通过 {PASS} 项：")
        for name in FAILURES:
            print(f"  - {name}")
        os._exit(1)
    print(f"全部测试通过（{PASS} 项）✓")
    os._exit(0)


if __name__ == "__main__":
    main()
