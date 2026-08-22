<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

---

# 南网协议解析工具 — Agent 指南

> 本文档是所有 AI Coding Agent / 模型接手本项目时的**唯一权威上手文档**。
> 阅读本文档后应能完全掌握：项目架构、模块职责、协议→解析器→参考文档的映射、字节序/校验/编码约定、开发原则、最新变更与陷阱。
>
> **维护原则**：每次合并 PR / 完成功能后，请同步更新 §10「变更日志」与 §11「最新变更摘要」。如新增协议或解析器，必须更新 §2、§3、§5、§7。

---

## 1. 项目概览

多种电力通信协议的图形化解析工具。单代码库，纯 Python 3.8+，无构建系统，无正式测试框架。当前版本见 `main_gui.py:APP_VERSION`（现 `1.14.1`）。

**支持的协议（共 12 种，对应 GUI 协议下拉框 `current_protocol` 索引）：**

| 索引 | 协议名（GUI显示） | 标准号 | 字节序 | 校验算法 |
|------|------------------|--------|--------|----------|
| 0 | 南网协议 | Q/CSG1209021-2019 | 小端 | 8位位组算术和（不溢出） |
| 1 | PLC RF 协议（万胜海外） | 万胜 V1_04 | 大端 | 累加和 & 0xFF |
| 2 | HDLC/国网DLMS | IEC 62056-46 | 大端（网络序） | CRC-16/FCS（CCITT） |
| 3 | DLMS-APDU(国网) | IEC 62056-46 | 大端 | 无 |
| 4 | DLMS Wrapper 裸报文 | IEC 62056-46 | 大端 | 无（裸 APDU） |
| 5 | DLMS-APDU 裸报文 | IEC 62056-46 | 大端 | 无 |
| 6 | DLT645-2007 电表协议 | DL/T 645-2007 | BCD，地址低字节在前 | 累加和 & 0xFF |
| 7 | 国网协议 | Q/GDW 10376.2—2024 | 小端 | 8位位组算术和（不溢出） |
| 8 | 698.45 协议 | DL/T 698.45-2017 | 小端 | **CRC-16（crcmod 的 `x-25`）** |
| 9 | 新一代载波协议（通感一体化） | 通感一体化低压电力线宽带载波通信规约（2026校对版） | 小端 | CRC-32（MAC帧） |
| 10 | 国网新一代双模通信互联互通 | 国网新一代双模通信互联互通技术规范 | 小端 | CRC-32（MAC帧） |
| 11 | HDC 1.0 双模互联互通 | Q/GDW 12087.42-2020 | 小端（MAC 地址大端） | CRC-24（FC/PB）+ CRC-32（MAC） |

> 协议覆盖差异：**HDC 1.0（索引 11）目前仅在 PySide6 主程序支持**；Reflex Web 版支持索引 0-10（11 种）。NiceGUI/TUI 版本已于 2026-08-17 移除。修改协议相关文档/代码时注意区分。

---

## 2. 运行与打包

```bash
# 运行 GUI（唯一入口点）
python main_gui.py

# 运行 Reflex Web 版（实验性）
python reflex_web/run_app.py

pyinstaller 南网协议解析工具.spec --noconfirm   # 主程序单文件 EXE
pyinstaller reflex_web/reflex_web_exe.spec      # Reflex Web 版 EXE（可选）
```

**GUI 命令行参数（系统集成）：**
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

**依赖：**
- `pip install pyside6`（GUI 必需）
- `pip install crcmod`（698.45 协议 CRC 校验，**1.7.0 起新增**）
- `pip install openpyxl`（Excel 测试报告，可选）
- `pip install lupa`（测试方案 Lua 脚本引擎，**1.8.1 新增**，未安装时静默降级为不可用）
- `pip install scapy`（TCP 流量监控，Windows 需另装 npcap，未就绪时标签页提示但不影响其他功能）
- `pip install reflex`（Reflex Web 版，实验性）
- Reflex Web 在线/离线依赖以 `reflex_web/requirements.in` + `reflex_web/requirements.lock` 为准，至少包含 `reflex`、`uvicorn`、`crcmod`、`websockets`

**运行环境注意：**
- Windows 优先；中文路径需保证 UTF-8 / GBK 编码兼容
- 当前主程序保留 `南网协议解析工具.spec`（单文件 EXE），打包 `custom_di.json`、`dlt645_di.json`、`gdw_custom_afn.json`、`icons/` 与 `enhanced_export.py` 等资源；新增需打包的数据文件时必须检查该 spec
- `reflex_web/reflex_web_exe.spec` 负责 Reflex Web 版打包；开发模式先执行 `cd reflex_web && reflex export --frontend-only --env prod --no-zip`
- Lua 脚本引擎依赖 `lupa`，打包时需作为 hidden import 或确保运行环境已安装
- 当前主程序 spec 未显式声明 `scapy`；如需把 TCP 监控打包进 exe，需补充 `scapy` 依赖并确保目标机器安装 npcap
- `docs/Lua脚本使用说明.md` 是 Lua 功能的用户文档
- Inno Setup 安装脚本 `南网解析工具.iss` / `2222.iss` 中 `MyAppVersion` 仍为 `1.7.2`，发版时需手动同步

### Reflex Web 离线源码部署（UV）

局域网目标服务器没有外网时，使用 `reflex_web/build_offline_deploy.py` 在有网机器上生成一个可整体复制的部署目录：

```bash
python reflex_web/build_offline_deploy.py
```

该脚本会按以下顺序工作：

1. 读取 `reflex_web/requirements.in`，执行 `uv pip compile` 并覆盖 `reflex_web/requirements.lock`
2. 检查 `reflex_web/.web/build/client`；缺失时尝试执行 `reflex export --frontend-only --env prod --no-zip`
3. 把运行所需源码、JSON 数据、`validator/`、`reflex_web/` 复制到 `dist/reflex_web_offline/`
4. 用 `uv venv --relocatable` 创建 `.venv` 并安装锁定依赖
5. 生成 `start_web.cmd` 和 `start_web.sh`

目标服务器无网部署：

```text
复制整个 dist/reflex_web_offline/ 目录到目标服务器
Windows: start_web.cmd
Linux:   ./start_web.sh
访问:    http://服务器IP:8080
```

后续维护规则：

- **新增任何 Python 依赖时，先改 `reflex_web/requirements.in`，不要只改 `requirements.txt`；再重跑上面的构建脚本**
- **修改 Reflex Web 页面/后端逻辑后，必须重跑脚本**，确保 `.venv` 与 `reflex_web/.web/build/client` 都是最新版本
- `.venv` 只能复制到与构建机相同操作系统、相同 CPU 架构、相同 Python 大版本的目标机；目标机仍需要安装同版本 Python，`.venv` 不包含解释器本体
- `reflex_web/.web` 是前端构建产物，默认被 `.gitignore` 排除，不能只用 git clone 代替部署目录拷贝
- 当前脚本输出默认在 `dist/reflex_web_offline/`，该路径已被 `.gitignore` 排除，实际部署产物不进入版本库
- 详细说明见 `reflex_web/离线部署.md`

### Reflex Web 内嵌 Python 部署（推荐，零安装）

目标机器无需安装 Python，解压即用。使用 `reflex_web/build_embedded_deploy.py`：

```bash
python reflex_web/build_embedded_deploy.py --python-version 3.12
```

该脚本会：

1. 下载 Python embeddable 包（Windows）或用 UV 安装 Python（Linux）
2. 在部署目录中安装 pip 和所有依赖
3. 复制运行时文件和预编译前端
4. 生成启动脚本

部署：把 `dist/reflex_web_embedded/` 整个目录复制到目标服务器，运行 `start_web.cmd` 或 `./start_web.sh`。

**与 UV 方案的区别：** 目标机器不需要安装 Python，但部署目录体积更大（~30MB 额外）。Windows 构建的目录只能在 Windows 上运行，Linux 同理。

**增量构建原则（重要）：**

内嵌部署目录内含解释器 + site-packages 依赖（约 100MB+），完整重装每次需下载 Python 包并
重新 pip 安装全部依赖（可达 10+ 分钟）。但**源码和依赖几乎不动，真正变化的只有你改的 parser/gui/web
那几个 .py 文件**。因此：

- **日常迭代（改源码/数据文件）**：用增量模式，复用已有 `python/` 目录，只刷新源码层，秒~分钟级：
  ```bash
  python reflex_web/build_embedded_deploy.py --skip-deps
  ```
- **首次构建 / 改依赖 / 换 Python 版本**：才用完整模式（重新下载解释器 + 装依赖，10+ 分钟）：
  ```bash
  python reflex_web/build_embedded_deploy.py --python-version 3.12
  ```
- 增量模式逻辑：先移走 `out_dir/python/`，重建其余目录，再移回——保留解释器与依赖，仅刷新源码/数据/前端。
- `--skip-deps` 的前提是目标部署目录 `dist/reflex_web_embedded/python/` 已存在且完整（来自上次完整构建）。
- 依赖锁文件 `requirements.lock` 存在且不旧于 `requirements.in` 时，uv 编译自动跳过（依赖未变则复用）。
- 若不慎删了 `dist/reflex_web_embedded/python/`，需回到完整模式重建一次。

**编译原则（exe打包）：**

1. **窗口标题包含编译日期**：每次打包前必须更新 `main_gui.py` 中的 `BUILD_DATE` 变量为当前日期（格式：`YYYY-MM-DD`）
   ```python
   APP_VERSION = "1.13.0"
   BUILD_DATE = "2026-08-14"  # 编译日期，每次打包前更新
   ```
   窗口标题格式：`协议解析工具 v{APP_VERSION} ({BUILD_DATE})`

2. **exe 文件名自动带版本号+时间戳**：`南网协议解析工具.spec` 顶部从 `main_gui.py` 的 `APP_VERSION` 自动读取版本号，输出名固定为 `南网协议解析工具_v{APP_VERSION}_{YYYYMMDDHHMMSS}.exe`（时间戳精确到秒）。窗口标题版本号与 exe 文件名版本号**天然对齐**（同一数据源），无需手工同步。spec 还会动态生成 `_version_info_gen.txt`（Windows 文件属性 FileVersion/ProductVersion 与 APP_VERSION 对齐），旧的静态 `version_info_nw.txt` 不再使用。

3. **打包流程**：
   ```bash
   # 1. 更新 BUILD_DATE 为当前日期（APP_VERSION 仅在功能变更时 bump）
   # 2. 执行打包命令
   pyinstaller 南网协议解析工具.spec --noconfirm
   # 3. 在 dist/ 下验证带版本号+时间戳的 exe 文件生成
   ```

4. **版本号管理**：
   - `APP_VERSION`：功能版本号，仅在有功能变更时更新；是 exe 文件名、文件属性、窗口标题的唯一版本源
   - `BUILD_DATE`：编译日期，每次打包前必须更新
   - 两者共同构成完整版本标识，便于区分不同时间编译的版本

---

## 3. 架构总览

