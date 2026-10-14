"""

新一代载波协议 (通感一体化) 解析器测试
直接运行: python test_csg_new_gen.py
"""

import _path_setup  # noqa: E402,F401

from csg_new_gen_parser import CSGNewGenParser


def find_field(table, name_contains):
    """查找包含指定字符串的字段名对应的行"""
    for row in table:
        if name_contains in row[0]:
            return row
    return None


def find_all_fields(table, name_contains):
    """查找所有包含指定字符串的字段"""
    return [row for row in table if name_contains in row[0]]


def test_confirm():
    """测试确认帧（应用层直接输入）"""
    parser = CSGNewGenParser()
    # 端口号 0x11 + 标识符 0x0101(LE) + 保留 0x00
    # + 控制域 0x0000(LE, 确认/否认) + 业务标识 0x00 + 版本 0x01 + 帧序号 0x0001(LE) + 帧长 0x0000(LE)
    frame = bytes.fromhex("11 01 01 00 00 00 00 01 00 01 00 00".replace(" ", ""))
    table = parser.parse_to_table(frame)

    assert find_field(table, "确认/否认负载"), "缺少确认负载字段"
    row = find_field(table, "确认/否认负载")
    assert row[2] == "确认", f"确认帧解析值错误: {row}"
    print("[OK] 确认帧测试通过")


def test_deny():
    """测试否认帧"""
    parser = CSGNewGenParser()
    # 控制域 0x0000 + 业务标识 0x01 + 版本 0x01 + 帧序号 0x0001 + 帧长 0x0001 + 原因码 0x04(格式错误)
    frame = bytes.fromhex("11 01 01 00 00 00 01 01 00 01 00 01 04".replace(" ", ""))
    table = parser.parse_to_table(frame)

    row = find_field(table, "否认原因码")
    assert row is not None, "缺少否认原因码字段"
    assert row[2] == "4", f"否认原因码值错误: {row}"
    assert "格式错误" in row[3], f"否认原因码说明错误: {row}"
    print("[OK] 否认帧测试通过")


def test_data_transparent_to_device_downlink():
    """测试数据透传至设备下行业务"""
    parser = CSGNewGenParser()
    # 端口号 0x11 + 标识符 0x0101 + 保留 0x00
    # 控制域 0x0011(LE: 11 00, 下行/数据传输) + 业务标识 0x00 + 版本 0x01 + 帧序号 0x0001
    # 帧长: 之后所有 payload 字节数
    # payload: 源地址 6B(00 00 00 00 00 00) + 目的地址 6B(11 22 33 44 55 66) + 超时 0x0A + 保留 0x00 + 长度 2B LE(0x0003) + 数据 01 02 03
    header = bytes.fromhex("11 01 01 00 11 00 00 01 00 01".replace(" ", ""))
    payload = bytes.fromhex("00 00 00 00 00 00 11 22 33 44 55 66 0A 00 03 00 01 02 03".replace(" ", ""))
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    assert find_field(table, "源地址"), "缺少源地址字段"
    assert find_field(table, "目的地址"), "缺少目的地址字段"
    assert find_field(table, "设备超时时间"), "缺少设备超时时间字段"
    assert find_field(table, "转发数据长度"), "缺少转发数据长度字段"
    assert find_field(table, "转发数据内容"), "缺少转发数据内容字段"

    timeout_row = find_field(table, "设备超时时间")
    assert timeout_row[2] == "10", f"超时时间错误: {timeout_row}"

    len_row = find_field(table, "转发数据长度")
    assert len_row[2] == "3", f"转发数据长度错误: {len_row}"

    data_row = find_field(table, "转发数据内容")
    assert "01 02 03" in data_row[1], f"转发数据内容错误: {data_row}"
    print("[OK] 数据透传至设备下行测试通过")


def test_data_transparent_to_module_uplink():
    """测试数据透传至模块上行业务"""
    parser = CSGNewGenParser()
    # 控制域: D15=1(上行), 保留=1, 帧类型=1 => 0x8011, LE: 11 80
    header = bytes.fromhex("11 01 01 00 11 80 01 01 00 02".replace(" ", ""))
    payload = bytes.fromhex("00 00 00 00 00 00 11 22 33 44 55 66 00 00 05 00 11 22 33 44 55".replace(" ", ""))
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    assert find_field(table, "业务代码"), "缺少业务代码字段"
    assert find_field(table, "数据转发长度"), "缺少数据转发长度字段"
    assert find_field(table, "数据转发内容"), "缺少数据转发内容字段"

    len_row = find_field(table, "数据转发长度")
    assert len_row[2] == "5", f"数据转发长度错误: {len_row}"
    print("[OK] 数据透传至模块上行测试通过")


