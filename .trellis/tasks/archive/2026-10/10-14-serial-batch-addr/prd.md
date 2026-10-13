# 串口工具：批量替换通信地址（按协议替换地址域 + 重算校验）

## Goal

串口工具现场最常见的流程是「**加载一批报文 → 发给某台表计**」。报文里的通信地址是别人的表号，
用户目前只能**逐条手工改地址并重算校验**（改错一位整帧无效，且校验必须跟着变）。

本次给串口工具加一个**批量替换通信地址**的动作：勾选（或全部）命令 → 对话框里选协议 + 填地址
→ 一次性把每条命令的发送数据按该协议**替换地址域并重算校验**，结果逐条可查、**可撤销**。

用户本轮已确认的三条口径（问答）：

| 项 | 决定 |
|---|---|
| 任务 | 建 Trellis 任务并进入规划 |
| 协议来源与作用范围 | **对话框里选协议**（不是逐条读命令的协议列）+ 可选「同时把协议写入这些命令的『协议』列」；作用范围 = **勾选的命令**（无勾选 = 全部） |
| 预期响应 | **同时替换**：能通过「结构 + 校验」自证的才替换，失败保持原样并提示 |

## 现状证据（实现必须与此一致）

- 地址替换引擎**已存在**且已被蓝牙页使用（无需新写偏移/算法）：
  `frame_addr_fix.py`（纯逻辑、无 Qt、协议模块按需导入）—— `SUPPORTED_PROTOCOLS = (0, 6, 7, 8, 13, 14)`，
  `fields_for(protocol) -> AddrField[]`（字段标签/写法提示/在线长度）、
  `parse_address(text, field, on_wire_length)`、`apply(frame, protocol, values) -> FixResult(ok, frame, notes, error)`
  （`notes` 含「地址域 … → …」「校验和 0xAA → 0xBB」）。
- 串口命令记录结构：`{name, data_hex, match_type, match_hex, protocol, enabled, send_count}` ——
  `normalize_command`（`serial_tool_widget.py:579-624`）、`export_commands`（`:641-655`）。
- **「加载报文文件」导入的报文 `protocol=None`**（`_load_message_file:2860-2868`，写死 `"protocol": None`）
  ⇒ 批量替换必须由对话框指定协议（这正是「按对应协议替换」的入口）。
- 命令表勾选列 + `_checked_rows()` / `_set_all_checkboxes` 已存在（`:2726-2742`、`:2712`）；
  期望响应的匹配方式 `MATCH_TYPES`（`:49-57`，含 `regex` / `hex_wildcard` / `none`）。
- 命令按钮行 `cmd_btns`（`:1736-1761`，当前 8 个按钮：添加/编辑/删除/上移/下移 + 保存配置/加载配置/加载报文文件）。
- 前导 FEH：**只有协议 8（DL/T 698.45 §6.3.1 b）与协议 6（DL/T 645 §5.3.1）有规范依据**；
  `wakeup_prefix.py` 是唯一实现，`serial_tool_widget.py` 已在白名单（`test/test_wakeup_fe_prefix.py:453-463`）。
- 门禁：`release_check.py:CORE_TESTS`；窄窗按钮裁字判据 `btn.width() >= btn.sizeHint().width()`（AGENTS §8 陷阱 63，
  在 `show()` 之后量，且只设 `minimumWidth` 不设上限）。

## Requirements

### R1 纯逻辑编排层（`serial_tool_widget.py` 纯逻辑段，无 Qt）

- R1.1 `batch_fix_commands(commands, indices, protocol_index, values, write_protocol=True, fix_match=True)
  -> List[AddrBatchItem]`：**不修改入参**（只读 `commands` / `indices`），逐条返回「新值 / 原因」，
  由 GUI 负责写回（撤销点 = GUI 在写回前抓的快照）。
- R1.2 每条命令的结果三态：
  - `ok` —— 替换成功，`data_hex` 为新帧；
  - `kept` —— 尝试了但失败：**原样保留** + 可读 `error`（结构/校验自证不过、地址写错、协议不支持…）；
  - `skipped` —— 不该处理（`data_hex` 非法）。
- R1.3 前导 FEH：协议 6 / 8 先按 `wakeup_prefix.strip_wakeup_prefix` 剥离再 `apply`，成功后**原样恢复**前导字节；
  **其余协议不剥离**（规范无依据，带 FE 就该报错，不得「救活」本应失败的帧）。
- R1.4 `write_protocol=True`：把 `protocol_index` 写入**作用范围内所有命令**的协议列
  （与单条替换成败无关 —— 「这批报文属于协议 X」是用户声明；写协议列的目的是让 RX 能按该协议断帧解析）。
- R1.5 `fix_match=True`：仅当 `match_type ∈ {contains, equals, starts_with, ends_with}`（`HEX_MATCH_TYPES`）
  且 `match_hex` 能解析成字节时**尝试**替换；**能自证才写回**，不适用（通配/正则/不匹配）或自证失败
  一律保持原样，并在 `notes` 里说明原因（不得静默改坏匹配规则）。
- R1.6 任何异常都必须转成该条的 `kept` + 可读 error，**不得抛出中断整批**。

### R2 GUI（命令表按钮行 + 对话框 + 撤销）

