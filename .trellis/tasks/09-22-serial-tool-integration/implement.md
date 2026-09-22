# 实施计划：串口工具集成

对应 `prd.md`（R1~R9）与 `design.md`（契约 A~F）。**每个 Block 完成后跑该 Block 的验证命令并全绿，才进入下一 Block。**

## B0 基线冻结（改代码前）

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_serial_worker_framing.py
python release_check.py --skip-tests
```

- 记录基线结果；已知既有失败（**不计入本次回归**）：`test/test_hdc10_batch_strip_level.py :: 帧类型含 [11]`。

**门禁**：`test_serial_worker_framing.py` 全绿、`release_check --skip-tests` 无 FAIL。

## B1 `serial_worker.write_raw`（契约 A / AC9.3）

1. 加 `self._write_lock = Lock()`；`send_frame` 与新增 `write_raw` 共用。
2. `write_raw(data) -> bool`：未打开 → `error_occurred.emit` + False；写异常 → `error_occurred.emit` + False；成功 → **不发任何信号**。
3. 新增 `test/test_serial_worker_write_raw.py`：用假串口对象（鸭子类型，`is_open`/`write`）断言
   - 写入字节正确、返回 True；
   - **不产生 `log_message` 信号**（与 `send_frame` 对比：后者必须产生）；
   - 未打开返回 False 且发 `error_occurred`；
   - 写异常返回 False 且发 `error_occurred`。

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_serial_worker_write_raw.py
QT_QPA_PLATFORM=offscreen python -u test/test_serial_worker_framing.py   # 回归
```

## B2 纯逻辑层：匹配 / HEX / 报文文件 / 持久化（契约 D、E / AC6.1~6.6、AC8.x、AC9.1）

新增 `serial_tool_widget.py`，先落**与 UI 无关**的部分：

1. `hex_str_to_bytes(s) -> bytes | None`（支持空格/逗号；非法返回 None）
2. `check_match(received, expected, match_type) -> bool`（6 种，与源工具同名同义）
3. `load_hex_messages(path) -> list[bytes]`（每行一条，兼容 `前缀:` 形式，非法行跳过）
4. `SerialToolConfig`（或模块级函数）：`load_config(path) -> (commands, params)` / `save_config(path, commands, params)`（临时文件 + `os.replace` 原子写）；损坏/缺失回落默认值；导出裸列表、导入兼容两种形态
5. `test/test_serial_tool_widget.py` 第 1 段：
   - 6 种匹配方式各正反例（含非法正则返回 False、`none` 恒真）
   - `hex_str_to_bytes` 正/反例（含逗号、`0x` 前缀不加支持要与源工具一致、空串）
   - `load_hex_messages`：正常行、`前缀: hex`、空行、非法行跳过计数
   - 配置往返：save→load 等价；**导入源工具裸列表**；导出后是裸列表；损坏文件回落默认值

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_serial_tool_widget.py
```

## B3 UI 骨架 + 命令表（契约 F / R1、R3）

1. `SerialToolWidget._build_ui()`：**只读串口状态行**、命令列表（`ZoomableTableWidget` 4 列 + 按钮行）、发送配置行、接收模式行、统计区、日志区；风格按契约 F（`set_btn`/`set_btn_icon`/`_setup_table_copy_menu`/`apply_chinese_context_menus`/无自定义 stylesheet）。
   > 端口/波特率/连接控件**不做**：串口复用主窗口共享的 `serial_worker`，本页只读跟随连接状态（见设计 §8 与契约 A 的修正）。
2. `SerialCommandDialog`：名称 / 发送数据 HEX / 匹配方式 / 预期响应；HEX 校验（AC3.3）。
3. 命令表操作：添加/编辑/删除/上移/下移/刷新表格；变更后触发去抖落盘（AC3.6）。
4. 导入/导出/加载报文文件（AC3.4/AC3.5）。
5. 测试第 2 段：命令增删改上下移的行数/顺序断言；首尾上下移无副作用；非法 HEX 被拒（对话框 `_on_ok` 不 accept）；导入源工具样本（用仓库内样本或内联样例）后表格行数正确；导出后文件是裸列表。

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_serial_tool_widget.py
```

## B4 发送 + 统计 + 日志（契约 B、F / R4、R7 / AC7.3）

