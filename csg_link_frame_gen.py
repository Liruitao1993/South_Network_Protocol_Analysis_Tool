# -*- coding: utf-8 -*-
"""协议9（新一代载波 / 通感一体化）**链路层组帧**：FC 帧控制 / 物理块 / MAC 帧头。纯逻辑无 Qt。

背景
====
应用层组帧早已存在（``csg_new_gen_frame_gen``：测试帧 BDU → 业务报文 → 应用层帧 → ED 封装），
但 **FC(16B) / 物理块(4B 头 + 体 + PBCS) / MAC 帧头(32B 长 / 12B 短)** 三层没有组帧实现，
因此无法构造可在信道收发的完整 MPDU。本模块补齐这三层。

设计原则（详见 `.trellis/tasks/09-30-csg-link-layer-frame-gen/`）
==============================================================
1. **字段依据以协议第4部分表格为准**（research/01、02），但**位级布局以现有解析器
   ``csg_new_gen_parser`` 的实测实现为准**（research/03）——解析器已由 60 帧真实夹具锚定。
2. **三处校验一律自动计算**，覆盖范围各不相同（research/02 §7）：
   - FCCS      = CRC-24(FC 字节 0-12)，小端 3 字节
   - PBCS      = CRC-24(物理块头 + 块体 + 保留字节)，小端 3 字节
   - 完整性校验 = CRC-32(**MSDU 载荷**，不含 MAC 帧头)，小端 4 字节
3. **不新建第二份协议取值表**：下拉候选与常量全部从解析器常量派生（见各 ``*_choices()``）。
4. **组帧 ⇄ 解析同源对拍**：组出的帧必须能被 ``CSGNewGenParser.parse_to_table`` 解回同样的值，
   这是本模块测试的唯一权威判据。

已知分歧（按解析器语义实现，已记录待核）
=====================================
下列两处「文档表述」与「解析器代码」不一致。本模块**按解析器语义**组帧，以保证本工具
回读自洽；分歧本身未擅自修改解析器（属独立任务），详见模块内对应位置注释与
``research/03``。
"""

from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import csg_new_gen_parser as _parser_mod
from csg_new_gen_frame_gen import FrameBuildError, _clip_count  # noqa: F401  (供外部复用)
from csg_new_gen_parser import CSGNewGenParser as _Parser

__all__ = [
    "FrameBuildError",
    "put_bits_le",
    "crc24_le",
    "crc32_le",
    "pb_body_size",
    "cmt_index_for_pb_size",
    "bl_pb_size_code",
    "build_fc",
    "build_pb_block",
    "build_mac_header",
    "build_mac_frame",
    "build_msdu_header",
    "build_msdu",
    "build_link_frame",
    "LinkFrameConfig",
    "LinkFrameBuildResult",
    "delimiter_choices",
    "std_version_choices",
    "mac_header_type_choices",
    "mac_version_choices",
    "msdu_type_choices",
    "send_type_choices",
    "broadcast_dir_choices",
    "beacon_phase_choices",
    "sack_snr_type_choices",
]

# ────────────────────────── 常量（来自协议第4部分；值取自解析器以保证单一来源） ──────────────────────────

DELIM_BEACON = 0
DELIM_SOF = 1
DELIM_SACK = 2
DELIM_NET = 3

STD_VERSION_BPLC = 1
STD_VERSION_ISAC = 2

MAC_HDR_TYPE_LONG = 0   # 32 字节长帧头（长 MSDU 原语）
MAC_HDR_TYPE_SHORT = 1  # 12 字节短帧头（短 MSDU 原语）
MAC_VERSION_STD = 1     # 标准帧协议（版本2 单跳帧协议仅无线，本模块未支持）

MSDU_TYPE_APP = 0x01
MSDU_TYPE_RF_DISCOVER = 0x02
MSDU_TYPE_IPV4 = 0x80
MSDU_TYPE_MME = 0x88E1  # 长 MSDU 头的网络管理消息（与 VLAN=0x8100 配对）

MAC_HDR_LEN_LONG = 32
MAC_HDR_LEN_SHORT = 12

PB_HDR_LEN = 4
PB_TAIL_LEN = 4  # 保留(1) + 物理块检查序列(3)
PB_OVERHEAD = PB_HDR_LEN + PB_TAIL_LEN  # 块体 = PB总大小 - 8

#: 第一期支持的帧类型（与 ``delimiter_type`` 对应）
FRAME_KINDS = ("sof", "beacon", "sack")

#: 第一期支持的 PB 总大小（BPLC 实际为 136/520；其余为 ISAC-PLC）
PB_TOTAL_SIZES = (520, 264, 136, 72, 16)


# ────────────────────────── 下拉候选（全部派生自解析器常量，禁止另写一份） ──────────────────────────


def _choices(mapping: Dict[int, str], order: Optional[Sequence[int]] = None) -> Tuple[Tuple[int, str], ...]:
    keys = list(order) if order is not None else sorted(mapping)
    return tuple((k, f"{k} - {mapping[k]}") for k in keys if k in mapping)


