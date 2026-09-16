# 实施计划：Windows 局域网部署（8091）

## 步骤 1 — 构建脚本支持 `--port`

- [ ] `build_embedded_deploy.py`：`write_launchers(out_dir, python_exe, is_windows, port=8080)`；三份模板与 `部署说明.txt` 用 `port`；`main()` 加 `--port`（默认 8080，`type=int`）并传入。
- [ ] `build_offline_deploy.py`：同样加 `--port`；`write_launchers(out_dir, venv_python, port=8080)`。
- [ ] `test/test_web_data_paths.py`：现有调用保持可用（默认参数）；新增断言「传入 port=8091 时三份脚本都含 `--port 8091`」。

**验收**：`python -c "import sys;sys.path.insert(0,'reflex_web');import build_embedded_deploy as b;..."` 生成到临时目录后 grep 端口；`python test/test_web_data_paths.py` 全绿。

## 步骤 2 — 教程文档

- [ ] 新建 `docs/Web版局域网部署教程.md`（结构见 `design.md §2`，含防火墙命令、任务计划/NSSM 两种常驻方案、备份/升级、排错表）。
- [ ] `reflex_web/离线部署.md` 顶部加一行指向该教程；`README.md` 部署段也提一句。

## 步骤 3 — 构建 8091 的内嵌离线包

```bash
python reflex_web/build_embedded_deploy.py --skip-deps --port 8091
```

- 前端若过期会自动 `reflex export --frontend-only --env prod --no-zip`（本次网页结构改了，**必须**重编译）。
- 产物：`dist/reflex_web_embedded/`。

## 步骤 4 — 产物自检 + 真实起服务验证

按 `design.md §3` 四条逐项验证；起服务用产物自带的 python：
```bash
cd dist/reflex_web_embedded && python/python.exe reflex_web/run_app.py --host 127.0.0.1 --port 8091
```
（另开一个临时 `NW_WEB_DATA_DIR`，避免污染真实数据根。）

## 步骤 5 — 文档与提交

- [ ] `AGENTS.md` §2（部署）补 `--port` 与教程指引；`main_gui.py:CHANGELOG` 1.23.14 追加一条（构建脚本 `--port` + 教程）。
- [ ] 提交（只暂存本次文件；另一会话的在途改动不碰）。

## 完成定义（DoD）

- 产物能双击启动在 8091、页面与在线工具可用、反馈写入外部数据根；文档能照着把服务跑起来并做开机自启。
- `test/test_web_data_paths.py` 全绿（含新端口断言）；`release_check.py` 无 FAIL。