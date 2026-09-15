# 设计：频谱图绘制（spectrum_widget.py + 常驻 Tab）

## 1. 边界

**新增**
- `spectrum_widget.py` — 两层：前半**纯逻辑层**（无 Qt：参数/迹线模型、数值解析、轴计算、格式化），后半 **Qt 层**（`SpectrumCanvas` 自绘画布 + `SpectrumWidget` 标签页）。
- `test/test_spectrum_model.py`（纯逻辑）、`test/test_spectrum_gui.py`（offscreen）。

**修改**
- `main_gui.py` — import；常驻 tab 注册（`1627-1732` 区，紧跟「报文工具」`1692`）；`_restyle_for_theme` 主题钩子（`10548` 区）；`CHANGELOG` 头部 + `APP_VERSION` → `1.23.9`。
- `release_check.py` — `CORE_TESTS` / `GUI_TESTS` 追加两个新测试。
- `AGENTS.md`（§3 文件树、§7 测试清单、§10 摘要）、`README.md`（功能列表）。

**不动**：`parser/*`、`validator/*`、`protocol_registry.py`、`parser_registry.py`。频谱图与协议解析无关，不进入协议注册表。

## 2. 关键取舍

| 方案 | 结论 |
|---|---|
| matplotlib | 打包被**显式排除**（`南网协议解析工具.spec:181`、`reflex_web_exe.spec:171`），引入即与既有 excludes 冲突 + 数十 MB 体积 → **否决** |
| QtCharts（PySide6 自带，已确认可 import） | 面向"数据图"的自动坐标轴/刻度模型，与仪器式固定格（参考电平锚定、每格 dB）语义不合；又需把新增子模块纳入打包 → **否决** |
| **QPainter 自绘** | 与 `sequence_diagram_widget.py` 同构先例；网格/刻度/注记完全可控；零新增依赖；纯逻辑层可脚本测试 → **采用** |

**Tab 采用 eager 创建**（不用懒加载）：懒加载机制是为避免启动时导入重解析器/schema（`_ensure_frame_gen_tab` 等），本组件只依赖 Qt 自身，且 `apply_chinese_context_menus(self)`（`main_gui.py:5808`）已覆盖常驻子控件，eager 更简单、无占位页替换的图标丢失风险（历史缺陷见 `main_gui.py:241`）。

## 3. 纯逻辑层契约（无 Qt，可脚本测试）

```python
UNIT_DBM, UNIT_DBUV, UNIT_DBMV = "dBm", "dBμV", "dBmV"
UNIT_OFFSET_FROM_DBM = {UNIT_DBM: 0.0, UNIT_DBUV: 107.0, UNIT_DBMV: 47.0}  # 50Ω 系统
DETECTORS = ("峰值", "准峰值", "平均值", "RMS", "采样")
HZ_UNITS = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
SEPARATORS = (" ", "\t", "\r", "\n", ",", ";", "，", "、")   # 含中文全角分隔符


class SpectrumInputError(ValueError):
    """输入校验失败（消息可直接展示给用户）"""


@dataclass(frozen=True)
class SpectrumParams:
    start_hz: float
    stop_hz: float
    ref_level_db: float = -20.0
    db_per_div: float = 10.0
    y_divs: int = 8
    unit: str = UNIT_DBM
    convert_50ohm: bool = False
    rbw_hz: float | None = None
    vbw_hz: float | None = None
    detector: str = "峰值"

    @property
    def span_hz(self) -> float: ...          # stop - start
    @property
    def center_hz(self) -> float: ...        # (start + stop) / 2
    def step_hz(self, n_points: int) -> float | None: ...   # span / (n-1)，n<2 → None


@dataclass(frozen=True)
class SpectrumTrace:
    params: SpectrumParams
    freqs: tuple[float, ...]
    levels: tuple[float, ...]      # 已应用单位换算，用于绘制/导出
    n_points: int                  # property = len(levels)


def parse_levels(text: str) -> tuple[float, ...]      # 抛 SpectrumInputError
def validate_params(params: SpectrumParams) -> None
def build_trace(text: str, params: SpectrumParams) -> SpectrumTrace
def freqs_for(params: SpectrumParams, n_points: int) -> tuple[float, ...]
def display_levels(levels, params) -> tuple[float, ...]     # 50Ω 换算
def y_range(params, levels, auto: bool) -> tuple[float, float]     # (top, bottom)
def y_ticks(params, levels, auto: bool) -> tuple[float, ...]       # 自顶向下，len = y_divs + 1
def x_tick_stride(max_labels: int) -> int                           # 1/2/5/10
def x_tick_labels(params, max_labels: int) -> tuple[tuple[int, str], ...]   # (格序号 0..10, 文本)
def format_hz(hz: float) -> str
def format_level(value: float, unit: str = "") -> str
def auto_tick_decimals(step: float) -> int          # 自动适配刻度小数位
def format_fixed(value: float, decimals: int) -> str
def count_out_of_range(params, levels, auto) -> int
def resolve_freq_inputs(changed, start_hz, stop_hz, center_hz, span_hz) -> tuple[float, float, float, float]
def units_to_hz(value: float, unit: str) -> float
def to_freq_unit(hz: float, unit: str) -> float
def note_text(params: SpectrumParams, n_points: int) -> str
def status_text(trace: SpectrumTrace) -> str
def axis_range_text(params, levels, auto) -> str
def palette_for(dark: bool) -> dict
```

