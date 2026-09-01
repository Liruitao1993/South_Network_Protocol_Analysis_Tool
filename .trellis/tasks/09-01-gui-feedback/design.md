# 设计：GUI 问题反馈（HTTP API 共享 Web 数据库）

## 1. 总体架构

```
GUI 客户端 (PySide6, main_gui.py)
  帮助菜单「问题反馈」
    └─ gui_widgets/feedback_dialog.py: FeedbackDialog
         ├─ 表单：类型/协议/描述/联系方式/截图×≤3
         ├─ 自动环境信息（APP_VERSION/OS/Python/机器名/协议）
         └─ FeedbackSubmitWorker(QThread)
              └─ urllib.request POST  JSON(base64 截图)
                   │  http://<server_url>/api/feedback/submit
                   ▼
Reflex Web 服务器
  ├─ 开发模式: reflex_web/reflex_web/reflex_web.py 末尾 Starlette Route
  └─ 生产模式: reflex_web/run_app.py ASGI 中间件 path 分支
        └─ reflex_web/reflex_web/feedback_api.py（新建，纯逻辑）
             ├─ handle_ping() -> (200, {"ok": True, ...})
             └─ handle_submit(payload: dict) -> (status:int, body:dict)
                  └─ feedback_model.save_screenshot() + FeedbackStore.add()
                       └─ reflex_web/data/feedback.db + data/uploads/feedback/
                            ▲
Web 反馈列表 /feedback、/feedback-admin（既有，刷新即见新记录）
```

## 2. 服务端设计

### 2.1 数据模型扩展（`feedback_model.py`）

`FeedbackItem` 新增两列：

```python
app_version: str = ""   # 客户端版本（GUI 提交时有值，Web 表单提交为空/"web"）
sys_info: str = ""      # 客户端环境信息（OS/Python/机器名等，长文本）
```

**轻量迁移**（既有部署的 feedback.db 已建表，`create_all` 不会自动加列）：
`FeedbackStore.__init__` 在 `create_all` 后执行 `_ensure_columns(engine)`：
`PRAGMA table_info(feedbackitem)` 检查缺列 → `ALTER TABLE feedbackitem ADD COLUMN app_version VARCHAR DEFAULT ''`（SQLite 支持 ADD COLUMN，幂等）。表名按 SQLModel 规则为类名小写 `feedbackitem`（测试中验证实际表名，不匹配则按 metadata.tables 取）。

### 2.2 新模块 `reflex_web/reflex_web/feedback_api.py`

纯 stdlib + feedback_model，**不 import reflex/starlette**（dev/prod 两处路由共用、可单测）：

```python
MAX_SYSINFO_LEN = 2000

def handle_ping() -> tuple[int, dict]:
    return 200, {"ok": True, "service": "feedback-api", "version": 1}

def handle_submit(payload: dict) -> tuple[int, dict]:
    """返回 (HTTP status, response body dict)。
    - 400: 校验失败（body {"ok": False, "error": "中文原因"}）
    - 200: 成功（body {"ok": True, "id": int, "screenshots": [服务端文件名]}）
    - 500: 服务端异常（body {"ok": False, "error": ...}）
    """
```

处理流程：

1. payload 类型检查（dict），字段取值 + 类型校验（str）。
2. `issue_type` 必填且 ∈ `ISSUE_TYPES`；`description` 必填 strip 非空且 ≤ MAX_DESC_LEN；`contact` ≤ MAX_CONTACT_LEN；`sys_info` ≤ MAX_SYSINFO_LEN 截断或拒绝（拒绝，提示超长）。
3. screenshots：须为 list，长度 ≤ MAX_SCREENSHOTS；每项 dict 含 `name`(str)、`data_base64`(str)；`base64.b64decode(validate=True)` 解码 → `save_screenshot(data, name)`（复用魔数/扩展名/5MB 校验，扩展名从 name 取，非法名默认 .png？——不：name 无合法扩展名直接 400）。
4. 任何截图失败：`delete_screenshots(已保存)` 回滚 + 400。
5. 构造 `FeedbackItem(created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), issue_type, protocol, description, contact, screenshots=";".join(names), status="待处理", app_version, sys_info)` → `FeedbackStore.instance().add(item)`。
6. 写库异常：删截图回滚 + 500。

### 2.3 路由接线

- **开发模式**（`reflex_web/reflex_web/reflex_web.py` 文件末尾，与现有 `_dev_fbimg_handler` 同模式）：

```python
async def _dev_feedback_submit_handler(request):
    from starlette.responses import JSONResponse
    from .feedback_api import handle_submit
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "请求体不是合法 JSON"}, status_code=400)
    status, body = handle_submit(payload if isinstance(payload, dict) else {})
    return JSONResponse(body, status_code=status)

async def _dev_feedback_ping_handler(request):
    from .feedback_api import handle_ping
    status, body = handle_ping()
    return JSONResponse(body, status_code=status)

app._api.routes.insert(0, Route("/api/feedback/submit", _dev_feedback_submit_handler, methods=["POST"]))
app._api.routes.insert(0, Route("/api/feedback/ping", _dev_feedback_ping_handler, methods=["GET"]))
```

