# 实施计划：所有表格 Ctrl+滚轮缩放

## 执行清单

1. **`gui_utils.py`**：追加 `ZoomableTableWidget`（wheelEvent Ctrl 缩放 1.1/0.9、字号 5-24pt 钳制、行高同步、Ctrl+0 恢复基准）
2. **抽查**：确认无表用 `setRowHeight` 逐行定高 / QTableWidgetItem 独立 setFont
3. **替换 35 处** `QTableWidget(` → `ZoomableTableWidget(` + 各文件 import：
   - main_gui.py(17) / diff_widget.py(2) / frame_gen_widget.py(3) / archive_widget.py(1)
   - llm_api_manager.py(1) / lookup_pages.py(1) / lookup_pages_simple.py(1) / test_plan_widget.py(1)
   - monitor_widget.py(2) / monitor/frame_monitor.py(2) / monitor/tcp_monitor.py(4)
4. **AGENTS.md 变更日志**（§10）

## 验证

```bash
cd E:/python/南网解析工具
python -c "import ast; ..."                                         # 各文件语法
QT_QPA_PLATFORM=offscreen python - <<'EOF'                          # 缩放行为: 构造表, QWheelEvent(ctrl) 注入,
EOF                                                                 #   断言字号/行高变化+钳制+Ctrl+0恢复
python -c "import main_gui, diff_widget, monitor_widget, monitor.tcp_monitor, lookup_pages, ..."  # 全量导入
python test_csg_hrf_mac.py && python test_csg_new_gen.py && python test_gw_ext_cmd.py  # 回归
```

offscreen 缩放下注要点：构造 `QWheelEvent(pos, globalPos, angleDelta=QPoint(0,120), buttons, modifiers=ControlModifier)`，直接调 `table.wheelEvent(e)`。

## 审查门

实现 → 验证 → AGENTS.md → commit（排除 build/dist 与无关文件）