"""Web 运行时数据外置回归测试（任务 09-16-web-data-externalization）

覆盖：
  1. 数据根解析矩阵：NW_WEB_DATA_DIR → 冻结态 exe 同级 nw_web_data → 回落代码目录（现状）
  2. 单一来源：feedback/share 模型与 reflex_web 的 getter 全部走 app_data
  3. ensure_dirs 建目录；legacy_paths 指向旧的树内位置
  4. 迁移：搬走旧数据 / 幂等 / 绝不覆盖 / 失败不抛（返回告警）
  5. 部署产物排除运行时数据（data/ downloads/ admin_config.json）——含 copytree 端到端
  6. 启动脚本注入 NW_WEB_DATA_DIR 且「已设则不覆盖」；迁移脚本随产物生成
  7. 部署文档不再出现「重建时自动保留 data/」这类不成立的承诺

直接运行: PYTHONIOENCODING=utf-8 python test/test_web_data_paths.py
"""

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reflex_web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


class _EnvGuard:
    """临时设置环境变量，退出时还原（NW_WEB_DATA_DIR 会影响所有路径函数）。"""

    def __init__(self, **env):
        self.env = env
        self.saved = {}

    def __enter__(self):
        for k, v in self.env.items():
            self.saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


# ═══════════════════════════════════════════════════════════════
# 1. 解析矩阵
# ═══════════════════════════════════════════════════════════════


def test_resolution():
    print("\n[1] 数据根解析矩阵")
    from reflex_web import app_data as ad

    # 1.1 环境变量优先
    with (
        tempfile.TemporaryDirectory(prefix="nwdata_env_") as td,
        _EnvGuard(NW_WEB_DATA_DIR=td),
    ):
        check(
            "env: data_root = NW_WEB_DATA_DIR",
            ad.data_root() == Path(td),
            str(ad.data_root()),
        )
        check("env: feedback_dir = <root>/data", ad.feedback_dir() == Path(td) / "data")
        check(
            "env: downloads_dir = <root>/downloads",
            ad.downloads_dir() == Path(td) / "downloads",
        )
        check(
            "env: admin_config = <root>/admin_config.json",
            ad.admin_config_path() == Path(td) / "admin_config.json",
        )
        paths = ad.resolve_paths()
        check(
            "resolve_paths 与各函数一致",
            paths.data_root == ad.data_root()
            and paths.feedback_dir == ad.feedback_dir()
            and paths.downloads_dir == ad.downloads_dir()
            and paths.admin_config == ad.admin_config_path(),
        )

    # 1.2 冻结态（PyInstaller）：exe 同级 nw_web_data（**不能**落 _MEIPASS 临时目录）
    fake_exe_dir = Path(tempfile.mkdtemp(prefix="nwdata_exe_"))
    fake_meipass = Path(tempfile.mkdtemp(prefix="nwdata_mei_"))
    try:
        with _EnvGuard(NW_WEB_DATA_DIR=None):
            saved = (
                getattr(sys, "_MEIPASS", None),
                getattr(sys, "frozen", None),
                sys.executable,
            )
            sys._MEIPASS = str(fake_meipass)  # type: ignore[attr-defined]
            sys.frozen = True  # type: ignore[attr-defined]
            sys.executable = str(fake_exe_dir / "协议解析工具Web版.exe")
            try:
                check("frozen: is_frozen() 为真", ad.is_frozen())
                check(
                    "frozen: 数据根 = exe 同级 nw_web_data",
                    ad.data_root() == fake_exe_dir / "nw_web_data",
                    str(ad.data_root()),
                )
                check(
                    "frozen: 数据根不在 _MEIPASS 临时目录内",
                    fake_meipass not in ad.data_root().parents,
                    str(ad.data_root()),
                )
            finally:
                if saved[0] is None:
                    del sys._MEIPASS  # type: ignore[attr-defined]
                else:
                    sys._MEIPASS = saved[0]  # type: ignore[attr-defined]
                if saved[1] is None:
                    del sys.frozen  # type: ignore[attr-defined]
                else:
                    sys.frozen = saved[1]  # type: ignore[attr-defined]
                sys.executable = saved[2]
    finally:
        shutil.rmtree(fake_exe_dir, ignore_errors=True)
        shutil.rmtree(fake_meipass, ignore_errors=True)

    # 1.3 都没设（开发态）：回落代码目录 —— 与改造前一致，开发者零感知
    with _EnvGuard(NW_WEB_DATA_DIR=None):
        check(
            "default: 数据根 = 代码目录（现状）",
            ad.data_root() == ad.code_root(),
            str(ad.data_root()),
        )
        check(
            "default: feedback_dir = <repo>/reflex_web/data",
            ad.feedback_dir() == WEB / "data",
        )
        check(
            "default: downloads_dir = <repo>/reflex_web/downloads",
            ad.downloads_dir() == WEB / "downloads",
        )
        check(
            "default: admin_config = <repo>/reflex_web/admin_config.json",
            ad.admin_config_path() == WEB / "admin_config.json",
        )
        check("default: 无需迁移（legacy == 当前）", ad.migrate_legacy() == [])


