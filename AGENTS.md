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
> **维护原则**：每次合并 PR / 完成功能后，请同步更新 `main_gui.py:CHANGELOG`。如新增协议或解析器，必须更新 §2、§3、§5、§7。

---

## 1. 项目概览

多种电力通信协议的图形化解析工具。单代码库，纯 Python 3.8+，无构建系统，无正式测试框架。当前版本见 `main_gui.py:APP_VERSION`（现 `1.23.16`）。

**支持的协议（共 12 种，对应 GUI 协议下拉框 `current_protocol` 索引）：**

| 索引 | 协议名（GUI显示） | 标准号 | 字节序 | 校验算法 |
| ------ | ------------------ | -------- | -------- | ---------- |
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

> 协议覆盖差异：**HDC 1.0（索引 11）在 PySide6 主程序与 Reflex Web 版均支持**（2026-09-15 核实）。Web 版无实时监控器/档案/拓扑；组帧与预设标签页在 Web 存在但协议 9/10/11 均不支持（与桌面一致），协议11 另有「无实时监控器/组帧/预设」的说明见 §8 陷阱 27。**「频谱图」标签页两端都有**（与协议无关，常驻）：桌面 `spectrum_widget.py`（QPainter 自绘），Web `reflex_web/reflex_web/spectrum_web.py`（SVG）——两侧共用同一份纯逻辑层。**Web 另有主题系统**（浅色/深色/跟随系统 + 6 个预设 + 5 个强调色，`reflex_web/reflex_web/theme_web.py`，token 化 CSS）；桌面为 7 套 QSS 主题（`theme_settings.py`，含毛玻璃/云母，Web 无对应）。NiceGUI/TUI 版本已于 2026-08-17 移除。

> **Web 路由（1.23.14 起，改链接前必读）**：`/` = **产品首页**（落地页，介绍桌面客户端：Hero/功能卡/12 协议表/命令行与系统集成/下载区/页脚，实现在 `reflex_web/reflex_web/landing_web.py`）；`/app` = **在线工具**（原主页的 9 个标签页，函数名 `index()` 已更名 `tool_page()`）；`/share`、`/feedback`、`/feedback-admin` 不变。首页数据全部读 `reflex_web/downloads/`（`version.json` 版本、`*.exe` 体积、`client_screenshot.png` 截图，缺图降级占位卡）。**新增/修改站内链接时必须按语义选目标**（回介绍页 `/`、回工具 `/app`），`landing_web.INTERNAL_LINKS` 是落地页侧的唯一来源，`test/test_web_landing.py` 有死链白名单守卫。

修改协议相关文档/代码时注意区分。

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
- Reflex Web 在线/离线依赖以 `reflex_web/requirements.in` + `reflex_web/requirements.lock` 为准，至少包含 `reflex`、`uvicorn`、`crcmod`、`websockets`、`sqlmodel`（问题反馈存储，**1.19.0 新增**；Reflex 0.9.8 的 rx.Model 需要数据库依赖，默认不随 reflex 安装）
- GUI 反馈对话框依赖 PySide6 自带 QtNetwork（QNetworkAccessManager 异步 multipart 提交），**零新增 pip 依赖**（1.20.0 起）；GUI 侧反馈服务器地址配置在 `config.json` 的 `feedback.server_url`

**运行环境注意：**

- Windows 优先；中文路径需保证 UTF-8 / GBK 编码兼容
- 当前主程序保留 `南网协议解析工具.spec`（单文件 EXE），打包 `custom_di.json`、`dlt645_di.json`、`gdw_custom_afn.json`、`icons/` 与 `enhanced_export.py` 等资源；新增需打包的数据文件时必须检查该 spec
- `reflex_web/reflex_web_exe.spec` 负责 Reflex Web 版打包；开发模式先执行 `cd reflex_web && reflex export --frontend-only --env prod --no-zip`
- Lua 脚本引擎依赖 `lupa`，打包时需作为 hidden import 或确保运行环境已安装
- 当前主程序 spec 未显式声明 `scapy`；如需把 TCP 监控打包进 exe，需补充 `scapy` 依赖并确保目标机器安装 npcap
- `docs/Lua脚本使用说明.md` 是 Lua 功能的用户文档
- Inno Setup 安装脚本 `南网解析工具.iss` / `2222.iss` 的 `MyAppVersion` 用 `python release_check.py --sync-iss` 与 `APP_VERSION` 对齐（当前 1.23.16），发版前务必再跑一次 `python release_check.py`

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

- 增量模式逻辑：先移走 `out_dir/python/`，重建其余目录，再移回——保留解释器与依赖，仅刷新源码/前端。**运行数据不在部署目录内**（见下），故重建无需保留任何数据目录。
- `--skip-deps` 的前提是目标部署目录 `dist/reflex_web_embedded/python/` 已存在且完整（来自上次完整构建）。
- 依赖锁文件 `requirements.lock` 存在且不旧于 `requirements.in` 时，uv 编译自动跳过（依赖未变则复用）。
- 若不慎删了 `dist/reflex_web_embedded/python/`，需回到完整模式重建一次。

**Web 运行数据目录（1.23.14 起，改部署/存储前必读）：**

运行时会写盘的东西（`data/feedback.db`、`data/frameshare.db`、`data/uploads/feedback/`、`downloads/`、`admin_config.json`）**不在部署目录内**，默认落在**部署目录的上一级** `nw_web_data/`，由启动脚本注入环境变量 `NW_WEB_DATA_DIR` 指定（已设则不覆盖）；路径解析的唯一来源是 `reflex_web/reflex_web/app_data.py`（解析顺序：`NW_WEB_DATA_DIR` → 冻结态 exe 同级 `nw_web_data/` → 回落代码目录 = 开发态现状）。

- 两个构建脚本的忽略规则（`reflex_web/deploy_common.py::ignored_web_entries`）**必须**排除 `data/`、`admin_config.json`，以及 `downloads/` 里的**运行时产物**（`*.exe`、`version.json`、`archive/`）；`downloads/` 下的**随包静态资源**（`client_screenshot.png` / `client_readme.md` / `README.md`）反而必须保留——`downloads/` 用**白名单**（`deploy_common.DOWNLOADS_ASSETS`，取自 `app_data.PACKAGED_DOWNLOAD_ASSETS`），黑名单会漏掉 `build/`、`dist/` 这类开发机产物（实测曾漏约 25MB）。
- 升级 = 替换部署目录，数据在目录外不受影响；产物内附 `迁移数据.cmd/sh` 用于把旧版（数据在代码目录内）的数据搬到 `nw_web_data/`。
- 详见 `reflex_web/离线部署.md` 与 `AGENTS.md §8` 陷阱 38。

**端口固化（局域网部署常用）：** 两个构建脚本都支持 `--port N`（默认 8080），会把端口写进三份启动脚本与 `部署说明.txt`（命令行仍可 `start_web.cmd --port 9000` 覆盖）：

```bash
python reflex_web/build_embedded_deploy.py --skip-deps --port 8091   # 内嵌 Python 包
python reflex_web/build_offline_deploy.py --port 8091                # UV 包
```

