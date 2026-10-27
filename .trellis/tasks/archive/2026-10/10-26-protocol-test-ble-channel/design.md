# 设计：协议测试页双通道（串口 / 蓝牙）

> PRD 见 `prd.md`。核心事实：**升级页 1.23.85 已跑通同一套蓝牙通道口径**
> （`_BleSendPort` + provider 注入 + `notification_received` + `single_write_limit`），
> 本任务把「通道选择 / 发送 / RX 分流 / 状态文案」抽成共用控制器，供 698 与 645 两页复用，
> **不重新发明**。蓝牙连接生命周期仍完全归「蓝牙工具」页。

## 1. 文件与边界

| 文件 | 角色 | 动作 |
|---|---|---|
| `channel_link.py` | 共用通道控制器（Qt，无协议细节） | **新增** |
| `dlt698_test_widget.py` | 698 协议测试页 | 顶部加通道下拉；收发改走控制器 |
| `dlt645_test_widget.py` | 645 协议测试页 | 同上 |
| `main_gui.py` | 接线 | 两个 ensure 方法加 `set_bluetooth_provider(self._upgrade_bluetooth_source)` |
| `test/test_channel_link.py` | 控制器单测 | **新增** |
| `test/test_dlt698_testbench.py` / `test/test_dlt645_testbench.py` | 页面双通道 | 各加一段 |
| 两个 `*_test_tab_wiring.py` | 注入断言 | 各加 1 项 |

不改：`bluetooth_worker.py`、蓝牙工具页、升级页、协议 core、Web。

## 2. `channel_link.py` 契约

```python
CHANNELS = (("串口", "serial"), ("蓝牙", "bluetooth"))
SERIAL, BLUETOOTH = "serial", "bluetooth"
DEFAULT_CHANNEL = SERIAL

def normalize_channel(value) -> str          # 非法 → DEFAULT

class BleSendPort:
    """与 SerialWorker 同构的发送口（只用 is_open / write_raw）。"""
    def is_open(self) -> bool: return bool(self._worker and self._worker.is_connected())
    def write_raw(self, data) -> bool: return bool(self._worker.send_data(bytes(data), single_write=True))

class ChannelController(QObject):
    rx = Signal(bytes)                 # 当前通道收到的字节（另一通道直接丢弃）
    state_changed = Signal(str, bool)  # (可读状态, 当前通道是否就绪)
    channel_changed = Signal(str)      # 切换后（页面据此清 RX 缓冲）
    error = Signal(str)                # 写失败/超限/串口异常（页面记日志）

    channel: str                       # 只读属性
    def set_channel(self, value: str) -> None
    def set_serial_worker(self, worker) -> None
    def set_bluetooth_provider(self, provider) -> None
    def worker_ref(self)               # 蓝牙 worker（经 provider 取，异常→None）
    def rebind_bluetooth(self) -> None # 重新解析 provider 并换绑信号
    def ready(self) -> (bool, str)     # 当前通道是否可用 + 原因
    def send(self, frame: bytes) -> (bool, str)   # 串口 write_raw / 蓝牙单写（超限预检）
    def state_text(self) -> str
    def cleanup(self) -> None          # 断全部订阅（幂等，不断开连接）
```

- **RX 分流**：串口 `raw_data_received`、蓝牙 `notification_received` 都进控制器，按 `channel` 过滤后
  `rx.emit`。切通道发 `channel_changed` → 页面清分帧缓冲（半帧绝不跨通道拼接）。
- **超限在控制器里预检**：`len(frame) > worker.single_write_limit()` ⇒
  `(False, f"蓝牙一次 ATT 写上限 {limit} 字节，该帧 {len(frame)} 字节（协议帧必须整帧一次写）")`，
  **不调用 worker**（worker 自带的文案是「请调小每包字节数」，对测试页是误导）。