```
main_gui.py                     # GUI主程序 (PySide6)，应用入口，5000+ 行，MainWindow 类
│                                #  - APP_VERSION、CHANGELOG（手写）+ _get_git_changelog()（动态）
│                                #  - current_protocol 硬编码索引(0~10)，见 §6
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
│   │           └── dl_t698_45_data_decode.py # APDU 数据内容业务解码 (CLASS_ATTR_TEMPLATES/OI_UNIT_HINT/decode_oad_data)
│   ├── csg_new_gen_parser.py       # 新一代载波 (CSGNewGenParser) ~4970行
│   └── csg_new_gen_cmd_payloads.py # 应用层命令业务数据单元解析
├── gw_new_gen_parser.py        # 国网新一代双模 (GWNewGenParser) — 国网新一代双模通信互联互通
│   ├── gw_new_gen_mme_parser.py  # 国网新一代 MME 管理消息解析（关联/代理变更/发现列表/诊断等）
│   └── gw_new_gen_cmd_payloads.py # 国网新一代应用层命令载荷解析
├── hdc10_parser.py            # HDC 1.0 双模互联互通 (HDC10Parser) — Q/GDW 12087.42-2020
│   └── hdc10_mme_parser.py    # HDC 1.0 MME 网络管理消息解析（关联/发现列表/时隙分配等）
└── (解析级别：新一代 auto/fc_pb/fc_efc/fc_only/app/pb_only；国网新一代&HDC 1.0 auto/fc_pb/fc_only/mac_only/pb_only/fc_mac/app；通道：PLC 载波 / HRF 无线)
│
├── 查询/映射模块（lookup）── 单例 get_xxx_lookup() 提供全局实例
│   ├── obis_lookup.py              # OBIS码 (HDLC/DLMS)
│   ├── command_lookup.py           # PLC RF 命令字
│   ├── dlt645_di_lookup.py         # DLT645 DI
│   ├── gdw_afn_lookup.py           # 国网 AFN
│   ├── gdw_eb_di_lookup.py         # 本地通信模块扩展 EB 数据标识（附件1，1.14.0 起）
│   └── (698.45 OI 查询内嵌于 dl_t698_45_oi_lookup.py)
│
├── 对比引擎
│   └── frame_diff_engine.py        # 协议感知帧对比引擎 (FrameDiffEngine) — 字节级/字段级 diff
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
│   ├── diff_widget.py              # 报文对比标签页 (DiffWidget) - 双报文输入，字节/字段级对比
│   ├── message_tool_widget.py       # 报文工具标签页 (MessageToolWidget) - ASCII/HEX转换/CRC/校验
│   ├── enhanced_export.py           # 增强导出功能 (EnhancedBatchResultExporter) - Excel/CSV/TXT/JSON
│   ├── theme_settings.py            # 主题与字体设置 (ThemeManager + ThemeSettingsDialog) - 5套主题/QSS/字体持久化
│   ├── monitor_widget.py            # 实时监控器 (RealtimeMonitorWidget) - 串口原始字节流自动组帧/CSV记录
│   ├── monitor/tcp_monitor.py       # TCP流量监控 (TCPMonitorWidget) - scapy抓包/流重组/自动解析
│   ├── system_integration/          # 系统集成包（Windows）
│   │   ├── sys_tray.py              #   系统托盘（关闭最小化/显示隐藏/自启/退出）
│   │   ├── global_hotkey.py         #   全局热键（默认 Ctrl+Alt+X，解析剪贴板 hex）
│   │   ├── single_instance.py       #   单实例（QLocalServer，转发命令行参数）
│   │   ├── registry_menu.py         #   注册表：开机自启 + .log/.txt/.hex/.bin 右键菜单
│   │   ├── clipboard_monitor.py     #   剪贴板报文自动检测（严格 hex 校验 + 协议特征识别）
│   │   ├── parse_prompt_dialog.py   #   剪贴板报文解析提示框（置顶、协议选择、复用实例）
│   │   ├── npp_integration.py       #   Notepad++ 集成（右键菜单 + 运行命令，触发 --clipboard）
│   │   └── system_settings.py       #   系统集成设置面板与 config.json "system" 段
│   └── reflex_web/                 # Reflex Web 版（实验性，run_app.py + reflex_web_exe.spec）
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
│   ├── csg_new_gen_validator.py    # 新一代载波 (CSGNewGenValidator)
│   ├── gw_new_gen_validator.py     # 国网新一代双模 (GWNewGenValidator)
│   └── hdc10_validator.py          # HDC 1.0 双模 (HDC10Validator) - 定界符/版本/FCCS(CRC-24)
│
├── 监听/报表/模板/可视化编辑
│   ├── monitor_widget.py           # 实时监控器（南网新一代/国网新一代，96..16 / ED..EE 解帧）
│   ├── monitor/tcp_monitor.py      # TCP 流量监控器（scapy，流重组 + 应用层解析）
│   ├── monitor/frame_monitor.py    # 串口实时帧监听组件（旧版，FrameMonitorWidget）
│   ├── report/excel_reporter.py    # Excel 测试报告（需 openpyxl）
│   ├── templates/test_templates.py # 测试模板库
│   └── visual_editor/test_item_editor.py # 可视化测试项编辑器
│
├── 脚本引擎 / 用户文档
│   ├── lua_script_engine.py     # 测试方案 Lua 脚本引擎（依赖 lupa，1.8.1 新增）
│   └── docs/Lua脚本使用说明.md   # Lua 脚本用户使用文档
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
    (0:ProtocolFrameParser / 1:PLCRFProtocolParser / 2~5:HDLCParser / 6:DLT645Parser
     7:GDW10376Parser / 8:DLT69845Parser(+APDUParser+AXDRCoder)
     9:CSGNewGenParser(+CSGNewGenCmdPayloads) / 10:GWNewGenParser(+GWNewGenMMEParser+GWNewGenCmdPayloads)
     11:HDC10Parser(+HDC10MMEParser))
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
- GUI 代码集中在 `main_gui.py` 单文件，`MainWindow` 类约 4000+ 行；**新增 UI 组件必须拆分到独立文件**（参考 `frame_gen_widget.py`），由 `main_gui.py` 导入组合
- 所有 parser 返回**嵌套 dict**，禁止返回自定义类给 GUI 层

### 4.2 解析结果 dict 标准字段
所有 parser 返回的 dict 中关键中文键名（GUI 表格列直接读取）：
- `原始值` / `原始字节` — 十六进制原始数据
- `十进制` / `解析值` — 解析后的数值
- `说明` / `名称` / `业务说明` — 中文描述
- `偏移` / `长度` — 字节定位（用于高亮）

- **南网(0) / 国网(7) / 698.45(8) / 新一代(9) / 国网新一代(10) / HDC 1.0(11)**：长度域、DI、多字节字段 → **小端序 (little-endian)**
- **HDC 1.0(11) MAC 地址**：大端（与多字节字段小端不同）
- **HDLC/DLMS(2,3,4,5)**：网络字节序 **big-endian**
- **DLT645(6)**：BCD 编码，地址域低字节在前
- **PLC RF(1)**：大端
- ASCII / BCD 字段经常需要"反转后解析"，参考 CHANGELOG 1.6.4~1.6.7 的字节序修复历史

### 4.4 校验和 / CRC
- 南网(0)：控制域 + 用户数据区的 8 位位组算术和（不考虑溢出）
- 国网(7)：同南网（控制域 + 用户数据区算术和）
- DLT645(6)：所有字节累加和 `& 0xFF`
- HDLC(2)：CRC-16/FCS（CCITT，`base.py:_calc_crc16_ccitt`）
- 新一代(9) / 国网新一代(10)：MAC 帧 CRC-32
- HDC 1.0(11)：FC 的 FCCS 为 **CRC-24**，PB 尾 PBCS 为 **CRC-24**，MAC 帧尾 ICV 为 **CRC-32**（见 `hdc10_parser.py` 的 `_crc24` / `_crc32`）

### 4.5 自定义数据持久化
| 文件 | 内容 | 来源 |
|------|------|------|
| `custom_di.json` | 南网自定义 DI | GUI 运行时增删 |
| `gdw_custom_afn.json` | 国网自定义 AFN+Fn | GUI 运行时增删 |
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
- **参考文档**：
  - `集中器本地通信模块接口-2024.md`（Q/GDW 10376.2—2024，**严格依据此文档解析**）
  - `协议文档/7.国网本地接口协议/附件3：1376.2集中器本地通信模块接口协议【福建增补】V1.4-20240729`（**福建增补规约，AFN=50H~56H，1.14.0 起支持**）
  - `协议文档/7.国网本地接口协议/附件1：本地通信模块扩展协议 V3.42-20260514`（**EB 数据标识扩展，1.14.0 起支持**，V3.31 前置版本）
  - `协议文档/7.国网本地接口协议/附件4：集中器和CCO通信接口补充要求-20220416`（以太网/UDP 通信链路要求）

### 5.6 DL/T 698.45-2017（索引 7，**1.7.0 新增**）
- **解析器**：
  - `dl_t698_45_parser.py` (DLT69845Parser) — 链路层帧（68 L L C SA CA [HCS] [APDU] [FCS] 16）
  - `dl_t698_45_apdu_parser.py` (DLT69845APDUParser) — APDU 服务类型（GET/SET/ACTION/REPORT/PROXY/LINK/CONNECT...）
  - `dl_t698_45_axdr.py` (AXDRCoder) — **A-XDR 编解码**（依据 DL/T 790.6-2010）
  - `dl_t698_45_data_decode.py` — **APDU 数据内容业务解码**（按对象属性格式解码 A-XDR 数据：电能量 kWh 换算、需量值@时间、分相 A/B/C 相、单值换算；Scaler_Unit 10^scaler）
  - `dl_t698_45_oi_lookup.py` (OILookup) — OI 对象标识查询
- **组帧**：`dl_t698_45_frame_gen.py` + `dl_t698_45_frame_schema.py`
- **校验器**：`validator/dl_t698_45_validator.py`
- **依赖**：`crcmod`（`Crc('x-25')`）
- **参考文档**：`面向对象的用电信息数据交换协议(20210910).md`
  - **CRC 范围**：文档明确定义 HCS/FCS 各自覆盖的字段，**哪些字段参与 CRC 必须查文档**
  - **A-XDR 编码**：APDU 内部所有数据用 A-XDR，tag 高 3 位 = 010

### 5.7 新一代载波协议 / 通感一体化（索引 9，**1.7.0 新增**）
- **解析器**：
  - `csg_new_gen_parser.py` (CSGNewGenParser) — MAC 帧（MPDU/MAC头/MSDU/CRC-32）+ 应用层业务报文
  - `csg_new_gen_cmd_payloads.py` — 应用层命令业务数据单元解析（依据第5部分）
- **校验器**：`validator/csg_new_gen_validator.py`
- **GUI 特性**：协议索引 9 时显示解析级别下拉（auto / fc_pb / fc_efc / fc_only / app / pb_only），pb_only 模式可指定 SOF/信标/ACK/NET 帧类型；由 `_csg_parse_level` 控制
- **解析重点**：支持多物理块重组、聚合帧级联块应用层解析、NET 帧可变区域解析；批量解析支持监控日志前缀剥离与业务摘要
- **参考文档**（位于 `南网新一代20260226校对/南网新一代20260226校对/` 子目录，每部分同时有 .docx 和 .md）：
  - `1-通感一体化低压电力线宽带载波通信规约 第1部分 总则（文本校对）.md` — 总则
  - `2-...第2部分 技术要求（文本校对）_力合微_20260304.md` — 技术要求
  - `3-...第3部分 物理层通信协议（文本校对）.md` — 物理层
  - `4-...第4部分 数据链路层通信协议 （文本校对）.md` — **数据链路层（MAC/MSDU 帧格式）**
  - `5-...第5部分 应用层通信协议（文本校对）.md` — **应用层（业务报文结构）**
  - `6-...第6部分：检验规范（文本校对）.md` — 检验规范
  - 源 docx 可用 `convert_docx_to_md.py` 重新转换
### 5.8 国网新一代双模通信互联互通（索引 10）
- **解析器**：
  - `gw_new_gen_parser.py` (GWNewGenParser) — 国网新一代双模通信互联互通协议解析，支持 HDC 1.0 / HDC 2.0 版本判定
  - `gw_new_gen_mme_parser.py` (MMETYPE_NAMES + _MME_CONTENT_PARSERS) — MME 管理消息深度解析（关联/代理变更/发现列表/网络冲突/诊断等）
  - `gw_new_gen_cmd_payloads.py` — 应用层命令业务数据单元解析
- **校验器**：`validator/gw_new_gen_validator.py` (GWNewGenValidator)
- **GUI 特性**：协议索引 10 时显示解析级别下拉（auto / fc_pb / fc_only / mac_only / pb_only / fc_mac / app），pb_only 模式可指定帧类型；由 `_gwcsg_parse_level` 控制
- **解析重点**：MPDU = FC(16B) + PB；PB = PBH(1B) + MAC帧头 + MSDU + [ICV] + [填充] + [PBCS]，FC 末 3 字节为 FCCS，其后直接为 PB；MME 报文支持 FC 后直接管理消息与 0x0008 发现列表等特殊类型
- **参考文档**（位于 `国网新一代协议/` 目录）：
  - `双模通信互联互通技术规范 第1部分：总则.md` — 总则
  - `双模通信互联互通技术规范 第2部分：技术要求20251229.md` — 技术要求
  - `第4-1部分：物理层通信协议_智芯合稿_20260108.md` — 物理层
  - `双模通信互联互通技术规范 第4-2部分：数据链路层通信协议.md` — **数据链路层（MAC/MSDU 帧格式）**
  - `双模通信互联互通技术规范 第4-3部分：新一代应用层协议.md` — **应用层（业务报文结构）**
  - `双模通信互联互通技术规范 第3部分：检验方法-20251222.md` — 检验方法
  - 源文件（.doc/.docx）可用 markitdown 重新转换

### 5.9 HDC 1.0 双模互联互通（索引 11，**独立协议**）
> 与索引 10（国网新一代）的关系：国网新一代解析器内部按 FC 字节 12 高 4 位自动区分 HDC 1.0 / 2.0；**协议 11 是独立解析 HDC 1.0 帧的单独入口**（Q/GDW 12087.42-2020，旧版双模），帧结构与国网新一代共用同一套双模技术规范早期版本。
- **解析器**：
  - `hdc10_parser.py` (HDC10Parser) — 完整 MPDU（FC 16B + 物理块 PB×N）、FC 可变区域（信标/SOF/SACK/网间协调）、信标载荷与管理信息条目（含时隙分配 0xC0）、MAC 帧（标准 16B 头 / 单跳 4B 头）、MSDU 载荷与应用层业务报文
  - `hdc10_mme_parser.py` (parse_management_message) — HDC 1.0 网络管理消息（MME）深度解析，MMTYPE 2 字节小端
- **校验器**：`validator/hdc10_validator.py` (HDC10Validator) — 定界符类型 / 标准版本号(=0) / FCCS(CRC-24) 校验
- **GUI 特性**：协议索引 11 时显示解析级别下拉（auto / fc_pb / fc_only / mac_only / pb_only / fc_mac / app）与通道下拉（PLC 载波 / HRF 无线），复用国网新一代控件（`gw_parse_level_combo` / `gw_channel_combo`），由 `_hdc10_parse_level` / `_hdc10_channel` 控制；查询页新增 `_create_hdc10_lookup_content`（报文 ID / 端口号 / 定界符 / MSDU 类型等映射）
- **解析重点**：`MPDU = FC(16B) + PB×N`；`PB = PBH(1B) + PB 体 + PBCS(3B, CRC-24)`；`MAC帧 = MAC 头 + MSDU + ICV(4B, CRC-32)`；信标帧 FC 后直接为信标载荷（无 PBH）；多字节小端、MAC 地址大端；批量解析复用 `_strip_gw_new_gen_prefix` 前缀剥离与 `_get_gw_new_gen_summary` 摘要
- **参考文档**（位于 `国网新一代协议/HDC-国网双模协议/` 目录，Q/GDW 12087 早期版本）：
  - `双模通信互联互通技术规范 第1部分：总则.md` — 总则
  - `双模通信互联互通技术规范 第4-1部分：物理层通信协议.md` — 物理层
  - `双模通信互联互通技术规范 第4-2部分：数据链路层通信协议.md` — **数据链路层（MAC/MSDU 帧格式，表22/表38/表42/表50）**
  - `双模通信互联互通技术规范 第4-3部分：应用层通信协议.md` — **应用层（业务报文结构）**
  - 注：HDC 1.0 相关表格/字段定义（如时隙分配条目 0xC0 长度字段 2 字节、发现信标省略非中央信标信息）以实测报文 + 上述文档为准

---


## 6. GUI 协议集成点（添加/修改协议必读）

`current_protocol` 索引在 `main_gui.py` **硬编码**，添加新协议必须**同时**修改以下位置（用 grep 定位）：

| 位置 | 行为 |
|------|------|
| `MainWindow.__init__`（~L285） | 注释列出索引含义，并初始化对应 parser 实例 |
| `protocol_combo.addItem`（~L549-560） | 添加下拉项（顺序即索引，现 0~11） |
| `_on_protocol_changed`（~L1300+） | 协议切换：输入提示 / 查询页 / 各 Tab 可见性 |
| `_extract_frames_for_protocol`（~L5449+） | 多帧提取逻辑（不同协议起始符不同；协议 11 走通用每行一帧） |
| `_get_current_parser` / `_parse_single_frame`（~L3100+） | 选择 parser 调用（协议 11 → HDC10GuiParser 包装） |
| `_update_protocol_lookup_tab`（~L2113+） | 查询标签页内容（DI/AFN/OBIS/命令字/业务标识/HDC 1.0 报文 ID） |
| `_run_validation`（~L3698） | 校验器注册（`validators` dict，11 → HDC10Validator） |
| `_protocol_name_to_index`（~L4600） | 协议名 ↔ 索引映射（含 "HDC1.0"→11 等） |
| 批量解析（~L4780+） | 前缀剥离（10/11 → `_strip_gw_new_gen_prefix`）、摘要（10/11 → `_get_gw_new_gen_summary`） |
**Tab 可见性规则：**
- 组帧 / 预设命令：南网(0) / 国网(7) / 698.45(8)，三种模式 `south` / `gdw` / `dlt698`
- 档案管理 / 拓扑信息：仅南网(0) / 国网(7)
- 新一代解析级别下拉：仅索引 9（新一代载波，auto/fc_pb/fc_efc/fc_only/app/pb_only）
- 国网新一代 / HDC 1.0 解析级别 + 通道下拉：索引 10 / 11（auto/fc_pb/fc_only/mac_only/pb_only/fc_mac/app），由 `_hdc10_parse_level` / `_hdc10_channel` 控制
- 实时监控器：仅索引 9 / 10 可见，南网新一代用 `ED..EE` 包装，国网新一代用 `96..16` 包装（**索引 11 无监控器**）
- TCP 监控：始终可见，独立于协议切换；scapy 未安装或 npcap 缺失时功能降级并提示
- 报文对比 / 报文工具 / 测试方案：始终可见

---

## 7. 测试

> **规则（强制）**：所有测试文件一律放入 `test/` 目录，**项目根目录禁止新增 `test_*.py` 测试文件**（`.gitignore` 已忽略根目录 `/test_*.py`）。新增测试在 `test/` 下建 `test_xxx.py`，文件头必须包含 `import _path_setup  # noqa: E402`（位于 docstring 之后、业务 import 之前），它会自动把项目根加入 `sys.path` 并把工作目录切到项目根，使 `from xxx_parser import ...` 与 JSON 数据文件读取在任意启动目录下都成立。

