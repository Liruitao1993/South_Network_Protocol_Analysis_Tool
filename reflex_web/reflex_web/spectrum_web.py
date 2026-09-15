# -*- coding: utf-8 -*-
"""Web 频谱图：SVG 几何层（纯逻辑，无 Qt / 无 reflex）。

设计要点（见 .trellis/tasks/09-15-web-spectrum-plot/design.md）：
- **一切数值/算法都复用桌面 `spectrum_widget.py` 的纯逻辑层**（参数校验、trace 清洗、
  刻度、标记吸附、峰值搜索、积分带宽），本模块只负责「把结果换算成 SVG 坐标」；
- 坐标单位是 SVG viewBox（与像素解耦，画布自适应缩放）；
- 本模块可被脚本直接测试（`test/test_web_spectrum.py`）。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 复用桌面纯逻辑层（同一份实现；Web 进程无 PySide6，Qt 层被 try/except 守护）
from spectrum_widget import (  # noqa: E402
    X_DIVS,
    Marker,
    SpectrumParams,
    SpectrumTrace,
    auto_tick_decimals,
    format_level,
    marker_color,
    x_tick_labels,
    y_range,
    y_ticks,
)

# ── 画布几何（viewBox 单位）──
VIEW_W = 1000
VIEW_H = 620
PLOT_X0 = 76
PLOT_X1 = 964
PLOT_Y0 = 46
PLOT_Y1 = 540
BAND_CLICK_COUNT = 60  # 绘图区切成 N 个透明带承载点击（Reflex 不暴露 DOM 事件坐标）
X_LABEL_MAX = 8  # 横轴最多标签数（超出则按 x_tick_stride 抽稀）

# 导出 PNG（纯前端：SVG → canvas → toDataURL → 下载；零新增依赖）
EXPORT_PNG_JS = """
(() => {
  const svg = document.getElementById('spectrum-svg');
  if (!svg) return 'no-svg';
  const clone = svg.cloneNode(true);
  clone.setAttribute('width', '1600');
  clone.setAttribute('height', '992');
  const data = new XMLSerializer().serializeToString(clone);
  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement('canvas');
    canvas.width = 1600; canvas.height = 992;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'spectrum.png';
    a.click();
  };
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(data);
  return 'ok';
})()
"""


def plot_rect() -> Tuple[float, float, float, float]:
    """绘图区矩形 (x0, y0, x1, y1)。"""
    return PLOT_X0, PLOT_Y0, PLOT_X1, PLOT_Y1


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _num(value: float) -> str:
    """坐标 → SVG 属性字符串（Reflex 的 SVG 属性只接受 str|int）。"""
    return f"{round(float(value), 2):g}"


def x_for_freq(freq_hz: float, params: SpectrumParams) -> float:
    """频率 → 绘图区 X 坐标（越界不裁剪；调用方按需 clamp）。"""
    span = params.span_hz
    if span == 0:
        return PLOT_X0
    ratio = (freq_hz - params.start_hz) / span
    return PLOT_X0 + ratio * (PLOT_X1 - PLOT_X0)


def freq_for_x(x: float, params: SpectrumParams) -> float:
    """绘图区 X 坐标 → 频率（x_for_freq 的逆）。"""
    width = PLOT_X1 - PLOT_X0
    if width == 0:
        return params.start_hz
    ratio = (x - PLOT_X0) / width
    return params.start_hz + ratio * params.span_hz


def y_for_level(
    level: float, params: SpectrumParams, levels: Sequence[float], auto: bool
) -> float:
    """幅值 → 绘图区 Y 坐标；超出纵轴范围的点**裁剪到边缘**（与桌面一致）。"""
    top, bottom = y_range(params, levels, auto)
    span = top - bottom
    if span == 0:
        return PLOT_Y0
    ratio = (top - level) / span
    return _clamp(PLOT_Y0 + ratio * (PLOT_Y1 - PLOT_Y0), PLOT_Y0, PLOT_Y1)


def level_for_y(
    y: float, params: SpectrumParams, levels: Sequence[float], auto: bool
) -> float:
    """绘图区 Y 坐标 → 幅值（y_for_level 的逆）。"""
    top, bottom = y_range(params, levels, auto)
    height = PLOT_Y1 - PLOT_Y0
    if height == 0:
        return top
    ratio = (y - PLOT_Y0) / height
    return top - ratio * (top - bottom)


def grid_segments(params: SpectrumParams) -> Tuple[list, list]:
    """(竖线, 横线)：竖线含首末边框共 X_DIVS+1 条；横线 y_divs+1 条。"""
    vertical = [
        {"x": _num(PLOT_X0 + i * (PLOT_X1 - PLOT_X0) / X_DIVS)}
        for i in range(X_DIVS + 1)
    ]
    divs = max(1, int(params.y_divs))
    horizontal = [
        {"y": _num(PLOT_Y0 + i * (PLOT_Y1 - PLOT_Y0) / divs)}
        for i in range(divs + 1)
    ]
    return vertical, horizontal


def trace_path(
    trace: SpectrumTrace, auto: bool
) -> str:
    """迹线 SVG `path` 的 d 字符串（单条路径；越界点裁到边缘）。

    注：本项目 Reflex 版本的 `el` 无 `polyline`（只有 polygon/path），且 polygon 会自动
    闭合首尾点（多出一条回边），故用 path（M/L）。
    """
    if trace.n_points == 0:
        return ""
    cmds = []
    for i, (freq, level) in enumerate(zip(trace.freqs, trace.levels)):
        x = _num(x_for_freq(freq, trace.params))
        y = _num(y_for_level(level, trace.params, trace.levels, auto))
        cmds.append(f"{'M' if i == 0 else 'L'}{x},{y}")
    return " ".join(cmds)


def x_label_items(params: SpectrumParams, max_labels: int = X_LABEL_MAX) -> list:
    """横轴标签：[{x, text, anchor}]，首标签左对齐、末标签右对齐（避免越出画布）。"""
    items = []
    for idx, text in x_tick_labels(params, max_labels):
        x = PLOT_X0 + idx * (PLOT_X1 - PLOT_X0) / X_DIVS
        if idx == 0:
            anchor = "start"
        elif idx == X_DIVS:
            anchor = "end"
        else:
            anchor = "middle"
        items.append({"x": _num(x), "text": text, "anchor": anchor,
                      "ty": _num(PLOT_Y1 + 16)})
    return items


def y_label_items(
    params: SpectrumParams, levels: Sequence[float], auto: bool
) -> list:
    """纵轴标签：[{y, text}]，自顶向下 y_divs+1 个（含上下边框）。"""
    ticks = y_ticks(params, levels, auto)
    top, bottom = y_range(params, levels, auto)
    decimals = auto_tick_decimals((top - bottom) / max(1, int(params.y_divs))) if auto else None
    items = []
    for i, value in enumerate(ticks):
        y = PLOT_Y0 + i * (PLOT_Y1 - PLOT_Y0) / max(1, int(params.y_divs))
        text = (
            f"{value:.{decimals}f}" if decimals is not None else format_level(value)
        )
        items.append({"y": _num(y), "ty": _num(y + 4), "text": text})
    return items


def marker_var(order: int) -> str:
    """标记颜色变量（由 theme_web.marker_css 按主题生成数值，图与表共用同一变量）。"""
    return f"var(--sp-m{int(order) % 6 + 1})"


def marker_items(
    markers: Sequence[Marker],
    params: SpectrumParams,
    trace: SpectrumTrace,
    auto: bool,
) -> list:
    """标记图元：[{x, y, label, color, text}]（竖虚线 + 圆点 + 标签，颜色与标记表同源）。

    颜色是 CSS 变量（`var(--sp-mN)`）→ 明暗主题各自解析，无需 Python 侧判断。
    """
    items = []
    for order, marker in enumerate(markers):
        items.append(
            {
                "x": _num(x_for_freq(marker.freq_hz, params)),
                "y": _num(y_for_level(marker.level, params, trace.levels, auto)),
                "label": marker.label,
                "color": marker_var(order),
                "text": f"{marker.label}",
            }
        )
    return items


def band_rect(
    low_hz: float, high_hz: float, params: SpectrumParams
) -> Optional[dict]:
    """积分带宽带矩形（与绘图区求交）；无交集 → None（不绘制）。

    返回 `{x, w, low_x, high_x}`：`x/w` 为填充带，`low_x/high_x` 为两条边沿线。
    """
    low_x = _clamp(x_for_freq(low_hz, params), PLOT_X0, PLOT_X1)
    high_x = _clamp(x_for_freq(high_hz, params), PLOT_X0, PLOT_X1)
    # 与扫描范围无交集 → 不画
    if high_hz < params.start_hz or low_hz > params.stop_hz:
        return None
    if high_x <= low_x:
        return None
    return {
        "x": _num(low_x),
        "w": _num(high_x - low_x),
        "low_x": _num(low_x),
        "high_x": _num(high_x),
    }


def band_click_freq(index: int, params: SpectrumParams) -> float:
    """第 index 个点击带（0..BAND_CLICK_COUNT-1）的中心频率。"""
    idx = int(_clamp(index, 0, BAND_CLICK_COUNT - 1))
    width = (PLOT_X1 - PLOT_X0) / BAND_CLICK_COUNT
    center_x = PLOT_X0 + (idx + 0.5) * width
    return freq_for_x(center_x, params)


def band_items() -> list:
    """点击带图元：[{index, x, w}]（透明 rect，承载 click/hover）。"""
    width = (PLOT_X1 - PLOT_X0) / BAND_CLICK_COUNT
    return [
        {"index": i, "id": f"sp-band-{i}",
         "x": _num(PLOT_X0 + i * width), "w": _num(width)}
        for i in range(BAND_CLICK_COUNT)
    ]


def view_box() -> str:
    return f"0 0 {int(VIEW_W)} {int(VIEW_H)}"


def plot_size_hint() -> Tuple[str, str]:
    """外层 <svg> 的宽/高（CSS 尺寸，viewBox 负责缩放）。"""
    return "100%", "min(72vh, 620px)"


def band_area_span(params: SpectrumParams) -> float:
    """一个点击带覆盖的频率宽度（状态提示用）。"""
    return params.span_hz / BAND_CLICK_COUNT if params.span_hz else 0.0


def finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))
