# Web 版频谱图标签页（SVG 自绘，复用桌面纯逻辑层）

## Goal

在 Reflex Web 版新增**常驻**标签页「频谱图」（与协议无关，不进 `protocol_registry`），功能与桌面 `spectrum_widget.py`（1.23.9~1.23.11）等价：频谱仪参数 → trace 数值 → 仪器式网格频谱图 + 测量（标记/Δ/峰值）+ 积分带宽 + 导出 PNG。

**核心判断：不重写逻辑，只重写绘制层。** `spectrum_widget.py`（2365 行）前 ~950 行是**零 Qt 依赖**的纯逻辑层，Web 侧直接 `import` 复用；Qt 层（`SpectrumCanvas`/`SpectrumWidget`）替换为 SVG。

## Confirmed Facts（代码证据）

- 纯逻辑层（`spectrum_widget.py`，仅依赖 stdlib+bisect+math）：
  - 数据模型：`SpectrumParams`(:130) `SpectrumTrace`(:160) `TraceInput`(:191) `Marker`(:455) `IntegrationBand`(:775) `IntegrationResult`(:785)
  - 输入/校验：`preprocess_trace`(:217，日志行清洗 + 不变式 `lines_total == used + skipped`) `parse_levels`(:291) `validate_params`(:296) `build_trace`(:341) `display_levels`(:323)
  - 几何/刻度：`freqs_for`(:333) `y_range`(:356) `y_ticks`(:376) `x_tick_stride`(:385) `x_tick_labels`(:393) `format_hz`(:405) `format_level`(:419) `auto_tick_decimals`(:425) `format_fixed`(:437) `count_out_of_range`(:442)
  - 测量：`marker_color`(:78，M1~M6 固定配色) `nearest_index`(:465) `markers_for`(:482) `peak_index`(:503) `valley_index`(:514) `peak_indices`(:567，单调栈 O(n)) `next_peak_index`(:590) `extreme_points`(:611) `delta_text`(:646) `marker_rows`(:659) `readout_text`(:701) `extremes_text`(:711)
  - 联动/带：`resolve_freq_inputs`(:721，四字段双向联动) `ibw_edges`(:800) `integrate_band`(:809，移位求和防溢出) `integration_text`(:863) `integration_short_text`(:877) `integration_band_for`(:885) `format_band`(:765)
  - 文案/主题：`note_text`(:902) `status_text`(:920) `axis_range_text`(:932) `palette_for`(:943)
  - 常量：`X_DIVS=10`(:54) `MIN/MAX_DB_PER_DIV` `MIN/MAX_Y_DIVS` `MAX_MARKERS=6` `PEAK_MIN_PROMINENCE_DB=3.0` `LEVEL_UNITS` `DETECTORS` `FREQ_UNITS` `RBW_UNITS` `UNIT_OFFSET_FROM_DBM`
- Qt 层被 `try: from PySide6 … except ImportError: _QT_AVAILABLE=False` 守护（`_QT_IMPORT_ERROR` :87 留痕）→ Web 进程（`reflex_web_exe.spec` 已 `excludes PySide6`）可安全 import 该模块、只用纯函数。
- 既有回归网：`test/test_spectrum_model.py`（225 项，纯逻辑）与 `test/test_spectrum_gui.py`（offscreen Qt）——前者对 Web 版同样有效。

## Requirements

### R1 复用（禁止复制）
- Web 侧只允许 `from spectrum_widget import (…)` 使用上表纯逻辑 API；**不得**把参数校验/trace 清洗/刻度/标记/峰值/积分算法抄一份到 `reflex_web/`（复刻漂移是本项目已发生的教训）。
- 若发现纯逻辑层缺函数（如 SVG 需要的坐标换算），新逻辑放新的 **纯** 模块 `reflex_web/reflex_web/spectrum_web.py`（无 Qt、无 reflex），不得改动桌面行为。

### R2 参数表单
- 频率：起始/终止/中心/扫宽四字段**双向联动**（`resolve_freq_inputs`）＋统一单位下拉（kHz/MHz/GHz，`FREQ_UNITS`）。
- 幅度：参考电平、每格 dB（0.1~20）、纵向格数（4~12）、幅值单位（dBm/dBμV/dBmV）＋「输入按 dBm，50Ω 换算」开关（`UNIT_OFFSET_FROM_DBM`）、检波方式（`DETECTORS`）、「纵轴自动适配」开关。
- 非法参数：沿用 `validate_params` 的消息，显示在错误行且**保留上一次成功图形**（不破坏已有画面）。

