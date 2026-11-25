# -*- coding: utf-8 -*-
"""SPLC 收发机控制页 —— 纯逻辑层（无 Qt）。

**两套协议、两个方向，别混用（这是 1.26.27 纠正过的错误）**：

1. **发射机下行 = PLC2.0（ED..EE）**，依据
   ``南网新一代20260226校对/PLC2.0收发机报文格式0629.docx``：:

       EDH + 帧长(2, LE) + 控制域1 + 控制域2 + EFH + 数据域 + CS + EEH

   - 帧长 = 控制域1+控制域2+EF+数据域+CS 的字节数（= 数据域长度 + 4），小端；
   - 控制域1：0x00 数据报文 / 0x01 控制报文；
   - 数据报文控制域2：0x01 FC / 0x02 FC+Payload / 0x03 Payload /
     0x06 RF+HPLC 同时发 / 0x07 OFDMA 四用户 / 0x08 UL-OFDMA；
   - 控制报文是设备配置与状态指令（复位、频段、相线、物理信道、同步、
     Tonemask、NTB 采集、bitloading…，见 :data:`TX_COMMANDS`）；
   - 多字节一律**小端**。

2. **监控器（接收机）上行 = 96..16**，依据
   ``SPLC双模监控器_发射机_接口协议20260725(1).docx``：:

       96H + RSSI(1) + NTB(4, LE) + [LEN(12b,LE)+协议类型(3b)+CHANNEL(1b)](2)
           + DATA(LEN) + CS(1) + 16H

   监控器把收到的载波业务帧上报给 PC；协议类型=4（南网 SPLC）时 DATA 前面还有
   「帧类型 + 数据头」（见 :func:`split_splc_header`）。

3. **监控器（接收机）配置 = 68..16**，同一份接口协议文档：::

       68H + 保留(6B) + 68H + 标识 + [读写标志(1B，仅下行)] + 数据 + CS + 16H

   用于查询版本/频段/无线/工作模式、设置频段/无线/功率/SNID/工作模式。
   **命令帧不带长度域**，解帧只能靠「CS 校验通过的第一个 16H」定界
   （见 :func:`_find_command_frame_end`）。

三者帧头互不相同（EDH / 96H / 68H），:func:`deframe_stream` 按帧头自动分流。

另外提供「用例文件」（JSON）的读写与校验：一个用例 = 一套公共参数 + 一串有序步骤，
每个步骤可以是一条发射机数据报文、一条发射机控制报文、一条监控器命令、一段等待
或一条透传报文。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import app_paths

# ======================================================================
# 常量
# ======================================================================

FRAME_HEAD_DATA = 0x96      # 业务数据帧帧头（收发载波报文）
FRAME_HEAD_CMD = 0x68       # 命令帧帧头
FRAME_TAIL = 0x16

#: 协议类型（LEN 域高 3 bit）
PROTO_TYPE_NAMES = {
    0: "国网HPLC",
    1: "南网宽带",
    2: "IEEE1901",
    3: "国网HPLC双模块",
    4: "南网SPLC双模",
}
PROTO_TYPE_SPLC = 4

#: CHANNEL 位
CHANNEL_NAMES = {0: "HPLC", 1: "RF"}

#: 协议类型=4（南网 SPLC）时 DATA 域的帧类型
SPLC_FRAME_TYPE_NAMES = {0: "信标帧", 1: "SOF帧", 2: "ACK帧(外扩)", 3: "网间协调"}

#: SPLC SOF 帧「帧类型1」
SPLC_SOF_KIND_NAMES = {1: "MIMO", 2: "bitloading", 3: "OFDMA"}

#: 载波频段（01/11、02/12）
BAND_NAMES = {0: "10M", 1: "3M", 2: "2.2M", 3: "1.2M"}

#: 无线模式（04/14、05/15）
WIRELESS_MODE_NAMES = {1: "Option1 1MHz", 2: "Option2 500kHz", 3: "Option2 200kHz"}

#: 工作模式（07/17、08/18）
WORK_MODE_NAMES = {0: "监控器模式", 1: "发射机模式"}

#: 通信协议（07/17、08/18 的第 2 字节）
COMM_PROTO_NAMES = {
    0: "国网HPLC",
    1: "南网宽带",
    2: "IEEE1901",
    3: "国网HPLC双模块",
    4: "南网SPLC双模",
}

#: 命令帧最大合理长度（防伪帧头把缓冲区拖死）
MAX_CMD_FRAME_LEN = 512
#: 业务数据帧 DATA 上限（LEN 只有 12 bit）
MAX_DATA_LEN = 0xFFF


# ======================================================================
# 字节工具
# ======================================================================

def hex_to_bytes(text: str) -> bytes:
    """把用户输入的 HEX 文本转字节；容忍空格/逗号/换行/0x 前缀；非法抛 ValueError。"""
    if isinstance(text, (bytes, bytearray)):
        return bytes(text)
    raw = str(text or "")
    raw = re.sub(r"0[xX]", " ", raw)
    raw = re.sub(r"[\s,;:_\-]+", "", raw)
    if not raw:
        return b""
    if len(raw) % 2:
        raise ValueError(f"HEX 长度为奇数（{len(raw)} 个字符），无法按字节切分")
    # 用 fromhex 的合法字符集做严格校验：只吃 0-9A-Fa-f
    if re.search(r"[^0-9A-Fa-f]", raw):
        bad = re.search(r"[^0-9A-Fa-f]", raw)
        raise ValueError(f"包含非 HEX 字符 {bad.group(0)!r}（第 {bad.start() + 1} 个字符）")
    return bytes.fromhex(raw)


def bytes_to_hex(data: bytes, upper: bool = True) -> str:
    """字节 → 空格分隔 HEX。"""
    text = bytes(data).hex()
    if upper:
        text = text.upper()
    return " ".join(text[i:i + 2] for i in range(0, len(text), 2))


def checksum(data: Sequence[int]) -> int:
    """累加和校验：参与字节求和取低 8 位（文档口径「CS 之前到帧头」）。"""
    return sum(data) & 0xFF


def _u12_le(value: int) -> int:
    return value & 0xFF


# ======================================================================
# 一、业务数据帧（96..16）
# ======================================================================

def build_data_frame(data: bytes, channel: int = 0,
                     proto_type: int = PROTO_TYPE_SPLC) -> bytes:
    """组一帧下行业务数据帧（96..16）。

    :param data: 业务帧内容（对协议9 来说通常是 MPDU：FC + 可选 eFC + 载荷）
    :param channel: 0=HPLC 1=RF
    :param proto_type: 0~7，南网 SPLC 双模为 4
    """
    payload = bytes(data)
    if len(payload) > MAX_DATA_LEN:
        raise ValueError(f"业务帧过长（{len(payload)} > {MAX_DATA_LEN} 字节）")
    if proto_type not in PROTO_TYPE_NAMES:
        raise ValueError(f"协议类型超出 3 bit 范围：{proto_type}")
    if channel not in CHANNEL_NAMES:
        raise ValueError(f"信道只能取 0(HPLC) 或 1(RF)：{channel}")

    low = _u12_le(len(payload))
    high = ((proto_type & 0x07) << 4) | ((channel & 0x01) << 7) | ((len(payload) >> 8) & 0x0F)
    body = bytearray([FRAME_HEAD_DATA, 0x00, 0x00, 0x00, 0x00, 0x00, low, high])
    body.extend(payload)
    body.append(checksum(body))
    body.append(FRAME_TAIL)
    return bytes(body)


def parse_data_frame(frame: bytes) -> Dict[str, object]:
    """解析一帧业务数据帧（上/下行通用）。

    返回 dict（键含 ``ok``/``error``/``data``/``data_len``/``proto_type``/``channel``），
    并区分上行（RSSI/NTB 有值）与下行（第 2 字节与第 3~6 字节为保留）。
    """
    frame = bytes(frame)
    info: Dict[str, object] = {"ok": False, "error": "", "frame": frame}
    if len(frame) < 10:
        info["error"] = f"长度不足（{len(frame)} < 10 字节）"
        return info
    if frame[0] != FRAME_HEAD_DATA:
        info["error"] = f"帧头不是 96H（实际 {frame[0]:02X}H）"
        return info
    if frame[-1] != FRAME_TAIL:
        info["error"] = f"帧尾不是 16H（实际 {frame[-1]:02X}H）"
        return info

    low = frame[6]
    high = frame[7]
    length = low | ((high & 0x0F) << 8)
    total = 8 + length + 2
    if total != len(frame):
        info["error"] = (f"LEN 域声明 {length} 字节，整帧应为 {total} 字节，"
                         f"实际 {len(frame)} 字节")
        return info

    data = frame[8:8 + length]
    cs = frame[8 + length]
    calc = checksum(frame[:8 + length])
    info.update({
        "ok": calc == cs,
        "error": "" if calc == cs else f"CS 校验失败（收到 {cs:02X}H，计算 {calc:02X}H）",
        "rssi": frame[1],
        "ntb": int.from_bytes(frame[2:6], "little"),
        "len": length,
        "data_len": length,
        "proto_type": (high >> 4) & 0x07,
        "channel": (high >> 7) & 0x01,
        "cs": cs,
        "cs_calc": calc,
        "data": data,
    })
    info["proto_name"] = PROTO_TYPE_NAMES.get(info["proto_type"], "保留")
    info["channel_name"] = CHANNEL_NAMES.get(info["channel"], "?")
    return info


# ======================================================================
# 二、命令帧（68..16）
# ======================================================================

def build_command_frame(cmd_id: int, rw: int = 0, data: bytes = b"") -> bytes:
    """组一帧 PC 下行命令帧。

    :param cmd_id: 命令号（0x01~0x0A，见 :data:`COMMANDS`）
    :param rw: 0=查询 1=设置（**下行固定带这一字节**）
    :param data: 设置值 / 查询无数据
    """
    cmd_id = int(cmd_id) & 0x0F
    body = bytearray([FRAME_HEAD_CMD])
    body.extend(b"\x00" * 6)
    body.append(FRAME_HEAD_CMD)
    body.append(cmd_id)
    body.append(1 if rw else 0)
    body.extend(bytes(data))
    body.append(checksum(body))
    body.append(FRAME_TAIL)
    return bytes(body)


def build_command_response(cmd_id: int, data: bytes = b"") -> bytes:
    """组一帧**应答**命令帧（标识高 4 位=1，没有读写标志字节）。

    现场联调/单元测试要造「设备回包」时用它；正常运行时不需要。
    """
    cmd_id = int(cmd_id) & 0x0F
    body = bytearray([FRAME_HEAD_CMD])
    body.extend(b"\x00" * 6)
    body.append(FRAME_HEAD_CMD)
    body.append(0x10 | cmd_id)
    body.extend(bytes(data))
    body.append(checksum(body))
    body.append(FRAME_TAIL)
    return bytes(body)



def parse_command_frame(frame: bytes) -> Dict[str, object]:
    """解析一帧命令帧（下行 / 应答通用）。

    应答帧（标识高 4 位 = 1）没有读写标志字节；这里按高 4 位自动区分，
    并把数据域交给 :data:`COMMANDS` 里对应的字段解释器展开（失败只降级，不抛）。
    """
    frame = bytes(frame)
    info: Dict[str, object] = {"ok": False, "error": "", "frame": frame}
    if len(frame) < 11:
        info["error"] = f"长度不足（{len(frame)} < 11 字节）"
        return info
    if frame[0] != FRAME_HEAD_CMD or frame[7] != FRAME_HEAD_CMD:
        info["error"] = "帧头不是 68H…68H（保留 6 字节后应再现 68H）"
        return info
    if frame[-1] != FRAME_TAIL:
        info["error"] = f"帧尾不是 16H（实际 {frame[-1]:02X}H）"
        return info

    cs = frame[-2]
    calc = checksum(frame[:-2])
    ident = frame[8]
    is_response = bool(ident & 0xF0)
    cmd_id = ident & 0x0F

    if is_response:
        rw = None
        data = frame[9:-2]
    else:
        if len(frame) < 12:
            info["error"] = "下行命令帧长度不足（缺读写标志）"
            return info
        rw = frame[9]
        data = frame[10:-2]

    info.update({
        "ok": calc == cs,
        "error": "" if calc == cs else f"CS 校验失败（收到 {cs:02X}H，计算 {calc:02X}H）",
        "ident": ident,
        "direction": "response" if is_response else "down",
        "cmd_id": cmd_id,
        "rw": rw,
        "data": data,
        "cs": cs,
        "cs_calc": calc,
    })
    cmd = COMMANDS.get(cmd_id)
    info["cmd_name"] = cmd.name if cmd else f"未知命令(0x{cmd_id:02X})"
    fields, note = decode_command_payload(cmd_id, data, is_response)
    info["fields"] = fields
    info["payload_note"] = note
    return info


# ----------------------------------------------------------------------
# 命令表
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class CommandDef:
    """一条查询/设置命令的元数据。"""

    cmd_id: int
    name: str
    #: 设置命令需要的数据域长度（查询命令为 0）
    set_len: int = 0
    #: 应答数据域长度（None = 变长/未知）
    resp_len: Optional[int] = None
    #: 设置值字段名（与 ``set_len`` 一一对应）
    set_fields: Tuple[str, ...] = ()
    #: 应答字段名（与 ``resp_len`` 一一对应）
    resp_fields: Tuple[str, ...] = ()
    #: 是否支持设置（rw=1）；False 表示只读
    settable: bool = True
    note: str = ""


COMMANDS: Dict[int, CommandDef] = {
    0x01: CommandDef(
        0x01, "设置载波频段", set_len=1, resp_len=1,
        set_fields=("载波频段",), resp_fields=("设置后当前频段",),
        note="0-10M 1-3M 2-2.2M 3-1.2M",
    ),
    0x02: CommandDef(
        0x02, "查询载波频段", settable=False, resp_len=3,
        resp_fields=("MCU频段", "PHY频段", "DSP频段"),
        note="0-10M 1-3M 2-2.2M 3-1.2M",
    ),
    0x03: CommandDef(
        0x03, "查询版本", settable=False, resp_len=7,
        resp_fields=("DSP版本", "监控器版本", "版本日期"),
        note="DSP/监控器版本各 2 字节 AA.BB，日期 3 字节 年-月-日",
    ),
    0x04: CommandDef(
        0x04, "查询无线模式和频点", settable=False, resp_len=3,
        resp_fields=("无线模式", "频点号", "发送PHR的MCS"),
        note="无线模式 1-Option1 2-Option2(500k) 3-Option2(200k)",
    ),
    0x05: CommandDef(
        0x05, "设置无线模式和频点", set_len=3, resp_len=3,
        set_fields=("无线模式", "频点号", "发送PHR的MCS"),
        resp_fields=("无线模式", "频点号", "发送PHR的MCS"),
        note="发送PHR的MCS 只对发射机有效",
    ),
    0x06: CommandDef(
        0x06, "设置监控器载波同步SNID", set_len=4, resp_len=4,
        set_fields=("SNID",), resp_fields=("SNID",),
        note="只对监控器模式有效；0=不限同步 SNID",
    ),
    0x07: CommandDef(
        0x07, "设置工作模式及协议", set_len=2, resp_len=2,
        set_fields=("工作模式", "通信协议"), resp_fields=("工作模式", "通信协议"),
        note="0-监控器 1-发射机；协议 0-国网HPLC 1-南网宽带 2-IEEE1901 3-国网HPLC双模块 4-南网SPLC双模",
    ),
    0x08: CommandDef(
        0x08, "查询工作模式及协议", settable=False, resp_len=2,
        resp_fields=("工作模式", "通信协议"),
        note="发射机模式不接收数据，监控器模式不支持数据发送",
    ),
    0x09: CommandDef(
        0x09, "设置发射功率", set_len=3, resp_len=3,
        set_fields=("无线发射功率", "载波DSP", "载波3450"),
        resp_fields=("无线发射功率", "载波DSP", "载波3450"),
        note="无线功率 S8(-16~16dBm)；载波幅度倍率 = 值/32（8~32），32=不调整",
    ),
    0x0A: CommandDef(
        0x0A, "查询发射功率", settable=False, resp_len=3,
        resp_fields=("无线发射功率", "载波DSP", "载波3450"),
        note="无线功率 S8(-16~16dBm)；载波幅度倍率 = 值/32",
    ),
}

#: 「设置」与「查询」成对时，设置命令号 +1 = 查询命令号（01/02、09/0A 例外，见下）
#: —— 文档里查询命令号并不统一（02 查频段、08 查模式、0A 查功率），
#: 因此**不按公式推算**，一律查表 :data:`COMMANDS`。
QUERY_OF_SET = {0x01: 0x02, 0x05: 0x04, 0x07: 0x08, 0x09: 0x0A}


@dataclass(frozen=True)
class FieldSpec:
    """设置命令里一个数据字段的输入规格（页面据此生成下拉框/数字框）。"""

    name: str
    kind: str = "u8"                 # u8 | s8 | u32le
    minimum: int = 0
    maximum: int = 255
    choices: Optional[Dict[int, str]] = None
    suffix: str = ""
    help: str = ""


#: 设置命令的字段规格（顺序 = 数据域字节顺序）。
#: 页面用结构化控件填这些字段，**不靠用户手写 HEX**，避免「10 4」被当成 0x10 0x04 这类歧义。
COMMAND_FIELD_SPECS: Dict[int, Tuple[FieldSpec, ...]] = {
    0x01: (
        FieldSpec("载波频段", "u8", 0, 3, BAND_NAMES,
                  help="切换频段后设备需要重新同步"),
    ),
    0x05: (
        FieldSpec("无线模式", "u8", 1, 3, WIRELESS_MODE_NAMES),
        FieldSpec("频点号", "u8", 0, 255),
        FieldSpec("发送PHR的MCS", "u8", 0, 6, help="只对发射机有效"),
    ),
    0x06: (
        FieldSpec("SNID", "u32le", 0, 0xFFFFFFFF, help="0 = 不限制同步 SNID"),
    ),
    0x07: (
        FieldSpec("工作模式", "u8", 0, 1, WORK_MODE_NAMES),
        FieldSpec("通信协议", "u8", 0, 4, COMM_PROTO_NAMES,
                  help="南网 SPLC 双模 = 4"),
    ),
    0x09: (
        # 范围取满 S8 而不是文档建议的 -16~16 dBm：现场固件可能回/收 0x14(20dBm) 这类值，
        # 按建议区间夹紧会**静默改掉线上字节**（打开→另存就把 20dBm 变成 16dBm）。
        FieldSpec("无线发射功率", "s8", -128, 127, suffix=" dBm",
                  help="协议建议 -16~16 dBm；超出范围按原值保留，仅 S8 范围受限"),
        FieldSpec("载波DSP", "u8", 8, 32, help="幅度倍率 = 值/32（32 = 不调整）"),
        FieldSpec("载波3450", "u8", 8, 13, help="08H ~ 0DH"),
    ),
}


def command_field_specs(cmd_id: int) -> Tuple[FieldSpec, ...]:
    """取某条设置命令的字段规格；只读命令返回空元组。"""
    return COMMAND_FIELD_SPECS.get(int(cmd_id), ())


def command_field_count(cmd_id: int) -> int:
    """数据域字节数（u32le 占 4 字节）。"""
    total = 0
    for spec in command_field_specs(cmd_id):
        total += 4 if spec.kind == "u32le" else 1
    return total


def command_payload_from_values(cmd_id: int, values: Sequence[int]) -> "CommandPayload":
    """结构化字段值 → 命令数据域（长度/范围都校验）。"""
    specs = command_field_specs(cmd_id)
    if not specs:
        return CommandPayload(True, b"", "")
    if len(values) != len(specs):
        return CommandPayload(False, b"", f"需要 {len(specs)} 个字段，实际 {len(values)} 个")
    payload = bytearray()
    for spec, value in zip(specs, values):
        try:
            number = int(value)
        except (TypeError, ValueError):
            return CommandPayload(False, b"", f"{spec.name} 不是整数：{value!r}")
        if not spec.minimum <= number <= spec.maximum:
            return CommandPayload(
                False, b"", f"{spec.name} 超出范围（{number} 不在 {spec.minimum}~{spec.maximum}）")
        if spec.kind == "u32le":
            payload.extend(int(number).to_bytes(4, "little"))
        else:
            payload.append(number & 0xFF)
    return CommandPayload(True, bytes(payload), "")


def command_values_from_payload(cmd_id: int, payload: bytes) -> List[int]:
    """命令数据域 → 结构化字段值（长度不符时尽力取，供界面回填）。"""
    specs = command_field_specs(cmd_id)
    values: List[int] = []
    offset = 0
    data = bytes(payload)
    for spec in specs:
        if spec.kind == "u32le":
            chunk = data[offset:offset + 4]
            values.append(int.from_bytes(chunk, "little") if len(chunk) == 4 else 0)
            offset += 4
        else:
            if offset >= len(data):
                values.append(0)
            else:
                byte = data[offset]
                if spec.kind == "s8" and byte > 127:
                    byte -= 256
                values.append(byte)
            offset += 1
    return values


def decode_command_payload(cmd_id: int, data: bytes,
                           is_response: bool) -> Tuple[List[Tuple[str, str, str]], str]:
    """把命令帧数据域展开成 ``[(字段, 原始值, 解析值), ...]``；无法识别时给原始 HEX。"""
    rows: List[Tuple[str, str, str]] = []
    cmd = COMMANDS.get(cmd_id)
    if not data:
        return rows, ""
    if cmd is None:
        return [("数据", bytes_to_hex(data), f"{len(data)} 字节")], "未知命令，按原始 HEX 展示"

    names = cmd.resp_fields if is_response else cmd.set_fields
    # 版本应答：2+2+3
    if cmd_id == 0x03 and is_response and len(data) >= 7:
        rows.append(("DSP版本", bytes_to_hex(data[0:2]),
                     f"{data[0]}.{data[1]:02d}"))
        rows.append(("监控器版本", bytes_to_hex(data[2:4]),
                     f"{data[2]}.{data[3]:02d}"))
        rows.append(("版本日期", bytes_to_hex(data[4:7]),
                     f"20{data[4]:02d}-{data[5]:02d}-{data[6]:02d}"))
        if len(data) > 7:
            rows.append(("多余字节", bytes_to_hex(data[7:]), f"{len(data) - 7} 字节"))
        return rows, cmd.note

    if cmd_id == 0x06 and len(data) >= 4:
        snid = int.from_bytes(data[0:4], "little")
        rows.append(("SNID", bytes_to_hex(data[0:4]),
                     "0（不限制同步）" if snid == 0 else str(snid)))
        return rows, cmd.note

    # 逐字节解释的常见命令
    enum_maps = {
        0x02: (BAND_NAMES, BAND_NAMES, BAND_NAMES),
        0x08: (WORK_MODE_NAMES, COMM_PROTO_NAMES, None),
        0x07: (WORK_MODE_NAMES, COMM_PROTO_NAMES, None),
        0x04: (WIRELESS_MODE_NAMES, None, None),
        0x05: (WIRELESS_MODE_NAMES, None, None),
        0x0A: (None, None, None),
        0x09: (None, None, None),
    }
    maps = enum_maps.get(cmd_id, (None, None, None))
    for idx, byte in enumerate(data):
        name = names[idx] if idx < len(names) else f"数据[{idx}]"
        parsed = str(byte)
        mp = maps[idx] if idx < len(maps) else None
        if mp is not None:
            parsed = f"{byte}（{mp.get(byte, '保留')}）"
        elif cmd_id in (0x09, 0x0A) and idx == 0:
            signed = byte - 256 if byte > 127 else byte
            parsed = f"{signed} dBm（0x{byte:02X}）"
        elif cmd_id in (0x09, 0x0A) and idx in (1, 2):
            parsed = f"{byte}（幅度 ×{byte / 32:.4g}）"
        elif cmd_id == 0x01:
            parsed = f"{byte}（{BAND_NAMES.get(byte, '保留')}）"
        rows.append((name, f"0x{byte:02X}", parsed))
    return rows, cmd.note


# ======================================================================
# 三、协议类型=4（南网 SPLC）业务帧的「数据头」
# ======================================================================

def _looks_like_mpdu_fc(data: bytes) -> bool:
    """FC 首字节特征：bit3=1（接入指示）且 bits0-2=定界符类型(0~3)，且至少 16 字节。

    与 ``csg_new_gen_parser`` 自动层级识别同一口径（AGENTS §5.7 / 解析器 823 行附近）。
    """
    if len(data) < 16:
        return False
    first = data[0]
    return bool((first >> 3) & 0x01) and (first & 0x07) <= 3


_SPLC_HDR_NOTE = (
    "协议类型=4（南网SPLC）监控上报的数据头：帧类型(1)+数据头内容(变长)；"
    "SOF 帧为 帧类型1/用户数/4×TMI/4×数据长度，其后才是 MPDU 帧控制(FC)"
)


def split_splc_header(data: bytes) -> Tuple[Optional[Dict[str, object]], bytes]:
    """从协议类型=4 的 DATA 域里剥离监控数据头，返回 ``(info, 剩余字节)``。

    识别失败（结构对不上）返回 ``(None, data)``，调用方按「整段就是 MPDU」处理 —— 
    **绝不猜**：宁可让解析器报错，也不擅自吞掉几字节。

    数据头长度在文档里没有给出显式长度域，因此按两种候选布局试：
      - 定长：帧类型1(1)+用户数(1)+4×TMI(4)+4×数据长度(8) = 15 字节（含帧类型共 16）
      - 变长：帧类型1(1)+用户数(1)+用户数×(TMI 1 + 数据长度 2)
    两种都用「其后必须是一个像样的 MPDU 帧控制」来验证。
    """
    data = bytes(data)
    if not data:
        return None, data
    frame_type = data[0]
    if frame_type not in SPLC_FRAME_TYPE_NAMES:
        return None, data

    if frame_type != 1:
        # 信标 / ACK / 网间协调：只有 1 字节帧类型
        rest = data[1:]
        if not _looks_like_mpdu_fc(rest):
            return None, data
        info = {
            "frame_type": frame_type,
            "frame_type_name": SPLC_FRAME_TYPE_NAMES[frame_type],
            "header_len": 1,
            "users": None,
            "sof_kind": None,
            "user_info": [],
        }
        return info, rest

    # SOF 帧
    if len(data) < 3:
        return None, data
    sof_kind = data[1]
    users = data[2]
    if users < 1 or users > 4:
        return None, data

    candidates: List[int] = []
    fixed = 1 + 1 + 1 + 4 * 1 + 4 * 2        # = 15
    variable = 1 + 1 + 1 + users * 3
    for hlen in (fixed, variable):
        if hlen not in candidates:
            candidates.append(hlen)

    for hlen in candidates:
        rest = data[hlen:]
        if not _looks_like_mpdu_fc(rest):
            continue
        tm_i = list(data[3:3 + users]) if len(data) >= 3 + users else []
        base = 3 + 4 if hlen == fixed else 3 + users
        lens: List[int] = []
        for i in range(users):
            start = base + i * 2
            if start + 2 <= len(data):
                lens.append(int.from_bytes(data[start:start + 2], "little"))
        info = {
            "frame_type": frame_type,
            "frame_type_name": SPLC_FRAME_TYPE_NAMES[frame_type],
            "header_len": hlen,
            "layout": "定长(4×TMI+4×长度)" if hlen == fixed else "变长(按用户数)",
            "sof_kind": sof_kind,
            "sof_kind_name": SPLC_SOF_KIND_NAMES.get(sof_kind, "保留"),
            "users": users,
            "tmi": tm_i,
            "user_lens": lens,
        }
        return info, rest
    return None, data


# ======================================================================
# 三·B、发射机帧（ED..EE，《PLC2.0收发机报文格式0629》）
#
# 注意与上面两节的分工（这一条是 1.26.27 纠正的错误，务必看清）：
#   - **发射机下行**用 ED..EE（本节）：PC 把要发的载波帧交给发射机；
#   - **监控器上行**用 96..16（第二节）：监控器把收到的帧上报给 PC；
#   - **68..16** 是监控器/接收机的查询设置命令（第三节），**不是**发射机协议。
# 三者帧头互不相同，不要拿 96..16 的头部字段去解释 ED..EE。
# ======================================================================

TX_HEAD = 0xED
TX_TAIL = 0xEE
TX_DATA_START = 0xEF

CTRL1_DATA = 0x00           # 控制域1：数据报文
CTRL1_CONTROL = 0x01        # 控制域1：控制报文

#: 帧长（2 字节小端）= 控制域1 + 控制域2 + EF + 数据域 + CS，故 数据域 ≤ 65535-4
MAX_TX_DATA_LEN = 0xFFFF - 4

#: 物理信道（数据报文第一字节）
PHY_CHANNEL_NAMES = {
    0x01: "HPLC",
    0x02: "RF",
    0x03: "HPLC+RF",
    0x20: "PLC2.0 OFDMA",
}
#: 0x10~0x1C 是 PLC2.0 MIMO 端口映射
PHY_CHANNEL_MIMO_RANGE = (0x10, 0x1C)

#: 时间戳取值（数据报文）
TS_IMMEDIATE = 0x00000000   # 立即发送
TS_TRIGGER = 0xFFFFFFFF     # 触发发送

#: 数据报文子类型（PC->HW 可发的四种结构化 + 两种手工）
TX_DATA_SUBTYPES = {
    0x01: "FC数据",
    0x02: "FC+Payload数据",
    0x03: "Payload数据",
    0x06: "RF+HPLC同时发送FC+Payload",
    0x07: "FC+Payload（OFDMA 四用户）",
    0x08: "UL-OFDMA帧(DL-OFDMA的SACK帧)",
}
#: HW->PC 上报的数据子类型（只解析/展示，不作为发帧选项）
TX_DATA_SUBTYPES_HW = {
    0x04: "发送完成",
    0x05: "选择确认帧发送完成",
}
#: 可由页面结构化组帧的子类型（其余走「手工数据域」）
TX_STRUCTURED_SUBTYPES = (0x01, 0x02, 0x03, 0x08)


def phy_channel_name(value: int) -> str:
    """物理信道名字；0x10~0x1C 归为 MIMO。"""
    try:
        channel = int(value)
    except (TypeError, ValueError):
        return f"保留({value!r})"
    if channel in PHY_CHANNEL_NAMES:
        return PHY_CHANNEL_NAMES[channel]
    low, high = PHY_CHANNEL_MIMO_RANGE
    if low <= channel <= high:
        return f"PLC2.0 MIMO(0x{channel:02X})"
    return f"保留(0x{channel:02X})"


def tx_data_subtype_name(ctrl2: int) -> str:
    ctrl2 = int(ctrl2)
    if ctrl2 in TX_DATA_SUBTYPES:
        return TX_DATA_SUBTYPES[ctrl2]
    if ctrl2 in TX_DATA_SUBTYPES_HW:
        return TX_DATA_SUBTYPES_HW[ctrl2]
    return f"保留(0x{ctrl2:02X})"


def build_tx_frame(ctrl1: int, ctrl2: int, data: bytes = b"",
                   cs_mode: str = "sum") -> bytes:
    """组一帧 PLC2.0 收发机帧（ED..EE）。

    :param ctrl1: 0x00 数据报文 / 0x01 控制报文
    :param ctrl2: 子类型（数据报文 = 0x01/0x02/0x03/0x06/0x07/0x08；控制报文见 TX_COMMANDS）
    :param data: 数据域（已按子类型排好的头部 + 载荷）
    :param cs_mode: ``"sum"`` = 帧头到数据域末累加取低 8 位；``"xff"`` = 固定 0xFF
        （文档写「校验暂且保留…目前填 0xFF」，两种现场设备都有，故做成可选）
    """
    payload = bytes(data)
    if len(payload) > MAX_TX_DATA_LEN:
        raise ValueError(f"数据域过长（{len(payload)} > {MAX_TX_DATA_LEN} 字节）")
    frame_len = len(payload) + 4          # 控制域1+控制域2+EF+数据域+CS
    body = bytearray([TX_HEAD, frame_len & 0xFF, (frame_len >> 8) & 0xFF,
                      int(ctrl1) & 0xFF, int(ctrl2) & 0xFF, TX_DATA_START])
    body.extend(payload)
    cs = 0xFF if str(cs_mode).lower() == "xff" else checksum(body)
    body.append(cs)
    body.append(TX_TAIL)
    return bytes(body)


def build_tx_data_payload(ctrl2: int, *, payload: bytes = b"", channel: int = 0x01,
                          timestamp: int = TS_IMMEDIATE, pb_count: int = 1,
                          pb_len: int = 0, crc_error: int = 0,
                          tmi: int = 0, ru: int = 0, pad: int = 0) -> bytes:
    """按子类型组「数据报文」的数据域（公共头 + 业务帧）。

    ``pb_len=0`` 表示按业务帧长度自动填（= ``len(payload)``）。
    0x06/0x07 结构过于自由，页面走「手工数据域」，这里不做自动拼装。
    """
    ctrl2 = int(ctrl2)
    payload = bytes(payload)
    if ctrl2 not in TX_STRUCTURED_SUBTYPES:
        raise ValueError(f"子类型 0x{ctrl2:02X} 不支持自动拼装，请用「手工数据域」")
    length = len(payload) if not pb_len else int(pb_len)
    if not 0 <= length <= 0xFFFF:
        raise ValueError(f"单个物理块长度超出 2 字节范围：{length}")
    if not 0 <= int(pb_count) <= 0xFF:
        raise ValueError(f"物理块个数超出 1 字节范围：{pb_count}")
    if not 0 <= int(timestamp) <= 0xFFFFFFFF:
        raise ValueError(f"时间戳超出 4 字节范围：{timestamp}")

    out = bytearray()
    if ctrl2 == 0x08:
        out.extend([int(channel) & 0xFF, int(tmi) & 0xFF, int(ru) & 0xFF,
                    int(pad) & 0xFF])
    else:
        out.append(int(channel) & 0xFF)
    out.extend(int(timestamp).to_bytes(4, "little"))
    out.append(int(pb_count) & 0xFF)
    out.append(1 if crc_error else 0)     # 0x01/0x03 此处为「保留」，恒 0
    out.extend(length.to_bytes(2, "little"))
    out.extend(payload)
    return bytes(out)


def parse_tx_frame(frame: bytes) -> Dict[str, object]:
    """解析一帧 PLC2.0 收发机帧（ED..EE），返回包装头信息。

    结构与 :func:`monitor_widget` 的 plc2 解帧口径一致（同一份文档），
    这里独立实现一份纯逻辑版本，供收发机页的日志与执行器使用。
    """
    frame = bytes(frame)
    info: Dict[str, object] = {"ok": False, "error": "", "frame": frame}
    if len(frame) < 8:
        info["error"] = f"长度不足（{len(frame)} < 8 字节）"
        return info
    if frame[0] != TX_HEAD:
        info["error"] = f"起始符不是 EDH（实际 {frame[0]:02X}H）"
        return info
    frame_len = frame[1] | (frame[2] << 8)
    total = frame_len + 4
    if total != len(frame):
        info["error"] = (f"帧长域声明 {frame_len} 字节，整帧应为 {total} 字节，"
                         f"实际 {len(frame)} 字节")
        return info
    if frame[5] != TX_DATA_START:
        info["error"] = f"数据域起始符不是 EFH（实际 {frame[5]:02X}H）"
        return info
    if frame[-1] != TX_TAIL:
        info["error"] = f"结束符不是 EEH（实际 {frame[-1]:02X}H）"
        return info

    ctrl1 = frame[3]
    ctrl2 = frame[4]
    data = frame[6:-2]
    cs = frame[-2]
    calc = checksum(frame[:-2])
    info.update({
        "ok": calc == cs or cs == 0xFF,
        "cs": cs,
        "cs_calc": calc,
        "cs_reserved": cs == 0xFF,
        "error": ("" if (calc == cs or cs == 0xFF)
                  else f"CS 校验失败（收到 {cs:02X}H，计算 {calc:02X}H）"),
        "frame_len": frame_len,
        "ctrl1": ctrl1,
        "ctrl1_name": {CTRL1_DATA: "数据报文", CTRL1_CONTROL: "控制报文"}.get(
            ctrl1, f"保留(0x{ctrl1:02X})"),
        "ctrl2": ctrl2,
        "ctrl2_name": (tx_data_subtype_name(ctrl2) if ctrl1 == CTRL1_DATA
                       else tx_command_name(ctrl2)),
        "data_len": len(data),
        "data": data,
    })
    return info


# ----------------------------------------------------------------------
# 数据报文：解出公共头（供日志/详情展示）
# ----------------------------------------------------------------------

#: 数据报文各子类型的公共头长度（其后才是业务帧 FC+Payload）
TX_DATA_HEADER_LEN = {
    0x01: 9,    # 信道+时间戳+块个数+保留+块长
    0x02: 9,    # 信道+时间戳+块个数+CRC+块长
    0x03: 9,    # 信道+时间戳+块个数+保留+块长
    0x08: 12,   # 信道+TMI+RU+pad+时间戳+块个数+CRC+块长
    0x06: 13,   # 两个信道+时间戳+两个块数+CRC+两个块长
    0x07: 40,   # 信道+保留3+时间戳+4×(块数+CRC+块长)+FC+eFC(32B)
}


def tx_business_payload(ctrl2: int, data: bytes) -> Optional[bytes]:
    """从数据报文数据域里取出**业务帧**（FC + Payload），供协议9 解析器展开。

    结构对不上（数据域太短 / 未知子类型）返回 ``None`` —— 调用方据此跳过业务帧解析，
    绝不按猜测的偏移切字节。
    """
    data = bytes(data)
    offset = TX_DATA_HEADER_LEN.get(int(ctrl2))
    if offset is None or len(data) < offset:
        return None
    return data[offset:]


def decode_tx_data_payload(ctrl2: int, data: bytes) -> Tuple[List[Tuple[str, str, str]], str]:
    """把「数据报文」的数据域展开成 ``[(字段, 原始值, 解析值), ...]``。"""
    data = bytes(data)
    rows: List[Tuple[str, str, str]] = []
    ctrl2 = int(ctrl2)

    def need(n: int) -> bool:
        return len(data) >= n

    if ctrl2 in (0x01, 0x02, 0x03):
        if not need(9):
            return rows, f"数据域不足 9 字节（{len(data)}）"
        ch = data[0]
        ts = int.from_bytes(data[1:5], "little")
        pb_count = data[5]
        flag = data[6]
        pb_len = int.from_bytes(data[7:9], "little")
        rows += [
            ("物理信道", f"0x{ch:02X}", phy_channel_name(ch)),
            ("时间戳", f"0x{ts:08X}", _describe_timestamp(ts)),
            ("物理块个数", str(pb_count), str(pb_count)),
            (("Payload CRC" if ctrl2 == 0x02 else "保留"),
             f"0x{flag:02X}",
             ("错误" if flag else "正确") if ctrl2 == 0x02 else "保留"),
            ("单个物理块长度", str(pb_len), str(pb_len)),
            (("数据FC+Payload" if ctrl2 == 0x02 else
              ("数据FC" if ctrl2 == 0x01 else "数据Payload")),
             bytes_to_hex(data[9:][:32]) + (" …" if len(data) - 9 > 32 else ""),
             f"{len(data) - 9} 字节"),
        ]
        return rows, ""

    if ctrl2 == 0x08:
        if not need(13):
            return rows, f"数据域不足 13 字节（{len(data)}）"
        ch, tmi, ru, pad = data[0], data[1], data[2], data[3]
        ts = int.from_bytes(data[4:8], "little")
        pb_count, flag = data[8], data[9]
        pb_len = int.from_bytes(data[10:12], "little") if need(12) else 0
        rows += [
            ("物理信道", f"0x{ch:02X}", phy_channel_name(ch)),
            ("TMI", str(tmi), str(tmi)),
            ("RU", str(ru), str(ru)),
            ("pad", f"0x{pad:02X}", str(pad)),
            ("时间戳", f"0x{ts:08X}", _describe_timestamp(ts)),
            ("物理块个数", str(pb_count), str(pb_count)),
            ("Payload CRC", f"0x{flag:02X}", "错误" if flag else "正确"),
            ("单个物理块长度", str(pb_len), str(pb_len)),
            ("数据FC+Payload", bytes_to_hex(data[12:][:32]) + (" …" if len(data) - 12 > 32 else ""),
             f"{len(data) - 12} 字节"),
        ]
        return rows, "0x08 的 时间戳=0xFFFFFFFF 表示触发发送、0 立即发送、其它为定时发送"

    if ctrl2 == 0x06:
        if not need(13):
            return rows, f"数据域不足 13 字节（{len(data)}）"
        ch1, ch2 = data[0], data[1]
        ts = int.from_bytes(data[2:6], "little")
        pb1, pb2, crc = data[6], data[7], data[8]
        len1 = int.from_bytes(data[9:11], "little")
        len2 = int.from_bytes(data[11:13], "little")
        rows += [
            ("报文1物理信道", f"0x{ch1:02X}", phy_channel_name(ch1)),
            ("报文2物理信道", f"0x{ch2:02X}", phy_channel_name(ch2)),
            ("时间戳", f"0x{ts:08X}", _describe_timestamp(ts)),
            ("报文1物理块个数", str(pb1), str(pb1)),
            ("报文2物理块个数", str(pb2), str(pb2)),
            ("Payload CRC", f"0x{crc:02X}", "错误" if crc else "正确"),
            ("报文1单个物理块长度", str(len1), str(len1)),
            ("报文2单个物理块长度", str(len2), str(len2)),
            ("数据1+数据2", bytes_to_hex(data[13:][:32]) + (" …" if len(data) - 13 > 32 else ""),
             f"{len(data) - 13} 字节"),
        ]
        return rows, ""

    if ctrl2 == 0x07:
        if not need(20):
            return rows, f"数据域不足 20 字节（{len(data)}）"
        ch = data[0]
        ts = int.from_bytes(data[4:8], "little")
        rows.append(("物理信道", f"0x{ch:02X}", phy_channel_name(ch)))
        rows.append(("保留", bytes_to_hex(data[1:4]), "3 字节"))
        rows.append(("时间戳", f"0x{ts:08X}", _describe_timestamp(ts)))
        offset = 8
        for user in range(4):
            if offset + 4 > len(data):
                break
            pb_cnt, crc = data[offset], data[offset + 1]
            pb_len = int.from_bytes(data[offset + 2:offset + 4], "little")
            rows.append((f"用户{user} 物理块个数", str(pb_cnt), str(pb_cnt)))
            rows.append((f"用户{user} Payload CRC", f"0x{crc:02X}",
                         "错误" if crc else "正确"))
            rows.append((f"用户{user} 单个物理块长度", str(pb_len), f"{pb_len} 字节"))
            offset += 4
        if offset + 32 <= len(data):
            rows.append(("数据FC+eFC", bytes_to_hex(data[offset:offset + 32]), "32 字节"))
            offset += 32
        rows.append(("Payload0~3", bytes_to_hex(data[offset:][:32]) +
                     (" …" if len(data) - offset > 32 else ""), f"{len(data) - offset} 字节"))
        return rows, "0x07 是 OFDMA 四用户帧：FC+eFC 固定 32 字节，其后按用户顺序拼 Payload"

    if ctrl2 in TX_DATA_SUBTYPES_HW:
        if ctrl2 == 0x04:
            if need(4):
                ts = int.from_bytes(data[0:4], "little")
                rows.append(("时间戳", f"0x{ts:08X}", "发送结束时间"))
            return rows, "发送完成上报"
        if need(4):
            ts = int.from_bytes(data[0:4], "little")
            rows.append(("时间戳", f"0x{ts:08X}", "发送结束时间"))
            if len(data) > 4:
                rows.append(("选择确认帧", bytes_to_hex(data[4:][:32]),
                             f"{len(data) - 4} 字节"))
        return rows, ""

    rows.append(("数据域", bytes_to_hex(data[:64]) + (" …" if len(data) > 64 else ""),
                 f"{len(data)} 字节"))
    return rows, "未定义的数据子类型，按原始 HEX 展示"


def _describe_timestamp(ts: int) -> str:
    """时间戳的**解析值**（日志里只显示这一列，所以不再重复原始数值）。

    - ``0`` → 立即发送；``0xFFFFFFFF`` → 触发发送；其它是按 PC 预置时间的定时发送，
      保留具体时间点（`定时发送 1234567890`），否则无法判断发的是哪一刻。
    """
    if ts == TS_IMMEDIATE:
        return "立即发送"
    if ts == TS_TRIGGER:
        return "触发发送"
    return f"定时发送 {ts}"


# ----------------------------------------------------------------------
# 控制报文（控制域1=0x01）：PC->HW 指令表
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class TxField:
    """控制指令里的一个定长字段（页面据此生成下拉/数字框）。

    ``kind="pad"`` 表示文档里的「保留 N 字节」——发送时填 0，界面上不给控件。
    """

    name: str
    kind: str = "u8"            # u8 | u16le | u32le | pad
    minimum: int = 0
    maximum: int = 255
    choices: Optional[Dict[int, str]] = None
    suffix: str = ""
    help: str = ""
    length: int = 0             # 仅 pad：固定字节数

    @property
    def size(self) -> int:
        if self.kind == "pad":
            return max(1, int(self.length))
        return 4 if self.kind == "u32le" else (2 if self.kind == "u16le" else 1)


@dataclass(frozen=True)
class TxCommandDef:
    """一条 PLC2.0 控制指令。"""

    ctrl2: int
    name: str
    fields: Tuple[TxField, ...] = ()
    #: 变长尾巴的说明（非空 ⇒ 页面给一个 HEX 输入框）
    tail: str = ""
    #: 该指令的应答子类型（0 表示无/未知）
    resp: int = 0
    note: str = ""
    #: False = 只解析（HW->PC 上报指令）
    sendable: bool = True

    @property
    def fixed_len(self) -> int:
        return sum(spec.size for spec in self.fields)


BAND_TAGS = {0: "10M", 1: "3M", 2: "2.2M", 3: "1.2M"}
PHASE_CHOICES = {1: "A相", 2: "B相", 3: "C相"}
CLOCK_CHOICES = {1: "标准设备自身时钟源", 2: "外灌时钟源"}
FILL_CRC_CHOICES = {1: "硬件填充 CRC", 2: "硬件不填充 CRC"}
TONEMASK_CHOICES = {0: "Tonemask 测试模式1", 1: "Tonemask 测试模式2"}
SFO_CHOICES = {1: "按信标同步时钟与补偿频偏", 2: "不同步/不补偿"}
SYNC_CHOICES = {0: "优先与无线信标对齐", 1: "优先与载波信标对齐"}
TEST_FLAG_CHOICES = {1: "发送开始", 2: "发送结束"}
CRC_FLAG_CHOICES = {0: "CRC 正确", 1: "CRC 错误"}

TX_COMMANDS: Dict[int, TxCommandDef] = {
    0x00: TxCommandDef(0x00, "复位", resp=0x00,
                       note="接口未定义确认指令；复位后建议重新下发频段/相线"),
    0x01: TxCommandDef(
        0x01, "通讯测试（连续发送）",
        fields=(
            TxField("连续发送次数", "u16le", 1, 65535),
            TxField("单个物理块长度", "u16le", 0, 4096, help="0 = 按业务帧长度自动"),
            TxField("连续发送帧间隔", "u32le", 0, 0xFFFFFFFF, suffix=" us"),
            TxField("物理块个数", "u8", 1, 255),
            TxField("物理信道", "u8", 1, 0xFF, PHY_CHANNEL_NAMES),
        ),
        tail="数据FC+Payload", resp=0x02,
        note="用于通信性能测试：一次性让硬件连发 N 次，不用 PC 逐帧发",
    ),
    0x03: TxCommandDef(0x03, "读硬件平台时间", resp=0x04),
    0x05: TxCommandDef(
        0x05, "设置硬件平台时间偏移",
        fields=(TxField("偏移量", "u32le", 0, 0xFFFFFFFF),),
        resp=0x06, note="应答返回「偏移后时间戳」",
    ),
    0x07: TxCommandDef(
        0x07, "设置回复选择确认帧的TEI列表",
        tail="TEI 列表（2 字节/个，低 12bit 有效）", resp=0x08,
        note="列表为空 = 清除硬件里的列表",
    ),
    0x09: TxCommandDef(
        0x09, "频段模式配置",
        fields=(TxField("频段TAG", "u8", 0, 3, BAND_TAGS),
                TxField("保留", "pad", length=3)),
        resp=0x0A, note="切换频段后需等待 2s 再进行其它操作",
    ),
    0x0B: TxCommandDef(
        0x0B, "设置通讯相线",
        fields=(TxField("相线", "u8", 1, 3, PHASE_CHOICES),
                TxField("保留", "pad", length=3)),
        resp=0x0C,
    ),
    0x0D: TxCommandDef(
        0x0D, "设置强制回复NACK的TEI列表",
        tail="TEI 列表（2 字节/个，低 12bit 有效）", resp=0x0E,
        note="同时出现在回复列表与 NACK 列表时以 NACK 为准",
    ),
    0x11: TxCommandDef(
        0x11, "进入速率测试模式",
        tail="数据FC+Payload", resp=0x00,
        note="进入后按该业务帧连续发送（文档未定义确认指令）",
    ),
    0x12: TxCommandDef(0x12, "退出速率测试模式", resp=0x00),
    0x13: TxCommandDef(
        0x13, "切换标准设备时钟源",
        fields=(TxField("时钟源", "u8", 1, 2, CLOCK_CHOICES),
                TxField("保留", "pad", length=3)),
        resp=0x14,
    ),
    0x15: TxCommandDef(
        0x15, "设置硬件填充CRC",
        fields=(TxField("CRC填充", "u8", 1, 2, FILL_CRC_CHOICES),
                TxField("保留", "pad", length=3)),
        resp=0x16,
    ),
    0x17: TxCommandDef(
        0x17, "设置Tonemask测试模式",
        fields=(TxField("Tonemask 模式", "u8", 0, 1, TONEMASK_CHOICES),
                TxField("保留", "pad", length=3)),
        resp=0x18, note="切换后需等待 2s 再进行其它操作",
    ),
    0x19: TxCommandDef(
        0x19, "设置同步时钟与补偿频偏",
        fields=(TxField("SFO", "u8", 1, 2, SFO_CHOICES),
                TxField("同步类型", "u8", 0, 1, SYNC_CHOICES),
                TxField("保留", "pad", length=2)),
        resp=0x20,
    ),
    0x21: TxCommandDef(
        0x21, "设置强制回复特殊ACK的设备TEI",
        fields=(
            TxField("TEI", "u16le", 0, 0x0FFF),
            TxField("SNID", "u32le", 0, 0xFFFFFFFF),
            TxField("RESULT", "u8", 0, 0xFF),
            TxField("STATE", "u8", 0, 0xFF),
            TxField("STEI", "u16le", 0, 0x0FFF),
            TxField("DTEI", "u16le", 0, 0x0FFF),
        ),
        resp=0x22,
        note="特殊 ACK 里填充的接收结果/状态与源、目的 TEI",
    ),
    0x23: TxCommandDef(
        0x23, "进入特定物理信道收发模式",
        fields=(TxField("物理信道", "u8", 1, 3,
                        {1: "HPLC", 2: "RF", 3: "RF+HPLC"}),),
        resp=0x24,
    ),
    0x25: TxCommandDef(
        0x25, "RF信道切换",
        fields=(TxField("频点index", "u16le", 0, 0xFFFF,
                        help="从起始频点到目标频点的信道 index"),
                TxField("Option", "u8", 0, 3)),
        resp=0x26,
    ),
    0x31: TxCommandDef(0x31, "启动NTB采集", resp=0x32),
    0x33: TxCommandDef(0x33, "停止NTB采集", resp=0x34),
    0x36: TxCommandDef(
        0x36, "bitloading加载表配置",
        fields=(
            TxField("源TEI", "u16le", 0, 0x0FFF),
            TxField("目的TEI", "u16le", 0, 0x0FFF),
            TxField("流数", "u8", 1, 2),
            TxField("截止载波", "u16le", 0, 0xFFFF),
            TxField("子载波分组大小", "u8", 0, 0xFF),
            TxField("比特加载表长度", "u16le", 0, 0xFFFF,
                    help="0 = 按下面填写的比特加载表字节数自动"),
            TxField("Bps", "u16le", 0, 0xFFFF),
        ),
        tail="比特加载表（每 8 个子载波组 3 字节，3bit/组）", resp=0x00,
    ),
    0x38: TxCommandDef(
        0x38, "dl_ofdma数据接收TEI配置",
        fields=(TxField("TEI", "u16le", 0, 0x0FFF),
                TxField("保留", "pad", length=3)),
        resp=0x00,
    ),
    0x39: TxCommandDef(
        0x39, "ul_ofdma数据接收配置",
        fields=tuple(
            field
            for user in range(4)
            for field in (
                TxField(f"User{user} TMI", "u8", 0, 0xFF),
                TxField(f"User{user} RU", "u8", 0, 0xFF),
                TxField(f"User{user} PB个数", "u8", 0, 0xFF),
            )
        ),
        resp=0x00,
    ),
    0x3A: TxCommandDef(0x3A, "ul_ofdma接收帧间隔上报",
                       fields=(TxField("接收NTB间隔", "u32le", 0, 0xFFFFFFFF),),
                       note="HW->PC 上报", sendable=False),
    # ---- 仅解析（HW->PC） ----
    0x02: TxCommandDef(0x02, "通讯测试确认",
                       fields=(TxField("FLAG", "u8", 1, 2, TEST_FLAG_CHOICES),
                               TxField("保留", "pad", length=3)),
                       sendable=False),
    0x04: TxCommandDef(0x04, "读硬件平台时间回复",
                       fields=(TxField("时间戳", "u32le", 0, 0xFFFFFFFF),),
                       sendable=False),
    0x06: TxCommandDef(0x06, "设置时间偏移确认",
                       fields=(TxField("偏移后时间戳", "u32le", 0, 0xFFFFFFFF),),
                       sendable=False),
    0x08: TxCommandDef(0x08, "设备TEI列表设置确认", sendable=False),
    0x0A: TxCommandDef(0x0A, "频段模式配置确认", sendable=False),
    0x0C: TxCommandDef(0x0C, "设置通讯相线确认", sendable=False),
    0x0E: TxCommandDef(0x0E, "NACK设备TEI列表设置确认", sendable=False),
    0x14: TxCommandDef(0x14, "切换时钟源成功", sendable=False),
    0x16: TxCommandDef(0x16, "硬件填充CRC成功", sendable=False),
    0x18: TxCommandDef(0x18, "设置Tonemask成功", sendable=False),
    0x20: TxCommandDef(0x20, "设置同步时钟与补偿频偏成功", sendable=False),
    0x22: TxCommandDef(0x22, "设置特殊ACK成功", sendable=False),
    0x24: TxCommandDef(0x24, "进入特定物理信道成功", sendable=False),
    0x26: TxCommandDef(0x26, "切换指定信道成功", sendable=False),
    0x32: TxCommandDef(0x32, "启动NTB采集成功", sendable=False),
    0x34: TxCommandDef(0x34, "停止NTB采集成功", sendable=False),
    0x35: TxCommandDef(0x35, "NTB采集结果上报", sendable=False,
                       tail="A/B/C 相过零点数量(各2B) + 三相 NTB 序列(各 N*4B)"),
}


def tx_command_name(ctrl2: int) -> str:
    definition = TX_COMMANDS.get(int(ctrl2))
    return definition.name if definition else f"保留(0x{int(ctrl2):02X})"


def sendable_tx_commands() -> List[TxCommandDef]:
    return [TX_COMMANDS[key] for key in sorted(TX_COMMANDS)
            if TX_COMMANDS[key].sendable]


def tx_command_payload(ctrl2: int, values: Sequence[int] = (),
                       tail: bytes = b"") -> "CommandPayload":
    """按指令表把结构化字段 + 变长尾巴拼成数据域。

    ``values`` 只对应**可编辑字段**（``pad`` 保留字节由本函数自动填 0，不占位）。
    """
    definition = TX_COMMANDS.get(int(ctrl2))
    if definition is None:
        return CommandPayload(False, b"", f"未知控制指令 0x{int(ctrl2):02X}")
    if not definition.sendable:
        return CommandPayload(False, b"", f"{definition.name} 是设备上报指令，不能下发")
    specs = [spec for spec in definition.fields if spec.kind != "pad"]
    if values and len(values) != len(specs):
        return CommandPayload(False, b"", f"{definition.name} 需要 {len(specs)} 个字段，"
                                          f"实际 {len(values)} 个")
    out = bytearray()
    index = 0
    for spec in definition.fields:
        if spec.kind == "pad":
            out.extend(b"\x00" * spec.size)
            continue
        value = int(values[index]) if values else int(spec.minimum)
        index += 1
        if not spec.minimum <= value <= spec.maximum:
            return CommandPayload(False, b"",
                                  f"{spec.name} 超出范围（{value} 不在 "
                                  f"{spec.minimum}~{spec.maximum}）")
        if spec.kind == "u32le":
            out.extend(value.to_bytes(4, "little"))
        elif spec.kind == "u16le":
            out.extend(value.to_bytes(2, "little"))
        else:
            out.append(value & 0xFF)
    out.extend(bytes(tail))
    return CommandPayload(True, bytes(out), "")


def tx_command_values(ctrl2: int, data: bytes) -> List[int]:
    """从数据域里回填**可编辑字段**（``pad`` 跳过；长度不符时尽力取）。"""
    definition = TX_COMMANDS.get(int(ctrl2))
    if definition is None:
        return []
    values: List[int] = []
    offset = 0
    for spec in definition.fields:
        size = spec.size
        chunk = bytes(data[offset:offset + size])
        if spec.kind != "pad":
            values.append(int.from_bytes(chunk, "little") if len(chunk) == size else 0)
        offset += size
    return values


def decode_tx_control_payload(ctrl2: int, data: bytes) -> Tuple[List[Tuple[str, str, str]], str]:
    """控制报文数据域 → 字段行。"""
    definition = TX_COMMANDS.get(int(ctrl2))
    data = bytes(data)
    rows: List[Tuple[str, str, str]] = []
    if definition is None:
        rows.append(("数据域", bytes_to_hex(data[:64]), f"{len(data)} 字节"))
        return rows, "未定义的控制指令，按原始 HEX 展示"
    offset = 0
    for spec in definition.fields:
        size = spec.size
        chunk = data[offset:offset + size]
        if len(chunk) < size:
            break
        if spec.kind == "pad":
            rows.append((f"{spec.name}({size}B)", bytes_to_hex(chunk), "保留"))
            offset += size
            continue
        value = int.from_bytes(chunk, "little")
        text = str(value)
        if spec.choices:
            text = f"{value}（{spec.choices.get(value, '保留')}）"
        elif spec.suffix:
            text = f"{value}{spec.suffix}"
        rows.append((spec.name, f"0x{value:0{size * 2}X}", text))
        offset += size
    tail = data[offset:]
    if tail:
        rows.append((definition.tail or "附加数据",
                     bytes_to_hex(tail[:32]) + (" …" if len(tail) > 32 else ""),
                     f"{len(tail)} 字节"))
    return rows, definition.note


# ======================================================================
# 四、串口数据流解帧
# ======================================================================

def _find_command_frame_end(buf: bytes, start: int) -> Optional[int]:
    """在 ``buf[start:]`` 里找一个 CS 校验通过的命令帧，返回帧末索引（含 16H）。

    命令帧没有长度域，只能用「候选 16H + CS 校验」逐个试；
    顺序为「从最短合法帧往长找」，且 **只有 CS 校验通过才接受**，
    避免数据域里恰好出现 16H 时把帧切碎。
    """
    n = len(buf)
    cs_at = start + 10            # 最短情形：CS 紧跟读写标志（68+6+68+id+rw 之后）
    # CS 位置上限：整帧（CS + 16H）不超过 MAX_CMD_FRAME_LEN
    max_cs_at = start + MAX_CMD_FRAME_LEN - 2
    while cs_at <= max_cs_at and cs_at + 1 < n:
        if buf[cs_at + 1] == FRAME_TAIL:
            calc = checksum(buf[start:cs_at])
            if calc == buf[cs_at]:
                return cs_at + 1
        cs_at += 1
    return None


def deframe_stream(buf: bytes) -> Tuple[List[Dict[str, object]], int]:
    """从串口字节流里抽取所有完整帧。

    返回 ``(frames, consumed)``：

    - ``frames``：``[{"kind": "tx"|"data"|"cmd", "frame": bytes, "info": dict}, ...]``
      - ``"tx"``  = ED..EE 发射机帧（PC → 发射机 / 发射机回执）
      - ``"data"``= 96..16 监控器上报帧（监控器 → PC）
      - ``"cmd"`` = 68..16 监控器查询/设置命令
    - ``consumed``：已消费字节数，调用方可 ``del buf[:consumed]``

    三种帧头（EDH / 96H / 68H）混排也能处理：以最先出现的帧头为准，
    某个帧头解不出完整帧时（数据未收齐）停止，剩余字节留待下一批。
    """
    frames: List[Dict[str, object]] = []
    data = bytes(buf)
    n = len(data)
    i = 0
    while i < n:
        head = data[i]
        if head == TX_HEAD:
            if i + 6 > n:
                break
            frame_len = data[i + 1] | (data[i + 2] << 8)
            total = frame_len + 4
            if total < 8 or total > MAX_TX_DATA_LEN + 4:
                i += 1                      # 帧长不合理，判为伪帧头
                continue
            if i + total > n:
                break                       # 未收齐
            if data[i + total - 1] != TX_TAIL or data[i + 5] != TX_DATA_START:
                i += 1                      # 结束符/数据域起始符不符，判为伪帧头
                continue
            frame = data[i:i + total]
            frames.append({"kind": "tx", "frame": frame,
                           "info": parse_tx_frame(frame)})
            i += total
            continue
        if head == FRAME_HEAD_DATA:
            if i + 8 > n:
                break
            length = data[i + 6] | ((data[i + 7] & 0x0F) << 8)
            total = 8 + length + 2
            if i + total > n:
                break
            if data[i + total - 1] != FRAME_TAIL:
                i += 1
                continue
            frame = data[i:i + total]
            frames.append({"kind": "data", "frame": frame,
                           "info": parse_data_frame(frame)})
            i += total
            continue
        if head == FRAME_HEAD_CMD:
            if i + 8 > n:
                break
            if data[i + 7] != FRAME_HEAD_CMD:
                i += 1
                continue
            end = _find_command_frame_end(data, i)
            if end is None:
                # 可能是数据还没收齐：整段留着等下一批；但已超长就丢弃这个帧头
                if n - i > MAX_CMD_FRAME_LEN:
                    i += 1
                    continue
                break
            frame = data[i:end + 1]
            frames.append({"kind": "cmd", "frame": frame,
                           "info": parse_command_frame(frame)})
            i = end + 1
            continue
        i += 1
    return frames, i


# ======================================================================
# 五、用例文件（JSON）
# ======================================================================

CASE_FORMAT = "splc-transceiver-case"
#: 2 = 1.26.27 起改用 PLC2.0（ED..EE）发射机协议；1 = 早期 96..16 版本（已废弃）
CASE_SCHEMA_VERSION = 2
CASE_SUFFIX = ".json"
CASE_DIR_NAME = "splc_transceiver_cases"
MAX_CASE_STEPS = 500
MAX_NAME_LEN = 80

#: 步骤类型
STEP_KINDS = {
    "data": "发射机·数据报文",
    "command": "发射机·控制报文",
    "monitor": "接收机·监控器命令",
    "wait": "等待",
    "raw": "透传报文",
}
#: 步骤信道/端口
STEP_PORTS = {
    "HPLC": "HPLC",
    "RF": "RF",
    "工装板": "工装板",
    "接收机": "接收机",
}

DEFAULT_STEP = {
    "kind": "data",
    "category": "发送",
    "name": "",
    "type": "",
    "param": "",
    "count": 1,
    "interval_ms": 500,
    "port": "HPLC",
    "data": "",
    "command": "",
    "note": "",
    "enabled": True,
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def case_dir() -> Path:
    """用例目录（开发模式=项目根，打包后=exe 目录）。"""
    return Path(app_paths.data_path(CASE_DIR_NAME))


def settings_path() -> Path:
    """页面配置（串口/参数等）落盘文件。"""
    return Path(app_paths.data_path("splc_transceiver.json"))


def normalize_name(name: str) -> str:
    return " ".join(str(name or "").split())


def _safe_int(value, fallback: int, minimum: int, maximum: int) -> int:
    """宽松转 int 并夹到区间（读用例文件用，坏值一律回落而不是抛异常）。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, number))


