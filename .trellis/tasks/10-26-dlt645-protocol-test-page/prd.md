# 645 协议测试页：地址读写 + 按大项分类的命令树 + 预置命令下发

## Goal

698（协议8）已有「协议测试」页：设备操作条（读/写地址、读写时间、连接、超时、循环、发送/停止）
+ 4 个测试分页 + 按 OI 分类的命令树 + 待发队列 + 收发日志 + 底部报文表。**645（协议6）没有对应页面**
——现场想发一条「读 A 相电压」得去「协议组帧」页手选 DI，想知道表地址得自己拼 `13H` 帧。

本任务为 645 建一个**同构的协议测试页**：

1. **读地址**：一个按钮发 `13H`（地址域 `AA×6`），从应答里回填表地址（12 位书写序）；
2. **按协议大项分类的命令树**：电能量 / 最大需量 / 电压电流 / 功率与谐波 / 参变量 /
   结算日 / 记录 / 光伏扩展 …… → 子类 → 具体 DI（叶子上直接下发）；
3. **方便发送特定命令**：读数据（11H）、写数据（14H）、特殊命令（读/写通信地址、广播校时、
   冻结、改速率、改密码、三类清零、读后续），支持勾选多个叶子顺序下发、逐帧判定响应。

## 现状证据（实现必须与此一致）

- 698 页参考实现：`dlt698_test_widget.py`（2045 行：`_build_top_bar` / `_build_left_panel` /
  `_build_center`（`PAGES` + `_ensure_page` + `_build_tree` + `_build_detail`）/ `_build_log_panel` /
  `_build_bottom`（信息表 + 报文表）/ `_send_next` 队列状态机 / `_on_read_address` 回填）
  + `dlt698_test_core.py`（分类库 + 组帧 + `evaluate_response` + `detail_lines`）。
- 645 现有能力（**全部复用，不新增第二份**）：
  - `dlt645_frame_gen.DLT645FrameGenerator`：**唯一** 645 封装（地址线上低字节在前、数据域 +0x33、
    CS、`68…16`）；`generate_frame((REQ, func), field_values, addr)` 走 schema 拼数据域。
  - `dlt645_frame_schema`：`DLT645_CMD_SCHEMA`（11H/12H/13H/14H/15H/16H/17H/08H/18H/19H/1AH/1BH 等，
    含字段定义 `F_HEX/F_DI/F_DI_VALUE/F_PA/F_PWD/F_OPERATOR/F_DATETIME/F_TIME/F_ADDR`）、
    `get_command()`、`build_di_fields()`（按 DI 的 data_type 掩码生成写入字段）、`length_warning()`。
  - DI 表：`dlt645_di.json`（1099 条）+ `dlt645_pv_ext.merge_pv_di_map`（光伏扩展 682 条）
    ⇒ **合并后 1781 条**；字段 `{name, unit, data_type, length}`。
  - DI 大类分布（实测）：`00` 电能量 306、`01` 需量 32、`02` 电压电流 83（含 `02E6` 光伏变量 77）、
    `03` 功率/谐波 572（含 `03E6` 光伏事件 433）、`04` 参变量 237（含上月电能、`04E6` 光伏参数 172、
    `04FF…` LME 1）、`05` 结算日 508、`06` 记录 39、`07` 冻结次数 3、`FF` LME 1。
  - `DLT645Parser.parse()` → `{control, data_length, data, di_code, di_desc, di_unit, di_data_type,
    address_in_data, checksum_valid, fields...}`；表格化用 `protocol_registry.DLT645GuiParser.parse_to_table`
    （含前导 FE 行与偏移位移，**不要另写**）。
  - 断帧：`frame_deframe.frame_length_for("dlt645", buf)`（`L+12`，认前导 FEH、末字节 `16H` 自证）。
- 页面能力位：`protocol_registry.ProtocolSpec.has_test`（当前仅索引 8）；`protocols_with_test()`；
  `main_gui` 有 `_test_placeholder/_test_tab_index/_ensure_test_tab`（单页、只构造 698 控件）。

