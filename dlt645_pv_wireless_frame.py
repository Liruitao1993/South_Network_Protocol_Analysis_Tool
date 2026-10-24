# -*- coding: utf-8 -*-
"""南网光伏协议转换单元 · 无线模组接口手册（V1.6）扩展 —— **组帧方向**（纯逻辑，无 Qt）

来源：``协议文档/6.645协议/南网光伏协议转换单元无线接口手册-V1.6.md``

本模块与 :mod:`dlt645_pv_wireless`（解析方向）严格互为逆运算：
``parse_wireless_di(di, ctrl, build_wireless_payload(di, fv))`` 必须把 fv 里的
值原样解回来。帧封装（地址域、控制码、+0x33 加扰、L、CS、68/16）仍由
:mod:`dlt645_frame_gen` 统一负责，本模块只产出 **DI 之后的数据域部分**。

供 :mod:`dlt645_frame_schema` 在「DI 属于本手册」时优先调用；对非本手册 DI
一律返回 ``None``，标准 645 行为完全不受影响。

两个「手册自身不一致」的位置（如实按手册落实现，不臆造）：

1. ``04900103`` 升级文件信息：长度列写 **108**，但各字段累加为
   ``32+4+4+2+32+32 = 106``。此处按 108 补 2 字节「尾部保留」，与解析侧
   （``_decode_upgrade_file_info`` 把 106 之后的字节当作尾部）保持闭环。
2. ``04E60001`` 地址列表：附件1 给的是「长度列 16」，本手册给 ``1+6×M``
   且有 4.4.3 实测报文自证 ⇒ 本模块按 ``1+6×M`` 编码（与解析侧一致）。
"""

from typing import Any, Dict, List, Optional

from dlt645_data_codec import bcd_pack, parse_hex
from dlt645_frame_gen import encode_addr
from dlt645_pv_wireless import (
    ONLINE_STATE,
    UPGRADE_STATUS,
    WIRELESS_DI_MAP,
    is_wireless_di,
)

# 字段类型标记：与 dlt645_frame_schema 的 F_* 同值（此处不 import schema，避免循环依赖）
F_HEX = "hex"

#: 读请求（11H）也要带数据域的 DI —— 手册 §4.1.3：数据转发请求
#: ``02EB0000 + 波特率Z + 校验C + 超时T + 逆变器数据``（L=07H+len(DATA)）。
#: 其余无线 DI 的读请求只带 DI 4 字节（见 4.4.2/4.4.3/4.4.6 发送帧）。
REQ_WITH_PAYLOAD_DI = ("02EB0000",)

#: 手册给固定长度（用于 length_warning / UI 展示）；不定长 DI 记 0 = 不校验
_FIXED_LEN = {
    "04E60002": 4,
    "04900102": 37,
    "04900103": 108,
    "04900105": 2,
    "04900106": 5,
    "028100FF": 1,
}


# ── 字段构造（与 dlt645_frame_schema.fld 同构）──────────────────────────────

def _fld(name: str, default: str = "", hint: str = "",
         length: Optional[int] = None, ftype: str = F_HEX) -> Dict[str, Any]:
    d: Dict[str, Any] = {"name": name, "type": ftype,
                         "default": default, "hint": hint}
    if length is not None:
        d["length"] = length
    return d


def _fv(fv: Dict, name: str, default: str = "") -> str:
    v = (fv or {}).get(name, None)
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    return str(v).strip()


# ── 编码小工具 ─────────────────────────────────────────────────────────────

def _dec_int(text: str, label: str, lo: int, hi: int) -> int:
    """十进制整数字段 → int；越界抛中文 ValueError。"""
    s = (text or "").strip()
    if not s:
        raise ValueError(f"请填写{label}")
    if s.lower().startswith("0x"):
        try:
            v = int(s, 16)
        except ValueError:
            raise ValueError(f"{label}含非法十六进制字符：{text!r}")
    else:
        if not s.isdigit():
            raise ValueError(f"{label}应为十进制整数（当前 {text!r}）")
        v = int(s)
    if not lo <= v <= hi:
        raise ValueError(f"{label}应在 {lo}~{hi}（当前 {v}）")
    return v


def _bin_hex(text: str, label: str, nbytes: Optional[int]) -> bytes:
    """hex 字节字段 → bytes；nbytes 给定时不足右补 0x00、超长报错。"""
    raw = parse_hex(text or "", None, label)
    if nbytes is None:
        return raw
    if len(raw) > nbytes:
        raise ValueError(
            f"{label}最多 {nbytes} 字节（当前 {len(raw)} 字节）")
    return raw + b"\x00" * (nbytes - len(raw))


