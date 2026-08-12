# 实施计划：校验结果展开/收缩 + 结果表全屏/恢复

## 执行清单（全部在 `main_gui.py`）

1. **通用辅助 `_make_fullscreen_controls(hide_widgets)`**：按钮对（全屏/恢复，状态互斥），返回右对齐按钮行
2. **校验结果展开/收缩**（`create_single_parse_tab` L976-983 重构）：
   - [ ] verify_head 行（展开/收缩按钮，默认展开态）
   - [ ] `verify_label` 移入 `QScrollArea`（NoFrame、widgetResizable）
   - [ ] `_on_verify_expand` / `_on_verify_collapse` 方法
3. **单帧解析表全屏/恢复**：导出按钮行追加 `_make_fullscreen_controls([input_group, verify_group])`
4. **批量摘要表全屏/恢复**：summary_layout 表格后追加 `_make_fullscreen_controls([result_splitter.widget(1)])`
5. **批量详情表全屏/恢复**：detail_layout 表格后追加 `_make_fullscreen_controls([result_splitter.widget(0), batch_detail_hex])`
6. **AGENTS.md 变更日志**（§10）

## 验证

```bash
cd E:/python/南网解析工具
python -c "import ast; ast.parse(open('main_gui.py',encoding='utf-8').read())"   # 语法
# offscreen 冒烟: 实例化 MainWindow, 校验按钮存在且点击切换状态不崩溃
QT_QPA_PLATFORM=offscreen python - <<'EOF'   # (经 eval 执行, 见实现后)
EOF
python test_csg_hrf_mac.py && python test_csg_new_gen.py  # 解析回归（确认 GUI 改动不碰解析逻辑）
```

offscreen 冒烟要点：
- `MainWindow()` 可实例化（可能触发配置加载；QT_QPA_PLATFORM=offscreen 下无显示）
- `w.verify_expand_btn` / `w.verify_collapse_btn` 存在；调用 `_on_verify_collapse()` 后 `verify_scroll.isHidden()` 为 True，`verify_expand_btn.isEnabled()` 为 True；`_on_verify_expand()` 还原
- 三个全屏按钮存在；`_make_fullscreen_controls` 返回行；点击逻辑由闭包驱动（offline 直接调即可跳过 Qt 事件）
- 若 MainWindow 实例化过重（串口/监控器副作用），改为仅验证 create_single_parse_tab 产物：临时子类只调该方法？—— MainWindow.__init__ 调用 _build_ui → create_single_parse_tab；直接尝试，失败再降级

## 审查门

实现 → 语法 + offscreen 冒烟 + 解析回归 → AGENTS.md → commit → /trellis:finish-work