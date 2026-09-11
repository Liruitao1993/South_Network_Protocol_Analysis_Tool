"""协议9批量解析通信时序图 - 纯逻辑模型测试

覆盖 design.md 测试设计 T1~T6，另加广播判别与 ED 监控包装帧样本：
  T1 从样本帧 _table_data 提取源/目的 TEI 正确
  T2 TEI=1 → CCO 节点且排序最左
  T3 信标帧 → kind=beacon、src=CCO、dst=None
  T4 SACK 帧 → 有向确认（帧内目的TEI=291 即箭头所指节点，src 缺省 CCO）
  T5 解析失败帧 / 无TEI且非信标SACK帧 → 计入 skipped 不产生消息
  T6 节点按首次出现排序、同 TEI 去重
  T7 应用层「发送类型」注释含"广播" → kind=broadcast、dst=None
  T8 ED 监控包装帧（── PLC2.0 监控包装头 ── + 内层业务帧字段）TEI 照常提取
  T9 分派入口与 frame_indices 原始索引保持
  T10 广播类消息标签带[广播]标识；TEI=0 关联请求帧 → 未入网站点节点
  T11 业务标识=0xF0 测试帧 → 台体与CCO合并生命线
  T12 未入网归并+阶段分隔+入网标记
  T13 协议10(国网新一代)缩进字段同构提取
  T14 协议11(HDC 1.0) 定界符类型(DT)/消息类型(MMTYPE) 同构提取+入网归并

样本帧复用 test_csg_batch_parse_level.py / test_sack_fix.py 的协议9帧常量。

直接运行: python test_csg_sequence_model.py
"""

import _path_setup  # noqa: E402

from csg_new_gen_parser import CSGNewGenParser
from sequence_diagram_widget import (
    build_sequence_model,
    build_sequence_model_csg,
)

# ── 样本帧（复用现有协议9测试常量）──────────────────────────────

# SOF 下行：真实并发抄读完整MPDU帧（FC 16B + PB 136B），源TEI=1(CCO) 目的TEI=2
# （与 test_csg_batch_parse_level.REAL_FRAME 同一帧）
SOF_DOWN = bytes.fromhex(
    "19012000030000417804005B1000000000000000030045000210004111"
    "0805000301110101000160020109003700640198900000011100682119"
    "70051E0025000210006801110068211968110433333433661610006801"
    "1100682119681104343433376B16A89D0543" + "00" * 44 + "0B8F8D"
)

# SOF 上行：多PB重组并发抄读应答帧，源TEI=2 目的TEI=1(CCO)
# （与 test_csg_batch_parse_level.test_parser_multi_pb_uplink 同一帧）
SOF_UP = bytes.fromhex(
    "19 02 10 00 08 5B 2A 00 B3 01 00 00 20 20 31 3D 00 00 00 00 "
    "13 00 4C 00 01 20 00 11 00 08 A4 90 00 01 11 01 01 00 01 80 "
    "02 01 09 00 3E 00 01 11 00 68 21 19 64 01 98 90 00 00 00 00 "
    "00 2D 00 02 14 00 68 01 11 00 68 21 19 68 91 08 33 33 34 33 "
    "34 35 33 33 00 04 FF 86 01 00 00 00 B9 16 14 00 68 01 11 00 "
    "68 21 19 68 91 08 34 34 33 37 3A 35 33 33 C4 16 A5 46 1B 15 "
    + "00 " * 36 + "67 70 4F"
)

# SACK 16B：byte0=0x1A(delim=2, access=1)，byte12=0x10(扩展帧类型=0标准SACK)
# 可变区域带目的TEI=0x123=291（验证规则2先于TEI规则：SACK 不产生目的节点）
SACK_FRAME = bytes([0x1A, 0xA0, 0x23, 0x31, 0x01] + [0x00] * 7 + [0x10, 0, 0, 0])

