# 实施计划：Web 主题系统

前置：`prd.md`（R1~R6）、`design.md`（token 表/强调色覆盖/替换策略）。dev 服务在 `localhost:3000` 可实测。

---

## 步骤 1 — `reflex_web/reflex_web/theme_web.py`（纯逻辑）

`MODES` / `ACCENTS` / `GRAYS` / `RADII` / `PRESETS`(6) / `TOKENS_LIGHT` / `TOKENS_DARK` / `ACCENT_OVERRIDES`
/ `build_theme_css()` / `marker_css()`（由 `spectrum_widget.MARKER_COLORS_LIGHT/DARK` 生成 `--sp-mN`）/ `theme_class(accent)`。

**验收**：`python -c "import sys;sys.path.insert(0,'reflex_web');from reflex_web import theme_web as w;css=w.build_theme_css();print(css.count('--card'), len(w.PRESETS), w.theme_class('teal'))"`

---

## 步骤 2 — `GLOBAL_CSS` token 化 + 注入主题 CSS

1. `GLOBAL_CSS` 里所有硬编码色改 `var(--token)`（body/容器/卡片/表格/Tab/消息条/滚动条/可搜索下拉）。
2. 页面 `<style>` 注入顺序：`SEARCHABLE_CSS + GLOBAL_CSS + theme_web.build_theme_css()`。

**验收**：浅色截图与改动前对比（步骤 6）；`python -c "import reflex_web.reflex_web as m; s=str(m.index()); print(':root' in s and 'html.dark' in s)"`

---

## 步骤 3 — 组件内色值替换（脚本化 + 人工过 diff）

映射表（hex → token，按出现次数从多到少）：
`#2563eb→--accent`、`#1d4ed8→--accent-ink`、`#94a3b8/#9ca3af→--muted-2`、`#64748b/#6b7280/#475569→--muted|--text-2`、`#f1f5f9→--bg`、`#ffffff→--card`、`#cbd5e1→--border-strong`、`#e2e8f0→--border`、`#16a34a→--ok`、`#dc2626→--danger`、`#f59e0b→--warn`、`#0f766e→--trace`、`#f8fafc→--code-bg`、`#fbfdff→--plot-bg`。
- Radix 组件属性：`color="<hex>"` → `style={"color": "var(--x)"}`；
- 原生元素/SVG：`fill/stroke/background="var(--x)"`；
- `rx.button(color_scheme=…)` / `rx.badge` 等语义属性不动。

**验收**：`grep` 统计 `reflex_web.py` 中剩余裸 hex < 20 且均为刻意保留（如品牌 logo 色）；组件树可构建；浅色截图等价。

---

## 步骤 4 — `ThemeState` + 顶栏控件 + 持久化

- `ThemeState(rx.State)`：`preset/accent/gray/radius/theme_class/preset_options` + `apply_preset/set_dimension/persist/restore`（`design.md` §3）。
- 顶栏右侧：`rx.color_mode.button(allow_system=True)` + 预设下拉 + 三个维度下拉；主页面内容包 `rx.theme(appearance="inherit", accent_color=ThemeState.accent, gray_color=ThemeState.gray, radius=ThemeState.radius)`。
- 主页面 `on_load`：`rx.call_script("localStorage.getItem('nw-theme')", callback=ThemeState.restore)`；切换时 `persist()`。

**验收**：浏览器切预设即时生效；刷新后保持。

---

## 步骤 5 — 频谱图跟随主题

- `spectrum_web.marker_items` 颜色 → `var(--sp-mN)`；画布网格/坐标轴/迹线/积分带/注记 → token；`SpectrumState` 的标记表 `color` 同样引用变量。
- 移除 `palette_for` 的 Python 侧 dark 依赖（改为 CSS）。

**验收**：深色下打开「频谱图」，网格/迹线/标记可见且与标记表同色；浅色不变。

---

## 步骤 6 — 测试与截图验收

- 新增 `test/test_web_theme.py`（`prd.md` R6 四类断言）；登记 `release_check.py:CORE_TESTS`。
- 截图：浅色（与改动前对比）、深色、深色+teal、浅色+amber；存 `test/` 同级无需入库，只需在提交信息里记录结论数值（浅色逐像素差异）。
- `python release_check.py` 无 FAIL。

---

## 步骤 7 — 文档

`AGENTS.md §1/§3/§7/§10`（Web 主题能力 + `theme_web.py` + 测试清单 + 摘要）、`main_gui.py:CHANGELOG`（1.23.12 条目追加 Web 主题系统）、`.trellis/spec/frontend/component-guidelines.md` 补「Web 主题 token 契约 + 新颜色必须走 token」约定。

## 完成定义（DoD）

R1~R6 全部满足；浅色等价（逐像素或给出量化差异）；深色与两个强调色截图通过；测试与 release_check 全绿。
