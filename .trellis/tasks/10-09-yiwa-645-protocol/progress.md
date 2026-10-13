# 执行进度与证据：依瓦定制645（协议13）

> 本档记录每阶段的**实际命令 + 实测输出 + 复核结论**，作为 `prd.md` AC1~AC16 的证据来源。
> 阶段划分见 `implement.md`；审查点 A~F 是推进门槛。

---

## 阶段 0：前置确认

### 0.1 既有未提交改动（**本任务提交时不得混入**）

阶段 0 实测 `git status --short` — 已修改（15 项，属**既有**工作，非本任务产出）：

```
 M .gitignore
 M .trellis/workspace/Liruitao1993/journal-1.md
 M 2222.iss
 M AGENTS.md
 M CLAUDE.md
 M README.md
 M csg_new_gen_parser.py
 M frame_gen_widget.py
 M main_gui.py
 M protocol_registry.py
 M release_check.py
 M test/test_csg_new_gen.py
 M test/test_protocol_registry.py
 M "南网协议解析工具.spec"
 M "南网解析工具.iss"
```

未跟踪（既有，非本任务产出）：`.acl-recovery/`、`.aoci/`、`aoci.txt`、`aoci.code.txt`、`aoci.meta.txt`、
`AGENTS.md.backup.20261008_*`、`_tmp_check_beacon.py`、`collapsible_section.py`、`csg_frame_reverse.py`、
`csg_frame_templates.py`、`csg_link_frame_gen.py`、`csg_new_gen_frame_gen.py`、`csg_test_frame_gen_widget.py`、
`test/test_batch_toolbar_layout.py`、`test/test_collapsible_section.py`、`test/test_csg_frame_gen_gui.py`、
`test/test_csg_frame_reverse.py`、`test/test_csg_frame_templates.py`、`test/test_csg_link_frame_gen.py`、
`.trellis/tasks/09-30-csg-link-layer-frame-gen/`、`.trellis/tasks/10-06-aoci-integration/`。

> ⚠ **注意**：`protocol_registry.py`、`main_gui.py`、`frame_gen_widget.py`、`南网协议解析工具.spec`、
> `test/test_protocol_registry.py`、`release_check.py` **在阶段 3/4/6 会被本任务继续修改** ⇒
> 阶段 7.2 必须逐 hunk 区分「既有改动」与「本任务改动」，不能整文件提交。

### 0.2 协议文档与图片在位

```
协议文档/13.依瓦定制645协议/
├── 依瓦定制645协议.docx      (123,912 B)
├── 依瓦定制645协议.md        (8,401 B, UTF-8 无 BOM)
└── images/
    ├── 图1-数据格式.png          (58,246 B)  ← 数据域结构 ID+FL+数据
    ├── 图-COMMAND位定义.png      (23,176 B)  ← COMMAND 高/低 4 位划分
    ├── 图-地址域示例.png         ( 2,156 B)
    └── 图-工作流程.png           (36,928 B)
```

`test/_path_setup.py` 在位（`import _path_setup  # noqa: E402,F401` 可用）。

### 0.3 基线回归

| 测试 | 基线 | 8 阶段中复跑 |
| --- | --- | --- |
| `test/test_dlt645_pv_ext.py` | RC=0 ✓ | ☐ |
| `test/test_dlt645_tolerant_parse.py` | RC=0 ✓ | ☐ |
| `test/test_protocol_registry.py` | RC=0 ✓ | ☐ |
| `test/test_web_landing.py` | RC=0 ✓ | ☐ |

基线任务 `.pi/tasks/01a11b9e-.../bb99d4bc2.output`（`bg_run`，已 completed / exitCode=0）：4 个文件**均 RC=0**。
阶段 7 发版门禁会用 `release_check.py` 拿带 PASS/FAIL 计数的正式基线再比一次。

---

## 阶段 1：线格式核心 —— ☑ 完成并通过独立验证

