"""DL/T 698.45 APDU 数据内容业务解码测试

覆盖：
- 电能量数组（kWh 换算，费率展开）
- 分相电压/电流（A/B/C 相 + 单位）
- 最大需量数组（值 @ 时间）
- 单数值（数据变量）
- APDU 解析器接入（GET-Response / SET-Request / REPORT-Notification）
- 链路层表格展示（parse_to_table 含 数据业务 行）
"""

import _path_setup  # noqa: E402


def _enc_array(vals, val_tag=0x05, val_size=4):
    """构造 A-XDR array：tag=0x01 + 长度 + 元素"""
    body = b""
    for v in vals:
        body += bytes([val_tag]) + v.to_bytes(val_size, "little")
    return bytes([0x01, len(body)]) + body


def _enc_structure(*items):
    """构造 A-XDR structure：tag=0x02 + 长度 + 成员"""
    body = b"".join(items)
    return bytes([0x02, len(body)]) + body


def _enc_double_long(v):
    return bytes([0x05]) + v.to_bytes(4, "little")


def _enc_date_time_s(year=2024, month=5, day=1, hour=12, minute=0, second=0):
    """date_time_s：octet-string tag=0x0C + 7字节（年2B大端 月 日 时 分 秒）"""
    body = year.to_bytes(2, "big") + bytes([month, day, hour, minute, second])
    return bytes([0x0C, len(body)]) + body


def test_energy_array_decode():
    """电能量数组：OAD=0x0000 属性2 → kWh 换算 + 费率展开"""
    from dl_t698_45_data_decode import decode_oad_data

    data = _enc_array([1234567, 5000])
    biz = decode_oad_data(0x0000, 2, {"类型": "array", "解析值": data})
    # decode_oad_data 期望 AXDRCoder.decode 结果；此处直接传 array dict
    assert biz is None or isinstance(biz, dict)


def test_energy_array_via_axdr():
    """电能量数组（走 AXDRCoder 全链路）"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser
    from dl_t698_45_data_decode import decode_oad_data

    parser = DLT69845APDUParser()
    data = _enc_array([1234567, 5000])
    apdu = bytes([0x85, 0x01, 0x00]) + bytes.fromhex("0000") + bytes([0x02, 0x00]) + bytes([0x00]) + data
    result = parser.parse(apdu)
    assert result["APDU类型"] == "GET-Response"
    assert result["子类型"] == "GetResponseNormal"
    biz = result.get("数据业务")
    assert biz, "应产生数据业务解码"
    assert biz["总"] == "1234.567 kWh", biz
    assert biz["费率1"] == "5 kWh", biz
    # 原始 A-XDR 结果保留
    assert result["数据"]["类型"] == "array"
    print("test_energy_array_via_axdr PASSED")


def test_phase_array_voltage():
    """分相电压：OAD=0x2000 属性2 → A/B/C 相 V"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    data = _enc_array([2205, 2203, 2201])
    apdu = bytes([0x85, 0x01, 0x00]) + bytes.fromhex("2000") + bytes([0x02, 0x00]) + bytes([0x00]) + data
    result = parser.parse(apdu)
    biz = result.get("数据业务")
    assert biz["A相"] == "220.5 V", biz
    assert biz["B相"] == "220.3 V", biz
    assert biz["C相"] == "220.1 V", biz
    print("test_phase_array_voltage PASSED")


def test_phase_array_current():
    """分相电流：OAD=0x2001 属性2 → A 相 A"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    data = _enc_array([5200, 5100, 5300])
    apdu = bytes([0x85, 0x01, 0x00]) + bytes.fromhex("2001") + bytes([0x02, 0x00]) + bytes([0x00]) + data
    result = parser.parse(apdu)
    biz = result.get("数据业务")
    assert biz["A相"] == "5.2 A", biz
    assert biz["C相"] == "5.3 A", biz
    print("test_phase_array_current PASSED")


def test_demand_array_with_time():
    """最大需量：OAD=0x1010 属性2 → 值 @ 发生时间"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    item = _enc_structure(_enc_double_long(12340), _enc_date_time_s())
    data = bytes([0x01, len(item)]) + item
    apdu = bytes([0x85, 0x01, 0x00]) + bytes.fromhex("1010") + bytes([0x02, 0x00]) + bytes([0x00]) + data
    result = parser.parse(apdu)
    biz = result.get("数据业务")
    assert "总" in biz, biz
    assert "12.34 W" in biz["总"], biz
    assert "2024-05-01 12:00:00" in biz["总"], biz
    print("test_demand_array_with_time PASSED")


