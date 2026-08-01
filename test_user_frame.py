"""测试用户实际帧数据的PB头+MAC头解析"""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from gw_new_gen_parser import GWNewGenParser


def test_user_frame():
    """测试用户提供的实际帧数据"""
    print("Test: 用户实际帧数据解析")
    parser = GWNewGenParser()
    
    # 用户提供的帧数据（从截图）- 简化版本用于测试
    # C0 00 00 FF = PB头 (序列号=0x00C0, 聚合标志=0)
    # 2F 03 08 00 00 34 80 11 08 00 39 00 = MAC短帧头(12字节)
    #   2F: 帧头类型=1(短), 版本=1(标准), SNID高=0, 发送序号高=2
    #   03: 发送序号低=3, 总序号=0x203
    #   08 00: MSDU长度=8
    #   00: 目的TEI低=0
    #   34: 目的TEI高=0, 源TEI低=3
    #   80: 源TEI高=8, 源TEI=0x830=2096
    #   11: SNID低=1, 重启次数=1
    #   08: 路由跳数=8, 广播方向=0
    #   00: 发送类型=0(单播), 发送次数限值=0
    #   39 00: MSDU序列号=0x0039
    frame_hex = "C00000FF2F0308000034801108003900"
    
    frame_bytes = bytes.fromhex(frame_hex)
    print(f"  帧长度: {len(frame_bytes)}字节")
    print(f"  前4字节(PB头): {frame_bytes[:4].hex().upper()}")
    print(f"  字节5-16(MAC头): {frame_bytes[4:16].hex().upper()}")
    
    # PB头解析
    pb_seq = (frame_bytes[1] << 8) | frame_bytes[0]
    agg_flag = frame_bytes[2] & 0x01
    print(f"\n  PB序列号: 0x{pb_seq:04X} ({pb_seq})")
    print(f"  聚合标志: {agg_flag} ({'多MAC帧' if agg_flag else '单MAC帧'})")
    
    # MAC头解析
    mac_byte0 = frame_bytes[4]
    hdr_type = mac_byte0 & 0x01
    version = (mac_byte0 >> 1) & 0x03
    
    print(f"\n  MAC字节0: 0x{mac_byte0:02X} = {mac_byte0:08b}")
    print(f"    帧头类型(bit0): {hdr_type} ({'短帧头(12B)' if hdr_type else '长帧头(32B)'})")
    print(f"    版本(bits[2:1]): {version} ({['保留','标准帧','单跳帧','保留'][version]})")
    
    # 使用pb_only模式解析
    result = parser.parse_to_table(frame_bytes, parse_level='pb_only', frame_type=1)
    
    print(f"\n  解析结果行数: {len(result)}")
    
    # 查找关键行
    pbh_row = [r for r in result if '物理块头' in r[0]]
    pb_seq_row = [r for r in result if 'PB序列号' in r[0]]
    agg_row = [r for r in result if '聚合标志' in r[0]]
    mac_type_row = [r for r in result if 'MAC帧头类型' in r[0]]
    mac_ver_row = [r for r in result if 'MAC版本' in r[0]]
    src_tei_row = [r for r in result if '原始源TEI' in r[0]]
    dst_tei_row = [r for r in result if '原始目的TEI' in r[0]]
    
    if pbh_row:
        print(f"\n  ✅ 物理块头: {pbh_row[0][2]}")
    if pb_seq_row:
        print(f"  ✅ PB序列号: {pb_seq_row[0][2]}")
    if agg_row:
        print(f"  ✅ 聚合标志: {agg_row[0][2]}")
    if mac_type_row:
        print(f"  ✅ MAC帧头类型: {mac_type_row[0][2]}")
    if mac_ver_row:
        print(f"  ✅ MAC版本: {mac_ver_row[0][2]}")
    if src_tei_row:
        print(f"  ✅ 原始源TEI: {src_tei_row[0][2]}")
    if dst_tei_row:
        print(f"  ✅ 原始目的TEI: {dst_tei_row[0][2]}")
    
    print("\n  [✅] 用户实际帧数据解析成功\n")


if __name__ == '__main__':
    test_user_frame()
