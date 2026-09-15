# Web 版解析 P0 缺陷修复（校验 / 失败判定 / 预处理 / 帧类型 / ED 广西台体 / 查询页事实错误）

## Goal

修掉 Web 版解析链路上**会让用户拿到错误结果或错误结论**的 10 条缺陷（父任务 `research/web-parse-audit.md` §1/§2/§3 的 P0 项），并顺手消除两处跨端语义不一致。修复后 Web 与桌面在「校验是否通过、批量状态列、奇数长度输入、剔除幂等、PB 帧类型、ED 包装格式、查询页事实数据」上同口径。

## Confirmed Facts（本次审计实测，行号对应 main @ 9d0bb4e）

1. **校验不可用**：`reflex_web/reflex_web/reflex_web.py:560` `return validators.get(p, NWValidator)()` 中 `p` 从未定义（AST 全模块无 `p` 绑定，无 `global p`）。异常只被 `except ImportError`（561）兜住，NameError 逃到 `verify_frame` 的 `except Exception`（730）→ 文案「校验出错: name 'p' is not defined」。主会话实测（抽出函数体 exec）复现 `NameError: name 'p' is not defined`。全仓无 Web 校验测试。
2. **失败判定只看首行**：`reflex_web.py:928-932` 判 `result[0][0]`；而解析器会把 ❌ 行写在**表中途** —— 实测 `csg_new_gen_parser.py:843` 先追加 `("解析模式", "", "仅MAC帧", …)`，随后 `_parse_mac_frame` 追加 `("❌ 解析失败", …, "MAC帧长度不足(需要>16字节)")`：输入 `49 5C 2F AA BB CC DD EE` + `parse_level="mac_only"` 时 `rows[0]` 无 ❌ 而 `rows[1]` 是 ❌ → 该帧在 Web 被标「成功」（反向验证：还原旧判定后状态确为「成功」）。桌面用全表扫描但只认精确串 `"❌ 解析失败"`（`main_gui.py:7555-7557`），漏 `❌ 单跳MAC帧头不完整` 等 7 类标记 → 两侧统一为「以 `❌` 开头」。
   （原文引用的「旧行号 747 标题 + 754 ❌」经复核属**两个并列分支**、不共存，已更正为上述实测用例。）
3. **奇数长度静默截断**：`reflex_web.py:577-578` `cleaned = cleaned[:-1]`；桌面弹窗中止（`main_gui.py:5307-5311`「输入长度为奇数，十六进制字符串必须是偶数长度！」）。
4. ~~**剔除不幂等**~~ **（审计误判，已核实撤销）**：原报告称 `reflex_web.py:614-615` 每次解析无条件 `_apply_strip` 会导致「连点两次 = 二次裁剪」。实施时核实：Web 每次都从**原始** `frame_hex` 重新清洗后剔除（`self._apply_strip(self._clean_hex(self.frame_hex))`，索引 `frame_hex` 未被回写），因此同一输入恒定得到同一结果，**本来就是幂等的**——差异只在实现方式（桌面回写输入框 + `_csg_last_stripped_hex` 缓存 vs Web 纯粹重算）。
   → 本任务的处置：不引入缓存（引入反而会让第二次解析拿到未剔除的原始字节，实施中已实测到该回归并撤销），改为把切片逻辑抽成纯函数 `web_utils.strip_frame_bytes`，并用「同一输入重复调用结果一致」+ State 层连续两次调用断言把该不变式钉住。
