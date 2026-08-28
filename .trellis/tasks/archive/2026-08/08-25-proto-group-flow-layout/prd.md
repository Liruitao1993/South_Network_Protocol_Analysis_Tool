# 修复协议选择组控件重叠

## Goal

软件启动后顶部「协议选择」分组内控件重叠：协议下拉框与「自动识别」等辅助控件叠在一起，高 DPI / 窄窗口下尤其明显。要求该控件组在任何窗口宽度、任何协议下都不重叠，空间不足时自动换行。

## Root Cause

协议选择组用单个 `QHBoxLayout` 排列全部控件，水平布局不支持换行。同时 `protocol_combo` 设置了 `AdjustToContents`，下拉框自身宽度被撑到最长协议名（约 480px）。协议 9/10 同行还要显示「解析级别 / 通道 / 剔除前 / 尾部」等控件，各控件最小宽之和超过协议组实际宽度，Qt 排不下即重叠。

附带问题：`csg_channel_label`（「通道：」标签）初始隐藏，但切到协议 9 时只显示了 `csg_channel_combo`，漏显 label。

## Requirements

- 协议选择组在空间不足时自动换行，控件永不重叠。
- 协议下拉框不再因最长协议名而强行撑宽；弹出列表仍能看到完整协议名。
- 切换协议动态显隐辅助控件后，分组高度与换行立即重算正确。
- 修复协议 9「通道：」标签不显示的问题。

## Implementation

文件：`main_gui.py`

1. 新增 `FlowLayout(QLayout)` 类（Qt 官方 FlowLayout 实现，支持 `heightForWidth` 自动换行）。
2. 协议选择组 `proto_layout` 由 `QHBoxLayout` 改为 `FlowLayout(margin=4, spacing=6)`，保存 `self.proto_group`。
3. `protocol_combo`：
   - `setMinimumWidth(150)`（原 320）。
   - 去掉 `AdjustToContents`，改用 `AdjustToMinimumContentsLengthWithIcon` + `setMinimumContentsLength(12)`。弹出列表宽度仍自适应最长项。
4. 收紧辅助 combo 最小宽：`csg_parse_level_combo` 180→140、`csg_channel_combo` 100→80、`gw_parse_level_combo` 150→120。
5. 新增 `_reflow_proto_group()`：`layout.invalidate()` + `group.updateGeometry()` + `group.adjustSize()`。在 `_on_protocol_changed`、`_on_csg_parse_level_changed`、`_on_gw_parse_level_changed` 末尾调用，修复动态显隐后 heightForWidth 缓存不更新导致的组高不变/重叠。
6. 修复 `_on_protocol_changed` 中 `csg_channel_label` 漏设可见：切到协议 9 时随 combo 一起 `setVisible(True)`。
7. 移除原 `proto_layout.addStretch()`（FlowLayout 无此方法）。新增 `from PySide6.QtWidgets import QLayout` 及 `QRect/QPoint/QSize` 导入。

## Acceptance Criteria

- [x] offscreen 自动化：窗口宽 650/1000/1280 下，遍历协议 0-11，协议组内可见控件重叠对数均为 0。
- [x] 窄窗（650px）下协议 9 控件自动换到多行而非溢出重叠。
- [x] 切换协议 9 时「通道：」标签正常显示。
- [x] 启动主窗口无异常，默认协议 0 布局正常。

## Verification

```bash
# 语法 + offscreen 实例化，遍历协议检测几何重叠
QT_QPA_PLATFORM=offscreen python -c "..."
# 结果：全部协议 overlap=0，窄窗自动换行，launch OK
```

## Notes

- 轻量任务 PRD-only。
