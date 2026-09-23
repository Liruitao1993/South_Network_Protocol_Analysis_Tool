# 协议12 模组化终端功能模块接口：组帧接线 + 查询页覆盖 + 收尾

## Goal

把「模组化终端功能模块接口协议」（Q/GDW 模组化终端功能模块接口协议）在本工具里**补成完整可用的一条链路**：
单帧解析 / 批量解析 / 摘要 / 校验 / **组帧** / 预设命令 / 查询页。

上一轮会话已完成主体（解析器、组帧纯逻辑、校验器、注册表 index 12、查询页雏形、46 项测试），
但**组帧页未接线**（用户明确要求「组帧能力」）、查询页只覆盖 APDU/控制码/DT 名称、
解析器有若干文档对齐缺陷（详见 Background）。本轮补齐这些缺口并收尾提交。

**协议文档（唯一权威）**：`协议文档/12.模组化功能协议/模组化终端功能模块接口协议.md`
（1136 行，已由 anydoc 从同名 .docx 转出；docx 原文件同目录保留）。

## Background（已确认事实）

### 已完成（工作区未提交）

| 文件 | 状态 | 内容 |
| --- | --- | --- |
| `协议文档/12.模组化功能协议/模组化终端功能模块接口协议.md` | 新增（未跟踪） | 1136 行 MD（anydoc 转出） |
| `modular_iface_parser.py` | 新增（未跟踪，689 行） | `ModularIfaceParser`：链路层 + 8 类 APDU + DT + `calc_fcs`/`data_total_len`/`decode_dt`/`is_frame` |
| `modular_iface_frame_gen.py` | 新增（未跟踪，~230 行） | 纯逻辑组帧：`build_frame`/`build_info_frame`/`build_ack_frame`/`build_nak_frame`/8 类 APDU builder/`FRAME_TEMPLATES`/`build_from_template`/A-XDR 编码助手 |
| `validator/modular_iface_validator.py` | 新增（未跟踪） | `ModularIfaceValidator` |
| `test/test_modular_iface.py` | 新增（未跟踪，46 项 PASS） | 注册表/DT/组帧→解析闭环/模板/校验 |
| `protocol_registry.py` | 已改 | index 12 `ProtocolSpec`（`parser_key="modular"`、`lookup_kind="modular"`、`extract_strategy="modular"`、`frame_gen_mode=None`、`preset_mode=None`） |
| `parser_registry.py` | 已改 | `"modular": ("modular_iface_parser", "ModularIfaceParser")` |
| `main_gui.py` | 已改 | `_create_modular_iface_lookup_content` 查询页、`_extract_modular_frames` 批量提取、CHANGELOG 1.23.57 |
| `release_check.py` | 已改 | `CORE_TESTS` 含 `test/test_modular_iface.py` |
| `reflex_web/reflex_web/landing_web.py` | 已改 | 首页协议表新增「模组化终端功能模块接口」 |
| `test/test_protocol_registry.py`、`test/test_web_landing.py`、`validator/__init__.py`、`AGENTS.md` | 已改 | 对拍与文档同步 |

`APP_VERSION = "1.23.57"`、`BUILD_DATE = "2026-09-22"`。

### 本轮研究发现的缺口（按文档逐条核对）

**G1 组帧页未接线（用户明确要求的「组帧能力」）**
- `protocol_registry.py` index 12 的 `frame_gen_mode=None` ⇒ 组帧页与预设页对该协议隐藏（`main_gui.py:4194-4210` 按 `spec.frame_gen_mode is not None` 决定可见性）。
- `frame_gen_widget.py`（4380 行）是 4 模式单文件复用：`set_protocol_mode` 白名单硬编码 `("south","gdw","dlt698","dlt645")`，模式分派点约 12 处。
- `modular_iface_frame_gen.py` 的组帧能力**已完整**，缺的只是 UI 接线。

