# Journal - Liruitao1993 (Part 1)

> AI development session journal
> Started: 2026-08-01

---



## Session 1: 系统集成增强：开机自启/托盘/右键菜单/全局热键/命令行

**Date**: 2026-08-02
**Task**: 系统集成增强：开机自启/托盘/右键菜单/全局热键/命令行
**Branch**: `main`

### Summary

完成系统集成 6 项：开机自启(HKCU Run)、系统托盘(关闭最小化/左键显隐/右键菜单)、文件右键菜单(.log/.txt/.hex/.bin 协议子菜单)、全局热键(RegisterHotKey 默认 Ctrl+Alt+X)、命令行参数(--parse/--protocol/--file/--minimized)、单实例(QLocalServer)。新增 system_integration 包 5 模块，ThemeSettingsDialog 内嵌系统集成分组。验证：语法+导入+MainWindow 实例化+热键注册+CLI 解析+文件解析+单实例两进程+注册表往返+右键菜单注册/注销+退出清理全部通过。

### Git Commits

| Hash | Message |
|------|---------|
| `5d7f0b5` | (see git log) |

### Status

[OK] **Completed**


## Session 2: 系统集成全流程完成:剪贴板检测/托盘/热键/右键菜单/单实例+exe编译

**Date**: 2026-08-02
**Task**: 系统集成全流程完成:剪贴板检测/托盘/热键/右键菜单/单实例+exe编译
**Branch**: `main`

### Summary

完成系统集成全链路: 剪贴板检测(默认关+严格hex校验,测试通过), 解析不弹主窗口, 解析级别下拉+ED剥离, pb_only信标帧修复, 单实例ACK修复, NPP/文件右键/自启指向exe, exe编译+验证主窗口与剪贴板提示框。用户测试3/4通过(纯hex弹窗/非hex不弹)。

### Git Commits

| Hash | Message |
|------|---------|
| `580d929` | (see git log) |
| `2d2744a` | (see git log) |
| `2d315d8` | (see git log) |
| `3d94e59` | (see git log) |
| `5dc4dea` | (see git log) |
| `4231bd1` | (see git log) |
| `9e79a87` | (see git log) |
| `3265531` | (see git log) |
| `c42e4bb` | (see git log) |

### Status

[OK] **Completed**


## Session 3: 国网协议7 福建增补(AFN 50H~56H)+EB数据标识 解析与组帧

**Date**: 2026-08-17
**Task**: 国网协议7 福建增补(AFN 50H~56H)+EB数据标识 解析与组帧
**Branch**: `main`

### Summary

基于 协议文档/7.国网本地接口协议/ 三份新文档（附件1 本地模块扩展协议V3.31 / 附件3 福建增补V1.4 / 附件4 以太网补充），为协议7 国网解析器新增福建增补规约全功能解析+组帧+EB数据标识深度解析。改动：gdw10376_parser.py(AFN/FN映射+福建增补帧结构识别+_parse_fujian_afn+_parse_eb_di)、gdw_eb_di_lookup.py(新,52项)、gdw_frame_generator_schema.py(+27 (AFN,Fn))、gdw_send_frame_lib.py(增补R/A结构+length_field bug修复)、validator/gdw_validator.py(AFN定位)、main_gui.py(版本1.14.0+CHANGELOG+EB查询区块)、test/test_gdw_fujian.py(新,15项全过)。验证：py_compile全过、test_gdw_fujian 15/15、test_web_frame_gen_utils 18/18、GUI组帧页冒烟通过。

### Git Commits

(No commits - planning session)

### Status

[OK] **Completed**


## Session 4-1: GUI 按钮添加图标（规划）

**Date**: 2026-08-27
**Task**: GUI 按钮添加图标（08-27-gui-button-icons，planning）
**Branch**: `main`

### Summary

用户提出「软件 GUI 很多按钮没有图标，需提升用户体验」。确认方案为 **Qt 内置标准图标**（QStyle.StandardPixmap，零资源/不改打包）。受 bash 与 PowerShell MCP 均不可用限制，无法运行 task.py，故**手动创建规划工件**待命令环境恢复后正式注册。

已创建 `.trellis/tasks/08-27-gui-button-icons/` 下三件：
- `prd.md`：Goal/Requirements/Acceptance（图标+文字并存、不破坏 set_btn/btnKind 体系、不新增资源）。
- `design.md`：方案——gui_utils 新增 `set_btn_icon(btn, icon_key, icon_only=False)` + `_STANDARD_ICON_MAP`（icon_key→QStyle.StandardPixmap），未知 key 静默安全；逐文件按钮映射清单。
- `implement.md`：实施清单（gui_utils→main_gui→frame_gen/diff/monitor/preset/test_plan 等）+ 验证 + 回滚点。

关键决策：图标 16px、图标+文字并存（默认不隐藏文字）、图标随系统主题自动适配、不新增资源文件、不改 spec 打包。

### Git Commits

(No commits - planning session, 待 task.py 注册)

### Status

[OK] **Planning artifacts created (pending task.py registration)**


## Session 4: 国网协议7 福建增补+EB扩展 全栈开发完成（解析/组帧/校验/Web/部署）

**Date**: 2026-08-18
**Task**: 国网协议7 福建增补+EB扩展 全栈开发完成（解析/组帧/校验/Web/部署）
**Branch**: `main`

### Summary

完成协议7 国网福建增补规约(AFN 50H~56H)解析与组帧、本地通信模块扩展协议(EB数据标识 V3.42)深度解析、Reflex Web 同步（EB 698 完整帧生成器+对象配置+查询页）、客户端下载页（exe下载/截图/README）、离线部署包(Python 3.13)。6 个语义提交，任务已归档。

### Git Commits

(No commits - planning session)

### Status

[OK] **Completed**

---

## Session 5: GUI 按钮添加图标（1.15.0）

**Date**: 2026-08-27
**Task**: `.trellis/tasks/08-27-gui-button-icons/`（prd/design/implement 已建；命令环境不可用未用 task.py 注册）

### Summary

- **方案**：Qt 内置标准图标 `QStyle.StandardPixmap`（零资源文件、跨平台、随系统主题自动适配、自动高 DPI），不用自定义 PNG（避免维护/打包/暗色适配）。
- **核心实现**：`gui_utils.py` 新增 `set_btn_icon(btn, icon_key, icon_only=False)` + `_STANDARD_ICON_MAP`（icon_key → StandardPixmap，含 search/clear/copy/save/export/open_file/open/delete/refresh/help/fullscreen/add/down/up/write/settings/play/pause/stop/next/import 等）；`btn.style().standardIcon()` + `setIconSize(QSize(16,16))`；未知 key 静默安全跳过；默认图标+文字并存。
- **覆盖文件**：gui_utils（核心）、main_gui（单帧解析/批量工具栏/串口/全屏）、frame_gen_widget、diff_widget、test_plan_widget、monitor/tcp_monitor、monitor_widget、archive_widget、topology_widget。message_tool_widget（转换类无贴切图标）与 preset 动态按钮保持原样。
- **版本**：APP_VERSION 1.14.9 → **1.15.0**，BUILD_DATE 2026-08-27，CHANGELOG 已加条目。
- **验证**：bash 因本机 Docker WSL 发行版损坏（`...Docker\wsl\main\ext4.vhdx` 挂载失败 / MountDisk ERROR_PATH_NOT_FOUND，System32\bash.exe 启动 WSL 必败）不可用；改用 `lsp_diagnostics`（ruff）验证 9 个改动文件——无新增错误，102 条全为既有告警（F401/E402 及 2 处历史 F821 非本次改动行）。
- **待办**：shell 恢复后跑 `python -m py_compile` + offscreen GUI 冒烟 + 人工 GUI 核验图标；spec 无需改（未新增数据文件）。

### Status

[~] **Implemented (pending runtime verification)**


## Session 5: 小窗模式核验+3主题提交入库完成

**Date**: 2026-08-29
**Task**: 小窗模式核验+3主题提交入库完成
**Branch**: `main`

### Summary

核验 1.17.0~1.18.1 快捷解析小窗：py_compile 六文件全过；test_quick_parse_panel 62 项断言全过（退出码 0，无历史 fastfail）；MainWindow 集成点抽查通过。按主题分 3 提交入库：b43460f 小窗+系统集成（5文件）、c24a3b3 主程序+打包（main_gui/spec/AGENTS.md）、a4bf623 其余功能（虚拟表/状态栏/协议修复/Web，49文件）。复验通过，git status 仅剩 R3 有意保留项。附带查清 .claude/skills/grill-with-docs 的 D+?? 状态为 6 月符号链接遗留（指向 .agents/skills/，git 不跟链接后文件），与任务无关。

### Git Commits

| Hash | Message |
|------|---------|
| `b43460f` | (see git log) |
| `c24a3b3` | (see git log) |
| `a4bf623` | (see git log) |

### Status

[OK] **Completed**


## Session 6: 协议9多物理块帧PB大小推断与PBCS CRC-24校验修复(1.22.1)

**Date**: 2026-09-08
**Task**: 协议9多物理块帧PB大小推断与PBCS CRC-24校验修复(1.22.1)
**Branch**: `main`

### Summary

真实4x520抓包帧暴露两缺陷：BPLC分支CMT->PB映射(0-7=>136)对SPLC帧失效致切片错位；PBCS从未计算CRC-24。修复：帧长一致性等式offset+pb_count*size==frame_len在候选集唯一推断PB大小并加提示行(无解回退先验,HRF/Bitloading显式值不参与)；逐PB CRC-24(PBH+体+保留,小端)三态结论(通过/置零未提供/失败)+截断分支+PB尾保留行。新增test_csg_pb_size_pbcs.py 4项,既有csg 69项无回归,合计73 passed。trellis-check自修截断偏移start>end边界。

### Git Commits

| Hash | Message |
|------|---------|
| `76af3dece5d36543a8a2a2f0caed3a929f781e06` | (see git log) |

### Status

[OK] **Completed**


## Session 7: 645虚拟表 LME 模块版本查询下发(1.23.7)

**Date**: 2026-09-11
**Task**: 645虚拟表 LME 模块版本查询下发(1.23.7)
**Branch**: `main`

### Summary

虚拟表新增主站下发能力：4.2/4.6/4.7 LME 帧一键下发 + 模块回包解析（95 项测试含 COM1↔COM2 真实回环）

### Main Changes

- 新增 dlt645_sim/lme_query.py（纯逻辑，复用 DLT645FrameGenerator + pack_lme_query_request + DLT645Parser）
- 645虚拟表运行页新增「模块版本查询」分组：三按钮+帧框+下发/复制；4.7 下发前确认
- 串口线程按 ctrl(idx8)&0x80 分流 DIR=1 模块回包 → slave_frame → 结果表；离线 DIR=1 直解
- AGENTS.md/CHANGELOG/APP_VERSION 1.23.7/spec hiddenimports/iss 同步；.trellis/spec 记录双角色契约

### Git Commits

| Hash | Message |
|------|---------|
| `57a4154` | (see git log) |

### Testing

- [OK] test/test_dlt645_sim_lme_query.py 95/95（4.2 手册 golden 逐字节、4.6/4.7 位域、手册回包 135B 字段回归、截断容错、offscreen GUI、COM1↔COM2 真实回环）
- [OK] 回归：test_dlt645_sim / test_dlt645_lme / test_dlt645_frame_gen(161) / test_dlt645_frame_gen_gui(73) / test_quick_parse_panel(84) / test_app_exit 全过
- [OK] release_check PASS=41 FAIL=1（test_gw_new_gen 既有失败，未触碰协议10）

### Status

[OK] **Completed**

### Next Steps

- 4.7 帧布局实机验证（文档/schema 无 645 密码组，若实机要求需在 build_dual_set 加前缀）


## Session 8: 事件状态字随机 + 协议10红灯归零 + 后续批次规划

**Date**: 2026-09-12
**Task**: 事件状态字随机 + 协议10红灯归零 + 后续批次规划
**Branch**: `main`

### Summary

交付 1.23.8 事件状态字随机与随机产生事件开关；查清并修复协议10 假阳性吞帧，release_check 首次全绿；建 5 个子任务规划

### Main Changes

- 645虚拟表：事件状态字 04001501 类型/长度修复（L=0x08→0x10）+ RandomEventWord + 模拟设置勾选框 + 持久化；顺带修复 import json 丢失导致的档案 JSON 读写全线失效
- 协议10：parse_to_table 裸管理消息判据收紧（MMTYPE 命中 + 保留=0 + 非 FC 前缀），修掉整帧被吞的假阳性
- 建父任务 09-12-backlog-batch-0912 + 5 子任务（南网自定义DI增删/645虚拟表功能码/HDC网间协调帧/协议9深解析/协议10未识别报文）

### Git Commits

| Hash | Message |
|------|---------|
| `2be9b2a` | (see git log) |
| `0272643` | (see git log) |
| `669fc74` | (see git log) |

### Testing

- [OK] test_dlt645_sim_event_word.py 66/66（含 COM1↔COM2 回环）；645 既有 5 套回归全过
- [OK] release_check PASS=48 FAIL=0 WARN=0（此前长期 1 FAIL）

### Status

[OK] **Completed**

### Next Steps

- 实现 09-12-nanwang-custom-di-crud（南网查询页自定义 DI 增删死按钮）
- 按序推进 645虚拟表功能码 → HDC网间协调帧 → 协议10未识别报文 → 协议9深解析


## Session 9: 自定义DI增删单源收口 1.23.11 + 三任务归档 + AGENTS目录树补漏

**Date**: 2026-09-15
**Task**: 自定义DI增删单源收口 1.23.11 + 三任务归档 + AGENTS目录树补漏
**Branch**: `main`

### Summary

南网查询页自定义DI增删收口为 custom_di_store.py 单源（protocol_parser/main_gui/lookup_pages 三方共用；覆盖确认+多选批量删除+内置拒删），lookup_pages 两枚「功能待实现」死按钮转真；新增 test_nanwang_custom_di.py 92 项并入 CORE_TESTS，修复 test_plc_rf GBK 控制台✓崩溃；release_check PASS=50 FAIL=0 WARN=0 全绿；APP_VERSION 1.23.11 / BUILD_DATE 2026-09-15，iss 与 README 徽章同步；删除 _seq_preview.png；归档 09-14-spectrum-plot、09-14-batch-test-frame-summary、09-12-nanwang-custom-di-crud；AGENTS.md 补 §3 目录树漏项与 §7/§10 更新

### Git Commits

| Hash | Message |
|------|---------|
| `bd4be7a` | (see git log) |
| `7618f3b` | (see git log) |

### Status

[OK] **Completed**


## Session 10: Web 版解析 P0 缺陷修复（审计→任务树→实现→复核→提交）

**Date**: 2026-09-15
**Task**: Web 版解析 P0 缺陷修复（审计→任务树→实现→复核→提交）
**Branch**: `main`

### Summary

新增父任务 09-15-web-parse-alignment + 5 子任务（p0-fixes 已归档）。完成 P0：校验 NameError、批量失败判定、奇数长度、剔除误判撤销、frame_type/mac_only、ED 广西台体单源、查询页 3 处事实错误、CRC-24。新增 test_web_parse_fixes.py 75 项；release_check PASS=51 FAIL=0。复核发现并修复：快捷小窗 ED 漏传 wrapper、打包 hiddenimports（validator re-export + 3 spec）、文档口径。教训：推断型审计结论必须实测复现（剔除误判曾被照抄改坏）。

### Git Commits

| Hash | Message |
|------|---------|
| `5f4fde3` | (see git log) |

### Status

[OK] **Completed**


## Session 11: Web 频谱图移植（复用桌面纯逻辑层 + SVG 自绘）

**Date**: 2026-09-15
**Task**: Web 频谱图移植（复用桌面纯逻辑层 + SVG 自绘）
**Branch**: `main`

