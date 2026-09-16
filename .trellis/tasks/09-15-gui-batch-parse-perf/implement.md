# 实施计划：批量解析后台化 + 详情按需 + 过滤提速

前置：`prd.md`（范围/验收）、`design.md`（契约/取舍）。命令均在项目根执行，offscreen 测试前设 `QT_QPA_PLATFORM=offscreen`。

**执行顺序刻意设计为「先解耦、再线程化、最后省内存」**：步骤 1 严格无行为变更，是后续所有步骤的公共前提；步骤 2/3/4 各自独立可回滚。

---

## 步骤 1 — 解耦准备（无行为变更，独立提交）

1. 新增 `MainWindow._current_parse_params() -> dict`：把 `_get_current_parser`（4638）中「读参数」的逻辑抽出（index / parse_level / frame_type / channel，含 `csg_pb_frame_type_combo.currentData()` 读法）；`_get_current_parser` 改为调用它。
2. `_get_summary_from_table_data`（7675）与 `_get_frame_type_name` 增加可选 `protocol_index=None` 形参（None → `self.current_protocol`），内部改读该参数。
3. 批量循环内 `current_parser = self._get_current_parser()`（7550）提到循环外（一次）。
4. 修缺陷：异常分支（7588-7598）也写入 `_type_name`（如 `"异常"`），并让 7632 的 `proto_type` 不再回落到上一帧残留的 `table_data`。

**验收**：

```bash
python test/test_csg_summary.py
python test/test_gw_monitor_summary.py
python test/test_batch_snapshot_locate.py
```

同一批输入（样本日志）解析后的 `batch_results` 字段与改动前逐字段一致（人工核对一次即可，步 3 会做正式对拍）。

**回滚点**：单体提交，`git revert` 即回到纯同步实现。

---

## 步骤 2 — 后台解析 + 进度 + 取消（独立提交）

1. 新建 `batch_parse_worker.py`：
   - `BatchParseWorker(QThread)`，信号 `progress(done, total, ok, fail, batch)` / `finished_ok(ok, fail)` / `cancelled(ok, fail)` / `failed(msg)`；`cancel()` 置标志。
   - 分片 200 帧；每片后检查取消；异常按帧隔离，转 `_status="异常"` + `错误` 字段（与现状一致）。
   - parser：`get_parser_class(spec.parser_key)()` → `build_gui_parser(index, base, parse_level=..., frame_type=..., channel=...)`（**不用单例**，见 `design.md` §4.3）。
   - 不 import 任何 widget；只依赖参数快照 + 解析器 + 两个摘要函数（以 `protocol_index` 实参调用）。
2. `main_gui.py`：
   - `parse_batch`（7330）拆为 `_prepare_batch_input()`（搬移现 7333-7430，保持剥离/快照/行号同步语义）与 `_start_batch_parse(frames, params)`。
   - 新增 `_on_batch_progress(...)`（`setUpdatesEnabled(False)` 包裹批量 append 行 + `batch_results.extend` + 进度条 + 状态栏增量）、`_finish_batch_parse(...)`（收尾，见 `design.md` §4.7）、`_cancel_batch_parse()`。
   - 工具栏加 `batch_progress_bar` + `batch_cancel_btn` + 计数标签；状态机：解析中禁用「批量解析」按钮与协议下拉。
   - `thread_registry.track(self, "批量解析")`；关闭窗口时取消 + `wait(2000)`。
3. `_refresh_batch_type_combo` / 时序图重建统一挪到 `_finish_batch_parse`。

**验收**：

```bash
QT_QPA_PLATFORM=offscreen python test/test_batch_snapshot_locate.py
python test/test_app_exit.py
```

手工（真实 GUI）：导入 33 MB 样本日志 → 解析期间窗口可拖动、进度条递增、「取消」可点；取消后 ≤1 s 停止且已完成行可看详情。

**回滚点**：删除新文件 + 恢复 `parse_batch` 主体（该提交自包含）。

### 步骤 2 完成与复核记录（2026-09-16）

**交付物**：`batch_parse_worker.py`（`CHUNK_SIZE=200` / `ACK_TIMEOUT=0.05` / `resolve_ed_wrapper` / `BatchParseWorker`）、`test/_batch_wait.py`（`wait_batch`）、`main_gui.py` 接线（`parse_batch` → `_prepare_batch_input` + `_start_batch_parse`，`_batch_ed_parser` / `_set_batch_parsing_state` / `_is_stale_batch_signal` / `_on_batch_progress` / `_on_batch_finished` / `_on_batch_cancelled` / `_on_batch_failed` / `_finish_batch_parse` / `_cancel_batch_parse`，工具栏进度条 + 取消按钮，`_shutdown_threads` 回收，`_ed_wrapper_for_frame` 委托）。

