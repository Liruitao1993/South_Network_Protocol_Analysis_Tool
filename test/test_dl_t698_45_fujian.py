"""DL/T 698.45 福建简化698（choice=0x02 List 结构）解析测试

依据：协议文档/8.698.45协议/【CCO和STA要求】本地通信模块扩展协议V3.42-20260514.md A.2
覆盖：SET/ACTION 的 Request/Response List 分支、REPORT count 结构、EB 数据标识名称、
      EB 数据内容字段解码（大端 uint，645 减33逆序规则）、用户实测帧
"""

import _path_setup  # noqa: E402


def test_action_request_list_user_frame():
    """用户实测帧：ACTION-Request List，OMD=EB030307（过零NTB值）"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    apdu = bytes.fromhex("07020001EB03030709081C07E80B1B0A200000")
    r = parser.parse(apdu)
    assert r["APDU类型"] == "ACTION-Request"
    assert r["子类型"] == "ActionRequestNormalList"
    assert r["子类型码"] == "0x02"
    assert r["PIID"]["服务序号"] == 0
    items = r["列表"]
    assert len(items) == 1
    omd = items[0]["OMD"]
    assert omd["原始值"] == "EB030307"
    assert "过零" in omd["语义说明"], omd.get("语义说明")
    # 参数 octet-string 保留
    assert items[0]["参数"]["类型"] == "octet-string"
    assert items[0]["参数"]["原始值"] == "1C07E80B1B0A2000"
    # 无字段 schema → 原始数据兜底
    assert items[0]["数据业务"]["原始数据"] == "1C07E80B1B0A2000"
    print("test_action_request_list_user_frame PASSED")


def test_set_request_list_doc_example():
    """文档示例：SET 配置 EB030110 台区识别任务启动（方法+时长）"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    apdu = bytes.fromhex("06020001EB030110090300000500")
    r = parser.parse(apdu)
    assert r["APDU类型"] == "SET-Request"
    assert r["子类型"] == "SetRequestNormalList"
    item = r["列表"][0]
    assert item["OAD"]["原始值"] == "EB030110"
    assert "台区识别" in item["OAD"]["语义说明"]
    # 数据 000005: 方法0=自动(enum), 时长 00 05 大端=5分钟
    biz = item["数据业务"]
    assert biz["台区识别方法"] == "自动", biz
    assert biz["识别时长(分钟)"] == 5, biz
    print("test_set_request_list_doc_example PASSED")


def test_action_request_list_doc_example():
    """文档示例：ACTION 读取 EB030110（无参数）"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    apdu = bytes.fromhex("07020001EB0301100000")
    r = parser.parse(apdu)
    assert r["子类型"] == "ActionRequestNormalList"
    item = r["列表"][0]
    assert item["OMD"]["原始值"] == "EB030110"
    assert "台区识别" in item["OMD"]["语义说明"]
    assert item["参数"]["类型"] == "null"
    print("test_action_request_list_doc_example PASSED")


def test_action_response_list_doc_example():
    """文档示例：ACTION 响应 EB030110（DAR=成功 + 响应数据方法1+时长5）"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    apdu = bytes.fromhex("87020001EB0301100009030100050000")
    r = parser.parse(apdu)
    assert r["子类型"] == "ActionResponseNormalList"
    item = r["列表"][0]
    assert item["OMD"]["原始值"] == "EB030110"
    assert item["结果"]["DAR说明"] == "成功", item["结果"]
    biz = item["数据业务"]
    assert biz["台区识别方法"] == "工频电压特征", biz
    assert biz["识别时长(分钟)"] == 5, biz
    print("test_action_response_list_doc_example PASSED")


