# -*- coding: utf-8 -*-
"""国网新一代双模通信互联互通 校验器"""
from .base import BaseValidator, ValidationResult, CheckItem, CheckLevel


class GWNewGenValidator(BaseValidator):
    """国网新一代双模通信互联互通协议校验器"""

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        checks = []
        errors = []
        warnings = []

        if len(frame_bytes) < 2:
            errors.append("帧数据过短")
            return ValidationResult(protocol="国网新一代双模", valid=False, checks=checks, errors=errors, warnings=warnings)

        # 检查FC长度
        if len(frame_bytes) >= 16:
            fc = frame_bytes[:16]
            # 检查定界符类型
            dt = fc[0] & 0x07
            checks.append(CheckItem(
                name="定界符类型",
                expected="0~3",
                actual=str(dt),
                level=CheckLevel.PASS if dt <= 3 else CheckLevel.FAIL,
                message=f"DT={dt}"
            ))

            # 检查NID
            nid = (fc[1] << 8) | fc[2]
            checks.append(CheckItem(
                name="网络标识(NID)",
                expected="1~65535",
                actual=str(nid),
                level=CheckLevel.PASS if 1 <= nid <= 65535 else CheckLevel.WARN,
                message=f"NID=0x{nid:04X}"
            ))

            # 检查标准版本号
            version = (fc[12] >> 4) & 0x0F
            checks.append(CheckItem(
                name="标准版本号",
                expected="0~1",
                actual=str(version),
                level=CheckLevel.PASS if version <= 1 else CheckLevel.WARN,
                message=f"版本={version}"
            ))

            # 检查FCCS存在
            fccs = (fc[13] << 16) | (fc[14] << 8) | fc[15]
            checks.append(CheckItem(
                name="FCCS校验序列",
                expected="存在",
                actual=f"0x{fccs:06X}",
                level=CheckLevel.PASS,
                message="24bit CRC"
            ))

        valid = all(c.level != CheckLevel.FAIL for c in checks)
        summary = f"帧长{len(frame_bytes)}字节，{'校验通过' if valid else '校验失败'}"

        return ValidationResult(
            protocol="国网新一代双模",
            valid=valid,
            checks=checks,
            errors=errors,
            warnings=warnings,
        )
