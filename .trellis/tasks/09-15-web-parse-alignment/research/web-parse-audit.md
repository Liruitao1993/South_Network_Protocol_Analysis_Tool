# Web vs 桌面解析能力审计（2026-09-15，只读调查）

来源：4 个只读子代理（批量链路 / 单帧链路 / 查询与工具 / 重复与性能）+ 主会话实测复现。
本文件是父任务与各子任务的证据底稿；行号对应本次审计时的仓库状态（`main` @ 9d0bb4e）。

---

## 0. 架构事实（为什么会有这些差异）

- **共享**：`parser_*.py` / `validator/*` 被两端共用 → 帧内容解析不漂移。
- **不共享**：预处理（前缀剥离/ED 包装/剔除）、帧提取、摘要、DLT645 dict→表格转换、字段层级、查询页数据源，两端各写一份。
  - 桌面：`protocol_registry.ProtocolSpec`（`extract_strategy`/`parser_wrapper`/`validator_class`/`parse_level_family`）驱动，`build_gui_parser` 注入 `parse_level/frame_type/channel`（`protocol_registry.py:449-479`），`parser_registry.get_parser` 提供共享实例（`parser_registry.py:47-54`）。
  - Web：`State._get_parser` 手写 12 分支 + 内联包装类（`reflex_web/reflex_web/reflex_web.py:417-481`）、`_safe_parse_to_table`（483-529）、`_get_validator`（531-562）、`web_utils.py` 纯函数复刻、`lookup_utils.py` 查询页独立实现；`protocol_registry` / `parser_registry` 在 `reflex_web/` **0 引用**。
- **时间漂移**：`reflex_web/reflex_web/reflex_web.py` 最后改动 = 2026-09-08（`75b0142`）；桌面同期到 2026-09-15（`bd4be7a`，1.23.11）。1.23.9/1.23.10/1.23.11 的解析相关改动（测试模式摘要、自定义 DI 单源）均未进 Web。

---

## 1. 批量链路差异（子任务：web-batch-alignment）

| # | 项 | Web | 桌面（权威） |
|---|---|---|---|
| B1 | 摘要分派 | `web_utils.py:615-637`：9/10 → CSG 摘要；11 → Web 独有 `get_hdc10_summary`；其余关键词兜底 | `main_gui.py:7666-7772`：0/7/8 各有专属分支；9 → CSG；**10 与 11 共用 `_get_gw_new_gen_summary`** |
| B2 | 协议10 摘要 | 用协议9 的 `get_csg_new_gen_summary`（键名/分支完全不同） | `_get_gw_new_gen_summary`（`main_gui.py:8218-8332`，NID/帧类型/TEI/msduSeq/报文ID…） |
| B3 | 协议11 摘要 | `get_hdc10_summary`（`web_utils.py:552-612`）——其 `业务类型ID` 键（596）与 `hdc10_parser.py:2029-2032` 实际字段名不匹配 → **恒不命中**；`定界符类型` 输出原始 comment（`DT=1: SOF帧`） | 走 `_get_gw_new_gen_summary`，输出净化名 |
| B4 | 测试模式摘要 | 无（`reflex_web/` grep「测试模式」= 0） | 1.23.10：`_extract_test_mode_content`（`main_gui.py:7777-7886`），协议9 表61 / 协议10 检测扩展命令 |
| B5 | 前缀剥离（协议10/11） | `strip_gw_new_gen_prefix`（`web_utils.py:149-181`，33 行"取最后一个冒号"） | `_strip_gw_new_gen_prefix`（`main_gui.py:4736-4840`）：`fc_payload_data := '…'` 跨行引号状态机、引号截断、行映射 |
| B6 | 前缀剥离（协议9） | `strip_csg_new_gen_prefix`（`web_utils.py:76-146`）：无跨行状态机、无 `mac_only` 直通、app 扫描阈值不同（`:122` `len-i>=8` vs 桌面 `while i+32<=len`） | `_strip_csg_new_gen_frame_prefix`（`main_gui.py:4842-4975`，含 4872-4930 状态机、4942 mac_only） |
| B7 | EDA5/TCP 包装 | 协议9 有（`web_utils.py:102-107`），协议10/11 无 | 三者均有（`main_gui.py:4855-4861, 4933-4937`） |
| B8 | 帧提取返回契约 | 纯字符串（`web_utils.py:355-386`，12 分支 if/elif） | `(hex, ed_data_type, line_no)` 三元组（`main_gui.py:8334-8370`）→ 行号回跳 + ED 类型标记 |
| B9 | ED 每帧分支 | 无（整帧丢给 parser） | 三条分支（`main_gui.py:7479-7541`）：ED 提取失败明确报错 / 合法 ED 无业务数据出监控头 / 常规；摘要带 `[ED:类型]` 前缀 |
| B10 | 失败判定 | `result[0][0]` 含 "❌"（`reflex_web.py:928-932`） | 全表 `any(item[0] == "❌ 解析失败")`（`main_gui.py:7555-7557`）——口径偏窄（漏 `❌ 单跳MAC帧头不完整` 等）；**实测中途 ❌ 用例**：协议9 `mac_only` 短 MAC 帧（`49 5C 2F AA BB CC DD EE`）→ 行0「解析模式」、行1 ❌ |
| B11 | 空表语义 | 空 → 「失败」 | 空 → 「成功」（`any([])==False`）——两侧不一致 |
| B12 | 空输入诊断 | 一句「未找到有效帧数据」（`reflex_web.py:881-885`） | 区分「预处理后为空」+ 清洗后样本 + 3 条可能原因（`main_gui.py:7391-7406/7419-7432`） |
| B13 | 异常状态字面量 | `status="错误"`、`proto="解析错误"`（`reflex_web.py:946-957`） | `status="异常"` + `错误` 字段（`main_gui.py:7583-7595`） |
| B14 | 导出 | JSON 含字段详情；CSV 仅 6 列汇总（`web_utils.py:975-1019`） | Excel/CSV/TXT/JSON 增强导出（`enhanced_export.py`） |
| B15 | 摘要列与类型列 | 同一文本既填 `proto` 又填 `summary`（`reflex_web.py:941-942`） | `摘要` 与 `_type_name`（`_get_frame_type_name`，`main_gui.py:9776-9853`）两列不同 |

