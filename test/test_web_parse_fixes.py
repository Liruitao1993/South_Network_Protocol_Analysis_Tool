# -*- coding: utf-8 -*-
"""Reflex Web 版解析 P0 修复回归测试（2026-09-15，任务 09-15-web-parse-p0-fixes）

覆盖（与 prd.md 验收 1 的 a~j 对应）：
  1. hex_to_bytes_strict：奇数长度/空输入报错，不再静默截断
  2. batch_frame_status：❌ 行在表中途也判失败；空表判失败
  3. apply_strip_once：同一输入只剥离一次（连点两次解析不再二次裁剪）
  4. parse_kwargs_for：协议9/10/11 的级别参数（含 pb_only 的 frame_type 下发）
  5. 解析级别/物理块帧类型选项单一来源（协议9 含 mac_only）
  6. ED 广西台体（gx 8B 公共头）自动识别 + 双布局业务偏移正确
  7. 协议10 pb_only：frame_type 生效（无则「未知(None)」）
  8. 查询页：南网 AFN=DI1、协议10 用自有表、698 属性/方法列有值
  9. 校验器工厂对 12 协议可用（Web _get_validator 委托 protocol_registry）
 10. 报文工具 CRC-24 与解析器同口径（CRC-32 已等价，勿改）

直接运行: PYTHONIOENCODING=utf-8 python test/test_web_parse_fixes.py
"""

import _path_setup  # noqa: E402

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reflex_web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from reflex_web import lookup_utils, web_utils  # noqa: E402

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


def expect_error(name, fn, keyword):
    try:
        fn()
    except ValueError as e:
        check(name, keyword in str(e), f"实际错误: {e}")
    except Exception as e:  # noqa: BLE001
        check(name, False, f"异常类型错误: {type(e).__name__}: {e}")
    else:
        check(name, False, "未抛异常")


# ═══════════════════════════════════════════════════════════════
# ED..EE 包装帧构造（测试夹具）
# ═══════════════════════════════════════════════════════════════

def _wrap_ed(data: bytes, ctrl1: int = 0x00, ctrl2: int = 0x02) -> bytes:
    """ED+帧长(2,LE)+ctrl1+ctrl2+EF+data+CS+EE"""
    body = bytes([ctrl1, ctrl2, 0xEF]) + data
    frame_len = len(body) + 1
    head = bytes([0xED, frame_len & 0xFF, frame_len >> 8]) + body
    return head + bytes([sum(head) & 0xFF, 0xEE])


def _build_gx(business: bytes, pb_len: int = 136) -> bytes:
    """广西台体：数据域公共头 8 字节 = 时间戳(4)+物理信道(1)+物理块个数(1)+物理块长度(2)"""
    data = (
        (0x11223344).to_bytes(4, "little")
        + bytes([0x01])            # 物理信道 HPLC
        + bytes([0x01])            # 物理块个数
        + pb_len.to_bytes(2, "little")
        + business
    )
    return _wrap_ed(data)


def _build_plc2(business: bytes, pb_len: int = 136) -> bytes:
    """PLC2.0：数据域公共头 9 字节 = 物理信道(1)+时间戳(4)+物理块个数(1)+CRC(1)+物理块长度(2)"""
    data = (
        bytes([0x01])              # 物理信道 HPLC
        + (0x11223344).to_bytes(4, "little")
        + bytes([0x01, 0x00])      # 物理块个数 + Payload CRC
        + pb_len.to_bytes(2, "little")
        + business
    )
    return _wrap_ed(data)


# ═══════════════════════════════════════════════════════════════
# 1~5. web_utils 纯函数
# ═══════════════════════════════════════════════════════════════

def test_hex_to_bytes_strict():
    print("\n[1] hex_to_bytes_strict（严格清洗）")
    check("偶数长度正常转换",
          web_utils.hex_to_bytes_strict("68 11 01 01 01") == bytes.fromhex("6811010101"))
    check("0x 前缀支持",
          web_utils.hex_to_bytes_strict("0x68,0x11") == bytes.fromhex("6811"))
    expect_error("奇数长度报错（不静默截断）",
                 lambda: web_utils.hex_to_bytes_strict("681101010"), "奇数")
    expect_error("空输入报错", lambda: web_utils.hex_to_bytes_strict("  "), "报文为空")