**G2 查询页覆盖不足**
现状只列 APDU 名称表 / 控制码 / 通用 DT 名称。文档里尚未进入查询页的内容：
- **附录 C**（DTA1=0H）：12 条信息类的完整 ASN.1 定义（0000 模块信息 / 0001 链路协商信息 / 0002 协议版本 / 0003 电源状态 / 0004 文件传输状态 / 0100 时钟 / 0200 硬件初始化 / 0201 参数初始化 / 0202 数据初始化 / 0203 文件传输）
- **附录 G**（遥信脉冲）：DT 4000 遥信状态、4001 上一次脉冲计数和时间、4002 脉冲计数及统计时间、4100 遥信脉冲功能配置、4101 遥信防抖时间
- **附录 J**（控制模块）：DT 7100 继电器输出模式、7101 继电器输出脉冲宽度
- **附录 K**（模拟量采集）：DT 8000 模拟量采样
- **附录 L**（回路状态巡检）：DT 9000/9001/9002
- **附录 M**：物理单位枚举 75 个具名代码 + 254/255（Scaler_Unit 的单位表）
- **附录 D/E/F/G/J/K/L**：7 张设备子接口表（虚拟通道号/接口形式/功能定义）
- **附录 B**：VID=0x3C93、PID=0xFFFF

**G3 解析器文档对齐缺陷（研究时发现，非用户报障）**
1. `modular_iface_parser.py` `parse()` 收尾写 `self._rows(rows, {...} if False else None)` —— **死代码**，meta 恒为 `None`，`valid`/`fcs_ok` 永不外传；`_rows(self, rows, _meta=None)` 的 `_meta` 也未使用。
2. `DAR_NAMES`（21 条：硬件故障/暂时故障/…）与文档 **§6.3.8 表11 矛盾**：表11 只定义 4 个值 —— 成功(0) / 拒绝读写(1) / 信息类未定义(2) / 其它(255)。现表无文档依据（形似其它协议的 DAR）。
3. `decode_dt` 只命名 DTA1=0 的 DTB；模块信息类（4000/7100/8000/9000…）无法命名。
4. **Scaler_Unit（表12）未解码** ⇒ 附录 M 单位表无从体现。表12：`Scaler_Unit ∷= SEQUENCE { 换算 integer, 单位 ENUMERATED }`，换算 = 以 10 为底的指数。
5. `get_summary` 的 `dt_off` 判断有冗余分支（`if apdu_tag in (130,131) or apdu_tag == 4: dt_off = 1` 之后又 `if apdu_tag == 3: dt_off = 1`），结果正确但语义含糊。

**G4 批量摘要落兜底分支**
`main_gui.py:9018 _get_summary_from_table_data` 无 `proto == 12` 分支 ⇒ 落到 `else`「取前 4 个非冗余字段」，批量摘要会输出「68H」「8」这类无意义内容。

**G5 打包缺项**
`南网协议解析工具.spec` 的 `hiddenimports` 无 `modular_iface_parser` / `modular_iface_frame_gen` / `validator.modular_iface_validator`（`validator.make_validator` 走 importlib，打包器静态分析看不到）。

**G6 收尾未做**
- 无预设命令（`preset_mode=None`；`preset_buttons.py` 只认 south/gdw/dlt698/dlt645）。
- 工作区遗留临时文件：`test/_tmp_dump_tables.py`、`test/_tmp_parse_user_ed.py`、`test/_tmp_probe_tcp11.py`、`test/_tmp_scan_log_ed.py`、`test/_tmp_scan_log_ed2.py`、`test/_tmp_scan_out.txt`、`test/_tmp_tcp_out.txt`、`test/out.txt`、`test/out2.txt`、`test/out3.txt`、`test/out5.txt`、`test/out6.txt`。
- 工作区混有**另外两条**未提交改动线，与本任务无关，提交时须分开说明：
  - `gdw10376_parser.py`（协议7 从节点芯片ID 整块小端倒序解析）
  - `serial_tool_widget.py` + `test/test_serial_tool_widget.py`（串口工具命令「次数」列，1.23.57 部分）

### 文档关键定义（供实现与测试引用）

