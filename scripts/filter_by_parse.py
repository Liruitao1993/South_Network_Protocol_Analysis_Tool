"""
filter_by_parse.py — 按解析结果过滤帧

逐行解析报文，只保留解析成功的帧。
可用于从大量杂帧中筛选有效报文。

注意：
- 每行视为一帧
- 解析失败的行被丢弃
- 使用当前 GUI 选中的协议解析器（context['parser']）
"""

import traceback


def process(text, context):
    """
    Args:
        text: 每行一帧的 hex 文本
        context: 上下文字典，必须包含 'parser'

    Returns:
        只含解析成功帧的文本
    """
    parser = context.get('parser')
    if parser is None:
        raise RuntimeError("当前协议解析器不可用")

    lines = text.splitlines()
    kept = []
    skipped = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            # 尝试调用 parse_to_table（大多数 parser 支持）
            if hasattr(parser, 'parse_to_table'):
                result = parser.parse_to_table(line)
                # parse_to_table 返回 None 或空列表视为失败
                if result is None:
                    skipped += 1
                    continue
                if isinstance(result, list) and len(result) == 0:
                    skipped += 1
                    continue
            elif hasattr(parser, 'parse'):
                result = parser.parse(line)
                if result is None:
                    skipped += 1
                    continue
                if isinstance(result, dict) and not result:
                    skipped += 1
                    continue
            else:
                # 无法判断，保守保留
                kept.append(line)
                continue

            kept.append(line)
        except Exception:
            skipped += 1
            continue

    print(f"[filter_by_parse] 保留 {len(kept)} 帧，跳过 {skipped} 帧")
    return '\n'.join(kept)
