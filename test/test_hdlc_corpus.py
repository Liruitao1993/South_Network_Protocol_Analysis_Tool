# -*- coding: utf-8 -*-
"""协议2（HDLC/国网DLMS）真实报文语料回归。

语料来源（抓取时间 2026-10-23）：
- DLMS UA《Examples for DLMS/COSEM Information Exchange》(Gyozo Kmethy)：
  SNRM/UA、AARQ/AARE、Get/Set 请求响应、多种数据类型（date-time/int8/int16/uint8/bool/enum/octet-string）
- 《DLMS Handbook》(pdfcoffee, 第 3 章 HDLC 帧结构)：带 HDLC 参数协商的 SNRM/UA、AARQ/AARE(LLS)
- Gurux 论坛实抓帧：短 SNRM/UA（2 字节服务器地址）

覆盖点：
1. 真实帧不崩溃、HCS/FCS 判定正确；
2. 地址语义（4 字节 → 逻辑设备/逻辑块，2 字节 → 服务器地址）；
3. AARQ/AARE 的 BER 结构（application-context OID、user-information）；
4. DLMS A-XDR 数据类型（date-time / int / bool / enum / octet-string / OBIS）；
5. 事件通知(0xC2)、数据通知(0x0F)、异常响应(0xD8)、分块响应(C4/02)、分段位；
6. 多帧连续传输共享 7E 标志时的批量切帧；
7. 文档笔误帧（FCS 不符）不崩溃、如实标注错误。

运行：``python test/test_hdlc_corpus.py`` 或 ``pytest test/test_hdlc_corpus.py``
"""

import re

import _path_setup  # noqa: E402,F401

from hdlc_parser import HDLCParser

# ── 真实帧语料（均已用解析器 HCS/FCS 校验为自洽帧）────────────────────
FRAMES = {
    # SNRM / UA
    "snrm": "7EA00A00020023219318717E",
    "ua": "7EA023210002002373F6C58180140502008006020080070400000001080400000001CE6A7E",
    "snrm_params": "7EA01E032193CD3B818012050182060182070400000002080400000002CDBE7E",
    "ua_params": "7EA01E210373C37A818012050180060180070400000002080400000002A6A17E",
    "snrm_2byte_addr": "7EA0080247099362EF7E",
    "ua_2byte_addr": "7EA02109024773311A8180140502016006020160070400000001080400000001DE897E",
    # AARQ / AARE
    "aarq_ln": "7EA02E0002002321107ECBE6E600601DA109060760857405080101BE10040E01000000065F1F040000301DFFFFD4C57E",
    "aare_ln": "7EA03A2100020023309941E6E7006129A109060760857405080101A203020100A305A103020100BE10040E0800065F1F040000301D190000070C527E",
    "aarq_lls": "7EA047000200230310413EE6E6006036A1090607608574050801018A0207808B0760857405080201AC0A80083132333435363738BE10040E01000000065F1F0400001A1DFFFF33897E",
    "aare_lls": "7EA03A030002002330AFCCE6E7006129A109060760857405080101A203020100A305A103020100BE10040E0800065F1F0400001A1D05DC00075B807E",
    # Get / Set
    "get_req_clock": "7EA0199575546835E6E600C0018100080000010000FF01000DFD7E",
    "get_resp_clock": "7EA018759574E9E8E6E700C401810009060000010000FFFD497E",
    "get_req_time": "7EA0199575767837E6E600C0018100080000010000FF020065D77E",
    "get_resp_time": "7EA01E7595966F67E6E700C4018100090C07D20C04030A060BFF007800F3307E",
    "set_req_time": "7EA027957598B8DBE6E600C1018100080000010000FF0200090C07D20C04030A060BFF00780062FB7E",
    "set_resp_ok": "7EA0107595B85101E6E700C501810036CF7E",
    "get_req_attr3": "7EA0199575BA183BE6E600C0018100080000010000FF0300BDCE7E",
    "get_resp_int16": "7EA0137595DA8864E6E700C4018100100078563A7E",
    "set_req_int16": "7EA01C9575DC7F53E6E600C1018100080000010000FF030010007801177E",
    "get_resp_uint8": "7EA01275951E1BF8E6E700C40181001100AC5B7E",
    "get_resp_octet12": "7EA01E75953053A7E6E700C4018100090CFF4F19F3007000000000000F090A7E",
    "get_resp_int8": "7EA0127595744734E6E700C40181000F002D547E",
    "get_resp_bool": "7EA0127595965BF0E6E700C401810003008DFD7E",
    "get_resp_enum": "7EA0127595B82738E6E700C401810016012D077E",
    # 事件通知（UI 帧，国网自定义事件体）
    "event_notification": "7EA02B030313E38DE6E700C20000070000636202FF0201010202090C07E80A1D0214170FFFFED4001101E6B37E",
}

