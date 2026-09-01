# 实施计划 — GUI客户端问题反馈接入Web服务

## 执行顺序

> 前置：规划审查 → `task.py start` 后实施。

### Step 1: feedback_model.py 扩展（source 列 + API 纯函数）

- [ ] `FeedbackItem` 加 `source: str = "web"` 列
- [ ] `FeedbackStore.__init__`：create_all 后 PRAGMA 检查缺列则 `ALTER TABLE ... ADD COLUMN source VARCHAR DEFAULT 'web'`（旧库迁移）
- [ ] `fa_load`（reflex_web.py）/API 列表输出补 `source` 字段
- [ ] 新增纯函数 `submit_from_api(fields, files) -> (ok, id_or_error, http_status)`：
  校验（issue_type 白名单/desc 长度/contact 长度/协议非空/截图数）→ save_screenshot → add(source="gui")
- [ ] 新增 `_parse_multipart(body: bytes, boundary: bytes) -> (fields: dict, files: list[tuple[str, bytes, str]])` 纯函数（生产中间件用，二进制安全解析，单测覆盖）
- [ ] reflex_web.py：Web 页面 submit_feedback 构造 FeedbackItem 补 `source="web"`；列表行 dict 加 source
- 验证：`PYTHONUTF8=1 python.exe -c "import reflex_web.reflex_web.feedback_model"`（旧库打开自动迁移）

### Step 2: Web 服务端 API 路由

- [ ] reflex_web.py 尾部：Starlette Route `POST /api/feedback`（request.form() 解析）+ `GET /api/feedback/config` + OPTIONS 204；响应带 CORS 头
- [ ] run_app.py：`env_rewrite_middleware` 加 `/api/feedback` 分支 → `_handle_feedback_api`（手工 multipart 解析用 `_parse_multipart`）；同样 OPTIONS/CORS
- [ ] 频率限制：路由层 `_FEEDBACK_RATE: dict[str, list[float]]`，滑动窗口 60s/5 条，超限 429
- 验证：curl -F 提交 → ok:true 且数据库 source=gui；curl 参数错 → 400

### Step 3: Web 主页桌面端标识

- [ ] `fa_load` items 加 "source"；`_fa_item_row` 在 source=="gui" 时渲染 `rx.badge("桌面端", color_scheme="cyan")`
- 验证：渲染冒烟 + curl 提交后浏览器可见徽章

### Step 4: GUI feedback_dialog.py（新文件，项目根）

- [ ] 模块级常量：ISSUE_TYPES/PROTOCOL_OPTIONS/限制（与 Web 对齐，不 import web 包）
- [ ] `load_feedback_server_url(config_path) -> str` / `save_feedback_server_url(...)` 纯函数（config.json "feedback" 段）
- [ ] `validate_fields(issue_type, desc, contact, shots) -> (ok, msg)` 纯函数
- [ ] `build_multipart_parts(fields, shots) -> QHttpMultiPart`（或拆纯函数生成 body 供测试）
- [ ] `FeedbackDialog(QDialog)`：布局按 design.md；QNetworkAccessManager 异步提交；超时 15s；成功 QMessageBox+accept；失败红字提示；服务器地址行内修改（QInputDialog）并持久化
- [ ] 主 GUI：帮助菜单「问题反馈(&F)...」→ `_show_feedback_dialog`（懒 import）
- 验证：offscreen 创建冒烟；真机提交到本机 dev 服务

### Step 5: 测试

- [ ] `test/test_feedback_api.py`（文件头 `import _path_setup  # noqa: E402`）：
  submit_from_api 正常/参数错/截图校验；_parse_multipart 往返；频率限制；旧库迁移
- [ ] `test/test_feedback_dialog.py`：URL 读写、validate_fields 分支、multipart 构造；offscreen 对话框冒烟
- [ ] 回归：`test_web_feedback.py`（49 项）、`test_web_frame_gen_utils.py`（63 项）
- [ ] 真机冒烟：dev 服务 + curl + GUI 对话框提交 → 同库可见
- 验证命令：`PYTHONUTF8=1 python.exe test/test_feedback_api.py`、`PYTHONUTF8=1 python.exe test/test_feedback_dialog.py`

### Step 6: 收尾

- [ ] 文档：AGENTS.md（§3 架构树 feedback_dialog.py + API 端点、§7 测试清单）、README、main_gui.py CHANGELOG（新版本条目）
- [ ] Web 服务重启验证生产链路（run_app.py 中间件分支）
- [ ] `trellis-check` → commit（含本会话此前未提交的反馈模块修复批次，分两个 commit：fix 批次 + 本任务 feat）

## 验证命令汇总

```bash
PYTHONUTF8=1 python.exe test/test_feedback_api.py
PYTHONUTF8=1 python.exe test/test_feedback_dialog.py
PYTHONUTF8=1 python.exe test/test_web_feedback.py
curl -F "issue_type=功能异常" -F "protocol=南网协议" -F "description=api测试" http://127.0.0.1:8000/api/feedback
```

## 回滚点

- Step 1（模型迁移）向后兼容（只加列不破坏）；异常时 git checkout 还原即可。
- Step 2/3/4 各自独立成 commit，可单独回滚。
