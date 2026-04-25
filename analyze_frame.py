from protocol_parser import ProtocolFrameParser
import json

# 用户提供的报文
frame_hex = "68400188F00032F000E8003A0112484C02123039031E060226041606C00512484C06123039070C3F080C00094400000000000000000B0C020C360000000000000D36FFFFFFFFFFFF0E24FFFFFFFF0F140502100C02111490041214120213140F6741A246656220203620323032362031343A33333A3135421606C04316010044160F104516460146161E104716460148162E03491639404A1609014B16090150065106541601015516000056160D0157160000581600005E16000081C400000000000000000000000000000000000000000000000000825C00000000000000000000008302840C07850486048704880489048A048B0494CC0989130300000000000000000089130300000000000000009564000000001E74817FFFFFFFFF96141D2297149D00991C000000C105C21D3F00022516"

frame_bytes = bytes.fromhex(frame_hex)

print("=== 报文分析 ===")
print(f"原始数据: {frame_hex}")
print(f"报文长度: {len(frame_bytes)} 字节")
print()

# 手动解析基本结构
print("=== 手动解析 ===")
print(f"帧头: 0x{frame_bytes[0]:02X}")
length = int.from_bytes(frame_bytes[1:3], 'little')
print(f"长度域: 0x{frame_bytes[1]:02X}{frame_bytes[2]:02X} = {length} (0x{length:04X})")
print(f"控制域: 0x{frame_bytes[3]:02X}")

# 控制域解析
c = frame_bytes[3]
print(f"  DIR: {(c>>7)&1}, PRM: {(c>>6)&1}, ADD: {(c>>5)&1}, VER: {(c>>3)&3}")

# 用户数据区
user_data_len = length - 6
print(f"用户数据区长度: {user_data_len}")
print()

user_data = frame_bytes[4:4+user_data_len]
print(f"用户数据区: {user_data.hex().upper()}")
print()

# 解析AFN
afn = user_data[0]
print(f"AFN: 0x{afn:02X}")

# 解析SEQ
seq = user_data[1]
print(f"SEQ: 0x{seq:02X}")

# 解析DI
di = user_data[2:6]
print(f"DI: {di.hex().upper()}")
di_val = int.from_bytes(di, 'little')
print(f"DI值: 0x{di_val:08X}")
print(f"  DI3: 0x{di[3]:02X}, DI2: 0x{di[2]:02X}, DI1: 0x{di[1]:02X}, DI0: 0x{di[0]:02X}")
print()

# 数据标识内容
data_content = user_data[6:]
print(f"数据标识内容: {data_content.hex().upper()}")
print(f"数据标识内容长度: {len(data_content)} 字节")
print()

# 解析信息条目
print("=== 信息条目解析 ===")
pos = 0
entries = []
while pos < len(data_content):
    if pos + 2 > len(data_content):
        print(f"剩余数据不足: pos={pos}, len={len(data_content)}")
        break
    entry_id = data_content[pos]
    entry_len = data_content[pos + 1]
    
    if pos + 2 + entry_len > len(data_content):
        print(f"条目数据不足: pos={pos}, id={entry_id}, len={entry_len}, remain={len(data_content)-pos}")
        break
        
    entry_data = data_content[pos + 2:pos + 2 + entry_len]
    entries.append({
        'id': entry_id,
        'len': entry_len,
        'data': entry_data.hex().upper(),
        'raw': entry_data
    })
    pos += 2 + entry_len

print(f"解析出 {len(entries)} 个信息条目:")
print("-" * 80)
for entry in entries:
    print(f"ID: 0x{entry['id']:02X} ({entry['id']:3d}), 长度: {entry['len']:3d}, 数据: {entry['data']}")

print()
print("=== 校验和 ===")
cs_pos = 4 + user_data_len
cs = frame_bytes[cs_pos]
print(f"校验和位置: {cs_pos}")
print(f"校验和: 0x{cs:02X}")
