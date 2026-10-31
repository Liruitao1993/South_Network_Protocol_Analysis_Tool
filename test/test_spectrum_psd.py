# -*- coding: utf-8 -*-
"""频谱图功率谱密度（PSD）测试

覆盖：
  1. 换算公式与单位（PSD = level − 10·log10(RBW)；dBm → dBm/Hz）
  2. RBW 必填（未填/非正 → 明确报错，不猜默认值）
  3. build_trace 在 PSD 视图下的幅值口径
  4. 纵轴参考电平、注记、状态行、峰值/谷值的口径同步
  5. 积分带宽在 PSD 视图下按「密度 × 频率步进」回到功率
  6. GUI：勾选后自动重绘、表头/状态/标记表同步，取消后还原，RBW 缺失时提示且保留旧图
  7. Web：State 开关端到端（复用同一套纯逻辑）

直接运行: python test/test_spectrum_psd.py
"""

import _path_setup  # noqa: E402

import math
import os
import sys

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


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


def raises(fn, keyword=""):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        return (keyword in str(exc)), f"{type(exc).__name__}: {exc}"
    return False, "未抛异常"


from spectrum_widget import (  # noqa: E402
    SpectrumInputError,
    SpectrumParams,
    axis_range_text,
    build_trace,
    display_ref_level,
    display_unit,
    extremes_text,
    integrate_band,
    integration_text,
    note_text,
    psd_levels,
    psd_offset_db,
    psd_unit,
    status_text,
    validate_params,
)

BASE_TEXT = " ".join(["-60"] * 101)  # 101 点 → 步进 7.2 MHz


def base_params(**kw):
    data = {"start_hz": 240e6, "stop_hz": 960e6}
    data.update(kw)
    return SpectrumParams(**data)


# ═══════════════════════════════════════════════════════════════
# 1. 纯逻辑：换算与单位
# ═══════════════════════════════════════════════════════════════

def test_units_and_offset():
    print("\n[1] 单位与换算公式")
    check("单位后缀 dBm → dBm/Hz", psd_unit("dBm") == "dBm/Hz", psd_unit("dBm"))
    check("单位后缀 dBμV → dBμV/Hz", psd_unit("dBμV") == "dBμV/Hz", psd_unit("dBμV"))
    check("非 PSD 视图单位不变", display_unit(base_params()) == "dBm")
    check("PSD 视图单位带 /Hz", display_unit(base_params(psd=True, rbw_hz=1e3)) == "dBm/Hz")

    # 1 kHz RBW → −10log10(1000) = −30 dB
    check("1 kHz 偏移 -30 dB", close(psd_offset_db(1e3), -30.0))
    check("1 Hz 偏移 0 dB", close(psd_offset_db(1.0), 0.0))
    check("1 MHz 偏移 -60 dB", close(psd_offset_db(1e6), -60.0))
    # 参考电平同样换算：-20 dBm @ 1 kHz → -50 dBm/Hz
    check(
        "参考电平换算到 dBm/Hz",
        close(display_ref_level(base_params(ref_level_db=-20.0, psd=True, rbw_hz=1e3)), -50.0),
        str(display_ref_level(base_params(ref_level_db=-20.0, psd=True, rbw_hz=1e3))),
    )
    check(
        "非 PSD 视图参考电平不变",
        close(display_ref_level(base_params(ref_level_db=-20.0)), -20.0),
    )
    # 逐点换算：同一偏移
    check(
        "psd_levels 逐点减同一偏移",
        psd_levels((-60.0, -61.0), 1e3) == (-90.0, -91.0),
        str(psd_levels((-60.0, -61.0), 1e3)),
    )


def test_rbw_required():
    print("\n[2] RBW 必填")
    ok, msg = raises(lambda: validate_params(base_params(psd=True)), "需要 RBW")
    check("未填 RBW 报错并点名 RBW", ok, msg)
    ok, msg = raises(lambda: validate_params(base_params(psd=True, rbw_hz=0.0)), "RBW")
    check("RBW=0 报错", ok, msg)
    ok, msg = raises(lambda: validate_params(base_params(psd=True, rbw_hz=float("nan"))), "RBW")
    check("RBW=nan 报错", ok, msg)
    ok, msg = raises(lambda: build_trace(BASE_TEXT, base_params(psd=True)), "需要 RBW")
    check("build_trace 同样拒绝（不产出半成品 trace）", ok, msg)
    # 非 PSD 视图 RBW 仍可选
    ok, msg = raises(lambda: validate_params(base_params()), "")
    check("非 PSD 视图 RBW 仍可留空", not ok or "错误" not in msg, msg)


