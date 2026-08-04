# -*- coding: utf-8 -*-
"""国网新一代监控前缀剥离

剥离 96..16 包装格式：96H + RSSI(1) + NTB(4) + LEN+TYPE+CH(1) + DATA + CS(1) + 16H
"""
import re
import sys
import argparse

META = {
    "id": "clean_gw_prefix",
    "name": "清理国网新一代监控前缀",
    "description": "剥离 96..16 监控包装头，保留内部协议报文",
    "order": 21,
    "args": [],
}


def strip_gw_prefix(line: str) -> str:
    """剥离一行中的国网新一代 96..16 监控包装头"""
    line = line.strip()
    if not line:
        return ""

    # 清洗：去掉非 hex 字符，保留 hex
    hex_chars = re.sub(r"[^0-9a-fA-F]", "", line).upper()
    if len(hex_chars) < 20:  # 最小包装帧长度
        return ""

    # 查找 96 开头 16 结尾的包装帧
    # 包装格式: 96 + RSSI(2hex) + NTB(8hex) + LEN_TYPE_CH(3hex) + DATA + CS(2hex) + 16
    # 最小长度: 1+2+8+3+2+2 = 18 hex chars (9字节)
    idx = 0
    while idx <= len(hex_chars) - 18:
        if hex_chars[idx:idx+2] == "96":
            # 找到 96 开头，尝试解析
            pos = idx + 2
            # RSSI: 1 字节 (2 hex)
            if pos + 2 > len(hex_chars):
                break
            pos += 2
            # NTB: 4 字节 (8 hex)
            if pos + 8 > len(hex_chars):
                break
            pos += 8
            # LEN+TYPE+CH: 1.5 字节 (3 hex) - 实际是 12bit LEN + 3bit TYPE + 1bit CH
            if pos + 3 > len(hex_chars):
                break
            len_field = int(hex_chars[pos:pos+3], 16)
            data_len = (len_field >> 4) & 0xFFF  # 高 12 位是长度
            pos += 3
            # DATA: data_len 字节 (data_len * 2 hex)
            data_end = pos + data_len * 2
            if data_end + 4 > len(hex_chars):  # +4 for CS(2) + 16(2)
                break
            # 检查结尾 16
            if hex_chars[data_end+2:data_end+4] == "16":
                # 提取 DATA 部分
                data_hex = hex_chars[pos:data_end]
                if len(data_hex) >= 8:  # 至少 4 字节
                    bytes_list = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]
                    return " ".join(bytes_list)
            # 不匹配，继续搜索
            idx += 2
        else:
            idx += 2

    return ""


def run(input_text: str) -> str:
    """主处理函数"""
    results = []
    for line in input_text.splitlines():
        cleaned = strip_gw_prefix(line)
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