def _ascii_fixed(text: str, nbytes: int, label: str) -> bytes:
    """ASCII 定长字段（右补 0x00）；超长报错。"""
    s = (text or "").strip()
    try:
        b = s.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError(f"{label}只能填 ASCII 字符（当前 {text!r}）")
    if len(b) > nbytes:
        raise ValueError(f"{label}最多 {nbytes} 字节（当前 {len(b)} 字节）")
    return b + b"\x00" * (nbytes - len(b))


def _bcd_or_ff(text: str, nbytes: int, label: str, digits_len: int) -> bytes:
    """``nbytes`` 字节 BCD（低字节在前）；填 FF / 留空 / 「立即」→ 全 FF。"""
    s = (text or "").strip().upper().replace(" ", "")
    if not s or s in ("FF", "FF" * nbytes, "立即", "立即执行"):
        return b"\xff" * nbytes
    if not s.isdigit():
        raise ValueError(f"{label}应为 {digits_len} 位数字（或填 FF 表示立即执行）")
    if len(s) != digits_len:
        raise ValueError(f"{label}应为 {digits_len} 位数字（当前 {len(s)} 位）")
    return bcd_pack(s, nbytes, label)


def _split_multi(text: str) -> List[str]:
    """多项分隔：逗号 / 分号 / 空格 / 换行 / 中文标点一律视为分隔符。"""
    s = (text or "").replace("；", ";").replace("，", ",").replace("、", ",")
    for sep in (";", "\n", "\r", "\t", ","):
        s = s.replace(sep, " ")
    return [p for p in s.split(" ") if p]


def _split_records(text: str) -> List[str]:
    """记录分隔：分号 / 换行（记录内部的地址等用逗号分隔）。"""
    s = (text or "").replace("；", ";").replace("\r", "\n")
    s = s.replace(";", "\n")
    return [p.strip() for p in s.split("\n") if p.strip()]


def _addr_token(token: str, label: str) -> bytes:
    """单个地址 → 线上 6 字节（低字节在前）。容忍 0x 前缀与内部空格。"""
    return encode_addr(token.replace(" ", ""), label)


# ── 各 DI 的字段模板 ───────────────────────────────────────────────────────

def _fields_transfer() -> List[Dict]:
    return [
        _fld("波特率特征字 Z", "08",
             "1 字节位图：bit0=115200、bit1=600、bit2=1200、bit3=2400、"
             "bit4=4800、bit5=9600、bit6=19200、bit7=38400（仅一位为 1 时有效）；"
             "08H = 2400bps"),
        _fld("校验方式 C", "02", "0=无校验、1=奇校验、2=偶校验（手册 §4.1.3）"),
        _fld("超时 T（BCD）", "10",
             "单位 100ms，字段为 BCD 码：10H → 10 → 1000ms；00H → 模组默认 5 秒"),
        _fld("转发数据（逆变器报文）", "",
             "选填：透传给光伏逆变器的 645/厂家报文原文，按裸 hex 填写"),
    ]


def _fields_addr_list() -> List[Dict]:
    return [
        _fld("有效数量 M", "",
             "留空 = 按地址列表个数自动；M≤12（手册 §4.2.2）"),
        _fld("地址列表", "",
             "每项 12 位地址（如 000006881031），多项用逗号/空格分隔，最多 12 个；"
             "线上按低字节在前 + BCD 写入"),
    ]


def _fields_band() -> List[Dict]:
    return [
        _fld("无线调制方式", "2",
             "1=备用（保留）、2=500kHz（信道 1~79）、3=200kHz（信道 1~200）"),
        _fld("无线信道编号", "32",
             "十进制 1~200；线上为 2 字节 BCD 且低字节在前（手册 §4.2.1 v1.3）"),
        _fld("信道协商使能", "1", "0=禁止、1=允许（默认 1）"),
    ]


def _fields_topology() -> List[Dict]:
    return [
        _fld("光伏接入单元数量 N", "",
             "留空 = 按拓扑条目条数自动；N≤12（手册 §4.2.3）"),
        _fld("拓扑条目", "",
             "每行一条：地址(12 位),信号质量(0~255),父节点地址(12 位)[,保留4位]；"
             "多条用分号/换行分隔。父节点填 FFFFFFFFFFFF 表示该单元未入网，"
             "保留默认 0000"),
    ]