- **生产模式**（`reflex_web/run_app.py` ASGI 中间件 `env_rewrite_middleware` 内，http 分支、download/fbimg 路由旁）：

```python
if path == "/api/feedback/submit" and scope.get("method") == "POST":
    return await _serve_feedback_submit(scope, receive, send)
if path == "/api/feedback/ping" and scope.get("method") == "GET":
    return await _serve_feedback_ping(scope, receive, send)
```

`_serve_feedback_submit`：循环 `await receive()` 收集 body bytes → `json.loads` → `from reflex_web.feedback_api import handle_submit`（注意 run_app.py 已把 resource_dir 加入 sys.path，import 路径 `reflex_web.feedback_api` 或 `from reflex_web import feedback_api`，与既有 `from reflex_web.reflex_web import app` 一致用 `reflex_web.feedback_api`）→ 用 `_send_json(send, status, body)` 辅助发 JSON 响应（content-type application/json; charset=utf-8）。
注意：生产中间件中这些 path 必须在 env.js rewrite 包装逻辑**之前**直接 return，避免响应被重写包装。

### 2.4 Web 详情展示（小改）

`feedback_admin_page` 详情弹窗中，当 `fa_detail["app_version"]` 非空时显示「客户端版本」行；`sys_info` 非空时加可折叠/只读多行文本展示环境信息。Web 表单提交的记录这两字段为空，不显示。

## 3. GUI 客户端设计

### 3.1 新文件 `gui_widgets/feedback_dialog.py`

**环境信息收集**（纯函数，便于测试）：

```python
def collect_sys_info(app_version: str, build_date: str, protocol_name: str) -> str:
    import platform, getpass, sys as _sys
    lines = [
        f"软件版本: {app_version} ({build_date})",
        f"操作系统: {platform.platform()}",
        f"Python: {_sys.version.split()[0]}",
        f"机器名: {platform.node()}",
        f"用户: {getpass.getuser()}",
        f"当前协议: {protocol_name}",
    ]
    return "\n".join(lines)
```

**配置读写**（复用 main_gui 传入的 config 路径，或 dialog 内部用 `app_paths.data_path("config.json")`）：

```python
def load_feedback_config() -> dict:
    """config.json 的 "feedback" 段：{"server_url": "http://ip:8080", "timeout": 15}"""
def save_feedback_config(cfg: dict) -> None
```

**网络层**（纯函数，便于 mock 测试）：

```python
class FeedbackSubmitError(Exception): ...

def submit_feedback(server_url: str, payload: dict, timeout: float = 15) -> dict:
    """POST {server_url}/api/feedback/submit，JSON。
    - URLError(含 socket.timeout) → FeedbackSubmitError("无法连接服务器..."/"提交超时...")
    - HTTP 4xx/5xx → 读 body error 字段 → FeedbackSubmitError("服务器拒绝：<原因>")
    - 成功返回 body dict（含 id）。
    """

def ping_server(server_url: str, timeout: float = 5) -> dict:
    """GET {server_url}/api/feedback/ping，失败抛 FeedbackSubmitError。"""
```

**截图持有**：dialog 内部维护 `self._shots: list[tuple[str, bytes]]`（原始文件名 + PNG 字节）。

- 粘贴：`QApplication.clipboard().image()` → 非空则 `QBuffer` 存 PNG 字节，名 `clipboard_<n>.png`。
- 文件：`QFileDialog.getOpenFileName` 过滤 `图片 (*.png *.jpg *.jpeg *.webp)`，读字节。
- 客户端侧预检：扩展名 + 魔数（复用简单 PNG/JPEG/WEBP 头判断）+ 5MB 上限 + ≤3 张，不合格弹提示不添加。
- 缩略图：QListWidget 带 QIcon(QPixmap)，每项右键/选中后「移除选中」按钮。

**payload 组装**（纯函数 `build_payload(...)` 便于测试）：

```python
{
  "issue_type": ..., "protocol": ..., "description": ..., "contact": ...,
  "app_version": APP_VERSION, "sys_info": collect_sys_info(...),
  "screenshots": [{"name": n, "content_type": "image/png",
                   "data_base64": base64.b64encode(b).decode("ascii")} ...],
}
```

**QThread worker**：

```python
class _SubmitWorker(QThread):
    finished_ok = Signal(dict)      # 成功 body
    failed = Signal(str)           # 中文错误
    def __init__(self, server_url, payload, timeout): ...
    def run(self):
        try: self.finished_ok.emit(submit_feedback(...))
        except FeedbackSubmitError as e: self.failed.emit(str(e))
        except Exception as e: self.failed.emit(f"未知错误: {e}")
```

对话框提交流程：前端校验（描述非空、地址非空）→ 按钮置灰 + 「提交中...」→ worker 信号：

- 成功：QMessageBox 提示「反馈提交成功（编号 #id）」→ 询问是否打开 Web 反馈页（`QDesktopServices.openUrl(f"{server_url}/feedback")`）→ accept()。
- 失败：QMessageBox warning，**表单保留**，按钮恢复。

