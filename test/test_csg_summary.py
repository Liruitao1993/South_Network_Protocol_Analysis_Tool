"""新一代载波协议批量解析摘要生成 - 测试

验证批量解析表格中「业务摘要」列对各类报文的展示：
  - 网络层管理消息：体现 MMTYPE 解析
  - 网络层 MPDU/MAC 帧：体现定界符类型 + TEI
  - 应用层报文：体现业务标识 + 帧类型 + 核心内容

直接运行: python test_csg_summary.py
"""


import _path_setup  # noqa: E402

from csg_new_gen_parser import CSGNewGenParser

# ── 复刻 main_gui.py 中的摘要生成逻辑 ──

def get_csg_new_gen_summary(table_data: list) -> str:
    """与 MainWindow._get_csg_new_gen_summary 一致"""
    if not table_data:
        return "-"
    for item in table_data:
        if item[0].startswith("❌"):
            return item[3] if item[3] else "解析失败"
    fields = {item[0]: item for item in table_data}

    # 公共：MSDU 类型作为顶层分类（若存在）
    msdu_type_prefix = ""
    if "MSDU类型" in fields:
        msdu_type_name = fields["MSDU类型"][3]
        if msdu_type_name:
            msdu_type_prefix = msdu_type_name

    # 网络层：MMTYPE
    if "管理消息类型(MMTYPE)" in fields:
        mmtype_item = fields["管理消息类型(MMTYPE)"]
        mmtype_comment = mmtype_item[3]
        mmtype_name = mmtype_comment.split(":", 1)[1].strip() if ":" in mmtype_comment else mmtype_comment
        prefix = msdu_type_prefix if msdu_type_prefix else "网络层"
        summary_parts = [f"{prefix} | MMTYPE:{mmtype_name}"]
        if "管理消息版本" in fields:
            ver = fields["管理消息版本"][2]
            summary_parts.append(f"版本{ver}")
        return " | ".join(summary_parts)

    # 网络层：MPDU/MAC 帧
    if "定界符类型" in fields:
        delim_item = fields["定界符类型"]
        delim_desc = delim_item[3]
        prefix = msdu_type_prefix if msdu_type_prefix else "网络层"
        summary_parts = [f"{prefix} | {delim_desc}"]
        if delim_desc == "信标帧" and "信标载荷头" in fields:
            beacon_head_item = fields["信标载荷头"]
            beacon_parsed = beacon_head_item[2]
            if isinstance(beacon_parsed, str) and beacon_parsed.startswith("类型:"):
                beacon_type = beacon_parsed[3:]
                summary_parts.append(f"信标类型:{beacon_type}")
        if "源TEI" in fields:
            summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
        if "目的TEI" in fields:
            summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
        return " | ".join(summary_parts)

    # 应用层报文
    if "业务标识" in fields:
        summary_parts = [msdu_type_prefix if msdu_type_prefix else "应用层"]
        frame_type_item = fields.get("  帧类型域(D3~D0)")
        if frame_type_item:
            ft_comment = frame_type_item[3]
            ft_name = ft_comment.split(" - ", 1)[1] if " - " in ft_comment else ft_comment
            summary_parts.append(ft_name)
        svc_item = fields["业务标识"]
        svc_comment = svc_item[3]
        svc_desc = svc_comment.split(" - ", 1)[1] if " - " in svc_comment else svc_comment
        summary_parts.append(f"业务标识:{svc_desc}")
        dir_item = fields.get("  传输方向位(D15)")
        if dir_item:
            dir_comment = dir_item[3]
            dir_name = dir_comment.split(" - ", 1)[1] if " - " in dir_comment else dir_comment
            summary_parts.append(dir_name)
        core = extract_csg_core_content(table_data)
        if core:
            summary_parts.append(core)
        return " | ".join(summary_parts)

    # 兜底
    parts = []
    for item in table_data[:4]:
        fn, pv, desc = item[0], item[2], item[3]
        if any(k in fn for k in ["帧起始", "格式", "长度", "校验", "结束"]):
            continue
        parts.append(str(desc) if desc else str(pv))
    return " | ".join(parts) if parts else "-"


