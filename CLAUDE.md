# CLAUDE.md

> 项目权威 Agent 指南见 [`AGENTS.md`](AGENTS.md)，本文件是 Claude Code 精简入口。内容冲突时以 `AGENTS.md` 为准。

## 项目概述

多协议电力通信报文解析工具，当前版本为 `1.13.0`（见 `main_gui.py:APP_VERSION`）。项目使用 Trellis 管理开发流程，工作流见 `.trellis/workflow.md`。

支持 12 种协议：

| 索引 | 协议 |
| --- | --- |
| 0 | 南网协议 |
| 1 | PLC RF 协议（万胜海外） |
| 2 | HDLC/国网DLMS |
| 3 | DLMS-APDU（国网） |
| 4 | DLMS Wrapper 裸报文 |
| 5 | DLMS-APDU 裸报文 |
| 6 | DLT645-2007 |
| 7 | 国网协议 |
| 8 | 698.45 协议 |
| 9 | 新一代载波协议（通感一体化） |
| 10 | 国网新一代双模通信互联互通 |
| 11 | HDC 1.0 双模互联互通（Q/GDW 12087.42-2020） |

界面形态包括 PySide6 GUI、Textual TUI、NiceGUI Web 与实验性 Reflex Web，并新增实时监控器、TCP 流量监控和 Windows 系统集成。

## 快速开始

```bash
pip install pyside6 crcmod lupa openpyxl scapy reflex

python main_gui.py                 # PySide6 GUI 主入口
python reflex_web/run_app.py       # Reflex Web 版（实验性）

pyinstaller 南网协议解析工具.spec --noconfirm
```

GUI 支持命令行参数：

```bash
python main_gui.py --parse "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16" --protocol 0
python main_gui.py --file sample.log --protocol 国网新一代
python main_gui.py --minimized
python main_gui.py --clipboard
```

## 核心架构

- `main_gui.py`：PySide6 主程序，`MainWindow` 负责协议切换、标签页集成与系统集成，代码体量较大，新 UI 组件应拆到独立文件
- `monitor_widget.py`：实时监控器，面向南网新一代（`ED..EE`）与国网新一代（`96..16`）包装格式
- `monitor/tcp_monitor.py`：TCP 流量监控，基于 scapy 抓包、双向流重组与监控封装解帧
- `system_integration/`：系统托盘、全局热键、剪贴板报文自动检测、Notepad++ 集成、单实例、注册表右键菜单、开机自启与系统设置
- `reflex_web/`：Reflex Web 版（实验性）
- `validator/`：统一协议校验引擎，各协议 validator 继承 `BaseValidator`

主要解析器：

| 文件 | 类 | 协议 |
| --- | --- | --- |
| `protocol_parser.py` | `ProtocolFrameParser` | 南网协议 |
| `gdw10376_parser.py` | `GDW10376Parser` | 国网协议 |
| `plc_rf_parser.py` | `PLCRFProtocolParser` | PLC RF |
| `hdlc_parser.py` | `HDLCParser` | HDLC / DLMS |
| `dlms_deep_parser.py` | `DLMSDeepParser` | DLMS APDU 深度解析 |
| `dlt645_parser.py` | `DLT645Parser` | DLT645-2007 |
| `dl_t698_45_parser.py` | `DLT69845Parser` | 698.45 链路层 |
| `dl_t698_45_apdu_parser.py` | `DLT69845APDUParser` | 698.45 APDU |
| `dl_t698_45_axdr.py` | `AXDRCoder` | A-XDR 编解码 |
| `csg_new_gen_parser.py` | `CSGNewGenParser` | 新一代载波 |
| `gw_new_gen_parser.py` | `GWNewGenParser` | 国网新一代双模 |
| `gw_new_gen_mme_parser.py` | `parse_management_message` | 国网新一代 MME 管理消息 |
| `hdc10_parser.py` | `HDC10Parser` | HDC 1.0 双模互联互通 |
| `hdc10_mme_parser.py` | `parse_management_message` | HDC 1.0 MME 网络管理消息 |

所有 parser 均返回嵌套 dict 或解析行列表，关键中文键为 `原始值`、`解析值`、`说明`、`偏移`、`长度`。

## 关键约定

