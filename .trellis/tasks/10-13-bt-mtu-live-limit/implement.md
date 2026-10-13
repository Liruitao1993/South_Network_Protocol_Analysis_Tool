# 执行计划

## 1. 纯逻辑层（`bluetooth_core.py`）

- [ ] 在 `MIN_CHUNK` / `DEFAULT_MAX_CHUNK` 附近新增常量与判据：
      `MTU_DEFAULT = 23`、`MTU_POLL_INTERVAL = 0.25`、`MTU_POLL_TIMEOUT = 3.0`、
      `mtu_is_unnegotiated(value) -> bool`（`<= MTU_DEFAULT`，含 0/None/非法）。
- [ ] 注释写清判据依据（ATT 默认 MTU 23 = 负载 20；Windows 上只能读不能请求）。

## 2. 通信层（`bluetooth_worker.py`）

- [ ] `import` 新常量与 `mtu_is_unnegotiated`（从 `bluetooth_core`）。
- [ ] 新信号 `mtu_updated = Signal(int, list)`（与 `characteristics_updated` 并列，注释写清差别）。
- [ ] `__init__`：`self._char_objects: Dict[str, Any] = {}`。
- [ ] `_collect_characteristics()`：同时填充 `self._char_objects[str(uuid)] = char`。
- [ ] 新增 `_refresh_live_limits() -> bool`：
      重读 `client.mtu_size` + 活对象 `max_write_without_response_size`；
      有变化 → 更新 `self._mtu` / `_characteristics[i]["max_write"]` /
      `mtu_updated.emit(...)` / 日志「MTU 协商更新：旧 → 新（特征码免响应写上限 N）」。
- [ ] 新增 `async def _poll_mtu_if_needed(client) -> None`：
      仅 `mtu_is_unnegotiated(self._mtu)` 时轮询；每 `MTU_POLL_INTERVAL` 调 `_refresh_live_limits()`；
      值变化即返回；`MTU_POLL_TIMEOUT` 到期 → 一行提示；断开/换 client/`_closing` → 直接返回。
- [ ] `_connect_coro`：`connected.emit(...)` 与（有接收通道时）`_subscribe_coro()` 之后，
      `await self._poll_mtu_if_needed(client)`。
- [ ] `_write_coro`：在 `self._chunk_plan(targets)` **之前** 调 `self._refresh_live_limits()`。
- [ ] 断开路径（`_disconnect_coro` 与 `_on_disconnected_cb`）：`self._char_objects.clear()`。
- [ ] `shutdown()` 无需额外改（轮询在 connect 协程内，`_closing`/client 判据已覆盖）。

## 3. 界面（`bluetooth_tool_widget.py`）

- [ ] `_wire_worker` 增加 `(worker.mtu_updated, self._on_limits_updated)`。
- [ ] 抽 `_mtu_text(mtu) -> str`（单一实现）：
      `0` → 「未知（按 ATT 最小值 20 字节分包）」；
      `mtu_is_unnegotiated` 且已连接 → 明示「ATT 默认值 23（协商结果未回）」+ 单包上限；
      否则「N 字节（单包上限 M）」。
- [ ] `_on_connected` 改用 `_mtu_text`。
- [ ] 新增 `_on_limits_updated(mtu, characteristics)`：
      更新 `self._chars` 缓存、MTU 标签、特征码计数标签；
      **不得**调 `_apply_characteristics` / `worker.set_characteristics`；
      若有打开中的特征码对话框 → 调其刷新（保勾选、保当前行），否则只更新缓存。
- [ ] 特征码对话框：抽出 `refresh_chars()`（重建两个列表，保留勾选集合与当前行）。

## 4. 测试

- [ ] `test/test_bluetooth_core.py`：新增 `mtu_is_unnegotiated` 边界段（0/None/""/23/24/247）
      + 常量关系 + 反例自检（把判据改成 `< 23` 必须变红）。
- [ ] `test/test_bluetooth_worker.py`：
  - [ ] 假 bleak 扩展：`FakeClient.mtu_size` 改成 **property**（可脚本化/可变），
        `ScriptedChar`（上限按读次数或按可变 `value` 返回）；
  - [ ] [新增段] 迟到协商 / 只支持默认值 / 发送前重读 / 断开打断 / 反例自检；
  - [ ] 既有段（[2] MTU=247、[5] 分包）必须保持全绿（改动不得回退既有契约）。
- [ ] `test/test_bluetooth_widget.py`：新增 `_on_limits_updated` 段
      （标签更新 + `_chars` 更新 + **不重订阅/不改记忆**）。
- [ ] `python test/test_bluetooth_tab_wiring.py` 保持一致（接线未变，跑一遍确认）。

## 5. 验证（收尾门禁）

```bash
# 目标测试（逐条）
python test/test_bluetooth_core.py
python test/test_bluetooth_worker.py
python test/test_bluetooth_widget.py
python test/test_bluetooth_tab_wiring.py
# 全量门禁
PYTHONIOENCODING=utf-8 python release_check.py --with-gui     # 目标 FAIL=0
```

- [ ] 变异反证（每条都要「干净变红」：rc=1 且有 `[NG]` 明细，不是崩溃）：
  1. 去掉连接后轮询 → 迟到协商用例变红；
  2. 去掉发送前 `_refresh_live_limits()` → 发送前重读用例变红（仍按 20 分 2 包）；
  3. 把 `mtu_is_unnegotiated` 判据改成 `< MTU_DEFAULT` → core 边界用例变红。
  - 改源码用 `path.write_bytes()`（本仓 CRLF，`write_text` 会破坏续行），收尾 `finally` 还原 + md5 比对。
- [ ] `CHANGELOG` / `AGENTS.md` / `README.md` 更新（留工作区，不随本提交）。
- [ ] 提交（**只提交本任务文件**，见 memory：版本/文档四件套不提交）。

## 回滚点

- 每个文件改动独立可还原；无持久化格式变更。
- 若发现轮询影响连接时延：把 `MTU_POLL_TIMEOUT` 调小即可（单一常量），或把轮询移到 `connected` 之前回滚语义（不推荐）。
