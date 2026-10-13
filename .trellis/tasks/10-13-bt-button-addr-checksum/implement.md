# 执行计划

## 0. 布局探针（先做，empirical）

- [ ] 用脚本对 6 个协议各取一条**真实帧**（来源：`NW_command.json` / `GW_command.json` / `DLT645_command.json` / 698 测试夹具 / `YW645_command.json` / `CSG_UPLINK_command.json` 或 `test/test_*.py` 内的固定帧），打印：
  - 我的布局推导（地址域起止、长度、中继级别/地址特征字节） vs 该协议解析器的地址行（`parse_to_table` 里名称含「地址」的行）；
  - 原帧是否通过该协议校验器（`validator` → fail 数）。
- [ ] 用探针结果确认/修正 design.md 表里的每个偏移（尤其：南网 D5=0 的无地址帧、国网 dir=1（上行）信息域长度、698 SA 长度推导）。
- [ ] 探针结论写进 `research/layout-probe.md`（含每协议的帧 hex + 地址字节 + 校验器 fail 数）。

## 1. 纯逻辑模块 `frame_addr_fix.py`

- [ ] `AddrField` / `FixResult` / `SUPPORTED_PROTOCOLS` / `fields_for()`。
- [ ] `parse_address(text, field, frame, protocol_index)`：hex（在线顺序）与协议地址（数字）双认 + 长度校验 + 可读错误。
- [ ] 6 个 `_apply_<proto>()`：结构自证 → 定位 → 替换 → 复用协议实现重算校验 → 返回 `FixResult`（`notes` 含地址与校验旧/新值）。
- [ ] `apply()` 分派：不支持的协议 → 可读错误；`fields_for(...)==()` 时不接受地址参数。
- [ ] 异常一律转为 `ok=False`（不得抛给 GUI）。

## 2. 数据与 UI

- [ ] `bluetooth_core.normalize_button`：保留 `protocol`（int 或 None，越界/非法回落 None）与 `addr`（dict[str,str]，非 dict 回落 None；值 strip 限长）。
- [ ] `bluetooth_tool_widget.ButtonEditDialog`：协议下拉（`不处理` + `fields_for` 非空的协议，名称取 `protocol_registry`）+ 动态地址行（QFormLayout 重建）+ 实时提示（写入字节预览/错误）。
- [ ] 按钮 tooltip 显示绑定的协议与地址（便于核对）。
- [ ] `_on_custom_clicked`：`apply()` → 失败弹框+日志不发；成功日志 notes + 发送处理后帧；**不改 `edit_send`**。
- [ ] 导出/导入/批量：不丢新键（`parse_button_lines` 保持 3 字段语义）。

## 3. 测试

- [ ] `test/test_bluetooth_addr_fix.py`（新）：每协议真帧 oracle（地址字节 + **协议校验器 0 fail** + 其它字节不变）、错误矩阵、双输入语义、反例自检。
- [ ] `test/test_bluetooth_widget.py`：对话框联动/回读/发送替换/失败不发/发送框不变。
- [ ] `test/test_bluetooth_core.py`：新键规范化（保留/回落/坏值）。
- [ ] `test/test_bluetooth_worker.py` / `test_bluetooth_tab_wiring.py`：回归（不应受影响）。

## 4. 验证门禁

```bash
python test/test_bluetooth_addr_fix.py
python test/test_bluetooth_core.py
python test/test_bluetooth_worker.py
python test/test_bluetooth_widget.py
python test/test_bluetooth_tab_wiring.py
PYTHONIOENCODING=utf-8 python release_check.py --with-gui     # 目标 FAIL=0（既有环境红除外）
```

- [ ] 变异反证（每条必须「干净变红」：rc=1 + `[NG]` 明细、无 Traceback；改源码用 `write_bytes`，`finally` 还原 + md5 一致）：
  1. 去掉校验重算（写回旧校验字节）→ 各协议校验器用例红；
  2. 地址字节序反了（645 高低字节对调）→ 地址断言红；
  3. 698 SA/CA 不重建（只改 SA 不改 HCS/FCS）→ 698 校验器红；
  4. 长度不校验（允许改长度）→ 长度错误用例红。
- [ ] 冒烟：offscreen 建页面 + 假 worker，建一个绑定地址的按钮 → 点发送，打印**实际写出的字节**与日志 notes。
- [ ] `CHANGELOG` / `AGENTS.md` / `README.md` 更新（留工作区，随发版批次）；`.trellis/spec/frontend/component-guidelines.md` 补 §7f 契约。

## 回滚点

- 每文件独立可还原；按钮数据结构向后兼容（旧配置无新键）。
- 若某协议布局探针不成立：该协议 `fields_for` 返回 `()` 并在 PRD/日志中标注「v1 不支持」，不硬编码猜测。
