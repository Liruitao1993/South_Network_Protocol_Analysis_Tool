# 多线程下载器四批次加固

## Goal

自动升级的多线程分段下载（`downloader.py` + `update_download_dialog.py` + `main_gui` 接线）在 1.23.95 首次落地后，经评审发现 17 项缺陷/欠账。本任务**全量落地四批次**，并用**可反证的自动化测试**钉住每条修复，交付一个「下载不会产出错文件、不会卡死退出、交互不再自相矛盾」的稳定版本。

## Background

- 现状：`downloader.download_multithreaded` 已实现 Range 分段 + 最多 32 线程 + 每线程独立 fd + 只写 `.part` + 合并校验 + 断点续传 + 暂停/取消 + 不支持 Range 时回落单流。
- 已知历史缺陷（上一轮已修）：多线程共用文件句柄导致 `seek/write` 踩偏移、64 KB 边界字节错位。
- 本轮评审发现的新问题（编号沿用评审清单，下文 AC 一一对应）。

## Requirements

### 批次一 · P0 数据安全与退出安全

| # | 要求 |
|---|---|
| R1 | 分段请求收到 `HTTP 200`（服务端/代理忽略 Range）时**不得**按段偏移写入；必须判为「该源不可分段」并回落单流，或复位该段进度后重下，**绝不能把整文件写进某一段的偏移**。 |
| R2 | 主窗口退出（含托盘退出、自动更新重启）时**必须取消正在进行的下载线程并等待其结束**；暂停态线程不得让进程带着运行中的 QThread 退出。暂停等待不得用 `sleep` 轮询。 |
| R3 | 同一时刻只允许一个下载任务；重复触发下载（再次点检查更新→下载）必须被拒绝并把已有面板唤到前台，不得起第二个 worker 抢同一个 `.part` / 覆盖 `_download_ctx`。 |

### 批次二 · P1 续传自证

| # | 要求 |
|---|---|
| R4 | 续传前必须校验 `url`（`progress.json` 已存该字段）：url 变化即整份进度作废。 |
| R5 | 分段的响应必须校验 `Content-Range` 起始偏移（须等于请求起点）与总长（须等于 plan 总长）；不符即判失败，不得静默错位写入。 |
| R6 | 单流回落路径也要能续传：暂停后再继续不得从 0 重来（服务端支持 `Range: bytes=off-` 时用追加写）；不支持时须在日志/面板明示「该源不支持断点续传」。`resume=False` 时单流也必须清理旧 `.part`。 |
| R7 | 磁盘空间不足等 `OSError` 必须转成可读中文提示（含所需空间/失败原因），不得把原始英文异常抛给用户。 |

### 批次三 · P1 交互可用性

| # | 要求 |
|---|---|
| R8 | 下载面板被用户点 X 关闭后，必须**能从界面上重新打开**（菜单入口或状态栏入口），并能继续暂停/取消；关闭时给「已在后台继续」提示。 |
| R9 | 下载结束后状态栏进度必须清理（不得永久占住状态栏顶掉后续消息）。 |
| R10 | 下载面板的 3 个按钮不得写死宽度，必须走 `gui_utils.fit_btn_width`（字号可配置时不裁字），并纳入按钮不裁字回归测试。 |
| R11 | 暂停期间界面必须自洽：进度快照的 `state` 要驱动标题/表格状态列（显示「已暂停」而不是继续「下载中」），继续后恢复。 |

### 批次四 · P2 一致性与清理

| # | 要求 |
|---|---|
| R12 | `DEFAULT_MAX_THREADS` 要么真正生效（自动默认它），要么删除；文档/注释口径必须与实际一致。 |
| R13 | `http_probe` 死参数删除或真正接入。 |
| R14 | `_UpdateDownloadWorker.progress` 死信号删除或停止 emit（避免误导接线）。 |
| R15 | 取消下载时**默认保留**已下载进度（下次可续传），并另提供「取消并清理缓存」的入口；面板文案与行为一致。 |
| R16 | 取消后尽快返回：不得顺序等待所有分段 future 结束；取消分支不得留空语句。 |
| R17 | 分段重试识别 `429` / `Retry-After`（有该头则按其秒数退避，无则沿用现有退避），并限制单次等待上限。 |

