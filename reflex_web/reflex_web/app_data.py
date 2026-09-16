"""Web 版运行时数据路径的**唯一来源**（纯 stdlib：无 Qt、无 reflex、不 import 包内其他模块）。

运行时会写盘的东西有三样，都归口到「数据根」：

    <数据根>/data/             feedback.db、frameshare.db、uploads/feedback/（反馈截图）
    <数据根>/downloads/        发布管理上传的客户端 exe / version.json / archive
    <数据根>/admin_config.json 管理员口令哈希

数据根的解析顺序：

1. 环境变量 ``NW_WEB_DATA_DIR``（部署脚本生成的启动器默认注入，运维可指到任意路径）；
2. 冻结态（PyInstaller 单文件 exe）→ **exe 同级** ``nw_web_data/``
   —— 绝不能写 ``sys._MEIPASS``：那是每次启动解包、退出即删的临时目录；
3. 其他（开发机 / 手工启动）→ **代码目录**（`<repo>/reflex_web/`）= 改造前的现状，开发者零感知。

为什么要外置：升级最常见的方式是「删掉旧部署目录 → 拷新包」，数据若在代码目录内会**在新程序
启动前**就被删除；放在部署目录的上一级后，替换部署目录天然不动数据。详见 `离线部署.md`
与 `AGENTS.md §8` 陷阱 38。

约定：**不要在别处拼这些路径**（历史上 `load_download_info` 用两候选目录猜测、`run_app.py`
中间件用 `resource_dir/"data"`，都已被本模块取代）。
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "NW_WEB_DATA_DIR"
DATA_SUBDIR = "data"
DOWNLOADS_SUBDIR = "downloads"
ADMIN_CONFIG_NAME = "admin_config.json"
UPLOADS_SUBPATH = ("uploads", "feedback")
# 随「代码/部署包」分发的下载页静态资源（与运行时发布产物 *.exe/version.json 同目录但来源不同）：
#   - 应用侧：`resolve_download_asset()` 数据根优先、缺失回落随包 → 新部署也能直接看到截图/说明；
#   - 构建侧：`deploy_common` 用这份清单作白名单决定「downloads/ 里哪些随包」；
#   - 迁移侧：`migrate_legacy()` **不搬**这几样（旧版把它们放在代码树里）——搬过去后数据根会一直
#     压着随包副本，后续版本更新的截图/说明永远不生效。
PACKAGED_DOWNLOAD_ASSETS = (
    "client_screenshot.png",
    "client_readme.md",
    "README.md",
)
# 冻结态（单文件 exe）默认数据根目录名（exe 同级）
DEFAULT_DATA_DIRNAME = "nw_web_data"


def code_root() -> Path:
    """代码目录 = `reflex_web/` 包所在层（开发态即 `<repo>/reflex_web`，部署态 `<部署>/reflex_web`）。"""
    return Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包产物中。"""
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def exe_dir() -> Path:
    """可执行文件所在目录（冻结态用于放数据；不依赖 `_MEIPASS`）。"""
    return Path(sys.executable).resolve().parent


def data_root() -> Path:
    """数据根目录（每次调用重新解析，便于测试切环境变量/切 `code_root`）。"""
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser()
    if is_frozen():
        return exe_dir() / DEFAULT_DATA_DIRNAME
    return code_root()


def feedback_dir() -> Path:
    """反馈/分享数据目录（两个 SQLite + 上传截图都在这一层）。"""
    return data_root() / DATA_SUBDIR


def uploads_dir() -> Path:
    """反馈截图目录 `<数据根>/data/uploads/feedback/`。"""
    return feedback_dir().joinpath(*UPLOADS_SUBPATH)


def downloads_dir() -> Path:
    """发布管理目录（客户端 exe / version.json / archive）。"""
    return data_root() / DOWNLOADS_SUBDIR


def admin_config_path() -> Path:
    """管理员口令文件路径。"""
    return data_root() / ADMIN_CONFIG_NAME


@dataclass(frozen=True)
class ResolvedPaths:
    """一次解析出的全部运行时路径（供启动期一次性取用，避免各处重复解析）。"""

    data_root: Path
    feedback_dir: Path
    uploads_dir: Path
    downloads_dir: Path
    admin_config: Path


def resolve_paths(root: Path | None = None) -> ResolvedPaths:
    """解析全部路径；`root` 显式给出时按该根计算（测试与迁移用）。"""
    base = Path(root) if root is not None else data_root()
    fb = base / DATA_SUBDIR
    return ResolvedPaths(
        data_root=base,
        feedback_dir=fb,
        uploads_dir=fb.joinpath(*UPLOADS_SUBPATH),
        downloads_dir=base / DOWNLOADS_SUBDIR,
        admin_config=base / ADMIN_CONFIG_NAME,
    )