**4 个测试迁移到 `wait_batch`**（等待方式改变，断言语义不变；`check(...)` 调用集合逐条核对：48/48、8/8、16/16、0/0）：`test_batch_snapshot_locate.py`、`test_batch_src_line_jump.py`、`test_ed_fallback_fix.py`、`test_ofdma_batch.py`。

**复核中修掉的 2 个缺陷**：

1. **取消丢弃「未满一片」的结果**（本任务引入，中）——`run()` 的三处取消分支直接 `cancelled.emit` 返回，`batch` 里已解析未回传的帧（≤199）被静默丢弃；逐帧解析占本线程几乎全部耗时，取消**大概率落在分片中途**，因此不是偶发边界。现象：状态栏「已解析 N」大于表格行数（N 不诚实），且这些帧白解析（违背 R2）。修复：新增 `_emit_cancelled()`（`batch_parse_worker.py:354`），三处取消统一走它（先回传未满一片，再 `cancelled.emit`；刻意不等 ack，保证取消 < 1 s）。
2. **3 个迁移文件丢掉 `import _path_setup  # noqa: E402`**（本任务引入，中）——违反 AGENTS.md §7 强制约定；其中 `test/test_ed_fallback_fix.py` 直接 `ModuleNotFoundError: No module named 'main_gui'`（EXIT=1），而该文件在 `release_check.py:CORE_TESTS`（L74）内 ⇒ `python release_check.py` 会出现本任务引入的新失败。已补回 3 个文件的 import。

**独立探测证据**（写在 `/tmp/nwverify/`，不进仓库）：

- `probe_cancel.py`（真实 `MainWindow` offscreen，20000 帧）：`parse_batch` 返回 96 ms；progress 48 次、done 单调、`Σ分片条数 == batch_results 长度 == 表格行数`（9600/9600/9600）；取消耗时 13.8 ms；状态机复位；取消后结果仍带详情数据。
- `probe_partial_chunk.py`（纯逻辑，450 帧 / 分片 200，第 250 帧取消）：命中「分片中途」→ 回传批次 `[200, 50]`，`cancelled` 计数 250 == 实际回传 250 == 实际解析 250。
- `probe_counterfactual.py`（把 `_emit_cancelled` 换回修复前实现）：回传 200 vs 计数 250，**差额 50 帧复现** ⇒ 证明该修复确有必要。

**门槛**：`py_compile` OK；`test_batch_snapshot_locate` 47、`test_batch_src_line_jump` 7、`test_ed_fallback_fix` 15/0、`test_ofdma_batch`、`test_ed_gx_wrapper` 26、`test_csg_summary` 全过、`test_gw_monitor_summary` 18/0、`test_app_exit` 全过；`ruff check main_gui.py batch_parse_worker.py test/_batch_wait.py` = main_gui 10 项（8×F841 + 2×E741，与 HEAD 同类同数）、新文件 0 项。

**复核遗留（均低危、需改 `main_gui.py`，并入步骤 3 一起处理）**：

- `worker.disconnect(worker)`（`main_gui.py` 的 `_shutdown_threads` 与 `_start_batch_parse` 两处）实为**无效断连**（`QObject.disconnect(receiver)` 语义是「断开 this→receiver」，自己传自己实测返回 `False`），注释承诺的「先断信号」未生效；所有槽有 `_is_stale_batch_signal` 兜底，实测无功能影响 → 步骤 3 改为 `worker.disconnect(self)`。
- `_shutdown_threads` 把 `_batch_worker` 置 None 后再让 worker 的 `cancelled` 变成陈旧信号 → `_finish_batch_parse` 提前 return，批量按钮/协议下拉/进度条可能停在「解析中」；仅**真退出**路径可达（托盘最小化分支提前 return，不进 `_shutdown_threads`），无用户可见影响 → 步骤 3 调整置空时机。
- `_parse_ed_monitor_header` 在 `wrapper not in ("plc2", "gx")` 时回落读 `ed_wrapper_combo`，而该方法**在 worker 线程内被调用**（`_batch_ed_parser` 闭包）；当前 `resolve_ed_wrapper` 只返回这两个值 ⇒ 不可达 → 步骤 3 在闭包里归一化/断言 wrapper，避免将来跨线程读控件。

---

## 步骤 3 — 详情按需（去 `_table_data` 缓存，独立提交）

