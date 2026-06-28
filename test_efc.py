#!/usr/bin/env python3
"""测试eFC(扩展帧控制)解析 - DL-OFDMA / UL-OFDMA trigger / UL-OFDMA SACK"""

from csg_new_gen_parser import CSGNewGenParser


def _set_efc_crc(efc: bytearray):
    """计算eFC前13字节CRC-24并写入字节13-15（小端序）"""
    p = CSGNewGenParser()
    crc_val = p._crc24(bytes(efc[:13]))
    efc[13] = crc_val & 0xFF
    efc[14] = (crc_val >> 8) & 0xFF
    efc[15] = (crc_val >> 16) & 0xFF


def build_ofdma_frame(ofdma_type, station_count_minus1, efc_bytes):
    """构造一个OFDMA SOF帧(FC 16字节 + eFC 16字节 + 一些物理块填充)"""
    fc = bytearray(16)
    # 字节0: 定界符类型=1(SOF) + 接入指示=1 + SNID低位=0x1
    fc[0] = 0x01 | (1 << 3) | (0x1 << 4)  # 0x19

    # 字节1-2: 源TEI=0x001, 目的TEI=0x002
    src_tei = 0x001
    dst_tei = 0x002
    fc[1] = src_tei & 0xFF           # byte1 = 0x01
    fc[2] = ((src_tei >> 8) & 0x0F) | ((dst_tei & 0x0F) << 4)  # byte2 = 0x20
    fc[3] = (dst_tei >> 4) & 0xFF    # byte3 = 0x00

    # 字节3(b4): multi_site=1 + OFDMA帧类型 + 频段标识=1 + 站点数
    b4 = 0x01  # multi_site=1
    b4 |= (ofdma_type & 0x03) << 1
    b4 |= (1 & 0x07) << 3  # band_id=1
    b4 |= (station_count_minus1 & 0x03) << 6
    fc[4] = b4

    # 字节4(b5): eFC符号个数=0(2个符号) + 保留
    fc[5] = 0x00

    # 字节5-6: PL符号数=10
    fc[6] = 10
    fc[7] = 0

    # 字节7-8: 帧长=20(200μs)
    fc[8] = 20
    fc[9] = 0

    # 字节12: SNID高位=0 + 标准版本=2(ISAC-PLC)
    fc[12] = 0x02 << 4  # std_version=2

    # 字节13-15: FC校验(简化,填0)
    fc[13] = fc[14] = fc[15] = 0x00

    # 组合: FC + eFC + 填充(模拟物理块)
    frame = bytes(fc) + bytes(efc_bytes) + b'\x00' * 32
    return frame