1. `SerialSendWorker(QThread)`：精确间隔 + `loop_count=0` 无限 + `sent/done/failed` 信号 + `stop()`。
2. 发送配置接线：间隔/次数/超时/启用匹配/开始-停止按钮状态与文案（AC4.5）；启动前校验（AC4.2/AC4.3）。
3. 统计轮询（200ms）+ 运行时长 + 清除统计（发送中禁用，AC6.5）。
4. 日志：着色 + `setMaximumBlockCount(10000)` + 自动滚动/显示发送/显示接收开关 + 清空；**发送日志按 100ms 批量汇总**（AC7.3）。
5. 收尾：发送完成后等 `timeout + 100ms` 再收尾并打印成功率摘要（AC4.5）；停止/异常路径复位（AC4.6）。
6. 测试第 3 段：用**假 worker**（鸭子类型，记录 `write_raw` 调用）驱动发送线程
   - 发送条数 = 命令数 × 次数；`loop_count=0` 时 `stop()` 能及时结束
   - 精确间隔：间隔 50ms × 3 条，实测总耗时不小于理论值的 80%（不引入脆弱上界断言）
   - 写失败 → `failed` 信号且停止后续发送
   - 日志批量：连续发送 N 帧后日志行数远小于 N（AC7.3 的可测代理）

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_serial_tool_widget.py
```

## B5 接收分帧 + 匹配队列 + 超时（契约 C、D / R5、R6）

1. 订阅 `raw_data_received`：先匹配、再显示（raw 聚合 / frame 尾切分）。
2. `frame_tail` 编辑校验（AC5.2）。
3. 匹配队列：发送回调入队（AC6.2 的门槛）、接收从队首连续匹配（AC6.3）、100ms 超时弹出计失败（AC6.4）、停止/收尾把剩余计失败。
4. 测试第 4 段（**不打开真实串口**，直接调方法喂数据）：
   - 帧尾切分：跨包（分两次喂）、一包多帧、尾部残帧保留
   - 队首连续匹配：一次喂入能命中两个待匹配项的数据 → 成功 2
   - 顺序语义：后入队项不越前匹配
   - 超时：把 `sent_time` 改早 → 100ms 检查后计失败并出日志
   - 统计口径：`_tx_total` 只统计「启用匹配且 match_type≠none」的发送；成功率 = 成功/`_tx_total`
   - 停止时剩余待匹配计失败

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_serial_tool_widget.py
```

## B6 主窗口集成（契约 F / R1 / AC1.1）

1. `setup_ui`：占位 Tab「串口工具」（图标 `cable`，追加在末尾）。
2. Tab 切换 `elif` → `_ensure_serial_tool_tab()`：懒加载 + **`tab.set_serial_worker(self.serial_worker)`** + `_replace_lazy_tab` + `apply_chinese_context_menus`。
3. `SerialToolWidget.cleanup()`：停发送 → 落盘（**不关闭共享串口**）；接到主窗口关闭流程（与既有工具页一致）。
4. 测试第 5 段（offscreen 构建 MainWindow）：
   - Tab 存在且标题/图标正确；**首次切到该页才创建**（懒加载断言）
   - 切过去后页面对象存在、命令表/日志/统计控件就位，且**接入的是 `mw.serial_worker`**
   - 共享串口契约：未连接置灰、`connection_changed` 驱动按钮、未连接拒绝发送、换绑后旧 worker 信号被忽略、`cleanup()` 不关串口
   - `cleanup()` 幂等、不崩（无串口时）

```bash
QT_QPA_PLATFORM=offscreen python -u test/test_serial_tool_widget.py
QT_QPA_PLATFORM=offscreen python -u test/test_menu_wiring.py   # 菜单/Tab 接线回归
```

## B7 收尾

1. 登记 `release_check.py:CORE_TESTS`：`test/test_serial_tool_widget.py`、`test/test_serial_worker_write_raw.py`。
2. `main_gui.py:APP_VERSION` 递增 + `CHANGELOG` 条目（含源工具对照与验收映射）+ `BUILD_DATE` 更新。
3. `python release_check.py --sync-iss` 同步 Inno Setup 版本。
4. `AGENTS.md`：§3 主要文件表加 `serial_tool_widget.py`；§8 新增陷阱（串口工具契约：write_raw 静默发送、日志节流、匹配队列语义、持久化文件、独立句柄）；§10 版本摘要。
5. 全量验证 + 人工冒烟：

```bash
QT_QPA_PLATFORM=offscreen python release_check.py
python main_gui.py     # 真机：连串口（或虚拟串口对）→ 加命令 → 开始发送 → 看 TX/RX 与成功率
```

## 顺序与回滚点

| Block | 可独立回滚 | 回滚方式 |
| --- | --- | --- |
| B1 | 是（纯增量） | 删 `write_raw` 与写锁 |
| B2~B5 | 是（新文件） | 删 `serial_tool_widget.py` + 测试 |
| B6 | 是（3 处小改） | 移除 Tab 注册与 `_ensure_serial_tool_tab` |

**依赖顺序**：B1 独立；B2 → B3 → B4 → B5 顺序推进（同文件增量）；B6 依赖 B3（页面可构建）。

## `task.py start` 前的最终检查

- [ ] `prd.md` / `design.md` / `implement.md` 已评审通过（用户明确批准）
- [ ] B0 基线已记录（`test_serial_worker_framing.py` + `release_check --skip-tests`）
- [ ] 源工具样本已定位（`commands.json` 1 条、`发送数据.txt` 150 行）——用于导入/导出兼容测试
- [ ] 图标键已确认存在（`cable`、`refresh-cw`、`add/edit/delete/up/down/save/open/open_file/clear/play/stop`）
