"""协议验证引擎模块"""

from .base import ValidationResult, CheckItem, CheckLevel, BaseValidator
from .nw_validator import NWValidator
from .gdw_validator import GDWValidator
from .hdlc_validator import HDLCValidator
from .plc_rf_validator import PLCRFValidator
from .dlt645_validator import DLT645Validator
from .dl_t698_45_validator import DLT69845Validator
from .csg_new_gen_validator import CSGNewGenValidator
from .gw_new_gen_validator import GWNewGenValidator
from .hdc10_validator import HDC10Validator

# 说明：protocol_registry.make_validator 用 importlib 按字符串加载校验器类，
# PyInstaller 无法静态分析该路径 —— 在此显式 re-export 让打包器的模块图
# 通过本文件的静态 import 收集到全部 12 个协议校验器（含 gw_new_gen / hdc10）。
__all__ = [
    'ValidationResult', 'CheckItem', 'CheckLevel', 'BaseValidator',
    'NWValidator', 'GDWValidator', 'HDLCValidator', 'PLCRFValidator', 'DLT645Validator',
    'DLT69845Validator', 'CSGNewGenValidator', 'GWNewGenValidator', 'HDC10Validator'
]
