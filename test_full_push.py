"""
测试完整推送帧解析（含DLMS）
"""
from plc_rf_parser import PLCRFProtocolParser
import struct

# 用户提供的完整推送帧
frame_hex = "02 00 7A C4 12 01 01 5B 66 65 38 30 3A 30 3A 30 3A 30 3A 37 38 31 64 3A 66 66 3A 66 65 30 30 3A 30 5D 3A 36 31 36 31 36 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01 00 01 00 66 00 3A DB 08 57 53 47 66 71 34 66 13 2F 30 00 00 00 01 F6 B4 63 01 54 32 6C 02 53 D4 4D B1 70 20 D3 A4 C5 2F D6 69 E3 E3 9C 8B 0E E8 36 B4 F1 9A 3A DF 7E 11 B4 FD 7B 92 21 1C 84 2E 5E CA"

parser = PLCRFProtocolParser()
frame_bytes = bytes.fromhex(frame_hex.replace(" ", ""))

print("=" * 100)
print("完整推送帧解析（含DLMS）")
print("=" * 100)
print(f"报文长度: {len(frame_bytes)} 字节")
print()

# 解析
result = parser.parse(frame_bytes)
print(f"解析状态: {result['解析状态']}")
if result.get('错误信息'):
    print(f"错误: {result['错误信息']}")

if result.get('命令字'):
    print(f"命令字: {result['命令字']['名称']} (0x{result['命令字']['命令值']:04X})")

if result.get('校验和'):
    print(f"CRC16校验: {result['校验和']['校验结果']}")

print("\n" + "=" * 100)
print("表格解析结果:")
print("=" * 100)

table_data = parser.parse_to_table(frame_bytes)
for field, raw, parsed, comment, start, end in table_data:
    indent = "  " if field.startswith("  ") else ""
    indent2 = "    " if field.startswith("    ") else ""
    indent3 = "      " if field.startswith("      ") else ""
    field_name = field.strip()
    raw_display = raw[:40] + "..." if len(raw) > 40 else raw
    parsed_display = parsed[:30] + "..." if len(parsed) > 30 else parsed
    print(f"{indent}{indent2}{indent3}{field_name:25s} | {raw_display:45s} | {parsed_display:35s} | {comment}")
