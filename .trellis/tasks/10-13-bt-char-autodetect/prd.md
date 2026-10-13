# 蓝牙工具：特征码自动优选 + 一键探测 + 按设备记忆

## Goal

让「连上设备就能收发 HEX 报文」成为默认路径：**不再让用户在几十个特征码里挑**。

- 连接后**按属性 + 厂商族谱自动优选**出「发送 / 接收」通道（**不写任何数据，零副作用**）；
- 需要时点**一键「自动探测」**：对候选依次「订阅 → 写探测帧 → 等回包」，命中即锁定并给出结论与依据；
- 选择**按设备地址记忆**，同一模块下次连接直接沿用；
- 手工对话框保留为兜底，但把优选结果**预选并置顶**。

## 现状与痛点（证据见 `research/char-select-facts.md`）

| 事实 | 影响 |
|---|---|
| `_auto_pick()` 取设备枚举顺序里**第一个** `can_recv` / 第一个 `can_send` | 常落在标准 GATT（`2A00` 设备名 / `2A19` 电量）、OTA/DFU、配置特征码 → 用户仍要手动挑 |
| 选择**全局存一份**（`settings.recv_uuids/send_uuids`），不区分设备 | 换模块就得重挑 |
| 无任何探测/验证 | 选错只能现场试错 |
| 对话框列出**全部**特征码（不可用项置灰） | 「一堆特征码」的来源；且 AGENTS §8 陷阱 71：QSS 主题下置灰不可见 |

## Requirements

### R1 打分优选（纯逻辑，零副作用）

- R1.1 新增到 `bluetooth_core.py`（**纯逻辑：禁止 import Qt / bleak**）：`rank_characteristics(chars) -> List[dict]`
  （稳定排序，同分保持原顺序）与 `pick_auto(chars) -> (recv_uuids, send_uuids, reason)`。
- R1.2 打分要素（可叠加，权重集中在一处常量表，便于调参）：
  ① 同一条特征码**既 `can_send` 又 `can_recv`**（透传回环）最高；
  ② 厂商透传族谱优先：`6E400002/6E400003`（Nordic UART TX/RX）、`FFE1`（HM-10/CC2540）、`FFE5/FFE9`、
  `FFF0~FFF2`、`FFF6`、`FF01/FF02`、`AE01/AE02`、`FF10/FF11`；
  ③ 名称/描述/服务名含 `tx/rx/uart/write/notify/serial/串口/透传/transparent`；
  ④ **降权**标准 GATT（`2A00~2AFF` 特征码、`1800/1801/180A/180F` 服务）与 OTA/DFU（`FE59`、`1530`、`FFC0/FFC1`）。
- R1.3 同一服务内配对优先：写特征码与通知特征码同属一个 service 时加分（透传模块几乎都这样）。
- R1.4 **首选必须来自打分**：`_on_characteristics_updated` 不再用「第一个」，改为 `pick_auto`；
  日志给出依据摘要（例：`自动优选：发送 → 0xFFE1、接收 → 0xFFE1（厂商透传族谱 + 该特征码同时可写可通知）`）。
- R1.5 候选为空（无 `can_send` 或无 `can_recv`）时给出可读提示，不静默（沿用既有 warn 文案）。

### R2 一键「自动探测」

- R2.1 新增纯逻辑探测会话 `ProbeSession`（`bluetooth_core.py`）：输入候选列表 + 探测载荷 + 单项超时，
  逐项推进；对外暴露步骤意图（`select_recv` / `write` / `wait`），由界面用 QTimer 驱动；
  事件入口 `on_subscribed(ok: bool)` / `on_frame(nbytes: int)` / `on_timeout()`；`result()` 给出
  `success / attempts[] / winner`。**全败不抛异常**。
- R2.2 候选 = `rank_characteristics` 结果里取前 `PROBE_MAX_CANDIDATES = 6` 个「可发送」通道
  （各自配对同服务/同码的接收通道；无接收通道的候选仍可试写，但会明确标注「无接收通道，只验证写入」）。
- R2.3 探测载荷解析（纯逻辑）`resolve_probe_payload(edit_text, mode, default_hex)`：
  **优先**用发送框内容（按当前格式解析，HEX 写错 → 返回错误、**不写**）；为空则用配置的默认探测帧；
  返回值带 `source ∈ {"edit", "default"}`，界面据此在日志里注明「使用默认探测帧」。
