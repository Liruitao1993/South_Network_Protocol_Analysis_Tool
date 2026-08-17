"""DL/T 698.45 协议解析器测试"""



import _path_setup  # noqa: E402

def test_link_request_login():
    """测试 LINK-Request 登录帧解析"""

    from dl_t698_45_parser import DLT69845Parser
    parser = DLT69845Parser()

    # 使用生成器生成的已知正确帧进行解析验证
    # 68 0E 00 41 01 07 08 09 88 03 01 00 00 00 00 34 87 16
    frame = bytes.fromhex("68 0E 00 41 01 07 08 09 88 03 01 00 00 00 00 34 87 16")

    result = parser.parse(frame)
    assert result["解析状态"] == "成功", result.get("错误信息", "")
    assert result["帧头"]["起始字符"] == "0x68"
    assert result["长度域"]["长度值"] == 14
    assert result["控制域"]["DIR"]["位"] == 0
    assert result["控制域"]["PRM"]["位"] == 1
    assert result["控制域"]["功能码"]["值"] == 1
    assert result["帧头校验HCS"]["校验结果"] == "通过"
    assert result["帧校验FCS"]["校验结果"] == "通过"
    print("test_link_request_login PASSED")


def test_axdr_basic():
    """测试 A-XDR 基础类型编解码"""
    from dl_t698_45_axdr import AXDRCoder
    coder = AXDRCoder()

    # 测试 integer
    data = bytes([0x0F, 0x05])  # integer = 5
    result, consumed = coder.decode(data)
    assert result["类型"] == "integer"
    assert result["解析值"] == 5
    assert consumed == 2

    # 测试 long-unsigned
    data = bytes([0x12, 0x34, 0x12])  # long-unsigned = 0x1234
    result, consumed = coder.decode(data)
    assert result["类型"] == "long-unsigned"
    assert result["解析值"] == 0x1234
    assert consumed == 3

    # 测试 OAD
    data = bytes([0x51, 0x01, 0x00, 0x02, 0x00])  # OAD: OI=0x0001, attr=0x02, index=0x00
    result, consumed = coder.decode(data)
    assert result["类型"] == "OAD"
    assert result["解析值"]["OI"] == "0x0001"
    assert result["解析值"]["属性编号"] == 2
    assert consumed == 5

    # 测试 encode/decode 往返
    encoded = coder.encode(100, 0x12)  # long-unsigned
    result, _ = coder.decode(encoded)
    assert result["解析值"] == 100

    print("test_axdr_basic PASSED")


def test_apdu_get_request_normal():
    """测试 GET-Request Normal APDU 解析"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser
    parser = DLT69845APDUParser()

    # GET-Request Normal: 05 01 [PIID=00] [OAD=2000 40 01]
    apdu = bytes([0x05, 0x01, 0x00, 0x20, 0x00, 0x40, 0x01])
    result = parser.parse(apdu)
    assert result["APDU类型"] == "GET-Request"
    assert result["子类型"] == "GetRequestNormal"
    assert result["OAD"]["解析值"]["OI"] == "0x2000"
    print("test_apdu_get_request_normal PASSED")


def test_oi_lookup():
    """测试 OI 查询"""
    from dl_t698_45_oi_lookup import OILookup
    lookup = OILookup()

    # 0x2000 -> class_id=3 (分相变量类), OI名称="电压"
    assert lookup.get_class_name(3) == "分相变量类"

    desc = lookup.get_oad_description(0x2000, 2, 0)
    assert "电压" in desc
    assert "分相变量类" in desc
    assert "分相数值数组" in desc
    assert "全部内容" in desc

    desc_logic = lookup.get_oad_description(0x2000, 1, 0)
    assert "逻辑名" in desc_logic

    # 测试 OI->class_id 映射 + 属性名称解析
    assert lookup.get_attribute_name(0x2000, 2) == "分相数值数组"
    assert lookup.get_attribute_name(0x2000, 1) == "逻辑名"
    assert lookup.get_attribute_name(0x2000, 99) is None  # 不存在的属性

    # 测试 OMD 描述
    desc_method = lookup.get_omd_description(0x2000, 1)
    assert "电压" in desc_method
    assert "复位" in desc_method

    print("test_oi_lookup PASSED")


def test_frame_generator():
    """测试帧生成器"""
    from dl_t698_45_frame_gen import DLT69845FrameGenerator
    from dl_t698_45_parser import DLT69845Parser

    gen = DLT69845FrameGenerator()
    parser = DLT69845Parser()

    # 测试 LINK-Request
    sa = bytes([0x01, 0x07, 0x08])  # 地址特征=01 (长度=2), 地址=07 08
    frame = gen.generate_link_request(sa, ca=0x09, piid=0x00, req_type=0x00, heartbeat=0x0000)
    result = parser.parse(frame)
    assert result["解析状态"] == "成功", result.get("错误信息", "")
    assert result["控制域"]["功能码"]["值"] == 1
    assert result["帧头校验HCS"]["校验结果"] == "通过"
    assert result["帧校验FCS"]["校验结果"] == "通过"

    # 测试 GET-Request Normal
    frame = gen.generate_get_request_normal(sa, ca=0x09, piid=0x00,
                                            oad=bytes.fromhex("20004001"))
    result = parser.parse(frame)
    assert result["解析状态"] == "成功", result.get("错误信息", "")
    apdu = result["链路用户数据"].get("APDU", {})
    assert apdu.get("APDU类型") == "GET-Request"

    print("test_frame_generator PASSED")


def test_validator():
    """测试协议验证器"""
    from validator.dl_t698_45_validator import DLT69845Validator
    from dl_t698_45_frame_gen import DLT69845FrameGenerator

    validator = DLT69845Validator()
    gen = DLT69845FrameGenerator()

    sa = bytes([0x01, 0x07, 0x08])
    frame = gen.generate_link_request(sa, ca=0x09, piid=0x00, req_type=0x00, heartbeat=0x0000)
    result = validator.verify(frame)
    assert result.valid
    assert result.pass_count >= 4
    print("test_validator PASSED")


def test_apdu_get_response_normal():
    """测试 GET-Response Normal 解析"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser
    from dl_t698_45_axdr import AXDRCoder
    parser = DLT69845APDUParser()
    axdr = AXDRCoder()

    # GET-Response Normal: 85 01 [PIID-ACD=00] [OAD=2000 40 01] [00=DAR_OK] [Data]
    # Data = long-unsigned 1234 (tag=0x12, value=0x1234)
    data_bytes = axdr.encode(0x1234, 0x12)
    apdu = bytes([0x85, 0x01, 0x00, 0x20, 0x00, 0x40, 0x01, 0x00]) + data_bytes
    result = parser.parse(apdu)
    assert result["APDU类型"] == "GET-Response"
    assert result["子类型"] == "GetResponseNormal"
    assert result["OAD"]["解析值"]["OI"] == "0x2000"
    assert result.get("数据访问结果", {}).get("DAR") == 0
    print("test_apdu_get_response_normal PASSED")


