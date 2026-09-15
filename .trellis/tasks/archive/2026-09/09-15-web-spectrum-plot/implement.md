# 实施计划：Web 频谱图

前置：`prd.md`（R1~R8）、`design.md`（几何常量/State 字段/取舍）。dev 服务可在 `localhost:3000` 实测。

---

## 步骤 1 — `reflex_web/reflex_web/spectrum_web.py`（纯几何，无 Qt/reflex）

按 `design.md` §2 实现：常量 + `plot_rect` / `x_for_freq` / `freq_for_x` / `y_for_level` / `level_for_y` /
`grid_segments` / `trace_points` / `x_label_items` / `y_label_items` / `marker_items` / `band_rect` /
`band_click_freq` / `EXPORT_PNG_JS`。
坐标一律 `round(..., 2)` 成字符串或数值（前端渲染模型用 `str`，便于 `rx.foreach`）。

**验收**：`python -c "import sys;sys.path.insert(0,'reflex_web');from reflex_web import spectrum_web as sw;print(sw.plot_rect(), sw.y_for_level(-30, …))"`（见步骤 4 测试）。

---

## 步骤 2 — `SpectrumState`（`reflex_web.py`）

按 `design.md` §3 实现字段与动作。要点：
- 只调用 `spectrum_widget` 的纯逻辑 API，自身不重写任何算法；
- `sp_draw()` 失败路径必须**保留旧图**（错误只写 `sp_error`）；
- 标记以频率为锚点存 `sp_marker_freqs`，每次绘制用 `markers_for` 重吸附；
- 前端渲染模型（`sp_grid_*`/`sp_polyline`/`sp_markers_svg`/…）全为 JSON 可序列化类型。

**验收**：State 端到端断言（步骤 4）。

---

## 步骤 3 — `spectrum_tab()` 组件 + Tab 接线

1. `spectrum_tab()`：参数卡（频率四字段 + 单位 + 幅度参数 + 检波/自动适配/50Ω）→ trace 卡（textarea + 绘制/清空 + 状态行）→ 画布卡（`rx.el.svg` 800×500 视口 + viewBox，内含网格/标签/迹线/标记/IBW/注记；60 个透明带承载 click）→ 测量卡（读数/峰值谷值/标记表 + Δ 参考下拉 + 峰值搜索/删除/清空 + 导出 PNG）。
2. `index()` 的 tab 按钮链加「频谱图」（`icon="chart_spline"`，`data_testid="tab-spectrum"`），`rx.cond` 链加 `State.active_tab == "spectrum"` → `spectrum_tab()`。
3. 导出 PNG：`on_click=rx.call_script(spectrum_web.EXPORT_PNG_JS)`（纯前端，无需后端往返）。

**验收**：`python -c "import reflex_web.reflex_web as m; m.index()"` 可构建；浏览器实测（步骤 5）。

---

## 步骤 4 — `test/test_web_spectrum.py`

- `spectrum_web` 纯几何：坐标换算往返一致、越界裁剪、网格条数（11 / y_divs+1）、标签首末贴边、`band_rect` 求交与无交集、`trace_points` 点数为 `2N-2` 段（含逗号分隔）等；
- 复用性守卫：`import spectrum_widget`（Web 进程无 PySide6）后纯逻辑 API 可用（`build_trace` 出图）；
- `SpectrumState` 端到端：设参数 → 喂 101 点常量 trace → 绘制 → 断言 `sp_status` 含点数、polyline 非空；四字段联动（改 center 后 start/stop 同步）；点两个带 → 2 个标记 + 标记表含 `M1↔M2`；峰值搜索加标记；IBW 开 → 带矩形 + 读数含「积分功率」；错误路径（非法参数/非法 token）→ `sp_error` 非空且**旧图仍在**。
- 登记进 `release_check.py:CORE_TESTS`。

**验收**：`PYTHONIOENCODING=utf-8 python test/test_web_spectrum.py` 全过。

---

## 步骤 5 — 浏览器实测（dev 服务）

1. 打开「频谱图」tab，粘贴 101 点常量 trace（-70）→ 出图（直线），状态行含点数/步进/扫宽。
2. 点画布两处 → M1/M2 出现且颜色不同；标记表出现 Δ 且含 `M1↔M2`。
3. 开「积分带宽」（中心 600 MHz、带宽 100 MHz、RBW 7.2 MHz）→ 出现半透明带 + 竖线 + `IBW Σ` 注记，参数区读数含「积分功率 … 按 RBW 归一化」。
4. 改「每格 dB」→ 纵轴刻度变化且标记自动重吸附（频率不变）。
5. 点「导出 PNG」→ 浏览器触发下载（headless 下断言未抛错 + 监听 download 事件）。

---

## 步骤 6 — 门槛与文档

- `python release_check.py` 无 FAIL；`CHANGELOG` 1.23.12 追加 Web 频谱图条目；`AGENTS.md §1/§3/§7/§10`（Web 能力表 + 新模块 + 测试清单 + 摘要）；
- `.trellis/spec/frontend/component-guidelines.md` 补「Web 复用桌面纯逻辑层 + SVG 自绘」范式（含 `spectrum_web` 几何契约）。

## 完成定义（DoD）

`prd.md` R1~R8 全部满足；步骤 4/5 验收通过；桌面 `test_spectrum_model.py`/`test_spectrum_gui.py` 仍全过；`release_check` 无 FAIL。
