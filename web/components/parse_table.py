# -*- coding: utf-8 -*-
"""解析结果表格组件：高亮、双击提取APDU、右键菜单、导出图片"""
from nicegui import ui
from typing import List, Tuple, Optional, Callable, Dict, Any
import json
import time


class ParseTable:
    """解析结果表格
    
    数据格式: List[Tuple[field_name, raw_value, parsed_value, comment, byte_start, byte_end, is_child]]
    对应 PySide6 的 table_data 结构
    """
    
    def __init__(
        self,
        on_row_click: Optional[Callable[[int, int], None]] = None,
        on_row_double_click: Optional[Callable[[str, int, int], None]] = None,
        on_export_image: Optional[Callable[[], None]] = None,
    ):
        self.on_row_click = on_row_click
        self.on_row_double_click = on_row_double_click
        self.on_export_image = on_export_image
        self._table = None
        self._rows_data: List[Dict] = []
        self._byte_ranges: List[Tuple[int, int]] = []  # 每行对应的字节范围
        self._last_click_time = 0
        self._last_click_row = -1
    
    def build(self):
        with ui.card().classes("w-full shadow-2 rounded-borders"):
            # 标题栏
            with ui.row().classes("w-full items-center q-pb-sm"):
                ui.icon("table_chart", size="sm", color="primary")
                ui.label("解析结果").classes("text-subtitle1 text-weight-medium")
                ui.space()
                with ui.menu() as self._overflow_menu:
                    ui.menu_item("导出图片", on_click=self._handle_export).props("icon=download")
                ui.button(icon="more_vert", on_click=self._overflow_menu.open).props("flat dense round")
            
            ui.separator()
            
            # 表格
            columns = [
                {"name": "field", "label": "字段", "field": "field", "align": "left", "sortable": True},
                {"name": "raw", "label": "原始值", "field": "raw", "align": "left", "sortable": True},
                {"name": "parsed", "label": "解析值", "field": "parsed", "align": "left", "sortable": True},
                {"name": "comment", "label": "说明", "field": "comment", "align": "left", "sortable": True},
            ]
            
            self._table = ui.table(
                columns=columns,
                rows=[],
                row_key="id",
                selection="single",
            ).classes("dense-table parse-table-striped w-full").props("flat bordered separator=cell virtual-scroll")
            
            # 行交替色 CSS
            ui.add_head_html("""
                <style>
                    .parse-table-striped .q-table tbody tr:nth-child(even) {
                        background-color: rgba(0, 0, 0, 0.02);
                    }
                    .parse-table-striped .q-table tbody tr:hover {
                        background-color: rgba(25, 118, 210, 0.06);
                    }
                </style>
            """)
            
            # 单元格自定义渲染：字段名缩进显示层级
            self._table.add_slot('body-cell-field', '''
                <q-td :props="props">
                    <div :style="{'padding-left': props.row.is_child ? '24px' : '0'}">
                        {{ props.row.field }}
                    </div>
                </q-td>
            ''')
            
            # 行点击事件
            self._table.on('rowClick', self._on_row_click)
            self._table.on('rowDblclick', self._on_row_double_click)
            
            # 右键菜单
            with ui.menu() as self._context_menu:
                ui.menu_item("复制字段名", on_click=lambda: self._copy_cell('field')).props("icon=content_copy")
                ui.menu_item("复制原始值", on_click=lambda: self._copy_cell('raw')).props("icon=content_copy")
                ui.menu_item("复制解析值", on_click=lambda: self._copy_cell('parsed')).props("icon=content_copy")
                ui.menu_item("复制说明", on_click=lambda: self._copy_cell('comment')).props("icon=content_copy")
                ui.separator()
                ui.menu_item("复制整行", on_click=self._copy_row).props("icon=content_copy")
                ui.separator()
                ui.menu_item("导出 JSON", on_click=self._export_json).props("icon=data_object")
    
    def set_data(self, table_data: List[Tuple], frame_bytes: bytes = b''):
        """设置表格数据
        
        Args:
            table_data: [(field, raw, parsed, comment, byte_start, byte_end, is_child), ...]
            frame_bytes: 原始帧字节，用于字节高亮
        """
        self._rows_data = []
        self._byte_ranges = []
        
        for idx, row in enumerate(table_data):
            # Handle both 6-element and 7-element tuples
            if len(row) == 6:
                field, raw, parsed, comment, byte_start, byte_end = row
                is_child = False
            else:
                field, raw, parsed, comment, byte_start, byte_end, is_child = row
            row_id = idx
            self._rows_data.append({
                "id": row_id,
                "field": field or "",
                "raw": str(raw) if raw is not None else "",
                "parsed": str(parsed) if parsed is not None else "",
                "comment": str(comment) if comment is not None else "",
                "is_child": bool(is_child),
                "_byte_start": byte_start,
                "_byte_end": byte_end,
            })
            self._byte_ranges.append((byte_start, byte_end))
        
        self._table.rows = self._rows_data
    
    def get_selected_range(self) -> Optional[Tuple[int, int]]:
        """获取选中行的字节范围"""
        selected = self._table.selected
        if selected and len(selected) > 0:
            row = selected[0]
            return (row.get("_byte_start"), row.get("_byte_end"))
        return None
    
    def _on_row_click(self, e):
        """行单击：高亮字节 + 单击回调"""
        row = e.args[0] if e.args else {}
        row_idx = row.get("id", -1)
        now = time.time() * 1000
        
        # 字节范围
        byte_start = row.get("_byte_start")
        byte_end = row.get("_byte_end")
        if byte_start is not None and byte_end is not None and self.on_row_click:
            self.on_row_click(byte_start, byte_end)
        
        # 双击检测：300ms 内同一行点击两次
        if row_idx == self._last_click_row and (now - self._last_click_time) < 300:
            if self.on_row_double_click:
                field = row.get("field", "")
                self.on_row_double_click(field, byte_start, byte_end)
        
        self._last_click_time = now
        self._last_click_row = row_idx
    
    def _on_row_double_click(self, e):
        """行双击事件（备选，NiceGUI 可能不直接支持 dblclick）"""
        pass
    
    async def _handle_export(self):
        if self.on_export_image:
            await self.on_export_image()
        else:
            ui.notify("导出图片功能待实现", type="info")
    
    def _copy_cell(self, col: str):
        selected = self._table.selected
        if selected:
            val = selected[0].get(col, "")
            ui.clipboard.write(val)
            ui.notify(f"已复制 {col}", type="positive")
    
    def _copy_row(self):
        selected = self._table.selected
        if selected:
            row = selected[0]
            text = "\t".join([str(row.get(c, "")) for c in ["field", "raw", "parsed", "comment"]])
            ui.clipboard.write(text)
            ui.notify("已复制整行", type="positive")
    
    def _export_json(self):
        selected = self._table.selected
        if selected:
            json_str = json.dumps(selected[0], ensure_ascii=False, indent=2)
            ui.clipboard.write(json_str)
            ui.notify("已导出 JSON", type="positive")
