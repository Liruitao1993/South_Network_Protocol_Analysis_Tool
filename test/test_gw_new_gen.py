# -*- coding: utf-8 -*-
"""国网新一代双模通信互联互通协议 解析器测试"""

import _path_setup  # noqa: E402

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
# 项目根由 _path_setup 提供，此处不再依赖 __file__

from gw_new_gen_parser import GWNewGenParser

passed = 0
failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [✅] {name}")
    else:
        failed += 1
        print(f"  [❌] {name} {detail}")


def test_app_after_fc():
    """应用层紧跟FC(无MAC帧头)"""

    print("Test: 应用层紧跟FC")
    parser = GWNewGenParser()
    # 业务数据: version=1, hdr_len=8, data_len=8
    # 编码: b2低4位=data_len低位=8, b3低4位=data_len高位=0 → data_len=(0<<4)|8=8
    frame = bytes([
        # FC 16字节
        0x11,0x00,0x01,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        # 应用层(offset 16): port=0x11, msg_id=0x0001(LE:01 00), control=0x00
        0x11,0x01,0x00,0x00,
        # 业务数据: b0=0x41(ver=1,hdr_h=1) b1=0x08(hdr_l=8)
        # b2=0xF3(proto=3,data_len低=F) b3=0x03(data_len高=3) → data_len=0x3F=63
        0x41,0x08,0xF3,0x03,0x42,0x0D,0x23,0x05,
        # 转发数据(8字节)
        0x68,0xAA,0xAA,0xAA,0xAA,0xAA,0xAA,0x16,
    ])
    r = parser.parse_to_table(frame)
    check("解析结果非空", len(r) > 0)
    len_rows = [row for row in r if "转发数据长度" in row[0]]
    check("找到转发数据长度", len(len_rows) > 0)
    if len_rows:
        check("数据长度=63字节", "63" in len_rows[0][2], f"got: {len_rows[0][2]}")
    port_rows = [row for row in r if "报文端口号" in row[0]]
    check("报文端口号=抄表业务", len(port_rows) > 0 and "抄表" in port_rows[0][2])


def test_false_positive_rejection():
    """假阳性拒绝: MAC头中含类似port+msg_id的字节"""
    print("\nTest: 假阳性拒绝")
    parser = GWNewGenParser()
    # 假阳性区域: 11 01 00 01 (port=0x11, msg_id=0x0001, control=0x01≠0)
    # 真正应用层(offset 20): port=0x11, msg_id=0x0001, control=0x00
    # 业务数据: version=1, hdr_len=8, proto=3, data_len=8
    frame = bytes([
        # FC 16字节
        0x11,0x00,0x01,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        # 假阳性区域: 11 01 00 01 (control=0x01≠0)
        0x11,0x01,0x00,0x01,
        # 真正应用层(offset 20): port=0x11, msg_id=0x0001, control=0x00
        0x11,0x01,0x00,0x00,
        # 业务数据: version=1, hdr_len=8, data_len=63
        # b2=0xF3(proto=3,data_len低=F), b3=0x03(data_len高=3) → 0x3F=63
        0x41,0x08,0xF3,0x03,0x42,0x0D,0x23,0x05,
        # 转发数据(8字节示例)
        0x68,0x11,0x22,0x33,0x44,0x55,0x66,0x16,
    ])
    r = parser.parse_to_table(frame)
    len_rows = [row for row in r if "转发数据长度" in row[0]]
    check("找到转发数据长度", len(len_rows) > 0)
    if len_rows:
        check("数据长度=63字节(非3843)", "63" in len_rows[0][2], f"got: {len_rows[0][2]}")
    port_rows = [row for row in r if "报文端口号" in row[0]]
    check("只找到1个应用层", len(port_rows) == 1, f"found {len(port_rows)}")


