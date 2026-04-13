"""
生成带正确CRC16的测试帧（使用查表法）
"""
import struct
from plc_rf_parser import PLCRFProtocolParser

def create_frame(control: int, command: int, user_data: bytes = b'') -> str:
    """创建带正确CRC的完整帧（使用查表法CRC16）"""
    parser = PLCRFProtocolParser()
    
    # 构建帧（不含Start和CRC）
    frame_body = bytearray()
    frame_body.append(control)
    frame_body.extend(struct.pack('>H', command))
    frame_body.extend(user_data)
    
    # 计算长度：Control + Command + UserData + CRC16
    length = 1 + 2 + len(user_data) + 2
    
    # 完整帧（从Start开始，用于CRC计算）
    full_frame = bytearray()
    full_frame.append(0x02)  # Start
    full_frame.extend(struct.pack('>H', length))  # Length
    full_frame.extend(frame_body)
    
    # 计算CRC16（使用查表法，从Length开始）
    crc_data = full_frame[1:]  # 从Length开始
    crc = parser.calculate_crc16(crc_data)
    
    # 添加CRC16（小端序）
    full_frame.extend(struct.pack('<H', crc))
    
    return full_frame.hex(' ').upper()


if __name__ == "__main__":
    # 测试1: 模块获取电表表号（请求）
    frame1 = create_frame(0xC0, 0x2001)
    print(f"测试1（获取表号请求）: {frame1}")
    
    # 测试2: 心跳
    frame2 = create_frame(0xC0, 0x2002)
    print(f"测试2（心跳）: {frame2}")
    
    # 测试3: 模块信息传输
    # 在线(1) + HPLC_band 0(1) + CCO_MAC "12345678"(16字节，不足补0)
    user_data3 = bytes([0x01, 0x00])  # 在线，频段0
    cco_mac = b"12345678" + b"\x00" * 8  # 16字节
    user_data3 += cco_mac
    frame3 = create_frame(0xC0, 0x2003, user_data3)
    print(f"测试3（模块信息）: {frame3}")
    
    # 测试4: 获取电表表号（响应）- 表号123456789987654321
    # 09(类型) + 12(长度18) + ASCII表号
    meter_id = "123456789987654321"
    user_data4 = bytes([0x09, len(meter_id)]) + meter_id.encode('ascii')
    frame4 = create_frame(0xC4, 0x2001, user_data4)
    print(f"测试4（表号响应）: {frame4}")
