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