- R2.4 探测时序：选中候选的接收通道 → **等订阅完成** → 写载荷 → 等回包（默认 `PROBE_TIMEOUT_MS = 800`，可配 200~5000）。
  订阅完成信号是**新增**的 `bluetooth_worker.subscribe_finished(list, bool)`（既有信号不改语义）。
- R2.5 结果落盘 + 记忆：成功 → 应用到界面/worker，并按设备地址记忆（`source="probe"`）；
  全败 → 保留原选择、逐候选给出失败原因（订阅失败 / 写入失败 / 超时无回包），提示可用「特征码…」手工选。
- R2.6 探测期间按钮禁用并给进度（`探测中 2/6…`），可中途停止；**不阻塞 GUI**（QTimer 分步，不 sleep）。

### R3 按设备地址记忆

- R3.1 新增设置键 `char_map`：`{"<address>": {"recv": [...], "send": [...], "source": "auto|probe|manual", "ts": 0}}`；
  `merge_settings` 对其做宽容校验（非 dict / 非法 uuid 列表一律丢弃该条，坏条目不影响其它条目）。
- R3.2 连接成功后：若 `char_map` 命中该地址 → 直接沿用（`source="recall"`，日志注明「沿用上次」）；
  否则按 R1 自动优选。
- R3.3 手工选择 / 探测成功 / 自动优选三处都写入 `char_map`（含 `source` 与时间戳），并保留全局
  `recv_uuids/send_uuids` 作为「无匹配设备时的上次值」（向后兼容旧配置）。
- R3.4 上限：`char_map` 最多保留 `CHAR_MAP_MAX = 20` 条（超出按 `ts` 最旧淘汰），防配置无限增长。

### R4 提速的界面改动（最小侵入）

- R4.1 状态行新增「发送 → `0xFFE1` ｜ 接收 → `0xFFE1`」（短 UUID；未选则显示「未选」）。
- R4.2 新增按钮「自动探测」（挨着「特征码…」），tooltip 明说：**会真的写入一帧**（默认发送框内容），
  以及「发送框为空时使用默认探测帧」。
- R4.3 `CharacteristicSelectDialog`：**预选**优选结果、把优选条目置顶（`rank_characteristics` 顺序），
  顶部加一行「推荐：发送 …｜接收 …（依据 …）」；不可用项除置灰外**必须**有文字标注（陷阱 71）。
- R4.4 探测/优选/沿用的结论都走既有 `_log()`（弹框必留日志，陷阱 69），且**不逐帧刷屏**。

### R5 不回归

- R5.1 既有四份蓝牙测试全绿；不改 `send_data` / 分包 / 重组 / 虚拟串口透传语义。
- R5.2 `bluetooth_core` 仍**零 Qt / 零 bleak 依赖**（纯逻辑可脱硬件单测）。
- R5.3 旧配置（无 `char_map` / `probe_frame` 键）行为与旧版一致（仅多出更好的自动优选）。
- R5.4 不新增 pip 依赖；`main_gui.py` / `reflex_web/` 不改（widget 仍不 import main_gui）。

### R6 测试

- R6.1 `test/test_bluetooth_core.py` 扩段：打分排序（族谱/双属性/同服务/标准 GATT 降权/稳定性）、
  `pick_auto` 边界（无候选/只有写/只有通知）、`char_map` 合并与淘汰、探测载荷解析（输入框优先/空回落/HEX 写错拒绝）、
  `ProbeSession` 全流程（命中即停、单项超时推进、全败原因、订阅失败）、`CHAR_MAP_MAX` 淘汰顺序。
- R6.2 `test/test_bluetooth_worker.py` 扩段：`subscribe_finished` 在成功/失败两条路径都发出且带 uuid 列表。
- R6.3 `test/test_bluetooth_widget.py` 扩段：**连上后自动选中的是打分最优**（构造一个「第一个可写的是
  `2A19` 电量、真正的透传是 `FFE1`」的假特征码列表 → 必须选 `FFE1`，反例：旧逻辑会选 `2A19`）、
  按设备记忆沿用、探测成功锁定并落盘、探测全败保留原选择且逐条给原因、状态行摘要、
  对话框预选/置顶与「不可用」文字标注、探测期间按钮禁用与进度。
