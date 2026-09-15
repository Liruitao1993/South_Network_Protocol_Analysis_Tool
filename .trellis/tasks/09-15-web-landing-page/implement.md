# 实施计划：Web 版产品首页（落地页）

前置：`prd.md`（R1~R8）、`design.md`（路由表/模块结构/State 增补/视觉规格/契约）。
顺序原则：**先内容与纯组件（可离线测）→ 再接线路由 → 再改既有引用 → 再浏览器验收**。

---

## 步骤 0 — 前置 API 实测（5 分钟，避免整段返工）

Reflex 组件 API 有 3 处不确认（`prd.md` Risks），先用最小脚本验证，不成立就换等价写法并在 `design.md` 回记：

```bash
python -c "import reflex as rx; print(hasattr(rx,'grid'), hasattr(rx,'el')); import inspect; print('description' in inspect.signature(rx.App.add_page).parameters)"
```

- [ ] `rx.cond(<plain bool>, a, b)` 可构建
- [ ] `app.add_page(..., description=...)` 支持（不支持则省略该参数）
- [ ] 网格自动填充表达（`rx.grid(columns="repeat(auto-fill, minmax(280px,1fr))")` 或 `style={"grid_template_columns": ...}`）

---

## 步骤 1 — `reflex_web/reflex_web/landing_web.py`（纯内容 + 纯组件）

1. 头部：`from __future__ import annotations`、`import sys` + `ROOT` 注入（与 `web_utils.py` 同款）、`import reflex as rx`。
2. 常量：`INTERNAL_LINKS`、`FEATURES`(12)、`PROTOCOLS`(12)、`CLI_ACTIONS`(4)、`SYSTEM_INTEGRATIONS`(6)、`HERO_STATS`(4)。
   - 协议表逐行对照 `AGENTS.md §1`（索引/协议名/标准号/字节序/校验），**不得凭记忆**。
   - 功能卡逐条对照 `client_readme.md` 功能总览 17 行，只写有实现的能力。
3. `LANDING_CSS`：hero 光晕/网格、窗口拟态、卡片 hover、section 间距、协议表窄屏滚动、`@media (max-width:900px)`。
4. 组件构建器：`landing_nav / landing_hero / landing_features / landing_protocols / landing_quickstart / landing_cta / landing_footer / landing_page`（签名见 `design.md §3`），全部带 testid。

**验收**：
```bash
python -c "import sys;sys.path.insert(0,'reflex_web');from reflex_web import landing_web as L;print(len(L.PROTOCOLS), len(L.FEATURES), len(L.CLI_ACTIONS), len(L.HERO_STATS));print(str(L.landing_page())[:200])"
```
期望：`12 12 4 4` 且组件树可 `str()`。

---

## 步骤 2 — `reflex_web.py`：State 增补（下载/图片字段）

- [ ] `download_image_src: str = ""` 新增；`download_image_data_url` 删除（同时删 base64 计算分支）。
- [ ] `download_exe_size_mb: str = ""` 新增（`round(size/1024/1024, 2)`，与历史版本行同算法）。
- [ ] `load_download_info()` 改为：算 `download_image_src = f"/api/download/client_screenshot.png?v={int(mtime)}"`。
- [ ] `download_tab()`（`:8327`）图片 `src` 改 `State.download_image_src`。

**验收**：`python -c "import re;s=open('reflex_web/reflex_web/reflex_web.py',encoding='utf-8').read();print(s.count('download_image_data_url'), s.count('download_image_src'))"` → `0 2+`。

---

## 步骤 3 — `reflex_web.py`：路由与导航接线

- [ ] `index()` → `tool_page()`（保留全部 Tab 内容，行首加 `data-testid="tool-root"` 的根标记或等价锚点）。
- [ ] 顶栏主题控件抽为 `theme_controls_compact()`，工具页顶栏改调它（**单一来源**）。
- [ ] 新增 `def landing_page()` 组合（`design.md §3` 代码骨架），挂 `theme_style()` + `LANDING_CSS` + `ThemeState.root_class`。
- [ ] `header()`：品牌块包 `rx.el.a href="/"`（testid `nav-brand`）；「返回主页」→「在线工具」`href="/app"`（testid `nav-tool`）；独立页管理员登录 `href="/app"`。
- [ ] `:9420`（feedback-admin）、`:9825`（share）→ `/app`。
- [ ] `add_page`：`tool_page` → `route="/app"`，`title="多协议解析平台 - 在线工具"`；新增 `landing_page` → `route="/"`，`title="多协议解析平台 - 电力通信协议解析与调试工具"`，`on_load=[ThemeState.theme_boot, State.load_download_info]`。
- [ ] 核查 `reflex_web/reflex_web_exe.spec` 是否需补 `reflex_web.landing_web` hiddenimport（该模块被 `reflex_web.py` 顶层 import，通常静态可分析，确认即可）。

**验收**：
```bash
python -c "import sys;sys.path.insert(0,'reflex_web');import reflex_web.reflex_web as m;print(sorted(m.app._pages));print('tool_page', hasattr(m,'tool_page'))"
```
期望：路由集合含 `/` `/app` `/share` `/feedback` `/feedback-admin`。

---

## 步骤 4 — 测试：新增 + 同步既有

- [ ] `test/test_web_landing.py`（`design.md §7` 六类断言，含死链守卫与防漂移）。
- [ ] `test/test_web_spectrum.py`、`test/test_web_theme.py`：`app.index()` → `app.tool_page()`。
- [ ] `reflex_web/tests/test_reflex_app.py`：`page.goto(reflex_app + "/app")`；新增 `test_landing` 断言 Hero/协议表/`nav-online` 存在。
- [ ] `release_check.py:CORE_TESTS` 增 `test/test_web_landing.py`（放在 `test_web_theme.py` 之后）。

**验收**：
```bash
python test/test_web_landing.py && python test/test_web_spectrum.py && python test/test_web_theme.py
python release_check.py --skip-tests   # 或全跑
```

---

## 步骤 5 — 浏览器验收（dev 服务，真实渲染）

1. `hub start` 起 dev 服务（**绕幽灵端口**：`--backend-port 8002`，前端 3000）。
2. 自动化检查：`/` 无 console error、无 404 资源；截图浅色 + 深色（切 `ThemeState`）+ 1 个非默认强调色。
3. 交互：点 `nav-online`/`hero-online` → 落到 `/app`；`/app` 单帧解析 `68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16` 出结果；`?v=` 图片请求 200。
4. ≤900px 视口截图：无横向溢出。
5. 下载 Tab 的截图仍正常显示（验证步骤 2 的 URL 化没有回归）。

---

## 步骤 6 — 文档

- [ ] `AGENTS.md`：§1（Web 首页/路由）、§3 架构树（`landing_web.py` + 路由表）、§7（测试清单加 `test_web_landing.py`）、§8（新增陷阱：路由 `/` 与 `/app` 的语义、`download_image_src` 取代 base64）、§10 摘要。
- [ ] `main_gui.py:CHANGELOG` 头部新增条目（1.23.14 或当前开发版本）。
- [ ] `README.md`：Web 版入口说明（`/` 首页、`/app` 工具）。
- [ ] `reflex_web/downloads/client_readme.md` 不动（属发布产物内容）。

---

## 完成定义（DoD）

- R1~R8 全部满足，逐条对应 `prd.md` Acceptance Criteria 1~7。
- 三个测试文件全绿 + `release_check.py` 无 FAIL。
- 浏览器截图（浅色/深色/强调色/窄屏）与 `?v=` 图片 200 的证据在提交说明里记录。
- `design.md §8` 的回滚点有效（可单文件回退）。