- **状态文案**（与升级页一致）：
  - 串口：`串口通道：已连接 / 未连接（端口/波特率在顶部「串口配置」设置）`
  - 蓝牙：`蓝牙通道：未连接（请先在「蓝牙工具」页扫描并连接设备）` /
    `蓝牙通道：<设备名>（MTU N，一次 ATT 写上限 M 字节）`
  - 订阅 `mtu_updated` 重算（协商完成后文案/上限会变）。
- **延迟出现**：蓝牙页懒加载 ⇒ 先选蓝牙、后连接是常态；`set_bluetooth_provider` 立即绑定一次，
  `rebind_bluetooth()` 在页面 `showEvent` 与 `set_channel` 时再试。

## 3. 页面改造（两页同构）

1. 顶部新增一行「发送通道：[串口 ▾] <状态文本…>」：
   - 698：放在原 row1 与 row2 之间（新增 `row_channel`，状态 `lbl_state` 从 row2 移过来）；
   - 645：原本两行网格改三行（通道+状态独占一行），避免与「超时/循环/发送/停止」抢宽度。
2. `set_serial_worker(worker)`：仍保存 `self._serial_worker`（既有断言依赖），内部转交控制器；
   删除页内对 `raw_data_received` 的直连（否则 RX 双份）。
3. 就绪判据：`self._channel_ready()` = `controller.ready()`；未就绪的弹框文案用返回的**原因**。
4. 发送：`self._write(frame)` → `controller.send(frame)`；失败原因写日志（645 还要写信息表行）。
5. 收到字节：`controller.rx` → `self._on_rx_data`（原 `_on_serial_raw_data` 改名，
   保留旧名别名防外部引用）；分帧逻辑不变。
6. 落盘：`channel` 键（默认 `serial`）；加载时 `combo_channel.setCurrentIndex(...)` →
   触发 `set_channel`（顺序：先建控制器与信号，再设下拉）。
7. `showEvent`：`controller.rebind_bluetooth()`（只重绑，不改通道）。
8. `cleanup()`：`controller.cleanup()`（并保持 `self._serial_worker = None`）。

## 4. 测试计划

### `test/test_channel_link.py`（新增，`GUI_TESTS`）
- 通道归一化 / 默认值；`state_text` 四态（串口连/断、蓝牙未连/已连含 MTU+上限）。
- `send`：串口成功/异常；蓝牙成功（断言 `single_write=True`）；蓝牙超限（**worker 未被调用** + 可读原因）；
  未连接/未注入 provider 的 `ready()` 原因。
- RX 分流：串口字节在蓝牙通道被丢弃；蓝牙通知在串口通道被丢弃；切通道后 `rx` 只来自新通道。
- provider 延迟出现：先选蓝牙（未连接）→ 注入 provider → `rebind_bluetooth()` 后可用；
  `mtu_updated` 触发状态刷新。
- `cleanup` 幂等：断开后 emit 两路信号都不再 `rx`；蓝牙 `is_connected()` 仍为 True（不断开连接）。

### 页面测试（追加段）
- 645/698 各：切蓝牙 → 发送走假蓝牙 worker 的 `send_data`（single_write True）；
  蓝牙通知解出帧并判定；串口字节在蓝牙通道被忽略；反向同理；超限帧不发送 + 信息表失败；
  `channel` 落盘往返；`cleanup` 后 `_bt_worker` 置空且蓝牙仍连接。
- wiring：两页 `set_bluetooth_provider` 注入可调用（`tab._channel.worker_ref` 或 provider 属性）。

## 5. 风险与边界

- **不改升级页**（它有自己的块长逻辑与文案）；后续若要收口，可换成 `ChannelController` + `BleSendPort`。
- **BLE 不分包**：协议帧必须整帧一次写；MTU 23（上限 20）下多数 698 帧会超限 —— 此时给明确原因，
  让用户到蓝牙页重连（Windows 会在连接后异步协商，通常 247/512）。**不设假上限、不静默分包**。
- 页面 `cleanup` 不得断开蓝牙；`ChannelController` 只断信号。
- 兼容：`_serial_worker` 属性保留；`_on_serial_raw_data` 保留别名；既有 279/89 项测试必须全绿。
