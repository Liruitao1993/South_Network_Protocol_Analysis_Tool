# 蓝牙自定义报文区空间治理（滚动封顶 + 可折叠 + 竖向分栏）

## Goal

蓝牙页「自定义报文」按钮越加越多时**直接挤占界面**：现状是 `QGroupBox` + `QGridLayout`（固定 3 列）
**无高度上限、无滚动、不可折叠**，而它挂在右栏 `[日志(stretch 1)] [发送区] [自定义区]` 的最下面
（`bluetooth_tool_widget.py:_build_right_panel`）。上限 `MAX_CUSTOM_BUTTONS = 64` ⇒ 最坏 22 行 × ≈30px
≈ 700px，日志窗口被压到看不见，窗口放大也救不了（组框高度由内容撑开）。

目标：**按钮数量增长时，自定义区的占用有上限、可收起、且用户能自己分配它与日志的竖向空间**。

用户已确认的口径（本轮问答）：

| 项 | 决定 |
|---|---|
| 任务 | 建立 Trellis 任务并推进 |
| 方案档位 | **B = 滚动 + 高度封顶（约 3 行）+ 整区可折叠（记忆展开态）** |
| 竖向空间 | **加竖向 QSplitter**（日志 ↔（发送区 + 自定义区）），用户可拖拽分配 |
| 网格列数 | **固定 3 列**（不做宽度自适应） |

## 现状证据

- 右栏组装：`_build_right_panel()` → `outer.addWidget(self._build_log_group(), 1)` + `_build_send_group()`
  + `_build_custom_group()`（**顺序固定、无分栏器**）。
- 自定义区：`_build_custom_group()` → `QGroupBox` + `QVBoxLayout` → `custom_host`(`QGridLayout`) + 工具栏行；
  `_rebuild_custom_buttons()` 按 `index // BUTTON_GRID_COLUMNS, index % BUTTON_GRID_COLUMNS` 落格
  （`BUTTON_GRID_COLUMNS = 3`），并 `custom_group.setTitle(f"自定义报文（{n}）")`。
- 可复用组件：`collapsible_section.CollapsibleSection`（独立模块，带 `toggled` 信号 / `set_expanded_quiet`
  / `is_content_hidden` / `set_title` / `content_layout()`；协议9 组帧页在用，测试 `test_collapsible_section.py`）。
  **不引入第二份折行布局**：`FlowLayout` 在 `main_gui.py` 里，而本页契约禁止 import `main_gui`
  （且 `main_gui.py` 属"随发版批次提交"的文件，本次不动它）⇒ 列数按用户口径固定 3 列。
- 配置读写：`core.load_settings/save_settings`（`bluetooth_tool_config.json`，原子写、坏文件宽容）；
  本页 `_apply_settings_to_ui()`（套用）/ `_collect_settings()`（采集）/ `_schedule_save()`（400ms 去抖）。

## Requirements

### R1 自定义区：封顶 + 内部滚动

- R1.1 `custom_host` 放进 `QScrollArea`（`setWidgetResizable(True)`、无边框、横向不滚动、纵向按需），
  并把 **`maximumHeight` 设为「3 行按钮 + 间距 + 边距」**（由实际按钮 `sizeHint().height()` 计算，
  无按钮时用字体高度兜底；**不写死像素**——本项目字号可配置，见 AGENTS 陷阱 63）。
- R1.2 封顶高度必须在**按钮重建后**与**主题/字号切换后**重算（`_rebuild_custom_buttons()` /
  `restyle_for_theme()`），保证大字号下仍不裁字、不越界。
- R1.3 按钮数量不超过 3 行时**不出现滚动条**、高度按内容收缩（不浪费空间）。

### R2 整区可折叠（记忆状态）

- R2.1 `_build_custom_group()` 改为返回 `CollapsibleSection`（标题 `自定义报文（N）`，工具栏行与滚动区
  都在其内容区）——收起时本区只占**一行标题**。
- R2.2 折叠状态变化 → 写 `settings["custom_collapsed"]`（True = 收起）并触发既有去抖保存；
  载入时按配置恢复（`set_expanded_quiet` 避免触发一轮保存）。

### R3 竖向分栏（日志 ↔ 发送+自定义）

- R3.1 右栏改为**竖向 `QSplitter`**：上 = 日志组（stretch 1），下 = 发送区 + 自定义区（stretch 0）；
  `setChildrenCollapsible(False)`（不允许拖到 0 高度，否则用户会"丢"掉日志或发送区）。
- R3.2 拖动完成后把 `sizes()`（`[上, 下]`，px）写进 `settings["right_split"]`；载入时套用（坏值/缺省 →
  默认值）；`merge_settings` 负责**夹紧与回落**（不抛异常）。

### R4 测试

- R4.1 `test_bluetooth_core.py`：`merge_settings` 对 `right_split`（缺省/坏类型/越界/长度不对）与
  `custom_collapsed`（坏值回落 False）的宽容处理；`right_split` 默认值在合法范围内。
- R4.2 `test_bluetooth_widget.py` 新增一节：
  - 自定义区在 `QScrollArea` 内且 `maximumHeight` ≤ 3 行高度（用真实按钮算上界）；
  - 加 40 个按钮（真实 show + resize）后：**日志组高度 ≥ 其最小高度**（不被挤没）、自定义区高度 ≤ 封顶；
  - 内容高度 > 封顶（证明「确实需要滚动」——判据非恒真）；
  - 收起 → 内容隐藏 + 本区高度骤减（≈ 标题行）；`settings["custom_collapsed"]` 被写入；
  - 竖向 `QSplitter` 存在、`setSizes` 后 `settings["right_split"]` 被记录；
  - **重启恢复**：同一配置路径新建页面 → 折叠态与分栏尺寸都恢复。
- R4.3 五份蓝牙测试 + `release_check.py --with-gui` FAIL=0（既有环境红除外）。

## Acceptance Criteria

- A1 加满 64 个按钮（或 40 个）后，**日志窗口仍可见可用**（高度 ≥ 其最小高度），自定义区停在上限高度、
  内部出现纵向滚动条。
- A2 收起自定义区后本区只占一行标题，展开后恢复；重开页面（同配置）状态一致。
- A3 拖动分栏器改变「日志/下半区」比例后重启仍保持；坏配置（`right_split: "x"`）回落默认且不报错。
- A4 按钮数很少（≤ 9）时**没有任何滚动条**、区域高度贴合内容（不出现大片空白）。
- A5 换字号/换主题后封顶高度随之重算（不裁字、不越界）。

## 非目标

- 不改按钮网格列数（保持 3 列）；不引入第二份 `FlowLayout`（`main_gui.FlowLayout` 不搬动）。
- 不做「按分组/关键字筛选」与「超量切下拉菜单」（用户本次未选；可作为后续增量）。
- 不改 `MAX_CUSTOM_BUTTONS`、不改按钮数据结构与发送/解析链路。
- 不改 Web 版。