def test_dl_ofdma_efc():
    """测试DL-OFDMA eFC解析(表27)"""
    print("=" * 60)
    print("测试1: DL-OFDMA eFC (ofdma_type=0, 2站点)")
    print("=" * 60)

    # 构造eFC 16字节
    # TF个数=0(实际2个), 站点0: PB=0(1个), TEI=0x010, TMI=5, RU=3, SACK_RU=2
    # 站点1: PB=1(2个), TEI=0x020, TMI=10, RU=1, SACK_RU=4
    efc = bytearray(16)

    # bit0-1: TF个数=0
    # bit2: PB个数=0 (1个PB)
    # bit3-14: TEI=0x010=16
    tei0 = 0x010
    # bit2=PB0=0
    efc[0] |= (0 << 2)
    # bit3-7: TEI低5位 = 0x010 & 0x1F = 16
    efc[0] |= (tei0 & 0x1F) << 3
    # bit8-14: TEI高7位 = (0x010 >> 5) & 0x7F = 0
    efc[1] |= (tei0 >> 5) & 0x7F
    # bit15-19: TMI=5
    tmi0 = 5
    efc[1] |= (tmi0 & 0x01) << 7  # TMI bit0 → byte1 bit7
    efc[2] |= (tmi0 >> 1) & 0x0F  # TMI bit1-4 → byte2 bit0-3
    # bit20-23: RU=3
    ru0 = 3
    efc[2] |= (ru0 & 0x0F) << 4
    # bit24-26: SACK_RU=2
    sack_ru0 = 2
    efc[3] |= (sack_ru0 & 0x07)

    # 站点1: 起始bit=27
    pb1 = 1  # 2个PB
    tei1 = 0x020
    tmi1 = 10
    ru1 = 1
    sack_ru1 = 4
    # bit27: PB=1
    efc[3] |= (pb1 & 0x01) << 3
    # bit28-39: TEI=0x020=32
    efc[3] |= (tei1 & 0x0F) << 4  # bit28-31
    efc[4] |= (tei1 >> 4) & 0xFF  # bit32-39
    # bit40-44: TMI=10
    efc[5] |= (tmi1 & 0x1F)
    # bit45-48: RU=1
    efc[5] |= (ru1 & 0x0F) << 5
    # bit49-51: SACK_RU=4
    efc[6] |= (sack_ru1 & 0x07) << 1

    # CRC (bytes 13-15) - 自动计算
    _set_efc_crc(efc)

    frame = build_ofdma_frame(ofdma_type=0, station_count_minus1=1, efc_bytes=efc)

    parser = CSGNewGenParser()
    table = parser.parse_to_table(frame, parse_level="fc_pb")

    # 打印结果
    efc_found = False
    for row in table:
        name = row[0]
        if 'eFC' in name or 'OFDMA' in name or '多站点' in name or '站点' in name:
            efc_found = True
            print(f"  {name:30s} | {row[1]:20s} | {row[2]:15s} | {row[3]}")

    assert efc_found, "未找到eFC相关字段!"

    # 验证关键字段
    efc_rows = {r[0]: r for r in table if 'eFC' in r[0] or 'OFDMA' in r[0]}
    assert "OFDMA帧类型" in efc_rows, "缺少OFDMA帧类型"
    assert efc_rows["OFDMA帧类型"][3] == "DL-OFDMA帧", f"OFDMA类型错误: {efc_rows['OFDMA帧类型'][3]}"

    # 检查站点0 TEI
    s0_tei = [r for r in table if '站点0 TEI' in r[0]]
    assert len(s0_tei) > 0, "缺少站点0 TEI"
    print(f"\n  站点0 TEI: {s0_tei[0][1]} → {s0_tei[0][3]}")

    # 检查站点0 SACK_RU无NameError
    s0_sack = [r for r in table if 'SACK_RU' in r[0] and '站点0' in r[0]]
    if s0_sack:
        print(f"  站点0 SACK_RU: {s0_sack[0][1]} → {s0_sack[0][3]}")

    print("\n  [PASS] DL-OFDMA eFC 测试通过\n")


def test_ul_trigger_efc():
    """测试UL-OFDMA trigger eFC解析(表28)"""
    print("=" * 60)
    print("测试2: UL-OFDMA trigger eFC (ofdma_type=2, 1站点)")
    print("=" * 60)

    efc = bytearray(16)
    # TF个数=1(实际4个), 站点0: PB=0(1个), TEI=0x100, TMI=15, RU=5, Tx功率回退=2(8dB)
    tei0 = 0x100
    tmi0 = 15
    ru0 = 5
    tx_backoff = 2

    # bit0-1: TF个数=1
    efc[0] |= 0x01
    # bit2: PB=0
    # bit3-14: TEI=0x100=256
    efc[0] |= (tei0 & 0x1F) << 3
    efc[1] |= (tei0 >> 5) & 0x7F
    # bit15-19: TMI=15
    efc[1] |= (tmi0 & 0x01) << 7
    efc[2] |= (tmi0 >> 1) & 0x0F
    # bit20-23: RU=5
    efc[2] |= (ru0 & 0x0F) << 4
    # bit24-26: Tx功率回退=2
    efc[3] |= (tx_backoff & 0x07)

    efc[13] = 0x11
    efc[14] = 0x22
    efc[15] = 0x33
    _set_efc_crc(efc)

    frame = build_ofdma_frame(ofdma_type=2, station_count_minus1=0, efc_bytes=efc)

    parser = CSGNewGenParser()
    table = parser.parse_to_table(frame, parse_level="fc_pb")

    efc_found = False
    for row in table:
        name = row[0]
        if 'eFC' in name or 'OFDMA' in name or '多站点' in name:
            efc_found = True
            print(f"  {name:35s} | {row[1]:20s} | {row[2]:15s} | {row[3]}")

    assert efc_found, "未找到eFC相关字段!"

    # 验证OFDMA类型
    efc_rows = {r[0]: r for r in table if 'OFDMA' in r[0]}
    assert efc_rows["OFDMA帧类型"][3] == "UL-OFDMA trigger帧"

    # 验证Tx功率回退
    tx_rows = [r for r in table if 'Tx功率回退' in r[0]]
    assert len(tx_rows) > 0, "缺少Tx功率回退字段"
    print(f"\n  Tx功率回退: {tx_rows[0][3]}")

    print("\n  [PASS] UL-OFDMA trigger eFC 测试通过\n")


