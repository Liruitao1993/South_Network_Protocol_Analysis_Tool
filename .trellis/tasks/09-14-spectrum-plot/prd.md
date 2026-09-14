# 频谱图绘制（频谱仪参数配置 + trace 数值输入 → 频谱图输出）

## Goal

GUI 新增**常驻标签页「频谱图」**：按频谱仪口径配置扫描参数（起始/终止频率、RBW/VBW、参考电平、每格 dB、单位、检波方式、纵向格数）→ 输入一条 trace 的全部扫频点数值 → 绘制仪器式网格频谱图 → 可导出 PNG。纯 QPainter 自绘，**零新增第三方依赖**。

## Confirmed Facts（代码证据）

- **全仓无既有频谱功能**：`grep -E "频谱|RBW|dBm|sweep|trace"` 零命中（唯一命中是无关 JSON 时间戳）。
- **绘图依赖现状**：`matplotlib` 被显式排除于打包（`南网协议解析工具.spec:181`、`reflex_web/reflex_web_exe.spec:171`）；项目未使用 matplotlib / pyqtgraph / QtCharts（本机装有 matplotlib 3.9.3 但仓库不用）。
- **自绘先例**：`sequence_diagram_widget.py` — 前半纯逻辑层（`SequenceModel`，不 import PySide6）+ 后半 Qt 层（`QGraphicsView`/QPainter 手绘），含「导出 PNG」按钮（`sequence_diagram_widget.py:509-513`、`:789` 保存实现）。
- **Tab 集成点**：`main_gui.py:1627-1732`。常驻 eager 例 = `message_tool_tab`（`main_gui.py:1692`）；懒加载例 = `_ensure_lazy_tab`（`:3068`）+ `_replace_lazy_tab`（`:3168`）+ `_ensure_seq_diagram_tab`（`:3150`）。
- **主题适配惯例**：组件暴露 `restyle_for_theme(dark)`（`diff_widget.py`），主窗口两端挂钩 → 创建时 `main_gui.py:1686`，主题切换时 `_restyle_for_theme`（`main_gui.py:10548-10552`）。
- **图标资源**：`app_icons.load_icon(name)` 读 `icons/lucide/*.svg`，可用 `chart-spline` / `chart-line` / `audio-waveform` / `area-chart`。
- **中文右键菜单**：`apply_chinese_context_menus(self)`（`main_gui.py:5808`）覆盖主窗口全部子控件，常驻 tab 无需单独调用（懒加载 tab 才需在 `_ensure_*` 里补调，见 `:3098`）。
- **版本基线**：`APP_VERSION = "1.23.8"`、`BUILD_DATE = "2026-09-12"`（`main_gui.py`）→ 本功能 bump 至 `1.23.9`。
- **发布门槛**：`release_check.py` 的 `CORE_TESTS`（纯逻辑）/ `GUI_TESTS`（offscreen 可选）/ `KNOWN_FLAKY`；新增测试必须进清单（历史教训：不进清单的红灯长期无人管）。
- **测试约定**：`test/` 下脚本式 `check()` 断言，文件头 `import _path_setup`；GUI 测试 `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`（`test/test_csg_sequence_gui.py:16-20`）。

## Requirements

### R1 频谱仪参数配置区

| 参数 | 控件 | 默认 | 校验 |
|---|---|---|---|
| 起始频率 | 数值 | 240 | > 0，且 < 终止频率 |
| 终止频率 | 数值 | 960 | > 起始频率 |
| 中心频率 | 数值（**双向联动**） | 600 | 与扫宽联动后起点必须 > 0 |
| 扫宽 Span | 数值（**双向联动**） | 720 | > 0 |
| 频率单位 | 下拉 kHz/MHz/GHz | MHz | 四个频率字段共用同一单位 |
| RBW（分辨率带宽） | 数值 + 单位下拉（kHz/MHz） | 空 | 填了必须 > 0 |
| VBW（视频带宽） | 数值 + 单位下拉（kHz/MHz） | 空 | 填了必须 > 0 |
| 参考电平 | 数值（dB） | −20 | 任意有限值 |
| 每格 dB（dB/div） | 数值 | 10 | 0.1 ≤ x ≤ 20 |
| 纵向格数 | 整数 | 8 | 4 ≤ n ≤ 12 |
| 单位 | 下拉 dBm / dBμV / dBmV | dBm | — |
| 按 50Ω 换算 | 复选框 | 不勾 | — |
| 检波方式 | 下拉 峰值/准峰值/平均值/RMS/采样 | 峰值 | 仅作图中注记 |

- **只读派生显示**（不额外输入）：中心频率 = (起+止)/2、扫宽 = 止−起、频率步进 = 扫宽/(N−1)（N=trace 点数），随输入实时刷新。
- **单位语义（明确定义，避免隐式换算）**：`单位` 下拉同时决定纵轴标注与图中注记；trace 数值按该单位**原样绘制**。勾选「按 50Ω 换算」时才做偏移（输入按 dBm 计：dBμV = dBm + 107，dBmV = dBm + 47），不勾选则数值不变、仅标注改变。

### R2 trace 数值输入（单 trace）

