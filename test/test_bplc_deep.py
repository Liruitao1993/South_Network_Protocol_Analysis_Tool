"""BPLC深化应用报文解析 快速集成测试"""

import _path_setup  # noqa: E402

import struct
from csg_new_gen_parser import CSGNewGenParser
from csg_new_gen_cmd_payloads import _parse_cmd_district_phase

p = CSGNewGenParser()
passed = 0
failed = 0

def check(name, rows, field_name, expected_parsed=None):
    global passed, failed
    found = [r for r in rows if r[0] == field_name]
    if not found:
        print(f"  FAIL: {name} - 字段 '{field_name}' 未找到")
        failed += 1
        return None
    if expected_parsed is not None:
        if found[0][2] != expected_parsed:
            print(f"  FAIL: {name} - {field_name}={found[0][2]} != {expected_parsed}")
            failed += 1
            return found[0]
    print(f"  OK: {field_name} = {found[0][2]}")
    passed += 1
    return found[0]

# ====== Test 1: 精准对时 ======
print("=== Test 1: 精准对时 (业务代码0x01) ===")
src = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])
dst = bytes([0x00, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE])
fwd = struct.pack('<HBB', 1, 1, 0) + struct.pack('<I', 12345678) + bytes([0x68]*8)
payload = src + dst + bytes([0x00, 0x01]) + struct.pack('<H', len(fwd)) + fwd
r = p._parse_data_transparent_to_module(payload, 0, 100)
check("T1", r, "业务代码", "1")
check("T1", r, "端口号", "1")
check("T1", r, "序号", "1")
check("T1", r, "CCO网络基准时间", "12345678")
check("T1", r, "校时报文(DL/T645)", "8字节")

# ====== Test 2: 负荷曲线-配置采集间隔 ======
print("\n=== Test 2: 负荷曲线-配置采集间隔 (功能码0x01) ===")
fwd2 = bytes([0x01]) + struct.pack('<I', 15)
payload2 = src + dst + bytes([0x00, 0x02]) + struct.pack('<H', len(fwd2)) + fwd2
r2 = p._parse_data_transparent_to_module(payload2, 0, 200)
check("T2", r2, "业务代码", "2")
check("T2", r2, "功能码", "1")
check("T2", r2, "采集间隔", "15")

# ====== Test 3: 负荷曲线-抄读数据项(下行) ======
print("\n=== Test 3: 负荷曲线-抄读数据项(下行) ===")
# 功能码0x02 + 表类型0x00 + 起始时间BCD(5B) + 采集点4 + 间隔15min + 数据项2 + 标识1(4B) + 标识2(4B)
fwd3 = bytes([0x02, 0x00,
              0x00, 0x12, 0x25, 0x01, 0x24,  # mm=00, hh=12, DD=25, MM=01, YY=24
              4, 15, 2])
di1 = bytes([0x01, 0x01, 0x12, 0x06])  # A相电压 (DI3=06,DI2=12,DI1=01,DI0=01)
di2 = bytes([0x03, 0x01, 0x12, 0x06])  # C相电压 (DI3=06,DI2=12,DI1=01,DI0=03)
fwd3 += di1 + di2
payload3 = src + dst + bytes([0x00, 0x02]) + struct.pack('<H', len(fwd3)) + fwd3
r3 = p._parse_data_transparent_to_module(payload3, 0, 300)
check("T3", r3, "功能码", "2")
check("T3", r3, "表类型", "0")
check("T3", r3, "采集点数量", "4")
check("T3", r3, "数据项数量", "2")
check("T3", r3, "数据标识1", "A相电压")
check("T3", r3, "数据标识2", "C相电压")

# ====== Test 4: 台区识别-采集启动 ======
print("\n=== Test 4: 台区识别-采集启动 ===")
hdr = bytes([0x0C, 0x00, 0x00, 0x00, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 1, 1])
data4 = struct.pack('<I', 99999) + bytes([10, 20, 1, 0])
payload4 = hdr + data4
r4 = _parse_cmd_district_phase(payload4, 0, 400)
check("T4", r4, "特征类型", "1")
check("T4", r4, "采集类型", "1")
check("T4", r4, "起始NTB", "0x0001869F")
check("T4", r4, "采集周期", "10")
check("T4", r4, "采集数量", "20")

# ====== Test 5: 台区识别-判别结果 ======
print("\n=== Test 5: 台区识别-判别结果 ===")
hdr5 = bytes([0x0C, 0x00, 0x00, 0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 1, 5])
data5 = struct.pack('<H', 0x0005) + bytes([1, 2]) + bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
payload5 = hdr5 + data5
r5 = _parse_cmd_district_phase(payload5, 0, 500)
check("T5", r5, "采集类型", "5")
check("T5", r5, "台区识别结果", "2")
check("T5", r5, "台区判别过程结束标志", "1")

# ====== Test 6: 相位特征信息告知 ======
print("\n=== Test 6: 相位特征信息告知 (采集类型0x07) ===")
# TEI=0x001, 采集方式=1(下降沿), seq=1, total=6, base_ntb=100000, rsv=0
tei_mode = 0x001 | (1 << 12)  # TEI=1, mode=1
hdr6 = bytes([0x0C, 0x00, 0x00, 0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 3, 7])
data6 = struct.pack('<H', tei_mode) + bytes([1, 6]) + struct.pack('<I', 100000) + bytes([0, 2, 2, 2])
data6 += struct.pack('<H', 500) + struct.pack('<H', 510)  # 相线1差值
data6 += struct.pack('<H', 480) + struct.pack('<H', 490)  # 相线2差值
data6 += struct.pack('<H', 520) + struct.pack('<H', 530)  # 相线3差值
payload6 = hdr6 + data6
r6 = _parse_cmd_district_phase(payload6, 1, 600)
check("T6", r6, "采集类型", "7")
check("T6", r6, "TEI", "0x001")
check("T6", r6, "相线1过零NTB差值数量", "2")
check("T6", r6, "相线1差值1", "500")
check("T6", r6, "相线3差值2", "530")

# ====== Test 7: 停电上报-位图式 ======
print("\n=== Test 7: 停电上报-位图式 ===")
mac_sta = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
outage = bytes([12]) + mac_sta + bytes([1, 5, 1]) + struct.pack('<H', 2) + bytes([0b00000101])
r7 = p._parse_power_outage_report(outage, 1, 700)
check("T7", r7, "帧头长度", "12")
check("T7", r7, "功能码", "1")
check("T7", r7, "事件类型", "1")
check("T7", r7, "起始TEI", "2")

# ====== Test 8: 停电上报-地址式 ======
print("\n=== Test 8: 停电上报-地址式(上电) ===")
outage2 = bytes([12]) + mac_sta + bytes([1, 11, 4]) + struct.pack('<H', 1) + mac_sta + bytes([1])
r8 = p._parse_power_outage_report(outage2, 1, 800)
check("T8", r8, "事件类型", "4")
check("T8", r8, "电表个数", "1")
check("T8", r8, "电表1带电状态", "1")

print(f"\n{'='*40}")
print(f"通过: {passed}, 失败: {failed}")