### Summary

新增常驻频谱图 tab：spectrum_web.py 纯几何(SVG) + SpectrumState + spectrum_tab；复用 spectrum_widget 前 950 行纯逻辑（零算法重写），QPainter→SVG；点击带实现标记 M1~M6（配色/Δ/峰值搜索/IBW 全对齐）；导出 PNG 走前端 SVG→canvas。测试 64 项；release_check PASS=53。

### Git Commits

| Hash | Message |
|------|---------|
| `621b346` | (see git log) |

### Status

[OK] **Completed**


## Session 12: 预处理命令链全角空格/引号不可用修复（1.23.13）

**Date**: 2026-09-15
**Task**: 预处理命令链全角空格/引号不可用修复（1.23.13）
**Branch**: `main`

### Summary

定位并修复批量解析预处理命令链在中文输入法全角状态下报「未知命令」的缺陷；pp_cli 新增 split_commands 单源 + 三处调用点收口 + 错误提示码位；新增 test/test_pp_cli.py 47 项；发布自检全绿

### Main Changes

- pp_cli.split_commands()：兜底式全角→半角归一化（仅首个 token 非已知命令时重试），保参数里刻意保留的全角字符
- main_gui._run_cli_preprocessor 与 Web parse_batch/run_preprocess 三处改走 split_commands；tooltip/帮助/Web 说明补半角规则
- parse_and_run 未知命令报错附转义+非 ASCII 码位+半角提示；AGENTS.md 新增陷阱 33；版本 1.23.13 + iss/README 同步

### Git Commits

| Hash | Message |
|------|---------|
| `b5e0efe` | (see git log) |

### Testing

- [OK] test/test_pp_cli.py 47 项（含 offscreen MainWindow 真实回调：全角不弹错/非法命令仍报错/真实 config.json 未改写）
- [OK] Web 真实 reflex State 驱动 run_preprocess + parse_batch：半角/全角/NBSP 四种写法产出逐字相同
- [OK] python release_check.py PASS=54 FAIL=0 WARN=0

### Status

[OK] **Completed**

### Next Steps

- 并行任务 09-15-web-theme-system 正在改 reflex_web/reflex_web/reflex_web.py（var(--token) + theme_web.py），当前工作区该模块 import 报 NameError: theme_web 未定义——其落地后需重跑 test_web_parse_fixes/release_check


## Session 13: Web 主题系统（明暗模式 + 预设 + token 化 + 频谱图跟随）+ 用户报障修复

**Date**: 2026-09-15
**Task**: Web 主题系统（明暗模式 + 预设 + token 化 + 频谱图跟随）+ 用户报障修复
**Branch**: `main`

### Summary

theme_web.py 纯逻辑（6 预设/5 强调色/3 模式/token 表/客户端脚本）；GLOBAL_CSS 与组件 215 处色值 token 化（浅色等价，测试断言）；顶栏主题下拉+模式按钮，localStorage 持久化，class 观察器兜住 Reflex ThemeProvider 覆盖竞态；频谱图 SVG 与标记配色走 var(--sp-mN)。顺带修用户报障：独立页面顶栏导航被主题控件挤没（主题控件限主页 + 全页注入样式）、顶栏渐变不随强调色（class 挂根容器）、分享卡片 str(Var) 垃圾串。test_web_theme.py 89 项；release_check PASS=55。

### Git Commits

| Hash | Message |
|------|---------|
| `20f2c8c` | (see git log) |

### Status

[OK] **Completed**


## Session 14: Web 批量解析结果搜索/筛选（接分页）

**Date**: 2026-09-15
**Task**: Web 批量解析结果搜索/筛选（接分页）
**Branch**: `main`

### Summary

filter_batch_summaries 纯函数 + BATCH_STATUS_FILTERS；State 搜索词/状态筛选/可见计数 + 私有 _batch_filtered；分页改为对过滤后摘要切片（搜索作用于全量）；帧 HEX 存后端私有行不下发；UI 搜索框+状态下拉+显示 N/M；test_web_batch_paging 扩至 57 项；顺带修 hex 字段的 UnboundLocalError。

### Git Commits

| Hash | Message |
|------|---------|
| `7dc5ac5` | (see git log) |

### Status

[OK] **Completed**


## Session 15: Web 版产品首页（落地页）+ 路由搬迁

**Date**: 2026-09-15
**Task**: Web 版产品首页（落地页）+ 路由搬迁
**Branch**: `main`

### Summary

新增 landing_web.py（纯内容+纯展示，不 import reflex_web）：Hero/统计条/12 功能卡/12 协议表/CLI 与系统集成/下载区/页脚，全 token 化（浅深+5 强调色）。路由 /→首页、/app→工具（index 更名 tool_page），4 处语义链接改指、品牌块回首页、主题控件抽 theme_controls_compact 共用。修：顶栏版本徽章写死 v1.13.0→读 version.json；load_download_info 复位上提消除陈旧字段；420px 横向溢出；深色下浅色强调白字对比度。放弃截图改 URL 方案（实测 dev 前端不代理后端路径，相对 URL 必破图）。新增 test/test_web_landing.py 100 项（含变异反证过的死链接线与 CLI 守卫）；release_check PASS=56 FAIL=0。

### Git Commits

| Hash | Message |
|------|---------|
| `b1aecdc` | (see git log) |

### Status

[OK] **Completed**


## Session 16: Web 运行时数据外置（升级不再丢库/发布产物/口令）

**Date**: 2026-09-16
**Task**: Web 运行时数据外置（升级不再丢库/发布产物/口令）
**Branch**: `main`

### Summary

新增 app_data.py 作为运行时路径唯一来源（NW_WEB_DATA_DIR → 冻结态 exe 同级 nw_web_data → 回落代码目录），数据根默认在部署目录上一级、启动脚本注入（已设不覆盖）；feedback_model/share_model/reflex_web 六处/run_app 中间件全部收口，删 FEEDBACK_DATA_DIR/FRAMESHARE_DATA_DIR。构建侧新增 deploy_common.py：downloads 白名单（随包资产进包、运行时产物与 build/dist 排除）、生成 迁移数据.cmd/sh、启动脚本注入变量；删除从未生效的 preserve_data_* 与错误承诺。修 onefile exe 数据写 _MEIPASS（重启清零）、迁移改递归按条目搬（不覆盖/幂等/空骨架可补/失败只告警）且不搬随包资产。复核（trellis-check，10 条含 2 个 P1）逐条修复：迁移脚本 set -eu 不可用、downloads 漏 build/dist 25MB、随包资产被迁移遮蔽、cmd 不判 robocopy 致命码、PS 下的 set 语法、cmd 编码 GBK、守卫缺口、启动不可写无指引。测试 test/test_web_data_paths.py 118 项 + release_check PASS=56 FAIL=0 + 两条真实部署 E2E（删目录重建数据仍在 / 旧版自动迁移）。

### Git Commits

| Hash | Message |
|------|---------|
| `c70a1c8` | (see git log) |

### Status

[OK] **Completed**


## Session 17: Windows 局域网部署：--port 固化 + 教程 + 内嵌离线包构建

**Date**: 2026-09-16
**Task**: Windows 局域网部署：--port 固化 + 教程 + 内嵌离线包构建
**Branch**: `main`

### Summary

两个部署构建脚本新增 --port（默认 8080，写入三份启动脚本与部署说明，命令行可覆盖）；新增 docs/Web版局域网部署教程.md（防火墙放行/启动验证/首次配置/任务计划与NSSM常驻/备份升级/排错表）；以 --skip-deps --port 8091 增量构建 dist/reflex_web_embedded（前端重编译），并真实起服务验收 27 项全通过（无运行时数据、脚本固化 8091、GET / 与 /app 可用、反馈写入外部数据根）；生成 dist/reflex_web_embedded_8091.zip（103MB）供拷到服务器。测试 126 项 + release_check PASS=56 FAIL=0。

### Git Commits

| Hash | Message |
|------|---------|
| `2a717fd` | (see git log) |

### Status

[OK] **Completed**


## Session 18: 下载地址端口错乱修复（8091 却跳 host:8000）

**Date**: 2026-09-16
**Task**: 下载地址端口错乱修复（8091 却跳 host:8000）
**Branch**: `main`

### Summary

根因：发布页/首页按钮用 rx.config 构建期端口(3000/8000)+socket 猜 IP 拼绝对下载地址，单端口 8091 部署后写成 host:8000 并进 version.json（GUI 自动更新也读它）。修法：web_utils 新增 resolve_download_target/release_absolute_url/release_download_path/is_same_origin_serving 收口——网页按钮同源相对路径（自愈历史 :8000、外部托管原样保留），发布页默认地址/version.json 用真实请求 host；删两处重复实现与死代码 set_release_url_from_host。新增 test/test_web_download_url.py 35 项并登记 CORE_TESTS；重建 8091 内嵌包并 32 项产物验收通过（含修复进包断言）；重打 zip 103MB。过程中我的脚本用 s.index 找锚点误命中字段区同名注释，导致 reflex_web.py 被整段复制（12393→15400 行，语法有效测试也过）——已回滚重做并加护栏（行数突变/重复 def 断言）。

### Git Commits

| Hash | Message |
|------|---------|
| `9d059f4` | (see git log) |

### Status

[OK] **Completed**


## Session 19: GUI 批量解析后台化 + 详情按需 + 过滤提速（1.23.15）

**Date**: 2026-09-16
**Task**: GUI 批量解析后台化 + 详情按需 + 过滤提速（1.23.15）
**Branch**: `main`

### Summary

任务 09-15-gui-batch-parse-perf 完成并归档。批量解析从「主线程同步 21s 冻结」改为「主线程同步预处理 + BatchParseWorker 后台分片解析」：工具栏进度条 + 取消（实测 10~15ms 停止）、取消落分片中途不再丢未满一片的结果；batch_results 去 _table_data 常驻缓存，229.4MB → 20.6MB，详情/导出/复制/时序图改走 _get_frame_table_data(index) LRU(50) 按需重解析；摘要过滤 0.87s → 0.012s（setUpdatesEnabled + 250ms 去抖）。对拍：协议9 真实日志 49,532 帧与协议11 13,763 帧「HEAD vs 当前」全量 0 差异（含导出「包含表格数据」列）；修详情重解析与批量不一致 934 帧（根因=解析器跨帧可变状态，用 _ctx 锁存+apply_cross_frame_state 还原，未改解析器算法）。新增 test/test_gui_batch_perf.py（99 项）并登记 CORE_TESTS；4 个既有批量测试迁移到 wait_batch。release_check PASS=57 FAIL=0 WARN=2（WARN 为 HEAD 基线）。顺带查出并修：3 个测试文件丢了 import _path_setup（# noqa: E402 不抑制 F401 → ruff --fix 会删掉它），已补 F401 并写入 AGENTS §7 约定。遗留：解析器入口未重置跨帧状态（陷阱 41）、协议10 无真实对拍、enhanced_batch_export.py 是被 gitignore 的孤立副本。

### Git Commits

| Hash | Message |
|------|---------|
| `560df22` | (see git log) |
| `41a9935` | (see git log) |
| `1c5b13a` | (see git log) |

### Status

[OK] **Completed**


## Session 20: GUI 窗口/分栏/列宽状态持久化（1.23.16）

**Date**: 2026-09-16
**Task**: GUI 窗口/分栏/列宽状态持久化（1.23.16）
**Branch**: `main`

### Summary

任务 09-15-gui-window-state-persist 完成并归档。主窗口几何/result_splitter 比例/10 张关键表列宽持久化到 config.json 顶层 window 段（不用 QSettings；不塞 ui 段——那份每次由 ThemeManager.to_config 整体重建会被抹掉），只在 closeEvent 真实退出路径写；带屏外回落与非法值容错，配置菜单加「恢复默认窗口布局」。复核中发现并修掉本特性引入的真实副作用：测试构造并关闭主窗口时会把 offscreen 合成几何（实测 684x666）写进开发机真实 config.json，下次启动被套用 —— 两道防线：① closeEvent 的 _window_shown_once 守卫（从未 show 过的窗口不写盘，覆盖所有「构造即关闭」测试路径与 --parse/--file/--clipboard 路径）；② 新增共享沙箱 test/_config_sandbox.py（同时 patch app_paths.data_path 与 main_gui.data_path——后者是 from app_paths import data_path 绑进模块命名空间的那份），接线到实测会写盘的 test_app_exit/test_theme_settings，并给 test_pp_cli 补 app_paths.data_path 的 patch，其原有「真实 config.json 未被改写」md5 断言因此恢复成立。实测：5 个测试 + 整轮 release_check 跑完后真实 config.json 顶层键仍为 11 个、无 window 残留。新增 test/test_window_state.py（93 项）登记 CORE_TESTS，变异反证（_apply_window_state 改空实现 → 变红 8 项）。顺带给 3 个测试文件的 import _path_setup 补 F401 抑制（# noqa: E402 不压 F401，ruff --fix 会删掉该行导致 ModuleNotFoundError）。release_check PASS=58 FAIL=0 WARN=2（WARN 为 HEAD 基线）。

### Git Commits

| Hash | Message |
|------|---------|
| `adb7064` | (see git log) |

### Status

[OK] **Completed**


## Session 21: GUI 死代码清理 + 修模型API管理菜单失效（1.23.16）

**Date**: 2026-09-16
**Task**: GUI 死代码清理 + 修模型API管理菜单失效（1.23.16）
**Branch**: `main`

### Summary

任务 09-15-gui-dead-code-cleanup 完成并归档。纯删除 main_gui.py -301 行（0 插入）：5 组重名方法的死版本（后定义覆盖前定义，故删前面那批；逐组 diff 确认 _clear_layout 逐字相同、其余为 f58c863「串口配置持久化」的有意重写且伴随占位项成对移除）+ 6 个零引用方法/函数（先做 getattr 动态派发扫描 40+ 处、注册表映射核对、全仓含 spec/iss/json 0 引用确认）+ 10 个已跟踪根临时脚本（792 行）+ 3 个未跟踪临时脚本 + 连带 import subprocess。_generated_mapping*.py 的数据核对后确认已活在 protocol_parser._get_f0_32_entry_name（v1 130 键 ⊂ 现 145、v2 == 现），删除无损失。复核中发现真实功能回归：「配置→模型API管理」菜单项的 triggered.connect 被 e1dd85e（2026-08-21 协议11 功能提交）误删 → 菜单项点了没反应，且方法因零引用几乎被当死代码删掉；已恢复接线并新增守卫 test/test_menu_wiring.py（13 项行为式断言：类级打桩 + 真实 action.trigger()；变异反证拿掉 connect → 变红）。顺带修掉 release_check 的 README 徽章 WARN（1.23.14→1.23.16）。验证：AST 重名组 0（MainWindow 262/262）、ruff 保持基线 10、release_check PASS=59 FAIL=0 WARN=2、真实 config.json 全程未被测试污染。注：确认 QAction 生命周期坑——[a.menu() for a in menubar.actions()] 取到的 QMenu 包装会当场失效（shiboken），必须用 menubar.findChildren(QMenu) 持强引用。

### Git Commits

| Hash | Message |
|------|---------|
| `58f9ad6` | (see git log) |

### Status

[OK] **Completed**


## Session 22: 收口 GUI 优化批次步骤 5/6 + 归档父容器（1.23.16）

**Date**: 2026-09-16
**Task**: 收口 GUI 优化批次步骤 5/6 + 归档父容器（1.23.16）
**Branch**: `main`

### Summary

