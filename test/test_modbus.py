# -*- coding: utf-8 -*-
"""Modbus（协议15）纯逻辑测试：帧层 / PDU / 寄存器列表 / 帧提取 / 注册表 / 校验器。

运行方式：
    python test/test_modbus.py          # 独立运行（无需 pytest）
    pytest test/test_modbus.py          # 项目 CI 风格
"""

import shutil
import tempfile
from pathlib import Path

import _path_setup  # noqa: E402,F401

import modbus_core as mc
import modbus_register_store as store
import protocol_registry
from validator.modbus_validator import ModbusValidator


# ── 工具 ────────────────────────────────────────────────────────────


def _frame(body_hex: str) -> bytes:
    """按 Modbus RTU 补上正确 CRC16 的整帧。"""
    body = bytes.fromhex(body_hex.replace(" ", ""))
    return body + mc.crc16_bytes(body)


def _row(rows, prefix: str):
    for row in rows:
        if str(row[0]).strip().startswith(prefix):
            return row
    return None


def _row_by_field(rows, field: str):
    for row in rows:
        if str(row[0]) == field:
            return row
    return None


def _profile(**kwargs) -> dict:
    profile = {
        "id": "test-profile",
        "name": "测试寄存器列表",
        "brand": "测试",
        "transport": "auto",
        "byte_order": "big",
        "word_order": "big",
        "start_addr": 0,
        "note": "",
        "registers": [
            {"addr": 0x0000, "name": "电压", "type": "uint16", "count": 1, "scale": 0.1, "unit": "V", "note": ""},
            {"addr": 0x0001, "name": "电流", "type": "int16", "count": 1, "scale": 0.001, "unit": "A", "note": ""},
            {"addr": 0x0002, "name": "电能", "type": "uint32", "count": 2, "scale": 0.01, "unit": "kWh", "note": ""},
        ],
    }
    profile.update(kwargs)
    return profile


# ── CRC / 传输识别 ──────────────────────────────────────────────────


def test_crc16_known_value():
    # 规范常见样例：01 03 00 00 00 0A → CRC 0xCDC5（线上 C5 CD）
    assert mc.crc16(bytes.fromhex("01030000000A")) == 0xCDC5
    assert mc.crc16_bytes(bytes.fromhex("01030000000A")) == b"\xC5\xCD"
    assert mc.crc16(b"") == 0xFFFF


def test_detect_transport_does_not_mistake_rtu_zero_address_for_tcp():
    # RTU 起始地址 0x0000 ⇒ data[2:4] 恰好是 00 00，不能被误判成 MBAP
    rtu = _frame("010300000002")
    assert mc.detect_transport(rtu) == mc.TRANSPORT_RTU
    tcp = bytes.fromhex("000100000007010304006400C8")
    assert mc.detect_transport(tcp) == mc.TRANSPORT_TCP


def test_transport_split_fields():
    rtu = mc.split_frame(_frame("010300000002"))
    assert rtu["transport"] == mc.TRANSPORT_RTU
    assert rtu["slave"] == 1
    assert rtu["crc_ok"] is True
    assert rtu["pdu"] == bytes.fromhex("0300000002")

    tcp = mc.split_frame(bytes.fromhex("000100000007010304006400C8"))
    assert tcp["transport"] == mc.TRANSPORT_TCP
    assert tcp["slave"] == 1
    assert tcp["length_ok"] is True
    assert tcp["pdu"] == bytes.fromhex("030400640 0C8".replace(" ", ""))


# ── RTU 解析 ────────────────────────────────────────────────────────


def test_rtu_read_holding_registers_request():
    res = mc.parse_frame(_frame("010300000002"))
    assert res["direction"] == "请求"
    assert res["crc_ok"] is True
    assert "0x03 读保持寄存器" in _row(res["rows"], "功能码")[2]
    assert "0x0000" in _row(res["rows"], "起始地址")[2]
    assert _row(res["rows"], "寄存器数量")[2] == "2"
    assert res["func"] == 0x03


