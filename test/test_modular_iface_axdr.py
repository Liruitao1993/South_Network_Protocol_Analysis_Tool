"""协议12 A-XDR 编解码单源（`modular_iface_axdr`）测试。

运行：
    pwshu '$env:PYTHONIOENCODING="utf-8"; python -u test/test_modular_iface_axdr.py'

本文件的断言刻意分成两类：
  1. **文档对拍**：协议12 表4/表5/表6~表12、附录 A 的 fcstab —— 逐条抄自文档；
  2. **独立 oracle**：同族标准 DL/T 698.45 的真实编码实例（`面向对象的用电信息数据交换协议
     (20210910).md` 附录 H.1.1「登录」与 H.3.2「读取多个对象属性」）——
     这些字节**不是**本模块 encode 出来的，能真正抓住「自证闭环」类假绿。
"""

import os
import re
import sys

import _path_setup  # noqa: E402,F401

from modular_iface_axdr import (  # noqa: E402
    APDU_TAGS,
    AXDR_LEN_FOR_FIXED_IN_CHOICE,
    AXDR_TAG_IN_SEQUENCE,
    AXDR_TYPES,
    AXDR_VAR_LENGTH_BYTES,
    DATA_CHOICE_TYPES,
    FCSTAB,
    AxdrError,
    apdu_self_check,
    calc_fcs,
    decode_apdu,
    decode_data_node,
    decode_sequence,
    decode_value,
    describe_value,
    encode_apdu,
    encode_channel_list,
    encode_data_item,
    encode_sequence,
    encode_value,
    format_date_time,
    frame_layout,
    pppfcs16,
    tag_of,
    type_name_of_tag,
    verify_frame,
    weekday_name,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n== {title} ==")


# ── 文档对拍数据（协议12 表4「通用数据类型定义」逐条）─────────────────

DOC_TYPES = {
    "NULL": 0,
    "array": 1,
    "structure": 2,
    "bool": 3,
    "bit-string": 4,
    "double-long": 5,
    "double-long-unsigned": 6,
    "octet-string": 9,
    "visible-string": 10,
    "UTF8-string": 12,
    "integer": 15,
    "long": 16,
    "unsigned": 17,
    "long-unsigned": 18,
    "long64": 20,
    "long64-unsigned": 21,
    "enum": 22,
    "float32": 23,
    "float64": 24,
    "date_time": 25,
    "date": 26,
    "time": 27,
    "date_time_s": 28,
    "DT": 80,
    "Scaler_Unit": 81,
}

#: 表4「定义」列里写了 SIZE(n) 的按 SIZE 取，其余取类型本身宽度
DOC_FIXED = {
    "NULL": 0,
    "bool": 1,
    "double-long": 4,
    "double-long-unsigned": 4,
    "integer": 1,
    "long": 2,
    "unsigned": 1,
    "long-unsigned": 2,
    "long64": 8,
    "long64-unsigned": 8,
    "enum": 1,
    "float32": 4,
    "float64": 8,
    "date_time": 10,  # octet-string(SIZE(10))
    "date": 5,  # SIZE(5)
    "time": 3,  # SIZE(3)
    "date_time_s": 7,  # SIZE(7)
    "DT": 2,  # ::= long-unsigned（表10）
    "Scaler_Unit": 2,  # SEQUENCE{integer, enum}（表12）
}

DOC_VAR_TYPES = ("array", "structure", "bit-string", "octet-string", "visible-string", "UTF8-string")

#: 附录 A.1 的 fcstab 抽样（原值按文档抄录；完整 256 项在文档存在时逐条对拍）
DOC_FCSTAB_SAMPLE = {
    0: 0x0000,
    1: 0x1189,
    50: 0x1291,
    100: 0x2522,
    127: 0x8B70,
    128: 0x8408,
    200: 0x4A44,
    254: 0x1EF1,
    255: 0x0F78,
}

DOC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "协议文档",
    "12.模组化功能协议",
    "模组化终端功能模块接口协议.md",
)


def doc_fcstab():
    """从协议12 文档现场抽取附录 A.1 的 fcstab（256 项）；文件缺失返回 None。"""
    if not os.path.exists(DOC_PATH):
        return None
    with open(DOC_PATH, encoding="utf-8") as fh:
        src = fh.read()
    i = src.find("fcstab")
    if i < 0:
        return None
    j = src.find("};", i)
    if j < 0:
        return None
    vals = [int(v, 16) for v in re.findall(r"0x[0-9a-fA-F]{4}", src[i:j])]
    return vals if len(vals) == 256 else None


