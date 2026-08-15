# -*- coding: utf-8 -*-
"""查询功能工具

为 Reflex Web 版提供统一的查询接口。
按协议索引返回对应查询数据。
"""
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════
# 协议 → 查询类型 映射
# ═══════════════════════════════════════════════════════════════

# 每种协议对应的查询类型和列定义
QUERY_CONFIG = {
    0: {  # 南网
        "title": "DI 查询",
        "columns": ["DI3", "DI2", "DI1", "DI0", "AFN", "中文含义"],
    },
    1: {  # PLC RF
        "title": "命令字查询",
        "columns": ["命令字", "名称", "说明"],
    },
    2: {  # HDLC/国网DLMS
        "title": "OBIS 查询",
        "columns": ["OBIS码", "对象名称", "对象类型", "访问属性"],
    },
    3: {  # DLMS-APDU(国网)
        "title": "OBIS 查询",
        "columns": ["OBIS码", "对象名称", "对象类型", "访问属性"],
    },
    4: {  # DLMS Wrapper
        "title": "OBIS 查询",
        "columns": ["OBIS码", "对象名称", "对象类型", "访问属性"],
    },
    5: {  # DLMS-APDU
        "title": "OBIS 查询",
        "columns": ["OBIS码", "对象名称", "对象类型", "访问属性"],
    },
    6: {  # DLT645
        "title": "DI 查询",
        "columns": ["DI编码", "名称", "单位", "数据类型", "说明"],
    },
    7: {  # 国网
        "title": "AFN+Fn 查询",
        "columns": ["AFN", "AFN名称", "Fn", "功能说明"],
    },
    8: {  # 698.45
        "title": "OI 查询",
        "columns": ["OI", "对象名称", "属性", "方法", "说明"],
    },
    9: {  # 新一代载波
        "title": "业务标识查询",
        "columns": ["类别", "代码", "名称"],
    },
    10: {  # 国网新一代
        "title": "报文ID查询",
        "columns": ["类别", "代码", "名称"],
    },
    11: {  # HDC 1.0 双模互联互通
        "title": "报文ID/端口查询",
        "columns": ["类别", "代码", "名称"],
    },
}


def get_query_config(protocol_index: int) -> Dict[str, Any]:
    """获取当前协议的查询配置"""
    return QUERY_CONFIG.get(protocol_index, QUERY_CONFIG[0])


# ═══════════════════════════════════════════════════════════════
# 查询实现
# ═══════════════════════════════════════════════════════════════

def _search_south_di(keyword: str = "") -> List[List[str]]:
    """南网 DI 查询"""
    try:
        from protocol_parser import ProtocolFrameParser
        parser = ProtocolFrameParser()
        results = []
        keyword_upper = keyword.upper().strip()
        for (di3, di2, di1, di0), desc in parser.DI_COMBINATION_MAP.items():
            # 计算 AFN
            afn = (di3 & 0x0F)
            afn_hex = f"{afn:02X}H"
            row = [f"{di3:02X}", f"{di2:02X}", f"{di1:02X}", f"{di0:02X}", afn_hex, desc]

            if not keyword_upper:
                results.append(row)
                continue

            # 关键词匹配
            match = False
            for cell in row:
                if keyword_upper in cell.upper():
                    match = True
                    break
            if match:
                results.append(row)
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", "", "", "", ""]]


def _search_plc_cmd(keyword: str = "") -> List[List[str]]:
    """PLC RF 命令字查询"""
    try:
        from command_lookup import get_command_lookup
        lookup = get_command_lookup()
        if keyword.strip():
            data = lookup.search(keyword)
        else:
            data = lookup._data
        results = []
        for item in data:
            code_int = item[0]
            name = item[1]
            desc = item[2] if len(item) > 2 else ""
            results.append([f"{code_int:04X}", name, desc])
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", ""]]


