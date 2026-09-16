# Web 运行时数据外置（反馈/分享库、downloads、admin_config 移出代码目录）

## Goal

Reflex Web 版的**运行时可写数据**当前全部写在代码目录内部（`<部署>/reflex_web/`）。升级 = 替换该目录 ⇒ 库、截图、已发布 exe、管理员口令全部可能消失；更糟的是构建脚本不排除运行时数据，会把**构建机的开发库**打进部署包，覆盖式升级时用开发数据顶掉服务器生产数据。本任务把运行时数据外置到部署目录之外，并修掉打包与「数据保留」逻辑两处缺陷。

## Confirmed Facts（代码证据，2026-09-16）

**运行时数据位置（全在代码目录内）**

| 状态 | 位置 | 依据 |
|---|---|---|
| 反馈库 + 截图 | `<部署>/reflex_web/data/{feedback.db,uploads/feedback/}` | `feedback_model.py:54-72` `data_dir() = Path(__file__).parent.parent/"data"` |
| 分享库 | `<部署>/reflex_web/data/frameshare.db` | `share_model.py:54-68`（同构） |
| 发布管理上传的 exe / version.json / archive | `<部署>/reflex_web/downloads/` | `run_app.py:219`、`reflex_web.py::load_download_info` |
| 管理员口令哈希 | `<部署>/reflex_web/admin_config.json` | `reflex_web.py::_get_admin_cfg`（取「含 downloads 的那层」） |

`run_app.py:20-26` `resource_dir = run_app.py 所在目录`（打包态为 `sys._MEIPASS`），与上表一致；`run_app.py:296` 的 `/fbimg` 中间件用 `resource_dir/"data"/"uploads"/"feedback"`，`:219` 的 `/download` 中间件用 `resource_dir/"downloads"`。

**缺陷 A：打包会把构建机的运行时数据一起装进产物**
- `build_offline_deploy.py:124-164` 与 `build_embedded_deploy.py:196-233` 均 `shutil.copytree(REFLEX_WEB, out_dir/"reflex_web", ignore=_ignore_web_only)`；`_BASE_IGNORE = {__pycache__, .states, .tests, tests, reflex.lock, uploaded_files}`（+ `.spec`/`.pyc`，顶层另加 `build`/`dist`）——**不含 `data`、`downloads`、`admin_config.json`**。
- `reflex_web/.gitignore` 只挡 git（`*.db`、`admin_config.json`、`downloads/*.exe`、`downloads/version.json`），对 copytree 无效。
- 本机 `reflex_web/data/`（`feedback.db`、`frameshare.db`、`uploads/`）与 `downloads/南网协议解析工具1.14.13.exe`（98.7MB）+`version.json` 实际存在 → 会原样进包。

**缺陷 B：「重建时保留 data/」路径写错，且只保护构建机**
- `build_offline_deploy.py:240-268`（`preserve_data_dir`/`restore_data_dir`）与 `build_embedded_deploy.py:162-194`（`preserve_data_dirs`/`restore_data_dirs`）搬移的是 `<out_dir>/data`，而运行时真实数据目录是 `<out_dir>/reflex_web/data` ⇒ 该保护**零作用**。
- `离线部署.md:63-76`「重新构建部署目录都会自动保留 data/，用户已提交的反馈不会丢失」+ 两个脚本打印的「保留 data/」是**错误的安全感**。

**缺陷 C：单文件 exe 模式更彻底**
- `reflex_web_exe.spec:214-234`：`EXE(pyz, a.scripts, a.binaries, a.datas, [], name=…)` 无 `COLLECT` 段 ⇒ **onefile**，`_MEIPASS` 每次启动解到临时目录、退出即删；而 `run_app.py:20-26` 打包态把 `resource_dir` 取成 `_MEIPASS` ⇒ 反馈库/分享库/downloads/口令全写在临时目录，**每次重启清零**。

