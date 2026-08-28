# 快捷解析小窗：输入框与结果拆为两张独立卡片

## Goal

快捷解析小窗（`system_integration/quick_parse_panel.py`）当前整窗是一张大卡片，徽章行/输入框/状态提示/结果表格/底部按钮挤在同一张卡内。按用户反馈与 uTools 视觉惯例，拆为**两张独立卡片**：输入卡（徽章+输入）在上方常驻，结果卡（提示+表格+按钮）在下方实时浮出，视觉上互为独立圆角卡片。

## Background (confirmed facts)

- 现结构：单 `self.card`（#qpCard）承载 header + input + status_label + table + footer；空态靠逐控件 setVisible 收缩。
- 设计已确认（方案 A）：输入卡 = 徽章行（协议下拉+帧长+校验徽章）+ 输入框；结果卡 = status_label + 结果表格 + 底部按钮行。两卡间距 ~8px。
- QSizeGrip 从旧大卡移挂到最外层 window 右下角（落在 margin 空白处，不遮挡内容，两态均可用）。
- 主题 `_restyle` 需同时作用于两张卡并各自持有投影 effect。

## Requirements

1. `QuickParsePanel._build_ui` 拆为 `input_card` / `result_card` 两个 QFrame，同款圆角+边框+独立投影，objectName 分别设置，`_restyle` 双卡同步明暗主题配色。
2. 形态切换：
   - 空态 → 仅输入卡可见（不含徽章行），`result_card` 整体隐藏；
   - 展开/错误态 → 输入卡含徽章行，结果卡显示状态提示或表格 + 底部行；
   - 复制成功提示仍在结果卡内浮现。
3. 行为不变：拖动空白/卡间隙移动、右下角调整大小、Esc/失焦隐藏、防抖实时解析、协议自动识别、校验徽章、「复制结果」「在主窗口打开完整视图」。
4. `_fit_height` 高度自适应对两张卡的布局均强制重算。

## Acceptance Criteria

- [x] 展开态视觉上为上下两张独立圆角卡片（各自边框/投影），间隙空白可拖动窗口（offscreen 截图核验）
- [x] 空态只剩一张输入卡，无结果卡残影
- [x] 错误态：⚠ 提示出现在结果卡内，结果卡弹出
- [x] 缩放柄位于面板右下角 margin 区，空态与展开态均可拖拽调整大小
- [x] 明暗主题切换后两卡配色同步
- [x] `test/test_quick_parse_panel.py` 适配双卡引用后全部通过（45 项断言，offscreen；退出码 0xC0000409 为本机 MainWindow 关闭期既有 fastfail，与改动无关）
- [x] 不引入对 parser 的依赖（哑组件约束保持）

## Out of Scope

- 主窗口其他标签页、解析弹窗、quick-parse-panel 功能逻辑改动
- 三卡拆分等进一步视觉细分