def test_build_trace_psd():
    print("\n[3] build_trace 幅值口径")
    plain = build_trace("-60 -60 -63", base_params(rbw_hz=1e3))
    psd = build_trace("-60 -60 -63", base_params(rbw_hz=1e3, psd=True))
    check("非 PSD 幅值原样", plain.levels == (-60.0, -60.0, -63.0), str(plain.levels))
    check("PSD 幅值统一 -30 dB", psd.levels == (-90.0, -90.0, -93.0), str(psd.levels))
    check("频率轴不受 PSD 影响", psd.freqs == plain.freqs)
    # 50Ω 换算先做，再归一化：-70 dBm → 37 dBμV → 7 dBμV/Hz
    conv = build_trace(
        "-70 -70",
        base_params(unit="dBμV", convert_50ohm=True, rbw_hz=1e3, psd=True),
    )
    check("50Ω 换算与 PSD 叠加顺序正确", conv.levels == (7.0, 7.0), str(conv.levels))


def test_reports_psd():
    print("\n[4] 纵轴 / 注记 / 状态 / 极值口径")
    params = base_params(ref_level_db=-20.0, rbw_hz=1e3, psd=True)
    trace = build_trace(BASE_TEXT, params)
    text = axis_range_text(params, trace.levels, False)
    check("纵轴顶端按 PSD 换算", "-50" in text and "dBm/Hz" in text, text)
    check("纵轴标注 PSD 视图", "PSD 视图" in text, text)
    check("纵轴底端 = 顶 − 每格×格数", "-130" in text, text)

    note = note_text(params, trace.n_points)
    check("注记含功率谱密度与归一化口径", "功率谱密度 dBm/Hz" in note and "RBW" in note, note)
    check("注记参考电平按 PSD 换算", "参考电平 -50 dBm/Hz" in note, note)

    status = status_text(trace)
    check("状态行标注 PSD 单位", "PSD dBm/Hz" in status, status)

    ext = extremes_text(trace)
    check("峰值/谷值带 dBm/Hz", ext.count("dBm/Hz") == 2, ext)


def test_integration_psd():
    print("\n[5] 积分带宽在 PSD 视图下的口径")
    # 101 点、720 MHz 扫宽 → 步进 7.2 MHz；恒定 -60 dBm @ 1 kHz RBW = -90 dBm/Hz
    params = base_params(rbw_hz=1e3, psd=True)
    trace = build_trace(BASE_TEXT, params)
    step = params.step_hz(trace.n_points)
    # 取一个整步进的带宽：中心 600 MHz、带宽 72 MHz → 11 点
    result = integrate_band(trace, 600e6, 72e6, params.rbw_hz)
    expected = -90.0 + 10.0 * math.log10(result.n_points * step)
    check("积分点数符合带宽/步进", result.n_points == 11, str(result.n_points))
    check("PSD 按密度×步进积分为功率", close(result.total_db, expected, 1e-6),
          f"{result.total_db} vs {expected}")
    check("PSD 积分标注口径", "PSD 密度 × 频率步进" in result.basis, result.basis)
    check("PSD 积分结果为功率单位（无 /Hz）", result.unit == "dBm", result.unit)
    check("积分文案可读", "积分功率" in integration_text(result), integration_text(result))

    # 与「先按功率积分再归一化」在等步进/等 RBW 下应得到同一数值
    plain = build_trace(BASE_TEXT, base_params(rbw_hz=1e3))
    plain_result = integrate_band(plain, 600e6, 72e6, 1e3)
    check(
        "两种口径积分结果一致",
        close(result.total_db, plain_result.total_db, 1e-6),
        f"{result.total_db} vs {plain_result.total_db}",
    )


# ═══════════════════════════════════════════════════════════════
# 2. GUI
# ═══════════════════════════════════════════════════════════════

