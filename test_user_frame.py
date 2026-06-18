import sys
sys.path.insert(0, r'E:\python\南网解析工具')

from csg_new_gen_parser import CSGNewGenParser

# 用户截图中的实际帧数据（修正版）
frame_hex = "69 00 10 00 03 00 00 41 25 05 20 5B 10 2D 60 68 00 00 00 00 02 00 5C 00 01 00 00 86 00 08 EF 4D 19 21 68 00 00 01 00 00 00 00 00 00 00 00 00 00 00 19 21 68 00 02 04 00 81 00 00 E1 88 01 30 00 00 00 00 19 21 68 00 02 04 01 00 00 00 00 00 00 00 00 00 01 00 00 03 00 7B 51 6D C6 11 EA 64 1D 00 00 00 00 A8 25 57 48 43 9C 99 2D BB 7B 00 00 00 03 02 18 A2 52 54 48 4C 00 00 18 00 02 08 02 01 D9 B2 00 00 B9 98 D0 8F 00 9D 01 66 9F EE"
frame_bytes = bytes.fromhex(frame_hex.replace(" ", ""))

print(f"Frame length: {len(frame_bytes)}")

# mac_data
mac_data = frame_bytes[20:]
print(f"\nmac_data[0:60]:")
for i in range(0, 60):
    if i < len(mac_data):
        print(f"  [{i}] = {mac_data[i]:02X}")

# Check MAC frame header fields
print(f"\nMAC Frame Header Analysis:")
print(f"帧头类型: {mac_data[0]:02X}")
print(f"版本: {mac_data[1]:02X}")
print(f"发送序号: {mac_data[2:4].hex()}")
print(f"MSDU长度: {mac_data[4:6].hex()}")
print(f"原始目的TEI: {mac_data[6:8].hex()}")
print(f"原始源TEI: {mac_data[8:10].hex()}")
print(f"短网络标识: {mac_data[10]:02X}")
print(f"重启次数: {mac_data[11]:02X}")
print(f"路由跳数: {mac_data[12]:02X}")
print(f"广播方向: {mac_data[13]:02X}")
print(f"发送类型: {mac_data[14]:02X}")
print(f"发送次数限值: {mac_data[15]:02X}")
print(f"MSDU序列号: {mac_data[16:18].hex()}")
print(f"目的MAC地址: {mac_data[18:24].hex()}")
print(f"保留字段1: {mac_data[24:28].hex()}")
print(f"保留字段2: {mac_data[28:38].hex()}")

# Check MSDU long header
print(f"\nMSDU Long Header Analysis:")
print(f"目的MAC地址: {mac_data[18:24].hex()}")
print(f"源MAC地址: {mac_data[24:30].hex()}")
print(f"VLAN标签: {mac_data[30:34].hex()}")
print(f"MSDU类型: {mac_data[34:36].hex()}")

vlan_tag = int.from_bytes(mac_data[30:34], 'little')
msdu_type = int.from_bytes(mac_data[34:36], 'little')
print(f"VLAN tag = 0x{vlan_tag:04X}")
print(f"MSDU type = 0x{msdu_type:04X}")

# Check management message header
print(f"\nManagement Message Header:")
print(f"mac_data[36:40] = {mac_data[36:40].hex()}")
mgmt_version = mac_data[36]
mgmt_type = int.from_bytes(mac_data[37:39], 'little')
print(f"Management version = {mgmt_version}")
print(f"Management type = 0x{mgmt_type:04X}")

# Run parser
parser = CSGNewGenParser()
result = parser.parse_to_table(frame_bytes)

# Print relevant rows
for i, row in enumerate(result):
    if 'MSDU' in row[0] or '管理' in row[0] or 'VLAN' in row[0] or 'MAC' in row[0]:
        print(f"[{i}] {row[0]} | {row[1]} | {row[2]} | {row[3]}")