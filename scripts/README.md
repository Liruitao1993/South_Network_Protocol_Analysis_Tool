# 脚本预处理示例

此目录为 Python 脚本预处理示例。

## 使用方式

1. 在批量解析标签页工具栏的「脚本」下拉框旁点「加载」
2. 选择 `.py` 文件
3. 点击「运行」对输入框内容执行脚本处理

## 脚本规范

每个脚本必须定义 `process(text, context)` 函数：

```python
def process(text, context):
    """
    Args:
        text:    批量输入框中的原始文本（str）
        context: 上下文字典，包含：
                 - protocol_index: int  当前协议索引
                 - protocol_name:  str  当前协议名称
                 - config_dir:     str  项目根目录
                 - parser:         object 当前协议解析器实例
                 - main_window:    object 主窗口引用（慎用）
    Returns:
        处理后的文本（str），将回填到输入框
    """
    return text
```

## 示例列表

- `hex_clean.py` — 通用十六进制清洗：去除非 hex 字符，每行一帧归一化
- `tcp_payload_extract.py` — TCP 日志 payload 提取：从 "tcp data: XX XX ..." 格式提取连续 hex
- `filter_by_parse.py` — 按解析结果过滤：逐帧调用解析器，只保留解析成功的帧
