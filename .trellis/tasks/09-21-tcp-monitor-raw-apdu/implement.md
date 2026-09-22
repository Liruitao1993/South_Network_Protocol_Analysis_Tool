# 实施计划：TCP 监控原始载荷成帧 + APDU 显示 + UI 完善

对应 `prd.md`（R1~R8）与 `design.md`（契约 A~E）。**每个 Block 完成后必须跑该 Block 的验证命令并全绿，才进入下一 Block。**

## B0 基线冻结（改代码前）

1. 记录改动前基线，确认后面能区分「我引入的失败」与「既有失败」：

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_ed_hdc.py
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_proto11_frames.py
QT_QPA_PLATFORM=offscreen python -u test/hdc10_tcp_ed_frames.py
python release_check.py --skip-tests
```

2. 已知既有失败（**不计入本次回归**）：`test/test_hdc10_batch_strip_level.py :: 帧类型含 [11]`（另一条批量重构工作线，见开发者 journal）。

**门禁**：3 个 TCP 测试全绿、`release_check --skip-tests` 无 FAIL。

## B1 字节视图组件（契约 C / R4）

1. 新增 `hex_dump_view.py`：`HexDumpView(QTextEdit)`，实现 `set_bytes` / `highlight_range` / `clear_highlight` / `char_pos_of_byte` / `byte_length`；行格式 `偏移 + 16 hex + ASCII`；高亮色与主窗口 `_apply_byte_highlight`（`main_gui.py:11204`）一致。
2. 新增 `test/test_hex_dump_view.py`（offscreen）：
   - 16 字节/行、偏移格式、不可打印字符转 `.`（含 `0x00`/`0xED`/中文 UTF-8 字节）
   - `char_pos_of_byte(i)` 与 `highlight_range(start, end)` 覆盖正确（含跨行区间）
   - `set_bytes(b"")` 不崩；4096B 渲染正常
   - 反例自检：故意偏移一位的高亮断言必须变红

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_hex_dump_view.py
```

## B2 `FlowBuffer` 切帧策略（契约 A / R1）

1. `FlowBuffer.__init__(mode="auto")`，新增 `_decided` 与 `_seg_marks`；实现 auto/ed/raw 三条路径（详见 `design.md` §3）。
2. 新增 `test/test_tcp_monitor_raw_payload.py`：
   - AC1.1：3 个原始 segment → 3 帧，逐帧长度等于各 segment 长度
   - AC1.2：ED 帧方向行为与改动前一致（帧数/帧长/内容）
   - AC1.3：同一批字节不重复产出（ED 帧数 + 原始帧数 == 期望）
   - AC1.4：空载荷不产生帧
   - 反例：原始载荷**含 `0xED`**（含「末尾是 0xED」与「中间是 0xED」两种）不得被误判为 ED 帧
   - `FlowBuffer(mode="ed")` 下原始载荷仍为 0 帧（旧行为可回滚）
3. 回归既有 ED 测试（`test_tcp_monitor_ed_hdc.py` 的 `FlowBuffer` 段）。

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_raw_payload.py
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_ed_hdc.py
```

**门禁**：新测试全绿 + 既有 ED 测试全绿（AC1.2/AC2.4 的硬门槛）。

## B3 解析分派与原始兜底（契约 B / R2 / R3）

1. 把现 `_parse_and_summarize` 主体**逐字搬移**为 `_parse_ed_frame(frame)`，`_parse_and_summarize` 变为 2 行分派（`design.md` §4）。
2. 新增 `_parse_raw_payload(payload)` + `_raw_payload_rows(payload)` + `_payload_parser_for(index)`（`build_gui_parser` 惰性缓存）。
3. 扩展候选与兜底（R2/R3），标签表复用 `dl_t698_45_apdu_parser.APDU_TYPE_MAP` / `hdlc_parser.APDU_TYPES`。
4. 测试（并入 `test/test_tcp_monitor_raw_payload.py` 或新建 `test/test_tcp_monitor_proto_detect.py`）：
   - AC3.1/AC3.2：随机二进制载荷 → 协议列「原始数据」、摘要含长度、解析行非空
   - AC3.3：非 ASCII / `0x00` / `0xED` 载荷不抛异常
   - 首字节命中标签表时给出「疑似 698.45/DLMS APDU: 名称」
   - AC2.3：698.45 / DLMS Wrapper / DLMS-APDU / 645 / 南网 / 国网 **各至少 1 例真实样本**自动识别命中（样本须来自仓库既有测试或协议文档示例，不得凭空造）
   - AC2.4：ED/HDC 既有样本判定与改动前一致

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_raw_payload.py
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_proto11_frames.py
```

**风险点**：698.45 / 645 / 南网 / 国网 均以 `0x68` 起头 —— 顺序与证据判据必须用真实样本校准，校准结论写进测试注释。

