"""南网新一代通感一体化 - 批量解析级别与帧起始定位测试

覆盖:
  1. 解析器 pb_only/fc_pb/fc_only/app 级别（直接调 parse_to_table）
  2. GUI 预处理 _strip_csg_new_gen_frame_prefix：FC起始定位 / PB-only保留 / app扫描 / 监控标记分派

直接运行: python test_csg_batch_parse_level.py
"""
import re
from csg_new_gen_parser import CSGNewGenParser

# 真实并发抄读完整MPDU帧（FC 16B + PB 136B）
REAL_FRAME = bytes.fromhex(
    "19012000030000417804005B1000000000000000030045000210004111"
    "0805000301110101000160020109003700640198900000011100682119"
    "70051E0025000210006801110068211968110433333433661610006801"
    "1100682119681104343433376B16A89D0543" + "00" * 44 + "0B8F8D"
)
FC_LEN = 16
PB_ONLY = REAL_FRAME[FC_LEN:]  # 剥FC后的物理块


def _find(table, name):
    for r in table:
        if r[0] == name:
            return r
    return None


# ── 解析器级别测试 ──

def test_parser_fc_pb():
    """fc_pb 级别: 完整MPDU应解析到业务标识2与2条抄读报文"""
    t = CSGNewGenParser().parse_to_table(REAL_FRAME, parse_level="fc_pb")
    assert _find(t, "FC校验序列(FCS)"), "fc_pb应解析FC头"
    sid = _find(t, "业务标识")
    assert sid and sid[2] == "2", f"业务标识应为2, 实际: {sid}"
    cnt = _find(t, "报文条数")
    assert cnt and cnt[2] == "2", f"报文条数应为2, 实际: {cnt}"
    print("[OK] 解析器 fc_pb 级别通过")


def test_parser_fc_only():
    """fc_only 级别: 仅解析FC头16字节，无PB/MSDU"""
    t = CSGNewGenParser().parse_to_table(REAL_FRAME, parse_level="fc_only")
    assert _find(t, "定界符类型"), "fc_only应解析定界符类型"
    assert _find(t, "FC校验序列(FCS)"), "fc_only应解析FC校验序列"
    # 无物理块头/MSDU负载
    assert not _find(t, "物理块头"), "fc_only不应解析物理块"
    assert not _find(t, "业务标识"), "fc_only不应解析应用层"
    print("[OK] 解析器 fc_only 级别通过")


def test_parser_pb_only():
    """pb_only 级别: 仅PB输入应从物理块头开始解析, 还原业务标识2"""
    t = CSGNewGenParser().parse_to_table(PB_ONLY, parse_level="pb_only", pb_frame_type="sof")
    pbh = _find(t, "物理块头")
    assert pbh, "pb_only应从物理块头开始解析"
    assert not _find(t, "定界符类型"), "pb_only无FC, 不应出现定界符类型"
    assert not _find(t, "FC校验序列(FCS)"), "pb_only无FC, 不应出现FCS"
    sid = _find(t, "业务标识")
    assert sid and sid[2] == "2", f"pb_only业务标识应为2, 实际: {sid}"
    cnt = _find(t, "报文条数")
    assert cnt and cnt[2] == "2", f"pb_only报文条数应为2, 实际: {cnt}"
    print("[OK] 解析器 pb_only 级别通过")


def test_parser_app():
    """app 级别: 应用层报文输入(从端口0x11起)应解析业务标识2"""
    # app输入 = 报文端口号(0x11)起 = 帧内偏移 FC16+PB头4+MAC头12 + VLAN1 + MSDU类型1 = 34
    app_input = REAL_FRAME[34:]
    assert app_input[0] == 0x11, f"app输入应从端口0x11开始, 实际首字节: {app_input[0]:#X}"
    t = CSGNewGenParser().parse_to_table(app_input, parse_level="app")
    sid = _find(t, "业务标识")
    assert sid and sid[2] == "2", f"app业务标识应为2, 实际: {sid}"
    print("[OK] 解析器 app 级别通过")


# ── GUI 预处理函数测试（通过绑定未绑定方法到桩对象）──

class _Stub:
    """复用 MainWindow._strip_csg_new_gen_frame_prefix 的最小桩对象"""
    CSG_MONITOR_PREFIX = "> 接收机 Has Get"

    def _strip_csg_monitor_prefix(self, text):
        # 模拟监控路径: 仅保留含标记的行, 剥15字节监控头
        out = []
        for line in text.splitlines():
            idx = line.find(self.CSG_MONITOR_PREFIX)
            if idx < 0:
                continue
            tail = line[idx + len(self.CSG_MONITOR_PREFIX):].strip()
            c = re.sub(r'[^0-9A-Fa-f]', '', tail).upper()
            # 跳15字节监控头(30 hex chars)
            if len(c) > 30:
                c = c[30:]
            if len(c) >= 8:
                out.append(c)
        return '\n'.join(out)


