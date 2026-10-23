# -*- coding: utf-8 -*-
"""把**本仓库的构建产物目录**加进 Windows Defender 排除项（需管理员）。

用途：只在**自己的开发机**上避免「刚编出来的 exe 被实时防护当场删掉/隔离」，
让构建与冒烟测试能跑通。**这不能解决对外分发时的 SmartScreen / 360 拦截** ——
那是「无签名 + 无信誉」问题，见 docs/anti_virus_and_signing.md。

设计约束（改之前先读）：
- **只放行 dist/ 与 build/ 两个目录**，绝不整盘/整个用户目录放行；
  `--show` 只读打印、`--remove` 精确撤销本脚本加过的两条。
- 命令一律走 `Add-MpPreference -ExclusionPath`（Defender 官方接口），
  不碰注册表、不改策略、不关实时防护。
- 非管理员直接给可复制的提权命令，不静默失败。

用法：
    python scripts/defender_exclude_build.py --show
    python scripts/defender_exclude_build.py --add      # 需管理员
    python scripts/defender_exclude_build.py --remove    # 需管理员
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 只放行这两个目录（构建产物 + 中间产物），不要扩成父目录
TARGETS = (ROOT / "dist", ROOT / "build")


def _is_admin() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:                                   # noqa: BLE001
        return False


def _powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="mbcs", errors="replace",
    )


def show() -> int:
    """打印当前排除项（需要管理员；普通权限下 Defender 会拒绝读取）。"""
    result = _powershell("(Get-MpPreference).ExclusionPath")
    out = (result.stdout or "").strip()
    if "Must be an administrator" in out or (result.returncode != 0 and not out):
        print("读取排除项需要管理员权限。请用管理员 PowerShell 运行：")
        print(f"  python {Path(__file__).relative_to(ROOT)} --show")
        return 1
    entries = [line.strip() for line in out.splitlines() if line.strip()]
    if not entries or entries == ["N/A"]:
        print("当前没有任何排除项。")
    else:
        print(f"当前排除项（{len(entries)} 条）：")
        for entry in entries:
            mark = "  ← 本脚本加的" if _same(entry) else ""
            print(f"  {entry}{mark}")
    return 0


def _same(text: str) -> bool:
    try:
        return Path(text).resolve() in {t.resolve() for t in TARGETS if t.exists()}
    except OSError:
        return False


def add() -> int:
    if not _is_admin():
        print("需要管理员权限。请右键「以管理员身份运行」PowerShell，然后执行：")
        print(f"  python {Path(__file__).relative_to(ROOT)} --add")
        return 1
    for target in TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        result = _powershell(
            f"Add-MpPreference -ExclusionPath '{target}' -ErrorAction Stop")
        if result.returncode != 0:
            print(f"[失败] {target}: {(result.stderr or '').strip()}")
            return 1
        print(f"[OK] 已排除 {target}")
    print("\n注意：这只影响本机 Defender，且只对上述两个目录生效。")
    print("对外分发被 SmartScreen/360 拦截的问题不靠这个解决 —— 见 "
          "docs/anti_virus_and_signing.md")
    return 0


def remove() -> int:
    if not _is_admin():
        print("需要管理员权限。请用管理员 PowerShell 运行：")
        print(f"  python {Path(__file__).relative_to(ROOT)} --remove")
        return 1
    for target in TARGETS:
        result = _powershell(
            f"Remove-MpPreference -ExclusionPath '{target}' -ErrorAction SilentlyContinue")
        print(f"[OK] 已撤销 {target}" if result.returncode == 0
              else f"[警告] 撤销 {target} 时返回 {result.returncode}")
    return 0


def main() -> int:
    if os.name != "nt":
        print("本脚本只适用于 Windows Defender。")
        return 1
    parser = argparse.ArgumentParser(description="Defender 排除项：只放行本仓库构建目录")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--show", action="store_true", help="查看当前排除项")
    group.add_argument("--add", action="store_true", help="添加 dist/ 与 build/ 排除项")
    group.add_argument("--remove", action="store_true", help="撤销本脚本加过的排除项")
    args = parser.parse_args()
    if args.show:
        return show()
    if args.add:
        return add()
    return remove()


if __name__ == "__main__":
    sys.exit(main())
