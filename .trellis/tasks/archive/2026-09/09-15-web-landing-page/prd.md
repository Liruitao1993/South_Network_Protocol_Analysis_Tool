# Web 版产品首页（落地页：介绍 GUI 客户端软件）

## Goal

Reflex Web 版当前**没有独立首页**：`/` 直接就是 9 个 Tab 的解析工具本体，「客户端下载」只是其中一个 Tab（`reflex_web.py:8161`）。用户拿到的第一个界面是干活用的工具台，不是产品说明。

本任务交付一个**独立、美观、可对外宣传的产品首页**（落地页），介绍桌面 GUI 客户端：Hero + 功能卡片 + 12 协议支持表 + 界面截图 + 快速上手 + 页脚，并把工具本体让到 `/app`。目标：第一次访问的人 10 秒内知道「这是什么、支持什么协议、能干什么、怎么下载」，然后一键下载 exe 或进入在线工具。

## Confirmed Facts（代码/文件证据，2026-09-15）

**路由与页面**
- `reflex_web.py:11751-11776` 共 4 条路由：`/`(index 工具) `/feedback` `/feedback-admin` `/share`。
- `index()` 在 `reflex_web.py:11554`，组合 `theme_style()` + `header()` + 9 个 Tab（单帧/批量/组帧/对比/查询/频谱图/报文工具/客户端下载/(管理员)发布管理/问题反馈）。
- `reflex_web.py:4438` `header(show_parse_controls: bool)`：工具页 True（带协议选择器 + 登录弹窗入口），独立页 False（「返回主页」`href="/"` + 管理员登录 `href="/"`）。
- 顶栏 `flex_wrap="nowrap"`（`:4634`），**横向空间已紧张**：品牌 + 协议选择器(320px) + 问题反馈 + 作者博客 + 报文分享 + 版本徽章 + 主题控件(下拉+按钮) + 管理员登录 + 就绪灯。
- 内部 `href="/"` 共 4 处：`:4511`（独立页返回主页）、`:4611`（独立页管理员登录）、`:9420`（feedback-admin「前往主页」）、`:9825`（share「去解析并分享」）。

**可复用素材（全部已存在）**
- `reflex_web/downloads/client_screenshot.png`（112KB，1916×1028）→ `State.download_image_available` / `State.download_image_data_url`（base64，`:3211-3220`）。
- `reflex_web/downloads/version.json` → `State.download_version` / `download_version_date` / `download_version_notes` / `download_version_url`（`:3234-3245`）。
- `reflex_web/downloads/client_readme.md`（357 行）：功能总览表 **17 行**、12 协议表（索引/协议/标准号/字节序/校验）、快速开始、打包说明。
- `State.download_client`（`:3281`）已实现「version.json url 优先，否则 `/api/download/<转义文件名>`」的下载跳转。
- `State.load_download_info`（`:3160`）扫描 downloads/ 填充上述字段。

**静态资源路由（已验证 dev/prod 双通）**
- dev：`app._api.routes.insert(0, Route("/download/{path:path}", _dev_download_handler))` + `/api/download/...`（`:11854-11859`），`_dev_download_handler` 按 `mimetypes` 猜 mime 内联返回（仅 `?dl=1` 才 attachment）。
- prod：`run_app.py:429` `_serve_download` 同时接受 `/download/` 与 `/api/download/` 前缀。
- → `<img src="/api/download/client_screenshot.png">` 两种模式都可用，**无需 base64 进 state**。

**主题系统（首页必须吃满）**
- `theme_web.py`：`TOKENS_LIGHT`/`TOKENS_DARK`（29 个语义 token）、`ACCENT_OVERRIDES`(+DARK) 5 个强调色、`build_theme_css()`、`theme_class(accent)`。
- `ThemeState`（`:4286`）：`preset/accent/gray/radius/mode` + `theme_boot/apply_choice/cycle_mode/restore`，`persist_js/restore_js` 走 `localStorage['nw-theme']`。
- `theme_style()`（`:4424`）= `SEARCHABLE_CSS + GLOBAL_CSS + build_theme_css()`，**每个页面必须挂**。
- 页面模板：`rx.theme(appearance="inherit", accent_color=ThemeState.accent, gray_color=ThemeState.gray, radius=ThemeState.radius)`（`:11556-11731`）。