- R2.1 命令按钮行新增「替换地址」→ 打开 `BatchAddrDialog`。
- R2.2 对话框内容：
  - 协议下拉：`frame_addr_fix.supported_choices()`（`[0] 南网` … `[14] 南网上行`）；
  - 地址输入区：按所选协议**动态生成**（`fields_for`，标签/占位提示来自字段声明，界面不硬编码协议细节）；
  - 作用范围下拉：「勾选的命令（N 条）」/「全部命令（M 条）」，默认「勾选」；**无勾选时默认「全部」**；
  - 复选「同时把协议写入这些命令的『协议』列」（默认勾选）；
  - 复选「同时替换『预期响应』中的地址」（默认勾选）；
  - 提示行：`将写入 N 字节：xx xx …`；能取到作用范围内第一条可解析帧时给出**替换预览**
    （`apply` 的 notes；失败则显示可读错误），让用户点确定前就看见会发生什么。
- R2.3 确定前校验：选了协议就必须填地址，且每个字段都要 `parse_address` 通过
  （长度优先按帧内推导，推导不到时按字段声明长度），否则拦下并说明原因。
- R2.4 执行顺序：抓撤销快照 → 写回 `data_hex`（+ 可选协议列 / `match_hex`）→ 重建表格 → `_schedule_save()`
  → **日志逐条**（`[地址] 名称：<notes 或原因>`，明细最多 20 行，其余汇总为「另有 N 条见汇总」）
  → **汇总弹框**（成功 / 保留 / 跳过 计数 + 每类前 3 条原因）。
- R2.5 **撤销**：汇总弹框内有「撤销本次替换」按钮 → 把**这一批**命令恢复到替换前的 5 个键
  （`data_hex` / `protocol` / `match_hex` / `match_type` / `enabled` 中实际被改动的项），并写日志；
  一次替换只保留一个撤销点（再次替换即覆盖）。
- R2.6 没有作用对象、或全部 `kept`/`skipped` 时，必须明确告知原因且**不改动任何命令**（不许「点了没反应」）。

### R3 测试

- R3.1 新增 `test/test_serial_addr_fix.py`（纯逻辑，脚本式 `check()`）：
  - **六协议真帧 oracle**：替换后 ① 地址字节 = 期望（含字节序）② **该协议校验器 0 fail**
    ③ 非地址字节未被改动；
  - 前导 FE：协议 8/6 带 `FE FE FE FE` → 替换成功且前导保留（校验器 0 fail）；协议 0/7/13/14 带 FE → `kept`；
  - `write_protocol` 开/关；`fix_match` 四类（可自证整帧 / 片段 / 通配 / 正则 / 失败）；
  - 作用范围与混合协议：`protocol=None`、非法 `data_hex`、空 `values`、地址非法、协议不支持（9/10/11/12）；
  - `batch_fix_commands` **不修改入参**（逐键对比快照）；
  - **变异反证**（实施阶段做，逐条变红后逐字节还原）：去掉校验重算 / 不恢复前导 FE / 无条件覆盖 `match_hex`。
- R3.2 `test/test_serial_tool_widget.py` 新增段 [35]（offscreen）：
  按钮存在且 `width >= sizeHint`（未设上限）、对话框按协议生成字段行、预览提示、执行后表内
  HEX / 协议列 / 预期响应变化、撤销恢复、落盘回读、汇总计数文案、`protocol=None` 批量场景。
- R3.3 `test/test_serial_addr_fix.py` 登记进 `release_check.py:CORE_TESTS`（只提交自己那几行）。

## Acceptance Criteria

- A1 载入 3 条真实 645 报文（`protocol=None`）→ 勾全选 → 替换地址为 `000000000033`：
  表内 3 条 HEX 的地址域变为 `33 00 …`（低字节在前）且 CS 正确（`DLT645Validator` 0 fail）、
  协议列变为 `[6] DLT645`；日志出现「地址域 …」与「校验和 0x… → 0x…」。
- A2 同一批里混入一条南网帧：该条 `kept` 并给出可读原因，其余仍成功；汇总计数 = 成功/保留/跳过。
- A3 协议 8 带前导 `FE FE FE FE` 的报文：替换后前导字节仍在，HCS/FCS 重算且 `DLT69845Validator` 0 fail。
- A4 「预期响应」为可自证整帧时地址同步替换；写成 `68 D0` 片段 / `XX` 通配 / 正则时保持原样并在汇总里说明。
- A5 点「撤销本次替换」：这批命令恢复到替换前（逐字节一致），其它命令不受影响。
- A6 取消勾选「同时把协议写入协议列」→ 命令的协议列保持原值。
- A7 `PYTHONIOENCODING=utf-8 python release_check.py --with-gui` → FAIL=0（既有环境红除外）。

## 非目标

- 不做协议 9/10/11/12（`frame_addr_fix` v1 不支持，逐条给可读原因）。
- **不改 `frame_addr_fix.py`**（复用，禁止第二套偏移/算法/校验表）；前导 FE 的处理放在本任务的批量层，且只对 6/8 生效。
- 不做「改变地址长度」（改长度要连带改 L / HCS / FCS 与 698 地址长度特征位）。
- 不做「发送时替换」（本功能是**写回表内数据**；蓝牙页那套发送时套用不在串口页重复）。
- 不改 Web 版（Reflex 无串口工具的这套命令表）。