def _obis_type_from_a(a_val: int) -> str:
    """从 OBIS A 值推断对象类型"""
    type_map = {
        0: "Abstract Object",
        1: "Data",
        2: "Register",
        3: "Extended Register",
        4: "Demand Register",
        5: "Register Activation",
        6: "Profile Generic",
        7: "Clock",
        8: "Script Table",
        9: "Schedule",
        10: "Special Days Table",
        11: "Assortment",
        12: "Octet String",
        15: "Data Protection",
    }
    return type_map.get(a_val, f"Unknown({a_val})")


def _search_obis(keyword: str = "") -> List[List[str]]:
    """OBIS 查询"""
    try:
        from obis_lookup import get_obis_lookup
        lookup = get_obis_lookup()
        if keyword.strip():
            data = lookup.search(keyword)
        else:
            data = lookup._data
        results = []
        for item in data:
            obis_tuple = item[0]
            name = item[1]
            desc = item[2] if len(item) > 2 else ""
            obis_str = ".".join(str(x) for x in obis_tuple)
            obj_type = _obis_type_from_a(obis_tuple[0]) if isinstance(obis_tuple, tuple) and len(obis_tuple) > 0 else ""
            access_attr = "-"
            results.append([obis_str, name, obj_type, access_attr])
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", "", ""]]


def _search_dlt645_di(keyword: str = "") -> List[List[str]]:
    """DLT645 DI 查询"""
    try:
        from dlt645_di_lookup import get_dlt645_di_lookup
        lookup = get_dlt645_di_lookup()
        if keyword.strip():
            data = lookup.search(keyword)
        else:
            data = lookup.data
        results = []
        for item in data:
            di_code = item[0]
            name = item[1]
            unit = item[2] if len(item) > 2 else ""
            data_type = item[3] if len(item) > 3 else ""
            desc = item[4] if len(item) > 4 else ""
            results.append([di_code, name, unit, data_type, desc])
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", "", "", ""]]


def _search_gdw_afn(keyword: str = "") -> List[List[str]]:
    """国网 AFN+Fn 查询"""
    try:
        from gdw_afn_lookup import get_gdw_afn_lookup
        lookup = get_gdw_afn_lookup()
        if keyword.strip():
            data = lookup.search(keyword)
        else:
            data = lookup.data
        results = []
        for item in data:
            afn = item[0]
            afn_name = item[1]
            fn = item[2]
            fn_name = item[3] if len(item) > 3 else ""
            results.append([f"{afn:02X}H", afn_name, f"F{fn:02d}", fn_name])
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", "", ""]]


def _search_698_oi(keyword: str = "") -> List[List[str]]:
    """698.45 OI 查询"""
    try:
        from dl_t698_45_oi_lookup import OILookup
        lookup = OILookup()
        keyword_upper = keyword.upper().strip()
        results = []

        # OI_NAME_MAP 是 oi->名称 的映射
        oi_map = getattr(lookup, 'OI_NAME_MAP', {})
        for oi_val, name in oi_map.items():
            row = [f"0x{oi_val:04X}", name, "-", "-", ""]
            if not keyword_upper:
                results.append(row)
                continue
            match = any(keyword_upper in cell.upper() for cell in row)
            if match:
                results.append(row)
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", "", "", ""]]


