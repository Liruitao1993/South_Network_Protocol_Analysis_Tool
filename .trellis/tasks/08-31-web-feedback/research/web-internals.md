# 研究笔记 — Web 版内部机制（本任务相关结论）

> 调查时间：2026-08-31。来源：实际代码审查（reflex_web.py 7640 行 / run_app.py / 两个部署脚本）。

## 1. reflex_web.py 现状

- 单文件 Reflex 0.9.8 应用，7640 行。`app.add_page(index, route="/")` 仅一个页面（L7565）。
- 主题：light / blue / slate。
- `State(rx.State)` 是全局主状态（L29 起）。
- 管理员口令：`AdminConfig`（admin_release.py），懒加载单例 `_get_admin_cfg()`（L2847 附近），`config_dir = here.parent.parent`（即 reflex_web/ 包的上级 = reflex_web/ 目录），读 `admin_config.json`。登录事件 L2935 `admin_login()`，用 `cfg.verify_password(pwd)`。默认密码 admin123。
- 文件上传模式（L657 `handle_batch_upload`）：`rx.Upload` 的 `on_drop` → `files: List[rx.UploadFile]` → `await f.read()`。上传直接可读字节，**无需落临时目录再读**（与设计稿假设不同——可直接在读到字节后立即保存）。
- dev 下载路由：`_dev_download_handler`（L7585 附近）经 `app.router` 挂 Starlette 路由 `/download/{path}`，服务 `reflex_web/downloads/`。生产由 `run_app.py` ASGI 中间件 `_serve_download`（L199）实现：防穿越（禁 `..` `/` `\`）、resolve 校验、图片 inline。

## 2. 部署脚本现状

### build_embedded_deploy.py

- `main()`（L333）：
  - `--skip-deps` 增量模式：仅当 `out_dir/python/` 存在时，把 `python/` move 到 `out_dir.with_name(name+".pytmp")` → `rmtree(out_dir)` → 重建 → move 回（L375-389）。
  - 完整模式：直接 `rmtree(out_dir)`。
  - 之后 `copy_runtime_files(out_dir)`（L147）：复制根目录 *.py/*.json、validator/、reflex_web/（ignore 掉 build/dist/uploaded_files/tests 等）。
- **结论**：`data/` 需要加入保留逻辑（与 python/ 同待遇）；`copy_runtime_files` 复制 reflex_web/ 时 ignore 集合不含 data/，但源码树 data/ 一般不存在（gitignore），不会误复制。安全起见在 `_ignore_web_only` 里也无需要动——保留逻辑在 out_dir 层面即可。

### build_offline_deploy.py

- `main()`（L221）：`if out_dir.exists(): shutil.rmtree(out_dir)`（L241-242），然后 copy_runtime_files + venv。
- **结论**：rmtree 前 move data/，重建后移回。

## 3. run_app.py

- `resource_dir` = reflex_web/ 目录（`_get_resource_dir`）。
- `env_rewrite_middleware`（L262）按 path 前缀分发：`/download/`、`/api/download/` → `_serve_download`。新增 `/fbimg/` 前缀分支 → `_serve_fbimg`（镜像实现，目录改为 `resource_dir/"reflex_web"/"data"/"uploads"/"feedback"`——注意生产部署时 reflex_web.py 位于 `<部署>/reflex_web/reflex_web/`，resource_dir 是 `<部署>/reflex_web/`）。
  - 核对：run_app.py L200 注释 "downloads 目录: reflex_web/downloads/（resource_dir 是 reflex_web/）"。所以 data 目录 = `resource_dir / "reflex_web" / "data"`？不对——downloads 在源码树是 `reflex_web/downloads/`（包外层），部署后同样位于 `<部署>/reflex_web/downloads/`。而我们的 data 按设计在 `reflex_web/data/`（包外层，与 downloads 同级）。feedback_model.py 里 `Path(__file__).parent / "data"`：`__file__` 是 `reflex_web/feedback_model.py`（包外层文件），parent = `reflex_web/`，所以 data = `reflex_web/data/`。run_app.py 中等价 `resource_dir / "data"`。**修正 design.md 的描述**：`resource_dir / "data"` 而非 `resource_dir / "reflex_web" / "data"`。

## 4. 依赖

- Reflex 0.9.8 自带 sqlmodel（rx.Model 底层）。requirements.in 无需新增。
- SQLite 引擎必须 `connect_args={"check_same_thread": False}`（Reflex 后端多线程事件处理）。

## 5. 测试环境

- Windows 侧 `python.exe`（3.13.0）已装 reflex → 可直接 import feedback_model 跑纯逻辑测试（不经 GUI）。
- 输出用 ASCII OK/FAIL，避免 GBK 控制台问题。
