"""

协议9（通感一体化）无线信道单跳MAC帧解析测试
直接运行: python test_csg_hrf_mac.py

覆盖（表12/表13/表139/表142，参见 .trellis/tasks/08-12-protocol9-hrf-mac/）:
- T1 单跳MAC帧直入（版本2，MSDU类型1=应用层报文）
- T2 完整无线 MPDU（channel=hrf, fc_pb：HRF SOF FC + PB + 单跳MAC帧）
- T3 无线发现列表消息（MSDU类型2，表139 TLV + 站点属性表142）
- T4 PLC 版本1 短帧头回归（12B 头解析不受影响）
"""

import _path_setup  # noqa: E402

import crcmod
from csg_new_gen_parser import CSGNewGenParser

_crc24_func = crcmod.mkCrcFun(0x1800063, initCrc=0x000000, rev=True, xorOut=0x000000)
_crc32_func = crcmod.mkCrcFun(0x104C11DB7, initCrc=0x00000000, rev=True, xorOut=0xffffffff)


def find_field(table, name_contains):
    """查找包含指定字符串的字段名对应的行"""
    for row in table:
        if name_contains in row[0]:
            return row
    return None


def find_all_fields(table, name_contains):
    return [row for row in table if name_contains in row[0]]


def _crc24(data: bytes) -> int:
    return _crc24_func(data)


def _crc32(data: bytes) -> int:
    return _crc32_func(data)


def _single_hop_mac(msdu_type: int, payload: bytes) -> bytes:
    """构造单跳MAC帧（表12）：帧头类型0+版本2+保留 + MSDU类型 + MSDU长度(小端) + 载荷 + CRC-32"""
    header = bytes([0x04, msdu_type]) + len(payload).to_bytes(2, 'little')
    return header + payload + _crc32(payload).to_bytes(4, 'little')


def _hrf_sof_fc(src_tei=0x123, dst_tei=0x456, link_id=0x10, frame_len=100,
                pb_size_idx=3, mcs=2, snid_high=0, snid_low=5, std_version=2) -> bytes:
    """构造 HRF SOF 帧 FC（表45 可变区域 + CRC-24 FCS）"""
    fc = bytearray(16)
    fc[0] = (snid_low << 4) | (1 << 3) | 1  # SNID低4位 | 接入指示=1 | 定界符类型=1(SOF)
    fc[1] = src_tei & 0xFF
    fc[2] = ((src_tei >> 8) & 0x0F) | ((dst_tei & 0x0F) << 4)
    fc[3] = (dst_tei >> 4) & 0xFF
    fc[4] = link_id
    fc[5] = frame_len & 0xFF
    fc[6] = ((frame_len >> 8) & 0x0F) | (pb_size_idx << 4)
    fc[7] = mcs & 0x0F
    fc[8:12] = b'\x00\x00\x00\x00'  # 保留
    fc[12] = (std_version << 4) | snid_high
    fcs = _crc24(bytes(fc[:13]))
    fc[13:16] = fcs.to_bytes(3, 'little')
    return bytes(fc)


def test_single_hop_mac_app():
    """T1: 单跳MAC帧直入（版本2 + MSDU类型1 应用层报文）"""
    parser = CSGNewGenParser()
    # 应用层: 端口0x11 + 标识0x0101 + 保留 + 控制域0 + 业务标识0 + 版本1
    app_payload = bytes.fromhex("11 01 01 00 00 00 00 01")
    frame = _single_hop_mac(0x01, app_payload)
    table = parser.parse_to_table(frame)

    row = find_field(table, "版本")
    assert row and row[2] == "2", f"版本字段错误: {row}"
    assert "单跳帧协议" in row[3], f"版本说明错误: {row}"

    row = find_field(table, "MSDU类型")
    assert row and row[2] == "1", f"MSDU类型错误: {row}"
    assert "应用层报文" in row[3], f"MSDU类型说明错误: {row}"

    row = find_field(table, "MSDU长度")
    assert row and row[2] == "8字节", f"MSDU长度错误: {row}"

    assert find_field(table, "报文端口号"), "缺少应用层报文端口号字段"
    row = find_field(table, "报文标识符")
    assert row and "0x0101" in row[2], f"报文标识符错误: {row}"

    row = find_field(table, "完整性校验(CRC-32)")
    assert row and "校验通过" in row[3], f"CRC校验错误: {row}"

    # 版本2 帧头类型 无意义标注
    row = find_field(table, "帧头类型")
    assert "无意义" in row[3], f"帧头类型说明错误: {row}"
    print("[OK] T1 单跳MAC帧直入测试通过")


