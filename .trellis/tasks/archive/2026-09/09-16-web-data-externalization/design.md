# 设计：Web 运行时数据外置

## 1. 分层与单一来源

```
reflex_web/reflex_web/app_data.py        ← 新增：路径解析唯一来源（纯 stdlib，无 Qt/无 reflex）
    ENV_VAR = "NW_WEB_DATA_DIR"
    code_root()      # run_app.py / reflex_web 包所在层 = <部署>/reflex_web
    is_frozen()      # hasattr(sys, "_MEIPASS") or getattr(sys, "frozen", False)
    data_root()      # env → frozen(exe 同级 nw_web_data) → 现状 code_root()
    feedback_dir()   # data_root()/data          （feedback.db + frameshare.db 同目录，与现状一致）
    uploads_dir()    # feedback_dir()/uploads/feedback
    downloads_dir()  # data_root()/downloads
    admin_config_path()  # data_root()/admin_config.json
    ensure_dirs()    # mkdir(data/uploads/feedback, downloads, admin_config 的父目录)
    legacy_paths()   # 旧的「树内」位置（= code_root() 下的 data/downloads/admin_config.json）
    migrate_legacy() # 旧有内容 + 新无 → move；返回迁移项；幂等

消费方（全部改为调它，不许再各自拼路径）
  feedback_model.data_dir()            → app_data.feedback_dir()
  share_model.data_dir()               → app_data.feedback_dir()
  reflex_web.py  _get_release_mgr()    → app_data.downloads_dir()
  reflex_web.py  _get_admin_cfg()      → app_data.admin_config_path()
  reflex_web.py  load_download_info()  → app_data.downloads_dir()
  reflex_web.py  _get_fbimg_dir()      → app_data.uploads_dir()
  run_app.py     _serve_download()     → resolve_paths().downloads_dir
  run_app.py     _serve_fbimg()        → resolve_paths().uploads_dir
  run_app.py     main() 启动期         → ensure_dirs() + migrate_legacy() + 打印数据根
```

## 2. 解析顺序（为什么这样排）

| 优先级 | 条件 | 数据根 | 理由 |
| --- | --- | --- | --- |
| 1 | 设了 `NW_WEB_DATA_DIR` | 该路径 | 运维可把数据指到别的盘；**部署脚本生成的启动器默认就注入它** |
| 2 | 冻结态（exe） | `Path(sys.executable).parent/"nw_web_data"` | onefile 的 `_MEIPASS` 退出即删（缺陷 C）；exe 同级目录可持久、升级只换 exe |
| 3 | 其他（开发机/手工启动） | `code_root()`（= 现状：`reflex_web/{data,downloads}`） | 开发者零感知，既有 dev DB 与测试路径假设不变 |

**为什么部署态不放在部署目录内的 `nw_web_data/`**：升级常见做法是「删掉旧目录 → 拷新包」，那样旧树里的数据在**新程序启动前**就被删了，自动迁移来不及。放在**部署目录的上一级**（`<parent>/nw_web_data`）后，无论"删旧拷新"还是"覆盖粘贴"，数据都在被替换的目录之外 ⇒ 天然幸存。

启动器模板（两种部署方式各 3 个脚本）统一写成「**已设则不覆盖**」：

```bat
if not defined NW_WEB_DATA_DIR for %%I in ("%~dp0..") do set "NW_WEB_DATA_DIR=%%~fI\nw_web_data"
```

```sh
: "${NW_WEB_DATA_DIR:=$(cd "$(dirname "$0")/.." && pwd)/nw_web_data}"; export NW_WEB_DATA_DIR
```

PowerShell 同理（`$env:NW_WEB_DATA_DIR` + `Resolve-Path`）。`%~fI` / `pwd` 归一化掉 `..`，避免日志里出现 `C:\deploy\..\nw_web_data`。

## 3. 迁移契约（`migrate_legacy`）

```
输入：无（内部用 data_root() 与 legacy_paths()）
行为：
  若 data_root() == legacy root（开发/未设变量）→ 直接返回 []（不做任何事）
  对 [data, downloads, admin_config.json] 逐项：
    源不存在          → 跳过
    目标已存在        → 跳过 + 记录「保留现有，未覆盖」（绝不覆盖）
    否则              → shutil.move（跨盘自动退化为 copy+delete）
  任何 OSError         → 捕获，记录到返回值 + 打印醒目告警（含新旧路径与手工命令），**不阻断启动**
返回：list[str] 迁移/跳过/失败的说明行（供启动日志与测试断言）
```

**顺序陷阱（写进文档的硬要求）**：自动迁移只在旧树尚存时生效。若运维「先删旧部署目录再拷新包」，必须在删除前手工把旧 `reflex_web/{data,downloads,admin_config.json}` 拷到 `nw_web_data/`。

## 4. 打包侧改动

两个构建脚本（`build_offline_deploy.py` / `build_embedded_deploy.py`）：