5. **PB 帧类型不下发**：`reflex_web.py:620-637` 协议10/11 只传 `parse_level`（+channel）；`gw_new_gen_parser.py:159` `frame_type = kwargs.get('frame_type', None)` → `231-241` 落 `1241-1242`「⚠️ 未知帧类型 … 无对应解析逻辑」；`hdc10_parser.py:261` 缺省 `frame_type=1`（SOF）；桌面在 `pb_only` 时注入（`main_gui.py:4622-4626`）。协议9 级别下拉缺 `mac_only`（`reflex_web.py:3986-3996` vs `main_gui.py:1451`；parser 分支 `csg_new_gen_parser.py:737-743`）。
6. **ED 广西台体错位**：Web 无 ED 开关/格式选择，整帧交给 parser；parser `_parse_ed_wrapper`（`csg_new_gen_parser.py:518-622`）只有 PLC2.0 布局（573-580 固定 `ch=data[0]; ts=data[1:5]; pb_len=data[7:9]; business=data[9:]`），而广西台体（gx）公共头是 8 字节（`main_gui.py:5171-5180`：`ts=data[0:4]; ch=data[4]; pb_cnt=data[5]; pb_len=data[6:8]; business=data[8:]`）→ gx 帧业务整体错位 1 字节。**桌面在未勾选 ED 复选框时走 parser 同一分支，同样错位**（两侧共同缺陷）。
7. **南网 DI 查询 AFN 列算错**：`reflex_web/reflex_web/lookup_utils.py:92` `afn = di3 & 0x0F`；权威 `main_gui.py:2234` `afn_val = di1` + `AFN_MAP` 名称；`protocol_parser.py:519-541` 键序 `(DI3,DI2,DI1,DI0)` 与 `# AFN=02H 管理任务` 注释自证 DI1=AFN。实测 `_search_south_di("添加任务")` → `['E8','02','02','01','08H','添加任务']`（应 `02H`）。
8. **协议10 查询页抄协议9**：`lookup_utils.py:328-331` `_search_gw_newgen` 直接 `return _search_csg_service(keyword)`（注释「后续可补充」）。实测搜「关联」0 命中、总 40 条；桌面用 `GWNewGenParser` 7 类表共 49 条（`main_gui.py:3669-3685`）。
9. **协议8 查询页属性/方法恒占位**：`lookup_utils.py:266-271` 写死 `"-"`。实测 777 行全为 `'-'`；桌面从 `OI_TO_CLASS_ID`+`CLASS_ID_MAP` 填（`main_gui.py:3813-3823`）。
10. **报文工具 CRC-24 参数错**：`web_utils.py:850` `crcmod.Crc(0x1800063, initCrc=0, rev=False, xorOut=0)`；全项目 4 处权威实现均 `rev=True`（`csg_new_gen_parser.py:20`、`hdc10_parser.py:22`、`gw_new_gen_parser.py:22`、`message_tool_widget.py:24`）。实测同一输入：Web `0xEAC98F` vs 权威 `0xFC4D81`。（反例：CRC-32 两端等价，实测 200 组随机输入 0 差异，**不得改动**。）

## Requirements

### R1 校验可用且与解析同预处理（Web 内部一致；与桌面 verify 的差异见下）

- `_get_validator` 不得引用未定义变量：改为按 `self.current_protocol` 取校验器（`protocol_registry.make_validator(i)`，该模块无 Qt 依赖）。
- `verify_frame` 的输入预处理与 Web 侧 `parse_frame` 完全一致：`hex_to_bytes_strict` → `strip_frame_bytes`（R3/R4）。理由：Web 解析用的是剔除后的字节，校验若用原始字节会出现「解析通过、校验失败」的自相矛盾。
- **与桌面的既定差异（复核发现，此处明确记录）**：桌面 `verify_single`（`main_gui.py:5406-5428`）只做清洗、**不做头/尾剔除**（桌面仅在解析弹窗/批量/CLI 等路径做 ED 包装与剔除）。因此协议9/10 配了「剔除前/尾」时，Web 校验剔除后帧、桌面校验原始帧 → 同一输入两端结论可能不同。本任务选择保留 Web 的「与解析一致」语义，并把「桌面 verify 是否补剔除」列入子任务 `09-15-web-shared-parse-core`（属桌面行为变更，需单独回归）。
- 校验失败/成功文案沿用现有格式（`[通过]/[失败] summary` + 逐项 ✅/❌ 行），不改变既有 UI 结构。

### R2 批量失败判定（两侧统一口径）

- 判定规则：**结果表中存在字段名以 `❌` 开头的行 → 失败**（覆盖 `❌ 解析失败`/`❌ 单跳MAC帧头不完整`/`❌ MPDU解析失败` 等 8 类实测标记）；不再只看首行。
- 失败摘要取该 ❌ 行的第 4 列（说明）；无说明则「解析失败」。
- **空表语义两侧统一为「失败」**：Web `parse_batch` 与桌面 `main_gui.parse_batch` 同为「`table_data` 为空 或 存在 ❌ 行 → 失败」（桌面原实现 `any([]) == False` → 成功，属缺陷）。
- 纯函数落点：`web_utils.batch_frame_outcome(rows, ok_type_name) -> (status, 类型列, 摘要列)`（失败时类型列固定「解析失败」，摘要取 ❌ 行说明）。

### R3 奇数长度 hex 报错

- Web 单帧/校验：奇数长度直接抛错，文案与桌面一致（`输入长度为奇数，十六进制字符串必须是偶数长度！`），**不截断**。
- Web 批量逐帧同样不裁剪（交由 `bytes.fromhex` 报错 → per-frame 记「异常」，摘要含帧片段），与桌面批量同口径。
- 纯函数落点：`web_utils.hex_to_bytes_strict(text) -> bytes`（空串 → `报文为空`）。