def delimiter_choices() -> Tuple[Tuple[int, str], ...]:
    return _choices(_Parser.DELIMITER_TYPE_MAP, order=(DELIM_BEACON, DELIM_SOF, DELIM_SACK, DELIM_NET))


def std_version_choices() -> Tuple[Tuple[int, str], ...]:
    return _choices(_parser_mod.MPDU_VERSION_MAP, order=(STD_VERSION_BPLC, STD_VERSION_ISAC))


def mac_header_type_choices() -> Tuple[Tuple[int, str], ...]:
    return _choices(_parser_mod.MAC_HEADER_TYPE_MAP, order=(MAC_HDR_TYPE_LONG, MAC_HDR_TYPE_SHORT))


def mac_version_choices() -> Tuple[Tuple[int, str], ...]:
    return _choices(_parser_mod.MAC_VERSION_MAP, order=(MAC_VERSION_STD, 2))


def msdu_type_choices() -> Tuple[Tuple[int, str], ...]:
    """MSDU 类型（表13 + 解析器长头用的管理消息类型）。"""
    return tuple(
        (v, f"0x{v:02X} {name}")
        for v, name in (
            (MSDU_TYPE_APP, _parser_mod.MSDU_TYPE_MAP.get(MSDU_TYPE_APP, "应用层报文")),
            (MSDU_TYPE_RF_DISCOVER, _parser_mod.MSDU_TYPE_MAP.get(MSDU_TYPE_RF_DISCOVER, "无线发现列表消息")),
            (MSDU_TYPE_IPV4, _parser_mod.MSDU_TYPE_MAP.get(MSDU_TYPE_IPV4, "IPV4报文")),
            (MSDU_TYPE_MME, _parser_mod.MSDU_TYPE_MAP.get(MSDU_TYPE_MME, "网络管理消息")),
        )
    )


def send_type_choices() -> Tuple[Tuple[int, str], ...]:
    return _choices(_parser_mod.SEND_TYPE_MAP)


def broadcast_dir_choices() -> Tuple[Tuple[int, str], ...]:
    return _choices(_parser_mod.BROADCAST_DIR_MAP)


def beacon_phase_choices() -> Tuple[Tuple[int, str], ...]:
    return _choices(_Parser.BEACON_PHASE_MAP)


def sack_snr_type_choices() -> Tuple[Tuple[int, str], ...]:
    return _choices(_Parser.SACK_SNR_TYPE_MAP)


# ────────────────────────── 位打包：与解析器 _extract_bits 严格互逆 ──────────────────────────


def put_bits_le(buf: bytearray, start_bit: int, width: int, value: int, name: str = "") -> None:
    """把 ``value`` 的低 ``width`` 位写入 ``buf`` 的 ``[start_bit, start_bit+width)`` 位区间。

    位序约定与 ``CSGNewGenParser._extract_bits`` 完全一致（LSB 优先：bit0 = byte0.bit0），
    即本函数是它的**严格逆运算**：``_extract_bits(bytes(buf), start_bit, width) == value``。

    跨字节字段（如 FC 的 12bit 源/目的 TEI、MAC 头的 12bit 发送序号）**必须**用它写入，
    不要按「首字节=高位」手工拼字节——那正是协议11 曾整批错位的原因（AGENTS 陷阱 54）。
    """
    if width <= 0:
        raise FrameBuildError(f"位宽必须为正：{width}（字段 {name or '未知'}）")
    if start_bit < 0:
        raise FrameBuildError(f"起始位不能为负：{start_bit}（字段 {name or '未知'}）")
    if not isinstance(value, int):
        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise FrameBuildError(f"{name or '字段'} 必须是整数，得到 {value!r}") from exc
    maximum = (1 << width) - 1
    if value < 0 or value > maximum:
        raise FrameBuildError(
            f"{name or '字段'} 超出 {width}bit 范围：{value}（允许 0~{maximum}）")
    need = (start_bit + width + 7) // 8
    if need > len(buf):
        raise FrameBuildError(
            f"位写入越界（字段 {name or '未知'}）：需要 {need} 字节，缓冲区仅 {len(buf)} 字节")
    for i in range(width):
        bp = start_bit + i
        byte_idx, bit_idx = bp // 8, bp % 8
        if (value >> i) & 1:
            buf[byte_idx] |= 1 << bit_idx
        else:
            buf[byte_idx] &= (~(1 << bit_idx)) & 0xFF


# ────────────────────────── CRC（复用解析器实现，不另写一份算法） ──────────────────────────


def crc24_le(data: bytes) -> bytes:
    """CRC-24 的小端 3 字节形式（FCCS / PBCS 用）。"""
    return int(_Parser._crc24(bytes(data)) & 0xFFFFFF).to_bytes(3, "little")