**CLI 与系统集成（首页「快速上手」的事实来源）**
- `main_gui.py:7038-7063` 支持 `--parse` / `--protocol` / `--file` / `--minimized` / `--clipboard`。
- `system_integration/`：系统托盘、全局热键 Ctrl+Alt+X、单实例、剪贴板 hex 自动检测、Notepad++ 集成、`.log/.txt/.hex/.bin` 右键菜单、开机自启。

**会被本任务打破的既有测试（必须同步改）**
- `test/test_web_spectrum.py:279` 与 `test/test_web_theme.py:231`：`str(app.index())` 断言「主页含频谱图 tab / 主题控件」→ 若 `index()` 让位给落地页即失效（两文件都在 `release_check.py:CORE_TESTS`）。
- `reflex_web/tests/test_reflex_app.py`：7 个 playwright 用例 `page.goto(reflex_app)` 后找 Tab → 工具页搬到 `/app` 后全部失效。

**模块依赖方向（架构约束）**
- `web_utils / lookup_utils / spectrum_web / theme_web / share_model / feedback_model / admin_release` **均不 import `reflex_web`**；`reflex_web.py` 单向 import 它们（`:24-25`）。
- → 新模块 `landing_web.py` 必须同向：只放内容数据 + 纯展示组件（参数注入），由 `reflex_web.py` 组合并注入 `State`/`ThemeState`。

## Requirements

### R1 路由重组（无死链是硬约束）
- `/` → 新的产品首页；`/app` → 现有工具页（原 `index()`）。
- `/share`、`/feedback`、`/feedback-admin` 路由与内容不变。
- 所有指向 `/` 的内部链接按语义改指：**「回工具」语义 → `/app`**（`:4511`、`:4611`、`:9420`、`:9825`），**「回首页」语义 → `/`**。
- 工具页顶栏品牌块（logo + 「多协议解析平台」）变为指向 `/` 的链接（**不新增按钮**，顶栏已 `nowrap` 空间紧张）。
- 独立页顶栏：`返回主页` → 文案改「在线工具」→ `/app`；未登录态「管理员登录」→ `/app`（登录弹窗只挂在工具页，`reflex_web.py:11718`）。

### R2 Hero 首屏
- 主标题 + 副标题（一句话说清「电力通信多协议解析调试工具，覆盖 12 种协议」）+ 版本徽章（读 `State.download_version`，空则隐藏）。
- 双 CTA：**下载客户端**（`State.download_client`，未就绪时禁用并提示）与 **进入在线工具**（`/app`）。
- CTA 副文案给出 exe 文件名 + 体积 + 平台（Windows 10/11），数据来自 downloads/ 实况。
- 右侧界面截图：`<img src="/api/download/client_screenshot.png?v=<mtime>">`；`download_image_available` 为假时降级为占位卡（图标 + 说明），**不得出现破图**。
- 关键数字条（≥3 项，数字必须可从仓库事实核对）。

### R3 核心功能卡片网格
- ≥10 张卡片，每张：lucide 图标 + 标题 + 一句说明（可选标签）。
- 内容必须与产品实际功能一致（来源：`client_readme.md` 功能总览 17 行 + `AGENTS.md §3`），**不得宣传不存在的能力**。

### R4 12 种协议支持表
- 12 行，列：索引 / 协议 / 标准号 / 字节序 / 校验，数值与 `AGENTS.md §1`、`client_readme.md` 一致。
- 加防漂移断言：行数 == `protocol_registry` 协议数，索引唯一且覆盖 `0..N-1`。

### R5 快速上手
- 4 条 CLI 示例（`--parse` / `--file` / `--clipboard` / `--minimized`），命令与参数名与 `main_gui.py:7038` 逐字一致。
- 系统集成条目（托盘 / 全局热键 / 剪贴板检测 / 右键菜单 / 开机自启 / 单实例）。

### R6 页脚
- 品牌 + 版本号；链接：作者博客（CSDN 外链，新标签打开）、问题反馈 `/feedback`、报文分享 `/share`、进入在线工具 `/app`。

### R7 视觉与主题（「非常美观」的可验收拆解）
- 落地页有自己的营销顶栏（锚点导航 + 主题控件 + CTA），**不复用**工具页 `header()`。
- 全部颜色走 CSS token（`var(--*)`），**禁止裸 hex**（`theme_web.build_theme_css()` 已提供 5 强调色 × 浅/深）。
- 浅色 / 深色 / 至少 2 个强调色下渲染正常（截图佐证）。
- 响应式：≤900px 单列、顶栏锚点收起、表格可横向滚动；不得出现横向溢出滚动条。
- 视觉层次要求：Hero 有背景光晕/网格、截图卡有窗口拟态与阴影、卡片 hover 有反馈（边框转强调色 + 轻微上移）、区块间有节奏感（统一 section 间距与标题样式）。

