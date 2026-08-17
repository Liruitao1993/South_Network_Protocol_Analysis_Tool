
#!/usr/bin/env python3

"""Test SACK frame parsing after offset fix.

Verifies that byte 12 is parsed as 扩展帧类型 (not 短网络标识高位)
and that the SACK variable area bytes 1-11 are correctly consumed.
"""
import _path_setup  # noqa: E402

from csg_new_gen_parser import CSGNewGenParser

def build_sack_frame():
    """Build a minimal SACK MPDU frame for testing.
    
    Frame structure:
    - Byte 0 (FC fixed): delimiter=2(SACK), access=1, SNID_low=5
    - Bytes 1-11 (SACK variable area):
      - Byte 1: rx_result(4b)=0(all ok) + rx_status(4b)=0b1010
      - Bytes 2-3: dst_tei(12b)=0x123, rx_pb_count(4b)=3
      - Byte 4: snid_high(1b)=1, snr_type(2b)=0(no SNR), reserved(5b)=0
      - Bytes 5-8: SNR info (30b) + reserved (2b) = 4 bytes
      - Bytes 9-11: reserved (24b) = 3 bytes
    - Byte 12: ext_type(4b)=0(SACK), version(4b)=1(BPLC)
    - Bytes 13-15: FCS (24-bit CRC)
    """
    frame = bytearray(16)  # 16-byte FC header
    
    # Byte 0: delimiter=2(010), access=1, SNID_low=5(0101)
    # bit0-2=delimiter, bit3=access, bit4-7=SNID_low
    frame[0] = 0b01010101  # 0x55: delim=2, access=1, SNID_low=5
    
    # Byte 1: rx_result=0(all ok, bits 0-3), rx_status=0b1010 (PB0 ok, PB1 fail, PB2 ok, PB3 fail, bits 4-7)
    frame[1] = 0b10100000  # 0xA0
    
    # Bytes 2-3: dst_tei(12b)=0x123
    # byte2 = 0x23 (low 8 bits of TEI)
    # byte3 bits 0-3 = 0x1 (high 4 bits of TEI)
    # byte3 bits 4-7 = 0x3 (rx_pb_count)
    frame[2] = 0x23
    frame[3] = 0x31  # 0x31 = 0b00110001: rx_count=3(bits4-7), tei_high=1(bits0-3)
    
    # Byte 4: snid_high(1b)=1, snr_type(2b)=0, reserved(5b)=0
    frame[4] = 0b00000001  # snid_high=1
    
    # Bytes 5-8: SNR info (30 bits) + reserved (2 bits) = 32 bits = 4 bytes
    # SNR type=0 so info is reserved, fill with 0x00
    frame[5] = 0x00
    frame[6] = 0x00
    frame[7] = 0x00
    frame[8] = 0x00
    
    # Bytes 9-11: reserved = 3 bytes
    frame[9] = 0x00
    frame[10] = 0x00
    frame[11] = 0x00
    # bits 0-2=delim(2=010), bit3=access(1), bits 4-7=SNID_low(5=0101)
    frame[0] = 0b01011010  # 0x5A: delim=2, access=1, SNID_low=5
    # Byte 12: ext_type(4b)=0(SACK), version(4b)=1(BPLC)
    frame[12] = 0x10  # 0b00010000: version=1(bits4-7), ext_type=0(bits0-3)
    
    # Bytes 13-15: FCS placeholder
    frame[13] = 0x00
    frame[14] = 0x00
    frame[15] = 0x00
    
    return bytes(frame)


def test_sack_parsing():
    parser = CSGNewGenParser()
    frame = build_sack_frame()
    
    print(f"Frame hex: {' '.join(f'{b:02X}' for b in frame)}")
    print(f"Byte 0: 0x{frame[0]:02X} -> delim={frame[0]&7}, access={(frame[0]>>3)&1}, SNID_low={(frame[0]>>4)&0xF}")
    print(f"Byte 12: 0x{frame[12]:02X} -> ext_type={frame[12]&0xF}, version={(frame[12]>>4)&0xF}")
    print()
    
    # Parse using the MPDU frame parser
    offset, table = parser._parse_mpdu_frame(frame, base_offset=0)
    
    print("Parsed fields:")
    for row in table:
        name, raw, val, desc = row[0], row[1], row[2], row[3]
        print(f"  {name}: raw={raw}, val={val}, desc={desc}")
    
    # Verify specific fields
    field_names = [row[0] for row in table]
    
    print()
    
    # Check: 扩展帧类型 should appear (not 短网络标识高位 for SACK)
    has_ext_type = "扩展帧类型" in field_names
    has_nid_high = "短网络标识高位" in field_names
    
    print(f"Has 扩展帧类型: {has_ext_type}")
    print(f"Has 短网络标识高位: {has_nid_high}")
    
    # Find the 扩展帧类型 value
    for row in table:
        if row[0] == "扩展帧类型":
            print(f"扩展帧类型 value: {row[2]} (should be 0 = SACK)")
            assert row[2] == "0", f"Expected ext_type=0, got {row[2]}"
    
    # Find 标准版本号
    for row in table:
        if row[0] == "标准版本号":
            print(f"标准版本号 value: {row[2]} (should be 1 = BPLC)")
            assert row[2] == "1", f"Expected version=1, got {row[2]}"
    
    # Find 接收结果
    for row in table:
        if row[0] == "接收结果":
            print(f"接收结果 value: {row[2]} (should be 0 = all ok)")
            assert row[2] == "0", f"Expected rx_result=0, got {row[2]}"
    
    # Find 目的TEI
    for row in table:
        if row[0] == "目的TEI":
            print(f"目的TEI value: {row[2]} (should be 0x123 = 291)")
            assert row[2] == "291", f"Expected dst_tei=291, got {row[2]}"
    
    print()
    print("[OK] SACK frame parsing test PASSED")


