# -*- coding: utf-8 -*-
"""频谱图纯逻辑层测试（无 Qt）

覆盖 spectrum_widget.py 前半纯逻辑层：
  1. trace 数值解析容错（分隔符/BOM/科学计数/非法 token）
  2. 频谱仪参数校验错误矩阵
  3. 频率轴与步进（等间隔、端点精确）
  4. 纵轴范围与刻度（仪器式参考电平口径 / 自动适配 / 退化输入）
  5. 横轴标签步长（落在网格线上）
  6. 格式化（频率/幅值/定点小数）与单位换算（50Ω）
  7. 起始/终止/中心/扫宽 四字段双向联动
  8. 越界点数与状态/注记文本

直接运行: python test/test_spectrum_model.py
"""

import _path_setup  # noqa: E402

import math

from spectrum_widget import (
    AUTO_Y_MARGIN,
    DEFAULT_DB_PER_DIV,
    DEFAULT_REF_LEVEL_DB,
    DEFAULT_Y_DIVS,
    LEVEL_UNITS,
    MARKER_MAX_POINTS,
    MAX_MARKERS,
    MIN_DB_PER_DIV,
    MAX_DB_PER_DIV,
    MIN_Y_DIVS,
    MAX_Y_DIVS,
    PEAK_MIN_PROMINENCE_DB,
    SpectrumInputError,
    SpectrumParams,
    X_DIVS,
    auto_tick_decimals,
    axis_range_text,
    build_trace,
    count_out_of_range,
    delta_pair_index,
    delta_text,
    display_levels,
    extremes_text,
    extreme_points,
    format_delta_hz,
    format_delta_level,
    format_fixed,
    format_hz,
    format_level,
    freqs_for,
    marker_color,
    marker_rows,
    markers_for,
    nearest_index,
    next_peak_index,
    note_text,
    parse_levels,
    peak_index,
    peak_indices,
    readout_text,
    resolve_freq_inputs,
    status_text,
    to_freq_unit,
    units_to_hz,
    validate_params,
    valley_index,
    x_tick_labels,
    x_tick_stride,
    y_range,
    y_ticks,
)

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


def raises(fn, keyword=""):
    """返回 (是否抛错, 消息)"""
    try:
        fn()
    except SpectrumInputError as exc:
        msg = str(exc)
        return (not keyword or keyword in msg), msg
    except Exception as exc:  # 非 SpectrumInputError 视为失败
        return False, f"wrong-exception:{type(exc).__name__}:{exc}"
    return False, "no-exception"


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


def base_params(**kw):
    data = dict(start_hz=240e6, stop_hz=960e6)
    data.update(kw)
    return SpectrumParams(**data)


# ── 1. trace 数值解析 ─────────────────────────────────────────────

def test_parse_levels():
    check(
        "空格/逗号/分号/制表/换行混排",
        parse_levels("1 2,3;4\t5\n6") == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
    )
    check(
        "中文全角分隔符（，、）",
        parse_levels("1，2、3　4") == (1.0, 2.0, 3.0, 4.0),
        str(parse_levels("1，2、3　4")),
    )
    check("BOM 与首尾空白", parse_levels("\ufeff -1.5 \n 2.5 \n") == (-1.5, 2.5))
    check("正号与科学计数", parse_levels("+1e2 -2.5E-1") == (100.0, -0.25))

    ok, msg = raises(lambda: parse_levels(""), "请输入")
    check("空文本报错", ok, msg)
    ok, msg = raises(lambda: parse_levels("   ,;\n"), "请输入")
    check("全分隔符报错", ok, msg)
    ok, msg = raises(lambda: parse_levels("12a3 5"), "第 1 项")
    check("非法 token 报序号", ok, msg)
    ok, msg = raises(lambda: parse_levels("1 2 xx"), "第 3 项")
    check("非法 token 序号正确", ok and "xx" in msg, msg)
    ok, msg = raises(lambda: parse_levels("1 inf"), "第 2 项")
    check("拒绝 inf", ok, msg)
    ok, msg = raises(lambda: parse_levels("1 nan"), "第 2 项")
    check("拒绝 nan", ok, msg)


