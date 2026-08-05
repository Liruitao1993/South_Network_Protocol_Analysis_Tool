# -*- coding: utf-8 -*-
"""通用文本预处理 CLI 工具

类似 Notepad++ 的查找/替换，但支持管道式命令链。
用法:
    pp_cli.py <input_file> <cmd1> [args] [<cmd2> [args] ...] [-o output_file]

命令:
    find <pattern>              保留匹配 pattern 的行（正则）
    excluding <pattern>         从每行中删除 pattern 及其之前的所有内容
    replace <pattern> < repl>   将 pattern 替换为 replacement（正则）
    head <n>                    保留前 n 行
    tail <n>                    保留后 n 行
    skip <n>                    跳过前 n 行
    hex_extract                 从每行提取最长 hex 序列
    dedup                       去除连续重复行

示例:
    # 找出包含 "tcp data:" 的行
    pp_cli.py input.log find "tcp data:" -o filtered.txt

    # 找出包含 "tcp data:" 的行，然后裁剪掉 "len:14: " 之前的内容
    pp_cli.py input.log find "tcp data:" excluding "len:\\d+: " -o trimmed.txt

    # 管道式多命令
    pp_cli.py input.log find "60F0" excluding "60F0" replace "FF" "00" -o out.txt

    # 从监控日志提取 hex 帧
    pp_cli.py monitor.log hex_extract -o frames.txt
"""
import re
import sys
import argparse
import json
from typing import List, Callable


# ── 命令实现 ──────────────────────────────────────────────────────────────

def cmd_find(lines: List[str], pattern: str) -> List[str]:
    """保留匹配 pattern 的行"""
    regex = re.compile(pattern)
    return [l for l in lines if regex.search(l)]


def cmd_excluding(lines: List[str], pattern: str) -> List[str]:
    """从每行删除 pattern 及其之前的所有内容（保留 pattern 之后的部分）"""
    regex = re.compile(pattern)
    results = []
    for line in lines:
        m = regex.search(line)
        if m:
            # 删除从行首到 pattern 结束的部分
            results.append(line[m.end():])
        else:
            # pattern 不匹配的行原样保留
            results.append(line)
    return results


def cmd_replace(lines: List[str], pattern: str, replacement: str) -> List[str]:
    """正则替换"""
    regex = re.compile(pattern)
    return [regex.sub(replacement, l) for l in lines]


def cmd_head(lines: List[str], n: str) -> List[str]:
    """保留前 n 行"""
    return lines[:int(n)]


def cmd_tail(lines: List[str], n: str) -> List[str]:
    """保留后 n 行"""
    return lines[-int(n):]


def cmd_skip(lines: List[str], n: str) -> List[str]:
    """跳过前 n 行"""
    return lines[int(n):]


_HEX_BYTE = r"[0-9a-fA-F]{2}"
_SEP = r"[\s:,\-]*"
_HEX_PATTERN = re.compile(rf"(?:{_HEX_BYTE}{_SEP}){{3,}}")


def cmd_hex_extract(lines: List[str]) -> List[str]:
    """从每行提取最长 hex 序列"""
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        matches = _HEX_PATTERN.findall(line)
        if not matches:
            continue
        best = max(matches, key=len)
        hex_chars = re.sub(r"[^0-9a-fA-F]", "", best)
        if len(hex_chars) < 8:
            continue
        bytes_list = [hex_chars[i:i+2].upper() for i in range(0, len(hex_chars) - 1, 2)]
        results.append(" ".join(bytes_list))
    return results


def cmd_dedup(lines: List[str]) -> List[str]:
    """去除连续重复行"""
    results = []
    prev = None
    for line in lines:
        if line != prev:
            results.append(line)
            prev = line
    return results


# ── 命令注册表 ────────────────────────────────────────────────────────────

