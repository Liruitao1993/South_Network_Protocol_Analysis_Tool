"""
测试表号解析的字节偏移
"""
from plc_rf_parser import PLCRFProtocolParser
import struct

# 构建表号响应帧
# 02 00 19 C4 20 01 09 12 31 32 33 34 35 36 37 38 39 39 38 37 36 35 34 33 32 31 8D F9

parser = PLCRFProtocolParser()

# 用户数据区: 09 12 31 32 33 34 35 36 37 38 39 39 38 37 36 35 34 33 32 31
#             ^  ^  ^-----------------------------------------------^
#             |  |  |
#             |  |  +-- 表号内容(18字节): 31 32 33 34 35 36 37 38 39 39 38 37 36 35 34 33 32 31
#             |  +----- 长度: 0x12 = 18
#             +-------- 类型: 0x09

frame_hex = "02 00 19 C4 20 01 09 12 31 32 33 34 35 36 37 38 39 39 38 37 36 35 34 33 32 31 8D F9"
frame_bytes = bytes.fromhex(frame_hex.replace(" ", ""))

print("=" * 100)
print("表号帧解析测试")
print("=" * 100)
print(f"报文: {frame_hex}")
print(f"字节位置:")
for i, b in enumerate(frame_bytes):
    print(f"  [{i:2d}] = 0x{b:02X}", end="")
    if i == 0:
        print("  (起始符)")
    elif i in [1, 2]:
        print("  (长度域)" if i == 1 else "")
    elif i == 3:
        print("  (控制域)")
    elif i in [4, 5]:
        print("  (命令字)" if i == 4 else "")
    elif i == 6:
        print("  (0x09 类型)")
    elif i == 7:
        print("  (0x12 长度=18)")
    elif 8 <= i <= 25:
        print(f"  (表号内容[{i-8}])")
    elif i in [26, 27]:
        print("  (CRC16)" if i == 26 else "")
    else:
        print()

print("\n" + "=" * 100)
print("表格解析结果（关注偏移位置）:")
print("=" * 100)

table_data = parser.parse_to_table(frame_bytes)
for field, raw, parsed, comment, start, end in table_data:
    indent = "  " if field.startswith("  ") else ""
    field_name = field.strip()
    raw_display = raw[:30] + "..." if len(raw) > 30 else raw
    parsed_display = parsed[:20] + "..." if len(parsed) > 20 else parsed
    pos_str = f"[{start}-{end}]" if start is not None and end is not None else "-"
    print(f"{indent}{field_name:20s} | {raw_display:35s} | {parsed_display:25s} | {pos_str:12s} | {comment}")
