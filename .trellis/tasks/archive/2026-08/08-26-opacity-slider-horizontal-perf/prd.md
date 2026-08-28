# 透明度滑块改水平 + 拖动卡顿修复

## Goal

主题设置对话框中，透明度滑块显示成又高又宽的垂直长条且占用大量垂直空间；拖动调节时明显卡顿。改为水平方向并消除卡顿。

## Root Cause

1. **垂直**：`QSlider()` 无参构造默认方向是 `Qt.Vertical`（Qt 经典陷阱），代码没传 `Qt.Horizontal`。
2. **卡顿**：`valueChanged` 直接连 `_apply_preview()`，拖动时每经过一个像素都触发一次全量 `ThemeManager.apply`——重建整份 QSS（含 build_glass_qss 正则扫描、按钮 QSS 拼接）、`app.setStyleSheet` 全应用、刷新所有表格字体，逐帧重算导致卡顿。

## Fix（theme_settings.py ThemeSettingsDialog）

1. 滑块显式 `QSlider(Qt.Orientation.Horizontal)`，加 `setMinimumHeight(22)`、单步/页步。
2. 新增 60ms 单次防抖定时器 `_opacity_preview_timer`，timeout 连 `_apply_preview`。
3. `_on_glass_opacity_changed`：
   - 标签实时更新；
   - `isSliderDown()`（正在拖动）时启动防抖定时器合并应用；
   - 非拖动（键盘/点击/松手）时立即 `_apply_preview`。
   拖动期间每 60ms 最多应用一次，松手立即生效。

## Acceptance Criteria

- [x] offscreen 确认滑块 orientation == Horizontal，value 正常。
- [x] 主窗口 + 对话框实例化、拖动设值无异常。
- [ ] 真机：滑块水平、高度正常不占垂直空间；拖动流畅不卡顿，松手实时生效。

## Notes

- 透明度滑块在所有主题可见（沿用上一任务）；玻璃颜色/背景图仅玻璃主题显示。