def crc32_le(data: bytes) -> bytes:
    """CRC-32 (IEEE) 的小端 4 字节形式（MAC 帧完整性校验用）。"""
    return int(_Parser._crc32_ieee(bytes(data)) & 0xFFFFFFFF).to_bytes(4, "little")


# ────────────────────────── 物理块大小 ↔ 载波映射表索引/TMI ──────────────────────────


def pb_body_size(pb_total: int) -> int:
    """物理块体大小 = 物理块总大小 - 物理块头(4) - 保留(1) - 检查序列(3)。"""
    if pb_total not in PB_TOTAL_SIZES:
        raise FrameBuildError(
            f"物理块总大小非法：{pb_total}（允许 {sorted(PB_TOTAL_SIZES)}）")
    return pb_total - PB_OVERHEAD


def cmt_index_for_pb_size(pb_total: int, std_version: int) -> int:
    """按物理块总大小**反查**载波映射表索引/TMI。

    以「块大小」为主动输入反推索引，可避免用户填出不满足
    ``PB起始偏移 + 物理块个数×PB大小 == 帧长`` 的组合——解析器会因此多打一行
    「PB大小推断」（``_infer_pb_size``）。映射关系取自解析器 ``_get_pb_size``。
    """
    pb_body_size(pb_total)  # 合法性校验
    if std_version == STD_VERSION_ISAC:
        for tmi in sorted(_Parser.ISAC_PB_MAP):
            if _Parser.ISAC_PB_MAP[tmi] == pb_total:
                return tmi
        raise FrameBuildError(f"ISAC-PLC 无对应 TMI 的物理块大小：{pb_total}")
    if pb_total == 136:
        return 4           # _get_pb_size: tmi<=0x7 或 0xE → 136
    if pb_total == 520:
        return 8           # _get_pb_size: tmi in (8,9,A,B,C,F) → 520
    raise FrameBuildError(
        f"BPLC 版本仅支持 136 / 520 字节物理块，得到：{pb_total}（允许 [136, 520]）")


def bl_pb_size_code(pb_total: int) -> int:
    """Bitloading 模式下的物理块大小码（表23 字节6 bit1-2）：0:136 1:520 2:72 3:264。"""
    for code, size in _Parser.ISAC_BL_PB_SIZE_MAP.items():
        if size == pb_total:
            return code
    raise FrameBuildError(
        f"Bitloading 模式不支持该物理块大小：{pb_total}"
        f"（允许 {sorted(_Parser.ISAC_BL_PB_SIZE_MAP.values())}）")


# ────────────────────────── FC 组帧 ──────────────────────────


def _fill_fc_sof_bplc(fc: bytearray, cfg: "LinkFrameConfig") -> None:
    """SOF 帧可变区域 —— BPLC 版本（协议第4部分 表20）。"""
    _, snid_high = _snid_parts(cfg)
    put_bits_le(fc, 8, 12, cfg.src_tei, "源TEI")
    put_bits_le(fc, 20, 12, cfg.dest_tei, "目的TEI")
    put_bits_le(fc, 32, 8, cfg.link_id, "链路标识符")
    put_bits_le(fc, 40, 1, snid_high, "短网络标识高位")
    put_bits_le(fc, 41, 15, cfg.fc_reserved, "保留")
    put_bits_le(fc, 56, 4, cfg.pb_count, "物理块个数")
    put_bits_le(fc, 60, 4, cfg.cmt_index, "载波映射表索引")
    put_bits_le(fc, 64, 12, cfg.frame_len_10us, "帧长")
    put_bits_le(fc, 76, 9, cfg.fc_reserved, "保留")
    put_bits_le(fc, 85, 1, cfg.tei_filter, "TEI过滤标志位")
    put_bits_le(fc, 86, 1, cfg.retransmit, "重传标志位")
    put_bits_le(fc, 87, 9, cfg.symbol_count, "符号数")
    put_bits_le(fc, 96, 4, cfg.ext_cmt_index, "扩展载波映射表索引")


