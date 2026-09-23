"""模组化终端功能模块接口协议 —— A-XDR 编解码「单源」。

依据（协议文档/12.模组化功能协议/模组化终端功能模块接口协议.md）：
  * §6.1「APDU 的标记规则遵循 ASN.1 的抽象语法，编码规则遵循 A-XDR，详见 DL/T 790.6—2010」
  * 表4（通用数据类型与标记）、表5（Data CHOICE）、表6~表12（date_time/date/time/date_time_s/DT/DAR/Scaler_Unit）
  * 表13~表21（APDU CHOICE 与 8 类 APDU 的 ASN.1）
  * 附录 A（FCS = PPP 的 fcstab，生成多项式 0x8408）

⚠ 协议12 文档**没有任何示例帧**，字节级布局由同族标准 DL/T 698.45 的真实编码实例推导
（`面向对象的用电信息数据交换协议(20210910).md` 附录 H.1.1「登录」）：

    01 ___ [1] LINK-Request
    00 ___ PID-ACD
    00 —— 请求类型：建立连接（0）
    00 B4 —— 心跳周期：180s                    ← 定长类型裸排、大端、无长度域
    07 E0 05 13 04 08 05 00 00 A4 —— 请求时间 date_time: 2016-05-19 08:05:00.0164

由此确证三条规则：
  ① A-XDR 多字节**大端**（`07 E0`=2016、`00 B4`=180、`00 A4`=164）；
  ② 定长类型（含带 SIZE 的 date_time/date/time/date_time_s、以及 octet-string(SIZE(n))）在
     SEQUENCE 内**不带 tag、不带长度域**；
  ③ 变长类型带长度域（1 字节，见开关 ③）。
自检：2016-05-19 是周四 → `day_of_week=04` ✓，`day_of_month=13H=19` ✓。

三条假设集中在下面三个开关里 —— 拿到真实帧后只改这里，**不要**在解析函数里各写一份猜测；
判据是 `verify_frame()["axdr_tail"]`（≠0 即假设与真实帧不符），组合只有 8 种，逐一切换即可。

另注（协议12 文档未给示例、按同族标准取值，实现时须留意）：
  * `array`/`structure` 的长度域是**元素个数**而非字节数 —— 依据 DL/T 698.45 附录 H.3.2
    （`01 array / 03 元素个数=3`）与本仓库既有的 `dl_t698_45_axdr.AXDRCoder`；
  * `bit-string` 内容 = 位宽(1B) + 位组，位序按字节内 LSB-first（协议12 附录 G.3 的
    「bit0 表示第一路」自证 bit0 是低位）；
  * 表18 的「虚拟通道工作模式」（`SEQUENCE OF {接口类型 enum, 功能配置 unsigned}`）按
    「个数(1B) + N×(1B + 1B)」编码（见 `encode_channel_list` / `decode_channel_list`）。
    另一种读法（每个元素再套一层 structure tag+count）会多出 2 字节/元素，
    **无文档示例可判**，故集中在这两个函数里，便于一处切换。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ── 编码假设开关（**唯一来源**，勿在别处再写一份）──────────────────────────

#: ① SEQUENCE 内的成员是否发 tag。默认 False —— 698 附录 H.1.1 直接实证：
#:   LINK-Request 的「请求时间 date_time」（表4 里带标记 25）在 SEQUENCE 内是**裸 10 字节**。
AXDR_TAG_IN_SEQUENCE = False

#: ② 定长类型作为 CHOICE 分支时是否附带长度域。默认 False —— 实证同上（`00 B4` 无长度字节）。
AXDR_LEN_FOR_FIXED_IN_CHOICE = False

#: ③ 变长类型长度域的字节数。默认 1。
AXDR_VAR_LENGTH_BYTES = 1

WEEKDAY_NAMES = ("周日", "周一", "周二", "周三", "周四", "周五", "周六")

DATE_TIME_FIELDS = (
    "year",
    "month",
    "day_of_month",
    "day_of_week",
    "hour",
    "minute",
    "second",
    "milliseconds",
)
DATE_TIME_S_FIELDS = ("year", "month", "day", "hour", "minute", "second")
DATE_FIELDS = ("year", "month", "day_of_month", "day_of_week")
TIME_FIELDS = ("hour", "minute", "second")

#: 2 字节字段（无效值 FFFFH）
_DATE_2B_FIELDS = ("year", "milliseconds")
#: 1 字节字段（无效值 FFH）
_DATE_1B_FIELDS = ("month", "day", "day_of_month", "day_of_week", "hour", "minute", "second")


# ── 异常 ──────────────────────────────────────────────────────────────


class AxdrError(ValueError):
    """A-XDR 编解码唯一异常类型；消息面向用户（含字段名与偏移）。"""

    def __init__(
        self,
        message: str,
        *,
        offset: int = 0,
        field: str = "",
        consumed: int = 0,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.offset = offset
        self.field = field
        #: 相对「传入缓冲区起点」已消费的字节数（由 decode_apdu 统一换算）
        self.consumed = consumed
        #: 出错前已成功解出的节点（供容错显示；见 AGENTS.md §8 陷阱 23）
        self.partial: List["AxdrNode"] = []


# ── 表4：通用数据类型与标记 ───────────────────────────────────────────


@dataclass(frozen=True)
class AxdrType:
    name: str
    tag: int  # 表4「标记」列；CHOICE 内作为 tag 字节
    fixed: Optional[int]  # 固定字节数；None = 变长（带长度域）
    multibyte: bool = False  # True 时多字节按大端解释
    signed: bool = False


#: 表4 逐条（25 类）。tag 即协议12 表4「标记」列的数字值。
AXDR_TYPES: Dict[str, AxdrType] = {
    "NULL": AxdrType("NULL", 0x00, 0),
    "array": AxdrType("array", 0x01, None),
    "structure": AxdrType("structure", 0x02, None),
    "bool": AxdrType("bool", 0x03, 1),
    "bit-string": AxdrType("bit-string", 0x04, None),
    "double-long": AxdrType("double-long", 0x05, 4, True, True),
    "double-long-unsigned": AxdrType("double-long-unsigned", 0x06, 4, True),
    "octet-string": AxdrType("octet-string", 0x09, None),
    "visible-string": AxdrType("visible-string", 0x0A, None),
    "UTF8-string": AxdrType("UTF8-string", 0x0C, None),
    "integer": AxdrType("integer", 0x0F, 1, False, True),
    "long": AxdrType("long", 0x10, 2, True, True),
    "unsigned": AxdrType("unsigned", 0x11, 1),
    "long-unsigned": AxdrType("long-unsigned", 0x12, 2, True),
    "long64": AxdrType("long64", 0x14, 8, True, True),
    "long64-unsigned": AxdrType("long64-unsigned", 0x15, 8, True),
    "enum": AxdrType("enum", 0x16, 1),
    "float32": AxdrType("float32", 0x17, 4, True),
    "float64": AxdrType("float64", 0x18, 8, True),
    "date_time": AxdrType("date_time", 0x19, 10),
    "date": AxdrType("date", 0x1A, 5),
    "time": AxdrType("time", 0x1B, 3),
    "date_time_s": AxdrType("date_time_s", 0x1C, 7),
    "DT": AxdrType("DT", 0x50, 2, True),
    "Scaler_Unit": AxdrType("Scaler_Unit", 0x51, 2),
}

AXDR_BY_TAG: Dict[int, AxdrType] = {t.tag: t for t in AXDR_TYPES.values()}

#: 表5 Data CHOICE：25 个分支即表4 的全部类型
DATA_CHOICE_TYPES = tuple(AXDR_TYPES)


def tag_of(type_name: str) -> int:
    """表4 标记值。"""
    t = AXDR_TYPES.get(type_name)
    if t is None:
        raise AxdrError(f"未知 A-XDR 类型：{type_name}")
    return t.tag


def type_of_tag(tag: int) -> Optional[AxdrType]:
    return AXDR_BY_TAG.get(tag)


def type_name_of_tag(tag: int) -> Optional[str]:
    t = AXDR_BY_TAG.get(tag)
    return t.name if t else None


# ── 解析节点 ──────────────────────────────────────────────────────────


@dataclass
class AxdrNode:
    """一个已解码的字段/结构节点。

    * ``value``：标量（int/float/str/bytes/None）、日期类为 dict、
      ``array``/``structure``/通道列表为 ``list[AxdrNode]``；
    * ``offset``：相对**调用方传入的缓冲区起点**的偏移（解析器再加帧内基底）；
    * ``raw``：该节点占用的原始字节（含 tag 与长度域）。
    """

    name: str
    type_name: str
    value: Any
    raw: bytes
    offset: int
    note: str = ""

    @property
    def children(self) -> Optional[List["AxdrNode"]]:
        return self.value if isinstance(self.value, list) else None


def describe_value(value: Any, type_name: str) -> str:
    """把解码值转成表格「解析值」列文本（纯结构描述，不查名称表）。"""
    if value is None:
        return "-"
    if type_name in ("date_time", "date_time_s", "date", "time"):
        return format_date_time(value, type_name)
    if type_name in ("octet-string", "visible-string", "UTF8-string"):
        return _decode_text(value, type_name)
    if type_name == "bit-string":
        return format_bit_string(value)
    if type_name == "Scaler_Unit":
        scaler = value.get("scaler", 0) if isinstance(value, dict) else 0
        unit = value.get("unit") if isinstance(value, dict) else None
        return f"换算=10^{scaler}，单位={unit}"
    if type_name == "DT":
        return f"0x{int(value):04X}"
    if type_name == "channel":
        iface = value.get("iface") if isinstance(value, dict) else None
        config = value.get("config") if isinstance(value, dict) else None
        return f"接口类型={iface}，功能配置={config}"
    if type_name in ("array", "structure"):
        return f"{len(value)}个元素"
    if type_name == "channel-list":
        return f"{len(value)}个虚拟通道"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _decode_text(value: Any, type_name: str) -> str:
    raw = bytes(value) if not isinstance(value, str) else value.encode("latin-1")
    if not raw:
        return "（空）"
    codec = "utf-8" if type_name == "UTF8-string" else "ascii"
    return raw.decode(codec, "replace")


def format_bit_string(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    nbits = int(value.get("bits") or 0)
    bits = value.get("data") or b""
    bit_text = "".join(
        "1" if (i >> 3) < len(bits) and (bits[i >> 3] >> (i & 7)) & 1 else "0"
        for i in range(nbits - 1, -1, -1)
    )
    set_bits = value.get("set") or []
    tail = f"，置位: {','.join(str(b) for b in set_bits)}" if set_bits else "，无置位"
    return f"{nbits}位 {bit_text}{tail}"


def format_date_time(value: Dict[str, Any], type_name: str = "date_time") -> str:
    """按表6~表9 格式化；无效字段（FFFFH/FFH）显示 ``--``。

    date_time 示例（698 附录 H.1.1）→ ``2016-05-19 08:05:00.164``
    """
    if not isinstance(value, dict):
        return str(value)
    year = value.get("year")
    year_s = f"{year:04d}" if isinstance(year, int) and year != 0xFFFF else "--"
    month = value.get("month")
    month_s = f"{month:02d}" if isinstance(month, int) and month != 0xFF else "--"
    day = value.get("day_of_month", value.get("day"))
    day_s = f"{day:02d}" if isinstance(day, int) and day != 0xFF else "--"
    hour = value.get("hour")
    hour_s = f"{hour:02d}" if isinstance(hour, int) and hour != 0xFF else "--"
    minute = value.get("minute")
    minute_s = f"{minute:02d}" if isinstance(minute, int) and minute != 0xFF else "--"
    second = value.get("second")
    second_s = f"{second:02d}" if isinstance(second, int) and second != 0xFF else "--"
    out = f"{year_s}-{month_s}-{day_s}"
    if type_name == "date":
        return out
    out = f"{out} {hour_s}:{minute_s}:{second_s}"
    if type_name == "date_time_s":
        return out
    ms = value.get("milliseconds")
    ms_s = f"{ms:03d}" if isinstance(ms, int) and ms != 0xFFFF else "--"
    return f"{out}.{ms_s}"


def weekday_name(day_of_week: Any) -> str:
    if not isinstance(day_of_week, int) or day_of_week == 0xFF or not (0 <= day_of_week <= 6):
        return ""
    return WEEKDAY_NAMES[day_of_week]


# ── 长度域 ────────────────────────────────────────────────────────────


def _read_length(data: bytes, off: int) -> Tuple[int, int]:
    n = AXDR_VAR_LENGTH_BYTES
    if off + n > len(data):
        raise AxdrError(
            f"长度域不足（需要 {n} 字节，偏移 {off}，总长 {len(data)}）", offset=off
        )
    return int.from_bytes(data[off : off + n], "big"), off + n


def _length_bytes(n: int) -> bytes:
    if n < 0:
        raise AxdrError(f"长度不能为负：{n}")
    try:
        return int(n).to_bytes(AXDR_VAR_LENGTH_BYTES, "big")
    except OverflowError as exc:  # pragma: no cover - 取决于开关取值
        raise AxdrError(
            f"长度 {n} 超出 {AXDR_VAR_LENGTH_BYTES} 字节长度域上限"
            f"（可调 AXDR_VAR_LENGTH_BYTES：{exc}）"
        ) from exc


# ── 定长类型编解码 ────────────────────────────────────────────────────

def _decode_fixed(raw: bytes, t: AxdrType) -> Any:
    name = t.name
    if name == "NULL":
        return None
    if name == "bool":
        return bool(raw[0] & 1)
    if name in ("unsigned", "enum"):
        return raw[0]
    if name in ("long", "long-unsigned", "double-long", "double-long-unsigned", "long64", "long64-unsigned", "DT"):
        return int.from_bytes(raw, "big", signed=t.signed)
    if name == "integer":
        return int.from_bytes(raw, "big", signed=True)
    if name == "float32":
        return struct.unpack(">f", raw)[0]
    if name == "float64":
        return struct.unpack(">d", raw)[0]
    if name == "date_time":
        return _decode_date(raw, DATE_TIME_FIELDS)
    if name == "date_time_s":
        return _decode_date(raw, DATE_TIME_S_FIELDS)
    if name == "date":
        return _decode_date(raw, DATE_FIELDS)
    if name == "time":
        return _decode_date(raw, TIME_FIELDS)
    if name == "Scaler_Unit":
        return {"scaler": int.from_bytes(raw[0:1], "big", signed=True), "unit": raw[1]}
    raise AxdrError(f"未实现的定长类型：{name}")  # pragma: no cover


def _decode_date(raw: bytes, fields: Sequence[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    pos = 0
    for field in fields:
        if field in _DATE_2B_FIELDS:
            out[field] = int.from_bytes(raw[pos : pos + 2], "big")
            pos += 2
        else:
            out[field] = raw[pos]
            pos += 1
    return out


def _encode_fixed(value: Any, t: AxdrType) -> bytes:
    name = t.name
    if name == "NULL":
        return b""
    if name == "bool":
        return bytes((1 if value else 0,))
    if name == "float32":
        return struct.pack(">f", float(value))
    if name == "float64":
        return struct.pack(">d", float(value))
    if name == "date_time":
        return _encode_date(value, DATE_TIME_FIELDS)
    if name == "date_time_s":
        return _encode_date(value, DATE_TIME_S_FIELDS)
    if name == "date":
        return _encode_date(value, DATE_FIELDS)
    if name == "time":
        return _encode_date(value, TIME_FIELDS)
    if name == "Scaler_Unit":
        scaler, unit = _split_scaler_unit(value)
        return bytes((scaler & 0xFF, unit & 0xFF))
    size = t.fixed or 0
    try:
        return int(value).to_bytes(size, "big", signed=t.signed)
    except (OverflowError, ValueError) as exc:
        raise AxdrError(
            f"{name} 取值 {value} 超出 {size} 字节{'有符号' if t.signed else '无符号'}范围"
        ) from exc


def _split_scaler_unit(value: Any) -> Tuple[int, int]:
    if isinstance(value, dict):
        scaler = value.get("scaler", 0)
        unit = value.get("unit", 255)
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        scaler, unit = value
    else:
        raise AxdrError("Scaler_Unit 需要 {'scaler':…, 'unit':…} 或 (换算, 单位)")
    if scaler is None:
        scaler = 0
    if unit is None:
        unit = 255
    return int(scaler), int(unit)


def _encode_date(value: Any, fields: Sequence[str]) -> bytes:
    if not isinstance(value, dict):
        raise AxdrError(f"日期类型需要 dict（键：{'/'.join(fields)}）")
    out = bytearray()
    for field in fields:
        v = value.get(field)
        if field in _DATE_2B_FIELDS:
            if v is None:
                v = 0xFFFF
            out += int(v).to_bytes(2, "big")
        else:
            if v is None:
                v = 0xFF
            out.append(int(v) & 0xFF)
    return bytes(out)


# ── 变长类型编解码 ────────────────────────────────────────────────────


def _decode_bit_string(body: bytes) -> Dict[str, Any]:
    if not body:
        raise AxdrError("bit-string 缺位宽字节")
    nbits = body[0]
    payload = bytes(body[1:])
    need = (nbits + 7) // 8
    set_bits = [
        i for i in range(nbits) if (i >> 3) < len(payload) and (payload[i >> 3] >> (i & 7)) & 1
    ]
    return {"bits": nbits, "data": payload, "set": set_bits, "need": need}


def _encode_bit_string(value: Any) -> bytes:
    if isinstance(value, dict):
        nbits = int(value.get("bits") or 0)
        payload = bytes(value.get("data") or b"")
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        nbits, payload = int(value[0]), bytes(value[1])
    elif isinstance(value, int):
        nbits, payload = value, b""
    else:
        payload = bytes(value)
        nbits = len(payload) * 8
    need = (nbits + 7) // 8
    if len(payload) < need:
        payload = payload + b"\x00" * (need - len(payload))
    return bytes((nbits & 0xFF,)) + payload[:need]


def _encode_variable(value: Any, t: AxdrType) -> bytes:
    name = t.name
    if name == "octet-string":
        return _length_bytes(len(value)) + bytes(value)
    if name == "visible-string":
        raw = value.encode("ascii") if isinstance(value, str) else bytes(value)
        return _length_bytes(len(raw)) + raw
    if name == "UTF8-string":
        raw = value.encode("utf-8") if isinstance(value, str) else bytes(value)
        return _length_bytes(len(raw)) + raw
    if name == "bit-string":
        body = _encode_bit_string(value)
        return _length_bytes(len(body)) + body
    if name in ("array", "structure"):
        items = list(value or [])
        out = bytearray(_length_bytes(len(items)))
        for item in items:
            out += _encode_data_item(item)
        return bytes(out)
    raise AxdrError(f"未实现的变长类型：{name}")  # pragma: no cover


def _encode_data_item(item: Any) -> bytes:
    """编码一个 Data CHOICE 元素：``(类型名, 值)`` 或现成的 ``AxdrNode``/bytes。"""
    if isinstance(item, AxdrNode):
        return bytes(item.raw)
    if isinstance(item, (tuple, list)) and len(item) == 2 and isinstance(item[0], str):
        return encode_value(item[1], item[0], with_tag=True)
    if isinstance(item, (bytes, bytearray)):
        return bytes(item)
    raise AxdrError(f"array/structure 元素需要 (类型名, 值)：{item!r}")


# ── 编解码入口 ────────────────────────────────────────────────────────


def decode_value(
    data: bytes, off: int, type_name: str, *, with_tag: bool
) -> Tuple[Any, int]:
    """解码一个字段，返回 ``(值, 新偏移)``；越界/不匹配抛 `AxdrError`。"""
    t = AXDR_TYPES.get(type_name)
    if t is None:
        raise AxdrError(f"未知 A-XDR 类型：{type_name}", offset=off)
    start = off
    if with_tag:
        if off >= len(data):
            raise AxdrError(
                f"{type_name} 读取类型标签越界（偏移 {off}，总长 {len(data)}）",
                offset=off,
                consumed=off - start,
            )
        if data[off] != t.tag:
            raise AxdrError(
                f"{type_name} 类型标签不匹配：期望 0x{t.tag:02X}，实际 0x{data[off]:02X}（偏移 {off}）",
                offset=off,
                consumed=off - start,
            )
        off += 1
    if t.fixed is not None:
        if with_tag and AXDR_LEN_FOR_FIXED_IN_CHOICE:
            _ln, off = _read_length(data, off)
        need = t.fixed
        if off + need > len(data):
            raise AxdrError(
                f"{type_name} 数据不足：需要 {need} 字节，剩余 {len(data) - off} 字节（偏移 {off}）",
                offset=off,
                consumed=off - start,
            )
        return _decode_fixed(data[off : off + need], t), off + need

    count, pos = _read_length(data, off)
    if t.name in ("array", "structure"):
        nodes: List[AxdrNode] = []
        cur = pos
        for _ in range(count):
            node, cur = decode_data_node(data, cur)
            nodes.append(node)
        return nodes, cur
    end = pos + count
    if end > len(data):
        raise AxdrError(
            f"{type_name} 长度域声明 {count} 字节，实际剩余 {len(data) - pos} 字节（偏移 {pos}）",
            offset=pos,
            consumed=pos - start,
        )
    body = data[pos:end]
    if t.name == "bit-string":
        return _decode_bit_string(body), end
    if t.name == "visible-string":
        return bytes(body), end
    if t.name == "UTF8-string":
        return bytes(body), end
    if t.name == "octet-string":
        return bytes(body), end
    raise AxdrError(f"未实现的变长类型：{t.name}")  # pragma: no cover


def decode_data_node(data: bytes, off: int, name: str = "数据") -> Tuple[AxdrNode, int]:
    """解码一个 Data CHOICE 元素（tag + 内容）。"""
    if off >= len(data):
        raise AxdrError(f"Data 类型标签越界（偏移 {off}，总长 {len(data)}）", offset=off)
    tag = data[off]
    t = AXDR_BY_TAG.get(tag)
    if t is None or t.name not in DATA_CHOICE_TYPES:
        raise AxdrError(
            f"未知 Data 类型标签 0x{tag:02X}（表5 共 25 个分支，偏移 {off}）", offset=off
        )
    value, end = decode_value(data, off + 1, t.name, with_tag=False)
    return AxdrNode(name=name, type_name=t.name, value=value, raw=data[off:end], offset=off), end


def decode_sequence(
    data: bytes,
    off: int,
    layout: Sequence[Tuple[str, str]],
    *,
    with_tag: Optional[bool] = None,
    sink: Optional[List[AxdrNode]] = None,
) -> Tuple[List[AxdrNode], int]:
    """按 ``[(字段名, 类型名), …]`` 解码 SEQUENCE，返回 ``(节点列表, 新偏移)``。

    传 ``sink`` 时逐字段追加到该列表：**中途失败时已解出的成员仍会留在 sink 里**
    （容错显示，见 AGENTS.md §8 陷阱 23）。
    """
    if with_tag is None:
        with_tag = AXDR_TAG_IN_SEQUENCE
    nodes: List[AxdrNode] = sink if sink is not None else []
    for field_name, type_name in layout:
        start = off
        value, off = decode_value(data, off, type_name, with_tag=with_tag)
        nodes.append(
            AxdrNode(
                name=field_name,
                type_name=type_name,
                value=value,
                raw=data[start:off],
                offset=start,
            )
        )
    return nodes, off


def encode_value(value: Any, type_name: str, *, with_tag: bool) -> bytes:
    """编码一个字段；``with_tag=True`` 用于 CHOICE 分支（带类型标签）。"""
    t = AXDR_TYPES.get(type_name)
    if t is None:
        raise AxdrError(f"未知 A-XDR 类型：{type_name}")
    if t.fixed is not None:
        body = _encode_fixed(value, t)
        if with_tag and AXDR_LEN_FOR_FIXED_IN_CHOICE:
            body = _length_bytes(len(body)) + body
    else:
        body = _encode_variable(value, t)
    return (bytes((t.tag,)) if with_tag else b"") + body


def encode_sequence(
    fields: Iterable[Tuple[str, Any]], *, with_tag: Optional[bool] = None
) -> bytes:
    """按 ``[(类型名, 值), …]`` 编码 SEQUENCE（外层无 tag）。"""
    if with_tag is None:
        with_tag = AXDR_TAG_IN_SEQUENCE
    out = bytearray()
    for type_name, value in fields:
        out += encode_value(value, type_name, with_tag=with_tag)
    return bytes(out)


def encode_data_item(type_name: str, value: Any) -> bytes:
    """编码一个 Data CHOICE 元素（tag + 内容）。"""
    return encode_value(value, type_name, with_tag=True)


# ── APDU（表13~表21）─────────────────────────────────────────────────

APDU_TAGS: Dict[str, int] = {
    "LinkRequest": 1,
    "GetRequest": 2,
    "SetRequest": 3,
    "ReportNotification": 4,
    "LinkResponse": 129,
    "GetResponse": 130,
    "SetResponse": 131,
    "ReportResponse": 132,
}
APDU_BY_TAG: Dict[int, str] = {v: k for k, v in APDU_TAGS.items()}

GET_RESULT_DAR = 0x00
GET_RESULT_DATA = 0x01

LINK_REQUEST_LAYOUT: Tuple[Tuple[str, str], ...] = (
    ("协议版本号", "long-unsigned"),
    ("终端设备型号", "visible-string"),
    ("终端设备ID", "visible-string"),
    ("最大发送缓冲区长度", "long-unsigned"),
    ("最大接收缓冲区长度", "long-unsigned"),
    ("并发传输窗口数", "unsigned"),
)

LINK_RESPONSE_LAYOUT: Tuple[Tuple[str, str], ...] = (
    ("协议版本号", "long-unsigned"),
    ("功能模块设备型号", "visible-string"),
    ("功能模块设备ID", "visible-string"),
    ("最大发送缓冲区长度", "long-unsigned"),
    ("最大接收缓冲区长度", "long-unsigned"),
    ("并发传输窗口数", "unsigned"),
)

DT_LAYOUT: Tuple[Tuple[str, str], ...] = (("信息类标识(DT)", "DT"),)


# ── 表18 虚拟通道工作模式（见模块文档「另注」）────────────────────────


def encode_channel_list(channels: Iterable[Any]) -> bytes:
    """``个数(1B) + N×(接口类型(1B) + 功能配置(1B))``。"""
    items: List[Tuple[int, int]] = []
    for ch in channels or ():
        if isinstance(ch, dict):
            iface = int(ch.get("iface", ch.get("接口类型", 1)))
            func = int(ch.get("config", ch.get("功能配置", 0)))
        else:
            iface, func = int(ch[0]), int(ch[1])
        items.append((iface & 0xFF, func & 0xFF))
    out = bytearray(_length_bytes(len(items)))
    for iface, func in items:
        out += bytes((iface, func))
    return bytes(out)


def decode_channel_list(data: bytes, off: int) -> Tuple[List[AxdrNode], int]:
    count, pos = _read_length(data, off)
    nodes: List[AxdrNode] = []
    for idx in range(count):
        if pos + 2 > len(data):
            raise AxdrError(
                f"虚拟通道工作模式第 {idx + 1} 项不完整（偏移 {pos}，总长 {len(data)}）",
                offset=pos,
            )
        nodes.append(
            AxdrNode(
                name=f"  虚拟通道{idx + 1}",
                type_name="channel",
                value={"iface": data[pos], "config": data[pos + 1]},
                raw=data[pos : pos + 2],
                offset=pos,
            )
        )
        pos += 2
    return nodes, pos


# ── Get-Result（表19）────────────────────────────────────────────────

GET_RESULT_SELECTOR_NAMES = {
    GET_RESULT_DAR: "错误信息(DAR)",
    GET_RESULT_DATA: "数据(Data)",
}


def decode_get_result(
    data: bytes, off: int, sink: Optional[List[AxdrNode]] = None
) -> Tuple[List[AxdrNode], int]:
    """解码 ``Get-Result∷=CHOICE { [0] DAR, [1] Data }``，返回 ``(节点列表, 新偏移)``。

    传 ``sink`` 时追加到该列表（中途失败也保留已解出的选择标签）。
    """
    if off >= len(data):
        raise AxdrError(f"Get-Result 缺失（偏移 {off}，总长 {len(data)}）", offset=off)
    sel = data[off]
    out: List[AxdrNode] = sink if sink is not None else []
    selector = AxdrNode(
        name="读取结果(Get-Result)",
        type_name="choice",
        value=GET_RESULT_SELECTOR_NAMES.get(sel, f"非法选择({sel})"),
        raw=data[off : off + 1],
        offset=off,
    )
    if sel == GET_RESULT_DAR:
        if off + 1 >= len(data):
            out.append(selector)
            raise AxdrError(f"DAR 字节缺失（偏移 {off + 1}）", offset=off + 1)
        dar = AxdrNode(
            name="错误信息(DAR)",
            type_name="DAR",
            value=data[off + 1],
            raw=data[off + 1 : off + 2],
            offset=off + 1,
        )
        out.extend((selector, dar))
        return out, off + 2
    if sel == GET_RESULT_DATA:
        out.append(selector)
        child, pos = decode_data_node(data, off + 1, name="数据(Data)")
        out.append(child)
        return out, pos
    raise AxdrError(
        f"Get-Result 选择标签非法 0x{sel:02X}（0=错误信息DAR / 1=数据Data，表19）", offset=off
    )


def _dar_node(data: bytes, off: int, name: str) -> Tuple[AxdrNode, int]:
    if off >= len(data):
        raise AxdrError(f"{name} 缺失（偏移 {off}）", offset=off)
    return (
        AxdrNode(name=name, type_name="DAR", value=data[off], raw=data[off : off + 1], offset=off),
        off + 1,
    )


# ── 8 类 APDU 解码（表13~表21）──────────────────────────────────────


def decode_apdu(data: bytes, off: int = 0) -> Tuple[List[AxdrNode], int]:
    """解码一个完整 APDU，返回 ``(节点列表, APDU 结束偏移)``。

    ``AxdrError.consumed`` 会被换算成「相对 APDU 起点已消费的字节数」，
    ``AxdrError.partial`` 带上出错前已解出的节点（容错显示用）。
    """
    start = off
    partial: List[AxdrNode] = []
    try:
        return _decode_apdu(data, off, partial)
    except AxdrError as exc:
        exc.consumed = max(0, exc.offset - start)
        exc.partial = partial
        raise


def _decode_apdu(
    data: bytes, off: int, nodes: List[AxdrNode]
) -> Tuple[List[AxdrNode], int]:
    if off >= len(data):
        raise AxdrError(f"APDU 为空（偏移 {off}）", offset=off)
    tag = data[off]
    name = APDU_BY_TAG.get(tag)
    if name is None:
        raise AxdrError(
            f"未知 APDU 标签 0x{tag:02X}（表13 CHOICE：1/2/3/4/129/130/131/132）", offset=off
        )
    nodes.append(
        AxdrNode(
            name="APDU 类型",
            type_name="apdu-tag",
            value=name,
            raw=data[off : off + 1],
            offset=off,
        )
    )
    pos = off + 1
    if name == "LinkRequest":
        _sub, pos = decode_sequence(data, pos, LINK_REQUEST_LAYOUT, sink=nodes)
    elif name == "LinkResponse":
        _sub, pos = decode_sequence(data, pos, LINK_RESPONSE_LAYOUT, sink=nodes)
        ch_start = pos
        channels, pos = decode_channel_list(data, pos)
        nodes.append(
            AxdrNode(
                name="虚拟通道工作模式",
                type_name="channel-list",
                value=channels,
                raw=data[ch_start:pos],
                offset=ch_start,
            )
        )
    elif name == "GetRequest":
        _sub, pos = decode_sequence(data, pos, DT_LAYOUT, sink=nodes)
    elif name == "SetRequest":
        _sub, pos = decode_sequence(data, pos, DT_LAYOUT, sink=nodes)
        child, pos = decode_data_node(data, pos, name="数据(Data)")
        nodes.append(child)
    elif name in ("GetResponse", "ReportNotification"):
        _sub, pos = decode_sequence(data, pos, DT_LAYOUT, sink=nodes)
        _sub, pos = decode_get_result(data, pos, sink=nodes)
    elif name == "SetResponse":
        _sub, pos = decode_sequence(data, pos, DT_LAYOUT, sink=nodes)
        dar, pos = _dar_node(data, pos, "设置执行结果(DAR)")
        nodes.append(dar)
    elif name == "ReportResponse":
        _sub, pos = decode_sequence(data, pos, DT_LAYOUT, sink=nodes)
    return nodes, pos


# ── 8 类 APDU 编码 ───────────────────────────────────────────────────


def encode_apdu(
    name: str,
    *,
    fields: Any = None,
    dt: Optional[int] = None,
    data_value: Any = None,
    data_type: Optional[str] = None,
    dar: Optional[int] = None,
    channels: Any = None,
) -> bytes:
    """按表13~表21 编码一个 APDU。

    * ``LinkRequest``/``LinkResponse``：``fields`` 为 6 个成员的值（按 ASN.1 顺序）；
      后者可再给 ``channels``；
    * ``GetRequest``/``ReportResponse``：``dt``；
    * ``SetRequest``：``dt`` + ``data_value``/``data_type``；
    * ``GetResponse``：``dt`` + 二选一 —— ``data_value``/``data_type`` 或 ``dar``；
    * ``SetResponse``：``dt`` + ``dar``；
    * ``ReportNotification``：``dt`` + ``data_value``/``data_type``。
    """
    tag = APDU_TAGS.get(name)
    if tag is None:
        raise AxdrError(f"未知 APDU 类型：{name}")
    out = bytearray((tag,))
    if name in ("LinkRequest", "LinkResponse"):
        layout = LINK_REQUEST_LAYOUT if name == "LinkRequest" else LINK_RESPONSE_LAYOUT
        values = list(fields or [])
        if len(values) < len(layout):
            raise AxdrError(f"{name} 需要 {len(layout)} 个成员值，实得 {len(values)}")
        for (fname, ftype), val in zip(layout, values):
            out += encode_value(val, ftype, with_tag=AXDR_TAG_IN_SEQUENCE)
        if name == "LinkResponse":
            out += encode_channel_list(channels or ())
    elif name in ("GetRequest", "ReportResponse"):
        out += encode_value(int(dt or 0), "DT", with_tag=AXDR_TAG_IN_SEQUENCE)
    elif name == "SetRequest":
        out += encode_value(int(dt or 0), "DT", with_tag=AXDR_TAG_IN_SEQUENCE)
        out += encode_data_item(data_type or "NULL", data_value)
    elif name in ("GetResponse", "ReportNotification"):
        out += encode_value(int(dt or 0), "DT", with_tag=AXDR_TAG_IN_SEQUENCE)
        if name == "GetResponse" and dar is not None:
            out += bytes((GET_RESULT_DAR, int(dar) & 0xFF))
        else:
            out += bytes((GET_RESULT_DATA,))
            out += encode_data_item(data_type or "NULL", data_value)
    elif name == "SetResponse":
        out += encode_value(int(dt or 0), "DT", with_tag=AXDR_TAG_IN_SEQUENCE)
        out += bytes((int(dar or 0) & 0xFF,))
    return bytes(out)


# ── 附录 A：FCS（PPP fcstab）────────────────────────────────────────


def _build_fcstab() -> Tuple[int, ...]:
    """按附录 A.2「校验表发生器」生成：``P = 0x8408``（x^0+x^5+x^12+x^16）。"""
    tab: List[int] = []
    for b in range(256):
        v = b
        for _ in range(8):
            v = (v >> 1) ^ 0x8408 if v & 1 else v >> 1
        tab.append(v & 0xFFFF)
    return tuple(tab)


#: 附录 A.1 的 ``fcstab[256]``
FCSTAB: Tuple[int, ...] = _build_fcstab()

PPPINITFCS16 = 0xFFFF
PPPGOODFCS16 = 0xF0B8


def pppfcs16(payload: bytes, fcs: int = PPPINITFCS16) -> int:
    """附录 A.1 ``pppfcs16``：不取反的累进值。"""
    for b in payload:
        fcs = (fcs >> 8) ^ FCSTAB[(fcs ^ b) & 0xFF]
    return fcs & 0xFFFF


def calc_fcs(payload: bytes) -> int:
    """FCS-16 = ``~pppfcs16(payload)``（≡ CRC-16/X-25），覆盖 L + C + 数据域。"""
    return (pppfcs16(payload) ^ 0xFFFF) & 0xFFFF


# ── 自检入口 ─────────────────────────────────────────────────────────


FRAME_START = 0x68
FRAME_END = 0x16
#: 固定部分 = 68H + L(2) + C(2) + FCS(2) + 16H
HEADER_LEN = 9


def frame_layout(data: bytes) -> dict:
    """帧结构判据的**单一实现**（解析器 `parse()` / 校验器 / `verify_frame()` 共用）。

    返回：
    ``{start_ok, end_ok, end_offset, declared_l, expected_total, length_ok,
       reserved_bits_nonzero, fcs_ok, fcs_field, fcs_calc, fcs_offset, fcs_usable,
       control:{dir,prm,code,fid}, payload, errors, structure_ok, ok}``

    * ``structure_ok`` = 起始符 + 长度域一致 + 结束符；
    * ``ok`` = ``structure_ok and fcs_ok and not errors``（保留位非 0 计入 ``errors``）；
    * 长度不符时仍按声明布局给出 ``payload``（切片自动夹取），FCS 回退用「实际帧尾 3 字节」
      定位，以便告诉用户正确值。
    """
    data = bytes(data or b"")
    out: dict = {
        "start_ok": bool(data) and data[0] == FRAME_START,
        "end_ok": False,
        "end_offset": -1,
        "declared_l": None,
        "expected_total": None,
        "length_ok": False,
        "reserved_bits_nonzero": False,
        "fcs_ok": False,
        "fcs_field": b"",
        "fcs_calc": b"",
        "fcs_offset": None,
        "fcs_usable": False,
        "control": None,
        "payload": b"",
        "errors": [],
        "structure_ok": False,
        "ok": False,
    }
    if len(data) < 5:
        out["errors"].append("帧短于 5 字节，长度域/控制域未收全")
        return out
    l_raw = data[1] | (data[2] << 8)
    data_len = l_raw & 0x0FFF
    total = data_len + 8
    out.update(
        {
            "declared_l": data_len,
            "expected_total": total,
            "reserved_bits_nonzero": (l_raw >> 12) != 0,
            "length_ok": len(data) == total,
            "control": {
                "dir": (data[3] >> 7) & 1,
                "prm": (data[3] >> 6) & 1,
                "code": data[3] & 0x3F,
                "fid": data[4],
            },
            "payload": data[5 : 5 + data_len],
        }
    )
    fcs_off = 5 + data_len
    if fcs_off + 2 <= len(data):
        out["fcs_offset"] = fcs_off
        out["fcs_usable"] = True
    elif len(data) >= 8 and data[-1] == FRAME_END:
        out["fcs_offset"] = len(data) - 3
        out["fcs_usable"] = True
    if out["fcs_usable"]:
        off = int(out["fcs_offset"])
        wire = data[off : off + 2]
        calc = calc_fcs(data[1:off]).to_bytes(2, "little")
        out["fcs_field"] = wire
        out["fcs_calc"] = calc
        out["fcs_ok"] = wire == calc
    end_off = (total - 1) if out["length_ok"] else (len(data) - 1)
    out["end_offset"] = end_off
    out["end_ok"] = 0 <= end_off < len(data) and data[end_off] == FRAME_END
    if not out["length_ok"]:
        out["errors"].append(f"帧长度 {len(data)} ≠ 长度域声明整帧 {total} 字节")
    if not out["end_ok"]:
        out["errors"].append("结束符不是 16H")
    if out["reserved_bits_nonzero"]:
        out["errors"].append(f"长度域保留位(bit12~15)非 0（0x{l_raw:04X}）")
    out["structure_ok"] = bool(out["start_ok"] and out["length_ok"] and out["end_ok"])
    out["ok"] = bool(out["structure_ok"] and out["fcs_ok"] and not out["errors"])
    return out


def apdu_self_check(payload: bytes) -> dict:
    """APDU 自证：能否被 A-XDR 完整解完（``axdr_tail`` = 未消费字节数）。"""
    out = {
        "apdu_tag": None,
        "apdu_name": None,
        "axdr_consumed": 0,
        "axdr_tail": None,
        "reason": "",
    }
    if not payload:
        return out
    out["apdu_tag"] = payload[0]
    out["apdu_name"] = APDU_BY_TAG.get(payload[0])
    try:
        _nodes, consumed = decode_apdu(payload, 0)
    except AxdrError as exc:
        out["axdr_consumed"] = min(exc.consumed, len(payload))
        out["axdr_tail"] = len(payload) - out["axdr_consumed"]
        out["reason"] = f"A-XDR 解析未完成：{exc.message}"
        return out
    out["axdr_consumed"] = consumed
    out["axdr_tail"] = len(payload) - consumed
    return out


def verify_frame(frame: bytes) -> dict:
    """给定真实帧的自检报告（现场/测试/GUI 校验共用）。

    ``axdr_tail`` 是编码假设的判据：**APDU 解完后仍有剩余（或不足）字节即说明
    三个开关与真实帧不符**。逐一切换 ①/②/③（组合 8 种）重试，能过则改默认值。
    """
    data = bytes(frame)
    layout = frame_layout(data)
    out: Dict[str, Any] = {
        "ok": False,
        "reason": "",
        "frame_len": len(data),
        "declared_l": layout["declared_l"],
        "l_matches": layout["length_ok"],
        "fcs_ok": layout["fcs_ok"],
        "fcs_field": layout["fcs_field"],
        "fcs_calc": layout["fcs_calc"],
        "reserved_bits_nonzero": layout["reserved_bits_nonzero"],
        "control": layout["control"],
        "apdu_tag": None,
        "apdu_name": None,
        "axdr_consumed": 0,
        "axdr_tail": None,
    }
    if not data:
        out["reason"] = "空帧"
        return out
    if data[0] != FRAME_START:
        out["reason"] = f"起始符不是 68H（实际 {data[0]:02X}H）"
        return out
    if len(data) < 8:
        out["reason"] = f"帧长 {len(data)} 字节少于最小 8 字节"
        return out
    if (layout["control"] or {}).get("code") == 0x02 and layout["payload"]:
        out.update(apdu_self_check(layout["payload"]))
    out["ok"] = bool(
        layout["ok"] and out["axdr_tail"] in (0, None) and not out["reason"]
    )
    if not out["ok"] and not out["reason"]:
        out["reason"] = "；".join(layout["errors"]) or "APDU 未完整解析"
    return out