def test_apdu_set_request_normal():
    """测试 SET-Request Normal 解析"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser
    from dl_t698_45_axdr import AXDRCoder
    parser = DLT69845APDUParser()
    axdr = AXDRCoder()

    # SET-Request Normal: 06 01 [PIID=00] [OAD=2000 40 01] [Data]
    data_bytes = axdr.encode(0x1234, 0x12)  # long-unsigned
    apdu = bytes([0x06, 0x01, 0x00, 0x20, 0x00, 0x40, 0x01]) + data_bytes
    result = parser.parse(apdu)
    assert result["APDU类型"] == "SET-Request"
    assert result["子类型"] == "SetRequestNormal"
    assert result["OAD"]["解析值"]["OI"] == "0x2000"
    print("test_apdu_set_request_normal PASSED")


def test_apdu_action_request_normal():
    """测试 ACTION-Request Normal 解析"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser
    parser = DLT69845APDUParser()

    # ACTION-Request Normal: 07 01 [PIID=00] [OMD=0001 01 00]
    apdu = bytes([0x07, 0x01, 0x00, 0x00, 0x01, 0x01, 0x00])
    result = parser.parse(apdu)
    assert result["APDU类型"] == "ACTION-Request"
    assert result["子类型"] == "ActionRequestNormal"
    assert result["OMD"]["解析值"]["OI"] == "0x0001"
    print("test_apdu_action_request_normal PASSED")


def test_apdu_security():
    """测试 SECURITY-Request 解析"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser
    parser = DLT69845APDUParser()

    # SECURITY-Request: 10 00(明文) 08(长度=8) 05 01 7D 00 10 02 01 00 01(随机数) 10(RN_len=16) 00..0F
    apdu = bytes([0x10, 0x00, 0x08, 0x05, 0x01, 0x7D, 0x00, 0x10, 0x02, 0x01, 0x00, 0x01, 0x10]) + bytes(range(16))
    result = parser.parse(apdu)
    assert result["APDU类型"] == "SECURITY-Request"
    assert result["安全类型"]["解析值"] == 0
    assert result["解析状态"] == "成功"
    assert result["明文数据长度"] == 8
    assert result["SecurityRequestVerifyType"]["解析值"] == 1
    assert result["RN长度"] == 16
    print("test_apdu_security PASSED")


def test_apdu_error_response():
    """测试 ERROR-Response 解析"""
    from dl_t698_45_apdu_parser import DLT69845APDUParser
    parser = DLT69845APDUParser()

    # ERROR-Response: EE [PIID-ACD=00] [DAR=01]
    apdu = bytes([0xEE, 0x00, 0x0F, 0x01])
    result = parser.parse(apdu)
    assert result["APDU类型"] == "ERROR-Response"
    assert result.get("数据访问结果", {}).get("解析值") == 1
    print("test_apdu_error_response PASSED")


if __name__ == "__main__":
    test_link_request_login()
    test_axdr_basic()
    test_apdu_get_request_normal()
    test_oi_lookup()
    test_frame_generator()
    test_validator()
    test_apdu_get_response_normal()
    test_apdu_set_request_normal()
    test_apdu_action_request_normal()
    test_apdu_security()
    test_apdu_error_response()
    print("\n=== 所有测试通过 ===")
