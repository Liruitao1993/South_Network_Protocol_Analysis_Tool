"""
测试PLC RF协议解析器
"""
from plc_rf_parser import PLCRFProtocolParser

def test_frame(hex_str, description):
    """测试解析一帧"""
    print(f"\n{'='*60}")
    print(f"测试: {description}")
    print(f"报文: {hex_str}")
    print(f"{'='*60}")
    
    # 清理输入
    clean = hex_str.replace(" ", "").replace("\n", "")
    frame_bytes = bytes.fromhex(clean)
    
    # 解析
    parser = PLCRFProtocolParser()
    result = parser.parse(frame_bytes)
    
    # 打印结果
    print(f"解析状态: {result['解析状态']}")
    if result.get('错误信息'):
        print(f"错误: {result['错误信息']}")
    
    if result.get('帧头'):
        print(f"帧头: {result['帧头']}")
    
    if result.get('长度域'):
        print(f"长度域: {result['长度域']}")
    
    if result.get('控制域'):
        print(f"控制域: {result['控制域']}")
    
    if result.get('命令字'):
        print(f"命令字: {result['命令字']}")
    
    if result.get('用户数据区'):
        print(f"用户数据区: {result['用户数据区']}")
    
    if result.get('校验和'):
        print(f"校验和: {result['校验和']}")
    
    # 表格解析
    print(f"\n表格解析结果:")
    table_data = parser.parse_to_table(frame_bytes)
    for row in table_data:
        field, raw, parsed, comment, start, end = row
        indent = "  " if field.startswith("  ") else ""
        field_name = field.strip()
        print(f"  {indent}{field_name:20s} | {raw:25s} | {parsed:20s} | {comment}")


if __name__ == "__main__":
    # 测试1: 文档示例 - 模块获取电表表号（请求）✓ CRC正确
    test_frame(
        "02 00 05 C0 20 01 00 99",
        "文档示例: 模块获取电表表号（请求）✓"
    )
    
    # 测试2: 文档示例 - 模块信息传输 ✓ CRC正确
    test_frame(
        "02 00 17 C0 20 03 01 00 31 32 33 34 35 36 37 38 00 00 00 00 00 00 00 00 92 BB",
        "文档示例: 模块将自身信息传输至电表 ✓"
    )
    
    print(f"\n{'='*60}")
    print("所有测试完成！")
    print(f"{'='*60}")
