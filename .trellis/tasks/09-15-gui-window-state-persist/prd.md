# GUI 窗口 / 分栏 / 列宽状态持久化

## Goal

让「窗口大小与位置、结果区分栏比例、主要表格列宽」在关闭后保存、下次启动还原；并保证**恢复出来的布局永远可见可用**（换显示器 / 分辨率变化 / 配置损坏都不能把窗口丢到屏幕外或直接报错）。

## Confirmed Facts（证据，2026-09-15）

- 全仓库（排除 `dist/`）**无任何** `saveGeometry` / `restoreGeometry` / `saveState` / `restoreState` / `QSettings` —— `grep -rn "QSettings" --include=*.py .` 返回空，`main_gui.py` 对几何/分栏/列宽**零持久化**。
- 分栏只有一个：`main_gui.py:2841` 硬编码 `result_splitter.setSizes([450, 550])`。
- 列宽共 **45** 处硬编码 `setColumnWidth`，涉及：单帧结果 `result_table_widget`（1970-1972）、批量摘要 `batch_summary_table`（2739-2741）、批量详情 `batch_detail_table`（2817-2819）、查询页 `di_table`（2229-2233 / 4207-4211）、`obis_table`（4271-4273）、`dlt645_di_table`（4319-4320）、`cmd_table`（4526）、`gdw_table`（3922-3924）、`eb_di_table`（3961-3964）、`oad_table`（3535-3538）。
- **已有现成的持久化通道**（不需要引入新机制）：`main_gui.py:10512 _save_app_config` 已把 `ui`（主题/字体/毛玻璃，经 `theme_settings.py:2083 ThemeManager.to_config` 序列化）与 `parse` 段写入 `app_paths.data_path("config.json")`。
- 窗口最小尺寸兜底在 `main_gui.py:1273-1278`（`setMinimumSize(1000, 700)`）。
- 退出路径涉及托盘：`closeEvent` 在 `main_gui.py:6530`，最小化到托盘分支 `event.ignore()`；真正退出分支在 `event.accept()` 后追加 `QTimer.singleShot(0, QApplication.quit)`（`AGENTS.md` 陷阱 20b）——保存必须走这条真实退出路径。
- 协议切换会重建查询表格（`_update_protocol_lookup_tab` `main_gui.py:3494` → `_clear_layout` + builder），**列数会因协议不同而变**，恢复时必须校验列数。

## Requirements

- **R1 窗口几何**：用 `QMainWindow.saveGeometry()/restoreGeometry()`（QByteArray → base64 存 JSON）持久化；**恢复后必须做可见性校验**——若窗口矩形与当前任一 `QScreen.availableGeometry()` 无相交（换显示器 / 分辨率变小），则丢弃保存值改用默认居中尺寸，不把窗口丢到屏幕外。
- **R2 分栏状态**：`result_splitter.saveState()/restoreState()`；`setSizes([450, 550])` 降级为「无保存值时的默认」。
- **R3 列宽状态**：对 R-Facts 列出的表格持久化 `horizontalHeader().saveState()`；恢复时**逐表校验 `count()` 与当前列数一致**，不一致（协议切换导致）则忽略该表并保留代码默认宽度。
- **R4 存储通道**：沿用 `config.json` 现有 `_save_app_config`（`main_gui.py:10512`）通道，新增 `ui.window` 段；**不引入 `QSettings`**（全仓库 0 处使用，保持一致，且 `config.json` 已随 `app_paths` 处理 frozen 路径）。
- **R5 写出时机**：真实退出路径（含托盘「退出」与自动更新重启）都必须在关闭前写出；最小化到托盘（`event.ignore()` 分支）不写。
- **R6 容错**：键缺失 / base64 损坏 / 值类型错误 / 列数不匹配 → **静默回落默认布局**，不得弹错、不得启动失败。
- **R7 恢复默认入口**：设置菜单提供「恢复默认窗口布局」，一次性清掉 `ui.window` 段并应用默认尺寸。
- **R8 冻结版路径**：`config.json` 通过 `app_paths.data_path` 定位（frozen 下为 exe 目录），不得直接写相对路径。

## Acceptance Criteria

- [ ] 移动窗口 + 改大小 + 拖动 `result_splitter` + 调整单帧结果表与批量摘要表列宽 → 退出 → 重启：全部还原。
- [ ] 删除 `config.json` 的 `ui.window` 段（或用损坏的 base64 替换）→ 启动不报错，使用默认布局，且此后能正常保存。
- [ ] 模拟第二显示器被移除（保存的几何落在当前屏幕外）→ 启动后窗口仍完整可见。
- [ ] 协议切换（12 个逐个切）后表列数变化时，不崩溃、不套用错误的列宽、不报错。
- [ ] 托盘「退出」与菜单「退出」两条路径都能保存（`test/test_app_exit.py` 场景下验证）。
- [ ] 新增 `test/test_window_state.py`（offscreen：保存→恢复往返、坏值回落、屏幕外回落、列数不匹配忽略、恢复默认）。
- [ ] 既有 `test/test_theme_settings.py`、`test/test_app_exit.py` 全过；`python release_check.py` 无 FAIL / WARN。
- [ ] `main_gui.py:CHANGELOG` 增条目。

## Out of Scope

- 多套布局档 / 按协议分别记忆几何 / 按项目记忆。
- 弹窗类几何持久化（`_open_table_popup` 克隆弹窗、`show_detail_dialog`、快捷解析小窗、详情对话框）。
- 迁移到 `QSettings` 或独立 `window_state.json`（复用 `config.json` 更少新机制）。
- 字体缩放 / `ZoomableTableWidget` 的 zoom 级别持久化。

## Open Questions

- 列宽持久化的表格清单以上文 R-Facts 的 10 张为准（覆盖单帧结果、批量摘要/详情与 7 个查询页表）。若需增减（例如加入 TCP 监控表、实时监控表），实现前告知即可，不影响其余设计。
