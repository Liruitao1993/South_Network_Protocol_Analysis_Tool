# 技术设计 — Web版问题反馈页面

## 1. 总体架构

```text
reflex_web/
├── feedback_model.py            # 新增：FeedbackItem(rx.Model) + 存储层（单例 FeedbackStore）
├── reflex_web/
│   ├── reflex_web.py            # 修改：新增 FeedbackState + /feedback 与 /feedback-admin 页面
│   └── admin_release.py         # 复用 AdminConfig（口令验证），不改
├── build_embedded_deploy.py     # 修改：部署时保留 data/
├── build_offline_deploy.py      # 修改：部署时保留 data/
└── data/                        # 新增（运行时生成，进 .gitignore）
    ├── feedback.db              # SQLite 数据库
    └── uploads/feedback/        # 截图
```

## 2. 数据模型（feedback_model.py）

用 Reflex 自带 sqlmodel（`rx.Model`）：

```python
class FeedbackItem(rx.Model, table=True):  # noqa: D101
    created_at: str          # ISO 本地时间 "YYYY-MM-DD HH:MM:SS"
    issue_type: str          # 功能异常/解析错误/界面体验/新功能建议/其他
    protocol: str            # 协议名（含"不确定"）
    description: str         # ≤2000 字
    contact: str = ""        # ≤100 字，选填
    screenshots: str = ""    # 分号分隔的相对文件名列表 "fb_20260831_xxxx_1.png;..."
    status: str = "待处理"    # 待处理/已确认/已修复/已忽略
```

存储层 `FeedbackStore`（单例，懒加载）：

- `db_url()`：`sqlite:///data/feedback.db`，路径基于 `Path(__file__).resolve().parent / "data"`（即 `reflex_web/data/`，部署后在部署目录内，与 `downloads/`、`admin_config.json` 同级策略）。
- 显式 `sqlmodel.create_engine(db_url, connect_args={"check_same_thread": False})`——Reflex 多 worker 线程访问 SQLite 必需。
- 启动时 `sqlmodel.SQLModel.metadata.create_all(engine)`（幂等）。
- 方法（同步实现，Reflex 事件处理器里用 `with rx.session(engine)` 或直接 `sqlmodel.Session`）：
  - `add(item) -> id`
  - `list_all(offset, limit) -> (items, total)`
  - `count_pending() -> int`
  - `update_status(id, status)`
  - `delete(id) -> screenshots`（返回关联截图名，供 UI 层删文件）
- 截图文件工具函数（纯函数，便于测试）：
  - `save_screenshot(data: bytes, orig_name: str) -> str`：校验扩展名 {png,jpg,jpeg,webp} 与大小 ≤5MB；文件名重生成 `fb_YYYYmmdd_HHMMSS_<rand4>.<ext>`（**不使用用户原始文件名**，防路径穿越/重名），写入 `data/uploads/feedback/`
  - `delete_screenshots(names: list[str])`：仅允许删除 `uploads/feedback/` 内匹配 `fb_*` 模式的文件（二次防穿越）
- 魔数校验：png/jpeg/webp 文件头检查（`save_screenshot` 内），不匹配拒绝。

## 3. UI / State（reflex_web.py 内新增）

### 3.1 FeedbackState（独立 State 类，与主 State 并列）

```python
class FeedbackState(rx.State):
    # 提交表单
    fb_type: str = "功能异常"
    fb_protocol: str = "不确定"
    fb_desc: str = ""
    fb_contact: str = ""
    fb_upload_names: str = ""        # 已选截图展示
    _fb_pending_files: list[str] = []  # rx.upload_files 暂存名
    fb_msg: str = ""
    fb_msg_type: str = "info"
    # 管理页
    fa_logged: bool = False
    fa_password: str = ""
    fa_page: int = 0
    fa_items: list[dict] = []
    fa_total: int = 0
    fa_detail: dict = {}
    ...
```

关键事件处理器：

- `handle_screenshot_files(files)`：复用 `rx.get_upload_data`/`rx.upload_files` 模式（参考现有 `handle_batch_upload`），仅暂存文件名与计数，**提交时才真正读文件落盘**——Reflex upload 会把文件放到临时目录，`rx.get_uploaded_files` 可读字节。
- `submit_feedback()`：校验（desc 非空≤2000、contact≤100、截图数≤3）→ `save_screenshot` → `FeedbackStore.add` → 清空表单 + 成功提示。
- 管理页：`fa_login()`（复用 `AdminConfig.verify_password`）、`fa_load()`（分页列表）、`fa_open_detail()`、`fa_set_status()`、`fa_delete()`（先删记录再删文件）。