### R8 质量与文档
- 新增 `test/test_web_landing.py`（内容不变式 + 组件树 + 路由 + 死链守卫），登记 `release_check.py:CORE_TESTS`。
- 更新 `test/test_web_spectrum.py`、`test/test_web_theme.py`（`app.index()` → 工具页函数）、`reflex_web/tests/test_reflex_app.py`（goto `/app` + 新增落地页冒烟）。
- 更新 `AGENTS.md`（§1 Web 能力、§3 架构、§7 测试清单、§8 陷阱）、`main_gui.py:CHANGELOG`、`README.md`。
- `python release_check.py` 无 FAIL。

## Acceptance Criteria

1. 访问 `http://<host>:3000/` 得到产品首页：可见 12 个协议名、≥10 张功能卡、Hero 双 CTA、截图（或降级占位）、CLI 示例、页脚；**页面内无 404 资源、无破图**。
2. 点击「进入在线工具」→ `/app`，9 个 Tab 全部可用（单帧解析实测能出结果）。
3. 工具页顶栏品牌块点击 → 回 `/`；独立页「在线工具」→ `/app`；`/share` 的「去解析并分享」→ `/app`。**全站无指向已不存在页面的链接**。
4. 版本徽章/下载按钮与 `downloads/` 实况一致：有 exe 时显示版本 + 文件名 + 体积并可下载；无 exe 时按钮禁用且有提示。
5. 浅色 / 深色（`ThemeState` 切换）下首页均正常渲染；切强调色后 Hero 渐变、CTA、卡片 hover 边框随之变化。
6. ≤900px 视口无横向溢出；Hero 单列堆叠。
7. `python test/test_web_landing.py`、`test_web_spectrum.py`、`test_web_theme.py` 全绿；`python release_check.py` 无 FAIL。

## Out of Scope

- 「版本与更新」独立区块（更新说明/历史版本表）——用户未选；现有「客户端下载」Tab 保留这一职责。
- 首页多语言 / i18n。
- 落地页的服务端 SEO 预渲染、OG 卡片图生成。
- 桌面 GUI 本体任何改动（本任务只改 Reflex Web 侧）。
- 工具页 Tab 结构、Topbar 协议选择器行为不变。

## 人工事项（需用户提供/确认，代码只做机制与降级）

1. **截图替换**：现有 `downloads/client_screenshot.png` 是 v1.12.0（2026-08-13）的空态界面（无解析结果），用作 Hero 主视觉偏弱。建议替换为当前版本、带解析结果与频谱图的界面截图（同名覆盖即可，首页自动带 `?v=mtime` 破缓存）。
2. **version.json 内容**：仓库内为 `1.14.13`（`notes: "3333333"`），与当前 `APP_VERSION=1.23.13` 不一致。首页徽章与下载按钮读它，发布前应由「发布管理」Tab 或手工更新。

## Risks / Deferred

- **Reflex 组件 API 细节需实测**：`rx.cond` 接受纯 Python bool、`add_page(description=...)` 是否支持、`rx.grid` 的 `auto-fill` 表达方式 —— 实现时先用最小脚本验证，不成立则改用等价写法（`style={"grid_template_columns": ...}` / `rx.el.div`）。
- **顶栏空间**：独立页文案从「返回主页」改「在线工具」宽度相近；品牌块变链接不增宽。若实测挤压协议选择器，则在 `GLOBAL_CSS` 收紧 `padding`。
- **base64 截图改为 URL**（`download_image_data_url` → `download_image_src`）会让「客户端下载」Tab 的图片来源从 state 变为 HTTP 路由：需确认 prod 单端口模式下 `/api/download/` 前缀确实命中中间件（已在 `run_app.py:429` 核实），并用浏览器实测下载 Tab 截图仍显示。
- **playwright 测试**（`reflex_web/tests/`）本机需浏览器依赖，未必能跑通；若无法运行，改为在 `test_reflex_app.py` 添加 `/app` 路径常量并在报告中标注未执行原因。
