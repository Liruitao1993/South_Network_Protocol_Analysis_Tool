# -*- mode: python ; coding: utf-8 -*-
# 南网协议解析工具 - 单文件 EXE 构建配置
# 包含所有依赖：pandas, openpyxl, enhanced_export 等

a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('custom_di.json', '.'),
        ('dlt645_di.json', '.'),
        ('gdw_custom_afn.json', '.'),
        ('icons', 'icons'),
        ('enhanced_export.py', '.'),  # 增强导出模块
    ],
    hiddenimports=[
        # PySide6 核心模块
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        # 数据处理依赖
        'pandas',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.np_datetime',
        'openpyxl',
        'openpyxl.cell',
        'openpyxl.styles',
        'openpyxl.utils',
        'openpyxl.workbook',
        'openpyxl.writer.excel',
        # 项目内部模块
        'enhanced_export',
        'protocol_parser',
        'plc_rf_parser',
        'hdlc_parser',
        'dlt645_parser',
        'gdw10376_parser',
        'dl_t698_45_parser',
        'csg_new_gen_parser',
        'obis_lookup',
        'command_lookup',
        'dlt645_di_lookup',
        'gdw_afn_lookup',
        'frame_gen_widget',
        'archive_widget',
        'topology_widget',
        'preset_buttons',
        'test_plan_widget',
        'diff_widget',
        'serial_worker',
        'gui_utils',
        'frame_diff_engine',
        'lua_script_engine',
        # 可选依赖
        'crcmod',
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5',
        'PyQt6',
        'matplotlib',
        'scipy',
        'PIL',
        'tkinter',
        '_tkinter',
        'IPython',
        'notebook',
        'jupyter',
        'pytest',
        'unittest',
    ],
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
    name='南网协议解析工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'vcruntime140.dll',
        'python313.dll',
        'pandas',
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
)