def test_rtu_read_holding_registers_response_generic():
    res = mc.parse_frame(_frame("010304006400C8"))
    assert res["direction"] == "响应"
    # 未指定寄存器列表：显式给出「通用解析」行 + 地址推导说明
    assert _row_by_field(res["rows"], "寄存器列表")[2] == "通用解析（未指定寄存器列表）"
    start_row = _row_by_field(res["rows"], "起始地址")
    assert start_row is not None and "推导" in start_row[3]
    reg0 = _row(res["rows"], "寄存器 0x0000")
    assert reg0 is not None and reg0[2] == "100"
    assert len(res["registers"]) == 2


def test_rtu_read_holding_registers_response_with_profile():
    res = mc.parse_frame(_frame("010304006400C8"), _profile())
    reg0 = _row(res["rows"], "寄存器 0x0000 电压")
    assert reg0 is not None
    assert reg0[2] == "10 V"  # 100 × 0.1
    reg1 = _row(res["rows"], "寄存器 0x0001 电流")
    assert reg1 is not None
    assert reg1[2] == "0.2 A"  # 200 × 0.001


def test_rtu_uint32_with_word_order_and_scale():
    # 0x00000100 = 256 → ×0.01 = 2.56 kWh，占 0x0002~0x0003
    profile = _profile(start_addr=0x0002)
    res = mc.parse_frame(_frame("01030400000100"), profile)
    row = _row(res["rows"], "寄存器 0x0002 电能")
    assert row is not None and row[2] == "2.56 kWh"

    # 低字在前（CDAB）：同一份数据 00 00 00 01，低字在前时高字是第二个寄存器 0x0001
    profile_le = _profile(start_addr=0x0002, word_order="little")
    res_le = mc.parse_frame(_frame("01030400000001"), profile_le)
    row_le = _row(res_le["rows"], "寄存器 0x0002 电能")
    assert row_le is not None and row_le[2] == "655.36 kWh"  # 0x00010000 × 0.01

    # 对照：高字在前时同一份数据 = 0x00000001 → 0.01 kWh
    res_be = mc.parse_frame(_frame("01030400000001"), _profile(start_addr=0x0002))
    assert _row(res_be["rows"], "寄存器 0x0002 电能")[2] == "0.01 kWh"


def test_rtu_int16_negative_value():
    profile = _profile(start_addr=0x0001)
    profile["registers"] = [profile["registers"][1]]
    res = mc.parse_frame(_frame("010302FFFE"), profile)
    row = _row(res["rows"], "寄存器 0x0001 电流")
    assert row is not None and row[2] == "-0.002 A"  # -2 × 0.001


def test_rtu_float32_profile():
    profile = {
        "id": "f",
        "name": "浮点表",
        "registers": [
            {"addr": 0, "name": "浮点值", "type": "float32", "count": 2, "scale": 1, "unit": ""}
        ],
        "start_addr": 0,
    }
    res = mc.parse_frame(_frame("01030442F6E979"), profile)
    row = _row(res["rows"], "寄存器 0x0000 浮点值")
    assert row is not None
    assert row[2].startswith("123.456")


def test_rtu_exception_response():
    res = mc.parse_frame(_frame("018302"))
    assert res["func"] == 0x03
    assert "异常" in res["func_name"]
    code_row = _row_by_field(res["rows"], "异常码")
    assert code_row is not None and "非法数据地址" in code_row[2]
    assert any("异常响应" in warn for warn in res["warnings"])


def test_rtu_read_coils_response():
    res = mc.parse_frame(_frame("01010105"))
    assert res["direction"] == "响应"
    bit0 = _row(res["rows"], "线圈 0x0000")
    bit1 = _row(res["rows"], "线圈 0x0001")
    assert bit0 is not None and "ON" in bit0[2]
    assert bit1 is not None and "OFF" in bit1[2]
    assert len(res["bits"]) == 8


def test_rtu_write_single_and_multiple_registers():
    single = mc.parse_frame(_frame("01060002000A"))
    assert _row(single["rows"], "寄存器地址")[2].startswith("0x0002")
    assert "0x000A" in _row(single["rows"], "写入值")[2]

    multi = mc.parse_frame(_frame("0110000000020400 0A000B".replace(" ", "")))
    assert multi["direction"] == "请求"
    assert _row(multi["rows"], "寄存器数量")[2] == "2"
    assert len(multi["registers"]) == 2


