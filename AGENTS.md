# 南网协议解析工具 — Agent 指南

## 项目概览

多种电力通信协议的图形化解析工具。单代码库，纯 Python，无构建系统。

**支持的协议：**
- 南网协议 (Q/CSG1209021-2019)
- PLC RF 协议 (万胜海外 V1_04)
- HDLC/DLMS (IEC 62056-46)
- DLMS Wrapper 裸报文 / DLMS-APDU 裸报文
- DLT645-2007 电表协议

## 运行与打包

```bash
# 运行 GUI（唯一入口点）
python main_gui.py

# 运行 Web 版
streamlit run streamlit_app.py

# 打包 exe
pyinstaller --onefile --windowed --name "协议解析工具" main_gui.py
# 或使用 spec 文件
pyinstaller 南网协议解析工具.spec
pyinstaller 协议解析工具.spec
```

**依赖：** `pip install pyside6` （Web 版额外需要 `pip install streamlit`）

## 架构

```
main_gui.py           # GUI主程序 (PySide6)，应用入口，~3000行
├── protocol_parser.py # 南网协议解析器 (ProtocolFrameParser类)
│   └── protocol_tool.py  # 控制域结构体(ControlField) + 组帧(Frame)
├── plc_rf_parser.py   # PLC RF协议解析器 (PLCRFProtocolParser)
│   └── dlms_parser.py    # DLMS基础解析器 (DLMSParser)
├── hdlc_parser.py     # HDLC/DLMS帧解析器 (HDLCParser)
├── dlms_deep_parser.py # DLMS-APDU深度解析器 (DLMSDeepParser)
├── dlt645_parser.py   # DLT645-2007电表协议解析器
├── obis_lookup.py     # OBIS码查询模块
├── command_lookup.py  # PLC RF命令字查询模块
├── dlt645_di_lookup.py # DLT645 DI查询模块
├── dlt645_di.json     # DLT645 DI映射数据 (自动生成)
├── custom_di.json      # 用户自定义南网DI (运行时读写)
└── send_frame_lib.py  # 帧生成工具 (ProtocolFrameGenerator)
```

**数据流：** 用户输入hex → `main_gui.py`选择对应parser → parser返回结构化dict → GUI表格展示 + 字节高亮 + DLMS深度弹窗

## 关键约定

### 代码风格
- Python 3.8+，使用类型提示
- 类名 CamelCase (`ProtocolFrameParser`)，函数/变量 snake_case (`parse_frame`)，常量 UPPER_CASE (`AFN_MAP`)
- GUI代码全在 `main_gui.py` 一个文件中，`MainWindow` 类超过2500行

### 解析结果格式
所有parser返回嵌套dict，关键字段：
- `原始值`/`原始字节` — 十六进制原始数据
- `十进制`/`解析值` — 解析后的数值
- `说明`/`名称`/`业务说明` — 中文描述

### 字节序
- 南网协议：长度域、DI 字段使用**小端序 (little-endian)**
- HDLC/DLMS：网络字节序 (big-endian)
- DLT645：BCD编码，地址域低字节在前

### 自定义数据持久化
- 南网自定义DI: `custom_di.json`（运行时通过GUI添加/删除）
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
```

每个测试脚本包含硬编码的测试帧和预期输出，通过 `assert` 或 `print` 对比验证。

## 常见陷阱

- **`main_gui.py` 中的 `_clear_layout`** 会递归删除所有子widget。修改查询标签页逻辑时必须理解此方法，否则会造成widget残留或崩溃
- **PyInstaller 打包**：spec文件中 `datas=[]`，运行时依赖的 JSON 文件（`custom_di.json`, `dlt645_di.json`）需要手动添加到 datas 或确保与exe同目录
- **协议切换**：`current_protocol` 索引（0=南网, 1=PLC RF, 2=HDLC, 3=Wrapper, 4=APDU, 5=DLT645）硬编码在 `main_gui.py`，添加新协议必须同时更新 `_on_protocol_changed` 和 `_update_protocol_lookup_tab`
- **DLMS深度解析**：双击表格中 `DLMS APDU` 行触发 `dlms_deep_parser`，不是自动触发
- **HDLC字节填充**：7E帧内遇到7E需转义（7E→7E 5D, 7D→7D 5D），解析器自动处理，组帧时也需注意

## 参考

- `QWEN.md` — 项目详细文档（中文），含协议帧格式说明和开发约定
- `README.md` — 用户面向的简要说明
- `DLMS_Protocol.md` / `DLT645-2007.md` / `HDLC.md` / `HDLC解析说明.md` — 协议参考文档