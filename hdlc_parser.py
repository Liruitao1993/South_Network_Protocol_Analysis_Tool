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
        'I': "信息帧 (Information)",
        # RR帧：bit0=1, bit1=0, bit3=0
        'RR': "接收就绪 (Receive Ready)",
        # RNR帧：bit0=1, bit1=0, bit3=1
        'RNR': "接收未就绪 (Receive Not Ready)",
        # SNRM帧：bit0=1, bit1=1, bit2=0, bit3=0
        'SNRM': "设置正常响应模式 (Set Normal Response Mode)",
        # DISC帧：bit0=1, bit1=1, bit2=1, bit3=0
        'DISC': "断开连接 (Disconnect)",
        # UA帧：bit0=1, bit1=1, bit2=1, bit3=0 (bit6=1)
        'UA': "无编号确认 (Unnumbered Acknowledgement)",
        # DM帧：bit0=1, bit1=1, bit2=1, bit3=1
        'DM': "断开模式 (Disconnected Mode)",
        # FRMR帧：bit0=1, bit1=1, bit2=1, bit3=0 (bit5=1)
        'FRMR': "帧拒绝 (Frame Reject)",
        # UI帧：bit0=1, bit1=1, bit2=0, bit3=0 (bit3=0表示UI)
        'UI': "无编号信息 (Unnumbered Information)",
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
        
        control_byte = frame_bytes[offset]
        ctrl_type, ctrl_desc, ctrl_details = self._parse_control_field(control_byte)
        
        table_data.append(("控制域", f"0x{control_byte:02X}", ctrl_type, ctrl_desc, offset, offset))
        
        # 控制域子字段
        if ctrl_details:
            for key, val in ctrl_details.items():
                table_data.append((f"  {key}", "-", val, "", offset, offset))
        
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
            
            # 尝试解析DLMS数据
            if len(info_data) > 0:
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
        注意：地址值需要移除LSB扩展位后组合，字节按传输顺序（大端序）
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
            
            # 按传输顺序组合（第一个字节是高位）
            address |= (address_value << shift)
            shift += 7
            
            # LSB=1表示这是最后一个地址字节
            if extension_bit == 0x01:
                break
            
            # 安全检查：最多4字节地址
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

    def _parse_control_field(self, control_byte: int) -> Tuple[str, str, Dict[str, str]]:
        """
        解析控制域
        
        返回: (帧类型名称, 详细描述, 子字段字典)
        """
        details = {}
        
        # 判断帧类型
        # I帧：bit0=0
        if (control_byte & 0x01) == 0:
            # I帧格式: N(R) P/F N(S) 0
            n_r = (control_byte >> 5) & 0x07  # 接收序列号 N(R)
            p_f = (control_byte >> 4) & 0x01  # P/F位
            n_s = (control_byte >> 1) & 0x07  # 发送序列号 N(S)
            
            details = {
                "N(R)接收序号": str(n_r),
                "P/F位": "P(查询)" if p_f else "F(最终)",
                "N(S)发送序号": str(n_s),
            }
            return "I帧 (信息帧)", f"信息传输帧, N(S)={n_s}, N(R)={n_r}", details
        
        # 检查其他帧类型（bit0=1）
        # UI帧: 0 0 0 P/F 0 0 1 1 = 0x03 (P/F=0) 或 0x0B (P/F=1)
        if (control_byte & 0xEF) == 0x03:  # 屏蔽bit4 (P/F位)
            p_f = (control_byte >> 3) & 0x01
            details = {
                "P/F位": "P(查询)" if p_f else "F(最终)",
            }
            return "UI帧 (无编号信息)", f"无编号信息传输, P/F={'P' if p_f else 'F'}", details
        
        # SNRM帧: 1 0 0 P 0 0 1 1 = 0x83 (P=0) 或 0x93 (P=1)
        if (control_byte & 0xEF) == 0x83:  # 屏蔽bit4 (P位)
            p = (control_byte >> 4) & 0x01
            details = {
                "P位(查询)": "是" if p else "否",
            }
            return "SNRM帧", f"设置正常响应模式, P={'是' if p else '否'}", details
        
        # DISC帧: 010 P 0011 = 0x43 或 0x53 (bit7=0, bit6=1, bit5=0, bit4=P, bit3-0=0011)
        if (control_byte & 0x0F) == 0x03 and (control_byte & 0xE0) in [0x40, 0x50]:
            p = (control_byte >> 4) & 0x01
            details = {
                "P位(查询)": "是" if p else "否",
            }
            return "DISC帧", f"断开连接, P={'是' if p else '否'}", details
        
        # UA帧: 011 F 0011 = 0x63 或 0x73 (bit7=0, bit6=1, bit5=1, bit4=F, bit3-0=0011)
        if (control_byte & 0x0F) == 0x03 and (control_byte & 0xE0) in [0x60, 0x70]:
            f = (control_byte >> 4) & 0x01
            details = {
                "F位(最终)": "是" if f else "否",
            }
            return "UA帧", f"无编号确认, F={'是' if f else '否'}", details
        
        # DM帧: 000 F 1111 = 0x0F 或 0x1F (bit7-4=0000/0001, bit3-0=1111)
        if (control_byte & 0x0F) == 0x0F and (control_byte & 0xE0) in [0x00, 0x10]:
            f = (control_byte >> 4) & 0x01
            details = {
                "F位(最终)": "是" if f else "否",
            }
            return "DM帧", f"断开模式, F={'是' if f else '否'}", details
        
        # FRMR帧: 100 F 0111 = 0x87 或 0x97 (bit7=1, bit6-5=00, bit4=F, bit3-0=0111)
        if (control_byte & 0x0F) == 0x07 and (control_byte & 0xE0) in [0x80, 0x90]:
            f = (control_byte >> 4) & 0x01
            details = {
                "F位(最终)": "是" if f else "否",
            }
            return "FRMR帧", f"帧拒绝, F={'是' if f else '否'}", details
        
        # RR帧: N(R) P/F 0001 (bit7-5=N(R), bit4=P/F, bit3-0=0001)
        if (control_byte & 0x0F) == 0x01:
            n_r = (control_byte >> 5) & 0x07
            p_f = (control_byte >> 4) & 0x01
            details = {
                "N(R)接收序号": str(n_r),
                "P/F位": "P(查询)" if p_f else "F(最终)",
            }
            return "RR帧 (接收就绪)", f"接收就绪, N(R)={n_r}", details
        
        # RNR帧: N(R) P/F 0101 (bit7-5=N(R), bit4=P/F, bit3-0=0101)
        if (control_byte & 0x0F) == 0x05:
            n_r = (control_byte >> 5) & 0x07
            p_f = (control_byte >> 4) & 0x01
            details = {
                "N(R)接收序号": str(n_r),
                "P/F位": "P(查询)" if p_f else "F(最终)",
            }
            return "RNR帧 (接收未就绪)", f"接收未就绪(忙), N(R)={n_r}", details
        
        # 未识别类型
        return f"未知帧(0x{control_byte:02X})", "未识别的控制域类型", {}

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

    def _parse_dlms_data(self, data: bytes, table_data: list, base_offset: int):
        """
        尝试解析信息域中的DLMS数据
        支持两种格式：
        1. 带LLC地址域：DSAP(1) + SSAP(1) + Control(1) + DLMS APDU
        2. 直接DLMS APDU
        """
        if len(data) < 2:
            return

        offset = 0
        
        # 检查是否包含LLC子层地址域（DSAP + SSAP + Control）
        # LLC格式: DSAP(1字节) + SSAP(1字节) + Control(1字节) + DLMS APDU
        # DSAP和SSAP通常是成对出现的地址，如 0xE6/0xE7, 0xE8/0xE9等
        has_llc = False
        if len(data) >= 3:
            dsap = data[0]
            ssap = data[1]
            llc_ctrl = data[2]
            
            # LLC地址可能使用扩展地址格式（LSB=1表示单个字节地址）
            # 或者普通地址格式（LSB=0表示还有扩展，但实际只使用1字节）
            # 常见LLC地址范围：0xE0-0xFF（高地址范围通常用于特殊服务）
            # 典型LLC地址对：0xE6/0xE7（DLMS常用）
            if dsap >= 0xE0 and ssap >= 0xE0:
                # 这很可能是LLC地址域
                has_llc = True
                dsap_value = (dsap >> 1) if (dsap & 0x01) else dsap
                ssap_value = (ssap >> 1) if (ssap & 0x01) else ssap
                
                table_data.append(("  LLC DSAP", f"0x{dsap:02X}", 
                                  f"0x{dsap_value:02X}", "目的服务接入点（LLC地址）",
                                  base_offset + offset, base_offset + offset))
                offset += 1
                
                table_data.append(("  LLC SSAP", f"0x{ssap:02X}", 
                                  f"0x{ssap_value:02X}", "源服务接入点（LLC地址）",
                                  base_offset + offset, base_offset + offset))
                offset += 1
                
                # LLC控制字段（服务质量）
                table_data.append(("  LLC控制", f"0x{llc_ctrl:02X}", 
                                  f"服务质量=0x{llc_ctrl:02X}", "LLC质量控制字段",
                                  base_offset + offset, base_offset + offset))
                offset += 1
        
        # 现在解析DLMS APDU
        if offset >= len(data):
            return
        
        apdu_start = offset
        apdu_byte = data[offset]
        
        # DLMS APDU类型映射
        apdu_types = {
            0x01: "AARQ (关联请求)",
            0x02: "AARE (关联响应)",
            0x03: "RLRQ (释放请求)",
            0x04: "RLRE (释放响应)",
            0xC0: "Get-Request (读请求)",
            0xC1: "Set-Request (写请求)",
            0xC2: "Action-Request (操作请求)",
            0xC3: "Exception-Response (异常响应)",
            0xC4: "Get-Response (读响应)",
            0xC5: "Set-Response (写响应)",
            0xC6: "Action-Response (操作响应)",
            0xC7: "Confirmed-Service-Error (确认服务错误)",
            0xC8: "General-Block-Transfer (通用块传输)",
        }
        
        # 检查是否是标准APDU类型
        if apdu_byte in apdu_types:
            apdu_name = apdu_types[apdu_byte]
            table_data.append(("  DLMS APDU类型", f"0x{apdu_byte:02X}", apdu_name,
                              "DLMS应用层协议数据单元", 
                              base_offset + apdu_start, base_offset + apdu_start))
            offset += 1
            
            # 根据APDU类型解析具体内容
            # 传递切片后的数据（从APDU内容开始）和修正后的base_offset
            self._parse_apdu_content(data[offset:], table_data, 0, apdu_byte, base_offset + offset)
        else:
            # 检查是否是长格式DLMS（控制字段0x00或0x01）
            if apdu_byte in [0x00, 0x01]:
                format_type = "长格式" if apdu_byte == 0x00 else "短格式"
                table_data.append(("  DLMS控制字段", f"0x{apdu_byte:02X}", format_type,
                                  "DLMS帧格式", 
                                  base_offset + offset, base_offset + offset))
                offset += 1
                
                # 长格式包含目标地址(4字节)和源地址(1字节)
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
                
                # 继续解析APDU
                if len(data) > offset and data[offset] in apdu_types:
                    apdu_byte2 = data[offset]
                    table_data.append(("    APDU类型", f"0x{apdu_byte2:02X}", 
                                      apdu_types[apdu_byte2], "",
                                      base_offset + offset, base_offset + offset))
                    offset += 1
                    self._parse_apdu_content(data, table_data, base_offset + offset, apdu_byte2)
            else:
                # 无法识别的APDU类型，可能是BER-TLV编码或专有格式
                # 尝试BER-TLV解析
                if self._looks_like_ber_tlv(data[offset:]):
                    table_data.append(("  DLMS数据 (BER-TLV)", self._bytes_to_hex(data[offset:offset+20]) + ("..." if len(data) > offset + 20 else ""),
                                      f"{len(data) - offset}字节", "BER-TLV编码的DLMS数据",
                                      base_offset + offset, min(base_offset + len(data) - 1, base_offset + offset + 19)))
                    # 解析BER-TLV结构
                    self._parse_ber_tlv(data[offset:], table_data, base_offset + offset)
                else:
                    table_data.append(("  DLMS数据", self._bytes_to_hex(data[offset:offset+20]) + ("..." if len(data) > offset + 20 else ""),
                                      f"{len(data) - offset}字节", "未识别的DLMS APDU类型",
                                      base_offset + offset, min(base_offset + len(data) - 1, base_offset + offset + 19)))
    
    def _looks_like_ber_tlv(self, data: bytes) -> bool:
        """检查数据是否像BER-TLV编码"""
        if len(data) < 2:
            return False
        # BER-TLV特征：
        # 0x1F表示高标签号（后续字节为标签扩展）
        # 0x60-0x7F是APPLICATION标签（如0x61=AARQ, 0x62=AARE）
        # 0x80-0x9F是Context-Specific标签（如0x81, 0x80等）
        # 0xA0-0xBF是Context-Specific标签
        tag = data[0]
        if tag == 0x1F:
            return True  # 高标签号
        if 0x60 <= tag <= 0x7F:
            return True  # APPLICATION标签
        if 0x80 <= tag <= 0x9F:
            return True  # Context-Specific标签 (Class 2)
        if 0xA0 <= tag <= 0xBF:
            return True  # Context-Specific标签
        return False
    
    def _parse_ber_tlv(self, data: bytes, table_data: list, base_offset: int):
        """解析BER-TLV编码的数据"""
        if len(data) < 2:
            return
        
        offset = 0
        local_offset = base_offset
        
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
            tag_desc = f"Context-Specific [{ctx_num}]"
        else:
            tag_desc = f"标签 0x{tag:02X}"
        
        table_data.append(("    BER标签", f"0x{tag:02X}" + (f" 0x{tag_number:02X}" if tag == 0x1F else ""), 
                          tag_desc, "BER-TLV标签", local_offset, local_offset))
        offset += 1
        local_offset += 1
        
        # 解析长度
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
                if offset + num_length_bytes <= len(data):
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
            if offset < len(data):
                value_data = data[offset:offset + min(tlv_length, len(data) - offset)]
                table_data.append(("    BER值", self._bytes_to_hex(value_data[:20]) + ("..." if len(value_data) > 20 else ""),
                                  f"{len(value_data)}字节", "TLV值数据", local_offset, local_offset + min(len(value_data) - 1, 19)))
                
                # 尝试递归解析嵌套的TLV结构
                if len(value_data) > 2:
                    self._parse_ber_tlv(value_data, table_data, local_offset)
    
    def _parse_apdu_content(self, data: bytes, table_data: list, offset: int, apdu_type: int, base_offset: int = 0):
        """解析APDU具体内容"""
        if len(data) <= offset:
            return
        
        remaining = data[offset:]
        local_offset = offset
        
        if apdu_type == 0xC0:  # Get-Request
            if len(remaining) >= 1:
                invoke_id = remaining[0]
                table_data.append(("    调用ID", f"0x{invoke_id:02X}", str(invoke_id), 
                                  "请求标识符", base_offset + local_offset, base_offset + local_offset))
                local_offset += 1
                
                if len(remaining) >= 2:
                    selector = remaining[1]
                    selector_map = {0x01: "变量", 0x02: "变量组", 0x03: "属性描述符"}
                    selector_name = selector_map.get(selector, f"未知(0x{selector:02X})")
                    table_data.append(("    选择符", f"0x{selector:02X}", selector_name, 
                                      "请求类型", base_offset + local_offset, base_offset + local_offset))
                    local_offset += 1
                    
                    # OBIS码（6字节）
                    if len(remaining) >= 8:
                        obis = remaining[2:8]
                        obis_str = ".".join(str(b) for b in obis)
                        table_data.append(("    OBIS码", self._bytes_to_hex(obis), obis_str, 
                                          "对象标识系统码", base_offset + local_offset, base_offset + local_offset + 5))
                        local_offset += 6
                        
                        # 属性索引
                        if len(remaining) >= 9:
                            attr_idx = remaining[8]
                            table_data.append(("    属性索引", f"0x{attr_idx:02X}", str(attr_idx), 
                                              "对象属性", base_offset + local_offset, base_offset + local_offset))
                            local_offset += 1
                            
                            # 可能有数据值（对于Set-Request）
                            if len(remaining) >= 10:
                                value_data = remaining[9:]
                                table_data.append(("    请求数据", 
                                                  self._bytes_to_hex(value_data[:10]) + ("..." if len(value_data) > 10 else ""),
                                                  f"{len(value_data)}字节", "请求参数值",
                                                  base_offset + local_offset, base_offset + min(local_offset + 9, len(remaining) - 1)))
        
        elif apdu_type == 0xC4:  # Get-Response
            if len(remaining) >= 1:
                invoke_id = remaining[0]
                table_data.append(("    调用ID", f"0x{invoke_id:02X}", str(invoke_id), 
                                  "响应标识符", base_offset + local_offset, base_offset + local_offset))
                local_offset += 1
                
                if len(remaining) >= 2:
                    result = remaining[1]
                    result_map = {
                        0x00: "成功", 
                        0x01: "硬件故障", 
                        0x02: "临时失败",
                        0x03: "读写对象未定义",
                        0x09: "对象未定义",
                        0x0B: "对象访问被拒绝",
                        0x0D: "对象未激活"
                    }
                    result_name = result_map.get(result, f"未知(0x{result:02X})")
                    table_data.append(("    结果", f"0x{result:02X}", result_name, 
                                      "请求执行结果", base_offset + local_offset, base_offset + local_offset))
                    local_offset += 1
                    
                    # 如果成功，包含返回数据
                    if result == 0x00 and len(remaining) >= 3:
                        # 数据类型
                        data_type = remaining[2]
                        type_names = {
                            0x00: "Null", 0x01: "Array", 0x02: "Boolean",
                            0x03: "Bit-String", 0x04: "Double-Long-Unsigned",
                            0x05: "Double-Long", 0x06: "Octet-String",
                            0x09: "Visible-String", 0x0A: "UTF8-String",
                            0x0B: "BCD", 0x0C: "Integer", 0x0D: "Long",
                            0x0F: "Long-Unsigned", 0x10: "Compact-Array",
                            0x11: "Long64-Unsigned", 0x12: "Long64",
                            0x13: "Enum", 0x16: "Float32", 0x17: "Float64",
                            0x18: "DateTime", 0x19: "Date", 0x1A: "Time"
                        }
                        type_name = type_names.get(data_type, f"未知(0x{data_type:02X})")
                        table_data.append(("    数据类型", f"0x{data_type:02X}", type_name,
                                          "DLMS数据类型", base_offset + local_offset, base_offset + local_offset))
                        local_offset += 1
                        
                        # 数据值
                        value_data = remaining[3:]
                        if len(value_data) > 0:
                            table_data.append(("    返回数据",
                                              self._bytes_to_hex(value_data[:15]) + ("..." if len(value_data) > 15 else ""),
                                              f"{len(value_data)}字节", "响应数据值",
                                              base_offset + local_offset, base_offset + min(local_offset + 14, len(remaining) - 1)))
        
        elif apdu_type == 0xC1:  # Set-Request
            if len(remaining) >= 1:
                invoke_id = remaining[0]
                table_data.append(("    调用ID", f"0x{invoke_id:02X}", str(invoke_id), "",
                                  base_offset + local_offset, base_offset + local_offset))
                local_offset += 1
                
                if len(remaining) >= 7:
                    # OBIS码
                    obis = remaining[1:7]
                    obis_str = ".".join(str(b) for b in obis)
                    table_data.append(("    OBIS码", self._bytes_to_hex(obis), obis_str,
                                      "对象标识", base_offset + local_offset, base_offset + local_offset + 5))
                    local_offset += 6
                    
                    if len(remaining) >= 8:
                        attr_idx = remaining[7]
                        table_data.append(("    属性索引", f"0x{attr_idx:02X}", str(attr_idx), "",
                                          base_offset + local_offset, base_offset + local_offset))
                        local_offset += 1
                        
                        # 数据值
                        if len(remaining) >= 9:
                            value_data = remaining[8:]
                            table_data.append(("    写入数据",
                                              self._bytes_to_hex(value_data[:10]) + ("..." if len(value_data) > 10 else ""),
                                              f"{len(value_data)}字节", "Set请求数据",
                                              base_offset + local_offset, base_offset + min(local_offset + 9, len(remaining) - 1)))
        
        elif apdu_type == 0xC2:  # Action-Request (操作请求)
            # Action-Request-Normal 结构:
            # Tag(1) + ActionType(1) + InvokeId(1) + ClassID(2) + OBIS(6) + MethodID(1) + [HasData(1) + Data]
            # 注意：dlms-cosem 库中 ActionRequestNormal.TAG=195(0xC3)，但标准中常用 0xC2。
            # 这里按 0xC2 为 Action-Request-Normal 进行解析。
            
            if len(remaining) >= 1:
                action_type = remaining[0]
                type_map = {0: "Normal (普通)", 1: "With-First-Block", 2: "With-List", 3: "With-List-And-First-Block"}
                type_name = type_map.get(action_type, f"未知({action_type})")
                table_data.append(("    请求类型 (Action-Type)", f"0x{action_type:02X}", type_name,
                                  "Action-Request 类型", base_offset + local_offset, base_offset + local_offset))
                local_offset += 1
                
                if action_type == 0:  # Normal
                    if len(remaining) >= 2:
                        invoke_byte = remaining[1]
                        invoke_id = (invoke_byte >> 4) & 0x0F
                        priority = invoke_byte & 0x03
                        table_data.append(("    调用ID (Invoke-ID)", f"0x{invoke_byte:02X}", 
                                          f"ID={invoke_id}, Priority={priority}",
                                          "请求标识符", base_offset + local_offset, base_offset + local_offset))
                        local_offset += 1
                        
                        # Class-ID (2 bytes)
                        if len(remaining) >= 4:
                            class_id = struct.unpack('>H', remaining[2:4])[0]
                            class_name = {
                                1: "Data", 3: "Register", 4: "Extended-Register",
                                7: "Profile-Generic", 8: "Clock", 17: "Association-Logical-Device",
                                70: "Pulse-Counter", 81: "Comms-Port-HDLC", 100: "Application-Association"
                            }.get(class_id, f"Class-{class_id}")
                            
                            table_data.append(("    类ID (Class-ID)", f"0x{class_id:04X}", class_name,
                                              "COSEM 对象类", base_offset + local_offset, base_offset + local_offset + 1))
                            local_offset += 2
                            
                            # OBIS Code (6 bytes)
                            if len(remaining) >= 10:
                                obis_bytes = remaining[4:10]
                                obis_str = ".".join(str(b) for b in obis_bytes)
                                obis_desc = "未知对象"
                                # 常见 OBIS 映射
                                if obis_str == "0.0.99.98.2.255": obis_desc = "事件记录/日志 (Event Log)"
                                elif obis_str == "1.0.1.8.0.255": obis_desc = "有功电能正向总 (Active Energy Import Total)"
                                elif obis_str == "1.0.96.1.0.255": obis_desc = "设备标识/资产号"
                                
                                table_data.append(("    OBIS码", self._bytes_to_hex(obis_bytes), obis_str,
                                                  f"对象标识: {obis_desc}", base_offset + local_offset, base_offset + local_offset + 5))
                                local_offset += 6
                                
                                # Method-ID (1 byte)
                                if len(remaining) >= 11:
                                    method_id = remaining[10]
                                    table_data.append(("    方法ID (Method-ID)", f"0x{method_id:02X}", str(method_id),
                                                      "操作方法", base_offset + local_offset, base_offset + local_offset))
                                    local_offset += 1
                                    
                                    # Optional Data
                                    if len(remaining) >= 12:
                                        has_data = remaining[11]
                                        if has_data:
                                            table_data.append(("    包含数据", "0x01", "Yes", "请求参数存在", base_offset + local_offset, base_offset + local_offset))
                                            local_offset += 1
                                            
                                            # 解析参数数据 (Data 结构)
                                            # 数据通常以 Tag 开始
                                            if len(remaining) > 12:
                                                data_blob = remaining[12:]
                                                
                                                # 尝试识别数据结构
                                                # 常见模式: Structure(01) -> Elements
                                                # 或者直接是 DateTime/String
                                                
                                                # 查找 DateTime 模式 (07 XX XX ...) 或 String (09 XX ...)
                                                # 我们扫描数据寻找特征
                                                dt_found = False
                                                str_found = False
                                                
                                                # 简单启发式：查找 0x09 后跟长度
                                                for i in range(len(data_blob) - 1):
                                                    if data_blob[i] == 0x09:
                                                        d_len = data_blob[i+1]
                                                        if len(data_blob) >= i + 2 + d_len:
                                                            # 检查内容是否像 DateTime (以 07 开头)
                                                            val_start = data_blob[i+2]
                                                            if val_start == 0x07 and d_len == 12:
                                                                dt_bytes = data_blob[i+2:i+2+12]
                                                                try:
                                                                    year = struct.unpack('>H', dt_bytes[0:2])[0]
                                                                    month = dt_bytes[2]
                                                                    day = dt_bytes[3]
                                                                    hour = dt_bytes[4]
                                                                    minute = dt_bytes[5]
                                                                    second = dt_bytes[6]
                                                                    dt_str = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
                                                                    table_data.append(("      参数值 (DateTime)",
                                                                                      self._bytes_to_hex(dt_bytes),
                                                                                      dt_str,
                                                                                      "日期时间参数",
                                                                                      base_offset + local_offset + i, base_offset + local_offset + i + 13))
                                                                    dt_found = True
                                                                    break
                                                                except:
                                                                    pass
                                                    elif data_blob[i] == 0x07 and i > 0:
                                                        # 可能是直接的 DateTime 标签 (有些实现用 0x07 作为 DateTime 标签?)
                                                        # 标准是 0x18，但有时 Octet-String (0x06) 包含 DateTime
                                                        pass
                                                
                                                if not dt_found:
                                                    # 显示原始数据
                                                    table_data.append(("      参数数据 (Raw)",
                                                                      self._bytes_to_hex(data_blob[:15]) + ("..." if len(data_blob) > 15 else ""),
                                                                      f"{len(data_blob)}字节",
                                                                      "未解析的请求参数",
                                                                      base_offset + local_offset, base_offset + local_offset + min(len(data_blob) - 1, 14)))
        
        elif apdu_type == 0xC6:  # Action-Response (操作响应)
            if len(remaining) >= 1:
                invoke_id = remaining[0]
                table_data.append(("    调用ID", f"0x{invoke_id:02X}", str(invoke_id),
                                  "响应标识符", base_offset + local_offset, base_offset + local_offset))
                local_offset += 1
                
                if len(remaining) >= 2:
                    result = remaining[1]
                    result_map = {
                        0x00: "成功",
                        0x01: "硬件故障",
                        0x02: "临时失败",
                        0x03: "读写对象未定义",
                        0x09: "对象未定义",
                        0x0B: "对象访问被拒绝",
                        0x0D: "对象未激活"
                    }
                    result_name = result_map.get(result, f"未知(0x{result:02X})")
                    table_data.append(("    结果", f"0x{result:02X}", result_name,
                                      "操作执行结果", base_offset + local_offset, base_offset + local_offset))
                    local_offset += 1
                    
                    # 如果成功，可能包含返回数据
                    if result == 0x00 and len(remaining) >= 3:
                        return_data = remaining[2:]
                        table_data.append(("    返回数据",
                                          self._bytes_to_hex(return_data[:15]) + ("..." if len(return_data) > 15 else ""),
                                          f"{len(return_data)}字节",
                                          "操作响应数据",
                                          base_offset + local_offset, base_offset + min(local_offset + 14, len(remaining) - 1)))
        
        elif apdu_type in [0x01, 0x02]:  # AARQ/AARE
            if len(remaining) >= 1:
                # AARQ/AARE通常包含BER编码的关联数据
                table_data.append(("    关联数据",
                                  self._bytes_to_hex(remaining[:10]) + ("..." if len(remaining) > 10 else ""),
                                  f"{len(remaining)}字节",
                                  "关联请求/响应（BER编码）",
                                  base_offset + local_offset, base_offset + min(local_offset + 9, len(remaining) - 1)))

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
        control_byte = frame_bytes[offset]
        ctrl_type, ctrl_desc, ctrl_details = self._parse_control_field(control_byte)
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
