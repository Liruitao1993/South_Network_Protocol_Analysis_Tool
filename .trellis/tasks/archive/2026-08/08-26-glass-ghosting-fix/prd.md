# 毛玻璃主题切换/滚动重影修复

## Goal

毛玻璃主题下，切换 tab、滚动、控件移动时出现上一画面残留的“重影/拖影”。要求消除重影，保持玻璃半透明质感。

## Root Cause

毛玻璃开启时窗口设了 `WA_TranslucentBackground`。此前为解决“白底叠加致死白”，把 GLASS_QSS 基础规则设成 `QWidget { background-color: transparent }`。但 **transparent 会让 Qt 跳过该控件的背景填充/擦除**：半透明子控件重绘时不清除旧像素，旧画面与新画面叠加，切 tab/滚动时就产生重影。不是 GPU 性能问题，是背景不擦除导致的渲染合成问题。

## Fix（theme_settings.py，仅 GLASS_QSS）

1. 基础 `QWidget` 背景由 `transparent` 改为 `rgba(255,255,255,6)`：
   - alpha=6 极低，视觉几乎不降低透明度；
   - 但非透明，强制每帧背景填充，擦除旧像素，消除重影。
2. 内容承载面给近不透明背景，防止切页透影：
   - `QStackedWidget/QScrollArea/QMdiArea` → `rgba(248,250,255,200)`。
   - `QTabWidget::pane` 由 `rgba(255,255,255,110)` → `rgba(248,250,255,215)`。
3. 表格行 item 背景提高 alpha，滚动不残留：
   - 非交替行 `rgba(255,255,255,40)` → `200`。
   - 交替行 `rgba(219,234,254,100)` → `215`。
4. `QSplitter/QSplitterHandle` 保持透明（分隔条不需要底色）。

## Acceptance Criteria

- [x] offscreen 毛玻璃主题启动 + 遍历全部 tab 无异常。
- [ ] 真机：切 tab/滚动表格/移动控件无重影拖影。
- [ ] 真机：玻璃半透明质感保留（未退回死白）。

## Notes

- 非毛玻璃主题 QSS 未改动。
- 若真机仍有局部重影，通常是该控件设了 `WA_NoSystemBackground`/`WA_TranslucentBackground` 或 viewport 透明，按同样思路给其极低 alpha 背景即可。
