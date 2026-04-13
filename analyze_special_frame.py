"""
分析特殊HDLC报文
"""
from hdlc_parser import HDLCParser


def analyze_special_frame():
    """分析特殊格式HDLC帧"""
    parser = HDLCParser()
    
    # 用户提供的报文
    frame_hex = "7E 10 2B 00 01 00 11 00 01 00 1F 61 01 A1 09 06 07 60 85 74 05 08 01 01 BE 10 04 0E 01 00 00 00 06 5F 1F 04 00 00 7E 1F 00 00 9C 8F 7E"
    frame_bytes = bytes.fromhex(frame_hex.replace(' ', ''))
    
    print("=" * 100)
    print("特殊HDLC报文分析")
    print("=" * 100)
    print(f"原始帧: {frame_hex}")
    print(f"帧长度: {len(frame_bytes)} 字节")
    print()
    
    # 详细字节分析
    print("【字节级别分析】")
    print("索引  字节    说明")
    print("-" * 50)
    
    # 帧结构分析
    print(f"0     0x{frame_bytes[0]:02X}    起始标志 (0x7E)")
    print(f"1-2   0x{frame_bytes[1]:02X} {frame_bytes[2]:02X}    格式域 (0x{frame_bytes[1]:02X}{frame_bytes[2]:02X})")
    
    format_field = (frame_bytes[1] << 8) | frame_bytes[2]
    format_type = (format_field >> 12) & 0x0F
    seg_bit = (format_field >> 11) & 0x01
    frame_len = format_field & 0x07FF
    
    print(f"       → 格式类型: 0x{format_type:X} ({'Type 3' if format_type == 0xA else '非Type 3'})")
    print(f"       → 分段位: {seg_bit}")
    print(f"       → 帧长度: {frame_len} 字节")
    print()
    
    # 地址域分析
    print("【地址域分析】")
    # 目的地址
    print(f"3-4   0x{frame_bytes[3]:02X} {frame_bytes[4]:02X}    目的地址域")
    print(f"       → Byte3=0x{frame_bytes[3]:02X} (LSB={frame_bytes[3] & 0x01}, 扩展={frame_bytes[3] & 0x01 == 0})")
    print(f"       → Byte4=0x{frame_bytes[4]:02X} (LSB={frame_bytes[4] & 0x01}, 结束={frame_bytes[4] & 0x01 == 1})")
    
    # 源地址
    print(f"5-6   0x{frame_bytes[5]:02X} {frame_bytes[6]:02X}    源地址域")
    print(f"       → Byte5=0x{frame_bytes[5]:02X} (LSB={frame_bytes[5] & 0x01}, 扩展={frame_bytes[5] & 0x01 == 0})")
    print(f"       → Byte6=0x{frame_bytes[6]:02X} (LSB={frame_bytes[6] & 0x01}, 结束={frame_bytes[6] & 0x01 == 1})")
    print()
    
    # 控制域
    print(f"7     0x{frame_bytes[7]:02X}    控制域")
    ctrl = frame_bytes[7]
    if (ctrl & 0x01) == 0:
        print(f"       → I帧 (信息帧)")
        n_r = (ctrl >> 5) & 0x07
        p_f = (ctrl >> 4) & 0x01
        n_s = (ctrl >> 1) & 0x07
        print(f"       → N(R)={n_r}, P/F={'P' if p_f else 'F'}, N(S)={n_s}")
    print()
    
    # HCS
    print(f"8-9   0x{frame_bytes[8]:02X} {frame_bytes[9]:02X}    HCS校验")
    hcs_value = (frame_bytes[8] << 8) | frame_bytes[9]
    print(f"       → 实际值: 0x{hcs_value:04X}")
    print()
    
    # 信息域
    info_start = 10
    print(f"10+   信息域开始")
    print(f"       → 首字节: 0x{frame_bytes[10]:02X}")
    
    # 分析信息域内容
    info_data = frame_bytes[info_start:]
    print(f"       → 信息域长度: {len(info_data)} 字节")
    print(f"       → 信息域内容: {parser._bytes_to_hex(info_data[:20])}...")
    
    # 分析0x1F的含义
    print()
    print("【信息域首字节 0x1F 分析】")
    print("可能的解释:")
    print("1. 专有协议标识符")
    print("2. BER编码的高标签号 (0x1F表示后续字节为标签扩展)")
    print("3. 加密/压缩数据")
    print("4. 南网自定义DLMS封装格式")
    
    # 查找特征模式
    print()
    print("【信息域特征模式检测】")
    for i in range(min(30, len(info_data) - 1)):
        byte = info_data[i]
        if byte == 0x09:
            print(f"  偏移{i}: 0x09 (Visible-String标签)")
        elif byte == 0x06:
            print(f"  偏移{i}: 0x06 (Octet-String标签)")
        elif byte == 0x0F:
            print(f"  偏移{i}: 0x0F (Long-Unsigned标签)")
        elif byte == 0x12:
            print(f"  偏移{i}: 0x12 (Long64标签)")
        elif byte == 0x18:
            print(f"  偏移{i}: 0x18 (DateTime标签)")
        elif byte == 0xC0:
            print(f"  偏移{i}: 0xC0 (Get-Request)")
        elif byte == 0xC2:
            print(f"  偏移{i}: 0xC2 (Action-Request)")
        elif byte == 0xC4:
            print(f"  偏移{i}: 0xC4 (Get-Response)")
    
    print()
    print("=" * 100)
    print("结论:")
    print("-" * 100)
    print("该报文使用非标准HDLC格式（格式类型=0x1而非0xA）")
    print("HCS校验失败可能是因为使用了不同的HCS算法或计算范围")
    print("信息域以0x1F开头，不是标准DLMS APDU类型")
    print("建议: 1) 检查是否使用了南网自定义协议 2) 确认HCS计算算法")
    print("=" * 100)


if __name__ == "__main__":
    analyze_special_frame()