**没有正式测试框架**（无 pytest / unittest 配置）。`test/*.py` 是独立脚本，直接运行（命令在项目根执行）：

```bash
# 长期维护的核心测试
python test/test_dlms.py            # DLMS 基础
python test/test_hdlc.py            # HDLC 帧
python test/test_plc_rf.py          # PLC RF
python test/test_ber_tlv.py         # BER-TLV 编码
python test/test_actual_hdlc.py     # 真实 HDLC 报文
python test/test_special_frame.py   # 特殊帧
python test/test_snrm_frame.py      # SNRM 帧
python test/test_dl_t698_45.py      # 698.45 协议
python test/test_dl_t698_45_data_decode.py  # 698.45 APDU 数据内容业务解码（电能量/需量/分相/单值）
python test/test_dl_t698_45_fujian.py  # 698.45 福建简化698（choice=0x02 List 结构，1.14.2 起）
python test/test_oad_enrichment.py  # 698.45 OAD 增强
python test/test_csg_new_gen.py     # 新一代载波协议
python test/test_csg_hrf_mac.py     # 新一代载波无线单跳MAC帧（表12/表139）
python test/test_csg_batch_prefix.py # 新一代载波监控日志前缀剥离
python test/test_csg_batch_parse_level.py # 新一代载波解析级别/完整 MPDU
python test/test_csg_summary.py     # 新一代载波批量摘要
python test/test_gw_new_gen.py      # 国网新一代双模协议
python test/test_gdw_fujian.py      # 国网福建增补规约 + EB 数据标识（1.14.0 起）
python test/test_hdc10.py           # HDC 1.0 双模互联互通协议（时隙分配条目/信标 BPCS/PBCS）
python test/test_gw_batch_parse.py  # 国网新一代批量解析
python test/test_gw_ext_cmd.py      # 国网新一代扩展命令载荷
python test/test_gw_parse_levels.py # 国网新一代解析级别
python test/test_gw_monitor_summary.py # 国网新一代监控摘要
python test/test_sack_fix.py        # SACK 帧解析
python test/test_ed_fallback_fix.py  # ED..EE 监控帧非法回退修复（1.11.1 起）
python test/test_dl_t698_45_fujian.py # 698.45 福建简化698（choice=0x02 List）解析
python test/test_diff_engine.py    # 报文对比引擎
python test/test_plan_widget.py     # 测试计划组件（需 GUI 环境）
python test/test_monitor_widget.py  # 实时监控器组件（需 GUI 环境）
python test/test_monitor_deframe.py # 国网新一代 96..16 解帧
python test/test_monitor_plc2_deframe.py # 南网新一代 ED..EE 解帧
python test/test_monitor_strip.py   # 监控报文头尾剔除
python test/test_theme_settings.py  # 主题与字体设置
python test/test_web_frame_gen_utils.py # Reflex Web 版组帧纯逻辑

# 调试用临时脚本（可清理）：test_mac_*.py / test_msdu_debug.py / test_user_frame.py / test_full_debug.py / test_len_debug.py
```

每个脚本内含**硬编码测试帧 + 预期输出**，用 `assert` 或 `print` 对比。新增解析逻辑时，应同步在 `test/` 下对应 `test_xxx.py` 增加用例。

---

## 8. 常见陷阱（**修改前必读**）

1. **`_clear_layout` 递归销毁**（`main_gui.py`）：递归删除所有子 widget。改查询标签页逻辑时必须理解此方法，否则 widget 残留或崩溃。
2. **`current_protocol` 硬编码索引**：见 §6，添加协议要改 8+ 处。
3. **PyInstaller spec 数据资源**：当前主程序使用 `南网协议解析工具.spec`，打包 `custom_di.json`、`dlt645_di.json`、`gdw_custom_afn.json`、`icons/` 与 `enhanced_export.py` 等资源；**新增需打包的数据文件时必须检查该 spec**，Reflex Web 版另行检查 `reflex_web/reflex_web_exe.spec`
4. **DLMS 深度解析是双击触发**，不是自动：双击表格中 `DLMS APDU` 行才弹 `dlms_deep_parser`。
5. **HDLC 字节填充**：组帧时 7E/7D 必须转义（见 §4.6）。
6. **698.45 CRC 范围**：HCS / FCS 覆盖字段不同，必须查文档，不能照抄南网/国网。
7. **698.45 APDU 解析器延迟导入**：`dl_t698_45_parser.py` 用 `@property apdu_parser` 延迟初始化，避免循环依赖。
8. **新一代载波解析级别**：`auto` 模式会自动判断是完整 MPDU 还是仅 FC 还是应用层；调试特定层时切到 `fc_only` / `app`。
9. **字节序修复历史**：1.6.4~1.6.7 系统性修复了多字节字段小端序、ASCII/BCD 反转问题。改多字节字段解析时参考此段历史，避免回退。
10. **`dlt645_di.json` 勿手改**：由 `generate_dlt645_di.py` 生成；`OI_NAME_MAP` 由 `generate_oi_lookup.py` 生成。
11. **新一代载波协议(8)批量解析的监控前缀剥离时机**：`_strip_csg_monitor_prefix` **必须在 `_clean_hex_input` 之前调用**（在 `parse_batch` 内）。因为监控标记 `-> 接收机 Has Get` 含中文/箭头，若先清洗 hex 会破坏标记导致无法定位 15 字节监控头边界。改批量解析流程时注意此顺序。
12. **Lua 脚本引擎依赖 `lupa`**：未安装时 `LUA_AVAILABLE=False`，测试方案中 Lua 脚本类型不可用但其余功能正常。`lua_script_engine.py` 通过 `raw_data_received` 信号直接接收串口原始字节（绕过 FT1.2 帧解析），改串口数据流时注意此旁路。
13. **Inno Setup 版本号滞后**：`南网解析工具.iss` / `2222.iss` 中 `MyAppVersion` 为 `1.7.2`，落后于 `APP_VERSION`，发版时需手动同步。
14. **国网新一代 HDC 1.0 / 2.0**：`gw_new_gen_parser.py` 依据 FC 字节 12 的高 4 位标准版本号自动选择 MAC 帧头规则；改 MAC 头解析时不要把 HDC 1.0 的保留字段当成 HDC 2.0 字段。
15. **国网新一代信标帧无 PBH（重要）**：`_parse_beacon_frame` 中信标帧（DT=0）FC 后**直接为信标载荷，无物理块头(PBH)**，HDC 1.0 与 HDC 2.0 均如此。依据：表22/表38 字段从字节0即信标类型，无 PBH 位置；BPCS(CRC-32) 校验范围为信标载荷内容，无 PBCS(CRC-24)。文档第906行"以物理块头和物理块体为目标"是 **SOF 帧(图18)** 的 PBCS 描述，不是信标帧。若误把信标载荷首字节当 PBH，会导致信标类型错位 1 字节（如发现信标 0xC8 被误判成中央信标 0x42）。
16. **国网新一代 MME**：管理消息由 `gw_new_gen_mme_parser.py` 负责，MMTYPE 为 2 字节小端；0x0008 按发现列表报文处理（文档中该值标为保留，但报文顺序支持该解释），改解析时先查表 42~93 与实测报文。
17. **监控器包装格式**：`monitor_widget.py` 区分 `96..16`（国网新一代/HPLC）与 `ED..EE`（南网新一代/PLC2）；协议 9 / 10 切换时 wrapper 会自动切换，不要用错格式。
18. **TCP 监控可选依赖**：`monitor/tcp_monitor.py` 使用 scapy QThread + signal 回主线程，Windows 需 npcap；scapy 缺失时不能调用 `get_if_list`，UI 已做降级，但新增抓包逻辑要保持 try/except。
19. **输入即 PB 契约**：`mac_only` / `pb_only` / `app` 等仅输入解析模式不再剥离 FC，输入内容按界面提示的层级直接解析；不要再次假设输入包含完整 MPDU 而剥离 16 字节。
20. **系统集成仅限 Windows**：`system_integration/registry_menu.py` 与 `global_hotkey.py` 依赖 Windows API 与 HKCU 注册表；热键注册失败时应打印提示而不是阻塞启动。`main()` 先做单实例判断，修改启动流程时不要破坏该顺序。
21. **剪贴板检测与 Notepad++ 集成**：`clipboard_monitor.py` 监听 `QClipboard.dataChanged`，受 `config.json` 的 `system.clipboard_monitor` 控制；`npp_integration.py` 会修改 `%APPDATA%/Notepad++` 下的 XML 并保留 `.parser_backup`。改动时保持严格 hex 校验、去抖与提示框单实例复用，避免自身复制触发弹窗。
22. **ED..EE 监控帧剥离失败禁止回退**：协议 9 下勾选「ED监控协议」（或弹窗「剥离ED监控头」）时，首字节 0xED 的报文只能是 ED 包装帧（CSG FC 起始字节低 4 位 ∈ {8,9,A,B}，0xED 永不是合法 FC 起始）。`_parse_ed_monitor_header` / `_extract_business_from_ed_frame` 校验失败（帧不完整、缺 EF/EE）时必须明确报错，**绝不能静默把 ED 首字节当 FC 起始符送解析器**。三处路径（`parse_single` / `_parse_and_show_dialog._preprocess` / 批量解析）必须保持一致。
23. **字段声明与实际不一致时的容错显示原则**：当报文长度、字段声明值与实际内容不匹配时（如 DLT645 数据长度字段声明 102 字节但实际只有 15 字节），**解析器不得直接返回空白结果**（会让用户以为按钮失灵）。正确做法：尽力解析所有可解析字段，`valid` 置 `False`，并在解析结果表格中以醒目的 `⚠` 行插入错误提示。校验器对应项必须标记 FAIL。核心原则——用户点了解析按钮就必须看到内容和错误，不能什么都没有。
24. **新一代载波协议(索引9)无线信道单跳MAC帧头仅 4 字节**：版本2（单跳帧协议，表12，仅无线信道）MAC 帧头为 4 字节（帧头类型1b+版本2b+保留5b / MSDU类型8b 表13 / MSDU长度16b），**帧头类型位无意义**，不得按 header_type 推导 12/32 字节帧头长；MSDU 类型在 MAC 头内、载荷无 VLAN+类型前缀，须内联分派（1=应用层 / 2=无线发现列表 表139 TLV / 128=IPV4）。改 `_parse_mac_frame` / `parse_to_table` 步骤3 / `_parse_pb_block` 尾段三处时保持一致（v2 → `mac_hdr_len=4` 且 `msdu_payload=b""` 防重复解析）。版本1 帧头「发送序号」为小端（`(byte1<<4)|byte0高4位`）。
25. **HDC 1.0(索引11)信标条目长度字段**：信标管理信息条目（如时隙分配 0xC0）长度字段为 **2 字节**，条目内容 = `total_len - 3`（头 1B + 长度 2B 开销），不要用 `total_len - 2` 多算 1 字节（详见 `test_hdc10.py::test_entry4_content_length`）。
26. **HDC 1.0(索引11)发现信标省略非中央信标信息**：发现信标（类型 0）省略非中央信标信息字段，可变部分只有 CSMA 时隙信息（4B/条，按相线 A/B/C 展开）；不要按中央信标格式去解析 TEI 条目（`test_hdc10.py`）。
27. **HDC 1.0(索引11)与国网新一代(索引10)并存**：协议 11 是独立解析 HDC 1.0 帧的入口（`hdc10_parser.py`），与协议 10 内部自动判定 HDC 1.0/2.0 的两条路径**不要混用解析器**；协议 11 无实时监控器、无组帧/预设命令、无档案/拓扑（仅单帧/批量/校验/查询/对比）。批量解析时协议 10/11 共用 `_strip_gw_new_gen_prefix` 与 `_get_gw_new_gen_summary`。