def tx_command_ref(ctrl2: int) -> str:
    """发射机控制报文的引用字符串（``"09"``）。"""
    return f"{int(ctrl2):02X}"


def _parse_hex_code(text) -> int:
    """``"09"`` / ``"0x09"`` / ``9`` → 9；非法返回 0。"""
    if isinstance(text, int):
        return text
    raw = str(text or "").strip()
    if not raw:
        return 0
    try:
        return int(raw, 16)
    except ValueError:
        return 0


def validate_case_name(name: str) -> str:
    """返回错误信息，空串表示合法（同时用于文件名）。"""
    clean = normalize_name(name)
    if not clean:
        return "用例名不能为空"
    if len(clean) > MAX_NAME_LEN:
        return f"用例名过长（{len(clean)} > {MAX_NAME_LEN}）"
    if any(ch in clean for ch in '\\/:*?"<>|'):
        return '用例名不能包含 \\ / : * ? " < > |'
    return ""


@dataclass
class Step:
    """用例里的一步。

    步骤类型与「谁说话」的对应关系（1.26.27 起）：

    - ``data``：**发射机**数据报文（PLC2.0，ED..EE）—— 业务帧 + 物理信道/时间戳/
      物理块个数/块长度；``data`` 存业务帧 HEX（``manual_data=True`` 时存完整数据域）；
    - ``command``：**发射机**控制报文（PLC2.0，ED..EE 控制域1=0x01）——``command`` 存
      ``"<ctrl2 hex>"``，字段值由 ``tx_values`` 保存，变长尾巴在 ``data``；
    - ``monitor``：**接收机（监控器）** 查询/设置命令（68..16）——``command`` 存
      :func:`command_ref` 生成的 ``"07:1"`` 形式，``data`` 存命令数据域 HEX；
    - ``wait``：等待；``raw``：原样透传（工装板/发射机口）。
    """

    kind: str = "data"
    category: str = "发送"
    name: str = ""
    type: str = ""
    param: str = ""
    count: int = 1
    interval_ms: int = 500
    port: str = "HPLC"
    data: str = ""
    command: str = ""
    note: str = ""
    enabled: bool = True
    # ---- 发射机数据报文（kind="data"）----
    ctrl2: int = 0x02           # 数据子类型（0x01/0x02/0x03/0x06/0x07/0x08）
    channel: int = 0x01         # 物理信道（0x01 HPLC / 0x02 RF / 0x03 RF+HPLC / 0x20 OFDMA / 0x10~0x1C MIMO）
    timestamp: int = 0          # 0=立即 0xFFFFFFFF=触发 其它=定时
    pb_count: int = 1           # 物理块个数
    pb_len: int = 0             # 单个物理块长度（0 = 按业务帧长度）
    crc_error: int = 0          # Payload 是否 CRC 错误（0x02/0x08）
    tmi: int = 0                # 0x08 UL-OFDMA
    ru: int = 0                 # 0x08 UL-OFDMA
    pad: int = 0                # 0x08 UL-OFDMA
    manual_data: bool = False   # True = data 已是完整数据域（0x06/0x07 等自由结构）
    # ---- 发射机控制报文（kind="command"）----
    tx_values: List[int] = field(default_factory=list)

    # -------------------------------------------------- 序列化
    def to_dict(self) -> Dict[str, object]:
        return {
            "kind": self.kind,
            "category": self.category,
            "name": self.name,
            "type": self.type,
            "param": self.param,
            "count": int(self.count),
            "interval_ms": int(self.interval_ms),
            "port": self.port,
            "data": self.data,
            "command": self.command,
            "note": self.note,
            "enabled": bool(self.enabled),
            "ctrl2": int(self.ctrl2),
            "channel": int(self.channel),
            "timestamp": int(self.timestamp),
            "pb_count": int(self.pb_count),
            "pb_len": int(self.pb_len),
            "crc_error": int(self.crc_error),
            "tmi": int(self.tmi),
            "ru": int(self.ru),
            "pad": int(self.pad),
            "manual_data": bool(self.manual_data),
            "tx_values": [int(v) for v in self.tx_values],
        }

    @classmethod
    def from_dict(cls, obj: Dict[str, object]) -> "Step":
        if not isinstance(obj, dict):
            raise ValueError("步骤必须是 JSON 对象")
        step = cls()
        step.kind = str(obj.get("kind", step.kind) or step.kind)
        if step.kind not in STEP_KINDS:
            step.kind = "data"
        step.category = str(obj.get("category", step.category) or "")
        step.name = str(obj.get("name", "") or "")
        step.type = str(obj.get("type", "") or "")
        step.param = str(obj.get("param", "") or "")
        try:
            step.count = max(0, int(obj.get("count", 1)))
        except (TypeError, ValueError):
            step.count = 1
        try:
            step.interval_ms = max(0, int(obj.get("interval_ms", 500)))
        except (TypeError, ValueError):
            step.interval_ms = 500
        step.port = str(obj.get("port", "HPLC") or "HPLC")
        step.data = str(obj.get("data", "") or "")
        step.command = str(obj.get("command", "") or "")
        step.note = str(obj.get("note", "") or "")
        step.enabled = bool(obj.get("enabled", True))
        step.ctrl2 = _safe_int(obj.get("ctrl2"), 0x02, 0x00, 0xFF)
        step.channel = _safe_int(obj.get("channel"), 0x01, 0x00, 0xFF)
        step.timestamp = _safe_int(obj.get("timestamp"), 0, 0, 0xFFFFFFFF)
        step.pb_count = _safe_int(obj.get("pb_count"), 1, 0, 0xFF)
        step.pb_len = _safe_int(obj.get("pb_len"), 0, 0, 0xFFFF)
        step.crc_error = _safe_int(obj.get("crc_error"), 0, 0, 1)
        step.tmi = _safe_int(obj.get("tmi"), 0, 0, 0xFF)
        step.ru = _safe_int(obj.get("ru"), 0, 0, 0xFF)
        step.pad = _safe_int(obj.get("pad"), 0, 0, 0xFF)
        step.manual_data = bool(obj.get("manual_data", False))
        raw_values = obj.get("tx_values") or []
        if isinstance(raw_values, list):
            # 范围取到 0xFFFFFFFF：控制报文字段里有 4 字节无符号（时间偏移/帧间隔），
            # 用 int32 夹紧会把 0xFFFFFFFF 静默改成 0x7FFFFFFF（实测踩过）
            step.tx_values = [_safe_int(v, 0, 0, 0xFFFFFFFF) for v in raw_values]
        return step

    # -------------------------------------------------- 展示
    def summary_type(self) -> str:
        if self.kind == "command":
            return tx_command_name(_parse_hex_code(self.command)) or "控制报文"
        if self.kind == "monitor":
            name = command_name(self.command)
            return f"监控器·{name}" if name else "监控器命令"
        if self.kind == "wait":
            return "等待"
        if self.kind == "raw":
            return "透传报文"
        name = tx_data_subtype_name(self.ctrl2)
        return self.type or name

    def summary_param(self) -> str:
        """「参数」列文案：只写人看的参数名，字节数放 tooltip（避免长文案撑高整行）。"""
        if self.kind == "wait":
            return f"{self.interval_ms} ms"
        if self.kind == "command":
            if self.param:
                return self.param
            ctrl2 = _parse_hex_code(self.command)
            definition = TX_COMMANDS.get(ctrl2)
            if definition is None:
                return ""
            # 把字段值按「名=值」拼出来，表格里能直接看出这条指令要下发什么
            parts: List[str] = []
            index = 0
            for spec in definition.fields:
                if spec.kind == "pad":
                    continue
                if index >= len(self.tx_values):
                    break
                value = self.tx_values[index]
                index += 1
                if spec.choices:
                    parts.append(f"{spec.choices.get(value, value)}")
                else:
                    parts.append(f"{spec.name}={value}")
            if definition.tail:
                parts.append(definition.tail.split("（")[0])
            return " · ".join(parts)
        if self.kind == "monitor":
            return self.param or ""
        if self.kind == "data" and not self.manual_data:
            return self.param or f"{phy_channel_name(self.channel)} · " \
                                 f"{self.pb_count} 块 · {_describe_timestamp(self.timestamp)}"
        return self.param or ""

    def summary_detail(self) -> str:
        """tooltip 明细：参数 + 字节数 + 备注。"""
        pieces: List[str] = []
        if self.param:
            pieces.append(self.param)
        if self.kind in ("data", "raw", "monitor"):
            try:
                pieces.append(f"{len(hex_to_bytes(self.data))} 字节")
            except ValueError:
                pieces.append("HEX 非法")
        if self.kind == "data" and not self.manual_data:
            pieces.append(f"子类型 0x{self.ctrl2:02X}")
            pieces.append(phy_channel_name(self.channel))
        if self.note:
            pieces.append(self.note)
        return " · ".join(pieces)


