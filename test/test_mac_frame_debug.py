

import sys
import _path_setup  # noqa: E402

sys.path.insert(0, r'E:\python\南网解析工具')

from csg_new_gen_parser import CSGNewGenParser

# 用户截图中的实际帧数据
frame_hex = "69 00 10 00 03 00 00 41 25 05 20 5B 10 2D 60 68 00 00 00 00 02 00 5C 00 01 00 00 86 00 08 EE 4D 19 21 68 00 00 01 00 00 00 00 00 00 00 00 00 00 00 19 21 68 00 02 04 00 81 00 00 E1 88 01 30 00 00 00 00 19 21 68 00 02 04 01 00 00 00 00 00 00 00 00 00 01 00 00 03 00 7B 51 6D C6 11 EA 64 1D 00 00 00 00 A8 25 57 48 43 9C 99 2D BB 7B 00 00 00 03 02 18 A2 52 54 48 4C 00 00 18 00 02 08 02 01 D9 B2 00 00 B9 98 D0 8F 00 9D 01 66 9F EE"
frame_bytes = bytes.fromhex(frame_hex.replace(" ", ""))

print(f"Frame length: {len(frame_bytes)}")
print(f"pb_body length: {len(frame_bytes) - 20}")
print(f"pb_body[32:]: {len(frame_bytes) - 20 - 32}")
print(f"pb_body[32:121]: {len(frame_bytes) - 20 - 32 - 4}")

# Test _parse_mac_frame directly
parser = CSGNewGenParser()
mac_data = frame_bytes[20:]
offset, mac_table = parser._parse_mac_frame(mac_data, base_offset=0)

for row in mac_table:
    if 'MSDU' in row[0]:
        print(f"MAC frame: {row[0]} | {row[1]} | {row[2]} | {row[3]}")

# Test parse_to_table
result = parser.parse_to_table(frame_bytes)
for row in result:
    if 'MSDU' in row[0] or 'VLAN' in row[0] or 'MAC' in row[0]:
        print(f"Full: {row[0]} | {row[1]} | {row[2]} | {row[3]}")