def _fill_fc_sof_isac(fc: bytearray, cfg: "LinkFrameConfig") -> None:
    """SOF 帧可变区域 —— ISAC-PLC 版本单站点数据帧（协议第4部分 表23）。"""
    if cfg.multi_site:
        raise FrameBuildError("ISAC-PLC 多站点帧(OFDMA)与训练帧属第二期范围，本期未支持")
    _, snid_high = _snid_parts(cfg)
    put_bits_le(fc, 8, 12, cfg.src_tei, "源TEI")
    put_bits_le(fc, 20, 12, cfg.dest_tei, "目的TEI")
    put_bits_le(fc, 32, 1, 0, "多站点帧标识")
    put_bits_le(fc, 33, 1, 0, "训练帧标识")
    put_bits_le(fc, 34, 4, cfg.pb_count, "物理块个数")
    put_bits_le(fc, 38, 2, cfg.streams, "流数")
    put_bits_le(fc, 40, 3, cfg.tf_symbols_cfg, "TF符号数")
    put_bits_le(fc, 43, 3, cfg.pl_band, "PL频段标识")
    put_bits_le(fc, 46, 1, cfg.tf_ext_band, "TF扩展频段指示")
    put_bits_le(fc, 47, 1, 0, "保留")
    put_bits_le(fc, 48, 1, cfg.bitloading, "Bitloading标识")
    if cfg.bitloading:
        put_bits_le(fc, 49, 5, bl_pb_size_code(cfg.pb_total), "物理块大小码")
    else:
        put_bits_le(fc, 49, 5, cfg.cmt_index, "TMI编号")
    put_bits_le(fc, 54, 2, 0, "保留")
    put_bits_le(fc, 56, 8, 0, "保留")
    put_bits_le(fc, 64, 12, cfg.frame_len_10us, "帧长")
    put_bits_le(fc, 76, 4, 0, "保留")
    put_bits_le(fc, 80, 16, 0, "保留")
    put_bits_le(fc, 96, 1, snid_high, "短网络标识高位")
    put_bits_le(fc, 97, 3, 0, "保留")


def _fill_fc_beacon(fc: bytearray, cfg: "LinkFrameConfig") -> None:
    """信标帧可变区域（协议第4部分 表18）。"""
    _, snid_high = _snid_parts(cfg)
    put_bits_le(fc, 8, 32, cfg.beacon_timestamp, "信标时间戳")
    put_bits_le(fc, 40, 32, cfg.beacon_cycle, "信标周期计数")
    put_bits_le(fc, 72, 12, cfg.src_tei, "源TEI")
    put_bits_le(fc, 84, 4, cfg.cmt_index, "载波映射表索引")
    # ⚠ 已知分歧（本期按【文档】位置实现，未擅改解析器，已记入 research/03）：
    #   文档表18：符号数为 9bit，落在「字节11 全部 + 字节12 bit0」，即本模块的 bits 88-96。
    #   但解析器 `_parse_mpdu_beacon` 读作 `byte11<<1 | byte12.bit7`，把第 9 位取到了
    #   bits 103，而 bits 100-103 是**标准版本号**（FC 固定部分，表14 字节12 高4位）——
    #   两者冲突：解析器按 bits 103 读，等于把版本号的最高位当成符号数第 9 位。
    #   由于版本号必须正确（001x = 1=BPLC / 2=ISAC-PLC），组帧侧不可能把版本号让出去，
    #   故本模块按文档位置写 bits 96 并保持版本号正确；代价是**符号数第 9 位（即 ≥256 的
    #   符号数）在本工具回读时取不到**（测试中只断言低 8 位有效区间）。
    put_bits_le(fc, 88, 8, (cfg.symbol_count & 0x1FF) >> 1, "符号数(低8位)")
    put_bits_le(fc, 96, 1, cfg.symbol_count & 0x01, "符号数(第9位)")
    put_bits_le(fc, 97, 1, snid_high, "短网络标识高位")
    put_bits_le(fc, 98, 2, cfg.beacon_phase, "相线")


def _sack_snr_words(snr_type: int, value: int, ru: Sequence[int]) -> bytes:
    """SNR 评估信息 4 字节（字节5-8）。

    解析器 ``_parse_mpdu_sack`` 读作 ``int.from_bytes(字节5-8, 'big') >> 2``，即**有效 30 位
    位于该大端字的 bit2-31**（含字节8 的 bit2-7）。因此写入方式是把 30 位值左移 2 位。

    ⚠ 由此产生一条**位域冲突**（本期按解析器语义实现，未擅改解析器，已记入 research/03）：
      文档表30 把「字节8 bit6-7」列为保留，但按解析器读法字节8 bit6-7 实为 30 位字段的高位
      （即 SNR 值的 bit4-5）。故本函数**不得**再把 bit70-71 当保留位清零——那样会丢掉
      SNR 值的高 2 位（实测：值 27 被读成 11）。
    """
    if snr_type == 0:
        return b"\x00\x00\x00\x00"      # 不携带 SNR 信息
    if snr_type == 1:
        thirty = value & 0x1F
    elif snr_type == 2:
        thirty = 0
        for i, v in enumerate(list(ru)[:6]):
            thirty |= (int(v) & 0x1F) << (5 * i)
    else:
        raise FrameBuildError(
            f"SNR类型仅支持 0(不携带)/1(当前帧SNR)/2(基础RU，见解析器 SACK_SNR_TYPE_MAP)，"
            f"得到 {snr_type}")
    return ((thirty << 2) & 0xFFFFFFFF).to_bytes(4, "big")