- **链路层帧**：`68H | L(2B, LE, bit0~11=数据域字节数, bit12~15 保留) | C(2B, LE) | 数据域(L) | FCS(2B, LE) | 16H`；整帧 = L + 8（§5.2.1~5.2.5）。
- **控制域低字节**：bit7=DIR（0 终端发出 / 1 模块发出）、bit6=PRM（0 模块发起 / 1 终端发起）、bit5~0=控制码；高字节 = FID 帧序号（响应与请求一致）。表1 组合意义 4 种；表2 控制码 00H 确认 / 01H 否认 / 02H 信息 / 其他保留。
- **否认帧数据域**：错误信息码 BIN 2 字节（表3）。确认帧无数据域。信息帧数据域 = 一个完整 APDU。
- **FCS**：附录 A，`fcstab` 标准 PPP 表 + `GOODFCS=0xF0B8`（与 `crcmod` 的 `x-25` 同族）。
- **字节序**：§5.1「传输顺序为低位在前，高位在后；低字节在前，高字节在后」。
- **DT**：表22，bit15~11=DTA1、bit10~8=DTA2、bit7~0=DTB。§7.1：DTA1 0H=通用，1~N 对应功能模块；DTA2 0H 只读 / 1H 读-写 / 2H 只写。
- **APDU**：表13 CHOICE —— [1] LinkRequest、[2] GetRequest、[3] SetRequest、[4] ReportNotification、[129] LinkResponse、[130] GetResponse、[131] SetResponse、[132] ReportResponse。
- **Get-Result**：CHOICE `[0] DAR` / `[1] Data`；`A-ResultNormal ∷= SEQUENCE { 信息类标识 DT, 读取结果 Get-Result }`。
- **DAR**：表11 只有 4 个值。
- **date_time**（表6）：year(long-unsigned) + month/day_of_week/day_of_month/hour/minute/second(unsigned) + milliseconds(long-unsigned)；`FFFFH`/`FFH` 表示无效；day_of_week 0=周日。
- **文档内部矛盾（需记录，不臆造）**：§6.3.9 表12 写「单位……见附 录 L」，但物理单位枚举实际在**附录 M**（附录 L 是回路状态巡检模块）；附录 K.2/L.2 互相引用「见 K.3」。按附录 M 实现，并在 AGENTS.md 记录该矛盾。

## Scope（本轮已与用户确认）

- **桌面端补齐缺口**（不含 Web 端的解析/查询/组帧实现）。
- **附录覆盖取核心范围**：附录 C 通用信息类 + 正文 §7 的 DTA1 分类 + 模块专属信息类（附录 G/J/K/L）+ 附录 M 物理单位 + 附录 D~L 设备子接口表 + 附录 B。附录 F/I/H 无信息类定义（只有子接口与字节流说明），按文档原样记录。
- 不含：协议12 的虚拟表从站模拟、TCP 监控协议识别、串口工具协议下拉（这三处如需支持另立任务评估）。

## Requirements

### R1 组帧能力（用户显式要求）

- AC1.1 协议12 在 GUI 出现「帧生成」与「预设命令」标签页（`frame_gen_mode="modular"`；预设 Tab 现状由 `frame_gen_mode is not None` 决定可见性）。
- AC1.2 组帧页新增 modular 模式，提供：命令/模板选择、控制域编辑（DIR、PRM、FID）、数据域构造（按所选 APDU 生成或直接填 hex）。
- AC1.3 生成结果符合文档帧格式（`68…16`、L=数据域长度、整帧=L+8、FCS 覆盖 L+C+Data）。
- AC1.4 实时预览用 `ModularIfaceParser` 回读自校验，字段与单帧解析页一致。
- AC1.5 组帧页串口回包解析在 modular 模式下走 `ModularIfaceParser`（不得落到国网/南网解析器）。
- AC1.6 切换协议不能让 modular 模式状态污染其它模式（回到其它协议后行为与改动前一致）。
- AC1.7 「生成帧」结果可加入预设命令与测试方案（沿用既有按钮行为）。

### R2 查询页覆盖（核心范围）

- AC2.1 查询页分「控制码 / APDU / 通用信息类(附录C) / 模块信息类(附录G,J,K,L) / 物理单位(附录M) / 设备子接口(附录D~M) / 厂商标识(附录B)」分组呈现，可搜索、显示匹配/总条数。
- AC2.2 附录 C 的 12 条信息类**逐条与文档对拍**（DT 码、名称、ASN.1 定义文本）。
- AC2.3 模块信息类 11 条逐条与文档对拍。
- AC2.4 物理单位按文档表31 逐条对拍（代码 1~75 + 254 + 255；不含保留行）。
- AC2.5 设备子接口表按附录 D/E/F/G/J/K/L 逐条对拍。
- AC2.6 DT 命名统一由一个数据模块提供（不再有第二份 DT 名称表）。

### R3 解析器文档对齐

