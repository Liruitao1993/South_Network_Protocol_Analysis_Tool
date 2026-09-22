# 串口工具：集成 USB 负载测试工具（命令发送 + 响应匹配）

## Goal

把 `E:\python\USB负载测试工具`（单文件高速串口收发器，1433 行）的能力**功能照搬**进当前项目，作为主窗口一个始终可见的**「串口工具」标签页**，用于：按命令表高速循环发送报文、按需切分接收帧、**实时比对预期响应**并统计成功率。现场价值：联调时不必另开一个 exe，在同一软件里就能发命令、看响应、算成功率。

风格必须与本项目一致（按钮/图标/表格/主题/右键菜单/配置落盘/测试约定），**不照搬**源工具的自带主题与 `QMainWindow` 外壳。

## Background（已确认事实）

### 源工具（`E:\python\USB负载测试工具\`）

- `serial_load_test.py`（1433 行）+ `commands.json`（1 条国网样本命令）+ `发送数据.txt`（150 行国网 hex 报文，供「加载报文文件」）+ `USB负载测试工具.spec`。
- 功能：串口控制（端口刷新/选择、波特率 15 档 9600~4000000 默认 4000000、连接/断开、1MB 收发缓冲）；命令表 4 列（名称/发送数据 HEX/匹配方式/预期响应）+ 增删改上下移 + 保存配置/加载配置(JSON)/加载报文文件(txt)；发送（间隔 1~10000ms 默认 100、次数 0=无限 默认 1、响应超时 10~600000ms 默认 5000、启用匹配开关、开始/停止）；接收两模式（原始数据 1ms 聚合 / 按帧尾分割，帧尾 HEX 默认 `FE 16`）；响应匹配 6 种（`contains` 包含 / `equals` 完全相等 / `starts_with` 开头 / `ends_with` 结尾 / `regex` 正则 / `none` 不匹配=全部成功）；统计（发送帧/字节、接收帧/字节、匹配成功/失败/成功率、运行时长、清除统计）；彩色日志（TX 红 / RX 绿 / 匹配 ✓✗ / 系统蓝，1 万行上限、自动滚动、显示发送/接收开关、清空）。
- 关键实现细节（照搬依据）：
  - **发送精确间隔**（`SenderThread.run`）：间隔 >5ms 先 `sleep(interval-2ms)`，再用 `while perf_counter() < target: pass` 忙等保精度；最后一条命令后不再延时。
  - **匹配队列语义**（`_on_sent_callback` / `_on_rx_match_data` / `_check_match_timeout`）：发送时仅当「启用匹配 且 `match_type != none`」才把 `(seq, msg_index, expected, match_type, sent_time)` 入队（`_tx_total += 1`）；接收数据**从队首连续**尝试匹配（一批数据可连续命中多项）；100ms 定时器把队首超时项弹出并计入失败。
  - **收尾**（`_handle_send_done` / `_finalize_send`）：发送完成后**再等 `match_timeout + 100ms`** 收尾剩余响应，然后打印成功率摘要；停止发送时把剩余待匹配项直接计为失败。
  - **命令文件格式**：JSON 列表 `[{"name","data_hex","match_type","match_hex"}]`；报文文件为每行 hex（`load_hex_messages` 会取 `:` 之后的部分）。
  - 接收线程 raw 模式：匹配回调吃**实时数据**，显示走 1ms 聚合缓冲（两者分离，避免聚合延迟影响匹配）。

### 当前项目（`E:\python\南网解析工具\`）