# ═══════════════════════════════════════════════════════════════
# 2. 单一来源
# ═══════════════════════════════════════════════════════════════


def test_single_source():
    print("\n[2] 所有消费方共用同一来源")
    with (
        tempfile.TemporaryDirectory(prefix="nwdata_ss_") as td,
        _EnvGuard(NW_WEB_DATA_DIR=td),
    ):
        from reflex_web import app_data as ad
        from reflex_web import feedback_model as fm
        from reflex_web import share_model as sm

        check(
            "feedback_model.data_dir() == app_data.feedback_dir()",
            fm.data_dir() == ad.feedback_dir(),
        )
        check(
            "share_model.data_dir() == app_data.feedback_dir()",
            sm.data_dir() == ad.feedback_dir(),
        )
        check(
            "feedback_db 落在数据根内",
            fm.db_path() == ad.feedback_dir() / "feedback.db",
        )
        check(
            "frameshare_db 落在数据根内",
            sm.db_path() == ad.feedback_dir() / "frameshare.db",
        )
        check(
            "反馈截图目录 = <root>/data/uploads/feedback",
            fm.uploads_dir() == ad.uploads_dir(),
        )
        check(
            "uploads_dir 在数据根内",
            str(ad.uploads_dir()).startswith(str(Path(td))),
            str(ad.uploads_dir()),
        )

        # 组合层接线：不许再各自拼路径（源码级守卫，避免依赖内部函数命名）
        src_rw = (WEB / "reflex_web" / "reflex_web.py").read_text(encoding="utf-8")
        check("reflex_web.py 引用 app_data", "app_data." in src_rw)
        check(
            "reflex_web.py 不再自行拼 downloads 目录",
            'here.parent.parent / "downloads"' not in src_rw
            and 'here.parent / "downloads"' not in src_rw,
        )
        check(
            "load_download_info 不再用两候选目录猜测",
            "if not downloads_dir.exists():" not in src_rw,
        )
        src_run = (WEB / "run_app.py").read_text(encoding="utf-8")
        check("run_app.py 引用 app_data", "app_data." in src_run)
        check(
            "run_app.py 中间件不再用 resource_dir 拼数据路径",
            'resource_dir / "downloads"' not in src_run
            and 'resource_dir / "data"' not in src_run,
        )


def test_ensure_dirs():
    print("\n[3] ensure_dirs 建目录")
    with (
        tempfile.TemporaryDirectory(prefix="nwdata_mk_") as td,
        _EnvGuard(NW_WEB_DATA_DIR=td),
    ):
        from reflex_web import app_data as ad

        ad.ensure_dirs()
        check("data/ 已创建", (Path(td) / "data").is_dir())
        check("data/uploads/feedback/ 已创建", ad.uploads_dir().is_dir())
        check("downloads/ 已创建", ad.downloads_dir().is_dir())
        marker = ad.uploads_dir() / "keep.txt"
        marker.write_text("x", encoding="utf-8")
        ad.ensure_dirs()  # 第二次调用
        check(
            "重复调用是幂等（目录仍在且已有文件未被清掉）",
            ad.uploads_dir().is_dir()
            and ad.downloads_dir().is_dir()
            and marker.exists(),
            f"uploads={ad.uploads_dir().is_dir()} downloads={ad.downloads_dir().is_dir()} keep={marker.exists()}",
        )


