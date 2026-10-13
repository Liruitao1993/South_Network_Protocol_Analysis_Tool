# 技术设计：依瓦定制645（协议13）

> 依据：`prd.md`。本文只写技术设计（边界、契约、数据流、取舍、兼容、回滚），不写执行清单。

## 1. 模块划分与边界

```
yw645_wire.py          # 线格式编解码 SINGLE SOURCE（纯 stdlib，零 Qt）
  ├─ 帧常量：FRAME_START=0x68 / FRAME_END=0x16 / ADDR_LEN=6 / MASK=0x33
  ├─ MODE_* 命令码 + MODE_NAMES
  ├─ encode_addr12(text) / decode_addr12(bytes) / is_broadcast_addr(bytes)
  ├─ cmd_from_len(n) / len_from_cmd(cmd, L)        # 12bit 长度 ↔ COMMAND/L 双字节
  ├─ calc_cs(body: bytes) -> int
  ├─ apply_mask(data, direction) -> bytes           # +0x33 / -0x33
  ├─ encode_items(items) / decode_items(payload)    # 数据项序列（请求/回复两种形态）
  ├─ encode_frame(...) -> bytes                     # 整帧组帧（唯一实现）
  └─ frame_total_len(data: bytes) -> Optional[int]   # 自证式总长探测（供切帧）

yw645_di.py            # 静态数据项表 SINGLE SOURCE（附录A）+ 双索引查表
  └─ DI_TABLE / DI_INDEX_LITERAL / DI_INDEX_SWAPPED
     di_lookup(raw_id: bytes) -> DiHit | None        # 字面优先、字节交换备选
     di_payload_note(di, payload) -> str             # 数据项业务说明（枚举等）

yw645_parser.py        # 解析器（协议13 的 parser_key 实现）
  └─ class YW645Parser: parse / parse_to_table / get_summary / is_frame
                        calc_checksum / last_meta

yw645_frame_gen.py     # 组帧器（纯逻辑，零 Qt）
  └─ YW645FrameGenerator + FRAME_TEMPLATES + build_from_template

yw645_frame_gen_widget.py  # 组帧 GUI 页（QWidget，独立文件，供 frame_gen_widget 挂 QStackedWidget）

validator/yw645_validator.py  # 与 BaseValidator 对齐
```

**边界规则**

- `yw645_*` 模块**不 import** `main_gui`、不 import 其它协议解析器（协议间零横向耦合）。
- 协议 6（`dlt645_*`）**零改动**：不复用其 schema、不 import 其模块、不共享常量。
- 所有 ±0x33、长度拼接、CS、地址编解码**只在 `yw645_wire.py`** 出现一次；
  解析器、组帧器、GUI 页、Web、测试全部经它——**禁止第二份实现**（项目既有约定，见 AGENTS.md 陷阱 48/55/61）。

## 2. 线格式编解码设计

### 2.1 帧布局（与 prd §协议事实基线一致）

```
偏移  0      1..6        7      8        9        10..10+n-1   10+n   11+n
    68H   A0..A5(6B)   68H   COMMAND    L       DATA(n)       CS     16H
                            bit7-4 模式  ┐
                            bit3-0 ──────┴── 长度高 4 位
n = ((COMMAND & 0x0F) << 8) | L          ; 0 <= n <= 0x0FFF
整帧长度 = n + 12
```

### 2.2 地址域

- **高字节在前**（MSB first），BCD 有效数字 0~9；`AA×6` = 广播。
- `encode_addr12(text)`：去空白 → 校验仅数字 → 取**低 12 位**（`text[-12:]`）→ 左侧补 `0` 至 12 →
  每 2 字符 1 字节。返回 `bytes`（6B）。
- `decode_addr12(bytes)`：6 字节逐字节 `%02X` 拼接 → `int(...)` 去前导 0 → 返回字符串（保留 12 位原文另存）。
  - 三示例自证：`12 34 56 78 90 12`→`123456789012`；`10 30 00 00 00 10`→`103000000010`；`04 50 00 00 00 13`→`45000000013`。
- 与标准 645 相反（645 是低字节在前）：**不得**复用 `dlt645_frame_schema._encode_di_value` / 645 地址助手。

### 2.3 长度域

- `cmd_from_len(n)` → `(cmd_hi_nibble | ((n >> 8) & 0x0F), n & 0xFF)`；`n > 0x0FFF` 抛 `ValueError`（可读中文）。
- `len_from_cmd(cmd, L)` → `((cmd & 0x0F) << 8) | L`。
- 文档「最大可传输 4096 个数据」按 12 bit 实现（上限 **0xFFF = 4095**，见 prd D4）。

