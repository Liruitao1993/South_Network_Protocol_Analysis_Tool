# -*- coding: utf-8 -*-
"""协议注册表：集中管理解析器/校验器映射，避免各 tab 重复定义"""
from typing import Dict, Type, Tuple


def _lazy_import_parsers() -> Dict[int, Type]:
    """延迟导入解析器类，避免启动时加载所有协议模块"""
    from protocol_parser import ProtocolFrameParser
    from plc_rf_parser import PLCRFProtocolParser
    from hdlc_parser import HDLCParser
    from dlt645_parser import DLT645Parser
    from gdw10376_parser import GDW10376Parser
    from dl_t698_45_parser import DLT69845Parser
    from csg_new_gen_parser import CSGNewGenParser
    return {
        0: ProtocolFrameParser,
        1: PLCRFProtocolParser,
        2: HDLCParser,
        3: HDLCParser,   # DLMS-APDU(国网) 复用
        4: HDLCParser,   # DLMS Wrapper
        5: HDLCParser,   # DLMS-APDU 裸报文
        6: DLT645Parser,
        7: GDW10376Parser,
        8: DLT69845Parser,
        9: CSGNewGenParser,
    }


def _lazy_import_validators() -> Dict[int, Type]:
    from validator import (
        NWValidator, PLCRFValidator, HDLCValidator,
        DLT645Validator, GDWValidator, DLT69845Validator, CSGNewGenValidator,
    )
    return {
        0: NWValidator,
        1: PLCRFValidator,
        2: HDLCValidator,
        3: HDLCValidator,
        4: HDLCValidator,
        5: HDLCValidator,
        6: DLT645Validator,
        7: GDWValidator,
        8: DLT69845Validator,
        9: CSGNewGenValidator,
    }


_parser_map: Dict[int, Type] = None
_validator_map: Dict[int, Type] = None


def get_parser_map() -> Dict[int, Type]:
    global _parser_map
    if _parser_map is None:
        _parser_map = _lazy_import_parsers()
    return _parser_map


def get_validator_map() -> Dict[int, Type]:
    global _validator_map
    if _validator_map is None:
        _validator_map = _lazy_import_validators()
    return _validator_map


def make_parser(protocol_idx: int):
    return get_parser_map()[protocol_idx]()


def make_validator(protocol_idx: int):
    return get_validator_map()[protocol_idx]()