把 09-15-gui-batch-parse-perf 的步骤 5/6 真正做完并关掉待办（此前只是忘标完成）：步骤 5 核对确认已完备（test_gui_batch_perf.py 99 项全过 + 已登记 CORE_TESTS；4 个迁移/既有批量测试在门槛内均 [PASS]）；步骤 6 补齐 4 处真实缺口——CHANGELOG 1.23.16 补记死代码清理（main_gui.py -301 行）与「配置→模型API管理」菜单接线失效修复、AGENTS.md 两处版本陈述滞后修正（§1 现 1.23.15→1.23.16、§2 Inno Setup 段 1.23.14→1.23.16）、BUILD_DATE 2026-09-15→2026-09-16。门槛从 PASS=60/FAIL=0/WARN=1 变成 PASS=61/FAIL=0/WARN=0 —— 归档时 DoD 写的「无 FAIL/WARN」到这一刻才字面成立。另：提交后 pi-lens 自动格式化了 3 个已提交文件（README 空行、test_app_exit 的 import 重排与未用 thread_registry 移除、test_theme_settings 重排），逐项核对无实质损失（断言失败消息未丢、thread_registry 确实只出现在字符串/注释中）后纳入 0f010a6。最后把父容器 09-15-gui-optimization 归档，并在其 prd.md 追加「跨子任务验收结果」记录（3 个子任务的提交/版本、5 条验收标准逐条核对、复核阶段另发现的 3 个真实缺陷、已知偏差与遗留）。至此 GUI 优化批次三子任务全部完成并归档，活跃任务里已无 gui-* 条目。

### Git Commits

| Hash | Message |
|------|---------|
| `0f010a6` | (see git log) |

### Status

[OK] **Completed**


## Session 23: 协议6 主动上报状态字/模式字位表入库 + 电表运行状态字1~7 位号纠错（v1.23.23）

**Date**: 2026-09-17
**Task**: 协议6 主动上报状态字/模式字位表入库 + 电表运行状态字1~7 位号纠错（v1.23.23）
**Branch**: `main`

### Summary

依据国网第4号补遗给协议6 入库 96 位主动上报状态字与 64 位主动上报模式字位表，并修正 dlt645_data_codec.STATUS_WORD_BITS（电表运行状态字 1~7）系统性位号错误

### Main Changes

- dlt645_data_codec.py 新增 REPORT_STATUS_BITS(96 位)/REPORT_MODE_BITS(64 位)/SUPPLY_MODE_NAMES/_format_bits/decode_report_status_word/decode_report_mode_word；_norm_bit_entry 支持 (名称,位宽,枚举) 两位域写法
- 修正 STATUS_WORD_BITS：原 8 个字无一正确（状态字4 0x0002 原报「A相潮流方向异常」，附录C 实为 Bit1=欠压）；供电方式由两个单 bit 改为 Bit2~Bit1 两位域；补全附录C 声明的保留位占位
- 保留位显式 None 占位 + 置位时点名「保留位（补遗未定义事件）: Bit76」（用户现场帧命中补遗未定义位），未置位不进列表防噪声；模式字=使能、状态字=已发生
- 提示文案纠错：未收录位域不再只写「见DL/T645-2007附录C」（对主动上报表是错误出处），改为并列两个出处
- test/test_dlt645_status_word_bits.py（130 项，登记 CORE_TESTS，含 R2 不变量 状态字Bit(32+n)≡模式字Bit(n) 与桌面↔Web 逐行对拍）；test_dlt645_lme.py 12b/12c 原固化错误位号且 12c 假绿，已修正
- 版本 1.23.23：APP_VERSION / README（badge·版本句·更新记录）/ 2222.iss 与 南网解析工具.iss / CHANGELOG（逐条列出状态字 1~3/7 输出变化）/ AGENTS.md（§5.4 依据、§8 陷阱 50、§10 摘要）
- 入库《第4号补遗》PDF + 转换 MD 至 协议文档/6.645协议/；位表以 pdfplumber 按单元格重取为准（MD 的 markitdown 转换有拆行/丢格/页码混入）

### Git Commits

| Hash | Message |
|------|---------|
| `0f10205` | (see git log) |
| `497a64b` | (see git log) |

### Testing

- [OK] python release_check.py → PASS=68 FAIL=0 WARN=0（68 = 原 67 + 新增 1 项）
- [OK] 变异反证 3 条均实测变红后还原：M1 状态字4 位号改回旧错位 9 红 / M2 去掉保留位标注 2 红 / M3 96 位当 64 位解 3 红

### Status

[OK] **Completed**

### Next Steps

- 09-17-web-gui-parity-sync（Web↔GUI 版本×Web 审计与已确认缺口修复）可开始
- 组帧侧位域写入（dlt645_frame_schema 的 BS* 分支）仍属本次范围外


## Session 24: Web↔GUI 修复同步（审计清单 + 645 转表单源 + 测试模式摘要单源 + 查询页自定义 DI/AFN CRUD，1.23.42）

**Date**: 2026-09-21
**Task**: 09-17-web-gui-parity-sync（父任务 09-15-web-parse-alignment）
**Branch**: `main`

### Summary

接续该任务：R2（645 转表偏移 + 单一来源）此前已落地但未收口，本次补齐 R1 审计清单、R3（测试模式摘要两端同源）、R4（Web 查询页自定义条目 CRUD），并跑完全量门槛与变异反证。

### Main Changes

- **R1 审计**：`docs/Web与GUI同步审计.md`（167 条逐条判定：继承 88 / 缺失 21 / 同错 0 / N/A 58 + 1 条派生同错），全部附 `文件:行号`；含未覆盖区间 1.23.23~1.23.40 与 1.22.x 待办。G1 门新发现 6 项 Web 缺失 → 拆子任务 `09-21-web-missing-capabilities`（已建 PRD）
- **R3 单源**：原计划新建 `frame_summary.py`，实测发现另一任务线的共享核心 `batch_core.py` 已含逐字搬移的 `extract_test_mode_content` + `TEST_MODE_SENTINELS` → 改为直接复用（删除临时新建的 `frame_summary.py`）；桌面一行转发、Web `from batch_core import ...`；Web `get_csg_new_gen_summary` 经新增 `_append_test_mode_segment`（去重守卫）与 `get_hdc10_summary` 各补片段（协议10 的检测扩展命令帧会路由到 csg 摘要，两处都要接）
- **R4/R4b CRUD**：`custom_di_store` 读写加可选 `path`；Web 协议0 自定义 DI 增/覆盖/删 + 勾选列与批量「删除选中」（内置忽略并计数）；**G2 门用户决定**国网 AFN+Fn CRUD 也纳入 → `lookup_utils.add_gdw_custom_fn` / `remove_gdw_custom_fns` 薄封装 `GDW10376Parser` 既有 API（不新增第二份 JSON 读写），`gdw_afn_lookup.refresh()` 解决查询缓存不刷新；查询表新增「自定义」★ 列
- **测试**：`test/test_web_gui_parity.py`（83 项：R3 两端片段对拍 + R4/R4b 增删与沙箱），与 `test/test_dlt645_table_offsets.py` 一并登记 `release_check.CORE_TESTS`；**变异反证 3+1 条**全部实测变红后还原
- **收尾**：CHANGELOG 1.23.42、`APP_VERSION` 1.23.42 + `--sync-iss`、AGENTS.md §1/§2 版本陈述 + §8 陷阱 31 已收口清单 + 新增陷阱 55（Web 查询页自定义条目约定）+ §10 摘要

### Testing

- [OK] `python release_check.py` → **PASS=86 / FAIL=1 / WARN=1**；唯一 FAIL = `test/test_hdc10_batch_strip_level.py`（「帧类型含 [11]」），属另一条工作线的批量重构（`_type_name` 走 `batch_parse_worker`/`batch_core`），本任务未触及
- [OK] 变异反证：偏移公式回退 8 红 / 去 Web 片段 6 红（协议11 路径再 2 红）/ 645 复制体回潮 4 红
- [OK] 沙箱：全程未污染真实 `custom_di.json` / `gdw_custom_afn.json`（测试后 `git status` 干净）

### Notes

- 工作区内另一会话同期在做「顶部栏折叠 1.23.41」等改动（`main_gui.py` 在我收尾前几分钟仍被写入），本次按用户要求把全部未提交改动一并提交；仅排除明显临时调试产物（`test/_tmp_*`、`test/out*.txt`）
- 收尾前曾出现一次 `test_nanwang_custom_di` / `test_menu_wiring` 报 `MainWindow` 缺 `_top_bar_toggle_style` 的偶发失败——实为另一会话正在写 `main_gui.py` 的中间态；随后连跑两次均全过（92/92、13/13），非本任务回归


## Session 24: 协议8 698.45 A-XDR 字节序修复（数据域大端）

**Date**: 2026-09-29
**Task**: 协议8 698.45 A-XDR 字节序修复（数据域大端）
**Branch**: `feat/serial-tool-protocol-parse`

### Summary

协议8 两层字节序修正：链路层(L/HCS/FCS/地址)保持小端，APDU 内 A-XDR 全部多字节改大端(DL/T 790.6-2010 §7.1)。实测帧 05 FF FF 9E D0 由 -794886145 修正为 -24880。含解码/编码同步、组帧 '>H'、LINK-Request/Response 按 SEQUENCE 不带 tag 解析；新增 test/test_dl_t698_45_endian.py(48 项 oracle+链路层回归)；AGENTS.md §5.6/陷阱64 + 跨层指南 + 版本 1.23.63 与 iss 同步。trellis-check 全 AC PASS，drawer 4 处小端文案残留已修。

### Git Commits

| Hash | Message |
|------|---------|
| `05fe755` | (see git log) |

### Status

[OK] **Completed**


## Session 25: 协议9（南网新一代载波）接入「协议组帧」页

**Date**: 2026-09-30
**Task**: 09-30-csg-link-layer-frame-gen —— GUI 协议9 组帧，折叠窗口填字段，SOF 帧与测试模式帧优先
**Branch**: `main`

### Summary

协议9 的组帧控件（csg_link_frame_gen / csg_new_gen_frame_gen / csg_test_frame_gen_widget）此前只存在于工作区，**没有接到 GUI**（改动前 frame_gen_widget.py 里没有任何 csg 分支，`git grep csg_new_gen_frame_gen` 在已跟踪文件里零命中）。本次按注册表 `frame_gen_mode="csg"` 接线：组帧页左栏改 `QStackedWidget`（0=常规动态表单 / 1=协议9 链路层组帧），五层折叠表单 ①FC ②物理块 ③MAC 头 ④MSDU ⑤ED 封装，进页面默认勾选「组装链路层」+ 默认 SOF 帧；SOF（BPLC/ISAC、长/短 MAC 头、多物理块）/ 信标 / SACK 三型 + **24 个测试模式**全部闭环（FCCS/PBCS/CRC-32 回读「校验通过」）。过程中发现并修掉 3 个真缺陷 + 1 条可见性口径，新增 71 项 offscreen GUI 端到端测试。版本 1.23.64。

### Main Changes

- **接线**：`protocol_registry.ProtocolSpec(frame_gen_mode="csg", preset_mode=None)`；`frame_gen_widget.py` 左栏 `QStackedWidget` 托管 `CsgTestFrameGenWidget(link_layer_default=True)`（栈而非直接塞 `_form_layout`：`_rebuild_form` 会走 `_clear_layout` 递归销毁子控件）；`set_protocol_mode("csg")` 分支隐藏 DI/AFN/mode_group/EB 区与「添加到预设」；`_do_realtime_update_csg` / `_generate_csg_frame` 把 hex 与解析行送进共享的 `result_hex` / `preview_table`；`reset()` 补栈索引复位（mode_group 是栈外兄弟节点，`_rebuild_form(None)` 会把它重新显出来）
- **预设页可见性口径**：`main_gui._on_protocol_changed` 由 `frame_gen_mode is not None` 改判 `preset_mode is not None` —— 协议9 有组帧页但无预设库，原判据会露出**空的**预设页，且「添加到预设」会经 `preset_buttons._get_path` 的兜底分支误写 `GW_command.json`
- **修真缺陷 ①**：信标时间戳/周期是 32bit 字段，`QSpinBox.setRange(0, 0xFFFFFFFF)` 抛 `OverflowError` 打断 `_rebuild_fc_fields` ⇒ 切信标帧即崩、输出仍是上一帧类型的 MPDU。改为先夹 `0x7FFFFFFF`
- **修真缺陷 ②**：`build_link_frame` 预按 `cfg.std_version` 反查 cmt_index（ISAC 136B → TMI 16），使 `_ensure_cmt_index` 的「信标按 BPLC 语义反查」特例被跳过 ⇒ 信标帧报「载波映射表索引 超出 4bit 范围：16」。改为只由 `build_fc → _ensure_cmt_index` 解析
- **修真缺陷 ③**：`FrameBuildResult.hex()` 的 `mac_frame` 写成 `mac_header + msdu`，SACK 两者皆 `None` ⇒ `TypeError`；该层字典**无条件求值**，故任何 `hex(层)`（含 `parse_rows` 内的 `hex("app")`）都崩、预览整块空掉。改 None 安全拼接，无该层时抛可读 `FrameBuildError`
- **测试**：新增 `test/test_csg_frame_gen_gui.py`（71 项）；`test_csg_link_frame_gen.py`(176) 入 `CORE_TESTS`，`test_collapsible_section.py`(51) 与前者入 `GUI_TESTS`；`test_protocol_registry.py` 组帧集更新为 `{0,6,7,8,9,12}` 并断言协议9 `preset_mode is None`
- **文档/版本**：`APP_VERSION`/`BUILD_DATE` → 1.23.64 / 2026-09-30、`main_gui.CHANGELOG` 1.23.64（8 条）、两个 `.iss`、README（badge / 功能表 / 组帧与预设页说明 / 文件清单 / 测试命令）、CLAUDE.md（版本 + 标签页可见性）、AGENTS.md §5.7 组帧页 + **陷阱 65** + §10 摘要

### Testing

- [OK] `release_check.py --with-gui`：直接跑 → PASS=114 FAIL=0 WARN=1（唯一 WARN 是 `BUILD_DATE` 未对齐当天，已修）；版本对齐后直接跑 → PASS=114 **FAIL=1 WARN=0**，唯一 FAIL = `test/test_modular_iface.py`，而该测试自身输出 `结果: PASS=430 FAIL=0`、进程退出码 `-1073740791`（= `0xC0000409`）⇒ **陷阱 62 的 fastfail 假红**（`modular_iface*` 未被本次改动触碰，`git status` 可证）。按陷阱 62 用 `pwsh -File` 包一层重跑 → **PASS=115 FAIL=0 WARN=0**，exit 0
- [OK] 新增 `test/test_csg_frame_gen_gui.py` 71 项：SOF/信标/SACK 三型闭环、24 模式全量（每帧 FCCS/PBCS/CRC-32 三项「校验通过」+ 接入指示=1 + MAC 头原始 TEI = FC 源/目的 TEI）、输出层次四档、折叠状态收集/恢复与容错、配置快照往返、协议切换回退、按钮不裁字（`show()` 之后按 `sizeHint` 量）
- [OK] 旁证未回退：`test_csg_new_gen.py`、`test_csg_pbcs_fill_gui.py`(12)、`test_csg_pb_highlight_gui.py`(16)、`test_dlt645_frame_gen_gui.py`(73)、`test_btn_width_fit.py`(66)、`test_button_icons.py`(10)、`test_csg_sequence_gui.py`(37)
- [OK] 独立核对：链路层组帧与解析器 auto 回读闭环（SOF/信标/SACK/多 PB/长短头，FCCS/PBCS/CRC-32 均「校验通过」、TEI oracle）；全部改动文件 `py_compile` 通过；`main_gui.CHANGELOG[0]` 无残留转义符
- [备注] 定位过程中踩到「**没有 QApplication 就构造 QWidget**」= Qt 致命错误（`0xC0000409`、stdout 全空、退出码 `-1073740791`），与陷阱 62 手感完全一致、极易误判为环境问题；已在测试的 `_fresh_gen()` 里固定先建 app

### Notes

