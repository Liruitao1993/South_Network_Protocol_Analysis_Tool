# implement.md — 协议8 698.45 文件传输升级

> 执行顺序即编号顺序；每个「门禁」不通过**不得进入下一步**（证据优先，禁止带病推进）。
> 约定：改动前先 `git status --porcelain -- <file>` 记录本任务触达文件；不提交本任务之外的文件；发版四件套（`main_gui.py` 的版本/CHANGELOG、`AGENTS.md`、`README.md`、两个 `.iss`）随发版批次留在工作区，**不单独提交**。

## 阶段 0 · 基线（先做，作为回归对照）

1. 记录基线：`PYTHONIOENCODING=utf-8 python test/test_dl_t698_45.py`、`test_dl_t698_45_data_decode.py`、`test_dl_t698_45_endian.py`、`test_dl_t698_45_extract.py`、`test_serial_proto_frame.py`、`test_serial_tool_widget.py`、`test_wakeup_fe_prefix.py`、`test_protocol_registry.py`、`test_yw645_gui.py` 各自 PASS/FAIL 数（存到任务 `research/baseline.txt`）。
2. 确认三帧 golden 与 doc 逐字节一致（已在本设计的实测中达成，脚本化进 `test/test_dl698_upgrade.py` 的 A1）。
3. 确认 `crcmod` 可用：`python -c "import crcmod.predefined;print('ok')"`。

**门禁 0**：基线测试全绿（允许既有环境红，如 COM1/COM2 占用，需逐条说明）。

## 阶段 1 · 既有协议栈修复 + 分帧单一来源（先修基础设施，再做新功能）

1. `dl_t698_45_axdr.py`：
   - `_decode_bit_string`：长度域按**位数**，`nbytes=(bits+7)//8`，消耗 `1+llen+nbytes`，说明文案 `N位`。
   - `_encode_bit_string`：长度域写 `len(value)*8`。
   - `_encode_date_time_s` / `_encode_date_time` / `_encode_date` / `_encode_time`：改为 `bytes([tag]) + 定长原始字节`（7/10/5/3），不再委托 `_encode_octet_string`。
   - `_decode_time`：尝试改为 3 字节（规范 SIZE(3)）；**若 `test_dl_t698_45*.py` 出现回归则回退**，并在 `design.md §6.3` 记录结论。
2. `dl_t698_45_oi_lookup.py`：类18 的 `0xF001` 实例方法名补 7 启动传输 / 8 写文件 / 9 读文件 / 10 软件比对 / 13 执行升级 / 14 启动传输（沿用该文件既有数据结构，不新开清单）。
3. `frame_deframe.py`（新建）：把 `serial_tool_widget.py` 的纯分帧族**原样搬出**（`STRATEGY_BY_PROTOCOL`/`END_CHAR_STRATEGIES`/`FE_WAKEUP_STRATEGIES`/`_wakeup_base`/`_sane_frame_len`/`frame_length_for`/`declared_frame_len`/`hdlc_frame_len`/`dlt645_frame_len`/`dlms_wrapper_frame_len`/`frame_incomplete`），模块内只依赖 `wakeup_prefix`；`serial_tool_widget.py` 改为 `from frame_deframe import *`（显式列名）+ 保留 `SerialToolWidget._declared_frame_len` 委托。
4. 验证：
   - `python test/test_dl_t698_45.py`、`test_dl_t698_45_data_decode.py`、`test_dl_t698_45_endian.py`
   - `python test/test_serial_proto_frame.py`、`test/test_serial_tool_widget.py`、`test/test_dl_t698_45_extract.py`、`test/test_wakeup_fe_prefix.py`
   - 手工核对：doc 启动传输帧 `parse_to_table` 不再出现「未知类型(0x76)」，OMD/成员4 显示 `3位`。

**门禁 1**：门禁 0 的全部测试项**数量与结果不变**；doc 帧解析从「失败」变「成功」（这是本步唯一的预期变化）。

## 阶段 2 · 纯逻辑升级模块 `dl_t698_45_upgrade.py`

1. 数据类与函数（全部无 Qt）：`UpgradePlan`/`split_blocks`、`build_sa`、`build_file_info`、`build_start_transfer`、`build_write_block`、`build_exec_upgrade`、`check_action_response`、`calc_checksum_value`（md5/sha1/crc32 大端·小端）。
   - 组帧一律经 `DLT69845FrameGenerator.generate_action_request_normal(... , param + b"\x00")`；`AXDRCoder` 只用于标签+值编码；bit-string 走 `04 <bits> <byte>`。
   - `dl_t698_45_frame_gen` / `dl_t698_45_axdr` / `dl_t698_45_parser` 在本模块**顶层 import 允许**（纯逻辑模块，非 GUI），但**调用方（Qt 页）必须函数内惰性 import 本模块**。
2. `test/test_dl698_upgrade.py`（新，登记 `release_check.py:CORE_TESTS`）：按 design §11 的用例表逐条写；含 AC3/AC5 golden、分包矩阵、SA 矩阵、确认判定矩阵、校验对拍、encode↔decode 互逆、doc 帧解析零错误。
3. **变异反证**（每条都要实测变红后逐字节还原）：`_decode_bit_string` 改回字节（红）、`_encode_date_time_s` 加回长度域（红）、块序号改 1 基（红）、SA 不逆序（红）、`frame_length_for` 的 `L+2` 改 `L`（红）。

