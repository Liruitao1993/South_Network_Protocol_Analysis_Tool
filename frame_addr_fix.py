# -*- coding: utf-8 -*-
"""按协议「替换地址域 + 重算校验」（纯逻辑，无 Qt / 无 GUI 依赖）。

用途：蓝牙页「自定义报文」按钮可以绑定协议与地址参数，发送前把帧内地址域换成现场表计的地址，
并按该协议**重算校验**（改地址后校验必然变化，否则对端直接丢帧）。

设计原则（见 `.trellis/tasks/archive/2026-10/10-13-bt-button-addr-checksum/design.md`）：

* **只复用各协议既有实现**，不另写第二份偏移/算法表：
  - 645 → `dlt645_frame_gen.DLT645FrameGenerator.build_frame`
  - 698.45 → `dl_t698_45_frame_gen.DLT69845FrameGenerator._assemble_frame`
  - 依瓦645 → `yw645_wire.encode_frame`（唯一整帧组帧实现）
  - 南网上行 → `csg_uplink_wire.encode_frame` + `resolve_layout`
  - 南网 / 国网 → 字节拼接 + 各自 `Frame.calculate_checksum` / `GDWFrame.calculate_checksum`
* **先自证再改**：原帧必须先通过「结构 + 校验」自证（`68…16`、长度域自洽、原校验正确），
  否则一律拒绝——避免把「本来就不是该协议的帧」洗成看似合法的帧。
* **地址长度必须与帧内一致**（改长度会连带改 L / HCS / FCS 布局，v1 明确不做）。
* 任何异常都转成可读 `error`，不抛给 GUI（按钮点下去必须有反应）。

支持协议（v1）：0 南网 / 6 DLT645 / 7 国网 / 8 698.45 / 13 依瓦645 / 14 南网上行。
其余协议（1/2/3/4/5/9/10/11/12）返回可读「暂不支持」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

import protocol_registry

# 各协议模块**按需导入**（延迟到真正处理该协议时）：
# `dl_t698_45_frame_gen` 依赖**可选**的 `crcmod`，模块级导入会让「没装 crcmod 的机器」
# 连蓝牙页都打不开；其余协议模块同理保持延迟导入，保证本模块可被无依赖地 import。

#: v1 支持的协议索引（其余返回可读错误）
SUPPORTED_PROTOCOLS: Tuple[int, ...] = (0, 6, 7, 8, 13, 14)

#: 国网福建增补（附件3）：信息域/地址域结构与 2024 国网不同（`gdw_send_frame_lib.py:62-69`）
_FUJIAN_AFNS = frozenset({0x50, 0x51, 0x52, 0x53, 0x55, 0x56})

#: 地址输入写法（决定「数字」分支怎么编码；含分隔符/0x 的输入一律按在线字节处理）
KIND_METER12 = "meter12"     # 12 位表号（书写序 hex），上线字节逆序（南网/国网）
KIND_DLT645 = "dlt645"       # 645 表地址：12 位书写序 hex（逆序）或 6 字节 hex
KIND_DIGITS = "digits"       # 依瓦：十进制数字表号（高字节在前）
KIND_TERMINAL = "terminal"   # 南网上行：终端地址十进制（A2，小端 3B）
KIND_SA698 = "sa698"         # 698 SA：书写序 hex（上线逆序），地址特征字节保留
KIND_CA698 = "ca698"         # 698 CA：1 字节


@dataclass(frozen=True)
class AddrField:
    """一个可由用户填写的地址字段。"""

    key: str        #: 配置键（button["addr"] 里的 key）
    label: str      #: 界面标签
    hint: str       #: 写法说明（含示例）
    kind: str       #: 编码方式（KIND_*）
    length: int = 0  #: 在线字节数（0 = 由帧决定，如 698 SA）


@dataclass
class FixResult:
    """`apply()` 的结果。"""

    ok: bool
    frame: bytes = b""
    notes: List[str] = field(default_factory=list)
    error: str = ""


# ── 字段声明（单一来源：界面与编码都读它）────────────────────────────────────

_FIELDS: Dict[int, Tuple[AddrField, ...]] = {
    0: (
        AddrField("src", "源地址", "12 位表号（书写序，如 000000000001）；或 6 字节 hex（如 01 00 00 00 00 00）",
                  KIND_METER12, 6),
        AddrField("dst", "目的地址", "12 位表号（书写序，如 000000000002）；或 6 字节 hex",
                  KIND_METER12, 6),
    ),
    6: (
        AddrField("addr", "表地址", "12 位表号（如 000000000033，低字节在前写入）；或 6 字节 hex",
                  KIND_DLT645, 6),
    ),
    7: (
        AddrField("src", "源地址", "12 位表号（书写序）；或 6 字节 hex", KIND_METER12, 6),
        AddrField("dst", "目的地址", "12 位表号（书写序）；或 6 字节 hex", KIND_METER12, 6),
    ),
    8: (
        AddrField("sa", "服务器地址 SA", "书写序 hex（如 0000000033，上线逆序）；长度须与帧内一致",
                  KIND_SA698, 0),
        AddrField("ca", "客户机地址 CA", "1 字节（十进制 0~255 或 hex，如 00）", KIND_CA698, 1),
    ),
    13: (
        AddrField("addr", "表地址", "12 位十进制表号（如 450000000013，高字节在前）", KIND_DIGITS, 6),
    ),
    14: (
        AddrField("a2", "终端地址", "十进制终端地址（如 1，小端 3B）；或 7 字节 hex（整段地址域）",
                  KIND_TERMINAL, 3),
    ),
}


def fields_for(protocol_index: int) -> Tuple[AddrField, ...]:
    """该协议需要用户填写的地址字段（不支持的协议返回空元组 ⇒ 界面隐藏地址区）。"""
    try:
        index = int(protocol_index)
    except (TypeError, ValueError):
        return ()
    return _FIELDS.get(index, ())


def is_supported(protocol_index: int) -> bool:
    return bool(fields_for(protocol_index))


# ── 地址文本 → 在线字节 ─────────────────────────────────────────────────────

_HEX_SEPARATORS = (" ", "\t", ":", "-", "_")


def _looks_on_wire_hex(text: str) -> bool:
    """是否按「在线字节顺序」解释：含分隔符 / 0x 前缀（用户明确在写字节）。"""
    return any(sep in text for sep in _HEX_SEPARATORS) or "0x" in text.lower()


def _hex_bytes(text: str) -> Optional[bytes]:
    s = text.strip().replace("0x", "").replace("0X", "")
    for sep in _HEX_SEPARATORS:
        s = s.replace(sep, "")
    if not s or len(s) % 2:
        return None
    try:
        return bytes.fromhex(s)
    except ValueError:
        return None


def parse_address(text: str, addr_field: AddrField, on_wire_length: int = 0) -> Tuple[bytes, str]:
    """地址文本 → **在线字节**；`(b"", 错误说明)` 表示失败。

    两种写法（用户口径）：

    * 含分隔符 / `0x`（如 `01 00 00 00 00 00`）→ 按**帧内在线顺序**原样写入；
    * 纯书写序（如 `000000000013`、依瓦的 `450000000013`）→ 按**该协议既有编码函数**编码。
    """
    raw = str(text or "").strip()
    if not raw:
        return b"", f"{addr_field.label}不能为空"
    length = int(on_wire_length or addr_field.length or 0)

    if _looks_on_wire_hex(raw):
        data = _hex_bytes(raw)
        if data is None:
            return b"", f"{addr_field.label}不是有效的 HEX：{raw!r}"
        if length and len(data) != length:
            return b"", f"{addr_field.label}应为 {length} 字节（当前 {len(data)} 字节）"
        return data, ""

    if addr_field.kind == KIND_DIGITS:                       # 依瓦：数字表号，高字节在前
        import yw645_wire                                     # 按需导入（见模块头说明）
        try:
            return yw645_wire.encode_addr12(raw), ""
        except ValueError as exc:
            return b"", f"{addr_field.label}：{exc}"

    if addr_field.kind == KIND_TERMINAL:                     # 南网上行：终端地址十进制 → A2
        digits = raw
        if not digits.isdigit():
            return b"", f"{addr_field.label}应为十进制数字（或 7 字节 hex）：{raw!r}"
        value = int(digits)
        if not 0 <= value <= 0xFFFFFF:
            return b"", f"{addr_field.label}越界（0~16777215）：{value}"
        return value.to_bytes(3, "little"), ""

    if addr_field.kind == KIND_CA698:                        # 698 CA：0~255
        if raw.isdigit():
            value = int(raw)
            if not 0 <= value <= 0xFF:
                return b"", f"{addr_field.label}越界（0~255）：{value}"
            return bytes([value]), ""
        data = _hex_bytes(raw)
        if data is None or len(data) != 1:
            return b"", f"{addr_field.label}应为 1 字节（十进制 0~255 或两位 hex）：{raw!r}"
        return data, ""

    # 645 / 南网 / 国网 / 698 SA：书写序 hex（无分隔符），上线字节逆序
    data = _hex_bytes(raw)
    if data is None:
        return b"", f"{addr_field.label}应为十六进制字符串（或用空格分隔的在线字节）：{raw!r}"
    if addr_field.kind == KIND_SA698:
        if not length:
            return b"", f"{addr_field.label}长度需由帧内决定（当前未能确定）"
        if len(data) > length:
            return b"", f"{addr_field.label}最多 {length} 字节（当前 {len(data)} 字节）"
        return data.rjust(length, b"\x00")[::-1], ""         # 书写序 → 右补零 → 逆序（同组帧页口径）
    if len(data) > length:
        return b"", f"{addr_field.label}最多 {length} 字节（当前 {len(data)} 字节）"
    return data.rjust(length, b"\x00")[::-1], ""              # 书写序 → 逆序（南网/国网/645）


# ── 自证（结构 + 原校验）────────────────────────────────────────────────────

def _check_sum8(frame: bytes, end: int, label: str) -> str:
    """8 位位组算术和自证（`end` = 校验字节下标）。"""
    calc = sum(frame[3:end]) & 0xFF
    if calc != frame[end]:
        return f"{label}原帧校验和不符（帧内 0x{frame[end]:02X}，按帧内容应为 0x{calc:02X}）"
    return ""


def _self_check_little_len(frame: bytes, label: str) -> str:
    """南网 / 国网：`68 L(2B 小端) C … CS 16`，L = 整帧字节数。"""
    if len(frame) < 8:
        return f"{label}帧太短（{len(frame)} 字节）"
    if frame[0] != 0x68 or frame[-1] != 0x16:
        return f"{label}帧头/帧尾不符（应为 68H … 16H）"
    declared = int.from_bytes(frame[1:3], "little")
    if declared != len(frame):
        return f"{label}长度域不符（声明 {declared}，实际 {len(frame)}）"
    return ""


# ── 各协议实现 ──────────────────────────────────────────────────────────────

def _apply_south(frame: bytes, values: Mapping[str, str]) -> FixResult:
    """南网（0）：`68 L L C [源6B+目的6B] 用户数据 CS 16`，地址仅当控制域 D5=1。"""
    import protocol_tool                                      # 按需导入（见模块头说明）
    err = _self_check_little_len(frame, "南网")
    if err:
        return FixResult(False, error=err)
    if not frame[3] & 0x20:
        return FixResult(False, error="该帧不含地址域（控制域 D5 地址域标识 = 0）")
    err = _check_sum8(frame, len(frame) - 2, "南网")
    if err:
        return FixResult(False, error=err)

    fields = {f.key: f for f in fields_for(0)}
    notes: List[str] = []
    new = bytearray(frame)
    for key, offset in (("src", 4), ("dst", 10)):
        text = values.get(key)
        if text is None or not str(text).strip():
            continue
        data, err = parse_address(str(text), fields[key], 6)
        if err:
            return FixResult(False, error=err)
        new[offset:offset + 6] = data
        notes.append(f"地址域 {fields[key].label} {frame[offset:offset + 6].hex(' ')} → {data.hex(' ')}")
    if not notes:
        return FixResult(False, error="未填写任何地址（源地址 / 目的地址至少填一个）")

    cs_old = new[-2]
    cs_new = protocol_tool.Frame().calculate_checksum(bytes(new[3:-2]))
    new[-2] = cs_new
    notes.append(f"校验和 0x{cs_old:02X} → 0x{cs_new:02X}")
    return FixResult(True, frame=bytes(new), notes=notes)


def _apply_gdw(frame: bytes, values: Mapping[str, str]) -> FixResult:
    """国网（7）：`68 L L C 信息域6B [地址域] AFN … CS 16`；地址域存在 ⟺ 信息域 byte0 bit2=1。"""
    import gdw10376_tool                                      # 按需导入（见模块头说明）
    err = _self_check_little_len(frame, "国网")
    if err:
        return FixResult(False, error=err)
    info0 = frame[4]
    if not info0 & 0x04:
        return FixResult(False, error="该帧不含地址域（信息域「通信模块标识」= 0）")
    level = (info0 >> 4) & 0x0F
    addr_len = 12 + 6 * level
    addr_start = 10
    addr_end = addr_start + addr_len
    if addr_end + 3 > len(frame):
        return FixResult(False, error="地址域越界（中继级别与帧长不符）")
    afn = frame[addr_end]
    if afn in _FUJIAN_AFNS:
        return FixResult(False, error=f"该帧是福建增补规约（AFN=0x{afn:02X}），地址域布局不同，v1 不支持")
    err = _check_sum8(frame, len(frame) - 2, "国网")
    if err:
        return FixResult(False, error=err)

    fields = {f.key: f for f in fields_for(7)}
    notes: List[str] = []
    new = bytearray(frame)
    targets = (("src", addr_start), ("dst", addr_end - 6))
    for key, offset in targets:
        text = values.get(key)
        if text is None or not str(text).strip():
            continue
        data, err = parse_address(str(text), fields[key], 6)
        if err:
            return FixResult(False, error=err)
        new[offset:offset + 6] = data
        notes.append(f"地址域 {fields[key].label} {frame[offset:offset + 6].hex(' ')} → {data.hex(' ')}")
    if not notes:
        return FixResult(False, error="未填写任何地址（源地址 / 目的地址至少填一个）")

    cs_old = new[-2]
    cs_new = gdw10376_tool.GDWFrame().calculate_checksum(bytes(new[3:-2]))
    new[-2] = cs_new
    notes.append(f"校验和 0x{cs_old:02X} → 0x{cs_new:02X}")
    return FixResult(True, frame=bytes(new), notes=notes)


def _apply_dlt645(frame: bytes, values: Mapping[str, str]) -> FixResult:
    """645（6）：`68 A6 68 C L DATA(+0x33) CS 16`，整帧重建走组帧器（CS 单一来源）。"""
    import dlt645_frame_gen                                   # 按需导入（见模块头说明）
    if len(frame) < 12 or frame[0] != 0x68 or frame[7] != 0x68 or frame[-1] != 0x16:
        return FixResult(False, error="DLT645 帧结构不符（应为 68H+6 字节地址+68H … 16H）")
    if len(frame) != 12 + frame[9]:
        return FixResult(False, error=f"DLT645 长度域不符（声明 {frame[9]}，实际数据域 {len(frame) - 12}）")
    if (sum(frame[:-2]) & 0xFF) != frame[-2]:
        calc = sum(frame[:-2]) & 0xFF
        return FixResult(False, error=f"DLT645 原帧校验和不符（帧内 0x{frame[-2]:02X}，应为 0x{calc:02X}）")

    addr_field = fields_for(6)[0]
    text = str(values.get("addr") or "").strip()
    if not text:
        return FixResult(False, error="未填写表地址")
    data, err = parse_address(text, addr_field, 6)
    if err:
        return FixResult(False, error=err)

    notes: List[str] = []
    if data != frame[1:7]:
        notes.append(f"地址域 表地址 {frame[1:7].hex(' ')} → {data.hex(' ')}")
    try:
        rebuilt = dlt645_frame_gen.DLT645FrameGenerator().build_frame(
            data, ctrl=frame[8], data=frame[10:-2], scramble=False)
    except ValueError as exc:
        return FixResult(False, error=f"DLT645 组帧失败：{exc}")
    notes.append(f"校验和 0x{frame[-2]:02X} → 0x{rebuilt[-2]:02X}")
    return FixResult(True, frame=bytes(rebuilt), notes=notes)


def _apply_69845(frame: bytes, values: Mapping[str, str]) -> FixResult:
    """698.45（8）：`68 L(2) C 地址特征 SA CA HCS(2) APDU FCS(2) 16`，整帧重建走组帧器。"""
    import dl_t698_45_frame_gen                               # 按需导入（依赖可选 crcmod）
    if len(frame) < 12 or frame[0] != 0x68 or frame[-1] != 0x16:
        return FixResult(False, error="698.45 帧结构不符（应为 68H … 16H）")
    declared = frame[1] | (frame[2] << 8)
    if declared != len(frame) - 2:
        return FixResult(False, error=f"698.45 长度域不符（声明 {declared}，实际 {len(frame) - 2}）")
    sa_total = 2 + (frame[4] & 0x0F)          # 地址特征字节(1B) + SA 本体(1 + 低 4 位)
    ca_offset = 4 + sa_total
    apdu_start = ca_offset + 3                # +CA(1) +HCS(2)
    if apdu_start > len(frame) - 3:
        return FixResult(False, error="698.45 地址域/长度域自相矛盾")
    sa_old = frame[4:ca_offset]
    ca_old = frame[ca_offset]
    control = frame[3]
    apdu = frame[apdu_start:-3]

    # 原帧 HCS/FCS 自证（用同一组帧器重算比对）
    gen = dl_t698_45_frame_gen.DLT69845FrameGenerator()
    if bytes(gen._assemble_frame(sa_old, ca_old, control, apdu)) != bytes(frame):
        return FixResult(False, error="698.45 原帧 HCS/FCS 不符（不是本标准形态的帧）")

    fields = {f.key: f for f in fields_for(8)}
    notes: List[str] = []
    sa_new = sa_old
    ca_new = ca_old
    text = values.get("sa")
    if text is not None and str(text).strip():
        body, err = parse_address(str(text), fields["sa"], sa_total - 1)
        if err:
            return FixResult(False, error=err)
        sa_new = bytes([sa_old[0]]) + body        # 地址特征字节（类型/长度）保留
        notes.append(f"地址域 SA {sa_old[1:].hex(' ')} → {body.hex(' ')}")
    text = values.get("ca")
    if text is not None and str(text).strip():
        data, err = parse_address(str(text), fields["ca"], 1)
        if err:
            return FixResult(False, error=err)
        ca_new = data[0]
        notes.append(f"地址域 CA 0x{ca_old:02X} → 0x{ca_new:02X}")
    if not notes:
        return FixResult(False, error="未填写任何地址（SA / CA 至少填一个）")

    rebuilt = bytes(gen._assemble_frame(sa_new, ca_new, control, apdu))
    notes.append(f"帧头校验HCS {frame[ca_offset + 1:ca_offset + 3].hex(' ')} → {rebuilt[ca_offset + 1:ca_offset + 3].hex(' ')}")
    notes.append(f"帧校验FCS {frame[-3:-1].hex(' ')} → {rebuilt[-3:-1].hex(' ')}")
    return FixResult(True, frame=rebuilt, notes=notes)


def _apply_yw645(frame: bytes, values: Mapping[str, str]) -> FixResult:
    """依瓦定制645（13）：`68 A6 68 COMMAND L DATA(+0x33) CS 16`，重建走 `yw645_wire`。"""
    import yw645_wire                                         # 按需导入（见模块头说明）
    if len(frame) < 12 or frame[0] != 0x68 or frame[7] != 0x68 or frame[-1] != 0x16:
        return FixResult(False, error="依瓦645 帧结构不符（应为 68H+6 字节地址+68H … 16H）")
    dlen = ((frame[8] & 0x0F) << 8) | frame[9]
    if len(frame) != dlen + yw645_wire.HEADER_LEN + yw645_wire.TRAILER_LEN:
        return FixResult(False, error=f"依瓦645 长度域不符（声明 {dlen}，实际 {len(frame)}）")
    if (sum(frame[:-2]) & 0xFF) != frame[-2]:
        calc = sum(frame[:-2]) & 0xFF
        return FixResult(False, error=f"依瓦645 原帧校验和不符（帧内 0x{frame[-2]:02X}，应为 0x{calc:02X}）")

    addr_field = fields_for(13)[0]
    text = str(values.get("addr") or "").strip()
    if not text:
        return FixResult(False, error="未填写表地址")
    data, err = parse_address(text, addr_field, 6)
    if err:
        return FixResult(False, error=err)
    notes: List[str] = []
    if data != frame[1:7]:
        notes.append(f"地址域 表地址 {frame[1:7].hex(' ')} → {data.hex(' ')}")
    unmasked = yw645_wire.unmask_data(frame[10:-2])
    try:
        rebuilt = yw645_wire.encode_frame(data, frame[8] & 0xF0, unmasked)
    except ValueError as exc:
        return FixResult(False, error=f"依瓦645 组帧失败：{exc}")
    if bytes(rebuilt[8:10]) != bytes(frame[8:10]):
        # 长度域由组帧器按数据长度反推，等长替换下必须一致
        return FixResult(False, error="依瓦645 长度域与重建结果不一致（数据域长度异常）")
    notes.append(f"校验和 0x{frame[-2]:02X} → 0x{rebuilt[-2]:02X}")
    return FixResult(True, frame=bytes(rebuilt), notes=notes)


def _apply_csg_uplink(frame: bytes, values: Mapping[str, str]) -> FixResult:
    """南网上行（14）：`68 L L 68 C A(7B) 用户数据 CS 16`，重建走 `csg_uplink_wire.encode_frame`。"""
    import csg_uplink_wire                                    # 按需导入（见模块头说明）
    layout = csg_uplink_wire.resolve_layout(frame)
    if layout is None:
        return FixResult(False, error="南网上行帧结构不符（三种长度域形态均不自洽）")
    if not csg_uplink_wire.check_cs(frame, layout):
        return FixResult(False, error="南网上行原帧 CS 不符（按规范 5.1.5 计算不一致）")
    addr_start, addr_end = layout.addr_index, layout.addr_index + csg_uplink_wire.ADDR_LEN
    if addr_end + 2 > len(frame):
        return FixResult(False, error="南网上行地址域越界")
    apdu = frame[addr_end:-2]
    old_addr = csg_uplink_wire.parse_addr(frame[addr_start:addr_end])

    addr_field = fields_for(14)[0]
    text = str(values.get("a2") or "").strip()
    if not text:
        return FixResult(False, error="未填写终端地址")
    if _looks_on_wire_hex(text):
        data, err = parse_address(text, addr_field, 7)
        if err:
            return FixResult(False, error=err)
        new_addr = data
        notes = [f"地址域 终端地址 {frame[addr_start:addr_end].hex(' ')} → {new_addr.hex(' ')}"]
    else:
        data, err = parse_address(text, addr_field, 3)
        if err:
            return FixResult(False, error=err)
        new_addr = csg_uplink_wire.encode_addr(old_addr.a1, int.from_bytes(data, "little"), old_addr.a3)
        notes = [f"地址域 终端地址 {old_addr.a2} → {int.from_bytes(data, 'little')}"
                 f"（{frame[addr_start:addr_end].hex(' ')} → {new_addr.hex(' ')}）"]

    try:
        rebuilt = csg_uplink_wire.encode_frame(frame[layout.c_index], new_addr, apdu, layout.form)
    except ValueError as exc:
        return FixResult(False, error=f"南网上行组帧失败：{exc}")
    notes.append(f"校验和 0x{frame[-2]:02X} → 0x{rebuilt[-2]:02X}")
    return FixResult(True, frame=bytes(rebuilt), notes=notes)


_APPLIERS = {
    0: _apply_south,
    6: _apply_dlt645,
    7: _apply_gdw,
    8: _apply_69845,
    13: _apply_yw645,
    14: _apply_csg_uplink,
}


def apply(frame: bytes, protocol_index: int, values: Mapping[str, str]) -> FixResult:
    """按协议替换地址并重算校验（失败时 `frame` 为空、`error` 可读）。"""
    try:
        index = int(protocol_index)
    except (TypeError, ValueError):
        return FixResult(False, error="未选择协议")
    applier = _APPLIERS.get(index)
    if applier is None:
        names = "、".join(str(i) for i in SUPPORTED_PROTOCOLS)
        return FixResult(False, error=f"该协议暂不支持地址替换（v1 支持协议 {names}）")
    data = bytes(frame or b"")
    if not data:
        return FixResult(False, error="报文内容为空")
    try:
        return applier(data, dict(values or {}))
    except Exception as exc:                                   # noqa: BLE001 - 兜底成可读错误
        return FixResult(False, error=f"地址替换失败：{type(exc).__name__}: {exc}")


def protocol_label(protocol_index: int) -> str:
    """协议短名（界面显示用；不支持的索引回落空串）。"""
    try:
        return protocol_registry.get_protocol(int(protocol_index)).short_name
    except Exception:                                          # noqa: BLE001 - 索引越界
        return ""


def supported_choices() -> List[Tuple[str, int]]:
    """界面下拉用：``[(显示名, 协议索引), …]``（顺序与 `SUPPORTED_PROTOCOLS` 一致）。"""
    out: List[Tuple[str, int]] = []
    for index in SUPPORTED_PROTOCOLS:
        spec = protocol_registry.get_protocol(index)
        out.append((f"[{index}] {spec.short_name}", index))
    return out


__all__ = [
    "AddrField",
    "FixResult",
    "SUPPORTED_PROTOCOLS",
    "apply",
    "fields_for",
    "is_supported",
    "parse_address",
    "protocol_label",
    "supported_choices",
]
