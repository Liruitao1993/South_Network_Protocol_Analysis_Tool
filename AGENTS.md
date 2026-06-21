# 南网协议解析工具 — Agent 指南

> 本文档是所有 AI Coding Agent / 模型接手本项目时的**唯一权威上手文档**。
> 阅读本文档后应能完全掌握：项目架构、模块职责、协议→解析器→参考文档的映射、字节序/校验/编码约定、开发原则、最新变更与陷阱。
>
> **维护原则**：每次合并 PR / 完成功能后，请同步更新 §10「变更日志」与 §11「最新变更摘要」。如新增协议或解析器，必须更新 §2、§3、§5、§7。

---

## 1. 项目概览

多种电力通信协议的图形化解析工具。单代码库，纯 Python 3.8+，无构建系统，无正式测试框架。当前版本见 `main_gui.py:APP_VERSION`（现 `1.7.1`）。

**支持的协议（共 9 种，对应 GUI 协议下拉框 `current_protocol` 索引）：**

| 索引 | 协议名（GUI显示） | 标准号 | 字节序 | 校验算法 |
|------|------------------|--------|--------|----------|
| 0 | 南网协议 | Q/CSG1209021-2019 | 小端 | 8位位组算术和（不溢出） |
| 1 | PLC RF 协议（万胜海外） | 万胜 V1_04 | 大端 | 累加和 & 0xFF |
| 2 | HDLC/DLMS | IEC 62056-46 | 大端（网络序） | CRC-16/FCS（CCITT） |
| 3 | DLMS Wrapper 裸报文 | IEC 62056-46 | 大端 | 无（裸 APDU） |
| 4 | DLMS-APDU 裸报文 | IEC 62056-46 | 大端 | 无 |
| 5 | DLT645-2007 电表协议 | DL/T 645-2007 | BCD，地址低字节在前 | 累加和 & 0xFF |
| 6 | 国网协议 | Q/GDW 10376.2—2024 | 小端 | 8位位组算术和（不溢出） |
| 7 | 698.45 协议 | DL/T 698.45-2017 | 小端 | **CRC-16（crcmod 的 `x-25`）** |
| 8 | 新一代载波协议（通感一体化） | 通感一体化低压电力线宽带载波通信规约（2026校对版） | 小端 | CRC-32（MAC帧） |

---

## 2. 运行与打包

```bash
# 运行 GUI（唯一入口点）
python main_gui.py

# 运行 Web 版
streamlit run streamlit_app.py

# 打包 exe（两个 spec 的 datas 不同，见下方说明）
pyinstaller 协议解析工具.spec         # 完整版：custom_di.json + dlt645_di.json + gdw_custom_afn.json
pyinstaller 南网协议解析工具.spec       # 南网精简版：custom_di.json + dlt645_di.json
```

**依赖：**
- `pip install pyside6`（GUI 必需）
- `pip install streamlit`（Web 版）
- `pip install crcmod`（698.45 协议 CRC 校验，**1.7.0 起新增**）
- `pip install openpyxl`（Excel 测试报告，可选）

**运行环境注意：**
- Windows 优先；中文路径需保证 UTF-8 / GBK 编码兼容
- `main_gui.py` 内有 `_get_git_changelog()` 会调用 `git log`，无 git 环境时静默降级
- PyInstaller spec 文件中 `excludes` 列表用于减小体积（PyQt5/matplotlib/scipy/numpy 等）

---

## 3. 架构总览