def _fields_block_bitmap() -> List[Dict]:
    return [
        _fld("块状态字（位图 hex）", "",
             "BIN 位图，bitN=1 表示第 N 块传输成功（N 从 0 起）；"
             "不定长，按块数向上取整字节"),
    ]


def _fields_upgrade_status() -> List[Dict]:
    return [
        _fld("升级文件名（ASCII）", "", "最多 32 字节 ASCII，不足右补 0x00"),
        _fld("文件校验 CRC32", "00000000",
             "4 字节 BIN，按线上字节顺序填 hex（解析时按低字节在前解释）"),
        _fld("升级状态", "0",
             "0=初始、1=启动传输成功待下载、2=下载中、3=下载成功、"
             "4=校验成功、5=定时升级等待中、6=升级成功…255=其它失败"),
    ]


def _fields_upgrade_file_info() -> List[Dict]:
    return [
        _fld("升级文件名（ASCII）", "", "最多 32 字节 ASCII，不足右补 0x00"),
        _fld("文件大小（字节）", "0",
             "十进制，4 字节 BIN 低字节在前（如 65536）"),
        _fld("文件校验 CRC32", "00000000", "4 字节 BIN，按线上字节顺序填 hex"),
        _fld("升级块大小（字节）", "241",
             "十进制，2 字节 BIN；手册：最大 241、最小 128"),
        _fld("保留段 1（32 字节 hex）", "",
             "选填，不足右补 00（手册定义为保留）"),
        _fld("保留段 2（32 字节 hex）", "",
             "选填，不足右补 00（手册定义为保留）"),
        _fld("尾部保留（2 字节 hex）", "",
             "选填。注：手册长度列写 108，但各字段累加为 106，此处补齐 2 字节对齐"),
    ]


def _fields_upgrade_block() -> List[Dict]:
    return [
        _fld("升级块序号", "0", "十进制，2 字节 BIN 低字节在前（从 0 起）"),
        _fld("升级块数据", "",
             "本块原始字节 hex；单块最大不超过 04900105 上报的最大块大小（≤241）"),
    ]


def _fields_max_block() -> List[Dict]:
    return [
        _fld("最大升级块大小（字节）", "241",
             "十进制，2 字节 BIN；手册：最大 241、最小 128"),
    ]


def _fields_upgrade_time() -> List[Dict]:
    return [
        _fld("执行升级时间", "FF",
             "YYMMDDhhmm 共 10 位数字（如 2611010830 = 2026-11-01 08:30），"
             "或填 FF / 留空表示立即执行；小于设备当前时间也会立即升级"),
    ]


def _fields_version() -> List[Dict]:
    return [
        _fld("版本信息（ASCII）", "", "不定长 ASCII，如 V1.6.0"),
    ]


def _fields_online() -> List[Dict]:
    return [
        _fld("在网状态", "1", "0=离网、1=在网（手册 §4.3.1）"),
    ]


#: DI → 字段模板工厂（顺序即 UI 展示顺序）
_FIELD_BUILDERS = {
    "02EB0000": _fields_transfer,
    "04E60001": _fields_addr_list,
    "04E60002": _fields_band,
    "04900100": _fields_topology,
    "04900101": _fields_block_bitmap,
    "04900102": _fields_upgrade_status,
    "04900103": _fields_upgrade_file_info,
    "04900104": _fields_upgrade_block,
    "04900105": _fields_max_block,
    "04900106": _fields_upgrade_time,
    "04900107": _fields_version,
    "028100FF": _fields_online,
}


# ── 各 DI 的数据域编码（DI 之后部分）──────────────────────────────────────

def _payload_transfer(fv: Dict) -> bytes:
    z = _bin_hex(_fv(fv, "波特率特征字 Z", "08"), "波特率特征字 Z", 1)
    c = _bin_hex(_fv(fv, "校验方式 C", "02"), "校验方式 C", 1)
    t = _bin_hex(_fv(fv, "超时 T（BCD）", "10"), "超时 T", 1)
    data = parse_hex(_fv(fv, "转发数据（逆变器报文）"), None, "转发数据")
    return z + c + t + data


def _payload_addr_list(fv: Dict) -> bytes:
    tokens = _split_multi(_fv(fv, "地址列表"))
    addrs = [_addr_token(tok, f"地址列表第 {i + 1} 项")
             for i, tok in enumerate(tokens)]
    if len(addrs) > 12:
        raise ValueError(f"地址列表最多 12 项（当前 {len(addrs)} 项）")
    m_text = _fv(fv, "有效数量 M")
    if m_text:
        m = _dec_int(m_text, "有效数量 M", 0, 12)
        if m != len(addrs):
            raise ValueError(
                f"有效数量 M={m} 与地址列表项数 {len(addrs)} 不一致；"
                f"请清空 M 让其自动取值，或补齐/删掉地址")
    else:
        m = len(addrs)
    if m == 0:
        raise ValueError("地址列表为空：M=0 的应答帧没有地址数据，如需组空列表请直接用裸 hex 组帧")
    return bytes([m]) + b"".join(addrs)