#: 文档笔误帧（FCS 与实际字节不符，用于容错回归）
BROKEN_FCS = {
    "get_req_serial_bad_fcs": "7EA0190321326FD8E6E600C00181000100000000FF0200C6607E",
    "get_resp_serial_bad_fcs": "7EA01A210352A438E6E700C40181000908" "55544F383434383867D97E",
}

parser = HDLCParser()


# ── 工具 ────────────────────────────────────────────────────────────
def rows_of(hexstr: str):
    return parser.parse_to_table(bytes.fromhex(hexstr))


def row_value(rows, keyword: str):
    """取第一个「字段名包含 keyword」的解析值。"""
    for row in rows:
        if keyword in str(row[0]):
            return str(row[2])
    return ""


def row_comment(rows, keyword: str):
    for row in rows:
        if keyword in str(row[0]):
            return str(row[3])
    return ""


def check_level(rows, keyword: str) -> str:
    for row in rows:
        if keyword in str(row[0]):
            return str(row[2])
    return ""


def build_frame(info: bytes, *, dest=b"\x03", src=b"\x21", ctrl=0x10, segmented=False) -> str:
    """按 IEC 62056-46 Type 3 组一帧（HCS/FCS 用解析器同一算法）。"""

    def fcs(data: bytes) -> bytes:
        value = parser._calculate_fcs(data)
        return bytes((value & 0xFF, value >> 8))

    total = 2 + len(dest) + len(src) + 1 + 2 + len(info) + 2
    ff = (0xA800 if segmented else 0xA000) | total
    header = ff.to_bytes(2, "big") + dest + src + bytes([ctrl])
    body = header + fcs(header) + info
    return (b"\x7E" + body + fcs(body) + b"\x7E").hex().upper()


# ── 1. 真实帧：不崩溃 + 校验结论 ────────────────────────────────────
def test_all_real_frames_parse_without_crash():
    for name, hexstr in FRAMES.items():
        rows = parser.parse_to_table(bytes.fromhex(hexstr))
        assert rows, name
        assert not any(str(row[0]).startswith("错误") for row in rows), name
        # 每条真实帧都应给出结构化结果（曾 100% TypeError）
        result = parser.parse(bytes.fromhex(hexstr))
        assert result["解析状态"] == "成功", name
        assert result["控制域"]["帧类型"], name
        assert isinstance(result["控制域"]["位明细"], list), name


def test_real_frames_hcs_and_fcs_ok():
    for name, hexstr in FRAMES.items():
        rows = rows_of(hexstr)
        # 无信息域帧只有一行「HCS/FCS校验」；有信息域时 HCS、FCS 各一行
        checks = [
            str(row[2]) for row in rows
            if str(row[0]).startswith(("HCS", "FCS"))
        ]
        assert checks and all("正确" in text for text in checks), (name, checks)


