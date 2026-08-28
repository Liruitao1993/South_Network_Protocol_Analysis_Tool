# 统一全应用按钮风格

## Goal

全应用 QPushButton 形状风格统一（圆角/高度/padding/字重），颜色按语义类区分，换主题（浅色/暗色/毛玻璃/Fusion）按钮跟随变化，所有按钮都有 hover/pressed/disabled 反馈。

## Requirements

- 圆角统一 4px（毛玻璃也从 6px 对齐到 4px）。
- 默认按钮 `padding:4px 12px`、bold、无边框；尺寸 sm(min-h22)/默认(min-h26)/lg(min-h30)。
- 语义类（动态属性 `btnKind`）：primary 蓝、success 绿、danger 红、warning 橙、accent 紫、secondary 灰底实心、ghost 透明图标按钮。
- 每个语义类在浅色/暗色/毛玻璃三套主题都有 normal/hover/pressed/disabled 四态。
- 行内 `setStyleSheet` 不再写圆角/padding/字号/背景，改用 `set_btn()` 设 `btnKind`。
- 图标按钮（刷新/★/×/?/最大化等）用 ghost：透明无边框，hover 淡底。
- 对话框标准按钮保持裸用，由基础 QPushButton 规则统一为 primary。

## Acceptance Criteria

- [ ] 单帧解析行、组帧、对比、TCP监控、监控器、测试方案、档案、拓扑等主要页面按钮圆角/高度统一。
- [ ] 有背景色的按钮 hover/pressed/disabled 均有反馈，无“死按钮”。
- [ ] 同排按钮高度一致。
- [ ] 切浅色/暗色/毛玻璃主题，按钮颜色与状态跟随。
- [ ] 语法检查通过，offscreen 启动主窗口无异常。
