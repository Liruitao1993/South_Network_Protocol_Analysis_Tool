# -*- coding: utf-8 -*-
"""Reflex Web 版协议组帧纯逻辑测试（独立脚本，直接 `python test_web_frame_gen_utils.py`）。

核心断言：同一输入下 `reflex_web/frame_gen_utils.py` 产出字节 == GUI 生成器产出字节。
覆盖：collect→generate 字节一致（南网/国网）、自定义模板、A-XDR、SA 特征字节。
"""


import _path_setup  # noqa: E402

import sys
from pathlib import Path

ROOT = _path_setup._ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "reflex_web"))

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def test_parse_field_value():
    print("== parse_field_value ==")
    from frame_gen_utils import parse_field_value
    check("uint8 hex", parse_field_value("0x10", {"type": "uint8"}) == 0x10)
    check("uint8 dec", parse_field_value("16", {"type": "uint8"}) == 16)
    check("uint16 empty", parse_field_value("", {"type": "uint16"}) == 0)
    check("bytes str", parse_field_value("1f40", {"type": "bytes"}) == "1f40")
    check("oi hex", parse_field_value("0x0000", {"type": "oi"}) == 0)
    check("enum", parse_field_value("3", {"type": "enum"}) == 3)


def test_collect_south():
    """南网：配置运行参数 E8 02 04 74（含 list/count_type + enum/bytes）"""
    print("== collect→generate 南网字节一致 ==")
    from send_frame_lib import ProtocolFrameGenerator, DI_FIELD_SCHEMA
    from frame_gen_utils import collect_field_values

    di_key = (0xE8, 0x02, 0x04, 0x74)
    gen = ProtocolFrameGenerator()
    schema = DI_FIELD_SCHEMA[di_key]
    fields = schema["fields"]

    # 位置对齐：gen_field_values / gen_list_rows / gen_sub_fields
    gen_field_values = []
    gen_sub_fields = []
    gen_list_rows = []
    for f in fields:
        gen_field_values.append(str(f.get("default", "")))
        gen_sub_fields.append([str(s.get("default", "")) for s in f.get("sub_fields", [])])
        gen_list_rows.append([])

    # 定位站点MAC/参数列表字段索引
    mac_i = next(i for i, f in enumerate(fields) if f["name"] == "站点MAC地址")
    rows_i = next(i for i, f in enumerate(fields) if f["name"] == "参数列表")
    gen_field_values[mac_i] = "111111111111"
    # 参数列表：2 行，每行 item_fields 顺序与 schema 一致
    item_fields = fields[rows_i]["item_fields"]
    gen_list_rows[rows_i] = [
        [str(it.get("default", "")) for it in item_fields],
        [str(it.get("default", "")) for it in item_fields],
    ]

    # 用纯函数收集
    field_values = collect_field_values(fields, gen_field_values, gen_list_rows, gen_sub_fields)

    # 用 GUI 生成器直接生成（同输入手工构造）
    gui_values = {}
    gui_values["站点MAC地址"] = "111111111111"
    item_fields = fields[rows_i]["item_fields"]
    gui_items = []
    for _ in range(2):
        gui_items.append({it["name"]: it.get("default") for it in item_fields})
    gui_values["参数列表"] = gui_items

    src = bytes.fromhex("000000000000")
    dst = bytes.fromhex("000000000000")
    frame_pure = gen.generate_frame(di_key, field_values, src_addr=src, dst_addr=dst, dir_flag=0, prm=1, add_flag=1)
    frame_gui = gen.generate_frame(di_key, gui_values, src_addr=src, dst_addr=dst, dir_flag=0, prm=1, add_flag=1)
    check("南网字节一致", frame_pure == frame_gui, f"pure={frame_pure.hex()} gui={frame_gui.hex()}")


