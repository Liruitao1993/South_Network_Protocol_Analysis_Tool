"""OAD/OMD 语义增强集成测试"""
from dl_t698_45_apdu_parser import DLT69845APDUParser
from dl_t698_45_oi_lookup import OILookup

lookup = OILookup()
parser = DLT69845APDUParser()

def test_get_request_oad():
    # OAD=0x2000 (电压, class_id=3), attr=2, index=1
    apdu = bytes([0x05, 0x01, 0x00, 0x20, 0x00, 0x02, 0x01])
    result = parser.parse(apdu)
    oad = result['OAD']
    desc = oad['语义说明']
    assert '电压' in desc, f"期望包含'电压', 实际: {desc}"
    assert '分相变量类' in desc, f"期望包含'分相变量类', 实际: {desc}"
    assert '分相数值数组' in desc, f"期望包含'分相数值数组', 实际: {desc}"
    assert '第1个元素' in desc, f"期望包含'第1个元素', 实际: {desc}"
    print(f"test_get_request_oad PASSED: {desc}")

def test_get_request_oad_index0():
    # OAD=0x2000, attr=2, index=0 (全部内容)
    apdu = bytes([0x05, 0x01, 0x00, 0x20, 0x00, 0x02, 0x00])
    result = parser.parse(apdu)
    oad = result['OAD']
    desc = oad['语义说明']
    assert '全部内容' in desc, f"期望包含'全部内容', 实际: {desc}"
    print(f"test_get_request_oad_index0 PASSED: {desc}")

def test_get_request_oad_energy():
    # OAD=0x0010 (正向有功总电能, class_id=1), attr=2, index=0
    # Verify in lookup first
    oi_name = lookup.OI_NAME_MAP.get(0x0010)
    class_id = lookup.OI_TO_CLASS_ID.get(0x0010)
    attr_name = lookup.get_attribute_name(0x0010, 2)
    print(f"OI 0x0010: name={oi_name}, class_id={class_id}, attr2={attr_name}")

    apdu = bytes([0x05, 0x01, 0x00, 0x00, 0x10, 0x02, 0x00])
    result = parser.parse(apdu)
    oad = result['OAD']
    desc = oad['语义说明']
    assert oi_name in desc, f"期望包含'{oi_name}', 实际: {desc}"
    assert attr_name in desc, f"期望包含'{attr_name}', 实际: {desc}"
    print(f"test_get_request_oad_energy PASSED: {desc}")

def test_action_request_omd():
    # OMD=0x0010, method=1 (复位)
    apdu = bytes([0x07, 0x01, 0x00, 0x00, 0x10, 0x01, 0x00])
    result = parser.parse(apdu)
    omd = result['OMD']
    desc = omd['语义说明']
    assert '正向有功电能' in desc, f"期望包含'正向有功电能', 实际: {desc}"
    assert '复位' in desc, f"期望包含'复位', 实际: {desc}"
    print(f"test_action_request_omd PASSED: {desc}")

def test_get_request_normal_list():
    # Two OADs: 0x2000 attr2 idx0, 0x0010 attr2 idx0
    apdu = bytes([0x05, 0x02, 0x00, 0x02,
                  0x20, 0x00, 0x02, 0x00,
                  0x00, 0x10, 0x02, 0x00])
    result = parser.parse(apdu)
    oads = result['OAD列表']
    assert len(oads) == 2
    desc0 = oads[0]['语义说明']
    desc1 = oads[1]['语义说明']
    assert '电压' in desc0, f"OAD[0]期望包含'电压', 实际: {desc0}"
    assert '正向有功电能' in desc1, f"OAD[1]期望包含'正向有功电能', 实际: {desc1}"
    print(f"test_get_request_normal_list PASSED: {desc0}; {desc1}")

def test_set_request_oad():
    # SET-Request Normal: OAD=0x2000 attr=2 index=0 + data
    from dl_t698_45_axdr import AXDRCoder
    axdr = AXDRCoder()
    data_bytes = axdr.encode(0x1234, 0x12)  # long-unsigned
    apdu = bytes([0x06, 0x01, 0x00, 0x20, 0x00, 0x02, 0x00]) + data_bytes
    result = parser.parse(apdu)
    oad = result['OAD']
    desc = oad['语义说明']
    assert '电压' in desc, f"期望包含'电压', 实际: {desc}"
    print(f"test_set_request_oad PASSED: {desc}")

def test_get_response_oad():
    # GET-Response Normal: OAD=0x0010 attr=2 idx=0, DAR_OK, data
    from dl_t698_45_axdr import AXDRCoder
    axdr = AXDRCoder()
    data_bytes = axdr.encode(0x1234, 0x12)
    apdu = bytes([0x85, 0x01, 0x00, 0x00, 0x10, 0x02, 0x00, 0x00]) + data_bytes
    result = parser.parse(apdu)
    oad = result['OAD']
    desc = oad['语义说明']
    assert '正向有功电能' in desc, f"期望包含'正向有功电能', 实际: {desc}"
    print(f"test_get_response_oad PASSED: {desc}")

def test_action_response_omd():
    # ACTION-Response Normal: OMD=0x2000 method=1, DAR_OK
    apdu = bytes([0x87, 0x01, 0x00, 0x20, 0x00, 0x01, 0x00, 0x00])
    result = parser.parse(apdu)
    omd = result['OMD']
    desc = omd['语义说明']
    assert '电压' in desc, f"期望包含'电压', 实际: {desc}"
    assert '复位' in desc, f"期望包含'复位', 实际: {desc}"
    print(f"test_action_response_omd PASSED: {desc}")

if __name__ == "__main__":
    test_get_request_oad()
    test_get_request_oad_index0()
    test_get_request_oad_energy()
    test_action_request_omd()
    test_get_request_normal_list()
    test_set_request_oad()
    test_get_response_oad()
    test_action_response_omd()
    print("\n=== 所有OAD/OMD增强测试通过 ===")
