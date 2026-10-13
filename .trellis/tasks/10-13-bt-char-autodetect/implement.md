# 执行计划：蓝牙特征码自动优选 + 一键探测 + 按设备记忆

> 目标版本 `APP_VERSION 1.23.78 → 1.23.79`。
> 铁律：批量/GUI 测试经 pwsh（AGENTS §8 陷阱 62），命令带 `PYTHONIOENCODING=utf-8`；
> 提交只挑本任务文件（禁止 `git add -A`）；`bluetooth_core` 保持**零 Qt / 零 bleak**。

## 阶段 0 · 证据固化（已完成）

- [x] `research/char-select-facts.md`：现状（`_auto_pick` 取「第一个」、全局存储、无探测、对话框列全部）、
      发送侧可复用能力（`edit_send` / `parse_plain_text` / `_payload_from_edit` / `_send_payload`）、
      配置 API（`DEFAULT_SETTINGS` / `merge_settings` / `load_settings` / `save_settings`）、
      既有四份蓝牙测试与相关陷阱（69/71）。

## 阶段 1 · `bluetooth_core.py`（纯逻辑）

- [ ] 常量：`CHAR_SCORE_*` 权重表、`PASSTHROUGH_UUIDS`、`PASSTHROUGH_HINTS`、`STANDARD_GATT_*`、`OTA_DFU_*`、
      `PROBE_MAX_CANDIDATES = 6`、`PROBE_TIMEOUT_MS = 800`、`PROBE_TIMEOUT_RANGE = (200, 5000)`、`CHAR_MAP_MAX = 20`。
- [ ] `short_key(uuid)`（归一化为 4 位短码或 `None`，供族谱/标准 GATT 判定，大小写与 128bit 形式都覆盖）。
- [ ] `char_score(char, best_send_service=None) -> int` + `rank_characteristics(chars) -> List[dict]`
      （稳定排序，附 `score` 字段副本，不改原对象）。
- [ ] `pick_auto(chars) -> (recv, send, reason)`：发送 = 分最高且 `can_send`；接收优先同码 → 同服务 → 全局。
- [ ] `probe_candidates(chars, limit=PROBE_MAX_CANDIDATES) -> List[dict]`：每项
      `{send, recv, label, has_recv, score}`。
- [ ] `resolve_probe_payload(edit_text, mode, default_hex) -> (bytes|None, error, source)`：
      输入框优先（HEX 写错 → 返回错误且**不写**）；空 → 默认帧（`source="default"`）。
- [ ] `ProbeSession`：构造 `(candidates, payload, timeout_ms)`；`next() -> intent|None`；
      `on_subscribed(ok)` / `on_frame(n)` / `on_timeout()` / `stop()`；`result()`；
      `attempts` 记录每项 `{send, recv, status, detail}`。
- [ ] 记忆三件套：`recall_choice(settings, address)` / `remember_choice(settings, address, recv, send, source)` /
      `forget_choice(settings, address)`（含 `ts`，超 `CHAR_MAP_MAX` 淘汰最旧）。
- [ ] `DEFAULT_SETTINGS` 追加：`char_map: {}`、`probe_frame: "41 54"`、`probe_timeout_ms: PROBE_TIMEOUT_MS`；
      `merge_settings` 校验三者（`char_map` 逐条丢弃坏项；`probe_frame` 非法 HEX 回合默认；超时夹紧）。
- [ ] **审查点 A**：纯逻辑自测（`python -c`）：打分排序命中 `FFE1` 而非 `2A19`；`pick_auto` 三档兜底；
      记忆往返 + 淘汰；探测状态机全败/命中；载荷解析三分支。

## 阶段 2 · `bluetooth_worker.py`（只加一个信号）

- [ ] 新增 `subscribe_finished = Signal(list, bool)`（uuid 列表, 是否订阅成功）；
      在 `_subscribe_coro` 的两条返回路径都 `emit`（成功 `True` / 失败 `False`）。
- [ ] **不**改既有信号与收发语义。
- [ ] **审查点 B**：`test_bluetooth_worker.py`（假 bleak）新用例：订阅成功/失败各发一次且 uuid 列表正确。

## 阶段 3 · `bluetooth_tool_widget.py`（接线 + UI）

