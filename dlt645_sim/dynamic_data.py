# -*- coding: utf-8 -*-
"""DLT645 从站动态数据产生器（纯逻辑无 Qt）。

目前只有一项：**事件状态字随机变化**。

- 事件状态字 = DI `04001501`「主动上报状态字」（《LME产品相关信息生产运维接口手册》语境下
  模块检测到引脚事件时主动读取的"电能表事件状态字"，实测抓包中载波模块反复轮询的正是它）。
- `dlt645_di.json` 声明该 DI 为 `BS96` → **12 字节**（与 `04001503 复位主动上报状态字` 同为
  BS96；`04000501~04000507 电表运行状态字1~7` 是 BS32/4 字节，不在此列）。
- 默认（不随机）时虚拟表读档案值，即 12 字节全 0 = 无事件、每次读取都一样；开启随机后
  每次读取返回一个新的随机 12 字节值。

> **状态归属**：虚拟表引擎每帧重建（串口线程收帧循环内 `_engine_factory()`），所以
> "保证与上一次不同"的状态必须由本模块的实例承载，由 GUI 持有并注入引擎，不能挂在引擎上。
"""

from __future__ import annotations

import random
from typing import Optional

#: 事件状态字 DI（主动上报状态字）
EVENT_WORD_DI = "04001501"

#: BS96 → 12 字节
EVENT_WORD_BYTES = 12

#: 重抽上限：12 字节随机撞上"与上次相同"的概率为 2^-96，仅在注入确定性桩时会用到
_MAX_RETRY = 8


class RandomEventWord:
    """事件状态字随机源：`next_value()` 每次返回新的 24 位 hex（12 字节）。

    - 保证与**上一次**返回值不同（否则"连续两次读到相同值"会被误判为随机没生效）；
    - `rng` 可注入（`random.Random(seed)` 便于测试复现，或注入必定碰撞的桩验证重抽）。
    """

    def __init__(self, nbytes: int = EVENT_WORD_BYTES, rng: Optional[random.Random] = None):
        if nbytes <= 0:
            raise ValueError(f"事件状态字字节数必须为正（当前 {nbytes}）")
        self.nbytes = int(nbytes)
        self._rng = rng or random.Random()
        self._last: Optional[str] = None

    def next_value(self) -> str:
        """新的随机事件状态字（大写 hex，长度 = 2 × nbytes）。"""
        value = self._draw()
        for _ in range(_MAX_RETRY):
            if value != self._last:
                break
            value = self._draw()
        self._last = value
        return value

    def reset(self) -> None:
        """清除"上一次值"记忆（切表/重置模拟时用）。"""
        self._last = None

    @property
    def last_value(self) -> Optional[str]:
        return self._last

    def _draw(self) -> str:
        return "".join(f"{self._rng.randrange(256):02X}" for _ in range(self.nbytes))