COMMANDS = {
    "find": {"fn": cmd_find, "args": 1, "help": "保留匹配 pattern 的行（正则）"},
    "excluding": {"fn": cmd_excluding, "args": 1, "help": "从每行删除 pattern 及其之前的内容"},
    "replace": {"fn": cmd_replace, "args": 2, "help": "正则替换 pattern → replacement"},
    "head": {"fn": cmd_head, "args": 1, "help": "保留前 n 行"},
    "tail": {"fn": cmd_tail, "args": 1, "help": "保留后 n 行"},
    "skip": {"fn": cmd_skip, "args": 1, "help": "跳过前 n 行"},
    "hex_extract": {"fn": cmd_hex_extract, "args": 0, "help": "从每行提取最长 hex 序列"},
    "dedup": {"fn": cmd_dedup, "args": 0, "help": "去除连续重复行"},
}


# ── 管线执行器 ────────────────────────────────────────────────────────────

def parse_and_run(input_text: str, commands: List[str]) -> str:
    """解析命令列表并按顺序执行管线"""
    lines = input_text.splitlines()
    i = 0
    while i < len(commands):
        cmd_name = commands[i]
        if cmd_name not in COMMANDS:
            raise ValueError(f"未知命令: {cmd_name}\n可用命令: {', '.join(COMMANDS.keys())}")
        info = COMMANDS[cmd_name]
        n_args = info["args"]
        args = commands[i+1:i+1+n_args]
        if len(args) < n_args:
            raise ValueError(f"命令 {cmd_name} 需要 {n_args} 个参数，只给了 {len(args)} 个")
        fn = info["fn"]
        if n_args == 0:
            lines = fn(lines)
        elif n_args == 1:
            lines = fn(lines, args[0])
        elif n_args == 2:
            lines = fn(lines, args[0], args[1])
        i += 1 + n_args
    return "\n".join(lines)


# ── JSON 接口（供 GUI 调用）───────────────────────────────────────────────

def run_from_json(json_str: str) -> str:
    """从 JSON 输入执行管线，供 GUI 集成使用

    JSON 格式:
    {
        "input": "原始文本内容",
        "commands": ["find", "tcp data:", "excluding", "len:\\d+: "]
    }
    """
    data = json.loads(json_str)
    input_text = data.get("input", "")
    commands = data.get("commands", [])
    return parse_and_run(input_text, commands)


# ── CLI 入口 ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="通用文本预处理 CLI — 管道式命令链",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s input.log find "tcp data:" -o filtered.txt
  %(prog)s input.log find "tcp data:" excluding "len:\\d+: " -o trimmed.txt
  %(prog)s monitor.log hex_extract -o frames.txt
  %(prog)s input.log find "60F0" dedup -o unique.txt

可用命令:
  find <pattern>           保留匹配 pattern 的行（正则）
  excluding <pattern>      从每行删除 pattern 及其之前的内容
  replace <pat> <repl>     正则替换
  head <n>                 保留前 n 行
  tail <n>                 保留后 n 行
  skip <n>                 跳过前 n 行
  hex_extract              从每行提取最长 hex 序列
  dedup                    去除连续重复行
""",
    )
    parser.add_argument("input_file", nargs="?", help="输入文件（省略则读 stdin）")
    parser.add_argument("commands", nargs="*", help="命令链（命令名 + 参数交替）")
    parser.add_argument("-o", "--output", help="输出文件（省略则输出到 stdout）")
    parser.add_argument("--json", action="store_true", help="以 JSON 模式输入命令")
    parser.add_argument("--list-commands", action="store_true", help="列出所有可用命令")
    args = parser.parse_args()

    if args.list_commands:
        for name, info in COMMANDS.items():
            print(f"  {name:15s} {info['help']}")
        return

    # 读取输入
    if args.input_file:
        with open(args.input_file, encoding="utf-8", errors="replace") as f:
            input_text = f.read()
    else:
        input_text = sys.stdin.read()

    # 解析命令
    if args.json:
        result = run_from_json(json.dumps({"input": input_text, "commands": args.commands}))
    else:
        result = parse_and_run(input_text, args.commands)

    # 输出
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
            if not result.endswith("\n"):
                f.write("\n")
        print(f"输出到 {args.output}（{len(result.splitlines())} 行）")
    else:
        print(result)


if __name__ == "__main__":
    main()
