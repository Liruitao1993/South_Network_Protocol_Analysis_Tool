# Implement：Reflex 报文工具移植

## 步骤

1. **阅读现有代码**
   - [ ] 读 `reflex_web/reflex_web/web_utils.py` 607-839，确认已有工具函数签名。
   - [ ] 读 `reflex_web/reflex_web/reflex_web.py` 顶部 State 定义与 `index()` 导航区。
   - [ ] 读 `message_tool_widget.py` 相关转换逻辑，确保语义一致。

2. **补齐后端函数**
   - [ ] 在 `web_utils.py` 新增 `tool_hex_to_decimal(text, little_endian=True)`。
   - [ ] 确保 `_parse_hex` 可被复用。

3. **实现 Reflex 状态**
   - [ ] 在 `State` 新增字段：`tool_input`、`tool_output`、`tool_hex_mode`、`tool_endian`。
   - [ ] 新增 setter：`set_tool_input`、`set_tool_hex_mode`、`set_tool_endian`。
   - [ ] 新增 `run_tool(op: str)`：根据 `op` 映射调用 web_utils 函数。
   - [ ] 新增 `clear_tool()`、`copy_tool_output()`。

4. **实现 UI 组件**
   - [ ] 新增 `message_tool_tab() -> rx.Component`。
   - [ ] 输入区：textarea + 16进制复选框 + 清空按钮。
   - [ ] 基础按钮网格（18 个按钮）。
   - [ ] 扩展工具区：bitstring、CRC、字节规整、十进制转换。
   - [ ] 输出区：只读 textarea + 复制按钮。

5. **集成导航**
   - [ ] 在 `index()` tab 按钮行增加“报文工具”按钮。
   - [ ] 在 `rx.cond` 链中增加 `active_tab == "tool"` 分支。

6. **本地验证**
   - [ ] 运行 `python reflex_web/run_app.py`。
   - [ ] 访问页面，测试按钮输出。
   - [ ] 与 GUI 输出对比关键转换。

## 变更文件

- `reflex_web/reflex_web/web_utils.py`
- `reflex_web/reflex_web/reflex_web.py`

## 回滚

撤销两个文件的修改即可。
