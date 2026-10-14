# -*- coding: utf-8 -*-
"""协议14 南网上行通信规约（Q/CSG 11109004-2013）测试。

覆盖：线格式（L/CS/地址/切帧/控制域）、DI 索引与值解码、解析器（正常帧 / 坏 CS /
截断）、校验器、注册表接入。运行：``python test/test_csg_uplink.py``。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csg_uplink_wire as W          # noqa: E402
import csg_uplink_di as DI           # noqa: E402
import csg_uplink_parser as P        # noqa: E402
from validator.csg_uplink_validator import CSGUplinkValidator  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def build(afn, seq, info, c=0x40, a1="440306", a2=0x12D687, a3=0):
    """用线格式拼一帧（测试专用，独立于 frame_gen）；规范形态 = 长度域 4 字节。

    ``info`` 里的 DI 用**表序**（DI3 DI2 DI1 DI0，如 ``E0000000``），上线时自动转低字节在前。
    """
    raw = bytes.fromhex(info.replace(" ", ""))
    apdu = (bytes([afn, seq]) + raw[:2]
            + bytes.fromhex(DI.to_wire_di(raw[2:6].hex())) + raw[6:])
    return W.encode_frame(c, W.encode_addr(a1, a2, a3), apdu)


def build_legacy(afn, seq, info, c=0x40, a1="440306", a2=0x12D687, a3=0):
    """历史异形形态：长度域只有 2 字节小端 L（整帧 = L+6）。"""
    raw = bytes.fromhex(info.replace(" ", ""))
    apdu = (bytes([afn, seq]) + raw[:2]
            + bytes.fromhex(DI.to_wire_di(raw[2:6].hex())) + raw[6:])
    return W.encode_frame(c, W.encode_addr(a1, a2, a3), apdu, form=W.FORM_L16)


def test_wire():
    print("== 1. 线格式 ==")
    check("CS = C+A+APDU 模 256", W.calc_cs(bytes([0x40, 0x06])) == (0x40 + 0x06) & 0xFF)
    check("长度域 4 字节 = L(2B 小端)重复一次",
          W.encode_length(0x0117) == bytes([0x17, 0x01, 0x17, 0x01]),
          W.encode_length(0x0117).hex(" ").upper())
    check("长度域 2 字节（兼容形态）", W.encode_length(0x0117, W.FORM_L16) == bytes([0x17, 0x01]))
    check("长度域 FT1.2 双同值", W.encode_length(0x11, W.FORM_FT12) == bytes([0x11, 0x11]))
    check("长度小端解码", W.decode_length(0x17, 0x01) == 0x0117)
    check("规范形态偏移 APDU_OFFSET=14", W.APDU_OFFSET == 14 and W.MIN_FRAME_LEN == 16,
          f"{W.APDU_OFFSET}/{W.MIN_FRAME_LEN}")
    # 地址往返：省地市区县码高字节为省
    a = W.encode_addr("440306", 1234567, 7)
    check("地址编码 A1 低字节(区县)在前", a[:3] == bytes([0x06, 0x03, 0x44]), a[:3].hex())
    ad = W.parse_addr(a)
    check("地址往返 省地市区县码", ad.bcd_code == "440306", ad.bcd_code)
    check("地址往返 终端地址", ad.a2 == 1234567, str(ad.a2))
    check("地址往返 主站地址", ad.a3 == 7, str(ad.a3))
    # 控制域
    ctl = W.decode_control(0xC0)
    check("控制域 DIR/PRM 位", ctl["DIR"] == 1 and ctl["PRM"] == 1, str(ctl["传输方向"]))
    # 整帧
    f = build(0x00, 0x60, "0000 E0000000 00")
    check("长度域两段 L 相同且紧跟第二 68H",
          f[1:3] == f[3:5] and f[5] == 0x68, f.hex(" ").upper())
    check("整帧长度 = L+8", len(f) == W.decode_length(f[1], f[2]) + 8, f"len={len(f)}")
    check("looks_like 自洽", W.looks_like_csg_uplink(f))
    check("CS 自洽", W.check_cs(f))
    check("布局识别为 l16x2", W.resolve_layout(f).form == W.FORM_L16X2,
          W.resolve_layout(f).form)
    # 切帧：前缀垃圾 + 尾随
    frames = W.extract_csg_uplink_frames(b"\x11\x22\x33" + f + b"\x99\x88")
    check("从流中切出 1 帧", len(frames) == 1 and frames[0] == f, str(len(frames)))
    # 兼容：单个 2 字节小端 L（68 Llo Lhi 68）
    le16 = build_legacy(0x00, 0x60, "0000 E0000000 00")
    check("兼容 2 字节小端长度形态", le16 in W.extract_csg_uplink_frames(b"\x11" + le16),
          le16.hex(" ").upper())
    check("兼容形态整帧 = L+6", len(le16) == W.decode_length(le16[1], le16[2]) + 6, f"len={len(le16)}")
    check("兼容形态布局识别为 l16", W.resolve_layout(le16).form == W.FORM_L16,
          W.resolve_layout(le16).form)
    # FT1.2 形态（两个长度字节相同）
    apdu = bytes.fromhex("006000") + bytes(6) + b"\x00"
    body = bytes([0x68, 8 + len(apdu), 8 + len(apdu), 0x68, 0x40]) + W.encode_addr("000000", 1, 0) + apdu
    ft12 = body + bytes([W.calc_cs(body[4:]), 0x16])
    check("兼容 FT1.2 双同值长度形态", ft12 in W.extract_csg_uplink_frames(ft12),
          ft12.hex(" ").upper())
    # 规范形态优先：同一字节流里两种形态都不误伤
    both = W.extract_csg_uplink_frames(f + le16 + ft12)
    check("混合流切出 3 帧且顺序正确", [x.hex() for x in both] == [f.hex(), le16.hex(), ft12.hex()],
          str(len(both)))
    # 长度域两段不一致 → 非规范帧（结构仍可读，但 CS/长度校验不应误判为规范形态）
    bad = bytearray(f)
    bad[3] ^= 0x01
    check("长度域两段不一致不被认作规范形态",
          W.resolve_layout(bytes(bad)) is None or not W.resolve_layout(bytes(bad)).is_canonical,
          str(W.resolve_layout(bytes(bad))))
    # 歧义边界：L=0x68（Llo=0x68）时「4 字节形态」与「2 字节形态」结构都成立
    amb = W.encode_frame(0x40, W.encode_addr("440306", 1, 0), bytes(96))
    check("Llo=0x68 时仍判为规范形态", W.resolve_layout(amb).form == W.FORM_L16X2,
          f"{W.resolve_layout(amb).form} total={W.resolve_layout(amb).total} len={len(amb)}")
    check("歧义帧切帧不误切", W.extract_csg_uplink_frames(amb) == [amb],
          str([len(x) for x in W.extract_csg_uplink_frames(amb)]))


def test_di():
    print("== 2. DI 索引 ==")
    check("DI 索引非空", len(DI.DI_INDEX) > 200, str(len(DI.DI_INDEX)))
    e = DI.di_info("E0000000")
    check("E0000000 命中附 A", e is not None and e["appx"] == "A", str(e and e["appx"]))
    check("E0000120 终端地市区县码", DI.value_name_unit("E0000120")[0].startswith("终端地市区县码")
          or "地市区县" in DI.value_name_unit("E0000120")[0], DI.value_name_unit("E0000120")[0])
    check("附 C 复用 645（00010000）名称", "正向有功总电能" in DI.value_name_unit("00010000")[0],
          DI.value_name_unit("00010000")[0])
    check("645 内容长度 = 4", DI.content_length("00010000") == 4, str(DI.content_length("00010000")))
    check("E0000000 内容长度 = 1", DI.content_length("E0000000") == 1)
    check("E0000130 终端时间为 6 字节", DI.content_length("E0000130") == 6, str(DI.content_length("E0000130")))
    check("BCD 解码 12 34 56.78", DI.decode_bcd_number(bytes.fromhex("78563412"), 2) == "123456.78",
          str(DI.decode_bcd_number(bytes.fromhex("78563412"), 2)))
    check("非 BCD 返回 None", DI.decode_bcd_number(b"\xAB") is None)
    dec = DI.decode_di_value("E0000000", b"\x00")
    check("E0000000 值 00 → 确定", dec["解析值"] == "确定", str(dec["解析值"]))
    check("AFN 表含 0CH 读当前数据", DI.AFN_NAMES.get(0x0C) == "读当前数据")
    check("数据密度 6=1日", DI.DENSITY_NAMES.get(6) == "1日")
    check("错误码表非空", len(DI.ERR_CODES) >= 5, str(len(DI.ERR_CODES)))
    check("搜索 DI 前缀", len(DI.search_di("E00001", appx="A")) > 5)


def test_nm():
    """网管（深化应用）扩展：DI 归属、前缀规则、结构化解码、文档实帧回归。"""
    print("== 2b. 网管扩展（第4章）==")
    import csg_uplink_nm as NM
    import csg_uplink_frame_gen as fg

    check("网管扩展 DI 已并入索引", len(DI.nm_names()) >= 15, str(len(DI.nm_names())))
    check("归属标识 appx=N", DI.di_appendix("E1006010") == NM.NM_APPX, str(DI.di_appendix("E1006010")))
    check("查询页可按 appx=N 过滤", len(DI.search_di("", appx="N")) >= 14,
          str(len(DI.search_di("", appx="N"))))
    # 前缀规则（DI0 = 通信模块序号）
    check("前缀规则 E0800402 → E08004FF", DI.di_info("E0800402")["di"] == "E08004FF",
          str(DI.di_info("E0800402") and DI.di_info("E0800402")["di"]))
    check("前缀规则命中名称", "通信模块信息" in DI.value_name_unit("E0800403")[0],
          DI.value_name_unit("E0800403")[0][:20])
    check("前缀规则内容长度 = 65", DI.content_length("E0800402") == 65,
          str(DI.content_length("E0800402")))
    # 同号 DI 合并（E2000033/34 既有附 D 名称 + 网管扩展名称）
    check("同号 DI 合并名称", "设备掉电" in DI.di_info("E2000033")["name"]
          and DI.di_info("E2000033").get("nm") is True, DI.di_info("E2000033")["name"][:30])
    # 结构化解码
    dec = DI.decode_di_value("E1006010", bytes.fromhex("01000100"))
    check("自检信息 4 项枚举解码", "支持过零" in dec["解析值"] and "组网序列号变化" in dec["解析值"]
          and "掉电复位" in dec["解析值"], dec["解析值"])
    check("自检信息子项 = 4", len(dec["子项"]) == 4, str(len(dec["子项"])))
    check("频段枚举 00 → 1.953~11.96MHz",
          "1.953" in DI.decode_di_value("E0000040", b"\x00")["解析值"],
          DI.decode_di_value("E0000040", b"\x00")["解析值"])
    check("组网成功率 BCD 10 27 00 → 27.10%",
          DI.decode_di_value("E1800052", bytes.fromhex("102700"))["解析值"] == "27.10%",
          DI.decode_di_value("E1800052", bytes.fromhex("102700"))["解析值"])
    check("从节点重启 00 → 重启", "重启" in DI.decode_di_value("E0000041", b"\x00")["解析值"])
    check("并发数 0A → 10", DI.decode_di_value("E1006013", b"\x0A")["解析值"] == "10")
    mt = DI.decode_di_value("E1006015", bytes.fromhex("0200000000"))
    check("模块类型 02 → 集中器通信模块 + 离线时长", "集中器通信模块" in mt["解析值"]
          and "0 秒" in mt["解析值"], mt["解析值"])
    # 台账 65 字节：资产编号(32B ASCII) + 厂商代码(2B) + …
    ledger = (b"A" * 32 + b"ZK" + bytes.fromhex("0102") + b"\x01" + b"LX" + bytes(3) + bytes(6)
              + bytes.fromhex("0304") + bytes(3) + bytes.fromhex("0506") + bytes(3)
              + bytes.fromhex("0708") + bytes(3) + bytes.fromhex("0900"))
    check("台账内容长度 = 65", len(ledger) == 65, str(len(ledger)))
    dec2 = DI.decode_di_value("E0800402", ledger)
    check("台账解码出 14 个子项", len(dec2["子项"]) == 14, str(len(dec2["子项"])))
    check("台账资产编号 = 32×A", dec2["子项"][0]["解析值"] == "A" * 32,
          dec2["子项"][0]["解析值"][:12])
    check("台账 MAC 子项存在", any(r["名称"] == "模块出厂 MAC 地址" for r in dec2["子项"]))
    # 从节点地址列表：总数 2 + 本次数量 1 + n×6
    lst = bytes.fromhex("020002") + bytes.fromhex("111111111111") + bytes.fromhex("222222222222")
    dec3 = DI.decode_di_value("E1006012", lst)
    check("地址列表内容长度 = 3 + 6n", DI.content_length("E1006012", lst) == 15,
          str(DI.content_length("E1006012", lst)))
    check("地址列表解出 2 个节点地址",
          sum(1 for r in dec3["子项"] if "从节点地址" in r["名称"]) == 2,
          str([r["解析值"] for r in dec3["子项"] if "从节点地址" in r["名称"]]))
    # 网络拓扑 5 + 19n
    topo = bytes.fromhex("0100020001") + bytes.fromhex("111111111111") + bytes(13)
    check("拓扑内容长度 = 5 + 19n", DI.content_length("E1006014", topo) == 24,
          str(DI.content_length("E1006014", topo)))
    check("拓扑解码含节点信息位域",
          any("节点信息" in r["名称"] for r in DI.decode_di_value("E1006014", topo)["子项"]))
    # 4.14 远程模块：固定前缀 71 字节（厂商编号 8 / 序列号 15 / 版本号 32 / 制式 1 / IMEI 15）
    head = b"DL123456" + b"1" * 15 + b"V" * 32 + b"\x06" + b"8" * 15
    check("远程模块固定前缀 = 71 字节", len(head) == 71, str(len(head)))
    dec4 = DI.decode_di_value("E1006016", head + bytes(485 - 71))
    check("远程模块解析出 21 项",
          len([r for r in dec4["子项"] if not r["名称"].startswith("⚠")]) == 21,
          str(len(dec4["子项"])))
    sub = {r["名称"]: r["解析值"] for r in dec4["子项"]}
    check("远程模块制式 06 → FDD-LTE", "FDD-LTE" in sub.get("模组当前制式", ""),
          sub.get("模组当前制式", ""))
    check("远程模块 IMEI = 15×8", sub.get("模组 IMEI 号") == "8" * 15)
    check("远程模块 APN 名称存在", "APN 名称" in sub)
    # 掉电告警 ARD2（时间线上低字节在前：45 03 12 01 01 23 → 2023-01-01 12:03:45）
    ard = DI.decode_di_value("E2000033", bytes.fromhex("00450312010123"))
    check("掉电告警 ARD2 解出发生时间", "2023-01-01 12:03:45" in ard["解析值"], ard["解析值"])
    # ── 文档实帧回归：13 帧全部 valid；7 条 send 帧可逐字节复现 ──
    doc_frames = [
        "6810001000684B999999999999070A7C0102020480E0D716",
        "68120012006888491544090018070A6C0102020480E04852CB16",
        "6810001000684B9999999999990D0C630202126000E1B416",
        "681B001B0068881111211111110D0C630202126000E100000000007322000000006616",
        "6810001000684B9999999999990D0C630202146000E1B616",
        "681500150068881111211111110D0C630202146000E10000000000D316",
        "6810001000684B9999999999990D0C630000056000E1A316",
        "681800180068881111211111110D0C630000056000E1000D1111111111214316",
        "681100110068881111211111110D04650000400000E0009416",
        "6810001000684B9999999999990D0C630000086000E1A616",
        "681300130068881111211111110D0C630000086000E1000000C316",
        "6810001000684B9999999999990D0C630202106000E1B216",
        "681400140068881111211111110D0C630202106000E101000100D116",
    ]
    ok = True
    for hx in doc_frames:
        inst = P.CSGUplinkParser()
        inst.parse(bytes.fromhex(hx))
        if inst.last_meta.get("valid") is not True:
            ok = False
            break
    check("文档实帧 13 条全部解析 valid", ok, f"{len(doc_frames)} 帧")
    check("文档实帧 DI 归属网管扩展", DI.di_appendix(DI.to_semantic_di("020480E0")) == NM.NM_APPX)
    doc_send = [
        ("6810001000684B999999999999070A7C0102020480E0D716", 0x4B, 0x07, 0x0A, 0x7C, 0x01, 0x02,
         "E0800402", b""),
        ("6810001000684B9999999999990D0C630202126000E1B416", 0x4B, 0x0D, 0x0C, 0x63, 0x02, 0x02,
         "E1006012", b""),
        ("6810001000684B9999999999990D0C630202146000E1B616", 0x4B, 0x0D, 0x0C, 0x63, 0x02, 0x02,
         "E1006014", b""),
        ("6810001000684B9999999999990D0C630000056000E1A316", 0x4B, 0x0D, 0x0C, 0x63, 0x00, 0x00,
         "E1006005", b""),
        ("6810001000684B9999999999990D0C630000086000E1A616", 0x4B, 0x0D, 0x0C, 0x63, 0x00, 0x00,
         "E1006008", b""),
        ("6810001000684B9999999999990D0C630202106000E1B216", 0x4B, 0x0D, 0x0C, 0x63, 0x02, 0x02,
         "E1006010", b""),
        ("6821002100684A9999999999990D04710000400000E001000000000000000000000000000000008316",
         0x4A, 0x0D, 0x04, 0x71, 0x00, 0x00, "E0000040", b"\x01" + bytes(16)),
    ]
    same = 0
    for exp, c, a3, afn, seq_no, da1, da2, di, content in doc_send:
        got = fg.build_frame(
            c=c, afn=afn, a1="999999", a2=0x999999, a3=a3,
            tpv=(seq_no >> 7) & 1, fir=(seq_no >> 6) & 1, fin=(seq_no >> 5) & 1,
            con=(seq_no >> 4) & 1, pseq=seq_no & 0x0F,
            bodies=[fg.InfoBody(da1, da2, di, content)]).hex().upper()
        same += (got == exp)
    check("文档 send 实帧 7 条逐字节复现（含 DI 低字节在前）", same == len(doc_send),
          f"{same}/{len(doc_send)}")
    # 变长列表 DI：同一帧内两条信息体按内容长度正确切分
    two = fg.build_frame(c=0x88, afn=0x0C, a1="111121", a2=0x111111, a3=0x0D, fir=1, fin=1, pseq=3,
                         bodies=[fg.InfoBody(0x02, 0x02, "E1006010", bytes.fromhex("01000100")),
                                 fg.InfoBody(0x04, 0x02, "E1006010", bytes.fromhex("02030004"))])
    inst = P.CSGUplinkParser()
    rows_two = inst.parse(two)
    check("变长 DI 两条信息体正确切分",
          len([r for r in rows_two if "数据标识DI" in r[0]]) == 2 and inst.last_meta.get("valid"),
          str(len([r for r in rows_two if "数据标识DI" in r[0]])))


def test_parser():
    print("== 3. 解析器 ==")
    p = P.CSGUplinkParser()
    # 确认/否定
    f1 = build(0x00, 0x60, "0000 E0000000 00")
    rows = p.parse(f1)
    names = [r[0] for r in rows]
    check("解析出起始字符/长度/控制域/地址/AFN/SEQ/CS", all(
        any(k in n for n in names) for k in ("起始字符", "长度L", "控制域C", "地址域A",
                                              "应用功能码AFN", "帧序列域SEQ", "校验和CS", "结束字符")))
    check("确认帧 valid=True", p.last_meta.get("valid") is True, str(p.last_meta))
    check("长度域识别为规范 4 字节形态", p.last_meta.get("len_form") == W.FORM_L16X2,
          str(p.last_meta.get("len_form")))
    lrow = [r for r in rows if r[0] == "长度L"][0]
    check("长度L 行原始值为 4 字节", len(lrow[1].split()) == 4, lrow[1])
    check("长度L 行偏移 1~4", (lrow[4], lrow[5]) == (1, 4), f"{lrow[4]}~{lrow[5]}")
    check("有「长度L重复段」行且判定一致",
          any("长度L重复段" in r[0] and "⚠" not in r[3] for r in rows),
          str([r for r in rows if "长度L重复段" in r[0]]))
    check("第二个起始字符在偏移 5", any(r[0] == "起始字符2" and r[4] == 5 for r in rows))
    check("控制域C 在偏移 6", any(r[0] == "控制域C" and r[4] == 6 for r in rows))
    di_row = [r for r in rows if "数据标识DI" in r[0]]
    check("DI 行解析值 = 表序 E0000000", di_row and di_row[0][2] == "E0000000",
          str(di_row and di_row[0][2]))
    check("DI 行原始值 = 线上低字节在前 00 00 00 E0", di_row and di_row[0][1] == "00 00 00 E0",
          str(di_row and di_row[0][1]))
    check("DI 行偏移 18~21", di_row and (di_row[0][4], di_row[0][5]) == (18, 21),
          str(di_row and (di_row[0][4], di_row[0][5])))
    # 网管扩展：内容按字段展开成 ↳ 子行
    f_nm = build(0x0C, 0x63, "0202 E1006010 01000100", c=0x4B, a1="999999", a2=0x999999,
                 a3=0x0D)
    rows_nm = p.parse(f_nm)
    subs = [r for r in rows_nm if r[0].startswith("    ↳")]
    check("网管扩展内容展开出 4 个子行", len(subs) == 4, str(len(subs)))
    check("网管扩展子行含枚举解析", any("支持过零" in r[2] for r in subs),
          str([r[2] for r in subs]))
    # 读当前数据响应
    f2 = build(0x0C, 0x70, "0101 00010000 78563412")
    rows2 = p.parse(f2)
    da_row = [r for r in rows2 if "信息点标识DA" in r[0]]
    check("DA 解析出测量点 p1", da_row and "p1" in da_row[0][3], str(da_row and da_row[0][3]))
    di_row2 = [r for r in rows2 if "数据标识DI" in r[0]]
    check("DI=00010000 名称含正向有功", di_row2 and "正向有功" in di_row2[0][3], str(di_row2 and di_row2[0][3]))
    content_row = [r for r in rows2 if "数据标识内容" in r[0]]
    check("内容 {BCD 含 123456.78}", content_row and "123456.78" in content_row[0][2],
          str(content_row and content_row[0][2]))
    # 坏 CS：仍完整解析 + 标注
    bad = bytearray(f1)
    bad[-2] ^= 0xFF
    rows3 = p.parse(bytes(bad))
    check("坏 CS 仍返回字段且 valid=False", len(rows3) > 5 and p.last_meta.get("valid") is False)
    check("坏 CS 有醒目提示", any("不符" in r[3] or "⚠" in r[3] for r in rows3))
    # 帧长不足
    rows4 = p.parse(b"\x68\x01")
    check("帧长不足降级不抛错", len(rows4) >= 1 and "帧长不足" in rows4[0][0])
    # 摘要
    check("get_summary 含 AFN 名", "确认" in p.get_summary(f1), p.get_summary(f1))
    # 多信息体
    f3 = build(0x0A, 0x20, "0101 E0000120 0603 0102 E0000121 875634")
    rows5 = p.parse(f3)
    check("多信息体解析出 2 个 DI", len([r for r in rows5 if "数据标识DI" in r[0]]) == 2)
    # 兼容形态（单个 2 字节小端 L）仍可完整解析
    leg = build_legacy(0x0C, 0x70, "0101 00010000 78563412")
    rows6 = p.parse(leg)
    di_row6 = [r for r in rows6 if "数据标识DI" in r[0]]
    check("兼容形态解析出 DI=00010000", di_row6 and di_row6[0][2] == "00010000",
          str(di_row6 and di_row6[0][2]))
    check("兼容形态 valid=True 且 len_form=l16",
          p.last_meta.get("valid") is True and p.last_meta.get("len_form") == W.FORM_L16,
          str(p.last_meta))
    check("兼容形态 控制域偏移=4", any(r[0] == "控制域C" and r[4] == 4 for r in rows6))
    # 规范形态：长度域两段不一致 → 醒目提示且 valid=False
    badrep = bytearray(build(0x00, 0x60, "0000 E0000000 00"))
    badrep[3] = (badrep[3] + 1) & 0xFF
    rows7 = p.parse(bytes(badrep))
    check("长度域两段不一致 → ⚠ 且 valid=False",
          any("长度L重复" in r[0] for r in rows7) and p.last_meta.get("valid") is False,
          str(p.last_meta))


def test_validator():
    print("== 4. 校验器 ==")
    v = CSGUplinkValidator()
    good = build(0x00, 0x60, "0000 E0000000 00")
    r = v.verify(good)
    check("好帧 overall valid", r.valid, r.summary())
    check("好帧 0 失败项", r.fail_count == 0, r.summary())
    bad = bytearray(good)
    bad[-2] ^= 0xFF
    r2 = v.verify(bytes(bad))
    check("坏 CS 校验失败", not r2.valid and r2.fail_count >= 1, r2.summary())
    r3 = v.verify(b"\x68\x02")
    check("短帧校验失败不抛错", not r3.valid)
    r4 = v.verify(bytes([0x99]) + good[1:])
    check("起始字符错 → 失败", not r4.valid and r4.fail_count >= 1)
    # 长度域两段不一致 → 失败（条文解释：无效帧）
    r5 = v.verify(bytes(bytearray(good[:3]) + bytearray([good[3] ^ 0x01]) + bytearray(good[4:])))
    check("长度域两段不一致 → 失败", not r5.valid and r5.fail_count >= 1, r5.summary())
    # 兼容形态：通过但给出形态告警（规范形态应为 4 字节）
    r6 = v.verify(build_legacy(0x00, 0x60, "0000 E0000000 00"))
    check("兼容 2 字节长度形态 → 通过但告警", r6.valid and r6.warn_count >= 1, r6.summary())


def test_frame_gen():
    print("== 5. 组帧 ==")
    import csg_uplink_frame_gen as fg
    p = P.CSGUplinkParser()
    v = CSGUplinkValidator()
    f = fg.build_frame(afn=0x0C, bodies=[fg.InfoBody(da1=0x01, da2=0x01, di="00010000")],
                       a1="440306", a2=0x12D687, a3=0)
    check("组帧帧长 = L+8", len(f) == W.decode_length(f[1], f[2]) + 8, f"len={len(f)}")
    check("组帧长度域为规范 4 字节形态", f[5] == 0x68 and f[1:3] == f[3:5], f.hex(" ").upper())
    check("组帧自洽（解析 valid）", p.parse(f) and p.last_meta.get("valid") is True)
    check("组帧帧校验通过", v.verify(f).valid)
    ci = W.resolve_layout(f).c_index
    check("CON=0 → 功能码 11H", (f[ci] & 0x0F) == 0x0B, hex(f[ci]))
    f2 = fg.build_frame(afn=0x0A, bodies=[fg.InfoBody(0, 0, "E0000120")], con=True, a2=1)
    ci2 = W.resolve_layout(f2).c_index
    check("CON=1 → 功能码 10H", (f2[ci2] & 0x0F) == 0x0A, hex(f2[ci2]))
    da1, da2 = fg.da_from_pn(9)
    check("pn=9 → DA2=02 DA1=01", da1 == 0x01 and da2 == 0x02, f"{da1:02X}/{da2:02X}")
    check("DA 往返 pn=9", P._decode_da(bytes([da1, da2]))[2] == [9])
    tpls = fg.templates()
    check("模板非空且可组帧", len(tpls) >= 4 and all(
        W.check_cs(fg.build_frame(afn=t["afn"], bodies=[fg.InfoBody(**{k: b[k] for k in ("da1", "da2", "di")},
                                                                   content=bytes.fromhex(b.get("content", "")))
                                                          for b in t["bodies"]], a2=1))
        for t in tpls))
    # 预设种子文件全部自洽
    import json
    import os
    seed = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "CSG_UPLINK_command.json")
    with open(seed, encoding="utf-8") as fh:
        cmds = json.load(fh)["commands"]
    check("预设种子 ≥5 条", len(cmds) >= 5, str(len(cmds)))
    check("预设种子帧全部 CS 自洽", all(
        W.check_cs(bytes.fromhex(c["frame_hex"].replace(" ", ""))) for c in cmds))
    def _valid(cmd):
        inst = P.CSGUplinkParser()
        inst.parse(bytes.fromhex(cmd["frame_hex"].replace(" ", "")))
        return inst.last_meta.get("valid") is True

    check("预设种子解析全部 valid", all(_valid(c) for c in cmds))


def test_registry():
    print("== 6. 注册表 ==")
    import protocol_registry as PR
    import parser_registry as PaR
    spec = PR.get_protocol(14)
    check("协议14 已注册", spec.index == 14, spec.name)
    check("parser_key=csg_uplink", spec.parser_key == "csg_uplink")
    check("extract_strategy=csg_uplink", spec.extract_strategy == "csg_uplink")
    check("lookup_kind 映射到 builder", PR.lookup_builder_method(spec.lookup_kind)
          == "_create_csg_uplink_lookup_content")
    check("parser_registry 已登记", "csg_uplink" in PaR._PARSER_SPECS)
    cls = PaR.get_parser_class("csg_uplink")
    check("parser 类可实例化", isinstance(PaR.get_parser("csg_uplink"), cls))
    check("别名可反查索引", PR.name_to_index("南网上行") == 14, str(PR.name_to_index("南网上行")))
    check("协议总数 = 15", PR.protocol_count() == 15, str(PR.protocol_count()))
    val = PR.make_validator(14)
    check("make_validator 返回校验器", val is not None and val.verify(good_frame()).valid)
    # 注册表里的「输入示例」帧必须真的能解析（规范 4 字节长度域形态）
    ph = bytes.fromhex(spec.placeholder.split("：")[-1].strip().replace(" ", ""))
    inst = P.CSGUplinkParser()
    inst.parse(ph)
    check("注册表示例帧可解析且 valid", inst.last_meta.get("valid") is True, str(inst.last_meta))
    check("注册表示例帧为规范长度域形态", inst.last_meta.get("len_form") == W.FORM_L16X2,
          str(inst.last_meta.get("len_form")))


def good_frame():
    return build(0x00, 0x60, "0000 E0000000 00")


def main():
    test_wire()
    test_di()
    test_nm()
    test_parser()
    test_validator()
    test_frame_gen()
    test_registry()
    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
