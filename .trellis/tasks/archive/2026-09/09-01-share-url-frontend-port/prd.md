# 分享成功后浏览器打开前端地址（dev 端口自适应）

## Goal

GUI「分享此帧」成功后弹窗「是否在浏览器打开分享页」，当前打开 `server_url + /share`。
dev 模式（`reflex run`）前端 3000 / 后端 8000 分端口，GUI 的 server_url 必须指向后端
8000（POST /api/frameshare 才能通），导致浏览器打开 `http://<host>:8000/share`——
后端不服务页面路由，打不开。需要让 GUI 始终打开**浏览器可访问的分享页地址**。

## Background

- prod 模式（`reflex_web/run_app.py` 打包 exe / 单端口 uvicorn，默认 8080）前后端同源，
  `server_url + /share` 本来就对。
- prod 与 dev 的 `/api/frameshare` 都由 `reflex_web/reflex_web/reflex_web.py` 中
  `_dev_frameshare_api_handler`（注册在 `app._api.routes`）处理；run_app.py 无 frameshare
  分支，prod 请求落到 Reflex ASGI 后同样走该 handler。改一处响应即覆盖两种模式。
- 已有先例：`set_release_url_from_host`（reflex_web.py:3351）做反向端口替换
  （前端 host → 后端端口，供 /download 用），本次逻辑方向相反。

## Requirements

- POST `/api/frameshare` 成功响应（HTTP 200, `ok: true`）新增 `share_url` 字段：
  - dev 模式（未设置 `__REFLEX_MOUNT_FRONTEND_COMPILED_APP`）：把请求 Host 的端口替换为
    `rx.config.get_config().frontend_port`（默认 3000），Host 无端口时补端口；
    路径 `/share`，scheme 取请求 scheme。
  - prod 模式（run_app.py 设置 `__REFLEX_MOUNT_FRONTEND_COMPILED_APP=true`）：同源，
    直接用请求 Host 头拼 `http(s)://<host>/share`。
- GUI `share_dialog.py`：
  - 分享成功后保存响应中的 `share_url`；「在浏览器查看分享页」按钮与成功弹窗的「是」
    都打开该 URL。
  - 响应无 `share_url`（旧服务端）时兜底 `self.server_url + "/share"`，行为不变。
- 不改变提交 API 的地址、字段、频率限制与错误响应。

## Acceptance Criteria

- [ ] dev 模式（前端 3000/后端 8000）GUI 分享成功后，浏览器打开
      `http://<host>:3000/share`（不是 8000）。
- [ ] prod 单端口模式（如 8080）分享成功后打开 `http://<host>:8080/share`。
- [ ] 旧服务端（响应无 share_url）GUI 仍按原逻辑打开 `server_url + /share`，不报错。
- [ ] `test/test_frame_share.py` 通过（含 share_url 相关新断言）。
- [ ] GUI offscreen 冒烟通过。

## Notes

- 端口替换用正则 `:\d+$` 处理 Host 头（与 set_release_url_from_host 同手法）。
- dev 下若 GUI 经 Vite 代理（server_url 指 3000）提交，Host 端口已是前端端口，
  替换为 no-op，结果仍正确。
