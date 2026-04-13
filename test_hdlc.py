"""
HDLC协议解析测试脚本
演示各种HDLC帧类型的解析
"""
from hdlc_parser import HDLCParser


def test_hdlc_frame(name, frame_bytes):
    """测试并打印HDLC帧解析结果"""
    print(f"\n{'='*80}")
    print(f"测试: {name}")
    print(f"{'='*80}")
    print(f"原始帧: {' '.join(f'{b:02X}' for b in frame_bytes)}")
    print()
    
    parser = HDLCParser()
    table = parser.parse_to_table(frame_bytes)
    
    print(f"{'字段':<25s} | {'原始值':<15s} | {'解析值':<35s} | 说明")
    print("-" * 100)
    for row in table:
        print(f"{row[0]:<25s} | {row[1]:<15s} | {row[2]:<35s} | {row[3]}")


def main():
    print("HDLC协议解析测试 (基于IEC 62056-46标准)")
    print("=" * 80)
    
    # 测试1: SNRM帧 (设置正常响应模式)
    # 7E + 格式域(Type3, Len=7) + 目的地址(0x01) + 源地址(0x01) + 控制域(SNRM, P=1) + HCS(2) + FCS(2) + 7E
    test_hdlc_frame(
        "SNRM帧 (客户端→服务器，建立连接)",
        bytes([
            0x7E,                    # 起始标志
            0xA0, 0x07,              # 格式域: Type=0xA, S=0, Length=7
            0x01,                    # 目的地址: 0x01 (客户端管理进程)
            0x01,                    # 源地址: 0x01
            0x93,                    # 控制域: SNRM, P=1 (0x83 | 0x10)
            0x00, 0x00,              # HCS (占位)
            0x00, 0x00,              # FCS (占位)
            0x7E,                    # 结束标志
        ])
    )
    
    # 测试2: UI帧 (无编号信息帧)
    test_hdlc_frame(
        "UI帧 (无编号信息传输)",
        bytes([
            0x7E,                    # 起始标志
            0xA0, 0x0B,              # 格式域: Type=0xA, S=0, Length=11
            0x01,                    # 目的地址
            0x01,                    # 源地址
            0x03,                    # 控制域: UI, P/F=0
            0x00, 0x00,              # HCS
            0xC0, 0x01, 0x00, 0x00,  # 信息域: DLMS Get-Request
            0x00, 0x00,              # FCS
            0x7E,                    # 结束标志
        ])
    )
    
    # 测试3: I帧 (信息帧，带DLMS数据)
    test_hdlc_frame(
        "I帧 (信息传输帧，携带DLMS APDU)",
        bytes([
            0x7E,                    # 起始标志
            0xA0, 0x15,              # 格式域: Type=0xA, S=0, Length=21
            0x01,                    # 目的地址
            0x01,                    # 源地址
            0x00,                    # 控制域: I帧, N(S)=0, N(R)=0, P/F=0
            0x00, 0x00,              # HCS
            # 信息域: DLMS Get-Request APDU
            0xC0,                    # DLMS控制字段
            0x00, 0x00, 0x00, 0x01,  # 目标地址 (长格式)
            0x01,                    # 源地址
            0xC0,                    # Get-Request
            0x01,                    # 调用ID
            0x01,                    # 选择符
            0x00, 0x00, 0x28, 0x00, 0x00, 0xFF,  # OBIS码 (1.0.1.8.0.255)
            0x02,                    # 属性索引
            0x00, 0x00,              # FCS
            0x7E,                    # 结束标志
        ])
    )
    
    # 测试4: UA帧 (无编号确认)
    test_hdlc_frame(
        "UA帧 (服务器确认SNRM)",
        bytes([
            0x7E,                    # 起始标志
            0xA0, 0x07,              # 格式域: Type=0xA, S=0, Length=7
            0x01,                    # 目的地址
            0x01,                    # 源地址
            0x73,                    # 控制域: UA, F=1 (0x63 | 0x10)
            0x00, 0x00,              # HCS
            0x00, 0x00,              # FCS
            0x7E,                    # 结束标志
        ])
    )
    
    # 测试5: DISC帧 (断开连接)
    test_hdlc_frame(
        "DISC帧 (断开连接)",
        bytes([
            0x7E,                    # 起始标志
            0xA0, 0x07,              # 格式域: Type=0xA, S=0, Length=7
            0x01,                    # 目的地址
            0x01,                    # 源地址
            0x53,                    # 控制域: DISC, P=1 (0x43 | 0x10)
            0x00, 0x00,              # HCS
            0x00, 0x00,              # FCS
            0x7E,                    # 结束标志
        ])
    )
    
    # 测试6: 扩展地址 (2字节地址)
    test_hdlc_frame(
        "扩展地址帧 (2字节地址)",
        bytes([
            0x7E,                    # 起始标志
            0xA0, 0x09,              # 格式域: Type=0xA, S=0, Length=9
            0x02, 0x81,              # 目的地址: 2字节 (0x01 << 7 | 0x00) = 0x80
            0x01,                    # 源地址: 1字节
            0x03,                    # 控制域: UI
            0x00, 0x00,              # HCS
            0x00, 0x00,              # FCS
            0x7E,                    # 结束标志
        ])
    )
    
    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)


if __name__ == "__main__":
    main()
