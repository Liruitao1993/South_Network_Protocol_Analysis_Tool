# -*- coding: utf-8 -*-
"""频谱图标签页（频谱仪参数配置 + trace 数值输入 → 仪器式网格频谱图）

文件分两层（AGENTS.md §4.1；.trellis/spec/frontend/component-guidelines.md）：

  - 纯逻辑层（文件前半，**不 import PySide6**，可脚本测试）：
      SpectrumInputError / SpectrumParams / SpectrumTrace
      parse_levels / validate_params / build_trace / freqs_for / display_levels
      y_range / y_ticks / x_tick_stride / x_tick_labels / format_hz / format_level
      count_out_of_range / resolve_freq_inputs / units_to_hz / to_freq_unit
      note_text / status_text / axis_range_text
  - Qt 层（文件后半）：
      SpectrumCanvas(QWidget)  自绘画布（paintEvent 全量重绘，render_image 复用同一绘制）
      SpectrumWidget(QWidget)  标签页（参数表单 + trace 输入 + 画布 + 导出 PNG）

零新增第三方依赖：不使用 matplotlib（已被 PyInstaller spec 显式排除），
网格/刻度/迹线/注记全部由 QPainter 绘制。
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

# ══════════════════════════════════════════════════════════════════
# 纯逻辑层（无 Qt 依赖，可独立脚本测试）
# ══════════════════════════════════════════════════════════════════

UNIT_DBM = "dBm"
UNIT_DBUV = "dBμV"
UNIT_DBMV = "dBmV"
LEVEL_UNITS: Tuple[str, ...] = (UNIT_DBM, UNIT_DBUV, UNIT_DBMV)
# 50Ω 系统下相对 dBm 的偏移（dBμV = dBm + 107，dBmV = dBm + 47）
UNIT_OFFSET_FROM_DBM = {UNIT_DBM: 0.0, UNIT_DBUV: 107.0, UNIT_DBMV: 47.0}

DETECTORS: Tuple[str, ...] = ("峰值", "准峰值", "平均值", "RMS", "采样")
DEFAULT_DETECTOR = "峰值"

FREQ_UNITS = {"kHz": 1e3, "MHz": 1e6, "GHz": 1e9}  # 起始/终止/中心/扫宽 共用同一单位
RBW_UNITS = {"kHz": 1e3, "MHz": 1e6}  # RBW / VBW
DEFAULT_FREQ_UNIT = "MHz"
DEFAULT_RBW_UNIT = "kHz"

DEFAULT_START_HZ = 240e6
DEFAULT_STOP_HZ = 960e6
DEFAULT_REF_LEVEL_DB = -20.0
DEFAULT_DB_PER_DIV = 10.0
DEFAULT_Y_DIVS = 8
MIN_DB_PER_DIV, MAX_DB_PER_DIV = 0.1, 20.0
MIN_Y_DIVS, MAX_Y_DIVS = 4, 12
X_DIVS = 10  # 横向固定 10 格（频谱仪屏幕口径）
AUTO_Y_MARGIN = 0.05  # 自动适配时上下各留 5% 余量
MARKER_MAX_POINTS = 201  # 点数不超过此值时叠加数据点标记
MAX_MARKERS = 6  # MARK 标记上限（M1..M6，仪器惯例）
PEAK_MIN_PROMINENCE_DB = 3.0  # 「下一个峰值」的显著度阈值（dB）
# 每个标记一种颜色（M1..M6 顺序固定），图与标记表共用，便于一一对应
MARKER_COLORS_DARK: Tuple[str, ...] = (
    "#4FC3F7",  # M1 天蓝
    "#FF8A65",  # M2 橙
    "#81C784",  # M3 绿
    "#BA68C8",  # M4 紫
    "#FFD54F",  # M5 黄
    "#4DB6AC",  # M6 青绿
)
MARKER_COLORS_LIGHT: Tuple[str, ...] = (
    "#1565C0",  # M1 深蓝
    "#D84315",  # M2 深橙
    "#2E7D32",  # M3 深绿
    "#6A1B9A",  # M4 深紫
    "#F9A825",  # M5 琥珀
    "#00695C",  # M6 深青
)


def marker_color(dark: bool, order: int) -> str:
    """第 order 个标记（0 基，对应 M{order+1}）的颜色；超出上限循环取色。"""
    colors = MARKER_COLORS_DARK if dark else MARKER_COLORS_LIGHT
    return colors[int(order) % len(colors)]

_SEPARATORS = (",", ";", "\t", "\r", "\n", "，", "、")  # 归一为空格后 split
_TITLE = "频谱图"


class SpectrumInputError(ValueError):
    """频谱参数 / trace 数值校验失败（消息可直接展示给用户）。"""


def units_to_hz(value: float, unit: str) -> float:
    """频率数值 + 单位 → Hz。"""
    factor = FREQ_UNITS.get(unit)
    if factor is None:
        raise SpectrumInputError(f"未知频率单位：{unit}")
    return value * factor


def to_freq_unit(hz: float, unit: str) -> float:
    """Hz → 指定频率单位下的数值。"""
    return hz / units_to_hz(1.0, unit)


@dataclass(frozen=True)
class SpectrumParams:
    """频谱仪扫描参数（频率一律以 Hz 存储）。"""

    start_hz: float
    stop_hz: float
    ref_level_db: float = DEFAULT_REF_LEVEL_DB
    db_per_div: float = DEFAULT_DB_PER_DIV
    y_divs: int = DEFAULT_Y_DIVS
    unit: str = UNIT_DBM
    convert_50ohm: bool = False
    rbw_hz: Optional[float] = None
    vbw_hz: Optional[float] = None
    detector: str = DEFAULT_DETECTOR

    @property
    def span_hz(self) -> float:
        return self.stop_hz - self.start_hz

    @property
    def center_hz(self) -> float:
        return (self.start_hz + self.stop_hz) / 2.0

    def step_hz(self, n_points: int) -> Optional[float]:
        """等间隔扫频步进 = span / (N - 1)；N < 2 无意义 → None。"""
        if n_points < 2:
            return None
        return self.span_hz / (n_points - 1)


@dataclass(frozen=True)
class SpectrumTrace:
    """一条 trace：等间隔频率轴 + 已按所选单位换算的幅值。"""

    params: SpectrumParams
    freqs: Tuple[float, ...]
    levels: Tuple[float, ...]

    @property
    def n_points(self) -> int:
        return len(self.levels)


def parse_levels(text: str) -> Tuple[float, ...]:
    """解析 trace 数值文本（空格/制表/逗号/分号/换行/全角分隔符均可）。

    非法 token 一律抛错并指出**序号与原文**，绝不静默丢弃
    （AGENTS.md §8 陷阱 23：宁可报错也不能给出空白结果）。
    """
    if text is None:
        raise SpectrumInputError("请输入 trace 数值")
    cleaned = text.replace("\ufeff", "")
    for sep in _SEPARATORS:
        cleaned = cleaned.replace(sep, " ")
    tokens = cleaned.split()
    if not tokens:
        raise SpectrumInputError("请输入 trace 数值")
    values = []
    for idx, token in enumerate(tokens, 1):
        try:
            value = float(token)
        except ValueError:
            raise SpectrumInputError(f"第 {idx} 项不是有效数值：{token}") from None
        if not math.isfinite(value):
            raise SpectrumInputError(f"第 {idx} 项不是有效数值：{token}")
        values.append(value)
    return tuple(values)


def validate_params(params: SpectrumParams) -> None:
    """参数合法性校验（错误消息面向用户）。"""
    if not math.isfinite(params.start_hz) or params.start_hz <= 0:
        raise SpectrumInputError("起始频率必须为正数")
    if not math.isfinite(params.stop_hz) or params.stop_hz <= 0:
        raise SpectrumInputError("终止频率必须为正数")
    if params.stop_hz <= params.start_hz:
        raise SpectrumInputError("终止频率必须大于起始频率")
    if not math.isfinite(params.ref_level_db):
        raise SpectrumInputError("参考电平必须是有效数值")
    if not (MIN_DB_PER_DIV <= params.db_per_div <= MAX_DB_PER_DIV):
        raise SpectrumInputError(
            f"每格 dB 需在 {MIN_DB_PER_DIV} ~ {MAX_DB_PER_DIV} 之间"
        )
    if not (MIN_Y_DIVS <= int(params.y_divs) <= MAX_Y_DIVS):
        raise SpectrumInputError(f"纵向格数需在 {MIN_Y_DIVS} ~ {MAX_Y_DIVS} 之间")
    if params.unit not in LEVEL_UNITS:
        raise SpectrumInputError(f"未知幅值单位：{params.unit}")
    for name, value in (("RBW", params.rbw_hz), ("VBW", params.vbw_hz)):
        if value is None:
            continue
        if not math.isfinite(value) or value <= 0:
            raise SpectrumInputError(f"{name} 必须为正数")
    if params.detector not in DETECTORS:
        raise SpectrumInputError(f"未知检波方式：{params.detector}")


def display_levels(
    levels: Sequence[float], params: SpectrumParams
) -> Tuple[float, ...]:
    """按「50Ω 换算」开关把 trace 幅值换算到所选单位（不勾选则原样返回）。"""
    if not params.convert_50ohm or params.unit == UNIT_DBM:
        return tuple(float(v) for v in levels)
    offset = UNIT_OFFSET_FROM_DBM.get(params.unit, 0.0)
    return tuple(float(v) + offset for v in levels)


def freqs_for(params: SpectrumParams, n_points: int) -> Tuple[float, ...]:
    """等间隔线性频率轴：freqs[i] = start + i * span / (N - 1)。"""
    if n_points < 2:
        raise SpectrumInputError("至少需要 2 个数值点才能绘制")
    step = params.step_hz(n_points)
    return tuple(params.start_hz + i * step for i in range(n_points))


def build_trace(text: str, params: SpectrumParams) -> SpectrumTrace:
    """校验参数 + 解析数值 + 换算单位 + 生成频率轴。"""
    validate_params(params)
    raw = parse_levels(text)
    if len(raw) < 2:
        raise SpectrumInputError("至少需要 2 个数值点才能绘制")
    return SpectrumTrace(
        params=params,
        freqs=freqs_for(params, len(raw)),
        levels=display_levels(raw, params),
    )


def y_range(
    params: SpectrumParams, levels: Sequence[float], auto: bool
) -> Tuple[float, float]:
    """纵轴范围 (顶, 底)。

    auto=False（仪器式）：顶 = 参考电平，底 = 参考电平 − 每格 dB × 格数。
    auto=True：取数据 min/max 并上下各留 5% 余量（无数据时回落仪器式）。
    """
    if not auto or not levels:
        top = params.ref_level_db
        return top, top - params.db_per_div * params.y_divs
    low = min(levels)
    high = max(levels)
    if high == low:
        margin = max(1.0, abs(high) * 0.01)
    else:
        margin = (high - low) * AUTO_Y_MARGIN
    return high + margin, low - margin


def y_ticks(
    params: SpectrumParams, levels: Sequence[float], auto: bool
) -> Tuple[float, ...]:
    """纵轴刻度值，自顶向下共 y_divs + 1 个（含上下边框）。"""
    top, bottom = y_range(params, levels, auto)
    step = (top - bottom) / params.y_divs
    return tuple(top - i * step for i in range(params.y_divs + 1))


def x_tick_stride(max_labels: int) -> int:
    """按可容纳标签数选择每几个横向格标一次（1/2/5/10，保证标签落在网格线上）。"""
    for stride in (1, 2, 5, 10):
        if X_DIVS // stride + 1 <= max(2, int(max_labels)):
            return stride
    return X_DIVS


def x_tick_labels(
    params: SpectrumParams, max_labels: int
) -> Tuple[Tuple[int, str], ...]:
    """横轴标签：((格序号 0..10, 文本), ...)，格序号对应竖网格线。"""
    stride = x_tick_stride(max_labels)
    out = []
    for idx in range(0, X_DIVS + 1, stride):
        hz = params.start_hz + params.span_hz * idx / X_DIVS
        out.append((idx, format_hz(hz)))
    return tuple(out)


def format_hz(hz: float) -> str:
    """频率格式化（自动选 Hz/kHz/MHz/GHz，最多 6 位有效数字）。"""
    magnitude = abs(hz)
    if magnitude >= 1e9:
        value, unit = hz / 1e9, "GHz"
    elif magnitude >= 1e6:
        value, unit = hz / 1e6, "MHz"
    elif magnitude >= 1e3:
        value, unit = hz / 1e3, "kHz"
    else:
        value, unit = hz, "Hz"
    return f"{round(value, 6):g} {unit}"


def format_level(value: float, unit: str = "") -> str:
    """幅值/分格值格式化；unit 为空时只出数字（轴刻度用）。"""
    text = f"{round(float(value), 4):g}"
    return f"{text} {unit}".strip()


def auto_tick_decimals(step: float) -> int:
    """自动适配模式下纵轴刻度保留的小数位（按分格步长决定）。"""
    step = abs(float(step))
    if step >= 10:
        return 0
    if step >= 1:
        return 1
    if step >= 0.1:
        return 2
    return 3


def format_fixed(value: float, decimals: int) -> str:
    """定点小数格式化（自动适配刻度用，避免 47.3275 这类等分噪声）。"""
    return f"{float(value):.{max(0, int(decimals))}f}"


def count_out_of_range(
    params: SpectrumParams, levels: Sequence[float], auto: bool
) -> int:
    """超出当前纵轴范围的点数（绘制时会裁剪到边缘）。"""
    if not levels:
        return 0
    top, bottom = y_range(params, levels, auto)
    return sum(1 for v in levels if v > top or v < bottom)


# ── 测量层：光标吸附 / MARK 标记 / 峰值搜索 / Δ 计算 ──────────────


@dataclass(frozen=True)
class Marker:
    """一个 MARK 标记（吸附到数据点；频率为锚点，index 仅供绘制与查表）。"""

    label: str
    freq_hz: float
    level: float
    index: int


def nearest_index(freqs: Sequence[float], freq_hz: float) -> int:
    """频率轴上吸附到最近数据点的索引（二分查找，任意单调轴均正确）。"""
    count = len(freqs)
    if count == 0:
        raise SpectrumInputError("没有可吸附的数据点")
    if count == 1:
        return 0
    pos = bisect.bisect_left(freqs, freq_hz)
    if pos <= 0:
        return 0
    if pos >= count:
        return count - 1
    before, after = freqs[pos - 1], freqs[pos]
    # 正中间时取靠前索引，保证确定性
    return pos - 1 if (freq_hz - before) <= (after - freq_hz) else pos


def markers_for(trace: SpectrumTrace, freqs: Sequence[float]) -> Tuple[Marker, ...]:
    """按频率锚点重建标记：吸附最近数据点、越界丢弃、顺序重编号 M1..Mn。"""
    if trace.n_points == 0:
        return ()
    low, high = trace.freqs[0], trace.freqs[-1]
    markers = []
    for freq_hz in freqs:
        if not math.isfinite(freq_hz) or freq_hz < low or freq_hz > high:
            continue
        idx = nearest_index(trace.freqs, freq_hz)
        markers.append(
            Marker(
                label=f"M{len(markers) + 1}",
                freq_hz=trace.freqs[idx],
                level=trace.levels[idx],
                index=idx,
            )
        )
    return tuple(markers)


def peak_index(levels: Sequence[float]) -> int:
    """全局最大幅值点索引（并列取最靠前者）。"""
    if not levels:
        raise SpectrumInputError("没有数据点，无法搜索峰值")
    best = 0
    for i in range(1, len(levels)):
        if levels[i] > levels[best]:
            best = i
    return best


def valley_index(levels: Sequence[float]) -> int:
    """全局最小幅值点索引（并列取最靠前者）。"""
    if not levels:
        raise SpectrumInputError("没有数据点，无法搜索谷值")
    best = 0
    for i in range(1, len(levels)):
        if levels[i] < levels[best]:
            best = i
    return best


def _valley_left(levels: Sequence[float]) -> Tuple[float, ...]:
    """每个点左侧「通往更高地形」路径上的最低值（无更高点时取到数组左端）。

    单调栈一次遍历完成（O(n)），与逐点左右扫描的朴素实现结果完全一致：
    弹出的每个栈元素连同它覆盖的区间一起并入当前点的最小值。
    """
    count = len(levels)
    out = [0.0] * count
    stack = []  # [(索引, 该元素覆盖区间 (上一个更高点, 索引] 的最低值)]
    for i in range(count):
        level = levels[i]
        run = level
        while stack and levels[stack[-1][0]] <= level:
            index, covered = stack.pop()
            if covered < run:
                run = covered
            if levels[index] < run:
                run = levels[index]
        out[i] = run
        stack.append((i, run))
    return tuple(out)


def _valley_right(levels: Sequence[float]) -> Tuple[float, ...]:
    """每个点右侧「通往更高地形」路径上的最低值（_valley_left 的镜像）。"""
    count = len(levels)
    out = [0.0] * count
    stack = []
    for i in range(count - 1, -1, -1):
        level = levels[i]
        run = level
        while stack and levels[stack[-1][0]] <= level:
            index, covered = stack.pop()
            if covered < run:
                run = covered
            if levels[index] < run:
                run = levels[index]
        out[i] = run
        stack.append((i, run))
    return tuple(out)


def peak_indices(
    levels: Sequence[float], min_prominence_db: float = PEAK_MIN_PROMINENCE_DB
) -> Tuple[int, ...]:
    """局部峰索引（显著度 ≥ 阈值）；首尾点不作为峰（避免边界伪峰）。

    显著度 = 峰高 − max(左侧谷, 右侧谷)，谷值取「通往更高地形」路径上的最低值
    （标准 key-col 定义）。左右谷值用单调栈预计算，整体 O(n)——早期逐点扫描实现
    在「一侧没有更高点」的频谱上会退化为 O(n²)（实测 16000 点 3.7 s，冻结 GUI）。
    """
    count = len(levels)
    if count < 3:
        return ()
    left = _valley_left(levels)
    right = _valley_right(levels)
    peaks = []
    for i in range(1, count - 1):
        if levels[i] < levels[i - 1] or levels[i] <= levels[i + 1]:
            continue  # 非局部极大（右侧平/降才算峰，避免平台被重复计数）
        if levels[i] - max(left[i], right[i]) >= min_prominence_db:
            peaks.append(i)
    return tuple(peaks)


def next_peak_index(
    levels: Sequence[float],
    current_index: int,
    direction: int = 1,
    min_prominence_db: float = PEAK_MIN_PROMINENCE_DB,
) -> Optional[int]:
    """从 current_index 起沿 direction 找下一个峰（环形；无峰返回 None）。"""
    peaks = peak_indices(levels, min_prominence_db)
    if not peaks:
        return None
    if direction >= 0:
        for idx in peaks:
            if idx > current_index:
                return idx
        return peaks[0]  # 环形：已到最后一个峰 → 回到首个峰
    for idx in reversed(peaks):
        if idx < current_index:
            return idx
    return peaks[-1]


def extreme_points(trace: SpectrumTrace) -> Tuple[Marker, Marker]:
    """(峰值点, 谷值点)——基础计算显示用。"""
    high = peak_index(trace.levels)
    low = valley_index(trace.levels)
    return (
        Marker("峰值", trace.freqs[high], trace.levels[high], high),
        Marker("谷值", trace.freqs[low], trace.levels[low], low),
    )


def format_delta_hz(delta_hz: float) -> str:
    """频率增量（带符号，自动单位）。"""
    sign = "-" if delta_hz < 0 else ""
    return f"{sign}{format_hz(abs(delta_hz))}"


def format_delta_level(delta_db: float) -> str:
    """幅值增量（带符号，2 位小数，仪器惯例）。"""
    return f"{delta_db:+.2f} dB"


def delta_pair_index(
    markers: Sequence[Marker], ref_index: int = 0
) -> Optional[Tuple[int, int]]:
    """两点测量的下标对 (参考, 目标)：目标取参考之后的下一个标记，参考为最后一个时取前一个。"""
    count = len(markers)
    if count < 2:
        return None
    ref = int(ref_index)
    if ref < 0 or ref > count - 1:
        ref = 0
    # 参考标记始终排在前面，与标记表 Δ 单元格的 `M?↔M?` 标注保持一致
    return (ref, ref + 1) if ref < count - 1 else (ref, ref - 1)


def delta_text(markers: Sequence[Marker], ref_index: int = 0) -> str:
    """两点测量文案：明确标注是哪两个标记之间的 Δf（频段宽度）与 Δlevel。"""
    pair = delta_pair_index(markers, ref_index)
    if pair is None:
        return ""
    first, second = markers[pair[0]], markers[pair[1]]
    return (
        f"Δf({first.label}↔{second.label}) "
        f"{format_delta_hz(second.freq_hz - first.freq_hz)}"
        f"   Δlevel {format_delta_level(second.level - first.level)}"
    )


def marker_rows(
    markers: Sequence[Marker], ref_index: int = 0
) -> Tuple[Tuple[str, ...], ...]:
    """标记表行：(标记, 频率, 幅值, Δ频率, Δ幅值)。

    Δ 相对「参考标记」（默认 M1）；**每个 Δ 单元格自带 `M?↔M?` 标注**，
    避免只看到一个数值却不知道是哪两点之差。参考标记行为「参考」。
    """
    if not markers:
        return ()
    count = len(markers)
    ref = int(ref_index)
    if ref < 0 or ref > count - 1:
        ref = 0
    reference = markers[ref]
    rows = []
    for order, marker in enumerate(markers):
        if order == ref:
            rows.append(
                (
                    marker.label,
                    format_hz(marker.freq_hz),
                    format_level(marker.level),
                    "参考",
                    "参考",
                )
            )
            continue
        rows.append(
            (
                marker.label,
                format_hz(marker.freq_hz),
                format_level(marker.level),
                f"{reference.label}↔{marker.label}  "
                f"{format_delta_hz(marker.freq_hz - reference.freq_hz)}",
                f"{reference.label}↔{marker.label}  "
                f"{format_delta_level(marker.level - reference.level)}",
            )
        )
    return tuple(rows)


def readout_text(freq_hz: float, level: float, unit: str) -> str:
    """单点读数文本（光标读数框与状态行共用）。"""
    return f"{format_hz(freq_hz)}   {format_level(level, unit)}"


def marker_note(marker: Marker, unit: str) -> str:
    """标记状态提示文本。"""
    return f"{marker.label} {readout_text(marker.freq_hz, marker.level, unit)}"


def extremes_text(trace: SpectrumTrace) -> str:
    """峰值/谷值摘要（基础计算）。"""
    high, low = extreme_points(trace)
    unit = trace.params.unit
    return (
        f"峰值 {format_hz(high.freq_hz)} / {format_level(high.level, unit)}"
        f"     谷值 {format_hz(low.freq_hz)} / {format_level(low.level, unit)}"
    )


def resolve_freq_inputs(
    changed: str,
    start_hz: float,
    stop_hz: float,
    center_hz: float,
    span_hz: float,
) -> Tuple[float, float, float, float]:
    """起始/终止/中心/扫宽 四字段双向联动（单位一致，均为 Hz）。

    changed ∈ {"start", "stop", "center", "span"} 表示用户刚改动的字段：
      - start  ：保住 start 与 span → 重算 stop / center
      - stop   ：保住 start 与 stop → 重算 center / span
      - center ：保住 center 与 span → 重算 start / stop
      - span   ：保住 center 与 span → 重算 start / stop
    结果非法（扫宽非正、频率非正）时抛 SpectrumInputError，调用方保持原值。
    """
    if changed == "start":
        start = start_hz
        span = span_hz
        stop = start + span
    elif changed == "stop":
        start = start_hz
        stop = stop_hz
        span = stop - start
    elif changed == "center":
        center = center_hz
        span = span_hz
        start = center - span / 2.0
        stop = center + span / 2.0
    elif changed == "span":
        center = center_hz
        span = span_hz
        start = center - span / 2.0
        stop = center + span / 2.0
    else:
        raise SpectrumInputError(f"未知的频率字段：{changed}")

    if span <= 0:
        raise SpectrumInputError("扫宽必须为正数（终止频率需大于起始频率）")
    if start <= 0:
        raise SpectrumInputError("该中心频率与扫宽会得到非正的起始频率，已忽略本次修改")
    return start, stop, (start + stop) / 2.0, stop - start


def note_text(params: SpectrumParams, n_points: int) -> str:
    """图中参数注记（导出图一并渲染，便于直接贴报告）。"""
    parts = [
        f"起始 {format_hz(params.start_hz)}",
        f"终止 {format_hz(params.stop_hz)}",
        f"扫宽 {format_hz(params.span_hz)}",
    ]
    if params.rbw_hz:
        parts.append(f"RBW {format_hz(params.rbw_hz)}")
    if params.vbw_hz:
        parts.append(f"VBW {format_hz(params.vbw_hz)}")
    parts.append(f"检波 {params.detector}")
    parts.append(f"参考电平 {format_level(params.ref_level_db, params.unit)}")
    parts.append(f"{format_level(params.db_per_div)} dB/格 × {params.y_divs} 格")
    parts.append(f"点数 {n_points}")
    return "   ".join(parts)


def status_text(trace: SpectrumTrace) -> str:
    """状态行文本：点数 / 频率步进 / 扫宽 / RBW。"""
    parts = [f"点数 {trace.n_points}"]
    step = trace.params.step_hz(trace.n_points)
    if step is not None:
        parts.append(f"频率步进 {format_hz(step)}")
    parts.append(f"扫宽 {format_hz(trace.params.span_hz)}")
    if trace.params.rbw_hz:
        parts.append(f"RBW {format_hz(trace.params.rbw_hz)}")
    return " · ".join(parts)


def axis_range_text(
    params: SpectrumParams, levels: Sequence[float], auto: bool
) -> str:
    """纵轴范围文本（参数区只读显示 + 测试可断言）。"""
    top, bottom = y_range(params, levels, auto)
    return (
        f"纵轴 {format_level(top)} ~ {format_level(bottom)} {params.unit}"
        + ("（自动适配）" if auto and levels else "（参考电平口径）")
    )


def palette_for(dark: bool) -> dict:
    """浅/暗主题调色板（画布与状态文字共用）。"""
    if dark:
        return {
            "bg": "#1E1E1E",
            "plot_bg": "#141414",
            "grid": "#3C3C3C",
            "axis": "#9E9E9E",
            "text": "#E6E6E6",
            "sub": "#9E9E9E",
            "trace": "#FFD54F",
            "warn": "#FF8A65",
            "marker": "#4FC3F7",
            "cursor": "#90A4AE",
            "panel": "#CC101010",
        }
    return {
        "bg": "#FFFFFF",
        "plot_bg": "#FAFAFA",
        "grid": "#D0D0D0",
        "axis": "#8A8A8A",
        "text": "#212121",
        "sub": "#666666",
        "trace": "#1E88E5",
        "warn": "#D84315",
        "marker": "#6A1B9A",
        "cursor": "#607D8B",
        "panel": "#E6FFFFFF",
    }


# ══════════════════════════════════════════════════════════════════
# Qt 层（无 Qt 环境仍可导入上面的纯逻辑层）
# ══════════════════════════════════════════════════════════════════

try:
    from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPolygonF
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    import app_icons

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - 无 Qt 环境（CI 纯逻辑）不执行 Qt 层
    _QT_AVAILABLE = False


if _QT_AVAILABLE:

    class SpectrumCanvas(QWidget):
        """频谱图画布：QPainter 自绘（paintEvent 与导出共用 _paint）。"""

        add_marker_requested = Signal(float)  # 绘图区内左键点击 → 该频率处添加标记

        def __init__(self, parent=None):
            super().__init__(parent)
            self._trace: Optional[SpectrumTrace] = None
            self._auto_y = False
            self._palette = palette_for(False)
            self._markers: Tuple[Marker, ...] = ()
            self._cursor: Optional[Tuple[int, float, float]] = None
            self._dark = False
            self._ref_index = 0  # 两点测量的参考标记下标（Δ 显示哪两个点之间）
            self.setMinimumSize(400, 220)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setMouseTracking(True)
            self.setCursor(Qt.CursorShape.CrossCursor)

        # ── 对外接口 ──────────────────────────────────────────────
        def set_trace(self, trace: Optional[SpectrumTrace]) -> None:
            self._trace = trace
            self._cursor = None  # 轨迹换了，旧读数作废（否则十字与读数框口径不一致）
            self.update()

        def set_auto_y(self, auto: bool) -> None:
            self._auto_y = bool(auto)
            self.update()

        def apply_palette(self, dark: bool) -> None:
            self._dark = bool(dark)
            self._palette = palette_for(dark)
            self.update()

        def render_image(self, width: int = 1600, height: int = 1000) -> QImage:
            """渲染到离屏图像（导出 PNG 与测试共用同一绘制逻辑）。"""
            image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QColor(self._palette["bg"]))
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            try:
                self._paint(painter, QRect(0, 0, width, height))
            finally:
                painter.end()
            return image

        # ── 几何与字体（_paint 与鼠标换算共用同一份计算）────────────
        def _fonts(self):
            """返回 (标题, 刻度, 注记, 提示, 基础磅值)——字号随软件字体设置缩放。"""
            base_pt = self.font().pointSizeF() or 9.0
            title = QFont(self.font())
            title.setPointSizeF(max(base_pt + 3, 10.0))
            title.setBold(True)
            label = QFont(self.font())
            label.setPointSizeF(max(base_pt - 1, 7.0))
            note = QFont(self.font())
            note.setPointSizeF(max(base_pt - 2, 7.0))
            hint = QFont(label)
            hint.setPointSizeF(max(base_pt + 1, 9.0))
            return title, label, note, hint, base_pt

        def _y_labels(self, trace: Optional[SpectrumTrace]) -> Tuple[str, ...]:
            """纵轴刻度文本（顶端带单位；自动适配按步长定小数位）。"""
            if trace is None:
                return ()
            params = trace.params
            ticks = y_ticks(params, trace.levels, self._auto_y)
            if self._auto_y and trace.levels:
                top, bottom = y_range(params, trace.levels, self._auto_y)
                decimals = auto_tick_decimals((top - bottom) / params.y_divs)
                labels = [format_fixed(v, decimals) for v in ticks]
            else:
                labels = [format_level(v) for v in ticks]
            labels[0] = f"{labels[0]} {params.unit}"
            return tuple(labels)

        def plot_rect(self, rect: Optional[QRect] = None) -> Optional[QRect]:
            """绘图区矩形；空间不足返回 None（鼠标换算与 _paint 共用）。"""
            rect = self.rect() if rect is None else rect
            _, label_font, _, _, _ = self._fonts()
            metrics = QFontMetrics(label_font)
            labels = self._y_labels(self._trace)
            y_label_w = max([metrics.horizontalAdvance(t) for t in labels], default=0)
            left_margin = max(52, y_label_w + 12)
            top_band = 36 if self._trace is not None else 20
            margin = 12
            x_label_h = metrics.height() + 14
            plot = QRect(
                rect.left() + margin + left_margin,
                rect.top() + margin + top_band,
                rect.width() - 2 * margin - left_margin - 16,
                rect.height() - 2 * margin - top_band - x_label_h,
            )
            if plot.width() < 80 or plot.height() < 60:
                return None  # 可用空间不足，避免负尺寸绘制
            return plot

        # ── 鼠标测量（R7 / R8）────────────────────────────────────
        def set_markers(self, markers: Sequence[Marker]) -> None:
            self._markers = tuple(markers)
            self.update()

        def markers(self) -> Tuple[Marker, ...]:
            return self._markers

        def set_reference(self, ref_index: int) -> None:
            """设置两点测量的参考标记下标（影响图上 Δ 注记标注哪两个点）。"""
            self._ref_index = int(ref_index)
            self.update()

        def cursor_readout(self) -> Optional[Tuple[int, float, float]]:
            """当前光标读数 (索引, 频率, 幅值)；无则 None。"""
            return self._cursor

        def point_at(self, pos) -> Optional[Tuple[int, float, float]]:
            """屏幕坐标 → (索引, 频率, 幅值)；不在绘图区或无数据返回 None。"""
            trace = self._trace
            plot = self.plot_rect()
            if trace is None or plot is None or not plot.contains(pos):
                return None
            ratio = (pos.x() - plot.left()) / max(1, plot.width())
            ratio = 0.0 if ratio < 0.0 else (1.0 if ratio > 1.0 else ratio)
            freq = trace.params.start_hz + trace.params.span_hz * ratio
            index = nearest_index(trace.freqs, freq)
            return index, trace.freqs[index], trace.levels[index]

        def mouseMoveEvent(self, event):  # noqa: N802 - Qt 命名
            point = self.point_at(event.position().toPoint())
            if point != self._cursor:
                self._cursor = point
                self.update()
            super().mouseMoveEvent(event)

        def leaveEvent(self, event):  # noqa: N802 - Qt 命名
            if self._cursor is not None:
                self._cursor = None
                self.update()
            super().leaveEvent(event)

        def mousePressEvent(self, event):  # noqa: N802 - Qt 命名
            if event.button() == Qt.MouseButton.LeftButton:
                point = self.point_at(event.position().toPoint())
                if point is not None:
                    self.add_marker_requested.emit(point[1])
                    event.accept()
                    return
            super().mousePressEvent(event)

        # ── 绘制 ──────────────────────────────────────────────────
        def paintEvent(self, event):  # noqa: N802 - Qt 命名
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            try:
                self._paint(painter, self.rect())
            finally:
                painter.end()

        def _paint(self, painter: QPainter, rect: QRect) -> None:
            palette = self._palette
            painter.fillRect(rect, QColor(palette["bg"]))

            title_font, label_font, note_font, hint_font, base_pt = self._fonts()
            label_metrics = QFontMetrics(label_font)

            trace = self._trace
            params = trace.params if trace is not None else None
            levels = trace.levels if trace is not None else ()
            labels = self._y_labels(trace)
            ticks = y_ticks(params, levels, self._auto_y) if params is not None else ()

            plot = self.plot_rect(rect)
            if plot is None:
                return  # 可用空间不足，避免负尺寸绘制
            margin = 12
            left_margin = plot.left() - rect.left() - margin

            # ── 绘图区背景 + 网格 + 边框 ──
            painter.fillRect(plot, QColor(palette["plot_bg"]))
            painter.setPen(QPen(QColor(palette["grid"]), 1))
            for i in range(1, X_DIVS):
                x = plot.left() + int(plot.width() * i / X_DIVS)
                painter.drawLine(x, plot.top(), x, plot.bottom())
            for j in range(1, max(0, len(ticks) - 1)):
                y = plot.top() + int(plot.height() * j / max(1, len(ticks) - 1))
                painter.drawLine(plot.left(), y, plot.right(), y)
            painter.setPen(QPen(QColor(palette["axis"]), 1))
            painter.drawRect(plot)

            # ── 纵轴刻度 ──
            painter.setFont(label_font)
            painter.setPen(QPen(QColor(palette["sub"])))
            for i, text in enumerate(labels):
                y = plot.top() + int(plot.height() * i / max(1, len(labels) - 1))
                box = QRect(
                    rect.left() + margin, y - label_metrics.height() // 2,
                    left_margin - 8, label_metrics.height(),
                )
                painter.drawText(
                    box,
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                    text,
                )

            # ── 横轴刻度（首/末标签贴边对齐，避免越出画布或压住纵轴标签）──
            if params is not None:
                max_labels = max(3, min(X_DIVS + 1, plot.width() // 78))
                label_w = 120
                for div, text in x_tick_labels(params, max_labels):
                    x = plot.left() + int(plot.width() * div / X_DIVS)
                    if div == 0:
                        box = QRect(x, plot.bottom() + 3, label_w, label_metrics.height())
                        align = Qt.AlignmentFlag.AlignLeft
                    elif div == X_DIVS:
                        box = QRect(
                            plot.right() - label_w,
                            plot.bottom() + 3,
                            label_w,
                            label_metrics.height(),
                        )
                        align = Qt.AlignmentFlag.AlignRight
                    else:
                        box = QRect(
                            x - label_w // 2,
                            plot.bottom() + 3,
                            label_w,
                            label_metrics.height(),
                        )
                        align = Qt.AlignmentFlag.AlignHCenter
                    painter.drawText(box, int(align), text)

            if trace is None:
                hint_font = QFont(label_font)
                hint_font.setPointSizeF(max(base_pt + 1, 9.0))
                painter.setFont(hint_font)
                painter.setPen(QPen(QColor(palette["sub"])))
                painter.drawText(
                    plot,
                    int(Qt.AlignmentFlag.AlignCenter),
                    "输入频谱仪参数与 trace 数值后点击「绘制」",
                )
                return

            # ── 标题 + 参数注记 ──
            title_box = QRect(
                rect.left() + margin, rect.top() + margin - 2,
                rect.width() - 2 * margin, max(18, int(base_pt + 6)),
            )
            painter.setFont(title_font)
            painter.setPen(QPen(QColor(palette["text"])))
            painter.drawText(
                title_box,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                _TITLE,
            )
            painter.setFont(note_font)
            painter.setPen(QPen(QColor(palette["sub"])))
            note = note_text(params, trace.n_points)
            painter.drawText(
                QRect(
                    rect.left() + margin,
                    title_box.bottom(),
                    rect.width() - 2 * margin,
                    label_metrics.height(),
                ),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                QFontMetrics(note_font).elidedText(
                    note, Qt.TextElideMode.ElideRight, rect.width() - 2 * margin
                ),
            )

            # ── 迹线（越界点裁剪到边缘）──
            top, bottom = y_range(params, levels, self._auto_y)
            span = (top - bottom) or 1.0
            count = trace.n_points
            polygon = QPolygonF()
            for i, value in enumerate(levels):
                ratio = (top - value) / span
                ratio = 0.0 if ratio < 0.0 else (1.0 if ratio > 1.0 else ratio)
                x = plot.left() + (plot.width() * i / (count - 1) if count > 1 else 0.0)
                y = plot.top() + ratio * plot.height()
                polygon.append(QPointF(x, y))

            painter.save()
            painter.setClipRect(plot)
            painter.setPen(QPen(QColor(palette["trace"]), 1.4))
            painter.drawPolyline(polygon)
            if count <= MARKER_MAX_POINTS:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette["trace"]))
                for point in polygon:
                    painter.drawEllipse(point, 1.8, 1.8)
            painter.restore()

            self._paint_measure(painter, plot, trace, label_font, note_font)

        def _paint_measure(
            self, painter: QPainter, plot: QRect, trace: SpectrumTrace, label_font, note_font
        ) -> None:
            """标记 / Δ 注记 / 光标十字与读数框（导出图与屏幕同一实现）。"""
            palette = self._palette
            params = trace.params
            count = trace.n_points
            top, bottom = y_range(params, trace.levels, self._auto_y)
            span = (top - bottom) or 1.0

            def x_of(index: int) -> float:
                return plot.left() + (
                    plot.width() * index / (count - 1) if count > 1 else 0.0
                )

            def y_of(level: float) -> float:
                ratio = (top - level) / span
                ratio = 0.0 if ratio < 0.0 else (1.0 if ratio > 1.0 else ratio)
                return plot.top() + ratio * plot.height()

            # ── 标记竖虚线 + 圆点 + M? 标签（每个标记一种颜色）；光标十字 ──
            painter.save()
            painter.setClipRect(plot)
            for order, marker in enumerate(self._markers):
                color = QColor(marker_color(self._dark, order))
                x, y = x_of(marker.index), y_of(marker.level)
                painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(x, plot.top()), QPointF(x, y))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(x, y), 3.2, 3.2)
                # 标记名贴在圆点旁边，颜色与标记一致，便于与表格对应
                painter.setFont(label_font)
                painter.setPen(QPen(color))
                painter.drawText(
                    QRectF(x + 5, y + 2, 46, label_font.pointSizeF() + 8),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                    marker.label,
                )
            if self._cursor is not None:
                index, _freq, level = self._cursor
                x, y = x_of(index), y_of(level)
                painter.setPen(
                    QPen(QColor(palette["cursor"]), 1, Qt.PenStyle.DotLine)
                )
                painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
                painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette["cursor"]))
                painter.drawEllipse(QPointF(x, y), 3.0, 3.0)
            painter.restore()

            # ── 标记读数 + Δ 注记（右上角，导出图自带说明；每行用标记自身颜色）──
            if self._markers:
                painter.setFont(note_font)
                metrics = QFontMetrics(note_font)
                lines = [
                    (
                        f"{marker.label} {readout_text(marker.freq_hz, marker.level, params.unit)}",
                        QColor(marker_color(self._dark, order)),
                    )
                    for order, marker in enumerate(self._markers)
                ]
                delta = delta_text(self._markers, self._ref_index)
                if delta:
                    lines.append((delta, QColor(palette["text"])))
                width = max(metrics.horizontalAdvance(text) for text, _ in lines) + 16
                height = metrics.height() * len(lines) + 10
                box = QRect(
                    plot.right() - width - 6,
                    plot.top() + 6,
                    width,
                    height,
                )
                painter.setPen(QPen(QColor(palette["axis"]), 1))
                painter.setBrush(QColor(palette["panel"]))
                painter.drawRect(box)
                for i, (text, color) in enumerate(lines):
                    painter.setPen(QPen(color))
                    painter.drawText(
                        QRect(
                            box.left() + 8,
                            box.top() + 5 + i * metrics.height(),
                            box.width() - 16,
                            metrics.height(),
                        ),
                        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                        text,
                    )

            # ── 光标读数框（跟随光标，夹在绘图区内）──
            if self._cursor is not None:
                index, freq, level = self._cursor
                painter.setFont(note_font)
                metrics = QFontMetrics(note_font)
                text = readout_text(freq, level, params.unit)
                width = metrics.horizontalAdvance(text) + 16
                height = metrics.height() + 8
                x = x_of(index) + 14
                y = y_of(level) - height - 10
                if x + width > plot.right() - 4:
                    x = x_of(index) - width - 14
                if x < plot.left() + 4:
                    x = plot.left() + 4
                if y < plot.top() + 4:
                    y = y_of(level) + 14
                box = QRect(int(x), int(y), width, height)
                painter.setPen(QPen(QColor(palette["cursor"]), 1))
                painter.setBrush(QColor(palette["panel"]))
                painter.drawRect(box)
                painter.setPen(QPen(QColor(palette["text"])))
                painter.drawText(
                    box.adjusted(8, 0, -8, 0),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    text,
                )

    class SpectrumWidget(QWidget):
        """频谱图标签页：工具栏 + 参数表单 + trace 输入 + 自绘画布。"""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._trace: Optional[SpectrumTrace] = None
            self._palette = palette_for(False)
            self._freq_unit = DEFAULT_FREQ_UNIT
            self._sync_guard = False
            self._status_error = False
            self._marker_freqs: list = []  # MARK 标记锚点（频率，Hz）
            self._dark = False
            self._ref_guard = False

            layout = QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(4)

            # ── 工具栏 ──
            toolbar = QHBoxLayout()
            toolbar.setSpacing(6)

            self.draw_btn = QPushButton("绘制")
            self.draw_btn.setIcon(app_icons.load_icon("chart-spline"))
            self.draw_btn.setToolTip("按当前参数解析 trace 数值并绘制频谱图")
            self.draw_btn.clicked.connect(self._on_draw)
            toolbar.addWidget(self.draw_btn)

            self.paste_btn = QPushButton("粘贴")
            self.paste_btn.setIcon(app_icons.load_icon("clipboard-paste"))
            self.paste_btn.setToolTip("从剪贴板读入 trace 数值")
            self.paste_btn.clicked.connect(self._on_paste)
            toolbar.addWidget(self.paste_btn)

            self.clear_btn = QPushButton("清空")
            self.clear_btn.setIcon(app_icons.load_icon("eraser"))
            self.clear_btn.setToolTip("清空 trace 数据与图形")
            self.clear_btn.clicked.connect(self._on_clear)
            toolbar.addWidget(self.clear_btn)

            self.export_btn = QPushButton("导出 PNG")
            self.export_btn.setIcon(app_icons.load_icon("image"))
            self.export_btn.setToolTip("导出当前频谱图（含标题与参数注记）为 PNG")
            self.export_btn.clicked.connect(self._on_export_png)
            toolbar.addWidget(self.export_btn)

            self.auto_check = QCheckBox("纵轴自动适配")
            self.auto_check.setToolTip("勾选后纵轴按数据 min/max 自动取范围（默认参考电平口径）")
            self.auto_check.toggled.connect(self._on_auto_toggled)
            toolbar.addWidget(self.auto_check)

            toolbar.addStretch()
            self.status_label = QLabel("就绪")
            self.status_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            toolbar.addWidget(self.status_label)
            layout.addLayout(toolbar)

            # ── 测量工具栏（R7 / R8）──
            measure_bar = QHBoxLayout()
            measure_bar.setSpacing(6)

            self.peak_btn = QPushButton("峰值搜索")
            self.peak_btn.setIcon(app_icons.load_icon("crosshair"))
            self.peak_btn.setToolTip("把选中标记移到全局最大幅值点（无标记时新建 M1）")
            self.peak_btn.clicked.connect(self._on_search_peak)
            measure_bar.addWidget(self.peak_btn)

            self.next_peak_btn = QPushButton("下一个峰值")
            self.next_peak_btn.setIcon(app_icons.load_icon("chevrons-right"))
            self.next_peak_btn.setToolTip("把选中标记移到下一个局部峰（环形搜索）")
            self.next_peak_btn.clicked.connect(self._on_next_peak)
            measure_bar.addWidget(self.next_peak_btn)

            self.del_marker_btn = QPushButton("删除标记")
            self.del_marker_btn.setIcon(app_icons.load_icon("delete"))
            self.del_marker_btn.setToolTip("删除标记表中选中的一行（未选则删最后一个）")
            self.del_marker_btn.clicked.connect(self._on_delete_marker)
            measure_bar.addWidget(self.del_marker_btn)

            self.clear_markers_btn = QPushButton("清空标记")
            self.clear_markers_btn.setIcon(app_icons.load_icon("eraser"))
            self.clear_markers_btn.setToolTip("清除全部标记")
            self.clear_markers_btn.clicked.connect(self._on_clear_markers)
            measure_bar.addWidget(self.clear_markers_btn)

            measure_bar.addWidget(QLabel("Δ 参考"))
            self.ref_combo = QComboBox()
            self.ref_combo.setToolTip("两点测量（Δ）以哪个标记为参考：Δ 显示该标记与相邻标记之间的差值")
            self.ref_combo.setMinimumWidth(64)
            self.ref_combo.currentIndexChanged.connect(self._on_reference_changed)
            measure_bar.addWidget(self.ref_combo)

            self.measure_label = QLabel("点击绘图区添加标记；鼠标悬停读取频点与幅值")
            self.measure_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            measure_bar.addWidget(self.measure_label)
            measure_bar.addStretch()
            layout.addLayout(measure_bar)

            # ── 主体：左参数 / 右画布 + 标记表 + 数据 ──
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._build_param_panel())

            right = QSplitter(Qt.Orientation.Vertical)
            self._right_splitter = right
            self.canvas = SpectrumCanvas()
            self.canvas.add_marker_requested.connect(self._on_canvas_marker)
            right.addWidget(self.canvas)
            right.addWidget(self._build_marker_table())
            right.addWidget(self._build_input_panel())
            right.setSizes([520, 0, 200])
            right.setStretchFactor(0, 1)
            right.setStretchFactor(1, 0)
            right.setStretchFactor(2, 0)
            splitter.addWidget(right)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 1)
            splitter.setSizes([340, 900])
            layout.addWidget(splitter, 1)

            self._write_freq_fields(
                DEFAULT_START_HZ, DEFAULT_STOP_HZ, None, None
            )
            self._refresh_axis_label()
            self.restyle_for_theme(False)

        # ── 构建：参数区 ──────────────────────────────────────────
        def _build_param_panel(self) -> QWidget:
            panel = QWidget()
            panel.setMinimumWidth(300)
            panel.setMaximumWidth(460)
            outer = QVBoxLayout(panel)
            outer.setContentsMargins(0, 0, 0, 0)

            box = QGroupBox("频谱仪参数")
            form = QFormLayout(box)
            form.setContentsMargins(8, 8, 8, 8)
            form.setSpacing(6)

            self.freq_unit_combo = QComboBox()
            self.freq_unit_combo.addItems(list(FREQ_UNITS))
            self.freq_unit_combo.setCurrentText(DEFAULT_FREQ_UNIT)
            self.freq_unit_combo.currentTextChanged.connect(self._on_freq_unit_changed)
            form.addRow("频率单位", self.freq_unit_combo)

            self.start_edit = self._freq_edit()
            self.stop_edit = self._freq_edit()
            self.center_edit = self._freq_edit()
            self.span_edit = self._freq_edit()
            self.start_edit.editingFinished.connect(
                lambda: self._on_freq_edited("start")
            )
            self.stop_edit.editingFinished.connect(
                lambda: self._on_freq_edited("stop")
            )
            self.center_edit.editingFinished.connect(
                lambda: self._on_freq_edited("center")
            )
            self.span_edit.editingFinished.connect(
                lambda: self._on_freq_edited("span")
            )
            form.addRow("起始频率", self.start_edit)
            form.addRow("终止频率", self.stop_edit)
            form.addRow("中心频率", self.center_edit)
            form.addRow("扫宽 Span", self.span_edit)

            self.rbw_edit, self.rbw_unit_combo = self._bw_row("RBW 留空则不标注")
            form.addRow("RBW", self.rbw_edit)
            form.addRow("RBW 单位", self.rbw_unit_combo)
            self.vbw_edit, self.vbw_unit_combo = self._bw_row("VBW 留空则不标注")
            form.addRow("VBW", self.vbw_edit)
            form.addRow("VBW 单位", self.vbw_unit_combo)

            self.ref_edit = QLineEdit(f"{DEFAULT_REF_LEVEL_DB:g}")
            self.ref_edit.editingFinished.connect(self._refresh_axis_label)
            form.addRow("参考电平", self.ref_edit)

            self.dbdiv_edit = QLineEdit(f"{DEFAULT_DB_PER_DIV:g}")
            self.dbdiv_edit.editingFinished.connect(self._refresh_axis_label)
            form.addRow("每格 dB", self.dbdiv_edit)

            self.ydivs_spin = QSpinBox()
            self.ydivs_spin.setRange(MIN_Y_DIVS, MAX_Y_DIVS)
            self.ydivs_spin.setValue(DEFAULT_Y_DIVS)
            self.ydivs_spin.valueChanged.connect(self._refresh_axis_label)
            form.addRow("纵向格数", self.ydivs_spin)

            self.unit_combo = QComboBox()
            self.unit_combo.addItems(list(LEVEL_UNITS))
            self.unit_combo.currentTextChanged.connect(self._refresh_axis_label)
            form.addRow("幅值单位", self.unit_combo)

            self.convert_check = QCheckBox("输入按 dBm，50Ω 换算到所选单位")
            self.convert_check.toggled.connect(self._refresh_axis_label)
            form.addRow("", self.convert_check)

            self.detector_combo = QComboBox()
            self.detector_combo.addItems(list(DETECTORS))
            self.detector_combo.currentTextChanged.connect(self._refresh_axis_label)
            form.addRow("检波方式", self.detector_combo)

            self.axis_label = QLabel("—")
            self.axis_label.setWordWrap(True)
            form.addRow("纵轴范围", self.axis_label)

            outer.addWidget(box)

            hint = QLabel(
                "参数改完按回车或移开焦点即自动联动：\n"
                "改「起始/终止」重算中心与扫宽；\n改「中心/扫宽」重算起始与终止。"
            )
            hint.setWordWrap(True)
            self.hint_label = hint
            outer.addWidget(hint)
            outer.addStretch()
            return panel

        @staticmethod
        def _freq_edit() -> QLineEdit:
            edit = QLineEdit()
            edit.setToolTip("改完按回车（或点其它控件）触发四个频率字段联动")
            return edit

        def _bw_row(self, placeholder: str):
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            combo = QComboBox()
            combo.addItems(list(RBW_UNITS))
            combo.setCurrentText(DEFAULT_RBW_UNIT)
            edit._unit = combo.currentText()  # type: ignore[attr-defined]
            combo.currentTextChanged.connect(
                lambda text, e=edit, c=combo: self._on_bw_unit_changed(e, c, text)
            )
            return edit, combo

        # ── 构建：数据区 ──────────────────────────────────────────
        def _build_input_panel(self) -> QWidget:
            panel = QWidget()
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)

            label = QLabel(
                "trace 数值（每个数值一个扫频点，空格/逗号/分号/换行分隔，"
                "点数即频率轴点数）"
            )
            layout.addWidget(label)

            self.trace_edit = QPlainTextEdit()
            self.trace_edit.setPlaceholderText("-62.5 -63.1 -62.8 ...")
            layout.addWidget(self.trace_edit, 1)
            return panel

        def _build_marker_table(self) -> QWidget:
            """标记表（R8）：仅存在标记时可见，避免压缩画布高度。"""
            table = QTableWidget(0, 5)
            table.setHorizontalHeaderLabels(
                ["标记", "频率", "幅值", "Δ频率", "Δ幅值"]
            )
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setMaximumHeight(150)
            table.setMinimumHeight(110)
            table.setVisible(False)
            self.marker_table = table
            return table

        # ── 频率字段双向联动 ─────────────────────────────────────
        def _on_freq_edited(self, changed: str) -> None:
            if self._sync_guard:
                return
            try:
                start, stop, center, span = self._read_freq_fields()
                start, stop, center, span = resolve_freq_inputs(
                    changed, start, stop, center, span
                )
            except SpectrumInputError as exc:
                self._set_status(f"⚠ {exc}", error=True)
                return
            self._write_freq_fields(start, stop, center, span)
            self._refresh_axis_label()
            self._set_status("频率参数已联动更新")

        def _on_freq_unit_changed(self, new_unit: str) -> None:
            if self._sync_guard or new_unit == self._freq_unit:
                return
            factor = FREQ_UNITS[self._freq_unit] / FREQ_UNITS[new_unit]
            self._freq_unit = new_unit
            for edit in (
                self.start_edit,
                self.stop_edit,
                self.center_edit,
                self.span_edit,
            ):
                value = self._try_float(edit.text())
                if value is not None:
                    edit.setText(_fmt_number(value * factor))
            self._refresh_axis_label()

        def _on_bw_unit_changed(self, edit: QLineEdit, combo: QComboBox, new_unit: str) -> None:
            value = self._try_float(edit.text())
            if value is None:
                return
            old_unit = getattr(edit, "_unit", None)
            edit._unit = new_unit
            if old_unit and old_unit in RBW_UNITS:
                edit.setText(
                    _fmt_number(value * RBW_UNITS[old_unit] / RBW_UNITS[new_unit])
                )

        def _read_freq_fields(self) -> Tuple[float, float, float, float]:
            unit = self._freq_unit
            return (
                units_to_hz(self._read_float(self.start_edit, "起始频率"), unit),
                units_to_hz(self._read_float(self.stop_edit, "终止频率"), unit),
                units_to_hz(self._read_float(self.center_edit, "中心频率"), unit),
                units_to_hz(self._read_float(self.span_edit, "扫宽"), unit),
            )

        def _write_freq_fields(
            self,
            start_hz: float,
            stop_hz: float,
            center_hz: Optional[float],
            span_hz: Optional[float],
        ) -> None:
            unit = self._freq_unit
            if center_hz is None:
                center_hz = (start_hz + stop_hz) / 2.0
            if span_hz is None:
                span_hz = stop_hz - start_hz
            self._sync_guard = True
            try:
                self.start_edit.setText(_fmt_number(to_freq_unit(start_hz, unit)))
                self.stop_edit.setText(_fmt_number(to_freq_unit(stop_hz, unit)))
                self.center_edit.setText(_fmt_number(to_freq_unit(center_hz, unit)))
                self.span_edit.setText(_fmt_number(to_freq_unit(span_hz, unit)))
            finally:
                self._sync_guard = False

        # ── 参数读取 ──────────────────────────────────────────────
        def _read_float(self, edit: QLineEdit, name: str) -> float:
            text = edit.text().strip()
            if not text:
                raise SpectrumInputError(f"{name}不能为空")
            try:
                value = float(text)
            except ValueError:
                raise SpectrumInputError(f"{name}不是有效数值：{text}") from None
            if not math.isfinite(value):
                raise SpectrumInputError(f"{name}不是有效数值：{text}")
            return value

        @staticmethod
        def _try_float(text: str) -> Optional[float]:
            try:
                value = float(str(text).strip())
            except (TypeError, ValueError):
                return None
            return value if math.isfinite(value) else None

        def _read_optional_hz(
            self, edit: QLineEdit, combo: QComboBox, name: str
        ) -> Optional[float]:
            text = edit.text().strip()
            if not text:
                return None
            return units_to_hz(self._read_float(edit, name), combo.currentText())

        def read_params(self) -> SpectrumParams:
            """读取并校验当前参数（错误抛 SpectrumInputError）。"""
            params = SpectrumParams(
                start_hz=units_to_hz(self._read_float(self.start_edit, "起始频率"), self._freq_unit),
                stop_hz=units_to_hz(self._read_float(self.stop_edit, "终止频率"), self._freq_unit),
                ref_level_db=self._read_float(self.ref_edit, "参考电平"),
                db_per_div=self._read_float(self.dbdiv_edit, "每格 dB"),
                y_divs=int(self.ydivs_spin.value()),
                unit=self.unit_combo.currentText(),
                convert_50ohm=self.convert_check.isChecked(),
                rbw_hz=self._read_optional_hz(self.rbw_edit, self.rbw_unit_combo, "RBW"),
                vbw_hz=self._read_optional_hz(self.vbw_edit, self.vbw_unit_combo, "VBW"),
                detector=self.detector_combo.currentText(),
            )
            validate_params(params)
            return params

        # ── 动作 ──────────────────────────────────────────────────
        def _on_draw(self) -> None:
            try:
                params = self.read_params()
                trace = build_trace(self.trace_edit.toPlainText(), params)
            except SpectrumInputError as exc:
                self._set_status(f"⚠ {exc}", error=True)
                return
            self._trace = trace
            self.canvas.set_auto_y(self.auto_check.isChecked())
            self.canvas.set_trace(trace)
            text = status_text(trace)
            out_of_range = count_out_of_range(
                params, trace.levels, self.auto_check.isChecked()
            )
            if out_of_range:
                text += f"  ⚠ {out_of_range} 个点超出纵轴范围（已裁剪到边缘）"
            self._set_status(text, error=bool(out_of_range))
            self._refresh_axis_label()
            dropped = self._refresh_markers()
            if dropped:
                self._set_status(
                    f"{text}  ⚠ {dropped} 个标记超出当前扫描范围，已丢弃",
                    error=True,
                )

        def _on_paste(self) -> None:
            text = QApplication.clipboard().text()
            if not text.strip():
                self._set_status("⚠ 剪贴板没有文本内容", error=True)
                return
            self.trace_edit.setPlainText(text)
            self._set_status("已从剪贴板读入 trace 数值，点「绘制」出图")

        def _on_clear(self) -> None:
            self.trace_edit.clear()
            self._trace = None
            self.canvas.set_trace(None)
            self._refresh_markers()
            self._refresh_axis_label()
            self._set_status("就绪")

        def _on_auto_toggled(self, checked: bool) -> None:
            self.canvas.set_auto_y(checked)
            self._refresh_axis_label()
            if self._trace is not None:
                out_of_range = count_out_of_range(
                    self._trace.params, self._trace.levels, checked
                )
                text = status_text(self._trace)
                if out_of_range:
                    text += f"  ⚠ {out_of_range} 个点超出纵轴范围（已裁剪到边缘）"
                self._set_status(text, error=bool(out_of_range))

        def _on_export_png(self) -> None:
            path, _ = QFileDialog.getSaveFileName(
                self, "导出频谱图", "spectrum.png", "PNG 图片 (*.png)"
            )
            if not path:
                return
            if not path.lower().endswith(".png"):
                path += ".png"
            self._save_png(path)

        def _save_png(self, path: str) -> bool:
            """渲染并保存 PNG（导出按钮与测试共用）。"""
            ok = bool(self.canvas.render_image().save(path, "PNG"))
            self._set_status(
                f"已导出：{path}" if ok else f"⚠ 导出失败：{path}", error=not ok
            )
            return ok

        # ── MARK 标记与测量（R7 / R8）──────────────────────────────
        def markers(self) -> Tuple[Marker, ...]:
            return self.canvas.markers()

        def _on_canvas_marker(self, freq_hz: float) -> None:
            """绘图区点击 → 在该频率处添加一个标记（吸附到最近数据点）。"""
            if self._trace is None:
                self._set_status("⚠ 请先绘制 trace 数据再添加标记", error=True)
                return
            if len(self._marker_freqs) >= MAX_MARKERS:
                self._set_status(
                    f"⚠ 最多 {MAX_MARKERS} 个标记，请先删除或清空", error=True
                )
                return
            self._marker_freqs.append(freq_hz)
            self._refresh_markers()
            markers = self.canvas.markers()
            if markers:
                self._set_status(
                    f"已添加 {marker_note(markers[-1], self._trace.params.unit)}"
                )

        def _selected_marker_row(self) -> int:
            """标记表选中行；未选中时返回最后一个标记行（无标记返回 -1）。"""
            if not self._marker_freqs:
                return -1
            model = self.marker_table.selectionModel()
            rows = model.selectedRows() if model is not None else []
            return rows[0].row() if rows else len(self._marker_freqs) - 1

        def _set_marker_at(self, row: int, index: int, note: str) -> None:
            """把第 row 个标记移到数据点 index（row < 0 → 新建一个标记）。"""
            if self._trace is None:
                self._set_status("⚠ 请先绘制 trace 数据", error=True)
                return
            freq_hz = self._trace.freqs[index]
            if row < 0:
                if len(self._marker_freqs) >= MAX_MARKERS:
                    self._set_status(
                        f"⚠ 最多 {MAX_MARKERS} 个标记，请先删除或清空", error=True
                    )
                    return
                self._marker_freqs.append(freq_hz)
            else:
                self._marker_freqs[row] = freq_hz
            self._refresh_markers()
            markers = self.canvas.markers()
            target_row = row if row >= 0 else len(markers) - 1
            if 0 <= target_row < len(markers):
                self._set_status(
                    f"{note}：{marker_note(markers[target_row], self._trace.params.unit)}"
                )

        def _on_search_peak(self) -> None:
            if self._trace is None:
                self._set_status("⚠ 请先绘制 trace 数据", error=True)
                return
            self._set_marker_at(
                self._selected_marker_row(), peak_index(self._trace.levels), "峰值搜索"
            )

        def _on_next_peak(self) -> None:
            if self._trace is None:
                self._set_status("⚠ 请先绘制 trace 数据", error=True)
                return
            row = self._selected_marker_row()
            if row < 0:
                self._on_search_peak()  # 无标记 → 直接在峰值处新建 M1
                return
            current = nearest_index(self._trace.freqs, self._marker_freqs[row])
            nxt = next_peak_index(self._trace.levels, current)
            if nxt is None:
                self._set_status(
                    f"⚠ 未找到显著度 ≥ {PEAK_MIN_PROMINENCE_DB:g} dB 的局部峰", error=True
                )
                return
            if nxt == current:
                self._set_status("⚠ 已是唯一显著峰，未找到其他峰", error=True)
                return
            self._set_marker_at(row, nxt, "下一个峰值")

        def _on_delete_marker(self) -> None:
            if not self._marker_freqs:
                self._set_status("⚠ 当前没有标记", error=True)
                return
            row = self._selected_marker_row()
            if row < 0:
                row = len(self._marker_freqs) - 1
            self._marker_freqs.pop(row)
            self._refresh_markers()
            self._set_status(f"已删除标记（剩余 {len(self._marker_freqs)} 个）")

        def _on_clear_markers(self) -> None:
            if not self._marker_freqs:
                self._set_status("⚠ 当前没有标记", error=True)
                return
            self._marker_freqs = []
            self._refresh_markers()
            self._set_status("已清空全部标记")

        def _refresh_markers(self) -> int:
            """按频率锚点重建标记，刷新画布/标记表/测量文本；返回被丢弃的标记数。"""
            dropped = 0
            if self._trace is None:
                self._marker_freqs = []
                markers: Tuple[Marker, ...] = ()
            else:
                markers = markers_for(self._trace, self._marker_freqs)
                dropped = len(self._marker_freqs) - len(markers)
                self._marker_freqs = [m.freq_hz for m in markers]
            self._sync_reference_combo(markers)
            self.canvas.set_markers(markers)
            self.canvas.set_reference(self._ref_index())
            self._fill_marker_table(markers)
            self.measure_label.setText(self._measure_text(markers))
            return dropped

        def _ref_index(self) -> int:
            """当前两点测量的参考标记下标（越界回落 0）。"""
            index = int(self.ref_combo.currentIndex())
            count = len(self._marker_freqs)
            if count == 0 or index < 0 or index > count - 1:
                return 0
            return index

        def _sync_reference_combo(self, markers: Tuple[Marker, ...]) -> None:
            """参考标记下拉跟随标记列表（保持原选择，越界回落第一个）。"""
            labels = [m.label for m in markers]
            current = self.ref_combo.currentIndex()
            self._ref_guard = True
            try:
                self.ref_combo.clear()
                self.ref_combo.addItems(labels)
                if labels:
                    self.ref_combo.setCurrentIndex(
                        current if 0 <= current < len(labels) else 0
                    )
            finally:
                self._ref_guard = False

        def _on_reference_changed(self, _index: int) -> None:
            if getattr(self, "_ref_guard", False):
                return
            self.canvas.set_reference(self._ref_index())
            self._fill_marker_table(self.canvas.markers())
            self.measure_label.setText(self._measure_text(self.canvas.markers()))

        def _fill_marker_table(self, markers: Tuple[Marker, ...]) -> None:
            rows = marker_rows(markers, self._ref_index())
            unit = self._trace.params.unit if self._trace is not None else ""
            self.marker_table.setHorizontalHeaderLabels(
                [
                    "标记",
                    "频率",
                    f"幅值 ({unit})" if unit else "幅值",
                    "Δ频率 (哪两点)",
                    "Δ幅值 (哪两点)",
                ]
            )
            self.marker_table.clearSelection()
            self.marker_table.setRowCount(len(rows))
            dark = self._dark
            for r, row in enumerate(rows):
                color = QColor(marker_color(dark, r))
                for c, text in enumerate(row):
                    item = QTableWidgetItem(text)
                    if r != self._ref_index():
                        item.setForeground(color)  # 标记行文字用该标记的颜色
                    elif c == 0:
                        item.setForeground(color)
                    self.marker_table.setItem(r, c, item)
            self.marker_table.setVisible(bool(rows))
            self._rebalance_marker_table(bool(rows))

        def _rebalance_marker_table(self, visible: bool) -> None:
            """标记表显隐时重分配右侧分割区高度（QSplitter 不会自动让出空间）。"""
            splitter = getattr(self, "_right_splitter", None)
            if splitter is None:
                return
            sizes = splitter.sizes()
            if len(sizes) < 3:
                return
            if visible:
                total = sum(sizes)
                give = min(150, max(110, total // 4))
                sizes[1] = give
                sizes[0] = max(self.canvas.minimumHeight(), total - give - sizes[2])
            else:
                sizes[0] += sizes[1]
                sizes[1] = 0
            splitter.setSizes(sizes)

        def _measure_text(self, markers: Tuple[Marker, ...]) -> str:
            """测量栏文本：峰值/谷值 + 两点 Δ（频段宽度与电平差）。"""
            if self._trace is None:
                return "点击绘图区添加标记；鼠标悬停读取频点与幅值"
            parts = [extremes_text(self._trace)]
            delta = delta_text(markers, self._ref_index())
            if delta:
                parts.append(delta)
            return "     ".join(parts)

        # ── 状态与主题 ────────────────────────────────────────────
        def _set_status(self, text: str, error: bool = False) -> None:
            self._status_error = bool(error)
            self.status_label.setText(text)
            self.status_label.setToolTip(text)
            color = self._palette["warn"] if error else self._palette["sub"]
            self.status_label.setStyleSheet(f"color: {color};")

        def _refresh_axis_label(self) -> None:
            try:
                params = self.read_params()
            except SpectrumInputError:
                self.axis_label.setText("—")
                return
            levels = self._trace.levels if self._trace is not None else ()
            text = axis_range_text(params, levels, self.auto_check.isChecked())
            if self._pending_param_change():
                # 画布仍按上一次「绘制」的参数渲染：明确提示，避免同屏两套口径看不出差别
                text += "（参数已改，点「绘制」生效）"
            self.axis_label.setText(text)

        def _pending_param_change(self) -> bool:
            """表单参数是否已偏离已绘制的 trace（单位/参考电平/每格/格数/换算/检波）。"""
            trace = self._trace
            if trace is None:
                return False
            try:
                params = self.read_params()
            except SpectrumInputError:
                return False
            old = trace.params
            return (
                params.unit != old.unit
                or params.convert_50ohm != old.convert_50ohm
                or params.detector != old.detector
                or abs(params.ref_level_db - old.ref_level_db) > 1e-9
                or abs(params.db_per_div - old.db_per_div) > 1e-9
                or int(params.y_divs) != int(old.y_divs)
            )

        def restyle_for_theme(self, dark: bool) -> None:
            """主题切换：刷新画布调色板与文字颜色（标记表文字颜色随主题重算）。"""
            self._dark = bool(dark)
            self._palette = palette_for(dark)
            if hasattr(self, "canvas"):
                self.canvas.apply_palette(dark)
            if hasattr(self, "hint_label"):
                self.hint_label.setStyleSheet(f"color: {self._palette['sub']};")
            if hasattr(self, "measure_label"):
                self.measure_label.setStyleSheet(f"color: {self._palette['sub']};")
            if hasattr(self, "marker_table") and self.marker_table.rowCount():
                self._fill_marker_table(self.canvas.markers())
            if hasattr(self, "status_label"):
                self._set_status(self.status_label.text(), error=self._status_error)

        # ── 对外状态 ──────────────────────────────────────────────
        def current_trace(self) -> Optional[SpectrumTrace]:
            return self._trace


def _fmt_number(value: float) -> str:
    """频率输入框回写格式（避免 240.00000000001 这类浮点噪声）。"""
    text = f"{round(float(value), 9):g}"
    return text


if not _QT_AVAILABLE:  # pragma: no cover - 无 Qt 环境下的占位（仅纯逻辑层可用）
    SpectrumCanvas = None  # type: ignore[assignment]
    SpectrumWidget = None  # type: ignore[assignment]