---

## 9. 开发原则

1. **协议定义优先**：遇到不确定的协议字段、字节序、校验范围，**先查 §5 对应文档**，不要凭记忆或猜测。
2. **PDF 文档用 pdf skill 检索**：645 补遗、IEC 62056-46、DLT645 原始标准都是 PDF，调用 pdf skill 而非人工翻阅。
3. **新增协议的完整 checklist**：
   - [ ] 新建 `xxx_parser.py`，返回嵌套 dict（键名遵循 §4.2）
   - [ ] 在 `main_gui.py` import + 初始化 parser 实例
   - [ ] 添加 `protocol_combo.addItem`（注意索引顺序）
   - [ ] 在 `_on_protocol_changed` / `_parse_single_frame` / `_extract_frames_for_protocol` / `_update_protocol_lookup_tab` 加分支
   - [ ] 新建 `validator/xxx_validator.py` 继承 `BaseValidator`，在 `_run_validation` 注册（`main_gui.py` 的 `validators` dict）
   - [ ] 如需 Web 版支持，同步更新 `reflex_web/reflex_web/reflex_web.py` 与 `reflex_web/reflex_web/lookup_utils.py`
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

### 1.14.5 — 2026-08-21
- **协议11（HDC 1.0）查询站点升级状态上行报文解析**（`hdc10_parser.py::_parse_upgrade` 0x034）：此前只按下行表40 解析（连续查询块数/起始块号/升级ID），上行应答的 升级状态(字节1高4位)/有效块数/升级位图 全部丢失。现按文档第4-3部分 表45 补全：升级状态（0空闲/1接收进行/2接收完成/3升级进行/4试运行）、有效块数、起始块号、升级ID + 接收位图（每bit对应一个文件块，1=已接收，显示 `N/M块已接收`）。**升级位图逐块编号明细**：按 起始块号+i 编号，每行32块多行展开，`[✓n]`=已接收 `[✕n]`=丢包，行说明统计丢包数。方向判定：len>12 或字节1高4位∈{1..4} 判为上行；恰12字节且状态位0 按表40 下行。`test/test_hdc10.py` 增至 10 项（上行全收/下行/丢包编号）全过
- **协议11（HDC 1.0）台区户变关系识别(0x0A1)深度解析**（`hdc10_parser.py`）：①修复报文头长度公式——6bit值(byte0[6:7]高2位+byte1[0:3]低4位)×4字节（类IPv4 IHL），此前错把「(b0低2位|b1高4位<<2)×4」致12字节头算成48字节、DATA 从错误偏移切片只剩尾部16字节；校时/事件/通信测试/注册/升级等全部 **7 处**统一修正。②DATA 域按采集类型深度解析：采集启动(表56)、特征信息告知(表57 TEI/采集方式/序列号/告知总数/起始NTB+特征序列)、判别结果信息(表61 TEI/结束标志/识别结果/正确隶属CCO地址)。③特征序列按特征类型分派：工频电压(表58 BCD XXX.X 大端)、工频频率(表59 BCD XX.XX 大端)、工频周期(表60 有符号偏差值+μs换算)，三相出线逐相展开，双沿采集解析 NTB2+第二组序列。`test/test_hdc10.py` 增至 16 项全过
- **协议11（HDC 1.0）信标时隙分配条目/心跳检测/发现列表深度解析**（`hdc10_parser.py` + `hdc10_mme_parser.py`）：①时隙分配条目(0xC0/F0)可变区按**实机顺序**解析——CSMA时隙信息先行 → 非中央信标信息(逐2B到数据边界，实测发现信标也携带、不做表50省略假设) → 绑定CSMA；实机声明 total_len 偏小（只含固定头+CSMA），内容延伸到管理区末尾(BPCS前)，真实帧 17 条时隙(2代理+15发现)+3条CSMA 全解零剩余。②心跳检测(0x0007)按表94：原始源TEI/最大站点TEI(各12b跨字节)+数量+位图大小+位图逐TEI明细。③发现列表(0x0008)按表95：固定头32B逐字段 + 三段变长区锚点切分——上行路由条目(锚点:路由条目总数, TEI12b+路由类型表98)、发现站点列表位图(锚点:位图大小, TEI明细)、接收发现列表信息与位图置位TEI**一一配对**显示 `[TEIn←计数]`。`test/test_hdc10.py` 增至 19 项全过

### 1.14.4 — 2026-08-21
- **内嵌部署增量构建**（`reflex_web/build_embedded_deploy.py`）：新增 `--skip-deps` 模式——复用已有 `python/`（解释器+site-packages），仅刷新源码/数据/前端层，重复构建从 10+ 分钟降至约 1 分钟；`requirements.lock` 已最新时跳过 uv 重新编译（构建原则已写入 §2）
- **协议8（DL/T 698.45）组帧 OI 增强**（`frame_gen_widget.py`）：预定义/A-XDR 两模式 OI 均改为「预设下拉 + 手动 hex 输入」双通道；A-XDR 模式新增「描述符类型」下拉可选 属性(OAD)/方法(OMD)（默认 ACTION→OMD 其余→OAD），属性标识/索引 与 方法标识/操作模式 随选择切换
- **修复协议8 A-XDR 复合类型编码语义**：array/structure tag 后字节应为**元素个数**而非子项字节总长（文档附录 H.3.2）。此前组帧 3 项 structure 误填 09（字节长），现正确填 03；修复 `frame_gen_widget.py` / `reflex_web/frame_gen_utils.py` 编码器与 `dl_t698_45_axdr.py` 解码器（按个数循环，此前按字节长截断致自组帧回读只显示 1 项）
- **修复协议8 SET/ACTION 组帧缺尾部 TimeLabel 字节**：此前仅 GET-Request 尾补 `00`，SET/ACTION 少 1 字节（文档 H.4/H.5 均以 OPTIONAL TimeLabel 结尾，00=无）；修复 `frame_gen_widget.py` 两条生成路径与 `frame_gen_utils.py::build_dlt698_axdr_apdu`
- **解析表格 array/structure 成员逐项展开**（`dl_t698_45_parser.py`）：复合类型不再只显示「[N项]」，为每个成员生成子行（原始编码/值/类型说明，如 `成员1 | 1101 | 1 | A-XDR:unsigned(0x11)`），嵌套递归展开，对齐官方工具；新增 `_add_axdr_item_rows`
- **请求 APDU 尾部 TimeTag 解析**（`dl_t698_45_apdu_parser.py`）：GET/SET/ACTION 的 Normal/NormalList 六个分支统一解析 OPTIONAL TimeTag 尾字节（00=无时间标签），表格显示「时间标签 | 0x00 | 无时间标签」；新增公共 `_parse_time_tag` 辅助
- **修复协议8 预设命令保存/显示**（`preset_buttons.py`）：新增 `DLT698_command.json` 独立预设文件（此前 `_get_path` 只认 south，dlt698 预设被误存入 `GW_command.json`）；`PresetButtonWidget.set_protocol` 支持 dlt698（此前守卫只认 south/gdw，切协议8 时静默忽略致预设页看不到 698 按钮）；加载时按 `protocol` 过滤历史混入条目（国网页不再显示 GW 文件中误存的 dlt698 条目），无 protocol 键的老数据按文件归属正常显示；`AddPresetDialog` 协议行显示「698.45 协议」；新增 `test/test_dlt698_preset.py`（31 项）
- 回归 `test_web_frame_gen_utils.py`（63项）/ `test_dl_t698_45.py` / `test_dl_t698_45_data_decode.py` / `test_dl_t698_45_fujian.py` / `test_oad_enrichment.py` 全过

### 1.14.3 — 2026-08-19
- **协议8 EB030307 过零NTB值上行数据解析**（`dl_t698_45_apdu_parser.py`）：ACTION-Response NormalList 每项结构 = OMD + DAR + **数据个数** + [Data]——DAR 后 `01`=数据个数、`09 81 81`=octet-string 129B，此前把 `01` 当 A-XDR array tag 解导致 `0x81 未知类型` 报错；新增 `_parse_axdr_items_or_single` 双路径（数据个数 N×A-XDR 失败回退单 A-XDR，兼容文档示例无前缀格式）
- **EB030307 字段 schema**（`gdw_eb_di_fields.py`）：数据开始时间(bcd_time 6B)/边沿类型(enum 0保留/1下降沿/2上升沿)/数据周期_分钟(uint8)/数据点数M(uint8)/NTB值数组(list，每项 相线1+相线2+相线3 NTB值 uint32 40ns)
- **bcd_time 可读化**：YYMMDDhhmmss（BCD）→ `2026-08-14 14:42:00`；EB030307 请求参数（1C 开头 date_time_s）优先时间解码、响应数据走字段 schema；数据不足固定头时回退 A-XDR 头+原始数据
- `test_dl_t698_45_fujian.py` 增至 12 项（新增用户真实上行帧 + 表格相线 NTB 展示）；全量回归 62+19+12 项通过

### 1.14.2 — 2026-08-19
- **协议8（DL/T 698.45）福建简化698 解析（choice=0x02 List 结构）**：`dl_t698_45_apdu_parser.py` 新增 SET/ACTION 的 Request/Response NormalList 分支（PIID + count + SEQUENCE OF {OAD/OMD, Data/DAR}），支持福建「本地通信模块扩展协议」V3.42 698 承载格式（A.2 要求 V3.3 起支持）——EB030110 台区识别、EB030307 过零NTB 等此前只能解析出「子类型码:0x02」
- **REPORT 带 count 结构**：REPORT-Notification/Response 按 `PIID-ACD + count + OAD列表 + 数据个数 + A-XDR 数据` 解析（对齐福建示例 `88 01 00 01 ...` / `08 01 00 01 ...`），OAD 逐项中文名 + 数据业务解码
- **EB 数据标识名称与字段解码**：OAD/OMD 的 OI 高字节 0xEB 时按 4 字节原样查 `gdw_eb_di_lookup` 名称（如 EB030110→台区识别_任务启动）；数据内容按 `gdw_eb_di_fields` 字段 schema 解码（enum→名称、uint→值、bcd/bs8/list），无 schema 保留原始 hex
- **修复 EB 数据内容 uint 字节序**：按文档「645 减33逆序」规则为**大端**（识别时长 `00 05`=5 分钟，此前小端误读 1280）；`gdw_eb_di_fields.py` 编码器同步修正
- 新增 `test/test_dl_t698_45_fujian.py`（9 项）；回归 `test_dl_t698_45.py` / `test_dl_t698_45_data_decode.py` / `test_gdw_fujian.py`（19项）/ `test_web_frame_gen_utils.py`（62项）全过；Web 浏览器实测用户帧 + 文档示例

### 1.14.1 — 2026-08-17
- **协议8（DL/T 698.45）APDU 数据内容业务解码**（`dl_t698_45_data_decode.py` 新增）：按对象属性格式解码 A-XDR 数据为业务值，覆盖常用数据项——电能量数组（kWh 换算+费率展开）、最大需量数组（值@发生时间）、分相电压/电流/功率/谐波（A/B/C 相+单位）、单值数据变量；Scaler_Unit 换算按 10^scaler，单位码映射表；无属性3 时按 OI 推断单位与默认缩放
- **APDU 解析器接入**（`dl_t698_45_apdu_parser.py`）：GET-Response Normal/NormalList/Next、SET-Request、REPORT-Notification Normal 新增「数据业务」键；REPORT-Notification Normal 补齐 OAD 解析（此前漏解）
- **GUI 表格**（`dl_t698_45_parser.py`）：「数据业务」按项展开（总/费率N/A相/B相/C相）
- **修复 DLT69845Validator 长度域公式**：L=帧长-2（文档附录 H.1 例证），此前 +4 误判合法帧
- 新增 `test/test_dl_t698_45_data_decode.py`（10 项）；回归 `test_dl_t698_45.py` / `test_gdw_fujian.py`（19项）/ `test_web_frame_gen_utils.py`（62项）全过

