# 技术设计 — GUI客户端问题反馈接入Web服务

## 1. 总体架构

```text
GUI (PySide6)                         Web 服务端
┌──────────────────┐    HTTPS/HTTP    ┌─────────────────────────────┐
│ feedback_dialog.py│ ── multipart ──▶ │ POST /api/feedback          │
│  (QDialog)        │                  │  ├─ 参数校验/频率限制        │
│  QNetwork mgr     │                  │  ├─ save_screenshot() 复用  │
└──────────────────┘                  │  └─ FeedbackStore.add()     │
                                      │        ↓                    │
                                      │ reflex_web/data/feedback.db │
                                      │ reflex_web/data/uploads/    │
                                      └─────────────────────────────┘
GUI config.json "feedback" 段 ──▶ server_url（默认 http://127.0.0.1:8000）
```

## 2. 数据模型微调（feedback_model.py）

FeedbackItem 增加 `source: str = "web"` 列（web/gui）：

- `create_all` 幂等只建缺失表；**已存在的表不会自动加列**——需要轻量迁移：
  `FeedbackStore.__init__` 里 create_all 后执行 `PRAGMA table_info(feedbackitem)`，
  无 `source` 列则 `ALTER TABLE feedbackitem ADD COLUMN source VARCHAR DEFAULT 'web'`。
- `add()` 无需改（source 由构造时传入）；Web 页面提交处补 `source="web"`，API 提交传 `source="gui"`。
- 列表 dict 输出加 `source` 字段；Web 主页列表行在 `source=="gui"` 时显示一个「桌面端」小徽章（青色，区别于状态徽章）。

## 3. Web 服务端 API

### 3.1 路由与实现（双模式，与 /fbimg/ 同套路）

- **开发模式**：`reflex_web.py` 尾部 Starlette Route `POST /api/feedback`，handler 为异步函数，直接调 `feedback_model`。
- **生产模式**：`run_app.py` ASGI 中间件新增 `/api/feedback` 前缀分支 → `_handle_feedback_api`（解析 multipart、返回 JSON）。
- **公共逻辑抽出**：`feedback_model.py` 新增纯函数 `submit_from_api(fields: dict, files: list[tuple[str, bytes]]) -> tuple[bool, str|int, int]`（返回 (ok, id_or_error, http_status)），两条路由共用，单测覆盖。内部：
  1. `issue_type in ISSUE_TYPES`、description 非空≤MAX_DESC_LEN、contact≤MAX_CONTACT_LEN、protocol 非空
  2. files 数量 ≤3、每张走 `save_screenshot`（扩展名+魔数+大小三重校验）
  3. `FeedbackItem(source="gui")` + `FeedbackStore.instance().add()`
  4. 频率限制不放在纯函数里（需要请求上下文），由路由层做

### 3.2 multipart 解析

- 不引入 python-multipart 手工解析（虽然 Reflex 依赖里有，但走标准库更稳）：
  开发模式用 Starlette `request.form()`（starlette 自带 multipart 解析，无需额外依赖）；
  生产 run_app.py 中间件手工解析 multipart body（`boundary` 切分，二进制安全）——`_parse_multipart(body, boundary) -> (fields, files)` 纯函数放 feedback_model.py 或 run_app.py 内，单测覆盖。
- 截图文件名：API 里客户端传 `filename`（如 `shot.png`），仅取后缀；服务端重生成文件名逻辑复用。

### 3.3 频率限制

- 路由层内存 dict `{ip: [timestamps]}`，滑动窗口 60s 内 >5 次 → 返回 429 `{"ok":false,"error":"提交过于频繁，请稍后再试"}`。
- 进程级（单进程部署足够）；不持久化，重启清零可接受。

### 3.4 CORS

- `/api/feedback` 响应统一加 `Access-Control-Allow-Origin: *`（宽松——无 cookie/无认证接口，无 CSRF 面；方便以后 Web 前端直调）。OPTIONS 预检请求直接 204 返回。

### 3.5 GET /api/feedback/config

- 返回 `{ok, issue_types, protocols, max_desc_len, max_screenshots, max_size_mb}`，GUI 用于填充下拉（失败时用 GUI 内置默认值，不阻塞）。

## 4. GUI 客户端（feedback_dialog.py 新文件）

### 4.1 FeedbackDialog(QDialog)

