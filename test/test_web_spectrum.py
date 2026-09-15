# -*- coding: utf-8 -*-
"""Web 频谱图回归测试（任务 09-15-web-spectrum-plot）

覆盖：
  1. 「复用桌面纯逻辑层」守卫：Web 进程（无 PySide6）能 import spectrum_widget
     并完成 build_trace（Qt 层被守护导入 → 预期不可用）
  2. spectrum_web 纯几何：坐标换算往返、越界裁剪、网格条数、标签首末贴边、
     点击带中心频率、积分带求交/无交集
  3. SpectrumState 端到端（真实 reflex State 实例）：绘制、频率四字段联动、
     单位换算、点击加标记、峰值搜索、Δ 参考、积分带宽、错误路径保留旧图
  4. 组件树可构建（index() 含频谱图 tab）

直接运行: PYTHONIOENCODING=utf-8 python test/test_web_spectrum.py
"""

import _path_setup  # noqa: E402

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reflex_web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

PASS = 0
FAILURES = []

TRACE_101 = " ".join(["-70"] * 101)
TRACE_PEAK = " ".join(
    ["-70"] * 40 + ["-30"] + ["-70"] * 40 + ["-55"] + ["-70"] * 19
)


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


# ═══════════════════════════════════════════════════════════════
# 1. 复用守卫
# ═══════════════════════════════════════════════════════════════

def test_reuse_guard():
    print("\n[1] 复用桌面纯逻辑层（Web 无 PySide6）")
    try:
        import spectrum_widget as sw
    except Exception as e:  # noqa: BLE001
        check("import spectrum_widget", False, f"{type(e).__name__}: {e}")
        return
    check("import spectrum_widget 成功（Qt 层被守护）", True)
    params = sw.SpectrumParams(start_hz=240e6, stop_hz=960e6)
    trace = sw.build_trace(TRACE_101, params)
    check("纯逻辑可出图（101 点）", trace.n_points == 101, str(trace.n_points))
    check("频率轴等间隔", abs((trace.freqs[1] - trace.freqs[0]) - 7.2e6) < 1e6,
          f"{trace.freqs[1] - trace.freqs[0]:.3e}")
    check("标记吸附到最近点",
          sw.markers_for(trace, [600e6])[0].freq_hz == 600e6,
          str(sw.markers_for(trace, [600e6])[0].freq_hz))
    check("M1/M2 配色不同",
          sw.marker_color(False, 0) != sw.marker_color(False, 1))


# ═══════════════════════════════════════════════════════════════
# 2. spectrum_web 几何
# ═══════════════════════════════════════════════════════════════

def test_geometry():
    print("\n[2] spectrum_web 几何（纯函数）")
    from reflex_web import spectrum_web as g
    from spectrum_widget import SpectrumParams, build_trace, markers_for

    params = SpectrumParams(start_hz=240e6, stop_hz=960e6)
    trace = build_trace(TRACE_101, params)

    check("绘图区矩形", g.plot_rect() == (76, 46, 964, 540), str(g.plot_rect()))
    check("左端频率贴左框", g.x_for_freq(240e6, params) == 76, str(g.x_for_freq(240e6, params)))
    check("右端频率贴右框", g.x_for_freq(960e6, params) == 964)
    check("频率↔X 往返一致",
          abs(g.freq_for_x(g.x_for_freq(600e6, params), params) - 600e6) < 1.0,
          str(g.freq_for_x(g.x_for_freq(600e6, params), params)))
    check("参考电平贴顶格", g.y_for_level(-20, params, trace.levels, False) == 46)
    check("底格 = 参考-每格*格数", g.y_for_level(-100, params, trace.levels, False) == 540)
    check("越界点裁剪到边缘（不越出画布）",
          g.y_for_level(-500, params, trace.levels, False) == 540)
    check("幅值↔Y 往返一致",
          abs(g.level_for_y(g.y_for_level(-55, params, trace.levels, False), params,
                            trace.levels, False) + 55) < 0.01)

    v, h = g.grid_segments(params)
    check("竖网格 X_DIVS+1 = 11 条", len(v) == 11, str(len(v)))
    check("横网格 y_divs+1 = 9 条", len(h) == 9, str(len(h)))
    check("网格坐标为 SVG 字符串", isinstance(v[0]["x"], str), type(v[0]["x"]).__name__)

    xl = g.x_label_items(params)
    check("横轴标签首末贴边（start/end）",
          xl[0]["anchor"] == "start" and xl[-1]["anchor"] == "end",
          f"{xl[0]['anchor']}/{xl[-1]['anchor']}")
    check("横轴标签数 ≤ 8", len(xl) <= 8, str(len(xl)))
    yl = g.y_label_items(params, trace.levels, False)
    check("纵轴标签 = y_divs+1", len(yl) == 9, str(len(yl)))
    check("仪器式刻度无小数", yl[0]["text"] == "-20", yl[0]["text"])

    path = g.trace_path(trace, False)
    check("迹线为单条 path（M/L 指令）",
          path.startswith("M") and path.count("L") == trace.n_points - 1,
          f"L={path.count('L')}")

    bands = g.band_items()
    check("点击带数量", len(bands) == g.BAND_CLICK_COUNT, str(len(bands)))
    f0 = g.band_click_freq(0, params)
    f_last = g.band_click_freq(g.BAND_CLICK_COUNT - 1, params)
    check("首带中心靠起始、末带靠终止", f0 < params.center_hz < f_last,
          f"{f0/1e6:.1f}/{f_last/1e6:.1f} MHz")
    check("越界带号夹取", g.band_click_freq(999, params) == f_last)

    rect = g.band_rect(550e6, 650e6, params)
    check("积分带矩形（有交集）", rect is not None and float(rect["w"]) > 0, str(rect))
    check("积分带无交集 → None", g.band_rect(2e9, 3e9, params) is None)
    clipped = g.band_rect(100e6, 300e6, params)
    check("部分越界按交集裁剪",
          clipped is not None and float(clipped["x"]) == 76, str(clipped))

    mk = markers_for(trace, [300e6, 700e6])
    items = g.marker_items(mk, params, trace, False)
    check("标记图元含坐标与配色",
          len(items) == 2 and items[0]["color"] != items[1]["color"]
          and items[0]["x"] != items[1]["x"], str(items))