def test_set_response_list_doc_example():
    """文档示例：SET 确认 / 否认 EB030110"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    r = parser.parse(bytes.fromhex("86020001EB030110000000"))
    assert r["子类型"] == "SetResponseNormalList"
    assert r["列表"][0]["OAD"]["原始值"] == "EB030110"
    assert r["列表"][0]["结果"]["DAR说明"] == "成功", r["列表"][0]["结果"]
    r2 = parser.parse(bytes.fromhex("86020001EB030110FF0000"))
    assert r2["列表"][0]["结果"]["DAR说明"] != "成功"
    print("test_set_response_list_doc_example PASSED")


def test_report_notification_doc_example():
    """文档示例：REPORT 上报 EB030002 停上电事件（带 count + 数据个数01）"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    apdu = bytes.fromhex("88010001EB03000201090800011122334455660000")
    r = parser.parse(apdu)
    assert r["子类型"] == "ReportNotificationNormal"
    assert len(r["OAD列表"]) == 1
    assert r["OAD列表"][0]["原始值"] == "EB030002"
    assert "停上电事件" in r["OAD列表"][0]["语义说明"]
    assert r["数据个数"] == 1
    assert r["数据"]["类型"] == "octet-string"
    # EB030002 字段解码: 停上电类型0=停电 + 数量1 + 地址列表
    biz = r["数据业务"]
    assert biz["停上电类型"] == "模块停电", biz
    assert biz["本次上报数量"] == 1, biz
    assert biz["模块地址列表"][0]["模块地址"] == "112233445566", biz
    print("test_report_notification_doc_example PASSED")


def test_report_response_doc_example():
    """文档示例：REPORT 确认 EB030002（count + OAD + 结果）"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    apdu = bytes.fromhex("08010001EB03000200")
    r = parser.parse(apdu)
    assert r["子类型"] == "ReportResponseList"
    assert r["OAD"]["原始值"] == "EB030002"
    assert r["结果"]["DAR说明"] == "成功", r["结果"]
    print("test_report_response_doc_example PASSED")


def test_set_request_multiple_oads():
    """SET-Request List 多对象：count=2 逐项解析"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    # count=2: EB030110(方法0+时长5) + EB030307(无schema, 原始数据)
    apdu = (bytes([0x06, 0x02, 0x00, 0x02])
            + bytes.fromhex("EB030110") + bytes([0x09, 0x03]) + bytes.fromhex("000005")
            + bytes.fromhex("EB030307") + bytes([0x09, 0x02]) + bytes.fromhex("0102"))
    r = parser.parse(apdu)
    assert r["子类型"] == "SetRequestNormalList"
    items = r["列表"]
    assert len(items) == 2
    assert items[0]["OAD"]["原始值"] == "EB030110"
    assert items[0]["数据业务"]["识别时长(分钟)"] == 5
    assert items[1]["OAD"]["原始值"] == "EB030307"
    assert items[1]["数据业务"]["原始数据"] == "0102"
    print("test_set_request_multiple_oads PASSED")


def test_eb_uint_big_endian():
    """EB 数据内容多字节 uint 大端（645 减33逆序规则）"""
    from gdw_eb_di_fields import encode_eb_di_data
    from dl_t698_45_apdu_parser import DLT69845APDUParser

    parser = DLT69845APDUParser()
    # 编码器: 方法0 + 时长5 → 00 00 05（大端）
    b = encode_eb_di_data("EB030110", {"台区识别方法": 0, "识别时长(分钟)": 5})
    assert b.hex() == "000005", b.hex()
    # 解码器回读一致
    apdu = bytes([0x06, 0x02, 0x00, 0x01]) + bytes.fromhex("EB030110") + bytes([0x09, 0x03]) + b
    r = parser.parse(apdu)
    assert r["列表"][0]["数据业务"]["识别时长(分钟)"] == 5
    print("test_eb_uint_big_endian PASSED")


if __name__ == "__main__":
    test_action_request_list_user_frame()
    test_set_request_list_doc_example()
    test_action_request_list_doc_example()
    test_action_response_list_doc_example()
    test_set_response_list_doc_example()
    test_report_notification_doc_example()
    test_report_response_doc_example()
    test_set_request_multiple_oads()
    test_eb_uint_big_endian()
    print("ALL 福建简化698 测试 PASSED")