def _payload_band(fv: Dict) -> bytes:
    mod = _dec_int(_fv(fv, "无线调制方式", "2"), "无线调制方式", 0, 255)
    chan = _dec_int(_fv(fv, "无线信道编号", "32"), "无线信道编号", 1, 200)
    en = _dec_int(_fv(fv, "信道协商使能", "1"), "信道协商使能", 0, 255)
    return bytes([mod]) + bcd_pack(str(chan), 2, "无线信道编号") + bytes([en])


def _payload_topology(fv: Dict) -> bytes:
    records = _split_records(_fv(fv, "拓扑条目"))
    out = bytearray()
    for i, rec in enumerate(records):
        parts = _split_multi(rec)
        if len(parts) < 2:
            raise ValueError(
                f"拓扑条目第 {i + 1} 行至少要有「地址,信号质量」（当前 {rec!r}）")
        addr_b = _addr_token(parts[0], f"拓扑条目第 {i + 1} 行地址")
        quality = _dec_int(parts[1], f"拓扑条目第 {i + 1} 行信号质量", 0, 255)
        parent_b = (_addr_token(parts[2], f"拓扑条目第 {i + 1} 行父节点")
                    if len(parts) > 2 and parts[2] else b"\x00" * 6)
        rsv = _bin_hex(parts[3] if len(parts) > 3 else "", 
                       f"拓扑条目第 {i + 1} 行保留", 2)
        out += addr_b + bytes([quality]) + parent_b + rsv
    if not records:
        raise ValueError("拓扑条目为空：组 N=0 的空拓扑请直接用裸 hex 组帧")
    if len(records) > 12:
        raise ValueError(f"拓扑条目最多 12 条（当前 {len(records)} 条）")
    n_text = _fv(fv, "光伏接入单元数量 N")
    if n_text:
        n = _dec_int(n_text, "光伏接入单元数量 N", 0, 12)
        if n != len(records):
            raise ValueError(
                f"数量 N={n} 与拓扑条目条数 {len(records)} 不一致；"
                f"请清空 N 让其自动取值，或补齐/删掉条目")
    return bytes([len(records)]) + bytes(out)


def _payload_block_bitmap(fv: Dict) -> bytes:
    return parse_hex(_fv(fv, "块状态字（位图 hex）"), None, "块状态字")


def _payload_upgrade_status(fv: Dict) -> bytes:
    name = _ascii_fixed(_fv(fv, "升级文件名（ASCII）"), 32, "升级文件名")
    crc = _bin_hex(_fv(fv, "文件校验 CRC32", "00000000"), "文件校验 CRC32", 4)
    status = _dec_int(_fv(fv, "升级状态", "0"), "升级状态", 0, 255)
    return name + crc + bytes([status])


def _payload_upgrade_file_info(fv: Dict) -> bytes:
    name = _ascii_fixed(_fv(fv, "升级文件名（ASCII）"), 32, "升级文件名")
    size = _dec_int(_fv(fv, "文件大小（字节）", "0"), "文件大小", 0, 0xFFFFFFFF)
    crc = _bin_hex(_fv(fv, "文件校验 CRC32", "00000000"), "文件校验 CRC32", 4)
    chunk = _dec_int(_fv(fv, "升级块大小（字节）", "241"), "升级块大小", 0, 0xFFFF)
    rsv1 = _bin_hex(_fv(fv, "保留段 1（32 字节 hex）"), "保留段 1", 32)
    rsv2 = _bin_hex(_fv(fv, "保留段 2（32 字节 hex）"), "保留段 2", 32)
    tail = _bin_hex(_fv(fv, "尾部保留（2 字节 hex）"), "尾部保留", 2)
    return (name + size.to_bytes(4, "little") + crc
            + chunk.to_bytes(2, "little") + rsv1 + rsv2 + tail)


def _payload_upgrade_block(fv: Dict) -> bytes:
    seq = _dec_int(_fv(fv, "升级块序号", "0"), "升级块序号", 0, 0xFFFF)
    data = parse_hex(_fv(fv, "升级块数据"), None, "升级块数据")
    return seq.to_bytes(2, "little") + data


