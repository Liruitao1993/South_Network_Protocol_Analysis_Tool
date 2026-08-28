# 协议组下拉框选中文字完整显示

## Goal

协议选择组各 QComboBox 选中项文字被截断（如「[9] 新一代载波协议 (通感一体化」缺右括号、「自动识别」只显示「自动识」），要求控件完整显示当前选中文字。

## Root Cause

上一任务 `_fit_combo_to_current` 用手写常量 `pad=36`（文字宽 + 固定像素）作为内边距+下拉箭头宽度。高 DPI 缩放下箭头与边框实际更宽，pad 不足，尾字被裁。

## Implementation

文件：`main_gui.py`，`_fit_combo_to_current`

- 弃用手写 pad，改用 Qt style 精确测量：构造 `QStyleOptionComboBox`，填入 `currentText`，调用
  `combo.style().sizeFromContents(QStyle.ContentsType.CT_ComboBox, opt, QSize(text_w + pad_extra, 0), combo)`。
  该方法返回当前 style/DPI 下含下拉箭头、边框、内边距的准确控件尺寸，自动适配缩放。
- 在 style 结果基础上额外加 `pad_extra=12` 文字渲染余量，防止不同字体度量下尾字贴边/被截。
- 弹出列表宽度 = 列表最长文字 + `pad_extra*2`（列表无下拉箭头），长项完整可见。
- 抬高部分 combo 最小宽地板：channel combo 72→96、pb_frame_type 80→90，确保「自动识别」等短文字也完整。

## Acceptance Criteria

- [x] offscreen 验证协议 9 各 combo 控件宽 - 文字 advance = headroom 42~52px（style 精确余量），无截断。
- [x] 高 DPI 由 Qt style 自动同比放大，不再依赖手写 pad。
- [x] 全协议 0-11 × 解析级别/通道所有组合状态，协议组重叠对数为 0。
- [x] 语法检查通过、主窗口启动正常。

## Notes

- 轻量任务 PRD-only。延续 `08-25-combo-width-fit-current`。
