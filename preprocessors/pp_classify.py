# -*- coding: utf-8 -*-
"""按协议分类提取

识别 hex 帧的协议类型并分类输出。
"""
import re
import sys
import argparse

META = {
    "id": "classify",
    "name": "按协议分类",
    "description": "识别每个 hex 帧的协议类型，按类别分组输出",
    "order": 40,
    "args": [
        {"name": "--filter", "type": "str", "default": "", "help": "只输出指定协议（nw/gdw/dlt645/hdlc/csg/gw/tcp）"},
    ],
}


def classify_frame(hex_str: str) -> str:
    """判断一个 hex 帧的协议类型"""
    hex_clean = re.sub(r"\s+", "", hex_str).upper()
    if len(hex_clean) < 4:
        return "unknown"

    first_byte = hex_str.strip()[:2].upper()

    # 南网/国网协议：68 开头
    if first_byte == "68":
        return "nw_or_gdw"  # 需要进一步分析 AFN/DI 区分

    # HDLC/DLMS：7E 开头
    if first_byte == "7E":
        return "hdlc"

    # DLT645：68 开头（与南网/国网相同起始符）
    # 区分方法：DLT645 地址域 6 字节 + 68 + 控制码
    if first_byte == "68":
        return "nw_or_gdw_or_dlt645"

    # 新一代载波（CSG）：FC 字节低 4 位 ∈ {8,9,A,B}
    if len(hex_clean) >= 4:
        try:
            fc = int(first_byte, 16)
            if (fc & 0x0F) in (0x08, 0x09, 0x0A, 0x0B):
                return "csg"
        except ValueError:
            pass

    # 国网新一代双模：FC 字节低 4 位 ∈ {0,1,2,3}
    if len(hex_clean) >= 4:
        try:
            fc = int(first_byte, 16)
            if (fc & 0x0F) in (0x00, 0x01, 0x02, 0x03):
                return "gw"
        except ValueError:
            pass

    return "unknown"


def run(input_text: str, filter_proto: str = "") -> str:
    """主处理函数"""
    lines = input_text.splitlines()
    groups = {}
    for line in lines:
        hex_str = line.strip()
        if not hex_str:
            continue
        proto = classify_frame(hex_str)
        if filter_proto and proto != filter_proto:
            continue
        groups.setdefault(proto, []).append(hex_str)

    # 输出
    result_lines = []
    for proto, frames in sorted(groups.items()):
        result_lines.append(f"# [{proto}] ({len(frames)} frames)")
        for f in frames:
            result_lines.append(f)
        result_lines.append("")

    return "\n".join(result_lines)


def main():
    parser = argparse.ArgumentParser(description=META["description"])
    parser.add_argument("--filter", type=str, default="", help="只输出指定协议")
    parser.add_argument("input_file", nargs="?", help="输入文件（省略则读 stdin）")
    args = parser.parse_args()

    if args.input_file:
        with open(args.input_file, encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    print(run(text, args.filter))


if __name__ == "__main__":
    main()