- **未提交**：本次改动与上一会话遗留的未跟踪文件（`csg_link_frame_gen.py` / `csg_new_gen_frame_gen.py` / `csg_test_frame_gen_widget.py` / `collapsible_section.py` / 三个新测试 / `.trellis/tasks/09-30-csg-link-layer-frame-gen/`）**均未 commit**，等用户确认后统一提交
- **该任务文档与实际不符（重要）**：`09-30-csg-link-layer-frame-gen/prd.md` / `design.md` 里称作「既有」的 `test_csg_new_gen_frame_gen.py`(144 项) / `test_csg_frame_gen_gui.py`(117 项) **并不存在**，design 要改的 `frame_gen_widget._do_realtime_update_csg` 等三处也从未存在过；「现有页面 465 行」的说法同样无据。本次按**实际代码状态**接线，「复用既有页面」的前提不成立，已在 AGENTS.md §5.7 / 陷阱 65 按事实重写口径
- 工作区根目录遗留 `temp_csg_diff.patch`（只含 `csg_new_gen_parser.py` 的 diff，与本功能无关，上一会话产物），未删除
- 协议9 暂无预设命令库；若要补，需在 `preset_buttons._get_path` 增加 csg 路径并放开组帧页「添加到预设」按钮


## Session 26: 协议9 组帧「仿照报文回填 + 模板」与右栏布局

**Date**: 2026-09-30
**Task**: 协议9 组帧 —— 粘贴现成报文自动回填参数（可存本地模板）+ 响应解析默认收起
**Branch**: `main`

### Summary

按用户需求做两件事：①「实时解析预览」腾空间——响应帧解析对纯组帧场景（协议9）默认收起，加开关随时打开；②**核心**：从官方测试系统拷一帧报文粘进来，自动反解出**全部可识别参数**回填表单，用户只改要变的字段再生成；这套参数可命名存本地，下次「加载模板 → 改关键字段 → 出新帧」。新增纯逻辑 `csg_frame_reverse.py`（反解）+ `csg_frame_templates.py`（存档），组帧页新增「⓪ 仿照报文 / 模板」折叠区。顺带修掉一个**32bit 字段装不进 QSpinBox** 的真缺陷。用户对三个口径的选择：手工 HEX 保真兜底（推荐）/ 模板存完整参数集 + 原始参考报文（推荐）/ 仅协议9 默认收起（推荐）。

### Main Changes

- **反解（`csg_frame_reverse.py`，纯逻辑）**：ED..EE（plc2 / 广西台体）→ 整帧 MPDU → ①FC ②物理块 ③MAC 头 ④MSDU → 应用层帧 → 测试帧 BDU。**取值一律以解析器行为唯一基准**，按「偏移区间」区分 FC(0~15)/物理块头(16~19)/MAC 及以内(≥20)，同名标签（如 `源TEI` 在 FC 与 2.0 扩展里都出现）不串味；长字段（MSDU 负载 / 物理块体 / B 表）的「原始值」列被解析器用 `...` 截断，改为按 `偏移~结束偏移`（第 5 列是闭区间末偏移）从原始字节切。**24 个模式全部可反解**（表61 取模式号高 4 位并回算 `header_len_layout`；2.0 扩展按扩展 ID 分派；A 组取测试数据区频段）
- **回填即逐字节反证**：`_verify_against()` 用**真实组帧路径**重建并与原帧对比；不一致时把原 MSDU 载荷写进 ④ 区「手工载荷」再比一次（保真兜底），提示里明确"此后改应用层/模式参数不影响载荷"；`unmapped` 记录表单表达不了的字段（报文标识符非 `0x0101` 等）。另给「对比当前输出」报告首个不一致字节偏移
- **模板存档（`csg_frame_templates.py`）**：`csg_frame_templates.json`（`app_paths.data_path`，已 gitignore），存完整参数集 + 原始参考报文 + 状态摘要；「临时文件 + `os.replace`」原子写；坏文件宽容（非 JSON / 顶层非对象 / 条目缺字段都只跳过并给原因）。`frame_state()` / `apply_frame_state()` 是 state 唯一口径，**apply 顺序不可改**：先切帧类型/标准版本/模式（它们会重建字段控件）再写字段值
- **修真缺陷：32bit 字段装不进 QSpinBox**。ED 时间戳是真实 Unix 秒量级（`0x68xxxxxx` > `0x7FFFFFFF`），此前上限被夹到 `0x7FFFFFFF` —— 既填不进真实时间戳、回填时 `setValue` 还直接抛 `OverflowError`；信标时间戳/周期同理（陷阱 65 第一条只覆盖了信标）。新增宽整数文本框 `_WideIntEdit`（十进制 / `0x` 十六进制，信号 `textChanged`），并把**所有**回填写值收敛到 `_write_widget_value()`（先夹控件范围再 setValue）
- **右栏布局**：「显示响应解析」复选框 + `resp_group` 引用；`_apply_resp_visibility()` 只覆盖显示状态、不改用户偏好 → 协议9 强制收起、其它协议按 `frame_gen_mode` 之外的原状显示（逐协议核对过：**只有协议9 行为变化**）
- **文档/版本**：1.23.65（APP_VERSION / 两个 .iss / README badge）、`main_gui.CHANGELOG`（7 条）、README（功能表 / 组帧章节 / 文件清单 / 测试命令）、CLAUDE.md、AGENTS.md §5.7 + 陷阱 65 扩写 + §10 摘要

### Testing

- [OK] `release_check.py --with-gui` → **PASS=117 FAIL=0 WARN=0**，exit 0（新登记 3 个测试全部 PASS）
- [OK] 新增 `test/test_csg_frame_reverse.py` **96 项**（纯逻辑）：层次识别 / 24 模式全量反解（应用层帧 + ED+MPDU 两条路径，应用层帧逐字节还原）/ 三型定界符 / BPLC 与 ISAC / 两种 ED 公共头 / ED 32bit 时间戳与信标满 32bit 字段 / 错误路径可读原因 / **变异反证**（改载荷字节 → 反解结果随之变化；改 TEI → 被反解出来）
- [OK] 新增 `test/test_csg_frame_templates.py` **92 项**：存档往返 / 同名覆盖（不重复、保留 created）/ 名称校验 9 类非法字符 / **坏文件宽容**（非 JSON、顶层非对象、空文件、坏条目跳过）/ 原子写不残留 `.tmp` / 数量上限 / 路径契约；每个用例用独立临时文件，不碰真实数据目录
- [OK] `test/test_csg_frame_gen_gui.py` **139 项**（原 71 项，新增）：⓪ 区六段折叠齐备、粘贴整帧 → 回填各层（**ED 32bit 时间戳 > 0x7FFFFFFF 也被正确回填**）、改字段后输出变化且 FCCS/CRC-32 重算通过、**保真兜底**（报文标识符改成 0x0202 → 提示走手工 HEX 且「对比当前输出」报告逐字节一致）、对比报告首个偏移、非法/空输入可读提示、模板存档往返（命令行不通 QInputDialog/QMessageBox，用打桩绕过）、响应解析开关（协议9 默认收起、勾上显示、切走再回来按偏好）、预览表高度
- [OK] 旁证未回退：`test_csg_link_frame_gen.py`(176)、`test_collapsible_section.py`(51)、`test_csg_new_gen.py`、`test_protocol_registry.py`、`test_dlt645_frame_gen_gui.py`(73)、`test_btn_width_fit.py`(66)、`test_csg_pbcs_fill_gui.py`、`test_csg_pb_highlight_gui.py`
- [备注] 排查中再次踩到「没有 QApplication 就构造 QWidget」= `0xC0000409`、stdout 全空（与陷阱 62 手感相同）；已在测试的 `_fresh_gen()` 固定先建 app
- [备注] `test_modular_iface.py` 本轮**间歇性**以 `0xC0000409` 退出（连跑 3 次：1 次崩溃 2 次正常，测试自身始终 `PASS=430 FAIL=0`）⇒ 陷阱 62 记录的「本机已知 MainWindow 关闭期 fastfail」，`release_check` 的总 FAIL 因此在 0/1 之间摆动；该模块本次未被改动（`git status` 可证），`pwsh -File` 包一层**并不能**稳定规避

### Notes

- **未提交**：本会话与上一会话的改动**仍未 commit**（用户未要求提交）
- 交付前逐项核对了三处「只在协议9 生效」：预设页可见性、左栏栈索引、响应解析开关（`preset_mode` 判据逐协议打印对比过）
- 协议9 模板文件是**用户私有运行时数据**，已在 `.gitignore` 加 `/csg_frame_templates.json`
- 已知边界（不是缺陷）：若原帧使用表单未建模的常量（报文标识符非 `0x0101`、业务标识非 `0xF0`、保留位非 0），结构化还原不成立 → 走「手工 HEX 保真」，此时改应用层/模式参数不影响载荷（提示里已写明）

### Build

- `BUILD_DATE` = 2026-09-30（当天）/ `APP_VERSION` = 1.23.65 → `pyinstaller 南网协议解析工具.spec --noconfirm` **一次通过**
- 产物：`dist/南网协议解析工具_v1.23.65_20260930135352.exe`（**98.1 MB**，13:55:48）；文件属性 `FileVersion` / `ProductVersion` = **1.23.65.0**（spec 自动从 `main_gui.APP_VERSION` 生成，与窗口标题同源，无需手工同步）
- **打包前补了 spec 漏项**：`hiddenimports` 少 6 个协议9 组帧模块（`csg_test_frame_gen_widget` / `csg_link_frame_gen` / `csg_new_gen_frame_gen` / `csg_frame_reverse` / `csg_frame_templates` / `collapsible_section`）。性质说明：它们都是**静态 import**，PyInstaller 静态分析本就能找到，**不是必崩**；但该文件的既有约定是「静态 import 也显式声明保险」，缺了就是漏项（其中 4 个是 1.23.64 遗留、2 个是本轮新增）。已补齐；`Analysis-00.toc` 确认 6 个模块**全部进包**，`warn-南网协议解析工具.txt` 里**零** csg/collapsible 相关缺失
- 打包日志告警只有既有噪声、**0 个 ERROR**：`importlib_resources.trees`、SQLAlchemy 可选驱动（`pysqlite2`/`MySQLdb`/`psycopg2`）、pyserial 的 macOS ctypes 导入（`IOKit`/`CoreFoundation`）
- 冒烟：exe 能起来并**跑完整个 import 图**（`try_connect_existing` 在 main_gui 顶层 import 之后才执行，能走到这一步说明冻结尾包模块完整），随后按单实例逻辑把参数交给**正在运行的源码实例**（PID 19724 `python main_gui.py`）并 `exit 0`。**未能以「主实例」身份验证窗口与组帧页** —— 用户当时正开着源码实例，会被抢占；要补需先关掉再跑一次（可通过 `--minimized` 起、确认存活后收掉）

### 1.23.66 — 批量解析工具栏合并成两行

- **需求**：批量解析页「预处理」与「脚本」两行占纵向空间，要求合并到一行
- **⚠ 本会话与另一个会话并发改了同一批文件**（详见本节末「并发收口」）。最终设计以对方方案为准，我在其基础上收口并把文档/数字对齐
- **最终布局**：`row0 = 核心操作(5) + 弹性空隙 + 导出(4) + 帧计数徽章`、`row1 = 预处理: + 命令框 + 保存/删除/执行/帮助 ｜ 脚本: + 脚本框 + 加载/运行/移除/帮助`，两行都是 `FlowLayout(stretch=True)`；解析**进度条与「取消」移到页面底部状态行**（只在解析中出现的瞬态控件）
- **关键发现 ①（否则合并白做）**：4 个导出按钮合计 ~470px，**留在合并行里单行需 ~1700px ⇒ 1366×768 下照样折行**。第一版就是栽在这里（我先把导出留在合并行，实测单行阈值 1820px）。导出移到核心行右端后才真正省下行高
- **关键发现 ②**：可编辑 `QComboBox` 的 `sizeHint()` **把 `placeholderText` 算进宽度** —— 我写的那条 40 字符示例实测 **481px**（比最长的一条命令还宽），把整行顶到 2012px。换成短示例 `如: hex_extract dedup` 后 371 → **250px**。**不要**用 `setMaximumWidth` 压制（会让宽屏剩余宽度全浪费），宽屏吃满整行改由 `FlowLayout` 的权重分配实现
- **`FlowLayout` 新增可选 `stretch` 权重**（对方实现）：`FlowLayout(..., stretch=True)` + `addWidget(w, stretch)` / `addStretch()`，默认关闭 ⇒ 顶部协议组行为不变；「宽屏吃满整行」与「窄屏自动折行、永不重叠」同时成立（`QHBoxLayout` 只有前者、单纯 FlowLayout 只有后者）
- **修复：拉伸与折行共存时的控件重叠** —— 拉伸只改宽度、x 仍按原始 `sizeHint` 排，被拉宽的下拉框会盖住同行右侧按钮（**我在 1920/2560 宽下实测 9~10 处重叠**，如 `QComboBox×保存`/`×删除`/`×脚本:`）。对方 16:19 那次写入用「被拉宽的项把同行后续项一起右推」的 `shift` 累加修好了；我复测确认 2560→760 全宽度**零重叠**
- **实测阈值**（offscreen，`layout.itemAt(i).geometry()` 判行）：窗口 **≥1264px 两行各自一行**（工具栏 52px，原三行 80px ⇒ 净省一行）；1230~1263px 只有 `row1` 折行（82px）；**<1230px 两行都折**（1000px 默认窗口下 104px，比原三行**多** ~24px —— 这是「导出留在工具栏右上角、不改用户习惯」的代价，已写进 AGENTS 陷阱 66）
- **测试**：`test/test_batch_toolbar_layout.py`（**59 项**，入 `GUI_TESTS`）。**刻意不绑定「哪个按钮在哪一行」**，只守布局性质：两行且都是 FlowLayout、`stretch` 真生效（下拉框宽于 `sizeHint`）、**1366 基准两行各自一行**、宽窗每行一行、徽章贴行右端、瞬态控件不在工具栏行内、命令框 `sizeHint() ≤ 320`、**2560→760 共 13 个宽度 × 两行零重叠**、相邻项不重叠
- **测试踩坑（保留）**：①跨 `QTabWidget` 页面**不能用 `mapTo(win)` 判行** —— offscreen 下量出 x=2563 这种超出窗口的离谱坐标；要用 `layout.itemAt(i).geometry()`；②行数要按**容差聚类**（同一行内各项高度不同，`top()` 会差 55/57/61 几像素，直接 `set()` 会误判成多行）；③`QLabel` 是 `QFrame` 子类，数分组竖线必须用**精确类型** `type(w) is QFrame`

#### 并发收口（重要，供后续参考）

- 现象：本会话工作期间，仓库根目录出现 6 个**不是我建的** `scratch_*.py`（`scratch_measure_toolbar.py` 15:52、`scratch_combo_min.py` 15:53、`scratch_combo_live.py`/`scratch_combo_min2.py` 15:54、`scratch_min_override.py` 15:56、`scratch_ph.py` 16:01），`main_gui.py` 里也出现非我所写的改动；连续两次 `git diff` 行号不一致 ⇒ 判定有并发写入
- 处置：先**探活**（连测 3 次 `main_gui.py` 的 SHA256 + mtime，90 秒内未变、最后写入 16:19 ⇒ 对方已停手），再把**当前工作区当作基线**收口，不擅自回退对方改动
- 教训：**未跟踪文件也会被并发改写**。我用 `write` 覆盖 `test/test_batch_toolbar_layout.py` 时，把对方扩到 38 项的版本（含「1366 基准」「徽章贴行右端」「命令框 `sizeHint` 上限」三条断言）一并覆盖且**无法从 git 恢复**（该文件从未入库）。已按对方 CHANGELOG/AGENTS 的文字记录把那三条断言补回（现 59 项），并把文档里所有「38 项」修正为 59 项。**下次动未跟踪文件前先读一遍**
- 对方产物状态：`main_gui.py` 工具栏 + `FlowLayout` stretch + `main_gui.CHANGELOG` 1.23.66 + AGENTS 陷阱 66/§10 均已由对方写好，我只修正了测试项数与（journal 这节）描述；对方的 `scratch_*.py` 仍在仓库根目录未删（非我所建，等用户决定）

