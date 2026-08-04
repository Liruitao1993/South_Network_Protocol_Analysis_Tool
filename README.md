# 南网协议解析工具

[![Version](https://img.shields.io/badge/version-1.11.1-blue)]()
[![Python](https://img.shields.io/badge/Python-3.8%2B-brightgreen)]()
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()

一个面向电力通信现场调试的多协议解析工具，基于 Python / PySide6 开发，支持 11 种电力通信协议，覆盖单帧解析、批量解析、协议校验、帧生成、串口通信、测试方案、Lua 脚本、实时监控与 TCP 抓包等工作流。

当前版本为 `1.11.1`，版本号与编译日期见 `main_gui.py` 中的 `APP_VERSION` 与 `BUILD_DATE`。

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
| 查询页 | DI、AFN、DLT645 DI、OBIS、PLC RF 命令字、新一代业务标识查询 |
| 多端界面 | PySide6 GUI、Textual TUI、NiceGUI Web、实验性 Reflex Web |
| 主题与字体 | 5 套主题与字体设置，支持配置持久化 |
| 系统集成 | 系统托盘、全局热键、剪贴板报文检测、Notepad++ 集成、单实例、命令行解析、文件右键菜单与开机自启 |

## 支持协议

工具支持 11 种电力通信协议，下拉框索引即协议编号：

| 索引 | 协议 | 标准号 | 字节序 | 校验 |
| --- | --- | --- | --- | --- |
| 0 | 南网协议 | Q/CSG1209021-2019 | 小端 | 8 位位组算术和 |
| 1 | PLC RF 协议（万胜海外） | 万胜 V1_04 | 大端 | 累加和 & 0xFF |
| 2 | HDLC/国网DLMS | IEC 62056-46 | 大端 | CRC-16/FCS（CCITT） |
| 3 | DLMS-APDU（国网） | IEC 62056-46 | 大端 | 无 |
| 4 | DLMS Wrapper 裸报文 | IEC 62056-46 | 大端 | 无 |
| 5 | DLMS-APDU 裸报文 | IEC 62056-46 | 大端 | 无 |
| 6 | DLT645-2007 电表协议 | DL/T 645-2007 | BCD，低字节在前 | 累加和 & 0xFF |
| 7 | 国网协议 | Q/GDW 10376.2-2024 | 小端 | 8 位位组算术和 |
| 8 | 698.45 协议 | DL/T 698.45-2017 | 小端 | CRC-16（crcmod `x-25`） |
| 9 | 新一代载波协议（通感一体化） | 通感一体化宽带载波通信规约 | 小端 | CRC-32（MAC 帧） |
| 10 | 国网新一代双模通信互联互通 | 国网新一代双模通信互联互通技术规范 | 小端 | CRC-32（MAC 帧） |

## 快速开始

### 环境要求

- Windows 优先，支持 UTF-8 / GBK 中文路径
- Python 3.8+
- TCP 监控需要安装 `scapy`，Windows 下还需要安装 npcap

### 安装依赖

```bash
pip install pyside6        # GUI 必需
pip install nicegui        # NiceGUI Web 版（1.8.2 起）
pip install pyserial       # NiceGUI Web 版串口通信（1.8.2 起）
pip install textual        # TUI 终端版（1.8.2 起，可选）
pip install crcmod         # 698.45 协议 CRC 校验（1.7.0 起）
pip install lupa           # Lua 脚本引擎（1.8.1 起，可选）
pip install openpyxl       # Excel 测试报告（可选）
pip install scapy          # TCP 流量监控（可选，Windows 需 npcap）
pip install streamlit      # Streamlit Web 版（可选，功能子集）
pip install reflex         # Reflex Web 版（实验性）
```

> `lupa` 未安装时 Lua 脚本功能不可用，其余功能不受影响；`scapy` 或 npcap 未就绪时，TCP 监控标签页会给出安装提示。

### 运行

```bash
# PySide6 GUI 版（主入口）
python main_gui.py

# NiceGUI Web 版（完整功能）
python web_app.py

# Textual TUI 终端版
python tui_app.py

# Streamlit Web 版（功能子集）
streamlit run streamlit_app.py

# Reflex Web 版（实验性）
python reflex_web/run_app.py
```

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

### 批量解析

切换到「批量解析」标签页：

- 从文件加载或剪贴板粘贴
- 自动从混杂文本中提取完整帧
- 批量处理并导出 JSON / CSV / Excel
- 新一代载波协议支持监控日志前缀剥离与业务摘要

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

- 查询页支持南网 DI、国网 AFN、DLT645 DI、OBIS 码、PLC RF 命令字与新一代业务标识
- 档案管理与拓扑信息仅在南网 / 国网协议下显示
- 支持档案导入导出与拓扑组网统计

## 项目结构

```text
main_gui.py                  # PySide6 GUI 主程序，应用入口
protocol_parser.py           # 南网协议解析器
gdw10376_parser.py           # 国网协议解析器
plc_rf_parser.py             # PLC RF 协议解析器
hdlc_parser.py               # HDLC / DLMS 解析器
dlms_deep_parser.py          # DLMS APDU 深度解析
dlt645_parser.py             # DLT645-2007 解析器
dl_t698_45_parser.py         # 698.45 链路层解析器
dl_t698_45_apdu_parser.py    # 698.45 APDU 解析器
dl_t698_45_axdr.py           # A-XDR 编解码
csg_new_gen_parser.py        # 新一代载波协议解析器
csg_new_gen_cmd_payloads.py  # 新一代载波应用层命令载荷
gw_new_gen_parser.py         # 国网新一代双模解析器
gw_new_gen_mme_parser.py     # 国网新一代 MME 管理消息解析
gw_new_gen_cmd_payloads.py   # 国网新一代应用层命令载荷
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
tui_app.py                   # Textual TUI 终端版
tui_app.tcss                 # TUI 样式表
web_app.py                   # NiceGUI Web 版入口
web/                         # NiceGUI Web 版组件
reflex_web/                  # Reflex Web 版（实验性）
validator/                   # 协议校验引擎
monitor/frame_monitor.py     # 串口实时帧监听组件
report/excel_reporter.py     # Excel 测试报告
templates/test_templates.py  # 测试模板库
docs/Lua脚本使用说明.md       # Lua 脚本使用文档
南网协议解析工具.spec          # PyInstaller 打包配置
```

## 测试

项目无正式测试框架，`test_*.py` 为独立脚本，直接运行：

```bash
python test_csg_new_gen.py            # 新一代载波协议
python test_gw_new_gen.py             # 国网新一代双模协议
python test_dl_t698_45.py             # 698.45 协议
python test_hdlc.py                   # HDLC 帧
python test_plc_rf.py                 # PLC RF
python test_lua_engine.py             # Lua 脚本引擎
python test_sack_fix.py               # SACK 帧解析
python test_diff_engine.py            # 报文对比引擎
python test_monitor_deframe.py        # 监控解帧
python test_monitor_plc2_deframe.py   # PLC2 解帧
python test_gw_monitor_summary.py     # 国网新一代监控摘要
python test_theme_settings.py         # 主题与字体设置
```

## 开发文档

- [`AGENTS.md`](AGENTS.md)：AI Coding Agent 上手指南，包含架构、协议映射、字节序与校验约定、开发原则与变更日志
- [`docs/Lua脚本使用说明.md`](docs/Lua脚本使用说明.md)：Lua 脚本功能使用说明与 API 参考
- [`.trellis/workflow.md`](.trellis/workflow.md)：Trellis 开发工作流与任务规范

## 许可证

MIT
