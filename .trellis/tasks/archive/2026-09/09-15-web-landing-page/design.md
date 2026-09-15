# 设计：Web 版产品首页（落地页）

## 1. 分层与依赖方向

```
reflex_web/reflex_web/landing_web.py     ← 新增：内容数据 + 纯展示组件 + LANDING_CSS
                                            不 import reflex_web（与 web_utils/theme_web 同向）
                                            所有随运行时而变的值由参数注入（str / rx.Var / EventHandler）
reflex_web/reflex_web/reflex_web.py      ← index() 更名 tool_page() 挂 /app；新增 landing_page() 组合
                                            landing_page() 注入 State.download_*/ThemeState 控件
test/test_web_landing.py                 ← 新增（内容不变式 + 组件树 + 路由 + 死链守卫）
test/test_web_spectrum.py                ← app.index() → app.tool_page()
test/test_web_theme.py                   ← 同上
reflex_web/tests/test_reflex_app.py      ← goto /app + 新增 / 落地页冒烟
release_check.py                         ← CORE_TESTS += test/test_web_landing.py
```

依赖方向与既有模块一致（`web_utils/lookup_utils/spectrum_web/theme_web` 都不反向 import `reflex_web`）。`landing_web.landing_page(**ctx)` 的每个运行时值都有安全默认值 → **测试可不依赖 State/QApplication 直接构建整页并断言**。

## 2. 路由与导航（改动清单）

| 路由 | 现状 | 目标 | `data-testid` |
|---|---|---|---|
| `/` | 工具（`index()`） | **落地页**（`landing_page()`） | `landing-root` |
| `/app` | — | 工具（`tool_page()`） | `tool-root` |
| `/share` `/feedback` `/feedback-admin` | 不变 | 不变 | — |

内部链接改指（死链是硬约束，逐处列出）：

| 位置 | 现 | 改 |
|---|---|---|
| `header()` `:4511` 「返回主页」 | `href="/"`，testid `nav-home` | 文案「在线工具」，`href="/app"`，testid `nav-tool` |
| `header()` `:4611` 独立页「管理员登录」 | `href="/"` | `href="/app"`（弹窗只挂工具页） |
| `header()` 品牌块（logo+标题） | 纯 `rx.hstack` 不可点 | 包 `rx.el.a href="/"` testid `nav-brand`（**不新增按钮**，顶栏 `nowrap` 空间紧张） |
| `:9420` feedback-admin「前往主页·问题反馈」 | `href="/"` | `href="/app"` |
| `:9825` share「去解析并分享」 | `href="/"` | `href="/app"` |
| `add_page(index, route="/")` | — | `add_page(tool_page, route="/app")` + `add_page(landing_page, route="/")` |

落地页顶栏**不复用** `header()`（后者含协议选择器/就绪灯，语义不符），由 `landing_web.landing_nav(theme_controls)` 提供营销导航：品牌 + 锚点（功能 / 协议 / 快速上手 / 下载）+ 主题控件 + 「进入在线工具」CTA。

主题控件组件在 `reflex_web.py` 内构建（需要 `ThemeState` + `theme_web.preset_options()`），作为参数传进 `landing_nav`；与工具页顶栏同一套控件（`ThemeState.apply_choice` / `cycle_mode` 跨页可复用，State 是同一实例）。

## 3. `landing_web.py` 公开结构

内容数据（纯 Python，测试直接断言）：

| 名称 | 形状 | 来源 |
|---|---|---|
| `FEATURES` | `list[dict]`：`icon/title/desc/tags`，**12 项** | `client_readme.md` 功能总览 + `AGENTS.md §3` |
| `PROTOCOLS` | `list[dict]`：`index/name/standard/endian/check`，**12 项** | `AGENTS.md §1` |
| `CLI_ACTIONS` | `list[dict]`：`cmd/desc`，**4 项** | `main_gui.py:7038-7063` |
| `SYSTEM_INTEGRATIONS` | `list[dict]`：`icon/title/desc`，**6 项** | `system_integration/` |
| `HERO_STATS` | `list[dict]`：`value/label`，**4 项** | 12 协议 / 17 项功能模块（readme 功能总览行数）/ 4 种数据入口 / 100% 离线 |
| `INTERNAL_LINKS` | `dict`：语义名 → 路径（`home="/"` `tool="/app"` `feedback="/feedback"` `share="/share"`） | 单一来源，组件与死链测试共读 |
| `LANDING_CSS` | `str`：落地页专属 CSS（hero 光晕/网格、窗口拟态、卡片 hover、响应式） | — |

组件构建器（全部回传 `rx.Component`，无 State 依赖）：