```
main_gui.py                     # GUI主程序 (PySide6)，应用入口，~3600行，MainWindow 类
│                                #  - APP_VERSION、CHANGELOG（手写）+ _get_git_changelog()（动态）
│                                #  - current_protocol 硬编码索引(0~8)，见 §6
│                                #  - ConfigDialog：配置文件路径管理（自定义 JSON 路径）
│
├── 协议解析器（parser）── 每个返回嵌套 dict，字段约定见 §4
│   ├── protocol_parser.py          # 南网 (ProtocolFrameParser) ~4450行 [最大单文件]
│   │   └── protocol_tool.py          # ControlField(ctypes) + Frame(dataclass) 组帧
│   ├── gdw10376_parser.py          # 国网 (GDW10376Parser)
│   │   └── gdw10376_tool.py          # 国网控制域 + 常量
│   ├── plc_rf_parser.py            # PLC RF (PLCRFProtocolParser)
│   │   └── dlms_parser.py            # DLMS基础解析器 (DLMSParser)
│   ├── hdlc_parser.py              # HDLC/DLMS (HDLCParser)
│   ├── dlms_deep_parser.py         # DLMS-APDU深度解析 (DLMSDeepParser) - 双击表格行触发
│   ├── dlt645_parser.py            # DLT645-2007 (DLT645Parser)
│   ├── dl_t698_45_parser.py        # 698.45 链路层 (DLT69845Parser)
│   │   └── dl_t698_45_apdu_parser.py # 698.45 APDU (DLT69845APDUParser) - 延迟导入避免循环依赖
│   │       └── dl_t698_45_axdr.py     # A-XDR 编解码 (AXDRCoder, DL/T 790.6-2010)
│   │           └── dl_t698_45_oi_lookup.py  # OI 对象标识查询 (OILookup)
│   ├── csg_new_gen_parser.py       # 新一代载波 (CSGNewGenParser) ~4370行
│   │   └── csg_new_gen_cmd_payloads.py # 应用层命令业务数据单元解析
│   └── (新一代解析级别 auto/fc_pb/fc_only/app 由 _csg_parse_level 控制)
│
├── 查询/映射模块（lookup）── 单例 get_xxx_lookup() 提供全局实例
│   ├── obis_lookup.py              # OBIS码 (HDLC/DLMS)
│   ├── command_lookup.py           # PLC RF 命令字
│   ├── dlt645_di_lookup.py         # DLT645 DI
│   ├── gdw_afn_lookup.py           # 国网 AFN
│   └── (698.45 OI 查询内嵌于 dl_t698_45_oi_lookup.py)
│
├── 组帧/发送（frame generation）
│   ├── send_frame_lib.py           # 南网帧生成 (ProtocolFrameGenerator)
│   ├── gdw_send_frame_lib.py       # 国网帧生成 (GDWFrameGenerator)
│   ├── dl_t698_45_frame_gen.py     # 698.45 帧生成 (DLT69845FrameGenerator)
│   ├── dl_t698_45_frame_schema.py  # 698.45 组帧字段 schema
│   ├── frame_generator_schema.py   # 南网帧生成 UI schema (~165KB)
│   └── gdw_frame_generator_schema.py # 国网帧生成 UI schema
│
├── GUI 组件（独立文件，main_gui.py 导入组合）
│   ├── frame_gen_widget.py         # 帧生成标签页 (FrameGenWidget) - 支持 south/gdw/dlt698 三种模式
│   ├── preset_buttons.py           # 预设命令按钮 (PresetButtonWidget / PresetButtonManager)
│   ├── test_plan_widget.py         # 测试计划 (TestPlanWidget) - CRUD/顺序发送/超时/结果
│   ├── serial_worker.py            # 串口通信线程 (SerialWorker)
│   ├── gui_utils.py                # 中文右键菜单等工具
│   ├── archive_widget.py           # 档案管理 (ArchiveWidget) - 仅南网(0)/国网(6)
│   ├── topology_widget.py          # 拓扑信息 (TopologyWidget) - 仅南网(0)/国网(6)
│   └── streamlit_app.py            # Web 版（功能子集）
│
├── 验证引擎 validator/ ── BaseValidator + 各协议 validator，统一 ValidationResult
│   ├── __init__.py                 # 导出所有 validator
│   ├── base.py                     # BaseValidator(ABC) + ValidationResult/CheckItem/CheckLevel
│   │                                 # 内置 _calc_checksum_sum、_calc_crc16_ccitt 通用方法
│   ├── nw_validator.py             # 南网 (NWValidator)
│   ├── gdw_validator.py            # 国网 (GDWValidator)
│   ├── hdlc_validator.py           # HDLC/DLMS/Wrapper/APDU 共用 (HDLCValidator)
│   ├── plc_rf_validator.py         # PLC RF (PLCRFValidator)
│   ├── dlt645_validator.py         # DLT645 (DLT645Validator)
│   ├── dl_t698_45_validator.py     # 698.45 (DLT69845Validator) - 使用 crcmod
│   └── csg_new_gen_validator.py    # 新一代载波 (CSGNewGenValidator)
│
├── 监听/报表/模板/可视化编辑
│   ├── monitor/frame_monitor.py    # 实时帧监听器（串口数据自动解析）
│   ├── report/excel_reporter.py    # Excel 测试报告（需 openpyxl）
│   ├── templates/test_templates.py # 测试模板库
│   └── visual_editor/test_item_editor.py # 可视化测试项编辑器
│
├── 数据提取/生成脚本（一次性或离线使用，不要打包）
│   ├── generate_dlt645_di.py       # 生成 dlt645_di.json（勿手动编辑该 JSON）
│   ├── generate_oi_lookup.py       # 生成 dl_t698_45_oi_lookup.py 中的 OI_NAME_MAP
│   ├── extract_69845_classes.py    # 从 698.45 文档抽取类定义 → extracted_classes.json
│   ├── extract_oi_to_class.py      # 生成 oi_to_class.json
│   ├── convert_docx_to_md.py       # docx → md 转换（新一代协议文档使用）
│   ├── extract_pdf.py / extract_doc_fields.py / extract_di_definitions.py
│   ├── analyze_frame.py / analyze_fields.py / analyze_lme_ids.py
│   ├── gap_analysis.py / create_work_list.py / search_di.py
│   └── lme_info_entry_parser.py    # LME 信息条目解析
│
└── 数据文件（运行时读写，需随打包/版本管理）
    ├── custom_di.json              # 南网自定义DI（GUI 增删）
    ├── gdw_custom_afn.json         # 国网自定义AFN+Fn（GUI 增删）
    ├── dlt645_di.json              # DLT645 DI 映射（generate_dlt645_di.py 生成，勿手改）
    ├── dlt645_di_custom.json       # DLT645 自定义 DI（GUI 增删）
    ├── NW_command.json             # 南网预设命令
    ├── GW_command.json             # 国网预设命令
    ├── command.json                # PLC RF 命令字
    ├── config.json                 # 串口配置
    ├── test_plan.json              # 测试方案（自动持久化）
    ├── archive_data.json           # 档案数据（持久化）
    ├── lme_all_tables.json         # LME 全表数据（解析缓存）
    ├── lme_info_entries.json       # LME 信息条目缓存
    ├── oi_to_class.json            # 698.45 OI→类映射
    └── extracted_classes.json      # 698.45 类定义抽取结果
```

