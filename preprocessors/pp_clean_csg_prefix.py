# -*- coding: utf-8 -*-
"""南网新一代监控前缀剥离

剥离格式：<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>
支持连帧和分片。
"""
import re
import sys
import argparse

META = {
    "id": "clean_csg_prefix",
    "name": "清理南网新一代监控前缀",
    "description": "剥离 '-> 接收机 Has Get' 标记 + 15 字节监控头，保留协议报文",
    "order": 20,
    "args": [],
}

# 监控前缀标记
_CSG_MARKER = re.compile(
    r"->\s*接收机\s*Has\s*Get\s*"  # -> 接收机 Has Get
    , re.IGNORECASE
)

# 15 字节监控头 = 30 个 hex 字符（含空格/冒号分隔的 15 字节）
_CSG_HEADER_BYTES = 15


def strip_csg_prefix(line: str) -> str:
    """剥离一行中的南网新一代监控前缀，返回纯协议报文 hex"""
    line = line.strip()
    if not line:
        return ""

    # 检查是否包含监控标记
    m = _CSG_MARKER.match(line)
    if not m:
        return ""  # 非监控格式

    # 提取标记后的部分
    rest = line[m.end():].strip()

    # rest 应该是 <15字节监控头 hex> <协议报文 hex>
    # 清洗 hex
    hex_chars = re.sub(r"[^0-9a-fA-F]", "", rest)
    if len(hex_chars) < 30:  # 至少 15 字节监控头
        return ""

    # 跳过前 15 字节（30 hex 字符），后面是协议报文
    if len(hex_chars) <= 30:
        return ""  # 只有监控头，没有报文

    payload_hex = hex_chars[30:]  # 跳过 15 字节
    # 转为空格分隔大写
    bytes_list = [payload_hex[i:i+2].upper() for i in range(0, len(payload_hex) - 1, 2)]
    return " ".join(bytes_list)


def run(input_text: str) -> str:
    """主处理函数：剥离所有行的 CSG 监控前缀"""
    results = []
    for line in input_text.splitlines():
        cleaned = strip_csg_prefix(line)
        if cleaned:
            results.append(cleaned)
    return "\n".join(results)


def main():
    parser = argparse.ArgumentParser(description=META["description"])
    parser.add_argument("input_file", nargs="?", help="输入文件（省略则读 stdin）")
    args = parser.parse_args()

    if args.input_file:
        with open(args.input_file, encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    print(run(text))


if __name__ == "__main__":
    main()
