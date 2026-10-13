"""DLT645-2007 电表协议验证器"""

from .base import BaseValidator, ValidationResult, CheckItem, CheckLevel
from wakeup_prefix import strip_wakeup_prefix


class DLT645Validator(BaseValidator):
    """DLT645-2007 协议帧合法性验证器"""

    START_CHAR = 0x68
    END_CHAR = 0x16

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        """验证 DLT645 帧的合法性"""
        result = ValidationResult(protocol="DLT645-2007", valid=True)

        # 前导 FE 唤醒字节（DL/T645-2007 §5.3.1「建议先发送 4 个字节 FEH」）：
        # 校验与解析同预处理——先剥离再走全部检查（最小长度/起始符/结束符/CS/数据长度）。
        # 判定单一来源 = wakeup_prefix。
        original = frame_bytes
        frame_bytes, skipped = strip_wakeup_prefix(frame_bytes)

        if skipped:
            result.checks.append(CheckItem(
                name="前导唤醒字节",
                level=CheckLevel.PASS,
                expected="无",
                actual=f"{original[:skipped].hex(' ').upper()}（{skipped} 字节）",
                message=f"跳过 {skipped} 字节 FE 前导码（规范 §5.3.1 前导字节，非帧内容）",
            ))

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

        # 6. 数据长度字段检查（声明值与实际帧长一致性）
        if len(frame_bytes) >= 11:
            data_len = frame_bytes[9]  # 第10字节是数据长度
            expected_total = 12 + data_len  # 68+addr(6)+68+ctrl+len+data(N)+cs+16
            actual_total = len(frame_bytes)
            actual_data_len = actual_total - 12
            if actual_data_len != data_len:
                check = CheckItem(
                    name="数据长度",
                    level=CheckLevel.FAIL,
                    expected=f"{data_len}字节（帧总长{expected_total}）",
                    actual=f"{actual_data_len}字节（帧总长{actual_total}）",
                    message=f"数据域长度不匹配：声明{data_len}字节，实际{actual_data_len}字节"
                )
                result.errors.append(f"数据域长度不匹配：声明{data_len}字节，实际{actual_data_len}字节")
                result.valid = False
            elif data_len > 200:  # 合理性检查
                # LME自定义接口（单模STA版本251B/双模STA条目255B）数据域合法超长
                is_lme = False
                if len(frame_bytes) >= 14:
                    try:
                        di_bytes = bytes(((b - 0x33) & 0xFF) for b in frame_bytes[10:14])
                        di_code = f"{int.from_bytes(di_bytes, 'little'):08X}"
                        is_lme = di_code in ("04FFAAF9", "FF00DD01")
                    except Exception:
                        is_lme = False
                if is_lme:
                    check = CheckItem(
                        name="数据长度",
                        level=CheckLevel.PASS,
                        expected="LME自定义接口允许<=255字节",
                        actual=f"{data_len}字节",
                        message=f"LME自定义接口数据域{data_len}字节"
                    )
                else:
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
                    expected=f"{data_len}字节",
                    actual=f"{data_len}字节",
                    message=f"数据长度{data_len}字节"
                )
            result.checks.append(check)

        return result