- **已有串口层可复用**：`serial_worker.SerialWorker(QThread)`（202 行）提供 `configure/open_port/close_port/is_open/send_frame/send_hex_string`、信号 `frame_received`/`raw_data_received`/`log_message`/`connection_changed`/`error_occurred`、静态 `list_ports()`；已被 `frame_gen_widget`（组帧页串口发送）使用。**注意**：`send_frame` 每帧都会 `log_message.emit`，高速发送时会淹没 GUI；且无写锁。
- **标签页约定**：工具类标签页在 `setup_ui` 用占位 `QWidget` + `app_icons.load_icon(...)` 加 Tab（`main_gui.py:2441-2443` 的 TCP 监控），切到该 Tab 时经 `elif index == self._xxx_tab_index:` 调 `_ensure_xxx_tab()`（`main_gui.py:3686`）懒加载并 `_replace_lazy_tab(placeholder, index, tab)` + `apply_chinese_context_menus(tab)`（`main_gui.py:3739-3758`）。
- **风格约定**：按钮 `set_btn(btn, kind)` + `set_btn_icon(btn, key)`（`gui_utils._STANDARD_ICON_MAP` 键：add/edit/delete/up/down/save/open/open_file/refresh/clear/play/stop/apply/cancel…）；表格用 `gui_utils.ZoomableTableWidget` + `_setup_table_copy_menu`；图标可用 `app_icons.load_icon("refresh-cw")`（lucide）；主题走项目 QSS（组件内**不写** stylesheet）；线程用 `thread_registry.track(self, name)`。
- **落盘约定**：组件自有数据用 `app_paths.data_path("<name>.json")` + `json.dump`（如 `frame_gen_widget.py:1678` 的 `dlt645_addr_history.json`）；主窗口设置走 `config.json` 的段落（现有 `serial` 段 = 顶栏串口配置 `{port, baudrate, parity}`，**不可复用/覆盖**）。
- **测试约定**：`test/test_*.py` 独立脚本、`import _path_setup  # noqa: E402,F401`、offscreen、`os._exit(1 if FAIL else 0)`、登记 `release_check.py:CORE_TESTS`。

## Key Decisions（已与用户确认）

1. **形态**：主窗口新增**「串口工具」标签页**（与 TCP 监控/报文工具同级，始终可见），不额外做独立窗口。
2. **串口层**：**复用 `serial_worker.SerialWorker`**（端口列举/打开/接收循环），仅为其新增静默写入接口 `write_raw()`（不逐帧发日志信号 + 加写锁）；项目内只保留一套串口实现。
   - **修正（实施期由用户指出）**：进一步改为**复用主窗口共享的 `self.serial_worker`**（与组帧页/监控器页同一约定，`tab.set_serial_worker(self.serial_worker)`），本页**不再自带端口/波特率/连接控件**，只读跟随 `connection_changed`。原因：一个 COM 口只能被打开一次，各页各持一个 `SerialWorker` 会互相抢口（顶栏连上后本页再连必失败），且波特率会出现两处配置——与项目既有风格不一致。
3. **持久化**：命令表与发送参数**自动落盘**（`data_path("serial_tool_config.json")`），同时保留「导入/导出 JSON」与「加载报文 txt」；导出格式与源工具兼容。
4. **流程**：走 Trellis（本任务 `09-22-serial-tool-integration`）。

## Requirements

### R1 串口工具标签页

- AC1.1 主窗口出现「串口工具」标签页（带图标），**始终可见**（不随协议切换隐藏），首次切到该页时才创建内容（懒加载，不拖慢启动）。
- AC1.2 页面含：串口控制行、命令列表、发送配置行、接收模式行、统计区、彩色日志区。
- AC1.3 界面风格与本项目一致：按钮走 `set_btn`/`set_btn_icon`、表格走 `ZoomableTableWidget` 且带右键复制菜单、中文右键菜单已应用、颜色随项目主题（组件内无自定义 stylesheet）。

### R2 串口接入（复用主窗口共享串口）

- AC2.1 本页**不提供**端口/波特率/连接控件；串口的连接与断开、波特率与校验全部在顶部「串口配置」完成（一个 COM 口只能打开一次，避免多页争抢）。
- AC2.2 本页只读展示连接状态，并随 `connection_changed` 实时更新；未连接时「开始发送」按钮置灰。
- AC2.3 未连接时点「开始发送」给出明确提示（引导去顶部「串口配置」连接），不启动、不写串口。
- AC2.4 页面 `cleanup()` **不关闭串口**（端口生命周期归顶部「串口配置」与主窗口收尾），只停发送线程与落盘。
- AC2.5 换绑 worker 时旧 worker 的信号必须被解绑（迟到的 `connection_changed` 不得影响本页状态）。

### R3 命令列表

- AC3.1 4 列：名称 / 发送数据(HEX) / 匹配方式 / 预期响应；只读、整行选择、支持右键复制。
- AC3.2 添加/编辑/删除/上移/下移；上移下移在首尾时无副作用。
- AC3.3 添加/编辑对话框校验 HEX 合法性（发送数据必填合法；匹配方式非「不匹配」时预期响应也须合法），非法给出提示且不落库。
- AC3.4 保存配置/加载配置（JSON）与源工具**格式兼容**：可加载源工具 `commands.json`（裸列表），导出的 JSON 也能被源工具加载。
- AC3.5 加载报文文件：每行一条 hex（兼容 `前缀:` 形式），逐行追加为命令（名称自动编号），非法行跳过并计数。
- AC3.6 命令表变化后自动落盘，重启后自动恢复。

