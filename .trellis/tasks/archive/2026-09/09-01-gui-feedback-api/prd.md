# GUI客户端问题反馈接入Web服务（共享数据库）

## Goal

给 Web 服务端开放问题反馈 HTTP API；PySide6 GUI 客户端新增「问题反馈」功能（帮助菜单入口），提交的反馈写入 Web 服务端数据库，与 Web 页面的反馈列表/管理共用同一个 `reflex_web/data/feedback.db`。

## Background

- Web 版问题反馈已上线（f93c7bc + 本轮未提交修复）：`reflex_web/data/feedback.db`（SQLite）+ `/feedback` 提交页 + 主页反馈 Tab（权限分层）+ `/fbimg/` 截图路由。
- GUI 已有菜单栏：`main_gui.py` L5653 帮助菜单（检查更新/关于）——反馈入口加在此处。
- GUI 已有连接 Web 服务器的先例：`config.json "update"` 段的 `private_url`（自动更新）。反馈服务器地址沿用此模式（`config.json "feedback"` 段）。
- GUI 打包exe 分布在现场内网，Web 服务部署在运维可访问的服务器上——反馈需要跨机器提交。

## Requirements

### R1 Web 服务端反馈 API（run_app.py / reflex_web）

- `POST /api/feedback`（multipart/form-data）：
  - 字段：`issue_type`（必须，白名单校验）、`protocol`（必须）、`description`（必须 ≤2000）、`contact`（选填 ≤100）、`client`（选填，固定 "gui" 标识来源）
  - 文件：`screenshots`（选填，可多个，≤3 张，jpg/png/webp，单张 ≤5MB，复用 `feedback_model.save_screenshot` 校验与防穿越）
  - 返回 JSON：`{"ok": true, "id": N}` / `{"ok": false, "error": "..."}`（HTTP 400 参数错 / 413 超限 / 500 内部错误）
  - 写入同一个 `reflex_web/data/feedback.db`（复用 `FeedbackStore`），来源标记：`contact` 或新列不强制——用 `client="gui"` 存入（设计评审定字段方案，倾向 FeedbackItem 增加 `source` 列默认 "web"，GUI 提交为 "gui"）
- `GET /api/feedback/config`：返回 `{"ok": true, "max_desc_len": 2000, "max_screenshots": 3, "max_size_mb": 5}`（GUI 拉取限制参数，失败不阻塞提交）
- CORS：允许跨域（GUI 用 Qt 网络请求非浏览器，无预检；但开发调试页面可能需要）——仅对 `/api/feedback*` 加 `Access-Control-Allow-Origin: *`，不动全局
- 生产（run_app.py ASGI 中间件）与开发（reflex_web.py Starlette Route）双实现，与 `/fbimg/` 路由同模式
- 频率限制：轻量防滥用——同一 IP 每分钟最多 5 条（内存计数即可，无需持久化）

### R2 GUI 客户端反馈对话框（PySide6）

- 入口：帮助菜单「问题反馈(&F)...」（检查更新与关于之间）
- 新组件 `feedback_dialog.py`（遵循"新 UI 组件独立成文件"原则）：
  - 字段：问题类型下拉（与 Web 一致 5 项）、涉及协议下拉（12 协议+不确定）、问题描述（QTextEdit，必填，实时字数 ≤2000）、联系方式（选填 ≤100）
  - 截图：最多 3 张（QListWidget + 添加/移除按钮，文件对话框选择 jpg/png/webp，预览缩略图可选；仅校验扩展名与大小，不读内容）
  - 服务器地址：`config.json "feedback"` 段 `{"server_url": "http://127.0.0.1:8000"}`；对话框内显示当前地址（只读标签）+「设置」按钮打开输入框修改（写回 config.json）；默认值 `http://127.0.0.1:8000`
  - 提交：QNetworkAccessManager multipart POST（Qt 网络栈，无需 requests 依赖）；提交中按钮禁用+进度提示；成功弹「提交成功」并关对话框；失败显示错误（服务器不可达给出友好提示"无法连接反馈服务器，请检查网络或稍后再试"）
  - 线程安全：QNetworkAccessManager 异步回调，不阻塞 UI
- 主 GUI 集成：`main_gui.py` 帮助菜单加 action；不改其他逻辑

### R3 共享数据库约束

- GUI 提交的反馈与 Web 页面提交落在同一 `data/feedback.db`、同一 `uploads/feedback/` 目录
- Web 主页反馈 Tab 与管理页能查看/处理 GUI 提交的反馈（无需改动——同一张表；若加 source 列则列表行加一个小标识，非必须）
- 部署脚本 data/ 保留逻辑不受影响

## Acceptance Criteria

- [ ] `curl -F` 提交 POST /api/feedback 成功 → 数据库新增记录（client 字段为 gui）、截图落盘、Web 主页反馈 Tab 可见
- [ ] 缺必填/超长/非法扩展名/超大文件 → 400/413 + 明确 error 消息
- [ ] 频率限制生效（1 分钟内第 6 条返回 429 或明确拒绝提示）
- [ ] GUI 帮助菜单打开反馈对话框，填写+选截图提交 → 成功提示；数据库可见新记录且 source=gui
- [ ] 服务器不可达时 GUI 显示友好错误，不崩溃
- [ ] 服务器地址可在对话框内修改并持久化到 config.json "feedback" 段
- [ ] 新增 test/test_feedback_api.py（服务端：正常提交/参数校验/频率限制/截图校验）与 GUI 对话框纯逻辑测试（字段校验、multipart 构造），全部通过
- [ ] 现有 test_web_feedback.py 49 项不回归
- [ ] 文档同步：AGENTS.md（架构树 feedback_dialog.py、API 说明）、README、CHANGELOG

## Constraints

- GUI 侧仅用 PySide6 自带 QNetworkAccessManager（不新增 requests 依赖——exe 打包体积敏感）
- API 路径与字段命名与 Web 前端提交逻辑字段对齐（issue_type/protocol/description/contact/screenshots）
- 反馈提交无需登录（与 Web 一致，内网信任环境）
- Windows/Linux GUI 均需工作（QNetworkAccessManager 跨平台）