### 交付物（3 个新文件；**未改任何既有文件**，已用 `git status` 核对）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `yw645_wire.py` | 550 | 线格式编解码**唯一来源**：常量、`MODE_*`、地址域高字节在前编解码、12 bit 长度拼接、`calc_cs`、`apply_mask`(±0x33)、`encode_items`/`decode_items`/`score_form`、`encode_frame`、`frame_total_len`、`is_frame`、`resolve_mask` |
| `yw645_di.py` | 129 | 附录A 数据项表**唯一来源**（2 项）+ 字面/字节交换**双索引** + `di_lookup`/`di_exists`/`di_payload_note` |
| `test/test_yw645_wire.py` | 520 | 250 项断言，含**运行时读文档**的 oracle 对拍防线 |

依赖检查：`yw645_wire.py` 只 import `__future__`/`dataclasses`/`typing`；`yw645_di.py` 只 import `__future__`/`typing` + `yw645_wire`。
**无 Qt、无任何协议模块依赖** ✓

### 实测证据

```
pwshu '$env:PYTHONIOENCODING="utf-8"; python test/test_yw645_wire.py'
结果: PASS=250 FAIL=0        rc=0
ruff check yw645_wire.py yw645_di.py test/test_yw645_wire.py  → All checks passed!
```

（须带 `PYTHONIOENCODING=utf-8`：Windows 控制台默认 GBK 编不出 `−`/`⚠`；`release_check.py` 已对子进程注入该变量。）

### 独立复核（**不复用子代理自述**，由主会话另写脚本）

| 复核项 | 结论 |
| --- | --- |
| 9 条示例抽帧 | 文档中 **5 条带真 CS**（L171/L215/L236/L251/L269）、**4 条 CS 为字面占位符 `CS`**（L137/L153/L176/L196） |
| 独立算 CS（自写 `sum(b[:10+n])`，不用模块） | 5 条带 CS 的帧**全部逐条吻合**：`B4`/`B2`/`31`/`9C`/`AC` |
| 模块 `calc_cs` 对拍 | 传 `body=frame[:10+n]`（契约约定）后**与独立算一致** ✓ |
| CS 范围反证 | `body[1:]` 与 `body+CS` 两种错范围**均不等于**正确值 ✓（5 条各 2 项） |
| 长度拼接 | 9 条 `((cmd&0x0F)<<8)\|L` 与 `len(frame)==n+12` **全部自洽** ✓ |
| 地址 | `45000000013`→`04 50 00 00 00 13`、`103000000010`→`10 30 00 00 00 10` **逐字节吻合**（3 条独立示例） ✓ |
| ±0x33 | `36 13`→`03 E0`、`37 13`→`04 E0`、X5 14 字节→`04 E1 31 32 33 34 35 36 37 38 39 3A 30 3B`（尾部恰为 ASCII `"123456789:0;"`，**铁证**）；往返一致 ✓ |
| items 往返 | 请求 `00 10 00 20` ⇄ `encode_items(with_fl=False)`；回复 `00 10 01 01 00 20 06 10 30 00 00 00 10` ⇄ `with_fl=True`；字段 `(ID,FL,data)` 往返一致 ✓ |
| 形态判别 | `00 10 00 20`→`request`；X2 数据域(13B 奇长)→`reply`；**互不误判** ✓ |
| D1 写模式 | `MODE_WRITE_REQUEST = MODE_WRITE_RESPONSE = None`；AST 扫常量池**无 0x50/0x60** ✓ |
| 定界 | 全模块**无 `find`/`index` 切帧**；切帧只走 `frame_total_len` ✓ |
| **变异反证（主会话自跑）** | `calc_cs` 范围 `sum(body)`→`sum(body[1:])` → `PASS=226 FAIL=24` **实测变红**；还原后 250/0 ✓ |

### 审查点 A 结论：**通过**（逐字节 oracle 100% 命中 + 独立复核一致）

### 带入阶段 2 的已知事项

