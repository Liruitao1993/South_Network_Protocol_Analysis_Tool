# -*- coding: utf-8 -*-
"""Modbus 协议解析核心（RTU / TCP，纯逻辑，无 Qt、无 GUI 依赖）。

职责边界
--------
- 帧层：自动识别 **Modbus RTU**（``从站地址 + PDU + CRC16``）与 **Modbus TCP**
  （``MBAP 头 + PDU``），给出传输层字段行、CRC16 / 长度域校验结论；
- PDU 层：按功能码解析请求/响应，输出「读哪个寄存器、写哪个寄存器、值是多少」；
- 寄存器映射：可选传入一份寄存器列表（``modbus_register_store`` 的 profile），
  把响应里的裸字节按「地址 + 数据类型 + 系数 + 单位」翻译成工程量。
  **没有寄存器列表时按通用方式解析**（功能码 + 起始地址/数量 + 寄存器值），
  并在说明列显式标注「地址为按响应顺序推导」，绝不假装知道品牌含义。

表格行格式与全项目其它解析器一致：``(字段, 原始, 解析值, 说明, 起始字节, 结束字节)``，
``起始/结束`` 为该行在**整帧**中的字节下标（含），可为 None（不参与高亮）。

被复用方：
- ``modbus_parser.ModbusParser`` —— 单帧 / 批量解析入口
- ``main_gui`` 的批量帧提取（``extract_modbus_frames``）
- ``validator/modbus_validator.py`` —— 校验器直接复用本模块的判据，不另写一份
"""

from __future__ import annotations

import re
import struct
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: 表格行：(字段, 原始, 解析值, 说明, 起始字节, 结束字节)
Row = Tuple[str, str, str, str, Optional[int], Optional[int]]

PROTOCOL_NAME = "Modbus"

TRANSPORT_RTU = "rtu"
TRANSPORT_TCP = "tcp"

TRANSPORT_LABELS = {
    TRANSPORT_RTU: "Modbus RTU（串行链路：从站地址 + PDU + CRC16）",
    TRANSPORT_TCP: "Modbus TCP（以太网：MBAP 头 + PDU）",
}

#: 功能码 → (简称, 规范说明)
FUNC_NAMES: Dict[int, Tuple[str, str]] = {
    0x01: ("读线圈", "Read Coils：读取 0x 区线圈状态（按位，1 位/线圈）"),
    0x02: ("读离散输入", "Read Discrete Inputs：读取 1x 区离散输入（按位，只读）"),
    0x03: ("读保持寄存器", "Read Holding Registers：读取 4x 区保持寄存器（16 位/寄存器）"),
    0x04: ("读输入寄存器", "Read Input Registers：读取 3x 区输入寄存器（16 位/寄存器，只读）"),
    0x05: ("写单个线圈", "Write Single Coil：写单个线圈（FF00=ON，0000=OFF）"),
    0x06: ("写单个寄存器", "Write Single Register：写单个保持寄存器"),
    0x07: ("读异常状态", "Read Exception Status：读串行链路异常状态字节"),
    0x08: ("诊断", "Diagnostics：诊断子功能（子功能码见明细）"),
    0x0B: ("获取通信事件计数", "Get Comm Event Counter：读通信事件计数器"),
    0x0C: ("获取通信事件日志", "Get Comm Event Log：读通信事件日志"),
    0x0F: ("写多个线圈", "Write Multiple Coils：批量写线圈（按位）"),
    0x10: ("写多个寄存器", "Write Multiple Registers：批量写保持寄存器"),
    0x11: ("报告从站ID", "Report Server ID：读从站标识"),
    0x14: ("读文件记录", "Read File Record：按文件记录读取"),
    0x15: ("写文件记录", "Write File Record：按文件记录写入"),
    0x16: ("屏蔽写寄存器", "Mask Write Register：按 AND/OR 掩码修改寄存器"),
    0x17: ("读写多个寄存器", "Read/Write Multiple Registers：一次交互中先读后写"),
    0x18: ("读FIFO队列", "Read FIFO Queue：读 FIFO 队列"),
    0x2B: ("设备识别", "Encapsulated Interface Transport：读设备识别信息（MEI=0x0E）"),
}

#: 诊断子功能码（0x08）
DIAG_SUBFUNCS: Dict[int, str] = {
    0x0000: "返回查询数据",
    0x0001: "重新启动通信选项",
    0x0002: "返回诊断寄存器",
    0x0003: "修改 ASCII 字符分隔符",
    0x0004: "强制监听模式",
    0x0005: "清除计数器",
    0x0006: "返回总线报文计数",
    0x0007: "返回总线通信错误计数",
    0x0008: "返回总线异常错误计数",
    0x000A: "清除通信事件计数器",
    0x000B: "返回通信事件计数器",
    0x000C: "返回通信事件日志",
    0x000D: "返回从站报文计数",
    0x000E: "返回从站无响应计数",
    0x000F: "返回从站 NAK 计数",
    0x0010: "返回从站忙计数",
    0x0011: "返回总线字符溢出计数",
    0x0012: "清除溢出计数与标志",
    0x0014: "返回 I/O 位状态",
    0x0015: "写 I/O 位状态",
}

#: 异常码（功能码 | 0x80 的响应第 2 字节）
EXCEPTION_CODES: Dict[int, str] = {
    0x01: "非法功能码（设备不支持该功能码）",
    0x02: "非法数据地址（寄存器/线圈地址不存在）",
    0x03: "非法数据值（数量或取值超出设备允许范围）",
    0x04: "从站设备故障（执行过程中出现不可恢复错误）",
    0x05: "确认（设备已接受请求，需较长时间处理）",
    0x06: "从站设备忙（正在处理长任务，稍后重试）",
    0x08: "存储奇偶性差错",
    0x0A: "网关路径不可用",
    0x0B: "网关目标设备响应失败",
}

#: 设备识别 MEI 读取码（0x2B/0x0E）
DEVICE_ID_READ_CODES: Dict[int, str] = {
    0x01: "基本设备识别（厂商/产品代码/修订号）",
    0x02: "常规设备识别",
    0x03: "扩展设备识别",
    0x04: "读取指定对象",
}

#: 设备识别对象 ID
DEVICE_ID_OBJECTS: Dict[int, str] = {
    0x00: "厂商名称（VendorName）",
    0x01: "产品代码（ProductCode）",
    0x02: "主修订号（MajorMinorRevision）",
    0x03: "厂商网址（VendorUrl）",
    0x04: "产品名称（ProductName）",
    0x05: "型号名称（ModelName）",
    0x06: "用户应用名（UserApplicationName）",
}

#: 支持的数据类型 → (字节数, 中文名)
REG_TYPES: Dict[str, Tuple[int, str]] = {
    "uint16": (2, "无符号 16 位"),
    "int16": (2, "有符号 16 位"),
    "uint32": (4, "无符号 32 位"),
    "int32": (4, "有符号 32 位"),
    "uint64": (8, "无符号 64 位"),
    "int64": (8, "有符号 64 位"),
    "float32": (4, "单精度浮点（IEEE754）"),
    "float64": (8, "双精度浮点（IEEE754）"),
    "bit": (2, "位（取最低位）"),
    "hex": (0, "原始十六进制（长度由数量决定）"),
    "ascii": (0, "ASCII 字符串（长度由数量决定）"),
}

TYPE_ALIASES = {
    "u16": "uint16",
    "i16": "int16",
    "u32": "uint32",
    "i32": "int32",
    "u64": "uint64",
    "i64": "int64",
    "float": "float32",
    "f32": "float32",
    "f64": "float64",
    "double": "float64",
    "bool": "bit",
    "string": "ascii",
    "str": "ascii",
    "raw": "hex",
}


# ── 基础工具 ────────────────────────────────────────────────────────


