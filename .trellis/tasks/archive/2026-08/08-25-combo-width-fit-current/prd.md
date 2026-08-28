# 协议组下拉框按当前选中文字自适应宽度

## Goal

协议选择组里的 QComboBox 宽度不再固定按「选项列表中最长项」撑宽，而是按**当前选中项显示的文字**实时自适应；切换选项后控件收/放到新文字宽度，弹出列表仍保证能看到最长项。

## Root Cause

此前为消除重叠，给各 combo 设置了 `AdjustToMinimumContentsLengthWithIcon` + 固定 `setMinimumWidth`，控件宽度锁定为列表最长项宽度（或一个固定最小值），选中短文字（如「自动识别」）时也占着大块空间。用户要求按选中后实际显示的文字宽度贴合。

## Implementation

文件：`main_gui.py`

1. 新增 `_fit_combo_to_current(combo, pad=36, min_w=72)`：
   - 用 `fontMetrics().horizontalAdvance(currentText()) + pad` 计算控件宽度，同时 `setMinimumWidth/setMaximumWidth` 锁死该宽（贴合当前文字，不被最长项撑大）。
   - 遍历列表项测量最长文字，给弹出视图 `combo.view().setMinimumWidth(...)`，保证下拉展开时长项不被截断。
2. 创建时拟合一次：`protocol_combo`（min 120）、`csg_parse_level_combo`（90）、`csg_channel_combo`（72）、`gw_parse_level_combo`（90）、`csg/gw_pb_frame_type_combo`（80）、`gw_channel_combo`（72）。
3. 在相关切换回调中重新拟合再 reflow：
   - `_on_protocol_changed`：全部 combo 拟合 + `_reflow_proto_group()`。
   - `_on_csg_parse_level_changed` / `_on_gw_parse_level_changed`：本级 combo + 帧类型 combo 拟合 + reflow。
   - `_on_csg_channel_changed` / `_on_gw_channel_changed`：通道 combo 拟合 + reflow。
4. 移除各 combo 原先写死的 `setMinimumWidth(...)` 与 `AdjustToMinimumContentsLengthWithIcon` 固定宽度约束（fitter 接管）。

## Acceptance Criteria

- [x] offscreen 验证：选中项文字变化时控件宽度跟随变化。
      例：解析级别「自动识别」=90px → 「FC+PB解析(完整MPDU)」=201px；
      协议 0（长名）=372px → 协议 9（短名）=264px；通道「HRF」=102px。
- [x] 弹出列表视图最小宽度 ≥ 控件宽度，长选项完整可见。
- [x] 全协议、多次切换后协议组重叠对数为 0。
- [x] 语法检查通过、主窗口启动正常。

## Notes

- 轻量任务 PRD-only。
- 与 `08-25-proto-group-flow-layout`、`08-25-proto-group-vcenter` 同属协议组 UI 修整。