# ═══════════════════════════════════════════════════════════════
# 4. 旧数据迁移
# ═══════════════════════════════════════════════════════════════


def _make_fake_legacy(root: Path) -> None:
    """在给定「代码根」下造一份旧版树内数据。"""
    (root / "data" / "uploads" / "feedback").mkdir(parents=True, exist_ok=True)
    (root / "data" / "feedback.db").write_text("feedback-db", encoding="utf-8")
    (root / "data" / "frameshare.db").write_text("share-db", encoding="utf-8")
    (root / "data" / "uploads" / "feedback" / "fb_1.png").write_bytes(b"png")
    (root / "downloads" / "archive").mkdir(parents=True, exist_ok=True)
    (root / "downloads" / "南网协议工具.exe").write_bytes(b"exe")
    (root / "admin_config.json").write_text('{"pwd": "x"}', encoding="utf-8")


def test_migration():
    print("\n[4] 迁移（旧树内 → 外置数据根）")
    from reflex_web import app_data as ad

    with tempfile.TemporaryDirectory(prefix="nwdata_mig_") as td:
        fake_code = Path(td) / "code"
        ext_root = Path(td) / "nw_web_data"
        _make_fake_legacy(fake_code)

        saved_code_root = ad.code_root
        try:
            ad.code_root = lambda: fake_code  # type: ignore[assignment]
            with _EnvGuard(NW_WEB_DATA_DIR=str(ext_root)):
                notes = ad.migrate_legacy()
                check(
                    "迁移返回说明行",
                    isinstance(notes, list) and len(notes) > 0,
                    str(notes),
                )
                check(
                    "feedback.db 到位",
                    (ext_root / "data" / "feedback.db").read_text(encoding="utf-8")
                    == "feedback-db",
                )
                check(
                    "frameshare.db 到位", (ext_root / "data" / "frameshare.db").exists()
                )
                check(
                    "截图到位",
                    (ext_root / "data" / "uploads" / "feedback" / "fb_1.png").exists(),
                )
                check(
                    "downloads 到位（含 archive 子目录）",
                    (ext_root / "downloads" / "archive").is_dir(),
                )
                check(
                    "admin_config.json 到位", (ext_root / "admin_config.json").exists()
                )
                check("旧位置已搬空（move 语义）", not (fake_code / "data").exists())

                # 幂等：再调一次不应报错、也不应有任何搬移
                notes2 = ad.migrate_legacy()
                check("第二次调用无操作（幂等）", notes2 == [], str(notes2))

                # 绝不覆盖：目标已有文件时保持原样
                (fake_code / "admin_config.json").write_text(
                    '{"pwd": "NEW"}', encoding="utf-8"
                )
                (fake_code / "data").mkdir(exist_ok=True)
                (fake_code / "data" / "feedback.db").write_text(
                    "MUST-NOT-WIN", encoding="utf-8"
                )
                ad.migrate_legacy()
                check(
                    "目标已存在时不覆盖（现有数据优先）",
                    (ext_root / "data" / "feedback.db").read_text(encoding="utf-8")
                    == "feedback-db",
                    (ext_root / "data" / "feedback.db").read_text(encoding="utf-8"),
                )
                check(
                    "不覆盖 admin_config.json",
                    (ext_root / "admin_config.json").read_text(encoding="utf-8")
                    == '{"pwd": "x"}',
                )
                check(
                    "未覆盖项会被记录并保留在旧位置",
                    (fake_code / "data" / "feedback.db").read_text(encoding="utf-8")
                    == "MUST-NOT-WIN",
                )
        finally:
            ad.code_root = saved_code_root  # type: ignore[assignment]

    # 目标已有「空骨架」时也必须把旧库迁过来（部署若先启动过一次，ensure_dirs 会建出
    # data/uploads/feedback/；若按整目录判断"目标已存在"就跳过，旧库会永远迁不过来）
    with tempfile.TemporaryDirectory(prefix="nwdata_migskeleton_") as td:
        fake_code = Path(td) / "code"
        ext_root = Path(td) / "nw_web_data"
        _make_fake_legacy(fake_code)
        (ext_root / "data" / "uploads" / "feedback").mkdir(
            parents=True
        )  # ensure_dirs 产物
        saved_code_root = ad.code_root
        try:
            ad.code_root = lambda: fake_code  # type: ignore[assignment]
            with _EnvGuard(NW_WEB_DATA_DIR=str(ext_root)):
                ad.migrate_legacy()
                check(
                    "目标有空骨架时旧库仍然迁入",
                    (ext_root / "data" / "feedback.db").exists()
                    and (ext_root / "data" / "frameshare.db").exists(),
                    str(sorted(p.name for p in (ext_root / "data").iterdir())),
                )
                check(
                    "旧库已从旧位置移走",
                    not (fake_code / "data" / "feedback.db").exists(),
                )
                check(
                    "骨架本身保留",
                    (ext_root / "data" / "uploads" / "feedback").is_dir(),
                )
        finally:
            ad.code_root = saved_code_root  # type: ignore[assignment]

    # 失败不抛（源不可读/目标只读时只返回告警）
    with tempfile.TemporaryDirectory(prefix="nwdata_migfail_") as td:
        fake_code = Path(td) / "code"
        _make_fake_legacy(fake_code)
        saved_code_root = ad.code_root
        try:
            ad.code_root = lambda: fake_code  # type: ignore[assignment]
            with _EnvGuard(NW_WEB_DATA_DIR=str(Path(td) / "ext")):
                real_move = shutil.move

                def boom(*a, **k):
                    raise OSError("simulated disk error")

                shutil.move = boom  # type: ignore[assignment]
                try:
                    notes = ad.migrate_legacy()
                    check(
                        "搬移失败不抛异常（返回告警行）",
                        isinstance(notes, list) and len(notes) > 0,
                        str(notes),
                    )
                    check(
                        "告警行提到失败",
                        any(("失败" in n) or ("error" in n.lower()) for n in notes),
                        str(notes),
                    )
                finally:
                    shutil.move = real_move  # type: ignore[assignment]
        finally:
            ad.code_root = saved_code_root  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════
