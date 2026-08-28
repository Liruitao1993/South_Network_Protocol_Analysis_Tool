# 设计：所有表格 Ctrl+滚轮缩放（类 Excel）

## 1. 基类（`gui_utils.py` 追加）

```python
class ZoomableTableWidget(QTableWidget):
    """支持 Ctrl+滚轮整体缩放的表格（类 Excel）。

    缩放 = 字号 + 行高同步（列宽保持，避免破坏固定列布局）；
    Ctrl+0 恢复缩放前基准。缩放为 per-table 覆盖，全局字体设置变更后回到基准。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._zoom_base: Optional[tuple] = None  # (pointSizeF, defaultSectionSize)

    def _zoom_start(self):
        """首次缩放前记录基准（缩放前字体为基准字号）"""
        if self._zoom_base is None:
            self._zoom_base = (self.font().pointSizeF() or 9.0,
                               self.verticalHeader().defaultSectionSize() or 20)

    def _apply_zoom(self, factor: float):
        self._zoom_start()
        f = self.font()
        f.setPointSizeF(max(5.0, min(24.0, (f.pointSizeF() or 9.0) * factor)))
        self.setFont(f)
        vh = self.verticalHeader()
        vh.setDefaultSectionSize(max(6, int(vh.defaultSectionSize() * factor)))

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            y = e.angleDelta().y()
            if y != 0:
                self._apply_zoom(1.1 if y > 0 else 0.9)
                e.accept()
                return
        super().wheelEvent(e)

    def keyPressEvent(self, e):
        if (e.modifiers() & Qt.KeyboardModifier.ControlModifier
                and e.key() == Qt.Key.Key_0 and self._zoom_base is not None):
            base_pt, base_row = self._zoom_base
            f = self.font()
            f.setPointSizeF(base_pt)
            self.setFont(f)
            self.verticalHeader().setDefaultSectionSize(base_row)
            self._zoom_base = None
            e.accept()
            return
        super().keyPressEvent(e)
```

要点：
- 行高走 `defaultSectionSize`（全仓表格均用 defaultSectionSize 紧凑行高，无 setRowHeight 覆盖——实现时抽查确认）
- 触控板小步长：`angleDelta().y() != 0` 即生效（高频小幅累计）
- Ctrl+0 仅在缩放过（`_zoom_base` 非 None）时恢复

## 2. 替换

35 处 `QTableWidget(` → `ZoomableTableWidget(`，每文件头部 `from gui_utils import ZoomableTableWidget`（原 QTableWidget import 保留——`setCellWidget` 等函数签名按 QTableWidget 只需子类可用，且文件仍可能在类型标注/helper 中使用父类名）。

替换文件：main_gui.py(17)、monitor/frame_monitor.py(2)、monitor/tcp_monitor.py(4)、monitor_widget.py(2)、diff_widget.py(2)、frame_gen_widget.py(3)、archive_widget.py(1)、llm_api_manager.py(1)、lookup_pages.py(1)、lookup_pages_simple.py(1)、test_plan_widget.py(1)。

注意各文件导入路径：monitor 子目录内 `from gui_utils import ...` 同根目录不变（Python 将脚本目录加入 sys.path）。

## 3. 验证

- offscreen：构造缩放表 → 注入 Ctrl+wheelEvent(QWheelEvent) → 断言字号/行高变化与钳制；Ctrl+0 恢复
- 全量 import：`python -c "import 各文件"`（qt 环境 offscreen）
- 回归：test_csg_hrf_mac / test_csg_new_gen / test_gw_ext_cmd

## 风险

- 有表格用 `setRowHeight` 逐行定高 → defaultSectionSize 不影响逐行高度（影响极小，抽查确认后如无则忽略）
- `QTableWidgetItem` 单独 setFont 的单元格随表字体走（无独立字体场景，抽查）
- wheelEvent 覆盖不影响 QScrollArea 内表格的滚动（无 Ctrl 时走 super）