### R3 trace 输入
- 单条 trace：粘贴多值文本（空格/制表/逗号/分号/换行/全角分隔符），走 `preprocess_trace`；支持带日志前缀的行（取行尾电平）。
- 状态行提示清洗统计（`TraceInput.note()`：「已清洗 N 行日志，跳过 K 行无数值」）。
- 报错语义与桌面一致：行内有值却取不到行尾值 → 报错并给出行号；无日志结构却含非法 token → 报错；点数 < 2 → 「至少需要 2 个数值点才能绘制」。

### R4 SVG 仪表式绘制
- 横向固定 10 格（`X_DIVS`）、纵向 `y_divs` 格；顶格 = 参考电平，每格 −`db_per_div`（自动适配模式按 min/max ±5%）。
- 网格线、横轴刻度（`x_tick_labels`，首末标签贴边对齐）、纵轴刻度（仪器式取 `format_level`；自动适配按 `auto_tick_decimals`）、迹线（**一条** `polyline`，越界点裁到边缘）、参数注记（`note_text`）、状态行（`status_text` + `axis_range_text` + 越界点数提示 `count_out_of_range`）。
- 单色浅色调色板取 `palette_for(False)`（Web 无暗色主题）。

### R5 测量
- 点击绘图区 → 在**最近数据点**加 MARK 标记（上限 `MAX_MARKERS=6`，超出给提示）；每个标记配色 `marker_color(False, order)`，图上竖虚线 + 圆点 + `M?` 标签与标记表行文字**同色**（一图一表一一对应）。
- 标记以**频率**为锚点：重绘/改单位/改纵轴口径后自动重新吸附（`markers_for`），越界丢弃并提示。
- 标记表列 `标记/频率/幅值/Δ频率/Δ幅值`（Δ 单元格自带 `M?↔M?` 标注，`marker_rows`）；「Δ 参考」下拉切换参考标记（`delta_text`）。
- 测量栏：峰值/谷值（`extremes_text`）、点击读数（`readout_text`）、「峰值搜索/下一个峰值」（`next_peak_index`）、「删除标记/清空标记」。

### R6 积分带宽
- 参数：中心频率 + 积分带宽 + 单位 + 显示开关；边上用 `ibw_edges`，带内积分 `integrate_band`（含 RBW 归一化/单点外推/交集裁剪口径）。
- 图上：两条点划线竖线 + 半透明填充带（画在迹线**之下**）+ `IBW Σ …` 短注记；参数区显示完整口径（`integration_text`）。

### R7 导出 PNG
- 客户端把 `<svg>` 序列化 → canvas → `toDataURL` → 下载（**零新增依赖**，不引 matplotlib/服务端栅格化）。

### R8 测试与验收
- `test/test_web_spectrum.py`：`spectrum_web` 纯几何（坐标换算/网格/标签/裁剪/带矩形）+ `SpectrumState` 端到端（`State(_reflex_internal_init=True)`：参数联动、绘制、加/删标记、峰值搜索、IBW、错误路径）+ 组件树可构建。
- 桌面回归不掉：`test/test_spectrum_model.py`（225）/`test_spectrum_gui.py` 保持通过；`release_check.py` 无 FAIL。
- 浏览器实测：在跑着的 dev 服务上粘贴 trace → 出图；点两处加 M1/M2；标记表出现 Δ 且标注 `M1↔M2`；开 IBW 出现带与积分读数；导出 PNG 触发下载。

## Out of Scope

- **悬停实时读数**（桌面 hover 十字光标 + 读数框）：Web 首版用「点击读数」（同一组纯函数 `nearest_index`+`readout_text`），悬停版需把 trace 数据带进前端做本地换算，列为后续增量。
- 暗色主题配色（Web 目前只有浅色主题）、trace 文件导入（粘贴已足够）、多 trace 叠加（桌面亦为单条）。
- 桌面侧任何改动（本任务纯 Web 新增）。

## Risks / Deferred

- **点击坐标映射**：Reflex 的 `on_click` 不暴露 DOM 事件，无法直接拿像素 → 首版把绘图区切成 60 个透明带（各带 `on_click`），点击按带中心频率吸附到最近数据点（标记本来就吸附，精度无损）；若将来要更高精度或悬停，再上「JS 桥（原生 setter + InputEvent）」。
- **大点数渲染**：迹线必须渲染成**一条** polyline（16000 点 → 一个 `points` 字符串）；绝不可按点生成元素。
- `spectrum_widget.py` 的 Qt 层在 Web 进程导入时会走 `except ImportError` 分支：**这是预期**，但若将来有人在该模块顶层新增未守护的 PySide6 用法，Web 会整体导入失败——测试里显式断言「纯逻辑 API 可用」以暴露该回归。