# ── 2. 参数校验错误矩阵 ───────────────────────────────────────────

def test_validate_params():
    validate_params(base_params())  # 合法参数不抛错
    check("合法参数通过校验", True)

    cases = [
        ("起始频率为 0", base_params(start_hz=0.0), "起始频率"),
        ("起始频率为负", base_params(start_hz=-1e6), "起始频率"),
        ("终止频率 ≤ 起始频率", base_params(stop_hz=240e6), "终止频率必须大于"),
        ("参考电平 NaN", base_params(ref_level_db=float("nan")), "参考电平"),
        ("每格 dB 过小", base_params(db_per_div=MIN_DB_PER_DIV / 2), "每格 dB"),
        ("每格 dB 过大", base_params(db_per_div=MAX_DB_PER_DIV * 2), "每格 dB"),
        ("纵向格数过小", base_params(y_divs=MIN_Y_DIVS - 1), "纵向格数"),
        ("纵向格数过大", base_params(y_divs=MAX_Y_DIVS + 1), "纵向格数"),
        ("未知单位", base_params(unit="dBW"), "单位"),
        ("RBW 为 0", base_params(rbw_hz=0.0), "RBW"),
        ("VBW 为负", base_params(vbw_hz=-1.0), "VBW"),
        ("未知检波方式", base_params(detector="花样检波"), "检波方式"),
    ]
    for name, params, keyword in cases:
        ok, msg = raises(lambda p=params: validate_params(p), keyword)
        check(f"校验拒绝：{name}", ok, msg)


# ── 3. 频率轴 ────────────────────────────────────────────────────

def test_freqs():
    params = base_params()
    freqs = freqs_for(params, 100)
    check("频率轴点数", len(freqs) == 100)
    check("频率轴起点 = 起始频率", close(freqs[0], 240e6))
    check("频率轴终点 = 终止频率", close(freqs[-1], 960e6))
    check("频率步进 = span/(N-1)", close(params.step_hz(100), 720e6 / 99))
    check("相邻点间隔一致", close(freqs[1] - freqs[0], freqs[50] - freqs[49]))
    check("单点无法成轴", raises(lambda: freqs_for(params, 1), "至少需要 2 个")[0])
    check("step_hz(N<2) 为 None", params.step_hz(1) is None)


def test_build_trace():
    trace = build_trace("1 2 3", base_params())
    check("build_trace 点数", trace.n_points == 3)
    check("build_trace 频率轴自洽", close(trace.freqs[1], 240e6 + 360e6))
    check("build_trace 幅值原样（无换算）", trace.levels == (1.0, 2.0, 3.0))
    ok, msg = raises(lambda: build_trace("1", base_params()), "至少需要 2 个")
    check("单点报错", ok, msg)
    ok, msg = raises(lambda: build_trace("1 2", base_params(stop_hz=1.0)), "终止频率必须大于")
    check("参数非法时不解析数值（先校验）", ok, msg)


# ── 4. 纵轴范围与刻度 ────────────────────────────────────────────