# ═══════════════════════════════════════════════════════════════
# 3. SpectrumState 端到端
# ═══════════════════════════════════════════════════════════════

def test_state():
    print("\n[3] SpectrumState 端到端")
    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return

    st = app.SpectrumState(_reflex_internal_init=True)
    check("分页/频谱状态互不影响（独立 State）", st.sp_freq_unit == "MHz")

    # 绘制
    st.sp_trace_text = TRACE_101
    st.sp_draw()
    check("绘制无错误", st.sp_error == "", st.sp_error)
    check("迹线非空且为 path", st.sp_polyline.startswith("M"), st.sp_polyline[:16])
    check("状态行含点数/步进",
          "点数 101" in st.sp_status and "频率步进" in st.sp_status, st.sp_status)
    check("参数注记含起止与检波",
          "起始 240 MHz" in st.sp_params_note and "检波" in st.sp_params_note,
          st.sp_params_note)
    check("纵轴范围文案（参考电平口径）",
          "参考电平口径" in st.sp_axis_range, st.sp_axis_range)
    check("网格/标签已生成", len(st.sp_grid_v) == 11 and len(st.sp_y_labels) == 9)
    check("点击带已生成", len(st.sp_bands) == 60)

    # 频率联动：改中心 → start/stop 同步
    st.sp_set_param("center", "500")
    check("改中心 → 起止联动",
          st.sp_start == "140" and st.sp_stop == "860",
          f"{st.sp_start}~{st.sp_stop}")
    check("联动提示", "已联动更新" in st.sp_msg, st.sp_msg)

    # 单位换算（MHz → GHz：数值换算，物理频率不变）
    before = st.sp_start
    st.sp_set_unit("GHz")
    check("切 GHz 后数值换算（240MHz→0.24GHz 量级）",
          float(st.sp_start) < 1 and abs(float(st.sp_start) * 1e9 - float(before) * 1e6) < 1e3,
          f"{before} MHz → {st.sp_start} GHz")
    st.sp_set_unit("MHz")

    # 点击加标记（带 30 ≈ 中心频率附近）
    st.sp_plot_click(30)
    check("点击后产生读数", st.sp_readout != "", st.sp_readout)
    check("标记数 = 1", st.sp_marker_count == 1, str(st.sp_marker_count))
    check("标记表含 M1", st.sp_marker_rows and st.sp_marker_rows[0]["label"] == "M1")
    st.sp_plot_click(45)
    check("第二个标记 M2", st.sp_marker_count == 2, str(st.sp_marker_count))
    check("Δ 文案标注哪两点",
          "M1↔M2" in st.sp_marker_rows[1]["d_freq"], st.sp_marker_rows[1]["d_freq"])
    check("标记配色一图一表同源",
          st.sp_marker_rows[0]["color"] == st.sp_markers_svg[0]["color"],
          f"{st.sp_marker_rows[0]['color']} vs {st.sp_markers_svg[0]['color']}")

    # 峰值搜索（换成有峰的数据）
    st.sp_trace_text = TRACE_PEAK
    st.sp_draw()
    st.sp_clear_markers()
    st.sp_next_peak()
    check("峰值搜索加标记", st.sp_marker_count == 1, str(st.sp_marker_count))
    check("找到的峰在 -30 附近",
          "峰值" in st.sp_extremes and "-30" in st.sp_extremes, st.sp_extremes)

    # 删除 / 清空
    st.sp_del_marker()
    check("删除标记后归零", st.sp_marker_count == 0, str(st.sp_marker_count))
    st.sp_plot_click(10)
    st.sp_clear_markers()
    check("清空标记 + 提示", st.sp_marker_count == 0 and "已清空" in st.sp_msg, st.sp_msg)

    # 标记上限 6
    for i in range(8):
        st.sp_plot_click(i * 7)
    check("标记上限 M6", st.sp_marker_count == 6, str(st.sp_marker_count))
    check("超限提示", "上限" in st.sp_msg, st.sp_msg)

    # 积分带宽（101 点常量 -70，扫宽 720MHz，步进 7.2MHz，RBW 7.2MHz → 归一化后 -70+10log10(N)）
    st.sp_clear_markers()
    st.sp_set_param("center", "600")
    st.sp_set_param("span", "720")
    st.sp_set_toggle("ibw_show", True)
    st.sp_set_param("ibw_center", "600")
    st.sp_set_param("ibw_bw", "100")
    check("IBW 读数含积分功率与点数",
          "积分功率" in st.sp_ibw_text and "点" in st.sp_ibw_text, st.sp_ibw_text)
    check("IBW 短注记", st.sp_ibw_short.startswith("IBW Σ"), st.sp_ibw_short)
    check("IBW 带矩形存在", "w" in st.sp_ibw_rect, str(st.sp_ibw_rect))
    check("RBW 归一化口径（RBW 已填且步进=RBW）",
          "按 RBW 归一化" in st.sp_ibw_text, st.sp_ibw_text)

    # 错误路径：非法 trace 保留旧图
    old_polyline = st.sp_polyline
    st.sp_trace_text = "abc 12a3"
    st.sp_draw()
    check("非法 token 报错", "不是有效数值" in st.sp_error or "第" in st.sp_error, st.sp_error)
    check("报错时保留旧图", st.sp_polyline == old_polyline and st.sp_has_trace)

    # 错误路径：非法参数（扫宽 <= 0 → resolve 抛错，保留原值）
    st.sp_trace_text = TRACE_101
    st.sp_set_param("start", "1200")  # start 与 span 保留 → 重算 stop/center（合法）
    check("改起始保扫宽 → 重算终止/中心",
          st.sp_stop == "1920" and st.sp_center == "1560",
          f"{st.sp_start}/{st.sp_stop}/{st.sp_center}")
    kept_start, kept_stop = st.sp_start, st.sp_stop
    st.sp_set_param("span", "-10")  # 扫宽非正 → 报错且四个字段保持原值
    check("非法扫宽被拒绝且保留原值",
          st.sp_error != "" and st.sp_start == kept_start and st.sp_stop == kept_stop,
          f"{st.sp_error} | {st.sp_start}~{st.sp_stop}")
    st.sp_error = ""
    st.sp_set_param("span", "720")  # 先恢复合法扫宽（中心/扫宽保留 → 重算起止）
    st.sp_set_param("start", "240")  # 再拉回起始（扫宽保留 → 终止 960）
    check("恢复为默认扫描（240~960）",
          st.sp_start == "240" and st.sp_stop == "960",
          f"{st.sp_start}~{st.sp_stop}")

    # 自动纵轴适配
    st.sp_set_toggle("auto_y", True)
    check("自动适配文案", "自动适配" in st.sp_axis_range, st.sp_axis_range)
    st.sp_set_toggle("auto_y", False)

    # 清空
    st.sp_clear()
    check("清空后无图", not st.sp_has_trace and st.sp_polyline == "")


# ═══════════════════════════════════════════════════════════════
# 4. 组件树
# ═══════════════════════════════════════════════════════════════

def test_component_tree():
    print("\n[4] 组件树可构建")
    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return
    tab = app.spectrum_tab()
    check("spectrum_tab() 构建成功", tab is not None)
    page = str(app.tool_page())
    check("工具页含频谱图 tab", "spectrum-svg" in page or "频谱图" in page,
          page[:80])


def main():
    print("=" * 62)
    print("Web 频谱图回归测试")
    print("=" * 62)
    test_reuse_guard()
    test_geometry()
    test_state()
    test_component_tree()
    print("\n" + "=" * 62)
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"全部通过（{PASS} 项）✓")
    print("=" * 62)


if __name__ == "__main__":
    main()