def test_documented_broken_frames_are_flagged_not_crashed():
    for name, hexstr in BROKEN_FCS.items():
        rows = parser.parse_to_table(bytes.fromhex(hexstr))
        assert rows, name
        assert "错误" in check_level(rows, "FCS"), name


# ── 2. 帧层：地址 / 控制域 ─────────────────────────────────────────
def test_address_semantics():
    # 4 字节服务器地址 00 02 00 23 → 逻辑设备 0x0001 / 逻辑块 0x0011（第 3 列是格式化描述）
    rows = rows_of(FRAMES["aarq_ln"])
    dest = row_value(rows, "目的地址域")
    assert "逻辑设备 0x0001" in dest and "逻辑块 0x0011" in dest, dest

    # 2 字节服务器地址 02 47 → 服务器地址 0x1181（Gurux 口径）
    rows = rows_of(FRAMES["snrm_2byte_addr"])
    dest = row_value(rows, "目的地址域")
    assert "0x1181" in dest, dest

    # 1 字节客户端地址 0x21 → 0x10（公共客户端）
    rows = rows_of(FRAMES["snrm_params"])
    assert "客户端" in row_value(rows, "源地址域")


def test_control_field_types():
    assert "SNRM" in row_value(rows_of(FRAMES["snrm"]), "控制域")
    assert "UA" in row_value(rows_of(FRAMES["ua"]), "控制域")
    # I 帧序号：get_resp_time 控制域 0x96 → N(S)=3 / N(R)=4
    rows = rows_of(FRAMES["get_resp_time"])
    assert row_value(rows, "N(S)发送序号") == "3"
    assert row_value(rows, "N(R)接收序号") == "4"
    # UI 帧
    assert "UI帧" in row_value(rows_of(FRAMES["event_notification"]), "控制域")


# ── 3. APDU 类型识别 ───────────────────────────────────────────────
def test_apdu_type_detection():
    cases = {
        "aarq_ln": "AARQ",
        "aare_ln": "AARE",
        "get_req_clock": "Get-Request",
        "get_resp_clock": "Get-Response",
        "set_req_time": "Set-Request",
        "set_resp_ok": "Set-Response",
        "event_notification": "Event-Notification-Request",
    }
    for name, expected in cases.items():
        rows = rows_of(FRAMES[name])
        apdu = row_value(rows, "DLMS APDU")
        assert expected in apdu, (name, apdu)


def test_aarq_ber_structure():
    rows = rows_of(FRAMES["aarq_ln"])
    values = [str(row[2]) for row in rows]
    # application-context OID 必须解码成 OID 字符串（曾因整棵 BER 树错位而碎成标签）
    assert any("2.16.756.5.8.1.1" in value for value in values), values[:12]
    # APDU 标签本身必须是 AARQ
    assert any("AARQ (关联请求)" in value for value in values)
    # user-information 必须被识别
    assert any("user-information" in value for value in values)


def test_aare_ber_fields():
    rows = rows_of(FRAMES["aare_ln"])
    assert "AARE (关联响应)" in row_value(rows, "BER标签")
    # 协商的 DLMS 版本 / conformance / server-max-receive-pdu 都在 user-information 内
    assert any("user-information" in str(r[2]) for r in rows)


def test_lls_auth_fields():
    rows = rows_of(FRAMES["aarq_lls"])
    text = " ".join(str(r[2]) for r in rows)
    assert "authentication-value" in text or "password" in text or "Context-Specific" in text


# ── 4. DLMS A-XDR 数据类型 ────────────────────────────────────────
def test_datetime_decoding():
    rows = rows_of(FRAMES["get_resp_time"])
    text = row_value(rows, "date-time")
    assert "2002-12-04" in text, text
    assert "10:06:11" in text, text
    assert "UTC偏差 120 分钟" in text, text