def test_y_axis():
    params = base_params()
    top, bottom = y_range(params, (), False)
    check("仪器式：顶 = 参考电平", close(top, DEFAULT_REF_LEVEL_DB))
    check(
        "仪器式：底 = 参考电平 - 每格 × 格数",
        close(bottom, DEFAULT_REF_LEVEL_DB - DEFAULT_DB_PER_DIV * DEFAULT_Y_DIVS),
    )

    levels = (-70.0, -55.0, -62.0)
    top_a, bottom_a = y_range(params, levels, True)
    check("自动：上界 = max + 5%", close(top_a, -55.0 + 15.0 * AUTO_Y_MARGIN))
    check("自动：下界 = min - 5%", close(bottom_a, -70.0 - 15.0 * AUTO_Y_MARGIN))
    top_e, bottom_e = y_range(params, levels, True)
    check("自动模式忽略参考电平", not close(top_e, DEFAULT_REF_LEVEL_DB))

    flat = y_range(params, (-60.0, -60.0), True)
    check("自动：全等值不除零且有余量", close(flat[0], -59.0) and close(flat[1], -61.0))
    zero = y_range(params, (0.0, 0.0), True)
    check("自动：全 0 值余量兜底 1.0", close(zero[0], 1.0) and close(zero[1], -1.0))
    check("自动：无数据回落仪器式", y_range(params, (), True) == (top, bottom))

    ticks = y_ticks(params, (), False)
    check("仪器式刻度个数 = 格数 + 1", len(ticks) == DEFAULT_Y_DIVS + 1)
    check("仪器式刻度首值 = 参考电平", close(ticks[0], DEFAULT_REF_LEVEL_DB))
    check(
        "仪器式刻度步长 = 每格 dB",
        all(close(ticks[i] - ticks[i + 1], DEFAULT_DB_PER_DIV) for i in range(len(ticks) - 1)),
    )
    custom = y_ticks(base_params(ref_level_db=-10.0, db_per_div=5.0, y_divs=4), (), False)
    check("自定义参数刻度", [round(v, 6) for v in custom] == [-10.0, -15.0, -20.0, -25.0, -30.0])


# ── 5. 横轴标签 ──────────────────────────────────────────────────

def test_x_ticks():
    check("标签多时每格标（step=1）", x_tick_stride(X_DIVS + 1) == 1)
    check("标签适中时隔格标（step=2）", x_tick_stride(6) == 2)
    check("标签少时间隔放大", x_tick_stride(3) in (2, 5))
    params = base_params()
    labels = x_tick_labels(params, 6)
    check("标签数不超过上限", len(labels) <= 6, str(labels))
    check("标签落在格线上", all(0 <= div <= X_DIVS for div, _ in labels))
    check("首标签 = 起始频率", labels[0][0] == 0 and labels[0][1] == "240 MHz", str(labels[0]))
    check("末标签 = 终止频率", labels[-1][0] == X_DIVS and labels[-1][1] == "960 MHz", str(labels[-1]))
    every = x_tick_labels(params, X_DIVS + 1)
    check("全格标签含 11 个刻度", len(every) == X_DIVS + 1, str(len(every)))


# ── 6. 格式化与单位换算 ──────────────────────────────────────────

def test_format():
    check("format_hz 240MHz", format_hz(240e6) == "240 MHz", format_hz(240e6))
    check("format_hz GHz", format_hz(1e9) == "1 GHz", format_hz(1e9))
    check("format_hz kHz", format_hz(2.5e3) == "2.5 kHz", format_hz(2.5e3))
    check("format_hz Hz", format_hz(125.0) == "125 Hz", format_hz(125.0))
    check("format_hz 步进", format_hz(720e6 / 99) == "7.27273 MHz", format_hz(720e6 / 99))
    check("format_level 整数", format_level(-20.0) == "-20", format_level(-20.0))
    check("format_level 带单位", format_level(-20.0, "dBm") == "-20 dBm")
    check("format_fixed 定点", format_fixed(47.3275, 1) == "47.3", format_fixed(47.3275, 1))
    check("auto_tick_decimals 步长 10", auto_tick_decimals(10.0) == 0)
    check("auto_tick_decimals 步长 1.84", auto_tick_decimals(1.8425) == 1)
    check("auto_tick_decimals 步长 0.05", auto_tick_decimals(0.05) == 3)
    check("units_to_hz", close(units_to_hz(240.0, "MHz"), 240e6))
    check("to_freq_unit", close(to_freq_unit(240e6, "MHz"), 240.0))
    check("未知频率单位报错", raises(lambda: units_to_hz(1.0, "THz"), "未知频率单位")[0])


