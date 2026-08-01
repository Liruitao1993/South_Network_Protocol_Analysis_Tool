# -*- mode: python ; coding: utf-8 -*-
"""
南网协议解析工具 - Reflex Web 版 单文件 EXE 构建配置

用法:
    cd reflex_web
    pyinstaller reflex_web_exe.spec --clean

输出: dist/协议解析工具Web版.exe

启动:
    协议解析工具Web版.exe --port 8080 --host 0.0.0.0
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# === 路径配置 ===
# 项目根目录（南网解析工具/）
PROJECT_ROOT = Path(SPECPATH).resolve().parent
# reflex_web 子目录
REFLEX_WEB_DIR = Path(SPECPATH).resolve()
# 前端构建产物
WEB_BUILD_DIR = REFLEX_WEB_DIR / ".web" / "build" / "client"

if not WEB_BUILD_DIR.exists():
    raise RuntimeError(
        f"前端构建产物不存在: {WEB_BUILD_DIR}\n"
        "请先运行: cd reflex_web && reflex export --frontend-only --env prod --no-zip"
    )

# === 数据文件列表 ===
datas = []

# 0. Reflex 框架数据文件（模板、静态资源等）
for pkg in ["reflex_base", "reflex", "reflex_components_radix", "reflex_components_core"]:
    try:
        pkg_datas = collect_data_files(pkg, include_py_files=False)
        datas.extend(pkg_datas)
    except Exception:
        pass

# 1. 前端静态文件 → _MEIPASS/web_static/build/client/
# datas 元组格式: (源路径, 目标相对路径)
datas.append((str(WEB_BUILD_DIR), "web_static/build/client"))

# 2. 数据 JSON 文件（协议解析器需要）
json_files = [
    "custom_di.json",
    "dlt645_di.json",
    "gdw_custom_afn.json",
    "command.json",
    "NW_command.json",
]
for jf in json_files:
    src = PROJECT_ROOT / jf
    if src.exists():
        datas.append((str(src), "."))

# 3. rxconfig.py（Reflex 需要）
datas.append((str(REFLEX_WEB_DIR / "rxconfig.py"), "."))

# === hidden imports ===
# Reflex 使用 lazy loader，大量模块是动态导入的，用 collect_submodules 批量收集
reflex_hidden = []
for pkg in [
    "reflex",
    "reflex_base",
    "reflex_components_core",
    "reflex_components_radix",
    # anyio 是 starlette 的依赖，后端模块是动态导入的
    "anyio",
]:
    try:
        reflex_hidden.extend(collect_submodules(pkg))
    except Exception:
        pass

hiddenimports = reflex_hidden + [
    # ---- Web 框架（补齐动态导入） ----
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "websockets.legacy.server",
    "websockets.legacy.client",
    "starlette.websockets",
    "python_multipart",

    # ---- 数据序列化 ----
    "orjson",
    "msgpack",
    "pydantic_settings",

    # ---- 模板引擎 ----
    "jinja2",

    # ---- 工具库 ----
    "watchfiles",
    "rich",
    "typer",
    "aiofiles",
    "distro",
    "platformdirs",

    # ---- 协议解析依赖 ----
    "crcmod",
    "bs4",
    "lxml",

    # ---- 项目模块：协议解析器 ----
    "protocol_parser",
    "protocol_tool",
    "gdw10376_parser",
    "gdw10376_tool",
    "plc_rf_parser",
    "hdlc_parser",
    "dlms_deep_parser",
    "dlms_parser",
    "dlt645_parser",
    "csg_new_gen_parser",
    "gw_new_gen_parser",
    "gw_new_gen_mme_parser",
    "dl_t698_45_parser",
    "dl_t698_45_apdu_parser",
    "lme_info_entry_parser",

    # ---- 项目模块：查找表 ----
    "obis_lookup",
    "command_lookup",
    "dlt645_di_lookup",
    "gdw_afn_lookup",
    "dl_t698_45_oi_lookup",

    # ---- 项目模块：校验器 ----
    "validator",
    "validator.base",
    "validator.nw_validator",
    "validator.gdw_validator",
    "validator.hdlc_validator",
    "validator.plc_rf_validator",
    "validator.dlt645_validator",
    "validator.dl_t698_45_validator",
    "validator.csg_new_gen_validator",
    "validator.gw_new_gen_validator",

    # ---- 项目模块：Reflex Web ----
    "reflex_web",
    "reflex_web.reflex_web",
    "reflex_web.web_utils",
    "reflex_web.lookup_utils",
]

# === 排除不需要的模块（减小体积） ===
excludes = [
    # GUI 相关（Web 版不需要 PySide6）
    "PySide6",
    "PyQt5",
    "PyQt6",
    # 测试框架
    "pytest",
    "unittest",
    # 大数据库（如果用不到可以排除，先保留以防万一）
    # "numpy",      # pydantic 可能依赖
    # "pandas",     # 暂不需要
    # 其他
    "matplotlib",
    "scipy",
    "PIL",
    "tkinter",
    "_tkinter",
    "IPython",
    "notebook",
    "jupyter",
    "tornado",
]

# === Analysis ===
a = Analysis(
    [str(REFLEX_WEB_DIR / "run_app.py")],
    pathex=[
        str(PROJECT_ROOT),       # 项目根（协议解析器在这）
        str(REFLEX_WEB_DIR),     # reflex_web 目录
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# === PYZ ===
pyz = PYZ(a.pure)

# === EXE ===
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='协议解析工具Web版',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Reflex 体积大，UPX 压缩时间很长且容易出问题，先关闭
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Web 服务器需要控制台输出日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='app_icon.ico',  # 没有图标先注释
)
