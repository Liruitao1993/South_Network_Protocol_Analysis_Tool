# -*- coding: utf-8 -*-
"""抄读「正向有功总电能」报文的构造（纯逻辑，零 Qt）。

用途
----
流程测试里的抄表类步骤（`13H F1 监控从节点`、`14H F1 路由请求抄读内容` 等）需要一个
**真正可抄的报文内容**，且必须与从节点的协议一致：

- 645-2007 电能表：``68 <表地址6B 低字节在前> 68 11 04 33 33 34 33 <CS> 16``
  （DI 00010000 正向有功总电能，+0x33 加扰）
- 698.45 电能表：GET-Request-Normal，OAD = 00100200（正向有功总电能），SA 带单地址特征 0x05

以前流程里只填了协议类型、报文长度写了 0、内容为空 —— 被测 CCO 收到的是空报文，
自然抄不回来。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

#: 正向有功总电能 DI（645-2007）
DI_TOTAL_ACTIVE_645 = "00010000"
#: 正向有功总电能 OAD（698.45）
OAD_TOTAL_ACTIVE_698 = "00100200"

#: 1376.2 的「通信协议类型」取值
MSG_PROTO_645_1997 = 1
MSG_PROTO_645_2007 = 2
MSG_PROTO_698 = 3

#: 组网参数里的协议代号（与 gdw_test_network.PROTO_* 一致）
NODE_PROTO_645_1997 = 1
NODE_PROTO_645_2007 = 2
NODE_PROTO_698 = 3


def _addr_bytes(addr: str) -> bytes:
    """12 位表地址 → 6 字节 BCD（低字节在前）。"""
    text = "".join(ch for ch in str(addr or "") if ch.isdigit()).rjust(12, "0")[:12]
    return bytes.fromhex(text)[::-1]


# ── 读报文必须落在「虚拟表支持的 OAD / DI」上 ────────────────────────────
# 用户口径（2026-10-30）：抄读内容要用虚拟表支持的 OAD 和 APDU，否则被测 CCO
# 抄不到正确响应。虚拟表的档案（meter_sim_data.json / 645 档案）是用户可编辑的数据，
# 硬编码一个档案里没有的标识，虚拟表只会回「对象不存在 / 数据标识不存在」。

def supported_698_oads() -> List[str]:
    """虚拟表档案里支持的 OAD 列表（大写 8 位 hex）；导入失败时返回空。"""
    try:
        from meter_sim.archive import load_archive

        arch = load_archive()
    except Exception:                       # 虚拟表不可用时按「不知道」处理
        return []
    out: List[str] = []
    for item in getattr(arch, "items", None) or []:
        key = str(item.get("key") or "").strip().upper()
        if len(key) == 8 and all(c in "0123456789ABCDEF" for c in key):
            out.append(key)
    return out


def supported_645_dis() -> List[str]:
    """虚拟表 645 档案里支持的数据标识（DI）列表；导入失败时返回空。"""
    try:
        from dlt645_sim.archive import DLT645Archive

        data = DLT645Archive().as_dict()
    except Exception:                       # noqa: BLE001
        return []
    return [str(k).strip().upper() for k in (data or {})]


def pick_698_oad(preferred: str = OAD_TOTAL_ACTIVE_698) -> str:
    """挑一个虚拟表支持的 OAD：优先正向有功总电能，档案里没有就退到任意电能量项。"""
    want = str(preferred or "").strip().upper()
    oads = supported_698_oads()
    if not oads or want in oads:
        return want
    # 退一步：优先 attr=02 的电能量项（OAD = OI(2B) + attr(1B) + idx(1B)）
    energy = [o for o in oads if o[4:6] == "02"]
    return (energy[0] if energy else oads[0]).upper()


def pick_645_di(preferred: str = DI_TOTAL_ACTIVE_645) -> str:
    """挑一个虚拟表支持的 645 DI：优先正向有功总电能，档案里没有就退到任意电能量项。"""
    want = str(preferred or "").strip().upper()
    dis = supported_645_dis()
    if not dis or want in dis:
        return want
    energy = [d for d in dis if len(d) == 8 and d.endswith("0000")]
    return (energy[0] if energy else dis[0]).upper()


def build_645_read_total_active(addr: str, di: Optional[str] = None) -> bytes:
    """645-2007 读数据帧（DI 默认正向有功总电能，且必须是虚拟表档案支持的）。

    注意 DI 也是**低字节在前**：书写序 00010000 → 线序 00 00 01 00 → +0x33 = 33 33 34 33。
    """
    di = pick_645_di(di or DI_TOTAL_ACTIVE_645)
    di_bytes = bytes.fromhex(di)[::-1]
    scrambled = bytes((b + 0x33) & 0xFF for b in di_bytes)
    body = b"\x11\x04" + scrambled          # 控制码 11H + 数据长度 04H + DI
    head = b"\x68" + _addr_bytes(addr) + b"\x68" + body
    cs = sum(head) & 0xFF
    return head + bytes([cs, 0x16])


def build_698_read_total_active(addr: str, oad: Optional[str] = None) -> bytes:
    """698.45 GET-Request-Normal（OAD 默认正向有功总电能，且必须是虚拟表档案支持的）。

    **必须带「时间标签 = 无」这个 00 字节**（用户现场口径）：
    不带时 APDU 少 1 字节、长度域 L 少 1，被测 CCO 会认为报文不完整而**不执行抄表**。

    帧结构（逐字节对齐现场实测报文，见下方示例）::

        68 17 00 43 05 <表地址6B> 00 C7 52 05 01 01 <OAD4B> 00 92 2E 16
        └68 └L=23  └C  └SA(含长度特征 05) └CA └HCS  └APDU(GET)      └TT └FCS └16

    两个校验的范围（照现场报文反推，和 `DLT69845FrameGenerator` 的默认口径不同）：
    - **HCS = CRC16(x-25)( L' + C + SA + CA )**，其中 **L' 是不含时间标签的长度**
      （现场设备就是这样算的：带 00 时间标签后 HCS 仍然是 L-1 时的值）；
    - **FCS = CRC16(x-25)( L + C + SA + CA + HCS + APDU )**，用的是**真实长度**。
    """
    from dl_t698_45_frame_gen import DLT69845FrameGenerator

    import crcmod.predefined
    import struct

    crc = crcmod.predefined.Crc('x-25')
    sa = bytes([0x05]) + _addr_bytes(addr)      # 0x05 = 单地址，长度 6
    ca = 0
    control = 0x43                              # DIR=0 PRM=1 SC=0 func=3（用户数据）
    oad = pick_698_oad(oad or OAD_TOTAL_ACTIVE_698)
    apdu = bytes([0x05, 0x01, 0x01]) + bytes.fromhex(oad) + b"\x00"   # 时间标签=无

    length = 2 + 1 + len(sa) + 1 + 2 + len(apdu) + 2
    # HCS 按「不含时间标签」的长度算（现场口径），FCS 用真实长度
    hcs_len = length - 1
    hcs = struct.pack('<H', crc.new(
        struct.pack('<H', hcs_len) + bytes([control]) + sa + bytes([ca])).crcValue)
    fcs = struct.pack('<H', crc.new(
        struct.pack('<H', length) + bytes([control]) + sa + bytes([ca])
        + hcs + apdu).crcValue)
    return (b"\x68" + struct.pack('<H', length) + bytes([control]) + sa
            + bytes([ca]) + hcs + apdu + fcs + b"\x16")


def msg_proto_for_node(node_proto: int) -> int:
    """组网参数的从节点协议 → 1376.2 报文里的「通信协议类型」。"""
    proto = int(node_proto or 0)
    if proto == NODE_PROTO_698:
        return MSG_PROTO_698
    if proto == NODE_PROTO_645_1997:
        return MSG_PROTO_645_1997
    return MSG_PROTO_645_2007


def read_request_for(node_proto: int, addr: str) -> bytes:
    """按从节点协议生成「读正向有功总电能」报文。"""
    if int(node_proto or 0) == NODE_PROTO_698:
        return build_698_read_total_active(addr)
    return build_645_read_total_active(addr)


def describe_request(frame: bytes) -> str:
    """给日志看的简述（645 / 698 各一句）。"""
    if not frame:
        return "（空报文）"
    if len(frame) >= 12 and frame[0] == 0x68 and frame[7] == 0x68 and frame[8] == 0x11:
        return f"645-2007 读正向有功总电能（{len(frame)}B）"
    if len(frame) >= 4 and frame[0] == 0x68 and frame[3] in (0x43, 0x83):
        return f"698.45 GET 正向有功总电能（{len(frame)}B）"
    return f"（未识别，{len(frame)}B）"


def apply_delay_correction(frame: bytes, delay_ms: int = 0) -> Tuple[bytes, str]:
    """按「预计延迟时间」修正抄读报文（14H F3 下行要放修正后的报文）。

    现实约束：645 读数据帧里没有时标字段；698 的 GET 请求是否带时标取决于原始报文，
    而各家对「依延时修正」的实现细节不同（现场示例里的 16 字节填充只是示意值）。
    所以这里**不做猜测性改写**，只做可解释的处理：

    - 报文原样回送（这是实测能让被测继续抄表的最小充分条件）；
    - 返回人话说明，日志里能直接看到「修正了什么 / 为什么没改」；
    - 若将来拿到厂家明确的时标修正规则，在 `_shift_timetag()` 里补实现即可。
    """
    data = bytes(frame or b"")
    if not data:
        return b"", "没有可修正的报文"
    if delay_ms <= 0:
        return data, "预计延迟时间为 0，原报文回送"
    if len(data) > 10 and data[0] == 0x68 and data[7] == 0x68:
        return data, f"645 读帧不含时标，原报文回送（预计延迟 {delay_ms} ms）"
    if len(data) > 4 and data[0] == 0x68:
        return data, (f"698 报文按其原始时标回送（预计延迟 {delay_ms} ms；"
                      "未做数值改写，避免改错报文导致被测抄表失败）")
    return data, f"报文结构未收录，原报文回送（预计延迟 {delay_ms} ms）"
