# -*- coding: utf-8 -*-
"""Modbus 协议解析器（RTU / TCP）。

对上层暴露的接口与其它协议解析器一致：

- ``ModbusParser.parse(data, profile=None)`` → 结构化 dict
- ``ModbusParser.parse_to_table(data, profile=None)`` → 表格行列表

``profile`` 为一份寄存器列表（``modbus_register_store`` 的 profile）：

- 传入 ⇒ 按「地址 + 数据类型 + 系数 + 单位」翻译每个寄存器；
- 不传 ⇒ **通用解析**：只解析到「读/写操作、起始地址与数量、寄存器原始值」，
  响应帧不含地址时按 0x0000 起推导并在说明列明确标注。

GUI 侧由 ``protocol_registry.ModbusGuiParser`` 包装，每次解析自动读取
``modbus_register_store`` 里当前选中的寄存器列表（顶栏下拉框所选）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import modbus_core

PROTOCOL_NAME = "Modbus"


class ModbusParser:
    """Modbus RTU / TCP 解析器。"""

    PROTOCOL_NAME = PROTOCOL_NAME

    def __init__(self) -> None:
        #: 最近一次解析的元信息（校验器 / 测试可读）
        self.last_meta: Dict[str, Any] = {}

    # ── 结构化解析 ──────────────────────────────────────────────
    def parse(self, data: bytes, profile: Optional[dict] = None) -> Dict[str, Any]:
        """解析整帧，返回含 ``rows`` 的结构化结果。"""
        result = modbus_core.parse_frame(bytes(data or b""), profile)
        self.last_meta = {
            "transport": result.get("transport"),
            "slave": result.get("slave"),
            "func": result.get("func"),
            "func_name": result.get("func_name"),
            "direction": result.get("direction"),
            "crc_ok": result.get("crc_ok"),
            "length_ok": result.get("length_ok"),
            "warnings": list(result.get("warnings") or []),
            "error": result.get("error") or "",
            "registers": result.get("registers") or [],
            "bits": result.get("bits") or [],
            "profile": (profile or {}).get("name") if isinstance(profile, dict) else "",
        }
        return result

    # ── 表格解析（GUI / 批量统一入口）───────────────────────────
    def parse_to_table(
        self, data: bytes, profile: Optional[dict] = None, verify: bool = None
    ) -> List[tuple]:
        """解析整帧为表格行（``verify`` 仅为接口兼容，Modbus 无容错模式）。"""
        raw = bytes(data or b"")
        try:
            result = self.parse(raw, profile)
            rows = result.get("rows") or []
            if not rows:
                reason = result.get("error") or "未产出任何字段"
                return [
                    ("❌ 解析失败", "", "", reason, 0, max(0, len(raw) - 1))
                ]
            return rows
        except Exception as exc:  # noqa: BLE001 —— 单帧异常不应炸整批
            self.last_meta = {"error": f"{type(exc).__name__}: {exc}"}
            return [
                (
                    "❌ 解析失败",
                    "",
                    "",
                    f"{type(exc).__name__}: {exc}",
                    0,
                    max(0, len(raw) - 1),
                )
            ]

    # ── 帧提取（批量解析复用同一实现）───────────────────────────
    @staticmethod
    def extract_frames(text: str) -> List[tuple]:
        """从日志文本提取 Modbus 帧（``[(hex, "", 行号), ...]``）。"""
        return modbus_core.extract_modbus_frames(text)


__all__ = ["PROTOCOL_NAME", "ModbusParser"]
