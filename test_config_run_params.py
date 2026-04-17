"""测试配置运行参数的表格显示效果"""
from protocol_parser import ProtocolFrameParser

def test_config_run_params_table():
    parser = ProtocolFrameParser()
    
    # 测试帧：配置运行参数（AFN=04H, DI=E8020474）
    # 参数ID=0x03（异常离网锁定时间），参数值=0x001F（31分钟）
    frame_hex = '68 17 00 40 04 07 74 04 02 E8 01 10 04 26 90 09 01 03 02 1F 00 A6 16'
    frame_bytes = bytes.fromhex(frame_hex.replace(' ', ''))
    
    print("测试帧:", frame_hex)
    print("=" * 100)
    
    # 获取表格数据
    table_data = parser.parse_to_table(frame_bytes)
    
    # 打印表格
    print(f"{'字段':<30s} | {'原始值':<20s} | {'解析值':<25s} | 说明")
    print("-" * 130)
    for row in table_data:
        field, raw, parsed, comment, start, end = row
        print(f"{field:<30s} | {raw:<20s} | {parsed:<25s} | {comment}")

if __name__ == "__main__":
    test_config_run_params_table()