# 信标帧 16B：byte0=0x18(delim=0, access=1, SNID低4位=1)
BEACON_FRAME = bytes([0x18] + [0x00] * 15)

# ED 包装内层业务帧（SOF，源TEI=1 目的TEI=2，与 test_ed_fallback_fix 同一业务帧）
ED_BIZ_FRAME = bytes.fromhex("0901200004" + "1B03001606000020D6B625" + "00000000")


def _parse(frame_bytes):
    return CSGNewGenParser().parse_to_table(frame_bytes)


def _make_entry(frame_bytes, summary="测试帧摘要", status="成功", table=None):
    """构造 batch_results 风格条目（frame_bytes 与 table 二选一）"""
    return {
        "_input": frame_bytes.hex().upper() if frame_bytes else "",
        "_status": status,
        "_table_data": table if table is not None else _parse(frame_bytes),
        "_type_name": "",
        "摘要": summary,
    }


def _key(tei):
    return f"TEI:{tei}"


# ── 测试用例 ────────────────────────────────────────────────────

def test_t1_tei_extract():
    """T1: 从样本帧 _table_data 提取源/目的 TEI 正确"""
    model = build_sequence_model_csg([_make_entry(SOF_DOWN)])
    assert len(model.messages) == 1, f"应产生1条消息: {len(model.messages)}"
    msg = model.messages[0]
    assert msg.kind == "unicast", f"SOF应为单播: {msg.kind}"
    assert msg.src_key == _key(1), f"源TEI应为1: {msg.src_key}"
    assert msg.dst_key == _key(2), f"目的TEI应为2: {msg.dst_key}"
    tei_map = {n.key: n.tei for n in model.nodes}
    assert tei_map == {_key(1): 1, _key(2): 2}, f"节点TEI不符: {tei_map}"
    print("[OK] T1 源/目的TEI提取正确")


def test_t2_cco_leftmost():
    """T2: TEI=1 → CCO 节点且排序最左（即使首条消息由 STA 发出）"""
    # 首条消息 STA-2 → CCO：CCO 并非首次出现的节点，仍须排最左
    model = build_sequence_model_csg(
        [_make_entry(SOF_UP), _make_entry(SOF_DOWN)]
    )
    assert model.nodes[0].tei == 1, f"首节点应为CCO: {model.nodes[0]}"
    assert model.nodes[0].role == "CCO" and model.nodes[0].label == "CCO"
    sta = model.nodes[1]
    assert sta.role == "STA" and sta.label == "STA-0002", f"STA标签: {sta.label}"
    print("[OK] T2 CCO节点最左且标注正确")


def test_t3_beacon_broadcast():
    """T3: 信标帧 → kind=beacon、src=CCO、dst=None"""
    model = build_sequence_model_csg([_make_entry(BEACON_FRAME, "信标帧")])
    assert len(model.messages) == 1, f"信标应产生1条消息: {len(model.messages)}"
    msg = model.messages[0]
    assert msg.kind == "beacon", f"kind应为beacon: {msg.kind}"
    assert msg.src_key == _key(1), f"信标src应为CCO: {msg.src_key}"
    assert msg.dst_key is None, f"广播dst应为None: {msg.dst_key}"
    assert "[广播]" in msg.label, f"广播标签应带[广播]标识: {msg.label}"
    assert len(model.nodes) == 1, f"广播不产生目的节点: {len(model.nodes)}"
    print("[OK] T3 信标帧→CCO广播")


def test_t4_sack_directed():
    """T4: SACK 帧 → 有向确认：帧内目的TEI(291)即箭头所指节点，src 缺省 CCO"""
    model = build_sequence_model_csg([_make_entry(SACK_FRAME, "选择确认帧")])
    assert len(model.messages) == 1, f"SACK应产生1条消息: {len(model.messages)}"
    msg = model.messages[0]
    assert msg.kind == "sack", f"kind应为sack: {msg.kind}"
    assert msg.src_key == _key(1), f"SACK src缺省应为CCO: {msg.src_key}"
    assert msg.dst_key == _key(291), (
        f"SACK帧内目的TEI应为箭头所指节点: {msg.dst_key}"
    )
    assert "[广播]" not in msg.label, f"有向SACK不应带[广播]: {msg.label}"
    assert [n.tei for n in model.nodes] == [1, 291], (
        f"应建CCO与目的TEI节点: {model.nodes}"
    )
    print("[OK] T4 SACK帧→有向确认(目的TEI为箭头所指)")