**升级流程的致命顺序问题（本任务必须一并解决）**
- 若运维「先删旧目录再拷新包」（最常见的升级方式），旧树里的 `reflex_web/data` 会在**新程序启动前**就被删除 ⇒ 任何「启动时自动迁移」都来不及。因此数据根**必须在部署目录之外**，而不是部署目录内的 `nw_web_data/`。

**其他相关事实**
- 现有测试专用覆盖变量：`FEEDBACK_DATA_DIR`（`feedback_model.py:60`，被 `test/test_web_feedback.py:33`、`test/test_feedback_api.py:25,240` 使用）、`FRAMESHARE_DATA_DIR`（`share_model.py:60`，被 `test/test_frame_share.py:37` 使用）。
- `run_app.py` 模块级只有 docstring + `if __name__ == "__main__"` ⇒ **可被测试 import**（`_get_resource_dir`/`_setup_frontend_static`/`main` 三个函数，中间件是 `main()` 内的闭包）。
- 两个构建脚本的启动器模板：`build_offline_deploy.py:197-237`、`build_embedded_deploy.py:360-409`（cmd/ps1/sh 三种 + 部署说明）。
- `load_download_info` 当前用「`here.parent.parent/downloads` 否则 `here.parent/downloads`」两候选目录猜测（`reflex_web.py:3167-3170`）——外置后应改为单一来源。

## Requirements

### R1 统一数据根（单一来源）
- 新增纯逻辑模块 `reflex_web/reflex_web/app_data.py`（无 Qt/无 reflex）：解析顺序
  1. 环境变量 **`NW_WEB_DATA_DIR`**（运维可指向任意路径，如 `D:\nw_web_data`）；
  2. 冻结态（PyInstaller：`sys._MEIPASS`/`sys.frozen`）→ **exe 同级** `nw_web_data/`（`Path(sys.executable).parent`）；
  3. 其他（开发/未设变量）→ **维持现状**（`<repo>/reflex_web/{data,downloads}` + `admin_config.json`），开发者零感知。
- 数据根下的布局与现状同形：`data/`（含 `uploads/feedback/`）、`downloads/`、`admin_config.json`。
- 提供 `data_root()/feedback_dir()/downloads_dir()/admin_config_path()/uploads_dir()/ensure_dirs()/resolve_paths()/legacy_paths()/migrate_legacy()`。
- **所有**读写方改为消费该模块：`feedback_model`、`share_model`、`reflex_web.py`（发布管理/下载页/反馈截图目录）、`run_app.py`（`/download`、`/fbimg` 与启动期）。
- 删除 `FEEDBACK_DATA_DIR`/`FRAMESHARE_DATA_DIR` 两个测试专用变量（收敂为 `NW_WEB_DATA_DIR`），三个既有测试同步改。

### R2 数据根放在部署目录之外
- 两个构建脚本生成的启动脚本（`start_web.cmd` / `start_web.ps1` / `start_web.sh`）**默认注入** `NW_WEB_DATA_DIR=<部署目录的上一级>/nw_web_data`，且**若运维已自行设置则不覆盖**（允许把数据指到别的盘）。
- 部署说明（脚本生成 + `离线部署.md`）写清：数据目录位置、如何改到别处（`set NW_WEB_DATA_DIR=...`）、备份=拷该目录。

### R3 一次性迁移（兼容已部署的在树内数据）
- 启动时（`run_app.py`）若「数据根 ≠ 旧位置」且**旧位置有数据**而**新位置没有** → 把 `data/`、`downloads/`、`admin_config.json` 搬到新根（`shutil.move`，跨盘自动退化为复制），并打印迁移清单。
- 幂等：新位置已有同名项则**不覆盖**，只提示。
- 失败不阻断启动，但必须打印醒目告警（含新旧路径与手工搬迁命令）。
- 文档必须写明：**「先删旧目录再拷新包」的升级方式下，必须在删除前手工把旧 `reflex_web/{data,downloads,admin_config.json}` 拷到 `nw_web_data/`**（自动迁移只能在旧树尚存时生效）。