def test_collect_south_sub():
    """南网：添加任务（含 sub_fields 位域）——父值由生成器 Pass3 打包"""
    print("== collect→generate 南网 sub_fields 字节一致 ==")
    from send_frame_lib import ProtocolFrameGenerator, DI_FIELD_SCHEMA
    from frame_gen_utils import collect_field_values

    di_key = (0xE8, 0x02, 0x02, 0x01)
    gen = ProtocolFrameGenerator()
    schema = DI_FIELD_SCHEMA[di_key]
    fields = schema["fields"]
    gen_field_values = [str(f.get("default", "")) for f in fields]
    gen_sub_fields = []
    gen_list_rows = []
    for f in fields:
        gen_sub_fields.append([str(s.get("default", "")) for s in f.get("sub_fields", [])])
        gen_list_rows.append([])

    # 任务模式字 有 sub_fields —— 设置子值
    mode_i = next(i for i, f in enumerate(fields) if f["name"] == "任务模式字")
    # 任务响应标识=1, 转发标识=1, 优先级=0 → 父值 = 1<<7 | 1<<6 = 0xC0
    gen_sub_fields[mode_i] = ["1", "1", "0", "0"]

    # 报文内容 有 sub_fields（业务代码 + 报文有效内容），且业务代码有 condition 依赖转发标识
    content_i = next(i for i, f in enumerate(fields) if f["name"] == "报文内容")
    gen_sub_fields[content_i] = ["1", "30313233"]  # 业务代码=1(DLMS), 内容="0123"

    field_values = collect_field_values(fields, gen_field_values, gen_list_rows, gen_sub_fields)

    # GUI 参考：父值由生成器 Pass3 从子值打包，报文内容由子字段拼接
    gui_values = {}
    gui_values["任务ID"] = 0
    gui_values["超时时间"] = 30
    gui_values["任务响应标识"] = 1
    gui_values["转发标识"] = 1
    gui_values["保留"] = 0
    gui_values["任务优先级"] = 0
    gui_values["业务代码"] = 1
    gui_values["报文有效内容"] = "30313233"

    src = bytes.fromhex("000000000000")
    dst = bytes.fromhex("000000000000")
    frame_pure = gen.generate_frame(di_key, field_values, src_addr=src, dst_addr=dst, dir_flag=0, prm=1, add_flag=1)
    frame_gui = gen.generate_frame(di_key, gui_values, src_addr=src, dst_addr=dst, dir_flag=0, prm=1, add_flag=1)
    check("sub_fields 字节一致", frame_pure == frame_gui, f"pure={frame_pure.hex()} gui={frame_gui.hex()}")


def test_generate_custom_data():
    """自定义模板字节：uint16 小端 + checksum 回填"""
    print("== generate_custom_data ==")
    from frame_gen_utils import generate_custom_data
    templates = [
        {"name": "n1", "length": 2, "ftype": "uint16", "endian": "little", "display": "hex", "value": "1F40"},
        {"name": "cs", "length": 1, "ftype": "checksum", "endian": "little", "display": "hex", "value": ""},
    ]
    data = generate_custom_data(templates)
    # 0x1F40 小端 = 40 1F；校验和 = (0x40+0x1F)&0xFF = 0x5F
    check("custom 字节", data.hex() == "401f5f", f"got={data.hex()}")


def test_build_dlt698_sa():
    """698.45 SA 特征字节"""
    print("== build_dlt698_sa ==")
    from frame_gen_utils import build_dlt698_sa
    check("广播", build_dlt698_sa(3, 0, 0, "").hex() == "aa")
    check("普通", build_dlt698_sa(0, 0, 6, "010203040506").hex() == "05060504030201")


def test_axdr_and_apdu():
    """A-XDR 编码与 APDU 组装"""
    print("== A-XDR / APDU ==")
    from frame_gen_utils import encode_axdr_items, build_dlt698_axdr_apdu
    from dl_t698_45_axdr import AXDRCoder
    check("uint8 编码", encode_axdr_items([{"tag": 0x11, "type": "unsigned", "value": 1, "length": 0}]).hex() == "1101",
          f"={encode_axdr_items([{'tag':0x11,'type':'unsigned','value':1,'length':0}]).hex()}")
    check("AXDRCoder 一致", encode_axdr_items([{"tag": 0x11, "type": "unsigned", "value": 1, "length": 0}]) == AXDRCoder().encode(1, 0x11))
    # 复合 structure: tag 0x02 + length + children
    items = [{"tag": 0x02, "type": "structure", "value": 0, "length": 0, "children": [
        {"tag": 0x11, "type": "unsigned", "value": 1, "length": 0},
        {"tag": 0x11, "type": "unsigned", "value": 2, "length": 0},
    ]}]
    check("structure 编码", encode_axdr_items(items).hex() == "020411011102", f"={encode_axdr_items(items).hex()}")
    # GET-Request get_normal APDU
    apdu = build_dlt698_axdr_apdu("GET-Request", "get_normal", 0x0F, "0000",
                                  {"属性标识": 2, "索引": 0}, b"\x11\x01", False)
    check("GET APDU", apdu.hex() == "05010f00000200110100", f"={apdu.hex()}")
    # custom
    apdu2 = build_dlt698_axdr_apdu("_custom_", "", 0x05, "", {}, b"\x11\x01", True)
    check("custom APDU", apdu2.hex() == "0501051101", f"={apdu2.hex()}")


