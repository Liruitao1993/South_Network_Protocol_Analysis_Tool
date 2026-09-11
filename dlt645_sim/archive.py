# -*- coding: utf-8 -*-
"""DLT645 从站档案：DI → 数据值（字符串，与 encode_value 的 value 入参同口径）。"""

from __future__ import annotations

from typing import Dict, Optional

# 与 dlt645_di.json 常见字段对齐的默认演示值；可运行时改
DEFAULT_ARCHIVE: Dict[str, str] = {
    "00010000": "123456.78",  # (当前)正向有功总电能 kWh
    "00020000": "000123.45",  # (当前)反向有功总电能
    "00030000": "000001.23",  # 组合无功1总
    "00040000": "000000.45",  # 组合无功2总
    "00110000": "000045.67",  # (当前)正向有功总最大需量及发生时间用值部分
    "02010100": "220.5",  # A相电压 V（XXX.X）
    "02020100": "220.1",  # B相电压
    "02030100": "219.8",  # C相电压
    "02030101": "5.250",  # A相电流（XX.XXX）
    "02040101": "4.800",  # B相电流
    "02050101": "5.050",  # C相电流
    "04000101": "2026-09-11",  # 当前日期
    "04000201": "12:30:45",  # 当前时间
    "04000401": "100",  # 当前有功总功率
}


class DLT645Archive:
    """可读写 DI 值表。value 为组帧前的可读字符串。"""

    def __init__(self, values: Optional[Dict[str, str]] = None):
        self._values: Dict[str, str] = dict(DEFAULT_ARCHIVE)
        if values:
            for k, v in values.items():
                self._values[str(k).strip().upper().replace(" ", "")] = str(v)

    def get(self, di_code: str) -> Optional[str]:
        key = (di_code or "").strip().upper().replace(" ", "")
        return self._values.get(key)

    def set(self, di_code: str, value: str) -> None:
        key = (di_code or "").strip().upper().replace(" ", "")
        self._values[key] = str(value)

    def as_dict(self) -> Dict[str, str]:
        return dict(self._values)