def test_octet_string_obis_and_raw():
    rows = rows_of(FRAMES["get_resp_clock"])
    text = row_value(rows, "返回数据")
    assert "OBIS 0.0.1.0.0.255" in text, text

    # 12 字节但日期字段非法（全 FF）→ 不能硬当 date-time，应按 octet-string 展示
    rows = rows_of(FRAMES["get_resp_octet12"])
    text = row_value(rows, "返回数据")
    assert "FF 4F 19" in text or "12 字节" in text, text


def test_integer_and_boolean_types():
    assert row_value(rows_of(FRAMES["get_resp_int16"]), "返回数据") == "120"
    assert row_value(rows_of(FRAMES["get_resp_int8"]), "返回数据") == "0"
    assert row_value(rows_of(FRAMES["get_resp_uint8"]), "返回数据") == "0"
    assert row_value(rows_of(FRAMES["get_resp_bool"]), "返回数据") == "FALSE"
    assert row_value(rows_of(FRAMES["get_resp_enum"]), "返回数据") == "1"


def test_set_request_value_and_descriptor():
    rows = rows_of(FRAMES["set_req_int16"])
    assert row_value(rows, "写入数据") == "120"
    assert "Clock" in row_value(rows, "类ID")
    assert "0.0.1.0.0.255" in row_value(rows, "OBIS码")


def test_snrm_ua_parameter_negotiation():
    rows = rows_of(FRAMES["snrm_params"])
    assert "Max Info Field Length - Transmit" in " ".join(str(r[2]) for r in rows)
    assert "Window Size - Transmit" in " ".join(str(r[2]) for r in rows)


# ── 5. 边界分支（按规范构造）───────────────────────────────────────
LLC = bytes.fromhex("E6E700")
DATETIME = bytes.fromhex("07E80A1D0214170F")


def test_get_response_with_datablock():
    frame = build_frame(LLC + bytes.fromhex("C402810000000001") + b"\x09\x0C" + DATETIME)
    rows = rows_of(frame)
    assert "With-data-block" in row_value(rows, "响应类型")
    assert "非最后一块" in row_value(rows, "Block-Control")
    assert row_value(rows, "Block-Number") == "1"
    assert row_value(rows, "分块数据")


def test_data_notification():
    frame = build_frame(LLC + bytes.fromhex("0F0000000100") + b"\x19" + DATETIME + b"\x00\x00")
    rows = rows_of(frame)
    assert "Data-Notification" in row_value(rows, "DLMS APDU")
    assert "data-notification" in row_value(rows, "通知体类型")


def test_exception_response():
    # state-error=1 (service-not-allowed)、service-error=1 (operation-not-possible)
    frame = build_frame(LLC + bytes.fromhex("D80101"))
    rows = rows_of(frame)
    assert "Exception-Response" in row_value(rows, "DLMS APDU")
    assert "service-not-allowed" in row_value(rows, "State-Error")
    assert "operation-not-possible" in row_value(rows, "Service-Error")


def test_invoke_id_and_priority_bit_layout():
    # Green Book：低 4 位=invoke-id、bit6=service-class（0=Unconfirmed/1=Confirmed）、
    # bit7=priority（0=Normal/1=High）。
    # 0xC1 = 1100 0001 → ID=1、Confirmed、High；0x81 → ID=1、Unconfirmed、High。
    rows = rows_of(build_frame(LLC + bytes.fromhex("C401C100") + b"\x09\x0C" + DATETIME))
    text = row_value(rows, "Invoke-Id")
    assert "ID=1" in text and "Confirmed" in text and "High" in text, text

    rows = rows_of(build_frame(LLC + bytes.fromhex("C4018100") + b"\x09\x0C" + DATETIME))
    text = row_value(rows, "Invoke-Id")
    assert "ID=1" in text and "Unconfirmed" in text and "High" in text, text


def test_data_access_result_enum_values():
    # Get-Response-Normal 失败：result=0x01 + DataAccessResult=3（read-write-denied）
    frame = build_frame(LLC + bytes.fromhex("C401810103"))
    text = row_value(rows_of(frame), "结果")
    assert "read-write-denied" in text, text


