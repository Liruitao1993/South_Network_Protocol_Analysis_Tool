"""测试用户实际输入的报文是否能正确触发深化应用解析"""

import _path_setup  # noqa: E402

from csg_new_gen_parser import CSGNewGenParser

p = CSGNewGenParser()

# 用户实际输入的报文
hex_str = "13 01 01 00 01 60 01 01 C0 08 36 00 01 00 13 07 00 00 12 11 13 07 00 00 00 02 26 00 02 00 00 00 28 06 26 01 0F 07 FF 01 12 06 FF 02 12 06 FF 03 12 06 FF 04 12 06 FF 06 12 06 FF 07 12 06 FF 08 12 06"
frame = bytes.fromhex(hex_str)

result = p.parse_to_table(frame, parse_level="app")

print("=== 解析结果 ===")
for row in result:
    name, raw, parsed, desc, start, end = row
    print(f"  {name}: {parsed} | {desc[:60]}")

# 检查是否触发了深化应用解析
field_names = [r[0] for r in result]
has_business_code = "业务代码" in field_names
has_load_curve = "功能码" in field_names
has_port = "报文端口号" in field_names

print(f"\n=== 验证 ===")
print(f"报文端口号解析: {has_port}")
print(f"业务代码解析: {has_business_code}")
print(f"功能码(负荷曲线)解析: {has_load_curve}")
if has_business_code and has_load_curve:
    print("✓ 深化应用解析已正确触发！")
else:
    print("✗ 深化应用解析未触发")