### R4 打包排除运行时数据（缺陷 A）
- 两个构建脚本的忽略列表加入 `data`、`downloads`、`admin_config.json`（以及 `nw_web_data`），确保产物**不含**开发机数据；忽略判定函数提取为模块级可测函数。
- 删除因此失效的 `preserve_data_*`/`restore_data_*`（缺陷 B 的死逻辑）与其调用点、以及「保留 data/」的错误打印（`离线部署.md` 的对应承诺同步改写）。

### R5 exe 模式持久化（缺陷 C）
- 冻结态数据根 = exe 同级 `nw_web_data/`，不再落 `_MEIPASS`；`reflex_web_exe.spec` 无需改（用 exe 同级目录即可），但需在打包说明/文档中注明「exe 与 `nw_web_data/` 同级；升级只换 exe」。

### R6 测试与验收
- 新增 `test/test_web_data_paths.py`：解析矩阵（env/冻结/默认）、三处消费方同一来源、`ensure_dirs`、迁移（幂等/不覆盖/失败告警）、两个构建脚本忽略运行时数据（含小树 copytree 端到端）、启动器模板含 `NW_WEB_DATA_DIR` 且不覆盖既有值；登记 `release_check.py:CORE_TESTS`。
- 既有 `test_web_feedback.py`、`test_feedback_api.py`、`test_frame_share.py` 改用 `NW_WEB_DATA_DIR` 后仍全绿。
- **端到端验收（真实部署目录模拟）**：`python reflex_web/build_offline_deploy.py --output <tmp>` 产出的目录里 **不含** `reflex_web/data`、`reflex_web/downloads`、`reflex_web/admin_config.json`；用该启动脚本跑起来后，写入一条反馈 → 数据落在 `<部署上级>/nw_web_data/data/feedback.db`；**删掉整个部署目录再拷一份新的** → 重启后那条反馈仍在（这是本任务的核心验收）。

## Out of Scope

- 桌面 GUI 客户端自身的数据路径（`app_paths.py` 已按 exe 目录/项目根处理，与本任务无关）。
- 把数据迁到数据库服务/集中存储、多实例共享同一数据根（SQLite 单写者，多实例并发不在本任务范围）。
- Reflex 自身的工作目录（`.web`、`.states`）——可再生，不入数据根。
- 打包 exe 后分发 `downloads/` 里的客户端 exe（属发布管理运行时行为）。

## 人工事项（需用户确认/执行）

1. **已有在线部署的一次性搬迁**：本次发版后首次升级时，若采用「先删旧目录」的方式，必须在删除前把旧 `reflex_web/{data,downloads,admin_config.json}` 拷到目标 `nw_web_data/`；文档与启动日志都会提示。是否需要在交付时附一个 `迁移数据.cmd` 辅助脚本？（当前设计只给文档步骤 + 自动迁移）
2. 数据根默认落在**部署目录的上一级**（`<parent>/nw_web_data`）。若你希望固定到别的盘（如 `D:\nw_web_data`），告知即可改成默认值。

## Risks / Deferred

- **迁移只在旧树尚存时自动生效**（见 R3），这是「先删后拷」升级方式的固有顺序问题，无法在代码里彻底消除。
- 既有部署若升级后未设 `NW_WEB_DATA_DIR` 且用旧启动脚本启动（例如自建 systemd/服务），数据会继续写在代码目录 → 文档必须把「用新启动脚本」写成硬要求；代码侧在启动日志打印实际数据根，便于核对。
- `feedback_model`/`share_model` 的 data dir 变更会影响 `test_web_feedback.py` 里「旧库迁移」用例（它通过切 env 模拟老库），改造时需保持该用例语义（改进程内 env + `reset()`）。