实测（可复现）：`get_frame_summary(rows, 10)` 走 CSG 分支；协议10 现场日志摘要与桌面文案不同。

---

## 2. 单帧链路差异（子任务：web-single-frame-alignment）

| # | 项 | Web | 桌面 |
|---|---|---|---|
| S1 | 解析预处理 | `_clean_hex` → `_apply_strip` → `parse_to_table`（`reflex_web.py:602-687`） | 加「4 字节反转」（`main_gui.py:5292-5298`）、ED 监控剥离+业务行偏移修正（5348-5406）、剔除幂等缓存（5322-5346）——**注：Web 侧剔除本身已幂等**（每次从原始 `frame_hex` 重算），差异仅是「缓存+回写」vs「重算」，见文末勘误 |
| S2 | 字节范围 | 丢弃 `row[4]/row[5]`（只渲染 row[0..3]，`reflex_web.py:643-668`） | `_byte_ranges` + 点行高亮（`main_gui.py:10138-10168/10170-10219`） |
| S3 | 深度解析 | 无 | 双击行 → `_extract_apdu_reparse`（`main_gui.py:10221-10284`，按协议分派 gw_new_gen/hdc10/DLT645/hdlc APDU） |
| S4 | 协议9 通道 | 无状态无控件（永远 parser 默认 auto） | 下拉 auto/plc/hrf（`main_gui.py:1468-1481`）→ `main_gui.py:4628-4629` |
| S5 | 协议9 解析级别 | 缺 `mac_only`（`reflex_web.py:3986-3996`） | 含 `mac_only`（`main_gui.py:1451`） |
| S6 | PB 帧类型 | 协议9 恒 `sof`（`reflex_web.py:38`，无 UI 改）；协议10/11 不传 `frame_type` | `pb_only` 时下发（`main_gui.py:4622-4626` → `protocol_registry.py:407-446`） |
| S7 | ED 包装 | 无开关、无格式选择；gx 帧静默错位 | 复选框 + 格式下拉（`main_gui.py:1886-1906`）+ 逐帧打分（5014-5060）+ 双布局（5169-5240） |
| S8 | 字段层级 | `indent=(len-lstrip)//2`（`reflex_web.py:646-667`） | `_field_level_map` 归一化深度 + `_format_tree_field`（4 空格/级，`main_gui.py:872-896`） |
| S9 | 协议重解析 | 无（桌面弹窗支持换协议重解，`main_gui.py:6929-6982`） | 有 |
| S10 | 校验 | `_get_validator` NameError（`reflex_web.py:560`）；且不应用 `_apply_strip` | `build_validator_map()`（`protocol_registry.py:320-326`）+ 校验剥离链（`main_gui.py:6711/6749`） |
| S11 | 奇数长度 | 静默砍末位（`reflex_web.py:577-578`） | 弹窗中止（`main_gui.py:5307-5311`） |

