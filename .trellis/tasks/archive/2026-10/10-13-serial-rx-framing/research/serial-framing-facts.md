# 证据固化：串口工具「协议特征断帧」与「可调字节超时」

> 本文件是本次实现的事实基线。实现不得与之冲突；若实测推翻某条，先改本文件再改代码。

## 1. 报障现象（用户现场，2026-10-13）

串口工具「接收模式 = 原始数据」，命令表协议列 = `698.45协议`（协议索引 8）。
日志里**一帧被切成两条 `[RX]`**：

```
[RX] FE FE FE FE 68 21 00 C3 05 06 05 04 03 02                                  (14 B)
[RX] 01 00 EA 33 85 01 2C 40 01 02 00 01 09 06 01 02 03 04 05 06 00 00 1A 38 16   (25 B)
```

- 完整包 = **39 B**（4×FE 前导 + 35 B 的 698.45 链路帧：`68 | L(2B LE)=0x0021 | C | SA | CA | HCS | APDU | FCS | 16`，L = 33 ⇒ 整帧 = L+2 = **35**，与 §5.6 帧长公式一致）
- 帧尾 `16H` ✔、`FE FE FE FE` 是规范前导（698.45 §6.3.1 b) 要求、645 §5.3.1 建议；桌面/Web 解析层已在 1.23.76 支持（`wakeup_prefix.py`）

## 2. 复现实测（1.23.77 工作区）

```python
strategy = STRATEGY_BY_PROTOCOL[8]              # "dlt698_45"
wakeup_prefix_len(首片 14B 以 FE 开头)           # 4
frame_length_for("dlt698_45", 首片含 FE)         # 0     ← 判不出
frame_length_for("dlt698_45", 首片剥离 FE)       # 35    ← 剥离后完全可判
```

根因链：`frame_length_for` / `declared_frame_len` 一律要求 **`buf[0] == 0x68`**，前导 FE 使首字节为 `0xFE`
⇒ 返回 0 ⇒ `_frame_incomplete()` 也判 False（`buf[0] != 0x68` 不满足 `min_hdr` 分支，`need=0` 直接
`return False`）⇒ 该段不被视为「已开始未收全的帧」⇒ 走 10ms 静默窗口 ⇒ 首片单独成一行，
余下 25 B 再成一行。

**这是 1.23.76 的已知取舍，不是新引入的**：AGENTS §8 陷阱 75 明确写了「串口/蓝牙**分帧策略表**也不变
（带 FE 时不满足 `buf[0] == 0x68` ⇒ 走既有时间聚合，整段交给解析回调，由链路层兜住）」——
链路层确实兜住了（解析成功），但**帧表行数、RX 帧统计、响应匹配窗口、日志可读性都被切碎**。
本次要把这条取舍改掉（串口工具侧）。

## 3. 现有实现锚点（`serial_tool_widget.py`）