### 3.2 页面

- `/feedback`：卡片式表单。布局与其他页面一致（`page_container` 风格）。截图上传用 `rx.upload` + `rx.upload_files`；提交按钮 `on_click=FeedbackState.submit_feedback`。
- `/feedback-admin`：未登录显示口令输入卡；登录后显示列表（`rx.table` 或 vstack 行卡）+ 分页按钮 + 详情弹窗（`rx.dialog`，含截图 `<img>` 用 `/download/fb_xxx.png` 或专用路由）+ 状态下拉 + 删除按钮。
- 主页导航栏 `header()` 增加「问题反馈」链接（`rx.link("问题反馈", href="/feedback")`）；两个新页面共用同一 `header()` 组件（抽出参数化或直接复用）。

### 3.3 截图访问路由

管理页查看截图：**复用现有 `/download/` 路由不可行**（其仅服务 `downloads/` 目录且禁止子目录）。两个方案：

1. `run_app.py` 的 ASGI 中间件新增 `/fbimg/` 前缀 → 服务 `data/uploads/feedback/`（生产，目录 = `resource_dir / "data"`，与 downloads/ 同级定位方式）；
2. reflex_web.py 里用 dev 模式 Starlette 路由（`app.router`）服务同前缀（开发）。

采用方案：`run_app.py` 增加 `_serve_fbimg`（镜像 `_serve_download` 实现：防穿越、仅 `data/uploads/feedback/`、图片内联）；dev 路由同步添加（镜像 `_dev_download_handler`）。

## 4. 部署持久化改造（核心）

### 4.1 build_embedded_deploy.py

当前增量模式仅保留 `python/`；完整模式 `rmtree` 全部。改造：

- 引入 `PRESERVED_DIRS = ("python", "data")`（Linux 模式还有 `.venv`）。
- 增量模式：把 `python/` **和 `data/`** 一并 move 到临时目录，重建后移回。
- 完整模式：重建 out_dir 前，若 `data/` 存在也 move 出来重建后移回（完整重建同样不能丢反馈数据）。

### 4.2 build_offline_deploy.py

- 当前 `main()` 直接 `rmtree(out_dir)`。同样改为：rmtree 前 move `data/` 到 `out_dir.with_name(out_dir.name + ".datatmp")`，重建并 `copy_runtime_files` 后移回。
- `copy_runtime_files` 无需改动（`data/` 不在源码树复制范围内）。

### 4.3 运行时目录定位

`feedback_model.py` 中 data 目录 = `reflex_web/data/`（源码树内）。部署后结构为 `<部署目录>/reflex_web/data/`，与 `downloads/` 同级策略一致（`run_app.py` 中 `resource_dir` 即 `reflex_web/`）。`.gitignore` 追加：

```
reflex_web/data/
```

## 5. 安全要点

- 用户上传文件名完全不参与落盘路径（服务端重生成）。
- 扩展名白名单 + 魔数校验 + 大小限制（服务端）。
- `/fbimg/` 路由仅服务 `data/uploads/feedback/` 且 resolve 后必须仍在该目录内。
- 反馈管理页口令复用 AdminConfig（与发布管理同一口令体系）。
- 描述/联系方式纯文本渲染（Reflex 默认转义，无 XSS 注入面）。

## 6. 兼容与回滚

- 不改动任何现有解析/发布逻辑；新增 State 与页面为纯增量。
- 数据库文件是普通 SQLite，可随时备份/迁移；部署回滚 = 恢复旧源码目录 + data/ 保留不动。
- Reflex 0.9.8 的 rx.Model/SQLModel 迁移：仅用 `create_all`（自动建缺失表），不用 alembic 迁移链——避免 Reflex CLI 迁移复杂度。

## 7. 测试设计（test/test_web_feedback.py）

不依赖 Reflex 运行时（Windows 侧 python.exe 无需 GUI），纯逻辑测试：

1. `save_screenshot` 正常保存 png 魔数 → 文件存在、名字匹配 fb_* 模式
2. 非法扩展名 / 非法魔数 / 超大文件 → 拒绝并报错
3. `delete_screenshots` 防穿越：传入 `../feedback.db` → 拒绝删除
4. FeedbackStore CRUD：临时目录建库 → add/list/update_status/delete 往返
5. 部署脚本：`_preserve_data_dirs` 抽出的纯函数 —— 临时目录模拟 out_dir 旧 data/ + 新建 → 验证 data 保留
6. （可选）`import reflex_web.reflex_web` 编译级验证（不渲染）——跳过，因导入会拉起全部解析器依赖，已有其他测试覆盖
