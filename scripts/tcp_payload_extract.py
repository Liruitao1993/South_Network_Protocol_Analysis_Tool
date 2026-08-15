"""
tcp_payload_extract.py — TCP 日志 payload 提取

从类似以下格式的日志中提取 TCP 数据段的 hex：

    12:34:56.789 tcp data: 68 0E 00 00 00 00 01 00
    12:34:57.123 [TCP] payload=68 0E 00 00 00 00 01 00
    [RX] TCP payload: 68 0E 00 ...

策略：先找到 tcp/payload/data 等关键词，再从关键词之后提取连续的空格分隔 hex 字节。
"""

import re


def process(text, context):
    """
    Args:
        text: 原始日志文本
        context: 上下文字典（本脚本未使用）

    Returns:
        每行一帧的 hex 文本
    """
    lines = text.splitlines()
    result = []

    # 匹配 tcp/payload/data 关键词，捕获其后的内容
    # 支持 : / = / 空格 分隔
    pattern = re.compile(
        r'(?:tcp\s*(?:data|payload)?|payload|data)\s*[:=]?\s*(.*)',
        re.IGNORECASE
    )
    hex_byte_re = re.compile(r'\b[0-9A-Fa-f]{2}\b')

    for line in lines:
        m = pattern.search(line)
        if not m:
            continue

        after = m.group(1)
        if not after.strip():
            continue

        hex_bytes = hex_byte_re.findall(after)
        if len(hex_bytes) >= 2:
            result.append(''.join(hex_bytes).upper())

    return '\n'.join(result)
