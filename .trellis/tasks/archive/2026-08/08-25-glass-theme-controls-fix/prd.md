# 毛玻璃主题下按钮/表格等控件未跟随玻璃样式

## Goal

启用毛玻璃主题后，大片控件（解析结果表格、输入框、部分按钮区域）显示为不透明死白/实色，亚克力模糊透不过来，看起来主题「没生效」。要求毛玻璃主题下各控件正确呈现半透明磨砂质感，玻璃背景能透出。

## Root Cause

1. **主因（多层背景叠加）**：`theme_settings.GLASS_QSS` 有通配规则
   `QWidget { background-color: rgba(255,255,255,150) }`。
   这让控件树里**每一个** QWidget（QTableWidget 内部 viewport / QScrollArea viewport / corner button / 嵌套布局容器 / QTabWidget 内部栈）都各画一层半透明白。父子多层嵌套时，半透明白层层叠加累积成接近不透明的死白，亚克力背景被彻底盖住。表格和多行输入框内部子控件最多，因此最明显。
2. 次要：少数控件的内部子部件（表格 corner button、QAbstractScrollArea viewport、splitter 手柄）没有显式透明规则，沿用了上面的通配白底。
3. 彩色功能按钮（解析/校验/添加/CRC 等）的硬编码 `setStyleSheet` 是**有意的语义强调色**，不应改；本次只确保它们在玻璃背景上对比度足够，不做半透明化。

## Requirements

- 毛玻璃主题下，普通容器/子控件默认透明，玻璃底色只由 QMainWindow / QDialog / QGroupBox / 输入控件 / 表格等「表面」控件承担，不出现多层叠加致死白。
- 解析结果表格、QTextEdit/QPlainTextEdit、QLineEdit、QSpinBox 背景半透明且可读，能透出玻璃。
- 表格 viewport、corner button、QScrollArea 视口、QSplitter 子件透明，不额外堆白底。
- 非毛玻璃主题（default/dark/fusion/vista）行为不变。
- 不破坏彩色功能按钮的语义色与可读性。

## Non-Goals

- 不全改 182 处控件级 `setStyleSheet`（大量是有意强调色/状态色）。
- 不改非 Windows 平台的退化外观。
- 不改亚克力模糊的开启逻辑本身。

## Acceptance Criteria

- [ ] 毛玻璃主题下，解析结果表格区域呈现半透明磨砂，不再是整块死白。
- [ ] 输入框/多行编辑框背景半透明、文字清晰可读。
- [ ] default/dark/fusion 主题回归无样式回归。
- [ ] 语法检查通过、offscreen 启动并切换玻璃主题无异常。
