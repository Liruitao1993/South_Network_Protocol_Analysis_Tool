"""
测试特殊HDLC报文解析 - 非Type 3格式 + BER-TLV编码
"""
from hdlc_parser import HDLCParser


def test_special_frame():
    """测试特殊格式的HDLC帧"""
    parser = HDLCParser()
    
    # 用户提供的报文
    frame_hex = "7E 10 2B 00 01 00 11 00 01 00 1F 61 01 A1 09 06 07 60 85 74 05 08 01 01 BE 10 04 0E 01 00 00 00 06 5F 1F 04 00 00 7E 1F 00 00 9C 8F 7E"
    frame_bytes = bytes.fromhex(frame_hex.replace(' ', ''))
    
    print("=" * 120)
    print("特殊HDLC报文解析测试 - 非Type 3格式 + BER-TLV编码")
    print("=" * 120)
    print(f"原始帧: {frame_hex}")
    print(f"帧长度: {len(frame_bytes)} 字节")
    print()
    
    # 分析报文结构
    print("【报文结构分析】")
    print("-" * 120)
    
    # 查找所有7E标志
    flag_positions = [i for i, b in enumerate(frame_bytes) if b == 0x7E]
    print(f"7E标志位置: {flag_positions}")
    
    if len(flag_positions) > 2:
        print(f"⚠️  检测到多个7E标志，可能是:")
        print(f"   1. 多个帧拼接")
        print(f"   2. 数据中包含未转义的7E（应为7D 5E）")
        print(f"   3. 专有协议格式")
        print()
        
        # 尝试解析第一个完整帧（从第一个7E到第二个7E）
        if len(flag_positions) >= 2:
            first_frame_end = flag_positions[1] + 1
            first_frame = frame_bytes[:first_frame_end]
            print(f"尝试解析第一个帧（索引0-{first_frame_end-1}）:")
            print(f"帧数据: {' '.join(f'{b:02X}' for b in first_frame)}")
            print()
            
            table = parser.parse_to_table(first_frame)
            print(f"{'字段':<30s} | {'原始值':<50s} | {'解析值':<35s} | 说明")
            print("-" * 150)
            for row in table:
                print(f"{row[0]:<30s} | {row[1]:<50s} | {row[2]:<35s} | {row[3]}")
            print()
    
    # 分析信息域内容
    print("=" * 120)
    print("【信息域内容分析】")
    print("-" * 120)
    
    # 信息域（假设从HCS之后开始）
    # HCS在索引10-11，信息域从索引12开始
    info_start = 12
    info_data = frame_bytes[info_start:]
    
    print(f"信息域起始位置: 索引{info_start}")
    print(f"信息域内容: {' '.join(f'{b:02X}' for b in info_data[:20])}...")
    print()
    
    # 分析BER-TLV结构
    print("【BER-TLV结构分析】")
    print("-" * 120)
    
    offset = 0
    while offset < len(info_data) - 1:
        tag = info_data[offset]
        
        # 解析标签
        tag_desc = ""
        if tag == 0x1F:
            tag_desc = "高标签号（后续字节为标签扩展）"
            if offset + 1 < len(info_data):
                tag_desc += f" → 0x{info_data[offset+1]:02X}"
        elif 0x60 <= tag <= 0x7F:
            app_num = tag - 0x60
            app_names = {1: "AARQ (关联请求)", 2: "AARE (关联响应)", 3: "RLRQ (释放请求)", 4: "RLRE (释放响应)"}
            tag_desc = f"APPLICATION {app_num} {app_names.get(app_num, '')}"
        elif 0xA0 <= tag <= 0xBF:
            ctx_num = tag - 0xA0
            tag_desc = f"Context-Specific [{ctx_num}]"
        elif tag == 0x09:
            tag_desc = "Visible-String"
        elif tag == 0x06:
            tag_desc = "Octet-String"
        elif tag == 0x02:
            tag_desc = "Integer"
        elif tag == 0x0F:
            tag_desc = "Long-Unsigned"
        else:
            tag_desc = f"未知标签 0x{tag:02X}"
        
        print(f"偏移{offset:2d}: 0x{tag:02X} - {tag_desc}")
        offset += 1
        
        # 如果还有数据，尝试解析长度
        if offset < len(info_data):
            length_byte = info_data[offset]
            if length_byte < 0x80:
                print(f"       长度: {length_byte} 字节")
                # 如果是Visible-String或Octet-String，尝试显示内容
                if tag == 0x09 and length_byte > 0 and offset + 1 + length_byte <= len(info_data):
                    str_data = info_data[offset + 1:offset + 1 + length_byte]
                    try:
                        str_val = str_data.decode('ascii', errors='replace')
                        print(f"       内容: \"{str_val}\"")
                    except:
                        print(f"       内容: {' '.join(f'{b:02X}' for b in str_data[:10])}")
                elif tag == 0x06 and length_byte > 0 and offset + 1 + length_byte <= len(info_data):
                    str_data = info_data[offset + 1:offset + 1 + length_byte]
                    print(f"       内容: {' '.join(f'{b:02X}' for b in str_data[:10])}")
                    
                    # 检查是否是DateTime格式（12字节，以0x07开头）
                    if length_byte == 12 and str_data[0] == 0x07:
                        try:
                            import struct
                            year = struct.unpack('>H', str_data[0:2])[0]
                            month = str_data[2]
                            day = str_data[3]
                            hour = str_data[4]
                            minute = str_data[5]
                            second = str_data[6]
                            print(f"       → DateTime: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
                        except:
                            pass
                
                offset += 1 + length_byte
            else:
                print(f"       长度: 长格式 0x{length_byte:02X}")
                offset += 1
        
        print()
        
        # 限制输出
        if offset > 30:
            print("... (截断)")
            break
    
    print("=" * 120)
    print("【结论】")
    print("-" * 120)
    print("该报文使用非标准HDLC格式（格式类型=0x1而非0xA）")
    print("信息域包含BER-TLV编码的DLMS数据，特征:")
    print("  - 0x1F: 高标签号（BER编码扩展）")
    print("  - 0x61: APPLICATION 1（AARQ关联请求）")
    print("  - 0xA1: Context-Specific [1]")
    print("  - 0x09: Visible-String")
    print("  - 0x06: Octet-String（可能包含DateTime）")
    print()
    print("建议:")
    print("  1. 确认HCS计算算法（非Type 3格式可能使用不同算法）")
    print("  2. 使用BER-TLV解析器深度解析信息域")
    print("  3. 检查是否存在多个帧拼接或数据转义问题")
    print("=" * 120)


if __name__ == "__main__":
    test_special_frame()