def test_tcp_response_and_request():
    resp = mc.parse_frame(bytes.fromhex("000100000007010304006400C8"))
    assert resp["transport"] == mc.TRANSPORT_TCP
    assert _row_by_field(resp["rows"], "事务标识")[2] == "1"
    assert len(resp["registers"]) == 2

    req = mc.parse_frame(bytes.fromhex("000A0000000601030000000 2".replace(" ", "")))
    assert req["transport"] == mc.TRANSPORT_TCP
    assert _row(req["rows"], "寄存器数量")[2] == "2"


def test_crc_error_still_parses_with_warning():
    bad = bytearray(_frame("010304006400C8"))
    bad[-1] ^= 0xFF
    res = mc.parse_frame(bytes(bad))
    assert res["crc_ok"] is False
    assert any("CRC" in warn for warn in res["warnings"])
    assert _row(res["rows"], "CRC16") is not None


def test_ascii_frame_is_rejected_with_hint():
    res = mc.parse_frame(b":010300000002FB\r\n")
    assert "ASCII" in res["summary"]
    assert res["rows"][0][0].startswith("❌")


def test_empty_and_short_frames():
    assert mc.parse_frame(b"")["rows"][0][0].startswith("❌")
    assert mc.parse_frame(b"\x01\x02")["rows"][0][0].startswith("❌")


# ── 帧提取（批量）───────────────────────────────────────────────────


def test_extract_single_and_multi_frames_with_log_prefix():
    frame = _frame("010304006400C8").hex().upper()
    assert [f[0] for f in mc.extract_modbus_frames(frame)] == [frame]

    line = f"15:49:51 254 -> {frame}  {frame}"
    assert [f[0] for f in mc.extract_modbus_frames(line)] == [frame, frame]

    # 空格分节的日志（时间戳里的数字不会被当成帧内容）
    spaced = " ".join(f"{b:02X}" for b in _frame("010304006400C8"))
    assert mc.extract_modbus_frames(f"15:49:51 -> {spaced}")[0][0] == frame


def test_extract_tcp_and_bad_crc_fallback():
    tcp = "000100000007010304006400C8"
    assert mc.extract_modbus_frames(tcp)[0][0] == tcp
    # CRC 被改坏：不静默丢帧，整段当一帧交给解析器（表格会标注 CRC 错误）
    bad = "010304006400C81A3C"
    extracted = mc.extract_modbus_frames(bad)
    assert extracted and extracted[0][0] == bad


def test_extract_skips_lines_without_hex():
    assert mc.extract_modbus_frames("启动完成\n无报文\n") == []


# ── 寄存器列表存储 ──────────────────────────────────────────────────


def _sandbox():
    path = Path(tempfile.mkdtemp(prefix="modbus_store_")) / "modbus_registers.json"
    store.set_store_path(path)
    return path


def test_store_builtin_examples_and_selection():
    _sandbox()
    profiles = store.profiles()
    assert len(profiles) >= 2
    assert store.selected_profile() is None  # 默认不选择 = 通用解析

    store.set_selected(profiles[0]["id"])
    assert store.selected_profile()["id"] == profiles[0]["id"]

    store.set_selected("不存在的 ID")
    assert store.selected_id() == ""  # 非法选择自动回落通用解析


def test_store_upsert_delete_and_duplicate():
    _sandbox()
    profile = _profile(id="", name="新表")
    new_id = store.upsert_profile(profile)
    assert store.get_profile(new_id)["name"] == "新表"
    assert store.get_profile(new_id)["registers"][0]["addr"] == 0

    clone_id = store.duplicate_profile(new_id, "新表副本")
    assert clone_id and clone_id != new_id
    assert store.get_profile(clone_id)["name"] == "新表副本"

    assert store.delete_profile(clone_id) is True
    assert store.get_profile(clone_id) is None
    assert store.delete_profile(clone_id) is False