> 目标服务器只对外开放某个端口（如 8091）时**必须**用它，否则双击启动会跑默认 8080。
> Windows 服务器从零到上线（防火墙、开机自启、备份、升级、排错）见 **`docs/Web版局域网部署教程.md`**。

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
main_gui.py                     # GUI主程序 (PySide6)，应用入口，11000+ 行，MainWindow 类
│                                #  - APP_VERSION、CHANGELOG（手写列表；原 _get_git_changelog() 已于 2026-09-15
│                                #    死代码清理中移除，改动前已从 About 对话框断开）
│                                #  - current_protocol 硬编码索引(0~10)，见 §6
│                                #  - ConfigDialog：配置文件路径管理（自定义 JSON 路径）
│
├── protocol_registry.py      # 协议能力注册表（1.23.1）：下拉名/别名/Tab/校验/提取/包装
├── parser_registry.py        # Parser 懒加载（按名缓存实例）
├── batch_parse_worker.py     # 批量解析后台工作线程（200 帧/片 · 进度/取消/背压回执 · 自建 parser 实例
│                             #   （不用共享单例）；`parse_one_frame` 是「单帧解析」的唯一实现，
│                             #   worker 与详情按需重解析共用；1.23.15 起）
├── custom_di_store.py        # 南网自定义DI存储单源（纯逻辑无Qt：custom_di.json 读写/校验/upsert/批量删；main_gui·lookup_pages·protocol_parser 共用）
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
│   ├── dlt645_data_codec.py        # DLT645 数据域编解码（decode_*/split_* 与 encode_*/pack_* 成对互逆）
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
│   ├── gdw_eb_di_fields.py         # EB 数据标识字段 schema（字段格式/编码实现，供 698 APDU EBE0 等解析复用）
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
│   ├── dlt645_frame_gen.py         # DLT645-2007 帧生成 (DLT645FrameGenerator) — 全仓库唯一 645 封装实现
│   ├── dlt645_frame_schema.py      # DLT645 组帧命令 schema + data_type 掩码→字段推导
│   ├── frame_generator_schema.py   # 南网帧生成 UI schema (~165KB)
│   └── gdw_frame_generator_schema.py # 国网帧生成 UI schema
│
├── GUI 组件（独立文件，main_gui.py 导入组合）
│   ├── frame_gen_widget.py         # 帧生成标签页 (FrameGenWidget) - 支持 south/gdw/dlt698 三种模式
│   ├── preset_buttons.py           # 预设命令按钮 (PresetButtonWidget / PresetButtonManager)
│   ├── test_plan_widget.py         # 测试计划 (TestPlanWidget) - CRUD/顺序发送/超时/结果
│   ├── serial_worker.py            # 串口通信线程 (SerialWorker)
│   ├── gui_utils.py                # 中文右键菜单等工具
│   ├── lookup_pages.py             # 简化版查询页（当前无调用方；create_di_lookup_page 的自定义DI增删与 main_gui 共用 custom_di_store）
│   ├── app_icons.py                # 图标加载（icons/lucide/*.svg；按钮/窗口图标）
│   ├── thread_registry.py          # QThread 登记表（新增 QThread 必须 track；_shutdown_threads 兜底回收依赖）
│   ├── auto_updater.py             # 自动升级：版本比对/下载/update.bat 替换编排（纯逻辑无Qt；配置在 config.json update 段）
│   ├── llm_preprocess.py           # LLM 日志预处理纯逻辑（LLMWorker 线程，thread_registry 登记）
│   ├── llm_preprocess_widget.py    # LLM 日志预处理面板（挂在批量解析输入区，默认折叠）
│   ├── llm_api_manager.py          # LLM API Key 管理对话框（llm_preprocess 的 API 配置）
│   ├── enhanced_batch_export.py    # 批量解析增强导出（与 enhanced_export 配合的批量侧实现）
│   ├── archive_widget.py           # 档案管理 (ArchiveWidget) - 仅南网(0)/国网(6)
│   ├── topology_widget.py          # 拓扑信息 (TopologyWidget) - 仅南网(0)/国网(6)
│   ├── diff_widget.py              # 报文对比标签页 (DiffWidget) - 双报文输入，字节/字段级对比
│   ├── sequence_diagram_widget.py   # 通信时序图标签页 (SequenceDiagramWidget) - 仅协议9，批量结果→CCO⇄STA序列图，
│   │                                 #   前半纯逻辑层(SequenceModel/build_sequence_model_csg，无Qt可测)，后半QGraphicsView自绘；
│   │                                 #   与批量摘要表双向联动（_seq_sync_guard 防环），导出PNG（1.23.0 起）
│   ├── batch_source_view.py        # 原始日志快照查看器 (SourceViewerDialog) - 批量摘要表右键「转到原始报文位置」，
│   │                                 #   拖入/打开/粘贴建立不可变快照（回填式预处理只改输入框）；前半纯逻辑
│   │                                 #   (hex_stream/find_frame_in_stream，无Qt可测)，后半只读行号编辑器+Ctrl+F搜索条（1.23.0 起）
│   ├── message_tool_widget.py       # 报文工具标签页 (MessageToolWidget) - ASCII/HEX转换/CRC/校验
│   ├── spectrum_widget.py           # 频谱图标签页 (SpectrumWidget/SpectrumCanvas) - 频谱仪参数 + trace 数值 → 仪器式网格频谱图；光标读数/MARK标记/两点Δ测量/峰值搜索 + 导出PNG（常驻，与协议无关；1.23.9 起）
│   ├── feedback_dialog.py           # 问题反馈对话框 (FeedbackDialog) - 帮助菜单入口，提交到 Web 服务端共享 feedback.db（1.20.0 起）
│   ├── share_dialog.py              # 报文分享对话框 (ShareDialog) - 单帧解析「分享此帧」，JSON POST /api/frameshare（1.21.0 起）
│   ├── enhanced_export.py           # 增强导出功能 (EnhancedBatchResultExporter) - Excel/CSV/TXT/JSON
│   ├── theme_settings.py            # 主题与字体设置 (ThemeManager + ThemeSettingsDialog) - 7套主题(含Win11云母Mica)/QSS/字体持久化
│   ├── meter_sim_widget.py         # 虚拟表 tab (VirtualMeterWidget) - 698.45 从站模拟器（离线/串口从站，仅协议8，1.16.0 起）
│   ├── meter_sim/                  # 虚拟表核心逻辑包（纯逻辑无 Qt，1.16.0 起）
│   │   ├── archive.py              #   档案 meter_sim_data.json（194 OI，app_paths 持久化）
│   │   ├── link_layer.py           #   68...16 帧提取（粘包/分片/FE前缀）+ 帧头解析
│   │   ├── response_builder.py     #   Get-Response Normal/NormalList/Record、链接、安全MAC封装；复用 DLT69845FrameGenerator
│   │   ├── dynamic_data.py         #   时间/地址/电能量递增/冻结时标/漏点
│   │   └── engine.py               #   MeterSimEngine.handle_frame(frame) -> 0..n 响应帧
│   ├── dlt645_meter_sim_widget.py  # 645虚拟表 tab (Dlt645VirtualMeterWidget) - 645 从站模拟 + LME 主站下发（仅协议6，1.23.5 起）
│   ├── dlt645_sim/                 # 645虚拟表核心逻辑包（纯逻辑无 Qt）
│   │   ├── archive.py              #   档案 DI→可读值（dlt645_sim_data.json 持久化）
│   │   ├── dynamic_data.py         #   动态数据：RandomEventWord 事件状态字随机源（04001501，1.23.8 起）
│   │   ├── engine.py               #   从站引擎 handle_frame：11H 读档案 / 13H 读通信地址 / 15H 写通信地址 / 08H 校时 / 其余 DnH 异常
│   │   └── lme_query.py            #   LME 自定义下发组帧 4.2/4.6/4.7（模块版本查询，1.23.7 起；复用 DLT645FrameGenerator + DLT645Parser）
│   ├── monitor_widget.py            # 实时监控器 (RealtimeMonitorWidget) - 串口原始字节流自动组帧/CSV记录
│   ├── monitor/tcp_monitor.py       # TCP流量监控 (TCPMonitorWidget) - scapy抓包/流重组/自动解析
│   ├── system_integration/          # 系统集成包（Windows）
│   │   ├── sys_tray.py              #   系统托盘（关闭最小化/显示隐藏/自启/退出）
│   │   ├── global_hotkey.py         #   全局热键（默认 Ctrl+Alt+X，唤出快捷解析小窗）
│   │   ├── single_instance.py       #   单实例（QLocalServer，转发命令行参数）
│   │   ├── registry_menu.py         #   注册表：开机自启 + .log/.txt/.hex/.bin 右键菜单
│   │   ├── clipboard_monitor.py     #   剪贴板报文自动检测（严格 hex 校验 + 协议特征识别）
│   │   ├── parse_prompt_dialog.py   #   剪贴板报文解析提示框（置顶、协议选择、复用实例）
│   │   ├── npp_integration.py       #   Notepad++ 集成（右键菜单 + 运行命令，触发 --clipboard）
│   │   ├── quick_parse_panel.py     #   uTools 风格快捷解析小窗（热键唤出/实时解析卡片，1.17.0 起）
│   │   └── system_settings.py       #   系统集成设置面板与 config.json "system" 段
│   └── reflex_web/                 # Reflex Web 版（实验性，run_app.py + reflex_web_exe.spec）
│       ├── reflex_web/reflex_web.py  #   Reflex 应用：4 条路由 = `/` 落地页(landing_page) / `/app` 工具页(tool_page,
│       │                             #   原 index，9 标签页) / `/feedback` / `/share`；含反馈列表 Tab，1.19.0 起
│       ├── reflex_web/landing_web.py #   产品首页内容与纯展示组件（**不 import reflex_web**，运行时值全参数注入；
│       │                             #   12 协议表/12 功能卡/CLI/系统集成/统计条 + LANDING_CSS，1.23.14 起）
│       ├── reflex_web/theme_web.py   #   主题系统：6 预设 + 5 强调色 + 深浅 token + theme_controls_compact 复用（1.23.12 起）
│       ├── reflex_web/spectrum_web.py #  频谱图 SVG 换算（复用桌面 spectrum_widget 纯逻辑层，1.23.12 起）
│       ├── reflex_web/web_utils.py   #   解析链纯函数（清洗/提帧/摘要/分页/命令行预处理拆分）
│       ├── reflex_web/lookup_utils.py #  查询页数据源
│       ├── reflex_web/feedback_model.py #   反馈存储层：FeedbackItem(rx.Model/SQLite，source/sys_info 列) + submit_from_api/parse_multipart/频率限制（GUI API 复用，1.20.0 起）
│       ├── reflex_web/share_model.py    #   报文分享存储层（frameshare.db）：ShareItem + submit_share/normalize_hex/list_page 搜索（Web /share 页与 GUI 共享，1.21.0 起）
│       ├── reflex_web/app_data.py    #   运行时数据路径唯一来源（纯 stdlib）：NW_WEB_DATA_DIR → 冻结态 exe 同级
│       │                             #   nw_web_data/ → 回落代码目录（开发态现状）；含 ensure_dirs/migrate_legacy（1.23.14 起）
│       ├── deploy_common.py         #   两个部署构建脚本共用：忽略规则（排除 data/downloads/admin_config.json）、
│       │                             #   启动脚本注入 NW_WEB_DATA_DIR、迁移数据脚本生成（1.23.14 起）
│       ├── reflex_web/admin_release.py  #   管理员口令（admin_config.json，路径由 app_data 决定）+ 发布管理
│       ├── data/                   #   开发态运行数据（feedback.db/frameshare.db + uploads/feedback/，gitignore）
│       └── downloads/              #   开发态发布产物（首页数据源）：version.json（版本徽章/下载地址）、client_screenshot.png
│                                   #   （Hero 截图，缺图降级占位卡）、南网协议解析工具*.exe（体积读 stat）、client_readme.md
│                                   #   ※ 部署态：data/、admin_config.json 与 downloads/ 里的运行时产物位于部署目录**之外**的
│                                   #     <部署上级>/nw_web_data/；downloads/ 里的随包资产仍随代码走。见 §2 与 §8 陷阱 38
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
├── proc_stats.py                   # 本进程资源占用采样（CPU%/内存，纯标准库零依赖，1.18.0 起）
│                                   #   Windows: ctypes GetProcessTimes/GetProcessMemoryInfo；Linux: /proc/self；其他降级 --
├── app_paths.py                    # 所有可写数据文件路径的唯一入口（1.14.7 起）
│                                   #   app_data_dir()/data_path(name)/ensure_data_file(name)
│                                   #   frozen(单文件exe) → exe 所在目录；dev → 项目根
│                                   #   纯 stdlib 无 Qt；函数内惰性读 sys.frozen/_MEIPASS/executable
│
└── 数据文件（运行时读写，需随打包/版本管理；一律经 app_paths.data_path 定位，frozen 下落 exe 目录）
    ├── custom_di.json              # 南网自定义DI（GUI 增删；打包内置，exe 目录缺失时从 _MEIPASS 复制种子）
    ├── gdw_custom_afn.json         # 国网自定义AFN+Fn（GUI 增删；打包内置，exe 目录缺失时从 _MEIPASS 复制种子）
    ├── meter_sim_data.json         # 虚拟表档案（194 个 OI→A-XDR 数据；scripts/gen_meter_sim_data.py 从开源 config.ini 生成，1.16.0 起）
    ├── meter_sim_settings.json     # 虚拟表模拟设置（多表数/名单/递增/漏点/MAC 开关，运行时生成）
    ├── dlt645_di.json              # DLT645 DI 映射（generate_dlt645_di.py 生成，勿手改）
    ├── dlt645_di_custom.json       # DLT645 自定义 DI（GUI 增删）
    ├── NW_command.json             # 南网预设命令
    ├── GW_command.json             # 国网预设命令
    ├── command.json                # PLC RF 命令字
    ├── config.json                 # 串口配置 + 顶层 window 段（窗口几何/分栏/列宽，见 §8 陷阱 42）
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
| ------ | ------ | ------ |
| `custom_di.json` | 南网自定义 DI | GUI 运行时增删 |
| `gdw_custom_afn.json` | 国网自定义 AFN+Fn | GUI 运行时增删 |
| `dlt645_di.json` | DLT645 标准 DI 映射 | `generate_dlt645_di.py` 生成，**勿手改** |
| `DLT645_command.json` | 协议6 预设命令 | GUI 运行时增删（种子 5 条） |
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
  - `协议文档/0.南网协议/13 计量自动化终端本地通信模块接口协议.md` — **本地通信模块接口协议（试行）**，108 个数据标识（E8 86 + EA 22），模块特征信息/即插即用/黑名单/相位等新增 DI 的字段定义以此为准（1.14.9 起）；源文件为同目录 `.doc`/`.docx`（OLE2 格式需用 Word COM 转 docx 后再 markitdown）

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

### 5.4 DLT645-2007（索引 6）

