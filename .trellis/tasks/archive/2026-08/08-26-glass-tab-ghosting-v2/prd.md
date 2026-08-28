# 毛玻璃 tab 页重影二次修复

## Goal

上一版把基础 QWidget 改 rgba(255,255,255,6) 后仍有重影，tab 切换尤其明显。彻底消除切 tab 残影。

## Root Cause

QTabWidget 内部用 QStackedWidget 管理页面。切 tab 时新页面自身仍是近透明（alpha 6），无法盖住 backing store 里上一页的像素；半透明控件重绘只“叠加”不“擦除”，于是上一页透出来形成重影。QSS 给 pane 上底色，但页面 widget 覆盖在 pane 上、自身透明，pane 底色透不出来擦除。

## Fix

1. theme_settings.py（GLASS_QSS）：
   - `QStackedWidget > QWidget`（每个 tab 子页面）背景设为 `rgba(248,250,255,245)` 近不透明，切页时新页盖死旧像素。
   - `QTabWidget::pane` 提到 215、QStackedWidget/QScrollArea 200，多层兜底。
   - 表格 item 行背景 alpha 提高（上一版已做）。
2. main_gui.py：
   - 新增 `_on_tab_changed_repaint(index)`，连接 `tab_widget.currentChanged`；仅毛玻璃主题生效。
   - `QTimer.singleShot(0, ...)` 在新页布局后对当前页 `update()` + `repaint()`，强制擦除重绘，双保险。

## Acceptance Criteria

- [x] offscreen 玻璃主题启动 + 遍历全部 tab 无异常，槽连接正常。
- [ ] 真机：切 tab 无重影（重点验证）；滚动/展开表格无拖影。
- [ ] 真机：玻璃质感保留，tab 页面可读（近不透明面板符合毛玻璃设计）。

## Notes

- 非玻璃主题不触发额外重绘（按 `self._theme_id == "glass"` 守卫）。
- 若真机仍有残影，下一步考虑：对玻璃主题临时关闭 `WA_TranslucentBackground` 改用纯色半透明窗口（无亚克力模糊但绝无残影），或给所有滚动视口 `setAutoFillBackground(True)`。