def test_full_wireless_mpdu():
    """T2: 完整无线 MPDU（channel=hrf, fc_pb：HRF SOF FC + PB + 单跳MAC帧）"""
    parser = CSGNewGenParser()
    app_payload = bytes.fromhex("11 01 01 00 00 00 00 01")
    mac_frame = _single_hop_mac(0x01, app_payload)
    # PB: 头4B(seq 2B LE + 聚合标志 + 保留) + 体(128B) + 保留1B + PBCS 3B
    pb_hdr = bytes([0x00, 0x00, 0x00, 0x00])
    body = mac_frame + b'\x00' * (128 - len(mac_frame))
    pbcs = _crc24(pb_hdr + body + b'\x00').to_bytes(3, 'little')
    pb = pb_hdr + body + b'\x00' + pbcs
    frame = _hrf_sof_fc() + pb

    table = parser.parse_to_table(frame, parse_level="fc_pb", channel="hrf")

    row = find_field(table, "源TEI")
    assert row and row[2] == "291", f"HRF SOF 源TEI错误: {row}"
    row = find_field(table, "目的TEI")
    assert row and row[2] == "1110", f"HRF SOF 目的TEI错误: {row}"
    row = find_field(table, "MCS")
    assert row and row[2] == "2", f"MCS错误: {row}"

    assert find_field(table, "物理块头"), "缺少物理块头"
    # 区分 FC 的"标准版本号"行：MAC 版本行说明必含"单跳帧协议"
    mac_version = [r for r in table if r[0] == "版本" and "单跳帧协议" in r[3]]
    assert mac_version, f"缺少单跳MAC帧版本行: {[r for r in table if r[0] == '版本']}"
    assert mac_version[0][2] == "2", f"MAC帧版本错误: {mac_version[0]}"
    assert find_field(table, "报文端口号"), "缺少应用层分析字段"
    row = find_field(table, "完整性校验(CRC-32)")
    assert row and "校验通过" in row[3], f"CRC校验错误: {row}"
    print("[OK] T2 完整无线MPDU测试通过")


def test_rf_discover_node_list():
    """T3: 无线发现列表消息（MSDU类型2，表139 TLV + 站点属性表142）"""
    parser = CSGNewGenParser()
    # 站点MAC 6B + 统计序号 1B + TLV: 类型0(站点属性) 长度14B
    mac = bytes.fromhex("01 02 03 04 05 06")
    seq = bytes([0x2A])
    # 表142 站点属性14B: CCO MAC 6B + 代理TEI 12b/角色4b + 层级4b/RF跳数4b
    # + 代理上行/下行接收率 + 链路最小接收率 + 发现列表周期 + 老化周期个数
    attr = bytes.fromhex("0A 0B 0C 0D 0E 0F 10 01 20 21 50 60 03 05")
    tlv = bytes([0x00, 14]) + attr
    payload = mac + seq + tlv
    frame = _single_hop_mac(0x02, payload)
    table = parser.parse_to_table(frame)

    row = find_field(table, "MSDU类型")
    assert row and "无线发现列表消息" in row[3], f"MSDU类型说明错误: {row}"
    row = find_field(table, "站点MAC地址")
    assert row and row[2] == "01:02:03:04:05:06", f"站点MAC错误: {row}"
    row = find_field(table, "统计序号")
    assert row and row[2] == "42", f"统计序号错误: {row}"
    row = find_field(table, "信息单元0类型")
    assert row and row[2] == "站点属性信息", f"信息单元类型错误: {row}"
    row = find_field(table, "CCO MAC地址")
    assert row and row[2] == "0A:0B:0C:0D:0E:0F", f"CCO MAC错误: {row}"
    row = find_field(table, "代理TEI")
    assert row and row[2] == "272", f"代理TEI错误: {row}"
    row = find_field(table, "角色")
    assert row and "CCO" in row[3], f"角色错误: {row}"
    row = find_field(table, "链路RF跳数")
    assert row and row[2] == "2", f"RF跳数错误: {row}"
    row = find_field(table, "代理上行接收率")
    assert row and row[2] == "33%", f"上行接收率错误: {row}"
    row = find_field(table, "代理下行接收率")
    assert row and row[2] == "80%", f"下行接收率错误: {row}"
    row = find_field(table, "链路最小接收率")
    assert row and row[2] == "96%", f"最小接收率错误: {row}"
    row = find_field(table, "无线发现列表周期")
    assert row and row[2] == "3s", f"发现列表周期错误: {row}"
    row = find_field(table, "无线接收率老化周期个数")
    assert row and row[2] == "5", f"老化周期个数错误: {row}"
    print("[OK] T3 无线发现列表测试通过")