def _get_strip_fn():
    import main_gui
    return main_gui.MainWindow._strip_csg_new_gen_frame_prefix


def test_strip_fc_start_locate():
    """fc_pb: 带日志前缀的行应定位到FC起始字节(低4位∈{8,9,A,B})"""
    strip = _get_strip_fn()
    stub = _Stub()
    hexstr = REAL_FRAME.hex().upper()
    line = f"Line 339: 260718-111145: {hexstr}"
    out = strip(stub, line, "fc_pb")
    assert out.startswith("1901200003"), f"应定位到FC起始0x19, 实际: {out[:20]}"
    print("[OK] 预处理 fc_pb FC起始定位通过")


def test_strip_discard_non_frame_line():
    """fc_pb: 不含FC起始特征的行(纯时间戳)应被丢弃"""
    strip = _get_strip_fn()
    stub = _Stub()
    out = strip(stub, "15:50:23 186 HPLC_STA_test", "fc_pb")
    assert out == "", f"非报文行应被丢弃, 实际: {out!r}"
    print("[OK] 预处理 非报文行丢弃通过")


def test_strip_pb_only_keep():
    """pb_only: 输入即物理块, 直接保留整行(无FC签名扫描)"""
    strip = _get_strip_fn()
    stub = _Stub()
    hexstr = PB_ONLY.hex().upper()
    out = strip(stub, hexstr, "pb_only")
    assert out == hexstr, f"pb_only应整行保留, 实际: {out[:20]}"
    print("[OK] 预处理 pb_only 整行保留通过")


def test_strip_app_scan():
    """app: 扫描端口0x11定位应用层报文起始"""
    strip = _get_strip_fn()
    stub = _Stub()
    app_hex = REAL_FRAME[32:].hex().upper()[:40]  # 端口0x11起
    line = "junk_prefix: " + app_hex
    out = strip(stub, line, "app")
    assert out.startswith("11"), f"app应定位到0x11, 实际: {out[:10]}"
    print("[OK] 预处理 app 应用层起始定位通过")


def test_strip_monitor_dispatch():
    """含监控标记的文本应分派到监控剥离路径"""
    strip = _get_strip_fn()
    stub = _Stub()
    hexstr = REAL_FRAME.hex().upper()
    # 标记后跟15字节监控头(30 hex) + 报文
    mon = f"15:50:23 186 -> 接收机 Has Get {'AA'*15} {hexstr}"
    out = strip(stub, mon, "fc_pb")
    # 监控路径应剥15字节头并保留报文
    assert out.startswith("1901200003"), f"监控路径应保留报文, 实际: {out[:20]}"
    print("[OK] 预处理 监控标记分派通过")


def test_strip_multi_frame_batch():
    """多帧批量: 每行定位FC起始, 非报文行丢弃"""
    strip = _get_strip_fn()
    stub = _Stub()
    hexstr = REAL_FRAME.hex().upper()
    text = f"15:50:23 时间行\nLine1: ts: {hexstr}\n纯文本备注\nLine2: ts: {hexstr}"
    out = strip(stub, text, "fc_pb")
    lines = [l for l in out.splitlines() if l]
    assert len(lines) == 2, f"应保留2帧报文, 实际: {len(lines)}帧"
    for l in lines:
        assert l.startswith("1901200003"), f"每帧应从FC起始, 实际: {l[:20]}"
    print("[OK] 预处理 多帧批量定位通过")

def test_strip_tcp_eda5_prefix():
    """TCP 包装报文: 检测 EDA5 前缀, 从 ED 偏移 15 字节定位 FC 起始"""
    strip = _get_strip_fn()
    stub = _Stub()
    # 完整日志行: 流程日志前缀 + 引号 + EDA5 TCP 头(15B) + FC+PB + 结尾标识
    tcp_hex = (
        "EDA5000002EF0149C84C27010088000900F0FF010000417804005B10EA9809"
        "0000000003001300FF0F00001F0102000301110101000260F0010000050002"
        "00010002AD4353F8004A95AF" + "00" * 50 + "FFEE"
    )
    log = f'2026-07-28 19:35:44 383: 流程日志：Rx(5)@DESKTOP: "EDA2junk" "{tcp_hex}\'O"'
    # 该日志含冒号分隔，最后一个冒号后为报文（含单引号），清洗后应以EDA5开头
    # 构造更接近真实的单行: 时间戳 + 冒号 + 报文
    log = f"流程日志：Rx(5)@HOST: {tcp_hex}"
    out = strip(stub, log, "fc_pb")
    assert out.startswith("0900F0FF"), f"EDA5应剥15B头定位到FC(0x09 00 F0 FF), 实际: {out[:16]}"
    # 端到端: 剥后应可解析为有效帧
    import importlib, sys
    sys.path.insert(0, 'E:/python/南网解析工具')
    import csg_new_gen_parser
    importlib.reload(csg_new_gen_parser)
    t = csg_new_gen_parser.CSGNewGenParser().parse_to_table(
        bytes.fromhex(out), parse_level="auto")
    sid = _find(t, "业务标识")
    assert sid and sid[2] == "240", f"TCP报文应为业务标识240(测试帧), 实际: {sid}"
    crc = _find(t, "完整性校验(CRC-32)")
    assert crc and "校验通过" in crc[3], f"CRC应通过, 实际: {crc}"
    print("[OK] 预处理 EDA5 TCP包装前缀剥离通过")

