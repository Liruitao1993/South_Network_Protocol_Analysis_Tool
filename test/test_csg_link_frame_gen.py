# -*- coding: utf-8 -*-
"""协议9 链路层组帧（FC / 物理块 / MAC 帧头）对拍测试。

核心思路与 ``test_csg_new_gen_frame_gen.py`` 一致：**组出的帧必须被现有解析器解回同样的值**。
本测试用项目里既有的 ``CSGNewGenParser`` 做唯一基准，不复制第二份字段定义：

- 位打包：``csg_link_frame_gen.put_bits_le`` ↔ ``CSGNewGenParser._extract_bits``（严格互逆）
- 三处校验：FCCS / PBCS / 完整性校验(CRC-32) 的**覆盖范围**由回读「校验通过」反证
- 分层回读：``parse_level`` = ``fc_only`` / ``pb_only`` / ``mac_only`` / ``auto``

运行：``python test/test_csg_link_frame_gen.py``（也可 pytest 收集）。
"""

import _path_setup  # noqa: E402,F401

import csg_link_frame_gen as csg  # noqa: E402
import csg_new_gen_frame_gen as fg  # noqa: E402
from csg_new_gen_parser import CSGNewGenParser  # noqa: E402

_FAILURES = []
_CHECKS = []


def check(name, condition, detail=""):
    _CHECKS.append(name)
    if not condition:
        _FAILURES.append(f"{name} —— {detail}")


def field_of(table, label):
    """从解析表取字段的「解析值」列。"""
    for row in table:
        if row[0] == label:
            return row[2]
    return None


def desc_of(table, label):
    for row in table:
        if row[0] == label:
            return row[3]
    return None


def has_row(table, label):
    return any(row[0] == label for row in table)


