"""DLT645-2007 电表协议验证器"""

from .base import BaseValidator, ValidationResult, CheckItem, CheckLevel


class DLT645Validator(BaseValidator):
    """DLT645-2007 协议帧合法性验证器"""

    START_CHAR = 0x68
    END_CHAR = 0x16

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        """验证 DLT645 帧的合法性"""
        result = ValidationResult(protocol="DLT645-2007", valid=True)

        # 1. 最小帧长度校验
        check = self._check_min_length(frame_bytes, 12, "DLT645")
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False
            return result

        # 2. 起始符1校验 (0x68)
        check = self._check_start_char(frame_bytes, self.START_CHAR, 0)
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 3. 起始符2校验 (0x68)
        check = self._check_start_char(frame_bytes, self.START_CHAR, 7)
        check.name = "起始符2"
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 4. 结束符校验 (0x16)
        check = self._check_end_char(frame_bytes, self.END_CHAR)
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 5. 校验和校验（所有字节累加和 & 0xFF）
        if len(frame_bytes) >= 12:
            cs_pos = len(frame_bytes) - 2  # 倒数第2字节
            cs_actual = frame_bytes[cs_pos]
            cs_data = frame_bytes[0:cs_pos]  # 从第一个0x68到校验和之前
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
                    message=f"校验和错误，期望0x{cs_calc:02X}"
                )
                result.valid = False
            result.checks.append(check)

        # 6. 数据长度字段检查
        if len(frame_bytes) >= 11:
            data_len = frame_bytes[9]  # 第10字节是数据长度
            if data_len > 200:  # 合理性检查
                check = CheckItem(
                    name="数据长度",
                    level=CheckLevel.WARN,
                    expected="<=200字节",
                    actual=f"{data_len}字节",
                    message=f"数据长度{data_len}字节异常偏大"
                )
                result.warnings.append(f"数据长度{data_len}字节异常偏大")
            else:
                check = CheckItem(
                    name="数据长度",
                    level=CheckLevel.PASS,
                    expected="合理范围",
                    actual=f"{data_len}字节",
                    message=f"数据长度{data_len}字节"
                )
            result.checks.append(check)

        return result
