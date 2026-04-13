"""
分析截图中的报文
"""
# 构造正确的上报任务状态报文 (DI=E8:05:05:05)
# 用户数据区结构:
# - AFN: 05
# - SEQ: 70
# - 地址域标识: 00 (带地址域, 但地址域长度为0?) 或 01 (不带地址域)
#   从截图看是 01 (不带地址域)
# - DI: 05 05 05 E8 (小端序, 对应 E8:05:05:05)
#   等等, DI 应该是 4 字节: DI3 DI2 DI1 DI0 = E8 05 05 05
#   小端序传输: 05 05 05 E8
# - 数据内容: 任务ID(2B) + 从节点地址(6B) + 任务状态(1B) = 9字节
#   - 任务ID: 22 00 (小端序, 值=34)
#   - 从节点地址: 30 01 00 00 00 00
#   - 任务状态: 01 (从节点无响应)

# 重新分析截图中的用户数据区:
# 05 70 01 05 05 05 E8 22 00 30 01 00 00 00 00 01
# - 05: AFN
# - 70: SEQ
# - 01: 地址域标识 (不带地址域)
# - 05 05 05 E8: DI (小端序) -> E8:05:05:05
# - 22 00: 任务 ID (小端序) = 34
# - 30 01 00 00 00 00: 从节点地址
# - 01: 任务状态

user_data = bytes.fromhex('057001050505E8220030010000000001')
print(f'用户数据区: {user_data.hex().upper()}')
print(f'用户数据区长度: {len(user_data)} 字节')
print(f'  AFN: 0x{user_data[0]:02X}')
print(f'  SEQ: 0x{user_data[1]:02X}')
print(f'  地址域标识: 0x{user_data[2]:02X}')
print(f'  DI: {user_data[3:7].hex().upper()}')
print(f'  数据内容: {user_data[7:].hex().upper()}')

di_bytes = user_data[3:7]
di_value = int.from_bytes(di_bytes, 'little')
print(f'\nDI 解析:')
print(f'  原始字节: {di_bytes.hex().upper()}')
print(f'  小端序值: 0x{di_value:08X}')
print(f'  DI3: 0x{di_bytes[3]:02X}')
print(f'  DI2: 0x{di_bytes[2]:02X}')
print(f'  DI1: 0x{di_bytes[1]:02X}')
print(f'  DI0: 0x{di_bytes[0]:02X}')

length = len(user_data) + 6  # 用户数据区长度 + 6字节固定长度
length_bytes = length.to_bytes(2, 'little')
control = bytes.fromhex('C0')
start = bytes.fromhex('68')
end = bytes.fromhex('16')

# 计算校验和
checksum = sum(user_data) & 0xFF
checksum_byte = bytes([checksum])

# 组装报文
frame = start + length_bytes + control + user_data + checksum_byte + end
print(f'\n完整报文: {frame.hex().upper()}')
print(f'长度域: 0x{length_bytes.hex().upper()} = {length}')
print(f'校验和: 0x{checksum:02X}')

# 验证解析
from protocol_parser import ProtocolFrameParser
parser = ProtocolFrameParser()
table_data = parser.parse_to_table(frame)
print('\n解析结果:')
for i, row in enumerate(table_data, 1):
    field, raw, parsed, comment = row
    print(f'{i:2d}. {field:25s} | {raw:25s} | {parsed:15s} | {comment}')