def test_batch_frame_outcome():
    print("\n[2] batch_frame_outcome（失败判定全表扫描 + 类型/摘要列）")
    mid = [
        ("── 信标帧载荷（仅MAC帧模式）──", "", "", "", None, None),
        ("解析模式", "", "仅MAC帧", "", None, None),
        ("❌ 解析失败", "", "", "帧长度不足", None, None),
    ]
    st, tp, sm = web_utils.batch_frame_outcome(mid, "命令帧")
    check("表中途 ❌ 行 → 失败", st == "失败", f"status={st}")
    check("失败类型列固定为「解析失败」（与桌面同列语义）", tp == "解析失败", tp)
    check("失败摘要取 ❌ 行说明", sm == "帧长度不足", sm)
    st2, tp2, sm2 = web_utils.batch_frame_outcome(
        [("帧类型", "", "0", "命令帧", 0, 0)], "命令帧")
    check("正常表 → 成功", st2 == "成功", f"status={st2}")
    check("成功时类型/摘要用解析摘要", tp2 == "命令帧" and sm2 == "命令帧", f"{tp2}/{sm2}")
    st3, _, sm3 = web_utils.batch_frame_outcome([], "命令帧")
    check("空表 → 失败（与桌面统一）", st3 == "失败", f"status={st3}")
    check("空表摘要可读", "未产出字段" in sm3, sm3)
    st4, _, _ = web_utils.batch_frame_outcome(
        [("❌ 单跳MAC帧头不完整", "", "", "", None, None)], "x")
    check("非「解析失败」字样的 ❌ 行也判失败", st4 == "失败")


def test_strip_frame_bytes():
    print("\n[3] strip_frame_bytes（剔除：同一输入恒定结果）")
    raw = bytes.fromhex("0102030405")
    check("未配置剔除 → 原样返回", web_utils.strip_frame_bytes(raw, 0, 0) == raw)
    check("剔除前1+尾1", web_utils.strip_frame_bytes(raw, 1, 1) == bytes.fromhex("020304"))
    check("仅尾剔除", web_utils.strip_frame_bytes(raw, 0, 2) == bytes.fromhex("010203"))
    check("重复调用结果一致（重复点击解析不二次裁剪）",
          web_utils.strip_frame_bytes(raw, 1, 1) == web_utils.strip_frame_bytes(raw, 1, 1))
    expect_error("剔除超界报错",
                 lambda: web_utils.strip_frame_bytes(raw, 9, 9), "剔除")


def test_parse_kwargs_for():
    print("\n[4] parse_kwargs_for（级别参数下发）")
    k10 = web_utils.parse_kwargs_for(10, "pb_only", gw_frame_type=2, channel="plc")
    check("协议10 pb_only 下发 frame_type", k10.get("frame_type") == 2, str(k10))
    check("协议10 pb_only 带 parse_level/channel",
          k10.get("parse_level") == "pb_only" and k10.get("channel") == "plc", str(k10))
    k10a = web_utils.parse_kwargs_for(10, "auto", gw_frame_type=2, channel="plc")
    check("协议10 auto 不下发 frame_type", "frame_type" not in k10a, str(k10a))
    k11 = web_utils.parse_kwargs_for(11, "pb_only", gw_frame_type=0, channel="hrf")
    check("协议11 pb_only 下发 frame_type 与通道",
          k11.get("frame_type") == 0 and k11.get("channel") == "hrf", str(k11))
    k9 = web_utils.parse_kwargs_for(9, "mac_only", pb_frame_type="beacon", channel="auto")
    check("协议9 pb_frame_type 下发",
          k9.get("pb_frame_type") == "beacon" and k9.get("parse_level") == "mac_only", str(k9))
    check("其他协议无附加参数", web_utils.parse_kwargs_for(0, "pb_only") == {})


