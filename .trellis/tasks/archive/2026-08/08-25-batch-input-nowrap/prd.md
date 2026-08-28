# 批量输入框禁止自动折行

## Goal

批量输入报文框中，一行即一帧。超长帧不得在可视区自动折行，改用水平滚动条查看，保证按行预处理/切帧不被视觉换行干扰。

## Requirements

- 批量输入框（`self.batch_input`，`DragDropTextEdit`）设置为不自动换行。
- 超长行通过水平滚动条查看，垂直滚动行为不变。
- 仅影响该输入框，不波及其他 `QTextEdit`/`DragDropTextEdit` 用途（当前仅此一处使用）。

## Acceptance Criteria

- [x] 输入超长 hex 帧不在控件宽度处折行，底部出现水平滚动条。
- [x] 每行文本保持原始换行边界，按行切分的预处理逻辑不受影响。
- [x] 其他文本框行为不变。

## Implementation

- 文件：`main_gui.py:1731`
- 改动：在 `self.batch_input = DragDropTextEdit()` 之后增加
  `self.batch_input.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)`。

## Notes

- `DragDropTextEdit` 仅被批量输入框使用，直接在创建处设置即可，无需改类定义。
