"""
新一代载波协议 (通感一体化) 解析器测试
直接运行: python test_csg_new_gen.py
"""
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
    test_net_frame_nonzero_fields()
    print("=" * 50)
    print("[OK] 全部测试通过")


if __name__ == '__main__':
    main()
