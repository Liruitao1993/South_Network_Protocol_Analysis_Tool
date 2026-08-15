# -*- coding: utf-8 -*-
"""协议组帧纯逻辑模块（Reflex Web 版）

将 GUI `frame_gen_widget.py` 的字段编辑器行为抽成纯函数，供 Reflex State 调用，
同时可被独立测试脚本（`test_web_frame_gen_utils.py`）断言字节与 GUI 生成器一致。

本模块不依赖 Reflex / Qt，只依赖项目根目录下的生成器模块：
- send_frame_lib.ProtocolFrameGenerator（南网）
- gdw_send_frame_lib.GDWFrameGenerator（国网）
- dl_t698_45_frame_gen.DLT69845FrameGenerator（698.45）
- dl_t698_45_axdr.AXDRCoder（A-XDR 编解码）

行为逐一对应 GUI 源码（frame_gen_widget.py）：
- parse_field_value / collect_field_values  <- _collect_values(:2105)
- generate_custom_data                      <- _generate_custom_data(:2228)
- build_dlt698_sa                           <- _get_dlt698_sa(:911)
- build_dlt698_axdr_apdu                    <- _generate_dlt698_frame A-XDR 分支(:2713)
- encode_axdr_items                         <- _encode_axdr_data/_encode_axdr_item(:1690/:1700)
"""
import struct
from typing import Any, Dict, List, Optional

# A-XDR 复合类型（与 frame_gen_widget.A_XDR_TYPE_LIST / COMPOUND_TYPES 一致）
COMPOUND_TYPES = {"array", "structure"}

# 变长类型（长度/个数可编辑）
VAR_LEN_TYPES = {"array", "structure", "octet-string", "visible-string", "UTF8-string", "bit-string"}

# A-XDR 类型列表（name, tag, desc），与 GUI A_XDR_TYPE_LIST 一致
A_XDR_TYPE_LIST = [
    ("null", 0x00, "空"),
    ("array", 0x01, "数组"),
    ("structure", 0x02, "结构体"),
    ("bool", 0x03, "布尔值"),
    ("bit-string", 0x04, "位串"),
    ("double-long", 0x05, "32位整数"),
    ("double-long-unsigned", 0x06, "32位正整数"),
    ("octet-string", 0x09, "字节串"),
    ("visible-string", 0x0A, "ASCII字符串"),
    ("UTF8-string", 0x0C, "UTF8字符串"),
    ("integer", 0x0F, "8位整数"),
    ("long", 0x10, "16位整数"),
    ("unsigned", 0x11, "8位正整数"),
    ("long-unsigned", 0x12, "16位正整数"),
    ("long64", 0x14, "64位整数"),
    ("long64-unsigned", 0x15, "64位正整数"),
    ("enum", 0x16, "枚举"),
    ("float32", 0x17, "32位浮点数"),
    ("float64", 0x18, "64位浮点数"),
    ("date_time", 0x19, "日期时间SIZE(10)"),
    ("date", 0x1A, "日期SIZE(5)"),
    ("time", 0x1B, "时间SIZE(3)"),
    ("date_time_s", 0x1C, "日期时间SIZE(7)"),
    ("OI", 0x50, "对象标识"),
    ("OAD", 0x51, "对象属性描述符"),
    ("OMD", 0x53, "对象方法描述符"),
    ("TI", 0x54, "时间间隔"),
    ("TSA", 0x55, "时间戳"),
    ("MAC", 0x56, "消息认证码"),
    ("RN", 0x57, "随机数"),
]

# 按 tag -> type name 映射
TAG_TO_TYPE = {tag: name for name, tag, _ in A_XDR_TYPE_LIST}
# 按 type name -> tag 映射
TYPE_TO_TAG = {name: tag for name, tag, _ in A_XDR_TYPE_LIST}

# 二进制串类型（octet-string 类，值按 hex 输入）
HEX_STRING_TYPES = {
    "octet-string", "bit-string", "date_time", "date", "time", "date_time_s",
    "TI", "TSA", "MAC", "RN",
}


