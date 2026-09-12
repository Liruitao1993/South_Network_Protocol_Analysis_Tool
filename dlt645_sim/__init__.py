# -*- coding: utf-8 -*-
"""DL/T 645-2007 从站模拟（离线/串口共用核心，无 Qt）。

对齐 meter_sim/ 设计：engine.handle_frame(bytes) → list[bytes] 响应帧。
首版聚焦主站读数据（C=11H）闭环，未知 DI 回异常应答（ERR 无请求数据）。
"""

from .engine import DLT645MeterSim
from . import dynamic_data, lme_query

__all__ = ["DLT645MeterSim", "dynamic_data", "lme_query"]