```python
landing_nav(theme_controls=None) -> rx.Component
landing_hero(*, version="", version_date="", exe_name="", exe_size_mb="",
             exe_available=False, image_src="", image_available=False,
             on_download=None) -> rx.Component
landing_features() -> rx.Component
landing_protocols() -> rx.Component
landing_quickstart() -> rx.Component
landing_footer(*, version="") -> rx.Component
landing_page(**ctx) -> rx.Component     # 组装全部 section，供 reflex_web 与测试调用
```

`reflex_web.landing_page()`（约 25 行）只做注入：

```python
def landing_page() -> rx.Component:
    return rx.theme(
        rx.box(
            theme_style(),
            rx.el.style(landing_web.LANDING_CSS),
            landing_web.landing_page(
                version=State.download_version,
                version_date=State.download_version_date,
                exe_name=State.download_exe_name,
                exe_size_mb=State.download_exe_size_mb,
                exe_available=State.download_exe_available,
                image_src=State.download_image_src,
                image_available=State.download_image_available,
                on_download=State.download_client,
                theme_controls=theme_controls_compact(),
            ),
            background="var(--bg)", min_height="100vh", class_name=ThemeState.root_class,
        ),
        appearance="inherit", accent_color=ThemeState.accent,
        gray_color=ThemeState.gray, radius=ThemeState.radius,
    )
```

`theme_controls_compact()`：把工具页顶栏里的主题下拉 + 模式按钮抽成一个可复用构建器（工具页与落地页共用，**单一来源**，不是复制）。

## 4. State 增补（`reflex_web.py`）

| 字段 | 变化 | 理由 |
|---|---|---|
| `download_exe_size_mb: str` | **新增** = `round(primary_exe.stat().st_size/1024/1024, 2)` | Hero CTA 副文案（历史版本行已用同样算法 `:3259`） |
| `download_image_data_url: str` | **保持不变**（原计划删除，见下「已推翻的前提」） | 它是当前唯一在 dev 与 prod 都成立的图片通道 |
| `load_download_info()` | 内部加 `download_exe_size_mb` 计算 | 单次扫描 |

落地页 `on_load=[ThemeState.theme_boot, State.load_download_info]`（工具页 `set_tab("download")` 路径不变）。

### 已推翻的前提（2026-09-15 实测，原设计错误）

原设计写「`/api/download/client_screenshot.png` 在 dev/prod 双通，改用 URL 并删除 base64」——**dev 侧不成立**：