### 2.4 校验码 CS

```python
def calc_cs(body: bytes) -> int:      # body = 帧头 .. DATA 末字节（不含 CS/16H）
    return sum(body) & 0xFF
```

- 覆盖范围 = **第一个 68H 起、到 CS 之前所有字节**（含已 +0x33 的 DATA 原样字节）。
- 5 条文档给出 CS 的示例全部吻合（0xB4/0xB2/0x31/0x9C/0xAC），4 条计算值与文档逻辑一致。

### 2.5 ±0x33 数据域混淆

- `apply_mask(data, +1)` = 逐字节 `(b + 0x33) & 0xFF`；`apply_mask(data, -1)` = `(b - 0x33) & 0xFF`。
- **接收默认 −0x33**（依据文档 L113 注1「接收方在收到数据后需做减 0x33 处理」）。

### 2.6 数据项序列

图1 定义：`ID(2B) | F+L(1B) | 数据(FL 字节)` 重复。文档 L120：**请求不带 F+L，回复带 F+L**。

```python
def encode_items(items, *, with_fl: bool) -> bytes
    # items: [{"id": b"\x00\x10", "data": b"\x01"}, ...]
    # with_fl=False（请求）：只拼 ID
    # with_fl=True （回复）：拼 ID + bytes([len(data)]) + data

def decode_items(payload: bytes) -> (list[Item], str)   # 返回 (项列表, 形态结论)
    # 形态结论 ∈ {"reply", "request", "ambiguous", "malformed"}
```

**形态判别算法（`decode_items` 的核心决策，需可解释、可测试）**

对同一 `payload` 分别按 `with_fl=True/False` 尝试切分，各打分：

| 打分项 | 权重 |
| --- | --- |
| 能完整消费全部字节（无残留） | +4 |
| 每项 ID 在 `DI_TABLE` 中命中（字面或交换） | +2 / 项 |
| 项数 > 0 | +1 |
| 出现 FL=0 且其后仍有数据（`with_fl` 不自洽） | 直接判该分支不合法 |

取高分者作为结论；同分时按 `reply → request` 顺序（回复是业务常态），结论写入 `last_meta["items_form"]`
与表格行「数据域形态」并在歧义时插 `⚠` 行。→ 满足 prd R2.6「不确定时同时给出两种解释」。

## 3. 0x33 形态自动判别（prd R3.1 / F3）

**问题**：文档读模式示例是**未混淆形态**（`00 10 00 20`），透传示例是**已混淆形态**（`36 13`）。
两种形态都会喂给解析器（用户可能直接粘贴文档示例）。

**算法**：对 DATA 计算两个候选 `raw` 与 `raw_minus_33`，各自调用 `decode_items` 拿 `(score, form)`：

```
score_candidate = decode_items 的分数
选择：取分高者
同分：优先 raw_minus_33（协议规范形态，文档 L113 注1）
结论写入 表格行「数据域混淆」：
  - 采用 −0x33  → "已按规范减 0x33 还原"
  - 回落原样     → "⚠ 按原样解析（减 0x33 后无法自洽切分）：<简述原因>"
```

CS 校验**始终按帧内原样字节**计算，与混淆判别无关（两者正交）。

## 4. DI 表（附录A）与双索引

`DI_TABLE` 条目结构（与 `modular_iface_data.py` 的静态表风格一致）：

```python
{"id": "0010", "name": "设备类型", "length": "变长", "dtype": "BCD",
 "rw": "读", "note": "01：电表", "enum": {"01": "电表"}}
{"id": "0020", "name": "设备号", "length": "变长", "dtype": "BCD",
 "rw": "读", "note": "最大12个字节", "enum": {}}
```

- **主索引 `DI_INDEX_LITERAL`** = 线上字面字节（`b"\x00\x10"` → 条目）。依据 X2 自证（prd F6）。
- **备选索引 `DI_INDEX_SWAPPED`** = 字节交换（`b"\x10\x00"`）。用于 D2 歧义（文档把 `04 E0` 注为 "E004"）。
- `di_lookup(raw)`：字面命中 → `(hit, "literal")`；否则交换命中 → `(hit, "swapped")`；否则 `(None, "unknown")`。
  命中方式写入 `last_meta`，并在表格行注明（`(字节交换命中)`）。