def test_collect_gdw():
    """国网：从节点列表（含 list + count_field）"""
    print("== collect→generate 国网字节一致 ==")
    from gdw_send_frame_lib import GDWFrameGenerator, GDW_AFNFN_SCHEMA
    from frame_gen_utils import collect_field_values

    afn, fn = 0x11, 0x01  # 从节点列表
    gen = GDWFrameGenerator()
    schema = GDW_AFNFN_SCHEMA.get((afn, fn))
    if not schema:
        check("国网 schema 存在", False, f"({afn:02X},{fn}) 无 schema")
        return
    fields = schema["fields"]

    gen_field_values = [str(f.get("default", "")) for f in fields]
    gen_sub_fields = []
    gen_list_rows = []
    for f in fields:
        gen_sub_fields.append([str(s.get("default", "")) for s in f.get("sub_fields", [])])
        gen_list_rows.append([])

    # 找 list 字段并加 2 行
    for i, f in enumerate(fields):
        if f.get("type") == "list":
            item_fields = f["item_fields"]
            gen_list_rows[i] = [
                [str(it.get("default", "")) for it in item_fields],
                [str(it.get("default", "")) for it in item_fields],
            ]

    field_values = collect_field_values(fields, gen_field_values, gen_list_rows, gen_sub_fields)

    # GUI 直接构造
    gui_values = {}
    for i, f in enumerate(fields):
        if f.get("type") == "list":
            item_fields = f["item_fields"]
            gui_values[f["name"]] = [{it["name"]: it.get("default") for it in item_fields},
                                     {it["name"]: it.get("default") for it in item_fields}]
        else:
            gui_values[f["name"]] = f.get("default")

    info_config = {
        "dir": 0, "prm": 1, "通信方式": 3, "路由标识": 0, "附属节点标识": 0,
        "通信模块标识": 1, "冲突检测": 0, "中继级别": 0, "纠错编码标识": 0,
        "信道标识": 0, "预计应答字节数": 0, "通信速率": 0, "速率单位标识": 0, "报文序列号": 0,
    }
    frame_pure = gen.generate_frame(afn, fn, field_values, info_config,
                                    src_addr="000000000000", dst_addr="000000000000")
    frame_gui = gen.generate_frame(afn, fn, gui_values, info_config,
                                   src_addr="000000000000", dst_addr="000000000000")
    check("国网字节一致", frame_pure == frame_gui, f"pure={frame_pure.hex()} gui={frame_gui.hex()}")


def test_69845_predefined():
    """698.45 predefined 组帧（复用生成器）"""
    print("== 698.45 predefined ==")
    from dl_t698_45_frame_gen import DLT69845FrameGenerator
    from dl_t698_45_frame_schema import DLT69845_FIELD_SCHEMA
    from frame_gen_utils import collect_field_values, build_dlt698_sa

    apdu_type, sub_type = "GET-Request", "get_normal"
    schema = DLT69845_FIELD_SCHEMA.get((apdu_type, sub_type), {})
    fields = schema.get("fields", [])
    gen_field_values = [str(f.get("default", "")) for f in fields]
    gen_sub_fields = [[str(s.get("default", "")) for s in f.get("sub_fields", [])] for f in fields]
    gen_list_rows = [[] for _ in fields]
    field_values = collect_field_values(fields, gen_field_values, gen_list_rows, gen_sub_fields)

    gen = DLT69845FrameGenerator()
    sa = build_dlt698_sa(0, 0, 6, "010203040506")
    frame = gen.generate_frame(apdu_type, sub_type, field_values, sa=sa, ca=0,
                               dir_bit=0, prm_bit=1, seg_bit=0, sc_bit=0, func_code=3)
    check("698.45 生成非空", len(frame) > 0, f"len={len(frame)}")


