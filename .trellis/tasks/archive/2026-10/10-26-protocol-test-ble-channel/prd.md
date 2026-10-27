# 698 / 645 协议测试页：新增串口 / 蓝牙发送通道选择

## Goal

「协议测试」两页（698 `dlt698_test_widget`、645 `dlt645_test_widget`）现在只能走**串口**。
现场越来越多设备只提供 BLE（手机/平板调试、模块出厂测试），而「蓝牙工具」页已经能连设备、
逐特征码收发；`光伏升级` 页 1.23.85 起已支持「串口 / 蓝牙」双通道。

本次把同一套通道能力接到两个协议测试页：

- 顶部新增 **发送通道：串口 / 蓝牙** 下拉 + 通道状态行（连接态 / MTU / 一次写上限）；
- 蓝牙通道**复用「蓝牙工具」页已建立的连接**（本页不建、不断），**整帧一次 ATT 写**，
  页内自己做 698 / 645 分帧；
- 帧长度超过一次 ATT 写上限时**明确报错、不发送**（不静默分包 —— 分包会让设备收到被切断的帧）；
- 通道选择落盘；切换通道清空 RX 缓冲，**两个通道的字节绝不混用**。

## 现状证据（实现必须与此一致）

- 参考实现：`dlt698_upgrade_widget.py` —— `CHANNELS = (("串口","serial"),("蓝牙","bluetooth"))`、
  `_BleSendPort`（`write_raw` → `worker.send_data(frame, single_write=True)`）、
  `set_bluetooth_provider(provider)` + `_bind_bluetooth_worker()`（订阅 `notification_received` /
  `connection_changed` / `mtu_updated` / `error_occurred`）、`_refresh_channel_state()` 文案、
  `showEvent` 重新对齐绑定、`cleanup` 断绑定。**本任务照这套口径做，不重新发明。**
- 主窗口已有注入点 `MainWindow._upgrade_bluetooth_source()`（取「蓝牙工具」页当前 worker，
  懒加载页可能还没建 ⇒ 返回 None），升级页经 `set_bluetooth_provider(...)` 使用。
- `BluetoothWorker`：`is_connected()`、`mtu_size()`、`single_write_limit()`、
  `send_data(data, single_write=True)`（超过上限 ⇒ `error_occurred` + `False`，**不分包**）、
  `notification_received = Signal(str, bytes)`（单个 ATT 通知，原样）、
  `frame_received = Signal(str, bytes)`（worker 静默超时重组后的整帧）。
- 两个测试页现状：`set_serial_worker` 只订阅 `raw_data_received / connection_changed / error_occurred`；
  `_worker()` 判串口是否打开；`_write(frame)` 走 `worker.write_raw`；`_on_serial_raw_data` 里做协议分帧
  （698：`frame_deframe("dlt698_45")` + 末字节 16H；645：`frame_deframe("dlt645")` + FE 重同步）。
  顶部状态标签 `lbl_state`；落盘配置 `dlt698_testbench.json` / `dlt645_testbench.json`。
- 两页各自的既有测试：`test/test_dlt698_testbench.py`（279 项）、`test/test_dlt645_testbench.py`（89 项），
  都用假串口 worker 注入 `raw_data_received`；接线测试 `*_test_tab_wiring.py`。

## Requirements

### R1 共用通道控制器（新 `channel_link.py`，Qt 但无协议细节）

- R1.1 常量/工具：`CHANNELS`、`DEFAULT_CHANNEL`、`normalize_channel()`、`BleSendPort`
  （与升级页同一语义：`is_open`→`is_connected`、`write_raw`→`send_data(single_write=True)`）。
- R1.2 `ChannelController(QObject)`：
  - 信号：`rx = Signal(bytes)`（**当前通道**的原始字节）、`state_changed = Signal(str, bool)`（文案, 是否就绪）、
    `channel_changed = Signal(str)`、`error = Signal(str)`；
  - `set_channel(value)` / `channel` 属性；`set_serial_worker(worker)`；
    `set_bluetooth_provider(provider)` / `rebind_bluetooth()` / `worker_ref()`；
  - `ready() -> (bool, str)`：当前通道是否可用 + 原因文案（串口未打开 / 蓝牙未连接 / 未注入 provider）；
  - `send(frame) -> (bool, str)`：串口 `write_raw`；蓝牙先判 `single_write_limit()`，
    **帧超上限直接返回可读错误**（不调用 worker，避免升级页文案串台），否则 `send_data(single_write=True)`；
  - `cleanup()`：停订阅（串口 + 蓝牙），幂等。
- R1.3 RX 分流：串口 `raw_data_received` 与蓝牙 `notification_received` 都进控制器，
  **按当前通道过滤后**才 `rx.emit`（另一通道的字节直接丢弃）。切通道时控制器发 `channel_changed`，
  页面据此清空自己的分帧缓冲。