### 1.14.0 — 2026-08-17
- **国网协议（索引 7）新增「福建增补规约」解析与组帧**（`gdw10376_parser.py` / `gdw_send_frame_lib.py` / `gdw_frame_generator_schema.py` / `validator/gdw_validator.py`）：基于 `协议文档/7.国网本地接口协议/附件3：1376.2集中器本地通信模块接口协议【福建增补】V1.4-20240729`
  - **AFN=50H~56H 全功能**：50H 确认/否认、51H 初始化、52H 数据转发（F1 透明转发 / F2 任务队列_智能补采 / F3 任务队列_本地定时 / F11 并发抄表_福建 / F12 清空队列）、53H 查询数据（F1 参数配置 / F2 主节点地址 / F4 厂商版本 / F5 信道信息 / F6 串口参数 / F10 模式切换）、55H 控制命令（F1 设置地址 / F2 允许禁止上报 / F3/F4 广播 / F6 注册 / F7 结束任务 / F8 预告执行 / F9 预告抄读 / F10 模式切换 / F11~F13 速率协商 / F18 2字节模式）、56H 主动上报（F1 注册信息 / F2 事件内容 / F3/F13 抄读请求 / F4/F14 响应报文 / F5 信道延时 / F6 广播完成 / F15 带任务信息上报）
  - **帧结构识别**：福建增补信息域 R = 保留(5B)+序列号(1B)（上行加事件标志位）、地址域 A = A1+A3(12B 无中继 A2)，与 2024 国网（有中继地址）自动区分——按 `FUJIAN_AFNS` 探测 offset 22 处 AFN
- **新增「本地通信模块扩展协议」EB 数据标识深度解析**（`gdw_eb_di_lookup.py`）：附件1 V3.31 的 40+ 数据项映射（事件/台区识别/设备基础/时钟/档案/任务队列等），645 帧内嵌 EB030002 停上电事件、EB030110 台区识别、EB030501 时钟、EB030503 校时、EB040302 停上电记录、EBEEEEEE 多数据项抄读等深度解析，透明转发(52H-F1)/事件上报(56H-F2)自动识别
- **福建增补组帧**：schema 新增 27 个 (AFN,Fn) 定义（list 字段自动数量 + length_field 报文长度自动计算），`generate_frame` 对增补 AFN 自动切换 R/A 结构
- **校验器**：GDWValidator AFN 值域检查按福建增补帧结构定位真实 AFN
- **GUI**：查询页自动含福建增补 AFN/Fn + 新增 EB 数据标识查询区块；组帧页自动可选福建增补命令
- **修复** `gdw_send_frame_lib.py::_pack_fields` 的 length_field 语义 bug（此前取长度字段自身值，导致含报文内容命令的长度计算错误）
- 新增 `test/test_gdw_fujian.py`（15 项测试全过）
- **本地通信模块扩展协议升级 V3.42-20260514**：新增 EB030313/314 周边节点信号通信质量（本台区/非本台区，含载波/无线成功率、SNR、RSSI）、EB030320/321 通信测距（启动指令/结果情况表，载波/无线测距值单位 1ns）、EB030506 NTB校时_698方式专用（`1C`+YYYYMMDDhhmmss(BCD 7B)+NTB(4B)）、EB030520 自动NTB校时模式扩展为 0~3（停用/645格式/698格式）；EBEEEEEE 标记取消（V3.40 起采用 698 读取方式）。`gdw_eb_di_lookup.py` 增至 57 项，`test/test_gdw_fujian.py` 增至 16 项测试；Web 查询页 EB 查询自动含新增项
- **Reflex Web 版同步**：协议7 解析/组帧/校验复用 GUI 模块（`GDW10376Parser` / `GDWFrameGenerator` / `GDWValidator`），自动获得福建增补支持（AFN+Fn 下拉含 52H/55H 等增补命令、list/length_field 字段正常渲染组帧）；查询页新增 EB 数据标识查询（协议7 下输入 `EB` 前缀或「台区/时钟/档案」等关键词返回附件1 数据标识表）；组帧页新增「EB 数据标识 帧生成器」（645 帧 + 698.45 **完整链路层帧**双格式：698 支持 8 种服务含 GET 读取、SA/CA/DIR/PRM/功能码头部可配置、HCS/FCS 自动计算；对象个数一个/若干、PIID/OI/属性编号/属性特征/元素索引/方法标识/操作模式可配置；新增 `gdw_eb_di_fields.py` 为 42 个 EB 数据项定义数据内容字段 schema，选 OAD 后按字段表单配置自动编码）；`test_web_frame_gen_utils.py` 增至 62 项全过
- **修复 main_gui.py 启动崩溃**：`test_plan_widget.py` 是 GUI 组件（`main_gui.py` 导入的 TestPlanWidget），此前被 `bdf4d22`（测试文件迁移）误移入 `test/` 目录，根目录 `/test_*.py` 忽略规则使其丢失，启动报 `ModuleNotFoundError: test_plan_widget`。已恢复至根目录，`.gitignore` 增加 `!/test_plan_widget.py` 例外；`test/test_plan_widget.py` 作为独立测试副本保留（AGENTS.md §7 测试列表不变）

### 1.13.0 — 2026-08-14
- **新增「HDC 1.0 双模互联互通」协议（索引 11，独立协议）**：主程序第 12 种协议（Q/GDW 12087.42-2020 旧版双模）。新增 `hdc10_parser.py`（HDC10Parser：FC/可变区域/信标载荷/时隙分配条目/MAC 帧/应用层）、`hdc10_mme_parser.py`（MME 管理消息）、`validator/hdc10_validator.py`（HDC10Validator）、`test_hdc10.py`。GUI 集成：协议下拉框、解析级别 + 通道下拉（复用国网新一代控件）、查询页（`_create_hdc10_lookup_content`）、校验注册（`_run_validation` 11 → HDC10Validator）、批量前缀剥离 + 摘要（复用 `_strip_gw_new_gen_prefix` / `_get_gw_new_gen_summary`）。仅 PySide6 主程序支持（Reflex Web 版 0-10，NiceGUI/TUI 已移除）
- **协议选择持久化**（`main_gui.py`）：上次使用的协议索引存入 `config.json` 的 `parse.protocol`，启动时 `_restore_saved_protocol` 自动恢复选中（UI 全部就绪后执行，走正常切换逻辑），用户无需每次打开软件重新选择协议
- **所有解析/查询/监控表格支持 Ctrl+滚轮缩放（类 Excel）**：新增 `gui_utils.py::ZoomableTableWidget(QTableWidget)`——Ctrl+滚轮按 1.1/0.9 倍整体缩放（字号+行高同步，5-24pt 钳制，列宽保持避免破坏固定列布局），Ctrl+0 恢复缩放前基准；缩放为 per-table 覆盖，改全局字体设置后回到基准字号。全仓 35 处 `QTableWidget(` 实例（11 文件：main_gui 17、monitor 系列 8、diff/查询/档案/测试方案等 10）替换为该基类，原右键复制/Ctrl+C/字节高亮/双击深度解析等行为不变（子类即父类）；单元格级 `setCellWidget`/固定字体 item 不随缩放（可接受）
- **校验结果 展开/收缩 + 解析结果表 全屏**（`main_gui.py`）：校验结果区新增「展开/收缩」按钮对（内容 `verify_label` 移入 QScrollArea，收缩后仅保留组标题+按钮行，默认收缩，重新展开恢复全文）；单帧解析结果表、批量摘要表、批量详情表各新增单个「全屏」按钮——与报文对比「结果详情」交互一致：点击在新窗口弹窗克隆展示表格快照（`_open_table_popup`），点「关闭」或窗口 X 关闭即恢复，主界面不做隐藏/重排。通用辅助 `_make_table_fullscreen_btn` 与 `_open_table_popup`
- **新一代载波协议(索引9)批量解析管理消息摘要崩溃修复**（`main_gui.py`）：`_get_csg_new_gen_summary` 中 `int(mmtype_val)` 未处理 `0x` 前缀（MMTYPE 解析值为 `'0x0030'` 形式字符串），关联请求/关联指示/发现列表等管理消息帧批量解析报 `invalid literal for int() with base 10` 并标记 ❌ 异常；改为 `int(val, 16)` + try/except 兜底。通道自动识别本身正常（3 帧均判为 PLC 载波），崩溃仅发生在摘要生成层
- **新一代载波协议(索引9)通道自动识别 PLC/HRF**（`csg_new_gen_parser.py` + `main_gui.py`）：`parse_to_table` 新增 `channel="auto"`，MPDU 级输入按 FC SOF 可变区域结构判别通道——表45(HRF)/表20(BPLC)/表23(ISAC) 三假设分别预测帧长与实际帧长比对，命中者胜；强信号：载荷PB大小=40 → HRF（表44 独有）、物理块个数>1 → PLC（无线仅支持1个PB）；解析结果新增「通道判定」行。GUI 通道下拉首位新增「自动识别」(默认，配置持久化)。新增 test_csg_hrf_mac.py T5-T8（用户PLC帧/合成HRF帧/PB40强信号/显式通道回归）
- **新一代载波协议(索引9)测试帧切频操作目标按 Option+信道号解析**（`csg_new_gen_cmd_payloads.py`）：测试模式/配置操作=6（频段切换操作/切频）的目标字段不再按 12bit 目标频段值（`20 00` 误显示 512）解析，改为 **Option(字节2高4位) + 无线信道号(字节3)**（`20 00` → Option=2, 信道号=0），与模式8（无线信道切换）一致；同步修正国网新一代 `gw_new_gen_cmd_payloads.py` 模式6（删除废弃 `_EXT_FREQ_BANDS`）并更新 `test_gw_ext_cmd.py` T3/T13/T14 断言
- **新一代载波协议无线信道单跳MAC帧解析**（`csg_new_gen_parser.py`）：
  - **版本2 单跳帧协议（表12，仅无线信道）MAC 帧头解析**：`_parse_mac_frame` 新增 `_parse_single_hop_mac` 分支——4 字节头（帧头类型1b+版本2b+保留5b / MSDU类型8b 表13 / MSDU长度16b 小端），载荷无 VLAN+类型前缀，按 MSDU 类型内联分派（1=应用层报文 / 2=无线发现列表 / 128=IPV4），尾部 CRC-32 校验
  - **无线发现列表消息（表139 MMeRF DiscoverNodeList）**：新增 `_parse_rf_discover_node_list`——站点MAC 6B + 统计序号 1B + 信息单元 TLV 链（类型7bit+长度类型1bit，长度1/2B），类型0 站点属性按表142 展开 14B（CCO MAC/代理TEI/角色/层级/RF跳数/接收率/发现列表周期/老化周期个数）
  - `parse_to_table` 步骤3 与 `_parse_pb_block` 尾段按版本2 定 4B 帧头长，`msdu_payload=b""` 防与内联解析重复
  - 顺带修正版本1 MAC 帧头「发送序号」字节序（`(byte1<<4)|byte0高4位` 小端，与表7/表11 及原始目的TEI/源TEI 约定一致）
  - 新增 `test_csg_hrf_mac.py`（4 用例：单跳帧直入 / 完整无线MPDU(fc_pb,hrf) / 无线发现列表 / PLC 短帧头回归）
- **GUI 按钮风格统一**：批量解析工具栏、LLM API 管理对话框、LLM 预处理面板按钮高度/内边距/字号统一（`main_gui.py` 新增 `_make_toolbar_btn`、`llm_api_manager.py` 新增 `_style_action_btn`、`llm_preprocess_widget.py` 新增 `_make_btn`）；修复 `_py_run_btn` 连接到不存在方法 `_run_py_script_file` 的 bug
- **国网新一代信标帧无 PBH 修复**（`gw_new_gen_parser.py`）：
  - **根因**：`_parse_beacon_frame` 对 HDC 1.0 和 HDC 2.0 信标帧都误读 1 字节 PBH，导致信标载荷首字节（信标类型）被当作 PBH 吃掉，信标类型错位 1 字节（如发现信标 0xC8 被误判成中央信标 0x42）
  - **协议依据**：HDC 1.0（5.1.2.4 节）与 HDC 2.0（表22）信标帧 PB 结构均为 FC + 信标载荷 + BPCS(4B CRC-32)，**无 PBH、无 PBCS**；表22 字段从字节0即信标类型，无 PBH 位置；文档第906行"以物理块头和物理块体为目标"是 **SOF 帧(图18)** 的 PBCS 描述，非信标帧
  - **修复**：`_parse_beacon_frame` 对 HDC 1.0/2.0 均不再解析 PBH，FC 后直接解析信标载荷；尾部校验从 BPCS(4B)+PBCS(3B) 改为仅 BPCS(4B)；同步修正 HDC 1.0 信标固定头保留区域为字节14-19（与表38一致，管理信息从字节20开始）
  - **验证**：用户提供的发现信标报文现正确识别为"发现信标"，4 个信标条目结构全部合法；全部 44 项回归测试通过
- **DLT645 数据域长度一致性校验增强**：
  - 解析器（`dlt645_parser.py`）新增数据长度声明值与实际帧长一致性检查，不匹配时 `valid=False` 并在 fields 中插入 `⚠ 数据长度错误` 行，**但仍尽力解析实际存在的所有字段**（地址、控制码、DI、数据内容、校验和均正常显示），不直接 return 空白结果
  - 校验器（`validator/dlt645_validator.py`）"数据长度"项从只检查上限 200 字节改为先校验声明长度与实际帧长一致性，不一致标记 FAIL 并置整体 `valid=False`
  - 设计原则：**协议字段声明与实际不一致时，不得静默截断也不得直接返回空白**，必须在用户可见结果中标红提示 + 尽力解析，保证用户点"解析"按钮始终有响应、有内容、知道哪里错了