# ── 图 4/8/10：A-XDR 层 ──────────────────────────────────────────────


def test_type_table():
    section("表4：通用数据类型与标记（25 类逐条）")
    check(
        "类型数量 = 25",
        len(AXDR_TYPES) == 25,
        str(len(AXDR_TYPES)),
    )
    check(
        "类型名集合与文档一致",
        set(AXDR_TYPES) == set(DOC_TYPES),
        str(sorted(set(AXDR_TYPES) ^ set(DOC_TYPES))),
    )
    for name, tag in DOC_TYPES.items():
        check(f"tag {name} = {tag}", tag_of(name) == tag, f"{tag_of(name)}")
    check(
        "tag → 类型名反向表",
        all(type_name_of_tag(t) == n for n, t in DOC_TYPES.items()),
    )
    for name, size in DOC_FIXED.items():
        check(
            f"定长 {name} = {size}B",
            AXDR_TYPES[name].fixed == size,
            str(AXDR_TYPES[name].fixed),
        )
    for name in DOC_VAR_TYPES:
        check(f"变长 {name}", AXDR_TYPES[name].fixed is None, str(AXDR_TYPES[name].fixed))
    check("Data CHOICE 覆盖 25 类（表5）", len(DATA_CHOICE_TYPES) == 25, str(len(DATA_CHOICE_TYPES)))
    check("APDU 标签（表13）8 类", APDU_TAGS == {
        "LinkRequest": 1,
        "GetRequest": 2,
        "SetRequest": 3,
        "ReportNotification": 4,
        "LinkResponse": 129,
        "GetResponse": 130,
        "SetResponse": 131,
        "ReportResponse": 132,
    }, str(APDU_TAGS))
    check("开关① 定长成员在 SEQUENCE 内不带 tag", AXDR_TAG_IN_SEQUENCE is False)
    check("开关② 定长分支不带长度域", AXDR_LEN_FOR_FIXED_IN_CHOICE is False)
    check("开关③ 变长长度域 1 字节", AXDR_VAR_LENGTH_BYTES == 1)


def test_oracle_698_login():
    section("独立 oracle：DL/T 698.45 附录 H.1.1「登录」的 date_time 逐字节")
    # 698 原文：07 E0 05 13 04 08 05 00 00 A4 —— 请求时间 2016-05-19 08:05:00:0164
    raw = bytes.fromhex("07E005130408050000A4")
    val, off = decode_value(raw, 0, "date_time", with_tag=False)
    check("偏移 = 10（定长裸排）", off == 10, str(off))
    check(
        "字段值（大端）",
        val
        == {
            "year": 2016,
            "month": 5,
            "day_of_month": 19,
            "day_of_week": 4,
            "hour": 8,
            "minute": 5,
            "second": 0,
            "milliseconds": 164,
        },
        str(val),
    )
    check("2016 是大端 07E0", val["year"] == 2016, f"{raw[0]:02X}{raw[1]:02X}")
    check("milliseconds 是大端 00A4", val["milliseconds"] == 164, f"{raw[8]:02X}{raw[9]:02X}")
    check("2016-05-19 是周四 → day_of_week=4", weekday_name(val["day_of_week"]) == "周四")
    check(
        "格式化文本与 698 原文一致",
        format_date_time(val, "date_time") == "2016-05-19 08:05:00.164",
        format_date_time(val, "date_time"),
    )
    check("date_time 定长 = octet-string(SIZE(10))", AXDR_TYPES["date_time"].fixed == 10)


def test_oracle_698_multi():
    section("独立 oracle：DL/T 698.45 附录 H.3.2「读取多个对象属性」的 array / double-long")
    # 698 原文：01 — 类型=1（数组）；03 — 数组元素个数=3；12 09 6D — long-unsigned 241.3V
    node, off = decode_data_node(bytes.fromhex("010312096D12096D12096D"), 0)
    check("数组类型", node.type_name == "array", node.type_name)
    check("长度域 = 元素个数 3（不是字节数）", len(node.children or []) == 3, str(len(node.children or [])))
    check("偏移 = 11（1 字节数组 tag + 1 字节个数 + 3×3 字节元素）", off == 11, str(off))
    check(
        "元素类型 long-unsigned",
        all(c.type_name == "long-unsigned" for c in node.children or []),
        str([c.type_name for c in node.children or []]),
    )
    check(
        "元素值 2413",
        all(c.value == 2413 for c in node.children or []),
        str([c.value for c in node.children or []]),
    )
    # 698 原文：05 00 00 03 E8 — 类型：5 double-long
    node2, off2 = decode_data_node(bytes.fromhex("05000003E8"), 0)
    check("double-long 大端", node2.value == 1000 and node2.type_name == "double-long", str(node2.value))
    check("double-long 偏移 5", off2 == 5, str(off2))