1. 把嵌套的 `_ignore_web_only` 提为**模块级** `ignored_web_entries(src, names) -> set[str]`（供测试直接调用），忽略集合加 `data`、`downloads`、`admin_config.json`、`nw_web_data`。
2. **删除** `preserve_data_dir`/`restore_data_dir`（offline）与 `preserve_data_dirs`/`restore_data_dirs`（embedded）及其调用点、`data_backup` 变量、「保留 data/」打印——外置+排除后它们只剩误导（缺陷 B）。`main()` 里改为直接 `rmtree(out_dir)` 重建。
3. 启动器模板（cmd/ps1/sh）与 `部署说明.txt` 增加数据根注入与说明；构建结束时打印数据根默认位置。
4. 保留 `--skip-deps` 增量模式的 `python/` 迁移逻辑（与数据无关）。

## 5. exe 侧

`reflex_web_exe.spec` **不改**：冻结态由 `app_data` 自动落到 exe 同级 `nw_web_data/`。前端静态资源仍走 `_MEIPASS`（`run_app.py:29-47` 不动）。文档注明：exe 与 `nw_web_data/` 同级；升级只替换 exe 文件。

## 6. 兼容与取舍

| 场景 | 行为 |
| --- | --- |
| 开发机（未设变量，非冻结） | 与今天完全一致（`reflex_web/data`、`reflex_web/downloads`、`reflex_web/admin_config.json`） |
| 部署（新启动器） | 数据在 `<部署上级>/nw_web_data`，代码目录可随意替换 |
| 部署（运维自建服务、未设变量、非冻结） | 回落「树内」现状（不会崩，但数据仍在代码目录）→ 启动日志打印实际数据根，便于发现 |
| exe | 数据在 exe 同级 `nw_web_data`（不再随重启丢失） |
| 既有部署升级（旧树尚存） | 首次启动自动搬走旧数据（幂等、不覆盖） |
| 既有部署升级（先删旧目录） | 需人工先拷（文档硬要求 + 启动日志告警） |

**删除 `FEEDBACK_DATA_DIR` / `FRAMESHARE_DATA_DIR`**：收敂为单一 `NW_WEB_DATA_DIR`（三个测试同步改），不做别名兼容——留两套变量正是本任务要消掉的「多处各自拼路径」。

## 7. 测试与验证

`test/test_web_data_paths.py`（纯脚本 + 临时目录，不启服务）：

1. **解析矩阵**：`NW_WEB_DATA_DIR` 设置 → 用它；monkeypatch `sys._MEIPASS`/`sys.frozen` + `sys.executable` → exe 同级；都不设 → 回落 `code_root()`。四路径（data/uploads/downloads/admin_config）逐项断言。
2. **单一来源**：`feedback_model.data_dir() == share_model.data_dir() == app_data.feedback_dir()`；`reflex_web.py` 的三个 getter 与 `resolve_paths()` 一致（用临时 env 指向沙箱，避免碰真实数据）。
3. `ensure_dirs()` 建出 `data/uploads/feedback` 与 `downloads`。
4. **迁移**：临时造旧树（`data/feedback.db` + `downloads/x.exe` + `admin_config.json`）→ 新根为空 → 全部搬走且内容一致；**再调一次幂等**；**新根已有同名文件时不覆盖**；只读/占用导致的失败路径返回告警串且不抛。
5. **打包排除**：两个脚本的 `ignored_web_entries` 含 4 个运行时项；并用临时小树 `copytree(ignore=…)` 端到端验证 `data/`、`downloads/`、`admin_config.json` 确实没被复制、而普通 `.py`/`.json` 被复制。
6. **启动器模板**：调 `write_launchers` 到临时目录（offline 与 embedded 各一次），断言三个脚本都含 `NW_WEB_DATA_DIR` 且带「已设则不覆盖」语义。
7. **既有测试**：`test_web_feedback.py`、`test_feedback_api.py`、`test_frame_share.py` 改用 `NW_WEB_DATA_DIR` 后全绿（含 `test_feedback_api` 的「旧库迁移」用例语义保持）。

**端到端验收（真实产物）**：`build_offline_deploy.py --output <tmp>` → 产物内**无** `reflex_web/{data,downloads,admin_config.json}`；启动该部署（`start_web.cmd` 等价命令 + 临时端口）→ 提交一条反馈 → 断言落在 `<tmp 上级>/nw_web_data/data/feedback.db`；**删除整个部署目录 → 重新构建/拷贝一份新的 → 重启 → 该反馈仍在**（核心验收）。

## 8. 回滚

- 代码侧：新模块 + 消费方改回原路径 + 启动器去掉注入（`git revert` 单提交可回）。
- 数据侧：数据根是**独立目录**，回滚后把 `nw_web_data/{data,downloads,admin_config.json}` 拷回 `<部署>/reflex_web/` 即可恢复旧行为；迁移是 move（非删除），迁移后旧位置为空但可随时拷回。
- 风险最低的发布顺序：先发本版 → 运维按文档升级（首次自动/手工搬迁）→ 之后升级只说一句「换目录」。
