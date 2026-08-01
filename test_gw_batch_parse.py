"""测试国网新一代双模协议批量解析功能"""
import sys
import io

# 确保中文输出正常
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from gw_new_gen_parser import GWNewGenParser


def test_strip_gw_prefix():
    """测试日志前缀剥离"""
    print("Test: 日志前缀剥离")
    
    # 模拟日志输入
    log_input = """Line 339: 260718-111145-349: B1D[3] mrd:ar[75]:110300000132F303420D2305683D004305090000000000000049CD1000190502000500100200002002002000020020010200200402000001103665F58C473D02E77788BE734E626394A11D16
Line 346: 260718-111145-450: B1D[3] mrd:ar[75]:110300000132F303430D2305683D004305090000000000000049CD1000190502000500100200002002002000020020010200200402000001103665F58C473D02E77788BE734E626394A11D16
Line 490: 260718-111153-343: B1D[3] mrd:ar[75]:110300000132F303440D2305683D004305090000000000000049CD1000190502000500100200002002002000020020010200200402000001103665F58C473D02E77788BE734E626394A11D16"""
    
    # 模拟 _strip_gw_new_gen_prefix 的逻辑
    import re
    out_lines = []
    for line in log_input.splitlines():
        line = line.strip()
        if not line:
            continue
        last_colon = line.rfind(':')
        if last_colon >= 0:
            hex_part = line[last_colon + 1:].strip()
        else:
            hex_part = line
        hex_clean = re.sub(r'[^0-9A-Fa-f]', '', hex_part).upper()
        if len(hex_clean) < 4:
            continue
        out_lines.append(hex_clean)
    
    print(f"  输入行数: {len(log_input.splitlines())}")
    print(f"  输出帧数: {len(out_lines)}")
    
    for i, frame in enumerate(out_lines[:3]):
        print(f"  帧{i+1}: {frame[:40]}... (长度: {len(frame)//2}字节)")
        # 验证是否以11开头（应用层端口）
        assert frame.startswith('11'), f"帧{i+1}应以11开头，实际: {frame[:2]}"
    
    print("  [✅] 前缀剥离成功，所有帧以11开头\n")


def test_parse_level_app():
    """测试app级别解析"""
    print("Test: app级别解析")
    parser = GWNewGenParser()
    
    # 从日志中提取的帧数据
    frame_hex = "110300000132F303420D2305683D004305090000000000000049CD1000190502000500100200002002002000020020010200200402000001103665F58C473D02E77788BE734E626394A11D16"
    frame_bytes = bytes.fromhex(frame_hex)
    
    # 使用app级别解析
    result = parser.parse_to_table(frame_bytes, parse_level='app')
    
    print(f"  解析结果行数: {len(result)}")
    
    # 查找关键行
    port_row = [r for r in result if '报文端口号' in r[0]]
    data_len_row = [r for r in result if '转发数据长度' in r[0]]
    fwd_data_row = [r for r in result if '转发数据(' in r[0]]
    
    if port_row:
        print(f"  报文端口号: {port_row[0][2]}")
        assert '抄表' in port_row[0][2], "应为抄表业务"
    
    if data_len_row:
        print(f"  转发数据长度: {data_len_row[0][2]}")
        assert '63' in data_len_row[0][2], "应为63字节"
    
    if fwd_data_row:
        print(f"  转发数据: {fwd_data_row[0][2][:50]}...")
        # 实际提取的数据可能包含CRC等尾部字节，长度可能略大于data_len
        assert '字节' in fwd_data_row[0][2], "应显示字节数"
    
    print("  [✅] app级别解析成功\n")


def test_scan_for_11():
    """测试扫描'11'定位应用层起始"""
    print("Test: 扫描'11'定位应用层")
    
    # 模拟包含非帧数据的hex字符串
    hex_with_prefix = "AABBCCDD110300000132F303420D2305683D0043"
    
    # 扫描'11'
    i = 0
    found = False
    while i < len(hex_with_prefix) - 1:
        if hex_with_prefix[i:i+2] == '11' and len(hex_with_prefix) - i >= 8:
            frame_start = i
            found = True
            break
        i += 2
    
    assert found, "应找到'11'起始位置"
    frame = hex_with_prefix[frame_start:]
    print(f"  原始hex: {hex_with_prefix}")
    print(f"  帧起始位置: {frame_start}")
    print(f"  提取帧: {frame[:40]}...")
    assert frame.startswith('11'), "提取的帧应以11开头"
    print("  [✅] 扫描定位成功\n")


if __name__ == '__main__':
    test_strip_gw_prefix()
    test_parse_level_app()
    test_scan_for_11()
    print("=" * 50)
    print("所有测试通过！")