- **解析器**：`dlt645_parser.py` (DLT645Parser)
- **查询**：`dlt645_di_lookup.py` + `dlt645_di.json`
- **组帧**：`dlt645_frame_gen.py` + `dlt645_frame_schema.py`（GUI/Web 协议6；DI 掩码驱动字段模板）
- **虚拟表（从站模拟 + LME 主站下发）**：`dlt645_meter_sim_widget.py`（tab「645虚拟表」，仅协议6）+ `dlt645_sim/` 包
  - **LME 自定义接口**（《LME产品相关信息生产运维接口手册_V2.4》）：解析侧 `lme_info_entry_parser.py`（4.2 单模 STA 详细版本 DI=`04FFAAF9`；4.6/4.7 双模 STA 内部信息条目 DI=`FF00DD01`，TLV 条目字典 `LME_INFO_ENTRIES`），`dlt645_parser.py` 按 DI 自动分派深度展开；下发侧 `dlt645_sim/lme_query.py`（虚拟表作主站向模块索取版本信息：4.2 无数据单元 / 4.6 查询 11H / 4.7 设置 14H，TLV 头编码与长度取 `LME_INFO_ENTRIES` 定义，长度上限 31 字节）
  - **手册 §5.1.1 逐字节 golden**：4.2 请求 `68 AA AA AA AA AA AA 68 11 04 2C DD 32 37 53 16`；应答 135 字节（L=0x7B、CS=0x56），字段 LH/60/V0102/2020-11-10/v0244/APS 0135/N0230/P2008/V4028
  - **串口回包判据**：控制码在 idx8，`ctrl & 0x80`（D7=DIR）为 1 → 从站/模块发出的回包，虚拟表按主站解析展示（`Dlt645SerialSlaveThread.slave_frame`）；为 0 才走从站引擎应答
  - **事件状态字（DI `04001501` 主动上报状态字，`BS96`=12 字节）**：载波模块反复轮询的「电能表事件状态字」（`协议文档/7.国网本地接口协议/附件1.md:214`）。档案默认 12 字节全 0（无事件、不变化）；「模拟设置 · 随机产生事件」勾选后由 `dlt645_sim/dynamic_data.py::RandomEventWord` 每次给新的随机 12 字节（保证与上次不同），引擎经 `event_word_source` 注入取用，勾选状态存 `dlt645_sim_data.json` 的 `random_event`
  - **DI 类型/长度权威源 = `dlt645_frame_schema.get_di_info`**（读 `dlt645_di.json`）：引擎 `_di_info_for` 用它取 `data_type`+`length` 并以 `nbytes=length` 调 `encode_value`；`dlt645_di_lookup` 的方法名是 **`get_di_info`**（不是 `get_info`）——曾因探测错名让 `BS96` 按 4 字节回（04001501 应答 L=08）
- **校验器**：`validator/dlt645_validator.py`
- **参考文档**：
  - `DLT645-2007.md` — 主协议（Markdown）
  - `DLT645-2007 多功能电表通信协议.pdf` — 原始 PDF
  - `国网计量中心电能表全性能试验检测公告-第4号补遗-事件记录采集-远程费控功能和负荷曲线抄读功能.pdf` — 补遗（PDF，需用 pdf skill 检索）

### 5.5 国网协议（索引 7）

- **解析器**：`gdw10376_parser.py` (GDW10376Parser) + `gdw10376_tool.py`
- **组帧**：`gdw_send_frame_lib.py` + `gdw_frame_generator_schema.py`
- **查询**：`gdw_afn_lookup.py`
- **校验器**：`validator/gdw_validator.py`
- **参考文档**：
  - `集中器本地通信模块接口-2024.md`（Q/GDW 10376.2—2024，**严格依据此文档解析**）
  - `协议文档/7.国网本地接口协议/附件3：1376.2集中器本地通信模块接口协议【福建增补】V1.4-20240729`（**福建增补规约，AFN=50H~56H，1.14.0 起支持**）
  - `协议文档/7.国网本地接口协议/附件1：本地通信模块扩展协议 V3.42-20260514`（**EB 数据标识扩展，1.14.0 起支持**，V3.31 前置版本）
  - `协议文档/7.国网本地接口协议/附件4：集中器和CCO通信接口补充要求-20220416`（以太网/UDP 通信链路要求）

### 5.6 DL/T 698.45-2017（索引 8，**1.7.0 新增**）

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
- **解析重点**：支持多物理块重组、聚合帧级联块应用层解析、NET 帧可变区域解析；批量解析支持监控日志前缀剥离与业务摘要；ED..EE 包装的数据域若为《测试装置通信控制协议V1.1》工装板/功能驱动板控制帧，也由协议9解析器识别展开
- **参考文档**（位于 `南网新一代20260226校对/南网新一代20260226校对/` 子目录，每部分同时有 .docx 和 .md）：
  - `1-通感一体化低压电力线宽带载波通信规约 第1部分 总则（文本校对）.md` — 总则
  - `2-...第2部分 技术要求（文本校对）_力合微_20260304.md` — 技术要求
  - `3-...第3部分 物理层通信协议（文本校对）.md` — 物理层
  - `4-...第4部分 数据链路层通信协议 （文本校对）.md` — **数据链路层（MAC/MSDU 帧格式）**
  - `5-...第5部分 应用层通信协议（文本校对）.md` — **应用层（业务报文结构）**
  - `6-...第6部分：检验规范（文本校对）.md` — 检验规范
  - 源 docx 可用 `convert_docx_to_md.py` 重新转换
  - `《南方电网计量自动化系统双模通信技术规范 第2部分：无线通信接入协议》（报批稿）.md` — **无线信道(HRF)协议定义权威参考**（同目录 .pdf 为原始文件，192页，Q/CSG 报批稿）。**引用优先级：新一代协议本身有定义 → 以新一代为准；新一代未定义的无线专有内容（RF物理层前导/SFD、无线信道编号与option、无线路由参数条目等）→ 本文档**。已核对布局一致：精简信标载荷（无线表154≡新一代表73）、0x0E 精简条目（表155≡表74）、信标载荷固定区（表134≈表51）；差异点——信标条目头 0x0F 起无线版为保留，新一代扩展了 信标机制切换(0x0F)/代理角色(0x10)
  - `南网新一代载波通信互联互通测试装置 通信控制协议V1.1.md` — **测试装置工装板/功能驱动板控制协议参考**（ED..EE 数据域可能携带）。CCO/STA 仓工装板：`FE...05 + 地址 + 命令码 + 6字节数据 + 校验和`；功能驱动板：`FE FE FE 05 + 地址 + 指令 + 6字节数据 + 校验和 + AA 0D 0A`

### 5.8 国网新一代双模通信互联互通（索引 10）

- **解析器**：
  - `gw_new_gen_parser.py` (GWNewGenParser) — 国网新一代双模通信互联互通协议解析，支持 HDC 1.0 / HDC 2.0 版本判定
  - `gw_new_gen_mme_parser.py` (MMETYPE_NAMES +_MME_CONTENT_PARSERS) — MME 管理消息深度解析（关联/代理变更/发现列表/网络冲突/诊断等）
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
>
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

**1.23.1 起：能力元数据集中在 `protocol_registry.py`。**

- `parser_registry.py`：按名字懒加载 parser 类/实例
- `protocol_registry.py`：按协议索引声明展示名、别名、占位符、查询页、组帧/预设模式、Tab 能力（档案/拓扑/虚拟表/监控/时序图）、解析级别族、批量提取策略、校验器类路径、GUI 解析器包装

`main_gui` 已改为查表分派的位置：

| 位置 | 行为 |
| ------ | ------ |
| `protocol_combo` 填充 | `combo_labels()` |
| `_on_protocol_changed` | 占位符 / Tab 可见性 / 组帧与预设 mode / 监控 / 时序图 |
| `_update_protocol_lookup_tab` | `lookup_builder_method(spec.lookup_kind)` |
| `_get_current_parser` | `build_gui_parser(...)` |
| `_run_validation` / 快捷小窗校验 | `build_validator_map()` |
| `_protocol_name_to_index` | `name_to_index()` |
| `_extract_frames_for_protocol` | `spec.extract_strategy` |

**新增协议 checklist（1.23.1 起优先改注册表）：**

1. 在 `protocol_registry._PROTOS` 末尾追加一条 `ProtocolSpec`（索引 = 下一项）
2. 在 `parser_registry._PARSER_SPECS` 注册 parser 键
3. 新建 `xxx_parser.py` + `validator/xxx_validator.py`
4. 如需 Web 支持，同步 `reflex_web/`
5. 新建 `test/test_xxx.py`；必要时扩 `test_protocol_registry.py`
6. 同步本文件 §1/§3/§5、README 与 CHANGELOG；打包时检查 spec `datas`/hiddenimports

仍可能需要手写的点（未完全表驱动）：

- 批量前缀剥离 / 业务摘要（协议 9/10/11 共用逻辑，新协议若结构不同需在 `parse_batch` 增加策略）
- 解析级别下拉的控件集合与默认值（`_csg_parse_level` / `_gw_parse_level` 等）
- 查询页 builder 的具体 UI（`_create_*_lookup_content`）
- 单帧解析里特殊预处理（ED 包装、PB 填充等）

**Tab 可见性规则（与注册表字段一一对应）：**

- 虚拟表：`has_virtual_meter`，仅 698.45(8)；串口监听线程独立，关闭须 `shutdown()`
- 645虚拟表：`has_dlt645_sim`，仅 DLT645(6)；同时含从站模拟与 LME 主站下发，串口线程独立，关闭须 `shutdown()`
- 组帧 / 预设：`frame_gen_mode` / `preset_mode`，南网(0)/DLT645(6)/国网(7)/698.45(8)
- 档案 / 拓扑：`has_archive` / `has_topology`，仅南网(0)/国网(7)
- 新一代解析级别：`parse_level_family == "csg"`（索引 9）
- 国网新一代 / HDC 1.0 解析级别+通道：`parse_level_family in ("gw","hdc10")`
- 实时监控器：`has_monitor` + `monitor_wrapper`（9=plc2/ED..EE，10=hplc/96..16；**11 无**）
- 通信时序图：`has_sequence_diagram`（9/10/11）
- TCP 监控 / 报文对比 / 报文工具 / 测试方案：始终可见

---

## 7. 测试