def num_of(table, label, default=None):
    """把「解析值」列数字化的宽松版（去掉 μs / 字节 等后缀与 0x 前缀）。"""
    raw = field_of(table, label)
    if raw is None:
        return default
    text = str(raw).strip()
    for suffix in ("字节", "μs", "个PB", "个物理块", "个符号", "流"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return default


def parse(frame, **kwargs):
    return CSGNewGenParser().parse_to_table(bytes(frame), **kwargs)


def app_payload(extra=b"") -> bytes:
    """一段合法的应用层帧（端口 + 报文标识 + 保留 + 业务报文），用作 MSDU 载荷。"""
    return fg.build_app_frame(extra, msg_port=fg.MSG_PORT_MANAGE)


def base_sof(**overrides):
    """SOF 帧的公共基线配置（各用例只覆盖关心字段）。"""
    params = dict(
        frame_kind="sof",
        delimiter_type=csg.DELIM_SOF,
        std_version=csg.STD_VERSION_BPLC,
        snid=0x15,
        src_tei=0x123,
        dest_tei=0x456,
        link_id=0x37,
        frame_len_10us=100,
        symbol_count=0x155,
        retransmit=1,
        tei_filter=1,
        pb_count=1,
        pb_total=136,
        mac_header_type=csg.MAC_HDR_TYPE_SHORT,
        mac_version=csg.MAC_VERSION_STD,
        msdu_seq=7,
        tx_seq=0x9,
        send_type=0,
        max_send=3,
        hop_count=0,
        broadcast_dir=0,
        reboot_count=2,
        dest_mac=bytes.fromhex("AABBCCDDEEFF"),
        vlan=0,
        msdu_type=csg.MSDU_TYPE_APP,
        msdu_payload=app_payload(b"\x01\x02\x03"),
    )
    params.update(overrides)
    return csg.LinkFrameConfig(**params)


# ────────────────────────── 1. 位打包与解析器严格互逆 ──────────────────────────


def test_put_bits_le_roundtrip():
    """put_bits_le 是 _extract_bits 的逆运算，含跨字节/非对齐/边界。"""
    cases = [
        (0, 3, 0x5), (3, 1, 1), (4, 4, 0xA),
        (8, 12, 0x123), (20, 12, 0x456),      # FC 源/目的TEI（跨字节且交错）
        (32, 12, 0xFFF), (44, 12, 0x001),
        (56, 4, 0xF), (60, 4, 0x7),
        (64, 12, 0xABC), (76, 9, 0x1FF),
        (85, 1, 1), (87, 9, 0x155),
        (96, 4, 0xD), (100, 4, 0x2),
    ]
    buf = bytearray(16)
    for start, width, value in cases:
        csg.put_bits_le(buf, start, width, value, f"位{start}/{width}")
    for start, width, value in cases:
        got = CSGNewGenParser._extract_bits(bytes(buf), start, width)
        check(f"put/extract 互逆 {start}+{width}", got == value, f"写入 {value} 读回 {got}")


def test_put_bits_le_wide_fields():
    """宽字段（30bit 非对齐，SACK 的 SNR 评估信息形态）单独测，避免与其它字段区间重叠。"""
    buf = bytearray(8)
    csg.put_bits_le(buf, 8, 30, 0x3FFFFFFF, "30位全1")
    csg.put_bits_le(buf, 40, 16, 0xBEEF, "16位")
    check("30bit 全1 回读", CSGNewGenParser._extract_bits(bytes(buf), 8, 30) == 0x3FFFFFFF)
    check("相邻 16bit 回读", CSGNewGenParser._extract_bits(bytes(buf), 40, 16) == 0xBEEF)
    buf2 = bytearray(4)
    csg.put_bits_le(buf2, 0, 30, 0x155, "30位小值")
    check("30bit 小值回读", CSGNewGenParser._extract_bits(bytes(buf2), 0, 30) == 0x155)


def test_put_bits_le_guards():
    buf = bytearray(2)
    for name, kwargs in (
        ("位宽为0被拒", dict(start_bit=0, width=0, value=0)),
        ("起始位为负被拒", dict(start_bit=-1, width=1, value=0)),
        ("超位宽取值被拒", dict(start_bit=0, width=4, value=0x10)),
        ("负数被拒", dict(start_bit=0, width=4, value=-1)),
        ("缓冲区不足被拒", dict(start_bit=8, width=16, value=1)),
    ):
        try:
            csg.put_bits_le(buf, **kwargs)
        except fg.FrameBuildError:
            check(name, True)
        else:
            check(name, False, f"{kwargs} 竟然通过")


def test_tei_byte_order_oracle():
    """文档表8 自带实例：目的TEI=0x123、源TEI=0x456 → 第4/5/6 字节 = 23 61 45。"""
    buf = bytearray(12)
    csg.put_bits_le(buf, 32, 12, 0x123, "目的TEI")
    csg.put_bits_le(buf, 44, 12, 0x456, "源TEI")
    check("目的TEI 低字节在字节4", buf[4] == 0x23, hex(buf[4]))
    check("TEI 交错字节5", buf[5] == 0x61, hex(buf[5]))
    check("源TEI 高字节在字节6", buf[6] == 0x45, hex(buf[6]))
    # 同一实例经组帧 + 解析器回读
    cfg = base_sof(dest_tei=0x123, src_tei=0x456)
    table = parse(csg.build_mac_frame(csg.build_msdu(cfg), cfg), parse_level="mac_only")
    check("回读原始目的TEI", num_of(table, "原始目的TEI") == 0x123, str(field_of(table, "原始目的TEI")))
    check("回读原始源TEI", num_of(table, "原始源TEI") == 0x456, str(field_of(table, "原始源TEI")))


# ────────────────────────── 2. 契约 C1：接入指示必须为 1 ──────────────────────────


def test_access_indicator_required_for_mpdu():
    """接入指示=1 → 解析器走 MPDU 路径；置 0 → 整帧落到启发式路径（不得通过 MPDU 断言）。"""
    good = parse(csg.build_link_frame(base_sof()).mpdu, parse_level="auto")
    check("接入指示=1 时按 MPDU 解析（出现定界符类型行）", has_row(good, "定界符类型"))

    bad_cfg = base_sof(access_indicator=0)
    bad = parse(csg.build_link_frame(bad_cfg).mpdu, parse_level="auto")
    check(
        "接入指示=0 时不再按 MPDU 解析",
        not has_row(bad, "定界符类型"),
        "置 0 竟然仍被识别为 MPDU —— 本契约的守卫失效",
    )
    check("FC 字节0 bit3 = 接入指示", csg.build_fc(base_sof())[0] & 0x08 == 0x08)


# ────────────────────────── 3. SOF 帧：BPLC / ISAC 整帧回读 ──────────────────────────


def test_sof_bplc_roundtrip():
    cfg = base_sof()
    result = csg.build_link_frame(cfg)
    check("SOF-BPLC FC 长度=16", len(result.fc) == 16, str(len(result.fc)))
    table = parse(result.mpdu, parse_level="auto")

    check("定界符类型", num_of(table, "定界符类型") == csg.DELIM_SOF, str(field_of(table, "定界符类型")))
    check("接入指示", num_of(table, "接入指示") == 1, str(field_of(table, "接入指示")))
    check("短网络标识低位", num_of(table, "短网络标识低位(SNID)") == (cfg.snid & 0x0F), str(field_of(table, "短网络标识低位(SNID)")))
    check("短网络标识高位", num_of(table, "短网络标识高位") == 1, str(field_of(table, "短网络标识高位")))
    check("标准版本号", num_of(table, "标准版本号") == csg.STD_VERSION_BPLC, str(field_of(table, "标准版本号")))
    check("源TEI", num_of(table, "源TEI") == cfg.src_tei, str(field_of(table, "源TEI")))
    check("目的TEI", num_of(table, "目的TEI") == cfg.dest_tei, str(field_of(table, "目的TEI")))
    check("链路标识符", num_of(table, "链路标识符") == cfg.link_id, str(field_of(table, "链路标识符")))
    check("物理块个数", num_of(table, "物理块个数") == cfg.pb_count, str(field_of(table, "物理块个数")))
    check("载波映射表索引", num_of(table, "载波映射表索引") == 4, str(field_of(table, "载波映射表索引")))
    check("帧长(单位10μs)", num_of(table, "帧长") == cfg.frame_len_10us * 10, str(field_of(table, "帧长")))
    check("TEI过滤标志", num_of(table, "TEI过滤标志") == 1, str(field_of(table, "TEI过滤标志")))
    check("重传标志", num_of(table, "重传标志") == 1, str(field_of(table, "重传标志")))
    check("符号数", num_of(table, "符号数") == cfg.symbol_count, str(field_of(table, "符号数")))
    check("FCCS 校验通过", "校验通过" in (desc_of(table, "FC校验序列(FCS)") or ""), str(desc_of(table, "FC校验序列(FCS)")))


def test_sof_isac_data_frame_roundtrip():
    cfg = base_sof(
        std_version=csg.STD_VERSION_ISAC,
        src_tei=0x0AB,
        dest_tei=0x0CD,
        streams=1,
        tf_symbols_cfg=3,
        pl_band=2,
        tf_ext_band=1,
        bitloading=0,
        frame_len_10us=250,
        pb_total=520,
    )
    result = csg.build_link_frame(cfg)
    table = parse(result.mpdu, parse_level="auto")

    check("ISAC 标准版本号", num_of(table, "标准版本号") == csg.STD_VERSION_ISAC, str(field_of(table, "标准版本号")))
    check("ISAC 源TEI", num_of(table, "源TEI") == cfg.src_tei, str(field_of(table, "源TEI")))
    check("ISAC 目的TEI", num_of(table, "目的TEI") == cfg.dest_tei, str(field_of(table, "目的TEI")))
    check("多站点帧标识=0", num_of(table, "多站点帧标识") == 0, str(field_of(table, "多站点帧标识")))
    check("训练帧标识=0", num_of(table, "训练帧标识") == 0, str(field_of(table, "训练帧标识")))
    check("ISAC 物理块个数", num_of(table, "物理块个数") == cfg.pb_count, str(field_of(table, "物理块个数")))
    check("ISAC 流数", num_of(table, "流数") == cfg.streams, str(field_of(table, "流数")))
    check("TF符号数=(配置+1)*2", num_of(table, "TF符号数") == (cfg.tf_symbols_cfg + 1) * 2, str(field_of(table, "TF符号数")))
    check("PL频段标识", num_of(table, "PL频段标识") == cfg.pl_band, str(field_of(table, "PL频段标识")))
    check("TF扩展频段", num_of(table, "TF扩展频段") == cfg.tf_ext_band, str(field_of(table, "TF扩展频段")))
    check("Bitloading标识=0", num_of(table, "Bitloading标识") == 0, str(field_of(table, "Bitloading标识")))
    check("TMI编号=0(PB 520)", num_of(table, "TMI编号") == 0, str(field_of(table, "TMI编号")))
    check("ISAC 帧长", num_of(table, "帧长") == cfg.frame_len_10us * 10, str(field_of(table, "帧长")))
    check("ISAC FCCS 校验通过", "校验通过" in (desc_of(table, "FC校验序列(FCS)") or ""), str(desc_of(table, "FC校验序列(FCS)")))


def test_sof_isac_bitloading_pb_size():
    """Bitloading=1 时填物理块大小码，并据其推导 PB 大小。"""
    cfg = base_sof(
        std_version=csg.STD_VERSION_ISAC,
        bitloading=1,
        pb_total=72,          # → 大小码 2（0:136 1:520 2:72 3:264）
    )
    table = parse(csg.build_link_frame(cfg).mpdu, parse_level="auto")
    check("Bitloading标识=1", num_of(table, "Bitloading标识") == 1, str(field_of(table, "Bitloading标识")))
    check("物理块大小码=2", num_of(table, "物理块大小码") == 2, str(field_of(table, "物理块大小码")))
    check("Bitloading PB 大小解析为 72", "72" in (desc_of(table, "物理块大小码") or ""), str(desc_of(table, "物理块大小码")))
    check("Bitloading 模式 FCCS 通过", "校验通过" in (desc_of(table, "FC校验序列(FCS)") or ""), str(desc_of(table, "FC校验序列(FCS)")))


# ────────────────────────── 4. 信标帧 / SACK ──────────────────────────


def test_beacon_frame_roundtrip():
    cfg = csg.LinkFrameConfig(
        frame_kind="beacon",
        delimiter_type=csg.DELIM_BEACON,
        std_version=csg.STD_VERSION_BPLC,
        snid=0x15,
        src_tei=0x0FF,
        beacon_timestamp=0x11223344,
        beacon_cycle=0x55667788,
        # ⚠ 符号数只覆盖低 8 位有效区间（0~255，此处取偶数）：
        #   解析器把符号数第 9 位读在 bits 103，而 bits 100-103 是标准版本号，两者冲突。
        #   本例取 BPLC 版本(1) → 字节12 高4位 = 0001，其 bit7（=解析器读的第9位）为 0，
        #   与写入的第 9 位 0 一致，故回读自洽。详见 csg_link_frame_gen 注释。
        symbol_count=0x0AA,
        beacon_phase=2,
        pb_total=136,
        beacon_payload=b"\xAA\xBB\xCC",
    )
    result = csg.build_link_frame(cfg)
    check("信标帧无物理块", result.pb == b"", f"得到 {len(result.pb)} 字节")
    check("信标整帧 = FC + 载荷", len(result.mpdu) == 16 + 3, str(len(result.mpdu)))
    table = parse(result.mpdu, parse_level="auto")

    check("信标定界符类型", num_of(table, "定界符类型") == csg.DELIM_BEACON, str(field_of(table, "定界符类型")))
    check("信标时间戳", num_of(table, "信标时间戳") == cfg.beacon_timestamp, str(field_of(table, "信标时间戳")))
    check("信标周期计数", num_of(table, "信标周期计数") == cfg.beacon_cycle, str(field_of(table, "信标周期计数")))
    check("信标源TEI", num_of(table, "源TEI") == cfg.src_tei, str(field_of(table, "源TEI")))
    check("信标载波映射表索引", num_of(table, "载波映射表索引") == 4, str(field_of(table, "载波映射表索引")))
    check("信标符号数(含第9位)", num_of(table, "符号数") == cfg.symbol_count, str(field_of(table, "符号数")))
    check("信标 SNID 高位", num_of(table, "短网络标识高位") == 1, str(field_of(table, "短网络标识高位")))
    check("相线", num_of(table, "相线") == cfg.beacon_phase, str(field_of(table, "相线")))
    check("信标 FCCS 校验通过", "校验通过" in (desc_of(table, "FC校验序列(FCS)") or ""), str(desc_of(table, "FC校验序列(FCS)")))


def test_sack_frame_roundtrip():
    cfg = csg.LinkFrameConfig(
        frame_kind="sack",
        delimiter_type=csg.DELIM_SACK,
        std_version=csg.STD_VERSION_BPLC,
        snid=3,
        dest_tei=0x1A2,
        sack_rx_result=1,
        sack_rx_status=0x0D,
        sack_rx_pb_count=2,
        sack_snr_type=1,
        sack_snr_value=27,
    )
    result = csg.build_link_frame(cfg)
    check("SACK 整帧仅 FC 16 字节", result.mpdu == result.fc and len(result.fc) == 16, str(len(result.mpdu)))
    table = parse(result.mpdu, parse_level="auto")

    check("SACK 定界符类型", num_of(table, "定界符类型") == csg.DELIM_SACK, str(field_of(table, "定界符类型")))
    check("接收结果", num_of(table, "接收结果") == cfg.sack_rx_result, str(field_of(table, "接收结果")))
    check("接收状态", num_of(table, "接收状态") == cfg.sack_rx_status, str(field_of(table, "接收状态")))
    check("SACK 目的TEI", num_of(table, "目的TEI") == cfg.dest_tei, str(field_of(table, "目的TEI")))
    check("接收物理块个数", num_of(table, "接收物理块个数") == cfg.sack_rx_pb_count, str(field_of(table, "接收物理块个数")))
    check("SACK SNR类型", num_of(table, "SNR类型") == cfg.sack_snr_type, str(field_of(table, "SNR类型")))
    check("SNR评估信息按解析器语义回读", "SNR: 27" in (desc_of(table, "SNR评估信息") or ""), str(desc_of(table, "SNR评估信息")))
    check("扩展帧类型=0", num_of(table, "扩展帧类型") == 0, str(field_of(table, "扩展帧类型")))
    check("SACK FCCS 校验通过", "校验通过" in (desc_of(table, "FC校验序列(FCS)") or ""), str(desc_of(table, "FC校验序列(FCS)")))


def test_sack_snr_ru_list():
    """SNR类型=2：6 个 5bit 基础 RU 值。"""
    cfg = csg.LinkFrameConfig(
        frame_kind="sack", delimiter_type=csg.DELIM_SACK,
        sack_snr_type=2, sack_snr_ru=(1, 2, 3, 4, 5, 6),
    )
    table = parse(csg.build_link_frame(cfg).mpdu, parse_level="auto")
    desc = desc_of(table, "SNR评估信息") or ""
    check("RU SNR 逐项回读", all(f"RU{i}={i + 1}" in desc for i in range(6)), desc)


# ────────────────────────── 5. 物理块（PBH + PBCS） ──────────────────────────


def test_pb_header_and_pbcs_roundtrip():
    cfg = base_sof()
    mac_frame = csg.build_mac_frame(csg.build_msdu(cfg), cfg)
    pb = csg.build_pb_blocks(mac_frame, cfg)
    check("单 PB 总长 = 136", len(pb) == 136, str(len(pb)))
    check("块体大小 = 总长 - 8", csg.pb_body_size(136) == 128, str(csg.pb_body_size(136)))

    table = parse(pb, parse_level="pb_only", pb_frame_type="sof")
    check("PB 序列号", num_of(table, "  序列号") == 0, str(field_of(table, "  序列号")))
    check("PB 聚合标志", num_of(table, "  聚合标志") == 0, str(field_of(table, "  聚合标志")))
    pbcs_desc = desc_of(table, "物理块检查序列") or ""
    check("PBCS 校验通过", "校验通过" in pbcs_desc, pbcs_desc)
    check("PBCS 覆盖范围为 头+体+保留", "共133字节" in pbcs_desc, pbcs_desc)


def test_multi_pb_reassembly():
    """多 PB：MAC 帧跨块，解析器重组后仍能读出完整 MAC/MSDU 树。"""
    # 3 个 136 字节 PB 的块体容量 = 3×128 = 384 字节；
    # MAC 帧 = 短头12 + MSDU头2 + 应用层帧 + CRC32 4，故载荷取 300 字节留足余量。
    payload = (bytes(range(256)) + bytes(range(44)))[:300]
    cfg = base_sof(pb_count=3, pb_total=136, msdu_payload=app_payload(payload))
    result = csg.build_link_frame(cfg)
    check("3 个 PB 总长 = 408", len(result.pb) == 136 * 3, str(len(result.pb)))
    check("3 PB 容量足够", len(result.mac_frame) <= 128 * 3, str(len(result.mac_frame)))

    table = parse(result.mpdu, parse_level="auto")
    check("多 PB 物理块个数", num_of(table, "物理块个数") == 3, str(field_of(table, "物理块个数")))
    check("多 PB 首块序列号", num_of(table, "  序列号[0]") == 0, str(field_of(table, "  序列号[0]")))
    check("多 PB 末块序列号", num_of(table, "  序列号[2]") == 2, str(field_of(table, "  序列号[2]")))
    check("多 PB 承载 MAC 帧(多PB重组)", "多PB重组" in (desc_of(table, "物理块体[0]") or ""), str(desc_of(table, "物理块体[0]")))
    check("多 PB MSDU长度", num_of(table, "MSDU长度") == len(result.msdu), f"{field_of(table, 'MSDU长度')} vs {len(result.msdu)}")
    check("多 PB PBCS 通过", all(
        "校验通过" in (desc_of(table, f"物理块检查序列[{i}]") or "") for i in range(3)),
        str([desc_of(table, f"物理块检查序列[{i}]") for i in range(3)]))


def test_pb_size_and_cmt_consistent():
    """PB 大小自动反查 cmt_index，回读应**不出现**「PB大小推断」行。"""
    for pb_total, expect_cmt in ((136, 4), (520, 8)):
        cfg = base_sof(pb_total=pb_total)
        check(f"PB{pb_total} 反查 cmt", csg.cmt_index_for_pb_size(pb_total, csg.STD_VERSION_BPLC) == expect_cmt,
              str(csg.cmt_index_for_pb_size(pb_total, csg.STD_VERSION_BPLC)))
        table = parse(csg.build_link_frame(cfg).mpdu, parse_level="auto")
        check(f"PB{pb_total} 无「PB大小推断」行", not has_row(table, "PB大小推断"),
              "出现推断行说明 PB 大小与 FC 声明不自洽")
        check(f"PB{pb_total} 载波映射表索引", num_of(table, "载波映射表索引") == expect_cmt,
              str(field_of(table, "载波映射表索引")))

    isac520 = base_sof(std_version=csg.STD_VERSION_ISAC, pb_total=520)
    table520 = parse(csg.build_link_frame(isac520).mpdu, parse_level="auto")
    check("ISAC PB520 反查 TMI=0", num_of(table520, "TMI编号") == 0, str(field_of(table520, "TMI编号")))
    check("ISAC PB520 无推断行", not has_row(table520, "PB大小推断"))

    # ISAC PB264（TMI=9）—— ⚠ 已知限制，只验证**组帧侧**正确性
    #   解析器 `_detect_channel` 的 ISAC 分支用**硬编码 4 值表** {0:136,1:520,2:72,3:264}
    #   （而非 `ISAC_PB_MAP`），且 `byte6` 高 4 位会成为「HRF 载荷PB大小=40」的强信号：
    #   TMI=9 → byte6 = (9<<1) = 0x12 → 高 4 位 1 → HRF 表值 1 = 40 字节 → 该帧被判成 HRF 通道，
    #   走无线可变区域布局，回读拿不到「TMI编号」行。
    #   故此处断言 FC 里确实写入了 TMI=9 且 FCCS 通过，**不断言回读结果**；
    #   解析器修复后应改为断言回读（届时本注释与断言同步更新）。
    fc264 = csg.build_fc(base_sof(std_version=csg.STD_VERSION_ISAC, pb_total=264))
    check("ISAC PB264 组帧写入 TMI=9", (fc264[6] >> 1) & 0x1F == 9, hex(fc264[6]))
    check("ISAC PB264 FCCS 校验通过",
          "校验通过" in (desc_of(parse(fc264, parse_level="fc_only"), "FC校验序列(FCS)") or ""))


# ────────────────────────── 6. MAC 帧头（长/短）与 MSDU 头联动 ──────────────────────────


def test_mac_short_header_roundtrip():
    cfg = base_sof()
    result = csg.build_link_frame(cfg)
    check("短头 12 字节", len(result.mac_header) == 12, str(len(result.mac_header)))
    check("MSDU 头 2 字节（短头）", len(result.msdu) == 2 + len(cfg.msdu_payload), str(len(result.msdu)))

    table = parse(result.mac_frame, parse_level="mac_only", pb_frame_type="sof")
    check("帧头类型=1", num_of(table, "帧头类型") == 1, str(field_of(table, "帧头类型")))
    check("MAC 版本=1", num_of(table, "版本") == 1, str(field_of(table, "版本")))
    check("发送序号", num_of(table, "发送序号") == cfg.tx_seq, str(field_of(table, "发送序号")))
    check("MSDU长度", num_of(table, "MSDU长度") == len(result.msdu), str(field_of(table, "MSDU长度")))
    check("重启次数", num_of(table, "重启次数") == cfg.reboot_count, str(field_of(table, "重启次数")))
    check("发送类型", num_of(table, "发送类型") == cfg.send_type, str(field_of(table, "发送类型")))
    check("发送次数限值", num_of(table, "发送次数限值") == cfg.max_send, str(field_of(table, "发送次数限值")))
    check("MSDU序列号", num_of(table, "MSDU序列号") == cfg.msdu_seq, str(field_of(table, "MSDU序列号")))
    check("短头无目的MAC地址行", not has_row(table, "目的MAC地址"))
    check("短 MSDU 头 VLAN", num_of(table, "VLAN标签") == cfg.vlan, str(field_of(table, "VLAN标签")))
    check("短 MSDU 头类型", num_of(table, "MSDU类型") == cfg.msdu_type, str(field_of(table, "MSDU类型")))
    check("MAC CRC-32 校验通过", "校验通过" in (desc_of(table, "完整性校验(CRC-32)") or ""),
          str(desc_of(table, "完整性校验(CRC-32)")))
    check("MAC CRC-32 覆盖范围为 MSDU 负载", "MSDU负载" in (desc_of(table, "完整性校验(CRC-32)") or ""),
          str(desc_of(table, "完整性校验(CRC-32)")))


def test_mac_long_header_msdu_header_follows():
    """帧头类型=0（32B 长头）→ MSDU 头必须变 18 字节长头。"""
    cfg = base_sof(mac_header_type=csg.MAC_HDR_TYPE_LONG)
    result = csg.build_link_frame(cfg)
    check("长头 32 字节", len(result.mac_header) == 32, str(len(result.mac_header)))
    check("MSDU 头 18 字节（长头）", len(result.msdu) == 18 + len(cfg.msdu_payload), str(len(result.msdu)))

    table = parse(result.mac_frame, parse_level="mac_only", pb_frame_type="sof")
    check("帧头类型=0", num_of(table, "帧头类型") == 0, str(field_of(table, "帧头类型")))
    check("长头出现目的MAC地址", has_row(table, "目的MAC地址"))
    check("MSDU头-原始目的地址", has_row(table, "MSDU头-原始目的地址"))
    check("MSDU头-原始源地址", has_row(table, "MSDU头-原始源地址"))
    check("长 MSDU 头 VLAN", num_of(table, "VLAN标签") == cfg.vlan, str(field_of(table, "VLAN标签")))
    check("MAC CRC-32 校验通过（长头）", "校验通过" in (desc_of(table, "完整性校验(CRC-32)") or ""),
          str(desc_of(table, "完整性校验(CRC-32)")))


def test_msdu_header_type_mismatch_is_rejected():
    """MSDU 头长度必须与 MAC 帧头类型一致，不允许用户单独设成不匹配的值。"""
    cfg = base_sof(mac_header_type=csg.MAC_HDR_TYPE_SHORT, msdu_header_type=csg.MAC_HDR_TYPE_LONG)
    try:
        csg.build_msdu_header(cfg)
        check("MSDU 头类型与帧头类型不一致被拒", False, "竟然允许组出解析器认不出的帧")
    except fg.FrameBuildError:
        check("MSDU 头类型与帧头类型不一致被拒", True)


# ────────────────────────── 7. 分层回读（fc_only / pb_only / mac_only） ──────────────────────────


def test_fc_only_readback():
    cfg = base_sof()
    result = csg.build_link_frame(cfg)
    fc_table = parse(result.fc, parse_level="fc_only")
    check("fc_only 仅出 FC 字段（无物理块头）", has_row(fc_table, "定界符类型") and not has_row(fc_table, "物理块头"))
    check("fc_only FCCS 通过", "校验通过" in (desc_of(fc_table, "FC校验序列(FCS)") or ""))


def test_manual_hex_payload():
    """手工 HEX 作为 MSDU 载荷。"""
    manual = bytes.fromhex("110101000200010000000203")
    cfg = base_sof(msdu_payload=manual)
    result = csg.build_link_frame(cfg)
    table = parse(result.mpdu, parse_level="auto")
    check("手工 HEX 载荷长度进入 MSDU长度", num_of(table, "MSDU长度") == len(result.msdu), str(field_of(table, "MSDU长度")))
    check("手工应用层帧被展开（报文端口号）", has_row(table, "报文端口号"), str([r[0] for r in table][-8:]))
    check("手工载荷 MAC CRC 通过", "校验通过" in (desc_of(table, "完整性校验(CRC-32)") or ""),
          str(desc_of(table, "完整性校验(CRC-32)")))


# ────────────────────────── 8. 错误路径 ──────────────────────────


def test_illegal_configurations_rejected():
    cases = [
        ("未知帧类型被拒", dict(frame_kind="net")),
        ("定界符与帧类型不符被拒", dict(delimiter_type=csg.DELIM_SACK)),
        ("HRF 信道本期未支持", dict(channel="hrf")),
        ("单跳 MAC 头本期未支持", dict(mac_version=2)),
        ("ISAC 多站点帧本期未支持", dict(std_version=csg.STD_VERSION_ISAC, multi_site=1)),
        ("SACK 扩展帧类型本期限 0", dict(frame_kind="sack", delimiter_type=csg.DELIM_SACK, sack_ext_type=3)),
        ("TEI 超 12bit 被拒", dict(dest_tei=0x1000)),
        ("SNID 超 5bit 被拒", dict(snid=0x20)),
        ("PB 大小非法被拒", dict(pb_total=200)),
        ("BPLC 不支持 264 字节 PB", dict(pb_total=264)),
        ("PB 个数为 0 被拒", dict(pb_count=0)),
    ]
    for name, overrides in cases:
        cfg = base_sof(**overrides)
        try:
            csg.build_link_frame(cfg)
        except fg.FrameBuildError:
            check(name, True)
        else:
            check(name, False, f"{overrides} 竟然通过")


def test_pb_capacity_guard():
    """MAC 帧超过 PB 容量时必须报错，而不是静默截断。"""
    cfg = base_sof(pb_count=1, pb_total=136, msdu_payload=app_payload(bytes(200)))
    try:
        csg.build_link_frame(cfg)
    except fg.FrameBuildError as exc:
        check("超出 PB 容量被拒", "容量" in str(exc), str(exc))
    else:
        check("超出 PB 容量被拒", False, "竟然静默通过")


# ────────────────────────── 9. 结果对象与下拉候选 ──────────────────────────


def test_result_layers_and_hex():
    result = csg.build_link_frame(base_sof())
    sizes = result.sizes()
    check("sizes 含全部层次", set(sizes) == {"fc", "pb", "mac_header", "msdu", "mac_frame", "payload", "mpdu"},
          str(sorted(sizes)))
    check("mpdu = fc + pb", len(result.mpdu) == len(result.fc) + len(result.pb), str(sizes))
    check("mpdu hex 可读", result.hex("mpdu").split()[0] == f"{result.mpdu[0]:02X}")
    try:
        result.hex("nope")
    except fg.FrameBuildError:
        check("未知层次被拒", True)
    else:
        check("未知层次被拒", False)


def test_choices_derive_from_parser_constants():
    """下拉候选必须来自解析器常量（防第二份协议取值表）。"""
    import csg_new_gen_parser as _pm          # 模块级常量（表13/表4/表5/表10/表9）
    from csg_new_gen_parser import CSGNewGenParser as P  # 类级常量（表15/表19/表32）

    for name, choices, mapping in (
        ("delimiter", csg.delimiter_choices(), P.DELIMITER_TYPE_MAP),
        ("std_version", csg.std_version_choices(), _pm.MPDU_VERSION_MAP),
        ("mac_header_type", csg.mac_header_type_choices(), _pm.MAC_HEADER_TYPE_MAP),
        ("mac_version", csg.mac_version_choices(), _pm.MAC_VERSION_MAP),
        ("send_type", csg.send_type_choices(), _pm.SEND_TYPE_MAP),
        ("broadcast_dir", csg.broadcast_dir_choices(), _pm.BROADCAST_DIR_MAP),
        ("beacon_phase", csg.beacon_phase_choices(), P.BEACON_PHASE_MAP),
        ("sack_snr_type", csg.sack_snr_type_choices(), P.SACK_SNR_TYPE_MAP),
    ):
        values = [v for v, _ in choices]
        check(f"{name} 候选取自解析器常量", all(v in mapping for v in values), str(values))
        check(f"{name} 候选项有说明文案", all(str(label).strip() for _, label in choices))

    msdu_values = [v for v, _ in csg.msdu_type_choices()]
    check("MSDU 类型含应用层报文", csg.MSDU_TYPE_APP in msdu_values, str(msdu_values))
    check("pb_body_size(520)=512", csg.pb_body_size(520) == 512, str(csg.pb_body_size(520)))
    check("bl_pb_size_code(264)=3", csg.bl_pb_size_code(264) == 3, str(csg.bl_pb_size_code(264)))
    check("cmt_index_for_pb_size(ISAC 264)=9",
          csg.cmt_index_for_pb_size(264, csg.STD_VERSION_ISAC) == 9,
          str(csg.cmt_index_for_pb_size(264, csg.STD_VERSION_ISAC)))


def main():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"检查项：{len(_CHECKS)} 项，失败 {len(_FAILURES)} 项")
    if _FAILURES:
        for item in _FAILURES:
            print(f"  [FAIL] {item}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