- 实测 `http://localhost:3000/api/download/client_screenshot.png`、`/download/...`、`/fbimg/x.png`、`/ping` **全部返回 200 + `text/html`（SPA 兜底 3527 字节）**；只有直连 `http://localhost:8000/...` 返回 `image/png`（114765 字节）。
- `reflex_web/.web/env.json` = `{"PING": "http://localhost:8000/ping", "EVENT": "ws://localhost:8000/_event", ...}` → dev 下前后端**跨源、绝对地址**通信，前端**不代理**任何后端路径。`reflex_web.py:11851` 那条注释「开发模式 Vite 会把 /api/* 代理到后端」与实测不符。
- prod 侧原结论仍成立（`run_app.py:429` `_serve_download` 同时接受 `/download/` 与 `/api/download/`），但单侧成立不足以支撑「统一 URL」。

**决策**：Hero 截图沿用 `State.download_image_data_url`（base64 data URL，`download_image_available` 控可见性）。代价是 state 初始 delta 多 ~150KB（一次性、且是首屏主视觉，可接受）；收益是零新增失败模式，与「客户端下载」Tab 走同一条已验证通道。

**顺带发现的既有问题（本任务不修，仅登记）**：`feedback_model.screenshot_url()` 返回相对路径 `/fbimg/<name>`，Web 反馈列表在 **dev 模式（:3000）下截图同样是破图**（prod 同源才正常）。属独立缺陷，另行处理。

## 5. 视觉设计（可验收）

**布局骨架**（自上而下）：营销顶栏 → Hero → 统计条 → 功能网格 → 协议表 → 快速上手 → 下载 CTA → 页脚。

**Hero**：两列 `rx.grid`（≤900px 单列）
- 左：`badge(v{version} · Windows 桌面版)` → `h1` 「电力通信多协议，一站解析到底」→ 副标题（12 种协议 / 单帧到批量 / 解析到组帧 / 串口到抓包）→ 双 CTA（主：accent→accent-ink 渐变按钮；次：白底描边按钮）→ 小字（文件名 / 体积 / 免安装绿色版 · 更新日期）
- 右：窗口拟态卡（顶部三圆点条 + 1px border + 大阴影 + `border-radius:14px`），内含 `<img src=image_src>`；`image_available` 假 → 同尺寸占位（`image_off` 图标 + 「截图待更新」）
- 背景：`radial-gradient` 光晕（`--accent-soft`）×2 + 24px 网格线（`--grid` 线性渐变），用 `LANDING_CSS` 里的 `.landing-hero::before/::after` 表达

**统计条**：4 格，数字用 accent 渐变文字（`background-clip: text`），标签 muted。

**功能网格**：`grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`；卡片 = `rx.card` 变体：图标块（`--accent-soft` 底 + accent 图标）+ 标题 + 描述 + 标签行；`:hover` → `border-color: var(--accent)` + `translateY(-2px)` + 阴影增强。

**协议表**：`rx.table`，12 行；索引列 `rx.code`；「字节序」「校验」列 muted；斑马纹 `--card-hover`；窄屏 `overflow-x:auto` 包裹（`LANDING_CSS`）。

**快速上手**：左右两列 —— 左：4 条命令，每条为 `--code-bg` 代码块（JetBrains Mono 已在 `rx.App(stylesheets=…)` 加载）+ 一句说明；右：6 张系统集成小卡（图标 + 标题 + 一句）。

**下载 CTA**：整宽卡片，accent 渐变底 + 白字 + 大号下载按钮（同 `download_client`）+ 副链「或直接在线使用 →」。

**页脚**：品牌 + 版本 / 链接列 / 版权行；外链 `is_external=True`。

**主题与响应式**：全色值走 token，零裸 hex（品牌渐变里白色文字用 `#fff` 属例外，计入白名单）；`LANDING_CSS` 用 `@media (max-width: 900px)` 单列 + 隐藏锚点。

## 6. 契约（组件与测试共享）

- 测试可寻址的锚点（`data-testid`）：`landing-root` `nav-brand` `nav-online` `theme-preset` `theme-mode` `hero-title` `hero-download` `hero-online` `hero-shot`（或 `hero-shot-placeholder`）`feature-grid` `protocol-table` `quickstart-cli` `cta-download` `landing-footer`。
- 内部链接白名单：`INTERNAL_LINKS` 的值 + 锚点（`#features` `#protocols` `#quickstart` `#download`）。**落地页字符串中出现的任何 `href="/..."` 必须 ∈ 白名单**（测试断言）。
- 防漂移不变式：`len(PROTOCOLS) == len(protocol_registry)`（协议数一致）、`PROTOCOLS[i]["index"] == i`。

## 7. 测试与验证

`test/test_web_landing.py`（新，纯逻辑 + 组件树，不启服务）：
1. 内容不变式：12 协议 / index 连续唯一 / 与 `protocol_registry` 数量一致；`FEATURES` ≥10 且 title 唯一、icon 非空；`CLI_ACTIONS` 的 4 个参数名 ⊆ `main_gui` 实际支持的参数集合（读源码字符串断言，防文案漂移）。
2. 组件树构建：`landing_web.landing_page()`（全默认值）与带假数据的 `landing_page(version="9.9.9", ...)` 均成功；字符串含 Hero 标题、12 个协议名、全部 testid。
3. 缺图降级：`image_available=False` → 含 `hero-shot-placeholder` 且**不含** `hero-shot"`（testid 子串包含关系，断言要严）；`True` → 反之。**不断言 src 形态**（base64 data URL 与 URL 都算合法）。
4. 死链守卫：扫出所有 `href="/…"` → 全部 ∈ 白名单；断言扫出的集合非空（防正则失效导致假绿）。
5. 路由：`reflex_web.reflex_web.app._pages` 含 `"/"` 与 `"/app"`；`tool_page()` 仍含 9 个 tab testid。
6. 既有测试同步：`app.index()` 引用已改 `app.tool_page()`。

浏览器实测（dev server，:3000 前端 + :8000 后端）：`/` 浅色 + 深色截图、控制台无错误、无 404 资源；Hero 截图为 `<img>` 且**自然宽度 > 0**（破图会 naturalWidth===0，这是 base64 方案的直接判据）；点击 `nav-online`/`hero-online` → `/app`；`/app` 单帧解析实测出结果；`/app` 的「客户端下载」Tab 截图仍显示（回归）。

## 8. 兼容 / 回滚

- 路由改动是**破坏性**的（老书签 `/` 语义变了），但 `/` 仍可用，仅入口不同；无外部 API 依赖 `/`。
- 回滚点：`landing_web.py` 新增文件 + `reflex_web.py` 的导航/`add_page` 改动；回滚即还原 `index()` 名与 `route="/"`，删除新文件。
- 打包影响：`reflex_web_exe.spec` 若有显式 `hiddenimports` 需补 `reflex_web.landing_web`（实现步骤中核查）。
- **不触碰** `download_image_data_url` 的读写链路（`load_download_info` 的 base64 分支、`download_tab` 的 `rx.image`），因此不存在图片通道回归面。
