# 设计：Web 主题系统

## 1. 分层与单一来源

```
reflex_web/reflex_web/theme_web.py      ← 新增：纯逻辑（无 Qt/reflex）
    MODES / ACCENTS / GRAYS / RADII
    PRESETS            # 6 个命名预设（模式 × 强调色 × 灰阶 × 圆角）
    TOKENS_LIGHT / TOKENS_DARK   # 语义 token → 色值
    ACCENT_OVERRIDES   # 每个强调色覆盖 --accent/--accent-soft（自定义 CSS 侧）
    build_theme_css()  # :root / html.dark / html[data-accent=…] 三段
    marker_css()       # 由 spectrum_widget.MARKER_COLORS_* 生成 --sp-m1..6
reflex_web/reflex_web/reflex_web.py     ← GLOBAL_CSS 改引 token；ThemeState；顶栏控件
spectrum_web.marker_items               ← 颜色改为 var(--sp-mN)
```

## 2. Token 契约（浅色 = 现状值）

| token | 浅色（现值） | 深色 |
|---|---|---|
| `--bg` | `#f1f5f9` | `#0b1220` |
| `--card` | `#ffffff` | `#131c2e` |
| `--card-hover` | `#f8fafc` | `#1a2540` |
| `--border` | `#e2e8f0` | `#27334d` |
| `--border-strong` | `#cbd5e1` | `#3b4a6b` |
| `--text` | `#0f172a` | `#e6edf7` |
| `--text-2` | `#334155` | `#c3cfe2` |
| `--muted` | `#64748b` | `#9fb0c9` |
| `--muted-2` | `#94a3b8` | `#7d8ea8` |
| `--accent` | `#2563eb` | `#60a5fa` |
| `--accent-soft` | `rgba(37,99,235,.10)` | `rgba(96,165,250,.16)` |
| `--accent-ink` | `#1d4ed8` | `#93c5fd` |
| `--ok` / `--ok-soft` | `#16a34a` / `rgba(22,163,74,.12)` | `#34d399` / `rgba(52,211,153,.16)` |
| `--warn` | `#f59e0b` | `#fbbf24` |
| `--danger` | `#dc2626` | `#f87171` |
| `--code-bg` | `#f8fafc` | `#0d1526` |
| `--grid` | `#e2e8f0` | `#2a354f` |
| `--plot-bg` | `#fbfdff` | `#0d1526` |
| `--trace` | `#0f766e` | `#5eead4` |

强调色覆盖（自定义 CSS 侧，与 Radix 的 `accent_color` 同选）：

| accent | `--accent` | `--accent-soft` |
|---|---|---|
| blue（默认，无需覆盖块） | `#2563eb` | `rgba(37,99,235,.10)` |
| teal | `#0d9488` | `rgba(13,148,136,.12)` |
| violet | `#7c3aed` | `rgba(124,58,237,.12)` |
| amber | `#d97706` | `rgba(217,119,6,.12)` |
| green | `#15803d` | `rgba(21,128,61,.12)` |

深色下强调色覆盖同样给一套（浅色字面量在深底上对比不足）→ `html.dark[data-accent="teal"]{--accent:#2dd4bf;…}`。

## 3. State（`ThemeState(rx.State)`）

| 字段 | 说明 |
|---|---|
| `preset: str` | 当前预设 id（自定义时为 `"custom"`） |
| `accent: str` / `gray: str` / `radius: str` | Radix 主题维度（接给 `rx.theme(...)`） |
| `theme_class: str` | 页面根容器 class：`f"nw-theme nw-accent-{accent}"`（自定义 CSS 的作用域） |
| `preset_options` | 预设下拉项（label/id） |

动作：
- `apply_preset(preset_id)`：设模式（`rx.color_mode` 由前端按钮/`set_color_mode` 处理；预设里若含 dark/light 则同时切换）+ accent/gray/radius。
- `set_dimension(name, value)`：微调 → `preset = "custom"`。
- `persist()`：`rx.call_script("localStorage.setItem('nw-theme', JSON.stringify({...}))")`。
- `restore(raw_json)`：`on_load` 读回并套用。

模式切换用 Radix 原生 `rx.color_mode.button(allow_system=True)`（自带持久化 + 跟随系统）。

## 4. 替换策略（浅色等价）

1. `GLOBAL_CSS` 内所有硬编码色 → `var(--token)`（含 `.rt-Card` 阴影色）。
2. 组件内 `color=<hex>` / `background=<hex>` / `fill=` / `stroke=`：
   - Radix 组件（`rx.text/heading/icon`）：`color="#2563eb"` → `style={"color": "var(--accent)"}`；
   - 原生元素（`rx.el.*`、SVG）：直接 `fill="var(--grid)"` / `stroke="var(--trace)"`（emotion 落到 CSS）；
   - `rx.card(background=…)` 之类 → `style={"background": "var(--card)"}`。
3. 保留 Radix 语义属性（`color_scheme="blue"/"green"/"red"`、`variant="soft"`）不替换：它们随 `.dark` 自动适配。
4. 每个替换点在浅色下 `var(--token)` 解析回原 hex → 逐像素不变；深色生效于 token 覆盖。

## 5. 兼容与取舍

- **`rx.theme(...)` 包裹**：把主页面内容包一层 `rx.theme(appearance="inherit", accent_color=ThemeState.accent, gray_color=ThemeState.gray, radius=ThemeState.radius)`，让 Radix 组件跟随；`appearance="inherit"` 交给 `.dark`/`.light` 类决定。若该版本 `appearance` 不接受 `"inherit"`，则用 `rx.color_mode_cond(light="light", dark="dark")`。
- 主题控件放在顶栏右侧：模式按钮 + 「主题」预设下拉 + （展开/或放在一处）三个维度下拉。
- 非主页面（`/feedback`、`/share`）不挂控件，但 token 生效（跟随模式）。