def test_store_validation_rules():
    ok, error = store.validate_profile({"name": "", "registers": []})
    assert not ok and "名称" in error

    ok, error = store.validate_profile({"name": "x", "registers": []})
    assert not ok and "寄存器" in error

    dup = _profile()
    dup["registers"].append(dict(dup["registers"][0]))
    ok, error = store.validate_profile(dup)
    assert not ok and "重复" in error

    bad_scale = _profile()
    bad_scale["registers"][0]["scale"] = "abc"
    ok, error = store.validate_profile(bad_scale)
    assert not ok and "系数" in error


def test_store_import_export_json():
    _sandbox()
    text = store.profile_to_json(_profile(id="imp", name="导入表"))
    imported = store.import_profiles(text)
    assert imported and store.get_profile(imported[0])["name"] == "导入表"

    # 同一 ID 再导入：自动重新分配 ID，不覆盖已有列表
    again = store.import_profiles(text)
    assert again[0] != imported[0]
    assert len(store.profiles()) >= 2


def test_store_corrupted_file_falls_back_to_examples():
    path = _sandbox()
    path.write_text("{ this is not json", encoding="utf-8")
    store.reload()
    assert len(store.profiles()) >= 2  # 回落内置示例，不抛异常


# ── 注册表 / 校验器 ────────────────────────────────────────────────


def test_protocol_registry_entry():
    spec = protocol_registry.get_protocol(15)
    assert spec.name.startswith("[15]")
    assert spec.parser_key == "modbus"
    assert spec.parser_wrapper == "modbus"
    assert spec.extract_strategy == "modbus"
    assert spec.lookup_kind == "modbus"
    assert spec.frame_gen_mode is None and spec.preset_mode is None
    assert spec.has_monitor is False and spec.has_upgrade is False
    assert protocol_registry.name_to_index("Modbus") == 15
    assert protocol_registry.name_to_index("modbus tcp") == 15
    assert protocol_registry.lookup_builder_method("modbus") == "_create_modbus_lookup_content"
    assert len(protocol_registry.combo_labels()) == protocol_registry.protocol_count()


def test_registry_build_gui_parser_and_validator_map():
    import parser_registry

    base = parser_registry.get_parser("modbus")
    gui = protocol_registry.build_gui_parser(15, base)
    assert isinstance(gui, protocol_registry.ModbusGuiParser)

    validators = protocol_registry.build_validator_map()
    assert 15 in validators
    assert isinstance(validators[15], ModbusValidator)


def test_validator_accepts_good_frame_and_rejects_bad_crc():
    validator = ModbusValidator()
    good = validator.verify(_frame("010304006400C8"))
    assert good.valid is True
    assert good.fail_count == 0

    bad = bytearray(_frame("010304006400C8"))
    bad[-1] ^= 0xFF
    result = validator.verify(bytes(bad))
    assert result.valid is False
    assert result.fail_count >= 1


def test_validator_reports_ascii_and_mbap_length():
    validator = ModbusValidator()
    assert validator.verify(b":010300000002FB\r\n").valid is False

    tcp_bad = bytes.fromhex("0001000000080103040064 00C8".replace(" ", ""))  # 声明 14 字节，实收 13
    result = validator.verify(tcp_bad)
    assert any(check.name == "MBAP 长度域" for check in result.checks)
    assert result.valid is False


def test_validator_flags_pdu_length_mismatch():
    validator = ModbusValidator()
    # 0x03 响应字节数=3（奇数，本应为偶数）→ 长度不自洽
    body = bytes.fromhex("0103030010 02".replace(" ", ""))
    frame = body + mc.crc16_bytes(body)
    result = validator.verify(frame)
    assert any(
        check.name == "数据长度自洽" and check.level.value == "fail"
        for check in result.checks
    )


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  [PASS] {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  [FAIL] {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  [ERR ] {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n结果: {len(tests) - failed} 通过, {failed} 失败")
    shutil.rmtree(Path(store.store_path()).parent, ignore_errors=True)
    raise SystemExit(1 if failed else 0)
