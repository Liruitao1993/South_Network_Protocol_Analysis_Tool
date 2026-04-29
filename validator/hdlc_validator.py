"""HDLC/DLMS 协议验证器 (IEC 62056-46)"""

from .base import BaseValidator, ValidationResult, CheckItem, CheckLevel


class HDLCValidator(BaseValidator):
    """HDLC/DLMS 协议帧合法性验证器"""

    HDLC_FLAG = 0x7E

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        """验证 HDLC 帧的合法性"""
        result = ValidationResult(protocol="HDLC/DLMS", valid=True)

        # 1. 最小帧长度校验
        check = self._check_min_length(frame_bytes, 7, "HDLC")
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False
            return result

        # 2. 起始标志校验 (0x7E)
        check = self._check_start_char(frame_bytes, self.HDLC_FLAG, 0)
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 3. 结束标志校验 (0x7E)
        check = self._check_end_char(frame_bytes, self.HDLC_FLAG)
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 4. 格式域校验
        if len(frame_bytes) >= 3:
            fmt_byte = frame_bytes[1]
            format_type = (fmt_byte >> 4) & 0x0F
            if format_type == 0x0A:  # Type 3
                check = CheckItem(
                    name="格式域类型",
                    level=CheckLevel.PASS,
                    expected="Type 3 (0xA)",
                    actual=f"Type {format_type}",
                    message="格式域类型正确(Type 3)"
                )
            else:
                check = CheckItem(
                    name="格式域类型",
                    level=CheckLevel.WARN,
                    expected="Type 3 (0xA)",
                    actual=f"Type {format_type}",
                    message=f"非标准格式域类型(Type {format_type})"
                )
                result.warnings.append(f"非标准格式域类型(Type {format_type})")
            result.checks.append(check)

        # 5. HCS 校验（头部校验序列）
        if len(frame_bytes) >= 7:
            # HCS 位于地址域+控制域之后，信息域之前
            # 需要先解析地址域确定 HCS 位置
            addr_end = self._find_address_end(frame_bytes)
            if addr_end > 0 and addr_end + 2 < len(frame_bytes):
                hcs_pos = addr_end
                hcs_received = frame_bytes[hcs_pos] | (frame_bytes[hcs_pos + 1] << 8)
                hcs_data = frame_bytes[1:hcs_pos]  # 格式域 + 地址域 + 控制域
                hcs_calc = self._calc_crc16_ccitt(hcs_data)
                if hcs_received == hcs_calc:
                    check = CheckItem(
                        name="HCS校验",
                        level=CheckLevel.PASS,
                        expected=f"0x{hcs_calc:04X}",
                        actual=f"0x{hcs_received:04X}",
                        message="HCS校验正确"
                    )
                else:
                    check = CheckItem(
                        name="HCS校验",
                        level=CheckLevel.FAIL,
                        expected=f"0x{hcs_calc:04X}",
                        actual=f"0x{hcs_received:04X}",
                        message=f"HCS校验错误，期望0x{hcs_calc:04X}"
                    )
                    result.valid = False
                result.checks.append(check)

        # 6. FCS 校验（帧校验序列）
        if len(frame_bytes) >= 7:
            # FCS 位于结束标志之前
            fcs_pos = len(frame_bytes) - 3  # 倒数第2-3字节是FCS，最后1字节是结束标志
            if fcs_pos >= 2:
                fcs_received = frame_bytes[fcs_pos] | (frame_bytes[fcs_pos + 1] << 8)
                fcs_data = frame_bytes[1:fcs_pos]  # 格式域到信息域
                fcs_calc = self._calc_crc16_ccitt(fcs_data)
                if fcs_received == fcs_calc:
                    check = CheckItem(
                        name="FCS校验",
                        level=CheckLevel.PASS,
                        expected=f"0x{fcs_calc:04X}",
                        actual=f"0x{fcs_received:04X}",
                        message="FCS校验正确"
                    )
                else:
                    check = CheckItem(
                        name="FCS校验",
                        level=CheckLevel.FAIL,
                        expected=f"0x{fcs_calc:04X}",
                        actual=f"0x{fcs_received:04X}",
                        message=f"FCS校验错误，期望0x{fcs_calc:04X}"
                    )
                    result.valid = False
                result.checks.append(check)

        return result

    def _find_address_end(self, data: bytes) -> int:
        """查找地址域结束位置（地址域最高位为1表示结束）"""
        if len(data) < 3:
            return -1
        pos = 2  # 从第3字节开始（跳过起始标志和格式域）
        for i in range(pos, min(pos + 8, len(data))):
            if data[i] & 0x01:  # 最高位为1表示地址域结束
                return i + 1
        return -1