def _fill_fc_sack(fc: bytearray, cfg: "LinkFrameConfig") -> None:
    """选择确认帧可变区域（协议第4部分 表30）。"""
    if cfg.sack_ext_type != 0:
        raise FrameBuildError(
            f"SACK 扩展帧类型仅支持 0（标准选择确认帧），得到 {cfg.sack_ext_type}；"
            "1/2（抄控器网络搜索/同步帧）与 3（Bitloading扩展帧）属第二期范围")
    _, snid_high = _snid_parts(cfg)
    put_bits_le(fc, 8, 4, cfg.sack_rx_result, "接收结果")
    put_bits_le(fc, 12, 4, cfg.sack_rx_status, "接收状态")
    put_bits_le(fc, 16, 12, cfg.dest_tei, "目的TEI")
    put_bits_le(fc, 28, 4, cfg.sack_rx_pb_count, "接收物理块个数")
    put_bits_le(fc, 32, 1, snid_high, "短网络标识高位")
    put_bits_le(fc, 33, 2, cfg.sack_snr_type, "SNR类型")
    put_bits_le(fc, 35, 5, 0, "保留")
    fc[5:9] = _sack_snr_words(cfg.sack_snr_type, cfg.sack_snr_value, cfg.sack_snr_ru)
    # ⚠ 此处**不得**再写 put_bits_le(fc, 70, 2, 0)：字节8 bit6-7 是 SNR 30 位字段的高位，
    #    不是保留位（详见 _sack_snr_words 的说明）。写零会让 SNR 值丢掉高 2 位。
    put_bits_le(fc, 72, 24, 0, "保留")
    put_bits_le(fc, 96, 4, cfg.sack_ext_type, "扩展帧类型")


_FC_VARIANTS = {
    DELIM_SOF: {STD_VERSION_BPLC: _fill_fc_sof_bplc, STD_VERSION_ISAC: _fill_fc_sof_isac},
    DELIM_BEACON: {STD_VERSION_BPLC: _fill_fc_beacon, STD_VERSION_ISAC: _fill_fc_beacon},
    DELIM_SACK: {STD_VERSION_BPLC: _fill_fc_sack, STD_VERSION_ISAC: _fill_fc_sack},
}


def _snid_parts(cfg: "LinkFrameConfig") -> Tuple[int, int]:
    """SNID 的（低4位, 高1位）。SNID 共 5bit，有效取值 1~31（表14/表20 说明）。"""
    snid = _clip_count(cfg.snid, "短网络标识(SNID)", 31)
    return snid & 0x0F, (snid >> 4) & 0x01


def _ensure_cmt_index(cfg: "LinkFrameConfig") -> int:
    """确保载波映射表索引/TMI 已定：未显式指定时按物理块大小反查。

    信标帧特例：其载波映射表索引字段只有 **4bit**（表18），而 ISAC-PLC 的 TMI 取值可达 27，
    故信标帧一律按 BPLC 语义反查（136→4 / 520→8），避免读出 >15 的值。
    """
    if cfg.cmt_index is None:
        version = STD_VERSION_BPLC if cfg.frame_kind == "beacon" else cfg.std_version
        cfg.cmt_index = cmt_index_for_pb_size(cfg.pb_total, version)
    return int(cfg.cmt_index)


def build_fc(cfg: "LinkFrameConfig") -> bytes:
    """组 FC 帧控制（16 字节）：固定部分 + 变体可变区域 + 自动计算的 FCCS。

    固定部分（表14）：定界符类型(3b) + 接入指示(1b) + SNID低位(4b) + … + 标准版本号(4b，字节12 高4位)。
    FCCS = CRC-24(字节 0-12)，小端 3 字节。

    ⚠ **接入指示默认为 1 且不可随意改动**：解析器判定输入是否为 MPDU 的依据是
    ``(byte0 >> 3) & 1 == 1 and delimiter <= 3``（``parse_to_table`` 步骤0）。置 0 会导致
    整帧落到 MAC/MSDU/APP 的启发式路径上，生成的帧无法被本工具按 MPDU 解析。
    """
    kind = (cfg.frame_kind or "").strip().lower()
    if kind not in FRAME_KINDS:
        raise FrameBuildError(f"未知帧类型：{cfg.frame_kind!r}（允许 {list(FRAME_KINDS)}）")
    expected_delim = {"sof": DELIM_SOF, "beacon": DELIM_BEACON, "sack": DELIM_SACK}[kind]
    if cfg.delimiter_type != expected_delim:
        raise FrameBuildError(
            f"定界符类型 {cfg.delimiter_type} 与帧类型 {kind} 不符"
            f"（应为 {expected_delim}）")
    if (cfg.channel or "plc").lower() != "plc":
        raise FrameBuildError("无线信道(HRF)的 FC 变体属第二期范围，本期仅支持 PLC 载波")

    _ensure_cmt_index(cfg)  # 未显式指定时按 PB 大小反查，保证与解析器帧长判据自洽
    fc = bytearray(13)
    put_bits_le(fc, 0, 3, cfg.delimiter_type, "定界符类型")
    put_bits_le(fc, 3, 1, cfg.access_indicator, "接入指示")
    put_bits_le(fc, 4, 4, int(cfg.snid) & 0x0F, "短网络标识低位")

    variant = _FC_VARIANTS.get(cfg.delimiter_type, {}).get(cfg.std_version)
    if variant is None:
        raise FrameBuildError(
            f"定界符类型 {cfg.delimiter_type} + 标准版本号 {cfg.std_version} 的组合本期未支持")
    variant(fc, cfg)

    put_bits_le(fc, 100, 4, cfg.std_version, "标准版本号")
    return bytes(fc) + crc24_le(fc)


