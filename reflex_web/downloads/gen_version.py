"""生成私有更新源 version.json（单文件版，零依赖，仅用标准库）

放到服务器上 exe 同目录直接运行，自动扫描当前目录的 exe。

用法：
    python gen_version.py                      # 自动找 exe，版本号需手动输入
    python gen_version.py --version 1.14.7     # 指定版本号
    python gen_version.py --exe app.exe --version 1.14.7 --notes "修复xxx"
    python gen_version.py --url "http://10.1.10.172:8091/download/南网协议解析工具.exe"

默认：
    --exe      当前目录下第一个 .exe 文件
    --output   version.json（与 exe 同目录）
    --url      自动用文件名拼接 /download/ 路径
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def find_exe_in_dir(d: Path) -> Path | None:
    """找目录下第一个 exe（排除 gen_version.py 自己和明显无关的）。"""
    exes = [p for p in d.glob("*.exe") if p.is_file()]
    if not exes:
        return None
    # 优先选名字含"协议"或"解析"的
    for e in exes:
        if "协议" in e.name or "解析" in e.name or "jiexi" in e.name.lower():
            return e
    return exes[0]


def sha256_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    here = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="生成 version.json（私有更新源）")
    parser.add_argument("--exe", type=str, default="",
                        help="exe 路径（默认：当前目录第一个 exe）")
    parser.add_argument("--version", type=str, default="",
                        help="版本号，如 1.14.7（必须指定）")
    parser.add_argument("--notes", type=str, default="",
                        help="更新说明")
    parser.add_argument("--url", type=str, default="",
                        help="下载地址（默认：/download/exe文件名）")
    parser.add_argument("--output", type=str, default="",
                        help="输出路径（默认：exe 同目录 version.json）")
    args = parser.parse_args()

    # 定位 exe
    if args.exe:
        exe_path = Path(args.exe).resolve()
    else:
        exe_path = find_exe_in_dir(here)
        if exe_path is None:
            print("错误：当前目录找不到 exe 文件，请用 --exe 指定", file=sys.stderr)
            return 1

    if not exe_path.exists():
        print(f"错误：exe 不存在: {exe_path}", file=sys.stderr)
        return 1

    version = args.version.strip()
    if not version:
        print("错误：请用 --version 指定版本号", file=sys.stderr)
        return 1

    size_mb = exe_path.stat().st_size / 1024 / 1024

    # 下载地址
    if args.url:
        url = args.url
    else:
        # 默认：/download/ + exe 文件名
        from urllib.parse import quote
        url = "/download/" + quote(exe_path.name)

    print(f"exe:      {exe_path.name}")
    print(f"大小:     {size_mb:.2f} MB")
    print(f"版本:     {version}")
    print(f"下载地址: {url}")
    print("计算 SHA-256...")

    sha = sha256_of_file(exe_path)
    print(f"SHA-256:  {sha}")

    data = {
        "version": version,
        "url": url,
        "notes": args.notes,
        "sha256": sha,
    }

    if args.output:
        out_path = Path(args.output).resolve()
    else:
        out_path = exe_path.parent / "version.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n已生成: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