**门禁 2**：新测试全绿 + 5 条变异反证均实测变红 + 阶段 1 门禁仍绿。

## 阶段 3 · Qt 页面 `dlt698_upgrade_widget.py`

1. `_DropArea(QFrame)`（`setAcceptDrops`/`dragEnterEvent`/`dropEvent` → `file_dropped=Signal(str)`）+ 浏览按钮。
2. 参数字段与折叠区（`collapsible_section.CollapsibleSection`）、进度条、日志区、按钮（`gui_utils.fit_btn_width`，**禁止** `setFixedWidth`）。
3. `set_serial_worker(worker)`：只订阅 `raw_data_received`/`connection_changed`/`error_occurred`；`write_raw` 发送；**不 open_port**。
4. 逐包状态机（单发 `QTimer` + 标志位，见 design §4/§5）、PIID 自增、重试、超时、中止、进度。
5. 配置持久化 `app_paths.data_path("dlt698_upgrade_config.json")`（属性访问，原子写，坏文件宽容）；`cleanup()`；`restyle_for_theme(dark)`。
6. `test/test_dl698_upgrade_gui.py`（新，登记 `GUI_TESTS`）：假 `SerialWorker`（记录 `write_raw` 次数、可注 `raw_data_received`）→ 全通 / 中间包重试成功 / 超时用尽中止 / 中止按钮 / 进度一致 / 未连接禁用 / 拖放（`QMimeData.setUrls` + `QDropEvent`）/ 按钮不裁字。

**门禁 3**：GUI 测试全绿；`QT_QPA_PLATFORM=offscreen` 下无异常退出。

## 阶段 4 · 接线 + 文档/版本

1. `protocol_registry.py`：`has_upgrade` 字段 + 协议8 `has_upgrade=True`（+ 可选 helper/`__all__`）。
2. `main_gui.py` 六处（design §8）：tab 创建即隐藏、`_ensure_lazy_tab` 分支、`_ensure_upgrade_tab()`、`_on_protocol_changed` 显隐、`_shutdown_threads` 调 `cleanup()`、`_restyle_for_theme` 钩子。
3. 测试同步：`test_protocol_registry.py`（`has_upgrade` 仅协议8）、`test_yw645_gui.py` 可见性矩阵加 `("_upgrade_tab_index", spec.has_upgrade, "升级")`。
4. 文档：`AGENTS.md`（§1 协议表注记、§3 模块树、§5.6 新增「文件传输升级」小节、§6 Tab 可见性规则、§8 新陷阱：bit-string 位宽 / date_time_s 定长 / raw_data_received 组帧 / 惰性 import）、`.trellis/spec/frontend/component-guidelines.md` **§7j**（新增「协议专属升级页」规范）、`main_gui.py:CHANGELOG` + `APP_VERSION`、`README.md`、两个 `.iss`（`python release_check.py --sync-iss` 对齐）。
5. 打包资源：若新模块需显式 `hiddenimports`，同步 `南网协议解析工具.spec`。

**门禁 4**：`python release_check.py --sync-iss` 的 FAIL 仅剩既有环境红；`test_protocol_registry.py`、`test_yw645_gui.py` 全绿。

## 阶段 5 · 验收与交付

1. 逐条对照 PRD AC1~AC10，每条给出**可复核证据**（命令 + 关键输出片段）。
2. `PYTHONIOENCODING=utf-8 python release_check.py --with-gui` → 目标 `FAIL` 不新增（既有 COM1/COM2 环境红除外）。
3. `python main_gui.py` 真机手测（若可用串口/回环）：
   - 协议8 下「升级」tab 出现、其它协议不出现；
   - 拖入 1~2 MB 文件 → 分包数正确；
   - 用 698 虚拟表（`meter_sim`）或串口回环确认「启动传输 → 逐包确认 → 执行升级」时序（虚拟表当前对 ACTION 只回通用成功 DAR，需人工核对帧序列与日志，**不要求**其实现升级逻辑）。
4. 变更日志与长尾：把「阶段 1 的协议栈修复」写成 AGENTS §8 陷阱条目（含 doc 实帧证据与「为什么按位」），确保后来者不会改回字节口径。

## 回滚点

| 回滚点 | 影响面 | 回滚动作 |
|---|---|---|
| R1 阶段 1 完成 | `dl_t698_45_axdr.py`、`dl_t698_45_oi_lookup.py`、`frame_deframe.py`、`serial_tool_widget.py` | 按文件 `git checkout -- <file>`（各自独立，互不依赖） |
| R2 阶段 2 完成 | 新增 `dl_t698_45_upgrade.py` + 新测试 | 删文件 + `release_check.py` 去掉登记行 |
| R3 阶段 3 完成 | 新增 widget + 新测试 | 删文件 + 去掉登记行（tab 未接，用户不可见） |
| R4 阶段 4 完成 | `protocol_registry.py` + `main_gui.py` 六处 + 文档 | 回退 6 处接线即隐藏入口；新文件仍在但不被引用 |

## 提交切分（建议）

1. `fix(698): A-XDR bit-string 长度域按位 + 定长时间类型编码器`（阶段 1 + 测试）
2. `refactor(serial): 分帧族抽到 frame_deframe 单一来源`（阶段 1 第 3 步）
3. `feat(698): 文件传输升级（启动传输/写文件/执行升级）+ 升级页`（阶段 2~4）
4. 文档/版本四件套随发版批次（不单独提交）
