"""测试运行参数解析的表格显示效果"""
from protocol_parser import ProtocolFrameParser

def test_run_params_table():
    parser = ProtocolFrameParser()
    
    # 测试帧：返回查询运行参数信息
    frame_hex = '68 17 00 88 03 06 74 03 04 E8 01 10 04 26 90 09 01 03 02 1E 00 EC 16'
    frame_bytes = bytes.fromhex(frame_hex.replace(' ', ''))
    
    print("测试帧:", frame_hex)
    print("=" * 100)
    
    # 获取表格数据
    table_data = parser.parse_to_table(frame_bytes)
    
    # 打印表格
    print(f"{'字段':<30s} | {'原始值':<20s} | {'解析值':<15s} | 说明")
    print("-" * 120)
    for row in table_data:
        field, raw, parsed, comment, start, end = row
        print(f"{field:<30s} | {raw:<20s} | {parsed:<15s} | {comment}")

if __name__ == "__main__":
    test_run_params_table()