def test_encode_endianness():
    section("编码：多字节一律大端（铁证 1）")
    check(
        "180 → 00B4",
        encode_value(180, "long-unsigned", with_tag=False) == bytes.fromhex("00B4"),
        encode_value(180, "long-unsigned", with_tag=False).hex().upper(),
    )
    check(
        "2016 → 07E0",
        encode_value(2016, "long-unsigned", with_tag=False) == bytes.fromhex("07E0"),
        encode_value(2016, "long-unsigned", with_tag=False).hex().upper(),
    )
    check(
        "date_time 编码 = 698 原文",
        encode_value(
            {
                "year": 2016,
                "month": 5,
                "day_of_month": 19,
                "day_of_week": 4,
                "hour": 8,
                "minute": 5,
                "second": 0,
                "milliseconds": 164,
            },
            "date_time",
            with_tag=False,
        )
        == bytes.fromhex("07E005130408050000A4"),
    )
    check(
        "CHOICE 分支带 tag（定长不带长度域）",
        encode_value(180, "long-unsigned", with_tag=True) == bytes.fromhex("1200B4"),
        encode_value(180, "long-unsigned", with_tag=True).hex().upper(),
    )
    check(
        "SEQUENCE 内定长裸排（无 tag、无长度域）",
        encode_sequence([("long-unsigned", 180), ("unsigned", 7)]) == bytes.fromhex("00B407"),
        encode_sequence([("long-unsigned", 180), ("unsigned", 7)]).hex().upper(),
    )
    check(
        "变长类型在 SEQUENCE 内 = 长度 + 内容（无 tag）",
        encode_sequence([("visible-string", "ABC")]) == bytes.fromhex("03414243"),
        encode_sequence([("visible-string", "ABC")]).hex().upper(),
    )


def test_sequence_roundtrip():
    section("SEQUENCE 解码与文档定义一致（表6~表9 的字段顺序）")
    layout = [
        ("year", "long-unsigned"),
        ("month", "unsigned"),
        ("day_of_month", "unsigned"),
        ("day_of_week", "unsigned"),
        ("hour", "unsigned"),
        ("minute", "unsigned"),
        ("second", "unsigned"),
        ("milliseconds", "long-unsigned"),
    ]
    raw = bytes.fromhex("07E005130408050000A4")
    nodes, off = decode_sequence(raw, 0, layout)
    check("字段顺序与表6 完全一致", [n.name for n in nodes] == [n for n, _t in layout], str([n.name for n in nodes]))
    check("8 个成员", len(nodes) == 8)
    check("偏移 10", off == 10, str(off))
    check("year=2016", nodes[0].value == 2016)
    check("milliseconds=164", nodes[7].value == 164)


def test_scaler_unit():
    section("表12 Scaler_Unit（换算 integer + 单位 enum）")
    val, off = decode_value(bytes((0xFF, 5)), 0, "Scaler_Unit", with_tag=False)
    check("偏移 2", off == 2)
    check("换算 = -1（有符号 1B）", val == {"scaler": -1, "unit": 5}, str(val))
    check("描述含 10^-1", "10^-1" in describe_value(val, "Scaler_Unit"), describe_value(val, "Scaler_Unit"))
    val2, _ = decode_value(bytes((0x00, 0xFF)), 0, "Scaler_Unit", with_tag=False)
    check("换算 0 / 单位 255", val2 == {"scaler": 0, "unit": 255}, str(val2))


def test_bit_string():
    section("bit-string（内容 = 位宽 1B + 位组，位序 LSB-first）")
    raw = "02051A"  # 长度2：位宽 05，位组 0x1A
    val, off = decode_value(bytes.fromhex(raw), 0, "bit-string", with_tag=False)
    check("偏移 3", off == 3, str(off))
    check("位宽 5", val["bits"] == 5, str(val["bits"]))
    check("置位 = bit1/bit3/bit4（LSB-first）", val["set"] == [1, 3, 4], str(val["set"]))
    enc = encode_value({"bits": 5, "data": b"\x1a"}, "bit-string", with_tag=False)
    check("编码可逆", enc == bytes.fromhex(raw), enc.hex().upper())
    # 附录 G.3：遥信状态 bit0 表示第一路 → bit0 是最低位
    v2, _ = decode_value(bytes.fromhex("020101"), 0, "bit-string", with_tag=False)
    check("bit0 是 LSB（第一路）", v2["set"] == [0], str(v2["set"]))