# 5. 部署产物排除运行时数据
# ═══════════════════════════════════════════════════════════════

RUNTIME_ENTRIES = ("data", "admin_config.json")


def test_build_ignore():
    print("\n[5] 部署产物排除运行时数据（保留随包静态资源）")
    import deploy_common

    for modname in ("build_offline_deploy", "build_embedded_deploy"):
        try:
            mod = __import__(modname)
        except Exception as e:  # noqa: BLE001
            check(f"导入 {modname}", False, f"{type(e).__name__}: {e}")
            continue
        # 断言**调用点实参**（不是字符串存在性）：copytree(..., ignore=deploy_common.ignored_web_entries)
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "copytree"
        ]
        uses_shared = any(
            any(
                isinstance(kw.value, ast.Attribute)
                and kw.value.attr == "ignored_web_entries"
                and isinstance(kw.value.value, ast.Name)
                and kw.value.value.id == "deploy_common"
                for kw in c.keywords
                if kw.arg == "ignore"
            )
            for c in calls
        )
        check(f"{modname} 的 copytree 用 deploy_common.ignored_web_entries 作 ignore", uses_shared)
        names = list(RUNTIME_ENTRIES) + [
            "keep.py",
            "sub",
            "web_utils.py",
            "nw_web_data",
        ]
        ignored = deploy_common.ignored_web_entries(deploy_common.WEB_DIR, names)
        check(
            f"{modname}: 忽略 data/admin_config.json/nw_web_data",
            set(RUNTIME_ENTRIES) | {"nw_web_data"} <= ignored,
            str(sorted(ignored)),
        )
        check(
            f"{modname}: 不忽略普通源码与子目录",
            "keep.py" not in ignored
            and "web_utils.py" not in ignored
            and "sub" not in ignored,
        )

    # downloads/ 一级：**白名单**——只有随包资产放行，其余一律不进包
    # （黑名单语义会漏掉 build/dist 这类 PyInstaller 中间产物：实测曾漏约 25MB）
    dl_names = [
        "client_screenshot.png",
        "client_readme.md",
        "README.md",
        "南网协议解析工具1.14.13.exe",
        "version.json",
        "archive",
        "gen_version.py",
        "gen_version_gui.py",
        "o.k..png",
        "build",
        "dist",
        "version生成工具.exe",
        "screenshot_20260916.png",
    ]
    dl_ignored = deploy_common.ignored_web_entries(
        deploy_common.WEB_DIR / "downloads", dl_names
    )
    for gone in (
        "南网协议解析工具1.14.13.exe",
        "version.json",
        "archive",
        "gen_version.py",
        "o.k..png",
        "build",
        "dist",
        "version生成工具.exe",
        "screenshot_20260916.png",
    ):
        check(f"downloads/: 排除 {gone}", gone in dl_ignored)
    for kept in ("client_screenshot.png", "client_readme.md", "README.md"):
        check(f"downloads/: 保留 {kept}", kept not in dl_ignored)
    from reflex_web import app_data as _ad

    check(
        "构建白名单与 app_data.PACKAGED_DOWNLOAD_ASSETS 同源",
        tuple(deploy_common.DOWNLOADS_ASSETS) == tuple(_ad.PACKAGED_DOWNLOAD_ASSETS),
        f"{deploy_common.DOWNLOADS_ASSETS}",
    )

    # 端到端：真跑一次 copytree，确认运行时数据没被复制、随包资源被复制
    with tempfile.TemporaryDirectory(prefix="nwdata_copy_") as td:
        src = Path(td) / "reflex_web"
        dst = Path(td) / "out" / "reflex_web"
        _make_fake_legacy(src)
        (src / "keep.py").write_text("# code", encoding="utf-8")
        (src / "sub").mkdir(exist_ok=True)
        (src / "sub" / "keep2.py").write_text("# code", encoding="utf-8")
        (src / "downloads" / "client_screenshot.png").write_bytes(b"png")
        (src / "downloads" / "version.json").write_text("{}", encoding="utf-8")
        (src / "downloads" / "南网协议解析工具.exe").write_bytes(b"exe")
        shutil.copytree(
            src,
            dst,
            ignore=lambda s_dir, names: deploy_common.ignored_web_entries(
                s_dir, names, web_root=src
            ),
        )
        check("产物含源码 keep.py", (dst / "keep.py").exists())
        check("产物含子目录源码 sub/keep2.py", (dst / "sub" / "keep2.py").exists())
        for entry in RUNTIME_ENTRIES:
            check(f"产物**不含** {entry}", not (dst / entry).exists())
        check("产物不含 exe", not (dst / "downloads" / "南网协议解析工具.exe").exists())
        check(
            "产物不含 version.json", not (dst / "downloads" / "version.json").exists()
        )
        check(
            "产物**保留** client_screenshot.png（首页 Hero / 下载页截图数据源）",
            (dst / "downloads" / "client_screenshot.png").exists(),
        )


