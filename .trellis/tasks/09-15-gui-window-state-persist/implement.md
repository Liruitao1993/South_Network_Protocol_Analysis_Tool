# 实施计划：窗口 / 分栏 / 列宽状态持久化

前置：`prd.md`（范围与验收）。命令在项目根执行；GUI 相关验证用 `QT_QPA_PLATFORM=offscreen`。

架构决策（本任务不单列 `design.md`，关键取舍写在此处）：

1. **复用 `config.json`**：写入 `_save_app_config`（`main_gui.py:10483`）已有的 `self._app_config`，新增 `ui.window` 段；**不引入 `QSettings`**（全仓库 0 处使用）。
2. **载入与套用分离**：`_load_app_config`（10405）只解析成 `self._window_state`（不碰 widget，此时 UI 还没建）；真正的 `restoreGeometry` / `restoreState` / 列宽套用放在 `__init__` **末尾**（`main_gui.py:1829 _restore_saved_protocol()` 之后、`_ui_ready = True` 前后均可，取 1830 之后）。
3. **列宽键 = 表属性名 + 列数**：存 `[{"name": "di_table", "count": 5, "sizes": [...]}, ...]`；恢复时列数不匹配即跳过（协议切换会重建查询表且列数不同）。
4. **查询页表重建后需二次套用**：`_update_protocol_lookup_tab`（3494）末尾追加一次 `_apply_saved_column_widths()`，否则切协议后宽度回到代码默认。
5. **几何可见性校验**：套用后若与任何 `QScreen.availableGeometry()` 都不相交，则丢弃保存值、走默认居中尺寸（防换显示器丢窗口）。

---

## 步骤 1 — 契约与工具方法（`main_gui.py`）

新增三个方法（放在 `_load_app_config` 附近）：

- `_collect_window_state() -> dict`：返回
  `{"geometry": <base64 str>, "splitter": <base64 str 或 [int,...]>, "columns": [{"name","count","sizes"}...]}`
  - 几何：`bytes(self.saveGeometry().toBase64()).decode("ascii")`
  - 分栏：优先 `result_splitter.saveState()`（QByteArray → base64）；保存时若不可用则退回 `sizes()` 列表
  - 列宽：遍历 `_WINDOW_STATE_TABLES`（见步骤 2 清单），每表取 `horizontalHeader().count()` 与 `[sectionSize(i) for i in range(count)]`
- `_apply_window_state()`：按第 2/4 条决策套用；全程 `try/except`，任何异常 → 静默回落默认。
- `_is_rect_visible(rect) -> bool`：与 `QApplication.screens()` 的 `availableGeometry()` 逐屏相交判断。
- `_reset_window_layout()`：清 `self._app_config["ui"]["window"]` → 立即写盘 → 套用默认（`resize(1000, 700)` 居中 + `result_splitter.setSizes([450, 550])` + 代码默认列宽）。

`_WINDOW_STATE_TABLES`（表清单，来自 prd R-Facts 的 10 张）：

```python
("result_table_widget", "batch_summary_table", "batch_detail_table",
 "di_table", "obis_table", "dlt645_di_table", "cmd_table",
 "gdw_table", "eb_di_table", "oad_table")
```

---

## 步骤 2 — 保存路径

1. `_load_app_config`（10405）：读 `self._app_config.get("ui", {}).get("window", {})` → `self._window_state`（类型/结构校验失败则置 `{}`）。
2. `closeEvent`（6530）**真实退出分支**：在 `self._is_closing = True`（6546）之前执行
   `self._app_config.setdefault("ui", {})["window"] = self._collect_window_state()` 并调用 `self._save_app_config()`；最小化到托盘分支（`event.ignore()`）**不保存**。
3. 自动更新重启路径（`_schedule_quit`）与托盘「退出」都走 `close()` → 同一处保存。

**验收**：手工改窗口/分栏/列宽 → 退出 → `config.json` 出现 `ui.window` 且值合理；托盘退出同样写入。

---

## 步骤 3 — 恢复路径

1. `__init__` 末尾（`_restore_saved_protocol()` 之后）调用 `self._apply_window_state()`。
2. `_update_protocol_lookup_tab`（3494）末尾调用 `self._apply_saved_column_widths()`（与步骤 1 的套用逻辑共用同一私有实现，避免两份口径）。

**验收**：重启后窗口位置/大小/分栏/主要列宽还原；12 个协议逐个切换不崩、宽度不乱套。

---

## 步骤 4 — 菜单入口

`配置(&C)` 菜单（5824-5832）追加一项「恢复默认窗口布局(&W)」→ `_reset_window_layout()`。

**验收**：点击后窗口回到默认尺寸/分栏/列宽，且 `config.json` 中 `ui.window` 被清空；再次启动仍是默认布局。

---

## 步骤 5 — 新增 `test/test_window_state.py`

文件头：docstring → `import _path_setup  # noqa: E402` → `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`。用 `app_paths.data_path` 沙箱（参考 `test/test_nanwang_custom_di.py` 的写法，指向临时目录，避免污染真实 `config.json`）。覆盖：

1. 往返：`_collect_window_state()` → 新实例 `_apply_window_state()` → 几何/分栏/列宽一致。
2. 坏值回落：`ui.window` 为 `{}` / 非法 base64 / 错误类型 → 不抛异常且用默认布局。
3. 屏幕外回落：构造一个远离所有屏幕的矩形 → `_is_rect_visible` 为 `False`，套用后被丢弃。
4. 列数不匹配：写入 `count` 与当前不符的条目 → 该表跳过，不报错。
5. 协议切换：逐个切 12 个协议，断言 `_update_protocol_lookup_tab` 后无异常、列数一致时宽度被套用。
6. 恢复默认：`_reset_window_layout()` 后 `config.json` 的 `ui.window` 键被清空。

登记进 `release_check.py:CORE_TESTS`。

---

## 步骤 6 — 文档与门槛

1. `main_gui.py:CHANGELOG` 增条目。
2. `AGENTS.md` §3 数据文件表补一句 `config.json` 现含 `ui.window`（窗口/分栏/列宽），§8 陷阱补「窗口状态持久化走 `_save_app_config`，不要在 closeEvent 里另写一份 JSON」。
3. 门槛：

```bash
python release_check.py
python test/test_window_state.py
python test/test_theme_settings.py
python test/test_app_exit.py
```

---

## 完成定义（DoD）

- [ ] 窗口大小/位置、`result_splitter` 比例、10 张表的列宽，退出后重启全部还原。
- [ ] 删除或损坏 `ui.window` → 启动不报错，用默认布局，且此后能正常保存。
- [ ] 保存的几何落在当前屏幕外时，启动窗口仍完整可见。
- [ ] 协议切换（12 个）不崩、不套用错误宽度。
- [ ] 托盘退出与菜单退出两条路径都会保存。
- [ ] `test_window_state.py` 全过，`test_theme_settings.py` / `test_app_exit.py` 不回归，`python release_check.py` 无 FAIL/WARN。
- [ ] CHANGELOG + AGENTS.md 已同步。
