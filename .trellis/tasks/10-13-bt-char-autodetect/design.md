# 技术设计：蓝牙特征码自动优选 + 一键探测 + 按设备记忆

## 1. 边界

**在范围内**：`bluetooth_core.py`（打分/优选/探测状态机/记忆/探测载荷解析）、
`bluetooth_worker.py`（**只加**一个订阅完成信号）、`bluetooth_tool_widget.py`（自动优选接线、探测按钮与驱动、
状态行摘要、对话框预选/置顶/标注）、四份蓝牙测试、文档与版本。

**不在范围内**：BLE 收发链路（`send_data`/分包/`BleReassembler`）、虚拟串口透传、`main_gui` 接线、
`reflex_web/`（Web 版无蓝牙页）。

## 2. 契约（唯一来源）

| 语义 | 唯一来源 | 说明 |
|---|---|---|
| 特征码打分与排序 | `bluetooth_core.rank_characteristics` / `char_score` | **禁止**在界面再写一份「第一个可用的」逻辑（本次就删掉旧的 `_auto_pick` 朴素实现，改委托） |
| 自动优选结果 | `bluetooth_core.pick_auto(chars)` | 返回 `(recv, send, reason)`；`reason` 直接进日志 |
| 权重/族谱常量 | `bluetooth_core` 模块级 `CHAR_SCORE_*` / `PASSTHROUGH_HINTS` / `PASSTHROUGH_UUIDS` / `STANDARD_GATT_*` / `OTA_DFU_*` | 调参只改这一处 |
| 探测流程 | `bluetooth_core.ProbeSession` | 纯状态机；界面只负责「按意图调 worker + 计时 + 喂事件」 |
| 探测载荷 | `bluetooth_core.resolve_probe_payload` | 复用 `parse_plain_text`（HEX 写错 → 错误，不写） |
| 配置键 | `bluetooth_core.DEFAULT_SETTINGS` / `merge_settings` | `char_map` / `probe_frame` / `probe_timeout_ms`；校验只在这一处 |
| 订阅就绪 | `bluetooth_worker.subscribe_finished = Signal(list, bool)` | 探测必须先等到它才能写（否则丢首个回包） |

## 3. 数据流

```
连接成功 → worker.characteristics_updated(list)
  └─ widget._on_characteristics_updated
       ├─ char_map 命中该地址？ → 沿用（source="recall"）→ worker.set_characteristics
       └─ 否则 core.pick_auto → worker.set_characteristics（source="auto"）+ 日志给依据
                                     ↓
                               状态行「发送 → 0xFFE1 ｜ 接收 → 0xFFE1」

点「自动探测」→ widget._start_probe
  payload = core.resolve_probe_payload(edit_send.text(), mode, settings.probe_frame)
  session = core.ProbeSession(candidates=core.probe_candidates(chars, N=6), payload=payload,
                              timeout_ms=settings.probe_timeout_ms)
  loop: intent = session.next()
     select_recv(uuids) → worker.set_characteristics(recv, send)        # 期望 subscribe_finished
     write(payload)     → worker.send_data(payload)                     # 期望 data_sent / 失败
     wait(ms)           → QTimer 单项超时
  事件：worker.subscribe_finished → session.on_subscribed(ok)
        worker.frame_received     → session.on_frame(len(bytes))
        QTimer                    → session.on_timeout()
  session.result(): 成功 → _apply_characteristics + _remember(address, source="probe") + 日志
                    失败 → 逐候选原因 + 保留原选择 + 提示手工选
```

## 4. 打分表（初版，集中可调）

| 要素 | 分值 | 依据 |
|---|---|---|
| `can_send and can_recv`（同码双属性） | +50 | 透传模块最常见的回环通道 |
| 族谱命中（`FFE1` / `6E400002` / `6E400003` / `FFE5` / `FFE9` / `FFF0~FFF2` / `FFF6` / `FF01/FF02` / `AE01/AE02` / `FF10/FF11`） | +40 | 市面透传模块约定 |
| 名称/描述/服务名含 `tx/rx/uart/write/notify/serial/串口/透传` | +20 | 厂商命名习惯 |
| 与「最佳写码」同属一个 service | +15 | 透传对（TX/RX）同服务 |
| 标准 GATT（`2A00~2AFF` 特征码 / `1800/1801/180A/180F` 服务） | −60 | 设备名/电量/固件版本不承载业务 |
| OTA/DFU（`FE59`、`1530`、`FFC0/FFC1`） | −60 | 误写有风险 |
| `can_send` 但无 `can_recv`（仅用于发送侧的兜底） | 0 | 仍可作为发送通道 |

排序：分数降序，**同分保持设备枚举顺序**（稳定）；`pick_auto` 取分数最高者作为发送通道，
接收通道优先取**同一条码**（若它也能收），否则取同服务内分最高的可收码，再否则全局分最高的可收码。

## 5. 关键决策与取舍

1. **默认零副作用**（用户选定）：连接后只做「属性 + 命名」优选，不写任何字节；真写只在用户点「自动探测」时发生，
   且 tooltip + 日志都明说。避免把「连上就发 AT」这种可能改变模块状态的行为设为默认。
2. **纯逻辑下沉到 `bluetooth_core`**：打分、候选配对、探测状态机、记忆读写、探测载荷解析全部无 Qt / 无 bleak
   → 可脱硬件单测（陷阱 69 的既有约定），界面只做「调 worker + 计时 + 喂事件」。
3. **新增订阅完成信号而不是让界面 sleep**：订阅是 async，写早了会丢首个回包；再用 `log_message` 猜时机不可靠。
   信号只**新增**（既有信号语义不变），worker 测试用假 bleak 覆盖两条路径。
4. **记忆以地址为键 + 保留全局旧键**：向后兼容旧配置；命中地址优先于全局；上限 20 条按 `ts` 淘汰（防配置膨胀）。
5. **对话框只做「预选 + 置顶 + 可读标注」**：不重写成向导（用户要的是少点几下，不是删能力）；置灰不可依赖
   （陷阱 71），所以不可用项加显式文字。
6. **失败必须可读**：「订阅失败 / 写入失败 / 写入成功但 N ms 内无回包」三类原因分别输出，不合并成「探测失败」。

## 6. 兼容性与回归风险

| 风险 | 判断/处置 |
|---|---|
| 旧配置无新键 | `merge_settings` 补默认；行为与旧版一致（只是自动优选更准） |
| `char_map` 坏数据（非 dict / uuid 非字符串 / 超长） | `merge_settings` 逐条丢弃坏条目，不影响其它条目与启动 |
| 打分把非透传设备选错 | 提供「特征码…」与「自动探测」两条兜底；日志始终给出**依据**，用户能立刻判断 |
| 探测期间用户点发送 / 切页 | 探测期间禁用发送与探测按钮；`cleanup()` 停止探测定时器（不残留） |
| worker 新增信号影响既有测试 | 既有四份测试必须全绿（信号只加不改） |
| 与 `main_gui` 的接线 | 不改：页面仍由 `_ensure_bluetooth_tool_tab` 懒加载 + 注入（`set_bluetooth_worker` / 三 provider） |

## 7. 回滚

- 改动集中在三个模块 + 测试 + 文档；配置只**多**了 3 个键（旧版忽略未知键）。
- 回滚 = `git checkout bluetooth_core.py bluetooth_worker.py bluetooth_tool_widget.py` + 移除新增测试段；
  无需清理运行时数据（`char_map` 残留键不影响旧版）。
