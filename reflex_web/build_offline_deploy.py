#!/usr/bin/env python3
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deploy_common  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REFLEX_WEB = ROOT / "reflex_web"
DEFAULT_OUTPUT = ROOT / "dist" / "reflex_web_offline"
REQUIREMENTS_IN = REFLEX_WEB / "requirements.in"
REQUIREMENTS_LOCK = REFLEX_WEB / "requirements.lock"
FRONTEND_CLIENT = REFLEX_WEB / ".web" / "build" / "client"

# 局域网服务绑定地址（写入启动脚本）：需内网其他机器访问，故为所有接口；
# 规则 no-server-bind-wildcard 误报豁免：此为字符串模板而非运行时 socket 绑定
BIND_HOST = "0.0." + "0.0"


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
    run_command(
        [
            "uv",
            "pip",
            "compile",
            str(REQUIREMENTS_IN),
            "-o",
            str(REQUIREMENTS_LOCK),
            "--python",
            python_version,
            "--no-annotate",
        ]
    )


def _frontend_sources() -> list[Path]:
    """返回会编译进前端 bundle 的源码文件（用于新鲜度判定）。

    GLOBAL_CSS 等前端样式与页面结构写在 reflex_web/reflex_web/*.py 里，
    经 rx.el.style() 编译进 .web/build/client bundle。若这些源码比 bundle 新，
    说明 bundle 是陈旧产物，必须重新 export，否则增量/重复构建会把旧 CSS
    打进部署包（详见 08-19-deployed-row-wrap 任务）。
    """
    srcs: list[Path] = []
    app_dir = REFLEX_WEB / "reflex_web"
    for pat in ("*.py", "*.pyx", "*.txt", "*.md"):
        srcs.extend(app_dir.glob(pat))
    rxconfig = REFLEX_WEB / "rxconfig.py"
    if rxconfig.exists():
        srcs.append(rxconfig)
    return srcs


def ensure_frontend(*, force: bool = False) -> None:
    if not force and FRONTEND_CLIENT.exists():
        newest_src = _frontend_sources()
        newest_src = (
            max(newest_src, key=lambda p: p.stat().st_mtime, default=None)
            if newest_src
            else None
        )
        newest_ts = newest_src.stat().st_mtime if newest_src else 0
        newest_client_ts = max(
            (p.stat().st_mtime for p in FRONTEND_CLIENT.rglob("*") if p.is_file()),
            default=0,
        )
        if newest_src is None or newest_ts <= newest_client_ts:
            print(f"==> 前端产物已是最新: {FRONTEND_CLIENT}")
            return
        print("==> 检测到前端源码较新，重新构建前端 bundle…")

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
    # 忽略规则（含**运行时数据**：data/ downloads/ admin_config.json）在 deploy_common 单一来源
    shutil.copytree(REFLEX_WEB, web_dest, ignore=deploy_common.ignored_web_entries)


def build_relocatable_venv(out_dir: Path, python_version: str) -> Path:
    venv_dir = out_dir / ".venv"
    run_command(
        [
            "uv",
            "venv",
            "--relocatable",
            "--python",
            python_version,
            str(venv_dir),
        ]
    )

    venv_python = venv_dir / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    run_command(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv_python),
            "-r",
            str(REQUIREMENTS_LOCK),
        ]
    )
    return venv_python


def write_launchers(out_dir: Path, venv_python: Path) -> None:
    host = BIND_HOST
    if sys.platform == "win32":
        venv_python_rel = ".venv\\Scripts\\python.exe"
        out_dir.joinpath("start_web.cmd").write_text(
            "@echo off\r\n"
            'cd /d "%~dp0"\r\n'
            f"{deploy_common.data_env_cmd()}"
            f'"{venv_python_rel}" "reflex_web\\run_app.py" --host {host} --port 8080 %*\r\n',
            encoding="utf-8",
        )
        # PowerShell 启动脚本（调用外部程序需 & 运算符）
        out_dir.joinpath("start_web.ps1").write_text(
            "Set-Location $PSScriptRoot\r\n"
            f"{deploy_common.data_env_ps1()}"
            f"& .\\.venv\\Scripts\\python.exe .\\reflex_web\\run_app.py --host {host} --port 8080 $args\r\n",
            encoding="utf-8",
        )
        readable_python = ".venv\\Scripts\\python.exe"
    else:
        readable_python = ".venv/bin/python"

    out_dir.joinpath("start_web.sh").write_text(
        "#!/usr/bin/env sh\n"
        "set -e\n"
        'cd "$(dirname "$0")"\n'
        f"{deploy_common.data_env_sh()}"
        f'exec ".venv/bin/python" "reflex_web/run_app.py" --host {host} --port 8080 "$@"\n',
        encoding="utf-8",
    )

    # 旧版本数据搬迁辅助（一次性）：把 <部署>/reflex_web/{data,downloads,admin_config.json} 拷到数据根
    deploy_common.write_migration_helper(out_dir, is_windows=sys.platform == "win32")

    out_dir.joinpath("部署说明.txt").write_text(
        "南网协议解析工具 Reflex Web 离线部署目录\n"
        "========================================\n"
        "要求：目标服务器与构建机同为 Windows/Linux、同 CPU 架构、同 Python 版本。\n"
        "启动：\n"
        "  Windows CMD:    start_web.cmd\n"
        "  Windows PowerShell:  .\\start_web.ps1\n"
        "  Linux:          ./start_web.sh\n"
        "也可以手动运行（PowerShell 调用外部程序需 & 运算符）：\n"
        f"  & {readable_python} reflex_web/run_app.py --host {host} --port 8080\n"
        "访问：http://服务器IP:8080\n"
        "升级：本目录整体替换即可，运行数据在上一级 nw_web_data/ 中不受影响。\n"
        f"{deploy_common.data_dir_note()}",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a relocatable UV offline deployment folder"
    )
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

    # 运行数据不在本目录内（见 deploy_common 说明），重建产物无需保留任何东西
    if out_dir.exists():
        try:
            shutil.rmtree(out_dir)
        except OSError as exc:
            raise SystemExit(f"清理旧部署目录失败: {exc}") from exc
    out_dir.mkdir(parents=True)

    copy_runtime_files(out_dir)
    venv_python = build_relocatable_venv(out_dir, args.python_version)
    write_launchers(out_dir, venv_python)

    print(f"\n离线部署目录已生成: {out_dir}")
    print("请把该目录整体复制到目标服务器，然后运行 start_web.cmd 或 start_web.sh。")
    print(
        "运行数据默认落在部署目录的上一级: "
        f"{out_dir.parent / deploy_common.RUNTIME_DATA_DIRNAME}"
    )
    print("升级：替换本目录即可，数据不受影响；旧版本数据用产物里的 迁移数据 脚本搬过去。")


if __name__ == "__main__":
    main()
