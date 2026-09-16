# 设计：批量解析后台化 + 详情按需 + 过滤提速

前置阅读：`prd.md`（范围与验收）。本设计**不含分页**——用户已确认按实测结论走「只修数据层」（见 §7.1）。

---

## 1. 现状与根因（实测，2026-09-15）

输入样本：`CCO-2-COM3-260628-124120 - 复制.log`（33 MB / 316,671 行 / GBK），协议 9（CSG），产出 **49,532 帧**。

| 阶段 | 现状耗时 | 位置 |
| --- | --- | --- |
| 剥离监控前缀 | 1.26 s | `main_gui.py:7347/7368` |
| 提取帧 | 0.20 s | `main_gui.py:8348 _extract_frames_for_protocol` |
| 逐帧解析 + 逐行上表 | **19.33 s** | `main_gui.py:7550-7645` |
| 摘要表填充 | 1.49 s（含在上行内） | `main_gui.py:7605-7641` |
| 过滤一次按键 | 0.87 s | `main_gui.py:9877 _on_batch_filter_changed` |
| 常驻内存 `batch_results` | **229.4 MB** | `main_gui.py:7585` |
| 表格控件自身内存 | 13.3 MB | 实测 |
| 同一过滤循环 `setUpdatesEnabled(False)` 包裹 | **0.02 s** | 实测 |

四个根因：

1. **全同步主线程**：`parse_batch`（7330）从剥离到填表 21 s 无一次事件循环让步，界面完全冻结。
2. **详情全量常驻**：`"_table_data": table_data`（7585）把每帧完整解析表缓存进 `batch_results` → 229.4 MB。
3. **循环内建 parser**：`current_parser = self._get_current_parser()`（7550）在 49,532 次迭代里各做一次 registry 查表 + `build_gui_parser` 包装对象分配。
4. **过滤无重绘抑制**：9877 对全表逐行 `setRowHidden`，代价来自重绘而非循环本身。

附带缺陷（本设计顺带修，属同一条代码路径）：

- 异常分支（7588-7598）写入的 dict **缺 `_table_data` / `_type_name`**，而紧随其后的 `proto_type = self.batch_results[-1].get("_type_name") or self._get_frame_type_name(table_data, status)`（7632）会**读到上一帧残留的 `table_data`** → 异常行的「协议/类型」列可能张冠李戴。

---

## 2. 目标 / 非目标

**目标**：把 19.33 s + 1.49 s 的逐帧工作移出 UI 线程，使其可进度化、可取消；把 229.4 MB 降到 < 40 MB；把过滤从 0.87 s 降到 < 0.2 s。

**非目标**：不改解析算法；不线程化剥离/提取（见 §7.2）；不做分页；不改导出格式。

---

## 3. 数据流（改后）

```text
点击「批量解析」/ 程序化调用（7238）
│
├─ UI 线程（同步，~1.5 s）
│   _prepare_batch_input()                       ← 现 7333-7430 原样搬移，语义不变
│     clean → _strip_*（填 _last_strip_line_map）→ _extract_frames_for_protocol
│     → _batch_lead_lines / _set_batch_snapshot（四处快照调用之一，9214）
│   _current_parse_params()                      ← 参数快照（§4.1）
│
├─ _start_batch_parse(frames, params)            ← 新增
│   建 BatchParseWorker(frames, params)（§4.3）
│   thread_registry.track(self, "批量解析")
│   摘要表 setRowCount(0)、进度条归零、禁用「批量解析」与协议下拉
│
├─ Worker 线程（自有 parser 实例）
│   分片（每 200 帧）：
│     逐帧 parse_to_table → 摘要 → 状态判定 → 临时 table_data 用完即弃
│     emit progress(已解析数, 总数, 成功数, 失败数, 批次结果列表)
│     每片检查 self._cancel → emit cancelled(已完成结果)
│   emit finished(计数)
│
└─ UI 线程（槽）
    progress  → setUpdatesEnabled(False) 批量 append 行 + batch_results.extend + 进度条 + 状态栏
    finished  → 收尾（§4.7）：过滤计数 / batch_type_combo / 时序图 / 自动选中首行 / 恢复控件
    cancelled → 同上收尾，但状态栏提示「已取消：已解析 N / M 帧」

详情 / 导出 / 复制
   _get_frame_table_data(idx)（§4.4）→ LRU 命中 或 按锁存的原始帧字节重解析
```

---

## 4. 契约

### 4.1 解析参数快照 `_current_parse_params() -> dict`（新增，纯读）

从 `_get_current_parser`（4638）中抽出「读参数」部分，返回：

```python
{"index": int, "parse_level": str | None, "frame_type": Any, "channel": str}
```

