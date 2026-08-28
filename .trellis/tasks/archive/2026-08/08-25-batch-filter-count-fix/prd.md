# 修复批量过滤计数控件缺失导致关闭崩溃

## Goal

修复关闭软件时控制台输出 `AttributeError: 'MainWindow' object has no attribute 'batch_filter_count'` 的问题。

## Root Cause

UI 构建时只创建了 `batch_selected_count`，漏掉了 `batch_filter_count`（QLabel），但槽函数 `_on_batch_filter_changed`（`main_gui.py:7359`/`7361`）直接调用 `self.batch_filter_count.setText(...)`。

关闭软件时 `batch_search_edit` 析构过程中触发 `textChanged`（清空内容），若 `batch_results` 非空，槽函数执行到计数更新处访问不存在的属性，抛 `AttributeError`。同样在有批量结果后输入关键词/切换状态过滤也会崩溃，关闭只是最常触发路径。`clear_batch` 中（6904 行）用 `hasattr` 守卫也反证该控件本应存在。

## Requirements

- 创建 `self.batch_filter_count` 并加入批量结果过滤栏，用于显示「显示 N / 总」。
- 槽函数无需再加 `hasattr` 守卫，控件生命周期内始终存在。

## Acceptance Criteria

- [x] 有批量解析结果时输入搜索关键词/切换状态过滤不再抛 AttributeError，计数正常显示。
- [x] 关闭软件不再输出该 traceback。
- [x] 过滤栏布局正常，计数 label 可见。

## Implementation

- 文件：`main_gui.py:1820` 附近
- 改动：在 `self.batch_selected_count` 之后补建
  ```python
  self.batch_filter_count = QLabel("")
  self.batch_filter_count.setFont(self._ui_font(-1))
  self.batch_filter_count.setStyleSheet("color: #757575;")
  filter_bar.addWidget(self.batch_filter_count)
  ```

## Notes

- 轻量任务 PRD-only。