def test_errors():
    section("越界 / 截断：唯一异常类型 AxdrError（不返回半成品）")
    try:
        decode_value(bytes.fromhex("07E0"), 0, "date_time", with_tag=False)
        check("date_time 截断应抛错", False)
    except AxdrError as exc:
        check("date_time 截断抛 AxdrError", True, exc.message)
        check("消息含字段类型与所需字节", "date_time" in exc.message and "10" in exc.message, exc.message)
    try:
        decode_value(bytes.fromhex("0A03"), 0, "visible-string", with_tag=False)
        check("变长长度越界应抛错", False)
    except AxdrError as exc:
        check("变长长度越界抛 AxdrError", True, exc.message)
    try:
        decode_value(bytes.fromhex("12"), 0, "long-unsigned", with_tag=True)
        check("标签不匹配应抛错", False)
    except AxdrError as exc:
        check("标签不匹配抛 AxdrError", True, exc.message)
    try:
        decode_data_node(bytes.fromhex("7F00"), 0)
        check("未知 Data 标签应抛错", False)
    except AxdrError as exc:
        check("未知 Data 标签抛 AxdrError", True, exc.message)
    # decode_apdu 必须把 consumed 换算成「相对 APDU 起点」并带上 partial
    try:
        decode_apdu(bytes.fromhex("0101" + "4142"), 0)
        check("APDU 截断应抛错", False)
    except AxdrError as exc:
        check("APDU 截断抛 AxdrError", True, exc.message)
        check("consumed 相对 APDU 起点", exc.consumed >= 1, str(exc.consumed))
        check("partial 带上已解字段", isinstance(exc.partial, list) and len(exc.partial) >= 1, str(exc.partial))


def test_apdu_roundtrip():
    section("8 类 APDU（表13~表21）编解码闭环")
    cases = [
        ("LinkRequest", dict(fields=[1, "TERMINAL", "T0001", 256, 256, 1])),
        ("GetRequest", dict(dt=0x0000)),
        ("SetRequest", dict(dt=0x0100, data_value={"year": 2026, "month": 9, "day_of_month": 23,
                                                  "day_of_week": 3, "hour": 10, "minute": 30,
                                                  "second": 0, "milliseconds": 0}, data_type="date_time")),
        ("ReportNotification", dict(dt=0x0003, data_value=1, data_type="enum")),
        ("LinkResponse", dict(fields=[1, "MODULE", "M0001", 256, 256, 1], channels=((1, 0), (2, 2)))),
        ("GetResponse", dict(dt=0x0000, data_value=[("visible-string", "X")], data_type="structure")),
        ("GetResponse", dict(dt=0x0000, dar=2)),
        ("SetResponse", dict(dt=0x0000, dar=0)),
        ("ReportResponse", dict(dt=0x0003)),
    ]
    for name, kwargs in cases:
        apdu = encode_apdu(name, **kwargs)
        check(f"{name} 首个字节 = CHOICE 标签", apdu[0] == APDU_TAGS[name], f"0x{apdu[0]:02X}")
        nodes, consumed = decode_apdu(apdu, 0)
        check(
            f"{name} 完整消费（axdr_tail = 0）",
            consumed == len(apdu),
            f"{consumed}/{len(apdu)}",
        )
        check(f"{name} 解出 APDU 类型名", nodes[0].value == name, str(nodes[0].value))
    # DT 大端（GetRequest）
    gq = encode_apdu("GetRequest", dt=0x0000)
    check("GetRequest 数据域 = 02 00 00", gq == bytes.fromhex("020000"), gq.hex().upper())
    check(
        "GetRequest 的 DT 在 SEQUENCE 内是裸 2 字节大端",
        gq[1:] == bytes.fromhex("0000"),
        gq[1:].hex().upper(),
    )
    # Get-Result 两分支（表19）
    n1, _ = decode_apdu(encode_apdu("GetResponse", dt=0x0000, dar=1), 0)
    dar_node = next(n for n in n1 if n.type_name == "DAR")
    check("Get-Result[0] DAR", dar_node.value == 1, str(dar_node.value))
    n2, _ = decode_apdu(encode_apdu("GetResponse", dt=0x0000, data_value=7, data_type="unsigned"), 0)
    data_node = next(n for n in n2 if n.type_name == "unsigned")
    check("Get-Result[1] Data", data_node.value == 7, str(data_node.value))
    # 虚拟通道工作模式（表18）：个数(1B) + N×(接口类型, 功能配置)
    ch = encode_channel_list(((1, 0), (2, 2)))
    check("通道列表编码 = 02 0100 0202", ch == bytes.fromhex("0201000202"), ch.hex().upper())
    lr = encode_apdu("LinkResponse", fields=[1, "M", "M1", 256, 256, 1], channels=((1, 0),))
    nodes3, end3 = decode_apdu(lr, 0)
    ch_node = next(n for n in nodes3 if n.type_name == "channel-list")
    check("通道列表解出 1 项", len(ch_node.children or []) == 1, str(len(ch_node.children or [])))
    check("通道项 = 管理通道", ch_node.children[0].value == {"iface": 1, "config": 0}, str(ch_node.children[0].value))
    check("LinkResponse 完整消费", end3 == len(lr), f"{end3}/{len(lr)}")


