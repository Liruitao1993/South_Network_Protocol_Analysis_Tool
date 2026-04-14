"""
DLMS/COSEM 深度解析器
参考 dlmslib 和 IEC 62056 标准实现
支持 Action-Request/Response, Get-Request/Response, Set-Request/Response 等
"""
import struct
from typing import Dict, Any, List, Optional, Tuple


class DLMSDeepParser:
    """DLMS/COSEM 深度解析器"""

    # DLMS 数据类型映射
    DLMS_DATA_TYPES = {
        0x00: ("Null", 0, None),
        0x01: ("Data (Array/Structure)", 0, None),  # 长度在后续字节
        0x02: ("Boolean", 1, "bool"),
        0x03: ("Bit-String", 0, None),  # 长度+数据
        0x04: ("Double-Long-Unsigned", 4, "uint32"),
        0x05: ("Double-Long", 4, "int32"),
        0x06: ("Octet-String", 0, None),  # 长度+数据
        0x09: ("Visible-String", 0, None),  # 长度+ASCII
        0x0A: ("UTF8-String", 0, None),  # 长度+UTF8
        0x0B: ("BCD", 0, None),  # 长度+数据
        0x0C: ("Integer", 2, "int16"),
        0x0D: ("Long", 4, "int32"),
        0x0F: ("Long-Unsigned", 2, "uint16"),
        0x10: ("Compact-Array", 0, None),
        0x11: ("Long64-Unsigned", 8, "uint64"),
        0x12: ("Long64", 8, "int64"),
        0x13: ("Enum", 1, "uint8"),
        0x16: ("Float32", 4, "float"),
        0x17: ("Float64", 8, "double"),
        0x18: ("DateTime", 12, "datetime"),
        0x19: ("Date", 5, "date"),
        0x1A: ("Time", 4, "time"),
        0x1B: ("Dont-Care", 0, None),
    }

    # OBIS 码描述（常见对象）
    OBIS_DESCRIPTIONS = {
        (0, 0, 96, 1, 0, 255): "逻辑设备名称",
        (0, 0, 96, 1, 1, 255): "设备标识",
        (0, 0, 96, 1, 2, 255): "固件版本",
        (1, 0, 1, 8, 0, 255): "有功电能正向累计值（总）",
        (1, 0, 1, 8, 1, 255): "有功电能正向费率1",
        (1, 0, 1, 8, 2, 255): "有功电能正向费率2",
        (1, 0, 2, 8, 0, 255): "有功电能反向累计值（总）",
        (1, 0, 3, 8, 0, 255): "无功电能正向累计值（总）",
        (1, 0, 4, 8, 0, 255): "无功电能反向累计值（总）",
        (1, 0, 21, 7, 0, 255): "瞬时电压 L1",
        (1, 0, 22, 7, 0, 255): "瞬时电压 L2",
        (1, 0, 23, 7, 0, 255): "瞬时电压 L3",
        (1, 0, 31, 7, 0, 255): "瞬时电流 L1",
        (1, 0, 32, 7, 0, 255): "瞬时电流 L2",
        (1, 0, 33, 7, 0, 255): "瞬时电流 L3",
        (1, 0, 51, 7, 0, 255): "瞬时功率 L1",
        (1, 0, 52, 7, 0, 255): "瞬时功率 L2",
        (1, 0, 53, 7, 0, 255): "瞬时功率 L3",
        (1, 0, 96, 1, 0, 255): "电表时间",
        (1, 0, 96, 1, 1, 255): "电表日期",
    }

    # COSEM 类 ID
    COSEM_CLASS_IDS = {
        1: "数据 (Data)",
        3: "寄存器 (Register)",
        4: "扩展寄存器 (Extended-Register)",
        5: "需求寄存器 (Demand-Register)",
        6: "活动日历 (Activity-Calendar)",
        7: "配置文件 (Profile-Generic)",
        8: "时钟 (Clock)",
        9: "脚本表 (Script-Table)",
        10: "调度器 (Schedule)",
        15: "特殊天数表 (Special-Days-Table)",
        17: "关联逻辑设备 (Association-Logical-Device)",
        20: "关联快照 (Association-Snapshot)",
        42: "MBus 客户端端口 (M-Bus-Client-Port)",
        43: "MBus 主端口 (M-Bus-Master-Port)",
        44: "MBus 诊断 (M-Bus-Diagnostic)",
        70: "脉冲计数器 (Pulse-Counter)",
        71: "水计量 (Water-Meter)",
        72: "气体计量 (Gas-Meter)",
        73: "热计量 (Heat-Meter)",
        74: "热成本分配器 (Heat-Cost-Allocator)",
        81: "通信口 HDLC (Comms-Port-HDLC)",
        82: "通信口 调制解调器 (Comms-Port-Modem)",
        88: "自动应答 (Auto-Ans-wer)",
        89: "自动连接 (Auto-Connect)",
        90: "GPRS 调制解调器配置 (GPRS-Modem-Configuration)",
        91: "LTE 调制解调器配置 (LTE-Modem-Configuration)",
        100: "应用关联 (Application-Association)",
        101: "安全设置 (Security-Setup)",
        111: "断开控制 (Disconnect-Control)",
        113: "极限值 (Limit-Value)",
        114: "参数监控 (Parameter-Monitor)",
        115: "参数控制 (Parameter-Control)",
        118: "MBus 端口配置 (M-Bus-Port-Configuration)",
        129: "报警对象 (Alarm-Object)",
        200: "动作计划 (Action-Schedule)",
    }

    def parse_action_request(self, data: bytes, base_offset: int) -> List[Tuple]:
        """
        解析 Action-Request (0xC2)
        参考 dlmslib 的解析逻辑
        """
        table_data = []
        offset = 0
        local_base = base_offset

        # Action-Request 结构:
        # - Invoke-Id-And-Priority (1 byte): 高4位=Invoke-ID, 低2位=Priority
        if len(data) > offset:
            invoke_byte = data[offset]
            invoke_id = (invoke_byte >> 4) & 0x0F
            priority = invoke_byte & 0x03
            
            table_data.append((
                "    调用ID (Invoke-ID)",
                f"0x{invoke_byte:02X}",
                f"Invoke-ID={invoke_id}, Priority={priority}",
                "请求标识符和优先级",
                local_base + offset,
                local_base + offset
            ))
            offset += 1

        # 检查是否有 SEQUENCE 标签 (0x30 或 0xA0 等)
        # 但在某些编码中，SEQUENCE 可能是隐式的
        if len(data) > offset:
            # 尝试解析 Cosem-Attribute-Descriptor
            # 这通常是: OBIS(6 bytes) + Class-ID(2 bytes) + Attribute-ID(2 bytes)
            
            # 检查是否是 OCTET STRING 标签 (0x09) 后跟 OBIS
            if data[offset] == 0x09 and len(data) >= offset + 8:
                # OCTET STRING (OBIS)
                obis_len = data[offset + 1]
                if obis_len == 6:
                    obis_bytes = data[offset + 2:offset + 8]
                    obis_str = ".".join(str(b) for b in obis_bytes)
                    obis_tuple = tuple(obis_bytes)
                    obis_desc = self.OBIS_DESCRIPTIONS.get(obis_tuple, "未知对象")
                    
                    table_data.append((
                        "    OBIS码",
                        self._bytes_to_hex(obis_bytes),
                        obis_str,
                        f"对象标识: {obis_desc}",
                        local_base + offset,
                        local_base + offset + 7
                    ))
                    offset += 8  # tag(1) + len(1) + data(6)
                    
                    # Class-ID (2 bytes)
                    if len(data) >= offset + 2:
                        class_id = struct.unpack('>H', data[offset:offset + 2])[0]
                        class_name = self.COSEM_CLASS_IDS.get(class_id, f"未知类({class_id})")
                        
                        table_data.append((
                            "    类ID (Class-ID)",
                            f"0x{class_id:04X}",
                            class_name,
                            "COSEM对象类",
                            local_base + offset,
                            local_base + offset + 1
                        ))
                        offset += 2
                        
                        # Attribute-ID (2 bytes)
                        if len(data) >= offset + 2:
                            attr_id = struct.unpack('>H', data[offset:offset + 2])[0]
                            
                            table_data.append((
                                "    属性ID (Attribute-ID)",
                                f"0x{attr_id:04X}",
                                str(attr_id),
                                "对象属性索引",
                                local_base + offset,
                                local_base + offset + 1
                            ))
                            offset += 2
                            
                            # Method-ID (1 byte)
                            if len(data) > offset:
                                method_id = data[offset]
                                
                                table_data.append((
                                    "    方法ID (Method-ID)",
                                    f"0x{method_id:02X}",
                                    str(method_id),
                                    "操作方法",
                                    local_base + offset,
                                    local_base + offset
                                ))
                                offset += 1
                                
                                # 可选参数 (Parameter)
                                if len(data) > offset:
                                    # 参数可能有上下文标签 [0] (0xA0 或 0xC0)
                                    if data[offset] in [0xA0, 0xC0]:
                                        # 有上下文标签
                                        param_tag = data[offset]
                                        table_data.append((
                                            "    参数标签",
                                            f"0x{param_tag:02X}",
                                            "[0] Parameter",
                                            "参数上下文标签",
                                            local_base + offset,
                                            local_base + offset
                                        ))
                                        offset += 1
                                        
                                        # 解析参数数据
                                        remaining = data[offset:]
                                        self._parse_dlms_data_value(
                                            remaining, table_data, local_base + offset, "    参数值"
                                        )
                                    else:
                                        # 直接是参数数据
                                        remaining = data[offset:]
                                        self._parse_dlms_data_value(
                                            remaining, table_data, local_base + offset, "    参数值"
                                        )
            else:
                # 如果不是标准格式，尝试直接解析
                # 可能是: Invoke-ID + 其他结构
                remaining = data[offset:]
                table_data.append((
                    "    Action-Request数据",
                    self._bytes_to_hex(remaining[:15]) + ("..." if len(remaining) > 15 else ""),
                    f"{len(remaining)}字节",
                    "非标准编码的Action-Request数据",
                    local_base + offset,
                    local_base + min(offset + 14, base_offset + len(data) - 1)
                ))

        return table_data

    def _parse_dlms_data_value(self, data: bytes, table_data: List, base_offset: int, label: str) -> int:
        """
        解析 DLMS 数据值（BER 编码）
        返回解析的字节数
        """
        if len(data) == 0:
            return 0

        offset = 0
        local_base = base_offset

        # 数据类型标签
        type_tag = data[0]
        offset += 1

        if type_tag not in self.DLMS_DATA_TYPES:
            # 未知类型
            table_data.append((
                label,
                self._bytes_to_hex(data[:10]) + ("..." if len(data) > 10 else ""),
                f"未知类型(0x{type_tag:02X})",
                "无法识别的DLMS数据类型",
                local_base,
                local_base + min(len(data) - 1, 9)
            ))
            return len(data)

        type_name, fixed_len, type_format = self.DLMS_DATA_TYPES[type_tag]

        # 处理变长类型（需要读取长度字段）
        if fixed_len == 0:
            if type_tag == 0x00:  # Null
                table_data.append((label, "-", "Null", "空值", local_base - 1, local_base - 1))
                return 1
            elif type_tag == 0x01:  # Array/Structure
                # 数组/结构：标签 + 元素数量 + 元素数据
                if len(data) > offset:
                    elem_count = data[offset]
                    offset += 1
                    
                    table_data.append((
                        label,
                        f"0x{type_tag:02X} {elem_count}",
                        f"{type_name}, 元素数={elem_count}",
                        "复合数据类型",
                        local_base - 1,
                        local_base
                    ))
                    
                    # 解析元素
                    if elem_count > 0 and len(data) > offset:
                        # 简化处理：显示原始数据
                        remaining = data[offset:]
                        table_data.append((
                            f"{label} (元素数据)",
                            self._bytes_to_hex(remaining[:10]) + ("..." if len(remaining) > 10 else ""),
                            f"{len(remaining)}字节",
                            f"包含{elem_count}个元素",
                            local_base + offset - 1,
                            local_base + min(offset + 8, len(data) - 1)
                        ))
                        return len(data)
                    return offset
            elif type_tag in [0x03, 0x06, 0x09, 0x0A, 0x0B]:  # 字符串/字节串类型
                if len(data) > offset:
                    str_len = data[offset]
                    offset += 1
                    
                    if len(data) >= offset + str_len:
                        str_data = data[offset:offset + str_len]
                        
                        if type_tag == 0x09:  # Visible-String (ASCII)
                            try:
                                str_value = str_data.decode('ascii', errors='replace')
                                table_data.append((
                                    label,
                                    self._bytes_to_hex(str_data),
                                    f'"{str_value}"',
                                    f"ASCII字符串({str_len}字节)",
                                    local_base - 1,
                                    local_base + str_len
                                ))
                            except:
                                table_data.append((
                                    label,
                                    self._bytes_to_hex(str_data),
                                    f"{str_len}字节",
                                    "字节串数据",
                                    local_base - 1,
                                    local_base + str_len
                                ))
                        elif type_tag == 0x06:  # Octet-String
                            # 检查是否是 DateTime (12字节)
                            if str_len == 12:
                                try:
                                    year = struct.unpack('>H', str_data[0:2])[0]
                                    month = str_data[2]
                                    day = str_data[3]
                                    hour = str_data[4]
                                    minute = str_data[5]
                                    second = str_data[6]
                                    dt_str = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
                                    table_data.append((
                                        label + " (DateTime)",
                                        self._bytes_to_hex(str_data),
                                        dt_str,
                                        "日期时间",
                                        local_base - 1,
                                        local_base + str_len
                                    ))
                                except:
                                    table_data.append((
                                        label,
                                        self._bytes_to_hex(str_data),
                                        f"{str_len}字节",
                                        "二进制数据",
                                        local_base - 1,
                                        local_base + str_len
                                    ))
                            else:
                                table_data.append((
                                    label,
                                    self._bytes_to_hex(str_data[:10]) + ("..." if str_len > 10 else ""),
                                    f"{str_len}字节",
                                    "字节串数据",
                                    local_base - 1,
                                    local_base + min(str_len, 9)
                                ))
                        else:
                            table_data.append((
                                label,
                                self._bytes_to_hex(str_data[:10]) + ("..." if str_len > 10 else ""),
                                f"{str_len}字节",
                                type_name,
                                local_base - 1,
                                local_base + min(str_len, 9)
                            ))
                        return offset + str_len
                    else:
                        # 长度不足
                        available = len(data) - offset
                        table_data.append((
                            label,
                            self._bytes_to_hex(data[offset:]),
                            f"{available}字节 (预期{str_len}字节)",
                            "数据不完整",
                            local_base - 1,
                            local_base + available - 1
                        ))
                        return len(data)
        else:
            # 定长类型
            if len(data) >= offset + fixed_len:
                value_data = data[offset:offset + fixed_len]
                
                if type_format == "uint16":
                    value = struct.unpack('>H', value_data)[0]
                    table_data.append((label, self._bytes_to_hex(value_data), str(value), type_name,
                                      local_base - 1, local_base + fixed_len - 1))
                elif type_format == "int16":
                    value = struct.unpack('>h', value_data)[0]
                    table_data.append((label, self._bytes_to_hex(value_data), str(value), type_name,
                                      local_base - 1, local_base + fixed_len - 1))
                elif type_format == "uint32":
                    value = struct.unpack('>I', value_data)[0]
                    table_data.append((label, self._bytes_to_hex(value_data), str(value), type_name,
                                      local_base - 1, local_base + fixed_len - 1))
                elif type_format == "int32":
                    value = struct.unpack('>i', value_data)[0]
                    table_data.append((label, self._bytes_to_hex(value_data), str(value), type_name,
                                      local_base - 1, local_base + fixed_len - 1))
                elif type_format == "bool":
                    value = "True" if value_data[0] != 0 else "False"
                    table_data.append((label, f"0x{value_data[0]:02X}", value, type_name,
                                      local_base - 1, local_base))
                elif type_format == "datetime":
                    try:
                        year = struct.unpack('>H', value_data[0:2])[0]
                        month = value_data[2]
                        day = value_data[3]
                        hour = value_data[4]
                        minute = value_data[5]
                        second = value_data[6]
                        dt_str = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
                        table_data.append((label, self._bytes_to_hex(value_data), dt_str, "日期时间",
                                          local_base - 1, local_base + fixed_len - 1))
                    except:
                        table_data.append((label, self._bytes_to_hex(value_data), f"{fixed_len}字节", type_name,
                                          local_base - 1, local_base + fixed_len - 1))
                else:
                    table_data.append((label, self._bytes_to_hex(value_data), f"{fixed_len}字节", type_name,
                                      local_base - 1, local_base + fixed_len - 1))
                return offset + fixed_len
            else:
                # 数据不足
                available = len(data) - offset
                table_data.append((label, self._bytes_to_hex(data[offset:]),
                                  f"{available}字节 (预期{fixed_len}字节)",
                                  "数据不完整",
                                  local_base - 1, local_base + available - 1))
                return len(data)

        return offset

    @staticmethod
    def _bytes_to_hex(data: bytes) -> str:
        """将字节转换为十六进制字符串"""
        return ' '.join(f'{b:02X}' for b in data)