**越界提示不在模型里**（原设计的 `SpectrumTrace.warnings` 已去掉）：越界与否取决于「纵轴自动适配」开关，而该开关属于 UI 状态；绘制/状态行统一用 `count_out_of_range(params, levels, auto)` 现算，避免两处口径。

### 3.1 坐标系与公式（显式，禁止隐式字节/量纲推断）

- 频率轴（**线性**）：`freqs[i] = start_hz + i * span_hz / (N - 1)`，`i ∈ [0, N-1]`。
- 纵向映射（仪器式，`auto=False`）：
  `y(v) = plot.top + (ref_level_db - v) / (db_per_div * y_divs) * plot.height`
  即顶格 = 参考电平，底格 = `ref_level_db - db_per_div * y_divs`。
- 纵向映射（自动适配，`auto=True`）：
  `margin = 0.05 * (max - min)`（`max == min` 时 margin 取 `max(1.0, |max| * 0.01)`）
  `top = max + margin`，`bottom = min - margin`，等分 `y_divs` 格。
- 单位换算（勾选时）：`display = level + UNIT_OFFSET_FROM_DBM[unit]`（输入按 dBm 计）。

### 3.2 错误矩阵（全部抛 `SpectrumInputError`，消息面向用户）

| 条件 | 消息要点 |
|---|---|
| 起始/终止频率非有限数或 ≤ 0 | 「起始频率必须为正数」/「终止频率必须为正数」 |
| `stop_hz <= start_hz` | 「终止频率必须大于起始频率」 |
| `db_per_div` 不在 `[0.1, 20]` | 「每格 dB 需在 0.1 ~ 20」 |
| `y_divs` 不在 `[4, 12]` | 「纵向格数需在 4 ~ 12」 |
| RBW/VBW 填了但 ≤ 0 | 「RBW/VBW 必须为正数」 |
| trace 文本为空/全分隔符 | 抛错，消息「请输入 trace 数值」 |
| 非法 token | 「第 N 项不是有效数值：`<原文>`」（**不静默丢弃**） |
| 有效数值个数 N < 2 | 「至少需要 2 个数值点才能绘制」 |

非阻断（状态行 ⚠ 提示，仍绘制）：数值超出当前纵轴范围（提示「M 个点超出纵轴范围，已裁剪到边缘」，仅仪器式口径可能出现）。

### 3.3 参数表单层校验（`SpectrumWidget`，同样抛 `SpectrumInputError`）

| 条件 | 消息要点 |
|---|---|
| 任一参数输入框为空 | 「<字段名>不能为空」 |
| 输入框非数值 / 非有限 | 「<字段名>不是有效数值：<原文>」 |
| 四字段联动后扫宽 ≤ 0 | 「扫宽必须为正数（终止频率需大于起始频率）」（保留原值） |
| 四字段联动后起始频率 ≤ 0 | 「该中心频率与扫宽会得到非正的起始频率，已忽略本次修改」 |

### 3.4 测量层（R7/R8，纯逻辑，可脚本测试）