> **规则（强制）**：所有测试文件一律放入 `test/` 目录，**项目根目录禁止新增 `test_*.py` 测试文件**（`.gitignore` 已忽略根目录 `/test_*.py`）。新增测试在 `test/` 下建 `test_xxx.py`，文件头必须包含 `import _path_setup  # noqa: E402`（位于 docstring 之后、业务 import 之前），它会自动把项目根加入 `sys.path` 并把工作目录切到项目根，使 `from xxx_parser import ...` 与 JSON 数据文件读取在任意启动目录下都成立。
>
> **该 import 的 noqa 必须同时抑制 `F401`，即写 `import _path_setup  # noqa: E402,F401`**：`# noqa: E402` 只压「导入不在文件顶部」，ruff 仍认它是「未使用导入（``F401``）」→ 任何 `ruff check --fix` / 编辑器自动修复都会**把这一行删掉**，该测试随即 `ModuleNotFoundError: No module named 'main_gui'`（本项目实测被此坑一次：`test_ed_fallback_fix.py` 在 `release_check.py:CORE_TESTS` 内，被批量修复删掉后 `release_check.py` 直接多出一项 FAIL）。查漏：`grep -rn "import _path_setup  # noqa: E402$" test/`。

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
python test/test_nw_lcmi.py         # 南网本地通信模块接口协议 LCMI（1.14.9 起：15 新 DI 解析 + 组帧回读 + 双格式兼容）
python test/test_nanwang_custom_di.py # 南网自定义DI增删（92项：store纯逻辑/沙箱零污染/MainWindow offscreen 增删·覆盖·内置拒绝·批量·重启保持/简化页/无死按钮反例，1.23.11 起）
python test/test_dl_t698_45.py      # 698.45 协议
python test/test_dl_t698_45_data_decode.py  # 698.45 APDU 数据内容业务解码（电能量/需量/分相/单值）
python test/test_dlt645_sim.py       # DLT645 虚拟表从站引擎（11H 读档案 / 13H 读地址 / 15H 写地址 / 08H 校时 / 异常应答）
python test/test_dlt645_sim_lme_query.py  # 645虚拟表 LME 模块版本下发（95 项：4.2 手册 golden 逐字节 / 4.6 条目查询 / 4.7 TLV 与 5bit 上限 / 手册回包字段回归 / 截断容错 / offscreen GUI / COM1↔COM2 真实回环，1.23.7 起）
python test/test_dlt645_sim_event_word.py # 645虚拟表 事件状态字（66 项：L=0x10 类型修复 / 默认 12 字节全 0 不变化 / 随机产生事件相邻不同 / 产生器碰撞重抽 / 异常回落 / 持久化 / COM1↔COM2 回环，1.23.8 起）
python test/test_dlt645_lme.py       # LME 自定义接口解析（4.2 单模STA / 4.6·4.7 双模STA 条目 TLV）
python test/test_dlt645_frame_gen.py # DLT645 组帧（掩码推导 / 组帧→解析闭环 / LME 查询模板）
python test/test_dlt645_frame_gen_gui.py # 645 组帧标签页 offscreen 冒烟
python test/test_meter_sim.py       # 698.45 虚拟表从站模拟器（62 项：自组帧自解析闭环/NormalList/Record/安全MAC/通配多表/名单/递增/漏点/粘包分片，1.16.0 起）
python test/test_quick_parse_panel.py # uTools 风格快捷解析小窗（29 项：空态/真实帧/自动识别/错误态/徽章/显隐/手动切协议/MainWindow 集成，1.17.0 起）
python test/test_app_exit.py         # 关闭/托盘退出进程不残留 + 线程回收（offscreen：X→托盘退出事件循环结束/直接关闭/虚拟表线程登记，1.17.2 起）
python test/test_oad_enrichment.py  # 698.45 OAD 增强
python test/test_csg_new_gen.py     # 新一代载波协议
python test/test_csg_hrf_mac.py     # 新一代载波无线单跳MAC帧（表12/表139）
python test/test_csg_batch_prefix.py # 新一代载波监控日志前缀剥离
python test/test_csg_batch_parse_level.py # 新一代载波解析级别/完整 MPDU
python test/test_csg_summary.py     # 新一代载波批量摘要
python test/test_batch_snapshot_locate.py # 批量摘要右键定位原始日志快照（纯逻辑+快照链+offscreen，1.23.0 起）
python test/test_gui_batch_perf.py   # 批量解析后台化（99 项：worker 分片/取消/异常隔离/失败判定/单巾解析单一来源/跨帧状态锁存/详情 LRU+对拍/导出「包含表格数据」列/过滤 oracle 对拍 + 耗时 + 去抖 + UI 心跳，1.23.15 起）
python test/test_hex_clean_script.py   # scripts/hex_clean 回退清洗 + 脚本列表判重（1.23.0 起）
python test/test_pp_cli.py             # 预处理命令链拆分（半角基准 / 全角空格·全角引号·NBSP·零宽归一化 / 参数内容保护 / 错误提示码位 / 端到端 / offscreen GUI 回调，1.23.13 起）
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
python test/test_web_parse_fixes.py     # Reflex Web 版解析 P0 修复（75 项：严格 hex 清洗/失败判定（含中途 ❌）/剔除/级别参数下发/ED gx 双布局/pb_only frame_type/查询页 AFN·协议10·698 属性/校验器工厂/CRC-24 同口径 + reflex State 真实实例 + parse_batch 批量端到端，1.23.12 起）
python test/test_web_batch_paging.py    # Reflex Web 版批量摘要分页与搜索（57 项：paginate/filter 纯函数 + 250 帧端到端翻页/跨页选中/每页条数切换 + 249 行端到端搜索（HEX/类型/#序号）与状态筛选/过滤后翻页/选中清理，1.23.12 起）
python test/test_web_spectrum.py        # Reflex Web 版频谱图（64 项：复用桌面纯逻辑层守卫 + SVG 几何 + SpectrumState 端到端（联动/标记/峰值/IBW/错误路径）+ 组件树，1.23.12 起）
python test/test_web_theme.py           # Reflex Web 版主题系统（89 项：预设/维度清单 + token 契约与浅色等价 + CSS 结构 + 标记配色单一来源 + ThemeState 端到端 + 无裸 hex 守卫，1.23.12 起）
python test/test_web_landing.py         # Reflex Web 版产品首页（100 项：内容不变式 + 与 protocol_registry 逐行对拍防漂移 + CLI 参数对 main_gui 源码 + 组件树/testid 契约 + 缺图降级互斥 + 死链白名单 + 路由与页面搬迁 /→首页 /app→工具，1.23.14 起）
python test/test_web_data_paths.py      # Web 运行时数据外置（数据根解析矩阵 env/冻结态/默认 + 消费方单一来源 + 迁移幂等不覆盖 + 构建产物排除 data/downloads/admin_config.json 端到端 + 启动脚本注入 NW_WEB_DATA_DIR，1.23.14 起）
python test/test_web_feedback.py        # Web 版问题反馈（存储层/截图校验/防穿越/run_app 语法，1.19.0 起）
python test/test_feedback_api.py        # 反馈提交 API（submit_from_api/parse_multipart/频率限制/旧库迁移，31 项，1.20.0 起）
python test/test_feedback_dialog.py     # GUI 反馈对话框（URL/config/校验/sys_info/offscreen 冒烟，30 项，1.20.0 起）
python test/test_frame_share.py         # 报文分享（normalize_hex/submit_share/Store 分页搜索/GUI payload+offscreen，57 项，1.21.0 起）
python test/test_spectrum_model.py      # 频谱图纯逻辑（含 trace 日志清洗：分隔符解析/行尾取值/时间戳防护/统计不变式/错误兼容，225 项，1.23.9 起）
python test/test_spectrum_gui.py        # 频谱图 GUI offscreen（含日志块粘贴绘制、清洗提示不丢失、行号报错，135 项，1.23.9 起）

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
13. **Inno Setup 版本号**：1.23.3 起用 `python release_check.py --sync-iss` 与 `APP_VERSION` 对齐；发版前应再跑一次 `python release_check.py`。
14. **国网新一代 HDC 1.0 / 2.0**：`gw_new_gen_parser.py` 依据 FC 字节 12 的高 4 位标准版本号自动选择 MAC 帧头规则；改 MAC 头解析时不要把 HDC 1.0 的保留字段当成 HDC 2.0 字段。
15. **国网新一代信标帧无 PBH（重要）**：`_parse_beacon_frame` 中信标帧（DT=0）FC 后**直接为信标载荷，无物理块头(PBH)**，HDC 1.0 与 HDC 2.0 均如此。依据：表22/表38 字段从字节0即信标类型，无 PBH 位置；BPCS(CRC-32) 校验范围为信标载荷内容，无 PBCS(CRC-24)。文档第906行"以物理块头和物理块体为目标"是 **SOF 帧(图18)** 的 PBCS 描述，不是信标帧。若误把信标载荷首字节当 PBH，会导致信标类型错位 1 字节（如发现信标 0xC8 被误判成中央信标 0x42）。
16. **国网新一代 MME**：管理消息由 `gw_new_gen_mme_parser.py` 负责，MMTYPE 为 2 字节小端；0x0008 按发现列表报文处理（文档中该值标为保留，但报文顺序支持该解释），改解析时先查表 42~93 与实测报文。
17. **监控器包装格式**：`monitor_widget.py` 区分 `96..16`（国网新一代/HPLC）与 `ED..EE`（南网新一代/PLC2）；协议 9 / 10 切换时 wrapper 会自动切换，不要用错格式。
18. **TCP 监控可选依赖**：`monitor/tcp_monitor.py` 使用 scapy QThread + signal 回主线程，Windows 需 npcap；scapy 缺失时不能调用 `get_if_list`，UI 已做降级，但新增抓包逻辑要保持 try/except。
19. **输入即 PB 契约**：`mac_only` / `pb_only` / `app` 等仅输入解析模式不再剥离 FC，输入内容按界面提示的层级直接解析；不要再次假设输入包含完整 MPDU 而剥离 16 字节。
20. **系统集成仅限 Windows**：`system_integration/registry_menu.py` 与 `global_hotkey.py` 依赖 Windows API 与 HKCU 注册表；热键注册失败时应打印提示而不是阻塞启动。`main()` 先做单实例判断，修改启动流程时不要破坏该顺序。
20b. **退出必须显式 `QApplication.quit()`**（2026-08-28 修复）：Qt 仅在「最后一个可见顶层窗口关闭」时发 `lastWindowClosed` 并结束 `app.exec()`。点 X 最小化到托盘后窗口已 `hide()`，托盘「退出」/自动更新重启（`_schedule_quit`）再调 `self.close()` 时**没有可见窗口关闭**，即使 `closeEvent` 里 `event.accept()`、所有线程都已回收，事件循环仍不退出、进程残留。正确做法：`closeEvent` 真正退出路径（最小化到托盘的 `event.ignore()` 分支之后）在 `event.accept()` 后追加 `QTimer.singleShot(0, QApplication.quit)`（延迟到当前事件处理结束后，不能在 closeEvent 中途直接 quit）。新增 QThread 一律 `thread_registry.track(self, 名称)`，`_shutdown_threads` 的兜底回收依赖该注册表；回归测试 `test/test_app_exit.py`（offscreen）。
21. **剪贴板检测与 Notepad++ 集成**：`clipboard_monitor.py` 监听 `QClipboard.dataChanged`，受 `config.json` 的 `system.clipboard_monitor` 控制；`npp_integration.py` 会修改 `%APPDATA%/Notepad++` 下的 XML 并保留 `.parser_backup`。改动时保持严格 hex 校验、去抖与提示框单实例复用，避免自身复制触发弹窗。
22. **ED..EE 监控帧剥离失败禁止回退**：协议 9 下勾选「ED监控协议」（或弹窗「剥离ED监控头」）时，首字节 0xED 的报文只能是 ED 包装帧（CSG FC 起始字节低 4 位 ∈ {8,9,A,B}，0xED 永不是合法 FC 起始）。`_parse_ed_monitor_header` / `_extract_business_from_ed_frame` 校验失败（帧不完整、缺 EF/EE）时必须明确报错，**绝不能静默把 ED 首字节当 FC 起始符送解析器**。三处路径（`parse_single` / `_parse_and_show_dialog._preprocess` / 批量解析）必须保持一致。
23. **字段声明与实际不一致时的容错显示原则**：当报文长度、字段声明值与实际内容不匹配时（如 DLT645 数据长度字段声明 102 字节但实际只有 15 字节），**解析器不得直接返回空白结果**（会让用户以为按钮失灵）。正确做法：尽力解析所有可解析字段，`valid` 置 `False`，并在解析结果表格中以醒目的 `⚠` 行插入错误提示。校验器对应项必须标记 FAIL。核心原则——用户点了解析按钮就必须看到内容和错误，不能什么都没有。
24. **新一代载波协议(索引9)无线信道单跳MAC帧头仅 4 字节**：版本2（单跳帧协议，表12，仅无线信道）MAC 帧头为 4 字节（帧头类型1b+版本2b+保留5b / MSDU类型8b 表13 / MSDU长度16b），**帧头类型位无意义**，不得按 header_type 推导 12/32 字节帧头长；MSDU 类型在 MAC 头内、载荷无 VLAN+类型前缀，须内联分派（1=应用层 / 2=无线发现列表 表139 TLV / 128=IPV4）。改 `_parse_mac_frame` / `parse_to_table` 步骤3 / `_parse_pb_block` 尾段三处时保持一致（v2 → `mac_hdr_len=4` 且 `msdu_payload=b""` 防重复解析）。版本1 帧头「发送序号」为小端（`(byte1<<4)|byte0高4位`）。
25. **HDC 1.0(索引11)信标条目长度字段**：信标管理信息条目（如时隙分配 0xC0）长度字段为 **2 字节**，条目内容 = `total_len - 3`（头 1B + 长度 2B 开销），不要用 `total_len - 2` 多算 1 字节（详见 `test_hdc10.py::test_entry4_content_length`）。
26. **HDC 1.0(索引11)发现信标省略非中央信标信息**：发现信标（类型 0）省略非中央信标信息字段，可变部分只有 CSMA 时隙信息（4B/条，按相线 A/B/C 展开）；不要按中央信标格式去解析 TEI 条目（`test_hdc10.py`）。
27. **HDC 1.0(索引11)与国网新一代(索引10)并存**：协议 11 是独立解析 HDC 1.0 帧的入口（`hdc10_parser.py`），与协议 10 内部自动判定 HDC 1.0/2.0 的两条路径**不要混用解析器**；协议 11 无实时监控器、无组帧/预设命令、无档案/拓扑（仅单帧/批量/校验/查询/对比）。批量解析时协议 10/11 共用 `_strip_gw_new_gen_prefix` 与 `_get_gw_new_gen_summary`。
28. **HDC 1.0(索引11) MAC 帧 ICV 校验规则**（实测帧验证，2026-08-22）：
    - **ICV = CRC-32(MSDU载荷)**，zlib 标准反射算法，**小端**存放于帧尾 PBCS 前 4 字节
    - **计算范围 = MSDU 载荷本身**（不含 MAC 头、不含 ICV 自身），文档原文"不包括MAC帧头"
    - **MSDU 起点 = PBH + MAC头总长**：MAC地址标志=1 时头长 28B（16B 固定域 + 源/目的MAC各6B），标志=0 时 16B——必须用 `_parse_mac_std_header` 返回的 header_len 定位，禁止硬编码 16
    - MSDU 长度 = 声明值（MAC头 byte8），与 `帧尾-4 - MSDU起点` 应一致；不一致说明对齐错误
    - **PBH 剥离判据**：MAC标准头 b0 bit7 恒为0（源TEI≤0x7FF），b0 bit7=1 必为 PBH——auto/mac_only 自动剥离；PBH 低4位=0 与 MAC版本0 冲突，**不能用 ver 位区分**
    - MME 头为 **4字节**（表58：MMTYPE 2B + 保留 2B），不是3字节；MME 解析器 offset 参数是切片内相对索引，切片后传 0
    - 实机明文模式 ICV 可能填全0（此时校验必然"失败"），应显示"明文填充"而非报错
