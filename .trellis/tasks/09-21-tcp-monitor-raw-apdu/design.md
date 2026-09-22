# 技术设计：TCP 监控原始载荷成帧 + APDU 显示 + UI 完善

对应 `prd.md`（R1~R8 / AC1.1~AC8.3）。本文只写技术设计与契约，不写需求。

## 1. 边界与模块划分

- **改动集中**：`monitor/tcp_monitor.py`（切帧 / 解析 / UI 三层）。
- **新增 1 个可复用组件**：`hex_dump_view.py`（Wireshark 风格字节视图，供 TCP 监控使用；后续主窗口可迁移，本次不动主窗口）。
- **复用（严禁新增第二份实现）**：
  - 解析入口：`protocol_registry.build_gui_parser(index, get_parser(spec.parser_key))`（F6，实测协议 0/2/3/4/5/6/7/8 均返回带 `parse_to_table` 的对象）
  - 证据判据：`validator.<proto>_validator` 的 `BaseValidator.verify(bytes) -> ValidationResult`（F7）
  - 字段树：`parse_result_view.build_tree_from_table_data()` / `build_ui_tree()`（F8）
  - APDU 标签表：`dl_t698_45_apdu_parser.APDU_TYPE_MAP`（698.45，首字节 → `(名称, 说明)`）、`hdlc_parser.APDU_TYPES`（DLMS，首字节 → 名称）
- **不改**：任何解析器内部实现、ED..EE 解包语义、`batch_core.unwrap_ed_for_parse` 契约（F9）。

## 2. 数据流与插入点

```
PacketSniffer(QThread) --signal--> _on_packet_received
  -> TCPFlowReassembler.process_packet
  -> TCPFlow.add_packet  ->  FlowBuffer.append/_deframe  ->  TCPFlow._frames
  -> _refresh_frame_list -> _parse_and_summarize -> _frame_cache + frame_table
  -> 选中帧 -> _on_frame_selected -> 字节视图 + 解析表/字段树
```

插入点三处：① `FlowBuffer`（切帧策略，R1）② `_parse_and_summarize`（分派与兜底，R2/R3）③ 视图层（R4~R8）。

## 3. 契约 A：`FlowBuffer` 切帧策略（R1）

```python
class FlowBuffer:
    def __init__(self, mode: str = "auto"):   # "auto" | "ed" | "raw"
```

- `mode="ed"`：与现状完全等价（只切 `ED..EE`）。
- `mode="auto"`（默认，既有调用点 `FlowBuffer()` 不变）：每方向状态 `_decided: None | "ed" | "raw"`
  1. 先跑既有 ED 切帧逻辑；**产出帧** → `_decided = "ed"`，按现状输出 ED 帧（丢弃非 ED 前缀）。
  2. **未产出帧**时：
     - `_decided == "raw"` → 直接按 segment 产出原始帧（不再扫 ED）；
     - 否则若缓冲区存在「ED 候选进行中」（存在 i 使 `buf[i] == 0xED` 且 `i + 6 > n`，即头未收全）→ 继续缓冲，不产原始帧；
     - 否则 → `_decided = "raw"`，按 segment 产出原始帧。
- **segment 边界（AC1.1 的硬要求）**：缓冲内记录每次 `append` 的起点 `_seg_marks: List[Tuple[int, float]]`。落入 raw 时按标记切出**多条** `(ts, bytes)`，绝不把多个 segment 合并成一条（长度必须等于该报文载荷长度）。
- 契约不变：`append(data, ts)`、`pop_frames() -> List[(ts, bytes)]`、`pending_bytes`；`TCPFlow.add_packet` 无需改动。
- **反例守卫**：原始载荷含 `0xED`（长度字节/数据字节常见）不得被误判为 ED 帧。只有既有**完整定界校验**全部通过（`buf[i]==0xED` + `frame_len ∈ [4, 4096]` + `buf[i+5]==0xEF` + `buf[i+total-1]==0xEE`）才转 ED；一旦判定 raw 不再回头。
- AC1.4：`append(b"", ts)` 不产生帧、不建 segment 标记。

## 4. 契约 B：解析分派与兜底（R2/R3）