def test_option_constants():
    print("\n[5] 解析级别/帧类型选项单一来源")
    csg_levels = [o["value"] for o in web_utils.CSG_PARSE_LEVEL_OPTIONS]
    check("协议9 级别含 mac_only", "mac_only" in csg_levels, str(csg_levels))
    check("协议9 级别含 fc_efc", "fc_efc" in csg_levels)
    gw_levels = [o["value"] for o in web_utils.GW_PARSE_LEVEL_OPTIONS]
    check("协议10/11 级别含 pb_only/fc_mac",
          "pb_only" in gw_levels and "fc_mac" in gw_levels, str(gw_levels))
    csg_pb = [o["value"] for o in web_utils.CSG_PB_FRAME_TYPE_OPTIONS]
    check("协议9 PB 帧类型 4 项", set(csg_pb) == {"sof", "beacon", "sack", "net"}, str(csg_pb))
    gw_pb = [o["value"] for o in web_utils.GW_PB_FRAME_TYPE_OPTIONS]
    check("协议10/11 PB 帧类型 4 项", set(gw_pb) == {"0", "1", "2", "3"}, str(gw_pb))


# ═══════════════════════════════════════════════════════════════
# 6. ED 广西台体自动识别 + 双布局
# ═══════════════════════════════════════════════════════════════

def test_ed_wrapper_detection_and_layout():
    print("\n[6] ED 广西台体（gx）自动识别与业务偏移")
    from csg_new_gen_parser import CSGNewGenParser, detect_ed_wrapper

    # 业务帧：FC 首字节 bit3=1（接入指示）+ 定界符，长度 = 16 + 1*136（PB 自洽打分命中）
    business = bytes([0x0B]) + bytes((i & 0xFF) for i in range(15 + 136))
    gx, plc2 = _build_gx(business), _build_plc2(business)

    check("gx 帧识别为 gx", detect_ed_wrapper(gx) == "gx", detect_ed_wrapper(gx))
    check("plc2 帧识别为 plc2", detect_ed_wrapper(plc2) == "plc2", detect_ed_wrapper(plc2))
    check("非 ED 帧回退 fallback",
          detect_ed_wrapper(b"\x68\x01\x02\x03", fallback="gx") == "gx")

    parser = CSGNewGenParser()
    rows_auto = parser.parse_to_table(gx)  # 不传 ed_wrapper → 自动识别
    first = str(rows_auto[0][0])
    fields = {str(r[0]): r for r in rows_auto}
    check("自动识别后标题为广西台体包装头",
          first == "── 广西台体监控包装头 ──", first)
    check("gx 物理信道按 8B 头解析（data[4]=0x01 HPLC）",
          fields["物理信道"][2] == "HPLC", str(fields.get("物理信道")))
    check("gx 时间戳按 8B 头解析（data[0:4]）",
          fields["时间戳"][2] == str(0x11223344), str(fields.get("时间戳")))
    check("gx 单个物理块长度 = 136",
          fields["单个物理块长度"][1] == "136", str(fields.get("单个物理块长度")))
    check("gx 无 Payload CRC 行（8B 头无该字节）", "Payload CRC" not in fields)

    # 同帧按 plc2 布局解析 → 字段错位（证明格式判别确实改变结果）
    rows_wrong = CSGNewGenParser().parse_to_table(gx, ed_wrapper="plc2")
    wrong_fields = {str(r[0]): r for r in rows_wrong}
    check("gx 帧按 plc2 布局解析会错位（物理信道非 HPLC）",
          wrong_fields["物理信道"][1] == "0x44",
          str(wrong_fields.get("物理信道")))

    # 业务帧偏移不变式：ED 表「业务帧」之后的行 == 直接解析业务帧
    idx = next(i for i, r in enumerate(rows_auto) if str(r[0]).startswith("── 业务帧"))
    ed_biz = [(r[0], r[1], r[2], r[3]) for r in rows_auto[idx + 1:]]
    direct = [(r[0], r[1], r[2], r[3]) for r in CSGNewGenParser().parse_to_table(business)]
    check("gx 业务帧解析结果 == 直接解析业务帧（无 1 字节错位）",
          ed_biz == direct, f"ED={len(ed_biz)}行 direct={len(direct)}行")

    # 摘要消费者识别两种包装头
    sm_gx = web_utils.get_frame_summary(rows_auto, 9)
    check("gx 摘要体现广西台体包装", "广西台体监控包装" in sm_gx, sm_gx)
    sm_plc2 = web_utils.get_frame_summary(CSGNewGenParser().parse_to_table(plc2), 9)
    check("plc2 摘要体现 PLC2.0 包装", "PLC2.0" in sm_plc2 or "ED监控包装" in sm_plc2, sm_plc2)


