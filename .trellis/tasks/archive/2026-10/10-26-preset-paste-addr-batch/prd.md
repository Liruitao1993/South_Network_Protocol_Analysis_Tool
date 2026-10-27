# 预设命令页：粘贴报文添加按钮 + 按协议一键批量替换地址

## Goal

预设命令页目前只能**看/发/删**：新增预设必须绕到「协议组帧」页点「添加到预设」；换表号只能逐条重建报文
（预设存的是完整 HEX，改一位地址就要自己重算校验）。

本次给预设页补两个**页面内自足**的动作：

1. **添加命令**：弹框里直接**粘贴报文**（剪贴板自动带入）→ 填名称/分组/说明 → 存成按钮；
2. **一键替换地址**：页面上一排**地址输入框**（按当前协议动态生成）+ 一个按钮 → 把地址写进
   **该协议的全部预设**并重算校验，逐条给出成功/跳过原因。

> 用户原话：「预设命令页面可以直接添加按钮，通过直接复制报文的方式也是可以进行命令添加的，
> 同样的也支持批量替换地址，按照协议进行地址的替换，有一个位置可以输入地址的输入框，
> 然后有一键替换地址的按钮，将所有的对应协议的地址一并替换掉。」

## 现状证据（实现必须与此一致）

- `preset_buttons.py`（545 行）：`PresetButtonManager`（load/save/add/remove/update，
  `atomic_write_json` 落盘）+ `AddPresetDialog(frame_hex, protocol)`（**报文预览只读**）
  + `PresetButtonWidget`（搜索过滤 / 分组按钮 / 右键删除 / 串口日志）。
  页面**没有任何新增入口**，也没有地址相关 UI。
- 预设文件按协议分文件（`NW_command.json` / `GW_command.json` / `DLT698_command.json` /
  `DLT645_command.json` / `MODULAR_command.json` / `YW645_command.json` / `CSG_UPLINK_command.json`），
  页面只显示 `cmd["protocol"] == 当前协议` 的条目（`load_buttons` 过滤，历史混入条目被隐藏）。
- 页面协议标识 → 协议索引**没有映射**；唯一来源应是 `protocol_registry` 的 `preset_mode`
  （`south`/`gdw`/`dlt698`/`dlt645`/`modular`/`yw645`/`csg_uplink` ↔ 0/7/8/6/12/13/14）。
- 地址替换引擎**已存在**且已被复用 4 次：`frame_addr_fix.py`（纯逻辑无 Qt，协议模块按需导入；
  `SUPPORTED_PROTOCOLS = (0, 6, 7, 8, 13, 14)`、`fields_for()`、`check_values()`、`apply()`）+
  `message_tool_widget.replace_frame_address(frame_text, protocol_index, values) -> (hex, notes, error)`
  （**报文文本层的唯一编排**：解析 HEX → 协议 6/8 剥/恢复前导 FEH → `apply` → 空格分隔回写）。
  两者都**必须复用**，不得新增偏移/算法清单。
- `message_tool_widget` 顶层 `import crcmod`（可选依赖）⇒ 在预设页只能**函数内按需导入**
  （AGENTS §8 陷阱 69/77：模块级导入会让没装 crcmod 的机器连预设页都打不开）。
- 按钮宽度：本项目字号可配置，**禁止 `setFixedWidth`**；判据 `width >= sizeHint`（AGENTS §8 陷阱 63）。

## Requirements

### R1 纯逻辑层（`preset_buttons.py`，无 Qt，可脱 GUI 测试）

- R1.1 `preset_protocol_index(preset_key) -> Optional[int]`：遍历 `protocol_registry.all_protocols()`
  匹配 `preset_mode`；未知/空 → `None`。**不得在预设页另写一张映射表**。
- R1.2 `AddrBatchItem`（`index` / `name` / `status` / `frame_hex` / `error` / `notes`）+
  `batch_fix_presets(commands, protocol_index, values) -> List[AddrBatchItem]`：
  - **不修改入参**（写回由 GUI 负责）；
  - 两态：`ok`（`frame_hex` = 新帧 + `notes`）/ `skipped`（原值 + 可读 `error`；
    含「报文为空」/ 结构或原帧校验不符 / 地址写法非法 / 协议不支持）；
  - 单条异常转 `skipped` + 可读原因，**绝不中断整批、绝不抛出**。
- R1.3 逐条实现**只调** `message_tool_widget.replace_frame_address`（函数内导入）；
  前导 FEH 只对协议 6/8 剥离并恢复（既有口径，勿改）。

### R2 GUI（`PresetButtonWidget` + `AddPresetDialog`）

- R2.1 搜索行左侧新增「添加命令」按钮 → `AddPresetDialog("", 当前协议, parent, editable_frame=True)`
  → 保存（`PresetButtonManager.add_command`）→ 刷新按钮 + 日志；保存失败要弹框说明。
