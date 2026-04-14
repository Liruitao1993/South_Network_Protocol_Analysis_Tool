"""
DLMS/COSEM协议解析器
简化版，支持基本APDU解析
"""
import struct
from typing import Dict, Any


class DLMSParser:
    """DLMS协议解析器"""

    # APDU类型映射（按IEC 62056标准/Green Book定义）
    APDU_TYPES = {
        0x01: "AARQ (关联请求)",
        0x02: "AARE (关联响应)",
        0x03: "RLRQ (释放请求)",
        0x04: "RLRE (释放响应)",
        0x0C: "Confirmed-Service-Error",
        0x0E: "General-Block-Transfer",
        0x60: "AARQ (关联请求-BER)",
        0x61: "AARE (关联响应-BER)",
        0xC0: "Get-Request",
        0xC1: "Set-Request",
        0xC3: "Action-Request",
        0xC4: "Get-Response",
        0xC5: "Set-Response",
        0xC7: "Action-Response",
        0xC8: "Glo-Get-Request",
        0xC9: "Glo-Set-Request",
        0xCB: "Glo-Action-Request",
        0xCC: "Glo-Get-Response",
        0xCD: "Glo-Set-Response",
        0xCF: "Glo-Action-Response",
        0xD0: "Ded-Get-Request",
        0xD1: "Ded-Set-Request",
        0xD3: "Ded-Action-Request",
        0xD4: "Ded-Get-Response",
        0xD5: "Ded-Set-Response",
        0xD7: "Ded-Action-Response",
        0xE6: "Event-Notification",
        0xE7: "Data-Notification",
    }

    # 数据类型映射
    DATA_TYPES = {
        0x00: "Null",
        0x01: "Data (Array/Structure)",
        0x02: "Boolean",
        0x03: "Bit-String",
        0x04: "Double-Long-Unsigned",
        0x05: "Double-Long",
        0x06: "Octet-String",
        0x09: "Visible-String",
        0x0A: "UTF8-String",
        0x0B: "BCD",
        0x0C: "Integer",
        0x0D: "Long",
        0x0F: "Long-Unsigned",
        0x10: "Compact-Array",
        0x11: "Long64-Unsigned",
        0x12: "Long64",
        0x13: "Enum",
        0x16: "Float32",
        0x17: "Float64",
        0x18: "DateTime",
        0x19: "Date",
        0x1A: "Time",
        0x1B: "Dont-Care",
    }

    def parse_to_table(self, dlms_data: bytes) -> list:
        """解析DLMS数据到表格格式"""
        table_data = []
        
        if len(dlms_data) < 2:
            table_data.append(("错误", "-", "-", "数据过短", None, None))
            return table_data

        offset = 0

        # 尝试解析HDLC帧（如果以0x7E开头）
        if dlms_data[0] == 0x7E:
            self._parse_hdlc_frame(dlms_data, table_data, offset)
            return table_data

        # 直接解析APDU
        self._parse_apdu(dlms_data, table_data, offset)
        return table_data

    def _parse_hdlc_frame(self, data: bytes, table_data: list, offset: int):
        """解析HDLC封装的DLMS帧"""
        table_data.append(("HDLC起始符", f"0x{data[offset]:02X}", "0x7E", "HDLC帧起始标志", offset, offset))
        offset += 1

        # HDLC地址字段（简化）
        if len(data) > offset:
            addr_field = data[offset]
            table_data.append(("HDLC地址域", f"0x{addr_field:02X}", "", "", offset, offset))
            offset += 1

        # HDLC控制字段
        if len(data) > offset:
            ctrl_field = data[offset]
            table_data.append(("HDLC控制域", f"0x{ctrl_field:02X}", "", "", offset, offset))
            offset += 1

        # HCS（HDLC校验和）
        if len(data) > offset + 1:
            hcs = struct.unpack('<H', data[offset:offset+2])[0]
            table_data.append(("HCS校验", f"0x{hcs:04X}", "", "", offset, offset+1))
            offset += 2

        # 解析内部APDU
        self._parse_apdu(data[offset:], table_data, offset)

    def _parse_apdu(self, data: bytes, table_data: list, offset: int):
        """解析DLMS APDU"""
        start_offset = offset

        if len(data) < 2:
            return

        # 控制字段
        ctrl_field = data[0]
        ctrl_desc = ""
        
        # 分析控制字段
        if ctrl_field == 0x00:
            ctrl_desc = "长格式"
        elif ctrl_field == 0x01:
            ctrl_desc = "短格式"
        
        table_data.append(("DLMS控制字段", f"0x{ctrl_field:02X}", ctrl_desc, "", offset, offset))
        offset += 1

        # 根据控制字段判断格式
        if ctrl_field == 0x00:
            # 长格式：目标地址(4字节) + 源地址(1字节) + APDU
            if len(data) > offset + 4:
                dst_addr = data[offset:offset + 4]
                table_data.append(("  目标地址", dst_addr.hex(' ').upper(), f"4字节", "长格式目标地址", offset, offset + 3))
                offset += 4
            
            if len(data) > offset:
                src_addr = data[offset]
                table_data.append(("  源地址", f"0x{src_addr:02X}", f"1字节", "", offset, offset))
                offset += 1
        
        # APDU类型（可能是下一个字节）
        if len(data) > offset:
            apdu_byte = data[offset]
            
            # 检查是否是已知的APDU类型
            if apdu_byte in self.APDU_TYPES:
                apdu_name = self.APDU_TYPES[apdu_byte]
                table_data.append(("APDU类型", f"0x{apdu_byte:02X}", apdu_name, "", offset, offset))
                offset += 1
                
                # 继续解析具体APDU内容
                self._parse_apdu_content(data[offset:], table_data, offset, apdu_byte)
            else:
                # 可能APDU类型在更后面的位置
                # 尝试寻找常见的APDU类型
                for i in range(min(10, len(data) - offset)):
                    if data[offset + i] in self.APDU_TYPES:
                        apdu_name = self.APDU_TYPES[data[offset + i]]
                        table_data.append(("  APDU类型(偏移{}字节)".format(i), f"0x{data[offset + i]:02X}", apdu_name, "", offset + i, offset + i))
                        offset = offset + i + 1
                        self._parse_apdu_content(data[offset:], table_data, offset, data[offset - 1])
                        break
                else:
                    # 未识别，显示原始数据
                    table_data.append(("  APDU数据", data[offset:offset+20].hex(' ').upper() + ("..." if len(data) > offset + 20 else ""), f"{len(data) - offset}字节", "未识别的APDU格式", offset, len(data) - 1))

    def _parse_apdu_content(self, data: bytes, table_data: list, offset: int, apdu_type: int):
        """解析APDU具体内容"""
        if apdu_type == 0xC0:  # Get-Request
            if len(data) >= 1:
                invoke_id = data[0]
                table_data.append(("  调用ID", f"0x{invoke_id:02X}", str(invoke_id), "", offset, offset))
                offset += 1
                
                if len(data) >= offset + 1:
                    selector = data[offset]
                    selector_map = {0x01: "变量", 0x02: "变量组", 0x03: "属性"}
                    selector_name = selector_map.get(selector, f"未知(0x{selector:02X})")
                    table_data.append(("  选择符", f"0x{selector:02X}", selector_name, "", offset, offset))
                    offset += 1
                    
                    # OBIS码（6字节）
                    if len(data) >= offset + 6:
                        obis = data[offset:offset + 6]
                        obis_str = ".".join(str(b) for b in obis)
                        table_data.append(("  OBIS码", obis.hex(' ').upper(), obis_str, "对象标识", offset, offset + 5))
                        offset += 6
                        
                        # 属性索引
                        if len(data) >= offset + 1:
                            attr_idx = data[offset]
                            table_data.append(("  属性索引", f"0x{attr_idx:02X}", str(attr_idx), "", offset, offset))
                            offset += 1
                            
                            # 数据值
                            if len(data) >= offset + 1:
                                value_data = data[offset:]
                                self._parse_dlms_data(value_data, table_data, offset, "  数据值")
        
        elif apdu_type == 0xC4:  # Get-Response
            if len(data) >= 1:
                invoke_id = data[0]
                table_data.append(("  调用ID", f"0x{invoke_id:02X}", str(invoke_id), "", offset, offset))
                offset += 1
                
                if len(data) >= offset + 1:
                    result = data[offset]
                    result_map = {0x00: "成功", 0x01: "硬件故障", 0x02: "临时失败"}
                    result_name = result_map.get(result, f"未知(0x{result:02X})")
                    table_data.append(("  结果", f"0x{result:02X}", result_name, "", offset, offset))
                    offset += 1
                    
                    if result == 0x00 and len(data) >= offset + 1:
                        value_data = data[offset:]
                        self._parse_dlms_data(value_data, table_data, offset, "  返回数据")
        
        elif apdu_type in [0xC1, 0xC5]:  # Set-Request/Response
            if len(data) >= 1:
                invoke_id = data[0]
                table_data.append(("  调用ID", f"0x{invoke_id:02X}", str(invoke_id), "", offset, offset))
                offset += 1
        
        elif apdu_type in [0xC3, 0xC7]:  # Action-Request/Response
            if len(data) >= 1:
                invoke_id = data[0]
                table_data.append(("  调用ID", f"0x{invoke_id:02X}", str(invoke_id), "", offset, offset))
                offset += 1
        
        elif apdu_type == 0x01:  # AARQ
            if len(data) >= 1:
                table_data.append(("  协议版本", f"0x{data[0]:02X}", str(data[0]), "", offset, offset))
        
        elif apdu_type == 0x02:  # AARE
            if len(data) >= 1:
                result_map = {0x00: "接受", 0x01: "拒绝-永久", 0x02: "拒绝-临时"}
                result_name = result_map.get(data[0], f"未知(0x{data[0]:02X})")
                table_data.append(("  结果", f"0x{data[0]:02X}", result_name, "", offset, offset))

    def _parse_get_apdu(self, data: bytes, table_data: list, offset: int, is_request: bool):
        """解析Get请求/响应"""
        if len(data) < 1:
            return

        # 调用ID
        if len(data) >= 2:
            invoke_id = data[0]
            table_data.append(("  调用ID", f"0x{invoke_id:02X}", str(invoke_id), "", offset, offset))
            offset += 1

        if is_request:
            # Get-Request
            if len(data) > offset:
                selector = data[offset]
                selector_map = {0x01: "变量", 0x02: "变量组", 0x03: "属性"}
                selector_name = selector_map.get(selector, f"未知(0x{selector:02X})")
                table_data.append(("  选择符", f"0x{selector:02X}", selector_name, "", offset, offset))
                offset += 1

                # OBIS码（6字节）
                if len(data) >= offset + 6:
                    obis = data[offset:offset + 6]
                    obis_str = ".".join(str(b) for b in obis)
                    table_data.append(("  OBIS码", obis.hex(' ').upper(), obis_str, "对象标识", offset, offset + 5))
                    offset += 6

                # 属性索引
                if len(data) > offset:
                    attr_idx = data[offset]
                    table_data.append(("  属性索引", f"0x{attr_idx:02X}", str(attr_idx), "", offset, offset))
                    offset += 1

                # 值（可选）
                if len(data) > offset:
                    value_data = data[offset:]
                    value_type = value_data[0]
                    type_name = self.DATA_TYPES.get(value_type, f"未知(0x{value_type:02X})")
                    table_data.append(("  请求值", value_data.hex(' ').upper()[:30] + ("..." if len(value_data) > 15 else ""), type_name, "", offset, offset + len(value_data) - 1))
        else:
            # Get-Response
            if len(data) > offset:
                result = data[offset]
                result_map = {0x00: "成功", 0x01: "硬件故障", 0x02: "临时失败", 0x03: "读写对象未定义",
                             0x09: "对象未定义", 0x0B: "对象访问被拒绝", 0x0D: "对象未激活"}
                result_name = result_map.get(result, f"未知(0x{result:02X})")
                table_data.append(("  结果", f"0x{result:02X}", result_name, "", offset, offset))
                offset += 1

                # 数据（如果成功）
                if result == 0x00 and len(data) > offset:
                    value_data = data[offset:]
                    value_type = value_data[0]
                    type_name = self.DATA_TYPES.get(value_type, f"未知(0x{value_type:02X})")
                    self._parse_dlms_data(value_data, table_data, offset, "  返回数据")

    def _parse_set_apdu(self, data: bytes, table_data: list, offset: int):
        """解析Set请求/响应"""
        if len(data) < 1:
            return

        # 调用ID
        if len(data) >= 1:
            invoke_id = data[0]
            table_data.append(("  调用ID", f"0x{invoke_id:02X}", str(invoke_id), "", offset, offset))
            offset += 1

    def _parse_action_apdu(self, data: bytes, table_data: list, offset: int):
        """解析Action请求/响应"""
        if len(data) < 1:
            return

        # 调用ID
        if len(data) >= 1:
            invoke_id = data[0]
            table_data.append(("  调用ID", f"0x{invoke_id:02X}", str(invoke_id), "", offset, offset))
            offset += 1

    def _parse_aarq(self, data: bytes, table_data: list, offset: int):
        """解析AARQ（关联请求）"""
        if len(data) < 1:
            return

        # 协议版本
        if len(data) >= 1:
            table_data.append(("  协议版本", f"0x{data[0]:02X}", str(data[0]), "", offset, offset))
            offset += 1

    def _parse_aare(self, data: bytes, table_data: list, offset: int):
        """解析AARE（关联响应）"""
        if len(data) < 1:
            return

        # 结果
        if len(data) >= 1:
            result_map = {0x00: "接受", 0x01: "拒绝-永久", 0x02: "拒绝-临时"}
            result_name = result_map.get(data[0], f"未知(0x{data[0]:02X})")
            table_data.append(("  结果", f"0x{data[0]:02X}", result_name, "", offset, offset))
            offset += 1

    def _parse_dlms_data(self, data: bytes, table_data: list, offset: int, label: str):
        """解析DLMS数据值"""
        if len(data) < 1:
            return

        data_type = data[0]
        type_name = self.DATA_TYPES.get(data_type, f"未知(0x{data_type:02X})")

        if data_type == 0x09:  # Visible-String
            str_len = data[1] if len(data) > 1 else 0
            if len(data) >= 2 + str_len:
                str_val = data[2:2+str_len].decode('ascii', errors='replace')
                table_data.append((label, data[:2+str_len].hex(' ').upper(), str_val, f"Visible-String({str_len}字节)", offset, offset + 1 + str_len))
        elif data_type == 0x0A:  # UTF8-String
            str_len = data[1] if len(data) > 1 else 0
            if len(data) >= 2 + str_len:
                str_val = data[2:2+str_len].decode('utf-8', errors='replace')
                table_data.append((label, data[:2+str_len].hex(' ').upper(), str_val, f"UTF8-String({str_len}字节)", offset, offset + 1 + str_len))
        elif data_type == 0x06:  # Octet-String
            str_len = data[1] if len(data) > 1 else 0
            if len(data) >= 2 + str_len:
                hex_val = data[2:2+str_len].hex(' ').upper()
                table_data.append((label, data[:2+str_len].hex(' ').upper(), hex_val[:30] + ("..." if len(hex_val) > 30 else ""), f"Octet-String({str_len}字节)", offset, offset + 1 + str_len))
        elif data_type == 0x0F:  # Long-Unsigned
            if len(data) >= 3:
                val = struct.unpack('>H', data[1:3])[0]
                table_data.append((label, data[:3].hex(' ').upper(), str(val), "Long-Unsigned", offset, offset + 2))
        elif data_type == 0x12:  # Long64-Unsigned
            if len(data) >= 9:
                val = struct.unpack('>Q', data[1:9])[0]
                table_data.append((label, data[:9].hex(' ').upper(), str(val), "Long64-Unsigned", offset, offset + 8))
        else:
            table_data.append((label, data.hex(' ').upper()[:30] + ("..." if len(data) > 15 else ""), type_name, "", offset, offset + len(data) - 1))
