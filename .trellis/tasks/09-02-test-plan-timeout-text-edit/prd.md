# 测试方案表格超时列改纯文本输入

## 背景

测试方案页（`test_plan_widget.py`）表格"超时(ms)"列（col 10）当前用内嵌 `QSpinBox` 作为 cell widget。SpinBox 上下调节按钮占窄单元格宽度，超时数字被遮挡，看不清当前值。用户建议直接填写文本即可。

## 需求

1. 表格 col 10 改为可编辑 `QTableWidgetItem`，显示超时毫秒数（默认 2000），双击/选中直接输入数字。
2. 输入校验：必须为整数，范围 100–600000（与原 SpinBox range 一致）；非法或越界输入还原为修改前的值。
3. 持久监听行（persistent）该列不可编辑（原 SpinBox 为 disabled）。
4. AddTestItemDialog（添加测试项对话框）中的超时 SpinBox 保留不变（对话框空间充足，无遮挡）。
5. 删除不再使用的 `_on_timeout_changed`。
6. 同步修改手动测试副本 `test/test_plan_widget.py`（独立运行的快照副本）。

## 验收标准

- 表格中超时列数字完整可见，无 SpinBox 按钮遮挡。
- 输入合法数字后 `timeout_ms` 更新并自动保存；输入非法内容后单元格还原旧值。
- 测试执行超时行为与修改前一致（读 `item["timeout_ms"]`）。
- `python test/test_plan_widget.py` 方式的独立副本行为一致。
- 持久监听行超时列不可编辑。
