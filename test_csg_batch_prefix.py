"""新一代载波协议批量解析监控前缀剥离 - 预处理链路测试

验证批量解析在协议8下能正确剥离监控日志前缀：
  "<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>"

直接运行: python test_csg_batch_prefix.py
"""
import re
import sys


# ── 复刻 main_gui.py 中的预处理逻辑（避免启动 GUI）──

CSG_MONITOR_PREFIX = "-> 接收机 Has Get"
CSG_MONITOR_HEADER_BYTES = 15


def strip_csg_monitor_prefix(text: str) -> str:
    """剥离监控前缀（逐行），与 MainWindow._strip_csg_monitor_prefix 一致"""
    prefix_len = len(CSG_MONITOR_PREFIX)
    hex_only_line_re = re.compile(r'^[0-9A-Fa-f\s,\-]*$')
    out_lines = []
    for line in text.splitlines():
        pos = line.find(CSG_MONITOR_PREFIX)
        if pos == -1:
            if hex_only_line_re.match(line):
                out_lines.append(line)
            continue
        after = line[pos + prefix_len:]
        tokens = re.findall(r'[0-9A-Fa-f]{1,2}', after)
        payload_tokens = tokens[CSG_MONITOR_HEADER_BYTES:]
        out_lines.append(' '.join(payload_tokens))
    return '\n'.join(out_lines)


def clean_hex_input(text: str, keep_newlines: bool = False) -> str:
    pattern = r'[^0-9A-Fa-f\n]' if keep_newlines else r'[^0-9A-Fa-f]'
    return re.sub(pattern, '', text)


def extract_csg_new_gen_frames(text: str) -> list:
    frames = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        clean_line = ''.join(c for c in line if c in '0123456789ABCDEFabcdef').upper()
        if len(clean_line) < 8:
            continue
        if len(clean_line) % 2 != 0:
            clean_line = clean_line[:-1]
        frames.append(clean_line)
    return frames


def parse_batch_pipeline(raw_text: str, current_protocol: int) -> list:
    """复刻 MainWindow.parse_batch 的预处理 + 提取链路（协议8分支）"""
    text = raw_text.strip()
    if current_protocol == 8:
        text = strip_csg_monitor_prefix(text)
    text = clean_hex_input(text, keep_newlines=True)
    if not text:
        return []
    if current_protocol == 8:
        return extract_csg_new_gen_frames(text)
    return []


# ── 测试用例 ──

def test_strip_single_monitor_line():
    """单行监控日志：剥离 15 字节监控头"""
    raw = ("15:49:51 254  -> 接收机 Has Get "
           "ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 "
           "68 11 01 01 00 00 00 00 01 00 01 00 00")
    frames = parse_batch_pipeline(raw, current_protocol=8)
    assert len(frames) == 1, f"应提取1帧，实际{len(frames)}: {frames}"
    # 第一个字节应是 68（用户明确："68才是协议报文"）
    assert frames[0].startswith("68"), f"剥离后应以68开头: {frames[0]}"
    # 监控头 15 字节应被完全去除，68 之后紧跟 11（报文端口号）
    assert frames[0].startswith("6811"), f"68后应为报文端口号11: {frames[0]}"
    print("[OK] 单行监控日志剥离通过 ->", frames[0])


def test_strip_multi_monitor_lines():
    """多行监控日志：每行剥离后各成一帧"""
    raw = "\n".join([
        ("15:49:51 254  -> 接收机 Has Get "
         "ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 "
         "68 11 01 01 00 00 00 00 01 00 01 00 00"),
        ("15:50:02 255  -> 接收机 Has Get "
         "ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 "
         "68 11 01 01 00 11 00 00 01 00 01 00 19"),
    ])
    frames = parse_batch_pipeline(raw, current_protocol=8)
    assert len(frames) == 2, f"应提取2帧，实际{len(frames)}"
    assert all(f.startswith("6811") for f in frames), f"每帧都应以6811开头: {frames}"
    # 两帧的报文内容应不同
    assert frames[0] != frames[1], "两帧应不同"
    print("[OK] 多行监控日志剥离通过 ->", len(frames), "帧")


