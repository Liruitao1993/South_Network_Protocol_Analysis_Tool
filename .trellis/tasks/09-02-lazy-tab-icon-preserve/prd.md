# 懒加载 Tab 替换后图标丢失修复

## 背景

主窗口部分 tab 用占位 widget 懒加载（协议组帧、档案管理、拓扑信息、TCP监控）。占位 tab 创建时带 Lucide 图标（`addTab(..., app_icons.load_icon(name), title)`）。首次点击该 tab 时 `_ensure_*_tab` 调 `_replace_lazy_tab`，内部 `removeTab(index)` 后 `insertTab(index, new_widget, title)` —— `insertTab` 未传图标，新 tab 图标为空。

现象（用户报告）：TCP监控 tab 启动时图标正常；点击进入后图标消失；切走再切回仍不显示。协议组帧/档案管理/拓扑信息三个懒加载 tab 同样受影响。

## 需求

1. `_replace_lazy_tab`（main_gui.py:2926）在 `removeTab` 前保存 `tabIcon(index)`，`insertTab` 时用带图标的重载 `insertTab(index, widget, icon, title)` 把图标带回。
2. tab 标题、当前选中行为、占位 widget 销毁逻辑保持不变。
3. 不影响非懒加载 tab（解析、查询、批量解析、预设命令、测试方案、报文对比、报文工具、虚拟表、监控器）。

## 验收标准

- 首次点击 TCP监控 tab 完成懒加载后，tab 图标仍显示（radar）。
- 切到其他 tab 再切回 TCP监控，图标保持。
- 协议组帧/档案管理/拓扑信息懒加载后图标同样保持。
- offscreen 冒烟：构造 QTabWidget 模拟 remove+insert 流程，断言替换前后 tabIcon 非空且缓存 key 一致。
