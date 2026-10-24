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
        0x00: "无站地址（NO_STATION）",
        0x01: "客户端管理进程",
        0x10: "公共客户端 (最低安全级)",
        0x7F: "广播地址（ALL_STATION）",
        # 服务器端特殊地址
    }

    # HDLC链路层协商参数标识符（SNRM/UA信息域TLV标签，见ISO/IEC 13239 5.5.3.2）
    SNRM_UA_PARAM_TAGS = {
        0x05: "发送最大信息域长度（Max Info Field Length - Transmit）",
        0x06: "接收最大信息域长度（Max Info Field Length - Receive）",
        0x07: "发送窗口大小（Window Size - Transmit）",
        0x08: "接收窗口大小（Window Size - Receive）",
    }

    # COSEM 对象类名（Class-ID → 中文名，IEC 62056-6-2 蓝皮书对象模型）
    # 单一来源：`_parse_cosem_descriptor` 与 Action 分支都查这张表，避免两处表漂移。
    COSEM_CLASS_NAMES = {
        1: "数据（Data）", 3: "寄存器（Register）", 4: "扩展寄存器（Extended-Register）",
        5: "需量寄存器（Demand-Register）", 6: "活动日历（Activity-Calendar）",
        7: "通用曲线（Profile-Generic）", 8: "时钟（Clock）", 9: "脚本表（Script-Table）",
        10: "调度器（Schedule）", 15: "特殊日表（Special-Days-Table）",
        17: "关联逻辑设备（Association-Logical-Device）",
        20: "关联快照（Association-Snapshot）",
        42: "M-Bus 客户端端口（MBus-Client-Port）", 70: "脉冲计数器（Pulse-Counter）",
        81: "HDLC 通信端口（Comms-Port-HDLC）",
        100: "应用关联（Application-Association）",
        101: "安全设置（Security-Setup）",
        111: "断开控制（Disconnect-Control）",
    }

    # DLMS APDU类型映射（按IEC 62056标准/Green Book定义）
    APDU_TYPES = {
        # ── ACSE（BER 编码，标签 = APPLICATION 0~3；Green Book 9.4.1 / 9.3.2）──
        0x60: "AARQ (关联请求)",
        0x61: "AARE (关联响应)",
        0x62: "RLRQ (释放请求)",
        0x63: "RLRE (释放响应)",
        # ── xDLMS 标准 APDU（无加密、非 LN 引用；Green Book 9.4.1 CHOICE）──
        0x01: "Initiate-Request (初始化请求)",
        0x05: "Read-Request (读请求·SN 引用)",
        0x06: "Write-Request (写请求·SN 引用)",
        0x08: "Initiate-Response (初始化响应)",
        0x0C: "Read-Response (读应答·SN 引用)",
        0x0D: "Write-Response (写应答·SN 引用)",
        0x0E: "Confirmed-Service-Error (确认服务错误)",
        0x0F: "Data-Notification (数据通知/主动推送)",
        0x10: "Data-Notification-Confirm (数据通知确认)",
        0x16: "Unconfirmed-Write-Request (非确认写)",
        0x18: "Information-Report-Request (信息报告)",
        # ── xDLMS（LN 引用，无加密）──
        0xC0: "Get-Request (读请求)",
        0xC1: "Set-Request (写请求)",
        0xC2: "Event-Notification-Request (事件通知)",
        0xC3: "Action-Request (方法请求)",
        0xC4: "Get-Response (读应答)",
        0xC5: "Set-Response (写应答)",
        0xC7: "Action-Response (方法应答)",
        # ── 全局密钥加密（glo-*）──
        0xC8: "Glo-Get-Request (加密读请求)",
        0xC9: "Glo-Set-Request (加密写请求)",
        0xCA: "Glo-Event-Notification-Request (加密事件通知)",
        0xCB: "Glo-Action-Request (加密方法请求)",
        0xCC: "Glo-Get-Response (加密读应答)",
        0xCD: "Glo-Set-Response (加密写应答)",
        0xCF: "Glo-Action-Response (加密方法应答)",
        # ── 专属密钥加密（ded-*）──
        0xD0: "Ded-Get-Request (专属加密读请求)",
        0xD1: "Ded-Set-Request (专属加密写请求)",
        0xD2: "Ded-Event-Notification-Request (专属加密事件通知)",
        0xD3: "Ded-Action-Request (专属加密方法请求)",
        0xD4: "Ded-Get-Response (专属加密读应答)",
        0xD5: "Ded-Set-Response (专属加密写应答)",
        0xD7: "Ded-Action-Response (专属加密方法应答)",
        # ── 异常 / 访问 ──
        0xD8: "Exception-Response (异常响应)",
        0xD9: "Access-Request (访问请求)",
        0xDA: "Access-Response (访问应答)",
        # 注意：0xE6/0xE7 是 **LLC 地址字节**，不是 APDU 标签。
        # 旧表把 0x01/0x02/0x03/0x04 当 AARQ/AARE/RLRQ/RLRE、0x0C 当
        # ConfirmedServiceError、0x0E 当 GBT —— 与 Green Book 9.4.1 不符
        # （0x01=InitiateRequest、0x0C=ReadResponse、0x0E=ConfirmedServiceError，
        #  RLRQ/RLRE 是 ACSE 的 0x62/0x63），已按文档更正。
    }

    # Get-Request/Response 子类型
    # Get-Request/Response 子类型（中文在前、IEC 英文原名括注，方便国内现场对照文档）
    GET_REQUEST_TYPES = {
        0x01: "正常读（Normal）",
        0x02: "下一数据块（Next-Data-block）",
        0x03: "批量读（With-list）",
        0x04: "分块读（With-block）",
    }
    GET_RESPONSE_TYPES = {
        0x01: "正常响应（Normal）",
        0x02: "数据块响应（With-data-block）",
        0x03: "批量响应（With-list）",
    }

    # Set-Request/Response 子类型
    SET_REQUEST_TYPES = {
        0x01: "正常写（Normal）",
        0x02: "首块写（With-first-data-block）",
        0x03: "数据块写（With-data-block）",
        0x04: "批量写（With-list）",
        0x05: "批量首块写（With-list-and-first-data-block）",
    }
    SET_RESPONSE_TYPES = {
        # Green Book 9.4.1（L7072-7086）
        0x01: "正常响应（Normal）",
        0x02: "数据块响应（Datablock）",
        0x03: "最后块响应（Last-datablock）",
        0x04: "批量最后块响应（Last-datablock-with-list）",
        0x05: "批量响应（With-list）",
    }

    # Action-Request/Response 子类型（Green Book 9.4.1，L7142-7240）
    ACTION_REQUEST_TYPES = {
        0x01: "普通（Normal）",
        0x02: "下一参数块（Next-pblock）",
        0x03: "批量（With-list）",
        0x04: "首参数块（With-first-pblock）",
        0x05: "批量首参数块（With-list-and-first-pblock）",
        0x06: "参数块（With-pblock）",
    }
    ACTION_RESPONSE_TYPES = {
        0x01: "普通（Normal）",
        0x02: "参数块（With-pblock）",
        0x03: "批量（With-list）",
        0x04: "下一参数块（Next-pblock）",
    }

    # Data-Access-Result（Green Book 9.4.1，L7591-7627；稀疏枚举，不是连续 0~N）
    DATA_ACCESS_RESULTS = {
        0: "成功（success）",
        1: "硬件故障（hardware-fault）",
        2: "临时失败（temporary-failure）",
        3: "读写被拒绝（read-write-denied）",
        4: "对象未定义（object-undefined）",
        9: "对象类不一致（object-class-inconsistent）",
        11: "对象不可用（object-unavailable）",
        12: "类型不匹配（type-unmatched）",
        13: "访问范围越界（scope-of-access-violated）",
        14: "数据块不可用（data-block-unavailable）",
        15: "长读被中止（long-get-aborted）",
        16: "无进行中的长读（no-long-get-in-progress）",
        17: "长写被中止（long-set-aborted）",
        18: "无进行中的长写（no-long-set-in-progress）",
        19: "数据块号非法（data-block-number-invalid）",
        250: "其他原因（other-reason）",
    }

    # Action-Result（Green Book 9.4.1，L7629-7661）
    ACTION_RESULTS = {
        0: "成功（success）",
        1: "硬件故障（hardware-fault）",
        2: "临时失败（temporary-failure）",
        3: "读写被拒绝（read-write-denied）",
        4: "对象未定义（object-undefined）",
        9: "对象类不一致（object-class-inconsistent）",
        11: "对象不可用（object-unavailable）",
        12: "类型不匹配（type-unmatched）",
        13: "访问范围越界（scope-of-access-violated）",
        14: "数据块不可用（data-block-unavailable）",
        15: "长方法调用被中止（long-action-aborted）",
        16: "无进行中的长方法调用（no-long-action-in-progress）",
        19: "数据块号非法（data-block-number-invalid）",
        250: "其他原因（other-reason）",
    }

    # Exception-Response 的 service-error CHOICE（Green Book 9.4.1，L7291-7307）
    EXCEPTION_STATE_ERRORS = {
        1: "服务不允许（service-not-allowed）",
        2: "服务未知（service-unknown）",
    }
    EXCEPTION_SERVICE_ERRORS = {
        1: "操作不允许（operation-not-possible）",
        2: "服务不支持（service-not-supported）",
        3: "其他原因（other-reason）",
        4: "PDU 超长（pdu-too-long）",
        5: "解密失败（deciphering-error）",
        6: "调用计数器错误（invocation-counter-error），后跟 4 字节计数",
    }

    @staticmethod
    def _decode_invoke_id(invoke_byte: int) -> dict:
        """解码 Invoke-Id-And-Priority（Green Book 9.4.1，L7669-7693）。

        位定义（DLMS UA 从 bit0 起算）：

        - bits 0-3：invoke-id（0~15）
        - bits 4-5：保留
        - bit 6：service-class（0 = Unconfirmed，1 = Confirmed）
        - bit 7：priority（0 = Normal，1 = High）

        ⚠ 旧实现取**高** 4 位当 invoke-id、bit2 当 service-class、bit1-0 当
        priority，与文档相反：真实帧 `81`（1000 0001）应为「invoke-id=1、
        Confirmed、High」，旧实现显示「ID=8、Confirmed、Low」。
        """
        invoke_id = invoke_byte & 0x0F
        service_class = (
            "需确认（Confirmed）" if (invoke_byte & 0x40) else "不需确认（Unconfirmed）"
        )
        priority = "高优先级（High）" if (invoke_byte & 0x80) else "普通优先级（Normal）"
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
        # 帧长自证（IEC 62056-46 Type 3）：格式域声明值 = 首尾 7E 之间的字节数。
        # 现场抓包截断 / 串口半包时这里必然对不上；非阻断告警，但必须显式提示，
        # 否则「长度对不上」的残帧会被当成正常帧解析（实测 12 字节残帧曾判为解析成功）。
        length_hint = self._check_declared_length(frame_bytes, frame_length)
        if length_hint:
            table_data.append(("警告", f"声明 {frame_length} 字节", f"实际 {len(frame_bytes)} 字节",
                              length_hint, format_field_start, format_field_start + 1))
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
        
        dest_addr_desc = self._format_address_description(
            dest_addr, dest_addr_len, "目的",
            frame_bytes[dest_addr_start:dest_addr_start + dest_addr_len],
        )
        table_data.append(("目的地址域", self._bytes_to_hex(frame_bytes[offset:offset + dest_addr_len]),
                          dest_addr_desc, f"目的地址（{dest_addr_len}字节）", offset, offset + dest_addr_len - 1))
        offset += dest_addr_len

        # 4. 源地址域 (Source Address)
        src_addr_start = offset
        src_addr, src_addr_len = self._parse_address_field(frame_bytes, offset)
        if src_addr is None:
            table_data.append(("错误", "-", "-", "源地址解析失败", offset, offset))
            return table_data
        
        src_addr_desc = self._format_address_description(
            src_addr, src_addr_len, "源",
            frame_bytes[src_addr_start:src_addr_start + src_addr_len],
        )
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

    def _format_address_description(self, address: int, length: int, role: str,
                                    raw: bytes = b"") -> str:
        """格式化地址描述。

        HDLC 地址按 7 位一组编码（每字节 LSB 为扩展位），所以 4 字节
        ``00 02 00 23`` 的「HDLC 地址值」是 0x02200080 —— 这个数字对现场没有
        意义。DLMS（Green Book）把服务器地址拆成「逻辑设备 + 逻辑块」：

        - 2 字节：整体是服务器地址（HDLC 7 位值，如 ``02 47`` → 0x1181）
        - 4 字节：前 2 字节 = 逻辑设备地址、后 2 字节 = 逻辑块地址
          （每字节取高 7 位、组内大端：``00 02`` → 0x0001，``00 23`` → 0x0011）

        两种口径都给出，便于与厂家文档 / 抓包工具（Gurux）对照。
        """
        special = self.SPECIAL_ADDRESSES.get(address, "") if length == 1 else ""
        head = f"0x{address:0{max(2, length * 2)}X}"
        if special:
            head += f" ({special})"

        if length == 2 and len(raw) == 2:
            server = (raw[0] >> 1) | ((raw[1] >> 1) << 7)
            detail = f"服务器地址 0x{server:04X}（{server}）"
        elif length == 4 and len(raw) == 4:
            device = ((raw[0] >> 1) << 8) | (raw[1] >> 1)
            block = ((raw[2] >> 1) << 8) | (raw[3] >> 1)
            detail = (
                f"服务器地址：逻辑设备 0x{device:04X}（{device}），"
                f"逻辑块 0x{block:04X}（{block}）"
            )
        elif length == 1:
            detail = f"{role}地址（1 字节；客户端地址恒为 1 字节）"
        else:
            detail = f"{role}地址（{length} 字节）"
        return f"{head}，{detail}"

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

    @staticmethod
    def _check_declared_length(frame_bytes: bytes, frame_length: int) -> str:
        """校验格式域声明的帧长与实际字节数是否自洽（返回中文告警；自洽返回空串）。

        协议口径（IEC 62056-46 Type 3）：帧长 = 首尾 7E 之间的字节数（不含 7E 本身）。

        - 首尾都是 7E（完整帧）：整帧 = 帧长 + 2；
        - 只有起始 7E（半包）：整帧 = 帧长 + 1。

        现场意义：串口半包、抓包被截断、多帧粘在一起时，声明值一定对不上；
        这时仍应尽量解析已有字段，但必须让使用者看到「这条帧不完整/有残留」。
        """
        if frame_length <= 0:
            return ""
        has_tail_flag = len(frame_bytes) >= 2 and frame_bytes[-1] == HDLCParser.HDLC_FLAG
        expected = frame_length + (2 if has_tail_flag else 1)
        if len(frame_bytes) == expected:
            return ""
        if len(frame_bytes) < expected:
            return (f"帧长声明 {frame_length} 字节，实际只有 {len(frame_bytes)} 字节，"
                    f"疑似截断（还差 {expected - len(frame_bytes)} 字节）")
        return (f"帧长声明 {frame_length} 字节，实际有 {len(frame_bytes)} 字节，"
                f"多出 {len(frame_bytes) - expected} 字节（可能粘包）")
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
                                  f"SAP 0x{dsap >> 1:02X}（目的）",
                                  "LLC 目的服务接入点（DLMS 固定 0xE6）",
                                  base_offset + offset, base_offset + offset))
                offset += 1

                table_data.append(("  LLC SSAP", f"0x{ssap:02X}",
                                  f"SAP 0x{ssap >> 1:02X}（源）",
                                  "LLC 源服务接入点（0xE6=客户端发起 / 0xE7=服务端应答）",
                                  base_offset + offset, base_offset + offset))
                offset += 1

                table_data.append(("  LLC控制", f"0x{llc_ctrl:02X}",
                                  dir_desc, "UI 帧（无编号信息，LLC 控制字段=0x00）",
                                  base_offset + offset, base_offset + offset))
                offset += 1
            elif dsap >= 0xE0 and ssap >= 0xE0:
                # 其他 LLC 地址（兼容旧版）
                table_data.append(("  LLC DSAP", f"0x{dsap:02X}",
                                  f"SAP 0x{dsap >> 1:02X}",
                                  "目的服务接入点",
                                  base_offset + offset, base_offset + offset))
                offset += 1

                table_data.append(("  LLC SSAP", f"0x{ssap:02X}",
                                  f"SAP 0x{ssap >> 1:02X}",
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
        """是否像 ACSE 的 BER-TLV 编码（只有 AARQ 0x60 / AARE 0x61）。

        ⚠ 这里曾写成「长度 ≥ 2 就返回 True」，于是所有未识别 APDU（事件通知 0xC2、
        数据通知 0x0F、异常响应 0xD8 等）都被当成 BER 树解析，输出一堆错位的
        「BER 标签/长度」（真实帧实测）。DLMS 信息域里的 APDU 是 raw 编码，
        只有 ACSE 的 AARQ/AARE 使用 BER（tag 0x60/0x61）。
        """
        if len(data) < 3 or data[0] not in (0x60, 0x61):
            return False
        length_byte = data[1]
        if length_byte < 0x80:
            return 2 + length_byte <= len(data)
        num = length_byte & 0x7F
        if num not in (1, 2) or len(data) < 2 + num:
            return False
        declared = int.from_bytes(data[2:2 + num], "big")
        return 2 + num + declared <= len(data)
    
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
                # APPLICATION 标签：0x60=AARQ、0x61=AARE、0x62=RLRQ、0x63=RLRE
                # ⚠ 曾按 `tag - 0x60` 配表却把 0 写成 AARQ、1 写成 AARE 的同时
                #   又让 0x60 落到「APPLICATION 0」，结果 AARE 被标成 AARQ。
                app_num = tag - 0x60
                app_names = {
                    0: "AARQ (关联请求)",
                    1: "AARE (关联响应)",
                    2: "RLRQ (释放请求)",
                    3: "RLRE (释放响应)",
                }
                tag_desc = app_names.get(app_num, f"APPLICATION {app_num}")
            elif 0xA0 <= tag <= 0xBF:
                # Context-Specific标签
                ctx_num = tag - 0xA0
                # AARQ/AARE 中常见 Context-Specific 标签含义
                ctx_names = {
                    0: "协商 DLMS 版本（negotiated-dlms-version）",
                    1: "提议参数（proposed-parameter-pp）",
                    2: "提议参数挑战字（proposed-parameter-challenge）",
                    3: "客户端 SAP 标识（client-sap-id）",
                    4: "关联信息（association-information）",
                    5: "xDLMS 上下文信息（xdlms-context-info）",
                    6: "认证（authentication）",
                    7: "认证机制名（mechanism-name）",
                    8: "挑战字（challenge）",
                    9: "响应（response）",
                    10: "服务端 SAP 标识（server-sap-id）",
                    11: "提议的服务质量（proposed-quality-of-service）",
                    12: "密码（password）",
                    30: "用户信息（user-information）",
                }
                if ctx_num in ctx_names:
                    tag_desc = f"上下文 [{ctx_num}] {ctx_names[ctx_num]}"
                else:
                    tag_desc = f"上下文 [{ctx_num}]"
            else:
                # 解析 BER 标签: 解码 class + constructed + tag number
                tag_class = (tag >> 6) & 0x03
                constructed = (tag >> 5) & 0x01
                tag_number = tag & 0x1F
                class_names = {0: "通用（Universal）", 1: "应用（Application）",
                               2: "上下文（Context-Specific）", 3: "私有（Private）"}
                class_name = class_names.get(tag_class, f"类别 {tag_class}")
                constructed_str = "（构造类型）" if constructed else ""

                # 通用标签名称映射（中文在前，BER/ASN.1 英文原名括注）
                universal_names = {
                    0x01: "布尔值（BOOLEAN）",
                    0x02: "整数（INTEGER）",
                    0x03: "位串（BIT STRING）",
                    0x04: "字节串（OCTET STRING）",
                    0x05: "空值（NULL）",
                    0x06: "对象标识（OBJECT IDENTIFIER）",
                    0x09: "实数（REAL）",
                    0x0A: "枚举（ENUMERATED）",
                    0x10: "序列（SEQUENCE）",
                    0x13: "集合（SET）",
                    0x30: "序列（SEQUENCE）",
                    0x31: "集合（SET）",
                    0x35: "序列集合（SEQUENCE OF）",
                }
                if tag_class == 0 and tag_number in universal_names:
                    tag_desc = f"{class_name} {universal_names[tag_number]}{constructed_str}"
                elif tag_class == 2:  # 上下文专用（编号 = tag & 0x1F）
                    ctx_names = {
                        4: "调用标识与优先级（invoke-id-and-priority）",
                        10: "发起方 ACSE 要求（sender-acse-requirements）",
                        12: "主叫认证值（calling-authentication-value）",
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
                # ⚠ 只对 constructed 递归。曾经写成「constructed 或长度>2 都递归」，
                # 于是 OBJECT IDENTIFIER / OCTET STRING 这类 primitive 的值被当成
                # 嵌套 TLV 拆开（AARQ 的 application-context OID 就这样碎成了
                # 「BER 标签 0x60 / BER 长度 85 74 ...」）。
                if is_constructed and len(value_data) >= 2:
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
        class_name = self.COSEM_CLASS_NAMES.get(
            class_id, f"未登记类 {class_id}（Class-{class_id}）"
        )
        table_data.append((f"{label_prefix}COSEM 类ID（Class-ID）", f"0x{class_id:04X}", class_name,
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

        # A-XDR 数据类型标签（IEC 62056-6-2 表 3 / DLMS Blue Book「Data」编码）。
        # 值 = (IEC 英文原名, 中文名)；解析值/说明列按「中文（英文原名）」展示，
        # 便于国内现场对照标准文档。
        # ⚠ 这张表曾经整体错位：0x02 当 Boolean、0x06 当 Octet-String、0x09 当
        #   Visible-String、0x10 当 Compact-Array —— 真实帧里 `09 0C <12 字节>`
        #   的 date-time 被当成可见字符串输出乱码，`10 00 78` 的 int16 完全解析不出来。
        TYPE_NAMES = {
            0x00: ("null", "空值"), 0x01: ("array", "数组"), 0x02: ("structure", "结构"),
            0x03: ("boolean", "布尔值"), 0x04: ("bit-string", "位串"),
            0x05: ("double-long", "32 位有符号整数"),
            0x06: ("double-long-unsigned", "32 位无符号整数"),
            0x09: ("octet-string", "字节串"), 0x0A: ("visible-string", "可见字符串"),
            0x0C: ("utf8-string", "UTF-8 字符串"), 0x0D: ("bcd", "BCD 码"),
            0x0F: ("integer", "8 位有符号整数"), 0x10: ("long", "16 位有符号整数"),
            0x11: ("unsigned", "8 位无符号整数"), 0x12: ("long-unsigned", "16 位无符号整数"),
            0x13: ("compact-array", "压缩数组"), 0x14: ("long64", "64 位有符号整数"),
            0x15: ("long64-unsigned", "64 位无符号整数"), 0x16: ("enum", "枚举"),
            0x17: ("float32", "32 位浮点数"), 0x18: ("float64", "64 位浮点数"),
            0x19: ("date-time", "日期时间"), 0x1A: ("date", "日期"), 0x1B: ("time", "时间"),
        }
        if type_tag in TYPE_NAMES:
            type_name, type_cn = TYPE_NAMES[type_tag]
            type_label = f"{type_cn}（{type_name}）"
        else:
            type_name = f"未知(0x{type_tag:02X})"
            type_label = type_name

        def add(parsed: str, consumed: int, note: str = "") -> None:
            """追加一行（原始值取本类型值的字节范围）。"""
            raw = data[:consumed]
            table_data.append((
                label,
                self._bytes_to_hex(raw[:32]) + ("..." if len(raw) > 32 else ""),
                parsed,
                note or f"{type_label}，共 {consumed} 字节",
                base_offset,
                base_offset + max(0, consumed - 1),
            ))

        # null
        if type_tag == 0x00:
            add("空值（null）", 1)
            return 1

        # array(0x01) / structure(0x02)：元素数(1) + 元素序列
        if type_tag in (0x01, 0x02):
            if len(data) < 2:
                add("数据不足", len(data))
                return len(data)
            count = data[1]
            table_data.append((
                label,
                f"0x{type_tag:02X} ({count})",
                f"{type_label}，元素数={count}",
                "复合数据类型（递归解析每个元素）",
                base_offset,
                base_offset + 1,
            ))
            cursor = 2
            for index in range(count):
                if cursor >= len(data):
                    break
                step = self._parse_dlms_value(
                    data[cursor:], table_data, base_offset + cursor,
                    f"    {label} [{index}]",
                )
                if step <= 0:
                    break
                cursor += step
            if cursor < len(data):
                table_data.append((
                    f"    {label} [未解析]",
                    self._bytes_to_hex(data[cursor:cursor + 20]) + ("..." if len(data) - cursor > 20 else ""),
                    f"{len(data) - cursor}字节",
                    "元素个数/长度与声明不符，剩余字节原样展示",
                    base_offset + cursor,
                    base_offset + len(data) - 1,
                ))
                cursor = len(data)
            return cursor

        # boolean
        if type_tag == 0x03:
            if len(data) < 2:
                add("数据不足", len(data))
                return len(data)
            value = data[1]
            add("TRUE" if value else "FALSE", 2)
            return 2

        # bit-string：位数(1) + 数据
        if type_tag == 0x04:
            if len(data) < 2:
                add("数据不足", len(data))
                return len(data)
            bit_len = data[1]
            byte_len = (bit_len + 7) // 8
            if len(data) < 2 + byte_len:
                add(f"数据不足（声明 {bit_len} 位）", len(data))
                return len(data)
            add(f"{bit_len} 位", 2 + byte_len, f"{type_label}，{bit_len} 位")
            return 2 + byte_len

        # 定长数值类型
        fixed = {
            0x05: (4, ">i"),   # double-long（32 位有符号）
            0x06: (4, ">I"),   # double-long-unsigned
            0x0F: (1, ">b"),   # integer（8 位有符号）
            0x10: (2, ">h"),   # long（16 位有符号）
            0x11: (1, ">B"),   # unsigned（8 位）
            0x12: (2, ">H"),   # long-unsigned（16 位）
            0x14: (8, ">q"),   # long64
            0x15: (8, ">Q"),   # long64-unsigned
            0x16: (1, ">B"),   # enum
            0x17: (4, ">f"),   # float32
            0x18: (8, ">d"),   # float64
        }
        if type_tag in fixed:
            size, fmt = fixed[type_tag]
            if len(data) < 1 + size:
                add("数据不足", len(data))
                return len(data)
            value = struct.unpack(fmt, data[1:1 + size])[0]
            text = f"{value:g}" if isinstance(value, float) else str(value)
            add(text, 1 + size)
            return 1 + size

        # octet-string：12 字节按 date-time、6 字节按 OBIS 逻辑名、其余十六进制
        if type_tag == 0x09:
            if len(data) < 2:
                add("数据不足", len(data))
                return len(data)
            length = data[1]
            if len(data) < 2 + length:
                add(f"数据不足（声明 {length} 字节）", len(data))
                return len(data)
            payload = data[2:2 + length]
            # 12 字节只有在「像合法 date-time」时才按日期解释；否则是普通
            # OCTET STRING（例如 0x09 0C FF4F19F3... 这种全 FF 的无效值）。
            if length == 12 and self._looks_like_dlms_datetime(payload):
                table_data.append((
                    f"{label} (date-time)",
                    self._bytes_to_hex(payload),
                    self._format_dlms_datetime(payload),
                    f"{type_label}（12 字节日期时间）",
                    base_offset,
                    base_offset + 1 + length,
                ))
            else:
                text = self._bytes_to_hex(payload) if payload else "-"
                if length == 6:
                    text = f"{text}  (OBIS {'.'.join(str(b) for b in payload)})"
                table_data.append((
                    label,
                    self._bytes_to_hex(payload),
                    text,
                    f"{type_label}（{length} 字节）",
                    base_offset,
                    base_offset + 1 + length,
                ))
            return 2 + length

        # visible-string / utf8-string / bcd：长度(1) + 内容
        if type_tag in (0x0A, 0x0C, 0x0D):
            if len(data) < 2:
                add("数据不足", len(data))
                return len(data)
            length = data[1]
            if len(data) < 2 + length:
                add(f"数据不足（声明 {length} 字节）", len(data))
                return len(data)
            payload = data[2:2 + length]
            if type_tag == 0x0A:
                text = payload.decode("ascii", errors="replace")
            elif type_tag == 0x0C:
                text = payload.decode("utf-8", errors="replace")
            else:
                text = "".join(f"{b >> 4}{b & 0x0F}" for b in payload)
            table_data.append((
                label,
                self._bytes_to_hex(payload),
                f'"{text}"',
                f"{type_label}（{length} 字节）",
                base_offset,
                base_offset + 1 + length,
            ))
            return 2 + length

        # date-time(0x19) / date(0x1A) / time(0x1B)：无长度前缀的定长类型
        if type_tag in (0x19, 0x1A, 0x1B):
            size = 12 if type_tag == 0x19 else (5 if type_tag == 0x1A else 4)
            if len(data) < 1 + size:
                add("数据不足", len(data))
                return len(data)
            payload = data[1:1 + size]
            if type_tag == 0x19:
                text = self._format_dlms_datetime(payload)
            elif type_tag == 0x1A:
                text = (
                    f"{int.from_bytes(payload[0:2], 'big'):04d}-"
                    f"{payload[2]:02d}-{payload[3]:02d}（星期{payload[4]}）"
                )
            else:
                text = f"{payload[0]:02d}:{payload[1]:02d}:{payload[2]:02d}.{payload[3]:02d}"
            add(text, 1 + size)
            return 1 + size

        # compact-array：元素类型/数量在数据内部，暂按原始字节展示
        if type_tag == 0x13:
            add(f"compact-array（{max(0, len(data) - 1)} 字节）", len(data),
                "压缩数组：元素类型与数量编码在数据内部，暂按原始字节展示")
            return len(data)

        # 未知类型：原样展示
        table_data.append((
            label,
            self._bytes_to_hex(data[:20]) + ("..." if len(data) > 20 else ""),
            f"{len(data)}字节",
            type_label,
            base_offset,
            base_offset + min(19, len(data) - 1),
        ))
        return len(data)

    @staticmethod
    def _format_dlms_datetime(payload: bytes) -> str:
        """DLMS date_time（12 字节）→ 可读文本。

        布局（IEC 62056-6-2）：年(2) 月 日 星期 时 分 秒 百分秒(1) 偏差(2，有符号分钟) 状态(1)。
        ``0xFF`` / ``0xFFFF`` 表示「未指定」。
        """
        if len(payload) != 12:
            return HDLCParser._bytes_to_hex(payload)
        year = int.from_bytes(payload[0:2], "big")
        month, day, weekday = payload[2], payload[3], payload[4]
        hour, minute, second = payload[5], payload[6], payload[7]
        hundredths = payload[8]
        deviation = int.from_bytes(payload[9:11], "big", signed=True)
        status = payload[11]
        time_text = f"{hour:02d}:{minute:02d}:{second:02d}"
        if hundredths != 0xFF:
            time_text += f".{hundredths:02d}"
        parts = [f"{year:04d}-{month:02d}-{day:02d}", time_text]
        weekdays = "一二三四五六日"
        if 1 <= weekday <= 7:
            parts.append(f"星期{weekdays[weekday - 1]}")
        parts.append(f"UTC偏差 {deviation} 分钟")
        parts.append("状态正常" if status == 0 else f"状态 0x{status:02X}（非 0，可能有异常）")
        return " ".join(parts)

    @staticmethod
    def _looks_like_dlms_datetime(payload: bytes) -> bool:
        """12 字节是否像合法 date-time（用于「可选日期字段」判别，避免硬套结构）。"""
        if len(payload) != 12:
            return False
        year = int.from_bytes(payload[0:2], "big")
        month, day = payload[2], payload[3]
        hour, minute, second = payload[5], payload[6], payload[7]
        return (
            1970 <= year <= 2200
            and 1 <= month <= 12
            and 1 <= day <= 31
            and hour <= 23
            and minute <= 59
            and second <= 59
        )

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
                                  "Get-Request（读请求）类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    调用标识与优先级（Invoke-Id-And-Priority）", f"0x{invoke_byte:02X}",
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
                            table_data.append(("    选择性访问（Selective-Access）",
                                              self._bytes_to_hex(remaining_after_desc[:5]) + ("..." if len(remaining_after_desc) > 5 else ""),
                                              f"{len(remaining_after_desc)}字节", "选择性访问描述符(可选)",
                                              bo + local_offset, bo + min(local_offset + 4, len(remaining) - 1)))

                # Next-Data-Block: block-number(4字节)
                elif req_type == 0x02 and len(remaining) >= 6:
                    block_num = struct.unpack('>I', remaining[2:6])[0]
                    table_data.append(("    Block-Number", f"0x{block_num:08X}", str(block_num),
                                      "数据块序号", bo + local_offset, bo + local_offset + 3))

                # With-List：invoke + COUNT + N ×（属性描述符 + 选择访问）
                elif req_type == 0x03 and len(remaining) >= 3:
                    count = remaining[2]
                    table_data.append(("    属性描述符数量", f"0x{count:02X}", str(count),
                                      "Get-Request-With-List 条目数",
                                      bo + local_offset + 1, bo + local_offset + 1))
                    pos = 3
                    for index in range(count):
                        if pos + 9 > len(remaining):
                            table_data.append((f"    [{index}] 数据不足",
                                              self._bytes_to_hex(remaining[pos:]),
                                              f"{len(remaining) - pos}字节", "条目被截断",
                                              bo + pos, bo + len(remaining) - 1))
                            pos = len(remaining)
                            break
                        consumed = self._parse_cosem_descriptor(
                            remaining[pos:], table_data, bo + pos, f"    [{index}] "
                        )
                        pos += consumed if consumed > 0 else 9
                        if pos < len(remaining):
                            sel = remaining[pos]
                            table_data.append((f"    [{index}] 选择访问", f"0x{sel:02X}",
                                              "无" if sel == 0 else "有（原始字节）",
                                              "Cosem-Attribute-Descriptor-With-Selection",
                                              bo + pos, bo + pos))
                            pos += 1
                            if sel == 0x01 and pos < len(remaining):
                                table_data.append((f"    [{index}] 选择器",
                                                  f"0x{remaining[pos]:02X}",
                                                  "选择性访问选择器（结构随对象类型）",
                                                  "access-selector", bo + pos, bo + pos))
                                pos += 1
                    local_offset = pos

        # ======== Get-Response (0xC4) ========
        # 结构: Response-Type(1) + InvokeIdAndPriority(1) + 后续内容(取决于type)
        elif apdu_type == 0xC4:
            if len(remaining) >= 1:
                resp_type = remaining[0]
                type_name = self.GET_RESPONSE_TYPES.get(resp_type, f"未知(0x{resp_type:02X})")
                table_data.append(("    响应类型", f"0x{resp_type:02X}", type_name,
                                  "Get-Response（读应答）类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    调用标识与优先级（Invoke-Id-And-Priority）", f"0x{invoke_byte:02X}",
                                  f"ID={inv['invoke_id']}, {inv['service_class']}, {inv['priority']}",
                                  "调用标识和优先级", bo + local_offset, bo + local_offset))
                local_offset += 1

                if resp_type == 0x01:
                    # Get-Response-Normal: Result(1) + [Data]
                    if len(remaining) >= 3:
                        result_tag = remaining[2]
                        if result_tag == 0x00:
                            # Data 成功
                            table_data.append(("    结果", "0x00", "成功（data）",
                                              "Get-Data-Result（读取结果）", bo + local_offset, bo + local_offset))
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
                                table_data.append(("    结果", f"0x{result_tag:02X}", f"访问结果错误：{err_name}",
                                                  "Get-Data-Result（读取结果·错误）", bo + local_offset, bo + local_offset + 1))
                            else:
                                table_data.append(("    结果", "0x01", "访问结果错误（DataAccessError）",
                                                  "Get-Data-Result（读取结果·错误）", bo + local_offset, bo + local_offset))

                elif resp_type == 0x02:
                    # Get-Response-With-Data-Block:
                    #   block-control(1) + block-number(4) + raw-data(n)
                    # 真实帧（分块读 profile/电能）先给块控制与块号，原始数据留给
                    # 「首块 + 后续块」拼装后按 A-XDR 解析。
                    pos = 2
                    if len(remaining) >= pos + 1:
                        block_control = remaining[pos]
                        table_data.append((
                            "    Block-Control",
                            f"0x{block_control:02X}",
                            "最后一块" if (block_control & 0x01) else "非最后一块（后续还有块）",
                            "分块控制：bit0 = last-block",
                            bo + local_offset + pos,
                            bo + local_offset + pos,
                        ))
                        pos += 1
                    if len(remaining) >= pos + 4:
                        block_number = int.from_bytes(remaining[pos:pos + 4], "big")
                        table_data.append((
                            "    Block-Number",
                            self._bytes_to_hex(remaining[pos:pos + 4]),
                            str(block_number),
                            "数据块序号（从 1 开始）",
                            bo + local_offset + pos,
                            bo + local_offset + pos + 3,
                        ))
                        pos += 4
                    raw_data = remaining[pos:]
                    if raw_data:
                        table_data.append((
                            "    分块数据",
                            self._bytes_to_hex(raw_data[:20]) + ("..." if len(raw_data) > 20 else ""),
                            f"{len(raw_data)}字节",
                            "raw-data（与首块拼装后再按 A-XDR 解析）",
                            bo + local_offset + pos,
                            bo + len(remaining) - 1,
                        ))
                    local_offset += len(remaining)
                # With-List：invoke + COUNT + N × Get-Data-Result（0x00=data / 0x01=错误）
                elif resp_type == 0x03 and len(remaining) >= 3:
                    count = remaining[2]
                    table_data.append(("    结果数量", f"0x{count:02X}", str(count),
                                      "Get-Response-With-List 条目数",
                                      bo + local_offset + 1, bo + local_offset + 1))
                    pos = 3
                    for index in range(count):
                        if pos >= len(remaining):
                            break
                        tag = remaining[pos]
                        if tag == 0x00:
                            table_data.append((f"    [{index}] 结果", "0x00", "成功（data）",
                                              "Get-Data-Result（数据）", bo + pos, bo + pos))
                            pos += 1
                            if pos < len(remaining):
                                consumed = self._parse_dlms_value(
                                    remaining[pos:], table_data, bo + pos, f"    [{index}] 数据"
                                )
                                pos += consumed if consumed > 0 else 0
                        elif tag == 0x01:
                            error = remaining[pos + 1] if pos + 1 < len(remaining) else 0
                            table_data.append((f"    [{index}] 结果", f"0x{error:02X}",
                                              self.DATA_ACCESS_RESULTS.get(error, f"未知(0x{error:02X})"),
                                              "Get-Data-Result（数据访问结果）",
                                              bo + pos, bo + min(pos + 1, len(remaining) - 1)))
                            pos += 2
                        else:
                            table_data.append((f"    [{index}] 未识别", f"0x{tag:02X}",
                                              "非 0x00/0x01 标签", "Get-Data-Result（读取结果）",
                                              bo + pos, bo + len(remaining) - 1))
                            pos = len(remaining)
                            break
                    local_offset = pos
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
                                  "Set-Request（写请求）类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    调用标识与优先级（Invoke-Id-And-Priority）", f"0x{invoke_byte:02X}",
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
                            table_data.append(("    选择性访问（Selective-Access）", "0x00", "无",
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
                                  "Set-Response（写应答）类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    调用标识与优先级（Invoke-Id-And-Priority）", f"0x{invoke_byte:02X}",
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
                elif resp_type in (0x04, 0x05) and len(remaining) >= 3:
                    # With-List / Last-Datablock-With-List：COUNT + N × Data-Access-Result
                    count = remaining[2]
                    table_data.append(("    结果数量", f"0x{count:02X}", str(count),
                                      "Set-Response-With-List 条目数",
                                      bo + local_offset + 1, bo + local_offset + 1))
                    pos = 3
                    for index in range(count):
                        if pos >= len(remaining):
                            break
                        value = remaining[pos]
                        table_data.append((f"    [{index}] 结果", f"0x{value:02X}",
                                          self.DATA_ACCESS_RESULTS.get(value, f"未知(0x{value:02X})"),
                                          "Data-Access-Result", bo + pos, bo + pos))
                        pos += 1
                    local_offset = pos
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
                                  "Action-Request（方法请求）类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    调用标识与优先级（Invoke-Id-And-Priority）", f"0x{invoke_byte:02X}",
                                  f"ID={inv['invoke_id']}, {inv['service_class']}, {inv['priority']}",
                                  "调用标识和优先级", bo + local_offset, bo + local_offset))
                local_offset += 1

                # Action-Normal: Cosem-Method-Descriptor (Class-ID + OBIS + Method-ID)
                if req_type == 0x01 and len(remaining) >= 11:
                    # Class-ID (2字节)
                    class_id = struct.unpack('>H', remaining[2:4])[0]
                    class_name = self.COSEM_CLASS_NAMES.get(
                        class_id, f"未登记类 {class_id}（Class-{class_id}）"
                    )

                    table_data.append(("    COSEM 类ID（Class-ID）", f"0x{class_id:04X}", class_name,
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

                elif req_type == 0x03 and len(remaining) >= 3:
                    # With-List：invoke + COUNT + N × 方法描述符 + COUNT + N × 参数
                    count = remaining[2]
                    table_data.append(("    方法描述符数量", f"0x{count:02X}", str(count),
                                      "Action-Request-With-List 条目数",
                                      bo + local_offset + 1, bo + local_offset + 1))
                    pos = 3
                    for index in range(count):
                        if pos + 9 > len(remaining):
                            table_data.append((f"    [{index}] 数据不足",
                                              self._bytes_to_hex(remaining[pos:]),
                                              f"{len(remaining) - pos}字节", "条目被截断",
                                              bo + pos, bo + len(remaining) - 1))
                            pos = len(remaining)
                            break
                        consumed = self._parse_cosem_descriptor(
                            remaining[pos:], table_data, bo + pos, f"    [{index}] "
                        )
                        pos += consumed if consumed > 0 else 9
                    if pos < len(remaining):
                        pcount = remaining[pos]
                        table_data.append(("    参数数量", f"0x{pcount:02X}", str(pcount),
                                          "SEQUENCE OF Data（方法调用参数）",
                                          bo + pos, bo + pos))
                        pos += 1
                        for index in range(pcount):
                            if pos >= len(remaining):
                                break
                            consumed = self._parse_dlms_value(
                                remaining[pos:], table_data, bo + pos, f"    [{index}] 参数"
                            )
                            pos += consumed if consumed > 0 else 0
                    local_offset = pos
        # ======== Action-Response (0xC7) ========
        # 结构: Response-Type(1) + InvokeIdAndPriority(1) + Action-Result(2) + [Return-Parameters]
        elif apdu_type == 0xC7:
            if len(remaining) >= 1:
                resp_type = remaining[0]
                type_name = self.ACTION_RESPONSE_TYPES.get(resp_type, f"未知(0x{resp_type:02X})")
                table_data.append(("    响应类型", f"0x{resp_type:02X}", type_name,
                                  "Action-Response（方法应答）类型", bo + local_offset, bo + local_offset))
                local_offset += 1

            if len(remaining) >= 2:
                invoke_byte = remaining[1]
                inv = self._decode_invoke_id(invoke_byte)
                table_data.append(("    调用标识与优先级（Invoke-Id-And-Priority）", f"0x{invoke_byte:02X}",
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
                                          "Action-Result（操作结果·成功）", bo + local_offset + 2, bo + local_offset + 2))
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
                                          "Action-Result（操作结果 CHOICE）", bo + local_offset + 2, bo + local_offset + 2))

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

                elif resp_type == 0x03 and len(remaining) >= 3:
                    # With-List：invoke + COUNT + N × Action-Result（success 时可跟返回数据）
                    count = remaining[2]
                    table_data.append(("    结果数量", f"0x{count:02X}", str(count),
                                      "Action-Response-With-List 条目数",
                                      bo + local_offset + 1, bo + local_offset + 1))
                    pos = 3
                    for index in range(count):
                        if pos >= len(remaining):
                            break
                        result = remaining[pos]
                        table_data.append((f"    [{index}] 结果", f"0x{result:02X}",
                                          self.ACTION_RESULTS.get(result, f"未知(0x{result:02X})"),
                                          "Action-Result（操作结果）", bo + pos, bo + pos))
                        pos += 1
                        if result == 0 and pos < len(remaining):
                            consumed = self._parse_dlms_value(
                                remaining[pos:], table_data, bo + pos, f"    [{index}] 返回数据"
                            )
                            pos += consumed if consumed > 0 else 0
                    local_offset = pos

        # ======== Event-Notification-Request (0xC2) ========
        # 结构: Long-Invoke-Id-And-Priority(4) + DateTime(12) + AttributeDescriptor(9) + Data
        elif apdu_type == 0xC2:
            if len(remaining) >= 4:
                invoke = int.from_bytes(remaining[0:4], "big")
                table_data.append(("    长调用标识与优先级（Long-Invoke-Id-And-Priority）", self._bytes_to_hex(remaining[0:4]),
                                  f"ID={invoke & 0x0FFFFFFF}", "4 字节调用标识（低 4 位为优先级/服务级别）",
                                  bo + local_offset, bo + local_offset + 3))
                local_offset += 4
            if len(remaining) >= local_offset + 12 and self._looks_like_dlms_datetime(
                remaining[local_offset:local_offset + 12]
            ):
                dt = remaining[local_offset:local_offset + 12]
                table_data.append(("    事件时间 (date-time)", self._bytes_to_hex(dt),
                                  self._format_dlms_datetime(dt), "事件发生的日期时间",
                                  bo + local_offset, bo + local_offset + 11))
                local_offset += 12
                if len(remaining) >= local_offset + 9:
                    consumed = self._parse_cosem_descriptor(
                        remaining[local_offset:], table_data, bo + local_offset
                    )
                    if consumed > 0:
                        local_offset += consumed
            # ⚠ 非标准/自定义的事件通知帧（日期字段不是合法 date-time）不硬套
            #   标准结构，直接按 A-XDR 数据解析剩余内容，避免输出荒谬时间。
            while local_offset < len(remaining):
                consumed = self._parse_dlms_value(
                    remaining[local_offset:], table_data, bo + local_offset, "    事件数据"
                )
                if consumed <= 0:
                    break
                local_offset += consumed

        # ======== Data-Notification (0x0F) ========
        # 结构（Green Book 9.4.1，L7322-7327）：
        #   long-invoke-id-and-priority(4) + date-time(OCTET STRING 12B) + notification-body
        elif apdu_type == 0x0F:
            if len(remaining) >= 4:
                invoke = int.from_bytes(remaining[0:4], "big")
                table_data.append(("    长调用标识与优先级（Long-Invoke-Id-And-Priority）", self._bytes_to_hex(remaining[0:4]),
                                  f"ID={invoke & 0xFFFFFF}，bit28 自描述={1 if invoke & (1 << 28) else 0}，"
                                  f"bit29 遇错继续={1 if invoke & (1 << 29) else 0}，"
                                  f"bit30 服务级别={'Confirmed' if invoke & (1 << 30) else 'Unconfirmed'}，"
                                  f"bit31 优先级={'High' if invoke & (1 << 31) else 'Normal'}",
                                  "4 字节长调用标识（低 24 位为 invoke-id）",
                                  bo + local_offset, bo + local_offset + 3))
                local_offset += 4
            # date-time：A-XDR OCTET STRING（09 0C + 12 字节）
            if (
                local_offset + 2 <= len(remaining)
                and remaining[local_offset] == 0x09
                and remaining[local_offset + 1] == 12
                and self._looks_like_dlms_datetime(
                    remaining[local_offset + 2: local_offset + 14]
                )
            ):
                payload = remaining[local_offset + 2: local_offset + 14]
                table_data.append(("    通知时间 (date-time)", self._bytes_to_hex(payload),
                                  self._format_dlms_datetime(payload),
                                  "主动推送的采集时间",
                                  bo + local_offset, bo + local_offset + 13))
                local_offset += 14
            elif (
                local_offset + 12 <= len(remaining)
                and self._looks_like_dlms_datetime(remaining[local_offset: local_offset + 12])
            ):
                # 少数实现直接跟 12 字节裸 date-time（不带 A-XDR 标签）
                payload = remaining[local_offset: local_offset + 12]
                table_data.append(("    通知时间 (date-time)", self._bytes_to_hex(payload),
                                  self._format_dlms_datetime(payload),
                                  "主动推送的采集时间（裸 12 字节）",
                                  bo + local_offset, bo + local_offset + 11))
                local_offset += 12
            if local_offset < len(remaining):
                body = remaining[local_offset]
                body_name = (
                    "data-notification（主动推送数据）"
                    if body == 0x00
                    else f"未知通知体(0x{body:02X})"
                )
                table_data.append(("    通知体类型", f"0x{body:02X}", body_name,
                                  "Notification-Body CHOICE", bo + local_offset, bo + local_offset))
                local_offset += 1
            while local_offset < len(remaining):
                consumed = self._parse_dlms_value(
                    remaining[local_offset:], table_data, bo + local_offset, "    通知数据"
                )
                if consumed <= 0:
                    break
                local_offset += consumed

        # ======== Exception-Response (0xD8) ========
        # 结构：state-error [0] ENUMERATED(1/2) + service-error [1] CHOICE(1~6)
        elif apdu_type == 0xD8:
            if len(remaining) >= 1:
                state = remaining[0]
                table_data.append((
                    "    State-Error",
                    f"0x{state:02X}",
                    self.EXCEPTION_STATE_ERRORS.get(state, f"未知/保留({state})"),
                    "异常响应：状态错误（1=服务不允许，2=服务未知）",
                    bo + local_offset, bo + local_offset,
                ))
                local_offset += 1
            if len(remaining) >= 2:
                service = remaining[1]
                table_data.append((
                    "    Service-Error",
                    f"0x{service:02X}",
                    self.EXCEPTION_SERVICE_ERRORS.get(service, f"未知/保留({service})"),
                    "异常响应：服务错误 CHOICE（1~6）",
                    bo + local_offset, bo + local_offset,
                ))
                local_offset += 1
                if service == 6 and len(remaining) >= 6:
                    counter = int.from_bytes(remaining[2:6], "big")
                    table_data.append((
                        "    调用计数器",
                        self._bytes_to_hex(remaining[2:6]),
                        str(counter),
                        "invocation-counter-error 附带的 4 字节计数器",
                        bo + local_offset, bo + local_offset + 3,
                    ))
                    local_offset += 4
            if local_offset < len(remaining):
                table_data.append((
                    "    剩余数据",
                    self._bytes_to_hex(remaining[local_offset:local_offset + 16]),
                    f"{len(remaining) - local_offset}字节",
                    "异常响应附加数据",
                    bo + local_offset, bo + len(remaining) - 1,
                ))
                local_offset = len(remaining)

        # ======== Access-Request / Access-Response (0xD9 / 0xDA) ========
        elif apdu_type in (0xD9, 0xDA):
            table_data.append(("    Access 数据", self._bytes_to_hex(remaining[:20]) + ("..." if len(remaining) > 20 else ""),
                              f"{len(remaining)}字节",
                              "DLMS 访问服务（access-request/response）：结构随访问描述符变化，"
                              "暂按原始字节展示",
                              bo + local_offset, bo + min(local_offset + 19, len(remaining) - 1)))
            local_offset = len(remaining)

        # ======== ACSE：AARQ/AARE/RLRQ/RLRE（0x60~0x63，BER 编码）========
        elif apdu_type in (0x60, 0x61, 0x62, 0x63):
            # AARQ/AARE 使用 BER 编码：APDU tag(0x60/0x61) + BER 长度 + 内容。
            # ⚠ remaining 已跳过 tag，必须把 tag 拼回去再交给 BER 解析 ——
            # 否则长度字节会被当成下一个 tag（真实 AARQ 帧实测整棵 BER 树错位一层）。
            ber = bytes([apdu_type]) + remaining
            table_data.append(("    关联数据",
                              self._bytes_to_hex(ber[:20]) + ("..." if len(ber) > 20 else ""),
                              f"{len(ber)}字节",
                              "关联请求/响应（BER 编码，含 APDU 标签与长度）",
                              max(0, bo + local_offset - 1),
                              max(0, bo + local_offset - 1) + min(19, len(ber) - 1)))
            # 深度解析 BER-TLV（_parse_ber_tlv 从 tag 开始，自带长度域处理）
            if len(ber) >= 2:
                self._parse_ber_tlv(ber, table_data, max(0, bo + local_offset - 1))
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
            # 帧长自证：与声明不符时给出中文提示（不改变「解析状态」，保持容错可用）
            "帧长校验": self._check_declared_length(frame_bytes, frame_length) or "与声明一致",
            "说明": "HDLC Type 3格式"
        }
        offset += 2
        
        # 3. 目的地址
        dest_addr, dest_len = self._parse_address_field(frame_bytes, offset)
        result["目的地址域"] = {
            "原始值": self._bytes_to_hex(frame_bytes[offset:offset + dest_len]),
            "地址值": f"0x{dest_addr:X}",
            "地址长度": f"{dest_len}字节",
            "说明": self._format_address_description(
                dest_addr, dest_len, "目的", frame_bytes[offset:offset + dest_len]
            )
        }
        offset += dest_len
        
        # 4. 源地址
        src_addr, src_len = self._parse_address_field(frame_bytes, offset)
        result["源地址域"] = {
            "原始值": self._bytes_to_hex(frame_bytes[offset:offset + src_len]),
            "地址值": f"0x{src_addr:X}",
            "地址长度": f"{src_len}字节",
            "说明": self._format_address_description(
                src_addr, src_len, "源", frame_bytes[offset:offset + src_len]
            )
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
            # ctrl_details 是 [(字段名, 原始bit, 解析值), ...] 的列表，
            # 不能 ** 展开（真实帧一跑就 TypeError）；这里转成可序列化的明细
            "位明细": [
                {"字段": name, "原始": raw, "解析": parsed}
                for name, raw, parsed in (ctrl_details or [])
            ],
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


# 为 HDLCParser 类添加 verify 方法
def _hdlc_verify(self, frame_bytes: bytes):
    """验证帧的协议一致性，返回 ValidationResult"""
    from validator.hdlc_validator import HDLCValidator
    validator = HDLCValidator()
    return validator.verify(frame_bytes)

HDLCParser.verify = _hdlc_verify