### R4 发送

- AC4.1 参数：发送间隔 1~10000ms（默认 100）、发送次数 0~999999（0 显示为「无限」，默认 1）、响应超时 10~600000（默认 5000ms）、启用响应匹配（默认勾选）。
- AC4.2 未连接串口或命令表为空时点「开始发送」给出明确提示且不启动。
- AC4.3 任一命令数据非法时阻止启动并指出是哪条命令。
- AC4.4 发送线程独立于 GUI（不阻塞界面），按间隔精确发送；间隔 >5ms 时用「先 sleep 大部分 + 尾段忙等」保精度。
- AC4.5 发送中按钮变「停止发送」，停止后剩余待匹配项计为失败；发送完成后自动收尾（等一个响应超时 + 100ms）并打印成功率摘要。
- AC4.6 发送异常（如串口拔出）时日志报错、按钮复位、不崩。

### R5 接收与分帧

- AC5.1 两种模式：原始数据（短时聚合后显示，聚合不得影响匹配时效）/ 按帧尾分割（帧尾 HEX 可配，默认 `FE 16`）。
- AC5.2 帧尾非法时给出提示并保持上一有效值。
- AC5.3 接收字节流按帧尾正确切分（含跨包帧、一包多帧、尾部残帧保留）。
- AC5.4 接收统计（帧数/字节数）随接收更新。

### R6 响应匹配与统计

- AC6.1 6 种匹配方式，与源工具同名同义：包含/完全相等/开头匹配/结尾匹配/正则表达式/不匹配（全部成功）。
- AC6.2 匹配方式为「不匹配」或未勾选「启用响应匹配」时，该命令不计入匹配统计（与源工具一致）。
- AC6.3 接收数据**从队首连续**匹配：一批数据能连续命中多个待匹配项时全部计入成功。
- AC6.4 超过响应超时仍未匹配的项计为失败，并在日志给出「#序号 名称 超时未匹配」。
- AC6.5 统计区显示：发送帧数/字节、接收帧数/字节、匹配成功/失败/成功率、运行时长；「清除统计」在发送中不可用。
- AC6.6 统计口径与源工具一致：成功率 = 成功 / 已发送待匹配数。

### R7 日志

- AC7.1 彩色区分：TX（红）、RX（绿）、匹配成功（绿 ✓）/失败（红 ✗）、系统与统计（蓝）。
- AC7.2 上限 1 万行（超出自动丢弃最旧）；自动滚动可关；「显示发送」「显示接收」可分别关闭；「清空日志」可用。
- AC7.3 高速发送时日志不得拖垮界面（发送逐帧日志**批量/节流**，不逐帧刷屏）。

### R8 参数持久化

- AC8.1 参数（间隔、次数、超时、启用匹配、接收模式、帧尾、显示开关、自动滚动）自动落盘并在重启后恢复；**波特率不在此列**（归顶部「串口配置」的 `serial` 段）。
- AC8.2 落盘位置不与顶栏 `serial` 段、也不与其它组件的数据文件冲突。
- AC8.3 数据文件损坏/缺失时按默认值启动，不崩。

### R9 测试与回归

- AC9.1 新增 `test/test_serial_tool_widget.py`（offscreen）覆盖：6 种匹配方式、队首连续匹配、超时计入失败、帧尾切分（跨包/多帧/残帧）、统计口径、命令增删改与上下移、JSON 导入导出往返（含源工具裸列表）、参数落盘往返、非法输入校验、发送参数校验。
- AC9.2 关键逻辑用**纯函数/无串口**方式可测：匹配与统计不依赖真实串口（用假 worker 或直接调方法）。
- AC9.3 新增 `serial_worker.write_raw` 有测试覆盖（发送字节正确且**不发日志信号**）。
- AC9.4 既有 `test/test_serial_worker_framing.py` 等串口相关测试全绿；`python release_check.py` 无新增 FAIL。

## Out of Scope

- 源工具自带的 4 套主题与自定义 stylesheet（改用本项目主题系统）。
- 源工具的 `QMainWindow` 外壳、状态栏（改为标签页 + 页面内状态标签）。
- 源工具「本页自带端口/波特率/连接」的形态：本项目改为复用主窗口共享串口（见 R2 与 Key Decision 2 的修正）。
- 脚本化/自动化测试序列（如按脚本编排多命令）——源工具也没有。
- 把串口工具接入协议解析（本工具只做收发与匹配，不做协议解析）。

## Open Questions

无阻塞项（4 项产品决策已确认，见 Key Decisions）。
