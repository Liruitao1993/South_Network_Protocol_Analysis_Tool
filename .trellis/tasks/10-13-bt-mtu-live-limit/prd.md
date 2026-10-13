# 蓝牙工具：连接后轮询 MTU 协商结果 + 每次发送前重读实时写上限

## Goal

修掉蓝牙工具「单包上限永远是连接那一刻的快照」这一缺陷：用户现场看到同一台设备
**有时 20 字节、有时 512 字节**（截图：0xFFE1 显示「免响应写上上限：20 字节」），
根因是 ATT_MTU 由 **操作系统异步协商**，而我们在连接瞬间只读了一次快照。

本次改动让蓝牙页：

1. 连接后**轮询等协商结果**（值变了就更新界面与表格）；
2. **每次发送前重读实时上限**，按发送那一刻的真实值分包。

## 背景证据（实现必须与此一致）

- 界面显示的「免响应写上上限」= `bluetooth_worker._collect_characteristics()` 里的
  `char.max_write_without_response_size`（`bluetooth_worker.py:406`）；MTU 行 =
  `client.mtu_size`（`bluetooth_worker.py:325`）。
- Windows（bleak winrt 后端）这两个值都是**实时**的：
  - `bleak/backends/winrt/client.py:573` → `mtu_size` = `self._session.max_pdu_size`
  - `bleak/backends/winrt/client.py:770` → `max_write_without_response_size` =
    `lambda: self._session.max_pdu_size - 3`
- bleak 官方文档（`bleak/backends/characteristic.py:89-91`）明确写：
  > In rare cases, a device may take a long time to update this value, so reading this
  > property may return the default value of `20` and reading it again after some time
  > may return the expected higher value.

  并建议用 `while char.max_write_without_response_size == 20: await asyncio.sleep(...)` 等。
- 该值变化由 OS 驱动：`MaxPduSizeChanged is raised whenever the negotiated MTU for the
  Attribute Protocol (ATT) is changed. And that can be changed or negotiated by a remote
  Bluetooth peripheral. As a developer, you can't change the value used by Windows
  itself`（MS Learn `GattSession.MaxPduSizeChanged`）——**应用层只能读，不能请求**。
- 竞态是真实存在的：bleak issue #1497「MTU size incorrect on Windows」中，
  `mtu_size` 已是 247/498 而 `max_write_without_response_size` 仍返回 20，
  维护者判定为 `max_pdu_size_changed` 事件比服务枚举更晚到达（已由 PR #1552 修复后端，
  但**快照式读取**仍会拿到旧值）。

## Requirements

### R1 连接后轮询协商结果

- R1.1 判据单一来源：新增纯逻辑 `bluetooth_core.mtu_is_unnegotiated(value)`
  （`value <= MTU_DEFAULT`，含 0 / `None` / 非法值 ⇒ 视为未协商），
  常量 `MTU_DEFAULT = 23`、`MTU_POLL_INTERVAL = 0.25`、`MTU_POLL_TIMEOUT = 3.0`
  与既有 `MIN_CHUNK`/`DEFAULT_MAX_CHUNK` 同处（`bluetooth_core.py`）。
- R1.2 `BluetoothWorker._connect_coro` 在 **emit `connected` / 完成订阅之后**才等待协商结果
  （不得把 UI 与订阅卡在轮询上）：仅当 R1.1 判定为未协商时启动轮询，每 `MTU_POLL_INTERVAL`
  重读一次，直到值变化（成功）或 `MTU_POLL_TIMEOUT` 到期（放弃）。
- R1.3 成功：更新 MTU 与各特征码上限，发 `mtu_updated` 信号，日志一行
  `MTU 协商更新：23 → 247（特征码免响应写上限 244）`。
- R1.4 超时：**只打一行**提示（`3.0 秒内未收到 MTU 协商结果…对端可能只支持 ATT 默认值`），
  MTU 保持原值；不得把「对端确实只支持 23」误报成错误。
- R1.5 轮询期间断开 / 已切到别的 client / 已 shutdown：立即停止，不抛异常、不发信号。

### R2 每次发送前重读实时上限

