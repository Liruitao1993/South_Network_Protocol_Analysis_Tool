# Windows 局域网服务器部署包（端口 8091）

## Goal

用户要把 Reflex Web 版部署到**局域网 Windows 服务器**，该机只开放 **8091** 端口。交付两样：① 一份可直接照做的部署教程；② 针对该场景构建好的**内嵌 Python 离线部署包**（零安装、已把 8091 固化进启动脚本）。

## Confirmed Facts（代码/现场证据，2026-09-16）

- 构建机 = Windows（本项目工作机），已具备：`dist/reflex_web_embedded/python/python.exe` 存在（**可走 `--skip-deps` 增量构建**，分钟级）、`dist/.build_cache/python-3.12.4-embed-amd64.zip` 已缓存、`uv 0.7.8` 可用。
- 两个构建脚本的启动器模板**写死 `--port 8080`**：`build_embedded_deploy.py::write_launchers`（`--host 0.0.0.0 --port 8080`）、`build_offline_deploy.py::write_launchers` 同构；`部署说明.txt` 里的改端口示例是 `--port 9000`。启动器均转发 `%*` / `$@`，即**可以**用 `start_web.cmd --port 8091` 覆盖，但双击不带参数就会跑 8080 → 用户会以为部署失败。
- `run_app.py` 是**单端口模式**（前端静态 + 后端 API/WebSocket 共用 `--port`），并把编译进前端的 `localhost:<backend_port>` 硬编码在响应时改写成实际访问的 `host:port`（`run_app.py:125-160`）→ 换端口无需重编译前端。
- 运行数据外置于部署目录的上一级 `nw_web_data/`（1.23.14 起，任务 09-16-web-data-externalization）：`NW_WEB_DATA_DIR` → 冻结态 exe 同级 → 回落代码目录；启动脚本注入变量且已设则不覆盖。
- 本次网页结构有改动（首页 `/` + 工具页 `/app`）→ **前端 bundle 必须重编译**，否则部署包里还是旧页面。`ensure_frontend()` 会按源码 mtime 自动触发 `reflex export --frontend-only --env prod --no-zip`。

## Requirements

### R1 端口可配置并固化
- 两个构建脚本新增 `--port`（默认 8080），写进 cmd / ps1 / sh 三份启动脚本与 `部署说明.txt`；`--port` 仍可覆盖。
- 本次以 `--port 8091` 构建，产物双击 `start_web.cmd` 即监听 8091。
- 测试同步：`test/test_web_data_paths.py` 的启动器断言覆盖「传入端口出现在三份脚本里」。

### R2 部署教程（`docs/Web版局域网部署教程.md`）
按操作顺序写清每一步的**具体命令与预期现象**：
1. 前置（目标机要求、开放 8091 的两层含义：安全组/网络策略 + Windows 防火墙入站规则）
2. 拷贝部署目录（放在哪个路径、为什么不要放在 C:\Program Files）
3. 首次启动（双击/命令行、首次会建 `nw_web_data`、控制台该看到什么）
4. 验证（本机 `http://127.0.0.1:8091`、局域网 `http://<服务器IP>:8091`、首页与在线工具各点一下）
5. 管理员登录与首次发布客户端 exe（发布管理 Tab）
6. 开机自启/常驻（两种：任务计划程序「开机启动 + 失败重启」；或 NSSM/`sc` 包装成服务；给出具体命令与注意事项）
7. 数据目录与备份（`nw_web_data/` 位置、备份=停服后拷该目录）
8. 升级（替换部署目录；旧版数据先跑 `迁移数据.cmd`）
9. 排错表（端口被占/防火墙/页面打开但连不上后端/数据目录不可写/中文乱码）

### R3 构建并验证产物
- 构建：`python reflex_web/build_embedded_deploy.py --skip-deps --port 8091`（增量；前端若过期会自动重编译）。
- 产物自检：不含 `reflex_web/{data,admin_config.json}`、`downloads/` 里无 exe/version.json、启动脚本含 8091、含 `迁移数据.cmd`、`部署说明.txt` 写的是 8091。
- **真实起服务验证**：从产物目录启动（`--port 8091` + 临时 `NW_WEB_DATA_DIR`）→ `http://127.0.0.1:8091/` 返回 200 且标题为首页、`/app` 可用、`POST /api/feedback` 写入外部数据根、`/download/*` 与 `/fbimg/*` 前缀路由正常，最后停服。

## Out of Scope

- 反向代理/Nginx、HTTPS、域名（局域网单端口直连场景）。
- 改动 Reflex 代码或数据外置逻辑（前一任务已完成）。
- Linux 产物（本机无法构建 Linux 内嵌包；若目标改为 Linux，需在 Linux 机器上跑同一脚本）。

## Risks / Deferred

- 目标机若是 32 位或非 amd64 → 内嵌包不适用（需另行处理）。
- 8091 若只在内网策略层开放、Windows 防火墙未放行，浏览器会连不上：教程里必须包含 `netsh advfirewall` 的具体命令。
- 首次启动会写 `nw_web_data/`（部署目录的上一级）→ 若部署目录放在只读盘或根目录（如 `D:\`），上一级可能不可写；教程给出「显式设置 `NW_WEB_DATA_DIR`」的兜底。