- 未知 ID → 输出原始 ID hex + 「未知数据项」+ ⚠，**不拒解析**（prd D5 / R2.5）。
- 设备类型枚举：`01` → 「电表」；其它值 → 「未知设备类型(0xNN)」+ ⚠。
- 设备号：按 BCD 解读为 12 位表号（复用 `decode_addr12` 语义），长度 >12 字节时截断并 ⚠。

## 5. 解析器契约

严格对齐 `modular_iface_parser.ModularIfaceParser` 的既有契约（GUI/批量/串口三个调用方都依赖它）：

```python
class YW645Parser:
    last_meta: dict           # 每次 parse 覆写
    def parse(self, frame: bytes) -> List[tuple]
    def parse_to_table(self, frame: bytes) -> List[tuple]   # = parse（GUI/串口兼容入口）
    def get_summary(self, frame: bytes) -> str
    @staticmethod is_frame(data: bytes) -> bool             # 同时提供模块级 is_frame
    @staticmethod calc_checksum(data: bytes) -> int
```

- 行元组 = `(字段名, 原始值, 解析值, 说明, 起始偏移, 末偏移)`，**末偏移为闭区间**
  （AGENTS.md 陷阱 58 记录的既有约定：解析器的「结束偏移」列被 GUI/回填逻辑按闭区间使用）。
- `last_meta` 键：`valid` / `cs_ok` / `cs_expected` / `structure_ok` / `structure_error` /
  `length_ok` / `declared_len` / `actual_len` / `items_form` / `mask_mode` / `di_lookup_mode` /
  `mode_name` / `addr` / `is_broadcast` / `errors`。
- `valid` 语义 = `structure_ok and cs_ok and length_ok`（与 `dlt645_sim/engine.py` 读 `parsed.get("valid")` 的
  同款语义；协议13 无虚拟表，故 `valid` 仅对外语义，改动风险低）。
- **容错铁律（prd R2.7/R2.8）**：`parse` 只在 `len(data) < 12` 时降级返回「帧长不足 + 原始 hex」；
  长度够就一律继续完整解析。CS 错 / 长度不符 → 插 `⚠` 行（给出帧内值与**正确值**），`valid=False`，
  但**绝不返回空表**（项目强制约定，见 AGENTS.md 陷阱 23/49）。
- 提示行行名必须含「校验和」子串（AGENTS.md 陷阱 49：偏移映射按字段名子串匹配）。

## 6. 窗格式提取（批量/串口）

新增 `extract_strategy="yw645"` → `main_gui._extract_yw645_frames(clean)`，
**以 `_extract_modular_frames` 为模板**（同样按长度域定位帧尾，不搜索 0x16；见 prd F5）：

```python
while i < len(clean) - 23:                     # 最短帧 12B = 24 hex
    pos = clean.find("68", i)
    if pos == -1: break
    if pos + 8 > len(clean): i = pos + 2; continue      # 需要到 byte7
    if clean[pos+14:pos+16] != "68":  i = pos + 2; continue   # 自证①：第二个 68H
    cmd = int(clean[pos+16:pos+18], 16); low = int(clean[pos+18:pos+20], 16)
    data_len = ((cmd & 0x0F) << 8) | low
    total = data_len + 12; hl = total * 2
    if pos + hl > len(clean): i = pos + 2; continue
    cand = clean[pos:pos+hl]
    if cand[-2:] != "16": i = pos + 2; continue               # 自证②：末字节 16H
    frames.append(cand); i = pos + hl
```

**互斥性（prd AC13）**：两道自证（`byte7==0x68` + 末字节 `16H` + 长度域自洽）足以把
南网/国网（byte7 非 0x68）、698.45（无第二个 68H）、645（`68 + 6B addr + 68 + C + L`）排除；
645 是最接近的形态，靠「byte7==0x68 且 `data_len+12` 落位后末字节为 16H」双重条件区分，
测试须用四种协议的混合日志做互斥断言。

串口工具（`serial_tool_widget.STRATEGY_BY_PROTOCOL`）**本期不加 13**——理由：项目已有约定「未列出的协议
没有自证依据，不得硬加策略」，且 645（`L+12`）与依瓦（`12 + ((cmd&0x0F)<<8|L)`）同以 `68+6B+68` 开头，
误判风险高。**若后续要加，必须同时加末字节自证 + byte7 自证**。此取舍写入 CHANGELOG 与 AGENTS 陷阱。

## 7. 组帧器设计

`yw645_frame_gen.YW645FrameGenerator`（纯逻辑，零 Qt）：

