#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a relocatable UV deployment folder for the Reflex Web app.

This script is intended to run on a machine that has network access and UV
installed. It creates an offline folder containing:

- pinned Python dependencies built into a relocatable .venv
- Reflex web source and precompiled frontend assets
- protocol parser/data files needed by the web runtime
- start_web.cmd / start_web.sh launchers

Usage:
    python reflex_web/build_offline_deploy.py
    python reflex_web/build_offline_deploy.py --python-version 3.12
    python reflex_web/build_offline_deploy.py --output dist/reflex_web_offline

The target server must use the same OS, architecture and Python version as
the build machine.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFLEX_WEB = ROOT / "reflex_web"
DEFAULT_OUTPUT = ROOT / "dist" / "reflex_web_offline"
REQUIREMENTS_IN = REFLEX_WEB / "requirements.in"
REQUIREMENTS_LOCK = REFLEX_WEB / "requirements.lock"
FRONTEND_CLIENT = REFLEX_WEB / ".web" / "build" / "client"


def run_command(command: list[str], cwd: Path | None = None) -> None:
    display = " ".join(str(part) for part in command)
    print(f"==> {display}")
    subprocess.run(command, cwd=cwd, check=True)


def check_uv(python_version: str) -> None:
    if not shutil.which("uv"):
        raise SystemExit("未找到 uv，请先安装 UV：https://docs.astral.sh/uv/")
    if not shutil.which("python") and python_version:
        # uv 也可以自行发现/安装托管 Python；仅快速确认解析器可用。
        run_command(["uv", "python", "find", python_version])


def compile_lockfile(python_version: str) -> None:
    if not REQUIREMENTS_IN.exists():
        raise SystemExit(f"缺少依赖清单: {REQUIREMENTS_IN}")
    run_command([
        "uv",
        "pip",
        "compile",
        str(REQUIREMENTS_IN),
        "-o",
        str(REQUIREMENTS_LOCK),
        "--python",
        python_version,
        "--no-annotate",
    ])


def ensure_frontend() -> None:
    if FRONTEND_CLIENT.exists():
        print(f"==> 前端产物已存在: {FRONTEND_CLIENT}")
        return

    reflex_cli = shutil.which("reflex")
    if reflex_cli:
        run_command(
            ["reflex", "export", "--frontend-only", "--env", "prod", "--no-zip"],
            cwd=REFLEX_WEB,
        )
        return

    raise SystemExit(
        "未找到预编译前端。请先在 reflex_web 目录运行：\n"
        "  reflex export --frontend-only --env prod --no-zip\n"
        "或安装 reflex 后再重新执行本脚本。"
    )


def copy_runtime_files(out_dir: Path) -> None:
    for pattern in ("*.py", "*.json"):
        for source in ROOT.glob(pattern):
            if source.name in {"package-lock.json", "skills-lock.json"}:
                continue
            shutil.copy2(source, out_dir / source.name)

    validator_src = ROOT / "validator"
    if validator_src.exists():
        shutil.copytree(validator_src, out_dir / "validator", dirs_exist_ok=True)

    web_dest = out_dir / "reflex_web"

    _BASE_IGNORE = {
        "__pycache__", ".states", ".tests", "tests", "reflex.lock",
        "uploaded_files",
    }

    def _ignore_web_only(src: str, names: list[str]) -> set[str]:
        """忽略任意层级的缓存/测试/锁文件；reflex_web 顶层额外忽略 PyInstaller 中间产物 build/dist。"""
        src_path = Path(src)
        ignored = set(_BASE_IGNORE)
        # 任意层级忽略 .spec 与 .pyc
        for name in names:
            if name.endswith(".spec") or name.endswith(".pyc"):
                ignored.add(name)
        if src_path.resolve() == REFLEX_WEB.resolve():
            for name in names:
                if name in {"build", "dist"}:
                    ignored.add(name)
        return ignored

    shutil.copytree(
        REFLEX_WEB,
        web_dest,
        ignore=_ignore_web_only,
    )


def build_relocatable_venv(out_dir: Path, python_version: str) -> Path:
    venv_dir = out_dir / ".venv"
    run_command([
        "uv",
        "venv",
        "--relocatable",
        "--python",
        python_version,
        str(venv_dir),
    ])

    venv_python = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    run_command([
        "uv",
        "pip",
        "install",
        "--python",
        str(venv_python),
        "-r",
        str(REQUIREMENTS_LOCK),
    ])
    return venv_python


def write_launchers(out_dir: Path, venv_python: Path) -> None:
    if sys.platform == "win32":
        venv_python_rel = ".venv\\Scripts\\python.exe"
        out_dir.joinpath("start_web.cmd").write_text(
            "@echo off\r\n"
            "cd /d \"%~dp0\"\r\n"
            f"\"{venv_python_rel}\" \"reflex_web\\run_app.py\" --host 0.0.0.0 --port 8080 %*\r\n",
            encoding="utf-8",
        )
        readable_python = ".venv\\Scripts\\python.exe"
    else:
        readable_python = ".venv/bin/python"

    out_dir.joinpath("start_web.sh").write_text(
        "#!/usr/bin/env sh\n"
        "set -e\n"
        "cd \"$(dirname \"$0\")\"\n"
        "exec \".venv/bin/python\" \"reflex_web/run_app.py\" --host 0.0.0.0 --port 8080 \"$@\"\n",
        encoding="utf-8",
    )

    out_dir.joinpath("部署说明.txt").write_text(
        "南网协议解析工具 Reflex Web 离线部署目录\n"
        "========================================\n"
        "要求：目标服务器与构建机同为 Windows/Linux、同 CPU 架构、同 Python 版本。\n"
        "启动：\n"
        "  Windows: start_web.cmd\n"
        "  Linux:   ./start_web.sh\n"
        "也可以手动运行：\n"
        f"  {readable_python} reflex_web/run_app.py --host 0.0.0.0 --port 8080\n"
        "访问：http://服务器IP:8080\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a relocatable UV offline deployment folder")
    parser.add_argument(
        "--python-version",
        default="3.12",
        help="目标服务器使用的 Python 版本（默认 3.12）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="输出目录（默认 dist/reflex_web_offline）",
    )
    args = parser.parse_args()

    out_dir = args.output.resolve()
    check_uv(args.python_version)
    compile_lockfile(args.python_version)
    ensure_frontend()

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    copy_runtime_files(out_dir)
    venv_python = build_relocatable_venv(out_dir, args.python_version)
    write_launchers(out_dir, venv_python)

    print(f"\n离线部署目录已生成: {out_dir}")
    print("请把该目录整体复制到目标服务器，然后运行 start_web.cmd 或 start_web.sh。")


if __name__ == "__main__":
    main()
