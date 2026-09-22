# Design：串口工具按协议断帧与解析

## 1. 总体结构

```
SerialToolWidget (serial_tool_widget.py)
├── 命令表第 5 列「协议」            ← 新增（UI + 持久化）
├── SerialCommandDialog 协议下拉     ← 新增
├── _on_raw_data()                  ← 改造：按锁存协议选分帧策略
│   └── FrameStrategy.frame_len(buf) → int   ← 新增（纯函数，可单测）
│       ├── ft12_68 / dlt698_45 / dlt645     （68 家族，已有 _declared_frame_len）
│       ├── hdlc_7e                          （2/3）
│       ├── dlms_wrapper                     （4）
│       └── None                             （1/5/9/10/11 → 回落）
├── _emit_protocol_frames()         ← 新增：按策略逐帧产出
├── _parse_and_log(frame, proto)    ← 新增：调注入回调解析 → 日志文字
└── set_parse_provider(fn)          ← 新增：main_gui 注入（与 set_serial_worker 同约定）

main_gui.MainWindow
└── _ensure_serial_tool_tab()       ← 追加 tab.set_parse_provider(self._serial_parse_provider)
```

**解耦契约**：`serial_tool_widget` 不 import `main_gui`，通过注入的回调拿解析能力。

## 2. 契约 A：分帧策略（纯函数）

新增模块级纯函数（放 `serial_tool_widget.py`，与 `_declared_frame_len` 同处；便于独立单测）：

```python
# 分帧依据种类
STRATEGY_BY_PROTOCOL = {
    0: "ft12_68", 7: "ft12_68",     # 68 + L(2B 小端)，整帧 = L
    6: "dlt645",                    # 68 A(6) 68 … L(1B@9)，整帧 = L + 12
    8: "dlt698_45",                 # 68 L(2B) 68 …，整帧 = L + 3
    2: "hdlc_7e", 3: "hdlc_7e",     # 7E 定界（7D 转义）
    4: "dlms_wrapper",              # 00 01 + … + L(2B 大端@6)，整帧 = 8 + L
    # 1 / 5 / 9 / 10 / 11 无自证依据 → 不出现在表里
}

def frame_length_for(strategy, buf: bytes) -> int:
    """按策略推算整帧长度；不可信返回 0（调用方回落到既有路径）。"""
```

`frame_length_for` 的判定（**全部要求自证**，任一不满足即返回 0）：

| strategy | 前置判别 | 长度 | 自证 |
| --- | --- | --- | --- |
| `ft12_68` | `len >= 8`、`buf[0] == 0x68`、`buf[3] != 0x68`、`buf[7] != 0x68` | `buf[1] \| buf[2] << 8` | 收满后末字节 `0x16` |
| `dlt645` | `len >= 10`、`buf[0] == 0x68`、`buf[7] == 0x68` | `buf[9] + 12` | 收满后末字节 `0x16` |
| `dlt698_45` | `len >= 8`、`buf[0] == 0x68`、`buf[3] == 0x68` | `((buf[1] \| buf[2] << 8) & 0x3FFF) + 3` | 收满后末字节 `0x16` |
| `hdlc_7e` | 找到 `buf[0] == 0x7E` | 见下 | 找到第二个 `0x7E` |
| `dlms_wrapper` | `len >= 8`、`buf[0:2] == 00 01` | `8 + int.from_bytes(buf[6:8], "big")` | 长度 ∈ `[1, RAW_MAX_FRAME_LEN]` |

长度一律须落在 `[RAW_MIN_FRAME_LEN, RAW_MAX_FRAME_LEN]`。

**顺序约束**：68 家族三者的判别必须与既有 `_declared_frame_len` 一致（先查第 4 字节，再查第 8 字节），因为 `68 L L 68`（698.45）与 `68 A6 68`（645）的签名可能同时命中，错判会切错帧。

**HDLC 7E 分帧**（`hdlc_7e`）——与 `main_gui._extract_hdlc_frames` 同口径，输出**含首尾 7EH 的原始字节**（`HDLCParser.parse` 正是要求首字节为 `0x7E`）：

