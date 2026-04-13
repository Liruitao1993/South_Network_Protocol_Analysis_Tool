"""
测试实际HDLC报文解析
"""
from hdlc_parser import HDLCParser


def test_actual_frame():
    """测试实际报文"""
    parser = HDLCParser()
    
    # 实际报文
    frame_hex = "7E A0 2B 03 03 13 E3 8D E6 E7 00 C2 00 00 07 00 00 63 62 02 FF 02 01 01 02 02 09 0C 07 E8 0A 1D 02 14 17 0F FF FE D4 00 11 01 E6 B3 7E"
    frame_bytes = bytes.fromhex(frame_hex.replace(' ', ''))
    
    print("=" * 100)
    print("实际HDLC报文解析测试")
    print("=" * 100)
    print(f"原始帧: {frame_hex}")
    print(f"帧长度: {len(frame_bytes)} 字节")
    print()
    
    # 表格格式解析
    table = parser.parse_to_table(frame_bytes)
    
    print(f"{'字段':<25s} | {'原始值':<45s} | {'解析值':<35s} | 说明")
    print("-" * 130)
    for row in table:
        print(f"{row[0]:<25s} | {row[1]:<45s} | {row[2]:<35s} | {row[3]}")
    
    print("\n" + "=" * 100)
    print("结构化解析结果")
    print("=" * 100)
    
    result = parser.parse(frame_bytes)
    for key, value in result.items():
        if isinstance(value, dict):
            print(f"\n【{key}】")
            for k, v in value.items():
                print(f"  {k}: {v}")
        else:
            print(f"{key}: {value}")


if __name__ == "__main__":
    test_actual_frame()
