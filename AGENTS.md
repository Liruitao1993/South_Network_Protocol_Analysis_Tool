# 南网协议解析工具 — Agent 指南

## 项目概览

多种电力通信协议的图形化解析工具。单代码库，纯 Python 3.8+，无构建系统。当前版本 `1.6.8`。

**支持的协议：**
- 南网协议 (Q/CSG1209021-2019)
- 国网协议 (Q/GDW 10376.2—2024)
- PLC RF 协议 (万胜海外 V1_04)
- HDLC/DLMS (IEC 62056-46)
- DLMS Wrapper 裸报文 / DLMS-APDU 裸报文
- DLT645-2007 电表协议
- DLT698.45-2017 协议

## 运行与打包

```bash
# 运行 GUI（唯一入口点）
python main_gui.py

# 运行 Web 版
streamlit run streamlit_app.py

# 打包 exe
pyinstaller --onefile --windowed --name "协议解析工具" main_gui.py
# 或使用 spec 文件（南网/国网打包配置不同）
pyinstaller 南网协议解析工具.spec   # datas: custom_di.json, dlt645_di.json
pyinstaller 协议解析工具.spec       # datas: custom_di.json, dlt645_di.json, gdw_custom_afn.json
```

**依赖：** `pip install pyside6` （Web 版额外需要 `pip install streamlit`）

## 架构

```
main_gui.py                # GUI主程序 (PySide6)，应用入口，~3450行
├── 协议解析器
│   ├── protocol_parser.py   # 南网协议解析器 (ProtocolFrameParser)
│   │   └── protocol_tool.py   # 控制域结构体(ControlField) + 组帧(Frame)
│   ├── gdw10376_parser.py   # 国网协议解析器 (GDW10376Parser)
│   │   └── gdw10376_tool.py   # 国网控制域 + 常量
│   ├── plc_rf_parser.py     # PLC RF协议解析器 (PLCRFProtocolParser)
│   │   └── dlms_parser.py     # DLMS基础解析器 (DLMSParser)
│   ├── hdlc_parser.py       # HDLC/DLMS帧解析器 (HDLCParser)
│   ├── dlms_deep_parser.py  # DLMS-APDU深度解析器 (DLMSDeepParser)
│   ├── dlt645_parser.py     # DLT645-2007电表协议解析器
│   └── dl_t698_45_parser.py # DLT698.45-2017协议解析器 (DLT69845Parser)
├── 查询/映射模块
│   ├── obis_lookup.py       # OBIS码查询 (HDLC/DLMS)
│   ├── command_lookup.py    # PLC RF命令字查询
│   ├── dlt645_di_lookup.py  # DLT645 DI查询
│   └── gdw_afn_lookup.py    # 国网AFN查询
├── 组帧/发送
│   ├── send_frame_lib.py    # 南网帧生成 (ProtocolFrameGenerator)
│   └── gdw_send_frame_lib.py # 国网帧生成
├── GUI组件
│   ├── frame_gen_widget.py  # 帧生成标签页组件
│   ├── preset_buttons.py    # 预设命令按钮组件
│   ├── test_plan_widget.py  # 测试计划组件
│   ├── serial_worker.py     # 串口通信线程 (SerialWorker)
│   ├── gui_utils.py         # 右键菜单等GUI工具函数
│   ├── archive_widget.py    # 档案管理组件
│   └── topology_widget.py   # 拓扑信息组件
├── 验证/测试/报表
│   ├── validator/           # 协议验证引擎 (BaseValidator + 各协议validator)
│   ├── monitor/frame_monitor.py  # 实时帧监听器
│   ├── report/excel_reporter.py  # Excel测试报告 (需openpyxl)
│   ├── templates/test_templates.py # 测试模板库
│   └── visual_editor/test_item_editor.py # 可视化测试项编辑器
├── 组帧Schema
│   ├── frame_generator_schema.py    # 南网帧生成UI schema
│   └── gdw_frame_generator_schema.py # 国网帧生成UI schema
└── 数据文件
    ├── custom_di.json       # 南网自定义DI (运行时读写)
    ├── dlt645_di.json       # DLT645 DI映射 (由generate_dlt645_di.py生成，勿手动编辑)
    ├── gdw_custom_afn.json  # 国网自定义AFN+Fn (运行时读写)
    ├── config.json          # 串口配置
    ├── test_plan.json       # 测试方案自动持久化
    └── NW_command.json / GW_command.json / command.json  # 命令字数据
```

