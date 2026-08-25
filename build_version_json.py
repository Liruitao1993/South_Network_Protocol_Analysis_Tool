"""生成私有更新源的 version.json

用法：
    python build_version_json.py [--exe 路径] [--version 1.14.0] [--notes 更新说明]

默认：
    --exe      reflex_web/downloads/南网协议解析工具.exe
    --version  从 main_gui.py 的 APP_VERSION 读取
    --notes    空
    --url      http://10.1.10.172:8091/downloads/南网协议解析工具.exe
    --output   reflex_web/downloads/version.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).parent.resolve()
DEFAULT_EXE = ROOT / "reflex_web" / "downloads" / "南网协议解析工具.exe"
DEFAULT_OUTPUT = ROOT / "reflex_web" / "downloads" / "version.json"
DEFAULT_URL = "http://10.1.10.172:8091/downloads/南网协议解析工具.exe"


def get_version_from_source() -> str:
    """从 main_gui.py 读取 APP_VERSION 常量。"""
    main_gui = ROOT / "main_gui.py"
    if not main_gui.exists():
        return ""
    text = main_gui.read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else ""


def sha256_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """计算文件 SHA-256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成私有更新源 version.json")
    parser.add_argument("--exe", type=str, default=str(DEFAULT_EXE),
                        help=f"exe 路径 (默认: {DEFAULT_EXE})")
    parser.add_argument("--version", type=str, default="",
                        help="版本号 (默认从 main_gui.py 读取)")
    parser.add_argument("--notes", type=str, default="",
                        help="更新说明")
    parser.add_argument("--url", type=str, default=DEFAULT_URL,
                        help=f"下载地址 (默认: {DEFAULT_URL})")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT),
                        help=f"输出路径 (默认: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    exe_path = Path(args.exe).resolve()
    if not exe_path.exists():
        print(f"错误：exe 不存在: {exe_path}", file=sys.stderr)
        return 1

    version = args.version or get_version_from_source()
    if not version:
        print("错误：无法确定版本号，请用 --version 指定", file=sys.stderr)
        return 1

    print(f"exe:      {exe_path}")
    print(f"大小:     {exe_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"版本:     {version}")
    print(f"下载地址: {args.url}")
    print("计算 SHA-256...")

    sha = sha256_of_file(exe_path)
    print(f"SHA-256:  {sha}")

    data = {
        "version": version,
        "url": args.url,
        "notes": args.notes,
        "sha256": sha,
    }

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n已生成: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