# ═══════════════════════════════════════════════════════════════
# 6. 启动脚本 / 迁移脚本
# ═══════════════════════════════════════════════════════════════


def test_launchers():
    print("\n[6] 启动脚本注入数据根 + 迁移脚本随产物生成")
    import deploy_common

    var = deploy_common.ENV_VAR
    check("环境变量名 = NW_WEB_DATA_DIR", var == "NW_WEB_DATA_DIR", var)

    # 6.1 片段本身：三种脚本各一，且「已设则不覆盖」
    cmd = deploy_common.data_env_cmd()
    ps1 = deploy_common.data_env_ps1()
    sh = deploy_common.data_env_sh()
    check("cmd 片段：if not defined 才设值", f"if not defined {var}" in cmd, cmd)
    check(
        "cmd 片段：指向上一级 nw_web_data",
        "%~dp0.." in cmd and "nw_web_data" in cmd,
        cmd,
    )
    check("ps1 片段：仅当未设置时赋值", f"if (-not $env:{var})" in ps1, ps1)
    check("ps1 片段：取上一级目录", "Split-Path -Parent $PSScriptRoot" in ps1, ps1)
    check("sh 片段：仅当未设置时赋值（${VAR:-} 形式，未设不报错）",
          f'if [ -z "${{{var}:-}}" ]' in sh, sh)
    check("sh 片段：export", f"export {var}" in sh, sh)
    # 回归守卫：曾把 f-string 的 {VAR} 当 shell 变量用 → 生成缺 $ 的坏脚本；
    # 且必须用 ${VAR:-} 形式（set -e 下裸 ${VAR} 在未设时会被 set -u 类语义坑到）
    check(
        "sh 片段里是 ${VAR:-} 而非裸 VAR",
        f'"${{{var}:-}}"' in sh and f'"{var}"' not in sh,
        sh,
    )

    # 6.2 真写一次启动脚本（两个部署脚本各一份，Windows 与 Linux 分支都跑）
    import build_embedded_deploy as bed
    import build_offline_deploy as bod

    with tempfile.TemporaryDirectory(prefix="nwdata_launch_") as td:
        out = Path(td) / "deploy"
        out.mkdir()
        bod.write_launchers(out, Path(td) / "fake_python")
        for name in ("start_web.cmd", "start_web.ps1", "start_web.sh"):
            path = out / name
            check(f"offline 生成 {name}", path.exists())
            if path.exists():
                text = path.read_text(encoding="utf-8")
                check(f"offline {name} 含 {var}", var in text)
        check(
            "offline 生成 迁移数据 脚本",
            (out / "迁移数据.cmd").exists() or (out / "迁移数据.sh").exists(),
        )
        note = (out / "部署说明.txt").read_text(encoding="utf-8")
        check(
            "offline 部署说明含数据目录段",
            "运行数据目录" in note and "nw_web_data" in note,
            note[:80],
        )

    for is_win in (True, False):
        with tempfile.TemporaryDirectory(prefix="nwdata_launch2_") as td:
            out = Path(td) / "deploy"
            out.mkdir()
            bed.write_launchers(out, Path(td) / "fake_python", is_win)
            target = "start_web.cmd" if is_win else "start_web.sh"
            path = out / target
            check(
                f"embedded({'win' if is_win else 'linux'}) 生成 {target}", path.exists()
            )
            if path.exists():
                check(
                    f"embedded {target} 含 {var}",
                    var in path.read_text(encoding="utf-8"),
                )
            mig = out / ("迁移数据.cmd" if is_win else "迁移数据.sh")
            check(
                f"embedded({'win' if is_win else 'linux'}) 生成迁移脚本 {mig.name}",
                mig.exists(),
            )
            if mig.exists():
                # .cmd 用 GBK 写（中文控制台友好），.sh 用 UTF-8
                mtext = mig.read_text(
                    encoding="gbk" if mig.suffix == ".cmd" else "utf-8"
                )
                check(f"embedded 迁移脚本含 {var}", var in mtext)
                check(
                    "embedded 迁移脚本有确认提示",
                    ("confirm" in mtext) or ("read -r" in mtext),
                    mtext[:120],
                )


