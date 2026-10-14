# -*- coding: utf-8 -*-
"""协议13（依瓦定制645）**组帧 + 预设命令库**测试（纯逻辑，无 Qt 依赖运行时）。

运行（本机 console 默认 GBK，需 UTF-8）：
    pwshu '$env:PYTHONIOENCODING="utf-8"; python test/test_yw645_frame_gen.py'

覆盖（对应 prd R4 / R6 / AC8 / AC9 / D1~D5）：
1. 模式表与 with_fl 推导（含写模式占位禁用生成、不臆造 0x50/0x60）；
2. 地址边界：>12 取低 12 / <12 高位补 0 / 广播 AA×6 / 含非数字报错；
3. 模板 oracle：与文档示例 X3/X9 逐字节吻合；每条模板组帧 → 解析 valid=True 且 CS 通过；
4. 报错矩阵：数据域 >0xFFF、地址非数字、返回形态数据项为空、FL 与数据长度不一致；
5. 组帧 ↔ 解析闭环（AC8）：读模式1/读模式2/透传模式1/透传模式2 四类各一条；
6. 预设隔离（AC9）：`_get_path("yw645")` → `YW645_command.json`；写入时不触碰
   `GW_command.json` / `DLT645_command.json`（AGENTS 陷阱 65 事故护栏）；
7. 种子文件 `YW645_command.json` 与 `FRAME_TEMPLATES` **同源**（逐条重算对拍）；
8. 单源守卫：组帧页/组帧器的数据项表就是 `yw645_di.DI_TABLE`（无第二份手写表）。
"""

import json
import pathlib
import shutil
import sys
import tempfile

import _path_setup  # noqa: E402,F401

import preset_buttons as pb  # noqa: E402
import yw645_di  # noqa: E402
import yw645_frame_gen as fg  # noqa: E402
import yw645_wire as W  # noqa: E402
from preset_buttons import PresetButtonManager  # noqa: E402
from yw645_parser import YW645Parser  # noqa: E402

PASS = 0
FAIL = 0
ROOT = pathlib.Path(__file__).resolve().parent.parent


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


def raises_build(fn):
    try:
        fn()
    except fg.YW645BuildError:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


def hexc(text: str) -> str:
    return "".join(text.split()).upper()


# ── 1. 模式表与 with_fl 推导 ─────────────────────────────────────────


def test_modes():
    section("模式表与 with_fl 推导")
    check("4 个已定义模式命令码",
          fg.MODE_CODES == {"read_req": 0x10, "read_rsp": 0x20,
                            "pass_req": 0x30, "pass_rsp": 0x40, "write": None},
          str(fg.MODE_CODES))
    check("写模式为占位 None（文档未定义，不臆造）", fg.MODE_CODES["write"] is None)
    check("MODE_OPTIONS 无 0x50/0x60 推测值",
          all(code not in (0x50, 0x60) for _k, code, _l in fg.MODE_OPTIONS))
    check("mode_code(read_req)=0x10", fg.mode_code("read_req") == 0x10)
    check("mode_code(read_rsp)=0x20", fg.mode_code("read_rsp") == 0x20)
    check("mode_code(pass_req)=0x30", fg.mode_code("pass_req") == 0x30)
    check("mode_code(pass_rsp)=0x40", fg.mode_code("pass_rsp") == 0x40)
    check("写模式取命令码 → 抛可读错误", raises_build(lambda: fg.mode_code("write")))
    try:
        fg.mode_code("write")
        msg = ""
    except fg.YW645BuildError as exc:
        msg = str(exc)
    check("写模式错误提示含「未定义」与「不推测」",
          "未定义" in msg and "0x50" in msg, msg[:60])

    check("read_req 推导不带 FL", fg.with_fl_for_mode("read_req") is False)
    check("pass_req 推导不带 FL", fg.with_fl_for_mode("pass_req") is False)
    check("read_rsp 推导带 FL", fg.with_fl_for_mode("read_rsp") is True)
    check("pass_rsp 推导带 FL", fg.with_fl_for_mode("pass_rsp") is True)
    check("显式 with_fl 覆盖推导（read_req + True）",
          fg.with_fl_for_mode("read_req", True) is True)
    check("显式 with_fl 覆盖推导（read_rsp + False）",
          fg.with_fl_for_mode("read_rsp", False) is False)
    check("写模式无法推导 → 抛错", raises_build(lambda: fg.with_fl_for_mode("write")))
    check("未知模式 → 抛错", raises_build(lambda: fg.mode_code("nope")))