### R12 复核（trellis-check）追加修复

- **桌面 ED 调用点漏传 wrapper**：`main_gui.py` 的快捷解析小窗预处理曾调用 `_parse_ed_monitor_header(raw)`（旧默认值硬编码 `"plc2"`）→ gx 帧在该路径仍错位 1 字节（复核实测：业务偏移 15 而非 14）。修法：① 调用点显式传 `wrapper=self._ed_wrapper_for_frame(raw)`；② 两个 ED 解析入口的 `wrapper` 默认值改为 `None` = 「按当前下拉（auto 逐帧识别）」，消除「漏传即错」的隐患；③ `test/test_ed_gx_wrapper.py` 增 3 条「不传 wrapper 也走自动识别」断言（26 项）。
- **打包声明**（PyInstaller 无法静态分析 `importlib` 加载）：`validator/__init__.py` 显式 re-export `GWNewGenValidator`/`HDC10Validator`（此前缺，桌面 spec 也只声明了 hdc10），`reflex_web/reflex_web_exe.spec` 补 `protocol_registry`/`parser_registry`/`hdc10_parser`/`hdc10_mme_parser`/`validator.hdc10_validator`，`reflex_web/debug_web.spec` 与 `南网协议解析工具.spec` 补 `protocol_registry`/`parser_registry`（桌面 spec 另补 `validator.gw_new_gen_validator`）。
- **查询页关键词匹配范围**：协议10 Web 版对 4 列（含「说明」）匹配，桌面只匹配 类别/代码/名称 → Web 为超集（实测搜「安全机制」Web 28 条、桌面 0 条）。保留 Web 行为（更有用）并在此与 AGENTS §8.31 注明差异，避免「同口径」误读。
- **`mac_only` 批量直通**：Web 前缀剥离对 `mac_only` 曾走 FC 扫描分支 → 整行被丢弃（实测 0 帧）；改为与桌面同口径直通。

### R4 剔除（幂等性 + 可测）

- Web 保持「对原始输入重算」的语义（同一输入恒定结果）；切片逻辑抽为纯函数 `web_utils.strip_frame_bytes(frame_bytes, head, tail)`，越界仍报错（沿用现文案）。
- 不回写用户输入框（与桌面的回写策略有意不同：Web 输入框是受控 textarea，回写会打断编辑；字节高亮在 Web 尚不存在，无需坐标一致）。
- **不引入** `_csg_last_stripped_hex` 式缓存（实施中已验证：缓存会让第二次解析拿到未剔除的原始字节 → 真回归）。

### R5 PB 帧类型下发 + 协议9 mac_only

- 新增纯函数 `web_utils.parse_kwargs_for(protocol_index, parse_level, pb_frame_type, gw_frame_type, channel) -> dict`，单帧与批量共用（消除 `reflex_web.py` 两处重复的 3 段 if/elif）：
  - 协议9：`{"parse_level": ..., "channel": ..., "pb_frame_type": ...}`；`pb_frame_type` 在 `mac_only`/`pb_only` 下发。
  - 协议10/11：`{"parse_level": ..., "channel": ..., "frame_type": <int>}`，仅 `pb_only` 下发（其余级别不下发，保持 parser 默认）。
  - 其他协议：`{}`。
- Web 协议9 解析级别下拉补 `mac_only`（"仅MAC帧"）；协议10/11 新增 PB 帧类型下拉（pb_only 时可见），取值与桌面一致（协议10/11：SOF/信标/选择确认/网间协调 → 1/0/2/3；以解析器 `kwargs` 语义为准）。
- 协议9 的 `pb_frame_type` 下拉在 `mac_only`/`pb_only` 时可见（与桌面 `main_gui.py:3290-3292` 同规则）。

### R6 ED 包装格式自动识别（parser 层，两端共享）