### exe 抗杀毒加固（清单 + UPX + 元数据）

- **需求**：用户希望减少杀毒软件拦截/锁文件，问「添加软件相关信息」是否有用
- **做了什么（`南网协议解析工具.spec`）**：
  - `EXE(manifest=...)` 补 **`assemblyIdentity`**（`liruitao.SouthNetworkProtocolAnalysisTool` + 版本号）——这是默认清单里**唯一缺**的一项，"谁家的什么软件什么版本"的汇编层身份
  - `upx=True` → **`upx=False`**（显式关闭）
  - 版本资源补 `Comments`（用途说明）
- **⚠ 踩坑（重要）**：`PyInstaller.utils.win32.winmanifest.create_application_manifest()` 是**整份替换**、不是合并（只额外保证 `requestedExecutionLevel` 与 Common-Controls 两项）。第一版我只传 `<assemblyIdentity>`，结果把默认清单的 **`supportedOS`（5 条）与 `longPathAware` 一起冲掉** —— 构建后逐项核对产物清单才发现（`longPathAware` 丢了会让 >260 字符路径失效）。改为在 spec 里写**完整清单**（assemblyIdentity + trustInfo/asInvoker + compatibility/5×supportedOS + longPathAware + Common-Controls），比默认只多一条 assemblyIdentity
- **实测澄清**：`upx=True` 其实**一直没生效** —— PyInstaller 只在 `CONF['upx_available']` 为真时才用 UPX，本机 PATH 上只有 `upx.BAT`（它不认），构建日志里没有 `UPX is available` 那行、产物里 `UPX!` 标记 0 处。写死 `False` 是去掉"以后 UPX 真可用时会静默启用"的隐患
- **产物**：`dist/南网协议解析工具_v1.23.66_20260930170014.exe`（98.1 MB，sha256 `d3ea241fd77b2b78…`）。核对：清单五项齐全（`assemblyIdentity` / `requestedExecutionLevel` / `longPathAware` / `Common-Controls` / `supportedOS`×5 全 True）、`FileVersion`/`ProductVersion` 1.23.66.0、`Comments` 已填、`UPX!` = 0
- **冒烟**：新 exe 起动后正常走到单实例转交（用户的源码实例在跑）`exit 0` ⇒ 清单合法、启动路径正常（清单非法会以 `0xC0000142` 类失败，不会是 0）。中间那版清单不完整的产物已删除
- **如实结论**：清单/元数据只让 exe"看起来像正规程序"，**不是**误报解药。被拦的真实主因是 ①没有代码签名 ②onefile 自解压到 `%TEMP%\_MEIxxxxx` 再执行（与释放器同构）③每次重建哈希都不同、云信誉归零。已把这条现实边界写进 **AGENTS §2.2 第 5/6 条**
- **顺带发现的既有问题**：`南网解析工具.iss` 的 `[Files]` 取的是 `dist\协议解析工具\协议解析工具.exe`（**文件夹形态**），但该目录**停更在 2026-08-11**，当前没有任何 spec 会重新生成它 ⇒ 用该 .iss 打包会装到 8 月那份旧程序。要修就得给 spec 补一条 onedir（COLLECT）产物；这同时也正是抗杀毒最有效的结构性改动，等用户定夺


## Session 25: 协议8/6 前导 FEH 唤醒字节合规修复

**Date**: 2026-10-13
**Task**: 协议8/6 前导 FEH 唤醒字节合规修复
**Branch**: `main`

### Summary

按 DL/T 698.45 §6.3.1 b) 与 DL/T 645 §5.3.1 容忍帧首 FEH 前导：新增 wakeup_prefix.py 单源，协议8/6 解析器入口剥离 + 表格首行前导行 + 帧内行偏移整体位移 + 两校验器同预处理；蓝牙分包日志给出单包上限/MTU 来源。新增 test_wakeup_fe_prefix.py（73 项）入 CORE_TESTS，4 条变异反证。CHANGELOG/AGENTS/README/.iss 版本条目与 1.23.64~75 未提交批次同文件交错，留待该批提交。

### Git Commits

| Hash | Message |
|------|---------|
| `3da40c1` | (see git log) |

### Status

[OK] **Completed**


## Session 26: 协议9 2.0 测试扩展 0x0009（报文聚合传输测试模式）

**Date**: 2026-10-13
**Task**: 协议9 2.0 测试扩展 0x0009（报文聚合传输测试模式）
**Branch**: `main`

### Summary

按用户提供的《宽带双模通信模块（通感一体物联版）相关测试命令定义_260922》给协议9 补齐 2.0 测试扩展 0x0009「报文聚合传输测试模式」（数据区 1 字节 = 报文聚合数目，8bit）。文档 1.4 逐项核对后确认唯一缺口就是 0x0009（0x0001~0x0008 早已支持；第 2 章表61 模式 1~13 文档自标「原有」且代码已覆盖）。改动落在四处：解析映射+专属函数+分派表、组帧映射+builder+_EXT_BUILDERS+test_modes()（组帧页与仿照回填的唯一入口）、csg_frame_reverse._fill_ext 回填分支、摘要自动生效（补断言）。字节口径沿用 ext_data[x] = 文档字节 x+3。

### Main Changes

- csg_new_gen_cmd_payloads：_TEST_EXT_ID_MAP[0x0009] + _parse_test_ext_0009（整字节，无位域）+ 分派表；数据域缺失时给 ❌ 行不返回空表
- csg_new_gen_frame_gen：TEST_EXT_ID_MAP / build_ext_0009(agg_count=1) / _EXT_BUILDERS / test_modes() 新增 ext_agg（模式数 24 → 25）
- csg_frame_reverse._fill_ext：0x0009 → params['agg_count']，粘贴现成帧可「回填 → 原样重建」（unmapped 为空）
- csg_test_frame_gen_widget：三处互不一致且过期的模式数量文案（26/24/26）→ 模块级 _MODE_COUNT = len(fg.test_modes())
- 文档与版本（未随本次提交，留在工作区）：main_gui APP_VERSION 1.23.76→1.23.77 + CHANGELOG 1.23.77 条目、AGENTS §1/§5.7/§10、README（徽章/版本/功能表/模块表/更新记录）、两个 .iss 已用 --sync-iss 对齐

### Git Commits

| Hash | Message |
|------|---------|
| `74b305c` | (see git log) |

### Testing

- [OK] python test/test_csg_test_ext_0009.py → 76 项断言 / 0 失败（映射与模式清单、0x00·0x01·0x05·0xFF golden 含偏移 20、数据域缺失容错、未登记扩展ID 0x000A 护栏、组帧逐字节与越界、app 与 auto 两级闭环、仿照回填逐字节重建、摘要片段）
- [OK] 回归全绿：test_csg_new_gen / test_csg_summary / test_csg_frame_reverse / test_csg_frame_templates / test_csg_link_frame_gen / test_csg_batch_prefix / test_csg_batch_parse_level / test_csg_hrf_mac；GUI test_csg_frame_gen_gui(139 项) 与 test_collapsible_section(51 项)
- [OK] 变异反证 3 条：解析位宽取低 4bit → 3 项红；组帧数据域写 2 字节 → 5 项红；反解删 0x0009 分支 → 5 项红（每条跑完 md5 逐字节还原）
- [OK] python release_check.py --with-gui → PASS=133 FAIL=0 WARN=0（APP_VERSION / CHANGELOG / README 徽章 / .iss 四项一致）；test_modular_iface.py 首跑命中已知间歇 0xC0000409（PASS=430 FAIL=0，重跑 rc=0），与本次改动无关

### Status

[OK] **Completed**

### Next Steps

- 版本/文档四件套（main_gui.py、AGENTS.md、README.md、两个 .iss）随发版批次提交——HEAD 上它们落后工作区数百~数千行（含其它会话在途内容），单独摘取会与 release_check 的「CHANGELOG 顶部版本 = APP_VERSION」硬校验冲突
- 可选：同族 csg_link_frame_gen.py / csg_frame_templates.py / collapsible_section.py 仍整体未入库（另会话 1.23.64/65 批次），与 csg_test_frame_gen_widget.py 属同一功能集


## Session 27: 串口工具：协议特征断帧认前导 FEH + 可调断帧超时

**Date**: 2026-10-13
**Task**: 串口工具：协议特征断帧认前导 FEH + 可调断帧超时
**Branch**: `main`

### Summary

用户现场报障：协议 8 下同一帧被切成两条 [RX]。实测根因是分帧函数一律要求首字节 0x68，前导 FE 使 frame_length_for 返回 0、_frame_incomplete 也判 False → 退回 10ms 静默窗口把首片单独刷出（1.23.76 只保证链路层能解析，帧表/统计/匹配窗口仍碎）。本次让 68 家族分帧认前导 FE（复用 wakeup_prefix单一来源、返回值含前导 ⇒ 三处调用点零改动），并新增「断帧设置」把 4 个断帧超时与断帧方式交现场可调，另给出「此刻按什么断帧」的自查说明行。

### Main Changes

- serial_tool_widget：_wakeup_base + 68 家族分帧（frame_length_for / declared_frame_len / _frame_incomplete）认前导 FE，返回值含前导；HDLC/Wrapper 不加
- 新增断帧设置 5 键（rx_framing_mode + 4 个超时），默认 = 原常量 ⇒ 只新增键、CONFIG_VERSION 不动；FRAME_TIMEOUT_RANGES 是 UI 与 merge_params 的唯一范围来源
- timeout_only 在 _on_raw_data / _flush_raw_display / _flush_raw_display_now 三处统一跳过结构路径；_log_framing_summary 只在设置变更/协议变化/每轮开始输出
- test_wakeup_fe_prefix：单一来源白名单加入 serial_tool_widget.py（分帧层复用而非另写扫描）
- 文档与版本（未随本次提交，留在工作区）：main_gui APP_VERSION 1.23.77→1.23.78 + CHANGELOG、AGENTS §3/§8 陷阱 59 与 75/§10、README（徽章/版本行/串口通信行/更新记录）、两个 .iss 已 --sync-iss；spec §7c

### Git Commits

| Hash | Message |
|------|---------|
| `4a94111` | (see git log) |

### Testing

- [OK] test_serial_proto_frame.py（147 项）+ test_serial_tool_widget.py（501 项）全绿；现场帧 14+25 两块交付、块间隔 50ms（> 字节静默 10ms）→ 只出 1 行 39 字节
- [OK] 变异反证 3 条：不跳前导 FE → proto 9 红 / widget 4 红（其中「首块后不输出」失败即用户看到的断帧）；返回长度不含前导 → 4+4 红；断帧方式失效 → 3 红；每条跑完 md5 逐字节还原
- [OK] release_check.py --with-gui → PASS=133 FAIL=0 WARN=0（APP_VERSION/CHANGELOG/README 徽章/.iss 四项一致）

### Status

[OK] **Completed**

### Next Steps

- 版本/文档四件套随发版批次提交（HEAD 上落后工作区数千行、与 release_check 的版本硬校验强耦合）
- 可选加固：test_dlt645_sim_lme_query.py / test_dlt645_sim_event_word.py 的「串口回环（COM1↔COM2，可选）」段在端口被占用时会直接判 FAIL（本次见到 COM1 PermissionError(13)，同期另一进程持 COM9）——建议改为端口不可用时明确跳过，避免门禁被硬件占用误伤


## Session 28: 蓝牙工具：特征码自动优选 + 一键探测 + 按设备记忆

**Date**: 2026-10-13
**Task**: 蓝牙工具：特征码自动优选 + 一键探测 + 按设备记忆
**Branch**: `main`

### Summary

用户诉求：软件主要按 HEX 收发报文，给一堆特征码让用户挑体验很差，要能更快收发。定位到旧 `_auto_pick` 取设备枚举顺序里第一个可用写/通知码（实测常落到 2A00 设备名 / 2A19 电量 / DFU）。本次做三件事：① 按「同码可写可通知 > 厂商透传族谱 > 名称含 tx/rx/串口」打分优选并降权标准 GATT/OTA（打分表只在 bluetooth_core 一处）；② 新增「自动探测」按钮，按打分顺序逐个「订阅 → 写探测帧 → 等回包」，命中即锁定、失败逐条给原因、全败恢复原选择；③ 按设备地址记忆 char_map（换设备自动重新优选）。为使探测时序正确新增 bluetooth_worker.subscribe_finished。

### Main Changes

- bluetooth_core：rank_characteristics / pick_auto / probe_candidates / ProbeSession / resolve_probe_payload（parse 由界面注入）/ char_map 记忆 + settings 三个新键（默认 = 原值，CONFIG_VERSION 不动）
- bluetooth_worker：subscribe_finished 信号（订阅失败与空接收通道两条路径都发）
- bluetooth_tool_widget：连接后「按地址沿用 → 打分优选」；换设备清掉上一台的选择；探测按钮 + QTimer 分步驱动（仅 session.step 变化才推进）；全败恢复；状态行收发摘要；对话框置顶+预选+不可用方向文字标注
- 文档与版本（未随本次提交，留在工作区）：main_gui APP_VERSION 1.23.78→1.23.79 + CHANGELOG、AGENTS §3/§8 陷阱 69/§10、README（徽章/版本行/蓝牙功能行/更新记录）、两个 .iss 已 --sync-iss；spec §7d

### Git Commits

| Hash | Message |
|------|---------|
| `601a8ba` | feat(蓝牙工具): 特征码自动优选 + 一键探测 + 按设备记忆（连上即可收发） |

### Testing

- [OK] test_bluetooth_core 116 项 / test_bluetooth_worker 81 项 / test_bluetooth_widget 169 项 / test_bluetooth_tab_wiring 36 项 全绿
- [OK] 变异反证 3 条：打分排序失效 → 12 项红（自动优选明确变回 0x2A19）；订阅失败也照写 → 3 项红；记忆写同一全局键 → 3 项红；每条跑完 md5 逐字节还原
- [OK] 真机（offscreen + 假 worker）smoke：连上→自动优选 0xFFE1（发送/接收）+ 依据日志 + 状态行摘要 + 按地址记忆；点探测→写出发送框帧→收到回包→锁定记忆；对话框 0xFFE1 置顶预选、「0x2A00 …（不可写）」文字标注
- [OK] release_check.py --with-gui → PASS=131 FAIL=2，两项失败均为 test_dlt645_sim_lme_query / test_dlt645_sim_event_word 的「串口回环（COM1↔COM2）」段：实测 COM1/COM2 同时被 PID 8096（用户正在运行的主程序实例）占用（PermissionError13），与本改动无关（两测试不导入蓝牙模块）；同日早前 PASS=133 FAIL=0 已证

### Status

[OK] **Completed**

### Next Steps

- 可选加固：把 test_dlt645_sim_lme_query.py / test_dlt645_sim_event_word.py 的串口回环段改为「端口打不开时明确跳过」，避免门禁被硬件占用误伤（这两次均因此变红）
- 版本/文档四件套随发版批次提交（与前两个任务同处置：HEAD 落后数千行且与 release_check 版本硬校验强耦合）


## Session 29: 蓝牙工具：MTU/写上限实时化（连接后轮询 + 发送前重读）

**Date**: 2026-10-13
**Task**: 蓝牙工具：MTU/写上限实时化（连接后轮询 + 发送前重读）
**Branch**: `main`

### Summary