```python
def _parse_and_summarize(self, frame: bytes) -> Tuple[str, str, list]:
    if frame[:1] == b"\xed":
        return self._parse_ed_frame(frame)     # 现主体逐字搬移，判据不变
    return self._parse_raw_payload(frame)      # 新增
```

- `_parse_ed_frame(frame)` = 现 `_parse_and_summarize`（`monitor/tcp_monitor.py:1111-1226`）主体**逐字搬移**：ED 包装行 + 3 协议候选 + `hdc_fc_evidence` CRC-24 自证重排。**不得改判据、不得改返回文案**（F9）。
- `_parse_raw_payload(payload)`：
  - 候选：显式选择 → 单候选；自动识别 → 按**结构特异性**顺序 `_RAW_DETECT_ORDER`：
    DLMS Wrapper → DLMS-APDU 裸报文 → DLT645-2007 → 698.45 → 南网 → 国网 → 国网新一代 → 南网新一代 → HDC 1.0。
  - 每候选：`build_gui_parser(index, get_parser(spec.parser_key))`（惰性 + 缓存 `_payload_parser_cache`）→ `parse_to_table(payload)`。
  - **命中判据（三层证据，已按校准实测收敛）**：
    1. **字节结构前置检查** `_raw_structural_hint(index, payload)`：Wrapper（`payload[:2] == 00 01` 且 Wrapper 长度自洽）/ DLMS-APDU（首字节 ∈ `hdlc_parser.APDU_TYPES`）/ 645（`payload[0]==0x68 and payload[7]==0x68`）——不满足直接跳过该候选；
    2. **非退化**：`len(rows) >= 2`；
    3. **择优**：候选得分 = 该协议特征字段名命中数 − 校验器 `fail_count`，取最高分且 > 0。
  - **校准实测（`test/_tmp_detect_calib.py` 一次性探针，结论已固化到测试）**：六个协议的 GUI 解析器对各自样本均能产出 9~25 行；但校验器**无跨协议判别力**——南网样本对南网/国网校验器都是 0 fail，698.45 样本对自身校验器 3 fail，Wrapper/APDU 校验器对非自身帧形 4 fail。因此校验器只作**择优项**（失败数越少越像），不作闸门。
  - **已声明边界**：698.45 / 南网 / 国网 同为 `0x68` 起头且链路层结构相近，自动识别为尽力而为，推荐显式选择（对齐既有 HDC MAC 帧的边界声明做法，见 `test/test_tcp_monitor_proto11_frames.py:337-342`）。
  - **兜底（AC3.1/AC3.2）**：全部未命中 → `("原始数据", summary, rows)`
    - `summary`：`f"TCP 载荷 {len(payload)} 字节"`；若首字节命中标签表，追加 `" | 疑似 698.45 APDU: {APDU_TYPE_MAP[b][0]}"` 或 `" | 疑似 DLMS APDU: {APDU_TYPES[b]}"`。
    - `rows`：至少 3 行 —— `("TCP 载荷", f"{n} 字节", "", "原始数据，未匹配到已知协议")`、`("首字节", f"0x{b:02X}", 标签名或"", "APDU 标签表命中/未命中")`、`("原始数据", hex(前 32B), "", "完整字节见「原始报文」视图")`。
  - AC3.3：任意二进制（非 ASCII / `0x00` / `0xED`）不得抛异常；`_parse_raw_payload` 整体 try/except 兜到兜底行。

## 5. 契约 C：字节视图组件 `hex_dump_view.py`（R4）

```python
class HexDumpView(QTextEdit):
    def set_bytes(self, data: bytes) -> None
    def highlight_range(self, start: int | None, end: int | None) -> None  # 字节下标，闭区间
    def clear_highlight(self) -> None
    def char_pos_of_byte(self, index: int) -> int | None   # 供测试与高亮定位
    @property
    def byte_length(self) -> int
```