- R2.2 `AddPresetDialog` 新增关键字参数 `editable_frame=False`：
  - `True`：报文框**可编辑**（高度更大、等宽字体、占位提示）、新增「从剪贴板粘贴」按钮、
    打开时若报文为空且剪贴板内容是合法 HEX 则**自动带入**（归一化为空格分隔大写 HEX）；
    确定时用 `message_tool_widget.hex_text_to_bytes` 校验（非法 → 警告并停在对话框），
    存规范化 HEX；报文为空视为非法。
  - `False`（既有调用方 = 组帧页「添加到预设」）：行为**逐字节不变**。
- R2.3 新增地址区 `QGroupBox`，标题带协议显示名；内容按 `frame_addr_fix.fields_for(索引)` **动态重建**
  （标签/占位/写法提示全部来自字段声明），末行「一键替换地址」按钮。
  切协议时重建并按协议**暂存已填值**（回切回填）；协议不支持（`preset_protocol_index` 为 None
  或 `fields_for` 为空，如模组化 12）→ 按钮禁用 + 明确提示支持范围。
- R2.4 点「一键替换地址」：
  1. 未支持协议 / 未填任何地址 → 明确告知并**不改动**；
  2. 写法级预检 `message_tool_widget.addr_field_errors` 不过 → 列出原因并停；
  3. `batch_fix_presets` 计算结果；**0 条成功 → 告知失败原因且一个字节都不改**；
  4. 否则 `QMessageBox.question` 确认（成功 N / 跳过 M + 最多 8 条跳过原因）；
  5. 确认后写回 `commands[原下标]["frame_hex"]`，**一次** `save_commands` 落盘，`load_buttons()` 刷新，
     日志逐条（`[地址替换] 名称：地址域… / 校验和…` 或 `跳过（原因）`），再弹汇总。
- R2.5 日志沿用页面已有 `log_text`（`_trim_log` 500 行上限），**失败必须外显**（日志 + 弹框）。

### R3 测试与门禁

- R3.1 新增 `test/test_preset_paste_addr.py`（脚本式 `check()`）：
  - 映射（唯一来源）、`batch_fix_presets`（南网/645 真帧 oracle：替换后**该协议校验器 0 fail** +
    地址字节符合期望 + 非地址字节不变；前导 FEH 保留；空帧/坏帧/混合批次；**不修改入参**）；
  - `AddPresetDialog` 编辑模式（可编辑 / 归一化 / 非法拒绝 / 剪贴板带入 / 非编辑模式不变）；
  - offscreen GUI：地址区按协议生成、一键替换端到端（落盘 + 刷新 + 日志）、跳过项列出、
    空地址拦截、模组化禁用、添加命令端到端、按钮不裁字（`show()` 后量）。
- R3.2 登记进 `release_check.py:CORE_TESTS`（只加自己那几行）。

## Acceptance Criteria

- A1 南网 2 条预设 → 地址区填「源地址 000000000005 / 目的地址 000000000006」→ 一键替换 →
  两条 `frame_hex` 的地址域分别为 `05 00 00 00 00 00` / `06 00 00 00 00 00`，
  `NWValidator` 0 fail，日志出现「地址域」与「校验和 0x… → 0x…」，按钮 tooltip 已是新报文。
- A2 同一批混入一条结构不符的帧 → 该条跳过并给出可读原因（确认框/汇总/日志三处可见），其余照常成功。
- A3 645 预设带 `FE FE FE FE` 前导 → 替换后前导仍在、`DLT645Validator` 0 fail。
- A4 不填地址点替换 → 警告且预设文件字节不变；全部失败 → 明确告知且文件字节不变。
- A5 「添加命令」粘贴连续 HEX `6812004116` → 落盘为 `68 12 00 41 16`，按钮立即出现，重启后仍在。
- A6 对话框里贴非法 HEX（`68 12 0G`）点确定 → 警告且不落盘。
- A7 切到模组化（协议12）→ 地址区按钮禁用并提示「不支持地址替换」。
- A8 `PYTHONIOENCODING=utf-8 python release_check.py --with-gui` → FAIL=0（既有环境红除外）。

## 非目标

- **不改 `frame_addr_fix.py` / `message_tool_widget.replace_frame_address`**（同一引擎第 5 次复用）。
- 不做协议 9/10/11/12 的地址替换（引擎 v1 不支持，给出可读提示即可）。
- 不做撤销（与串口页不同：预设是「持久化库」，改前用户已有确认框；误改可重新替换回来）。
- 不做「单条预设编辑」（右键目前仍只有删除）。
- 不改 Web 版（Reflex 端预设库为只读展示，见既有同步审计）。
