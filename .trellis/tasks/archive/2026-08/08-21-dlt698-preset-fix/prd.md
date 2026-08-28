# 修复协议8(698.45)预设命令保存到国网文件且预设页不显示

## Goal

协议8 组帧页「添加到预设」后，预设按钮保存到独立的 698 预设文件，并在「预设命令」标签页正确显示（当前被写进 GW_command.json 且预设页静默忽略 dlt698 协议，用户看不到）。

## 背景 / 根因（已排查确认）

`preset_buttons.py` 预设体系只设计了两协议（south/gdw）：

1. **保存路径错位**：模块级 `_get_path(protocol)`（preset_buttons.py:31）仅判断 `protocol == "south"`，否则一律落到 `GW_command.json`。协议8 调 `add_command("dlt698", ...)` 被写进国网文件。
2. **显示端不认 dlt698**：`PresetButtonWidget.set_protocol()`（preset_buttons.py:210）守卫 `protocol in ("south", "gdw")`；`main_gui.py:2017` 切协议8 时传入 `"dlt698"` 被静默忽略，预设页停留在上一个协议文件（默认南网）。
3. **对话框标签错误**：`AddPresetDialog`（preset_buttons.py:106）协议行只会显示「南网协议/国网协议」。

## Requirements

- 协议8 预设保存到独立文件 `DLT698_command.json`（与 NW/GW 同级同格式 `{"commands": [...]}`）
- 切到协议8 时预设命令页显示 698 预设列表；`set_protocol("dlt698")` 生效
- 添加预设对话框协议行显示「698.45 协议」
- 预设点击发送时按 protocol 正确透传（现有 `button_clicked` 信号带 protocol，主程序已按协议分发，确认 698 路径可用）
- 已有南网/国网预设行为完全不变（含自定义文件路径 `_file_paths["nw_command"|"gw_command"]`；698 用默认路径即可）
- 历史误存条目：`GW_command.json` 中已存在的 `protocol=dlt698` 条目在国网页加载时按 protocol 过滤隐藏（不做文件迁移，保持简单）

## Acceptance Criteria

- [ ] 协议8 组帧页生成帧 → 添加到预设 → 预设命令页立即可见该按钮（分组正确）
- [ ] `DLT698_command.json` 生成在项目根目录，内容为 `{"commands": [...含 protocol=dlt698...]}`；新添加不再写入 `GW_command.json`
- [ ] 协议 0/7/8 之间来回切换，预设页各自显示对应文件内容；国网页不显示 protocol=dlt698 的历史条目
- [ ] 右键删除协议8 预设按钮后从 `DLT698_command.json` 移除
- [ ] offscreen 冒烟脚本验证以上各项（放入 `test/`，含 `import _path_setup`）
- [ ] 既有回归不破坏（至少 `test/test_web_frame_gen_utils.py` 与 GUI 启动冒烟）

## Notes

- 改动集中在 `preset_buttons.py`（约 5 处小改）；`main_gui.py` 仅在需要时小改。不改组帧逻辑。
- 遵循 AGENTS.md：完成后更新 `main_gui.py:CHANGELOG` 与 AGENTS.md §10/§11。
- Lightweight task: PRD-only，无需 design.md/implement.md。