- 行格式：`{offset:08X}  {16 个 hex，空格分隔}  |{ascii}|`；不可打印（`<0x20` 或 `>0x7E`）→ `.`；`setLineWrapMode(NoWrap)`、只读、`Consolas`。
- 高亮：与主窗口 `main_gui._apply_byte_highlight`（`main_gui.py:11204`）**同色同字体**（背景 `QColor(255,235,59,160)`，等宽字体）。主窗口按「每字节 3 字符」线性映射；本组件行内有偏移列，故用 `char_pos_of_byte()` 计算行内字符位置。
- AC4.4：`set_bytes(b"")` 不崩；≥4096B 正常渲染（`FlowBuffer.MAX_FRAME_LEN` 上限 4096）。
- 兼容：TCP 监控里保留旧属性名 `segment_hex` 指向该组件实例（既有引用不断裂），并新增 `frame_byte_view`。

## 6. 契约 D：解析结果 表 / 字段树 切换（R5）

- 切换控件 `QComboBox`（`表` / `字段树`），语义对齐主窗口 `result_view_combo`。
- 字段树：`build_tree_from_table_data(rows)` → `build_ui_tree(...)`；字节范围取 `FieldNode.byte_range()`（`parse_result_view.py:48`）。
- AC5.2：两种视图数据同源（同一 `rows`），字段数一致。

## 7. 契约 E：切换协议重解析（R7）

- `proto_combo.currentIndexChanged` → `_reparse_current_flow()`：遍历 `_frame_cache` 用新协议重算 `protocol/summary/parsed`，重填 `frame_table`；**帧字节、数量、顺序不动**（AC7.2）。
- 分帧结果不重算（切帧与协议无关）。
- >200 帧分批（`QTimer.singleShot(0, ...)` 链式），避免阻塞 UI（AC7.3）。

## 8. 兼容性与迁移

| 既有契约 | 处理 |
| --- | --- |
| `FlowBuffer()` 无参构造（`test_tcp_monitor_ed_hdc.py:115`） | 默认 `mode="auto"`，ED 方向行为与 `"ed"` 等价 |
| `_parse_and_summarize(frame)` 三返回值（`test_tcp_monitor_proto11_frames.py:228` 等直接调用） | 签名与返回值不变；ED 分支逐字搬移 |
| 协议下拉名称（`findText("HDC 1.0")` / `findText("南网新一代")`） | 只增不减，保留既有名称与顺序前缀 |
| `segment_hex` 属性 | 保留属性名，类型换为 `HexDumpView` |
| 帧表 5 列索引（时间/方向/长度/协议/摘要） | 新增「源 → 目的」列**插在第 1 列之后**，其余列索引后移；同步更新所有 `setItem(row, n, ...)` 调用点与 CSV 记录字段 |

## 9. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 原始载荷含 `0xED` 被误判为 ED 帧 | 完整定界校验 + 判定后不回头 + 专项反例测试（含 `0xED` 的原始载荷） |
| 自动识别误判（解析器退化结果算成功） | 校验器证据优先 + `len(rows)>=2` + 显式选择优先 + 每协议实测样本测试 |
| 重解析卡 UI | >200 帧分批 |
| 字节视图高亮错位 | 独立 `char_pos_of_byte()` + 单元测试锚定 |
| 帧表插列导致 CSV/索引错位 | 插列后全量检查 `frame_table.setItem` 与 `_write_csv_record` 调用点 |
| ED 回归 | `_parse_ed_frame` 逐字搬移；既有 3 个 TCP 测试全绿为硬门槛 |

## 10. 回滚

- 三块独立可回滚：切帧（`FlowBuffer`）、解析分派（`_parse_and_summarize`）、UI 视图层。
- 快速开关：`FlowBuffer(mode="ed")` 恢复旧切帧；`_parse_raw_payload` 直接返回 `("未知", "无法识别协议", [])` 恢复旧解析行为。

## 11. 验证策略

- 新增 3 个测试（见 `implement.md`），offscreen 可跑，登记 `release_check.py:CORE_TESTS`。
- 硬门槛：`test/test_tcp_monitor_ed_hdc.py`、`test/test_tcp_monitor_proto11_frames.py`、`test/hdc10_tcp_ed_frames.py` 全绿；`python release_check.py` 无新增 FAIL。
- 人工冒烟：真机抓一段含 ED 封装 + 原始载荷混合的流量，确认两类帧都成行、点击字段高亮正确、切换协议能重解析。