def _search_csg_service(keyword: str = "") -> List[List[str]]:
    """新一代载波业务标识查询"""
    try:
        from csg_new_gen_parser import (
            MSG_PORT_MAP, MSG_ID_MAP, FRAME_TYPE_MAP, DIRECTION_MAP,
            PRM_MAP, RESPONSE_MAP, EXTENSION_MAP,
            CONFIRM_SERVICE_MAP, DATA_SERVICE_MAP,
            CMD_FUNC_SERVICE_MAP, CMD_COMM_SERVICE_MAP,
            MPDU_VERSION_MAP,
        )

        keyword_upper = keyword.upper().strip()
        results = []

        # 汇总所有 MAP
        all_maps = [
            ("报文端口号", MSG_PORT_MAP),
            ("报文标识符", MSG_ID_MAP),
            ("帧类型", FRAME_TYPE_MAP),
            ("传输方向", DIRECTION_MAP),
            ("启动标志", PRM_MAP),
            ("响应标识", RESPONSE_MAP),
            ("业务扩展域", EXTENSION_MAP),
            ("确认类业务", CONFIRM_SERVICE_MAP),
            ("数据传输类业务", DATA_SERVICE_MAP),
            ("命令-功能性业务", CMD_FUNC_SERVICE_MAP),
            ("命令-通信管理业务", CMD_COMM_SERVICE_MAP),
            ("MPDU版本", MPDU_VERSION_MAP),
        ]

        for category, mapping in all_maps:
            for code, name in mapping.items():
                if isinstance(code, int):
                    code_str = f"0x{code:02X}"
                else:
                    code_str = str(code)
                row = [category, code_str, name]
                if not keyword_upper:
                    results.append(row)
                    continue
                match = any(keyword_upper in cell.upper() for cell in row)
                if match:
                    results.append(row)
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", ""]]


def _search_gw_newgen(keyword: str = "") -> List[List[str]]:
    """国网新一代报文ID查询"""
    # 先用新一代载波的数据（两者有很多共用部分），后续可补充国网特有的
    return _search_csg_service(keyword)


def _search_hdc10(keyword: str = "") -> List[List[str]]:
    """HDC 1.0 双模互联互通查询（定界符/端口/报文ID/MSDU类型/转发规约等）"""
    try:
        from hdc10_parser import (
            DELIMITER_TYPES, APP_PORTS, MSG_ID_NAMES,
            MSDU_TYPES, PROTOCOL_TYPES, SECURITY_MODES,
            NETWORK_TYPES, SINGLEHOP_MSG_TYPES,
        )

        keyword_upper = keyword.upper().strip()
        results = []

        all_maps = [
            ("定界符类型", DELIMITER_TYPES),
            ("网络类型", NETWORK_TYPES),
            ("报文端口号", APP_PORTS),
            ("报文ID(业务)", MSG_ID_NAMES),
            ("MSDU类型", MSDU_TYPES),
            ("单跳消息类型", SINGLEHOP_MSG_TYPES),
            ("转发数据规约", PROTOCOL_TYPES),
            ("安全模式", SECURITY_MODES),
        ]

        for category, mapping in all_maps:
            for code, name in mapping.items():
                if isinstance(code, int):
                    code_str = f"0x{code:02X}"
                else:
                    code_str = str(code)
                row = [category, code_str, name]
                if not keyword_upper:
                    results.append(row)
                    continue
                match = any(keyword_upper in cell.upper() for cell in row)
                if match:
                    results.append(row)
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", ""]]


# 查询函数映射
_SEARCH_FUNCTIONS = {
    0: _search_south_di,
    1: _search_plc_cmd,
    2: _search_obis,
    3: _search_obis,
    4: _search_obis,
    5: _search_obis,
    6: _search_dlt645_di,
    7: _search_gdw_afn,
    8: _search_698_oi,
    9: _search_csg_service,
    10: _search_gw_newgen,
    11: _search_hdc10,
}


def get_lookup_data(protocol_index: int, keyword: str = "") -> List[Dict[str, str]]:
    """获取查询数据（统一接口）

    返回 List[Dict]，每个 dict 的键与列名对应。
    """
    config = get_query_config(protocol_index)
    columns = config["columns"]
    search_func = _SEARCH_FUNCTIONS.get(protocol_index, _search_south_di)

    rows = search_func(keyword)
    results = []
    for row in rows:
        item = {}
        for i, col in enumerate(columns):
            item[col] = str(row[i]) if i < len(row) else ""
        results.append(item)
    return results
