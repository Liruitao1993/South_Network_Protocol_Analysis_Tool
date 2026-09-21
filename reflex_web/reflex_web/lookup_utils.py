# -*- coding: utf-8 -*-
"""查询功能工具

为 Reflex Web 版提供统一的查询接口。
按协议索引返回对应查询数据。
"""
import sys
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
        "columns": ["DI3", "DI2", "DI1", "DI0", "AFN", "中文含义", "自定义"],
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
        "columns": ["AFN", "AFN名称", "Fn", "功能说明", "自定义"],
    },
    8: {  # 698.45
        "title": "OI 查询",
        "columns": ["OI", "对象名称", "属性", "方法", "说明"],
    },
    9: {  # 新一代载波
        "title": "业务标识查询",
        "columns": ["类别", "代码", "名称"],
    },
    10: {  # 国网新一代（数据源：GWNewGenParser 自有表，含安全机制说明）
        "title": "报文ID查询",
        "columns": ["类别", "代码", "名称", "说明"],
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
    """南网 DI 查询

    AFN 列 = DI1（键序 (DI3, DI2, DI1, DI0)，见 protocol_parser.py:519-541 的分组注释
    「# AFN=02H 管理任务」）；此前误用 DI3 低 4 位，导致所有 E8 前缀 DI 都显示 08H。
    桌面同口径：main_gui.py:2234-2235（afn_val = di1 + AFN_MAP 名称）。

    第 7 列「自定义」：★ = 条目来自 `custom_di.json`（可在查询页删除/覆盖），
    空 = 内置条目（不可删除）。与桌面查询页的蓝色★标记同义
    （main_gui 表格 di_data 第 8 位标志），Web 侧靠这一列决定「删除」按钮是否可用。
    """
    try:
        from protocol_parser import ProtocolFrameParser
        from custom_di_store import custom_key_set

        parser = ProtocolFrameParser()
        afn_map = getattr(parser, "AFN_MAP", {})
        # 自定义键集合：ProtocolFrameParser 构造时已把 custom_di.json 合并进
        # DI_COMBINATION_MAP，这里取同一份文件的键集合做标记，保证「能看到的
        # 自定义条目 = 能删除的自定义条目」。
        custom_keys = custom_key_set()
        results = []
        keyword_upper = keyword.upper().strip()
        for (di3, di2, di1, di0), desc in parser.DI_COMBINATION_MAP.items():
            afn = di1
            afn_name = afn_map.get(afn, f"未知({afn:02X})")
            row = [f"{di3:02X}", f"{di2:02X}", f"{di1:02X}", f"{di0:02X}",
                   f"{afn:02X}H {afn_name}", desc,
                   "★" if (di3, di2, di1, di0) in custom_keys else ""]

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
        return [[f"加载失败: {e}", "", "", "", "", "", ""]]


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
    """国网 AFN+Fn 查询

    第 5 列「自定义」：★ = AFN+Fn 由用户自定义（可删除），空 = 标准定义。
    判据与桌面 `main_gui._delete_custom_gdw_fn` 一致：只有落在解析器
    `_custom_fn_map[afn][fn]` 里的组合才是自定义（标准 FN_MAP 条目不可删）。
    """
    try:
        from gdw_afn_lookup import get_gdw_afn_lookup

        lookup = get_gdw_afn_lookup()
        if keyword.strip():
            data = lookup.search(keyword)
        else:
            data = lookup.data
        custom_pairs = gdw_custom_fn_pairs()
        results = []
        for item in data:
            afn = item[0]
            afn_name = item[1]
            fn = item[2]
            fn_name = item[3] if len(item) > 3 else ""
            results.append([
                f"{afn:02X}H", afn_name, f"F{fn:02d}", fn_name,
                "★" if (afn, fn) in custom_pairs else "",
            ])
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", "", "", ""]]

def _search_gdw_eb(keyword: str = "") -> List[List[str]]:
    """国网本地通信模块扩展协议 EB 数据标识查询（附件1 V3.31）

    返回 [EB编码, 名称, 数据格式, 长度, 功能]
    """
    try:
        from gdw_eb_di_lookup import get_eb_di_lookup
        lookup = get_eb_di_lookup()
        if keyword.strip():
            data = lookup.search(keyword)
        else:
            data = lookup.get_all()
        results = []
        for code, info in sorted(data.items()):
            results.append([
                code,
                info.get("名称", ""),
                str(info.get("格式", "")),
                str(info.get("长度", "")),
                info.get("功能", ""),
            ])
        return results
    except Exception as e:
        return [[f"加载失败: {e}", "", "", "", ""]]


def _is_eb_query(protocol_index: int, keyword: str) -> bool:
    """判断是否为 EB 数据标识查询（协议7 + 关键词含 EB 前缀或 EB 编码）"""
    if protocol_index != 7:
        return False
    kw = keyword.strip().upper()
    if not kw:
        return False
    # 匹配 EB 前缀（如 EB03 / EB0402 / EBEEEEEE）或中文关键词（台区/时钟/档案等 EB 相关）
    return kw.startswith("EB") or kw in ("台区", "时钟", "档案", "停上电", "事件", "任务队列")


def _search_698_oi(keyword: str = "") -> List[List[str]]:
    """698.45 OI 查询

    属性/方法列来自 OILookup 类映射（OI_TO_CLASS_ID → CLASS_ID_MAP），
    与桌面 _load_oad_map_data（main_gui.py:3809-3823）同口径；
    此前恒为 "-" 占位。
    """
    try:
        from dl_t698_45_oi_lookup import OILookup
        lookup = OILookup()
        keyword_upper = keyword.upper().strip()
        results = []

        # OI_NAME_MAP 是 oi->名称 的映射
        oi_map = getattr(lookup, 'OI_NAME_MAP', {})
        oi_to_class = getattr(lookup, 'OI_TO_CLASS_ID', {})
        class_map = getattr(lookup, 'CLASS_ID_MAP', {})
        for oi_val, name in oi_map.items():
            class_id = oi_to_class.get(oi_val)
            info = class_map.get(class_id, {}) if class_id is not None else {}
            attrs = ", ".join(
                f"{k}:{v}" for k, v in (info.get("attributes", {}) or {}).items()
            )
            methods = ", ".join(
                f"{k}:{v}" for k, v in (info.get("methods", {}) or {}).items()
            )
            row = [f"0x{oi_val:04X}", name, attrs or "-", methods or "-",
                   f"OI=0x{oi_val:04X}"]
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
    """国网新一代报文ID查询（数据源：GWNewGenParser 自有映射表）

    与桌面 _create_gw_new_gen_lookup_content（main_gui.py:3669-3685）同口径：
    7 类共 49 条，含安全机制说明。此前直接复用协议9 的表（源码自述 TODO），
    导致「关联请求」等协议10 专有名称搜不到。
    """
    try:
        from gw_new_gen_parser import GWNewGenParser

        parser = GWNewGenParser()
        keyword_upper = keyword.upper().strip()
        results = []

        for code, name in parser.MSG_IDS.items():
            sec = (code >> 12) & 0x0F
            results.append(["报文ID", f"0x{code:04X}", name, f"安全机制={sec}"])
        for code, name in parser.PORT_NAMES.items():
            results.append(["报文端口号", f"0x{code:02X}", name, ""])
        for code, name in parser.DELIMITER_TYPES.items():
            results.append(["定界符类型", str(code), name, ""])
        for code, name in parser.MSDU_TYPES.items():
            results.append(["MSDU类型", str(code), name, ""])
        for code, name in parser.PROTOCOL_TYPES.items():
            results.append(["规约类型", str(code), name, ""])
        for code, name in parser.SEND_TYPES.items():
            results.append(["发送类型", str(code), name, ""])
        for code, name in parser.BROADCAST_DIRS.items():
            results.append(["广播方向", str(code), name, ""])

        if not keyword_upper:
            return results
        return [
            row for row in results
            if any(keyword_upper in str(cell).upper() for cell in row)
        ]
    except Exception as e:
        return [[f"加载失败: {e}", "", "", ""]]


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
    # EB 数据标识查询（协议7 + EB 关键词）：动态切换列
    if _is_eb_query(protocol_index, keyword):
        eb_columns = ["数据标识", "名称", "数据格式", "长度", "功能"]
        eb_rows = _search_gdw_eb(keyword)
        return [_row_to_dict(eb_rows[i], eb_columns) for i in range(len(eb_rows))]

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


def _row_to_dict(row: List[str], columns: List[str]) -> Dict[str, str]:
    """将行转换为 dict（键与列名对应）"""
    item = {}
    for i, col in enumerate(columns):
        item[col] = str(row[i]) if i < len(row) else ""
    return item


# ═══════════════════════════════════════════════════════════════
# 查询页「自定义条目」增删（协议0 DI / 协议7 AFN+Fn）
#
# 单一来源：DI 走 `custom_di_store`；AFN+Fn 走 `GDW10376Parser` 的自定义 API
# （与桌面 main_gui._add_custom_gdw_fn / _delete_custom_gdw_fn 同一实现），
# 落盘文件分别是 custom_di.json 与 gdw_custom_afn.json（app_paths 数据目录）。
# 这里只放**无 reflex 依赖**的逻辑，State 事件只做薄封装，便于测试。
# ═══════════════════════════════════════════════════════════════


def gdw_custom_fn_pairs() -> set:
    """国网自定义 AFN+Fn 组合集合 {(afn, fn)}（★ 标记与「是否可删」判据）"""
    from parser_registry import get_parser

    parser = get_parser("gdw")
    return {(afn, fn) for afn, _name, fn, _fn_name in parser.get_custom_entries()}


def refresh_gdw_afn_lookup() -> None:
    """重建 AFN+Fn 查询缓存（增删自定义组合后必须调用，否则页面仍是旧表）"""
    from gdw_afn_lookup import get_gdw_afn_lookup

    get_gdw_afn_lookup().refresh()


def add_gdw_custom_fn(
    afn_text: str, fn_text: str, name: str, afn_name: str = ""
) -> Tuple[bool, str]:
    """添加自定义 AFN+Fn（校验与提示文案对齐桌面 `_add_custom_gdw_fn`）。

    Returns:
        (ok, message)：失败时 message 为可直接展示的中文提示。
    """
    raw_afn = (afn_text or "").strip().replace("H", "").replace("h", "").replace("0x", "")
    try:
        afn = int(raw_afn, 16)
    except ValueError:
        return False, "AFN 必须为十六进制（00-FF）！"
    if not 0 <= afn <= 0xFF:
        return False, "AFN 必须为十六进制（00-FF）！"

    raw_fn = (fn_text or "").strip().lstrip("Ff")
    try:
        fn = int(raw_fn)
    except ValueError:
        return False, "Fn 必须为十进制整数（1-248）！"
    if not 1 <= fn <= 248:
        return False, "Fn 必须为十进制整数（1-248）！"

    name = (name or "").strip()
    if not name:
        return False, "功能名称不能为空"

    from parser_registry import get_parser

    parser = get_parser("gdw")
    if afn in parser.FN_MAP and fn in parser.FN_MAP.get(afn, {}):
        return False, f"AFN={afn:02X}H Fn=F{fn} 已在标准定义中存在"

    if (afn_name or "").strip():
        parser.add_custom_afn(afn, afn_name.strip())
    parser.add_custom_fn(afn, fn, name)
    refresh_gdw_afn_lookup()
    return True, f"已添加自定义组合: AFN={afn:02X}H Fn=F{fn}"


def remove_gdw_custom_fns(pairs) -> Tuple[int, int]:
    """批量删除自定义 AFN+Fn 组合；标准定义条目忽略（不可删）。

    Returns:
        (removed, ignored_builtin)
    """
    from parser_registry import get_parser

    parser = get_parser("gdw")
    custom = gdw_custom_fn_pairs()
    removed = ignored = 0
    for afn, fn in pairs:
        if (afn, fn) in custom:
            parser.remove_custom_fn(afn, fn)
            removed += 1
        else:
            ignored += 1
    if removed:
        refresh_gdw_afn_lookup()
    return removed, ignored


def parse_gdw_row_key(key: str) -> Optional[Tuple[int, int]]:
    """查询页行选择键 ``"03HF01"`` → ``(3, 1)``；非法返回 None"""
    raw = (key or "").strip().upper()
    if "H" not in raw:
        return None
    afn_part, fn_part = raw.split("H", 1)
    try:
        return int(afn_part, 16), int(fn_part.lstrip("F"))
    except ValueError:
        return None


def parse_di_row_key(key: str) -> Optional[Tuple[int, int, int, int]]:
    """查询页行选择键 ``"E8 00 08 03"`` → ``(232, 0, 8, 3)``；非法返回 None"""
    parts = [p for p in (key or "").replace(",", " ").split() if p]
    if len(parts) != 4:
        return None
    try:
        values = tuple(int(p, 16) for p in parts)
    except ValueError:
        return None
    return values if all(0 <= v <= 0xFF for v in values) else None