def parse_field_value(raw: str, field: Dict[str, Any]) -> Any:
    """将单个字段的字符串值转换为生成器所需的数据类型。

    对应 GUI `_collect_values` 的非 list 分支：
    - uint8/16/32/enum -> int(raw, 0) if raw else 0
    - bytes/ascii/bcd/oad_list -> 原样字符串（生成器负责 fromhex）
    - oi -> int(raw, 16) if raw else 0
    - list -> 由 collect_field_values 专门处理，此处不返回
    """
    ftype = field.get("type", "bytes")
    if ftype in ("uint8", "uint16", "uint32", "enum"):
        if raw is None or str(raw).strip() == "":
            return 0
        try:
            return int(str(raw), 0)
        except ValueError:
            return 0
    elif ftype == "bytes":
        return str(raw) if raw is not None else ""
    elif ftype in ("ascii", "bcd", "oad_list"):
        return str(raw) if raw is not None else ""
    elif ftype == "oi":
        if raw is None or str(raw).strip() == "":
            return 0
        try:
            return int(str(raw), 16 if str(raw).strip().lower().startswith("0x") else 10)
        except ValueError:
            return 0
    else:
        # 未知类型按字符串处理
        return str(raw) if raw is not None else ""


def _collect_sub_field_value(sub_name: str, sub_field: Dict[str, Any], raw: Any) -> Any:
    """收集单个子字段值（enum/uint -> int，bytes -> str）。"""
    sub_type = sub_field.get("type", "bytes")
    if raw is None or str(raw).strip() == "":
        raw = sub_field.get("default", "")
    if sub_type == "enum":
        try:
            return int(str(raw), 0)
        except ValueError:
            return sub_field.get("default", 0)
    elif sub_type in ("uint8", "uint16", "uint32"):
        try:
            return int(str(raw), 0)
        except ValueError:
            return sub_field.get("default", 0)
    elif sub_type == "bytes":
        return str(raw) if raw is not None else ""
    else:
        return str(raw) if raw is not None else ""


def collect_field_values(field_schema: List[Dict[str, Any]],
                         gen_field_values: List[str],
                         gen_list_rows: List[List[List[str]]],
                         gen_sub_fields: List[List[str]]) -> Dict[str, Any]:
    """收集所有字段值，返回 {字段名: 值}。

    对应 GUI `_collect_values` 的 predefined 分支。输入全部为**位置对齐列表**：
    - gen_field_values[i]：字段 i 的原始值字符串（简单字段）
    - gen_sub_fields[i][j]：字段 i 的第 j 个子字段值
    - gen_list_rows[i][r][j]：字段 i 的第 r 行、第 j 个 item 值

    有 sub_fields：按 sub_name 收集子值（enum/uint->int，bytes->str），
    父值由生成器 Pass3 位域打包，本函数不计算父值。
    - count_field / length_field 由生成器回填，本函数不处理。
    """
    values: Dict[str, Any] = {}
    for fi, field in enumerate(field_schema):
        name = field["name"]
        ftype = field.get("type", "bytes")

        if "sub_fields" in field:
            subs = field.get("sub_fields", [])
            for j, sub in enumerate(subs):
                sub_name = sub["name"]
                cond = sub.get("condition")
                if cond:
                    ref_val = values.get(cond.get("field"))
                    if ref_val != cond.get("value"):
                        continue
                raw = ""
                if fi < len(gen_sub_fields) and j < len(gen_sub_fields[fi]):
                    raw = gen_sub_fields[fi][j]
                values[sub_name] = _collect_sub_field_value(sub_name, sub, raw)
            # 不设置父值（生成器 Pass3 打包）
            continue

        if ftype == "list":
            items = []
            item_fields = field.get("item_fields", [])
            rows = gen_list_rows[fi] if fi < len(gen_list_rows) else []
            for row in rows:
                item_values: Dict[str, Any] = {}
                for j, item_field in enumerate(item_fields):
                    item_name = item_field["name"]
                    raw = row[j] if j < len(row) else ""
                    item_values[item_name] = parse_field_value(raw, item_field)
                items.append(item_values)
            values[name] = items
            continue

        if ftype == "oad_list":
            raw = gen_field_values[fi] if fi < len(gen_field_values) else ""
            values[name] = str(raw) if raw else ""
            continue

        # 其余类型
        raw = gen_field_values[fi] if fi < len(gen_field_values) else ""
        if raw is None or str(raw).strip() == "":
            raw = str(field.get("default", ""))
        values[name] = parse_field_value(raw, field)

    return values