## Requirements

### R1 纯逻辑层（新 `dlt645_test_core.py`，禁止 import Qt）

- R1.1 **分类库** `catalog() -> Tuple[Category, ...]`：顶层 = 协议大项（DI3 高字节 + 专门的光伏扩展），
  二级 = 子类（DI2，结算日按 20 天分桶），叶子 = 具体 DI（`DiItem(di, name, unit, data_type, length)`）。
  名称一律取 DI 表（`merge_pv_di_map`），**不臆造**；未知 DI2 回落 `NNH 类`。
- R1.2 **命令库** `command_groups()`：直接由 `DLT645_CMD_SCHEMA` 的 `(REQ, func)` 生成，
  按用途分组（通信地址 / 校时与冻结 / 速率与密码 / 清零 / 后续数据），字段定义原样透传给界面。
- R1.3 **组帧**（全部经 `DLT645FrameGenerator`）：`build_read(di, addr)`、`build_write(di, addr, fv)`、
  `build_command(func, addr, fv)`、`quick_read_address()`（13H + `AA×6`）、`quick_write_address(new_addr)`（15H）、
  `build_broadcast_time(when)`（08H + `99×6`）、`build_read_next(di, addr, extra)`。
- R1.4 **响应判定** `evaluate_response(frame, expect) -> dict`：结构/校验 → 方向位 D7 → 功能码 →
  异常位 D6（`decode_err` 位解释）→ DI 回显一致性 → 13H 回填地址 / 08H 无应答。
  返回 `{status, code, summary, lines, address, di, value_text}`；**不冒充成功**（缺失证据给「无法判定」）。
- R1.5 **报文渲染**：`parse_table(frame)`（转 `DLT645GuiParser`）、`detail_lines(frame)`、
  `format_hex`、`parse_hex`、`format_address`；四列格式化抽到共享 `test_page_render.py`
  （698 与 645 共用一份，禁止第二份）。
- R1.6 任何异常转可读 `ValueError`/`dict.error`，**不向 GUI 抛未捕获异常**。

### R2 页面（新 `dlt645_test_widget.py`，仅协议6 可见）

- R2.1 顶部「设备操作」：表地址（12 位书写序，默认 `000000000000`）+「读地址」（回填）+
  「写入地址」输入 +「写入地址」+「广播校时」（系统时间/可编辑）+ 连接状态 + 读取超时 +
  循环发送 + 发送/停止 + 收发计数。**发送中冻结会改变帧的输入**。
- R2.2 左栏「公共参数」：密码权限 PA / 密码 P0P1P2 / 操作者代码 C0~C3（写数据、清零点位共用）
  + 参数落盘与恢复；给出「写入需编程键」提示。
- R2.3 中栏 3 页（`读数据(11H)` / `写数据(14H)` / `特殊命令`）：
  - 每页：筛选框 + 分类树（叶子可勾选）+「当前项」参数面板 + 帧预览（实时）；
  - 读数据页：当前项 = DI + 名称/类型/长度/单位 + 最近一次读到的值；
  - 写数据页：按 `build_di_fields(di)` 动态字段 + `length_warning` 提示；
  - 特殊命令页：树 = 命令分组（命令节点可勾选），参数按 schema 字段动态生成；
  - 「发送」= 勾选的叶子（一个都没勾则用当前选中）顺序下发，**逐帧等响应**再发下一条。
- R2.4 右栏收发日志：`[TX]/[RX]` 整帧 + 响应逐字段明细（`detail_lines`）+ 判定结论；主题可切换。
- R2.5 底部「信息表」（序号/时间/动作/DI/结果/摘要）与「报文表」（时间/方向/长度/hex），
  双击报文行 → 主窗口单帧解析页（`frame_to_single_parse` 信号）。
- R2.6 落盘 `dlt645_testbench.json`（地址/PA/密码/操作者/超时/循环/当前页/筛选），坏文件回落默认；
  `cleanup()` 停定时器、断信号、落盘，**不关共享串口**。

### R3 接线

