# 报文分享（Web页面 + GUI提交，共享数据库）

## Goal

用户在单帧解析后可将有价值的命令帧分享到共享数据库：Web 新增「报文分享」页面（浏览/搜索），GUI 单帧解析页新增「分享」按钮（提交到 Web API）。两端共享同一 `frameshare.db`，记录带来源（web/gui）。

## Background

- 现有反馈体系（1.19.0/1.20.0）已建立：API 双路由模式（dev Starlette Route + prod run_app.py 中间件）、`save_screenshot` 校验、频率限制、GUI `QNetworkAccessManager` 提交、`feedback.server_url` 服务器地址配置——本任务全程复用该模式。
- GUI 单帧解析完成后 `main_gui.py` 已缓存 `self.current_result`（帧字节）与 `self._last_parsed_hex`（空格分隔 hex）。

## Requirements

### R1 分享记录模型（frameshare.db）

- 表 `shareitem`：
  - `created_at: str`（ISO 本地时间）
  - `frame_hex: str`（空格分隔大写 hex，≤8192 字符）
  - `protocol: str`（协议名，非空）
  - `sharer: str`（分享人，必填 ≤50 字）
  - `note: str`（分享说明，选填 ≤500 字；GUI 自动带出当前协议与版本信息作默认说明基础）
  - `source: str`（web/gui，默认 web）
- 独立库 `reflex_web/data/frameshare.db`（与 feedback.db 同目录、同保留策略——部署脚本 data/ 整体保留，无需改脚本）。

### R2 Web 端

- 新页面 `/share`（导航栏「报文分享」入口，所有人可访问无需登录）：
  - 顶部搜索框（防抖 300ms）：匹配 报文 hex（含去空格连续匹配）/ 协议 / 分享人 / 说明
  - 时间倒序卡片列表：协议徽章 + 来源徽章（桌面端）+ 分享人 + 时间 + 报文 hex（等宽字体，超长截断显示）+ 说明摘要
  - 点击展开详情弹窗：完整 hex（可复制按钮）+ 说明 + 协议 + 若为可识别协议显示「解析」按钮跳转主页并自动填入解析（URL 参数带 hex+协议，主页 on_load 检查）
  - 分页（每页 20 条）
  - 「我要分享」按钮 → 跳转主页提示"解析后点击分享"（web 端提交入口在解析完成后的解析结果区加「分享此帧」按钮，弹出表单：分享人必填 + 说明，提交 source=web）
- GUI 提交 API：
  - `POST /api/frameshare`（JSON body，无截图——比反馈简单）：字段 frame_hex/protocol/sharer/note/source
  - `GET /api/frameshare/config`：下发协议名列表（GUI 用于校验）
  - 服务端校验：hex 合法（偶长、仅 hex 字符、长度 2~2048 字节）、sharer 必填 ≤50、protocol 在白名单（或"不确定"）、note ≤500
  - 频率限制：复用 FeedbackRateLimiter 模式（60s/10条/IP——分享比反馈高频，放宽）

### R3 GUI 端

- 单帧解析页按钮行新增「分享此帧」（set_btn success）：仅当 `current_result` 存在时可用
- 新文件 `share_dialog.py`（QDialog，模式同 feedback_dialog）：
  - 只读展示：报文 hex（等宽字体，QPlainTextEdit 只读）、协议名（自动带当前协议，可改下拉）
  - 输入：分享人（必填，记住上次输入到 config.json `share.last_sharer`）、说明（选填 ≤500，预填 "版本 x.y.z 协议解析示例"）
  - 服务器地址复用 `feedback.server_url`（同一服务器；显示可改但保存到同一配置）
  - QtNetwork POST JSON（`QNetworkRequest.setHeader(ContentTypeHeader, "application/json")` + `setBody(json.dumps().encode())`，20s 超时）——JSON 比 multipart 简单，无截图
  - 成功提示 + 可跳浏览器 `/share` 页查看

### R4 非功能

- Web 端分享不要求登录（内网信任环境，与反馈一致）
- 数据文件进 .gitignore（`reflex_web/data/` 已覆盖 frameshare.db）
- 测试：test_frame_share.py（模型 CRUD/搜索/hex 校验/submit_from_api/双路由解析回归）+ GUI 对话框纯逻辑测试并入同文件

## Acceptance Criteria

- [ ] Web `/share` 页面可浏览全部分享（时间倒序/分页/搜索/详情含复制 hex）
- [ ] Web 解析结果区「分享此帧」→ 表单提交 → 列表实时可见（source=web）
- [ ] GUI「分享此帧」→ 对话框提交 → Web 列表可见（source=gui，桌面端徽章）
- [ ] 服务端校验：非法 hex / 空 sharer / 超长 note 被拒绝并返回明确错误
- [ ] 频率限制生效（60s/10条/IP）
- [ ] 详情「解析」跳转主页自动填入单帧解析并触发解析
- [ ] 新增测试全过 + 既有回归（feedback 49/api 31/dialog 30/frame_gen 63/qp 84）不破坏
- [ ] 文档：AGENTS.md（架构树/测试清单）、CHANGELOG 1.21.0、README

## Constraints

- Reflex 0.9.8 组件级避坑（记忆 #61）全部适用：受控弹窗 on_open_change、事件链拉数据、ObjectItemOperation.to_string 等
- GUI 零新增 pip 依赖（QtNetwork JSON POST）
- 中文路径/GBK 控制台兼容（测试输出 ASCII/GBK 清洗）