修「同一台设备有时 20 字节、有时 512 字节」：ATT_MTU 由 OS 异步协商，旧实现只读一次快照。新增 mtu_is_unnegotiated 判据 + 连接后轮询 + 每次发送前 _refresh_live_limits + 独立信号 mtu_updated

### Main Changes

- bluetooth_core: 新增 MTU_DEFAULT/MTU_POLL_INTERVAL/MTU_POLL_TIMEOUT/mtu_is_unnegotiated（判据单一来源）
- bluetooth_worker: _char_objects 持活对象、_refresh_live_limits、_poll_mtu_if_needed（connected 之后）、_write_coro 发送前重读、新信号 mtu_updated、断开清空
- bluetooth_tool_widget: _mtu_text 单一文案、_on_limits_updated（只更新读数、不重订阅）、CharacteristicSelectDialog.refresh_chars、模态期间交接引用

### Git Commits

| Hash | Message |
|------|---------|
| `231d575` | (see git log) |

### Testing

- [OK] test_bluetooth_core 129 项 / test_bluetooth_worker 106 项 / test_bluetooth_widget 177 项 / test_bluetooth_tab_wiring 36 项 全绿
- [OK] 变异反证 4 条（去轮询 5 红、去发送前刷新 6 红、判据改 < 2 红、对话框刷新失效 1 红）逐条实测变红后逐字节还原
- [OK] release_check.py --with-gui：PASS=130 FAIL=3（3 项既有环境红：COM1 被占用 ×2、test_modular_iface Qt 退出期 fastfail 而自身 PASS=430 FAIL=0）

### Status

[OK] **Completed**

### Next Steps

- 版本/文档四件套（main_gui APP_VERSION=1.23.80+CHANGELOG、AGENTS §8 陷阱 69、README、两个 .iss）留在工作区，随发版批次提交


## Session 30: 蓝牙自定义按钮：按协议替换地址 + 重算校验（发送时生效）

**Date**: 2026-10-13
**Task**: 蓝牙自定义按钮：按协议替换地址 + 重算校验（发送时生效）
**Branch**: `main`

### Summary

新增 frame_addr_fix.py（六协议地址定位+校验重算，全部复用既有实现）；按钮可绑 protocol/addr，发送时替换、发送框保持原模板；失败不发

### Main Changes

- frame_addr_fix.py: fields_for/parse_address（写法双认）/apply（自证→定位→替换→复用协议实现重算）；协议模块按需导入（698 依赖可选 crcmod）
- bluetooth_core: normalize_button 宽容保留 protocol/addr（旧按钮零影响）
- bluetooth_tool_widget: 对话框协议下拉+动态地址框+预览；_apply_button_address 只在发送时替换；失败弹框+日志不发；tooltip 标注
- v1 支持 0/6/7/8/13/14；无地址域/福建增补/长度不符/原帧校验不符 → 可读拒绝（先自证再改）

### Git Commits

| Hash | Message |
|------|---------|
| `acf4366` | (see git log) |

### Testing

- [OK] test_bluetooth_addr_fix.py 96 项（六协议真帧 oracle：替换后该协议校验器 0 fail）；core 145 / widget 200 / worker 106 / wiring 36 全绿
- [OK] 变异反证 4 条（645 不重算 2 红 / 地址不反转 9 红 / 698 不重算 HCS+FCS 2 红 / 不校验长度 2 红）逐字节还原 md5 一致
- [OK] 端到端冒烟：真 worker+真页面 offscreen，点绑定按钮写出 68 33 ... 33 E5 16，发送框仍为原始模板
- [OK] release_check.py --with-gui：PASS=132 FAIL=2 WARN=0（2 项 COM2 被运行实例占用，既有环境红）

### Status

[OK] **Completed**

### Next Steps

- 版本/文档四件套（main_gui APP_VERSION=1.23.81+CHANGELOG、AGENTS §8 陷阱 69、README、两个 .iss、spec §7f）留在工作区，随发版批次提交


## Session 31: 蓝牙自定义报文区空间治理（封顶+滚动+折叠+竖向分栏）

**Date**: 2026-10-14
**Task**: 蓝牙自定义报文区空间治理（封顶+滚动+折叠+竖向分栏）
**Branch**: `main`

### Summary

64 个按钮不再压没日志：封顶 3 行+内部滚动、CollapsibleSection 折叠（记忆状态）、右栏竖向 QSplitter 可拖拽（尺寸记忆）

### Main Changes

- bluetooth_core: CUSTOM_ROWS_MAX / RIGHT_SPLIT_DEFAULT,RANGE / normalize_right_split / merge_settings 两个新键
- bluetooth_tool_widget: QScrollArea 封顶（按 sizeHint 实算，字号变化重算）+ CollapsibleSection + 竖向分栏（尺寸只在真实布局后采集）

### Git Commits

| Hash | Message |
|------|---------|
| `02cd050` | feat(蓝牙工具): 自定义报文区空间治理（封顶 3 行 + 内部滚动 + 可折叠 + 竖向分栏） |

### Testing

- [OK] widget 219 项（+18 新节 [14]：封顶/滚动/不压扁/日志高度/收起展开/分栏记忆与重启恢复）、core 161 项（+16 配置宽容）
- [OK] 变异反证 4 条（不套用封顶 1 红 / 封顶行高写死 1 红 / 不采集分栏 2 红 / 不恢复折叠态 1 红）逐字节还原 md5 一致
- [OK] 冒烟：64 按钮 → 滚动区 76px 封顶 + 448 滚动范围（不封顶对照 169px）；收起后 23px
- [OK] release_check --with-gui：PASS=131 FAIL=2（COM 口被运行实例占用，既有环境红）

### Status

[OK] **Completed**

### Next Steps

- 版本/文档四件套（APP_VERSION=1.23.82+CHANGELOG、AGENTS §8 陷阱 69、README、两个 .iss、spec §7g）留在工作区随发版批次提交


## Session 32: 蓝牙自定义报文区修复：按钮随可用空间自动 + 编辑工具栏常驻

**Date**: 2026-10-14
**Task**: 蓝牙自定义报文区修复：按钮随可用空间自动 + 编辑工具栏常驻
**Branch**: `main`

### Summary

修用户复核的两个缺陷：腾出空间后按钮仍只 3 行+滚动条 / 编辑按钮被折叠藏起来；按钮区改为内容驱动高度（空间够就全显示），工具栏移出折叠区常驻

### Main Changes

- bluetooth_core: CUSTOM_ROWS_MAX(3) → CUSTOM_MIN_ROWS(1)（下限 1 行；上限按内容算）
- bluetooth_tool_widget: 新增 ButtonScrollArea（minimumSizeHint 由本页给定，避免内层网格最小高度透传给分栏器）+ _custom_scroll_limits/_apply_custom_scroll_limits + 去掉下半区尾部 addStretch + 工具栏移出折叠区 + 收起时锁 Maximum 尺寸策略

### Git Commits

| Hash | Message |
|------|---------|
| `8d33eb1` | (see git log) |

### Testing

- [OK] widget 221 项（[14] 重写：腾出空间后无滚动条 / 只有装不下才滚动 / 默认分栏日志不被挤 / 折叠后编辑按钮仍可见 / 分栏记忆与重启恢复）、core 161 项
- [OK] 变异反证 4 条（上限改回固定封顶 2 红 / 工具栏放回折叠内容 3 红 / 不设最小高度 1 红 / 不采集分栏尺寸 2 红）逐字节还原 md5 一致
- [OK] 冒烟：10 按钮+腾出空间 → 96px 滚动条 0；64 按钮 → 396px/滚动 128；默认分栏 64 按钮 → 日志 496px；收起 → 23px 且工具栏可见；对照旧实现 3 行+滚动条 16
- [OK] release_check --with-gui：PASS=130 FAIL=3（2 项 COM 口占用 + modular_iface Qt 退出期 fastfail，既有环境红）；BUILD_DATE 已更新为 2026-10-14 以清掉 WARN

### Status

[OK] **Completed**

### Next Steps

- 版本/文档四件套留在工作区随发版批次提交（1.23.82 的 CHANGELOG/README 条目已按修正后行为改写）


## Session 33: 串口工具批量替换通信地址（复用 frame_addr_fix + 撤销）

**Date**: 2026-10-14
**Task**: 串口工具批量替换通信地址（复用 frame_addr_fix + 撤销）
**Branch**: `main`

### Summary

串口工具命令表新增「替换地址」：对勾选/全部命令按所选协议替换地址域并重算校验，写回表内 data_hex（复用 frame_addr_fix，单一来源）；三态 ok/kept/skipped；前导 FEH 只对协议 6/8 剥/恢复；可选写协议列与同步替换预期响应（仅纯 HEX 写法且能自证）；汇总弹框三态计数 + 撤销本次替换。测试 test_serial_addr_fix.py 104 项 + test_serial_tool_widget.py 段[35] 536 项；变异反证 5 条全红后逐字节还原；release_check --with-gui PASS=133 FAIL=2 WARN=0（2 项为 COM1/COM2 串口回环环境红）。任务 10-14-serial-batch-addr 已归档。

### Git Commits

| Hash | Message |
|------|---------|
| `e97b145` | (see git log) |

### Status

[OK] **Completed**


## Session 34: 蓝牙自定义按钮：按协议类别批量替换地址

**Date**: 2026-10-14
**Task**: 蓝牙自定义按钮：按协议类别批量替换地址
**Branch**: `main`

### Summary

自定义报文区新增「批量地址…」：选协议→默认勾选该协议按钮→填一次地址→一次写入；逐按钮用自己的报文预检（失败默认不勾、强行勾选二次确认后跳过）；支持批量清除绑定；抽取 frame_addr_fix 共享校验入口

### Main Changes

- frame_addr_fix: +addr_lengths_for_frame(frame) +check_values(protocol, values, frame)（单一来源，单按钮对话框改调之，行为文案不变）
- bluetooth_tool_widget: +BatchAddressDialog（只产补丁，写回统一走 _set_buttons）+_on_custom_batch_address +工具栏「批量地址…」（6 按钮、去掉行内提示标签）

### Git Commits

| Hash | Message |
|------|---------|
| `1171fbc` | (see git log) |

### Testing

- [OK] test_bluetooth_addr_fix.py 111 项（[6] 共享入口边界 + 与 apply 同源对拍）；test_bluetooth_widget.py 270 项（[16]/[16b] 对话框直测 + 端到端写回/tooltip/日志/落盘/发送用新地址/清除还原 + 工具栏宽度 + [15] 反例）
- [OK] 变异反证 4 条：默认勾选全勾 9 项红 / 只选本协议改全选 5 项红 / 跳过时不弹二次确认 2 项红 / 清除只删 protocol 1 项红，逐字节还原 md5 一致
- [OK] 冒烟（offscreen）：默认只勾 1/4、坏 HEX 行标原因且默认不勾、强行勾选→二次确认→跳过、清除模式补丁 protocol=None、10/14/16/24 号字 6 按钮全不裁字
- [OK] release_check --with-gui：PASS=131 FAIL=4（2 项 .iss 版本不一致已用 --sync-iss 修好 + 2 项 COM 口被运行实例占用的既有环境红）→ 修后 --sync-iss 运行 PASS=121 FAIL=2 WARN=0

### Status

[OK] **Completed**

### Next Steps

- 版本取 1.23.84（1.23.83 已属并行任务的串口工具批量替换地址）；版本/文档四件套留在工作区随发版批次提交


## Session 35: 推送到 GitHub（排除参考项目/敏感文件）+ 编译 exe 1.23.84

**Date**: 2026-10-14
**Task**: 推送到 GitHub（排除参考项目/敏感文件）+ 编译 exe 1.23.84
**Branch**: `main`

### Summary

把工作区项目源码+文档全量推送到 GitHub（排除 1.3GB 参考项目 蓝牙转串口工具02 与运行时敏感文件），随后编译 Windows exe

### Main Changes

- gitignore 新增：/蓝牙转串口工具02/（1.3GB 参考学习项目）、/llm_preprocess_config.json（LLM API 配置可能含密钥）、/admin_config.json、/reflex_web/reflex_web/data/（反馈库+用户上传）、/dlt645_sim_data.json、/AGENTS.md.backup.*、/_tmp_*.py、/.aoci/、/aoci*.txt、/.acl-recovery/（提交 c2c5e05）

### Git Commits

| Hash | Message |
|------|---------|
| `0eff521` | (see git log) |

### Testing

- [OK] 推送前检查：工作区敏感串扫描（sk-/api_key 模式）0 命中；暂存集 >3MB 文件 0 个；待推 blob 261 个 14.4MB
- [OK] 推送结果：86949fe..0eff521 main -> main（fast-forward，34 提交）；复核远程树不含 蓝牙转串口工具02/llm_preprocess_config/admin_config/feedback.db/dlt645_sim_data/aoci.txt
- [OK] 编译：pyinstaller 南网协议解析工具.spec --noconfirm → EXIT=0，dist/南网协议解析工具_v1.23.84_20261014160516.exe（104,480,306 字节，16:08），FileVersion/ProductVersion=1.23.84.0；7 条 WARNING 均为可选后端/驱动（bleak corebluetooth、pysqlite2/MySQLdb/psycopg2、macOS 框架路径）

### Status

[OK] **Completed**

### Next Steps

- 如需发给用户/发布：dist 下该 exe；Web 版发布走 reflex_web/build_embedded_deploy.py


## Session 36: 协议8 698.45 文件传输升级（启动传输/写文件/执行升级）+「升级」页

**Date**: 2026-10-15
**Task**: 协议8 698.45 文件传输升级（启动传输/写文件/执行升级）+「升级」页
**Branch**: `main`

### Summary

新增 dl_t698_45_upgrade.py（纯逻辑）+ dlt698_upgrade_widget.py（仅协议8 可见的升级页）+ frame_deframe.py（分帧单一来源）；修 dl_t698_45_axdr 三处口径（bit-string 按位、定长时间类型不带长度域、time 3 字节）并收口 frame_gen_widget/reflex_web 的 A-XDR 自定义模式；协议口径按 doc 实帧逐字节验证（62 字节启动升级帧全等）；trellis-check 复核修掉 3 处阻塞级缺陷（RX 重同步卡死/传输中改输入/清除后门控不复位）；release_check --with-gui PASS=138 FAIL=0 WARN=0

### Git Commits

| Hash | Message |
|------|---------|
| `6a2efea` | (see git log) |

### Status

[OK] **Completed**


## Session 37: 协议8升级页：TX/RX 日志帧显示口径（小帧整帧 / 大帧中间省略）

**Date**: 2026-10-15
**Task**: 协议8升级页：TX/RX 日志帧显示口径（小帧整帧 / 大帧中间省略）
**Branch**: `main`

### Summary

用户报障「TX 日志只显示了部分，应该显示全部的帧内容」：启动传输那条 62 字节的帧原被截到 48 字节（尾部校验值/结束符看不到）。改为 ≤200B 整帧打印、>200B 头尾各 100B + 中间 ... + (共 N 字节)。顺带补 .gitignore 的 dlt698_upgrade_config.json / tcp_monitor_config.json。任务是 1.23.85（未发版）的收尾修订，不 bump 版本号。

### Main Changes

- dlt698_upgrade_widget.py：HEX_LOG_LIMIT 48→200；fmt_hex 由「只显前段」改为「≤limit 整帧 / >limit 头尾各半 + ' ... ' + (共 N 字节)」
- test/test_dl698_upgrade_gui.py：194→202 项（fmt_hex 边界矩阵 + 真实日志行断言 + tx_hex_tokens/tx_line 两个测试助手）
- .trellis/spec/frontend/component-guidelines.md §7j 增「TX/RX 日志帧显示口径」契约条
- .gitignore：补 /dlt698_upgrade_config.json、/tcp_monitor_config.json（运行时用户本地配置，同类漏配）
- main_gui.py CHANGELOG（1.23.85 条目追加 + 测试数 194→202）与 AGENTS.md §5.6 同款说明，按本仓惯例**留工作区**随发版批次提交

