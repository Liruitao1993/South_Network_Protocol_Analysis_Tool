# 执行计划：协议9批量解析通信时序图

## 实施清单（按序执行）

### 1. 纯逻辑模型层 `sequence_diagram_widget.py`（前半）
- [ ] 定义 `SequenceNode` / `SequenceMessage` / `SequenceModel` dataclass
- [ ] 实现 `build_sequence_model_csg(batch_results) -> SequenceModel`：
  - `_status` 过滤与 skipped 计数
  - `定界符类型` 信标(0)/SACK(2) 广播判别
  - `源TEI`/`目的TEI` 提取（parsed_value int）
  - 应用层 `发送类型` 含"广播"判别
  - 节点去重、CCO 最左、首现排序
- [ ] 预留 `build_sequence_model(results, protocol)` 分派入口（仅 9 有实现，其余返回 None）

### 2. 模型测试 `test/test_csg_sequence_model.py`
- [ ] T1~T6（见 design.md 测试设计），样本帧复用 test/ 目录现有协议9帧
- [ ] 验证：`python test/test_csg_sequence_model.py` 全过

### 3. UI 层 `sequence_diagram_widget.py`（后半）
- [ ] `SequenceDiagramView(QGraphicsView)`：滚轮+Ctrl 缩放、DragMode.ScrollHandDrag 平移
- [ ] `SequenceDiagramWidget`：工具栏（刷新/适应窗口/导出PNG/状态标签）+ view
- [ ] `_build_scene()`：节点框、生命线、单播实线箭头、广播虚线箭头、消息标签（截断+tooltip+帧序号）
- [ ] 消息 item 存 `frame_idx`（setData），点击发出 `message_clicked` 信号
- [ ] `highlight_frame(frame_idx)`：高亮 + ensureVisible；`set_model(model)` 重建场景
- [ ] 导出 PNG：`QImage` + `QPainter` + `scene.render`，QFileDialog 保存
- [ ] 按钮图标遵循项目惯例（icons/ 现有资源 + `_make_toolbar_btn` 风格）

### 4. main_gui.py 接线
- [ ] 注册「通信时序图」懒加载占位页 + `_replace_lazy_tab`（位置紧跟批量解析 tab）
- [ ] 批量解析工具栏新增「时序图」按钮：空结果提示；有勾选用勾选帧，否则全部；仅协议9启用；生成后切 tab
- [ ] 接线 `message_clicked` → 切回批量解析 tab + 按 UserRole 反查行 + selectRow + scrollToItem
- [ ] 接线 `batch_summary_table.itemSelectionChanged` → `highlight_frame`；加 `_seq_sync_guard` 防循环
- [ ] 重新批量解析/清空时重置时序图模型（或标记过期，点刷新重建）

### 5. 文档与收尾
- [ ] `main_gui.py` CHANGELOG 新增条目（版本号按发版时再 bump，本期先写条目内容）
- [ ] AGENTS.md §3 架构总览 GUI 组件清单补充 `sequence_diagram_widget.py`

## 验证命令

```bash
python test/test_csg_sequence_model.py        # 新模型测试
python test/test_csg_summary.py               # 回归
python test/test_csg_batch_parse_level.py     # 回归
python test/test_csg_batch_prefix.py          # 回归
python -c "import sequence_diagram_widget"    # 导入冒烟（无 Qt 环境也能过纯逻辑层）
python main_gui.py                            # 手工 GUI 验证 AC1~AC6、AC8
```

## 风险点与回退

- 风险 1：信标/SACK 帧 `_table_data` 中 `定界符类型` 字段的 parsed_value 形态（int 还是 "0" 字符串）需在步骤 1 实测确认，提取时做 int() 容错转换（参考 CHANGELOG L385 int() 0x 前缀崩溃教训）。
- 风险 2：ED 监控包装帧的字段名可能与裸帧不同，步骤 2 测试需覆盖一条 ED 样本。
- 风险 3：大量帧时场景性能——本期不优化，实测卡顿再议（prd Risks 已声明）。
- 回退点：步骤 1-2（纯逻辑）与 3-4（UI/接线）相互独立；任何一步失败可只还原对应文件，main_gui.py 接线为增量片段易摘除。

## 开始前检查

- [ ] 用户已批准最终规划总结
- [ ] `task.py start` 执行，状态 in_progress