def test_unit_conversion():
    levels = (-70.0, -60.0)
    check("dBm 不换算", display_levels(levels, base_params(unit="dBm", convert_50ohm=True)) == levels)
    check(
        "dBμV = dBm + 107",
        display_levels(levels, base_params(unit="dBμV", convert_50ohm=True)) == (37.0, 47.0),
    )
    check(
        "dBmV = dBm + 47",
        display_levels(levels, base_params(unit="dBmV", convert_50ohm=True)) == (-23.0, -13.0),
    )
    check(
        "不勾选换算则原样（仅改标注）",
        display_levels(levels, base_params(unit="dBμV", convert_50ohm=False)) == levels,
    )
    trace = build_trace("-70 -60", base_params(unit="dBμV", convert_50ohm=True))
    check("build_trace 应用换算", trace.levels == (37.0, 47.0))
    check("单位列表完整", set(LEVEL_UNITS) == {"dBm", "dBμV", "dBmV"})


# ── 7. 四字段双向联动 ────────────────────────────────────────────

def test_resolve_freq():
    got = resolve_freq_inputs("start", 300e6, 0.0, 0.0, 720e6)
    check("改起始：保留扫宽，重算终止/中心",
          [round(v) for v in got] == [300e6, 1020e6, 660e6, 720e6], str(got))

    got = resolve_freq_inputs("stop", 240e6, 840e6, 0.0, 0.0)
    check("改终止：重算中心/扫宽",
          [round(v) for v in got] == [240e6, 840e6, 540e6, 600e6], str(got))

    got = resolve_freq_inputs("center", 0.0, 0.0, 600e6, 720e6)
    check("改中心：保留扫宽，重算起止",
          [round(v) for v in got] == [240e6, 960e6, 600e6, 720e6], str(got))

    got = resolve_freq_inputs("span", 0.0, 0.0, 600e6, 100e6)
    check("改扫宽：保留中心，重算起止",
          [round(v) for v in got] == [550e6, 650e6, 600e6, 100e6], str(got))

    ok, msg = raises(lambda: resolve_freq_inputs("span", 0, 0, 600e6, -1.0), "扫宽必须为正数")
    check("扫宽为负被拒", ok, msg)
    ok, msg = raises(lambda: resolve_freq_inputs("start", 240e6, 0, 0, 0.0), "扫宽必须为正数")
    check("扫宽为 0 被拒", ok, msg)
    ok, msg = raises(lambda: resolve_freq_inputs("center", 0, 0, 50e6, 200e6), "非正")
    check("中心/扫宽组合得到负频率被拒", ok, msg)
    ok, msg = raises(lambda: resolve_freq_inputs("bogus", 1, 2, 3, 4), "未知的频率字段")
    check("未知字段报错", ok, msg)


# ── 8. 越界点数与文本 ────────────────────────────────────────────

def test_reports():
    params = base_params()
    levels = (-150.0, -70.0, -60.0, 5.0)
    check("越界点数（仪器式 -20 ~ -100）", count_out_of_range(params, levels, False) == 2)
    check("自动适配下无越界", count_out_of_range(params, levels, True) == 0)
    check("空数据无越界", count_out_of_range(params, (), False) == 0)

    trace = build_trace(" ".join(["-70"] * 100), base_params(rbw_hz=100e3))
    text = status_text(trace)
    check("状态含点数", "点数 100" in text, text)
    check("状态含频率步进", "频率步进 7.27273 MHz" in text, text)
    check("状态含扫宽", "扫宽 720 MHz" in text, text)
    check("状态含 RBW", "RBW 100 kHz" in text, text)

    note = note_text(base_params(rbw_hz=100e3, vbw_hz=10e3), 100)
    for fragment in ("起始 240 MHz", "终止 960 MHz", "扫宽 720 MHz", "RBW 100 kHz",
                     "VBW 10 kHz", "检波 峰值", "参考电平 -20 dBm", "10 dB/格 × 8 格",
                     "点数 100"):
        check(f"注记含「{fragment}」", fragment in note, note)

    axis = axis_range_text(base_params(), (-70.0, -60.0), False)
    check("纵轴文本（仪器式）", "-20 ~ -100 dBm" in axis and "参考电平口径" in axis, axis)
    axis_auto = axis_range_text(base_params(), (-70.0, -60.0), True)
    check("纵轴文本（自动适配）", "自动适配" in axis_auto, axis_auto)


