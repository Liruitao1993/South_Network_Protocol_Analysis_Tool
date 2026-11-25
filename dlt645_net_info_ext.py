# -*- coding: utf-8 -*-
"""DL/T645-2007 扩展：**入网信息**（DI ``FFAA0001``，双模/中继模块）。

依据现场报文（用户提供，2026-11-10）与厂家给出的字段定义实现：

**读取帧**（主站请求，控制码 11H，数据域只有 4 字节数据标识）::

    68 AA AA AA AA AA AA 68 11 04 34 33 DD 32 57 16
                                        └─ DI ─┘

**应答帧**（从站应答，控制码 91H，L = 16H = 22 字节）::

    68 33 00 98 06 55 07 68 91 16
       34 33 DD 32                       数据标识 DI（低字节在前，各字节已加 33H）
       34                                入网状态
       66 33 CB 39 88 3A                 STA 地址（低位在前）
       35 43                             本节点 TEI
       34 33                             代理节点 TEI
       44                                入网通道 / 角色 / 入网层级
       B4 68 B4 93 39 33                 入网 CCO 地址（低位在前）
    9F 16

**字段定义（用户口径）**

- 入网状态 1B：``0`` 未入网 / ``1`` 已入网 / ``2`` 离网；
- STA 地址 6B：BCD，低位在前（与 645 地址域同序）；
- 本节点 TEI 2B（低字节在前）：16bit 值**高 4bit 固定为 1**，低 12bit 为 TEI；
- 代理节点 TEI 2B（低字节在前）：同上取低 12bit；高 4bit 不作强制
  （本帧为 0，按「原值」如实展示，不硬套规则）；
- 入网通道/角色/层级 1B：bit7 入网通道（0 载波 / 1 无线）、
  bit6~bit4 角色（1 末端节点 / 2 代理节点）、bit3~bit0 入网层级；
- 入网 CCO 地址 6B：BCD，低位在前。

**注意**：解析器传进来的 ``data`` 已经是**减 33H 之后**的真实字节
（``dlt645_parser.parse()`` 的 `result['data']`），本模块不再做偏移处理。

实测自证（上面那帧）：入网状态=1（已入网）、STA=075506980033、
本节点 TEI=0x1002 → TEI=2、代理 TEI=0x0001 → TEI=1、
通道=载波 / 角色=末端节点 / 层级=1、CCO=000660813581。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#: 入网信息数据标识（减 33H 后、低字节在前拼成的 8 位十六进制）
DI_NET_JOIN_INFO = "FFAA0001"

#: 应答帧数据域长度：4(DI) + 18 = 22 = 0x16
NET_INFO_BODY_LEN = 18

#: 入网状态
JOIN_STATE_TEXT = {
    0: "未入网",
    1: "已入网",
    2: "离网",
}

#: 入网通道（bit7）
JOIN_CHANNEL_TEXT = {
    0: "载波",
    1: "无线",
}

#: 角色（bit6~bit4）
JOIN_ROLE_TEXT = {
    1: "末端节点",
    2: "代理节点",
}

#: DI 表条目（进 dlt645_di.json 同构结构；`length` 含 4 字节 DI）
NET_INFO_DI_MAP: Dict[str, dict] = {
    DI_NET_JOIN_INFO: {
        "name": "入网信息（双模/中继模块）",
        "unit": "",
        "data_type": "结构",
        "length": 22,
    },
}


def merge_net_info_di_map(base: Optional[dict]) -> dict:
    """把入网信息 DI 并入 DI 映射表（返回新 dict，不改入参）。"""
    merged = dict(base or {})
    merged.update(NET_INFO_DI_MAP)
    return merged


def is_net_info_di(di_code: str) -> bool:
    """是否命中入网信息数据标识。"""
    return str(di_code or "").upper() == DI_NET_JOIN_INFO


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _bcd_text(data: bytes) -> str:
    """BCD 字节串 → 连续数字文本（低位在前由调用方负责反序）。"""
    out: List[str] = []
    for byte in data:
        hi, lo = (byte >> 4) & 0x0F, byte & 0x0F
        if hi > 9 or lo > 9:
            return ""
        out.append(f"{hi}{lo}")
    return "".join(out)


def _addr_text(data: bytes) -> str:
    """6 字节地址 → 高位在前的 BCD 文本（帧内低位在前）。"""
    if len(data) != 6:
        return ""
    digits = _bcd_text(bytes(reversed(data)))
    if not digits:
        return ""
    return " ".join(digits[i:i + 2] for i in range(0, len(digits), 2))


def _tei_rows(name: str, chunk: bytes, fixed_high_nibble: bool) -> List[Tuple[str, str, str, str]]:
    """TEI 字段（2 字节，低字节在前，低 12bit 为 TEI）。"""
    if len(chunk) < 2:
        return []
    value = int.from_bytes(chunk[0:2], "little")
    high = (value >> 12) & 0x0F
    tei = value & 0x0FFF
    rows: List[Tuple[str, str, str, str]] = []
    if fixed_high_nibble:
        note = "16bit 值高 4bit 固定为 1，低 12bit 为 TEI（低字节在前）"
        parsed = f"0x{value:04X} → TEI={tei}（0x{tei:03X}）"
        if high != 1:
            rows.append((
                f"  └ ⚠ {name} 高4bit",
                f"0x{high:X}",
                f"0x{high:X}（协议规定固定为 1）",
                "按文件口径高 4bit 应为 1；此处如实显示帧内值，请核对原始报文",
            ))
    else:
        note = "低 12bit 为 TEI（低字节在前）；高 4bit 未定义语义"
        parsed = f"0x{value:04X} → TEI={tei}（0x{tei:03X}）"
        if high == 0:
            parsed += "（高4bit=0）"
    rows.insert(0, (f"  └ {name}", _hex(chunk[0:2]), parsed, note))
    return rows


def parse_net_info(di_code: str, ctrl: int,
                   data: bytes) -> Tuple[List[Tuple[str, str, str, str]], str]:
    """解析入网信息数据项。

    :param di_code: 数据标识（``FFAA0001``）
    :param ctrl: 控制码（0x11 读数据请求 / 0x91 读数据应答 …）
    :param data: **已减 33H** 的完整数据域（前 4 字节为 DI）
    :return: ``(rows, di_name)``；rows 为 ``(字段, 原始值, 解析值, 说明)``
    """
    name = NET_INFO_DI_MAP[DI_NET_JOIN_INFO]["name"]
    if not is_net_info_di(di_code):
        return [], ""

    data = bytes(data or b"")
    body = data[4:]
    rows: List[Tuple[str, str, str, str]] = []

    if not body:
        rows.append((
            "  └ 入网信息",
            "",
            "请求帧：仅数据标识，无数据域",
            f"控制码 {ctrl:02X}H 的读请求，等待从站以 91H 应答返回 18 字节数据",
        ))
        return rows, name

    if len(body) < NET_INFO_BODY_LEN:
        rows.append((
            "  └ ⚠ 数据域不足",
            _hex(body),
            f"{len(body)} 字节",
            f"入网信息应为 {NET_INFO_BODY_LEN} 字节（4 字节 DI + 18 字节数据），"
            "以下按实际字节尽量解析，缺项留空",
        ))

    state = body[0] if len(body) > 0 else None
    rows.append((
        "  └ 入网状态",
        f"{state:02X}" if state is not None else "",
        (f"{state}（{JOIN_STATE_TEXT.get(state, '保留')}）"
         if state is not None else "（缺）"),
        "0-未入网 1-已入网 2-离网（其他值保留）",
    ))

    sta = body[1:7]
    rows.append((
        "  └ STA 地址",
        _hex(sta),
        _addr_text(sta) or "（BCD 非法）" if sta else "（缺）",
        "6 字节 BCD，低位在前（与 645 地址域同序）",
    ))

    rows.extend(_tei_rows("本节点 TEI", body[7:9], fixed_high_nibble=True))
    rows.extend(_tei_rows("代理节点 TEI", body[9:11], fixed_high_nibble=False))

    if len(body) > 11:
        flag = body[11]
        channel = (flag >> 7) & 0x01
        role = (flag >> 4) & 0x07
        level = flag & 0x0F
        role_text = JOIN_ROLE_TEXT.get(role, f"保留({role})")
        rows.append((
            "  └ 入网通道/角色/层级",
            f"{flag:02X}H",
            f"通道={JOIN_CHANNEL_TEXT.get(channel, channel)}"
            f" / 角色={role_text} / 层级={level}",
            "bit7 入网通道（0-载波 1-无线）、bit6~bit4 角色（1-末端节点 2-代理节点）、"
            "bit3~bit0 入网层级",
        ))
    else:
        rows.append(("  └ 入网通道/角色/层级", "", "（缺）", "数据域不足 12 字节"))

    cco = body[12:18]
    rows.append((
        "  └ 入网 CCO 地址",
        _hex(cco),
        _addr_text(cco) or "（BCD 非法）" if cco else "（缺）",
        "6 字节 BCD，低位在前；模块当前入网所属 CCO 的地址",
    ))

    if len(body) > NET_INFO_BODY_LEN:
        rows.append((
            "  └ 多余字节",
            _hex(body[NET_INFO_BODY_LEN:]),
            f"{len(body) - NET_INFO_BODY_LEN} 字节",
            "超出 18 字节的部分（协议未定义，原样保留备查）",
        ))
    return rows, name
