# -*- coding: utf-8 -*-
"""档案管理标签页 - Web版本"""
from nicegui import ui
from typing import List, Dict, Any
from pathlib import Path
import json


class ArchiveTab:
    def __init__(self, protocol_selector, serial_panel):
        self.protocol_selector = protocol_selector
        self.serial_panel = serial_panel
        self.current_protocol = 0
        self._tree = None
        self._table = None

    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 工具栏
            with ui.row().classes("w-full items-center q-mb-sm"):
                with ui.row().classes("items-center q-gutter-xs"):
                    ui.icon("folder", size="sm", color="primary")
                    ui.label("档案管理").classes("text-h6 text-weight-bold")
                ui.space()
                ui.button("刷新", icon="refresh", on_click=self._refresh) \
                    .props("flat color=grey-7")
                ui.separator().props("vertical")
                ui.button("导入", icon="upload", on_click=self._import) \
                    .props("flat color=positive")
                ui.button("导出", icon="download", on_click=self._export) \
                    .props("flat color=secondary")

            # 分割器：左侧树形，右侧表格详情
            with ui.splitter(value=30).classes("w-full flex-grow") as splitter:
                with splitter.before:
                    with ui.card().classes("w-full h-full").style(
                        "box-shadow: 0 1px 5px rgba(0,0,0,0.08), 0 2px 2px rgba(0,0,0,0.06);"
                        "border-radius: 10px;"
                    ):
                        with ui.row().classes("items-center q-pa-sm q-px-md"):
                            ui.icon("account_tree", size="sm", color="grey-7")
                            ui.label("档案目录").classes("text-subtitle1 text-weight-medium")
                        ui.separator()
                        self._tree = ui.tree(
                            [],
                            label_key="name",
                            children_key="children",
                        ).classes("w-full flex-grow q-pa-sm").props("dense")

                with splitter.after:
                    with ui.card().classes("w-full h-full").style(
                        "box-shadow: 0 1px 5px rgba(0,0,0,0.08), 0 2px 2px rgba(0,0,0,0.06);"
                        "border-radius: 10px;"
                    ):
                        with ui.row().classes("items-center q-pa-sm q-px-md"):
                            ui.icon("list_alt", size="sm", color="grey-7")
                            ui.label("档案详情").classes("text-subtitle1 text-weight-medium")
                        ui.separator()
                        columns = [
                            {"name": "key", "label": "键", "field": "key", "width": "150px"},
                            {"name": "value", "label": "值", "field": "value"},
                        ]
                        self._table = ui.table(
                            columns=columns,
                            rows=[],
                        ).classes("dense-table w-full flex-grow").props("flat bordered separator=cell")

            self._refresh()

    def on_protocol_change(self, protocol_idx: int):
        self.current_protocol = protocol_idx
        if protocol_idx not in (0, 7):
            # 非南网/国网协议隐藏内容
            self._tree.nodes = []
            self._table.rows = []
        else:
            self._refresh()

    def _refresh(self):
        # 模拟数据
        nodes = [
            {"id": "collector", "name": "采集器档案", "children": [
                {"id": "meter_1", "name": "电表 001", "children": []},
                {"id": "meter_2", "name": "电表 002", "children": []},
            ]},
            {"id": "module", "name": "模块档案", "children": []},
        ]
        self._tree.nodes = nodes

    def _import(self):
        ui.notify("导入功能待实现", type="info")

    def _export(self):
        ui.notify("导出功能待实现", type="info")