def _hex(data: bytes) -> str:
    """字节串 → 空格分隔大写 hex。"""
    return " ".join(f"{b:02X}" for b in bytes(data))


def _crc16_update(crc: int, byte: int) -> int:
    """Modbus CRC16 单字节更新（多项式 0xA001，反射算法）。"""
    crc ^= byte & 0xFF
    for _ in range(8):
        if crc & 0x0001:
            crc = (crc >> 1) ^ 0xA001
        else:
            crc >>= 1
    return crc & 0xFFFF


def crc16(data: bytes) -> int:
    """Modbus RTU CRC16（初值 0xFFFF，多项式 0xA001，低字节先发）。"""
    crc = 0xFFFF
    for byte in bytes(data):
        crc = _crc16_update(crc, byte)
    return crc


def lrc(data: bytes) -> int:
    """Modbus ASCII 的 LRC（二补数校验），仅用于提示，不参与解析。"""
    total = sum(bytes(data)) & 0xFF
    return (-total) & 0xFF


def crc16_bytes(data: bytes) -> bytes:
    """CRC16 的线上字节序（低字节在前）。"""
    value = crc16(data)
    return bytes((value & 0xFF, (value >> 8) & 0xFF))


def format_number(value: Any) -> str:
    """数值 → 紧凑文本（整数值不带小数点，浮点去尾零）。"""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return str(value)
        if abs(value - round(value)) < 1e-9 and abs(value) < 1e15:
            return str(int(round(value)))
        text = f"{value:.6f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def format_addr(addr: int) -> str:
    """寄存器地址显示：``0x0000（0）``。"""
    return f"0x{addr:04X}（{addr}）"


def type_label(dtype: str) -> str:
    """数据类型 → 中文名（未知类型原样返回）。"""
    return REG_TYPES.get(dtype, (0, dtype))[1]


def normalize_type(dtype: Any) -> str:
    """数据类型文本归一化；未知返回 ``uint16``。"""
    text = str(dtype or "").strip().lower()
    text = TYPE_ALIASES.get(text, text)
    return text if text in REG_TYPES else "uint16"


def type_size(dtype: str) -> int:
    """数据类型字节数；``hex``/``ascii`` 返回 0（由寄存器数量决定）。"""
    return REG_TYPES.get(normalize_type(dtype), (2, ""))[0]


# ── 帧层：传输类型识别 / 拆帧 ───────────────────────────────────────


def _tcp_expected_length(data: bytes, offset: int = 0) -> Optional[int]:
    """按 MBAP 头推断 TCP 帧总长；不像 TCP 时返回 None。

    判据：协议标识必须为 0，长度域 = 单元标识 + PDU（2~254）。
    """
    if len(data) - offset < 8:
        return None
    if data[offset + 2] != 0x00 or data[offset + 3] != 0x00:
        return None
    length = (data[offset + 4] << 8) | data[offset + 5]
    if length < 2 or length > 254:
        return None
    return length + 6


def _rtu_crc_ok(data: bytes, offset: int, total: int) -> bool:
    """区间 ``data[offset:offset+total]`` 是否满足 RTU CRC16。"""
    if total < 4 or offset + total > len(data):
        return False
    body = data[offset : offset + total - 2]
    wire = (data[offset + total - 1] << 8) | data[offset + total - 2]
    return crc16(body) == wire


def is_ascii_frame(data: bytes) -> bool:
    """是否像 Modbus ASCII（以 ``:`` 0x3A 开头）。"""
    return bool(data) and data[0] == 0x3A


def detect_transport(data: bytes) -> str:
    """自动识别 RTU / TCP。

    判定顺序（实测踩坑：RTU 的起始地址 0x0000 会让 ``data[2:4]`` 恰好是
    ``00 00``，绝不能只看这两个字节）：

    1. RTU CRC 通过 → RTU；
    2. MBAP 长度域与整帧长度自洽 → TCP；
    3. 长度域差 1~2 字节（截断/多余）→ TCP；
    4. 其余 → RTU。
    """
    data = bytes(data or b"")
    if len(data) >= 4 and _rtu_crc_ok(data, 0, len(data)):
        return TRANSPORT_RTU
    expected = _tcp_expected_length(data)
    if expected is not None:
        if expected == len(data):
            return TRANSPORT_TCP
        if abs(expected - len(data)) <= 2:
            return TRANSPORT_TCP
    return TRANSPORT_RTU


def split_frame(data: bytes) -> Dict[str, Any]:
    """把整帧拆成传输层头 + PDU + 尾部校验。

    Returns dict:
        transport / slave / slave_label / pdu / pdu_offset /
        header_rows / trailer_rows / crc_ok / length_ok / warnings / error
    """
    data = bytes(data or b"")
    out: Dict[str, Any] = {
        "transport": TRANSPORT_RTU,
        "slave": 0,
        "slave_label": "从站地址",
        "pdu": b"",
        "pdu_offset": 0,
        "header_rows": [],
        "trailer_rows": [],
        "crc_ok": None,
        "length_ok": None,
        "warnings": [],
        "error": "",
    }
    if not data:
        out["error"] = "报文为空"
        return out
    if is_ascii_frame(data):
        out["error"] = (
            "报文以 0x3A（':'）开头，疑似 Modbus ASCII 帧；"
            "本工具目前只支持 Modbus RTU / TCP，请提供二进制帧的十六进制内容"
        )
        return out
    if len(data) < 4:
        out["error"] = f"帧长 {len(data)} 字节，Modbus 帧至少 4 字节（地址 + 功能码 + CRC16）"
        return out

    transport = detect_transport(data)
    out["transport"] = transport
    rows: List[Row] = []

    if transport == TRANSPORT_TCP:
        expected = _tcp_expected_length(data)
        transaction = (data[0] << 8) | data[1]
        protocol_id = (data[2] << 8) | data[3]
        declared = (data[4] << 8) | data[5]
        unit = data[6] if len(data) > 6 else 0
        out["slave"] = unit
        out["slave_label"] = "单元标识"
        out["pdu_offset"] = 7
        length_ok = expected is not None and expected == len(data)
        out["length_ok"] = length_ok
        rows.append(
            (
                "传输类型",
                "-",
                "Modbus TCP",
                "MBAP 头（7 字节）+ PDU：事务标识/协议标识/长度/单元标识",
                None,
                None,
            )
        )
        rows.append(
            (
                "事务标识",
                _hex(data[0:2]),
                str(transaction),
                "客户端用于请求/响应配对，从站原样回送",
                0,
                1,
            )
        )
        rows.append(
            (
                "协议标识",
                _hex(data[2:4]),
                str(protocol_id),
                "Modbus TCP 固定为 0" if protocol_id == 0 else "非 0（非标准 Modbus 封装）",
                2,
                3,
            )
        )
        rows.append(
            (
                "长度域",
                _hex(data[4:6]),
                str(declared),
                (
                    f"后续字节数 = 单元标识(1) + PDU({max(0, declared - 1)})；"
                    f"整帧应为 {declared + 6} 字节，实收 {len(data)} 字节"
                    + ("（一致）" if length_ok else "（不一致，按实收字节解析）")
                ),
                4,
                5,
            )
        )
        rows.append(
            (
                "单元标识",
                f"{unit:02X}",
                str(unit),
                "串口网关场景下即从站地址；直连设备常为 1 或 0xFF",
                6,
                6,
            )
        )
        if not length_ok and expected is not None:
            out["warnings"].append(
                f"MBAP 长度域声明整帧 {expected} 字节，实收 {len(data)} 字节"
            )
        # PDU：声明长度可能小于实际（尾部有附加字节）时以声明为准
        end = min(len(data), 6 + declared) if declared >= 2 else len(data)
        out["pdu"] = data[7:end] if end >= 7 else b""
        out["header_rows"] = rows
        return out

    # ── RTU ──
    slave = data[0]
    out["slave"] = slave
    out["slave_label"] = "从站地址"
    pdu = data[1:-2]
    out["pdu"] = pdu
    out["pdu_offset"] = 1
    wire_crc = (data[-1] << 8) | data[-2]
    calc_crc = crc16(data[:-2])
    crc_ok = wire_crc == calc_crc
    out["crc_ok"] = crc_ok
    rows.append(
        (
            "传输类型",
            "-",
            "Modbus RTU",
            "从站地址（1B）+ PDU + CRC16（2B，低字节在前）",
            None,
            None,
        )
    )
    rows.append(
        (
            "从站地址",
            f"{slave:02X}",
            str(slave),
            (
                "广播地址（0）：从站执行但不响应"
                if slave == 0
                else f"从站/设备地址 {slave}（0x{slave:02X}）"
            ),
            0,
            0,
        )
    )
    out["header_rows"] = rows
    out["trailer_rows"] = [
        (
            "CRC16",
            _hex(data[-2:]),
            f"0x{wire_crc:04X}",
            (
                f"校验通过（计算值 0x{calc_crc:04X}）"
                if crc_ok
                else f"校验失败：按帧内容计算应为 0x{calc_crc:04X}，实际 0x{wire_crc:04X}"
                "（帧可能被截断、拼接或含有前导/尾随字节）"
            ),
            len(data) - 2,
            len(data) - 1,
        )
    ]
    if not crc_ok:
        out["warnings"].append("RTU CRC16 校验失败")
    if not pdu:
        out["error"] = "CRC 之前的 PDU 为空（帧过短）"
    return out


