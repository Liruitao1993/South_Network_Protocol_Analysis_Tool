"""PLC RF 协议验证器"""

from .base import BaseValidator, ValidationResult, CheckItem, CheckLevel


class PLCRFValidator(BaseValidator):
    """PLC RF 协议帧合法性验证器"""

    FRAME_START = 0x02

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        """验证 PLC RF 帧的合法性"""
        result = ValidationResult(protocol="PLC RF", valid=True)

        # 1. 最小帧长度校验
        check = self._check_min_length(frame_bytes, 8, "PLC RF")
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False
            return result

        # 2. 起始符校验 (0x02)
        check = self._check_start_char(frame_bytes, self.FRAME_START, 0)
        result.checks.append(check)
        if check.level == CheckLevel.FAIL:
            result.valid = False

        # 3. 长度域校验（小端序）
        if len(frame_bytes) >= 3:
            length_val = int.from_bytes(frame_bytes[1:3], 'little')
            actual_len = len(frame_bytes)
            if actual_len < length_val:
                check = CheckItem(
                    name="长度域",
                    level=CheckLevel.FAIL,
                    expected=f">={length_val}字节",
                    actual=f"{actual_len}字节",
                    message=f"帧数据不足，长度域指示{length_val}字节"
                )
                result.valid = False
            else:
                check = CheckItem(
                    name="长度域",
                    level=CheckLevel.PASS,
                    expected=f"{length_val}字节",
                    actual=f"{actual_len}字节",
                    message="长度域校验通过"
                )
            result.checks.append(check)

        # 4. CRC-16 校验
        if len(frame_bytes) >= 8:
            # CRC 位于帧尾部（最后2字节之前）
            crc_pos = len(frame_bytes) - 2
            if crc_pos >= 3:
                crc_received = int.from_bytes(frame_bytes[crc_pos:crc_pos + 2], 'little')
                crc_data = frame_bytes[1:crc_pos]  # 从 Length 到 CRC 之前
                crc_calc = self._calc_crc16_ccitt(crc_data)
                if crc_received == crc_calc:
                    check = CheckItem(
                        name="CRC校验",
                        level=CheckLevel.PASS,
                        expected=f"0x{crc_calc:04X}",
                        actual=f"0x{crc_received:04X}",
                        message="CRC校验正确"
                    )
                else:
                    check = CheckItem(
                        name="CRC校验",
                        level=CheckLevel.FAIL,
                        expected=f"0x{crc_calc:04X}",
                        actual=f"0x{crc_received:04X}",
                        message=f"CRC校验错误，期望0x{crc_calc:04X}"
                    )
                    result.valid = False
                result.checks.append(check)

        # 5. 控制域值检查
        if len(frame_bytes) >= 4:
            ctrl = frame_bytes[3]
            known_ctrl = {0xC0, 0xC4}
            if ctrl in known_ctrl:
                check = CheckItem(
                    name="控制域",
                    level=CheckLevel.PASS,
                    expected="0xC0或0xC4",
                    actual=f"0x{ctrl:02X}",
                    message=f"控制域值0x{ctrl:02X}有效"
                )
            else:
                check = CheckItem(
                    name="控制域",
                    level=CheckLevel.WARN,
                    expected="0xC0或0xC4",
                    actual=f"0x{ctrl:02X}",
                    message=f"未知控制域值0x{ctrl:02X}"
                )
                result.warnings.append(f"未知控制域值0x{ctrl:02X}")
            result.checks.append(check)

        return result
