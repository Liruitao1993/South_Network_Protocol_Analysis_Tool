# -*- coding: utf-8 -*-
"""拓扑信息标签页 - Web版本"""
from nicegui import ui
from typing import List, Dict, Any


class TopologyTab:
    def __init__(self, protocol_selector, serial_panel):
        self.protocol_selector = protocol_selector
        self.serial_panel = serial_panel
        self.current_protocol = 0
        self._table = None
        self._search = None

    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 工具栏
            with ui.row().classes("w-full items-center q-mb-sm"):
                with ui.row().classes("items-center q-gutter-xs"):
                    ui.icon("device_hub", size="sm", color="primary")
                    ui.label("拓扑信息").classes("text-h6 text-weight-bold")
                ui.space()
                ui.button("刷新", icon="refresh", on_click=self._refresh) \
                    .props("flat color=grey-7")
                ui.button("自动刷新", icon="autorenew", on_click=self._toggle_auto) \
                    .props("flat color=info")
                ui.separator().props("vertical")
                with ui.input(placeholder="搜索 TEI/地址/角色...", on_change=self._filter) \
                        .classes("w-56").props("dense outlined clearable") as search_wrapper:
                    search_wrapper.add_slot("prepend",
                        '<q-icon name="filter_list" class="cursor-pointer" />')
                self._search = search_wrapper

            # 表格
            with ui.card().classes("w-full flex-grow").style(
                "box-shadow: 0 1px 5px rgba(0,0,0,0.08), 0 2px 2px rgba(0,0,0,0.06);"
                "border-radius: 10px;"
            ):
                columns = [
                    {"name": "tei", "label": "TEI", "field": "tei", "width": "80px"},
                    {"name": "addr", "label": "地址", "field": "addr"},
                    {"name": "role", "label": "角色", "field": "role", "width": "100px"},
                    {"name": "status", "label": "状态", "field": "status", "width": "100px"},
                    {"name": "rssi", "label": "信号强度", "field": "rssi", "width": "100px"},
                    {"name": "parent", "label": "父节点", "field": "parent"},
                    {"name": "children", "label": "子节点数", "field": "children", "width": "80px"},
                    {"name": "last_seen", "label": "最后见到", "field": "last_seen", "width": "150px"},
                ]
                self._table = ui.table(
                    columns=columns,
                    rows=[],
                ).classes("dense-table w-full flex-grow").props("flat bordered separator=cell virtual-scroll")

            self._refresh()

    def on_protocol_change(self, protocol_idx: int):
        self.current_protocol = protocol_idx
        if protocol_idx not in (0, 7):
            self._table.rows = []
        else:
            self._refresh()

    def _refresh(self):
        # 模拟数据
        rows = [
            {"tei": 1, "addr": "00:11:22:33:44:55", "role": "CCO", "status": "在线", "rssi": -45, "parent": "-", "children": 5, "last_seen": "2026-07-15 10:30:00"},
            {"tei": 2, "addr": "AA:BB:CC:DD:EE:FF", "role": "STA", "status": "在线", "rssi": -52, "parent": "1", "children": 0, "last_seen": "2026-07-15 10:29:55"},
        ]
        self._table.rows = rows

    def _filter(self, e):
        keyword = (e.value or "").lower()
        # 简单过滤
        pass

    def _toggle_auto(self):
        ui.notify("自动刷新待实现", type="info")