## B4 UI：字节视图接入（R4）

1. `segment_hex` 改为 `HexDumpView` 实例（保留属性名），`frame_byte_view` 用于「解析结果」Tab 帧字节。
2. `_on_frame_selected` / `_on_segment_selected` 填充字节视图；解析表行选中 → `highlight_range`。
3. UI 测试（新建 `test/test_tcp_monitor_ui_views.py`，offscreen）：
   - AC4.2/AC4.3：选中帧后 `byte_length == len(frame)`；选中解析行后高亮区间与字段 `byte_range` 一致
   - AC4.4：空帧、4096B 帧不崩

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_ui_views.py
```

## B5 UI：解析结果 表 / 字段树 切换（契约 D / R5）

1. 加 `表 / 字段树` 切换 `QComboBox`；字段树走 `parse_result_view.build_tree_from_table_data` + `build_ui_tree`。
2. 字段树选中 → 字节高亮（AC5.3）。
3. 测试：AC5.1/AC5.2（两视图字段数一致）、AC5.3（选中触发高亮）。

## B6 UI：帧表信息完善（R6）

1. 「源 → 目的」列插在「方向」之后；**同步更新所有 `frame_table.setItem(row, n, ...)` 调用点与 `_write_csv_record` 字段顺序**（插列是本次最容易漏改的地方）。
2. 未识别帧灰色弱化（`QTableWidgetItem.setForeground`）。
3. 测试：AC6.1（列值按方向正确）、AC6.2（未识别行存在且被弱化）、AC6.3（右键复制菜单仍在、列数一致）。

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_ui_views.py
```

**回归风险**：CSV 记录格式变化 → 同步检查 `_load_csv_recording` 的列读取，并跑一遍「记录 → 加载」往返测试。

## B7 UI：协议下拉扩展 + 重解析（契约 E / R2 / R7）

1. 下拉项改为「自动识别 + 全部 TCP 相关协议」，**保留既有名称与相对顺序**（`findText("HDC 1.0")` / `findText("南网新一代")` 必须仍可用）。
2. `currentIndexChanged` → `_reparse_current_flow()`（>200 帧分批）。
3. 测试：AC7.1（切换后 `_frame_cache` 与帧表同步重算）、AC7.2（帧数/顺序/字节不变）、AC2.1（下拉含全部要求项）。

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_ui_views.py
QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_ed_hdc.py
```

## B8 UI：过滤与空状态（R8）

1. 「仅显示未识别」勾选 + 协议过滤；过滤只影响显示（保留 `_frame_cache` 全量）。
2. 测试：AC8.1/AC8.2/AC8.3。

## B9 收尾

1. 登记 `release_check.py:CORE_TESTS`：`test/test_hex_dump_view.py`、`test/test_tcp_monitor_raw_payload.py`、`test/test_tcp_monitor_ui_views.py`（+ 若 B3 拆出 `test_tcp_monitor_proto_detect.py` 一并登记）。
2. `main_gui.py:APP_VERSION` 递增 + `CHANGELOG` 条目（含本次实测证据与验收映射）。
3. `release_check.py --sync-iss` 同步 Inno Setup 版本。
4. `AGENTS.md`：§8 新增陷阱（原始载荷成帧的 ED/raw 判定契约、自动识别证据判据、帧表插列需同步 CSV）+ §10 版本摘要。
5. 全量验证 + 人工冒烟：

```bash
QT_QPA_PLATFORM=offscreen python release_check.py
python main_gui.py     # 真机：抓一段含 ED + 原始载荷的流量，肉眼确认
```

## 顺序与回滚点

| Block | 可独立回滚 | 回滚方式 |
| --- | --- | --- |
| B1 | 是（新文件） | 删 `hex_dump_view.py` + 测试 |
| B2 | 是 | `FlowBuffer(mode="ed")` 或还原 `_deframe` |
| B3 | 是 | `_parse_raw_payload` 直接返回 `("未知","无法识别协议",[])` |
| B4~B8 | 是（UI 层） | 逐块还原对应 UI 代码 |

**依赖顺序**：B1 与 B2/B3 无依赖，可并行；B4 依赖 B1；B5/B6/B7/B8 依赖 B3（要有解析结果才谈视图与过滤）。

## `task.py start` 前的最终检查

- [ ] `prd.md` / `design.md` / `implement.md` 已评审通过（用户明确批准）
- [ ] B0 基线已记录（3 个 TCP 测试 + `release_check --skip-tests` 结果）
- [ ] 6 个真实协议样本（698.45 / DLMS Wrapper / DLMS-APDU / 645 / 南网 / 国网）已定位到来源（既有测试或协议文档示例）
- [ ] 回滚开关（`FlowBuffer(mode="ed")`）路径已想清
