#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a self-contained deployment folder with embedded Python runtime.

This script creates a deployment directory that includes:
- Python embeddable distribution (Windows) or UV-managed Python (Linux)
- All dependencies installed into the embedded Python
- Precompiled Reflex frontend
- Protocol parsers, validators, and data files
- Launch scripts

Target machines need NO Python installation - just copy and run.

Usage:
    python reflex_web/build_embedded_deploy.py
    python reflex_web/build_embedded_deploy.py --python-version 3.12
    python reflex_web/build_embedded_deploy.py --output dist/reflex_web_embedded
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
REFLEX_WEB = ROOT / "reflex_web"
DEFAULT_OUTPUT = ROOT / "dist" / "reflex_web_embedded"
REQUIREMENTS_IN = REFLEX_WEB / "requirements.in"
REQUIREMENTS_LOCK = REFLEX_WEB / "requirements.lock"
FRONTEND_CLIENT = REFLEX_WEB / ".web" / "build" / "client"

# 本地缓存目录（避免重复下载）
CACHE_DIR = ROOT / "dist" / ".build_cache"

# Python embeddable package URLs (amd64)
PYTHON_EMBED_URLS = {
    "3.11": "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip",
    "3.12": "https://www.python.org/ftp/python/3.12.4/python-3.12.4-embed-amd64.zip",
    "3.13": "https://www.python.org/ftp/python/3.13.0/python-3.13.0-embed-amd64.zip",
}

GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def run_command(command: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    display = " ".join(str(part) for part in command)
    print(f"==> {display}")
    return subprocess.run(command, cwd=cwd, check=check)


def download_file(url: str, dest: Path) -> None:
    """Download a file from URL to local path, with local cache support."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # 用 URL 文件名作为缓存 key
    cache_key = url.split("/")[-1]
    cache_path = CACHE_DIR / cache_key

    if cache_path.exists():
        print(f"==> 缓存命中: {cache_key}")
        shutil.copy2(cache_path, dest)
        return

    print(f"==> 下载: {url}")
    urllib.request.urlretrieve(url, dest)
    # 写入缓存
    shutil.copy2(dest, cache_path)
    print(f"    已缓存到: {cache_path}")


def check_uv(python_version: str) -> None:
    if not shutil.which("uv"):
        raise SystemExit("未找到 uv，请先安装 UV：https://docs.astral.sh/uv/")


def compile_lockfile(python_version: str) -> None:
    if not REQUIREMENTS_IN.exists():
        raise SystemExit(f"缺少依赖清单: {REQUIREMENTS_IN}")
    # 若 lock 已存在且比 in 新，说明依赖清单未变，直接复用无需重新编译
    # （增量构建场景依赖几乎不动，省掉每次 uv pip compile 的秒~分钟级开销）
    if REQUIREMENTS_LOCK.exists() and REQUIREMENTS_LOCK.stat().st_mtime >= REQUIREMENTS_IN.stat().st_mtime:
        print(f"==> 依赖锁文件已是最新: {REQUIREMENTS_LOCK.name}，跳过重新编译")
        return
    run_command([
        "uv", "pip", "compile",
        str(REQUIREMENTS_IN),
        "-o", str(REQUIREMENTS_LOCK),
        "--python", python_version,
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
    """Copy protocol parsers, data files, and web app to deployment directory."""
    # Copy root-level Python files and JSON data
    for pattern in ("*.py", "*.json"):
        for source in ROOT.glob(pattern):
            if source.name in {"package-lock.json", "skills-lock.json"}:
                continue
            shutil.copy2(source, out_dir / source.name)

    # Copy validator directory
    validator_src = ROOT / "validator"
    if validator_src.exists():
        shutil.copytree(validator_src, out_dir / "validator", dirs_exist_ok=True)

    # Copy reflex_web directory (excluding build artifacts)
    web_dest = out_dir / "reflex_web"
    _BASE_IGNORE = {
        "__pycache__", ".states", ".tests", "tests", "reflex.lock",
        "uploaded_files",
    }

    def _ignore_web_only(src: str, names: list[str]) -> set[str]:
        src_path = Path(src)
        ignored = set(_BASE_IGNORE)
        for name in names:
            if name.endswith(".spec") or name.endswith(".pyc"):
                ignored.add(name)
        if src_path.resolve() == REFLEX_WEB.resolve():
            for name in names:
                if name in {"build", "dist"}:
                    ignored.add(name)
        return ignored

    shutil.copytree(REFLEX_WEB, web_dest, ignore=_ignore_web_only)


def install_embedded_python_windows(out_dir: Path, python_version: str) -> Path:
    """Download and set up Python embeddable package for Windows."""
    python_dir = out_dir / "python"
    python_dir.mkdir(exist_ok=True)

    # Download embeddable package
    url = PYTHON_EMBED_URLS.get(python_version)
    if not url:
        raise SystemExit(f"不支持的 Python 版本: {python_version}。支持: {list(PYTHON_EMBED_URLS.keys())}")

    zip_path = python_dir / "python-embed.zip"
    download_file(url, zip_path)

    # Extract
    print("==> 解压 Python embeddable 包...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(python_dir)
    zip_path.unlink()

    # Enable site-packages by uncommenting import site in python312._pth
    pth_files = list(python_dir.glob("python*._pth"))
    for pth_file in pth_files:
        content = pth_file.read_text(encoding="utf-8")
        content = content.replace("#import site", "import site")
        pth_file.write_text(content, encoding="utf-8")
        print(f"    已启用 site-packages: {pth_file.name}")

    # Download and install pip
    print("==> 安装 pip...")
    get_pip_path = python_dir / "get-pip.py"
    download_file(GET_PIP_URL, get_pip_path)

    python_exe = python_dir / "python.exe"
    run_command([str(python_exe), str(get_pip_path)], cwd=python_dir)
    get_pip_path.unlink()

    # Install setuptools and wheel first (needed for building crcmod from source)
    print("==> 安装 setuptools + wheel...")
    run_command([
        str(python_exe), "-m", "pip", "install", "setuptools", "wheel",
        "--no-warn-script-location",
    ])

    # Install dependencies from lock file
    print("==> 安装依赖...")
    run_command([
        str(python_exe), "-m", "pip", "install",
        "-r", str(REQUIREMENTS_LOCK),
        "--no-warn-script-location",
    ])

    # Clean up pip and setuptools to save space (optional)
    # run_command([str(python_exe), "-m", "pip", "uninstall", "-y", "pip", "setuptools"])

    return python_exe


def install_embedded_python_linux(out_dir: Path, python_version: str) -> Path:
    """Use UV to install Python into a local directory for Linux."""
    python_dir = out_dir / "python"
    python_dir.mkdir(exist_ok=True)

    # Use UV to install Python into the directory
    print(f"==> 使用 UV 安装 Python {python_version}...")
    run_command([
        "uv", "python", "install", python_version,
        "--install-dir", str(python_dir),
    ])

    # Find the installed Python executable
    python_bin = python_dir / "bin" / "python"
    if not python_bin.exists():
        # Try alternative paths
        for pattern in ["python3.*/python", "python*/python"]:
            matches = list((python_dir / "bin").glob(pattern))
            if matches:
                python_bin = matches[0]
                break

    if not python_bin.exists():
        raise RuntimeError(f"无法找到安装的 Python: {python_dir}")

    # Install pip
    print("==> 安装 pip...")
    run_command([str(python_bin), "-m", "ensurepip", "--upgrade"])

    # Install dependencies
    print("==> 安装依赖...")
    run_command([
        str(python_bin), "-m", "pip", "install",
        "-r", str(REQUIREMENTS_LOCK),
        "--no-warn-script-location",
    ])

    return python_bin


def write_launchers(out_dir: Path, python_exe: Path, is_windows: bool) -> None:
    """Create startup scripts for the embedded deployment."""
    if is_windows:
        # Windows CMD launcher
        python_rel = "python\\python.exe"
        out_dir.joinpath("start_web.cmd").write_text(
            "@echo off\r\n"
            "cd /d \"%~dp0\"\r\n"
            f"\"{python_rel}\" \"reflex_web\\run_app.py\" --host 0.0.0.0 --port 8080 %*\r\n",
            encoding="utf-8",
        )

        # PowerShell launcher
        out_dir.joinpath("start_web.ps1").write_text(
            "Set-Location $PSScriptRoot\r\n"
            f"& .\\python\\python.exe .\\reflex_web\\run_app.py --host 0.0.0.0 --port 8080 $args\r\n",
            encoding="utf-8",
        )

        readable_python = "python\\python.exe"
    else:
        # Linux shell launcher
        out_dir.joinpath("start_web.sh").write_text(
            "#!/usr/bin/env bash\n"
            "set -e\n"
            "cd \"$(dirname \"$0\")\"\n"
            "exec \"./python/bin/python\" \"reflex_web/run_app.py\" --host 0.0.0.0 --port 8080 \"$@\"\n",
            encoding="utf-8",
        )
        out_dir.joinpath("start_web.sh").chmod(0o755)
        readable_python = "./python/bin/python"

    # Deployment instructions
    out_dir.joinpath("部署说明.txt").write_text(
        "南网协议解析工具 - Reflex Web 版（内嵌 Python）\n"
        "============================================\n\n"
        "特点：无需安装 Python，解压即用！\n\n"
        "启动方法：\n"
        f"  Windows CMD:       start_web.cmd\n"
        f"  Windows PowerShell: .\\start_web.ps1\n"
        f"  Linux/Mac:         ./start_web.sh\n\n"
        "也可以手动运行：\n"
        f"  {readable_python} reflex_web/run_app.py --host 0.0.0.0 --port 8080\n\n"
        "访问地址：http://服务器IP:8080\n\n"
        "修改端口：\n"
        f"  start_web.cmd --port 9000\n\n"
        "注意事项：\n"
        "- 本部署目录仅支持 Windows (amd64)\n"
        "- 如需 Linux 版本，请在 Linux 机器上重新构建\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build embedded Python deployment for Reflex Web")
    parser.add_argument(
        "--python-version",
        default="3.12",
        choices=["3.11", "3.12", "3.13"],
        help="Python version to embed (default: 3.12)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output directory (default: dist/reflex_web_embedded)",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="增量构建：复用已有内嵌 Python 解释器与 site-packages 依赖，"
             "只刷新源码与数据文件（大幅缩短重复构建时间）",
    )
    args = parser.parse_args()

    is_windows = sys.platform == "win32"
    out_dir = args.output.resolve()

    print("=" * 60)
    print("  南网协议解析工具 - 内嵌 Python 部署构建")
    print("=" * 60)
    if args.skip_deps:
        print("  模式: 增量构建（复用 Python 解释器 + 依赖，仅刷新源码）")
    else:
        print("  模式: 完整构建（重新安装 Python 解释器 + 全部依赖）")
    print()

    # Pre-checks
    if not is_windows:
        check_uv(args.python_version)

    compile_lockfile(args.python_version)
    ensure_frontend()

    # 输出目录清理与增量保留
    # 增量模式：保留已装好的 python/（解释器 + site-packages），仅重建其余源码层。
    # 这样重复构建只复制改动的源码/数据文件，秒级完成，无需重新下载解释器和依赖。
    python_backup: Path | None = None
    if out_dir.exists():
        keep_python = args.skip_deps and (out_dir / "python").exists()
        if keep_python:
            # 先移走 python/ 到临时目录，重建 out_dir 后再移回，避免整目录 rmtree 丢失依赖
            python_backup = out_dir.with_name(out_dir.name + ".pytmp")
            if python_backup.exists():
                shutil.rmtree(python_backup)
            shutil.move(out_dir / "python", python_backup)
            shutil.rmtree(out_dir)
            out_dir.mkdir(parents=True)
            shutil.move(python_backup, out_dir / "python")
            print("    增量保留 python/（内嵌解释器 + 依赖）")
        else:
            shutil.rmtree(out_dir)
            out_dir.mkdir(parents=True)
    else:
        out_dir.mkdir(parents=True)

    # Copy runtime files
    print("\n[1/4] 复制运行时文件...")
    copy_runtime_files(out_dir)

    # Install embedded Python（增量模式若 python/ 已有效则跳过）
    print("\n[2/4] 安装内嵌 Python...")
    need_install = True
    if args.skip_deps and (out_dir / "python" / "python.exe").exists():
        python_exe = out_dir / "python" / "python.exe"
        print(f"    已存在内嵌 Python: {python_exe}，跳过下载与依赖安装（增量构建）")
        need_install = False
    if need_install:
        if is_windows:
            python_exe = install_embedded_python_windows(out_dir, args.python_version)
        else:
            python_exe = install_embedded_python_linux(out_dir, args.python_version)

    # Create launchers
    print("\n[3/4] 创建启动脚本...")
    write_launchers(out_dir, python_exe, is_windows)

    # Summary
    print("\n[4/4] 构建完成！")
    print()
    print("=" * 60)
    print(f"  部署目录: {out_dir}")
    print()
    print("  部署步骤:")
    print(f"    1. 把 {out_dir.name} 整个目录复制到目标机器")
    print(f"    2. 运行 start_web.cmd (Windows) 或 ./start_web.sh (Linux)")
    print(f"    3. 浏览器访问 http://服务器IP:8080")
    print()
    if args.skip_deps:
        print("  本次为增量构建，python/ 依赖目录未被重建。")
        print("  如需强制重建解释器与依赖，去掉 --skip-deps 重跑完整构建。")
    print("=" * 60)


if __name__ == "__main__":
    main()
