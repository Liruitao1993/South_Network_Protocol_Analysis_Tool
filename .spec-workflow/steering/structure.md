# 项目架构

## 目录结构

```
南网解析工具/
├── main_gui.py                     # GUI主程序（PySide6），~4480行
├── web_app.py                      # NiceGUI Web 版入口（1.8.2 新增）
├── tui_app.py                      # TUI 版（Textual 框架）
├── streamlit_app.py                # Streamlit Web 版（功能子集）
│
├── 协议解析器（parser）
│   ├── protocol_parser.py          # 南网 (ProtocolFrameParser) ~4450行
│   ├── gdw10376_parser.py          # 国网 (GDW10376Parser)
│   ├── plc_rf_parser.py            # PLC RF (PLCRFProtocolParser)
│   ├── hdlc_parser.py              # HDLC/DLMS (HDLCParser)
│   ├── dlms_deep_parser.py         # DLMS-APDU 深度解析
│   ├── dlt645_parser.py            # DLT645-2007 (DLT645Parser)
│   ├── dl_t698_45_parser.py        # 698.45 链路层 (DLT69845Parser)
│   ├── dl_t698_45_apdu_parser.py   # 698.45 APDU (DLT69845APDUParser)
│   ├── dl_t698_45_axdr.py          # A-XDR 编解码 (AXDRCoder)
│   ├── csg_new_gen_parser.py       # 新一代载波 (CSGNewGenParser) ~4970行
│   └── gw_new_gen_parser.py        # 国网新一代双模 (GWNewGenParser)
│
├── 查询/映射模块（lookup）
│   ├── obis_lookup.py              # OBIS码 (HDLC/DLMS)
│   ├── command_lookup.py           # PLC RF 命令字
│   ├── dlt645_di_lookup.py         # DLT645 DI
│   ├── gdw_afn_lookup.py           # 国网 AFN
│   └── dl_t698_45_oi_lookup.py     # 698.45 OI 对象标识
│
├── 组帧/发送（frame generation）
│   ├── send_frame_lib.py           # 南网帧生成 (ProtocolFrameGenerator)
│   ├── gdw_send_frame_lib.py       # 国网帧生成 (GDWFrameGenerator)
│   ├── dl_t698_45_frame_gen.py     # 698.45 帧生成 (DLT69845FrameGenerator)
│   ├── frame_generator_schema.py   # 南网帧生成 UI schema
│   ├── gdw_frame_generator_schema.py # 国网帧生成 UI schema
│   └── dl_t698_45_frame_schema.py  # 698.45 组帧字段 schema
│
├── GUI 组件
│   ├── frame_gen_widget.py         # 帧生成标签页 (FrameGenWidget)
│   ├── preset_buttons.py           # 预设命令按钮 (PresetButtonWidget)
│   ├── test_plan_widget.py         # 测试计划 (TestPlanWidget)
│   ├── serial_worker.py            # 串口通信线程 (SerialWorker)
│   ├── gui_utils.py                # 中文右键菜单等工具
│   ├── archive_widget.py           # 档案管理 (ArchiveWidget)
│   ├── topology_widget.py          # 拓扑信息 (TopologyWidget)
│   ├── diff_widget.py              # 报文对比标签页 (DiffWidget)
│   └── monitor_widget.py           # 实时监控器标签页 (RealtimeMonitorWidget)
│
├── Web 组件
│   └── web/
│       ├── main_page.py            # 主页面布局
│       ├── protocol_registry.py    # 协议注册表
│       ├── frame_extractor.py      # 帧提取工具
│       ├── adapters/serial_adapter.py  # 串口通信适配器
│       ├── components/             # UI 组件
│       └── tabs/                   # 标签页
│
├── 校验器（validator）
│   ├── base.py                     # BaseValidator + ValidationResult
│   ├── nw_validator.py             # 南网
│   ├── gdw_validator.py            # 国网
│   ├── hdlc_validator.py           # HDLC/DLMS/Wrapper/APDU
│   ├── plc_rf_validator.py         # PLC RF
│   ├── dlt645_validator.py         # DLT645
│   ├── dl_t698_45_validator.py     # 698.45
│   ├── csg_new_gen_validator.py    # 新一代载波
│   └── gw_new_gen_validator.py     # 国网新一代双模
│
├── 监听/报表/模板/可视化编辑
│   ├── monitor/frame_monitor.py    # 实时帧监听器
│   ├── report/excel_reporter.py    # Excel 测试报告
│   ├── templates/test_templates.py # 测试模板库
│   └── visual_editor/test_item_editor.py # 可视化测试项编辑器
│
├── 脚本引擎
│   ├── lua_script_engine.py        # Lua 脚本引擎（依赖 lupa）
│   └── docs/Lua脚本使用说明.md     # Lua 功能用户文档
│
├── 对比引擎
│   └── frame_diff_engine.py        # 协议感知帧对比引擎 (FrameDiffEngine)
│
├── 数据提取/生成脚本
│   ├── generate_dlt645_di.py       # 生成 dlt645_di.json
│   ├── generate_oi_lookup.py       # 生成 OI_NAME_MAP
│   ├── extract_69845_classes.py    # 从文档抽取类定义
│   └── convert_docx_to_md.py       # docx → md 转换
│
├── 数据文件（运行时读写）
│   ├── custom_di.json              # 南网自定义 DI
│   ├── gdw_custom_afn.json         # 国网自定义 AFN+Fn
│   ├── dlt645_di.json              # DLT645 DI 映射（勿手改）
│   ├── NW_command.json             # 南网预设命令
│   ├── GW_command.json             # 国网预设命令
│   ├── command.json                # PLC RF 命令字
│   ├── config.json                 # 串口配置
│   └── ...
│
├── 测试脚本
│   ├── test_dlms.py / test_hdlc.py / test_plc_rf.py
│   ├── test_dl_t698_45.py / test_csg_new_gen.py
│   ├── test_gw_new_gen.py / test_diff_engine.py
│   └── ...
│
├── 协议文档
│   ├── 南网新一代20260226校对/     # 新一代载波协议文档
│   └── 国网新一代协议/             # 国网新一代双模协议文档
│
└── 打包配置
    ├── 协议解析工具.spec           # 完整版 PyInstaller spec
    └── 南网协议解析工具.spec       # 精简版 PyInstaller spec
```