@dataclass
class Case:
    """一个用例文件 = 公共参数 + 有序步骤。"""

    name: str = ""
    description: str = ""
    params: Dict[str, object] = field(default_factory=dict)
    steps: List[Step] = field(default_factory=list)
    created: str = ""
    updated: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "format": CASE_FORMAT,
            "version": CASE_SCHEMA_VERSION,
            "name": self.name,
            "description": self.description,
            "created": self.created or now_text(),
            "updated": now_text(),
            "params": dict(self.params),
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, obj: Dict[str, object]) -> "Case":
        if not isinstance(obj, dict):
            raise ValueError("用例文件根节点必须是 JSON 对象")
        fmt = obj.get("format")
        if fmt not in (None, CASE_FORMAT):
            raise ValueError(f"不是收发机用例文件（format={fmt!r}）")
        version = obj.get("version")
        if version is not None and int(version) < CASE_SCHEMA_VERSION:
            raise ValueError(
                f"这是旧版（v{version}，96..16 发射机协议）用例文件，当前版本改用 "
                f"PLC2.0（ED..EE）发射机协议，旧用例不再适用；请重新建立用例"
                f"（业务帧内容可以直接沿用）。")
        raw_steps = obj.get("steps") or []
        if not isinstance(raw_steps, list):
            raise ValueError("steps 必须是数组")
        steps = [Step.from_dict(item) for item in raw_steps]
        params = obj.get("params")
        return cls(
            name=str(obj.get("name", "") or ""),
            description=str(obj.get("description", "") or ""),
            params=dict(params) if isinstance(params, dict) else {},
            steps=steps,
            created=str(obj.get("created", "") or ""),
            updated=str(obj.get("updated", "") or ""),
        )


