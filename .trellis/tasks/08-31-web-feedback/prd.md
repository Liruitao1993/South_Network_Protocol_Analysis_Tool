# Web版问题反馈页面（SQLite持久化）

## Goal

在 Reflex Web 版（多协议解析平台）新增「问题反馈」页面：用户可提交软件问题反馈（含截图），数据存入 SQLite；管理员可查看/处理反馈。**重新部署 Web 版后反馈数据不丢失**。

## Background

- Web 版现状：Reflex 0.9.8 单文件应用 `reflex_web/reflex_web/reflex_web.py`，无数据库；批量解析文件上传已存 `reflex_web/uploaded_files/`。
- 部署方式：`build_embedded_deploy.py`（内嵌 Python）/ `build_offline_deploy.py`（UV venv）会**重建部署目录**（保留 `python/`，其余源码/数据层刷新）——直接写在部署目录其他位置的运行时数据会被覆盖/丢失。
- 发布管理已用 `admin_config.json` 做管理端口令，复用该机制保护反馈管理页。

## Requirements

### R1 反馈提交页（用户侧）

- 路由 `/feedback`（导航栏入口）。
- 表单字段：
  - 问题类型（下拉：功能异常/解析错误/界面体验/新功能建议/其他）
  - 涉及协议（下拉：跟随主程序 12 种协议 + "不确定"）
  - 问题描述（多行文本，必填，≤2000 字）
  - 联系方式（选填，≤100 字）
  - 截图上传（选填，最多 3 张，jpg/png/webp，单张 ≤5MB）
- 提交成功显示确认提示；校验失败（必填缺失/超长/类型不符）给出明确错误提示。
- 提交内容写入 SQLite 数据库；截图保存到服务端磁盘目录。

### R2 反馈管理页（管理员侧）

- 路由 `/feedback-admin`，**需要口令**（复用 `admin_config.json` 现有管理口令机制，风格与发布管理一致）。
- 功能：
  - 反馈列表（时间倒序）：时间/类型/协议/状态/问题描述摘要
  - 点击查看详情：完整描述、联系方式、截图预览
  - 状态流转：待处理 → 已确认 / 已修复 / 已忽略（可改）
  - 删除反馈（含关联截图文件）
  - 未处理数量徽章显示
- 分页（每页 20 条）。

### R3 数据持久化（核心约束）

- 反馈数据存储于部署目录 `data/` 子目录：
  - `data/feedback.db` — SQLite 数据库
  - `data/uploads/feedback/` — 截图文件
- **增量部署（`--skip-deps`）与完整重建部署都必须保留 `data/`**：
  - `build_embedded_deploy.py`：重建其余目录时移走 `data/` 再移回（与 `python/` 同等保留待遇）。
  - `build_offline_deploy.py`：同样处理。
- 开发模式运行时，数据落在 `reflex_web/data/`（源码目录内），不受部署影响。

### R4 非功能

- 反馈提交不要求登录，无口令（用户已确认内网信任环境）。
- SQLite 通过 Reflex `rx.Model`（sqlmodel）访问，自动建表。
- 文件类型/大小校验在服务端执行（前端提示仅辅助）。
- 界面风格与现有页面一致（深色主题、卡片布局）。

## Acceptance Criteria

- [ ] `/feedback` 可提交反馈：必填校验、类型/协议下拉、≤3 张截图上传，成功后数据库新增记录
- [ ] 截图落盘 `data/uploads/feedback/`，文件名不含用户可控原始名（防路径穿越）
- [ ] `/feedback-admin` 口令验证后可查看列表/详情/截图，可改状态、删除（删除时截图文件一并删除）
- [ ] SQLite 中删除记录与文件删除保持一致（不留孤儿文件）
- [ ] `build_embedded_deploy.py --skip-deps` 与完整模式执行后，部署目录 `data/feedback.db` 与截图均保留（用旧数据模拟验证）
- [ ] `build_offline_deploy.py` 同样保留 `data/`
- [ ] 新增 `test/test_web_feedback.py`：模型 CRUD / 文件保存清理 / 部署脚本 data/ 保留逻辑（纯逻辑部分）
- [ ] 现有 Web 测试（`test_web_frame_gen_utils.py` 等）与主程序测试不受影响
- [ ] 文档同步：AGENTS.md §2/§3、README.md、`reflex_web/离线部署.md`（如涉及）、main_gui.py CHANGELOG

## Constraints

- Reflex 版本 0.9.8，不引入新重量级依赖（sqlmodel 随 Reflex 自带）。
- Windows / Linux 双平台部署均需工作。
- 中文路径兼容（部署目录可能含中文）。
