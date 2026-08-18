# -*- mode: python ; coding: utf-8 -*-
# 南网协议解析工具 - 单文件 EXE 构建配置
# 包含所有依赖：openpyxl, enhanced_export 等（pandas 已改为可选依赖）

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
        ('scripts', 'scripts'),  # Python 脚本预处理示例脚本
        # EB 数据标识 645/698 帧生成器：运行时动态 import 的纯逻辑模块
        ('reflex_web/frame_gen_utils.py', '.'),  # build_eb_698_frame / build_dlt698_sa
        ('gdw_eb_di_fields.py', '.'),  # EB_DI_FIELDS / encode_eb_di_data
        ('gdw_eb_di_lookup.py', '.'),  # get_eb_di_lookup
    ],
    hiddenimports=[
        # PySide6 核心模块
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        # 数据处理依赖
        'openpyxl',
        'openpyxl.cell',
        'openpyxl.styles',
        'openpyxl.utils',
        'openpyxl.workbook',
        'openpyxl.writer.excel',
        'pandas',
        'pandas.core',
        # 项目内部模块
        'enhanced_export',
        'system_integration',
        'system_integration.sys_tray',
        'system_integration.global_hotkey',
        'system_integration.registry_menu',
        'system_integration.single_instance',
        'system_integration.system_settings',
        'system_integration.npp_integration',
        'system_integration.clipboard_monitor',
        'system_integration.parse_prompt_dialog',
        'protocol_parser',
        'plc_rf_parser',
        'hdlc_parser',
        'dlt645_parser',
        'gdw10376_parser',
        'dl_t698_45_parser',
        'csg_new_gen_parser',
        'gw_new_gen_parser',
        'gw_new_gen_cmd_payloads',
        'gw_new_gen_mme_parser',
        'hdc10_parser',
        'hdc10_mme_parser',
        'validator.hdc10_validator',
        'obis_lookup',
        'command_lookup',
        'dlt645_di_lookup',
        'gdw_afn_lookup',
        'frame_gen_widget',
        'gdw_eb_di_fields',  # EB 数据标识字段定义（被 frame_gen_widget 静态 import）
        'gdw_eb_di_lookup',  # EB 数据标识查询（被 frame_gen_widget 静态 import）
        'archive_widget',
        'topology_widget',
        'preset_buttons',
        'test_plan_widget',
        'diff_widget',
        'serial_worker',
        'gui_utils',
        'frame_diff_engine',
        'lua_script_engine',
        'py_script_engine',  # Python 脚本预处理引擎
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
        # 以下为未使用的库，排除以减小体积
        'sympy',
        'pygments',
        'xlsxwriter',
        'jinja2',
        'cryptography',
        'chardet',
        'mpmath',
        '_pytest',
        # 注意：pandas/numpy 不能被排除，否则批量解析的 Excel/CSV 导出功能会失效
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
    version='version_info_nw.txt',
)