def test_concurrent_meter_read_downlink():
    """测试并发抄读端设备下行业务 (表22/表23)"""
    parser = CSGNewGenParser()
    # 应用层头: 端口0x11 + 标识0x0101 + 保留0x00 + 控制域0x0011(LE,下行/数据传输)
    header = bytes.fromhex("11 01 01 00 11 00 02 01 00 03".replace(" ", ""))
    # 表22: 源地址6 + 目的地址6 + 配置字 + 报文间间隔 + 设备超时时间 + 保留 + 列表长度2(LE)
    # 配置字 0x70 = D4未应答重试1 / D5否认重试1 / D6~D7最大重试1
    payload_prefix = bytes.fromhex("00 00 00 00 00 00 11 22 33 44 55 66 70 05 0A 00".replace(" ", ""))
    # 表23: 报文条数1 + {长度2(保留4位+长度12位) + 内容Ln}
    msg_list = bytes.fromhex("02 02 00 AA BB 03 00 CC DD EE".replace(" ", ""))
    list_len = len(msg_list)
    payload = payload_prefix + bytes([list_len & 0xFF, (list_len >> 8) & 0xFF]) + msg_list
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    cfg = find_field(table, "配置字")
    assert cfg, "缺少配置字字段"
    assert "未应答重试=1" in cfg[3] and "否认重试=1" in cfg[3] and "最大重试=1" in cfg[3], f"配置字位定义错误: {cfg}"
    assert find_field(table, "报文间间隔"), "缺少报文间间隔字段"
    assert find_field(table, "设备超时时间"), "缺少设备超时时间字段"
    assert find_field(table, "报文列表对象长度"), "缺少报文列表对象长度字段"
    cnt = find_field(table, "报文条数")
    assert cnt and cnt[2] == "2", f"报文条数应为2, 实际: {cnt}"
    msgs = find_all_fields(table, "内容")
    assert len(msgs) == 2, f"应解析出2条报文内容，实际: {len(msgs)}"
    # 不应有剩余未解析数据
    assert not find_field(table, "剩余数据"), f"存在未解析剩余数据: {find_field(table, '剩余数据')}"
    print("[OK] 并发抄读端设备下行测试通过")


def test_concurrent_meter_read_uplink():
    """测试并发抄读端设备上行业务 (表24/表23)"""
    parser = CSGNewGenParser()
    header = bytes.fromhex("11 01 01 00 11 80 02 01 00 07".replace(" ", ""))
    # 表24: 源地址6 + 目的地址6 + 应答状态(保留4位+状态4位) + 保留2 + 列表长度2(LE)
    # 应答状态=0(正常)
    payload_prefix = bytes.fromhex("11 22 33 44 55 66 00 00 00 00 00 00 00 00 00".replace(" ", ""))
    # 表23: 报文条数1 + 报文0(长度2 + 内容2)
    msg_list = bytes.fromhex("01 02 00 AA BB".replace(" ", ""))
    list_len = len(msg_list)
    payload = payload_prefix + bytes([list_len & 0xFF, (list_len >> 8) & 0xFF]) + msg_list
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    st = find_field(table, "应答状态")
    assert st, "缺少应答状态字段"
    assert "正常应答" in st[3], f"应答状态说明错误: {st}"
    cnt = find_field(table, "报文条数")
    assert cnt and cnt[2] == "1", f"报文条数应为1, 实际: {cnt}"
    msgs = find_all_fields(table, "内容")
    assert len(msgs) == 1, f"上行应解析出1条报文内容，实际: {len(msgs)}"
    assert not find_field(table, "剩余数据"), "存在未解析剩余数据"
    print("[OK] 并发抄读端设备上行测试通过")


def test_concurrent_meter_read_real_frame():
    """真实报文回归: 含2条DLT645读数据请求的并发抄读帧"""
    parser = CSGNewGenParser()
    frame = bytes.fromhex(
        "19012000030000417804005B1000000000000000030045000210004111"
        "0805000301110101000160020109003700640198900000011100682119"
        "70051E0025000210006801110068211968110433333433661610006801"
        "1100682119681104343433376B16A89D0543"
        + "00" * 44 + "0B8F8D"
    )
    table = parser.parse_to_table(frame, parse_level="auto")
    sid = find_field(table, "业务标识")
    assert sid and sid[2] == "2", f"业务标识应为2, 实际: {sid}"
    cnt = find_field(table, "报文条数")
    assert cnt and cnt[2] == "2", f"报文条数应为2, 实际: {cnt}"
    msgs = find_all_fields(table, "内容")
    assert len(msgs) == 2, f"应解析出2条抄读报文，实际: {len(msgs)}"
    msg0 = msgs[0][1]
    assert msg0 == "68 01 11 00 68 21 19 68 11 04 33 33 34 33 66 16", f"报文0内容错误: {msg0}"
    msg1 = msgs[1][1]
    assert msg1 == "68 01 11 00 68 21 19 68 11 04 34 34 33 37 6B 16", f"报文1内容错误: {msg1}"
    assert not find_field(table, "剩余数据"), "存在未解析剩余数据"
    print("[OK] 并发抄读端设备真实报文回归测试通过")


def test_node_restart_downlink():
    """测试从节点重启下行业务"""
    parser = CSGNewGenParser()
    # 控制域 0x0012(LE: 12 00, 下行/命令帧) + 业务标识 0x04 + 版本 0x01 + 帧序号 0x0005
    header = bytes.fromhex("11 01 01 00 12 00 04 01 00 05".replace(" ", ""))
    # payload: 延时重启时间 0x0A + 保留 3字节
    payload = bytes.fromhex("0A 00 00 00".replace(" ", ""))
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    assert find_field(table, "延时重启时间"), "缺少延时重启时间字段"
    restart_row = find_field(table, "延时重启时间")
    assert restart_row[2] == "10", f"延时重启时间错误: {restart_row}"
    print("[OK] 从节点重启下行测试通过")