1. worker 产出的记录改为 `_has_detail` + `_frame_bytes`，不再写 `_table_data`（`design.md` §4.2）。
2. 新增 `MainWindow._get_frame_table_data(index)`（§4.4）：内存命中 → `None`+重解析 → LRU（50 帧）。
3. 改调用点：详情展示（9743-9744）、导出/复制（10084）、`enhanced_batch_export.py`（105/175/293/393 附近）、`enhanced_export.py`（83/126/212）。
4. `enhanced_export.py:232` 的 `"包含表格数据"` 改读 `_has_detail`（§4.5）。

**验收**（对拍，脚本化写进步骤 5 的测试）：

```bash
python test/test_batch_snapshot_locate.py
python -c "import subprocess" # 见下方说明
```

- 对同一输入，改动前保存一份 JSON 导出，改动后导出，逐字段 diff 必须为空（`包含表格数据` 列全为「是」）。
- 详情面板对成功帧/失败帧/异常帧分别展示，形态与改动前一致。

**回滚点**：该提交只动数据层与导出取值，`git revert` 后 `_table_data` 缓存恢复。

---

## 步骤 4 — 过滤提速 + 去抖（独立提交）

1. `_on_batch_filter_changed`（9877）：整体 `setUpdatesEnabled(False/True)` 包裹；行对象取一次缓存进局部变量；其余判定逻辑与字面量**保持不变**。
2. 关键词输入 250 ms 去抖（`QTimer` singleShot restart）；状态下拉变化立即生效（不走去抖）。

**验收**：`batch_search_edit` 连续输入，单次响应 < 0.2 s（测试内放宽断言）；过滤结果的可见行集合与旧实现一致（对拍）。

---

## 步骤 5 — 新增 `test/test_gui_batch_perf.py`

文件头按仓库约定：docstring → `import _path_setup  # noqa: E402` → `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`。覆盖：

1. **纯逻辑**：假 parser 驱动 worker —— 分片进度序列、取消中途停、单帧异常不影响后续帧、空表判失败。
2. **`_current_parse_params`**：12 个协议索引逐个取值与 `_get_current_parser` 行为一致（不读 widget 的等价断言）。
3. **内存**：49,532 帧结果集 < 40 MB（`sys.getsizeof` 递归近似或 `tracemalloc`）。
4. **UI 响应性**：解析中 `QTimer(0)` 心跳计数 ≥ 阈值（证明未阻塞事件循环）。
5. **取消**：发起后 < 1 s 停止，且已完成结果可读、可 `_get_frame_table_data`。
6. **详情按需**：LRU 命中/未命中路径、失败帧形态。
7. **过滤对拍**：新旧可见行集合一致 + 单次耗时断言。
8. **导出字段**：`包含表格数据` 列取值与改动前一致。

同时**迁移 `test/test_batch_snapshot_locate.py`** 的 3 处同步假设（147 / 235 / 259 直接 `win.parse_batch()` 后立即断言）：改为等待 worker 完成的公共 helper（pump event loop 直到 `_batch_worker is None`），不得改动其断言语义。

登记进 `release_check.py:CORE_TESTS`（与 `test/test_batch_snapshot_locate.py` 同组，紧邻插入）。

---

## 步骤 6 — 文档与门槛

1. `main_gui.py:CHANGELOG` 头部新增条目（后台化/进度/取消/内存/过滤 + 修的异常行类型缺陷）。
2. `AGENTS.md`：§8 陷阱补一条「批量解析已后台化：批量路径不得再直接同步调用 `parse_batch`；新增 QThread 必须 `thread_registry.track`；详情按需走 `_get_frame_table_data`」；§7 测试清单登记 `test_gui_batch_perf.py`。
3. 门槛：

```bash
python release_check.py
python test/test_app_exit.py
python test/test_batch_snapshot_locate.py
python test/test_gui_batch_perf.py
```

---

## 完成定义（DoD）

- [ ] 33 MB 样本：解析中界面可响应、有进度、可取消（< 1 s）；取消后结果可用。
- [ ] `batch_results` 常驻内存 < 40 MB（基线 229.4 MB）。
- [ ] 摘要表 ≤ 2 s 可见并可滚动（基线约 21 s 后一次性出现）。
- [ ] 过滤单次 < 0.2 s（基线 0.87 s）。
- [ ] 导出/复制/详情与改动前逐字段一致，`包含表格数据` 列不退化。
- [ ] `test_gui_batch_perf.py` 全过，`test_batch_snapshot_locate.py` 迁移后全过，`python release_check.py` 无 FAIL/WARN。
- [ ] CHANGELOG + AGENTS.md 已同步。
