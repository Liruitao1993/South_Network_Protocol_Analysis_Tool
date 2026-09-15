# 设计：Web 频谱图（SVG 渲染 + 纯逻辑复用）

## 1. 分层

```
spectrum_widget.py            ← 桌面/Web 共用纯逻辑（只读复用，不改）
  └─ SpectrumParams/Trace/… 纯函数
reflex_web/reflex_web/spectrum_web.py   ← 新增：SVG 几何（纯，无 Qt/reflex）
  └─ plot_rect / x_for_freq / y_for_level / grid_segments / trace_points
     x_label_items / y_label_items / marker_items / band_rect / band_click_index
reflex_web/reflex_web/reflex_web.py     ← SpectrumState + spectrum_tab()（只做状态与组装）
```

## 2. 画布几何（viewBox 单位，与像素解耦；SVG 自适应缩放）

```
VIEW_W, VIEW_H = 1000, 620
PLOT_X0, PLOT_X1 = 76, 964        # 左侧留纵轴刻度、右侧留边
PLOT_Y0, PLOT_Y1 = 46, 540        # 上方留参数注记、下方留横轴标签 + 状态行
BAND_CLICK_COUNT = 60             # 绘图区切成 60 个透明带承载 click/hover
```

坐标换算（全部纯函数，可测）：
- `x_for_freq(freq, params, rect)` = `X0 + (freq - start)/span * (X1 - X0)`
- `freq_for_x(x, params, rect)` 为其逆；`y_for_level(level, params, levels, auto, rect)` 按 `y_range` 线性映射，**并裁剪到 [Y0, Y1]**（越界点画到边缘，与桌面一致）
- `band_rect(i)` → 第 i 带的 `(x, w)`；`band_center_freq(i, params, rect)` → 点击吸附用的频率
- 网格：竖线 = 11 条（`X_DIVS+1`），横线 = `y_divs+1` 条
- 标签：横轴用 `x_tick_labels(params, max_labels=8)`（首末贴边：首标签左对齐、末标签右对齐），纵轴用 `y_ticks`；自动适配时按 `auto_tick_decimals(step)` 定小数位）
- 迹线：`trace_points(trace, auto)` → `"x,y x,y …"` 字符串（单条 `polyline`）
- 标记：`marker_items(markers, params, trace, auto, rect)` → `[{x, y, label, color, text}]`（竖虚线 + 圆点 + 标签，颜色取 `marker_color(False, i)`）
- 积分带：`band_rect(low_hz, high_hz, params, rect)` → 与绘图区求交后的 `(x, w)`；无交集 → `None`（不画）

## 3. State（`SpectrumState(rx.State)`）

| 字段 | 说明 |
|---|---|
| 参数（字符串，用户输入原样） | `sp_start`/`sp_stop`/`sp_center`/`sp_span` + `sp_unit`；`sp_ref`/`sp_dbdiv`/`sp_ydivs`；`sp_amp_unit`/`sp_50ohm`/`sp_detector`/`sp_auto_y` |
| 可选参数 | `sp_rbw`/`sp_rbw_unit`/`sp_vbw`/`sp_vbw_unit`（空 → `None`，送纯逻辑） |
| trace | `sp_trace_text`；绘制后 `sp_has_trace`/`sp_note`/`sp_status`/`sp_axis_range`/`sp_out_of_range` |
| 图形数据（前端渲染模型，全为 str/num） | `sp_grid_v`/`sp_grid_h`/`sp_polyline`/`sp_x_labels`/`sp_y_labels`/`sp_params_note`/`sp_markers_svg`/`sp_ibw_*` |
| 标记 | `sp_marker_freqs: list[float]`（**频率锚点**，重绘自动重吸附）；`sp_marker_rows`；`sp_ref_index`；`sp_readout`/`sp_extremes` |
| 积分带宽 | `sp_ibw_center`/`sp_ibw_bw`/`sp_ibw_unit`/`sp_ibw_show`/`sp_ibw_text` |
| 消息 | `sp_error`（红）/`sp_msg`（普通） |

动作：
- `sp_set_param(name, value)`：写字段 → 对频率四字段调 `resolve_freq_inputs` 联动（失败保留原值 + 提示）→ `sp_draw()`（有 trace 时自动重绘）。
- `sp_draw()`：`build_trace(text, params)` → 失败则写 `sp_error` 且**保留旧图** → 成功则重算 polyline/网格/标签/注记/标记（`markers_for` 重吸附）/IBW。
- `sp_plot_click(band_index)`：带中心频率 → `nearest_index` → 追加标记频率（上限 6）→ 重绘标记 + 读数。
- `sp_next_peak()` / `sp_del_marker()` / `sp_clear_markers()` / `sp_set_ref_index(v)`。
- `sp_set_ibw(name, value)` → 重算带与读数。
- `sp_state_for_plot()`（内部）：把 State 字段装配成 `SpectrumParams`，供所有动作复用。

## 4. 兼容与取舍

- 参数解析：字符串 → float 时允许空（RBW/VBW 为空）；非法数值沿用纯逻辑报错（不做二次校验口径）。
- 标记存**频率**而非索引（桌面同口径）：改点数/改扫宽后自动重吸附、越界丢弃。
- 着色：`palette_for(False)`（浅色）；Web 无暗色主题。
- 导出 PNG 用前端一次性函数（`spectrum_web.EXPORT_PNG_JS`）：`XMLSerializer` → `Image` → canvas → `toDataURL` → `<a download>`。
- 点击精度：按 60 带取「带中心频率」→ `nearest_index` 吸附到数据点（标记本身就吸附，精度等同桌面点击）。
