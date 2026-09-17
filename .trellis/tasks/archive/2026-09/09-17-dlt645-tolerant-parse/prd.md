# 协议6 校验和/长度/结构不符时仍继续解析并提示正确值

## Goal

协议6（DLT645-2007）在**校验和错误**（以及数据长度不符、帧结构不符）时，不再返回「无效的DLT645帧格式」空白结果，而是**照常解析全部可解析字段**，并明确告知**正确的校验和是多少**（含计算规则）。与协议0（南网，`protocol_parser.py:878` 已有此行为）保持一致。

## Background

- 用户报障：提供的 645 帧校验和不正确时，工具**完全不解析**（结果表为空），只给「无效的DLT645帧格式」；用户需要的是「正常解析 + 告诉我正确校验值」。
- 已复现（`dlt645_parser.py`，构造电压块帧后把 CS 改错）：

  | 输入 | valid | error | 字段数 |
  | --- | --- | --- | --- |
  | 合法帧 | True | None | 13 |
  | CS 错 | **False** | `无效的DLT645帧格式` | **0** |

- 根因：`dlt645_parser.py:39 check_frame()` 把「结构判据」（长度≥12 / 双 `68H` / 结尾 `16H`）与「校验判据」（CS）混在一个返回值里；`parse():68` 用它做**提前 return**，于是任何一项不符都得到空表。
- 这违反项目既有原则 **AGENTS.md §8 陷阱 23**（「字段声明与实际不一致时解析器不得直接返回空白结果」，正确做法是尽力解析 + `valid=False` + 表格中插入醒目 `⚠` 行）。
- 仓库内已有正确的先例实现：`protocol_parser.py:860-890`（南网）——照常解析、记录 `校验和: {校验值, 计算值, 校验结果}`、`解析状态=失败` + `错误信息 = 校验和错误，期望 0xXX，实际 0xYY`，**不提前 return**；结束符错误同样处理。本任务让协议6 对齐该行为。
- 影响面已核实：`check_frame` 在仓库内**只有 1 个调用点**（`dlt645_parser.py:68`）；GUI 侧 `protocol_registry.DLT645GuiParser.parse_to_table` 与 Web 侧均**只遍历 `result["fields"]`、不检查 `valid`** → 修好 `parse()` 两端自动生效；`dlt645_sim/engine.py:115` 与 `dlt645_meter_sim_widget.py:544` 用 `parsed.get("valid")` 拒收坏帧 → 必须**保持 `valid` 语义不变**（校验/结构不符仍为 False），否则虚拟表会开始接受坏帧。

## Requirements

- R1 校验和错误时：完整解析全部字段（DI 名、数据值、深度解析行等一个不少），并明确给出**帧内值**与**正确值**及计算规则。
- R2 数据长度声明与实际不符时：仍完整解析（现状已如此），并补上「应声明 N 字节」这类可执行信息。
- R3 帧结构不符（缺 `68H`/`16H`）但长度 ≥12 时：按假定位置继续解析，并插入醒目结构错误行说明**具体哪个字节不符**。
- R4 长度 <12 时：不崩溃、不空白，给出帧长不足说明 + 原始 hex（此时无法可靠定位字段，属可接受的降级）。
- R5 `valid` 语义不变：仅当「结构 OK + 校验 OK + 长度相符」时为 `True`（保证 `dlt645_sim` 等既有消费方行为不变）。
- R6 新增结果字段（`checksum_expected` / `structure_valid` / `structure_error`）不得破坏既有字段与既有消费方。
- R7 新增提示行的**行名包含「校验和」**，以便 `DLT645GuiParser` 的偏移映射自动定位到 CS 字节（该映射按字段名子串匹配）。
- R8 桌面与 Web 一致（同源 `fields`），批处理不回归。

## Scope

### In Scope
- `dlt645_parser.py`：拆判据、去提前 return、新增提示行与结果字段。
- 新增回归测试套件并登记 `release_check.py:CORE_TESTS`。
- 版本 1.23.22、`CHANGELOG`、`AGENTS.md`（陷阱条目）、`README` 徽章、两个 `.iss`。

### Out of Scope
- 其他协议（国网 `gdw10376_parser`、698.45、新一代系）是否同类：本次不动（南网已是正确行为；其余需逐协议验证，另行立项）。
- `validator/dlt645_validator.py` 的校验报告（**现状已正确**：`校验和错误，期望0xXX`，无需改）。
- 组帧侧、虚拟表从站逻辑。

## Acceptance Criteria

- [ ] A1 CS 错误帧：`fields` 非空且包含全部业务字段（以电压块帧为例，应含 `数据标识 DI` = `02E60101` 与「光伏逆变器1的电压数据块」深度解析行）。
- [ ] A2 CS 错误帧：表格出现「⚠ 校验和错误」行，且**同时**给出帧内值、正确值（`应为 XXH`）与计算规则（`起始符 68H 到数据域最后 1 字节的算术和 & 0xFF`）。
- [ ] A3 CS 错误帧：`valid is False`（语义未变），`checksum_valid is False`，`checksum_expected` = 计算值。
- [ ] A4 合法帧：行为与改动前**逐行一致**（`valid=True`、无新增提示行、字段数不变）。
- [ ] A5 数据长度不符帧：仍完整解析，且提示含「应声明 N 字节」。
- [ ] A6 结构不符帧（第 8 字节非 `68H` 或末字节非 `16H`，长度 ≥12）：仍解析出字段，且出现「❌ 帧结构错误」行并指明具体字节。
- [ ] A7 长度 <12：不抛异常，返回帧长不足说明 + 原始 hex 行。
- [ ] A8 虚拟表不回归：`dlt645_sim/engine.py` 对 bad-CS 主站帧仍判为无效（`valid False`）→ 既有套件全绿。
- [ ] A9 GUI 链路：`DLT645GuiParser.parse_to_table` 对 CS 错误帧返回非空表，且「⚠ 校验和错误」行的字节区间落在 CS 字节（`total_len - 2`）。
- [ ] A10 回归：`test_dlt645_lme.py` / `test_dlt645_pv_ext.py`（156）/ `test_dlt645_frame_gen.py`（161）/ `test_dlt645_sim*.py` / `test_web_parse_fixes.py` 全绿；`release_check.py` FAIL=0 / WARN=0。
- [ ] A11 变异反证：恢复提前 return → A1/A2 必须变红；去掉 `checksum_expected` → A3 变红；把 `valid` 恒置 True → A8 变红。

## Notes

- 复现脚本已确认现状（见 Background 表）。
- 参照实现：`protocol_parser.py:860-890`（南网，**同仓库先例**）。
- 相关既有处理：`dlt645_parser.py` 已有 `data_length_mismatch` 分支（`valid=False` + ⚠ 行，不空表）—— 本任务把 CS 与结构也纳入同一模式。
