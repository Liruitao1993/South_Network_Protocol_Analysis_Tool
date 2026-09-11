# -*- coding: utf-8 -*-
"""LME 自定义接口「查询/设置请求」组帧（645 虚拟表作主站下发用，纯逻辑无 Qt）。

依据《LME产品相关信息生产运维接口手册_V2.4_251115》：

===========  ===========  ====  ==================================================
接口          数据ID(C)     控制码  请求数据域（未加扰逻辑字节）
===========  ===========  ====  ==================================================
4.2 单模STA  04FFAAF9      11H   仅 DI 4 字节（L=04H，手册 §4.2「无数据单元」）
4.6 双模内部 FF00DD01      11H   DI(4) + 条目信息(1B=0) + M(1B) + M×(2B 请求头)
4.7 双模设置 FF00DD01      14H   DI(4) + 条目信息(1B=0) + M(1B) + M×(2B TLV 头 + L 字节)
===========  ===========  ====  ==================================================

- **请求头**（4.6，2B 小端）：数据ID 6bit | 分类ID 3bit | 保留 7bit（填 0）
- **TLV 头**（4.7，2B 小端）：数据ID 6bit | 分类ID 3bit | 编码格式 2bit | 数据长度 5bit
  编码格式 1=ASCII / 2=BIN / 3=BCD，取自 `LME_INFO_ENTRIES` 该条目定义；长度上限 31 字节。
- 4.7 下行**不含 645 标准写数据密码组**（PA/P0P1P2/C0~C3）——手册 §4.7 下行表与仓库解析侧
  （`lme_info_entry_parser.parse_dual_entry_set_request`）同口径。

帧封装统一走 `DLT645FrameGenerator`（全仓库唯一权威：地址序/+0x33 加扰/CS/68…16）；
解析走 `DLT645Parser`（LME 深度解析已在 `dlt645_parser` 内按 DI 分派）。
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple, Union

from dlt645_frame_gen import DLT645FrameGenerator, encode_di
from lme_info_entry_parser import (
    DI_DUAL_ENTRY,
    DI_STA_VERSION_SINGLE,
    LME_INFO_ENTRIES,
    pack_lme_query_header,
    pack_lme_query_request,
)

#: 三种下发类型（UI 按钮 1:1 对应）
KIND_SINGLE_STA = "4.2"   # 读模块版本：HPLC 单模 STA 详细版本信息
KIND_DUAL_STA = "4.6"     # 读内部详细信息：HPLC 双模 STA 内部信息条目
KIND_DUAL_SET = "4.7"     # 设置：HPLC 双模 STA 详细信息条目

#: 手册 §5.1.1「虚拟电表上位机」示例口径（点对点测试底板）
DEFAULT_ADDR = "AAAAAAAAAAAA"

#: TLV 头长度域仅 5 bit
MAX_ENTRY_LEN = 31

#: TLV 编码格式
ENC_ASCII, ENC_BIN, ENC_BCD = 1, 2, 3

#: 控制码（D4~D0 功能码）；D7=DIR 由 build_control 置位
FUNC_READ = 0x11
FUNC_WRITE = 0x14

_CTRL_NAMES = {FUNC_READ: "读数据", FUNC_WRITE: "写数据"}

_HEX_CHARS = set("0123456789abcdefABCDEF")

EntryItem = Tuple[int, int]
SetItem = Tuple[int, int, bytes]


# ---------------------------------------------------------------------------
# 输入解析与校验（错误信息为中文，UI 直接弹）
# ---------------------------------------------------------------------------

def clean_address(addr: str) -> str:
    """规范化并校验目标表地址（12 位十六进制），非法抛中文 ValueError。"""
    s = "".join(ch for ch in (addr or "") if ch not in " \t-:_")
    if s[:2].upper() == "0X":
        s = s[2:]
    s = s.upper()
    if len(s) != 12 or any(ch not in _HEX_CHARS for ch in s):
        raise ValueError(
            f"目标地址必须是 12 位十六进制（当前 {addr!r}）；"
            "模块直连可用 AAAAAAAAAAAA（手册示例口径）")
    return s


def _to_int(text: str, label: str) -> int:
    """十进制为主、`0x` 前缀表示十六进制（避免 '08' 被当八进制）。"""
    s = (text or "").strip()
    try:
        return int(s, 16) if s[:2].lower() == "0x" else int(s, 10)
    except ValueError:
        raise ValueError(f"{label}必须是整数（当前 {text!r}）")


def _check_cat_id(cat: int, data_id: int) -> None:
    if not 0 <= cat <= 0x07:
        raise ValueError(f"LME 分类ID 应为 0~7（当前 {cat}）")
    if not 0 <= data_id <= 0x3F:
        raise ValueError(f"LME 数据ID 应为 0~63（当前 {data_id}）")


def entry_name(cat: int, data_id: int) -> str:
    """条目中文名（查 LME_INFO_ENTRIES）；未知条目回 '分类c/数据d'。"""
    info = LME_INFO_ENTRIES.get(cat, {}).get(data_id)
    return info[0] if info else f"分类{cat}/数据{data_id}"


def entry_encoding(cat: int, data_id: int) -> int:
    """4.7 TLV 头编码格式位：取条目定义；未定义条目按 BIN(2)。"""
    info = LME_INFO_ENTRIES.get(cat, {}).get(data_id)
    enc = info[1] if info else ENC_BIN
    return enc if enc in (ENC_ASCII, ENC_BIN, ENC_BCD) else ENC_BIN


def parse_entry_items(text: str) -> List[EntryItem]:
    """4.6 条目串 → [(分类ID, 数据ID)]；空串 → []（= M=0 读模块全部支持条目）。"""
    out: List[EntryItem] = []
    for part in (text or "").replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "/" not in part:
            raise ValueError(
                f"4.6 条目格式应为 分类/数据ID（当前 {part!r}），如 0/15")
        cat_s, id_s = part.split("/", 1)
        cat, data_id = _to_int(cat_s, "分类ID"), _to_int(id_s, "数据ID")
        _check_cat_id(cat, data_id)
        out.append((cat, data_id))
    return out


def parse_set_items(text: str) -> List[SetItem]:
    """4.7 条目串 → [(分类ID, 数据ID, 数据bytes)]；必填至少 1 条。"""
    out: List[SetItem] = []
    for part in (text or "").replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(
                f"4.7 条目格式应为 分类/数据ID:数据hex（当前 {part!r}），如 0/15:0500")
        head, raw_text = part.split(":", 1)
        if "/" not in head:
            raise ValueError(
                f"4.7 条目格式应为 分类/数据ID:数据hex（当前 {part!r}），如 0/15:0500")
        cat_s, id_s = head.split("/", 1)
        cat, data_id = _to_int(cat_s, "分类ID"), _to_int(id_s, "数据ID")
        _check_cat_id(cat, data_id)
        raw = "".join(ch for ch in raw_text if ch not in " \t")
        if (not raw) or len(raw) % 2 or any(ch not in _HEX_CHARS for ch in raw):
            raise ValueError(
                f"4.7 条目数据必须是偶数位十六进制（分类{cat}/数据{data_id} 当前 {raw_text!r}）")
        out.append((cat, data_id, bytes.fromhex(raw)))
    if not out:
        raise ValueError(
            "4.7 设置必须至少填写 1 个条目（格式 分类/数据ID:数据hex，"
            "如 0/15:0500）")
    return out


def describe_items(text: str, kind: str = KIND_DUAL_SET) -> List[str]:
    """确认框/日志用条目描述：['分类0/数据15 本地接口默认信息 (2 字节)', ...]"""
    if kind == KIND_DUAL_STA:
        return [f"分类{c}/数据{d} {entry_name(c, d)}" for c, d in parse_entry_items(text)]
    return [f"分类{c}/数据{d} {entry_name(c, d)}（{len(raw)} 字节）"
            for c, d, raw in parse_set_items(text)]


# ---------------------------------------------------------------------------
# TLV 头（4.7）
# ---------------------------------------------------------------------------

def pack_set_header(cat: int, data_id: int, encoding: int, length: int) -> bytes:
    """4.7 条目 TLV 头（2 字节小端）：数据ID 6bit | 分类ID 3bit | 编码 2bit | 长度 5bit。"""
    _check_cat_id(cat, data_id)
    if not 0 <= length <= MAX_ENTRY_LEN:
        raise ValueError(
            f"条目数据长度 {length} 超出 5bit 上限 {MAX_ENTRY_LEN} 字节"
            f"（分类{cat}/数据{data_id}）")
    header = (int(data_id) | (int(cat) << 6)
              | ((int(encoding) & 0x03) << 9) | ((int(length) & 0x1F) << 11))
    return header.to_bytes(2, "little")


# ---------------------------------------------------------------------------
# 组帧（三条入口）
# ---------------------------------------------------------------------------

def _gen() -> DLT645FrameGenerator:
    return DLT645FrameGenerator()


def build_single_sta_query(addr: str = DEFAULT_ADDR) -> bytes:
    """手册 4.2：C=11H，数据域仅 DI（04FFAAF9），L=04H。"""
    gen = _gen()
    return gen.build_frame(clean_address(addr), gen.build_control(FUNC_READ),
                           encode_di(DI_STA_VERSION_SINGLE))


def build_dual_query(addr: str = DEFAULT_ADDR, entries: Union[str, Sequence] = "") -> bytes:
    """手册 4.6：C=11H，DI + 条目信息(0) + M + M×2B 请求头；entries 留空 = M=0。"""
    items: List[EntryItem]
    if isinstance(entries, str):
        items = parse_entry_items(entries)
    else:
        items = [(int(c), int(d)) for c, d in entries]
        for c, d in items:
            _check_cat_id(c, d)
    gen = _gen()
    payload = encode_di(DI_DUAL_ENTRY) + pack_lme_query_request(items)
    return gen.build_frame(clean_address(addr), gen.build_control(FUNC_READ), payload)


def build_dual_set(addr: str = DEFAULT_ADDR, items: Union[str, Sequence] = "") -> bytes:
    """手册 4.7：C=14H，DI + 条目信息(0) + M + M×(2B TLV 头 + L 字节数据)。"""
    parsed: List[SetItem]
    if isinstance(items, str):
        parsed = parse_set_items(items)
    else:
        parsed = []
        for row in items:
            cat, data_id, raw = int(row[0]), int(row[1]), bytes(row[2])
            _check_cat_id(cat, data_id)
            parsed.append((cat, data_id, raw))
        if not parsed:
            raise ValueError("4.7 设置必须至少填写 1 个条目")
    data = bytearray(encode_di(DI_DUAL_ENTRY))
    data += bytes([0x00, len(parsed) & 0xFF])
    for cat, data_id, raw in parsed:
        data += pack_set_header(cat, data_id, entry_encoding(cat, data_id), len(raw))
        data += raw
    gen = _gen()
    return gen.build_frame(clean_address(addr), gen.build_control(FUNC_WRITE), bytes(data))


#: 类型 → 组帧函数（UI 三个按钮共用）
_BUILDERS = {
    KIND_SINGLE_STA: lambda addr, text: build_single_sta_query(addr),
    KIND_DUAL_STA: build_dual_query,
    KIND_DUAL_SET: build_dual_set,
}

KIND_LABELS = {
    KIND_SINGLE_STA: "读模块版本（4.2 单模STA详细版本 04FFAAF9）",
    KIND_DUAL_STA: "读内部详细信息（4.6 双模STA内部信息 FF00DD01）",
    KIND_DUAL_SET: "设置（4.7 双模STA详细信息 FF00DD01）",
}

#: 该类型是否需要条目参数（4.2 无数据单元）
KIND_NEEDS_ENTRIES = {
    KIND_SINGLE_STA: False,
    KIND_DUAL_STA: True,
    KIND_DUAL_SET: True,
}


def build_query(kind: str, addr: str = DEFAULT_ADDR, text: str = "") -> bytes:
    """UI 分派入口：按类型组帧；text 语义随类型（4.6 条目 / 4.7 条目:数据）。"""
    builder = _BUILDERS.get(kind)
    if builder is None:
        raise ValueError(f"未知下发类型 {kind!r}")
    return builder(addr, text)


def describe_frame(frame: bytes) -> str:
    """帧摘要（日志/提示用）：控制码 + 长度域 + 数据域（未加扰逻辑字节）。

    645 帧布局：`68 A0..A5 68 C L DATA CS 16` → C 在 idx8、L 在 idx9、DATA 从 idx10。
    """
    if len(frame) < 12:
        return "帧不完整"
    ctrl, length = frame[8], frame[9]
    payload = DLT645FrameGenerator.descramble(frame[10:10 + length])
    func = ctrl & 0x1F
    parts = [
        f"地址 {frame[1:7].hex().upper()}",
        f"控制码 C={ctrl:02X}H（{'从站' if ctrl & 0x80 else '主站'}·"
        f"{_CTRL_NAMES.get(func, f'功能码{func:02X}')}）",
        f"L={length} 字节",
        f"数据域 {' '.join(f'{b:02X}' for b in payload)}",
    ]
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# 回包解析（复用 DLT645Parser 的 LME 深度解析）
# ---------------------------------------------------------------------------

_parser = None


def _get_parser():
    global _parser
    if _parser is None:
        from dlt645_parser import DLT645Parser
        _parser = DLT645Parser()
    return _parser


def decode_reply(frame: bytes) -> Dict:
    """模块回包 → DLT645Parser 解析结果（LME 自定义 DI 已深度展开）。"""
    return _get_parser().parse(bytes(frame))


def reply_rows(parsed: Dict) -> List[Tuple[str, str, str, str]]:
    """解析结果 → (字段, 原始值, 解析值, 说明) 行；兼容 3/4 元组 fields。"""
    rows: List[Tuple[str, str, str, str]] = []
    for item in (parsed or {}).get("fields") or []:
        seq = list(item) if isinstance(item, (tuple, list)) else [item]
        if len(seq) >= 4:
            rows.append((str(seq[0]), str(seq[1]), str(seq[2]), str(seq[3])))
        elif len(seq) == 3:
            rows.append((str(seq[0]), str(seq[1]), "", str(seq[2])))
        else:
            rows.append((str(seq[0]) if seq else "", "", "", ""))
    return rows


def reply_summary(parsed: Dict) -> str:
    """回包一行摘要：接口名 + 关键版本字段（供日志）。"""
    name = str((parsed or {}).get("di_desc") or "")
    keep = ("外部厂商代码", "外部芯片代码", "外部版本号", "外部版本日期",
            "MCU内部版本号", "应用层(APS)版本号", "网络层(NWK)版本号",
            "物理层(PHY)版本号", "编译时间", "总工程版本", "芯片程序版本")
    bits = []
    for field, _raw, value, _desc in reply_rows(parsed):
        short = field.replace("└", "").strip()
        if short in keep and value:
            bits.append(f"{short}={value.strip()}")
    tail = ("；" + "，".join(bits)) if bits else ""
    return (name or "（未识别接口）") + tail