def test_node_info_query_downlink():
    """测试从节点信息查询下行业务"""
    parser = CSGNewGenParser()
    # 控制域 0x0012(LE: 12 00, 下行/命令帧) + 业务标识 0x05 + 版本 0x01 + 帧序号 0x0006
    header = bytes.fromhex("11 01 01 00 12 00 05 01 00 06".replace(" ", ""))
    # payload: 信息列表元素数量 0x03 + 信息元素ID 0x00,0x01,0x02
    payload = bytes.fromhex("03 00 01 02".replace(" ", ""))
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    count_row = find_field(table, "信息列表元素数量")
    assert count_row is not None, "缺少信息列表元素数量字段"
    assert count_row[2] == "3", f"信息列表元素数量错误: {count_row}"
    print("[OK] 从节点信息查询下行测试通过")


def test_test_frame_loopback():
    """测试回环测试帧"""
    parser = CSGNewGenParser()
    # 控制域 0x0012(LE: 12 00, 下行/命令帧) + 业务标识 0xF0 + 版本 0x01 + 帧序号 0x0007
    header = bytes.fromhex("11 01 01 00 12 00 F0 01 00 07".replace(" ", ""))
    # payload: 测试ID 0x00 + 保留 0x00 + 数据区长度 0x0001 + 测试数据区 0x01
    payload = bytes.fromhex("00 00 01 00 01".replace(" ", ""))
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    assert find_field(table, "测试ID"), "缺少测试ID字段"
    assert find_field(table, "数据区长度"), "缺少数据区长度字段"
    assert find_field(table, "测试数据区"), "缺少测试数据区字段"

    id_row = find_field(table, "测试ID")
    assert "回环测试" in id_row[3], f"测试ID说明错误: {id_row}"
    print("[OK] 回环测试帧测试通过")


def test_active_report_event():
    """测试事件主动上报"""
    parser = CSGNewGenParser()
    # 控制域 0x0013(LE: 13 00, 上行/主动上报) + 业务标识 0x00 + 版本 0x01 + 帧序号 0x0008
    header = bytes.fromhex("11 01 01 00 13 00 00 01 00 08".replace(" ", ""))
    # payload: 事件代码 0x0002(LE: 02 00, 从节点上线) + 数据长度 0x0004 + 数据 01 02 03 04
    payload = bytes.fromhex("02 00 04 00 01 02 03 04".replace(" ", ""))
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    assert find_field(table, "上报事件代码"), "缺少上报事件代码字段"
    assert find_field(table, "事件数据长度"), "缺少事件数据长度字段"
    assert find_field(table, "事件数据内容"), "缺少事件数据内容字段"

    event_row = find_field(table, "上报事件代码")
    assert "从节点上线" in event_row[3], f"事件代码说明错误: {event_row}"
    print("[OK] 事件主动上报测试通过")


def test_broadcast_command():
    """测试广播命令帧"""
    parser = CSGNewGenParser()
    # 控制域 0x0015(LE: 15 00, 下行/广播命令) + 业务标识 0x04(从节点重启) + 版本 0x01 + 帧序号 0x0009
    header = bytes.fromhex("11 01 01 00 15 00 04 01 00 09".replace(" ", ""))
    # payload: 广播源地址 6B + 广播目的地址 6B + 从节点重启下行payload(延时+保留3B)
    broadcast_header = bytes.fromhex("00 00 00 00 00 00 FF FF FF FF FF FF".replace(" ", ""))
    restart_payload = bytes.fromhex("0A 00 00 00".replace(" ", ""))
    payload = broadcast_header + restart_payload
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    assert find_field(table, "广播源地址"), "缺少广播源地址字段"
    assert find_field(table, "广播目的地址"), "缺少广播目的地址字段"
    assert find_field(table, "延时重启时间"), "缺少重启参数字段"
    print("[OK] 广播命令帧测试通过")


