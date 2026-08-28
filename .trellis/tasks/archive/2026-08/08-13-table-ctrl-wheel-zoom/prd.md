# PRD：所有表格 Ctrl+滚轮缩放（类 Excel）

## 需求

所有解析/查询/监控/对比等 QTableWidget 支持 **Ctrl+滚轮** 整体缩放（类似 Excel）：
- Ctrl+上滚 → 1.1x 放大；Ctrl+下滚 → 0.9x 缩小（字号上限 24pt / 下限 5pt）
- 整体缩放 = 表格字号 + 行高同步缩放；列宽保持（摘要表 40/50/60px 固定列按比例缩放会破坏表头布局）
- **Ctrl+0** 恢复基准（缩放前字号/行高）
- 缩放为 per-table 覆盖；用户改全局字体设置后表格回到基准字号（语义合理）

## 范围

全仓 35 处 `QTableWidget(` 实例（11 个文件：main_gui 17、monitor/frame_monitor 2、monitor/tcp_monitor 4、monitor_widget 2、diff_widget 2、frame_gen_widget 3、archive_widget 1、llm_api_manager 1、lookup_pages 1、lookup_pages_simple 1、test_plan_widget 1）全部替换为可缩放基类。

## 约束

- 新增 `ZoomableTableWidget(QTableWidget)` 于 `gui_utils.py`（轻量工具模块，无循环依赖）；各文件 `from gui_utils import ZoomableTableWidget` 替换 `QTableWidget(`
- 基类保持 QTableWidget 全部既有行为（右键菜单/复制/Ctrl+C/高亮/双击深度解析等挂接不受影响——子类即父类）
- `setCellWidget` 的单元格（监控器字节高亮等）不随字体缩放——可接受
- 缩放因子 1.1/0.9，按 `angleDelta().y()` 累计生效（触控板小步长也响应）
- 基准记录：首次 Ctrl 缩放时记下 `font().pointSizeF()` 与 `verticalHeader().defaultSectionSize()`；Ctrl+0 恢复

## 验收标准

1. 任一表格（单帧解析/批量/查询/监控/对比）Ctrl+滚轮：字号与行高同步缩放、上下限钳制、无异常
2. Ctrl+0 恢复缩放前字号/行高
3. 无 Ctrl 修饰键时滚轮行为不变（滚动条滚动）
4. 全部 11 个文件 import 正常、解析/校验/批量回归全绿