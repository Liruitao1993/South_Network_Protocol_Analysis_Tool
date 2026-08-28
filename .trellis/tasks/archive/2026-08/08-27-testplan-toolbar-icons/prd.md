# 测试方案工具栏按钮补齐图标

## Goal

测试方案 tab 工具栏 12 按钮中 6 个（上移/下移/编辑选中/导出/导入/清空结果）仍为纯文字，用户要求设计/补齐图标。评估 Qt 标准图标映射与自定义图标方案。

## Background (confirmed facts)

`test_plan_widget.py` 工具栏 12 个按钮当前状态（L1469-1562）：

| 按钮 | 现有图标 (set_btn_icon key) |
|---|---|
| 添加 | add (SP_FileDialogNewFolder) |
| 删除 | delete (SP_TrashIcon) |
| 上移 | **无** |
| 下移 | **无** |
| 清空后台 | clear (SP_LineEditClearButton) |
| 编辑选中 | **无** |
| 开始测试 | play (SP_MediaPlay) |
| 停止测试 | stop (SP_MediaStop) |
| 导出（JSON） | **无** |
| 导入（JSON） | **无** |
| 清空结果 | **无** |
| 导出报告 | export (SP_DialogSaveButton) |

另：表格行内操作列按钮（发送/等待/后台/Lua，sm 尺寸，set_btn 配色区分）目前纯文字。

现有体系（gui_utils.py，1.15.0）：`set_btn_icon(btn, key)` 用 Qt 内置 QStyle 标准图标，零资源文件、跨平台、随主题；`_STANDARD_ICON_MAP` 已有 open/save/export/open_file/add/apply/ok/cancel/refresh/delete/clear/play/stop/pause/copy/help/warning。

实测渲染（offscreen contact sheet）Windows 原生 QStyle 图标为 Vista/7 风格彩色老图标：
- SP_ArrowUp/SP_ArrowDown = 绿色上/下箭头 → 上移/下移 语义完美
- SP_DialogOpenButton = 黄色文件夹（open_file 已用于「加载」）→ 导入可用
- SP_DialogSaveButton = 蓝色软盘（export 已用于全部导出按钮）→ 导出 JSON 保持一致
- SP_LineEditClearButton = 灰圆叉（clear 已用于清空后台）→ 清空结果保持一致
- **QStyle 无「编辑/铅笔」标准图标**：候选 SP_FileDialogListView（文件+横线，最像文档编辑）/ SP_FileDialogContentsView（文件夹+循环箭头，语义不符）/ SP_FileIcon（文件+放大镜，偏查看）

## Requirements

沿用现有 Qt 标准图标体系（`gui_utils.set_btn_icon`，1.15.0 起）为测试方案工具栏 6 个纯文字按钮补齐图标，图标+文字并存：

| 按钮 | icon_key | QStyle 标准图标 |
|---|---|---|
| 上移 | `up`（新增映射） | SP_ArrowUp（绿色向上箭头） |
| 下移 | `down`（新增映射） | SP_ArrowDown（绿色向下箭头） |
| 编辑选中 | `edit`（新增映射） | SP_FileDialogListView（文件+横线，文档编辑隐喻；QStyle 无铅笔图标） |
| 导出（JSON） | `export`（复用） | SP_DialogSaveButton（软盘，与导出报告/其他导出按钮一致） |
| 导入（JSON） | `open_file`（复用） | SP_DialogOpenButton（打开文件夹，与「加载」类按钮一致） |
| 清空结果 | `clear`（复用） | SP_LineEditClearButton（圆叉，与「清空后台」一致） |

- `gui_utils._STANDARD_ICON_MAP` 新增 3 个 key：`up`/`down`/`edit`
- 按钮文字、tooltip、set_btn 配色、信号连接全部不变；未知 key 静默跳过的既有行为不变

## Acceptance Criteria

- [ ] 测试方案工具栏 12 个按钮全部带标准图标 + 中文文字；6 个新补图标视觉语义正确（箭头方向、清空圆叉、导入文件夹/导出软盘）
- [ ] 表格行内操作按钮（发送/等待/后台/Lua）维持现状（sm 尺寸 + 配色语义），不加图标
- [ ] offscreen 冒烟：TestPlanWidget 实例化后 6 个按钮 `icon()` 非空；tooltip/文字/clicked 行为不变
- [ ] `py_compile` 通过；其他 tab 按钮图标无回归（map 仅新增 key，不改既有映射）

## Out of Scope

- 自定义 SVG 图标设计 / 全应用图标替换（用户已选标准图标方案）
- 其他 tab（批量/组帧/监控等）的图标调整
- 表格行内操作按钮（发送/等待/后台/Lua）
- CHANGELOG：不单独 bump 版本；改动并入当前未发布的 1.16.1 CHANGELOG 条目（同日 UI 完善）

## Open Questions

- 无（方案已经用户确认：Qt 标准图标补齐）
