"""协议验证引擎 - 基类

提供统一的验证结果数据结构和基类接口。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional
from abc import ABC, abstractmethod


class CheckLevel(Enum):
    """校验结果级别"""
    PASS = "pass"      # 通过
    FAIL = "fail"      # 失败
    WARN = "warn"      # 警告


@dataclass
class CheckItem:
    """单个校验项结果"""
    name: str           # 校验项名称（如"起始字符"、"校验和"）
    level: CheckLevel   # 校验结果级别
    expected: str       # 期望值（如"0x68"）
    actual: str         # 实际值
    message: str        # 描述信息

    @property
    def icon(self) -> str:
        """返回状态图标"""
        if self.level == CheckLevel.PASS:
            return "✅"
        elif self.level == CheckLevel.FAIL:
            return "❌"
        else:
            return "⚠️"


@dataclass
class ValidationResult:
    """验证结果"""
    protocol: str                    # 协议名称
    valid: bool                      # 整体是否通过
    checks: List[CheckItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.level == CheckLevel.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.level == CheckLevel.FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.level == CheckLevel.WARN)

    def summary(self) -> str:
        """返回摘要字符串"""
        status = "通过" if self.valid else "失败"
        parts = [f"[{status}]"]
        parts.append(f"通过{self.pass_count}项")
        if self.fail_count > 0:
            parts.append(f"失败{self.fail_count}项")
        if self.warn_count > 0:
            parts.append(f"警告{self.warn_count}项")
        return ", ".join(parts)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "协议": self.protocol,
            "整体结果": "通过" if self.valid else "失败",
            "通过项数": self.pass_count,
            "失败项数": self.fail_count,
            "警告项数": self.warn_count,
            "校验项": [
                {
                    "名称": c.name,
                    "状态": c.level.value,
                    "期望": c.expected,
                    "实际": c.actual,
                    "说明": c.message
                }
                for c in self.checks
            ],
            "警告": self.warnings,
            "错误": self.errors
        }


class BaseValidator(ABC):
    """协议验证器基类"""

    @abstractmethod
    def verify(self, frame_bytes: bytes) -> ValidationResult:
        """验证帧的合法性，返回 ValidationResult"""
        pass

    def _check_min_length(self, data: bytes, min_len: int, protocol: str) -> CheckItem:
        """通用最小长度校验"""
        if len(data) < min_len:
            return CheckItem(
                name="帧长度",
                level=CheckLevel.FAIL,
                expected=f">={min_len}字节",
                actual=f"{len(data)}字节",
                message=f"帧长度不足，最小需要{min_len}字节"
            )
        return CheckItem(
            name="帧长度",
            level=CheckLevel.PASS,
            expected=f">={min_len}字节",
            actual=f"{len(data)}字节",
            message="帧长度满足最小要求"
        )

    def _check_start_char(self, data: bytes, expected: int, pos: int = 0) -> CheckItem:
        """通用起始字符校验"""
        if len(data) <= pos:
            return CheckItem(
                name="起始字符",
                level=CheckLevel.FAIL,
                expected=f"0x{expected:02X}",
                actual="数据不足",
                message="帧数据不足以读取起始字符"
            )
        actual = data[pos]
        if actual != expected:
            return CheckItem(
                name="起始字符",
                level=CheckLevel.FAIL,
                expected=f"0x{expected:02X}",
                actual=f"0x{actual:02X}",
                message=f"起始字符错误，期望0x{expected:02X}，实际0x{actual:02X}"
            )
        return CheckItem(
            name="起始字符",
            level=CheckLevel.PASS,
            expected=f"0x{expected:02X}",
            actual=f"0x{actual:02X}",
            message="起始字符正确"
        )

    def _check_end_char(self, data: bytes, expected: int) -> CheckItem:
        """通用结束字符校验"""
        if len(data) == 0:
            return CheckItem(
                name="结束字符",
                level=CheckLevel.FAIL,
                expected=f"0x{expected:02X}",
                actual="空帧",
                message="帧数据为空，无法校验结束字符"
            )
        actual = data[-1]
        if actual != expected:
            return CheckItem(
                name="结束字符",
                level=CheckLevel.FAIL,
                expected=f"0x{expected:02X}",
                actual=f"0x{actual:02X}",
                message=f"结束字符错误，期望0x{expected:02X}，实际0x{actual:02X}"
            )
        return CheckItem(
            name="结束字符",
            level=CheckLevel.PASS,
            expected=f"0x{expected:02X}",
            actual=f"0x{actual:02X}",
            message="结束字符正确"
        )

    def _calc_checksum_sum(self, data: bytes) -> int:
        """计算累加和校验（& 0xFF）"""
        return sum(data) & 0xFF

    def _calc_crc16_ccitt(self, data: bytes) -> int:
        """计算 CRC16-CCITT 校验（初始值0xFFFF，最终异或0xFFFF）"""
        crc_table = [
            0x0000, 0x1189, 0x2312, 0x329b, 0x4624, 0x57ad, 0x6536, 0x74bf,
            0x8c48, 0x9dc1, 0xaf5a, 0xbed3, 0xca6c, 0xdbe5, 0xe97e, 0xf8f7,
            0x1081, 0x0108, 0x3393, 0x221a, 0x56a5, 0x472c, 0x75b7, 0x643e,
            0x9cc9, 0x8d40, 0xbfdb, 0xae52, 0xdaed, 0xcb64, 0xf9ff, 0xe876,
            0x2102, 0x308b, 0x0210, 0x1399, 0x6726, 0x76af, 0x4434, 0x55bd,
            0xad4a, 0xbcc3, 0x8e58, 0x9fd1, 0xeb6e, 0xfae7, 0xc87c, 0xd9f5,
            0x3183, 0x200a, 0x1291, 0x0318, 0x77a7, 0x662e, 0x54b5, 0x453c,
            0xbdcb, 0xac42, 0x9ed9, 0x8f50, 0xfbef, 0xea66, 0xd8fd, 0xc974,
            0x4204, 0x538d, 0x6116, 0x709f, 0x0420, 0x15a9, 0x2732, 0x36bb,
            0xce4c, 0xdfc5, 0xed5e, 0xfcd7, 0x8868, 0x99e1, 0xab7a, 0xbaf3,
            0x5285, 0x430c, 0x7197, 0x601e, 0x14a1, 0x0528, 0x37b3, 0x263a,
            0xdecd, 0xcf44, 0xfddf, 0xec56, 0x98e9, 0x8960, 0xbbfb, 0xaa72,
            0x6306, 0x728f, 0x4014, 0x519d, 0x2522, 0x34ab, 0x0630, 0x17b9,
            0xef4e, 0xfec7, 0xcc5c, 0xddd5, 0xa96a, 0xb8e3, 0x8a78, 0x9bf1,
            0x7387, 0x620e, 0x5095, 0x411c, 0x35a3, 0x242a, 0x16b1, 0x0738,
            0xffcf, 0xee46, 0xdcdd, 0xcd54, 0xb9eb, 0xa862, 0x9af9, 0x8b70,
            0x8408, 0x9581, 0xa71a, 0xb693, 0xc22c, 0xd3a5, 0xe13e, 0xf0b7,
            0x0840, 0x19c9, 0x2b52, 0x3adb, 0x4e64, 0x5fed, 0x6d76, 0x7cff,
            0x9489, 0x8500, 0xb79b, 0xa612, 0xd2ad, 0xc324, 0xf1bf, 0xe036,
            0x18c1, 0x0948, 0x3bd3, 0x2a5a, 0x5ee5, 0x4f6c, 0x7df7, 0x6c7e,
            0xa50a, 0xb483, 0x8618, 0x9791, 0xe32e, 0xf2a7, 0xc03c, 0xd1b5,
            0x2942, 0x38cb, 0x0a50, 0x1bd9, 0x6f66, 0x7eef, 0x4c74, 0x5dfd,
            0xb58b, 0xa402, 0x9699, 0x8710, 0xf3af, 0xe226, 0xd0bd, 0xc134,
            0x39c3, 0x284a, 0x1ad1, 0x0b58, 0x7fe7, 0x6e6e, 0x5cf5, 0x4d7c,
            0xc60c, 0xd785, 0xe51e, 0xf497, 0x8028, 0x91a1, 0xa33a, 0xb2b3,
            0x4a44, 0x5bcd, 0x6956, 0x78df, 0x0c60, 0x1de9, 0x2f72, 0x3efb,
            0xd68d, 0xc704, 0xf59f, 0xe416, 0x90a9, 0x8120, 0xb3bb, 0xa232,
            0x5ac5, 0x4b4c, 0x79d7, 0x685e, 0x1ce1, 0x0d68, 0x3ff3, 0x2e7a,
            0xe70e, 0xf687, 0xc41c, 0xd595, 0xa12a, 0xb0a3, 0x8238, 0x93b1,
            0x6b46, 0x7acf, 0x4854, 0x59dd, 0x2d62, 0x3ceb, 0x0e70, 0x1ff9,
            0xf78f, 0xe606, 0xd49d, 0xc514, 0xb1ab, 0xa022, 0x92b9, 0x8330,
            0x7bc7, 0x6a4e, 0x58d5, 0x495c, 0x3de3, 0x2c6a, 0x1ef1, 0x0f78
        ]
        fcs = 0xFFFF
        for byte in data:
            fcs = ((fcs >> 8) ^ crc_table[(fcs ^ byte) & 0xFF]) & 0xFFFF
        return fcs ^ 0xFFFF