1. **`resolve_mask` 的固有边界**：当两种 0x33 形态都自洽且 ID 均不在附录A 时（如透传载荷 `37 14` ↔ `04 E1`），
   **纯线格式层数学上不可判别**。阶段 2 必须提供 `assume_masked` 显式覆盖参数。
2. 因此 `implement.md` 2.5 的「同一帧两种形态断言相同字段结果」**仅对 DI 命中的帧**（X1/X2）成立；
   未知 ID 的透传帧需按「显式覆盖」或「两种形态并列输出 + 判别依据」处理。
3. **空数据域 → `FORM_AMBIGUOUS`**（两形态各得 4 分同分）。建议阶段 2 对空数据域直接按「请求」呈现
   并**不**出歧义提示（裸查询帧是正常业务），避免噪声。
4. `calc_cs(body)` 的 `body` = 帧头 … 数据域末字节（**不含** CS 与 `16H`）；`decode_items` 返回
   `(List[DataItem], form)`，`form ∈ {request, reply, ambiguous, malformed}`；
   `encode_items` 的 `with_fl` 是 **keyword-only**，项为 `{"id": ..., "data": ...}`。
5. `MAX_DATA_LEN = 0xFFF`、`MASK = 0x33`。

---

## 阶段 2：解析器与校验器 —— ☑ 完成并通过独立验证（审查点 B）

### 交付物

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `yw645_parser.py` | 654 | `YW645Parser`：`parse` / `parse_to_table` / `get_summary` / `is_frame`(类静态+模块级) / `calc_checksum` / `last_meta`；含 `assume_masked` 覆盖参数 |
| `validator/yw645_validator.py` | 177 | `YW645Validator`（8 项检查），继承 `BaseValidator` |
| `test/test_yw645_parse.py` | 645 | 307 项断言 |
| `test/test_yw645_validator.py` | 237 | 84 项断言 |
| `validator/__init__.py` | +? | 导出 `YW645Validator` |

依赖方向：parser → `yw645_wire` + `yw645_di`（**无 Qt、无其它协议模块**）。

### 实测证据

```
test_yw645_wire.py       PASS=250 FAIL=0
test_yw645_parse.py      PASS=307 FAIL=0
test_yw645_validator.py  PASS=84  FAIL=0                    合计 641
ruff check（7 个文件）    All checks passed!
```

### 独立复核（主会话自查，未采信子代理自述）

1. **逐行输出目视核对**（X1/X2/X5/X7）：地址/表号/模式/长度/偏移/CS/数据项全部正确。
2. **容错铁律 9/9 路径**（坏 CS、长度改大/改小、末字节非 16H、截断、空帧、起始符非 68H、<12B、未知模式）：
   **全部**非空表 + `valid=False` + 含 `⚠`；坏 CS 行给出「帧内值 0xB5，正确值 0xB4」（AC7 要求）。
3. **`last_meta`** 对 9 条 golden 的 14 个键齐备且取值正确（X7 `valid=True`/`declared_len=36`/`actual_len=36`/
   `items_form=request`/`mask_mode=unmasked`/`di_lookup_mode=unknown`）。
4. **修掉一处用户可见矛盾**（我发现的缺陷）：透传模式（0x30/0x40）原先也输出「数据域形态」行，
   导致 X5/X7 这种 **0x40 返回帧**被标成「主站请求（无 FL）」，与同行「透传模式返回」自相矛盾。
   现透传模式不再输出该行（`last_meta['items_form']` 仍照算，元数据不丢），并补了正/反两条断言。
5. **变异反证 6/6 变红**（驱动 `tools/mut_driver.py`）：

   | 变异 | FAIL | 变异 | FAIL |
   | --- | --- | --- | --- |
   | M1 地址改小端 | 17 | M4 行末偏移改开区间 | 12 |
   | M2 CS 范围错 | 54 | M5 帧长不足返回空表 | 12 |
   | M3 长度丢高 4 位 | 22 | M6 0x33 方向反转 | 25 |

