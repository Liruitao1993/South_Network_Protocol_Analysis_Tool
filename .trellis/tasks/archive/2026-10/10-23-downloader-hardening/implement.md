# 执行计划 · 多线程下载器四批次加固

> 顺序 = 依赖顺序：先纯逻辑自证（批次二的基础函数），再 P0，再 GUI。每步完成即跑对应测试，不留「最后一起跑」。

## 步骤 0 · 基线与回归保护

- [ ] 0.1 记录基线：`pwshu 'python test\test_downloader.py'`、`python test\test_update_download_dialog.py`、`python test\test_btn_width_fit.py` 三项全绿。
- [ ] 0.2 `git status` 确认工作区无本轮无关改动（已有 79 项历史改动，不清理、不提交它们）。

## 步骤 1 · downloader.py 纯逻辑（批次二 + 部分四）

- [ ] 1.1 新增异常 `_RangeViolation`（带 `reset_done`）与 `_verify_segment_response(status, headers, seg, plan)`（单一实现，R1/R5 共用）。
- [ ] 1.2 `_download_segment` 接入自证 + `Retry-After`（R17）+ 偏移不符/reset 复位。
- [ ] 1.3 `download_multithreaded` 捕获 `_RangeUnsupported` → `cleanup_partial` → 回落单流；`on_cancel` 参数（R15）。
- [ ] 1.4 `_load_progress` 校验 url（R4）。
- [ ] 1.5 `_download_single_stream` 支持 Range 追加续传 + `resume=False` 清理（R6）+ `restart` 进度提示。
- [ ] 1.6 预分配与合并的 `OSError` → 中文 `DownloadError`（R7）。
- [ ] 1.7 `choose_thread_count` 用 `DEFAULT_MAX_THREADS`（R12）；删 `http_probe`（R13）。
- [ ] 1.8 取消路径 `shutdown(cancel_futures=True)` + `as_completed` + 删空 `pass`（R16）。
- [ ] 1.9 跑 `test/test_downloader.py` + 新增用例（AC1/AC4/AC5/AC6/AC7/AC12/AC13/AC14/AC15）。

## 步骤 2 · update_download_dialog.py（批次三面板）

- [ ] 2.1 三按钮改 `fit_btn_width`（R10）。
- [ ] 2.2 `update_progress` 按 `progress.state` 驱动标题/状态列（R11）。
- [ ] 2.3 `closeEvent` → 后台运行 + `background_requested`（R8，控件侧）。
- [ ] 2.4 新增「清理缓存」按钮 + `discard_requested` 信号（R15 界面侧）。
- [ ] 2.5 `mark_failed` 也禁用「后台运行」（一致性）。
- [ ] 2.6 跑 `test/test_update_download_dialog.py`（含新增 AC10/AC11）。

## 步骤 3 · main_gui 接线（P0 + 交互）

- [ ] 3.1 `DownloadControl.wait_resumed()` 与 worker pause 改事件等待（R2 逻辑侧）。
- [ ] 3.2 `closeEvent` 对 `_download_thread` 先 `cancel()` 再 `wait(2000)`（R2）。
- [ ] 3.3 `_start_download` 防重入 + 唤回面板（R3）。
- [ ] 3.4 状态栏统一收尾 `clearMessage()`（R9）。
- [ ] 3.5 「配置 → 下载进度…」菜单项（R8 入口）；面板 `discard_requested` → 清理并刷新（R15）。
- [ ] 3.6 删 `progress` 死信号与 `progress_cb`（R14）。
- [ ] 3.7 跑新增 `test/test_update_download_wiring.py`（AC2/AC3/AC8/AC9）。

## 步骤 4 · 反证与收尾

- [ ] 4.1 变异反证 6 条（R1/R2/R3/R5/R10/R15）：改回旧写法 → 断言变红 → 还原 → 再全绿。
- [ ] 4.2 `test/test_btn_width_fit.py` 纳入下载面板（AC10 的字号矩阵）。
- [ ] 4.3 全量：`pwshu 'python release_check.py --with-gui'`（本机常见 4 项 offscreen 退出期 fastfail 属已知，需与实际断言失败区分）。
- [ ] 4.4 版本与文档：`APP_VERSION` 1.23.95 → **1.23.96**、`BUILD_DATE`、`main_gui.CHANGELOG` 顶部条目、`README` 下载相关描述、`AGENTS.md` §10 摘要。
- [ ] 4.5 更新 `.trellis/spec` 中与本模块相关的约定（若有对应层文档）。

## 验证命令

```bash
# 纯逻辑
pwshu 'python test\test_downloader.py'
# 面板
pwshu 'python test\test_update_download_dialog.py'
# 接线（offscreen）
pwshu 'python test\test_update_download_wiring.py'
# 按钮不裁字（含新面板）
pwshu 'python test\test_btn_width_fit.py'
# 门禁
pwshu 'python release_check.py --with-gui'
```

## 回滚点

- 步骤 1 后：`git checkout -- downloader.py`（GUI 不受影响）。
- 步骤 2 后：`git checkout -- update_download_dialog.py`。
- 步骤 3 后：`git checkout -- main_gui.py`。
- 整体回滚：三个文件一起 checkout 即回到 1.23.95。