def test_plc_short_header_regression():
    """T4: PLC 版本1 短帧头回归（12B 头，channel=plc 不受影响）"""
    parser = CSGNewGenParser()
    # 版本1 短帧头(表11, 12B): 帧头类型=1(bit0) 版本=1(bits1-2) → 0x03
    # SNID高位=0 / 发送序号=1 (byte1) / MSDU长度=2 (bytes2-3, LE)
    # 原始目的TEI=0x123 / 原始源TEI=0x456 / SNID低4位=5+重启次数=0 (byte7)
    # 路由跳数=1+广播方向=0 (byte8) / 发送类型=0+限值=0 (byte9) / MSDU序列号=1 (bytes10-11)
    payload = bytes.fromhex("11 01 01 00 00 00 00 01")  # 应用层 8B
    hdr12 = bytes.fromhex("03 01 08 00 23 61 45 05 01 00 01 00")
    frame = hdr12 + payload + _crc32(payload).to_bytes(4, 'little')
    table = parser.parse_to_table(frame)

    row = find_field(table, "版本")
    assert row and row[2] == "1", f"版本字段错误: {row}"
    row = find_field(table, "帧头类型")
    assert row and row[2] == "1", f"帧头类型错误: {row}"
    row = find_field(table, "MSDU长度")
    assert row and row[2] == "8字节", f"MSDU长度错误: {row}"
    row = find_field(table, "原始目的TEI")
    assert row and row[2] == "291", f"原始目的TEI错误: {row}"
    assert find_field(table, "报文端口号"), "缺少应用层分析字段"
    print("[OK] T4 PLC短帧头回归测试通过")


def _user_plc_mpdu() -> bytes:
    """用户实际 PLC 帧（BPLC 1x136B PB，152 字节）"""
    return bytes.fromhex(
        "09 00 F0 FF 01 00 00 41 78 04 20 5B 10 FA 98 4B"
        " 00 00 00 00 03 00 18 00 FF 0F 00 50 11 01 01 00 01 01 11 01 01 00 02 60"
        " F0 01 00 00 0A 00 03 00 06 00 81 61 20 00 00 00 59 06 47 A7"
        + " 00" * 88 + " 42 0D 17".replace(" ", ""))


def test_auto_channel_plc():
    """T5: 用户 PLC 帧 channel=auto → 通道判定=plc，可变区域按表20 解析"""
    parser = CSGNewGenParser()
    frame = _user_plc_mpdu()
    table = parser.parse_to_table(frame, parse_level="fc_pb", channel="auto")

    row = find_field(table, "通道判定")
    assert row and row[2] == "PLC 载波", f"通道判定错误: {row}"
    # 与显式 plc 解析一致（表20: 物理块个数/载波映射表索引/符号数）
    assert find_field(table, "物理块个数"), "缺少BPLC物理块个数字段"
    row = find_field(table, "载波映射表索引")
    assert row and row[2] == "4", f"载波映射表索引错误: {row}"
    assert find_field(table, "符号数"), "缺少BPLC符号数字段"
    print("[OK] T5 自动识别PLC帧测试通过")