- `_get_current_parser` 改为先用它取值再建 parser（**单一来源**，避免两份口径漂移）。
- `parse_level` 按 `spec.parse_level_family` 取 `_csg_parse_level` / `_gw_parse_level` / `_hdc10_parse_level`；`frame_type` 与 `channel` 同样取自现有读法（含 `csg_pb_frame_type_combo.currentData()`）。
- **必须在 UI 线程调用**（读了 widget），结果作为快照传给 worker。

### 4.2 `BatchFrameResult`（dict，键名与现状逐字兼容）

在 worker 内构造，经信号传回；**不持有 `_table_data`**：

| 键 | 现状锚点 | 说明 |
| --- | --- | --- |
| `_input` | 7580 | 帧 hex 串 |
| `_status` | 7581 | `成功` / `失败` / `异常`（与 9877 过滤口径一致，不得改字面量） |
| `_type_name` | 7583 | 协议/类型；**异常行也必须给值**（修 §1 附带缺陷） |
| `_src_line` | 7584 | 源日志行号 |
| `摘要` | 7586 | 由 `_get_summary_from_table_data` 生成 |
| `错误` | 7595 | 仅异常行 |
| `_has_detail` | 新增 | 该帧是否可以产出详情（= 解析成功且非空表） |
| `_frame_bytes` | 新增 | 原始帧字节，供详情按需重解析（49,532 × ~80 B ≈ **4 MB**） |

`_has_detail` 与 `_frame_bytes` 是「去缓存」后仍能一对一还原详情/导出的唯一依据。

### 4.3 `BatchParseWorker`（新增文件 `batch_parse_worker.py`）

沿用仓库既有线程范式（`serial_worker.py` + `thread_registry.py`）：

```python
class BatchParseWorker(QThread):
    progress = Signal(int, int, int, int, list)   # 已处理, 总数, 成功, 失败, 结果批次
    finished_ok = Signal(int, int)                 # 成功, 失败（全部完成）
    cancelled = Signal(int, int)                   # 成功, 失败（用户取消）
    failed = Signal(str)                           # 不可恢复错误（消息）
    def cancel(self): ...
```

- **分片粒度 200 帧**（≈ 78 ms）→ 取消响应远小于验收线 1 s。
- worker 内**不得触碰任何 widget**；所有 UI 读取都靠 §4.1 快照。
- parser 实例：`spec = protocol_registry.get_protocol(index)` → `base = parser_registry.get_parser_class(spec.parser_key)()` → `protocol_registry.build_gui_parser(index, base, parse_level=..., frame_type=..., channel=...)`。**不使用 `get_parser` 单例**（解析器带帧级可变状态 `_pb_size/_cmt_index/_pb_count`，与单帧页/实时监控共享会互相污染）。
- 摘要函数需在 worker 内可用：`_get_summary_from_table_data` / `_get_frame_type_name` 增加可选 `protocol_index` 形参（默认 `None` → 取 `self.current_protocol`，向后兼容），worker 传快照值，避免读主线程状态。

### 4.4 详情按需 `_get_frame_table_data(index) -> list`

1. 若 `batch_results[index].get("_table_data")` 存在 → 直接用（兼容旧路径/测试）。
2. 否则用锁存的 `_frame_bytes` + 快照解析参数重解析一次，写入 **LRU 缓存（上限 50 帧）**，返回结果。
3. 失败/异常帧返回 `[("❌ 解析失败", "", "", 错误文本, None, None)]`，与现状形态一致。

命中率预期：导出/查看集中在少数帧；冷帧单次重解析 0.39 ms。

### 4.5 「包含表格数据」列语义（防回归）

`enhanced_export.py:232` 现为 `"是" if "_table_data" in result else "否"`。去缓存后必须改为读 `_has_detail`：

- 解析成功 → `是`；失败/异常 → `否`。**与改动前的取值保持一致**，不得整列变「否」（写入本任务验收）。

### 4.6 过滤契约 `_on_batch_filter_changed`（9877）

- 状态过滤字面量不变（`success` / `fail` / `error` → `成功` / `失败` / `异常`）。
- 关键词匹配范围不变（`摘要` + 第 3 列「协议/类型」文本 + `_input`）。
- 提速手段：① 整段 `setUpdatesEnabled(False) / (True)` 包裹；② 行对象只取一次（`item(row,0)` 与 `item(row,3)` 缓存进局部变量）；③ 关键词输入 250 ms 去抖（`QTimer` restart 模式），状态下拉仍立即生效。
- 计数文案与「选中行被隐藏则选首条可见行」的行为保持不变。

### 4.7 收尾（完成 / 取消共用）

按现状顺序执行（7623-7645）：`_update_status_bar(success, fail, total)` → `_refresh_batch_type_combo()` + 清 `batch_selected_count` → 若 `rowCount() > 0` 则 `selectRow(0)` + `_on_batch_row_selected()`。

追加：时序图模型重建改为**在收尾时**触发（替代 `_generate_sequence_diagram` 依赖的解析中途状态）；恢复「批量解析」按钮与协议下拉的可用性；进度条置满或清零并显示取消文案。

---

## 5. UI 变更