- **新增「TCP 流量监控」标签页**（`monitor/tcp_monitor.py`，TCPMonitorWidget）：基于 scapy 抓包，支持网卡选择、BPF 过滤、TCP 流列表、双向流重组、监控封装解帧、原始 TCP 报文 / 解析结果分页展示、CSV 实时记录与历史 CSV 加载；可自动识别南网新一代 / 国网新一代并调用对应解析器
- **新增 Windows 系统集成**（`system_integration/`）：系统托盘、全局热键（默认 `Ctrl+Alt+X`）、单实例、命令行参数（`--parse` / `--protocol` / `--file` / `--minimized` / `--clipboard`）、文件右键菜单、开机自启、剪贴板报文自动检测与 Notepad++ 集成
- **剪贴板报文自动检测**（`clipboard_monitor.py` + `parse_prompt_dialog.py`）：任意软件复制 hex 报文即弹提示框，自动协议识别、协议切换、解析级别 / PB 帧类型选择，支持 `ED..EE` 监控头剥离
- **Notepad++ 集成**（`npp_integration.py`）：在 NPP 中选中报文 Ctrl+C 后，右键「用协议解析工具解析」或运行命令，通过 `--clipboard` 直接弹出解析结果
- **解析弹窗增强**：热键 / 命令行 / 文件右键共用解析弹窗，支持协议下拉切换、南网新一代 / 国网新一代解析级别与 PB 帧类型，`--parse` / `--file` / `--clipboard` 解析动作不再弹出主窗口
- **单实例加固**：`single_instance.py` 增加 ACK 握手，避免僵尸命名管道误判；`main()` 对解析动作与非解析动作区分窗口显示策略
- **新增表格右键复制与 Ctrl+C**：`main_gui.py`、`monitor/frame_monitor.py`、`monitor/tcp_monitor.py` 等解析结果表格支持复制选中行或全部
- **国网新一代 MME 管理消息解析持续完善**（`gw_new_gen_mme_parser.py`）：支持关联、代理变更、发现列表、网络冲突、无线信道冲突、过零 NTB、网络诊断等管理消息，MMTYPE 2 字节小端，0x0008 按发现列表处理
- **监控器日志路径显示与浏览**（`monitor_widget.py`）：CSV 记录结束后可直接打开日志目录
- `南网协议解析工具.spec` hidden imports 已补齐 `system_integration` 各模块

### 1.11.1 — 2026-08-04
- **修复勾选「ED监控协议」后不完整/非法 ED..EE 帧被静默回退为 FC 起始解析的 bug**：单帧解析（`parse_single`）、解析弹窗（`_parse_and_show_dialog._preprocess`）、批量解析三处路径在 `_parse_ed_monitor_header` / `_extract_business_from_ed_frame` 校验失败时明确报错（报文不完整/缺 EF 或 EE），首字节 ED 不再被当作南网新一代 FC 起始符
- 新增 `test_ed_fallback_fix.py`（14 用例）

### 1.11.0 — 2026-08-01
- **新一代载波协议(通感一体化,索引9)网间协调帧(NET,定界符类型=3)可变区域解析**：邻居网络比特图1~4 / 本网络无线信道编号 / 持续时间(40ms) / 带宽结束标志位 / 本网络无线option / 带宽结束偏移(4ms) / 带宽开始偏移(4ms)，字节12短网络标识高位组合完整SNID（表41）
- **新一代载波协议聚合帧级联块应用层解析**：抽取 `_parse_msdu_payload` 共享方法，级联块内 MAC 帧解析 MSDU 头并分派应用层报文（端口/控制域/业务标识/转发DLT645），消除伪 MSDU 残留行
- 新增 `test_net_frame_real` / `test_net_frame_nonzero_fields` / `test_aggregated_frame_app_layer` 回归用例

### 1.10.0 — 2026-07-31
- **新增「主题与字体设置」**（菜单 配置→主题与字体）：5 套主题（默认浅色 / Fusion经典 / Fusion暗色 / Windows原生 / WindowsVista原生），切换即时预览
- 全局样式表升级为**应用级**：QMessageBox / 文件对话框等所有弹窗统一跟随主题
- **字体设置**：字体族（系统字体列表）+ 字号（8~24pt），与主题一起持久化到 `config.json` 的 `ui` 段
- 暗色主题下自动适配统计标签 / 串口状态 / 批量状态等动态控件配色（`_restyle_for_theme` + `_make_stats_label` 等辅助方法）
- 新增 `theme_settings.py`（主题注册表 + ThemeManager + ThemeSettingsDialog）与 `test_theme_settings.py`

### 1.9.5 — 2026-06-27
- **国网新一代（索引 10）自动区分 HDC 1.0 / HDC 2.0**：依据 FC 字节 12 高 4 位标准版本号，解析后新增「协议版本判定」行
- HDC 1.0 下聚合帧标志 / 发送帧序号 / 链路标识符回退为保留字段；HDC 2.0 使用新消息类型表与聚合 MAC 帧标志
- 新增 `test_gw_new_gen.py` 版本区分用例

### 1.9.4 — 2026-06-27
- **国网新一代解析级别新增「FC+PB解析(完整MPDU)」**：FC(16B) + 完整物理块 PB
- 修正 FC+MAC 解析未计算 PBH(1B) 的缺陷，新增 `_locate_pbh_mac` 定位

### 1.9.3 — 2026-06-27
- 修复国网新一代完整帧结构解析：MPDU = FC(16B) + PB，PB = PBH(1B) + MAC帧头 + MSDU，FC 末 3 字节为 FCCS，其后直接为 PB，无独立 HCS
- 新增 `_pbh_row` 展示 PBH 位域

### 1.9.2 — 2026-06-27
- **国网新一代监控 / 批量摘要增强**：NID、帧类型、MMTYPE、源→目的 TEI、报文 ID、方向、规约、数据长度等关键信息
- 新增 `_get_gw_new_gen_summary` 与 `test_gw_monitor_summary.py`

### 1.9.1 — 2026-06-27
- **监控器新增「监控解帧(96..16)」模式**：按监控设备包装格式自动解帧，正确处理连帧与分片
- 包装格式：`96H + RSSI(1) + NTB(4,小端) + [LEN(12b) + 协议类型(3b) + CHANNEL(1b)] + DATA(LEN) + CS(1) + 16H`
- 新增 `test_monitor_deframe.py`

### 1.9.0 — 2026-07-08
- **新增「监控器」标签页**：南网新一代（索引 9）/ 国网新一代（索引 10）串口实时报文监控
- 静默间隔自动组帧、报文头尾剔除、1000 帧环形缓冲、过滤 / 暂停 / 清空 / CSV 导出、解析行字节高亮
- 新增 `monitor_widget.py` 与 `test_monitor_widget.py`

### 1.8.2 — 2026-07-06
- **新增「报文对比」标签页**：协议感知的双报文对比分析，支持字节级对比（字段感知对齐+差异高亮）和字段级语义对比（偏移/长度/值/差异类型）
- 支持差异人话解读（自然语言解释业务含义）、配置选项（忽略校验和/序列号、仅显示差异）、导出对比报告
- 新增 `frame_diff_engine.py`（帧对比引擎，FrameDiffEngine）和 `diff_widget.py`（GUI 组件，DiffWidget）
- **新增 TUI 版本**：`tui_app.py` + `tui_app.tcss`，基于 Textual 框架，支持单帧解析+字节高亮、批量多帧解析+摘要、协议一致性校验
- 新增 `test_diff_engine.py`（对比引擎测试）、`_tui_smoke_test.py`（TUI 冒烟测试）
- `main_gui.py`：集成 DiffWidget 标签页，`APP_VERSION` bump 至 `1.8.2`
- `test_plan_widget.py`：功能增强（+421 行）

### 后续更新（2026-07-20 ~ 2026-07-29）
- **新增「报文工具」标签页**（`message_tool_widget.py`）：ASCII/HEX 双向转换、DLT645 偏移（±0x33H）、字节逆序、报文↔Pn/Fn 转换、CRC/校验和计算、HEX↔bitstring 转换，20/20 功能测试通过
- **修复国网新一代双模协议双击深度解析**：`main_gui.py` 修复双击表格行无法触发深度解析
- **修复国网新一代 MSDU 定位**：`gw_new_gen_parser.py` 跳过 HCS(3B)+物理块头(1B)，正确定位 MSDU 起始
- **添加 `parse_command_payload` 入口函数**：`gw_new_gen_cmd_payloads.py` 修复 ImportError

### 1.8.1 — 2026-06-27
- **测试方案新增 Lua 脚本支持**：测试项「性质」新增「Lua脚本」类型，可在测试流程中嵌入可编程逻辑（条件分支、循环遍历、数据解析、变量共享、动态组帧、延时控制）
- 新增 `lua_script_engine.py`（Lua 脚本引擎），通过 `lupa`（Python-Lua 桥接）提供 API：`send` / `wait_for_response` / `wait` / `log` / `hex_to_bytes` / `bytes_to_hex` / `get_last_response` / `get_test_var` / `set_test_var` / `stop`
- 新增 `test_lua_engine.py`（Lua 引擎测试）
- 新增 `docs/Lua脚本使用说明.md`（Lua 功能用户文档）
- `test_plan_widget.py` 新增 `LuaCodeEditor`（带行号+列线指示器的代码编辑器）与 Lua 模式切换逻辑
- `serial_worker.py` 新增 `raw_data_received` 信号供 Lua 引擎桥接器接收原始串口数据
- 依赖：`lupa`（未安装时 `LUA_AVAILABLE=False`，Lua 脚本类型不可用但其他功能不受影响）

### 1.8.0 — 2026-07-04
- **新增 DLMS-APDU(国网) 协议选项（索引3）**：复用 HDLC 解析器的 APDU 深度解析功能，专门服务国网 DLMS 报文
- **HDLC/DLMS 协议重命名为 HDLC/国网DLMS**：明确国网协议背景，与新增的 DLMS-APDU(国网) 配套
- **协议索引重新编号**：原 3~8 顺延为 4~9，共 10 种协议，所有索引硬编码位置已同步更新

### 1.7.2 — 2026-06-21
- **修复新一代载波协议(索引8)选择确认帧(SACK)解析**：
  - `_parse_mpdu_sack` 返回值从 `offset + 1` 修正为 `offset + 11`，与其他子解析器一致
  - 公共代码 `parse_mpdu` 字节12处理增加 SACK 定界符类型分支：SACK 帧字节12 = 扩展帧类型(4b) + 标准版本号(4b)，不再误解析为短网络标识高位
  - `parse_to_table` auto 模式增加 SACK 早期返回：SACK 帧仅 FC 头16字节，无物理块/MSDU，解析完 FC 后直接返回，避免将 FC 头误当 MSDU 数据解析
  - 删除 `_parse_mpdu_sack` 中冗余的字节12读取
- **新一代载波协议(索引8)批量解析摘要增强**：`_extract_csg_core_content` 按帧类型+业务标识提取关键业务内容
  - 确认帧：显示确认状态（如"确认报文，无业务数据"）
  - 否认帧：显示否认原因（如"原因:格式错误"）
  - 数据传输帧：显示源/目的地址 + 数据长度
  - 命令帧：显示命令名 + 设备地址 + 关键参数（延时时间/查询数量等）
- 新增测试 `test_sack_fix.py`（SACK 帧解析验证用例）

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


**最近一次（2026-08-21）：发布 1.14.5（协议11 升级位图 + 台区户变深度解析）**

变更：
- **协议11（HDC 1.0）查询站点升级状态上行报文解析**：`hdc10_parser.py` 0x034 此前只按下行表40 解析，上行应答的 升级状态/有效块数/升级位图 全部丢失；现按文档第4-3部分 表45 补全 升级状态(0空闲/1接收进行/2接收完成/3升级进行/4试运行) + 有效块数 + 起始块号 + 升级ID + 接收位图（每bit一个文件块，显示 `N/M块已接收`）。**位图逐块编号明细**：按 起始块号+i 编号、每行32块多行展开，`[✓n]`=已接收 `[✕n]`=丢包。方向判定 len>12 或状态位∈{1..4} 判上行。`test/test_hdc10.py` 增至 10 项（上行全收/下行/丢包编号）全过
- **协议11（HDC 1.0）台区户变关系识别(0x0A1)深度解析**：修复报文头长度公式——6bit值(byte0[6:7]高2位+byte1[0:3]低4位)×4字节，此前公式错致 12 字节头算成 48 字节、DATA 只剩尾部切片；校时/事件/通信测试/注册/升级等 7 处统一修正。DATA 按采集类型深度解析：采集启动(表56)/特征信息告知(表57 TEI+采集方式+告知总数+NTB+特征序列)/判别结果信息(表61)；特征序列按特征类型分派 工频电压(BCD XXX.X 大端)/工频频率(BCD XX.XX 大端)/工频周期(有符号偏差+μs)，三相逐相展开，双沿采集解 NTB2+第二组序列。`test/test_hdc10.py` 增至 16 项全过

涉及文件：
- 修改：`hdc10_parser.py`、`test/test_hdc10.py`、`main_gui.py`（APP_VERSION 1.14.5）、`AGENTS.md`

**上一次（2026-08-21）：发布 1.14.4（协议8 组帧/解析对齐官方工具）**

