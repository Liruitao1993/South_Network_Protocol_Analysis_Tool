# 执行记录：毛玻璃主题控件不跟随

## 根因

`theme_settings.GLASS_QSS` 有通配规则：

```css
QWidget { background-color: rgba(255,255,255,150); }
```

这让控件树中**每个** QWidget（QTableWidget 内部 viewport、QScrollArea viewport、corner button、嵌套布局容器、QStackedWidget 页等）都各画一层半透明白。父子多层嵌套时，半透明白**层层叠加**，累积成接近死白的不透明层，把 Windows 亚克力模糊完全盖住。表格/多行输入框内部子部件最多，死白最明显。

## 改动

文件：`theme_settings.py`，仅改 `GLASS_QSS`（其它主题 QSS 不动）。

1. 基础 `QWidget` 背景由 `rgba(255,255,255,150)` 改为 `transparent`，并加注释说明为何不能给基础 QWidget 上白底。玻璃表面只由以下控件显式承担（原有规则，未改）：
   - `QMainWindow` 玻璃着色、`QDialog`/`QMessageBox` 近不透明面板
   - `QGroupBox` 半透明白面板（单层）
   - `QLineEdit`/`QTextEdit`/`QPlainTextEdit`/`QSpinBox` 半透明白输入面
   - `QTableWidget`/`QHeaderView::section` 半透明表格面
2. 新增容器透明规则（单类选择器，避免覆盖子控件）：
   ```css
   QStackedWidget, QScrollArea, QSplitter, QSplitterHandle { background-color: transparent; }
   QTableCornerButton::section { background-color: transparent; border: none; }
   ```
   消除 Fusion 风格给这些容器/角按钮上的实底色。
3. 特意**不**用 `QTabWidget QWidget` 之类后代选择器——其特异性 (0,0,2) 高于 `QPushButton` (0,0,1)，会把 tab 页内按钮/输入框也变透明，误伤。

## 不改的部分

- 182 处控件级 `setStyleSheet` 中的彩色功能按钮（解析/校验/添加/CRC 等）是有意的语义强调色，保持不透明以保证对比度与可读性。
- 非毛玻璃主题（default/dark/fusion/vista）的 QSS 完全未动。
- 亚克力开启逻辑（`_set_windows_acrylic` / `_apply_glass_blur`）未动。

## 验证

- `theme_settings.py` 语法检查通过。
- offscreen 以 `glass` 主题启动主窗口正常，QSS 长度 10249，无异常；`result_table_widget.viewport().autoFillBackground()` 为 False（不再强制实底）。
- 真实亚克力磨砂效果需在 Windows 10/11 真机肉眼确认（offscreen 无桌面合成，看不到模糊）。

## 待真机确认

- 启用毛玻璃后，解析结果表格/输入框/各容器是否透出磨砂玻璃，不再整块死白。
- default/dark/fusion 主题回归无样式变化。
- 若仍有个别死白块，多半是某控件用 `setStyleSheet` 设了实色背景（如第三方/子页面容器），按需单独改其颜色为 rgba 或 transparent。