def test_t5_skip_frames():
    """T5: 解析失败帧 / 无TEI且非信标SACK帧 → 计入 skipped 不产生消息"""
    failed = _make_entry(
        None,
        summary="ED 帧解析失败（报文不完整或格式错误）",
        status="失败",
        table=[("❌ 解析失败", "", "", "ED 监控帧解析失败", None, None)],
    )
    abnormal = {"_input": "AA", "_status": "异常", "错误": "x", "摘要": "x"}
    no_tei = _make_entry(
        None,
        status="成功",
        table=[("定界符类型", "0b011", "3", "网间协调帧", 0, 0)],
    )
    model = build_sequence_model_csg(
        [failed, _make_entry(SOF_DOWN), abnormal, no_tei]
    )
    assert model.skipped == 3, f"应跳过3帧: {model.skipped}"
    assert len(model.messages) == 1, f"仅SOF下行1条消息: {len(model.messages)}"
    assert model.messages[0].frame_idx == 1, "消息应指向原始索引1"
    print("[OK] T5 失败帧/无TEI帧跳过计数正确")


def test_t6_node_order_dedup():
    """T6: 节点按首次出现排序、同 TEI 去重"""
    # 消息流: 2→1, 1→2, 2→1；首现顺序 STA-2 在前，排序后 CCO 恒最左
    model = build_sequence_model_csg(
        [_make_entry(SOF_UP), _make_entry(SOF_DOWN), _make_entry(SOF_UP)]
    )
    assert [n.tei for n in model.nodes] == [1, 2], (
        f"节点应去重且CCO最左: {[n.label for n in model.nodes]}"
    )
    assert len(model.messages) == 3
    dirs = [(m.src_key, m.dst_key) for m in model.messages]
    assert dirs == [(_key(2), _key(1)), (_key(1), _key(2)), (_key(2), _key(1))], (
        f"消息方向序列不符: {dirs}"
    )
    print("[OK] T6 节点去重与首现排序正确")


def test_t7_app_broadcast():
    """T7: 应用层「发送类型」注释含"广播" → kind=broadcast、dst=None"""
    table = [
        ("定界符类型", "0b001", "1", "SOF帧", 0, 0),
        ("源TEI", "0x001", "1", "发送站点TEI: 1", 1, 2),
        ("目的TEI", "0x002", "2", "接收站点TEI: 2", 2, 3),
        ("发送类型", "0x1", "1", "全网广播(不确认)", 9, 9),
    ]
    model = build_sequence_model_csg(
        [_make_entry(None, status="成功", table=table)]
    )
    msg = model.messages[0]
    assert msg.kind == "broadcast", f"应为broadcast: {msg.kind}"
    assert msg.src_key == _key(1) and msg.dst_key is None
    assert "[广播]" in msg.label, f"广播标签应带[广播]标识: {msg.label}"
    assert [n.tei for n in model.nodes] == [1], "广播不产生目的节点"
    print("[OK] T7 应用层广播判别正确")