变更：
- **A-XDR 复合类型计数语义修复**：array/structure tag 后字节 = **元素个数**非字节总长（文档附录 H.3.2）。组帧 3 项 structure 由误填 09 改为 03；编码器（`frame_gen_widget.py` / `reflex_web/frame_gen_utils.py`）+ 解码器（`dl_t698_45_axdr.py` 按个数循环）同步修复
- **SET/ACTION 组帧补尾部 TimeLabel**：文档 H.4/H.5 GET/SET/ACTION 请求均以 OPTIONAL TimeLabel 结尾（00=无），此前仅 GET 补 `00`；修复两条 GUI 生成路径与 `frame_gen_utils.py::build_dlt698_axdr_apdu`
- **解析表格成员逐项展开**（`dl_t698_45_parser.py::_add_axdr_item_rows`）：array/structure 为每个成员生成子行（原始编码/值/类型说明），嵌套递归展开，对齐官方工具
- **请求尾部 TimeTag 解析**（`dl_t698_45_apdu_parser.py::_parse_time_tag`）：GET/SET/ACTION Normal/NormalList 六分支统一解析，表格显示「时间标签 | 0x00 | 无时间标签」
- **组帧 OI 增强**：预定义/A-XDR 模式 OI 均支持「预设下拉 + 手动 hex」；A-XDR 新增「描述符类型」OAD/OMD 切换
- **内嵌部署增量构建**：`build_embedded_deploy.py --skip-deps` 复用已有 python/ 目录，重复构建 10+ 分钟 → 约 1 分钟
- **修复协议8 预设命令保存/显示**（`preset_buttons.py`）：新增 `DLT698_command.json` 独立预设文件（此前 dlt698 预设被误存入 `GW_command.json`）；`set_protocol` 支持 dlt698（此前静默忽略致预设页看不到 698 按钮）；加载时按 protocol 过滤历史混入条目；`AddPresetDialog` 协议行显示「698.45 协议」

涉及文件：
- 修改：`dl_t698_45_axdr.py`、`dl_t698_45_apdu_parser.py`、`dl_t698_45_parser.py`、`frame_gen_widget.py`、`preset_buttons.py`、`reflex_web/frame_gen_utils.py`、`reflex_web/build_embedded_deploy.py`、`test/test_web_frame_gen_utils.py`（63项）、`test/test_dl_t698_45_data_decode.py`、`main_gui.py`（CHANGELOG/APP_VERSION 1.14.4）、`AGENTS.md`
- 新增：`test/test_dlt698_preset.py`（31 项）

**上一次（2026-08-19）：发布 1.14.3（EB030307 过零NTB值上行数据解析）**

变更：
- **ACTION-Response NormalList 数据个数兼容**（`dl_t698_45_apdu_parser.py`）：福建简化698 响应每项 = OMD + DAR + **数据个数**(1B) + [Data A-XDR]×N；此前 DAR 后 `01` 被当 A-XDR array tag（长度09）解，后续 `0x81` 报「未知类型」。新增 `_parse_axdr_items_or_single`：先按「个数N + N项A-XDR」解，失败回退单 A-XDR（兼容文档示例无前缀）
- **EB030307 字段 schema**（`gdw_eb_di_fields.py`）：数据开始时间 bcd_time(6B) / 边沿类型 enum(0保留/1下降沿/2上升沿) / 数据周期_分钟 uint8 / 数据点数M uint8 / NTB值数组 list（每项 相线1/相线2/相线3 NTB值 uint32，40ns，单相表2/3填0）
- **bcd_time 可读化**：YYMMDDhhmmss BCD → `2026-08-14 14:42:00`；EB030307 请求参数（`1C` 开头）优先 date_time_s 时间解码，响应/上报数据走字段 schema；数据不足固定头回退 A-XDR 头+原始数据
- **新增测试**：`test_dl_t698_45_fujian.py` 增至 12 项（用户真实上行帧 129B→10 组相线 NTB 值 + 表格展示）；全量回归 62+19+12 项通过；Web 实测显示 数据开始时间/边沿类型/数据周期/数据点数/NTB 值数组（10 组相线1/2/3）

涉及文件：
- 修改：`dl_t698_45_apdu_parser.py`、`gdw_eb_di_fields.py`、`main_gui.py`（CHANGELOG/APP_VERSION 1.14.3）、`AGENTS.md`、`test/test_dl_t698_45_fujian.py`

**最近一次（2026-08-19）：发布 1.14.2（协议8 福建简化698 解析）**

变更：
- **协议8（DL/T 698.45）福建简化698 解析**（`dl_t698_45_apdu_parser.py`）：新增 SET-Request/Response、ACTION-Request/Response 的 choice=0x02 NormalList 分支（PIID + count + SEQUENCE OF {OAD/OMD, Data/DAR}），支持福建「本地通信模块扩展协议」V3.42 698 承载格式——EB030110 台区识别、EB030307 过零NTB 等此前只能解析出「子类型码:0x02」，现完整解析 PIID/count/OAD/OMD/数据
- **REPORT 带 count 结构**：REPORT-Notification（`88 01 PIID-ACD count OAD列表 数据个数01 A-XDR 00 00`）/ REPORT-Response（`08 01 PIID-ACD count OAD 结果`）按福建示例解析，OAD 逐项中文名 + 数据业务解码
- **EB 名称与字段解码**：OAD/OMD 的 OI 高字节 0xEB 时按 4 字节原样查 `gdw_eb_di_lookup`（57 项）显示 EB 名称；数据内容按 `gdw_eb_di_fields`（42 项）字段 schema 解码（enum→名称/uint→值/bcd/bs8/list），无 schema 保留原始 hex
- **修复 EB uint 字节序**：按文档「645 减33逆序」规则 EB 数据内容多字节 uint 为**大端**（编码器 `gdw_eb_di_fields.py` 同步修正，`test_gdw_fujian.py`/`test_web_frame_gen_utils.py` 断言更新）
- **新增测试** `test/test_dl_t698_45_fujian.py`（9 项：用户实测帧/文档示例 SET/ACTION/REPORT/多对象/大端）；Web 浏览器实测用户帧显示 ActionRequestNormalList + 台区识别方法=自动 + 识别时长=5

涉及文件：
- 修改：`dl_t698_45_apdu_parser.py`（List 分支 + EB 名称/字段解码 + uint 大端）、`gdw_eb_di_fields.py`（编码大端）、`main_gui.py`（CHANGELOG/APP_VERSION 1.14.2）、`AGENTS.md`、`test/test_gdw_fujian.py`、`test/test_web_frame_gen_utils.py`、`test/test_dl_t698_45_data_decode.py`（REPORT count 结构）
- 新增：`test/test_dl_t698_45_fujian.py`

**最近一次（2026-08-17）：发布 1.14.1（协议8 APDU 数据内容业务解码）**

变更：
- **协议8（DL/T 698.45）APDU 数据内容业务解码**（新增 `dl_t698_45_data_decode.py`）：新建 CLASS_ATTR_TEMPLATES（电能量类(1)/最大需量类(2)/分相变量类(3)/功率类(4)/谐波类(5)/数据变量类(7) 的属性→格式模板）+ OI_UNIT_HINT（电压 V/电流 A/电能量 kWh/需量 W/相角 °/频率 Hz 等）+ UNIT_CODE_MAP 单位码表，`decode_oad_data(oi, attr_id, data)` 统一入口按 OAD 解码为业务值
- **APDU 解析器接入**（`dl_t698_45_apdu_parser.py`）：新增 `_decode_oad_business` 辅助，GET-Response Normal/NormalList/Next、SET-Request、REPORT-Notification Normal 解析结果新增「数据业务」键（不破坏原始 A-XDR「数据」）；REPORT-Notification Normal 补齐 OAD 解析
- **GUI 表格**（`dl_t698_45_parser.py`）：「数据业务」按项展开展示（总/费率N/A相/B相/C相 + 单位）
- **修复 DLT69845Validator 长度域一致性公式**：698.45 L = 不含起始符和结束符的数据长度（文档附录 H.1：帧长32 → L=30），原公式 +4 误判合法帧，改 +2
- **新增测试** `test/test_dl_t698_45_data_decode.py`（10 项）；`test_dl_t698_45.py`、`test_gdw_fujian.py`（19项）、`test_web_frame_gen_utils.py`（62项）回归全过

涉及文件：
- 新增：`dl_t698_45_data_decode.py`、`test/test_dl_t698_45_data_decode.py`
- 修改：`dl_t698_45_apdu_parser.py`、`dl_t698_45_parser.py`、`validator/dl_t698_45_validator.py`、`main_gui.py`（CHANGELOG/APP_VERSION 1.14.1）、`AGENTS.md`、`test/test_web_frame_gen_utils.py`（长度域断言注释）

**最近一次（2026-08-15）：Reflex Web 版协议组帧完整复刻**

变更：
- **Reflex Web 版组帧能力与 GUI 对齐**（`reflex_web/reflex_web.py`）：南网(0)/国网(7)/698.45(8) 三种协议、三种字段录入模式全部复刻——预定字段（predefined，按字段类型分派 uint/enum/bytes/ascii/bcd/oi/oad_list/list/sub_fields）、自定义模板（custom，字节/uint8/16/32/校验和，支持推荐序与 checksum 回填）、A-XDR（698.45 专属，单层数据项编辑器，复合类型由纯函数完整支持）
- **新增纯逻辑模块 `reflex_web/frame_gen_utils.py`**：`collect_field_values`（位置对齐数组→name-keyed dict，sub_fields 父值由生成器 Pass3 打包）、`generate_custom_data`、`build_dlt698_sa`、`build_dlt698_axdr_apdu`、`encode_axdr_items`，无 Reflex 依赖，可被独立测试断言字节与 GUI 生成器一致
- **实时回读预览**：字段 setter 与「生成帧」后自动重新组帧并送回解析器（`_refresh_gen_preview` / `gen_preview_rows` 表格），再现 GUI 200ms 实时预览
- **预设命令按钮**：读取 `NW_command.json`（南网）/`GW_command.json`（国网），按分组渲染按钮一键填入结果区；支持「保存为预设」
- **698.45 SA/控制字段**：地址类型/逻辑地址/地址长度/SA hex + seg/sc/func 下拉；**国网中继地址** A2 逗号分隔输入
- **Reflex 兼容性适配**：字段编辑器用位置索引数组（`gen_field_values/gen_list_rows/gen_sub_fields` + 渲染模型 `gen_field_meta/gen_field_enum/gen_field_items/gen_field_subs` 等全 str 平行数组）规避 Reflex `foreach` 无法遍历 Any 值 dict、Var 不能作 dict key、`rx.wrap`/`rx.textarea` 不存在的限制

涉及文件：
- 新增：`reflex_web/frame_gen_utils.py`、`test_web_frame_gen_utils.py`
- 修改：`reflex_web/reflex_web/reflex_web.py`、`README.md`、`AGENTS.md`

验证：`python test_web_frame_gen_utils.py` 18 用例全过（南网含 list/enum/sub_fields、国网从节点列表、698.45 A-XDR/SA 字节与 GUI 生成器一致）；`State` 冒烟 9 项全过；`reflex export` 后 `python reflex_web/run_app.py` 返回 HTTP 200

**最近一次（2026-08-14）：发布 1.13.0**

变更：
- **新增独立协议「HDC 1.0 双模互联互通」（索引 11）**：主程序支持 12 种协议。新增 `hdc10_parser.py`（HDC10Parser，Q/GDW 12087.42-2020）、`hdc10_mme_parser.py`、`validator/hdc10_validator.py`、`test_hdc10.py`
- **GUI 集成**（`main_gui.py`）：协议下拉框新增 `[11]`；解析级别 + 通道下拉复用国网新一代控件（`_hdc10_parse_level` / `_hdc10_channel`）；查询页新增 `_create_hdc10_lookup_content`（报文 ID/端口/消息类型映射）；校验注册 `_run_validation` 11 → HDC10Validator；批量解析复用 `_strip_gw_new_gen_prefix` 前缀剥离与 `_get_gw_new_gen_summary` 摘要
- **新一代载波协议(索引9)增强**：通道自动识别 PLC/HRF（`channel="auto"`）、无线单跳 MAC 帧（版本2/表12）、切频操作目标按 Option+信道号解析、批量摘要 `0x` 前缀崩溃修复
- **易用性**：协议选择持久化、全表格 Ctrl+滚轮缩放（ZoomableTableWidget）、校验结果展开/收缩 + 结果表全屏、GUI 按钮风格统一；国网新一代信标帧无 PBH 修复；DLT645 数据长度一致性校验增强
- **版本 bump**：`APP_VERSION` → 1.13.0，`BUILD_DATE` → 2026-08-14，`CHANGELOG` 新增 1.13.0 条目；文档（README/AGENTS.md/CLAUDE.md）同步至 12 种协议

涉及文件：
- 新增：`hdc10_parser.py`、`hdc10_mme_parser.py`、`validator/hdc10_validator.py`、`test_hdc10.py`
- 修改：`main_gui.py`、`README.md`、`AGENTS.md`、`CLAUDE.md`、`南网协议解析工具.spec`

---

**上一次（2026-08-11）：DLT645 数据域长度一致性校验增强**

变更：
- **DLT645 解析器新增数据长度一致性校验**（`dlt645_parser.py`）：声明值与实际帧长不匹配时，`valid=False`，fields 插入 `⚠ 数据长度错误` 行，但仍尽力解析所有可见字段（地址/控制码/DI/数据内容/校验和正常显示），不返回空白结果
- **DLT645 校验器数据长度项改为一致性校验**（`validator/dlt645_validator.py`）：从只检查 >200 字节上限告警改为先校验声明值与实际帧长是否一致，不一致标记 FAIL
- 确立容错显示原则：字段声明与实际不一致时，不得静默截断也不得直接返回空白，必须标红提示 + 尽力解析

