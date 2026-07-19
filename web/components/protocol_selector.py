# -*- coding: utf-8 -*-
"""协议选择器：下拉框 + 新一代载波解析级别 + 字节剔除"""
from nicegui import ui
from typing import Callable, Optional


class ProtocolSelector:
    PROTOCOLS = [
        ("南网协议 (Q/CSG1209021-2019)", 0),
        ("PLC RF协议 (万胜海外 V1_04)", 1),
        ("HDLC/国网DLMS (IEC 62056-46)", 2),
        ("DLMS-APDU(国网)", 3),
        ("DLMS Wrapper裸报文", 4),
        ("DLMS-APDU裸报文", 5),
        ("DLT645-2007 电表协议", 6),
        ("国网协议 (Q/GDW 10376.2-2024)", 7),
        ("698.45协议 (DL/T 698.45-2017)", 8),
        ("新一代载波协议 (通感一体化)", 9),
        ("国网新一代双模通信互联互通", 10),
    ]

    CSG_LEVELS = [
        ("自动识别", "auto"),
        ("FC+PB解析(完整MPDU)", "fc_pb"),
        ("FC+eFC解析", "fc_efc"),
        ("仅FC解析", "fc_only"),
        ("应用层报文", "app"),
    ]

    # Badge palette for protocol chip
    _BADGE_COLOR = 'indigo-7'
    _BADGE_TEXT = 'white'

    def __init__(self, on_change: Optional[Callable[[int], None]] = None):
        self.current_protocol = 0
        self.current_csg_level = "auto"
        self.strip_head = 0
        self.strip_tail = 0
        self._on_change = on_change
        self._select = None
        self._csg_level_select = None
        self._strip_head_input = None
        self._strip_tail_input = None
        self._badge = None
        self._divider = None
        self._csg_card = None

    def _update_badge(self, value: int):
        """Refresh the protocol badge to reflect the current selection."""
        name = self.PROTOCOLS[value][0] if value < len(self.PROTOCOLS) else "未知"
        if self._badge:
            self._badge.text = name

    # ------------------------------------------------------------------ #
    #  Build                                                             #
    # ------------------------------------------------------------------ #
    def build(self):
        self.build_selector()
        self.build_csg_controls()

    def build_selector(self):
        """只构建协议选择器（用于 header）"""
        # ── Main row: router icon + selector + badge ───────────────────
        with ui.row().classes("items-center no-wrap gap-3 m-0 p-0 h-full"):
            ui.icon('router', color='white').classes('text-xl')

            self._select = ui.select(
                options={idx: name for name, idx in self.PROTOCOLS},
                value=self.current_protocol,
                on_change=self._on_protocol_change,
            ).classes("protocol-select w-72 text-gray-800 bg-white/95").props("dense outlined")
            self._select.tooltip("选择要解析的通信协议类型")

            # Protocol badge / chip
            initial_name = self.PROTOCOLS[self.current_protocol][0]
            self._badge = ui.badge(initial_name, color='white',
                text_color='indigo-7'
            ).classes("text-xs font-medium tracking-wide")

    def build_csg_controls(self):
        """构建新一代载波控制面板（独立控制条）"""
        # ── Divider between main selector and CSG controls ─────────────
        self._divider = ui.separator().classes("my-2 opacity-30")
        self._divider.style("display:none")

        # ── CSG controls card ──────────────────────────────────────────
        self._csg_card = ui.card().classes(
            "w-full rounded-xl bg-blue-50/60 border border-blue-100 "
            "p-3 gap-3 shadow-none"
        )
        self._csg_card.style("display:none")

        with self._csg_card:
            # Card header
            with ui.row().classes("items-center no-wrap gap-3"):
                ui.icon('tune', color='blue-7').classes('text-lg')
                ui.label("新一代载波解析设置").classes(
                    "font-semibold text-blue-900 text-sm"
                )

            ui.separator().classes("opacity-20 my-1")

            # Controls row
            with ui.row().classes("items-center no-wrap gap-3"):
                self._csg_level_select = ui.select(
                    options={v: k for k, v in self.CSG_LEVELS},
                    value=self.current_csg_level,
                    on_change=lambda e: setattr(self, 'current_csg_level', e.value),
                ).classes("w-52 text-gray-800").props("dense outlined")
                self._csg_level_select.tooltip("选择帧解析的深度级别")

                ui.separator().classes("opacity-10 h-6 mx-1")

                self._strip_head_input = ui.number(
                    value=0, min=0, max=999, step=1,
                    on_change=lambda e: setattr(self, 'strip_head', e.value),
                ).classes("w-20 text-gray-800").props("dense outlined suffix=' 字节'")
                self._strip_head_input.tooltip("从报文头部剔除的字节数（跳过监控帧头等）")

                self._strip_tail_input = ui.number(
                    value=0, min=0, max=999, step=1,
                    on_change=lambda e: setattr(self, 'strip_tail', e.value),
                ).classes("w-20 text-gray-800").props("dense outlined suffix=' 字节'")
                self._strip_tail_input.tooltip("从报文尾部剔除的字节数")

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                  #
    # ------------------------------------------------------------------ #
    def _on_protocol_change(self, e):
        self.current_protocol = e.value
        self._update_badge(e.value)
        is_csg = (self.current_protocol == 9)
        self._toggle_csg_controls(is_csg)
        if self._on_change:
            self._on_change(self.current_protocol)

    def _toggle_csg_controls(self, visible: bool):
        display = "" if visible else "none"
        self._divider.style(f"display:{display}")
        self._csg_card.style(f"display:{display}")
