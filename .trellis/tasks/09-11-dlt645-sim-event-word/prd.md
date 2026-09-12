# 645虚拟表 事件状态字随机变化

## Goal

645虚拟表当前**读不出事件状态字**：档案里没有该数据项，且引擎的 DI 类型解析拿不到类型，把 12 字节的 `BS96` 当 4 字节数值回。本任务让虚拟表：

1. 档案默认就带「事件状态字」数据项（默认全 0 = 无事件、读多少遍都一样）；
2. 新增「模拟设置 · 随机产生事件」开关：**勾选后，每次读取事件状态字都返回一个新的随机 12 字节值**（用于验证载波模块/集中器对事件状态字变化的处理）。

## Confirmed Facts（代码/文档/实测证据）

- **「事件状态字」= DI `04001501` 主动上报状态字**：`dlt645_di.json` 中 `BS96`（=12 字节）的只有 `04001501 主动上报状态字` 与 `04001503 复位主动上报状态字`（`04000501~04000507 电表运行状态字1~7` 为 `BS32`=4 字节）。用户已确认取 `04001501`、12 字节。
- **手册情境印证**：`协议文档/7.国网本地接口协议/附件1.md:214`「模块检测到引脚有事件时，**主动读取电能表的事件状态字**上报给集中器」。
- **真实抓包印证**（`山东和兑智能.txt` L577-789，模块约每 20~30s 轮询一次）：请求 `68 33 00 00 00 00 00 68 11 04 34 48 33 37 FE 16` → 数据域去扰 `01 15 00 04` = DI `04001501`；应答 `… 91 13 34 48 33 37 DD 34 DD 33 … 34 E0 16`。该表应答数据域 15 字节（厂商扩展），本任务按 DI 表标准取 12 字节（用户已确认）。
- **当前缺陷（实测）**：`engine._data_type_for("04001501")` 返回 **None**（`dlt645_di_lookup` 的真实方法名是 `get_di_info`，而引擎探测的是 `get_info`/`get`/`lookup` → 全部不存在），于是回落到 `"XXXXXX.XX"`。实测：请求 04001501 得到 `68 33 00 00 00 00 00 68 91 08 34 48 33 37 33 33 33 33 4E 16` → **L=0x08（4 字节）而非 0x10（4+12）**，且 `dlt645_parser` 读成 `00000000`、说明为「格式BS96」——即数据被截断。故本任务必须一并修复类型/长度解析。
- **DI 类型权威来源**：`dlt645_frame_schema.get_di_info(di)` → `{'name','unit','data_type','length'}`（实测 `04001501 → BS96 / 12`），组帧路径 `_encode_di_value` 已用 `nbytes=info["length"] or nbytes` 的同口径。
- **编码口径**：`dlt645_data_codec.encode_value(value, "BS96")` → `parse_hex(value, 96//8)`，档案值填 24 位 hex（12 字节）。
- **引擎每帧重建**：串口线程在收帧循环里 `engine = self._engine_factory()`（`dlt645_meter_sim_widget.py:118`），离线每次 `_make_engine()`；`_make_engine` 读 `self.address` / `self.archive` 构造 `DLT645MeterSim`。**所以「上次随机值」这类跨帧状态不能放在引擎实例上**，必须由 GUI 持有一个可复用的产生器对象并注入。
- **持久化**：`dlt645_sim_data.json` 目前为 `{"address": ..., "values": {...}}`，由 `_archive_save` / `_archive_save_quiet` 写、`_load_archive_file` 读、`_archive_export`/`_archive_import` 走同一结构；`DLT645Archive.__init__` 先铺 `DEFAULT_ARCHIVE` 再用传入值覆盖 → **新增默认项对已有用户档案自动生效**。
- 现有测试：`test/test_dlt645_sim.py`（引擎 11H/13H/15H/08H 与异常应答）、`test/test_dlt645_sim_lme_query.py`（95 项，含 COM1↔COM2 回环）。

## Requirements

### R1 修复事件状态字的类型/长度解析（前置，否则随机也无意义）
- `dlt645_sim/engine.py`：类型解析改为优先 `dlt645_frame_schema.get_di_info(di_code)`（取 `data_type` 与 `length`），失败再回退既有快表；`encode_value(..., nbytes=length or None)`，与 GUI/Web 组帧路径同口径。
- 判定：请求 `04001501` → 应答 `L=0x10`（4 字节 DI + 12 字节数据），`dlt645_parser` 读回数据值长度为 12 字节。

### R2 档案默认含事件状态字数据项
- `dlt645_sim/archive.py::DEFAULT_ARCHIVE` 增 `"04001501": "000000000000000000000000"`（12 字节全 0 = 无事件，**每次读取都一样**）。
- 已有 `dlt645_sim_data.json`（无该项）经 `DLT645Archive` 默认铺底后自动具备该项；「档案数据」页表格随之出现该行。

### R3 随机事件状态字产生器（纯逻辑，无 Qt）
- 新 `dlt645_sim/dynamic_data.py`（对齐 `meter_sim/dynamic_data.py` 命名）：
  - `EVENT_WORD_DI = "04001501"`、`EVENT_WORD_BYTES = 12`
  - `class RandomEventWord`：`next_value() -> str` 返回 **24 位十六进制**（12 字节）随机值，且**保证与上一次返回值不同**（重抽，避免"随机到相同值"被误判为没有变化）；`rng` 可注入（测试可播种/注入碰撞桩）。
