# 技术设计：串口工具断帧（前导 FE + 可调超时）

## 1. 边界

**在范围内**：`serial_tool_widget.py` 的「原始数据」接收模式分帧链路（`frame_length_for` /
`declared_frame_len` / `_frame_incomplete` / `_emit_protocol_frames` / `_emit_structured_frames` /
`_flush_raw_display` / `_flush_raw_display_now`）+ 该页参数与 UI。

**不在范围内**：`SerialWorker`、响应匹配、`按帧尾分割` 模式、蓝牙工具、监控器、TCP 监控。

## 2. 契约（唯一来源）

| 语义 | 唯一来源 | 说明 |
|---|---|---|
| 前导 FE 判定 | `wakeup_prefix.wakeup_prefix_len` / `strip_wakeup_prefix` | **禁止**在分帧层另写 FE 扫描（AGENTS §8 陷阱 75 单一来源；1.23.76 已把该模块用于协议8/6 解析器与校验器） |
| 协议 → 分帧策略 | `STRATEGY_BY_PROTOCOL` | 未列出的协议 = 无自证依据 |
| 需要末字节 `16H` 自证的策略 | `END_CHAR_STRATEGIES` | 调用方判 `buf[need-1] == 0x16` |
| 整帧长度合理区间 | `RAW_MIN_FRAME_LEN` / `RAW_MAX_FRAME_LEN`（`_sane_frame_len`） | 作用于**剥离前导后的结构长度** |
| 断帧超时 | 4 个参数（默认 = 现行常量） | 见 §4 |

**长度返回口径（关键决策）**：分帧函数返回「**含前导 FE 的总字节数**」。
理由：三个调用点都已有 `buf[need-1] == 0x16` 的末字节自证，且 `del self._raw_buffer[:need]` 需要总量 ——
返回值语义保持一致，调用点**零改动**，新增的只有「下标偏移 + 总长换算」。

## 3. 数据流（改后）

```
SerialWorker.raw_data_received
  └─ SerialToolWidget._on_raw_data(data)           ← GUI 线程（既有口径）
       ├─ _on_rx_match_data(data)                  累積缓冲匹配（不受本次影响）
       ├─ 「按帧尾分割」→ _frame_buffer / _flush_frames            （不受本次影响）
       └─ 「原始数据」→ _raw_buffer.extend(data)
            ├─ 断帧方式 = timeout_only ? 不做结构切帧
            │   └─ auto ? 有协议 → _emit_protocol_frames(strategy)
            │              无协议 → _emit_structured_frames()      （68 启发式）
            └─ 5ms 定时器 _flush_raw_display()
                 ├─ 结构路径（同上）
                 └─ 时间路径：_frame_incomplete(strategy)
                       True  → 等 min(协议帧等待静默, 协议帧等待上限)
                       False → 等 min(字节静默超时, 聚合最长持有)
                       → 超限即 _emit_raw_chunk()

分帧函数内部（68 家族，新增）：
  base = wakeup_prefix_len(buf)          # 0..N
  buf[base] 必须是 0x68 才继续；结构判定与下标一律 +base
  返回 base + 结构长度
```

## 4. 参数（新增 4 键 + 1 键，默认值 = 现行常量）

| 键 | 默认 | 范围 | 作用 |
|---|---|---|---|
| `rx_byte_idle_ms` | `RAW_FLUSH_DELAY_MS` = 10 | 1~2000 | 无结构可判时的字节静默窗口（「字节超时」本体） |
| `rx_raw_max_hold_ms` | `RAW_MAX_HOLD_MS` = 200 | 10~60000 | 持续流下强制刷出的最长持有（防缓冲无界） |
| `rx_frame_idle_ms` | `FRAME_IDLE_MS` = 300 | 10~60000 | 已认出一帧但未收全时的静默容忍 |
| `rx_frame_hold_max_ms` | `FRAME_HOLD_MAX_MS` = 5000 | 100~600000 | 一帧的绝对等待上限（防中途断流挂死） |
| `rx_framing_mode` | `"auto"` | `auto` / `timeout_only` | 断帧方式 |

- **不改默认值 ⇒ 不改 `CONFIG_VERSION`**（只新增键，`merge_params` 自动补默认）。
- 取值经 `_clamp` 后使用；`range` 常量集中在模块级 `FRAME_TIMEOUT_RANGES`，UI 与夹紧共用一份。

## 5. 关键决策与取舍

1. **前导 FE 只在 68 家族生效**：HA 依据同 AGENTS §8 陷阱 75（698 §6.3.1 b)、645 §5.3.1）。
   HDLC/Wrapper 首字节另有语义，加容忍反而会掩盖错帧。
2. **长度含前导**（而非让调用方加 base）：调用点零改动、`need-1` 自证天然正确；比在三个调用点各加一次
   `+ skip` 更不容易漏。
3. **纯 FE 缓冲视为「未收全」**：FE 之后必然要跟 `68` 才是帧；但必须有**上限**兜底（R2 的等待上限），
   否则噪声会永久挂住。测试要钉住「最终刷出且不丢字节」。
4. **`timeout_only` 只影响「原始数据」模式**：`按帧尾分割` 本就与协议无关。
5. **断帧说明行只在设置变更 / 每轮开始**：逐帧打印会把日志冲垮（AGENTS §8 陷阱 58 的 burst 精神）。
6. **不加「按协议强制」第三档**：`auto` 在有协议时**已经**是「只按该协议切」（不使用启发式），
   与用户诉求一致；多一档徒增解释成本。

## 6. 兼容性与回归风险

| 风险 | 判据/处置 |
|---|---|
| 无 FE 输入的行为漂移 | 分帧函数在 `base == 0` 时是**恒等变换**（既有分支一字不改，只把 `buf[i]` 改写为 `buf[base+i]`）；`base==0` 断言 + 既有测试全绿 |
| 前导 FE 误伤：以 FE 开头但**不是** 68 家族的数据 | 结构函数在 `buf[base] != 0x68` 时照旧返回 0 → 走时间聚合（可能多等一个静默窗口，不丢数据） |
| 参数即时生效导致「改一半生效」 | 4 个 spin 的 `valueChanged` → 只更新 UI 与去抖保存，取值在分帧时实时读控件（无缓存不一致） |
| 老配置无新键 | `merge_params` 补默认 ⇒ 行为与旧版一致（无需迁移） |
| 新增控件挤压既有「接收模式」行 | 断帧设置放**独立分组行**（`QGroupBox("断帧设置")`，2 行网格），不动既有行；沿用 AGENTS §8 陷阱 63 的判据（`width() >= sizeHint().width()`）抽查 |

## 7. 回滚

- 改动集中在 `serial_tool_widget.py` 一个文件 + 测试 + 文档；无运行数据格式变化
  （配置只**多**了 5 个键，旧版读到时忽略未知键）。
- 回滚 = `git checkout serial_tool_widget.py` + 移除测试段（无需清理运行时数据）。
