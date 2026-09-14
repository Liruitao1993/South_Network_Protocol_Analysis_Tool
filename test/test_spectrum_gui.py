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
  8. 光标读数（悬停/移出/重绘清除）与 MARK 标记（点击添加/上限 6/峰值搜索/下一个峰值/删除/清空）
  9. 标记表内容、标记颜色与表格对应、Δ「哪两点」标注与参考切换、重绘后按频率保持
 10. 积分带宽：竖线/填充/短注记、积分功率精确值、越界与无交集、单位联动、关闭后与从未开启逐像素一致
 11. 渲染与导出（1600×1000、PNG 可读回、带标记渲染差异）
 12. 主题切换 restyle_for_theme 生效；主窗口 _restyle_for_theme 钩子不抛异常
 13. 清空复位

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
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QImage, QMouseEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    import main_gui
    import spectrum_widget
    from spectrum_widget import MAX_MARKERS, format_delta_hz, marker_color, peak_index

    check(
        "Qt 层导入成功（否则 SpectrumWidget 为 None）",
        spectrum_widget._QT_AVAILABLE,
        str(spectrum_widget._QT_IMPORT_ERROR),
    )

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

    # ── 8. 光标读数与 MARK 标记（R7 / R8）──
    tab.unit_combo.setCurrentText("dBm")
    tab._on_draw()
    canvas = tab.canvas
    trace = tab.current_trace()
    check("绘图区矩形可用", canvas.plot_rect() is not None and canvas.plot_rect().width() > 100)

    def _mouse(kind, x, y, button=Qt.MouseButton.NoButton):
        pos = QPointF(x, y)
        QApplication.sendEvent(
            canvas,
            QMouseEvent(
                kind, pos, pos, button, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier
            ),
        )
        app.processEvents()

    def _click_ratio(frac):
        """按当前绘图区（每次重取：标记表显隐会改变画布高度）点击。"""
        plot = canvas.plot_rect()
        _mouse(
            QEvent.Type.MouseButtonPress,
            plot.left() + int(plot.width() * frac),
            plot.center().y(),
            Qt.MouseButton.LeftButton,
        )

    def _hover_ratio(frac):
        plot = canvas.plot_rect()
        _mouse(
            QEvent.Type.MouseMove,
            plot.left() + int(plot.width() * frac),
            plot.center().y(),
        )

    # 无 trace 时悬停/点击不产生读数与标记（绘图区仍可算出，用于画空态提示）
    canvas.set_trace(None)
    empty_plot = canvas.plot_rect()
    check("无 trace 时仍可算出绘图区（空态提示用）", empty_plot is not None)
    _mouse(QEvent.Type.MouseMove, empty_plot.center().x(), empty_plot.center().y())
    check("无 trace 时悬停无读数", canvas.cursor_readout() is None)
    _mouse(
        QEvent.Type.MouseButtonPress,
        empty_plot.center().x(),
        empty_plot.center().y(),
        Qt.MouseButton.LeftButton,
    )
    check("无 trace 时点击不产生标记", tab.markers() == ())
    canvas.set_trace(trace)

    _hover_ratio(0.26)
    readout = canvas.cursor_readout()
    check("悬停产生光标读数", readout is not None)
    if readout is not None:
        index, freq, level = readout
        check(
            "读数 = 最近数据点的频率与幅值",
            freq == trace.freqs[index] and level == trace.levels[index],
            f"{freq}/{level} vs {trace.freqs[index]}/{trace.levels[index]}",
        )
        check(
            "读数与悬停位置对应（±1 步进）",
            abs(index - round(0.26 * (trace.n_points - 1))) <= 1,
            str(index),
        )
    _mouse(QEvent.Type.Leave, 0, 0)
    check("移出绘图区清除读数", canvas.cursor_readout() is None)

    # 重绘后不残留旧轨迹读数（D3：set_trace 清空光标）
    _hover_ratio(0.4)
    tab._on_draw()
    check("重绘后清除旧光标读数", canvas.cursor_readout() is None)

    check("初始无标记且标记表隐藏", tab.markers() == () and tab.marker_table.isHidden())
    _click_ratio(0.26)
    _click_ratio(0.57)
    check("点击两次 → 2 个标记", len(tab.markers()) == 2, str(len(tab.markers())))
    check("标记命名 M1/M2", [m.label for m in tab.markers()] == ["M1", "M2"])
    check("标记表显示且 2 行", not tab.marker_table.isHidden() and tab.marker_table.rowCount() == 2)
    check(
        "点击位点与标记频率一致（±1 步进）",
        abs(tab.markers()[0].index - round(0.26 * (trace.n_points - 1))) <= 1
        and abs(tab.markers()[1].index - round(0.57 * (trace.n_points - 1))) <= 1,
        f"{tab.markers()[0].index} / {tab.markers()[1].index}",
    )
    check(
        "标记表 M1 行为参考",
        tab.marker_table.item(0, 3).text() == "参考",
        tab.marker_table.item(0, 3).text(),
    )
    m1, m2 = tab.markers()
    check(
        "标记表 M2 行 Δ频率 = 两点频率差（带 M?↔M? 标注）",
        tab.marker_table.item(1, 3).text()
        == f"{m1.label}↔{m2.label}  {format_delta_hz(m2.freq_hz - m1.freq_hz)}",
        tab.marker_table.item(1, 3).text(),
    )
    check(
        "标记表行文字用该标记的颜色（M1/M2 不同色）",
        tab.marker_table.item(0, 3).foreground().color().name()
        != tab.marker_table.item(1, 3).foreground().color().name(),
        f"{tab.marker_table.item(0, 3).foreground().color().name()} vs "
        f"{tab.marker_table.item(1, 3).foreground().color().name()}",
    )
    check(
        "标记表颜色 = marker_color(主题, 序号)",
        tab.marker_table.item(0, 0).foreground().color().name().lower()
        == marker_color(tab._dark, 0).lower()
        and tab.marker_table.item(1, 0).foreground().color().name().lower()
        == marker_color(tab._dark, 1).lower(),
        f"{tab.marker_table.item(0, 0).foreground().color().name()} / "
        f"{tab.marker_table.item(1, 0).foreground().color().name()}",
    )
    check(
        "Δ 参考下拉列出全部标记",
        [tab.ref_combo.itemText(i) for i in range(tab.ref_combo.count())] == ["M1", "M2"],
        str([tab.ref_combo.itemText(i) for i in range(tab.ref_combo.count())]),
    )
    check(
        "测量栏含 Δf(M1↔M2) 频段宽度",
        "Δf(M1↔M2)" in tab.measure_label.text()
        and format_delta_hz(m2.freq_hz - m1.freq_hz) in tab.measure_label.text(),
        tab.measure_label.text(),
    )
    check("测量栏含峰值/谷值", "峰值" in tab.measure_label.text() and "谷值" in tab.measure_label.text())

    # 切换 Δ 参考为 M2 → Δ 列与测量栏都按 M2 重新标注
    tab.ref_combo.setCurrentIndex(1)
    check("切换参考后 M2 行变参考", tab.marker_table.item(1, 3).text() == "参考")
    check(
        "切换参考后 M1 行标注 M2↔M1",
        tab.marker_table.item(0, 3).text().startswith("M2↔M1"),
        tab.marker_table.item(0, 3).text(),
    )
    check("切换参考后测量栏显示 M2↔M1", "Δf(M2↔M1)" in tab.measure_label.text(), tab.measure_label.text())
    tab.ref_combo.setCurrentIndex(0)

    # 三个标记：颜色互不相同、Δ 标注各自成对
    _click_ratio(0.75)
    colors = [
        tab.marker_table.item(r, 0).foreground().color().name().lower()
        for r in range(tab.marker_table.rowCount())
    ]
    check("3 个标记颜色互不相同", len(set(colors)) == 3, str(colors))
    check(
        "M3 行 Δ 标注 M1↔M3",
        tab.marker_table.item(2, 3).text().startswith("M1↔M3"),
        tab.marker_table.item(2, 3).text(),
    )

    # 峰值搜索 / 下一个峰值（走真实按钮信号，覆盖 .clicked 接线）
    before_count = len(tab.markers())
    tab.peak_btn.click()
    peak_freq = trace.freqs[peak_index(trace.levels)]
    check(
        "峰值搜索把最后标记移到最大幅值点",
        abs(tab.markers()[-1].freq_hz - peak_freq) < 1e-6,
        f"{tab.markers()[-1].freq_hz} vs {peak_freq}",
    )
    before_index = tab.markers()[-1].index
    tab.next_peak_btn.click()
    check(
        "下一个峰值移动到另一个峰",
        tab.markers()[-1].index != before_index,
        str(tab.markers()[-1].index),
    )
    check(
        "标记数未增加（无选中即作用于最后一个）",
        len(tab.markers()) == before_count,
        f"{len(tab.markers())} vs {before_count}",
    )

    # 选中行分支：作用于选中行而非最后一个
    tab.marker_table.selectRow(0)
    app.processEvents()
    first_before = tab.markers()[0].index
    last_before = tab.markers()[-1].index
    tab.peak_btn.click()
    check(
        "有选中行时峰值搜索作用于选中行",
        tab.markers()[0].freq_hz == peak_freq and tab.markers()[-1].index == last_before,
        f"{tab.markers()[0].freq_hz} / {tab.markers()[-1].index} vs {last_before}",
    )

    # 删除中间标记 → 重新编号连续
    _click_ratio(0.9)
    count_before = len(tab.markers())
    tab.marker_table.selectRow(1)
    app.processEvents()
    tab.del_marker_btn.click()
    labels = [m.label for m in tab.markers()]
    check(
        "删除中间标记后剩余标记重新连续编号",
        len(labels) == count_before - 1 and labels == [f"M{i + 1}" for i in range(len(labels))],
        str(labels),
    )
    check("删除后表格行数同步", tab.marker_table.rowCount() == len(labels), str(tab.marker_table.rowCount()))

    # 收窄扫描范围 → 越界标记丢弃并提示，同时保留点数信息
    tab._write_freq_fields(360e6, 600e6, None, None)
    tab._on_draw()
    check(
        "越界标记被丢弃且提示仍保留点数信息",
        "已丢弃" in tab.status_label.text() and "点数" in tab.status_label.text(),
        tab.status_label.text(),
    )
    check(
        "丢弃后标记重编号连续",
        [m.label for m in tab.markers()] == [f"M{i + 1}" for i in range(len(tab.markers()))],
        str([m.label for m in tab.markers()]),
    )
    tab._write_freq_fields(240e6, 960e6, None, None)
    tab._on_draw()

    # 上限与六标记表格
    for frac in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        _click_ratio(frac)
    check("最多 6 个标记", len(tab.markers()) == MAX_MARKERS, str(len(tab.markers())))
    check("6 个标记时表格 6 行", tab.marker_table.rowCount() == MAX_MARKERS)
    check(
        "6 个标记颜色互不相同",
        len({tab.marker_table.item(r, 0).foreground().color().name() for r in range(6)}) == 6,
    )
    _click_ratio(0.8)
    check(
        f"第 {MAX_MARKERS + 1} 个标记被拒并提示",
        len(tab.markers()) == MAX_MARKERS and f"最多 {MAX_MARKERS} 个标记" in tab.status_label.text(),
        tab.status_label.text(),
    )

    # 重绘后标记按频率保持（单位换算 → 幅值随单位变化，频率不变）
    before = [(m.freq_hz, m.level) for m in tab.markers()]
    tab.unit_combo.setCurrentText("dBμV")
    tab.convert_check.setChecked(True)
    tab._on_draw()
    after = [(m.freq_hz, m.level) for m in tab.markers()]
    check("重绘后标记数量保持", len(after) == len(before))
    check(
        "重绘后标记频率保持（按频率锚定）",
        all(abs(a[0] - b[0]) < 1e-6 for a, b in zip(after, before)),
    )
    check(
        "重绘后标记幅值按新单位换算",
        abs(after[0][1] - (before[0][1] + 107.0)) < 1e-6,
        f"{before[0][1]} -> {after[0][1]}",
    )
    tab.convert_check.setChecked(False)
    tab.unit_combo.setCurrentText("dBm")
    tab._on_draw()

    # 只改表单参数不重绘 → 只读标签提示「点绘制生效」，与画布口径不同源被显式标注
    drawn_unit = tab.current_trace().params.unit
    tab.unit_combo.setCurrentText("dBμV")
    check(
        "改单位未重绘时标签提示需重新绘制",
        "点「绘制」生效" in tab.axis_label.text()
        and tab.current_trace().params.unit == drawn_unit,
        tab.axis_label.text(),
    )
    tab.unit_combo.setCurrentText("dBm")
    check("参数复位后提示消失", "点「绘制」生效" not in tab.axis_label.text(), tab.axis_label.text())

    tab.clear_markers_btn.click()
    check("清空标记后表隐藏且画布无标记", tab.marker_table.isHidden() and tab.markers() == ())

    # ── 9. 积分带宽（R10）──
    tab.ibw_check.setChecked(False)
    tab._refresh_integration()
    check("未启用时读数提示未启用", tab.ibw_label.text() == "未启用", tab.ibw_label.text())
    check("未启用时画布无积分带宽", canvas.integration_band() is None)

    # 常量 trace：积分功率可精确预期
    tab.trace_edit.setPlainText(" ".join(["-70"] * 101))
    tab.rbw_edit.setText("7200")
    tab.rbw_unit_combo.setCurrentText("kHz")
    tab._on_draw()
    # 同一 trace 下的「无积分带宽」基线（后续所有渲染对比都以此为准）
    same_trace_image = canvas.render_image(900, 560)
    never_on = bytes(same_trace_image.constBits())
    tab.ibw_center_edit.setText("600")
    tab.ibw_bw_edit.setText("720")
    tab.ibw_unit_combo.setCurrentText("MHz")
    tab.ibw_check.setChecked(True)
    app.processEvents()
    band = canvas.integration_band()
    check("积分带宽边沿 = 中心 ± 带宽/2", band is not None and (band.low_hz, band.high_hz) == (240e6, 960e6), str(band))
    expected = -70.0 + 10.0 * math.log10(101)
    check(
        "常量 trace 积分功率 = -70 + 10log10(101)",
        f"{round(expected, 4):g}" in tab.ibw_label.text(),
        tab.ibw_label.text(),
    )
    check("读数含点数与归一化口径", "101 点" in tab.ibw_label.text() and "按 RBW 归一化" in tab.ibw_label.text(), tab.ibw_label.text())

    # 两条竖线：带内像素与带外不同，且沿带宽聚类
    tab.ibw_center_edit.setText("600")
    tab.ibw_bw_edit.setText("200")
    tab._refresh_integration()
    app.processEvents()
    image = canvas.render_image(900, 560)
    check("启用后渲染与同 trace 无积分带宽基线不同", bytes(image.constBits()) != never_on)
    probe_plot = canvas.plot_rect(image.rect())

    def _pixel(freq_mhz):
        x = probe_plot.left() + int(
            probe_plot.width() * (freq_mhz * 1e6 - 240e6) / 720e6
        )
        return image.pixelColor(x, probe_plot.top() + 25).name()

    inside = _pixel(600)
    outside = _pixel(300)
    check("带宽内半透明填充生效", inside != outside, f"{inside} vs {outside}")
    edge_left = _pixel(500)
    check("左边沿处有竖线（像素与填充不同）", edge_left not in (inside, outside), edge_left)
    check(
        "边沿位置 = 500/700 MHz",
        abs(canvas.integration_band().low_hz - 500e6) < 1e-6
        and abs(canvas.integration_band().high_hz - 700e6) < 1e-6,
        str(canvas.integration_band()),
    )
    # z 序：填充在迹线之下（带内迹线像素不被压暗）
    tab.ibw_check.setChecked(False)
    app.processEvents()
    off_image = canvas.render_image(700, 420)
    tab.ibw_check.setChecked(True)
    tab.ibw_center_edit.setText("600")
    tab.ibw_bw_edit.setText("200")
    tab._refresh_integration()
    app.processEvents()
    on_image = canvas.render_image(700, 420)
    trace_color = spectrum_widget.palette_for(tab._dark)["trace"].lower()
    area = canvas.plot_rect(off_image.rect())

    def _count_trace_pixels(image):
        total = 0
        for py in range(area.top(), area.bottom()):
            for px in range(area.left(), area.right()):
                if image.pixelColor(px, py).name().lower() == trace_color:
                    total += 1
        return total

    check(
        "积分带宽填充在迹线之下（迹线像素数不变）",
        _count_trace_pixels(off_image) == _count_trace_pixels(on_image) > 0,
        f"{_count_trace_pixels(off_image)} vs {_count_trace_pixels(on_image)}",
    )
    # 窄带靠右缘：带内标签不得画到绘图区之外
    tab.ibw_center_edit.setText("950")
    tab.ibw_bw_edit.setText("20")
    tab._refresh_integration()
    app.processEvents()
    narrow_on = canvas.render_image(700, 420)
    tab.ibw_check.setChecked(False)
    app.processEvents()
    narrow_off = canvas.render_image(700, 420)
    outside_diff = 0
    for py in range(area.top(), area.bottom()):
        for px in range(area.right() + 2, min(area.right() + 100, narrow_on.width())):
            if narrow_on.pixelColor(px, py) != narrow_off.pixelColor(px, py):
                outside_diff += 1
    check("窄带靠右缘时 IBW 标签不越出绘图区", outside_diff == 0, str(outside_diff))
    tab.ibw_check.setChecked(True)
    tab.ibw_center_edit.setText("600")
    tab.ibw_bw_edit.setText("100")
    tab._refresh_integration()

    # 越界与无交集
    tab.ibw_center_edit.setText("240")
    tab.ibw_bw_edit.setText("400")
    tab._refresh_integration()
    check("带宽越界时读数提示按交集积分", "超出扫描范围" in tab.ibw_label.text(), tab.ibw_label.text())
    tab.ibw_center_edit.setText("5000")
    tab.ibw_bw_edit.setText("100")
    tab._refresh_integration()
    check("与扫描范围无交集时读数提示", "无交集" in tab.ibw_label.text(), tab.ibw_label.text())
    empty_image = canvas.render_image(900, 560)
    tab.ibw_check.setChecked(False)
    app.processEvents()
    check("关闭积分带宽后画布不再持有积分带宽", canvas.integration_band() is None)
    disabled_image = canvas.render_image(900, 560)
    # 读数框（右上角，含 ⚠ 无交集提示）属预期差异；先比对绘图区内部像素
    probe_area = canvas.plot_rect(empty_image.rect())
    probe_x = probe_area.left() + int(probe_area.width() * 0.1)
    probe_y = probe_area.bottom() - 8
    check(
        "无交集时不绘制竖线/填充（绘图区像素与关闭态一致）",
        empty_image.pixelColor(probe_x, probe_y).name()
        == disabled_image.pixelColor(probe_x, probe_y).name(),
        f"{empty_image.pixelColor(probe_x, probe_y).name()} vs "
        f"{disabled_image.pixelColor(probe_x, probe_y).name()}",
    )
    # 强不变量：同一 trace 下「从未开启」与「开启后再关闭」必须逐像素一致
    again_image = canvas.render_image(900, 560)
    check(
        "开启后再关闭 = 从未开启（同 trace 逐像素一致）",
        bytes(again_image.constBits()) == never_on,
    )

    # 单位切换同步换算中心频率
    tab.ibw_center_edit.setText("600")
    tab.freq_unit_combo.setCurrentText("GHz")
    check("切到 GHz 后积分带宽中心频率同步换算", tab.ibw_center_edit.text() == "0.6", tab.ibw_center_edit.text())
    tab.freq_unit_combo.setCurrentText("MHz")

    tab._on_draw()
    tab.ibw_check.setChecked(True)
    tab.ibw_center_edit.setText("600")
    tab.ibw_bw_edit.setText("100")
    tab.ibw_unit_combo.setCurrentText("MHz")
    tab._refresh_integration()
    app.processEvents()
    marked_ibw = canvas.render_image(800, 500)
    _click_ratio(0.3)
    with_marker = canvas.render_image(800, 500)
    check(
        "积分带宽与标记可同屏共存（渲染继续变化）",
        bytes(with_marker.constBits()) != bytes(marked_ibw.constBits()),
        f"markers={len(tab.markers())} trace={tab.current_trace() is not None} "
        f"band={canvas.integration_band() is not None}",
    )
    tab.clear_markers_btn.click()
    tab._on_clear()
    check("清空 trace 后积分带宽读数回到未启用/未绘制", canvas.integration_band() is None, str(canvas.integration_band()))
    check("清空后读数标签更新", tab.ibw_label.text() in ("未启用", "未绘制 trace"), tab.ibw_label.text())
    tab.ibw_check.setChecked(False)

    # ── 11. 日志文本预处理（R11）──
    log_values = ["-51.564613", "-52.085311", "-52.614507", "-52.901395", "-52.524243"]
    log_text = "\n".join(
        "2026-09-14 12:25:43 {:03d}: 流程日志：2026-09-14 12:24:26:295 "
        "--USER--MTC@DESKTOP-417FFS5: {}".format(i, v)
        for i, v in enumerate(log_values)
    )
    tab.ibw_check.setChecked(False)
    tab.trace_edit.setPlainText(log_text)
    tab._on_draw()
    log_trace = tab.current_trace()
    check("日志行可绘制（点数 = 行数）", log_trace is not None and log_trace.n_points == 5)
    check(
        "日志行取行尾数值",
        log_trace is not None
        and log_trace.levels == tuple(float(v) for v in log_values),
        str(log_trace.levels if log_trace else None),
    )
    check(
        "状态行提示已清洗日志行",
        "已清洗 5 行日志" in tab.status_label.text(),
        tab.status_label.text(),
    )
    mixed_text = "流程日志：开始采集\n" + log_text + "\n2026-09-14 12:24:26:295\n-60 -61"
    tab.trace_edit.setPlainText(mixed_text)
    tab._on_draw()
    mixed_trace = tab.current_trace()
    check("混合输入点数正确（5 日志 + 2 纯值）", mixed_trace is not None and mixed_trace.n_points == 7)
    check(
        "混合输入状态行同时提示清洗与跳过",
        "已清洗 5 行日志" in tab.status_label.text()
        and "跳过 2 行无数值" in tab.status_label.text(),
        tab.status_label.text(),
    )
    tab.trace_edit.setPlainText(_sample_text(100))
    tab._on_draw()
    check(
        "纯数值输入不显示清洗提示",
        "已清洗" not in tab.status_label.text(),
        tab.status_label.text(),
    )
    # 切换「纵轴自动适配」不应吞掉清洗提示
    tab.trace_edit.setPlainText(log_text)
    tab._on_draw()
    tab.auto_check.setChecked(True)
    check(
        "切换自动适配后清洗提示仍在",
        "已清洗 5 行日志" in tab.status_label.text(),
        tab.status_label.text(),
    )
    tab.auto_check.setChecked(False)
    check(
        "取消自动适配后清洗提示仍在",
        "已清洗 5 行日志" in tab.status_label.text(),
        tab.status_label.text(),
    )
    # 日志行有值但行尾非数值 → 明确报错（不静默丢行）
    tab.trace_edit.setPlainText("-70 -71\n2026-09-14 12:00:00 INFO: -51.5 dBm extra")
    tab._on_draw()
    check(
        "日志行无法确定数值时报错并指出行号",
        "第 2 行" in tab.status_label.text() and "无法确定 trace 值" in tab.status_label.text(),
        tab.status_label.text(),
    )
    check("报错时不破坏已有图形", tab.current_trace() is not None)
    tab.trace_edit.setPlainText(_sample_text(100))
    tab._on_draw()

    # ── 12. 渲染与导出 ──
    tab.trace_edit.setPlainText(_sample_text(100))  # 上一节清空过 trace，这里恢复
    tab.unit_combo.setCurrentText("dBm")
    tab.rbw_edit.setText("100")
    tab.rbw_unit_combo.setCurrentText("kHz")
    tab._on_draw()
    tab._on_clear_markers()
    image_plain = canvas.render_image(800, 500)
    plain = bytes(image_plain.constBits())  # 必须持有 QImage 引用：临时对象上取 constBits 会崩
    _click_ratio(0.26)
    _click_ratio(0.57)
    image_marked = canvas.render_image(800, 500)
    marked = bytes(image_marked.constBits())
    check("带标记导出图与无标记不同（标记/Δ 注记已渲染）", plain != marked)
    tab._on_clear_markers()
    image_again = canvas.render_image(800, 500)
    plain2 = bytes(image_again.constBits())
    check("清除标记后恢复与无标记一致", plain == plain2)
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