def test_strip_tcp_eda5_with_quotes():
    """EDA5 含日志引号包裹: 最后冒号后取hex后应仍正确剥15字节"""
    strip = _get_strip_fn()
    stub = _Stub()
    tcp_hex = (
        "EDA5000002EF0149C84C27010088000900F0FF010000417804005B10EA9809"
        "0000000003001300FF0F00001F0102000301110101000260F0010000050002"
        "00010002AD4353F8004A95AF" + "00" * 50 + "FFEE"
    )
    log = f'Rx(5)@DESKTOP: "len:169: {tcp_hex}\'O"'
    out = strip(stub, log, "auto")
    assert out.startswith("0900F0FF"), f"带引号日志应定位到FC, 实际: {out[:16]}"
    print("[OK] 预处理 EDA5 含引号日志剥离通过")

def test_parser_multi_pb_uplink():
    """多物理块重组: 上行并发抄读帧(2个PB, MAC帧跨PB), 完整还原2条抄读报文"""
    raw = (
        "19 02 10 00 08 5B 2A 00 B3 01 00 00 20 20 31 3D 00 00 00 00 "
        "13 00 4C 00 01 20 00 11 00 08 A4 90 00 01 11 01 01 00 01 80 "
        "02 01 09 00 3E 00 01 11 00 68 21 19 64 01 98 90 00 00 00 00 "
        "00 2D 00 02 14 00 68 01 11 00 68 21 19 68 91 08 33 33 34 33 "
        "34 35 33 33 00 04 FF 86 01 00 00 00 B9 16 14 00 68 01 11 00 "
        "68 21 19 68 91 08 34 34 33 37 3A 35 33 33 C4 16 A5 46 1B 15 "
        + "00 " * 36 + "67 70 4F"
    )
    import re
    frame = bytes.fromhex(re.sub(r'[^0-9A-Fa-f]', '', raw))
    t = CSGNewGenParser().parse_to_table(frame, parse_level="auto")
    # 应识别2个PB
    pbh = [r for r in t if r[0].startswith("物理块头[")]
    assert len(pbh) == 2, f"应解析2个PB头, 实际: {len(pbh)}"
    # MSDU负载应完整(76字节, 跨2个PB重组)
    msdu = _find(t, "MSDU负载")
    assert msdu and msdu[2] == "76字节", f"MSDU负载应为76字节(多PB重组), 实际: {msdu}"
    crc = _find(t, "完整性校验(CRC-32)")
    assert crc and "校验通过" in crc[3], f"CRC-32应校验通过, 实际: {crc}"
    # 应答方向=上行, 业务标识2, 2条抄读报文
    ctrl = _find(t, "  传输方向位(D15)")
    assert ctrl and "上行" in ctrl[3], f"应为上行, 实际: {ctrl}"
    sid = _find(t, "业务标识")
    assert sid and sid[2] == "2", f"业务标识应为2, 实际: {sid}"
    cnt = _find(t, "报文条数")
    assert cnt and cnt[2] == "2", f"报文条数应为2, 实际: {cnt}"
    msgs = [r for r in t if r[0].endswith("内容")]
    assert len(msgs) == 2, f"应解析2条抄读报文, 实际: {len(msgs)}"
    assert not _find(t, "剩余数据"), "存在未解析剩余数据"
    print("[OK] 解析器 多PB重组(上行并发抄读)通过")


def main():
    print("=" * 56)
    print("南网新一代批量解析级别与帧起始定位测试")
    print("=" * 56)
    test_parser_fc_pb()
    test_parser_fc_only()
    test_parser_pb_only()
    test_parser_app()
    test_parser_multi_pb_uplink()
    test_strip_fc_start_locate()
    test_strip_discard_non_frame_line()
    test_strip_pb_only_keep()
    test_strip_app_scan()
    test_strip_monitor_dispatch()
    test_strip_multi_frame_batch()
    test_strip_tcp_eda5_prefix()
    test_strip_tcp_eda5_with_quotes()
    print("=" * 56)
    print("[OK] 全部测试通过")


if __name__ == '__main__':
    main()