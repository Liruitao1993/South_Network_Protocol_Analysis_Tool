# -*- coding: utf-8 -*-
"""新一代载波协议（协议9 / 通感一体化）应用层组帧器。

设计原则：本模块是 ``csg_new_gen_parser`` + ``csg_new_gen_cmd_payloads`` 的**逆运算**，
字段顺序、端序、位域取值与解析侧逐一对应（解析侧 ``_bits()`` 与本模块 ``pack_bits()`` 严格对称），
因此可用「编码 → 现有解析器回读 → 断言字段相等」做防漂移对拍（见 test/test_csg_new_gen_frame_gen.py）。

四层结构（由内向外）：

    第1层 测试帧业务数据单元（BDU）  业务标识 = 0xF0
          测试ID(1B) | 保留(1B) | 数据区长度(2B,LE) | 测试数据区
          测试数据区：0x00/0x01/0x02 → 通信频段(1B)｜0x03 → 表61 六字节头｜
                      0x04 → 协商版本号(1B)+文件长度(1B)+扩展ID(2B,LE)+扩展数据
    第2层 业务报文头
          控制域(2B,LE) | 业务标识(1B) | 应用版本号(1B) | 帧序号(2B,LE) | 帧长(2B,LE) | 数据单元 | [扩展域]
          —— 控制域位域：D15 方向 / D14 PRM / D13 响应 / D12 业务扩展域 / D11-D8 优先级 / D3-D0 帧类型
    第3层 应用层帧
          报文端口号(1B) | 报文标识符(2B,LE) | 保留(1B) | 业务报文
    第4层 ED 封装（PLC2.0 收发机报文格式，上位机↔收发机/测试装置）
          ED(1) | 帧长(2,LE) | 控制域1(1) | 控制域2(1) | EF(1) | 数据域 | CS(1) | EE(1)
          帧长 = 控制域1+控制域2+EF+数据域+CS 的字节数
          数据域公共头：plc2 = 物理信道(1)+时间戳(4,LE)+物理块个数(1)+保留(1)+物理块长度(2,LE)
                        gx   = 时间戳(4,LE)+物理信道(1)+物理块个数(1)+物理块长度(2,LE)

依据文档（本仓 ``南网新一代20260226校对/``）：
- 《宽带双模通信模块（通感一体物联版）相关测试命令定义_增加相关接口》
- 《PLC2.0收发机报文格式0629》

待补资料处（当前留可填参数 + 合理默认，不阻塞组帧）：
- 表61「转发数据的规约类型」取值表（默认 0）
- 表61「报文头长度」取值（默认 6，即 6 字节头自身）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# ────────────────────────────── 常量（与解析侧同名同值） ──────────────────────────────

# 报文端口号（csg_new_gen_parser.MSG_PORT_MAP）
MSG_PORT_BUSINESS = 0x11  # 业务报文(转发)
MSG_PORT_MANAGE = 0x13  # 管理报文(模块)

# 报文标识符（csg_new_gen_parser.MSG_ID_MAP）
MSG_ID_CCO_STA = 0x0101  # CCO-STA应用层报文

# 帧类型域（控制域 D3~D0，csg_new_gen_parser.FRAME_TYPE_MAP）
FRAME_TYPE_CONFIRM = 0x0  # 确认/否认
FRAME_TYPE_DATA = 0x1  # 数据传输帧
FRAME_TYPE_CMD = 0x2  # 命令帧
FRAME_TYPE_REPORT = 0x3  # 主动上报帧
FRAME_TYPE_BROADCAST = 0x5  # 广播命令帧
FRAME_TYPE_DEBUG = 0xE  # 厂家调试

# 测试帧业务标识（csg_new_gen_parser.CMD_COMM_SERVICE_MAP）
SERVICE_TEST_FRAME = 0xF0

# 测试 ID（csg_new_gen_cmd_payloads._TEST_ID_MAP / 文档表1）
TEST_ID_MAP: Dict[int, str] = {
    0x00: "进入回环测试模式",
    0x01: "进入透明转发模式",
    0x02: "频段切换命令",
    0x03: "1.0测试",
    0x04: "2.0测试",
}

# 2.0 测试扩展 ID（csg_new_gen_cmd_payloads._TEST_EXT_ID_MAP）
TEST_EXT_ID_MAP: Dict[int, str] = {
    0x0001: "Bitloading测试模式",
    0x0002: "Bitloading表下发",
    0x0003: "空间映射测试模式",
    0x0004: "OFDMA测试模式",
    0x0005: "OFDMA多用户下发",
    0x0006: "MAC层OFDMA配置",
    0x0007: "非组网场景TEI配置",
    0x0008: "业务报文Bitloading收发开关",
    0x0009: "报文聚合传输测试模式",
}

# 表61「测试模式/配置操作」取值（文档第 2 章 1~13 条）
LEGACY_TEST_MODE_MAP: Dict[int, str] = {
    1: "转发应用层报文至应用层串口信道（暂未使用）",
    2: "转发应用层报文至载波信道（暂未使用）",
    3: "PLC物理层透传测试模式",
    4: "PLC物理层回传测试模式",
    5: "MAC层透传测试模式",
    6: "频段切换操作",
    7: "ToneMask配置操作（暂未使用）",
    8: "无线信道切换操作（暂未使用）",
    9: "RF物理层回传测试模式",
    10: "RF物理层透传测试模式",
    11: "RF/PLC物理层回传测试模式",
    12: "PLC到RF物理层回传测试模式",
    13: "安全测试模式（暂未使用）",
}

# 通信频段含义（文档 1.6 第 6 条；完整表待《第4部分 物理层》4.1.7.5）
BAND_MAP: Dict[int, str] = {
    0: "通信频段0：1.953~11.96MHz",
    1: "通信频段1：2.441~5.615MHz",
    2: "通信频段2：0.781~2.930MHz",
}

# Bitloading 表承载映射（解析侧 _BIT_MOD_MAP）
BIT_MOD_MAP: Dict[int, str] = {0: "不加载", 1: "BPSK", 2: "QPSK", 4: "16QAM", 6: "64QAM"}

# OFDMA 多用户下发帧类型（解析侧 _OFDMA_FRAME_TYPE_MAP）
OFDMA_FRAME_TYPE_MAP: Dict[int, str] = {
    0: "DL_OFDMA（立即发送）",
    1: "UL_OFDMA（等待触发发送）",
    2: "UL_OFDMA的trigger（立即发送）",
    3: "保留",
}

# ED 封装常用物理块尺寸（csg_new_gen_parser._ED_PB_SIZES）
ED_PB_SIZES: Sequence[int] = (16, 40, 72, 136, 264, 520)

# 物理信道（PLC2.0 收发机报文格式）
PHYSICAL_CHANNEL_MAP: Dict[int, str] = {
    0x01: "HPLC",
    0x02: "RF",
    0x03: "HPLC+RF",
    0x20: "PLC2.0 OFDMA",
}


class FrameBuildError(ValueError):
    """组帧参数非法。"""


# ────────────────────────────── 基础工具 ──────────────────────────────


def u16le(value: int) -> bytes:
    """2 字节小端。"""
    return int(value & 0xFFFF).to_bytes(2, "little")


def u32le(value: int) -> bytes:
    """4 字节小端。"""
    return int(value & 0xFFFFFFFF).to_bytes(4, "little")


def pack_bits(total_bits: int, fields: Sequence[Tuple[int, int, int]]) -> bytes:
    """位域打包，与解析侧 ``_bits(data, offset, bit_start, bit_width)`` 严格对称。

    fields: (bit_start, bit_width, value) 序列，bit_start 为整体小端整数中的起始位。
    返回 ``ceil(total_bits/8)`` 字节的小端字节串。
    """
    packed = 0
    for bit_start, bit_width, value in fields:
        if bit_width <= 0:
            continue
        mask = (1 << bit_width) - 1
        if value < 0 or value > mask:
            raise FrameBuildError(f"位域取值越界：{bit_width}bit 域放不下 {value}")
        packed |= (int(value) & mask) << bit_start
    if packed >= (1 << total_bits):
        raise FrameBuildError(f"位域总和越过 {total_bits}bit 容器")
    return packed.to_bytes((total_bits + 7) // 8, "little")


def _clip_count(value: int, name: str, maximum: int) -> int:
    if not isinstance(value, int):
        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise FrameBuildError(f"{name} 必须是整数，得到 {value!r}") from exc
    if value < 0 or value > maximum:
        raise FrameBuildError(f"{name} 超出范围：{value}（允许 0~{maximum}）")
    return value


# ────────────────────────────── 第1层：测试帧 BDU ──────────────────────────────


def build_legacy_test_mode_value(mode: int, value: int) -> int:
    """表61「测试模式/配置操作」与其配置值/持续时间的取值校验。

    文档 1~13 条里：
      - 1/2 模式值固定填 0（转发一帧后退出）
      - 3/4/5/9/10/11/12/13 的配置值是**测试模式持续时间（分钟）**
      - 6 的配置值是目标**频段值**、7 是 ToneMask 值、8 是 Option+信道号
    取值范围统一为 12bit（0~4095）。
    """
    if mode not in LEGACY_TEST_MODE_MAP:
        raise FrameBuildError(f"未知的表61测试模式取值：{mode}（允许 {sorted(LEGACY_TEST_MODE_MAP)}）")
    if mode in (1, 2) and value not in (0, None):
        raise FrameBuildError(f"表61 模式 {mode} 按文档配置值须填 0")
    return _clip_count(value or 0, "测试模式持续时间/配置值", 0xFFF)


def build_test_pdu_band(test_id: int, band: int) -> bytes:
    """测试ID 0x00/0x01/0x02：1 字节，D0-D3 通信频段，D4-D7 保留（文档表2/3/4）。"""
    if test_id not in (0x00, 0x01, 0x02):
        raise FrameBuildError(f"该测试ID 不使用单字节频段格式：0x{test_id:02X}")
    return pack_bits(8, [(0, 4, _clip_count(band, "通信频段", 0xF))])


def build_legacy_test_pdu(
    *,
    mode: int,
    value: int = 0,
    proto_version: int = 1,
    header_len: int = 6,
    header_len_layout: str = "doc",
    protocol_type: int = 0,
    security_mode: int = 0,
    phr_mcs: int = 0,
    psdu_mcs: int = 0,
    pb_size: int = 0,
    forward_data: bytes = b"",
) -> bytes:
    """表61「原有扩展命令格式」6 字节头（+ 可选转发数据）——即 1.0 测试的测试数据区。

    字节0: 协议版本号(6bit, bit0-5) | 报文头长度高2位(bit6-7)
    字节1: 报文头长度低4位(bit0-3) | 测试模式/配置操作(4bit, bit4-7)
    字节2: 转发数据的规约类型(4bit, bit0-3) | 持续时间/配置值高4位(bit4-7)
    字节3: 持续时间/配置值低8位
    字节4: 安全测试模式(4bit, bit0-3) | PHR_MCS(4bit, bit4-7)
    字节5: PSDU_MCS(4bit, bit0-3) | PbSIZE(4bit, bit4-7)

    ``header_len_layout`` 处理「文档表61」与「现有解析器」的口径差异：
    - ``"doc"``（默认，按文档表61）：报文头长度按 6bit 跨字节写 —— 字节0 bit6-7 是高 2 位、字节1 bit0-3 是低 4 位；
    - ``"parser"``：只写字节0 bit6-7（取值 ≤3），字节1 低 4 位留 0，
      与 ``csg_new_gen_cmd_payloads._parse_legacy_ext_cmd``（仅读 bit6-7）读回一致。
    """
    resolved_value = build_legacy_test_mode_value(mode, value)
    header_len = _clip_count(header_len, "报文头长度", 0x3F)
    if header_len_layout == "doc":
        head_len_fields = [(6, 2, (header_len >> 4) & 0x03), (8, 4, header_len & 0x0F)]
    elif header_len_layout == "parser":
        head_len_fields = [(6, 2, header_len & 0x03), (8, 4, 0)]
    else:
        raise FrameBuildError(f"未知报文头长度布局：{header_len_layout!r}（允许 doc / parser）")
    head = pack_bits(
        48,
        [
            (0, 6, _clip_count(proto_version, "协议版本号", 0x3F)),
            *head_len_fields,
            (12, 4, mode),
            (16, 4, _clip_count(protocol_type, "转发数据的规约类型", 0x0F)),
            (20, 4, (resolved_value >> 8) & 0x0F),
            (24, 8, resolved_value & 0xFF),
            (32, 4, _clip_count(security_mode, "安全测试模式", 0x0F)),
            (36, 4, _clip_count(phr_mcs, "PHR_MCS", 0x0F)),
            (40, 4, _clip_count(psdu_mcs, "PSDU_MCS", 0x0F)),
            (44, 4, _clip_count(pb_size, "PbSIZE", 0x0F)),
        ],
    )
    return head + bytes(forward_data or b"")


def build_ext_0001() -> bytes:
    """Bitloading 测试模式：无扩展数据（文档 1.6.1）。"""
    return b""


def build_ext_0002(
    *,
    src_tei: int = 0,
    dst_tei: int = 0,
    stream_count: int = 1,
    subcarrier_group: int = 1,
    cutoff_carrier: int = 0,
    bps: int = 0,
    bit_table: bytes = b"",
) -> bytes:
    """Bitloading 表下发（文档表6；解析侧 _parse_test_ext_0002，小端）。

    源TEI(2) | 目的TEI(2) | 流数(1) | 子载波分组大小(1) | 截止子载波(2) | 比特加载表长度(2) | Bps(2) | B表(n)
    比特加载表长度由 ``bit_table`` 实际长度自动写入。
    """
    table = bytes(bit_table or b"")
    stream_count = _clip_count(stream_count, "流数", 0xFF)
    if stream_count not in (1, 2):
        raise FrameBuildError(f"流数只允许 1（1流）或 2（2流），得到 {stream_count}")
    block = 3 if stream_count == 1 else 6
    if table and len(table) % block != 0:
        raise FrameBuildError(
            f"B表长度须是 {block} 的整数倍（{'单' if stream_count == 1 else '双'}流 8 组/块），得到 {len(table)}"
        )
    head = (
        u16le(_clip_count(src_tei, "源TEI", 0xFFF))
        + u16le(_clip_count(dst_tei, "目的TEI", 0xFFF))
        + bytes([stream_count])
        + bytes([_clip_count(subcarrier_group, "子载波分组大小", 0xFF)])
        + u16le(_clip_count(cutoff_carrier, "截止子载波", 0xFFFF))
        + u16le(len(table))
        + u16le(_clip_count(bps, "Bps", 0xFFFF))
    )
    return head + table


def build_ext_0003(*, mapping_mode: int = 0) -> bytes:
    """空间映射测试模式：映射模式(1B)（文档 1.6.3；解析侧 _parse_test_ext_0003）。"""
    return bytes([_clip_count(mapping_mode, "映射模式", 0xFF)])


def build_ext_0004() -> bytes:
    """OFDMA 测试模式：无扩展数据（文档 1.6.4）。"""
    return b""


def build_ext_0005(*, frame_type: int = 0, fc: bytes = b"", efc: bytes = b"", efc_required: Optional[bool] = None) -> bytes:
    """OFDMA 多用户下发（文档 1.6.5；解析侧 _parse_test_ext_0005）。

    字节3: 帧类型(2bit, bit0-1) + 保留(6bit)
    字节4-19: FC域 16 字节（定界符3bit + 接入指示1bit + SNID低4bit + 可变域12B + FCS 3B 由调用方给出）
    字节20-35: eFC域 16 字节（帧类型 1 时无）
    """
    frame_type = _clip_count(frame_type, "OFDMA帧类型", 0x3)
    if efc_required is None:
        efc_required = frame_type != 1
    fc = bytes(fc or b"")
    efc = bytes(efc or b"")
    if fc and len(fc) != 16:
        raise FrameBuildError(f"FC 域须为 16 字节，得到 {len(fc)}")
    if efc and len(efc) != 16:
        raise FrameBuildError(f"eFC 域须为 16 字节，得到 {len(efc)}")
    if not fc:
        fc = bytes(16)
    if efc_required and not efc:
        efc = bytes(16)
    body = pack_bits(8, [(0, 2, frame_type)]) + fc
    if efc_required:
        body += efc
    return body


def build_ext_0006(*, ofdma_type: int = 0, node_count: int = 0) -> bytes:
    """MAC 层 OFDMA 配置（文档 1.6.6；解析侧 _parse_test_ext_0006）。

    bit0 = OFDMA类型(0:DL 1:UL)，bit1-3 = 调度节点数，bit4-7 = 保留
    """
    return pack_bits(
        8,
        [
            (0, 1, _clip_count(ofdma_type, "OFDMA类型", 0x1)),
            (1, 3, _clip_count(node_count, "OFDMA调度节点数", 0x7)),
        ],
    )


def build_ext_0007(*, tei: int = 0) -> bytes:
    """非组网场景 TEI 配置（文档 1.6.7；解析侧 _parse_test_ext_0007）。

    TEI 12bit 小端：低8位在前，高4位在后一字节低4位，高4位保留。
    """
    tei = _clip_count(tei, "TEI", 0xFFF)
    return bytes([tei & 0xFF]) + bytes([(tei >> 8) & 0x0F])


def build_ext_0008(*, enable: int = 1) -> bytes:
    """业务报文 Bitloading 收发开关（文档 1.6.8；解析侧 _parse_test_ext_0008）。

    bit0 = 1 使用 Bitloading / 0 退出；bit1-7 保留
    """
    return pack_bits(8, [(0, 1, _clip_count(enable, "Bitloading开关", 0x1))])


def build_ext_0009(*, agg_count: int = 1) -> bytes:
    """报文聚合传输测试模式（文档 1.4.9；解析侧 _parse_test_ext_0009）。

    字节3: 报文聚合数目(8bit) —— 要求聚合发送的MAC帧个数。
    文档未规定默认值；默认 1 = 聚合 1 个 MAC 帧（等价于不聚合）。
    """
    return bytes([_clip_count(agg_count, "报文聚合数目", 0xFF)])


_EXT_BUILDERS = {
    0x0001: build_ext_0001,
    0x0002: build_ext_0002,
    0x0003: build_ext_0003,
    0x0004: build_ext_0004,
    0x0005: build_ext_0005,
    0x0006: build_ext_0006,
    0x0007: build_ext_0007,
    0x0008: build_ext_0008,
    0x0009: build_ext_0009,
}


def build_test_pdu(test_id: int, *, reserved: int = 0, **kwargs) -> bytes:
    """第1层：测试帧业务数据单元（业务标识 0xF0 的数据单元）。

    与解析侧 ``csg_new_gen_cmd_payloads._parse_cmd_test_frame`` 严格对应：

        测试ID(1B) | 保留(1B) | 数据区长度(2B,LE) | 测试数据区

    测试数据区按测试ID 分派（数据区长度由实际内容自动写入）：
    - 0x00/0x01/0x02 回环 / 透明转发 / 频段切换 → 1 字节通信频段（参数 ``band``）
    - 0x03 1.0 测试 → 表61 原有扩展命令格式（参数见 :func:`build_legacy_test_pdu`）
    - 0x04 2.0 测试 → 协商版本号(1B) + 文件长度(1B) + 扩展ID(2B,LE) + 扩展数据
      （参数 ``ext_id`` 与对应扩展字段；``neg_version`` / ``file_len`` 可选，默认 0 / 扩展数据长度）
    """
    if test_id in (0x00, 0x01, 0x02):
        data = build_test_pdu_band(test_id, kwargs.get("band", 0))
    elif test_id == 0x03:
        legacy_keys = (
            "mode",
            "value",
            "proto_version",
            "header_len",
            "header_len_layout",
            "protocol_type",
            "security_mode",
            "phr_mcs",
            "psdu_mcs",
            "pb_size",
            "forward_data",
        )
        legacy_args = {key: kwargs[key] for key in legacy_keys if key in kwargs}
        if "mode" not in legacy_args:
            raise FrameBuildError("1.0 测试（test_id=0x03）必须给出表61 测试模式号 mode")
        data = build_legacy_test_pdu(**legacy_args)
    elif test_id == 0x04:
        ext_id = kwargs.get("ext_id")
        if ext_id is None:
            raise FrameBuildError("2.0 测试（test_id=0x04）必须给出扩展ID ext_id")
        builder = _EXT_BUILDERS.get(ext_id)
        if builder is None:
            raise FrameBuildError(f"未知扩展ID：0x{ext_id:04X}（允许 {[f'0x{k:04X}' for k in sorted(_EXT_BUILDERS)]}）")
        ext_args = {k: v for k, v in kwargs.items() if k not in ("ext_id", "neg_version", "file_len")}
        ext_data = builder(**ext_args)
        neg_version = _clip_count(kwargs.get("neg_version", 0), "协商版本号", 0xFF)
        file_len = _clip_count(kwargs.get("file_len", len(ext_data)), "文件长度", 0xFF)
        data = bytes([neg_version, file_len]) + u16le(ext_id) + ext_data
    else:
        raise FrameBuildError(f"未知测试ID：0x{test_id:02X}（允许 {[f'0x{k:02X}' for k in sorted(TEST_ID_MAP)]}）")
    if len(data) > 0xFFFF:
        raise FrameBuildError(f"测试数据区过长：{len(data)} 字节（上限 65535）")
    return bytes([_clip_count(test_id, "测试ID", 0xFF), _clip_count(reserved, "保留", 0xFF)]) + u16le(len(data)) + data


def build_ext_pdu(ext_id: int, **kwargs) -> bytes:
    """便捷入口：按扩展ID 组 2.0 测试的**测试数据区**（不含测试ID/保留/数据区长度三字段）。"""
    return build_test_pdu(0x04, ext_id=ext_id, **kwargs)[4:]


# ────────────────────────── 第2层：业务报文头 ──────────────────────────


@dataclass
class BusinessHeader:
    """业务报文头字段（默认值取"下行 CCO→STA 命令帧"口径）。"""

    frame_type: int = FRAME_TYPE_CMD
    direction: int = 0  # D15: 0 下行(CCO→STA) / 1 上行
    prm: int = 1  # D14: 0 来自从动站 / 1 来自启动站
    response: int = 1  # D13: 0 不需要应答 / 1 需要应答
    extension: int = 0  # D12: 业务扩展域标识
    priority: int = 0  # D11~D8: 0 最高
    reserved: int = 0  # D7~D4
    service_id: int = SERVICE_TEST_FRAME
    app_version: int = 1
    frame_seq: int = 0
    ext_data: bytes = field(default_factory=bytes)


def build_business_message(sdu: bytes, header: Optional[BusinessHeader] = None) -> bytes:
    """第2层：业务报文头 + 数据单元（+ 可选业务扩展域）。

    控制域(2B,LE) | 业务标识(1B) | 应用版本号(1B) | 帧序号(2B,LE) | 帧长(2B,LE) | 数据单元 | [扩展域]
    """
    header = header or BusinessHeader()
    control = pack_bits(
        16,
        [
            (0, 4, _clip_count(header.frame_type, "帧类型", 0x0F)),
            (4, 4, _clip_count(header.reserved, "保留(D7~D4)", 0x0F)),
            (8, 4, _clip_count(header.priority, "任务优先级", 0x0F)),
            (12, 1, _clip_count(header.extension, "业务扩展域标识", 0x1)),
            (13, 1, _clip_count(header.response, "响应标识", 0x1)),
            (14, 1, _clip_count(header.prm, "启动标志", 0x1)),
            (15, 1, _clip_count(header.direction, "传输方向", 0x1)),
        ],
    )
    sdu = bytes(sdu or b"")
    body = (
        control
        + bytes([_clip_count(header.service_id, "业务标识", 0xFF)])
        + bytes([_clip_count(header.app_version, "应用版本号", 0xFF)])
        + u16le(_clip_count(header.frame_seq, "帧序号", 0xFFFF))
        + u16le(len(sdu))
        + sdu
    )
    if header.extension:
        ext = bytes(header.ext_data or b"")
        body += u16le(len(ext)) + ext
    return body


# ────────────────────────────── 第3层：应用层帧 ──────────────────────────────


def build_app_frame(
    sdu: bytes,
    *,
    msg_port: int = MSG_PORT_MANAGE,
    msg_id: int = MSG_ID_CCO_STA,
    reserved: int = 0,
    header: Optional[BusinessHeader] = None,
) -> bytes:
    """第3层：应用层帧 = 端口号(1B) + 报文标识符(2B,LE) + 保留(1B) + 业务报文。"""
    return (
        bytes([_clip_count(msg_port, "报文端口号", 0xFF)])
        + u16le(_clip_count(msg_id, "报文标识符", 0xFFFF))
        + bytes([_clip_count(reserved, "保留", 0xFF)])
        + build_business_message(sdu, header)
    )


# ────────────────────────────── 第4层：ED 封装 ──────────────────────────────


def build_ed_frame(
    payload: bytes,
    *,
    wrapper: str = "plc2",
    physical_channel: int = 0x01,
    timestamp: int = 0,
    pb_count: int = 1,
    pb_len: Optional[int] = None,
    ctrl1: int = 0x00,
    ctrl2: int = 0x02,
    cs_mode: str = "ff",
) -> bytes:
    """第4层：ED..EE 封装（PLC2.0 收发机报文格式）。

    ED(1) | 帧长(2,LE) | 控制域1(1) | 控制域2(1) | EF(1) | 数据域 | CS(1) | EE(1)
    - 帧长 = 控制域1+控制域2+EF+数据域+CS 的字节数（不含 ED/帧长/EE）
    - 数据域公共头：plc2 = 物理信道+时间戳(4,LE)+物理块个数+保留+物理块长度(2,LE)
                    gx   = 时间戳(4,LE)+物理信道+物理块个数+物理块长度(2,LE)
    - cs_mode: "ff" 按文档当前实现填 0xFF（默认）；"sum" 按"之前所有字节求和取低8位"计算
    """
    if wrapper not in ("plc2", "gx"):
        raise FrameBuildError(f"未知 ED 包装格式：{wrapper!r}（允许 plc2 / gx）")
    payload = bytes(payload or b"")
    if pb_len is None:
        pb_len = len(payload)
    pb_len = _clip_count(pb_len, "单个物理块长度", 0xFFFF)
    if wrapper == "plc2":
        data_header = (
            bytes([_clip_count(physical_channel, "物理信道", 0xFF)])
            + u32le(timestamp)
            + bytes([_clip_count(pb_count, "物理块个数", 0xFF)])
            + bytes([0x00])  # 保留（解析侧口径）
            + u16le(pb_len)
        )
    else:
        data_header = (
            u32le(timestamp)
            + bytes([_clip_count(physical_channel, "物理信道", 0xFF)])
            + bytes([_clip_count(pb_count, "物理块个数", 0xFF)])
            + u16le(pb_len)
        )
    data = data_header + payload
    if cs_mode == "sum":
        cs = (sum(bytes([0xED]) + u16le(len(data) + 4) + bytes([ctrl1, ctrl2, 0xEF]) + data)) & 0xFF
    elif cs_mode == "ff":
        cs = 0xFF
    else:
        raise FrameBuildError(f"未知 CS 模式：{cs_mode!r}（允许 ff / sum）")
    body = bytes([_clip_count(ctrl1, "控制域1", 0xFF), _clip_count(ctrl2, "控制域2", 0xFF), 0xEF]) + data + bytes([cs])
    return bytes([0xED]) + u16le(len(body)) + body + bytes([0xEE])


# ────────────────────────── 顶层：模式清单与一键组帧 ──────────────────────────


@dataclass(frozen=True)
class ModeField:
    """组帧参数（GUI 据此生成控件，避免界面里硬编码 20+ 个模式）。"""

    name: str
    label: str
    kind: str = "int"  # int | bytes | choice
    default: object = 0
    help: str = ""
    choices: Tuple[Tuple[object, str], ...] = ()


@dataclass(frozen=True)
class TestMode:
    key: str
    group: str
    name: str
    test_id: int
    ext_id: Optional[int] = None
    fields: Tuple[ModeField, ...] = ()
    legacy_mode: Optional[int] = None


def _band_field() -> ModeField:
    return ModeField(
        "band",
        "通信频段",
        "choice",
        0,
        "；".join(f"{k}={v}" for k, v in BAND_MAP.items()),
        tuple((k, v) for k, v in BAND_MAP.items()),
    )


def _legacy_fields(mode: int) -> Tuple[ModeField, ...]:
    needs_value = mode not in (1, 2)
    value_label = {
        6: "目标频段值",
        7: "ToneMask值",
        8: "Option+信道号",
    }.get(mode, "测试模式持续时间(分钟)")
    fields: List[ModeField] = [
        ModeField("proto_version", "协议版本号(6bit)", "int", 1, "默认 1；取值表待补"),
        ModeField("header_len", "报文头长度(6bit)", "int", 6, "默认 6（本头自身长度）；取值表待补"),
        ModeField(
            "header_len_layout",
            "报文头长度布局",
            "choice",
            "doc",
            "doc=按文档表61 六位跨字节；parser=只写高2位（与现有解析器读回一致）",
            (("doc", "文档6bit"), ("parser", "解析器2bit")),
        ),
        ModeField("protocol_type", "转发数据的规约类型(4bit)", "int", 0, "取值表待补（文档未给枚举）"),
    ]
    if needs_value:
        fields.append(ModeField("value", value_label, "int", 1, "12bit，0~4095"))
    fields.extend(
        [
            ModeField("security_mode", "安全测试模式(4bit)", "int", 0, "仅模式13 生效"),
            ModeField("phr_mcs", "PHR_MCS(4bit)", "int", 0, "模式12 生效；取值待《第4部分》"),
            ModeField("psdu_mcs", "PSDU_MCS(4bit)", "int", 0, "模式12 生效；取值待《第4部分》"),
            ModeField("pb_size", "PbSIZE(4bit)", "int", 0, "模式12 生效；取值待《第4部分》"),
        ]
    )
    return tuple(fields)


def test_modes() -> List[TestMode]:
    """全部可组帧的测试模式（A 新测试ID / B 2.0扩展ID / C 表61 原有模式）。"""
    modes: List[TestMode] = [
        TestMode("loopback", "A 新测试帧", TEST_ID_MAP[0x00], 0x00, fields=(_band_field(),)),
        TestMode("transparent", "A 新测试帧", TEST_ID_MAP[0x01], 0x01, fields=(_band_field(),)),
        TestMode("band_switch", "A 新测试帧", TEST_ID_MAP[0x02], 0x02, fields=(_band_field(),)),
    ]
    modes.extend(
        [
            TestMode("ext_bitloading", "B 2.0测试扩展", TEST_EXT_ID_MAP[0x0001], 0x04, 0x0001),
            TestMode(
                "ext_bitloading_table",
                "B 2.0测试扩展",
                TEST_EXT_ID_MAP[0x0002],
                0x04,
                0x0002,
                fields=(
                    ModeField("src_tei", "源TEI", "int", 0, "12bit"),
                    ModeField("dst_tei", "目的TEI", "int", 0, "12bit"),
                    ModeField("stream_count", "流数", "choice", 1, "1:1流 2:2流", ((1, "1流"), (2, "2流"))),
                    ModeField("subcarrier_group", "子载波分组大小", "int", 1),
                    ModeField("cutoff_carrier", "截止子载波", "int", 0),
                    ModeField("bps", "Bps（每符号比特数）", "int", 0),
                    ModeField("bit_table", "B表（十六进制）", "bytes", b"", "单流每块3B/双流每块6B（8组）"),
                ),
            ),
            TestMode(
                "ext_mapping",
                "B 2.0测试扩展",
                TEST_EXT_ID_MAP[0x0003],
                0x04,
                0x0003,
                fields=(ModeField("mapping_mode", "映射模式", "int", 0),),
            ),
            TestMode("ext_ofdma", "B 2.0测试扩展", TEST_EXT_ID_MAP[0x0004], 0x04, 0x0004),
            TestMode(
                "ext_ofdma_multi",
                "B 2.0测试扩展",
                TEST_EXT_ID_MAP[0x0005],
                0x04,
                0x0005,
                fields=(
                    ModeField(
                        "frame_type",
                        "帧类型",
                        "choice",
                        0,
                        "0:DL立即 1:UL等待触发 2:UL-trigger立即",
                        tuple((k, v) for k, v in OFDMA_FRAME_TYPE_MAP.items() if k != 3),
                    ),
                    ModeField("fc", "FC域（16字节十六进制）", "bytes", b"", "留空自动填 16 个 00"),
                    ModeField("efc", "eFC域（16字节十六进制）", "bytes", b"", "帧类型 1（UL）无 eFC"),
                ),
            ),
            TestMode(
                "ext_mac_ofdma",
                "B 2.0测试扩展",
                TEST_EXT_ID_MAP[0x0006],
                0x04,
                0x0006,
                fields=(
                    ModeField("ofdma_type", "OFDMA类型", "choice", 0, "0:DL_OFDMA 1:UL_OFDMA", ((0, "DL"), (1, "UL"))),
                    ModeField("node_count", "调度节点数(3bit)", "int", 0),
                ),
            ),
            TestMode(
                "ext_tei",
                "B 2.0测试扩展",
                TEST_EXT_ID_MAP[0x0007],
                0x04,
                0x0007,
                fields=(ModeField("tei", "TEI(12bit)", "int", 0),),
            ),
            TestMode(
                "ext_bitloading_switch",
                "B 2.0测试扩展",
                TEST_EXT_ID_MAP[0x0008],
                0x04,
                0x0008,
                fields=(
                    ModeField(
                        "enable",
                        "采用Bitloading传输数据",
                        "choice",
                        1,
                        "0:退出Bitloading模式 1:使用Bitloading模式",
                        ((1, "使用"), (0, "退出")),
                    ),
                ),
            ),
            TestMode(
                "ext_agg",
                "B 2.0测试扩展",
                TEST_EXT_ID_MAP[0x0009],
                0x04,
                0x0009,
                fields=(ModeField("agg_count", "报文聚合数目", "int", 1),),
            ),
        ]
    )
    for mode_value, name in sorted(LEGACY_TEST_MODE_MAP.items()):
        modes.append(
            TestMode(
                f"legacy_{mode_value}",
                "C 表61 原有测试模式",
                f"1.0测试 · {name}",
                0x03,
                legacy_mode=mode_value,
                fields=_legacy_fields(mode_value),
            )
        )
    return modes


def mode_by_key(key: str) -> Optional[TestMode]:
    for mode in test_modes():
        if mode.key == key:
            return mode
    return None


@dataclass
class FrameBuildResult:
    """组帧结果（供界面分层预览）。

    前五个字段是应用层组帧（1.23.64 既有语义，保持不变）；
    其后是**链路层**（协议9 的 FC / 物理块 / MAC 帧头）可选字段，
    仅在页面启用「组装链路层帧」时填充（默认 None = 未组装，行为与 1.23.64 一致）。
    """

    mode_key: str
    bdu: bytes
    app_frame: bytes
    business_message: bytes
    ed_frame: Optional[bytes] = None

    # —— 链路层（可选；见 csg_link_frame_gen）——
    fc: Optional[bytes] = None
    pb: Optional[bytes] = None
    mac_header: Optional[bytes] = None
    msdu: Optional[bytes] = None
    mpdu: Optional[bytes] = None
    link_enabled: bool = False

    def has_link_layer(self) -> bool:
        return bool(self.link_enabled and self.mpdu)

    def hex(self, layer: str = "app") -> str:
        # mac_frame 是派生层：信标帧没有 MAC 头、SACK 连 MSDU 都没有。
        # 直接写 self.mac_header + self.msdu 会在 None 上抛 TypeError，
        # 而下面这个 dict 是**无条件求值**的 —— 于是 SACK/信标的任何 hex() 都崩。
        mac_frame = None
        if self.has_link_layer() and (self.mac_header or self.msdu):
            mac_frame = (self.mac_header or b"") + (self.msdu or b"")
        data = {
            "bdu": self.bdu,
            "app": self.app_frame,
            "business": self.business_message,
            "ed": self.ed_frame,
            "fc": self.fc,
            "pb": self.pb,
            "mac_header": self.mac_header,
            "msdu": self.msdu,
            "mac_frame": mac_frame,
            "mpdu": self.mpdu,
        }.get(layer)
        if data is None:
            raise FrameBuildError(f"该结果没有 {layer} 层（ED 封装未启用？或未组装链路层？）")
        return " ".join(f"{b:02X}" for b in data)

    def sizes(self) -> Dict[str, int]:
        """各层字节数（仅列出已填充的层；供折叠区标题栏显示）。"""
        out: Dict[str, int] = {"bdu": len(self.bdu), "app": len(self.app_frame),
                               "business": len(self.business_message)}
        if self.ed_frame is not None:
            out["ed"] = len(self.ed_frame)
        for name in ("fc", "pb", "mac_header", "msdu", "mpdu"):
            value = getattr(self, name)
            if value is not None:
                out[name] = len(value)
        return out


def build_frame_from_mode(
    mode_key: str,
    params: Optional[Dict[str, object]] = None,
    *,
    msg_port: int = MSG_PORT_MANAGE,
    msg_id: int = MSG_ID_CCO_STA,
    header: Optional[BusinessHeader] = None,
    ed: Optional[Dict[str, object]] = None,
) -> FrameBuildResult:
    """按模式清单组帧：第1层 → 第2/3层 →（可选）第4层 ED 封装。

    params: 模式参数字典（键名见 :func:`test_modes` 里各 ``ModeField.name``）
    ed: 传字典则同时产出 ED 封装帧，键见 :func:`build_ed_frame`
    """
    mode = mode_by_key(mode_key)
    if mode is None:
        raise FrameBuildError(f"未知组帧模式：{mode_key}")
    params = dict(params or {})
    if mode.test_id == 0x03:
        bdu = build_test_pdu(0x03, mode=mode.legacy_mode, **params)
    elif mode.ext_id is not None:
        bdu = build_test_pdu(0x04, ext_id=mode.ext_id, **params)
    else:
        bdu = build_test_pdu(mode.test_id, **params)

    business = build_business_message(bdu, header)
    app_frame = (
        bytes([_clip_count(msg_port, "报文端口号", 0xFF)])
        + u16le(_clip_count(msg_id, "报文标识符", 0xFFFF))
        + bytes([0x00])
        + business
    )
    result = FrameBuildResult(mode_key=mode_key, bdu=bdu, app_frame=app_frame, business_message=business)
    if ed is not None:
        result.ed_frame = build_ed_frame(app_frame, **ed)
    return result


def hex_to_bytes(text: str) -> bytes:
    """把 ``"01 02 03"`` / ``"010203"`` 之类的十六进制文本转成 bytes（供界面输入 B表/FC 用）。"""
    cleaned = "".join(ch for ch in str(text or "") if ch not in " \t\r\n-_")
    if not cleaned:
        return b""
    if len(cleaned) % 2:
        raise FrameBuildError(f"十六进制长度须为偶数：{text!r}")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise FrameBuildError(f"非法十六进制：{text!r}") from exc