# ── 2. 地址边界 ──────────────────────────────────────────────────────


def test_address():
    section("地址边界（高字节在前）")
    check("103000000010 → 10 30 00 00 00 10",
          W.encode_addr12("103000000010").hex().upper() == "103000000010")
    check("45000000013（11 位）高位补 0 → 04 50 00 00 00 13",
          W.encode_addr12("45000000013").hex().upper() == "045000000013")
    check("13 位取低 12 位",
          W.encode_addr12("1234567890123") == W.encode_addr12("234567890123"))
    frame = fg.build_frame(addr="1234567890123", mode="read_req", items=[{"id": "0010"}])
    check(">12 位组帧地址 = 低 12 位", frame[1:7].hex().upper() == "234567890123")
    frame = fg.build_frame(addr="123", mode="read_req", items=[{"id": "0010"}])
    check("<12 位组帧地址高位补 0", frame[1:7].hex().upper() == "000000000123",
          frame[1:7].hex().upper())
    frame = fg.build_frame(addr=W.BROADCAST_ADDR, mode="read_req", items=[{"id": "0010"}])
    check("广播地址 AA×6", frame[1:7] == W.BROADCAST_ADDR)
    check("地址含非数字 → 抛可读错误",
          raises_build(lambda: fg.build_frame(addr="12A", mode="read_req", items=[{"id": "0010"}])))
    check("地址为 6 字节 bytes 时直接采用",
          fg.build_frame(addr=b"\x01\x02\x03\x04\x05\x06", mode="read_req",
                         items=[{"id": "0010"}])[1:7] == b"\x01\x02\x03\x04\x05\x06")
    check("地址 bytes 长度不对 → 抛错",
          raises_build(lambda: fg.build_frame(addr=b"\x01\x02", mode="read_req", items=[])))


# ── 3. 模板与 oracle ─────────────────────────────────────────────────


def test_templates():
    section("模板与文档示例 oracle")
    check("模板数 ≥5", len(fg.FRAME_TEMPLATES) >= 5, str(len(fg.FRAME_TEMPLATES)))
    check("模板 key 唯一",
          len({t["key"] for t in fg.FRAME_TEMPLATES}) == len(fg.FRAME_TEMPLATES))
    check("模板覆盖 读设备类型/读设备号/批量读/透传请求/透传返回",
          {"read_dev_type", "read_dev_id", "read_batch", "pass_req", "pass_rsp"}.issubset(
              set(fg.template_keys())))

    # 文档给出 CS 的两条透传示例，逐字节吻合
    check("模板 pass_req == 文档 X3",
          fg.build_from_template("pass_req").hex().upper() == "680450000000136830023714B416",
          fg.build_from_template("pass_req").hex().upper())
    check("模板 pass_rsp == 文档 X9",
          fg.build_from_template("pass_rsp").hex().upper() == "681030000000106840023713AC16",
          fg.build_from_template("pass_rsp").hex().upper())

    # 读模式示例（X1）是「未加 0x33」的展示形态 ⇒ 组帧输出为规范形态（数据域 +0x33），
    # 数据域减 0x33 后应与 X1 的数据域逐字节一致。
    f = fg.build_from_template("read_batch")
    data = f[W.HEADER_LEN:W.HEADER_LEN + W.len_from_cmd(f[8], f[9])]
    check("模板 read_batch 数据域减 0x33 == X1 的 00 10 00 20",
          W.unmask_data(data).hex().upper() == "00100020", W.unmask_data(data).hex().upper())
    check("模板 read_batch 命令/长度 == X1（0x10 / 0x04）", (f[8], f[9]) == (0x10, 0x04))
    check("模板 read_batch 地址 == X1 广播", f[1:7] == W.BROADCAST_ADDR)

    # 每条模板组帧 → 解析闭环
    for key in fg.template_keys():
        frame = fg.build_from_template(key)
        parser = YW645Parser()
        parser.parse(frame)
        meta = parser.last_meta
        check(f"模板 {key} 组帧→解析 valid=True", meta["valid"] is True,
              f"valid={meta['valid']} cs_ok={meta['cs_ok']} len_ok={meta['length_ok']}")
        check(f"模板 {key} CS 校验通过", meta["cs_ok"] is True)
        check(f"模板 {key} 长度域自洽", meta["declared_len"] == meta["actual_len"])
        check(f"模板 {key} 结构自洽", W.is_frame(frame))

    # 地址覆盖
    f = fg.build_from_template("pass_req", addr="45000000013")
    check("build_from_template 支持覆盖地址", f[1:7].hex().upper() == "045000000013")
    check("未知模板 → 抛可读错误", raises_build(lambda: fg.build_from_template("nope")))
    check("template_state 可回灌 Widget.apply_state 的结构",
          set(fg.template_state("read_batch")) >=
          {"addr", "broadcast", "mode", "with_fl", "items", "body", "write_cmd"})