- R1.4 状态文案与升级页同口径：串口「已连接/未连接（端口在顶部串口配置设置）」；
  蓝牙「未连接（请先在「蓝牙工具」页扫描并连接设备）」/「设备名（MTU N，一次 ATT 写上限 M 字节）」。
  蓝牙连接中 MTU/特征码变化要重算并刷新文案（订阅 `mtu_updated`）。

### R2 698 测试页改造

- R2.1 顶部加「发送通道：串口/蓝牙」下拉（`combo_channel`）+ 复用 `lbl_state` 显示通道状态。
- R2.2 `set_serial_worker` → 转交控制器；删除页内对 `raw_data_received` 的直连（避免双份 RX）。
- R2.3 `_worker()` 判据改为 `controller.ready()`；`_write()` 走 `controller.send()` 并把错误写日志/信息表。
- R2.4 固定动作（读/写地址、读/写时间、建立连接、发送）在蓝牙通道下同样可用；
  未就绪时弹框给出**当前通道**的原因（不是固定的「串口未连接」文案）。
- R2.5 `_on_serial_raw_data` 改名为通道无关的 RX 入口（保留旧名做别名，防测试/外部引用断裂），
  仅由 `controller.rx` 驱动；切通道清 `_rx_buf`。
- R2.6 落盘 `channel`（默认 serial）；`showEvent` 时 `controller.rebind_bluetooth()`（蓝牙页可能后连）；
  `cleanup()` 调 `controller.cleanup()`。

### R3 645 测试页改造

- R3.1~R3.6 与 R2 同构（读地址 / 写地址 / 广播校时 / 发送 / 循环发送都走控制器；
  超时与分帧逻辑不变；蓝牙超限写进信息表「失败」并继续下一条）。

### R4 接线

- R4.1 `main_gui._ensure_test_tab` / `_ensure_dlt645_test_tab` 增加
  `tab.set_bluetooth_provider(self._upgrade_bluetooth_source)`（复用同一注入点，不重命名现有方法）。
- R4.2 两页仍**不建、不断**蓝牙连接；`cleanup()` 只解绑。

### R5 测试

- R5.1 新 `test/test_channel_link.py`：假串口 + 假蓝牙 worker；通道切换、串/蓝牙 RX 只走当前通道、
  `send` 三态（串口 / 蓝牙成功 / 蓝牙超限带可读原因）、`ready()` 文案、状态文案（含 MTU/上限）、
  provider 延迟出现（先选蓝牙后连接）、`cleanup` 幂等且不断开蓝牙。
- R5.2 `test_dlt698_testbench.py` / `test_dlt645_testbench.py` 各加一段（假蓝牙 worker）：
  切通道 → 帧走 `send_data(single_write=True)`、蓝牙通知能解出帧、串口字节在蓝牙通道被忽略、
  反向同理、超限帧不发送且信息表记失败、通道落盘往返、`cleanup` 解绑。
- R5.3 两个 `*_test_tab_wiring.py`：断言两页都拿到 `set_bluetooth_provider` 注入（provider 可调用）。
- R5.4 三份新/改测试登记 `release_check.py`（`test_channel_link.py` 进 `CORE_TESTS` 或 `GUI_TESTS`，
  按是否构造 widget 决定）。

## Acceptance Criteria

- A1 两页顶部都有「发送通道」下拉；默认串口；选蓝牙且未连设备时状态行给
  「蓝牙未连接（请先在「蓝牙工具」页扫描并连接设备）」，点发送给同文案提示（不再说「串口未连接」）。
- A2 蓝牙工具页连上设备后，协议测试页选蓝牙 → 发送一条 645 读 DI / 698 读属性 →
  帧通过 `send_data(single_write=True)` 一次写出（假 worker 断言），设备回包（`notification_received`）
  能被页内分帧并判定成功。
- A3 构造一个超过 `single_write_limit()` 的帧 → **不调用 worker**、日志/信息表给出
  「蓝牙一次 ATT 写上限 M 字节，该帧 N 字节」的可读原因。
- A4 通道隔离：蓝牙通道下串口 `raw_data_received` 的字节不参与分帧/判定；串口通道下蓝牙通知同样被忽略。
- A5 切通道后 RX 缓冲清空（半帧不会跨通道拼接）。
- A6 通道选择落盘：重开页面仍是上次选择。
- A7 两页 `cleanup()` 后不再收帧、**蓝牙连接仍保持**（不调 disconnect）、`bluetooth_worker` 引用清空。
- A8 `python release_check.py --with-gui` → PASS 且 FAIL=0（既有环境红除外）。

## 非目标

- 不改 `BluetoothWorker` / 蓝牙工具页 / 升级页行为（升级页可后续换共用控件，本任务不动它）。
- 不做 BLE 分包发送（协议帧必须整帧一次写；超限就报错）。
- 不做「让测试页自己发起扫描/连接」（连接生命周期仍归蓝牙工具页）。
- 不改 Web 版；不改协议分帧/组帧/判定逻辑。
