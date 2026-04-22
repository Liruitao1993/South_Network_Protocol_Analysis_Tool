from binascii import hexlify
from ctypes import Structure, addressof, c_uint16, c_uint32, c_uint64, c_uint8, memmove
import time
# input_string= "683300000000006891A034103332334C34457B7F3545636C36514844563749355638457B7F3945636C3A3F4C3B3F333E3F36433F3574D58094A5535365536563656753646A6D66686D646875497738764977387749583378499453B6F57F778B666C6374607A838563656574606B66333333333333B73F39B85733333335B93F34BA3F34BB3F34BC3F34BD3F33C79F34B74636333333333333333333C897333333332288B85E323232327A16"
# string2 = "689D008300001000001BF020070011C21D140002C1FD07000000030301010100024C4A5A333930422D475052313033412D3034000001124B5302123039031E300524041601240C36000000050624100C0212147903160C0141A24D617920333020323032342030383A34373A3131421671804316010044160F10450694CC3F8A1303008A1303008A1303008A1303008A1303008A13030097140000CF16"
# string3 = "68250083000010000019F04007000AC201C10101000200030004000C00100012001600C016"

# input_bytes_string = bytes.fromhex(input_string.replace(" ", "").replace(",", ""))

def Sub_33(bytes_string):
    tempbytes = bytes(0)
    for byte1 in bytes_string:
        if byte1 >= 0x33:
            tempbytes +=  (byte1 - 0x33).to_bytes(1, "little")
        else:
            tempbytes  += (byte1+256-0x33).to_bytes(1, "little")
    return tempbytes


# C数据类型定义
u8 = c_uint8
u16 = c_uint16
u32 = c_uint32
u64 = c_uint64

U8 = c_uint8
U16 = c_uint16
U32 = c_uint32
U64 = c_uint64

# 条目头的定义
class EntryHeader(Structure):
    _pack_ = 1
    _fields_ = [
        ("Data_ID", u16, 6),
        ("Classified_ID", u16, 3),
        ("Coding", u16, 2),
        ("Data_Length", u16, 5),
        ]
# 确认帧条目头的定义
class SackEntryHeader(Structure):
    _pack_ = 1
    _fields_ = [
        ("Data_ID", u16, 6),
        ("Classified_ID", u16, 3),
        ("result", u16, 7),
        ]
    