---

## 3. 查询页 / 报文工具 / 组帧（子任务：web-single-frame-alignment 的查询侧）

| # | 项 | Web | 桌面 |
|---|---|---|---|
| Q1 | 南网 DI 的 AFN 列 | `afn = di3 & 0x0F`（`lookup_utils.py:92`）→ 实测 `添加任务` 显示 `08H` | `afn = di1` + `AFN_MAP` 名称（`main_gui.py:2234-2235`）→ `02H` |
| Q2 | 协议10 查询 | 复用协议9 表（`lookup_utils.py:328-331`，源码自述 TODO）→ 实测搜「关联」0 命中，40 条 | `GWNewGenParser` 7 类 49 条（`main_gui.py:3669-3685`） |
| Q3 | 协议8 查询 | 属性/方法恒 `-`（`lookup_utils.py:266-271`）→ 实测 777 行全占位 | 从 `CLASS_ID_MAP/OI_TO_CLASS_ID` 填（`main_gui.py:3813-3823`） |
| Q4 | 自定义条目 | 4 处只读（南网 DI / 645 DI / 国网 AFN / OBIS 标记） | `custom_di_store` / `dlt645_di_lookup.add_custom_di` / `gdw_custom_afn.json` CRUD |
| Q5 | 645 DI 列 | 只用前 5 列，丢 `is_custom`（`lookup_utils.py:187-193`） | 6 元组含自定义标记（`dlt645_di_lookup.py:17/96`） |
| Q6 | 报文工具 CRC-24 | `rev=False`（`web_utils.py:850`）→ 实测 `0xEAC98F` | `rev=True`（`message_tool_widget.py:24`）→ `0xFC4D81`（与三处解析器一致） |
| Q7 | 报文工具 CRC-32 | `crcmod.predefined.crc-32` | `mkCrcFun(0x104C11DB7, init=0, rev=True, xorOut=0xFFFFFFFF)` → **实测 200 组随机输入 0 差异，二者等价，勿改** |
| Q8 | 组帧 | 协议集一致（南网/645/国网/698，`reflex_web.py:4947-6928`） | 缺串口下发/收帧回读、645 长度告警与广播地址联动（`frame_gen_widget.py:1617-1825/3846-3867`） |
| Q9 | 「16进制」复选框 | 死控件（两端都是） | 死控件 |

---

## 4. 重复实现与性能（子任务：web-shared-parse-core / web-parse-perf）

重复实现（D1 clean_hex_input 未漂移；D2-D6 已漂移；D7/D8 当前一致但属复制体）：

- D1 `web_utils.py:25-39` ↔ `main_gui.py:4649-4665`
- D2 `strip_csg_monitor_prefix`（Web 无行映射）
- D3 `strip_csg_new_gen_prefix` ↔ `_strip_csg_new_gen_frame_prefix`
- D4 `strip_gw_new_gen_prefix` ↔ `_strip_gw_new_gen_prefix`（**最严重**）
- D5 `extract_frames_for_protocol` ↔ `_extract_frames_for_protocol`
- D6a-d 摘要分派 + `get_csg_new_gen_summary` + `extract_csg_core_content` + `get_hdc10_summary`
- D7 `_safe_parse_to_table` DLT645 分支（`reflex_web.py:483-529`）↔ `protocol_registry.DLT645GuiParser`（`355-404`）——逐字一致
- D8 `APDUParserWeb`/`WrapperParserWeb`（`reflex_web.py:436-453`）↔ `_APDUParserGuowang`/`_WrapperParser`/`_APDUParser`（`protocol_registry.py:331-352`）
- D9 `tool_msg_to_pn`/`pn_to_msg`/`msg_to_fn`/`fn_to_msg` 四个直通别名（`web_utils.py:745-762`）
- D10 测试侧第三份复刻：`test/test_csg_batch_prefix.py:19-48`