```
定位 buf 中第一个 0x7E（前面的字节视为噪声，需计入"已消费"以免缓冲无界增长）
从其后找下一个 0x7E（帧内 7E 已被发送方转义为 7D 5E，故不会出现在帧内 → 自证）
帧 = buf[first_7E : second_7E + 1]（含首尾标志）
连续 7E（如 7E 7E）：后一个 7E 既是上一帧的尾又是下一帧的头 → 实现为「尾标志不作为下一帧的头」，
  即 consumed 前进到 second_7E（不含），下一轮从 second_7E 重新找头 → 不产生空帧
未找到尾标志 → 不产出（等待），受 FRAME_IDLE_MS / FRAME_HOLD_MAX_MS 约束
```

**自证失败时的处理**：`frame_length_for` 返回 0 → 该字节序列交回既有「帧结构优先（`_declared_frame_len`）+ 时间聚合」路径。这保证 AC4.1（不解析时行为不变）与 AC2.7。

**与既有 `_declared_frame_len` 的关系**：`_declared_frame_len` 保留（它是「未指定协议」时的启发式兜底）；协议已知时改用 `frame_length_for`，判别更严格（`ft12_68` 额外排除 645/698.45 签名）。

## 3. 契约 B：协议锁存与接收路径

```python
# 发送时锁存（_on_sent 或发送前）
self._last_tx_protocol = command.get("protocol")      # int | None
```

`_on_raw_data(data)` 的改造：

```
1. _rx_bytes += len(data)
2. 匹配（不受分帧/解析影响）—— 既有逻辑不动
3. 接收模式分派：
   a. 若「按帧尾分割」模式 → 既有 _flush_frames()（不变）
   b. 否则（原始数据模式）：
      strategy = STRATEGY_BY_PROTOCOL.get(self._last_tx_protocol)   # 需「显示解析」不参与
      若 strategy：先 _emit_protocol_frames(strategy) 逐帧产出；
                   剩余残帧再按既有「帧结构优先 + 时间聚合」刷出
      否则：完全走既有 _flush_raw_display()（行为不变）
```

产出每帧时：`_rx_frames += 1` → `_rx_log_queue.append(("raw", hex))` → 若该协议非 `None` 且「显示解析」开 → `_queue_parse(frame, proto, channel="rx")`。

**TX 也解析**（1.23.48 补，实测反馈「发送为何没有解析」）：`_on_sent` 用**该条命令自己的协议**入 TX 队列 —— `_tx_log_queue.append(("raw", label))` + `_queue_parse(data, proto, channel="tx")`。`_queue_parse(frame, protocol, channel)` 按 `channel ∈ {rx, tx}` 选择目标队列。

**队列元素升级**：`_tx_log_queue` 与 `_rx_log_queue` 均为 `deque[tuple[str, str]]`（`kind ∈ {raw, parse, fail}`），`_flush_log_queues` 用同一套规则处理两个队列（前缀 `[TX]`/`[RX]`、raw 用各自 tx/rx 配色、解析 sys、失败 fail）。**burst 只对各自队列的 `raw` 计数**：超 `LOG_FLUSH_BURST` 时只输出摘要 + 首末 raw 行并**丢弃**同批 parse 明细（防刷屏）。

## 4. 契约 C：解析与日志文字

注入回调（`main_gui` 侧）：

```python
def _serial_parse_provider(self, frame_bytes: bytes, protocol_index: int):
    """串口工具解析回调：返回 (摘要, [(字段名, 原始值, 解析值, 说明), ...]) 或抛异常。"""
    parser = self._get_current_parser(protocol_index)
    table_data = parser.parse_to_table(frame_bytes)
    if not table_data:
        return "", []
    summary = self._get_summary_from_table_data(table_data, protocol_index)
    return summary, table_data
```

`serial_tool_widget` 侧渲染（纯函数，可单测）：

```python
def format_parse_rows(table_data, max_lines) -> list[str]:
    """解析表 → 日志文字行。
    每行：'    ' + 字段名 + ' = ' + (解析值 or 原始值) + ('  ' + 说明 if 说明)
    字段名/值均空的行跳过；超 max_lines 追加 '    …（共 N 行，已省略 M 行）'
    """
```

日志输出形态：

```
[RX] 68 D0 00 83 … 16
[解析·国网协议] 长度域:208 | 控制域:… 
    起始字符 = 68H  帧起始标志
    长度域 = 208  用户数据长度=202字节，小端序，2字节
    …
    …（共 87 行，已省略 57 行）
```

失败：

```
[解析] 失败：'GDW10376Parser' object has no attribute …
```

