# -*- coding: utf-8 -*-
"""TCP 载荷提取

从 TCP 抓包日志中提取应用层载荷数据。
支持 scapy/tcpdump 格式和原始 hex dump。
"""
import re
import sys
import argparse

META = {
    "id": "extract_tcp",
    "name": "提取 TCP 载荷",
    "description": "从 TCP 抓包日志中提取应用层载荷 hex 数据",
    "order": 30,
    "args": [
        {"name": "--src-port", "type": "str", "default": "", "help": "按源端口过滤"},
        {"name": "--dst-port", "type": "str", "default": "", "help": "按目的端口过滤"},
    ],
}

# TCP 报文行格式：时间戳 + IP:Port -> IP:Port + 协议 + 长度 + 载荷
# 典型格式: 10:30:00.123 192.168.1.1:8080 -> 10.0.0.1:12345 [P] Len 123
_TCP_LINE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[\.\d]*)\s+"  # 时间戳
    r"(\S+):(\d+)\s*->\s*(\S+):(\d+)\s+"  # src:port -> dst:port
    r".*?Len\s+(\d+)",  # Len NNN
    re.IGNORECASE
)

# 载荷 hex 行（紧跟 TCP 头之后的 hex dump）
_HEX_LINE = re.compile(r"^\s*([0-9a-fA-F]{2}[\s:]+[0-9a-fA-F]{2}.*)$")


def extract_from_tcp_log(input_text: str, src_port: str = "", dst_port: str = "") -> str:
    """从 TCP 日志中提取载荷"""
    lines = input_text.splitlines()
    results = []
    capture_payload = False
    payload_lines = []

    for line in lines:
        m = _TCP_LINE.search(line)
        if m:
            # 保存之前的载荷
            if capture_payload and payload_lines:
                hex_str = " ".join(payload_lines)
                hex_clean = re.sub(r"[^0-9a-fA-F]", "", hex_str)
                if len(hex_clean) >= 8:
                    bytes_list = [hex_clean[i:i+2].upper() for i in range(0, len(hex_clean)-1, 2)]
                    results.append(" ".join(bytes_list))
                payload_lines = []

            s_port = m.group(3)
            d_port = m.group(5)

            # 端口过滤
            if src_port and s_port != src_port:
                capture_payload = False
                continue
            if dst_port and d_port != dst_port:
                capture_payload = False
                continue

            capture_payload = True
            continue

        # 检查是否是 hex dump 行
        if capture_payload:
            hm = _HEX_LINE.match(line)
            if hm:
                payload_lines.append(hm.group(1).strip())
            else:
                # 非 hex 行，结束当前载荷
                if payload_lines:
                    hex_str = " ".join(payload_lines)
                    hex_clean = re.sub(r"[^0-9a-fA-F]", "", hex_str)
                    if len(hex_clean) >= 8:
                        bytes_list = [hex_clean[i:i+2].upper() for i in range(0, len(hex_clean)-1, 2)]
                        results.append(" ".join(bytes_list))
                    payload_lines = []
                capture_payload = False

    # 处理最后的载荷
    if payload_lines:
        hex_str = " ".join(payload_lines)
        hex_clean = re.sub(r"[^0-9a-fA-F]", "", hex_str)
        if len(hex_clean) >= 8:
            bytes_list = [hex_clean[i:i+2].upper() for i in range(0, len(hex_clean)-1, 2)]
            results.append(" ".join(bytes_list))

    return "\n".join(results)


def run(input_text: str, src_port: str = "", dst_port: str = "") -> str:
    return extract_from_tcp_log(input_text, src_port, dst_port)


def main():
    parser = argparse.ArgumentParser(description=META["description"])
    parser.add_argument("--src-port", type=str, default="", help="按源端口过滤")
    parser.add_argument("--dst-port", type=str, default="", help="按目的端口过滤")
    parser.add_argument("input_file", nargs="?", help="输入文件（省略则读 stdin）")
    args = parser.parse_args()

    if args.input_file:
        with open(args.input_file, encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    print(run(text, args.src_port, args.dst_port))


if __name__ == "__main__":
    main()
