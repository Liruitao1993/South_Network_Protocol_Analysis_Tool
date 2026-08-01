# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('.web\\build\\client', 'web_static\\build\\client'), ('..\\custom_di.json', '.'), ('..\\dlt645_di.json', '.'), ('..\\gdw_custom_afn.json', '.'), ('..\\command.json', '.'), ('rxconfig.py', '.')]
binaries = []
hiddenimports = ['protocol_parser', 'gdw10376_parser', 'plc_rf_parser', 'hdlc_parser', 'dlms_deep_parser', 'dlt645_parser', 'csg_new_gen_parser', 'gw_new_gen_parser', 'dl_t698_45_parser', 'validator', 'reflex_web.reflex_web', 'reflex_web.web_utils', 'reflex_web.lookup_utils']
tmp_ret = collect_all('reflex_base')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('reflex')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('reflex_components_core')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('reflex_components_radix')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['run_app.py'],
    pathex=['E:\\python\\南网解析工具', 'E:\\python\\南网解析工具\\reflex_web'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='debug_web',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='debug_web',
)