- 在 `csg_new_gen_parser.py` 新增模块级 `detect_ed_wrapper(frame_bytes, fallback="plc2") -> "plc2"|"gx"`：逐候选打分（`+2` 剥头后业务帧首字节符合 FC MPDU 特征：bit3 接入指示=1 且 bits0-2 定界符 0~3；`+1` 物理块长度字段与业务长度自洽：`(业务长-16)` 为 `pb_len` 正整数倍且 `pb_len` ∈ 常用 PB 尺寸集，倍数 ≤5；平局优先 plc2；无正分回退 `fallback`）。算法与桌面 `main_gui._detect_ed_wrapper`（`main_gui.py:5014-5060`）一致。
- `_parse_ed_wrapper` 支持两种公共头布局（PLC2.0 9 字节 / 广西台体 8 字节），标题行分别为 `── PLC2.0 监控包装头 ──` / `── 广西台体监控包装头 ──`，字段偏移与桌面 `_parse_ed_monitor_header`（`5172-5240`）一致；`gx` 无 `Payload CRC` 行。
- `parse_to_table` 新增可选 `ed_wrapper=None`（None=自动识别），透传给 `_parse_ed_wrapper`。
- **单一实现**：`main_gui._detect_ed_wrapper` 改为委托 `csg_new_gen_parser.detect_ed_wrapper`（桌面下拉的手动值作为 `fallback` 传入），删除桌面重复的打分实现。
- **包装头消费者同步**：摘要侧改按「含 `监控包装头`」判定，同时支持两种标题（Web `web_utils.py:412`；桌面 `main_gui.py:7910`，包装名按标题区分 `PLC2.0监控包装帧` / `广西台体监控包装帧`）。

### R7 南网 DI 查询 AFN 列 = DI1

- `lookup_utils._search_south_di`：`afn = di1`（键序 `(di3, di2, di1, di0)`），列值形如 `02H 管理任务`（与桌面 `main_gui.py:2250` 同格式，含 `AFN_MAP` 名称）。

### R8 协议10 查询页使用国网新一代表

- `_search_gw_newgen` 改为读取 `GWNewGenParser` 的 7 类表：`MSG_IDS`（含安全机制说明）/`PORT_NAMES`/`DELIMITER_TYPES`/`MSDU_TYPES`/`PROTOCOL_TYPES`/`SEND_TYPES`/`BROADCAST_DIRS`，列 `类别/代码/名称/说明`（与桌面 `main_gui.py:3669-3685` 同口径、同条数）。`QUERY_CONFIG[10]` 列改为 4 列。
- 允许删除代码中的「先用新一代载波数据」兜底注释与实现（协议10 不再复用协议9 表）。

### R9 协议8 查询页属性/方法列

- `_search_698_oi`：`属性`/`方法` 从 `OILookup.OI_TO_CLASS_ID` + `CLASS_ID_MAP[class_id]["attributes"/"methods"]` 生成（格式 `k:v, k:v`，与桌面 `main_gui.py:3813-3818` 一致）；无类映射时保持 `-`。

### R10 报文工具 CRC-24 参数

- `tool_crc24_newgen`：`rev=True`（其余参数不变），与 `csg_new_gen_parser._crc24_func` 数值一致。
- 不得改动 `tool_crc32_newgen`（已等价）。

### R11 文档

- `AGENTS.md §1`：修正「Reflex Web 版支持索引 0-10」为实际支持 0-11，并注明协议11 的 Web 侧与桌面差异（无实时监控器/组帧）。
- `AGENTS.md §7`：测试清单补 `test/test_web_parse_fixes.py`。
- `main_gui.py:CHANGELOG` 头部新增 1.23.12 条目（Web P0 修复 + 空表语义统一 + ED 自动识别下沉）；`APP_VERSION` → `1.23.12`。

## Acceptance Criteria

