"""测试国网新一代双模协议新增解析级别：mac_only和pb_only"""

import _path_setup  # noqa: E402

import sys
import io

# 确保中文输出正常
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from gw_new_gen_parser import GWNewGenParser


def test_mac_only():
    """测试仅MAC帧解析模式：输入即 MAC 帧（不含 PBH），从字节 0 解析。

    契约（AGENTS §8 陷阱19 / 协议9 同口径）：mac_only 不得自动剥离物理块头。
    pb_only 仍按「PBH+MAC」解析，见 test_pb_only_sof。
    """

    print("Test: mac_only - 仅MAC帧解析（输入即MAC帧，不含PBH）")
    parser = GWNewGenParser()

    # 标准MAC帧头(版本=0, 源TEI=0, 目的TEI=1, MSDU类型0=网络管理消息) + MAC地址12B
    # 现场关联请求帧（协议10/11 共用样本，见 test_hdc10_mac_only_contract）
    mac_data = bytes.fromhex(
        "00000100019673005C80FF0800960000"
        "200000000124010101010101"
        "000000002000000001240100000000000000000001030001"
        "329FBACA69DE640900000000A860CAF104A18A64E8F2"
        "0000040099F4484C3039000000000000000065F9"
        "0000000000000000000000000000000000000000000000000000"
        "688150C4"
        "0000000000000000BA711E"
    )

    result = parser.parse_to_table(mac_data, parse_level='mac_only')

    print(f"  解析结果行数: {len(result)}")

    mode_row = [r for r in result if '解析模式' in r[0]]
    pbh_row = [r for r in result if '物理块头' in r[0] or 'PBH' in r[0]]
    src_tei_row = [r for r in result if '原始源TEI' in r[0]]
    dst_tei_row = [r for r in result if '原始目的TEI' in r[0]]
    msdu_type_row = [r for r in result if 'MSDU类型' in r[0]]
    mmtyp_row = [r for r in result if 'MMTYPE' in r[0]]

    if mode_row:
        print(f"  解析模式: {mode_row[0][2]}")
        assert 'MAC帧' in mode_row[0][2], "应为MAC帧模式"

    # 契约：mac_only 不得出现物理块头
    assert not pbh_row, f"mac_only 不应解析物理块头，实际: {pbh_row}"
    assert mode_row and '不含' in str(mode_row[0][3]), "说明应交代不含PBH"

    assert src_tei_row and src_tei_row[0][2] == '0', "源TEI应为0"
    assert dst_tei_row and dst_tei_row[0][2] == '1', "目的TEI应为1"
    assert msdu_type_row and msdu_type_row[0][2] == '0', "MSDU类型应为0(网络管理消息)"
    assert mmtyp_row and mmtyp_row[0][2] == '0x0000', "MMTYPE应为0x0000(关联请求)"
    print(f"  源TEI: {src_tei_row[0][2]}  目的TEI: {dst_tei_row[0][2]}")
    print(f"  MMTYPE: {mmtyp_row[0][2] if mmtyp_row else 'N/A'}")

    print("  [✅] mac_only解析成功\n")


def test_pb_only_sof():
    """测试仅PB解析模式 - SOF帧（物理块头1字节）"""
    print("Test: pb_only - SOF帧")
    parser = GWNewGenParser()

    # 实际SOF帧物理块: PBH(0xC0) + 标准MAC帧头(16B) + MAC地址(12B)
    pb_data = bytes.fromhex("C01000FF2F0114000024001108003F0000009098016 3FFFFFFFFFFFF08".replace(" ", ""))

    result = parser.parse_to_table(pb_data, parse_level='pb_only', frame_type=1)

    print(f"  解析结果行数: {len(result)}")

    # 查找关键行
    mode_row = [r for r in result if '解析模式' in r[0]]
    pbh_row = [r for r in result if '物理块头' in r[0]]
    seq_row = [r for r in result if 'PB序列号' in r[0]]
    start_row = [r for r in result if '帧起始标志' in r[0]]
    end_row = [r for r in result if '帧结束标志' in r[0]]
    ver_row = [r for r in result if r[0].strip() == '版本']

    if mode_row:
        print(f"  解析模式: {mode_row[0][2]}")
        assert 'SOF帧' in mode_row[0][2], "应为SOF帧"

    # PBH=0xC0: 序列号=0, 帧起始=1, 帧结束=1，仅1字节
    assert pbh_row, "应解析出物理块头"
    assert pbh_row[0][5] - pbh_row[0][4] == 1, "PB头应为1字节"
    assert pbh_row[0][1] == '0xC0', f"PBH原始值应为0xC0, 实际={pbh_row[0][1]}"
    assert seq_row and seq_row[0][2] == '0', "PB序列号应为0"
    assert start_row and start_row[0][1] == '1', "帧起始标志应为1"
    assert end_row and end_row[0][1] == '1', "帧结束标志应为1"
    # MAC帧头版本=0(标准帧协议)，从offset=1开始
    assert ver_row and ver_row[0][2] == '0', "MAC帧头版本应为0(标准帧协议)"
    assert ver_row[0][4] == 1, "MAC帧头应从偏移1开始(PB头仅1字节)"
    print(f"  PBH: {pbh_row[0][1]}  帧起始={start_row[0][1]} 帧结束={end_row[0][1]}")

    print("  [✅] pb_only SOF帧解析成功\n")