- [ ] `_on_characteristics_updated`：先查 `core.recall_choice`（命中 → 沿用，`source="recall"` 日志「沿用上次」）；
      否则 `core.pick_auto` → `_apply_characteristics(..., source="auto")` + 依据日志。
- [ ] 删除朴素 `_auto_pick`（改委托 `core.pick_auto`），避免第二份「第一个可用」逻辑。
- [ ] `_apply_characteristics(..., source=...)`：写 `char_map[address]` + 兼容旧全局键；更新状态行。
- [ ] `_refresh_status_line`：追加「发送 → `0xFFE1` ｜ 接收 → `0xFFE1`」（未选「未选」）。
- [ ] 新增按钮「自动探测」（挨着「特征码…」；tooltip 说明会真写一帧 + 发送框为空用默认帧）；
      `_start_probe` / `_probe_step`（QTimer 驱动 `ProbeSession`）/ `_finish_probe` / `_cancel_probe`；
      探测期间禁用发送与探测按钮、显示进度日志；`cleanup()` 停表。
- [ ] 探测事件接线：`worker.subscribe_finished` → `session.on_subscribed`；
      `worker.frame_received` → `session.on_frame`（仅在探测中转发，正常收包不受影响）。
- [ ] `CharacteristicSelectDialog`：条目按 `rank_characteristics` 顺序（优选置顶）且**预选**；
      顶部一行「推荐：发送 …｜接收 …（依据 …）」；不可用项在文字上标注「（不可写）/（不可通知）」（陷阱 71 置灰不可靠）。
- [ ] **审查点 C**：offscreen 假 worker 手测：自动选中 `FFE1`；第二次连接沿用；探测命中/全败两条路径。

## 阶段 4 · 测试

- [ ] `test/test_bluetooth_core.py` 扩段（打分/优选/记忆/载荷/状态机，含反例：旧「第一个」会被选成 `2A19`）。
- [ ] `test/test_bluetooth_worker.py` 扩段（`subscribe_finished` 两条路径）。
- [ ] `test/test_bluetooth_widget.py` 扩段（自动优选/沿用/探测成功/探测全败/状态行/对话框预选/按钮禁用）。
- [ ] **变异反证 ≥3 条**（跑完必须还原）：① `char_score` 恒 0；② 探测不等订阅就写（跳过 `on_subscribed` 门）；
      ③ 记忆写全局而非按地址。
- [ ] **审查点 D**：四份蓝牙测试全绿 + 3 条反证变红。

## 阶段 5 · 文档与版本

- [ ] `main_gui.py:CHANGELOG` 1.23.79 条目；`APP_VERSION` → `1.23.79`；`--sync-iss`；README（徽章/版本行/蓝牙通信行/更新记录）。
- [ ] `AGENTS.md`：§8 陷阱 69 补三条（优选单一来源 / 探测必须等 `subscribe_finished` / `char_map` 结构）与演示；
      §3 模块表 `bluetooth_core.py`、`bluetooth_tool_widget.py` 描述各补一句；§10 追加 1.23.79。
- [ ] `.trellis/spec/frontend/component-guidelines.md` 新增「蓝牙特征码优选与探测」契约段落。
- [ ] `python release_check.py --with-gui` → FAIL=0。
- [ ] **审查点 E**：提交只挑本任务文件（`bluetooth_core.py` / `bluetooth_worker.py` / `bluetooth_tool_widget.py` +
      三份测试 + `.trellis/` 产物 + spec 段落），版本/文档四件套按既有结论留在工作区。

## 审查点汇总

| 审查点 | 时机 | 判据 |
|---|---|---|
| A | 阶段 1 后 | 纯逻辑打分/状态机/记忆/载荷全部正确 |
| B | 阶段 2 后 | 订阅完成信号两条路径都发 |
| C | 阶段 3 后 | 自动选中最优；沿用生效；探测两条路径正确 |
| D | 阶段 4 后 | 四份测试全绿 + 3 条变异反证变红 |
| E | 提交前 | release_check FAIL=0、文档齐、只提交本任务文件 |

## 回滚点

1. 阶段 1 失败 → `git checkout bluetooth_core.py`。
2. 阶段 2/3 失败 → `git checkout bluetooth_worker.py bluetooth_tool_widget.py`。
3. 配置只新增 3 个键 ⇒ 回滚不需清理运行时数据。
