"""
测试数据推送帧解析
根据用户提供的截图示例
"""
from plc_rf_parser import PLCRFProtocolParser
import struct

def test_push_frame():
    """测试数据推送帧解析"""
    parser = PLCRFProtocolParser()
    
    # 构建推送帧示例（根据截图）
    # 命令字: 0x1201 (数据推送)
    # 数据域:
    #   - 推送的目标地址类型: 0x01 (IPv6)
    #   - 推送的目标地址: 46字节 (IPv6地址 + 端口)
    #   - 推送延时时间: 0x00 0x00 (无延时)
    #   - 透传的数据内容: DLMS数据帧
    
    # 构建IPv6地址部分（46字节）
    # 示例: [fe80:0:0:781d:ff:fe00:0]:61616
    ipv6_addr_str = "[fe80:0:0:781d:ff:fe00:0]:61616"
    ipv6_addr_bytes = ipv6_addr_str.encode('ascii')
    # 填充到46字节
    ipv6_addr_padded = ipv6_addr_bytes + b'\x00' * (46 - len(ipv6_addr_bytes))
    
    # DLMS数据内容（示例）
    dlms_data = bytes.fromhex("00 01 00 01 00 66 00 3A DB 08 57 53 47 66 71 34 66 13 2F 30 00 00 00 01 F6 B4 63 01 54 32 6C 02 53 D4 4D B1 70 20 D3 A4 C5 2F D6 69 E3 E3 9C 8B 0E E8 36 B4 F1 9A 3A DF 7E 11 B4 FD 7B 92 21 1C 84 2E")
    
    # 构建用户数据区
    user_data = bytearray()
    user_data.append(0x01)  # 地址类型: IPv6
    user_data.extend(ipv6_addr_padded)  # 目标地址
    user_data.extend(struct.pack('>H', 0))  # 延时时间: 0秒
    user_data.extend(dlms_data)  # DLMS数据
    
    # 构建完整帧
    length = 1 + 2 + len(user_data) + 2  # Control + Command + UserData + CRC16
    frame = bytearray()
    frame.append(0x02)  # Start
    frame.extend(struct.pack('>H', length))  # Length
    frame.append(0xC0)  # Control (模块→电表)
    frame.extend(struct.pack('>H', 0x1201))  # Command
    frame.extend(user_data)
    
    # 计算CRC16
    crc_data = frame[1:]
    crc = parser.calculate_crc16(crc_data)
    frame.extend(struct.pack('<H', crc))
    
    # 打印帧信息
    print("=" * 80)
    print("测试: 数据推送帧 (0x1201)")
    print("=" * 80)
    print(f"报文: {frame.hex(' ').upper()}")
    print(f"长度: {len(frame)} 字节")
    print()
    
    # 解析
    result = parser.parse(frame)
    
    print(f"解析状态: {result['解析状态']}")
    if result.get('错误信息'):
        print(f"错误: {result['错误信息']}")
    
    if result.get('帧头'):
        print(f"帧头: {result['帧头']}")
    
    if result.get('长度域'):
        print(f"长度域: {result['长度域']['长度值']} 字节")
    
    if result.get('控制域'):
        print(f"控制域: {result['控制域']['说明']}")
    
    if result.get('命令字'):
        print(f"命令字: {result['命令字']['名称']} (0x{result['命令字']['命令值']:04X})")
    
    if result.get('用户数据区'):
        print("\n用户数据区解析:")
        user_data_result = result['用户数据区']
        for key, value in user_data_result.items():
            if key != "原始数据":
                if isinstance(value, dict):
                    print(f"  {key}: {value}")
    
    if result.get('校验和'):
        print(f"\nCRC16校验: {result['校验和']['校验结果']}")
    
    # 表格解析
    print("\n" + "=" * 80)
    print("表格解析结果:")
    print("=" * 80)
    table_data = parser.parse_to_table(frame)
    for row in table_data:
        field, raw, parsed, comment, start, end = row
        indent = "  " if field.startswith("  ") else ""
        field_name = field.strip()
        print(f"{indent}{field_name:25s} | {raw:40s} | {parsed:30s} | {comment}")


if __name__ == "__main__":
    test_push_frame()
