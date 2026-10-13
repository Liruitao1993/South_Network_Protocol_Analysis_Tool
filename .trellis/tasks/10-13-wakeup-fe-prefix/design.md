# 技术设计：前导 FE 唤醒字节容忍

## 0. 结论一句话

**把「跳过前导 FE」放进链路层解析器本身**（协议6/8 各一处），而不是放进 5~6 个调用点；
表格偏移由「解析器报告跳过的字节数 + 表格构建方整体位移」保持一致；
两个校验器复用同一判定，消除「解析成功但校验报起始字符错误」。

## 1. 为什么放在解析器层，而不是各调用点

### 备选方案对照

| 方案 | 覆盖面 | 偏移/高亮 | 漂移风险 | 判定 |
|---|---|---|---|---|
| A. 各调用点预剥离（`parse_single` / `_serial_parse_provider` / 快捷小窗 `_preprocess` / Web 单帧 / 两处校验入口） | 需逐一枚举，共 6 处 | 需各自决定是否重写输入框 | **高**：项目已有 Web↔GUI 解析链复制体漂移史（AGENTS §8 陷阱 31） | 否 |
| B. `analyze_frame` 式的「输入规范化」新入口 | 需改所有调用方 | 同 A | 高 | 否 |
| **C. 解析器/校验器内部容忍（本设计）** | 全部既有与未来调用方（单帧/串口/蓝牙/快捷小窗/批量详情/Web/虚拟表） | 解析器报告跳过数，表格行整体位移，与原始输入对齐 | **低**：单一来源模块 + 两个表格构建方共用位移函数 | **采纳** |

### 直接证据

- 协议8 规范 **明确要求** 前导码：`协议文档/8.698.45协议/面向对象的用电信息数据交换协议(20210910).md:509`
  「b) 在有效数据帧前加 4 个 FEH 作为前导码；」（§6.3.1 字节规则）
- 协议6 规范：`DLT645-2007.md:486`「§5.3.1 前导字节：在主站发送帧信息之前，建议先发送 4 个字节 FEH」
- 帧的首字节判据在链路层（`START_CHAR = 0x68`），前导码同属链路层 ⇒ 链路层负责跳过，语义正确。
- 项目内先例：`meter_sim/link_layer.py`、`dlt645_sim/link_layer.py` 的帧提取**已经**跳过 FE 前缀
  （「跳过 FE 前缀与杂字节（在 68 之前同步）」）⇒ 本项目一贯把「FE 前导」视为链路层关注点，本设计与之对齐。

## 2. 单一来源模块：`wakeup_prefix.py`（新增）

纯逻辑、零依赖、不 import 任何 parser/Qt（可被解析器、校验器、表格构建方安全引用）：

```python
WAKEUP_BYTE = 0xFE
WAKEUP_FIELD_NAME = "唤醒前导字节"

def wakeup_prefix_len(data: bytes) -> int          # 帧首连续 0xFE 的个数（不做其它猜测）
def strip_wakeup_prefix(data: bytes) -> tuple[bytes, int]
def wakeup_display(skipped: int) -> str            # "FE FE FE FE"
def shift_row_offsets(rows: list, delta: int) -> list
    # 仅位移 (第5列, 第6列) 同时为 int 的行；None（APDU 子行等）原样保留
```

**判定口径**：只跳过**帧首连续的 `0xFE`**，其余字节一律不猜。长度取「实际连续个数」（0~N），
不假定恰好 4 个（698 规范写 4，实机与 645 均为「建议/实际可变」；`FE FE` 也必须能解析）。
`0xFE` 在任何 68 家族帧内都不可能作为首字节出现（首字节恒 `0x68`）⇒ 零误伤。

**为什么把 `shift_row_offsets` 也放这里**：协议8 的表格在 `dl_t698_45_parser.parse_to_table` 里构建，
协议6 的表格在 `protocol_registry.DLT645GuiParser.parse_to_table` 里构建 —— 两个构建方必须用**同一套位移规则**
（都只位移 int 偏移、都跳过 None），否则偏移口径会漂移。放同一模块 = 一个可测的判据。

## 3. 文件级改动

### 3.1 `dl_t698_45_parser.py`（协议8）

