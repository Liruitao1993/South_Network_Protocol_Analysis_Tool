# PRD：Reflex 报文工具移植

## 背景

GUI 版本 `message_tool_widget.py` 提供了“报文工具”标签页，用于对原始 hex/ASCII 字符串做常见转换与校验计算。Reflex Web 版本目前缺少该功能，但后端转换函数已在 `reflex_web/reflex_web/web_utils.py` 中实现大部分，只需补齐 UI 与导航。

## 目标

在 Reflex Web 版本中新增“报文工具”标签页，功能与 GUI 版本完全一致，所有转换通过 Web 后端函数完成。

## 范围

- 在 `reflex_web/reflex_web/reflex_web.py` 增加报文工具标签页 UI。
- 复用 `reflex_web/reflex_web/web_utils.py` 中的转换函数。
- 补齐目前缺失的 `HEX→十进制` 大小端转换函数。
- 在主导航中加入“报文工具”入口。
- 不改动 GUI 版本。

## 功能清单（与 GUI 对齐）

输入区：
- 多行文本输入框
- “16进制模式”复选框
- 清空、复制输出按钮

工具按钮（按 GUI 原布局）：
- 字节反转
- +0x33
- 反转+0x33
- ASCII→HEX
- 字节长度
- 大写
- 移除空格
- msg→Pn
- Pn→msg
- 校验和
- −0x33
- 反转−0x33
- HEX→ASCII
- 字符数
- 小写
- 添加空格
- msg→Fn
- Fn→msg

扩展工具：
- HEX→bitstring
- bitstring→HEX
- 字节规整
- CRC-16（698.45）
- CRC-32
- CRC-24
- 大小端选择 + HEX→十进制

输出区：
- 只读多行文本输出框

## 验收标准

1. Reflex 应用启动后，主导航出现“报文工具”入口。
2. 点击入口后显示报文工具页面，布局与 GUI 基本一致。
3. 所有转换按钮均可点击并返回正确结果。
4. 16进制模式影响输入解析方式（与 GUI 一致）。
5. HEX→十进制支持大端/小端选择。
6. 输出可复制。
7. 不影响现有其他标签页功能。

## 非目标

- 不移植 GUI 的 QShortcut、主题样式等桌面端特性。
- 不修改 `message_tool_widget.py`。
