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

多种电力通信协议的图形化解析工具。单代码库，纯 Python 3.8+，无构建系统，无正式测试框架。当前版本见 `main_gui.py:APP_VERSION`（现 `1.23.77`）。

**支持的协议（共 15 种，对应 GUI 协议下拉框 `current_protocol` 索引）：**

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
| 8 | 698.45 协议 | DL/T 698.45-2017 | 小端（链路层 L/HCS/FCS）/**大端（A-XDR 数据）** | **CRC-16（crcmod 的 `x-25`）** |
| 9 | 新一代载波协议（通感一体化） | 通感一体化低压电力线宽带载波通信规约（2026校对版） | 小端 | CRC-32（MAC帧） |
| 10 | 国网新一代双模通信互联互通 | 国网新一代双模通信互联互通技术规范 | 小端 | CRC-32（MAC帧） |
| 11 | HDC 1.0 双模互联互通 | Q/GDW 12087.42-2020 | 小端（MAC 地址大端） | CRC-24（FC/PB）+ CRC-32（MAC） |
| 12 | 模组化终端功能模块接口 | Q/GDW 模组化终端功能模块接口协议 | 小端（链路层 L/C/FCS）/**大端（A-XDR 数据）** | CRC-16/PPP FCS（x-25） |
| 13 | 依瓦定制645 | 依瓦定制645协议 V1.0 | 地址域高字节在前 / 数据域逐字节 | 8位位组算术和（数据域 ±0x33） |
| 14 | 南网上行通信规约 | Q/CSG 11109004-2013 | 小端（长度L/地址域/多字节字段） | 8位位组算术和（控制域+地址域+链路用户数据） |
| 15 | Modbus 协议（RTU/TCP） | Modbus Application Protocol V1.1b3 / Modbus over Serial Line V1.02 | 大端（寄存器内可配字节序/字序） | CRC-16（多项式 0xA001，RTU）/ TCP 靠 MBAP 长度域 |

> 协议覆盖差异：**HDC 1.0（索引 11）在 PySide6 主程序与 Reflex Web 版均支持**（2026-09-15 核实）。Web 版无实时监控器/档案/拓扑；组帧与预设标签页在 Web 存在但协议 9/10/11 均不支持（与桌面一致），协议11 另有「无实时监控器/组帧/预设」的说明见 §8 陷阱 27。**「频谱图」标签页两端都有**（与协议无关，常驻）：桌面 `spectrum_widget.py`（QPainter 自绘），Web `reflex_web/reflex_web/spectrum_web.py`（SVG）——两侧共用同一份纯逻辑层。**Web 另有主题系统**（浅色/深色/跟随系统 + 6 个预设 + 5 个强调色，`reflex_web/reflex_web/theme_web.py`，token 化 CSS）；桌面为 7 套 QSS 主题（`theme_settings.py`，含毛玻璃/云母，Web 无对应）。NiceGUI/TUI 版本已于 2026-08-17 移除。**协议8/6 另有专用页**：协议8 有「光伏升级」标签页（698.45 文件传输升级：启动传输 → 写文件×N → 执行升级，拖入升级包、逐包等确认、进度条，1.23.85 起；另有**可选**的「升级前/升级完成后读版本信息」两步——通用版本 `OAD 43000300` 或厂家扩展内部版本 `OAD FF100400` 二选一，默认不勾、失败不阻断升级，**两次读到的版本会自动比对给出「升级成功（版本已变化）/ 升级失败（版本完全一致）/ 无法判定」结论**（1.23.86 起）；以及仅串口的**可选**「提升波特率」——升级前先发 FT1.2 命令让设备切 115200，传完切回 9600，升级后读版本在两种速率上各试一遍（1.23.86 起）；后端为纯逻辑 `dl_t698_45_upgrade.py`，**Web 无对应**），协议6 有「645虚拟表」（1.23.5 起）与「**645协议测试**」页（1.24.1 起：按 DI 大类分类的命令树 + 读/写通信地址 + 特殊命令，纯逻辑 `dlt645_test_core.py`，**Web 无对应**）。**「生产测试架」也是常驻页**（与协议无关，1.23.88 起）：类串口助手（5 条发送配置，各自 HEX/ASCII + checksum8）+ 一条可配置的测试架参数帧（49 项参数，改动即生成 75 字节整帧），纯逻辑在 `production_testbench_core.py`，**Web 无对应**。**Modbus（协议15，1.23.97 起）仅桌面端支持**：RTU/TCP 自动识别 + 可选「寄存器列表」（`modbus_registers.json`，按品牌记录地址/类型/系数/单位）翻译工程量；未选列表时按通用方式解析（只到功能码、地址/数量与原始值）。

> **Web 路由（1.23.14 起，改链接前必读）**：`/` = **产品首页**（落地页，介绍桌面客户端：Hero/功能卡/协议表/命令行与系统集成/下载区/页脚，实现在 `reflex_web/reflex_web/landing_web.py`）；`/app` = **在线工具**（原主页的 9 个标签页，函数名 `index()` 已更名 `tool_page()`）；`/share`、`/feedback`、`/feedback-admin` 不变。首页数据全部读 `reflex_web/downloads/`（`version.json` 版本、`*.exe` 体积、`client_screenshot.png` 截图，缺图降级占位卡）。**新增/修改站内链接时必须按语义选目标**（回介绍页 `/`、回工具 `/app`），`landing_web.INTERNAL_LINKS` 是落地页侧的唯一来源，`test/test_web_landing.py` 有死链白名单守卫。

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

# 打包后自检（不建窗、不读写文件；返回码 0 才算打包合格）
南网协议解析工具_v1.23.90_xxxx.exe --self-test

# 自动化冒烟专用：跳过单实例检查（正常用户不要设置）
NW_NO_SINGLE_INSTANCE=1 QT_QPA_PLATFORM=offscreen 南网协议解析工具_v1.23.90_xxxx.exe
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
- Inno Setup 安装脚本 `南网解析工具.iss` / `2222.iss` 的 `MyAppVersion` 用 `python release_check.py --sync-iss` 与 `APP_VERSION` 对齐（**不要在本文件里写死版本号——它会随每次 bump 过期**；`--sync-iss` 会打印新旧值）。`release_check` 有硬校验：iss 与 `APP_VERSION` 不一致直接 **FAIL**，README 徽章不一致则 **WARN**；发版前务必再跑一次 `python release_check.py`

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

3. **打包流程**（两种形态，版本资源/清单/依赖清单的单一来源都是 `pyinstaller_meta.py`）：

   ```bash
   # 1. 更新 BUILD_DATE 为当前日期（APP_VERSION 仅在功能变更时 bump）

   # 2a. 文件夹形态（推荐对外分发 + 安装包用；无自解压，被杀软拦的概率更低、启动更快）
   pyinstaller 协议解析工具_onedir.spec --noconfirm
   dist\协议解析工具\协议解析工具.exe --self-test      # 返回码 0 才算打包合格
   # 然后编译 南网解析工具.iss（它的 Source 就是 dist\协议解析工具\协议解析工具.exe）

   # 2b. 单文件便携版（Release 附件用）
   pyinstaller 南网协议解析工具.spec --noconfirm
   # 3. 在 dist/ 下验证带版本号+时间戳的 exe 文件生成
   ```

   - **`协议解析工具_onedir.spec` 的 exe 名必须叫 `协议解析工具`** —— 与 `南网解析工具.iss`
     的 `MyAppExeName` 绑定；改名会让安装包找不到源文件。
   - 杀软/SmartScreen 拦截的成因、申诉入口、签名选型与稳定性清单见
     [`docs/anti_virus_and_signing.md`](docs/anti_virus_and_signing.md)（**别指望元数据能解误报**）。
   - 本机构建被实时防护打断时（会造成产物缺文件 → 随机崩溃）：
     `python scripts/defender_exclude_build.py --add`（只放行 `dist\` 与 `build\`，需管理员）。

4. **版本号管理**：
   - `APP_VERSION`：功能版本号，仅在有功能变更时更新；是 exe 文件名、文件属性、窗口标题的唯一版本源
   - `BUILD_DATE`：编译日期，每次打包前必须更新
   - 两者共同构成完整版本标识，便于区分不同时间编译的版本

5. **`EXE(...)` 的清单与 UPX 两条硬约束（2026-09-30 起，别改回去）**：

   - **`manifest=` 传的必须是完整清单**：PyInstaller 的 `winmanifest.create_application_manifest()` 是**整份替换**而不是合并（它只额外保证 `requestedExecutionLevel` 与 `Microsoft.Windows.Common-Controls` 两项）。第一版只传了 `<assemblyIdentity>`，结果把默认清单里的 `supportedOS`（5 个）与 `longPathAware` **一起冲掉**——`longPathAware` 丢了会让 >260 字符路径失效，属实打实的回归。现在 spec 里写的是一份**完整清单**（assemblyIdentity + trustInfo/asInvoker + compatibility/5×supportedOS + longPathAware + Common-Controls），只比默认多一条 `assemblyIdentity`（"谁家的什么软件什么版本"这条汇编层身份，默认清单没有它）。
     - 校验方法（改完必做）：构建后在产物里搜 `<assembly` 取出清单，逐项确认 `assemblyIdentity` / `requestedExecutionLevel` / `longPathAware` / `Common-Controls` / `supportedOS`(应为 5 条) **全部为 True**。
     - 特意**不**声明 `dpiAware` / `dpiAwareness`：高 DPI 缩放由 Qt 启动时自己设置，清单里再声明一次会改变现有缩放行为（本项目有大量高 DPI 布局适配）。
   - **`upx=False`（显式关闭）**：UPX 压缩壳是杀毒启发式的重点特征（"自解压 + 加壳"与恶意软件同构）。本机 `PATH` 上只有 `upx.BAT`，PyInstaller 未认定其可用（构建日志没有 `UPX is available` 那行、产物里 `UPX!` 标记 0 处），所以**历史上并未真的压过**；写死 `False` 是为了去掉"以后 UPX 变得可用就静默启用"的隐患。
   - 与之配套的版本资源补了 `Comments`（用途说明），`CompanyName`/`FileDescription`/`InternalName`/`LegalCopyright`/`ProductName` 保持原样。

6. **杀毒误报的现实边界（重要，别指望元数据能解决）**：上面的清单/元数据只让 exe "看起来像正规程序"，**不是**误报的解药。本程序被拦的实际主因依次是：①**没有代码签名**（无发布者、零信誉）；②**onefile 自解压**——每次运行解到 `%TEMP%\_MEIxxxxx` 再执行，与"释放器"行为同构；③**每次重建哈希都不同**（文件名带时间戳），云信誉永远从零开始。真正有效的顺序：**代码签名**（OV/EV 证书或 Azure Trusted Signing）> **改 onedir**（安装脚本 `南网解析工具.iss` 取的就是文件夹形态 `dist\协议解析工具\协议解析工具.exe`，但该目录已停更在 2026-08-11、当前没有任何 spec 会重新生成它）> 向微软提交误报 > 本机加 Defender 排除项。

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
├── production_testbench_core.py # 生产测试架纯逻辑（无 Qt，1.23.88）：FieldSpec/FIELD_GROUPS 字段表（界面与组帧单一来源）、75 字节组帧、checksum8、HEX/ASCII、配置合并与原子写
├── testpage_render.py          # 测试页四列文本渲染单源（纯逻辑无 Qt，1.24.1）：CJK 宽度/截断/
│                               #   format_table_rows；698 与 645 测试页共用（禁止第二份）
├── channel_link.py             # 协议测试页的串口/蓝牙双通道控制器（Qt，无协议细节，1.24.1）：
│                               #   ChannelController（rx 分流 / ready / send 超限预检 / 状态文案）+
│                               #   BleSendPort（BluetoothWorker → 整帧一次 ATT 写）；
│                               #   698/645 两个「协议测试」页共用（升级页另有一套，见 §8 陷阱 92）
├── atomic_io.py             # 原子写（纯标准库，1.23.89）：tmp+fsync+os.replace，失败保留旧文件；main_gui 的 config.json 全部走它
├── diagnostics.py           # 诊断包（无 Qt，1.23.89）：环境信息 + 配置（递归脱敏）+ 日志尾部 → zip，入口在帮助菜单
├── crash_handler.py         # 崩溃兜底（1.23.90）：sys/threading excepthook → logs/crash_*.log（保留 20 份）
├── wakeup_prefix.py          # 68 家族前导 FEH 唤醒字节单源（1.23.76）：判定/剥离/表格前导行/偏移位移；
│                             #   协议8（§6.3.1 b）与协议6（§5.3.1）的解析器·校验器共用，其余协议禁止引用（见 §8 陷阱 75）
├── frame_deframe.py          # 串口分帧族单源（1.23.85 抽出，纯逻辑无 Qt）：68 家族 L+2 / 末字节 16H 自证 / 前导 FEH 容忍、
│                             #   HDLC 7EH 定界、645、DLMS Wrapper 判据 + 策略常量；`serial_tool_widget` 只做同名 re-export（见 §8 陷阱 77）
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
│   │   └── dl_t698_45_upgrade.py   # 文件传输升级纯逻辑（OI 0xF001：启动传输/写文件/执行升级组帧、分包、确认判定；1.23.85 起）
│   ├── csg_new_gen_parser.py       # 新一代载波 (CSGNewGenParser) ~4970行
│   └── csg_new_gen_cmd_payloads.py # 应用层命令业务数据单元解析
├── gw_new_gen_parser.py        # 国网新一代双模 (GWNewGenParser) — 国网新一代双模通信互联互通
│   ├── gw_new_gen_mme_parser.py  # 国网新一代 MME 管理消息解析（关联/代理变更/发现列表/诊断等）
│   └── gw_new_gen_cmd_payloads.py # 国网新一代应用层命令载荷解析
├── hdc10_parser.py            # HDC 1.0 双模互联互通 (HDC10Parser) — Q/GDW 12087.42-2020
│   └── hdc10_mme_parser.py    # HDC 1.0 MME 网络管理消息解析（关联/发现列表/时隙分配等）
├── modular_iface_parser.py    # 模组化终端功能模块接口 (ModularIfaceParser) — 链路+APDU+DT
│   └── modular_iface_axdr.py     # A-XDR 编解码单源（表4 类型/8 类 APDU/date_time/Scaler_Unit/fcstab/verify_frame）
│   └── modular_iface_data.py     # 静态表单源（附录 B/C/D~L/M + 表1/2/3/5/11/13；DT 命名/单位/子接口）
├── modular_iface_frame_gen.py # 模组化组帧（整帧/ACK/NAK/APDU 模板，纯逻辑）
├── yw645_parser.py            # 依瓦定制645 (YW645Parser) — 协议13
│   ├── yw645_wire.py          # 依瓦定制645 线格式单源（地址/12bit 长度/CS/±0x33/切帧）
│   ├── yw645_di.py            # 依瓦定制645 数据项表（附录A）
│   └── yw645_frame_gen.py / yw645_frame_gen_widget.py  # 组帧逻辑 / 组帧页
├── csg_uplink_parser.py       # 南网上行通信规约 (CSGUplinkParser) — 协议14 Q/CSG 11109004-2013
│   ├── csg_uplink_wire.py     # 线格式单源（68H+L(2B小端)×2+68H+C+A+CS+16H / 地址域 / 切帧）
│   ├── csg_uplink_di.py       # AFN/数据密度/错误码 + DI 索引单源
│   ├── csg_uplink_di_data.py  # DI 数据表（tools/gen_csg_uplink_di.py 从 PDF 抽取的生成物）
│   └── csg_uplink_frame_gen.py / csg_uplink_frame_gen_widget.py  # 组帧逻辑 / 组帧页
├── modbus_parser.py           # Modbus (ModbusParser) — 协议15 RTU/TCP
│   ├── modbus_core.py         # 帧层/PDU 层解析单源（RTU CRC16 / MBAP 识别、功能码、寄存器映射、批量切帧）
│   ├── modbus_register_store.py  # 寄存器列表配置 modbus_registers.json（读写/校验/导入导出/选中项）
│   └── modbus_register_widget.py # 寄存器列表管理对话框 + 查询页浏览面板
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
│   ├── preset_buttons.py           # 预设命令按钮 (PresetButtonWidget / PresetButtonManager / AddPresetDialog)
│   │                               #   + 页面「添加命令」可直接粘贴报文建按钮（editable_frame 模式）
│   │                               #   + 「一键批量替换地址」按当前协议改全部预设并重算校验（复用 frame_addr_fix /
│   │                               #     message_tool_widget.replace_frame_address；1.24.1 起）
│   ├── test_plan_widget.py         # 测试计划 (TestPlanWidget) - CRUD/顺序发送/超时/结果
│   ├── serial_worker.py            # 串口通信线程 (SerialWorker)
│   ├── gui_utils.py                # 中文右键菜单等工具
│   ├── lookup_pages.py             # 简化版查询页（当前无调用方；create_di_lookup_page 的自定义DI增删与 main_gui 共用 custom_di_store）
│   ├── app_icons.py                # 图标加载（icons/lucide/*.svg；按钮/窗口图标）。load_icon 跟随主题前景色；
│   │                               #   render_pixmap(name, size, color) 按**指定颜色**渲染（状态灯：绿=连接/灰=断开）
│   ├── canvas_theme.py             # 自绘画布配色单源（纯逻辑无 Qt）：bg/bg_alt/border/text/muted/hint/line/highlight/hover，
│   │                               #   深浅各一套。QSS 管不到 QGraphicsView 场景、paintEvent、QTextCharFormat 的默认前后景
│   ├── thread_registry.py          # QThread 登记表（新增 QThread 必须 track；_shutdown_threads 兜底回收依赖）
│   ├── auto_updater.py             # 自动升级：版本比对/下载/update.bat 替换编排（纯逻辑无Qt；配置在 config.json update 段）
│   │                               #   更新源默认 **GitHub Release**（owner/repo 由 AUTHOR_GITHUB_URL 解析注入，单一来源）；
│   │                               #   另支持 Gitee / 私有 HTTP；GitHub 资产 digest→sha256、body=更新说明（1.23.87 起）
│   ├── update_dialogs.py           # 升级对话框：版本列表+更新说明面板 / 「发现新版本」确认（markdown 渲染；不发网络请求）
│   ├── update_download_dialog.py   # 下载面板（非模态，1.23.95 / 1.23.96 加固）：逐线程进度表 + 实时速率 + 剩余时间；
│   │                               #   暂停/继续/取消并清理缓存/后台运行（不做网络 IO，快照由 worker 喂入）
│   ├── downloader.py               # 多线程分段下载器（纯逻辑无 Qt，1.23.95）：Range 分段 + 最多 32 线程并发 +
│   │                               #   断点续传 + 暂停/取消 + 不支持 Range 时回落单流；只写 .part，合并后才落目标文件
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
│   ├── message_tool_widget.py       # 报文工具标签页 (MessageToolWidget) - ASCII/HEX转换/CRC/校验；
│   │                                 #   数值⟷HEX（698.45/A-XDR 12 种基础类型，**两个方向**都同时给大端/小端；
│   │                                 #   纯逻辑 `encode_numeric_value` / `decode_numeric_value` 严格互逆，
│   │                                 #   字节宽度与 dl_t698_45_axdr 一一对应；1.23.60 起 / 1.23.62 补 HEX→数值）；
│   │                                 #   **地址替换**（粘贴任意一帧 + 选协议 → 替换地址域 + 重算校验，第四次复用
│   │                                 #   `frame_addr_fix`：纯逻辑 `replace_frame_address` / `addr_field_errors`，
│   │                                 #   前导 FEH 只对协议 6/8 剥离并恢复；见 §8 陷阱 69、component-guidelines §7l）
│   ├── spectrum_widget.py           # 频谱图标签页 (SpectrumWidget/SpectrumCanvas) - 频谱仪参数 + trace 数值 → 仪器式网格频谱图；光标读数/MARK标记/两点Δ测量/峰值搜索/**功率谱密度 PSD 视图**（`psd=True`：PSD = 幅值 − 10·log10(RBW)，RBW 必填）+ 导出PNG（常驻，与协议无关；1.23.9 起，PSD 于 1.24.3 追加）
│   ├── production_testbench_widget.py # 生产测试架页 (ProductionTestbenchWidget) - 类串口助手：5 条发送配置（各自 HEX/ASCII + checksum8 三种落位）+ HEX/ASCII 日志/时间戳 + 测试架参数帧（49 项，改动即组帧）；常驻、懒加载、复用共享串口（1.23.88 起）
│   ├── feedback_dialog.py           # 问题反馈对话框 (FeedbackDialog) - 帮助菜单入口，提交到 Web 服务端共享 feedback.db（1.20.0 起）
│   ├── github_issue.py              # GitHub Issue 提交纯逻辑（无 Qt，1.23.94）：建单 payload（段标题对齐 bug.yml 表单）/ REST 建单（含 422 去标签重试）/
│   │                               #   浏览器兜底预填 URL（按表单字段 id）/ 令牌优先级（显式>环境变量>config.json）/ 崩溃摘要本机路径脱敏
│   ├── github_issue_dialog.py       # GitHub Issue 反馈对话框 (GitHubIssueDialog) - 帮助菜单「提交问题到 GitHub」+ 崩溃弹窗一键提交；
│   │                               #   API 直连（真自动）与浏览器预填（免令牌）双通道，自动带入当前协议/最近报文 hex/运行环境（1.23.94 起）
│   ├── share_dialog.py              # 报文分享对话框 (ShareDialog) - 单帧解析「分享此帧」，JSON POST /api/frameshare（1.21.0 起）
│   ├── enhanced_export.py           # 增强导出功能 (EnhancedBatchResultExporter) - Excel/CSV/TXT/JSON
│   ├── theme_settings.py            # 主题与字体设置 (ThemeManager + ThemeSettingsDialog) - 7套主题(含Win11云母Mica)/QSS/字体持久化
│   ├── meter_sim_widget.py         # 虚拟表 tab (VirtualMeterWidget) - 698.45 从站模拟器（离线/串口从站，仅协议8，1.16.0 起）
│   ├── dlt698_upgrade_widget.py    # 「光伏升级」tab (Dlt698UpgradeWidget) - 协议8 文件传输升级（拖入升级包/分包/逐包确认/进度，
│   │                               #   可选升级前/后读版本信息：通用 OAD 43000300 / 厂家扩展内部版本 FF100400 二选一，失败不阻断；
│   │                               #   可选「提升波特率」（仅串口）：升级前发 FT1.2 命令 → 静态等待后主机切 115200，传完切回 9600；
│   │                               #   升级后读版本在 9600/115200 上各试一遍（设备升级失败可能仍停在 115200），都读不到才算读不到；
│   │                               #   升级前/后版本**自动比对判定**：变了=升级成功、完全一致=升级失败、缺证据=无法判定；
│   │                               #   升级包**路径落盘**：重开程序直接显示上次的文件，换新文件才更新（文件没了不恢复、也不删记录）；
│   │                               #   仅协议8 可见；复用共享串口 write_raw + raw_data_received，惰性 import crcmod 依赖，1.23.85 起）
│   ├── meter_sim/                  # 虚拟表核心逻辑包（纯逻辑无 Qt，1.16.0 起）
│   │   ├── archive.py              #   档案 meter_sim_data.json（194 OI，app_paths 持久化）
│   │   ├── link_layer.py           #   68...16 帧提取（粘包/分片/FE前缀）+ 帧头解析
│   │   ├── response_builder.py     #   Get-Response Normal/NormalList/Record、链接、安全MAC封装；复用 DLT69845FrameGenerator
│   │   ├── dynamic_data.py         #   时间/地址/电能量递增/冻结时标/漏点
│   │   └── engine.py               #   MeterSimEngine.handle_frame(frame) -> 0..n 响应帧
│   ├── dlt645_meter_sim_widget.py  # 645虚拟表 tab (Dlt645VirtualMeterWidget) - 645 从站模拟 + LME 主站下发（仅协议6，1.23.5 起）
│   ├── dlt645_test_widget.py       # 645协议测试 tab (Dlt645TestWidget) - 仅协议6（1.24.1 起）：
│   │                               #   表地址/读·写地址/广播校时 + 读数据·写数据·特殊命令三页 + DI 大类树
│   │                               #   + 勾选顺序下发（等应答再发下一条）+ 收发日志 + 信息表/报文表
│   ├── dlt645_test_core.py         #   ↑ 纯逻辑（无 Qt）：catalog() DI 大类树 / command_groups() / 组帧
│   │                               #   （全走 DLT645FrameGenerator）/ evaluate_response() 判定
│   ├── dlt645_sim/                 # 645虚拟表核心逻辑包（纯逻辑无 Qt）
│   │   ├── archive.py              #   档案 DI→可读值（dlt645_sim_data.json 持久化）
│   │   ├── dynamic_data.py         #   动态数据：RandomEventWord 事件状态字随机源（04001501，1.23.8 起）
│   │   ├── engine.py               #   从站引擎 handle_frame：11H 读档案 / 13H 读通信地址 / 15H 写通信地址 / 08H 校时 / 其余 DnH 异常
│   │   └── lme_query.py            #   LME 自定义下发组帧 4.2/4.6/4.7（模块版本查询，1.23.7 起；复用 DLT645FrameGenerator + DLT645Parser）
│   ├── monitor_widget.py            # 实时监控器 (RealtimeMonitorWidget) - 串口原始字节流自动组帧/CSV记录
│   ├── monitor/tcp_monitor.py       # TCP流量监控 (TCPMonitorWidget) - scapy抓包/流重组/自动解析
│   ├── serial_worker.py             # 串口后台线程 (SerialWorker) - 打开/读取/FT1.2+645 分帧/发送（write_raw 静默写，供高速发送；set_baudrate 运行中热切换波特率：先 flush 再改 DCB、不关端口，1.23.86 起）
│   ├── serial_tool_widget.py        # 串口工具 (SerialToolWidget) - 命令表循环发送 + 响应匹配 + 统计 + 按协议断帧解析 + 断帧设置（可调超时/断帧方式，认前导 FE）
│   │                                #   + 日志自动保存到文件 + **批量替换通信地址**（按协议替换地址域+重算校验+撤销，复用 frame_addr_fix；纯逻辑 `batch_fix_commands`，1.23.83）（集成自 USB 负载测试工具）
│   ├── bluetooth_core.py            # 蓝牙纯逻辑（无 Qt / 无 bleak）：配置持久化（原子写+坏文件宽容）、按 MTU 分包、BleReassembler 静默超时切帧、
│   │                                #   特征码打分优选 / ProbeSession 探测状态机 / 按设备地址记忆 char_map（1.23.79）/ 按钮的 protocol+addr 参数（1.23.81）
│   ├── frame_addr_fix.py            # 按协议替换地址域 + 重算校验（纯逻辑，无 Qt；**按需导入**协议模块 —— 698 依赖可选 crcmod）：
│   │                                #   字段声明 fields_for / parse_address（在线 hex 与协议书写序双认）/ apply（自证→定位→替换→复用协议实现重算）
│   │                                #   v1 支持 0/6/7/8/13/14；地址定位与校验全部复用既有实现（见 §8 陷阱 69）（1.23.81）
│   ├── bluetooth_worker.py          # 蓝牙通信线程 (BluetoothWorker, QObject + 私有 asyncio 事件循环) - 扫描/连接/特征码枚举/订阅/写/重组；
│   │                                #   含 subscribe_finished（探测时序依赖）+ MTU/写上限实时化（1.23.80：连接后轮询协商结果 + 每次发送前重读）
│   ├── bluetooth_tool_widget.py     # 蓝牙工具 (BluetoothToolWidget) - 扫描连接 + 特征码自动优选/一键探测/按设备记忆 + 收发解析 + 自定义报文按钮（可绑协议+地址）
│   │                                #   + 虚拟串口透传（集成自蓝牙转串口工具02）；右栏「日志 ↔ 发送+自定义」为竖向 QSplitter，
│   │                                #   自定义区 = CollapsibleSection + ButtonScrollArea（高度按内容自动 + 工具栏常驻，1.23.82）；
│   │                                #   工具栏 6 个按钮（含「批量地址…」= 按协议类别批量替换 / 清除地址，1.23.84）
│   ├── system_integration/          # 系统集成包（Windows）
│   │   ├── sys_tray.py              #   系统托盘（关闭最小化/显示隐藏/自启/退出 + **菜单内嵌报文输入框**，1.23.85）
│   │   ├── taskbar_buttons.py       #   任务栏**缩略图工具栏按钮**（悬停图标预览里 3~5 个可点按钮；纯 ctypes 调
│   │   │                            #   ITaskbarList4/3（Win11 只认 4！）+ QImage→HICON + WM_COMMAND 拦截，1.23.85）
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
│   └── yw645_validator.py          # 依瓦定制645 (YW645Validator) - 起始符/CS/±0x33/DI 命中
│   └── csg_uplink_validator.py     # 南网上行通信规约 (CSGUplinkValidator) - 68H×2/L/C/A/AFN/CS/16H
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
├── ruff.toml / .pi-lens.json     # 工具链配置（2026-09-17）：ruff 只启用 pyflakes（F）规则；
│                                 #   pi-lens 关闭自动格式化/自动修复（只报诊断、不改写文件）——见 §8 陷阱 46
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
- **位域数据标识（主动上报状态字/模式字，1.23.23 起，国网第4号补遗）**：
  - DI `04001501` 主动上报状态字（BS96 / 12 字节，其后每字节为「主动上报事件N新增次数」）、`04001503` 复位主动上报状态字（BS96）、`04001104` 主动上报模式字（BS64 / 8 字节）
  - **位表（96 位 / 64 位）只在 `dlt645_data_codec.py` 定义一处**：`REPORT_STATUS_BITS` / `REPORT_MODE_BITS` / `_format_bits` / `decode_report_status_word` / `decode_report_mode_word`；桌面 `protocol_registry.DLT645GuiParser`、Web `_safe_parse_to_table`、645 虚拟表共用（**不要再新增第二份清单**）
  - **字节序低字节在前**：第 n 字节承载 Bit(8n)~Bit(8n+7)，字节内 Bit0 为最低位（由补遗自带三示例自证）
  - **语义**：模式字 1 = 该事件允许主动上报（使能）；状态字 1 = 该事件已发生；**两表存在不变量 状态字 Bit(32+n) ≡ 模式字 Bit(n)（n=32..63）**
  - **「电表运行状态字 1~7」位号已于 1.23.23 修正**（原表 8 个字无一正确，且状态字3 的「供电方式」实为 Bit2~Bit1 两位域）；详见 §8 陷阱 50
- **校验器**：`validator/dlt645_validator.py`
- **STA 硬件初始化（复位）命令（1.24.9 起）**：`68 AA AA AA AA AA AA 68 14 0C … DA 16`（14H 写数据，DI `04A00401`，密码 `00370AA0`，操作者 `00000000`）—— 模组固定在工装底座无法断电时用它代替上下电。统一实现在 `sta_reset.py`（645/698 两个虚拟表共用，`build_frame()` 与现场帧逐字节一致）；虚拟表收到后：**广播 → 静默 + 中文日志**（旧实现会回 D4H 异常帧），单播 → 94H 正常应答。两个虚拟表页面各有「被测模组复位」下发按钮；回归 `test/test_sta_reset.py`
- **前导 FEH 唤醒字节（1.23.76 起）**：§5.3.1「在主站发送帧信息之前，建议先发送 4 个字节 FEH，以唤醒接收方」⇒ `parse` / `check_structure` / `check_frame` / `calc_checksum` 与校验器统一**先剥离帧首连续 `0xFE`** 再判定（单一来源 `wakeup_prefix.py`），`DLT645GuiParser` 表格首行给「唤醒前导字节」且其余行偏移整体 `+skip`；详见 §8 陷阱 75
- **参考文档**：
  - `DLT645-2007.md` — 主协议（Markdown）
  - `DLT645-2007 多功能电表通信协议.pdf` — 原始 PDF
  - `国网计量中心电能表全性能试验检测公告-第4号补遗-事件记录采集-远程费控功能和负荷曲线抄读功能.pdf` — 补遗（PDF，需用 pdf skill 检索）
  - `协议文档/6.645协议/附件1：协议转换单元【低压分布式光伏协议转换单元】-技术规范书0625.md` — **光伏协议转换单元 DL/T645-2007 扩展协议**（§D.1 三张 DI 表：变量 `02E6xxxx`/参数 `04E6xxxx`/事件 `03E6xxxx`；附录 I.3.3.1 扩展控制码 `0FH`/`8FH` 透传帧。1.23.21 起支持解析，原 `.docx` 同目录）
  - `协议文档/6.645协议/南网光伏协议转换单元无线接口手册-V1.6.md` — **无线模组接口扩展**（LME V1.6 / 2026-10-08，由同名 PDF 转换）：`02EB0000` 逆变器数据转发（波特率特征字 / 校验 / **超时 T 为 BCD**）、`04E60001` 地址列表（`1+6×M`）、`04E60002` 无线频段、`04900100` 拓扑、`04900101~04900106` 升级、`04900107` 版本、`028100FF` 在网状态；控制码扩展 `86H/06H`（上报 / 确认）、`1EH/9EH`（在网状态）、`D1H`（转发异常，`ERR=0x80` = 未入网）。解析在 `dlt645_pv_wireless.py`，**优先于**附件1 接管 `04E60001`（见 §8 陷阱 88）
- **「645协议测试」页（1.24.1 新增，`has_dlt645_test`，仅协议6 可见）**：与协议8「协议测试」页同构，
  但分类维度是 **DI 前缀**而不是 OI：
  - `dlt645_test_core.py`（纯逻辑无 Qt）—— `catalog()` 顶级按 DI3（`00` 电能量 / `01` 需量 / `02` 电压·电流 /
    `03` 功率·功率因数·谐波 / `04` 参变量 / `05` 结算日电能 / `06` 记录 / `07` 冻结次数 / `FF` LME），
    子类按 DI2（`05` 的 254 个结算日按 20 天分桶）；`02E6/03E6/04E6`（光伏）抽到独立顶层「光伏扩展」。
    **判定光伏必须同时看 DI3**：`05E6xxxx` 是第 230 个结算日，只看 `DI2=="E6"` 会把它误判成光伏。
  - 组帧一律 `DLT645FrameGenerator.generate_frame((REQ, func), fv, addr)`；特殊命令的字段直接取
    `DLT645_CMD_SCHEMA`（13H/15H 的地址域固定 `AA×6`、08H 固定 `99×6`，页面表地址对它们无效）。
  - 判定 `evaluate_response()`：结构/校验 → 方向位 D7 → 功能码 → 异常位 D6（`decode_err` 位解释）→
    DI 回显 → 取值（`decode_value`）。**不冒充成功**；08H 广播校时记「已发送」而不等应答。
  - 四列文本渲染与 698 共用 `testpage_render.py`（**唯一实现**，不要再写第二份）。
  - 两处 DI 表既有瑕疵（**只做展示、不改表**）：`dlt645_di.json` 中 16 条 `0090xxx0` 是 7 位残键
    （与标准 `0090xxxx` 同名重复，`malformed_di_keys()` 暴露，不进树）；`04000101 日期` 声明 length=4
    而标准/编码器是 3 字节（`length_warning` 会给提示但**不阻断**）。
  - `dlt645_frame_schema._value_or_raw` 1.24.1 起认「日期/时间/通信地址/位串内容/数据内容」这些
    **掩码推导字段名**（此前只有「写入数据/数据值」能触发编码，导致日期类 DI 的 14H 帧组不出来）。
  - **发送通道（1.24.1 起）**：与 698 测试页共用 `channel_link.ChannelController`（串口/蓝牙、
    整帧一次 ATT 写、超限报错、两通道 RX 不串味、通道落盘）；蓝牙连接归「蓝牙工具」页。
  - **光伏无线扩展（手册 V1.6，1.24.1 起）**：树末尾有「光伏无线扩展（V1.6）」分类，12 条 DI
    （`02EB0000` / `04E60001~2` / `04900100~107` / `028100FF`）**直接取自 `dlt645_pv_wireless.WIRELESS_DI_MAP`**
    （不要再手写一份）；`02EB0000` 与 `FF00DD01` 的**读请求**要带数据域（`read_request_fields()` →
    `build_read(..., field_values=)`，字段同源 `build_di_fields`），`028100FF` 手册口径是 `1EH/9EH`
    （测试页仍可发 11H 读，备注里写明）；无线应答的摘要用 `parse_wireless_di` 行解码。
    `04E60001` 与附件1 重叠时**以无线手册为准**（只挂在无线分类，光伏参数剩 171 条）。
  - 回归：`test/test_dlt645_testbench.py`（**106** 项，含 [4b] 双通道段）+
    `test/test_dlt645_test_tab_wiring.py`（**20** 项，能力位/tab 显隐/懒加载/串口·蓝牙注入/cleanup）。

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
- **前导 FEH 前导码（1.23.76 起，规范 §6.3.1 b)）**：链路帧允许（本协议标准为「要求」）在帧前带 `FEH` 前导码 ⇒ `DLT69845Parser.parse` / `parse_to_table` 与 `DLT69845Validator` 统一**先剥离帧首连续 `0xFE`**（单一来源 `wakeup_prefix.py`），`原始数据` 保留用户原始输入（含 FE），表格首行给「唤醒前导字节」且其余行偏移整体 `+skip`；详见 §8 陷阱 75
- **参考文档**：`面向对象的用电信息数据交换协议(20210910).md`
  - **帧长公式（1.23.61 修正；三处实现曾错，改前必读）**：`L` 是「传输帧中**不包含**起始字符和结束字符的数据长度」（6.2.2 a)，L 本身含两个长度域字节）⇒ **整帧 = `L + 2`**；真实链路帧**没有第二个 68H**（`68 | L(2B 小端) | 控制域 | SA | CA | HCS | APDU | FCS | 16`）。自证：附录 H.1.1「登录」示例 32 字节、L=0x001E=30。批量提取（`main_gui._extract_69845_frames` / `batch_core._extract_69845_frames` / `reflex_web.web_utils.extract_69845_frames`）与串口分帧（`serial_tool_widget` 的 `dlt698_45` 策略）都必须按 `L + 2`；因南网/国网与 698.45 前 3 字节同形（`68 L L`），三者互斥只能靠**末字节自证**（南网/国网 L = 整帧、末字节恒 16H）。回归：`test/test_dl_t698_45_extract.py`
  - **CRC 范围**：文档明确定义 HCS/FCS 各自覆盖的字段，**哪些字段参与 CRC 必须查文档**
  - **A-XDR 编码**：APDU 内部所有数据用 A-XDR，tag 高 3 位 = 010
  - **两层字节序（1.23.63 修正；改任何 `dl_t698_45_*.py` 多字节字段前必读）**：链路层——长度域 `L`(2B)、HCS(2B)、FCS(2B)、地址域反转——按**小端**（协议文档 L347「链路层传输顺序为低位在前…低字节在前，高字节在后」）；APDU 内的 A-XDR 数据域**全部多字节字段按大端**（§7.1：APDU 编码规则遵循 A-XDR，详见 DL/T 790.6—2010）。**两层不可互相套用**；`int.from_bytes`/`struct` 必须显式写端序。判据 oracle（协议文档**附录 H.1.1「登录」**逐字节示例）：`00 B4`=心跳周期 **180s**、`07 E0`=**2016** 年、`00 A4`=**164**ms、`02 5F`=607ms、`02 DA`=730ms（按小端读会全错）。回归：`test/test_dl_t698_45_endian.py`
- **文件传输升级（OI `0xF001` 文件分块传输管理，1.23.85 新增）**：
  - **三步命令**（均为 `ACTION-Request Normal` `07 01`，`param` 末尾**必须补 `00`**=TimeTag 无）：① 启动传输 OMD `F0 01 07 00`，param = `structure{文件信息, 传输块大小 CHOICE{[18] u16 短帧 / [6] u32 长帧}, 校验 structure{类型 enum{CRC(0)/md5(1)/SHA1(2)}, 值 octet-string}}`；② 写文件 OMD `F0 01 08 00`，param = `structure{块序号 u16 大端, 块数据 octet-string}`，**每包一帧、逐包等确认**；③ 执行升级 OMD `F0 01 0D 00`，param = `structure{执行升级时间 date_time_s（全 FF=立即执行）, 软件许可 CHOICE{NULL[00], License[09] octet-string}}`
  - **文件信息**（表188 属性2）= `structure{源文件 visible-string, 目标文件 visible-string, 文件大小 double-long-unsigned, 文件属性 bit-string(SIZE(3)), 文件版本 visible-string, 文件类别 enum{当前设备文件(0)/其他设备文件(1)}}`
  - **逐字节 golden**（`协议文档/8.698.45协议/代理升级流程.docx`，SA=单地址/6B/书写序 `075506980033`）：启动传输 = `68 3C 00 43 05 33 00 98 06 55 07 00 3C 7F 07 01 00 F0 01 07 00 02 03 02 06 0A 00 0A 00 06 00 04 35 63 04 03 E0 0A 04 76 31 2E 30 16 00 12 07 D0 02 02 16 00 09 04 7F 7E D9 D2 00 54 24 16`（62 字节，字段：文件大小 275811、属性 `E0`、版本 `v1.0`、块大小 2000、校验 CRC `7F7ED9D2`）；响应 `68 1A 00 C3 … 87 01 00 F0 01 07 00 00 00 00 00 AE 11 16`。`test/test_dl698_upgrade.py` A1/A3 断逐字节相等（含 HCS/FCS）
  - **落点**：`dl_t698_45_upgrade.py`（纯逻辑：分包/组帧/确认判定/校验值/读版本，零 Qt）+ `dlt698_upgrade_widget.py`（「**光伏升级**」页，仅协议8 可见）+ `frame_deframe.py`（698 分帧单一来源，见陷阱 77）；页面只用**共享串口**（`write_raw` 发送、`raw_data_received` 收，见陷阱 77）
  - **可选「读版本信息」两步（1.23.85 追加）**：`升级前读版本信息`/`升级完成后读版本信息`（默认**不勾**、落盘、传输中冻结）→ 状态机 `ver_pre`/`ver_post` 阶段；帧 = `build_read_version(sa, ca, piid, oad=…)`（GET-Request Normal + TimeTag `00`；SA/CA 取页面配置）；判定 = `check_get_response(frame, oad)`；**失败不阻断升级**（重试用尽则记日志继续）
  - **全部块确认后先校验「传输块状态字」（F001 属性4）才允许执行升级（1.24.2 新增，禁止跳过）**：
    最后一块的确认**不再**直接发执行升级，而是进入 `PHASE_STATUS`（`_begin_status_gate()`）→ GET-Request Normal
    `05 01 <PIID> F0 01 04 00 00`（`dl_t698_45_upgrade.build_read_block_status(sa, ca, piid)`，与读版本共用组帧）。
    判定 `check_block_status(frame, blocks)`：DAR 必须 0、bit-string **位数 ≥ 本次块数**、**位序兼容 MSB-first 与 LSB-first**
    （命中 LSB 时日志给「已按反向解释」警告，两种都放行但**不静默**）、缺块 / 位数不足 / 超出块数的补位被置 1 / 多报块
    一律 `ok=False` 并点名**缺哪一块（1-based）**。**不通过 ⇒ 按既有超时/重试口径重试状态字请求**（不重传数据块、更不冒充成功）；
    重试用尽 ⇒ `failed`，且**一帧执行升级都不发**。只有状态字通过后，勾了自动执行才发执行升级；没勾则进 `PHASE_WAIT_RESET`
    （随后可读升级后版本）。日志在进入闸门与通过时各给一行 `[信息]`（含块数与位序）。
    回归：`test_dl698_upgrade.py` A15（组帧 golden + 位序/缺块/位数/补位/DAR/OAD/ACTION 矩阵）、
    `test_dl698_upgrade_gui.py` 全流程（`run_to_end` 已认该阶段）；**块数口径单一来源仍是 `_num_blocks()`**。
  - **「升级完成后读版本」与「是否发执行升级命令」解耦 + 读前先等设备复位（用户纠错追加）**：勾了自动执行 ⇒ 执行升级确认后读；**没勾** ⇒ 最后一包写文件确认后读（有的设备收全包会**自动复位升级**）；两种情形都先走 `PHASE_WAIT_RESET`（「升级后等待(s)」默认 **10 秒**、0~600 可改、落盘，1 秒重复 QTimer 倒计时、状态行显示 `等待设备复位（剩余 N 秒）`，0 秒则立即读）。等待期间状态仍是 `finishing`（不新增 `STATE_*`）、收到的帧记 `忽略（等待设备复位中）`；`中止`/`清除`/`cleanup()`/`_finish_buttons` 都要停这个定时器。**`_retry_or_fail` 必须有等待期守卫**（独立复核 F1 实测）：等待期若被误触发超时槽（`QTimer.stop()` 不撤已投递的 timeout 事件 ⇒ 真实竞态），放行会按 `_expected_omd()` 落到 `OMD_EXEC` **凭空发出「执行升级」帧**（用户可能根本没勾它），重试用尽还会把等待误判成失败 ⇒ 等待期直接忽略超时/重试（记一条 warn）。回归：`test_dl698_upgrade_gui.py` [22]
  - **「读版本内容」两条命令**：通用 `OAD 43 00 03 00`（OI 0x4300 属性3）与**厂家扩展内部版本** `OAD FF 10 04 00`（OI 0xFF00 起的厂商自定义区间，解析器标「未知对象(0xFF10)」）。OAD 字节**只在协议模块一份**（`OAD_VERSION`/`OAD_INTERNAL_VERSION`，页面经 `_read_oad()` 取）；组帧与判定都按所选 OAD ⇒ **两条命令的响应互斥**。两条现场实帧均逐字节复现：read-version 通用 = `68 17 00 43 05 AA×6 00 AA 2A 05 01 01 43 00 03 00 00 6D 5C 16`、内部 = `68 17 00 43 05 03 24 08 04 26 20 00 CD 9A 05 01 2C FF 10 04 00 00 C2 8A 16`（`generate_get_request_normal` 的 TimeTag 走**新增可选参数** `time_tag_none`，默认不补 ⇒ 既有调用方逐字节不变）
  - **tab 标题 = 「光伏升级」**（1.23.85 改名；索引仍是 `_upgrade_tab_index`、能力仍是 `spec.has_upgrade`；改名必须同步 `test_dl698_upgrade_tab_wiring.py` 与 `test_yw645_gui.py` 的文案断言）
  - **发送通道：串口（默认）/ 蓝牙（1.23.85 追加）**：蓝牙通道**复用「蓝牙工具」页的连接**（升级页经 `main_gui._upgrade_bluetooth_source()` 注入的取值回调拿 worker，不建不断连接）；发送走 `_BleSendPort` → `worker.send_data(frame, single_write=True)`（**整帧一次 ATT 写**，超限由 worker 拒发不静默分包），接收订阅 `notification_received` 喂本页 `_on_raw_data`（698 分帧归本页）。**每包上限自动算**：`worker.single_write_limit()`（特征码写上限或 `MTU−3`，**不叠**蓝牙页 200 字节 `_max_chunk`；单一实现 `_limit_plan`）→ `upgrade.max_block_bytes_for_frame_limit()` 用真实组帧二分反推（MTU 512 ⇒ 509 ⇒ 每包 **475**，用户口径 ≤480 成立）→ `spin_block.setMaximum(cap)` + 夹值 + 标签写明过程（`wordWrap` 防截断）。上限算不出（未连接/`mtu_is_unnegotiated`/放不下帧头）⇒ **不设假上限**、禁用开始并写明原因；重算时机=通道切换/连接变化/`mtu_updated`/SA 变化。回归：GUI [23]、`test_bluetooth_worker.py` [8]、`test_dl698_upgrade.py` A13、wiring [5b]
  - **版本信息的「展示与详细解析」（1.23.85 现场反馈追加）**：① 日志改成「`[RX] <整帧>` 单独一行 + `  → 版本信息（升级前·内部）读取成功（N 项）` + 缩进字段行」—— **不要再贴在帧尾**（日志 NoWrap，70 字节响应帧会把内容顶到屏幕外）；② 参数栏之下新增「版本信息」区，`升级前`/`升级完成后` **并排两栏**只读框（每栏高度 ≥ 7 行行距，防挤掉日志），`开始升级`/`清除` 都重置；③ 逐字段解析走 `dl_t698_45_data_decode` 的**单一来源**（`VERSION_FIELDS`/`VERSION_FIELD_BYTES`/`version_like_members`/`version_lengths_match`/`decode_version_info`，`CLASS_ATTR_TEMPLATES[(19,3)]` 引用它）⇒ `dl_t698_45_upgrade.version_rows` 给 `名称/值/原始/长度`；**长度与表191 声明不符时命名照给但必须带 `⚠ 长度未自证` 行**，非结构数据兜底一行 `数据`。现场实帧（内部版本响应，6 项 4/4/6/4/6/8）解析为 厂商代码=LHIN / 软件版本号=0039 / 软件版本日期=2026-08-03 / 硬件版本号=001A / 硬件版本日期=2025-10-13 / 厂商扩展信息=GWGSXXXX
  - **升级前/后版本比对判定（1.23.86 追加）**：「版本信息」组顶部有**判定条**（`lbl_verdict`，位于并排两栏之上）：**版本有差异 ⇒ 判定升级成功（✅ 绿）**；**完全一致 ⇒ 判定升级失败（❌ 红，设备没换新固件）**；缺基线/有一侧没读到/前后读的不是同一项 ⇒ **无法判定（⚠ 橙）**，两侧都没读 ⇒ **尚未比对（⏳ 灰）**。判等**优先比原始字节**（`值` 会补全日期、裁剪长值，拿它判等会把同一版本误判成变了）、`⚠` 诊断行不参与；结论同时写进收尾状态行（`状态：done｜已发送 N 帧｜判定：升级成功（版本已变化）`）与日志（`[信息]/[失败] 版本比对：…`）。**判定不改状态机**（流程照常 `done`/100%，流程跑完 ≠ 固件升级成功）。详见 §8 陷阱 80
  - **「升级前/后读版本」必须逐字段命名，NULL 成员也不例外（1.23.93 现场修正，改前必读）**：现场报障「升级前读版本只显示 `数据 = 0206...` 原始内容」。根因是 `version_like_members` 要求 **6 个成员全部是 visible-string**，而设备把「厂商扩展信息」回成 A-XDR `null`（`00`）⇒ 整条结构被判「非版本形状」⇒ `version_rows` 退化成单行 `数据`。修法三条：① 判据改为「6 个成员，每个是 **visible-string 或 null**」（与 `_decode_version_structure` 本就容忍非字符串的行为对齐）；② null 成员显示 `NULL` 并**追加一行「⚠ 字段缺失」**点名是哪几项（表191 声明为定长 visible-string，缺失要说出依据，不能静默吞掉）；③ 定长字段常用 **NUL 补齐**（`CNC\0`）⇒ 显示前 `rstrip("\x00")`，但「原始」列保留 NUL 字节可追溯。判据单一来源 `dl_t698_45_data_decode._is_null_member`（升级页经 `_is_null_version_member` 转调，**不要另写一份**）。回归：`test/test_dl698_upgrade.py` A12 ③b/③c
  - **TX/RX 日志的帧显示口径**（1.23.85 用户反馈修订；唯一入口 `dlt698_upgrade_widget.fmt_hex`，`HEX_LOG_LIMIT = 200`）：**≤200 字节整帧打印**（启动传输 62 字节帧原被截到 48 字节，尾部校验值/结束符看不到）；**>200 字节**（写文件大帧）只显**头尾各 100 字节 + 中间 `...` + `(共 N 字节)`**，省略的正是升级包数据体。**不要退回「只显前 N 字节」**
  - **「提升波特率」+ 升级后读版本的「双波特率尝试」（1.23.86 追加；改这块前必读）**：升级页串口通道新增勾选 `提升波特率`（`chk_boost_baud`，默认不勾、落盘、传输中冻结）+ `切换等待(ms)`（`spin_boost_wait`，默认 300、0~10000）。**顺序铁律**：开始升级前先发那条 31 字节 FT1.2 现场实帧 `BAUD_BOOST_COMMAND`（`68 1D 00 43 05 AA×6 A0 28 98 07 01 3E FF 10 80 00 5F 0A 02 08 01 00 00 6B C4 16`，L=29=31−2、末字节 `16`）让**设备**先切自己的 UART，静默 `切换等待(ms)` 之后**主机**才跟着切到 `BAUD_BOOST`（115200）——主机先切就连命令都发不出去；命令**只发不等确认**（`PHASE_BAUD_BOOST` 期间任何回帧都忽略：设备切完速率时主机还停在旧速率，等它只会白等一个超时）。切速**必须**走 `SerialWorker.set_baudrate()`（端口开着也安全：`with self._write_lock:` 内**先 `flush()` 排空发送缓冲、再改 DCB**——顺序反了前半截会按旧速率发成残帧；**绝不** `close_port`/重开端口，会丢设备侧会话表现为掉线），成功后才发 `baudrate_changed` 供 `main_gui._on_serial_baudrate_changed` 同步顶部回显（**刻意不落盘**：热切换是升级临时状态，不是用户下次启动的默认值）。**切回 `BAUD_DEFAULT`（9600）的时机**：`_begin_reset_wait` 入口（覆盖「勾/不勾自动执行」两条路径）+ `_finish_buttons` 终态兜底 + `cleanup`；`_restore_baud` **只在真切成功时才清 `_boosted`**（失败保留标记，收尾会再试一次），否则共享串口会被永久留在 115200 而顶栏与页面都按 9600 说话、现场查不出原因。**「升级完成后读版本信息」要两种速率各试一遍**：设备升级**成功**会复位回 9600，**失败则可能仍停在 115200**（现场口径，`POST_READ_BAUDS = (9600, 115200)`，9600 优先——命中率更高且是共享串口的「安全态」）⇒ `ver_post` 的重试用尽**不等于**读不到：`_continue_after_version_failure` 先 `_switch_post_baud()` 换速率重发一轮（清 RX 缓冲、`_attempt` 归零、切到 115200 时置 `_boosted` 让收尾带回来），**两种都读不到才**记原因收尾，原因文案同时给出两个速率。只在 `_boost_used`（黏性：切回后仍为 True）为真时才换速率——**没提升过就是单速率、一次切速都不做**（与旧版逐字相同）；`ver_pre`（升级前）**也换速率**（设备此刻必在提升速率上）。回归：`test/test_dl698_upgrade_gui.py` [25]/[26]、`test/test_serial_worker_set_baudrate.py`
  - **升级包路径持久化（1.23.86 追加，现场口径）**：拖入/浏览选中的升级包**路径随配置落盘**（`DEFAULTS["file_path"]`，只存路径不存字节 —— 升级包几十 MB 塞进 JSON 会拖慢启动，且文件随时会被替换），重开程序/重开本页**直接显示上次的文件**，**只有换新文件才更新路径**。恢复在 `_load_persisted` 末尾（参数就位之后）调 `_restore_package`：文件没了/变目录/读失败 ⇒ **不恢复**（保持「未选择文件」，`_validate_inputs` 会拦住开始），拖放区写明原因 + 一条 `[警告]` 日志，**落盘路径仍保留**（U 盘/网络盘可能回来，不替用户删记录）；恢复**不弹框**（`_upgrade_module(quiet=True)`）、**不冲掉**手工「文件大小」覆盖值（`set_size=False`）、**不写**「分包完成」日志（`announce=False`）。手工选择与恢复**共用 `_apply_package`**（防两条路走偏）；选到可用文件后撤掉告警提示（`DROP_HINT_IDLE`）。文件名只显 basename、**完整路径挂 tooltip**（同名不同目录要分得清）；`_on_file_selected` 选完**立刻** `_schedule_save()`（不等 400ms 防抖，选完就关窗口也不丢）；「清除」按原契约**保留**文件与路径。回归：`test/test_dl698_upgrade_gui.py` [28]
  - **启动传输的两种报文 + 校验值必须是 2 字节 CRC-16/X-25（1.23.93 现场修正，改前必读）**：
  - **校验值宽度错了 4 个月**：1.23.93 及以前 `calc_checksum_value(kind="crc")` 用 `zlib.crc32` 出 **4 字节**，而设备要的是 **2 字节**。现场实帧 `DPU_APP_V1.0.3.4.bin`（469,200 B）的校验字段是 `09 02 73 73`，即 `0x7373`；用 **CRC-16/X-25**（poly 0x1021 反射 / init 0xFFFF / xorout 0xFFFF，与链路层 HCS/FCS 同一规格）算该文件**恰好** `0x7373`。反证：ARC-MODBUS=0x4739、CCITT-FALSE=0x6F1E、XMODEM=0x834A、KERMIT=0xA6BB、DNP=0x3F8D、AUG-CCITT=0xCCE4 全部对不上 ⇒ 不是"随便挑个 CRC16"。唯一实现 `dl_t698_45_upgrade.crc16_x25`（内部就用 `crcmod` 的 `x-25`）
  - **方法14 = 现场真身**：现场两帧都用 `OMD=F0010E00`（方法14「启动传输（带块大小/版本/下载方标识）」），不是文档示例的方法7。参数 = `02 06 | 文件信息 | 块大小 | 校验 | 软件版本数组 | 下载方标识数组 | 2字节标识 | 00`，其中「软件版本/下载方标识」是 `01 01 0A <len> <ascii>`（数组仅 1 项）。实现 `build_start_transfer_v14(...)`，**两帧现场报文逐字节复现**（`test_dl698_upgrade.py` A14）
  - **两种现场帧只差 1 个类型标签**：第 6 项「2 字节标识」用 `09`(octet-string) 还是 `0A`(visible-string)，不同设备只认其中一种 ⇒ `variant="octet"/"visible"`
  - **自动兼容（页面「启动格式」下拉）**：`自动兼容` 时按 `START_FORMATS` 顺序逐个试，**哪条回 DAR=0 就用哪种继续下发文件块**；某一种重试用尽**不算失败**，先换下一种（`_next_start_format`），三种都不回才判失败。默认仍是 `v7`（老设备/既有测试的既有轨迹零变化），新设备切一次即落盘保持
  - **判定必须用当前格式的 OMD**：`_expected_omd` 在 `PHASE_START` 返回 `_start_omd(upg)`（方法14=0E / 方法7=07），写死 07 会把方法14 的确认帧当"非本步"忽略
  - 页面「校验」下拉文案同步改为 `CRC-16(X-25)`；`按文件计算` 对现场包给 `7373`
  - 回归：`test/test_dl698_upgrade.py` A14（两帧逐字节 + 差异仅 3 字节 + CRC 口径）、A7（2 字节宽度）；`test/test_dl698_upgrade_gui.py` `test_start_format_fallback`（自动逐个试 / 锁定单格式不换 / 确认后进写文件）
- **校验值的算法/字节序未经现场证实** ⇒ 默认 `zlib.crc32` 大端且允许手工覆盖；**不要把「与设备一致」当成已验证事实**
- **「国网协议测试」页（1.24.3 新增，`has_gdw_test`，仅协议7 可见）**：按 **功能域 → AFN → Fn** 三层的预置命令树
  （`gdw_test_core.catalog(page)`），五页签 = 读取数据 / 设置控制 / 主动上报 / EB 扩展 / 自定义。
  - **单一来源**：命令与字段 schema 取 `GDW_AFNFN_SCHEMA`（122 条，**已含**福建增补 50H~56H 与 F0/F1 扩展），
    AFN/Fn 名称取解析器 `AFN_MAP`/`FN_MAP`，EB 取 `gdw_eb_di_lookup`（75 条）+ `gdw_eb_di_fields.EB_DI_FIELDS`（56 条有表单），
    自定义取 `GDW10376Parser.get_custom_entries()`（`gdw_custom_afn.json`）。**禁止另建 AFN/EB 表**。
  - **`AFN_PAGE` 必须恰好覆盖 `AFN_MAP` 且互斥**（测试有断言）：读取={03,04,10,14,53,F0}、设置={01,02,05,11,12,13,15,51,52,55,F1}、
    上报={00,06,50,56}。新增 AFN 时要同时补解析器表、schema 与页面归属，否则测试先红。
  - **组帧只走 `GDWFrameGenerator.generate_frame`**（新增可选参数 `extra_data`，供**上行模拟**追加数据单元；
    上行命令在 schema 里没有字段）。派生字段（`报文长度`/`*数量`）由 `build_frame(auto_lengths=True)` 回填。
  - **EB 帧 = 645 帧**：DI 线上序低字节在前 + 数据域**逐字节 +0x33**，外层默认 `AFN=02H F1` 转发（`通信协议类型=2`）。
    口径与解析器 `_try_parse_embedded_eb` 严格互逆（测试用解析器的同一入口回读自证）。
  - **判定只读表格行**（不新增协议判据）：AFN/Fn 回显 → DAR/错误代码/错误状态字/确认否认 → 其余 `ok=None`
    （「已接收（未做字段级判定）」）。`ok=False` 才写失败，**绝不把无证据写成成功**。
  - **布局对齐协议8「协议测试」页**（用户口径）：左 = 命令树、中 = 参数/预览/发送、**右 = 收发日志**（`QSplitter` 三栏，
    日志不得放回底部），信息表/报文表横跨底部；三栏宽度随配置落盘（`split_sizes`）。
  - 回归：`test/test_gdw_testbench.py`（97 项，含 4 条变异反证：AFN 回显 / EB 加扰 / 结构失败置 False / `_awaiting` 守卫）+
    `test/test_gdw_test_tab_wiring.py`（26 项）。
  - **参数存档 / 支持统计 / 日志落盘（1.24.3 追加，纯逻辑在 `gdw_test_store.py`）**：
    - **每条命令各自存档**：`ParamStore` 存 `commands[key] = {values, ui, raw}` 与 `eb[di] = {values, ui, raw}`，
      落 `gdw_test_params.json`。切换命令时 `_on_tree_selection` 先 `_persist_current_params()` 再 `_apply_saved_*`；
      **与「渲染后的默认态」一致就删条目**（`_fresh_ui` 比对），所以「清理所有参数」不会被切换动作立刻写回。
    - **发送队列必须用 `_values_for(page, key)`**（存档值，缺省回落 `core.default_values`）：原来用
      `self._collect_values()` 会把当前显示的字段值套给队列里所有命令（多命令批量下发时是实打实的错帧）。
    - **支持统计**：`stats[key] = {state, reason, at}`，五态 `support` / `support_error` / `mismatch` /
      `no_reply` / `untested`，由 `classify_result(evaluate_response(...))` 归一；「支持」= `support` +
      `support_error`（设备认识该 AFN/Fn，只是执行报错）。EB 页是 DI 口径且无字段级判据，**不计入统计**。
    - **日志落盘**：`SessionLog` 每条 `[HH:MM:SS.mmm] 文本` 追加到 `logs/gdw_test_YYYYMMDD.log`（单文件 8 MB 滚动
      `_2`/`_3`）；面板只显示本次会话，「清空日志/报文」只清缓冲不动文件；「导出日志」写本次会话（带时间戳）。
    - **显示发送的命令**：日志 TX 行、信息表（时间/命令/结果/说明）、报文表（时间/方向/命令/长度/报文）统一用
      `_cmd_label(key)`（`03H F1 名称` / `EB DI 名称`）—— 报文表列号因此后移，`_on_raw_row_activated` 取 col 4。
    - **多页全选**：`_set_all_pages()` 先把五页树 `_ensure_tree` 建出来再统一勾；`lbl_checked` 显示
      `已选 n/总数（本页）· 合计 N/197`。
    - 回归：`test/test_gdw_test_store.py`（84 项：存档往返/删条目、五态矩阵、汇总与 CSV、日志滚动与导出、
      队列各用各的参数、多页全选、命令列、统计渲染、清理范围）。
  - **1 对 2 组网遍历（1.24.3 追加，纯逻辑在 `gdw_test_network.py` + `gdw_test_report.py`）**：
    - **组网参数是一等公民**：`NetworkConfig` = 1~2 个 `SlaveNode`（12 位地址 + 协议类型 + 启用）
      + CCO 地址 + 载波频段 + 无线调制/信道/协商 + `auto_fill` / `fanout` 两个开关；
      落 `gdw_test_params.json` 的 `network` 段，页面「组网参数（1 对 2 测试网络）」一栏读写。
    - **绑定按字段名语义，不按命令硬编码**（`BIND_RULES` 是唯一事实来源）：`从节点列表` /
      `从节点附属节点列表` → 节点集合；`通信对象地址` / `从节点地址` → 当前展开节点；
      `主节点地址` → CCO；`宽带载波频段` → 频段；`无线调制方式`/`无线信道编号`/`信道协商使能`
      → 无线参数；`规约类型`/`通信协议类型` → 该节点协议。新增命令只要字段名一致就自动吃到值。
    - **手改优先**：存档里每条命令带 `dirty` 字段名清单（`ParamStore.set_command(..., dirty=)`），
      绑定跳过这些字段；**dirty 必须按控件值判定**（`_collect_ui()`），拿 `_collect_values()`
      比会把列表字段的 `[]` 与控件里的 `""` 判成不等 → 列表绑定量被误跳过（已踩过）。
    - **节点展开只认单节点地址字段**：`is_node_scoped()` 命中 `通信对象地址`/`从节点地址` 才按节点各发一帧
      （52H F11 并发抄表、52H F1 转发、10H F3 路由查询、11H F3 固定中继路径、05H F200 …）；
      列表类命令（11H F1/F2 添加/删除从节点）一帧放两个节点，**不展开**。
      队列项因此是三元组 `(page, key, node_addr)`，`_targets()` 走 `plan_targets()`。
    - **树级联勾选**：功能域 / AFN 组节点加 `ItemIsUserCheckable`，勾父 = 整组全选；
      `_sync_one()` 自下而上汇总（全勾=勾、全不选=不勾、混合=半勾），`_rebuild_checked_from_tree()`
      再把 `_checked` 与树对齐。
    - **统计按 命令 × 从节点**：统计键 `stat_key(key, node)` = `key@地址`；AFN 汇总按命令去重
      （任一节点支持即算该命令支持）。`summarize(commands, stats, nodes)` 对单节点命令按启用节点
      各出一行，列表命令一行、从节点列显示 `—`。可视化仍是「支持统计」页，列序
      `AFN/Fn/命令/从节点/方向/状态/依据/时间`（状态列移到 index 5）。
    - **遍历报告**：`gdw_test_report.build_report(...)` 出单文件 HTML（内联 CSS、无外链）：
      测试环境（`report_env_rows`：组网摘要 + 通道/地址/超时/收发计数）、AFN 支持汇总、
      逐条结果、交互明细（`_interactions` 记 TX/RX 的帧与结果）、日志路径。入口是统计页「生成报告」。
    - 回归：`test/test_gdw_test_network.py`（99 项：组网模型往返/非法兜底、绑定矩阵与手改优先、
      展开判定、级联勾选三态、控件↔模型往返、统计粒度、HTML 报告结构与转义、端到端两帧各带自己地址）。
  - **支持判定口径（1.24.3 追加，纯逻辑在 `gdw_test_expect.py`）——按报文本质，不是「有回帧就算支持」**：
    - **依据**（`集中器本地通信模块接口-2024.md`）：§6.5.1 AFN=00H 为确认/否认——F1 确认数据单元
      4B 信道状态 + 2B 等待时间（表 9）；F2 否认 1B 错误状态字（表 10）。§6.5.2/6.5.5/6.5.6/6.5.9/6.5.10
      明写「上行报文为确认/否认报文」；§6.5.3/6.5.4/6.5.8/6.5.11/6.5.12/6.5.13 上行是数据帧。
      附件3 福建增补是「标准 AFN + 0x50」的镜像（50H 确认/否认 … 56H 主动上报），
      且 §52H F11 原文「(数据单元格式同F2)或否认【国网标准AFN=00H_F2】」。
    - **两类期望**：`EXPECT_CONFIRM_AFNS` = {01,04,05,11,12, 51,54,55, 06,56}——收到 F1 确认即支持；
      `EXPECT_DATA_AFNS` = {02,03,10,13,14,15, 52,53, F0,F1}——**必须**同 AFN/Fn 上行数据。
      未收录 AFN（用户自定义）**保守按 data**，不把确认误当抄读成功。
    - **否认按错误状态字分档**：4（信息类不存在）/10（主节点不支持此命令）→ `unsupported`（不支持）；
      其余（0 通信超时、9 主节点忙、11 从节点不应答、12 不在网内、109/110/111…）→
      `support_error`（命令被识别，执行失败）。
    - **抄表类的中间态**：收到 F1 确认只是「已受理」，`judge()` 返回 `waiting_data`（非终态），
      页面**不推进队列**继续等数据；等到 → `support`；等到同命令帧但字段级失败 → `support_error`；
      一直没数据而超时 → `confirm_only`（「仅确认·无数据」），**按用户口径不计入支持**。
    - **状态集**（`gdw_test_store`）：support / support_error / unsupported / confirm_only /
      mismatch（收到过帧但都不是该命令）/ no_reply / untested；
      `SUPPORTED_STATES` 只含前两个，AFN 汇总按命令去重。
    - **无关帧不当场定性**：等待期间收到别的命令帧只记 `_pending_saw_other`，超时才落 `mismatch`——
      否则设备主动上报会污染「不支持」结论。
    - 回归：`test/test_gdw_test_expect.py`（71 项：分类计数、确认/否认矩阵（4/10 与 0/9/11/12/109/110/111）、
      同命令数据、坏帧不误判、页面三态流转、汇总不计仅确认）。
  - **上行命令不下发（1.24.3 追加，用户口径纠正）**：本页是上位机，只能发**下行**帧。
    `00H/50H 确认·否认`、`06H` 上报类、`56H` 上报类共 **19 条 `direction=up`** 是被测 CCO
    自己发出的（应答或主动上报），测试系统只接收：
    - `expect.is_uplink_only()` 只认**显式** `direction == "up"`（缺字段的自定义命令按可下发，
      否则自定义 AFN 会被静默漏测）；`expect_mode()` 对上行为 `uplink`，不给支持结论；
    - 树里上行叶子**移除 ItemIsUserCheckable/ItemIsSelectable 并置灰**，`_sendable_leaves()`
      过滤后「全选本页/所有页」不会选中；`plan_targets()` 返回 `(plan, skipped)`，
      混进勾选清单的上行项走 `skipped` 并记一条「[跳过] 上行命令不下发」；
    - 统计分母只含**103 条可下发下行命令**（`_stats_commands` 过滤）；报告新增
      「上行命令（仅接收，不判支持）」附录，列出 19 条并说明触发条件（注册需留时间、
      06H F5 需陪测从节点断电等），明确**不纳入自动遍历结论**；
    - 「主动上报」页因此可下发数为 0（该页 19 条全是上行），计数标签会追加「另有 N 条仅接收」。
    - 回归：`test/test_gdw_test_expect.py`（92 项，含上行不可勾选/全选不选中/跳过并记日志/统计不含上行/报告附录）。
  - **「流程测试」页（1.25.0 新增，第 6 页签，在「自定义」右边）**：按
    `互换性协议一致性测试用例-本地通信单元(能源控制器(专变)-双模)-SGCM010720240329.xlsx` 第 70~78 行
    建 9 条用例（识别 / 档案同步 / 点抄 / 从节点主动注册 / 能源控制器主动抄表 / 路由模块主动抄表 /
    广播（通信时延）/ 宽带增补 / 抄表测试），步骤与判定转写自 `关于能源控制器.docx` 2.2.x。
    - 引擎 `gdw_test_flows.FlowRunner` **纯逻辑零 Qt**：步骤 `send`/`wait`/`sleep`/`manual`/`note`；
      `wait` 用于模块主动发起的流程（等 `14H F1` 上行等）；`optional` 步失败只跳过；
      `stop()` 置 `stopped=True`，**停止不算通过**（`passed` 要求 finished 且未 failed 未 stopped）。
    - **校验不能只看「收到一帧」**：`run_check` 覆盖 `CHECK_ARCHIVE`（F2 含组网全部地址）、
      `CHECK_TOPOLOGY`（F20 角色有效）、`CHECK_DELAY`（03H F9 的 T1>0）、
      `CHECK_BROADCAST_ACK`（05H F3 的 T2）、`CHECK_ROUTE_STATE`（10H F4 工作标志=停止）。
    - **陷阱**：流程页**不计入命令合计**（`_sendable_count(PAGE_FLOW)=0`，`_checked` 里也不并入
      `all_n`）；新增页会让 `test_gdw_test_store` / `test_gdw_test_network` 的「五页全选」断言失效，
      改页数时必须同步这两处。
    - 多选流程按树序排队执行（`_flow_queue`），一条结束 300ms 后自动跑下一条。
    - **「前提」是真跑不是说明**（1.25.1，用户口径）：依赖从节点的用例先执行
      `prerequisite_steps()` —— `01H F2 初始化` → `11H F1 建档` → `10H F1 查数量` → `10H F2 核对档案`
      → **`KIND_RESET_STA` 复位 STA** → `11H F102 启动组网` → **`KIND_POLL` 轮询 `10H F20`
      至全部入网（15s × 最长 300s）** → 再跑用例本体。组网是要时间的，别写成固定 sleep 或一句注释。
    - **识别流程的「上电」= `01H F1 硬件初始化`**（1.25.2，用户口径「CCO 上电动作可以使用硬件初始化来触发」）：
      首步发 `01H F1`（无数据单元）→ **紧接着就等 `03H F10` 主动上报（60s）** → 主动查 `03H F10`（可选）
      → `03H F4` → `05H F1`。不要再用「模块已上电」的 note 步糊过去。
    - **陷阱：`wait` 步要用十进制 Fn**（1.25.3）：`03H F10` 是 `fn=10`，写 `0x10`（16）永远匹配不上；
      解析器的 DT→Fn 是十进制。且**别在 wait 前面横插 sleep** —— 硬件初始化后 CCO 几乎立刻上报，
      sleep 会把帧挡在窗口外；流程期间所有收帧都进 `_flow_rx_buffer`，进入 `wait` 先查缓存（命中即判通过并标记消费）。
    - **STA 复位通道**：`KIND_RESET_STA` 下发 645 广播 `68 AA…68 14 0C … DA 16`
      （`sta_reset.build_frame()`），优先经 `set_sta_reset_provider` 注入的通道 ——
      主程序注入 `VirtualMeterWidget.send_sta_reset_frame`（协议8 虚拟表的从站串口，那才是 STA 总线）；
      返回 False（未监听）时退回流程页自己的串口并在日志说明。
    - **主动上报必须回确认**（1.25.1，1.26.1/1.26.2/1.26.6 修正数据单元）：`needs_confirm()` 覆盖 `06H`/`56H` 整类 +
      `03H F10/F11`、`14H F1/F3`；确认帧 = `00H F1`，**数据单元 6 字节 = 4B BS + 2B 等待时间**（表 9）：
      BS 32 位里 D0 = 命令状态（0 未处理/1 已处理），D1~D31 = 信道 1~31（0 忙/1 闲）；
      等待时间 BIN 2B（单位 s，**协议要求 ≤5s**，本工具填 `ACK_WAIT_SECONDS = 1`）。
      全空闲+未处理+1s → `FE FF FF FF 01 00`（低字节在前，整帧 21B）。
      **空数据单元、只填 1 字节、只发 4B BS（漏等待时间）都是不合规确认帧** —— 解析侧对 4B 帧会显式标「等待时间缺失」。
      确认帧沿用原帧报文序列号，原帧无地址域时确认帧也不带。
      **解析侧注意**：`00H F1` 与 `00H F2` **数据单元结构完全不同，不能共用一套解析**（表 9 vs 表 10）：
      - **F1 确认 = 4B BS + 2B 等待时间，没有错误状态字**。命令状态是 **D0（bit0）**，别写成 D7（`0x80`）；
        字节 1~3 是信道 8~31 状态、**不是**「错误状态字」；等待时间在**字节 4~5**，不是 2~3。
      - **F2 否认 = 只有 1B 错误状态字**（0 通信超时 / 1 无效数据单元 / 2 长度错 / 3 校验错 / 4 信息类不存在 /
        6 表号重复 / 9 主节点忙 / 10 主节点不支持此命令 / 11 从节点不应答 / 12 从节点不在网内 …109~111），
        没有信道状态、没有等待时间；多出的字节按「多余字节」单独标出，别塞进错误状态字。
    - **抄表两轮 + 数据一致性**（1.26.2，用户口径）：`read_round_steps()` 生成
      ① 延时标志=00H → 直接等 `13H F1` 上报；② 延时标志=01H → 等 `14H F3` 上行 → 回 `14H F3` 下行 → 再等 `13H F1`。
      **判定不是只比 AFN/Fn**：`CHECK_READ_MATCH` 把上报数据单元里的 645/698 报文与虚拟表
      **实际发出的应答逐字节比对**（`StaSimService.recent_responses`）；无记录才退化为结构校验
      （645 需 D7=1 应答且数据非空；D6 是「从站正确应答」，别写成 0x40 判定）。
      **陷阱**：摘内嵌 698 帧时长度要按 **总长 = L + 2**（698.45 的 L 是用户数据长度）；
      只有外层 376.2 帧才是 L = 总长。按 L 切会把 53B 应答截成 51B，导致「数据明明一致却判失败」。
    - **顶部参数区「折叠分层」**（1.26.7，用户口径「界面要整洁、善于用折叠控件、串口状态只要一个图标」）：
      「测试参数」框只留**常驻一行**（通道图标 + 发送通道 + 序列号/超时/重试 + 两个清理按钮）；
      源地址/目的地址/模块标识/中继级别折进 `CollapsibleSection`（`key="gdw_params_addr"`，
      **默认收起**）；组网参数折成 `key="gdw_params_network"`（**默认展开**，现场要改）。
      折叠状态经 `collapsible_section.collect_state/apply_state` 存进 `gdw_testbench.json` 的
      `sections`；**串口状态只用图标 + 颜色**（`plug` 绿 / `unplug` 红，`app_icons.render_pixmap`），
      完整文案（端口在哪设、蓝牙怎么连）只放 tooltip —— 别再往标签里塞长句。
      回归：`test/test_gdw_ui_layout.py`（38 项：图标颜色像素、折叠默认态、常驻项不被折叠、
      逐行对齐、状态持久化与坏数据容错）。
    - **建档帧必须有显式覆盖值**（1.26.8，回归缺陷）：`build_preflight` 原先只给 `10H F2`/`10H F20`
      生成 overrides，**`11H F1 建档` 的从节点列表全靠界面「按组网参数自动填充」开关兜底** ——
      开关被关掉（或存档里是关闭态）时会发出「数量=0、没有地址」的空档案帧，被测一遍空跑，
      现场表现为「建档成功但一块表都没进去」；该缺陷只在特定执行顺序下复现（偶发测试失败）。
      现在 `_preflight_add_nodes_overrides()` 显式给 `从节点数量` + `从节点列表[{从节点地址,通信协议类型}]`，
      与自动填充开关无关。回归：`test_gdw_test_network.py` 的 [8]（建档覆盖值 3 项 + 「关掉自动填充仍能建档」1 项）。
    - **14H F1 应答的 1376.2 头部照现场参考报文**（1.26.14，用户给了参考帧）：控制域 = **`01H`**
      （DIR=0 下行、**PRM=0 从动站**——本帧是对模块请求的应答、通信方式=1 窄带载波）；
      信息域 = **`08 00 00 00 00 <seq>`**（首字节 D3 冲突检测=1，**D2 通信模块标识=0 ⇒ 不带地址域**）。
      实现是 `_router_reply_info()`，只作用于 14H F1 回抄读内容，其它命令仍用界面上的
      `_info_config()`。抄读内容本身不变（仍是按从节点协议生成的 645/698 读帧）。
      参考报文里的抄读内容是**加密的 SECURITY-Request（APDU 0x10）**，属于现场加密链路，
      本工具发明文读帧。
    - **应答帧的报文序列号必须回显请求帧**（1.26.15，用户口径「如果是被测 CCO 发过来的请求帧，
      那么我们回复的报文序列号需要和请求的序列号匹配上」）：`14H F1` / `14H F2` 的应答都用
      `_router_reply_info(seq)`，`seq` 取自请求帧解析行的「报文序列号」（`_row_int(table, ...)`）；
      **不要用界面上的自增序号、也不要因为应答而去递增 `spin_seq`**（会把后续手工发送的序列号带偏）。
      确认帧（00H F1）本来就沿用原帧序号，口径一致。
    - **抄读内容必须是虚拟表支持的 OAD / DI**（1.26.13，用户口径「抄读的内容是虚拟表支持的 OAD 和 APDU，
      否则 CCO 仍然抄不到正确响应」）：`gdw_meter_request.pick_698_oad()` / `pick_645_di()` 会先读虚拟表档案
      （`meter_sim_data.json` 的 194 条 OAD、645 档案的 DI），**档案里有就用默认的正向有功总电能，
      没有就退到档案里任意 `attr=02` 的电能量项**。虚拟表档案是用户可编辑的数据，硬编码一个档案里不存在的
      OAD/DI，虚拟表只会回「对象不存在 / 数据标识不存在」，CCO 就抄不到东西。
      回归：`test_gdw_flows` 的 `[3g]`（把读帧真的喂给 `MeterSimEngine` / `DLT645MeterSim`，
      断言 698 回 `85` GET-Response、645 回 `91H`，并保住 698 读帧与现场样例逐字节一致）。
    - **`14H F1` 下行不填「从节点附属节点地址」**（1.26.12，用户口径「发送请求抄读内容 14F1 给被测模块时，
      第一不需要填写从节点附属节点 1 地址」）：表 125 明确「02H 可以抄读时 **n ≥ 0**」，抄读内容本身已带
      表地址，所以 `从节点附属节点数量 = 0`、列表留空即可；填了反而可能与请求不匹配。应答结构：
      `抄读标志(02H) + 通信延时相关性标志(00H) + 路由请求数据长度 L + 数据内容(L) + 附属节点数量(00H)`。
    - **`14H F3` 下行回完就推进，不等应答**（1.26.11，用户口径「收到了 14F3 的请求，测试系统就回复
      14F3 下行就完了，为何有超时？回复完成后就等被测 CCO 上报 13F1 的数据」）：`FlowStep.no_reply=True`
      的发送步在**发完立即 `_flow_done(True)`**，不启等待定时器。否则干等确认只会白超时判失败
      （现场日志就是这样：`[TX] 14H F3 …` 之后 6s 超时）。被测收到修正数据后会自己继续抄表并上报 `13H F1`。
    - **698 读报文必须带「时间标签 = 无」的 `00`**（1.26.11，用户现场口径）：APDU = `05 01 01 OAD(4B) 00`。
      少了这个字节 → 长度域 L 少 1、被测认为报文不完整而**不执行抄表**。另外**两个校验的范围**要照现场：
      **HCS = CRC16(x-25)(L' + C + SA + CA)**，`L'` 是**不含时间标签**的长度；
      **FCS = CRC16(x-25)(L + C + SA + CA + HCS + APDU)**，用**真实长度**。
      基准报文（逐字节比对的 golden，改这里前先跑测试）：
      `68 17 00 43 05 33 00 00 00 00 00 00 C7 52 05 01 01 00 10 02 00 00 92 2E 16`。
    - **广播类命令的报文长度必须随报文内容派生**（1.26.11）：`03H F9`（表 18）与 `05H F3`（表 43）
      的数据单元都是 `协议类型/控制字(1B) + 报文长度 L(1B) + 报文内容(L)`。schema 里 `报文长度` 要写
      `length_field: "报文内容"`，否则 L 恒为 0，被测当成「没有报文」——
      现场表现就是「长度 0、内容空」。`05H F3` 的控制字：01H 645-1997 / 02H 645-2007 /
      **03H 是相位识别（不是 698.45）**，698 表按 00H 透明传输发原始报文。
    - **`03H F9` 的上下行结构不同，解析必须判方向**（1.26.11）：下行 `协议(1)+长度(1)+内容(L)`；
      上行 `延迟时间(2)+协议(1)+长度(1)+内容`。上行分支少判 `is_upstream` 会把下行的长度字节
      当成协议类型（解析出「协议类型=0x10」这种鬼值）。
    - **从节点模拟（虚拟表）串口参数随配置存档**（1.26.10）：`sta_port/sta_baud/sta_parity/sta_stop`
      写进 `gdw_testbench.json`，`_refresh_sta_ports()` **保留当前选择**（现场口是固定的，
      刷新按钮不该把它重置成第一个口），存档里的口当前没插上时也补进下拉框，插上即用。
    - **跑完的用例点回去要能看到逐步结果**（1.26.10，用户口径「点失败的用例，右边全部是待测试，
      明明已经测完」）：`self._flow_history[fid] = {states, notes, current}` 在每次
      `_render_flow_runner()` 与 `_finish_flow()` 时落快照；`_on_flow_case_selected()` 有历史就用
      `_render_flow_steps(case, states=..., notes=..., current=...)` 回显（失败步连原因一起显示）。
      历史里残留的 `running` 只要不是当前步就显示「待执行」，避免永远转圈；
      步骤数比历史多（流程改过）时多出的按「待执行」补齐，别越界。
    - **「全选」后必须按自上而下的顺序执行**（1.26.17，用户报障「全选之后是从下面向上面开始测试」）：
      根因是 `_iter_leaves()` 用 LIFO 栈（`stack.pop()`）遍历树，产出顺序反向，
      而「全选本页」与勾选记录 `_checked` 都依赖它。现在 `_iter_leaves` 倒序压栈、正序弹出，
      与界面顺序一致；`_flow_selected_cases()` 再以**树的位置**排序（不信任 `_checked` 的顺序，
      旧存档里可能残留倒序）。**注意**：`_iter_leaves` 也决定命令页「全选」的发送顺序，
      改动后是从上到下，别按旧的倒序写断言。
    - **左树第三列 = 「测试结果」**（1.26.9，用户口径「方向的右边增加一个测试结果列，表示整个流程的测试结果」）：
      表头 `["命令 (AFN/Fn)", "方向", "测试结果"]`；流程叶子行显示 `—`（未执行）/`排队中`/
      `进行中…`/`✓ 通过`/`✗ 失败`/`■ 已停止`，颜色写在 `FLOW_RESULT_STYLES`。
      状态存 `self._flow_results`（fid → 状态），`_set_flow_result()` 只重画那一行的第三列，
      **别再整体重建树**（会丢勾选/展开态）。注意该列宽 84px，「进行中…」刚好放得下。
    - **确认帧只给「主动上报类」**（1.26.9，用户口径「不是所有被测 CCO 上报都给确认帧」）：
      `needs_confirm` 覆盖 `06H`/`56H` 整类 + `03H F10/F11` + **`14H F3`**。
      **`14H F1`（请求抄读内容）与 `14H F2`（请求集中器时钟）不发确认帧** ——
      它们要的是业务应答，见下面的 `serve` 步；回确认会让被测以为请求被拒/继续重发。
    - **`serve` 步：路由请求的循环应答**（1.26.9）：`FlowStep(kind="serve", key="14-1",
      serve=((0x14,1),(0x14,2)), until=(0x06,2), check=CHECK_READ_MATCH)`。
      窗口内**每收到一次** `14H F1` 就回一次抄读内容（抄读标志=02H + 该从节点协议的正向有功总电能，
      `_reply_router_read`；报文走 schema 字段 `路由请求数据内容`，长度自动派生，**不要另拼 raw_data**，
      否则 L 会被算成 0）；收到 `14H F2` 就回**当前系统时间**（`_reply_router_clock`，秒/分/时/日/月/年 BCD）。
      收到 `until` 指定的 `06H F2` 即完成该步；超时未收到判失败（备注记「已服务 N 次」）。
      测试完成后必须发 `12H F2 暂停`，否则 CCO 会一直上行 `14H F1` 要抄读内容。
    - **14H F2 的时间字段是 BCD，必须还原成十进制**（1.26.9 修）：旧解析直接 `str(byte)`，
      `0x14`（14 时）会显示成「20 时」，对时链路看着像差 6 小时。现在 `0x14 → 14`，
      非法 BCD（半字节 > 9）标「非法BCD(0xXX)」而不是硬猜。
    - **主动注册等 `06H F4`，不是 `06H F1`**（1.26.5，用户口径：`06H F1` 是 09 版标准的旧报文，
      新标准要求 CCO 用 `06H F4`「上报从节点信息及设备类型」）：`11H F5 激活` 之后主判据是 `06H F4`
      （300s）；`06H F1` 只作为 `accept` 兼容项，命中时日志/步骤备注告警「新标准应报 06H F4」。
      **陷阱**：`wait` 步的 `accept` 以前**从未生效**（只对 `send` 应答判断），现在统一走
      `step_accepts()` / `is_primary_uplink()` —— `match_uplink`、`_flow_consume_buffered`（缓存重放）、
      `_flow_on_frame` 三处缺一处就会「一直等不到」或「等错帧」；只改 `FlowStep.fn` 不改匹配逻辑同样无效。
    - **14H F3 延时修正必须「按上行请求回送」**（1.26.4）：`14H F3` 上行 = 从节点地址(6B) +
      预计延迟时间(2B) + 抄读信息长度(1B) + 抄读数据内容(L)；下发 `14H F3` 下行要放
      **上行里那份报文**（`数据长度 + 修正通信数据内容`），自己另造一帧被测不认、不会继续抄表。
      取上行值时注意：`预计延迟时间` 原始值是 `0xDC05` 这种 2 字节（别用 1~2 位正则截断）；
      `抄读数据内容` 的 hex 在「原始值」列（解析值列是 `24字节`）。
    - **抄表步骤的报文内容必须按从节点协议生成**（1.26.1）：`gdw_meter_request.read_request_for(proto, addr)`
      —— 645-2007 `68 <地址6B 低字节在前> 68 11 04 33 33 34 33 CS 16`（DI 00010000 需**先逆序**再 +0x33，
      否则成 `33 34 33 33` 错 DI）；698.45 = `GET-Request-Normal(OAD=00100200)`，SA 带 `0x05` 单地址特征。
      流程里 `_build_flow_frames` 自动填 `报文内容` + `通信协议类型`（2/3），长度由 `length_field` 派生，
      且**每个从节点各发一帧**。`13H F1` 的附属节点地址同样要 `reverse`。
    - 回归：`test/test_gdw_flows.py`（44 项：用例定义 / 引擎 / 被动等待匹配 / 内容校验 / 页面）。
  - **前置流程「准备测试网络」（1.24.5 起，1.24.10 定为 F20 判入网，1.24.11 加初始化）**：
    - 五段：`01H F2 参数区初始化` → `11H F1 添加从节点`（建档）→ `10H F1 查询从节点数量`（档案总数）→
      `10H F2 查询从节点信息`（**只核对档案加得对不对**）→ `10H F20 查询双模网络拓扑信息`（**入网判据**）。
    - **必须先初始化**（用户口径）：模块里已有该表档案时 `11H F1` 会回「否认（错误状态字=6 表号重复）」。
      代价是参数区一起被清空 —— 现场依赖原频段/路由模式的，初始化后要重新下发配置。
    - **F2 ≠ 入网**（用户口径）：F2 报的是模块里下装了哪些表；某表有档案不等于该表已联网。
      入网只看 `10H F20`，且要求节点**角色有效**（STA/PCO/CCO；角色=无效 不算）。
    - 拓扑上行结构：总数量(2B)+节点起始序号(2B)+本次数量(1B)+n×[地址(6B)+拓扑(5B)]，
      角色在拓扑第 5 字节 D4~D6。地址提取用 `topology_addrs_from_rows`（**注意字段名是「节点N…」**，
      与 F2 的「从节点N…」不同，别混用），证据用 `topology_detail`（角色/层级/信道）。
    - 查询范围：F2 = 起始 1 + 档案个数；F20 = 起始 **1**（1=主节点）+ 1+档案个数。
      字段名必须按各命令 schema 取（`_range_overrides`），写死会覆盖不到 → 帧里数量恒为 1。
    - 未报全时自动重查**拓扑**（`PREFLIGHT_POLL_GAP_MS=2000` × `PREFLIGHT_POLLS=3`），
      组网栏显示「入网 n/N ✓｜档案 m/N」，日志先档案核对、再入网结论（逐条角色/层级/信道）。
    - 回归：`test/test_gdw_test_network.py` 的 `[9a]` 纯逻辑、`[9b]` 端到端、
      `[9c]` 档案 ≠ 入网（角色无效不计、双层标签）。
  - **04H F3 报文通信测试**：`目标地址` 走组网绑定（`FIELD_TARGET_ADDR`）、`报文长度` 用 `length_field` 派生；
    目标地址/长度全 0 时 CCO 只回「错误状态字=7 表号不存在」，别再当命令不支持。
  - **「附加数据」只填数据单元**：贴整帧（`68…16`）会让数据单元多出一段 → CCO 回「错误状态字=2 长度错误」；
    预览区已有护栏提示（`_raw_data_warnings`）。无数据单元的命令（如 `10H F104`）留空即可。
  - **`10H F104 查询升级后模块版本信息` 必须带查询范围（1.24.7 起，1.24.9 按权威文档定稿）**：
    权威来源 = `协议文档/7.国网本地接口协议/HPLC远程升级方案20190130.md`
    （由同名 PDF 转换，2.4.2(2)）。
    - 下行：`节点起始序号(BIN 2B) + 节点数量 n(BIN 1B)`；**序号从 0 开始，0=CCO，1=第 1 个载波从节点**；
      每次查询数量建议 ≤15。空数据单元会回「错误状态字=2 长度错」。
    - 上行：`节点总数量 m(2B，含 CCO 与全部 STA) + 本次应答数量 n(1B) + n×[节点地址(BCD 6B) + 节点信息(9B)]`；
      节点信息 = 软件版本号(BCD 2B) + 版本日期 日/月/年(BCD 各 1B) + 模块厂商代码(ASCII 2B) + 芯片代码(ASCII 2B)。
      示例 `15 01 21 03 19 48 4C 31 41` → 15.01 / 2019-03-21 / HL / 1A。
    - **注意**：`集中器本地通信模块接口-2024.md` 的 OCR 版 §6.5.8.3 **漏了 F104 小节**，
      别再据此判断「无数据单元」；序号是 **0 起**，不要照抄 F20/F21 的 1 起。
    - DT 兼容：远程升级文档示例写 `DT=80 12`（组 12 的 BCD 写法），§6.4.3.2 要求二进制 `80 0C`；
      仅在 `AFN=10H && DT==80 12` 放宽识别，报文表标注来源。该示例帧 `CS=0x99` 与任何前缀求和对不上
      （§5.3 应为 `0x81`），判定按坏帧处理。
  - **同文档定义的其它点**：`10H F4` 运行状态字 **D1=工作标志**（升级中置 1）、工作开关 **D7D6=当前状态**
    （00 抄表 / 01 搜表 / 10 升级 / 11 其他，2024 版把 01 写作「报表」）；`15H F1` 文件标识用
    00/03/07/08/**09H**（09H=本地通信模块和子节点模块升级）。
    `1376.1 AFN=0CH F15`（主站↔集中器）与 `698.45 F209 属性 12`（节点版本信息）只入 markdown，
    **不在本工具 376.2 链路范围**，未实现解析。
  - **否认错误码要落到「怎么办」（1.24.6）**：`gdw_test_expect.ERROR_HINTS` + `error_hint(code)`，
    判定结果带 `hint`，页面日志在结论后打「处置建议」。`2 长度错` 需说明 **L = 整帧总长**
    （68+L+C+R+AFN+DT+数据+CS+16），并给「附加数据补 `01 00 01`」的探测路径（`10H F104` 文档未定义数据单元）；
    `7 表号不存在` 指向地址线序（§5.2 低字节在前、界面正序）与建档（`11H F1`）。
  - **手改字段会跳过组网绑定**：`apply_binding` 对 `dirty_fields` 一律不覆盖。现场 `04H F3`
    目标地址被手改成线序旧值 `330000000000`，组帧后成 `00 00 00 00 00 33` → CCO 判「表号不存在」。
    预览区会提示「⚠ 以下字段被手改，未套用组网参数」（`_dirty_bind_fields`），
    排障时先「清空所有参数」再看绑定结果。
  - **14H 路由数据抄读 F1~F4 参数修正（1.24.4，用户口径「14H F1-F4 参数都不太对」）**：
    - **F1 路由请求抄读内容**（下行应答）：`抄读标志`(00H 失败/01H 成功/02H 可以抄读) + `通信延时相关性标志`
      （**仅 02H 时有效**）+ `路由请求数据长度L` + `路由请求数据内容`（DL/T 645 读报文，也可放 698.45 读请求）
      + 附属节点数量 n + `[附属节点地址(6B)]*n`。**00H/01H 要求 L=0、n=0；02H 要求 L>0**，
      `L` 由 `length_field` 随内容自动派生（原来默认 02H 配 L=0 属非法组合）。
    - **典型流程**（§A.6.2 路由模块主动方式）：集中器 `12H F1` 重启（或 `11H F102` 启动组网）→
      路由**上行** `14H F1`（通信相位(1B)+从节点地址(6B)+从节点序号(2B)）请求抄读 →
      集中器用**下行** `14H F1` 回复抄读标志与待抄读报文（如正向有功总电能
      `68 <表地址6B 低字节在前> 68 11 04 33 33 34 33 B3 16`）。本页只发下行帧，上行由被测设备发。
      **抄读结果的上行是 `06H F2`（上报抄读数据），不是 `13H F1`**（1.26.8 用户口径）——
      `13H F1` 是**集中器主动监控**方式的下行命令、其上行同命令号；路由主动方式走的是
      `06H F2`。流程测试的「路由模块主动方式抄表」因此是：前置建档组网 → `12H F1` 重启 →
      等 `14H F1` 请求 → 回 `14H F1`（报文本工具按该从节点协议自动填 645/698 正向有功总电能）→
      等 `06H F2` 并做逐字节一致性校验。漏掉 `12H F1` 那步 CCO 根本不会主动上行 `14H F1`。
    - **F2/F3/F4 原来 `fields: []`（组帧只有空数据单元，实为错帧）**，现按表 126/127/128 补齐：
      F2 = 秒/分/时/日/月/年 各 1B BCD（默认取程序启动时刻）；F3 = `数据长度L` + 修正通信数据内容
      （**L=0 = 放弃本次通信**）；F4 = 数据项类型(1=645-2007 / 2=698.45) + 交采数据项标识(4B BIN,
      低字节在前, 默认正向有功总电能 `00 00 01 00`) + 交采数据项内容。
    - **陷阱（bcd 地址必须逆序）**：协议 §5.2「低字节在前，高字节在后」，地址域 `_bcd_encode` 已逆序，
      解析器 `_format_addr` 显示时也逆序；但 `GDWFrameGenerator` 的 `bcd` 打包原先**忽略** `reverse`，
      导致 14H F1 附属节点地址与 A1/A3 方向相反（组网自动填充后 CCO 匹配不到表地址）。
      现 `bcd` 支持 `reverse`，14H F1 的 `从节点附属节点地址` 已置 `reverse: True`。
      **其余 bcd 地址字段（05H F1 主节点地址、10H F3、11H F1/F3、13H F1/F2、53H/55H 通信对象地址、
      F1H 从节点地址）仍是正序打包，与 §5.2 相反——尚未统一，改动会牵动 golden，勿顺手全改。**
    - 回归：`test/test_gdw_testbench.py` 新增 `test_route_read_14h`（16 项：F1~F4 逐字节 golden、
      L 与附属节点数量自动派生、附属节点地址低字节在前、F3 空内容 L=0、F4 交采标识/内容、解析器回读），
      全量 113 项通过；`test_frame_corpus` / `test_parser_fuzz` / `test_web_frame_gen_utils` 同步复跑。
- **「协议测试」页（1.23.93 新增，`has_test`，仅协议8 可见）**：按 OAD 分类的**预置测试库**，与「协议组帧」页分工明确 —— 组帧页临时/任意，本页预先做好可直接下发
  - 落点：`dlt698_test_core.py`（纯逻辑：分类库 + 组帧 + 响应判定，零 Qt）+ `dlt698_test_widget.py`（页面，仅协议8）
  - **分类口径**：OI 高字节 → 顶层分类（`HBYTE_INFO`：0x00~0x05 电能量 / 0x10~0x11 需量 / 0x20~0x28 变量 / 0x30~0x37 事件 / 0x40~0x49 参变量 / 0x50 冻结 / 0x60 采集 / 0x70~0x73 文件与应用 / 0x80~0x82 控制 / 0xF0~0xF4 厂家扩展），**子类必须按高字节排序**（按中文名排会把「关联」排到「总电能」前面）；对象名与接口类/属性/方法表全部取自 `OILookup`（777 个对象，唯一来源，**不要另建 OI 表**）
  - **树的三层文案（与现场同类工具同形，改前必读）**：顶层 `4H: 参变量`（OI 高字节的**高 4 位**）、子层 `3H: 设备管理`（**低 4 位**）、叶子 `43000300_（版本信息）_(索引=0)_(优先级及序号=00)`。**叶子是「每个属性一条具体 OAD」**（`leaf_entries`/`record_entries`/`omd_entries` 摊平，共 **4658 条**；设置方法页的叶子是具体 OMD），不是「一个对象一条」—— 现场点 `43000300` 就该直接发读版本信息的帧，不必再挑属性。`index=0` 照工具写数字（不翻译成「全部」）；叶子里的 `优先级及序号` 表示「点这条会用什么 PIID 发」，**PIID/优先级一变必须全树同步文案**（`_on_piid_changed`），否则标签对用户撒谎
  - **叶子名必须写「这个 OAD 是什么」，不是类级属性名**（用户纠正；`leaf_base_name` 单一实现）：
    - 通用属性名补对象名：`逻辑名` → `电压逻辑名`、`换算及单位` → `电压换算及单位`、`分相数值数组`/`数值`/`参数`/`…数组` → **对象名本身**（`电压`）
    - **具体属性名原样保留**：`设备描述符`/`版本信息`/`生产日期`/`事件记录表`/`A相各次谐波数值数组`。早先把后缀映射无差别套用，`43000200` 被叫成「电气设备」、`43000300` 被叫成「电气设备换算及单位」，把真名盖掉了
    - 同对象的兄弟数组加限定词区分：`（扩展精度2）`/`（扩展精度）`/`（尾数）`/`（带品质）`（class 1 有 6 个电能量数组，全叫「正向有功电能」就分不清）
    - **分相展开**：仅 class 3（分相变量类）的属性 1/2/3/31 按 A/B/C 拆成 `20000201 A相电压`、`20000202 B相电压`、`20000203 C相电压`。依据 §7.3.5「00H=整个属性，01H=第一个元素」+ 仓库内唯一解码口径 `dl_t698_45_data_decode._decode_phase_array` 的 `labels=["A相","B相","C相"]`。**class 4（功率类）不拆** —— 其「总及分相数值数组」在解码器里按 A/B/C 标注、与「总+三相」四元素说法冲突，证据不足就不猜。选中分相叶子时「元素索引」同步成该叶子的索引（否则帧仍发 00H）
    - 参考工具里 `2000020A`（索引 0x0A）这类写法**不照抄**：按协议 0x0A 是「第 10 个元素」，设备上没有，照发只会回 DAR
  - **四个分页**：读取属性（GET Normal）/ 设置属性（SET Normal）/ 读取记录（GET Record，RSD 支持 `0/1/2/9/10`，`3~8/11` 结构未用到 ⇒ **传进去直接抛**，不要猜）/ 设置方法（ACTION Normal）。「属性/方法」下拉已改为**只读回显**（叶子已定死属性），「元素索引」仍可调，改动只作用于选中那一条并同步其文案
  - **组帧黄金（协议文档附录 H，逐字节断言在 `test_dlt698_testbench.py`）**：读属性 `05 01 PIID OAD 00`｜读多属性 `05 02 PIID 个数 OAD×n 00`（= 页面「Lst发送」）｜读记录 `05 03 PIID OAD RSD RCSD 00`｜设置 `06 01 PIID OAD Data 00`｜操作 `07 01 PIID OMD Data 00`｜建立连接 `02 PIID 协议版本(2B) 协议一致性(8B) 功能一致性(15B) 发送帧长(2B) 接收帧长(2B) 窗口(1B) 最大APDU(2B) 超时(4B) 认证 00`（默认参数 = 文档 H.2 的 40 字节）
  - **HCS/FCS 仍只由 `DLT69845FrameGenerator` 算**（新增公开方法 `generate_apdu_frame` / `generate_connect_request`，既有调用零行为变化）；SA 编码复用 `dl_t698_45_upgrade.build_sa`（唯一实现）—— **页面与逻辑层都不得手拼 `68 … 16`**（陷阱 31）
  - **「获取设备地址」**：读 `OAD 40010200`（通信地址，`OILookup` 里 OI 0x4001 属参数变量类、属性2），响应 octet-string 回填「服务器地址」，后续所有 OAD 都用它组帧；**不覆盖**用户已填的「写地址」
  - **不冒充判定**：CONNECT-Response 与记录型二维数据体没有可自证的字段布局 ⇒ `evaluate_response` 给 `ok=None` + 「未做字段级解析」，**不得写「成功」**；DAR 中文取自解析器 `_enrich_dar`（单一来源）
  - **收发日志的逐字段解析（1.23.93 追加；用户口径「解析器已经很完备，要详细输出」）**：勾选「详细解析」（`chk_detail`，默认勾、落盘）后，**TX 与 RX 都**打印整帧字段表 —— 数据源是 `DLT69845Parser.parse_to_table`（**就是单帧解析页那张表**），单一实现 `dlt698_test_core.parse_table` / `detail_lines` / `format_table_rows`，**禁止在页面里另写字段拆解**（陷阱 31 的漂移根因）。四列 `字段 | 原始值 | 解析值 | 说明` 按显示宽度对齐（CJK 算 2 列）；长 hex 与结构化值必须压缩（`_compact_hex_like` / `_clip`），否则一行能撑到屏幕外 —— **压缩判据不能要求「长度为偶数」**（解析器偶尔给出被截断的奇数长度编码，早先这样判会整段漏压）。未请求的帧（主动上报）也走同一套明细。双击底部「报文」表任意行 → 送主窗口「单帧解析」页看完整解析树（`frame_to_single_parse` 信号，与监控器共用 `_send_frame_to_single_parse` 注入点）；报文表「行号 → 原字节」映射在裁剪行时必须重建，否则双击会送上一帧
  - **「编辑」= OAD/OMD 覆盖框**（就地改一两个字节；留空回到按属性生成），非法长度在预览与发送处都报 ⚠，**不静默退回**
  - 复用共享串口（`write_raw` + `raw_data_received`，自组帧用 `frame_deframe` 的 `L+2` 判据，见陷阱 77）；落盘 `dlt698_testbench.json`；「远程升级」按钮跳「光伏升级」页
  - **发送通道（1.24.1 起）**：顶部「发送通道：串口/蓝牙」走共用 `channel_link.ChannelController`；
    蓝牙复用「蓝牙工具」页连接（`set_bluetooth_provider`），整帧一次 ATT 写、超限报错不发送；
    收发只经 `controller.rx/send`（页面**不再**直连 `raw_data_received`，见 §8 陷阱 92）。
  - 回归：`test/test_dlt698_testbench.py`（**294** 项，含 [18] 双通道段）+ `test/test_dlt698_test_tab_wiring.py`（**23** 项，接线/显隐/注入/跳转/收尾）
- **虚拟表（从站模拟器，1.16.0 起）**：`meter_sim_widget.py`（tab「虚拟表」，仅协议8）+ `meter_sim/` 纯逻辑包
  - **虚拟表地址（1.24.9 起）**：`SimOptions.meter_address`（12 位十进制数字，UI「虚拟表地址」框），**未设置时回落到档案 `40020200` 表号**；`MeterSimEngine.own_address()` 是唯一取值口。响应帧 SA 一律由它派生（`dynamic_data.address_sa`：特征 `05` + 反转 BCD），**不再回显请求 SA**
  - **组地址对象（OAD `40050200`，1.26.16 起内置）**：协议定义 OI 4005 属性2 = **array octet-string**，
    引擎按 `01`(array) + 个数 + 每个 `09`(octet-string) + 长度 + 数据 编码，默认回 1 个 6 字节 BCD 的
    `000000000000` ⇒ 数据 `01 01 09 06 00 00 00 00 00 00`（`dynamic_data.group_address_data()`）。
    CCO 现场会主动读组地址，虚拟表不认这个对象就回「对象不存在」，CCO 拿不到组地址。
    **不要照 4001 的 `55 07 05 + 6B` 结构写**（那是通信地址对象自己的编码）。
    回归：`test/test_meter_sim.py` 的 `test_group_address`（含现场请求帧 `68 17 00 43 … 40 05 02 00 …`）。
  - **寻址判据（`link_layer.classify_address`，改前必读）**：单地址（类型0）/ 通配（类型1，**每字节高低 4 位可为 `AH` 通配位**，`nibble_match` 逐半字节比对本机地址，全 `AA` 视为全通配）/ 组地址（类型2，协议要求**无需应答**）/ 广播（类型3 `AA` 单字节，另把**全 99 / 全 AA** 写法一并当广播）。通配、广播、全 99、白名单命中的请求**都要应答**，且应答 SA = 本机地址 —— 主站读通信地址（OAD `40010200`/`40020200`/`202a0200`）时回的也是本机地址
  - **`strict_address`（默认关）**：关 = 任意单地址请求都应答（兼容旧行为，`offscreen` 与历史测试用任意 SA）；开 = 只有 SA 等于本机地址（或白名单命中）才应答。白名单**只约束单地址请求**，不得再挡通配/广播（1.24.9 前的旧实现会把通配请求一起挡掉，表现为「模块发现不到表」）
  - **`meter_count`（默认 1）**：通配请求回几块表，1 = 只回本机地址；>1 时按 `本机+1…+n` 依次回，首帧必为本机地址
  - ⚠ **广播按协议「无需应答」**，本工具为了测试台可见性**仍然应答**；现场若与真实总线上其它表打架，属预期行为（用户口径），不要当成 bug 改回静默
  - **STA 硬件初始化（复位）命令（1.24.9 起，`sta_reset.py`）**：模组固定在工装底座无法断电，异常时用这条 **645 广播写数据帧**代替上下电：
    `68 AA AA AA AA AA AA 68 14 0C 34 37 D3 37 33 6A 3D D3 33 33 33 33 DA 16`（C=14H，DI=04A00401，密码 00370AA0，操作者 00000000）
    - 两个虚拟表都支持：645（协议6）与 698（协议8）页面各有「被测模组复位」按钮下发；`sta_reset.build_frame()` 与现场帧**逐字节一致**（`test_sta_reset.py` 守护）
    - 收到时处置：**广播（AA×6 / 99×6）→ 按 645「广播命令不要求从站应答」静默 + 中文日志**（以前 645 虚拟表会回 D4H 异常帧）；单播 → 回 94H 正常应答（L=00）
    - ⚠ **698 虚拟表必须显式跳过 645 帧**：645 头的 `AA AA` 按 698 长度域解析会变成 0x2AAA≈10924 字节巨帧，缓冲永远等不齐 → 后续 698 请求全部被卡死。`link_layer._is_645_frame()` 用「`buf[i+7]==0x68` + 末字节 16 + CS 求和匹配」识别并跳过，`extract_645_frames()` 供上层处置
- **A-XDR 三处口径（1.23.85 修正，改 `dl_t698_45_axdr.py` 前必读）**：① **`bit-string` 长度域 = 位数**（`04 03 E0` = 3 位、1 字节；旧实现按字节数读 ⇒ 解析上述 doc 帧必崩 `未知类型(0x76)`，因为 0x76 就是 `"v1.0"` 的 `v`）；② **定长类型不带长度域**（`date_time` tag+10 / `date` tag+5 / `time` tag+3 / `date_time_s` tag+7；规范类型表 tag 25/26/27/28 + §7.3.26/7.3.27 + 示例 `1C 07 E0 01 14 00 00 00` = 2016-01-20，**不是**「tag+长度 07+6 字节」）；③ `_encode_bit_string` 只能表达「N 字节 = 8N 位」，而 `bit-string(SIZE(3))` 这种**声明位宽 ≠ 8×字节数**的形态必须由调用方硬编码 `04 03 <byte>`（`build_file_info` 即如此）。改这三处后 `frame_gen_widget` / `reflex_web/frame_gen_utils` 的「A-XDR 自定义」模式已收口为委托 `AXDRCoder.encode`（此前各自手拼、多写长度域）。详见 §8 陷阱 76

- ⚠ **改解析判据前先跑历史版本（1.23.93 现场教训，改 `csg_new_gen_parser` 任何判据前必读）**：现场报「eFC 解析不了」，我在修的过程中把 eFC 判据从 `类型 != 1` 改成 `类型 in (0, 2)`（误读文档中段，认定类型 3 不带 eFC），**把原本正确的类型 3 eFC 解析改坏了**，用户用截图打回「曾经这个帧我是能够解析的」。根因三条：① 只读了文档中段就外推（漏读后面「表29 UL-OFDMA SACK 的 eFC」）；② **动手前没验证历史版本的行为**，不知道「以前能解析」对应的是哪条路径；③ 改判据时没意识到原判据本来就是对的。
  **规矩**：① 改判据前先 `git stash push -- <file>` 跑一次历史版本拿到基线，再 `git stash pop`；② 判据类改动**逐条对照文档全文**（含表格与后续小节），「某类型不带 X」先搜全文确认无第二处反例；③ 修复必须补**回归测试断言「原先能解析的仍能解析」**；④ 既有判据已被 934/49,532 帧 corpus 验证过时**只做加法**（补字段、补说明行），不重写条件表达式（陷阱 41：解析器带跟帧可变状态，判据一改历史行为就变）。

### 5.7 新一代载波协议 / 通感一体化（索引 9，**1.7.0 新增**）

- **解析器**：
  - `csg_new_gen_parser.py` (CSGNewGenParser) — MAC 帧（MPDU/MAC头/MSDU/CRC-32）+ 应用层业务报文
  - `csg_new_gen_cmd_payloads.py` — 应用层命令业务数据单元解析（依据第5部分）
- **校验器**：`validator/csg_new_gen_validator.py`
- **★ 通道以「用户选择」为准，结构判别只服务「自动识别」（1.26.18，用户口径，改通道逻辑前必读）**：
  解析页有 PLC / HRF / 自动识别 三档。**显式选了 PLC 或 HRF，就必须按该通道解析，禁止再用 FC
  可变区域结构反推、更不许用结构结论去反驳用户**（旧实现把下拉值只当提示，还额外打一行
  「下拉通道与 FC 判别不一致，以 FC 判别为准」—— 实测一张明确的 PLC MIMO 帧被反判成 HRF，
  字段全按错表解析，用户明确要求改掉）。落点：
  - `parse_to_table(channel=...)`：`plc`/`hrf` → `self._channel = 所选值`，`_detected_channel=None`；
    只有 `channel="auto"` 才调 `_detect_channel()` 并记 `_detected_channel`。
  - 「通道判定」行：显式选择时写「按解析页所选通道解析（用户选择优先，不做结构判别）」；
    auto 时写「按FC可变区域结构判别（仅「自动识别」使用…）」。**「通道判别」行（不一致提示）已删除**。
  - **单帧解析 vs 批量解析的优先级不同（1.26.19，用户口径，别只记住一半）**：
    - **单帧解析**：人工选的「解析级别 + 通道」**优先于自动识别**（见上条）。
    - **批量解析**：日志里 PLC 报文与 RF 报文混排，**没有任何一种通道/级别能套全文** ⇒
      批量一律 `parse_level="auto"` + `channel="auto"`，**逐帧**识别（`main_gui._batch_parse_params_for()`，
      在 `_start_batch_parse` 入口转换；`_batch_parse_params` 存转换后的参数，保证详情重解析与批量一致）。
      **自动识别的准确率因此是硬要求**，不能拿「用户会自己选通道」当兜底。
    - ⚠ 只有协议9的解析器实现了 auto=逐帧判 PLC/HRF；协议10/11 没有 auto 通道判别
      （HDC 的 `channel` 只认 `plc`/`hrf`，传 `auto` 会全走 HRF 分支）⇒ 批量对它们只归零解析级别。
      另外 **协议 10（国网新一代）是既有缺口**：`GWNewGenParser` 根本不消费 `channel`，
      界面上的通道下拉对它不生效（不报错也不提示）——未定义 PLC/HRF 在 FC 可变区域上的差异前
      **不许**在文档里写「已支持」。HDC 1.0 本来就只按 `kwargs["channel"]` 定表，符合本原则。
  - **`_detect_channel` 的强信号必须带「帧里真有物理块」的前置条件（1.26.19 修，改前必读）**：
    「载荷PB大小=40 → HRF」这条强信号原先无条件提前返回，把**16 字节的 PLC MIMO 帧**
    （`19 01 20 00 04 0B 14 00 E8 03 00 00 20 A4 29 72`，FC 之后没有物理块，PLC 侧「物理块个数=0」）
    误判成 HRF，字段全按表45 解析。现加前置：`frame_len >= 16 + 40` 才认这条强信号，
    否则交给帧长一致性判（`plc_len = 16 + cnt*pb` 命中 16 → plc）。回归：`test_csg_hrf_mac` T7（真 PB40 帧仍判 HRF）与 T10（该 PLC 帧 auto 必须判 PLC）。
  - 回归：`test/test_csg_hrf_mac.py` T9（结构像 PLC 的帧选 hrf → 按 HRF 解析且无「通道判别」行；
    结构像 HRF 的帧选 plc → 出表20 的「物理块个数」；auto 仍按结构判）。
- **GUI 特性**：协议索引 9 时显示解析级别下拉（auto / fc_pb / fc_efc / fc_only / app / pb_only），pb_only 模式可指定 SOF/信标/ACK/NET 帧类型；由 `_csg_parse_level` 控制
- **OFDMA（多站点）帧：通道判别必须先看「多站点帧标识」（1.23.93 修，改 `_detect_channel` / eFC 判定前必读）**：现场帧 `D9 01 F0 FF DF …`（32 字节）报「解析不了 eFC」，实际是三个坑叠加：
  - ① **通道被误判成 HRF**：`_detect_channel` 用「预测帧长 == 实际帧长」投票，而 OFDMA 帧的 FC 布局（表26）与单站点完全不同 —— ISAC 单站点公式按 `var[3]` 取「物理块个数」得到 7（实际是多站点标识+OFDMA类型），预测 968 字节；HRF 假设默认 16 字节 PB ⇒ 预测 32 字节**恰好命中**，于是整帧按 HRF（表45）解，OFDMA 与 eFC 全丢。修法：**`var[3] & 0x01`（多站点标识）为 1 时直接判 `plc`**（OFDMA 是载波侧多站点调度，HRF 是点对点无线）
  - ② **ISAC 分支不解析 OFDMA 可变域**：`_parse_mpdu_sof_isac` 里 `if multi_site:` 只有 `pass`（BPLC 分支才实现），ISAC 版 OFDMA 帧被按单站点帧解、字段全错位。修法：抽出共享方法 `_parse_ofdma_variable`（表26，BPLC/ISAC 同构），两个分支都调用；**只允许一处调用**（早先两处叠加会导致 OFDMA 行重复两份）
  - ③ **eFC 携带规则只能按 `类型 != 1`**（**别想当然把类型 3 也排除**）：文档「OFDMA帧类型不同，携带的eFC内容不同」只有一句 **「类型 1（DL-OFDMA 的 SACK / UL-OFDMA）不携带 eFC」**；类型 0/2/3 各有 eFC 定义 —— **表27**（DL-OFDMA）、**表28**（UL-OFDMA trigger）、**表29**（UL-OFDMA 的 SACK，每站点 3 字节：TEI 12b + 接收状态 4b + 保留 8b）。1.23.93 修复过程中我一度把「类型 3」也当成不携带 eFC，结果这帧依旧看不到 eFC（**已被现场截图打回**）。判据保留 `_ofdma_frame_type != 1`，并新增一行「eFC携带判定」把四种类型的依据写出来
  - 该帧正确结果：多站点帧=1、OFDMA类型=3（UL-OFDMA SACK）、站点数=4、**携带 eFC**（表29：站点0~3 的 TEI=2/3/4/5、接收状态均为 `PB0:OK PB1:FAIL`、CRC-24 通过）、通道=plc
  - ⚠ 类型 3 的 eFC 与「物理块」在长度上**同为 16 字节且都用 13+3 的 CRC-24 尾**，单看 CRC 自证无法区分；区分只能靠 FC 的 OFDMA 类型。类型 1 的帧才是「FC 之后直接物理块」
  - 回归：`test/test_csg_new_gen.py::test_ofdma_ul_sack_efc`（auto 与 fc_efc 两档：识别多站点 / 类型3 / 站点数4 / **携带 eFC** / 判 plc / 表29 四个站点 TEI=2~5 与接收状态 / eFC CRC 通过 / OFDMA 行只一份）
- **组帧页（1.23.64 新增）**：协议9 也支持「协议组帧」（`protocol_registry` 的 `frame_gen_mode="csg"`，`preset_mode` 保持 `None`）。组帧页左栏是 `QStackedWidget`：第 0 页常规动态表单、**第 1 页协议9 链路层组帧**（`csg_test_frame_gen_widget.CsgTestFrameGenWidget`）。五层折叠表单：①FC 帧控制 / ②物理块 PBH+PBCS / ③MAC 帧头 / ④MSDU / ⑤ED 封装；进页面默认勾选「组装链路层」、默认帧类型 **SOF 帧**
  - 组帧器 `csg_link_frame_gen.py`（`put_bits_le` ↔ 解析器 `_extract_bits` 严格互逆；FCCS / PBCS 为 CRC-24，MAC 帧尾 ICV 为 CRC-32，全部自动算）+ 复用 `csg_new_gen_frame_gen.py` 的 **25 个测试模式**（1.23.77 新增 2.0 测试扩展 `0x0009`「报文聚合传输测试模式」：`报文聚合数目` 1 字节，解析/组帧/仿照回填/摘要四处同构）
  - 定界符三型：**SOF**（BPLC / ISAC-PLC 两版本、长/短 MAC 头、多物理块）｜**信标**（FC 后直接载荷，无物理块与 MAC 头）｜**选择确认帧 SACK**（仅 FC 16 字节）
  - 输出层次四档：`ed`（ED..EE 封装，推荐下发）/ `app`（应用层帧）/ `bdu`（仅测试帧数据单元）/ `mpdu`（整帧 FC + 物理块）
  - **协议9 无预设命令库** ⇒ 预设命令页不显示（可见性按 `preset_mode` 判定，见陷阱 65），组帧页「添加到预设」按钮隐藏
  - **仿照报文回填（1.23.65 新增，⓪ 折叠区）**：粘贴一帧现成报文 → `csg_frame_reverse.reverse_frame()` 反解出各组帧参数 → 回填表单 → 只改要变的字段再生成。分层：ED..EE 封装（plc2 / 广西台体）→ 整帧 MPDU → ①FC ②物理块 ③MAC 头 ④MSDU → 应用层帧 → 测试帧 BDU；**字段取值一律以解析器行（`parse_to_table`）为唯一基准**，用「偏移区间」区分 FC(0~15) / 物理块头(16~19) / MAC 及以内(≥20)，避免 `源TEI` 这类同名标签串味。长字段（MSDU 负载 / 物理块体 / B 表）的「原始值」列会被解析器用 `...` **截断**，必须按 `偏移~结束偏移`（第 5 列是**闭区间**末偏移）从原始字节切
  - **回填后必须逐字节反证**：GUI 侧用真实组帧路径重建一次并与原帧对比（`csg_test_frame_gen_widget._verify_against`）；表单表达不了的字段（报文标识符非 `0x0101`、业务标识非 `0xF0`、保留位非 0）记入 `unmapped` 并按「手工 HEX 保真」兜底（把原 MSDU 载荷写进 ④ 区手工载荷），提示里明确说明"此后改应用层/模式参数不影响载荷"
  - **模板本地存储**：`csg_frame_templates.py` → `csg_frame_templates.json`（`app_paths.data_path`，已 gitignore），存完整参数集 + 原始参考报文 + 状态摘要；「临时文件 + `os.replace`」原子写，读取对坏文件宽容。state 口径由 `csg_test_frame_gen_widget.frame_state()` / `apply_frame_state()` 定义（`apply` 的顺序不能改：**先切帧类型/标准版本/模式**——它们会重建字段控件——**再写字段值**）
  - **右栏「显示响应解析」开关**：协议9 是纯组帧场景，进页面强制收起（把高度让给实时解析预览），其它协议按用户偏好显示；`_apply_resp_visibility()` 只覆盖显示状态、不改偏好
  - 回归：`test/test_csg_frame_gen_gui.py`（139 项，offscreen GUI 端到端）+ `test/test_csg_link_frame_gen.py`（176 项）+ `test/test_csg_frame_reverse.py`（96 项，纯逻辑）+ `test/test_csg_frame_templates.py`（92 项）+ `test/test_csg_test_ext_0009.py`（76 项，2.0 测试扩展 `0x0009` 解析/组帧/回填/摘要）+ `test/test_collapsible_section.py`（51 项）
- **解析重点**：支持多物理块重组、聚合帧级联块应用层解析、NET 帧可变区域解析；批量解析支持监控日志前缀剥离与业务摘要；ED..EE 包装的数据域若为《测试装置通信控制协议V1.1》工装板/功能驱动板控制帧，也由协议9解析器识别展开
- **批量前缀剥离必须放行「测试装置控制帧」（1.23.87 修，改 `_strip_csg_new_gen_frame_prefix` / `batch_core.strip_csg_new_gen_frame_prefix` / Web `web_utils.strip_csg_new_gen_prefix` 前必读）**：工装板/功能驱动板控制帧（`FE×n + 05 地址 命令码 6字节数据 校验`，功能驱动板以 `AA 0D 0A` 结尾）**没有 FC 起始签名**、也大多不以 `ED` 开头（现场常直接贴裸帧，如 `FEFEFE0501051400000000001AAA0D0A` = 台体控制衰减器）。此前剥离层的 FC 扫描判定「无有效起始」把它**整行丢弃** → 批量弹「预处理后未保留有效报文内容！」，而**同一帧单帧解析正常**（`parse_to_table` 第一步就优先判它）。三条不可拆：
  - 判据是**解析器里的单一实现** `csg_new_gen_parser.is_test_device_control_frame(data)`（入参同时收 `bytes` 与纯 hex `str`，判据内部复用 `_parse_test_device_control`）；**禁止**在剥离层另写一份帧格式判据（陷阱 31 的漂移根因）。
  - 三处剥离实现（桌面 `main_gui`、共享 `batch_core`、Web `web_utils`）都要有该分支 —— 它们目前是**三份同源副本**，改一处必须三处同改（残留的重复本身就是漂移风险，见「已知待办」）。
  - 只在 `auto / fc_pb / fc_only / fc_efc / pb_only / mac_only` 放行；**`app` 级别刻意不放行**（用户已声明「输入即应用层报文」，控制帧不属该级别）。
  - 回归：`test/test_csg_batch_parse_level.py`（新增 5 项：整行保留 / 端到端解析出「命令码=衰减器C」/ app 级别不放行 / 非帧行仍丢弃 / 共享 `batch_core` 同口径）、`test/test_csg_test_device_control.py`（判据正反例）、`reflex_web/tests/test_csg_ed_control.py`（Web 同口径 + 端到端）。**变异反证 2 条**：判据恒 False → 三层全红；只改坏 `batch_core` 分支 → 该层单独变红（各副本独立覆盖）。
- **测试装置控制帧的**批量摘要**必须给「命令专属解析值」（1.23.87 修，改摘要前必读）**：用户报障「解析摘要里居然没有衰减值」—— 此前这类表落到 `_get_csg_new_gen_summary` 的**兜底分支**，只取了 `table_data[:4]` 的**说明文案**（结果长成「射频信号切换/衰减控制（9600 8N1…） | 数据帧开始 | 00=广播预留，01=工装板默认地址 | 测试装置通信控制协议 V1.1」，**核心值全丢**）。三条：
  - 共享单一实现 `batch_core.test_device_summary(table_data)`（桌面 `_get_csg_new_gen_summary` 与 Web `get_frame_summary` 都调它，**禁止再写第二份**）；摘要格式 = `命令名 | 命令专属行=解析值…`，例：`衰减器C | 衰减器C衰减值=20 dB`、`设置引脚状态/衰减器A | CCO仓引脚控制=…；STA仓引脚控制=STA1；RST=高电平；EVENT=高电平`。
  - 「命令专属行」用**排除法**识别（跳过 `起始字符/帧头/地址/命令码/校验和/结束符` 与 `数据项字节N`），因此**解析器新增命令时摘要自动跟随**，不要在摘要层再维护一张命令表。
  - **ED..EE 包装的控制帧不接管**（表里同时有包装头行与控制行）：那类仍走既有 ED 摘要分支（含包装名 + 业务帧核心值），抢过来会丢包装上下文 —— 回归 `test_web_summary_contains_control_state` 钉住这一点。
  - 回归：`test/test_csg_summary.py`（+3 项：5 类控制帧核心值 / 无噪声行 / 反例普通帧不被污染）、`reflex_web/tests/test_csg_ed_control.py`（+1 项 Web 摘要）。**变异反证**：摘要不接管（恒返回空）→ 桌面与 Web 两项同时变红，且举证输出正是改前那段无核心值的文案。
- **信标条目解析的实机差异（2026-10-08 实测，改动前先读）**：
  - **`0x10 代理角色条目` 实机按 1 字节长度字段发送**（表59/表72 写的是 16 比特）：按规格宽度读会得到 `04 60 → 0x6004 = 24580` 这类荒谬长度，把其后全部字节（含后续条目）吞成「代理角色条目 28字节 / 代理站点数 14」。`_parse_beacon_entries` 现按表59 宽度读，仅当**声明值超出剩余字节**时退回 1 字节重读（声明值合法时仍按表59），并在该条目「条目长度」行注明「长度字段实发 1 字节」；`0x00`（表59 非法值）处停止，不再把补齐/校验序列当条目
  - **帧载荷校验序列不再无条件取末 4 字节**：旧逻辑先切掉末 4 字节再解析条目，输入若是**裁剪过的 PB 载荷（到最后一个条目为止、不含 BPCS）**，就会把最后一个条目的末 4 字节吞掉（实测该帧末 4 字节是 `0x02 时隙分配条目` 的 CSMA时隙信息）。现改为先按条目解析定位条目末尾，再在剩余字节里取末 4 字节（`_beacon_tail_rows`），无剩余字节时明确提示「未包含」、剩余多于 4 字节时注明补齐字节数
  - **表62 时隙分配条目字段偏移**：RF信标时隙长度在信标周期长度（条目字节 19-22）之后，占条目字节 **23-24**（表62 该行印成 22/23，与信标周期长度重叠，属文档笔误）；固定区共 24 字节，其后才是按 `非中央信标时隙总数×2 + CSMA相线个数×4 + 绑定CSMA相线个数×4` 展开的可变长时隙信息区（解析器给「可变长时隙信息」行）
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

### 5.10 模组化终端功能模块接口（索引 12，**1.23.57 新增 / 1.23.58 重写 A-XDR 层**）

- **解析器**：`modular_iface_parser.py` (ModularIfaceParser) — 链路层 + 8 类 APDU + DT 命名 + 容错 ⚠ 行；`parse` / `parse_to_table` / `get_summary` / `is_frame` / `calc_fcs` / `data_total_len`
- **A-XDR 层（单源）**：`modular_iface_axdr.py` — 表4 全部类型、8 类 APDU 的 ASN.1 编解码、`date_time`/`date`/`time`/`date_time_s`/`Scaler_Unit`/`bit-string`/数组/结构、附录 A 的 `FCSTAB`+`calc_fcs`、`frame_layout`、`verify_frame`
- **静态表（单源）**：`modular_iface_data.py` — 附录 B（VID/PID）、附录 C（通用信息类 10 条）、附录 D~L（设备子接口表）、附录 G/J/K/L（模块信息类 11 条）、附录 M（物理单位 77 条），以及表1/2/3/5/11/13；`decode_dt`（大端，返回 dict）唯一 DT 名称来源
- **组帧**：`modular_iface_frame_gen.py` — 整帧/ACK/NAK/8 类 APDU 编码 + `FRAME_TEMPLATES`（**13 个**模板）；GUI 组帧页已接线（`frame_gen_mode="modular"`），预设页 `preset_mode="modular"` 用 `MODULAR_command.json`（种子 8 条）
- **校验器**：`validator/modular_iface_validator.py` — FCS = CRC-16/PPP(x-25)，覆盖 `L + C + Data`（附录 A，与 698 同族）；另有控制域/长度域/控制码/APDU 解析检查
- **批量提取**：`extract_strategy="modular"` → `main_gui._extract_modular_frames`（**L 是数据域长度，整帧 = L + 8**，与南网/国网的「L 即整帧长」不同）
- **查询页**：`lookup_kind="modular"` → `_create_modular_iface_lookup_content`（控制码 / APDU / DTA / 通用信息类 / 模块信息类 / 物理单位 / 设备子接口 / 厂商标识）
- **参考文档**：`协议文档/12.模组化功能协议/模组化终端功能模块接口协议.md`（anydoc 自同名 .docx 转换，1136 行）
- **⚠ 两层字节序不同**：链路层 `68 | L(2B LE) | C(2B LE) | Data | FCS(2B LE) | 16` 是**小端**；APDU 内的 DT/整型/`date_time` 属 **A-XDR → 大端**。两者不可互相套用（1.23.57 的原实现即因此错位）
- **回归**：`test/test_modular_iface.py`（430 项）+ `test/test_modular_iface_axdr.py`（185 项）；契约与错误排查见 §8 陷阱 61

---

### 5.11 南网上行通信规约（索引 14，**1.23.68 新增 / 1.23.69 修正长度域 / 1.23.70 网管扩展 + DI 字节序**）

- **协议**：Q/CSG 11109004-2013《计量自动化终端上行通信规约》（南网 2013 版上行规约，与索引 0 的 Q/CSG1209021-2019 本地模块规约、索引 7 的国网 10376.2 同族但字段不同）
- **帧格式**（5.1.1 图2）：`68H | L(2B 小端) | L(同值，重复一次) | 68H | C(1B) | A(7B) | 链路用户数据 | CS(1B) | 16H`；`L = 控制域+地址域+链路用户数据 = 8 + 应用层`，**长度域线上 4 字节、整帧 = L + 8**；`CS = (控制域+地址域+链路用户数据) 模 256 和`（5.1.5）
- **⚠ 长度域 4 字节的证据链（1.23.69 修正，此前误按「单 2 字节 L」实现）**：① 5.1.2 + 图3 规定 L 是 **2 字节** 16 位（网络上限 16383 亦需 16 位）；② 图2/图11/图12 的固定报文头逐行画出 `68H / L / L / 68H`，而**图中一行即一个字段**（同图内 A(7B)、信息点标识(2B)、数据标识编码(4B) 各占一行），故两个 L 是两个字段；③ 条文解释「长度L由两个字节组成，两个重复的长度L必需完全一致，否则此帧为无效帧」+ 5.2.1「识别2个长度L」；④ 5.2.1「每帧接收的字符数为用户数据长度 L+8」= 68H(1)+L(4)+68H(1)+CS(1)+16H(1)。**四条互证，无一条需要「文档写错」来解释**
- **切帧/解析容错**：`resolve_layout()` 按「结构 + 声明整帧长 + CS + 末字节 16H」在三种形态间择优 —— 规范 4 字节（`l16x2`）→ 单个 2 字节小端（`l16`，历史报文）→ FT1.2 双同值单字节（`ft12`）；**规范形态优先**。组帧 `encode_frame()` 只输出规范形态；解析摘要 `last_meta["len_form"]` 给出实际形态
- **控制域 C**（5.1.3 图4）：D7 DIR / D6 PRM / D5 FCB(PRM=1)|ACD(PRM=0) / D4 FCV(PRM=1)|保留 / D3~D0 功能码（PRM=1 表2、PRM=0 表3）
- **地址域 A**（5.1.4 表4）：A1 省地市区县码(3B **BCD**，线上低字节=区县码在前) + A2 终端地址(3B BIN 小端，0 无效/FFFFFF 广播) + A3 主站地址(1B BIN)
- **应用层**（6.1 图5）：`AFN(1B) | SEQ(1B) | 信息体×N | [PW(16B)] | [Tp(5B)]`；SEQ D7 TpV / D6 FIR / D5 FIN / D4 CON / D3~D0 PSEQ|RSEQ；信息体 = `DA(2B: DA1 信息点元 + DA2 信息点组) + DI(4B) + 数据标识内容`；`pn = (DA2-1)*8 + bit + 1`
- **AFN**：00 确认/否定、01 复位、02 链路接口检测、04 写参数、06 身份认证、0A 读参数、0C 读当前数据、0D 读历史数据、0E 读事件记录、0F 文件传输、10 中继转发、12 读任务数据、13 读告警数据、14 级联命令、15 用户自定义数据
- **DI 单源**：`csg_uplink_di.py`（附 A 终端参数 / 附 B 测量点参数 / 附 D 告警 / 附 E 事件，共 282 条，由 `tools/gen_csg_uplink_di.py` 从条文解释 PDF 用 pdfplumber 抽取；**网管扩展并入 14 条**、另 2 条与附 D 同号合并，共 **296** 条）；**附 C 测量点数据**沿用 DL/T 645-2007 数据标识（附 C.2 首句「支持 DL/T 645—2007 中的数据标识，传输时不加 33H」）→ 复用 `dlt645_di.json`
- **协议文档**：`协议文档/14.南网上行通信规约/中国南方电网有限责任公司计量自动化终端上行通信规约(条文解释).md`（+ PDF，2013 版）；`协议文档/14.南网上行通信规约/新一代计量自动化主站通信网络管理技术要求.md`（+ 同名 .docx，网络管理/深化应用扩展，**由 .docx 用 markitdown 转换**，含第 4 章拓展 DI 与 13 条实帧）
- **⚠ 数据标识 DI 线上字节序 = 低字节在前**（1.23.70 修正）：表 `E1 00 60 12` 上线为 `12 60 00 E1`。依据：网管扩展文档 13 条实帧（send/rec 成对、CS 全部自洽）+ 5.1.1「低字节在前，高字节在后」+ 协议0（`protocol_parser` 用 `di_bytes[::-1]`）与 DL/T 645 同族约定。索引键一律**表序**（DI3 DI2 DI1 DI0），换算用 `csg_uplink_di.to_semantic_di()` / `to_wire_di()`；解析表并列显示「原始值=线上顺序、解析值=表序」；组帧 `InfoBody.to_bytes()` 自动转线上序
- **网管（深化应用）扩展**（1.23.70 新增，文档第 4 章「终端上行规约（针对网络管理扩展）」）：单源 `csg_uplink_nm.py`（16 条 DI 记录 = 文档 15 个扩展 DI + 4.5 实帧别名 `E1006014`；含枚举 + 结构化解码 + 前缀规则），由 `csg_uplink_di` 合并进 `DI_ENTRIES`（`appx="N"`，同号 DI 如 `E2000033/34` 与附 D 名称合并）。DI 清单：`E08004xx` 通信模块台账（65B/14 项）、`E1006012` 入网从节点（3+6n）、`E1800052` 组网成功率（BCD×100）、`E1006009` 周边节点信道（3+16n）、`E1006004`/`E1006014` 网络拓扑（5+19n）、`E1006015` 模块类型+离线时长、`E2000033/34` 掉电/上电（ARD2）、`E1006005` 多网络信息、`E0000040` 频段、`E1006008` 入网被拒（3+6n）、`E1006010` 节点自检、`E0000041` 从节点重启、`E1006013` 并发数、`E1006016` 远程模块网管（21 项，**报文字段高位在前**）。解码结果按字段展开成解析表子行（`    ↳ 字段`）；`content_length(di, data)` 支持变长列表按内容推算，多信息体可正确切分
- **⚠ 两处文档自身的出入（已按“并存 + 标注”处理）**：① 4.5 表列 DI0=`04`，而其 send/rec 实帧用 `14`（两条都收录，`E1006014` 名称已标注）；② 4.1 的 send 实帧控制域为 `4BH`（功能码 0BH=请求 2 级数据）而同帧 SEQ 的 CON=1，与 5.1.3.6「CON=1 → 功能码 0AH」不符（其余实帧自洽；组帧页按 5.1.3.6 生成 `4AH`，若要逐字节复现 4.1 实帧用 `build_frame(c=0x4B, …)`）
- **组帧**：`csg_uplink_frame_gen.py`（`build_frame`/`InfoBody`/`templates`，线格式统一走 `csg_uplink_wire.encode_frame`）+ `csg_uplink_frame_gen_widget.py`；`frame_gen_mode`/`preset_mode="csg_uplink"`，预设库 `CSG_UPLINK_command.json`（6 → **11 条**种子，含 5 条网管扩展）
- **回归**：`test/test_csg_uplink.py`（**126 项**：线格式三种长度域形态 / DI 索引 / 网管扩展解码 / 解析 / 校验 / 组帧 / 注册表，含文档 13 条实帧 valid + 7 条 send 实帧逐字节复现）

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
- 光伏升级（协议8 文件传输升级+可选读版本信息）：`has_upgrade`，仅 698.45(8)；tab 文案 = 「光伏升级」
- 协议测试（协议8 按 OAD 分类的预置测试库）：`has_test`，仅 698.45(8)；tab 文案 = 「协议测试」，紧随「光伏升级」之后
- 645协议测试（协议6 按 DI 大类分类的预置命令树 + 读/写地址）：`has_dlt645_test`，仅 DLT645(6)；
- 国网协议测试（协议7 按 AFN/Fn 分类的预置命令树 + EB 扩展）：`has_gdw_test`，仅国网(7)；
  tab 文案 = 「国网协议测试」，紧随「645协议测试」之后
  tab 文案 = 「645协议测试」（紧随「协议测试」之后）；**与 `has_test` 分开**（698 语义与既有断言不变）
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
python test/test_dlt645_pv_ext.py    # 协议6 光伏协议转换单元 645 扩展协议（156 项：682 DI 表驱动全覆盖 / 功率符号位含边界 / 单相 FF / DI0 双语义 / 事件块逆变器字节序 / 0F·8F 透传含二次展开 / 歧义行存疑 / 组帧守卫 / 桌面·Web 两端一致，1.23.21 起）
python test/test_dlt645_tolerant_parse.py # 协议6 容错解析（135 项：CS 错/长度不符/结构错仍完整解析 + 提示正确 CS 值与计算规则 / 长度<12 降级 / valid 语义不变 / GUI 偏移落在 CS 字节 / 合法帧逐行不变，1.23.22 起）
python test/test_sta_reset.py       # STA 硬件初始化（复位）命令（27 项：现场帧逐字节复现 / DI 识别 / 645 广播静默·单播94H / 698 收帧不被645帧卡死；1.24.9 起）
python test/test_meter_sim.py       # 698.45 虚拟表从站模拟器（85 项：自组帧自解析闭环/NormalList/Record/安全MAC/通配多表/名单/递增/漏点/粘包分片/寻址与应答（通配 AH 位/广播/全99/本机地址），1.16.0 起）
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
python test/test_modular_iface.py   # 模组化终端功能模块接口（组帧→解析闭环/FCS/DT/模板/摘要接线，430 项，1.23.57 起）
python test/test_modular_iface_axdr.py # 模组化 A-XDR 编解码（表4 逐条/698 附录 H.1.1 独立 oracle/fcstab 对拍/verify_frame，185 项，1.23.58 起）
python test/test_hdc10_app_dispatch.py # 协议11 应用层分派收口（94 项：MAC 头类型字段判据 / 端口白名单收口 / 未定义业务命名与依据 A13 表驱动 / 安全模式提示 / 真实帧 60 帧分派一致性 / fuzz，1.23.20 起）
python test/test_hdc10_pb_structure_probe.py # 协议11 无物理块头(PBH)帧形态探测（39 项：现场帧 auto 17→57 行 golden / ICV 自证 / fc_mac 偏移修复 / 探测判据纯函数 / 变异反证 / 真实夹具 60 帧×7 级别零差异，1.23.24 起）
python test/test_hdc10_mac_only_contract.py # 协议10/11 仅MAC帧契约：输入即MAC帧禁止剥PBH（35 项：现场帧 golden / GUI 包装 / bit7前缀变异反证 / pb_only 仍解析 PBH，1.23.29 起）
python test/test_gw_pb_mme_summary.py # 协议10/11 批量摘要网络层 MMTYPE（13 项：pb_only/auto/两协议字段名/Web 同口径，1.23.30 起）
python test/test_ed_ui_for_gw_hdc10.py # 协议9/10/11 共用 ED 勾选+4字节反转+剔除（25 项：注册表能力/可见性/解包/反转/报错，1.23.35 起）
python test/test_ed_wrapper_labels.py # ED 包装头文案按协议分语义（19 项：协议9=广西/PLC2.0，10/11=国网HDC，1.23.36 起）
python test/test_tcp_monitor_ed_hdc.py # TCP 监控 HDC 1.0 + ED 封装（15 项：FlowBuffer 整帧/协议11 国网HDC 文案/业务解析，1.23.37 起）
python test/test_btn_width_fit.py     # 按钮文字被裁回归（66 项：两个取宽函数纯逻辑（含未设上限 / 不降既有下限断言）/ 真机布局 10·12·14 号字不裁字且等宽 / 反例自检（改回 80px 必红）/ 动态文案按钮走真实勾选动作 / 运行中切字号·切主题 / AST 静态守卫含正负样例自检，1.23.59 起）
python test/test_beacon_ed_hdc10.py # 协议11 ED 信标帧现场样本（20 项：帧长域异常解包/中央信标/摘要，1.23.38 起）
python test/test_gw_parse_levels.py # 国网新一代解析级别（mac_only 按「输入即MAC帧」契约，pb_only 仍解析 PBH）
python test/test_gw_batch_parse.py  # 国网新一代批量解析
python test/test_gw_ext_cmd.py      # 国网新一代扩展命令载荷
python test/test_gw_parse_levels.py # 国网新一代解析级别
python test/test_gw_monitor_summary.py # 国网新一代监控摘要
python test/test_sack_fix.py        # SACK 帧解析
python test/test_ed_fallback_fix.py  # ED..EE 监控帧非法回退修复（1.11.1 起）
python test/test_dl_t698_45_fujian.py # 698.45 福建简化698（choice=0x02 List）解析
python test/test_dlt698_testbench.py # 协议8 协议测试页（1.23.93 起，279 项：附录 H 六条组帧 golden 逐字节 + HCS/FCS 自解析 + L+2 自洽 / OAD·OMD·PIID / date_time_s / SA / RSD·RCSD / 分类库 777 项与记录型筛选 / 响应判定含 DAR·列表·记录·CONNECT 不冒充 / 地址与时间提取 / 筛选 / offscreen 页面与发送队列·超时重发·终止 / 读地址回填 / OAD 覆盖 / 落盘与 cleanup / RX 半帧与噪声重同步 / 主题 / 源码护栏）
python test/test_dlt698_test_tab_wiring.py # 协议测试页 main_gui 接线（22 项：has_test 只属协议8 / 页签标题与位置 / 协议显隐 / 懒加载 / 串口注入 / 远程升级跳转 / 主题 / 收尾不关串口，1.23.93 起）
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
python test/test_github_issue.py        # GitHub Issue 提交（与仓库 yml 模板逐字对拍/API 建单与错误码/令牌优先级与脱敏/崩溃摘要脱敏/offscreen 对话框，32 项，1.23.94 起）
python test/test_downloader.py          # 多线程分段下载（分段规划/并发字节一致/断点续传/暂停·继续·取消端到端/失败不留半截文件/url 变更作废/Content-Range 自证/单流续传/磁盘中文提示/Retry-After 夹上限，42 项，1.23.95 起）
python test/test_update_download_dialog.py  # 下载面板（非模态守卫/逐线程进度/速率/暂停取消/后台运行/状态文案随 state/大字号不裁字/宿主级重入守卫·菜单重开·状态栏清理，26 项，1.23.95 起）
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
    **mac_only 契约（1.23.29 起，协议9/10/11 统一）**：`mac_only` 的输入**就是 MAC 帧**，解析器从**字节 0** 直接解析，**禁止**探测/剥离物理块头(PBH)。协议10 曾误走 `_parse_pb_by_frame_type`（输入按 PBH+MAC），协议11 曾在 `data[0]&0x80` 时自动剥 1 字节——两者均已改为从 0 解析；需要带 PBH 的输入请用 `pb_only` / `auto`。回归：`test/test_hdc10_mac_only_contract.py`、`test/test_gw_parse_levels.py`。
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
    - **PBH 剥离判据**：MAC标准头 b0 bit7 恒为0（源TEI≤0x7FF），b0 bit7=1 必为 PBH——**仅 auto/fc_pb 等「FC+未知形态PB」路径**可用探测；**mac_only 不得剥离**（陷阱19）。PBH 低4位=0 与 MAC版本0 冲突，**不能用 ver 位区分**
    - MME 头为 **4字节**（表58：MMTYPE 2B + 保留 2B），不是3字节；MME 解析器 offset 参数是切片内相对索引，切片后传 0
    - 实机明文模式 ICV 可能填全0（此时校验必然"失败"），应显示"明文填充"而非报错
29. **HDC 1.0(索引11) 真实报文回归测试**：`test/test_hdc10_real.py` 使用 TMI 遍历测试日志提取的 119 个真实 PB 帧（`test/hdc10_real_frames.pkl`）。修改 `hdc10_parser.py`/`hdc10_mme_parser.py` 后必须运行该测试——组帧只能覆盖想象结构，真实日志才能暴露实机与文档差异。原始数据源：`国网新一代协议/HDC-国网双模协议/TMI模式遍历测试_频段1__All.log`（4500+ 条 `Origin sof pb:'<hex>'` 行）。
30. **ED..EE 监控包装格式判别是解析器层单源**（1.23.12 起）：PLC2.0（9B 公共头）与广西台体（gx，8B 公共头）的判别与两套字段偏移都在 `csg_new_gen_parser.detect_ed_wrapper` / `_parse_ed_wrapper`，桌面 `main_gui._detect_ed_wrapper` 仅委托（手动下拉值作 `fallback`）。改 ED 相关逻辑时不要再在调用方写第二份打分或偏移表；摘要侧判定按「字段名含 `监控包装头`」而不是 `PLC2.0`（否则 gx 帧摘要掉到兜底分支）。`parse_to_table(..., ed_wrapper=...)` 可显式覆盖自动识别。
31. **Web 与桌面解析链路的复刻风险**（1.23.12 记录，待 `09-15-web-shared-parse-core` 收口）：`reflex_web/reflex_web/web_utils.py` + `lookup_utils.py` 与 `main_gui.py` 仍存在多份同义实现（前缀剥离/帧提取/摘要主体/字段层级/查询数据源），历史上已发生漂移（协议10 摘要用协议9 函数、Web 独有 `get_hdc10_summary` 键名不匹配恒不命中、协议10 查询页抄协议9 表、南网 AFN 列算成 `di3 & 0x0F`）。改这些逻辑时必须**同时改两侧**并在 `test/test_web_parse_fixes.py` 补对拍断言，直至共享核心任务落地。
    - **已收口（1.23.42 起，勿再复制）**：① **645 转表**——唯一实现在 `protocol_registry.DLT645GuiParser`，Web 走 `reflex_web._safe_parse_to_table` 的 import（守卫 `test/test_dlt645_table_offsets.py`）；② **测试模式摘要片段**——唯一实现在 `batch_core.extract_test_mode_content`（桌面一行转发、Web 直接 import，对拍 `test/test_web_gui_parity.py`）。审计清单见 `docs/Web与GUI同步审计.md`（1.23.0~1.23.22 逐条判定 + 7 项待补缺失）。
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
43. **协议10/11 共用「解析级别」下拉但属性独立；批量前缀剥离必须与解析侧同源取级别**（1.23.17 起）：`main_gui._strip_gw_new_gen_prefix` 早期硬读 `_gw_parse_level`（协议10 的值），而协议11 的级别在 `_hdc10_parse_level`（`_on_gw_parse_level_changed` 按 `current_protocol` 写不同属性，界面共用同一个 `gw_parse_level_combo`）。后果：在协议10 下选过「应用层报文(app)」后切到协议11，**界面显示「自动识别」而批量剥离却按 app 过滤**；`12` 开头的 HDC 1.0 升级业务帧（端口 `0x12`）里没有偶字节 `11` → 整批被丢弃，弹「预处理后未保留有效报文内容！」（用户现场报障：`Line NNNN: 时间戳: B1D[3] mrd:ar[24]:<hex>` 一帧都解析不出）。规则：
    - 级别**只能**经 `_current_parse_params()` 取（`parse_level=None` 的默认分支已如此实现），**不要**在剥离函数里再写第二份 `if current_protocol == 11` 分派；
    - app 级别的帧起始判据是**应用层端口集合** `{0x11, 0x12, 0x1A}`，集合**取自解析器端口表**（`hdc10_parser.APP_PORTS` / `gw_new_gen_parser.GWNewGenParser.PORT_NAMES`）；依据《双模通信互联互通技术规范 第4-3部分：应用层通信协议》§5.2.2（升级业务 0x12、其他业务 0x11）。**不要再硬编码只认 `11`**；
    - Web 侧 `web_utils.strip_gw_new_gen_prefix(text, parse_level, protocol_index)` 与桌面**同判据同来源**，`test/test_hdc10_batch_strip_level.py` 内有对拍断言防漂移（含「端口集合必须含 0x12」与「协议10 残留 app 不影响协议11」两条回归，已用变异反证确认能抓住回退）。
    - **新增调用方注意**：`_strip_gw_new_gen_prefix` 现在依赖 `_current_parse_params()`，而后者在 `family ∈ {gw, hdc10}` 且级别为 `pb_only` 时会读控件 `gw_pb_frame_type_combo`。目前只有 `_prepare_batch_input` 的两个主线程调用点（UI 已就绪，安全）；**无控件上下文的调用方**（Host/headless 测试、命令行路径）必须**显式传 `parse_level`**，否则会 `AttributeError`。
44. **协议10/11 应用层摘要 = 业务名 + 前 2 个关键业务字段；提取规则单一来源、两端同规则**（1.23.18 起）：批量摘要的「应用层报文」段由 `_gw_app_biz_summary`（桌面 `main_gui` 与 Web `web_utils` 各一份，**规则逐字一致**）产出——**业务名**两优先级：① `── 业务数据 ──` 区头之后首个带缩进行的字段名（协议11 布局，如 `开始升级`）；② 「报文ID」解析值非 hex 时即业务名（协议10 布局）；**关键字段**取**应用层/业务数据段窗口内**带缩进、非元数据、非分隔/业务名行、解析值非空且非「N字节」占位的前 `_GW_APP_SUMMARY_KEY_FIELDS`（=2）个。改这块时注意：
    - **扫描窗口是必需的，不是优化**：起点 = `── 业务数据` 行 +1（优先；协议11 业务名与业务字段都在该区内），无该区头时 = 顶层「应用层报文」行 +1（协议10/auto 布局）；终点 = 起点之后首个**顶层行**（无缩进）或表尾。**全表扫描会中招**：真实 MPDU 在默认 auto/fc_pb 级别下 FC/MAC 字段（`版本`/`原始源TEI`/`定界符类型`/`网络类型`）排在应用层之前会占满关键字段位（复核用 `test/hdc10_real_frames.pkl` 实测修复前 6/6 带应用层的表全中、修复后 0/6）；
    - **仅应用层报文（有 `报文端口号` 或 `报文ID`）才提取**（第二道守门）：纯网络层/物理层帧不该出现业务段；
    - 元数据黑名单 `_GW_APP_META_FIELDS` 是**两协议字段名并集**（协议10 叫「安全机制」、协议11 叫「安全模式」；含 `转发数据长度`/`转发数据规约类型`）——新增协议字段名时必须补进去，否则它会挤掉真正的业务字段位（注意 `startswith` 方向：`转发数据长度` 不以 `数据长度` 开头，必须单独列出）；
    - 桌面口径是「去缩进后字段名精确相等」（`val()`）；Web 的 `_find_field` 是**子串包含**（会把「业务报文ID」当「报文ID」）→ Web 侧业务段改用 `_field_value`/`_field_comment` 保持同语义，两端才能逐字符对拍；
    - Web `get_frame_summary` 对协议10 **按表类型分流**：应用层报文走 `get_hdc10_summary`（与协议11 同一实现），物理层/网络层帧**保持原路径**（协议9 摘要函数——它对 TEI/发送类型等段覆盖更全，整包切换会让 105/118 张真实表摘要丢信息）；物理层段全量对齐属 `09-15-web-shared-parse-core`。业务名已含于 `报文:{报文ID}` 段时**不重复追加**（协议10 的 `报文:开始升级`）；
    - 对拍范围**只限应用层表**（物理层/MSDU/MME 段两端文案差异属共享核心任务），回归套件 `test/test_gw_app_summary_detail.py`（42 项，含**真实夹具 auto/fc_pb/app 三级别**不得混入 FC/MAC 字段的断言、真实批量解析 20 帧可区分性、Web 协议10 非应用层表不退化、变异反证）。

45. **HDC 1.0（协议11）抄表报文解析曾有未定义名（1.23.19 修复）；同文件 2 处静态告警为误报**：`hdc10_parser._parse_meter_reading`（服务报文ID `0x001`/`0x002`/`0x003` 三类抄表报文）渲染「协议版本号」行时引用了**从未赋值**的局部名 `proto_ver`（同文件 `_parse_confirm`/`_parse_timesync` 等 6 个函数都写有 `proto_ver = b0 & 0x3F`，唯独它漏写）⇒ **协议11 + 解析级别「应用层报文(app)」+ 抄表类报文ID + 端口 `0x11`** 四条件齐备时抛 `NameError`，GUI 弹「解析失败：name 'proto_ver' is not defined」。**默认「自动识别」级别走 MAC 帧路径、不经过该函数，故自协议11 引入以来长期潜伏**——改本协议时留意「同一份数据在不同解析级别下走完全不同的代码路径」。同类排查手段：`ruff check --select F821`（全仓已 0 命中）。
    - 另注：pyright/ty 对 `hdc10_parser.py` 的 `bcsha_phases`（`for i in range(bcsha_phases)`，位于 `_parse_beacon_management_info` 一类的信标可变区解析）与 `msdu_len`（`base_offset + msdu_abs + msdu_len + 4`，位于 `_parse_mac_frame` 的帧尾多余数据行）报 possibly-unbound / 类型收窄，**均为不可达路径误报**：前者使用点在 `if ln > 20` 内、赋值在 `if ln >= 7` 内（数值蕴含，检查器不做）；后者 `extra_bytes` 初始化为 `b''`、只在 `if msdu_len is not None` 分支被赋值 ⇒ `if extra_bytes:` 块内 `msdu_len` 必非 None（跨变量关联，检查器推断不出）——**这两条已于 2026-09-17 以「2 行零行为变更」清理固化**（`bcsha_phases = 0` 前置初始化；`if extra_bytes and msdu_len is not None:`），实测 hdc10 全套（20/94/13/3/29）+ `test_gw_new_gen`(44) 全绿且输出与改动前逐行一致，lens/pyright 对该文件转为 **clean**；同类误报若再出现，参照此做法（不改逻辑、只补显式信息）而非欠着。同类的还有 `main_gui.py` 的 88 条（PySide6 枚举经类访问 `QTableWidget.NoEditTriggers` / `__init__` 动态属性 `update_stats` / `QLayout.takeAt` 覆盖签名）、`reflex_web/reflex_web/web_utils.py` 的 `from reflex_web import web_utils` unknown-import-symbol（`test/_path_setup.py` 把 `reflex_web/` 插入 `sys.path`，包名解析到内层包；外层目录无 `__init__.py` 故静态不可解析——`test_gw_app_summary_detail.py:56` 等既有测试同款）、以及 `release_check.py` 的 `sys.stdout.reconfigure`（`typing.TextIO` 协议不含该方法）。**这些不属于开放缺陷，勿按告警改造**。⚠ **行号会随改动漂移（实测：1.23.20 的 +16 行便使 L1516→L1532、L1655→L1671），请按符号名/代码文本检索，不要按行号判断是否新引入**；复核手段：`git show HEAD:<file> | sed -n '<HEAD行号>p'` 与被标记行逐字节对比 + `git diff` 的 hunk 范围是否覆盖该行（2026-09-17 复核：该两行与 HEAD 逐字节相同且不在任何 hunk 内）。

46. **pi-lens 的自动格式化与自动修复在本项目已关闭（`ruff.toml` + `.pi-lens.json`，2026-09-17）**：pi-lens 在**项目无 ruff 配置**时会回落它自带的 `config/ruff/core.toml`（`line-length=88` + `select=E,W,F,I,B,UP,SIM,C4,PIE,S`），配合 `ruff format` 对既有代码做大规模重写——实测 `hdc10_parser.py` 单文件产生 **4201 行**格式 diff、`web_utils.py` **343 行**（单引号统一为双引号、`List[X]`→`list[X]`、长行炸开成一行一参），**5 行的真实修复被淹没在 2932 行格式噪声中、无法评审**。
    - **分工**：`ruff.toml`（`select=["F"]` + `quote-style="preserve"`）决定「报什么」——只留 pyflakes 真实缺陷（F821 未定义名，1.23.19 修的 `proto_ver` 即此类；另有 F841/F541），不选任何风格/现代化规则，从根上消除改写来源；`.pi-lens.json` 的 `format.enabled=false` + `autofix.enabled=false` 决定「是否后台改写」——两者都关，lens 只**报告**诊断、不动文件。
    - **变异反证（同轮实测，双向）**：同一份「单引号 + `List[int]` + 超长行(>88)」探针，`format.enabled=true` 时 lens 立刻 `Auto-fixed 2 issue(s)` 并改写；改回 `false` 后 md5 逐字节不变、无任何改写提示。ruff 侧另证：从仓库根运行 `ruff check --statistics <file>`（**不带 `--config`**）只报 F 类 → 项目 `ruff.toml` 被自动发现、不再回落 lens 的 `core.toml`。
    - **临时恢复格式化**：把 `.pi-lens.json` 的 `format.enabled` 改回 `true`（或删除该文件 = 回落 lens 默认）。**改真实代码时不要开**：长行重排是 `ruff format` 的固有行为，`quote-style="preserve"` 只能挡住引号统一，挡不住重排。
    - 工具提示：ruff 是 Windows 程序，`--config` 传 WSL 路径（`/mnt/c/...`）会直接 `invalid value ... for '--config'` 退出 2（**表现是「所有测量结果全 0」的假绿**）——对比配置时必须传 `C:/...` 形式；`ruff --diff` 不写文件，可安全用于测量。

47. **协议11 应用层的「是否应用层」由 MAC 头类型字段决定，不由端口字节决定；值域、判据、文案都是单一来源**（1.23.20 起，改 `hdc10_parser.py` 应用层任何分支前必读）：
    - **分派顺序**（`_parse_msdu_payload`）：`msdu_type == 0` → MME（两套表的 0 都是管理类；单跳表的 0 是「发现列表消息」，经 MMTYPE `0x0008` 在 MME 树内解析）→ `in APP_MSDU_TYPES`（标准头 `48` / 单跳头 `128`，表10/表13）→ 应用层 → `in IPV4_MSDU_TYPES`（`49`/`129`）→ IPv4 提示（不展开载荷）→ `msdu_type is None` 才回退首字节启发式（`first in APP_PORTS`，`0x00` → MME）→ 其余才走「未定义(厂商扩展)」。**不要为提高“兼容性”把端口白名单写回 app 分支**：真实帧实测过双向误判——声明 `48`（应用层）的帧被当「厂商扩展」不解析，声明 `47`（表外）的帧反被当应用层错位解析。
    - **`app` 级别入口白名单**（`_parse_app_only`）：现为 `data[0] in APP_PORTS or (data[3] == 0 and not has_fc)`，最后兜底仍按应用层解释并标 `⚠ 推测解析`（陷阱 23：宁可解释也不空白）。**`and not has_fc` 不可删**：FC 的 byte3 是**网络标识(NID)高字节**、取 0 概率约 1/256，字面按「控制字为 0 即应用层」会错位解析合法完整 MPDU（`test/test_hdc10_app_dispatch.py` 的 A6d 与变异 7.5 钉住此护）。
    - **fallback 文案两分（依据必须成立）**：`MSG_ID_NO_FORMAT_DEFINED`（= `{0x0A0, 0x0A4}`——规范第4-3部分只有报文ID表、无字段格式章节，已全文核实第1/4-1/4-2/4-3部分）→ `⚠ 格式未定义`；其余命中 `MSG_ID_NAMES` 但**有**定义的 → `⚠ 未按业务格式解析`（附当前端口，说明未命中已实现分支）。**两者不可混用**：给有定义的业务印「规范未给出字段格式」是**事实错误**（1.23.20 初版曾如此，影响 44 种端口×业务ID 组合，被独立检查抳出）。该表是**规范文档事实**的建模，不是分派链的第二份清单——哪个组合有解析由 `_parse_app_payload` 的 `if/elif` 链权威决定。
    - **安全模式提示**：`sec_mode != 0`（报文ID 高4位=信道安全机制，如 `0x2004` 完整性保护的校时、`0x3032` 全面保护的传输文件数据）时插「⚠ 安全保护」行（说明数据域受保护、按明文解析的字段可能无效；仍保留解析，不在安全报文上直接空白）。该行已进桌面 `main_gui._GW_APP_META_FIELDS` 与 Web `web_utils` 同名字段的**黑名单**（两端集合必须相等），防它挤占批量摘要的业务名/关键字段位（陷阱 44）——改摘要逻辑时勿删。
    - **排查夹具陷阱**：`test/hdc10_real_frames.pkl` 定 60 帧，其 **43 帧是 TMI 填充帧（随机数据）**——它们的「未定义(厂商扩展)」`0x347`、`未解析的管理消息内容(0x1002/0xC0C3…)` **不是缺陷**。语义断言只能对 `key[1] != '-'` 的真实业务帧做（填充帧只断言「不抛异常」），否则会得到大量假阳性。
    - **同批已识别、尚未修的缺口（另行立项）**：抄表 DATA 域内嵌 645/698.45 未展开（现场抄表报文的核心内容就在 DATA 里）；`hdc10_mme_parser` 15 类 MMTYPE 只实现 8 类（缺代理变更 `0x0003/0x0004/0x0005`、过零NTB `0x000B/0x000C`、网络诊断 `0x004F`、无线信道冲突 `0x0080`；真实帧已实测命中 `0x000B`）；`_parse_msdu_payload` 的 MME 分支 `except Exception` 静默吞异常（不记录异常类型/位置——同类 `NameError` 在此分支会永久潜伏）。

48. **协议6（DL/T 645-2007）光伏扩展协议：DI 表来自独立模块、数据切分看「数据长度」列、功率带符号位**（1.23.21 起，改协议6 解析或组帧前必读）：
    - **规范来源**：`协议文档/6.645协议/附件1：协议转换单元【低压分布式光伏协议转换单元】-技术规范书0625.md`（§D.1 三张 DI 表 + 附录 I.3.3.1）。仓库**没有** Q/CSG 1209006-2015 原文，扩展定义以该文件为准。
    - **DI 表单一来源**：扩展 DI（682 键：变量 `02E6xxxx` / 参数 `04E6xxxx` / 事件 `03E6xxxx`）**只在 `dlt645_pv_ext.py` 定义**；解析器 `DLT645Parser._load_di_map()`、查询页 `dlt645_di_lookup`、Web `lookup_utils` 三处都调 `merge_pv_di_map()` 合并 —— **不要再新增第四份清单**，也**不要手改 `dlt645_di.json`**（生成物，§4.5）。合并冲突集由 `_merge_conflicts` 暴露，测试断言为空。
    - **数据切分权威是「数据长度」列**：该列把每值字节数直接相连（`222`=三个值各 2B；全变量块 `222333444444442222` = 3×2B+3×3B+4×4B+4×4B+4×2B = 18 值）。`数据格式`列是多值串（用 `|` 分隔，如 `XXX.X|XXX.X|XXX.X`）**仅作显示提示**，不能机械解析。文档若干行切分有歧义（`04E60001` 尾部 3B、`04E62101` 接入端口 2B 与末段 1B、`04E63002` 小数位、`03E61401` 电压小数位、`03E61403` 长度列与格式列矛盾）→ **保留 hex + 标注存疑，禁止臆造字段**（`02E60FFF` 文档未定义故未登记，命中走兜底）。
    - **语义要点**：多字节 BCD 低字节在前（含时刻：文档写 `YYMMDDhhmmss`，**线序是 `ss mm hh DD MM YY`**）；功率块 4B/值且**最高半字节的 bit3 是符号位**（0=发电/正、1=用电/负，故上界是 `7999.9999` 而非 `9999.9999`）；整字节 `FF` = 该项不存在（单相设备 B/C 相即此）；事件块**每字节从左往右对应逆变器 12→11→…→1**；调控结果枚举 `00` 成功/`01` 未调/`02` 失败/`03` 不支持/`04` 其他/`FF` 不存在；`DI0` 双语义（变量·参数组=逆变器 1~12 或 `FF` 下载全部；事件记录组=第 1~50 次，`0x32`=50）。
    - **扩展控制码 `0FH`/`8FH`**：无线转发透传帧，数据域 = DI + 透传数据（`L = 04H + N`）；`8FH` 靠 `func = ctrl & 0x1F = 0x0F` 复用 `FUNC_NAMES[0x0F]`；透传内容命中扩展 DI 会二次展开。
    - **组帧侧守卫（本次改动引入的副作用，已修）**：扩展 DI 进入组帧下拉后，`dlt645_frame_schema.build_di_fields` 把多值掩码当单值套模板（运行状态 `NN`→「通信地址」、时段调节块→「日期」、事件块→「时间」）。现守卫：`_is_multivalue_dt(dt)`（含 `|`）一律走裸字节模板 + `set(dt.upper()) == {"N"}` 需 `len >= 12`；`_encode_di_value` **同步加守卫**（模板与编码必须一致，否则出现「显示裸 hex 但编码走时间/地址」。判据零误伤的前提是**标准表 1099 条无 `|` 掩码、无短全 N 掩码**（测试已钉住这两个前提，表变化会让断言失败提醒复核）。**组帧支持该扩展协议仍属范围外**。
    - **本文件既有静态告警（勿按告警改造）**：`dlt645_frame_schema.py` 的 `fld()` 内 `d["length"] = length`（类型标注）、`_norm_key` 的 `int(func)`（无 try/except）、`int(info.get("length") or 0)`、`BS*` 分支的 `int(up[2:])` —— 经核实**均为改动前既有**（HEAD 第 64/250/302/355 行同文本），后两条分别由 `or 0` 与 `.isdigit()` 保证安全 → 同陷阱 45 处置。

49. **协议6 解析的容错契约：结构/校验/长度不符一律继续解析，并把「正确值」告诉用户**（1.23.22 起，改 `dlt645_parser` 前必读）：
    - **判据必须分开**：`check_structure(data)`（长度≥12 / 双 `68H` / 结束 `16H`）与 `calc_checksum(data)`（`sum(data[0:-2]) & 0xFF`）是两类不同性质的判据；`check_frame()` 保留为二者合取（语义不变）。**不要再把校验判据混进提前 return** —— 1.23.22 前正是如此，导致 CS 写错时整张表为空、只弹「无效的DLT645帧格式」。
    - **`parse()` 只在 `len(data) < 12` 时降级**（帧长不足说明 + 原始 hex）；长度够就一律继续完整解析（陷阱 23）。
    - **`valid` 语义不可动**：`结构OK and 校验OK and not 长度不符`。`dlt645_sim/engine.py` 与 `dlt645_meter_sim_widget.py` 读 `parsed.get("valid", True)`，改语义会连带改虚拟表行为。
    - **新增提示行的行名必须含「校验和」**：`protocol_registry.DLT645GuiParser` 的偏移映射按字段名子串匹配（`elif "校验和" in field: byte_start = total_len - 2`），改名会让高亮落到字节 0。
    - **合法帧输出逐行不变**是硬约束（`test_dlt645_tolerant_parse.py` 的 A4 会抓住）；`校验和` / `帧结束符` 行的增强**只在该项不符时**生效。
    - **虚拟表对 `valid=False` 帧「尽力响应」是作者有意行为**（`dlt645_sim/engine.py:114` 分支注释「尽力：仍尝试取 control / data」+ `pass`，不是 bug）。因此 1.23.22 后「坏 CS 主站帧」从回异常应答变为回正常应答——这是本次修复的**已知副作用，已确认接受**；虚拟表日志现会打出「⚠ 帧校验未通过: 校验和错误，期望 0xXX，实际 0xYY」。若要改成严格拒收，属独立小任务（改 `engine.py` 那一行 + 补测试）。
    - 同类未修（另行立项）：国网(7)/698.45(8)/新一代系 是否存在「校验不符即拒解析」需逐协议核实（南网协议0 **已是正确行为**：`protocol_parser.py` 的 `解析状态=失败` + `错误信息=校验和错误，期望 0xXX，实际 0xYY`）。

---

50. **协议6 位域（状态字 / 主动上报字）的四处易错点（1.23.23 起，改 `dlt645_data_codec.py` 位表前必读）**：
    - **位表单一来源**：`STATUS_WORD_BITS`（电表运行状态字 1~7，附录C）、`REPORT_STATUS_BITS`（96 位）、`REPORT_MODE_BITS`（64 位）**只在 `dlt645_data_codec.py` 定义**，桌面 / Web / 645 虚拟表均经 `decode_value` 间接使用。新增位表知识必须在同一文件（`_format_bits` 是唯一的「置位/未置位」文案拼装器），否则就是第二份清单。
    - **字节序低字节在前**（与 645 一般字段一致）：96 位表第 n 字节 = Bit(8n)~Bit(8n+7)；`int.from_bytes(data, "little")`。补遗三示例自证：首字节 `01H`→Bit0、`02H`→Bit1、字节[10] `01H`→Bit80。**误用高字节在前会“看似正常”地输出错误事件名**（示例1 会变成 Bit88 节假日编程）。
    - **保留位必须显式占位且置位时点名**：表里写 `None`（保持 16/64/96 位完整，防「整体错位」类回归）；置位 → 输出「保留位（补遗未定义事件）: Bit76」/「保留位（未定义）: Bit9」；**未置位不进“未置位”列表**（96 位表若列未置位会输出近百项噪声）。附录C 对状态字3 只写「Bit15..Bit9 保留」而未提 Bit8 → **同样按保留处理，不臆造事件**。
    - **两位域项的 key 是 LSB 位号**：状态字3 供电方式占 Bit2~Bit1 → 声明为 `1: ("供电方式", 2, SUPPLY_MODE_NAMES)`（**不是 key=2**）。`_norm_bit_entry` 支持 `"名称"` / `None` / `("名称", 位宽)` / `("名称", 位宽, 枚举)` 四种写法；位表完整性应用「覆盖位集合」而非 `table.keys()` 校验。`STATUS_WORD_BITS` 各字取 `data[:2]`（声明 BS32 但附录C 只定义 Bit0~Bit15）。
    - **两个位表文档的用词差异不是错**：补遗 Bit16–23 与附录C 状态字4 Bit7–0 **逐位一致**，仅「功率反向」↔「潮流方向」用词不同（本实现分别在两表里保留各自用词），可作为双源互证。
    - **改位表后必须检查既有测试是否固化了错误期望**：`test/test_dlt645_lme.py` 的 12b/12c 就曾固化旧错位（且 12c 用子串断言 `"有功功率方向" in svc`，会命中**未置位列表**而假绿）→ 断言应切分 `svc.split("未置位")[0]` 只查置位段，或用 `check(..., 精确相等)`。
    - **补遗 MD 的位表有转换瑕疵**（markitdown：`费率参数表编程`/`电流严重不平衡` 被拆到两行、跨页的 `Bit87–80`/`Bit55–48` 值行丢格、页码「15」混入表格）→ **位表必须以 pdfplumber 按单元格重取为准**（`page.extract_tables()`），MD 仅作文字对照；跨页表必须把「位段头行」与「跨页后的值行」配对才能拿全。

51. **协议10/11「仅MAC帧」不得自动剥离物理块头（1.23.29 起）**：`mac_only` 输入即 MAC 帧，从字节 0 解析。协议10 曾把输入当 PBH+MAC 走 `_parse_pb_by_frame_type`，协议11 曾在 `data[0]&0x80` 时剥 1 字节——两者都会让 MAC 头错位并冒出「物理块头(PBH)」行。需要 PBH 用 `pb_only`/`auto`。协议11 MME 内容行偏移为**绝对帧偏移**（`_parse_msdu_payload` 在切片解析后统一 `+ base_offset`）；改 MME 字段时不要改回相对 MSDU 切片。回归：`test/test_hdc10_mac_only_contract.py`。

52. **协议10/11 摘要里的 MMTYPE 字段名不同构（1.23.30 起）**：协议10=`管理消息类型(MMTYPE)`（`gw_new_gen_mme_parser`），协议11=`消息类型(MMTYPE)`（`hdc10_mme_parser`）。桌面 `_get_gw_new_gen_summary` 与 Web `get_hdc10_summary` 必须**两种都认**（或子串含 `MMTYPE`）；`仅PB` 批量时网络层帧靠这段摘要区分关联请求/发现列表等，漏字段名会让整批摘要变成 `0→1 | msduSeq:x | 单播`。回归：`test/test_gw_pb_mme_summary.py`。

53. **协议10/11 的 ED..EE 监控包装帧必须在「行提取」阶段解包，且公共头有 plc2(9B)/gx(8B) 两种（1.23.32 起，改批量/监控前缀剥离前必读）**：现场日志把 ED 包装帧原样贴进来（真实形态每帧 168B，帧尾 `CS+EE`=`FF EE`，帧间无换行、**一行可能拼多帧**）。协议9 的 `csg_line` 策略一直有解包，但协议10(`gw_line_min4`)/11(`line`) **完全没有** → 首字节 `0xED` 被当成应用层端口号，解析成「应用层报文 端口 0xED / 业务 0x0A4」。规则：
    - 解包三件套在 `batch_core`：`ed_wrapper_prefix_len`（按帧长 + `detect_ed_wrapper` 判别 plc2=15B / gx=14B）、`split_ed_frames`（按帧长切分一行内拼接的多帧，尾部残帧丢弃）、`unwrap_ed_line`（返回 `None` 表示「不是 ED 行」→ 调用方按原逻辑处理）。桌面 `main_gui._extract_line_frames` 与 Web `web_utils.extract_frames_for_protocol`（协议10/11 分支）都走它。
    - **不要再写 `startswith("EDA5")` + 固定剥 15 字节**：帧长字节随报文变化（`EDA4`/`ED1D`… 都合法），gx 帧只有 8B 公共头，多剥 1 字节会让整帧错位。旧硬编码仍保留在协议9 的 `strip_csg_new_gen_frame_prefix`（既有测试锚定其输出），新代码不要照抄。
    - **不要在 strip 阶段剥 ED 帧**：`_strip_*_prefix` 只做日志前缀清洗，ED 帧应原样留给提取函数——strip 剥出来的业务数据会带上 `CS+EE` 尾巴，反而解析失败（实测 20B 业务帧带 2B 尾巴即失败）。ED 帧太短（无业务域，如测试装置控制帧）时**不得丢弃**，否则触发「预处理后未保留有效报文内容」弹窗（offscreen 测试会直接卡住）。
    - **三条路径都必须覆盖**（1.23.33 补齐单帧两条）：批量（`_extract_line_frames`）、单帧 `parse_single`、快捷弹窗 `_parse_and_show_dialog._preprocess`。前两条单帧路径曾把 ED 解包硬门控在协议9（`current_protocol == 9 and ed_monitor_chk.isChecked()`；快捷弹窗只认 `idx in (9, 10)`），而「ED监控协议」复选框仅 9/10 可见 → **协议11 单帧贴 ED 帧仍被当应用层解析**。协议10/11 现为自动识别，判据用 `_ed_business_is_fc`（解包后业务帧 `DT = business[0] & 0x07` 必须 ∈0~3；`0xED` 低 3 位=5 恒非法，真 FC 恒满足）防误剥离；协议9 勾选态「不完整帧必须报错、禁止回退」契约不变（AGENTS 陷阱 22）。
    - **单帧工具栏能力来自注册表（1.23.35 起）**：`ProtocolSpec.has_ed_monitor` / `has_reverse_4byte`（协议9/10/11=True）控制「ED监控协议 / ED包装格式 / 4字节反转 / 字节剔除」可见性与 `parse_single` 是否应用；**不要再写 `current_protocol == 9` 硬门控**。勾选 ED 时三协议统一「解包失败必须报错」；未勾选时 10/11 仍自动识别。回归：`test/test_ed_ui_for_gw_hdc10.py`。
    - **展示文案按协议分语义（1.23.36 起）**：`batch_core.ed_wrapper_display(protocol_index, wrapper)` 是标题/注释/摘要/下拉文案的**单一来源**。协议9→`PLC2.0`/`广西台体`；协议10/11→`国网HDC`（gx 8B 与 HDC 同构，**禁止**再写广西台体；plc2 布局标题带「(PLC2.0布局)」后缀）。摘要判定用标题含 `监控包装头` + `ed_wrapper_summary_name`。回归：`test/test_ed_wrapper_labels.py`。
    - **TCP 监控（1.23.37 起）**：协议下拉含「HDC 1.0」；`FlowBuffer` **保留完整 ED 帧**（禁止写死剥 9 字节）；解析走 `batch_core.unwrap_ed_for_parse(frame, protocol_index)` + 对应 parser。`resolve_ed_wrapper(..., protocol_index=10/11)` auto 时**优先 gx/8B**（HDC 同构），不得回落 plc2 造成业务错位 1 字节。回归：`test/test_tcp_monitor_ed_hdc.py`。
    - **ED 帧长域与 EE 不一致（1.23.38 起）**：现场日志可能出现「帧长域偏小、EE 在缓冲区末尾」的信标/数据帧。`_ed_frame_parts` 与 `extract_business_from_ed_frame` 在 `EF..EE` 自洽时按**末尾 EE 重算**；`extract` 未传 wrapper 时 `resolve` 必须带 `protocol_index`。HDC10 `auto` 在 FCCS 失败且 DT=0 时仍可按信标解析（⚠ 推测信标帧）。回归：`test/test_beacon_ed_hdc10.py`。
    - 回归：`test/test_hdc10_ed_wrapper.py`（30 项，含现场 7 帧、一行多帧、plc2/gx 判别、协议6 不受影响护栏、批量/单帧/快捷弹窗三条路径端到端）。

54. **协议11（HDC 1.0）跨字节位域一律按「LSB-first 位流」读，不得按「首字节=高位」组装（1.23.34 起，改 `hdc10_parser` 任何 FC/载荷字段前必读）**：规范各表（表19/23/27/30/34 等）的「字节号 / 比特位」列把跨字节字段写成「字节N 比特0-7」+「字节N+1 比特0-3」这类形式，含义是**位号小的一端是低位**。两条独立实证（同一现场帧）：① `广播标志位 = 比特1` → `(b11>>1)&1 = 1`，且该帧目的TEI 确为广播地址 `4095`；② `分集拷贝基本模式 = 比特4-7` → `4`，而该帧物理块恰好 `136` 字节（模式4 = 136B）。
    - 统一入口：`hdc10_parser._bits_lsb(data, byte_off, bit_off, nbits)`（参数即规范表的「起始字节 / 起始比特 / 位宽」，公式可直接对照表格核验）。**新增跨字节字段一律用它**。
    - 已修的 13 处（原为 `(bX << 4) | (bY & 0x0F)` 这类「首字节=高位」写法）：6 个 FC 可变区域函数（`_parse_fc_vf_sof_plc` / `_parse_fc_vf_beacon_plc` / `_parse_fc_vf_beacon_hrf` / `_parse_fc_vf_sack_plc` / `_parse_fc_vf_sof_hrf` / `_parse_fc_vf_sack_hrf`）的 **源TEI / 目的TEI / 帧长 / 符号数**。现场帧 FC 源TEI 曾解成 `32`（应为 `2`）、目的TEI 解成 `256`（应为 `1`）。
    - **MAC 头是正确参照**：`((b0>>4)&0x0F) | (b1<<4)`（原始源TEI）、`b2 | ((b3&0x0F)<<8)`（原始目的TEI）——都等价于 `_bits_lsb`。排查同类位序问题的最快手段是**语义不变量**：单跳帧的 FC 源TEI/目的TEI 必须等于 MAC 头的「原始源TEI」/「原始目的TEI」。
    - 回归：`test/test_hdc10_fc_bits.py`（22 项，含上述不变量、`_bits_lsb` 单元、以及「6 个函数无旧位序写法」的静态守卫）。
55. **Web 查询页的自定义条目（协议0 DI / 协议7 AFN+Fn）落盘位置 = 该端解析器实际读取的那一份，且改完必须刷新查询缓存**（1.23.42 起，改 `reflex_web.lookup_utils` / `reflex_web.reflex_web` 查询页前必读）：
    - **落盘位置**：DI 走 `custom_di_store`（`app_paths.data_path("custom_di.json")`），AFN 走 `GDW10376Parser`（`app_paths.data_path("gdw_custom_afn.json")`）。**不要**按 Web 的 `app_data.data_root()`（那是反馈库/发布产物的数据根）另存一份——写了那里，`ProtocolFrameParser` 与 `GDW10376Parser` 读不到，用户会看到「保存成功但查询不到」。`custom_di_store.load_custom_di/save_custom_di/custom_key_set` 现支持可选 `path`（默认 None = 历史行为，桌面调用点不传）；`GDW10376Parser(custom_config_path=...)` 同理。
    - **测试沙箱**：`custom_di_store` 以属性形式调 `app_paths.data_path` → patch `app_paths.data_path` 即可；`gdw10376_parser` 是 `from app_paths import data_path`（直接绑名）→ 必须 patch `gdw10376_parser.data_path`，并清 `parser_registry._INSTANCES["gdw"]` 与 `gdw_afn_lookup._LOOKUP_INSTANCE`（否则复用旧路径/旧数据）。
    - **查询缓存**：`GDWAFNLookup._data` 在构造时一次性构建，自定义 AFN+Fn 增删后必须 `gdw_afn_lookup.refresh()`（`lookup_utils.refresh_gdw_afn_lookup()` 已封装），否则查询页仍是旧表。
    - **判据同源**：某条目「是否自定义（可删）」= 是否存在于 `custom_di.json` / 解析器 `_custom_fn_map[afn][fn]`（内置 DI 只活在 `DI_COMBINATION_MAP`、标准 Fn 只活在 `FN_MAP`），查询表「自定义」列（★）与删除逻辑必须用同一判据；批量删除时内置/标准条目**忽略并计数**，不要静默丢弃。回归：`test/test_web_gui_parity.py`（R4/R4b 段）。

56. **顶部「协议选择」组的 FlowLayout：`sizeHint()` 必须是单行总宽，且 reflow 必须重排外层顶栏**（1.23.44 起，改 `FlowLayout` / `_reflow_proto_group` / 顶栏容器前必读）：
    - **`sizeHint()` 不能用 `minimumSize()`**：后者是「各子项最小尺寸的逐分量最大值」（≈最宽单项，实测 276px），父布局（`QGroupBox` → 顶栏 `QHBoxLayout`）会照此只给这么宽 → FlowLayout 被迫换行成两行 → 分组框高 75px 而顶栏容器只有 49px → 第二行的**协议下拉框被裁成一条缝**（实测 geometry (5,44)、`visibleRegion()` 仅 266x5）→ 启动后该控件显示为空白，点一下（触发重排）才出现文字。现 `sizeHint()` 返回单行总宽（各子项 `sizeHint()` 之和 + 间距 + 边距），`minimumSize()` 保持「最宽单项」语义不变 —— 窗口真窄时仍照旧换行。
    - **`_reflow_proto_group()` 必须重排外层顶栏**：只 `invalidate()` / `updateGeometry()` / `adjustSize()` 内层时，协议分组框拿不到最终宽度，内层 FlowLayout 也不会被重新调用，子项就停在旧的换行位置（**单独调 `QLayout.activate()` 是空操作**，实测无效）。补上 `top_bar_widget.layout().invalidate() + activate()` 后，分组框立刻拿到最终宽度、内层随之重排，实测同步从 (5,44)/266x5 恢复到 (76,20)/266x26，不再依赖点击等交互触发。
    - **排查手段**：`QWidget.visibleRegion()`（真正被绘制的区域）比 `geometry()` / `grab()` 更能暴露「控件在但没画出来」；`grab()` 会强制重绘，看不出这类问题。回归：`test/test_flow_layout_proto_group.py`（含反例自检）。

57. **TCP 监控的「原始载荷」路径：切帧策略、识别边界、帧表列序、记录位置四处约定**（1.23.45 起，改 `monitor/tcp_monitor.py` 的切帧/解析/帧表前必读）：
    - **切帧**：`FlowBuffer(mode)` 三档 —— `ed` 只切 ED..EE（旧行为）、`raw` 一段一帧、`auto`（默认）先 ED、判定非 ED 后按 **TCP segment 逐包**产出原始帧。判定只认完整定界校验（`ED` + 帧长∈[4,4096] + `buf[5]==EF` + 末字节 `EE`）；「未收全的 ED 候选」最多等 `MAX_WAIT_SEGMENTS`(=2) 段（原始流里偶然出现的 `ED xx xx` 会伪装成候选，不设上限会让该方向长时间不出行）。raw 方向仍检测**完整 ED 帧并升级回 ED**（抓包从 ED 连接中途开始时不丢既有能力），升级时 ED 帧之前的字节仍按原始载荷产出 —— 同一字节只上报一次。回归：`test/test_tcp_monitor_raw_payload.py`。
    - **识别边界**：自动识别**只认可自证形态**（DLMS Wrapper `00 01`+长度自洽 / DLMS-APDU 首字节 ∈ `HDLCParser.APDU_TYPES` / 645 结构 `68+6+68`+校验器 0 fail / 698.45 HCS/FCS 双通过）。**南网 / 国网 不参与自动识别**：两者同为 `0x68` 起头、链路层结构相近，校准实测校验器互判 0 fail（无法区分），错解析比不解析更糟 → 需显式选择。注意 `APDU_TYPES` 是 `HDLCParser` 的**类属性**（不是模块级常量）；路由判据不能只看首字节 `0xED`（原始载荷恰以 0xED 开头会被塞进 ED 路径，得到「无法识别协议」+ 空表）。回归：`test/test_tcp_monitor_proto_detect.py`。
    - **帧表列序**：`时间/方向/源 → 目的/长度/协议/摘要`（6 列）。第 0 列 UserRole 存 `_frame_cache` 下标 —— 过滤开启后行号与缓存下标不再一一对应，`_on_frame_selected` 必须经 `_row_cache_index(row)` 取下标。改列序要同步 `_fill_frame_row` / `_rebuild_frame_table`；CSV 用列名读写（`_write_csv_record` / `_load_csv_recording`），不受列序影响。回归：`test/test_tcp_monitor_ui_views.py`。
    - **记录位置（1.23.59 起）**：CSV 落盘目录的唯一来源是 `TCPMonitorWidget.record_dir()` —— 用户配置优先、否则 `<数据目录>/Output`（与串口工具日志目录同一约定，见陷阱 60）。**不要再硬编码 `app_data_dir() / "Output"`**：那样测试沙箱拦不住，跑一趟测试就往开发机真实数据目录拉文件（静态守卫 `无裸 app_data_dir() 调用` 钉住）。目录存 `tcp_monitor_config.json`（`load_record_config` / `save_record_config` 原子写，缺失/损坏/非对象/BOM 一律回落空配置）；路径一律经 `app_paths.data_path` **属性访问**。工具栏「打开位置」用 `open_in_file_manager`（Windows `explorer /select,` **定位并选中当前记录文件**、无文件或文件已删则打开目录；非 Windows 回落 `xdg-open`），目录缺失时先自动创建 —— 否则资源管理器打不开。**`QFileDialog` 必须保持在导入列表中**：「加载记录」按钮与「选择记录目录」都依赖它，曾因漏导入让该按钮一点即抛 `NameError` 长期潜伏（测试从不点它）。新增按钮必须用 `gui_utils._STANDARD_ICON_MAP` 的**合法图标键**：`set_btn_icon` 对未知键**静默跳过**（同「分享此帧」无图标的同类坑）—— 本模块的测试有「图标非空」与「全文件 `set_btn_icon` 键合法性」两道断言。回归：`test/test_tcp_monitor_record_dir.py`（61 项）。
    - **按钮宽度（1.23.59 起）**：工具栏 4 个按钮（开始记录 / 加载记录 / 打开位置 / 记录目录）**不得写死宽度** —— 写死 80px 会让文字被裁（现场截图里「记录目录」显示成「记录目」）；统一走 `gui_utils.fit_btn_width(...)`，判据与理由见陷阱 63。回归：`test/test_btn_width_fit.py`。

58. **串口工具（`serial_tool_widget.py`）的四条契约**（1.23.46 起，改串口工具/`serial_worker` 前必读）：
    - **发送必须走 `SerialWorker.write_raw`**（静默写，不发日志信号），不要用 `send_frame`：负载测试按毫秒级连发，逐帧 `log_message.emit` 会让 GUI 事件队列被日志淹没。`write_raw` 与 `send_frame` 共用 `_write_lock`，可被发送线程与 GUI 线程并发调用。回归：`test/test_serial_worker_write_raw.py`。
    - **发送器身份 + 发送代次双重守卫**：`_start_send` 把发送器实例绑进信号 lambda，`_on_sent/_on_send_done/_on_send_failed` 先判 `sender is not self._sender` 则忽略；收尾定时器用 `_send_generation` 代次校验。**去掉任一守卫都会复现「上一轮遗留的收尾定时器/迟到信号掐断新一轮发送」**（实测 200 帧只发出 140）。
    - **匹配队列语义**：只有「启用响应匹配 且 该命令 `match_type != none`」的发送才 `_tx_total += 1` 并入队；接收数据从**队首连续**比对（一批数据可连续命中同值的多个待匹配项，这是源工具语义、不是 bug）；超时 / 停止 / 收尾把剩余待匹配计入失败。成功率 = 成功 / `_tx_total`。
    - **匹配必须按「累积接收缓冲」比对，不能按单次交付的块**（1.23.50 修，实测报障「设了匹配规则仍超时未匹配」）：串口驱动会把一帧拆成多次交付（实测 208 字节国网帧 = 77+92+36+3 四块），按单次交付比对时「预期 = 整帧」**永远匹配不上**（且与接收模式无关 —— 匹配吃的是原始交付块，不是切好的帧）。实现：`_match_buffer`（上限 `MATCH_BUFFER_MAX = 8192`）累积接收字节后比对；**每次发送清空**（一问一答窗口重新开始）、队列清空时清空，避免用上一次响应的字节误判本次。**「队首连续匹配」语义不变**。回归：`test/test_serial_tool_widget.py` 第 [26] 段（用实测四块交付复现）。
    - **匹配判决必须输出可比对的日志**（1.23.50）：只打「超时未匹配」现场无从分析。发送时打 `[匹配] #n 等待响应：<方式>，预期 = …`；命中打 `[匹配✓] …（<方式>，预期 = …）`；超时打 5 行（标题 + 匹配方式 + 预期响应 + 期间收到 + `match_failure_reason()` 的诊断）。`match_failure_reason()` 按 6 种方式分别说明差在哪，并识别最常见误填「**预期响应与发送数据完全相同**」。匹配日志走 RX/TX 队列（享受 burst 保护）。回归：`test_serial_proto_frame.py` 第 [10] 段 + `test_serial_tool_widget.py` 第 [26] 段。
    - **给按钮槽函数加位置参数是个坑**（1.23.51）：`QPushButton.clicked` 会带一个 bool（`checked`）实参，`btn.clicked.connect(self._edit_command)` 下若把签名写成 `_edit_command(self, row=None)`，那个 `False` 会被当成行号 → **永远编辑第 0 行**。要传参就单独写一个信号专用处理函数（如 `_on_cmd_double_clicked(row, col)`）再转调，别改按钮槽的签名。回归：`test_serial_tool_widget.py` 第 [27] 段。
    - **落盘与句柄**：命令与参数存 `app_paths.data_path("serial_tool_config.json")`（原子写 + 损坏回落默认值；导入/导出用**裸列表**以兼容源工具 `commands.json`）；用 `app_paths.data_path` **属性访问**（不是 `from app_paths import data_path`），否则测试的 `_config_sandbox` 无法重定向。串口**复用主窗口共享的 `self.serial_worker`**（`main_gui._ensure_serial_tool_tab` 里 `tab.set_serial_worker(self.serial_worker)`，与组帧页/监控器页同一约定）：本页**不做端口/波特率/连接控件**，只订阅 `connection_changed`（驱动按钮可用性）与 `raw_data_received`；`cleanup()` **不得关闭串口**（端口生命周期归顶部「串口配置」与主窗口收尾）。**一个 COM 口只能被打开一次**，各页各持 `SerialWorker` 会互相抢口（顶栏连上后本页再连必失败），波特率也会出现两处配置。回归：`test/test_serial_tool_widget.py`。
    - **命令勾选与「只发勾选项」**（1.23.52）：勾选存命令的 `enabled`（`coerce_enabled`：旧配置缺键 → `True` 全选）；表格第 0 列是勾选框（`ItemIsEnabled | ItemIsUserCheckable` + `setCheckState`，项目既有范式见 `archive_widget.py`），**`NoEditTriggers` 不阻碍勾选**（勾选走 delegate 的 `editorEvent`，不经 `edit()`）；重建表格期间必须用 `_rebuilding_cmd_table` 抑制 `itemChanged` 回写。**筛选发送必须传 `index_map`**：`messages` 是勾选子集而 `sent` 的 `msg_index` 要回指 `commands` 原下标，否则名称/协议/匹配规则全部错位。**命令级「次数」`send_count`**（1.23.57）：表内第 7 列，每轮对该命令展开 N 帧进 `messages`，`index_map` 每次都指回该命令原下标；与底部「循环次数」（全局 loop，已改名避免与「次数」列混淆）相乘。`coerce_send_count` 默认 1、范围 1~9999。回归：`test/test_serial_tool_widget.py` 第 [28] 段（含 `QTest` 真鼠标点击）。
    - **`hex_str_to_bytes` 必须容忍「连续无分隔」的 hex**（1.23.52 修）：原实现按空格/半角逗号切分后把每个片段当**一个字节**（`int(p, 16)` + `bytes([...])`），于是 `6812004116` 整串被转成越界整数 → 判为非法，现场报「明明是对的却提示不是有效的 HEX」。现：连续串按字节切（`bytes.fromhex`，奇数位拒绝）、半角/全角逗号、顿号、半角/全角分号、斜杠、竖线、连字符、全角空格都作分隔符、容忍 `0x` 前缀；仍拒绝奇数位与非 hex。**报错必须给原因**：`hex_input_error()` 返回「含非 HEX 字符 'G'（第 6 个字符）」这类可读原因，别只说「格式不对」。
    - **「正则表达式」匹配方式下「预期响应」是正则文本、不是 HEX**（1.23.52 修）：旧实现一律按 HEX 校验 → 正则必然非法 → 被 `normalize_command` 静默降级成 `none`、待匹配项**根本不会入队**，现场只看到「超时未匹配」，极难排查。现：`normalize_command` 对 regex 只校验正则语法（空正则也降级）；`_on_sent` 用 `match_hex.encode("latin-1")` 而非 `hex_str_to_bytes`；日志按 `expected_display()` 展示（正则是文本且**不用 repr**，否则 `68\s*D0` 会显示成 `'68\\s*D0'`）。回归：`test/test_serial_tool_widget.py` 第 [29] 段。
    - **正则匹配二进制帧有两个坑**（实测确认，故新增 HEX 通配）：① 模式是在**字节按 latin-1 解码后的字符流**上匹配，字节必须写 `\xNN`，直接写 hex 数字匹配不上（`68` ≠ 字节 `0x68`）；② `re.IGNORECASE` 会把「解码成字母」的字节大小写互配 —— 实测 `\x68` 也匹配 `0x48`、`\x69`↔`0x49`、`\xD0`↔`0xF0`、`\x41`↔`0x61`（**国网帧起始符 0x68 会误配 `'H'`**）；③ `.` **不匹配 `0x0A`**，要写 `[\s\S]` 或 `(?s).`。
    - **「HEX 通配」匹配方式**（1.23.53）：约定**必须与「测试方案」一致** —— `test_plan_widget._match_frame` 是逐字符走、遇 `XX` 跳过一个字节，故 `XX` 可内嵌连续串（`68D0XXXX16`），`??` 为等价别名；语义为**包含式**（在累积接收数据里任意位置找）+ 可选 `^`/`$` 锚点；命中报偏移。改这里要与 `test_plan_widget._match_frame` 的约定保持同源，别自创 `*`/`?` 之类记号。回归：`test/test_serial_tool_widget.py` 第 [30] 段。
    - **匹配统一入口是 `match_offset()`**（返回偏移或 None）：`check_match()` 只回答「是否命中」，日志要报位置就得用 `match_offset()`；新增匹配方式时**两处都要接**（`check_match` 供纯判断、`match_offset` 供带位置判断）。
    - **命令状态图标**（1.23.55）：状态存命令的**运行时键 `_status`**（`CMD_STATUS_KEY`）—— 不进 `normalize_command`、**不落盘不导出**（`export_commands` 剔除所有 `_` 开头的键，否则下次打开会显示上一轮的旧状态）；状态变化只调 `_refresh_cmd_row(i)` **重画那一行的名称单元格**，别整表重建（会丢选中/滚动位置）。图标颜色靠 `CompositionMode_SourceIn` 给 `app_icons.load_icon()` 渲染出的 pixmap 整体染色（`app_icons` 只出单色）。迁移点：每轮 `_start_send` 先 `_clear_cmd_statuses()`、`_on_sent` 先记「通过」再在真正入待匹配队列时改「发送中」、`_on_send_failed` 用 `_mark_running_as("error")`。回归：`test/test_serial_tool_widget.py` 第 [32] 段（**逐态校验渲染出的像素颜色**，别只断言 icon 非空）。1.23.56 起「清除状态」按钮走 `_clear_cmd_status_clicked()`（发送中禁止，与「清除统计」同口径）；第 [33] 段。
    - **「原始数据」接收模式必须做「帧结构优先、时间聚合兜底」**（实测报障两轮，改这里前必读）：① 串口驱动会把**同一帧**拆成多次 `read` 交付（低波特率甚至逐字节），按每次交付输出一行会让一帧打成多行、RX 帧数虚增；② **只做时间聚合不够**——实测 208 字节的国网帧被拆成 77+92+36+3 共 4 行，即**交付块间隔本身就大于静默窗口**（10ms），窗口调多大都不稳。正确做法是按长度域收全再输出：`_declared_frame_len()` 按**末字节自证**互斥判别三种结构（南网/国网与 698.45 的前 3 字节同形 `68 L L`，**不能**靠头部签名区分）—— 698.45：`68H + L(2B 小端) + 控制域 + … + FCS + 16H`，**没有第二个 68H**，L 是不含首尾定界符的数据长度（6.2.2 a)）⇒ 整帧 = `L + 2`（附录 H.1.1 示例 32 字节、L=30 自证；1.23.61 修正，原判据「第 4 字节恒为 68H」与 `L + 3` 均错）、DLT645-2007：`68H + 地址(6B) + 68H + 控制码 + 数据长度 L(1B) + … + 16H`，整帧 = `L + 12`、南网/国网：`68H + L(2B 小端) + … + CS + 16H`，**L 就是整帧字节数**（见 `protocol_parser.py:72` / `gdw10376_parser.py:333`）；**判据 = 「谁到齐且以 16H 收尾就是谁」**——南网/国网末字节恒为 16H，故「按 L 到齐却非 16H」即否定南网口径、改判 698.45 的 `L + 2`，不足 8 字节或长度域越界一律返回 0 退回时间聚合 —— **错切帧比不切更糟**。`_emit_structured_frames()` 只在**末字节确为 16H** 时才算自证（帧体内含 16H 不会被误切，两帧连在一次交付里会切成两行）。无结构裸数据仍走时间聚合：`RAW_FLUSH_DELAY_MS = 10` 静默窗口 + `RAW_MAX_HOLD_MS = 200` 最长持有（防持续流 `_raw_buffer` 无界增长且永不显示）；已声明长度但未收全时改用 `FRAME_IDLE_MS = 300` 容忍静默 + `FRAME_HOLD_MAX_MS = 5000` 绝对上限。**头标志 68 已出现但长度域还没收够字节时也算未收全**（1.23.57）——首片仅 1~2 字节时若走 10ms 静默会单独刷出首片，缓冲从下一片起不再以 68 开头、整帧被切碎（实测国网 F112 拆成 4 行）；协议已知时 `ft12_68` 3 字节即可算整帧长。切换接收模式与 `cleanup()` 时立即刷出（含未收全残帧），不丢数据。**取舍**：非 68 结构的裸数据两段间隔小于窗口会被合并成一行 —— 需要逐帧精确切分时用「按帧尾分割」模式。回归：`test/test_serial_tool_widget.py` 第 [17] 段（含首片仅 68 的四块交付复现）。
    - **`_save_timer` 必须先于 `_build_ui()/_load_persisted()` 创建**：载入持久化参数会触发控件 `toggled` → `_schedule_save()`，若定时器还没建好，信号槽内会抛 `AttributeError` 被 Qt **静默吞掉**（表现为配置保存失效，极难排查）。回归：`test/test_serial_tool_widget.py` 第 [18] 段。
    - **线程归属（已知取舍）**：接收数据经 `raw_data_received` 信号投递到 **GUI 线程**后再做匹配与分帧（源工具是在接收线程里直接匹配）。与既有组帧页同一口径、只保留一套串口层；常规表计流量无影响；解析也走同一口径（`set_parse_provider` 注入的回调在 GUI 线程执行）。若将来遇到极高接收速率（数千帧/秒）导致界面滞后，再把匹配与解析一起下沉到 worker 线程。
    - **批量替换通信地址（1.23.83，改这条前必读）**：命令表工具行「替换地址」= 对**作用范围内（勾选行；无勾选=全部）每条命令**按所选协议替换地址域并重算校验，**写回表内 `data_hex`**（与蓝牙页那套「发送时替换」不同，这里表里看到的就是要发的内容）。
      - **只复用 `frame_addr_fix`**（地址定位/字节序/校验算法单一来源，禁止在串口页另写第二份），串口页只做编排：纯逻辑 `fix_frame_text` / `batch_fix_commands` / `addr_batch_summary`（**不修改入参**，写回与撤销归 GUI），GUI 侧 `_on_batch_addr_clicked` / `_apply_addr_batch` / `_undo_addr_batch`。
      - **三态**：`ok`（已替换）/ `kept`（尝试失败：结构或原帧校验不符、地址写错、协议不支持 → **原样保留 + 可读原因**）/ `skipped`（发送数据本身不是有效 HEX）。**失败绝不洗白、绝不静默改半条**。
      - **前导 FEH 只对协议 6/8 剥离并原样恢复**（`FE_WAKEUP_PROTOCOLS`，依据见陷阱 75）；其余协议带前导就该报错 —— 剥了等于「救活」错帧。
      - **协议列写入与替换成败解耦**：勾选「写入协议列」时，作用范围内**每条**命令都写（「这批报文属于协议 X」是用户声明，且「加载报文文件」导入的报文 `protocol=None`，写入后接收侧才能按它断帧解析）；未替换的条目靠汇总三态计数 + 逐条原因区分。
      - **预期响应只在发送数据替换成功时动，且只动纯 HEX 写法**（`HEX_MATCH_TYPES` = contains/equals/starts_with/ends_with；通配 / 正则 / 不匹配保持原样并说明）——「能自证才替换」由 `frame_addr_fix.apply` 第一步的结构+校验自证天然保证。
      - **撤销**只保留最近一次（快照 3 键：`data_hex` / `protocol` / `match_hex`），汇总弹框里点；全失败时不给撤销按钮。发送中禁止替换（命令内容正在被使用）。
      - 回归：`test/test_serial_addr_fix.py`（104 项，六协议真帧 oracle = 替换后该协议**校验器 0 fail**）+ `test_serial_tool_widget.py` 段 [35]（536 项）。**变异反证 5 条**（前导不恢复 4+1 红 / 前导门控失效 5 红 / 未成功也改预期响应 1 红 / 就地改入参 2 红 / 关闭协议列写入失效 1+1 红）。

59. **串口工具「按命令协议断帧 + 解析」（1.23.47 起，任务 09-22-serial-proto-parse）**：
    - **协议来源 = 最近一次发送命令的协议**（串口问答式，RX 就是这条 TX 的响应）：`_on_sent` 里 `_last_tx_protocol = coerce_protocol(commands[msg_index]["protocol"])` 锁存；同批命令协议不同时以**最后发出的**为准。为 `None`（不解析）时接收行为与 1.23.46 完全一致。
    - **分帧策略表 `STRATEGY_BY_PROTOCOL`**：`0/7 → ft12_68`（`68H + L(2B 小端)`，**L 就是整帧字节数**）、`6 → dlt645`（`L(1B@9) + 12`）、`8 → dlt698_45`（`68H + L(2B 小端) + 控制域 + … + FCS + 16H`，**无第二个 68H**，整帧 = `L + 2`，见协议文档 6.2.2 a) + 附录 H.1.1 示例）、`2/3 → hdlc_7e`（`7EH…7EH` 定界，帧内 `7D 5E/7D 5D` 转义，**输出含首尾 7EH**，与 `main_gui._extract_hdlc_frames` / `HDLCParser.parse` 同口径）、`4 → dlms_wrapper`（`版本 0001 + … + 长度(2B 大端@6)`，整帧 = `8 + L`）。**未列出的 1/5/9/10/11 没有自证依据，不得硬加策略**。
    - **一律要求自证，不满足就返回 0 交回既有路径**：68 家族看**末字节必须 16H**（`END_CHAR_STRATEGIES`，长度域只给长度、末字节才是自证；DLMS Wrapper / HDLC 各有自证，**不要**给它们套 16H 检查）；`ft12_68` 还要排除**不是南网/国网结构**的输入 —— 判据是**末字节自证**（南网/国网 L = 整帧、末字节恒 16H，故「按 L 到齐却非 16H」即否定本结构，典型：把 698.45 帧按本口径切，其 L 比整帧小 2），并保留 645 的「第 8 字节 68H + 末字节」双自证；**`dlt698_45` 反向同理**（末字节自证是南网 → 返回 0）。历史上的 `buf[3] == 0x68`（「698.45 的第二个起始符」）判据已于 1.23.61 删除：真实 698.45 链路帧没有第二个 68H，该签名恒不命中。**错切帧比不切更糟** —— 指定了协议时**只**按该协议切，不再叠加启发式（避免"你告诉了我协议却按另一种结构切"）。
    - **解析能力走注入，widget 不 import `main_gui`**：`main_gui._ensure_serial_tool_tab` 调 `tab.set_parse_provider(self._serial_parse_provider)`（与 `set_serial_worker` 同一约定），回调返回 `(摘要, 解析表)` 且与单帧页/批量**共用同一套分派**（`_get_current_parser` + `build_gui_parser` + `_get_summary_from_table_data`），保证「串口工具看到的解析」与「复制到单帧页解析」逐字段一致。
    - **发送与接收都解析**（1.23.48 起）：`_queue_parse(frame, protocol, channel)` 的 `channel ∈ {rx, tx}` 决定入哪个队列；TX 用**该条命令自己的协议**、RX 用锁存的「最近发送命令的协议」。`_tx_log_queue` 与 `_rx_log_queue` 元素**都是** `(kind, text)`。
    - **失败不伪造**：回调抛异常 / 返回空表 → 只输出 `[解析·<短名>] 失败：<原因>`（fail 配色），不出半成品字段；原始 `[TX]`/`[RX]` 行始终完整。
    - **RX/TX 日志队列元素是 `(kind, text)`**（`kind ∈ raw/parse/fail`，决定配色；raw 用各自队列的 tx/rx 配色）；**burst 只对各自队列的 `raw` 计数**：一批超 `LOG_FLUSH_BURST` 时只输出「摘要 + 首帧 + 末帧」，同批解析明细整批丢弃（防刷屏）。改 `_flush_log_queues` 或队列元素结构必须同步 `test/test_serial_tool_widget.py` 的 `raw_texts/parse_texts/fail_texts/tx_raw_texts/tx_parse_texts` 辅助函数。
    - **`parse_max_lines` 默认 `0` = 不限制**（可选 0~2000，spin box 0 显示为「不限制」）：现场实测国网「查询从节点ID信息」**一条应答帧就有 113 行**解析（22 行帧级字段 + 1 行从节点总数量 + **15 个节点 × 6 行**），默认截断会让现场看不到完整结果。`format_parse_rows` 里 `max_lines <= 0` 即不截断。**注意「113 行」与报文里的「从节点总数量 = 113」纯属数字巧合** —— 解析器只输出「本次应答数量」个节点（实测 15 个），不是 113 个。
    - **改参数默认值必须配配置迁移**（1.23.49 踩坑，通用教训）：参数一旦被保存过就会把**当时的默认值**写进 `serial_tool_config.json`，而 `merge_params` 只在「键不存在」时才用新默认值 —— 于是「改了默认值」对老用户**完全不生效**（实测：1.23.48 已把 `parse_max_lines` 默认改为 0，用户日志里仍显示「已省略 83 行」，因为 1.23.47 那次运行把 30 存进了配置）。做法：升 `CONFIG_VERSION` + 在 `load_config` 里按 `version` 调 `migrate_params`（旧默认值 → 新默认值，用户特意设过的其他值保留；回写后版本升级，不会来回抖动）。**以后改任何参数默认值都要照此办理**。回归：`test/test_serial_proto_frame.py` 第 [9] 段。
    - **`export_commands` 统一补齐并归一化 `protocol` 键**（程序内直接构造的命令可能缺它）；旧配置/旧导出文件缺该键 → `coerce_protocol` 回落 `None`（不解析）。回归：`test/test_serial_proto_frame.py`（84 项）+ `test/test_serial_tool_widget.py` 第 [19]~[23] 段。
    - **前导 FEH 已由分帧层跳过（1.23.78）**：68 家族（`ft12_68` / `dlt645` / `dlt698_45` 三种策略**与未指定协议的启发式**）先按 `_wakeup_base`（= `wakeup_prefix.wakeup_prefix_len`，**单一来源，不要在分帧层另写 FE 扫描**）跳过帧首连续 `0xFE`，并且**返回值含前导字节数**（调用方仍按 `buf[need-1] == 0x16` 自证，故三个调用点零改动）；`_frame_incomplete` 里「只有 FE、还没见到 `68`」也算**已开始未收全**。HDLC（`7EH` 定界）与 DLMS Wrapper（`00 01` 版本头）**不**加前导容忍。现场收益：`FE FE FE FE 68 21 00 … 38 16`（39B 698.45）按 14+25 两块交付只出 **1 行**（修前 2 行）。回归：`test_serial_proto_frame.py` [12] + `test_serial_tool_widget.py` [34]。
    - **断帧可调（1.23.78）**：`rx_framing_mode`（`auto` = 有协议按结构特征 / 无协议按字节超时+68 自证；`timeout_only` = 忽略结构）+ 4 个超时 `rx_byte_idle_ms` / `rx_raw_max_hold_ms` / `rx_frame_idle_ms` / `rx_frame_hold_max_ms`（默认 = 原常量 `RAW_FLUSH_DELAY_MS` / `RAW_MAX_HOLD_MS` / `FRAME_IDLE_MS` / `FRAME_HOLD_MAX_MS`）。因为**默认值等于旧常量、只新增键**，`CONFIG_VERSION` **不动**（改既有默认值才需要迁移，见陷阱 49）；`FRAME_TIMEOUT_RANGES` 是 UI spin range 与 `merge_params` 夹紧的**唯一来源**。`timeout_only` 下 `_on_raw_data` / `_flush_raw_display` / `_flush_raw_display_now` 全部跳过结构路径。断帧依据说明行走 `_log_framing_summary()`，只在**设置变更 / 协议变化 / 每轮开始**时输出 —— **不要**逐帧打印（AGENTS 陷阱 58 的 burst 精神）。
60. **串口工具「日志自动保存到文件」的六条契约**（1.23.54 起，改 `serial_tool_widget.py` 日志相关代码前必读）：
    - **写入点是 `_log()`，且只能是它**：`_log` 是日志窗口的**唯一出口**（`_flush_log_queues` 也走它），文件写在 `_log` 里调 `_save_log_line` ⇒ **面板显示什么、文件里就是什么**。不要另开「按 `[TX]`/`[RX]` 前缀抓行」之类的第二套过滤 —— 那正是「显示发送/显示接收」关掉后两边不一致的来源。回归：`test/test_serial_tool_widget.py` 第 [31] 段（「面板新增的每一行都在文件里」「显示发送关闭 → 文件同步不写」两条）。
    - **文件不截断、窗口截断**：日志窗口 `setMaximumBlockCount(10000)`，文件一直追加 —— 现场跑完还能回到最早的帧。不要顺手给文件也加上限。
    - **`LogFileWriter` 是纯逻辑无 Qt**（可直接单测）：写一行 `flush()` 一次（崩溃/断电尽量保住）；`text` 含换行时**按物理行逐行**加前缀；`header` / `write_raw()` 是**原文行**（文件头上下文、文件尾统计，不带时间戳前缀）。**`_write` 必须同时捕 `OSError` 与 `ValueError`** —— 句柄被外部关掉时 Python 抛 `ValueError: I/O operation on closed file`，只捕 `OSError` 会把异常抛进 GUI 线程（实测踩到）。
    - **默认目录由「本页配置文件的目录」派生**：`log_dir()` = 用户选择 → 否则 `default_log_dir(os.path.dirname(self._config_path))`（= 数据目录下的 `Output/`，已被 `.gitignore` 排除）。**不要直接调 `app_paths.app_data_dir()`**：那样测试沙箱（`_config_sandbox` 只重定向 `data_path`）挡不住，跑一次测试就会往开发机真实数据目录里拉一堆日志文件。
    - **失败必须外显且不递归**：打开失败 → 弹窗 + 勾选回弹（`blockSignals` 包住 `setChecked(False)`，否则会重入）；写失败 → 先把 `_log_writer` 摘成 `None` 再 `_log("…已停止自动保存：<原因>")`，这样提示行不会再往坏文件里写（否则无限递归）。**断网/磁盘满/目录被删都要按此处理**，不许静默丢日志（陷阱 23 的同一精神）。
    - **`cleanup()` 的顺序与副作用**：`_stop_send()` → `_flush_raw_display_now()` → **`_flush_log_queues()`** → `_stop_log_recording()`（写统计尾 + 关闭）→ 落盘配置。**第 3 步是本版新增的行为**：旧版残留队列（最后几帧原始行、解析行）在退出时直接丢；现在会先刷进窗口与文件（`test/test_serial_tool_widget.py` 第 [17] 段「cleanup 时把聚合缓冲刷出」的断言已相应改为**看窗口内容**，因为队列随即被清空）。勾选状态**不改**（当偏好持久化，下次启动仍自动保存）。
    - 参数：`log_auto_save` / `log_dir` / `log_timestamp` 三个**新键**（旧配置缺键 → 默认关闭，行为与旧版完全一致 ⇒ **不需要** `CONFIG_VERSION` 迁移，见陷阱 58 最后一条：只有「改默认值」才需要迁移）。

61. **协议12（模组化终端功能模块接口）：文档无示例帧，A-XDR 布局靠同族标准实证；三处编码开关是唯一假设来源**（1.23.58 起，改 `modular_iface_axdr.py` / `modular_iface_data.py` 前必读）：
    - **两层字节序不同，不可互相套用**：链路层 `68 | L(2B) | C(2B) | Data | FCS(2B) | 16` 的 L/C/FCS 是**小端**（§5.1「低字节在前，高字节在后」）；而 APDU 内的 DT / 整型 / `date_time` 属 **A-XDR → 大端**。1.23.57 的原实现把链路层的小端与 BER 长度域一起套到 APDU 上，导致 APDU 内所有多字节字段错位。
    - **链路的长度域语义与南网/国网不同**：`L = 数据域字节数`，**整帧 = L + 8**（南网/国网是 L 即整帧长）。批量提取 `_extract_modular_frames` 与校验器都依赖这条。
    - **铁证只有一处，而且是跨标准的**：协议12 文档 `grep 示例` 为空（**通篇没有一条示例帧**），三个开关的取值靠同族标准 DL/T 698.45 附录 H.1.1「登录」的真实编码推导：`05 07 09 19 05 16 20 SA | 01 | 00 | 00 00 | 00 B4 | 07 E0 05 13 04 08 05 00 00 A4` —— `07 E0`=2016、`00 B4`=180、`00 A4`=164 ⇒ **大端**；且 SEQUENCE 内的 `date_time` **连自身标记 0x19 都没有** ⇒ **定长类型在 SEQUENCE 内不带 tag、不带长度域**。自检：2016-05-19 是周四 ⇒ `day_of_week = 04` ✓
    - **编码假设只能有一份**：`modular_iface_axdr.AXDR_TAG_IN_SEQUENCE` / `AXDR_LEN_FOR_FIXED_IN_CHOICE` / `AXDR_VAR_LENGTH_BYTES` 是**唯一**来源（现取值 `False` / `False` / `1`）；**禁止在某个解析函数里另写一份猜测**（原实现的 `_take_axdr_uint`/`_take_axdr_string` 就是「探测式 + 取不到静默返回 0」，会让真实帧字段无声消失，已删）。
    - **拿到真实帧的第一动作是跑 `verify_frame(frame)["axdr_tail"]`**：非 0 即当前假设不符，把 3 个开关的 **8 种组合**枚举一遍，能过的那个把**实测依据**（帧来源 + `axdr_tail` 变化）写进注释，而不是往解析函数里加特例。
    - **静态表单一来源** `modular_iface_data.py`（附录 B/C/D~L/M 与表1/2/3/5/11/13）：禁止在解析器/查询页/Web 各写一份。**已修正的错表**：`DAR` 只能是**表11 的 4 个值**（0 成功 / 1 拒绝读写 / 2 信息类未定义 / 255 其它；旧表 21 项形似其它协议）；DT 位段改 **4+4+8**（表22 按 5+3+8 会把 `0x4000` 解成 DTA1=8H 模拟量，与附录 G / §7.6「4H 遥信脉冲」冲突 ⇒ 取与附录及 §7.3~§7.11 全部自洽的一侧）。
    - **文档自身的矛盾（记录、不臆造）**：① 表22 的 DTA1 位段 vs 附录 G/J/K/L（见上，需实测帧定论）；② §6.3.9 表12 写「单位见附录 L」，实际在**附录 M**（附录 L 是回路状态巡检模块）；③ 附录 L.2 写「信息类定义见 K.3」应为 **L.3**（K.2 的「见 K.3」才是对的）；④ 附录 M 表31 第 60~64 行**列错位**（已按原文逐字抄录，未自行「修正」）。
    - **容错显示**（陷阱 23 同一精神）：长度域不符 / FCS 不符 / 截断 / 确认帧带数据域 / 信息帧无 APDU / APDU 未解完，一律**继续解析并输出已能解析的字段** + 醒目 `⚠` 行，**不得返回空表**。
    - **未确证的 6 条**（需实测帧才能定论；已集中在可切换处，别硬改）：① 三个开关默认值；② `array`/`structure` 长度域是**元素个数**还是字节数（现按元素个数，依据 698 附录 H.3.2）；③ `bit-string` 位序（现按字节内 LSB-first）；④ 表18 通道列表是否每元素再套一层 `structure`（现按 `个数(1B) + N×(接口类型 1B + 功能配置 1B)`；一处可切：`encode_channel_list`/`decode_channel_list`）；⑤ 变长类型长度域是否 BER 长形式（>255 时现抛可读错误，不静默截断）；⑥ DT 5+3+8 vs 4+4+8。
    - **回归**：`test/test_modular_iface.py`（430 项，含 meta 非死代码 / ⚠ 容错行 / 13 模板闭环 / 批量摘要与类型列接线）+ `test/test_modular_iface_axdr.py`（185 项，含 698 oracle **独立**对拍、附录 A `fcstab` 全表 + crcmod 交叉验证）。

62. **从 cmd.exe 直接启动的 Python 会让 GUI 测试以 0xC0000409 崩溃（假红，2026-09-23 实测）**：
    - **现象**：`bg_run` 里直接跑 `python release_check.py` → `PASS=65 FAIL=32 WARN=2`，32 项**全部是 GUI/offscreen 测试**，报 `exit=3221226505`（= `0xC0000409` `STATUS_STACK_BUFFER_OVERRUN`，fastfail），且 **`stdout`/`stderr 全空**（release_check 的 `tail` 为空所以只打 `exit=`）—— Python 块缓冲（8KB）还没 flush 就 fastfail，输出全丢；打印量超 8KB 的会只捕获到前半段（`test_modular_iface.py` 就是这样）。同一批测试**单独跑（父进程是 pwsh）则全部 RC=0 全绿**。
    - **定位矩阵（实测，逐项排除）**：`cmd.exe → python → 测试` = **崩**；`cmd.exe → pwsh → python → 测试` = **不崩（RC=0）**；`pwsh → python → 测试` = 不崩。**与 `chcp` 无关**（`chcp 65001` / `chcp 437` / 不设，三者全崩）；**与 stdin 无关**（`inherit` / `DEVNULL` / `PIPE` 全崩）；**与具体测试文件无关**（问题文件在 pwsh 父进程下逐项通过）。⇒ 唯一变量是**直接父进程是不是 PowerShell**（根因未继续下探，但复现稳定、固定两次跑出完全相同的 32 项）。
    - **处置（写进习惯）**：凡**从 cmd 侧**发起的批量测试 / 自检 / 发版门禁，**都套一层 pwsh**。`bg_run` 的写法：
      ```
      # 先把环境与命令写进一个脚本（避开多层引号）
      pwsh.exe -NoProfile -NoLogo -NonInteractive -File "%TEMP%\run_rc.ps1"
      # run_rc.ps1 内容：Set-Location "E:\python\南网解析工具"; $env:PYTHONIOENCODING="utf-8"; python release_check.py; exit $LASTEXITCODE
      ```
      `%TEMP%` 的脚本用 `pwshu` + `Set-Content -Encoding UTF8` 生成最简单（不要 `Set-Content` 成 GBK）。
    - **判别假红的手感**：结果里失败项**输出为空 + 退出码恒为 3221226505** ⇒ 先按本条复核，**不要动代码**（1.23.57/58 的协议12 工作就被这个现象困了一轮）。若只有**少数** GUI 测试崩、其他 GUI 测试过，才可能是代码问题。
    - 与 §10 1.17.1 记录的「本机已知 MainWindow 关闭期 fastfail」是同一个现象；本条给出了**精确触发条件与避开手法**。

63. **按钮宽度不得写死 —— 本项目字号可配置，写死必裁字（2026-09-23 现场实测）**（改任何工具栏 / 按钮布局前必读）：
    - **现象**：TCP 监控「应用层帧」工具栏 4 个按钮文字显示不全（现场截图里「记录目录」只显示成「记录目」）。根因是 `setFixedWidth(80)`，而 QSS 主题下这 4 个「16px 图标 + 4 个汉字」的按钮 `sizeHint().width()` 已是 **92px**（带菜单下拉箭头的「记录目录」再 +12px = **104px**）⇒ **默认 10 号字就裁**；本项目字号可配置（`theme_settings`，7 套主题 × 任意字号），12 / 14 号字时需 **104 / 116~128px**。`QPushButton` 不会用省略号缩排，**只会截断** ⇒ 「宽度 < sizeHint」等价于「文字被裁」。
    - **判据（唯一可靠）**：布局跑完后 `btn.width() >= btn.sizeHint().width()`。`sizeHint` 已含图标 + 文字 + QSS 内边距 + 菜单箭头，就是「不裁字的最小宽度」。**必须在 `show()` 之后量**：headless 下未 show 的 widget 没有 geometry，`width()` 是默认 **640**，量出来永远是「不裁」—— 假绿（本缺陷最初就是这么被测漏的）。
    - **正确做法**：`gui_utils.fit_btn_width(*btns)` —— 取组内最宽者的 `sizeHint` 设为 `minimumWidth`（**只设下限，不设上限**）。字号变大时 `sizeHint` 继续增长、布局仍会满足它，故**切主题 / 改字号后无需重算**；反之写死 `setFixedWidth` 就必须在每次切主题时重算，迟早漏一处又裁。`test/test_btn_width_fit.py` 用「`maximumWidth` 仍等于 `QWIDGETSIZE_MAX`」钉住「没写死」这一点。
    - **别只按参考窗口量**：现场截图 1901px 宽，把窗口拖窄到 900px 时这 4 个按钮仍稳定在 104px（压缩压力落在表格 / 分栏器上）⇒ **无需**为窄窗另加横向滚动。
    - 现状核查（1.23.59，一次性脚本未入库）：主窗口全量扫描 **170 个可见按钮，零裁字**，即该缺陷仅此一处。改按钮 / 工具栏布局后请按上述判据抽查。
    - **文案会变的按钮要按「候选全集」取下限**（`fit_btn_width_for_texts`）：在线监控器「帧类型 / MSDU类型」写死 100 / 120px，默认 10 号字下只要**单选**「选择确认帧(SACK)」（按钮显示截断后的 `选择确认帧(`）就需 **103px** ⇒ 当场裁字；只按当前文案「全部」（68px）取下限完全不够。该函数临时 `setText` 量完再恢复（`QAbstractButton.setText` 不发信号，无副作用）。**候选文案必须与运行时文案同源** —— 两者共用 `monitor_widget._short_label` / `_BTN_TEXT_MAX`，改截断长度时两处一起动，否则取宽失真、又开始裁字。
    - **`setFixedWidth` + QSS `min-width` 会退化成「纯上限」**（实测）：在线监控器「浏览」按钮写了 `setFixedWidth(60)`，实际却是 `min 68 > max 60` —— QSS 的 `min-width` 覆盖了 min，只剩 `max=60` 生效 ⇒ 宽度**只减不增**，字号一大必裁。所以**不要用 `setFixedWidth` 给带文字的按钮定宽**；要「至少这么宽」就用 `minimumWidth`。
    - **大字号 / 最小窗口无需额外改造**（2026-09-23 实测，故**未**引入 FlowLayout 折行）：主窗口在最小尺寸 **1000×700** 下切到 TCP 监控页，10 / 14 / 16 / 24 号字下这 4 个按钮都不裁字（24 号字需 168px、实得 180px；窗口自身的布局最小宽度随之增大，不会把按钮压下去）。抽查脚本记得 `show()` 之后再量。

64. **协议8（698.45）A-XDR 数据域必须大端，链路层必须小端，两层不可互套（2026-09-29 修正）**（改 `dl_t698_45_axdr.py` / `dl_t698_45_frame_gen.py` / `dl_t698_45_apdu_parser.py` 前必读）：
    - **现象**：现场帧 `… 05 FF FF 9E D0 …`（OAD `20 04 02 01` = 有功功率分相数值组）本工具解析 `-794886145`（按小端读成 `0xD09EFFFF`），官方工具为 **-24880**（按大端读 `0xFFFF9ED0`）。矛盾点即 bug 现场：同一帧里 OAD 的 OI 已按大端（`0x2004` 正确），紧随其后的数据元素却按小端。
    - **判据（协议文档自带，可复查 `协议文档/8.698.45协议/面向对象的用电信息数据交换协议(20210910).md`）**：① L347「低字节在前，高字节在后」⇒ 链路层长度域/HCS/FCS **小端**；② §7.1「APDU 编码规则遵循 A-XDR，详见 DL/T 790.6—2010」⇒ APDU 内多字节 **大端**；③ 附录 H.1.1「登录」逐字节示例 `00 B4`=180s、`07 E0`=2016、`00 A4`=164ms、`02 5F`=607、`02 DA`=730 —— 只有大端成立。先例：协议12（陷阱 61）已把「链路层小端 / A-XDR 大端」写成上线契约。
    - **修正范围**：`dl_t698_45_axdr.py` 的整型（long / long-unsigned / double-long / double-long-unsigned / long64 / long64-unsigned）、浮点（float32 / float64）、`date_time` / `date`（年与毫秒）、OI/OAD/OMD 的 OI、TI 间隔值全部改**大端**；**编码侧同步**（否则组帧↔解析不自洽）；`dl_t698_45_frame_gen.py` 的心跳周期 / 客户机 APDU 最大长度 / 期望帧最大帧长 / 期望超时时间等 2 字节字段改 `>H`。**链路层（`dl_t698_45_parser.py` 的长度域/HCS/FCS）与组帧长度域/FCS 保持小端，不得「一刀切」**。
    - **连带修复**：LINK 预连接 `_parse_link_request` / `_parse_link_response`（标准表38/39）原把请求类型/结果/心跳周期/时间标签当**带 tag** 的 A-XDR 元素解 ⇒ 标准附录 H.1.1 示例直接解析失败。SEQUENCE 内定长字段**不带 tag、不带长度域**（同陷阱 61 的规则），已改为定长切分（1B PIID / 1B 请求类型·结果 / 2B 心跳周期(大端) / 10B date_time ×N / bit7 时钟可信标志）。
    - **回归**：`test/test_dl_t698_45_endian.py`。改这里时注意：**历史解析值全部作废**（从错误变正确），既有测试里按旧小端写死的期望值必须同步重写。

65. **协议9 组帧页（1.23.64 起）三个已修真缺陷 + 一条可见性口径**（改 `csg_test_frame_gen_widget.py` / `csg_link_frame_gen.py` / `csg_new_gen_frame_gen.py` / `frame_gen_widget.py` 前必读）：
    - **QSpinBox 的上限是 C++ int，不是 `0xFFFFFFFF`**：信标时间戳 / 信标周期是 32bit 字段（`LinkFieldSpec.maximum=0xFFFFFFFF`），`spin.setRange(0, 0xFFFFFFFF)` 抛 `OverflowError`。而 `_rebuild_fc_fields` 是**一次遍历把字段建完**，异常会打断整个 ① 区重建 —— 现象是「切到信标帧后 FC 区还是 SOF 的字段、输出也仍是上一帧类型的 MPDU」，极易误判成「下拉信号没接上」。**ED 时间戳同理且更隐蔽**：它是真实 Unix 秒量级（`0x68xxxxxx` > `0x7FFFFFFF`），此前上限被夹到 `0x7FFFFFFF` —— 既填不进真实时间戳，回填时 `setValue` 还会直接抛 `OverflowError`（1.23.65 修）。现在满 32bit 字段一律用宽整数文本框 `_WideIntEdit`（接受十进制 / `0x` 十六进制，信号是 `textChanged` 不是 `valueChanged`），且**所有回填赋值统一走 `_write_widget_value()`（先夹到控件范围再 setValue）**，不要在任何地方直接 `setValue(int(x))`。
    - **载波映射表索引只允许一个解析入口**：`_ensure_cmt_index` 对信标帧有特例（按 **BPLC** 语义反查：136→4 / 520→8）——因为表18 该字段只有 **4bit**，而 ISAC 的 TMI 可达 27。`build_link_frame` 里**不得**再按 `cfg.std_version` 预反查一次：那会让 `cmt_index` 不再是 `None`，特例被跳过，信标帧直接抛「载波映射表索引 超出 4bit 范围：16」。
    - **`FrameBuildResult.hex(layer)` 的层字典是「无条件求值」的**：`mac_frame` 曾写成 `self.mac_header + self.msdu`，而 SACK 两者皆 `None`、信标只有 `msdu` ⇒ `TypeError` ——**任何** `hex(层)` 调用（包括 `parse_rows` 内部的 `hex("app")`）都会崩，GUI 预览整块空掉。派生层必须 None 安全；确实没有该层时要抛可读的 `FrameBuildError` 而不是 `TypeError`。
    - **预设命令页可见性按 `preset_mode` 判定，不能沿用 `frame_gen_mode`**：协议9 有组帧页但没有预设库，按 `frame_gen_mode` 判定会多出一个**空的**预设页，且组帧页「添加到预设」会经 `preset_buttons._get_path` 的兜底分支把协议9 的帧写进 **`GW_command.json`**。协议9 下该按钮必须隐藏（`_on_add_to_preset_clicked` 亦加了拦截）。
    - 回归：`test/test_csg_frame_gen_gui.py`（71 项：SOF/信标/SACK 三型闭环、24 模式全量、输出层次四档、折叠状态收集/恢复、协议切换回退、按钮不裁字）。

66. **批量解析工具栏合并成两行（1.23.66 起）后的三条硬约束**（改 `create_batch_parse_tab` 工具栏 / `FlowLayout` 前必读）：
    - **「预处理 + 脚本」这一行必须把导出按钮排除在外**：4 个导出按钮（导出 Excel / JSON / 选中 + 时序图）合计 ~470px，留在合并行里单行需 ~1700px ⇒ 1366×768 下照样折成两行，等于白合并（**实测**：这正是第一版的失败原因）。现布局是 `row0 = 核心操作 + 导出 + 帧计数`、`row1 = 预处理 + 脚本`，两行都是 `FlowLayout`（够宽一行、窄窗自动折行、永不重叠）。**实测阈值**：窗口 ≥ **1264px** 两行各自一行（工具栏 52px，原三行 80px）；1230~1263px 只有 `row1` 折行（82px）；< 1230px 两行都折（1000px 默认窗口下 104px，比原三行高 ~24px）—— 这是「把导出留在工具栏右上角、不改变用户习惯」付出的代价，接受它就别再把控件塞进这两行。
    - **可编辑 `QComboBox` 的 `sizeHint()` 把 `placeholderText` 算进宽度**：命令框那条 40 字符长示例实测 **481px**（比最长的一条命令还宽），换短示例后 371 → 250px。**改这句占位符文案就是改布局宽度** —— 回归 `test/test_batch_toolbar_layout.py` 用 `sizeHint() <= 320` 钉住。**不要**改用 `setMaximumWidth` 压制：那会让宽屏剩余宽度全浪费、下拉框再也不跟着变宽。
    - **`FlowLayout` 的 stretch 是可选能力**：`FlowLayout(..., stretch=True)` + `addWidget(w, stretch)` / `addStretch()`（默认关闭 ⇒ 顶部协议组口径不变）。`_row_widths()` 把行内剩余宽度按权重分给指定子项与弹性空隙；**拉伸只改宽度，`_do_layout` 必须把同一行后续项的 x 一起右移**，否则变宽的下拉框会盖住后面的按钮。
    - 顺带：解析进度条与「取消」已从工具栏移到**底部状态栏**（只在解析中出现），别再往 `row0` 加随解析显隐的控件 —— 那会让第一行在 1366 下溢出。回归：`test/test_batch_toolbar_layout.py`（**59 项**：1366 基准两行各一行、宽窗一行且下拉框吃余宽、徽章贴行右端、进度条/取消在状态栏、命令框 `sizeHint() ≤ 320`、2560→760 十三个宽度零重叠）。

67. **协议9 信标管理信息条目 `0x10`（代理角色条目）的代理站点 TEI 是「连续 12 比特位流」，不能按每 2 字节一个切（1.23.67 起，改 `_parse_beacon_entry_detail` 前必读）**：
    - **表72 原文（第4部分 · 代理角色条目）**：`代理角色条目头` 字节0 bits0-7 = 8 比特（0x10）；`代理角色条目长度` 字节1 bits0-7 + 字节2 bits0-7 = **16 比特**（可变总长度）；`代理节点1TEI` 字节3 bits0-7 = **12 比特**（跨到 字节4 bits0-3）；`代理节点2TEI` 字节4 bits4-7 = 12 比特（跨到 字节5 bits0-7）；…… `代理节点NTEI` 可变字节 bits0-7 = 12 比特；`保留` 末字节 bits4-7 = 4 比特（「若总的代理站点个数为偶数个，则无此保留位」）。
    - **表72 的规则**：长度字段之后是 N 个**连续 12 比特**的代理节点 TEI（LSB 优先）—— 代理节点1TEI = 内容字节0 bits0-7 + 内容字节1 bits0-3；代理节点2TEI = 内容字节1 bits4-7 + 内容字节2 bits0-7 ……（**位域跨半字节，相邻两个 TEI 共享同一个字节**）。与表61 站点TEI、`0x0E` 精简条目同一约定（都走 `_extract_bits`）。
    - **条目里没有独立的站点计数字段** ⇒ 只能由内容比特数反推：`N = 内容字节数 × 8 // 12`（表72：内容 = 12N 比特，N 为奇数时末尾补 4 比特保留位）。
    - **旧实现（按每 2 字节一个 TEI + `内容字节数//2` 当站点数）漏解**：用户现场帧 `10 06 00 01 70 00`（长度字段 2 字节 = 表72 的 6 → 条目长度 6 → **内容 3 字节 = 2 个 12 比特 TEI：1 和 7**）被解成「代理站点数: 1 / 代理[0]TEI = 1」，第 2 个 TEI（内容字节1 高4位 `0x7` + 内容字节2 `0x00`）**整段丢掉** —— 即用户报的「代理角色 TEI 解析不对」。另一帧 `10 04 60 00` 只有按**1 字节长度字段**才自洽（按 2 字节读得 `0x6004`=24580 的荒谬长度，会把其后条目全吞成「代理角色条目 28字节 / 代理站点数 14」），实测 `test_std_beacon_proxy_role_entry_real` 走的正是容错回退分支、`条目长度` 行带「长度字段实发 1 字节」注——两个真实帧一个走表59 正途、一个走回退，两条路径都在用。
    - **固定长与可变长混用**：`0x10` 的条目长度随代理站点数变化（内容 = `12N` 比特补至整字节）⇒ 同一字段的字节偏移不固定，**不要**按固定偏移读；`条目尾保留位` 行仅在内容比特数 % 12 == 4 时出现（表72「代理站点个数为偶数个时无保留位」）。
    - **长度字段宽度按表59 保持 2 字节**（`BEACON_ENTRY_MAP[0x10] = 2`），仅当 2 字节声明值超出剩余字节时才退回 1 字节重读（既有实机容错，勿删）—— 上面两个真实帧正好一个 2 字节、一个实发 1 字节，两条路径都在用。
    - 回归：`test/test_csg_new_gen.py::test_std_beacon_proxy_role_entry_12bit_real`（用户实帧 114 字节：6 条条目链 22/34/4/10/6/31 不变、TEI = 1/7、高亮 96-97 与 97-98、偶数站点无尾保留位行）与 `test_std_beacon_proxy_role_entry_real`（奇数站点帧补「条目尾保留位 = `4bit`」断言）。**变异反证**：把 `n_nodes = ln * 8 // 12` 改回 `ln // 2`，新用例实测变红（`代理站点数: 1`）。
    - **协议11（HDC 1.0）的同名条目 `0xC1` 不适用本条**（不是同一份规范）：本仓库 `hdc10_parser._parse_beacon_entry_content` **没有** `0xC1` 分支，代理角色内容目前只显示条目名 + 原始内容（`0xC0/0xF0` 时隙分配已实现）。若要补实现，先查 HDC 第4-2部分表46 的字段定义，**不要照抄新一代的 12 比特位流规则**。
68. **组帧页（`frame_gen_widget.FrameGenWidget`）的 Qt 子控件只能「惰性创建」，且新增 `def` 绝不能插在 `__init__`/`setup_ui` 中间（2026-10-10 实测）**：
    - `test_modular_iface.py::test_frame_gen_gui` 在 offscreen 下 `FrameGenWidget()` → `deleteLater()`，**退出期偶发 0xC0000409（STATUS_STACK_BUFFER_OVERRUN）**：它是 Qt 析构期的时序脆弱点，**新增整页 Qt 子控件会抬高触发率**（实测 HEAD 无 9/13/14 组帧页时 0/12；带 9/13 页时约 3/12）。
      新增协议组帧页时：**子控件在 `_ensure_xxx_gen()` 里惰性 import+构造**（首次切到该协议才建），`left_stack` 里先放一个**空 `QScrollArea` 占位页**即可 —— 这样冒烟测试根本不构造新控件，不改变析构顺序。
    - **另一个坑（真会造成 100% 崩溃且难查）**：把新 `def`（如 `_ensure_xxx_gen`）**插进 `__init__`/`setup_ui` 的语句流中间**，会让后续所有 UI 构建代码变成「上一个方法内的死代码」—— 表现为 `result_hex`/`preview_table` 等属性不存在、退出期崩、且 `ast` 能看到 `__init__` 只有 20 多行。**新增方法一律追加在类内其它方法之间（`def` 行不紧接语句块）**，改完用 `python -m py_compile` + 最小复现脚本（`QApplication` → `FrameGenWidget()` → `deleteLater()`，跑 6 次看退出码）自检。
    - **信号→信号连接是红鲱鱼**：`table.itemChanged.connect(self.changed)`（无参自定义 Signal）在 PySide6 下并不会崩；排查时不要被它带偏，真正的差异在 Qt 对象数量/析构顺序。
69. **蓝牙工具（`bluetooth_core.py` / `frame_addr_fix.py` / `bluetooth_worker.py` / `bluetooth_tool_widget.py`）的契约**（1.23.71 起，改蓝牙相关代码前必读）：
    - **三层拆分，`main_gui.py` 只接线**：`bluetooth_core`（纯逻辑，**禁止** import Qt/bleak，故可脱 GUI 与硬件单测；含 `merge_settings` 宽容合并 + 夹紧、`save_settings` 原子写、`chunk_size_for_mtu`、`split_chunks`、`BleReassembler`）、`bluetooth_worker`（`QObject` + **私有 asyncio 事件循环线程** `"bluetooth-loop"`，`MONITOR_TICK=0.05` 轮询超时切帧）、`bluetooth_tool_widget`（UI + 三个对话框）。**BLE 线程由页面自持**（`_ensure_worker()` 惰性创建）：蓝牙设备不存在「COM 口全局独占」约束，故**不像串口那样由主窗口托管单例**；仍保留 `set_bluetooth_worker()` 注入入口供测试/主窗口托管。
    - **串口侧必须复用主窗口共享的 `SerialWorker`**（`_ensure_bluetooth_tool_tab` 里 `tab.set_serial_worker(self.serial_worker)`）：本页**不做端口/波特率控件**，只订阅 `connection_changed` / `raw_data_received`；`cleanup()` **不得关闭串口**（端口生命周期归顶部「串口配置」与主窗口收尾）。各页各持 `SerialWorker` 会互抢同一个 COM 口（同陷阱 58）。
    - **解析/协议/单帧三件事全部走注入**（widget **不得** import `main_gui`）：`set_parse_provider(self._serial_parse_provider)`（与串口工具页共用同一套 `_get_current_parser` + `build_gui_parser` 分派，保证逐字段一致）、`set_protocol_provider(self._bluetooth_protocol_provider)`（协议下拉跟随主窗口当前协议）、`set_send_to_single_handler(self._send_frame_to_single_parse)`。**主窗口收尾必须调 `bluetooth_tool_tab.cleanup()`**（`_shutdown_threads` 第 6c 步）—— 它 `shutdown()` BLE 线程并收尾日志文件；漏掉会让 asyncio 线程随进程一起被硬杀、日志尾（统计行/停止时间）丢失。
    - **HEX 写错绝不静默降级为文本发送**（本工具相对原工具的关键安全改进）：`parse_plain_text(text, mode)` 的 `auto` 模式用 `looks_like_hex` 判「HEX 意图」（判据：按分隔符切分后**存在长度 ≥2 且全为 hex 字符的片段**），命中即按 HEX 解析，**失败就报错拒发**。原工具的「HEX 失败回落文本」会把 `68 12 0G` 这 8 个**字符的 UTF-8 字节**写到设备上 —— 静默发错比报错危险得多。`hex` 模式强制 HEX、`ascii` 模式强制 UTF-8 文本。
    - **位数不成对（`68 12 0`）也必须拒发**：`serial_tool_widget.hex_str_to_bytes` 对奇数长度 HEX 是**静默补/丢**的（`68 12 0` → `68 12 00`），少打或多打一个字符就变成另一串字节。`hex_odd_nibble_error()` 专门拦这一条，**放在 `looks_like_hex` 之后调用**（先判是不是 HEX 意图，再判写没写对）。
    - **未知 RSSI 必须按未知处理**：bleak 对未知信号强度报 `0`，而 `0` 比任何负阈值都「大」—— `rssi_level()` 里 `value >= 0` 一律返回 0 档（否则未知信号会显示成满格，与 `rssi_text(0) == "--"` 自相矛盾）。
    - **分包按协商 MTU 算，不写死**：`chunk_size_for_mtu()` 用 `mtu_size - 3` 与特征码 `max_write_without_response_size` 取小并夹到 `[MIN_CHUNK, DEFAULT_MAX_CHUNK]`（原工具硬编码 200 字节）；写入先试 `response=False`，失败回落 `response=True`。**重组只有「静默超时切帧」一种语义**（不同特征码独立成帧），断开/掉线前 `flush()` 交出未成帧残包，不丢尾包。
    - **MTU / 写上限必须「连接后轮询 + 每次发送前重读」，禁止把连接瞬间的快照用到底（1.23.80）**：ATT_MTU 由**操作系统异步协商**（Windows 上应用层只能读、不能请求，MS 文档 `GattSession.MaxPduSizeChanged`），连接那一刻读到的常常还是 ATT 默认值 **23（负载 20）** ⇒ 现场表现是「同一台设备有时 20 字节、有时 512 字节」。三条不可拆的约定：
      ① **判据单一来源** `bluetooth_core.mtu_is_unnegotiated()`（`≤ MTU_DEFAULT=23`，含 0/`None`/非法值）；轮询参数 `MTU_POLL_INTERVAL=0.25` / `MTU_POLL_TIMEOUT=3.0` 与 `MIN_CHUNK` 同处。**「对端确实只支持 23」与「结果还没回报」在读数上不可区分**，故超时**只打一行提示、不得报错**；
      ② `_connect_coro` 的 `await self._poll_mtu_if_needed(client)` 必须在 `connected` 与订阅**之后**（否则界面/订阅被白等 3 秒）；断开/换 client/`_closing` 立即静默返回；
      ③ `_write_coro` 在 `_chunk_plan()` **之前**调 `_refresh_live_limits()` —— 分包按**发送那一刻**的真实值（否则重连前读到的 20 会让每次发送都白拆包）。刷新读的是 `_char_objects`（`_collect_characteristics` 顺手存的**活特征码对象**，断开时 clear），**不进**投给界面的 dict；**有变化才**更新 + 发 `mtu_updated` + 记日志，无变化完全静默（不得每包刷日志）。
    - **`mtu_updated`（`Signal(int, list)`）与 `characteristics_updated` 不可互相替代**：后者语义是「特征码枚举完成」，界面收到会走「沿用/优选 → `_apply_characteristics` → `worker.set_characteristics`（**重新订阅**）」，拿它刷上限会产生多余重订阅、改写用户已选通道、并多打日志。界面 `_on_limits_updated` 只允许更新 `_chars` 缓存 + MTU/特征码标签 + 刷新**打开中**的特征码对话框（`refresh_chars`，保勾选与当前行），**禁止**调 `_apply_characteristics`；`test_bluetooth_widget.py` 用 `worker.char_sets` 计数钉住这一点。MTU 文案抽在 `_mtu_text()`（连接时与实时更新共用），默认值时要写出「ATT 默认值，协商结果未回」。
    - **自定义按钮「协议 + 地址」= 发送时替换地址并重算校验（1.23.81）**：新模块 `frame_addr_fix.py`（纯逻辑、无 Qt），按钮字典新增可选键 `protocol`(int) 与 `addr`(dict[str,str])（`core.normalize_button` 宽容保留；旧按钮无这两个键 ⇒ 行为与改动前逐字节一致）。四条不可拆的约定：
      ① **地址定位与校验算法一律复用既有实现**（不得另写偏移/算法表）：645 → `DLT645FrameGenerator.build_frame(..., scramble=False)`；698.45 → `DLT69845FrameGenerator._assemble_frame`（HCS/FCS 自动）；依瓦 → `yw645_wire.encode_frame`；南网上行 → `csg_uplink_wire.encode_frame`（保留 `resolve_layout` 的原长度域形态）；南网/国网 → 字节拼接 + `Frame.calculate_checksum` / `GDWFrame.calculate_checksum`。**南网 `68 L L C …` 没有第二个 68H**，地址域仅当控制域 **D5=0x20**；**国网**信息域 byte0 **bit2=通信模块标识**、地址域长度 = `12 + 6×高 4 位中继级别`，福建增补（AFN 0x50~0x56）明确不支持；
      ② **先自证再改**：结构（`68…16`、长度域自洽）+ **原帧校验**都必须通过，否则拒绝（避免把别的协议的帧洗成看似合法的帧）；地址**在线长度必须与帧内一致**（改长度会连带改 L/HCS/FCS，v1 不做）；无地址域（南网 D5=0 / 国网 bit2=0）报「该帧不含地址域」；
      ③ **地址写法双认**：含分隔符/`0x` → 按**在线顺序**原样写入；纯书写序（12 位表号 / 依瓦十进制 / 南网上行终端地址十进制）→ 按协议既有编码函数处理。界面提示行必须回显「将写入 N 字节：…」，内容框可解析时给出替换后预览（含校验旧→新）；
      ④ **只在发送时替换**（`_on_custom_clicked` → `_apply_button_address`）：失败**弹框 + 日志且一个字节都不发**；成功日志给 notes；`edit_send` 仍显示**原始模板**（用户口径）。
      `frame_addr_fix` 里协议模块**必须按需导入**（`dl_t698_45_frame_gen` 依赖可选 `crcmod`，模块级导入会让没装 crcmod 的机器连蓝牙页都打不开）；回归：`test/test_bluetooth_addr_fix.py`（96 项，六协议真帧 oracle = 替换后**该协议校验器 0 fail**）+ widget [13]。
    - **自定义报文区的空间治理：按钮随空间自动 + 工具栏常驻 + 可折叠 + 竖向分栏（1.23.82）**：按钮多时**不得**让自定义区按内容一路长高（改前 64 个按钮 ≈ 22 行 ≈ 700px 直接把日志压没），也**不得按固定行数硬封顶**（用户复核：把日志上拖腾出空间后 10 个按钮仍只显示 3 行 + 白滚动条）。四条约定：
      ① **高度 = 内容驱动 + 分栏约束**：`_custom_scroll_limits()` 返回 `(下限, 上限)` —— 下限 = 1 行按钮高（`core.CUSTOM_MIN_ROWS`），上限 = **按钮全部显示所需高度**（按「行数 × 行高 + 间距」算，**不要读 `custom_host.sizeHint()`**：重建后它是旧值/0，会把上限算成一行）；`_apply_custom_scroll_limits()` 在「按钮重建后」与 `restyle_for_theme()` 各调一次。于是**空间够就不滚动、不够才滚动**；
      ② **滚动容器必须是本页的 `ButtonScrollArea`**（`minimumSizeHint()` 由本页显式给定）：直接用 `QScrollArea` 时它的 `minimumSizeHint()` 跟着内层网格走，按钮一多就把「最小高度」透传给分栏器（实测 64 个按钮 → 下半区最小 559px、日志只剩 177px）。并且**下半区不要加尾部 `addStretch()`**，否则腾出的空间被弹性空隙吃掉、按钮区永远长不大；
      ③ **编辑工具栏在折叠区外**：5 个按钮 + 提示由 `_build_custom_group()` 返回的容器持有（折叠只收起按钮网格）；收起时把本区尺寸策略锁 `Maximum`（否则标题与工具栏之间留大片空白），展开恢复 `Preferred`；
      ④ **配置宽容**：`custom_collapsed` / `right_split` 都走 `bluetooth_core.merge_settings` / `normalize_right_split`（坏类型/长度不对/越界逐项夹紧或回落默认，**不抛**）；`right_split` **只在两侧都有真实高度时才采集**（未 show 时 `sizes()` 可能是 `[0,0]`）。
      另注：`custom_group` 就是那个 `CollapsibleSection`（既有断言 `tab.custom_group.title()` 继续可用）。回归：`test_bluetooth_widget.py` [14]（**几何断言前先 `settle()` 多泵几次事件** —— 重建大量控件后一次 `processEvents` 读到的滚动条范围还是 0；**并且要分别量「默认分栏」与「拖大分栏」两档**，只在默认档量会漏掉「腾出空间后仍滚动」这个缺陷）、`test_bluetooth_core.py` [13]。
    - **弹框必须同时留日志**：内容无效 / 未连接 / 回调缺失等路径原先只弹 `QMessageBox`，用户一点确定就没了，现场排查只能靠日志 —— 一律**先 `_log()` 再弹框**。日志的**唯一写窗口点**是 `_append_log`、**唯一写文件点**是 `_save_log_line`（写失败必须告知用户并关掉自动保存，不许静默丢日志，同陷阱 60 的口径）。
    - **落盘走 `app_paths.data_path` 属性访问**：配置存 `app_paths.data_path("bluetooth_tool_config.json")`（`_config_sandbox` 靠 patch `app_paths.data_path` 重定向，**不能** `from app_paths import data_path`）；日志目录默认 `<数据目录>/Output`（复用 `serial_tool_widget.default_log_dir()`，已 gitignore）。**`_save_timer` 必须先于 `_build_ui()` / `_load_persisted()` 创建** —— 载入配置会触发控件 `toggled` → `_schedule_save()`，那时若还没有 `_save_timer`，Qt 会吞掉 `AttributeError`，配置保存随之静默失效。
    - **特征码自动优选只有一个实现（1.23.79）**：`bluetooth_core.rank_characteristics` / `pick_auto`（打分表 `CHAR_SCORE_*` 与族谱 `PASSTHROUGH_UUIDS` 也在这里，调参只改这一处）。**界面禁止再写「取第一个可用」** —— 历史实现正是那样，实测常选到 `2A00` 设备名 / `2A19` 电量 / DFU 特征码。接线顺序也要守：`_on_characteristics_updated` 是「① 按设备地址沿用 → ② 打分优选 → ③ 提示」，且**换到没记过的设备要先清掉上一台的选择**（否则上一台的通道会压住优选）。
    - **一键探测必须等 `subscribe_finished` 才能写**：订阅是异步的，写完才等回包会丢掉首个响应。流程状态在纯逻辑 `core.ProbeSession`（`select → write → wait`，事件 `on_subscribed / on_written / on_frame / on_timeout`）；界面只做「按意图调 worker + QTimer + 喂事件」，并且**仅当该事件真的让阶段前进时才推进**（用 `session.step` 前后对比，防同一意图被重复下发）。**不许 sleep 阻塞 GUI**；候选无接收通道时 worker 也要发一次完成信号（否则探测挂着）。
    - **探测结果与手工选择都按设备地址记忆**（`char_map`：`remember_choice / recall_choice / forget_choice`；上限 `CHAR_MAP_MAX = 20` 按 `ts` 淘汰；坏条目逐条丢弃不影响其它条目）。**全败时必须恢复探测前的选择**（否则界面停在「最后一个试过的候选」，用户以为选对了）；旧的全校 `recv_uuids/send_uuids` 仍写（兼容旧配置），但**命中地址优先**。
    - **探测载荷优先发送框内容**：`core.resolve_probe_payload(..., parse)` 的 `parse` 由界面注入 `parse_plain_text` —— 纯逻辑层不 import Qt 侧实现，也**不写第二份「什么算合法 HEX」**。HEX 写错 → 拒绝且**一个字节都不写**；发送框为空 → 用 `probe_frame`（默认 `41 54`）；配置值是坏 HEX → 用内置默认并**明确告知**（不静默）。
    - **对话框结论必须是文字**：不可用方向除置灰外还要标「（不可写）/（不可通知）」（QSS 主题下置灰看不见，见陷阱 71）；列表按打分**置顶并预选**优选结果，顶部给出推荐依据。
    - **批量替换地址（按协议类别，1.23.84）**：底部工具栏「批量地址…」→ `BatchAddressDialog`（对话框**只给补丁、不直接改按钮列表**，写回统一走 `_set_buttons`）。五条约定：① **默认作用域** = 「已绑定所选协议」的按钮（清除模式 = 已绑定任意协议者），另有 全选/全不选/只选本协议；② **逐按钮用「自己的报文」预检**（`_precheck` → `frame_addr_fix.check_values` + `apply`），**只对勾选行**算错误（未勾选的行不许出现 ⚠ 噪声：给南网按钮换地址时 645 的按钮不该被标成「不是南网帧」）；③ 预检失败行标原因且**默认不勾**；强行勾上 → `QMessageBox.question` 二次确认「将跳过这 N 个」后照改其余，拒绝则**一个按钮都不改**，跳过项经 `result_skipped()` 逐条写 warn 日志；④ 全部失败时不 accept 且 `result_patches()` 为空（状态自洽，防止调用方误读补丁）；⑤ 清除模式（下拉第 0 项）返回 `{"protocol": None, "addr": {}}`，调用方**删两个键**。地址字段/长度/校验算法一律走 `frame_addr_fix`，**禁止第二份**。
    - **地址判据的单一来源**：`frame_addr_fix.addr_lengths_for_frame(frame)`（由帧定 698.45 SA 长度）与 `check_values(protocol, values, frame) -> (回显项, [(标签, 原因)])` 是**唯一实现**，单按钮编辑对话框与批量对话框共用；界面只把回显项原样显示、把错误项拼成 `⚠ 标签：原因`（不要在纯逻辑里拼 UI 文案）。
    - **报文工具「地址替换」= 同一引擎的第 4 处复用**：报文工具标签页粘贴**任意一帧** + 显式选协议 → 替换地址域并重算校验。纯逻辑 `message_tool_widget.replace_frame_address(frame_text, protocol, values) -> (新报文 HEX, notes, error)` 与 `addr_field_errors`（**只做「报文文本这层」编排**：解析 HEX → 协议 6/8 剥前导 FEH → `frame_addr_fix.apply` → 空格分隔回写；地址定位/字节序/算法照旧全走 `frame_addr_fix`，**不得出现第 4 份偏移或算法清单**）。三条口径：① 前导 FEH 沿用 `FE_WAKEUP_PROTOCOLS = (6, 8)`（剥离并**原样恢复**，其余协议带 FE 必须报错，见陷阱 75）；② **不做协议自动识别**（南网/国网同形 `68 L L …`，靠外形猜协议只会误导；错选由 `apply` 的结构+校验自证兜住），协议下拉取 `supported_choices()`（即 0/6/7/8/13/14）；③ `error` 非空 ⇒ 帧**未改动**，界面只把可读原因写进输出区 + 弹框，「替换后报文」结果行**保持原值**（否则用户会以为已替换成功）。回归：`test/test_message_tool_addr_fix.py`（132 项：口径与字段来源 / 六协议真帧 oracle / FE 门控 / 错误矩阵 / 输入写法容错 / 反例自检 / offscreen GUI 接线与失败不污染）。
      另外两条 Qt 坑：`QFormLayout.removeRow(row)` **会连同该行控件一起删除** ⇒ 重建地址行时按控件反查行号再 `removeRow`，**不要再补 `deleteLater()`**（二次删除 ⇒ `RuntimeError: Internal C++ object (QLineEdit) already deleted`；串口页那套「先 `deleteLater` 再 `removeRow(0)`」口径不同，勿照抄）；协议下拉按内容取宽（`addStretch()` 兜住，不整行拉满），弹出列表按最长项 `view().setMinimumWidth(...)`（不写死像素，同主窗口 `_fit_combo_width` 精神）。
    - **工具栏宽度**：本区工具栏现有 6 个按钮（新增…/批量新增…/批量地址…/导出…/导入…/全部清除）+ 尾部 stretch，**没有行内提示标签**（「右键可编辑/删除/移位」已在每个按钮 tooltip 末行）。实测 10/14/16/24 号字下 `width ≥ sizeHint` 全不裁字；**不要**给带文字按钮写 `setFixedWidth`（陷阱 63）。
    - **回归**：`test/test_bluetooth_core.py`（**161 项**，纯逻辑，含 `mtu_is_unnegotiated` 边界、按钮 `protocol`/`addr` 规范化、空间治理两个配置键）、`test/test_bluetooth_addr_fix.py`（**111 项**，六协议真帧 oracle + 错误矩阵 + 反例自检 + 共享校验入口 `addr_lengths_for_frame`/`check_values`）、`test/test_bluetooth_worker.py`（**106 项**，`sys.modules["bleak"]` 注入假 bleak，**不碰硬件**；含 MTU 轮询段：迟到协商 / 只支持默认值 / 发送前重读 / 断开打断）、`test/test_bluetooth_widget.py`（**270 项**，offscreen + 假 worker/假串口；含空间治理：内容驱动高度/滚动/不压扁/工具栏常驻/折叠/分栏记忆 + [16] 批量替换地址：默认作用域/逐行预检/二次确认跳过/清除/端到端/工具栏不裁字）、`test/test_bluetooth_tab_wiring.py`（36 项，构造真实 `MainWindow` 验证接线 —— **改本页接线只跑 widget 那份是假绿**）。五份都在 `release_check.py:CORE_TESTS`。**测试里不要把 `⚠`/`✓` 等字符直接塞进断言 detail**（Windows 控制台 GBK 会 `UnicodeEncodeError` 把测试进程带崩，widget/wiring 两份的 `check()` 已用 `_console_safe()` 兜底）；**断言与 detail 也不要假设 `attempts` 非空**（状态机被改坏时索引会先抛异常，把「变红」变成「崩溃」）。测 MTU 轮询时**先改特征码上限、再改 MTU**（轮询只看「MTU 变了」就结束该轮，反序会出现「MTU 已更新、上限还没读到」的中间态 ⇒ 断言随机）。测发送路径要**先 `worker.become_connected()`**（未连接时页面只提示、不落到 worker，会让「没发送」的断言假绿）。**测几何（滚动条范围/高度）要先 `settle()` 多泵几次事件**，且**封顶的效果要在「分栏给足空间」那一档量**（默认分栏下封顶与不封顶都被压成 3 行，量不出差别 ⇒ 判据假绿）。

70. **主题 QSS 的「表格 / 字段树」组必须同时覆盖 `QListWidget`，新增视图类控件前必须先验「交替行」（1.23.72 起）**：
    - **症状**：列表**隔行看不清**（非交替行正常）。**根因**：各主题的表格组（基类 + `::item:!alternate` / `::item:alternate` / `::item:selected` 四条）原先只写 `QTableWidget, QTreeWidget`，**`QListWidget` 一个都没覆盖**。QSS 是本项目**唯一**的色彩来源（`ThemeManager.apply` 只做 `app.setStyle()` + `setStyleSheet()`，**从不设 `QPalette`**），因此未被 QSS 覆盖的部件（这里是列表的 `alternate-background-color`）会退回**系统调色板** —— 主题与系统调色板不一致时就崩：深色系统（报障机实测 `AlternateBase = #001a68`，`AppsUseLightTheme=0`）+ 浅色主题（`* { color: #000000 }` 黑字）→ 实测对比度 **1.35**（同环境 glass 1.06 / mica 1.12）；反向的浅色系统 + 暗色主题（`color: #e0e0e0`）→ **1.23**。
    - **修法**：补 `QListWidget` 进 5 套带 QSS 主题（default / dark / glass / mica / windowsvista）的**四条选择器组**，配色一律沿用该主题既有表格值（`build_glass_qss` / `build_mica_qss` 的参数化生成自动继承）。**不要在页面里写 light/dark 硬编码样式**（页面只提供 `restyle_for_theme(dark)` 钩子，件 69 之外的同一口径）。
    - **新增任何视图类控件（`QListView` / `QTreeView` / `QTableView` / `QListWidget`…）前先问**：它的交替行 / 选中行 / 禁用态底色从哪来？只要没有 QSS 覆盖，就一定会被系统调色板接管。凡主题给 `QTableWidget` 的规则，`QListWidget` 必须同款——`test/test_theme_settings.py` 1c 节已把这条 + 「深/浅两种注入调色板下交替行与普通行文字对比度 ≥ 4.5」固化成断言，改主题后跑它，别只靠眼看。
    - **量文字可读性别眼估**：`grab()` 取像后按「**只取文字区**（跳过勾选框 —— 勾选框图元的高对比像素会掩盖文字问题）+ 底色取众数 + 文字色取偏离底色最大者」算 WCAG 对比度。**注意 offscreen 合成的调色板是浅色的**：要复现系统深色模式必须 `app.setPalette()` 显式注入（测试就是这么做的），或干脆用真实平台跑一遍（不设 `QT_QPA_PLATFORM` + `Qt.WidgetAttribute.WA_DontShowOnScreen`，可避免弹窗又走真实调色板）。
71. **`~ItemIsEnabled`（置灰条目）在 QSS 主题下**不会**变灰（2026-10-12 实测，尚未修）**：只要主题给该部件写过 `color`（或命中全局 `* { color }`），Qt 就把前景色塞进**所有**调色板组，`QStyleSheetStyle` 下 `QPalette::Disabled` 的置灰被一起覆盖 —— 于是 `bluetooth_tool_widget.CharacteristicSelectDialog` 里「置灰的条目表示该特征码不支持这一方向」的提示与实际渲染**不符**（5 套 QSS 主题下置灰条目与可用条目文字**同色**，实测均为 `#000000` / `#e0e0e0`；原生主题 `fusion` / `windows` 走 Qt 自己的 `Disabled` 组，置灰是正常的，但浅色系统下 `#bebebe` 压白底只有 1.86）。要真灰起来只能在主题里加 `QListWidget::item:disabled { color: … }`（Qt 确实认这个伪状态，实测生效），并注意 WCAG 对**非活动控件**不作对比度要求、别把置灰改得比现在还难读。

72. **协议规定的校验位在现场可能「留空待硬件填充」——不得把「校验不过」当成「不是这种帧」，也不得据此改走另一条帧结构路径（1.23.73 起）**：
    - **场景**（协议11 报障）：台体/模拟器把报文内容组好后落日志，**FCCS / PBCS / ICV 由硬件发射机在发射时填充**，日志里留空为全 0（报障帧 152 字节，前 45 字节有值、其余 0 填充）。这类帧**同样要能解析**，不能弹「解析不出内容」。
    - **曾经的后果**：`hdc10_parser._detect_fc` 把 FCCS 当**唯一判据** → 判「无 FC」；而「判无 FC」分支里 **DT=0（信标）有启发式兜底、DT=1（SOF）没有** → 整帧按「裸 MAC 帧」解，吐一屏错位臆造（版本=1 单跳帧协议、MSDU长度=0、ICV 取到 `00 F0 FF FE` 校验失败、144 字节「多余数据」）。
    - **判据口径（三条，缺一不可）**：① FCCS 通过 → 是完整 MPDU；② **FCCS 有值但校验不过 → 不是**（保持严格，防误判）；③ **FCCS 全 0 → 看帧体结构**（`_looks_like_fc_payload`）。结构判据 = 帧长 ≥ 26 + **只对 SOF 帧（`DT==1`）生效** + 偏移16 是合法 PBH 且置着帧起始位 + `_probe_pb_form(data[17:])` 打分 ≥ `_FC_BLANK_FCCS_MIN_SCORE`(=4)。阈值标定：真实单 PB 现场帧 44 条被误当 FC 解时打分分布 **{0: 28, 1: 16}（最高 1）**，报障帧 **6 分**。
    - **`_looks_like_fc_payload` 绝不做 DT 泛化**：开头为 PBH 的物理块帧（`0x40/0xC0`）其 byte0 低 3 位同样是 0，按 DT=0 统一放开会把 PB 级输入误判成信标帧。
    - **显式级别即契约，但必须有规范硬条件防劫持**：用户选 `fc_pb`/`fc_mac` 时用 `forced_fc` 尊重声明（不再因 FCCS 不过就偷偷改走 MAC 路径），条件 = `flen>=26` + `DT==1` + 标准版本号 0 + **偏移16 是置了帧起始位的首块 PBH**（表37：首块不带帧起始标志即自相矛盾）。**最后一条不能省**：60 条真实夹具里唯一低 3 位为 1 的 `0xC1` 开头 PB 帧，其 `frame_bytes[16]=0x06` 无帧起始位——省掉即被劫持（8 行 → 18 行错位臆造）。
    - **`fc_mac` 同坑（连带）**：`_parse_pb_and_mac_header` 对**首块也跑**「是否省略 PBH」的探测，帧尾 0 填充让 `_probe_pb_form` 的「ICV 全 0」强证据**误命中** → 合法 PBH `0xC0` 被当 MAC 头（PB头=无、MSDU类型=0）。**SOF 首块置了帧起始位时直接采信 PBH**，与 `_parse_pb_block` 的 SOF 分支同条件（防两处漂移）。
    - **「填充CRC-24」必须按协议门控**：`main_gui._fill_crc24` 的 eFC（字节29-31）与逐物理块 PBCS 是**协议9 专属布局**；协议11 的 FC 之后直接是物理块，按协议9 偏移回填会把 CRC 写进 MAC 帧头（实测「组网序列号」由 `0x01` 变 `0xE1`，静默改坏）。现在 `if self.current_protocol != 9` 直接跳过并提示「协议N … 无此布局」；**FCCS（字节13-15）保持对所有协议生效**。
    - **文案口径**：留空一律给「未填充」而不是「校验失败」——FCCS 行 `⚠ 未填充(全 0)：…此处计算值应为 0x…`；PB 尾 3 字节全 0 给 `⚠ PBCS未填充`（与 `⚠ 无PBCS`＝截断区分），**都不判为错误**；FCCS 未通过仍按 FC 解析时追加 `⚠ FCCS 未通过` 行写明依据。
    - 回归：`test/test_hdc10_blank_checksum.py`（**55 项**，`CORE_TESTS`）+ `test/test_hdc10_blank_checksum_gui.py`（**20 项**，`GUI_TESTS`）；**四处修复逐条变异反证全部变红**。
73. **测试文件用 `os._exit()` 退出前必须 `sys.stdout.flush()`（2026-10-12 实测）**：`os._exit` **不冲刷 stdio 缓冲**，而 `release_check.run_test_script` 是**管道**读 stdout（非 tty → 全缓冲），于是「打印完就 `os._exit(1)`」的测试**只留下退出码、失败明细全丢**（实测 `test_hdc10_blank_checksum_gui.py` 初次只剩 `exit=1`、零输出；`test_csg_pbcs_fill_gui.py` / `test_hdc10_mme_full.py` 同样如此）。Qt offscreen 退出期析构可能原生崩溃、必须用 `os._exit` 避开的场合，**改成 `sys.stdout.flush(); os._exit(code)`**（或 `python -u`）；排查时也可先用 `PYTHONUNBUFFERED=1` 跑一遍看真实输出。
74. **协议11（HDC 1.0）跨字节位域**只有一个**打包方向**：字节号小的段是**低位段**（1.23.75 修正；1.23.74 曾写成「`报文头长度` 是唯一例外、字节号小的存高位」，**该结论已被推翻，勿按它改回去**）：
    - **`报文头长度`（6bit，值 = 报文头的「字节数」，不是 4 字节字）**：`(b1 & 0x0F) << 2 | (b0 >> 6)`——**字节0 的 bit7-6 是低 2 位、字节1 的 bit3-0 是高 4 位**。同字节邻居：字节0 bit0-5 = 协议版本号、字节1 bit4-7 = 该报文自有语义（测试模式/配置操作、未应答重传位 …）。
    - **12bit「转发数据长度 / 模式持续时间 / 配置值」**：`((b2>>4)&0x0F) | (b3<<4)`，也是「字节号小的段为低位」；MAC 头 MSDU 长度、事件 0x008 功能码同理。口径统一 = `_bits_lsb`。
    - **⚠ 为什么 1.23.74 那次「实测钉死」是错的（务必理解，否则会再错一次）**：旧口径 `(b0>>6)<<4 | (b1&0x0F)` 与正确值**只在字节0 的 bit7-6 == 0 时**给出相同的「总字节数」——此时 `4 × lowNibble == lowNibble << 2`。而当时用的三个校准帧（`01 53`→12B、`01 61`→4B、`01 02`→8B）**字节0 恰好都是 `0x01`**，因此完全无法判别方向；`01 53` 的「12 字节头」既等于 `3×4` 也等于「值 12 = 12 字节」，属**两个解释撞在同一条证据上**。用户 2026-10-12 的报障帧字节0 = `0x81`（bit7-6 = 0b10）才暴露：旧口径给 33（132B），正确值 6。
    - **四条互证（改这一族字段前先核这四条）**：① 协议10 同字段同口径（`gw_new_gen_cmd_payloads._parse_comm_test`），真实帧 `81 61 20 00 00 00` 的 `报文头长度` = **6**，且该载荷**恰好 6 字节** = 整根报文头（`test/test_gw_ext_cmd.py` T13）；② 本协议 0x0A1 真实帧 `01 53` → 12 字节头，与实测 DATA 自字节 12 起自洽；③ 表2 扩展命令的报文头就是字节0~5 = 6 字节（用户报障帧 `81 C1` → 6）；④ 各报文自家的说明文字（抄表「固定为8」、通用「报文头 4 字节」、注册「下行=20, 上行=36」）与**新值逐一对上**（旧值 2/1/5/9 全对不上）。
    - **协议10 的 `gw_new_gen_cmd_payloads` 已同步收口**（14 处 `hdr_len_high/low` 写法全改成同一公式；均为**显示用**，不影响切片）。**以后新增报文头解析一律写 `((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)`，绝不要再写 `(((b0 >> 6) & 0x03) << 4) | (b1 & 0x0F)`（「字节0 存高位」）**。另注：协议10 的帧类型判定（`gw_new_gen_parser` 的 `hdr_len_high | (hdr_len_low << 2)` + 4~64 合理性区间）**一直是正确口径**——可作为第 ⑤ 条互证。
    - **渲染口径**：`_hdr_len_cells` → 原始值给**按值序**的位段拼装式 `0b0001+0b10`（`+` = 按位拼接，直接可读为数值）、说明给字节/比特归属 + 移位拼装式 `0b10 | 0b0001<<2 = 6`（`_bit_span_note`，协议内只有一种方向，故**不再有 `lsb_first` 参数**）+ 「单位 字节」；解析值列 = `N字节`（不再是 `N×4B=MB`）。**别把 `_bit_span_note` 的 `lsb_first`/「高位段在前」分支加回来**——那是 1.23.74 的误判产物。
    - **动说明列可能连带改摘要**：`batch_core.extract_test_mode_content` 按「(解析值, 说明, 原始值) 里第一个非数值者即模式名」探测 → **测试模式行的原始值必须保持十进制 `6`/`12`、解析值必须保持模式名**；`转发数据规约类型` 的说明被 `test_hdc10_comm_test_ext.py` 逐字断言 `== "DL/T698.45"`，不得追加尾注。
    - **真实夹具要按 `pb_only` 级别跑**：`test/hdc10_real_frames.pkl` 的 60 条是 **PB 级**输入，`auto`/`fc_pb`/`fc_mac` 都到不了应用层（只有 `pb_only` 能解出 `报文头长度`）；60 条里只有 1 条带该行（帧 #25，`01 61` → 4）。
    - 回归：`test/test_hdc10_bitfield_display.py`（**47 项**，`CORE_TESTS`），含用户报障帧（`81 C1` → 6 字节，反证旧口径 33）、**与协议10 同字节同值对拍**、「值 = 字节数」的偏移锚定（确认帧 span / 抄表 DATA 自字节 8 起）、10 组取值三处反解恒等、60 条夹具逐条反解。改这一族字段后**必须跑变异反证**（方向改回旧口径 → 应变红 16 项；位域渲染段序/单位改回旧样 → 应变红 17 项）。
75. **68 家族前导 FEH 唤醒字节：按规范剥离，且剥离后「表格偏移必须整体位移」（1.23.76 起，改协议8/协议6 解析或校验前必读）**：
    - **判据来自规范，不是「容错放宽」**：DL/T 698.45-2017 §6.3.1 字节规则 b)「在有效数据帧前加 4 个 FEH 作为前导码」（`协议文档/8.698.45协议/面向对象的用电信息数据交换协议(20210910).md:509`）；DL/T 645-2007 §5.3.1「在主站发送帧信息之前，建议先发送 4 个字节 FEH，以唤醒接收方。」（`DLT645-2007.md:486`）。**只有协议8/协议6 有这条依据** ⇒ 只在这两个协议启用；协议 0/7/9/10/11/12/13 行为一律不变（`test_wakeup_fe_prefix.py` 有逐协议护栏 + 「白名单之外无 `wakeup_prefix` 引用」源码守卫）。此前把首字节当起始符判据 ⇒ 带 FE 的**合法**帧一律报 `起始字符错误: 0xFE`（用户报障：39 字节全可见却一字段解不出）。
    - **单一来源 = `wakeup_prefix.py`**（`wakeup_prefix_len` / `strip_wakeup_prefix` / `wakeup_display` / `make_wakeup_row` / `shift_row_offsets`，行名常量 `WAKEUP_FIELD_NAME`）。**禁止在调用方或 Web 侧另写一份扫描**（同一教训见陷阱 31/55/61）。
    - **口径**：只跳过帧首**连续** `0xFE`（0~N 个，**不假定恰好 4 个**）；**帧中间的 FE 绝不跳**（那是普通数据）；68 家族首字节恒 `68` ⇒ `0xFE` 不可能是合法首字节，剥离零误伤。`strip_wakeup_prefix` 无前导时是**恒等操作** —— 这是「无 FE 帧逐行不变」硬约束依赖的基石。
    - **三层必须同时改，缺一层就出错**：① **解析**（`DLT69845Parser.parse` / `DLT645Parser.parse` 先剥离再解析，`原始数据` / `raw_hex` 仍保留**用户原始输入**含 FE）；② **表格偏移**（`parse_to_table` 首行插「唤醒前导字节」行 + 所有帧内行偏移整体 `+skip`）——**漏掉这步比解析失败更隐蔽**：高亮会落在错误字节（点「起始字符」高亮到第 0 字节）；③ **校验器**（先剥离再走全部检查，`skip > 0` 时追加 PASS 说明项，否则出现「解析成功但校验报起始符错误」）。
    - **协议6 的两处细节**：`check_structure` / `check_frame` / `calc_checksum` **都要**按剥离后的帧判定（否则 CS 把前导算进和里、`valid` 恒 False），且对已剥离输入幂等；`DLT645GuiParser.parse_to_table` 的 `frame_len` 必须用**剥离后**长度（否则「校验和 / 帧结束符」偏移越界）。协议6 的 `fields` 列表**不加**前导行（前导只在表格层）—— `test_dlt645_tolerant_parse.py` 的形状守卫依赖这一点。
    - **不要动的地方**：批量/Web 帧提取（`main_gui._extract_69845_frames` / `batch_core._extract_69845_frames` / `web_utils.extract_69845_frames`）本就从 `68H` 起同步扫描、天然跳过前导 —— **不要**给它们加前导处理。**串口工具的分帧层在 1.23.78 起改为认前导**（见陷阱 59 末条：68 家族先按 `wakeup_prefix` 跳过帧首连续 FE、返回值含前导），蓝牙工具仍按静默超时切帧（`BleReassembler`，未改）；**串口工具的「批量替换通信地址」层（1.23.83）同样剥/恢复前导**，且门控为 `FE_WAKEUP_PROTOCOLS = (6, 8)` —— 其余协议带前导必须报错（见陷阱 58 末条）。
    - **BLE 分包不可消除（顺带说明）**：ATT 层单包上限 = `MTU − 3`（协商 MTU=23 ⇒ 20 字节），**应用层无法一次写出 25 字节**；`bluetooth_worker._chunk_plan` 是尺寸与来源的唯一实现，分包时打一条含「单包上限 / 包数 / MTU 来源」的日志。**不要**为此改「包间延迟」默认值（改默认值需配置迁移，见陷阱 59）。
    - 回归：`test/test_wakeup_fe_prefix.py`（**73 项**，`CORE_TESTS`：报障帧 golden / 局部前缀 / 全 FE 与「FE 后非 68」降级 / 无 FE 零回归锚点（协议6 冻结 13 行基线）/ 协议6 解析 + 表格偏移 + 虚拟表从站 / 两校验器 / 逐协议护栏 / 批量与 Web 提取 / offscreen GUI（单帧页 + 串口·蓝牙共用回调）/ 反例自检 + 单一来源守卫）+ `test_bluetooth_worker.py`（分包日志断言）。
76. **698.45 A-XDR 三处口径：`bit-string` 长度域是「位数」、定长类型不带长度域、`time` = 3 字节（1.23.85 修正，改 `dl_t698_45_axdr.py` 前必读）**：
    - **`bit-string` 的长度域 = 位数**：规范里 bit-string 一律写成 `SIZE(8/16/32/64/128/3)`，都是**位**；实帧 `04 03 E0` = 3 位 + 1 字节数据。旧实现按**字节数**读 ⇒ 先吞 3 字节（`E0 0A 04`）再在 `0x76` 抛「未知类型(0x76)」——`0x76` 正是 `"v1.0"` 的 `v`。**后果**：`代理升级流程.docx` 的启动传输实帧在旧实现下 `APDU类型=失败`、整表 19 行全错位；按位读后 32 行全对。解码 `nbytes=(bits+7)//8`、编码 `len(value)*8`，严格互逆。
    - **通用编码器表达不了「1 字节 + 声明位宽 3」**：位宽是**字段声明**（`bit-string(SIZE(3))`），无法由字节数推导 ⇒ 该形态由调用方**硬编码** `bytes([0x04, 3]) + bytes([attr_byte])`（`dl_t698_45_upgrade.build_file_info` 即如此）。不要把这种形态硬塞进通用编码器（会与其「N 字节 = 8N 位」的互逆性冲突）。
    - **定长类型不带长度域**：`date_time` = tag + 10B、`date` = tag + 5B、`time` = tag + 3B、`date_time_s` = tag + 7B。依据：规范类型表（tag 25/26/27/28，`面向对象的用电信息数据交换协议(20210910).md`）+ §7.3.26/7.3.27 + **规范自带示例 `1C 07 E0 01 14 00 00 00` = 2016-01-20 00:00:00**（`07 E0` 是**年**，不是长度域；按长度域读得年 = 0xE001 = 57345 且 SIZE(7) 只剩 6 字节）。旧编码器多写一个长度字节 ⇒ 与自己的解码器不自洽。
    - **`_decode_time` 曾读 4 字节**（规范 `time ::= SEQUENCE{hour, minute, second}` = 3 字节）⇒ 已一并改为 3 字节。
    - **调用方必须收口**：`frame_gen_widget._encode_axdr_item` 与 `reflex_web/frame_gen_utils._encode_axdr_item` 的「原始字节类」分支原先**自行拼装**（bit-string 按字节数写长度、定长时间类型多写长度域）⇒ 已改为保留各自 `length` pad/truncate 后**委托 `coder.encode(raw, tag)`**。改这三处口径后**必须** grep 这两个调用方，别让它再手拼。
    - 回归：`test/test_dl698_upgrade.py`（A1/A3 逐字节 golden、A8 doc 实帧零错误行、A9 变异反证）+ 既有 698 套件（`test_dl_t698_45*.py` / `test_dlt698_preset.py` / `test_web_frame_gen_utils.py`）。
    - **不要按静态告警「清理」本文件的 `from typing import Dict, List, Optional`**：与 HEAD 逐字相同且未使用（F401），属既有状态。
77. **698.45 长流程串口页：`frame_received` 不可用，必须 `raw_data_received` + `frame_deframe`（1.23.85 起，改升级页/串口分帧前必读）**：
    - **`SerialWorker.frame_received` 对 698 是错的**：`serial_worker._process_buffer` 只认 DL/T645 双 68H 与 FT1.2（`end_pos = pos + L`），而 698 整帧 = `L + 2` ⇒ `buf[end_pos-1]` 是 FCS[0] 而非 `0x16`，必然落到「找载荷里第一个 `0x16`」的**容错分支**被截断（600 字节载荷含 `0x16` 的概率 ≈ 90%）。⇒ 任何 698 的「逐包等确认」页面必须：订阅 `raw_data_received` → 自有缓冲 → `frame_deframe.frame_length_for("dlt698_45", buf)` 取长度、**末字节必须 `0x16`** 才切帧、`frame_incomplete` 为真则继续等。
    - **`frame_deframe.py` 是分帧族单一来源**（`L+2` / 末字节自证 / 前导 FEH 容忍 / HDLC 定界 / 645 / Wrapper + `STRATEGY_BY_PROTOCOL` / `END_CHAR_STRATEGIES` / `FE_WAKEUP_STRATEGIES`）；`serial_tool_widget` 只做**同名 re-export**（`frame_length_for` / `declared_frame_len` / `SerialToolWidget._declared_frame_len` / `_wakeup_base`…，既有 500+ 项测试锚点依赖这些名字）。**新增分帧判据只能加在 `frame_deframe`**（教训同陷阱 31/55/61）；`test_wakeup_fe_prefix.py` 的单一来源白名单已含 `frame_deframe.py` + `serial_tool_widget.py`。
    - **发送用 `write_raw`（静默）**，不要 `send_frame`（逐帧 emit `[发送]` 会刷屏）；但**页面自建 TX/RX 日志行**，且失败/超时/弹框必须外显（弹框与日志并存）。
    - **等待用「单发 QTimer + 标志位」**（照 `test_plan_widget` 范式），**不要**为逐包确认新建 QThread（也就无需 `thread_registry`）；PIID 每帧自增 `& 0x7F`；确认判定走 `dl_t698_45_upgrade.check_action_response`（APDU 类型 + OMD + DAR + 解析器 HCS/FCS 一起判），**不要**用字符串/字节比对。
    - **`crcmod` 是可选依赖**：`dl_t698_45_frame_gen` / `dl_t698_45_parser` / `dl_t698_45_upgrade` 顶层 import 它 ⇒ Qt 页必须**函数内惰性 import**，ImportError 给「协议8 需要 crcmod，请 pip install crcmod」提示（同陷阱 69 铁律）。
    - **分包算术单一来源** = `dl_t698_45_upgrade.UpgradePlan`（`total_bytes` / `block_size` / `num_blocks` / `last_block_bytes`）：页面不要再自己算 `ceil`。
    - **RX 重同步必须能丢弃「不可能成为帧头」的字节**（1.23.85 复核发现并修）：只跳过「首字节非 `68`/`FE`」不够 —— 一次线噪（如 `FE FE 99 …`、或长度域被噪声污染成「按长度到齐却非 `16H`」）会让缓冲头**永久卡住**，此后所有确认都收不到（一次噪声 = 整轮升级失败，缓冲要涨到 262144B 才清）。正确判据：**只有「当前既无半截帧在等、也切不出整帧」时才允许丢弃**，且丢多少由 `frame_deframe` 的判据决定（**不要**在页面里另写分帧算术）。
    - **传输进行中必须冻结会改变计划的输入**（同上）：换升级包 / 改 SA·块大小 / 点「清除」都要么拒绝（提示先「中止」）要么完整复位状态与按钮门控；否则轻则 `_on_ack` 里 `IndexError`（Qt 吞掉 → 状态机卡死），重则**静默改发另一个文件的数据**。
    - 回归：`test/test_dl698_upgrade_gui.py`（194 项，假串口；含重同步边界与传输中控件的反例段）+ `test/test_dl698_upgrade_tab_wiring.py`（29 项，真实 `MainWindow` 接线）+ `test_serial_proto_frame.py` / `test_serial_tool_widget.py` / `test_dl_t698_45_extract.py`（抽取后行为不变）。

78. **Win11 任务栏「缩略图工具栏按钮」的三处硬坑（1.23.85 起，改 `system_integration/taskbar_buttons.py` 前必读）**：
    - **接口必须按 `ITaskbarList4 → 3 → 2` 的顺序试**：本机 Win11（`10.0.26300`）上 `CoCreateInstance`/`QI` 拿 `IID_ITaskbarList3` 直接返回 `E_NOINTERFACE(0x80004002)`，而 `ITaskbarList4` 正常（`HrInit`／`ThumbBarAddButtons`／`SetThumbnailTooltip` 全 `S_OK`，**按钮真的挂上了**）。只写 3 就会在这台机器上直接判「不可用」。三者对我们要用的方法**槽位相同**（`HrInit`=3、`ThumbBarAddButtons`=15、`ThumbBarUpdateButtons`=16、`ThumbBarSetImageList`=17、`SetThumbnailTooltip`=19），别按名字重排。
    - **涉及 `HANDLE` 的 Win32 调用必须显式 `argtypes`**：64 位下不声明时 ctypes 按 C int 传 ⇒ `DeleteObject(hbm)` 抛 `OverflowError: int too long to convert`（`qimage_to_hicon` 实测）。同时 `QImage.constBits()` 返回 `memoryview`，`ctypes.memmove` 前要先 `.tobytes()`。
    - **`QAbstractNativeEventFilter.nativeEventFilter` 在 PySide6 返回单个 `bool`**（True = 吞掉消息）；返回 `(bool, int)` 元组会被当 truthy ⇒ **把所有 WM_COMMAND 都吞掉**（Qt 那一套 tuple 是 PyQt 的约定）。
    - **能力边界（别向用户承诺过头）**：Win11 的任务栏对第三方封闭（Win10 的 deskband/自定义工具栏已移除），**任意控件（输入框）不可能放进任务栏那一行**；截图里那种「封面+标题+播放键」是 **SMTC 系统媒体卡片**（媒体会话专属）。受支持的挂载点只有：托盘菜单内嵌控件、**缩略图工具栏按钮**（悬停预览里，本陷阱这套）、屏幕边缘 AppBar 常驻条。另外按钮只在窗口**有任务栏按钮**时可见（`hide()` 到托盘后没有）⇒ 依赖它就得先谈「关到托盘」还是「最小化到托盘」。
    - 回归：`test/test_tray_taskbar_entries.py`（27 项，offscreen：托盘提交/清空/禁用、HICON、降级、合成 `WM_COMMAND` 命中与不误吞、`_parse_text_input` 两条路径、4 个按钮分派）+ 真机冒烟（`_setup_taskbar_buttons()`→True、按钮 id `0x7700..0x7703`、`PostMessage` 触发 `clicked`）。

79. **运行中热切换串口波特率：三条顺序铁律 + 一条状态诚实性规则（1.23.86 起，改 `serial_worker.set_baudrate` / 升级页波特率逻辑前必读）**：
    - **设备先行，主机后切**：设备只认「先收到那条提升波特率的命令、再切自己的 UART」。主机先切就连命令都发不出去（`_on_boost_ready` 与 `_send_boost_command` 的顺序不可换）；命令**只发不等确认**（切速瞬间主机还在旧速率，等确认只会白等一个超时）。
    - **`flush()` 必须排在改 `baudrate` 之前**：串口发送缓冲里可能还压着前半截帧，改了 DCB 之后那半截会按**新**速率发出去（现场表现为设备收到半截乱码）。顺序反了就是残帧。
    - **绝不用 `close_port` + `open_port` 换速率**：重开端口会丢设备侧会话状态（现场表现为掉线），项目既有测试也以源码守卫断言升级页里不出现 `open_port(`/`configure(`。串口开着时直接改 DCB 本身是安全的（pyserial 支持），**不关端口、不断读线程**。
    - **失败不许改 `_baudrate`**：`set_baudrate` 只在 `flush()` 与改速率**都成功**后才更新 `self._baudrate` 并发 `baudrate_changed`。否则 `_baudrate` 与实际速率说谎，而 `serial_tool_widget.serial_context_text` 是**直读** `_baudrate` 显示的 ⇒ 界面上写着 115200、实际还在 9600，现场查不出原因。同理 `_restore_baud` **只在真切成功时**才清「已提升」标记（失败保留标记，收尾还会再试），否则共享串口被永久留在 115200。
    - **切速状态是「临时」的**：`main_gui._on_serial_baudrate_changed` 同步顶栏回显但**刻意不落盘**（不调 `_save_serial_config`）—— 升级热切换不是用户下次启动要的默认值。
    - 回归：`test/test_serial_worker_set_baudrate.py`（49 项：顺序账本断言 `flush` 先于改速率、共写锁、不关端口、非法参数/底层失败不动 `_baudrate`）+ `test/test_dl698_upgrade_gui.py` [25]/[26]。

80. **升级前/后版本比对判定：变了=成功、一致=失败，但「没证据」不许下结论（1.23.86 起，改 `dlt698_upgrade_widget` 判定逻辑前必读）**：
    - **判定口径由现场定死**：升级前后读到的版本信息**有差异 ⇒ 判定升级成功**；**完全一致 ⇒ 判定升级失败**（设备没换新固件）。判定**只做差异比较、不挑字段**——软件版本号没变但日期变了同样是「变了」（现场设备固件常只动日期）。
    - **判等必须优先比原始字节**（`_compare_version_entries`）：`值` 是给人看的格式化结果（日期补全为 `20YY-MM-DD`、长值被 `_clip` 裁剪），拿 `值` 判等会把**同一个版本**误判成变了。两侧原始都缺时才退化为比 `值`；只在一边出现的字段算变化。
    - **`⚠` 诊断行不参与比对**：`version_rows` 在长度与表191 声明不符时会追加 `⚠ 长度未自证` 行，那是解析器对帧形状的告警、不是版本字段。把它算进去等于让告警行决定升级成败（`VERDICT_SKIP_ROW_PREFIX`）。
    - **没有证据就不下结论（诚实性规则）**：缺升级前基线（没勾「升级前读版本信息」）、有一侧没读到、**前后读的不是同一项版本内容**（`target` 不同）⇒ 一律 `VERDICT_UNKNOWN`「无法判定」；两侧都没读 ⇒ `VERDICT_PENDING`「尚未比对」。**任何展示都不得把 pending/unknown 说成成功或失败**——现场据此判断要不要重刷固件，猜错比不说更糟。
    - **判定不改状态机**：流程照常收尾 `done` / 进度 100%（**流程跑完 ≠ 固件升级成功**），结论只在三处外显：判定条（`_render_version_verdict`，配色走 `LOG_PALETTES` 随主题）、收尾状态行（`_set_status` 仅在 `STATE_DONE` 且结论明确时追加「判定：升级成功/失败」）、日志（`_log_verdict`）。
    - **日志不许复述字段值**：`pending` 只写结论行、不写明细。待比对时把升级前字段值再抄一遍会与「帧下一行的读版本明细」重复刷屏，且会破坏既有断言「`厂商代码`+`JCDZ` 的日志行恰好 2 行」（`test_dl698_upgrade_gui.py` [17]）。
    - 回归：`test/test_dl698_upgrade_gui.py` [27]（纯比对口径 + 相同/变化/缺基线/读不到/口径不一致/主题换色 六类场景）。
81. **协议9/10「原有扩展命令」（表61）的跨字节字段一律「字节号小的端为低位」，且测试模式 6 与 8 语义不同（1.23.87 起，改 `csg_new_gen_cmd_payloads._parse_legacy_ext_cmd` / `gw_new_gen_cmd_payloads._parse_comm_test_ext` 前必读）**：
    - **12bit「转发数据长度/模式持续时间/频段值/ToneMask值/无线信道号/MCS值」= 字节2 bit4-7（低 4 位）| 字节3 << 4（高 8 位）**——与协议11 `hdc10_parser.config_val`、协议10 `gw_new_gen_cmd_payloads` 同口径（即「字节号小的端为低位」，同陷阱 54 的 LSB-first）。旧协议9 按大端拼（`(b2>>4)<<8 | b3`）会把用户帧 `20 00` 读成 512（应为 2）、把「30 分钟」读成 3585。
    - **报文头长度是 6bit**：字节0 bit6-7 为低 2 位 + 字节1 bit0-3 为高 4 位（表61 跨两行）。只取字节0 的 2bit 会把 `81 61…` 报成「2」（正确 6 = 整根 6 字节报文头）。
    - **测试模式 6 ≠ 8**：模式 6 = **频段切换（载波切频）**，配置值 = 目标**频段值**（0/1/2 → 通信频段 0/1/2 及 MHz 范围）；模式 8 = **无线信道切换**，才是 Option（字节2 bit4-7）+ 信道号（字节3）。两者不可合并解析——历史上一次「与模式8 一致」的改动让载波切频帧显示成一堆无线信道号（用户 2026-10-19 报障）。频段映射单源在各 payload 模块的 `_BAND_MAP`。
    - 回归：`test/test_csg_summary.py::test_legacy_mode6_band_switch_is_carrier_semantics`（用户真实帧：模式6→频段值2/报文头长度6/无无线信道字段 + 模式8 仍为无线信道口径 的反例对拍）、`test/test_gw_ext_cmd.py` T3/T13/T14。
82. **自动升级默认查 GitHub Release，仓库地址只有一个来源，更新说明必须渲染出来（1.23.87 起，改 `auto_updater.py` / `update_dialogs.py` / 更新设置前必读）**：
    - **默认源 = GitHub**：`DEFAULT_UPDATE_CONFIG.source_type = "github"`，接口 `api.github.com/repos/{owner}/{repo}/releases/latest`（列表 `?per_page=30`），未鉴权 60 次/小时足够（启动一次 + 每 30 分钟一次）。**不要**把默认改回 `gitee` 或把 owner/repo 再写死一份 —— owner/repo 由 `merge_update_config(..., repo_url=AUTHOR_GITHUB_URL)` 从「关于」那个常量解析注入（`parse_github_repo_url` 容忍 `/releases/...`、`.git`、查询串），用户显式配置优先、**空串视为未设置**（设置对话框清空 = 回默认，否则会拿空 owner 去请求、报错原因还看不出是配置问题）。
    - **更新说明是 Release `body`（markdown）**：版本列表对话框（左列表 + 右说明）与「发现新版本」确认框都用 `QTextBrowser.setMarkdown` 渲染（链接可点）；空说明给「（该版本未填写更新说明）」占位，**不许静默留白**；`summarize_notes()` 只用于状态栏/tooltip 的一行摘要（剥 `#`/`**`/表格竖线），**不要**拿它替换对话框里的完整说明。
    - **GitHub 资产的 `digest`（`sha256:…`）就是校验值**：`_digest_to_sha256` 只认 sha256 且必须是 64 位十六进制，顶层 `sha256`（私有 version.json）优先。此前 GitHub 源永远取不到 sha256 ⇒ 勾了「校验 SHA-256」其实没校验。
    - **失败一律给中文人话**（`describe_http_status`：404=地址不存在或还没发 Release、401=非公开仓库、403/429=频率限制、5xx=服务器错误），`_http_get_text` / `_download_to_stream` 里 `HTTPError` **必须**先于 `URLError` 捕获（前者是后者子类）。
    - **源码压缩包不是安装包**：资产名命中 `source code`/`source.zip`/`src.zip`/`源码` 一律排除，避免把源码包当 exe 下下来替换自身；版本列表里**草稿（draft）略过**、无安装包资产的版本不进列表（列表里禁用下载按钮而不是点了报错）。
    - **【阻塞级·必读】发布对象的顶层 `url` 是 API 端点，不是下载地址**：GitHub/Gitee release 对象的 `url` = `api.github.com/repos/{o}/{r}/releases/{id}`。历史上（含 1.23.87 发布前）旧逻辑在「资产没匹配到 exe」时回落到顶层 `url` ⇒ 实测仓库里「有 Release 但没传安装包」的旧版本 `1.8.2` 被列进版本列表，点下载拿到的是**接口 JSON**，再被当作新 exe 覆盖自身。现行规则：**发布对象（含 `assets`/`tag_name`/`html_url`）只认资产直链**；顶层 `url`/`download_url` 仅供私有 version.json（非发布对象）使用；任何路径命中 `api.github.com/repos/` 或 `gitee.com/api/v5/repos/` 一律拒绝；无资产即抛「没有可下载的安装包资产」。回归：`test_auto_updater.py::test_extract_release_never_uses_api_endpoint_as_download_url`。
    - **替换 exe 前必须有 PE 兜底**（`is_pe_executable`：`MZ` 魔数 + `MIN_PE_BYTES`）：更新源写错 / 拿到 HTML 错误页 / 接口 JSON 时，SHA-256 往往也没配（无预期值即视为通过），只有这道闸能拦住「把 exe 覆盖成垃圾」。**不要**因为「有 sha256 校验了」就删掉它 —— 校验通过的前提是更新源给的就是正确摘要。
    - **`sha256_verify` 必须真的接进下载线程**（`_UpdateDownloadWorker(verify_sha=...)`）：它曾在全仓库里只有设置对话框读写、实际是否校验只看「摘要有没拿到」⇒ 勾不勾一样（死开关）。改这块时保持「关掉=不校验、打开=摘要不匹配即拒绝」三态可测。
    - **保存时把等于默认值的 owner/repo 收敛成空串**（`github_fields_for_save`）：否则用户点过一次「更新设置→确定」就把默认值落盘，显式配置优先会让**此后再改 `AUTHOR_GITHUB_URL` 失效**；`DEFAULT_GITHUB_OWNER/REPO` 与 `AUTHOR_GITHUB_URL` 两处硬编码的一致性由 `test_update_notes_gui.py::test_repo_url_single_source_no_drift` 看守。
    - **临时文件名必须过 `safe_file_stem()`**：tag 含 `/`（`release/1.24`）会把临时文件写成子目录、`: * ?` 等字符在 Windows 非法 ⇒ 表现为一句「下载失败」，现场查不出原因。
    - 回归：`test/test_auto_updater.py`（40 项）、`test/test_update_notes_gui.py`（54 项 offscreen，含接线源码守卫、下载线程 PE 三态与 sha256 开关三态 —— 防被改回内联 `QMessageBox` 拼原始 markdown / 防删掉 PE 闸或把开关改回死代码）。

83. **「提交问题到 GitHub」：两条通道、令牌不入包、字段 id 与仓库模板逐字绑定（1.23.94 起，改 `github_issue.py` / `github_issue_dialog.py` 前必读）**：
    - **两条通道，语义不同**：① **API 直连** = `POST /repos/{owner}/{repo}/issues`，**真自动**（issue 立刻出现在仓库里，不需要碰浏览器），前提是令牌对该仓库有 **Issues: write**（细粒度 PAT）或 `repo`（经典 PAT）权限；② **浏览器预填** = `issues/new?template=bug.yml&<字段 id>=…`，**不需要任何令牌**，用户在网页点一次提交。**不要**把浏览器兜底当成 API 的等价替代（前者用户还要点一次），也**不要**在无令牌时静默失败 —— 明确提示改用浏览器通道。
    - **令牌绝不能进 exe / 源码 / 日志**：只从「环境变量 `GITHUB_TOKEN` / `GH_TOKEN`」或「本机 config.json 的 `github_issue.token`」读，优先级 **显式 > 环境变量 > config.json**。理由：exe 是公开分发的，嵌了令牌 = 任何拿到 exe 的人都能替你在仓库里刷 issue。config.json 里的令牌会被 `diagnostics.redact` 自动脱敏（键名含 `token`），诊断包不会泄露。**开发机上环境里可能真的存在 `GH_TOKEN`** —— 写测试时必须先把这两个变量摘掉再断言优先级，否则会被真实令牌干扰（实测踩过）。
    - **字段 id 与仓库 yml 强绑定**：浏览器兜底靠 GitHub 按 **Issue Form 的字段 id** 预填，`FORM_PROTOCOL_OPTIONS` 抄的是 `.github/ISSUE_TEMPLATE/bug.yml` 里 protocol 下拉的**逐字**选项文本（GitHub 下拉要求与选项**完全一致**才会选中 —— 多一个空格、少「双模互联互通」都不生效）。`test/test_github_issue.py::test_form_protocol_options_match_bug_yml` 拿仓库里的真实 yml 对拍，**改了模板必须同步改代码**（反之亦然），否则直接变红。
    - **API 建单不经过 YAML 表单**：正文段标题刻意写成 `### 工具版本` / `### 期望结果` 等**与表单 label 一致**的 Markdown，让 issue 页面看起来与网页表单提交的没差别；空段不占位。
    - **标签可有可无**：仓库里没有的标签会让 GitHub 直接 422 ⇒ `submit_issue` 捕获后**自动去掉 labels 重试一次**（不能因为一个标签建不出 issue）。
    - **崩溃提交要脱敏本机路径**：`crash_handler` 的报告含「可执行文件 / 工作目录」两行（`C:\Users\<用户名>\…`），提交到**公开仓库**前必须抹掉（`sanitize_crash_summary`），否则泄露提交者的 Windows 用户名。运行环境摘要同理**不含**用户名 / 机器名。
    - **崩溃时 MainWindow 可能还没建好**：崩溃提交入口是**模块级** `_report_crash_to_github`（`main_gui.py`），不是 `MainWindow` 方法；两条入口（菜单 / 崩溃）必须共用同一份仓库地址与令牌来源，否则会出现「一个能提交一个不能」的分裂。
    - 回归：`test/test_github_issue.py`（32 项，含与仓库 yml 逐字对拍 ×3、API 错误码中文翻译、422 去标签重试、令牌优先级与脱敏、崩溃摘要脱敏、offscreen 对话框与接线守卫），已进 `release_check.py:CORE_TESTS`。

84. **自动升级下载：多线程分段可以，但「并发写同一句柄」会把文件写错；下载面板必须非模态（1.23.95 起，改 `downloader.py` / `update_download_dialog.py` 前必读）**：
    - **【阻塞级·必读】每个线程必须用自己的文件句柄**：`seek()` + `write()` **不是原子操作**。多线程共用一个 `handle` 写不同区间时，线程之间会互相踩掉文件偏移 —— 实测表现为「**第一次下载就与源文件字节不一致**」，且第一个错位点在 64 KB（`READ_BLOCK`）边界；而「第二次下载又对了」，极易被误判为偶发网络问题。正确做法：每个线程 `open(part_path, "r+b")` 独立 fd，各自 seek 到自己那一段。回归：`test_downloader.py::test_multithreaded_download_matches_source`（本地 HTTP 端到端逐字节对拍）。
    - **只写 `.part`，全部段完成并合并后才 `os.replace` 到目标路径**：自动升级会拿目标文件覆盖正在运行的 exe，**半截文件是破坏性的**。合并时逐段核对长度，少一个字节直接失败。取消时 `cleanup_partial()` 把 `.part` / `.progress.json` 一起删掉。
    - **暂停 = 复用续传，不是新机制**：`DownloadControl.pause()` 让各线程在**块边界**（64 KB）抛内部 `_SegmentPaused` 停下（已写字节保留），`download_multithreaded` **正常返回**；worker 看 `control.paused` 决定「发 paused 信号并等待」，`resume()` 后**再调一轮** `download_multithreaded(resume=True)`，只补未完成的段。**取消要能穿透暂停**（`cancel()` 会清掉 pause 事件），否则线程卡在暂停等待里退不出来。
    - **进度必须按字节上报，不能按段完成**：段很大时（100 MB / 16 线程 ≈ 6.5 MB 一段）「段完成才报」会让进度条长时间不动，看起来像卡死。现每写满一个 64 KB 块回调一次，节流 0.15 s。
    - **面板必须 `NonModal`**：此前是 `QProgressDialog` + `WindowModal`，下载时整个程序不能操作（用户现场口径）。现在 `show()` 而非 `exec()`，并提供「后台运行」收起面板、进度留在状态栏。回归：`test_update_download_dialog.py::test_dialog_is_non_modal` 与 `test_main_gui_uses_non_modal_panel`（后者断言**源码里不得残留 `QProgressDialog`**，防止被改回去）。
    - **服务端不认 Range 就老实单流**：`probe_size` 只认 `206`（`Range: bytes=0-0` 探测）。返回 200 时 `supports_range=False` ⇒ 走 `_download_single_stream`，不因为「并发不了」就下载失败。
    - **段布局变化必须让旧进度作废**：`.progress.json` 记录每段 `(start, end)` 与 `etag`/`total`；线程数变了导致段边界变了而 done 计数还按老布局走 ⇒ 拼出来的文件字节错位。对不上就整份作废、从头下。
    - **【1.23.96 起追加】四条不可回退的约定**：① **每段响应必须自证** `Content-Range`（起始偏移 == 请求起点、总长 == 计划总长）；不认 Range 的源回 200 时**判为不可分段并回落单流**，绝不按段偏移写整文件 —— 那会产出「大小对、内容错」的 exe，PE 与 SHA 都拦不住（摘要对得上是因为文件本身就是错的内容，只有体积恰好相同才危险；实测服务端/代理忽略 Range 是真实场景）。② **暂停等待必须是事件阻塞**（`DownloadControl.wait_resumed()`），不许 `sleep` 轮询 —— 轮询让「继续」平均晚 50 ms 生效，且退出时更难点干净。③ **退出时取消但保留分片**（`qt.on_cancel = "keep"` 后再 `cancel()`）：默认 `clean` 会把几百 MB 的 `.part` 删掉，等于每次关程序白下。④ **同一时刻只允许一个下载任务**：`_start_download` 有 `isRunning()` 重入守卫，两个 worker 抢同一个 `.part` 会拼出坏文件；重复触发只把面板叫回前台。回归：`test_downloader.py`（42 项，含 `test_cancel_keep_leaves_resumable_part` / `test_segment_response_self_check`），与 `test_update_download_dialog.py` 的 `test_start_download_refuses_second_task` / `test_download_panel_reopen_from_menu` / `test_download_done_clears_statusbar`）。
    - 回归：`test/test_downloader.py`（42 项，含暂停/继续/取消的**端到端**验证、失败时目标文件不出现）、`test/test_update_download_dialog.py`（26 项 offscreen）。

85. **协议2（HDLC/国网DLMS）：A-XDR 类型表、BER 起点、批量 7E 切帧三个坑（1.23.98 起，改 `hdlc_parser.py` / `_extract_hdlc_frames` 前必读）**：
    - **【阻塞级】A-XDR 数据类型表不能凭感觉编号**：真实帧里 `09 0C 07D2 0C 04 03 0A 06 0B FF 0078 00` 是 **octet-string(0x09) + 长度 12 的 date_time**（→ 2002-12-04 10:06:11 星期三），`10 00 78` 是 long(0x10)=120，`11 00` 是 unsigned(0x11)=0，`03 00` 是 boolean(0x03)。旧表整体错位一格（0x02 当 Boolean、0x09 当 Visible-String、0x10 当 Compact-Array）⇒ date-time 输出乱码、int16 解析不出来、uint8 越界读 8 字节。正确表见 `_parse_dlms_value` 的 `TYPE_NAMES`（IEC 62056-6-2：00 null / 01 array / 02 structure / 03 boolean / 04 bit-string / 05 double-long / 06 double-long-unsigned / 09 octet-string / 0A visible-string / 0C utf8 / 0D bcd / 0F integer / 10 long / 11 unsigned / 12 long-unsigned / 13 compact-array / 14 long64 / 15 long64-unsigned / 16 enum / 17 float32 / 18 float64 / 19 date-time / 1A date / 1B time）。
    - **12 字节 octet-string ≠ 一定是 date-time**：全 FF（`FF4F19F3…`）要按普通 OCTET STRING 展示；用 `_looks_like_dlms_datetime`（年份 1970~2200、月/日/时分秒范围）判别，事件通知(0xC2) 的可选日期字段同理。
    - **AARQ/AARE 的 BER 必须从 APDU tag(0x60/0x61) 开始解析**：`_parse_apdu_content` 收到的是「tag 之后」的数据，直接把 remaining 丢给 `_parse_ber_tlv` 会把长度字节当 tag，整棵树错位一层（OID 碎成「BER 标签/长度」）。另外 BER 只对 constructed 递归，OCTET STRING/OID 这类 primitive 一律不递归。
    - **BER-TLV 判定不要「长度≥2 就 True」**：未识别 APDU（0xC2/0x0F/0xD8/0xD9/0xDA）会被当 BER 树拆碎；`_looks_like_ber_tlv` 只认 0x60/0x61 且长度自洽。这些 APDU 已在 `APDU_TYPES` + `_parse_apdu_content` 里独立解析（事件通知 = 4B invoke + 12B date-time + 9B 描述符 + 数据；数据通知 = 4B invoke + 通知体；异常响应 = state/service error）。**0xE6/0xE7 是 LLC 地址字节，不是 APDU tag**。
    - **批量切帧必须按字节找 0x7E**：`_extract_hdlc_frames` 曾在 hex **字符串**里 `find("7E")`，把 `67 E6` 中间的字符当成帧边界 —— 实测一条 32 字节响应被切成 8+24 两条残帧（批量摘要显示「异常 / non-hexadecimal number」）。改为 `bytes.fromhex` 后 `data.find(0x7E)`，并支持相邻帧共用一个 7E（结束标志即下一帧起始）。
    - **4 字节服务器地址给 DLMS 语义**：`00 02 00 23` 的 HDLC 7 位拼接值是 0x02200080（对现场无意义），应显示「逻辑设备 0x0001 / 逻辑块 0x0011」（每字节取高 7 位、2 字节组内大端）；2 字节整体是服务器地址（`02 47` → 0x1181）。
    - **APDU 标签 / Invoke-Id 位序 / 结果码枚举必须按 Green Book 9.4.1（1.23.99 起）**：① APDU 标签不是 1~4（0x01=InitiateRequest），**RLRQ/RLRE = 0x62/0x63**、0x0C=ReadResponse、0x0D=WriteResponse、0x0E=ConfirmedServiceError、0x10=DataNotificationConfirm、0x16=UnconfirmedWrite、0x18=InformationReport；② `Invoke-Id-And-Priority` 是「低 4 位 invoke-id、bit6 service-class（0=Unconfirmed/1=Confirmed）、bit7 priority（0=Normal/1=High）」——`0xC1` = ID1/Confirmed/High；③ `DataAccessResult` / `Action-Result` 是**稀疏枚举**（0,1,2,3,4,9,11,12,13,14,15,16,17,18,19,250），不能按 0~N 连续编号；ExceptionResponse 的 state-error 只有 1/2，service-error 是 CHOICE 1~6（6 后跟 4 字节计数器）。回归：`test_hdlc_corpus.py` 的 invoke 位序、枚举、RLRQ/RLRE、with-list 用例。
    - **解析输出一律「中文在前、英文原名括注」（1.23.99 续做，国内现场口径）**：面向用户的「解析值 / 说明」两列不要再写纯英文枚举。已统一的范围与写法：SNRM/UA 协商参数「发送最大信息域长度（Max Info Field Length - Transmit）」；Get/Set/Action 子类型「数据块响应（With-data-block）」；DataAccessResult / Action-Result / Exception「读写被拒绝（read-write-denied）」「服务不允许（service-not-allowed）」；A-XDR 类型说明「16 位有符号整数（long），共 3 字节」（旧写「long（3 字节）」既英文又会让人误读成类型长度）；BER 标签「上下文 [30] 用户信息（user-information）」「通用（Universal） 字节串（OCTET STRING）」；Invoke-Id「不需确认（Unconfirmed）」「高优先级（High）」；特殊地址「无站地址（NO_STATION）」。**APDU 名称例外，保留英文在前**（AARQ / Get-Request 是国内现场通用叫法）。**COSEM 类名只保留一份**：类常量 `COSEM_CLASS_NAMES`，`_parse_cosem_descriptor` 与 Action 分支都查它 —— 曾经两处各有一张表，Action 分支那份是纯英文 `Clock`，同一类在不同 APDU 下显示不一致。
    - **帧长必须自证（`_check_declared_length`）**：格式域声明的帧长 = 首尾 7E 之间的字节数（完整帧整帧 = 帧长 + 2，半包 = 帧长 + 1）。串口半包 / 抓包截断 / 多帧粘包时表格出「警告」行、`parse()` 的「格式域」多一个「帧长校验」文字，但**解析状态不改成失败**（已有字段照常展示，容错优先）。曾把 12 字节残帧判为「解析成功」而毫无提示。
    - 回归：`test/test_hdlc_corpus.py`（**39 项**：27 条真实帧 + 构造帧 + 文档笔误帧 + 共享 7E 切帧 + with-list/RLRQ + DLMS 摘要 + **中文化守卫 5 项**（枚举表必须含中文且英文用全角括号括注，新增纯英文枚举会变红）+ **帧长自证 2 项** + Action 请求/应答 + glo-*/Confirmed-Service-Error 兜底 + Access 请求应答 + 坏输入容错），已进 `CORE_TESTS`。

86. **主题一致性：懒加载页 + 独立弹层是深色主题的两个白底雷区（1.23.99 起，改 `main_gui` 懒加载或 `theme_settings` QSS 前必读）**：
    - **懒加载页创建时不会自动跟随主题**：带 `restyle_for_theme(dark)` 的页面（`Dlt698UpgradeWidget` / `Dlt698TestWidget` / `BluetoothToolWidget` / `ProductionTestbenchWidget` / `FrameDiffWidget` / `SpectrumWidget`）内部 `_dark` 初值都是 `False`；只在「主题切换」回调里刷新是不够的 —— 「先选深色主题、再首次打开该页」必然白底。**新建这类页要在 `_ensure_*_tab()` 里创建后立刻 `tab.restyle_for_theme(self._is_dark_theme())`**（`_ensure_upgrade_tab` / `_ensure_test_tab` / `_ensure_bluetooth_tool_tab` 曾三处漏掉，已补；`_ensure_testbench_tab` 是正确样板）。
    - **QCompleter 的 popup 是独立顶层 `QListView`**，不是 QComboBox 的后代，`QComboBox QAbstractItemView` 选不中它；四套 QSS 现已各有一条独立 `QListView` 规则，**不要再在页面里 `.completer().popup().setStyleSheet(...)` 写死白底**（`frame_gen_widget.py` 原有 5 处已删）。
    - **`QMessageBox` / `QMenu` 不要写局部 `background-color`**：局部样式盖掉全局 QSS 的深色规则（拓扑页节点详情弹窗、`gui_utils.setup_chinese_context_menu` 的文本框右键菜单都踩过；只留字号这类与颜色无关的属性）。
    - **验证手法**：AX 树与 `get_app_state` 看不到颜色，用 `widget.grab()` 取四角像素算亮度（>170 判亮底、<90 判暗底），逐 tab 扫（`setCurrentIndex` 会触发懒加载）+ 深色 / 浅色 / 深浅往返三轮。

87. **串口工具的「通道」复用蓝牙（1.23.99 起，改 `serial_tool_widget` / `bluetooth_worker` 前必读）**：
    - 蓝牙连接**只**在「蓝牙工具」页建立；串口工具页经 `set_bluetooth_provider` 注入取值回调（main_gui 传 `_upgrade_bluetooth_source`，与「光伏升级」页**共用同一注入点**）。本页不建/不断连接，切到蓝牙时惰性重取 worker（蓝牙页可能才刚连上）。
    - **发送复用 `SerialSendWorker`**：它只认 ``write_raw(bytes) -> bool``，蓝牙差异由 `BluetoothWriteAdapter` 吸收（转 `send_data`）。不要再为蓝牙另写一套发送线程 —— 发送节奏 / 序号回指 / 失败处理必然漂移。
    - **接收用 `frame_received`**（BLE 通知重组后的整帧），不要用 `notification_received`（分包），否则断帧与响应匹配会把一帧拆成多次。
    - **两个通道的字节绝不混用**：`_on_serial_raw` 与 `_on_bt_frame` 都先判当前通道，非当前通道直接丢；否则串口与蓝牙同时在收时会串台（日志与匹配统计全乱）。
    - `_refresh_channel_ui` **不得**调用 `_channel_ready()`：后者会惰性重取 worker 再回调刷新，形成递归。界面刷新用已绑定的 worker 直接判定，懒重取只在 `_channel_ready` / `_send_target` 里做。
    - 回归：`test/test_serial_tool_channel.py`（25 项：默认通道 / 未连接禁用 / 已连接可用 / 写入口转调 / 通道隔离双向 / 持久化与非法值回落），已进 `CORE_TESTS`。

88. **南网光伏无线模组接口（V1.6）扩展：四条容易踩错的解析细节（1.23.99 起，改 `dlt645_pv_wireless.py` / `dlt645_parser.py` 前必读）**：
    - **超时字段 T 是 BCD，不是整数**：`02EB0000` 数据转发里 `T=0x10` 表示 **10**（1000ms）；按整数读会得到 16 → 1600ms。手册 §3.1 明写「超时字段T（BCD 码）」，§4.4.4 示例即 `0x10` ↔ 正文「T=10，即 1000ms」（本仓首版即踩过，已按 BCD 修正并加断言 `"1600" not in` 守卫）。
    - **无线信道是 2 字节 BCD、低字节在前**：线上 `00 32` → 32，不是按小端整数读成 50（v1.3 修订点，§4.4.2 有实测帧）。
    - **`04E60001` 两份规范冲突**：附件1（§D.1）的「长度列 16 / 12 路地址」无法自洽切分；无线手册（V1.6）给 `1 + 6×M` 且 §4.4.3 实测报文自证（5 台 → 31 字节）⇒ `dlt645_pv_wireless` **优先接管**该 DI，附件1 的歧义切分只在 pv 模块层保留（`test_dlt645_pv_ext.py` 改为直接调 `pv.parse_pv_di` 锁契约，不要再从 parser 断言）。
    - **控制码 `06H/86H`、`1EH/9EH` 在标准 645 里不存在**：不能塞进通用 `FUNC_NAMES`（`06H` 与 `86H` 的 `0x1F` 都是 0x06、方向相反）⇒ 用 `control_extra()` 在命中扩展时**整段替换** `control_desc`，否则会显示「未知功能码06H」、甚至把 `1EH` 标成「主站请求」。同理 `D1H + ERR=0x80` 在本手册是「目标无线接口转换器未入网」。
    - 回归：`test/test_dlt645_pv_wireless.py`（**65 项**：6 条 §4.4 原文示例 + 升级类构造帧 + 普通 DI 反例 + 工具函数），已进 `CORE_TESTS`。

89. **状态栏连接指示 + 光伏升级页参数分组框：命名与空间预算两条硬约束（1.24.0 起）**：
    - **状态栏「串口 / 蓝牙」指示**（`main_gui._serial_conn_btn` / `_bt_conn_btn`，图标+中文，绿=已连接 / 灰=未连接）的状态**必须从 worker 实况读**，不要靠信号里那个 bool 自己记：串口读 `SerialWorker.is_connected()`（并订阅它的 `connection_changed` 刷新）——**`SerialWorker` 的权威方法是 `is_open()`，`is_connected()` 只是它的别名**（2026-10-26 现场报障：主窗口只调 `is_connected()`、AttributeError 又被 `except` 吞掉 ⇒ 状态栏永远显示「未连接」）；主窗口统一走 `MainWindow._worker_connected(worker)`（先 `is_connected` 再退回 `is_open`），测试必须用**只提供 `is_open` 的假串口**才能抓住这类回归（`test_statusbar_stats` ⑥/②b），蓝牙读 **`bluetooth_tool_tab.bluetooth_worker()`**（页面的访问器就叫 `bluetooth_worker()`，**没有 `worker()`** —— 写错会被 `_refresh_conn_indicators` 的 `except` 吞掉、指示永远灰）并订阅页面新增的 `BluetoothToolWidget.connection_state_changed`。蓝牙页是**懒加载**的：没创建过就是「未连接」，所以 `_refresh_conn_indicators` 里全是 `getattr` 兜底。
    - **染色只能走 `app_icons.render_pixmap(name, size, color)`**：`load_icon` 的引擎只跟随主题前景色，做不到「绿/灰按状态」；高 DPI 要先按 `devicePixelRatioF()` 放大 `size`、再 `pm.setDevicePixelRatio(dpr)`，否则 150% 缩放下发虚。切主题必须重刷（已挂在 `_restyle_for_theme`）。
    - **「光伏升级」页的空间预算是刻意留的，别当冗余删**：参数区 5 个分组框包在**滚动容器**里（`PARAMS_MIN_HEIGHT=132`）、日志有**最小高度**（`LOG_MIN_HEIGHT=132`）、版本信息两栏上限 **124**。删掉滚动容器或任一下限后，矮窗口（本项目最小 1000×700）下布局会把分组框压到只剩标题行（实测 27px、控件全被裁），日志被版本框挤到 56px。
    - 回归：`test/test_statusbar_stats.py` 的连接指示用例 + `test/test_dl698_upgrade_gui.py`（523 项）。

93. **QSS 的行内复选框必须用 `QAbstractItemView::indicator`（`QCheckBox::indicator` 管不到，1.24.1 修）**：
    - **现象**：树/表里的行内复选框（协议测试页命令树、串口工具命令表、归档页等）**未勾选时白底白框**，
      现场报「好多复选框看不清楚，边框没有颜色」；勾选后只有一个勾/色块，靠位置猜。
    - **根因**：4 套 QSS 只写了 `QCheckBox::indicator`（独立按钮式复选框），**item view 的行内指示器是
      另一个绘制路径**（`QStyle::PE_IndicatorViewItemCheck`），QSS 未覆盖时按调色板画；本项目的
      `background-color` 经 QSS 映射到调色板后，未选指示器的边框与行底色同色 ⇒ default 下实测全 `#ffffff`。
    - **修法**：每套 QSS 在 `QCheckBox::indicator:indeterminate` 之后追加
      `QAbstractItemView::indicator` / `:checked` / `:indeterminate` 三条（未选：灰框+底色；已选：强调色底；
      部分选：浅强调）。抄现有的 `QCheckBox::indicator` 配色即可，**不要**新增图标资源。
      实测该选择器同时覆盖 `QTreeView/QTreeWidget`、`QTableView/QTableWidget`、`QListView/QListWidget`。
    - **判据必须是渲染级**：静态断言（QSS 里有 `border:`）挡不住「白底白框」。`test_theme_settings.py` 1d 节
      的做法：`ThemeManager.apply` 后建一棵 `QTreeWidget`（`setRootIsDecorated(False)` 去掉分支箭头），
      在 `visualItemRect(...)` 左侧 24px 内统计「与行底色 WCAG 对比度 ≥ 3 的像素数 ≥ 20」，并含
      **反例自检**（把 indicator 规则整段删掉后该判据必须变红）。新增主题/改配色后跑它。
    - **附带口径**：原生主题（fusion / windows / windowsvista 主体）不写复选框样式，由系统绘制，
      测试按「该主题是否本来就有 `QCheckBox::indicator`」决定是否参与断言（`windowsvista` 有一段只修
      输入框的补充 QSS，不能用「qss 非空」当判据）。

92. **协议测试页的双通道（串口 / 蓝牙）三条硬约束（1.24.1 起，改 `channel_link.py` 或两页收发前必读）**：
    - **收发只能经 `ChannelController`**：页面直连 `raw_data_received` = 双份 RX；蓝牙通道又订阅
      `notification_received`，两路字节会混进同一个 `_rx_buf`，半帧跨通道拼接后**判定全错**。
      控制器按「当前通道」过滤后才 `rx.emit`；切通道必须清页面分帧缓冲（`channel_changed` → `_rx_buf.clear()`）。
      源码护栏（698 页 [16]）现断言「页面不出现 `raw_data_received.connect`」。
    - **蓝牙帧必须整帧一次 ATT 写，超限就报错**：`BluetoothWorker.send_data(single_write=True)`
      超限会拒绝；升级页那句「请调小每包字节数」对测试页是误导 ⇒ `ChannelController.send()`
      **先按 `single_write_limit()` 预检、不调用 worker**，直接给「一次 ATT 写上限 M 字节，该帧 N 字节」。
      **不要**改成自动分包（设备会收到被切断的 698/645 帧）。
    - **连接生命周期归「蓝牙工具」页**：页面只经 `set_bluetooth_provider(MainWindow._upgrade_bluetooth_source)`
      取 worker；`cleanup()` 只断信号、**不断开**连接；蓝牙页懒加载 ⇒ 先选蓝牙后连接是常态，
      必须 `showEvent` 里 `rebind_bluetooth()`（否则一直停在「未连接」）。
    - 回归：`test/test_channel_link.py`（49 项）+ 两页双通道段（698 [18] / 645 [4b]）+ 两个接线测试的注入断言。

91. **645 数据标识表的两处既有瑕疵，不要在解析/组帧层「顺手改表」（1.24.1 记录）**：
    - `dlt645_di.json` 合并 `dlt645_pv_ext` 后共 1781 键，其中 **16 条是 7 位残键**（`0090000`…`0090F00`，
      生成「第1象限无功费率 N」时少写一位）。它们与标准条目 `0090xxxx` **同名重复**，`encode_di` 只接受 8 位
      ⇒ 不能下发。645 测试页用 `dlt645_test_core.malformed_di_keys()` 显式暴露并**不进树**；
      若将来重生成 DI 表，测试会因「残键集合变化」先变红。
    - `04000101 日期` 在表里声明 `length=4`，而 DL/T645 与 `encode_value/decode_value` 是 **3 字节**（YY MM DD 低字节在前）。
      `length_warning` 会给出「声明 4 / 实际 3」提示，但**不阻断组帧**（与既有「长度不符仅提示」口径一致）。
      **不要**为了消掉提示去改表或改编码器 —— 那会让标准设备的帧变非法。
    - 645/其它页若需要「读某 DI」，一律用 `dlt645_test_core.build_read(di, addr)`（内部走唯一组帧器），
      不要手拼 `68 … 16`，也不要另存一份 DI 名称表。

90. **自绘画布与字符格式不会自动跟随主题（1.24.0 起，改任何 QGraphicsView / paintEvent / QTextCharFormat 前必读）**：
    - **谁需要自己跟**：QSS 只覆盖标准控件。「非 QSS」的三类地方必须自己按主题取色 —— ① `QGraphicsView` 的 viewport（`setStyleSheet("background-color: …")` 或 `setBackgroundBrush`）+ 场景里每个 item 的 `QPen`/`setDefaultTextColor`；② `paintEvent` 里 `fillRect` 的区域（行号槽、自绘网格）；③ `QTextCharFormat`（`setForeground`/`setBackground`，会**盖掉** QSS 给 QTextEdit 的配色）。
    - **配色单源 = `canvas_theme.py`**（`CANVAS_PALETTES[False/True]` + `palette(dark)`，纯字典、不 import Qt）。深色一套与日志面板 `#1E1E1E` 同族。**不要再在各个 wiget 里各写一份 `#FAFAFA`/`#333`/`#999`**：拓扑图曾写死 `#FAFAFA` 白底 + `#333` 深轮廓 ⇒ 深色主题下整页白底（实测亮底占比 **65.6%**）、节点轮廓与角色名几乎看不见。
    - **必须同时接三处**：① 组件自己的 `restyle_for_theme(dark)`（拓扑/字节视图/测试方案/原始日志快照/TCP 监控都已实现）；② 主窗口 `_restyle_for_theme` 里对**已创建**实例的调用；③ **懒加载页创建后立刻** `tab.restyle_for_theme(self._is_dark_theme())`（同陷阱 86：只挂回调，先选深色再首开该页就会留浅色）。
    - **验收手段**：`test_appearance_gui.py::test_dark_canvas_follows_theme` 做**全页像素扫描**（深色下每页亮底占比 < 5%，拓扑修复前 65.6%）+ 逐组件断言（视图底色、节点轮廓、角色名、字节视图字符背景、行号槽、勾选框与徽章）。改这类画布后先跑它，别只靠眼看。
    - **顺带清掉的一颗地雷**：`test/test_plan_widget.py` 原是**产品模块的过期副本**（2600 行、零断言、无 `__main__`），而 `test/` 常在 `sys.path` 前部 ⇒ 测试里 `import test_plan_widget` 拿到的是这份旧控件（主程序测试假绿）。已删除并换成 `test/test_test_plan_widget.py`（真实冒烟 + 「test/ 下不得有同名副本」守卫）。**新增/重命名测试文件时不要与产品模块同名**。

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

> 详细版本变更记录请查看 `main_gui.py:CHANGELOG`（按版本倒序），或运行 `git log --oneline` 查看提交历史。本文档保留近期版本的摘要。

### 1.23.96 — 2026-10-23

- **下载器四批次加固（R1~R17）**：① 分段收到 `HTTP 200` 不再按段偏移写入，判「该源不可分段」并回落单流；② 退出时 cancel 下载但**保留分片**（`on_cancel="keep"`），并等线程结束；③ 同一时刻只允许一个下载任务，重复触发把已有面板唤到前台；④ url 变化让 `progress.json` 整份作废；⑤ 每段自证 `Content-Range` 偏移与总长；⑥ 单流也支持续传、不支持时明示；⑦ `OSError(ENOSPC)` 翻成「磁盘空间不足：需要至少 X」；⑧ 关面板=后台继续 + 新菜单「配置 → 下载进度…」可叫回；⑨ 下载结束清空状态栏；⑩ 面板按钮走 `fit_btn_width` 且在 `FontChange` 后重算（14 号字下实测会裁）；⑪ 标题/状态列由 `progress.state` 驱动；⑫ `DEFAULT_MAX_THREADS`(16) 成为「自动」上限；⑬ 删 `http_probe` 死参数；⑭ 删 `_UpdateDownloadWorker.progress` 死信号；⑮ 取消默认保留进度 + 独立「清理缓存」；⑯ 取消立即返回；⑰ 识别 `429`/`Retry-After`（上限 10 s）。
- **暂停等待改事件阻塞**：`DownloadControl.wait_resumed()` 取代 `sleep(0.1)` 轮询。
- 测试：`test_downloader.py` **42 项**、`test_update_download_dialog.py` **26 项**（含**宿主级**重入守卫/菜单重开/状态栏清理），6 条变异反证逐条变红后还原。
- 顺带修两处测试假红：`test_menu_wiring.py` 打印 `✓` 在 GBK 控制台崩；`test_app_icon_path.py` 改查 `pyinstaller_meta.DATAS`（spec 已改为 `datas=list(meta.DATAS)`）。

### 1.23.95 — 2026-10-22

- **自动升级改多线程分段下载**：新增 `downloader.py`（Range 分段 + 线程池，上限 **32 线程** + 断点续传 + 暂停/取消；服务端不支持 Range 时自动回落单流）。只写 `.part`，全部段完成并合并后才落目标文件；SHA-256 与 PE 兜底不变。
- **下载面板重做**：新增 `update_download_dialog.py` —— **非模态**（下载时主程序可用）、逐线程进度表、实时速率 + 剩余时间、暂停/继续、取消并清理缓存、后台运行。替换掉原 `QProgressDialog`。
- **修掉一个真实并发缺陷**：多线程共用文件句柄导致 `seek/write` 互相踩偏移 ⇒ 下载字节错位（错位点在 64 KB 边界）；改为每线程独立句柄。实测发现，非理论推演。
- 「配置 → 更新设置」新增「下载线程」（自动 / 8 / 16 / 24 / 32），存 `update.download_threads`。
- 测试：`test_downloader.py`（30）+ `test_update_download_dialog.py`（14）。

### 1.23.94 — 2026-10-22

- **「提交问题到 GitHub」**：新增 `github_issue.py`（纯逻辑无 Qt）+ `github_issue_dialog.py`（PySide6）。帮助菜单「提交问题到 GitHub」与**崩溃弹窗「提交到 GitHub」**两个入口。**两条通道**：API 直连（`POST /repos/{owner}/{repo}/issues`，填令牌即可真自动建单）/ 浏览器预填（按 Issue Form 字段 id 预填，免令牌）。自动带入当前协议、最近解析报文 hex、运行环境（不含个人信息）；崩溃摘要提交前抹掉本机路径行。
- **令牌不入 exe**：来源优先级 显式 > `GITHUB_TOKEN`/`GH_TOKEN` 环境变量 > config.json 的 `github_issue.token`；config.json 内令牌被 `diagnostics.redact` 自动脱敏。owner/repo 由 `resolve_owner_repo(AUTHOR_GITHUB_URL)` 解析，与「关于」/自动升级源同源。
- **字段 id 与仓库 yml 绑定**：`FORM_PROTOCOL_OPTIONS` 与 `.github/ISSUE_TEMPLATE/bug.yml` 的 protocol 下拉逐字一致，测试直接对拍；仓库 `bug.yml` 增补 `contact` 字段。
- 测试：`test/test_github_issue.py`（32 项）；spec `hiddenimports` 增补两个新模块。

### 1.23.92 — 2026-10-21

- **单帧「校验该帧」开关**：`TOLERANT_PARSE_PROTOCOLS = {8}`；勾选走原严格路径，取消调用 `parse_to_table(frame, verify=False)`。`_sync_verify_frame_chk()` 在协议切换时置灰非协议8；状态存 `config.json: single_parse.verify`。
- **698 容错解析**：`parse(frame, verify=True)` / `parse_to_table(frame, verify=True)` 新增关键字参数（默认 True，零行为变化）。容错分支 `_parse_tolerant` + `_build_tolerant_table`：长度域只作参考（整帧 = L+2）、起始/HCS/FCS/结束符只标注、末尾是 0x16 才切 FCS、拆不动给「未解析字节」、**必定输出「原始报文」行**；APDU 异常时给「APDU解析错误 + APDU原始字节」。
- 测试：`test_dl698_tolerant_parse.py`（7）+ `test_tolerant_parse_gui.py`（12，GUI_TESTS）。

### 1.23.91 — 2026-10-20

- **外观模式（浅/深/跟随系统）与主题解耦**：`theme_settings.resolve_appearance(theme, mode, system_dark) -> (实际主题, 是否深色)`；`ThemeManager.apply(..., mode=, system_dark=)` 新增两个默认参数（向后兼容）。`PALETTE_DARK_THEMES = ("fusion","windows","windowsvista")`：深色时**保留主题 id**、换 `build_dark_palette()` 并叠加 `DARK_QSS`（只换调色板会出现"菜单黑了、页面还是白"的割裂）；`default/glass/mica` 深色时落 `dark` 主题。
- **主界面**：菜单栏右上角新增 `appearance_btn`（sun/moon/monitor），与顶栏折叠按钮同容器；`_cycle_appearance()` 三态循环（暗色主题 + 浅色模式点击自动回 default，否则"点了没反应"）；`_is_dark_theme()` 改为按 `resolve_appearance` 计算，所有 `restyle_for_theme(dark)` 自动跟随；`colorSchemeChanged` 仅 system 模式实时跟随。
- **配置**：`ui.appearance` 落盘（`ThemeManager.load_mode / to_config(..., mode=)`），旧配置缺键按 `theme == dark` 推断。
- 测试：`test_appearance_mode.py` 10 项 + `test_appearance_gui.py` 16 项（含"fusion 深色后 Window=#202225、切回恢复 #efefef"）。

### 1.23.90 — 2026-10-20

- **性能**：`topology_widget` 不再顶层导入 `TopologyGraph`，改为 `@property topo_graph` 按需创建 —— 首开 1586 ms → 13 ms（`networkx` 导入 ~0.97 s 不再压在开页上）；20 页全开 RSS 156 → 125 MB。**注意**：以后任何在 `topology_graph` 上加逻辑的改动，都不能把它改回顶层 import。
- **崩溃兜底**：新增 `crash_handler.py`（`install(app_version, build_date, base_dir, on_crash)`）：`sys.excepthook` + `threading.excepthook` → `<数据目录>/logs/crash_YYYYmmdd_HHMMSS_微秒_pid.log`，保留最近 20 份；`SystemExit` 忽略；写盘/回调异常全部吞掉；主线程才弹框（子线程只落盘）。`main()` 在 `QApplication` 之后、`MainWindow` 之前安装。
- **日志合并刷新**：`production_testbench_widget` 的 `_log` 入队 + 100 ms `_flush_log`（`LOG_FLUSH_MS` / `LOG_FLUSH_MAX=300` 立即刷）；清空丢弃队列、`cleanup()` 先刷后停。
- **状态写入原子化全覆盖**：`custom_di_store` / `dlt645_di_lookup` / `command_lookup` / `obis_lookup` / `preset_buttons` / `archive_widget` / `llm_api_manager` / `llm_preprocess_widget` / `frame_gen_widget` / `meter_sim_widget` 的 JSON 写入统一 `atomic_write_json`；`test_p0_hardening.STATE_WRITERS` 静态守卫（新增状态写入点必须加进清单）。
- **短时长稳**：`test/test_soak_stability.py`（GUI_TESTS）—— 切页 600 次 RSS 158→185→189→189（末段 0 增长）+ 5000 帧灌入 0.1 s、日志块 ≤ 上限、队列清空。
- **解析健壮性**：修 `gdw10376_parser` 截断帧越界（`cs_pos` 夹回 `frame_len-2`，取 AFN 前再判 `offset < frame_len`）。新增 `test/frames/<registry_key>/*.hex` 语料库 + `test/test_frame_corpus.py`、`test/test_parser_fuzz.py`（固定 seed、12 解析器、含全前缀截断与国网回归）、`test/test_crash_handler.py`；均进 CORE_TESTS。
- 配套：`APP_VERSION 1.23.90`；spec 增补 `crash_handler`；`--sync-iss`。

### 1.23.89 — 2026-10-20

- **P0 加固三项**（依据 `docs/产品级优化评估-2026-10-20.md`）：
  1. **配置原子写**：新增 `atomic_io.py`（纯标准库：同目录 tmp + flush/fsync + `os.replace`，Windows 占用重试 4 次；失败保留旧文件、清理 tmp）。`main_gui` 6 处 `open(config.json,"w")+json.dump` 全部换成 `atomic_write_json`。
  2. **升级失败可回滚**：`auto_updater.UPDATE_BAT_TEMPLATE` 重写为「等旧进程退出 → 备份 `.bak` → 覆盖 → 新旧文件大小比对 → 启动 → `ping -n 16` 15 秒健康检查 → 失败删新文件（重试 10 次）→ 还原 `.bak` 并重启」。备份移动失败（占用）时放弃升级、不动旧文件；成功后保留一份 `.bak`。
  3. **诊断包**：新增 `diagnostics.py`（无 Qt），从 `app_data_dir()` 收集 环境信息 + 5 个配置文件（递归脱敏 `api_key/token/password/secret/cookie/authorization` 等）+ `Output/` 最近 5 个日志尾部（单个 ≤200KB、总包 ≤5MB）；缺文件只跳过。入口：帮助 → 生成诊断包。
- 另修：`gui_utils._STANDARD_ICON_MAP` 补 `search` / `settings` 两键（归档/拓扑按钮原本静默无图标）。
- **回归**：新增 `test/test_p0_hardening.py` **13 项**（原子写 5 + 升级脚本 2 + 诊断包 4 + 主程序静态守卫 2），已进 `release_check.py` CORE_TESTS；`test_auto_updater.py` 40 项仍全绿。
- 配套：`APP_VERSION 1.23.88 → 1.23.89`、`BUILD_DATE 2026-10-20`、两个 `.iss` 已 `--sync-iss`；spec `hiddenimports` 增补 `atomic_io` / `diagnostics`；`release_check` 支持「动态 Release 徽章」（不再要求静态版本徽章）。

### 1.23.88 — 2026-10-19

- **新增「生产测试架」标签页**（常驻、与协议无关、懒加载，图标 `flask-conical`）：**三栏布局** —— 左「发送配置」**5 条发送框**（各自 HEX/ASCII、各自 checksum8 + 落位方式：追加 / 覆盖末字节 / 插在 16H 前）、中「接收日志」（HEX/ASCII 显示、时间戳开关、自动滚动、收发计数）、右「测试架参数帧」（现场参数表 49 项 + 6 字节地址域，改动即时生成 75 字节整帧，可发送 / 复制 / 恢复现场示例；**发送形态可选 HEX / ASCII**：HEX 发 75 字节二进制帧、ASCII 发大写 HEX 文本 150 字符）
- **左右两栏可折叠、三栏宽度可拖**：折叠按钮在标题行**外沿**（左栏在左、右栏在右），折叠后只剩 30 px 窄条（按钮 + 竖排栏名），宽度全给中栏日志；展开还原折叠前三栏宽度；`QSplitter` 分隔条直接拖动；折叠状态 + 三栏宽度随配置落盘。参数分组在右栏**单列排布**（不裁标签、不出横向滚动条）
- **现场样例逐字节复现**：`68 AAAAAAAAAAAA 68 14 35 55AA55AA 01 00 60 0E 12 08 18 13 2F 05 FE … 00 39 16`（75 字节）。帧结构 = `68 + 地址6 + 68 + 14(控制域) + 35(参数区 53 字节) + 55AA55AA(命令标识) + 测试STA + 测试无线 + 参数区 + 保留4×00 + CS8 + 16`；**CS8 = 首字节到保留位末字节的 8 位算术和**。参数区 47 项：`动态电流最大值` 为 2 字节保留（样例 `05 FE`），`表号高位` 4 字节，`无线模块版本日期` 3 字节
- **字段表是单一来源**：`production_testbench_core` 的 `FieldSpec`（`HEADER_FIELDS` 2 项 + `BODY_FIELDS` 47 项）的 key/标签/长度/默认值/下拉选项同时驱动界面、组帧与落盘；`FIELD_GROUPS` 只决定界面分组；导入即断言参数区 = 53 字节
- **纯逻辑 / Qt 分层**：`production_testbench_core.py` 无 Qt（组帧 / checksum8 / HEX·ASCII / 时间戳 / 配置合并与 `.tmp`+`os.replace` 原子写），`production_testbench_widget.py` 只做界面；主窗口 5 处接线（import / 占位 tab / 懒加载注入共享串口 / `_restyle_for_theme` / 退出 `cleanup`），不改协议可见性逻辑；串口只订阅 `raw_data_received` / `connection_changed` / `error_occurred`，**绝不开/关端口**
- **落盘** `production_testbench.json`：发送框（名称/内容/模式/CS8/落位）、全部参数、地址域、显示偏好、三栏折叠状态与宽度；脏值（非 HEX、长度不符、下拉越界）逐字段回落默认，坏 JSON 整体回落默认
- **测试**：`test/test_production_testbench.py` **120 项**（A 纯逻辑 55：golden、校验范围反例、CS8 三态、文本编解码、字段偏移、非法输入、配置合并、布局配置、`frame_payload` HEX/ASCII；B GUI 56：三栏布局、折叠/展开还原、拖动宽度、窄条竖排标题、无横向滚动条、参数帧 HEX/ASCII 发送、5 框联动、非法拒发、时间戳、恢复示例、落盘重开、主题、断开、cleanup 幂等；C 接线 9：常驻 tab、排在蓝牙工具之后、懒加载注入共享串口、切协议不隐藏、主题钩子、cleanup），已登记 `release_check.py` GUI_TESTS
- 配套：`APP_VERSION` `1.23.87 → 1.23.88`；spec `hiddenimports` 增补两个新模块（函数级惰性 import，静态分析扫不到）；README 功能表 / 本节说明

### 1.23.85 — 2026-10-15

- **新增「光伏升级」标签页（初版名为「升级」，同版改名）：协议8（DL/T 698.45）文件传输升级（分布式产品升级）**（用户需求：拖入二进制升级包 → 按可设每包字节数分包 → 经 698.45 文件传输逐包下发并等设备确认 → 全部传完发执行升级命令）。三步命令走 OI `0xF001` 文件分块传输管理：启动传输 `F0 01 07 00` → 写文件 `F0 01 08 00`×N（**每包一帧、逐包等确认**）→ 执行升级 `F0 01 0D 00`（默认「立即执行」= `date_time_s` 全 FF）
- **逐字节 golden**：`协议文档/8.698.45协议/代理升级流程.docx` 的启动传输实帧（62 字节）由 `dl_t698_45_upgrade.build_start_transfer` **逐字节复现**（含 HCS/FCS）；`test/test_dl698_upgrade.py` 断其相等
- **新增**：`dl_t698_45_upgrade.py`（纯逻辑：分包/文件信息/三帧组帧/确认判定/校验值，`UpgradePlan` 为分包算术单一来源）、`dlt698_upgrade_widget.py`（Qt 页：拖放、参数折叠区、进度条、日志、中止；**复用共享串口** `write_raw` + `raw_data_received`，单发 QTimer 状态机，无 QThread）、`frame_deframe.py`（**串口分帧族抽出为单一来源**，`serial_tool_widget` 仅同名 re-export）
- **修复三个既有协议栈缺陷（否则本功能无法自证）**：① `AXDRCoder._decode_bit_string` 把 `bit-string` 长度域当**字节数**（规范是**位数**）⇒ 旧实现解析上述 doc 实帧直接失败（`未知类型(0x76)`，0x76 = `"v1.0"` 的 `v`），按位读后 32 行全对；② `_encode_bit_string` 同错（改按 `len(bytes)*8`）；③ 定长时间类型编码器多写长度域（`date_time`/`date`/`time`/`date_time_s` 改为 tag + 定长字节，`time` 同时从 4 字节修回 3 字节）——依据：规范类型表 + 示例 `1C 07 E0 01 14 00 00 00` = 2016-01-20
- **调用方收口**：`frame_gen_widget` / `reflex_web/frame_gen_utils` 的「A-XDR 自定义」模式原先自行拼装（bit-string 按字节写长度、定长时间类型多写长度域）⇒ 改为委托 `AXDRCoder.encode`（单一来源）
- 协议8 SA 默认**通配地址**（特征 `0x45` + `AA×6`），可改单地址/组/广播；每包字节数默认 **600**、超时/重试可配；进度只按**已确认**包累加
- 测试：`test/test_dl698_upgrade.py`（**225 项**，`CORE_TESTS`）+ `test/test_dl698_upgrade_gui.py`（**194 项**，`GUI_TESTS`）+ `test/test_dl698_upgrade_tab_wiring.py`（29 项，`GUI_TESTS`）；约定沉淀为 §5.6 与 §8 陷阱 76/77
- **独立复核（trellis-check）发现并修掉 3 处阻塞级缺陷**：① RX 重同步只跳「非 68/FE」，一次线噪即让缓冲头永久卡住 ⇒ 整轮升级失败（改为「无半帧在等且切不出整帧才丢」）；② 传输中换升级包 ⇒ `_on_ack` 里 `IndexError`（Qt 吞掉 → 状态机卡死）或**静默改发另一文件的数据**（改为传输中拒绝换文件/改参数，须先中止）；③ 传输中点「清除」⇒ 状态回 idle 但按钮门控没复位、页面永久不可用（补 `_finish_buttons()`）。同轮还修掉一条**恒真断言**（cleanup 断信号验证只投整帧 ⇒ 在「忘了断信号」时照样绿），并删掉两条不触产品代码的伪变异反证（A9 七条 → 五条）
- **TX/RX 日志帧显示口径修正**（用户反馈：62 字节的启动传输帧只打到 48 字节，尾部校验值看不到）：`≤200 字节整帧打印`；写文件大帧只显**头尾各 100 字节 + 中间 `...` + `(共 N 字节)`**（`HEX_LOG_LIMIT` 48 → 200）
- **tab 改名 + 可选「读版本信息」两步**（用户需求）：tab 标题「升级」→「**光伏升级**」；新增「升级前读版本信息」/「升级完成后读版本信息」两个勾选项（**默认不勾**、落盘、传输中冻结），读版本 = GET-Request Normal（`05 01 <PIID> <OAD> 00`），**失败不阻断升级**（重试用尽记日志继续）；「读版本内容」下拉二选一：通用 `OAD 43 00 03 00` / **厂家扩展内部版本** `OAD FF 10 04 00`；两条现场实帧（含内部版本）都由 `build_read_version` **逐字节复现**，响应判定 `check_get_response` 按所选 OAD **互斥**（OAD 不符即忽略）
- 同批测试：`test/test_dl698_upgrade.py` 225 → **259 项**（新增 A10 读版本组帧/响应判定矩阵 + A11 内部版本与互斥）、`test/test_dl698_upgrade_gui.py` 194 → **252 项**（[17]~[20]：两开关流程/非阻断/响应不符重试/读版本内容选择与持久化）
- **读版本信息的展示改版 + 逐字段详细解析**（现场反馈：解析内容贴在帧尾要横向拖到底才看得见；内部版本只有一串值看不出字段含义）：日志改为「`[RX] <整帧>` 一行 + `→ 版本信息（…）读取成功（N 项）` + 缩进字段行」；参数栏之下新增「版本信息」区（`升级前`/`升级完成后` 并排两栏，`开始升级`/`清除` 重置）；表191 六个字段名/长度/日期补全规则收口到 `dl_t698_45_data_decode.VERSION_FIELDS`（`CLASS_ATTR_TEMPLATES[(19,3)]` 引用），厂家扩展内部版本与标准对象共用 —— 现场实帧解析出 厂商代码=LHIN / 软件版本号=0039 / 软件版本日期=2026-08-03 / 硬件版本号=001A / 硬件版本日期=2025-10-13 / 厂商扩展信息=GWGSXXXX；**长度与声明不符时命名照给但追加 `⚠ 长度未自证` 行**
- 同批测试（二次）：`test/test_dl698_upgrade.py` 259 → **273 项**（A12 版本明细）、`test/test_dl698_upgrade_gui.py` 252 → **269 项**（[13] 展示区几何护栏 + [20] 现场帧 + [21] 非结构兜底）
- **读版本信息显示改版 + 逐字段详细解析 + 等设备复位 + 发送通道（蓝牙）**（连续三轮现场反馈/需求，细节见 §5.6 与 spec §7j）：① 日志「帧一行 + 明细在下」、参数栏下新增「版本信息」两栏展示区（升级前/升级后对比）；② 「升级完成后读版本」与是否发执行升级**解耦**，读前先按「升级后等待(s)」等设备复位（默认 10 秒、0~600，1 秒倒计时显示在状态行；等待期 `_retry_or_fail` 有守卫，防凭空补发执行升级帧）；③ 新增**发送通道**（串口/蓝牙）：蓝牙复用蓝牙工具页的连接，每包上限按「一次 ATT 写上限 − 698 整帧开销」**自动算**（MTU 512 ⇒ 509 ⇒ 每包 475），整帧一次 ATT 写（`send_data(..., single_write=True)`，超限拒发）
- 同批测试（三次）：`test/test_dl698_upgrade.py` **286**、`test/test_dl698_upgrade_gui.py` **355**、`test_bluetooth_worker.py` **123**、`test_dl698_upgrade_tab_wiring.py` **37**；`release_check.py --with-gui` = PASS=138 FAIL=0 WARN=0（读版本展示轮）/ PASS=134 FAIL=4（4 项为本机已知 offscreen 退出期 fastfail，断言全绿）
- **桌面「粘性入口」：托盘菜单内嵌报文输入框 + 任务栏缩略图按钮**（用户问「能不能像汽水音乐那样把可交互控件放任务栏上」）。先落结论：**Win11 任务栏对第三方封闭**，任意控件（尤其输入框）进不去那一行；截图里的「封面+标题+播放键」是 **SMTC 媒体卡片**（媒体会话专属）。因此做两条**受支持**的入口：① `sys_tray` 菜单里嵌「输入框 + 解析」(`QWidgetAction`)，回车 → 与剪贴板/文件右键**同源**的解析路径（`clipboard_monitor.strict_hex` 判据），不受理时状态栏+气泡说明；② 新模块 `system_integration/taskbar_buttons.py`（纯 ctypes 调 **ITaskbarList4/3** + `QImage→HICON` + `WM_COMMAND` 拦截）：悬停任务栏图标时预览里出现 4 个可点按钮（解析剪贴板/快捷解析/批量解析/光伏升级）。硬坑见 §8 陷阱 78（Win11 只认 `ITaskbarList4`、HANDLE 必须声明 `argtypes`、PySide6 过滤器返回**单个 bool**）
- 同批测试（四次）：新增 `test/test_tray_taskbar_entries.py`（**27 项**）；真机冒烟 `_setup_taskbar_buttons()`→True、按钮 id `0x7700..0x7703`、`PostMessage(WM_COMMAND)` 触发 `clicked`，「光伏升级」按钮 → 协议 8 + tab 文案「光伏升级」

### 1.23.79 — 2026-10-13

- **蓝牙工具：特征码自动优选 + 一键探测 + 按设备记忆**（用户：本软件主要按 HEX 收发报文，给一堆特征码让用户挑体验很差，要能更快收发）。旧逻辑取设备枚举顺序里**第一个**可用写/通知码 —— 实测常落到 `2A00` 设备名 / `2A19` 电量 / DFU 特征码上；现按「同码可写可通知（透传回环）> 厂商透传族谱（Nordic UART `6E400002/3`、`FFE1`、`FFE5/FFE9`、`FFF0~FFF2`…）> 名称/描述含 `tx/rx/uart/串口`」打分排序，并**降权**标准 GATT 与 OTA/DFU。打分表与族谱**只在 `bluetooth_core` 一处**
- **一键「自动探测」**（新增按钮）：按打分顺序逐个「订阅 → 写探测帧 → 等回包」，命中即锁定并报告「收到 N 字节回包」；失败逐条给出可读原因（订阅失败 / 写入失败 / 写入成功但无回包）；**全败恢复探测前的选择**并提示手工选。探测帧优先用发送框内容（HEX 写错直接拒绝），为空时用 `probe_frame`（默认 `41 54` = AT）
- **协议时序**：新增 `bluetooth_worker.subscribe_finished` —— 订阅是异步的，写完才等回包会丢首个响应，探测必须先等到它；状态机 `core.ProbeSession` 纯逻辑 + 界面 QTimer 分步驱动，**不阻塞 GUI**，可中途停止
- **按设备地址记忆**（`char_map`，`CHAR_MAP_MAX=20` 按 `ts` 淘汰）：同设备重连直接沿用；换到**没记过**的设备会清掉上一台的选择再重新优选。界面状态行显示「发送 → `0xFFE1` ｜ 接收 → `0xFFE1`」；「特征码…」对话框按打分**置顶并预选**、不可用方向**文字标注**（置灰在 QSS 下看不见，见陷阱 71）
- 测试：`test_bluetooth_core.py`（**116 项**）/ `test_bluetooth_worker.py`（**81 项**，含订阅完成信号两条路径）/ `test_bluetooth_widget.py`（**169 项**，含反例自检「旧逻辑会选 `2A19`」）；**变异反证 3 条**（打分排序失效 → 12 项红；订阅失败也照写 → 3 项红；记忆写同一全局键 → 3 项红）逐条实测变红后逐字节还原
- 配套：`APP_VERSION` `1.23.78 → 1.23.79`、README 徽章/功能表/更新记录、两个 `.iss` 同步；AGENTS §3 与 §8 陷阱 69 已更新；spec 新增「蓝牙特征码优选与探测」契约段落

### 1.23.78 — 2026-10-13

- **串口工具：协议特征断帧认前导 FEH**（现场报障：协议 8 下 `FE FE FE FE 68 21 00 … 38 16`（39 字节）被切成两条 `[RX]`）。根因是分帧函数一律要求首字节 `0x68`，前导 FE 使其判不出长度 → `_frame_incomplete` 也判 False → 退回 10ms 静默窗口。现 68 家族（`ft12_68` / `dlt645` / `dlt698_45` 与未指定协议的启发式）先按 `wakeup_prefix` 跳过帧首连续 FE 再算长度，**返回值含前导字节数**（调用方仍按 `buf[need-1] == 0x16` 自证 ⇒ 三处调用点零改动）；HDLC / DLMS Wrapper 不加前导容忍
- **新增「断帧设置」**（接收模式下方）：断帧方式 `auto`（有协议→按协议特征断帧拼帧，无协议→按字节超时 + 68 结构自证）/ `timeout_only`（忽略协议结构）；4 个可调超时 `rx_byte_idle_ms` / `rx_raw_max_hold_ms` / `rx_frame_idle_ms` / `rx_frame_hold_max_ms`（默认 = 原模块常量 ⇒ 只新增键、`CONFIG_VERSION` 不动）；`FRAME_TIMEOUT_RANGES` 是 UI spin range 与 `merge_params` 夹紧的唯一来源
- 断帧依据可自查：日志在**设置变更 / 协议变化 / 每轮开始**时输出一行 `[断帧] 方式=…；依据=…；超时 …`（不逐帧打印）
- 测试：`test/test_serial_proto_frame.py`（**147 项**）+ `test/test_serial_tool_widget.py`（**501 项**，含现场帧 14+25 两块交付只出 1 行）；**变异反证 3 条**（不跳前导 FE / 长度不含前导 / 断帧方式失效）逐条实测变红后逐字节还原
- 配套：`APP_VERSION` `1.23.77 → 1.23.78`、README 徽章与更新记录、两个 `.iss` 同步；AGENTS §8 陷阱 59 与 75 已更新

### 1.23.77 — 2026-10-13

- **协议9 新增 2.0 测试扩展 `0x0009`「报文聚合传输测试模式」**（依据《宽带双模通信模块（通感一体物联版）相关测试命令定义_260922》1.4.9：`报文聚合数目 | 字节3 | 位0-7 | 8bit`）。此前 `0x0001~0x0008` 已支持、`0x0009` 三处表全部缺失（解析映射表 / 解析分派表 / 组帧 `_EXT_BUILDERS`）；本次补齐，并保证**解析 · 组帧 · 仿照报文回填 · 批量摘要**四处同构
- 字节口径沿用既有扩展约定 `ext_data[x] = 文档字节 x+3`（`_parse_test_ext_0005` docstring 已固化）⇒ `报文聚合数目` = 扩展数据第 0 字节（整字节，无位域）；解析/组帧/反解三处同名同值（`报文聚合数目` / 模式 key `ext_agg` / 参数 `agg_count`，组帧默认 1）
- 顺带修正 `csg_test_frame_gen_widget.py` 三处**互不一致且都已过期**的模式数量文案（26 / 24 / 26）→ 模块级 `_MODE_COUNT = len(fg.test_modes())` 单一来源（现 25）
- 测试：新增 `test/test_csg_test_ext_0009.py`（**76 项**，入 `CORE_TESTS`）；**变异反证 3 条**（解析位宽 / 组帧字节数 / 反解分支）逐条实测变红后逐字节还原
- 配套：`APP_VERSION` `1.23.76 → 1.23.77`、README 版本徽章、两个 `.iss` 同步；AGENTS §5.7 模式数与回归清单已更新

### 1.23.76 — 2026-10-13

- **修复协议8/协议6「带 FEH 前导码的合法帧解析失败」**（用户报障：蓝牙工具收到 `FE FE FE FE 68 21 00 C3 …` 的 39 字节回包，报「❌ 解析失败  起始字符错误: 0xFE, 期望 0x68」，字节全可见却一字段都解不出）。根因是**规范符合性缺口**（不是容错不足）：DL/T 698.45-2017 §6.3.1 b) 规定「在有效数据帧前加 4 个 FEH 作为前导码」，DL/T 645-2007 §5.3.1「建议先发送 4 个字节 FEH 以唤醒接收方」，而旧实现把首字节当起始符判据
- 新增 `wakeup_prefix.py` 作为**全仓唯一**前导判定实现（`wakeup_prefix_len` / `strip_wakeup_prefix` / `wakeup_display` / `make_wakeup_row` / `shift_row_offsets`，零依赖无 Qt）：只跳过帧首**连续** `0xFE`（0~N 个，不假定恰好 4 个、不动帧中 FE），无前导时恒等
- 协议8：`parse` 剥离并记录 `唤醒前导`、`原始数据` 保留原始输入（含 FE）；`parse_to_table` 首行插「唤醒前导字节」+ 所有帧内行偏移整体 `+skip`（报障帧实测起始字符 4~4、HCS 16~17、FCS 36~37、结束符 38~38）
- 协议6：`check_structure` / `check_frame` / `calc_checksum` / `parse` 统一按剥离后帧判定（幂等），新增 `wakeup_len`、`raw_hex` 保留原始输入；`DLT645GuiParser` 同款插行 + 偏移位移（帧起始符 1 = 4~4，校验和/帧结束符 = 末两字节），`fields` 形状不变
- 两个校验器先剥离再走全部检查，`skip > 0` 时追加「前导唤醒字节」PASS 说明项，消除「解析成功但校验报起始符错误」；坏 CS 帧仍 FAIL
- 蓝牙工具分包日志：`_chunk_plan` 为尺寸与来源的唯一实现，分包时输出「单包上限 / 包数 / 协商 MTU 与来源」说明（分包不可消除 —— ATT 层 `MTU−3`）
- 范围**严格限定**协议8/协议6（逐协议护栏 + 白名单源码守卫）；批量/Web 帧提取不变（本就从 `68H` 起同步）
- 测试：新增 `test/test_wakeup_fe_prefix.py`（**73 项**，入 `CORE_TESTS`）；`test_bluetooth_worker.py` 补分包日志断言、`test_dlt645_table_offsets.py` 适配前导行
- 配套：`APP_VERSION` `1.23.75 → 1.23.76`、README 版本徽章、两个 `.iss` 同步；AGENTS §5.4/§5.6 各加前导约定、§8 新增陷阱 75

### 1.23.75 — 2026-10-12

- **修复协议11（HDC 1.0）`报文头长度` 解析错误**（用户报障：报文头 `81 C1 …` 被解成 33、表格显示 `33×4B=132B`，正确应为 **6**）。根因是该 6bit 跨字节位域的**拼装方向取反**——全协议唯一一处「字节号小的段存高位」；口径统一为 `((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)`，且**值 = 报文头的字节数**（不再是 4 字节字）
- 收口范围：协议11 全部 8 处 + 协议10 `gw_new_gen_cmd_payloads` 全部 14 处（后者的抄表/通用/注册等旧值同样与自家说明「固定为8」自相矛盾）
- **四处互证**：① 协议10 真实帧 `81 61 20 00 00 00` → 6，且该载荷恰好 6 字节即整根报文头（`test_gw_ext_cmd.py` T13）；② 0x0A1 真实帧 `01 53` → 12 与 DATA 自字节 12 自洽；③ 表2 扩展命令报文头 = 字节0~5 = 6；④ 各报文自家说明（固定为8 / 通用 4 字节 / 下行20·上行36）与新值逐一对上。**旧口径只在字节0 bit7-6 == 0 时与「值=字节数」数值相同**（此时 `4×lowNibble == lowNibble<<2`），故 1.23.74 用 `01 53`/`01 61`/`01 02` 校准无法判别方向
- 表格呈现同步：原始值 `0b0001+0b10`（按值序，可直接读为数值）、说明给归属 + 移位拼装式 + 「单位 字节」、解析值 `N字节`；`_bit_span_note` 去掉已无调用方的 `lsb_first` 参数与「高位段在前」分支
- 测试：`test/test_hdc10_bitfield_display.py` 重写扩到 **47 项**（用户报障帧 / 与协议10 对拍 / 「值=字节数」偏移锚定 / 10 组取值自洽 / 旧口径 33 反证），4 个测试文件期望同步；**变异反证**：方向改回 → 16 项红、渲染段序改回 → 17 项红（还原后逐字节一致且全绿）
- 顺带删掉 `main_gui.py:_extract_test_mode_content` 里一行**不可达的** `return frame_summary.extract_test_mode_content(...)`（1.23.42 收口时的遗留，是全仓唯一 F821）
- 配套：`APP_VERSION` `1.23.74 → 1.23.75`、README 版本徽章、两个 `.iss` 同步；AGENTS §8 陷阱 74 **重写**（原文「两类位域方向相反、别互相纠正」已被本次证据推翻）

### 1.23.74 — 2026-10-12

> ⚠ **本条的口径结论已于 1.23.75 被推翻**（`报文头长度` 并非「字节号小的存高位」、单位也不是 4 字节字；该次「实测钉死」的两例无法判别方向）。位域在表格里的**呈现形式**仍沿用，**方向与单位以 1.23.75 及 §8 陷阱 74 为准**。

- **协议11（HDC 1.0）跨字节位域在表格里「看得见」了**（用户追问：`报文头长度` 的 4B 是怎么拼出来的、如何体现 bit 组合关系）。原先只给 `1×4B=4B`，看不出 1 来自哪两个字节的哪几位
- 新增纯函数 `_bit_slice` / `_bit_span_note` / `_hdr_len_cells`：**原始值列**给位段拼装式 `0b00+0b0001`（`+` = 按位拼接），**说明列**给 `0b00_0001 = 1`（`_` 标字节边界）+ 单位口径（4 字节字，类 IPv4 IHL）；相邻位域字段说明列追加「位域归属」（`报文头字节1[bit7-4]=4bit=0b0110`）。**偏移列本就高亮跨字节区间**（报障帧 = 字节 37-38），两侧合看即可核对 bit 占用
- 覆盖 `报文头长度` 三处产出点（抄表 0x001~0x003 / 通信测试 0x006 / 升级状态 0x034），并把 0x034 的解析值由裸数字补成 `N×4B=MB`；0x006 检测扩展命令的 测试模式 / 12bit 配置值 / 安全测试模式 / PHR_MCS / PSDU_MCS / PbSIZE 均补归属
- **关键发现（沉淀为 §8 陷阱 74）**：同一应用报文头里两类跨字节位域拼装方向**相反** —— `报文头长度` 是「字节号小的存高位」，12bit「转发数据长度/配置值」是「字节号小的存低位」（口径同 `_bits_lsb`）；两者都不得按另一种口径「顺手纠正」
- 不动被判定的槽位：测试模式行原始值保持十进制 `6`、解析值保持模式名（`extract_test_mode_content` 靠「非数值者即名称」探测）；`转发数据规约类型` 说明被逐字断言，不加尾注
- 新增 `test/test_hdc10_bitfield_display.py`（**38 项**，`CORE_TESTS`）：位序反证（`0x81/0x63` 正解 35 ≠ 反解的 50）、三处反解恒等（8 组取值 + 边界 0）、三类报文口径一致、60 条真实夹具逐条自洽（**夹具须用 `pb_only` 级别**）、0-5 字节 × 7 级别不抛异常

### 1.23.73 — 2026-10-12

- **修复协议11（HDC 1.0）台体日志帧「解析不出内容」**（用户现场报障：协议 [11] + 级别「FC+PB解析(完整MPDU)」）。台体把报文内容组好后落日志，**FCCS / PBCS / ICV 由硬件发射机在发射时填充**，日志里留空为全 0；这类留空帧必须能解析
- 三条根因：① `_detect_fc` 拿 FCCS 当唯一判据 → 判「无 FC」，而 DT=0 有信标兜底、**DT=1（SOF）没有** → 整帧按裸 MAC 帧解，吐错位臆造；② `fc_mac` 的 `_parse_pb_and_mac_header` 对首块也跑「省略 PBH」探测，帧尾 0 填充让「ICV 全 0」证据误命中 → 合法 PBH 被当 MAC 头；③ `_fill_crc24` 的 **eFC 分支无协议门控** → 把 CRC-24 写进协议11 的 MAC 帧头（「组网序列号」`0x01` → `0xE1`）
- 修法：新增 `_looks_like_fc_payload`（FCCS 全 0 时改判帧体结构，**只对 SOF 生效**、复用 `_probe_pb_form` 打分 ≥ 4）；`forced_fc` 尊重显式级别但加规范硬条件（偏移16 必是置帧起始位的首块 PBH，防劫持 PB 级输入）；SOF 首块直接采信 PBH；`_fill_crc24` 的 eFC/PBCS 门控到协议9（FCCS 仍对所有协议生效）；留空一律给「⚠ 未填充」而非「校验失败」
- 端到端（用户原帧，auto 与 fc_pb 逐字符一致，54 行）：DT=1 SOF、PBH `0xC0`、MSDU类型 `0x30`、MSDU长度 8、端口 `0x11`、报文ID `0x0006`、ICV `C5 0F 88 0D` 校验正确 ✓、⚠ PBCS未填充
- 新增 `test/test_hdc10_blank_checksum.py`（55 项，`CORE_TESTS`）与 `test/test_hdc10_blank_checksum_gui.py`（20 项，`GUI_TESTS`），四处修复**逐条变异反证全部变红**；约定沉淀为 §8 陷阱 72（另见陷阱 73：`os._exit` 前必须 flush）

### 1.23.72 — 2026-10-12

- **修复「特征码」选择对话框列表文字看不清**（用户现场报障：浅色主题下隔行看不清）。根因在**主题层**：各主题的「表格 / 字段树」选择器组（基类 + `::item:!alternate` / `::item:alternate` / `::item:selected`）只写 `QTableWidget, QTreeWidget`，**从未覆盖 `QListWidget`**；报障机是 Windows 深色模式（`AlternateBase = #001a68`），而 `LIGHT_QSS` 用 `* { color: #000000 }` 强制黑字 → 列表**交替行**变成「深色系统底 + 黑色主题字」，实测对比度 **1.35**（glass 1.06 / mica 1.12）；反向的「浅色系统 + 暗色主题」同样 **1.23**
- 修法：`QListWidget` 补进 5 套带 QSS 主题的四条选择器组，配色沿用各主题既有表格值（`build_glass_qss` / `build_mica_qss` 自动继承）；`bluetooth_tool_widget` 一行样式未改（页面不写硬编码配色）。**同一根因还影响 `feedback_dialog` 的截图列表与 `main_gui` 的列表**，一并修好
- `test/test_theme_settings.py` 新增 1c 节「列表主题覆盖」（48 → **73 项**）：静态「凡 `QTableWidget` 规则必须含 `QListWidget`」+ 注入深/浅两种系统调色板的真实渲染对比度（只取文字区、跳过勾选框）；**变异反证**：还原修复前写法 → 变红 9 项，还原后 73/73 全绿。约定沉淀为 §8 陷阱 70（另见陷阱 71：`~ItemIsEnabled` 置灰在 QSS 主题下不生效，已知未修）
- 配套：`APP_VERSION` `1.23.71 → 1.23.72`、README 版本徽章、两个 `.iss` 同步；全量 `release_check.py` → PASS=117 / FAIL=0 / WARN=0

### 1.23.71 — 2026-10-12

- **新增「蓝牙工具」标签页：本项目首次具备 BLE 蓝牙通信能力**（集成自子工程 `蓝牙转串口工具02` 的 PySide6 版与 PyTauri 版传输核心）。始终可见、懒加载，与协议无关：扫描 BLE 设备 → 连接 → 选特征码 → 收发 → 解析 → 虚拟串口透传
- 三个新独立模块：`bluetooth_core.py`（纯逻辑，无 Qt/bleak）、`bluetooth_worker.py`（`QObject` + 私有 asyncio 事件循环线程）、`bluetooth_tool_widget.py`（UI + 特征码选择/按钮编辑/批量导入三个对话框）；`main_gui.py` 只做懒加载接线（`_ensure_bluetooth_tool_tab`）、主题钩子与收尾（`_shutdown_threads` 第 6c 步）
- 接线复用既有约定：串口侧复用主窗口**共享** `SerialWorker`（虚拟模式透传，端口/波特率只在顶部「串口配置」设置）；解析/协议/单帧三项能力全部注入，widget **不 import `main_gui`**
- **相对原工具的实测改进**：按协商 MTU 与特征码 `max_write_without_response_size` 分包（原硬编码 200 字节）；重组只保留「静默超时切帧」单一语义且断开/掉线前交出残包；发送格式三态且 **HEX 写错绝不静默按文本发**、位数不成对也拒发；未选特征码时自动取首个可用通道并记日志；未知 RSSI（bleak 报 0）不再误显示满格
- **弹框必留日志**：内容无效 / 未连接 / 回调缺失等原先只弹模态框的路径，现在同时写日志（弹框一点就没了，现场排查只能靠日志）
- 新增 4 份测试并登记 `release_check.py:CORE_TESTS`：`test_bluetooth_core.py`（68 项）、`test_bluetooth_worker.py`（74 项，注入假 bleak）、`test_bluetooth_widget.py`（146 项，offscreen + 假 worker/假串口）、`test_bluetooth_tab_wiring.py`（36 项，真实 `MainWindow` 验证懒加载/注入/主题/收尾接线）；约定沉淀为 §8 陷阱 69
- 配套：`main_gui.py` 的 `CHANGELOG` / `APP_VERSION`（`1.23.70 → 1.23.71`）、打包 spec（`collect_submodules('bleak')` + `collect_submodules('winrt')` 与三个新模块的 `hiddenimports`）、`.gitignore`（`bluetooth_tool_config.json`）、README（依赖 / 功能 / 模块 / 测试四处）

### 1.23.67 — 2026-10-08

- **修复协议9（南网新一代载波）信标帧 `0x10` 代理角色条目的代理站点 TEI 解析错误**（用户现场报障：「解析代理角色TEI的时候解析的不对，协议是12个bit位组合成一个TEI的」）：表72 规定长度字段之后是**连续 12 比特**的 TEI 位流（节点1TEI = 内容字节0 bits0-7 + 字节1 bits0-3，节点2TEI = 字节1 bits4-7 + 字节2 bits0-7），且**条目里没有独立计数字段**（只能由内容比特数反推 N = `字节数×8//12`）。旧实现按「每 2 字节一个 TEI」切、把 `内容字节数//2` 当站点数 ⇒ 用户帧 `10 06 00 01 70 00`（条目长度 6 → 内容 3 字节 = **2 个** 12 比特 TEI）只输出「代理站点数: 1 / 代理[0]TEI = 1」，第 2 个 TEI（=7）被整段丢掉。现场帧修复后：代理站点数 2 / 代理[0]TEI = 1 / 代理[1]TEI = 7
- 修复：`csg_new_gen_parser._parse_beacon_entry_detail` 的 `0x10` 分支改为按 12 比特连续位流解包（复用 `_extract_bits`，LSB 优先，与表61 站点TEI 同一约定），每个 TEI 单独一行并给出**跨半字节**的字节范围（TEI2 落在内容字节 1~2）；末尾不足 12 比特时新增「条目尾保留位」行（表72 对奇数个代理站点的 4 比特保留位）。长度字段宽度不受影响（仍按表59 = 2 字节，声明值超限才退回 1 字节）
- 回归：`test/test_csg_new_gen.py` 新增用户实帧用例（114 字节；逐条目长度 22/34/4/10/6/31、6 条条目链不变、TEI = 1/7、字节高亮 96-97 与 97-98、偶数站点时无尾保留位行），既有 1 个代理站点帧（`10 04 60 00` ⇒ TEI=96）断言保留并补「条目尾保留位 = 4bit」；**变异反证**：站点数改回 `ln // 2` 实测新用例变红。约定沉淀为 §8 陷阱 67

### 1.23.66 — 2026-09-30

- **批量解析工具栏合并成两行**：「CLI 预处理」与「Python 脚本」原是上下两行 → 合并进**同一个 `FlowLayout`**（组间竖线分隔），1366×768 与 1920 下都排成一行（工具栏区段 104px → 52px，省下一行）。合并的**关键前提是把 4 个导出按钮挪出这一行**（移到核心操作行右端，仍在工具栏右上角）：第一版把导出留在合并行，单行需 ~1700px，1366 下照样折成两行 = 白合并；解析进度条与「取消」同时移到状态栏（只在解析中出现）
- **`FlowLayout` 新增可选 stretch 权重**（`FlowLayout(..., stretch=True)` + `addWidget(w, stretch)` / `addStretch()`，默认关闭 ⇒ 顶部协议组口径不变）：宽屏把行内剩余宽度分给两个下拉框（命令框 2 : 脚本框 1）与行右端的帧计数徽章；**拉伸后必须把同行后续项的 x 一起右移**，否则变宽的下拉框会盖住后面的按钮
- **命令框占位符必须短**：可编辑 `QComboBox` 的 `sizeHint()` 会把 `placeholderText` 算进宽度（长示例 481px → 短示例 250px），长文案足以把合并行顶到折行；改用权重分配后不再需要给下拉框设 `maximumWidth`（那会浪费宽屏剩余宽度）
- `test/test_batch_toolbar_layout.py`（**59 项**，offscreen）：工具栏只剩两行、**1366 基准宽度下两行各自一行**、宽窗一行且下拉框吃满余宽、帧计数徽章贴行右端、进度条/取消在状态栏、**2560→760 共 13 个宽度零重叠**、命令框 `sizeHint` 不得失控。**测试踩坑**：跨 `QTabWidget` 页面不能用 `mapTo(win)` 判行（offscreen 下给出 x=2563 的离谱坐标），要用 `layout.itemAt(i).geometry()` 并**容差聚类**判行（同行各项 `top()` 会差几像素）；另外 `QLabel` 是 `QFrame` 子类，数分割线必须用精确类型
- `release_check.py --with-gui` → **PASS=118 FAIL=0 WARN=0**

### 1.23.65 — 2026-09-30

- **协议9 组帧页新增「⓪ 仿照报文 / 模板」**：粘贴一帧官方报文 → 自动反解回填各层参数（ED..EE 封装 / 整帧 MPDU / 应用层帧都能识别；24 个测试模式全部可反解，表61 模式号取高 4 位、2.0 扩展按扩展 ID 分派）→ 只改要变的字段再生成；参数集 + 原始参考报文可存成本地模板（`csg_frame_templates.json`，原子写 + 坏文件宽容），下次「加载模板 → 改关键字段 → 出新帧」
- **回填即逐字节反证**：用真实组帧路径重建一次与原帧对比，一致才提示可放心微调；表单表达不了的字段（报文标识符非 `0x0101` / 业务标识非 `0xF0` / 保留位非 0）按「手工 HEX 保真」兜底并明确告知后续改动的影响范围；另有「对比当前输出」按钮报告首个不一致字节
- **修复：32bit 字段装不进 QSpinBox** —— ED 时间戳是真实 Unix 秒量级（`0x68xxxxxx`），此前上限被夹到 `0x7FFFFFFF`，既填不进真实时间戳、回填 `setValue` 还直接抛 `OverflowError`；信标时间戳/周期同理。新增宽整数文本框 `_WideIntEdit`，并把所有回填赋值收敛到 `_write_widget_value()`（先夹范围再 setValue）
- **右栏「显示响应解析」开关**：协议9 纯组帧场景默认收起、把高度让给实时解析预览，其它协议保持默认显示；开关状态记住用户偏好（协议9 只强制收起，随时可勾回）
- 新增 `test/test_csg_frame_reverse.py`（**96 项**，纯逻辑：层次识别 / 24 模式全量反解 / 三型定界符 / 两种 ED 公共头 / 32bit 字段 / 错误路径 / 变异反证）与 `test/test_csg_frame_templates.py`（**92 项**：存档往返 / 同名覆盖 / 名称校验 / 坏文件宽容 / 原子写 / 上限），均入 `CORE_TESTS`；`test/test_csg_frame_gen_gui.py` 扩到 **139 项**。`release_check.py --with-gui` → **PASS=117 FAIL=0 WARN=0**

### 1.23.64 — 2026-09-30

- **协议9（南网新一代载波）接入「协议组帧」页**：注册表 `frame_gen_mode="csg"`（`preset_mode` 保持 `None`）。组帧页左栏改为 `QStackedWidget`（0=常规动态表单 / 1=协议9 链路层组帧）；五层折叠表单 ①FC 帧控制 ②物理块 PBH+PBCS ③MAC 帧头 ④MSDU ⑤ED 封装，进页面默认勾选「组装链路层」、默认帧类型 **SOF 帧**
- **优先覆盖 SOF 帧 + 各类测试模式帧**：定界符三型 SOF（BPLC / ISAC-PLC、长/短 MAC 头、多物理块）/ 信标帧 / SACK；**24 个测试模式全部**能组出带链路层、且 FCCS / PBCS / CRC-32 三处「校验通过」的 MPDU（用 `CSGNewGenParser` 的 `parse_level="auto"` 回读反证，含接入指示=1 与 MAC 头原始 TEI = FC 源/目的 TEI 的语义不变量）
- **修 3 个真缺陷**：①信标帧 32bit 字段 `QSpinBox.setRange` 溢出（`OverflowError`）打断 ① 区重建 —— 切信标帧即崩且输出仍是上一帧类型；②`build_link_frame` 预反查 `cmt_index` 使 `_ensure_cmt_index` 的信标 BPLC 特例失效（`载波映射表索引 超出 4bit 范围：16`）；③`FrameBuildResult.hex()` 的 `mac_frame` 对 `None` 不安全 ⇒ SACK / 信标预览整块空掉
- **预设命令页可见性改按 `preset_mode`**（原 `frame_gen_mode`）：协议9 无预设库，原判据会露出空预设页、且「添加到预设」会经 `preset_buttons._get_path` 兜底分支误写 `GW_command.json`；协议9 下该按钮隐藏并带提示。0/6/7/8/12 有预设库的协议行为不变
- 新增 `test/test_csg_frame_gen_gui.py`（**71 项** offscreen GUI 端到端）；`test/test_csg_link_frame_gen.py`（176）/ `test/test_collapsible_section.py`（51）登记进 `release_check.py`；`test/test_protocol_registry.py` 的组帧协议集合更新为 `{0,6,7,8,9,12}`。`release_check.py --with-gui` → **PASS=114 FAIL=0**

### 1.23.62 — 2026-09-29

- **报文工具补齐「HEX → 数值」**（对称 1.23.60 的「数值 → HEX」）：同一分组框与类型下拉，输入 HEX 后同时给出**大端/小端两个解析值**；浮点按 IEEE 754（`3F C0 00 00` → 1.5），有符号/无符号按类型位宽（`FF FF 9E D0` 作 double-long → 大端 -24880 / 小端 -794886145）
- 新增纯逻辑 `hex_text_to_bytes`（容忍分隔符与 `0x`、连续写法，拒奇数位/非 HEX）与 `decode_numeric_value`；与 `encode_numeric_value` **严格互逆**（同类型下 `解码(编码(x)) == x`），字节数不符**不静默截断**而报可读错误
- `test/test_message_tool_numeric.py` 278 → **469 项**（[6] 互逆+文档锚点 / [7] HEX 错误路径 / [8] GUI 对称方向）；**变异反证 3 条**（大小端互换 / 有符号位丢失 / 去掉字节数守卫）分别 20 / 13 / 21 项变红

### 1.23.61 — 2026-09-28

- **修复协议8（698.45）批量解析「一帧都提取不出」（P0）**：`_extract_69845_frames` 用 `L + 4`，而 §6.2.2 a) 定义 L = 不含首尾定界符的数据长度（L 含两个长度域字节）⇒ **整帧 = `L + 2`**；多算 2 字节 ⇒ 末字节自证必失败 ⇒ 恒返回空、只弹「预处理后未保留有效报文内容！」。三处（桌面 `main_gui` / 共享 `batch_core` / Web `reflex_web.web_utils`）同源修复
- **串口工具 698 分帧同根因修复**：原判据要求「第 4 字节是第二个 68H」且 `L + 3`，而真实 698.45 帧是 `68 | L(2B) | C | … | FCS | 16`（无第二个 68H）⇒ 协议8 分帧恒不命中、退化为时间聚合。现按 `L + 2`；698 / 645 / 南网·国网 的互斥判据改为**末字节自证**（南网/国网 L = 整帧、末字节恒 16H；反向亦然）
- **依据**：① 6.2.2 a)；② 附录 H.1.1 示例 32 字节、L=30；③ 现场 33 字节帧（L=31）经解析器 HCS/FCS 双通过
- 新增 `test/test_dl_t698_45_extract.py`（46 项，登记 `release_check.py:CORE_TESTS`）；**变异反证 3 条**（`+2→+4` / `+2→+3` ×2）分别 6 / 5 / 3 项变红；既有测试里按错误公式造的 `68 L L 68` 假帧夹具全部换成真实帧
- 约定沉淀为 §5.6 帧长公式条与 §8 陷阱 58/59 修正

### 1.23.60 — 2026-09-28

- **报文工具新增「数值 → HEX（大端/小端）」转换**：选基础数据类型（DL/T 790.6-2010 = 698.45 APDU 的 A-XDR 中可用十进制表述的 12 种：bool / integer / unsigned / enum / long / long-unsigned / double-long / double-long-unsigned / long64 / long64-unsigned / float32 / float64），输入十进制值后一次输出**大端**与**小端**两种字节序 HEX
- 类型表与编码器为**模块级纯逻辑**（`NUMERIC_TYPES` / `NUMERIC_TYPE_SPECS` / `encode_numeric_value`，零 Qt）：超范围、非十进制、bool 非 0/1、float 的 NaN/inf/溢出均给**可读中文原因**且不覆盖上次输出
- 字节宽度与符号性**与 `dl_t698_45_axdr.AXDRCoder` 的各 `_decode_*` 一一对应**（测试交叉断言「类型在 AXDR_TAG 中存在 + 解码器已实现」），往返 oracle = 「编码 → 698.45 A-XDR 解码」；文档锚点：`2016`→`07 E0` / `180`→`00 B4` / `164`→`00 A4`（附录 H.1.1）、`-24880`→`FF FF 9E D0`（A-XDR 大端判据）
- 新增 `test/test_message_tool_numeric.py`（278 项）并登记 `release_check.py:CORE_TESTS`；**变异反证 1 条**（小端改为直通 → 12 项变红）
- 布局护栏随测试钉住：下拉/输入框 `visibleRegion` 非空（陷阱 56 类）、按钮 `width >= sizeHint` 且未设上限（陷阱 63 类）

### 1.23.59 — 2026-09-23

- **TCP 监控新增「记录位置」能力**（现场：记录下来的 CSV 找不到、也不知道去哪找）：工具栏新增「打开位置」按钮——一键在资源管理器中**定位并选中当前记录文件**（无记录文件时打开记录目录）；新增「记录目录」菜单（选择记录目录… / 打开记录目录 / 恢复默认目录），目录可自选并**记住**（`tcp_monitor_config.json`，重启仍生效）；状态栏记录名悬停给出完整路径
- 记录目录解析收敛到**单一来源** `TCPMonitorWidget.record_dir()`（用户配置优先，否则 `<数据目录>/Output`）；`_start_csv_recording` 不再硬编码 `app_data_dir()/Output`（沙箱拦不住 → 跑测试会往开发机真实数据目录拉文件）；纯逻辑层 `default_record_dir` / `load_record_config`（缺失/损坏/非对象/BOM 均回落空配置）/ `save_record_config`（原子写）/ `resolve_record_dir` / `open_in_file_manager`（Windows `explorer /select` 定位文件，非 Windows 回落 `xdg-open`）
- **顺带修复既有缺陷**：`monitor/tcp_monitor.py` 从未导入 `QFileDialog`，「加载记录」按钮一点即抛 `NameError`（自 TCP 监控 UI 引入以来潜伏 —— 测试从未点过该按钮）；文件对话框起始目录同时改为当前记录目录
- `gui_utils._STANDARD_ICON_MAP` 新增 `folder` 键（`SP_DirIcon`）—— `set_btn_icon` 对未知键**静默跳过**（同「分享此帧」曾无图标的同类坑），故新按钮必须用合法键并由测试断言图标非空
- 新增 `test/test_tcp_monitor_record_dir.py`（61 项）并登记 `release_check.py` 门禁；**变异反证 5 条**（退回硬编码目录 / 忽略用户配置 / 去掉 `QFileDialog` 导入 / 不再定位文件 / 图标键改非法）均实测变红；约定沉淀为 §8 陷阱 57
- **修复「应用层帧」工具栏 4 个按钮文字被裁**（现场：截图中「记录目录」只显示成「记录目」）：根因是写死 `setFixedWidth(80)`，而 QSS 下 `sizeHint` 已需 92px（带菜单箭头的「记录目录」104px）⇒ 默认字号就裁；真正裁字的是**上限**（`setFixedWidth` 的 min 被 QSS `min-width` 覆盖，只剩 max 生效）。改为 `gui_utils.fit_btn_width(...)`（取最宽者 `sizeHint` 作 `minimumWidth`，只设下限不设上限，切主题/改字号后无需重算、且保持等宽）
- **同一根因第二处（在线监控器筛选栏）**：`monitor_widget.py`「帧类型 / MSDU类型」写死 100 / 120px，默认 10 号字单选「选择确认帧(SACK)」即显示成「选择确认帧(」；因文案会变，新增 `gui_utils.fit_btn_width_for_texts(btn, 候选全集)`（候选与运行时文案共用 `_short_label` 防漂移），「浏览」按钮改走 `fit_btn_width`
- 新增 `test/test_btn_width_fit.py`（66 项）并登记 `release_check.py` 门禁；**真机取证**：用真实窗口渲染工具栏后 OCR，修复前只读出「记录目」、修复后完整读出「记录目录」；主窗口全量扫描 170 个可见按钮**零裁字**；最小窗口 1000×700 下 10 / 14 / 16 / 24 号字均不裁字（24 号需 168px 实得 180px，故**未**引入折行）；约定沉淀为 §8 陷阱 63

### 1.23.58 — 2026-09-23

- **协议12 A-XDR 编码层重写（正确性修复）**：原实现把「小端 + BER 长度域」套到 A-XDR 上 ⇒ APDU 内所有多字节字段错位。协议12 文档**通篇无示例帧**，故改用同族标准 DL/T 698.45 附录 H.1.1「登录」真实编码实例推导：`07 E0`=2016 年、`00 B4`=180s、`00 A4`=164ms ⇒ **A-XDR 多字节为大端**，且**定长类型在 SEQUENCE 内不带 tag、不带长度域**（date_time 连自身标记 0x19 都没有）。链路层 L/C/FCS 仍为小端，两层不再互相套用
- 新增 `modular_iface_axdr.py`（A-XDR 编解码**单源**：表4 全部类型、8 类 APDU、日期时间/Scaler_Unit/bit-string/数组/结构、附录 A `fcstab`+`calc_fcs`、`frame_layout`、`verify_frame`）与 `modular_iface_data.py`（静态表**单源**：附录 B/C/D~L/M 与表1/2/3/5/11/13）
- 编码假设集中 3 个开关（`AXDR_TAG_IN_SEQUENCE=False` / `AXDR_LEN_FOR_FIXED_IN_CHOICE=False` / `AXDR_VAR_LENGTH_BYTES=1`），并新增 `verify_frame(frame)["axdr_tail"]` **作为判据**——拿到真实帧先跑它，非 0 就把 8 种开关组合枚举一遍（实测依据写进注释）
- 修正既有错表：`DAR_NAMES` 由 21 项（形似其它协议）收口到表11 的 **4 个值**（0 成功 / 1 拒绝读写 / 2 信息类未定义 / 255 其它）；DT 位段由 5+3+8 改为 **4+4+8**（与附录 G/J/K/L 的 4000/7100/8000/9000 及 §7.3~§7.11 自洽；表22 按 5 位会与附录冲突，已记录待真实帧定论）
- 删除 `_take_axdr_uint` / `_take_axdr_string`（探测式 + 取不到静默返回 0 会让真实帧字段无声消失）→ 严格解码 + 失败时的 ⚠ 行；新增 Scaler_Unit（表12）解码；`parse()` 收尾的 `self._rows(rows, {...} if False else None)` 死代码修复（meta 如实给出 `valid`/`fcs_ok`/`structure_ok`/`axdr_tail`/`errors`）
- 批量摘要/类型列补协议12 专属分支（此前落兜底）：摘要 =「方向 | 控制码 | 信息类:… | APDU 名」（信息类名走解析器同一个 `dt_name`）；类型列 = APDU 名/控制码名（不改会落 `name.split(" ")[0]` → 显示 `[12]`）
- 组帧页模板下拉恢复「读取·协议版本」→ **13 个模板**；spec `hiddenimports` 补齐 `modular_iface_axdr` / `modular_iface_data`
- 测试：`test/test_modular_iface.py` 46 → **430 项**；新增 `test/test_modular_iface_axdr.py` **185 项**（含 698 附录 H.1.1/H.3.2 独立 oracle、附录 A `fcstab` 全表对拍 + crcmod 交叉验证、表4 逐条、越界/截断、`verify_frame`）
- 顺带修复（新增协议引发的既有测试红/回归）：① 6 项硬编码「12 个协议」变红（`test_window_state` / `test_serial_tool_widget` / `test_serial_proto_frame`）→ 改为与 `protocol_registry.combo_labels()` 同源比对；② 串口工具 `ft12_68` **签名排除恢复**（1.23.57 为修「首片过短」把签名排除整个去掉，连带丢掉「指定南网/国网时不得把 698.45/645 帧按南网口径切」的契约）→ 改为**字节够判时才排除**（`len(buf) >= 8`）
- 遗留：Web 端（`reflex_web/`）尚未支持协议12 的解析/查询/组帧（仅首页协议表有条目）；协议12 未接入虚拟表与 TCP 监控协议识别
- 同步文档：README 协议表/下载区、`landing_web.PROTOCOLS`、本文件 §1/§3/§5/§6/§7/§8/§9/§10/§12；详见 §5.10 与 §8 陷阱 61/62

### 1.23.57 — 2026-09-22

- **串口工具 RX 按发送协议断帧修复**（用户报障：国网 F112 响应被拆成 4 条 `[RX]`）：根因是首片只有 1 字节 `68` 时长度域未收齐 → `frame_length_for` 返回 0 → `_frame_incomplete` 误判「非协议帧」→ 走 10ms 静默窗口单独刷出首片，后续缓冲不再以 68 开头 → 整帧碎裂。修：头标志已出现但长度域未收够 → 一律按**未收全**等待；协议已知时 `ft12_68` **3 字节即可算整帧长**。回归：1+22+9+21 四块、块间隔>10ms → 只输出 1 行 53 字节整帧
- **国网 F112 芯片 ID 解析修复**：24 字节线上为整块小端 → **先原样显示原始 24 字节**，再整体倒序后按表104 解析（类别/厂商/型号/序列号）；现场帧倒序后前 6 字节恰为表104 固定头 `01 02 9C 01 C1 FB`，类别 0x03=HPLC+HRF 双模
- **串口工具命令表新增「次数」列**：每条命令可单独设置本轮连发 N 次（默认 1，范围 1~9999）；双击行 → 编辑对话框修改；发送时按 N 展开进 `messages`，`index_map` 仍指回原命令下标；与底部「循环次数」（原全局发送次数，已改名避免混淆）相乘
- **顶栏折叠后启动时协议名仍贴左**：`showEvent` 在窗口显示后（及 150ms 延迟）按**最终标题栏宽度**重算居中填充；`_update_window_title` 用 `frameGeometry` 宽度、控件+应用两套字体度量；padding 算成负时放宽 chrome 预留再算一次
- **新增协议12 模组化终端功能模块接口**（anydoc 转 MD：`协议文档/12.模组化功能协议/…接口协议.md`）：链路层 `68 + L(数据域长) + C + FCS + 16`、FCS = CRC-16/PPP（`x-25`）；APDU 8 类 CHOICE、DT 信息类标识；`modular_iface_parser` / `modular_iface_frame_gen` / `ModularIfaceValidator`；注册表 index 12、extract=modular、查询页「信息类查询」；组帧 GUI 接线（模板下拉 + DIR/PRM/FID/DT/Data 配置 + 实时解析预览 + 串口回包解析）、预设页独立 `MODULAR_command.json` 种子 8 条、spec 补 datas/hiddenimports
- 协议12 模块信息 Data 深解：GetResponse/Set/Report 的 Data 不再只显示 hex，按附录C DT=0000 展开 模块设备型号/模块设备ID/软件版本/软件发布日期/硬件版本/硬件发布日期/厂商编码（日期约定 `1A 05 + year LE(2)+month+day+week`，避开 698 AXDR `_decode_date` 长度偏差）
- 测试：`test/test_modular_iface.py` 54 项；registry / landing 101 项对拍通过

### 1.23.56 — 2026-09-22

- **串口工具命令状态可手动清理**：勾选操作行新增「清除状态」按钮 → `_clear_cmd_status_clicked()`（只清运行态图标，不动命令内容/勾选；发送中禁止，与「清除统计」同一口径）
- 测试：`test_serial_tool_widget.py` 463 项（第 [33] 段 15 项）

### 1.23.55 — 2026-09-22

- **串口工具命令列表「名称」列用状态图标表示本轮结果**：○ 待测 / ↻ 发送中 / ✓ 通过 / ✗ 失败 / ⚠ 错误；图标取 lucide 并用 `CompositionMode_SourceIn` **按状态上色**（`app_icons.load_icon` 只出单色）；名称文字同色系 + tooltip + 表格下方图例
- 状态存运行时键 `_status`：不进 `normalize_command`、不落盘（`export_commands` 剔除 `_` 开头的键）；状态变化只重画那一行（`_refresh_cmd_row`），不整表重建
- 测试：`test_serial_tool_widget.py` 448 项（第 [32] 段 30 项，含逐态校验渲染像素颜色）

### 1.23.54 — 2026-09-22

- **串口工具日志支持自动保存到文件**（实测诉求）：勾选「自动保存日志」即把日志**实时写入文件**，取消勾选即停止并写入统计尾。文件是**日志窗口内容的完整镜像**（同样受「显示发送 / 显示接收 / 显示解析」控制），但**不截断**（窗口只保留最近 10000 行）。每行带**毫秒时间戳**前缀（可关）、**写一行 flush 一次**；文件头写标题/开始时间/串口上下文，文件尾写停止时间与收发、匹配统计；目录可选（默认数据目录下的 `Output/`）、可一键打开；另有「保存当前日志…」手动另存
- 写入点挂在 `_log()`（日志窗口**唯一出口**）上 → 不存在第二套过滤规则；`LogFileWriter` 纯逻辑无 Qt，文件名同名**不覆盖**（`_1`/`_2` 递增）；打开/写失败一律**外显 + 自动关闭且不递归**（不静默丢日志）
- `cleanup()` 现在会先把**残留日志队列**刷进窗口/文件再收尾（旧版最后几帧会在退出时丢）；第 [17] 段相关断言改为看窗口内容
- 新增三个参数（旧配置缺键 → 默认关闭，行为与旧版一致，故不动 `CONFIG_VERSION`）；测试 `test_serial_tool_widget.py` 418 项（第 [31] 段 59 项）；约定沉淀为 §8 陷阱 60

### 1.23.53 — 2026-09-22

- **串口工具新增匹配方式「HEX 通配（XX=任意字节）」**：正则匹配二进制帧要写 `\xNN`、还得绕开「忽略大小写把 `\x68` 也当 `0x48`」「`.` 不匹配 `0x0A`」两个坑，故新增直写 HEX + `XX` 的方式。**沿用「测试方案」既有约定**（`test_plan_widget._match_frame`：逐字符走、遇 `XX` 跳一字节），`XX` 可内嵌连续串（`68D0XXXX16`），`??` 为别名；语义为**包含式** + 可选 `^`/`$` 锚点（可表达开头/结尾/全长）；命中报偏移
- 匹配方式下拉 6 → 7 项；对话框按方式动态切换占位符与说明（正则的说明里点明两个坑并建议二进制帧改用 HEX 通配）
- 新增纯函数 `parse_hex_wildcard()` / `hex_wildcard_match()` / `match_offset()`（统一匹配入口并返回偏移）
- 测试：`test_serial_tool_widget.py` 356 项（第 [30] 段 34 项）

### 1.23.52 — 2026-09-22

- **串口工具命令表新增「选择」勾选列 + 全选/全不选/反选，发送只发勾选项**（按表内顺序）：勾选存命令 `enabled`（旧配置无该键 → 全选）；`SerialSendWorker.index_map` 把筛选后下标映射回 `commands` 原下标（名称/协议/匹配规则按原下标取，否则张冠李戴）；一条未勾 → 提示不启动。用 `QTest` 真鼠标点击验证 `NoEditTriggers` 下勾选框仍可切换
- **修复「明明是对的却提示不是有效的 HEX」**：`hex_str_to_bytes` 原按空格/半角逗号切分后把片段当**一个字节** → 连续无分隔的 hex（`6812004116`）整串越界被判非法。现容错连续串按字节切、全角/顿号/分号/斜杠/竖线/连字符/全角空格作分隔符、容忍 `0x`；仍拒奇数位与非 hex。新增 `hex_input_error()` 给出可读原因（含字符与位置）
- **修复「正则表达式」匹配方式完全不工作**：旧实现把预期一律按 HEX 校验 → 正则被静默降级成「不匹配」、待匹配项不入队（现场只看到「超时未匹配」）。现正则按文本处理（只校验语法、空正则降级、`encode('latin-1')`），日志按 `正则 <文本>` 展示且不用 repr
- 测试：`test_serial_tool_widget.py` 322 项

### 1.23.51 — 2026-09-22

- **串口工具命令列表双击直接进编辑窗口**（+ 表格提示文案）。单独加 `_on_cmd_double_clicked(row, col)`，**不给 `_edit_command` 加位置参数** —— 按钮 `clicked` 带的 bool 会被当成行号（`False` → 第 0 行）
- 测试：`test_serial_tool_widget.py` 265 项（含走真实 `cellDoubleClicked` 信号验证连线）

### 1.23.50 — 2026-09-22

- **修复响应匹配漏配**（实测报障）：匹配原来按**串口单次交付的块**比对，而驱动把一帧拆成多次交付（实测 208 字节国网帧 = 77+92+36+3），「预期 = 整帧」永远匹配不上（与接收模式无关：匹配吃原始交付块，不是切好的帧）→ 改为按**累积接收缓冲**比对（`MATCH_BUFFER_MAX` 上限），每次发送/队列清空时清空缓冲；「队首连续匹配」语义不变
- **匹配判决全部输出可比对日志**（实测诉求）：发送时打规则行、命中打方式+预期、超时打 5 行诊断（方式 / 预期响应 / 期间收到 / `match_failure_reason()` 结论）；新增 `match_failure_reason()` / `hex_preview()` / `first_diff_offset()` / `match_type_label()` 四个纯函数，并能点名最常见误填「预期 = 发送值」
- 测试：`test_serial_proto_frame.py` 122 项、`test_serial_tool_widget.py` 257 项（含用实测四块交付复现跨块匹配）

### 1.23.49 — 2026-09-22

- **修复「改了默认值却对老用户不生效」**（实测报障）：参数一旦被保存过就把**当时的默认值**写进 `serial_tool_config.json`（实测 `version:1` + `parse_max_lines:30`），而 `merge_params` 只在「键不存在」时才用新默认值 → 1.23.48 的「默认不限制」等于没生效。引入**配置版本迁移**：`CONFIG_VERSION` → 2，`load_config` 按 `version` 调 `migrate_params`（v1 里 `parse_max_lines == 30` = 旧默认 → 迁移为 0；用户特意设的其他值保留；回写升版本 2，不抖动）
- **通用教训**：改任何参数默认值时，必须同时处理「旧配置里已存了旧默认值」，否则对老用户无效 —— 见 §8 陷阱 59
- 测试：`test_serial_proto_frame.py` 102 项（新增配置迁移段）

### 1.23.48 — 2026-09-22

- **串口工具：发送（TX）也按命令协议解析**，与接收对称（之前只解析 RX，发送只有一行 hex）：`_tx_log_queue`/`_rx_log_queue` 统一为 `(kind, text)`，`_queue_parse(..., channel)` 按方向入队；flush 用同一套规则（前缀 `[TX]`/`[RX]`、raw 各自 tx/rx 配色、解析 sys、失败 fail），**burst 只对各自队列的 raw 计数**
- **解析行数默认不再截断**：`parse_max_lines` 默认 `0` = 不限制（0~2000，spin box 0 显示「不限制」）。起因：国网「查询从节点ID信息」一条应答帧实测 **113 行**（22 行帧级字段 + 1 行从节点总数量 + 15 节点 × 6 行），默认上限 30 让现场看不到完整结果；**「113 行」与报文里的「从节点总数量=113」是巧合**，解析器只输出「本次应答数量」个节点
- 测试：`test_serial_proto_frame.py` 88 项、`test_serial_tool_widget.py` 136 项（新增第 [24] 段 TX 解析对称性）

### 1.23.47 — 2026-09-22

- **串口工具：命令表新增「协议」字段**（任务 `09-22-serial-proto-parse`）：第 5 列显示协议短名，添加/编辑命令时下拉选择（`不解析` + 12 协议）；随配置落盘读回，旧配置无该键回落「不解析」，导出裸列表统一补齐该键
- **接收按「最近一次发送命令的协议」断帧**：新增 `frame_length_for(strategy, buf)` —— 南网/国网 `68H+L(2B 小端)`、645 `L+12`、698.45 `L+3`、HDLC `7EH…7EH` 定界、DLMS Wrapper `8+L`；**每种都要求自证**，不满足即交回既有「启发式 + 时间聚合」路径（**错切帧比不切更糟**）；无自证依据的 1/5/9/10/11 行为不变
- **按该协议解析并在日志输出文字**：解析能力由 `main_gui` 注入回调（`set_parse_provider`，widget 不 import main_gui），与单帧页共用同一套分派 → `[解析·<短名>] 摘要` + 缩进字段行；行数上限可配（默认 30）；解析异常/空表只输出失败行，**不伪造**
- 新增「显示解析」开关（关闭零解析开销）与「解析行数上限」参数；RX 日志队列升级为 `(kind, text)`，**burst 只对原始行计数**，同批解析明细整批丢弃
- 新增 `test/test_serial_proto_frame.py`（84 项）；`test/test_serial_tool_widget.py` 扩至 119 项（含**真实解析器端到端冒烟**）；约定沉淀为 §8 陷阱 59

### 1.23.46 — 2026-09-22

- **新增「串口工具」标签页**（任务 `09-22-serial-tool-integration`，集成自 `E:\python\USB负载测试工具`）：命令表（名称/发送 HEX/匹配方式/预期响应）+ 增删改上下移 + 保存·加载配置（JSON 与源工具裸列表双向兼容）+ 加载报文 txt；**精确间隔**循环发送（0=无限）+ 完成后等一个响应超时收尾出成功率；接收两模式（原始数据 / 按帧尾分割）；6 种响应匹配 + **队首连续匹配** + 超时统计；彩色日志 + 高速时按 100ms 批量刷出
- **串口层复用而非重写**：`SerialWorker` 新增静默写入 `write_raw()`（不发日志信号 + 写锁）；串口工具**复用主窗口共享的 `serial_worker`**（端口/波特率只在顶部「串口配置」设置，本页只读跟随连接状态，避免两个句柄争抢同一个 COM 口）
- **命令与参数自动落盘** `serial_tool_config.json`（原子写、损坏回落默认值，已入 .gitignore）
- 实现期由测试发现并修复：**上一轮发送遗留的收尾定时器/迟到信号会掐断新一轮发送**（200 帧只发 140）→ 「发送器身份 + 发送代次」双重守卫；另修复 `_save_timer` 晚于 `_load_persisted()` 创建导致配置保存静默失效
- 新增 `test/test_serial_tool_widget.py`、`test/test_serial_worker_write_raw.py`（登记 `CORE_TESTS`）；既有 `test_serial_worker_framing.py`（28 项）全绿；约定沉淀为 §8 陷阱 58

### 1.23.45 — 2026-09-22

- **TCP 监控补齐「原始载荷」路径**（任务 `09-21-tcp-monitor-raw-apdu`）：`FlowBuffer` 新增 `auto/ed/raw` 切帧策略，非 ED..EE 封装的 TCP 载荷按 **TCP segment 逐包**成帧（实测原先 27B 原始载荷切出 0 帧、字节被静默丢弃）
- **协议识别**：显式选择优先 + 自动识别只认可自证形态（DLMS Wrapper / DLMS-APDU / DLT645-2007 / 698.45）；**南网/国网 不参与自动识别**（校准实测两者校验器互判 0 fail，无法区分），需显式选择 —— 边界已声明并钉在测试里
- **未识别载荷按「原始数据」正常显示** + APDU 标签提示；显式选择下解析器返回退化结果也如实回落，不冒充解析成功
- **UI**：新增 Wireshark 风格字节视图 `hex_dump_view.py`（偏移/hex/ASCII/按字节高亮）、解析结果 表↔字段树 切换（复用 `parse_result_view`）、帧表「源 → 目的」列与未识别帧弱化、仅未识别 + 协议过滤、切换协议重解析已抓帧（>200 帧分批）
- 新增 4 个测试（27 + 27 + 36 + 46 项）并登记 `release_check.py:CORE_TESTS`；既有 ED 相关 TCP 测试（15 / 55 项）全绿；约定与排查手段沉淀为 §8 陷阱 57

### 1.23.44 — 2026-09-21

- **修复启动后「协议选择」下拉框显示为空白（点一下才出现文字）**：根因是顶部协议组自定义 `FlowLayout.sizeHint()` 返回 `minimumSize()`（≈最宽单项 276px），父布局据此只给该宽度 → 布局被迫换行两行 → 分组框 75px 而顶栏容器 49px → 第二行的协议下拉框被裁成一条缝（实测 geometry (5,44)、`visibleRegion()` 仅 266x5）
- **`FlowLayout.sizeHint()` 改为单行自然尺寸**（各子项 `sizeHint()` 之和 + 间距 + 边距），语义对齐 `QHBoxLayout`；`minimumSize()` 不变，窄窗仍照旧换行
- **`_reflow_proto_group()` 补「重排外层顶栏」**：原实现只动内层布局，分组框拿不到最终宽度、内层 FlowLayout 不会被重新调用（单独 `activate()` 是空操作）；补上后下拉框同步从 (5,44)/266x5 恢复到 (76,20)/266x26，无需交互触发
- 新增 `test/test_flow_layout_proto_group.py`（11 项，offscreen，登记 `release_check.CORE_TESTS`）；**反例自检**还原修复前两处实现后判据实测变红
- 排查手段沉淀为 §8 陷阱 56（`visibleRegion()` vs `grab()` 的判别价值）

### 1.23.43 — 2026-09-21

- **「关于」对话框新增 GitHub Star 入口**：底部按钮行加「去 GitHub 给作者点 Star」（`icons/lucide/star.svg`）+ 提示行「如果这个工具帮到了你，欢迎在 GitHub 上给作者点个 ⭐ Star」，点击用系统默认浏览器打开作者仓库
- **地址单一来源 `main_gui.AUTHOR_GITHUB_URL`**：按钮 tooltip / 跳转 / 测试都读它，改地址只改一处（`test/test_about_github_star.py` 有「main_gui.py 内 URL 字面量只有一处」守卫）；`QDesktopServices.openUrl` 返回 False（未装浏览器）或地址为空时**弹窗给出可手动复制的地址**，不静默无反应（同 §8 陷阱 23）
- 「关于」对话框拆出 `_build_about_dialog()`（构造与 `exec()` 分离，便于测试直接检查控件与接线）；菜单接线不变（仍由 `test_menu_wiring.py` 守卫）
- 新增 `test/test_about_github_star.py`（22 项，offscreen，登记 `release_check.CORE_TESTS`）；**变异反证 2 条**（删 `clicked.connect` / 加第二份 URL 字面量）均实测变红后还原
- 遗留（本次未改）：该对话框内「版本 2.0」与更新记录仍是早期**写死的占位文案**，未读 `APP_VERSION` / `CHANGELOG`

### 1.23.42 — 2026-09-21

- **Web↔GUI 修复同步（任务 09-17-web-gui-parity-sync）**：新增审计清单 `docs/Web与GUI同步审计.md`（1.23.0~1.23.22 共 167 条逐条判定：继承 88 / 缺失 21 / 同错 0 / N/A 58，均附 `文件:行号` 依据）
- **645 转表收口**：Web 删除逐字复制体、改 import `protocol_registry.DLT645GuiParser`；偏移改按**实际帧长**算 → 修「声明长度不符」帧的校验和/结束符偏移越界（合法帧输出不变）；`test/test_dlt645_table_offsets.py`（40 项）
- **测试模式摘要片段收口**：单源 `batch_core.extract_test_mode_content`（桌面一行转发 + Web import）；Web 协议10/11 测试类报文摘要补齐该片段（`_append_test_mode_segment` 带去重守卫）；`test/test_web_gui_parity.py`（83 项，含两端对拍）
- **Web 查询页自定义条目 CRUD**：协议0 自定义 DI 增/覆盖/删除（勾选列 + 「删除选中」批量按钮，内置忽略并计数）；协议7 自定义 AFN+Fn 增删（复用 `GDW10376Parser` API + `gdw_afn_lookup.refresh()`）；查询表新增「自定义」★ 列；`custom_di_store` 读写支持可选 `path` 注入
- 详见 §8 陷阱 31（已收口清单）、陷阱 55（Web 查询页自定义条目约定）

### 1.23.42 — 2026-09-21

- Web↔GUI 同步修复等（见 `main_gui.py:CHANGELOG`）；本构建同时包含 1.23.41 的顶部栏整体显隐

### 1.23.41 — 2026-09-21

- **GUI 顶部栏协议+串口整体显隐**：菜单栏右上角**一个小图标**（`panel-top-open`/`panel-top-close`）一键切换；协议选择与串口配置**同时**显示/隐藏，折叠后整行高度归零（开关不在顶栏内）
- 顶栏折叠时窗口标题：左侧保持「版本+日期 - 作者」，**仅协议短名**空格近似居中；状态栏显示 `串口: 端口 · 波特率 · 校验 · 连接状态`
- 折叠态持久化 `config.json` 顶层 `top_bar.collapsed`（兼容初版分键）；测试 `test/test_top_bar_collapse.py`

### 1.23.38 — 2026-09-20

- **协议11 TCP/ED 可解析信标帧**：帧长域与末尾 EE 不一致时按末尾 EE 重算整包；业务解出中央信标（NID/时隙分配等）；摘要兼容「定界符类型(DT)」并带信标类型。详见 §8 陷阱 53

### 1.23.37 — 2026-09-20

- **TCP 监控支持 HDC 1.0 与 ED 封装解析**：协议下拉新增「HDC 1.0」；选中国网HDC 时 ED..EE 按国网HDC 文案解析包装头 + HDC10Parser 解析业务；FlowBuffer 保留完整 ED 帧；`resolve_ed_wrapper` 在协议10/11 auto 时优先 8 字节 gx 布局。详见 §8 陷阱 53

### 1.23.36 — 2026-09-20

- **ED 包装头文案按协议分语义**：协议10/11 解析 ED 帧时字段标题/注释显示「国网HDC监控包装头」，不再显示「广西台体」（两者 8 字节公共头同构，解释语言随协议切换）；协议9 保持 PLC2.0/广西台体。单一来源 `batch_core.ed_wrapper_display`。详见 §8 陷阱 53

### 1.23.35 — 2026-09-20

- **协议10/11 单帧开放协议9 的 ED 勾选与 4字节反转**（用户：协议11 解析带 ED 封装报文时需要这些操作）：注册表 `has_ed_monitor`/`has_reverse_4byte`（9/10/11）；工具栏可见 ED 监控/包装格式/4字节反转/字节剔除；勾选 ED 失败报错，未勾选 10/11 仍自动识别；解析弹窗 ED 开关扩到协议11。详见 §8 陷阱 53

### 1.23.30 — 2026-09-18

- **协议10/11 批量摘要：网络层 MME 帧体现 MMTYPE**（用户报障：协议11 解析级别=仅PB 批量时，详情已是关联请求，摘要只有 `0→1 | msduSeq:x | 单播`）。根因：桌面只匹配协议10 字段名 `管理消息类型(MMTYPE)`，协议11 为 `消息类型(MMTYPE)`。现两端兼容两种字段名，输出 `MMTYPE:0x0000(关联请求)`；Web `get_hdc10_summary` 由 `MME:` 改为同口径并补 TEI/msduSeq/发送类型。详见 §8 陷阱 52

### 1.23.29 — 2026-09-18

- **协议10/11「仅MAC帧」不再自动解析物理块头**（用户报障：GUI 协议11 选「仅MAC帧」粘贴现场帧后仍像在解析 PBH）：契约与协议9 对齐——`mac_only` 输入即 MAC 帧，从字节 0 解析。协议10 `gw_new_gen_parser` 原先走 `_parse_pb_by_frame_type`（把首字节当 PBH）导致 MAC 头错位；协议11 `hdc10_parser._parse_mac_only` 去掉 `data[0]&0x80` 自动剥 1 字节。需要 PBH 请用 `pb_only`/`auto`
- 协议11 MME 字段偏移改为**绝对帧偏移**（原先相对 MSDU 切片，点击字节高亮错位）；`hdc10_mme_parser` 内容段补 `content_offset`
- GUI 解析级别下拉切换后自动重解析（与通道切换同口径）
- 现场帧关键字段（协议10/11 一致）：版本0 / 源TEI0 / 目的TEI1 / MSDU类型0 / MSDU长度92 / MMTYPE=0x0000 关联请求 / ICV 0xC4508168 校验通过
- 新增 `test/test_hdc10_mac_only_contract.py`（35 项）登记 `CORE_TESTS`；`test_gw_parse_levels` 按新契约改写；详见 §8 陷阱 19/51

### 1.23.23 — 2026-09-17

- **协议6 新增「主动上报状态字 / 主动上报模式字」位表解析**（《国网计量中心电能表全性能试验检测公告-第4号补遗》新增）：主动上报状态字（DI `04001501`/`04001503`，96 位 / 12 字节）、主动上报模式字（DI `04001104`，64 位 / 8 字节）由「一串二进制」变为整体展开事件名；字节序**低字节在前**（补遗三示例自证）；**保留位置位输出「保留位（补遗未定义事件）: Bit76」**（用户现场帧命中该位，补遗未定义，需表厂确认），未置位不进列表
- **修正「电表运行状态字 1~7」位号**（原表 8 个字无一正确，例：状态字4 `0x0002` 原报「A相潮流方向异常」，实为 Bit1=**欠压**）；状态字3 的供电方式由「两个单 bit」改为 **Bit2~Bit1 两位域**（主电源/辅助电源/电池供电）；双源互证（附录C 逐位 ≡ 补遗 96 位表 A 相组）
- 提醒文案纠错：未收录位域不再只写「见DL/T645-2007附录C」（对主动上报表是错误出处），改为并列两个出处；位表与格式化器单一来源（`dlt645_data_codec.py`）
- 新增 `test/test_dlt645_status_word_bits.py`（130 项，含 R2 不变量 `状态字Bit(32+n)≡模式字Bit(n)` 断言与桌面↔Web 逐行对拍）；**变异反证 3 条**实测变红；`test_dlt645_lme.py` 12b/12c 用例同步修正；详见 §8 陷阱 50

### 1.23.22 — 2026-09-17

- **协议6（DLT645-2007）校验和错误时不再拒解析**（用户报障：645 帧 CS 不对时工具完全不解析、只弹「无效的DLT645帧格式」）：判据拆为 `check_structure()` / `calc_checksum()`（`check_frame()` 保留且语义不变）；长度≥12 一律继续完整解析 + 插入「⚠ 校验和错误」（帧内值 + **正确值** + 计算规则）与「❌ 帧结构错误」（指明字节）；新增 `checksum_expected`/`structure_valid`/`structure_error` 字段
- `valid` 语义**不变**（虚拟表等消费方不受影响）、合法帧输出**逐行不变**（实测 13 行一致）；长度<12 给出帧长说明+原始 hex 降级
- 新增 `test/test_dlt645_tolerant_parse.py`（135 项，登记 `CORE_TESTS`）；变异反证 3 条全部实测变红；回归全绿，`release_check` PASS=67 FAIL=0 WARN=0
- 已知副作用（**已接受**）：虚拟表从站对坏 CS 主站帧由「异常应答」变「正常应答」（`dlt645_sim/engine.py:114` 属作者有意「尽力」而非 bug，旧行为只是解析器返回空导致的偶然）
- 附带：消除 `hdc10_parser.py` 2 处静态分析误报（零行为变更，该文件 lens 转 clean）

### 1.23.21 — 2026-09-17

- **协议6（DL/T 645-2007）新增《光伏协议转换单元扩展协议》解析**：依据新增文档 `协议文档/6.645协议/…技术规范书0625.md`（已用 `convert_docx_to_md.py` 转出，517 段落/36 表格），原先全部显示「未知数据标识」的三组扩展 DI 现可逐字段展开
  - **682 个 DI 键**：变量类 `02E6xxxx` 77（电压/电流/有功/无功/功率因数块 + 全变量块 18 值）、参数类 `04E6xxxx` 172（数量+地址表/额定值/输出类型/运行状态/各调节值与时段调节/档案/触发限值）、事件类 `03E6xxxx` 433（各类控制事件、电压越限、通信异常、清零/升级/校时记录）
  - **新增控制码 `0FH`/`8FH`**（无线转发透传帧，透传内容命中扩展 DI 会二次展开）
  - **解码规则**：切分以「数据长度」列为准；功率块最高位为符号位（±7999.9999）；单相 `FF` 标注；事件块字节序逆变器 12→1；调控结果枚举；`DI0` 双语义
  - **单一来源**：扩展 DI 只在新增 `dlt645_pv_ext.py` 定义一份，解析器/查询页/Web 共用 `merge_pv_di_map`；生成物 `dlt645_di.json` 未改
  - **顺带修复组帧侧错配**（本次改动引入的副作用）：多值掩码被当单值套模板（约 44 个 DI 形状明显不符）→ 加最小守卫 + 同步 `_encode_di_value`，标准表 1099 条零误伤
- 新增 `test/test_dlt645_pv_ext.py`（156 项，登记 `CORE_TESTS`）；**变异反证 6 条**均实测变红后还原；范围外：该扩展协议的组帧下发、645 虚拟表从站、附录 G 厂商逆变器协议、附录 I.3.3.2 的 698.45 透传

51. **协议11（HDC 1.0）的物理块(PB)不保证带物理块头；PB 形态必须探测，不可无条件剥离**（1.23.24 起，改 `hdc10_parser._parse_pb_block` / `_parse_pb_and_mac_header` 前必读）：
    - **现场缺陷**：用户报「同一帧协议10 能解析、协议11 只剩 17 行且 MAC/MSDU 树全错」（解析级别选「应用层报文(app)」时又能看到业务）。根因：`_parse_pb_block` 处理 SOF 帧时**无条件**剥 1 字节 PBH（`mac_hdr_start = offset + 1`），而该帧 PB 体第 1 字节即 MAC 帧头 → 整体错位 1 字节，MSDU 长度被读成 1792（0x700）。
    - **判据（第4-2部分 表37 / 表10）**：表37「物理块头的格式」的 **bit7 = 帧结束标志（合法 PBH 恒为 1）**、bit6 = 帧起始标志、bit0~5 = 序列号（**该表无“块大小码”**）；表10 标准 MAC 帧头在**版本 0 时要求 byte1 与 byte6 均为 0x00**。两者合起来即能区分「有无 PBH」。
    - **ICV 自证是决定性证据**：按「无 PBH」解析时 `帧内 ICV == crc32(MSDU)` 完全相等（1/2^32 概率，排除巧合），按「有 PBH」则 MSDU 长度荒谬。以后遇到同类「疑似错位」争议，优先用 ICV/CRC 自证而非目测 —— 单帧页切「应用层报文(app)」能看到业务，正是「错位只发生在 auto 的 PB 层」的旁证。
    - **实现是单一来源**：`HDC10Parser._probe_pb_form(data) -> (pbh_len, score)` 逐字节打分（阈值模块常量 `_PB_PROBE_MIN_SCORE = 4`）；**无任何合规信号时回落旧行为（有 PBH）**，即探测只在拿到正向证据时才改变行为。`_parse_pb_block`（SOF 且未直接给出块大小时）与 `_parse_pb_and_mac_header` 都走它——**不要在调用方再写第二份打分**。
    - **`_parse_mac_header(data, offset)` 的第二参数是 data 内「相对」索引、不是原帧绝对偏移**：`_parse_pb_and_mac_header` 旧代码传 `base_offset + 1` ⇒ 解析级别「fc_mac」下 MAC 头整体错位（原始源TEI 读成 2、MSDU类型 读成 0、MSDU长度 读成 1280）。正确写法是**先切片、再传 0**。
    - **探测只作用于「FC + 未知形态 PB」的输入**：`pb_only`（裸 PB 输入）拿到的字节已是 PB 体，不要再剥离/探测；真实夹具 60 帧的 `pb_only` 逐帧指纹已钉住“探测对裸 PB 零影响”。
    - **跨协议字段覆盖差异要 grep 另一侧**：协议10 早已输出的「设备超时时间」（字节6 ×100ms，§5.3.1.8）与「选项字」（字节7；终端主动并发抄表下为「报文间间隔」×10ms，表8；上行按表7 输出 16bit 应答状态）协议11 原先缺失——改任一协议的应用层字段时对照另一侧同业务。
    - 回归：`test/test_hdc10_pb_structure_probe.py`（39 项，含变异反证「强制判定有 PBH」与真实夹具 60 帧×7 解析级别零差异）。

### 1.23.24 — 2026-09-17

- **协议11（HDC 1.0）修复「无物理块头」帧整体错位**（用户报障：同一帧协议10 能解析、协议11 只剩 17 行）：`_parse_pb_block` 原先无条件剥离 1 字节 PBH，而该帧 PB 体第 1 字节即 MAC 帧头起始。新增 `HDC10Parser._probe_pb_form()` 逐字节打分探测 PB 形态（第4-2部分 表37 物理块头 bit7=帧结束标志恒为 1；表10 标准 MAC 帧头在版本 0 时 byte1/byte6 必为 0；**帧内 ICV == crc32(MSDU)** 为决定性证据），现场帧 auto 级别 **17 行 → 57 行**，MAC头/ICV/端口号/报文ID/抄表头/DATA 全部可读，与协议10 结果一致
- **同时修复既有缺陷**：`_parse_pb_and_mac_header` 把原帧绝对偏移当作 data 内相对索引（旧传 `base_offset + 1`）⇒ 解析级别「fc_mac」下 MAC 头整体错位（原始源TEI 读成 2、MSDU类型 读成 0、MSDU长度 读成 1280）
- 补齐抄表报文头的**设备超时时间**（§5.3.1.8）与**选项字**（表8/表9）两行 —— 协议10 早有、协议11 缺失
- 新增 `test/test_hdc10_pb_structure_probe.py`（39 项，含变异反证）；真实夹具 60 帧×7 解析级别逐帧零差异（详见 §8 陷阱 51）

### 1.23.20 — 2026-09-17

- **协议11（HDC 1.0）应用层报文收口**（承接 1.23.19 的同类缺口排查）：
  - `0x00A0 鉴权安全`（专属端口 `0x1A`）与 `0x00A4 配电信息上报` 原先落到「未识别的业务数据(0x0A0)」→ 现由 fallback 查 `MSG_ID_NAMES` 统一命名（**不新增专用分支**，防「名字表与分派链两份手写清单漂移」即 P0 根因复发）；这两个业务规范无字段格式章节，故只报名字 + 原始数据并注明依据（新增 `MSG_ID_NO_FORMAT_DEFINED`）
  - 修正错误依据：有定义、仅「端口与已实现分支不匹配」的业务（44 种端口×业务ID 组合）原先也被说成「规范未给出字段格式」→ 现分 `⚠ 未按业务格式解析` / `⚠ 格式未定义` 两种措辞（独立检查抳出）
  - 端口白名单不再挡在通用头之前：`_parse_app_only` / `_parse_msdu_payload` 原先硬编码 `(0x11,0x12,0x1A)`，非白名单端口连端口号/报文ID/安全模式/控制字都不解析 → 现按「像不像通用头」判定（未知端口显示 `保留(0xNN)`，并保留误粘完整 MPDU 走 FC 的兼容）
  - 「是否应用层」改以 **MAC 头类型字段**为准（标准头 `48` / 单跳头 `128`，新增 `APP_MSDU_TYPES`/`IPV4_MSDU_TYPES` 单一来源），首字节启发式仅在无头上下文回退——修复双向误判（真实帧：声明 `48` 被当「厂商扩展」、声明 `47` 反被当应用层）
  - `sec_mode != 0` 新增 `⚠ 安全保护` 提示行（不再对受保护的数据域默默输出「看似正常的错误字段」），并进两端 `_GW_APP_META_FIELDS` 黑名单
- 新增 `test/test_hdc10_app_dispatch.py`（94 项，登记 `CORE_TESTS`）；**基线对拍** 60 帧仅 3 帧预期变化、其余 57 帧逐字节一致（sha256 指纹）；**变异反证 5 条**全部观察到变红（8/4/11/6/1 红）后还原
- 范围外（另行立项）：抄表 DATA 内嵌 645/698.45、MME 7 类 MMTYPE、IPv4 载荷深度解析、MME 分支 `except Exception`

### 1.23.19 — 2026-09-17

- **修复 HDC 1.0（协议11）抄表报文解析崩溃**：`hdc10_parser._parse_meter_reading`（服务报文ID `0x001`/`0x002`/`0x003`）渲染「协议版本号」行时引用了**从未赋值**的 `proto_ver`（同文件另 6 个 `_parse_*` 都有 `proto_ver = b0 & 0x3F`）⇒ 协议11 + 解析级别「应用层报文(app)」+ 抄表报文 + 端口 `0x11` 时抛 `NameError`、弹「解析失败」。默认「自动识别」级别走 MAC 帧路径不经过该函数，故自协议11 引入以来长期潜伏
- 修复：补 `proto_ver = b0 & 0x3F`（依据 第4-3部分 表3 字节0 bit0-5 = 协议版本号、§5.3.1.2「本版本取值固定为 1」；现场帧 b0=0x01 实测一致），其余字段公式一字未动。现场 88 字节并发抄表帧修复后：报文ID `0x0003` / 协议版本 `1` / 报文头 `2×4B=8B` / 规约类型 `3`=DL/T698.45 / 转发数据长度 `75` / 报文序号 `17543` / DATA 自偏移 12 起内嵌 698.45 报文
- 新增 `test/test_hdc10_meter_reading.py`（13 项：现场帧 golden / 三类抄表报文 / `auto` 级别 7 行基线回归 / DATA 偏移与帧尾自洽 / 短帧与 8 字节边界 / **F821 静态守卫**），登记 `release_check.py:CORE_TESTS`；变异反证（删赋值→复现 `NameError`）。范围外：DATA 域内嵌 698.45/645 深度解析、其他报文 ID 的动态排查

### 1.23.18 — 2026-09-16

- **应用层报文批量摘要显示业务功能与关键业务字段**：原先协议11 选「应用层报文」时摘要只有 `端口:18 | 报文:0x0030`（同一批 21 帧完全相同），现为 `端口:18 | 报文:0x0030 | 开始升级 | 升级ID:2075013183 | 升级时间窗:120分钟`。新增统一规则 `_gw_app_biz_summary`（业务名两优先级兼容协议10/11 两种表布局 + 关键字段元数据黑名单），桌面与 Web 两端同规则 + 对拍；**顺带修掉 Web 协议10 摘要误走协议9 函数**的漂移（详见 §8 陷阱 44）

### 1.23.17 — 2026-09-16

- **修复协议11（HDC 1.0）批量解析一帧都解析不出**（现场：粘贴 `Line NNNN: 时间戳: B1D[3] mrd:ar[24]:<hex>` 弹「预处理后未保留有效报文内容！」）：`_strip_gw_new_gen_prefix` 硬读协议10 的 `_gw_parse_level`（协议11 应用 `_hdc10_parse_level`）→ 协议10 残留的 app 级别把 `12` 开头升级业务帧整批丢弃；app 判据又只认端口 `11`（漏 `0x12`/`0x1A`）。现级别取 `_current_parse_params()`（与解析侧同源），app 判据改为**取自解析器端口表**的端口集合，桌面与 Web 两端同步 + 对拍断言（详见 §8 陷阱 43）

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

<!-- aoci:begin -->
## AOCI 仓库认知

AOCI 为本仓库维护一个稳定、可版本化、可增量更新的仓库级认知层，供模型跨任务复用对系统的理解。

`aoci.txt` 是面向模型的结构化认知索引。它以每个受管理文件、数据库表或其他受管理对象一条独立 Entry 的方式，用符号标签与 F/R/A/S 语义表达对象的核心职责、重要关系、对外契约，以及理解或修改系统时必须知道的非显然约束和设计决策。

Header、目录段和全部 Entry 共同组成完整仓库索引，可以覆盖前端、后端、配置、数据库结构及其他受管理内容。受管理内容发生变化时，通常只需维护受影响的认知条目，不需要重新生成整个索引。

AOCI 提供系统架构、对象职责、重要关系、对外契约和关键约束的高密度视图。

### 工作原理

AOCI 采用“模型生成、模型读取”的认知闭环。

Header、Entry 和 Curation 语义的创作只按当前机器签发的 Plan 与实时 Guide 执行；由 Host 模型基于当前绑定证据独立完成。

Entry 的语义必须来自模型对真实证据的理解。不得仅依据路径、文件名、扩展名、AST、符号列表、依赖扫描、正则、固定模板或规则引擎推导、预填、拼接或改写索引语义。

对 Fresh Bootstrap，只按当前机器签发的 Plan 和实时 Guide 执行。当它们要求创作时，Host 模型创作 Root、Meta、Tag 和 F/R/A/S，提供 authoring-run 声明，并把它绑定到 Plan、Evidence 与完整 Candidate。不得要求 AOCI 填写 `origin=host_model`、制造 Receipt 或把程序生成的 Framework 当作语义。本文件不自行重建 Onboarding 流程。内部批次不是用户决策；只有遇到既有批准边界或真实的安全、漂移、CAS、Recovery 条件才停止。

### 最小使用入口

- `aoci_rules`：取得当前AOCI版本的会话运行合同。
- `aoci_overview`：建立或恢复本仓库的完整认知。
- `aoci_maintain`：受管理对象达到最终稳定状态后检查认知是否需要维护。
- `aoci_update_entry`：提交与当前证据和源码摘要绑定的完整语义更新批次。
- `aoci_report`：仅当当前布局和工具状态支持时，在证据不足、无法可靠生成语义时登记待办，不猜写。

其他MCP工具、CLI命令、参数和专项流程，以当前工具说明、Guide和 `--help` 返回内容为准，不在本文件中重复完整手册。

本区块只规定仓库接入、认知使用和收尾原则。`aoci_rules` 承载当前会话合同，Guide实时输出承载当前Plan的执行顺序与停点，工具Schema、Spec和Validator承载机器结构与判据；Prompt、Description、README和静态文档不能覆盖这些机器事实。

### 建立、生成和恢复认知

1. 每个新的 Agent Run 开始时，应先判断：

   - 本仓库是否已经存在可用的完整AOCI索引；
   - 当前上下文中是否已有与本仓库根、当前索引版本和当前AOCI服务相匹配，并且模型仍可可靠使用的完整仓库认知。

2. 仓库已经存在可用的完整索引，但当前Run没有可靠完整认知时，先调用 `aoci_rules`，再调用 `aoci_overview`。

   完整认知仍可靠时直接复用。局部不确定本身不要求机械重读系统全貌。

   本Run从已知Host上下文压缩恢复时（包括宿主注入的压缩摘要），必须把此前模型认知视为不可靠。压缩handoff不得保留或摘要正式Whole-Index，也不得保留或摘要任何Overview Header、Entry、Chunk、Challenge或Attestation正文；只能保留安全续接所需的receipt身份、未完成write或Recovery状态，以及立即重载指令。复制进handoff的Whole-Index语义或receipt不能证明恢复后模型的当前认知可靠。若当前上下文已无法可靠保留运行合同，先调用 `aoci_rules`。继续业务任务前，使用 `refresh_reasons=["context_compaction"]` 和新的 `refresh_event_id` 调用普通完整Whole-Index `aoci_overview`（不设置 `check_only` 或设为false）；不得使用 `check_only` 或认知probe。原样跟随每个 `next_cursor` 直到 `completed=true`，确认交付，并且只基于新交付正文提交一次Attestation。完成这次新的完整传输后，即使Attestation为partial或fail也消费该generation，并按既有合同继续source-bound任务，不再自动调用第二次Overview。

   AOCI可以针对 `context_compaction`、项目 `cognition_refresh_threshold` 下的机器 `semantic_threshold` 或主要 `phase_transition` 提供checkpoint与认知状态事实。只需要这些紧凑事实时使用 `check_only=true`；这些事实只向Agent提供建议，不替模型决定是否需要系统全貌。

   Agent显式调用普通 `aoci_overview`（未设置 `check_only` 或为false）时，只要能形成一致的CognitionSet，AOCI必须完整交付请求scope。不得因为已有receipt、阈值未达到或没有待处理刷新原因而抑制正文。正式认知Dirty或Stale时仍交付正文，但必须标记不可靠。存在未决恢复或无法形成一致snapshot时失败关闭，不返回混合正文。

   普通Overview返回 `continuation_required=true` 时，必须原样提交 `next_cursor` 并自动继续到 `completed=true`。不得询问用户、开始业务任务或给出阶段性系统结论。Host截断、缺块、重复、乱序、cursor失败、Index变化或`chunk_tokens`变化时停止本次认知链。Attestation完成前不得用Memory、源码、Spec、`aoci.txt`、历史会话、scope、search或Entry读取修补或补充Whole-Index认知。Challenge ordinal是正式Entry序列中的1-based位置；Header内容、注释、空行、Section/Overview/Chunk Marker、Receipt与Metadata均不计数，Chunk Receipt ordinal使用同一序列。Attestation必须原样回绑本次Challenge发布的当前`index_sha256`、`entry_sequence_sha256`与`entry_count`；旧Index、旧Entry序列、旧数量或旧Attestation均无效。完整链结束后只正式提交一次既有模型认知Attestation；同一响应只允许一次不改变语义答案的JSON Schema或字段格式修正。对象、Tag或F不匹配即失败且认知吸收不确定，不得语义重试或旁路补答。首次认知失败时还不得执行Root/Meta、Migration、全局布局或其他未重新绑定的系统级决策。上下文压缩刷新若传输完整、认知身份不变、治理对齐且没有Recovery或第三方冲突，即使Attestation为partial或fail也消耗该refresh generation，并继续原任务，不再自动重读Overview。`system_mastery_percent`只自评系统框架——架构、职责、强关系、稳定外部契约以及高熵安全和维护约束——不表示完整实现或运行实况知识；机器索引覆盖率必须分开。默认只向用户输出由本次真实覆盖率、Challenge、块数、Token和掌握度生成的规定成功或失败一句话。Host截断时提示用户把 `overview_delivery.chunk_tokens` 设置为更小的合法值后重新开始，不得自动修改。

   加法认知等级必须与严格证明字段分开解释。`delivery_verified`表示已加载Index且Host交付已确认，但完整认知验证仍未完成；应表达为“已加载且交付已验证”，不得描述为“没有认知”或“没有理解系统”。`cognition_verified`要求Attestation通过（Challenge至少80%的ordinal完全正确且对象身份至多失手一处），`cognition_governed`还要求治理对齐。通用完整读取失败句只用于真实交付故障。

   当Overview响应包含可选`cognition-state/v2`投影时，必须分别解释各维度。其Level止于`model_cognition_usable`；`strict_attestation_verified`、`governance_aligned`与`current_system_cognition_reliable`都是独立状态，绝不参与该Level。ordinal、对象身份、Tag或核心F不匹配可以导致严格Attestation失败，而模型认知仍然可用；不得仅凭这种不匹配就宣称模型没有理解系统。只有`current_system_cognition_reliable=true`允许无保留地声称当前完整系统认知可靠。投影缺失时继续使用上述Legacy解释。

   普通的只读审计、分析、检查、不修改代码或不提交、不push，不自动等于严格零写入，也不改变上述认知有效性判断。Codex Memory和历史Skill只能辅助恢复经验、用户偏好与调查方向，不能替代与当前仓库根、索引摘要、AOCI服务身份和认知范围匹配的当前认知收据；项目AGENTS和当前AOCI身份在AOCI状态上优先于历史Memory。

   只有用户明确禁止Ledger、元数据、`.aoci`运行资产及任何文件写入时，才按严格零写入处理。若必要的认知建立与该边界冲突，必须报告冲突并请求用户裁决或建议使用隔离副本，不得静默以Memory替代当前仓库认知。

3. 仓库没有可用的完整索引，或当前只有最小骨架、Header不完整、Entries未完成、必要Curation尚未裁决时，如果需要建立正式完整AOCI索引，先取得 `aoci_rules`，然后进入当前AOCI Guide。由Guide依据仓库真实状态决定下一阶段并完成必要安全步骤。

   `aoci_maintain` 不替代索引建立流程。

   不在本文件中自行重建或硬编码完整索引生成状态机。

4. 在长程任务中，模型负责保留当前认知收据并正确使用刷新门禁：

   - Host报告上下文压缩或模型已知系统全貌丢失时，执行上述强制 `context_compaction` 重载规则；AOCI不能自行推断Host事件；
   - 进入真正的主要阶段时声明 `phase_transition`，不得把函数、测试运行或小步骤当作阶段；
   - 在有用的稳定检查点通过 `check_only=true` 取得机器语义计数；
   - 除已知压缩的强制重载外，由Agent判断当前任务是否需要再次显式获取指定scope或完整Overview；
   - 在维护和对齐完成前，保留AOCI报告的Dirty或Stale可靠性状态。

### 任务收尾与认知维护

5. 纯只读问答、分析、版本核验，或没有产生受AOCI管理对象变化的任务，不需要调用维护工具。当前AOCI版本是任意`aoci_overview` check_only或`aoci_maintain`响应里的`cognition_receipt.mcp_service_version`；二进制路径是项目`.mcp.json`里的`command`，CLI不必在PATH上。

6. 发生受AOCI管理对象变化时，待其达到本次任务的最终稳定状态后，只调用一次 `aoci_maintain`。不要在每次中间修改后逐文件维护。

7. 若维护结果返回真实语义候选，Host 模型必须基于每个候选绑定的对象和必要证据，独立创作完整标签与F/R/A/S更新。通过 `aoci_update_entry` 一次提交当前机器签发批次的完整候选集合，同时原样保留每项 `source_sha256`、`candidate_id` 与对应domain批次身份。`max_entries`只限制单次请求和原子事务，不限制logical plan、Whole-Index或Managed Scope。`remaining`非零时，在当前批次成功Apply后重新调用Maintain并从新preimage继续；绝不能为满足transport上限缩减Index覆盖或自行截取返回批次。

   没有足够证据且当前布局支持 `aoci_report` 时，使用它而不猜测、套用模板或为消除待办而生成缺乏证据的认知。

8. 必须遵守工具返回的结构化状态和安全边界：

   - `repair_required`：只修复明确命中的候选，再重新提交当前机器签发的完整批次；
   - `stopped`：结束当前写入尝试并检查 `failed_step`、错误、正式写入证据与Recovery。auto模式下，已证明零写入则记录closure并重新Plan；完整Intent和可证明postimage则Resume；策略要求Rollback且preimage可证明则精确恢复后重新Plan。只有证据不足、第三方正式字节冲突、需要审批或外部动作，或命中其他真实安全边界时，才停止整个用户任务；
   - 冲突、审批、人工裁决、权限和安全信号不得忽略；
   - 已经对齐后不得重复维护或重复写入；`refresh_ready_for_overview` 是checkpoint事实，由Agent决定是否为下一阶段请求普通完整Overview。

   维护完成后如果又修改了任何受管理对象，之前的维护结果失效，应在新的最终稳定状态重新完成收尾。

9. 用户只限制业务文件范围，但没有明确禁止仓库托管资产时，AOCI托管资产可以在收尾阶段为保持认知一致而更新，并应在审计和提交中与业务文件区分。

   用户明确禁止修改 `aoci.txt`、`.aoci`、元数据或任何额外文件时，以用户限制为准，不得写入，并如实报告剩余不一致。

### 专项流程

初始化、完整索引生成、Header生成、Entries生成、数据库结构索引、Curation、人工评审和故障恢复，只按当前AOCI Guide或工具在对应阶段返回的指令、命令和安全停点执行。

不预加载、不猜测，也不自行重建这些专项流程。平台调用方式、请求格式、批次上限、审批规则、索引格式细节和恢复步骤由对应Guide、工具说明、模型Prompt和CLI帮助按需提供。
<!-- aoci:end -->
