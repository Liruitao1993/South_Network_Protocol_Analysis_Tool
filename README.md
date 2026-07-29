# 南网协议解析工具

多种电力通信协议的图形化解析工具，基于 Python / PySide6 开发，支持单帧解析、批量解析、协议校验、帧生成、串口通信、测试计划、Lua 脚本等完整工作流。

当前版本见 [`main_gui.py`](main_gui.py) 中的 `APP_VERSION`（`1.8.2`）。

## 支持协议

工具支持 11 种电力通信协议，下拉框索引即协议编号：

| 索引 | 协议 | 标准号 | 字节序 | 校验 |
|------|------|--------|--------|------|
| 0 | 南网协议 | Q/CSG1209021-2019 | 小端 | 8位位组算术和 |
| 1 | PLC RF 协议（万胜海外） | 万胜 V1_04 | 大端 | 累加和 & 0xFF |
| 2 | HDLC/国网DLMS | IEC 62056-46 | 大端 | CRC-16/FCS（CCITT） |
| 3 | DLMS-APDU(国网) | IEC 62056-46 | 大端 | 无 |
| 4 | DLMS Wrapper 裸报文 | IEC 62056-46 | 大端 | 无 |
| 5 | DLMS-APDU 裸报文 | IEC 62056-46 | 大端 | 无 |
| 6 | DLT645-2007 电表协议 | DL/T 645-2007 | BCD，低字节在前 | 累加和 & 0xFF |
| 7 | 国网协议 | Q/GDW 10376.2—2024 | 小端 | 8位位组算术和 |
| 8 | 698.45 协议 | DL/T 698.45-2017 | 小端 | CRC-16（crcmod `x-25`） |
| 9 | 新一代载波协议（通感一体化） | 通感一体化宽带载波通信规约 | 小端 | CRC-32（MAC帧） |
| 10 | 国网新一代双模通信互联互通 | 国网新一代双模通信互联互通技术规范 | 小端 | CRC-32（MAC帧） |

## 主要功能

- **单帧解析**：输入十六进制报文，一键解析为分层表格，点击行联动高亮输入框对应字节
- **批量解析**：从文件或剪贴板导入多帧报文自动解析，支持导出 JSON；新一代载波协议支持监控日志前缀剥离
- **协议校验**：内置校验引擎（`validator/`），覆盖起始符、长度域、校验和/CRC，逐项展示通过/失败/警告
- **帧生成**：南网/国网/698.45 三种组帧模式，字段模板化编辑，支持预设命令一键填充
- **预设命令**：南网/国网预设命令库，点击即可生成对应下行帧
- **串口通信**：配置串口参数、发送帧、实时接收解析、日志窗口
- **测试计划**：测试项 CRUD、顺序发送、超时匹配、结果记录；支持导出 Excel 测试报告
- **Lua 脚本**（1.8.1 新增）：测试计划中嵌入可编程逻辑，支持条件分支、循环遍历、数据解析、变量共享
- **DLMS 深度解析**：双击 `DLMS APDU` 行弹出深度解析窗口，支持 BER-TLV 递归解析
- **档案管理 / 拓扑信息**：南网/国网协议专用，支持档案导入导出、拓扑组网统计
- **查询页**：南网 DI、国网 AFN、DLT645 DI、OBIS 码、PLC RF 命令字、新一代业务标识查询
- **新一代载波解析级别**：auto / fc_pb / fc_only / app 四种级别切换
- **NiceGUI Web 版**（1.8.2 新增）：基于 NiceGUI 框架的浏览器解析器，支持完整 11 种协议解析、单帧/批量解析、报文对比、组帧发送、预设命令、查询页、测试计划、档案管理、拓扑信息等标签页，集成串口通信，暗色主题，健康检查端点
- **TUI 终端版**（1.8.2 新增）：基于 Textual 的终端图形化解析器，支持单帧解析+字节高亮、批量多帧解析+摘要、协议一致性校验
- **报文工具**：ASCII/HEX 双向转换、DLT645 偏移（±0x33H）、字节逆序、报文↔Pn/Fn 转换、CRC/校验和计算、HEX↔bitstring 转换

## 运行环境

- Windows 优先；Python 3.8+
- 中文路径需保证 UTF-8 / GBK 编码兼容

## 安装依赖

```bash
pip install pyside6        # GUI 必需
pip install nicegui        # NiceGUI Web 版（1.8.2 起）
pip install pyserial       # NiceGUI Web 版串口通信（1.8.2 起）
pip install crcmod         # 698.45 协议 CRC 校验（1.7.0 起）
pip install lupa           # 测试方案 Lua 脚本引擎（1.8.1 起，可选）
pip install openpyxl       # Excel 测试报告（可选）
pip install streamlit      # Streamlit Web 版（可选，功能子集）
```

> `lupa` 未安装时 Lua 脚本功能不可用，其余功能不受影响。

## 运行

```bash
# GUI 版（主入口）
python main_gui.py

# NiceGUI Web 版（完整功能，1.8.2 新增）
python web_app.py

# Streamlit Web 版（功能子集）
streamlit run streamlit_app.py
```

## 打包 exe

项目提供两个 PyInstaller spec 文件，`datas` 与 `excludes` 配置一致，差异仅在打包模式：

```bash
pip install pyinstaller

# 目录型（COLLECT），exe 在 dist/协议解析工具/
pyinstaller 协议解析工具.spec

# 单文件型（EXE），exe 在 dist/南网协议解析工具.exe
pyinstaller 南网协议解析工具.spec
```

