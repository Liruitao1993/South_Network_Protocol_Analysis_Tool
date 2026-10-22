# -*- mode: python ; coding: utf-8 -*-
# 南网协议解析工具 —— **单文件（onefile）** 便携版构建配置
#
# 产物：dist/南网协议解析工具_v{APP_VERSION}_{YYYYMMDDHHMMSS}.exe
#   · 版本号取 main_gui.py:APP_VERSION（唯一版本源），与窗口标题天然对齐
#   · 时间戳精确到秒，区分同版本多次编译
#
# 版本资源 / 应用清单 / 依赖清单都在 `pyinstaller_meta.py`（与 onedir 规格共用同一份，
# 避免两边各写一套而漂移）。本文件只保留「单文件形态」特有的部分。
#
# ⚠ 单文件形态的固有代价（改之前先读 AGENTS §2.6）：
#   每次运行都要把内嵌依赖解到 %TEMP%\_MEIxxxxxx 再执行 —— 与「释放器」行为同构，
#   是杀软启发式与 360 拦截的主要结构性原因之一；启动也比文件夹形态慢几秒。
#   对外分发若被拦得厉害，改用 `协议解析工具_onedir.spec` + 安装包（见该规格）。

import sys
from datetime import datetime
from pathlib import Path

_spec_root = Path(SPECPATH)
if str(_spec_root) not in sys.path:
    sys.path.insert(0, str(_spec_root))

import pyinstaller_meta as meta  # noqa: E402 —— 同目录的共享元数据（单一来源）

# 1. 版本与产物名
_app_version = meta.read_app_version(_spec_root)
_build_ts = datetime.now().strftime("%Y%m%d%H%M%S")
_exe_name = meta.onefile_exe_name(_app_version, _build_ts)

# 2. 蓝牙（bleak）依赖收集
# Windows 上的 BLE 后端通过 winrt 命名空间包分发（winrt.windows.devices.bluetooth.*，
# 数量多且随版本变动），逐个手写 hiddenimports 必漏 —— 用 collect_submodules 全收。
# 未安装 bleak 时返回空表：蓝牙页自动降级为「提示安装」，不影响其余页面。
_ble_imports = []
try:
    from PyInstaller.utils.hooks import collect_submodules

    for _pkg in ("bleak", "winrt"):
        try:
            _ble_imports.extend(collect_submodules(_pkg))
        except Exception:
            pass
except Exception:
    pass

# 3. 版本资源（FileVersion/ProductVersion 与 APP_VERSION 对齐）+ 应用清单
_version_info_file = _spec_root / "_version_info_gen.txt"
_version_info_file.write_text(
    meta.version_info_text(_app_version, f"{_exe_name}.exe"), encoding="utf-8")
print(f"==> 构建目标(onefile): {_exe_name}.exe (APP_VERSION={_app_version})")

_manifest_xml = meta.manifest_xml(_app_version)

a = Analysis(
    ['main_gui.py'],
    pathex=[SPECPATH],
    binaries=[],
    datas=list(meta.DATAS),
    hiddenimports=list(meta.HIDDENIMPORTS) + _ble_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=list(meta.EXCLUDES),
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=_exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX 压缩：**显式关闭**（压缩壳是杀毒启发式的重点特征；体积收益不值得这种风险）
    upx=False,
    upx_exclude=[
        'vcruntime140.dll',
        'python313.dll',
        'openpyxl',
    ],
    runtime_tmpdir=None,
    console=False,  # GUI 模式，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
    version=str(_version_info_file),
    manifest=_manifest_xml,
)
