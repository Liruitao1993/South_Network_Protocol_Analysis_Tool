# 快速切 tab 卡顿不响应修复

## Goal

快速切换 tab 页面时卡顿、不响应。修复为流畅切换，同时保留毛玻璃去重影。

## Root Cause

上一版为消除毛玻璃 tab 残影，在 `currentChanged` 里用 `QTimer.singleShot(0)` 调 `_repaint_tab_pages`，其中调用 `w.repaint()`。`repaint()` 是**同步强制立即重绘**，切到含大表格/复杂控件的页时会阻塞事件循环一次绘制；快速连续切换时每切一次都强制重绘整页，累积导致卡顿不响应。

## Fix（main_gui.py）

- 把 `_on_tab_changed_repaint` 改为异步防抖：
  - 新增 50ms 单次 QTimer `_tab_repaint_timer`，快速切换只在停顿后触发一次。
  - 记录目标页 `_pending_repaint_tab`。
- `_repaint_tab_pages` → `_do_tab_repaint`：只调用 `w.update()`（异步、Qt 自动合并多次重绘请求），**删除 `w.repaint()`**。
- 仅毛玻璃主题生效（`self._theme_id == "glass"` 守卫不变）。

重影在毛玻璃下已由近不透明的 tab 页面背景（QStackedWidget>QWidget rgba 245、pane 215）承担擦除，update 足以刷新，无需同步 repaint。

## Acceptance Criteria

- [x] offscreen 快速来回切换 20 轮无异常/无冻结。
- [ ] 真机：快速切 tab 流畅不卡；毛玻璃下切页无残影回归。

## Notes

- 轻量任务 PRD-only。
