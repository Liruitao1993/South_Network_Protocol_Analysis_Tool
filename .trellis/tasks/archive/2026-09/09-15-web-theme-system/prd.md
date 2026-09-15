# Web 版主题系统（明暗模式 + 预设主题 + token 化）

## Goal

Reflex Web 版目前只有**一套硬编码浅色**（`GLOBAL_CSS` + 组件里 215 处十六进制色值）。本任务引入主题系统：**明暗模式（含跟随系统）** + **6 个命名预设主题**（模式 × 强调色组合）+ **CSS token 层**（浅色保持与现状逐像素等价），并让频谱图 SVG/标记配色一并跟随。目标：夜间/弱光可用、品牌强调色可换、首屏观感更专业。

## Confirmed Facts（代码证据，2026-09-15）

- 桌面主题注册表在 `theme_settings.py:1763-1815`（7 项）：`default`(浅色)/`fusion`(Fusion 经典)/`dark`(Fusion 暗色)/`glass`(毛玻璃)/`mica`(Win11 云母)/`windows`/`windowsvista`；`is_dark()`(:1828) 仅 `dark` 为暗色。
  → 其中 Fusion 经典 / Windows 原生 / Vista 是 **Qt 专属**，Web 无对应概念；毛玻璃/云母在 Web 用 CSS `backdrop-filter` 表达（后续可加）。**Web 侧应给「模式 × 强调色」的预设**，而不是照搬 Qt 风格名。
- Reflex/Radix **自带**明暗机制：前端运行时给根节点加 `light`/`dark` 类（`reflex_base/.templates/web/utils/react-theme.js`、`reflex_base/.templates/web/components/reflex/radix_themes_color_mode_provider.js`），`rx.color_mode.button(allow_system=True)` 提供 浅色/深色/跟随系统 并**自动持久化**；`rx.color_mode_cond(light=…, dark=…)` 可在 Python 侧按模式取值（已核实 `hasattr(rx, "color_mode_cond") is True`）。
- Radix 主题支持**运行时**强调色：`app = rx.App(theme=rx.theme(appearance="light", accent_color="blue", gray_color="slate", radius="medium"))`（`reflex_web.py` 末尾），且 `rx.theme(...)` 亦可用作**包裹组件**并把 `accent_color`/`gray_color`/`radius` 接成 State 变量 → `rx.button/rx.badge/rx.card/rx.table` 等 Radix 组件自动跟随。
- 自定义 CSS 单主题：`GLOBAL_CSS` 的 `body/.app-container/.app-header-inner/.rt-Card/.app-tab/...` 全是硬编码浅色。
- 组件内硬编码色值：`reflex_web.py` 中 **215 处 `#RRGGBB`（去重 36 个）**、**231 处颜色属性**；Top：`#2563eb`×46（强调蓝）、`#94a3b8`×27、`#64748b`×15、`#6b7280`×12、`#f1f5f9`×11、`#9ca3af`×10、`#16a34a`×10、`#cbd5e1`×8、`#e2e8f0`×8、`#ffffff`×8、`#dc2626`×6、`#475569`×6。
- 频谱图已具备双调色板：`spectrum_widget.palette_for(dark)`(:943)、`marker_color(dark, order)`(:78)；Web 侧 `spectrum_web.marker_items` 目前固定 `marker_color(False, i)`，`sp_polyline` 用固定 `#0f766e`。

## Requirements

### R1 模式（浅色 / 深色 / 跟随系统）
- 用 Radix 原生机制（`rx.color_mode.button(allow_system=True)` 或等价下拉），**不自己实现** localStorage 持久化。
- 深色下：页面底 `body`、卡片、表格、输入框、Tab 条、消息条、代码块、滚动条全部跟随（token 覆盖）。

### R2 预设主题（"一些默认的主题"）
- `theme_web.PRESETS` 定义 6 个命名预设（模式 + 强调色 + 灰阶 + 圆角），例如：
  `经典浅色`(light/blue/slate/medium)、`夜间深色`(dark/blue/slate/medium)、`暗夜青绿`(dark/teal)、`暗夜紫`(dark/violet)、`浅色琥珀`(light/amber)、`护眼绿`(light/green)。