- R6.4 **变异反证 ≥3 条**：① 打分恒 0（退回枚举顺序）→ 自动优选用例变红；② 探测不等订阅就写 → 时序用例变红；
  ③ 记忆不按地址（写全局）→ 沿用用例变红。每条实测变红后逐字节还原。
- R6.5 `python release_check.py --with-gui` → FAIL=0（四份蓝牙测试已在 `CORE_TESTS`）。

### R7 文档与版本

- R7.1 `main_gui.py:CHANGELOG` 头部新增条目；`APP_VERSION 1.23.78 → 1.23.79`；`release_check.py --sync-iss`；README 徽章/版本行/功能表/更新记录。
- R7.2 `AGENTS.md`：§8 陷阱 69 补「特征码优选/探测/按设备记忆」三条契约；§3 模块表 `bluetooth_*.py` 描述补一句；§10 追加 1.23.79。
- R7.3 `.trellis/spec`：新增「蓝牙特征码优选与探测」契约段落（打分单一来源、探测必须等订阅、记忆键结构）。

## Acceptance Criteria

- [ ] AC1 构造假特征码列表（含 `2A00` 设备名、`2A19` 电量（可写）、`FFE1`（可写可通知））→
      自动优选出 **`FFE1`**（发送与接收都是 `FFE1`），日志给出依据；**旧逻辑会选 `2A19`**（反例自检）。
- [ ] AC2 同一设备第二次连接：直接沿用 `char_map` 里的记录（日志注明「沿用上次」），
      不再重新打分；换地址（`char_map` 未命中）→ 走优选。
- [ ] AC3 探测成功路径：候选 A 订阅失败 → 继续；候选 B 订阅成功但无回包（超时）→ 继续；
      候选 C 订阅成功且收到回包 → 锁定 C，`char_map[address].source == "probe"`，日志含「收到 N 字节」。
- [ ] AC4 探测全败：保留原选择、逐候选给出可读原因、提示手工选择；界面按钮恢复可用。
- [ ] AC5 探测载荷：发送框有内容时用它（HEX 写错 → 拒绝且不写）；发送框为空时用默认帧并在日志注明来源。
- [ ] AC6 状态行显示「发送 → 0xFFE1 ｜ 接收 → 0xFFE1」；未选时显示「未选」。
- [ ] AC7 旧配置（无新键）载入行为与旧版一致；`char_map` 坏条目被丢弃且不影响其它条目；超 20 条按 `ts` 淘汰。
- [ ] AC8 四份蓝牙测试 + 新增用例全绿；3 条变异反证实测变红后还原。
- [ ] AC9 `python release_check.py --with-gui` → FAIL=0；`.iss` / README 徽章 = `APP_VERSION`。
- [ ] AC10 文档同步：CHANGELOG / AGENTS（§3、§8 陷阱 69、§10）/ README / spec。

## Scope 边界（明确不做）

- **不**改 BLE 收发链路（`send_data` 分包、`BleReassembler` 切帧、虚拟串口透传）。
- **不**做「连接后自动全量探测」（用户选定：默认零副作用，探测由按钮触发）。
- **不**删手工特征码对话框（兜底能力保留，只加预选/置顶/可读标注）。
- **不**改 `main_gui.py` 的接线方式（页面仍由 `_ensure_bluetooth_tool_tab` 懒加载 + 注入三件套）。
- **不**引入 pip 依赖（不做自定义 GATT 探测库）。

## 存疑 / 实现中确认

- D1 探测对**有副作用**的设备（写 `AT` 会改模式）：默认探测帧用发送框内容；发送框为空时用可配置默认帧
  （默认 `AT`）并在日志明确「使用默认探测帧」，把选择权留给用户（tooltip 已写明会真写）。
- D2 某些模块的透传特征码要求**先写使能**（如写 `01` 到某个 CCCD 类特征码）才能收包：本次不猜这种私有协议，
  探测失败时日志给出「写入成功但无回包」的结论，并提示可用手工选择或先发自己的使能帧。
- D3 `subscribe_finished` 的时机：以 `_subscribe_coro` 返回为界（含 `False` 失败路径）。
