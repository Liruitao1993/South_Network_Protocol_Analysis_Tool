"""DL/T 698.45 协议验证器"""

from typing import List
from validator.base import BaseValidator, CheckItem, CheckLevel, ValidationResult
from dl_t698_45_parser import DLT69845Parser


class DLT69845Validator(BaseValidator):
    """698.45 帧验证器"""

    def __init__(self):
        self.parser = DLT69845Parser()

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        checks: List[CheckItem] = []
        n = len(frame_bytes)

        # 1. 起始字符
        if n < 1:
            checks.append(CheckItem("起始字符", CheckLevel.FAIL, "0x68", "空帧", "帧为空"))
            return ValidationResult("698.45", False, checks)

        start_ok = frame_bytes[0] == 0x68
        checks.append(CheckItem(
            "起始字符", CheckLevel.PASS if start_ok else CheckLevel.FAIL,
            "0x68", f"0x{frame_bytes[0]:02X}",
            "通过" if start_ok else "起始字符错误"
        ))

        # 2. 帧长度检查
        if n < 3:
            checks.append(CheckItem("长度域", CheckLevel.FAIL, "≥3字节", f"{n}字节", "帧过短"))
            return ValidationResult("698.45", False, checks)

        # 3. 长度域一致性
        try:
            result = self.parser.parse(frame_bytes)
            length_val = result.get("长度域", {}).get("长度值", 0)
            # 698.45: L = 不含起始符和结束符的数据长度 → 帧总长 = 起始符(1) + L + 结束符(1)
            expected_len = length_val + 2
            len_ok = (n == expected_len)
            checks.append(CheckItem(
                "长度域一致性", CheckLevel.PASS if len_ok else CheckLevel.FAIL,
                str(expected_len), str(n),
                "通过" if len_ok else f"长度不匹配: 期望{expected_len}, 实际{n}"
            ))
        except Exception as e:
            checks.append(CheckItem("长度域一致性", CheckLevel.FAIL, "-", str(n), str(e)))

        # 4. HCS
        hcs_info = result.get("帧头校验HCS", {})
        hcs_ok = hcs_info.get("校验结果") == "通过"
        checks.append(CheckItem(
            "帧头校验HCS", CheckLevel.PASS if hcs_ok else CheckLevel.FAIL,
            hcs_info.get("计算值", "-"), hcs_info.get("原始值", "-"),
            hcs_info.get("校验结果", "未知")
        ))

        # 5. FCS
        fcs_info = result.get("帧校验FCS", {})
        fcs_ok = fcs_info.get("校验结果") == "通过"
        checks.append(CheckItem(
            "帧校验FCS", CheckLevel.PASS if fcs_ok else CheckLevel.FAIL,
            fcs_info.get("计算值", "-"), fcs_info.get("原始值", "-"),
            fcs_info.get("校验结果", "未知")
        ))

        # 6. 结束字符
        end_ok = frame_bytes[-1] == 0x16 if n > 0 else False
        checks.append(CheckItem(
            "结束字符", CheckLevel.PASS if end_ok else CheckLevel.FAIL,
            "0x16", f"0x{frame_bytes[-1]:02X}" if n > 0 else "无",
            "通过" if end_ok else "结束字符错误"
        ))

        valid = all(c.level == CheckLevel.PASS for c in checks)
        return ValidationResult("698.45", valid, checks)