def test_collect_gdw_fujian():
    """福建增补（1.14.0）：52H-F1 透明转发（length_field 自动计算）+ 55H-F2 list 字段"""
    print("== collect→generate 福建增补字节一致 ==")
    from gdw_send_frame_lib import GDWFrameGenerator, GDW_AFNFN_SCHEMA
    from frame_gen_utils import collect_field_values
    from gdw10376_parser import GDW10376Parser

    gen = GDWFrameGenerator()
    parser = GDW10376Parser()
    info_config = {
        "dir": 0, "prm": 1, "通信方式": 3, "路由标识": 0, "附属节点标识": 0,
        "通信模块标识": 1, "冲突检测": 0, "中继级别": 0, "纠错编码标识": 0,
        "信道标识": 0, "预计应答字节数": 0, "通信速率": 0, "速率单位标识": 0, "报文序列号": 1,
    }

    # 52H-F1 透明转发：length_field 自动计算报文长度
    afn, fn = 0x52, 0x01
    schema = GDW_AFNFN_SCHEMA.get((afn, fn))
    check("福建增补 52H-F1 schema 存在", schema is not None, "")
    fields = schema["fields"]
    gen_field_values = ["1", "001122334455", "0", "1", "10", "", "68AABB"]
    gen_sub_fields = [[] for _ in fields]
    gen_list_rows = [[] for _ in fields]
    field_values = collect_field_values(fields, gen_field_values, gen_list_rows, gen_sub_fields)
    frame = gen.generate_frame(afn, fn, field_values, info_config,
                               src_addr="000000000001", dst_addr="001122334455")
    rows = parser.parse_to_table(frame)
    lens = [r for r in rows if "报文长度" in str(r[0])]
    check("52H-F1 报文长度自动计算=3", bool(lens) and lens[0][2] == "3", f"{lens}")

    # 55H-F2 允许/禁止上报：list 字段
    afn, fn = 0x55, 0x02
    schema = GDW_AFNFN_SCHEMA.get((afn, fn))
    check("福建增补 55H-F2 schema 存在", schema is not None, "")
    fields = schema["fields"]
    gen_field_values = ["1"]
    gen_list_rows = [[], [["1", "001122334455", "1"]]]
    gen_sub_fields = [[] for _ in fields]
    field_values = collect_field_values(fields, gen_field_values, gen_list_rows, gen_sub_fields)
    frame = gen.generate_frame(afn, fn, field_values, info_config,
                               src_addr="000000000001", dst_addr="001122334455")
    rows = parser.parse_to_table(frame)
    check("55H-F2 list 字段回读", any("对象1事件上报状态标志" in str(r[0]) for r in rows), "")


def test_eb_lookup_web():
    """Web 查询页 EB 数据标识查询（协议7 + EB 关键词）"""
    print("== Web EB 数据标识查询 ==")
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reflex_web"))
    from reflex_web.lookup_utils import get_lookup_data, _is_eb_query

    check("EB 判定 EB030002", _is_eb_query(7, "EB030002") is True, "")
    check("EB 判定 非EB", _is_eb_query(7, "F1") is False, "")
    data = get_lookup_data(7, "EB030110")
    check("EB030110 查询 1 条", len(data) == 1, f"len={len(data)}")
    check("EB030110 名称", bool(data) and "台区识别" in data[0].get("名称", ""), "")
    all_eb = get_lookup_data(7, "EB")
    check("EB 全部 ≥40 条", len(all_eb) >= 40, f"len={len(all_eb)}")
    # AFN 查询回归（含福建增补）
    afn_data = get_lookup_data(7, "")
    fujian = [r for r in afn_data if str(r.get("AFN", "")).startswith("5")]
    check("AFN 查询含福建增补", len(fujian) >= 27, f"fujian={len(fujian)}")


def test_eb_645_generator():
    """EB 数据标识 645 帧生成器：选 EB 标识+控制码+数据 → 完整 645 帧（含 CS）+ 填入报文内容"""
    print("== EB 645 帧生成器 ==")
    import os
    os.environ['PYTEST_CURRENT_TEST'] = 'x'
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reflex_web"))
    import importlib
    from reflex_web.reflex_web import State

    s = State()
    s.load_eb_di_options()
    check("EB 选项加载 ≥50", len(s.eb_di_options) >= 50, f"len={len(s.eb_di_options)}")

    # EB030002 停上电事件（控制码 81 主动上报 + 数据）
    s.set_eb_di('EB030002')
    s.set_eb_ctrl('81')
    s.set_eb_data('01 01 11 22 33 44 55 66')
    s.gen_eb_645_frame()
    frame = s.gen_eb_frame
    check("645 帧生成非空", bool(frame), "")
    b = bytes.fromhex(frame)
    check("645 帧结构 68..68..16", b[0] == 0x68 and b[7] == 0x68 and b[-1] == 0x16, "")
    cs_calc = sum(b[8:-2]) & 0xFF
    check("645 帧 CS 正确", b[-2] == cs_calc, f"CS={b[-2]:02X} expect={cs_calc:02X}")
    check("EB030002 字节序", b[10:14] == bytes.fromhex('EB030002'), b[10:14].hex())

    # 填入 52H-F1 报文内容字段
    s.set_protocol('7')
    s.set_gen_afn_fn('5201')
    s.apply_eb_frame_to_content()
    idx = [i for i, m in enumerate(s.gen_field_meta) if m.get('name') == '报文内容']
    check("找到报文内容字段", len(idx) == 1, f"idx={idx}")
    check("645 帧填入报文内容", idx and s.gen_field_values[idx[0]] == frame, "")