# ── 寄存器列表（profile）辅助 ───────────────────────────────────────


def _profile_entries(profile: Optional[dict]) -> Dict[int, dict]:
    """profile → {地址: 条目}（跳过非法条目）。"""
    if not isinstance(profile, dict):
        return {}
    entries: Dict[int, dict] = {}
    for raw in profile.get("registers") or []:
        if not isinstance(raw, dict):
            continue
        try:
            addr = int(raw.get("addr"))
        except (TypeError, ValueError):
            continue
        if not 0 <= addr <= 0xFFFF:
            continue
        entries[addr] = raw
    return entries


def profile_start(profile: Optional[dict]) -> Optional[int]:
    """profile 的读取起始地址：显式 ``start_addr`` 优先，否则取最小地址。"""
    if not isinstance(profile, dict):
        return None
    raw = profile.get("start_addr")
    try:
        if raw is not None and str(raw).strip() != "":
            value = int(raw)
            if 0 <= value <= 0xFFFF:
                return value
    except (TypeError, ValueError):
        pass
    entries = _profile_entries(profile)
    if entries:
        return min(entries)
    return None


def profile_name(profile: Optional[dict]) -> str:
    """profile 名称（无 profile 时给通用解析文案）。"""
    if isinstance(profile, dict) and str(profile.get("name") or "").strip():
        return str(profile["name"]).strip()
    return "通用解析（未指定寄存器列表）"


