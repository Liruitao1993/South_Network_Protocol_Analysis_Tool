# 小窗模式核验提交与后续开发

## Goal

核验小窗模式（快捷解析小窗）现有实现并可入库：确认 1.17.0~1.18.1 的小窗功能与测试当前可用、逻辑断言全过，然后按用户选定策略「按主题分 3 个提交」把 1.15.0~1.18.1 未提交代码分主题入库，为后续小窗开发建立干净基线。

## 背景事实（核验基线，2026-08-29 实测）

- `APP_VERSION = "1.18.1"`、`BUILD_DATE = "2026-08-28"`；`main_gui.py:CHANGELOG` 已有 1.17.0 / 1.17.1 / 1.17.2 / 1.18.0 / 1.18.1 条目（1.18.1 含毛玻璃/空态精简/玻璃化配色）。
- 归档任务 08-27-quick-parse-panel / 08-27-qp-panel-dual-cards / 08-28-qp-card-height-keep 均标记 completed，但**功能代码从未提交**——归档 commit 只含 `.trellis/tasks/archive/` 文档。
- 工作树共 35 个 M + 约 25 个 ??，覆盖 1.15.0（按钮图标）~1.18.1（毛玻璃）全部功能。
- 小窗相关文件：`system_integration/quick_parse_panel.py`（726 行）、`system_integration/acrylic_effect.py`、`test/test_quick_parse_panel.py`（63 项断言）、`system_integration/global_hotkey.py`（+3）、`system_integration/system_settings.py`（±7）、`南网协议解析工具.spec`（+12，hiddenimports 补 quick_parse_panel/acrylic_effect）、`main_gui.py`（含全部集成点 + CHANGELOG）。
- 已知环境约束：本机 GBK 控制台，跑测试必须 `PYTHONIOENCODING=utf-8 python -X utf8`（否则 ✓ 字符 UnicodeEncodeError）；1.17.1 注记 test_quick_parse_panel 退出码为本机已知 MainWindow 关闭期 fastfail（0xC0000409），逻辑断言全过——再次出现不算回归。
- `test/_probe_qp_cards.py` 为调试探针，**不提交**。

## Requirements

### R1 核验小窗现状

- `py_compile` 通过：quick_parse_panel.py / acrylic_effect.py / test_quick_parse_panel.py / main_gui.py / global_hotkey.py / system_settings.py。
- 跑 `test/test_quick_parse_panel.py`（offscreen）：63 项断言全过；fastfail 退出码按已知注记接受并记录。
- 集成点抽查：main_gui.py 中 QuickParsePanel 注入（clean/parse/validate/open_full/is_dark）、热键唤出、system_settings 热键文案。
- 若测试失败或发现缺陷：修到全过为止（小修），行为变更则补 CHANGELOG 条目。

### R2 按主题分 3 个提交入库

- **Commit 1（小窗+系统集成）**：
  - `system_integration/quick_parse_panel.py`
  - `system_integration/acrylic_effect.py`
  - `system_integration/global_hotkey.py`
  - `system_integration/system_settings.py`
  - `test/test_quick_parse_panel.py`
- **Commit 2（主程序+打包）**：
  - `main_gui.py`（版本 1.18.1，消息注明涵盖 1.15.0~1.18.1 全部集成）
  - `南网协议解析工具.spec`
  - `AGENTS.md`（若核验发现 §10 缺 1.18.1 条目则补后一并提交）
- **Commit 3（其余功能）**：
  - 剩余全部功能文件：meter_sim/、meter_sim_widget.py、meter_sim_data.json、meter_sim_settings.json、scripts/gen_meter_sim_data.py、parser_registry.py、proc_stats.py、thread_registry.py、gui_utils.py、theme_settings.py、frame_gen_widget.py、monitor_widget.py、monitor/*、test_plan_widget.py、diff_widget.py、message_tool_widget.py、preset_buttons.py、archive_widget.py、topology_widget.py、llm_*、lookup_pages.py、protocol_parser.py、gdw_afn_lookup.py、dl_t698_45_frame_schema.py、frame_generator_schema.py、gw_new_gen_parser.py、hdc10_parser.py、serial_worker.py、reflex_web/reflex_web/web_utils.py、reflex_web/tests/test_csg_ed_control.py、test/test_meter_sim.py、test/test_statusbar_stats.py、test/test_app_exit.py、test/test_nw_lcmi.py、test/test_csg_test_device_control.py、test/test_csg_new_gen.py、test/test_ed_fallback_fix.py、system_integration/clipboard_monitor.py
  - 消息按内容分点描述（虚拟表/状态栏/图标/协议修复/Web）。

### R3 提交规范

- **排除项**（明确不提交）：`_tmp_grep.txt`、`repomix-output.md`、`Meter698-45Simulator-master/`、`tools/`、`test/_probe_qp_cards.py`、`协议文档/0.南网协议/`、`南网新一代20260226校对/`（参考文档目录，保持 untracked）、`.trellis/tasks/08-29-qp-verify-commit/`（本任务自身工件，由归档流程处理）。
- 使用 `git add <具体文件>` 精确暂存，禁止 `git add -A` / `git add .`。
- 提交消息遵循仓库风格（`feat`/`fix`/`chore` + 中文描述，参考 `git log --oneline -10`）。
- 提交前检查：无密钥/敏感文件、无调试残留。

### R4 提交后状态

- `git status` 仅剩有意保留的 untracked（参考文档、临时目录、任务工件）。
- 小窗相关代码在提交后仍可运行（offscreen 冒烟复跑一遍 test_quick_parse_panel）。

## Acceptance Criteria

- [ ] py_compile 全过（上述文件清单）
- [ ] test_quick_parse_panel.py 63 项断言全过（fastfail 退出码与历史注记一致即接受并记录）
- [ ] 3 个提交按 R2 分组入库，不含 R3 排除项
- [ ] 提交后 `git status` 干净（除有意保留项）
- [ ] 提交后复跑 test_quick_parse_panel 仍全过

## Notes

- 本任务只做核验+提交；小窗后续功能开发（如有）另行建任务。
- 本机跑 GUI/测试必须 `PYTHONIOENCODING=utf-8 python -X utf8`。