**不伪造**：`table_data` 为空 / 摘要为 `-` 且无字段行 → 输出失败行。

## 5. 契约 D：协议字段（数据模型与持久化）

```python
def normalize_command(raw, fallback_name) -> Optional[dict]:
    # 新增
    "protocol": _coerce_protocol(raw.get("protocol")),   # int(0..11) 或 None

def _coerce_protocol(value) -> Optional[int]:
    """非法值一律 None（不解析）：非 int / bool / 越界 / 非数字字符串。"""
    if isinstance(value, bool) or not isinstance(value, int):
        # 兼容字符串数字（手改 JSON 的常见情况）
        try: value = int(str(value).strip())
        except (TypeError, ValueError): return None
    return value if 0 <= value < protocol_count() else None
```

- `DEFAULT_PARAMS` 新增 `parse_enabled: True`、`parse_max_lines: 0`（**0 = 不限制**）；`merge_params` 增加 int 分支与范围钳制（`0 <= parse_max_lines <= 2000`，**不得把 0 钳成 1**）。
- **配置版本迁移**（1.23.49 补，实测报障）：参数一旦被保存过就会把**当时的默认值**写进配置文件，`merge_params` 只在「键不存在」时才用新默认值 —— 于是「改默认值」对老用户不生效（实测：1.23.48 已把 `parse_max_lines` 默认改为 0，用户日志仍显示「已省略 83 行」，因为配置文件里存着 v1 的默认值 30）。做法：`CONFIG_VERSION = 2` + `migrate_params(params, version)` —— v1 里 `parse_max_lines == LEGACY_PARSE_MAX_LINES_DEFAULT (30)` 迁移为新默认 0，用户显式设过的其他值保留；`load_config` 按 `version` 调用；回写后版本升为 2，不会来回抖动。回归：`test/test_serial_proto_frame.py` 第 [9] 段 + `test_serial_tool_widget.py` 第 [25] 段（端到端：写 v1 配置 → 构造页面 → 显示「不限制」→ 真实解析 113 行全出）。
- 协议名映射用 `protocol_registry.get_protocol(i).short_name`（widget 内 `import protocol_registry` 是允许的：它不依赖 main_gui）。
- 导出/导入：`export_commands` 保留 `protocol` 键；`import_commands_file` 走 `normalize_commands`（缺键 → None）。

## 6. UI 变更

- 命令表：`ZoomableTableWidget` 由 4 列 → 5 列（`["名称", "发送数据 (HEX)", "匹配方式", "预期响应", "协议"]`）；第 5 列不可编辑，显示 `short_name` 或 `不解析`。
- 命令表 `cellDoubleClicked` → `_on_cmd_double_clicked(row, col)`（1.23.51）：`selectRow(row)` 后转调 `_edit_command()`，越界忽略；表格带「双击某一行可直接编辑该命令」提示。**不要给 `_edit_command` 加位置参数** —— 按钮 `clicked` 会带 bool（`checked`），会被当成行号（`False` → 第 0 行）。
- `SerialCommandDialog`：新增 `协议` 行（`QComboBox`，`不解析` + `[i] 名称` × 12），`get_data()` 返回 `protocol`。
- 「接收模式」行新增 `显示解析` 勾选（`chk_show_parse`，默认开）；`parse_max_lines` 用 `QSpinBox`（1~500，默认 30）。
- 按钮/控件全部走既有 `set_btn` / 主题 QSS，组件内不写 stylesheet。

## 7. 测试策略

| 测试文件 | 覆盖 |
| --- | --- |
| `test/test_serial_proto_frame.py`（新） | `frame_length_for` 7 策略 × 正常/越界/自证失败；`_emit_protocol_frames` 逐字节 / 分块 / 多帧连发 / 噪声前缀 / 未收全；HDLC 连续 7E 不产空帧；`format_parse_rows` 格式与截断 |
| `test/test_serial_tool_widget.py`（扩） | 协议列 UI；对话框默认值；`_coerce_protocol` 反例（bool/负数/越界/字符串/None）；落盘读回；旧配置无键回落；按协议解析输出（含失败行）；`显示解析` 关闭时零解析；burst 下不展开 parse |
| 既有 4 个测试 | 全绿（AC5.3） |

## 8. 契约 E：匹配诊断（1.23.50 补）