def test_eb_698_apdu():
    """EB 数据标识 698.45 APDU 生成（附件1 V3.42 698 承载格式）"""
    print("== EB 698 APDU 生成 ==")
    import os
    os.environ['PYTEST_CURRENT_TEST'] = 'x'
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reflex_web"))
    from frame_gen_utils import build_eb_698_apdu

    # 对照附件1 文档 698 示例（逐字节一致）
    tests = [
        ("EB030110", "SET-Request", "000005", False, "06020001EB030110090300000500"),
        ("EB030110", "ACTION-Request", "", False, "07020001EB0301100000"),
        ("EB030110", "ACTION-Response", "010005", False, "87020001EB0301100009030100050000"),
        ("EB030002", "REPORT-Notification", "0001112233445566", False, "88010001EB03000201090800011122334455660000"),
        ("EB030002", "REPORT-Response", "", False, "08010001EB03000200"),
        ("EB030110", "SET-Response", "", False, "86020001EB030110000000"),
        ("EB030110", "SET-Response", "", True, "86020001EB030110FF0000"),
    ]
    for di, svc, data, deny, expected in tests:
        got = build_eb_698_apdu(di, svc, data, deny).hex().upper()
        check(f"698 {svc} {di} 与文档一致", got == expected, f"got={got}")

    # GET 服务（读取）
    apdu_get = build_eb_698_apdu("EB030501", "GET-Request")
    check("698 GET-Request", apdu_get.hex().upper() == "05020001EB0305010000", apdu_get.hex())
    apdu_getr = build_eb_698_apdu("EB030501", "GET-Response", "260825101530")
    check("698 GET-Response", apdu_getr.hex().upper() == "85020001EB0305010009062608251015300000", apdu_getr.hex())

    # 对象配置：属性/方法/索引/PIID/单多对象
    apdu_attr = build_eb_698_apdu("EB030110", "GET-Request", piid=1, choice="one", attr_no=5, index=2)
    check("698 自定义属性 one", apdu_attr.hex().upper() == "050101EB0305020000", apdu_attr.hex())
    apdu_omd = build_eb_698_apdu("EB030110", "ACTION-Request", method=1, mode=2)
    check("698 ACTION OMD", apdu_omd.hex().upper() == "07020001EB0301020000", apdu_omd.hex())

    # State 集成：698 APDU 填入报文内容（关闭字段表单，走自由 hex → 完整帧）
    from reflex_web.reflex_web import State
    s = State()
    s.load_eb_di_options()
    s.set_protocol('7')
    s.set_gen_afn_fn('5201')
    s.set_eb_format('698')
    s.set_eb_di('EB030110')
    s.set_eb_698_service('SET-Request')
    s.set_eb_698_use_field('0')  # 自由 hex 模式
    s.set_eb_698_data('00 00 05')
    s.gen_eb_645_frame()
    # 完整帧以 68 开头，内嵌 APDU 06 02 00 01 EB030110 090300000500
    frame_lower = s.gen_eb_frame.lower()
    check("698 完整帧生成", frame_lower.startswith('68') and frame_lower.endswith('16'), s.gen_eb_frame)
    check("698 完整帧含 APDU+OAD", '06020001eb030110090300000500' in frame_lower, frame_lower)
    s.apply_eb_frame_to_content()
    idx = [i for i, m in enumerate(s.gen_field_meta) if m.get('name') == '报文内容']
    check("698 完整帧填入报文内容", idx and s.gen_field_values[idx[0]] == s.gen_eb_frame, "")