def extract_csg_core_content(table_data: list) -> str:
    """与 MainWindow._extract_csg_core_content 一致"""
    core_candidates = []
    for item in table_data:
        fn, raw, pv, desc = item[0], item[1], item[2], item[3]
        skip_keys = ["控制域", "传输方向", "启动标志", "响应标识", "业务扩展域标识",
                     "任务优先级", "保留(D", "帧类型域", "报文端口号", "报文标识符",
                     "应用版本号", "帧序号", "帧长", "业务标识", "保留",
                     "MSDU", "VLAN", "级联", "物理块", "MPDU", "MAC"]
        if any(k in fn for k in skip_keys):
            continue
        # 过滤噪声字段
        if any(k in fn for k in ["剩余数据", "未解析", "填充", "原始数据", "级联后剩余"]):
            continue
        if desc and any(k in desc for k in ["未解析", "可能为填充", "尚未实现"]):
            continue
        if desc and desc not in ("保留", "保留字段", "保留位默认填0"):
            if fn in ("业务数据单元", "确认/否认负载", "管理消息数据"):
                continue
            core_candidates.append((fn, desc))
    for fn, desc in core_candidates:
        if "否认原因" in fn or "原因码" in fn:
            return f"原因:{desc}"
    for fn, desc in core_candidates:
        if "MAC地址" in fn or fn in ("源地址", "目的地址"):
            return f"{fn}:{desc.split(':')[0] if ':' in desc else desc}"
    for fn, desc in core_candidates:
        if "TEI" in fn:
            return f"{fn}:{desc}"
    for fn, desc in core_candidates:
        if "抄读" in fn or "数据" in fn or "结果" in fn:
            return f"{fn}:{desc[:20]}"
    if core_candidates:
        fn, desc = core_candidates[0]
        return f"{fn}:{desc[:20]}"
    return ""


# ── 测试用例 ──

def test_app_confirm_summary():
    """应用层确认帧摘要：应含帧类型(确认/否认)+业务标识(确认)+方向"""
    parser = CSGNewGenParser()
    # 端口11 + 标识0101 + 保留00 + 控制域0000(确认/否认,下行) + 业务标识00(确认) + 版本01 + 序号0001 + 帧长0000
    frame = bytes.fromhex("1101010000000001000100")
    table = parser.parse_to_table(frame, parse_level="app")
    summary = get_csg_new_gen_summary(table)
    print(f"确认帧摘要: {summary}")
    assert "应用层" in summary, f"应标识为应用层: {summary}"
    assert "确认/否认" in summary, f"应含帧类型: {summary}"
    assert "业务标识:确认" in summary, f"应含业务标识: {summary}"
    assert "下行" in summary, f"应含方向: {summary}"
    print("[OK] 应用层确认帧摘要通过")


def test_app_neg_ack_summary():
    """应用层否认帧摘要：应含否认原因"""
    import struct
    parser = CSGNewGenParser()
    # 否认帧: 控制域帧类型=0(确认/否认), D14=1(启动站), 业务标识=0x01(否认), 原因码=0x00(通信超时)
    # 端口11 + 标识0101 + 保留00 + 控制域(0x4000小端) + 业务标识01 + 版本01 + 序号0000 + 帧长0001 + 数据00
    ctrl = 0x4000  # D14=1(启动), D3~D0=0(确认/否认)
    frame = bytes.fromhex("11") + bytes.fromhex("0101") + bytes.fromhex("00")
    frame += struct.pack('<H', ctrl)
    frame += bytes.fromhex("01")      # 业务标识=01(否认)
    frame += bytes.fromhex("01")      # 版本
    frame += struct.pack('<H', 0)     # 序号
    frame += struct.pack('<H', 1)     # 帧长=1
    frame += bytes.fromhex("00")      # 否认原因码=00(通信超时)
    table = parser.parse_to_table(frame, parse_level="app")
    summary = get_csg_new_gen_summary(table)
    print(f"否认帧摘要: {summary}")
    assert "业务标识:否认" in summary, f"应含业务标识否认: {summary}"
    assert "原因:通信超时" in summary, f"应含否认原因通信超时: {summary}"
    print("[OK] 应用层否认帧摘要通过")