**数据流（核心调用链）：**
```
用户输入 hex
  → main_gui.py 根据 current_protocol 选择 parser
    (0:ProtocolFrameParser / 1:PLCRFProtocolParser / 2~4:HDLCParser / 5:DLT645Parser
     6:GDW10376Parser / 7:DLT69845Parser(+APDUParser+AXDRCoder) / 8:CSGNewGenParser)
  → parser.parse(frame_bytes) 返回结构化嵌套 dict
  → GUI: QTableWidget 展示分层 + 字节高亮（点击行联动输入框）
  → 可选: 校验（validator.verify()）、DLMS 深度弹窗（双击 DLMS APDU 行）
```

---

## 4. 关键约定

### 4.1 代码风格
- **类名** CamelCase：`ProtocolFrameParser`、`CSGNewGenParser`
- **函数/变量** snake_case：`parse_frame`、`current_protocol`
- **常量** UPPER_CASE：`AFN_MAP`、`DI_COMBINATION_MAP`、`MSG_PORT_MAP`
- GUI 代码集中在 `main_gui.py` 单文件，`MainWindow` 类约 2500 行；**新增 UI 组件必须拆分到独立文件**（参考 `frame_gen_widget.py`），由 `main_gui.py` 导入组合
- 所有 parser 返回**嵌套 dict**，禁止返回自定义类给 GUI 层

### 4.2 解析结果 dict 标准字段
所有 parser 返回的 dict 中关键中文键名（GUI 表格列直接读取）：
- `原始值` / `原始字节` — 十六进制原始数据
- `十进制` / `解析值` — 解析后的数值
- `说明` / `名称` / `业务说明` — 中文描述
- `偏移` / `长度` — 字节定位（用于高亮）

### 4.3 字节序（**极易出错，务必逐协议确认**）
- **南网(0) / 国网(6) / 698.45(7) / 新一代(8)**：长度域、DI、多字节字段 → **小端序 (little-endian)**
- **HDLC/DLMS(2,3,4)**：网络字节序 **big-endian**
- **DLT645(5)**：BCD 编码，地址域低字节在前
- **PLC RF(1)**：大端
- ASCII / BCD 字段经常需要"反转后解析"，参考 CHANGELOG 1.6.4~1.6.7 的字节序修复历史

### 4.4 校验和 / CRC
- 南网(0)：控制域 + 用户数据区的 8 位位组算术和（不考虑溢出）
- 国网(6)：同南网（控制域 + 用户数据区算术和）
- DLT645(5)：所有字节累加和 `& 0xFF`
- HDLC(2)：CRC-16/FCS（CCITT，`base.py:_calc_crc16_ccitt`）
- **698.45(7)：`crcmod.predefined.Crc('x-25')`**（CRC16），HCS 覆盖"长度域+控制域+地址域"，FCS 覆盖"长度域…链路用户数据"
- 新一代(8)：MAC 帧 CRC-32

### 4.5 自定义数据持久化
| 文件 | 内容 | 来源 |
|------|------|------|
| `custom_di.json` | 南网自定义 DI | GUI 运行时增删 |
| `gdw_custom_afn.json` | 国网自定义 AFN+Fn | GUI 运行时增删 |
| `dlt645_di_custom.json` | DLT645 自定义 DI | GUI 运行时增删 |
| `dlt645_di.json` | DLT645 标准 DI 映射 | `generate_dlt645_di.py` 生成，**勿手改** |
| `dl_t698_45_oi_lookup.py` 内 `OI_NAME_MAP` | 698.45 OI 名称 | `generate_oi_lookup.py` 生成 |
| `oi_to_class.json` | 698.45 OI→类 | `extract_oi_to_class.py` 生成 |