```python
MAX_MARKERS = 6
PEAK_MIN_PROMINENCE_DB = 3.0
MARKER_COLORS_DARK / MARKER_COLORS_LIGHT = (...6 色...)      # M1..M6 与序号绑定的固定色

@dataclass(frozen=True)
class Marker:
    label: str          # M1..M6（按列表顺序编号，删除后重新编号）
    freq_hz: float
    level: float
    index: int          # 吸附到的数据点索引

def marker_color(dark, order) -> str                    # 第 order 个标记的颜色（超出上限循环）
def nearest_index(freqs, freq_hz) -> int                # bisect 二分吸附（任意单调轴正确；正中间取靠前）
def markers_for(trace, freqs) -> tuple[Marker, ...]     # 越界频率丢弃、顺序重编号
def peak_index(levels) -> int                            # 全局最大（并列取最靠前）
def valley_index(levels) -> int                          # 全局最小
def _valley_left(levels) / _valley_right(levels) -> tuple[float, ...]   # 单调栈 O(n) 谷值
def peak_indices(levels, min_prominence_db=3.0) -> tuple[int, ...]      # 局部峰（O(n)）
def next_peak_index(levels, current_index, direction=1, ...) -> int | None  # 环形
def extreme_points(trace) -> tuple[Marker, Marker]       # (峰值点, 谷值点)
def delta_pair_index(markers, ref_index=0) -> tuple[int, int] | None     # (参考, 目标)
def marker_rows(markers, ref_index=0) -> tuple[tuple[str, ...], ...]     # Δ 单元格带 `M?↔M?` 前缀
def delta_text(markers, ref_index=0) -> str                              # `Δf(M?↔M?) …  Δlevel …`
def format_delta_hz(delta_hz) / format_delta_level(delta_db) -> str
```

- **标记以频率为锚点**（不存索引）：参数/单位/纵轴口径变化后重绘时由 `markers_for` 重新吸附；频率落在当前扫描范围外则丢弃（调用方把丢弃数量**追加**到状态行文本，不覆盖点数/步进信息）。
- **显著度**（`peak_indices`）：局部极大的峰相对左右两侧「通往更高地形」路径谷值的落差 ≥ 阈值才算有效峰；首尾点不视为峰。**左右谷值用单调栈一次遍历预计算（O(n)）**——早期逐点扫描实现在「一侧没有更高点」的频谱上退化为 O(n²)（实测 16000 点 3.74 s，冻结 GUI 线程）；新实现与旧实现在 9000 组随机/边界数据上逐例等价（0 处不一致），16000 点耗时 5.3 ms。
- **Δ 语义与「哪两点」**：M1 为默认参考，`Δ 参考` 下拉可改；Δ 单元格与测量栏文案一律带 `M?↔M?` 前缀；参考为最后一个标记时目标取前一个（参考恒在 `↔` 左侧，与表格一致）。
- **色卡与主题**：`marker_color(dark, order)` 是图上与表格取色的唯一来源；`restyle_for_theme` 后重算表格文字颜色。

### 3.5 交互层（R7 / R8，Qt）

- **画布**：`setMouseTracking(True)`；绘图区几何由 `plot_rect()` **单一来源**同时供 `_paint` 与鼠标换算；`mouseMoveEvent` 在绘图区内 → 记录 `_cursor = (index, freq, level)` 重绘，`leaveEvent` 清除、`set_trace` 也清除（轨迹更换后旧读数作废）；`mousePressEvent`（左键、绘图区内）→ `add_marker_requested.emit(freq)`。
- **只读状态接口**（测试与绘制共用）：`cursor_readout() -> tuple[int, float, float] | None`、`point_at(pos)`、`set_markers(markers)`、`set_reference(ref_index)`、`plot_rect()`。
- **画布绘制**：光标十字点划线 + 该点圆点 + 读数框（框随光标偏移并夹在绘图区内）；标记竖虚线 + 圆点 + `M?` 标签（**颜色 = `marker_color(dark, order)`**，与标记表行文字同色）；≥2 个标记时在绘图区右上角画读数框，每行用该标记自身颜色，Δ 行用正文色。
- **参数区第 2 行工具栏**：`峰值搜索` / `下一个峰值` / `删除标记` / `清空标记` / `Δ 参考` 下拉 + 测量栏文本。标记操作作用于**标记表选中行**，无选中则最后一个标记；无标记时峰值类按钮直接新建 M1。
- **标记表**：`QTableWidget`，5 列 `标记/频率/幅值(单位)/Δ频率(哪两点)/Δ幅值(哪两点)`，行文字用该标记颜色，**仅在存在标记时可见**；显隐时用 `_rebalance_marker_table()` 重分配右侧 `QSplitter` 高度（QSplitter 不会自动让出空间，且未 show() 时 `sizes()` 不反映真实布局）。
- **口径单源**：表单参数改动但未重绘时，只读纵轴标签追加「（参数已改，点「绘制」生效）」——画布/标记表一律以 `trace.params`（已绘制的那份）为准，避免同屏两套单位。

### 3.6 积分带宽（R10，纯逻辑 + 渲染约定）