def test_t10_broadcast_tag_and_unassoc_tei0():
    """T10: 广播标签[广播]标识 + TEI=0 关联请求帧 → 未入网站点节点"""
    # 单播消息标签不带[广播]
    uni = build_sequence_model_csg([_make_entry(SOF_DOWN, "单播摘要")])
    assert "[广播]" not in uni.messages[0].label, (
        f"单播不应带[广播]: {uni.messages[0].label}"
    )
    # TEI=0（入网前关联请求）：节点标为未入网站点，CCO 仍最左
    table = [
        ("定界符类型", "0b001", "1", "SOF帧", 0, 0),
        ("源TEI", "0x000", "0", "发送站点TEI: 0", 1, 2),
        ("目的TEI", "0x001", "1", "接收站点TEI: 1", 2, 3),
    ]
    model = build_sequence_model_csg(
        [_make_entry(None, summary="关联请求", status="成功", table=table)]
    )
    msg = model.messages[0]
    assert msg.kind == "unicast" and msg.src_key == _key(0), (
        f"TEI=0应作为源节点: {msg.src_key}"
    )
    node0 = next(n for n in model.nodes if n.tei == 0)
    assert node0.label == "未入网站点", f"TEI=0标签: {node0.label}"
    assert node0.role == "UNASSOC", f"TEI=0角色: {node0.role}"
    assert model.nodes[0].tei == 1, "CCO 仍应最左"
    print("[OK] T10 广播标识与TEI=0未入网站点节点正确")


def test_t11_test_frame_merges_cco():
    """T11: 业务标识=0xF0 测试帧 ⇒ 台体模拟CCO：与CCO合并为一条生命线"""
    table = [
        ("定界符类型", "0b001", "1", "SOF帧", 0, 0),
        ("源TEI", "0x001", "1", "发送站点TEI: 1", 1, 2),
        ("目的TEI", "0x002", "2", "接收站点TEI: 2", 2, 3),
        ("业务标识", "0xF0", "240", "业务标识 240 - 测试帧", 4, 5),
    ]
    model = build_sequence_model_csg(
        [_make_entry(None, summary="测试帧", status="成功", table=table)]
    )
    msg = model.messages[0]
    assert msg.src_key == _key(1), f"测试帧源应归CCO生命线: {msg.src_key}"
    assert msg.dst_key == _key(2)
    cco = model.nodes[0]
    assert cco.label == "台体发射机(模拟CCO)", f"CCO标注: {cco.label}"
    assert [n.tei for n in model.nodes] == [1, 2], "不应另建台体独立节点"
    print("[OK] T11 测试帧→台体与CCO合并生命线")


def test_t12_unassoc_merge_phases_marker():
    """T12: 未入网站点归并到关联确认分配TEI + 阶段分隔 + 入网状态标记"""
    req = [
        ("定界符类型", "0b001", "1", "SOF帧", 0, 0),
        ("源TEI", "0x000", "0", "发送站点TEI: 0", 1, 2),
        ("目的TEI", "0x001", "1", "接收站点TEI: 1", 2, 3),
        ("管理消息类型(MMTYPE)", "0x0001", "1", "管理消息: 关联请求(MMeAssocReq)", 4, 5),
    ]
    cnf = [
        ("定界符类型", "0b001", "1", "SOF帧", 0, 0),
        ("源TEI", "0x001", "1", "发送站点TEI: 1", 1, 2),
        ("目的TEI", "0x002", "2", "接收站点TEI: 2", 2, 3),
        ("管理消息类型(MMTYPE)", "0x0002", "2", "管理消息: 关联确认(MMeAssocCnf)", 4, 5),
    ]
    model = build_sequence_model_csg(
        [
            _make_entry(None, summary="关联请求", status="成功", table=req),
            _make_entry(None, summary="关联确认", status="成功", table=cnf),
            _make_entry(SOF_DOWN, "抄读下行"),
        ]
    )
    assert [n.tei for n in model.nodes] == [1, 2], f"未入网应归并: {[n.label for n in model.nodes]}"
    dut = model.nodes[1]
    assert dut.label == "STA-0002 (DUT)", f"DUT标注: {dut.label}"
    m0, m1 = model.messages[0], model.messages[1]
    assert m0.src_key == _key(2) and m0.dst_key == _key(1), f"关联请求应自DUT生命线: {m0.src_key}->{m0.dst_key}"
    assert m1.marker == "入网→STA-0002", f"入网状态标记: {m1.marker}"
    labels = [p[1] for p in model.phases]
    assert any("关联入网" in x for x in labels), f"阶段分隔: {model.phases}"
    assert any("业务测试" in x for x in labels), f"阶段分隔: {model.phases}"
    print("[OK] T12 未入网归并+阶段分隔+入网标记正确")