- 多行文本输入框；分隔符支持 空格 / 制表符 / 逗号 / 分号 / 换行，忽略首尾空白与 BOM（U+FEFF）；支持 `+`/`-` 号与科学计数法（`1.2e-3`）。
- **非法 token 必须明确报错**（含「第 N 项」与原文），**不得静默丢弃、不得清空已有图形**（遵循 AGENTS.md §8 陷阱 23「字段/数据不一致时的容错显示原则」）。
- 点数 N = 实际数值个数（不额外声明点数，频率轴按 N 线性均分）；N < 2 → 报错（无法成图）。
- 「粘贴」（读剪贴板）、「清空」按钮；状态行显示 `点数 N / 频率步进 / span / RBW`。

### R3 绘图（仪器式网格 + 自动适配切换）

- **网格**：横向固定 10 格；纵向 `纵向格数` 格；仪器式口径 = 顶格为参考电平，向下每格 −`每格 dB`。
- **「纵轴自动适配」复选框**：勾选后纵轴范围取 trace min/max 并留 5% 边距、等分 `纵向格数` 格；取消则回到参考电平口径。
- **迹线**：单条折线；N ≤ 201 时叠加数据点标记便于核对。数值超出绘区时裁剪到边缘并在状态行提示超范围点数。
- **标题与注记**：顶部标题「频谱图」+ 参数注记行（起止频率 / span / RBW / VBW / 检波方式 / 参考电平 / 每格 dB / 点数 / 单位），导出时一并渲染（形成可直接贴报告的图）。
- **频率刻度**：标签按数值自动选单位（Hz/kHz/MHz/GHz）与小数位；绘区宽度不足以放下每格标签时间隔标注（避免重叠）。
- **主题适配**：浅/暗主题下网格、文字、迹线、背景均清晰可读；暴露 `restyle_for_theme(dark)`。

### R4 导出 PNG

工具栏「导出 PNG」→ `QFileDialog` 选择路径 → 导出含标题与注记的图像（默认 1600×1000）。依据原始需求的「最后**输出**一个绘制好的频谱图」；范围问答中未勾选的导出项（CSV/Excel/剪贴板）不做。

### R5 Tab 集成

- 常驻标签页（与协议无关，同「报文工具」），标题「频谱图」，图标 `chart-spline`，eager 创建（无重解析器导入，无懒加载必要）。
- 不进入 `protocol_registry.py`（与协议能力无关）；切换协议不隐藏。

### R6 测试与发布门槛

- `test/test_spectrum_model.py`：纯逻辑（数值解析容错、错误矩阵、轴范围与频率映射、刻度标签格式化、单位换算、派生值计算）。
- `test/test_spectrum_gui.py`：offscreen（tab 常驻可见、控件齐全、粘贴→绘制点数、非法输入不崩且有错误提示、自动适配切换改变刻度、导出 PNG 可被 `QImage` 读回、双主题 restyle 不抛异常）。
- `release_check.py`：两个新测试分别加入 `CORE_TESTS` / `GUI_TESTS`；`python release_check.py` 无 FAIL。

## Acceptance Criteria

1. 启动 GUI 后「频谱图」tab **常驻可见**，切换任意协议（0~11）都不隐藏。
2. 参数填 起始 240 MHz / 终止 960 MHz / RBW 100 kHz / 参考电平 −20 dB / 每格 10 dB / 8 格，粘贴 N=100 个数值 → 图形出现：X 轴左端标 `240 MHz`、右端标 `960 MHz`；Y 轴顶端标 `-20`，每格递减 10；状态行显示 `点数 100`、`频率步进 7.27273 MHz`（= 720/99）。
3. trace 文本含非法 token（如 `12a3`）→ 状态行给出含序号/原文的错误，且不绘制错误图形、不崩溃。
4. 勾选「纵轴自动适配」后纵轴刻度改为数据范围（含 5% 边距），取消勾选后恢复参考电平口径。
5. 单位选 `dBμV` 且勾选 50Ω 换算 → 迹线与注记按 +107 偏移；不勾选 → 数值不变仅轴标注改变。
6. 点「导出 PNG」生成 PNG，`QImage` 可读回且尺寸 > 0，图像包含标题与参数注记。
7. 切暗色主题后网格/文字/迹线仍清晰（offscreen 断言颜色随主题变化且无异常）。
8. `python test/test_spectrum_model.py` 与 `python test/test_spectrum_gui.py` 全过；`python release_check.py` 无 FAIL。

## Out of Scope

- 多 trace 叠加（Trace A/B/C）、迹线数学（A−B）、平均/最大保持/最小保持。
- CSV / Excel / 剪贴板导出（范围问答未勾选）。
- 实时数据接入（串口、监控器、SCPI 仪器控制）——本期仅手工输入；绘图入口按数据无关设计，后续接数据源不需重构。
- 峰值自动搜索与标记、游标（marker）读数、上下限线、对数频率轴、时间瀑布图。
- 频谱数据解析（从设备日志/报文中提取 trace）——本期只接受数值列表。
- Reflex Web 版同步（后续独立任务）。

## Risks / Deferred

- **纵向格数默认 8** 取自常见手持/台式频谱仪屏幕口径；不同型号为 8 或 10 → 已用参数暴露，不写死。
- **50Ω 换算常数**（+107 / +47）仅对 50Ω 系统成立；75Ω 系统需另加换算（本期不做，注记中标注 50Ω）。
- **1:1 复刻某型号屏幕**需该型号截图作 golden；本期按通用仪器口径绘制，不声称与某型号一致。
- **超大点数（>100k）**未做抽样优化（QPainter 折线本身支持），如遇性能问题另开任务。
- **PNG 导出**依据原始需求「输出一个绘制好的频谱图」纳入；若评审认为超范围，直接删该按钮与 R4（不影响其余交付）。