## Acceptance Criteria

每条 AC 都必须有**自动化测试**，且测试在修复被回退时会变红（变异反证至少覆盖 R1/R2/R3/R5/R10/R15）。

- [ ] AC1（R1）：本地服务端对**第 N 个**分段请求回 200 全文；断言最终要么逐字节正确，要么明确失败且不留脏进度（`.part` 的 done 全 0 或已清理），**绝不会**出现「大小对、内容错」的目标文件。
- [ ] AC2（R2）：offscreen 起下载 → pause → 关闭主窗口；断言 `DownloadControl.cancelled` 为真、下载线程 `isRunning()` 为假、关闭流程在超时内返回、无残留写入。
- [ ] AC3（R3）：`_start_download` 在已有运行中的下载线程时直接返回（不再起新线程），并把旧面板显示出来；断言线程数与 `_download_ctx` 未被改写。
- [ ] AC4（R4）：构造 `progress.json` 的 url 与当前请求不同、其余字段（total/layout/done）全部一致；断言进度作废（所有段 done=0）。
- [ ] AC5（R5）：本地服务端返回偏移错位的 `Content-Range`；断言该段判定失败（不产生错位写入 / 最终目标文件不落地）。
- [ ] AC6（R6）：单流路径 pause→resume，第二次请求带 `Range: bytes=off-` 且最终文件逐字节正确；`resume=False` 时旧 `.part` 被清。
- [ ] AC7（R7）：模拟 `truncate` 抛 `OSError(ENOSPC)`；断言抛 `DownloadError` 且消息含「磁盘空间」。
- [ ] AC8（R8）：面板 `close()` 后可从菜单/状态栏重新打开（`isVisible()` 为真），且仍能取消。
- [ ] AC9（R9）：下载结束后 `statusBar().currentMessage()` 为空。
- [ ] AC10（R10）：10/12/14 号字下三个按钮 `width() >= sizeHint().width()` 且未设 `maximumWidth`（不是写死）；反例自检（改回 `setFixedWidth` 必红）。
- [ ] AC11（R11）：`DownloadProgress(state="paused")` 喂进面板后，标题/状态列显示「暂停」，继续后恢复「下载中」。
- [ ] AC12（R12/13/14）：`DEFAULT_MAX_THREADS` 语义有断言（生效或已不存在）；`http_probe` 无残留引用；`_UpdateDownloadWorker` 无未连接的 `progress` 信号（源码守卫）。
- [ ] AC13（R15）：默认取消后 `.part` 与 `progress.json` 仍在且 done 可复用；「取消并清理」路径删除缓存；断言两者行为不同。
- [ ] AC14（R16）：取消后 `download_multithreaded` 在有限时间内返回（不等待卡住的分段），且取消分支无 `pass` 空语句。
- [ ] AC15（R17）：服务端回 429 + `Retry-After: 1`，断言第二次尝试发生在 ≥1s 且 ≤上限；无该头时退避行为与旧一致。
- [ ] AC16：`python test/test_downloader.py` + `test/test_update_download_dialog.py` + 新增 GUI/接线用例全绿；`release_check.py` 相关项不回归。

## Out of Scope

- 不改 `auto_updater.update.bat` 的替换/回滚编排（1.23.89 已加固）。
- 不引入第三方下载库（保持纯标准库）。
- 不做限速 / 代理认证 / 断点续传的跨机器迁移。

## Constraints

- `downloader.py` 必须保持**纯逻辑、无 Qt**（可脱离 GUI 测试）。
- 单帧解析与其它模块零行为变化；只在 `downloader.py` / `update_download_dialog.py` / `main_gui.py` 的下载接线与收尾处改动。
- 所有测试文件放 `test/`，文件头含 `import _path_setup  # noqa: E402,F401`。
- 遵守项目陷阱 63（按钮不写死宽度）、陷阱 20b（退出必须显式 `QApplication.quit()`）、陷阱 40（新增 QThread 必须 `thread_registry.track`）。
