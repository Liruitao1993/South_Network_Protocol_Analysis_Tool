# Web 版解析能力对齐桌面版（父任务）

## Goal

Reflex Web 版（`reflex_web/reflex_web/`）与 PySide6 桌面版（`main_gui.py`）**共享同一套 parser/validator 实现**，因此「帧内容解析」本身不漂移；但 Web 侧的**胶水层**（校验分派、失败判定、预处理、帧提取、摘要、查询页、导出）是桌面版的手工复刻，且自 2026-09-08 起未再跟进（桌面已到 09-15 / 1.23.11）。本父任务要求把 Web 解析链路收敛到「与桌面同源、同输入同输出」，并消除已经产生**错误结果或错误结论**的缺陷。

## 调查基线（2026-09-15，四个只读子代理 + 主会话实测）

**P0 —— 会让用户拿到错误结果/错误结论（已实测复现）**

| # | 现象 | 关键证据 |
|---|---|---|
| 1 | Web「校验报文」对 12 种协议 100% 失败：`NameError: name 'p' is not defined` | `reflex_web/reflex_web/reflex_web.py:560`（`p` 从未定义），实测抽出函数体执行抛 NameError；无任何 Web 校验测试 |
| 2 | 批量失败判定只看首行 `result[0][0]` → 失败帧标「成功」 | `reflex_web.py:928-932` vs 桌面 `main_gui.py:7555-7557`（全表 `any`，但只认精确串）。实测中途 ❌ 用例：协议9 `mac_only` 短 MAC 帧（`49 5C 2F AA BB CC DD EE`）→ 行0「解析模式」、行1 ❌（`csg_new_gen_parser.py:843` 写入）→ 旧判定返回「成功」 |
| 3 | 奇数长度 hex 静默砍末位 nibble | `reflex_web.py:577-578`；桌面弹窗中止（`main_gui.py:5307-5311`） |
| 4 | ~~协议9 剔除字节不幂等~~ **（审计误判，已撤销）** | 原报告据「无缓存」推断 Web 每次解析会二次裁剪（`reflex_web.py:614-615`）。实测：Web 每次从**未被回写的** `frame_hex` 重算，本就幂等；按该结论加缓存后第二次解析反而拿到未剔除字节（真回归，已撤销）。P0 任务改为纯函数 `strip_frame_bytes` + 重复调用一致断言。详见子任务 `09-15-web-parse-p0-fixes/prd.md` 第 4 条与 `research/web-parse-audit.md` §6 |
| 5 | PB 帧类型从不下发 → 协议10「仅物理块PB」落到「⚠️ 未知帧类型」；协议9/11 非 SOF 物理块按 SOF 解 | `reflex_web.py:620-637`；`gw_new_gen_parser.py:159/231-241`；`hdc10_parser.py:261`；桌面按 `parse_level` 注入 `main_gui.py:4622-4626` |
| 6 | 广西台体 ED 包装（14 字节头）在 Web 静默错位 1 字节 | Web 无 ED 开关；共享 `csg_new_gen_parser.py:573-580` 只有 PLC2.0 布局；桌面 `main_gui.py:5014-5060` + gx 布局 |
| 7 | 南网 DI 查询 AFN 列算错：`afn = di3 & 0x0F` → 实测「添加任务」显示 `08H`（应为 `02H`） | `lookup_utils.py:92` vs 权威 `main_gui.py:2234`（AFN = DI1）+ `protocol_parser.py:519-541` 键序注释 |
| 8 | 协议10 查询页整体复用协议9 的表 → 实测搜「关联」0 命中 | `lookup_utils.py:328-331`（源码自述 TODO）vs 桌面 7 类表 49 条 `main_gui.py:3669-3685` |
| 9 | 协议8 查询页「属性/方法」恒为 `-`（实测 777 行全是占位符） | `lookup_utils.py:266-271` vs 桌面 `main_gui.py:3813-3823` |
| 10 | 报文工具 CRC-24 参数错（`rev=False` → 实测 `0xEAC98F`；权威 `rev=True` → `0xFC4D81`） | `web_utils.py:850` vs `csg_new_gen_parser.py:20`/`hdc10_parser.py:22`/`gw_new_gen_parser.py:22`/`message_tool_widget.py:24` |