**问题**：匹配按**串口单次交付的块**比对（源工具语义），而驱动把一帧拆成多次交付（实测 208 字节国网帧 = 77+92+36+3）→「预期 = 整帧」永远匹配不上；且失败只打一句「超时未匹配」，现场无从分析。

**契约**：

```python
# 累积接收缓冲（跨交付块比对）；每次发送清空，队列清空时清空
self._match_buffer = bytearray()          # 上限 MATCH_BUFFER_MAX = 8192
self._match_rx_bytes = 0                  # 本窗口收到总字节数（诊断用）

def _on_rx_match_data(self, data):
    self._match_buffer.extend(data)       # 累积（超限丢最旧）
    accumulated = bytes(self._match_buffer)
    while self._pending_match:            # 队首连续匹配语义**不变**
        item = self._pending_match[0]
        if not check_match(accumulated, item["expected"], item["match_type"]):
            break
        ...
```

**为什么「累积 + 不清空」不会破坏「一批数据连续命中多项」**：`accumulated` 同时包含本批数据，故 `01 02` 仍能先命中 `01` 再命中 `02`（源工具语义保留）。**跨响应误判**由「每次发送清空 + 队列清空时清空」限制。

**日志**（走 RX/TX 队列，享受 burst 保护）：

```
[匹配] #1 查询从节点ID信息 等待响应：包含(contains)，预期 = 68 D0 00 …（共 208 字节）   ← 发送时
[匹配✓] #1 … 匹配成功（包含(contains)，预期 = …）                                      ← 命中
[匹配✗] #1 … 超时未匹配                                                                 ← 超时（5 行）
    匹配方式 = 完全相等(equals)
    预期响应 = AA BB CC
    期间收到 = 01 02（共 2 字节）
    诊断 = 长度不一致：预期 3 字节，收到 2 字节（完全相等要求长度也一致）
```

`match_failure_reason(match_type, expected, received, sent=None)` 是纯函数，按 6 种方式给结论；`sent` 用于识别最常见误填「预期 == 发送值」。配套纯函数：`hex_preview()`（超长 HEX 带总长）、`first_diff_offset()`、`match_type_label()`。

## 9. 契约 F：勾选发送 / HEX 容错 / 正则匹配（1.23.52 补）

**勾选发送**：命令 `enabled` 字段（`coerce_enabled`：缺键 → True）；表格第 0 列勾选框（`ItemIsEnabled | ItemIsUserCheckable`，范式同 `archive_widget.py`），`itemChanged` 回写 + 落盘（重建期间用 `_rebuilding_cmd_table` 抑制）。`_start_send` 过滤勾选项并传 `index_map`：

```python
messages, index_map = [], []
for i, cmd in enumerate(self.commands):
    if not coerce_enabled(cmd.get("enabled")):
        continue
    messages.append(hex_str_to_bytes(cmd["data_hex"]))
    index_map.append(i)          # sent 的 msg_index 回指 commands 原下标
```

**HEX 容错**（`hex_str_to_bytes`）：切分前统一分隔符（半角/全角逗号、顿号、半角/全角分号、`/`、`|`、`-`）并去 `0x` 前缀；片段 ≤2 字符按单字节（源工具语义），更长则要求偶数长度并 `bytes.fromhex`。**报错给原因**：`hex_input_error()` 指出「含非 HEX 字符 'X'（第 N 个字符）」或「片段字符数为奇数」。

**正则匹配**：`normalize_command` 对 `match_type == "regex"` 只校验正则语法（空正则降级）；`_on_sent` 用 `match_hex.encode("latin-1")` 得到模式字节（`check_match` 正是 `expected.decode("latin-1")` 后 `re.search`）；日志用 `expected_display()`（正则不加 repr）。

## 10. 契约 G：HEX 通配匹配（1.23.53 补）

**动机**：用正则匹配二进制帧要写 `\xNN`，且 `re.IGNORECASE` 会把「解码成字母」的字节大小写互配（实测 `\x68` 也命中 `0x48` —— 而 `0x68` 正是国网起始符），`.` 又不匹配 `0x0A`。现场太别扭。

**约定同源**（**必须与「测试方案」一致**）：`test_plan_widget._match_frame` 逐字符走、遇 `XX` 跳过一个字节 → 所以 `XX` 可内嵌连续串。

