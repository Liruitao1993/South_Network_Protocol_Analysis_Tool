# 协议9批量解析通信时序图

## Goal

协议9（新一代载波/通感一体化）批量解析后，目前只能看逐帧摘要列表，研发难以快速理解整个通信过程（如 CCO 与多个 STA 间的信标→关联→抄读流程）。本任务在 GUI 中新增**通信时序图**功能：将批量解析结果自动渲染为类似标准序列图（顶部网元、纵向生命线、带箭头的消息流）的交互图，并与摘要列表双向联动，让研发一眼看清"谁在什么时候和谁说了什么"。

## Confirmed Facts（代码证据）

- 批量解析结果存于 `main_gui.py` `MainWindow.batch_results`（约 L7486-L7507）：每项含 `_input`/`_status`/`_table_data`/`_type_name`/`摘要`。
- 摘要表 `batch_summary_table`（L2535 起）列：#/状态/长度/协议/类型/摘要；第 0 列 item 的 `Qt.UserRole` 存原始 `batch_results` 索引；`cellClicked → _on_batch_row_selected`（L2566）展示详情。
- 协议9摘要由 `_get_csg_new_gen_summary`（L7686 起）生成，其结果已存入 `batch_results[i]["摘要"]`，可直接复用为消息标签。
- 协议9 `_table_data` 中可提取：FC 级 `源TEI`/`目的TEI`（csg_new_gen_parser.py L1864/L1869、L1922/L1927，parsed_value 为 int）、`定界符类型`（0=信标/1=SOF/2=SACK/3=网间协调，L713）、应用层 `发送类型` 含广播枚举（L165-L168）。信标/SACK 帧无 TEI，语义为 CCO 广播。
- GUI 惯例：新增 UI 组件必须拆分为独立文件（AGENTS.md §4.1，参考 `frame_gen_widget.py`、`diff_widget.py`）；新标签页用懒加载 `_replace_lazy_tab`（main_gui.py L2975）。
- 批量解析输入为 hex 文本，**无时间戳** → 时序图纵轴按帧顺序（#1、#2…）排列，不表达真实时间间隔。
- 项目无正式测试框架，`test/` 目录为脚本式断言测试（如 test_csg_summary、test_csg_batch_parse_level）。

## Requirements

### R1 时序图标签页（内嵌 GUI）
- 新增独立标签页「通信时序图」，懒加载，位置紧跟「批量解析」之后。
- 使用 PySide6 QGraphicsView/QGraphicsScene 自绘：顶部网元节点框 + 名称（角色+TEI），纵向生命线，消息按帧序自上而下排列。
- 零新增第三方依赖。

### R2 节点与消息提取（纯逻辑，可无 GUI 测试）
- 节点标识：`源TEI`/`目的TEI`；TEI=1 标注 `CCO`，其余标注 `STA-xxxx`；节点按 CCO 固定最左、其余按首次出现排序。
- 消息方向：源TEI→目的TEI 画实线箭头；信标帧、SACK 帧、应用层发送类型含"广播"的画虚线广播箭头（CCO→全网）。
- 消息标签：直接复用 `batch_results[i]["摘要"]`，过长时省略号截断，完整摘要放 tooltip；每条消息带帧序号 `#N`。
- 解析失败（`_status != 成功`）或无 TEI 且非信标/SACK 的帧跳过，状态栏显示"已跳过 N 帧"。

### R3 生成入口与数据范围
- 批量解析工具栏新增「时序图」按钮：摘要表有勾选行时仅用勾选帧（对齐现有「导出选中」交互惯例），否则用全部帧；生成后自动切到时序图标签页。
- 时序图页内提供「刷新」按钮，按当前 batch_results 重新生成。

### R4 交互
- 滚轮/Ctrl+滚轮缩放、拖拽平移、「适应窗口」一键复位。
- 点击消息箭头/标签 → 跳转批量解析页并选中、滚动到对应帧行。
- 反向：摘要表选中行变化 → 时序图对应消息高亮（需防信号循环）。

### R5 导出
- 「导出 PNG」：QGraphicsScene.render 渲染整图保存，分辨率自适应内容尺寸。

## Acceptance Criteria

- [ ] AC1：对含 CCO+多 STA 的协议9样本日志批量解析后，点击「时序图」生成图：CCO 在最左，各 STA 按出现顺序排列，消息箭头方向、序号、摘要文字与摘要表逐帧一致。
- [ ] AC2：信标帧显示为 CCO 发出的虚线广播消息；SACK 同样处理。
- [ ] AC3：点击图上任意消息，自动切回批量解析页并定位到对应帧行；选中摘要表某行，图上对应消息高亮。
- [ ] AC4：勾选部分帧后点「时序图」，图中只出现勾选帧对应的消息。
- [ ] AC5：解析失败帧不出现在图中，状态栏提示跳过数量。
- [ ] AC6：「导出 PNG」生成的图片内容与视图一致、完整无裁剪。
- [ ] AC7：模型提取逻辑有 test/ 下断言测试覆盖（TEI 提取、CCO 判别、广播判别、跳过逻辑）；现有 test_csg_summary / test_csg_batch_parse_level 等回归通过。
- [ ] AC8：未做批量解析（batch_results 为空）时点「时序图」，给出明确提示而非崩溃。

## Out of Scope

- 其他协议（0-8）的时序图。

## Scope 变更（2026-09-10 用户追加）

- 时序图覆盖协议 **9/10/11**（南网新一代/国网新一代双模/HDC 1.0）：三协议解析器字段同构（定界符类型/源TEI/目的TEI/发送类型/MMTYPE，仅字段名与缩进差异），提取器统一为通用实现（去缩进索引 + 多字段名候选），build_sequence_model 对 9/10/11 分派同一管道；标签页与「时序图」按钮对三协议可见/可用。
- Reflex Web 版时序图。
- 真实时间轴/时间间隔比例表达（批量输入无时间戳）。
- Mermaid/PlantUML/HTML 导出（用户已选 GUI 内嵌方案）。
- 参考图中的"阶段注释框"（如周期性获取地址列表的批注）——后续可按需追加。

## Key Decisions（用户已确认）

1. 呈现形式：GUI 内嵌时序图标签页，QGraphicsView 自绘。
2. 节点标识：TEI + 角色自动判别，TEI=1 为 CCO。
3. 交互密度：摘要文字 + 点击双向联动摘要表。
4. 流程：走 Trellis 完整规划（prd/design/implement 审阅后再实施）。

## Risks / Deferred

- 大量帧（数百+）时场景高度很大：依赖 QGraphicsView 滚动 + 缩放应对，不设帧数上限；若实测卡顿再考虑分页（本期不处理）。
- ED 监控包装帧：其 `_table_data` 内含业务帧的 TEI 字段，按同一字段提取即可，包装头本身不产生节点。