def test_auto_channel_hrf():
    """T6: 合成 HRF MPDU channel=auto → 通道判定=hrf，可变区域按表45 解析"""
    parser = CSGNewGenParser()
    app_payload = bytes.fromhex("11 01 01 00 00 00 00 01")
    mac_frame = _single_hop_mac(0x01, app_payload)
    pb = _pb136(mac_frame)
    frame = _hrf_sof_fc() + pb
    table = parser.parse_to_table(frame, parse_level="fc_pb", channel="auto")

    row = find_field(table, "通道判定")
    assert row and row[2] == "HRF 高速无线", f"通道判定错误: {row}"
    # 与显式 hrf 解析一致（表45: MCS/载荷PB大小）
    row = find_field(table, "MCS")
    assert row and row[2] == "2", f"MCS错误: {row}"
    row = find_field(table, "载荷PB大小")
    assert row and "136" in row[3], f"载荷PB大小错误: {row}"
    assert find_field(table, "报文端口号"), "缺少应用层分析字段"
    print("[OK] T6 自动识别HRF帧测试通过")


def _pb136(mac_frame: bytes) -> bytes:
    """构造 136B PB：头4B + 体128B + 保留1B + PBCS 3B"""
    pb_hdr = bytes([0x00, 0x00, 0x00, 0x00])
    body = mac_frame + b'\x00' * (128 - len(mac_frame))
    pbcs = _crc24(pb_hdr + body + b'\x00').to_bytes(3, 'little')
    return pb_hdr + body + b'\x00' + pbcs


def test_auto_channel_pb40_strong_signal():
    """T7: 载荷PB大小=40 → HRF（表44 值1 为 HRF 独有强信号）"""
    parser = CSGNewGenParser()
    app_payload = bytes.fromhex("11 01 01 00 00 00 00 01")
    mac_frame = _single_hop_mac(0x01, app_payload)
    # 40B PB: 头4 + 体32 + 保留1 + PBCS 3
    pb_hdr = bytes([0x00, 0x00, 0x00, 0x00])
    body = mac_frame + b'\x00' * (32 - len(mac_frame))
    pbcs = _crc24(pb_hdr + body + b'\x00').to_bytes(3, 'little')
    pb = pb_hdr + body + b'\x00' + pbcs
    frame = _hrf_sof_fc(pb_size_idx=1) + pb  # 表44 值1 = 40字节
    table = parser.parse_to_table(frame, parse_level="fc_pb", channel="auto")

    row = find_field(table, "通道判定")
    assert row and row[2] == "HRF 高速无线", f"PB40强信号通道判定错误: {row}"
    row = find_field(table, "载荷PB大小")
    assert row and "40" in row[3], f"载荷PB大小错误: {row}"
    print("[OK] T7 PB40强信号测试通过")


def test_auto_channel_explicit_unchanged():
    """T8: 显式 channel=plc/hrf 行为不变（无通道判定行，解析结果一致）"""
    parser = CSGNewGenParser()
    frame = _user_plc_mpdu()
    table = parser.parse_to_table(frame, parse_level="fc_pb", channel="plc")
    assert find_field(table, "通道判定") is None, "显式plc不应出现通道判定行"
    assert find_field(table, "符号数"), "显式plc解析缺少符号数"

    app_payload = bytes.fromhex("11 01 01 00 00 00 00 01")
    mac_frame = _single_hop_mac(0x01, app_payload)
    hrf = _hrf_sof_fc() + _pb136(mac_frame)
    table2 = parser.parse_to_table(hrf, parse_level="fc_pb", channel="hrf")
    assert find_field(table2, "通道判定") is None, "显式hrf不应出现通道判定行"
    row = find_field(table2, "MCS")
    assert row and row[2] == "2", f"显式hrf MCS错误: {row}"
    print("[OK] T8 显式通道回归测试通过")


if __name__ == "__main__":
    test_single_hop_mac_app()
    test_full_wireless_mpdu()
    test_rf_discover_node_list()
    test_plc_short_header_regression()
    test_auto_channel_plc()
    test_auto_channel_hrf()
    test_auto_channel_pb40_strong_signal()
    test_auto_channel_explicit_unchanged()
    print("=" * 50)
    print("[OK] 全部测试通过")