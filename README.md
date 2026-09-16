# 南网协议解析工具

[![Version](https://img.shields.io/badge/version-1.23.16-blue)]()
[![Python](https://img.shields.io/badge/Python-3.8%2B-brightgreen)]()
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()

一个面向电力通信现场调试的多协议解析工具，基于 Python / PySide6 开发，支持 12 种电力通信协议，覆盖单帧解析、批量解析、协议校验、帧生成、串口通信、虚拟表、通信时序图、测试方案、Lua 脚本、实时监控与 TCP 抓包等工作流。

当前版本为 `1.23.16`，版本号与编译日期见 `main_gui.py` 中的 `APP_VERSION` 与 `BUILD_DATE`。

## 功能总览

| 模块 | 说明 |
| --- | --- |
| 单帧解析 | 输入十六进制报文，按协议分层解析，点击解析行联动高亮输入框对应字节并自动滚动到位置 |
| 批量解析 | 从文件/剪贴板/pcap 导入多帧报文，自动提取完整帧，支持导出选中/全部、类型过滤与 JSON / CSV / Excel 导出；摘要列对**测试帧（业务标识 0xF0）**体现测试模式（如 `测试模式:PLC物理层透传测试模式(3)`）、测试ID、通信频段 |
| 原始报文定位 | 批量摘要表点击行可回跳输入日志对应行；右键「转到原始报文位置」弹出只读查看器并高亮该帧 |
| 协议校验 | 覆盖起始符、长度域、校验和与 CRC（含协议9逐 PB PBCS CRC-24），逐项展示通过 / 失败 / 警告 |
| 表格复制 | 解析结果、批量结果、监控器与 TCP 监控表格支持右键复制及 Ctrl+C |
| 帧生成 | 南网、国网、698.45、DLT645-2007 组帧模板，支持预设命令一键填充与解析回读 |
| 串口通信 | 串口参数配置、帧发送、实时接收解析与日志窗口 |
| 虚拟表 | 协议8（698.45）从站模拟器；协议6 另有「645虚拟表」：离线粘贴读请求生成响应、档案 DI 值、可选串口从站 |
| 通信时序图 | 协议9/10/11 批量结果一键生成 CCO⇄STA 序列图，与摘要表双向联动，可导出 PNG |
| 测试方案 | 测试项 CRUD、顺序发送、超时匹配、结果记录与 Excel 报告导出 |
| Lua 脚本 | 测试流程中嵌入可编程逻辑，支持条件分支、循环遍历、数据解析与变量共享 |
| 报文对比 | 双报文字节级 / 字段级对比，支持差异高亮、人话解读与报告导出 |
| 报文工具 | ASCII / HEX 转换、DLT645 偏移、字节逆序、Pn/Fn 转换、CRC/校验和计算 |
| 频谱图 | 按频谱仪参数（起止/中心/扫宽、RBW/VBW、参考电平、每格 dB、单位、检波方式）输入单条 trace 全部扫频点数值，绘制仪器式网格频谱图；支持光标读数、MARK 标记与两点 Δ（频段宽度/电平差）测量，可导出 PNG |
| LLM 预处理 | 批量解析可折叠面板，OpenAI 兼容 API 多轮清洗原始日志后再解析 |
| 实时监控器 | 南网新一代 / 国网新一代串口报文实时监控、自动组帧、过滤与 CSV 记录 |
| TCP 监控 | 基于 scapy 的 TCP 抓包、流重组与南网新一代 / 国网新一代自动识别解析 |
| 档案与拓扑 | 南网 / 国网协议档案导入导出、拓扑组网统计 |
| 查询页 | DI、AFN、DLT645 DI、OBIS、PLC RF 命令字、新一代业务标识、HDC 1.0 报文 ID、EB 数据标识查询 |
| 多端界面 | PySide6 GUI、实验性 Reflex Web |
| 主题与字体 | 5 套主题与字体设置，支持配置持久化；表格 Ctrl+滚轮缩放 |
| 系统集成 | 系统托盘、全局热键、快捷解析小窗、剪贴板报文检测、Notepad++ 集成、单实例、命令行解析、文件右键菜单与开机自启 |
| 问题反馈 / 报文分享 | GUI 与 Web 共用服务端库；单帧可「分享此帧」到 Web 报文分享页 |
| 自动更新 | 帮助菜单检查更新，可配置自动检查并选择版本下载 |
| 状态栏 | 本软件 CPU / 内存占用、线程数明细（可点击复制） |

## 支持协议

工具支持 12 种电力通信协议，下拉框索引即协议编号：

| 索引 | 协议 | 标准号 | 字节序 | 校验 |
| --- | --- | --- | --- | --- |
| 0 | 南网协议 | Q/CSG1209021-2019 | 小端 | 8 位位组算术和 |
| 1 | PLC RF 协议（万胜海外） | 万胜 V1_04 | 大端 | 累加和 & 0xFF |
| 2 | HDLC/国网DLMS | IEC 62056-46 | 大端 | CRC-16/FCS（CCITT） |
| 3 | DLMS-APDU（国网） | IEC 62056-46 | 大端 | 无 |
| 4 | DLMS Wrapper 裸报文 | IEC 62056-46 | 大端 | 无 |
| 5 | DLMS-APDU 裸报文 | IEC 62056-46 | 大端 | 无 |
| 6 | DLT645-2007 电表协议 | DL/T 645-2007 | BCD，低字节在前 | 累加和 & 0xFF |
| 7 | 国网协议 | Q/GDW 10376.2-2024（含福建增补 AFN 50H~56H） | 小端 | 8 位位组算术和 |
| 8 | 698.45 协议 | DL/T 698.45-2017 | 小端 | CRC-16（crcmod `x-25`） |
| 9 | 新一代载波协议（通感一体化） | 通感一体化宽带载波通信规约 | 小端 | CRC-32（MAC 帧）+ CRC-24（PBCS） |
| 10 | 国网新一代双模通信互联互通 | 国网新一代双模通信互联互通技术规范 | 小端 | CRC-32（MAC 帧） |
| 11 | HDC 1.0 双模互联互通 | Q/GDW 12087.42-2020 | 小端（MAC 地址大端） | CRC-24（FC/PB）+ CRC-32（MAC） |

> HDC 1.0（索引 11）目前仅在 PySide6 主程序支持；Reflex Web 版支持索引 0–10（11 种）。

## 快速开始

### 环境要求

- Windows 优先，支持 UTF-8 / GBK 中文路径
- Python 3.8+
- TCP 监控需要安装 `scapy`，Windows 下还需要安装 npcap

### 安装依赖

```bash
pip install pyside6        # GUI 必需
pip install crcmod         # 698.45 协议 CRC 校验（1.7.0 起）
pip install lupa           # Lua 脚本引擎（1.8.1 起，可选）
pip install openpyxl       # Excel 测试报告（可选）
pip install scapy          # TCP 流量监控（可选，Windows 需 npcap）
pip install reflex         # Reflex Web 版（实验性）
```

> `lupa` 未安装时 Lua 脚本功能不可用，其余功能不受影响；`scapy` 或 npcap 未就绪时，TCP 监控标签页会给出安装提示。

### 运行

```bash
# PySide6 GUI 版（主入口）
python main_gui.py

# Reflex Web 版（实验性）
python reflex_web/run_app.py
```

**局域网部署（Windows 服务器 · 固定端口）**：完整步骤见 [`docs/Web版局域网部署教程.md`](docs/Web版局域网部署教程.md)——含防火墙放行、开机自启（任务计划/NSSM）、备份与升级、排错表。构建时用 `--port <端口>` 把端口固化进启动脚本（默认 8080）。

**Web 路由（1.23.14 起）**：`/` = **产品首页**（介绍桌面客户端：Hero、功能卡、12 协议表、命令行/系统集成、下载入口、页脚；`reflex_web/reflex_web/landing_web.py`）；`/app` = **在线工具**（原主页的 9 个标签页，含单帧/批量/组帧/对比/查询/频谱图/报文工具/客户端下载/问题反馈）；`/share`、`/feedback`、`/feedback-admin` 不变。首页的截图/版本/体积读 `reflex_web/downloads/`（`client_screenshot.png`、`version.json`、`*.exe`），换图换版本无需改代码；缺图时降级为占位卡。

**Reflex Web 版组帧**：南网(0)/国网(7)/698.45(8)/DLT645(6) 四种协议组帧与 GUI 完全对齐——预定字段（uint/enum/bytes/ascii/bcd/oi/oad_list/list/sub_fields 按类型分派）、自定义模板（含校验和回填）、698.45 A-XDR 数据编辑器；实时回读解析预览；预设命令按钮（NW_command.json / GW_command.json / DLT645_command.json 等）一键填入与保存。启动前先编译前端：`cd reflex_web && reflex export --frontend-only --env prod --no-zip`，再 `python reflex_web/run_app.py`。

**问题反馈**：导航栏「问题反馈」入口（`/feedback`）——用户提交问题类型/涉及协议/描述/联系方式/截图（≤3 张）；管理员通过 `/feedback-admin`（复用发布管理口令）查看/标记状态/删除。数据存 `reflex_web/data/`（SQLite + 截图），**重新部署自动保留**，备份只需拷贝该目录。

**报文分享（1.21.0 起）**：单帧解析后点「分享此帧」（Web 主页或 GUI 按钮行），报文 + 协议 + 分享人 + 说明入库（frameshare.db，与反馈同一 data/ 目录、部署自动保留）。所有人可在 Web 导航「报文分享」页浏览与搜索（hex 支持连续无空格输入）；GUI 提交走 `POST /api/frameshare`，分享人自动记忆。管理员（复用反馈管理口令）登录后可在列表每条记录上点「删除」清理杂乱分享（1.21.1 起）。

**桌面端问题反馈（1.20.0 起）**：GUI 客户端「帮助 → 问题反馈(F)...」打开反馈对话框，提交到 Web 服务端 `POST /api/feedback`，与网页反馈**共用同一个数据库**——主页「问题反馈」Tab 统一查看，桌面端来源的记录带「桌面端」徽章并附客户端环境信息。反馈服务器地址在对话框内可改（默认 `http://127.0.0.1:8000`，持久化到 `config.json` 的 `feedback.server_url`）。

### 部署到目标机器

有两种方式将 Reflex Web 版部署到没有 Python 环境的目标机器：

**方式一：内嵌 Python（推荐，零安装）**

构建包含 Python 运行时的部署目录，目标机器无需安装 Python，解压即用：

```bash
python reflex_web/build_embedded_deploy.py --python-version 3.12
# 输出: dist/reflex_web_embedded/
```

把 `dist/reflex_web_embedded/` 整个目录复制到目标机器，运行 `start_web.cmd`（Windows）或 `./start_web.sh`（Linux）即可。

**日常迭代构建（推荐）：** 源码/依赖几乎不动时，用增量模式只刷新源码层，复用已有内嵌 Python 与依赖，
避免每次重新下载解释器 + 重装依赖（完整耗时 10+ 分钟 → 增量约 1 分钟）：

```bash
python reflex_web/build_embedded_deploy.py --skip-deps
```

仅首次构建、改依赖或换 Python 版本时才需要去掉 `--skip-deps` 完整重建。

**方式二：UV 虚拟环境（需要目标机器有 Python）**

构建依赖虚拟环境的部署目录，目标机器需要安装相同版本的 Python：

```bash
python reflex_web/build_offline_deploy.py --python-version 3.12
# 输出: dist/reflex_web_offline/
```

详细说明见 [`reflex_web/离线部署.md`](reflex_web/离线部署.md)。

### 打包 exe

项目当前提供 `南网协议解析工具.spec`，打包时请先确认 `main_gui.py` 中的 `BUILD_DATE` 已更新为当前日期：

```bash
pip install pyinstaller
pyinstaller 南网协议解析工具.spec --noconfirm
```

生成的 exe 位于 `dist/`，文件名自动带版本号与时间戳，例如 `南网协议解析工具_v1.23.0_20260910120000.exe`。新增需打包的数据文件时，需要同步检查 spec 的 `datas` 配置。Reflex Web 版另有 `reflex_web/reflex_web_exe.spec`。

> 当前主程序 spec 未显式声明 `scapy`。如需将 TCP 监控功能打包进 exe，请先在 `南网协议解析工具.spec` 中补充 `scapy` 相关 hidden imports，并确保目标机器安装 npcap。

## 使用说明

### 单帧解析

1. 顶部下拉框选择协议类型
2. 在「输入报文」文本框粘贴十六进制报文（支持带空格 / 无空格混合）
3. 点击「解析报文」
4. 下方表格显示分层解析结果，点击解析行会高亮输入框中的对应字节并自动滚动到该位置

解析 HDLC 帧后，可双击 `DLMS APDU` 行打开深度解析窗口，支持 Get / Set / Action 等 APDU 类型与 BER-TLV 递归解析。

国网新一代（索引 10）与 HDC 1.0（索引 11）可选择解析级别（自动识别 / FC+PB / 仅FC / 仅MAC / 仅PB / FC+MAC / 应用层）与通道（PLC 载波 / HRF 无线）；新一代载波（索引 9）另支持 FC+eFC 级别与 ED 监控包装剥离。ED 包装头格式支持「自动识别(推荐) / PLC2.0 台体 / 广西台体(14字节头)」。

解析成功后可点「分享此帧」，把有价值的命令帧分享到 Web 服务端报文分享库。

### 批量解析

切换到「批量解析」标签页：

- 从文件加载或剪贴板粘贴
- **导入 pcap**：离线读经典 `.pcap`（零依赖）/ `.pcapng`（需 scapy），TCP 流重组后自动批量解析——PLC2 监控帧 / 业务帧 / 原始 TCP 负载三模式，接「按类型全选 → 时序图」
- 自动从混杂文本中提取完整帧
- 摘要表支持 Ctrl/Shift 多选，「导出选中」只导出目标子集；「按类型全选」可一键选中某类型全部帧
- 点击摘要行可在输入框回跳并选中对应报文行
- 右键「转到原始报文位置」弹出只读查看器（行号 / 高亮 / Ctrl+F 搜索），查看导入时的原始日志快照
- 新一代载波协议支持监控日志前缀剥离与业务摘要；ED 包装头可选 PLC2.0 / 广西台体 / 自动识别
- 国网新一代 / HDC 1.0 支持日志前缀剥离与业务摘要

批量解析工具栏另有「LLM 智能预处理」可折叠面板：配置 OpenAI 兼容 API 后，可对原始日志做多轮智能清洗再解析（内置提取 hex、清理前缀、按协议分类等模板，大文件自动分块异步执行）。

### 通信时序图

批量解析协议 9 / 10 / 11 后，点工具栏「时序图」或切换到「通信时序图」标签页：

- 节点按 TEI 自动判别（TEI=1 为 CCO 固定最左，其余 STA 按首现排序）
- 信标/SACK/应用层广播画虚线，单播画实线；支持台体发射机、未入网站点、阶段分隔线
- 滚轮缩放、拖拽平移、「适应窗口」、「导出 PNG」
- 点击图上消息跳回批量解析页定位对应帧行；反向选中摘要表行时图上对应消息高亮
- 摘要表有勾选行时仅用勾选帧生成，否则使用全部帧

### 虚拟表（协议 698.45 / DLT645）

**协议 698.45「虚拟表」**

「虚拟表」标签页仅在协议 8 下显示，提供 698 从站模拟：

- **离线模式**：粘贴主站请求帧，自动生成响应帧并解析回读，可一键送入单帧解析器
- **串口从站模式**：独立选择串口参数，持续监听 `68...16` 请求帧并自动组帧回复（建议配虚拟串口对）
- 支持 GET Normal/NormalList/Record、链接请求、SET/ACTION 成功 DAR、安全明文封装
- 档案数据（`meter_sim_data.json`）可在档案页增删改、JSON 导入导出；多表通配、黑/白名单、电能递增、冻结漏点等可配置

**协议 6「645虚拟表」（1.23.5）**：

- 离线：粘贴主站读数据请求 → 生成 `91H` 应答（未知 DI 回异常 `D1H`）
- 档案页编辑 DI→值（`dlt645_sim_data.json`）
- 可选串口从站自动监听回复（虚拟串口对）

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

TCP 监控支持流关注、表格复制、暂停刷新、CSV 实时记录与历史 CSV 加载。首次打开标签页时 scapy 在后台惰性加载，不阻塞主界面。

### 系统集成与命令行

GUI 版提供 Windows 系统集成能力：

- 关闭主窗口默认最小化到系统托盘，托盘左键单击可显示 / 隐藏主窗口
- 全局热键默认 `Ctrl+Alt+X`，复制十六进制报文后按下即可弹出**快捷解析小窗**（uTools 风格悬浮面板，实时解析 + 徽章 + 完整字段树；Esc/再按热键/失焦隐藏；「在主窗口打开」转入完整视图）
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

「协议组帧」与「预设命令」标签页在协议 0（南网）、协议 6（DLT645-2007）、协议 7（国网）与协议 8（698.45）下显示：

- 按字段模板填写参数
- 支持预设命令一键填充
- 生成帧后可直接通过串口发送，也可解析回读闭环校验
- 协议 6 支持主站请求 / 从站应答 / 异常应答三组命令，DI 由数据字典驱动并按 data_type 掩码自动推导字段表单

### 频谱图

「频谱图」标签页把频谱仪屏幕上的参数与 trace 数值画成图（常驻显示，与协议无关）：

- 参数区：起始/终止/中心/扫宽四字段**双向联动**（改任一项自动重算其余，按回车或移开焦点生效），可切换 kHz/MHz/GHz；另有 RBW、VBW、参考电平、每格 dB（0.1~20）、纵向格数（4~12）、幅值单位（dBm/dBμV/dBmV，支持按 50Ω 换算）、检波方式
- 数据区：粘贴频谱仪导出的 trace 所有扫频点数值（空格/逗号/分号/换行或中文分隔符均可），点数即频率轴点数、等间隔线性均分；**带日志前缀的行会自动取行尾真实数值**（如 `2026-09-14 12:25:43 015: 流程日志：… --USER--MTC@PC: -51.564613` → `-51.564613`，支持 `-51.5 dBm` 这类单位后缀），清洗行数/跳过行数显示在状态行；非法数值仍明确报错（不会只取一半）
- 绘图：仪器式网格（横向 10 格 × 纵向可配格数，顶格为参考电平、向下每格 −dB/div）；勾选「纵轴自动适配」改为按数据范围取轴；标题与参数注记随图渲染
- **光标测量**：鼠标在图上移动即显示十字光标与读数框（最近数据点的频率与幅值，吸附不插值）
- **MARK 标记与两点测量**：点击绘图区添加标记 M1~M6（吸附最近数据点），**每个标记一种颜色**，图上标记与标记表文字同色，便于一一对应；标记表列出 `标记/频率/幅值/Δ频率(哪两点)/Δ幅值(哪两点)`，Δ 一律标注是哪两个标记之差（如 `M1↔M3`），可用「Δ 参考」下拉切换参考标记；测量栏显示峰值/谷值；「峰值搜索」「下一个峰值」可把标记移到全局峰或下一个局部峰（环形）
- **积分带宽（IBW）**：设定中心频率与积分带宽后勾选「显示积分带宽」，图上出现两条点划线竖线 + 半透明填充带 + `IBW 起–止` 标签，并给出带内**积分功率**（按「频率步进/RBW」归一化，RBW 未填则注明未归一化）与带宽内点数；带宽超出扫宽按交集积分并提示
- 导出：工具栏「导出 PNG」，默认 1600×1000，标记、Δ 与积分带宽注记一并渲染，可直接贴入测试报告

### 测试方案

切换到「测试方案」标签页：

- 添加发送帧、后台监听、纯等待、Lua 脚本等测试项
- 配置超时与匹配规则
- 顺序执行并记录结果，支持导出 Excel 测试报告

Lua 脚本使用说明见 [`docs/Lua脚本使用说明.md`](docs/Lua脚本使用说明.md)。

### 查询、档案与拓扑

- 查询页支持南网 DI、国网 AFN、DLT645 DI、OBIS 码、 PLC RF 命令字、新一代业务标识、HDC 1.0 报文 ID 与 EB 数据标识查询
- 档案管理与拓扑信息仅在南网 / 国网协议下显示
- 支持档案导入导出与拓扑组网统计

### 自动更新与状态栏

- 「帮助 → 检查更新」可拉取仓库全部版本并选择下载；可在「配置 → 更新设置」开启/关闭自动检查
- 状态栏显示本软件 CPU / 内存占用与线程数；点「线程: N」可查看 Python 线程与 QThread 明细并一键复制

## 项目结构

```text
main_gui.py                  # PySide6 GUI 主程序，应用入口
parser_registry.py           # Parser 懒加载注册（按名缓存实例）
protocol_registry.py         # 协议能力注册表（下拉/Tab/校验/提取/包装查表）
app_paths.py                 # 可写数据文件路径唯一入口（frozen 下落 exe 目录）
app_icons.py                 # 应用图标加载
auto_updater.py              # 自动更新检查与下载
proc_stats.py                # 本进程 CPU / 内存采样（纯标准库）
protocol_parser.py           # 南网协议解析器
gdw10376_parser.py           # 国网协议解析器
gdw_eb_di_lookup.py          # 本地通信模块扩展协议 EB 数据标识查询（附件1）
plc_rf_parser.py             # PLC RF 协议解析器
hdlc_parser.py               # HDLC / DLMS 解析器
dlms_deep_parser.py          # DLMS APDU 深度解析
dlt645_parser.py             # DLT645-2007 解析器
dlt645_data_codec.py         # DLT645 数据域编解码（decode/encode 成对互逆）
dlt645_frame_gen.py          # DLT645-2007 帧生成（唯一 645 封装实现）
dlt645_frame_schema.py       # DLT645 组帧命令 schema
dl_t698_45_parser.py         # 698.45 链路层解析器
dl_t698_45_apdu_parser.py    # 698.45 APDU 解析器
dl_t698_45_axdr.py           # A-XDR 编解码
dl_t698_45_data_decode.py    # 698.45 APDU 数据内容业务解码
dl_t698_45_frame_gen.py      # 698.45 帧生成
dl_t698_45_frame_schema.py   # 698.45 组帧字段 schema
csg_new_gen_parser.py        # 新一代载波协议解析器
csg_new_gen_cmd_payloads.py  # 新一代载波应用层命令载荷
gw_new_gen_parser.py         # 国网新一代双模解析器
gw_new_gen_mme_parser.py     # 国网新一代 MME 管理消息解析
gw_new_gen_cmd_payloads.py   # 国网新一代应用层命令载荷
hdc10_parser.py              # HDC 1.0 双模互联互通解析器
hdc10_mme_parser.py          # HDC 1.0 MME 网络管理消息解析
frame_diff_engine.py         # 协议感知报文对比引擎
send_frame_lib.py            # 南网帧生成
gdw_send_frame_lib.py        # 国网帧生成
frame_gen_widget.py          # 协议组帧组件
preset_buttons.py            # 预设命令组件
sequence_diagram_widget.py   # 通信时序图组件（纯逻辑模型 + QGraphicsView）
batch_source_view.py         # 批量原始日志快照只读查看器
meter_sim_widget.py          # 虚拟表 tab（698 从站模拟器）
meter_sim/                   # 虚拟表核心逻辑包（纯字节操作，无 Qt）
test_plan_widget.py          # 测试方案组件
lua_script_engine.py         # Lua 脚本引擎
serial_worker.py             # 串口通信线程
monitor_widget.py            # 实时监控器组件
monitor/tcp_monitor.py       # TCP 流量监控组件
system_integration/          # 系统集成：托盘 / 热键 / 快捷小窗 / 剪贴板 / Notepad++ / 单实例 / 右键菜单
message_tool_widget.py       # 报文工具组件
spectrum_widget.py           # 频谱图组件（纯逻辑层 + QPainter 自绘）
theme_settings.py            # 主题与字体设置
enhanced_export.py           # 增强导出功能
llm_preprocess.py            # LLM 预处理客户端
llm_preprocess_widget.py     # LLM 预处理面板
llm_api_manager.py           # LLM API 管理对话框
feedback_dialog.py           # GUI 问题反馈对话框
share_dialog.py              # GUI 报文分享对话框
lookup_pages.py              # 协议查询页
reflex_web/                  # Reflex Web 版（实验性）
test/                        # 测试脚本目录（所有 test_*.py 统一存放）
validator/                   # 协议校验引擎
report/excel_reporter.py     # Excel 测试报告
templates/test_templates.py  # 测试模板库
docs/Lua脚本使用说明.md       # Lua 脚本使用文档
南网协议解析工具.spec          # PyInstaller 打包配置
```

## 测试

项目无正式测试框架，`test/*.py` 为独立脚本，直接运行（命令在项目根执行）：

```bash
# 协议解析
python test/test_protocol_registry.py     # 协议能力注册表（1.23.1）
python test/test_csg_new_gen.py            # 新一代载波协议
python test/test_gw_new_gen.py             # 国网新一代双模协议
python test/test_gdw_fujian.py             # 国网福建增补规约 + EB 数据标识
python test/test_hdc10.py                  # HDC 1.0 双模互联互通协议
python test/test_hdc10_real.py             # HDC 1.0 真实报文回归
python test/test_dl_t698_45.py             # 698.45 协议
python test/test_dl_t698_45_data_decode.py # 698.45 APDU 数据内容业务解码
python test/test_dl_t698_45_fujian.py      # 698.45 福建简化698 List 结构
python test/test_nw_lcmi.py                # 南网本地通信模块接口协议 LCMI
python test/test_hdlc.py                   # HDLC 帧
python test/test_plc_rf.py                 # PLC RF
python test/test_dlt645_frame_gen.py       # DLT645 组帧闭环
python test/test_sack_fix.py               # SACK 帧解析
python test/test_ed_fallback_fix.py        # ED..EE 监控帧非法回退修复
python test/test_ed_gx_wrapper.py          # ED 广西台体包装头

# 批量 / 监控 / 时序图
python test/test_csg_batch_prefix.py       # 新一代载波监控日志前缀剥离
python test/test_csg_batch_parse_level.py  # 新一代载波解析级别
python test/test_csg_summary.py            # 新一代载波批量摘要
python test/test_csg_sequence_model.py     # 通信时序图纯逻辑模型
python test/test_csg_sequence_gui.py       # 通信时序图 GUI
python test/test_batch_src_line_jump.py    # 批量摘要回跳原始日志行
python test/test_batch_snapshot_locate.py  # 批量原始快照定位查看器
python test/test_monitor_deframe.py        # 监控解帧
python test/test_monitor_plc2_deframe.py   # PLC2 解帧
python test/test_gw_monitor_summary.py     # 国网新一代监控摘要

# 功能组件
python test/test_spectrum_model.py         # 频谱图纯逻辑（解析/日志清洗/校验/轴/单位/联动/标记/峰值搜索/Δ成对/积分带宽，225 项）
python test/test_spectrum_gui.py           # 频谱图 GUI（offscreen，含光标、MARK 颜色、Δ 标注、积分带宽竖线、日志粘贴，135 项）
python test/test_meter_sim.py              # 698 虚拟表从站模拟器
python test/test_quick_parse_panel.py      # 快捷解析小窗
python test/test_frame_share.py            # 报文分享
python test/test_feedback_api.py           # 反馈提交 API
python test/test_feedback_dialog.py        # GUI 反馈对话框
python test/test_web_feedback.py           # Web 版问题反馈
python test/test_diff_engine.py            # 报文对比引擎
python test/test_lua_engine.py             # Lua 脚本引擎
python test/test_theme_settings.py         # 主题与字体设置
python test/test_app_paths.py              # 数据路径定位
python test/test_app_exit.py               # 关闭/托盘退出进程不残留
python test/test_statusbar_stats.py        # 状态栏 CPU/内存
python test/test_auto_updater.py           # 自动更新
python test/test_web_frame_gen_utils.py    # Reflex Web 组帧纯逻辑
python test/test_web_landing.py            # Web 产品首页（内容不变式/防漂移/死链接线/路由搬迁，100 项）
```

> **约定**：所有测试文件一律放入 `test/` 目录（项目根目录禁止新增 `test_*.py`）。新测试文件头需 `import _path_setup`（详见 `test/_path_setup.py` 说明与 `AGENTS.md` §7）。

## 开发文档

- [`AGENTS.md`](AGENTS.md)：AI Coding Agent 上手指南，包含架构、协议映射、字节序与校验约定、开发原则与变更日志
- [`docs/Lua脚本使用说明.md`](docs/Lua脚本使用说明.md)：Lua 脚本功能使用说明与 API 参考
- [`.trellis/workflow.md`](.trellis/workflow.md)：Trellis 开发工作流与任务规范

完整版本变更记录见 `main_gui.py` 中的 `CHANGELOG`（按版本倒序），或运行 `git log --oneline`。

## 更新记录

> 完整历史见 `main_gui.py:CHANGELOG`。以下仅摘录最近版本要点。

### 1.23.10 — 2026-09-14

- **批量解析摘要体现测试帧的测试模式**：协议9 业务标识 `0xF0` 测试帧与协议10/11 通信测试/检测扩展命令的摘要列现在带上 `测试模式:…`（含 `安全测试模式`/`新一代测试模式` 子模式）；没有测试模式字段的测试帧回退显示 `测试ID`/`扩展ID`/`通信频段`，上行测试帧显示「测试帧上行」
- `test/test_csg_summary.py` 去掉文件内复刻的摘要逻辑（已与产品实现漂移），改为复用 `main_gui.MainWindow` 真实实现并新增测试帧用例

### 1.23.9 — 2026-09-14

- **新增「频谱图」标签页**（常驻，与协议无关）：频谱仪参数（起始/终止/中心/扫宽四字段双向联动、频率单位、RBW/VBW、参考电平、每格 dB、纵向格数、幅值单位、检波方式）+ 单条 trace 全部扫频点数值 → 仪器式网格频谱图，标题与参数注记随图渲染
- **50Ω 单位换算**：幅值单位可选 dBm / dBμV / dBmV，勾选「输入按 dBm，50Ω 换算」时按 dBμV = dBm + 107、dBmV = dBm + 47 换算
- **纵轴双口径**：默认仪器式（顶格 = 参考电平，向下每格 −dB/div），可勾选「纵轴自动适配」按数据 min/max 留 5% 余量取轴；越界点裁剪到边缘并提示个数
- **光标读数与测量**：鼠标悬停绘图区显示十字光标与读数框（最近数据点的频率/幅值）；点击添加 MARK 标记 M1~M6，**每个标记一种颜色**（图上标记与标记表文字同色，便于一一对应）；标记表列出频率/幅值/`Δ频率(哪两点)`/`Δ幅值(哪两点)`，Δ 一律标注是哪两个标记之差，可用「Δ 参考」切换参考标记；测量栏显示峰值/谷值；「峰值搜索」「下一个峰值」按 3 dB 显著度环形搜索局部峰，导出 PNG 时标记与 Δ 注记一并渲染
- **积分带宽（IBW）**：中心频率 + 积分带宽 + 显示开关；图上两条点划线竖线、边沿间半透明填充带与 `IBW 起–止` 标签；带内积分功率（按 `频率步进/RBW` 归一化，RBW 未填则注明未归一化）、带宽内点数；越界按交集积分并提示、无交集不填充
- **trace 日志清洗**：直接粘贴带日志前缀的行即可出图——每行自动取行尾真实数值（`… --USER--MTC@PC: -51.564613`，支持 `-51.5 dBm` 电平后缀）；**秒/毫秒时间戳不会被当成数值**（表头/纯时间戳行跳过并计数）；含数值却无法确定行尾数值的行（如 `… INFO: -51.5 dBm extra`）**明确报错并指出行号**（不静默丢行）；状态行提示「已清洗 N 行日志，跳过 K 行无数值」且切换纵轴口径不会丢该提示
- **导出 PNG**（默认 1600×1000），浅/暗主题自动适配调色板
- 实现：新建 `spectrum_widget.py`（纯逻辑层 + QPainter 自绘，零新增依赖，不用 matplotlib/QtCharts）；新增 `test/test_spectrum_model.py`（225 项）与 `test/test_spectrum_gui.py`（135 项 offscreen）

### 1.23.8 — 2026-09-12

- **645虚拟表「模拟设置 · 随机产生事件」**：勾选后每次读取事件状态字（DI `04001501` 主动上报状态字，`BS96` 12 字节）返回新的随机 12 字节值且与上一次不同；不勾选读档案值（新增默认项 12 字节全 0 = 无事件、读多少遍都一样）；离线与串口两条应答路径均生效，勾选状态经 `dlt645_sim_data.json` 的 `random_event` 持久化
- **修复事件状态字应答被截断**：虚拟表引擎类型/长度解析改用权威源 `dlt645_frame_schema.get_di_info`（`data_type` + `length`，并以 `nbytes=length` 调 `encode_value`），04001501 应答从 `L=0x08`（4 字节）恢复为 `L=0x10`（4 字节 DI + 12 字节数据）；新增 `dlt645_sim/dynamic_data.py` 与 `test/test_dlt645_sim_event_word.py`

### 1.23.7 — 2026-09-11

- **645虚拟表「模块版本查询」**：虚拟表作主站一键下发 LME 4.2/4.6/4.7 请求，模块回包复用 `DLT645Parser` 做深度解析

### 1.23.6 — 2026-09-11

- **云母主题（Mica · Win11）**：第 7 套内置主题，Win11 云母观感静态实现——壁纸取色均值底色 #f3f3f3 + Fluent 浅色配色 + DWM 圆角窗；全不透明（透明底衬会在批量解析等页面产生表面重影，已弃用），要透出壁纸请用毛玻璃主题

### 1.23.5 — 2026-09-11
- **645 虚拟表 GUI**：协议6 新增「645虚拟表」——离线应答 / 档案 / 串口从站


### 1.23.4 — 2026-09-11

- **DLT645 从站模拟引擎** `dlt645_sim/`：读数据闭环 + 异常应答 + 档案；GUI/串口接入后续版本

### 1.23.3 — 2026-09-11

- **发布前自检** `python release_check.py`：版本/CHANGELOG/Inno Setup/spec datas/核心测试一键跑；`--sync-iss` 同步安装脚本版本
- `python test/test_core_suite.py` 与自检共用核心测试清单

### 1.23.2 — 2026-09-11

- **批量解析「导入 pcap」**：离线读 pcap/pcapng → TCP 重组 → 批量输入并自动解析；经典 `.pcap` 零依赖
- 新增 `pcap_import.py` 与 `test/test_pcap_import.py`

### 1.23.1 — 2026-09-11

- **协议能力注册表 `protocol_registry.py`**：12 种协议的展示名/别名/占位符/查询页/组帧模式/Tab 能力/解析级别族/批量提取策略/校验器/解析器包装统一声明；`main_gui` 查表分派
- 修复协议6 预设命令页未调用 `set_protocol("dlt645")`
- 新增 `test/test_protocol_registry.py`

### 1.23.0 — 2026-09-09

- **通信时序图**（协议 9/10/11）：批量解析结果一键生成 CCO⇄STA 序列图；TEI 自动判别节点、广播/单播/SACK 有向箭头、阶段分隔线、台体与未入网站点归并；与摘要表双向联动；支持缩放、平移、导出 PNG
- **批量解析回跳与原始快照**：摘要行点击回跳输入日志对应行；右键「转到原始报文位置」弹出只读查看器（行号/高亮/搜索）
- **ED 包装头**：新增广西台体(14字节头)格式与自动识别；单帧/批量/校验四条链路统一
- **协议9多物理块**：逐块交错展示、跨 PB 行高亮偏移修复、填充 CRC-24 支持逐 PB PBCS 回填

### 1.22.1 — 2026-09-08

- 协议9 多物理块帧 PB 大小按帧长一致性推断，逐 PB PBCS CRC-24 三态校验
- 多物理块帧表格逐块交错展示；噪声载荷抑制 MAC 伪解析行
- 单帧解析选中行高亮同步滚动到输入框对应位置
- 修复 exe 打包后窗口/托盘图标缺失；「分享此帧」按钮补图标

### 1.22.0 — 2026-09-08

- **协议6（DL/T645-2007）组帧**：主站请求/从站应答/异常应答三组命令，DI 驱动字段表单，解析预览实时刷新；Reflex Web 同步支持
- LME 自定义接口查询请求 11H 结构化组帧；EB 数据标识 645 帧口径修正
- 广播校时解析修正（数据域第 6 字节为年 YY）
- 修复协议9 SACK 帧批量解析误报 MAC 长度不足；通道判别改为逐帧自动判别

## 许可证

MIT