def test_measure_markers():
    trace = build_trace(" ".join(str(-70 + i % 5) for i in range(20)), base_params())
    check("nearest_index 精确命中", nearest_index(trace.freqs, trace.freqs[7]) == 7)
    check("nearest_index 就近吸附", nearest_index(trace.freqs, 300e6) == 2, str(nearest_index(trace.freqs, 300e6)))
    check("nearest_index 下越界夹到首点", nearest_index(trace.freqs, 1.0) == 0)
    check("nearest_index 上越界夹到末点", nearest_index(trace.freqs, 9e9) == 19)
    check("nearest_index 单点轴返回 0", nearest_index((5.0,), 1e9) == 0)
    check(
        "nearest_index 非等间隔轴也正确（二分）",
        nearest_index((0.0, 100.0, 101.0, 102.0), 100.0) == 1,
        str(nearest_index((0.0, 100.0, 101.0, 102.0), 100.0)),
    )
    check(
        "nearest_index 正中间取靠前索引",
        nearest_index((0.0, 10.0, 20.0), 5.0) == 0,
        str(nearest_index((0.0, 10.0, 20.0), 5.0)),
    )
    ok, msg = raises(lambda: nearest_index((), 1.0), "可吸附")
    check("nearest_index 空轴报错", ok, msg)

    markers = markers_for(trace, (300e6, 1e12, 900e6))
    check("markers_for 越界丢弃", len(markers) == 2, str(markers))
    check("markers_for 顺序重编号", [m.label for m in markers] == ["M1", "M2"])
    check("markers_for 频率吸附到数据点", markers[0].freq_hz == trace.freqs[2])
    check("markers_for 幅值取该点", markers[0].level == trace.levels[2])
    check("markers_for 空输入返回空", markers_for(trace, ()) == ())
    check("markers_for 非有限值丢弃", markers_for(trace, (float("nan"),)) == ())

    rows = marker_rows(markers)
    check("标记表 M1 行为参考", rows[0][3] == "参考" and rows[0][4] == "参考", str(rows[0]))
    check(
        "标记表 M2 行 Δ 带「哪两点」标注",
        rows[1][3] == f"M1↔M2  {format_delta_hz(markers[1].freq_hz - markers[0].freq_hz)}",
        str(rows[1]),
    )
    check(
        "标记表 M2 行 Δ幅值带标注",
        rows[1][4] == f"M1↔M2  {format_delta_level(markers[1].level - markers[0].level)}",
        str(rows[1]),
    )
    rows_ref2 = marker_rows(markers, ref_index=1)
    check("参考标记改为 M2 时该行显示参考", rows_ref2[1][3] == "参考", str(rows_ref2[1]))
    check(
        "参考标记改为 M2 时 M1 行标注 M2↔M1 且符号相反",
        rows_ref2[0][3]
        == f"M2↔M1  {format_delta_hz(markers[0].freq_hz - markers[1].freq_hz)}",
        str(rows_ref2[0]),
    )
    check("参考下标越界回落 M1", marker_rows(markers, ref_index=99)[1][3].startswith("M1↔M2"))

    check("两点下标对默认 M1→M2", delta_pair_index(markers) == (0, 1))
    check("参考为最后一个标记时取前一个", delta_pair_index(markers, 1) == (1, 0))
    check("标记不足两个返回 None", delta_pair_index(markers[:1]) is None)
    check("参考下标越界回落第一个", delta_pair_index(markers, 7) == (0, 1))
    check("单标记无 Δ 文案", delta_text(markers[:1]) == "")
    delta = delta_text(markers)
    check("Δ 文案含频段宽度", "Δf(M1↔M2)" in delta and "Δlevel" in delta, delta)
    three = markers_for(trace, (300e6, 600e6, 900e6))
    check("参考为中间标记时取其后一个", delta_pair_index(three, 1) == (1, 2))
    check(
        "Δ 文案带自定义参考（标注哪两点）",
        "Δf(M2↔M3)" in delta_text(three, 1),
        delta_text(three, 1),
    )
    check(
        "参考为最后一个标记时标注前一个",
        "Δf(M3↔M2)" in delta_text(three, 2),
        delta_text(three, 2),
    )

    check(
        "标记颜色 M1~M6 互不相同",
        len({marker_color(True, i) for i in range(MAX_MARKERS)}) == MAX_MARKERS,
    )
    check(
        "标记颜色浅/暗主题不同",
        all(marker_color(True, i) != marker_color(False, i) for i in range(MAX_MARKERS)),
    )
    check("M1 颜色稳定（暗色 #4FC3F7）", marker_color(True, 0) == "#4FC3F7", marker_color(True, 0))
    check("超出上限循环取色", marker_color(True, MAX_MARKERS) == marker_color(True, 0))
    check("Δ 频率带符号格式", format_delta_hz(-700e3) == "-700 kHz", format_delta_hz(-700e3))
    check("Δ 电平带符号格式", format_delta_level(-0.2) == "-0.20 dB", format_delta_level(-0.2))
    check(
        "读数文本含频率与幅值",
        readout_text(426261000.0, -51.0, "dBm") == "426.261 MHz   -51 dBm",
        readout_text(426261000.0, -51.0, "dBm"),
    )


