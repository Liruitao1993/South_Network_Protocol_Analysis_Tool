# 透明度全局化并修复切主题残留重影

## Goal

1. 透明度调节全局可用，不再仅毛玻璃主题显示。
2. 在毛玻璃主题调过透明度后切换到其他主题，不能继承半透明合成导致重影。

## Root Cause

- 透明度滑块放在「毛玻璃选项」组里，`_sync_glass_widgets` 把整组在非玻璃主题隐藏，导致其他主题无法调透明度。
- 切离玻璃主题时，`_apply_glass_blur(enabled=False)` 只调用了一次禁用亚克力，但没有先显式关闭再重开/重置属性，`WA_TranslucentBackground` 可能残留，半透明合成状态带到其他主题 → 不擦背景 → 重影。
- 非玻璃主题没有独立的透明机制，无法承载“全局透明度”。

## Fix（theme_settings.py）

1. **透明度全局化**：
   - 对话框分组改名「透明度与毛玻璃」，`glass_group` 始终可见，透明度滑块所有主题可用。
   - 仅「玻璃颜色」「背景图」两行在非玻璃主题隐藏（`tint_row`/`bg_row` 子控件按 `_is_glass_selected()` 显隐）。

2. **非玻璃主题的全局透明度**：新增 `_apply_window_opacity(app, opacity)`，用 `setWindowOpacity` 做 OS 级整窗透明。
   - 这是窗口合成器级 alpha，不依赖 `WA_TranslucentBackground`，不会产生“不擦背景”的重影。
   - 玻璃主题固定 windowOpacity=100（玻璃的透明由 QSS alpha + 亚克力承担）；非玻璃主题用用户设置的 opacity。

3. **切主题彻底重置透明合成**：重写 `_apply_glass_blur`：
   - 先关闭亚克力（AccentState=0）；
   - 显式 `WA_TranslucentBackground=False`；
   - 玻璃主题再开启亚克力并按需设 translucent；
   - 非玻璃主题 `setAutoFillBackground(True)` + `update()/repaint()` 强制擦除残留像素。
   - 这样玻璃 → 其他主题不会把半透明合成带过去。

## Acceptance Criteria

- [x] offscreen：玻璃主题 translucent 由亚克力结果决定；切到 default/dark 后 translucent=False，windowOpacity 按用户透明度（0.6 验证通过）。
- [x] offscreen：对话框透明度滑块在 default 主题可见且值保留；玻璃颜色/背景图仅玻璃主题显示，切到玻璃自动出现。
- [x] 语法检查通过，三主题启动/切换无异常。
- [ ] 真机：玻璃调透明度后切到浅色/暗色/Fusion 主题无重影；非玻璃主题拖透明度滑块整窗透明且无残影。

## Notes

- 真机亚克力开启成功时玻璃主题 translucent=True；offscreen 无合成器返回 False 属正常。