# ── 4. 报错矩阵 ──────────────────────────────────────────────────────


def test_error_matrix():
    section("报错矩阵（可读中文，不静默截断）")
    big = "11" * 0x1000  # 4096 字节 > 0xFFF
    check("数据域 4096 字节 → 抛错（12bit 上限 4095）",
          raises_build(lambda: fg.build_frame(addr="1", mode="pass_req", body=big)))
    try:
        fg.build_frame(addr="1", mode="pass_req", body=big)
        msg = ""
    except fg.YW645BuildError as exc:
        msg = str(exc)
    check("超限错误提示含 4095/0xFFF", "4095" in msg and "0xFFF" in msg, msg[:70])
    check("超限错误提示含 D4 处置说明（不截断）", "不截断" in msg, msg[:90])
    ok = "11" * 0xFFF
    check("数据域恰 4095 字节 → 允许生成",
          len(fg.build_frame(addr="1", mode="pass_req", body=ok)) == 0xFFF + 12)

    check("地址含非数字 → 抛错",
          raises_build(lambda: fg.build_frame(addr="abc", mode="read_req", items=[{"id": "0010"}])))
    check("返回形态数据项无数据 → 抛错",
          raises_build(lambda: fg.build_frame(addr="1", mode="read_rsp",
                                              items=[{"id": "0010", "data": ""}])))
    check("返回形态数据项缺 data 键 → 抛错",
          raises_build(lambda: fg.build_frame(addr="1", mode="read_rsp", items=[{"id": "0010"}])))
    check("FL 与数据长度不一致 → 抛错",
          raises_build(lambda: fg.build_frame(addr="1", mode="read_rsp",
                                              items=[{"id": "0010", "data": "0102", "fl": "1"}])))
    check("FL 与数据长度一致 → 通过",
          not raises_build(lambda: fg.build_frame(addr="1", mode="read_rsp",
                                                  items=[{"id": "0010", "data": "0102", "fl": "2"}])))
    check("ID 非 2 字节 → 抛错",
          raises_build(lambda: fg.build_frame(addr="1", mode="read_req", items=[{"id": "10"}])))
    check("未知模式 → 抛错",
          raises_build(lambda: fg.build_frame(addr="1", mode="nope", items=[])))
    check("写模式无命令码 → 抛错（不臆造）",
          raises_build(lambda: fg.build_frame(addr="1", mode="write", body="1122")))
    check("写模式 + 手填命令码 → 可生成",
          fg.build_frame(addr="1", mode="write", body="1122", cmd_override=0x50)[8] & 0xF0 == 0x50)


# ── 5. 组帧 ↔ 解析闭环（AC8：四类模式）──────────────────────────────