### ⚠ 本轮踩到并已固化的两个坑（已进 `mut_driver.py` 文档字符串 + 失败记忆）

1. **变异测试必须清 `__pycache__` + 禁写 pyc**：pyc 失效判据是「源 mtime（整秒）+ 字节数」，
   同一秒内「变异→还原」且变异前后**等长**（`d = MASK if invert else -MASK` ↔ `… -MASK … MASK` 都是 33
   字节）⇒ 用旧字节码，M6 因此假报 FAIL=1，清缓存后为 FAIL=26。
2. **备份/还原必须用原始字节 `write_bytes`**，不能用 `write_text`：后者默认做换行翻译，
   会把 LF 文件写成 CRLF（实测曾把 `yw645_wire.py` 550 行全变成 CRLF、md5 从 `4521cc…` 变 `9bcc31…`；
   已从子代理遗留的 `_tmp_pristine/` 还原并二次校验 LF=550 / md5 一致）。

> **M4 说明**：只验「偏移不越界」（`0<=起<=末<帧长`）**抓不住整体 +1 错位**——错位后末偏移落在
> CS 字节上仍满足边界条件。必须**精确断言**区间（如「数据域 = 10..10+n-1」）；已补帧级数据行
> 精确偏移断言 + 坏 CS 提示行偏移断言，M4 才由「未变红」变为 FAIL=12。

### 带入阶段 3 的已知事项

- `parse` 的 `assume_masked` 语义：`None`=自动判别 / `True`=强制按已混淆（−0x33）/ `False`=按原样。
  透传载荷（`37 14` ↔ `04 E1`）在 `None` 下走「同分优先规范形态」，有 `数据域混淆` 行说明依据。
- 协议13 **无虚拟表**，`valid` 仅对外语义；但 `validator` 读 `last_meta`，改 meta 键名要同步两侧。
- 长度声明不符时 `valid=False` 且 `length_ok=False` —— 阶段 3 的批量「失败判定」须按
  **表内是否有 `❌` 行**（项目统一口径），**不是** `valid`，因为容错帧是「有内容但 valid=False」。

---

## 阶段 3：注册表接入 + 批量提取 + 查询页 —— ☑ 完成并通过独立验证（审查点 C）

### 交付物

| 文件 | 改动 | 职责 |
| --- | --- | --- |
| `protocol_registry.py` | +17（纯追加） | `ProtocolSpec(index=13)` + `lookup_builder_method["di_yw645"]` |
| `parser_registry.py` | +1 | `_PARSER_SPECS["yw645"] = ("yw645_parser", "YW645Parser")` |
| `yw645_wire.py` | +62 | `extract_yw645_frames()`（**纯函数**，零 Qt） |
| `main_gui.py` | +96（纯追加） | 提取分支(+6) / `_extract_yw645_frames` 单行委托(+11) / `_create_yw645_lookup_content`+`_load_yw645_map_data`(+79) |
| `reflex_web/reflex_web/landing_web.py` | +7 | `PROTOCOLS` 追加 index=13（见下方「偏离」） |
| `test/test_yw645_extract.py` | 新建 | **48** 项断言 |

### 实测证据（主会话复跑，非子代理自述）

```
test_yw645_wire.py       PASS=250  FAIL=0    test_window_state.py      全部通过（95）
test_yw645_parse.py      PASS=307  FAIL=0    test_serial_tool_widget.py 全部通过（471）
test_yw645_validator.py  PASS=84   FAIL=0    test_serial_proto_frame.py 全部通过（122）
test_yw645_extract.py    PASS=48   FAIL=0    test_web_landing.py        全部通过（102）
test_protocol_registry.py  tests OK          test_dlt645_pv_ext.py       156 项 ✓（协议6）
ruff（新增/触碰文件）      All checks passed!  test_dlt645_tolerant_parse.py 135 项 ✓（协议6）
```

### 独立复核（主会话）