def test_fcs_doc_oracle():
    section("附录 A：fcstab / pppfcs16 / calc_fcs")
    check("FCSTAB 256 项", len(FCSTAB) == 256, str(len(FCSTAB)))
    for idx, want in DOC_FCSTAB_SAMPLE.items():
        check(f"fcstab[{idx}] = 0x{want:04X}", FCSTAB[idx] == want, f"0x{FCSTAB[idx]:04X}")
    doc = doc_fcstab()
    if doc is None:
        print("  [SKIP] 文档未找到，跳过 fcstab 全表对拍")
    else:
        bad = [i for i, (a, b) in enumerate(zip(FCSTAB, doc)) if a != b]
        check("fcstab 与文档全表逐条一致（256 项）", not bad, f"不一致下标 {bad[:8]}")
    # PPP 自证：把 FCS 追加到报文末尾后，累计值应等于 0xF0B8
    payload = bytes.fromhex("0B000201020000")
    fcs = calc_fcs(payload)
    check(
        "pppfcs16(报文 + FCS) == 0xF0B8（附录 A.1 GoodFCS）",
        pppfcs16(payload + fcs.to_bytes(2, "little")) == 0xF0B8,
        hex(pppfcs16(payload + fcs.to_bytes(2, "little"))),
    )
    check("calc_fcs = ~pppfcs16", calc_fcs(payload) == (pppfcs16(payload) ^ 0xFFFF))
    try:
        import crcmod.predefined  # type: ignore

        x25 = crcmod.predefined.mkCrcFun("x-25")
        for probe in (b"", b"\x00", b"abc", payload, bytes(range(64))):
            check(
                f"与 crcmod x-25 一致（{probe.hex()[:12] or '空'}）",
                calc_fcs(probe) == x25(probe),
                f"0x{calc_fcs(probe):04X} vs 0x{x25(probe):04X}",
            )
    except ImportError:
        print("  [SKIP] crcmod 未安装，跳过交叉验证")


