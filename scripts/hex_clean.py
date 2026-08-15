"""hex_clean.py — 通用十六进制清洗（'ED ... 'O 帧提取）

去除所有非十六进制字符，按换行拆分帧，每行归一化为连续大写 hex 字符串。

帧标记规则：
- 帧以 "'ED" 开头、以 "'O" 结尾（' 只是引号分隔符）。
  "'ED" 中的 "ED" 是帧头字节，会保留在输出中（仅去掉前置引号 '）。
- 单行同时包含 'ED 和 'O：直接提取该行 'ED 的 ED 之后、'O 之前的内容，
  帧头 ED 一并保留。
- 单行只有 'ED 没有 'O：帧跨行，继续在后续行收集 "'O" 之前的所有
  hex 字符，拼接到帧头，直到遇到 'O 闭合。
- 续帧行行首的时间戳会被剥离（可连续剥离多个，中间允许夹日志标签），
  避免时间戳数字混入帧内容。支持的格式如：
    12:34:56.789
    2026-08-07 12:34:56.789
    [2026/08/07 12:34:56,789]
    2026-08-05 20:40:30 059: 流程日志：2026-08-05 20:40:29:713
- 没有 'O 闭合的帧（日志被截断）视为不完整，丢弃。
"""

import re

# 匹配非十六进制字符（保留 0-9, a-f, A-F）
_HEX_STRIP_RE = re.compile(r'[^0-9a-fA-F]')

# 行首非十六进制前缀（时间戳之间的日志标签，如 "流程日志："）
_NONHEX_PREFIX_RE = re.compile(r'^[^0-9a-fA-F]+')

# 时间戳：可选日期 + 时:分:秒 + 可选毫秒（空格/冒号/点/逗号 + 3 位数字）+ 可选收尾
# 示例：12:34:56.789 / 2026-08-05 20:40:30 059: / 2026-08-05 20:40:29:713
_TS_RE = re.compile(
    r'^\s*\[?'
    r'(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T])?'
    r'\d{1,2}:\d{2}:\d{2}'
    r'(?:[\s:.,]\d{3})?'
    r'\]?:?\s*'
)

# 标记：'ED / 'O（' 为引号分隔符；ED 是帧头字节，保留在输出中）
_ED_MARKER = "'ED"
_O_MARKER = "'O"
_ED_SKIP = 1  # 只跳过前置引号 '，保留 ED 作为帧头
_O_LEN = len(_O_MARKER)


def _strip_leading_ts(line):
    """剥离行首的一个或多个时间戳（时间戳之间允许夹日志标签文本）。

    例如 "2026-08-05 20:40:30 059: 流程日志：2026-08-05 20:40:29:713 68 0E ..."
    剥离后得到 "68 0E ..."。
    """
    while True:
        m = _TS_RE.match(line)
        if not m:
            break
        line = line[m.end():]
        # 吃掉时间戳后紧邻的非 hex 文本（如 "流程日志："），便于继续匹配下一个时间戳
        line = _NONHEX_PREFIX_RE.sub('', line)
    return line


def process(text, context):
    """
    Args:
        text: 原始文本
        context: 上下文字典（本脚本未使用）

    Returns:
        清洗后的文本，每行一个 hex 帧（帧头 ED 保留）
    """
    lines = text.splitlines()
    result = []
    pending = None  # 跨行累积中的 hex 字符串；None 表示当前没有未闭合帧
    i = 0

    while i < len(lines):
        line = lines[i]

        # 情况一：已有跨行累积的帧，本行负责续帧或闭合
        if pending is not None:
            o_idx = line.find(_O_MARKER)
            if o_idx == -1:
                # 本行没有 'O：先剥离行首时间戳，再把整行 hex 拼入
                pending += _HEX_STRIP_RE.sub('', _strip_leading_ts(line))
                i += 1
                continue
            # 遇到 'O：取 'O 之前的内容，剥离行首时间戳后拼入并闭合
            pending += _HEX_STRIP_RE.sub('', _strip_leading_ts(line[:o_idx]))
            if pending:
                result.append(pending.upper())
            pending = None
            # 'O 之后若还有新的 'ED 起点，重新扫描本行剩余部分
            rest = line[o_idx + _O_LEN:]
            if _ED_MARKER in rest:
                lines[i] = rest
                continue
            i += 1
            continue

        # 情况二：当前没有未闭合帧，查找本行的 'ED 起点
        ed_idx = line.find(_ED_MARKER)
        if ed_idx == -1:
            i += 1
            continue

        o_idx = line.find(_O_MARKER, ed_idx)
        if o_idx != -1:
            # 单行内同时有 'ED 和 'O：直接提取（跳过前置引号 '，保留帧头 ED）
            cleaned = _HEX_STRIP_RE.sub('', line[ed_idx + _ED_SKIP:o_idx])
            if cleaned:
                result.append(cleaned.upper())
            # 'O 之后若还有新的 'ED 起点，重新扫描本行剩余部分
            rest = line[o_idx + _O_LEN:]
            if _ED_MARKER in rest:
                lines[i] = rest
                continue
            i += 1
            continue

        # 只有 'ED 没有 'O：开始跨行累积（跳过前置引号 '，保留帧头 ED）
        pending = _HEX_STRIP_RE.sub('', line[ed_idx + _ED_SKIP:])
        i += 1

    # 末尾仍未闭合的帧（不完整）丢弃
    return '\n'.join(result)