def test_hcs_pb_app():
    """HCS(3B)+PB(1B)+应用层(无MAC帧头)"""
    print("\nTest: HCS+PB+应用层")
    parser = GWNewGenParser()
    frame = bytes([
        # FC 16字节
        0x11,0x03,0x00,0x00,0x01,0x32,0xF3,0x03,
        0x42,0x0D,0x23,0x05,0x68,0x3D,0x00,0x43,
        # HCS(3B)+PB(1B) - 含假阳性0x11但后续验证不通过
        0xAB,0x11,0xCD,0x00,
        # 应用层(offset 20): port=0x11, msg_id=0x0001, control=0x00
        0x11,0x01,0x00,0x00,
        # 业务数据: version=1, hdr_len=8, data_len=63
        # b2=0xF3(proto=3,data_len低=F), b3=0x03(data_len高=3) → 0x3F=63
        0x41,0x08,0xF3,0x03,0x42,0x0D,0x23,0x05,
        # 转发数据(8字节示例)
        0x68,0x11,0x22,0x33,0x44,0x55,0x66,0x16,
    ])
    r = parser.parse_to_table(frame)
    len_rows = [row for row in r if "转发数据长度" in row[0]]
    check("找到转发数据长度", len(len_rows) > 0)
    if len_rows:
        check("数据长度=63字节", "63" in len_rows[0][2], f"got: {len_rows[0][2]}")
    port_rows = [row for row in r if "报文端口号" in row[0]]
    check("只找到1个应用层", len(port_rows) == 1, f"found {len(port_rows)}")


def test_mac_header_app():
    """完整MAC帧头(15B)+应用层"""
    print("\nTest: MAC帧头+应用层")
    parser = GWNewGenParser()
    frame = bytes([
        # FC 16字节
        0x11,0x00,0x01,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        # MAC帧头(15字节) - byte1=0x11为假阳性端口但msg_id不匹配
        0x00,0x11,0x00,0x01,0x00,0x05,0x30,0x00,
        0x4B,0x00,0x00,0x22,0x00,0x00,0x22,
        # 应用层(offset 31): port=0x11, msg_id=0x0001, control=0x00
        0x11,0x01,0x00,0x00,
        # 业务数据: version=1, hdr_len=8, data_len=63
        # b2=0xF3(proto=3,data_len低=F), b3=0x03(data_len高=3) → 0x3F=63
        0x41,0x08,0xF3,0x03,0x42,0x0D,0x23,0x05,
        # 转发数据(8字节示例)
        0x68,0x11,0x22,0x33,0x44,0x55,0x66,0x16,
    ])
    r = parser.parse_to_table(frame)
    len_rows = [row for row in r if "转发数据长度" in row[0]]
    check("找到转发数据长度", len(len_rows) > 0)
    if len_rows:
        check("数据长度=63字节", "63" in len_rows[0][2], f"got: {len_rows[0][2]}")
    port_rows = [row for row in r if "报文端口号" in row[0]]
    check("只找到1个应用层", len(port_rows) == 1, f"found {len(port_rows)}")
    mac_rows = [row for row in r if "MAC帧头" in row[0]]
    check("找到MAC帧头解析", len(mac_rows) > 0)


def test_confirm_deny():
    """确认/否认报文(0x0020)"""
    print("\nTest: 确认/否认报文")
    parser = GWNewGenParser()
    frame = bytes([
        # FC 16字节
        0x11,0x00,0x01,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        # 应用层: port=0x11, msg_id=0x0020(LE:20 00), control=0x00
        0x11,0x20,0x00,0x00,
        # 业务数据: version=1, hdr_len=4, dir=0, confirm=1, seq=0x0042
        0x41,0x04,0x42,0x00,
    ])
    r = parser.parse_to_table(frame)
    msg_rows = [row for row in r if "报文ID" in row[0]]
    check("报文ID=确认/否认", len(msg_rows) > 0 and "确认" in msg_rows[0][2])
    confirm_rows = [row for row in r if "确认位" in row[0]]
    check("找到确认位字段", len(confirm_rows) > 0)


def test_time_sync():
    """校时报文(0x0004)"""
    print("\nTest: 校时报文")
    parser = GWNewGenParser()
    frame = bytes([
        # FC 16字节
        0x11,0x00,0x01,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        # 应用层: port=0x11, msg_id=0x0004(LE:04 00), control=0x00
        0x11,0x04,0x00,0x00,
        # 业务数据: version=1, hdr_len=4, data_len=8, seq=0x0001
        0x41,0x04,0x00,0x08,0x01,0x00,
        # BCD时间: 2026-01-27 06:12:30
        0x30,0x12,0x06,0x27,0x01,0x26,
    ])
    r = parser.parse_to_table(frame)
    time_rows = [row for row in r if "校时数据" in row[0]]
    check("找到校时数据", len(time_rows) > 0)
    if time_rows:
        check("BCD时间含2026", "2026" in time_rows[0][2], f"got: {time_rows[0][2]}")


