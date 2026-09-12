# 协议10 未识别业务报文类型深解析

## Goal

协议10（国网新一代双模 / HDC 1.0+2.0）应用层里，解析器能识别的报文类型之外的内容会退回一行「报文ID=0xXXXX 暂不支持深度解析」原始 hex。本任务把其中**文档已定义**的类型补齐，让协议10 的解析覆盖率与协议9 对齐。

## Confirmed Facts（代码证据）

- 占位点：`gw_new_gen_parser.py:1312` — `f"报文ID=0x{msg_id:04X} 暂不支持深度解析"`。
- 协议10 应用层命令载荷已有独立模块：`gw_new_gen_cmd_payloads.py`（AGENTS.md §3），入口 `parse_command_payload(payload, msg_id, direction, port, offset)`（见 `gw_new_gen_parser._parse_application_layer` 调用）。
- **上游刚修掉一个假阳性吞帧缺陷**（`0272643`）：此前 FC 首字节撞 MMTYPE 会让整帧被当管理消息，应用层完全不解析；修复后 `test_gw_new_gen` 从 26/12 变为 44/0，`test_gw_monitor_summary` 3/8 → 11/0。**本任务必须在修复后的基线上做**，否则"未识别"清单会包含大量假阳性帧。
- 既有测试与资产：`test/test_gw_new_gen.py`（44 项）、`test_gw_batch_parse.py`、`test_gw_parse_levels.py`、`test_gw_ext_cmd.py`（49 项）、`test_gw_monitor_summary.py`（11 项）、`test/test_hdc10.py`、真实报文日志见 AGENTS.md §8 陷阱 29（`TMI模式遍历测试_频段1__All.log`）。
- 参考文档（AGENTS.md §5.8，`国网新一代协议/`）：
  - `双模通信互联互通技术规范 第4-3部分：新一代应用层协议.md`（**应用层报文类型权威**）
  - `双模通信互联互通技术规范 第4-2部分：数据链路层通信协议.md`
  - HDC 1.0 版（`国网新一代协议/HDC-国网双模协议/...第4-3部分：应用层通信协议.md`）

## Requirements

### R1 缺口盘点（先做，产出清单）
- 脚本化对比：文档 4-3 部分定义的报文ID（端口+报文ID 组合）清单 vs `gw_new_gen_cmd_payloads.py` 实际覆盖清单，输出「已结构化 / 仅原始 hex」两张表到本任务 `research/`。
- 用真实抓包（TMI 日志 / 现有测试帧）统计各未识别 ID 的出现频次，按频次排优先级。

### R2 按文档补齐
- 逐个未识别类型补 `parse_command_payload` 分支，输出字段行（字段名/原始值/解析值/说明 + 偏移），**每项附文档表号注释**。
- HDC 1.0 与 2.0 若同 ID 结构不同：按 `std_version` 分支，不要混用（AGENTS.md §8 陷阱 14）。
- 文档未定义/保留的 ID 保持原始 hex + 明确说明（不伪造字段）。

### R3 摘要联动
- `_get_gw_new_gen_summary`（main_gui）在补齐后应能提取新字段；确认 `main_gui.py:8078` 的跳过规则（`未解析/尚未实现` 关键字）不会吞掉已补齐的行。

### R4 测试
- 扩展 `test/test_gw_new_gen.py` + `test_gw_batch_parse.py`：逐补齐类型字段断言、保留类型容错、真实帧回归。
- 既有 4 个协议10 测试（`test_gw_new_gen` / `test_gw_monitor_summary` / `test_gw_batch_parse` / `test_gw_parse_levels` / `test_gw_ext_cmd`）全过；`release_check.py` 全绿（基线 PASS=48 FAIL=0 WARN=0）。

## Acceptance Criteria

1. `research/` 缺口清单存在，且"已补齐"与"仍退回原始 hex"两类与代码一一对应。
2. 清单内每个补齐的报文ID：解析出结构化字段行（不再是"暂不支持深度解析"），字段名与文档一致、附表号。
3. 文档未定义的 ID 仍为原始 hex + 说明（不伪造）。
4. 协议10 全部既有测试 + 新断言全过；`release_check.py` 无 FAIL/WARN。
5. 若同 ID 在 HDC 1.0/2.0 结构不同，两个版本各有断言。

## Out of Scope

- 不改协议9（另见 `09-12-csg-mme-app-deep`）。
- 不重构 `gw_new_gen_parser.py` 已实现的解析路径与 FC/MAC 定位逻辑。
- 不做发送/组帧侧。
- 不做 MME（管理消息）侧——协议10 MME 已有 `gw_new_gen_mme_parser.py`；若发现缺口另开。

## Risks / Deferred

- 范围可能大：**以 R1 盘点 + 频次排序为界**，先做高频类型；清单过大时与用户确认分批。
- 部分报文ID 可能只存在于某一网省扩展（如福建增补）：遇到时先确认是否属本任务范围（协议7 的福建增补已有独立实现，勿混）。
- 真实帧来源是 TMI 遍历日志（测试夹具），若某类型在真实帧中不存在，则只能构造帧并注明"构造帧"。
