# -*- coding: utf-8 -*-
"""测试方案标签页"""
from nicegui import ui
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from test_plan_widget import TEST_PLAN_PATH
from lua_script_engine import LuaScriptEngine, LUPA_AVAILABLE, LUA_TEMPLATES


class TestPlanTab:
    def __init__(self, protocol_selector, serial_panel):
        self.protocol_selector = protocol_selector
        self.serial_panel = serial_panel
        self.current_protocol = 0
        self._table = None
        self._items: List[Dict] = []
    
    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-sm"):
            # 标题栏
            with ui.row().classes("items-center q-gutter-sm q-mb-xs"):
                ui.icon("science", size="md", color="primary")
                ui.label("测试方案").classes("text-h6 text-weight-bold")
            
            ui.separator().classes("q-mb-sm")
            
            # 工具栏
            with ui.row().classes("w-full q-gutter-sm items-center"):
                ui.button("", icon="add_circle", on_click=self._add_item).props("flat round color=primary").tooltip("新建测试项")
                ui.button("", icon="upload", on_click=self._import_json).props("flat round color=grey-7").tooltip("导入")
                ui.button("", icon="download", on_click=self._export_json).props("flat round color=grey-7").tooltip("导出")
                ui.space()
                ui.button("", icon="play_arrow", on_click=self._run_sequence).props("flat round color=positive").tooltip("顺序发送")
                ui.button("", icon="stop", on_click=self._stop_sequence).props("flat round color=negative").tooltip("停止")
            
            ui.separator().classes("q-mb-sm")
            
            # 表格
            columns = [
                {"name": "enabled", "label": "启用", "field": "enabled", "width": "50px", "align": "center"},
                {"name": "type", "label": "性质", "field": "type", "width": "100px"},
                {"name": "name", "label": "名称", "field": "name"},
                {"name": "frame", "label": "报文", "field": "frame"},
                {"name": "match", "label": "匹配规则", "field": "match"},
                {"name": "timeout", "label": "超时(ms)", "field": "timeout", "width": "80px"},
                {"name": "result", "label": "结果", "field": "result", "width": "80px"},
                {"name": "actions", "label": "操作", "field": "actions", "width": "120px"},
            ]
            
            with ui.card().classes("w-full h-[calc(100%-120px)] shadow-md rounded-borders"):
                
                # 自定义单元格渲染
                self._table.add_slot('body-cell-type', '''
                    <q-td :props="props">
                        <q-select
                            :value="props.row.type"
                            :options="['发送帧', '等待响应', 'Lua脚本', '延时', '断言']"
                            @update:model-value="val => $parent.$emit('updateType', props.row.id, val)"
                            dense outlined borderless
                            style="min-width: 100px;"
                        />
                    </q-td>
                ''')
                
                self._table.add_slot('body-cell-actions', '''
                    <q-td :props="props">
                        <q-btn dense flat round size="sm" icon="edit" @click="$parent.$emit('editRow', props.row.id)" />
                        <q-btn dense flat round size="sm" icon="delete" @click="$parent.$emit('deleteRow', props.row.id)" color="negative" />
                        <q-btn dense flat round size="sm" icon="content_copy" @click="$parent.$emit('copyRow', props.row.id)" />
                    </q-td>
                ''')
                
                # 事件监听
                self._table.on('updateType', self._on_type_change)
                self._table.on('editRow', self._on_edit_row)
                self._table.on('deleteRow', self._on_delete_row)
                self._table.on('copyRow', self._on_copy_row)
            
            # 加载数据
            self._load_data()
    
    def on_protocol_change(self, protocol_idx: int):
        self.current_protocol = protocol_idx
        self._load_data()
    
    def _load_data(self):
        if TEST_PLAN_PATH.exists():
            try:
                with open(TEST_PLAN_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._items = data.get("items", [])
            except Exception:
                self._items = []
        else:
            self._items = []
        
        # 转换为表格行
        rows = []
        for idx, item in enumerate(self._items):
            rows.append({
                "id": item.get("id", idx),
                "enabled": item.get("enabled", True),
                "type": item.get("type", "发送帧"),
                "name": item.get("name", f"测试项{idx+1}"),
                "frame": item.get("frame", ""),
                "match": item.get("match", ""),
                "timeout": item.get("timeout", 2000),
                "result": item.get("result", "待测试"),
                "actions": "",
            })
        self._table.rows = rows
    
    def _save_data(self):
        data = {"items": self._items}
        with open(TEST_PLAN_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _add_item(self):
        new_id = max([i.get("id", 0) for i in self._items], default=-1) + 1
        item = {
            "id": new_id,
            "enabled": True,
            "type": "发送帧",
            "name": f"测试项{new_id+1}",
            "frame": "",
            "match": "",
            "timeout": 2000,
            "result": "待测试",
        }
        self._items.append(item)
        self._table.add_rows([{
            "id": new_id,
            "enabled": True,
            "type": "发送帧",
            "name": item["name"],
            "frame": "",
            "match": "",
            "timeout": 2000,
            "result": "待测试",
            "actions": "",
        }])
        self._save_data()
    
    def _on_type_change(self, e):
        row_id, new_type = e.args
        for item in self._items:
            if item.get("id") == row_id:
                item["type"] = new_type
                break
        self._save_data()
    
    def _on_edit_row(self, e):
        row_id = e.args
        item = next((i for i in self._items if i.get("id") == row_id), None)
        if not item:
            return
        
        if item["type"] == "Lua脚本":
            self._open_lua_editor(item)
        else:
            self._open_generic_editor(item)
    
    def _open_lua_editor(self, item: Dict):
        if not LUPA_AVAILABLE:
            ui.notify("Lua 功能不可用 (需安装 lupa)", type="warning")
            return
        
        with ui.dialog() as dialog, ui.card().classes("q-pa-md shadow-md rounded-borders").style("min-width: 800px; max-width: 1000px;"):
            ui.label(f"编辑 Lua 脚本: {item['name']}").classes("text-h6 q-mb-md")
            
            # 模板选择
            with ui.row().classes("q-gutter-sm q-mb-md"):
                ui.label("模板:").classes("text-weight-bold")
                template_select = ui.select(
                    options={k: v["description"] for k, v in LUA_TEMPLATES.items()},
                    value=None,
                    on_change=lambda e: self._apply_lua_template(e.value, editor),
                ).props("dense outlined").classes("w-64")
            
            # Monaco 编辑器
            editor = ui.codemirror(
                value=item.get("lua_script", ""),
                language="lua",
                theme="basicDark",
            ).classes("w-full").style("height: 400px; font-size: 13px;")
            
            with ui.row().classes("q-mt-md q-gutter-sm justify-end"):
                ui.button("取消", on_click=dialog.close).props("dense outline")
                ui.button("保存", on_click=lambda: self._save_lua_script(item, editor, dialog)).props("dense color=primary")
        
        dialog.open()
    
    def _apply_lua_template(self, template_key: str, editor):
        if template_key and template_key in LUA_TEMPLATES:
            editor.value = LUA_TEMPLATES[template_key]["code"]
            editor.update()
    
    def _save_lua_script(self, item: Dict, editor, dialog):
        item["lua_script"] = editor.value
        item["type"] = "Lua脚本"
        self._save_data()
        self._load_data()
        dialog.close()
        ui.notify("Lua 脚本已保存", type="positive")
    
    def _open_generic_editor(self, item: Dict):
        with ui.dialog() as dialog, ui.card().classes("q-pa-md shadow-md rounded-borders").style("min-width: 500px;"):
            ui.label(f"编辑: {item['name']}").classes("text-h6 q-mb-md")
            
            name_input = ui.input(label="名称", value=item["name"]).props("dense outlined").classes("w-full q-mb-sm")
            type_select = ui.select(
                label="性质",
                options=["发送帧", "等待响应", "Lua脚本", "延时", "断言"],
                value=item["type"],
            ).props("dense outlined").classes("w-full q-mb-sm")
            
            if item["type"] in ("发送帧", "等待响应"):
                frame_input = ui.textarea(label="报文 (HEX)", value=item["frame"]).props("dense outlined rows=3").classes("w-full q-mb-sm")
                match_input = ui.input(label="匹配规则 (HEX, XX为通配)", value=item["match"]).props("dense outlined").classes("w-full q-mb-sm")
                timeout_input = ui.number(label="超时(ms)", value=item["timeout"], min=100, max=60000).props("dense outlined").classes("w-full q-mb-sm")
            elif item["type"] == "延时":
                delay_input = ui.number(label="延时(ms)", value=item.get("delay", 1000), min=1).props("dense outlined").classes("w-full q-mb-sm")
            elif item["type"] == "断言":
                assert_input = ui.textarea(label="断言表达式", value=item.get("assertion", "")).props("dense outlined rows=3").classes("w-full q-mb-sm")
            
            with ui.row().classes("q-gutter-sm justify-end"):
                ui.button("取消", on_click=dialog.close).props("dense outline")
                ui.button("保存", on_click=lambda: self._save_generic_item(item, {
                    "name": name_input,
                    "type": type_select,
                    "frame": frame_input if item["type"] in ("发送帧", "等待响应") else None,
                    "match": match_input if item["type"] in ("发送帧", "等待响应") else None,
                    "timeout": timeout_input if item["type"] in ("发送帧", "等待响应") else None,
                    "delay": delay_input if item["type"] == "延时" else None,
                    "assertion": assert_input if item["type"] == "断言" else None,
                }, dialog)).props("dense color=primary")
        
        dialog.open()
    
    def _save_generic_item(self, item: Dict, inputs: Dict, dialog):
        item["name"] = inputs["name"].value
        item["type"] = inputs["type"].value
        if inputs["frame"]:
            item["frame"] = inputs["frame"].value
        if inputs["match"]:
            item["match"] = inputs["match"].value
        if inputs["timeout"]:
            item["timeout"] = inputs["timeout"].value
        if inputs["delay"]:
            item["delay"] = inputs["delay"].value
        if inputs["assertion"]:
            item["assertion"] = inputs["assertion"].value
        
        self._save_data()
        self._load_data()
        dialog.close()
        ui.notify("已保存", type="positive")
    
    def _on_delete_row(self, e):
        row_id = e.args
        self._items = [i for i in self._items if i.get("id") != row_id]
        self._table.remove_rows([row_id])
        self._save_data()
        ui.notify("已删除", type="positive")
    
    def _on_copy_row(self, e):
        row_id = e.args
        item = next((i for i in self._items if i.get("id") == row_id), None)
        if item:
            new_item = item.copy()
            new_item["id"] = max([i.get("id", 0) for i in self._items], default=-1) + 1
            new_item["name"] += " (副本)"
            self._items.append(new_item)
            self._load_data()
            self._save_data()
            ui.notify("已复制", type="positive")
    
    def _import_json(self):
        ui.notify("导入功能待实现", type="info")
    
    def _export_json(self):
        ui.download(json.dumps({"items": self._items}, ensure_ascii=False, indent=2).encode(), "test_plan.json")
        ui.notify("已导出", type="positive")
    
    def _run_sequence(self):
        ui.notify("顺序发送测试待实现 (需串口适配器)", type="info")
    
    def _stop_sequence(self):
        ui.notify("停止测试", type="warning")