def test_t13_protocol10_indented_fields():
    """T13: 协议10(国网新一代)缩进字段去缩进同构提取"""
    table = [
        ("  定界符类型", "0x11 D[2:0]=001", "1 (SOF帧)", "DT=1: SOF帧", 0, 1, True),
        ("  源TEI", "01 00", "1", "发送站点TEI", 8, 9, True),
        ("  目的TEI", "00 02", "2", "接收站点TEI", 9, 10, True),
        ("  发送类型", "0x0", "0", "单播(需确认)", 10, 10, True),
    ]
    model = build_sequence_model(
        [{"_status": "成功", "_table_data": table, "摘要": "SOF下行"}], 10
    )
    assert model is not None, "协议10应分派到通用提取管道"
    assert len(model.messages) == 1
    m = model.messages[0]
    assert m.kind == "unicast" and m.src_key == _key(1) and m.dst_key == _key(2), (
        f"协议10 TEI提取: {m.src_key}->{m.dst_key}"
    )
    # 信标帧（DT=0 注释形态）→ 广播
    beacon_tbl = [
        ("  定界符类型", "0x08 D[2:0]=000", "0 (信标帧)", "DT=0: 信标帧", 0, 1, True),
        ("  源TEI", "01 00", "1", "发送信标站点的TEI", 8, 9, True),
    ]
    model2 = build_sequence_model(
        [{"_status": "成功", "_table_data": beacon_tbl, "摘要": "信标帧"}], 10
    )
    b = model2.messages[0]
    assert b.kind == "beacon" and b.dst_key is None and b.src_key == _key(1), (
        f"协议10信标: {b.kind} {b.src_key}->{b.dst_key}"
    )
    print("[OK] T13 协议10缩进字段同构提取正确")


def test_t14_protocol11_assoc_merge():
    """T14: 协议11(HDC 1.0) 定界符类型(DT)/消息类型(MMTYPE) 同构+入网归并"""
    req = [
        ("定界符类型(DT)", "0b001", "1", "SOF帧", 0, 0),
        ("  源TEI", "0x000", "0", "源站点TEI", 4, 5),
        ("  目的TEI", "0x001", "1", "目的站点TEI", 5, 6),
        ("  消息类型(MMTYPE)", "0x0000", "0", "关联请求", 8, 9),
    ]
    cnf = [
        ("定界符类型(DT)", "0b001", "1", "SOF帧", 0, 0),
        ("  源TEI", "0x001", "1", "源站点TEI", 4, 5),
        ("  目的TEI", "0x002", "2", "目的站点TEI", 5, 6),
        ("  消息类型(MMTYPE)", "0x0001", "1", "关联确认", 8, 9),
    ]
    model = build_sequence_model(
        [
            {"_status": "成功", "_table_data": req, "摘要": "关联请求"},
            {"_status": "成功", "_table_data": cnf, "摘要": "关联确认"},
        ],
        11,
    )
    assert model is not None, "协议11应分派到通用提取管道"
    assert [n.tei for n in model.nodes] == [1, 2], (
        f"协议11未入网应归并: {[n.label for n in model.nodes]}"
    )
    assert model.messages[0].src_key == _key(2), "关联请求应自DUT生命线发出"
    assert model.messages[1].marker == "入网→STA-0002", (
        f"协议11入网标记: {model.messages[1].marker}"
    )
    labels = [p[1] for p in model.phases]
    assert any("关联入网" in x for x in labels), f"协议11阶段分隔: {model.phases}"
    print("[OK] T14 协议11同构提取+入网归并正确")