**测试连接**按钮：`ping_server` 在小 QThread 或直接短超时同步调用（5s，可接受点按后短暂等待；用 QApplication.setOverrideCursor 等待），成功/失败弹提示。

### 3.2 `main_gui.py` 集成

- import：`from gui_widgets.feedback_dialog import FeedbackDialog`（顶部 import 区）。
- 帮助菜单（约 L5653 `help_menu` 处）：

```python
feedback_act = help_menu.addAction("问题反馈(&F)...")
feedback_act.triggered.connect(self._show_feedback_dialog)
```

- 新方法：

```python
def _show_feedback_dialog(self):
    dlg = FeedbackDialog(
        parent=self,
        app_version=APP_VERSION,
        build_date=BUILD_DATE,
        protocol_name=self.protocol_combo.currentText(),
    )
    dlg.exec()
```

### 3.3 打包

`南网协议解析工具.spec`：`gui_widgets/feedback_dialog.py` 位于已收集的包目录（gui_widgets/ 已被其他组件引用，hiddenimports 通常自动）。检查 spec 的 hiddenimports 是否显式列了 gui_widgets 模块；若列了需补 feedback_dialog。纯 stdlib 网络（urllib/json/base64），无新依赖。

## 4. 测试设计

### `test/test_feedback_api.py`（服务端纯逻辑，Windows python.exe 跑，需 crcmod? 不——feedback_model import reflex；reflex 在 Windows 侧是否安装？Web 依赖 reflex，Windows 主环境未必装

**检查点**：feedback_model.py 顶层 `import reflex as rx` + `import sqlmodel`。测试若直接 import feedback_api → feedback_model 需要 reflex/sqlmodel 环境。test_web_feedback.py 已存在且 1.19.0 起运行——说明 Windows python.exe 环境装了 reflex/sqlmodel（AGENTS.md 测试列表里有 test_web_feedback.py）。沿用同环境。

- `FEEDBACK_DATA_DIR` 重定向到 tmp_path；`FeedbackStore.reset()`。
- 用例：
  1. handle_ping 返回 200/ok。
  2. 无图提交成功 → 200，body 有 id；list_all 能查到且字段一致、app_version/sys_info 落库。
  3. 带 1 张 PNG（base64，魔数正确）→ 200，uploads 目录有文件，screenshots 字段非空。
  4. issue_type 非法 / 描述空 / 描述超长 / contact 超长 / sys_info 超长 → 各 400 且中文 error。
  5. 截图非图片魔数 / 扩展名非法 / 超 5MB / 第 4 张 → 400，库中无记录、uploads 无残留文件（回滚）。
  6. payload 非 dict / screenshots 项非 dict / base64 非法 → 400。

### `test/test_feedback_dialog.py`（Qt offscreen，QT_QPA_PLATFORM=offscreen）

- collect_sys_info 含版本/协议关键字段。
- load/save_feedback_config 往返（临时 config 路径，用 app_paths 或 monkeypatch）。
- build_payload：字段映射正确、截图 base64 可解码回原字节、≤3 张。
- 对话框：描述为空点提交被拦截（worker 不启动）；server_url 为空被拦截；添加截图（用 QImage 生成 PNG 字节走内部 add 方法）后缩略图列表计数 +1、移除后归零；第 4 张被拒。
- submit_feedback 网络层：mock（monkeypatch urllib.request.urlopen）成功路径返回 dict；构造 URLError → 中文错误含「无法连接」；HTTPError 400 带 body error → 中文含「服务器拒绝」。
- 不发真实网络请求。

## 5. 风险与注意

- **ALTER TABLE 迁移**：SQLite ADD COLUMN 不能加 NOT NULL 无默认值的列；新列均有默认值 ""，安全。迁移函数需幂等、表名以实际 SQLModel metadata 为准。
- **run_app.py import 路径**：生产模式 cwd 与 sys.path 已切到 resource_dir（reflex_web/），`from reflex_web.feedback_api import handle_submit` 可行（与 `from reflex_web.reflex_web import app` 同构）。
- **ASGI body 读取**：必须循环 receive 直到 more_body=False；响应 JSON 需自行发 http.response.start/body（参考_send_download_error）。
- **中文字段**：JSON 一律 ensure_ascii=False + UTF-8；GUI 侧 `json.dumps(payload, ensure_ascii=False).encode("utf-8")`，Content-Type 带 charset。
- **server_url 规范化**：用户可能漏 http:// 前缀或尾部多 /，客户端拼接前 `url.rstrip("/")`，缺 scheme 时补 `http://`。
- **线程退出**：_SubmitWorker 随对话框生命周期，对话框关闭时若线程仍在跑，不阻塞退出（daemon QThread + 请求超时兜底）；参考既有 thread_registry 约定（陷阱 20b）——worker 需 `thread_registry.track` 或确保对话框关闭时 wait 短超时。简单起见：对话框 reject/accept 时若 worker 仍运行，`wait(500)` 后放行（urllib 有超时不会永久挂）。
- **版本号**：bump 到 1.20.0（新功能），CHANGELOG 头部新增条目。