coding = {1:"[ASCII]", 2:"[BIN  ]", 3:"[BCD  ]"}
"""
解析测试帧，输出各个条目的信息。
Args:
bytes_string_inpurt (bytes): 测试帧的字节数据。
chip_type (str): 芯片类型，可为 '3960A' 或 '3960B'。默认为 '3960A'。
Returns:
None

"""
def decode_testframe(bytes_string_inpurt, chip_type='3960A', log_callback=None):
    import logging
    
    # 如果没有提供回调函数，使用原来的列表方式（向后兼容）
    if log_callback is None:
        log_lines = []
        def local_log(level, message):
            log_lines.append(message)
        log_func = local_log
        use_callback = False
    else:
        log_func = log_callback
        use_callback = True
    
    start = 2
    jian33bytes = bytes_string_inpurt
    
    # 检查输入数据长度
    if len(jian33bytes) < 2:
        log_func(logging.ERROR, "错误: 输入数据长度不足，至少需要2字节")
        if not use_callback:
            return log_lines
        else:
            return
    
    log_func(logging.INFO, f"信息条目信息：{jian33bytes[0]}")
    log_func(logging.INFO, f"信息条目数：{jian33bytes[1]}")
    # print(jian33bytes.hex())
    # print(jian33bytes[1])
    for i in range(0, jian33bytes[1]):
        entryHeader = EntryHeader()
        #log_func(logging.INFO,"start=",start)
        memmove(addressof(entryHeader), jian33bytes[start:start+2], 2)
        # log_func(logging.INFO,"=========条目头信息=========")
        # log_func(logging.INFO,f"数据ID{entryHeader.Data_ID}")
        # log_func(logging.INFO,f"数据类型{entryHeader.Classified_ID}")
        # log_func(logging.INFO,f"数据编码{entryHeader.Coding}")
        # log_func(logging.INFO,f"条目长度{entryHeader.Data_Length}")
        match entryHeader.Classified_ID:    
            case 0:
                match entryHeader.Data_ID:
                    case 1:
                        if entryHeader.Coding == 1:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO, f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  外部厂商代码: {jian33bytes[start+2:end][::-1].decode('utf-8')}")
                    case 2:
                        if entryHeader.Coding == 1:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO, f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  外部芯片代码: {jian33bytes[start+2:end][::-1].decode('utf-8')}")
                    case 3:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO, f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  外部版本日期:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                        
                    case 4:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  外部版本号:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 5:
                        if entryHeader.Coding == 1:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  内部厂商代码: {jian33bytes[start+2:end][::-1].decode('utf-8')}")
                    case 6:
                        if entryHeader.Coding == 1:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  内部芯片代码: {jian33bytes[start+2:end][::-1].decode('utf-8')}")
                    case 7:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            data_content = jian33bytes[start+2:end]
                            if len(data_content) > 0:
                                data_value = data_content[0]
                            else:
                                data_value = 0
                            # 根据芯片类型解析
                            if chip_type == '3960A':
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  应用省份(3960A): {data_value}")
                            else:  # 3960B
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  应用省份(3960B): {data_value}")
                    case 8:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO,f"数据长度{entryHeader.Data_Length}")
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            # 根据芯片类型解析
                            if chip_type == '3960A':
                                data_content = jian33bytes[start+2:end]
                                if len(data_content) > 0:
                                    data_value = data_content[0]
                                else:
                                    data_value = 0
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  应用方案(3960A): {data_value}")
                            else:  # 3960B
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  应用方案(3960B):  ")
                    case 9:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            # 模块功能开关 - 8位二进制字段
                            data_content = jian33bytes[start+2:end]
                            if len(data_content) > 0:
                                switch_byte = data_content[0]
                            else:
                                switch_byte = 0
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  模块功能开关:0x{switch_byte:02X} (0b{switch_byte:08b})")
                            log_func(logging.INFO,f" "*78+f"B0-即装即采功能开关: {'打开' if (switch_byte & 0x01) else '关闭'}")
                            log_func(logging.INFO,f" "*78+f"B1-万年历启动开关: {'打开' if (switch_byte & 0x02) else '关闭'}")
                            log_func(logging.INFO,f" "*78+f"B2-低功耗使能开关: {'打开' if (switch_byte & 0x04) else '关闭'}")
                            log_func(logging.INFO,f" "*78+f"B3-白名单启动开关: {'打开' if (switch_byte & 0x08) else '关闭'}")
                            log_func(logging.INFO,f" "*78+f"B4~B7: 保留位 (0b{(switch_byte >> 4):04b})")
                    case 10:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            data_value = jian33bytes[start+2:end][0]
                            # 根据芯片类型解析
                            if chip_type == '3960A':
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  CLASS_ID=0 DATA_ID=10(3960A): {data_value}")
                            else:  # 3960B
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  CLASS_ID=0 DATA_ID=10(3960B): {data_value}")
                    case 11:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  模块类型: {jian33bytes[start+2:end][0]}")
                    case 12:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  模块生产时间: {hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 15:
                        if entryHeader.Coding == 2:  # 1:ASCII 2:BIN 3:BCD
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if chip_type == '3960A':
                                if entryHeader.Data_Length == 2:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  本地接口默认信息:波特率{int(jian33bytes[start+2:end][0])}校验位{int(jian33bytes[start+2:end][1])}")
                                else:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  本地接口默认信息:")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  本地接口默认信息:")
                    case 16:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  默认HPLC频段信息:{jian33bytes[start+2:end][0]}")
                    case 18:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  默认HRF信道信息信道index:{int(jian33bytes[start+2:end][0])}带宽option:{int(jian33bytes[start+2:end][1]&0x0f)}信道切换使能:{int(jian33bytes[start+2:end][1]&0x80>>7)}")
                    case 19:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  默认HRF参数信息发送功率:{int(jian33bytes[start+2:end][0])}调整因子:{int(jian33bytes[start+2:end][1])}")
                    case 20:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  以太网默认信息:")
                    case 21:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  以太网默认信息:")
                    case 22:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if chip_type == '3960A':
                                if entryHeader.Data_Length == 1:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  波特率协商使能:{jian33bytes[start+2:end][0]}")
                                else:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  波特率协商使能:")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  波特率协商使能:")
                    case 23:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if chip_type == '3960A':
                                if entryHeader.Data_Length == 1:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},   初始串口波特率:{jian33bytes[start+2:end][0]}")
                                else:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},   初始串口波特率:")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},   初始串口波特率:")
                    case 24:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if chip_type == '3960A':
                                if entryHeader.Data_Length == 1:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  波特率协商结果:{jian33bytes[start+2:end][0]}")
                                else:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  波特率协商结果:")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  波特率协商结果:")
                    case 25:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if chip_type == '3960A':
                                if entryHeader.Data_Length == 1:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  当前串口波特率:{jian33bytes[start+2:end][0]}")
                                else:
                                    log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  当前串口波特率:")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  当前串口波特率:")
                #log_func(logging.INFO,"end=",end)
                start += 2 + entryHeader.Data_Length
                        
            case 1:
                match entryHeader.Data_ID:
                    case 1:
                        if entryHeader.Coding == 1:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  编译时间:{jian33bytes[start+2:end].decode("utf-8")}")
                    case 2:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  程序总版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 3:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  总工程版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 4:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  boot程序版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 5:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  芯片程序版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 6:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  驱动层版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 7:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  载波接口层版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 8:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  无线PHY层版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 9:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  载波MAC层版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 10:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  无线MAC层版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 11:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  网络层版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 12:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  应用APS层版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 13:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  应用APP层版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 14:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  应用接口层版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 20:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  加密程序库版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 21:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  时钟管理库版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 22:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  虚拟扇区库版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 23:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  台区识别库版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 24:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  数据采集库版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    case 30:
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  深化应用库版本:{hexlify(jian33bytes[start+2:end][::-1]).decode('utf-8')}")
                    
                start += entryHeader.Data_Length + 2
            case 2:
                match entryHeader.Data_ID:
                    case 3:
                        if entryHeader.Coding == 1:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  硬件型号:{jian33bytes[start+2:end].decode("utf-8")}")
                    case 4:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            data_content = jian33bytes[start+2:end]
                            if len(data_content) > 0:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  芯片型号:{data_content[0]}")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  芯片型号:无数据")
                        
                    case 5:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  Flash型号及容量:{hexlify(jian33bytes[start+2:end]).decode('utf-8')}")
                    case 6:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if entryHeader.Data_Length == 1:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  电容容量:{jian33bytes[start+2:end][0]}")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  电容容量:")
                        
                    case 7:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if entryHeader.Data_Length == 1:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  过零电路类型:{jian33bytes[start+2:end][0]}")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  过零电路类型:")
                    case 8:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if entryHeader.Data_Length == 1:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  天线类型:{jian33bytes[start+2:end][0]}")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  天线类型:")
                    case 9:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if entryHeader.Data_Length == 1:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  载波功放型号:{jian33bytes[start+2:end][0]}")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  载波功放型号:")
                    case 10:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            if entryHeader.Data_Length == 1:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  特征电流拓朴类型:{jian33bytes[start+2:end][0]}")
                            else:
                                log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  特征电流拓朴类型:")
                    case 15:
                       
                        if entryHeader.Coding == 3:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            # 辅助函数：BCD时间转字符串
                            def bcd_time_to_str(bcd_bytes):
                                """将6字节BCD时间转为字符串格式 YY-MM-DD HH:MM:SS"""
                                if all(b == 0xFF for b in bcd_bytes):
                                    return "无效时间(全F)"
                                try:
                                    # BCD格式：年月日时分秒
                                    yy = f"{bcd_bytes[0]:02X}"
                                    mm = f"{bcd_bytes[1]:02X}"
                                    dd = f"{bcd_bytes[2]:02X}"
                                    hh = f"{bcd_bytes[3]:02X}"
                                    mi = f"{bcd_bytes[4]:02X}"
                                    ss = f"{bcd_bytes[5]:02X}"
                                    return f"20{yy}-{mm}-{dd} {hh}:{mi}:{ss}"
                                except:
                                    return "格式错误"
                            
                            data = jian33bytes[start+2:end]
                            
                            # B0: 时钟源
                            clock_source = data[0]
                            clock_source_map = {0: "未同步", 1: "设备时间", 2: "网络万年历"}
                            clock_source_str = clock_source_map.get(clock_source, f"未知({clock_source})")
                            
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  模块时钟信息")
                            log_func(logging.INFO,f" "*78+f"时钟源: {clock_source_str}")
                            log_func(logging.INFO,f" "*78+f"保留字节: 0x{data[1]:02X}")
                            
                            # B2-B7: 模块当前RTC时间
                            rtc_time = bcd_time_to_str(data[2:8])
                            log_func(logging.INFO,f" "*78+f"模块当前RTC时间: {rtc_time}")
                            
                            # B8-B13: 上次获取设备时间
                            last_device_time = bcd_time_to_str(data[8:14])
                            log_func(logging.INFO,f" "*78+f"上次获取设备时间: {last_device_time}")
                            
                            # B14-B19: 上次校时RTC时间
                            last_calibration_time = bcd_time_to_str(data[14:20])
                            log_func(logging.INFO,f" "*78+f"上次校时RTC时间: {last_calibration_time}")
                            
                            # B20-B25: 模拟设备运行时间
                            simulate_run_time = bcd_time_to_str(data[20:26])
                            log_func(logging.INFO,f" "*78+f"模拟设备运行时间: {simulate_run_time}")
                    case 20:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  过零检测信息:{hexlify(jian33bytes[start+2:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"{' '*78}过零标志：{jian33bytes[start+2:end][0]}")
                            log_func(logging.INFO,f"{' '*78}A相(下降沿)过零检测频率: {int.from_bytes(jian33bytes[start+2:end][1:3], byteorder='little', signed=False)*0.01}Hz")
                            log_func(logging.INFO,f"{' '*78}A相(下降沿)过零检测占空比: {int.from_bytes(jian33bytes[start+2:end][3:5], byteorder='little', signed=False)*0.1:0.2f}%")
                            log_func(logging.INFO,f"{' '*78}B相(下降沿)过零检测频率: {int.from_bytes(jian33bytes[start+2:end][5:7], byteorder='little', signed=False)*0.01}Hz")
                            log_func(logging.INFO,f"{' '*78}B相(下降沿)过零检测占空比: {int.from_bytes(jian33bytes[start+2:end][7:9], byteorder='little', signed=False)*0.1:0.2f}%")
                            log_func(logging.INFO,f"{' '*78}C相(下降沿)过零检测频率: {int.from_bytes(jian33bytes[start+2:end][9:11], byteorder='little', signed=False)*0.01}Hz")
                            log_func(logging.INFO,f"{' '*78}C相(下降沿)过零检测占空比: {int.from_bytes(jian33bytes[start+2:end][11:13], byteorder='little', signed=False)*0.1:0.2f}%")
                            log_func(logging.INFO,f"{' '*78}A相(上升沿)过零检测频率: {int.from_bytes(jian33bytes[start+2:end][13:15],byteorder='little', signed=False)*0.01}Hz")
                            log_func(logging.INFO,f"{' '*78}A相(上升沿)过零检测占空比: {int.from_bytes(jian33bytes[start+2:end][15:17], byteorder='little', signed=False)*0.1:0.2f}%")
                            log_func(logging.INFO,f"{' '*78}B相(上升沿)过零检测频率: {int.from_bytes(jian33bytes[start+2:end][17:19],byteorder='little', signed=False)*0.01}Hz")
                            log_func(logging.INFO,f"{' '*78}B相(上升沿)过零检测占空比: {int.from_bytes(jian33bytes[start+2:end][19:21], byteorder='little', signed=False)*0.1:0.2f}%")
                            log_func(logging.INFO,f"{' '*78}C相(上升沿)过零检测频率: {int.from_bytes(jian33bytes[start+2:end][21:23], byteorder='little', signed=False)*0.01}Hz")
                            log_func(logging.INFO,f"{' '*78}C相(上升沿)过零检测占空比: {int.from_bytes(jian33bytes[start+2:end][23:25], byteorder='little', signed=False)*0.1:0.2f}%")
                            
                    case 21:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  NTB采样信息:{hexlify(jian33bytes[start+2:end]).decode('utf-8')}")
                    case 23:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  无线接收信息:信号强度RSSI:{jian33bytes[start+2:end][0]}信噪比SNR:{jian33bytes[start+2:end][1]}")
                start += entryHeader.Data_Length + 2
                
            case 7:
                match entryHeader.Data_ID:
                    case 1:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  硬件信息组")
                            log_func(logging.INFO,str(" "*78+"芯片型号：",jian33bytes[start+2:end][0]))
                            log_func(logging.INFO,f" "*78+f"Flash型号及容量：{hexlify(jian33bytes[start+2:end][1:5])}")
                            log_func(logging.INFO,str(" "*78+"电容容量：",jian33bytes[start+2:end][5]))
                            log_func(logging.INFO,str(" "*78+"过零电路类型：",jian33bytes[start+2:end][6]))
                            log_func(logging.INFO,str(" "*78+"天线类型：",jian33bytes[start+2:end][7]))
                            log_func(logging.INFO,str(" "*78+"载波功放型号：",jian33bytes[start+2:end][8]))
                            log_func(logging.INFO,str(" "*78+"特征电流拓朴类型：",jian33bytes[start+2:end][9]))
                            log_func(logging.INFO,str(" "*78+"无线射频开关类型:",jian33bytes[start+2:end][10]))
                            log_func(logging.INFO,str(" "*78+"硬件编码:",jian33bytes[start+2:end].decode("utf-8")[11:31]))
                                
                    case 2:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  软件信息组")
                            log_func(logging.INFO,str(" "*78+"应用省份:",jian33bytes[start+2:end][0]))
                            log_func(logging.INFO,str(" "*78+"应用方案:",jian33bytes[start+2:end][1]))
                            log_func(logging.INFO,str(" "*78+"模块类型:",jian33bytes[start+2:end][2]))
                        
                    case 5:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  Flash型号及容量:{int(jian33bytes[start+2:end])}")
                    case 6:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  电容容量:{int(jian33bytes[start+2:end])}")
                        
                    case 7:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            data_content = jian33bytes[start+2:end]
                            if len(data_content) > 0:
                                circuit_type = int(data_content)
                            else:
                                circuit_type = 0
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  过零电路类型:{circuit_type}")
                    case 8:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            data_content = jian33bytes[start+2:end]
                            if len(data_content) > 0:
                                antenna_type = int(data_content)
                            else:
                                antenna_type = 0
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  天线类型:{antenna_type}")
                    case 9:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  载波功放型号:{int(jian33bytes[start+2:end])}")
                    case 10:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  特征电流拓朴类型:{int(jian33bytes[start+2:end])}")
                    case 20:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  过零检测信息:{int(jian33bytes[start+2:end])}")
                    case 21:
                        if entryHeader.Coding == 2:
                            end = start + 2 + entryHeader.Data_Length
                            log_func(logging.INFO, f"RawFrame-->{hexlify(jian33bytes[start:end]).decode('utf-8')}")
                            log_func(logging.INFO,f"类ID:{entryHeader.Classified_ID:02X},  数据ID:{entryHeader.Data_ID:02x},  数据类型:{entryHeader.Coding:02x}{coding[entryHeader.Coding]},  数据长度:{entryHeader.Data_Length:02x},  NTB采样信息:{jian33bytes[start+2:end]}")
                        
                start += entryHeader.Data_Length + 2
                
                
    # 返回日志行列表（仅在不使用回调时）
    if not use_callback:
        return log_lines
    
if __name__ == '__main__':
    while True:
        input_string = input("请输入十六进制字符串：")
        protocol = input("请输入协议类型：")
        input_bytes_string = bytes.fromhex(input_string.replace(" ", "").replace(",", ""))
        match protocol:
            case "0":   #13762
                ID_index = hexlify(input_bytes_string).find(b"f02007")
                log_func(logging.INFO,ID_index)
                index = int(ID_index/2)+3
                log_func(logging.INFO,hexlify(input_bytes_string[index:]))
                decode_testframe(input_bytes_string[index:])
            case "1":   # ACK 13762
                start = 0 
                log_func(logging.INFO,str("信息条目数M:",input_bytes_string[14]))
                for i in range(0, input_bytes_string[14]):    
                    sackentryheader = SackEntryHeader()
                    # log_func(logging.INFO,f"start={start}")
                    memmove(addressof(sackentryheader), input_bytes_string[start:start+2], 2)
                    log_func(logging.INFO,f"数据ID：{sackentryheader.Data_ID}数据类型：{sackentryheader.Classified_ID}信息条目设置结果:{sackentryheader.result}")
                    start += 2
                
            case "2":   # 645
                ID_index = hexlify(Sub_33(input_bytes_string[9:])).find(b"01dd00ff")
                index = int(ID_index/2)+4
                log_func(logging.INFO,hexlify(Sub_33(input_bytes_string[9:])[index:]))
                decode_testframe(Sub_33(input_bytes_string[9:])[index:])
        time.sleep(1)
            
