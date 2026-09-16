# 实施计划：下载地址端口错乱修复

1. `reflex_web/web_utils.py` 加 4 个纯函数：`release_download_path` / `release_absolute_url` / `resolve_download_target` / `is_same_origin_serving`。
2. `reflex_web/reflex_web/reflex_web.py`：
   - 加 `_download_origin(self, fallback="")`；
   - 改 `download_client` / `load_release_info` / `_update_release_url_filename`；
   - 删死代码 `set_release_url_from_host` 与两处 socket 猜 IP。
3. 新增 `test/test_web_download_url.py`，登记 `release_check.py:CORE_TESTS`。
4. 跑 `test/test_web_download_url.py` + `test_web_data_paths.py` + `test_web_feedback.py` + `release_check.py`。
5. 重新构建 8091 包（`--skip-deps --port 8091`）→ 跑既有产物验收脚本 + 专项自愈验证（数据根放一份 `url` 指向 `:8000` 的 version.json）。
6. 文档：`AGENTS.md §8` 新增陷阱（不要用 `rx.config` 的端口拼对外 URL）；`main_gui.py:CHANGELOG`；提交 + 归档任务。