**数据流：** 用户输入hex → `main_gui.py` 根据 `current_protocol` 选择对应parser → parser返回结构化dict → GUI表格展示 + 字节高亮 + DLMS深度弹窗

## 关键约定

### 代码风格
- 类名 CamelCase (`ProtocolFrameParser`)，函数/变量 snake_case (`parse_frame`)，常量 UPPER_CASE (`AFN_MAP`)
- GUI代码全在 `main_gui.py` 一个文件中，`MainWindow` 类 ~2500行
- 新增UI组件拆分到独立文件（如 `frame_gen_widget.py`），由 `main_gui.py` 导入组合

### 解析结果格式
所有parser返回嵌套dict，关键字段：
- `原始值`/`原始字节` — 十六进制原始数据
- `十进制`/`解析值` — 解析后的数值
- `说明`/`名称`/`业务说明` — 中文描述

### 字节序
- 南网/国网协议：长度域、DI 字段使用**小端序 (little-endian)**
- HDLC/DLMS：网络字节序 (big-endian)
- DLT645：BCD编码，地址域低字节在前

### 自定义数据持久化
- 南网自定义DI: `custom_di.json`（运行时通过GUI添加/删除）
- 国网自定义AFN+Fn: `gdw_custom_afn.json`（运行时通过GUI添加/删除）
- DLT645自定义DI: `dlt645_di_custom.json`
- DLT645标准DI数据: `dlt645_di.json`（由 `generate_dlt645_di.py` 生成，勿手动编辑）

### 校验和
- 南网协议：控制域 + 用户数据区的八位位组算术和（不考虑溢出）
- DLT645：所有字节累加和 & 0xFF
- HDLC：CRC-16 (FCS)

## 测试

没有正式测试框架。`test_*.py` 文件是独立脚本，直接 `python test_xxx.py` 运行：

```bash
python test_dlms.py
python test_hdlc.py
python test_plc_rf.py
python test_ber_tlv.py
python test_actual_hdlc.py
python test_special_frame.py
python test_snrm_frame.py
```

每个测试脚本包含硬编码的测试帧和预期输出，通过 `assert` 或 `print` 对比验证。

## 常见陷阱

- **`main_gui.py` 中的 `_clear_layout`** 会递归删除所有子widget。修改查询标签页逻辑时必须理解此方法，否则会造成widget残留或崩溃
- **PyInstaller 打包**：两个spec文件的 `datas` 不同——`南网协议解析工具.spec` 只打包 `custom_di.json` + `dlt645_di.json`，`协议解析工具.spec` 额外包含 `gdw_custom_afn.json`
- **协议切换**：`current_protocol` 索引（0=南网, 1=PLC RF, 2=HDLC, 3=Wrapper, 4=APDU, 5=DLT645, 6=国网, 7=698.45）硬编码在 `main_gui.py`，添加新协议必须同时更新 `_on_protocol_changed`、`_update_protocol_lookup_tab` 和 `_extract_frames_for_protocol`
- **DLMS深度解析**：双击表格中 `DLMS APDU` 行触发 `dlms_deep_parser`，不是自动触发
- **HDLC字节填充**：7E帧内遇到7E需转义（7E→7E 5D, 7D→7D 5D），解析器自动处理，组帧时也需注意
- **组帧/预设标签页可见性**：只在南网(0)和国网(6)协议下显示，通过 `setTabVisible` 控制

## 协议参考文档

解析协议遇到不确定定义时，按解析器检索对应文档（而非凭记忆推断）：

| 解析器 | 参考文档 |
|--------|----------|
| 南网 | `PLUZ计量自动化系统技术规范.md`、`LME产品相关信息生产运维接口手册_V2.4_251115.md`、`低压电力线宽带载波深化应用技术手册v1.1.md` |
| 国网 | `集中器本地通信模块接口-2024.md` |
| DLT645 | `DLT645-2007.md`、`国网计量中心电能表全性能试验检测公告-第4号补遗-事件记录采集-远程费控功能和负荷曲线抄读功能.pdf` |
| HDLC | `HDLC.md`、`HDLC解析说明.md`、`IEC 62056-46.PDF` |
| DLMS | `DLMS_Protocol.md`、`DLMS_Protocol.pdf` |
| 万胜(PLC RF) | `4.md` |
| DLT698.45 | `面向对象的用电信息数据交换协议(20210910).md`（CRC使用 crcmod 中 X-25/CRC16，文档明确定义哪些字段参与 CRC） |

## 其他参考

- `QWEN.md` — 项目详细文档（中文），含协议帧格式说明和开发约定
- `README.md` — 用户面向的简要说明