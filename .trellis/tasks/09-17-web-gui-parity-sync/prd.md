# Web↔GUI 修复同步：版本×Web 审计 + 已确认缺口修复

## Goal

落实「GUI 修的问题，Web 若同样存在必须一起修」这条长期要求：

1. **出审计清单**：1.23.0~1.23.22 逐版对照 Web 对应实现，判定每条 GUI 改动是否影响 Web（含批量/监控/组帧/时序图/导出链路）。
2. **修本轮已实测确认的缺口**（见 Requirements R2~R4）：645 转表两份复制去重 + 长度不符时偏移越界、Web 缺「测试模式」批量摘要、Web 查询页缺自定义 DI/AFN CRUD。
3. **建立防漂移机制**：两端同源 + 对拍断言，避免同类问题再发生。

## Requirements

### R1 审计清单（1.23.0~1.23.22 逐版）

- 覆盖 `main_gui.py:CHANGELOG` 中 1.23.0~1.23.22 的**每一条**改动。
- 每条产出：所属版本 / GUI 改动一句话 / **是否影响 Web 解析或展示链路** / Web 对应实现位置（`文件:行`）/ 判定（四选一：`继承` 无需动手 · `缺失` Web 没有该能力 · `同错` Web 有同款缺陷 · `N/A` GUI-only）/ 处置。
- `继承` 类判定必须给依据（如「Web `reflex_web.py:483` 直接 import 同一 `DLT645Parser` 类」），不得凭印象。
- 产出落 `docs/Web与GUI同步审计.md`，供后续版本追加维护。

### R2 645 转表：单一来源 + 偏移修复（两端）

**R2.1 去重**：`reflex_web/reflex_web/reflex_web.py:511` `_safe_parse_to_table` 里那份 645 转表逻辑，与桌面 `protocol_registry.py:355` `DLT645GuiParser.parse_to_table` **逐字相同**，是复制体。收口为单一来源。

**R2.2 偏移修复**：现有公式 `total_len = 10 + data_len + 2`（`protocol_registry.py:363`、`reflex_web.py:520`）用的是帧内**声明**长度。1.23.22 起「声明长度与实际不符」的帧不再拒解析 → 该公式必然算错：

实测 `68AAAAAAAAAAAA6811082CDD32375316`（声明 `L=08`，实际 16 字节）：

| 行 | 现状偏移 | 应为 |
| --- | --- | --- |
| `校验和` | `[18, 18]` ← 越界（帧仅 0~15） | `[14, 14]` |
| `⚠ 校验和错误` | `[18, 18]` ← 越界（行名含「校验和」子串） | `[14, 14]` |
| `帧结束符` | `[19, 19]` ← 越界 | `[15, 15]` |
| `数据内容` / `数据域` 末端 | 按声明长度推 | 受实际帧长约束 |

**影响**：点击这些行时输入框高亮落到不存在的位置，两端同错。1.23.22 之前该路径不可达（长度不符即拒解析），故为**本次修复才暴露的既有缺陷**。

### R3 Web 补「测试模式」批量摘要（1.23.10 同步）

桌面 `MainWindow._extract_test_mode_content`（`main_gui.py:8219`，staticmethod 纯逻辑）产出协议9/10/11 的测试模式摘要片段。`reflex_web/` 全目录无该逻辑 → Web 批量摘要比桌面**少一整段**。

- 需覆盖：`测试模式/配置操作`（协议9 表61 / 协议10 检测扩展命令）、子模式 `安全测试模式`/`新一代测试模式`、回退项 `测试ID`/`扩展ID`/通信频段。
- 共享方式见 design.md D3（不得让 Web import `main_gui`）。

### R4 Web 查询页补「自定义 DI / AFN」增删（1.23.11 同步）

- 协议0（南网）自定义 DI：桌面经 `main_gui.py:2667` `lookup_pages.apply_custom_di_add` / `:2681` `delete_selected_custom_di_interactive`，底层单源 `custom_di_store.py`。
- 协议7（国网）自定义 AFN：桌面经 `gdw_parser.add_custom_afn`（`main_gui.py:4380`），落 `gdw_custom_afn.json`。
- Web 查询页（`reflex_web.py:10642` `lookup_tab()`）目前是**只读**（只有 `do_lookup`/`load_lookup_default`），无任何增删入口 → 功能缺失。

### R5 防漂移守卫

- 新增/改动逻辑一律**两端同源**；无法同源处加对拍断言。
- 关键守卫须用**变异反证**自检（改回错误形态确认测试变红，再还原）。

## Acceptance Criteria

- [ ] `docs/Web与GUI同步审计.md` 覆盖 1.23.0~1.23.22 全部 CHANGELOG 条目，每条含判定与 `文件:行` 依据；抽查任意 3 条可复核成立
- [ ] 645 转表**只剩一份**实现，`reflex_web.py` 不再有转表复制体；两处调用点行为一致
- [ ] 声明长度不符帧：`校验和` 偏移 = 实际帧长-2、`帧结束符` = 实际帧长-1、`⚠ 校验和错误` 落在校验和字节；如上实测帧得 `14/14/15`
- [ ] **合法帧输出逐行不变**（与改动前对拍，硬约束）
- [ ] Web 协议9/10/11 批量摘要含测试模式片段，与桌面**逐字符一致**（真实帧对拍）
- [ ] Web 查询页协议0 可增/删自定义 DI、协议7 可增/删自定义 AFN，写盘与桌面**同一文件**且桌面重启后可见
- [ ] 新增测试登记 `release_check.py:CORE_TESTS`；`python release_check.py` PASS 且 FAIL=0

## Constraints

- **不得改 `valid` 语义**（`dlt645_sim/engine.py` 等消费方依赖，见 AGENTS §8 陷阱 49）
- **合法帧输出逐行不变**（陷阱 49 硬约束）
- 新增提示行的行名必须含「校验和」，否则偏移高亮落字节 0（陷阱 49）——R2.2 改动时勿破坏
- **Web 不得 import `main_gui`**（会拉 PySide6）；共享逻辑须落在无 Qt 的纯逻辑模块
- `dlt645_di.json` 是生成物，不得手改（AGENTS §4.5）
- 本任务**不做**全量共享解析核心抽取（归 `09-15-web-shared-parse-core`）

## Out of Scope

- Web 实时监控器 / 档案管理 / 拓扑（AGENTS §1 已定 Web 不做）
- 解析器层功能缺口（MME 未实现类型、抄表 DATA 内嵌 645/698.45 等）——另有任务
- Web 与桌面**有意保留**的差异（AGENTS §8 陷阱 31 列出的 3 条：校验预处理口径、协议10 查询页关键词列数、南网 DI 页匹配方式）

## Open Questions（设计阶段已定，见 design.md）

- 国网自定义 AFN 无独立 store 模块（桌面直调 `gdw_parser.add_custom_afn`）→ 是否顺带抽 `custom_afn_store`？（design.md D4 给结论）
- Web「多选批量删除」的实现形态（design.md D4 给结论）