- `dlt645_sim/engine.py::DLT645MeterSim.__init__` 增 `event_word_source=None`（无参可调用，返回 hex 字符串）；`_handle_one` 在 11H 读数据分支：`di_code == EVENT_WORD_DI 且 event_word_source 非空` → 值取 `source()`（绕过档案），并在 `last_error` 之外新增 `last_note`（如「随机事件状态字」）供 GUI 日志标注。
- 产生器异常（如返回非法长度）→ 不崩，回落档案值并在 `last_error` 记录。

### R4 GUI（运行页新增「模拟设置」小节）
- 位置：运行页「串口从站」与「模块版本查询」之间；内容：`QCheckBox("随机产生事件")` + 说明标签（默认不勾：读档案值，12 字节全 0 不变；勾选：每次读取 04001501 都返回新的随机 12 字节值）。
- `_make_engine()`：勾选时注入 `event_word_source=self._event_word.next_value`，未勾选注入 `None`。
- 勾选状态持久化到 `dlt645_sim_data.json`（新增 `"random_event": bool`）：`_archive_save` / `_archive_save_quiet` 写、`_load_archive_file` 读、`_archive_export` / `_archive_import` 同步（导入可选字段，缺失按 False）。
- 日志标注：离线「生成响应」与串口应答路径在随机生效时输出一行「（随机事件状态字 04001501 = …）」到收发日志，便于肉眼确认「每次读取都变」。
- 串口与离线两条路径共用 `_make_engine()`，勾选开关两边同时生效。

### R5 测试（新增 `test/test_dlt645_sim_event_word.py`）
- 引擎契约：请求 `04001501` → 应答 `L=0x10`、DI 正确、数据 12 字节；`DLT645Parser` 读回数据值长度 12；帧 CS 自洽。
- 默认不变化：连续读 3 次，应答数据域逐字节相同，且为全 0（无事件）。
- 随机模式：连读 20 次 → 每次数据 12 字节、长度域合法、相邻两次**互不相同**、至少一次非全 0；注入 `rng` 使随机可复现。
- `RandomEventWord` 单测：返回 24 位合法 hex、长度 12 字节、与上次不同（注入"必定碰撞一次"的桩验证会重抽）。
- 异常容错：`event_word_source` 抛异常 → 回落档案值、不抛栈、`last_error` 有说明。
- offscreen GUI：`模拟设置` 小节与勾选框存在且默认不勾；勾选后 `_make_engine().event_word_source` 非空；离线连点两次「生成响应」得到**不同**的响应帧；勾选状态保存后重载（新建 widget）仍为勾选。
- 回归：`test/test_dlt645_sim.py`、`test/test_dlt645_sim_lme_query.py`、`test/test_dlt645_lme.py`、`test/test_dlt645_frame_gen.py`、`test/test_dlt645_frame_gen_gui.py` 全过。
- 本机有虚拟串口对（ELTIMA COM1↔COM2）时做端到端：勾选后经 COM2 连发两次 04001501 读请求 → 两次应答数据不同；无串口对则打印 `[SKIP]`（不计失败）。

### R6 文档
- `main_gui.py`：`APP_VERSION` → `1.23.8`，`CHANGELOG` 顶部新增 1.23.8 条目（含 R1 修复说明），同步 `python release_check.py --sync-iss`。
- `AGENTS.md`：§3 目录树补 `dlt645_sim/dynamic_data.py`、§5.4 补「事件状态字 04001501（BS96 12B）/ 随机产生事件开关」、§7 测试清单补 `test/test_dlt645_sim_event_word.py`。

## Acceptance Criteria

1. 档案默认含 `04001501`（12 字节全 0）；不勾选时连续读取应答**完全一致**且 L=0x10（12 字节数据，不再是 4 字节截断）。
2. 勾选「随机产生事件」后，每次读取 `04001501` 都返回**不同的** 12 字节随机值（连续 20 次断言相邻不同）；离线与串口两条路径都生效。
3. 随机值经 `DLT645Parser` 可正常解析（DI=04001501、BS96、12 字节、CS 合法），不破坏既有 11H 读档案、13H/15H 地址、08H 校时与异常应答行为。
4. 勾选状态可持久化：保存后重启（新建 widget）仍保持；导出/导入 JSON 保留该字段。
5. `python test/test_dlt645_sim_event_word.py` 全过；4 个既有 645 测试脚本与 `test_dlt645_sim_lme_query.py` 无回归。
6. `APP_VERSION` = 1.23.8、CHANGELOG 有对应条目、AGENTS.md 已同步。

## Out of Scope

- `04001503 复位主动上报状态字`、`04000501~04000507 电表运行状态字1~7` 不做随机化（用户已确认仅 04001501）。
- 随机值不按位定义约束（不追求"像真表的事件组合"），为 96 bit 全随机；不跟随实测 15 字节厂商扩展。
- 不改 645 解析器 `dlt645_parser.py` / `dlt645_data_codec.py` / `dlt645_frame_gen.py` / `dlt645_frame_schema.py` 的既有签名与行为（只复用 `get_di_info`）。
- 不做"事件状态字按事件类型自动置位/定时翻转"等更复杂模拟；不改 698 虚拟表与 LME 下发功能。

## Risks / Deferred

- **实测表应答 15 字节**（山东和兑，`L=0x13`）：本任务按 DI 表标准 12 字节实现（用户确认）。若后续要仿该表，只需改档案默认值长度 + `EVENT_WORD_BYTES`，解析侧 `BS96` 仍按 12 展开。
- **`nbytes=length` 的口径变化**会同时作用于其它 DI 的应答编码：现网档案值多为标准长度，风险低；测试用既有 `test_dlt645_sim.py` 全量回归兜底，若有 DI 因声明长度与掩码不一致而变化，逐项核对后再决定是否只对 `BS*` 生效。
- 随机值不落档案（不回写 `dlt645_sim_data.json`），避免污染用户档案；仅在日志留痕。
