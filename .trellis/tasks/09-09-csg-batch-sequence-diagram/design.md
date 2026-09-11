# 技术设计：协议9批量解析通信时序图

## 架构与边界

新增一个独立文件 `sequence_diagram_widget.py`（遵循 AGENTS.md §4.1「新增 UI 组件必须拆分到独立文件」），分两层：

```
sequence_diagram_widget.py
├── 纯逻辑层（无 Qt，可脚本测试）
│   ├── SequenceNode      dataclass: key, tei, label, role
│   ├── SequenceMessage   dataclass: frame_idx, src_key, dst_key|None, label, kind, summary_full
│   ├── SequenceModel     dataclass: nodes: list[SequenceNode], messages: list[SequenceMessage], skipped: int
│   └── build_sequence_model_csg(batch_results) -> SequenceModel   # 协议9 提取器
│       # 预留 build_sequence_model(results, protocol) 分派入口，本期仅 protocol==9
└── UI 层（PySide6）
    ├── SequenceDiagramWidget(QWidget)
    │   ├── 工具栏：刷新 / 适应窗口 / 导出PNG / 状态标签（N 帧 / M 节点 / 跳过 K）
    │   ├── SequenceDiagramView(QGraphicsView)：缩放(滚轮+Ctrl)/拖拽平移
    │   └── set_model(model) / highlight_frame(frame_idx) / 信号 message_clicked(frame_idx)
    └── 场景绘制：_build_scene() 把 SequenceModel 布局为 QGraphicsItem
```

`main_gui.py` 只负责：注册懒加载标签页、批量解析工具栏「时序图」按钮、双向联动接线。绘制与提取逻辑全部在独立文件内。

## 数据流与契约

```
batch_results[i]["_table_data"]  (协议9 parse_to_table 输出)
        │  build_sequence_model_csg()
        ▼
SequenceModel {nodes, messages, skipped}
        │  SequenceDiagramWidget.set_model()
        ▼
QGraphicsScene（节点框/生命线/箭头/文字）
        │  message_clicked(frame_idx) 信号
        ▼
MainWindow: 切回批量解析 tab → 按 Qt.UserRole 反查行 → selectRow + scrollTo
        ▲
MainWindow: batch_summary_table.itemSelectionChanged → widget.highlight_frame(idx)
```

### 提取规则（协议9）

从每帧 `_table_data` 建 `{字段名: item}` 索引（同 `_get_csg_new_gen_summary` L7705 的做法）：

1. `_status != "成功"` → 跳过（skipped += 1）。
2. `定界符类型` 值为信标(0) 或 SACK(2) → 广播消息，src=CCO 节点，dst=None，kind=`beacon`/`sack`。
3. 存在 `源TEI`/`目的TEI`（parsed_value int）→ 单播消息；应用层 `发送类型` 注释含"广播"时改为广播。
4. 既无 TEI 又非信标/SACK → 跳过。
5. 消息标签：`batch_results[i]["摘要"]`；显示时超过 ~40 字截断为 `…`，完整文本放 tooltip；前缀帧序号 `#N`。

### 节点规则

- node key：`TEI:<int>`；TEI==1 → role=`CCO`，label=`CCO`；其余 role=`STA`，label=`STA-{tei:04X}`。
- 节点排序：CCO 恒为最左，其余按在消息流中首次出现的顺序。
- 广播消息不产生目的节点；信标/SACK 的 src 恒为 CCO 节点（不存在则创建）。

### 布局（QGraphicsScene 坐标）

- 节点框：顶部 y=0，高 36px，宽随文字；水平间距固定 200px，x = index*200。
- 生命线：节点框底到场景底的竖直虚线。
- 消息行高 48px：第 k 条消息 y = 60 + k*48。
- 单播：源生命线→目的生命线实线箭头（QGraphicsLineItem + 自绘箭头多边形），标签文字放线段中点上方。
- 广播：源生命线向右贯穿全场景的虚线 + 末端箭头，标签同上（参考用户提供图样的信标帧画法）。
- 高亮：设置该消息箭头画笔颜色为主题强调色并加粗，同时 `ensureVisible`。

### 联动防循环

`MainWindow` 侧加 `_seq_sync_guard` 布尔标志：摘要表 → 图 与 图 → 摘要表 两个方向都在入口置位、出口复位，对侧回调发现置位直接 return（模式同现有 `_lazy_tab_guard`，L1102）。

### 行索引映射

图上消息存的是 `batch_results` 原始索引；摘要表第 0 列 item 的 `Qt.UserRole` 也存原始索引（L7516）。图 → 表：遍历摘要表行找 UserRole 匹配项。表 → 图：点击行取 UserRole 传给 `highlight_frame`。

## 兼容性与回退

- 纯新增文件 + main_gui.py 增量接线，不改动任何 parser / validator / 现有导出逻辑；回退 = 还原 main_gui.py 接线段 + 删新文件。
- PyInstaller：纯 PySide6 自绘，无新依赖，spec 无需变更；若图标使用现有 `icons/` 资源需确认已在 spec 打包清单（现有机制已覆盖 icons/ 整目录）。
- 协议下拉非 9 时点「时序图」：按钮仅在 `current_protocol == 9` 时启用（同档案管理/拓扑 tab 的协议限定惯例）。

## 重要取舍

| 决策 | 选择 | 放弃项与理由 |
|---|---|---|
| 渲染技术 | QGraphicsView 自绘 | Mermaid/HTML：需内嵌浏览器或外部查看，交互联动弱 |
| 消息标签 | 复用 `摘要` 字段 | 重新格式化：与摘要表不一致，维护双份 |
| 数据范围 | 有勾选用勾选，否则全部 | 另设帧范围输入框：与「导出选中」惯例重复 |
| 节点标识 | TEI | MAC 地址：过长，序列图横向放不下 |

## 测试设计

新增 `test/test_csg_sequence_model.py`（脚本式断言，沿用 test/ 目录惯例）：

- T1 从样本帧 `_table_data` 提取源/目的 TEI 正确
- T2 TEI=1 → CCO 节点且排序最左
- T3 信标帧 → kind=beacon、src=CCO、dst=None
- T4 SACK 帧 → 广播
- T5 解析失败帧计入 skipped 不产生消息
- T6 节点按首次出现排序、同 TEI 去重
- 样本帧来源：复用 test/ 目录现有协议9测试帧常量（test_csg_summary.py 等）

回归：`test_csg_summary.py`、`test_csg_batch_parse_level.py`、`test_csg_batch_prefix.py` 全过。