def test_rlrq_rlre_recognition():
    # ACSE 释放：0x62=RLRQ、0x63=RLRE（此前被误登记为 0x03/0x04）
    for tag, name in ((0x62, "RLRQ"), (0x63, "RLRE")):
        frame = build_frame(LLC + bytes([tag, 0x03, 0x80, 0x01, 0x00]))
        apdu = row_value(rows_of(frame), "DLMS APDU")
        assert name in apdu, (tag, apdu)


def test_get_request_with_list():
    # Get-Request-With-List：C0 03 <invoke> <count=2> + 2×(9B 描述符 + 选择 0x00)
    payload = bytes.fromhex(
        "C0038102"
        "00080000010000FF0200"
        "00080000020000FF0200"
    )
    rows = rows_of(build_frame(LLC + payload))
    assert "With-list" in row_value(rows, "请求类型")
    assert row_value(rows, "属性描述符数量") == "2"


def test_segmented_frame_flag():
    frame = build_frame(LLC + b"\xC4\x01\x81\x00" + b"\x09\x0C" + DATETIME, segmented=True)
    rows = rows_of(frame)
    assert "分段位=1" in row_value(rows, "格式域")


# ── 6. 批量切帧：共享 7E 标志 ─────────────────────────────────────
def test_extract_frames_sharing_flag():
    import main_gui

    first = FRAMES["get_req_clock"]
    second = FRAMES["get_resp_clock"]
    # 两帧连续传输：前一帧的结束 7E 也是后一帧的起始 7E
    stream = first + second[2:]
    frames = main_gui.MainWindow._extract_hdlc_frames(None, stream)
    assert len(frames) == 2, frames
    assert frames[0] == first
    assert frames[1] == second


def test_extract_frames_shared_flag_with_e6e7():
    import main_gui

    # GET-RESP-TIME 帧内含 `67 E6`：按字符搜 "7E" 会在字节中间误判边界
    first = FRAMES["get_req_clock"]
    second = FRAMES["get_resp_time"]
    stream = main_gui.MainWindow._clean_hex_input(first + second[2:])
    frames = main_gui.MainWindow._extract_hdlc_frames(None, stream)
    assert frames == [first, second], frames


def test_summary_and_type_name_for_dlms():
    import main_gui

    rows = rows_of(FRAMES["get_req_clock"])
    summary = main_gui.MainWindow._get_summary_from_table_data(None, rows, 2)
    assert "Get-Request" in summary, summary
    assert "OBIS:0.0.1.0.0.255" in summary, summary

    name = main_gui.MainWindow._get_frame_type_name(None, rows, "成功", 2)
    assert name.startswith("Get-Request"), name


def test_structure_and_array():
    # structure(2)：long-unsigned(0x0064=100) + octet-string(2 字节)
    payload = bytes.fromhex("0202120064090200 01".replace(" ", ""))
    frame = build_frame(LLC + bytes.fromhex("C4018100") + payload)
    rows = rows_of(frame)
    assert "structure" in row_value(rows, "返回数据")
    assert row_value(rows, "返回数据 [0]") == "100"
    assert "00 01" in row_value(rows, "返回数据 [1]")

    # array(2)：两个 unsigned
    payload = bytes.fromhex("0102 11 05 11 0A".replace(" ", ""))
    frame = build_frame(LLC + bytes.fromhex("C4018100") + payload)
    rows = rows_of(frame)
    assert "array" in row_value(rows, "返回数据")
    assert row_value(rows, "返回数据 [0]") == "5"
    assert row_value(rows, "返回数据 [1]") == "10"


