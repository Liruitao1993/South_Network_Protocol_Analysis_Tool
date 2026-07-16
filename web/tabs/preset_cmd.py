# -*- coding: utf-8 -*-
"""预设命令标签页"""
from nicegui import ui
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from preset_buttons import PresetButtonManager


class PresetCmdTab:
    def __init__(self, protocol_selector, serial_panel):
        self.protocol_selector = protocol_selector
        self.serial_panel = serial_panel
        self.current_protocol = 0
        self._protocol_mode = "south"
        self._container = None
        self._search_input = None
        self._all_commands = []
    
    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 搜索栏
            with ui.row().classes("w-full q-gutter-sm items-center"):
                ui.label("搜索：").classes("text-weight-bold")
                self._search_input = ui.input(
                    placeholder="输入按钮名称/分组/描述搜索...",
                    on_change=self._filter_buttons,
                ).classes("flex-grow").props("dense outlined clearable prepend-icon='search'")
            
            # 按钮容器 (滚动区域)
            with ui.scroll_area().classes("w-full h-[calc(100%-80px)]"):
                self._container = ui.column().classes("w-full q-gutter-sm q-pa-sm")
            
            # 加载数据
            self._load_presets()
    
    def on_protocol_change(self, protocol_idx: int):
        self.current_protocol = protocol_idx
        self._protocol_mode = "gdw" if protocol_idx == 7 else "south"
        self._load_presets()
    
    def _load_presets(self):
        self._container.clear()
        self._all_commands = PresetButtonManager.load_commands(self._protocol_mode)
        keyword = self._search_input.value.strip().lower() if self._search_input and self._search_input.value else ""
        commands = self._all_commands
        if keyword:
            commands = [c for c in commands if keyword in c.get("name", "").lower()
                        or keyword in c.get("group", "").lower()
                        or keyword in c.get("desc", "").lower()
                        or keyword in c.get("frame", "").lower()]
        
        # 按分组渲染
        groups = {}
        for cmd in commands:
            group = cmd.get("group", "未分组")
            groups.setdefault(group, []).append(cmd)
        
        for group_name, cmds in groups.items():
            with self._container:
                with ui.expansion(group_name, icon="folder").classes("w-full shadow-md rounded-borders").props("dense"):
                    with ui.row().classes("w-full q-gutter-sm flex-wrap"):
                        for cmd in cmds:
                            self._create_preset_button(cmd)
    
    def _create_preset_button(self, cmd: Dict):
        btn = ui.button(
            cmd.get("name", "未命名"),
            on_click=lambda c=cmd: self._on_button_click(c),
        ).props("dense no-caps align=left").classes("w-48 h-24").style("white-space: normal; text-align: left;")
        
        # 右键菜单
        with ui.menu() as menu:
            ui.menu_item("发送该帧", lambda c=cmd: self._send_frame(c), icon="flash_on")
            ui.menu_item("编辑", lambda c=cmd: self._edit_preset(c), icon="edit")
            ui.menu_item("删除", lambda c=cmd: self._delete_preset(c), icon="delete")
            ui.menu_item("复制报文", lambda c=cmd: self._copy_frame(c), icon="content_copy")
        
        btn.on('contextmenu', lambda e, m=menu: m.open(e))
        
        # Tooltip 显示描述和报文
        desc = cmd.get("desc", "")
        frame = cmd.get("frame", "")
        btn.tooltip(f"{desc}\n\n{frame[:100]}...")
    
    def _on_button_click(self, cmd: Dict):
        frame_hex = cmd.get("frame", "")
        if frame_hex:
            ui.notify(f"点击预设: {cmd['name']}", type="info")
    
    def _send_frame(self, cmd: Dict):
        frame_hex = cmd.get("frame", "")
        if frame_hex:
            ui.notify(f"发送: {frame_hex[:32]}...", type="positive")
    
    def _edit_preset(self, cmd: Dict):
        ui.notify("编辑功能待实现", type="info")
    
    def _delete_preset(self, cmd: Dict):
        cmd_id = cmd.get("id")
        if cmd_id and PresetButtonManager.remove_command(self._protocol_mode, cmd_id):
            self._load_presets()
            ui.notify("已删除", type="positive")
        else:
            ui.notify("删除失败", type="negative")
    
    def _copy_frame(self, cmd: Dict):
        frame_hex = cmd.get("frame", "")
        if frame_hex:
            ui.clipboard.write(frame_hex)
            ui.notify("报文已复制到剪贴板", type="positive")
    
    def _filter_buttons(self, e):
        self._load_presets()