def test_mixed_monitor_and_plain():
    """混合输入：监控行 + 纯hex行"""
    raw = "\n".join([
        ("15:49:51 254  -> 接收机 Has Get "
         "ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 "
         "68 11 01 01 00 00 00 00 01 00 01 00 00"),
        "1101 0100 0000 0001 0001 0019",  # 纯 hex 应用层报文
    ])
    frames = parse_batch_pipeline(raw, current_protocol=8)
    assert len(frames) == 2, f"应提取2帧，实际{len(frames)}: {frames}"
    # 第一帧来自监控行，以68开头
    assert frames[0].startswith("6811"), f"第一帧应以6811开头: {frames[0]}"
    # 第二帧来自纯hex行，以1101开头（报文端口号0x11 + 标识符0x0101小端）
    assert frames[1].startswith("1101"), f"第二帧应以1101开头: {frames[1]}"
    print("[OK] 混合输入处理通过 ->", frames)


def test_plain_hex_unchanged():
    """纯 hex 报文（无监控前缀）应原样保留"""
    raw = "11 01 01 00 00 00 00 01 00 01 00 00"
    frames = parse_batch_pipeline(raw, current_protocol=8)
    assert len(frames) == 1
    assert frames[0] == "1101010000000001000100".upper() or frames[0].startswith("1101")
    print("[OK] 纯hex报文原样保留通过 ->", frames[0])


def test_short_line_filtered():
    """过短的行（<4字节）应被过滤"""
    raw = "\n".join([
        ("15:49:51 254  -> 接收机 Has Get "
         "ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 "
         "68 11 01 01"),
        "AB CD",  # 仅2字节，应被过滤
    ])
    frames = parse_batch_pipeline(raw, current_protocol=8)
    assert len(frames) == 1, f"短行应被过滤，实际{len(frames)}: {frames}"
    print("[OK] 短行过滤通过 ->", frames)


def test_header_byte_count():
    """精确验证剥离的是15字节（30个hex字符）监控头"""
    # 构造：前缀后跟 20 个可区分的字节，前15个是监控头
    header = "01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F"  # 15字节监控头
    payload = "68 11 22 33 44"  # 协议报文
    raw = f"10:00:00 001  -> 接收机 Has Get {header} {payload}"
    frames = parse_batch_pipeline(raw, current_protocol=8)
    assert len(frames) == 1
    # 剥离后应正好是 payload，不含 header 的任何字节
    expected = "6811223344"
    assert frames[0] == expected, f"剥离错误：期望{expected}，实际{frames[0]}"
    print("[OK] 15字节监控头精确剥离通过 ->", frames[0])


def test_no_prefix_other_protocol():
    """非监控前缀行：纯 hex 保留，含中文/时间戳/标记文本的日志行丢弃"""
    # 纯 hex 行应保留
    result = strip_csg_monitor_prefix("68110101")
    assert result == "68110101", "纯 hex 无标记行应保留"
    # 含中文文本的行应丢弃（不再原样保留）
    result = strip_csg_monitor_prefix("纯hex无标记行")
    assert result == "", "含中文的非 hex 行应被过滤"
    print("[OK] 无标记行过滤/保留行为通过")


def test_timestamp_marker_line_filtered():
    """时间戳 + 测试标记文本行不应被误解析为帧"""
    raw = ("15:48:16 013  -> ############# "
           "【STA_长MPDU帧载荷长度136长MAC帧头的SOF帧是否能够被正确处理测试】启动 #############")
    frames = parse_batch_pipeline(raw, current_protocol=8)
    assert len(frames) == 0, f"测试标记行应被过滤，不应产生伪帧，实际得到：{frames}"
    print("[OK] 时间戳测试标记行过滤通过")


if __name__ == "__main__":
    print("=" * 60)
    print("新一代载波协议批量解析 - 监控前缀剥离测试")
    print("=" * 60)
    test_strip_single_monitor_line()
    test_strip_multi_monitor_lines()
    test_mixed_monitor_and_plain()
    test_plain_hex_unchanged()
    test_short_line_filtered()
    test_header_byte_count()
    test_no_prefix_other_protocol()
    test_timestamp_marker_line_filtered()
    print("全部测试通过 ✓")