- 位置：批量解析工具栏行（`batch_parse_btn` 所在行，`main_gui.py:2458` 附近连线）。
- 新增：`batch_progress_bar`（QProgressBar，setRange(0, total)，`setTextVisible(True)` 显示 `N / M`）+ `batch_cancel_btn`（「取消」，仅解析中可见/可用）+ 计数标签复用 `batch_filter_count` 或旁挂 `batch_parse_info`。
- 状态机：`空闲 → 解析中（进度条可见、取消可用、协议下拉与解析按钮禁用）→ 收尾（恢复）`。取消走同一收尾路径，额外置文案「已取消」。
- 拖入/打开文件路径（7238 触发）与手工点按钮路径共用同一状态机。

---

## 6. 线程安全与生命周期

- 全部 QThread 必须 `thread_registry.track(self, "批量解析")`（`AGENTS.md` 陷阱 20：`_shutdown_threads` 兜底回收依赖该注册表），且 `test/test_app_exit.py` 场景下不得残留。
- 退出/关闭窗口时若 worker 仍在跑：置取消标志 + `wait(2000)`；超时则记录并放弃引用（不得阻塞关闭）。
- 重复点击「批量解析」：解析中按钮已禁用，另有 `self._batch_worker is not None` 守卫；新任务前先取消旧任务。
- worker 与 UI 只通过信号交互；批次结果列表在 emit 后**不再被 worker 引用**（避免两侧同时改同一 list）。

---

## 7. 兼容与取舍

### 7.1 不做分页（已决策）

实测：229 MB 全在数据层、表格仅 13.3 MB；过滤慢的根因是重绘（一行 `setUpdatesEnabled` 即 0.02 s）；49,532 行填充 1.49 s。故分页**不解决任何已测痛点**，却要改动全选 / 右键定位 / 导出选中 / 时序图联动的行语义（与进行中的 `09-10-batch-snapshot-locate` 耦合）。→ 只修数据层。

### 7.2 剥离/清洗/提取保持同步

三者合计 1.46 s，且必须**同步可见**：`_batch_lead_lines`、`_last_strip_line_map`、`_set_batch_snapshot` 在解析前就要就绪，摘要行号（`src_line`）与「转到原始报文位置」都依赖它们。线程化会引入「快照未就绪但已开始解析」的竞态，收益远小于 19.3 s 的解析段。

### 7.3 详情按需的取舍

- 收益：常驻内存 229.4 MB → 约 4 MB（帧字节）+ LRU 50 帧详情。
- 代价：查看/导出冷帧需重解析（0.39 ms/帧；导出 49,532 帧详情 ≈ 19 s，与现状导出耗时同量级，因为现状导出也要遍历 229 MB）。
- 若将来需要「导出全量详情」提速，走流式写出（另属 `09-15-web-parse-perf` 的桌面对应项），不在本任务。

### 7.4 行号 / 快照语义不变

`Qt.UserRole` 存 `batch_results` 索引（7613）的机制不变；分批 append 只会让行数单调增长，行↔索引映射在任意时刻都成立。取消时已填行的映射同样成立。

---

## 8. 风险与回滚

| 风险 | 缓解 | 回滚点 |
| --- | --- | --- |
| 后台化破坏行号/快照语义 | §7.2 保持同步；回归 `test/test_batch_snapshot_locate.py` | 提交 1（仅重构预处理，不改线程） |
| 去缓存导致导出/详情字段缺失 | `_has_detail` + `_frame_bytes`；导出逐字段对拍 | 提交 3 独立可回滚 |
| 取消后状态机卡死 | 完成/取消共用收尾函数；测试覆盖两条路径 | 提交 2 |
| 线程残留导致关不掉 | `thread_registry` + `wait()`；`test/test_app_exit.py` | 提交 2 |
| 过滤去抖导致输入迟滞 | 250 ms 且状态下拉立即生效；测试断言最终态 | 提交 4 |

实施按 4 个独立提交推进（见 `implement.md`），任一提交失败可单独 `git revert`。

---

## 9. 验证策略

- **纯逻辑**：`BatchParseWorker` 的分片/取消/异常隔离可在无 GUI 环境下用假 parser（`parse_to_table` 抛异常/返回空表/正常）直接驱动。
- **内存**：`tracemalloc`（或对 `batch_results` 取 `sys.getsizeof` 递归近似）断言 < 40 MB（49,532 帧）。
- **UI 响应性（offscreen）**：解析中注入 `QTimer(0)` 心跳，断言心跳次数 ≥ 阈值（证明事件循环未被阻塞）。
- **取消**：发起后计时，断言 < 1 s 停止且已完成结果可读。
- **过滤**：`QTest`/直接调用，断言单次 < 0.2 s（阈值放宽避免 flaky），并断言过滤结果集合与旧实现一致（对拍）。
- **导出**：改动前后对同一样本导出 JSON/CSV，逐字段 diff。
