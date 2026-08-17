

import sys
import _path_setup  # noqa: E402

sys.path.insert(0, r'E:\python\南网解析工具')

from csg_new_gen_parser import CSGNewGenParser

# 用户截图中的实际帧数据
frame_hex = "69 00 10 00 03 00 00 41 25 05 20 5B 10 2D 60 68 00 00 00 00 02 00 5C 00 01 00 00 86 00 08 EE 4D 19 21 68 00 00 01 00 00 00 00 00 00 00 00 00 00 00 19 21 68 00 02 04 00 81 00 00 E1 88 01 30 00 00 00 00 19 21 68 00 02 04 01 00 00 00 00 00 00 00 00 00 01 00 00 03 00 7B 51 6D C6 11 EA 64 1D 00 00 00 00 A8 25 57 48 43 9C 99 2D BB 7B 00 00 00 03 02 18 A2 52 54 48 4C 00 00 18 00 02 08 02 01 D9 B2 00 00 B9 98 D0 8F 00 9D 01 66 9F EE"
frame_bytes = bytes.fromhex(frame_hex.replace(" ", ""))

print(f"Frame length: {len(frame_bytes)}")

# mac_data
mac_data = frame_bytes[20:]
print(f"\nmac_data[38:50]:")
for i in range(38, 50):
    if i < len(mac_data):
        print(f"  [{i}] = {mac_data[i]:02X}")

# Check mac_data[38:44] and mac_data[44:50]
print(f"\nmac_data[38:44] = {mac_data[38:44].hex()}")
print(f"mac_data[44:50] = {mac_data[44:50].hex()}")

# Check if this is the MSDU long header
print(f"\n目的MAC地址: {mac_data[38:44].hex()}")
print(f"源MAC地址: {mac_data[44:50].hex()}")

# Check VLAN tag and MSDU type
print(f"\nmac_data[50:54] = {mac_data[50:54].hex()}")
print(f"mac_data[54:56] = {mac_data[54:56].hex()}")

vlan_tag = int.from_bytes(mac_data[50:54], 'little')
msdu_type = int.from_bytes(mac_data[54:56], 'little')
print(f"VLAN tag = 0x{vlan_tag:04X}")
print(f"MSDU type = 0x{msdu_type:04X}")

# Check management message header
print(f"\nmac_data[56:60] = {mac_data[56:60].hex()}")
mgmt_version = mac_data[56]
mgmt_type = int.from_bytes(mac_data[57:59], 'little')
print(f"Management version = {mgmt_version}")
print(f"Management type = 0x{mgmt_type:04X}")

# Run parser
parser = CSGNewGenParser()
result = parser.parse_to_table(frame_bytes)

# Print relevant rows
for i, row in enumerate(result):
    if 'MSDU' in row[0] or '管理' in row[0] or 'VLAN' in row[0]:
        print(f"[{i}] {row[0]} | {row[1]} | {row[2]} | {row[3]}")