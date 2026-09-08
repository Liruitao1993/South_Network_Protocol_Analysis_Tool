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
