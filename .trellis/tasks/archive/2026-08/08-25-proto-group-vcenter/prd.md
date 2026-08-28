# 协议组 FlowLayout 行内垂直居中

## Goal

「协议选择」组内文字标签（QLabel，约 11-12px 高）比下拉框/数字框（QComboBox/QSpinBox，约 22-24px 高）矮，FlowLayout 原按顶部对齐，导致文字纵轴偏上，与选项框不居中对齐。要求同一行控件垂直居中。

## Root Cause

上一任务新增的 `FlowLayout._do_layout` 把每行控件的 y 都设为行顶 y（顶对齐）。QLabel 高度小于输入控件时，标签贴在行顶，视觉上文字与选项框纵轴不齐。

## Implementation

文件：`main_gui.py`，`FlowLayout._do_layout`

- 改为先按行收集控件（`rows = [(row_items, line_height), ...]`），布局分两遍：
  1. 第一遍算换行位置与每行最大高度 `line_height`（不 setGeometry）。
  2. 第二遍对每个控件用 `cy = iy + (line_height - hint.height()) // 2` 垂直居中后 `setGeometry`。
- `heightForWidth` 返回值用最后一行高度正确累加，多行换行/窄窗行为不变。

## Acceptance Criteria

- [x] offscreen 检查协议 9 同一行所有控件垂直中心一致（行1 center≈34.0，行2 center≈63.5）。
- [x] 文字标签与 QComboBox/QSpinBox 纵轴居中对齐。
- [x] 不引入重叠（上一任务的 overlap=0 回归保持）。
- [x] 语法检查通过、主窗口启动正常。

## Verification

```
QLabel    center=34.0  当前协议：
QComboBox center=34.0
QLabel    center=33.5  解析级别：
QComboBox center=34.0
...
```

## Notes

- 轻量任务 PRD-only。
