# 收紧按钮尺寸，文字饱满居中不缺失

## Goal

统一按钮风格后，按钮高度/内边距偏大、文字四周空隙多。要求：文字在按钮内居中、饱满占据，去掉过大空隙；同时保证所有按钮文字完整可见不被截断。

## 改动（theme_settings.build_button_qss）

- 基础 QPushButton：`padding 4px 12px` → `3px 10px`；`min-height 26` → `22`；新增 `min-width: 48px`（防止短文字按钮被布局压扁截断）。
- `btnSize="lg"`：`min-height 30/padding 5px 16px` → `24/padding 3px 12px`。
- `btnSize="sm"`：`min-height 22/padding 1px 8px` → `18/padding 1px 6px`，加 `min-width:0`。
- ghost 图标按钮：加 `min-width:0`，不受基础 48 影响。
- 对话框按钮（QMessageBox/QInputDialog）：`min-width 80/padding 6px 20px` → `72/padding 4px 14px`。

工厂默认高度同步下调：
- `main_gui._make_toolbar_btn` height 28 → 24
- `llm_preprocess_widget._make_btn` min_height 28 → 24
- `llm_api_manager._style_action_btn` height 28 → 24
- `message_tool_widget._btn` setFixedHeight(28) → setMinimumHeight(24)；endian_combo 同步

防截断修正：
- `serial_open_btn`、`export_result_btn` 加 `setMinimumWidth(76)`（4 汉字按钮）。
- `test_plan_widget` 操作列列宽 50 → 60（Lua/后台/发送 迷你 sm 按钮文字不被截）。

## 验证

- offscreen 精确测量：遍历全部 QPushButton，用 `SE_PushButtonContents` 内容矩形对比 `fontMetrics.horizontalAdvance(text)`，**截断数 0**。
- 单帧 lg 按钮由 76×34 收紧到 76×30；默认按钮 72×28。
- 三主题（default/dark/glass）+ 全部 tab/协议切换无异常；改动文件语法通过。

## Notes

- lg 按钮在 10pt 微软雅黑下高度 30 是字体行高（约 20）+ padding 的合理紧凑下限，再小会裁切中文上下笔画。
- 真机确认三主题下按钮视觉是否满意。
