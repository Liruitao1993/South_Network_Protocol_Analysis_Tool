"""
分析报文: 68 2A 00 C0 03 01 02 03 00 E8 02 00 04 00 04 3C 99 99 99 99 99 99 F8 07 01 00 20 00 01 02 16 48 53 30 30 01 09 19 00 13 F7 16

DI=E8:00:03:02 查询本地通信模块运行模式信息

根据 MD 文档，上行数据内容格式：
- 本地通信模式字: 1字节 (BS)
- 最大支持的协议报文长度: 2字节 (BIN)
- 文件传输支持的最大单包长度: 2字节 (BIN)
- 升级操作等待时间: 1字节 (BIN)
- 主节点地址: 6字节 (BIN)
- 支持的最大从节点数量: 2字节 (BIN)
- 当前从节点数量: 2字节 (BIN)
- 支持单次读写从节点信息的最大数量: 2字节 (BIN)
- 通信模块接口协议发布日期: 3字节 (YYMMDD)
- 厂商代码和版本信息: 9字节

总长度: 1+2+2+1+6+2+2+2+3+9 = 30字节
"""

frame = bytes.fromhex('682A00C00301020300E802000400043C999999999999F80701002000010216485330300109190013F716')

print('报文分析:')
print(f'总长度: {len(frame)} 字节')
print(f'起始字符: 0x{frame[0]:02X}')
print(f'长度域: 0x{frame[1]:02X}{frame[2]:02X} = {int.from_bytes(frame[1:3], "little")}')
print(f'控制域: 0x{frame[3]:02X}')
print(f'用户数据区: {frame[4:-2].hex().upper()}')
print(f'校验和: 0x{frame[-2]:02X}')
print(f'结束符: 0x{frame[-1]:02X}')

# 校验和验证
checksum = sum(frame[4:-2]) & 0xFF
print(f'\n计算校验和: 0x{checksum:02X}')
print(f'校验结果: {"通过" if checksum == frame[-2] else "失败"}')

# 解析用户数据区
user_data = frame[4:-2]
print(f'\n用户数据区分析 ({len(user_data)} 字节):')
print(f'  字节0 (AFN): 0x{user_data[0]:02X}')
print(f'  字节1 (SEQ): 0x{user_data[1]:02X}')
print(f'  字节2 (地址域标识): 0x{user_data[2]:02X}')

# DI 解析
di_bytes = user_data[3:7]
di_value = int.from_bytes(di_bytes, 'little')
print(f'  字节3-6 (DI): {di_bytes.hex().upper()}')
print(f'    DI 小端序值: 0x{di_value:08X}')
print(f'    DI3: 0x{di_bytes[3]:02X}')
print(f'    DI2: 0x{di_bytes[2]:02X}')
print(f'    DI1: 0x{di_bytes[1]:02X}')
print(f'    DI0: 0x{di_bytes[0]:02X}')

# 数据内容解析 (从字节7开始)
data_content = user_data[7:]
print(f'\n  数据内容 ({len(data_content)} 字节): {data_content.hex().upper()}')

if len(data_content) >= 30:
    pos = 0
    
    # 本地通信模式字
    mode_byte = data_content[pos]
    comm_way = (mode_byte >> 1) & 0x07
    ways = {1: "窄带电力线载波", 2: "宽带电力线载波", 3: "微功率无线", 4: "窄带+微功率无线", 5: "宽带+微功率无线"}
    print(f'\n  本地通信模式字: 0x{mode_byte:02X}')
    print(f'    通信方式: {ways.get(comm_way, f"未知({comm_way})")}')
    pos += 1
    
    # 最大支持的协议报文长度
    max_len = int.from_bytes(data_content[pos:pos+2], 'little')
    print(f'  最大支持的协议报文长度: {max_len} 字节')
    pos += 2
    
    # 文件传输支持的最大单包长度
    file_max_len = int.from_bytes(data_content[pos:pos+2], 'little')
    print(f'  文件传输支持的最大单包长度: {file_max_len} 字节')
    pos += 2
    
    # 升级操作等待时间
    wait_time = data_content[pos]
    print(f'  升级操作等待时间: {wait_time} 秒')
    pos += 1
    
    # 主节点地址
    master_addr = data_content[pos:pos+6]
    print(f'  主节点地址: {master_addr.hex().upper()}')
    pos += 6
    
    # 支持的最大从节点数量
    max_nodes = int.from_bytes(data_content[pos:pos+2], 'little')
    print(f'  支持的最大从节点数量: {max_nodes}')
    pos += 2
    
    # 当前从节点数量
    curr_nodes = int.from_bytes(data_content[pos:pos+2], 'little')
    print(f'  当前从节点数量: {curr_nodes}')
    pos += 2
    
    # 支持单次读写从节点信息的最大数量
    max_read_nodes = int.from_bytes(data_content[pos:pos+2], 'little')
    print(f'  支持单次读写从节点信息的最大数量: {max_read_nodes}')
    pos += 2
    
    # 通信模块接口协议发布日期
    date_bytes = data_content[pos:pos+3]
    year = date_bytes[0]
    month = date_bytes[1]
    day = date_bytes[2]
    print(f'  通信模块接口协议发布日期: 20{year:02d}-{month:02d}-{day:02d}')
    pos += 3
    
    # 厂商代码和版本信息 (9字节)
    vendor_info = data_content[pos:pos+9]
    print(f'  厂商代码和版本信息: {vendor_info.hex().upper()}')
    if len(vendor_info) >= 9:
        vendor_code = vendor_info[0:2].decode('ascii', errors='ignore')
        chip_code = vendor_info[2:4].decode('ascii', errors='ignore')
        ver_date = f'{vendor_info[4]:02d}{vendor_info[5]:02d}{vendor_info[6]:02d}'
        ver = f'{vendor_info[7]:02d}{vendor_info[8]:02d}'
        print(f'    厂商代码: {vendor_code}')
        print(f'    芯片代码: {chip_code}')
        print(f'    版本日期: {ver_date}')
        print(f'    版本: {ver}')