def test_pb_only_beacon():
    """测试仅PB解析模式 - 信标帧"""
    print("Test: pb_only - 信标帧")
    parser = GWNewGenParser()
    
    # 信标帧PB数据：信标类型(1B) + 信标序列号(1B) + NID(2B,小端:34 12→0x1234) + 内容
    beacon_data = bytes.fromhex("01053412AABBCCDD")
    
    result = parser.parse_to_table(beacon_data, parse_level='pb_only', frame_type=0)
    
    print(f"  解析结果行数: {len(result)}")
    
    # 查找关键行
    mode_row = [r for r in result if '解析模式' in r[0]]
    beacon_type_row = [r for r in result if '信标类型' in r[0]]
    nid_row = [r for r in result if 'NID' in r[0]]
    
    if mode_row:
        print(f"  解析模式: {mode_row[0][2]}")
        assert '信标帧' in mode_row[0][2], "应为信标帧"
    
    if beacon_type_row:
        print(f"  信标类型: {beacon_type_row[0][2]}")
    
    if nid_row:
        print(f"  NID: {nid_row[0][2]}")
        assert '1234' in nid_row[0][1].upper(), "NID应为0x1234"
    
    print("  [✅] pb_only 信标帧解析成功\n")


def test_pb_only_ack():
    """测试仅PB解析模式 - ACK帧"""
    print("Test: pb_only - ACK帧")
    parser = GWNewGenParser()
    
    # ACK帧PB数据：确认类型(1B) + 确认TEI(2B,小端:19 00→0x0019) + 序列号列表
    ack_data = bytes.fromhex("021900AABB")
    
    result = parser.parse_to_table(ack_data, parse_level='pb_only', frame_type=2)
    
    print(f"  解析结果行数: {len(result)}")
    
    # 查找关键行
    mode_row = [r for r in result if '解析模式' in r[0]]
    ack_type_row = [r for r in result if '确认类型' in r[0]]
    ack_tei_row = [r for r in result if '确认TEI' in r[0]]
    
    if mode_row:
        print(f"  解析模式: {mode_row[0][2]}")
        assert 'ACK' in mode_row[0][2], "应为ACK帧"
    
    if ack_tei_row:
        print(f"  确认TEI: {ack_tei_row[0][2]}")
        assert '0019' in ack_tei_row[0][1].upper(), "TEI应为0x0019"
    
    print("  [✅] pb_only ACK帧解析成功\n")


def test_pb_only_net():
    """测试仅PB解析模式 - NET帧"""
    print("Test: pb_only - NET帧")
    parser = GWNewGenParser()
    
    # NET帧PB数据：网间类型(1B) + 网间标识(2B,小端:78 56→0x5678) + 协调数据
    net_data = bytes.fromhex("037856AABBCC")
    
    result = parser.parse_to_table(net_data, parse_level='pb_only', frame_type=3)
    
    print(f"  解析结果行数: {len(result)}")
    
    # 查找关键行
    mode_row = [r for r in result if '解析模式' in r[0]]
    net_type_row = [r for r in result if '网间类型' in r[0]]
    net_id_row = [r for r in result if '网间标识' in r[0]]
    
    if mode_row:
        print(f"  解析模式: {mode_row[0][2]}")
        assert 'NET' in mode_row[0][2], "应为NET帧"
    
    if net_id_row:
        print(f"  网间标识: {net_id_row[0][2]}")
        assert '5678' in net_id_row[0][1].upper(), "网间标识应含0x5678"
    
    print("  [✅] pb_only NET帧解析成功\n")


if __name__ == '__main__':
    test_mac_only()
    test_pb_only_sof()
    test_pb_only_beacon()
    test_pb_only_ack()
    test_pb_only_net()
    print("=" * 50)
    print("所有新增解析级别测试通过！")