def validate_case(case: Case) -> Tuple[List[str], List[str]]:
    """校验用例；返回 ``(errors, warnings)``。errors 非空表示不可保存/不可执行。"""
    errors: List[str] = []
    warnings: List[str] = []

    name_err = validate_case_name(case.name)
    if name_err:
        errors.append(name_err)
    if not case.steps:
        errors.append("用例没有任何步骤")
    if len(case.steps) > MAX_CASE_STEPS:
        errors.append(f"步骤过多（{len(case.steps)} > {MAX_CASE_STEPS}）")

    for idx, step in enumerate(case.steps, 1):
        prefix = f"第 {idx} 步"
        if step.kind == "data":
            if not step.data.strip():
                errors.append(f"{prefix}：业务帧内容为空")
                continue
            try:
                payload = hex_to_bytes(step.data)
            except ValueError as exc:
                errors.append(f"{prefix}：HEX 非法（{exc}）")
                continue
            if not payload:
                errors.append(f"{prefix}：业务帧内容为空")
                continue
            if step.manual_data:
                if len(payload) > MAX_TX_DATA_LEN:
                    errors.append(f"{prefix}：数据域过长（{len(payload)} > "
                                  f"{MAX_TX_DATA_LEN} 字节）")
            elif step.ctrl2 in TX_STRUCTURED_SUBTYPES:
                if len(payload) > MAX_TX_DATA_LEN - 9:
                    errors.append(f"{prefix}：业务帧过长（{len(payload)} 字节）")
                if step.ctrl2 not in TX_DATA_SUBTYPES:
                    errors.append(f"{prefix}：未知数据子类型 0x{step.ctrl2:02X}")
                if not 0 <= int(step.timestamp) <= 0xFFFFFFFF:
                    errors.append(f"{prefix}：时间戳超出 4 字节范围")
            else:
                errors.append(
                    f"{prefix}：子类型 0x{step.ctrl2:02X} 结构自由，必须勾选「手工数据域」")
            if step.count < 1:
                warnings.append(f"{prefix}：发送次数为 0，执行时会被跳过")
        elif step.kind == "command":
            ctrl2 = _parse_hex_code(step.command)
            definition = TX_COMMANDS.get(ctrl2)
            if definition is None:
                errors.append(f"{prefix}：未选择控制指令")
            elif not definition.sendable:
                errors.append(f"{prefix}：{definition.name} 是设备上报指令，不能下发")
            else:
                tail = b""
                if definition.tail:
                    try:
                        tail = hex_to_bytes(step.data)
                    except ValueError as exc:
                        errors.append(f"{prefix}：{definition.tail} HEX 非法（{exc}）")
                        tail = b""
                payload = tx_command_payload(ctrl2, step.tx_values, tail)
                if not payload.ok:
                    errors.append(f"{prefix}：{payload.error}")
                if len(payload.payload) > MAX_TX_DATA_LEN:
                    errors.append(f"{prefix}：控制报文数据域过长")
        elif step.kind == "monitor":
            cmd = parse_command_ref(step.command)
            if cmd is None:
                errors.append(f"{prefix}：未选择监控器命令")
            else:
                cmd_id, rw = cmd
                definition = COMMANDS.get(cmd_id)
                if definition is None:
                    errors.append(f"{prefix}：未知命令 0x{cmd_id:02X}")
                else:
                    if rw and not definition.settable:
                        errors.append(f"{prefix}：{definition.name} 不支持设置（仅查询）")
                    payload = command_payload_from_text(cmd_id, rw, step.data)
                    if not payload.ok:
                        errors.append(f"{prefix}：{payload.error}")
        elif step.kind == "wait":
            if step.interval_ms < 0:
                errors.append(f"{prefix}：等待时长不能为负")
        elif step.kind == "raw":
            try:
                if not hex_to_bytes(step.data):
                    errors.append(f"{prefix}：透传报文内容为空")
            except ValueError as exc:
                errors.append(f"{prefix}：HEX 非法（{exc}）")
        if step.interval_ms < 0:
            errors.append(f"{prefix}：发送间隔不能为负")
    return errors, warnings


