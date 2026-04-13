"""
测试DLMS解析
"""
from dlms_parser import DLMSParser

# 用户提供的DLMS数据
dlms_hex = "00 01 00 01 00 66 00 3A DB 08 57 53 47 66 71 34 66 13 2F 30 00 00 00 01 F6 B4 63 01 54 32 6C 02 53 D4 4D B1 70 20 D3 A4 C5 2F D6 69 E3 E3 9C 8B 0E E8 36 B4 F1 9A 3A DF 7E 11 B4 FD 7B 92 21 1C 84 2E"

dlms_bytes = bytes.fromhex(dlms_hex.replace(" ", ""))

parser = DLMSParser()
table = parser.parse_to_table(dlms_bytes)

print("=" * 80)
print("DLMS帧解析结果:")
print("=" * 80)
for field, raw, parsed, comment, start, end in table:
    indent = "  " if field.startswith("  ") else ""
    indent2 = "    " if field.startswith("    ") else ""
    field_name = field.strip()
    print(f"{indent}{indent2}{field_name:25s} | {raw:40s} | {parsed:30s} | {comment}")
