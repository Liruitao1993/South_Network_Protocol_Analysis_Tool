"""
HDLC协议解析器
基于IEC 62056-46标准（DLMS/COSEM数据链路层）
支持HDLC Frame Format Type 3
"""
import struct
from typing import Dict, Any, List, Optional, Tuple


class HDLCParser:
    """HDLC协议解析器 - 基于IEC 62056-46标准"""

    # HDLC帧起始符和结束符
    HDLC_FLAG = 0x7E  # 01111110

    # 控制域类型映射
    CONTROL_FIELD_TYPES = {
        # I帧：bit0=0
        'I': "信息帧 (Information - 信息帧，带有序号用于差错控制和流量控制)",
        # RR帧：bit0=1, bit1=0, bit3=0
        'RR': "接收准备就绪 (Receive Ready - 接收准备好，用于流量控制和应答)",
        # RNR帧：bit0=1, bit1=0, bit3=1
        'RNR': "接收未准备就绪 (Receive Not Ready - 接收未准备好，要求对方停止发送)",
        # SNRM帧：bit0=1, bit1=1, bit2=0, bit3=0
        'SNRM': "设置正常响应模式 (Set Normal Response Mode - 建立链路层连接)",
        # DISC帧：bit0=1, bit1=1, bit2=1, bit3=0
        'DISC': "断开连接 (Disconnect - 断开链路请求)",
        # UA帧：bit0=1, bit1=1, bit2=1, bit3=0 (bit6=1)
        'UA': "无编号确认 (Unnumbered Acknowledge - 无编号确认应答)",
        # DM帧：bit0=1, bit1=1, bit2=1, bit3=1
        'DM': "断开模式 (Disconnected Mode - 站点已断开模式)",
        # FRMR帧：bit0=1, bit1=1, bit2=1, bit3=0 (bit5=1)
        'FRMR': "帧拒绝 (Frame Reject - 帧拒绝应答)",
        # UI帧：bit0=1, bit1=1, bit2=0, bit3=0 (bit3=0表示UI)
        'UI': "无编号信息 (Unnumbered Information - 未确认信息帧)",
    }

    # 地址域特殊地址
    SPECIAL_ADDRESSES = {
        # 客户端特殊地址
        0x00: "NO_STATION (无站地址)",
        0x01: "客户端管理进程",
        0x10: "公共客户端 (最低安全级)",
        0x7F: "ALL_STATION (广播地址)",
        # 服务器端特殊地址
    }

    # HDLC链路层协商参数标识符（SNRM/UA信息域TLV标签，见ISO/IEC 13239 5.5.3.2）
    SNRM_UA_PARAM_TAGS = {
        0x05: "Max Info Field Length - Transmit (发送最大信息域长度)",
        0x06: "Max Info Field Length - Receive (接收最大信息域长度)",
        0x07: "Window Size - Transmit (发送窗口大小)",
        0x08: "Window Size - Receive (接收窗口大小)",
    }

    # DLMS APDU类型映射（按IEC 62056标准/Green Book定义）
    APDU_TYPES = {
        0x01: "AARQ (关联请求)",
        0x02: "AARE (关联响应)",
        0x03: "RLRQ (释放请求)",
        0x04: "RLRE (释放响应)",
        0x0C: "Confirmed-Service-Error",
        0x0E: "General-Block-Transfer",
        0x60: "AARQ (关联请求-BER)",
        0x61: "AARE (关联响应-BER)",
        0xC0: "Get-Request (读请求)",
        0xC1: "Set-Request (写请求)",
        0xC3: "Action-Request (方法请求)",
        0xC4: "Get-Response (读应答)",
        0xC5: "Set-Response (写应答)",
        0xC7: "Action-Response (方法应答)",
        0xC8: "Glo-Get-Request (加密读请求)",
        0xC9: "Glo-Set-Request (加密写请求)",
        0xCB: "Glo-Action-Request (加密方法请求)",
        0xCC: "Glo-Get-Response (加密读应答)",
        0xCD: "Glo-Set-Response (加密写应答)",
        0xCF: "Glo-Action-Response (加密方法应答)",
        0xD0: "Ded-Get-Request (专属加密读请求)",
        0xD1: "Ded-Set-Request (专属加密写请求)",
        0xD3: "Ded-Action-Request (专属加密方法请求)",
        0xD4: "Ded-Get-Response (专属加密读应答)",
        0xD5: "Ded-Set-Response (专属加密写应答)",
        0xD7: "Ded-Action-Response (专属加密方法应答)",
        0xE6: "Event-Notification (事件通知)",
        0xE7: "Data-Notification (数据推送)",
    }

    # Get-Request/Response 子类型
    GET_REQUEST_TYPES = {
        0x01: "Normal (正常读)",
        0x02: "Next-Data-block (下一数据块)",
        0x03: "With-list (批量读)",
        0x04: "With-block (分块读)",
    }
    GET_RESPONSE_TYPES = {
        0x01: "Normal (正常响应)",
        0x02: "With-data-block (数据块响应)",
        0x03: "With-list (批量响应)",
    }

    # Set-Request/Response 子类型
    SET_REQUEST_TYPES = {
        0x01: "Normal (正常写)",
        0x02: "With-first-data-block (首块写)",
        0x03: "With-data-block (数据块写)",
        0x04: "With-list (批量写)",
        0x05: "With-list-and-first-data-block (批量首块写)",
    }
    SET_RESPONSE_TYPES = {
        0x01: "Normal (正常响应)",
        0x02: "With-data-block (数据块响应)",
        0x03: "With-last-data-block (最后块响应)",
        0x04: "With-list (批量响应)",
        0x05: "With-list-and-last-data-block (批量最后块响应)",
    }

    # Action-Request/Response 子类型
    ACTION_REQUEST_TYPES = {
        0x01: "Normal (普通)",
        0x02: "With-first-pblock (首参数块)",
        0x03: "With-list (批量)",
        0x04: "With-first-pblock-and-list (批量首参数块)",
        0x05: "With-pblock (参数块)",
    }
    ACTION_RESPONSE_TYPES = {
        0x01: "Normal (普通)",
        0x02: "With-pblock (参数块)",
        0x03: "With-list (批量)",
        0x04: "Next-pblock (下一参数块)",
        0x05: "With-list-and-first-pblock (批量首参数块)",
    }

    # Data-Access-Result 错误码
    DATA_ACCESS_RESULTS = {
        0x00: "成功",
        0x01: "硬件故障",
        0x02: "临时失败",
        0x03: "读写对象未定义",
        0x04: "对象不可访问",
        0x05: "数据类型不匹配",
        0x06: "对象未定义",
        0x07: "对象地址不匹配",
        0x08: "对象地址非法",
        0x09: "对象未定义",
        0x0A: "对象不在",
        0x0B: "对象访问被拒绝",
        0x0C: "类型不匹配",
        0x0D: "对象未激活",
        0x0E: "方法未定义",
        0x0F: "方法不支持",
        0x10: "参数数量错误",
        0x11: "参数类型错误",
        0x12: "参数值非法",
        0x13: "参数非法",
        0x14: "操作不支持",
        0x15: "其他原因",
    }

    # Action-Result 错误码
    ACTION_RESULTS = {
        0x00: "成功",
        0x01: "硬件故障",
        0x02: "临时失败",
        0x03: "读写对象未定义",
        0x04: "对象不可访问",
        0x05: "数据类型不匹配",
        0x06: "对象未定义",
        0x07: "对象地址不匹配",
        0x08: "对象地址非法",
        0x09: "对象未定义",
        0x0A: "对象不在",
        0x0B: "对象访问被拒绝",
        0x0C: "类型不匹配",
        0x0D: "对象未激活",
    }

    @staticmethod
    def _decode_invoke_id(invoke_byte: int) -> dict:
        """
        解码Invoke-Id-And-Priority字节
        结构: bit7-4=Invoke-ID(0-15), bit2=ServiceClass(0=Confirmed,1=Unconfirmed), bit1-0=Priority(0=High,1=Low)
        """
        invoke_id = (invoke_byte >> 4) & 0x0F
        service_class = "Confirmed(需确认)" if (invoke_byte & 0x04) == 0 else "Unconfirmed(不需确认)"
        priority = "High(高优先级)" if (invoke_byte & 0x03) == 0 else "Low(低优先级)"
        return {
            "invoke_id": invoke_id,
            "service_class": service_class,
            "priority": priority,
        }

    def parse_to_table(self, frame_bytes: bytes) -> list:
        """
        解析HDLC帧到表格格式
        
        返回: [(字段名, 原始值, 解析值, 说明, byte_start, byte_end), ...]
        """
        table_data = []
        
        if len(frame_bytes) < 7:
            table_data.append(("错误", "-", "-", "帧长度不足（至少7字节）", 0, len(frame_bytes) - 1))
            return table_data

        offset = 0

        # 1. 起始标志 (Flag)
        if frame_bytes[0] != self.HDLC_FLAG:
            table_data.append(("错误", f"0x{frame_bytes[0]:02X}", "0x7E", "起始标志错误", 0, 0))
            return table_data
        
        table_data.append(("起始标志", f"0x{frame_bytes[offset]:02X}", "0x7E", "HDLC帧起始标志", offset, offset))
        offset += 1

        # 2. 格式域 (Frame Format Field) - 2字节
        if offset + 1 >= len(frame_bytes):
            table_data.append(("错误", "-", "-", "格式域缺失", offset, offset))
            return table_data
        
        format_field_start = offset
        format_bytes = frame_bytes[offset:offset + 2]
        format_field = struct.unpack('>H', format_bytes)[0]  # 大端序
        
        # 解析格式域
        format_type = (format_field >> 12) & 0x0F  # 高4位
        segmentation_bit = (format_field >> 11) & 0x01  # 分段位
        frame_length = format_field & 0x07FF  # 低11位
        
        format_type_str = f"0x{format_type:X}"
        if format_type == 0x0A:
            format_type_str += " (Type 3)"
        
        table_data.append(("格式域", f"0x{format_field:04X}", 
                          f"格式类型={format_type_str}, 分段位={segmentation_bit}, 帧长={frame_length}",
                          "格式域（2字节）", offset, offset + 1))
        offset += 2

        # 验证格式类型
        if format_type != 0x0A:
            table_data.append(("警告", f"0x{format_type:X}", "0xA", "非Type 3格式（可能使用专有HCS算法）", format_field_start, format_field_start + 1))

        # 3. 目的地址域 (Destination Address)
        dest_addr_start = offset
        dest_addr, dest_addr_len = self._parse_address_field(frame_bytes, offset)
        if dest_addr is None:
            table_data.append(("错误", "-", "-", "目的地址解析失败", offset, offset))
            return table_data
        
        dest_addr_desc = self._format_address_description(dest_addr, dest_addr_len, "目的")
        table_data.append(("目的地址域", self._bytes_to_hex(frame_bytes[offset:offset + dest_addr_len]),
                          dest_addr_desc, f"目的地址（{dest_addr_len}字节）", offset, offset + dest_addr_len - 1))
        offset += dest_addr_len

        # 4. 源地址域 (Source Address)
        src_addr_start = offset
        src_addr, src_addr_len = self._parse_address_field(frame_bytes, offset)
        if src_addr is None:
            table_data.append(("错误", "-", "-", "源地址解析失败", offset, offset))
            return table_data
        
        src_addr_desc = self._format_address_description(src_addr, src_addr_len, "源")
        table_data.append(("源地址域", self._bytes_to_hex(frame_bytes[offset:offset + src_addr_len]),
                          src_addr_desc, f"源地址（{src_addr_len}字节）", offset, offset + src_addr_len - 1))
        offset += src_addr_len

        # 5. 控制域 (Control Field) - 1字节
        if offset >= len(frame_bytes):
            table_data.append(("错误", "-", "-", "控制域缺失", offset, offset))
            return table_data

        # 判断帧方向（基于地址域）:
        # 客户端→服务端: 目的=服务端(通常多字节), 源=客户端(通常1字节, 如0x01/0x03/0x09等)
        # 服务端→客户端: 目的=客户端(1字节), 源=服务端(多字节)
        if dest_addr_len > src_addr_len:
            frame_direction = "client_to_server"
        elif src_addr_len > dest_addr_len:
            frame_direction = "server_to_client"
        else:
            frame_direction = "unknown"

        control_byte = frame_bytes[offset]
        ctrl_type, ctrl_desc, ctrl_details = self._parse_control_field(control_byte, frame_direction)

        table_data.append(("控制域", f"0x{control_byte:02X}", ctrl_type, ctrl_desc, offset, offset))

        # 控制域子字段
        if ctrl_details:
            for field_name, raw_bit, parsed_val in ctrl_details:
                table_data.append((f"  {field_name}", raw_bit, parsed_val, "", offset, offset))

        offset += 1

        # 计算HCS范围（格式域2字节 + 目的地址 + 源地址 + 控制域）
        hcs_start = format_field_start
        hcs_end = offset - 1

        # 判断是否有信息域
        has_info_field = ctrl_type in ['I帧 (信息帧)', 'UI帧 (无编号信息)', 'SNRM帧', 'UA帧', 'DM帧', 'FRMR帧', 'DISC帧']
        
        # 6. HCS校验域 (Header Check Sequence) - 2字节
        # 如果帧长度很短（无信息域），HCS就是FCS
        if offset + 1 >= len(frame_bytes):
            table_data.append(("错误", "-", "-", "HCS/FCS缺失", offset, offset))
            return table_data
        
        if not has_info_field:
            # 无信息域，HCS被视为FCS
            hcs_bytes = frame_bytes[offset:offset + 2]
            hcs_value = struct.unpack('>H', hcs_bytes)[0]
            
            # 计算HCS
            calculated_hcs = self._calculate_fcs(frame_bytes[hcs_start:hcs_end + 1])
            # HCS传输时也是低字节在前，需要反转比较
            calculated_hcs_swapped = ((calculated_hcs & 0xFF) << 8) | ((calculated_hcs >> 8) & 0xFF)
            hcs_valid = "正确" if hcs_value == calculated_hcs_swapped else f"错误(计算值:0x{calculated_hcs:04X})"
            
            table_data.append(("HCS/FCS校验", f"0x{hcs_value:04X}", hcs_valid,
                              "头部校验（无信息域时作为FCS）", offset, offset + 1))
            offset += 2
        else:
            # 有信息域，先解析HCS
            hcs_bytes = frame_bytes[offset:offset + 2]
            hcs_value = struct.unpack('>H', hcs_bytes)[0]
            
            # 计算HCS
            calculated_hcs = self._calculate_fcs(frame_bytes[hcs_start:hcs_end + 1])
            # HCS传输时也是低字节在前，需要反转比较
            calculated_hcs_swapped = ((calculated_hcs & 0xFF) << 8) | ((calculated_hcs >> 8) & 0xFF)
            hcs_valid = "正确" if hcs_value == calculated_hcs_swapped else f"错误(计算值:0x{calculated_hcs:04X})"
            
            table_data.append(("HCS校验", f"0x{hcs_value:04X}", hcs_valid,
                              "头部校验（2字节）", offset, offset + 1))
            offset += 2

        # 7. 信息域 (Information Field) - 可变长度
        info_start = offset
        # FCS在倒数第3、4字节，结束标志在最后一个字节
        fcs_pos = len(frame_bytes) - 3
        
        if has_info_field and info_start < fcs_pos:
            info_data = frame_bytes[info_start:fcs_pos]
            
            table_data.append(("信息域", self._bytes_to_hex(info_data[:20]) + ("..." if len(info_data) > 20 else ""),
                              f"长度={len(info_data)}字节",
                              "信息域（携带上层数据）", info_start, fcs_pos - 1))
            
            # 尝试解析信息域内容
            if len(info_data) > 0:
                if ctrl_type in ('SNRM帧', 'UA帧'):
                    self._parse_snrm_ua_info(info_data, table_data, info_start)
                else:
                    self._parse_dlms_data(info_data, table_data, info_start)
            
            offset = fcs_pos

        # 8. FCS校验域 (Frame Check Sequence) - 2字节
        if offset + 1 < len(frame_bytes):
            fcs_bytes = frame_bytes[offset:offset + 2]
            fcs_value = struct.unpack('>H', fcs_bytes)[0]  # 大端序读取
            
            # 计算FCS（从格式域到信息域结束）
            if has_info_field and info_start < fcs_pos:
                fcs_data = frame_bytes[format_field_start:fcs_pos]
            else:
                # 无信息域时，FCS已经作为HCS/FCS一起解析过了
                fcs_data = None
            
            if fcs_data:
                calculated_fcs = self._calculate_fcs(fcs_data)
                # HDLC标准中FCS传输时低字节在前（小端序），所以需要反转比较
                calculated_fcs_swapped = ((calculated_fcs & 0xFF) << 8) | ((calculated_fcs >> 8) & 0xFF)
                fcs_valid = "正确" if fcs_value == calculated_fcs_swapped else f"错误(计算值:0x{calculated_fcs:04X})"
                
                table_data.append(("FCS校验", f"0x{fcs_value:04X}", fcs_valid,
                                  "帧校验序列（2字节）", offset, offset + 1))
            offset += 2

        # 9. 结束标志 (Closing Flag)
        if offset < len(frame_bytes):
            if frame_bytes[offset] == self.HDLC_FLAG:
                table_data.append(("结束标志", f"0x{frame_bytes[offset]:02X}", "0x7E", "HDLC帧结束标志", offset, offset))
            else:
                table_data.append(("结束标志", f"0x{frame_bytes[offset]:02X}", "0x7E", "结束标志错误", offset, offset))

        return table_data

    def _parse_address_field(self, data: bytes, offset: int) -> Tuple[Optional[int], int]:
        """
        解析HDLC地址域（支持扩展地址机制）

        返回: (地址值, 地址长度)
        地址扩展规则：每个字节的LSB=0表示后面还有地址字节，LSB=1表示最后一个地址字节
        注意：地址值需要移除LSB扩展位后组合，第一个字节传输最低7位，最后一个字节传输最高7位
        """
        if offset >= len(data):
            return None, 0

        address = 0
        length = 0
        shift = 0

        while offset + length < len(data):
            byte = data[offset + length]
            length += 1

            # LSB (bit 0) 表示是否还有扩展字节
            extension_bit = byte & 0x01
            address_value = (byte >> 1) & 0x7F  # 高7位是地址值

            # 按传输顺序组合：第一个字节是最低7位，每增加一个字节向高位移7位
            address |= (address_value << shift)
            shift += 7

            # LSB=1表示这是最后一个地址字节，停止
            if extension_bit == 0x01:
                break

            # 安全检查：最多4字节地址，如果还没遇到结束标记就停止
            if length >= 4:
                break

        return address, length

    def _format_address_description(self, address: int, length: int, role: str) -> str:
        """格式化地址描述"""
        # 检查特殊地址
        special = self.SPECIAL_ADDRESSES.get(address, "")
        if special:
            return f"0x{address:02X} ({special})"
        
        # 普通地址
        if length == 1:
            return f"0x{address:02X} ({role}单字节地址)"
        elif length == 2:
            return f"0x{address:04X} ({role}双字节地址)"
        elif length == 4:
            return f"0x{address:08X} ({role}四字节地址)"
        else:
            return f"0x{address:X} ({role}{length}字节地址)"

    def _parse_control_field(self, control_byte: int, direction: str = "unknown") -> Tuple[str, str, List[Tuple[str, str, str]]]:
        """
        解析控制域

        参数:
            control_byte: 控制域字节
            direction: "client_to_server"(客户端发) 或 "server_to_client"(服务端发) 或 "unknown"

        返回: (帧类型名称, 详细描述, 子字段列表[(字段名, 原始bit显示, 解析值)])

        P/F位解释规则(IEC 62056):
          - 客户端发送的帧: bit4=P(Poll), P=1表示需要服务端响应
          - 服务端发送的帧: bit4=F(Final), F=1表示这是最后一帧(无后续数据)
        """
        details = []

        # P/F位描述根据方向不同
        def pf_desc(bit_val):
            if direction == "client_to_server":
                return "P=1(需响应)" if bit_val else "P=0"
            elif direction == "server_to_client":
                return "F=1(最终帧)" if bit_val else "F=0(有后续)"
            else:
                return "P/F=1" if bit_val else "P/F=0"

        # 生成原始bit字符串，例如 "bit7-bit5: 101"
        def bit_range_mask(shift: int, mask: int) -> str:
            value = (control_byte >> shift) & mask
            bits = bin(value)[2:].zfill(bin(mask).count('1'))
            msb = shift + bin(mask).count('1') - 1
            lsb = shift
            if msb == lsb:
                return f"bit{msb}: {bits}"
            else:
                return f"bit{msb}-bit{lsb}: {bits}"

        # 判断帧类型
        # I帧：bit0=0
        if (control_byte & 0x01) == 0:
            # I帧格式: N(R) P/F N(S) 0
            n_r = (control_byte >> 5) & 0x07  # 接收序列号 N(R)
            p_f = (control_byte >> 4) & 0x01  # P/F位
            n_s = (control_byte >> 1) & 0x07  # 发送序列号 N(S)

            details = [
                ("N(R)接收序号", bit_range_mask(5, 0b111), str(n_r)),
                ("P/F位", bit_range_mask(4, 0b1), pf_desc(p_f)),
                ("N(S)发送序号", bit_range_mask(1, 0b111), str(n_s)),
            ]
            return "I帧 (信息帧)", f"信息传输帧, N(S)={n_s}, N(R)={n_r}", details

        # 检查其他帧类型（bit0=1）
        # UI帧: 0 0 0 P/F 0 0 1 1 = 0x03 (P/F=0) 或 0x0B (P/F=1)
        if (control_byte & 0xEF) == 0x03:  # 屏蔽bit4 (P/F位)
            p_f = (control_byte >> 4) & 0x01
            details = [
                ("P/F位", bit_range_mask(4, 0b1), pf_desc(p_f)),
            ]
            return "UI帧 (无编号信息)", f"无编号信息传输", details

        # SNRM帧: 1 0 0 P 0 0 1 1 = 0x83 (P=0) 或 0x93 (P=1)
        if (control_byte & 0xEF) == 0x83:  # 屏蔽bit4 (P位)
            p = (control_byte >> 4) & 0x01
            details = [
                ("P位(查询)", bit_range_mask(4, 0b1), "是" if p else "否"),
            ]
            return "SNRM帧", f"设置正常响应模式, P={'是' if p else '否'}", details

        # DISC帧: 010 P 0011 = 0x43 或 0x53 (bit7=0, bit6=1, bit5=0, bit4=P, bit3-0=0011)
        if (control_byte & 0x0F) == 0x03 and (control_byte & 0xE0) in [0x40, 0x50]:
            p = (control_byte >> 4) & 0x01
            details = [
                ("P位(查询)", bit_range_mask(4, 0b1), "是" if p else "否"),
            ]
            return "DISC帧", f"断开连接, P={'是' if p else '否'}", details

        # UA帧: 011 F 0011 = 0x63 或 0x73 (bit7=0, bit6=1, bit5=1, bit4=F, bit3-0=0011)
        if (control_byte & 0x0F) == 0x03 and (control_byte & 0xE0) in [0x60, 0x70]:
            f = (control_byte >> 4) & 0x01
            details = [
                ("F位(最终)", bit_range_mask(4, 0b1), "是" if f else "否"),
            ]
            return "UA帧", f"无编号确认, F={'是' if f else '否'}", details

        # DM帧: 000 F 1111 = 0x0F 或 0x1F (bit7-4=0000/0001, bit3-0=1111)
        if (control_byte & 0x0F) == 0x0F and (control_byte & 0xE0) in [0x00, 0x10]:
            f = (control_byte >> 4) & 0x01
            details = [
                ("F位(最终)", bit_range_mask(4, 0b1), "是" if f else "否"),
            ]
            return "DM帧", f"断开模式, F={'是' if f else '否'}", details

        # FRMR帧: 100 F 0111 = 0x87 或 0x97 (bit7=1, bit6-5=00, bit4=F, bit3-0=0111)
        if (control_byte & 0x0F) == 0x07 and (control_byte & 0xE0) in [0x80, 0x90]:
            f = (control_byte >> 4) & 0x01
            details = [
                ("F位(最终)", bit_range_mask(4, 0b1), "是" if f else "否"),
            ]
            return "FRMR帧", f"帧拒绝, F={'是' if f else '否'}", details

        # RR帧: N(R) P/F 0001 (bit7-5=N(R), bit4=P/F, bit3-0=0001)
        if (control_byte & 0x0F) == 0x01:
            n_r = (control_byte >> 5) & 0x07
            p_f = (control_byte >> 4) & 0x01
            details = [
                ("N(R)接收序号", bit_range_mask(5, 0b111), str(n_r)),
                ("P/F位", bit_range_mask(4, 0b1), pf_desc(p_f)),
            ]
            return "RR帧 (接收就绪)", f"接收就绪, N(R)={n_r}", details

        # RNR帧: N(R) P/F 0101 (bit7-5=N(R), bit4=P/F, bit3-0=0101)
        if (control_byte & 0x0F) == 0x05:
            n_r = (control_byte >> 5) & 0x07
            p_f = (control_byte >> 4) & 0x01
            details = [
                ("N(R)接收序号", bit_range_mask(5, 0b111), str(n_r)),
                ("P/F位", bit_range_mask(4, 0b1), pf_desc(p_f)),
            ]
            return "RNR帧 (接收未就绪)", f"接收未就绪(忙), N(R)={n_r}", details

        # 未识别类型
        return f"未知帧(0x{control_byte:02X})", "未识别的控制域类型", []

    def _calculate_fcs(self, data: bytes) -> int:
        """
        计算FCS/HCS校验和
        使用CCITT-CRC16多项式: x^16 + x^12 + x^5 + 1 (0x8408)
        """
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0x8408
                else:
                    crc >>= 1
        return crc ^ 0xFFFF

    def _parse_snrm_ua_info(self, data: bytes, table_data: list, base_offset: int):
        """
        解析SNRM/UA帧信息域 - HDLC链路层协商参数（见ISO/IEC 13239 5.5.3.2）

        信息域格式:
          81H - 格式标识符 (Format Identifier)
          80H - 组标识符 (Group Identifier)
          n   - 组长度 (Group Length)
          [参数TLV列表]:
            Tag(1B)  - 参数标识符
            Len(1B)  - 参数长度
            Value(nB)- 参数值
        """
        offset = 0

        if len(data) < 3:
            # 信息域太短，无法包含协商参数
            table_data.append(("  链路协商数据", self._bytes_to_hex(data),
                              f"{len(data)}字节", "数据过短，无协商参数",
                              base_offset, base_offset + max(len(data) - 1, 0)))
            return

        # 格式标识符 0x81
        fmt_id = data[offset]
        table_data.append(("  格式标识符", f"0x{fmt_id:02X}",
                          "格式标识符" if fmt_id == 0x81 else f"非标准值(期望0x81)",
                          "标识SNRM/UA参数协商格式", base_offset + offset, base_offset + offset))
        offset += 1

        # 组标识符 0x80
        group_id = data[offset]
        table_data.append(("  组标识符", f"0x{group_id:02X}",
                          "组标识符" if group_id == 0x80 else f"非标准值(期望0x80)",
                          "", base_offset + offset, base_offset + offset))
        offset += 1

        # 组长度
        group_len = data[offset]
        table_data.append(("  组长度", f"0x{group_len:02X}", f"{group_len}字节",
                          "后续参数字节总数", base_offset + offset, base_offset + offset))
        offset += 1

        # 解析参数TLV列表
        param_end = offset + group_len
        while offset < param_end and offset < len(data):
            # 参数标识符
            tag = data[offset]
            tag_desc = self.SNRM_UA_PARAM_TAGS.get(tag, f"未知参数(0x{tag:02X})")
            table_data.append(("    参数标识符", f"0x{tag:02X}", tag_desc,
                              "", base_offset + offset, base_offset + offset))
            offset += 1

            if offset >= len(data):
                break

            # 参数长度
            param_len = data[offset]
            table_data.append(("    参数长度", f"0x{param_len:02X}", f"{param_len}字节",
                              "", base_offset + offset, base_offset + offset))
            offset += 1

            if offset + param_len > len(data):
                break

            # 参数值
            param_value_bytes = data[offset:offset + param_len]
            hex_str = self._bytes_to_hex(param_value_bytes)

            # 根据长度解析数值
            if param_len == 1:
                val = param_value_bytes[0]
                val_display = f"{val} (0x{val:02X})"
            elif param_len == 2:
                val = struct.unpack('>H', param_value_bytes)[0]
                val_display = f"{val} (0x{val:04X})"
            elif param_len == 4:
                val = struct.unpack('>I', param_value_bytes)[0]
                val_display = f"{val} (0x{val:08X})"
            else:
                val_display = hex_str

            table_data.append(("    参数值", hex_str, val_display,
                              tag_desc, base_offset + offset, base_offset + offset + param_len - 1))
            offset += param_len

    def _parse_dlms_data(self, data: bytes, table_data: list, base_offset: int):
        """
        解析信息域中的DLMS数据
        LLC子层格式: DSAP(1) + SSAP(1) + Control(1) + DLMS APDU
        方向识别规则（IEC 62056标准）:
          - 客户端→服务端（请求）: LLC = E6 E6 00
          - 服务端→客户端（应答）: LLC = E6 E7 00
        """
        if len(data) < 2:
            return

        offset = 0
        direction = "unknown"  # "request" 或 "response"

        # 检查是否包含LLC子层（DSAP + SSAP + Control = 3字节）
        if len(data) >= 3:
            dsap = data[0]
            ssap = data[1]
            llc_ctrl = data[2]

            # DLMS LLC地址特征:
            #   DSAP=0xE6, SSAP=0xE6, Control=0x00 → 客户端请求
            #   DSAP=0xE6, SSAP=0xE7, Control=0x00 → 服务端应答
            # 也可能出现 DSAP=0xE7, SSAP=0xE6 的情况（取决于实现）
            if dsap in (0xE6, 0xE7) and ssap in (0xE6, 0xE7) and llc_ctrl == 0x00:
                # 判断方向
                if dsap == 0xE6 and ssap == 0xE6:
                    direction = "request"
                    dir_desc = "客户端→服务端（请求方向）"
                elif dsap == 0xE6 and ssap == 0xE7:
                    direction = "response"
                    dir_desc = "服务端→客户端（应答方向）"
                elif dsap == 0xE7 and ssap == 0xE6:
                    direction = "response"
                    dir_desc = "服务端→客户端（应答方向）"
                else:
                    dir_desc = "LLC地址"

                table_data.append(("  LLC DSAP", f"0x{dsap:02X}",
                                  f"0x{(dsap >> 1):02X}" if dsap & 1 else f"0x{dsap:02X}",
                                  "目的服务接入点",
                                  base_offset + offset, base_offset + offset))
                offset += 1

                table_data.append(("  LLC SSAP", f"0x{ssap:02X}",
                                  f"0x{(ssap >> 1):02X}" if ssap & 1 else f"0x{ssap:02X}",
                                  "源服务接入点",
                                  base_offset + offset, base_offset + offset))
                offset += 1

                table_data.append(("  LLC控制", f"0x{llc_ctrl:02X}",
                                  dir_desc, "LLC服务质量",
                                  base_offset + offset, base_offset + offset))
                offset += 1
            elif dsap >= 0xE0 and ssap >= 0xE0:
                # 其他LLC地址（兼容旧版）
                table_data.append(("  LLC DSAP", f"0x{dsap:02X}",
                                  f"0x{(dsap >> 1):02X}" if dsap & 1 else f"0x{dsap:02X}",
                                  "目的服务接入点",
                                  base_offset + offset, base_offset + offset))
                offset += 1

                table_data.append(("  LLC SSAP", f"0x{ssap:02X}",
                                  f"0x{(ssap >> 1):02X}" if ssap & 1 else f"0x{ssap:02X}",
                                  "源服务接入点",
                                  base_offset + offset, base_offset + offset))
                offset += 1

                table_data.append(("  LLC控制", f"0x{llc_ctrl:02X}",
                                  f"服务质量=0x{llc_ctrl:02X}", "LLC质量控制字段",
                                  base_offset + offset, base_offset + offset))
                offset += 1

        # 检查是否有 Wrapper 头部 (WPDU - wrapper protocol data unit)
        # Wrapper 格式: 版本(2B) + 源端口(2B) + 目的端口(2B) + 长度(2B) = 总共8字节
        # 版本固定为 0x0001
        if len(data) >= offset + 8:
            version = (data[offset] << 8) | data[offset + 1]
            if version == 1:
                # 识别到 Wrapper 头部
                src_port = (data[offset + 2] << 8) | data[offset + 3]
                dst_port = (data[offset + 4] << 8) | data[offset + 5]
                apdu_len = (data[offset + 6] << 8) | data[offset + 7]

                table_data.append(("  Wrapper版本", f"{data[offset]:02X} {data[offset + 1]:02X}",
                                  str(version), "Wrapper协议版本（固定为1）",
                                  base_offset + offset, base_offset + offset + 1))
                table_data.append(("  Wrapper源端口", f"{data[offset + 2]:02X} {data[offset + 3]:02X}",
                                  f"0x{src_port:04X} ({src_port})", "源端口号",
                                  base_offset + offset + 2, base_offset + offset + 3))
                table_data.append(("  Wrapper目的端口", f"{data[offset + 4]:02X} {data[offset + 5]:02X}",
                                  f"0x{dst_port:04X} ({dst_port})", "目的端口号",
                                  base_offset + offset + 4, base_offset + offset + 5))
                table_data.append(("  Wrapper长度", f"{data[offset + 6]:02X} {data[offset + 7]:02X}",
                                  f"{apdu_len} 字节", "真正DLMS-APDU数据长度",
                                  base_offset + offset + 6, base_offset + offset + 7))
                offset += 8
                table_data.append(("  Wrapper数据", "", "", "Wrapper头部之后是真正的DLMS-APDU",
                                  base_offset + offset, base_offset + offset))

        # 解析DLMS APDU
        if offset >= len(data):
            return

        apdu_start = offset
        apdu_byte = data[offset]

        # 添加整个APDU父节点（覆盖完整字节范围），方便双击选中整个APDU进行深度解析
        # 由于解析内容会增加offset，这里先占位，解析完成后修正？不直接处理：先走一遍再添加
        if apdu_byte in self.APDU_TYPES:
            # 保存当前offset，解析完后计算
            original_offset = offset
            apdu_name = self.APDU_TYPES[apdu_byte]
            offset += 1  # 跳过APDU类型字节
            # 保存当前table长度，解析后新添加的项都会缩进
            start_len = len(table_data)
            # 解析所有子字段，都会加上"  "前缀缩进，返回消耗的字节数
            consumed = self._parse_apdu_content(data[offset:], table_data, 0, apdu_byte, base_offset + offset, direction)
            # 更新offset：加上消耗的字节数
            offset += consumed
            # 现在offset已经走到APDU末尾之后，计算整个APDU的字节范围
            apdu_end = base_offset + (offset - 1)
            apdu_len = offset - original_offset
            # 在所有子字段前面插入整个APDU父行（覆盖完整范围）
            # 原始值显示APDU类型字节的十六进制，解析值显示名称+长度
            apdu_byte_val = data[apdu_start]
            table_data.insert(start_len, ("  DLMS APDU", f"0x{apdu_byte_val:02X}",
                                        f"{apdu_name} (整个{apdu_len}字节)",
                                        "完整DLMS应用层协议数据单元（双击可深度解析）",
                                        base_offset + original_offset, apdu_end))
        elif apdu_byte in (0x00, 0x01):
            # 长格式/短格式DLMS控制，然后是APDU
            dlms_ctrl_start = offset
            format_type = "长格式" if apdu_byte == 0x00 else "短格式"
            table_data.append(("  DLMS控制字段", f"0x{apdu_byte:02X}", format_type,
                              "DLMS帧格式",
                              base_offset + offset, base_offset + offset))
            offset += 1

            if apdu_byte == 0x00 and len(data) > offset + 4:
                dst_addr = data[offset:offset + 4]
                table_data.append(("    目标地址", self._bytes_to_hex(dst_addr),
                                  "4字节", "长格式目标地址",
                                  base_offset + offset, base_offset + offset + 3))
                offset += 4

                if len(data) > offset:
                    src_addr = data[offset]
                    table_data.append(("    源地址", f"0x{src_addr:02X}",
                                      "1字节", "",
                                      base_offset + offset, base_offset + offset))
                    offset += 1

            if len(data) > offset and data[offset] in self.APDU_TYPES:
                # 整个APDU作为父节点
                original_offset = offset
                apdu_byte2 = data[offset]
                apdu_name = self.APDU_TYPES[apdu_byte2]
                offset += 1
                start_len = len(table_data)
                # 解析所有子字段，会自动缩进，返回消耗的字节数
                consumed = self._parse_apdu_content(data[offset:], table_data, 0, apdu_byte2, base_offset + offset, direction)
                # 更新offset
                offset += consumed
                apdu_end = base_offset + (offset - 1)
                apdu_len = offset - original_offset
                # 插入父行
                apdu_byte_val = data[apdu_start]
                table_data.insert(start_len, ("      DLMS APDU", f"0x{apdu_byte_val:02X}",
                                            f"{apdu_name} (整个{apdu_len}字节)",
                                            "完整DLMS应用层协议数据单元（双击可深度解析）",
                                            base_offset + original_offset, apdu_end))
        else:
            # BER-TLV编码（AARQ/AARE等使用BER编码） - 添加整个APDU父节点
            if self._looks_like_ber_tlv(data[offset:]):
                original_offset = offset
                start_len = len(table_data)
                total_len = len(data) - offset
                # _parse_ber_tlv 会递归解析所有子项并正确增加缩进
                self._parse_ber_tlv(data[offset:], table_data, base_offset + offset + 2)
                # offset不会被_parse_ber_tlv修改，它走参数传递，所以我们知道完整范围
                apdu_end = base_offset + (original_offset + total_len - 1)
                # 插入父节点
                table_data.insert(start_len, ("  DLMS APDU (BER-TLV)", f"整个APDU {total_len}字节", "BER-TLV编码",
                                            "完整DLMS APDU（双击可深度解析）",
                                            base_offset + original_offset, apdu_end))
            else:
                # 未识别的APDU，仍添加整个范围父节点
                original_offset = offset
                total_len = len(data) - offset
                apdu_end = base_offset + (original_offset + total_len - 1)
                table_data.append(("  DLMS APDU", f"整个APDU {total_len}字节", "未识别类型",
                                  "完整DLMS应用层协议数据单元（双击可深度解析）",
                                  base_offset + original_offset, apdu_end))
    
    def _looks_like_ber_tlv(self, data: bytes) -> bool:
        """检查数据是否像BER-TLV编码"""
        # 只要长度>=2，都尝试解析BER-TLV，因为标签可以是任何值
        return len(data) >= 2
    
    def _parse_ber_tlv(self, data: bytes, table_data: list, base_offset: int):
        """解析BER-TLV编码的数据，循环解析直到所有字节处理完"""
        if len(data) < 2:
            return

        offset = 0
        local_offset = base_offset

        # 循环解析多个连续的BER-TLV元素，直到所有字节处理完毕
        while offset < len(data):
            if offset + 1 >= len(data):
                # 剩余字节不足，停止解析
                break

            # 解析标签
            tag = data[offset]
            tag_desc = ""
            tag_number = tag

            if tag == 0x1F:
                # 高标签号：后续字节包含实际标签
                # 简化处理：取下一个字节
                if offset + 1 < len(data):
                    tag_number = data[offset + 1]
                    tag_desc = f"高标签号 0x{tag_number:02X}"
                    offset += 1
                    local_offset += 1
                else:
                    tag_desc = "高标签号（不完整）"
            elif 0x60 <= tag <= 0x7F:
                # APPLICATION标签
                app_num = tag - 0x60
                app_names = {
                    0: "APPLICATION 0",
                    1: "AARQ (关联请求)",
                    2: "AARE (关联响应)",
                    3: "RLRQ (释放请求)",
                    4: "RLRE (释放响应)"
                }
                tag_desc = app_names.get(app_num, f"APPLICATION {app_num}")
            elif 0xA0 <= tag <= 0xBF:
                # Context-Specific标签
                ctx_num = tag - 0xA0
                # AARQ/AARE 中常见 Context-Specific 标签含义
                ctx_names = {
                    0: "negotiated-dlms-version",
                    1: "proposed-parameter-pp",
                    2: "proposed-parameter-challenge",
                    3: "client-sap-id",
                    4: "association-information",
                    5: "xdlms-context-info",
                    6: "authentication",
                    7: "mechanism-name",
                    8: "challenge",
                    9: "response",
                    10: "server-sap-id",
                    11: "proposed-quality-of-service",
                    12: "password",
                    30: "user-information",
                }
                if ctx_num in ctx_names:
                    tag_desc = f"Context-Specific [{ctx_num}] {ctx_names[ctx_num]}"
                else:
                    tag_desc = f"Context-Specific [{ctx_num}]"
            else:
                # 解析 BER 标签: 解码 class + constructed + tag number
                tag_class = (tag >> 6) & 0x03
                constructed = (tag >> 5) & 0x01
                tag_number = tag & 0x1F
                class_names = {0: "Universal", 1: "Application", 2: "Context-Specific", 3: "Private"}
                class_name = class_names.get(tag_class, f"Class-{tag_class}")
                constructed_str = " constructed" if constructed else ""

                # 通用标签名称映射
                universal_names = {
                    0x01: "BOOLEAN",
                    0x02: "INTEGER",
                    0x03: "BIT STRING",
                    0x04: "OCTET STRING",
                    0x05: "NULL",
                    0x06: "OBJECT IDENTIFIER",
                    0x09: "REAL",
                    0x0A: "ENUMERATED",
                    0x0D: "ENUMERATED",
                    0x10: "SEQUENCE",
                    0x13: "SET",
                    0x30: "SEQUENCE",
                    0x31: "SET",
                    0x35: "SEQUENCE OF",
                    0x47: "OCTET STRING",
                    0xBE: "Context-Specific [30]",
                }
                if tag_class == 0 and tag_number in universal_names:
                    tag_desc = f"{class_name} {universal_names[tag_number]}{constructed_str}"
                elif tag_class == 2:  # Context-Specific
                    ctx_names = {
                        4: "invoke-id-and-priority",
                    }
                    if tag_number in ctx_names:
                        tag_desc = f"{class_name} [{tag_number}] {ctx_names[tag_number]}{constructed_str}"
                    else:
                        tag_desc = f"{class_name} [{tag_number}]{constructed_str}"
                else:
                    tag_desc = f"{class_name} [{tag_number}]{constructed_str}"

            table_data.append(("    BER标签", f"0x{tag:02X}" + (f" 0x{tag_number:02X}" if tag == 0x1F else ""),
                              tag_desc, "BER-TLV标签", local_offset, local_offset))
            offset += 1
            local_offset += 1

            # 解析长度
            tlv_length = 0
            if offset < len(data):
                length_byte = data[offset]
                if length_byte < 0x80:
                    # 短格式长度
                    tlv_length = length_byte
                    table_data.append(("    BER长度", f"0x{length_byte:02X}", str(tlv_length), "TLV长度", local_offset, local_offset))
                    offset += 1
                    local_offset += 1
                elif length_byte == 0x80:
                    # 不定长度
                    table_data.append(("    BER长度", "0x80", "不定长度", "需要结束标记", local_offset, local_offset))
                    offset += 1
                    local_offset += 1
                    tlv_length = len(data) - offset
                else:
                    # 长格式长度
                    num_length_bytes = length_byte & 0x7F
                    if offset + 1 + num_length_bytes <= len(data):
                        tlv_length = 0
                        len_bytes = data[offset + 1:offset + 1 + num_length_bytes]
                        for b in len_bytes:
                            tlv_length = (tlv_length << 8) | b
                        table_data.append(("    BER长度", self._bytes_to_hex(data[offset:offset+1+num_length_bytes]),
                                          str(tlv_length), f"TLV长度({num_length_bytes}字节)", local_offset, local_offset + num_length_bytes))
                        offset += 1 + num_length_bytes
                        local_offset += 1 + num_length_bytes
                    else:
                        tlv_length = len(data) - offset

            # 解析值
            if offset < len(data) and tlv_length > 0:
                value_data = data[offset:offset + min(tlv_length, len(data) - offset)]

                # 根据标签类型解析值
                parsed_value = f"{len(value_data)}字节"
                # 检查是否是基本类型，尝试解析
                if tag_number == 0x01:  # BOOLEAN
                    if len(value_data) >= 1:
                        parsed_value = "TRUE" if value_data[0] != 0 else "FALSE"
                elif tag_number == 0x02:  # INTEGER
                    if len(value_data) >= 1:
                        # 大端序解析为整数
                        val = 0
                        for b in value_data:
                            val = (val << 8) | b
                        # 检查是否有符号
                        if (value_data[0] & 0x80) != 0:
                            # 负数，补码转换
                            val -= (1 << (8 * len(value_data)))
                        parsed_value = str(val)
                elif tag_number == 0x06:  # OBJECT IDENTIFIER
                    if len(value_data) >= 1:
                        # OID 编码：第一个字节 = 40*first + second
                        oid_parts = []
                        if len(value_data) >= 1:
                            first = value_data[0]
                            oid_parts.append(str(first // 40))
                            oid_parts.append(str(first % 40))
                            # 剩余字节使用可变长度编码
                            val = 0
                            for b in value_data[1:]:
                                val = (val << 7) | (b & 0x7F)
                                if (b & 0x80) == 0:
                                    oid_parts.append(str(val))
                                    val = 0
                            parsed_value = ".".join(oid_parts)
                elif tag_number in [0x03, 0x04, 0x09, 0x0A]:  # BIT STRING, OCTET STRING, REAL, ENUMERATED
                    if tag_number == 0x0A and len(value_data) >= 1:  # ENUMERATED
                        val = 0
                        for b in value_data:
                            val = (val << 8) | b
                        parsed_value = str(val)
                    else:
                        # OCTET STRING / BIT STRING 保持十六进制显示
                        if len(value_data) <= 20:
                            parsed_value = self._bytes_to_hex(value_data)
                        else:
                            parsed_value = self._bytes_to_hex(value_data[:20]) + "..."

                table_data.append(("    BER值", self._bytes_to_hex(value_data[:20]) + ("..." if len(value_data) > 20 else ""),
                                  parsed_value, "TLV值数据", local_offset, local_offset + min(len(value_data) - 1, 19)))

                # 判断是否是 constructed 类型（bit6 = 1 表示 constructed）
                # 编码: [bit8-7: class][bit6: constructed][bits5-1: tag]
                is_constructed = (tag & 0x20) != 0  # bit6 是 constructed 标志
                # constructed 类型肯定包含嵌套 TLV，递归解析
                # primitive 类型如果长度大于 2 也可能包含嵌套（比如 OCTET STRING 包含 SEQUENCE）
                if (is_constructed or len(value_data) > 2) and len(value_data) >= 2:
                    self._parse_ber_tlv(value_data, table_data, local_offset)

                # 移动偏移
                offset += len(value_data)
                local_offset += len(value_data)
            else:
                # 没有值数据，跳出循环
                break
    
    def _parse_cosem_descriptor(self, data: bytes, table_data: list, base_offset: int, label_prefix: str = "    ") -> int:
        """
        解析Cosem-Attribute-Descriptor或Cosem-Method-Descriptor
        结构: Class-ID(2字节,大端) + Instance-ID/OBIS(6字节) + Attribute-ID或Method-ID(1字节)
        返回消耗的字节数
        """
        offset = 0
        if len(data) < 9:
            return 0

        # Class-ID (2字节, 大端序)
        class_id = struct.unpack('>H', data[offset:offset + 2])[0]
        class_name = {
            1: "Data (数据)", 3: "Register (寄存器)", 4: "Extended-Register (扩展寄存器)",
            5: "Demand-Register (需求寄存器)", 6: "Activity-Calendar (活动日历)",
            7: "Profile-Generic (配置文件)", 8: "Clock (时钟)", 9: "Script-Table (脚本表)",
            10: "Schedule (调度器)", 15: "Special-Days-Table (特殊天数表)",
            17: "Association-Logical-Device (关联逻辑设备)",
            20: "Association-Snapshot (关联快照)",
            42: "MBus-Client-Port", 70: "Pulse-Counter (脉冲计数器)",
            81: "Comms-Port-HDLC (通信口HDLC)",
            100: "Application-Association (应用关联)",
            101: "Security-Setup (安全设置)",
            111: "Disconnect-Control (断开控制)",
        }.get(class_id, f"Class-{class_id}")

        table_data.append((f"{label_prefix}类ID (Class-ID)", f"0x{class_id:04X}", class_name,
                          "COSEM对象类", base_offset + offset, base_offset + offset + 1))
        offset += 2

        # Instance-ID / OBIS码 (6字节)
        obis_bytes = data[offset:offset + 6]
        obis_str = ".".join(str(b) for b in obis_bytes)
        obis_desc = self._get_obis_description(obis_bytes)

        table_data.append((f"{label_prefix}OBIS码", self._bytes_to_hex(obis_bytes), obis_str,
                          f"对象标识: {obis_desc}", base_offset + offset, base_offset + offset + 5))
        offset += 6

        # Attribute-ID 或 Method-ID (1字节)
        attr_id = data[offset]
        table_data.append((f"{label_prefix}属性ID", f"0x{attr_id:02X}", str(attr_id),
                          "对象属性索引", base_offset + offset, base_offset + offset))
        offset += 1

        return offset

    @staticmethod
    def _get_obis_description(obis_bytes: bytes) -> str:
        """根据OBIS码返回描述"""
        obis_str = ".".join(str(b) for b in obis_bytes)
        # 常见电能表OBIS码中文映射表
        obis_map = {
            # 逻辑设备信息
            "0.0.96.1.0.255": "逻辑设备名称",
            "0.0.96.1.1.255": "设备标识/资产号/电表编号",
            "0.0.96.1.2.255": "固件版本/软件版本",
            "0.0.96.1.3.255": "硬件版本",
            "0.0.96.1.4.255": "出厂编号",
            "0.0.96.1.5.255": "安装日期",

            # 设备状态和管理
            "0.0.96.3.1.255": "电表运行状态",
            "0.0.96.3.2.255": "电表错误状态",
            "0.0.96.3.10.255": "断开控制对象",
            "0.0.10.0.1.255": "脚本表对象",
            "0.0.99.98.1.255": "电力事件日志",
            "0.0.99.98.2.255": "事件记录/日志",
            "0.0.99.98.3.255": "故障记录/掉电记录",
            "0.0.99.98.4.255": "电压异常记录",
            "0.0.99.98.5.255": "电流异常记录",

            # 总有功电能
            "1.0.1.8.0.255": "正向有功电能总累计",
            "1.0.1.8.1.255": "正向有功电能费率1 (尖)",
            "1.0.1.8.2.255": "正向有功电能费率2 (峰)",
            "1.0.1.8.3.255": "正向有功电能费率3 (平)",
            "1.0.1.8.4.255": "正向有功电能费率4 (谷)",
            "1.0.1.8.5.255": "正向有功电能费率5",
            "1.0.1.8.6.255": "正向有功电能费率6",

            # 反方向有功电能
            "1.0.2.8.0.255": "反向有功电能总累计",
            "1.0.2.8.1.255": "反向有功电能费率1 (尖)",
            "1.0.2.8.2.255": "反向有功电能费率2 (峰)",
            "1.0.2.8.3.255": "反向有功电能费率3 (平)",
            "1.0.2.8.4.255": "反向有功电能费率4 (谷)",

            # 四象限无功电能
            "1.0.3.8.0.255": "正向无功电能总累计(I象限)",
            "1.0.3.8.1.255": "正向无功电能费率1(I象限)",
            "1.0.3.8.2.255": "正向无功电能费率2(I象限)",
            "1.0.3.8.3.255": "正向无功电能费率3(I象限)",
            "1.0.3.8.4.255": "正向无功电能费率4(I象限)",

            "1.0.4.8.0.255": "反向无功电能总累计(II象限)",
            "1.0.4.8.1.255": "反向无功电能费率1(II象限)",
            "1.0.4.8.2.255": "反向无功电能费率2(II象限)",
            "1.0.4.8.3.255": "反向无功电能费率3(II象限)",
            "1.0.4.8.4.255": "反向无功电能费率4(II象限)",

            "1.0.5.8.0.255": "第三象限无功总累计",
            "1.0.6.8.0.255": "第四象限无功总累计",

            # 最大需量
            "1.0.15.8.0.255": "正向有功最大需量",
            "1.0.16.8.0.255": "反向有功最大需量",
            "1.0.17.8.0.255": "正向无功最大需量",
            "1.0.18.8.0.255": "反向无功最大需量",

            # 瞬时测量值 - 电压
            "1.0.21.7.0.255": "A相(L1)瞬时电压",
            "1.0.22.7.0.255": "B相(L2)瞬时电压",
            "1.0.23.7.0.255": "C相(L3)瞬时电压",
            "1.0.20.7.0.255": "平均电压",

            # 瞬时测量值 - 电流
            "1.0.31.7.0.255": "A相(L1)瞬时电流",
            "1.0.32.7.0.255": "B相(L2)瞬时电流",
            "1.0.33.7.0.255": "C相(L3)瞬时电流",
            "1.0.30.7.0.255": "中性线电流",

            # 瞬时测量值 - 功率
            "1.0.51.7.0.255": "A相(L1)瞬时有功功率",
            "1.0.52.7.0.255": "B相(L2)瞬时有功功率",
            "1.0.53.7.0.255": "C相(L3)瞬时有功功率",
            "1.0.50.7.0.255": "总有功功率",

            "1.0.61.7.0.255": "A相(L1)瞬时无功功率",
            "1.0.62.7.0.255": "B相(L2)瞬时无功功率",
            "1.0.63.7.0.255": "C相(L3)瞬时无功功率",
            "1.0.60.7.0.255": "总无功功率",

            "1.0.71.7.0.255": "A相(L1)视在功率",
            "1.0.72.7.0.255": "B相(L2)视在功率",
            "1.0.73.7.0.255": "C相(L3)视在功率",
            "1.0.70.7.0.255": "总视在功率",

            "1.0.81.7.0.255": "A相(L1)功率因数",
            "1.0.82.7.0.255": "B相(L2)功率因数",
            "1.0.83.7.0.255": "C相(L3)功率因数",
            "1.0.80.7.0.255": "总功率因数",

            # 频率
            "1.0.90.7.0.255": "电网频率",

            # 日/月累计
            "1.0.1.8.0.256": "正向有功电能日累计",
            "1.0.1.8.0.257": "正向有功电能月累计",

            # 时钟
            "0.0.1.0.0.255": "时钟/当前时间",
            "1.0.0.0.0.255": "有功电能基准值",

            # 电量日期
            "0.0.2.0.0.255": "抄表日期",
            "0.0.3.0.0.255": "最近掉电日期时间",

            # 谐波
            "1.0.111.7.0.255": "A相电压总谐波畸变率",
            "1.0.112.7.0.255": "B相电压总谐波畸变率",
            "1.0.113.7.0.255": "C相电压总谐波畸变率",
        }
        return obis_map.get(obis_str, obis_str)

    def _parse_dlms_value(self, data: bytes, table_data: list, base_offset: int, label: str = "    数据值") -> int:
        """
        解析DLMS数据值（A-XDR编码）
        返回消耗的字节数
        """
        if len(data) < 1:
            return 0

        type_tag = data[0]
        offset = 1

        type_names = {
            0x00: "Null", 0x01: "Array/Structure", 0x02: "Boolean", 0x03: "Bit-String",
            0x04: "Double-Long-Unsigned", 0x05: "Double-Long", 0x06: "Octet-String",
            0x09: "Visible-String", 0x0A: "UTF8-String", 0x0B: "BCD",
            0x0C: "Integer(16bit)", 0x0D: "Long(32bit)", 0x0F: "Long-Unsigned(16bit)",
            0x10: "Compact-Array", 0x11: "Long64-Unsigned", 0x12: "Long64",
            0x13: "Enum", 0x16: "Float32", 0x17: "Float64",
            0x18: "DateTime", 0x19: "Date", 0x1A: "Time", 0x1B: "Dont-Care",
        }
        type_name = type_names.get(type_tag, f"未知(0x{type_tag:02X})")

        # 定长类型
        fixed_lengths = {0x02: 1, 0x04: 4, 0x05: 4, 0x0C: 2, 0x0D: 4, 0x0F: 2,
                         0x11: 8, 0x12: 8, 0x13: 1, 0x16: 4, 0x17: 8, 0x18: 12, 0x19: 5, 0x1A: 4}

        if type_tag == 0x00:  # Null
            table_data.append((label, "-", "Null", type_name, base_offset, base_offset))
            return 1
        elif type_tag == 0x01:  # Array/Structure
            if len(data) > offset:
                elem_count = data[offset]
                offset += 1
                table_data.append((label, f"0x{type_tag:02X} ({elem_count})", f"{type_name}, 元素数={elem_count}",
                                  "复合数据", base_offset, base_offset + 1))
                # 逐个解析每个元素
                current_offset = offset
                for i in range(elem_count):
                    if current_offset >= len(data):
                        break
                    # 每个元素都是一个 DLMS 数据值，递归解析
                    elem_len = self._parse_dlms_value(data[current_offset:], table_data,
                                                    base_offset + current_offset,
                                                    f"    {label} [{i}]")
                    if elem_len <= 0:
                        break
                    current_offset += elem_len
                return current_offset
        elif type_tag == 0x06:  # Octet-String
            if len(data) > offset:
                str_len = data[offset]
                offset += 1
                if len(data) >= offset + str_len:
                    str_data = data[offset:offset + str_len]
                    # 检查是否是DateTime (12字节)
                    if str_len == 12:
                        try:
                            year = struct.unpack('>H', str_data[0:2])[0]
                            month = str_data[2]
                            day = str_data[3]
                            hour = str_data[4]
                            minute = str_data[5]
                            second = str_data[6]
                            dt_str = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
                            table_data.append((f"{label} (DateTime)", self._bytes_to_hex(str_data), dt_str,
                                              type_name, base_offset, base_offset + str_len))
                            return offset + str_len
                        except Exception:
                            pass
                    table_data.append((label, self._bytes_to_hex(str_data[:20]) + ("..." if str_len > 20 else ""),
                                      f"{str_len}字节", type_name, base_offset, base_offset + str_len))
                    return offset + str_len
        elif type_tag == 0x09:  # Visible-String
            if len(data) > offset:
                str_len = data[offset]
                offset += 1
                if len(data) >= offset + str_len:
                    str_data = data[offset:offset + str_len]
                    try:
                        str_value = str_data.decode('ascii', errors='replace')
                    except Exception:
                        str_value = self._bytes_to_hex(str_data)
                    table_data.append((label, self._bytes_to_hex(str_data), f'"{str_value}"',
                                      f"{type_name}({str_len}字节)", base_offset, base_offset + str_len))
                    return offset + str_len
        elif type_tag == 0x0A:  # UTF8-String
            if len(data) > offset:
                str_len = data[offset]
                offset += 1
                if len(data) >= offset + str_len:
                    str_data = data[offset:offset + str_len]
                    try:
                        str_value = str_data.decode('utf-8', errors='replace')
                    except Exception:
                        str_value = self._bytes_to_hex(str_data)
                    table_data.append((label, self._bytes_to_hex(str_data), f'"{str_value}"',
                                      f"{type_name}({str_len}字节)", base_offset, base_offset + str_len))
                    return offset + str_len
        elif type_tag == 0x03:  # Bit-String
            if len(data) > offset:
                bit_len = data[offset]
                offset += 1
                byte_len = (bit_len + 7) // 8  # 向上取整，计算需要多少字节存储
                if len(data) >= offset + byte_len:
                    bit_data = data[offset:offset + byte_len]
                    table_data.append((label, self._bytes_to_hex(bit_data),
                                      f"{bit_len} bits ({byte_len}字节)",
                                      type_name, base_offset, base_offset + byte_len))
                    # 递归解析后面的内容，每个bit之后可能紧跟着下一个DLMS数据项
                    return offset + byte_len
        elif type_tag in fixed_lengths:
            fl = fixed_lengths[type_tag]
            if len(data) >= offset + fl:
                value_data = data[offset:offset + fl]
                # 解析具体值
                if type_tag == 0x04:  # Double-Long-Unsigned
                    val = struct.unpack('>I', value_data)[0]
                    table_data.append((label, self._bytes_to_hex(value_data), str(val), type_name,
                                      base_offset, base_offset + fl - 1))
                elif type_tag == 0x0F:  # Long-Unsigned
                    val = struct.unpack('>H', value_data)[0]
                    table_data.append((label, self._bytes_to_hex(value_data), str(val), type_name,
                                      base_offset, base_offset + fl - 1))
                elif type_tag == 0x11:  # Long64-Unsigned
                    val = struct.unpack('>Q', value_data)[0]
                    table_data.append((label, self._bytes_to_hex(value_data), str(val), type_name,
                                      base_offset, base_offset + fl - 1))
                elif type_tag == 0x13:  # Enum
                    table_data.append((label, self._bytes_to_hex(value_data), str(value_data[0]), type_name,
                                      base_offset, base_offset))
                else:
                    table_data.append((label, self._bytes_to_hex(value_data), f"{fl}字节", type_name,
                                      base_offset, base_offset + fl - 1))
                return offset + fl

        # 兜底：显示原始数据
        table_data.append((label, self._bytes_to_hex(data[:20]) + ("..." if len(data) > 20 else ""),
                          f"{len(data)}字节", type_name, base_offset, base_offset + min(19, len(data) - 1)))
        return len(data)

    def _parse_apdu_content(self, data: bytes, table_data: list, offset: int,
                            apdu_type: int, base_offset: int = 0, direction: str = "unknown") -> int:
        """
        解析APDU具体内容

        参数:
            data: APDU类型字节之后的数据
            offset: 数据中的起始偏移
            apdu_type: APDU类型码
            base_offset: 在原始帧中的偏移
            direction: "request"(客户端→服务端) 或 "response"(服务端→客户端)

        返回:
            消耗的字节数
        """
        if len(data) <= offset:
            return 0

        remaining = data[offset:]
        local_offset = offset
        bo = base_offset  # 缩写

        # ======== Get-Request (0xC0) ========
        # 结构: Request-Type(1) + InvokeIdAndPriority(1) + Cosem-Attribute-Descriptor(9) + [Selective-Access]
        if apdu_type == 0xC0:
            if len(remaining) >= 1:
                req_type = remaining[0]
                type_name = self.GET_REQUEST_TYPES.get(req_type, f"未知(0x{req_type:02X})")
                table_data.append(("    请求类型", f"0x{req_type:02X}", type_name,
                                  "Get-Request类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    Invoke-Id-And-Priority", f"0x{invoke_byte:02X}",
                                  f"ID={inv['invoke_id']}, {inv['service_class']}, {inv['priority']}",
                                  "调用标识和优先级", bo + local_offset, bo + local_offset))
                local_offset += 1

                # Normal Get: Cosem-Attribute-Descriptor
                if req_type == 0x01 and len(remaining) >= 11:
                    consumed = self._parse_cosem_descriptor(remaining[2:], table_data, bo + local_offset)
                    local_offset += consumed

                    # 可能有 Selective-Access-Descriptor (0x00=无, 其他=有)
                    if local_offset < len(remaining):
                        sel_access = remaining[local_offset - 2] if local_offset - 2 >= 0 else 0
                        # 最后一个字节可能是 Selective Access 标记
                        remaining_after_desc = remaining[local_offset:]
                        if len(remaining_after_desc) > 0:
                            table_data.append(("    Selective-Access",
                                              self._bytes_to_hex(remaining_after_desc[:5]) + ("..." if len(remaining_after_desc) > 5 else ""),
                                              f"{len(remaining_after_desc)}字节", "选择性访问描述符(可选)",
                                              bo + local_offset, bo + min(local_offset + 4, len(remaining) - 1)))

                # Next-Data-Block: block-number(4字节)
                elif req_type == 0x02 and len(remaining) >= 6:
                    block_num = struct.unpack('>I', remaining[2:6])[0]
                    table_data.append(("    Block-Number", f"0x{block_num:08X}", str(block_num),
                                      "数据块序号", bo + local_offset, bo + local_offset + 3))

        # ======== Get-Response (0xC4) ========
        # 结构: Response-Type(1) + InvokeIdAndPriority(1) + 后续内容(取决于type)
        elif apdu_type == 0xC4:
            if len(remaining) >= 1:
                resp_type = remaining[0]
                type_name = self.GET_RESPONSE_TYPES.get(resp_type, f"未知(0x{resp_type:02X})")
                table_data.append(("    响应类型", f"0x{resp_type:02X}", type_name,
                                  "Get-Response类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    Invoke-Id-And-Priority", f"0x{invoke_byte:02X}",
                                  f"ID={inv['invoke_id']}, {inv['service_class']}, {inv['priority']}",
                                  "调用标识和优先级", bo + local_offset, bo + local_offset))
                local_offset += 1

                if resp_type == 0x01:
                    # Get-Response-Normal: Result(1) + [Data]
                    if len(remaining) >= 3:
                        result_tag = remaining[2]
                        if result_tag == 0x00:
                            # Data 成功
                            table_data.append(("    结果", "0x00", "成功(Data)",
                                              "Get-Data-Result", bo + local_offset, bo + local_offset))
                            local_offset += 1
                            # 解析返回数据
                            if len(remaining) > 3:
                                consumed_data = self._parse_dlms_value(remaining[3:], table_data, bo + local_offset, "    返回数据")
                                local_offset += consumed_data
                        elif result_tag == 0x01:
                            # Data-Access-Result 错误
                            if len(remaining) >= 4:
                                err_code = remaining[3]
                                err_name = self.DATA_ACCESS_RESULTS.get(err_code, f"未知(0x{err_code:02X})")
                                table_data.append(("    结果", f"0x{result_tag:02X}", f"DataAccessError: {err_name}",
                                                  "Get-Data-Result(错误)", bo + local_offset, bo + local_offset + 1))
                            else:
                                table_data.append(("    结果", "0x01", "DataAccessError",
                                                  "Get-Data-Result(错误)", bo + local_offset, bo + local_offset))

                elif resp_type == 0x02:
                    # Get-Response-With-Data-Block: block-control + payload
                    remaining_len = len(remaining) - 2
                    table_data.append(("    返回数据(分块)",
                                      self._bytes_to_hex(remaining[2:min(17, len(remaining))]) + ("..." if len(remaining) > 17 else ""),
                                      f"{remaining_len}字节", "分块传输数据",
                                      bo + local_offset, bo + local_offset + remaining_len - 1))
                    # 消耗掉所有剩余字节
                    local_offset += remaining_len
                else:
                    # 未知响应类型，消耗掉所有剩余字节，作为原始数据展示
                    remaining_len = len(remaining) - 2
                    if remaining_len > 0:
                        table_data.append(("    未知数据",
                                          self._bytes_to_hex(remaining[2:min(17, len(remaining))]) + ("..." if len(remaining) > 17 else ""),
                                          f"{remaining_len}字节", "未识别的Get-Response数据",
                                          bo + local_offset, bo + local_offset + remaining_len - 1))
                        local_offset += remaining_len

        # ======== Set-Request (0xC1) ========
        # 结构: Request-Type(1) + InvokeIdAndPriority(1) + Cosem-Attribute-Descriptor(9) + [Selective-Access] + Data
        elif apdu_type == 0xC1:
            if len(remaining) >= 1:
                req_type = remaining[0]
                type_name = self.SET_REQUEST_TYPES.get(req_type, f"未知(0x{req_type:02X})")
                table_data.append(("    请求类型", f"0x{req_type:02X}", type_name,
                                  "Set-Request类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    Invoke-Id-And-Priority", f"0x{invoke_byte:02X}",
                                  f"ID={inv['invoke_id']}, {inv['service_class']}, {inv['priority']}",
                                  "调用标识和优先级", bo + local_offset, bo + local_offset))
                local_offset += 1

                # Normal Set
                if req_type == 0x01 and len(remaining) >= 11:
                    consumed = self._parse_cosem_descriptor(remaining[2:], table_data, bo + local_offset)
                    local_offset += consumed

                    # Selective-Access (可选, 0x00=无)
                    if local_offset < len(remaining):
                        sel_byte = remaining[local_offset]
                        if sel_byte == 0x00:
                            table_data.append(("    Selective-Access", "0x00", "无",
                                              "无选择性访问", bo + local_offset, bo + local_offset))
                            local_offset += 1

                    # 写入数据值
                    if local_offset < len(remaining):
                        consumed_data = self._parse_dlms_value(remaining[local_offset:], table_data, bo + local_offset, "    写入数据")
                        local_offset += consumed_data

        # ======== Set-Response (0xC5) ========
        # 结构: Response-Type(1) + InvokeIdAndPriority(1) + 结果
        elif apdu_type == 0xC5:
            if len(remaining) >= 1:
                resp_type = remaining[0]
                type_name = self.SET_RESPONSE_TYPES.get(resp_type, f"未知(0x{resp_type:02X})")
                table_data.append(("    响应类型", f"0x{resp_type:02X}", type_name,
                                  "Set-Response类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    Invoke-Id-And-Priority", f"0x{invoke_byte:02X}",
                                  f"ID={inv['invoke_id']}, {inv['service_class']}, {inv['priority']}",
                                  "调用标识和优先级", bo + local_offset, bo + local_offset))
                local_offset += 1

                if resp_type == 0x01 and len(remaining) >= 3:
                    # Set-Response-Normal: result(1)
                    result = remaining[2]
                    result_name = self.DATA_ACCESS_RESULTS.get(result, f"未知(0x{result:02X})")
                    table_data.append(("    结果", f"0x{result:02X}", result_name,
                                      "写操作结果", bo + local_offset, bo + local_offset))
                    local_offset += 1
                    # 如果还有剩余数据，一并展示
                    if local_offset < len(remaining):
                        remaining_len = len(remaining) - local_offset
                        table_data.append(("    扩展数据",
                                          self._bytes_to_hex(remaining[local_offset:min(local_offset + 16, len(remaining))]) + ("..." if len(remaining) - local_offset > 16 else ""),
                                          f"{remaining_len}字节", "额外数据",
                                          bo + local_offset, bo + len(remaining) - 1))
                        local_offset += remaining_len
                else:
                    # 未知响应类型，消耗所有剩余字节
                    remaining_len = len(remaining) - 2
                    if remaining_len > 0:
                        table_data.append(("    剩余数据",
                                          self._bytes_to_hex(remaining[2:min(2 + 16, len(remaining))]) + ("..." if len(remaining) > 18 else ""),
                                          f"{remaining_len}字节", "未识别的Set-Response数据",
                                          bo + local_offset, bo + local_offset + remaining_len - 1))
                        local_offset += remaining_len

        # ======== Action-Request (0xC3) ========
        # 结构: Request-Type(1) + InvokeIdAndPriority(1) + Cosem-Method-Descriptor(9) + [HasParameter(1) + Data]
        elif apdu_type == 0xC3:
            if len(remaining) >= 1:
                req_type = remaining[0]
                type_name = self.ACTION_REQUEST_TYPES.get(req_type, f"未知(0x{req_type:02X})")
                table_data.append(("    请求类型", f"0x{req_type:02X}", type_name,
                                  "Action-Request类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    Invoke-Id-And-Priority", f"0x{invoke_byte:02X}",
                                  f"ID={inv['invoke_id']}, {inv['service_class']}, {inv['priority']}",
                                  "调用标识和优先级", bo + local_offset, bo + local_offset))
                local_offset += 1

                # Action-Normal: Cosem-Method-Descriptor (Class-ID + OBIS + Method-ID)
                if req_type == 0x01 and len(remaining) >= 11:
                    # Class-ID (2字节)
                    class_id = struct.unpack('>H', remaining[2:4])[0]
                    class_name = {
                        1: "Data", 3: "Register", 4: "Extended-Register",
                        7: "Profile-Generic", 8: "Clock", 9: "Script-Table",
                        17: "Association-Logical-Device", 70: "Pulse-Counter",
                        81: "Comms-Port-HDLC", 100: "Application-Association",
                        101: "Security-Setup", 111: "Disconnect-Control",
                    }.get(class_id, f"Class-{class_id}")

                    table_data.append(("    类ID (Class-ID)", f"0x{class_id:04X}", class_name,
                                      "COSEM对象类", bo + local_offset, bo + local_offset + 1))
                    local_offset += 2

                    # OBIS码 (6字节)
                    obis_bytes = remaining[4:10]
                    obis_str = ".".join(str(b) for b in obis_bytes)
                    obis_desc = self._get_obis_description(obis_bytes)
                    table_data.append(("    OBIS码", self._bytes_to_hex(obis_bytes), obis_str,
                                      f"对象标识: {obis_desc}", bo + local_offset, bo + local_offset + 5))
                    local_offset += 6

                    # Method-ID (1字节)
                    method_id = remaining[10]
                    table_data.append(("    方法ID (Method-ID)", f"0x{method_id:02X}", str(method_id),
                                      "操作方法编号", bo + local_offset, bo + local_offset))
                    local_offset += 1

                    # 可选参数: 0x00=无参数, 0x01=有参数后跟Data
                    if len(remaining) >= 12:
                        has_param = remaining[11]
                        if has_param == 0x01:
                            table_data.append(("    方法参数标记", "0x01", "有参数",
                                              "方法调用参数存在", bo + local_offset, bo + local_offset))
                            local_offset += 1
                            # 解析参数数据
                            if len(remaining) > 12:
                                consumed_data = self._parse_dlms_value(remaining[12:], table_data, bo + local_offset, "    方法参数")
                                local_offset += consumed_data
                        elif has_param == 0x00:
                            table_data.append(("    方法参数标记", "0x00", "无参数",
                                              "无方法调用参数", bo + local_offset, bo + local_offset))

        # ======== Action-Response (0xC7) ========
        # 结构: Response-Type(1) + InvokeIdAndPriority(1) + Action-Result(2) + [Return-Parameters]
        elif apdu_type == 0xC7:
            if len(remaining) >= 1:
                resp_type = remaining[0]
                type_name = self.ACTION_RESPONSE_TYPES.get(resp_type, f"未知(0x{resp_type:02X})")
                table_data.append(("    响应类型", f"0x{resp_type:02X}", type_name,
                                  "Action-Response类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    Invoke-Id-And-Priority", f"0x{invoke_byte:02X}",
                                  f"ID={inv['invoke_id']}, {inv['service_class']}, {inv['priority']}",
                                  "调用标识和优先级", bo + local_offset, bo + local_offset))
                local_offset += 1

                # Action-Response-Normal
                # 结构: 响应类型(1) + Invoke-Id-And-Priority(1) + Action-Result(1) + [Data-Access-Result(1)] + [return-data]
                # Action-Result 是 CHOICE，标签: 0=success, 1=data-access-error, ..., 12=type-unmatched(0x0C)
                if resp_type == 0x01 and len(remaining) >= 3:
                    result_tag = remaining[2]  # Action-Result CHOICE 标签

                    # 处理 Action-Result
                    if result_tag == 0x00:
                        # 00 = success
                        table_data.append(("    操作结果", "0x00", "成功",
                                          "Action-Result (success)", bo + local_offset + 2, bo + local_offset + 2))
                        local_offset_after_result = 3  # 已经用了 2+1=3 字节 (索引到3)

                        # success 之后可能有 return-data，可能带 0x00 标签
                        if len(remaining) > local_offset_after_result:
                            ret_tag = remaining[local_offset_after_result]
                            if ret_tag == 0x00:
                                # 带 0x00 标签的返回数据
                                local_offset_after_result += 1
                                if len(remaining) > local_offset_after_result:
                                    self._parse_dlms_value(remaining[local_offset_after_result:], table_data,
                                                          bo + local_offset + local_offset_after_result, "    返回数据")
                            elif ret_tag == 0x01:
                                # DataAccessError
                                local_offset_after_result += 1
                                if len(remaining) > local_offset_after_result:
                                    err_code = remaining[local_offset_after_result]
                                    err_name = self.DATA_ACCESS_RESULTS.get(err_code, f"未知(0x{err_code:02X})")
                                    table_data.append(("    数据结果", f"0x{err_code:02X}", err_name,
                                                      "Data-Access-Result", bo + local_offset + local_offset_after_result,
                                                      bo + local_offset + local_offset_after_result))
                            else:
                                # 没有标签，直接是返回数据
                                self._parse_dlms_value(remaining[local_offset_after_result:], table_data,
                                                      bo + local_offset + local_offset_after_result, "    返回数据")
                    else:
                        # 其他标签都是错误类型，比如 0x0C (12) = type-unmatched
                        # 结构: Action-Result(1B) + Data-Access-Result(1B) + result(1B)
                        result_name = self.ACTION_RESULTS.get(result_tag, f"type-unmatched({result_tag})")
                        table_data.append(("    Action-Result", f"0x{result_tag:02X}", result_name,
                                          "Action-Result CHOICE", bo + local_offset + 2, bo + local_offset + 2))

                        # 下一个字节是 Data-Access-Result 标签
                        if len(remaining) >= 4:
                            dar_tag = remaining[3]
                            # Data-Access-Result 后还有结果码
                            if len(remaining) >= 5:
                                dar_result = remaining[4]
                                dar_result_name = self.DATA_ACCESS_RESULTS.get(dar_result, f"未知(0x{dar_result:02X})")
                                table_data.append(("    Data-Access-Result", f"0x{dar_tag:02X}", dar_result_name,
                                                  "Data-Access-Result", bo + local_offset + 4, bo + local_offset + 4))
                            else:
                                table_data.append(("    Data-Access-Result", f"0x{dar_tag:02X}", "",
                                                  "Data-Access-Result", bo + local_offset + 3, bo + local_offset + 3))

        # ======== AARQ/AARE (0x60/0x61 或 0x01/0x02) ========
        elif apdu_type in (0x01, 0x02, 0x60, 0x61):
            # AARQ/AARE 使用BER编码，深度解析BER-TLV结构
            table_data.append(("    关联数据",
                              self._bytes_to_hex(remaining[:20]) + ("..." if len(remaining) > 20 else ""),
                              f"{len(remaining)}字节",
                              "关联请求/响应（BER编码）",
                              bo + local_offset, bo + min(local_offset + 19, len(remaining) - 1)))
            # 深度解析 BER-TLV，_parse_ber_tlv 会解析完所有剩余字节
            if len(remaining) >= 2:
                self._parse_ber_tlv(remaining, table_data, bo + local_offset)
                # BER-TLV 解析了所有剩余字节，local_offset 加上全部长度
                local_offset += len(remaining)

        # ======== 其他加密/未知类型 ========
        else:
            if len(remaining) > 0:
                table_data.append(("    APDU数据",
                                  self._bytes_to_hex(remaining[:20]) + ("..." if len(remaining) > 20 else ""),
                                  f"{len(remaining)}字节",
                                  f"APDU类型 0x{apdu_type:02X} 的数据",
                                  bo + local_offset, bo + min(local_offset + 19, len(remaining) - 1)))
                # 消耗了所有剩余字节
                local_offset += len(remaining)

        # 返回消耗的字节数
        return local_offset - offset

    @staticmethod
    def _bytes_to_hex(data: bytes) -> str:
        """将字节转换为十六进制字符串"""
        return ' '.join(f'{b:02X}' for b in data)

    def parse(self, frame_bytes: bytes) -> Dict[str, Any]:
        """
        解析HDLC帧为结构化字典
        
        返回: 解析结果字典
        """
        result = {
            "原始数据": self._bytes_to_hex(frame_bytes),
            "解析状态": "成功",
        }
        
        if len(frame_bytes) < 7:
            result["解析状态"] = "失败"
            result["错误信息"] = "帧长度不足（至少7字节）"
            return result
        
        offset = 0
        
        # 1. 起始标志
        if frame_bytes[0] != self.HDLC_FLAG:
            result["解析状态"] = "失败"
            result["错误信息"] = "起始标志错误"
            return result
        
        result["起始标志"] = {
            "原始值": f"0x{frame_bytes[0]:02X}",
            "解析值": "0x7E",
            "说明": "HDLC帧起始标志"
        }
        offset += 1
        
        # 2. 格式域
        format_bytes = frame_bytes[offset:offset + 2]
        format_field = struct.unpack('>H', format_bytes)[0]
        format_type = (format_field >> 12) & 0x0F
        segmentation_bit = (format_field >> 11) & 0x01
        frame_length = format_field & 0x07FF
        
        result["格式域"] = {
            "原始值": f"0x{format_field:04X}",
            "格式类型": f"0x{format_type:X} (Type 3)" if format_type == 0x0A else f"0x{format_type:X}",
            "分段位": segmentation_bit,
            "帧长度": frame_length,
            "说明": "HDLC Type 3格式"
        }
        offset += 2
        
        # 3. 目的地址
        dest_addr, dest_len = self._parse_address_field(frame_bytes, offset)
        result["目的地址域"] = {
            "原始值": self._bytes_to_hex(frame_bytes[offset:offset + dest_len]),
            "地址值": f"0x{dest_addr:X}",
            "地址长度": f"{dest_len}字节",
            "说明": self._format_address_description(dest_addr, dest_len, "目的")
        }
        offset += dest_len
        
        # 4. 源地址
        src_addr, src_len = self._parse_address_field(frame_bytes, offset)
        result["源地址域"] = {
            "原始值": self._bytes_to_hex(frame_bytes[offset:offset + src_len]),
            "地址值": f"0x{src_addr:X}",
            "地址长度": f"{src_len}字节",
            "说明": self._format_address_description(src_addr, src_len, "源")
        }
        offset += src_len
        
        # 5. 控制域
        # 判断帧方向
        if dest_len > src_len:
            parse_direction = "client_to_server"
        elif src_len > dest_len:
            parse_direction = "server_to_client"
        else:
            parse_direction = "unknown"

        control_byte = frame_bytes[offset]
        ctrl_type, ctrl_desc, ctrl_details = self._parse_control_field(control_byte, parse_direction)
        result["控制域"] = {
            "原始值": f"0x{control_byte:02X}",
            "帧类型": ctrl_type,
            "说明": ctrl_desc,
            **ctrl_details
        }
        offset += 1
        
        # 判断是否有信息域
        has_info = ctrl_type in ['I帧 (信息帧)', 'UI帧 (无编号信息)', 'SNRM帧', 'UA帧', 'DM帧', 'FRMR帧', 'DISC帧']
        
        # 6. HCS/FCS
        if offset + 1 < len(frame_bytes):
            hcs_bytes = frame_bytes[offset:offset + 2]
            hcs_value = struct.unpack('>H', hcs_bytes)[0]
            result["HCS校验"] = {
                "原始值": f"0x{hcs_value:04X}",
                "说明": "头部/帧校验序列"
            }
            offset += 2
        
        # 7. 信息域
        if has_info and offset < len(frame_bytes) - 3:
            info_end = len(frame_bytes) - 3  # 减去FCS和结束标志
            info_data = frame_bytes[offset:info_end]
            result["信息域"] = {
                "原始值": self._bytes_to_hex(info_data),
                "长度": len(info_data),
                "说明": "携带的上层数据（可能包含DLMS APDU）"
            }
            offset = info_end
        
        # 8. FCS（如果还未解析）
        if offset + 1 < len(frame_bytes):
            fcs_bytes = frame_bytes[offset:offset + 2]
            fcs_value = struct.unpack('>H', fcs_bytes)[0]
            result["FCS校验"] = {
                "原始值": f"0x{fcs_value:04X}",
                "说明": "帧校验序列"
            }
            offset += 2
        
        # 9. 结束标志
        if offset < len(frame_bytes):
            result["结束标志"] = {
                "原始值": f"0x{frame_bytes[offset]:02X}",
                "解析值": "0x7E" if frame_bytes[offset] == self.HDLC_FLAG else "错误",
                "说明": "HDLC帧结束标志"
            }
        
        return result

    def parse_wrapper_to_table(self, wrapper_bytes: bytes) -> list:
        """
        直接解析裸Wrapper报文（不含外层HDLC），从Wrapper头部开始解析
        格式: Wrapper-header(8字节) + DLMS-APDU
        """
        table_data = []
        offset = 0
        base_offset = 0

        if len(wrapper_bytes) < 8:
            table_data.append(("错误", "-", "-", "Wrapper报文长度不足（至少需要8字节）", 0, len(wrapper_bytes) - 1))
            return table_data

        # 解析 Wrapper 头部
        version = (wrapper_bytes[offset] << 8) | wrapper_bytes[offset + 1]
        src_port = (wrapper_bytes[offset + 2] << 8) | wrapper_bytes[offset + 3]
        dst_port = (wrapper_bytes[offset + 4] << 8) | wrapper_bytes[offset + 5]
        apdu_len = (wrapper_bytes[offset + 6] << 8) | wrapper_bytes[offset + 7]

        table_data.append(("Wrapper版本", f"{wrapper_bytes[offset]:02X} {wrapper_bytes[offset + 1]:02X}",
                          str(version), "Wrapper协议版本",
                          base_offset + offset, base_offset + offset + 1))
        table_data.append(("Wrapper源端口", f"{wrapper_bytes[offset + 2]:02X} {wrapper_bytes[offset + 3]:02X}",
                          f"0x{src_port:04X} ({src_port})", "源端口号",
                          base_offset + offset + 2, base_offset + offset + 3))
        table_data.append(("Wrapper目的端口", f"{wrapper_bytes[offset + 4]:02X} {wrapper_bytes[offset + 5]:02X}",
                          f"0x{dst_port:04X} ({dst_port})", "目的端口号",
                          base_offset + offset + 4, base_offset + offset + 5))
        table_data.append(("Wrapper长度", f"{wrapper_bytes[offset + 6]:02X} {wrapper_bytes[offset + 7]:02X}",
                          f"{apdu_len} 字节", "DLMS-APDU数据长度",
                          base_offset + offset + 6, base_offset + offset + 7))
        offset += 8
        table_data.append(("Wrapper数据", "", "", "Wrapper头部结束，以下是真正的DLMS-APDU",
                          base_offset + offset, base_offset + offset))

        # 解析 DLMS-APDU，从offset开始，base_offset已经是0
        if offset < len(wrapper_bytes):
            apdu_data = wrapper_bytes[offset:]
            boffset = base_offset + offset
            if len(apdu_data) > 0:
                apdu_byte = apdu_data[0]
                if apdu_byte in self.APDU_TYPES:
                    # 添加整个APDU父行（覆盖完整范围，方便双击深度解析）
                    original_offset = offset
                    apdu_name = self.APDU_TYPES[apdu_byte]
                    offset += 1
                    start_len = len(table_data)
                    # 解析APDU内容，获取消耗字节数
                    consumed = self._parse_apdu_content(apdu_data[1:], table_data, 0, apdu_byte, boffset + 1)
                    offset += consumed
                    # 计算完整范围
                    apdu_end = base_offset + (offset - 1)
                    apdu_len = offset - original_offset
                    # 插入父行，所有子项会自动在下面缩进
                    # 原始值显示APDU类型字节十六进制，解析值显示名称+总长度
                    table_data.insert(start_len, ("  DLMS APDU", f"0x{apdu_byte:02X}",
                                                f"{apdu_name} (整个{apdu_len}字节)",
                                                "完整DLMS应用层协议数据单元（双击可深度解析）",
                                                boffset + original_offset, apdu_end))
                    # 添加APDU类型行作为子项（缩进一级）
                    table_data.insert(start_len + 1, ("    DLMS APDU类型", f"0x{apdu_byte:02X}", apdu_name,
                                                    "DLMS应用层协议数据单元类型",
                                                    boffset, boffset))
                else:
                    # BER-TLV 编码 - 添加整个APDU父行
                    if self._looks_like_ber_tlv(apdu_data):
                        original_offset = offset
                        total_len = len(apdu_data)
                        start_len = len(table_data)
                        # 递归解析所有子项
                        self._parse_ber_tlv(apdu_data, table_data, boffset)
                        apdu_end = boffset + (original_offset + total_len - 1)
                        # 插入父节点
                        first_byte = apdu_data[0]
                        table_data.insert(start_len, ("  DLMS APDU (BER-TLV)", f"0x{first_byte:02X}",
                                                    f"BER-TLV编码 (整个{total_len}字节)",
                                                    "完整DLMS APDU（双击可深度解析）",
                                                    boffset + original_offset, apdu_end))
                    else:
                        table_data.append(("  DLMS数据", self._bytes_to_hex(apdu_data[:20]) + ("..." if len(apdu_data) > 20 else ""),
                                          f"{len(apdu_data)}字节", "未识别的DLMS APDU类型",
                                          boffset, min(boffset + len(apdu_data) - 1, boffset + 19)))

        return table_data

    def parse_apdu_to_table(self, apdu_bytes: bytes) -> list:
        """
        直接解析裸DLMS-APDU报文（不含外层HDLC，不含Wrapper），从APDU开始解析
        """
        table_data = []
        base_offset = 0
        if len(apdu_bytes) < 1:
            table_data.append(("错误", "-", "-", "APDU报文为空", 0, 0))
            return table_data

        apdu_byte = apdu_bytes[0]
        if apdu_byte in self.APDU_TYPES:
            apdu_name = self.APDU_TYPES[apdu_byte]
            table_data.append(("DLMS APDU类型", f"0x{apdu_byte:02X}", apdu_name,
                              "DLMS应用层协议数据单元",
                              base_offset, base_offset))
            # 解析APDU内容
            self._parse_apdu_content(apdu_bytes[1:], table_data, 0, apdu_byte, base_offset + 1)
        else:
            # BER-TLV 编码
            if self._looks_like_ber_tlv(apdu_bytes):
                table_data.append(("DLMS数据 (BER-TLV)", self._bytes_to_hex(apdu_bytes[:20]) + ("..." if len(apdu_bytes) > 20 else ""),
                                  f"{len(apdu_bytes)}字节", "BER-TLV编码的DLMS数据",
                                  base_offset, min(base_offset + len(apdu_bytes) - 1, base_offset + 19)))
                self._parse_ber_tlv(apdu_bytes, table_data, base_offset)
            else:
                table_data.append(("DLMS数据", self._bytes_to_hex(apdu_bytes[:20]) + ("..." if len(apdu_bytes) > 20 else ""),
                                  f"{len(apdu_bytes)}字节", "未识别的DLMS APDU类型",
                                  base_offset, min(base_offset + len(apdu_bytes) - 1, base_offset + 19)))

        return table_data


if __name__ == "__main__":
    # 测试HDLC解析器
    parser = HDLCParser()
    
    # 示例HDLC帧（需要根据实际协议构造）
    # 格式: 7E + 格式域(2) + 目的地址(1) + 源地址(1) + 控制域(1) + HCS(2) + 信息域(可变) + FCS(2) + 7E
    
    # 简单测试帧 - SNRM命令
    test_frame = bytes([
        0x7E,  # 起始标志
        0xA0, 0x07,  # 格式域: Type=0xA, S=0, Length=7
        0x01,  # 目的地址: 0x01 (客户端管理进程)
        0x01,  # 源地址
        0x93,  # 控制域: SNRM, P=1
        0x00, 0x00,  # HCS (需要计算)
        0x00, 0x00,  # FCS (需要计算)
        0x7E,  # 结束标志
    ])
    
    print("=== HDLC帧解析测试 ===")
    table = parser.parse_to_table(test_frame)
    for row in table:
        print(f"{row[0]:20s} | {row[1]:15s} | {row[2]:30s} | {row[3]}")
    
    print("\n=== 结构化解析 ===")
    result = parser.parse(test_frame)
    for key, value in result.items():
        if isinstance(value, dict):
            print(f"\n{key}:")
            for k, v in value.items():
                print(f"  {k}: {v}")
        else:
            print(f"{key}: {value}")