```text
┌ 问题反馈 ────────────────────────────────┐
│ 问题类型 [功能异常 ▾]   涉及协议 [不确定 ▾] │
│ 问题描述 *                                │
│ ┌────────────────────────────┐ 字数 0/2000│
│ │ QTextEdit                  │           │
│ └────────────────────────────┘           │
│ 联系方式（选填）[________]                 │
│ 截图（选填，≤3张） [添加截图] [移除选中]     │
│ ┌ QListWidget（文件名+大小）┐              │
│ 服务器: http://... [修改]                 │
│           [提示条 QLabel]   [提交反馈]     │
└──────────────────────────────────────────┘
```

- 字段常量（ISSUE_TYPES、协议列表、限制值）与 Web 侧对齐，写在对话框顶部（不 import reflex 相关模块——GUI 不依赖 web 包）。
- 校验（提交前本地）：描述必填≤2000、联系方式≤100、截图数≤3 且扩展名 {png,jpg,jpeg,webp} ≤5MB。
- 服务器地址：`config.json "feedback"."server_url"`，读写走 `main_gui._app_config` 同款 json 读写（对话框内自实现 `_load_server_url/_save_server_url`，避免耦合主窗口）。
- 网络发送：`QNetworkAccessManager.post(QNetworkRequest, QHttpMultiPart)`；finished 回调解析 JSON（QJsonDocument）；errorOccurred → 友好提示。超时 `setTransferTimeout(15000)`。
- 提交成功：QMessageBox 信息 → accept() 关闭；失败：红色提示条。
- multipart 构造：文本字段 QHttpPart（Content-Type: text/plain + name）；截图 QHttpPart（Content-Type: image/png + filename）。字段名与 API 对齐。

### 4.2 main_gui.py 集成（最小改动）

- 帮助菜单（L5653 区域）加：

  ```python
  feedback_act = help_menu.addAction("问题反馈(&F)...")
  feedback_act.triggered.connect(self._show_feedback_dialog)
  ```

- `_show_feedback_dialog`：懒 import `feedback_dialog.FeedbackDialog` 并 exec()（保持 main_gui 不新增顶层 import）。

### 4.3 部署与打包

- `feedback_dialog.py` 在项目根（与 gui_utils.py 同级），主程序 spec 无需改（py 文件自动收集）。
- Web 侧无新依赖（starlette form 解析自带；频率限制纯内存）。

## 5. 安全要点

- API 无认证（与 Web 提交页一致，内网信任环境）；频率限制防滥用。
- 截图仍走 `save_screenshot` 全套校验（扩展名/魔数/大小/重生成文件名），用户文件名不参与落盘路径。
- description/contact 存库为纯文本，Web 管理页展示时 Reflex 默认转义，无注入面。
- CORS `*` 仅开放 `/api/feedback*`（无凭据接口），不扩大到全局。

## 6. 测试设计

### test/test_feedback_api.py（新）

纯逻辑 + Starlette TestClient（开发路由）：

1. `submit_from_api` 正常提交（无截图）→ ok, id 递增, source=gui
2. 缺 description / 超长 / 非法 issue_type → 对应错误
3. 带截图：合法 png → 落盘；非法扩展/魔数/超 3 张 → 拒绝
4. `_parse_multipart`：构造含文本+二进制文件的 body → 字段与字节完整往返（run_app 手工解析器单测）
5. 频率限制：同 IP 连续 6 次 → 第 6 次 429（路由层测试用 TestClient + monkeypatch 计数器）
6. `PRAGMA` 迁移：旧库（无 source 列）建 Store → 自动补列且旧记录 source='web'

### test/test_feedback_dialog.py（新，纯逻辑）

不实例化 QDialog（CI 无显示环境跳过或用 QT_QPA_PLATFORM=offscreen）：

1. 服务器 URL 读写 config（临时目录）
2. multipart body 构造函数输出包含正确 boundary/字段名（抽纯函数 `build_multipart(fields, files) -> bytes`）
3. 本地校验函数 `validate_fields(...) -> (ok, msg)` 分支覆盖
4. offscreen 下 FeedbackDialog 创建/字段读写冒烟（Windows 本机可跑）

### 回归

- `test_web_feedback.py` 49 项（含部署脚本）不回归
- 真机冒烟：Web 服务跑起来 → curl 提交 → Web 主页 Tab 可见「桌面端」徽章 → GUI 对话框提交 → 数据库 2 条新记录