# ---------------------------------------------------------------- 命令引用

def command_ref(cmd_id: int, rw: int) -> str:
    """命令引用字符串：``"07:1"``（命令号:读写）。"""
    return f"{int(cmd_id):02X}:{1 if rw else 0}"


def parse_command_ref(text: str) -> Optional[Tuple[int, int]]:
    """解析命令引用；非法返回 None。兼容 ``"07:1"`` / ``"07"`` / ``"07:set"``。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    rw = 1
    if ":" in raw:
        head, tail = raw.split(":", 1)
        raw = head.strip()
        tail = tail.strip().lower()
        rw = 0 if tail in ("0", "query", "read", "q", "查询") else 1
    try:
        cmd_id = int(raw, 16)
    except ValueError:
        return None
    if cmd_id not in COMMANDS:
        return None
    if rw and not COMMANDS[cmd_id].settable:
        rw = 0
    return cmd_id, rw


def command_name(ref: str) -> str:
    parsed = parse_command_ref(ref)
    if parsed is None:
        return ""
    cmd_id, rw = parsed
    definition = COMMANDS[cmd_id]
    verb = "设置" if rw else "查询"
    # 命令名本身已含「设置/查询」，避免出现「查询查询版本」
    return f"{definition.name}" if definition.name.startswith(verb) else f"{verb}{definition.name}"


def command_payload_from_text(cmd_id: int, rw: int, text: str) -> "CommandPayload":
    """把用例里存的**命令数据域 HEX**（``"02 48 00"``）还原成字节并校验长度。

    页面里命令字段是结构化控件（见 :data:`COMMAND_FIELD_SPECS`），组好的 HEX 才写进
    用例文件，所以这里只认 HEX —— 不再「数字序列 / HEX 两义解析」，
    避免 ``"10 4"`` 到底是 ``0x10 0x04`` 还是 ``10, 4`` 这种歧义（现场最容易踩的一类坑）。
    """
    cmd = COMMANDS.get(cmd_id)
    if cmd is None:
        return CommandPayload(False, b"", f"未知命令 0x{cmd_id:02X}")
    if not rw:
        return CommandPayload(True, b"", "")
    need = cmd.set_len
    text = str(text or "").strip()
    if not text:
        if need == 0:
            return CommandPayload(True, b"", "")
        return CommandPayload(False, b"", f"{cmd.name} 需要 {need} 字节数据")
    try:
        payload = hex_to_bytes(text)
    except ValueError as exc:
        return CommandPayload(False, b"", f"命令数据 HEX 非法（{exc}）")
    if len(payload) != need:
        return CommandPayload(False, payload,
                              f"{cmd.name} 需要 {need} 字节数据，实际 {len(payload)} 字节")
    return CommandPayload(True, payload, "")


@dataclass
class CommandPayload:
    ok: bool
    payload: bytes
    error: str = ""


def build_step_command(step: Step) -> "CommandPayload":
    """按步骤里的命令引用组命令帧；返回 :class:`CommandPayload`（payload=完整帧）。"""
    parsed = parse_command_ref(step.command)
    if parsed is None:
        return CommandPayload(False, b"", "步骤未选择设备命令")
    cmd_id, rw = parsed
    payload = command_payload_from_text(cmd_id, rw, step.data)
    if not payload.ok:
        return payload
    return CommandPayload(True, build_command_frame(cmd_id, rw, payload.payload), "")


def build_step_data_frame(step: Step, cs_mode: str = "sum") -> bytes:
    """按步骤组**发射机**数据报文（ED..EE）；HEX 非法会抛 ``ValueError``。

    - ``manual_data=True``：``data`` 已是完整数据域，直接封 ED..EE；
    - 否则按 :data:`TX_STRUCTURED_SUBTYPES` 自动拼公共头 + 业务帧。
    """
    payload = hex_to_bytes(step.data)
    if step.manual_data:
        data = payload
    else:
        data = build_tx_data_payload(
            step.ctrl2, payload=payload, channel=step.channel,
            timestamp=step.timestamp, pb_count=step.pb_count,
            pb_len=step.pb_len, crc_error=step.crc_error,
            tmi=step.tmi, ru=step.ru, pad=step.pad)
    return build_tx_frame(CTRL1_DATA, step.ctrl2, data, cs_mode=cs_mode)


def build_step_tx_command(step: Step, cs_mode: str = "sum") -> "CommandPayload":
    """按步骤组**发射机**控制报文（ED..EE 控制域1=0x01）。"""
    ctrl2 = _parse_hex_code(step.command)
    definition = TX_COMMANDS.get(ctrl2)
    if definition is None:
        return CommandPayload(False, b"", "步骤未选择控制指令")
    tail = b""
    if definition.tail:
        try:
            tail = hex_to_bytes(step.data)
        except ValueError as exc:
            return CommandPayload(False, b"", f"{definition.tail} HEX 非法（{exc}）")
    payload = tx_command_payload(ctrl2, step.tx_values, tail)
    if not payload.ok:
        return payload
    return CommandPayload(True,
                          build_tx_frame(CTRL1_CONTROL, ctrl2, payload.payload,
                                         cs_mode=cs_mode), "")


# ---------------------------------------------------------------- 文件读写

def case_path(name: str) -> Path:
    return case_dir() / (normalize_name(name) + CASE_SUFFIX)


def load_case(path) -> Case:
    """读取用例文件；格式错误抛 ``ValueError``（调用方负责提示）。"""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"读取失败：{exc}") from exc
    try:
        obj = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"JSON 解析失败：{exc}") from exc
    case = Case.from_dict(obj)
    if not case.name:
        case.name = file_path.stem
    return case


def save_case(case: Case, path=None, *, create_only: bool = False) -> Path:
    """保存用例（原子写）；返回落盘路径。

    ``create_only=True`` 时目标已存在直接抛 ``ValueError``（新建重名保护）。
    """
    from atomic_io import atomic_write_json

    name_err = validate_case_name(case.name)
    if name_err:
        raise ValueError(name_err)
    target = Path(path) if path else case_path(case.name)
    if create_only and target.exists():
        raise ValueError(f"用例「{case.name}」已存在")
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target, case.to_dict())
    return target


def delete_case(path) -> None:
    Path(path).unlink()


def list_cases() -> List[Dict[str, object]]:
    """列出用例目录下的用例：``[{name, path, steps, error}, ...]``（按名称排序）。

    单个坏文件只标记 ``error``，不影响其它用例加载。
    """
    out: List[Dict[str, object]] = []
    folder = case_dir()
    if not folder.exists():
        return out
    for file_path in sorted(folder.glob("*" + CASE_SUFFIX), key=lambda p: p.name.lower()):
        item: Dict[str, object] = {
            "name": file_path.stem, "path": file_path, "steps": 0, "error": "",
        }
        try:
            case = load_case(file_path)
            item["name"] = case.name or file_path.stem
            item["steps"] = len(case.steps)
            item["case"] = case
        except ValueError as exc:
            item["error"] = str(exc)
        out.append(item)
    return out


# ---------------------------------------------------------------- 页面配置

DEFAULT_SETTINGS = {
    "tx_port": "",
    "tx_baud": 921600,
    "tx_parity": "无",
    "rx_port": "",
    "rx_baud": 921600,
    "rx_parity": "无",
    "fixture_port": "",
    "fixture_baud": 921600,
    # ---- 发射机（PLC2.0）默认参数 ----
    "tx_ctrl2": 0x02,          # 数据子类型：FC+Payload
    "tx_channel": 0x01,        # 物理信道：HPLC
    "tx_timestamp": 0,         # 0 = 立即发送
    "tx_pb_count": 1,
    "tx_pb_len": 0,            # 0 = 按业务帧长度
    "tx_crc_mode": "sum",      # sum | xff
    "tx_band": 2,              # 频段 TAG
    "tx_phase": 1,             # 通讯相线 A
    "tx_phy_mode": 1,          # 进入特定物理信道：HPLC
    "tx_sfo": 1,
    "tx_sync": 1,
    "tx_fill_crc": 1,
    "tx_tonemask": 0,
    "tx_rf_index": 0,
    "tx_rf_option": 2,
    # ---- 接收机（监控器，68..16 配置）默认参数 ----
    "monitor_band": 2,
    "monitor_snid": 0,
    # ---- 运行参数 ----
    "count": 10,
    "interval_ms": 500,
    "duration_min": 180,
    "last_case": "",
    # ---- 界面折叠状态 {区 key: 是否展开}（1.26.26：公共参数区做成折叠窗口）----
    "sections": {},
}


def load_settings() -> Dict[str, object]:
    from atomic_io import read_json

    data = read_json(settings_path(), {}) or {}
    merged = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
    return merged


def save_settings(values: Dict[str, object]) -> None:
    from atomic_io import atomic_write_json

    payload = {k: values.get(k, v) for k, v in DEFAULT_SETTINGS.items()}
    atomic_write_json(settings_path(), payload)


# ======================================================================
# 六、执行计划（把用例展开成「到点该发什么」的线性序列）
# ======================================================================

@dataclass
class Action:
    """执行计划里的一次动作。"""

    step_index: int      # 用例里的步骤序号（1 起）
    step: Step
    repeat: int          # 第几次（1 起）
    repeat_total: int
    action: str          # send_data / send_cmd / send_raw / wait
    payload: bytes = b""
    delay_ms: int = 0    # 执行完本动作后等待多久再执行下一个
    error: str = ""


def plan_actions(case: Case, *, default_count: int = 1,
                 default_interval_ms: int = 500,
                 cs_mode: str = "sum") -> Tuple[List[Action], List[str]]:
    """把用例展开成线性动作列表。

    - 步骤的 ``count`` 为 0 时用 ``default_count``（顶栏「发送次数」）；
    - 步骤的 ``interval_ms`` 为 0 时用 ``default_interval_ms``；
    - ``wait`` 步骤直接产出 delay，不产生报文；
    - 组装失败的步骤产出 ``error``（执行时跳过并记日志），不中断整条流程的展开。

    动作类型：``send_tx_data``（发射机数据报文）/ ``send_tx_cmd``（发射机控制报文）/
    ``send_monitor``（监控器命令，发往接收机口）/ ``send_raw``（透传）/ ``wait``。
    """
    actions: List[Action] = []
    errors: List[str] = []
    for idx, step in enumerate(case.steps, 1):
        if not step.enabled:
            continue
        if step.kind == "wait":
            delay = step.interval_ms if step.interval_ms > 0 else default_interval_ms
            actions.append(Action(idx, step, 1, 1, "wait", b"", int(delay)))
            continue
        total = step.count if step.count > 0 else max(1, int(default_count))
        interval = step.interval_ms if step.interval_ms > 0 else int(default_interval_ms)
        for repeat in range(1, total + 1):
            action = Action(idx, step, repeat, total, "send_tx_data", b"", interval)
            try:
                if step.kind == "data":
                    action.payload = build_step_data_frame(step, cs_mode=cs_mode)
                elif step.kind == "command":
                    built = build_step_tx_command(step, cs_mode=cs_mode)
                    if not built.ok:
                        action.error = built.error
                    else:
                        action.action = "send_tx_cmd"
                        action.payload = built.payload
                elif step.kind == "monitor":
                    built = build_step_command(step)
                    if not built.ok:
                        action.error = built.error
                    else:
                        action.action = "send_monitor"
                        action.payload = built.payload
                elif step.kind == "raw":
                    action.action = "send_raw"
                    action.payload = hex_to_bytes(step.data)
                else:
                    action.error = f"未知步骤类型 {step.kind!r}"
            except ValueError as exc:
                action.error = str(exc)
            if action.error:
                errors.append(f"第 {idx} 步：{action.error}")
            actions.append(action)
    return actions, errors
