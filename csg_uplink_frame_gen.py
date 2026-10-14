# -*- coding: utf-8 -*-
"""南网上行通信规约（协议14 Q/CSG 11109004-2013）下行组帧（纯逻辑，零 Qt）。

帧结构见 ``csg_uplink_wire``；应用层见 ``csg_uplink_parser`` 头注释。本模块只负责
「按 AFN + 信息体列表组装下行帧」，线格式全部走 ``csg_uplink_wire``（禁止第二份）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import csg_uplink_wire as W

__all__ = ["BuildError", "InfoBody", "build_frame", "da_from_pn", "da_bytes", "templates"]


class BuildError(ValueError):
    """组帧参数错误。"""


@dataclass
class InfoBody:
    """一个信息体：``DA(2B) + DI(4B, 线上低字节在前) + [数据标识内容]``。

    ``di`` 用**表序**（DI3 DI2 DI1 DI0，如 ``E0000000``/``E1006012``）；上线时按 5.1.1
    「低字节在前」自动转为 ``DI0 DI1 DI2 DI3``（唯一换算见 ``csg_uplink_di.to_wire_di``）。
    """

    da1: int = 0x01          #: 信息点元（bit0→p1）
    da2: int = 0x01          #: 信息点组
    di: str = ""             #: 4 字节十六进制串（表序；如 "" → E0000000）
    content: bytes = b""     #: 数据标识内容

    def to_bytes(self) -> bytes:
        import csg_uplink_di as DI

        di_hex = (self.di or "E0000000").replace(" ", "").upper()
        if len(di_hex) != 8:
            raise BuildError(f"DI 必须为 4 字节十六进制：{self.di!r}")
        if not (0 <= self.da1 <= 0xFF and 0 <= self.da2 <= 0xFF):
            raise BuildError("DA1/DA2 越界（0~255）")
        return (bytes([self.da1, self.da2]) + bytes.fromhex(DI.to_wire_di(di_hex))
                + bytes(self.content))


def da_from_pn(pn: int) -> Tuple[int, int]:
    """测量点号 pn（1~2032）→ ``(DA1, DA2)``；``pn = (DA2-1)*8 + bit + 1``。"""
    if not (1 <= pn <= 2032):
        raise BuildError(f"测量点号 pn 越界（1~2032）：{pn}")
    da2 = (pn - 1) // 8 + 1
    da1 = 1 << ((pn - 1) % 8)
    return da1, da2


def da_bytes(pns: Sequence[int]) -> Tuple[int, int]:
    """多个测量点号（同一组）→ ``(DA1 位组合, DA2)``。"""
    if not pns:
        return 0, 0
    grp = (pns[0] - 1) // 8 + 1
    bits = 0
    for pn in pns:
        if (pn - 1) // 8 + 1 != grp:
            raise BuildError("同一 DA 的测量点必须属于同一信息点组（8 个一组）")
        bits |= 1 << ((pn - 1) % 8)
    return bits, grp


def build_frame(
    *,
    afn: int,
    bodies: Optional[Sequence[InfoBody]] = None,
    info: bytes = b"",
    c: Optional[int] = None,
    prm: int = 1,
    dir_up: bool = False,
    fcb: int = 0,
    fcv: int = 0,
    a1: str = "000000",
    a2: int = 1,
    a3: int = 0,
    con: bool = False,
    pseq: int = 0,
    fir: int = 1,
    fin: int = 1,
    tpv: int = 0,
) -> bytes:
    """组装一帧下行/上行报文。

    - ``c`` 给定则直接作为控制域字节（覆盖 prm/dir/fcb/fcv）；
      否则按 ``dir_up/prm/fcb/fcv`` + 功能码（默认 0x04 发送/无回答 或 0x0A 请求1级）拼。
    - ``bodies`` 优先；否则用 ``info`` 原样作为信息体区字节。
    - SEQ：``tpv``(D7) / ``fir``(D6) / ``fin``(D5) / ``con``(D4) / ``pseq``(D3~D0)。
    """
    if not (0 <= afn <= 0xFF):
        raise BuildError(f"AFN 越界：{afn}")
    if bodies is not None:
        info = b"".join(b.to_bytes() for b in bodies)
    seq = ((tpv & 1) << 7) | ((fir & 1) << 6) | ((fin & 1) << 5) | ((con & 1) << 4) | (pseq & 0x0F)
    apdu = bytes([afn, seq]) + bytes(info)

    if c is None:
        # 5.1.3.6：CON=1 → 请求1级数据(10，需应用层确认)；CON=0 → 请求2级数据(11，请求数据)
        func = 0x0A if con else 0x0B
        c = ((1 if dir_up else 0) << 7) | ((prm & 1) << 6) | ((fcb & 1) << 5) | ((fcv & 1) << 4) | (func & 0x0F)

    try:
        addr = W.encode_addr(a1, a2, a3)
    except ValueError as exc:
        raise BuildError(str(exc)) from exc
    # 线格式（规范形态：长度域 = 2 字节小端 L 重复一次，整帧 = L+8）走 csg_uplink_wire 单源
    return W.encode_frame(c, addr, apdu)


def templates() -> List[dict]:
    """组帧页模板（AFN-focused）。``bodies`` 中的 DI 走 csg_uplink_di 单一来源名称。

    后 7 条为**网管（深化应用）扩展**（文档第 4 章，见 ``csg_uplink_nm``），其帧与文档
    ``send`` 实帧逐字节一致（CS 亦相同）。
    """
    import csg_uplink_di as DI

    def b(da1, da2, di, content=b""):
        return {"da1": da1, "da2": da2, "di": di, "content": content.hex().upper()}

    tpls = [
        {"name": "确认/否定（AFN=00）", "afn": 0x00, "bodies": [b(0, 0, "E0000000", b"\x00")]},
        {"name": "读参数·终端地市区县码（AFN=0A）", "afn": 0x0A, "bodies": [b(0, 0, "E0000120")]},
        {"name": "读参数·终端时间（AFN=0A）", "afn": 0x0A, "bodies": [b(0, 0, "E0000130")]},
        {"name": "读当前数据·正向有功总电能（AFN=0C）", "afn": 0x0C, "bodies": [b(0x01, 0x01, "00010000")]},
        {"name": "读当前数据·反向有功总电能（AFN=0C）", "afn": 0x0C, "bodies": [b(0x01, 0x01, "00020000")]},
        {"name": "读告警数据（AFN=13）", "afn": 0x13, "bodies": [b(0, 0, "E2000001")]},
        # ↓ 网管扩展（第4章）：与文档 send 实帧逐字节一致
        {"name": "网管扩展·查询设备台账（AFN=0A 4.1）", "afn": 0x0A,
         "bodies": [b(0x01, 0x02, "E0800402")]},
        {"name": "网管扩展·查询设备状态（AFN=0C 4.2）", "afn": 0x0C,
         "bodies": [b(0x02, 0x02, "E1006012")]},
        {"name": "网管扩展·组网成功率（AFN=0C 4.3）", "afn": 0x0C,
         "bodies": [b(0x00, 0x00, "E1800052")]},
        {"name": "网管扩展·查询网络拓扑（AFN=0C 4.5）", "afn": 0x0C,
         "bodies": [b(0x02, 0x02, "E1006014")]},
        {"name": "网管扩展·查询节点自检（AFN=0C 4.11）", "afn": 0x0C,
         "bodies": [b(0x02, 0x02, "E1006010")]},
        {"name": "网管扩展·查询/设置工作频段（AFN=04 4.9）", "afn": 0x04,
         "bodies": [b(0x00, 0x00, "E0000040", b"\x01")]},
        {"name": "网管扩展·从节点重启（AFN=04 4.12）", "afn": 0x04,
         "bodies": [b(0x00, 0x00, "E0000041", b"\x00")]},
    ]
    for t in tpls:
        t["afn_name"] = DI.AFN_NAMES.get(t["afn"], "")
        t["di_name"] = DI.value_name_unit(t["bodies"][0]["di"])[0]
    return tpls
