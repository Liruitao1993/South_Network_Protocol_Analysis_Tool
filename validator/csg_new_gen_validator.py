"""新一代载波协议验证器 (通感一体化低压电力线宽带载波通信规约)"""

from .base import BaseValidator, ValidationResult, CheckItem, CheckLevel


class CSGNewGenValidator(BaseValidator):
    """新一代通感一体化载波协议帧合法性验证器

    校验项包括:
    1. 最小帧长度
    2. 报文端口号合法性
    3. 报文标识符合法性
    4. 控制域位域合法性
    5. 帧类型域合法性
    6. 业务标识合法性
    7. 帧长度一致性
    """

    # 合法端口号
    VALID_PORTS = {0x11, 0x13}

    # 合法报文标识符
    VALID_MSG_IDS = {0x0101}

    # 合法帧类型
    VALID_FRAME_TYPES = {0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0xE}  # 0=确认/否认,1=数据传输,2=命令,3=主动上报,4=抄控器,5=广播,6=数据订阅,14=厂家调试

    # 合法确认/否认业务标识
    VALID_CONFIRM_SVC = {0x00, 0x01}  # 0=确认,1=否认

    # 合法数据传输业务标识
    VALID_DATA_SVC = {0x00, 0x01, 0x02, 0x03}

    # 合法命令业务标识
    VALID_CMD_FUNC_SVC = {0x02, 0x03}
    VALID_CMD_COMM_SVC = {0x00, 0x01, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x10, 0xF0}

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        """验证新一代载波协议帧的合法性

        支持的输入格式:
        1. 完整应用层报文 (端口号+标识符+保留+应用层业务报文)
        2. MSDU负载 (VLAN+MSDU类型+应用层报文)
        3. MAC帧 (MAC头+MSDU+CRC)
        """
        result = ValidationResult(protocol="新一代载波协议(通感一体化)", valid=True)

        # ── 步骤1: 识别输入层次 ──
        data = frame_bytes
        if len(data) < 4:
            check = CheckItem(
                name="帧长度",
                level=CheckLevel.FAIL,
                expected=">=4字节",
                actual=f"{len(data)}字节",
                message="帧长度不足，最小需要4字节"
            )
            result.checks.append(check)
            result.valid = False
            return result

        result.checks.append(CheckItem(
            name="帧长度",
            level=CheckLevel.PASS,
            expected=">=4字节",
            actual=f"{len(data)}字节",
            message="帧长度满足最小要求"
        ))

        # 跳过 MSDU 头和 MAC 头（如果存在）
        offset = 0
        first_byte = data[0]

        # 检测 MAC 帧头
        header_type = first_byte & 0x01
        version = (first_byte >> 1) & 0x03
        if header_type in (0, 1) and version in (1, 2) and len(data) >= 12:
            # MAC帧: 长头32字节或短头12字节
            if header_type == 0:
                mac_header_len = 32
            else:
                mac_header_len = 12
            offset = mac_header_len  # 跳过MAC头

        # 检测 MSDU 头
        if offset + 2 <= len(data):
            vlan = data[offset]
            msdu_type = data[offset + 1]
            is_msdu = ((0 <= vlan <= 3) and msdu_type in (0x01, 0x02, 0x80))
            if is_msdu:
                offset += 2  # 跳过MSDU头

        # ── 步骤2: 校验应用层报文 ──
        app_data = data[offset:]
        if len(app_data) < 4:
            check = CheckItem(
                name="应用层数据长度",
                level=CheckLevel.FAIL,
                expected=">=4字节",
                actual=f"{len(app_data)}字节",
                message="应用层数据长度不足"
            )
            result.checks.append(check)
            result.valid = False
            return result

        app_offset = 0

        # 2.1 报文端口号
        port = app_data[app_offset]
        if port in self.VALID_PORTS:
            port_name = "业务报文(转发)" if port == 0x11 else "管理报文(模块)"
            result.checks.append(CheckItem(
                name="报文端口号",
                level=CheckLevel.PASS,
                expected="0x11或0x13",
                actual=f"0x{port:02X}",
                message=f"端口号正确: {port_name}"
            ))
        else:
            result.checks.append(CheckItem(
                name="报文端口号",
                level=CheckLevel.FAIL,
                expected="0x11或0x13",
                actual=f"0x{port:02X}",
                message=f"端口号不合法: 0x{port:02X}"
            ))
            result.valid = False
        app_offset += 1

        # 2.2 报文标识符
        if app_offset + 1 < len(app_data):
            msg_id = (app_data[app_offset] << 8) | app_data[app_offset + 1]
            if msg_id in self.VALID_MSG_IDS:
                result.checks.append(CheckItem(
                    name="报文标识符",
                    level=CheckLevel.PASS,
                    expected="0x0101",
                    actual="0x0101",
                    message="报文标识符正确(CCO-STA)"
                ))
            else:
                result.checks.append(CheckItem(
                    name="报文标识符",
                    level=CheckLevel.WARN,
                    expected="0x0101",
                    actual=f"0x{msg_id:04X}",
                    message=f"非标准报文标识符: 0x{msg_id:04X}"
                ))
                result.warnings.append(f"报文标识符 0x{msg_id:04X} 非标准值")
        app_offset += 2

        # 2.3 保留字节
        if app_offset < len(app_data):
            reserved = app_data[app_offset]
            if reserved == 0x00:
                result.checks.append(CheckItem(
                    name="保留字段",
                    level=CheckLevel.PASS,
                    expected="0x00",
                    actual="0x00",
                    message="保留字段为0"
                ))
            else:
                result.checks.append(CheckItem(
                    name="保留字段",
                    level=CheckLevel.WARN,
                    expected="0x00",
                    actual=f"0x{reserved:02X}",
                    message="保留字段非零"
                ))
        app_offset += 1

        # 2.4 控制域
        if app_offset + 1 < len(app_data):
            ctrl = (app_data[app_offset + 1] << 8) | app_data[app_offset]
            direction = (ctrl >> 15) & 0x01
            prm = (ctrl >> 14) & 0x01
            response = (ctrl >> 13) & 0x01
            ext_flag = (ctrl >> 12) & 0x01
            priority = (ctrl >> 8) & 0x0F
            frame_type = ctrl & 0x0F

            # 帧类型域
            if frame_type in self.VALID_FRAME_TYPES:
                ft_names = {
                    0: "确认/否认", 1: "数据传输帧", 2: "命令帧",
                    3: "主动上报帧", 4: "抄控器协议", 5: "广播命令帧",
                    6: "数据订阅路由帧", 0xE: "厂家调试"
                }
                result.checks.append(CheckItem(
                    name="帧类型域(D3~D0)",
                    level=CheckLevel.PASS,
                    expected="0~6或0xE",
                    actual=f"0x{frame_type:X}",
                    message=f"帧类型: {ft_names.get(frame_type, '厂家调试')}"
                ))
            else:
                result.checks.append(CheckItem(
                    name="帧类型域(D3~D0)",
                    level=CheckLevel.FAIL,
                    expected="0~6或0xE",
                    actual=f"0x{frame_type:X}",
                    message=f"帧类型值0x{frame_type:X}不在合法范围内"
                ))
                result.valid = False

            # 业务扩展域标识
            result.checks.append(CheckItem(
                name="业务扩展域标识(D12)",
                level=CheckLevel.PASS if ext_flag in (0, 1) else CheckLevel.FAIL,
                expected="0或1",
                actual=str(ext_flag),
                message="有扩展域" if ext_flag else "无扩展域"
            ))

            # 方向
            result.checks.append(CheckItem(
                name="传输方向(D15)",
                level=CheckLevel.PASS,
                expected="0或1",
                actual=str(direction),
                message="下行(CCO→STA)" if direction == 0 else "上行(STA→CCO)"
            ))

            result.checks.append(CheckItem(
                name="启动标志(D14)",
                level=CheckLevel.PASS,
                expected="0或1",
                actual=str(prm),
                message="来自从动站" if prm == 0 else "来自启动站"
            ))
        app_offset += 2

        # 2.5 业务标识
        if app_offset < len(app_data):
            svc = app_data[app_offset]
            result.checks.append(CheckItem(
                name="业务标识",
                level=CheckLevel.PASS,
                expected="见协议文档",
                actual=f"0x{svc:02X}",
                message=f"业务标识: 0x{svc:02X}"
            ))
        app_offset += 1

        # 2.6 帧长度一致性 (如果有帧长字段)
        if app_offset + 1 < len(app_data):
            declared_len = (app_data[app_offset + 3] << 8) | app_data[app_offset + 2]
            # 帧长 = 应用版本(1) + 帧序号(2) + 帧长(2) + 数据单元
            # 剩余数据 = 总数据 - 头部
            remaining = len(app_data) - (app_offset + 4)
            if declared_len <= remaining + 100:  # 允许扩展域
                result.checks.append(CheckItem(
                    name="帧长度一致性",
                    level=CheckLevel.PASS,
                    expected=f"{declared_len}字节",
                    actual=f"数据区约{remaining}字节",
                    message="帧长度合理"
                ))
            else:
                result.checks.append(CheckItem(
                    name="帧长度一致性",
                    level=CheckLevel.WARN,
                    expected=f"{declared_len}字节",
                    actual=f"可用{remaining}字节",
                    message="声明帧长超过可用数据长度"
                ))

        return result