```python
@dataclass(frozen=True)
class IntegrationBand:      # 画布只负责画：边沿 + 两条文本
    low_hz: float
    high_hz: float
    text: str               # 侧栏只读行（完整口径：点数、归一化原因、越界/窄带提示）
    short_text: str         # 画布右上读数框短行（`IBW Σ -49.96 dBm`）

@dataclass(frozen=True)
class IntegrationResult:
    low_hz: float; high_hz: float; n_points: int
    total_db: float | None; unit: str
    normalized: bool; basis: str      # 未归一化时必须写明原因
    clipped: bool                     # 超出扫宽，按交集积分
    narrow: bool                      # 带宽 < 一个步进（单点外推）

def ibw_edges(center_hz, bandwidth_hz) -> tuple[float, float]      # 中心 ± 带宽/2（带宽必须为正）
def integrate_band(trace, center_hz, bandwidth_hz, rbw_hz=None) -> IntegrationResult
def integration_text(result) -> str          # 侧栏长文本
def integration_short_text(result) -> str    # 画布短文本
def integration_band_for(trace, center_hz, bandwidth_hz, rbw_hz=None) -> (IntegrationBand, IntegrationResult)
def format_band(low_hz, high_hz) -> str      # 同单位合并（`550–650 MHz`）
```

- **求和与归一化**：`peak + 10log10(Σ10^((v-peak)/10))`（移位求和，防极端电平溢出/下溢），再 `+10log10(步进/RBW)`；单位偏移在求和前后抵消。
- **渲染**：填充与两条点划线在 **迹线之下**（`_paint_ibw_region` 紧跟网格/边框之后调用），带内 `IBW 起–止` 标签与右上读数框短文在 `_paint_measure` 内（最上层）且夹在绘图区内；配色用独立 palette 键（`ibw` / `ibw_fill`）。
- **状态**：`SpectrumCanvas.set_integration_band(band|None)` 是唯一入口，`set_trace()` 一并清空（避免旧轨迹的区域带画在新轨迹上）；`SpectrumWidget._refresh_integration()` 由 `_on_draw` / `_on_clear` / 开关 / 编辑完成 / 频率与带宽单位切换触发，归一化口径取 `trace.params.rbw_hz`（与画布注记同源），表单 RBW 偏离时追加提示。

## 4. Qt 层设计

```python
class SpectrumCanvas(QWidget):          # 自绘画布（无交互状态，paintEvent 全量重绘）
    def set_trace(self, trace: SpectrumTrace | None) -> None
    def set_auto_y(self, auto: bool) -> None
    def apply_palette(self, dark: bool) -> None
    def render_image(self, width: int = 1600, height: int = 1000) -> QImage   # 导出与测试共用

class SpectrumWidget(QWidget):          # 标签页：左参数区 + 右（画布 / trace 输入）
    def restyle_for_theme(self, dark: bool) -> None
    def read_params(self) -> SpectrumParams          # 校验失败抛 SpectrumInputError
    def current_trace(self) -> SpectrumTrace | None
    def _save_png(self, path: str) -> bool           # 导出按钮与测试共用
    # 按钮：绘制 / 粘贴 / 清空 / 导出 PNG；复选框：纵轴自动适配
```

**刻度防越界**：横轴首/末标签改为贴边对齐（首标签左对齐于绘图区左沿、末标签右对齐于绘图区右沿），避免居中标签越出画布或压住纵轴刻度；自动适配模式刻度按 `auto_tick_decimals(step)` 定点格式化（不出现 `47.3275` 这类等分噪声）。

**布局**：`QSplitter`（左参数表单固定宽 ~340px、右「画布 + trace 输入框」上下 `QSplitter`），保证参数区与数据区在 1366×768 低分屏也不互相挤压（低分屏重叠是历史高发问题）。

**画布几何**：外边距 12px；标题带（标题 + 参数注记）34px；绘图矩形 `left=78`（Y 轴标签）、`right=16`、`bottom=46`（X 轴标签 + 单位）。字号从 `self.font().pointSizeF()` 派生（标题 +3、注记 −1、刻度 −2，最小 7），以兼容软件内「字体大小」设置。

**调色板**（`restyle_for_theme(dark)` 切换，绘制时按当前调色板取色）：

| key | dark | light | 用途 |
|---|---|---|---|
| bg | `#1E1E1E` | `#FFFFFF` | 控件背景 |
| plot_bg | `#141414` | `#FAFAFA` | 绘图区背景 |
| grid | `#3C3C3C` | `#D0D0D0` | 网格线 |
| axis | `#9E9E9E` | `#8A8A8A` | 边框/轴线 |
| text | `#E6E6E6` | `#212121` | 标题与刻度 |
| sub | `#9E9E9E` | `#666666` | 参数注记 |
| trace | `#FFD54F` | `#1E88E5` | 迹线（仪器黄 / 亮蓝） |
| warn | `#FF8A65` | `#D84315` | 状态与警告文字 |

