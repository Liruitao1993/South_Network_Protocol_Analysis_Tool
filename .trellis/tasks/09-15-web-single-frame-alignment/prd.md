# Web 单帧解析能力对齐（字节定位 / 深度解析 / 解析开关 / 查询页 CRUD）

## Goal

补齐 Web 单帧解析相对桌面的交互与解析开关能力，使用户能在 Web 上完成「字段 ↔ 字节」核对、子帧二次深度解析、按其他协议重解，以及查询页自定义条目的增删（父任务 `research/web-parse-audit.md` §2/§3）。

依赖：`09-15-web-parse-p0-fixes`（gx 自动识别、mac_only、kwargs）、`09-15-web-shared-parse-core`（字段层级与查询数据源单源化）。

## Confirmed Facts

- 字节范围被丢弃：`reflex_web.py:643-668` 只取 `row[0..3]`；桌面保留 `_byte_ranges` 并做点行高亮（`main_gui.py:10138-10168/10170-10219`）。
- 无深度解析入口：桌面双击行 → `_extract_apdu_reparse`（`main_gui.py:10221-10284`：协议11 `hdc10_parser`、10/9 `gw_new_gen`、8/9 分支、645 LME、默认 HDLC APDU）。
- 协议9 无通道下拉（`main_gui.py:1468-1481` 有 auto/plc/hrf；Web 无 `set_csg_channel`），无「4 字节反转」（`main_gui.py:5292-5298`），无「按其他协议重解析」（桌面弹窗 `6929-6982`）。
- 字段层级口径不同：Web `indent=(len-lstrip)//2`（`reflex_web.py:646-667`）vs 桌面 `_field_level_map` 归一化 + `_format_tree_field`（`main_gui.py:872-896`，4 空格/级）→ 使用 4 空格缩进的解析器（如 `gw_new_gen_parser`）在 Web 层级偏深。
- 查询页写侧缺失：南网 DI / 645 DI / 国网 AFN / OBIS 自定义标记 4 处只读；桌面走 `custom_di_store`（`main_gui.py:2231/2236` 读、`_add_custom_di/_del_custom_di` 写）、`dlt645_di_lookup.add_custom_di`、`gdw_custom_afn.json`；Web `_search_dlt645_di` 只用前 5 列丢 `is_custom`（`lookup_utils.py:187-193`），OBIS 访问属性恒 `-`（`164-171`）。
- 组帧写侧：Web 无串口下发/收帧回读、645 长度告警与广播地址联动（`frame_gen_widget.py:1617-1825/3846-3867`）。

## Requirements

### R1 字节范围与高亮

- State 保留 `row[4]/row[5]`（`byte_start/byte_end`）到结果行 payload；前端点击结果行 → 选中/高亮报文输入框对应字节区间（textarea 选区实现，跨行帧按 hex 字符区间换算）。
- 解析失败/无范围行不参与高亮（`None` 语义与桌面一致）。

### R2 选中行深度解析

- 新增「深度解析选中行」动作：按当前协议分派到桌面同款目标（协议11 → `hdc10_parser`；10/9 → `gw_new_gen_parser`；8 → 698 APDU；6 → `DLT645Parser`；2/3/4/5 → `hdlc_parser.parse_apdu_to_table`），结果以弹窗/展开面板展示。
- 分派表以**共享核心或注册表**的一处映射表达；禁止在 Web 再写一份按索引的 if/elif（若共享核心尚未提供该映射，本任务补上并让桌面复用）。

### R3 解析开关

- 协议9 通道下拉（auto/plc/hrf）并下发 `channel`。
- 协议9「4 字节反转」勾选（纯函数复用桌面 `_reverse_4byte_groups` 语义，抽到共享核心）。
- 「按其他协议重解析」：结果区提供协议切换重解（复用既有 `current_protocol` + parse 流程）。
- ED 包装格式选择器（auto/plc2/gx）：P0 已实现 parser 自动识别，本任务补 UI 显式选择（下发 `ed_wrapper`）。

### R4 字段层级口径统一

- 采用共享核心的层级归一化 + 树形前缀渲染，Web 与桌面显示层级一致。

### R5 查询页 CRUD 与标记

- 南网 DI：增/删自定义 DI（复用 `custom_di_store`，与桌面同一份 `custom_di.json`）、内置条目拒删、重复覆盖确认、多选批量删除（与桌面 1.23.11 行为一致）。
- 645 DI：增/删自定义 DI（`dlt645_di_lookup.add/delete_custom_di`），列表显示 `is_custom` 标记。
- 国网 AFN：增/删自定义 AFN+Fn（`gdw_custom_afn.json`）。
- OBIS：显示自定义标记与访问属性（`obis_lookup` 的 `is_custom`）。
- 所有查询页在协议切换后自动刷新（现 `set_protocol` 不刷新查询，`reflex_web.py:336-352`）。

### R6 组帧写侧（可选，按成本决定）

- 645 组帧长度告警与广播地址联动（桌面 `frame_gen_widget.py:1754-1825/1617-1739`）。
- 串口下发/收帧回读**不在 Web 范围**（浏览器无法直连串口）；如需要，明确记为不实现并在 UI 上说明。

## Acceptance Criteria

1. `test/test_web_single_frame_alignment.py`（新增，登记 `CORE_TESTS`）：字节范围保留（纯函数/State 级）、层级归一化对拍桌面、深度解析分派对每个协议返回非空行、通道与 4 字节反转纯函数、查询页 CRUD（沙箱 `app_paths` 数据目录，零污染）与协议切换刷新。
2. 查询页 CRUD 与桌面共用同一份 JSON：Web 增删后桌面读到同样结果（双向验证，复用 `test_nanwang_custom_di.py` 的沙箱范式）。
3. `python release_check.py` 无 FAIL。
4. `AGENTS.md §6/§7`、`CHANGELOG` 同步。

## Out of Scope

- Web 端直接串口通信（浏览器能力限制）；虚拟表/监控/时序图/档案/拓扑。
- 前端视觉改版（弹窗样式除外，深度解析结果需要可读容器）。

## Risks / Deferred

- 自定义 DI 的 Web 写路径会改 `custom_di.json`（服务端文件）→ 多用户并发写入需串行化（单进程单事件循环下天然串行，但需在实现中确认 Reflex 状态层的调用模型）。
- 深度解析的字节提取依赖 `row[4]/row[5]` 的准确性（多物理块重组后的偏移已在桌面 `_concat_segments` 处理过，Web 需同样的偏移翻译）。