```python
def parse_hex_wildcard(pattern) -> Optional[List[Optional[int]]]   # None 元素 = 通配字节
def hex_wildcard_match(received, pattern) -> Optional[int]         # 命中返回偏移
def match_offset(match_type, received, expected) -> Optional[int]  # 统一入口（含偏移）
```

- 模式：`XX` / `??` = 任意一个字节；其余每 2 个字符一个字节；分隔符复用 HEX 容错那套；单独的 `X` 非法。
- 语义：默认**包含式**（任意位置）；`^` 前缀锚定开头、`$` 后缀锚定结尾（两者同写 = 全长）。
- `expected` 在 `_pending_match` 里对 `hex_wildcard` 存**模式文本**（同 `regex`），匹配时经 `match_offset` 分派。
- 日志：`expected_display()` 展示 `通配模式 68 D0 XX`；命中报「命中偏移 N」；失败由 `match_failure_reason()` 区分「模式比数据长」/「未匹配到」。

## 11. 契约 H：命令状态图标（1.23.55 补）

```python
CMD_STATUS_STYLES = {           # 状态 → (lucide 图标名, 颜色)
    "":          ("circle", "#9E9E9E"),          # 待测
    "running":   ("loader", "#1565C0"),          # 发送中 / 等待响应
    "pass":      ("check-circle", "#008000"),    # 通过
    "fail":      ("x-circle", "#C00000"),        # 失败
    "error":     ("alert-triangle", "#EF6C00"),  # 错误
}
CMD_STATUS_KEY = "_status"      # 命令字典里的运行时键（不落盘、不导出）
```

- **上色**：`app_icons.load_icon()` 只出单色 → 对渲染好的 pixmap 用 `CompositionMode_SourceIn` 整体染色（保留 alpha），并按 `(icon, color)` 缓存 QIcon。
- **渲染位置**：名称列（第 1 列）的 `QTableWidgetItem` 图标 + 前景色 + tooltip；`_rebuild_cmd_table` 建完单元格后调 `_refresh_cmd_row(row)` 统一上状态。
- **只重画一行**：`_refresh_cmd_row(i)` 改图标/颜色/文字，**不**整表重建（避免丢选中与滚动位置）。
- **迁移点**：`_start_send` → `_clear_cmd_statuses()`；`_on_sent` → 先 `"pass"`，真正入待匹配队列时改 `"running"`；`_on_rx_match_data` 命中 → `"pass"`；`_check_match_timeout` → `"fail"`；`_on_send_failed` → `_mark_running_as("error")`；`_stop_send`/`_finalize_send` → 剩余待匹配记 `"fail"`。
- **不落盘**：`export_commands` 剔除所有 `_` 开头的键（`save_config` 走它）。

## 12. 风险与取舍

1. **解析在 GUI 线程**：与既有匹配同口径。国网 208 字节帧 `parse_to_table` 实测行数 ~87，单帧耗时可忽略；若将来高速接收（数千帧/秒）出现滞后，把解析下沉到 worker（与匹配同批处理）—— 记录为已知取舍，不在本任务做。
2. **HDLC 帧含首尾 7E**：已核实 `HDLCParser.parse`（`hdlc_parser.py:1767`）要求 `frame_bytes[0] == 0x7E`，且 `main_gui._extract_hdlc_frames` 输出的就是含首尾 `7E` 的原始 hex —— 故 `_emit_protocol_frames` 直接产出原始字节即可，**不需要**先做 `7D 5E→7E` 还原。回归：`test_serial_tool_widget.py` 第 [19] 段。
3. **末字节 16H 自证只适用于 68 家族**：`END_CHAR_STRATEGIES = {ft12_68, dlt645, dlt698_45}`；HDLC（7E 定界）与 DLMS Wrapper（版本 + 长度）各有自证，套用 16H 检查会把它们全部拒绝（实现期实测踩到：Wrapper 帧被误拒）。
3. **698.45 长度域**：`L + 3` 依据协议文档 6.2.2（长度域 = 除两个 68H 与 16H 外的字节数）。若真机不符，末字节自证会失败 → 回落，不会切错。
4. **帧长上限**：`RAW_MAX_FRAME_LEN = 8192` 沿用；超限视为不可信（回落）。
5. **噪声前缀**（HDLC）：跳过噪声字节必须计入已消费，否则 `_raw_buffer` 无界增长（既有陷阱 58 的同类风险）。
