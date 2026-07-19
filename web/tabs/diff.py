# -*- coding: utf-8 -*-
"""报文对比标签页"""
from nicegui import ui
from typing import Optional, Dict, Any, List
from frame_diff_engine import FrameDiffEngine
from web.protocol_registry import get_parser_map
from web.components.byte_highlighter import ByteHighlighter


class DiffTab:
    def __init__(self, protocol_selector):
        self.protocol_selector = protocol_selector
        self.current_protocol = 0
        self._engine = FrameDiffEngine()
        self._parsers = get_parser_map()
        self._engine.set_parser(self._parsers[0]() if 0 in self._parsers else None)
        self._input_a = None
        self._input_b = None
        self._byte_table = None
        self._field_table = None
        self._interpretation = None
        self._options = {
            "field_aware": True,
            "ignore_checksum": True,
            "ignore_seq": True,
            "show_diff_only": False,
        }

    def build(self):
        with ui.column().classes("w-full q-pa-md q-gutter-md").style("height: 100%; display: flex; flex-direction: column; overflow: hidden;"):
            # ── 输入区 ──
            with ui.card().classes("w-full shadow-2 rounded-borders"):
                with ui.row().classes("w-full q-gutter-md q-pa-md"):
                    with ui.column().classes("flex-grow"):
                        with ui.row().classes("w-full items-center q-mb-sm"):
                            ui.icon("compare_arrows", color="blue-7").classes("text-h6 q-mr-sm")
                            ui.label("报文 A (基准)").classes("text-h6 text-blue-7")
                        self._input_a = ui.textarea(placeholder="粘贴十六进制报文 A...").classes("w-full").props('dense rows=4 style="height: 120px; font-family: monospace;"')

                    with ui.column().classes("flex-grow"):
                        with ui.row().classes("w-full items-center q-mb-sm"):
                            ui.icon("compare_arrows", color="orange-7").classes("text-h6 q-mr-sm")
                            ui.label("报文 B (对比)").classes("text-h6 text-orange-7")
                        self._input_b = ui.textarea(placeholder="粘贴十六进制报文 B...").classes("w-full").props('dense rows=4 style="height: 120px; font-family: monospace;"')

                # ── 操作栏 ──
                with ui.row().classes("w-full q-gutter-sm items-center q-px-md q-pb-md"):
                    ui.button("开始对比", icon="difference", on_click=self._do_diff).props("dense color=primary")
                    ui.button("交换 A↔B", icon="swap_horiz", on_click=self._swap).props("dense outline")
                    ui.space()

                    # 选项
                    ui.checkbox("字段感知对齐", value=True).props("dense").bind_value(self._options, "field_aware")
                    ui.checkbox("忽略校验和", value=True).props("dense").bind_value(self._options, "ignore_checksum")
                    ui.checkbox("忽略序列号", value=True).props("dense").bind_value(self._options, "ignore_seq")
                    ui.checkbox("仅显示差异", value=False).props("dense").bind_value(self._options, "show_diff_only")

            # ── 分割线 ──
            ui.separator().classes("q-my-xs")

            # ── 结果区 ──
            with ui.splitter(value=50).classes("w-full").style("flex: 1; min-height: 0;") as splitter:
                with splitter.before:
                    with ui.card().classes("w-full h-full shadow-2 rounded-borders"):
                        with ui.row().classes("w-full items-center q-mb-sm q-px-md"):
                            ui.icon("data_object", color="primary").classes("text-h6 q-mr-sm")
                            ui.label("字节级对比").classes("text-h6 text-grey-9")
                        self._byte_table = ui.html("").classes("q-pa-md").style("overflow: auto; height: calc(100% - 48px); font-family: monospace; font-size: 12px;")

                with splitter.after:
                    with ui.tabs().classes("w-full") as detail_tabs:
                        tab_field = ui.tab("字段级对比", icon="table_view")
                        tab_interpret = ui.tab("差异解读", icon="psychology")

                    with ui.tab_panels(detail_tabs, value=tab_field).classes("w-full h-[calc(100%-48px)]"):
                        with ui.tab_panel(tab_field):
                            columns = [
                                {"name": "offset", "label": "偏移", "field": "offset", "width": "80px"},
                                {"name": "length", "label": "长度", "field": "length", "width": "60px"},
                                {"name": "field_a", "label": "字段A", "field": "field_a"},
                                {"name": "value_a", "label": "值A", "field": "value_a"},
                                {"name": "field_b", "label": "字段B", "field": "field_b"},
                                {"name": "value_b", "label": "值B", "field": "value_b"},
                                {"name": "diff_type", "label": "差异类型", "field": "diff_type", "width": "100px"},
                            ]
                            self._field_table = ui.table(
                                columns=columns,
                                rows=[],
                            ).classes("dense-table w-full h-full").props("flat bordered separator=cell virtual-scroll")

                        with ui.tab_panel(tab_interpret):
                            self._interpretation = ui.label("对比后显示自然语言解读").classes("q-pa-md text-grey-7").style("white-space: pre-wrap; font-family: monospace; font-size: 12px;")

    def on_protocol_change(self, protocol_idx: int):
        self.current_protocol = protocol_idx
        parser_cls = self._parsers.get(protocol_idx)
        if parser_cls:
            self._engine.set_parser(parser_cls())

    def _do_diff(self):
        import re
        text_a = self._input_a.value or ""
        text_b = self._input_b.value or ""

        if not text_a.strip() or not text_b.strip():
            ui.notify("请输入两个报文", type="warning")
            return

        def clean_hex(text):
            clean = re.sub(r'0[xX]([0-9A-Fa-f])', r'\1', text)
            clean = re.sub(r'[^0-9A-Fa-f]', '', clean)
            return bytes.fromhex(clean) if len(clean) % 2 == 0 else b''

        bytes_a = clean_hex(text_a)
        bytes_b = clean_hex(text_b)

        if not bytes_a or not bytes_b:
            ui.notify("报文格式错误", type="negative")
            return

        try:
            # 使用 FrameDiffEngine
            hex_a = bytes_a.hex().upper()
            hex_b = bytes_b.hex().upper()
            result = self._engine.compare(
                hex_a, hex_b,
                field_aware_align=self._options["field_aware"],
                ignore_checksum=self._options["ignore_checksum"],
                ignore_sequence=self._options["ignore_seq"],
                show_only_diff=self._options["show_diff_only"],
            )

            # 显示字节级对比
            html_a, html_b = ByteHighlighter.diff_highlight(bytes_a, bytes_b)
            self._byte_table.set_content(f"<div style='display:flex; gap:20px;'><div><b>报文 A</b><br>{html_a}</div><div><b>报文 B</b><br>{html_b}</div></div>")

            # 显示字段级对比
            field_rows = []
            for item in result.get("field_diff", []):
                field_rows.append({
                    "offset": f"0x{item.get('offset', 0):04X}",
                    "length": item.get("length", 0),
                    "field_a": item.get("field_a", ""),
                    "value_a": item.get("value_a", ""),
                    "field_b": item.get("field_b", ""),
                    "value_b": item.get("value_b", ""),
                    "diff_type": item.get("diff_type", ""),
                })
            self._field_table.rows = field_rows

            # 显示差异解读
            interpretation = "\n".join(result.get("explanation", ["无解读"]))
            self._interpretation.set_text(interpretation)

            ui.notify("对比完成", type="positive")
        except Exception as e:
            ui.notify(f"对比出错: {e}", type="negative")
            import traceback
            traceback.print_exc()

    def _swap(self):
        a_val = self._input_a.value
        b_val = self._input_b.value
        self._input_a.value = b_val
        self._input_b.value = a_val
        self._input_a.update()
        self._input_b.update()