**P1 —— 结果正确但能力缺失/双端不一致**

- 批量摘要是**三份实现**：协议10 用协议9 摘要（`web_utils.py:620-621`）、协议11 用 Web 独有 `get_hdc10_summary`（键名 `业务类型ID` 与 `hdc10_parser.py:2029` 实际字段不匹配 → 恒不命中）、协议0/7/8 退化为关键词兜底；桌面 1.23.10 的测试模式摘要 Web 完全没有。
- 批量前缀剥离缺 `fc_payload_data := '…'` 跨行状态机（`web_utils.py:149-181` vs `main_gui.py:4736-4840/4872-4930`）；协议10/11 缺 EDA5 包装剥离。
- 批量无行号（Web 提取返回纯字符串，桌面返回 `(hex, ed_type, line_no)`）→ 无「定位原始日志」。
- 单帧丢弃行字节范围 `row[4]/row[5]`（`reflex_web.py:643-668`）→ 无行↔字节高亮、无双击深度解析（桌面 `main_gui.py:10221-10284`）。
- 协议9 无通道下拉（永远 auto）、无「4字节反转」；无「按其他协议重解析」。
- 查询页 4 处自定义条目（南网DI/645DI/国网AFN/OBIS 标记）只读不能改。
- 批量 CSV 导出无字段详情（`web_utils.py:1009-1018`）。

**P2 —— 结构性风险与性能**

- Web **完全不引用** `protocol_registry`/`parser_registry`（0 命中）；协议索引硬编码分支 ≈145 处（`reflex_web.py` ≈105）。
- 三处手抄件（DLT645 转表 `reflex_web.py:483-529`、APDU/Wrapper 包装 `436-453`、validator 映射 `546-559`）：当前逐字一致，但无共享来源。
- 每请求新建 parser（`reflex_web.py:417-481`，`ProtocolFrameParser.__init__` 每次读 `custom_di.json`）；批量准备阶段零 yield（首个 yield 在第 100 帧）；摘要线性扫表；全量结果常驻 + 导出整串复制。
- 测试拦不住漂移：`reflex_web/tests/test_csg_ed_control.py` 只钉 Web 一侧，`test/test_web_all_protocols.py` 在测试里复刻 `_get_parser`，`test/test_csg_batch_prefix.py` 是第三份复刻。

## 子任务地图

| 子任务 | 交付物 | 独立验收方式 |
|---|---|---|
| `09-15-web-parse-p0-fixes` | P0 表 10 条全部修复（Web 侧行为与桌面同口径） | 新增 `test/test_web_parse_fixes.py` 逐条断言 + 手工复现命令 |
| `09-15-web-shared-parse-core` | 无 Qt 共享核心（剥离/提取/摘要/DLT645 转表/字段层级）+ Web 接 `protocol_registry` | 同一输入 Web 与桌面摘要/提取结果逐字相等；Web 侧协议分支数降到注册表驱动 |
| `09-15-web-batch-alignment` | 批量链路对齐（摘要含测试模式/跨行 payload/EDA5/行号/导出字段详情） | `test/test_web_batch_alignment.py` + 真实日志对拍 |
| `09-15-web-single-frame-alignment` | 单帧链路对齐（字节范围+深度解析/通道/4字节反转/重解析/查询页 CRUD） | `test/test_web_single_frame_alignment.py` + Web 端 offscreen 行为断言 |
| `09-15-web-parse-perf` | parser 缓存、分段 yield、摘要索引、导出流式 | 大输入（≥1MB/≥5k 帧）耗时与事件循环让出实测 |