```python
def build_frame(*, addr: str, mode: str, items: list[dict],
                with_fl: bool | None = None, body: bytes | None = None) -> bytes
```

- `mode` ∈ `{"read_req"=0x10, "read_rsp"=0x20, "pass_req"=0x30, "pass_rsp"=0x40}`
  （写模式见 §9 D1 处置）。
- `with_fl=None` → 由 mode 推导（`0x10/0x30` 不带 FL，`0x20/0x40` 带 FL），可显式覆盖。
- `body` 直通（透传场景不做数据项切分，直接给原始内容，由 `apply_mask` +0x33）。
- 组装顺序：`addr → cmd/L（由 items 长度反推）→ DATA(+0x33) → CS → 16H`。全部经 `yw645_wire`。
- 超限/非法输入抛 `YW645BuildError`（可读中文），GUI 捕获后红字提示：
  - 数据域长度 > 0xFFF
  - 地址含非数字
  - 数据项 data 为空且 with_fl=True（FL=0 无意义）
- `FRAME_TEMPLATES`：读设备类型 / 读设备号 / 批量读（两 ID）/ 透传请求 / 透传回复（种子与 `YW645_command.json` 对齐）。
- **闭环自证（prd R4.6 / AC8）**：`build_frame(...)` → `YW645Parser().parse(...)` → `valid=True`，四类模式各一条。

### 7.1 GUI 页

`yw645_frame_gen_widget.YW645FrameGenWidget`（独立文件，模式 `yw645`）：
地址输入（12 位数字 + 「广播」勾选）｜模式下拉（含写模式占位项，见 D1）｜数据项表格
（ID / 长度 / 值 + 增删/上下移）｜「添加数据项」按钮（ID 下拉取自 `yw645_di`，可手填）｜
输出区（hex + CS/长度注记）｜「添加到预设」按钮。

`frame_gen_widget.FrameGenWidget` 的左栏 `QStackedWidget` 追加第 N 页并按 `frame_gen_mode` 切换
——沿用协议 9 的既有范式（`csg_test_frame_gen_widget` 挂载点）。**协议 13 的组帧页不依赖协议 6 的
`dlt645_frame_schema`**。

## 8. 接入点清单（全部数据驱动，改注册表为主）

| 位置 | 改动 |
| --- | --- |
| `protocol_registry._PROTOS` | 追加 index=13 条目（新增 `lookup_kind="di_yw645"`、`frame_gen_mode="yw645"`、`extract_strategy="yw645"`、`preset_mode="yw645"`、`parser_wrapper="direct"`、`validator_class="validator.yw645_validator:YW645Validator"`）；`has_*` 全 False |
| `protocol_registry.lookup_builder_method` | 映射表加 `"di_yw645": "_create_yw645_lookup_content"` |
| `parser_registry._PARSER_SPECS` | `"yw645": ("yw645_parser", "YW645Parser")` |
| `main_gui._extract_frames_for_protocol` | 加 `if strategy == "yw645": return self._extract_yw645_frames(clean)` |
| `main_gui` | 实现 `_extract_yw645_frames`；离线运行 8 条示例的自检式注释 |
| `main_gui` 查询页 | 新增 `_create_yw645_lookup_content`（沿用 `_create_modular_iface_lookup_content` 的结构） |
| `frame_gen_widget` | 挂载 `yw645` 页 + 输出/复制/清空接线 |
| `preset_buttons` | `preset_mode == "yw645"` → `YW645_command.json`（种子 5 条） |
| `validator/__init__.py` | 导出 `YW645Validator` |
| `main_gui:CHANGELOG` / `README.md` / `AGENTS.md` | 见 prd R9.3 |
| `reflex_web/landing_web.PROTOCOLS` | 追加第 13 行 |
| `reflex_web/reflex_web/lookup_utils.py` | `di_yw645` 分支 |
| `reflex_web/reflex_web/web_utils.py` | 批量提取加 `yw645` 分支 + 摘要 |
| `南网协议解析工具.spec` / `reflex_web_exe.spec` / `build_*_deploy.py` | `hiddenimports` + `datas`（`YW645_command.json`） |

Web 组帧：本期**不做**（prd R7.4 要求显式声明并在下拉处给出可见提示）。

## 9. 已知缺陷的处置设计