- `parse()`：
  - `result["原始数据"]` **保持用户原始输入**（含 FE，追溯用；既有断言 `raw_hex == input.hex()` 不变）。
  - 紧随其后 `frame_bytes, skipped = strip_wakeup_prefix(frame_bytes)`（就地重绑局部名，下游 20+ 处
    `frame_bytes` 引用零改动、零语义变化）。
  - `skipped > 0` 时写 `result["唤醒前导"] = {"字节数": skipped, "原始值": wakeup_display(skipped)}`。
- `parse_to_table()`：
  - 从 `result` 取 `skip`；正常路径在**首行**插入
    `(WAKEUP_FIELD_NAME, "FE FE FE FE", "-", "串行前导码（698 §6.3.1 b)），非帧内容，解析已跳过", 0, skip-1)`，
    其余行过 `shift_row_offsets(rows, skip)`。
  - 失败分支（`解析状态 == 失败`）同样插入前导行（该分支其余行偏移为 `None`，不受位移影响）。
  - `skip == 0` 时**完全走原路径**（硬约束：无 FE 帧输出逐行相同）。

### 3.2 `dlt645_parser.py`（协议6）

- `check_structure` / `calc_checksum` / `check_frame` / `parse` 四个公开入口统一先 `strip_wakeup_prefix`：
  - `calc_checksum(data)` → `frame, _ = strip_wakeup_prefix(data); return sum(frame[0:-2]) & 0xFF`
    （既有守卫 `calc_checksum(f) == sum(f[0:-2]) & 0xFF` 对无 FE 帧**恒成立**，因为剥离是恒等操作）。
  - `check_structure(data)`：先剥离再判 `len >= 12` / `data[0]==0x68` / `data[7]==0x68` / `data[-1]==0x16`；
    对已剥离输入幂等（首字节是 68 时跳过 0 字节）。
  - `check_frame` 语义不变（= 结构 ∧ CS）。
- `parse()`：剥离后按既有逻辑解析；`raw_hex` 保留原始输入；新增 `wakeup_len`；
  `wakeup_len > 0` 时在 `fields` 顶部插入 `(WAKEUP_FIELD_NAME, "FE FE FE FE", note)`（3 元组，符合既有行形状守卫）。
- `valid` 语义**不变**（结构 ∧ 校验 ∧ 长度相符）；`dlt645_sim` 不感知 FE（其输入来自自建帧）。

### 3.3 `protocol_registry.py::DLT645GuiParser.parse_to_table`（协议6 表格，桌面+Web 唯一实现）

- `skip = int(result.get("wakeup_len", 0) or 0)`。
- 所有既有分支的字面偏移 **整体 + skip**（`帧起始符 1` 0→skip、`从站地址` 1~6→1+skip~6+skip、
  `帧起始符 2` 7+skip、`控制码`/`数据长度` 8+skip / 9+skip、`数据标识 DI` 10+skip~13+skip、
  `数据内容` 14+skip~data_end+skip、`数据域` 10+skip~data_end+skip、`校验和` cs_pos+skip、`帧结束符` end_pos+skip）；
- 新增分支 `"前导" in field → (0, max(0, skip-1))`（**必须放在其它分支之前**，且与 `-1` 取 max 防 skip=0 越界）；
- `skip == 0` 时输出与改动前逐行相同（`test_dlt645_table_offsets.py` 40 项 + `test_dlt645_tolerant_parse.py` A9 全绿）。

### 3.4 `validator/dl_t698_45_validator.py`

- 入口 `frame, skip = strip_wakeup_prefix(frame_bytes)`；`n = len(frame)`；
  最小长度 / 起始字符 / 长度域一致性 / 结束字符全部基于 `frame`；
  `skip > 0` 时**在最前面**追加 `CheckItem("前导码", PASS, "FE×N", f"{skip} 字节", "跳过 N 字节 FE 前导码（698 §6.3.1 b)）")`；
- HCS/FCS 来自 `self.parser.parse(frame_bytes)`（解析器已容忍，**继续传原始字节**，避免两处剥离逻辑）。

### 3.5 `validator/dlt645_validator.py`