## 命名约定

### 文件
- **解析器**：`snake_case`，后缀 `_parser.py`（如 `protocol_parser.py`）
- **校验器**：`snake_case`，后缀 `_validator.py`（如 `nw_validator.py`）
- **GUI 组件**：`snake_case`，后缀 `_widget.py`（如 `frame_gen_widget.py`）
- **工具模块**：`snake_case`，后缀 `_tool.py`（如 `protocol_tool.py`）
- **测试脚本**：`test_` 前缀（如 `test_dlms.py`）
- **数据文件**：`snake_case`，后缀 `.json`（如 `custom_di.json`）

### 代码
- **类名**：CamelCase（如 `ProtocolFrameParser`、`FrameDiffEngine`）
- **函数/变量**：snake_case（如 `parse_frame`、`current_protocol`）
- **常量**：UPPER_CASE（如 `AFN_MAP`、`DI_COMBINATION_MAP`）
- **GUI 键名**：中文（如 `原始值`、`十进制`、`说明`）

## 模块边界

### 解析器层
- **职责**：协议报文解析，返回标准化嵌套 dict
- **约束**：parser 之间避免横向耦合，公共逻辑放 `base.py` 或工具模块
- **接口**：统一 `parse(frame_bytes) -> dict`

### 校验器层
- **职责**：解析结果的正确性校验
- **约束**：继承 `BaseValidator`，统一 `ValidationResult` 返回格式
- **接口**：统一 `verify(table_data) -> ValidationResult`

### GUI 层
- **职责**：用户交互、表格展示、字节高亮
- **约束**：新 UI 组件必须拆分到独立文件，`main_gui.py` 只负责组合
- **数据流**：parser 返回 dict → GUI 读取中文键名 → 表格展示

### 数据层
- **职责**：配置、档案、预设命令的持久化
- **约束**：JSON 文件存储，无数据库依赖
- **同步**：`dlt645_di.json` 由脚本生成，勿手改

## 代码规模指南
- **单文件上限**：建议不超过 3000 行（`main_gui.py` 已超，逐步拆分中）
- **函数长度**：建议不超过 100 行
- **嵌套深度**：建议不超过 4 层
- **parser 行数**：当前最大 `csg_new_gen_parser.py` 约 4970 行，需关注复杂度

## 文档标准
- **AGENTS.md**：项目权威文档，所有 AI Agent 必读
- **CHANGELOG**：在 `main_gui.py` 中维护，每次功能变更同步更新
- **协议文档**：严格遵循标准文档，遇到定义不确定时必须查阅
- **中文注释**：关键逻辑使用中文注释，便于国内团队理解