### 4.6 HDLC 字节填充（透明传输）
- `7E` 在帧内 → 转义为 `7E 5D`
- `7D` → 转义为 `7D 5D`
- 解析器自动还原，**组帧时也必须处理**（否则生成的帧非法）

---

## 5. 协议 → 解析器 → 参考文档 完整映射

> **遇到协议定义不确定时，必须按本表检索对应文档，禁止凭记忆推断。**
> 文档路径均为**项目根目录**下的相对路径（新一代协议文档在子目录）。

### 5.1 南网协议（索引 0）
- **解析器**：`protocol_parser.py` (ProtocolFrameParser) + `protocol_tool.py` (ControlField/Frame)
- **组帧**：`send_frame_lib.py` + `frame_generator_schema.py`
- **校验器**：`validator/nw_validator.py`
- **参考文档**：
  - `PLUZ计量自动化系统技术规范.md` — **主协议文档**，帧结构/AFN/DI 定义
  - `LME产品相关信息生产运维接口手册_V2.4_251115.md` — 详细信息条目定义（docx 同名源文件可转换）
  - `低压电力线宽带载波深化应用技术手册v1.1.md` — **深化应用**（台区识别/交采/模块资产）专用
  - `1.md` / `1-1.md` / `2.md` — 早期协议文档（Markdown）
  - `2.pdf` — Q/CSG1209021-2019 原始 PDF

### 5.2 PLC RF 协议（索引 1，万胜海外）
- **解析器**：`plc_rf_parser.py` (PLCRFProtocolParser) + `dlms_parser.py` (DLMSParser 基类)
- **查询**：`command_lookup.py`
- **校验器**：`validator/plc_rf_validator.py`
- **参考文档**：`4.md`（万胜 V1_04 协议）

### 5.3 HDLC / DLMS（索引 2/3/4）
- **解析器**：`hdlc_parser.py` (HDLCParser) + `dlms_deep_parser.py` (DLMSDeepParser，双击触发)
- **查询**：`obis_lookup.py`
- **校验器**：`validator/hdlc_validator.py`（Wrapper/APDU 复用）
- **参考文档**：
  - `HDLC.md` — HDLC 帧格式详解
  - `HDLC解析说明.md` — 解析实现说明
  - `IEC 62056-46.PDF` — IEC 国际标准
  - `DLMS_Protocol.md` / `DLMS_Protocol.pdf` — DLMS 协议

### 5.4 DLT645-2007（索引 5）
- **解析器**：`dlt645_parser.py` (DLT645Parser)
- **查询**：`dlt645_di_lookup.py` + `dlt645_di.json`
- **校验器**：`validator/dlt645_validator.py`
- **参考文档**：
  - `DLT645-2007.md` — 主协议（Markdown）
  - `DLT645-2007 多功能电表通信协议.pdf` — 原始 PDF
  - `国网计量中心电能表全性能试验检测公告-第4号补遗-事件记录采集-远程费控功能和负荷曲线抄读功能.pdf` — 补遗（PDF，需用 pdf skill 检索）

### 5.5 国网协议（索引 6）
- **解析器**：`gdw10376_parser.py` (GDW10376Parser) + `gdw10376_tool.py`
- **组帧**：`gdw_send_frame_lib.py` + `gdw_frame_generator_schema.py`
- **查询**：`gdw_afn_lookup.py`
- **校验器**：`validator/gdw_validator.py`
- **参考文档**：`集中器本地通信模块接口-2024.md`（Q/GDW 10376.2—2024，**严格依据此文档解析**）

### 5.6 DL/T 698.45-2017（索引 7，**1.7.0 新增**）
- **解析器**：
  - `dl_t698_45_parser.py` (DLT69845Parser) — 链路层帧（68 L L C SA CA [HCS] [APDU] [FCS] 16）
  - `dl_t698_45_apdu_parser.py` (DLT69845APDUParser) — APDU 服务类型（GET/SET/ACTION/REPORT/PROXY/LINK/CONNECT...）
  - `dl_t698_45_axdr.py` (AXDRCoder) — **A-XDR 编解码**（依据 DL/T 790.6-2010）
  - `dl_t698_45_oi_lookup.py` (OILookup) — OI 对象标识查询