- 同样入口剥离；`_check_min_length` / `_check_start_char(0)` / `_check_start_char(7)` /
  `_check_end_char` / CS（`frame[-2]`）/ 数据长度（`frame[9]`）全部基于 `frame`；
  `skip > 0` 追加 PASS 说明项（说明引 645 §5.3.1）。

## 4. 不改的东西（明确边界）

| 位置 | 现状 | 本任务 |
|---|---|---|
| 批量提取 `_extract_69845_frames`（桌面/`batch_core`/Web） | 从 `"68"` 起同步，**已**天然跳过 FE | 不改；新增「带 FE 混合日志仍正确提取」测试钉住 |
| 串口工具分帧 `frame_length_for("dlt698_45"/"dlt645")` | 要求 `buf[0] == 0x68`；带 FE 时返回 0 ⇒ 走时间聚合 | 不改（整段交给解析回调，由 3.1/3.2 兜住）。理由：改分帧会**丢掉**界面上的原始 FE 字节显示，且时间聚合在同一次交付时已能整帧输出 |
| 协议 0/7/9/10/11/12/13 | — | 行为不得变化（新增护栏测试） |
| 蓝牙分包尺寸 | `min(200, 特征码免响应写上限 / MTU−3)`，下限 20 | 不改（ATT 物理限制）；只加日志说明 |
| 「包间延迟」默认 20 ms | 用户可配 | 不改默认值（改默认值需配置迁移，AGENTS §8 陷阱 59）；仅文档建议设为 0（698 §6.3.1 c)「帧的字节之间无线路空闲间隔」） |

## 5. 偏移与高亮的正确性论证

用户输入 `FE FE FE FE 68 21 00 …`（39 字节）。解析器内部在**剥离后的 35 字节**上计算，
故其行偏移是「相对帧」的（`起始字符` = 0、`结束符` = 34）。表格构建方整体 `+4` ⇒
`起始字符` = 4、`结束符` = 38，**与用户输入框的字节下标严格对齐**（GUI 高亮、串口日志偏移均正确）。
`parse_single` 的 `_last_parsed_hex = hex_display` 是原始输入 ⇒ 高亮命中正确字节，无需改 `main_gui`。

## 6. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 误把真实错帧「救活」（前导剥离掩盖首字节错误） | 只剥 `0xFE`（68 家族首字节恒 68，FE 不可能是合法首字节）；剥离后仍走全部结构与校验判据，坏帧照旧报错 |
| 无 FE 帧输出发生变化 | 硬约束 + 对拍锚点测试（无 FE 帧表格/fields 与改动前逐行比对） |
| 偏移位移漏掉某个分支（645 有 9 个分支） | 用 `shift_row_offsets` 统一位移而非逐分支手写；测试对**每一行**断言偏移 |
| 698 `原始数据` 语义被改 | 明确保留原始输入（含 FE），新增 `唤醒前导` 字段承载新信息 |
| 蓝牙日志改动影响既有断言 | 只**新增**一条 `log_message`（不改分块尺寸与信号顺序），`test_bluetooth_worker.py` 补断言 |

**回滚**：本次改动不涉及持久化格式与数据文件，回滚 = `git checkout` 涉及的 6 个文件 + 删除新增模块/测试。
无数据迁移、无配置迁移。

## 7. 蓝牙分包（报障 2）的结论与落地

- 代码链：`bluetooth_worker._write_coro` → `_chunk_size_for(targets)`
  → 有 `max_write`（`max_write_without_response_size`）时 `max(20, min(200, max_write))`，
  否则 `chunk_size_for_mtu(mtu, 200) = clamp(mtu-3, 20, 200)`。
  现场实测 20 字节 ⇒ 协商 **MTU = 23**（BLE 规范最小默认值，对端未协商放大）。
- **物理上限**：ATT 头占 3 字节，`MTU=23` 时单包 ≤ 20 字节 ⇒ 25 字节必然 2 包。应用层无解。
- **落地**：`_write_coro` 在 `len(chunks) > 1` 时输出
  `按单包上限 20 字节分 2 包写入（协商 MTU=23）`（数值全部取自同一来源，禁止界面另算）；
  小窗/文档写明「减少分包只能靠设备端支持更大 MTU」与「698 帧内不得有空闲间隔 ⇒ 建议包间延迟设 0」。
