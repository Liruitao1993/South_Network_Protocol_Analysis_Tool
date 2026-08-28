# 修复启动时协议选择组黑块

## Goal

软件刚启动时，顶部「协议选择」分组区域出现一块黑色/异常空白矩形（子控件位置不对），最大化窗口后恢复正常。消除该首次布局错误。

## Root Cause

协议选择组使用自定义 `FlowLayout`（heightForWidth 自动换行）。窗口首次 show 时，proto_group 在顶部 `QHBoxLayout` 中的宽度尚未最终确定，FlowLayout 第一次 setGeometry 用了未确定的 rect，子控件被排到错误位置，露出 group 背景形成黑块；最大化触发布局重算后归位。

## 尝试与最终方案

- 曾尝试重写 `FlowLayout.minimumSize()` 按参考宽度算换行高度，但会把 proto_group 最小尺寸锁成多行高/固定宽，导致 group 在顶栏被挤成 284×157 且不随窗口拉伸——已回退。
- 最终方案（main_gui.py showEvent）：首次显示后用 `QTimer.singleShot(0, self._reflow_proto_group)` 按真实宽度重排一次，`_proto_first_reflowed` 标志保证只执行一次。这是最小且不破坏尺寸协商的修复。

## Fix

- `MainWindow.showEvent`：super 之后，若 `_proto_first_reflowed` 为假，置真并 `QTimer.singleShot(0, self._reflow_proto_group)`。
- `FlowLayout.minimumSize` 保持原实现（对各子项 minimumSize 取 expandedTo），不强行计算换行高度。

## Acceptance Criteria

- [x] offscreen：启动 show 后协议组尺寸正常；协议9 自动换行；最大化 1298×53 单行。无异常高度。
- [ ] 真机：启动时协议选择组无黑块，控件即处于正确位置，无需最大化。
- [ ] 三主题正常，窗口缩放时协议组正确换行/不重叠。

## Notes

- 若真机仍偶发黑块，下一步可在 `MainWindow.resizeEvent` 首次 resize 时也调一次 `_reflow_proto_group`。
