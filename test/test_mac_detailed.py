

import sys
import _path_setup  # noqa: E402

sys.path.insert(0, r'E:\python\南网解析工具')

from csg_new_gen_parser import CSGNewGenParser

# 用户截图中的实际帧数据
frame_hex = "69 00 10 00 03 00 00 41 25 05 20 5B 10 2D 60 68 00 00 00 00 02 00 5C 00 01 00 00 86 00 08 EE 4D 19 21 68 00 00 01 00 00 00 00 00 00 00 00 00 00 00 19 21 68 00 02 04 00 81 00 00 E1 88 01 30 00 00 00 00 19 21 68 00 02 04 01 00 00 00 00 00 00 00 00 00 01 00 00 03 00 7B 51 6D C6 11 EA 64 1D 00 00 00 00 A8 25 57 48 43 9C 99 2D BB 7B 00 00 00 03 02 18 A2 52 54 48 4C 00 00 18 00 02 08 02 01 D9 B2 00 00 B9 98 D0 8F 00 9D 01 66 9F EE"
frame_bytes = bytes.fromhex(frame_hex.replace(" ", ""))

print(f"Frame length: {len(frame_bytes)}")

# Print frame_bytes[20:60]
print(f"frame_bytes[20:60]:")
for i in range(20, 60):
    print(f"  [{i}] = {frame_bytes[i]:02X}")

# mac_data
mac_data = frame_bytes[20:]
print(f"\nmac_data[0:40]:")
for i in range(0, 40):
    print(f"  [{i}] = {mac_data[i]:02X}")

# Check mac_data[32:36] and mac_data[36:38]
print(f"\nmac_data[32:36] = {mac_data[32:36].hex()}")
print(f"mac_data[36:38] = {mac_data[36:38].hex()}")

vlan_tag = int.from_bytes(mac_data[32:36], 'little')
msdu_type = int.from_bytes(mac_data[36:38], 'little')
print(f"vlan_tag = 0x{vlan_tag:04X}")
print(f"msdu_type = 0x{msdu_type:04X}")

# Check if long header
print(f"\nmac_data[0] = {mac_data[0]:02X}")
print(f"mac_data[0] & 0x01 = {mac_data[0] & 0x01}")
print(f"msdu_hdr_len = {18 if mac_data and (mac_data[0] & 0x01) == 0 else 2}")