# Frontend Development Guidelines

> Best practices for frontend development in this project.

---

## Overview

This directory contains guidelines for frontend development. Fill in each file with your project's specific conventions.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | To fill |
| [Component Guidelines](./component-guidelines.md) | Component patterns, props, composition | 已填充（PySide6 新标签页组件规范 + 虚拟表「从站+主站下发」双角色契约 + Web 首页/路由搬迁契约 + 串口工具批量替换地址契约 §7h） |
| [Hook Guidelines](./hook-guidelines.md) | Custom hooks, data fetching patterns | To fill |
| [State Management](./state-management.md) | Local state, global state, server state | To fill |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns | To fill |
| [Type Safety](./type-safety.md) | Type patterns, validation | To fill |

---

## 项目硬约束（改代码前先读；详细契约见 component-guidelines.md）

### Web 前端（Reflex）

- **路由语义**：`/` = 产品首页（`reflex_web/reflex_web/landing_web.py`）；`/app` = 在线工具（`reflex_web.py::tool_page()`，即原 `index()`）；`/share`、`/feedback`、`/feedback-admin` 不变。**回介绍页用 `/`，回工具用 `/app`**；登录弹窗与反馈 Tab 只挂工具页。
- **依赖单向**：`landing_web.py` 不得 `import reflex_web`（与 `web_utils`/`theme_web` 同向）；运行时值（版本号/exe 体积/截图/下载事件/主题控件）一律参数注入。
- **颜色**：只用 `theme_web` 的 `var(--token)`，禁止裸 hex（`test/test_web_theme.py` 有守卫）。
- **dev 模式前端不代理任何后端路径**（`reflex run --env dev` 前后端跨源绝对地址通信）：页面里**不能用相对 URL 引后端静态资源**（`<img src="/api/download/x.png">` 在 dev 必破图），要用 base64 data URL。
- 完整契约（testid / 状态矩阵 / 测试断言点 / Wrong-vs-Correct）见 [Component Guidelines](./component-guidelines.md) 末尾「Scenario: Web 产品首页（落地页）与路由搬迁」。

---

## How to Fill These Guidelines

For each guideline file:

1. Document your project's **actual conventions** (not ideals)
2. Include **code examples** from your codebase
3. List **forbidden patterns** and why
4. Add **common mistakes** your team has made

The goal is to help AI assistants and new team members understand how YOUR project works.

---

**Language**: All documentation should be written in **English**.