def test_msg_id_lookup():
    """报文ID/端口号查找"""
    print("\nTest: 报文ID查找")
    parser = GWNewGenParser()
    for msg_id, name in parser.MSG_IDS.items():
        assert name, f"报文ID 0x{msg_id:04X} 没有名称"
    check(f"报文ID: {len(parser.MSG_IDS)}个全部有描述", True)
    for port, name in parser.PORT_NAMES.items():
        assert name, f"端口号 0x{port:02X} 没有名称"
    check(f"端口号: {len(parser.PORT_NAMES)}个全部有描述", True)


def test_short_frame():
    """过短帧"""
    print("\nTest: 过短帧")
    parser = GWNewGenParser()
    result = parser.parse_to_table(bytes([0x10]))
    check("过短帧不崩溃", len(result) > 0)


def _fc_with_version(nibble):
    """构造 FC(16B), 字节12 D[7:4]=标准版本号 nibble"""
    return bytes([
        0x11, 0x00, 0x01, 0x00, 0x34, 0x02, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, (nibble << 4), 0x00, 0x00, 0x00,
    ])


def test_version_detection_row():
    """根据FC字节12标准版本号自动判定 HDC 1.0 / HDC 2.0"""
    print("\nTest: FC版本号自动判定")
    parser = GWNewGenParser()
    # nibble=0 -> HDC 1.0
    r0 = parser.parse_to_table(_fc_with_version(0) + bytes(8))
    v0 = [row for row in r0 if row[0] == "协议版本判定"]
    check("HDC1.0: 找到协议版本判定行", len(v0) > 0)
    if v0:
        check("HDC1.0: 版本名=HDC 1.0", v0[0][2] == "HDC 1.0", f"got: {v0[0][2]}")
    # nibble=1 -> HDC 2.0
    r1 = parser.parse_to_table(_fc_with_version(1) + bytes(8))
    v1 = [row for row in r1 if row[0] == "协议版本判定"]
    check("HDC2.0: 找到协议版本判定行", len(v1) > 0)
    if v1:
        check("HDC2.0: 版本名=HDC 2.0", v1[0][2] == "HDC 2.0", f"got: {v1[0][2]}")


def test_std_mac_header_versioning():
    """标准MAC帧头: HDC1.0下3处新增字段标为保留"""
    print("\nTest: 标准MAC帧头版本化")
    parser = GWNewGenParser()
    mac = bytes([
        0x00, 0x00, 0x00, 0x00,
        0x25,                    # byte4: 发送次数限值=5, D5=1
        0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0x00,                    # byte12
        0x05,                    # byte13 组网序列号
        0x00,                    # byte14 保留
        0x11,                    # byte15 链路标识符/保留
    ])
    # HDC 2.0
    r2 = parser._parse_mac_std_header(mac, 0, std_version=1)
    names2 = [row[0].strip() for row in r2]
    check("HDC2.0: 含聚合MAC帧标志", "聚合MAC帧标志" in names2)
    check("HDC2.0: 含链路标识符", "链路标识符" in names2)
    check("HDC2.0: 含发送帧序号", "发送帧序号" in names2)
    # HDC 1.0
    r1 = parser._parse_mac_std_header(mac, 0, std_version=0)
    names1 = [row[0].strip() for row in r1]
    check("HDC1.0: D5标为保留", "保留(D5)" in names1)
    check("HDC1.0: 链路标识位标为保留", "保留(链路标识位)" in names1)
    check("HDC1.0: 帧序号位标为保留", "保留(帧序号位)" in names1)
    check("HDC1.0: 无链路标识符字段", "链路标识符" not in names1)