def test_gui():
    print("\n[6] GUI 勾选/取消与提示")
    from PySide6.QtWidgets import QApplication

    from spectrum_widget import SpectrumWidget

    app = QApplication.instance() or QApplication([])
    tab = SpectrumWidget()
    tab.trace_edit.setPlainText(BASE_TEXT)
    tab.rbw_edit.setText("1")
    tab.rbw_unit_combo.setCurrentText("kHz")
    tab._on_draw()
    tab._on_search_peak()

    check("默认非 PSD 表头", tab.marker_table.horizontalHeaderItem(2).text() == "幅值 (dBm)",
          tab.marker_table.horizontalHeaderItem(2).text())
    check("默认 trace 为 dBm", tab.current_trace().levels[0] == -60.0,
          str(tab.current_trace().levels[:2]))

    tab.psd_check.setChecked(True)
    trace = tab.current_trace()
    check("勾选后自动重绘（幅值变 PSD）", trace.levels[0] == -90.0, str(trace.levels[:2]))
    check("勾选后表头带 /Hz", tab.marker_table.horizontalHeaderItem(2).text() == "幅值 (dBm/Hz)",
          tab.marker_table.horizontalHeaderItem(2).text())
    check("勾选后标记表数值为 PSD", tab.marker_table.item(0, 2).text() == "-90",
          tab.marker_table.item(0, 2).text())
    check("勾选后测量栏带 dBm/Hz", "dBm/Hz" in tab.measure_label.text(), tab.measure_label.text())
    check("勾选后状态行标注 PSD", "PSD dBm/Hz" in tab.status_label.text(), tab.status_label.text())
    check("勾选后纵轴文案", "dBm/Hz" in tab.axis_label.text(), tab.axis_label.text())
    # 导出图不因 PSD 崩溃
    image = tab.canvas.render_image(600, 400)
    check("PSD 视图可渲染", image.width() == 600 and image.height() == 400)

    tab.psd_check.setChecked(False)
    check("取消后回到 dBm", tab.current_trace().levels[0] == -60.0,
          str(tab.current_trace().levels[:2]))
    check("取消后表头回到 dBm", tab.marker_table.horizontalHeaderItem(2).text() == "幅值 (dBm)",
          tab.marker_table.horizontalHeaderItem(2).text())

    # RBW 缺失：勾选后提示，且不破坏已绘制的图
    tab.rbw_edit.clear()
    tab.psd_check.setChecked(True)
    check("RBW 缺失时明确提示", "需要 RBW" in tab.status_label.text(), tab.status_label.text())
    check("RBW 缺失时保留旧图", tab.current_trace() is not None)
    check("RBW 缺失时旧图仍是 dBm", tab.current_trace().levels[0] == -60.0,
          str(tab.current_trace().levels[:2]))
    ok, msg = raises(lambda: tab.read_params(), "需要 RBW")
    check("read_params 抛 PSD 缺 RBW", ok, msg)
    tab.psd_check.setChecked(False)
    tab.rbw_edit.setText("1")
    del app  # noqa: F841 - 保持 app 引用到此处，避免解释器提前回收


# ═══════════════════════════════════════════════════════════════
# 3. Web（复用同一套纯逻辑）
# ═══════════════════════════════════════════════════════════════

def test_web():
    print("\n[7] Web State 端到端")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reflex_web"))
    try:
        import reflex_web.reflex_web as app
    except Exception as exc:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(exc).__name__}: {exc}")
        return
    st = app.SpectrumState(_reflex_internal_init=True)
    st.sp_trace_text = BASE_TEXT
    st.sp_rbw = "1"
    st.sp_rbw_unit = "kHz"
    st.sp_draw()
    check("Web 默认非 PSD", "PSD" not in st.sp_status, st.sp_status)
    st.sp_set_toggle("psd", True)
    check("Web 勾选后状态行标注 PSD", "PSD dBm/Hz" in st.sp_status, st.sp_status)
    check("Web 纵轴文案切到 dBm/Hz", "dBm/Hz" in st.sp_axis_range, st.sp_axis_range)
    check("Web 极值带 dBm/Hz", st.sp_extremes.count("dBm/Hz") == 2, st.sp_extremes)
    st.sp_set_toggle("psd", False)
    check("Web 取消后回到 dBm", "PSD" not in st.sp_status and "dBm/Hz" not in st.sp_extremes,
          f"{st.sp_status} | {st.sp_extremes}")


def main():
    for fn in (
        test_units_and_offset,
        test_rbw_required,
        test_build_trace_psd,
        test_reports_psd,
        test_integration_psd,
        test_gui,
        test_web,
    ):
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
    os._exit(0)