def test_roundtrip():
    section("组帧↔解析闭环（AC8：四类模式各一条）")
    cases = [
        ("读模式请求(0x10)", dict(addr="103000000010", mode="read_req",
                                items=[{"id": "0010"}, {"id": "0020"}])),
        ("读模式返回(0x20)", dict(addr="103000000010", mode="read_rsp",
                                items=[{"id": "0010", "data": "01"},
                                       {"id": "0020", "data": "103000000010"}])),
        ("透传模式请求(0x30)", dict(addr="45000000013", mode="pass_req", body="04E1")),
        ("透传模式返回(0x40)", dict(addr="103000000010", mode="pass_rsp", body="04E0")),
    ]
    for name, kwargs in cases:
        frame = fg.build_frame(**kwargs)
        parser = YW645Parser()
        parser.parse(frame)
        meta = parser.last_meta
        check(f"{name} 闭环 valid=True", meta["valid"] is True,
              f"frame={frame.hex().upper()} valid={meta['valid']} cs_ok={meta['cs_ok']}")
        check(f"{name} 闭环 CS 通过", meta["cs_ok"] is True)
        check(f"{name} 闭环长度自洽", meta["declared_len"] == meta["actual_len"])
        check(f"{name} 闭环地址一致",
              meta["addr"].lstrip("0") == kwargs["addr"].lstrip("0") or meta["is_broadcast"])
    print("      闭环实测：")
    for name, kwargs in cases:
        frame = fg.build_frame(**kwargs)
        parser = YW645Parser()
        parser.parse(frame)
        m = parser.last_meta
        print(f"        {name}: {frame.hex().upper()}  valid={m['valid']} cs_ok={m['cs_ok']}"
              f" mode={m['mode_name']} decl={m['declared_len']}")


# ── 6. 预设隔离（AC9）────────────────────────────────────────────────


def test_preset_isolation():
    section("预设隔离（AC9：YW645_command.json 独立，不污染 GW/DLT645）")
    check("_get_path('yw645') == YW645_COMMAND_PATH",
          pb._get_path("yw645") == pb.YW645_COMMAND_PATH)
    check("路径文件名 = YW645_command.json",
          pb.YW645_COMMAND_PATH.name == "YW645_command.json")
    check("路径经 app_paths.data_path 定位（与 NW 同目录）",
          pb.YW645_COMMAND_PATH.parent == pb.NW_COMMAND_PATH.parent)
    check("yw645 在 set_protocol 支持列表", "yw645" in pb.SUPPORTED_PROTOCOLS)
    check("显示名 = 依瓦定制645", pb.PROTOCOL_DISPLAY.get("yw645") == "依瓦定制645")

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="yw645_preset_"))
    saved = (pb.YW645_COMMAND_PATH, pb.GW_COMMAND_PATH,
             pb.DLT645_COMMAND_PATH, pb.MODULAR_COMMAND_PATH)
    try:
        pb.YW645_COMMAND_PATH = tmp / "YW645_command.json"
        pb.GW_COMMAND_PATH = tmp / "GW_command.json"
        pb.DLT645_COMMAND_PATH = tmp / "DLT645_command.json"
        pb.MODULAR_COMMAND_PATH = tmp / "MODULAR_command.json"
        pb.GW_COMMAND_PATH.write_text('{"commands":[{"id":"gw-sentinel"}]}', encoding="utf-8")
        pb.DLT645_COMMAND_PATH.write_text('{"commands":[{"id":"d645-sentinel"}]}', encoding="utf-8")
        gw_before = pb.GW_COMMAND_PATH.read_bytes()
        d645_before = pb.DLT645_COMMAND_PATH.read_bytes()

        ok = PresetButtonManager.add_command(
            "yw645",
            {"button_name": "测试项", "group_name": "读模式", "protocol": "yw645",
             "frame_hex": "68 AA AA AA AA AA AA 68 10 02 33 43 54 16"},
        )
        check("add_command('yw645') 返回 True", ok is True)
        check("YW645_command.json 已写入", pb.YW645_COMMAND_PATH.exists())
        loaded = PresetButtonManager.load_commands("yw645")
        check("YW645 预设可读回 1 条", len(loaded) == 1, str(len(loaded)))
        check("GW_command.json 未被创建/修改", pb.GW_COMMAND_PATH.read_bytes() == gw_before)
        check("DLT645_command.json 未被创建/修改",
              pb.DLT645_COMMAND_PATH.read_bytes() == d645_before)
        check("MODULAR_command.json 未被创建", not pb.MODULAR_COMMAND_PATH.exists())
        check("预设按钮可取完整帧（frame_hex 非空且可解析）",
              bool(loaded[0].get("frame_hex")) and
              W.is_frame(bytes.fromhex(hexc(loaded[0]["frame_hex"]))))
    finally:
        (pb.YW645_COMMAND_PATH, pb.GW_COMMAND_PATH,
         pb.DLT645_COMMAND_PATH, pb.MODULAR_COMMAND_PATH) = saved
        shutil.rmtree(tmp, ignore_errors=True)
    check("模块路径常量已还原", pb.YW645_COMMAND_PATH.name == "YW645_command.json")