1. **diff 边界算术闭合**：`git diff --numstat` → `main_gui.py 337/93`（基线 `334` ⇒ 净增 **96** = 子代理自报的 79+6+11 ✓）、
   `protocol_registry.py 20/1`（基线 4 ⇒ 净增 **17** ✓）。那 1 处删除与 93 处删除均在**其它任务**的 hunk 区
   （`modular | csg` 注释、`FlowLayout`、`CHANGELOG` 等），子代理的 3 个 hunk 全是 `,0` **纯追加** ✓。
2. **运行期注册表探测**：`combo_labels()` 14 项、末项 `[13] 依瓦定制645`；6 个别名全 → 13；
   `extract_strategy=yw645` / `lookup_kind=di_yw645` / `frame_gen_mode=preset_mode=None` / 6 个 `has_*` 全 False；
   `get_parser("yw645")` → `YW645Parser`；`make_validator(13)` → `YW645Validator`。
3. **单源检查**：`_extract_yw645_frames` 确为单行委托；查询页数据源确为 `from yw645_di import DI_TABLE`
   （文件中无第二份 DI 清单）。
4. **ruff 告警来源核对**：`ruff` 对 `protocol_registry.py` 报 2 条 F401、`main_gui.py` 报 8 条（7×F841+1×F821）。
   把 **HEAD 版**两个文件导出到 Windows 可见路径重跑 → **完全一致**（2 条 / 8 条）
   ⇒ 全为既有告警，本阶段**未新增任何告警**，按 AGENTS 陷阱 45 不动（动它会与其它任务的 diff 边界混在一起）。
5. **变异反证 4/4 变红**（子代理执行，主会话核对口径）：去掉自证① → FAIL=1；整帧长漏 `+12` → FAIL=22；
   去掉自证② → FAIL=2；长度丢高 4 位 → FAIL=2。

### ⚠ 本轮发现的真实协议级歧义（已用测试钉住）

**DL/T645-2007 与依瓦定制645 在 645 控制码 `D3..D0 == 0` 时帧结构逐字节同构**：

```
645 : 68 | A(6) | 68 | C | L | DATA(L,+0x33) | CS | 16     整帧 = L + 12
依瓦: 68 | A(6) | 68 | CMD | L | DATA(n,+0x33) | CS | 16   整帧 = n + 12, n = ((CMD&0x0F)<<8)|L
⇒ C & 0x0F == 0 时 n = L ⇒ 两者完全重合
```

实测（主会话，真实字节）：`C=0x10/0x90/0xF0` → **被当作依瓦帧提取**；`C=0x11/0x91/0x08/0x0F/0x8F` →
算出 `data_len` 为 260/2052 等巨大值 → 正确跳过 ✓。

- **为何不修**：**从字节上不存在判别依据**（连 `+0x33` 掩码语义、CS 位置、末尾 `16H` 位置都相同）。
  加启发式（如限制 CMD 高 4 位必为 1/2/3/4）会反过来丢掉 prd R2.4 要求「未知模式也必须解析」的合法帧。
- **危害有限**：实测该误提取**不会吞掉也不会错位真正的依瓦帧**（`645(0x90)+X4` → 两帧都在）。
- **处置**：新增 `test_dlt645_known_ambiguity()`（10 条断言）同时钉住三件事：常见控制码不误提、
  `D3..D0==0` 会误提（记录行为、非认可）、真依瓦帧不被吞。待阶段 6 写进 AGENTS.md 陷阱条目。

> 这也解释了为什么 `design.md §6` 把「与 645 形态最接近」列为风险——双层自证（`byte7==0x68` + 落位后末字节 `16H`）
> 能挡住南网/国网/698.45，但挡不住这个同构子类。

### 偏离记录

1. **`landing_web.PROTOCOLS` 提前到本阶段**（原属 5.1）：`test/test_web_landing.py` 与 `protocol_registry` **逐行对拍**
   ⇒ 只加注册表不加该行必然变红，而审查点 C 要求「既有测试全绿」。属纯数据追加，与 5.1 一致。
