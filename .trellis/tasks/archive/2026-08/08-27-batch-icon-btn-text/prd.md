# 批量解析页纯图标按钮改为图标+文字

## Goal

批量解析工具栏预处理行(★保存/×删除/?帮助)与脚本行(×移除/?帮助)共5个按钮为36px纯字形方块，用户反馈无文字体验差。改为与同行执行/加载/运行一致的图标+文字按钮（set_btn_icon 标准图标），并移除 _make_toolbar_btn 的 icon_btn 死分支、同步 tooltip 说明。

## Requirements

- 批量解析工具栏 5 个 `icon_btn=True` 方块按钮全部改为「标准图标 + 中文文字」，与同行「执行/加载/运行」按钮风格一致（`gui_utils.set_btn_icon`，Qt 内置标准图标）：
  - 预处理行：`★` → 「保存」(save 图标)、`×` → 「删除」(delete 图标)、`?` → 「帮助」(help 图标)
  - 脚本行：`×` → 「移除」(delete 图标，语义=从列表移除不删磁盘文件)、`?` → 「帮助」(help 图标)
- 按钮保留现有 tooltip；点击行为、信号连接不变
- 预处理命令下拉框 tooltip 中「点『★』…点『×』」说明同步改为「保存/删除」
- `_make_toolbar_btn` 的 `icon_btn` 参数及方块样式分支在全仓已无调用方，移除该死代码
- 按钮宽度紧凑（2 字标签 + 图标），低分屏（1366×768）下两行工具栏不得出现几何重叠

## Acceptance Criteria

- [ ] 5 个按钮均显示中文文字 + 标准图标，无 36px 纯字形方块残留
- [ ] 保存/删除/移除/帮助按钮点击行为与改动前一致（信号连接不变）
- [ ] `_make_toolbar_btn` 不再含 `icon_btn` 参数；全仓 grep 无 `icon_btn` 引用
- [ ] offscreen 冒烟：MainWindow 批量页按钮文字/图标就位，同父级可见控件无几何重叠
- [ ] CHANGELOG（main_gui.py）与 AGENTS.md §10 同步

## Notes

- 仅改 `main_gui.py`（批量工具栏构造 + `_make_toolbar_btn` 工厂）；不涉及解析逻辑
- 参考 1.15.0 图标体系：`set_btn_icon(btn, key)` 默认图标+文字并存，未知 key 静默跳过
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