def test_singlehop_header_versioning():
    """单跳MAC帧头: 消息类型表与D7按版本区分"""
    print("\nTest: 单跳MAC帧头版本化")
    parser = GWNewGenParser()
    sh = bytes([0x01, 0x00, 0x08, 0x80])  # version=1, msg_type=0, agg=1
    # HDC 2.0
    r2 = parser._parse_mac_singlehop_header(sh, 0, std_version=1)
    names2 = [row[0].strip() for row in r2]
    msg2 = [row for row in r2 if row[0].strip() == "消息类型"]
    check("HDC2.0: 消息类型0=无线发现列表", msg2 and "无线发现列表" in msg2[0][1])
    check("HDC2.0: D7=聚合MAC帧标志", "聚合MAC帧标志" in names2)
    # HDC 1.0
    r1 = parser._parse_mac_singlehop_header(sh, 0, std_version=0)
    names1 = [row[0].strip() for row in r1]
    msg1 = [row for row in r1 if row[0].strip() == "消息类型"]
    check("HDC1.0: 消息类型0=发现列表消息", msg1 and "发现列表消息" in msg1[0][1])
    check("HDC1.0: D7标为保留", "保留(D7)" in names1)


def test_direct_mgmt_after_fc():
    """FC后直接网络管理消息: 无线信道冲突上报(MMTYPE=0x0080大端)

    帧结构: FC(16B) + 管理消息头(MMTYPE 2B + 保留 2B) + 内容
    MMTYPE 按文档表43大端存储(0x0080 -> 字节 00 80)
    """
    print("\nTest: FC后直接管理消息(无线信道冲突上报)")
    parser = GWNewGenParser()
    frame = bytes.fromhex(
        "C1 20 00 01 00 01 B2 B7 00 0F 80 FF 00 00 01 00 "
        "80 00 00 00 00 01 00 90 98 01 02 29 05 03 03 "
        "E0 C4 28 55 00 04 65 ED".replace(" ", ""))
    table = parser.parse_to_table(frame)
    # MMTYPE 大端 = 0x0080 无线信道冲突上报
    mm = find_row(table, "管理消息类型(MMTYPE)")
    check("MMTYPE=0x0080", mm and mm[2] == "0x0080")
    check("冲突上报名称", mm and "无线信道冲突上报" in mm[3])
    # 邻居网络个数=2 (分组布局: 先信道号后option)
    cnt = find_row(table, "邻居网络个数")
    check("邻居网络个数=2", cnt and cnt[2] == "2")
    # 分组布局: 先所有信道号(29,05) 再所有option(03,03)
    n0 = find_row(table, "邻居网络[0]")
    check("邻居网络[0]信道号+option", n0 and n0[2] == "信道号=41 option=0x03")
    n1 = find_row(table, "邻居网络[1]")
    check("邻居网络[1]信道号+option", n1 and n1[2] == "信道号=5 option=0x03")
    # 纯PB输入(剥离FC后): mac_only/pb_only 应正确识别管理消息
    # 用户勾选仅PB时输入的是无FC的纯数据
    pure_pb = frame[16:]
    for lvl in ("mac_only", "pb_only"):
        t2 = parser.parse_to_table(pure_pb, parse_level=lvl)
        mm2 = find_row(t2, "管理消息类型(MMTYPE)")
        check(f"纯PB输入 {lvl}级别 MMTYPE=0x0080", mm2 and mm2[2] == "0x0080")
    # app 级别: 完整帧或纯管理消息均可
    t3 = parser.parse_to_table(frame, parse_level="app")
    mm3 = find_row(t3, "管理消息类型(MMTYPE)")
    check("app级别 MMTYPE=0x0080", mm3 and mm3[2] == "0x0080")


def find_row(table, name_contains):
    for row in table:
        if name_contains in row[0]:
            return row
    return None


if __name__ == "__main__":
    test_app_after_fc()
    test_false_positive_rejection()
    test_hcs_pb_app()
    test_mac_header_app()
    test_confirm_deny()
    test_time_sync()
    test_msg_id_lookup()
    test_short_frame()
    test_version_detection_row()
    test_std_mac_header_versioning()
    test_singlehop_header_versioning()
    test_direct_mgmt_after_fc()
    print(f"\n═══ 结果: {passed} 通过, {failed} 失败 ═══")
    if failed > 0:
        sys.exit(1)
