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
    }


# ══════════════════════════════════════════════════════════════════
# Qt 层（无 Qt 环境仍可导入上面的纯逻辑层）
# ══════════════════════════════════════════════════════════════════

try:
    from PySide6.QtCore import QPointF, QRect, Qt
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPolygonF
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QSizePolicy,
        QSpinBox,
        QSplitter,
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

        def __init__(self, parent=None):
            super().__init__(parent)
            self._trace: Optional[SpectrumTrace] = None
            self._auto_y = False
            self._palette = palette_for(False)
            self.setMinimumSize(420, 260)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # ── 对外接口 ──────────────────────────────────────────────
        def set_trace(self, trace: Optional[SpectrumTrace]) -> None:
            self._trace = trace
            self.update()

        def set_auto_y(self, auto: bool) -> None:
            self._auto_y = bool(auto)
            self.update()

        def apply_palette(self, dark: bool) -> None:
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

            base_pt = self.font().pointSizeF() or 9.0
            title_font = QFont(self.font())
            title_font.setPointSizeF(max(base_pt + 3, 10.0))
            title_font.setBold(True)
            label_font = QFont(self.font())
            label_font.setPointSizeF(max(base_pt - 1, 7.0))
            note_font = QFont(self.font())
            note_font.setPointSizeF(max(base_pt - 2, 7.0))
            label_metrics = QFontMetrics(label_font)

            trace = self._trace
            params = trace.params if trace is not None else None
            levels = trace.levels if trace is not None else ()

            if params is not None:
                ticks = y_ticks(params, levels, self._auto_y)
                if self._auto_y and levels:
                    top, bottom = y_range(params, levels, self._auto_y)
                    decimals = auto_tick_decimals((top - bottom) / params.y_divs)
                    labels = [format_fixed(v, decimals) for v in ticks]
                else:
                    labels = [format_level(v) for v in ticks]
                labels[0] = f"{labels[0]} {params.unit}"  # 顶端刻度带单位
            else:
                ticks, labels = (), ()

            y_label_w = max([label_metrics.horizontalAdvance(t) for t in labels], default=0)
            left_margin = max(52, y_label_w + 12)
            top_band = 36 if params is not None else 20
            margin = 12
            x_label_h = label_metrics.height() + 14

            plot = QRect(
                rect.left() + margin + left_margin,
                rect.top() + margin + top_band,
                rect.width() - 2 * margin - left_margin - 16,
                rect.height() - 2 * margin - top_band - x_label_h,
            )
            if plot.width() < 80 or plot.height() < 60:
                return  # 可用空间不足，避免负尺寸绘制

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

    class SpectrumWidget(QWidget):
        """频谱图标签页：工具栏 + 参数表单 + trace 输入 + 自绘画布。"""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._trace: Optional[SpectrumTrace] = None
            self._palette = palette_for(False)
            self._freq_unit = DEFAULT_FREQ_UNIT
            self._sync_guard = False
            self._status_error = False

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

            # ── 主体：左参数 / 右画布 + 数据 ──
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._build_param_panel())

            right = QSplitter(Qt.Orientation.Vertical)
            self.canvas = SpectrumCanvas()
            right.addWidget(self.canvas)
            right.addWidget(self._build_input_panel())
            right.setSizes([520, 200])
            right.setStretchFactor(0, 1)
            right.setStretchFactor(1, 0)
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
            self.axis_label.setText(
                axis_range_text(params, levels, self.auto_check.isChecked())
            )

        def restyle_for_theme(self, dark: bool) -> None:
            """主题切换：刷新画布调色板与文字颜色。"""
            self._palette = palette_for(dark)
            if hasattr(self, "canvas"):
                self.canvas.apply_palette(dark)
            if hasattr(self, "hint_label"):
                self.hint_label.setStyleSheet(f"color: {self._palette['sub']};")
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