def test_get_response_normal_list():
    """GET-Response NormalList：逐项业务解码"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    d1 = _enc_array([2205, 2203, 2201])
    d2 = _enc_array([1234567])
    # GetResponseNormalList: PIID-ACD + count + (OAD + 00 + Data)*
    apdu = (bytes([0x85, 0x02, 0x00, 0x02])
            + bytes.fromhex("2000") + bytes([0x02, 0x00]) + bytes([0x00]) + d1
            + bytes.fromhex("0000") + bytes([0x02, 0x00]) + bytes([0x00]) + d2)
    result = parser.parse(apdu)
    assert result["子类型"] == "GetResponseNormalList"
    items = result["列表"]
    assert len(items) == 2
    assert items[0]["数据业务"]["A相"] == "220.5 V", items[0]
    assert items[1]["数据业务"]["总"] == "1234.567 kWh", items[1]
    print("test_get_response_normal_list PASSED")


def test_set_request_business():
    """SET-Request：下行设置参数同样给出业务值"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    # 设置 A/B/C 相电压 220.5/220.3/220.1 V → 分相数组 [2205, 2203, 2201]
    data = _enc_array([2205, 2203, 2201])
    apdu = bytes([0x06, 0x01, 0x00]) + bytes.fromhex("2000") + bytes([0x02, 0x00]) + data
    result = parser.parse(apdu)
    assert result["APDU类型"] == "SET-Request"
    assert result["子类型"] == "SetRequestNormal"
    assert result["数据业务"]["A相"] == "220.5 V", result.get("数据业务")
    print("test_set_request_business PASSED")


def test_report_notification_business():
    """REPORT-Notification Normal：OAD + 数据业务"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    data = _enc_array([1234567, 5000])
    apdu = bytes([0x88, 0x01, 0x00]) + bytes.fromhex("0000") + bytes([0x02, 0x00]) + data
    result = parser.parse(apdu)
    assert result["APDU类型"] == "REPORT-Notification"
    assert result["子类型"] == "ReportNotificationNormal"
    assert result["OAD"]["解析值"]["OI"] == "0x0000", result.get("OAD")
    assert result["数据业务"]["总"] == "1234.567 kWh", result.get("数据业务")
    print("test_report_notification_business PASSED")


def test_unknown_oi_no_template():
    """无模板 OI：不产生数据业务，不破坏原始解析"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    data = _enc_double_long(1234)
    apdu = bytes([0x85, 0x01, 0x00]) + bytes.fromhex("F000") + bytes([0x02, 0x00]) + bytes([0x00]) + data
    result = parser.parse(apdu)
    assert "数据业务" not in result
    assert result["数据"]["类型"] == "double-long"
    print("test_unknown_oi_no_template PASSED")


def test_parse_to_table_shows_business():
    """链路层表格：含 数据业务 行"""
    from dl_t698_45_frame_gen import DLT69845FrameGenerator
    from dl_t698_45_parser import DLT69845Parser

    gen = DLT69845FrameGenerator()
    parser = DLT69845Parser()
    data = _enc_array([1234567, 5000])
    apdu = bytes([0x85, 0x01, 0x00]) + bytes.fromhex("0000") + bytes([0x02, 0x00]) + bytes([0x00]) + data
    frame = gen._assemble_frame(sa=bytes([0x01, 0x07, 0x08]), ca=0x09, control=0x43, apdu=apdu)
    table = parser.parse_to_table(frame)
    rows = {row[0].strip(): row for row in table}
    assert "数据业务" in rows, [r[0] for r in table]
    assert rows["总"][2] == "1234.567 kWh", rows["总"]
    assert rows["费率1"][2] == "5 kWh", rows["费率1"]
    print("test_parse_to_table_shows_business PASSED")


if __name__ == "__main__":
    test_energy_array_decode()
    test_energy_array_via_axdr()
    test_phase_array_voltage()
    test_phase_array_current()
    test_demand_array_with_time()
    test_get_response_normal_list()
    test_set_request_business()
    test_report_notification_business()
    test_unknown_oi_no_template()
    test_parse_to_table_shows_business()
    print("ALL 698.45 数据解码测试 PASSED")
