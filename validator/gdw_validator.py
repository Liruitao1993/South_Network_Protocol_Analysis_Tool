"""国网协议验证器 (Q/GDW 10376.2-2024)"""

from .base import BaseValidator, ValidationResult, CheckItem, CheckLevel


class GDWValidator(BaseValidator):
    """国网协议帧合法性验证器"""

    AFN_VALID_RANGE = range(0x00, 0xF2)  # AFN 合法范围

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        """验证国网协议帧的合法性"""
        result = ValidationResult(protocol="国网协议", valid=True)

        # 1. 最小帧长度校验
        check = self._check_min_length(frame_bytes, 8, "国网协议")
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False
            return result

        # 2. 起始字符校验
        check = self._check_start_char(frame_bytes, 0x68, 0)
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 3. 格式域校验（第2-3字节）
        if len(frame_bytes) >= 4:
            fmt_byte = frame_bytes[1]
            # 格式域包含帧长度信息
            frame_len_from_fmt = ((frame_bytes[2] & 0x03) << 8) | fmt_byte
            actual_len = len(frame_bytes)
            if actual_len < frame_len_from_fmt:
                check = CheckItem(
                    name="格式域-帧长度",
                    level=CheckLevel.FAIL,
                    expected=f">={frame_len_from_fmt}字节",
                    actual=f"{actual_len}字节",
                    message=f"帧数据不足，格式域指示帧长{frame_len_from_fmt}字节"
                )
                result.valid = False
            else:
                check = CheckItem(
                    name="格式域-帧长度",
                    level=CheckLevel.PASS,
                    expected=f"{frame_len_from_fmt}字节",
                    actual=f"{actual_len}字节",
                    message="格式域帧长度校验通过"
                )
            result.checks.append(check)

        # 4. 结束字符校验
        check = self._check_end_char(frame_bytes, 0x16)
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 5. 校验和校验
        if len(frame_bytes) >= 8:
            cs_pos = len(frame_bytes) - 2
            cs_actual = frame_bytes[cs_pos]
            cs_data = frame_bytes[3:cs_pos]
            cs_calc = self._calc_checksum_sum(cs_data)
            if cs_actual == cs_calc:
                check = CheckItem(
                    name="校验和",
                    level=CheckLevel.PASS,
                    expected=f"0x{cs_calc:02X}",
                    actual=f"0x{cs_actual:02X}",
                    message="校验和正确"
                )
            else:
                check = CheckItem(
                    name="校验和",
                    level=CheckLevel.FAIL,
                    expected=f"0x{cs_calc:02X}",
                    actual=f"0x{cs_actual:02X}",
                    message=f"校验和错误，期望0x{cs_calc:02X}，实际0x{cs_actual:02X}"
                )
                result.valid = False
            result.checks.append(check)

        # 6. AFN 值域检查
        if len(frame_bytes) >= 8:
            afn = frame_bytes[6]
            if afn in self.AFN_VALID_RANGE:
                check = CheckItem(
                    name="AFN值域",
                    level=CheckLevel.PASS,
                    expected="0x00~0xF1",
                    actual=f"0x{afn:02X}",
                    message=f"AFN值0x{afn:02X}在合法范围内"
                )
            else:
                check = CheckItem(
                    name="AFN值域",
                    level=CheckLevel.WARN,
                    expected="0x00~0xF1",
                    actual=f"0x{afn:02X}",
                    message=f"AFN值0x{afn:02X}超出常规范围"
                )
                result.warnings.append(f"AFN值0x{afn:02X}超出常规范围")
            result.checks.append(check)

        return result
