# 下载地址端口错乱修复（发布页 / 首页按钮用编译期端口 8000）

## Goal

用户报告：部署在 8091 的实例，首页「下载客户端」跳到了 `<host>:8000/download/...`。核实为**设计缺陷**：下载地址由**编译期配置端口**（`rx.config` 的 frontend_port=3000 / backend_port=8000）与「猜本机 IP」拼成绝对 URL，部署成单端口 8091 后端口被改错并写进 `version.json`。

## Confirmed Facts（代码证据，2026-09-16）

| 位置 | 行为（缺陷） |
| --- | --- |
| `reflex_web.py:3536-3556` `load_release_info` | `release_url` 为空时：`socket(8.8.8.8)` 猜本机 IP + **`config.backend_port`(8000)** → `http://<ip>:8000/download/<exe>`，作为发布页默认地址 |
| `reflex_web.py:3641-3671` `_update_release_url_filename`（由 `:3637` 在上传 exe 后调用） | 地址为空时**再写一遍**同样的「猜 IP + 8000」逻辑 → 两份重复实现 |
| `reflex_web.py:3574-3609` `set_release_url_from_host` | 同一模式的第三份实现（按 `frontend_port != backend_port` 判定「开发模式」并把 host 端口改写成 8000）——**全仓无调用方，是死代码**（grep 仅命中定义） |
| `reflex_web.py:3326-3349` `download_client` | 首页/下载页按钮：`version.json.url` 存在就**原样跳转** → 跳到 `:8000`（用户看到的症状） |

**为什么不能简单改成相对路径**：`version.json.url` 同时被 GUI 客户端自动更新读取（`auto_updater.py:104-132` 取 `url` 后直接 `urllib.request.Request(url)`），**必须绝对地址**。

**为什么 config 端口不可用**：`run_app.py` 是单端口模式，运行时真实端口是 8091，而 `rx.config.get_config()` 仍是构建期 rxconfig.py 的 3000/8000。

## Requirements

- **R1 网页下载按钮**：优先走**同源相对路径** `/download/<exe>`（任意 host/port 都对，并**自愈**历史 `version.json` 里写死的 8000）；仅当 `version.json.url` 指向**别的主机**（外部托管）才原样使用。
- **R2 发布页默认地址 / version.json**：用**当前真实请求 host**（`self.router.headers.host`，实测可取；无上下文时回落相对路径），不再用 config 端口，也不再用 `socket` 猜 IP。
- **R3 收口**：三处重复实现收成一个纯函数模块（可脚本测试），删除死代码 `set_release_url_from_host`。
- **R4 测试**：纯函数矩阵（同源/外部主机/无 host/开发态）+ State 端到端（按钮生成的跳转串）+ 源码守卫（`reflex_web.py` 不再用 `backend_port` 拼下载地址、不再 socket 猜 IP）。
- **R5 重新构建 8091 部署包**并复验（含「已发布旧 version.json 也能正确跳到 8091」）。

## Out of Scope

- GUI 自动更新的 URL 语义（保持绝对地址）。
- 反向代理 / HTTPS / 域名。

## Risks

- 若运维确实把 exe 托管在别的服务器上，R1 的「外部主机原样使用」必须保留（否则会退化成站内 404）。
