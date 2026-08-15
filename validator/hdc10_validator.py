# -*- coding: utf-8 -*-
"""HDC 1.0 双模互联互通 校验器"""
from .base import BaseValidator, ValidationResult, CheckItem, CheckLevel


class HDC10Validator(BaseValidator):
    """HDC 1.0 双模互联互通协议校验器"""

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        checks = []
        errors = []
        warnings = []

        if len(frame_bytes) < 2:
            errors.append("帧数据过短")
            return ValidationResult(protocol="HDC 1.0双模", valid=False,
                                    checks=checks, errors=errors, warnings=warnings)

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
                message=f"DT={dt} (信标/SOF/SACK/网间协调)"
            ))

            # 标准版本号应为0 (HDC 1.0)
            version = (fc[12] >> 4) & 0x0F
            checks.append(CheckItem(
                name="标准版本号",
                expected="0",
                actual=str(version),
                level=CheckLevel.PASS if version == 0 else CheckLevel.WARN,
                message=f"版本={version} (0=HDC1.0)"
            ))

            # FCCS校验
            try:
                from hdc10_parser import _crc24
                calc = _crc24(fc[:13])
                fccs = int.from_bytes(fc[13:16], 'little')
                ok = calc == fccs
                checks.append(CheckItem(
                    name="FCCS校验",
                    expected=f"0x{calc:06X}",
                    actual=f"0x{fccs:06X}",
                    level=CheckLevel.PASS if ok else CheckLevel.FAIL,
                    message="CRC-24校验正确" if ok else "CRC-24校验失败"
                ))
            except Exception as e:
                checks.append(CheckItem(
                    name="FCCS校验",
                    expected="校验",
                    actual="无法计算",
                    level=CheckLevel.WARN,
                    message=str(e)
                ))

            # 网络标识NID
            nid = int.from_bytes(fc[1:4], 'little')
            checks.append(CheckItem(
                name="网络标识(NID)",
                expected="1~16777215",
                actual=str(nid),
                level=CheckLevel.PASS if 1 <= nid <= 16777215 else CheckLevel.WARN,
                message=f"NID=0x{nid:06X}"
            ))

        valid = all(c.level != CheckLevel.FAIL for c in checks)
        summary = f"帧长{len(frame_bytes)}字节，{'校验通过' if valid else '校验失败'}"

        return ValidationResult(
            protocol="HDC 1.0双模",
            valid=valid,
            checks=checks,
            errors=errors,
            warnings=warnings,
        )