def test_ul_sack_efc():
    """测试UL-OFDMA SACK eFC解析(表29)"""
    print("=" * 60)
    print("测试3: UL-OFDMA SACK eFC (ofdma_type=3, 2站点)")
    print("=" * 60)

    efc = bytearray(16)
    # 站点0: TEI=0x050, 接收状态=0x1(PB0=OK,PB1=FAIL)
    # 站点1: TEI=0x0A0, 接收状态=0x3(PB0=OK,PB1=OK)
    tei0 = 0x050
    rx0 = 0x1
    tei1 = 0x0A0
    rx1 = 0x3

    # 站点0: bit0-11=TEI, bit12-15=rx_status, bit16-23=reserved
    efc[0] = tei0 & 0xFF          # byte0: TEI低8位
    efc[1] = ((tei0 >> 8) & 0x0F) | ((rx0 & 0x0F) << 4)  # byte1: TEI高4位+rx_status
    efc[2] = 0x00                  # byte2: 保留

    # 站点1: bit24-35=TEI, bit36-39=rx_status, bit40-47=reserved
    efc[3] = tei1 & 0xFF          # byte3: TEI低8位
    efc[4] = ((tei1 >> 8) & 0x0F) | ((rx1 & 0x0F) << 4)  # byte4: TEI高4位+rx_status
    efc[5] = 0x00                  # byte5: 保留

    efc[13] = 0xDD
    efc[14] = 0xEE
    efc[15] = 0xFF
    _set_efc_crc(efc)

    frame = build_ofdma_frame(ofdma_type=3, station_count_minus1=1, efc_bytes=efc)

    parser = CSGNewGenParser()
    table = parser.parse_to_table(frame, parse_level="fc_pb")

    efc_found = False
    for row in table:
        name = row[0]
        if 'eFC' in name or 'OFDMA' in name or '多站点' in name or '站点' in name:
            efc_found = True
            print(f"  {name:35s} | {row[1]:20s} | {row[2]:15s} | {row[3]}")

    assert efc_found, "未找到eFC相关字段!"

    # 验证OFDMA类型
    efc_rows = {r[0]: r for r in table if 'OFDMA' in r[0]}
    assert efc_rows["OFDMA帧类型"][3] == "UL-OFDMA SACK帧"

    # 验证站点0 TEI
    s0_tei = [r for r in table if '站点0 TEI' in r[0]]
    assert len(s0_tei) > 0, "缺少站点0 TEI"
    print(f"\n  站点0 TEI原始值: {s0_tei[0][1]}")

    # 验证接收状态
    s0_rx = [r for r in table if '站点0 接收状态' in r[0]]
    assert len(s0_rx) > 0, "缺少站点0接收状态"
    assert "PB0:OK" in s0_rx[0][2], f"站点0 PB0应为OK, 实际: {s0_rx[0][2]}"
    assert "PB1:FAIL" in s0_rx[0][2], f"站点0 PB1应为FAIL, 实际: {s0_rx[0][2]}"
    print(f"  站点0 接收状态: {s0_rx[0][2]}")

    # 验证站点1接收状态
    s1_rx = [r for r in table if '站点1 接收状态' in r[0]]
    assert len(s1_rx) > 0, "缺少站点1接收状态"
    assert "PB0:OK" in s1_rx[0][2] and "PB1:OK" in s1_rx[0][2]
    print(f"  站点1 接收状态: {s1_rx[0][2]}")

    print("\n  [PASS] UL-OFDMA SACK eFC 测试通过\n")


