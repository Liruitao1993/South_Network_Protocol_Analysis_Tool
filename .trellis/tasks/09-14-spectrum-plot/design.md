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