def test_bitloading_extension_frame():
    """测试 Bitloading 扩展帧（SACK 扩展帧类型=3）按 Bitloading 格式解析可变区域。

    帧结构：
    - Byte 0: 0x1A = delim=2(SACK), access=1, SNID_low=1
    - Byte 1-2: 源TEI=0x002
    - Byte 2-3: 目的TEI=0x001
    - Byte 4: 0x06 = snid_high=0, Bitloading帧类型=3(训练请求拒绝), 拒绝原因=0
    - Byte 5-11: 保留
    - Byte 12: 0x23 = 扩展帧类型=3(Bitloading), 版本=2(ISAC)
    - Byte 13-15: FCS
    """
    frame_hex = "1A02100006000000000000002367F263"
    frame_bytes = bytes.fromhex(frame_hex)

    parser = CSGNewGenParser()
    table = parser.parse_to_table(frame_bytes, parse_level="auto")
    field_names = [row[0] for row in table]

    print(f"\nFrame hex: {frame_hex}")
    print(f"Frame length: {len(frame_bytes)} bytes")
    print("Parsed fields:")
    for row in table:
        if len(row) >= 4:
            print(f"  {row[0]}: raw={row[1]}, val={row[2]}, desc={row[3]}")

    assert "源TEI" in field_names, "Bitloading扩展帧应解析源TEI"
    assert "目的TEI" in field_names, "Bitloading扩展帧应解析目的TEI"
    assert "Bitloading帧类型" in field_names, "应解析Bitloading帧类型"
    assert "拒绝原因" in field_names, "训练请求拒绝帧应解析拒绝原因"

    # 验证字段值
    ext_type_row = next((r for r in table if r[0] == "扩展帧类型"), None)
    assert ext_type_row is not None and ext_type_row[2] == "3", "扩展帧类型应为3"

    bl_type_row = next((r for r in table if r[0] == "Bitloading帧类型"), None)
    assert bl_type_row is not None and bl_type_row[2] == "3", "Bitloading帧类型应为3(训练请求拒绝)"

    reason_row = next((r for r in table if r[0] == "拒绝原因"), None)
    assert reason_row is not None and reason_row[2] == "0", "拒绝原因应为0(站点正在训练)"

    # 不应出现标准SACK的"接收结果"字段
    assert "接收结果" not in field_names, "Bitloading扩展帧不应按标准SACK解析可变区域"

    print("[OK] Bitloading extension frame parsing test PASSED")


def test_controller_extension_frames():
    """测试扩展帧类型 1/2/保留值按原始字节展示，不崩溃。"""
    parser = CSGNewGenParser()
    for ext_type, expected_name in [(1, "网络搜索帧"), (2, "同步帧"), (6, "保留")]:
        # 构造 16 字节 SACK 帧，字节 12 扩展帧类型 = ext_type
        frame = bytearray(16)
        frame[0] = 0x1A  # delim=2, access=1, SNID_low=1
        frame[1] = 0x02  # 源TEI低8位
        frame[2] = 0x10
        frame[3] = 0x00
        frame[4] = 0x06  # Bitloading帧类型字段(对非Bitloading无意义)
        frame[5:12] = bytes([0] * 7)
        frame[12] = (0x02 << 4) | (ext_type & 0x0F)  # version=2, ext_type
        frame[13:16] = bytes([0, 0, 0])
        frame_hex = frame.hex().upper()
        table = parser.parse_to_table(bytes(frame), parse_level="auto")
        field_names = [row[0] for row in table]
        print(f"\nExt type {ext_type}: {frame_hex}")
        assert "扩展帧类型" in field_names
        assert "标准版本号" in field_names
        # 不应出现标准 SACK 的"接收结果"字段
        assert "接收结果" not in field_names, f"扩展帧类型{ext_type}不应按标准SACK解析"
        print(f"[OK] 扩展帧类型 {ext_type} ({expected_name}) 处理正常")
    print("[OK] Controller/reserved extension frame tests PASSED")


if __name__ == "__main__":
    test_sack_parsing()
    test_bitloading_extension_frame()
    test_controller_extension_frames()
