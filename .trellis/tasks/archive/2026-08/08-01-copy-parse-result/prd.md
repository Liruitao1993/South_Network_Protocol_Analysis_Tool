# 全局解析结果复制功能

## Goal

所有协议的解析结果表格（单帧、批量、弹窗、监控器）统一支持复制操作，用户可以通过右键菜单或 Ctrl+C 快捷键复制选中行或全部解析结果，粘贴到 Excel/文档时保持表格结构。

## Background / Confirmed Facts

- 单帧解析结果：`self.result_table_widget` (QTableWidget, 4列: 字段/原始值/解析值/说明) — main_gui.py:787
- 批量摘要表：`self.batch_summary_table` (QTableWidget, 5列: #/状态/长度/协议类型/摘要) — main_gui.py:1234
- 批量详情表：`self.batch_detail_table` (QTableWidget, 4列) — main_gui.py:1292
- 批量原始HEX：`self.batch_detail_hex` (QTextEdit) — main_gui.py:1277，已有复制按钮
- DLMS 深度解析弹窗表格：局部变量 `table` (QTableWidget) — main_gui.py:4945
- 实时监控解析结果表：`monitor/frame_monitor.py` 中 `self._parse_result_table` (QTableWidget)
- 所有 QTableWidget 均未设置自定义右键菜单，也无复制快捷键
- `gui_utils.py` 已有 `setup_chinese_context_menu` 但仅支持 QLineEdit/QTextEdit

## Requirements

### R1. 表格右键菜单

所有解析结果 QTableWidget 提供右键菜单，包含：
- 复制选中行（默认，有选中时启用）
- 复制全部（始终启用）

### R2. Ctrl+C 快捷键

所有解析结果 QTableWidget 支持 Ctrl+C：
- 有选中行时，复制选中行
- 无选中时，复制全部

### R3. 复制格式

- 制表符（\t）分隔列，换行符（\n）分隔行
- 第一行为表头（列标题）
- 粘贴到 Excel 可直接分列显示

### R4. 覆盖范围

必须覆盖以下全部表格：
- 单帧解析结果表（result_table_widget）
- 批量摘要表（batch_summary_table）
- 批量详情表（batch_detail_table）
- DLMS 深度解析弹窗表格
- 实时监控器解析结果表（monitor/frame_monitor.py）

### R5. QTextEdit 复用已有能力

批量原始 HEX 的 QTextEdit 已有原生复制（Ctrl+C）和右键菜单，无需额外处理。

## Acceptance Criteria

- [ ] 单帧解析结果表：右键有"复制选中行""复制全部"，Ctrl+C 正常工作
- [ ] 批量摘要表：右键有"复制选中行""复制全部"，Ctrl+C 正常工作
- [ ] 批量详情表：右键有"复制选中行""复制全部"，Ctrl+C 正常工作
- [ ] DLMS 深度解析弹窗表格：右键有复制选项，Ctrl+C 正常工作
- [ ] 实时监控器解析结果表：右键有复制选项，Ctrl+C 正常工作
- [ ] 复制内容包含表头，制表符分隔，粘贴到 Excel 分列正确
- [ ] 空表时复制不报错，给出空内容或提示
- [ ] 不影响现有表格的双击、点击、选中行为

## Out of Scope

- 复制为 CSV/Excel 文件（已有导出功能）
- 复制为 JSON/HTML 格式
- 查询页、预设页等非结果表格的复制
- 复制图片/富文本格式