# ═══════════════════════════════════════════════════════════════
# 7. 协议10 pb_only 的 frame_type 端到端
# ═══════════════════════════════════════════════════════════════

def test_gw_pb_only_frame_type():
    print("\n[7] 协议10 pb_only frame_type 下发（端到端）")
    from gw_new_gen_parser import GWNewGenParser

    # PBH + 非 MMTYPE 前缀（避开「直接管理消息」早返回）
    pb = bytes([0x01, 0x10]) + bytes(30)
    parser = GWNewGenParser()

    # 修复前：Web 从不传 frame_type → 解析器落「未知(None)」
    bare = parser.parse_to_table(pb, parse_level="pb_only", channel="plc")
    check("不传 frame_type → 未知(None)（修复前的表现）",
          "未知(None)" in str(bare[0][2]), str(bare[0][2]))

    default_ft = parser.parse_to_table(
        pb, **web_utils.parse_kwargs_for(10, "pb_only", channel="plc"))
    check("默认下发 frame_type=1 → SOF帧",
          str(default_ft[0][2]) == "仅PB - SOF帧", str(default_ft[0][2]))

    with_ft2 = parser.parse_to_table(
        pb, **web_utils.parse_kwargs_for(10, "pb_only", gw_frame_type=2, channel="plc"))
    check("下发 frame_type=2 → SACK",
          "SACK" in str(with_ft2[0][2]), str(with_ft2[0][2]))


# ═══════════════════════════════════════════════════════════════
# 8. 查询页
# ═══════════════════════════════════════════════════════════════

def test_lookup_south_afn():
    print("\n[8a] 南网 DI 查询 AFN 列 = DI1")
    rows = lookup_utils._search_south_di("添加任务")
    row = next((r for r in rows if r[5] == "添加任务"), None)
    check("命中「添加任务」", row is not None, str(rows[:2]))
    if row:
        check("AFN 列 = DI1 = 02H（此前错为 08H）",
              row[4].startswith("02H"), f"AFN列={row[4]}")
    rows2 = lookup_utils._search_south_di("返回查询未完成任务列表")
    check("同组 DI 的 AFN 同样为 02H",
          rows2 and rows2[0][4].startswith("02H"), str(rows2[:1]))


def test_lookup_gw_newgen():
    print("\n[8b] 协议10 查询页使用国网新一代表")
    all_rows = lookup_utils.get_lookup_data(10, "")
    check("协议10 条目数 = 49（桌面同口径）", len(all_rows) == 49, str(len(all_rows)))
    cats = sorted({r["类别"] for r in all_rows})
    check("7 类：报文ID/端口/定界符/MSDU/规约/发送类型/广播方向",
          cats == ["MSDU类型", "发送类型", "定界符类型", "广播方向", "报文ID",
                   "报文端口号", "规约类型"], str(cats))
    check("查询列含说明列",
          lookup_utils.get_query_config(10)["columns"] == ["类别", "代码", "名称", "说明"],
          str(lookup_utils.get_query_config(10)["columns"]))
    check("条目含安全机制说明",
          any("安全机制" in str(r.get("说明", "")) for r in all_rows),
          str(all_rows[:1]))
    # 数据源切换判据：协议9 表里没有的条目现在能搜到，协议9 专有条目不再出现
    hits = lookup_utils.get_lookup_data(10, "终端主动抄表")
    check("搜协议10 自有条目有命中", len(hits) == 1, str(len(hits)))
    csg_only = lookup_utils.get_lookup_data(10, "CCO-STA应用层报文")
    check("协议9 专有条目不再出现在协议10（数据源已切换）", len(csg_only) == 0,
          str(csg_only[:1]))


