# -*- mode: python ; coding: utf-8 -*-
# 南网协议解析工具 —— **文件夹（onedir）** 构建配置（安装包用它）
#
# 产物：dist/协议解析工具/协议解析工具.exe（+ 同目录的 _internal/ 依赖）
#   · exe 名必须是 `协议解析工具` —— `南网解析工具.iss` 的 MyAppExeName 就是它，
#     安装脚本 `Source: "...\dist\协议解析工具\{#MyAppExeName}"` 直接取这个文件。
#   · 版本资源 / 应用清单 / 依赖清单与 onefile 规格共用 `pyinstaller_meta.py`。
#
# 为什么要有这个规格（AGENTS §2.6）：单文件 exe 每次运行都要解压到 %TEMP%\_MEIxxxxxx
# 再执行，与「释放器」同构 —— 这是被 Defender/360 启发式拦截的主要结构性原因之一；
# 文件夹形态没有自解压动作，启动快 2~5 秒、内存更稳、被拦概率显著更低。
# 对外分发走「onedir 构建 + Inno Setup 安装包」这条链，比直接甩一个未签名 onefile 稳得多。
#
# 用法：
#   pyinstaller 协议解析工具_onedir.spec --noconfirm
#   dist\协议解析工具\协议解析工具.exe --self-test     # 返回码 0 = 打包合格
#   然后编译 南网解析工具.iss

import sys
from pathlib import Path

_spec_root = Path(SPECPATH)
if str(_spec_root) not in sys.path:
    sys.path.insert(0, str(_spec_root))

import pyinstaller_meta as meta  # noqa: E402 —— 同目录的共享元数据（单一来源）

_app_version = meta.read_app_version(_spec_root)
_exe_name = meta.ONEDIR_EXE_NAME           # 必须与 .iss 的 MyAppExeName 一致

# 蓝牙（bleak/winrt）命名空间包全收；未安装时为空表（蓝牙页降级提示）
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

_version_info_file = _spec_root / "_version_info_gen.txt"
_version_info_file.write_text(
    meta.version_info_text(_app_version, f"{_exe_name}.exe"), encoding="utf-8")
print(f"==> 构建目标(onedir): {_exe_name}\\{_exe_name}.exe (APP_VERSION={_app_version})")

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
    [],
    exclude_binaries=True,          # onedir：依赖交给 COLLECT，不塞进 exe
    name=_exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # 同 onefile：不压缩，避免加壳特征
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
    version=str(_version_info_file),
    manifest=_manifest_xml,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=_exe_name,                 # → dist/协议解析工具/
)