- **组帧**：`dl_t698_45_frame_gen.py` + `dl_t698_45_frame_schema.py`
- **校验器**：`validator/dl_t698_45_validator.py`
- **依赖**：`crcmod`（`Crc('x-25')`）
- **参考文档**：`面向对象的用电信息数据交换协议(20210910).md`
  - **CRC 范围**：文档明确定义 HCS/FCS 各自覆盖的字段，**哪些字段参与 CRC 必须查文档**
  - **A-XDR 编码**：APDU 内部所有数据用 A-XDR，tag 高 3 位 = 010

### 5.7 新一代载波协议 / 通感一体化（索引 8，**1.7.0 新增**）
- **解析器**：
  - `csg_new_gen_parser.py` (CSGNewGenParser) — MAC 帧（MPDU/MAC头/MSDU/CRC-32）+ 应用层业务报文
  - `csg_new_gen_cmd_payloads.py` — 应用层命令业务数据单元解析（依据第5部分）
- **校验器**：`validator/csg_new_gen_validator.py`
- **GUI 特性**：协议索引 8 时显示"解析级别"下拉（auto / fc_pb / fc_only / app），由 `_csg_parse_level` 控制
- **参考文档**（位于 `南网新一代20260226校对/南网新一代20260226校对/` 子目录，每部分同时有 .docx 和 .md）：
  - `1-通感一体化低压电力线宽带载波通信规约 第1部分 总则（文本校对）.md` — 总则
  - `2-...第2部分 技术要求（文本校对）_力合微_20260304.md` — 技术要求
  - `3-...第3部分 物理层通信协议（文本校对）.md` — 物理层
  - `4-...第4部分 数据链路层通信协议 （文本校对）.md` — **数据链路层（MAC/MSDU 帧格式）**
  - `5-...第5部分 应用层通信协议（文本校对）.md` — **应用层（业务报文结构）**
  - `6-...第6部分：检验规范（文本校对）.md` — 检验规范
  - 源 docx 可用 `convert_docx_to_md.py` 重新转换

---

## 6. GUI 协议集成点（添加/修改协议必读）

`current_protocol` 索引在 `main_gui.py` **硬编码**，添加新协议必须**同时**修改以下位置（用 grep 定位）：

| 位置 | 行为 |
|------|------|
| `MainWindow.__init__`（~L285） | 注释列出索引含义，并初始化对应 parser 实例 |
| `protocol_combo.addItem`（~L347-354） | 添加下拉项（顺序即索引） |
| `_on_protocol_changed`（~L1300+） | 协议切换：输入提示 / 查询页 / 各 Tab 可见性 |
| `_extract_frames_for_protocol`（~L1409+） | 多帧提取逻辑（不同协议起始符不同） |
| `_parse_single_frame`（~L2195+） | 选择 parser 调用 |
| `_update_protocol_lookup_tab`（~L1434+） | 查询标签页内容（DI/AFN/OBIS/命令字/业务标识） |
| `_run_validation`（~L2353+） | validator 字典映射 |
| `setTabVisible`（~L1342-1386） | 组帧/预设(0,6,7)、档案(0,6)、拓扑(0,6) 可见性 |

**Tab 可见性规则：**
- 组帧 / 预设命令：南网(0) / 国网(6) / 698.45(7) — 三种模式 `south` / `gdw` / `dlt698`
- 档案管理 / 拓扑信息：仅南网(0) / 国网(6)
- 新一代解析级别下拉：仅索引 8

---

## 7. 测试

**没有正式测试框架**（无 pytest / unittest 配置）。`test_*.py` 是独立脚本，直接运行：

```bash
# 长期维护的核心测试
python test_dlms.py            # DLMS 基础
python test_hdlc.py            # HDLC 帧
python test_plc_rf.py          # PLC RF
python test_ber_tlv.py         # BER-TLV 编码
python test_actual_hdlc.py     # 真实 HDLC 报文
python test_special_frame.py   # 特殊帧
python test_snrm_frame.py      # SNRM 帧
python test_dl_t698_45.py      # 698.45 协议
python test_oad_enrichment.py  # 698.45 OAD 增强
python test_csg_new_gen.py     # 新一代载波协议
python test_plan_widget.py     # 测试计划组件（需 GUI 环境）

# 调试用临时脚本（可清理）：test_mac_*.py / test_msdu_debug.py / test_user_frame.py / test_full_debug.py / test_len_debug.py
```

每个脚本内含**硬编码测试帧 + 预期输出**，用 `assert` 或 `print` 对比。新增解析逻辑时，应同步在对应 `test_xxx.py` 增加用例。

---

## 8. 常见陷阱（**修改前必读**）