**刻度防重叠**：`n_labels` 由绘图区宽度与单标签像素宽决定（`width // 78`，夹在 `[3, 11]`），`x_tick_labels` 按等分位置取标签文本；Y 轴每格都标（`y_divs ≤ 12`，不会挤）。

## 5. main_gui 接线段（3 处）

```python
# ① import 区
from spectrum_widget import SpectrumWidget

# ② tab 创建（main_gui.py:1692「报文工具」之后）
self.spectrum_tab = SpectrumWidget()
self.spectrum_tab.restyle_for_theme(self._is_dark_theme())
self._spectrum_tab_index = self.tab_widget.addTab(
    self.spectrum_tab, app_icons.load_icon("chart-spline"), "频谱图"
)

# ③ _restyle_for_theme（main_gui.py:10548 区，紧随 diff_tab）
if getattr(self, "spectrum_tab", None) is not None:
    try:
        self.spectrum_tab.restyle_for_theme(self._is_dark_theme())
    except RuntimeError:
        pass
```

tab 索引一律用 `addTab` 返回值（禁止硬编码，AGENTS.md/spec「新增标签页五步套路」第 2 条），本功能不参与协议可见性，因此**不需要** `_on_protocol_changed` 改动。

## 6. 测试设计

`test/test_spectrum_model.py`（纯逻辑，无 Qt）
1. `parse_levels`：空格/换行/逗号/分号/制表符/中文全角分隔混排；`+`/`-`/科学计数；BOM 与首尾空白；空文本抛错；非法 token 抛错且消息含序号与原文；`nan`/`inf` 拒绝。
2. 参数校验：错误矩阵逐行 `raises`。
3. `freqs_for`：N=2/3/100 端点精确等于起止频率，步进 = span/(N−1)（浮点用 `abs(x-y) < 1e-6`）。
4. `y_range`/`y_ticks`：仪器式 → `top == ref_level_db`、步长 `db_per_div`、`len == y_divs+1`；自动 → 含 5% 边距、`max == min` 的退化输入不除零。
5. `display_levels`：`dBm` 无偏移；`dBμV` +107；`dBmV` +47；不勾选换算时原样返回。
6. `format_hz` / `format_level`：`240e6 → "240 MHz"`、`7.2727e6` 单位选择与小数位、`1e9 → "1 GHz"`。
7. `count_out_of_range`：仪器式与自动模式下的超范围点数。

`test/test_spectrum_gui.py`（offscreen）
1. tab 常驻可见：`_spectrum_tab_index >= 0`，切协议 0/6/9 后 `isTabVisible` 恒为 True。
2. 控件齐全（绘制/粘贴/清空/导出按钮、自动适配复选框、参数输入）。
3. 粘贴 100 点 → 绘制：`current_trace()` 点数 = 100、状态行含「点数 100」与频率步进。
4. 非法 token → 状态行含错误信息、`current_trace()` 保持 None、不抛异常。
5. 勾选自动适配 → Y 轴刻度首值随数据 max 变化；取消 → 回到参考电平。
6. `render_image()` 在两种主题下尺寸正确（1600×1000）且非纯色（像素方差 > 0）。
7. 导出 PNG 到 `tempfile` 目录：文件存在、`QImage.load` 成功、尺寸 > 0（测试后清理临时文件）。
8. `restyle_for_theme(True/False)` 前后 `_palette["trace"]` 变化且不抛异常。

## 7. 兼容性 / 回滚

- **兼容性**：纯新增文件 + `main_gui.py` 3 处插入；不改任何 parser/validator 签名，不影响既有协议路径；不新增 pip 依赖，`南网协议解析工具.spec` 无需改动（无 datas/hiddenimports 变化 —— 只有一个新的根级 .py，PyInstaller 由 import 图自动收集）。
- **实测**：`test/test_spectrum_model.py` 103 项、`test/test_spectrum_gui.py` 58 项全过；`release_check.py --sync-iss` 后 PASS=47 FAIL=0（WARN 2 项为「BUILD_DATE 非今天」「README 徽章」——前者属打包期动作，本次不打包故保留，后者已同步为 1.23.9）。
- **回滚**：删 `spectrum_widget.py`、两个测试、`main_gui.py` 3 处插入、`release_check.py` 两行、CHANGELOG/AGENTS/README 对应条目。
- **版本**：`APP_VERSION` → `1.23.9`，`BUILD_DATE` 打包日更新（本次仅源码改动，不打包则不更新 BUILD_DATE）。