- `current_protocol` 索引硬编码，新增协议必须同步修改下拉框、协议切换、帧提取、解析分派、查询页、校验器与文档
- 南网 / 国网 / 698.45 / 新一代 / 国网新一代 / HDC 1.0：多字节字段默认小端；HDC 1.0 的 MAC 地址为大端
- HDLC / DLMS：网络字节序（大端）
- DLT645：BCD 编码，地址域低字节在前
- PLC RF：大端
- 698.45 校验使用 `crcmod` 的 `x-25`，参与 CRC 的字段范围必须查协议文档
- 南网新一代 / 国网新一代 MAC 帧使用 CRC-32
- HDC 1.0：FC 的 FCCS 与 PB 尾 PBCS 为 CRC-24，MAC 帧尾 ICV 为 CRC-32
- 组帧与预设命令标签页仅对南网（0）、国网（7）、698.45（8）显示
- 实时监控器仅对新一代（9）与国网新一代（10）显示
- TCP 监控与报文工具始终显示
- HDC 1.0（11）仅在 PySide6 主程序支持（无监控器/组帧/档案）；NiceGUI Web（0-10）与 TUI（0-9）暂未包含

## 测试

项目无正式测试框架，`test_*.py` 为独立脚本：

```bash
python test_csg_new_gen.py
python test_gw_new_gen.py
python test_hdc10.py
python test_dl_t698_45.py
python test_hdlc.py
python test_plc_rf.py
python test_lua_engine.py
python test_sack_fix.py
python test_diff_engine.py
python test_monitor_deframe.py
python test_monitor_plc2_deframe.py
python test_gw_monitor_summary.py
python test_theme_settings.py
```

## 常见陷阱

- `_clear_layout` 会递归销毁子 widget，改查询页或动态标签页时必须理解此行为
- DLMS 深度解析通过双击 `DLMS APDU` 行触发
- HDLC 透明传输会把 `7E` 转义为 `7E 5D`，`7D` 转义为 `7D 5D`，组帧也必须处理
- 国网新一代完整帧为 `FC(16B) + PB`，PB 含 `PBH(1B) + MAC帧头 + MSDU`，FC 末 3 字节为 FCCS，其后没有独立 HCS
- 国网新一代按 FC 字节 12 高 4 位自动区分 HDC 1.0 / HDC 2.0
- HDC 1.0（索引 11）是独立协议，用 `hdc10_parser.py` 解析；帧结构 `MPDU = FC(16B) + PB×N`，`PB = PBH(1B) + PB 体 + PBCS(3B)`，`MAC帧 = MAC头 + MSDU + ICV(4B)`；信标帧 FC 后直接为信标载荷（无 PBH）；信标管理条目（如 0xC0 时隙分配）长度字段为 2 字节，内容 = total_len - 3
- MME 管理消息的 MMTYPE 为 2 字节小端，保留字段实测为 1 字节
- `mac_only` / `pb_only` / `app` 等仅输入解析模式遵守“输入即 PB”契约，不要额外剥离 FC
- TCP 监控依赖 `scapy`，Windows 需 npcap；未安装时功能降级
- 系统集成中的注册表与全局热键仅适用于 Windows，修改启动流程时不要破坏单实例顺序
- 剪贴板自动检测监听 `QClipboard.dataChanged`，会严格校验纯 hex 并自动识别协议；Notepad++ 集成通过修改 `%APPDATA%/Notepad++` 下的 XML 注册命令，均带备份或开关
- 当前主程序打包使用 `南网协议解析工具.spec`，新增数据资源必须同步检查该 spec

## 协议文档

- 南网：`PLUZ计量自动化系统技术规范.md`、`LME产品相关信息生产运维接口手册_V2.4_251115.md`、`低压电力线宽带载波深化应用技术手册v1.1.md`
- 国网：`集中器本地通信模块接口-2024.md`
- 645：`DLT645-2007.md` 与补遗 PDF
- HDLC / DLMS：`HDLC.md`、`HDLC解析说明.md`、`IEC 62056-46.PDF`、`DLMS_Protocol.md`、`DLMS_Protocol.pdf`
- PLC RF：`4.md`
- 698.45：`面向对象的用电信息数据交换协议(20210910).md`
- 新一代载波：`南网新一代20260226校对/南网新一代20260226校对/`
- 国网新一代：`国网新一代协议/`
- HDC 1.0：`国网新一代协议/HDC-国网双模协议/`（双模技术规范第 1/4-1/4-2/4-3 部分）

遇到协议字段、字节序或校验范围不确定时，先查对应协议文档，不要凭记忆推断。
