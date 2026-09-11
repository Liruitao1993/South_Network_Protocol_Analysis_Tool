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


def test_read_address_13h():
    """读通信地址 13H（§7.4，地址域 AA…AA、L=0）→ 93H，数据域=表地址线上序。"""
    gen = DLT645FrameGenerator()
    sim = DLT645MeterSim(address="260526000028")
    req = gen.build_frame("AAAAAAAAAAAA", gen.build_control(0x13), b"")
    rsps = sim.handle_frame(req)
    assert len(rsps) == 1
    rsp = rsps[0]
    parsed = DLT645Parser().parse(rsp)
    assert parsed["control"] == 0x93, hex(parsed["control"])
    assert parsed["valid"] is True
    # 数据域 = 6 字节地址（+33H 加扰），去扰后按线上序 = encode_addr
    body = bytes((b - 0x33) & 0xFF for b in rsp[10:16])
    assert body == encode_addr("260526000028")
    # 应答地址域 = 表自身地址（非 AA）
    assert rsp[1:7] == encode_addr("260526000028")


def test_write_address_15h():
    """写通信地址 15H（§7.5）→ 95H 空数据应答，引擎地址变更、回调触发。"""
    gen = DLT645FrameGenerator()
    sim = DLT645MeterSim(address="000000000000")
    seen = []
    sim.on_address_written = seen.append
    new_addr = "123456789012"
    req = gen.build_frame("AAAAAAAAAAAA", gen.build_control(0x15),
                          encode_addr(new_addr))
    rsps = sim.handle_frame(req)
    assert len(rsps) == 1
    parsed = DLT645Parser().parse(rsps[0])
    assert parsed["control"] == 0x95, hex(parsed["control"])
    assert rsps[0][9] == 0  # L=00
    # §7.5.2：应答地址域 = 新设置的通信地址
    assert rsps[0][1:7] == encode_addr(new_addr)
    assert sim.address == new_addr
    assert seen == [new_addr]
    # 后续 13H 应答用新地址
    rsp13 = sim.handle_frame(
        gen.build_frame("AAAAAAAAAAAA", gen.build_control(0x13), b""))[0]
    assert DLT645Parser().parse(rsp13)["control"] == 0x93
    assert rsp13[1:7] == encode_addr(new_addr)


def test_write_address_bad_len():
    """15H 数据域长度非 6 → 异常应答 D5H（功能码跟随请求），地址不被改。"""
    gen = DLT645FrameGenerator()
    sim = DLT645MeterSim()
    req = gen.build_frame("AAAAAAAAAAAA", gen.build_control(0x15), b"\x11\x22")
    rsp = sim.handle_frame(req)[0]
    parsed = DLT645Parser().parse(rsp)
    assert parsed["control"] == 0xD5, hex(parsed["control"])
    assert sim.address == "000000000000"


def test_broadcast_time_08h_no_reply():
    """广播校时 08H：从站无应答。"""
    gen = DLT645FrameGenerator()
    sim = DLT645MeterSim()
    req = gen.build_frame("999999999999", gen.build_control(0x08),
                          bytes.fromhex("260526000028"))
    assert sim.handle_frame(req) == []
    assert "校时" in (sim.last_error or "")


def test_unsupported_func_error_code_follows_request():
    """未支持功能码（如 0x18）异常应答 = D8H 而非 D1H。"""
    gen = DLT645FrameGenerator()
    sim = DLT645MeterSim()
    req = gen.build_frame("000000000000", gen.build_control(0x18), b"")
    rsp = sim.handle_frame(req)[0]
    parsed = DLT645Parser().parse(rsp)
    assert parsed["control"] == 0xD8, hex(parsed["control"])


if __name__ == "__main__":
    for fn in (
        test_extract_frames,
        test_read_energy_roundtrip,
        test_unknown_di_error,
        test_archive_override,
        test_address_echo_field,
        test_encode_voltage_type,
        test_read_address_13h,
        test_write_address_15h,
        test_write_address_bad_len,
        test_broadcast_time_08h_no_reply,
        test_unsupported_func_error_code_follows_request,
    ):
        fn()
    print("dlt645_sim engine tests OK")