- R2.1 `_write_coro` 在计算分包尺寸**之前**调用统一的 `_refresh_live_limits()`：
  重读 `client.mtu_size` 与**活特征码对象**的 `max_write_without_response_size`。
  判据为 bleak 的实时 property（Windows 上等价于 `session.max_pdu_size - 3`），
  **不得**在 worker/界面另写一份「MTU − 3」推导（分包尺寸的推导只允许出现在
  `core.chunk_size_for_mtu` 与 `_chunk_plan`）。
- R2.2 值**有变化**才更新 + 发信号 + 打日志；无变化时完全静默（不得每包刷日志）。
- R2.3 活对象私有持有（`self._char_objects`），**不得**混进投给界面的 dict
  （界面 dict 保持纯数据）。

### R3 界面跟随

- R3.1 新增信号 `mtu_updated = Signal(int, list)`（新的 MTU, 最新特征码 dict 列表），
  只为「上限变化」服务：**不得**复用 `characteristics_updated` 代替
  —— 后者会触发界面 `_on_characteristics_updated` 的「沿用/优选 + `set_characteristics`」分支，
  在连接期造成多余重订阅与日志（见 `bluetooth_tool_widget.py:1675-1694`）。
- R3.2 MTU 标签文案抽成单一实现（`_on_connected` 与 `_on_limits_updated` 共用）：
  未协商时明确写出「ATT 默认值 23（协商结果未回）」并给出单包上限。
- R3.3 「特征码…」对话框若正打开，收到新上限后**刷新列表并保留勾选与当前行**；
  未打开时只更新缓存（下次打开即最新）。
- R3.4 收到 `mtu_updated` **不得**改写用户已选特征码、不得重复 `set_characteristics`。

### R4 测试

- R4.1 `test/test_bluetooth_core.py`：`mtu_is_unnegotiated` 边界（0/None/非法/23/24/247）+ 常量关系（`0 < INTERVAL < TIMEOUT`）。
- R4.2 `test/test_bluetooth_worker.py`（假 bleak，注入「值会变」的假特征码/假 client）：
  - 迟到协商：连接时 23/20 → 轮询后 `mtu_size() == 247`、`max_write == 244`、发出 `mtu_updated`、日志含「协商更新」；
  - 只支持默认值：轮询到超时后 `mtu_size()` 不变、**不发** `mtu_updated`、只一行提示；
  - 发送前重读：连接时 20，发送前实时值改为 244 ⇒ 该次发送按 244 分包（25 字节 = **1** 包），并发出 `mtu_updated`；
  - 断开打断轮询：不抛异常；
  - **反例自检**：删掉轮询 / 删掉发送前刷新 ⇒ 上述用例必须变红。
- R4.3 `test/test_bluetooth_widget.py`：`mtu_updated` 更新 MTU 标签与 `_chars` 缓存，
  且**不**重订阅、不改写特征码记忆。
- R4.4 四份蓝牙测试 + `python release_check.py --with-gui` 必须 FAIL=0。

## Acceptance Criteria

- A1 连接一台「协商结果迟到」的设备：**无需重连**，3 秒内界面 MTU 行与「特征码…」上限变为协商后的值，日志有一行「MTU 协商更新」。
- A2 对端只支持 ATT 默认值时：行为与改动前一致（MTU 23 / 单包 20），只多一行超时说明。
- A3 发送路径的证据：把实时上限从 20 改成 244 后，**同一连接**的下一次发送按 244 分包（日志「按单包上限 244 字节分为 1 包」）。
- A4 连接过程不被轮询阻塞（`connected` 信号在轮询之前发出；界面连接后立即可用）。
- A5 不引入多余重订阅：收到 `mtu_updated` 后 `set_characteristics` 调用次数不增加。

## 非目标

- 不实现「主动请求更大 MTU」（Windows 上应用层无权请求，只能读）。
- 不改写分包上限 `DEFAULT_MAX_CHUNK = 200`（发送尺寸仍夹到 200；本次只让**上限读数**实时）。
- 不改 Web 侧（Reflex 无蓝牙）。
- 不改 BLE 重组/切帧语义（仍是静默超时切帧）。