29. **HDC 1.0(索引11) 真实报文回归测试**：`test/test_hdc10_real.py` 使用 TMI 遍历测试日志提取的 119 个真实 PB 帧（`test/hdc10_real_frames.pkl`）。修改 `hdc10_parser.py`/`hdc10_mme_parser.py` 后必须运行该测试——组帧只能覆盖想象结构，真实日志才能暴露实机与文档差异。原始数据源：`国网新一代协议/HDC-国网双模协议/TMI模式遍历测试_频段1__All.log`（4500+ 条 `Origin sof pb:'<hex>'` 行）。
30. **ED..EE 监控包装格式判别是解析器层单源**（1.23.12 起）：PLC2.0（9B 公共头）与广西台体（gx，8B 公共头）的判别与两套字段偏移都在 `csg_new_gen_parser.detect_ed_wrapper` / `_parse_ed_wrapper`，桌面 `main_gui._detect_ed_wrapper` 仅委托（手动下拉值作 `fallback`）。改 ED 相关逻辑时不要再在调用方写第二份打分或偏移表；摘要侧判定按「字段名含 `监控包装头`」而不是 `PLC2.0`（否则 gx 帧摘要掉到兜底分支）。`parse_to_table(..., ed_wrapper=...)` 可显式覆盖自动识别。
31. **Web 与桌面解析链路的复刻风险**（1.23.12 记录，待 `09-15-web-shared-parse-core` 收口）：`reflex_web/reflex_web/web_utils.py` + `lookup_utils.py` 与 `main_gui.py` 存在多份同义实现（前缀剥离/帧提取/摘要/DLT645 转表/字段层级/查询数据源），历史上已发生漂移（协议10 摘要用协议9 函数、Web 独有 `get_hdc10_summary` 键名不匹配恒不命中、协议10 查询页抄协议9 表、南网 AFN 列算成 `di3 & 0x0F`）。改这些逻辑时必须**同时改两侧**并在 `test/test_web_parse_fixes.py` 补对拍断言，直至共享核心任务落地。
    - 已知**有意保留**的差异（勿当 bug 修）：① Web 校验与 Web 解析同预处理（含剔除），桌面 `verify_single` 不做头/尾剔除；② 协议10 查询页 Web 对 4 列（含「说明」）匹配关键词、桌面只匹配 类别/代码/名称（Web 为超集）；③ 南网 DI 页 Web 逐单元格匹配、桌面另含 DI 拼接串搜索。
