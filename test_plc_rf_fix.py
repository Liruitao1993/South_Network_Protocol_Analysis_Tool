"""测试PLC RF协议解析器修复"""
from plc_rf_parser import PLCRFProtocolParser

parser = PLCRFProtocolParser()

# 测试1: 模块向电表发送数据推送确认帧（下行，C0）
# 根据4.md文档：02 00 06 C0 12 01 [状态] CRC16
# 状态字：01=推送成功，00=推送失败
test_frame_down = bytes.fromhex("02 00 06 C0 12 01 01 00 00")

print("=" * 80)
print("测试1: 模块向电表发送数据推送确认帧（下行 C0）")
print("输入报文:", test_frame_down.hex(' ').upper())
print("=" * 80)
result = parser.parse(test_frame_down)
print("解析状态:", result.get("解析状态"))
print("控制域:", result.get("控制域", {}).get("说明"))
print("命令字:", result.get("命令字", {}).get("名称"))
print("用户数据区:", result.get("用户数据区"))
print()

# 表格解析
table = parser.parse_to_table(test_frame_down)
print("表格解析结果:")
for row in table:
    print(f"  {row[0]:20s} | {row[1]:10s} | {row[2]:15s} | {row[3]}")
print()

# 测试2: 电表向模块推送数据帧（上行，C4）
# 完整的数据推送结构：目标地址类型(1) + 目标地址(48) + 推送延时(2) + DLMS数据(N)
test_frame_up = bytes.fromhex("02 00 7A C4 12 01 01 5B 66 65 38 30 3A 30 3A 30 3A 30 3A 37 38 31 64 3A 66 66 3A 66 65 30 30 3A 30 5D 3A 36 31 36 31 36 00 00 00 00 00 00 00 00 00 00 00 00 01 00 01 00 66 00 3A DB 08 57 53 47 66 71 34 66 13 2F 30 00 00 00 01 F6 B4 63 01 54 32 6C 02 53 D4 4D B1 70 20 D3 A4 C5 2F D6 69 E3 E3 9C 8B 0E E8 36 B4 F1 9A 3A DF 7E 11 B4 FD 7B 92 21 1C 84 2E 5E CA")

print("=" * 80)
print("测试2: 电表向模块推送数据帧（上行 C4）")
print("输入报文:", test_frame_up.hex(' ')[:120].upper() + "...")
print("=" * 80)
result2 = parser.parse(test_frame_up)
print("解析状态:", result2.get("解析状态"))
print("控制域:", result2.get("控制域", {}).get("说明"))
print("命令字:", result2.get("命令字", {}).get("名称"))
if "推送的目标地址类型" in result2.get("用户数据区", {}):
    print("目标地址类型:", result2["用户数据区"]["推送的目标地址类型"]["说明"])
if "推送的目标地址" in result2.get("用户数据区", {}):
    print("目标地址:", result2["用户数据区"]["推送的目标地址"]["解析值"][:50] + "...")
print()
