# GUI 批量解析性能与内存（后台解析 / 进度 / 取消 / 详情按需）

## Goal

让「批量解析」在大输入（数万帧）下**不冻结界面、可中断、内存不爆**，并顺带修掉摘要过滤的逐键全表重排。

原状：一次 33 MB 真实日志（49,532 帧）= 主线程卡死约 21s（1.46s 剥离/提取 + 19.33s 解析）+ 常驻 229.4 MB + 50k 行一次性全量上表，期间无进度、无取消。

## Confirmed Facts（代码证据 + 实测，2026-09-15）

### 调用链与卡点

- `main_gui.py:2458` `batch_parse_btn.clicked → parse_batch`；`main_gui.py:7238` 另一处 `self.parse_batch()`（拖入/打开路径）。
- `main_gui.py:7330 parse_batch` 全程同步执行：剥离 → 清洗 → 提取 → **逐帧解析 + 逐行上表**，中间无 `processEvents`、无进度、无取消（全文件唯一 `QApplication.setOverrideCursor(WaitCursor)` 在 `main_gui.py:7218`，不在批量路径内；唯一 `processEvents` 在 `main_gui.py:2176`，无关）。
- `main_gui.py:7550` **在每帧循环体内**调用 `self._get_current_parser()`：49,532 次 registry 查表 + `parser_registry.build_gui_parser` 每次新建包装对象（`CSGGenGuiParser` 等）。纯浪费。
- `main_gui.py:7552` `table_data = current_parser.parse_to_table(frame_bytes)` → `main_gui.py:7585 "_table_data": table_data` 把**完整解析详情**塞进 `batch_results` 每一条 → 229.4 MB 的根源。
- 摘要表填充 `main_gui.py:7607-7641`：逐行 `insertRow` + 5×`setItem`，无分页（实测 49,532 行 = 1.49s，可接受）。
- `main_gui.py:9877 _on_batch_filter_changed`：对 `rowCount()` 全表逐行 `setRowHidden`（实测 0.87s / 每次按键；`setUpdatesEnabled(False)` 包裹后 0.02s）。
- `main_gui.py:2947 _debug_log` = `print(..., flush=True)`：批量路径在前 5 帧各打多条（无害，但 windowed exe 下不可见）。

### 解析器实例与线程安全（设计约束）

- `parser_registry.py:47 get_parser` 返回**共享单例**；`parser_registry.py:38 get_parser_class` 可取类自行实例化。
- 解析器实例带帧级可变状态：`csg_new_gen_parser.parse_to_table` 每帧重置 `_pb_size/_cmt_index/_pb_count`（`AGENTS.md` 陷阱 25 / 1.17.2）。**共享单例跨线程并发会互相污染** → 工作线程必须持有自己的实例。
- 需要现场解析的其它入口：单帧解析 `main_gui.py:5388`、对比页 `main_gui.py:3366`、快捷小窗、实时监控（`monitor_widget.py`）。

### `_table_data` 的消费者（去缓存的影响面，必须全部覆盖）

| 位置 | 用途 |
| --- | --- |
| `main_gui.py:9743` | 批量选中行 → 详情展示 |
| `main_gui.py:10084` | `result.get("_table_data", [])` 导出/复制路径 |
| `enhanced_batch_export.py:105 / 175 / 293 / 393` | Excel/CSV/TXT/JSON 详情明细 |
| `enhanced_export.py:83 / 126 / 212 / 232` | **`"包含表格数据": "是" if "_table_data" in result else "否"`** ← 摘要列**依赖缓存存在**，去缓存会让该列整列变「否」 |

### 行号 / 快照语义（不能被后台化破坏）

- `main_gui.py:7336-7339` 计算 `_batch_lead_lines`、重置 `_last_strip_line_map`；`main_gui.py:7347/7368` 剥离函数填充行映射；`main_gui.py:9214` `_set_batch_snapshot` 在 拖入/打开/粘贴/parse_batch 兜底 四处调用。
- 摘要行号 `src_line = _batch_lead_lines + strip_map[src_line_raw]`；`09-10-batch-snapshot-locate` 的「转到原始报文位置」依赖它，并依赖 `Qt.UserRole` 存的行↔结果索引（`main_gui.py:7613`）。
- 摘要表构造：`main_gui.py:2732-2776`（5 列 `ZoomableTableWidget`、`ExtendedSelection`、`SelectRows`、`NoEditTriggers`）。
- 时序图联动：`main_gui.py:7447` / `9401` 重置 `set_model(None)`，`9964` 起填充，`_seq_sync_guard` 防环 → 后台完成后才可重建。