# ═══════════════════════════════════════════════════════════════
# 7. 文档不再承诺「重建时自动保留 data/」
# ═══════════════════════════════════════════════════════════════


def test_asset_fallback():
    print("\n[8] 随包静态资源回落（截图 / README）")
    from reflex_web import app_data as ad

    with tempfile.TemporaryDirectory(prefix="nwdata_asset_") as td:
        root = Path(td) / "nw_web_data"
        root.mkdir()
        fake_code = Path(td) / "code"
        (fake_code / "downloads").mkdir(parents=True)
        (fake_code / "downloads" / "client_screenshot.png").write_bytes(b"png")
        saved = ad.code_root
        try:
            ad.code_root = lambda: fake_code  # type: ignore[assignment]
            with _EnvGuard(NW_WEB_DATA_DIR=str(root)):
                p1 = ad.resolve_download_asset("client_screenshot.png")
                check(
                    "数据根缺失时回落到随包资源",
                    p1 == fake_code / "downloads" / "client_screenshot.png"
                    and p1.exists(),
                    str(p1),
                )
                (root / "downloads").mkdir(parents=True, exist_ok=True)
                (root / "downloads" / "client_screenshot.png").write_bytes(b"new")
                p2 = ad.resolve_download_asset("client_screenshot.png")
                check(
                    "数据根优先于随包资源（运维可覆盖）",
                    p2 == root / "downloads" / "client_screenshot.png"
                    and p2.read_bytes() == b"new",
                    str(p2),
                )
                p3 = ad.resolve_download_asset("nope.png")
                check(
                    "都不存在时返回数据根候选路径（调用方按存在性判断）",
                    p3 == root / "downloads" / "nope.png",
                    str(p3),
                )
        finally:
            ad.code_root = saved  # type: ignore[assignment]



