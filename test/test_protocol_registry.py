"""protocol_registry 纯逻辑测试（无 Qt）。"""

import _path_setup  # noqa: E402

from protocol_registry import (  # noqa: E402
    all_protocols,
    build_gui_parser,
    build_validator_map,
    combo_labels,
    get_protocol,
    name_to_index,
    placeholder_for,
    protocols_with_frame_gen,
    protocols_with_monitor,
    protocols_with_sequence_diagram,
)


def test_registry_covers_12_protocols():
    assert len(all_protocols()) == 12
    assert len(combo_labels()) == 12
    for i in range(12):
        assert get_protocol(i).index == i


def test_combo_labels_keep_index_prefix():
    labels = combo_labels()
    for i, label in enumerate(labels):
        assert label.startswith(f"[{i}]")


def test_placeholder_non_empty():
    for i in range(12):
        assert placeholder_for(i).strip()


def test_name_to_index_aliases():
    assert name_to_index("0") == 0
    assert name_to_index("南网") == 0
    assert name_to_index("国网新一代") == 10
    assert name_to_index("HDC1.0") == 11
    assert name_to_index("645") == 6
    assert name_to_index("不存在协议") is None


def test_frame_gen_protocols():
    assert set(protocols_with_frame_gen()) == {0, 6, 7, 8}
    assert get_protocol(0).frame_gen_mode == "south"
    assert get_protocol(6).frame_gen_mode == "dlt645"
    assert get_protocol(6).preset_mode == "dlt645"


def test_sequence_and_monitor_capabilities():
    assert set(protocols_with_sequence_diagram()) == {9, 10, 11}
    assert set(protocols_with_monitor()) == {9, 10}
    assert get_protocol(9).monitor_wrapper == "plc2"
    assert get_protocol(10).monitor_wrapper == "hplc"
    assert get_protocol(11).has_monitor is False


def test_virtual_meter_only_698():
    assert get_protocol(8).has_virtual_meter is True
    assert get_protocol(6).has_virtual_meter is False
    assert get_protocol(0).has_archive is True
    assert get_protocol(6).has_archive is False


def test_validator_map_all_12():
    m = build_validator_map()
    assert set(m.keys()) == set(range(12))
    # 南网校验器应能对非空 bytes 返回 ValidationResult
    r = m[0].verify(b"\x00")
    assert hasattr(r, "valid")


def test_extract_strategies():
    assert get_protocol(0).extract_strategy == "ft12_68"
    assert get_protocol(7).extract_strategy == "ft12_68"
    assert get_protocol(8).extract_strategy == "dlt698_45"
    assert get_protocol(4).extract_strategy == "wrapper"
    assert get_protocol(9).extract_strategy == "csg_line"
    assert get_protocol(10).extract_strategy == "gw_line_min4"
    assert get_protocol(3).extract_strategy == "line"


class _FakeHdlc:
    def parse_apdu_to_table(self, data):
        return [("apdu", data, "", "", 0, 0)]

    def parse_wrapper_to_table(self, data):
        return [("wrap", data, "", "", 0, 0)]


def test_build_gui_parser_wrappers():
    hdlc = _FakeHdlc()
    p3 = build_gui_parser(3, hdlc)
    assert p3.parse_to_table(b"\x01") == [("apdu", b"\x01", "", "", 0, 0)]
    p4 = build_gui_parser(4, hdlc)
    assert p4.parse_to_table(b"\x02")[0][0] == "wrap"
    p0 = build_gui_parser(0, hdlc)
    assert p0 is hdlc  # direct 不包装


def test_lookup_builder_methods():
    from protocol_registry import lookup_builder_method

    assert lookup_builder_method("di_nw") == "_create_di_lookup_content"
    assert lookup_builder_method("hdc10") == "_create_hdc10_lookup_content"
    assert lookup_builder_method(None) is None


if __name__ == "__main__":
    test_registry_covers_12_protocols()
    test_combo_labels_keep_index_prefix()
    test_placeholder_non_empty()
    test_name_to_index_aliases()
    test_frame_gen_protocols()
    test_sequence_and_monitor_capabilities()
    test_virtual_meter_only_698()
    test_validator_map_all_12()
    test_extract_strategies()
    test_build_gui_parser_wrappers()
    test_lookup_builder_methods()
    print("protocol_registry tests OK")