def test_extract_frames_plain_and_noise():
    import main_gui

    first = FRAMES["get_req_clock"]
    assert main_gui.MainWindow._extract_hdlc_frames(None, first) == [first]
    # 与 parse_batch 一致：先清洗掉时间戳/空格再切帧
    noisy = main_gui.MainWindow._clean_hex_input(
        "15:49:51 " + first + "  " + FRAMES["get_resp_clock"]
    )
    assert len(main_gui.MainWindow._extract_hdlc_frames(None, noisy)) == 2


# ── 7. 中文表述约定（国内现场口径：中文在前、标准英文原名括注）────────────
CJK = re.compile(r"[\u4e00-\u9fff]")
CJK_FIRST = re.compile(r"^[\u4e00-\u9fff]")


def test_enum_tables_are_chinese_first():
    """枚举表每一条都必须「中文在前 + 英文原名括注」，防止后续新增纯英文枚举。"""
    tables = {
        "SNRM_UA_PARAM_TAGS": HDLCParser.SNRM_UA_PARAM_TAGS,
        "GET_REQUEST_TYPES": HDLCParser.GET_REQUEST_TYPES,
        "GET_RESPONSE_TYPES": HDLCParser.GET_RESPONSE_TYPES,
        "SET_REQUEST_TYPES": HDLCParser.SET_REQUEST_TYPES,
        "SET_RESPONSE_TYPES": HDLCParser.SET_RESPONSE_TYPES,
        "ACTION_REQUEST_TYPES": HDLCParser.ACTION_REQUEST_TYPES,
        "ACTION_RESPONSE_TYPES": HDLCParser.ACTION_RESPONSE_TYPES,
        "DATA_ACCESS_RESULTS": HDLCParser.DATA_ACCESS_RESULTS,
        "ACTION_RESULTS": HDLCParser.ACTION_RESULTS,
        "EXCEPTION_STATE_ERRORS": HDLCParser.EXCEPTION_STATE_ERRORS,
        "EXCEPTION_SERVICE_ERRORS": HDLCParser.EXCEPTION_SERVICE_ERRORS,
        "COSEM_CLASS_NAMES": HDLCParser.COSEM_CLASS_NAMES,
    }
    for name, table in tables.items():
        for code, text in table.items():
            # 必须含中文；并且英文原名用全角括号括注（半角括号的老写法一律淘汰）
            assert CJK.search(text), (name, code, text)
            assert "（" in text and "）" in text, (name, code, text)


def test_address_and_control_labels_are_chinese_first():
    for code in (0x00, 0x10, 0x7F):
        text = HDLCParser.SPECIAL_ADDRESSES[code]
        assert CJK_FIRST.match(text), (code, text)
    for key, text in HDLCParser.CONTROL_FIELD_TYPES.items():
        assert CJK_FIRST.match(text), (key, text)


def test_axdr_type_note_is_chinese_first():
    assert "16 位有符号整数（long）" in row_comment(rows_of(FRAMES["get_resp_int16"]), "返回数据")
    assert "布尔值（boolean）" in row_comment(rows_of(FRAMES["get_resp_bool"]), "返回数据")
    assert "字节串（octet-string）" in row_comment(rows_of(FRAMES["get_resp_octet12"]), "返回数据")


def test_ber_tag_desc_is_chinese_first():
    tags = [str(row[2]) for row in rows_of(FRAMES["aarq_ln"]) if str(row[0]).strip() == "BER标签"]
    assert any("用户信息（user-information）" in tag for tag in tags), tags
    assert any(tag.startswith("通用（Universal）") for tag in tags), tags


def test_invoke_and_class_labels_are_chinese_first():
    rows = rows_of(FRAMES["get_req_clock"])
    text = row_value(rows, "调用标识与优先级")
    assert "不需确认（Unconfirmed）" in text and "高优先级（High）" in text, text
    assert row_value(rows, "类ID").startswith("时钟（Clock）")