def test_mgmt_message_summary():
    """网络层管理消息摘要：应体现 MMTYPE"""
    parser = CSGNewGenParser()
    # 直接构造管理消息: 版本01 + MMTYPE=0x0030(关联请求,LE:3000) + 保留000000 + 60字节0
    mgmt = bytes.fromhex("01" + "3000" + "000000" + "00" * 60)
    table = parser._parse_management_message(mgmt, base_offset=0)
    summary = get_csg_new_gen_summary(table)
    print(f"管理消息摘要: {summary}")
    assert "网络层" in summary, f"应标识为网络层: {summary}"
    assert "MMTYPE:" in summary, f"应含MMTYPE: {summary}"
    assert "关联请求" in summary, f"应含关联请求: {summary}"
    print("[OK] 网络层管理消息摘要通过")


def test_tei_list_reply_summary():
    """网络层 TEI 列表回复摘要：应体现 MMTYPE=TEI列表回复"""
    parser = CSGNewGenParser()
    # MMTYPE=0x0084 (TEI列表回复, LE: 8400)
    mgmt = bytes.fromhex("01" + "8400" + "000000" + "00" * 20)
    table = parser._parse_management_message(mgmt, base_offset=0)
    summary = get_csg_new_gen_summary(table)
    print(f"TEI列表回复摘要: {summary}")
    assert "网络层" in summary
    assert "MMTYPE:" in summary
    assert "TEI列表回复" in summary
    print("[OK] 网络层TEI列表回复摘要通过")


def test_summary_format_readable():
    """摘要格式应简洁可读，包含分隔符"""
    parser = CSGNewGenParser()
    frame = bytes.fromhex("1101010000000001000100")
    table = parser.parse_to_table(frame, parse_level="app")
    summary = get_csg_new_gen_summary(table)
    print(f"格式检查摘要: {summary}")
    # 应使用 | 分隔多个信息段
    assert "|" in summary, "多段信息应用 | 分隔"
    # 不应过长
    assert len(summary) < 100, f"摘要过长: {len(summary)}字符"
    print("[OK] 摘要格式可读性通过")


def test_msdu_type_in_summary():
    """自动解析完整 MAC 帧时，摘要应体现 MSDU 类型（应用层报文）和业务标识"""
    parser = CSGNewGenParser()
    # 短 MAC 头 12B + 短 MSDU 头(VLAN=0, 类型=0x01) + 应用层确认帧
    mac_header = bytearray.fromhex("03 00 04 00 00 00 00 00 00 00 01 00")
    msdu = bytes.fromhex("00 01") + bytes.fromhex("1101010000000001000100")
    mac_header[2] = len(msdu) & 0xFF
    mac_header[3] = (len(msdu) >> 8) & 0xFF
    frame = bytes(mac_header) + msdu + bytes.fromhex("DEADBEEF")
    table = parser.parse_to_table(frame)
    summary = get_csg_new_gen_summary(table)
    print(f"含MSDU类型摘要: {summary}")
    assert "应用层报文" in summary, f"摘要应含MSDU类型'应用层报文': {summary}"
    assert "业务标识:确认" in summary, f"摘要应含业务标识: {summary}"
    print("[OK] MSDU类型在摘要中体现通过")


if __name__ == "__main__":
    print("=" * 60)
    print("新一代载波协议批量解析摘要生成 - 测试")
    print("=" * 60)
    test_app_confirm_summary()
    print()
    test_app_neg_ack_summary()
    print()
    test_mgmt_message_summary()
    print()
    test_tei_list_reply_summary()
    print()
    test_summary_format_readable()
    print()
    test_msdu_type_in_summary()
    print("=" * 60)
    print("全部测试通过 ✓")
