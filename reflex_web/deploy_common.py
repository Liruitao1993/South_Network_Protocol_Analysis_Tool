"""两个部署构建脚本（UV 离线 / 内嵌 Python）的共用部分：运行时数据根约定、启动器片段、数据迁移脚本。

**为什么要有这个模块**：运行时数据（反馈库 + 截图、分享库、发布管理上传的 exe、管理员口令）原先
写在代码目录内（`<部署>/reflex_web/`）。而升级的常见做法是「删掉旧部署目录 → 拷新包」，代码目录
内的数据会连同旧目录一起消失；构建脚本还会把**构建机的开发数据**一并拷进产物。因此这里的约定是：

- 数据根默认放在**部署目录的上一级** `<parent>/nw_web_data`（被替换的目录之外 ⇒ 天然幸存），
  可用环境变量 `NW_WEB_DATA_DIR` 指到任意位置；
- 启动脚本负责注入该变量（**已设则不覆盖**）；
- 构建产物**排除** `data/`、`downloads/`、`admin_config.json`，绝不把开发机数据打进包。

变量名与目录布局的**运行时**定义在 `reflex_web/app_data.py`，本模块从那里取，避免两处各写一份。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from reflex_web.app_data import (  # noqa: F401  单一来源：环境变量名 / 随包资产清单
    ENV_VAR,
    PACKAGED_DOWNLOAD_ASSETS,
)

WEB_DIR = Path(__file__).resolve().parent  # <repo>/reflex_web
RUNTIME_DATA_DIRNAME = "nw_web_data"  # 外置数据根的默认目录名（部署目录的上一级）

# copytree 的忽略集合：基础缓存/测试/锁 + 运行时数据
_BASE_IGNORE = {
    "__pycache__",
    ".states",
    ".tests",
    "tests",
    "reflex.lock",
    "uploaded_files",
}
# 整个目录都是运行时数据（必须排除）
RUNTIME_IGNORE = {
    "data",  # feedback.db / frameshare.db / uploads/feedback/
    "admin_config.json",  # 管理员口令哈希
    RUNTIME_DATA_DIRNAME,  # 万一有人把数据根建在代码目录内
}
# downloads/ 里混着三类东西：随包静态资源、运行时发布产物、开发机的中间产物/临时文件。
# 用**白名单**（只放行要随包分发的资产）而不是黑名单：黑名单语义下任何未列举的东西
# （PyInstaller 的 build/dist、被 gitignore 的 screenshot_*.png、生成工具…）都会被拷进
# 生产包——本次改造最初就踩过（实测漏了 build/dist 共约 25MB）。
# 新增随包资源时必须加进这里，测试 test_build_ignore 会盯着。
# 随包资源清单来自 app_data（应用侧单一来源）——两边必须一致，否则「随包但不被读」或反之
DOWNLOADS_ASSETS = tuple(PACKAGED_DOWNLOAD_ASSETS)


def ignored_web_entries(
    src: str | Path, names: Iterable[str], web_root: str | Path | None = None
) -> set[str]:
    """`shutil.copytree(..., ignore=...)` 回调的实体（提为模块级以便测试直接调用）。

    规则：
    - 任意层级：缓存/测试/锁 + `data`/`admin_config.json`/`nw_web_data`（运行时数据）；
    - `downloads/` 一级：只排除**运行时产物**（`*.exe`、`version.json`、`archive/`）与生成工具，
      保留随包静态资源（`client_screenshot.png`、`client_readme.md`）；
    - 顶层：额外忽略 PyInstaller 中间产物 `build`/`dist`，以及 `.spec`/`.pyc`。

    Args:
        src: 当前被扫描的目录（copytree 传入）。
        names: 该目录下的条目名（copytree 传入）。
        web_root: 被拷贝的 `reflex_web/` 根目录；默认真实包目录（测试用小树时可显式传入）。
    """
    root = Path(web_root) if web_root is not None else WEB_DIR
    src_path = Path(src).resolve()
    ignored = set(_BASE_IGNORE) | set(RUNTIME_IGNORE)
    ignored |= {n for n in names if n.endswith(".spec") or n.endswith(".pyc")}
    if src_path == Path(root).resolve():
        ignored |= {n for n in names if n in {"build", "dist"}}
    if src_path == Path(root).resolve() / "downloads":
        # 白名单语义：不在 DOWNLOADS_ASSETS 里的一律不拷（含 build/dist、*.exe、version.json…）
        ignored |= {n for n in names if n not in DOWNLOADS_ASSETS}
    return ignored


# ══════════════════════════════════════════════════════════════
# 启动器片段（三种脚本各一）
# ══════════════════════════════════════════════════════════════


def data_env_cmd() -> str:
    """CMD：默认数据根 = 本脚本所在目录的上一级 / nw_web_data（已设则不覆盖）。"""
    return (
        f'if not defined {ENV_VAR} for %%I in ("%~dp0..") do set '
        f'"{ENV_VAR}=%%~fI\\{RUNTIME_DATA_DIRNAME}"\r\n'
    )


def data_env_ps1() -> str:
    """PowerShell：同上（`Split-Path -Parent $PSScriptRoot` 归一化掉 `..`）。"""
    return (
        f"if (-not $env:{ENV_VAR}) {{ "
        f'$env:{ENV_VAR} = Join-Path (Split-Path -Parent $PSScriptRoot) "{RUNTIME_DATA_DIRNAME}" }}\r\n'
    )


def data_env_sh() -> str:
    """POSIX sh：同上。"""
    return (
        f'if [ -z "${{{ENV_VAR}:-}}" ]; then\n'
        f'  {ENV_VAR}="$(cd "$(dirname "$0")/.." && pwd)/{RUNTIME_DATA_DIRNAME}"\n'
        "fi\n"
        f"export {ENV_VAR}\n"
    )


def data_dir_note() -> str:
    """部署说明里的「数据目录」段（两种部署方式共用文案）。"""
    return (
        "\n运行数据目录（重要）：\n"
        f"  默认位置：本部署目录的上一级 / {RUNTIME_DATA_DIRNAME}\n"
        "    data/            反馈库 + 分享库 + 上传截图\n"
        "    downloads/       发布管理上传的客户端 exe / version.json\n"
        "    admin_config.json  管理员口令\n"
        f"  可用环境变量 {ENV_VAR} 指到任意位置（启动脚本已设则不覆盖）：\n"
        f"    CMD:        set {ENV_VAR}=D:\\nw_web_data\n"
        f"    PowerShell: $env:{ENV_VAR} = 'D:\\nw_web_data'\n"
        "  升级：替换本部署目录即可，数据在部署目录之外不会被动；备份只需拷该数据目录。\n"
        "  随包静态资源（界面截图 client_screenshot.png、客户端说明 client_readme.md）仍在部署目录内的\n"
        "  reflex_web/downloads/ 中，程序**优先读数据目录、缺失时回落**到这里，可离线直接看到。\n"
        "  若旧版本的数据还在本目录内（reflex_web\\data 等），先运行 迁移数据.cmd 再删除旧目录。\n"
    )


# ══════════════════════════════════════════════════════════════
# 数据迁移脚本（把旧「树内」数据搬到外置数据根；一次性）
# ══════════════════════════════════════════════════════════════


def migrate_script_windows() -> str:
    r"""生成 `迁移数据.cmd`：把 `<部署>\reflex_web\{data,downloads,admin_config.json}` 搬到数据根。

    拷贝（非移动）——旧副本保留作为兜底，确认无误后由运维自行删除。
    """
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        'cd /d "%~dp0"\r\n'
        f'if not defined {ENV_VAR} for %%I in ("%~dp0..") do set "{ENV_VAR}=%%~fI\\{RUNTIME_DATA_DIRNAME}"\r\n'
        "echo.\r\n"
        "echo 把旧版本留在部署目录内的运行数据搬到外置数据目录（升级只需执行一次）\r\n"
        "echo   源  : %CD%\\reflex_web\\ 下的 data\\ 、downloads\\ 、admin_config.json\r\n"
        f"echo   目标: %{ENV_VAR}%\\\r\n"
        "echo.\r\n"
        'if not exist "reflex_web\\data" if not exist "reflex_web\\downloads" '
        'if not exist "reflex_web\\admin_config.json" (\r\n'
        "  echo 未发现旧位置数据，无需迁移。\r\n"
        "  pause\r\n"
        "  exit /b 0\r\n"
        ")\r\n"
        "set /p confirm=确认迁移? [y/N] \r\n"
        'if /i not "%confirm%"=="y" (\r\n'
        "  echo 已取消。\r\n"
        "  pause\r\n"
        "  exit /b 0\r\n"
        ")\r\n"
        f'if not exist "%{ENV_VAR}%" mkdir "%{ENV_VAR}%"\r\n'
        "set FAIL=0\r\n"
        f'if exist "reflex_web\\data" robocopy "reflex_web\\data" "%{ENV_VAR}%\\data" /E /NFL /NDL /NJH /NJS\r\n'
        "if errorlevel 8 set FAIL=1\r\n"
        f'if exist "reflex_web\\downloads" robocopy "reflex_web\\downloads" "%{ENV_VAR}%\\downloads" /E /NFL /NDL /NJH /NJS\r\n'
        "if errorlevel 8 set FAIL=1\r\n"
        f'if exist "reflex_web\\admin_config.json" if not exist "%{ENV_VAR}%\\admin_config.json" '
        f'copy /y "reflex_web\\admin_config.json" "%{ENV_VAR}%\\admin_config.json" >nul\r\n'
        "if errorlevel 1 set FAIL=1\r\n"
        "echo.\r\n"
        "if \"%FAIL%\"==\"1\" (\r\n"
        "  echo ** 迁移未全部成功：请检查上面的错误信息，**不要**删除旧目录内的副本（数据可能还没搬完^)。\r\n"
        "  pause\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
        "echo 迁移完成（旧目录内副本已保留，确认无误后可自行删除）。\r\n"
        "pause\r\n"
    )


def migrate_script_posix() -> str:
    r"""生成 `迁移数据.sh`（Linux 部署用）：同 `migrate_script_windows` 语义。"""
    return (
        "#!/usr/bin/env sh\n"
        "set -e\n"
        'cd "$(dirname "$0")"\n'
        f'if [ -z "${{{ENV_VAR}:-}}" ]; then\n'
        f'  {ENV_VAR}="$(cd "$(dirname "$0")/.." && pwd)/{RUNTIME_DATA_DIRNAME}"\n'
        "fi\n"
        f"export {ENV_VAR}\n"
        "echo\n"
        "echo 把旧版本留在部署目录内的运行数据搬到外置数据目录（升级只需执行一次）\n"
        "echo   源  : $(pwd)/reflex_web/ 下的 data/ downloads/ admin_config.json\n"
        f"echo   目标: ${{{ENV_VAR}}}/\n"
        "echo\n"
        "if [ ! -e reflex_web/data ] && [ ! -e reflex_web/downloads ] && [ ! -e reflex_web/admin_config.json ]; then\n"
        "  echo 未发现旧位置数据，无需迁移。\n"
        "  exit 0\n"
        "fi\n"
        'printf "确认迁移? (y/N) "\n'
        "read -r confirm\n"
        'case "$confirm" in\n'
        "  y|Y) ;;\n"
        "  *) echo 已取消。; exit 0 ;;\n"
        "esac\n"
        f'mkdir -p "${{{ENV_VAR}}}"\n'
        f'[ -d reflex_web/data ] && cp -a reflex_web/data "${{{ENV_VAR}}}/"\n'
        f'[ -d reflex_web/downloads ] && cp -a reflex_web/downloads "${{{ENV_VAR}}}/"\n'
        f'if [ -f reflex_web/admin_config.json ] && [ ! -f "${{{ENV_VAR}}}/admin_config.json" ]; then\n'
        f'  cp -a reflex_web/admin_config.json "${{{ENV_VAR}}}/admin_config.json"\n'
        "fi\n"
        "echo\n"
        "echo 迁移完成（旧目录内副本已保留，确认无误后可自行删除）。\n"
    )


def write_migration_helper(out_dir: Path, *, is_windows: bool) -> Path:
    """把迁移脚本写进部署产物，返回其路径。"""
    if is_windows:
        path = out_dir / "迁移数据.cmd"
        # GBK：中文 Windows 控制台按 DBCS 解析 .cmd，UTF-8（无 BOM）会乱码且可能吞掉
        # 紧随其后的 ASCII 字符（实测 `源  :` 被解析成 `源? :`），与仓库既有 .cmd 一致
        path.write_text(migrate_script_windows(), encoding="gbk", errors="replace")
    else:
        path = out_dir / "迁移数据.sh"
        # 显式 LF：Windows 上 write_text 默认会把 \n 译成 CRLF，而 sh 脚本被 CR 污染后
        # 分支/引号解析会异常（本函数在 Linux 构建时生成，这里只是跨平台保险）
        path.write_text(migrate_script_posix(), encoding="utf-8", newline="\n")
        path.chmod(0o755)
    return path