def parse_dlms_deep(apdu_data: bytes, base_offset: int) -> List[Tuple]:
    """
    深度解析 DLMS APDU
    apdu_data: APDU 数据（不包含 LLC 头）
    base_offset: APDU 在原始帧中的起始位置
    """
    parser = DLMSDeepParser()
    table_data = []
    
    if len(apdu_data) == 0:
        return table_data
    
    apdu_type = apdu_data[0]
    
    if apdu_type == 0xC3:  # Action-Request
        return parser.parse_action_request(apdu_data[1:], base_offset + 1)
    elif apdu_type == 0xC7:  # Action-Response
        # 类似解析
        table_data.append(("    Action-Response", f"0x{apdu_type:02X}", "操作响应", "", base_offset, base_offset))
        return table_data
    elif apdu_type == 0xC0:  # Get-Request
        table_data.append(("    Get-Request", f"0x{apdu_type:02X}", "读请求", "", base_offset, base_offset))
        return table_data
    elif apdu_type == 0xC4:  # Get-Response
        table_data.append(("    Get-Response", f"0x{apdu_type:02X}", "读响应", "", base_offset, base_offset))
        return table_data
    else:
        table_data.append(("    未知APDU", f"0x{apdu_type:02X}", f"类型0x{apdu_type:02X}", "", base_offset, base_offset))
        return table_data