def test_eb_698_full_frame():
    """EB 数据标识 698.45 完整帧（68 链路层封装）+ 字段配置数据内容"""
    print("== EB 698 完整帧 + 字段配置 ==")
    import os
    os.environ['PYTEST_CURRENT_TEST'] = 'x'
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reflex_web"))
    from frame_gen_utils import build_eb_698_frame
    from dl_t698_45_frame_gen import DLT69845FrameGenerator
    from gdw_eb_di_fields import encode_eb_di_data, EB_DI_FIELDS

    # 字段编码（附件1 定义）
    check("EB030002 字段编码", encode_eb_di_data('EB030002', {'停上电类型': 1, '本次上报数量': 1, '模块地址列表': [{'模块地址': '112233445566'}]}).hex() == '0101112233445566', "")
    check("EB030110 字段编码", encode_eb_di_data('EB030110', {'台区识别方法': 0, '识别时长(分钟)': 5}).hex() == '000500', "")
    check("字段定义 ≥40 项", len(EB_DI_FIELDS) >= 40, f"len={len(EB_DI_FIELDS)}")

    # 完整帧组装
    from frame_gen_utils import build_dlt698_sa
    sa = build_dlt698_sa(0, 0, 6, "000000000000")
    frame_bytes = build_eb_698_frame("EB030110", "SET-Request", "000005",
                                     sa=sa, ca=0, dir_bit=0, prm_bit=1, func_code=3)
    if isinstance(frame_bytes, bytes):
        b = frame_bytes
        frame = frame_bytes.hex()
    else:
        b = bytes.fromhex(frame_bytes)
        frame = frame_bytes
    check("698 完整帧 68..16", b[0] == 0x68 and b[-1] == 0x16, "")
    check("控制域 0x43", b[3] == 0x43, f"{b[3]:02X}")
    # HCS/FCS 校验
    gen = DLT69845FrameGenerator()
    check("HCS 校验", gen._calc_crc(b[1:12]) == b[12:14], "")
    check("FCS 校验", gen._calc_crc(b[1:-3]) == b[-3:-1], "")
    # APDU 内嵌 EB OAD（帧: 68 LL C SA(7) CA(1) HCS(2) APDU FCS(2) 16 → APDU = b[14:-3]）
    apdu = b[14:-3]
    check("APDU 含 EB OAD", apdu.hex().upper().find('EB030110') >= 0, apdu.hex())
    # 长度域 = 长度域自身2 + 控制域1 + SA7 + CA1 + HCS2 + APDU + FCS2 → 帧长-2
    length = int.from_bytes(b[1:3], 'little') & 0x3FFF
    check("长度域 = 帧长-2", length == len(b) - 2, f"{length} vs {len(b)-2}")

    # State 集成：字段表单 → 完整帧 → 填入 52H-F1 报文内容
    from reflex_web.reflex_web import State
    s = State()
    s.load_eb_di_options()
    s.set_protocol('7')
    s.set_gen_afn_fn('5201')
    s.set_eb_format('698')
    s.set_eb_di('EB030002')
    check("字段表单加载", s.eb_di_field_use and len(s.eb_di_fields) == 3, f"fields={len(s.eb_di_fields)}")
    s.set_eb_field(0, '1')   # 模块上电
    s.set_eb_field(1, '1')   # 数量 1
    s.add_eb_list_row(2)
    s.set_eb_list_cell(2, 0, 0, '112233445566')
    s.set_eb_698_service('REPORT-Notification')
    s.gen_eb_645_frame()
    b2 = bytes.fromhex(s.gen_eb_frame)
    check("字段配置 698 完整帧", b2[0] == 0x68 and b2[-1] == 0x16, "")
    check("字段编码入 APDU", b2[14:-3].hex().upper().find('0101112233445566') >= 0, "")
    s.apply_eb_frame_to_content()
    idx = [i for i, m in enumerate(s.gen_field_meta) if m.get('name') == '报文内容']
    check("698 完整帧填入报文内容", idx and s.gen_field_values[idx[0]] == s.gen_eb_frame, "")


if __name__ == "__main__":
    test_parse_field_value()
    test_collect_south()
    test_collect_south_sub()
    test_generate_custom_data()
    test_build_dlt698_sa()
    test_axdr_and_apdu()
    test_collect_gdw()
    test_69845_predefined()
    test_collect_gdw_fujian()
    test_eb_lookup_web()
    test_eb_645_generator()
    test_eb_698_apdu()
    test_eb_698_full_frame()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)