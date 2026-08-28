# 设计：统一全应用按钮风格

## 现状（调查结论）

- 圆角混用 2/3/4/6px（GLASS 还是 6px），高度 24/26/28/32，padding 从 `1px 4px` 到 `6px 20px` 不一。
- 同排按钮圆角/高度不同（单帧解析行 parse/verify 等 3px 高 32，旁边 serial 高 28）。
- 绿色三套（`#4CAF50` / hover `#43A047` / `#45a049`），次要按钮两种语言（白底灰边 vs 裸用继承蓝）。
- 大量行内 `setStyleSheet` 只设背景色、不写 hover/pressed/disabled——而 Qt 一旦控件有自己的 stylesheet，应用级 QSS 的 `:hover/:pressed/:disabled` 对它失效，导致这些按钮无悬停反馈。
- 约 20+ 按钮裸用，在有主题时继承蓝色，在 Fusion/原生时变系统灰。

## 目标

- **形状统一**：圆角、高度、padding、字重全局一致，换主题自动跟随。
- **颜色语义化**：用 `btnKind` 动态属性区分 primary/success/danger/warning/accent/secondary，颜色随主题变。
- **状态完整**：每个语义类在每个主题都有 normal/hover/pressed/disabled。
- 行内不再写圆角/高度/padding/字号，只标 `btnKind`；图标/迷你按钮用单独 `btnSize` 属性。

## 统一规范

### 普通按钮
- `border-radius: 4px`（GLASS 也统一 4，不再 6）
- `padding: 4px 12px`（对话框主按钮 `6px 20px`、`min-width:80px` 由 `QMessageBox QPushButton`/`[btnSize="lg"]` 承担）
- `border: none`
- `font-weight: bold`
- `min-height: 26px`（默认；`btnSize="lg"`→30，`btnSize="sm"`→24）

### 语义类（dynamic property `btnKind`）
| kind | 用途 | LIGHT normal | DARK normal | GLASS normal |
|---|---|---|---|---|
| primary（默认） | 主操作 | #2196F3 | #42a5f5 | rgba(59,130,246,215) |
| success | 解析/连接/生成/确定 | #4CAF50 | #4CAF50 | rgba(76,175,80,215) |
| danger | 停止/删除/断开 | #f44336 | #ef5350 | rgba(239,68,68,220) |
| warning | CRC24/帮助/警告类 | #FF9800 | #ffa726 | rgba(245,158,11,220) |
| accent | CRC32/加入测试方案 | #9C27B0 | #ab47bc | rgba(147,51,234,215) |
| secondary | 清空/取消/导出等次要 | #6b7280 描边风 | #4b5563 | rgba(100,116,139,200) |

每个类配 normal/hover/pressed/disabled 四态，颜色在三个主题 QSS 里分别定义。

### 尺寸（dynamic property `btnSize`）
- 默认 min-height 26 / padding 4px 12px
- `lg`：min-height 30 / padding 5px 16px
- `sm`：min-height 22 / padding 1px 8px（迷你 +/-/发送，圆角仍 4，font 继承不单独缩，不再 11px 特例）

## 技术方案

### 1. gui_utils 加辅助
```python
def set_btn(btn, kind="primary", size=None):
    btn.setProperty("btnKind", kind)
    if size: btn.setProperty("btnSize", size)
    # 触发 QSS 重算
    btn.style().unpolish(btn); btn.style().polish(btn)
```

### 2. theme_settings 三个主题 QSS 加规则
新增统一块（追加到 LIGHT_QSS / DARK_QSS / GLASS_QSS，用 `[btnKind="..."]` 选择器），并把 GLASS 的 `QPushButton` 圆角 6 改 4。裸 `QPushButton`（无 btnKind）保持 primary 外观，保证未改到的裸按钮也是统一风格。

### 3. 逐文件替换行内样式
把 `setStyleSheet("background:#4CAF50; ...; border-radius:3px; ...")` 之类：
- 删除形状/圆角/padding/字号声明
- 改调 `set_btn(btn, "success")` / 对应 kind
- 已有的彩色功能按钮映射：解析→primary、校验→primary、添加测试方案→accent、清空→secondary、填充CRC24→warning、填充CRC32→accent、打开串口/生成→success、停止/删除→danger。
- 对话框 ok/cancel 保持裸用（QMessageBox/标准 QDialog 按钮），由基础 QPushButton 规则统一。
- diff_widget 白底描边次要按钮→secondary。
- 图标按钮（serial_refresh、★/×/?、最大化）保留透明/无边框，标 `btnKind="ghost"`（QSS 定义透明无边框，hover 淡底）。

### 4. 不动
- 彩色语义本身保留（用户接受不同颜色，只要风格统一）。
- 输入框/表格/标签等非按钮控件不动。
- 非按钮的 QLabel 可点击“链接”样式（更新提示）不动。

## 影响文件
theme_settings.py、gui_utils.py、main_gui.py、frame_gen_widget.py、diff_widget.py、monitor/tcp_monitor.py、monitor/frame_monitor.py、preset_buttons.py、test_plan_widget.py、monitor_widget.py、archive_widget.py、topology_widget.py、llm_preprocess_widget.py、llm_api_manager.py、lookup_pages.py、system_integration/system_settings.py、message_tool_widget.py。

## 验收
- [ ] 三个主题下，所有按钮圆角一致 4px、高度/padding 按 size 统一。
- [ ] 每个有背景色的按钮 hover/pressed/disabled 都有反馈。
- [ ] 同排按钮高度/圆角一致。
- [ ] 切换主题（含毛玻璃）按钮颜色与状态随主题变化。
- [ ] 语法/启动无异常，主要页面（单帧/组帧/对比/TCP监控/测试方案/档案/拓扑）按钮可见可点。
