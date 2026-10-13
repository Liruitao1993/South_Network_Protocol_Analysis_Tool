# 证据固化：蓝牙特征码「自动优选 + 一键探测 + 按设备记忆」

> 用户诉求（2026-10-13）：「蓝牙工具特征码，可否提前先进行测试…我们设计的软件主要还是采用 HEX 格式
> 进行报文的收发，给我一堆的特征码选择的话用户体验不是很好，如何让用户更快的实现收发？」
> 已确认口径：**① 连接后按属性 + 厂商族谱自动优选（不写任何数据，零副作用）；② 需要验证时点「自动探测」
> 按钮（真写帧看回包）；③ 探测帧优先取发送框已输入报文，为空则用可配置默认帧（默认 AT）**。

## 1. 现状（代码事实）

| 位置 | 现状 | 问题 |
|---|---|---|
| `bluetooth_tool_widget._auto_pick()` | 取设备枚举顺序里**第一个** `can_recv` / 第一个 `can_send` | 常落在标准 GATT（设备名 `2A00`、电量 `2A19`）、OTA/DFU、配置特征码 → 用户仍要手动挑 |
| `bluetooth_tool_widget._on_characteristics_updated()` | 未选过时才自动选，并 `_apply_characteristics(announce=True)` | 同上（选错就白选） |
| 选择结果落盘 | `settings["recv_uuids"] / ["send_uuids"]`（**全局一份**，不区分设备） | 换模块就得重挑 |
| `CharacteristicSelectDialog` | 左右两列列出**全部**特征码（不可用项置灰） | 即用户说的「一堆特征码」；AGENTS §8 陷阱 71 已知：QSS 主题下置灰不变灰 |
| 探测 | **无**。选完即订阅，从不验证「写进去有没有回包」 | 选错只能靠现场试错 |
| `bluetooth_worker._collect_characteristics()` | 每个特征码给出 `uuid / short / service_uuid / service_short / properties / description / can_recv / can_send / max_write` | **信息已足够**做打分优选，不必改采集 |
| `bluetooth_worker._subscribe_coro()` | 内部 async 订阅；**成功/失败都不发信号** | 探测必须知道「订阅已就绪」才能写，否则首个回包会丢 → 需补一个完成信号 |

## 2. 发送侧既有能力（探测帧复用）

- 发送框 `edit_send`（占位提示 `HEX（68 12 00 41 16）或 ASCII 文本（AT+INFO?）`）+ 格式下拉 `combo_send_format`
  （`SEND_FORMATS`：自动（HEX 优先）/ HEX 字节 / ASCII 文本，取值与 `core.parse_plain_text(text, mode)` 的 `mode` 一一对应）。
- `_payload_from_edit()` → `(payload|None, error)`；**HEX 写错绝不静默按文本发**（陷阱 69）。
- `_send_payload(payload)` → `worker.send_data()`（按 MTU 分包 + 包间延迟）。
- 收包：`worker.frame_received(uuid, frame)`（重组后的整帧）→ 界面 `_on_frame_received`。

## 3. 配置与持久化（`bluetooth_core.py`）

- `SETTINGS_NAME = "bluetooth_tool_config.json"`、`SETTINGS_VERSION = 1`、`DEFAULT_SETTINGS`、
  `merge_settings(raw)`（宽容合并 + 夹紧）、`load_settings/save_settings`（原子写）。
- `short_uuid()`：标准 SIG UUID → `0xFFF1`，自定义 128bit → 原样（界面短显示用）。

## 4. 本次要新增的能力（验收基线）

1. **打分优选（纯逻辑，`bluetooth_core.py`）**：按「同一条特征码同时可写可通知（透传回环）」>
   「厂商透传族谱（`6E400002/3` Nordic UART、`FFE1`（HM-10）、`FFE5/FFE9`、`FFF0~FFF2`、`FF01/FF02`、
   `AE01/AE02`、`FF10/FF11` 等）」>「名称/描述含 `tx/rx/uart/write/notify/serial/串口/透传`」排序；
   **降权**标准 GATT（`2A00~2AFF`、`180x` 服务）与 OTA/DFU（`FE59`、`1530`、`FFC0`…）。
   **禁止**再按枚举顺序取「第一个」。
2. **一键探测**：对候选（默认前 N=6）依次「选接收→等订阅就绪→写探测帧→等回包（默认 800 ms）」，
   命中即锁定并报告「写=X 收=Y（收到 N 字节）」；逐个失败给**可读原因**（订阅失败/写入失败/超时无回包）；
   全败 → 报告并保留原选择（不静默）。
3. **按设备地址记忆**：`settings["char_map"][address] = {recv, send, source}`（`auto|probe|manual|recall`），
   下次连同一地址直接沿用并注明「沿用上次」；缺省回落新的优选逻辑。
4. **UI 提速**：状态行显示「发送→0xFFE1 ｜ 接收→0xFFE1」；「特征码…」对话框把优选结果**预选并置顶**，
   顶部给出一条「推荐：…（依据 …）」；手工选择仍是兜底（用户明确说「不要一堆选择」，但不删）。

## 5. 受影响测试（既有，改动后必须全绿）

- `test/test_bluetooth_core.py`（68 项，纯逻辑）、`test/test_bluetooth_worker.py`（74 项，注入假 bleak）、
  `test/test_bluetooth_widget.py`（146 项，offscreen + 假 worker/假串口）、
  `test/test_bluetooth_tab_wiring.py`（36 项，真实 `MainWindow` 接线）——四份都在 `release_check.py:CORE_TESTS`。
- 相关陷阱：§8 陷阱 69（蓝牙九条契约：纯逻辑禁 Qt/bleak、widget 不 import main_gui、HEX 写错不静默降级、
  未知 RSSI 按未知、分包按 MTU、弹框必留日志、`app_paths.data_path` **属性访问**、`_save_timer` 必须先建）、
  陷阱 71（置灰在 QSS 下不可见 → 对话框的「不可用」提示不能只靠置灰）。