def test_peak_search():
    levels = [0.0, 1.0, 0.0, 1.0, 0.0, 5.0, 0.0, 0.0, 4.0, 0.0]
    check("峰值索引取最大点", peak_index(levels) == 5)
    check("峰值并列取最靠前", peak_index([1.0, 3.0, 3.0]) == 1)
    ok, msg = raises(lambda: peak_index(()), "没有数据点")
    check("空数据搜索峰值报错", ok, msg)
    check("谷值索引取最小点", valley_index([5.0, 1.0, 3.0]) == 1)
    ok, msg = raises(lambda: valley_index(()), "没有数据点")
    check("空数据搜索谷值报错", ok, msg)

    check("局部峰：1 dB 峰被显著度过滤", peak_indices(levels) == (5, 8), str(peak_indices(levels)))
    check(
        "局部峰：低阈值时全部命中",
        peak_indices(levels, min_prominence_db=0.5) == (1, 3, 5, 8),
        str(peak_indices(levels, min_prominence_db=0.5)),
    )
    check("首尾点不作为峰（首点 9.0 虽为最大值）", peak_indices([9.0, 0.0, 5.0, 0.0]) == (2,))
    check("平坦数据无峰", peak_indices([3.0] * 8) == ())
    check("数据太短无峰", peak_indices([1.0, 2.0]) == ())

    check("下一个峰向右侧找", next_peak_index(levels, 5) == 8)
    check("下一个峰环形回到首个", next_peak_index(levels, 8) == 5)
    check("上一个峰向前找", next_peak_index(levels, 8, direction=-1) == 5)
    check("无峰时返回 None", next_peak_index([1.0] * 8, 3) is None)

    trace = build_trace(" ".join(str(v) for v in levels), base_params())
    high, low = extreme_points(trace)
    check("峰值点频率/幅值", high.index == 5 and high.level == 5.0 and high.freq_hz == trace.freqs[5])
    check("谷值点频率/幅值", low.index == 0 and low.level == 0.0 and low.freq_hz == trace.freqs[0])
    text = extremes_text(trace)
    check("极值摘要文本", "峰值" in text and "谷值" in text and "dBm" in text, text)


def main():
    for fn in (
        test_parse_levels,
        test_validate_params,
        test_freqs,
        test_build_trace,
        test_y_axis,
        test_x_ticks,
        test_format,
        test_unit_conversion,
        test_resolve_freq,
        test_reports,
        test_measure_markers,
        test_peak_search,
    ):
        print(f"\n── {fn.__name__} ──")
        fn()

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项 / 通过 {PASS} 项：")
        for name in FAILURES:
            print(f"  - {name}")
        raise SystemExit(1)
    print(f"全部测试通过（{PASS} 项）✓")


if __name__ == "__main__":
    main()