## 跨子任务约束

- **执行顺序（硬依赖，写在此处而非树位置）**：`p0-fixes` → `shared-parse-core` → `batch-alignment` / `single-frame-alignment` → `parse-perf`。`shared-parse-core` 会删除 `web_utils` 的复刻体，后续两个对齐任务必须建立在共享核心之上，否则会出现第三份实现。
- **单一实现原则**：任何预处理/提取/摘要逻辑只允许存在一份（无 Qt 模块），`main_gui` 与 `reflex_web` 都调用它；禁止在 Web 侧再写复刻（本父任务的根因就是复刻）。
- **桌面行为是权威**：除明确判定桌面为缺陷的情形（如「空表状态语义」），Web 一律对齐桌面；发现两侧都不对时，以协议文档（AGENTS.md §5 映射）为准并同时修两侧。
- **测试必须拦漂移**：新增对照测试走「桌面未绑定方法（Host 宿主）+ Web 同输入」对拍（范式见 `test/test_csg_summary.py`），禁止在测试里复刻产品逻辑。
- **发布门槛**：每个子任务完成后 `python release_check.py` 无 FAIL；共享核心与批量子任务需把新测试登记进 `release_check.py:CORE_TESTS`。
- **版本号**：每个子任务独立 bump `APP_VERSION` 并在 `main_gui.py:CHANGELOG` 头部加条目（Web 修复同样记录，便于两端对账）。
- **文档同步**：`AGENTS.md` §1（Web 协议覆盖 0-10 → 实际已含 11）、§3 目录树、§7 测试清单、§10 摘要随改动同步。

## Acceptance Criteria

1. P0 表 10 条全部修复：每条在 `test/test_web_parse_fixes.py` 有独立断言，且断言的是可观察行为（校验成功/失败、状态列取值、解析结果），不是源码文本。
2. `reflex_web/` 不再包含与桌面重复的预处理/提取/摘要实现；新增/修改协议只需改 `protocol_registry.py`，Web 自动跟随。
3. 同一份现场日志（含监控前缀、跨行 payload、ED 包装）在 Web 与桌面得到逐字相同的摘要与帧提取结果（对拍测试）。
4. Web 单帧解析具备行↔字节定位与选中行深度解析能力。
5. `python release_check.py` 全绿（PASS ≥ 现有基线 49，FAIL=0）。
6. AGENTS.md / README / CHANGELOG 与实现一致（含 Web 协议覆盖说明修正）。

## Out of Scope

- 频谱图、虚拟表（698/645 从站）、档案、拓扑、实时监控、TCP 监控等 Web 未实现的**桌面专属功能**（属另立需求，不在「解析能力对齐」范围）。
- Reflex 前端视觉改版、CSS/主题体系重构。
- 桌面版独占能力的删除或降级（Web 只增不改桌面行为；桌面缺陷如确实存在，按上文「桌面行为是权威」的例外条款单独立项）。
- 打包/部署流程改造（`build_embedded_deploy.py` / `build_offline_deploy.py`），除新增模块需进 spec 的情况。

## Risks / Deferred

- **共享核心抽取的回归面**：`main_gui.parse_batch` 与 Web `parse_batch` 同时切换实现，桌面侧回归必须靠既有 `test_csg_*` / `test_gw_*` / `test_batch_*` 套件兜住；若发现桌面行为依赖某处「桌面独有细节」，在共享核心中以显式参数表达而不是复制分支。
- **Web 端无自动化端到端**：本次以纯逻辑 + State 级脚本断言为主，不引入 Reflex 运行时端到端测试（部署环境无浏览器驱动）。真机验证留给 `reflex_web` 本地起服。
- **协议11 支持早已存在但文档未同步**：`AGENTS.md §1` 的「Web 0-10」为滞后描述，本批任务顺手修正；不扩大为协议11 的 Web 能力补齐（除 P0 的帧类型/摘要对齐外）。