硬编码协议分支 ≈145 处（Web）：`PROTOCOL_OPTIONS` 12 + `FEEDBACK_PROTOCOL_OPTIONS` 13 + `_get_parser` 13 + `_get_validator` 12 + UI `rx.cond` 28 + 状态层 15 + 组帧 12 + `web_utils.extract_frames_for_protocol` 12 + `get_frame_summary` 3 + `lookup_utils.QUERY_CONFIG` 12 + `_SEARCH_FUNCTIONS` 12 + `_is_eb_query` 1。

性能：

- P1 每请求新建 parser（`reflex_web.py:417-481`）：`ProtocolFrameParser.__init__→_load_custom_di()` 每次读 `custom_di.json`（`protocol_parser.py:787-795`）；`DLT69845Parser.__init__` 每次建 crcmod（`dl_t698_45_parser.py:37-38`）
- P2 批量准备阶段零 yield（首个 yield 在第 100 帧，`reflex_web.py:973`）；输入上限 50MB（`reflex_web.py:749-751`）
- P3 逐帧二次正则清洗（`reflex_web.py:901-903`）
- P4 逐字符 Python 级 hex 过滤（`web_utils.py:311/362/365/368/377`）
- P5 摘要线性 `_find_field` 反复扫表（`web_utils.py:393-398`）vs 桌面先建 dict
- P6 全量结果常驻 `_batch_all_results` + 导出 `json.dumps(indent=2)`（`web_utils.py:975-1000`）
- P7 `rx.download(data=...)` 整串（`reflex_web.py:1139-1156`）
- P8 Wrapper 提取兜底把整段文本当单帧（`web_utils.py:301`）
- P9 明细表无分页（`reflex_web.py:4683-4700`）

---

## 5. 文档滞后

`AGENTS.md §1`：「HDC 1.0（索引 11）目前仅在 PySide6 主程序支持；Reflex Web 版支持索引 0-10（11 种）」——实际 Web 已支持 11（`reflex_web.py:474-477/919-924`、`web_utils.py:383-384/552-612`、`lookup_utils.py:334-355`）。
`AGENTS.md §7` 测试清单未含 Web 批量摘要/提取覆盖。

---

## 6. 勘误与实施反证（2026-09-15，P0 实施期间）

| 原结论 | 核实结果 | 依据 |
|---|---|---|
| S1/§2「协议9 剔除不幂等，连点两次 = 二次裁剪」 | **误判，撤销** | Web `parse_frame` 每次执行 `self._apply_strip(self._clean_hex(self.frame_hex))`，`frame_hex` 从未被回写 → 同一输入恒定同结果，**本来幂等**。实施中按原结论加「缓存键跳过」后，第二次解析拿到的是**未剔除**的原始字节（`_reflex_internal_init` State 实例实测 `strip#1=0304` / `strip#2=0102030405`），已撤销并改为纯函数 `strip_frame_bytes`。 |
| §1 B10「Web 失败判定看首行」 | **成立，已修**；但原引用证据（旧行号 747 标题行 + 754 ❌ 行）**误读**——两者是并列分支（mac_only 信标标题 / mac_only SACK 报错），不共存。已替换为实测用例：协议9 `mac_only` 短 MAC 帧 `49 5C 2F AA BB CC DD EE` → 行0「解析模式」、行1 ❌（`csg_new_gen_parser.py:843` 写入 | `_parse_mac_frame` 追加） |
| §1 B6「协议9 前缀剥离缺 mac_only 直通」 | **成立，已修**（P0 顺带）：Web 的 `strip_csg_new_gen_prefix` 对 `mac_only` 走 FC 扫描分支 → 实测 8 字节 MAC 帧整行被丢弃（0 帧）；已与桌面同口径直通（`main_gui.py:4942`） |
| §1 B11「空表语义两侧不一致」 | **成立，两侧已统一为「失败」** | Web `_808-932` 原判失败、桌面 `any([])==False` 判成功；现两侧同为「空表 ‖ 存在 ❌ 行 → 失败」。 |
| §2 S12「桌面 checksum 口径」类推断 | 未复核项 | 本轮未触及，留待对应子任务按需核实（**凡推断型结论必须实测后再动手**）。 |

**方法论教训**：子代理的「推断型缺陷」结论（依据「没有缓存 ⇒ 不幂等」这类推理）必须先用真实调用路径复现再改代码；本次若不复核就会把一个正常功能改坏。