def test_lookup_698_attrs():
    print("\n[8c] 协议8 查询页属性/方法列")
    rows = lookup_utils.get_lookup_data(8, "")
    check("条目非空", len(rows) > 0)
    with_attr = [r for r in rows if r["属性"] not in ("", "-")]
    check("存在带属性列表的 OI（此前恒为 -）", len(with_attr) > 0,
          f"共{len(rows)}条，带属性{len(with_attr)}条")
    check("属性格式为 k:v",
          with_attr and ":" in with_attr[0]["属性"], str(with_attr[:1]))


# ═══════════════════════════════════════════════════════════════
# 9~10. 校验器工厂与报文工具 CRC
# ═══════════════════════════════════════════════════════════════

def test_validator_factory():
    print("\n[9] 校验器工厂（Web _get_validator 委托 protocol_registry）")
    import protocol_registry

    missing = [i for i in range(12) if protocol_registry.make_validator(i) is None]
    check("12 协议校验器全部可实例化（原 NameError 路径）", not missing, str(missing))
    v0 = protocol_registry.make_validator(0)
    check("校验器具备 verify()", hasattr(v0, "verify"))
    # 真实南网帧：只要求返回结果对象（合法性与本任务无关）
    frame = bytes.fromhex("680E00000000010001E80005EF16")
    res = v0.verify(frame)
    check("verify() 返回结果对象", hasattr(res, "valid") and hasattr(res, "summary"))
    check("结果对象可给出摘要文本", isinstance(res.summary(), str) and res.summary() != "")


def test_tool_crc():
    print("\n[10] 报文工具 CRC 与解析器同口径")
    import crcmod

    import csg_new_gen_parser as csg

    out24 = web_utils.run_tool("crc24_newgen", "112233")
    expect24 = f"0x{csg._crc24_func(bytes.fromhex('112233')) & 0xFFFFFF:06X}"
    check("CRC-24 与协议9 解析器一致（rev=True）", expect24 in out24, f"{out24!r} vs {expect24}")
    out32 = web_utils.run_tool("crc32_newgen", "112233")
    expect32 = f"0x{csg._crc32_func(bytes.fromhex('112233')) & 0xFFFFFFFF:08X}"
    check("CRC-32 与协议9 解析器一致（等价实现，勿改）", expect32 in out32,
          f"{out32!r} vs {expect32}")


# ═══════════════════════════════════════════════════════════════
# 11. State 层（真实实例：校验分派/剔除重算/参数下发）
# ═══════════════════════════════════════════════════════════════