# ── 8. 帧长自证（串口半包 / 抓包截断 / 粘包）──────────────────────────
def test_declared_length_mismatch_is_reported():
    truncated = "7EA0199575546835E6E600C0"  # 格式域声明 25 字节，实际只到 12 字节
    result = parser.parse(bytes.fromhex(truncated))
    assert result["解析状态"] == "成功", result["解析状态"]
    hint = result["格式域"]["帧长校验"]
    assert "疑似截断" in hint and "25" in hint, hint
    warnings = [
        str(row[3]) for row in parser.parse_to_table(bytes.fromhex(truncated))
        if str(row[0]) == "警告"
    ]
    assert any("疑似截断" in text for text in warnings), warnings


def test_declared_length_ok_frames_have_no_warning():
    for name in ("get_req_clock", "snrm", "aarq_ln"):
        result = parser.parse(bytes.fromhex(FRAMES[name]))
        assert result["格式域"]["帧长校验"] == "与声明一致", (name, result["格式域"])
        warnings = [row for row in rows_of(FRAMES[name]) if str(row[0]) == "警告"]
        assert not warnings, (name, warnings)


# ── 9. 更多 APDU 分支（构造帧；每接一家厂商报文就补一条）──────────────────
def test_action_request_method_descriptor():
    # C3 <invoke> <class=0008 Clock> <obis=0000010000FF> <method=02> <参数个数=00>
    payload = bytes.fromhex("C30181" "0008" "0000010000FF" "02" "00")
    rows = rows_of(build_frame(LLC + payload))
    assert "Action-Request" in row_value(rows, "DLMS APDU")
    assert row_value(rows, "请求类型").startswith("普通"), row_value(rows, "请求类型")
    assert row_value(rows, "类ID").startswith("时钟（Clock）")
    assert row_value(rows, "方法ID (Method-ID)") == "2"


def test_action_response_normal():
    rows = rows_of(build_frame(LLC + bytes.fromhex("C701810000110A")))
    assert "Action-Response" in row_value(rows, "DLMS APDU")
    assert row_value(rows, "操作结果") == "成功"
    assert row_value(rows, "返回数据") == "10"


def test_glo_apdu_and_service_error_fallbacks():
    # 加密 APDU（glo-*）/ 确认服务错误 / 非确认写 / 信息报告：按原始字节展示即可，
    # 但名称必须是中文可读的名字，且绝不能崩（曾因 BER 误判把这几个标签当 BER 树拆碎）。
    cases = (
        ("C801810001000000" "0102030405060708", "Glo-Get-Request"),
        ("CC01810001" "00000002", "Glo-Get-Response"),
        ("0E010107", "Confirmed-Service-Error"),
        ("16018100" "00080000010000FF0200", "Unconfirmed-Write-Request"),
        ("18018100", "Information-Report-Request"),
    )
    for hexstr, expect in cases:
        rows = rows_of(build_frame(LLC + bytes.fromhex(hexstr)))
        assert expect in row_value(rows, "DLMS APDU"), (hexstr, rows)
        assert not any(str(row[0]).startswith("错误") for row in rows), (hexstr, rows)


def test_access_request_and_response():
    rows = rows_of(build_frame(LLC + bytes.fromhex("D901810001020304")))
    assert "Access-Request" in row_value(rows, "DLMS APDU")
    assert "暂按原始字节展示" in row_comment(rows, "Access 数据")
    rows = rows_of(build_frame(LLC + bytes.fromhex("DA0181000001")))
    assert "Access-Response" in row_value(rows, "DLMS APDU")


def test_bad_inputs_do_not_crash():
    for raw in (b"", b"\x7e", b"\x7e\xa0", b"\x00" * 4, bytes.fromhex("7EA00A000200")):
        rows = parser.parse_to_table(raw)
        assert isinstance(rows, list), raw
        result = parser.parse(raw)
        assert result["解析状态"] in ("成功", "失败"), (raw, result)
        if result["解析状态"] == "失败":
            assert result["错误信息"], (raw, result)


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
    raise SystemExit(1 if failed else 0)
