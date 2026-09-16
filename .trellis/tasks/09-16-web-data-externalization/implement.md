# 实施计划：Web 运行时数据外置

前置：`prd.md`（R1~R6）、`design.md`（解析顺序/迁移契约/打包改动/测试点）。
顺序原则：**先建单一来源模块 → 再改消费方（保持可运行）→ 再改构建脚本与启动器 → 再迁移与文档 → 最后真实产物端到端验收**。

---

## 步骤 1 — `reflex_web/reflex_web/app_data.py`（新，纯 stdlib）

按 `design.md §1` 实现：`ENV_VAR` / `code_root()` / `is_frozen()` / `data_root()` / `feedback_dir()` / `uploads_dir()` / `downloads_dir()` / `admin_config_path()` / `ensure_dirs()` / `legacy_paths()` / `migrate_legacy()`。

要点：
- 冻结态判定 `hasattr(sys, "_MEIPASS") or getattr(sys, "frozen", False)`；exe 目录取 `Path(sys.executable).resolve().parent`（**不要**用 `_MEIPASS`）。
- `legacy_paths()` 返回旧的树内三元组（供迁移与测试）。
- `migrate_legacy()` 严格按 `design.md §3`：旧有/新无才搬、绝不覆盖、失败只告警不抛。
- 模块内**不** import `reflex_web` 其他模块，也不 import reflex。

**验收**：
```bash
python -c "import sys;sys.path.insert(0,'reflex_web');from reflex_web import app_data as a;print(a.data_root());print(a.feedback_dir(), a.downloads_dir(), a.admin_config_path())"
```
期望：默认（无 env、非冻结）指向 `<repo>/reflex_web/{data,downloads}` 与 `admin_config.json`（与现状一致）。

---

## 步骤 2 — 消费方改单一来源

- [ ] `feedback_model.py`：`data_dir()` → `app_data.feedback_dir()`；**删除** `FEEDBACK_DATA_DIR` 覆盖分支（模块 docstring 同步改）。
- [ ] `share_model.py`：`data_dir()` → `app_data.feedback_dir()`；**删除** `FRAMESHARE_DATA_DIR`（docstring 同步）。
- [ ] `reflex_web.py`：`_get_release_mgr()`、`_get_admin_cfg()`、`load_download_info()`（删掉两候选目录猜测）、`_get_fbimg_dir()` 四处改调 `app_data`。
- [ ] `run_app.py`：`main()` 起始处 `paths = app_data.resolve_paths()`；`ensure_dirs()`；`migrate_legacy()` 结果打印；启动日志打印数据根。把 `paths.downloads_dir` / `paths.uploads_dir` 传进两个中间件闭包（替换 `resource_dir / "downloads"` 与 `resource_dir / "data" / ...`）。
- [ ] 三个既有测试改 env：`test/test_web_feedback.py:33`、`test/test_feedback_api.py:25,240`、`test/test_frame_share.py:37` → `NW_WEB_DATA_DIR`（`test_feedback_api` 的「旧库迁移」用例改成切 `NW_WEB_DATA_DIR` 后 `FeedbackStore.reset()`，语义不变）。

**验收**：
```bash
PYTHONIOENCODING=utf-8 python test/test_web_feedback.py && python test/test_feedback_api.py && python test/test_frame_share.py
```
三条全绿；且 `git grep -n "FEEDBACK_DATA_DIR\|FRAMESHARE_DATA_DIR"` 无残留（除历史 CHANGELOG/AGENTS 记录）。

---

## 步骤 3 — 构建脚本与启动器

- [ ] 两个脚本：嵌套 `_ignore_web_only` → 模块级 `ignored_web_entries(src, names)`，忽略集加 `data`、`downloads`、`admin_config.json`、`nw_web_data`。
- [ ] 两个脚本：删除 `preserve_data_*`/`restore_data_*` 及其调用点/`data_backup`/「保留 data/」打印，`main()` 直接 `rmtree + mkdir` 重建。
- [ ] 两个脚本的 `write_launchers`：cmd/ps1/sh 三脚本注入 `NW_WEB_DATA_DIR`（**已设则不覆盖**，路径归一到部署目录的上一级 `nw_web_data`）；`部署说明.txt` 增「数据目录」段（位置/改法/备份）。
- [ ] 构建结束打印数据根默认位置。
- [ ] `reflex_web/.gitignore` 加 `nw_web_data/`（开发机若设了变量也不会误提交）。

**验收**：
```bash
python -c "import sys;sys.path.insert(0,'reflex_web');from reflex_web import build_offline_deploy as b, build_embedded_deploy as c;print(sorted(b.ignored_web_entries('x',['data','downloads','admin_config.json','keep.py'])))"
```
期望：`['admin_config.json','data','downloads']`（`keep.py` 不在内）；两个脚本结论一致。

---

## 步骤 4 — 测试

- [ ] 新增 `test/test_web_data_paths.py`（`design.md §7` 七类断言，含迁移、打包排除端到端、启动器模板）。
- [ ] `release_check.py:CORE_TESTS` 登记（放在 `test_web_landing.py` 之后）。

**验收**：`PYTHONIOENCODING=utf-8 python test/test_web_data_paths.py` 全绿（脚本式 `check()` 计数，FAIL=0）。

---

## 步骤 5 — 真实产物端到端验收（本任务核心）

1. `python reflex_web/build_offline_deploy.py --output <tmp>/reflex_web_offline`
2. 断言产物**不含** `reflex_web/data`、`reflex_web/downloads`、`reflex_web/admin_config.json`。
3. 用产物启动（`start_web.cmd` 等价：`.venv\Scripts\python.exe reflex_web\run_app.py --host 127.0.0.1 --port 8099`，env 由脚本注入）→ 起服务后
   - 断言数据根建在 `<tmp>/nw_web_data/`（`data/`、`downloads/` 存在）
   - `POST /api/feedback` 提交一条 → 断言写在 `<tmp>/nw_web_data/data/feedback.db`
4. **删掉整个部署目录** → 重新构建/拷贝一份新的到同路径 → 重启 → `GET` 反馈列表（页面或直接查库）**那条反馈仍在** ← 核心验收
5. `python release_check.py` 无 FAIL。

---

## 步骤 6 — 文档与版本

- [ ] `reflex_web/离线部署.md`：改写「反馈数据持久化」为「运行时数据目录」（默认位置 = 部署目录上一级 `nw_web_data`；`NW_WEB_DATA_DIR` 改法；备份=拷该目录；**升级硬要求**：先删旧目录的方式必须先把旧 `reflex_web/{data,downloads,admin_config.json}` 拷进 `nw_web_data/`）；两种部署 + exe 三种方式同步说明。
- [ ] `AGENTS.md`：§2（部署）、§3 架构树（`app_data.py` + `nw_web_data`）、§7（测试清单）、§8（新陷阱：运行时数据必须外置、构建必须排除、`_MEIPASS` 不可写）、§10 摘要。
- [ ] `main_gui.py:CHANGELOG` 新条目 + `APP_VERSION` bump（1.23.15）+ `README` 徽章 + `release_check.py --sync-iss`。

---

## 完成定义（DoD）

- R1~R6 全部满足；`prd.md` 的端到端验收（第 3~4 步）有真实输出证据。
- 两个构建脚本产物不含运行时数据；旧部署可自动或按文档手工迁移；迁移幂等且不覆盖。
- 新增测试 + 三个既有测试 + `release_check.py` 全绿。
- 文档里**不再出现**「重建时自动保留 data/」这类不成立的承诺。