# 执行计划

## 0. 引用点盘点（先做）

- [ ] `grep -n "custom_group\|custom_grid\|custom_host" bluetooth_tool_widget.py test/*.py`：改名/改容器前确认
      所有引用点（含测试），需要时保留属性别名以免破坏既有断言。
- [ ] `grep -n "QSplitter" bluetooth_tool_widget.py`：确认本页没用过竖向分栏（避免与既有布局冲突）。

## 1. `bluetooth_core.py`

- [ ] 新增常量：`CUSTOM_ROWS_MAX = 3`、`RIGHT_SPLIT_DEFAULT = (420, 240)`、
      `RIGHT_SPLIT_RANGE = (60, 4000)`。
- [ ] 新增 `normalize_right_split(raw) -> list[int]`（长度/类型/越界宽容，回落默认）。
- [ ] `merge_settings`：写入 `custom_collapsed`（bool）与 `right_split`（normalize）。
- [ ] `DEFAULTS`/文档串同步（若有集中声明默认值的地方）。

## 2. `bluetooth_tool_widget.py`

- [ ] `_build_right_panel()`：改为竖向 `QSplitter`（日志 / 下半区），`setChildrenCollapsible(False)`，
      `splitterMoved → _schedule_save`。
- [ ] `_build_custom_group()`：返回 `CollapsibleSection`（key=`custom_buttons`）；内容区 = `QScrollArea`
      （包 `custom_host`）+ 工具栏行；`toggled → 记录 custom_collapsed`。
- [ ] `_custom_scroll_cap()`：按真实按钮 `sizeHint().height()`（无按钮时字体高度）算 3 行高度；
      `_rebuild_custom_buttons()` 与 `restyle_for_theme()` 都调用它。
- [ ] `_rebuild_custom_buttons()`：标题改 `custom_section.set_title(f"自定义报文（{n}）")`；
      按钮少时确保没有滚动条（`setMaximumHeight` + 内容高度自适应）。
- [ ] `_collect_settings()` / `_apply_settings_to_ui()`：采集与套用 `custom_collapsed` / `right_split`。
- [ ] `restyle_for_theme()`：重算封顶（字号可能变）。

## 3. 测试

- [ ] `test_bluetooth_core.py`：`normalize_right_split` / `merge_settings` 新键（缺省、坏类型、越界、长度不对）。
- [ ] `test_bluetooth_widget.py` 新增节（插在 `test_button_address` 之后，反例自检顺延）：
  - 结构：自定义区在 `QScrollArea` 内、`maximumHeight ≤ 3 行`、竖向 `QSplitter` 存在；
  - 40 个按钮 + `resize/show`：日志高度 ≥ 其最小高度、自定义区 ≤ 封顶、内容高度 > 封顶（判据非恒真）；
  - 收起/展开：`is_content_hidden()`、区高度骤减、`settings["custom_collapsed"]` 被写入；
  - 分栏：`setSizes` 后 `settings["right_split"]` 记录；
  - 重启恢复（同配置路径新建页面）。
- [ ] 既有 5 份蓝牙测试回归。

## 4. 验证门禁

```bash
python test/test_bluetooth_core.py
python test/test_bluetooth_widget.py
python test/test_bluetooth_worker.py
python test/test_bluetooth_tab_wiring.py
python test/test_bluetooth_addr_fix.py
python test/test_collapsible_section.py
PYTHONIOENCODING=utf-8 python release_check.py --with-gui     # 目标 FAIL=0（既有环境红除外）
```

- [ ] 变异反证（每条干净变红后逐字节还原 + md5 一致）：
  1. 去掉封顶（`maximumHeight` 不设）→ 「自定义区 ≤ 封顶 / 日志不被挤没」红；
  2. 收起时不隐藏内容（`set_expanded_quiet` 无效化）→ 「收起高度骤减」红；
  3. `right_split` 不采集 → 「分栏尺寸被记录」红；
  4. 载入时不套用折叠态 → 「重启恢复」红。
- [ ] 冒烟：offscreen 建页面 + 加 40 个按钮 + `show()`，打印日志组高度 / 自定义区高度 / 是否出现滚动条 /
      收起后高度，人工核对「日志不再被挤没」。
- [ ] `CHANGELOG` / `AGENTS.md`（陷阱 69 / §3）/ `README.md` 更新（留工作区，随发版批次）；
      `.trellis/spec/frontend/component-guidelines.md` 补 §7g 契约。

## 回滚点

- 两个文件独立可还原；配置向后兼容（缺键 = 旧观感 + 分栏默认值）。
- 若 `custom_group` 属性被外部引用：保留 `self.custom_group = self.custom_section` 别名并注释原因。