def test_station_to_station():
    """测试站点间通信"""
    parser = CSGNewGenParser()
    # 控制域 0x0011(LE: 11 00, 下行/数据传输) + 业务标识 0x03 + 版本 0x01 + 帧序号 0x0004
    header = bytes.fromhex("11 01 01 00 11 00 03 01 00 04".replace(" ", ""))
    payload = bytes.fromhex("00 00 00 00 00 00 11 22 33 44 55 66 0A 00 04 00 12 34 56 78".replace(" ", ""))
    frame_len = len(payload)
    frame = header + bytes([frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + payload
    table = parser.parse_to_table(frame)

    assert find_field(table, "数据转发长度"), "缺少数据转发长度字段"
    assert find_field(table, "数据转发内容"), "缺少数据转发内容字段"

    len_row = find_field(table, "数据转发长度")
    assert len_row[2] == "4", f"数据转发长度错误: {len_row}"
    print("[OK] 站点间通信测试通过")


def test_management_message():
    """测试管理消息 (MSDU类型 0x02)"""
    parser = CSGNewGenParser()
    # MAC 短头 12B: header_type=1, version=1, bit3=0 => byte0=0x03 + MSDU头 (VLAN=0, 类型=0x02) + 管理消息
    mac_header = bytes.fromhex("03 00 04 00 00 00 00 00 00 00 01 00".replace(" ", ""))
    msdu_header = bytes.fromhex("00 02".replace(" ", ""))
    # MMTYPE 2字节小端序: 0x0030 = 关联请求 (MMeAssocReq)
    # 管理消息头: 版本(1B) + MMTYPE(2B LE) + 保留(3B): 0x0030 = 关联请求
    mgmt_payload = bytes.fromhex("01 30 00 01 02 03".replace(" ", ""))
    msdu = msdu_header + mgmt_payload
    msdu_len = len(msdu)
    # 短头中 MSDU长度字段在 byte2-3, 小端序
    mac_header = bytearray(mac_header)
    mac_header[2] = msdu_len & 0xFF
    mac_header[3] = (msdu_len >> 8) & 0xFF
    # 追加 4 字节 CRC-32 占位
    frame = bytes(mac_header) + msdu + bytes.fromhex("DE AD BE EF".replace(" ", ""))
    table = parser.parse_to_table(frame)

    assert find_field(table, "MSDU类型"), "缺少MSDU类型字段"
    assert find_field(table, "管理消息类型(MMTYPE)"), "缺少管理消息类型字段"

    mgmt_row = find_field(table, "管理消息类型(MMTYPE)")
    assert "关联请求" in mgmt_row[3], f"管理消息类型说明错误: {mgmt_row}"
    print("[OK] 管理消息测试通过")



def _make_app_frame(service_id: int, payload: bytes, control: int = 0x0012) -> bytes:
    """构造应用层命令帧：端口0x11 + 标识0x0101 + 保留 + 控制域 + 业务标识 + 版本 + 序号 + 长度 + payload"""
    header = bytes([0x11, 0x01, 0x01, 0x00, control & 0xFF, (control >> 8) & 0xFF,
                    service_id, 0x01, 0x00, 0x01])
    return header + bytes([len(payload) & 0xFF, (len(payload) >> 8) & 0xFF]) + payload


def test_file_transfer_info():
    """测试文件传输-下发文件信息"""
    parser = CSGNewGenParser()
    payload = bytes.fromhex("00 00 00 00 02 00 99 99 99 99 99 99 44 33 22 11 00 00 01 00 10 00 05 00 DD CC BB AA".replace(" ", ""))
    frame = _make_app_frame(0x02, payload)
    table = parser.parse_to_table(frame)
    assert find_field(table, "文件传输信息ID"), "缺少文件传输信息ID"
    assert find_field(table, "文件性质"), "缺少文件性质"
    assert find_field(table, "文件大小"), "缺少文件大小"
    size_row = find_field(table, "文件大小")
    assert size_row[2] == "65536", f"文件大小错误: {size_row}"
    print("[OK] 文件传输-下发文件信息测试通过")


def test_query_terminal_search_results():
    """测试查询终端搜索结果上行业务"""
    parser = CSGNewGenParser()
    # 1 个终端: 6B BCD地址 00 00 00 00 00 01 + 规约类型 0x02 + 保留 0x00
    payload = bytes.fromhex("01 00 00 00 00 00 00 00 00 01 02 00".replace(" ", ""))
    frame = _make_app_frame(0x00, payload, control=0x8012)
    table = parser.parse_to_table(frame)
    assert find_field(table, "终端数量"), "缺少终端数量"
    count_row = find_field(table, "终端数量")
    assert count_row[2] == "1", f"终端数量错误: {count_row}"
    print("[OK] 查询终端搜索结果测试通过")


def test_address_mapping_downlink():
    """测试下发通信地址映射表列表下行业务"""
    parser = CSGNewGenParser()
    # 1 条映射: 通信地址 6B + 终端地址 12B
    payload = bytes.fromhex("01 00 00 00 11 22 33 44 55 66 00 11 22 33 44 55 66 77 88 99 AA BB CC".replace(" ", ""))
    frame = _make_app_frame(0x06, payload)
    table = parser.parse_to_table(frame)
    assert find_field(table, "映射终端数量"), "缺少映射终端数量"
    assert find_field(table, "映射1通信地址"), "缺少映射通信地址"
    print("[OK] 下发通信地址映射表列表测试通过")


def test_channel_info_downlink():
    """测试查询从节点信道信息下行业务"""
    parser = CSGNewGenParser()
    payload = bytes.fromhex("00 00 03".replace(" ", ""))
    frame = _make_app_frame(0x08, payload)
    table = parser.parse_to_table(frame)
    assert find_field(table, "周边节点起始序号"), "缺少周边节点起始序号"
    print("[OK] 查询从节点信道信息测试通过")


def test_module_run_params_downlink():
    """测试查询模块运行参数下行业务"""
    parser = CSGNewGenParser()
    # 起始序号 0 + 查询数量 2 + 2 个元素 ID 0x01 0x02
    payload = bytes.fromhex("00 00 02 02 01 02".replace(" ", ""))
    frame = _make_app_frame(0x09, payload)
    table = parser.parse_to_table(frame)
    assert find_field(table, "信息列表元素数量"), "缺少信息列表元素数量"
    print("[OK] 查询模块运行参数测试通过")


def test_district_phase_downlink():
    """测试台区户变关系/相位识别报文头解析"""
    parser = CSGNewGenParser()
    # 报文头: header_len=12(0x0C), phase=0; 3B保留; MAC 00:00:11:22:33:44; feature=1; collect=1
    header_bytes = bytes([0x0C, 0x00, 0x00, 0x00]) + bytes.fromhex("00 00 11 22 33 44") + bytes([0x01, 0x01])
    # DATA: 起始NTB 4B + 周期1 + 数量1 + 序列号1 + 保留1
    payload = header_bytes + bytes.fromhex("00 00 00 00 0A 05 01 00")
    frame = _make_app_frame(0x10, payload)
    table = parser.parse_to_table(frame)
    assert find_field(table, "MAC地址"), "缺少MAC地址"
    assert find_field(table, "特征类型"), "缺少特征类型"
    assert find_field(table, "采集类型"), "缺少采集类型"
    print("[OK] 台区户变关系/相位识别测试通过")


def test_net_frame_real():
    """真实网间协调帧(NET, 定界符类型=3): 可变区域按表41解析"""
    parser = CSGNewGenParser()
    frame = bytes.fromhex("7B 00 00 00 00 00 00 00 00 00 81 01 10 B6 51 55".replace(" ", ""))
    table = parser.parse_to_table(frame)
    # 定界符类型=3 网间协调帧
    dt_row = find_field(table, "定界符类型")
    assert dt_row and dt_row[2] == "3", f"定界符类型错误: {dt_row}"
    assert "网间协调帧" in dt_row[3]
    # 可变区域字段（表41）
    assert find_field(table, "邻居网络比特图1")
    assert find_field(table, "本网络无线信道编号")
    assert find_field(table, "邻居网络比特图2")
    assert find_field(table, "持续时间")
    assert find_field(table, "邻居网络比特图3")
    assert find_field(table, "带宽结束标志位")
    assert find_field(table, "本网络无线option")
    assert find_field(table, "邻居网络比特图4")
    assert find_field(table, "带宽结束偏移")
    assert find_field(table, "带宽开始偏移")
    # 带宽开始偏移 = 0x0181(小端) = 385 * 4ms = 1540ms
    bw_start = find_field(table, "带宽开始偏移")
    assert "1540ms" in bw_start[2], f"带宽开始偏移错误: {bw_start[2]}"
    # 短网络标识高位 + 完整SNID=0x07
    snid_high = find_field(table, "短网络标识高位")
    assert snid_high and "0x07" in snid_high[3], f"SNID高位错误: {snid_high}"
    # 网间协调帧无物理块/MSDU
    assert not find_field(table, "MSDU负载"), "网间协调帧不应有MSDU负载"
    print("[OK] 网间协调帧(NET)表41可变区域解析通过")


def test_net_frame_nonzero_fields():
    """构造非零字段网间协调帧: 验证比特图/信道/偏移位解析"""
    parser = CSGNewGenParser()
    # byte0=0x7B(dt=3, SNID低位=7)
    # 比特图1=0x1234 -> 34 12
    # 信道编号=0x2A -> byte3
    # 比特图2=10bit=0x1F4 -> byte4=0xF4 byte5低2位=0x01
    # 持续时间=0x1234: 低6位=0x34(byte5 bit2-7), bit6-13=0x48(byte6) -> byte5=0x34<<2|0x01=0xD1
    # byte7: 比特图3=1, 带宽结束=0, option=1, 比特图4=0xA -> 0b1010_01_0_1=0xA5
    # 带宽结束偏移=0x0050 -> 50 00; 带宽开始偏移=0x0200 -> 00 02
    # byte12: SNID高位=1 | 版本=1 -> 0x11
    body = bytes.fromhex("7B 34 12 2A F4 D1 48 A5 50 00 00 02 11".replace(" ", ""))
    fcs = parser._crc24(body)
    frame = body + fcs.to_bytes(3, "little")
    table = parser.parse_to_table(frame)
    assert find_field(table, "邻居网络比特图1")[2] == "0x1234"
    assert find_field(table, "本网络无线信道编号")[2] == "42"
    assert find_field(table, "邻居网络比特图2")[2] == "0x1F4"
    assert find_field(table, "持续时间")[2] == "4660 × 40ms (186400ms)"
    assert find_field(table, "邻居网络比特图3")[2] == "1"
    assert find_field(table, "带宽结束标志位")[2] == "0"
    assert find_field(table, "本网络无线option")[2] == "1"
    assert find_field(table, "邻居网络比特图4")[2] == "0b1010"
    assert "320ms" in find_field(table, "带宽结束偏移")[2]
    assert "2048ms" in find_field(table, "带宽开始偏移")[2]
    snid_high = find_field(table, "短网络标识高位")
    assert "0x17" in snid_high[3], f"完整SNID应=0x17(高1+低7), 实际: {snid_high}"
    print("[OK] 网间协调帧(NET)非零字段位解析通过")


def test_aggregated_frame_app_layer():
    """聚合帧(级联块)应用层解析: 2个级联块各含1条应用层报文(转发DLT645)"""
    parser = CSGNewGenParser()
    frame = bytes.fromhex(
        "19 02 30 00 03 00 00 41 25 05 20 5B 10 AD 49 E7 00 00 01 00 "
        "3E 10 03 00 2E 00 03 10 00 41 11 08 24 00 03 01 11 01 01 00 "
        "01 60 00 01 09 00 20 00 64 01 98 90 00 00 02 11 00 68 21 19 "
        "12 00 10 00 68 02 11 00 68 21 19 68 11 04 33 33 34 33 67 16 "
        "16 F7 9F 47 3E 20 03 00 2E 00 03 10 00 41 11 08 25 00 03 01 "
        "11 01 01 00 01 60 00 01 09 00 20 00 64 01 98 90 00 00 02 11 "
        "00 68 21 19 12 00 10 00 68 02 11 00 68 21 19 68 11 04 33 33 "
        "34 33 67 16 16 F7 9F 47 00 36 91 E5".replace(" ", ""))
    table = parser.parse_to_table(frame, parse_level="auto")
    # 聚合标志=1
    agg = find_field(table, "聚合标志")
    assert agg and agg[2] == "1", f"应为聚合帧, 实际: {agg}"
    # 2个级联头
    cascade = find_all_fields(table, "级联头")
    assert len(cascade) == 2, f"应有2个级联头, 实际: {len(cascade)}"
    # 每个级联块解出1条应用层报文（端口0x11 + 业务标识0 + 转发DLT645）
    ports = find_all_fields(table, "报文端口号")
    assert len(ports) == 2, f"应有2条应用层报文, 实际: {len(ports)}"
    for port in ports:
        assert port[2] == "17", f"端口应为0x11, 实际: {port}"
    sids = find_all_fields(table, "业务标识")
    assert len(sids) == 2 and all(s[2] == "0" for s in sids)
    # 转发数据内容 = DLT645 抄表帧
    fwd = find_all_fields(table, "转发数据内容")
    assert len(fwd) == 2, f"应有2条转发数据, 实际: {len(fwd)}"
    assert fwd[0][1].startswith("68 02 11 00 68 21 19 68 11 04 33 33 34 33 67 16"), f"转发数据错误: {fwd[0][1]}"
    # 无残留伪MSDU负载(整帧误判)
    msdu_rows = [r for r in table if r[0] == "MSDU负载" and "未识别" in r[3]]
    assert not msdu_rows, f"不应有未识别MSDU负载残留: {msdu_rows}"
    print("[OK] 聚合帧级联块应用层解析通过")


def test_compact_beacon_real():
    """精简信标载荷解析（表73）：用户实测帧字段

    载荷头D2(中央+精简标志) + 组网序列号46 + CCO MAC 00:00:90:98:01:63
    + 信标周期计数20(=FC) + 条目数1 + 0x0E条目(TEI=1/角色CCO) + BPCS
    此前按标准信标表51解析导致 MAC 被误读为 SNID/信道字段、0x0E 条目错位成"保留98"。
    """
    parser = CSGNewGenParser()
    payload = (bytes.fromhex("D246000090980163")
               + (20).to_bytes(4, 'little')
               + bytes.fromhex("010E13")            # 条目数1 + 0x0E + 长度19
               + bytes.fromhex("01000004000000000000000000000000000000")  # TEI=1 角色4=CCO 层级0
               + b"\x00\x39\x1d\x89")                # BPCS
    table = parser._parse_beacon_payload(payload, 16)
    rows = {r[0].strip(): r for r in table}
    assert rows["信标载荷头(精简)"][3].startswith("信标类型:2"), rows.get("信标载荷头(精简)")
    assert "精简:1" in rows["信标载荷头(精简)"][3]
    assert rows["组网序列号"][2] == "70"
    assert rows["CCO MAC地址"][2] == "00:00:90:98:01:63", rows.get("CCO MAC地址")
    assert rows["信标周期计数"][2] == "20", rows.get("信标周期计数")
    # 条目深度解析（表74）
    assert rows["条目类型"][1] == "0E" and "精简信标站点信息及时隙条目" in rows["条目类型"][3], rows.get("条目类型")
    assert rows["条目长度"][2] == "19"
    assert rows["TEI"][2] == "1", rows.get("TEI")
    assert "CCO" in rows["角色/层级数"][2], rows.get("角色/层级数")
    print("[OK] 精简信标载荷表73解析通过")

def test_std_beacon_proxy_role_entry_real():
    """标准信标载荷（表51）用户实测帧：6 条条目，含 0x10 代理角色条目 + 0x02 时隙分配条目

    实帧 112 字节（载荷头 6B + 管理信息 106B；输入是裁剪后的 PB 载荷，未含校验序列）：
    1) 0x10 代理角色条目**实机按 1 字节长度字段发送**（表59/表72 写的是 16 比特）——
       按 2 字节读得到 0x6004=24580 字节的荒谬长度，把其后所有字节（含 0x02 条目）吞成
       「代理角色条目 28字节 / 代理站点数 14」，即用户报的条目长度解析缺陷；
    2) 末条 0x02 时隙分配条目长度 31 = 固定 27 + 1×CSMA时隙信息(4B)（CSMA相线个数=1），
       条目正好结束在载荷末尾 ⇒ 末 4 字节 30 75 00 00 属该条目的 CSMA时隙信息，
       **不是**帧载荷校验序列（旧逻辑无条件吞末 4 字节 ⇒ 该条目少 4 字节、且多出伪 CRC 行）。
    """
    parser = CSGNewGenParser()
    payload = bytes.fromhex(
        "4a0264103300060116000140016666666666660000640000000000000006223c"
        "000000150000000000000000000000000000000000000000006666666666660c"
        "040a040b0a85995932823dc73710046000021f0000000100fa00320000000000"
        "c7ba523c307500003000000030750000")
    assert len(payload) == 112
    table = parser._parse_beacon_payload(payload, 16)

    # 6 条条目全部解析出来（旧实现第 6 条被 0x10 的超长声明吞掉）
    types = find_all_fields(table, "条目类型")
    assert [r[1] for r in types] == ["01", "06", "0C", "0B", "10", "02"], [r[1] for r in types]

    # 0x10 代理角色条目：长度字段实发 1 字节（0x04）⇒ 1 个代理站点、TEI=96
    lens = find_all_fields(table, "条目长度")
    assert [r[2] for r in lens] == ["22", "34", "4", "10", "4", "31"], [r[2] for r in lens]
    assert lens[4][1] == "04" and "长度字段实发 1 字节" in lens[4][3], lens[4]
    proxy = find_field(table, "代理角色条目")
    assert proxy[2] == "2字节" and "代理站点数: 1" in proxy[3], proxy
    proxies = find_all_fields(table, "代理[")
    assert len(proxies) == 1 and proxies[0][2] == "96", proxies
    assert (proxies[0][4], proxies[0][5]) == (95, 96), proxies[0]
    # 1 个代理站点为奇数 ⇒ 内容 2 字节 = 12bit TEI + 4bit 尾保留位（表72）
    tail = find_field(table, "条目尾保留位")
    assert tail is not None and tail[2] == "4bit" and "保留" in tail[3], tail

    # 末条 0x02 时隙分配条目：内容完整 28 字节，末 4 字节是 CSMA时隙信息
    assert find_field(table, "CSMA相线个数")[2] == "1", find_field(table, "CSMA相线个数")
    assert find_field(table, "信标周期长度")[2] == "30000x100us", find_field(table, "信标周期长度")
    rf = find_field(table, "RF信标时隙长度")
    assert rf[2] == "48ms" and (rf[4], rf[5]) == (120, 121), rf
    var = find_field(table, "可变长时隙信息")
    assert var[2] == "4字节" and "= 4字节" in var[3], var

    # 输入载荷未含校验序列 ⇒ 明确提示，且不得把末 4 字节当成 CRC
    crc = find_field(table, "帧载荷校验序列")
    assert crc is not None and crc[2] == "未包含", crc
    assert [r for r in table if r[0].strip() == "帧载荷校验序列" and r[1] != "-"] == [], crc

    # 同一载荷后面真接 4 字节校验序列 ⇒ 仍认作帧载荷校验序列，条目解析结果不变
    table2 = parser._parse_beacon_payload(payload + bytes.fromhex("11223344"), 16)
    assert [r[2] for r in find_all_fields(table2, "条目长度")] == ["22", "34", "4", "10", "4", "31"]
    crc2 = [r for r in table2 if r[0].strip() == "帧载荷校验序列"]
    assert crc2 and crc2[0][2] == "0x44332211", crc2
    print("[OK] 标准信标 0x10 代理角色条目长度字段 / 末条裁剪解析通过")


def test_std_beacon_proxy_role_entry_12bit_real():
    """标准信标载荷（表51）用户实测帧：0x10 代理角色条目按**连续 12 比特位流**解包（表72）

    实帧 114 字节（载荷头 6B + 管理信息 108B；输入是裁剪后的 PB 载荷，未含校验序列）：
    条目4 = ``10 06 00 01 70 00`` —— 条目长度字段 2 字节（表59：0x10 的长度字段大小 = 2），
    内容 3 字节 = 24 比特 = **2 个** 12 比特 TEI：
      代理节点1TEI = 内容字节0 bits0-7(0x01) + 内容字节1 bits0-3(0x0) = 1
      代理节点2TEI = 内容字节1 bits4-7(0x7) + 内容字节2 bits0-7(0x00) = 7
    旧实现按「每 2 字节一个 TEI」切（且用 ``ln//2`` 当站点数）⇒ 只输出 1 个站点、TEI=1，
    第 2 个 TEI（内容字节1 高4位 + 内容字节2）被整段丢掉，即用户报的「代理角色 TEI 解析不对」。
    """
    parser = CSGNewGenParser()
    parts = [
        "4A 02 62 10 33 00",                                  # 载荷头 6B
        "06",                                                  # 信标条目数 = 6
        "01 16 00 01 40 01 66 66 66 66 66 66 00 00 64 00 00 00 00 00 00 00",   # 条目0 站点能力条目 22B
        "06 22 3C 00 00 00 0D 00 00 00" + " 00" * 18 + " 66 66 66 66 66 66",   # 条目1 路由参数条目 34B
        "0C 04 0A 04",                                          # 条目2 无线路由参数条目 4B
        "0B 0A 0F 77 5A 32 94 AC EB 55",                        # 条目3 万年历同步条目 10B
        "10 06 00 01 70 00",                                    # 条目4 代理角色条目 6B
        "02 1F 00 00 00 01 00 C8 00 32 00 00 00 00 00 99 2C 77 5A 30 75 00 00"
        " 26 00 00 00 30 75 00 00",                             # 条目5 时隙分配条目 31B
    ]
    payload = bytes.fromhex(" ".join(parts))
    assert len(payload) == 114, len(payload)
    table = parser._parse_beacon_payload(payload, 16)

    # 条目链未被 0x10 条目打乱：仍是 6 条
    types = find_all_fields(table, "条目类型")
    assert [r[1] for r in types] == ["01", "06", "0C", "0B", "10", "02"], [r[1] for r in types]
    lens = find_all_fields(table, "条目长度")
    assert [r[2] for r in lens] == ["22", "34", "4", "10", "6", "31"], [r[2] for r in lens]
    assert lens[4][1] == "06 00" and "长度字段实发" not in lens[4][3], lens[4]

    # 0x10：3 字节内容 ⇒ 2 个代理站点，TEI = 1 / 7（12 比特连续位流，跨半字节）
    proxy = find_field(table, "代理角色条目")
    assert proxy[2] == "3字节" and "代理站点数: 2" in proxy[3], proxy
    proxies = find_all_fields(table, "代理[")
    assert [r[2] for r in proxies] == ["1", "7"], proxies
    assert [r[0].strip() for r in proxies] == ["代理[0]TEI", "代理[1]TEI"], proxies
    assert (proxies[0][4], proxies[0][5]) == (96, 97), proxies[0]
    assert (proxies[1][4], proxies[1][5]) == (97, 98), proxies[1]
    # 偶数个代理站点 ⇒ 表72 无末尾保留位
    assert find_field(table, "条目尾保留位") is None, find_field(table, "条目尾保留位")

    # 既有的 1 个代理站点帧（内容 60 00 = 12bit TEI + 4bit 保留）不受影响
    print("[OK] 标准信标 0x10 代理角色条目 12bit 连续位流解析通过")


def test_isac_sof_bitloading_pb_size():
    """ISAC-PLC SOF 数据帧: Bitloading标识=1 时字节6低2bit为物理块大小码(表23)。
    实帧: 29 01 20 00 04 5B 01 00 F0 00 00 00 20 6A 8F 56
    字节6(FC可变区域相对)=0x01: Bitloading=1, PB大小码=0 -> 136字节。
    旧实现误用表13 ROBO映射(0->520)且两字段合并显示。
    """
    parser = CSGNewGenParser()
    frame = bytes.fromhex("29012000045B0100F0000000206A8F56")
    table = parser.parse_to_table(frame)

    bl = find_field(table, "Bitloading标识")
    assert bl is not None, "缺少 Bitloading标识 字段"
    assert bl[2] == "1" and "使用Bitloading" in bl[3], f"Bitloading标识错误: {bl}"

    pb = find_field(table, "物理块大小码")
    assert pb is not None, "缺少 物理块大小码 字段"
    assert pb[1] == "0x0" and "136字节" in pb[3], f"物理块大小码错误: {pb}"

    # 不应再出现旧的合并字段名
    assert not find_field(table, "Bitloading/PB大小"), "旧合并字段名仍存在"
    # PB 大小已存入 _pb_size 供后续 PB 解析使用(不再走 TMI/ROBO 表)
    assert getattr(parser, "_pb_size", None) == 136, "_pb_size 未按 Bitloading 码设置"
    print("[OK] ISAC SOF Bitloading物理块大小解析通过")


def test_isac_sof_tmi_mode():
    """ISAC SOF 数据帧: Bitloading标识=0 时字节6为TMI编号(表13 ROBO模式)。
    构造字节6=0x00 -> TMI=0 (PB=520)。
    """
    parser = CSGNewGenParser()
    frame = bytearray.fromhex("29012000045B0100F0000000206A8F56")
    frame[6] = 0x00  # 字节6: bit0=0(TMI模式), bit1-5=TMI编号=0
    # 帧长域等其它字段不变; FCS不校验FC表23字段本身
    table = parser.parse_to_table(bytes(frame))

    bl = find_field(table, "Bitloading标识")
    assert bl is not None and bl[2] == "0" and "使用TMI" in bl[3], f"Bitloading标识错误: {bl}"
    tmi = find_field(table, "TMI编号")
    assert tmi is not None and tmi[1] == "0x00" and "520" in tmi[3], f"TMI编号错误: {tmi}"
    assert not find_field(table, "物理块大小码"), "TMI模式不应出现物理块大小码字段"
    print("[OK] ISAC SOF TMI模式解析通过")


def main():
    print("=" * 50)
    print("新一代载波协议解析器测试")
    print("=" * 50)
    test_confirm()
    test_deny()
    test_data_transparent_to_device_downlink()
    test_data_transparent_to_module_uplink()
    test_concurrent_meter_read_downlink()
    test_concurrent_meter_read_uplink()
    test_concurrent_meter_read_real_frame()
    test_node_restart_downlink()
    test_node_info_query_downlink()
    test_test_frame_loopback()
    test_active_report_event()
    test_broadcast_command()
    test_management_message()
    test_file_transfer_info()
    test_query_terminal_search_results()
    test_address_mapping_downlink()
    test_channel_info_downlink()
    test_module_run_params_downlink()
    test_district_phase_downlink()
    test_station_to_station()
    test_net_frame_real()
    test_aggregated_frame_app_layer()
    test_compact_beacon_real()
    test_std_beacon_proxy_role_entry_real()
    test_std_beacon_proxy_role_entry_12bit_real()
    test_isac_sof_bitloading_pb_size()
    test_isac_sof_tmi_mode()
    print("=" * 50)
    print("[OK] 全部测试通过")


if __name__ == '__main__':
    main()