### Git Commits

| Hash | Message |
|------|---------|
| `0af3f87` | (see git log) |
| `eb0cc41` | (see git log) |

### Testing

- [OK] test/test_dl698_upgrade_gui.py 202 项全绿（RC=0）；test/test_dl698_upgrade.py 225 项、test/test_dl698_upgrade_tab_wiring.py 29 项 PASS=… FAIL=0
- [OK] 变异反证 2 条：HEX_LOG_LIMIT 改回 48 → 4 项变红；去掉尾段（退回只显前段）→ 3 项变红；还原后 md5 逐字节一致
- [OK] 真实输出取证（新进程）：600B 块 → 634 字节写文件帧头部含 68/APDU 07 01/OMD F0 01 08 00/块序号 00 29，尾部 00 39 86 16，显示 token 恰 200
- [OK] release_check.py --with-gui：PASS=135 FAIL=3 WARN=0；3 项 FAIL 是 test_quick_parse_panel / test_app_icon_path / test_button_icons 的退出期 RC=0xC0000409（断言全绿，AGENTS 陷阱 62 已知本机 Qt offscreen 退出期 fastfail），与本改动无关

### Status

[OK] **Completed**

### Next Steps

- 发版批次：把 main_gui.py(APP_VERSION/CHANGELOG)、AGENTS.md、README.md、两个 .iss 一起提交；bump 后跑 python release_check.py --sync-iss


## Session 38: 光伏升级：tab 改名 + 可选读版本信息（通用 43000300 / 厂家扩展内部版本 FF100400）

**Date**: 2026-10-15
**Task**: 光伏升级：tab 改名 + 可选读版本信息（通用 43000300 / 厂家扩展内部版本 FF100400）
**Branch**: `main`

### Summary

用户需求两批：①「升级」tab 改名「光伏升级」；②页面增加可选的升级前/升级完成后读版本信息（默认通配 AAAAAA，命令 = 通用 698.45 读取 43000300）；③追加：内部版本（厂家扩展 FF100400）也要能选。两条现场实帧都被 build_read_version 逐字节复现，响应判定按所选 OAD 互斥；读版本失败刻意不阻断升级。

### Main Changes

- dl_t698_45_frame_gen.py：generate_get_request_normal 新增可选 time_tag_none（默认 False ⇒ 既有调用方逐字节不变，复核 180 组参数对拍 HEAD）
- dl_t698_45_upgrade.py：OAD_VERSION/OAD_INTERNAL_VERSION + build_read_version + check_get_response（HCS/FCS+0x85+GetResponseNormal+OAD 回显+Get-Result CHOICE 00=DAR/01=数据）
- dlt698_upgrade_widget.py：两个勾选项（默认不勾/落盘/传输中冻结）+「读版本内容」下拉（键 common/internal，OAD 字节只在协议模块一份）+ 状态机 ver_pre/ver_post + 非阻断失败 + 版本内容进日志
- main_gui.py：tab 文案「升级」→「光伏升级」（**只提交这一处 hunk**；APP_VERSION/CHANGELOG 属版本批次留工作区，剩 2 个 hunk）
- 测试：test_dl698_upgrade.py 225→259（A10/A11）、test_dl698_upgrade_gui.py 194→252（[17]~[20]）、tab_wiring 标题断言 + yw645 可见性矩阵文案
- 文档：spec §7j 新增「读版本信息 / 两条命令 / tab 改名」契约条，AGENTS §1/§3/§5.6/§6/§10 与 README（功能节 + 更新记录）同步 —— 后两者按惯例留工作区随发版批次

### Git Commits

| Hash | Message |
|------|---------|
| `26abef2` | (see git log) |

### Testing

- [OK] test_dl698_upgrade.py PASS=259 FAIL=0；test_dl698_upgrade_gui.py 252 项全绿；test_dl698_upgrade_tab_wiring.py PASS=29；698 全家（dl_t698_45*/endian/data_decode/extract/preset/fujian）+ test_web_frame_gen_utils.py(74) 全绿
- [OK] release_check.py --with-gui：PASS=138 FAIL=0 WARN=0（含 test_dl698_upgrade_gui.py PASS）
- [OK] 独立复核（trellis-check）11m43s：6 条变异反证全部变红后逐字节还原（OAD 对调/内部版本不生效/非阻断失效/丢 TimeTag/下拉映射对调/文案互换）；状态机边界 71 项探针全绿（中止/清除/掉线/超时用尽/迟到响应/只勾后读且关自动执行）；既有行为 46 项与 HEAD 逐字节对拍一致；修掉 1 条恒真断言（下拉两项文案与自己比较）

### Status

[OK] **Completed**

### Next Steps

- 发版批次：把 main_gui.py（APP_VERSION/CHANGELOG）、AGENTS.md、README.md、两个 .iss 一起提交；bump 后跑 python release_check.py --sync-iss


## Session 39: 光伏升级：读版本信息展示改版（帧下明细 + 两栏展示区）+ 版本逐字段解析

**Date**: 2026-10-15
**Task**: 光伏升级：读版本信息展示改版（帧下明细 + 两栏展示区）+ 版本逐字段解析
**Branch**: `main`

### Summary

现场反馈两问：①解析结果贴在帧尾、日志 NoWrap ⇒ 要横向拖到底才看得见；②内部版本只给一串值、看不出字段含义。改为「帧一行 + 明细在下」+ 参数栏下新增「版本信息」展示区（升级前/升级完成后并排两栏）+ 按表191 逐字段命名与日期补全（收口到 dl_t698_45_data_decode.VERSION_FIELDS 单一来源）。

### Main Changes

- dl_t698_45_data_decode.py：VERSION_FIELDS/VERSION_FIELD_BYTES + version_like_members/version_lengths_match/decode_version_info；CLASS_ATTR_TEMPLATES[(19,3)] 改引用 VERSION_FIELDS（表191 字段名全仓仅一份）
- dl_t698_45_upgrade.py：version_rows(apdu) 给名称/值/原始/长度；长度与表191 声明不符 ⇒ 命名照给 + 追加「⚠ 长度未自证」行；非结构 ⇒ 一行「数据」兜底；check_get_response 新增 rows 键
- dlt698_upgrade_widget.py：日志改「[RX] 整帧」一行 + 「→ 版本信息（…）读取成功（N 项）」+ 缩进字段行（不再贴帧尾）；参数栏下新增版本信息区（两栏只读框、每栏≥7 行行距、未读/失败文案、开始升级与清除都重置）
- 测试：test_dl698_upgrade.py 259→273（A12）、test_dl698_upgrade_gui.py 252→276（[13] 展示区几何护栏 + [17] 帧下行序 + [20] 现场实帧 + [21] 非结构兜底 + 复核补的 7 条断言）
- 文档：spec §7j 增「展示两条契约 + 逐字段解析单一来源」，AGENTS §5.6/§10 与 README（功能节 + 更新记录）同步，main_gui CHANGELOG 追加（后三者留工作区随发版批次）

### Git Commits

| Hash | Message |
|------|---------|
| `787d155` | (see git log) |

### Testing

- [OK] test_dl698_upgrade.py PASS=273 FAIL=0；test_dl698_upgrade_gui.py 276 项全绿；tab_wiring 29；698 全家（data_decode/dl_t698_45/fujian/endian/preset）全绿
- [OK] release_check.py --with-gui：PASS=134 FAIL=4 WARN=0 —— 4 项 FAIL 的尾部均为「全部通过/结果 PASS=430 FAIL=0」，即本机已知的 offscreen 退出期 0xC0000409（modular_iface 单跑 RC=0 PASS=430 复核过），非断言失败
- [OK] 独立复核（trellis-check 19m）：未发现产品缺陷；7 条变异反证全部变红后逐字节还原（M3 明细改回贴帧尾→10 项红、M4 两栏写成同一栏→10 项红、M5 开始升级不重置→仅复核新补那条红）；补上 2 处缺失断言（PRD 验收项原无覆盖）
- [OK] 真实平台渲染冒烟（非 offscreen）：两栏中文不裁行（余量 295px、滚动条 0）、明细确在帧行下方（几何 + 截图双证）

### Status

[OK] **Completed**

### Next Steps

- 发版批次：main_gui.py（APP_VERSION/CHANGELOG）、AGENTS.md、README.md、两个 .iss 一起提交；bump 后跑 python release_check.py --sync-iss


## Session 40: 光伏升级：不勾自动执行也读升级后版本 + 读前等设备复位（默认 10 秒可设）

**Date**: 2026-10-15
**Task**: 光伏升级：不勾自动执行也读升级后版本 + 读前等设备复位（默认 10 秒可设）
**Branch**: `main`

### Summary

用户纠错：有的设备收全升级包自动复位升级，所以没勾「传完后自动执行升级」同样要读升级后版本；复位期间读不到，需等一会儿再读（默认 10 秒，可手设）。已把读后版本与是否发执行升级解耦，并新增 PHASE_WAIT_RESET 倒计时阶段。

### Main Changes

- dlt698_upgrade_widget.py：新增 PHASE_WAIT_RESET + spin_read_after_delay（默认 10、0~600、落盘、传输中冻结）+ 1 秒重复 QTimer 倒计时（状态行显示剩余秒数）+ _begin_reset_wait/_on_reset_wait_tick/_end_reset_wait；不勾自动执行时末包确认后同样（等复位）读后版本；等待期 _on_frame 忽略、_finish_buttons/_on_start/cleanup 停表
- 复核抓出并修掉的真实缺陷：等待期被误触发超时槽时 _retry_or_fail 会按 _expected_omd() 落到 OMD_EXEC ⇒ 凭空补发「执行升级」帧/把等待判死；现加等待期守卫（记 warn 忽略）
- test/test_dl698_upgrade_gui.py 276→322：[22] 默认10秒/可设/0秒立即读/不勾自动执行也读/等待期忽略杂帧/中止与清除打断/连续两轮不残留/cleanup 停表/真实事件循环倒计时（不被手工 tick 快进掩盖）
- 文档：spec §7j 新增「解耦 + 等复位 + _retry_or_fail 等待期守卫」契约条，AGENTS §5.6/§10 与 README（功能节 + 更新记录）+ main_gui CHANGELOG 同步（后三者留工作区随发版批次）

### Git Commits

| Hash | Message |
|------|---------|
| `81df6bc` | (see git log) |

### Testing

- [OK] test_dl698_upgrade_gui.py 322 项全绿；test_dl698_upgrade.py PASS=273；tab_wiring PASS=29；test_yw645_gui.py 77（tab 文案联动）；ruff 干净
- [OK] release_check.py --with-gui：PASS=138 FAIL=0 WARN=0
- [OK] 真实事件循环冒烟（非 offscreen，delay=2 真 sleep）：剩余 2→1→0 后自动发出读版本帧（05 01 02 43 00 03 00 00）、最终 done、全程 3 帧
- [OK] 独立复核（trellis-check 20m）：9 条变异反证全部干净变红后逐字节还原（md5 一致）；不勾读后版本时 4 种组合的帧序列与**每一行日志**都与 HEAD 逐字节相同

### Status

[OK] **Completed**

### Next Steps

- 发版批次：main_gui.py（APP_VERSION/CHANGELOG）、AGENTS.md、README.md、两个 .iss 一起提交；bump 后跑 python release_check.py --sync-iss


## Session 41: 光伏升级：发送通道（串口/蓝牙）+ 按 ATT 上限自动算每包最大字节数

**Date**: 2026-10-15
**Task**: 光伏升级：发送通道（串口/蓝牙）+ 按 ATT 上限自动算每包最大字节数
**Branch**: `main`

### Summary

用户需求：新增发送通道（串口默认/蓝牙），蓝牙复用蓝牙工具页的连接，并把 ATT 限制截过来当每包数据上限（要计算：ATT 512 ⇒ 每包不能超 480），勾蓝牙时自动算好最大输入上限。已实现：single_write_limit（特征码写上限或 MTU−3，不叠蓝牙页 200 上限）+ 用真实 698 组帧二分反推块长（MTU 512 ⇒ 509 ⇒ 475）+ 整帧一次 ATT 写（超限拒发）+ 未连接/未协商不设假上限。

### Main Changes

- dl_t698_45_upgrade.py：max_block_bytes_for_frame_limit(limit, sa, ca) —— 真实组帧二分，开销自动算（BER 长度域/地址域都算进去）
- bluetooth_worker.py：_limit_plan（一次 ATT 写物理上限单一实现）+ single_write_limit()（不叠 _max_chunk）+ send_data(..., single_write=True)（整帧一次写，超限拒发不静默分包）
- dlt698_upgrade_widget.py：combo_channel（落盘/传输中冻结）+ set_bluetooth_provider 取值回调 + _BleSendPort + RX 走 notification_received + _apply_block_limit（算 cap→setMaximum+夹值+标签写明过程；算不出不设假上限并禁用开始）+ _bt_cap 缓存进 _worker() 判据 + 重算时机（通道/连接/mtu_updated/SA）
- main_gui.py：_upgrade_bluetooth_source() 取值回调（取蓝牙工具页的 worker；只提交这一处 hunk，CHANGELOG/APP_VERSION 留工作区）
- 复核修掉的 3 处真实缺陷：① 蓝牙信号误拨串口通道按钮/标签 + 蓝牙页报错抄进本页日志；② 蓝牙页后建 worker 时本页不回钩（永远未连接）⇒ showEvent 幂等重对齐；③ RX 跨通道混源（双向）⇒ 两个入口都判通道
- 文档：spec §7j 新增「发送通道」契约条，AGENTS §5.6/§10、README（功能节 + 更新记录）、main_gui CHANGELOG 同步（后三者留工作区）

### Git Commits

| Hash | Message |
|------|---------|
| `eeb046c` | (see git log) |

### Testing

- [OK] test_dl698_upgrade.py 286（A13 上限反推：509⇒475/512⇒478、紧致性、非法输入）；test_dl698_upgrade_gui.py 375（[23] 蓝牙通道 + [24] 通道隔离）；test_bluetooth_worker.py 126（[8] 整帧一次写）；test_dl698_upgrade_tab_wiring.py 37 —— 全绿，ruff 干净
- [OK] release_check.py --with-gui：PASS=138 FAIL=0 WARN=0
- [OK] 真实平台渲染冒烟（非 offscreen）：通道行不截断、切蓝牙后上限 475 且标签给出计算过程、串口投帧不推进蓝牙流程
- [OK] 独立复核（trellis-check 32m）：10 条变异反证全部干净变红后逐字节还原；MTU 各档×4 种 SA 全表「帧(cap) ≤ limit < 帧(cap+1)」紧致；块序号/PIID 变化帧长恒 509；MTU 竞态（23→512→200）行为正确

### Status

[OK] **Completed**

### Next Steps

- 发版批次：main_gui.py（APP_VERSION/CHANGELOG）、AGENTS.md、README.md、两个 .iss 一起提交；bump 后跑 python release_check.py --sync-iss


## Session 42: 桌面粘性入口：托盘菜单内嵌报文输入框 + 任务栏缩略图按钮

**Date**: 2026-10-16
**Task**: 桌面粘性入口：托盘菜单内嵌报文输入框 + 任务栏缩略图按钮
**Branch**: `main`

### Summary

用户问能否像汽水音乐那样在 Win11 任务栏放可交互控件。先定边界（SMTC 媒体卡片只有媒体会话能占、Win11 移除 deskband ⇒ 任意控件进不去任务栏那一行），再落两条系统支持的入口：托盘菜单内嵌输入框 + 任务栏缩略图按钮（ITaskbarList4/3）。

### Main Changes