- R3.1 `protocol_registry`：新增 `has_dlt645_test: bool = False`（索引 6 为 True）+
  `protocols_with_dlt645_test()`；**不动 `has_test`**（698 语义与既有断言不变）。
- R3.2 `main_gui`：新增 `_dlt645_test_placeholder/_dlt645_test_tab_index`（标题「645协议测试」，
  懒加载、创建即隐藏）、`_ensure_dlt645_test_tab()`（注入共享串口 + 主题 + `frame_to_single_parse`）、
  `_on_protocol_changed` 显隐、主题刷新、`_shutdown_threads` 里 `cleanup()`、`_ensure_lazy_tab` 分支。

### R4 测试

- R4.1 新 `test/test_dlt645_testbench.py`：分类库（计数/无重复/名称与 DI 表一致/结算日分桶/光伏分离）、
  命令库（覆盖 schema 的 REQ 命令）、组帧**逐字节 golden**（读 A 相电压 11H、写数据 14H、读地址 13H、
  写地址 15H、广播校时 08H、冻结 16H、事件清零 1BH；CS 自洽 + 解析器 `DLT645Parser` 回读一致）、
  响应判定矩阵（正常/异常应答/方向错/功能码错/DI 不符/13H 回填/08H 无应答）、offscreen GUI
  （树/页切换/帧预览/发送队列状态机/空地址拦截/落盘恢复/主题/cleanup）。
- R4.2 新 `test/test_dlt645_test_tab_wiring.py`：注册表能力（仅协议6）、tab 标题与位置、
  协议显隐、懒加载、串口注入、双击转单帧、主题、收尾不关串口。
- R4.3 两份都登记 `release_check.py`（`GUI_TESTS` / `CORE_TESTS` 各按是否有 Qt 决定；
  参照 698 的两份分别登记）。

## Acceptance Criteria

- A1 协议切到 6 → 出现「645协议测试」页；切其它协议隐藏；切回 6 页面状态还在。
- A2 点「读地址」→ 日志出现 `[TX]` 13H 帧（地址 `AA×6`）；喂入一帧 `93H` 应答（如
  `68 11 22 33 44 55 66 68 93 06 66 55 44 33 22 11 CS 16`）→ 表地址回填为 `112233445566`、信息表记「成功」。
- A3 读数据页选「A相电压 `02010100`」→ 帧预览 `68 <addr> 68 11 04 00 01 01 02 CS 16`；
  喂入 `91H` 应答 → 日志给出 DI 名称、值 `XXX.X V`（按 `decode_value`）、信息表「成功」；
  异常应答（`D1H`，ERR=0x02）→ 信息表「失败」并给出「无请求数据」位解释。
- A4 写数据页选参数类 DI（如 `04000101 日期`）填 `2026-10-26` → 帧预览数据域 = `DI(4)+PA+PWD+C0~C3+日期(4)`；
  回 `94H`（DI 回显）→ 成功。
- A5 特殊命令页「事件清零」→ 数据域 = `PA PWD C0~C3 + FFFFFFFF`；「广播校时」地址 `99×6`；
  「写通信地址」地址 `AA×6` 且数据域 6 字节新地址。
- A6 勾选 3 个 DI 点发送 → 顺序发出 3 帧、每帧等响应再发下一帧；无响应的那条超时后继续；
  停止按钮立即中止并复位。
- A7 底部报文表双击某行 → 主窗口单帧解析页显示该帧。
- A8 `PYTHONIOENCODING=utf-8 python release_check.py --with-gui` → 无新增 FAIL（既有环境红除外）。

## 非目标

- 不改 698 页行为（只把四列格式化抽成共享模块，698 输出逐字不变）。
- 不做 Web 版（Reflex 暂无该页，属既有缺失清单）。
- 不做「645 从站模拟」（已有 645虚拟表页）。
- 不做自动轮询/定时抄读（只做手动 + 循环发送勾选）。
- 不新增/修改 DI 表与组帧口径（`dlt645_di.json` 是生成物；`dlt645_frame_gen` 是唯一封装）。