# ────────────────────────── 物理块组帧 ──────────────────────────


def build_pb_block(payload: bytes, cfg: "LinkFrameConfig", seq: int = 0) -> bytes:
    """组单个物理块：物理块头(4B) + 块体(补零) + 保留(1B) + PBCS(3B)。

    - 物理块头（表47）：序列号(16b 小端) + 聚合标志(1b) + 保留(15b)
    - 块体大小 = 物理块总大小 − 8；不足部分补 0x00（与解析器补零行为一致）
    - PBCS = CRC-24(物理块头 + 块体 + 保留字节)，小端 3 字节（表49 说明「以物理块头和物理块体
      以及保留字节三部分为目标」）
    """
    body_size = pb_body_size(cfg.pb_total)
    body = bytes(payload or b"")[:body_size]
    if len(body) < body_size:
        body = body + b"\x00" * (body_size - len(body))

    head = bytearray(PB_HDR_LEN)
    put_bits_le(head, 0, 16, seq, "序列号")
    put_bits_le(head, 16, 1, cfg.pb_agg_flag, "聚合标志")
    put_bits_le(head, 17, 15, 0, "保留")

    reserved = bytes([0x00])
    crc_range = bytes(head) + body + reserved
    return bytes(head) + body + reserved + crc24_le(crc_range)


def build_pb_blocks(mac_frame: bytes, cfg: "LinkFrameConfig") -> bytes:
    """按物理块个数把 MAC 帧切成连续多个物理块（第一期不做聚合头级联，末块补零）。"""
    body_size = pb_body_size(cfg.pb_total)
    count = _clip_count(cfg.pb_count, "物理块个数", 4)
    if count < 1:
        raise FrameBuildError(f"物理块个数至少为 1，得到 {cfg.pb_count}")
    if len(mac_frame) > body_size * count:
        raise FrameBuildError(
            f"MAC 帧 {len(mac_frame)} 字节超过 {count} 个物理块的容量 "
            f"{body_size * count} 字节（单个块体 {body_size} 字节）")
    blocks = []
    for i in range(count):
        chunk = mac_frame[i * body_size:(i + 1) * body_size]
        if not chunk:
            break
        blocks.append(build_pb_block(chunk, cfg, seq=cfg.pb_seq_start + i))
    return b"".join(blocks)


# ────────────────────────── MAC 头 / MAC 帧组帧 ──────────────────────────


def build_mac_header(msdu_len: int, cfg: "LinkFrameConfig") -> bytes:
    """组 MAC 帧头（32 字节长头 / 12 字节短头）。

    两种头共用字节 0-11 的布局（表7 / 表11），长头多出「目的MAC地址(6B) + 保留(4B) + 保留(10B)」。
    跨字节字段（发送序号 12bit、源/目的 TEI 12bit）一律走 ``put_bits_le``。

    TEI 位序（表8「低字节在前，低位在前」+ 文档实例）：目的TEI=0x123、源TEI=0x456
    → 第4/5/6 字节 = ``23 61 45``；测试对该实例有专门断言。
    """
    if cfg.mac_version == 2:
        raise FrameBuildError("单跳 MAC 帧头（版本2，仅无线）属第二期范围，本期未支持")
    header_type = cfg.mac_header_type
    if header_type not in (MAC_HDR_TYPE_LONG, MAC_HDR_TYPE_SHORT):
        raise FrameBuildError(f"帧头类型非法：{header_type}（0=32字节长头 / 1=12字节短头）")

    size = MAC_HDR_LEN_LONG if header_type == MAC_HDR_TYPE_LONG else MAC_HDR_LEN_SHORT
    _, snid_high = _snid_parts(cfg)
    buf = bytearray(size)
    put_bits_le(buf, 0, 1, header_type, "帧头类型")
    put_bits_le(buf, 1, 2, cfg.mac_version, "版本")
    put_bits_le(buf, 3, 1, snid_high, "短网络标识高位")
    put_bits_le(buf, 4, 12, cfg.tx_seq, "发送序号")
    put_bits_le(buf, 16, 16, msdu_len, "MSDU长度")
    put_bits_le(buf, 32, 12, cfg.dest_tei, "原始目的TEI")
    put_bits_le(buf, 44, 12, cfg.src_tei, "原始源TEI")
    put_bits_le(buf, 56, 4, int(cfg.snid) & 0x0F, "短网络标识低位")
    put_bits_le(buf, 60, 4, cfg.reboot_count, "重启次数")
    put_bits_le(buf, 64, 4, cfg.hop_count, "路由跳数")
    put_bits_le(buf, 68, 4, cfg.broadcast_dir, "广播方向")
    put_bits_le(buf, 72, 3, cfg.send_type, "发送类型")
    put_bits_le(buf, 75, 5, cfg.max_send, "发送次数限值")
    put_bits_le(buf, 80, 16, cfg.msdu_seq, "MSDU序列号")
    if header_type == MAC_HDR_TYPE_LONG:
        buf[12:18] = _mac_bytes(cfg.dest_mac, b"\xFF" * 6, "目的MAC地址")
    return bytes(buf)