1. **`_clear_layout` 递归销毁**（`main_gui.py`）：递归删除所有子 widget。改查询标签页逻辑时必须理解此方法，否则 widget 残留或崩溃。
2. **`current_protocol` 硬编码索引**：见 §6，添加协议要改 8+ 处。
3. **PyInstaller spec 的 datas 不同**：
   - `协议解析工具.spec`：`custom_di.json` + `dlt645_di.json` + `gdw_custom_afn.json`，`excludes` 较多
   - `南网协议解析工具.spec`：仅前两个，`excludes` 为空
   - **新增需打包的数据文件，两个 spec 都要同步**
4. **DLMS 深度解析是双击触发**，不是自动：双击表格中 `DLMS APDU` 行才弹 `dlms_deep_parser`。
5. **HDLC 字节填充**：组帧时 7E/7D 必须转义（见 §4.6）。
6. **698.45 CRC 范围**：HCS / FCS 覆盖字段不同，必须查文档，不能照抄南网/国网。
7. **698.45 APDU 解析器延迟导入**：`dl_t698_45_parser.py` 用 `@property apdu_parser` 延迟初始化，避免循环依赖。
8. **新一代载波解析级别**：`auto` 模式会自动判断是完整 MPDU 还是仅 FC 还是应用层；调试特定层时切到 `fc_only` / `app`。
9. **字节序修复历史**：1.6.4~1.6.7 系统性修复了多字节字段小端序、ASCII/BCD 反转问题。改多字节字段解析时参考此段历史，避免回退。
10. **`dlt645_di.json` 勿手改**：由 `generate_dlt645_di.py` 生成；`OI_NAME_MAP` 由 `generate_oi_lookup.py` 生成。
11. **新一代载波协议(8)批量解析的监控前缀剥离时机**：`_strip_csg_monitor_prefix` **必须在 `_clean_hex_input` 之前调用**（在 `parse_batch` 内）。因为监控标记 `-> 接收机 Has Get` 含中文/箭头，若先清洗 hex 会破坏标记导致无法定位 15 字节监控头边界。改批量解析流程时注意此顺序。

---

## 9. 开发原则

1. **协议定义优先**：遇到不确定的协议字段、字节序、校验范围，**先查 §5 对应文档**，不要凭记忆或猜测。
2. **PDF 文档用 pdf skill 检索**：645 补遗、IEC 62056-46、DLT645 原始标准都是 PDF，调用 pdf skill 而非人工翻阅。
3. **新增协议的完整 checklist**：
   - [ ] 新建 `xxx_parser.py`，返回嵌套 dict（键名遵循 §4.2）
   - [ ] 在 `main_gui.py` import + 初始化 parser 实例
   - [ ] 添加 `protocol_combo.addItem`（注意索引顺序）
   - [ ] 在 `_on_protocol_changed` / `_parse_single_frame` / `_extract_frames_for_protocol` / `_update_protocol_lookup_tab` 加分支
   - [ ] 新建 `validator/xxx_validator.py` 继承 `BaseValidator`，在 `_run_validation` 注册
   - [ ] 同步更新本文件 §1（协议表）、§3（架构）、§5（文档映射）、§6（集成点）
   - [ ] 新建 `test_xxx.py`，含硬编码测试帧
   - [ ] 如需打包，更新 spec 的 `datas`
4. **解析器独立性**：parser 之间避免横向耦合；公共逻辑放 `base.py` 或工具模块。
5. **GUI 组件拆分**：新 UI 组件独立成文件，`main_gui.py` 只负责组合。
6. **中文键名保持一致**：`原始值`/`十进制`/`说明` 等，GUI 表格列直接读这些键。
7. **字节序显式**：`int.from_bytes(data, 'little'/'big')` 必须显式写参数，禁止依赖默认。
8. **CHANGELOG 即时维护**：完成功能后，在 `main_gui.py` 的 `CHANGELOG` 列表头部新增条目（版本号/日期/要点），并在 §10 同步。

---

## 10. 变更日志（与 `main_gui.py:CHANGELOG` 保持同步）

> 本节按版本倒序记录。详细 commit 见 `git log`。每发新版本必须更新此处。

### 1.7.1 — 2026-06-18
- **新一代载波协议(索引8)批量解析**：新增监控日志前缀剥离预处理
- 监控日志格式：`<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>`
- `parse_batch` 在协议8下先调用 `_strip_csg_monitor_prefix` 剥离 `-> 接收机 Has Get` 标记及其后 15 字节监控头，再做 hex 清洗
- 新增 `_extract_csg_new_gen_frames` 专用帧提取（按行 + 短行过滤 + 字节对齐兜底）
- 新增测试 `test_csg_batch_prefix.py`（8 个用例，含精确 15 字节剥离验证与时间戳/测试标记过滤验证）
- **修复**：`_strip_csg_monitor_prefix` 对不含监控前缀且非纯 hex 的日志行（如 `15:48:16 013 -> ...测试标记...`）不再原样保留，避免时间戳/中文/特殊符号被 `_clean_hex_input` 清洗成伪帧
- **新一代载波协议(索引8)批量解析摘要**：区分网络层/应用层报文展示关键业务内容
  - 网络层管理消息：摘要体现 MMTYPE 解析（如 `网络层 | MMTYPE:关联请求(MMeAssocReq) | 版本1`）
  - 网络层 MPDU/MAC 帧：体现定界符类型 + 源/目的TEI