- 顶栏「主题」控件：预设下拉（一键套用）+ 模式按钮；另给「强调色 / 灰阶 / 圆角」三项微调（与预设联动回显为「自定义」）。
- 切换即时生效（无刷新）。

### R3 CSS token 层（浅色等价是硬约束）
- `theme_web.TOKENS_LIGHT` 用**当前现值**（与现状逐像素等价）；`TOKENS_DARK` 给深色值；`build_theme_css()` 输出 `:root{…}` / `html.dark{…}` / `html[data-accent="…"]{…}` 三段。
- Token 清单（≥）：`--bg --card --card-hover --border --border-strong --text --text-2 --muted --muted-2 --accent --accent-soft --accent-ink --ok --ok-soft --warn --danger --code-bg --grid --plot-bg --trace --sp-m1..--sp-m6`。
- `GLOBAL_CSS` 与组件内的自定义色一律改为 `var(--token)`；Radix 组件自身的 `color_scheme`/`variant` 保持（它们随 `.dark` 自动适配）。
- 频谱图标记配色：CSS 变量由 `spectrum_widget.MARKER_COLORS_*` **生成**（单一来源），SVG 与标记表一律引用 `var(--sp-mN)`。

### R4 持久化
- 模式：Radix 原生（localStorage）。
- 预设/强调色/灰阶/圆角：State 字段 + `rx.call_script("localStorage.setItem(...)")` 写入；主页面 `on_load` 用 `rx.call_script("localStorage.getItem('nw-theme')", callback=ThemeState.restore)` 读回（同一份 JSON 一次读写）。
- 服务端不落盘（无多用户语义），浏览器即真相。

### R5 频谱图跟随
- SVG 的网格/坐标轴/迹线/标记/积分带/注记/背景全部走 token（`stroke="var(--grid)"` 等，Reflex 会把 SVG 表现属性落到 CSS）；`palette_for()` 与画布背景不再需要 Python 侧 dark 判断。
- 标记表文字色同样引用 `var(--sp-mN)`，与图上标记一一对应。

### R6 测试与验收
- `test/test_web_theme.py`：预设/强调色清单完整性（每个预设都有 label+mode+accent 且 accent ∈ ACCENTS）；`TOKENS_LIGHT` 与 `TOKENS_DARK` 键集合一致；`build_theme_css()` 含 `:root`/`html.dark`/`html[data-accent="teal"]` 且 **每个 token 都出现在两套里**；marker CSS 与 `MARKER_COLORS_*` 数值一致；`ThemeState` 端到端（套用预设 → 三个维度与 class 串正确；自定义微调 → preset 变「自定义」）；组件树可构建且含主题控件。
- **浅色回归**：改动前后同一页面在同一视口截图，逐像素差异为 0（或视觉不可辨别的极小差异，需给出数值）。
- 浏览器实测：深色 + 浅色 + 两个强调色各出一张截图；深色下频谱图网格/迹线/标记可读。

## Out of Scope

- 毛玻璃（`backdrop-filter`）与 Win11 云母主题（桌面专有观感；Web 端若要，另立增量）。
- 字体族/字号设置（桌面有；Web 端浏览器缩放已够用）——如需，后续增量。
- 非主页面（`/feedback`、`/share`）的主题控件（它们仍会跟随模式与 token，只是没有切换入口）。

## Risks / Deferred

- **token 化面积大**（215 处）：机械替换，但浅色必须等价 → 以「浅色用现值、深色只覆盖 token」策略 + 截图逐像素对比把关；发现等价性破坏就地回退该处。
- Radix `color=` 属性对非标准值（hex）的处理不透明：统一改为 `style={"color": "var(--token)"}`，Light 下 var 解析为同一 hex → 等价；若某处 Radix 语义变化（如 badge 的 color_scheme 被覆盖），以截图为准逐个修正。
- 深色下的对比度需人工过一遍（尤其表格斑马纹、代码块、禁用态按钮）。
