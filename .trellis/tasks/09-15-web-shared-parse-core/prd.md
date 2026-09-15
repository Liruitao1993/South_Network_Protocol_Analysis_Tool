# 共享解析核心抽取 + 接入协议注册表

## Goal

把「预处理 / 帧提取 / 摘要 / DLT645 dict→表格 / 字段层级」从「两端各写一份」收敛为**一份无 Qt 实现**，并让 Web 通过 `protocol_registry` / `parser_registry` 消费协议能力，从而消除 ≈145 处硬编码协议分支与已发生的漂移（父任务 `research/web-parse-audit.md` §4）。

依赖：必须在 `09-15-web-parse-p0-fixes` 之后执行（P0 已把 `web_utils` 的判据抽成纯函数并做了一次 ED 打分下沉）。

## Confirmed Facts

- Web 侧 `grep protocol_registry|parser_registry` = **0 命中**；`reflex_web/reflex_web/reflex_web.py` 单文件协议索引字面量 ≈105 处（清单见 research §4）。
- 已漂移的复刻体：`strip_gw_new_gen_prefix`（Web 33 行 vs 桌面 87 行含 `fc_payload_data` 跨行状态机）、`strip_csg_new_gen_prefix`、`extract_frames_for_protocol`（返回契约不同：纯字符串 vs `(hex, ed_type, line_no)` 三元组）、摘要分派与摘要主体、`get_hdc10_summary`（本仓别处不存在）。
- 仅「复制但当前一致」的复刻体：`_safe_parse_to_table` 的 DLT645 分支（`reflex_web.py:483-529` ↔ `protocol_registry.DLT645GuiParser:355-404`）、`APDUParserWeb`/`WrapperParserWeb`（`reflex_web.py:436-453` ↔ `protocol_registry.py:331-352`）、`_get_validator` 的 12 项 dict（P0 已改为 `make_validator`）。
- `protocol_registry.py` 只依赖 `dataclass/typing/importlib`（无 Qt），Web 可直接 import；`parser_registry.get_parser` 提供模块级共享实例（`parser_registry.py:47-54`）。
- 桌面 `main_gui.py:8334-8370` 的 `_extract_frames_for_protocol` 由 `spec.extract_strategy` 驱动。

## Requirements

### R1 抽取无 Qt 共享核心

- 新模块（建议 `batch_core.py`，或作为 `protocol_registry` 的兄弟模块；最终选择写进 `design.md`）：承载 `clean_hex_input` / `strip_csg_monitor_prefix` / `strip_csg_new_gen_frame_prefix` / `strip_gw_new_gen_prefix` / `extract_frames_for_protocol` / 摘要（`_get_summary_from_table_data` 全部分支）/ `DLT645GuiParser` 等价转换 / 字段层级归一化（`_field_level_map` + `_format_tree_field`）。
- 桌面 `main_gui` 与 Web `web_utils` 一律改成调用共享核心；**Web 侧删除被取代的复刻函数**，桌面侧删除对应私有实现（保留必要薄壳，如 GUI 行号映射/快照仍留在 `main_gui`）。
- 行号/ED 类型等桌面专属信息以**返回结构**表达（如 `FrameExtract(hex, ed_data_type, line_no)`）而非两套函数签名。

### R2 Web 接入注册表

- 协议下拉 → `protocol_registry.combo_labels()`；解析器 → `parser_registry.get_parser(spec.parser_key)` + `protocol_registry.build_gui_parser(...)`；校验器 → `make_validator`；提取策略 → `spec.extract_strategy`；查询页 → `spec.lookup_kind`；组帧/预设 → `spec.frame_gen_mode`/`preset_mode`；Tab 可见性 → `has_*` 标志。
- Web 的 `PROTOCOL_OPTIONS` / `FEEDBACK_PROTOCOL_OPTIONS` 收敛为一份（反馈页协议名可由同一源生成）。
- 摘要分派通过 `spec` 新增字段（如 `summary_kind`）表达，禁止再按索引 `if/elif`。

### R3 桌面/解析器缺陷同修（本任务范围内）

- 桌面批量失败判定口径偏窄（`main_gui.py:7555-7557` 只认 `❌ 解析失败`）→ 统一为「以 `❌` 开头的行」（P0 任务已在**两侧**统一，本任务只需保持共享核心里的单一实现）。
- 桌面 parser 实例跨帧共享导致的有状态污染（`csg` 的 `_channel`/`_concat_segments`/`_pb_size`）评估并按需改为按帧复位或按帧新建（`csg_new_gen_parser.py:654-661` 已有部分复位）。
- **新增（P0 实施中发现，parser 层缺陷，两端共享）**：`gw_new_gen_parser.parse_to_table` 的「直接网络管理消息」早返回（`gw_new_gen_parser.py:179-183`）位于 `parse_level` 分派**之前**，因此显式指定 `pb_only`/`mac_only`/`app` 的输入只要前 4 字节形如 `MMTYPE + 00 00` 就会被当作管理消息解析（实测 `PBH=0x01` 的 PB 输入 → 返回 MME 行、`解析模式`/物理块行全部消失）。显式级别应先于「自动识别」类判定，符合 AGENTS §8.19「输入即 PB/MAC 契约」。修复时须回归 `test/test_gw_new_gen.py`、`test/test_gw_batch_parse.py`、`test/test_gw_parse_levels.py`。

### R4 对照测试（拦漂移）

- 新增 `test/test_web_desktop_parity.py`：同一份输入（监控日志前缀 + 跨行 payload + ED gx/plc2 混排 + 各协议真实帧）下，断言 Web 与桌面**摘要文本逐字相等、帧提取结果相等**（范式：`test/test_csg_summary.py` 的 Host 未绑定方法写法）。
- 清理测试侧复刻：`test/test_csg_batch_prefix.py:19-48`、`reflex_web/tests/test_csg_ed_control.py` 不得再各写一份实现，改为引用共享核心。

## Acceptance Criteria

1. `reflex_web/` 中不再存在与桌面重复的沉淀/提取/摘要实现（同一逻辑只有一份，位于无 Qt 共享模块）；`grep` 可验证。
2. Web 协议索引硬编码分支从 ≈145 降到「注册表驱动 + UI 可见性表」（目标 ≤30，剩余项须在 `design.md` 中逐条给出理由）。
3. `test/test_web_desktop_parity.py` 对拍全过（摘要逐字相等、提取结果相等）。
4. 桌面既有套件全过：`test_csg_*` / `test_gw_*` / `test_hdc10.py` / `test_batch_src_line_jump.py` / `test_batch_snapshot_locate.py` / `test_csg_sequence_model.py`。
5. `python release_check.py` 无 FAIL；新测试登记 `CORE_TESTS`。
6. `AGENTS.md §3`（新增共享模块）、`§6`（协议集成点：Web 也走注册表）同步。

## Out of Scope

- Web 端未实现的桌面功能（虚拟表/档案/拓扑/监控/时序图/频谱图）。
- 前端 UI 结构改造（除协议清单来源变化外）。

## Risks / Deferred

- **桌面回归面大**：`main_gui.parse_batch` 与 Web 同时切换实现，必须分步落地（先共享核心并让桌面切过去、跑全量套件，再切 Web），每步单独可回滚。
- **行号映射与快照**属桌面专属，抽取时不要把 `batch_source_view` / `_last_strip_line_map` 一起搬进共享模块（Web 无此能力），以返回结构解耦。