def generate_custom_data(templates: List[Dict[str, Any]]) -> bytes:
    """根据自定义模板生成用户数据区字节（对应 GUI `_generate_custom_data(:2228)`）。

    templates: [{name, length, ftype, endian, display, reverse, value}]
    - checksum 类型占位 0x00 并记录偏移，末尾回填 sum(data)&0xFF
    - bytes -> fromhex + pad/截断到 length
    - uint8/16/32 -> struct.pack（按 endian / display hex|dec）
    """
    data = b""
    checksum_idx = -1

    for row, tpl in enumerate(templates):
        ftype = tpl.get("ftype", "bytes")
        length = int(tpl.get("length", 1) or 1)
        text = str(tpl.get("value", "") or "").strip().replace(" ", "")

        if ftype == "checksum":
            checksum_idx = row
            data += b"\x00" * length
            continue

        if ftype == "bytes":
            try:
                raw = bytes.fromhex(text)
            except ValueError:
                raw = b""
            if len(raw) < length:
                raw = raw + b"\x00" * (length - len(raw))
            elif len(raw) > length:
                raw = raw[:length]
        elif ftype in ("uint8", "uint16", "uint32"):
            try:
                if tpl.get("display", "hex") == "hex":
                    val = int(text, 16) if text else 0
                else:
                    val = int(text, 10) if text else 0
            except ValueError:
                val = 0
            endian = tpl.get("endian", "little")
            if ftype == "uint8":
                raw = struct.pack("B", val & 0xFF)
            elif ftype == "uint16":
                raw = struct.pack("<H" if endian == "little" else ">H", val & 0xFFFF)
            else:
                raw = struct.pack("<I" if endian == "little" else ">I", val & 0xFFFFFFFF)
        else:
            raw = b"\x00" * length

        data += raw

    # 回填校验和
    if checksum_idx >= 0:
        cs = sum(data) & 0xFF
        offset = 0
        for i, tpl in enumerate(templates):
            if i == checksum_idx:
                data = data[:offset] + struct.pack("B", cs) + data[offset + 1:]
                break
            offset += int(tpl.get("length", 1) or 1)

    return data


def build_dlt698_sa(addr_type: int, logic_addr: int, addr_len: int, sa_raw: str) -> bytes:
    """组装 698.45 服务器地址 SA（含地址特征字节 + 地址字节）（对应 GUI `_get_dlt698_sa(:911)`）。

    地址特征字节: bit7-6=地址类型, bit5-4=逻辑地址, bit3-0=地址长度-1
    广播地址(addr_type==3) 返回 1 字节 0xAA。
    """
    addr_type = int(addr_type or 0)
    logic_addr = int(logic_addr or 0)
    addr_len = int(addr_len or 0)

    if addr_type == 3:
        return bytes([0xAA])

    if addr_len == 0:
        addr_len = 6

    feature = ((addr_type & 0x03) << 6) | ((logic_addr & 0x03) << 4) | ((addr_len - 1) & 0x0F)

    sa_text = str(sa_raw or "").strip().replace(" ", "")
    try:
        sa_bytes = bytes.fromhex(sa_text) if sa_text else b""
    except ValueError:
        sa_bytes = b""

    if len(sa_bytes) < addr_len:
        sa_bytes = sa_bytes + b'\x00' * (addr_len - len(sa_bytes))
    elif len(sa_bytes) > addr_len:
        sa_bytes = sa_bytes[:addr_len]

    # GUI 大端正序输入，报文小端字节逆序
    return bytes([feature]) + sa_bytes[::-1]


def _build_apdu_header(apdu_type: str, sub_type: str) -> bytes:
    """构建 APDU 首部（类型码 + 子类型码）（对应 GUI `_build_apdu_header(:237)`）。"""
    type_map = {
        "LINK-Request": 0x01,
        "CONNECT-Request": 0x02,
        "RELEASE-Request": 0x03,
        "GET-Request": 0x05,
        "SET-Request": 0x06,
        "ACTION-Request": 0x07,
        "PROXY-Request": 0x09,
        "SECURITY-Request": 0x10,
    }
    sub_type_map = {
        "link_request": 0x00,
        "connect_request": 0x00,
        "release_request": 0x00,
        "get_normal": 0x01,
        "get_normal_list": 0x02,
        "get_record": 0x03,
        "get_record_list": 0x04,
        "get_next": 0x05,
        "set_normal": 0x01,
        "set_normal_list": 0x02,
        "action_normal": 0x01,
        "action_normal_list": 0x02,
        "proxy_request": 0x00,
        "security_request": 0x00,
    }
    t = type_map.get(apdu_type, 0x05)
    s = sub_type_map.get(sub_type, 0x01)
    if s == 0x00:
        return bytes([t])
    return bytes([t, s])