- 应用层报文：体现 MSDU 类型 + 帧类型 + 业务标识 + 方向 + 核心内容（如 `应用层报文 | 确认/否认 | 业务标识:否认 | 下行(CCO→STA) | 原因:通信超时`）
- 新增/更新 `_get_csg_new_gen_summary`：优先取 `MSDU类型` 字段作为顶层分类，管理消息/定界符帧/应用层报文均体现 MSDU 类型
- 新增测试 `test_csg_summary.py`（6 个用例，覆盖确认/否认/管理消息/TEI回复/格式可读性/MSDU类型展示）

### 1.7.0 — 2026-06-18
- **新增 DL/T 698.45-2017 协议（索引7）**：链路层解析、APDU 解析、A-XDR 编解码、OI 查询、帧生成、校验器
- **新增 新一代载波协议/通感一体化（索引8）**：MAC/MSDU 帧 + 应用层业务报文解析、命令载荷解析、校验器
- 新一代协议支持 4 种解析级别切换（auto/fc_pb/fc_only/app）
- 新一代协议业务标识查询页面
- 组帧/预设标签页扩展支持 698.45（`dlt698` 模式）
- 新增 `crcmod` 依赖（698.45 CRC 用 `x-25`）
- **新增文件**：`dl_t698_45_*.py`（parser/apdu/axdr/oi_lookup/frame_gen/frame_schema）、`csg_new_gen_parser.py`、`csg_new_gen_cmd_payloads.py`、`validator/dl_t698_45_validator.py`、`validator/csg_new_gen_validator.py`、`convert_docx_to_md.py`、`南网新一代20260226校对/`（6 部分协议文档 md+docx）

### 1.6.8 — 2026-05-09
- 档案管理：修复缺失 json 导入导致导出失败
- 档案管理：修复协议切换时错误清空档案数据
- 拓扑信息：新增组网完成时间统计（自动刷新模式）；TEI 搜索改为精确匹配；组网完成判定支持比例/数量两种模式；多字段节点搜索（TEI/地址/角色）

### 1.6.7 — 2026-04-30
- 修复南网协议 DI 字节序解析（恢复小端序，修复 DI 查找匹配）
- 修复查询运行参数(E8 03 03 74)数据内容解析 IndexError
- 修复国网验证器长度域校验逻辑
- 南网/国网控制域位域显示二进制位值（D7~D0），国网信息域（D0~D7）

### 1.6.6 — 2026-04-30
- 修复 DI 解析字节序，恢复小端序正确匹配 DI_COMBINATION_MAP

### 1.6.5 — 2026-04-22
- 系统性修复字节序：多字节字段统一小端序；ASCII/BCD 字段反转；所有 `int.from_bytes` 改 little；组帧引擎默认小端

### 1.6.4 — 2026-04-22
- 修复 BCD 日期/版本号解析（按 BCD 原值显示，多字节小端反转）

### 1.6.3 — 2026-04-22
- 添加任务字段优化：任务模式字位域拆分（响应/转发/优先级），报文内容拆分（业务代码+有效内容），引擎支持 sub_fields 位域合并

### 1.6.2 — 2026-04-22
- 字段定义修正：移除多余字段、补充缺失字段、修复字段名与文档不匹配

### 1.6.1 — 2026-04-22
- 协议组帧完善：支持 88 个下行 DI 命令；命令说明弹窗非模态；串口通信支持配置/发送/日志/接收解析

### 1.6.0 — 2026-04-21
- **新增国网协议（Q/GDW 10376.2-2024）**：AFN+Fn 组合查询、单帧/批量解析、字节高亮

### 1.5.0 — 2026-04-17
- 重构主界面，精简 GUI 代码；增强南网解析器；优化 PyInstaller 配置

### 1.4.0 — 2026-04-16
- 修复表格交替行颜色；新增 AGENTS.md；PyInstaller datas 修复

### 1.3.0 — 2026-04-16
- 修复查询页切换按钮残留；修复命令字查询缺失方法；新增菜单栏与"关于"对话框

### 1.2.0 — 2026-04-16
- 优化 HDLC 解析，修复 APDU 索引错误；新增 Wrapper 帧提取

### 1.1.0 — 2026-04-15
- 优化 HDLC 对返回数据/未知响应的处理；改善协议选择与输入提示

