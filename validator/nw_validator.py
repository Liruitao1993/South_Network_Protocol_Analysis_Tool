"""南网协议验证器 (Q/CSG1209021-2019)"""

from .base import BaseValidator, ValidationResult, CheckItem, CheckLevel


class NWValidator(BaseValidator):
    """南网协议帧合法性验证器"""

    AFN_VALID_RANGE = range(0x00, 0xF1)  # AFN 合法范围

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        """验证南网协议帧的合法性"""
        result = ValidationResult(protocol="南网协议", valid=True)

        # 1. 最小帧长度校验
        check = self._check_min_length(frame_bytes, 8, "南网协议")
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False
            return result

        # 2. 起始字符校验
        check = self._check_start_char(frame_bytes, 0x68, 0)
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 3. 长度域校验（小端序）
        if len(frame_bytes) >= 3:
            length_val = int.from_bytes(frame_bytes[1:3], 'little')
            expected_len = length_val + 6  # 长度域值 + 6字节固定长度
            actual_len = len(frame_bytes)
            if actual_len < expected_len:
                check = CheckItem(
                    name="长度域",
                    level=CheckLevel.FAIL,
                    expected=f"{expected_len}字节(长度域值{length_val}+6)",
                    actual=f"{actual_len}字节",
                    message=f"帧数据不足，长度域指示帧总长{expected_len}字节，实际仅{actual_len}字节"
                )
                result.valid = False
            elif actual_len > expected_len:
                check = CheckItem(
                    name="长度域",
                    level=CheckLevel.WARN,
                    expected=f"{expected_len}字节",
                    actual=f"{actual_len}字节",
                    message=f"帧数据超出长度域指示，可能包含额外数据"
                )
                result.warnings.append("帧数据超出长度域指示")
            else:
                check = CheckItem(
                    name="长度域",
                    level=CheckLevel.PASS,
                    expected=f"{expected_len}字节",
                    actual=f"{actual_len}字节",
                    message="长度域与实际帧长一致"
                )
            result.checks.append(check)

        # 4. 结束字符校验
        check = self._check_end_char(frame_bytes, 0x16)
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 5. 校验和校验（控制域 + 用户数据区的算术和）
        if len(frame_bytes) >= 8:
            cs_pos = len(frame_bytes) - 2  # 校验和位置：倒数第2字节
            cs_actual = frame_bytes[cs_pos]
            cs_data = frame_bytes[3:cs_pos]  # 控制域 + 用户数据区
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
            # AFN 在用户数据区第1字节（偏移6）
            afn = frame_bytes[6]
            if afn in self.AFN_VALID_RANGE:
                check = CheckItem(
                    name="AFN值域",
                    level=CheckLevel.PASS,
                    expected="0x00~0xF0",
                    actual=f"0x{afn:02X}",
                    message=f"AFN值0x{afn:02X}在合法范围内"
                )
            else:
                check = CheckItem(
                    name="AFN值域",
                    level=CheckLevel.WARN,
                    expected="0x00~0xF0",
                    actual=f"0x{afn:02X}",
                    message=f"AFN值0x{afn:02X}超出常规范围"
                )
                result.warnings.append(f"AFN值0x{afn:02X}超出常规范围")
            result.checks.append(check)

        return result
