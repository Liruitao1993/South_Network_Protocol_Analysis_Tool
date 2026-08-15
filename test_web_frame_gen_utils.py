# -*- coding: utf-8 -*-
"""Reflex Web 版协议组帧纯逻辑测试（独立脚本，直接 `python test_web_frame_gen_utils.py`）。

核心断言：同一输入下 `reflex_web/frame_gen_utils.py` 产出字节 == GUI 生成器产出字节。
覆盖：collect→generate 字节一致（南网/国网）、自定义模板、A-XDR、SA 特征字节。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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


if __name__ == "__main__":
    test_parse_field_value()
    test_collect_south()
    test_collect_south_sub()
    test_generate_custom_data()
    test_build_dlt698_sa()
    test_axdr_and_apdu()
    test_collect_gdw()
    test_69845_predefined()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)