### 1.0.0 — 2026-04-14
- 初始版本：南网/PLC RF/HDLC/DLMS 多协议解析；单帧/批量解析；DI/命令字/OBIS 查询

---

## 11. 最新变更摘要（最近一次 commit 摘要）

> 此处记录最近一次开发会话的修改要点，方便新 Agent 快速定位"刚改了什么"。每次提交后更新。

**最近一次（2026-06-18，待提交）：新一代载波协议(索引8)业务摘要增加 MSDU 类型展示**

需求：批量解析表格「业务摘要」列需把 MSDU 类型和业务标识同时体现出来，便于快速识别报文类别。

修改：
- `main_gui.py` `_get_csg_new_gen_summary`：优先读取 `MSDU类型` 字段作为顶层分类前缀；
  - 管理消息：`<MSDU类型> | MMTYPE:... | 版本x`（如 `网络管理消息 | MMTYPE:关联请求(MMeAssocReq) | 版本1`）
  - MPDU/MAC 物理层帧：`<MSDU类型> | <定界符类型> | 源/目的TEI`
  - 应用层报文：`<MSDU类型> | <帧类型> | 业务标识:... | 方向 | 核心内容`（如 `应用层报文 | 确认/否认 | 业务标识:确认 | 下行(CCO→STA)`）
  - 无 MSDU 类型字段时（如 parse_level=app）保持原有 "应用层"/"网络层" 兜底前缀
- `test_csg_summary.py`：
  - 同步更新 `get_csg_new_gen_summary` 测试辅助函数
  - 新增 `test_msdu_type_in_summary` 用例验证完整 MAC 帧解析时摘要同时展示 MSDU 类型与业务标识

**上一次（2026-06-18，待提交）：修复新一代载波协议(索引8)批量解析误将时间戳/测试标记行解析为伪帧的问题**

涉及文件：
- 新增：`csg_new_gen_parser.py`、`csg_new_gen_cmd_payloads.py`、`validator/csg_new_gen_validator.py`、`convert_docx_to_md.py`
- 新增测试：`test_csg_new_gen.py`、`test_mac_*.py`、`test_msdu_debug.py`、`test_user_frame.py`、`test_full_debug.py`、`test_len_debug.py`
- 新增协议文档：`南网新一代20260226校对/`（6 部分 .md + .docx）
- 修改：`main_gui.py`（协议索引8、解析级别下拉、业务标识查询页、validator 注册）、`validator/__init__.py`、`dl_t698_45_frame_gen.py`、`dl_t698_45_frame_schema.py`、`frame_gen_widget.py`

**上一次（2026-05-23，commit `5987370`）：新增 DLT698.45-2017 协议支持**
- 新增 6 个 `dl_t698_45_*.py` 模块、`validator/dl_t698_45_validator.py`、`test_dl_t698_45.py`、`test_oad_enrichment.py`
- GUI 集成协议索引 7、组帧 schema、OI/类抽取脚本

---

## 12. 其他参考文档

- `QWEN.md` — 项目详细文档（中文），含协议帧格式说明和开发约定（**部分内容可能滞后，以本文件为准**）
- `README.md` — 用户面向的简要说明（功能列表，偏旧，未含 698.45/新一代协议）
- `CLAUDE.md` — Claude Code 专用指南（与本文档部分重叠，**以 AGENTS.md 为权威**）
- `work_list.md` — 工作清单/字段定义（开发参考）
- `docs/superpowers/specs/2026-05-12-dl-t698-45-parser-design.md` — 698.45 解析器设计规格
- `docs/superpowers/plans/2026-05-12-dl-t698-45-parser.md` — 698.45 实现计划
- `docs/superpowers/specs/2026-05-09-topology-formation-timing-design.md` — 拓扑组网时序设计
- `.sisyphus/plans/csg_new_gen_parser.md` — 新一代载波解析器实现计划

> **冲突处理**：当 AGENTS.md 与 QWEN.md / CLAUDE.md / README.md 内容冲突时，**以 AGENTS.md 为准**。本文档随代码同步更新。

---

## 13. Agent 上手 Checklist

接手项目时按以下顺序操作：

- [ ] 通读本文件（§1~§9 是核心，§10~§11 是最新动态）
- [ ] `python main_gui.py` 启动 GUI，逐个协议切下拉框，确认能跑
- [ ] 查 `git log --oneline -20` 了解最近提交
- [ ] 查 `git status` 了解未提交改动
- [ ] 根据**要修改的协议**，按 §5 找到对应 parser 和参考文档
- [ ] 修改前查 §8 陷阱，修改后按 §9 原则自检
- [ ] 完成后更新 §10 CHANGELOG 和 §11 最新变更摘要