32. **ED 包装解析入口的 `wrapper` 默认值**（1.23.12 起）：`main_gui._parse_ed_monitor_header` / `_extract_business_from_ed_frame` 与 `csg_new_gen_parser._parse_ed_wrapper` 的 `wrapper` 默认均为「None = 按当前下拉/逐帧自动识别」，**不要再写成硬编码 `"plc2"`**——快捷解析小窗曾因漏传 wrapper + 硬编码默认值，把广西台体帧按 9B 头错位解析 1 字节（复核实测业务偏移 15 而非 14）。
33. **预处理命令链的拆分必须走 `pp_cli.split_commands()`**（1.23.13 起）：中文输入法全角状态打出的空格（U+3000）与引号（＂“”‘’）不是 ASCII 字符，`shlex.split` 既不视作分隔符也不视作引号 → 整串被当成一个命令名（`未知命令: find　＂CSG＂`）。桌面 `_run_cli_preprocessor` 与 Web `parse_batch`/`run_preprocess` 三处**不要再直接 `shlex.split`**；该函数只在「首个 token 不是已知命令」时才做全角→半角归一化，以免改写参数里刻意保留的全角字符。命令名含非 ASCII 时 `parse_and_run` 会附码位，便于定位零宽/全角字符。
34. **Web 路由语义：`/` 是产品首页，工具页在 `/app`**（1.23.14 起）：改 Web 站内链接前先读 §1 的「Web 路由」说明——「回介绍页」用 `/`、「回工具」用 `/app`。工具页函数名已由 `index()` 改为 `tool_page()`（测试里 `app.index()` 引用已同步），登录弹窗与反馈列表 Tab **只挂在工具页**，独立页的「管理员登录」必须跳 `/app`。落地页侧的链接唯一来源是 `landing_web.INTERNAL_LINKS`，`test/test_web_landing.py` 会拦截指向白名单外的站内链接（含锚点）。另注：Reflex 在 JSX 里把非 ASCII 转义成 `\uXXXX`、把 `data_testid=` 渲染为 `"data-testid":"x"`、把 `rx.el.a(href=…)` 编译成路由 `Link`（属性名变 `to:"…"`），写字符串断言时必须按这三种实际形态匹配。
35. **dev 模式下 Reflex 前端不代理任何后端路径**（1.23.14 实测）：`reflex run --env dev` 时前端（:3000）与后端（:8000）是**跨源、绝对地址**通信（`reflex_web/.web/env.json` 里 `EVENT: ws://localhost:8000/_event`），Vite/react-router **没有** `/api`、`/download`、`/fbimg` 等代理规则——这些路径在 :3000 一律返回 `200 + text/html`（SPA 兜底，约 3.5KB），只有直连 `:8000` 才是真资源。因此 **Web 页面里不能用相对 URL 引用后端静态资源**（`<img src="/api/download/x.png">` 在 dev 必然破图）；`reflex_web.py:11851` 那条「Vite 会把 /api/* 代理到后端」的注释与实测不符。prod（`run_app.py` 单端口挂载）才同源可用。首页 Hero 截图因此沿用 `State.download_image_data_url` 的 base64 data URL（已验证通道）；**遗留缺陷**：`feedback_model.screenshot_url()` 返回相对路径 `/fbimg/<name>`，Web 反馈列表在 dev 下截图同样是破图（prod 正常），待单独修。
36. **顶栏版本徽章是 import 期快照，不是实时值**（1.23.14 起）：`version_badge()` 读 `reflex_web/downloads/version.json`（`_read_published_version()` 在模块导入时执行一次）→ ① 通过「发布管理」Tab 发布新版本后，**顶栏徽章要重启进程才变**（同页的 `State.download_version` 是实时的，二者会短暂不一致；需要实时就把徽章改成读 State）；② `reflex_web/downloads/version.json` **被 `.gitignore` 排除**（`reflex_web/.gitignore`）→ 任何没有该文件的部署，徽章**直接不渲染**（设计意图：宁可不显示，也不显示写死的假版本，`v1.13.0` 就是这么骗了很久）；③ 首页版本徽章/下载按钮读的是 `version.json`（State，实时），与顶栏同源但刷新时机不同，排查「版本号对不上」先看这两条。
37. **对外 URL 不许用 `rx.config` 的端口拼**（1.23.14 修复，改下载/分享/回跳链接前必读）：`rx.config.get_config()` 是**构建期**配置（rxconfig.py：`frontend_port=3000` / `backend_port=8000`），而 `run_app.py` 是**单端口**部署（如 8091）⇒ 用 config 端口拼出来的地址会变成 `host:8000`。历史缺陷：发布管理页用「config 端口 + `socket` 猜本机 IP」自动生成下载地址并写进 `version.json`，首页「下载客户端」因此跳到 `:8000`（GUI 自动更新也读这个 url，且它**必须**是绝对地址）。
    规则：**浏览器侧一律用同源相对路径**（`/download/<exe>`，任意 host/port 都对，还能自愈历史 version.json 里写死的端口）；**给外部消费者的绝对地址只能用当前请求的真实 host**（`self.router.headers.host`，实测可取；取不到就回落相对路径），**禁止猜 IP/端口**。判定与实现集中在 `web_utils.resolve_download_target` / `release_absolute_url` / `is_same_origin_serving`（单一来源），`test/test_web_download_url.py` 有纯函数矩阵 + 源码守卫。
38. **Web 守卫测试必须能抓住回退，否则是假绿**（1.23.14 复核结论，`test/test_web_landing.py` 已按此改造）：两类踩过的自洽假绿——① **白名单与渲染同源**：`ALLOWED_HREFS` 若由 `INTERNAL_LINKS` 派生、渲染也由它生成，则改错链接值白名单会跟着变，死链断言恒真（改为**字面量白名单** + 读组合层渲染串取 `to:` 目标的**接线断言**）；② **子串存在性被无关代码满足**：`f'"{flag}"' in main_gui_src` 会被 `any(a in ("--parse", …))` 这类元组判断满足，与真实解析分支无关（改为断言 `arg == "--flag"`，并抽出每条命令的**全部** flag）。新增此类守卫后用**变异反证**自检：临时把产品代码改回错误形态，确认测试**变红**再还原。
39. **Web 运行时数据必须在部署目录之外，且构建产物必须排除它**（1.23.14 起，改部署/存储/paths 前必读）：
    - **位置**：`data/`（feedback.db + frameshare.db + uploads/feedback/）、`downloads/`（发布管理上传的 exe）、`admin_config.json`（管理员口令）。运行时路径**唯一来源**是 `reflex_web/reflex_web/app_data.py`：`NW_WEB_DATA_DIR` → 冻结态 exe 同级 `nw_web_data/` → 回落代码目录（开发态现状）。**不要再在别处拼路径**（`load_download_info` 曾用「两候选目录猜测」，`run_app.py` 中间件曾用 `resource_dir/"data"`，都已被单一来源取代）。
    - **为什么必须外置**：升级最常见的方式是「删掉旧部署目录 → 拷新包」，数据在代码目录内会**在新程序启动前**就被删除，任何「启动时自动迁移」都来不及 → 数据根放**部署目录的上一级** `<parent>/nw_web_data`，由启动脚本注入变量，替换部署目录天然不动它。
    - **构建必须排除**：两个构建脚本共用 `reflex_web/deploy_common.py::ignored_web_entries`，排除 `data/`、`admin_config.json`（整目录/文件）以及 `downloads/` 里的**运行时产物**（`*.exe`、`version.json`、`archive/`）——否则会把**构建机的开发库**打进部署包，合并式拷贝时用开发数据顶掉服务器生产数据（比丢掉更难发现）。
    - **`downloads/` 里混着两类东西，规则不同**：`client_screenshot.png` / `client_readme.md` 是**随包静态资源**（必须进包，否则新部署开箱看不到截图/说明；管理员也可在「发布管理」Tab 上传覆盖——那份写数据根、优先级更高）；忽略规则用**白名单** `deploy_common.DOWNLOADS_ASSETS`（取自 `app_data.PACKAGED_DOWNLOAD_ASSETS`），黑名单会漏 `build`/`dist`（实测漏 25MB）；`*.exe` / `version.json` / `archive/` 是**运行时发布产物**（只从数据根读）。程序侧用 `app_data.resolve_download_asset(name)`：**数据根优先、缺失回落随包资源**。改 `load_download_info` 的截图/README 两处或忽略规则时不要把这条弄丢。
    - **单文件 exe 的坑**：`reflex_web_exe.spec` 是 onefile，`sys._MEIPASS` 每次启动解包、退出即删 ⇒ **绝不能**把数据写在 `_MEIPASS` 下（`run_app.py` 曾把 `resource_dir` 取成 `_MEIPASS` 用于数据路径，等于每次重启清零）；冻结态取 `Path(sys.executable).parent / "nw_web_data"`。
    - **迁移**：`app_data.migrate_legacy()` 只搬「旧有、新无」，**绝不覆盖**，失败只告警不阻断启动；`downloads/` 里的随包资产**不搬**（否则数据根会永久压住后续版本的随包更新）；产物内附 `迁移数据.cmd/sh` 供「先删旧目录」式升级手工搬。文档不得再承诺「重建时自动保留 data/」（旧的 `preserve_data_dir` 逻辑保护的是 `<out_dir>/data`，而真实路径是 `<out_dir>/reflex_web/data` ⇒ 该保护从未生效）。
40. **批量解析已后台化：批量路径不得再假设它同步完成**（1.23.15 起，改批量/详情/导出前必读）：`parse_batch()` 现在**立即返回**，逐帧解析在 `batch_parse_worker.BatchParseWorker` 线程跑、结果按 200 帧/片经信号回填。因此：① **测试**里 `win.parse_batch()` 之后必须 `wait_batch(win)`（`test/_batch_wait.py`）再断言 `batch_results`，否则读到空集；② **详情/导出/复制/时序图不得再直接读 `result["_table_data"]`**——记录里已没有它（改为 `_has_detail`/`_ed_type`），一律走 `MainWindow._get_frame_table_data(index)`（LRU 50 帧）或给导出函数传 `table_data_resolver=`（`sequence_diagram_widget.build_sequence_model_csg` 同理）；③ 新增 QThread 必须 `thread_registry.track(self, 名称)`；④ worker 内**禁止触碰 widget**，解析参数一律由 `_current_parse_params()` 快照传入。
41. **解析器带「跟帧可变状态」，同一帧在不同解析历史下结果可能不同**（1.23.15 实测 934/49,532 帧不一致）：`csg_new_gen_parser.parse_to_table` 只在特定分支写 `_efc_symbol_count`/`_ofdma_frame_type`/`_ofdma_station_count`，**未在入口重置** ⇒ 前序帧影响当前帧的解析结果；单帧页、批量解析、详情重解析三者历史不同 → 表格差 1 行。批量侧现用 `capture/apply_cross_frame_state`（记录字段 `_ctx`，仅非默认值时存）锁存「帧前状态」并在重解析前复原。**任何「同一帧在两处解析结果必须相同」的功能（详情/对比/导出/时序图）都要考虑这条**；根治需在解析器入口重置全部状态，但那会改变批量结果本身 ⇒ 属独立任务。
42. **窗口/分栏/列宽状态持久化只走 `_save_app_config`（1.23.16 起）**：几何/分栏/列宽存 **`config.json` 顶层 `window` 段**（`_collect_window_state` 采集、`_apply_window_state` 套用、`_reset_window_layout` 清空）。改这块时注意：
    - **不要塞进 `ui` 段**：该段每次保存都由 `ThemeManager.to_config` **整体重建**，塞进去会被下一次保存抹掉；也不要在 `closeEvent` 里另写一份 JSON（保存统一走 `_save_app_config`）。
    - **写出时机只有 `closeEvent` 的真实退出路径**（含托盘「退出」与自动更新重启）；最小化到托盘（`event.ignore()` 分支）不写。`_save_app_config` 其它调用点沿用载入值，空则删键（避免把中途布局当退出布局）。
    - **恢复必须容错**：几何与任一 `QScreen.availableGeometry()` 无交集（换显示器/降分辨率）或 base64 损坏 → 回落默认居中尺寸；列宽按**表名 + 列数**匹配，列数不符（协议切换重建查询页）即丢弃该表。
    - **测试不得污染真实 `config.json`**：`MainWindow` 关闭时会写出该段，offscreen 测试必须先沙箱——`main_gui.data_path` **与** `app_paths.data_path` 都要 patch（`llm_preprocess_widget.save_config()` 内部是 `from app_paths import data_path`，只 patch 前者会把真实配置写掉，`test_pp_cli.py` 的「真实 config.json 未被测试改写」断言就是这么抓到的）；样板见 `test/test_window_state.py` 的 `Sandbox`（1.23.16 起）。

---

## 9. 开发原则

1. **协议定义优先**：遇到不确定的协议字段、字节序、校验范围，**先查 §5 对应文档**，不要凭记忆或猜测。
2. **PDF 文档用 pdf skill 检索**：645 补遗、IEC 62056-46、DLT645 原始标准都是 PDF，调用 pdf skill 而非人工翻阅。
3. **新增协议的完整 checklist（1.23.1 起）**：
   - [ ] 在 `protocol_registry.py` 追加 `ProtocolSpec`（下拉名/别名/占位符/能力/校验器/提取策略）
   - [ ] 在 `parser_registry.py` 注册 parser 键；新建 `xxx_parser.py` 返回嵌套 dict（键名遵循 §4.2）
   - [ ] 新建 `validator/xxx_validator.py` 继承 `BaseValidator`，写入 spec 的 `validator_class`
   - [ ] 查询页如有新类型：在 `lookup_builder_method` 映射 + 实现 `_create_*_lookup_content`
   - [ ] 如需 Web 版支持，同步更新 `reflex_web/reflex_web/reflex_web.py` 与 `reflex_web/reflex_web/lookup_utils.py`
   - [ ] **在 `reflex_web/reflex_web/landing_web.py` 的 `PROTOCOLS` 追加一行**（索引/协议名/标准号/字节序/校验）；`test/test_web_landing.py` 会用 `protocol_registry` 逐行对拍，漏改即测试变红
   - [ ] 同步更新本文件 §1/§3/§5/§6、README；新建 `test/test_xxx.py`
   - [ ] 如需打包，更新 spec 的 `datas`/hiddenimports
4. **解析器独立性**：parser 之间避免横向耦合；公共逻辑放 `base.py` 或工具模块。
5. **GUI 组件拆分**：新 UI 组件独立成文件，`main_gui.py` 只负责组合。
6. **中文键名保持一致**：`原始值`/`十进制`/`说明` 等，GUI 表格列直接读这些键。
7. **字节序显式**：`int.from_bytes(data, 'little'/'big')` 必须显式写参数，禁止依赖默认。
8. **CHANGELOG 即时维护**：完成功能后，在 `main_gui.py` 的 `CHANGELOG` 列表头部新增条目（版本号/日期/要点）。

---

## 10. 变更日志

> 详细版本变更记录请查看 `main_gui.py:CHANGELOG`（按版本倒序），或运行 `git log --oneline` 查看提交历史。本文档仅保留最近两个版本的摘要。

### 1.23.14 — 2026-09-15

- **Reflex Web 版新增独立产品首页（落地页）**：`/` 改为介绍桌面客户端的首页，原 9 标签页工具页让位到 `/app`（`index()` → `tool_page()`）；`/share`、`/feedback`、`/feedback-admin` 不变。首页含 Hero（版本徽章 + 双 CTA + 窗口拟态截图）、关键数字条、12 张功能卡、12 协议支持表、命令行与系统集成、下载收尾区、页脚；全部走 `theme_web` token（浅/深 + 5 强调色）
- 新增 `reflex_web/reflex_web/landing_web.py`（**纯内容 + 纯展示组件，不 import `reflex_web`**，运行时值全参数注入 → 可脱离 State/浏览器构建整页断言）；导航改造 4 处站内链接无死链（品牌块 → `/`、「返回主页」→「在线工具」`/app`、独立页管理员登录 → `/app`、share/feedback-admin 回跳 → `/app`）；主题控件抽 `theme_controls_compact()` 两端共用
- 放弃「截图改 URL + 删 base64 字段」的原设计：实测 **dev 模式 Reflex 前端跨源、不代理任何后端路径**（`:3000` 对 `/api/*`、`/download/*`、`/fbimg/*`、`/ping` 一律返回 SPA HTML）→ 相对路径图片在 dev 必破图，沿用 base64 通道。另修 420px 视口横向溢出（顶栏 `flex-wrap`）与深色下「浅色强调 + 白字」对比度不足（`html.dark` 覆盖改 `var(--bg)` 字色）
- 新增 `test/test_web_landing.py`（100 项，含与 `protocol_registry` 逐行对拍防漂移、死链白名单 + **跨页面接线断言**（读 `tool_page()`/`share_page()`/`feedback_page()`/`feedback_admin_page()` 渲染串取 `to:` 目标）、路由搬迁断言；已用**变异反证**确认能抓住「链接语义被改回去」与「CLI 解析分支被删」），登记 `release_check.py:CORE_TESTS`；`test_web_spectrum`/`test_web_theme` 的 `app.index()` 同步改名；playwright 用例 goto `/app` + 新增首页冒烟

- **Web 运行时数据外置（任务 09-16-web-data-externalization）**：反馈库/分享库/截图、发布管理上传的 exe、管理员口令原先都在代码目录内（升级替换目录即丢，且构建脚本会把**构建机的开发库**打进包）→ 新增 `reflex_web/reflex_web/app_data.py` 作为运行时路径唯一来源，数据根默认放**部署目录的上一级** `nw_web_data/`（`NW_WEB_DATA_DIR` 由启动脚本注入、可覆盖），两个构建脚本共用 `reflex_web/deploy_common.py`（忽略规则排除运行时数据 + 生成 `迁移数据.cmd/sh`），并修掉 onefile exe 把数据写进 `_MEIPASS`（每次重启清零）的缺陷；删除从未生效的 `preserve_data_*`/`restore_data_*` 与「重建时自动保留 data/」的错误承诺，新增 `test/test_web_data_paths.py`

### 1.23.13 — 2026-09-15

- **修复批量解析「预处理」命令链在中文输入法全角状态下不可用**：全角空格（U+3000）与全角/弯引号（＂ “ ” ‘ ’）不是 ASCII 字符，`shlex.split` 既不把它们当分隔符也不当引号 → 整串被当成一个命令名（现场表现为 `find　＂CSG＂` 报「未知命令: find　＂CSG＂」，而无参数的 `hex_extract` 能执行，故看起来"有的命令能跑、有的报错"）
- 新增 `pp_cli.split_commands()` 单源：先按原样拆分，**只有首个 token 不是已知命令时**才做全角→半角归一化重试（U+3000/U+00A0/U+2000–200A/U+202F/U+205F → 空格，U+200B/BOM 删除，＂“”‘’ → 半角引号）——「半角分隔符 + 参数里刻意保留全角字符」的写法不被改写；`main_gui._run_cli_preprocessor` 与 Web `parse_batch`/`run_preprocess` 三处调用点改走该函数
- `pp_cli.parse_and_run` 未知命令报错附转义形式 + 非 ASCII 字符码位（全角/零宽字符肉眼不可见，旧文案无法定位）+ 半角书写提示；GUI tooltip / 帮助对话框 / Web 说明同步补规则
- 新增 `test/test_pp_cli.py`（47 项：半角基准 / 归一化各变体 / 参数内容保护 / 错误提示码位 / 用户场景端到端 / offscreen `MainWindow._run_cli_preprocessor`），登记进 `release_check.py:CORE_TESTS`

### 1.23.12 — 2026-09-15

- **Reflex Web 版解析 P0 修复（任务 09-15-web-parse-p0-fixes）**：`_get_validator` 未定义变量 `p` → 12 协议校验全部 NameError（改走 `protocol_registry.make_validator`）；批量失败判定只看首行 → 改全表扫描「以 ❌ 开头的行」（**两侧**同时统一空表 = 失败）；奇数长度 hex 静默截断 → 改报错；协议10/11 pb_only 补 `frame_type` 下发 + 协议9 补 `mac_only`/PB 帧类型下拉；查询页南网 AFN=DI1、协议10 改读 `GWNewGenParser` 自有 7 类表、协议8 补属性/方法列；报文工具 CRC-24 `rev=True`
- **ED..EE 监控包装格式判别下沉到解析器**：`csg_new_gen_parser.detect_ed_wrapper`（逐帧打分，plc2/gx）+ `_parse_ed_wrapper` 双布局 + `parse_to_table(ed_wrapper=None)`；桌面 `main_gui._detect_ed_wrapper` 改为委托（删除重复打分与 `_ED_PB_SIZES`）。**广西台体(gx, 8B 公共头)帧此前在两端未勾选 ED 复选框时都错位 1 字节，本版一起修好**；摘要按「含 `监控包装头`」判定并区分两种包装名
- 新增 `test/test_web_parse_fixes.py`（75 项，含 reflex `State(_reflex_internal_init=True)` 真实实例断言与 `parse_batch` 批量端到端），登记进 `release_check.py:CORE_TESTS`；批量链路同时统一：`mac_only` 剥离直通（此前整行被丢弃）、不静默裁剪奇数长度、异常状态字面量 `异常`
- **Web 批量界面分页与全宽**（`web_utils.paginate/page_of` + `test/test_web_batch_paging.py` 25 项）：全量摘要留后端、前端只同步当前页（替换 `batch_display_limit=300` 截断），首页/上页/下页/末页 + 每页 100/200/500/1000，行号跨页连续；摘要/明细区高度改 `calc(100vh - …)`；`.app-container`/`.app-header-inner` 放开为全宽；选中高亮改 `class_name=rx.cond`（`style=rx.cond({...})` 在本项目不落 DOM）；**批量结果可搜索**（关键词匹配 摘要/类型/帧HEX/#序号 + 状态筛选，过滤作用于全量摘要后分页，帧 HEX 存后端私有行不下发前端）
- 审计勘误：原「Web 剔除不幂等」结论实测不成立（Web 每次从原始 `frame_hex` 重算本就幂等；照该结论加缓存会真回归，已撤销）→ 以纯函数 `strip_frame_bytes` + 重复调用一致断言钉住不变式
- 复核（trellis-check）追加修复：桌面快捷解析小窗 ED 调用点漏传 `wrapper`（gx 帧错位 1 字节）→ 补传并把两个 ED 入口的 `wrapper` 默认值改为「None=按当前下拉/自动识别」；`validator/__init__.py` 补齐 `GWNewGenValidator`/`HDC10Validator` re-export + 三个 spec 补 `protocol_registry`/`parser_registry`/`hdc10_*`/`validator.*` hiddenimports（`make_validator` 走 importlib，打包器静态分析看不到）
- **Web 版新增「频谱图」常驻标签页**（任务 09-15-web-spectrum-plot）：桌面 `spectrum_widget.py` 纯逻辑层（前 ~950 行，零 Qt）**被 Web 直接复用**（参数校验/trace 清洗/刻度/标记吸附/峰值搜索/积分带宽同一实现），新增 `reflex_web/reflex_web/spectrum_web.py` 仅做 SVG 坐标换算（纯函数），QPainter 换成 SVG；功能对齐桌面（四字段联动/单位换算/点击加 M1~M6 标记含固定配色与 Δ/峰值搜索/积分带宽含 RBW 归一化/导出 PNG 走前端 SVG→canvas）；新增 `test/test_web_spectrum.py`（64 项）
- **Web 版主题系统**（任务 09-15-web-theme-system）：`theme_web.py`（6 预设 + 5 强调色 + 3 模式 + token 表 + 客户端脚本）；`GLOBAL_CSS` 与组件 **215 处硬编码色值全部 token 化**（浅色取原值 → 观感等价，深色只覆盖 token）；顶栏主题下拉 + 模式循环按钮，选择存 `localStorage['nw-theme']` 并在刷新后恢复（含 Reflex ThemeProvider 类覆盖竞态的收敛）；频谱图 SVG/标记配色走 `var(--sp-mN)`；同步修复主题控件导致的独立页面顶栏导航被挤、顶栏渐变不随强调色、分享卡片 `str(Var)` 垃圾串三处问题
- 后续子任务（规划中）：`09-15-web-shared-parse-core`（共享核心 + 接注册表）、`09-15-web-batch-alignment`（余：摘要同源/跨行 payload/行号/导出字段）、`09-15-web-single-frame-alignment`、`09-15-web-parse-perf`（父任务 `09-15-web-parse-alignment`）

### 1.23.11 — 2026-09-15

- **南网查询页「自定义DI」增删收口（09-12-nanwang-custom-di-crud）**：新增 `custom_di_store.py` 单源（纯逻辑无 Qt：`custom_di.json` 读写 / 单字节 hex 校验 / DI 键解析 / upsert / 批量删除），`protocol_parser` 三处读写委托之（整体读改写，未知字段不丢）；`main_gui._add_custom_di/_del_custom_di` 与 `lookup_pages` 简化页共用 `apply_custom_di_add` / `delete_selected_custom_di_interactive` 同一份实现
- **行为增强**：重复 DI 由直接拒绝改为**覆盖确认**（提示区分「已添加/已覆盖」）；删除支持**多选批量**（DI 表开 ExtendedSelection，提示带条数与被忽略的内置条数）；内置 DI 拒删 / 未选中给出可读提示；新增条目同步进解析器 `DI_COMBINATION_MAP`（单帧解析即时生效）
- `lookup_pages.create_di_lookup_page` 两枚「功能待实现」死按钮改真实增删；表格刷新改 `state` 字典（刷新重建列表，防闭包引用陈旧 `di_data`）
- 测试：`test/test_nanwang_custom_di.py` 92 项（含 `app_paths.data_path` 沙箱零污染真身、offscreen MainWindow 增删/重启保持），登记进 `release_check.py:CORE_TESTS`

### 1.23.10 — 2026-09-14

- **批量解析摘要体现测试帧的测试模式**：`main_gui._extract_test_mode_content(table_data)`（staticmethod，纯逻辑）从解析行提取 `测试模式/配置操作`（名称/数值双槽探测：协议9 表61 名称在 comment、协议10 检测扩展命令名称在 parsed）+ `安全测试模式`/`新一代测试模式` 子模式；协议9 接入 `_extract_csg_core_content` **首个分支**（业务标识 0xF0；测试帧帧类型是「命令帧」，不提前返回会被通用命令分支淹没），协议10/11 在 `_get_gw_new_gen_summary` 既有片段后追加
- **无测试模式字段的测试帧回退**：`测试ID`（0/1/2 类，如「频段切换命令」）/`扩展ID`（2.0测试，如「Bitloading表下发」）/`通信频段:0x02`/上行「测试帧上行（确认/否认，无数据单元）」；非测试帧不受影响（helper 无痕迹返回空串）
- **名称取槽位不做描述黑名单**：两个解析器把模式名放在相反槽位（协议9 表61 名称在 comment、协议10 检测扩展命令名称在 parsed）→ 统一按「**parsed 非数值则名称在 parsed，否则在 comment**」探测，避免漏掉某个模式的描述句（曾因此让模式15 输出描述文本而非子模式名）；名称自带括号时省略模式号；`上行负载` 分支要求表内 `业务标识` 自证 0xF0（该行名被 4 个非测试上行业务共用），协议10/11 仅在三个哨兵行存在时才调用 helper
- **测试单源**：`test/test_csg_summary.py` 删除文件内复刻的摘要逻辑（已与产品实现漂移：复刻版输出「网络层」而产品输出「网络管理消息」），改为 Host 复用 `MainWindow` 未绑定方法 + 新增真实抓包 0xF0 帧/1.0 测试帧/上行/非测试帧用例；`test/test_gw_monitor_summary.py` 增检测扩展命令模式 3/13 与普通通信测试用例

### 1.23.9 — 2026-09-14

- **频谱图标签页**（`spectrum_widget.py`，常驻、与协议无关）：频谱仪参数（起始/终止/中心/扫宽**四字段双向联动** + 频率单位、RBW/VBW、参考电平、每格 dB、纵向格数、幅值单位 dBm/dBμV/dBmV（可选 50Ω 换算 +107/+47）、检波方式）+ 单条 trace 全部扫频点数值 → **QPainter 自绘仪器式网格频谱图**（横向 10 格 × 纵向 N 格，顶格=参考电平；可切「纵轴自动适配」），标题+参数注记随图渲染，可导出 PNG（1600×1000），浅/暗主题调色板
- **测量（同版本追加）**：鼠标悬停十字光标 + 频点/幅值读数框（吸附最近数据点）；点击添加 MARK 标记 M1~M6，**每个标记一种固定颜色**（图上竖虚线/圆点/M? 标签与标记表行文字同色）；标记以**频率**为锚点（重绘/改单位后自动重新吸附、越界丢弃且提示不覆盖点数信息）；标记表 `标记/频率/幅值/Δ频率(哪两点)/Δ幅值(哪两点)`（Δ 一律标注 `M?↔M?`，`Δ 参考` 下拉可切参考标记）；测量栏峰值/谷值；「峰值搜索/下一个峰值」按 3 dB 显著度环形搜索（**单调栈 O(n)**，原 O(n²) 在 16000 点上 3.74 s 冻结 GUI）；标记与 Δ 注记随导出 PNG 渲染
- **积分带宽（同版本追加）**：参数区「积分带宽」分组（中心频率 + 积分带宽 + kHz/MHz + 显示开关）；图上两条点划线竖线（独立配色）+ 边沿间半透明填充带 + `IBW 起–止` 标签；带内**积分功率**（线性求和后转 dB，按 `频率步进/RBW` 归一化；RBW 未填注明未归一化）与带宽内点数；越界按交集积分并标注、无交集不填充；参数区改包 `QScrollArea`（新增分组后矮窗口不裁掉底部控件）
- **trace 日志清洗（同版本追加）**：可直接粘贴带日志前缀的行（`… --USER--MTC@PC: -51.564613`）——每行取**行尾真实数值**（数值后可带 `dBm/MHz` 单位后缀）；逐行规则：空行忽略 / 全数值行全部采纳 / 行尾可取则取该值 / **有值却取不到行尾 → 明确报错**（不静默只取一半）/ 无数值含日志结构（冒号、日期、制表符）→ 跳过计数 / 无数值无日志结构 → 报错；纯时间戳行跳过；`TraceInput` 统计经状态行提示「已清洗 N 行日志，跳过 K 行无数值」
- **零新增依赖**：不用 matplotlib（`南网协议解析工具.spec` 显式排除）与 QtCharts；纯逻辑层不依赖 Qt（解析/日志清洗/校验/频率轴/纵轴/刻度/换算/联动/标记/峰值/积分功率 皆可脚本测试）
- main_gui 仅 3 处接线（import / 常驻 tab `chart-spline` / `_restyle_for_theme` 钩子）；不改协议可见性

### 1.23.3 — 2026-09-11

- **发布自检**：`python release_check.py`（可选 `--sync-iss` / `--with-gui` / `--skip-tests`）；核心测试清单与 `test/test_core_suite.py` 共用
- Inno Setup `MyAppVersion` 已从 1.11.0 同步到当前 APP_VERSION

### 1.23.1 — 2026-09-11

- **协议能力注册表**：新增 `protocol_registry.py`，12 协议元数据与校验器/解析器包装/批量提取策略集中声明；`main_gui` 的 combo/占位符/Tab 可见性/查询页/`_get_current_parser`/校验 map/名称映射/帧提取 全部查表
- 修复协议6 预设命令 `set_protocol("dlt645")`；新增 `test/test_protocol_registry.py`

### 1.18.1 — 2026-08-28

- **快捷解析小窗毛玻璃化**（`system_integration/quick_parse_panel.py` + 新增 `acrylic_effect.py`）：Windows 10 1803+/11 用 ctypes 调 `SetWindowCompositionAttribute` 启用系统级亚克力模糊（失败静默降级），卡片约 50% 半透明；空态精简——无输入时面板透明无边框禁投影（只显示输入框本身，可拉高），输入有效报文展开后才呈现 1px 细毛玻璃边框+投影；输入框/协议下拉/按钮/结果表格全部半透明化，卡片圆角 14px，明暗主题各有配色
- **修复小窗高度收回失效**：清空输入回空态时窗口高度滞留不回缩、手动调整高度被打回——根因 `_fit_height` 只 invalidate 内层布局未 activate，外层 `activate()`/`sizeHint()` 读到陈旧缓存；修复为先激活内层布局再取 sizeHint（`quick_parse_panel.py:_fit_height`）
- **测试**：`test/test_quick_parse_panel.py` 现 62 项断言全过（空态透明/投影禁用/输入框可拉高/展开恢复细边/毛玻璃透明度/亚克力接口/空态收回 390→244px/MainWindow 集成），退出码正常

### 1.18.0 — 2026-08-28

- **状态栏增强**：新增本软件自身 **CPU 占用 %** 与**内存占用（MB）**实时显示（CPU 为整机口径与任务管理器一致、0~100%；内存当前工作集 + 悬停看峰值；CPU <30% 灰、30~60% 橙、≥60% 红警示）。采样走新建 `proc_stats.py`（纯标准库零依赖：Windows ctypes、Linux /proc、其他平台安全降级 --），**4 秒慢刷新**定时器（微秒级系统调用，不影响 GUI 流畅度）
- **线程数标签可点击**：点状态栏「线程: N」弹出轻量 QMenu 明细——Python 线程（名称/ident/守护/运行状态）+ QThread（名称/类名/运行或已回收）分组列出，底部「📋 复制线程列表」一键复制；点外部即关不阻塞。原 tooltip 保留简要提示。菜单构建与弹出拆为 `_build_thread_detail_menu()`/`_on_thread_count_clicked()` 两方法（构建纯函数化便于测试）
- **测试**：新增 `test/test_statusbar_stats.py`（proc_stats 采样 / 三标签刷新 / 明细菜单结构+剪贴板 / CPU 着色阈值）；`test_app_exit.py` 线程回收回归通过

### 1.17.2 — 2026-08-28

- **修复关闭软件（含托盘退出）后进程残留**：Qt 仅在「最后一个可见顶层窗口」关闭时才结束 `app.exec()`；X 最小化到托盘后窗口已隐藏，托盘退出/自动更新重启再调 `close()` 时 `lastWindowClosed` 不触发——`closeEvent` 真正退出路径 `event.accept()` 后追加 `QTimer.singleShot(0, QApplication.quit)` 显式结束事件循环。新增 `test/test_app_exit.py`（offscreen 三场景）；`SerialSlaveThread` 补登记 thread_registry；剪贴板 monitor `stop()` 屏蔽无害 disconnect RuntimeWarning
- **修复协议9 ISAC-PLC SOF 帧 Bitloading/物理块大小解析错误**：字节6(表23) 拆分为 Bitloading标识(bit0) + 物理块大小码(bit1-2, 0:136 1:520 2:72 3:264，Bitloading=1时)；原实现误用表13 ROBO/TMI 映射（0→520，实为136）。Bitloading 模式显式 `_pb_size` 供 PB 解析，`parse_to_table` 入口每帧重置 `_pb_size/_cmt_index/_pb_count` 防跨帧残留；`test_csg_new_gen.py` +2 项

### 1.17.1 — 2026-08-27

- **快捷解析小窗拆为两张独立卡片**（`system_integration/quick_parse_panel.py`，用户反馈输入框与结果应分开）：单一大卡 → 输入卡（徽章行：协议下拉+帧长+校验徽章，加输入框）常驻 + 结果卡（状态提示/⚠错误 + 结果表格 + 底部操作行）在下方实时浮出；两卡各自圆角边框、独立投影，间隙空白可按住拖动窗口；空态仅显示输入卡
- **缩放柄移位**：QSizeGrip 从旧大卡移挂到最外层窗口右下角 margin 空白处——不遮挡任何控件，空态与展开态均可拖拽调整大小；明暗主题 `_restyle` 同步作用于双卡并刷新两卡投影颜色；`_fit_height` 对两张卡布局强制重算高度
- **测试**：`test/test_quick_parse_panel.py` 扩至 45 项断言（空态仅输入卡 / 双卡并存独立 / 错误态结果卡弹出 / 缩放柄挂外层 / 暗色主题双卡配色）；offscreen 截图核验。注：该套件退出码为本机已知的 MainWindow 关闭期 fastfail（0xC0000409），与改动无关、逻辑断言全过

### 1.17.0 — 2026-08-27

- **新增 uTools 风格「快捷解析小窗」**：全局热键（默认 Ctrl+Alt+X）唤出无边框圆角置顶悬浮面板；粘贴/输入报文实时（300ms 防抖）解析——协议下拉自动识别可手动切换、帧长、校验✓/✗徽章、完整字段树；剪贴板合法 hex 唤出即自动填入；Esc/再按热键/失焦隐藏；「完整视图」转原大弹窗、「复制结果」复制 TSV
- 新增 `system_integration/quick_parse_panel.py`（哑组件，clean/parse/validate/open_full/主题回调由 MainWindow 注入，不 import 解析器）；设置面板热键提示文案更新；spec hiddenimports 补 quick_parse_panel
- 新增 `test/test_quick_parse_panel.py`（初版 29 项）

---

## 12. 其他参考文档

- `QWEN.md` — 项目详细文档（中文），含协议帧格式说明和开发约定（**部分内容可能滞后，以本文件为准**）
- `README.md` — 用户面向的简要说明（功能列表、运行方式、项目结构，包含 Web 版/698.45/新一代协议等）
- `CLAUDE.md` — Claude Code 专用指南（与本文档部分重叠，**以 AGENTS.md 为权威**）
- `work_list.md` — 工作清单/字段定义（开发参考）
- `docs/superpowers/specs/2026-05-12-dl-t698-45-parser-design.md` — 698.45 解析器设计规格
- `南网新一代20260226校对/南网新一代20260226校对/《南方电网计量自动化系统双模通信技术规范 第2部分：无线通信接入协议》（报批稿）.md` — 协议9 无线信道(HRF)协议定义参考（原 PDF 同目录；引用优先级见 §5.7：新一代有定义用新一代，无线专有内容用本文档）
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

- [ ] 通读本文件（§1~§9 是核心，§10 是最近版本摘要），并按 `.trellis/workflow.md` 判断当前阶段
- [ ] 如修改代码，先读取 `.trellis/spec/` 中对应层级的规范
- [ ] `python main_gui.py` 启动 GUI，逐个协议切下拉框，确认能跑
- [ ] 查 `git log --oneline -20` 了解最近提交
- [ ] 查 `git status` 了解未提交改动
- [ ] 根据**要修改的协议**，按 §5 找到对应 parser 和参考文档
- [ ] 修改前查 §8 陷阱，修改后按 §9 原则自检
- [ ] 完成后同步更新 `main_gui.py:CHANGELOG` 与 `README.md`
