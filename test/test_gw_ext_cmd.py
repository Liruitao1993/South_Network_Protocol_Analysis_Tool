# -*- coding: utf-8 -*-
"""测试检测扩展命令解析（1.2 检测扩展命令，复用通信测试0x0006）"""

import _path_setup  # noqa: E402

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from gw_new_gen_cmd_payloads import _parse_comm_test

passed = 0
failed = 0


def check(name, table, field, expect_in):
    global passed, failed
    for row in table:
        if field in str(row[0]):
            text = ' '.join(str(x) for x in row[:4])
            if expect_in in text:
                print(f"  [OK] {field}: {row[2]}")
                passed += 1
                return
            else:
                print(f"  [FAIL] {field}: 期望含'{expect_in}', 实际'{text}'")
                failed += 1
                return
    print(f"  [FAIL] 未找到字段: {field}")
    failed += 1


# 1. 普通通信测试(mode=0) 不受影响
print("Test 1: 普通通信测试")
t = _parse_comm_test(bytes.fromhex("41000203AABB"), 0, 0)
check("T1", t, "规约类型", "DL/T 645-2007")
check("T1", t, "转发数据长度", "48字节")
check("T1", t, "测试数据", "2字节")

# 2. 模式3: HPLC物理层透传, 持续30分钟(0x01E: 低4=E→b2高4位, 高8=0x01→b3)
print("Test 2: HPLC物理层透传")
t = _parse_comm_test(bytes.fromhex("0130E0010000"), 0, 0)
check("T2", t, "测试模式", "HPLC物理层透传")
check("T2", t, "持续时间", "30分钟")

# 3. 模式6: 频段切换(切频)→Option=2 信道=0(低4=2→b2高4位, 信道号=b3; 同用户实际帧 81 61 20 00)
print("Test 3: 频段切换")
t = _parse_comm_test(bytes.fromhex("016020000000"), 0, 0)
check("T3", t, "测试模式", "频段切换")
check("T3", t, "Option值", "Option 2")
check("T3", t, "无线信道号", "信道 0")

# 4. 模式8: 无线信道切换 Option=1 信道=36
print("Test 4: 无线信道切换")
t = _parse_comm_test(bytes.fromhex("018010240000"), 0, 0)
check("T4", t, "Option值", "Option 1")
check("T4", t, "无线信道号", "信道 36")

# 5. 模式12: PLC到RF回传, 60分钟(0x03C: 低4=C→b2高4位, 高8=3→b3), PHR_MCS=5 PSDU_MCS=3 PbSIZE=9
print("Test 5: PLC到RF物理层回传")
t = _parse_comm_test(bytes.fromhex("01C0C0035093"), 0, 0)
check("T5", t, "测试模式", "PLC到RF物理层回传")
check("T5", t, "PHR_MCS", "MCS 5")
check("T5", t, "PSDU_MCS", "MCS 3")
check("T5", t, "PbSIZE", "9")

# 6. 模式13: 安全测试SM3, 仅随机数(前5段长度0)
print("Test 6: 安全测试模式-SM3")
# 10分钟(0x00A: 低4=A→b2高4位, 高8=0→b3)
t = _parse_comm_test(bytes.fromhex("01D0A0000200" + "0000000000" + "0400DEADBEEF"), 0, 0)
check("T6", t, "测试模式", "安全测试模式")
check("T6", t, "安全测试模式", "SM3算法测试")
check("T6", t, "随机数/明文/密文", "4字节")

# 7. 模式15/子6: CCO信标机制切换=1
print("Test 7: 新一代模式-信标机制切换")
# ng_mode=6(b2低4位), 数据转发长度=1(低4=1→b2高4位, 高8=0→b3)
t = _parse_comm_test(bytes.fromhex("01F01600000001"), 0, 0)
check("T7", t, "新一代测试模式", "CCO信标机制切换")
check("T7", t, "信标机制", "立即切换到竞争机制")

# 8. 模式15/子1: 信道探测帧发送(4B)
print("Test 8: 新一代模式-信道探测帧发送")
# ng_mode=1, 数据转发长度=4(低4=4→b2高4位)
t = _parse_comm_test(bytes.fromhex("01F04100000001020304"), 0, 0)
check("T8", t, "子载波组", "1")
check("T8", t, "TF符号数", "2")
check("T8", t, "训练序列频段", "4")

# 9. 模式15/子8: 指定TEI×4 (1,2,3,4)
# TEI1=b0+b1低4=1; TEI2=b1高4+b2=2→b2=0; TEI3=b3+b4低4=3; TEI4=b4高4+b5=4→b4=0x40
print("Test 9: 新一代模式-指定DUT TEI")
# ng_mode=8, 数据转发长度=6(低4=6→b2高4位)
t = _parse_comm_test(bytes.fromhex("01F068000000012000034000"), 0, 0)
check("T9", t, "TEI1", "TEI=1")
check("T9", t, "TEI2", "TEI=2")
check("T9", t, "TEI3", "TEI=3")
check("T9", t, "TEI4", "TEI=4")