2. **3.5 一项未改**：`test_window_state.py` / `test_serial_tool_widget.py` / `test_serial_proto_frame.py`
   **早已**改为动态读 `combo_labels()`（1.23.58 那次修正的成果）⇒ 无需改动。
3. 未给 `serial_tool_widget.STRATEGY_BY_PROTOCOL` 加协议13（`design.md §6` 明确范围外）。
4. 子代理期间两处运行期事故（均已精确还原、留证）：临时变异脚本超时被 kill 使 `yw645_wire.py` 一度停在变异态
   （已还原 + 四锚点核验）；一次性 GUI 核验脚本触发 `_save_app_config()` 把 `config.json` 的
   `parse.protocol` 写成 `13`（AGENTS 陷阱 42，已按字节级枚举定位并改回 `0`，md5 与运行前逐字节一致）。

### 带入阶段 4

- `frame_gen_mode` / `preset_mode` 现为 `None`，阶段 4 与实现一起翻转（**防止 `preset_buttons._get_path`
  的 `GW_COMMAND_PATH` 兜底把依瓦帧写进 `GW_command.json`**）。
- 阶段 5（Web）**必须** `from yw645_wire import extract_yw645_frames`，禁止复刻。

---

## 阶段 4：组帧 + 预设 —— ✅ 完成（审查点 D 通过）

### 交付物

| 文件 | 规模 | 职责 |
| --- | --- | --- |
| `yw645_frame_gen.py` | 新增 451 行 | 纯逻辑组帧器（零 Qt）：`MODE_OPTIONS`/`mode_code`/`with_fl_for_mode`/`build_frame`/`describe_frame`/`FRAME_TEMPLATES`(6)/`build_from_template`/`template_state`/`YW645FrameGenerator`；**整帧编码全走 `yw645_wire.encode_frame`** |
| `yw645_frame_gen_widget.py` | 新增 480 行 | 独立组帧页：地址+广播+模式（含写模式占位）+FL 覆盖+数据项表格（增删/上下移）+透传数据域+写模式手填码+长度/CS 注记 |
| `YW645_command.json` | 新增（6 条） | 预设种子，`frame_hex` 由 `FRAME_TEMPLATES` **同源重算**（不手写） |
| `test/test_yw645_frame_gen.py` | 131 项 | 模式/地址/模板 oracle/报错矩阵/闭环/预设隔离/种子同源/单源守卫 |
| `test/test_yw645_gui.py` | 76 项 | offscreen：Tab 可见性对拍、组帧页真实生成、查询过滤、预设页、**添加预设真实路径**、真实 config 未被改 |
| `tools/gen_yw645_seed.py` | 任务级工具 | 由模板重算种子（`parents[4]`=项目根） |

**修改（既有文件）**：`protocol_registry.py`（两个 mode 翻转为 `"yw645"`）、`frame_gen_widget.py`（左栏 `QStackedWidget`
追加索引 2 + 分派/快照接线）、`main_gui.py`（`_on_preset_button_clicked` 加 `elif protocol == "yw645" → 切协议13`，2 行）、
`preset_buttons.py`、`test/test_protocol_registry.py`（组帧协议集合加 13 + 13 能力断言）。

#### 算术闭合（纯追加核验）

```
基线：frame_gen_widget.py 178/5 · main_gui.py 337/93 · protocol_registry.py 20/1 · preset_buttons.py 0/0（干净）
终值：frame_gen_widget.py 275/5 · main_gui.py 339/93 · protocol_registry.py  23/1 · preset_buttons.py 29/7
```

前三个文件**删除数逐字不变**（5 / 93 / 1）⇒ hunk 全为纯追加 ✓。

### 主会话独立复核（**未采信子代理自述**，逐项自算）