def test_no_efc_for_type1():
    """测试OFDMA type=1时不解析eFC"""
    print("=" * 60)
    print("测试4: OFDMA type=1 (DL-OFDMA SACK/UL-OFDMA) 无eFC")
    print("=" * 60)

    efc = bytearray(16)  # 即使有数据也不应解析
    frame = build_ofdma_frame(ofdma_type=1, station_count_minus1=0, efc_bytes=efc)

    parser = CSGNewGenParser()
    table = parser.parse_to_table(frame, parse_level="fc_pb")

    efc_rows = [r for r in table if r[0].startswith('eFC:') or r[0] == 'eFC原始数据' or r[0] == 'eFC CRC校验']
    assert len(efc_rows) == 0, f"type=1不应有eFC, 但找到{len(efc_rows)}行"

    ofdma_rows = [r for r in table if 'OFDMA' in r[0]]
    assert len(ofdma_rows) > 0, "应有OFDMA帧类型字段"
    print(f"  OFDMA帧类型: {ofdma_rows[0][3]}")
    print("  确认: 无eFC字段 [OK]")

    print("\n  [PASS] OFDMA type=1 无eFC 测试通过\n")


def test_non_ofdma_no_efc():
    """测试非OFDMA帧不解析eFC"""
    print("=" * 60)
    print("测试5: 非OFDMA单站点帧 无eFC")
    print("=" * 60)

    # 构造普通SOF帧(multi_site=0)
    fc = bytearray(16)
    fc[0] = 0x19  # delimiter=1, access=1, SNID_low=1
    fc[1] = 0x01  # src_tei低8位
    fc[2] = 0x20  # src_tei高4位 + dst_tei低4位
    fc[3] = 0x00  # dst_tei高8位
    fc[4] = 0x04  # multi_site=0, training=0, pb_count=1, streams=0
    fc[5] = 0x04  # TMI=4
    fc[6] = 0x0A  # PL符号数
    fc[8] = 0x14  # 帧长
    fc[12] = 0x20  # 标准版本=2
    frame = bytes(fc) + b'\x00' * 32

    parser = CSGNewGenParser()
    table = parser.parse_to_table(frame, parse_level="fc_pb")

    efc_rows = [r for r in table if r[0].startswith('eFC:') or r[0] == 'eFC原始数据' or r[0] == 'eFC CRC校验']
    assert len(efc_rows) == 0, "非OFDMA帧不应有eFC"

    # 确认训练帧标识/PB数/流数正常解析
    field_names = [r[0] for r in table]
    assert "训练帧标识" in field_names, "非OFDMA帧应有训练帧标识"
    assert "物理块个数" in field_names, "非OFDMA帧应有物理块个数"
    print("  确认: 无eFC字段, 训练帧标识/PB数/流数正常 [OK]")

    print("\n  [PASS] 非OFDMA帧无eFC 测试通过\n")


def test_fc_efc_parse_level():
    """测试fc_efc解析级别：只解析FC+eFC，不解析物理块"""
    print("=" * 60)
    print("测试6: fc_efc解析级别 (FC+eFC后截断，不解析物理块)")
    print("=" * 60)

    efc = bytearray(16)
    # 简单DL-OFDMA eFC: TF=0, 1站点
    efc[0] = 0x00  # TF=0, PB=0
    efc[1] = 0x10  # TEI低7位=0x10
    _set_efc_crc(efc)

    frame = build_ofdma_frame(ofdma_type=0, station_count_minus1=0, efc_bytes=efc)

    parser = CSGNewGenParser()
    table = parser.parse_to_table(frame, parse_level="fc_efc")

    # 确认有eFC字段
    efc_rows = [r for r in table if r[0].startswith('eFC:') or r[0] == 'eFC原始数据']
    assert len(efc_rows) > 0, "fc_efc模式应有eFC字段"

    # 确认无物理块字段
    pb_rows = [r for r in table if '物理块' in r[0]]
    assert len(pb_rows) == 0, f"fc_efc模式不应有物理块, 但找到{len(pb_rows)}行"

    print(f"  eFC字段数: {len(efc_rows)}")
    print(f"  物理块字段数: {len(pb_rows)} (应为0)")
    print("  [PASS] fc_efc解析级别测试通过\n")


if __name__ == "__main__":
    test_dl_ofdma_efc()
    test_ul_trigger_efc()
    test_ul_sack_efc()
    test_no_efc_for_type1()
    test_non_ofdma_no_efc()
    test_fc_efc_parse_level()
    print("=" * 60)
    print("所有eFC测试通过!")
    print("=" * 60)