涉及文件：
- 修改：`dlt645_parser.py`、`validator/dlt645_validator.py`、`README.md`、`AGENTS.md`

---

**上一次（2026-08-04 前后）：TCP 流量监控 + 系统集成 + 1.11.x 功能**

变更：
- **新增「TCP 流量监控」标签页**（`monitor/tcp_monitor.py`，TCPMonitorWidget）：基于 scapy 的 TCP 抓包、流列表、双向流重组与南网新一代 / 国网新一代自动解析
- **新增 Windows 系统集成**（`system_integration/`）：系统托盘、全局热键、剪贴板报文自动检测、Notepad++ 集成、单实例、命令行解析、文件右键菜单与开机自启
- **剪贴板报文自动检测**：任意软件复制 hex 报文自动弹提示框，支持协议 / 解析级别 / PB 帧类型选择与 `ED..EE` 监控头剥离
- **解析弹窗与命令行增强**：热键 / 命令行 / 文件右键共用解析弹窗，新增 `--clipboard`，解析动作不弹出主窗口
- **新增表格右键复制与 Ctrl+C**：单帧 / 批量 / 监控 / TCP 监控等表格可复制选中行或全部
- **国网新一代 MME 管理消息解析持续完善**（`gw_new_gen_mme_parser.py`）：MMTYPE 2 字节小端，0x0008 按发现列表处理，覆盖关联、代理变更、网络冲突、无线信道冲突、过零 NTB、网络诊断等消息
- **监控器日志路径显示与浏览**（`monitor_widget.py`）：CSV 记录后可打开日志目录
- **重写 `README.md`**：按中文技术文档规范补全 1.9.x / 1.10 / 1.11 功能、TCP 监控、实时监控器、多端入口与当前项目结构
- **恢复并更新 `AGENTS.md`**：保留 Trellis 管理块，补齐 1.9.0~1.9.5 变更日志、当前解析级别、MME/HDC 说明与 TCP 监控注意事项

涉及文件：
- 新增：`monitor/tcp_monitor.py`
- 修改：`main_gui.py`、`monitor_widget.py`、`gw_new_gen_parser.py`、`gw_new_gen_mme_parser.py`、`README.md`、`AGENTS.md`

---

**上一次（2026-07-31）：新增主题与字体设置**

变更：
- **新增「主题与字体设置」**（`theme_settings.py`，ThemeSettingsDialog）：主题下拉 5 套内置主题（默认浅色/Fusion经典/Fusion暗色/Windows原生/WindowsVista原生），切换即时预览；字体族（QFontComboBox 系统字体列表）+ 字号（QSpinBox 8~24pt）
- **全局样式表升级为应用级**：原 `MainWindow.apply_styles` 的浅色 QSS 迁入 `theme_settings.py:LIGHT_QSS` 并在 `main()` 通过 `ThemeManager.apply_from_file(app)` 应用，QMessageBox/文件对话框等所有弹窗统一跟随主题
- **新增 Fusion 暗色主题**（`DARK_QSS`）：完整覆盖按钮/表格/菜单/滚动条/下拉框/复选框等全部控件配色
- **字体设置持久化**：`config.json` 新增 `ui` 段（`theme`/`font_family`/`font_size`），`_save_app_config`/`_load_app_config` 读写；`ThemeManager.load_from_config`/`to_config` 封装
- **暗色主题动态控件适配**：`_restyle_for_theme` + `_make_stats_label`/`_batch_count_style`/`_batch_status_style`/`_serial_status_style`/`_serial_refresh_style` 辅助方法，统计标签/串口状态/批量状态/刷新按钮随主题重设

涉及文件：
- 新增：`theme_settings.py`、`test_theme_settings.py`
- 修改：`main_gui.py`（主题/字体应用、菜单入口、配置持久化、动态控件适配）、`AGENTS.md`

---

**上一次（2026-07-29，commit `f8d92ff`）：新增报文工具标签页 + 国网新一代修复**

变更：
- **新增「报文工具」标签页**（`message_tool_widget.py`，MessageToolWidget）：提供协议报文处理常用工具，包括 ASCII/HEX 双向转换、DLT645 偏移（±0x33H）、字节逆序、报文↔Pn/Fn 转换、CRC-16/24/32 校验和计算、HEX↔bitstring 转换等
- **修复国网新一代双模协议支持双击深度解析**（`main_gui.py`）：修复双击表格行无法触发深度解析的问题
- **修复国网新一代解析器 MSDU 定位**（`gw_new_gen_parser.py`）：跳过 HCS(3B)+物理块头(1B)，正确定位 MSDU 起始
- **添加 `parse_command_payload` 入口函数**（`gw_new_gen_cmd_payloads.py`）：修复 ImportError

涉及文件：
- 新增：`message_tool_widget.py`（377 行）
- 修改：`main_gui.py`（+9 行）、`gw_new_gen_parser.py`（+18/-11 行）、`gw_new_gen_cmd_payloads.py`（+46 行）

---

**上一次（2026-07-16，commit `6e6e8ac`）：新增 NiceGUI Web 版本 + 报文对比增强 + 增强导出功能**

变更：
- **新增 NiceGUI Web 版本**（`web_app.py` + `web/` 目录）：基于 NiceGUI 框架的浏览器解析器，支持完整 11 种协议解析，支持单帧/批量/报文对比/组帧/预设/查询/测试计划/档案/拓扑等标签页，集成串口通信（SerialAdapter），暗色主题自定义 CSS，健康检查端点 `/health`
- **报文对比增强**（`diff_widget.py`）：新增差异人话解读（自然语言描述业务含义）、配置选项（忽略校验和/序列号、仅显示差异）、导出对比报告功能
- **增强导出功能**（`enhanced_export.py`）：Excel 增强导出（支持协议元数据、字节高亮样式、分 Sheet 导出），CSV/TXT/JSON 多格式导出
- **TUI 版本优化**（`tui_app.py`）：优化批量解析摘要显示，修复协议切换时的界面刷新问题
- **Web 布局调整**（`web/main_page.py`、`web/tabs/single_parse.py`、`web/components/parse_table.py`）：固定高度 + 内容滚动，避免顶栏重叠；CSG 控制条仅在协议 9 下显示
- `test_plan_widget.py`：功能增强（+421 行）
- **新增国网新一代双模通信互联互通协议（索引10）**：`gw_new_gen_parser.py` (GWNewGenParser) + `validator/gw_new_gen_validator.py`，复用新一代载波解析框架

涉及文件：
- 新增：`web_app.py`、`web/` 目录（`main_page.py`、`tabs/`、`components/`、`adapters/`、`styles/custom.css`、`protocol_registry.py`、`frame_extractor.py`）、`enhanced_export.py`、`gw_new_gen_parser.py`、`validator/gw_new_gen_validator.py`、`docs/superpowers/specs/2026-07-15-nicegui-web-version-design.md`、`docs/superpowers/plans/2026-07-15-nicegui-web-version-plan.md`
- 修改：`main_gui.py`、`test_plan_widget.py`、`config.json`、`test_plan.json`、`diff_widget.py`、`tui_app.py`

依赖：`nicegui`（Web 版）、`pyserial`（Web 版串口）、`textual`（TUI 版，可选），`pip install nicegui pyserial textual`

---

**上一次（2026-07-06，commit `087d03e`）：新增协议感知报文对比功能模块 + TUI 版本**

变更：
- 新增 `diff_widget.py`（DiffWidget）：报文对比标签页，支持双报文输入、字节级对比（字段感知对齐+差异高亮）、字段级语义对比（偏移/长度/值/差异类型）、差异人话解读、导出对比报告
- 新增 `frame_diff_engine.py`（FrameDiffEngine）：协议感知帧对比引擎，支持完整对比流程和结果结构化
- 新增 `tui_app.py`（936行）+ `tui_app.tcss`：基于 Textual 的终端图形化解析器，支持 9 种协议的解析、批量多帧解析+摘要、协议一致性校验
- 新增 `test_diff_engine.py`（对比引擎测试）、`_tui_smoke_test.py`（TUI 冒烟测试）、`docs/_gen_diff_mockup.py`（对比 UI 原型生成）
- `main_gui.py`（+23 行）：导入并集成 DiffWidget 标签页
- `test_plan_widget.py`（+421 行）：功能增强
- `config.json`：串口端口号改为 COM4

涉及文件：
- 新增：`diff_widget.py`、`frame_diff_engine.py`、`tui_app.py`、`tui_app.tcss`、`test_diff_engine.py`、`_tui_smoke_test.py`、`docs/_gen_diff_mockup.py`、`docs/diff_mockup.html`、`docs/diff_mockup.png`
- 修改：`main_gui.py`、`test_plan_widget.py`、`config.json`、`test_plan.json`

依赖：`textual`（TUI 版本，`pip install textual`），可选

---

**上一次（2026-07-04）：新增 DLMS-APDU(国网) 协议选项，协议索引重编号**

变更：
- `main_gui.py`：下拉框插入"DLMS-APDU(国网)"（索引3），"HDLC/DLMS"重命名为"HDLC/国网DLMS"
- `main_gui.py`：所有索引 3~8 硬编码位置顺延为 4~9，共 10 种协议
- 新协议复用 HDLCParser.parse_apdu_to_table，无需新增解析器文件
- 校验器、帧提取、方向提取、字节剔除、摘要生成等均已同步更新索引

涉及文件：
- 修改：`main_gui.py`、`AGENTS.md`

验证：GUI 手动检查各协议切换、解析、查询页正常（待执行）

---

**上一次（2026-06-21）：SACK解析 + 增强批量摘要业务内容**

修复1：SACK帧字节12被公共代码误解析为"短网络标识高位"，实际应为"扩展帧类型(4b) + 标准版本号(4b)"。
修复2：SACK帧仅FC头16字节无载荷，auto模式将FC头误当MSDU数据继续解析导致"解析失败"。
增强3：`_extract_csg_core_content` 按帧类型+业务标识提取关键业务内容，批量摘要不再只显示"业务标识:确认"。

修复：
- `csg_new_gen_parser.py` `_parse_mpdu_sack`：返回值从 `offset + 1` 修正为 `offset + 11`（不再消费字节12）
- `csg_new_gen_parser.py` `_parse_mpdu_frame` 字节12：增加 `delimiter_type == 2` 分支，SACK帧正确解析扩展帧类型
- `csg_new_gen_parser.py` `parse_to_table`：auto模式增加SACK早期返回（`elif delimiter_type == 2: return table_data`），避免将FC头误当MSDU
- 删除 `_parse_mpdu_sack` 中冗余的字节12读取（避免重复条目）
- `main_gui.py` `_extract_csg_core_content`：重写为按帧类型分支提取（确认/否认/数据传输/命令帧各有专属提取逻辑）

验证：全部 26 项测试通过（18 基础 + 6 摘要 + 1 批量 + 1 SACK 专项）

---

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
- `README.md` — 用户面向的简要说明（功能列表、运行方式、项目结构，包含 Web 版/698.45/新一代协议等）
- `CLAUDE.md` — Claude Code 专用指南（与本文档部分重叠，**以 AGENTS.md 为权威**）
- `work_list.md` — 工作清单/字段定义（开发参考）
- `docs/superpowers/specs/2026-05-12-dl-t698-45-parser-design.md` — 698.45 解析器设计规格
- `docs/superpowers/plans/2026-05-12-dl-t698-45-parser.md` — 698.45 实现计划
- `docs/superpowers/specs/2026-05-09-topology-formation-timing-design.md` — 拓扑组网时序设计
- `docs/superpowers/specs/2026-07-15-nicegui-web-version-design.md` — NiceGUI Web 版设计规格
- `docs/superpowers/plans/2026-07-15-nicegui-web-version-plan.md` — NiceGUI Web 版实现计划
- `.sisyphus/plans/csg_new_gen_parser.md` — 新一代载波解析器实现计划
- `.trellis/workflow.md` — Trellis 开发工作流、任务生命周期与子代理约定
- `.trellis/spec/` — 按包/层组织的编码规范与质量检查
- `monitor/tcp_monitor.py` 头部说明 — TCP 监控封装解帧格式与流重组设计
- `system_integration/` — 系统托盘、全局热键、单实例、右键菜单、剪贴板检测、Notepad++ 集成与系统设置实现
- `国网新一代协议/HDC-国网双模协议/` — HDC 1.0（索引 11）参考文档（双模技术规范第 1/4-1/4-2/4-3 部分，.md/.pdf）
- `hdc10_parser.py` 头部注释 — HDC 1.0 帧结构与解析约定（Q/GDW 12087.42-2020）

> **冲突处理**：当 AGENTS.md 与 QWEN.md / CLAUDE.md / README.md 内容冲突时，**以 AGENTS.md 为准**。本文档随代码同步更新。

---

## 13. Agent 上手 Checklist

接手项目时按以下顺序操作：

- [ ] 通读本文件（§1~§9 是核心，§10~§11 是最新动态），并按 `.trellis/workflow.md` 判断当前阶段
- [ ] 如修改代码，先读取 `.trellis/spec/` 中对应层级的规范
- [ ] `python main_gui.py` 启动 GUI，逐个协议切下拉框，确认能跑
- [ ] 查 `git log --oneline -20` 了解最近提交
- [ ] 查 `git status` 了解未提交改动
- [ ] 根据**要修改的协议**，按 §5 找到对应 parser 和参考文档
- [ ] 修改前查 §8 陷阱，修改后按 §9 原则自检
- [ ] 完成后同步更新 `main_gui.py:CHANGELOG`、本文件 §10、§11 与 `README.md`