1. **AC8 闭环 + 最强 oracle**：6 个模板全部 `valid=True` / `cs_ok=True`；更关键的是
   `pass_req` **逐字节 == 文档 X3**（`680450000000136830023714B416`，CS `0xB4` 由文档给出）、
   `pass_rsp` **逐字节 == 文档 X9**（`681030000000106840023713AC16`，CS `0xAC` 由文档给出）
   ⇒ 组帧输出与文档示例**完全一致且 CS 由文档背书**，比任何自测断言都强。
   `read_batch` 掩码还原 = `00 10 00 20`，与 X1 数据域一致 ✓
2. **`preset_buttons.py` 那 7 处删除是行为等价重构**（该文件基线干净，无与其它任务 hunk 混叠）：
   两处 `proto_display` 字典**逐字相同** ⇒ 收敛为 `PROTOCOL_DISPLAY` 单源；`set_protocol` 白名单**只是加了 `yw645`**；
   `AddPresetDialog.proto_names` 用的是全称（「南网协议」/「DLT645-2007 电表协议」）而 `PROTOCOL_DISPLAY` 用简称 ⇒ 二者
   本就有意不同，**不是漏收**。
   它还**额外堵了第二个同源漏洞**：`_on_button_clicked` 取自定义路径的分支若不加 `yw645 → None`，
   会落到 `return self._gw_path`（又写 GW）——与 `_get_path` 兜底是同一种事故的两处入口。
3. **预设 schema 与 MODULAR 先例逐键相同**（`id`/`button_name`/`group_name`/`description`/`protocol`/`frame_hex`/`config`）✓
   （我初次探测报「name 全为 None」是自己的字段名写错，实为 `button_name`。）
4. **16/16 测试 rc=0**：协议13 六个（131/76/250/307/84/48）+ 协议6 组帧（161/73，**零回归**）+ 协议12（430）
   + 协议9 组帧 GUI（139）+ Web 组帧纯逻辑（74）+ 注册表 + 窗口（95）+ 南网自定义 DI（92）
   + pv_ext（156）+ Web 首页（102）。
5. **ruff**：4 个新增/新测试文件全部 `All checks passed!`
   （我首次跑报「12 errors」是**我把 `YW645_command.json` 传给了 ruff** —— 非 Python 文件会报解析错，非代码缺陷；
   4 个既有文件的 4 条 F401 已与 HEAD 版逐条对照，**完全一致 ⇒ 本阶段未新增告警**。）

### 变异反证（4 条全部实测变红，sha256 核对还原）

```
P1 with_fl 推导反转（请求/返回搞反）                PASS=0   FAIL=1  变红 ✓
P2 数据域 12bit 长度上限校验失效                   PASS=130 FAIL=1  变红 ✓
P3 preset yw645 分支失效（兜底写 GW_command.json） PASS=126 FAIL=6  变红 ✓   ← 陷阱 65 护栏有效
P4 build_from_template 忽略模板 body               PASS=127 FAIL=4  变红 ✓
还原核对：preset_buttons.py sha256 一致 ✓ · yw645_frame_gen.py sha256 一致 ✓
```

（P1 的变异会让测试**崩溃**（无汇总行）⇒ 子代理把互变异驱动改为「无汇总行 = 计 1 个失败」，
否则崩溃会被误报成「未变红」——这是个值得留存的度量陷阱。）

### 偏离记录

1. **`YW645_command.json` 做成入库种子文件**（PRD R6.1 原写「已 gitignore」，**与事实矛盾**）。
   实测 `git check-ignore -v` 无命中、`git ls-files` 未含 ⇒ **它未被 gitignore**。依据 MODULAR 先例
   （`git ls-files MODULAR_command.json` 命中 + `南网协议解析工具.spec` 有 `('MODULAR_command.json','.')`）
   取「入库种子」是正确做法：否则**开箱无预设**，与 AC9「预设按钮可取出完整帧」冲突。
   ⇒ **PRD R6.1 已修正**；阶段 6 **必须**把 `('YW645_command.json','.')` 加进 spec datas。