1. `test/test_web_parse_fixes.py`（新增，登记进 `release_check.py:CORE_TESTS`）逐条断言：
   - a. `web_utils.hex_to_bytes_strict("681101010")` 抛 `ValueError` 且文案含「奇数」；`"6811010101"` 正常。
   - b. `web_utils.batch_frame_status([("── 信标帧载荷（仅MAC帧模式）──","","","",None,None), ("❌ 解析失败","","","帧长度不足",None,None)])` → `("失败", "帧长度不足")`。
   - c. `batch_frame_status([])` → 失败；`batch_frame_status([("帧类型","","","命令帧",0,0)])` → 成功。
   - d. `web_utils.strip_frame_bytes(b"\x01\x02\x03\x04\x05", 1, 1)` → `b"\x02\x03\x04"`；重复调用结果一致；超界抛 `ValueError`；State 层连续两次 `_apply_strip(_clean_hex(frame_hex))` 结果相同（重复点击解析不二次裁剪）。
   - e. `web_utils.parse_kwargs_for(10, "pb_only", "sof", 2, "plc")` 含 `frame_type == 2`；`parse_kwargs_for(10, "auto", ...)` 不含 `frame_type`；`parse_kwargs_for(9, "mac_only", "beacon", 1, "hrf")` 含 `pb_frame_type == "beacon"` 与 `channel == "hrf"`；`parse_kwargs_for(0, ...)` 为空 dict。
   - f. **端到端 pb_only**：用 `test/test_gw_batch_parse.py` / `test_gw_new_gen.py` 现成帧，`GWNewGenParser().parse_to_table(frame, parse_level="pb_only", channel="plc", frame_type=...)` 不出现「未知帧类型」；缺 `frame_type` 时出现（证明该参数确实生效）。
   - g. **ED gx 端到端**：构造广西台体 ED 帧（8 字节公共头 + 合法 CSG 业务帧）→ `CSGNewGenParser().parse_to_table(ed_gx)` 首行为 `── 广西台体监控包装头 ──`、`单个物理块长度` 解析值正确、`── 业务帧 ──` 之后的业务帧字段与「直接解析业务帧」一致；同帧按 plc2 布局解析时结果不同（证明格式判别有效）；`detect_ed_wrapper(gx)` == "gx"、`detect_ed_wrapper(plc2)` == "plc2"。
   - h. `lookup_utils.get_lookup_data(0, "添加任务")` 的 AFN 列含 `02H`（不再是 `08H`）；`get_lookup_data(10, "关联")` 命中 ≥1 条且 `get_lookup_data(10, "")` 条数 = 49；`get_lookup_data(8, "")[0]["属性"]` 非 `-`（对存在类映射的 OI）。
   - i. `web_utils.run_tool("crc24_newgen", "112233")` 的 CRC 值与 `csg_new_gen_parser._crc24_func(bytes.fromhex("112233"))` 一致。
   - j. Web 协议9 级别下拉选项集合包含 `mac_only`（从模块常量断言，不解析组件源码文本）。
2. 校验链路修复可被观测：`web_utils`/`lookup_utils` 测试通过之外，`protocol_registry.make_validator(i)` 对 0..11 全部返回实例（既有 `test/test_protocol_registry.py` 已覆盖映射，本任务补 Web 侧调用点断言）。
3. 桌面回归：`python test/test_ed_gx_wrapper.py`、`test/test_ed_fallback_fix.py`、`test/test_csg_summary.py`、`test/test_csg_batch_prefix.py`、`test/test_gw_monitor_summary.py`、`test/test_csg_sequence_model.py` 全过（ED 委托重构 + 空表语义改动的回归网）。
4. `python release_check.py` 无 FAIL（新测试已登记 `CORE_TESTS`）。
5. `AGENTS.md §1/§7` 与 `main_gui.py:CHANGELOG`（1.23.12）与实现一致。

## Out of Scope

- 批量行号/跨行 payload 状态机/EDA5/测试模式摘要/导出字段详情（子任务 `web-batch-alignment`）。
- 单帧字节范围高亮、双击深度解析、协议9 通道下拉、4 字节反转、按其他协议重解析、查询页 CRUD（子任务 `web-single-frame-alignment`）。
- 共享核心抽取与 `protocol_registry` 全面接入、`web_utils` 复刻体删除（子任务 `web-shared-parse-core`）——本任务只在 R6 做一次「ED 打分下沉」的最小单源化，其余复刻体留给该子任务。
- 性能（子任务 `web-parse-perf`）。
- ED 包装格式的 **Web UI 选择器**（本任务靠 parser 自动识别解决正确性；显式选择器随 `web-single-frame-alignment`）。

## Risks / Deferred

- **空表语义改动触及桌面**（`main_gui.parse_batch`）：ED 三分支自带 `status`（`7479-7541`）不受影响；受影响的是通用解析分支。已用 `test_ed_fallback_fix.py`/`test_csg_batch_prefix.py`/`test_batch_*` 作为回归网，并在 `release_check.py` 全量跑。
- **ED 自动识别的歧义**：打分平局优先 plc2、无正分回退调用方 `fallback`。桌面下拉手动值仍是最终 fallback，行为不变；Web 无下拉 → fallback 恒 `plc2`（与原行为一致，只是 gx 帧从「错」变「对」）。
- **协议10/11 PB 帧类型取值**：以解析器 `frame_type` 语义为准（`gw_new_gen_parser` 与 `hdc10_parser` 的取值集不同，实现时以两端解析器实际分支为准并写进测试，不凭文档猜）。
- **Web 端无端到端运行时测试**：本任务断言纯函数 + parser + 查询层，State 层改动以「调用点薄 + 纯函数承载逻辑」保证可测；真机验证留给 `reflex_web` 本地起服（后续子任务补充）。
