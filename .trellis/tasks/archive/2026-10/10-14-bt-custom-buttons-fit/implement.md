# 执行计划（修复 1.23.82 的两个缺陷）

## 1. `bluetooth_core.py`

- [ ] `CUSTOM_ROWS_MAX = 3` → `CUSTOM_MIN_ROWS = 1`（注释写清「滚动区最少可见行数；封顶概念已取消」）。
- [ ] `test_bluetooth_core.py` [13] 同步常量断言（`CUSTOM_MIN_ROWS == 1`；不再引用 `CUSTOM_ROWS_MAX`）。

## 2. `bluetooth_tool_widget.py`

- [ ] `_custom_scroll_cap()` → `_custom_scroll_limits() -> (min_h, max_h)`：
      min = 1 行按钮高（无按钮时按字体兜底），max = `custom_host.sizeHint().height()`（≥ min）。
- [ ] `_apply_custom_scroll_cap()` → `_apply_custom_scroll_limits()`：`setMinimumHeight` + `setMaximumHeight`。
      调用点不变（`_rebuild_custom_buttons()` 尾部、`restyle_for_theme()`）。
- [ ] `_build_custom_group()`：返回容器 `[CollapsibleSection(滚动区), 工具栏行]`；
      `self.custom_group` 仍是 `CollapsibleSection`（key/标题/折叠 API 不变）；
      工具栏 5 个按钮 + 提示移到容器（section 之外）。
- [ ] 折叠行为：收起只隐藏 `custom_group.content`（按钮网格），工具栏仍在。

## 3. 测试（`test_bluetooth_widget.py` [14] 重写）

- [ ] **D1 判据**：10 个按钮 + `right_splitter.setSizes([200, 600])` + `settle()` →
      `verticalScrollBar().maximum() == 0` 且滚动区高度 ≥ 内容高度 − 2。
- [ ] **反向判据**：64 个按钮 + 同样空间 → `maximum() > 0`（内容 700px > 600px，空间真不够）。
- [ ] **日志不被挤**：默认分栏 + 64 个按钮 → 日志组高度 ≥ 120。
- [ ] 上下限：`scroll.minimumHeight()` ≈ 1 行；`scroll.maximumHeight()` ≈ 内容高度（< 3 行时也按内容）。
- [ ] **D2 判据**：`set_expanded(False)` → `is_content_hidden()` 为真 **且** `btn_custom_add.isVisible()` 为真；
      并且 `btn_custom_add` 不是 `custom_group.content` 的后代（工具栏确实在折叠区外）。
- [ ] 保留：按钮少不滚动、收起高度骤减、`custom_collapsed`/`right_split` 采集与重启恢复。
- [ ] 反例自检：10 个按钮的内容高度 > 3 行（说明旧的 3 行封顶必然造成滚动 ⇒ 新判据非恒真）。

## 4. 验证门禁

```bash
python test/test_bluetooth_core.py
python test/test_bluetooth_widget.py
python test/test_bluetooth_addr_fix.py
python test/test_bluetooth_worker.py
python test/test_bluetooth_tab_wiring.py
python test/test_collapsible_section.py
PYTHONIOENCODING=utf-8 python release_check.py --with-gui     # 目标 FAIL=0（既有环境红除外）
```

- [ ] 变异反证（逐条干净变红后逐字节还原 + md5 一致）：
  1. 上限改回固定 3 行封顶 → 「10 个按钮 + 给足空间无滚动条」红；
  2. 工具栏放回折叠内容里 → 「折叠后编辑按钮仍可见」红；
  3. 去掉 `setMinimumHeight`（下限为 0）→ 「下限 ≈ 1 行」红；
  4. 不采集分栏尺寸 → 「分栏尺寸被写进设置」红。
- [ ] 冒烟：offscreen 1200×800，两种情况各量一次（`[420,240]` 默认 / `[200,600]` 拖大）：
      10 个与 64 个按钮的滚动条范围、滚动区高度、日志高度、折叠后工具栏可见性。
- [ ] 文档：`main_gui.py` CHANGELOG（1.23.82 条目改为最终行为，含「按内容自动 + 工具栏常驻」）、
      `README.md`、`AGENTS.md` §8 陷阱 69、spec §7g 同步（均留工作区随发版批次）。