2. **`build_frame` 多一个可选 kwarg `cmd_override`**（D1「写模式命令码可手填」所需），不传时与设计签名行为一致。
3. **未在 `_on_add_to_preset_clicked` 加协议13 专用 guard**（协议9 有）：13 有预设库，走 `_get_path` 显式分支；
   用真实路径实测作为护栏（6 项断言）比再加一段冗余分支更可验证。
4. 协议13 的**串口分帧策略**仍未加（`design.md §6` 明确范围外）。
5. 未跑 `release_check.py`（阶段 6 才做）。协议 6 四个核心文件 `git diff --numstat` **为空**（零改动）。

### 新发现：既有 GUI 测试改写开发机真实 `config.json`（**非本阶段引入**）

**决定性判定（mtime，与 md5 正交）**：

```
test/test_yw645_gui.py             未改写  ✓ 本次新增的测试沙箱正确
test/test_dlt645_frame_gen_gui.py  ★ 改写了真实 config.json
test/test_csg_frame_gen_gui.py     ★ 改写了（L535 / L814 有 win.show()）
test/test_nanwang_custom_di.py     ★ 改写了
```

**静态检查（机制）**：

| 测试 | `data_path` 提及 | 沙箱 | 判定 |
| --- | --- | --- | --- |
| `test/test_yw645_gui.py` | 6 | 6 | ✓ `_config_sandbox.install()` 同时 patch `app_paths` **与** `main_gui.data_path`，且断言真实 config md5 未变 |
| `test/test_dlt645_frame_gen_gui.py` | 0 | 0 | ❌ 完全无沙箱 |
| `test/test_csg_frame_gen_gui.py` | 0 | 0 | ❌ 完全无沙箱 |
| `test/test_nanwang_custom_di.py` | 11 | 11 | ⚠ 只 patch `app_paths.data_path`，**漏 `main_gui.data_path`**（AGENTS 陷阱 42） |

注：`test/_config_sandbox.py` **不是新文件**（2026-09-16 由任务 `09-15-gui-window-state-persist` 创建）——
本阶段是**复用**既有共享助手。其 docstring 里「只构造、从不 show 的测试无需沙箱（有 `_window_shown_once` 守卫）」
这个假设**对这 2 个测试不成立**（csg gui 明确 `win.show()`），是它们长期写盘的直接原因。

**后果与现状**：`config.json` 被 `_save_app_config` **首次**重序列化（md5 `4a8664be…` → `b89d11d0…`），
此后**幂等**（我复跑整轮 16 个测试前后 md5 **完全未变**）。结构体检（对照 `dist/config.json` 这份旧构建参照）：
13 个顶层键、**无缺失**、多出 `feedback`/`share`/`update`（后续版本合法新增）、`window` 含几何+分栏、
`serial`=`COM1/9600/偶`、`parse.protocol=0`、`csg_channel=hrf` ⇒ **语义完好，未丢键未错值**。
唯一差异是 `py_scripts` 的路径（dist 是构建期写死的绝对路径，当前是相对路径）——与测试无关。

**修法**：三处改用既有 `test/_config_sandbox.install()`（每个文件 1 行）。属其它任务的文件 ⇒ **本任务未动**，
建议单独立项（否则每次跑 `release_check.py` 都会改写用户配置）。

### 带入阶段 5

- Web **必须** `from yw645_wire import …`（禁止复刻线格式逻辑；`design.md §6` 已写明）。
- `landing_web.PROTOCOLS` 第 13 行已在阶段 3 加好（`test_web_landing.py` 102 项绿）。
- 阶段 6 待办：spec `datas` 加 `('YW645_command.json','.')`；`hiddenimports` 补 `yw645_*`（`make_validator` 走 importlib）。
- 协议13 未接入串口分帧策略（`design.md §6` 范围外，需在 CHANGELOG/AGENTS 记为范围外并说明理由）。

---

## 阶段 5：Web 端 —— ☐ 未开始
## 阶段 6：打包 + 文档 + 门禁 —— ☐ 未开始
## 阶段 7：收尾 —— ☐ 未开始