def test_frame_layout_and_verify():
    section("frame_layout / verify_frame")
    mid = b"\x00\x00" + bytes((0x40, 0x01))  # DIR=0 PRM=1 控制码=00 FID=1，数据域空
    ack = b"\x68" + mid + calc_fcs(mid).to_bytes(2, "little") + b"\x16"
    check("ACK 整帧 = 8 字节", len(ack) == 8, str(len(ack)))
    lay = frame_layout(ack)
    check("start_ok", lay["start_ok"] is True)
    check("length_ok（L=0 → 整帧 8）", lay["length_ok"] is True, str(lay["declared_l"]))
    check("end_ok", lay["end_ok"] is True)
    check("fcs_ok", lay["fcs_ok"] is True)
    check("structure_ok", lay["structure_ok"] is True)
    check("ok", lay["ok"] is True, str(lay["errors"]))
    check("control.code = 0x00", lay["control"]["code"] == 0x00)
    v = verify_frame(ack)
    check("verify_frame ok", v["ok"] is True, str(v))
    check("ACK 无 APDU ⇒ axdr_tail = None", v["axdr_tail"] is None, str(v["axdr_tail"]))

    # 坏 FCS
    bad = bytearray(ack)
    bad[-2] ^= 0xFF
    lay_bad = frame_layout(bytes(bad))
    check("坏 FCS → fcs_ok False", lay_bad["fcs_ok"] is False)
    check("坏 FCS → ok False（structure 仍 True）", lay_bad["structure_ok"] is True and lay_bad["ok"] is False)

    # 保留位非 0
    mid_r = bytes.fromhex("0010") + bytes((0x40, 0x01))  # L 小端 0x1000 ⇒ bit12 置位
    fr_r = b"\x68" + mid_r + calc_fcs(mid_r).to_bytes(2, "little") + b"\x16"
    lay_r = frame_layout(fr_r)
    check("保留位非 0 → 标记", lay_r["reserved_bits_nonzero"] is True)
    check("保留位非 0 → ok False", lay_r["ok"] is False, str(lay_r["errors"]))

    # 长度不符（多 3 字节）
    lay_long = frame_layout(ack + b"\xAA\xBB\xCC")
    check("长度不符 → length_ok False", lay_long["length_ok"] is False)
    check("长度不符 → 仍给出 payload", lay_long["payload"] == b"")

    # 被截断的信息帧：仍能定位实际帧尾的 FCS
    apdu = encode_apdu("GetRequest", dt=0x0000)
    mid2 = len(apdu).to_bytes(2, "little") + bytes((0x42, 0x01)) + apdu
    fr2 = b"\x68" + mid2 + calc_fcs(mid2).to_bytes(2, "little") + b"\x16"
    truncated = fr2[:-1]  # 丢一字节
    lay_t = frame_layout(truncated)
    check("截断 → length_ok False", lay_t["length_ok"] is False)
    check("截断 → 结束符不在声明位置", lay_t["end_ok"] is False)
    check("截断 → 仍能按实际帧尾定位 FCS", lay_t["fcs_usable"] is True, str(lay_t["fcs_offset"]))
    check("截断 → fcs_ok 仍可为真（FCS 字段完整）", lay_t["fcs_ok"] is True)
    check("截断 → ok False", lay_t["ok"] is False)

    # APDU 尾部多余字节 ⇒ axdr_tail != 0（编码假设的判据）
    mid3 = (len(apdu) + 1).to_bytes(2, "little") + bytes((0x42, 0x01)) + apdu + b"\x99"
    fr3 = b"\x68" + mid3 + calc_fcs(mid3).to_bytes(2, "little") + b"\x16"
    v3 = verify_frame(fr3)
    check("APDU 尾部多余 → axdr_tail = 1", v3["axdr_tail"] == 1, str(v3["axdr_tail"]))
    check("APDU 尾部多余 → ok False", v3["ok"] is False, str(v3["reason"]))

    sci = apdu_self_check(apdu)
    check("apdu_self_check 自洽", sci["axdr_tail"] == 0 and sci["apdu_name"] == "GetRequest", str(sci))


def test_choice_tag_paths():
    section("Data CHOICE：定长/变长/嵌套结构")
    # 变长（octet-string）在 CHOICE 里带 tag + 长度
    check(
        "octet-string CHOICE = 09 03 AABBCC",
        encode_data_item("octet-string", bytes.fromhex("AABBCC")) == bytes.fromhex("0903AABBCC"),
        encode_data_item("octet-string", bytes.fromhex("AABBCC")).hex().upper(),
    )
    # structure：长度域 = 成员个数，成员各自带 tag
    st = encode_data_item("structure", [("unsigned", 1), ("visible-string", "AB")])
    check("structure = 02 02 11 01 0A 02 41 42", st == bytes.fromhex("020211010A024142"), st.hex().upper())
    node, off = decode_data_node(st, 0)
    check("structure 成员 2 个", len(node.children or []) == 2, str(len(node.children or [])))
    check("成员1 unsigned = 1", node.children[0].value == 1)
    check("成员2 visible = AB", node.children[1].value == b"AB")
    check("偏移 = 8", off == 8, str(off))
    # NULL
    check("NULL CHOICE = 00", encode_data_item("NULL", None) == b"\x00")
    # 浮点
    f32, _ = decode_value(encode_data_item("float32", 1.5)[1:], 0, "float32", with_tag=False)
    check("float32 往返 1.5", abs(f32 - 1.5) < 1e-6, str(f32))


def main():
    test_type_table()
    test_oracle_698_login()
    test_oracle_698_multi()
    test_encode_endianness()
    test_sequence_roundtrip()
    test_scaler_unit()
    test_bit_string()
    test_errors()
    test_apdu_roundtrip()
    test_fcs_doc_oracle()
    test_frame_layout_and_verify()
    test_choice_tag_paths()

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
