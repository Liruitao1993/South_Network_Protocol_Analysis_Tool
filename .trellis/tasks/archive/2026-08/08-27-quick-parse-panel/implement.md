# 实现计划：uTools 风格快捷解析小窗

## 实现顺序

1. **新建 `system_integration/quick_parse_panel.py`**
   - `QuickParsePanel(QWidget)`：窗口标志 `Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint`；`WA_TranslucentBackground`
   - 圆角容器 QFrame（QSS radius 12px）+ `QGraphicsDropShadowEffect`
   - 布局：徽章行（协议 QComboBox 12 项 / 帧长 QLabel / 校验徽章 QLabel）→ 输入 QTextEdit（Consolas、NoWrap、max 64px、placeholder）→ 结果 QScrollArea + ZoomableTableWidget（4 列、13px 行、隐藏垂直头、交替行色、只读）→ 底部行（完整视图按钮 / 复制结果按钮 / 提示文字）
   - 构造参数：`clean_fn / parse_fn / validate_fn / open_full_fn / is_dark_fn`
   - `toggle_panel()`：可见→hide；不可见→`_reposition()` + `_restyle()` + 剪贴板预填 + show/raise/activate
   - `_reposition()`：光标所在屏 `availableGeometry`，水平居中、顶部 12%
   - `keyPressEvent`：Esc → hide
   - `changeEvent`：`ActivationChange` 且 `not isActiveWindow()` → hide
   - 剪贴板预填：`QGuiApplication.clipboard().text()` → clean_fn → 合法（≥4 字节偶数 hex）填入并 selectAll，否则清空
   - `textChanged` → 300ms 防抖定时器 → `_do_parse()`
   - `_do_parse()`：清洗 → detect_protocol（静默 setCurrentIndex）→ parse_fn → 填表/错误态/空态 → validate_fn → 徽章；帧长显示
   - 协议下拉 `currentIndexChanged`（用户手动）→ `_do_parse()` 重解析
   - 「完整视图」：open_full_fn(bytes, idx) 后 hide 自身
   - 「复制结果」：复用表格文本复制（直接拼 TSV 到剪贴板）
   - `_restyle()`：按 is_dark_fn 刷新容器/徽章/输入框配色
   - 协议列表由 MainWindow 注入（`protocol_items: list[(text, idx)]`），面板不硬编码协议名

2. **`main_gui.py` 接线**
   - import QuickParsePanel
   - `_on_global_hotkey` 改为：懒创建 `self._quick_panel`（不存在则实例化并注入回调）→ `toggle_panel()`
   - 新增 `_quick_panel_parse(frame_bytes, idx)`：9/10 ED 剥离 + `parse_level="auto"`（复用 `_parse_ed_monitor_header`，失败返回 err 文案）；`_get_current_parser(idx, **kwargs).parse_to_table(bytes)` → `(rows, None, None)` / `(None, str(e), None)`
   - 新增 `_quick_panel_validate(frame_bytes, idx)`：懒加载 validator dict（映射同 `_run_validation` L4316-4335）→ `verify()` → `(valid, summary)`；无 validator → `(None, "")`
   - 新增 `_quick_panel_open_full(frame_bytes, idx)`：`self._parse_and_show_dialog(frame_bytes, idx)`
   - 注入协议列表：`[(self.protocol_combo.itemText(i), i) for i in range(...)]`

3. **设置文案**：`system_integration/system_settings.py` L116 hint 更新为热键唤出小窗描述

4. **打包**：`南网协议解析工具.spec` hiddenimports 加 `system_integration.quick_parse_panel`

5. **测试** `test/test_quick_parse_panel.py`（offscreen）：
   - 面板实例化（注入 fake 回调）+ 初始空态
   - setText 合法帧（用真实南网帧，如 NW_command.json 首条或硬编码 68..16）→ 手动触发 `_do_parse()`（测试中直接调，不等防抖）→ 表格行数 >0、帧长标签正确、协议下拉非空
   - detect_protocol：68..16 帧 → 协议 0/6 自动选中
   - 非法 hex（"xyz"）→ 错误态显示、无异常
   - 校验徽章：valid 帧 → 绿色「通过」
   - Esc → isVisible False；toggle_panel 显隐切换
   - 协议手动切换 → parse_fn 收到新 idx
   - 完整视图按钮 → open_full_fn 被调用且面板隐藏
   - MainWindow 集成：`_on_global_hotkey` 调用后面板可见且剪贴板内容被填入（用 QApplication.clipboard().setText 设置）

6. **版本/文档**：版本 bump 1.16.1 → **1.17.0**（新功能）；CHANGELOG（main_gui）+ AGENTS.md §10 条目；AGENTS.md §3 架构图 system_integration 列表补 quick_parse_panel

## 验证命令

```bash
python -m py_compile system_integration/quick_parse_panel.py main_gui.py system_integration/system_settings.py
python test/test_quick_parse_panel.py
QT_QPA_PLATFORM=offscreen python -c "..."  # MainWindow 热键集成冒烟（热键唤出/剪贴板预填/真实帧解析）
```

## 风险点

- WA_TranslucentBackground + FramelessWindow 在 offscreen 下 grab 渲染中文字体缺失（已知），以控件状态/几何断言为准，视觉由用户实机确认
- Qt.Tool 窗口的 ActivationChange 在父窗口点击时触发——属预期（点外部关闭）
- validator dict 懒加载避免启动开销；解析器/校验器均无状态可复用单例
