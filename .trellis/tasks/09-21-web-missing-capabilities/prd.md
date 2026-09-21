# PRD：Web 缺失能力补齐（时序图 / 快照跳转 / 脚本预处理 / pcap / 批量取消 / 协议6 预设）

> 来源：`09-17-web-gui-parity-sync` 的审计产出 `docs/Web与GUI同步审计.md` §2.1「新发现的缺失」（6 项）。
> 父任务：`09-15-web-parse-alignment`。本任务只做需求收口，实现前需按 Trellis 流程补 `design.md` / `implement.md`。

## 背景

审计 1.23.0~1.23.22 共 167 条 CHANGELOG 条目后，除已修复的三项（645 转表偏移、测试模式摘要片段、查询页自定义 DI/AFN CRUD）外，发现 6 项桌面已有、Web 无对应物的能力。审计文档已给出证据（文件:行号）与可复用性判断，本任务负责把它们逐项规划、实现、验收。

## 范围（6 项，各自独立可验收）

| # | 能力 | 审计依据 | 复用性提示 |
| --- | --- | --- | --- |
| 1 | 通信时序图（协议9/10/11） | 1.23.0-01 ~ -08；Web 无该标签页 | `sequence_diagram_widget.py` 纯逻辑层（`SequenceNode`/`SequenceMessage`/`SequenceModel`/`build_sequence_model`）无 Qt，可被 Web import |
| 2 | 批量原始日志快照 + 「转到原始报文位置」 | 1.23.0-13、-14 | 桌面 `batch_source_view.py` + `_src_line` 行映射；Web 批量侧已有行号信息可扩展 |
| 3 | 脚本预处理（用户 py 脚本列表） | 1.23.0-09、-10 | `scripts/hex_clean.py` 等命令入口；Web 目前只有 `pp_cli` 管道 |
| 4 | pcap 导入 | 1.23.2-01、-02 | `pcap_import.py` 无 Qt 依赖，可直接被 Web 复用 |
| 5 | 批量解析「取消」 | 1.23.15-01、-02 | Web 批量已是分块 yield 的 async 生成器，需补取消事件与状态清理 |
| 6 | 协议6（DL/T 645）预设命令 | 1.23.1-03 | 桌面 `DLT645_command.json` + 预设页；Web `_load_preset_buttons` 目前仅 `p in (0, 7)` |

## 非目标

- 不改动已收口的单源实现（645 转表、测试模式摘要片段、`batch_core` 前缀剥离/帧提取）。
- 不承担 `09-15-web-shared-parse-core` 的职责（摘要主体/查询数据源两端收口）。
- 不做 1.23.23~1.23.40 区间的审计（该区间仍待审计，见审计文档 §三）。

## 验收标准

1. 6 项各自有「桌面行为 ↔ Web 行为」的对拍或等价性断言（能给出桌面输入 → 两端同结果）。
2. 新增/修改的 Web 状态与 UI 不破坏现有 9 个标签页；`python release_check.py` PASS 且无新增 FAIL。
3. 每项实现后更新 `docs/Web与GUI同步审计.md` 对应行的判定与修复位置（判定由 `缺失` 变为 `继承` 时须写明依据）。
4. 纯逻辑尽量下沉到无 Qt 模块并登记到 `release_check.py:CORE_TESTS`。

## 依赖与顺序建议

- 建议顺序：④ pcap → ⑥ 协议6 预设 → ⑤ 批量取消 → ③ 脚本预处理 → ② 快照跳转 → ① 时序图（复杂度递增）。
- ① 与 ② 会触及批量结果结构，若 `09-15-web-shared-parse-core` 同期进行需先对齐数据契约。