def _mac_bytes(value: Optional[bytes], default: bytes, name: str) -> bytes:
    data = bytes(value) if value else default
    if len(data) != 6:
        raise FrameBuildError(f"{name} 必须是 6 字节，得到 {len(data)} 字节")
    return data


def build_msdu_header(cfg: "LinkFrameConfig") -> bytes:
    """组 MSDU 头：帧头类型 0 → 18 字节长头（表1）；1 → 2 字节短头（表2）。

    ⚠ 头长度**必须**与 MAC 帧头类型一致：解析器据 ``mac_data[0] & 0x01`` 推导
    ``msdu_hdr_len``（0→18，1→2）。不一致会让 MSDU 被当业务数据，整棵解析树错位。
    """
    if (cfg.msdu_header_type is not None
            and cfg.msdu_header_type != cfg.mac_header_type):
        raise FrameBuildError(
            f"MSDU 头类型({cfg.msdu_header_type})必须与 MAC 帧头类型({cfg.mac_header_type})一致："
            "解析器据 MAC 帧头的帧头类型推导 MSDU 头长度，不一致会让 MSDU 被当业务数据、"
            "整棵解析树错位（详见本模块 build_msdu_header 说明）")
    header_type = cfg.mac_header_type
    if header_type not in (MAC_HDR_TYPE_LONG, MAC_HDR_TYPE_SHORT):
        raise FrameBuildError(f"MSDU 头类型非法：{header_type}（0=长头18字节 / 1=短头2字节）")
    if header_type == MAC_HDR_TYPE_LONG:
        return (
            _mac_bytes(cfg.msdu_dest_mac, b"\xFF" * 6, "MSDU原始目的地址")
            + _mac_bytes(cfg.msdu_src_mac, b"\xFF" * 6, "MSDU原始源地址")
            + int(_clip_count(cfg.vlan, "VLAN标签", 0xFFFFFFFF)).to_bytes(4, "little")
            + int(_clip_count(cfg.msdu_type, "MSDU类型", 0xFFFF)).to_bytes(2, "little")
        )
    return bytes([
        _clip_count(cfg.vlan, "VLAN标签", 0xFF),
        _clip_count(cfg.msdu_type, "MSDU类型", 0xFF),
    ])


def build_msdu(cfg: "LinkFrameConfig") -> bytes:
    """MSDU = MSDU 头（长 18 / 短 2 字节）+ 载荷。"""
    return build_msdu_header(cfg) + bytes(cfg.msdu_payload or b"")


def build_mac_frame(msdu: bytes, cfg: "LinkFrameConfig") -> bytes:
    """MAC 帧 = MAC 帧头 + MSDU + 完整性校验(CRC-32)。

    完整性校验范围是 **MSDU 载荷本身**（不含 MAC 帧头），小端 4 字节——
    依据文档「计算完整性校验值时，不包括MAC帧头」，与解析器一致。
    """
    header = build_mac_header(len(msdu), cfg)
    return header + bytes(msdu) + crc32_le(msdu)


# ────────────────────────── 顶层：配置与编排 ──────────────────────────