- system_integration/taskbar_buttons.py（新，纯 ctypes）：available/set_buttons/clear + QImage→HICON + WM_COMMAND 拦截；接口按 ITaskbarList4→3→2 试（Win11 只认 4）、HANDLE 调用全部声明 argtypes、PySide6 过滤器返回单个 bool
- system_integration/sys_tray.py：QWidgetAction 内嵌「输入框 + 解析」→ parse_text_requested(str) + 清空 + 收菜单；set_input_enabled 供禁用
- main_gui.py：_parse_text_input（判据与 clipboard_monitor.strict_hex 同源，HEX→_parse_and_show_dialog、否则 _parse_text_content、都不是则状态栏+气泡说明）+ 4 个任务栏按钮（解析剪贴板/快捷解析/批量解析/光伏升级）+ showEvent 延迟挂载(句柄变化才重挂) + closeEvent clear
- test/test_tray_taskbar_entries.py（新 27 项，登记 release_check.py:GUI_TESTS）
- 文档：spec §7k（粘性入口契约与能力边界）、AGENTS §3/§8 陷阱 78/§10、README（功能表+系统集成节+更新记录）、main_gui CHANGELOG（后三者留工作区随发版批次）；BUILD_DATE 顺手更到今天 2026-10-16（gate 的 WARN 归零）

### Git Commits

| Hash | Message |
|------|---------|
| `6a5afe1` | (see git log) |

### Testing

- [OK] test/test_tray_taskbar_entries.py 27 项全绿；release_check.py --with-gui PASS=135 FAIL=3 WARN=0（3 项为本机已知 offscreen 退出期 fastfail，尾部断言全绿）
- [OK] 真机冒烟（非 offscreen）：_setup_taskbar_buttons() → True、按钮 id 0x7700..0x7703、PostMessage(WM_COMMAND) 触发 clicked；「光伏升级」按钮 → 协议 8 + tab 文案「光伏升级」；托盘输入框提交 → 解析调用（字节与协议索引正确）
- [OK] 接口探测：CoCreateInstance(QI) 在 10.0.26300 上 IID_ITaskbarList3 = E_NOINTERFACE 而 ITaskbarList4 = S_OK，ThumbBarAddButtons/SetThumbnailTooltip 均 S_OK

### Status

[OK] **Completed**

### Next Steps

- 若要「任务栏按钮常驻」需把「关到托盘」改成「最小化到托盘」（行为变更，待用户确认）；SMTC 伪媒体卡片（截图那种）未做，需要先探针实测非媒体会话是否显示

## Session 43: 多线程下载器四批次加固（1.23.96）

1.23.95 首次把自动升级改成多线程分段下载后，逐行评审出 R1~R17 共 17 个问题（其中 3 个是 P0：回 200 会按段偏移写整文件、退出删掉几百 MB 分片、重复点下载起两个 worker 抢同一个 .part）。本会话把 17 条全部落地，每条都配可反证的自动化测试。

### Main Changes

- downloader.py：`_RangeUnsupported` 判不可分段 → 回落单流；每段自证 Content-Range（起始偏移 + 总长）；progress.json 的 url 参与校验（换源整份作废）；单流回落也支持续传；`wait_resumed()` 事件阻塞取代 `sleep(0.1)`；`on_cancel="keep"/"clean"` 两态；`_describe_os_error` 把 ENOSPC 等翻成中文；429/Retry-After 退避（夹上限 10 s）；取消立即返回；删死参数 `http_probe`；`DEFAULT_MAX_THREADS` 真正成为「自动」默认
- update_download_dialog.py：`changeEvent(FontChange)` 重算 `fit_btn_width`（14 号字下「后台运行」原本被压回旧下限裁字）；表格状态列与标题随 `progress.state` 走（已暂停 / 重新开始）
- main_gui.py：新增「配置 → 下载进度(&D)...」菜单；`_start_download` 加 `isRunning()` 重入守卫（重复触发只唤回面板）；`_shutdown_threads` 里对下载线程先 `on_cancel="keep"` 再 cancel；`_on_download_done` 清状态栏；新增 `_show_download_panel` / `_hide_download_panel` / `_discard_download_cache`；删 `_UpdateDownloadWorker.progress` 死信号
- test/test_downloader.py +12 项（总 42）、test/test_update_download_dialog.py +12 项（总 26，含宿主级重入守卫/菜单重开/状态栏清理）
- 文档：AGENTS 陷阱 84 追加四条不可回退约定 + §7/§10，README 补下载行为说明；版本 1.23.96 / BUILD_DATE 2026-10-23，两个 .iss 同步
- 顺带修两处测试假红：test_menu_wiring.py 结尾 `✓` 在 GBK 控制台抛 UnicodeEncodeError；test_app_icon_path.py 仍在 .spec 正文 grep 图标字面量（spec 早已改为 `datas=list(meta.DATAS)`）

### Git Commits

| Hash | Message |
|------|---------|
| `ebddc5e` | feat(downloader): 多线程下载器四批次加固 + 协议8「协议测试」页（1.23.93~1.23.96） |

### Testing

- [OK] test/test_downloader.py 42 项、test/test_update_download_dialog.py 26 项全绿
- [OK] 6 条变异反证逐条实测变红后逐字节还原（段自证 / keep 保留 / 进度推进 / 共用句柄 / Retry-After 上限 / 面板模态）
- [OK] release_check.py --with-gui：PASS=161 FAIL=0 WARN=0

### Status

[OK] **Completed**

### Next Steps

- 提交时发现工作区混有 1.23.93/1.23.95/1.23.96 三批未提交改动（downloader.py 等仍是未跟踪新文件），与用户确认后合并为一个发布提交；trellis/.claude/.agents 的运行时升级改动仍留在工作区未提交


## Session 44: 发布 1.24.0：编译单文件 exe + GitHub Release
<!-- trellis-session: v=2 fp=8ea0ae646a480f49 -->

**Date**: 2026-10-24
**Task**: 发布 1.24.0：编译单文件 exe + GitHub Release
**Branch**: `main`

### Summary

1.24.0 批次（协议15 Modbus、协议2 HDLC 定义级修正、645 无线组帧、串口蓝牙通道）编译打包并发布；先修两处门禁红，门禁 PASS=145 FAIL=0 WARN=0；Release 资产 exe+SUM 与本地 sha256 三方一致

### Main Changes

- protocol_registry/main_gui/AGENTS/README/.iss 版本四件套；reflex_web/landing_web.py 补 Modbus 协议行；test/test_self_test.py 解析器计数改按注册表取

### Git Commits

| Hash | Message |
|------|---------|
| `6dc01b2` | feat: 1.24.0 —— 新增协议15 Modbus + 协议2 HDLC 字段级重写 + 645 无线模组组帧 |

### Testing

- [OK] release_check.py PASS=145 FAIL=0 WARN=0（含 GUI）
- [OK] exe --self-test 退出 0（13 个解析器已加载）
- [OK] dist exe FileVersion=1.24.0.0；sha256 ca7d9708… 与 Release 资产 digest 一致

### Status

[OK] **Completed**

### Next Steps

- 协议2 HDLC 未覆盖项（安全 HLS/glo-ded、SN 短名、分段重组、ACCESS 展开）与 dlms_parser.py 旧表同步待办


## Session 45: 同步 Web 下载区版本信息到 1.24.0
<!-- trellis-session: v=2 fp=114623a3f32f23a8 -->

**Date**: 2026-10-24
**Task**: 同步 Web 下载区版本信息到 1.24.0
**Branch**: `main`

### Summary

工程内下载区与已部署的 1.24.0 对齐：version.json（gitignore/部署排除）指向 GitHub Release 资产，随包分发的 client_readme.md 从 1.14.0/12 种协议更新为 1.24.0/16 种，downloads/README.md 重写为数据根语义

### Main Changes

- reflex_web/downloads/client_readme.md：版本徽章/协议表 16 行/功能表纠正/1.24.0 更新记录
- reflex_web/downloads/README.md：随包静态资源 vs 运行时发布产物（数据根）
- reflex_web/downloads/version.json（本地，不入库）：1.24.0 + GitHub 资产 URL + sha256

### Git Commits

| Hash | Message |
|------|---------|
| `328b665` | docs(web): 下载区同步到 1.24.0 / 16 种协议 |

### Testing

- [OK] protocol_registry 对拍 16 行全对齐
- [OK] resolve_download_target/顶栏徽章读到 1.24.0
- [OK] Release 资产 URL 302→200, Content-Length 105030178
- [OK] test_web_landing(104)/test_web_download_url(35)/test_web_data_paths(126) 全绿

### Status

[OK] **Completed**


## Session 46: 预设命令页：粘贴报文添加按钮 + 按协议一键批量替换地址
<!-- trellis-session: v=2 fp=0c5851ac304d4fc4 -->

**Date**: 2026-10-26
**Task**: 预设命令页：粘贴报文添加按钮 + 按协议一键批量替换地址
**Branch**: `main`

### Summary

预设页新增「添加命令」（弹框可直接粘贴报文，剪贴板合法HEX自动带入，确定前校验/归一化）与「批量替换地址（当前协议）」（地址字段按 frame_addr_fix 动态生成、一键逐条替换并重算校验、确认框+日志+汇总、全失败不写盘）；纯逻辑 preset_protocol_index/AddrBatchItem/batch_fix_presets；新增 test/test_preset_paste_addr.py 82 项入 CORE_TESTS，变异反证3条，真机几何审计零重叠，release_check --with-gui 仅剩3项本机已知 offscreen 退出期 fastfail（HEAD 对照复现同样的3项）。

### Git Commits

| Hash | Message |
|------|---------|
| `81b380c` | feat(preset): 预设页支持粘贴报文添加 + 按协议一键批量替换地址 |

### Status

[OK] **Completed**


## Session 47: 645 协议测试页：DI 大类命令树 + 地址读写 + 特殊命令
<!-- trellis-session: v=2 fp=5dacbc0d074f8c06 -->

**Date**: 2026-10-26
**Task**: 645 协议测试页：DI 大类命令树 + 地址读写 + 特殊命令
**Branch**: `main`

### Summary

仿照 698 协议测试页为协议6 新建「645协议测试」页：顶部表地址/读地址(13H 回填)/写入地址(15H)/广播校时(08H)/超时/循环/发送停止；左栏 PA/密码/操作者；中栏读数据(11H)/写数据(14H)/特殊命令三页（筛选+DI 大类树+当前项+帧预览，勾选顺序下发、等应答再发下一条、超时继续）；右栏收发日志+逐字段明细+判定结论；底部信息表/报文表双击送单帧解析。纯逻辑 dlt645_test_core（catalog/command_groups/组帧全走 DLT645FrameGenerator/evaluate_response 不冒充成功/malformed_di_keys 暴露 16 条 7 位残键），共享 testpage_render 与 698 同一份四列渲染。顺带修 dlt645_frame_schema._value_or_raw 不认日期/时间/通信地址等掩码字段导致 14H 组不出的真缺陷。接线：protocol_registry.has_dlt645_test(仅6)+protocols_with_dlt645_test、main_gui 第二套懒加载 tab、pyinstaller_meta hiddenimports、.gitignore 加 dlt645_testbench.json。测试：test_dlt645_testbench 89 项 + test_dlt645_test_tab_wiring 19 项（均 GUI_TESTS），4 条变异反证，真机几何审计 1280x820/1000x700 零重叠；release_check --with-gui PASS=171 FAIL=0 WARN=0（白名单补新 wakeup 消费者后）。

### Git Commits

| Hash | Message |
|------|---------|
| `af045c6` | feat(645): 新增「645协议测试」页（DI 大类命令树 + 地址读写 + 特殊命令） |

### Status

[OK] **Completed**


## Session 48: 698/645 协议测试页：串口/蓝牙双通道
<!-- trellis-session: v=2 fp=bba8fc2a8d155f41 -->

**Date**: 2026-10-26
**Task**: 698/645 协议测试页：串口/蓝牙双通道
**Branch**: `main`

### Summary

两个协议测试页加「发送通道：串口/蓝牙」：蓝牙复用蓝牙工具页连接（main_gui 注入 provider），整帧一次 ATT 写、超限明确报错不发送；新增共用 channel_link.ChannelController（rx 分流/ready 原因/状态文案含 MTU+上限/send 超限预检/cleanup 只断信号），两页收发改走控制器（删除页内 raw_data_received 直连、RX 改名 _on_rx_data 保留旧别名、通道落盘、showEvent 重绑、cleanup 转交）；698 顶部加通道行（294 项）、645 三行顶栏（106 项）、新增 test_channel_link 49 项、接线注入断言（23/20）；3 条变异反证；真机几何 645@1280x820/1000x700、698@1500x900/1440x880 零重叠不裁字；release_check --with-gui PASS=172 FAIL=0 WARN=0。

### Git Commits

| Hash | Message |
|------|---------|
| `c51dda6` | feat(proto-test): 698/645 协议测试页支持串口 / 蓝牙发送通道 |

### Status

[OK] **Completed**


## Session 49: 主题：树/表行内复选框可见性（QAbstractItemView::indicator）
<!-- trellis-session: v=2 fp=a6aeab9bd31ccf05 -->

**Date**: 2026-10-26
**Task**: 主题：树/表行内复选框可见性（QAbstractItemView::indicator）
**Branch**: `main`

### Summary

修复树/表/列表行内复选框未勾选时白底白框（QCheckBox::indicator 管不到 item view 指示器；真实平台 default 实测整块 #ffffff）：4 套 QSS（default/dark/glass/mica）各补 QAbstractItemView::indicator 三态（灰框+底色/强调色/浅强调），tree/table/list 同源生效。回归：test_theme_settings 1d 节 22 项（静态规则 + 渲染取像素算对比度≥3 且像素数≥20 + 勾选可区分 + 反例自检），另做产品代码变异反证（删规则→4 红，还原）；真实平台 645 命令树未选框 60 个高对比像素（修复前 0）、边框对比 7.56:1（dark 5.36），QTableWidget 同 7.56:1；release_check --with-gui PASS=172 FAIL=0 WARN=0。

### Git Commits

| Hash | Message |
|------|---------|
| `6869697` | fix(theme): 树/表行内复选框补可见边框（QAbstractItemView::indicator） |

### Status

[OK] **Completed**


## Session 50: 645 测试页接入无线模组接口手册 V1.6 扩展 DI
<!-- trellis-session: v=2 fp=b138943dc95c34c7 -->

**Date**: 2026-10-26
**Task**: 645 测试页接入无线模组接口手册 V1.6 扩展 DI
**Branch**: `main`

### Summary

根因：测试页分类树只来自 merge_pv_di_map（基础+附件1 02E6/03E6/04E6），手册 V1.6 的 12 条 DI 在 dlt645_pv_wireless.WIRELESS_DI_MAP（仅组帧页接了）。新增顶层「光伏无线扩展（V1.6）」按手册分组（数据转发/无线参数/拓扑/升级/版本/在网状态）12 叶子；DiItem 增 wireless/note，di_info 回落无线表；04E60001 与附件1 重叠以手册为准（光伏参数 172→171，总数 1776 无重复）；read_request_fields（02EB0000 Z/C/T/DATA、FF00DD01 条目）+ build_read(field_values)，读页动态字段与手册备注；无线应答摘要走 parse_wireless_di；命令页补 06H/1EH。顺带修 schema 写数据 14H 未分派无线编码器（04900105 组不出）。测试 106→132 项（[10] 段）+ 接线树计数 10→11；变异反证 4 条（读字段恒空/取值不分派/不加分类/不去重）；真机核对 11 顶层/12 叶子/字段已绘制/备注可见；release_check --with-gui PASS=172 FAIL=0 WARN=0。

### Git Commits

| Hash | Message |
|------|---------|
| `62efa08` | feat(645): 协议测试页接入无线模组接口手册 V1.6 扩展 DI |

### Status

[OK] **Completed**