# ── 7. 种子文件同源 ──────────────────────────────────────────────────


def test_seed_file():
    section("YW645_command.json 种子与 FRAME_TEMPLATES 同源")
    path = ROOT / "YW645_command.json"
    check("种子文件存在", path.exists(), str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    commands = data.get("commands", [])
    check("种子条数 == 模板数", len(commands) == len(fg.FRAME_TEMPLATES),
          f"{len(commands)} vs {len(fg.FRAME_TEMPLATES)}")
    check("全部条目 protocol=yw645", all(c.get("protocol") == "yw645" for c in commands))
    by_key = {c["config"]["yw645"].get("template_key"): c for c in commands}
    for tmpl in fg.FRAME_TEMPLATES:
        key = tmpl["key"]
        entry = by_key.get(key)
        check(f"种子含模板 {key}", entry is not None)
        if entry is None:
            continue
        rebuilt = fg.build_from_template(key).hex().upper()
        check(f"种子 {key} frame_hex 与模板重算一致",
              hexc(entry["frame_hex"]) == rebuilt, entry["frame_hex"])
        parsed = YW645Parser()
        parsed.parse(bytes.fromhex(hexc(entry["frame_hex"])))
        check(f"种子 {key} 帧可解析且 CS 通过",
              parsed.last_meta["valid"] is True and parsed.last_meta["cs_ok"] is True)
    check("预设覆盖 读设备类型/读设备号/批量读/透传请求/透传返回",
          {"read_dev_type", "read_dev_id", "read_batch", "pass_req", "pass_rsp"}.issubset(
              set(by_key)))
    check("种子全部帧均带数据域 +0x33（规范线形态）",
          all(W.is_frame(bytes.fromhex(hexc(c["frame_hex"]))) for c in commands))


# ── 8. 单源守卫 ──────────────────────────────────────────────────────


def test_single_source():
    section("单源守卫（无第二份手写表）")
    import yw645_frame_gen_widget as gw

    check("组帧页数据项表就是 yw645_di.DI_TABLE（同一对象）",
          gw.DI_TABLE is yw645_di.DI_TABLE)
    src = (ROOT / "yw645_frame_gen.py").read_text(encoding="utf-8")
    check("组帧器不自己拼帧（无 0x68 硬编码帧尾拼接）",
          "FRAME_START" not in src and "0x16" not in src)
    check("组帧器 import yw645_wire（编码单源）", "import yw645_wire as W" in src)
    wsrc = (ROOT / "yw645_frame_gen_widget.py").read_text(encoding="utf-8")
    check("组帧页 import yw645_frame_gen（无第二份编码）",
          "import yw645_frame_gen as fg" in wsrc)
    check("组帧页不直接拼帧（不出现 encode_frame）", "encode_frame" not in wsrc)


def main():
    test_modes()
    test_address()
    test_templates()
    test_error_matrix()
    test_roundtrip()
    test_preset_isolation()
    test_seed_file()
    test_single_source()

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
