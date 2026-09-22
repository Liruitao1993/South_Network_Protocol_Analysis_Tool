# Implement：串口工具按协议断帧与解析

> 前置：`task.py start 09-22-serial-proto-parse`；先跑一遍基线
> `python release_check.py` 确认起点（当前应为 `PASS=94 FAIL=1 WARN=1`，唯一失败是既有的
> `test/test_hdc10_batch_strip_level.py :: 帧类型含 [11]`）。

## Step 0 基线

- [ ] `$env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; python -u test/test_serial_tool_widget.py` → 60 项通过（记录起始值）
- [ ] `python -m ruff check serial_tool_widget.py` → 零告警

## Step 1 分帧纯函数（`serial_tool_widget.py`）

- [ ] 新增 `STRATEGY_BY_PROTOCOL`、`frame_length_for(strategy, buf)`、`_hdlc_frame_end(buf)`（返回尾标志下标）
- [ ] 68 家族复用既有 `_declared_frame_len` 的判别顺序；新增 `dlt645` / `dlt698_45` 显式分支（按协议已知，判别可更严格）
- [ ] 新增 `format_parse_rows(table_data, max_lines) -> list[str]`（纯函数）
- [ ] `frame_length_for` 全部路径返回 0 的兜底：长度越界 / 自证失败 / 未知策略

**验证**：新建 `test/test_serial_proto_frame.py`，先写这 3 个纯函数的用例（含反例），跑通再往下。

## Step 2 协议字段数据模型

- [ ] `_coerce_protocol(value)`（bool/负数/越界/字符串数字/None 全覆盖）
- [ ] `normalize_command` 增加 `protocol` 键
- [ ] `DEFAULT_PARAMS` 增加 `parse_enabled` / `parse_max_lines`；`merge_params` 增加对应钳制
- [ ] `export_commands` 保留 `protocol`

**验证**：`test_serial_proto_frame.py` 追加 `_coerce_protocol` 反例组；`test_serial_tool_widget.py` 追加持久化/导入导出组。

## Step 3 UI：命令表第 5 列 + 对话框下拉 + 接收开关

- [ ] 命令表 4 → 5 列，第 5 列显示 `short_name` / `不解析`
- [ ] `SerialCommandDialog` 增加协议 `QComboBox`（`不解析` + 12 项），`get_data()` 带 `protocol`
- [ ] `_add_command` / `_edit_command` / `_refresh_command_table` 传参与渲染
- [ ] 接收模式行增加 `显示解析` 勾选 + `解析行数上限` `QSpinBox`
- [ ] 落盘/读回新参数（`_collect_params` / `_apply_params`）

**验证**：`test_serial_tool_widget.py` 追加「协议列渲染 / 对话框默认 / 参数落盘读回」。

## Step 4 接收路径改造（`_on_raw_data` / `_emit_protocol_frames`）

- [ ] 发送前锁存 `self._last_tx_protocol`
- [ ] `_rx_log_queue` 元素由 `str` → `(kind, text)`；`_flush_log_queues` 按 kind 上色，burst 只对 `raw` 计数
- [ ] `_emit_protocol_frames(strategy)`：按策略逐帧产出；HDLC 跳过噪声并正确推进 consumed
- [ ] `_on_raw_data` 分派：帧尾模式不变；原始模式在指定协议时先按策略产出，残帧交回既有路径
- [ ] `_flush_raw_display_now` / `cleanup` 仍能刷出残帧（含协议策略下的残帧）

**验证**：`test_serial_proto_frame.py` 的产出用例（逐字节 / 分块 / 多帧 / 噪声 / 未收全）；`test_serial_tool_widget.py` 回归既有 [17] 段（不解析时行为不变）。

## Step 5 解析注入与日志输出

- [ ] `set_parse_provider(fn)`（`None` 时安全降级为不解析）
- [ ] `_parse_and_log(frame_bytes, protocol_index)`：调回调 → `format_parse_rows` → 入队 `parse`/`fail`
- [ ] `main_gui._serial_parse_provider(frame_bytes, protocol_index)` + `_ensure_serial_tool_tab` 注入
- [ ] 「显示解析」关闭 → 直接跳过 `_parse_and_log`（零开销）

**验证**：`test_serial_tool_widget.py` 用**假 provider**（返回固定表 / 抛异常 / 返回空表）验证格式、截断、失败行、开关；不依赖真解析器。

## Step 6 真解析器冒烟（可选，本机可跑）

- [ ] 用真实国网 208 字节帧（测试 [17] 已内置）跑 `_serial_parse_provider(frame, 7)`，确认不抛异常且行数 > 0
- [ ] 用 645 / 698.45 构造帧各跑一次

**验证**：新增一个 `test_serial_proto_frame.py` 里的「真实解析器联调」小段（登记进 CORE_TESTS 前确认耗时可接受）。

## Step 7 文档与版本

- [ ] `AGENTS.md` §3 文件表（新测试文件）、§8 新增陷阱（协议分帧的判别顺序 / HDLC 噪声消费 / burst 只对 raw 计数）
- [ ] `CHANGELOG` 新增条目 + `APP_VERSION` 递增（1.23.47）+ `BUILD_DATE`
- [ ] `python release_check.py --sync-iss` 同步两个 `.iss`
- [ ] `.gitignore`（若新增运行时文件）

## Step 8 全量回归

- [ ] `python release_check.py` → 除既有 1 项失败外全绿
- [ ] `python -m ruff check <改动文件>` → 零新增告警
- [ ] 真机冒烟（需真实/虚拟串口）：国网命令 → RX 一行整帧 + 中文解析（**本机无串口则如实标注未验证**）

## 验收清单（对照 prd）

| AC | 验证方式 |
| --- | --- |
| AC1.1~1.6 | `test_serial_tool_widget.py` 协议列 / 持久化 / 非法值 |
| AC2.1~2.9 | `test_serial_proto_frame.py` 分帧用例 |
| AC3.1~3.8 | `test_serial_tool_widget.py` 假 provider 用例 |
| AC4.1~4.4 | 既有 [17] 段回归 + 开关用例 |
| AC5.1~5.4 | `release_check.py` + ruff + 文档 diff |
