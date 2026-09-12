# 后续功能批次（父任务）

## Goal

用户从「值得做的功能」清单中选定的 5 项独立可验证交付物，统一挂在本父任务下。父任务负责要求集、任务地图、跨子任务验收与最终集成复核；具体实现由各子任务承担。

## 子任务地图

| 子任务 | 交付物 | 规模 | 独立验收方式 |
|---|---|---|---|
| `09-12-nanwang-custom-di-crud` | 南网查询页「添加/删除自定义 DI」可用（现为死按钮） | 小 | offscreen GUI：新增/删除后 `custom_di.json` 落盘 + 查询表刷新 + 重启保持 |
| `09-12-dlt645-sim-func-codes` | 645虚拟表从站补齐 12H/16H/17H/18H/19H/1AH/1BH | 小-中 | 引擎逐功能码自组帧→应答→解析回读 + 档案/密码校验用例 |
| `09-12-hdc10-net-coord-vf` | HDC 1.0 网间协调帧可变区域结构化解析（现「待实现」） | 小-中 | 用真实/构造网间协调帧断言字段行 |
| `09-12-csg-mme-app-deep` | 协议9 管理消息 + 应用层业务数据结构化解析（现「尚未实现结构化解析」） | 中-大 | 文档条目逐项断言 + 真实抓包回归 |
| `09-12-gw-unknown-msg-deep` | 协议10 未识别业务报文类型深解析（现打原始 hex） | 中 | 逐个报文ID 断言字段行；既有 `test_gw_new_gen` 无回归 |

**顺序建议**（无硬依赖，按价值/成本排）：nanwang-custom-di-crud → dlt645-sim-func-codes → hdc10-net-coord-vf → gw-unknown-msg-deep → csg-mme-app-deep。

## 跨子任务约束

- 各子任务独立分支语义：不动他人文件；公共模块（`theme_settings`/`main_gui` 的 CHANGELOG/`release_check.py`）如需改动，由最后完成的子任务统一 bump 版本，避免 5 次版本冲突。
- 每个子任务完成后必须保持 `python release_check.py` 全绿（当前基线 **PASS=48 FAIL=0 WARN=0**）。
- 所有新增解析必须走对应协议文档（AGENTS.md §5 映射），不得凭记忆推断字段。

## 基线状态（本父任务创建时）

- 已交付：`2be9b2a` 645虚拟表事件状态字随机（1.23.8）、`0272643` 协议10 假阳性吞帧修复（release_check 首次全绿）。
- 在飞（用户自有）：`09-09-csg-batch-sequence-diagram`、`09-10-batch-snapshot-locate`。