- AC3.1 `parse()` 的 meta 不再是死代码：能如实给出 `valid` / `fcs_ok`（缺字段不得静默丢失）。
- AC3.2 `DAR_NAMES` 收口到表11 的 4 个值，并附文档出处注释。
- AC3.3 `decode_dt` 能命名附录 C 与附录 G/J/K/L 覆盖的 DTB（模块信息类也要有名称）。
- AC3.4 Scaler_Unit 按表12 解码（换算指数 + 单位代码 → 单位名/量），单位名取自附录 M。
- AC3.5 `get_summary` 的冗余判断收口；摘要内容不退化（现有 46 项测试的摘要断言保持通过）。
- AC3.6 **合法帧的解析输出逐行不变**（除上述新增/修正的行外），FCS 校验通过/失败判定不变。
- AC3.7 FCS 实现与文档附录 A 的 `fcstab`/`GOODFCS` 语义一致（用文档算法作独立 oracle 交叉验证）。

### R4 批量摘要

- AC4.1 协议12 有专属摘要分支，输出「方向 + 控制码 + APDU + 信息类名称」，不再走兜底「前 4 个非冗余字段」。
- AC4.2 摘要对 ACK/NAK 帧也给可读结果（不输出空串）。

### R5 预设命令

- AC5.1 预设命令页支持 modular 模式，数据落在独立文件（不与 NW/GW/DLT698/DLT645 四个文件混写）。
- AC5.2 首次无数据文件时给出可用种子命令（至少：读模块信息、读链路协商信息、读时钟、链路协商请求、ACK），且能正常组帧与解析。
- AC5.3 预设条目能被重复打开（`AppConfig` 往返不丢字段）。

### R6 打包与文档

- AC6.1 `南网协议解析工具.spec` 的 `hiddenimports` 补齐 3 个模块（解析器/组帧/校验器），使其可被打包器静态发现。
- AC6.2 `AGENTS.md` 同步：§1 协议表、§2/§3 文件清单、§5 新增协议小节（文档路径 + 已实现范围 + 文档内部矛盾）、§7 测试清单、§8 新增陷阱条目（本协议契约与本次修复）、§10 版本摘要。
- AC6.3 `main_gui.py:CHANGELOG` 新增条目；`APP_VERSION` 递增；`BUILD_DATE` 更新为编译日期。
- AC6.4 `python release_check.py --sync-iss` 同步 Inno Setup 版本号。
- AC6.5 清理本任务期间产生的临时文件（`test/_tmp_*`、`test/out*.txt`），不得把调试产物留在仓库。

### R7 测试与回归

- AC7.1 扩展 `test/test_modular_iface.py` 覆盖：附录 C/模块信息类/物理单位/子接口表的**逐条对拍**、DAR 表11、Scaler_Unit 解码、`parse()` meta、FCS 文档 oracle 交叉验证、组帧页 offscreen 冒烟、查询页分组、批量摘要。
- AC7.2 组帧页测试走真实链路（`FrameGenWidget` offscreen + `set_protocol_mode("modular")` + 点「生成帧」），不只直调私有方法。
- AC7.3 既有回归全绿：`test/test_modular_iface.py`、`test/test_protocol_registry.py`、`test/test_web_landing.py`、`test/test_dlt645_frame_gen_gui.py`（组帧页其它模式不得被改坏）、`test/test_serial_worker_framing.py`。
- AC7.4 `python release_check.py` 无新增 FAIL。

## Out of Scope

- Web 端（`reflex_web/`）的协议12 解析/查询/组帧实现：本轮明确延后（用户选择「桌面端补齐缺口」）。**遗留须记入 AGENTS.md 与任务备注**，避免误以为是已支持。
- 协议12 虚拟表从站模拟、TCP 监控自动识别/协议下拉新增、串口工具协议下拉：另立任务评估。
- 附录 F/I/H 的「字节流传输」实现（文档本身只给子接口，无信息类）。
- 修改文档原文（含 §6.3.9/附录 K.2/L.2 的引用矛盾）——只在 AGENTS.md 记录。
- 打包产物实际构建（只做 spec 清单核对与 self-check）。

## Open Questions

无阻塞项。3 项范围决策已与用户确认（见 Scope）。文档内部两处引用矛盾按「以实际章节为准 + 记录不臆造」处理。
