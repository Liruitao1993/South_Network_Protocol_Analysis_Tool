# Design：Reflex 报文工具移植

## 架构

Reflex 应用采用单一 `State` 管理所有页面状态。报文工具作为新 tab 加入，复用现有 `web_utils.py` 中的后端函数。

```
┌─────────────────────────────────────┐
│  reflex_web/reflex_web/reflex_web.py │
│  - State.tool_input                 │
│  - State.tool_output                │
│  - State.tool_hex_mode              │
│  - State.tool_endian                │
│  - message_tool_tab()               │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  reflex_web/reflex_web/web_utils.py │
│  - tool_byte_reverse                │
│  - tool_hex_add_33 / sub_33         │
│  - tool_reverse_add_33 / sub_33     │
│  - tool_hex_to_ascii / ascii_to_hex │
│  - tool_byte_length / char_count    │
│  - tool_to_upper / to_lower         │
│  - tool_remove_spaces / add_spaces  │
│  - tool_msg_to_pn / pn_to_msg       │
│  - tool_msg_to_fn / fn_to_msg       │
│  - tool_checksum8                   │
│  - tool_hex_to_bitstring / bitstring_to_hex
│  - tool_byte_normal                 │
│  - tool_crc16_698 / crc32 / crc24   │
│  - tool_hex_to_decimal（新增）        │
└─────────────────────────────────────┘
```

## 状态设计

在 `State` 中新增：

```python
tool_input: str = ""
tool_output: str = ""
tool_hex_mode: bool = True
tool_endian: str = "little"  # "little" | "big"
```

事件处理器：
- `set_tool_input(value: str)` — 绑定输入框
- `set_tool_hex_mode(value: bool)` — 绑定复选框
- `set_tool_endian(value: str)` — 绑定下拉
- `run_tool(op: str)` — 根据操作名调用 web_utils 函数，结果写入 `tool_output`
- `clear_tool()` — 清空输入输出
- `copy_tool_output()` — 将输出写入剪贴板（Reflex `rx.set_clipboard`）

## UI 设计

页面结构：
1. 标题：`rx.heading("报文工具", size="7")`
2. 输入区：`rx.text_area` + 复选框“16进制模式”+ 清空按钮
3. 基础工具按钮区：按 GUI 原布局排成 3 行 × 6 列网格
4. 扩展工具区：分组显示 CRC、bitstring、十进制转换
5. 输出区：只读 `rx.text_area` + 复制按钮

按钮网格参考 GUI：

| 字节反转 | +0x33 | 反转+0x33 | ASCII→HEX | 字节长度 | 大写     |
| 移除空格 | msg→Pn | Pn→msg  | 校验和    | −0x33   | 反转−0x33 |
| HEX→ASCII| 字符数 | 小写     | 添加空格  | msg→Fn  | Fn→msg  |

扩展工具：
- 按钮：HEX→bitstring、bitstring→HEX、字节规整
- 按钮：CRC-16（698.45）、CRC-32、CRC-24
- 下拉：大端/小端 + 按钮：HEX→十进制

## 后端补齐

新增 `tool_hex_to_decimal(text: str, little_endian: bool = True) -> str`：
- 调用 `_parse_hex(text)` 得到字节列表
- 按大小端拼接为整数
- 返回十进制字符串

实现位置：`reflex_web/reflex_web/web_utils.py`

## 导航集成

在 `index()` 的 tab 按钮行新增：
- 按钮文本：“报文工具”
- 点击设置 `State.active_tab = "tool"`
- 在 `rx.cond` 链中新增分支：`State.active_tab == "tool"` → `message_tool_tab()`

## 兼容性

- 仅修改 Reflex 相关文件，不影响 GUI/TUI/Streamlit。
- 新增函数不破坏现有 web_utils 接口。

## 测试策略

1. 启动 `python reflex_web/run_app.py`。
2. 导航到报文工具页。
3. 输入已知 hex，逐一点击按钮，比对 GUI 输出。
4. 测试边界：空输入、非法 hex、非 hex 字符。