def _payload_max_block(fv: Dict) -> bytes:
    size = _dec_int(_fv(fv, "最大升级块大小（字节）", "241"),
                    "最大升级块大小", 0, 0xFFFF)
    return size.to_bytes(2, "little")


def _payload_upgrade_time(fv: Dict) -> bytes:
    return _bcd_or_ff(_fv(fv, "执行升级时间", "FF"), 5, "执行升级时间", 10)


def _payload_version(fv: Dict) -> bytes:
    s = _fv(fv, "版本信息（ASCII）")
    try:
        return s.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError(f"版本信息只能填 ASCII 字符（当前 {s!r}）")


def _payload_online(fv: Dict) -> bytes:
    state = _dec_int(_fv(fv, "在网状态", "1"), "在网状态", 0, 1)
    return bytes([state])


#: DI → 数据域编码器
_PAYLOAD_BUILDERS = {
    "02EB0000": _payload_transfer,
    "04E60001": _payload_addr_list,
    "04E60002": _payload_band,
    "04900100": _payload_topology,
    "04900101": _payload_block_bitmap,
    "04900102": _payload_upgrade_status,
    "04900103": _payload_upgrade_file_info,
    "04900104": _payload_upgrade_block,
    "04900105": _payload_max_block,
    "04900106": _payload_upgrade_time,
    "04900107": _payload_version,
    "028100FF": _payload_online,
}


# ── 对外接口 ───────────────────────────────────────────────────────────────

def build_wireless_fields(di_code: str) -> Optional[List[Dict]]:
    """本手册 DI → 结构化字段模板；非本手册 DI 返回 ``None``（交回标准掩码推导）。"""
    code = (di_code or "").strip().upper()
    if not is_wireless_di(code):
        return None
    builder = _FIELD_BUILDERS.get(code)
    if builder is None:
        return None
    return builder()


def build_wireless_payload(di_code: str, fv: Dict) -> Optional[bytes]:
    """本手册 DI → **DI 之后**的数据域字节；非本手册 DI 返回 ``None``。"""
    code = (di_code or "").strip().upper()
    if not is_wireless_di(code):
        return None
    builder = _PAYLOAD_BUILDERS.get(code)
    if builder is None:
        return None
    return builder(fv or {})


def wireless_request_extra(di_code: str, fv: Dict) -> Optional[bytes]:
    """读请求（11H）在 DI 之后还要带的数据。

    - ``02EB0000`` 数据转发：返回 Z+C+T+DATA（手册 §4.1.3，L=07H+len）
    - 其余无线 DI：返回 ``b""``（只带 DI，见 4.4.2/4.4.3/4.4.6 发送帧）
    - 非本手册 DI：返回 ``None``（调用方走原标准逻辑）
    """
    code = (di_code or "").strip().upper()
    if not is_wireless_di(code):
        return None
    if code in REQ_WITH_PAYLOAD_DI:
        return build_wireless_payload(code, fv) or b""
    return b""


def wireless_di_info(di_code: str) -> Optional[Dict]:
    """本手册 DI → ``{name, unit, data_type, length}``（与 ``get_di_info`` 同构）。

    ``length`` 记 **0 = 不定长**（由内容决定），固定长度 DI 记实际字节数；
    这样 ``dlt645_frame_schema.length_warning`` 对不定长 DI 自动跳过校验。
    """
    code = (di_code or "").strip().upper()
    if not is_wireless_di(code):
        return None
    entry = WIRELESS_DI_MAP.get(code) or {}
    return {
        "name": entry.get("name", ""),
        "unit": entry.get("unit", ""),
        "data_type": entry.get("data_type", ""),
        "length": _FIXED_LEN.get(code, 0),
    }


def field_count() -> int:
    """字段模板总数（测试用守卫：12 个 DI 都必须有模板与编码器）。"""
    return len(_FIELD_BUILDERS)


def missing_builders() -> List[str]:
    """缺模板或编码器的 DI（正常应为空；测试用）。"""
    codes = set(WIRELESS_DI_MAP)
    return sorted(codes - set(_FIELD_BUILDERS) | codes - set(_PAYLOAD_BUILDERS))


#: 供 UI 展示的常量再导出（避免 GUI 二次 import 解析模块）
__all__ = [
    "build_wireless_fields",
    "build_wireless_payload",
    "wireless_request_extra",
    "wireless_di_info",
    "field_count",
    "missing_builders",
    "REQ_WITH_PAYLOAD_DI",
    "UPGRADE_STATUS",
    "ONLINE_STATE",
]
