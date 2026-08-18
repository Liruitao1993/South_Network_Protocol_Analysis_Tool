# 南网协议解析工具

[![Version](https://img.shields.io/badge/version-1.14.3-blue)]()
[![Python](https://img.shields.io/badge/Python-3.8%2B-brightgreen)]()
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()

一个面向电力通信现场调试的多协议解析工具，基于 Python / PySide6 开发，支持 12 种电力通信协议，覆盖单帧解析、批量解析、协议校验、帧生成、串口通信、测试方案、Lua 脚本、实时监控与 TCP 抓包等工作流。

当前版本为 `1.14.3`，版本号与编译日期见 `main_gui.py` 中的 `APP_VERSION` 与 `BUILD_DATE`。

## 功能总览

| 模块 | 说明 |
| --- | --- |
| 单帧解析 | 输入十六进制报文，按协议分层解析，点击解析行联动高亮输入框对应字节 |
| 批量解析 | 从文件或剪贴板导入多帧报文，自动提取完整帧并导出 JSON / CSV / Excel |
| 协议校验 | 覆盖起始符、长度域、校验和与 CRC，逐项展示通过 / 失败 / 警告 |
| 表格复制 | 解析结果、批量结果、监控器与 TCP 监控表格支持右键复制及 Ctrl+C |
| 帧生成 | 南网、国网、698.45 组帧模板，支持预设命令一键填充 |
| 串口通信 | 串口参数配置、帧发送、实时接收解析与日志窗口 |
| 测试方案 | 测试项 CRUD、顺序发送、超时匹配、结果记录与 Excel 报告导出 |
| Lua 脚本 | 测试流程中嵌入可编程逻辑，支持条件分支、循环遍历、数据解析与变量共享 |
| 报文对比 | 双报文字节级 / 字段级对比，支持差异高亮、人话解读与报告导出 |
| 报文工具 | ASCII / HEX 转换、DLT645 偏移、字节逆序、Pn/Fn 转换、CRC/校验和计算 |
| 实时监控器 | 南网新一代 / 国网新一代串口报文实时监控、自动组帧、过滤与 CSV 记录 |
| TCP 监控 | 基于 scapy 的 TCP 抓包、流重组与南网新一代 / 国网新一代自动识别解析 |
| 档案与拓扑 | 南网 / 国网协议档案导入导出、拓扑组网统计 |
| 查询页 | DI、AFN、DLT645 DI、OBIS、PLC RF 命令字、新一代业务标识、HDC 1.0 报文 ID 查询 |
| 多端界面 | PySide6 GUI、实验性 Reflex Web |
| 主题与字体 | 5 套主题与字体设置，支持配置持久化 |
| 系统集成 | 系统托盘、全局热键、剪贴板报文检测、Notepad++ 集成、单实例、命令行解析、文件右键菜单与开机自启 |

## 支持协议

工具支持 12 种电力通信协议，下拉框索引即协议编号：

| 索引 | 协议 | 标准号 | 字节序 | 校验 |
| --- | --- | --- | --- | --- |
| 0 | 南网协议 | Q/CSG1209021-2019 | 小端 | 8 位位组算术和 |
| 1 | PLC RF 协议（万胜海外） | 万胜 V1_04 | 大端 | 累加和 & 0xFF |
| 2 | HDLC/国网DLMS | IEC 62056-46 | 大端 | CRC-16/FCS（CCITT） |
| 3 | DLMS-APDU（国网） | IEC 62056-46 | 大端 | 无 |
| 4 | DLMS Wrapper 裸报文 | IEC 62056-46 | 大端 | 无 |
| 5 | DLMS-APDU 裸报文 | IEC 62056-46 | 大端 | 无 |
| 6 | DLT645-2007 电表协议 | DL/T 645-2007 | BCD，低字节在前 | 累加和 & 0xFF |
| 7 | 国网协议 | Q/GDW 10376.2-2024（含福建增补 AFN 50H~56H） | 小端 | 8 位位组算术和 |
| 8 | 698.45 协议 | DL/T 698.45-2017 | 小端 | CRC-16（crcmod `x-25`） |
| 9 | 新一代载波协议（通感一体化） | 通感一体化宽带载波通信规约 | 小端 | CRC-32（MAC 帧） |
| 10 | 国网新一代双模通信互联互通 | 国网新一代双模通信互联互通技术规范 | 小端 | CRC-32（MAC 帧） |
| 11 | HDC 1.0 双模互联互通 | Q/GDW 12087.42-2020 | 小端（MAC 地址大端） | CRC-24（FC/PB）+ CRC-32（MAC） |

## 快速开始

### 环境要求

- Windows 优先，支持 UTF-8 / GBK 中文路径
- Python 3.8+
- TCP 监控需要安装 `scapy`，Windows 下还需要安装 npcap

### 安装依赖

```bash
pip install pyside6        # GUI 必需
pip install crcmod         # 698.45 协议 CRC 校验（1.7.0 起）
pip install lupa           # Lua 脚本引擎（1.8.1 起，可选）
pip install openpyxl       # Excel 测试报告（可选）
pip install scapy          # TCP 流量监控（可选，Windows 需 npcap）
pip install reflex         # Reflex Web 版（实验性）
```

> `lupa` 未安装时 Lua 脚本功能不可用，其余功能不受影响；`scapy` 或 npcap 未就绪时，TCP 监控标签页会给出安装提示。

### 运行

```bash
# PySide6 GUI 版（主入口）
python main_gui.py

# Reflex Web 版（实验性）
python reflex_web/run_app.py
```

**Reflex Web 版组帧**：南网(0)/国网(7)/698.45(8) 三种协议组帧与 GUI 完全对齐——预定字段（uint/enum/bytes/ascii/bcd/oi/oad_list/list/sub_fields 按类型分派）、自定义模板（含校验和回填）、698.45 A-XDR 数据编辑器；实时回读解析预览；预设命令按钮（NW_command.json / GW_command.json）一键填入与保存。启动前先编译前端：`cd reflex_web && reflex export --frontend-only --env prod --no-zip`，再 `python reflex_web/run_app.py`。

### 部署到目标机器

有两种方式将 Reflex Web 版部署到没有 Python 环境的目标机器：

**方式一：内嵌 Python（推荐，零安装）**

构建包含 Python 运行时的部署目录，目标机器无需安装 Python，解压即用：

```bash
python reflex_web/build_embedded_deploy.py --python-version 3.12
# 输出: dist/reflex_web_embedded/
```

把 `dist/reflex_web_embedded/` 整个目录复制到目标机器，运行 `start_web.cmd`（Windows）或 `./start_web.sh`（Linux）即可。

**方式二：UV 虚拟环境（需要目标机器有 Python）**

构建依赖虚拟环境的部署目录，目标机器需要安装相同版本的 Python：

```bash
python reflex_web/build_offline_deploy.py --python-version 3.12
# 输出: dist/reflex_web_offline/
```

详细说明见 [`reflex_web/离线部署.md`](reflex_web/离线部署.md)。

### 打包 exe

项目当前提供 `南网协议解析工具.spec`，打包时请先确认 `main_gui.py` 中的 `BUILD_DATE` 已更新为当前日期：

```bash
pip install pyinstaller
pyinstaller 南网协议解析工具.spec --noconfirm
```

生成的 exe 位于 `dist/南网协议解析工具.exe`。新增需打包的数据文件时，需要同步检查 spec 的 `datas` 配置。Reflex Web 版另有 `reflex_web/reflex_web_exe.spec`。

> 当前主程序 spec 未显式声明 `scapy`。如需将 TCP 监控功能打包进 exe，请先在 `南网协议解析工具.spec` 中补充 `scapy` 相关 hidden imports，并确保目标机器安装 npcap。

## 使用说明

### 单帧解析

1. 顶部下拉框选择协议类型
2. 在「输入报文」文本框粘贴十六进制报文（支持带空格 / 无空格混合）
3. 点击「解析报文」
4. 下方表格显示分层解析结果，点击解析行会高亮输入框中的对应字节

解析 HDLC 帧后，可双击 `DLMS APDU` 行打开深度解析窗口，支持 Get / Set / Action 等 APDU 类型与 BER-TLV 递归解析。

国网新一代（索引 10）与 HDC 1.0（索引 11）可选择解析级别（自动识别 / FC+PB / 仅FC / 仅MAC / 仅PB / FC+MAC / 应用层）与通道（PLC 载波 / HRF 无线）；新一代载波（索引 9）另支持 FC+eFC 级别与 ED 监控包装剥离。

### 批量解析

切换到「批量解析」标签页：

- 从文件加载或剪贴板粘贴
- 自动从混杂文本中提取完整帧
- 批量处理并导出 JSON / CSV / Excel
- 新一代载波协议支持监控日志前缀剥离与业务摘要
- 国网新一代 / HDC 1.0 支持日志前缀剥离与业务摘要

### 实时监控器

「监控器」标签页在协议 9（南网新一代）与协议 10（国网新一代）下显示：

- 串口原始字节流自动组帧，支持静默间隔组帧与监控解帧模式
- 南网新一代使用 `ED..EE` 包装，国网新一代使用 `96..16` 包装
- 左侧帧列表支持过滤、暂停、自动滚动、清空、CSV 记录与日志目录打开
- 右侧展示完整解析表格与原始 HEX，双击帧可送入单帧解析页

### TCP 流量监控

「TCP监控」标签页基于 scapy 实现：

1. 选择网卡并输入 BPF 过滤条件，例如 `tcp port 8080` 或 `host 192.168.1.1`
2. 点击「开始抓包」
3. 上方 TCP 流列表按四元组实时汇总包数、字节数与最新时间
4. 选中一条流后，下方展示按监控封装格式重组切分出的应用层帧
5. 选中帧后自动调用南网新一代或国网新一代解析器，右侧显示解析结果

TCP 监控支持流关注、表格复制、暂停刷新、CSV 实时记录与历史 CSV 加载。

### 系统集成与命令行

GUI 版提供 Windows 系统集成能力：

- 关闭主窗口默认最小化到系统托盘，托盘左键单击可显示 / 隐藏主窗口
- 全局热键默认 `Ctrl+Alt+X`，复制十六进制报文后按下即可弹出解析结果
- 开启「剪贴板报文自动检测」后，在任意软件中复制十六进制报文会自动弹出解析提示框，自动识别协议后可直接转入解析
- 可注册 Notepad++ 集成：在 Notepad++ 中选中报文并按 Ctrl+C 复制，右键「用协议解析工具解析」或运行命令即可解析
- 程序支持单实例，重复启动会把命令行参数转发给已运行实例
- 在「配置 → 主题与字体」的「系统集成」面板可配置开机自启、关闭行为、热键与文件右键菜单
- 注册文件右键菜单后，`.log` / `.txt` / `.hex` / `.bin` 文件可右键选择协议直接解析

剪贴板提示框与热键 / 命令行解析弹窗支持切换协议；南网新一代 / 国网新一代报文还可选择解析级别、PB 帧类型，并自动剥离 `ED..EE` 监控包装头。

命令行示例：

```bash
# 按协议索引直接解析十六进制报文
python main_gui.py --parse "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16" --protocol 0

# 按协议名称解析文件中的报文
python main_gui.py --file sample.log --protocol 国网新一代

# 启动后最小化到托盘
python main_gui.py --minimized

# 读取剪贴板中的十六进制报文并直接弹出解析结果
python main_gui.py --clipboard
```

### 报文对比

切换到「报文对比」标签页：

- 双报文字节级对比与字段级语义对比
- 差异高亮、人话解读、忽略校验和 / 序列号等选项
- 导出对比报告

### 报文工具

「报文工具」标签页提供协议调试常用功能：

- ASCII / HEX 双向转换
- DLT645 偏移（±0x33H）
- 字节逆序
- 报文与 Pn/Fn 转换
- CRC-16 / 24 / 32 与校验和计算
- HEX 与 bitstring 转换

### 帧生成与预设命令

「协议组帧」与「预设命令」标签页在协议 0（南网）、协议 7（国网）与协议 8（698.45）下显示：

- 按字段模板填写参数
- 支持预设命令一键填充
- 生成帧后可直接通过串口发送

### 测试方案

切换到「测试方案」标签页：

- 添加发送帧、后台监听、纯等待、Lua 脚本等测试项
- 配置超时与匹配规则
- 顺序执行并记录结果，支持导出 Excel 测试报告

Lua 脚本使用说明见 [`docs/Lua脚本使用说明.md`](docs/Lua脚本使用说明.md)。

### 查询、档案与拓扑

- 查询页支持南网 DI、国网 AFN、DLT645 DI、OBIS 码、PLC RF 命令字、新一代业务标识与 HDC 1.0 报文 ID 查询
- 档案管理与拓扑信息仅在南网 / 国网协议下显示
- 支持档案导入导出与拓扑组网统计

## 项目结构

```text
main_gui.py                  # PySide6 GUI 主程序，应用入口
protocol_parser.py           # 南网协议解析器
gdw10376_parser.py           # 国网协议解析器
gdw_eb_di_lookup.py          # 本地通信模块扩展协议 EB 数据标识查询（附件1）
plc_rf_parser.py             # PLC RF 协议解析器
hdlc_parser.py               # HDLC / DLMS 解析器
dlms_deep_parser.py          # DLMS APDU 深度解析
dlt645_parser.py             # DLT645-2007 解析器
dl_t698_45_parser.py         # 698.45 链路层解析器
dl_t698_45_apdu_parser.py    # 698.45 APDU 解析器
dl_t698_45_axdr.py           # A-XDR 编解码
dl_t698_45_data_decode.py    # 698.45 APDU 数据内容业务解码（1.14.1 起）
csg_new_gen_parser.py        # 新一代载波协议解析器
csg_new_gen_cmd_payloads.py  # 新一代载波应用层命令载荷
gw_new_gen_parser.py         # 国网新一代双模解析器
gw_new_gen_mme_parser.py     # 国网新一代 MME 管理消息解析
gw_new_gen_cmd_payloads.py   # 国网新一代应用层命令载荷
hdc10_parser.py              # HDC 1.0 双模互联互通解析器（Q/GDW 12087.42-2020）
hdc10_mme_parser.py          # HDC 1.0 MME 网络管理消息解析
frame_diff_engine.py         # 协议感知报文对比引擎
send_frame_lib.py            # 南网帧生成
gdw_send_frame_lib.py        # 国网帧生成
dl_t698_45_frame_gen.py      # 698.45 帧生成
frame_gen_widget.py          # 协议组帧组件
preset_buttons.py            # 预设命令组件
test_plan_widget.py          # 测试方案组件
lua_script_engine.py         # Lua 脚本引擎
serial_worker.py             # 串口通信线程
monitor_widget.py            # 实时监控器组件
monitor/tcp_monitor.py       # TCP 流量监控组件
system_integration/          # 系统集成：托盘 / 热键 / 剪贴板 / Notepad++ / 单实例 / 右键菜单
message_tool_widget.py       # 报文工具组件
theme_settings.py            # 主题与字体设置
enhanced_export.py           # 增强导出功能
reflex_web/                  # Reflex Web 版（实验性）
test/                        # 测试脚本目录（所有 test_*.py 统一存放）
validator/                   # 协议校验引擎（含 hdc10_validator.py 等）
monitor/frame_monitor.py     # 串口实时帧监听组件
report/excel_reporter.py     # Excel 测试报告
templates/test_templates.py  # 测试模板库
docs/Lua脚本使用说明.md       # Lua 脚本使用文档
南网协议解析工具.spec          # PyInstaller 打包配置
```

## 测试

项目无正式测试框架，`test/*.py` 为独立脚本，直接运行（命令在项目根执行）：

```bash
python test/test_csg_new_gen.py            # 新一代载波协议
python test/test_gw_new_gen.py             # 国网新一代双模协议
python test/test_gdw_fujian.py             # 国网福建增补规约 + EB 数据标识（1.14.0 起）
python test/test_hdc10.py                  # HDC 1.0 双模互联互通协议
python test/test_dl_t698_45.py             # 698.45 协议
python test/test_dl_t698_45_data_decode.py # 698.45 APDU 数据内容业务解码（1.14.1 起）
python test/test_dl_t698_45_fujian.py      # 698.45 福建简化698 List 结构（1.14.2 起）
python test/test_hdlc.py                   # HDLC 帧
python test/test_plc_rf.py                 # PLC RF
python test/test_lua_engine.py             # Lua 脚本引擎
python test/test_sack_fix.py               # SACK 帧解析
python test/test_diff_engine.py            # 报文对比引擎
python test/test_monitor_deframe.py        # 监控解帧
python test/test_monitor_plc2_deframe.py   # PLC2 解帧
python test/test_gw_monitor_summary.py     # 国网新一代监控摘要
python test/test_sack_fix.py               # SACK 帧解析
python test/test_ed_fallback_fix.py         # ED..EE 监控帧非法回退修复（1.11.1 起）
python test/test_dl_t698_45_fujian.py      # 698.45 福建简化698 解析
python test/test_theme_settings.py         # 主题与字体设置
```

> **约定**：所有测试文件一律放入 `test/` 目录（项目根目录禁止新增 `test_*.py`）。新测试文件头需 `import _path_setup`（详见 `test/_path_setup.py` 说明与 `AGENTS.md` §7）。

## 开发文档

- [`AGENTS.md`](AGENTS.md)：AI Coding Agent 上手指南，包含架构、协议映射、字节序与校验约定、开发原则与变更日志
- [`docs/Lua脚本使用说明.md`](docs/Lua脚本使用说明.md)：Lua 脚本功能使用说明与 API 参考
- [`.trellis/workflow.md`](.trellis/workflow.md)：Trellis 开发工作流与任务规范

## 更新记录

### 1.14.3 — 2026-08-19

#### 协议 8（698.45）EB030307 过零NTB值上行数据解析

- ACTION-Response NormalList 兼容「数据个数」前缀（DAR 后 `01`=数据个数 + octet-string 数据），修复 `0x81 未知类型` 报错
- EB030307 字段 schema：数据开始时间/边沿类型/数据周期/数据点数/NTB 值数组（10 组相线1/2/3 NTB 值，uint32 40ns）
- bcd_time 可读化：`2026-08-14 14:42:00` 格式
- 新增 2 项测试（用户真实上行帧 + 表格展示）；`test_dl_t698_45_fujian.py` 增至 12 项

### 1.14.2 — 2026-08-19

#### 协议 8（698.45）福建简化698 解析

- 新增 SET/ACTION 的 Request/Response List 分支（choice=0x02：PIID + count + SEQUENCE OF {OAD/OMD, Data/DAR}），支持福建「本地通信模块扩展协议」V3.42 698 承载格式（EB030110 台区识别、EB030307 过零NTB 等）
- REPORT-Notification/Response 带 count 结构（对齐福建示例 `88 01 00 01 ...` / `08 01 00 01 ...`）
- EB 数据标识名称（gdw_eb_di_lookup 57 项）+ 数据内容字段解码（enum/uint/bcd/bs8/list，无 schema 保留原始 hex）
- 修复 EB 数据内容多字节 uint 字节序：按文档「645 减33逆序」规则为大端（识别时长 5 分钟正确显示，此前误读 1280）
- 新增 `test/test_dl_t698_45_fujian.py`（9 项测试全过）

### 1.14.1 — 2026-08-17

#### 协议 8（698.45）APDU 数据内容业务解码

- 新增 `dl_t698_45_data_decode.py`：按对象属性格式解码 A-XDR 数据为业务值——电能量数组（kWh 换算+费率展开）、最大需量数组（值@发生时间）、分相电压/电流/功率/谐波（A/B/C 相+单位）、单值数据变量；Scaler_Unit 换算按 10^scaler，单位码映射表
- APDU 解析器（GET-Response/SET-Request/REPORT-Notification）新增「数据业务」键，不破坏原始 A-XDR 结果；REPORT-Notification Normal 补齐 OAD 解析
- GUI 表格「数据业务」按项展开显示（如 `总: 1234.567 kWh` / `A相: 220.5 V`）
- 修复 DLT69845Validator 长度域一致性公式（L=帧长-2，文档附录 H.1 例证）
- 新增 `test/test_dl_t698_45_data_decode.py`（10 项测试全过）

### 1.14.0 — 2026-08-17

#### 国网协议（索引 7）新增福建增补规约 + EB 数据标识扩展

**福建增补规约解析与组帧**（附件3：1376.2集中器本地通信模块接口协议【福建增补】V1.4）：

- **AFN=50H~56H 全功能覆盖**：50H 确认/否认、51H 初始化、52H 数据转发（F1 透明转发 / F2 任务队列智能补采 / F3 本地定时 / F11 并发抄表福建 / F12 清空队列）、53H 查询数据（F1 参数配置 / F2 主节点地址 / F4 厂商版本 / F5 信道信息 / F6 串口参数 / F10 模式切换）、55H 控制命令（F1 设置地址 / F2 允许禁止上报 / F3/F4 广播 / F6 注册 / F7 结束任务 / F8/F18 预告执行 / F9 预告抄读 / F10 模式切换 / F11~F13 速率协商）、56H 主动上报（F1 注册信息 / F2 事件内容 / F3/F13 抄读请求 / F4/F14 响应报文 / F5 信道延时 / F6 广播完成 / F15 带任务信息上报）
- **帧结构自动识别**：福建增补信息域 R（保留5B+序列号1B，上行含事件标志）与地址域 A（A1+A3 12B 无中继）与 2024 国网自动区分
- **组帧支持**：schema 新增 27 个 (AFN,Fn) 定义，`generate_frame` 对增补 AFN 自动切换 R/A 结构；报文长度自动计算

**本地通信模块扩展协议 EB 数据标识深度解析**（附件1 V3.31）：

- 新增 `gdw_eb_di_lookup.py`（40+ 数据项映射：事件/台区识别/设备基础/时钟/档案/任务队列等）
- 645 帧内嵌 EB030002 停上电事件、EB030110 台区识别、EB030501 时钟、EB030503 校时、EB040302 停上电记录、EBEEEEEE 多数据项抄读等深度解析
- 透明转发（52H-F1）/ 事件上报（56H-F2）自动识别内嵌 EB 帧

**其他**：

- 校验器 GDWValidator 支持福建增补帧 AFN 定位；查询页新增 EB 数据标识查询区块
- **Reflex Web 版同步**：协议7 解析/组帧/校验自动获得福建增补支持；Web 查询页新增 EB 数据标识查询（协议7 下输入 `EB` 前缀或「台区/时钟/档案」等关键词）；组帧页新增「EB 数据标识 帧生成器」——支持 645 帧与 698.45 完整链路层帧双格式（698 含 8 种服务含 GET、SA/CA/控制域头部配置、HCS/FCS 自动计算、属性/方法/索引/PIID 可配置），42 个 EB 数据项支持按字段表单配置数据内容，一键填入报文内容字段
- 修复 `gdw_send_frame_lib.py::_pack_fields` 的 length_field 语义 bug（报文长度计算）
- 新增 `test/test_gdw_fujian.py`（16 项测试全过）；`test_web_frame_gen_utils.py` 增至 28 项
- **扩展协议升级 V3.42**：EB 数据标识新增周边节点信号质量（EB030313/314）、通信测距（EB030320/321）、NTB校时698方式（EB030506）、自动NTB校时模式扩展（EB030520）；EBEEEEEE 标记取消

### 1.13.0 — 2026-08-14

#### 新增 HDC 1.0 双模互联互通协议（索引 11）

主程序新增**第 12 种协议**「HDC 1.0 双模互联互通」（Q/GDW 12087.42-2020，旧版双模）：

- 新增独立解析器 `hdc10_parser.py`（`HDC10Parser`）：支持完整 MPDU（FC 16B + 物理块 PB×N）、FC 可变区域（信标/SOF/SACK/网间协调）、信标载荷与管理信息条目（含时隙分配 0xC0）、MAC 帧（标准 16B 头 + 单跳 4B 头）、MSDU 载荷与应用层业务报文
- 新增 `hdc10_mme_parser.py`：HDC 1.0 网络管理消息（MME）解析，MMTYPE 2 字节小端
- 新增 `validator/hdc10_validator.py`（`HDC10Validator`）：定界符类型 / 标准版本号 / FCCS（CRC-24）等校验
- GUI 集成：协议下拉框新增 `[11] HDC 1.0 双模互联互通`；解析级别下拉（auto/fc_pb/fc_only/mac_only/pb_only/fc_mac/app）与通道下拉（PLC 载波/HRF 无线）复用国网新一代控件；查询页新增 HDC 1.0 报文 ID / 端口号 / 消息类型查询
- 批量解析复用国网新一代前缀剥离与摘要逻辑；新增 `test_hdc10.py` 回归用例（时隙分配条目长度、信标 BPCS/PBCS 校验）
- 帧结构约定：`MPDU = FC(16B) + PB×N`；`PB = PBH(1B) + PB 体 + PBCS(3B, CRC-24)`；`MAC帧 = MAC头 + MSDU + ICV(4B, CRC-32)`；多字节字段小端、MAC 地址大端

> 注：HDC 1.0 目前仅在 PySide6 主程序支持；Reflex Web 版支持协议 0-10（11 种）。NiceGUI/TUI 版本已于 2026-08-17 移除。

#### 新一代载波协议（索引 9）增强

- **通道自动识别 PLC/HRF**：`parse_to_table` 新增 `channel="auto"`（默认），按 FC SOF 可变区域结构（表45 HRF / 表20 BPLC / 表23 ISAC）预测帧长并与实际帧长比对，命中者胜；解析结果新增「通道判定」行，GUI 通道下拉默认「自动识别」
- **无线信道单跳 MAC 帧解析**（版本2，表12）：4 字节帧头 + 无线发现列表消息（表139 TLV，站点属性按表142 展开）
- **测试帧切频操作目标按 Option+信道号解析**（模式6，与模式8 一致）；同步修正国网新一代模式6
- **批量解析管理消息摘要崩溃修复**：`int(mmtype_val)` 未处理 `0x` 前缀导致关联请求/发现列表等帧批量解析报错，改为 `int(val, 16)` + try/except 兜底

#### 界面交互与易用性

- **协议选择持久化**：上次协议索引存入 `config.json` 的 `parse.protocol`，下次启动自动恢复
- **所有解析/查询/监控表格支持 Ctrl+滚轮缩放**（`gui_utils.py::ZoomableTableWidget`，类 Excel，Ctrl+0 恢复）
- **校验结果展开/收缩 + 解析结果表全屏**：校验结果区可收缩；单帧/批量解析结果表可全屏弹窗展示
- **GUI 按钮风格统一**：批量工具栏 / LLM API 对话框 / LLM 预处理面板按钮高度、内边距、字号统一；修复 `_py_run_btn` 连接不存在方法的 bug

#### DLT645 数据域长度一致性校验增强

DLT645-2007 协议解析与校验新增**数据域长度声明值与实际帧长一致性检查**：

- **解析器**（`dlt645_parser.py`）：当数据长度字段声明值与帧中实际数据域字节数不一致时，仍然尽力解析实际存在的数据（地址、控制码、DI、数据内容、校验和均正常显示），但在解析结果表格中插入 `⚠ 数据长度错误` 行明确提示，并将 `valid` 置为 `False`，避免用户误以为报文合法。
- **校验器**（`validator/dlt645_validator.py`）："数据长度"校验项从原来仅检查上限（>200 字节告警）改为**先校验声明长度与实际帧长是否一致**，不一致时标记为 FAIL 并置整体校验不通过。

设计原则：**长度不匹配时不得静默截断或直接返回空白**，必须在用户可见的解析结果中明确标注错误，同时尽可能展示已解析的字段，便于现场调试定位问题。

## 许可证

MIT