| # | 处置 |
| --- | --- |
| **D1 写模式命令码缺失** | 组帧模式下拉含「写模式（文档未定义）」项，命令码可手填（默认空且**禁用生成**，选了即弹提示「文档未定义写模式命令码，请填写实测值或联系协议作者」）。解析侧对未知高 4 位输出「未知模式(0xN0)」并继续解析。命令码表 `MODE_NAMES` 中不含任何推测值。 |
| **D2 DI 字节序** | §4 双索引（字面优先 + 交换备选），命中方式写入输出。 |
| **D3 0x33 示例矛盾** | §3 自动判别 + 输出依据；文档（AGENTS/CHANGELOG）明确记录矛盾。 |
| **D4 长度上限** | 12 bit，上限 0xFFF；文档「4096」按 4095 实现并在注释注明。 |
| **D5 附录A 仅 2 项** | 未知 ID 走兜底（原始 hex + ⚠），不拒解析。 |

## 10. 测试设计

| 文件 | 覆盖 |
| --- | --- |
| `test/test_yw645_wire.py` | 线格式单元：地址编解码（含 >12/<12/广播/非法）、长度拼接、CS、±0x33、`encode/decode_items` 双形态、`frame_total_len` |
| `test/test_yw645_parse.py` | 9 条示例 golden（**对未混淆与已混淆两种形态各断言一次**）、容错（坏 CS/坏长度/截断/缺 16H）、`get_summary`、`is_frame`、`last_meta` 全键 |
| `test/test_yw645_frame_gen.py` | 四类模式组帧、超限/非法报错、组帧↔解析闭环、模板、预设 JSON 往返 |
| `test/test_yw645_extract.py` | 批量提取：单帧/多帧拼接/前置噪声/长度域偏小/末字节不符/**四协议混合日志互斥** |
| `test/test_yw645_validator.py` | `make_validator(13)`、各检查项 PASS/FAIL、坏帧校验 FAIL 但解析仍完整 |
| `test/test_yw645_gui.py` | offscreen：Tab 可见性对齐注册表、单帧解析、组帧页生成、查询页过滤 |
| `test/test_yw645_web.py` | Web 解析协议13 + 首页协议表逐行对拍 |

- 全部登记进 `release_check.py:CORE_TESTS`。
- **变异反证 ≥4 条**（prd R10.3）：地址大小端互换 / 长度拼接改为单字节 / CS 范围改为 `body[1:]` 或含 CS /
  ±0x33 方向反转 —— 各自须实测变红后还原。
- 测试沙箱：凡涉及 `data_path`（`YW645_command.json`）的用例，按项目约定同时 patch
  `main_gui.data_path` **与** `app_paths.data_path`（AGENTS.md 陷阱 42），避免污染真实配置。

## 11. 兼容性与回滚

- **协议 6 零回归**：不 import、不改动 `dlt645_*`；协议 6 全部既有测试必须保持全绿（作为本任务的回归门禁）。
- **注册表新增是纯追加**：index=13 追加在末尾，不改任何既有 spec；既有测试中「协议个数」硬编码断言
  按项目约定改为读 `combo_labels()`（这是**预期内的必要改动**，需在 CHANGELOG 说明）。
- **回滚**：单点回滚 = 从 `_PROTOS` 移除 index 13 条目 + 删除 `yw645_*` / `validator/yw645_validator.py`；
  无数据迁移、无配置格式变更（`YW645_command.json` 为新增独立文件，删除即回滚）。
- **打包**：新模块须进 spec `hiddenimports`；`make_validator` 走 importlib（打包器静态分析不可见），
  漏加会在 exe 里表现为「校验器缺失」而源码运行正常——属于必须在打包后实测的项目。

## 12. 风险与未决

| 风险 | 说明 | 缓解 |
| --- | --- | --- |
| 无真实设备帧 | 全部 oracle 来自文档（含作者自述「虚拟」的 X7） | 结构/长度/CS/地址规则已 5 条独立自证；数据项切分只由 X2 单条自证；预留 `last_meta` 供现场校准；**拿到现场帧后优先跑 `test_yw645_parse.py` 的 golden 并更新 oracle** |
| 0x33 判别误判 | 两种候选同分时按规范形态 | 输出判别依据；`parse` 增加**显式覆盖开关**（`assume_masked: bool | None`），GUI 无需暴露但测试与串口可用 |
| 写模式缺失 | 无法实现 | 占位 + 明确提示，不臆造 |
| 串口策略未加 | 用户可能期望串口断帧支持协议13 | CHANGELOG/AGENTS 明确记为范围外并说明理由（误判风险） |
| 与 645 结构相近 | 批量互斥靠双重自证 | `test_yw645_extract.py` 用四协议混合日志钉住 |