def test_migration_artifacts_and_scripts():
    """F1/F3/F4/F6/F7①/F8 的守卫：迁移只搬运行时产物、生成的脚本真能跑、启动接线顺序正确。"""
    print("\n[9] 迁移只搬运行时产物 + 生成脚本可用性 + 启动接线")
    import deploy_common
    from reflex_web import app_data as ad

    # F3：downloads 里的随包资产不搬进数据根（否则后续版本的随包更新会被永久遮蔽）
    with tempfile.TemporaryDirectory(prefix="nwdata_asset_mig_") as td:
        fake_code = Path(td) / "code"
        ext_root = Path(td) / "nw_web_data"
        (fake_code / "downloads").mkdir(parents=True)
        (fake_code / "downloads" / "client_screenshot.png").write_bytes(b"PACKAGED")
        (fake_code / "downloads" / "client_readme.md").write_text("PACKAGED-README", encoding="utf-8")
        (fake_code / "downloads" / "南网协议工具.exe").write_bytes(b"exe")
        (fake_code / "downloads" / "version.json").write_text("{}", encoding="utf-8")
        saved = ad.code_root
        try:
            ad.code_root = lambda: fake_code  # type: ignore[assignment]
            with _EnvGuard(NW_WEB_DATA_DIR=str(ext_root)):
                ad.migrate_legacy()
                check(
                    "下载页 exe 已迁到数据根",
                    (ext_root / "downloads" / "南网协议工具.exe").exists(),
                )
                check(
                    "version.json 已迁到数据根",
                    (ext_root / "downloads" / "version.json").exists(),
                )
                check(
                    "随包截图**未**被搬进数据根（避免遮蔽后续版本更新）",
                    not (ext_root / "downloads" / "client_screenshot.png").exists(),
                )
                check(
                    "随包截图仍留在代码树（作为回落资源）",
                    (fake_code / "downloads" / "client_screenshot.png").read_bytes() == b"PACKAGED",
                )
                check(
                    "resolve_download_asset 仍取到随包那份",
                    ad.resolve_download_asset("client_screenshot.png").read_bytes() == b"PACKAGED",
                )
        finally:
            ad.code_root = saved  # type: ignore[assignment]

    # F1/F4/F6：生成的 POSIX 迁移脚本可执行（无 unbound variable）、cmd 版有致命码判定、.cmd 用 GBK
    sh_text = deploy_common.migrate_script_posix()
    check("posix 迁移脚本不用 set -u（未设变量时会立即中止）", "set -eu" not in sh_text and "set -e\n" in sh_text)
    check("posix 迁移脚本用 ${VAR:-} 形式取默认值", "${NW_WEB_DATA_DIR:-}" in sh_text, sh_text[:120])
    cmd_text = deploy_common.migrate_script_windows()
    check("cmd 迁移脚本判 robocopy 致命码（>=8）", "if errorlevel 8" in cmd_text, cmd_text[:120])
    check("cmd 迁移脚本失败时给出非零退出与警告", 'exit /b 1' in cmd_text and "不要" in cmd_text)

    with tempfile.TemporaryDirectory(prefix="nwdata_script_") as td:
        out = Path(td) / "deploy"
        out.mkdir()
        mig_cmd = deploy_common.write_migration_helper(out, is_windows=True)
        raw = mig_cmd.read_bytes()
        check("迁移数据.cmd 用 GBK 写（中文控制台不乱码）", "确认迁移".encode("gbk") in raw)
        check("迁移数据.cmd 不是 UTF-8 无 BOM", not raw.startswith(b"\xef\xbb\xbf"))

        # 真跑一次 POSIX 版：变量**未设**时也必须能跑完并完成搬迁
        if shutil.which("sh"):
            dep = Path(td) / "old_deploy"
            (dep / "reflex_web" / "data").mkdir(parents=True)
            (dep / "reflex_web" / "data" / "feedback.db").write_text("db", encoding="utf-8")
            (dep / "reflex_web" / "admin_config.json").write_text("{}", encoding="utf-8")
            mig_sh = deploy_common.write_migration_helper(dep, is_windows=False)
            env = {k: v for k, v in os.environ.items() if k != "NW_WEB_DATA_DIR"}
            # 注意：必须用 bytes 传 stdin —— text=True 在 Windows 会把 "y\n" 译成
            # "y\r\n"，shell 的 read 拿到 "y\r" 匹配不上 y，脚本会走「已取消」分支
            r = subprocess.run(
                ["sh", str(mig_sh)], cwd=str(dep), env=env, input=b"y\n",
                capture_output=True,
            )
            r_stdout = r.stdout.decode("utf-8", "ignore")
            r_stderr = r.stderr.decode("utf-8", "ignore")
            check(
                "未设 NW_WEB_DATA_DIR 时迁移脚本仍能运行（无 unbound variable）",
                r.returncode == 0 and "unbound variable" not in r_stderr,
                f"rc={r.returncode} err={r_stderr[:120]}",
            )
            check(
                "脚本把旧数据搬到了部署目录上一级的 nw_web_data",
                (dep.parent / "nw_web_data" / "data" / "feedback.db").exists(),
                str(sorted(p.name for p in dep.parent.iterdir())),
            )
        else:
            check("（本机无 sh，跳过 POSIX 迁移脚本真跑，仅做静态断言）", True)

    # F7①/F8：启动接线顺序 + 数据目录不可写的可执行指引
    src_run = (WEB / "run_app.py").read_text(encoding="utf-8")
    i_mig = src_run.find("migrate_legacy()")
    i_ensure = src_run.find("ensure_dirs(")
    check("run_app 先迁移再建目录骨架（migrate_legacy 在 ensure_dirs 之前）",
          0 <= i_mig < i_ensure, f"migrate@{i_mig} ensure@{i_ensure}")
    check("run_app 数据块有 OSError 兜底（给出 NW_WEB_DATA_DIR 指引而非裸栈）",
          "数据目录不可写" in src_run and "SystemExit(2)" in src_run)


def test_docs():
    print("\n[7] 文档与承诺一致")
    doc = (WEB / "离线部署.md").read_text(encoding="utf-8")
    check("部署文档提到 NW_WEB_DATA_DIR", "NW_WEB_DATA_DIR" in doc)
    check("部署文档说明数据在部署目录之外", "上一级" in doc and "nw_web_data" in doc)
    check("部署文档给出升级步骤", "升级" in doc)
    check(
        "部署文档不再声称「重建部署目录都会自动保留 data/」",
        "重建部署目录" not in doc,
    )


def main():
    print("=" * 62)
    print("Web 运行时数据外置回归测试")
    print("=" * 62)
    test_resolution()
    test_single_source()
    test_ensure_dirs()
    test_migration()
    test_build_ignore()
    test_launchers()
    test_asset_fallback()
    test_migration_artifacts_and_scripts()
    test_docs()
    print("\n" + "=" * 62)
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"全部通过（{PASS} 项）✓")
    print("=" * 62)


if __name__ == "__main__":
    main()
