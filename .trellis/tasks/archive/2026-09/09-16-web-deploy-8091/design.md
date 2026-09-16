# 设计：Windows 局域网部署（端口 8091 固化）

## 1. 端口贯通链路

```
构建脚本 --port N（默认 8080）
   └─ write_launchers(..., port=N) → 三份启动脚本 + 部署说明.txt 里都写 --port N
          start_web.cmd / .ps1 / .sh  ──(转发 %* / $@)──►  run_app.py --host 0.0.0.0 --port N
                                                                  │
                                    单端口：前端静态 + 后端 API/WebSocket 同端口
                                                                  │
                              run_app.py 响应时把编译期硬编码的 localhost:<旧后端端口>
                              改写成请求头里的实际 host:N ⇒ 换端口无需重编译前端
```

- `--port` 只影响**生成的脚本内容**，不影响其他构建行为；命令行仍可 `start_web.cmd --port 9000` 覆盖。
- 签名（保持向后兼容，两个脚本各自的 `write_launchers` 末位追加默认参数）：
  - `build_offline_deploy.write_launchers(out_dir, venv_python, port=8080)`
  - `build_embedded_deploy.write_launchers(out_dir, python_exe, is_windows, port=8080)`

## 2. 教程文档结构（`docs/Web版局域网部署教程.md`）

面向「照着做就能上线」的运维视角，每一步给**命令 + 预期输出/现象 + 失败怎么办**：

| 环节 | 要点 |
|---|---|
| 0. 一次性准备 | 部署包拷到哪个路径（避开 `C:\Program Files`、避开含空格/中文的深层路径）；目标机需 64 位 Windows、无需装 Python；预留 ~200MB（含数据根） |
| 1. 开放 8091 | 两层都要：① 网络/安全组策略（用户已确认开放）；② **Windows 防火墙入站规则**——给出 `netsh advfirewall firewall add rule name="协议解析平台 8091" dir=in action=allow protocol=TCP localport=8091` |
| 2. 启动 | 双击 `start_web.cmd` 或 `.\start_web.cmd`；首次会打印 `[data] 运行数据目录: <部署上级>\nw_web_data` 并建目录；出现 uvicorn 监听行即成功 |
| 3. 验证 | 服务器本机 `http://127.0.0.1:8091/`；局域网 `http://<服务器IP>:8091/`；检查首页 Hero/12 协议表、点「进入在线工具」到 `/app` 能解析示例报文 |
| 4. 首次配置 | 管理员登录（默认口令，登录后应立即改）；「发布管理」上传客户端 exe 让「客户端下载」可用；换首页截图（可选） |
| 5. 常驻/自启 | 方案 A 任务计划程序（开机触发 + 失败重启 + 最高权限，命令给全）；方案 B NSSM 注册为 Windows 服务（`nssm install ... start_web.cmd`，给替代方案 `sc.exe` 注意点）；两者都强调**工作目录**必须是部署目录 |
| 6. 备份 | 停服 → 拷 `nw_web_data/`（反馈库+分享库+截图+已发布 exe+口令）；恢复=拷回后启动 |
| 7. 升级 | 替换部署目录；旧版（1.23.14 之前）数据先跑 `迁移数据.cmd`；升级**不要**动 `nw_web_data/` |
| 8. 排错表 | 端口占用（`netstat -ano \| findstr 8091`）、防火墙、页面能开但一直转圈（WebSocket 被拦/改端口后 env.js 缓存→强刷）、`数据目录不可写`（设 `NW_WEB_DATA_DIR`）、控制台中文乱码、杀软拦截 |

## 3. 产物验证（真实起服务，不是只看文件）

在**产物目录**里跑（不依赖仓库环境）：

1. `start_web.cmd` 生成的三份脚本都含 `--port 8091`；`部署说明.txt` 含 8091。
2. 产物不含 `reflex_web/data`、`reflex_web/admin_config.json`、`reflex_web/downloads/*.exe`、`version.json`；含 `client_screenshot.png`、`迁移数据.cmd`。
3. 用临时 `NW_WEB_DATA_DIR` 启动 → `GET /` 200（标题含「多协议解析平台」）、`GET /app` 200、`POST /api/feedback` 200 且库落在临时数据根、`GET /api/feedback/config` 200、`/download/` 与 `/fbimg/` 前缀各一个 200/404 符合预期。
4. 停服后确认进程退出干净（任务管理器无残留）。

## 4. 与既有约定的关系

- 数据外置契约（`app_data.py`）不变；教程里的数据目录说法必须与 `离线部署.md`、`AGENTS.md §2/§8-38` 一致（**不要**再出现「重建时自动保留 data/」这类旧说法）。
- 端口固化只是模板参数，不改 `run_app.py` 行为；`test/test_web_data_paths.py` 的启动器断言要跟着覆盖 8091 场景。