两个 spec 均打包 `custom_di.json`、`dlt645_di.json`、`gdw_custom_afn.json` 和 `icons/`。新增需打包的数据文件时，两个 spec 都要同步。

## 使用说明

### 基本解析

1. 顶部下拉框选择协议类型
2. 在「输入报文」文本框粘贴十六进制报文（支持带空格/无空格混合）
3. 点击「解析报文」
4. 下方表格显示分层解析结果，点击行高亮对应字节

### DLMS 深度解析

解析 HDLC 帧后，`DLMS APDU` 行覆盖整个 APDU 字节范围，**双击该行**即弹出深度解析窗口，支持 Get/Set/Action 等 APDU 类型与 BER-TLV 递归解析。

### 帧生成

切换到「帧生成」标签页（仅南网/国网/698.45）：
- 按字段模板填写参数
- 支持预设命令一键填充
- 生成帧后可直接通过串口发送

### 测试计划

切换到「测试计划」标签页：
- 添加测试项（发送帧 / 后台监听 / 纯等待 / Lua脚本）
- 配置超时与匹配规则
- 顺序执行并记录结果，支持导出 Excel 报告

Lua 脚本类型可在测试流程中嵌入可编程逻辑，详见 [`docs/Lua脚本使用说明.md`](docs/Lua脚本使用说明.md)。

### 批量解析

切换到「批量解析」标签页：
- 从文件加载或剪贴板粘贴
- 自动从混杂文本中提取完整帧
- 批量处理并导出 JSON

## 项目结构

```
main_gui.py                  # GUI 主程序（PySide6），应用入口
protocol_parser.py           # 南网协议解析器
gdw10376_parser.py           # 国网协议解析器
plc_rf_parser.py             # PLC RF 协议解析器
hdlc_parser.py               # HDLC/DLMS 解析器
dlms_deep_parser.py          # DLMS-APDU 深度解析（双击触发）
dlt645_parser.py             # DLT645-2007 解析器
dl_t698_45_parser.py         # 698.45 链路层解析器
dl_t698_45_apdu_parser.py    # 698.45 APDU 解析器
dl_t698_45_axdr.py           # A-XDR 编解码
csg_new_gen_parser.py        # 新一代载波协议解析器
gw_new_gen_parser.py         # 国网新一代双模通信互联互通解析器
gw_new_gen_cmd_payloads.py   # 国网新一代应用层命令载荷解析
frame_diff_engine.py         # 协议感知帧对比引擎
send_frame_lib.py            # 南网帧生成
gdw_send_frame_lib.py        # 国网帧生成
dl_t698_45_frame_gen.py      # 698.45 帧生成
frame_gen_widget.py          # 帧生成标签页组件
preset_buttons.py            # 预设命令组件
test_plan_widget.py          # 测试计划组件
serial_worker.py             # 串口通信线程
lua_script_engine.py         # Lua 脚本引擎（1.8.1）
archive_widget.py            # 档案管理组件
topology_widget.py           # 拓扑信息组件
diff_widget.py               # 报文对比标签页组件
message_tool_widget.py       # 报文工具标签页组件
enhanced_export.py           # 增强导出功能（Excel/CSV/TXT/JSON）
tui_app.py                   # TUI 终端版（基于 Textual）
tui_app.tcss                 # TUI 样式表
validator/                   # 协议校验引擎（BaseValidator + 各协议 validator）
monitor/frame_monitor.py     # 实时帧监听器
report/excel_reporter.py     # Excel 测试报告
templates/test_templates.py  # 测试模板库
docs/Lua脚本使用说明.md       # Lua 脚本用户文档
web_app.py                   # NiceGUI Web 版入口（1.8.2 新增）
web/                         # NiceGUI Web 版组件（1.8.2 新增）
├── main_page.py             #   主页面布局
├── protocol_registry.py     #   协议注册表（解析器/校验器映射）
├── frame_extractor.py       #   帧提取工具
├── adapters/                #   适配器
│   └── serial_adapter.py    #     串口通信适配器
├── components/              #   UI 组件
│   ├── hex_input.py         #     十六进制输入
│   ├── parse_table.py       #     解析结果表格
│   ├── protocol_selector.py #     协议选择器
│   ├── byte_highlighter.py  #     字节高亮
│   └── serial_panel.py      #     串口面板
├── tabs/                    #   标签页
│   ├── single_parse.py      #     单帧解析
│   ├── batch_parse.py       #     批量解析
│   ├── diff.py              #     报文对比
│   ├── lookup.py            #     查询页
│   ├── frame_gen.py         #     帧生成
│   ├── preset_cmd.py        #     预设命令
│   ├── test_plan.py         #     测试计划
│   ├── archive.py           #     档案管理
│   └── topology.py          #     拓扑信息
└── styles/
    └── custom.css           #     自定义暗色主题样式
```

协议定义、解析器与参考文档的完整映射详见 [`AGENTS.md`](AGENTS.md) §5。

## 开发文档

- [`AGENTS.md`](AGENTS.md) — AI Coding Agent 上手指南，包含完整架构、协议映射、字节序/校验约定、开发原则与变更日志
- [`docs/Lua脚本使用说明.md`](docs/Lua脚本使用说明.md) — Lua 脚本功能使用说明与 API 参考

## 测试

项目无正式测试框架，`test_*.py` 为独立脚本，直接运行：

```bash
python test_csg_new_gen.py      # 新一代载波协议
python test_dl_t698_45.py       # 698.45 协议
python test_hdlc.py             # HDLC 帧
python test_plc_rf.py           # PLC RF
python test_lua_engine.py       # Lua 脚本引擎
python test_sack_fix.py         # SACK 帧解析
```

## 许可证

MIT
