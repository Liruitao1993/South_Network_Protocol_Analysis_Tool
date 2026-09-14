# -*- coding: utf-8 -*-
"""新一代载波协议批量解析摘要生成 - 测试

验证批量解析表格中「摘要」列对各类报文的展示：
  - 网络层管理消息：体现 MMTYPE
  - 网络层 MPDU/MAC 帧：体现定界符类型 + TEI
  - 应用层报文：体现业务标识 + 帧类型 + 核心内容
  - 测试帧（业务标识 0xF0）：体现测试模式 / 测试ID / 频段

摘要逻辑**只保留 main_gui.MainWindow 一份实现**：本文件通过未绑定方法调用
（Host 承载），不再复刻第二份逻辑，避免实现漂移。

直接运行: python test_csg_summary.py
"""


import _path_setup  # noqa: E402

from csg_new_gen_parser import CSGNewGenParser
from csg_new_gen_cmd_payloads import parse_command_payload
import main_gui


class Host:
    """仅提供摘要方法的最小宿主（免 GUI/QApplication 驱动）"""

    _get_csg_new_gen_summary = main_gui.MainWindow._get_csg_new_gen_summary
    _extract_csg_core_content = main_gui.MainWindow._extract_csg_core_content
    # staticmethod 需显式包裹：直接挂到类体会变成实例方法（多传一个 self）
    _extract_test_mode_content = staticmethod(
        main_gui.MainWindow._extract_test_mode_content
    )
    _TEST_MODE_SENTINELS = main_gui.MainWindow._TEST_MODE_SENTINELS


host = Host()

