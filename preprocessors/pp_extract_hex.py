# -*- coding: utf-8 -*-
"""通用 Hex 帧提取

从任意格式的日志中提取所有有效的十六进制报文帧。
支持：空格分隔、冒号分隔、连续 hex、混合文本+hex 行。
"""
import re
import sys
import argparse

META = {
    "id": "extract_hex",
    "name": "提取所有 Hex 帧",
    "description": "从任意日志格式中提取所有有效的十六进制报文帧",
    "order": 10,
    "args": [
        {"name": "--min-bytes", "type": "int", "default": 4, "help": "最小帧字节数"},
        {"name": "--max-bytes", "type": "int", "default": 2048, "help": "最大帧字节数"},
    ],
}

# 匹配 hex 字节模式：2 位 hex，分隔符可为空格/冒号/逗号/无
_HEX_BYTE = r"[0-9a-fA-F]{2}"
_SEP = r"[\s:,\-]*"

# 匹配一行中连续的 hex 字节序列
_HEX_PATTERN = re.compile(
    rf"(?:{_HEX_BYTE}{_SEP}){{3,}}"  # 至少 3 个连续 hex 字节
)


def extract_hex_from_line(line: str) -> str:
    """从一行文本中提取最长的 hex 字节序列，返回空格分隔的大写 hex"""
    line = line.strip()
    if not line:
        return ""

    # 找所有匹配
    matches = _HEX_PATTERN.findall(line)
    if not matches:
        return ""

    # 取最长的匹配
    best = max(matches, key=len)

    # 清洗：提取纯 hex 字符
    hex_chars = re.sub(r"[^0-9a-fA-F]", "", best)
    if len(hex_chars) < 8:  # 至少 4 字节
        return ""

    # 转为大写空格分隔
    bytes_list = [hex_chars[i:i+2].upper() for i in range(0, len(hex_chars) - 1, 2)]
    return " ".join(bytes_list)


def run(input_text: str, min_bytes: int = 4, max_bytes: int = 2048) -> str:
    """主处理函数：提取所有 hex 帧"""
    lines = input_text.splitlines()
    results = []
    for line in lines:
        hex_str = extract_hex_from_line(line)
        if not hex_str:
            continue
        byte_count = len(hex_str.split())
        if byte_count < min_bytes:
            continue
        if byte_count > max_bytes:
            continue
        results.append(hex_str)
    return "\n".join(results)


def main():
    parser = argparse.ArgumentParser(description=META["description"])
    parser.add_argument("--min-bytes", type=int, default=4, help="最小帧字节数")
    parser.add_argument("--max-bytes", type=int, default=2048, help="最大帧字节数")
    parser.add_argument("input_file", nargs="?", help="输入文件（省略则读 stdin）")
    args = parser.parse_args()

    if args.input_file:
        with open(args.input_file, encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = run(text, args.min_bytes, args.max_bytes)
    print(result)


if __name__ == "__main__":
    main()