@dataclass
class LinkFrameConfig:
    """链路层组帧的全部参数（UI 据此生成表单；字段分组与五层折叠一一对应）。"""

    # —— ① FC：公共部分 ——
    frame_kind: str = "sof"              # sof / beacon / sack
    delimiter_type: int = DELIM_SOF
    std_version: int = STD_VERSION_ISAC
    channel: str = "plc"
    access_indicator: int = 1            # ⚠ 必须为 1（否则解析器不走 MPDU 路径）
    snid: int = 1                        # 5bit，有效 1~31
    fc_reserved: int = 0

    # —— ① FC：SOF 变体字段（BPLC / ISAC 数据帧共用） ——
    src_tei: int = 0
    dest_tei: int = 1
    link_id: int = 0                     # BPLC 链路标识符
    streams: int = 0                     # ISAC 流数
    tf_symbols_cfg: int = 0              # ISAC TF符号数配置值（实际 = (值+1)*2）
    pl_band: int = 0                     # ISAC PL频段标识
    tf_ext_band: int = 0                 # ISAC TF扩展频段指示
    bitloading: int = 0                  # ISAC Bitloading 标识
    frame_len_10us: int = 0              # 帧长（单位 10μs）
    tei_filter: int = 1                  # 本规约固定为 1
    retransmit: int = 0
    symbol_count: int = 0
    ext_cmt_index: int = 0               # 仅 BPLC 且 cmt_index=0xD 时有效
    multi_site: int = 0                  # 多站点(OFDMA)——本期报错提示二期

    # —— ① FC：信标帧字段 ——
    beacon_timestamp: int = 0
    beacon_cycle: int = 0
    beacon_phase: int = 0
    beacon_payload: bytes = b""

    # —— ① FC：SACK 字段 ——
    sack_rx_result: int = 0
    sack_rx_status: int = 0x0F
    sack_rx_pb_count: int = 1
    sack_snr_type: int = 0
    sack_snr_value: int = 0
    sack_snr_ru: Tuple[int, ...] = ()
    sack_ext_type: int = 0               # 0 标准SACK（本期仅支持 0）

    # —— ② 物理块 ——
    pb_count: int = 1
    pb_total: int = 136
    pb_seq_start: int = 0
    pb_agg_flag: int = 0                 # 聚合头级联属第二期

    # —— ③ MAC 帧头 ——
    mac_header_type: int = MAC_HDR_TYPE_SHORT
    mac_version: int = MAC_VERSION_STD
    tx_seq: int = 0
    reboot_count: int = 0
    hop_count: int = 0
    broadcast_dir: int = 0
    send_type: int = 0
    max_send: int = 0
    msdu_seq: int = 0
    dest_mac: bytes = b"\xFF" * 6

    # —— ④ MSDU ——
    msdu_header_type: Optional[int] = None   # None → 随 mac_header_type
    vlan: int = 0
    msdu_type: int = MSDU_TYPE_APP
    msdu_dest_mac: bytes = b"\xFF" * 6
    msdu_src_mac: bytes = b"\xFF" * 6
    msdu_payload: bytes = b""

    #: 载波映射表索引 / TMI。**保持 None = 按物理块大小自动反查**（保证与解析器的
    #: 帧长自洽判据 ``PB起始偏移 + 个数×大小 == 帧长`` 一致，避免回读时多出「PB大小推断」行）。
    cmt_index: Optional[int] = None


@dataclass
class LinkFrameBuildResult:
    """链路层组帧结果（供界面分层预览）。"""

    fc: bytes
    pb: bytes = b""
    mac_header: bytes = b""
    msdu: bytes = b""
    mac_frame: bytes = b""
    payload: bytes = b""
    mpdu: bytes = b""

    _LAYERS = ("fc", "pb", "mac_header", "msdu", "mac_frame", "payload", "mpdu")

    def layer_bytes(self, layer: str) -> bytes:
        if layer not in self._LAYERS:
            raise FrameBuildError(f"未知层次：{layer!r}（允许 {list(self._LAYERS)}）")
        return getattr(self, layer)

    def hex(self, layer: str = "mpdu") -> str:
        return " ".join(f"{b:02X}" for b in self.layer_bytes(layer))

    def sizes(self) -> Dict[str, int]:
        return {name: len(getattr(self, name)) for name in self._LAYERS}


def build_link_frame(cfg: LinkFrameConfig) -> LinkFrameBuildResult:
    """按配置组装链路层帧。

    SOF：FC [+ 物理块(MAC 帧)]   ｜ 信标：FC + 载荷   ｜ SACK：仅 FC（无物理块/MSDU）
    组帧顺序自内向外：MSDU → MAC 帧头(填 MSDU 长度) → MAC 帧(+CRC-32) → 物理块(+PBCS) → FC(+FCCS)。
    """
    # 载波映射表索引/TMI 统一交给 build_fc → _ensure_cmt_index 解析：
    # 信标帧的该字段只有 4bit，必须按 BPLC 语义反查（见 _ensure_cmt_index 的说明）。
    # 此处若先按 cfg.std_version 反查一次（ISAC 下 136 字节 → TMI 16），
    # cmt_index 就不再是 None，_ensure_cmt_index 的信标特例被跳过 →
    # _fill_fc_beacon 写 4bit 字段时抛「载波映射表索引 超出 4bit 范围：16」。
    fc = build_fc(cfg)
    kind = cfg.frame_kind

    if kind == "beacon":
        payload = bytes(cfg.beacon_payload or b"")
        return LinkFrameBuildResult(fc=fc, payload=payload, mpdu=fc + payload)

    if kind == "sack":
        # SACK 仅 FC 头（表30 覆盖到字节12），无物理块/MSDU
        return LinkFrameBuildResult(fc=fc, mpdu=fc)

    msdu = build_msdu(cfg)
    mac_frame = build_mac_frame(msdu, cfg)
    pb = build_pb_blocks(mac_frame, cfg)
    return LinkFrameBuildResult(
        fc=fc,
        pb=pb,
        mac_header=mac_frame[:len(mac_frame) - len(msdu) - 4],
        msdu=msdu,
        mac_frame=mac_frame,
        mpdu=fc + pb,
    )
