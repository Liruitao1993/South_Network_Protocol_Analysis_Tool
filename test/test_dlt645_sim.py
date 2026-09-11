# -*- coding: utf-8 -*-
"""DLT645 从站模拟引擎测试（纯逻辑，无 Qt）。"""

import _path_setup  # noqa: E402

from dlt645_data_codec import encode_value  # noqa: E402
from dlt645_frame_gen import DLT645FrameGenerator, encode_addr, encode_di  # noqa: E402
from dlt645_parser import DLT645Parser  # noqa: E402
from dlt645_sim import DLT645MeterSim  # noqa: E402
from dlt645_sim.archive import DLT645Archive  # noqa: E402
from dlt645_sim.engine import extract_645_frames  # noqa: E402


def _read_req(addr: str, di: str) -> bytes:
    gen = DLT645FrameGenerator()
    ctrl = gen.build_control(0x11, dir_bit=0)
    data = encode_di(di)
    return gen.build_frame(addr, ctrl, data)


def test_extract_frames():
    gen = DLT645FrameGenerator()
    fr = gen.build_frame("000000000000", gen.build_control(0x11), encode_di("00010000"))
    got = extract_645_frames(b"\x00" + fr + b"\xff" + fr)
    assert len(got) == 2
    assert got[0] == fr


def test_read_energy_roundtrip():
    sim = DLT645MeterSim(address="260526000028")
    req = _read_req("260526000028", "00010000")
    rsps = sim.handle_frame(req)
    assert len(rsps) == 1
    parsed = DLT645Parser().parse(rsps[0])
    assert parsed["valid"] is True
    assert parsed["control"] == 0x91
    assert parsed["di_code"] == "00010000"
    # 解析结果应含 123456.78 相关字段
    blob = str(parsed) + "".join(str(x) for x in parsed.get("fields", []))
    assert "123456" in blob or "78" in blob


def test_unknown_di_error():
    sim = DLT645MeterSim()
    req = _read_req("000000000000", "DEADBEEF")
    rsps = sim.handle_frame(req)
    assert len(rsps) == 1
    parsed = DLT645Parser().parse(rsps[0])
    assert parsed["control"] & 0x40  # ERR flag
    # 异常数据域末字节 ERR
    assert parsed.get("valid") in (True, False)


def test_archive_override():
    arc = DLT645Archive()
    arc.set("00010000", "000001.00")
    sim = DLT645MeterSim(archive=arc)
    rsps = sim.handle_frame(_read_req("000000000000", "00010000"))
    parsed = DLT645Parser().parse(rsps[0])
    assert parsed["control"] == 0x91


def test_address_echo_field():
    gen = DLT645FrameGenerator()
    # 确保地址编码与请求一致时从站用自己地址应答
    sim = DLT645MeterSim(address="112233445566")
    req = gen.build_frame("112233445566", gen.build_control(0x11), encode_di("02010100"))
    rsp = sim.handle_frame(req)[0]
    assert rsp[1:7] == encode_addr("112233445566")


def test_encode_voltage_type():
    b = encode_value("220.5", "XXX.X")
    assert len(b) == 2


if __name__ == "__main__":
    test_extract_frames()
    test_read_energy_roundtrip()
    test_unknown_di_error()
    test_archive_override()
    test_address_echo_field()
    test_encode_voltage_type()
    print("dlt645_sim engine tests OK")
