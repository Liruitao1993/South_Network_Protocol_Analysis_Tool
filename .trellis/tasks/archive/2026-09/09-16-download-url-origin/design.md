# 设计：下载地址与主机/端口解耦

## 1. 单一来源：`reflex_web/web_utils.py` 新增纯函数

```python
DOWNLOAD_ROUTE = "/download/"          # dev（reflex_web.py Starlette 路由）与 prod（run_app.py 中间件）都注册

release_download_path(exe_name) -> str          # "/download/<urlencoded 名>"，空名回落固定名
release_absolute_url(host, exe_name) -> str     # "http://<host>/download/<名>"；host 为空 → 相对路径
resolve_download_target(stored_url, exe_name, *, host, same_origin_serving) -> str
is_same_origin_serving(env=os.environ) -> bool  # run_app.py 设的 REFLEX_ENV=prod / __REFLEX_MOUNT_FRONTEND_COMPILED_APP=true
```

`resolve_download_target` 规则（按优先级）：

| # | 条件 | 结果 |
| --- | --- | --- |
| 1 | `stored_url` 有主机且**与当前 host 的主机名不同** | 原样返回（外部托管，尊重管理员配置） |
| 2 | 同源单端口部署（prod）或拿不到当前 host | 相对路径 `/download/<名>` ✓ 部署在 8091/任意端口都对 |
| 3 | 开发态（前端 3000 / 后端 8000 分端口） | `http://<host>/download/<名>`（host = 请求 host = 后端） |

主机名比较**忽略端口**（`server:8000` vs `server:8091` → 同主机 → 走规则 2）——这正是自愈历史 version.json 的关键。

## 2. State 侧改动（`reflex_web.py`）

- 新增 `_download_origin(self, fallback="")`：取 `self.router.headers.host`，为空时用调用方给的 host（无请求上下文的兜底）。
- `download_client()`：`web_utils.resolve_download_target(self.download_version_url, self.download_exe_name, host=self._download_origin(), same_origin_serving=web_utils.is_same_origin_serving())`。
- `load_release_info()` / `_update_release_url_filename()`：默认地址改 `web_utils.release_absolute_url(self._download_origin(), exe_name)`，删掉两段「socket 猜 IP + backend_port」。
- 删除死代码 `set_release_url_from_host`。

## 3. 测试（`test/test_web_download_url.py`）

1. 纯函数矩阵：路径编码（中文/空格名）、绝对拼接、host 为空、外部主机保留、同主机不同端口→相对、开发态→绝对、无当前 host→相对。
2. `is_same_origin_serving`：带 prod 标记 / 缺省 dev / 大小写与空值。
3. State 端到端：`State(_reflex_internal_init=True)` + `download_exe_available=True` + `download_version_url="http://server:8000/download/a.exe"` → `str(State.download_client())` 不含 `:8000` 且含 `/download/a.exe`；外部主机 URL → 原样出现；无 version.json → 相对路径。
4. 源码守卫：`reflex_web.py` 不再出现 `backend_port` 参与下载地址、且无 `socket.socket(...8.8.8.8...)` 猜 IP。

## 4. 重新构建与验收

- `python reflex_web/build_embedded_deploy.py --skip-deps --port 8091` → 复用既有 27 项产物验收脚本。
- 专项：往数据根塞一份 `url` 指向 `http://<host>:8000/...` 的 `version.json`，断言页面按钮目标为 `/download/...`（自愈），且发布页默认地址为真实 host（`http://127.0.0.1:8091/...`）。
