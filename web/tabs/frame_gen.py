# -*- coding: utf-8 -*-
"""协议组帧标签页 - 简化版框架"""
from nicegui import ui
from typing import Dict, List, Tuple, Any, Optional
from dl_t698_45_frame_schema import APDU_TYPE_LIST, OI_PRESET_LIST, DLT69845_FIELD_SCHEMA


class FrameGenTab:
    def __init__(self, protocol_selector):
        self.protocol_selector = protocol_selector
        self.protocol_mode = "south"
        self._di_combo = None
        self._afn_fn_combo = None
        self._dlt698_select_row = None
        self._dlt698_apdu_combo = None
        self._dlt698_sub_combo = None
        self._form_container = None
        self._preview_text = None
        self._field_widgets: Dict[str, Dict] = {}
        self._current_di_key = None
        self._current_afn_fn = None
        self._current_dlt698_key = None
    
    def build(self):
        with ui.splitter(value=40).classes("w-full h-full q-pa-md q-gutter-md") as splitter:
            # 左侧：命令选择 + 表单
            with splitter.before:
                with ui.column().classes("w-full h-full q-gutter-sm"):
                    # 命令选择区
                    self._build_command_selector()
                    
                    # 分割线
                    ui.separator().classes("q-my-xs")
                    
                    # 动态表单区
                    with ui.card().classes("w-full h-[calc(100%-200px)]").style("border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);"):
                        with ui.row().classes("w-full items-center q-pa-sm q-pb-none"):
                            ui.icon("dns", color="primary").classes("q-mr-sm")
                            ui.label("字段配置").classes("text-h6")
                        self._form_container = ui.column().classes("w-full h-full q-pa-md overflow-auto")
            
            # 右侧：预览 + 发送
            with splitter.after:
                with ui.column().classes("w-full h-full q-gutter-sm"):
                    with ui.card().classes("w-full h-[60%]").style("min-height: 300px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);"):
                        with ui.row().classes("w-full items-center q-pa-sm q-pb-none"):
                            ui.icon("visibility", color="primary").classes("q-mr-sm")
                            ui.label("生成预览").classes("text-h6")
                        self._preview_text = ui.textarea().classes("w-full h-full font-mono text-sm").props(
                            'dense readonly rows=20 style="height: 100%; font-family: JetBrains Mono, monospace; font-size: 12px;"'
                        )
                    
                    # 分割线
                    ui.separator().classes("q-my-xs")
                    
                    with ui.card().classes("w-full h-[40%]").style("min-height: 200px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);"):
                        with ui.row().classes("w-full items-center q-pa-sm q-pb-none"):
                            ui.icon("grid_on", color="primary").classes("q-mr-sm")
                            ui.label("帧配置").classes("text-h6")
                        self._build_frame_config()
                    
                    # 底部按钮栏
                    ui.separator().classes("q-my-xs")
                    with ui.card().classes("w-full").style("border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);"):
                        with ui.row().classes("w-full items-center q-gutter-sm q-pa-sm"):
                            ui.button("生成预览", icon="play_arrow", on_click=self._generate_preview).props("color=primary unelevated")
                            ui.button("发送帧", icon="send", on_click=self._send_frame).props("color=positive unelevated")
                            ui.button("添加到预设", icon="bookmark_add", on_click=self._add_to_preset).props("color=orange unelevated")
                            ui.button("添加到测试方案", icon="add_task", on_click=self._add_to_test).props("color=teal unelevated")
                            ui.space()
                            ui.button("导出JSON", icon="file_download", on_click=self._export_json).props("outline color=primary")
    
    def _build_command_selector(self):
        with ui.card().classes("w-full").style("border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);"):
            with ui.row().classes("w-full q-gutter-sm items-center q-pa-sm"):
                ui.icon("settings", color="primary").classes("q-mr-xs")
                ui.label("选择命令：").classes("text-weight-bold")
                
                # 南网 DI 选择
                self._di_combo = ui.select(
                    options={},
                    value=None,
                    on_change=self._on_di_change,
                ).classes("flex-grow").props("dense outlined clearable input-class='font-mono'")
                self._populate_di_combo()
                
                # 国网 AFN+Fn 选择 (隐藏)
                self._afn_fn_combo = ui.select(
                    options={},
                    value=None,
                    on_change=self._on_afn_fn_change,
                ).classes("flex-grow").props("dense outlined clearable input-class='font-mono'").set_visibility(False)
                self._populate_afn_fn_combo()
                
                # 698.45 APDU 选择 (隐藏)
                with ui.row().classes("flex-grow q-gutter-sm").set_visibility(False) as self._dlt698_select_row:
                    self._dlt698_apdu_combo = ui.select(
                        options={apdu: apdu for apdu in APDU_TYPE_LIST},
                        value=None,
                        on_change=self._on_dlt698_apdu_change,
                    ).classes("flex-grow").props("dense outlined clearable")
                    
                    self._dlt698_sub_combo = ui.select(
                        options={},
                        value=None,
                        on_change=self._on_dlt698_sub_change,
                    ).classes("flex-grow").props("dense outlined clearable")
                
                ui.button("命令说明", icon="help", on_click=self._show_cmd_help).props("dense outline")
    
    def _build_frame_config(self):
        with ui.grid().classes("w-full q-gutter-sm q-pa-sm").style("grid-template-columns: repeat(4, 1fr);"):
            ui.label("源地址 (6字节HEX):")
            self._src_addr = ui.input(value="000000000000", placeholder="000000000000").props("dense outlined").classes("col-span-3")
            
            ui.label("目的地址 (6字节HEX):")
            self._dst_addr = ui.input(value="000000000000", placeholder="000000000000").props("dense outlined").classes("col-span-3")
            
            ui.label("帧序列号:")
            self._seq_input = ui.number(value=0, min=0, max=255, step=1).props("dense outlined").classes("w-24")
            
            ui.label("传输方向:")
            self._dir_select = ui.select(options={0: "下行(主站→终端)", 1: "上行(终端→主站)"}, value=0).props("dense outlined")
            
            ui.label("启动标志(PRM):")
            self._prm_select = ui.select(options={0: "从动站发起(0)", 1: "启动站发起(1)"}, value=1).props("dense outlined")
    
    def _populate_di_combo(self):
        try:
            from protocol_parser import ProtocolFrameParser
            parser = ProtocolFrameParser()
            options = {}
            for (di3, di2, di1, di0), desc in parser.DI_COMBINATION_MAP.items():
                key = f"{di3:02X}{di2:02X}{di1:02X}{di0:02X}"
                options[key] = f"{key} - {desc}"
            self._di_combo.options = options
            self._di_combo.update()
        except Exception:
            pass
    
    def _populate_afn_fn_combo(self):
        try:
            from gdw10376_parser import GDW10376Parser
            parser = GDW10376Parser()
            options = {}
            for afn, fn_map in parser.FN_MAP.items():
                afn_name = parser.AFN_MAP.get(afn, f"未知({afn:02X})")
                for fn, fn_name in fn_map.items():
                    key = f"{afn:02X}{fn:02X}"
                    options[key] = f"{key} - {afn_name} / Fn={fn:02X} {fn_name}"
            self._afn_fn_combo.options = options
            self._afn_fn_combo.update()
        except Exception:
            pass
    
    def on_protocol_change(self, protocol_idx: int):
        mode_map = {0: "south", 1: "south", 2: "south", 3: "south", 4: "south", 5: "south", 
                    6: "south", 7: "gdw", 8: "dlt698", 9: "south"}
        self.protocol_mode = mode_map.get(protocol_idx, "south")
        
        is_gdw = (self.protocol_mode == "gdw")
        is_dlt698 = (self.protocol_mode == "dlt698")
        is_south = (self.protocol_mode == "south")
        
        self._di_combo.set_visibility(is_south)
        self._afn_fn_combo.set_visibility(is_gdw)
        self._dlt698_select_row.set_visibility(is_dlt698)
        
        self._clear_form()
        self._preview_text.value = ""
    
    def _on_di_change(self, e):
        if not e.value:
            return
        key = e.value
        try:
            di3 = int(key[0:2], 16)
            di2 = int(key[2:4], 16)
            di1 = int(key[4:6], 16)
            di0 = int(key[6:8], 16)
            self._current_di_key = (di3, di2, di1, di0)
            self._build_form_from_schema([])
        except Exception:
            pass
    
    def _on_afn_fn_change(self, e):
        if not e.value:
            return
        key = e.value
        try:
            afn = int(key[0:2], 16)
            fn = int(key[2:4], 16)
            self._current_afn_fn = (afn, fn)
            self._build_form_from_schema([])
        except Exception:
            pass
    
    def _on_dlt698_apdu_change(self, e):
        if not e.value:
            return
        self._current_dlt698_key = (e.value, None)
        sub_options = OI_PRESET_LIST.get(e.value, {})
        self._dlt698_sub_combo.options = sub_options
        self._dlt698_sub_combo.update()
    
    def _on_dlt698_sub_change(self, e):
        if not e.value or not self._current_dlt698_key:
            return
        apdu_type = self._current_dlt698_key[0]
        self._current_dlt698_key = (apdu_type, e.value)
        schema = DLT69845_FIELD_SCHEMA.get((apdu_type, e.value), [])
        self._build_form_from_schema(schema)
    
    def _build_form_from_schema(self, schema: List[Dict]):
        """根据 Schema 动态构建表单字段"""
        self._clear_form()
        
        for field_def in schema:
            name = field_def["name"]
            ftype = field_def.get("type", "uint8")
            default = field_def.get("default", "")
            options = field_def.get("options", {})
            
            with self._form_container:
                with ui.row().classes("w-full q-gutter-sm items-center q-mb-xs"):
                    ui.label(f"{name}:").classes("text-sm").style("min-width: 140px;")
                    
                    if options:
                        widget = ui.select(
                            options=options,
                            value=default,
                        ).props("dense outlined").classes("flex-grow")
                    elif ftype == "bool":
                        widget = ui.checkbox(value=bool(default)).props("dense")
                    else:
                        widget = ui.input(value=str(default), placeholder=f"{ftype}").props("dense outlined").classes("flex-grow")
                    
                    self._field_widgets[name] = {
                        "widget": widget,
                        "type": ftype,
                    }
    
    def _clear_form(self):
        self._form_container.clear()
        self._field_widgets = {}
    
    def _generate_preview(self):
        ui.notify("生成预览功能待实现 (需集成 send_frame_lib/gdw_send_frame_lib)", type="info")
    
    def _send_frame(self):
        hex_text = self._preview_text.value
        if not hex_text.strip():
            ui.notify("先生成预览", type="warning")
            return
        ui.clipboard.write(hex_text.replace(" ", ""))
        ui.notify("帧数据已复制到剪贴板", type="positive")
    
    def _add_to_preset(self):
        ui.notify("添加到预设待实现", type="info")
    
    def _add_to_test(self):
        ui.notify("添加到测试方案待实现", type="info")
    
    def _export_json(self):
        import json
        field_values = {}
        for name, info in self._field_widgets.items():
            val = info["widget"].value
            if val is not None and val != "":
                field_values[name] = val
        data = {
            "protocol_mode": self.protocol_mode,
            "di_key": self._current_di_key,
            "afn_fn": self._current_afn_fn,
            "dlt698_key": self._current_dlt698_key,
            "field_values": field_values,
            "frame_config": {
                "src_addr": self._src_addr.value,
                "dst_addr": self._dst_addr.value,
                "seq": self._seq_input.value,
                "direction": self._dir_select.value,
                "prm": self._prm_select.value,
            },
        }
        ui.download(json.dumps(data, ensure_ascii=False, indent=2).encode(), "frame_config.json")
        ui.notify("已导出配置", type="positive")
    
    def _show_cmd_help(self):
        if self.protocol_mode == "south" and self._current_di_key:
            di3, di2, di1, di0 = self._current_di_key
            try:
                from protocol_parser import ProtocolFrameParser
                parser = ProtocolFrameParser()
                desc = parser.DI_COMBINATION_MAP.get((di3, di2, di1, di0), "无说明")
                with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 500px; max-width: 800px;"):
                    ui.label(f"DI: {di3:02X}{di2:02X}{di1:02X}{di0:02X}").classes("text-h6 q-mb-md")
                    ui.label(desc).classes("q-mb-md")
                    ui.button("关闭", on_click=dialog.close).props("dense color=primary")
                dialog.open()
            except Exception:
                pass
        elif self.protocol_mode == "gdw" and self._current_afn_fn:
            afn, fn = self._current_afn_fn
            try:
                from gdw10376_parser import GDW10376Parser
                parser = GDW10376Parser()
                afn_name = parser.AFN_MAP.get(afn, f"未知({afn:02X})")
                fn_map = parser.FN_MAP.get(afn, {})
                fn_name = fn_map.get(fn, f"未知({fn:02X})")
                with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 500px;"):
                    ui.label(f"AFN={afn:02X} {afn_name} / Fn={fn:02X} {fn_name}").classes("text-h6 q-mb-md")
                    ui.button("关闭", on_click=dialog.close).props("dense color=primary")
                dialog.open()
            except Exception:
                pass
