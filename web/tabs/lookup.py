# -*- coding: utf-8 -*-
"""查询标签页：DI/AFN/OBIS/命令字/业务标识搜索表格"""
from nicegui import ui
from typing import List, Dict, Any, Optional
from protocol_parser import ProtocolFrameParser
from gdw10376_parser import GDW10376Parser
from obis_lookup import get_obis_lookup
from command_lookup import get_command_lookup
from dlt645_di_lookup import get_dlt645_di_lookup
from gdw_afn_lookup import get_gdw_afn_lookup
from csg_new_gen_parser import (
    FRAME_TYPE_MAP, MSDU_TYPE_MAP, CMD_FUNC_SERVICE_MAP, 
    CMD_COMM_SERVICE_MAP, DATA_SERVICE_MAP, CONFIRM_SERVICE_MAP
)


class LookupTab:
    def __init__(self, protocol_selector):
        self.protocol_selector = protocol_selector
        self.current_protocol = 0
        self._search_input = None
        self._table = None
        self._data = []
        self._stats_label = None
    
    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 搜索栏
            with ui.card().classes("w-full rounded-xl shadow-md"):
                with ui.row().classes("w-full q-pa-sm q-gutter-sm items-center"):
                    ui.icon("search", size="sm", color="grey-6")
                    self._search_input = ui.input(
                        placeholder="输入关键词搜索 (DI编码/中文/十六进制)...",
                        on_change=self._filter_table,
                    ).classes("flex-grow").props("dense outlined clearable")
                    
                    self._stats_label = ui.badge(
                        "0 条记录",
                        color="blue-grey-7",
                        text_color="white",
                    ).classes("text-xs")
                    
                    ui.button(icon="refresh", on_click=self._load_data).props(
                        'flat round dense color="grey-6"'
                    ).tooltip("刷新数据")
            
            # 表格
            with ui.card().classes("w-full h-[calc(100%-100px)] rounded-xl shadow-md"):
                with ui.row().classes("w-full items-center q-pa-sm q-px-md bg-blue-grey-1"):
                    ui.icon("data_usage", size="sm", color="blue-grey-8")
                    ui.label("查询结果").classes("text-weight-bold text-blue-grey-8 text-sm")
                columns = [
                    {"name": "col1", "label": "字段1", "field": "col1", "align": "left"},
                    {"name": "col2", "label": "字段2", "field": "col2", "align": "left"},
                    {"name": "col3", "label": "字段3", "field": "col3", "align": "left"},
                    {"name": "col4", "label": "字段4", "field": "col4", "align": "left"},
                    {"name": "col5", "label": "AFN/类型", "field": "col5", "align": "left"},
                    {"name": "desc", "label": "中文含义", "field": "desc", "align": "left"},
                ]
                self._table = ui.table(
                    columns=columns,
                    rows=[],
                    row_key="id",
                ).classes("dense-table w-full").props("flat bordered separator=cell virtual-scroll")
    
    def on_protocol_change(self, protocol_idx: int):
        self.current_protocol = protocol_idx
        self._load_data()
    
    def _load_data(self):
        """根据协议加载查询数据"""
        self._data = []
        
        if self.current_protocol == 0:  # 南网 DI
            self._load_nw_di()
        elif self.current_protocol == 1:  # PLC RF 命令字
            self._load_plc_rf_commands()
        elif self.current_protocol in (2, 3, 4, 5):  # HDLC/DLMS OBIS
            self._load_obis()
        elif self.current_protocol == 6:  # DLT645 DI
            self._load_dlt645_di()
        elif self.current_protocol == 7:  # 国网 AFN+Fn
            self._load_gdw_afn_fn()
        elif self.current_protocol == 8:  # 698.45 OI
            self._load_69845_oi()
        elif self.current_protocol == 9:  # 新一代载波 业务标识
            self._load_csg_service_id()
        
        self._table.rows = self._data
        self._update_stats()
    
    def _load_nw_di(self):
        parser = ProtocolFrameParser()
        custom_list = ProtocolFrameParser.load_custom_di_list()
        custom_keys = {(e["di3"], e["di2"], e["di1"], e["di0"]) for e in custom_list}
        
        for (di3, di2, di1, di0), desc in parser.DI_COMBINATION_MAP.items():
            afn_val = di1
            afn_name = parser.AFN_MAP.get(afn_val, f"未知({afn_val:02X})")
            is_custom = (di3, di2, di1, di0) in custom_keys
            self._data.append({
                "id": f"{di3:02X}{di2:02X}{di1:02X}{di0:02X}",
                "col1": f"{di3:02X}",
                "col2": f"{di2:02X}",
                "col3": f"{di1:02X}",
                "col4": f"{di0:02X}",
                "col5": f"{afn_val:02X}H {afn_name}",
                "desc": ("★ " if is_custom else "") + desc,
            })
        self._table.columns = [
            {"name": "col1", "label": "DI3", "field": "col1", "align": "left"},
            {"name": "col2", "label": "DI2", "field": "col2", "align": "left"},
            {"name": "col3", "label": "DI1", "field": "col3", "align": "left"},
            {"name": "col4", "label": "DI0", "field": "col4", "align": "left"},
            {"name": "col5", "label": "AFN", "field": "col5", "align": "left"},
            {"name": "desc", "label": "中文含义", "field": "desc", "align": "left"},
        ]
    
    def _load_plc_rf_commands(self):
        lookup = get_command_lookup()
        for cmd, desc in lookup.cmd_map.items():
            self._data.append({
                "id": f"{cmd:04X}",
                "col1": f"{cmd:04X}",
                "col2": "",
                "col3": "",
                "col4": "",
                "col5": "",
                "desc": desc,
            })
        self._table.columns = [
            {"name": "col1", "label": "命令字", "field": "col1", "align": "left"},
            {"name": "desc", "label": "说明", "field": "desc", "align": "left"},
        ]
    
    def _load_obis(self):
        lookup = get_obis_lookup()
        for obis, desc in lookup.obis_map.items():
            self._data.append({
                "id": obis.replace(".", ""),
                "col1": obis,
                "col2": "",
                "col3": "",
                "col4": "",
                "col5": "",
                "desc": desc,
            })
        self._table.columns = [
            {"name": "col1", "label": "OBIS码", "field": "col1", "align": "left"},
            {"name": "desc", "label": "说明", "field": "desc", "align": "left"},
        ]
    
    def _load_dlt645_di(self):
        lookup = get_dlt645_di_lookup()
        for di, desc in lookup.di_map.items():
            self._data.append({
                "id": di.replace(" ", ""),
                "col1": di,
                "col2": "",
                "col3": "",
                "col4": "",
                "col5": "",
                "desc": desc,
            })
        self._table.columns = [
            {"name": "col1", "label": "DI标识", "field": "col1", "align": "left"},
            {"name": "desc", "label": "说明", "field": "desc", "align": "left"},
        ]
    
    def _load_gdw_afn_fn(self):
        parser = GDW10376Parser()
        for afn, fn_map in parser.FN_MAP.items():
            afn_name = parser.AFN_MAP.get(afn, f"未知({afn:02X})")
            for fn, fn_name in fn_map.items():
                self._data.append({
                    "id": f"{afn:02X}{fn:02X}",
                    "col1": f"{afn:02X}",
                    "col2": f"{fn:02X}",
                    "col3": "",
                    "col4": "",
                    "col5": f"{afn:02X}H {afn_name}",
                    "desc": f"Fn={fn:02X} {fn_name}",
                })
        self._table.columns = [
            {"name": "col1", "label": "AFN", "field": "col1", "align": "left"},
            {"name": "col2", "label": "Fn", "field": "col2", "align": "left"},
            {"name": "col5", "label": "AFN名称", "field": "col5", "align": "left"},
            {"name": "desc", "label": "Fn名称", "field": "desc", "align": "left"},
        ]
    
    def _load_69845_oi(self):
        from dl_t698_45_oi_lookup import OILookup
        lookup = OILookup()
        for oi, name in lookup.OI_NAME_MAP.items():
            self._data.append({
                "id": oi.replace(".", ""),
                "col1": oi,
                "col2": "",
                "col3": "",
                "col4": "",
                "col5": "",
                "desc": name,
            })
        self._table.columns = [
            {"name": "col1", "label": "OI标识", "field": "col1", "align": "left"},
            {"name": "desc", "label": "对象名称", "field": "desc", "align": "left"},
        ]
    
    def _load_csg_service_id(self):
        """新一代载波业务标识"""
        # 帧类型
        for ft, name in FRAME_TYPE_MAP.items():
            self._data.append({"id": f"FT{ft:02X}", "col1": f"0x{ft:02X}", "col2": "", "col3": "", "col4": "", "col5": "帧类型", "desc": name})
        # MSDU类型
        for mt, name in MSDU_TYPE_MAP.items():
            self._data.append({"id": f"MT{mt:04X}", "col1": f"0x{mt:04X}", "col2": "", "col3": "", "col4": "", "col5": "MSDU类型", "desc": name})
        # 确认/否认
        for sid, name in CONFIRM_SERVICE_MAP.items():
            self._data.append({"id": f"CS{sid:02X}", "col1": f"0x{sid:02X}", "col2": "", "col3": "", "col4": "", "col5": "确认/否认", "desc": name})
        # 数据传输
        for sid, name in DATA_SERVICE_MAP.items():
            self._data.append({"id": f"DS{sid:02X}", "col1": f"0x{sid:02X}", "col2": "", "col3": "", "col4": "", "col5": "数据传输", "desc": name})
        # 命令帧-功能性
        for sid, name in CMD_FUNC_SERVICE_MAP.items():
            self._data.append({"id": f"CF{sid:02X}", "col1": f"0x{sid:02X}", "col2": "", "col3": "", "col4": "", "col5": "命令-功能", "desc": name})
        # 命令帧-通信管理
        for sid, name in CMD_COMM_SERVICE_MAP.items():
            self._data.append({"id": f"CC{sid:02X}", "col1": f"0x{sid:02X}", "col2": "", "col3": "", "col4": "", "col5": "命令-通信", "desc": name})
        
        self._table.columns = [
            {"name": "col1", "label": "标识值", "field": "col1", "align": "left"},
            {"name": "col5", "label": "分类", "field": "col5", "align": "left"},
            {"name": "desc", "label": "业务名称", "field": "desc", "align": "left"},
        ]
    
    def _filter_table(self, e):
        keyword = (e.value or "").strip().upper()
        if not keyword:
            self._table.rows = self._data
        else:
            filtered = []
            for row in self._data:
                search_text = " ".join(str(v) for v in row.values()).upper()
                if keyword in search_text:
                    filtered.append(row)
            self._table.rows = filtered
        self._update_stats()
    
    def _update_stats(self):
        total = len(self._data)
        visible = len(self._table.rows)
        if visible == total:
            self._stats_label.set_text(f"共 {total} 条记录")
        else:
            self._stats_label.set_text(f"匹配 {visible} / {total} 条记录")