def _entry_count(entry: Optional[dict]) -> int:
    """条目占用的寄存器个数（按数据类型推导，非法则 1）。"""
    if not isinstance(entry, dict):
        return 1
    dtype = normalize_type(entry.get("type"))
    need = type_size(dtype)
    try:
        count = int(entry.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    if need:
        need_regs = need // 2
        if count < need_regs:
            count = need_regs
    if count < 1:
        count = 1
    return min(count, 120)


def _apply_byte_order(raw: bytes, *, byte_order: str, word_order: str) -> bytes:
    """按字节序 / 字序重排寄存器原始字节，统一成大端整数语义。"""
    data = bytes(raw)
    if len(data) % 2:
        data = data[:-1]
    if not data:
        return b""
    words = [data[i : i + 2] for i in range(0, len(data), 2)]
    if str(byte_order).lower() == "little":
        words = [word[::-1] for word in words]
    if str(word_order).lower() == "little":
        words = list(reversed(words))
    return b"".join(words)


def decode_value(
    raw: bytes,
    entry: Optional[dict],
    profile: Optional[dict] = None,
) -> Dict[str, Any]:
    """把一个寄存器的原始字节解码为数值。

    Returns dict: ``value``（缩放后的数值或原始文本）、``raw_value``（缩放前）、
    ``dtype``、``scale``、``unit``、``text``（展示文本）、``raw``。
    """
    data = bytes(raw or b"")
    entry = entry if isinstance(entry, dict) else {}
    dtype = normalize_type(entry.get("type"))
    byte_order = str((profile or {}).get("byte_order") or "big")
    word_order = str((profile or {}).get("word_order") or "big")
    try:
        scale = float(entry.get("scale", 1) if entry.get("scale") not in (None, "") else 1)
    except (TypeError, ValueError):
        scale = 1.0
    unit = str(entry.get("unit") or "").strip()

    # 按条目声明的字节数裁剪（hex/ascii 用全部字节）
    size = type_size(dtype)
    if size and len(data) > size:
        data = data[:size]
    buf = _apply_byte_order(data, byte_order=byte_order, word_order=word_order)

    raw_value: Any
    text: str
    if dtype in ("uint16", "uint32", "uint64"):
        raw_value = int.from_bytes(buf, "big", signed=False)
        text = format_number(raw_value)
    elif dtype in ("int16", "int32", "int64"):
        raw_value = int.from_bytes(buf, "big", signed=True)
        text = format_number(raw_value)
    elif dtype == "float32":
        raw_value = (
            struct.unpack(">f", buf.ljust(4, b"\x00")[:4])[0] if buf else 0.0
        )
        text = format_number(raw_value)
    elif dtype == "float64":
        raw_value = (
            struct.unpack(">d", buf.ljust(8, b"\x00")[:8])[0] if buf else 0.0
        )
        text = format_number(raw_value)
    elif dtype == "bit":
        raw_value = int.from_bytes(buf or b"\x00", "big") & 0x01
        text = "1（ON/置位）" if raw_value else "0（OFF/复位）"
    elif dtype == "ascii":
        raw_value = None
        text = data.decode("ascii", errors="replace").strip("\x00").strip()
    else:  # hex
        raw_value = None
        text = "0x" + (data.hex().upper() if data else "")

    scaled = raw_value
    if raw_value is not None and dtype not in ("bit", "ascii", "hex"):
        scaled = raw_value * scale
        text = format_number(scaled)
    if unit and text:
        text = f"{text} {unit}"
    return {
        "value": scaled,
        "raw_value": raw_value,
        "dtype": dtype,
        "scale": scale,
        "unit": unit,
        "text": text or "-",
        "raw": data,
    }


def _entry_comment(entry: dict, profile: Optional[dict], addr: int) -> str:
    """寄存器条目的说明文本（名称 + 类型 + 系数 + 单位 + 备注）。"""
    parts: List[str] = []
    name = str(entry.get("name") or "").strip()
    if name:
        parts.append(name)
    dtype = normalize_type(entry.get("type"))
    detail = f"{type_label(dtype)}"
    try:
        scale = float(entry.get("scale", 1) if entry.get("scale") not in (None, "") else 1)
    except (TypeError, ValueError):
        scale = 1.0
    if abs(scale - 1.0) > 1e-12:
        detail += f" × {format_number(scale)}"
    unit = str(entry.get("unit") or "").strip()
    if unit:
        detail += f" {unit}"
    parts.append(detail)
    try:
        count = _entry_count(entry)
    except Exception:  # noqa: BLE001
        count = 1
    if count > 1:
        parts.append(f"占 {count} 个寄存器（0x{addr:04X}~0x{addr + count - 1:04X}）")
    note = str(entry.get("note") or "").strip()
    if note:
        parts.append(note)
    return "；".join(parts) if parts else "寄存器列表中已定义"


def _register_rows(
    data: bytes,
    *,
    start_addr: int,
    profile: Optional[dict],
    base_offset: int,
    has_profile: bool,
) -> Tuple[List[Row], List[Dict[str, Any]]]:
    """把一段寄存器字节流按地址顺序切成每个寄存器的明细行。

    ``start_addr`` 是数据流第一个寄存器对应的地址；有 profile 时按条目
    声明的 ``count`` 消费字节，未定义地址按单寄存器（2 字节）推进。
    """
    rows: List[Row] = []
    registers: List[Dict[str, Any]] = []
    entries = _profile_entries(profile) if has_profile else {}
    addr = start_addr
    off = 0
    total = len(data) - (len(data) % 2)
    while off + 1 < total:
        entry = entries.get(addr)
        count = _entry_count(entry) if entry else 1
        need = count * 2
        if off + need > total:
            # 剩余字节不足以满足该条目：按剩余字节尽力解码
            remain = total - off
            if remain < 2:
                break
            need = remain
            entry = None
            count = need // 2
        raw = data[off : off + need]
        decoded = decode_value(raw, entry, profile)
        if entry:
            name = str(entry.get("name") or "").strip() or f"寄存器 0x{addr:04X}"
            field = f"  寄存器 0x{addr:04X} {name}"
            comment = _entry_comment(entry, profile, addr)
        else:
            field = f"  寄存器 0x{addr:04X}"
            if has_profile:
                comment = "寄存器列表中未定义该地址；按 16 位无符号显示原始值"
            else:
                comment = (
                    "未指定寄存器列表：地址按响应顺序从本例起点推导，"
                    "如需按品牌寄存器表翻译请在上方「寄存器列表」中选择"
                )
        rows.append(
            (
                field,
                _hex(raw),
                decoded["text"],
                comment,
                base_offset + off,
                base_offset + off + len(raw) - 1,
            )
        )
        registers.append(
            {
                "addr": addr,
                "count": count,
                "raw": raw,
                "value": decoded["value"],
                "text": decoded["text"],
                "entry": entry,
            }
        )
        off += need
        addr += count
    return rows, registers


def _bit_rows(
    data: bytes,
    *,
    start_addr: int,
    profile: Optional[dict],
    base_offset: int,
    kind: str,
) -> Tuple[List[Row], List[Dict[str, Any]]]:
    """位数据（线圈/离散输入）→ 每个位一行。"""
    rows: List[Row] = []
    bits: List[Dict[str, Any]] = []
    entries = _profile_entries(profile) if isinstance(profile, dict) else {}
    limit = min(len(data) * 8, 256)
    for i in range(limit):
        byte = data[i // 8]
        value = (byte >> (i % 8)) & 0x01
        addr = start_addr + i
        entry = entries.get(addr)
        name = str((entry or {}).get("name") or "").strip()
        field = f"  {kind} 0x{addr:04X}" + (f" {name}" if name else "")
        comment = name or "未在寄存器列表中定义"
        rows.append(
            (
                field,
                f"{value:02X}",
                "1（ON）" if value else "0（OFF）",
                comment,
                base_offset + i // 8,
                base_offset + i // 8,
            )
        )
        bits.append({"addr": addr, "value": value})
    return rows, bits


# ── PDU 解析 ───────────────────────────────────────────────────────


def _u16(data: bytes, pos: int) -> int:
    """大端读 2 字节（越界返回 0）。"""
    if pos + 2 > len(data):
        return 0
    return (data[pos] << 8) | data[pos + 1]


def _func_label(func: int) -> str:
    name = FUNC_NAMES.get(func, ("未知功能码", "Modbus 规范未定义或厂商自定义功能码"))[0]
    return f"0x{func:02X} {name}"


def _decode_exception(pdu: bytes, base: int) -> Dict[str, Any]:
    """异常响应（功能码最高位置 1）。"""
    func = pdu[0] & 0x7F
    code = pdu[1] if len(pdu) > 1 else 0
    name, desc = FUNC_NAMES.get(func, ("未知功能码", ""))
    rows: List[Row] = [
        (
            "功能码",
            f"{pdu[0]:02X}",
            f"0x{pdu[0]:02X}（0x{func:02X} 异常响应）",
            f"{name}：{desc}（从站以异常响应拒绝请求）",
            base,
            base,
        )
    ]
    if len(pdu) > 1:
        reason = EXCEPTION_CODES.get(code, "未定义异常码")
        rows.append(
            (
                "异常码",
                f"{code:02X}",
                f"0x{code:02X} {reason}",
                "Modbus 应用协议规范 7 异常响应（最高位为 1 表示异常）",
                base + 1,
                base + 1,
            )
        )
    else:
        rows.append(
            ("异常码", "", "", "异常响应缺少异常码字节（帧被截断）", None, None)
        )
    return {
        "func": func,
        "func_name": f"{name}（异常响应）",
        "direction": "响应",
        "is_exception": True,
        "exception_code": code if len(pdu) > 1 else None,
        "rows": rows,
        "registers": [],
        "bits": [],
        "warnings": [],
        "error": "",
    }


def decode_pdu(
    pdu: bytes,
    *,
    base: int = 0,
    profile: Optional[dict] = None,
    transport: str = TRANSPORT_RTU,
) -> Dict[str, Any]:
    """解析 PDU（不含 RTU 地址与 CRC / TCP MBAP 头）。

    Args:
        pdu: 纯 PDU 字节（首字节为功能码）
        base: PDU 在整帧中的起始偏移（用于表格字节位置）
        profile: 寄存器列表（``None`` = 通用解析）
        transport: ``rtu``/``tcp``（仅用于说明文案）

    Returns dict: func / func_name / direction / rows / registers / bits /
    warnings / error / is_exception / exception_code
    """
    pdu = bytes(pdu or b"")
    out: Dict[str, Any] = {
        "func": None,
        "func_name": "",
        "direction": "",
        "is_exception": False,
        "exception_code": None,
        "rows": [],
        "registers": [],
        "bits": [],
        "warnings": [],
        "error": "",
    }
    if not pdu:
        out["error"] = "PDU 为空（帧被截断或只有地址/CRC）"
        return out

    func = pdu[0]
    if func & 0x80:
        return _decode_exception(pdu, base)

    out["func"] = func
    name, desc = FUNC_NAMES.get(
        func, (f"未知功能码 0x{func:02X}", "Modbus 规范未定义或厂商自定义功能码")
    )
    out["func_name"] = name
    rows: List[Row] = [
        (
            "功能码",
            f"{func:02X}",
            f"0x{func:02X} {name}",
            desc,
            base,
            base,
        )
    ]
    body = pdu[1:]
    entries = _profile_entries(profile) if isinstance(profile, dict) else {}
    p_start = profile_start(profile)
    has_profile = isinstance(profile, dict) and bool(entries)
    def finish(direction: str) -> Dict[str, Any]:
        out["direction"] = direction
        out["rows"] = rows
        return out

    # ── 0x01 / 0x02 读线圈、读离散输入 ──
    if func in (0x01, 0x02):
        kind = "线圈" if func == 0x01 else "离散输入"
        is_response = (
            len(pdu) >= 3 and body[0] > 0 and 2 + body[0] == len(pdu)
        )
        if is_response:
            byte_count = body[0]
            data = body[1 : 1 + byte_count]
            rows.append(
                (
                    "字节数",
                    f"{byte_count:02X}",
                    str(byte_count),
                    f"位数据 {byte_count} 字节（最多 {byte_count * 8} 个{kind}）",
                    base + 1,
                    base + 1,
                )
            )
            rows.append(
                (
                    "位数据",
                    _hex(data),
                    f"{len(data)} 字节",
                    f"{kind}状态按字节打包，低位在前",
                    base + 2,
                    base + 1 + len(data),
                )
            )
            start = p_start if p_start is not None else 0
            bit_rows, bits = _bit_rows(
                data,
                start_addr=start,
                profile=profile,
                base_offset=base + 2,
                kind=kind,
            )
            out["bits"] = bits
            if not has_profile and bit_rows:
                rows.append(
                    (
                        "起始地址",
                        "-",
                        format_addr(start),
                        "响应帧不含起始地址：未选寄存器列表时按 0x0000 起推导，"
                        "请据实际请求帧核对",
                        None,
                        None,
                    )
                )
            rows.extend(bit_rows)
            return finish("响应")
        if len(pdu) >= 5:
            start = _u16(body, 0)
            qty = _u16(body, 2)
            rows.append(
                (
                    "起始地址",
                    _hex(body[0:2]),
                    format_addr(start),
                    f"读取起始{kind}地址（0x 区）" if func == 0x01 else "读取起始离散输入地址",
                    base + 1,
                    base + 2,
                )
            )
            rows.append(
                (
                    f"{kind}数量",
                    _hex(body[2:4]),
                    str(qty),
                    f"读取 {qty} 个{kind}（响应将占 {(qty + 7) // 8} 字节位数据）",
                    base + 3,
                    base + 4,
                )
            )
            if has_profile and qty:
                for addr in range(start, min(start + qty, start + 256)):
                    entry = entries.get(addr)
                    name_txt = str((entry or {}).get("name") or "").strip()
                    rows.append(
                        (
                            f"  {kind} 0x{addr:04X}" + (f" {name_txt}" if name_txt else ""),
                            "",
                            name_txt or "（寄存器列表中未定义）",
                            "该地址将被读取（请求帧声明范围）",
                            None,
                            None,
                        )
                    )
            out["warnings"].append(
                f"请求帧：读取起始 0x{start:04X} 起的 {qty} 个{kind}，响应帧不含地址信息"
            )
            return finish("请求")
        rows.append(("数据", _hex(body), "", f"{kind}读写请求长度不足 4 字节", base + 1, base + len(pdu) - 1))
        return finish("未知")

    # ── 0x03 / 0x04 读保持寄存器、读输入寄存器 ──
    if func in (0x03, 0x04):
        kind = "保持寄存器" if func == 0x03 else "输入寄存器"
        is_response = (
            len(pdu) >= 4 and body[0] > 0 and 2 + body[0] == len(pdu) and body[0] % 2 == 0
        )
        if is_response:
            byte_count = body[0]
            data = body[1 : 1 + byte_count]
            rows.append(
                (
                    "字节数",
                    f"{byte_count:02X}",
                    str(byte_count),
                    f"寄存器数据 {byte_count} 字节（{byte_count // 2} 个寄存器）",
                    base + 1,
                    base + 1,
                )
            )
            start = p_start if p_start is not None else 0
            reg_rows, regs = _register_rows(
                data,
                start_addr=start,
                profile=profile,
                base_offset=base + 2,
                has_profile=has_profile,
            )
            if not has_profile:
                rows.append(
                    (
                        "起始地址",
                        "-",
                        format_addr(start),
                        "响应帧**不含寄存器地址**：未选寄存器列表时按 0x0000 起推导；"
                        "如需品牌语义请选择寄存器列表",
                        None,
                        None,
                    )
                )
            rows.extend(reg_rows)
            out["registers"] = regs
            return finish("响应")

        if len(pdu) >= 5:
            start = _u16(body, 0)
            qty = _u16(body, 2)
            rows.append(
                (
                    "起始地址",
                    _hex(body[0:2]),
                    format_addr(start),
                    f"读取起始{kind}地址（{'4x' if func == 0x03 else '3x'} 区）",
                    base + 1,
                    base + 2,
                )
            )
            rows.append(
                (
                    "寄存器数量",
                    _hex(body[2:4]),
                    str(qty),
                    f"读取 {qty} 个{kind}（响应数据 {qty * 2} 字节）",
                    base + 3,
                    base + 4,
                )
            )
            if has_profile and qty:
                for addr in range(start, min(start + qty, start + 256)):
                    entry = entries.get(addr)
                    name_txt = str((entry or {}).get("name") or "").strip()
                    rows.append(
                        (
                            f"  寄存器 0x{addr:04X}" + (f" {name_txt}" if name_txt else ""),
                            "",
                            name_txt or "（寄存器列表中未定义）",
                            _entry_comment(entry, profile, addr) if entry else "该地址将被读取",
                            None,
                            None,
                        )
                    )
            out["warnings"].append(
                f"请求帧：读取起始 0x{start:04X} 起的 {qty} 个{kind}；响应帧不带地址，"
                "解析响应时请选择同一份寄存器列表"
            )
            return finish("请求")
        rows.append(("数据", _hex(body), "", f"{kind}读取请求长度不足 4 字节", base + 1, base + len(pdu) - 1))
        return finish("未知")

    # ── 0x05 写单个线圈 ──
    if func == 0x05:
        if len(pdu) < 5:
            rows.append(("数据", _hex(body), "", "写单个线圈请求长度不足 4 字节", base + 1, base + len(pdu) - 1))
            return finish("未知")
        addr = _u16(body, 0)
        value = _u16(body, 2)
        entry = entries.get(addr)
        name_txt = str((entry or {}).get("name") or "").strip()
        rows.append(
            (
                "线圈地址",
                _hex(body[0:2]),
                format_addr(addr) + (f" {name_txt}" if name_txt else ""),
                "写入的线圈地址（0x 区）",
                base + 1,
                base + 2,
            )
        )
        if value == 0xFF00:
            text, note = "ON（0xFF00）", "规范要求写 ON 必须用 0xFF00"
        elif value == 0x0000:
            text, note = "OFF（0x0000）", "规范要求写 OFF 必须用 0x0000"
        else:
            text, note = f"非法值 0x{value:04X}", "写单个线圈只接受 0xFF00 / 0x0000"
        rows.append(("写入值", _hex(body[2:4]), text, note, base + 3, base + 4))
        out["warnings"].append(f"写单个线圈：0x{addr:04X} ← {text}")
        return finish("请求/响应（写单个线圈的请求与响应帧结构相同）")

    # ── 0x06 写单个寄存器 ──
    if func == 0x06:
        if len(pdu) < 5:
            rows.append(("数据", _hex(body), "", "写单个寄存器请求长度不足 4 字节", base + 1, base + len(pdu) - 1))
            return finish("未知")
        addr = _u16(body, 0)
        value_raw = body[2:4]
        entry = entries.get(addr)
        name_txt = str((entry or {}).get("name") or "").strip()
        rows.append(
            (
                "寄存器地址",
                _hex(body[0:2]),
                format_addr(addr) + (f" {name_txt}" if name_txt else ""),
                "写入的保持寄存器地址（4x 区）",
                base + 1,
                base + 2,
            )
        )
        decoded = decode_value(value_raw, entry, profile)
        rows.append(
            (
                "写入值",
                _hex(value_raw),
                f"0x{_u16(value_raw, 0):04X}（{decoded['text']}）",
                _entry_comment(entry, profile, addr) if entry else "未指定寄存器列表：按 16 位无符号显示",
                base + 3,
                base + 4,
            )
        )
        out["warnings"].append(
            f"写单个寄存器：0x{addr:04X} ← 0x{_u16(value_raw, 0):04X}"
        )
        return finish("请求/响应（写单个寄存器的请求与响应帧结构相同）")

    # ── 0x0F 写多个线圈 ──
    if func == 0x0F:
        # 请求：起址(2) 数量(2) 字节数(1) 位数据(n)
        is_request = (
            len(pdu) >= 7 and body[4] > 0 and 6 + body[4] == len(pdu)
        )
        if is_request:
            start = _u16(body, 0)
            qty = _u16(body, 2)
            byte_count = body[4]
            data = body[5 : 5 + byte_count]
            rows.append(("起始地址", _hex(body[0:2]), format_addr(start), "写入起始线圈地址", base + 1, base + 2))
            rows.append(("线圈数量", _hex(body[2:4]), str(qty), f"写入 {qty} 个线圈", base + 3, base + 4))
            rows.append(("字节数", f"{byte_count:02X}", str(byte_count), f"位数据 {byte_count} 字节", base + 5, base + 5))
            rows.append(
                (
                    "位数据",
                    _hex(data),
                    f"{qty} 个线圈",
                    "按位打包，低位在前",
                    base + 6,
                    base + 5 + len(data),
                )
            )
            bit_rows, bits = _bit_rows(
                data, start_addr=start, profile=profile, base_offset=base + 6, kind="线圈"
            )
            rows.extend(bit_rows)
            out["bits"] = bits
            out["warnings"].append(f"写多个线圈：起始 0x{start:04X}，共 {qty} 个")
            return finish("请求")
        if len(pdu) >= 5:
            start = _u16(body, 0)
            qty = _u16(body, 2)
            rows.append(("起始地址", _hex(body[0:2]), format_addr(start), "已写入的起始线圈地址", base + 1, base + 2))
            rows.append(("线圈数量", _hex(body[2:4]), str(qty), f"已写入 {qty} 个线圈", base + 3, base + 4))
            return finish("响应")
        rows.append(("数据", _hex(body), "", "写多个线圈长度不足", base + 1, base + len(pdu) - 1))
        return finish("未知")

    # ── 0x10 写多个寄存器 ──
    if func == 0x10:
        is_request = (
            len(pdu) >= 8 and body[4] > 0 and 6 + body[4] == len(pdu) and body[4] % 2 == 0
        )
        if is_request:
            start = _u16(body, 0)
            qty = _u16(body, 2)
            byte_count = body[4]
            data = body[5 : 5 + byte_count]
            rows.append(("起始地址", _hex(body[0:2]), format_addr(start), "写入起始保持寄存器地址", base + 1, base + 2))
            rows.append(("寄存器数量", _hex(body[2:4]), str(qty), f"写入 {qty} 个寄存器", base + 3, base + 4))
            rows.append(("字节数", f"{byte_count:02X}", str(byte_count), f"寄存器数据 {byte_count} 字节", base + 5, base + 5))
            reg_rows, regs = _register_rows(
                data,
                start_addr=start,
                profile=profile,
                base_offset=base + 6,
                has_profile=has_profile,
            )
            rows.extend(reg_rows)
            out["registers"] = regs
            out["warnings"].append(f"写多个寄存器：起始 0x{start:04X}，共 {qty} 个")
            return finish("请求")
        if len(pdu) >= 5:
            start = _u16(body, 0)
            qty = _u16(body, 2)
            rows.append(("起始地址", _hex(body[0:2]), format_addr(start), "已写入的起始寄存器地址", base + 1, base + 2))
            rows.append(("寄存器数量", _hex(body[2:4]), str(qty), f"已写入 {qty} 个寄存器", base + 3, base + 4))
            return finish("响应")
        rows.append(("数据", _hex(body), "", "写多个寄存器长度不足", base + 1, base + len(pdu) - 1))
        return finish("未知")

    # ── 0x16 屏蔽写寄存器 ──
    if func == 0x16:
        if len(pdu) < 7:
            rows.append(("数据", _hex(body), "", "屏蔽写寄存器长度不足 6 字节", base + 1, base + len(pdu) - 1))
            return finish("未知")
        addr = _u16(body, 0)
        and_mask = _u16(body, 2)
        or_mask = _u16(body, 4)
        entry = entries.get(addr)
        name_txt = str((entry or {}).get("name") or "").strip()
        rows.append(
            (
                "寄存器地址",
                _hex(body[0:2]),
                format_addr(addr) + (f" {name_txt}" if name_txt else ""),
                "被修改的保持寄存器地址",
                base + 1,
                base + 2,
            )
        )
        rows.append(("AND 掩码", _hex(body[2:4]), f"0x{and_mask:04X}", "结果 = (当前值 AND 掩码)", base + 3, base + 4))
        rows.append(("OR 掩码", _hex(body[4:6]), f"0x{or_mask:04X}", "结果 = (上述结果 OR 掩码)", base + 5, base + 6))
        return finish("请求/响应（屏蔽写的请求与响应帧结构相同）")

    # ── 0x17 读/写多个寄存器 ──
    if func == 0x17:
        is_response = (
            len(pdu) >= 3 and body[0] > 0 and 2 + body[0] == len(pdu) and body[0] % 2 == 0
        )
        if is_response:
            byte_count = body[0]
            data = body[1 : 1 + byte_count]
            rows.append(("字节数", f"{byte_count:02X}", str(byte_count), f"读回数据 {byte_count} 字节（{byte_count // 2} 个寄存器）", base + 1, base + 1))
            start = p_start if p_start is not None else 0
            reg_rows, regs = _register_rows(
                data,
                start_addr=start,
                profile=profile,
                base_offset=base + 2,
                has_profile=has_profile,
            )
            if not has_profile:
                rows.append(
                    (
                        "起始地址",
                        "-",
                        format_addr(start),
                        "响应帧不含地址：未选寄存器列表时按 0x0000 起推导",
                        None,
                        None,
                    )
                )
            rows.extend(reg_rows)
            out["registers"] = regs
            return finish("响应")
        if len(pdu) >= 10:
            read_start = _u16(body, 0)
            read_qty = _u16(body, 2)
            write_start = _u16(body, 4)
            write_qty = _u16(body, 6)
            byte_count = body[8]
            data = body[9 : 9 + byte_count]
            rows.append(("读起始地址", _hex(body[0:2]), format_addr(read_start), "本次读取的起始寄存器地址", base + 1, base + 2))
            rows.append(("读寄存器数量", _hex(body[2:4]), str(read_qty), f"读取 {read_qty} 个寄存器", base + 3, base + 4))
            rows.append(("写起始地址", _hex(body[4:6]), format_addr(write_start), "同一次交互中写入的起始地址", base + 5, base + 6))
            rows.append(("写寄存器数量", _hex(body[6:8]), str(write_qty), f"写入 {write_qty} 个寄存器", base + 7, base + 8))
            rows.append(("写字节数", f"{byte_count:02X}", str(byte_count), f"写入数据 {byte_count} 字节", base + 9, base + 9))
            reg_rows, regs = _register_rows(
                data,
                start_addr=write_start,
                profile=profile,
                base_offset=base + 10,
                has_profile=has_profile,
            )
            for row in reg_rows:
                rows.append((row[0].replace("寄存器", "写入寄存器", 1),) + row[1:])
            out["registers"] = regs
            out["warnings"].append(
                f"读写多个寄存器：读 0x{read_start:04X}×{read_qty}，写 0x{write_start:04X}×{write_qty}"
            )
            return finish("请求")
        rows.append(("数据", _hex(body), "", "读写多个寄存器长度不足", base + 1, base + len(pdu) - 1))
        return finish("未知")

    # ── 0x08 诊断 ──
    if func == 0x08:
        if len(pdu) >= 3:
            sub = _u16(body, 0)
            value = _u16(body, 2)
            sub_name = DIAG_SUBFUNCS.get(sub, "未定义诊断子功能")
            rows.append(("子功能码", _hex(body[0:2]), f"0x{sub:04X} {sub_name}", "诊断子功能（0x0000~0x0015）", base + 1, base + 2))
            if len(pdu) >= 5:
                rows.append(("数据", _hex(body[2:4]), f"0x{value:04X}（{value}）", "子功能对应的数据字段", base + 3, base + 4))
            return finish("请求/响应（诊断请求与响应帧结构相同）")
        rows.append(("数据", _hex(body), "", "诊断功能长度不足", base + 1, base + len(pdu) - 1))
        return finish("未知")

    # ── 0x2B 设备识别 ──
    if func == 0x2B:
        if len(pdu) >= 2:
            mei = body[0]
            rows.append(("MEI 类型", f"{mei:02X}", f"0x{mei:02X}", "0x0E = 读设备识别（Read Device Identification）", base + 1, base + 1))
            if mei == 0x0E and len(pdu) >= 4:
                read_code = body[1]
                object_id = body[2]
                rows.append(
                    (
                        "读取码",
                        f"{read_code:02X}",
                        f"0x{read_code:02X} {DEVICE_ID_READ_CODES.get(read_code, '')}".strip(),
                        "设备识别读取类型",
                        base + 2,
                        base + 2,
                    )
                )
                rows.append(
                    (
                        "对象 ID",
                        f"{object_id:02X}",
                        f"0x{object_id:02X} {DEVICE_ID_OBJECTS.get(object_id, '')}".strip(),
                        "起始读取的对象标识",
                        base + 3,
                        base + 3,
                    )
                )
                # 响应：MEI + readCode + conformity + moreFollows + nextObjectId + 对象列表
                if len(pdu) >= 6:
                    conformity = body[2]
                    more = body[3]
                    next_id = body[4]
                    rows.append(("一致性等级", f"{conformity:02X}", f"0x{conformity:02X}", "0x01 基本 / 0x02 常规 / 0x03 扩展", base + 3, base + 3))
                    rows.append(("后续标志", f"{more:02X}", "有后续对象" if more else "本次已返回全部对象", "More Follows", base + 4, base + 4))
                    rows.append(("下一对象 ID", f"{next_id:02X}", f"0x{next_id:02X}", "后续请求的起始对象", base + 5, base + 5))
                    pos = base + 6
                    idx = 6
                    while idx + 2 <= len(pdu):
                        obj_id = pdu[idx]
                        obj_len = pdu[idx + 1]
                        obj_data = pdu[idx + 2 : idx + 2 + obj_len]
                        rows.append(
                            (
                                f"  对象 0x{obj_id:02X} {DEVICE_ID_OBJECTS.get(obj_id, '')}".rstrip(),
                                _hex(obj_data),
                                obj_data.decode("ascii", errors="replace"),
                                "设备识别对象值（ASCII）",
                                pos,
                                pos + len(obj_data) + 1,
                            )
                        )
                        idx += 2 + obj_len
                        pos += 2 + obj_len
                return finish("请求" if len(pdu) <= 5 else "响应")
            return finish("请求/响应")
        rows.append(("数据", _hex(body), "", "设备识别功能长度不足", base + 1, base + len(pdu) - 1))
        return finish("未知")

    # ── 其它功能码：原样展示 ──
    rows.append(
        (
            "  数据",
            _hex(body),
            f"{len(body)} 字节",
            "该功能码暂未做字段级解析，已给出原始数据；如需扩展请联系维护者",
            base + 1,
            base + len(pdu) - 1,
        )
    )
    return finish("未知")


# ── 组装：整帧解析 ──────────────────────────────────────────────────


def parse_frame(data: bytes, profile: Optional[dict] = None) -> Dict[str, Any]:
    """解析一帧 Modbus（RTU/TCP），返回结构化结果与表格行。

    Returns dict:
        rows / transport / slave / func / func_name / direction / summary /
        registers / bits / warnings / error / crc_ok / length_ok
    """
    data = bytes(data or b"")
    split = split_frame(data)
    result: Dict[str, Any] = {
        "rows": [],
        "transport": split["transport"],
        "slave": split["slave"],
        "func": None,
        "func_name": "",
        "direction": "",
        "summary": "",
        "registers": [],
        "bits": [],
        "warnings": list(split["warnings"]),
        "error": split["error"],
        "crc_ok": split["crc_ok"],
        "length_ok": split["length_ok"],
        "profile": profile if isinstance(profile, dict) else None,
    }
    if split["error"] and not split["pdu"]:
        result["rows"] = list(split["header_rows"]) + [
            ("❌ 解析失败", "", "", split["error"], 0, max(0, len(data) - 1))
        ]
        result["summary"] = split["error"]
        return result

    pdu_info = decode_pdu(
        split["pdu"],
        base=split["pdu_offset"],
        profile=profile,
        transport=split["transport"],
    )
    result["func"] = pdu_info["func"]
    result["func_name"] = pdu_info["func_name"]
    result["direction"] = pdu_info["direction"]
    result["registers"] = pdu_info["registers"]
    result["bits"] = pdu_info["bits"]
    result["warnings"].extend(pdu_info["warnings"])
    if pdu_info.get("is_exception"):
        result["warnings"].append(
            f"异常响应：0x{pdu_info['exception_code'] or 0:02X} "
            f"{EXCEPTION_CODES.get(pdu_info['exception_code'] or 0, '')}".strip()
        )

    rows: List[Row] = list(split["header_rows"])
    rows.append(
        (
            "寄存器列表",
            "-",
            profile_name(profile),
            (
                "按所选寄存器列表翻译地址/取值"
                if isinstance(profile, dict)
                else "未选择寄存器列表：只解析功能码、地址/数量与原始寄存器值"
            ),
            None,
            None,
        )
    )
    if pdu_info["error"]:
        rows.append(("❌ 解析失败", "", "", pdu_info["error"], 0, max(0, len(data) - 1)))
        result["rows"] = rows
        result["summary"] = pdu_info["error"]
        return result
    rows.extend(pdu_info["rows"])
    rows.extend(split["trailer_rows"])
    result["rows"] = rows
    result["summary"] = _make_summary(result, split, pdu_info, profile)
    return result


def _make_summary(
    result: Dict[str, Any],
    split: Dict[str, Any],
    pdu_info: Dict[str, Any],
    profile: Optional[dict],
) -> str:
    """一句话摘要（批量列表 / 状态栏用）。"""
    parts: List[str] = []
    if isinstance(profile, dict):
        parts.append(profile_name(profile))
    parts.append(f"从站{result['slave']}" if split["transport"] == TRANSPORT_RTU else f"单元{result['slave']}")
    if pdu_info.get("is_exception"):
        code = pdu_info.get("exception_code") or 0
        parts.append(f"异常响应 0x{code:02X}")
    else:
        parts.append(_func_label(pdu_info["func"]) if pdu_info.get("func") is not None else "-")
        direction = pdu_info.get("direction") or ""
        if direction:
            parts.append(direction)
        regs = pdu_info.get("registers") or []
        if regs:
            first = regs[0]
            last = regs[-1]
            span = f"0x{first['addr']:04X}" if first["addr"] == last["addr"] else f"0x{first['addr']:04X}~0x{last['addr']:04X}"
            parts.append(f"{len(regs)} 个寄存器 {span}")
        bits = pdu_info.get("bits") or []
        if bits:
            parts.append(f"{len(bits)} 个位")
    if not result["crc_ok"] and split["transport"] == TRANSPORT_RTU:
        parts.append("CRC 错误")
    return " | ".join(parts)


# ── 批量帧提取 ─────────────────────────────────────────────────────


def _pdu_length_candidates(data: bytes, offset: int) -> List[int]:
    """按功能码推断 RTU 帧总长候选（含地址与 CRC），供 CRC 校验优先尝试。"""
    n = len(data) - offset
    if n < 3:
        return []
    func = data[offset + 1]
    if func & 0x80:
        func &= 0x7F
    cands: List[int] = []
    if func in (0x01, 0x02, 0x03, 0x04):
        byte_count = data[offset + 2] if n > 2 else 0
        cands.append(2 + byte_count + 3)  # 响应
        cands.append(1 + 5 + 2)  # 请求
    elif func in (0x05, 0x06, 0x16, 0x08, 0x0B, 0x0C, 0x11):
        cands.append(1 + 5 + 2)
        if func == 0x11:
            cands.append(1 + 4 + 2)
    elif func in (0x0F, 0x10):
        byte_count = data[offset + 6] if n > 6 else 0
        cands.append(1 + 6 + byte_count + 2)  # 请求
        cands.append(1 + 5 + 2)  # 响应
    elif func == 0x17:
        byte_count = data[offset + 10] if n > 10 else 0
        cands.append(1 + 10 + byte_count + 2)  # 请求
        resp_bc = data[offset + 2] if n > 2 else 0
        cands.append(2 + resp_bc + 3)  # 响应
    elif func == 0x2B:
        cands.append(1 + 4 + 2)
    else:
        cands.append(1 + 5 + 2)
    return [c for c in sorted(set(cands)) if 4 <= c <= 260]


def guess_frame_length(data: bytes, offset: int = 0) -> int:
    """从 ``offset`` 起推断一个 RTU/TCP 帧的总长；无法判断返回 0。"""
    n = len(data) - offset
    if n < 4:
        return 0
    # TCP：MBAP 长度域自洽 + 功能码合理
    expected = _tcp_expected_length(data, offset)
    if expected is not None and 8 <= expected <= n:
        func = data[offset + 7]
        if (func & 0x7F) in FUNC_NAMES:
            return expected
    # RTU：**功能码必须已知**才可能是帧起点 —— 日志里的时间戳/序号混进 hex 时，
    # 不加这道过滤纯靠 CRC 命中会把任意偏移当帧头（CRC 碰撞概率 1/65536/偏移）。
    func = data[offset + 1]
    if (func & 0x7F) not in FUNC_NAMES:
        return 0
    # 候选长度 CRC 校验（按功能码推导，命中率最高）
    for total in _pdu_length_candidates(data, offset):
        if _rtu_crc_ok(data, offset, total):
            return total
    # 兜底扫描：增量 CRC，命中即返回（处理厂商扩展长度）
    crc = 0xFFFF
    limit = min(len(data), offset + 260)
    for pos in range(offset, limit):
        crc = _crc16_update(crc, data[pos])
        total = pos - offset + 3  # 主体 + CRC(2)
        if total < 4 or offset + total > len(data):
            continue
        wire = (data[offset + total - 1] << 8) | data[offset + total - 2]
        if crc == wire:
            return total
    return 0


def split_stream(clean_hex: str) -> List[str]:
    """从一串连续 hex 中切出所有 Modbus 帧（RTU/TCP 均可）。

    逐偏移尝试（日志里的时间戳/序号会混进 hex），命中后按帧长前进。
    """
    text = re.sub(r"[^0-9A-Fa-f]", "", str(clean_hex or ""))
    if len(text) % 2:
        text = text[:-1]
    if len(text) < 8:
        return []
    data = bytes.fromhex(text)
    frames: List[str] = []
    i = 0
    while i <= len(data) - 4:
        length = guess_frame_length(data, i)
        if not length:
            i += 1
            continue
        frames.append(data[i : i + length].hex().upper())
        i += length
    return frames


#: 2 位十六进制 token（前后都不能再是 hex 字符，避免把长串切碎）
_HEX_TOKEN_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{2}(?![0-9A-Fa-f])")
#: token 之间的合法分隔符（只允许这些，时间戳里的 ``:`` / ``.`` 会切断分组）
_TOKEN_SEP_RE = re.compile(r"^[ \t,;\-]*$")


def hex_token_groups(line: str) -> List[str]:
    """把一行里「空格分隔的 hex 字节」按连续段分组（时间戳/序号自然被切开）。

    例：``15:49:51 254  -> 01 03 04 00 64 00 C8 BA 7A``
        ⇒ ``['010304006400C8BA7A']``（``15``/``20``/``01`` 这些单字节段长度不足被丢弃）
    """
    text = str(line or "")
    groups: List[str] = []
    current: List[str] = []
    prev_end: Optional[int] = None
    for match in _HEX_TOKEN_RE.finditer(text):
        if prev_end is not None and not _TOKEN_SEP_RE.match(text[prev_end : match.start()]):
            if current:
                groups.append("".join(current))
            current = []
        current.append(match.group(0))
        prev_end = match.end()
    if current:
        groups.append("".join(current))
    return groups


def extract_modbus_frames(text: str) -> List[Tuple[str, str, int]]:
    """批量解析用：日志文本 → ``[(hex, "", 行号), ...]``。

    每行至少一帧：

    1. 先按「空格分隔的 hex 字节段」分组（时间戳/序号不会被当成帧内容），
       每段再按 CRC16 / MBAP 长度域切分成一帧或多帧；
    2. 行内没有可分组 token 时（整行是连续 hex），清洗后整行切分；
    3. 切分不出来（CRC 被改坏、厂商扩展长度、只有片段）**把该段整段当一帧**
       继续往下传，由解析器在表格里标注 CRC 错误，而不是静默丢帧。
    """
    out: List[Tuple[str, str, int]] = []
    for line_no, raw_line in enumerate(str(text or "").splitlines()):
        frames: List[str] = []
        groups_all = hex_token_groups(raw_line)
        groups = [g for g in groups_all if len(g) >= 8]
        if not groups and groups_all:
            # 只有短字节段（如「01 83 02」这种被截断的帧）：取最长的那段交给解析器，
            # 由它明确报「帧长不足」，绝不把时间戳数字混进帧内容。
            longest = max(groups_all, key=len)
            if len(longest) >= 6:  # ≥3 字节才值得报错
                groups = [longest]
        for group in groups:
            frames.extend(split_stream(group) or [group])
        if not frames:
            # 没有可分组 token（整行连续 hex）：按下标 0/1 两种对齐各试一次。
            # 日志前缀（时间戳）长度可能是奇数，只按 0 对齐会让整行错位、切不出帧。
            hex_only = re.sub(r"[^0-9A-Fa-f]", "", raw_line)
            for shift in (0, 1):
                candidate = hex_only[shift:]
                if len(candidate) % 2:
                    candidate = candidate[:-1]
                if len(candidate) < 8:
                    continue
                frames = split_stream(candidate)
                if frames:
                    break
            if not frames:
                candidate = hex_only if len(hex_only) % 2 == 0 else hex_only[:-1]
                frames = [candidate] if len(candidate) >= 8 else []
        for frame in frames:
            out.append((frame.upper(), "", line_no))
    return out


__all__ = [
    "PROTOCOL_NAME",
    "TRANSPORT_RTU",
    "TRANSPORT_TCP",
    "TRANSPORT_LABELS",
    "FUNC_NAMES",
    "EXCEPTION_CODES",
    "DIAG_SUBFUNCS",
    "DEVICE_ID_READ_CODES",
    "DEVICE_ID_OBJECTS",
    "REG_TYPES",
    "TYPE_ALIASES",
    "crc16",
    "crc16_bytes",
    "lrc",
    "format_number",
    "format_addr",
    "type_label",
    "normalize_type",
    "type_size",
    "is_ascii_frame",
    "detect_transport",
    "split_frame",
    "decode_value",
    "decode_pdu",
    "parse_frame",
    "profile_start",
    "profile_name",
    "guess_frame_length",
    "split_stream",
    "extract_modbus_frames",
    "hex_token_groups",
]
