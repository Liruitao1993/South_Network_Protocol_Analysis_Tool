# -*- coding: utf-8 -*-
"""DL/T 698.45 虚拟表（从站模拟器）核心逻辑包。

纯逻辑，不依赖 Qt：
- archive.py        档案数据（meter_sim_data.json，OI→A-XDR 数据）
- link_layer.py     链路层帧提取/头部解析
- response_builder.py  响应 APDU/链路帧构造
- dynamic_data.py   动态数据（时间/地址/电能量递增/冻结时标/漏点）
- engine.py         MeterSimEngine：请求帧 → 响应帧
"""
from .archive import Archive, load_archive
from .engine import MeterSimEngine, SimOptions

__all__ = ["Archive", "load_archive", "MeterSimEngine", "SimOptions"]