def ensure_dirs(paths: ResolvedPaths | None = None) -> ResolvedPaths:
    """建出数据目录骨架（幂等）。"""
    p = paths or resolve_paths()
    p.uploads_dir.mkdir(parents=True, exist_ok=True)
    p.downloads_dir.mkdir(parents=True, exist_ok=True)
    return p


def asset_downloads_dir() -> Path:
    """随代码一起分发的静态资源目录（`client_screenshot.png` / `client_readme.md`）。

    与「运行时的发布产物」（exe / version.json / archive，见 `downloads_dir()`）分开：
    资源随部署包走（新部署开箱即有首页 Hero 与客户端说明；管理员也可在「发布管理」Tab 上传
    截图覆盖，那份写入数据根、优先级更高），发布产物一律由「发布管理」写入数据根。
    """
    return code_root() / DOWNLOADS_SUBDIR


def resolve_download_asset(name: str) -> Path:
    """取下载相关资源的实际路径：**数据根优先**（运维可覆盖），缺失时回落随包资源。

    返回的路径即使不存在也会是「数据根」下的那个（调用方按存在性判断即可）。
    """
    primary = downloads_dir() / name
    if primary.exists():
        return primary
    packaged = asset_downloads_dir() / name
    if packaged.exists():
        return packaged
    return primary


def legacy_paths() -> ResolvedPaths:
    """旧版位置（数据在代码目录内）：仅用于一次性迁移。"""
    return resolve_paths(code_root())


def _move_entry(
    src: Path, dst: Path, label: str, notes: list[str], skip: frozenset[str] = frozenset()
) -> None:
    """把 `src` 搬到 `dst`（**绝不覆盖**已有内容，失败只记不抛，`skip` 里的名字不搬）。

    目录的处理粒度是「条目」而不是「整目录」：目标目录可能已被 `ensure_dirs` 建出空骨架
    （此时整目录判断会误判为「目标已存在」而整项跳过），也可能需要过滤掉个别名字
    （如 downloads/ 里的随包静态资源）；两种情况都靠逐条递归覆盖。
    """
    if not src.exists():
        return

    per_entry = src.is_dir() and (bool(skip) or (dst.exists() and dst.is_dir()))
    if per_entry:
        try:
            dst.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            notes.append(f"迁移失败 {label}：无法创建目标目录 {dst}（{exc}）")
            return
        for child in sorted(src.iterdir()):
            if child.name in skip:
                continue
            _move_entry(child, dst / child.name, f"{label}/{child.name}", notes)
        try:
            if not any(src.iterdir()):  # 搬空后清掉，保持「旧位置不再残留数据」的语义
                src.rmdir()
        except OSError:
            pass
        return

    if dst.exists():
        notes.append(f"跳过 {label}：目标已存在，保留现有（未覆盖）→ {dst}")
        return

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        notes.append(f"已迁移 {label}：{src} → {dst}")
    except OSError as exc:
        notes.append(
            f"迁移失败 {label}：{src} → {dst}（{exc}）；"
            "请手工拷贝到新位置后再删除旧目录，否则下次启动仍会读到旧数据"
        )


def migrate_legacy() -> list[str]:
    """把旧版「树内」数据搬到当前数据根，返回逐项说明（供启动日志与测试断言）。

    规则（`design.md §3`）：
    - 当前数据根 == 旧位置（开发态）→ 什么都不做；
    - 逐项递归：源不存在 → 跳过；目标已存在 → **跳过，绝不覆盖**；否则移入（`shutil.move`，跨盘自动退化）；
    - 搬移失败只记录并告警，**不抛异常、不阻断启动**。
    """
    notes: list[str] = []
    target = resolve_paths()
    legacy = legacy_paths()
    if target.data_root == legacy.data_root:
        return notes

    items = (
        (legacy.feedback_dir, target.feedback_dir, "data/（反馈库 + 分享库 + 截图）"),
        (
            legacy.downloads_dir,
            target.downloads_dir,
            "downloads/（发布管理上传的客户端）",
        ),
        (legacy.admin_config, target.admin_config, "admin_config.json（管理员口令）"),
    )
    # downloads/ 里的随包资产**不搬**（留在代码树里做回落；搬过来会永久遮蔽后续版本的更新）
    asset_skip = frozenset(PACKAGED_DOWNLOAD_ASSETS)
    for src, dst, label in items:
        _move_entry(
            src,
            dst,
            label,
            notes,
            skip=asset_skip if src == legacy.downloads_dir else frozenset(),
        )
    return notes