### 现有测试的同步假设

- `test/test_batch_snapshot_locate.py:147/235/259` 直接 `win.parse_batch()` 后立即断言 `batch_results` / `_batch_lead_lines` → 后台化后必须等待完成（否则该文件全部失败）。

## Requirements

- **R1 后台化最小面**：保持「剥离 → 清洗 → 提取 → 快照 / 行映射」在主线程同步完成（1.5s 量级，且语义必须同步可见）；**只有逐帧解析 + 摘要表填充移到工作线程**。
- **R2 进度 + 取消**：解析期间显示进度（已解析 / 总数、成功 / 失败计数）与「取消」按钮；取消后已解析部分**保留且可用**（可看详情、可导出）。
- **R3 UI 只做攒批回填**：工作线程通过信号回传批次结果，UI 线程按批（而非逐帧）填表，保证拖动 / 点击可响应。
- **R4 内存**：`batch_results` 不再缓存 `_table_data`（改为详情 / 导出 / 复制时按需重解析单帧，实测 0.39 ms/帧）；摘要列「包含表格数据」语义**不得**回退为「否」。
- **R5 解析器实例**：循环内 `_get_current_parser()` 提到循环外；工作线程使用**自有实例**（`get_parser_class(...)()`）而非共享单例，避免与单帧页 / 实时监控竞争。
- **R6 过滤提速**：`_on_batch_filter_changed` 用 `setUpdatesEnabled(False/True)` 包裹并去掉冗余逐行取 item / `.data()`；输入去抖（避免连续按键排队）。
- **R7 回归与新增测试**：新增批量性能/取消的测试；把 `test/test_batch_snapshot_locate.py` 的同步假设改为「等待解析完成」的公共 helper。

## Acceptance Criteria

- [ ] 33 MB 样本日志解析期间，界面可响应（可拖动窗口 / 可点「取消」），并持续显示进度。
- [ ] 点「取消」后 ≤ 1s 停止解析，已完成结果仍可查看详情与导出。
- [ ] 同一输入的 `batch_results` 保留内存 **< 40 MB**（基线 229.4 MB）。
- [ ] 摘要表在解析开始后 **≤ 2s** 即可看到内容并滚动（基线：约 21s 后一次性出现）。
- [ ] 摘要关键词过滤单次响应 **< 0.2s**（基线 0.87s）。
- [ ] 详情展示 / Excel / CSV / JSON 导出 / 复制字段的输出与改动前**逐字段一致**，且「包含表格数据」列仍为「是」。
- [ ] 「转到原始报文位置」/ 时序图联动 / 行号回跳行为不变。
- [ ] 既有回归全过：`test_batch_snapshot_locate.py`、`test_csg_summary.py`、`test_gw_monitor_summary.py`、`test_app_exit.py`；`python release_check.py` 无 FAIL / WARN。

## Out of Scope

- 不改任何协议解析器内部算法、字节序、CRC 范围。
- 不线程化日志剥离 / 清洗 / 提取（1.5s 量级，且行映射语义要求同步）。
- 不做摘要表分页或 `QAbstractTableModel` 虚拟化（见 Open Questions）。
- 不把导出改成流式写出（属另一项：`09-15-web-parse-perf` 的桌面对应项）。
- 不改 `_debug_log` 的输出去向。

## Open Questions

1. **摘要表是否引入分页（对齐 Web 的 100/200/500/1000）？** 实测表明：内存 229MB 全在数据层、表格仅 13.3MB；过滤慢的根因是重绘而非行数，`setUpdatesEnabled` 一行即可从 0.87s → 0.02s；填充 49,532 行 1.49s 可接受。即**不引入分页也能满足全部验收标准**，而分页会改动全选 / 右键定位 / 导出选中 / 时序图联动的行语义（与进行中的 `09-10-batch-snapshot-locate` 有耦合）。待用户决策后再写 `design.md`。