# 10. 模式15/子5: 比特加载表
print("Test 10: 新一代模式-动态加载参数(比特加载表)")
# ng_mode=5, 数据转发长度=5(低4=5→b2高4位)
t = _parse_comm_test(bytes.fromhex("01F0550000000103001BE4"), 0, 0)
check("T10", t, "参数表类型", "比特加载表")
check("T10", t, "子载波段个数", "1段")
check("T10", t, "子载波段0", "16QAM")

# 11. 模式15/子2: 被动信道探测(TF位置=1, payload=3B)
print("Test 11: 新一代模式-被动信道探测")
# ng_mode=2, 数据转发长度=8(低4=8→b2高4位)
t = _parse_comm_test(bytes.fromhex("01F0820000000102030403AABBCC"), 0, 0)
check("T11", t, "TF位置", "数据载荷之前")
check("T11", t, "Payload长度", "3字节")
check("T11", t, "Payload数据", "3字节")

# 12. 模式15/子7: DUT发送模式切换(强制OFDMA, 1用户)
print("Test 12: 新一代模式-DUT发送模式切换")
# 发送模式=1 FCH=2 eFCH=3 用户数=0(1个) 用户0: TF=4 TEI=5 TMI=6 RU=7 payload=2B
# blk: 04 05 00 60 70 → TF=4, TEI=0x005, TMI=(0>>4)|(6<<4)=0x60? 重新算:
# TEI = blk[1]|((blk[2]&0xF)<<8) = 0x05|0 = 5 ✓ (blk[2]=0x00)
# TMI = (blk[2]>>4)|((blk[3]&0xF)<<4) = 0|(6<<4)=0x60=96
# 想要 TMI=6: blk[3]低4=6, blk[2]高4=0 → TMI=(0)|(6<<4)... 不对, TMI是8bit=blk[2]高4+blk[3]低4
# 文档: TMI=字节5(4-7)+字节6(0-3) → TMI = (blk[2]>>4) | ((blk[3]&0xF)<<4)
# TMI=0x06: blk[2]>>4=6, blk[3]低4=0 → blk[2]=0x60
# RU = (blk[3]>>4)|((blk[4]&0xF)<<4) = 0x07: blk[3]>>4=7, blk[4]低4=0 → blk[3]=0x70
# blk = 04 05 60 70 00, payload=AA BB
# 字节2=0x03: eFCH=3(低6bit), 用户数字段=0(高2bit)→用户数=1
# ng_mode=7, 数据转发长度=9(低4=9→b2高4位)
t = _parse_comm_test(bytes.fromhex("01F097000000" + "010203" + "0405607000" + "AABB"), 0, 0)
check("T12", t, "发送模式", "强制OFDMA")
check("T12", t, "用户数", "1个站点")
check("T12", t, "用户0 TEI", "TEI=5")
check("T12", t, "用户0 TMI", "TMI=6")
check("T12", t, "用户0 Payload", "2字节")

# 13. 用户实际载荷 81 61 20 00 00 00: hdr_len小端组合=6, 切频 Option=2 信道=0, 无数据域
print("Test 13: 频段切换-实际帧hdr_len小端")
t = _parse_comm_test(bytes.fromhex("816120000000"), 0, 0)
check("T13", t, "报文头长度", "6")
check("T13", t, "测试模式", "频段切换")
check("T13", t, "Option值", "Option 2")
check("T13", t, "无线信道号", "信道 0")
# 载荷恰好6字节, 不应出现"尾部数据"或"数据域"行
if any(("尾部数据" in str(r[0])) or ("数据域" in str(r[0])) for r in t):
    print("  [FAIL] T13 载荷6字节不应有尾部/数据域行")
    failed += 1
else:
    print("  [OK] T13 无尾部/数据域行")
    passed += 1

# 14. 用户完整帧(145B): FC+PBH+MSDU+ICV+填充+PBCS 经parser完整链路
print("Test 14: 完整帧链路解析(ICV/填充/PBCS)")
from gw_new_gen_parser import get_gw_new_gen_parser
_frame = bytes.fromhex(
    'C00000FF1F000000300A00FF00000100001106000081612000000094CD7089'
    + '00' * 111 + '9BFA85')
t14 = get_gw_new_gen_parser().parse_to_table(_frame)
check("T14", t14, "报文头长度", "6")
check("T14", t14, "Option值", "Option 2")
check("T14", t14, "无线信道号", "信道 0")
check("T14", t14, "完整性校验(ICV)", "校验通过")
check("T14", t14, "物理块填充", "111字节")
check("T14", t14, "PBCS", "0x85FA9B")
check("T14", t14, "物理块头", "序列号=0")

print(f"\n═══ 结果: {passed} 通过, {failed} 失败 ═══")
sys.exit(1 if failed else 0)