| 位置 | 现状 |
|---|---|
| `RAW_FLUSH_DELAY_MS = 10` / `RAW_FLUSH_TICK_MS = 5` / `RAW_MAX_HOLD_MS = 200` | 原始模式的字节静默窗口 / 检查节拍 / 聚合最长持有 |
| `FRAME_IDLE_MS = 300` / `FRAME_HOLD_MAX_MS = 5000` | 已声明长度帧的等待静默 / 绝对等待上限 |
| `RAW_MIN_FRAME_LEN = 8` / `RAW_MAX_FRAME_LEN` | 整帧长度合理区间（`_sane_frame_len`） |
| `STRATEGY_BY_PROTOCOL`（0/7→`ft12_68`、6→`dlt645`、8→`dlt698_45`、2/3→`hdlc_7e`、4→`dlms_wrapper`） | 命令协议 → 分帧策略；未列协议（1/5/9/10/11）无自证依据 |
| `END_CHAR_STRATEGIES = {ft12_68, dlt645, dlt698_45}` | 这三种必须**末字节 16H** 自证（`_emit_*` 里判 `buf[need-1]`） |
| `frame_length_for(strategy, buf)` | 协议已知时的长度推算；`ft12_68` 只要 3 字节即可算 |
| `declared_frame_len(buf)` | 未指定协议时的启发式（645 双起始符 / 南网国网 `L` / 698 `L+2`，靠末字节自证互斥） |
| `_on_raw_data` → `_emit_protocol_frames`（有策略时）→ 时间聚合兜底 | 收到字节即尝试切帧 |
| `_flush_raw_display`（5ms 定时器） | 结构优先，再由 `idle_ms` / `held_ms` 与 `FRAME_IDLE/HOLD`、`RAW_FLUSH_DELAY/MAX_HOLD` 决定是否刷行 |
| `_frame_incomplete(strategy)` | 「已开始未收全」→ 继续等；**含**「头标志出现但长度域没够」的特例（1.23.57 修） |
| `_flush_raw_display_now` | 切模式/收尾时忽略静默窗口强制刷出（`cleanup()` 也调） |
| `DEFAULT_PARAMS` / `merge_params` / `migrate_params` / `CONFIG_VERSION = 2` | 参数持久化 + 默认值迁移（改**既有**参数的默认值才需要 bump 版本） |
| `_collect_params` / `_load_persisted` / `_schedule_save` | 控件 ↔ 配置的双向绑定（去抖 500ms） |

## 4. 本次要改的判据（结论）

1. **68 家族的分帧函数必须认前导 FE**：`{ft12_68, dlt645, dlt698_45}` 三种策略 + 无协议启发式，
   先跳过帧首连续 `0xFE`（**复用 `wakeup_prefix.wakeup_prefix_len`**，不另写扫描），
   长度都以「**含前导的总长度**」返回，于是调用方 `buf[need-1] == 0x16` 的自证天然正确。
2. **前导只对 68 家族成立**（HA 依据同 §8 陷阱 75）：HDLC（7EH 定界）与 DLMS Wrapper（版本 00 01）不加。
3. **四个时间窗要暴露成参数**（默认值一律沿用现值 ⇒ 对老用户零行为变化 ⇒ **不需要 CONFIG_VERSION 迁移**）。
4. **断帧方式**（`auto` / `timeout_only`）：`timeout_only` 时忽略协议结构与启发式，纯按字节超时聚合。
5. 无协议时**保留** 68 结构自证增强（用户 2026-10-13 选定：超时为主 + 结构自证即出帧）。

## 5. 相关既有陷阱（改前必读，改后要同步）

- **§8 陷阱 59**：`_declared_frame_len` 的三结构互斥、`ft12_68` 的排除条件、645 双自证。
- **§8 陷阱 58**：`_save_timer` 必须先于 `_build_ui()/_load_persisted()`；接收数据经信号进 GUI 线程再做匹配/分帧。
- **§8 陷阱 60**：日志唯一出口 `_log()`；`LogFileWriter` 的行为不受本次影响。
- **§8 陷阱 63**：新增按钮不得写死宽度（本次新增的是 QSpinBox / QLabel，但仍要避免与既有行挤压）。
- **§8 陷阱 75（需同步修订）**：其「串口分帧策略表不变」一句本次被推翻 —— 串口工具改为**认前导 FE**；
  蓝牙工具的分包/重组语义不变（仍以静默超时切帧，不在本次范围）。
- **§8 陷阱 49/59（配置迁移）**：仅当**改默认值**才需要 `CONFIG_VERSION` 迁移；本次只新增键。

## 6. 受影响的既有测试

- `test/test_serial_proto_frame.py`：`frame_length_for` / 策略表 / 配置迁移（102 项）——本次要扩「前导 FE」与「新增参数」两段。
- `test/test_serial_tool_widget.py`：第 [17] 段（四块交付复现，463 项）——本次加 [34] 段：**现场 FE 帧分两块交付 → 恰好 1 条 `[RX]`**、`timeout_only` 行为、四个参数持久化。
- 回归底线：`test_serial_worker_write_raw.py`（`SerialWorker` 未改）。