def build_dlt698_axdr_apdu(apdu_type: str, sub_type: str, piid: int, oi_hex: str,
                           field_values: Dict[str, Any], axdr_data: bytes,
                           is_custom: bool = False) -> bytes:
    """组装 698.45 A-XDR APDU（对应 GUI `_generate_dlt698_frame` A-XDR 分支 :2713）。

    is_custom -> bytes([0x05, 0x01, piid]) + axdr_data
    else -> 头 + B(piid) + [OI>H + attr|idx / method|mode 按 GET/SET/ACTION] + axdr_data
      + GET-Request 且 sub_type in (get_normal, get_record, get_normal_list) 时尾补 b'\x00'
    """
    if is_custom:
        return bytes([0x05, 0x01, piid]) + axdr_data

    apdu_header = _build_apdu_header(apdu_type, sub_type)
    apdu_body = struct.pack("B", piid)

    oi_text = str(oi_hex or "0000").strip().replace(" ", "")
    try:
        oi_bytes = bytes.fromhex(oi_text)
    except ValueError:
        oi_bytes = b'\x00\x00'
    oi_bytes = oi_bytes.ljust(2, b'\x00')[:2]

    if apdu_type in ("GET-Request", "SET-Request"):
        attr = int(field_values.get("属性标识", 2)) & 0x1F
        idx = int(field_values.get("索引", 0)) & 0xFF
        oad = oi_bytes + struct.pack("B", attr) + struct.pack("B", idx)
        apdu_body += oad
    elif apdu_type == "ACTION-Request":
        method = int(field_values.get("方法标识", 1)) & 0x1F
        mode = int(field_values.get("操作模式", 0)) & 0xFF
        omd = oi_bytes + struct.pack("B", method) + struct.pack("B", mode)
        apdu_body += omd

    apdu_body += axdr_data

    if apdu_type == "GET-Request" and sub_type in ("get_normal", "get_record", "get_normal_list"):
        apdu_body += b'\x00'

    return apdu_header + apdu_body


def _encode_axdr_item(coder, item: Dict[str, Any]) -> bytes:
    """递归编码单个 A-XDR 数据项（对应 GUI `_encode_axdr_item(:1700)`）。"""
    tag = item["tag"]
    t = item.get("type", "unsigned")
    value = item.get("value", 0)
    length = item.get("length", 0)

    if t in COMPOUND_TYPES:
        children = item.get("children", [])
        result = bytes([tag])
        child_data = b""
        for child in children:
            child_data += _encode_axdr_item(coder, child)
        result += coder._encode_length(len(child_data))
        result += child_data
        return result

    if t == "bool":
        return coder.encode(value, tag)
    if t in ("octet-string", "bit-string"):
        raw = bytes.fromhex(str(value).replace(" ", "")) if isinstance(value, str) and value else b""
        if length > 0:
            raw = raw.ljust(length, b'\x00')[:length]
        return bytes([tag]) + coder._encode_length(len(raw)) + raw
    if t in ("visible-string", "UTF8-string"):
        data = str(value).encode('ascii' if t == "visible-string" else 'utf-8', errors='replace')
        if length > 0:
            data = data.ljust(length, b'\x00')[:length]
        return bytes([tag]) + coder._encode_length(len(data)) + data
    if t in HEX_STRING_TYPES:
        raw = bytes.fromhex(str(value).replace(" ", "")) if isinstance(value, str) and value else b""
        if length > 0:
            raw = raw.ljust(length, b'\x00')[:length]
        return bytes([tag]) + coder._encode_length(len(raw)) + raw
    if t == "OI":
        return coder.encode(int(value), tag)
    if t in ("OAD", "OMD"):
        val = value if isinstance(value, dict) else {}
        return coder.encode(val, tag)
    if t == "null":
        return coder.encode(None, tag)

    # 数值类型
    return coder.encode(value, tag)


def encode_axdr_items(items: List[Dict[str, Any]]) -> bytes:
    """将所有 A-XDR 数据项编码为字节（对应 GUI `_encode_axdr_data(:1690)`）。

    items: [{tag, type, length, value, children}]，结构对齐 GUI `_axdr_items`。
    """
    from dl_t698_45_axdr import AXDRCoder
    coder = AXDRCoder()
    data = b""
    for item in items:
        data += _encode_axdr_item(coder, item)
    return data