def test_state_layer():
    print("\n[11] State 层（reflex State 真实实例）")
    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return

    st = app.State(_reflex_internal_init=True)

    # 校验分派：原实现在 12 种协议上全部 NameError
    bad = []
    for i in range(12):
        st.current_protocol = i
        try:
            v = st._get_validator()
            if v is None:
                bad.append((i, "None"))
        except Exception as e:  # noqa: BLE001
            bad.append((i, f"{type(e).__name__}: {e}"))
    check("12 协议 _get_validator 均可用（此前 NameError）", not bad, str(bad))

    # 单帧解析路径：奇数长度报错、剔除重复点击一致
    st.current_protocol = 9
    st.csg_strip_head, st.csg_strip_tail = 2, 1
    st.frame_hex = "0102030405"
    first = st._apply_strip(st._clean_hex(st.frame_hex))
    second = st._apply_strip(st._clean_hex(st.frame_hex))
    check("剔除前2尾1 → 03 04", first == bytes.fromhex("0304"), first.hex())
    check("重复点击解析结果一致（不二次裁剪）", first == second,
          f"{first.hex()} vs {second.hex()}")

    # 解析级别参数下发（协议10 pb_only 带 frame_type）
    st.current_protocol, st.gw_parse_level = 10, "pb_only"
    st.gw_pb_frame_type = 2
    k = st._parse_kwargs()
    check("协议10 pb_only 参数含 frame_type=2", k.get("frame_type") == 2, str(k))
    st.gw_parse_level = "auto"
    check("协议10 auto 参数不含 frame_type", "frame_type" not in st._parse_kwargs())

    # 清理：避免影响同进程其他用例
    st.current_protocol = 0
    st.csg_strip_head = st.csg_strip_tail = 0


def test_end_to_end_batch():
    print("\n[12] 批量链路端到端（驱动 State.parse_batch）")
    import asyncio

    from csg_new_gen_parser import CSGNewGenParser

    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return

    async def drive(proto, level, text, pbft="sof"):
        st = app.State(_reflex_internal_init=True)
        st.current_protocol = proto
        st.csg_parse_level = level
        st.csg_pb_frame_type = pbft
        st.batch_input = text
        async for _ in st.parse_batch():
            pass
        return st

    # ① 协议9 mac_only 短 MAC 帧：行0 是「解析模式」、❌ 在行1 →
    #    修复前的「只看首行」判定会把它标成「成功」
    rows = CSGNewGenParser().parse_to_table(
        bytes.fromhex("495C2FAABBCCDDEE"), parse_level="mac_only", pb_frame_type="sof")
    check("该帧的 ❌ 行不在首行（原判定必误判成功）",
          "❌" not in str(rows[0][0]) and any(str(r[0]).startswith("❌") for r in rows),
          str([str(r[0])[:12] for r in rows[:3]]))

    st = asyncio.run(drive(9, "mac_only", "495C2FAABBCCDDEE"))
    check("mac_only 批量不再丢行（剥离直通）", len(st.batch_results) == 1,
          str(len(st.batch_results)))
    if st.batch_results:
        r0 = st.batch_results[0]
        check("批量端到端：中途 ❌ → 失败", r0["status"] == "失败", str(r0))
        check("失败原因进入摘要", "长度不足" in r0["summary"], r0["summary"])
        check("类型列显示「解析失败」", r0["proto"] == "解析失败", r0["proto"])
        ok = st.batch_results[0]["status"] == "失败"
        check("统计文案与状态一致", ("1 失败" in st.message) if ok else True, st.message)

    # ② 奇数长度 hex → 异常（不静默截断末位 nibble）
    st2 = asyncio.run(drive(10, "auto", "010203040"))
    check("奇数长度行仍被提取（未被预处理丢弃）", len(st2.batch_results) == 1,
          str(len(st2.batch_results)))
    if st2.batch_results:
        r1 = st2.batch_results[0]
        check("批量端到端：奇数长度 → 异常（不再静默裁剪）", r1["status"] == "异常", str(r1))
        check("异常摘要带帧片段", "010203040" in r1["summary"], r1["summary"])


def main():
    print("=" * 62)
    print("Web 版解析 P0 修复回归测试")
    print("=" * 62)
    test_hex_to_bytes_strict()
    test_batch_frame_outcome()
    test_strip_frame_bytes()
    test_parse_kwargs_for()
    test_option_constants()
    test_ed_wrapper_detection_and_layout()
    test_gw_pb_only_frame_type()
    test_lookup_south_afn()
    test_lookup_gw_newgen()
    test_lookup_698_attrs()
    test_validator_factory()
    test_tool_crc()
    test_state_layer()
    test_end_to_end_batch()
    print("\n" + "=" * 62)
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"全部通过（{PASS} 项）✓")
    print("=" * 62)


if __name__ == "__main__":
    main()