def test_t8_ed_wrapped_frame():
    """T8: ED 监控包装帧（包装头分段行 + 内层业务帧字段）TEI 照常提取"""
    biz_table = _parse(ED_BIZ_FRAME)
    ed_table = [
        ("── PLC2.0 监控包装头 ──", "", "", "ED..EE 监控设备附加信息（不属于业务帧）", None, None),
        ("起始符(ED)", "0xED", "ED", "PLC2.0 收发机包装起始标识", 0, 0),
        ("── 业务帧 ──", "", "", "以下为 ED 数据域解析结果", 15, 20),
    ] + biz_table
    model = build_sequence_model_csg(
        [_make_entry(None, summary="[ED:数据] 监控帧", status="成功", table=ed_table)]
    )
    assert len(model.messages) == 1, f"ED帧应产生1条消息: {len(model.messages)}"
    msg = model.messages[0]
    assert msg.kind == "unicast", f"内层SOF应为单播: {msg.kind}"
    assert (msg.src_key, msg.dst_key) == (_key(1), _key(2)), (
        f"ED内层TEI应照常提取: {msg.src_key}->{msg.dst_key}"
    )
    assert len(model.nodes) == 2, "包装头本身不产生节点"
    print("[OK] T8 ED监控包装帧TEI提取正确")


def test_t9_dispatch_and_frame_indices():
    """T9: 分派入口（仅协议9）+ frame_indices 保持原始索引"""
    # 未覆盖协议返回 None；9/10/11 共用通用管道
    assert build_sequence_model([_make_entry(SOF_DOWN)], 0) is None
    assert build_sequence_model([_make_entry(SOF_DOWN)], 7) is None
    model = build_sequence_model([_make_entry(SOF_DOWN)], 9)
    assert model is not None
    model = build_sequence_model([_make_entry(SOF_DOWN)], 10)
    assert model is not None and len(model.messages) == 1
    model = build_sequence_model([_make_entry(SOF_DOWN)], 11)
    assert model is not None and len(model.messages) == 1
    model = build_sequence_model([_make_entry(SOF_DOWN)], 9)
    assert model is not None and len(model.messages) == 1
    # 勾选子集：frame_indices 保持 batch_results 原始索引，#N 同步
    model = build_sequence_model_csg(
        [_make_entry(SOF_UP), _make_entry(SOF_DOWN)], frame_indices=[4, 7]
    )
    idxs = [m.frame_idx for m in model.messages]
    assert idxs == [4, 7], f"frame_idx应为原始索引: {idxs}"
    assert model.messages[0].label.startswith("#5 "), (
        f"标签帧序号应为原始#5: {model.messages[0].label}"
    )
    assert model.messages[1].label.startswith("#8 ")
    try:
        build_sequence_model_csg([_make_entry(SOF_DOWN)], frame_indices=[0, 1])
        raise AssertionError("frame_indices 长度不一致应抛 ValueError")
    except ValueError:
        pass
    print("[OK] T9 分派入口与原始索引保持正确")


def main():
    print("=" * 56)
    print("协议9批量解析通信时序图 - 纯逻辑模型测试")
    print("=" * 56)
    test_t1_tei_extract()
    test_t2_cco_leftmost()
    test_t3_beacon_broadcast()
    test_t4_sack_directed()
    test_t5_skip_frames()
    test_t6_node_order_dedup()
    test_t7_app_broadcast()
    test_t8_ed_wrapped_frame()
    test_t9_dispatch_and_frame_indices()
    test_t10_broadcast_tag_and_unassoc_tei0()
    test_t11_test_frame_merges_cco()
    test_t12_unassoc_merge_phases_marker()
    test_t13_protocol10_indented_fields()
    test_t14_protocol11_assoc_merge()
    print("=" * 56)
    print("[OK] 全部测试通过")


if __name__ == "__main__":
    main()
