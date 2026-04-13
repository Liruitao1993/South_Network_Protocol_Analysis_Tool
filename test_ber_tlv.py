"""
测试BER-TLV格式的HDLC报文解析
"""
from hdlc_parser import HDLCParser


def test_ber_tlv_frame():
    """测试BER-TLV格式的HDLC帧"""
    parser = HDLCParser()
    
    # 用户提供的报文
    frame_hex = "7E 10 2B 00 01 00 11 00 01 00 1F 61 01 A1 09 06 07 60 85 74 05 08 01 01 BE 10 04 0E 01 00 00 00 06 5F 1F 04 00 00 7E 1F 00 00 9C 8F 7E"
    frame_bytes = bytes.fromhex(frame_hex.replace(' ', ''))
    
    print("=" * 120)
    print("BER-TLV格式HDLC报文解析测试")
    print("=" * 120)
    print(f"原始帧: {frame_hex}")
    print(f"帧长度: {len(frame_bytes)} 字节")
    print()
    
    # 表格格式解析
    table = parser.parse_to_table(frame_bytes)
    
    print(f"{'字段':<30s} | {'原始值':<50s} | {'解析值':<35s} | 说明")
    print("-" * 150)
    for row in table:
        print(f"{row[0]:<30s} | {row[1]:<50s} | {row[2]:<35s} | {row[3]}")
    
    print("\n" + "=" * 120)
    print("分析说明:")
    print("-" * 120)
    print("该报文使用非标准HDLC格式（格式类型=0x1而非0xA）")
    print("信息域包含BER-TLV编码的DLMS数据")
    print("特征:")
    print("  - 0x1F: 高标签号（BER编码）")
    print("  - 0x61: ASN.1 SEQUENCE标签")
    print("  - 0xA1: Context-Specific [1] 标签")
    print("  - 0x09: Visible-String标签")
    print("  - 0x06: Octet-String标签")
    print("=" * 120)


if __name__ == "__main__":
    test_ber_tlv_frame()
