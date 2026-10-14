# -*- coding: utf-8 -*-
"""南网上行通信规约（协议14 Q/CSG 11109004-2013）—— 应用层常量与数据标识（DI）索引。

数据来源：
- 附 A/B/D/E 的 DI 索引：``csg_uplink_di_data.DI_ENTRIES``（由 ``tools/gen_csg_uplink_di.py``
  从条文解释 PDF 用 pdfplumber 抽取）；
- 附 C（测量点当前/历史数据）：本部分明写「支持 DL/T 645—2007 中的数据标识，传输时不加 33H」
  （附 C.2 首句），故**直接复用**协议6 的 ``dlt645_di.json``；
- 附 F 出错否定代码：``csg_uplink_di_data.ERR_CODES``；
- **网管（深化应用）扩展**（``csg_uplink_nm.NM_DIS``）：来自
  ``协议文档/14.南网上行通信规约/新一代计量自动化主站通信网络管理技术要求.docx`` 第 4 章
  「终端上行规约（针对网络管理扩展）」，含 AFN=0A/0C/04/13 下的 15 个扩展 DI 与结构化解码。

⚠ **DI 线上字节序 = 低字节在前**（表 ``E1 00 60 12`` → 线上 ``12 60 00 E1``）：与 5.1.1
「低字节在前，高字节在后」、协议0（``protocol_parser`` 用 ``di_bytes[::-1]``）及 DL/T645 同族约定
一致，并由网管扩展文档的实帧（CS 自洽）实证。索引键一律用**表序（DI3 DI2 DI1 DI0）**，
线上/表序换算见 :func:`to_semantic_di` / :func:`to_wire_di`。

本模块是解析器 / 查询页 / Web 的**唯一 DI 事实来源**（禁止在调用方再写一份）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from csg_uplink_di_data import DI_ENTRIES as _PDF_DI_ENTRIES, ERR_CODES
import csg_uplink_nm as _NM

__all__ = [
    "AFN_NAMES",
    "AFN_RESET",
    "DENSITY_NAMES",
    "TIME_BYTES",
    "ERR_CODES",
    "DI_ENTRIES",
    "DI_INDEX",
    "NM_APPX",
    "NM_APPX_NAME",
    "nm_names",
    "di_appendix",
    "di_info",
    "search_di",
    "decode_di_value",
    "decode_bcd_number",
    "format_645_di",
    "content_length",
    "value_name_unit",
    "to_semantic_di",
    "to_wire_di",
    "resolve_di",
]

# ── 应用层功能码 AFN（6.1.1 表6；01H 复位取自 5.1.3 功能码-AFN 对应表）────────

AFN_NAMES: Dict[int, str] = {
    0x00: "确认/否定",
    0x01: "复位",
    0x02: "链路接口检测",
    0x04: "写参数",
    0x06: "身份认证及密钥协商",
    0x0A: "读参数",
    0x0C: "读当前数据",
    0x0D: "读历史数据",
    0x0E: "读事件记录",
    0x0F: "文件传输",
    0x10: "中继转发",
    0x12: "读任务数据",
    0x13: "读告警数据",
    0x14: "级联命令",
    0x15: "用户自定义数据",
}
AFN_RESET = 0x01

#: 数据密度 m（6.1.6.3 表10）
DENSITY_NAMES: Dict[int, str] = {
    0: "终端历史数据存储密度",
    1: "1分钟",
    2: "5分钟",
    3: "15分钟",
    4: "30分钟",
    5: "60分钟",
    6: "1日",
    7: "1月",
}

#: 数据时间（6.1.6.1）：YYYY MM DD hh mm，BCD，共 6 字节
TIME_BYTES = 6

# ── DI 索引（附 A/B/D/E + 网管扩展 N）──────────────────────────────────

NM_APPX = _NM.NM_APPX
NM_APPX_NAME = _NM.NM_APPX_NAME

#: 附 A/B/D/E（PDF 抽取）+ 网管扩展（第4章）合并后的 DI 清单（查询页/解析器同源）
DI_ENTRIES: List[dict] = list(_PDF_DI_ENTRIES)

_PDF_INDEX: Dict[str, dict] = {e["di"]: e for e in DI_ENTRIES}
for _e in _NM.NM_DIS:
    _cur = _PDF_INDEX.get(_e["di"])
    if _cur is None:
        DI_ENTRIES.append(dict(_e))
    else:
        # 同号 DI 已被 2013 版清单收录（如 E2000033 终端掉电 / E2000034 终端上电）：
        # 保留原条目，补记网管扩展名称与归属，避免丢信息也不重复建条目
        _cur["name"] = f"{_cur['name']}｜{_e['name']}"
        _cur["nm"] = True
        _cur["nm_group"] = _e["group"]

DI_INDEX: Dict[str, dict] = {e["di"]: e for e in DI_ENTRIES}


def to_semantic_di(di: str) -> str:
    """线上 DI（低字节在前）→ 表序 DI（``12 60 00 E1`` → ``E1006012``）；非 8 位原样返回。"""
    d = (di or "").replace(" ", "").upper()
    if len(d) != 8:
        return d
    return "".join(d[i:i + 2] for i in range(6, -1, -2))


def to_wire_di(di: str) -> str:
    """表序 DI → 线上 DI（低字节在前）；组帧与 ``to_semantic_di`` 互为逆运算。"""
    return to_semantic_di(di)


def resolve_di(di: str) -> Optional[dict]:
    """DI（表序，支持前缀规则如 ``E0800402`` → ``E08004FF``）→ 索引条目；未收录返回 None。"""
    d = (di or "").replace(" ", "").upper()
    e = DI_INDEX.get(d)
    if e is not None:
        return e
    target = _NM.resolve_prefix(d)
    if target is not None:
        return DI_INDEX.get(target)
    return None


def nm_names() -> List[str]:
    """网管扩展 DI（表序）清单，供文档/自检使用。"""
    return [e["di"] for e in _NM.NM_DIS]


def di_appendix(di: str) -> Optional[str]:
    """DI → 归属附录字母（A/B/C/D/E/N）；附 C 走 645 表，无法静态判定。"""
    e = resolve_di(di)
    return e["appx"] if e else None


def di_info(di: str) -> Optional[dict]:
    """4 字节 DI（表序十六进制串）→ 索引条目；附 A/B/D/E/N 命中返回 dict，否则 None。"""
    return resolve_di(di)


def search_di(keyword: str, appx: Optional[str] = None, limit: int = 200) -> List[dict]:
    """按 DI 前缀或名称关键字检索（供查询页/命令行）。``keyword`` 为空返回全部。"""
    kw = (keyword or "").strip().upper()
    out = []
    for e in DI_ENTRIES:
        if appx and e["appx"] != appx:
            continue
        if kw and kw not in e["di"] and kw not in e["name"].upper():
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


# ── 数据值解码 ────────────────────────────────────────────────────────


def decode_bcd_number(raw: bytes, decimals: int = 0) -> Optional[str]:
    """BCD 字节串 → 带小数点的十进制串（非 BCD 返回 None）。

    ⚠ 按 5.2「低字节在前，高字节在后」：线上**低位字在前**，故先整体倒序再取数字。
    例：``78 56 34 12``（低字节在前）→ ``123456.78``（decimals=2）。
    """
    digits = ""
    for b in reversed(bytes(raw)):
        hi, lo = b >> 4, b & 0x0F
        if hi > 9 or lo > 9:
            return None
        digits += f"{hi}{lo}"
    digits = digits.lstrip("0") or "0"
    if decimals:
        if len(digits) <= decimals:
            digits = digits.rjust(decimals + 1, "0")
        return f"{digits[:-decimals]}.{digits[-decimals:]}"
    return digits


def _decimals_from_fmt(fmt: str) -> int:
    """从数据格式串（如 ``NNNNNN.NN`` / 645 的 ``XXXXXX.XX``）取小数位数。"""
    tail = (fmt or "").split(".")[-1]
    n = 0
    for ch in tail:
        if ch in "NnXx":
            n += 1
        else:
            break
    return n


def decode_di_value(di: str, raw: bytes) -> Dict[str, object]:
    """DI + 数据标识内容原始字节 → ``{原始值, 解析值, 说明, 长度}``。

    解码策略（南网文档 ``NN`` 既用于 BIN 参数也用于 BCD 电量，故**并给两种口径**）：
    - BIN（小端十进制）恒给出；
    - 数据格式含小数点位或全 N/X 占位时，若为合法 BCD 再给 BCD 口径（含小数）；
    - 时间类格式给 BCD 时间串；附 C 走 645 数据标识表。
    """
    name, unit, fmt = value_name_unit(di)
    result: Dict[str, object] = {
        "原始值": raw.hex(" ").upper(),
        "长度": len(raw),
        "数据格式": fmt,
        "名称": name,
    }
    if not raw:
        result["解析值"] = ""
        result["说明"] = name
        return result

    d = (di or "").replace(" ", "").upper()
    if d == "E0000000" and len(raw) == 1:
        result["解析值"] = "确定" if raw[0] == 0x00 else ("否定" if raw[0] == 0x01 else f"0x{raw[0]:02X}")
        result["说明"] = "全部确认/否定（A.1）"
        return result

    # 网管（深化应用）扩展：结构化逐字段解码
    nm = _NM.decode(d, raw)
    if nm:
        name, _unit, fmt = value_name_unit(d)
        result["名称"] = name
        result["数据格式"] = fmt
        result["解析值"] = str(nm.get("解析值") or "")
        result["说明"] = str(nm.get("说明") or "")
        result["子项"] = nm.get("子项", [])
        return result

    # 时间类（YYMMDDhhmmss / DDhhmmss 等，全 BCD）
    if "Y" in fmt.upper() or "h" in fmt or "M" in fmt:
        bcd = decode_bcd_number(raw)
        result["解析值"] = bcd if bcd is not None else raw.hex(" ").upper()
        result["说明"] = (f"{name}（BCD 时间，格式 {fmt}）" if name else f"BCD 时间，格式 {fmt}")
        return result

    dec = _decimals_from_fmt(fmt)
    bin_val = int.from_bytes(raw, "little")
    parts = [f"BIN={bin_val}{(' ' + unit) if unit else ''}"]
    bcd = decode_bcd_number(raw, dec)
    if bcd is not None and (dec > 0 or any(ch in "NnXx" for ch in fmt)):
        parts.append(f"BCD={bcd}{(' ' + unit) if unit else ''}")
    result["解析值"] = " / ".join(parts)
    result["说明"] = name or "（未收录 DI，按原始字节展示）"
    return result


def format_645_di(di: str, name: str = "", unit: str = "") -> str:
    """附 C 复用 645 时的名称后缀（供解析器统一文案）。"""
    return name + (f"（{unit}）" if unit else "")


# ── 数据标识内容长度 / 名称（附 C 复用 645 表）────────────────────────────

_DLT645_INDEX: Optional[Dict[str, dict]] = None


def _load_645() -> Dict[str, dict]:
    """懒加载协议6 的 ``dlt645_di.json``（附 C 测量点数据沿用 645 数据标识）。"""
    global _DLT645_INDEX
    if _DLT645_INDEX is None:
        import json
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dlt645_di.json")
        try:
            with open(path, encoding="utf-8") as f:
                _DLT645_INDEX = json.load(f).get("di_map", {})
        except Exception:
            _DLT645_INDEX = {}
    return _DLT645_INDEX


def content_length(di: str, data: bytes = b"") -> Optional[int]:
    """DI → 数据标识内容字节数；无法静态确定（变长/集合）返回 None。

    ``data`` 为该信息体的**内容起始字节**（可空）：网管扩展的变长列表 DI
    （``E1006012``/``E1006004``/…）据其「总数 + 本次数量」推算内容长度。
    """
    d = (di or "").replace(" ", "").upper()
    if d == "E0000000":       # 全部确认/否定（A.1）
        return 1
    nm = _NM.content_length(d, data)
    if nm is not None:
        return nm
    e = resolve_di(d)
    if e is not None:
        nb = (e.get("nbytes") or "").strip()
        return int(nb) if nb.isdigit() else None
    m = _load_645().get(d)
    if m and isinstance(m.get("length"), int):
        return m["length"]
    return None


def value_name_unit(di: str) -> Tuple[str, str, str]:
    """DI → ``(名称, 单位, 数据格式)``；未收录返回三个空串。"""
    d = (di or "").replace(" ", "").upper()
    e = resolve_di(d)
    if e is not None:
        return e.get("name", ""), e.get("unit", ""), e.get("fmt", "")
    m = _load_645().get(d)
    if m:
        return m.get("name", ""), m.get("unit", ""), m.get("data_type", "")
    return "", "", ""