# 真实抓包：协议9 测试帧（业务标识 0xF0，TCP EDA5 包装，剥 15 字节应用层头）
TCP_TEST_FRAME_HEX = (
    "EDA5000002EF0149C84C27010088000900F0FF010000417804005B10EA9809"
    "0000000003001300FF0F00001F0102000301110101000260F0010000050002"
    "00010002AD4353F8004A95AF" + "00" * 50 + "FFEE"
)
# 2.0 测试帧（Bitloading表下发，来自 GUI 抓包；见 test/test_cmd_test_frame.py）
SDU_TEST_2_0 = bytes.fromhex(
    "04 00 28 00 01 06 02 00 01 00 02 00 01 03 EA 01 "
    "18 00 48 04 B6 6D DB 24 49 92 24 49 49 92 24 49 "
    "4A 92 24 49 92 00 00 00 00 00 00 00".replace(" ", "")
)
# 1.0 测试帧 SDU：测试ID=0x03 + 保留 + 数据区长度(LE) + 表61（测试模式=3 在字节1高4位）
SDU_TEST_1_0 = bytes([0x03, 0x00, 0x08, 0x00]) + bytes(
    [0x01, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
)


def _app_frame(ctrl: int, sdu: bytes, sid: int = 0xF0) -> bytes:
    """构造应用层帧：端口+标识+保留+控制域+业务标识+版本+序号+帧长+SDU"""
    return (
        bytes([0x11, 0x01, 0x01, 0x00])
        + ctrl.to_bytes(2, "little")
        + bytes([sid, 0x01])
        + (0).to_bytes(2, "little")
        + len(sdu).to_bytes(2, "little")
        + sdu
    )


def _summary(table_data: list) -> str:
    return host._get_csg_new_gen_summary(table_data)


def test_app_confirm_summary():
    """应用层确认帧摘要：应含帧类型(确认/否认)+业务标识(确认)+方向"""
    parser = CSGNewGenParser()
    # 端口11 + 标识0101 + 保留00 + 控制域0000(确认/否认,下行) + 业务标识00(确认) + 版本01 + 序号0001 + 帧长0000
    frame = bytes.fromhex("1101010000000001000100")
    table = parser.parse_to_table(frame, parse_level="app")
    summary = _summary(table)
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
    ctrl = 0x4000  # D14=1(启动), D3~D0=0(确认/否认)
    frame = bytes.fromhex("11") + bytes.fromhex("0101") + bytes.fromhex("00")
    frame += struct.pack('<H', ctrl)
    frame += bytes.fromhex("01")      # 业务标识=01(否认)
    frame += bytes.fromhex("01")      # 版本
    frame += struct.pack('<H', 0)     # 序号
    frame += struct.pack('<H', 1)     # 帧长=1
    frame += bytes.fromhex("00")      # 否认原因码=00(通信超时)
    table = parser.parse_to_table(frame, parse_level="app")
    summary = _summary(table)
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
    summary = _summary(table)
    print(f"管理消息摘要: {summary}")
    assert "网络管理消息" in summary, f"应标识为网络层管理消息: {summary}"
    assert "MMTYPE:" in summary, f"应含MMTYPE: {summary}"
    assert "关联请求" in summary, f"应含关联请求: {summary}"
    print("[OK] 网络层管理消息摘要通过")


def test_tei_list_reply_summary():
    """网络层 TEI 列表回复摘要：应体现 MMTYPE=TEI列表回复"""
    parser = CSGNewGenParser()
    # MMTYPE=0x0084 (TEI列表回复, LE: 8400)
    mgmt = bytes.fromhex("01" + "8400" + "000000" + "00" * 20)
    table = parser._parse_management_message(mgmt, base_offset=0)
    summary = _summary(table)
    print(f"TEI列表回复摘要: {summary}")
    assert "网络管理消息" in summary, summary
    assert "MMTYPE:" in summary, summary
    assert "TEI列表回复" in summary, summary
    print("[OK] 网络层TEI列表回复摘要通过")


def test_summary_format_readable():
    """摘要格式应简洁可读，包含分隔符"""
    parser = CSGNewGenParser()
    frame = bytes.fromhex("1101010000000001000100")
    table = parser.parse_to_table(frame, parse_level="app")
    summary = _summary(table)
    print(f"格式检查摘要: {summary}")
    assert "|" in summary, "多段信息应用 | 分隔"
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
    summary = _summary(table)
    print(f"含MSDU类型摘要: {summary}")
    assert "应用层报文" in summary, f"摘要应含MSDU类型'应用层报文': {summary}"
    assert "业务标识:确认" in summary, f"摘要应含业务标识: {summary}"
    print("[OK] MSDU类型在摘要中体现通过")


# ── 测试帧（0xF0）：摘要体现测试模式 ──


def test_real_test_frame_summary():
    """真实抓包测试帧（TCP EDA5 包装）：摘要应含测试帧 + 测试ID + 频段"""
    parser = CSGNewGenParser()
    app = bytes.fromhex(TCP_TEST_FRAME_HEX)[15:]
    table = parser.parse_to_table(app)
    summary = _summary(table)
    print(f"真实测试帧摘要: {summary}")
    assert "业务标识:测试帧(0xF0)" in summary, f"应标识测试帧: {summary}"
    assert "测试ID:频段切换命令" in summary, f"应含测试ID: {summary}"
    assert "通信频段:0x02" in summary, f"应含测试数据区频段: {summary}"
    print("[OK] 真实抓包测试帧摘要通过")


def test_legacy_test_frame_mode_summary():
    """1.0测试帧（表61）整帧→摘要：应含测试模式名称（模式3 = PLC物理层透传测试模式）"""
    parser = CSGNewGenParser()
    table = parser.parse_to_table(_app_frame(0x4002, SDU_TEST_1_0), parse_level="app")
    mode_rows = [r for r in table if r[0].strip() == "测试模式/配置操作"]
    assert mode_rows, f"解析器应产出测试模式字段: {[r[0] for r in table]}"
    summary = _summary(table)
    print(f"1.0测试帧摘要: {summary}")
    assert "业务标识:测试帧(0xF0)" in summary, summary
    assert "测试模式:PLC物理层透传测试模式(3)" in summary, summary
    # 有测试模式时不再重复输出测试ID（避免冗长）
    assert "测试ID:" not in summary, summary
    print("[OK] 1.0测试帧测试模式通过")


def test_test_2_0_frame_ext_id_summary():
    """2.0测试帧（Bitloading表下发）整帧→摘要：回退体现测试ID + 扩展ID"""
    parser = CSGNewGenParser()
    table = parser.parse_to_table(_app_frame(0x4002, SDU_TEST_2_0), parse_level="app")
    summary = _summary(table)
    print(f"2.0测试帧摘要: {summary}")
    assert "业务标识:测试帧(0xF0)" in summary, summary
    assert "测试ID:2.0测试" in summary, summary
    assert "扩展ID:Bitloading表下发" in summary, summary
    print("[OK] 2.0测试帧扩展ID通过")


def test_uplink_test_frame_summary():
    """上行测试帧整帧→摘要：应体现「测试帧上行」"""
    parser = CSGNewGenParser()
    table = parser.parse_to_table(_app_frame(0xC002, b""), parse_level="app")
    summary = _summary(table)
    print(f"上行测试帧摘要: {summary}")
    assert "业务标识:测试帧(0xF0)" in summary, summary
    assert "测试帧上行（确认/否认，无数据单元）" in summary, summary
    print("[OK] 上行测试帧摘要通过")


def test_non_test_uplink_frames_not_polluted():
    """回归网：非测试业务的上行帧不得被写成「测试帧上行」

    （这些业务的解析表同样只有 `上行负载` 一行，若 gate 失效就会误报）
    """
    parser = CSGNewGenParser()
    for sid in (0x01, 0x03, 0x04, 0x06):
        table = parser.parse_to_table(
            _app_frame(0xC000 | sid, b"", sid=sid), parse_level="app"
        )
        assert host._extract_test_mode_content(table) == "", (
            f"sid=0x{sid:02X} 不应产出测试帧文本"
        )
        summary = _summary(table)
        assert "测试帧" not in summary and "测试ID" not in summary, f"sid=0x{sid:02X}: {summary}"
    print("[OK] 非测试上行业务帧未被污染通过")


def test_non_test_frame_has_no_mode_text():
    """非测试类报文不应产生测试模式片段（避免污染其它帧摘要）"""
    parser = CSGNewGenParser()
    frame = bytes.fromhex("1101010000000001000100")
    table = parser.parse_to_table(frame, parse_level="app")
    assert host._extract_test_mode_content(table) == "", "确认帧不应有测试模式文本"
    summary = _summary(table)
    assert "测试模式" not in summary and "测试ID" not in summary, summary
    print("[OK] 非测试帧无测试模式片段通过")


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
    print()
    test_real_test_frame_summary()
    print()
    test_legacy_test_frame_mode_summary()
    print()
    test_test_2_0_frame_ext_id_summary()
    print()
    test_uplink_test_frame_summary()
    print()
    test_non_test_uplink_frames_not_polluted()
    print()
    test_non_test_frame_has_no_mode_text()
    print("=" * 60)
    print("全部测试通过 ✓")
