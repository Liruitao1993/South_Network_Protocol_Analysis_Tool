# NiceGUI Web版南网协议解析工具 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 NiceGUI 开发 Web 版南网协议解析工具，完整复刻现有 PySide6 桌面端所有功能（10个协议、9大标签页），支持 PyInstaller 单文件 EXE 部署。

**Architecture:** NiceGUI 单体应用，直接复用现有解析器/验证器/组帧器/Diff引擎/Lua引擎/串口模块，零修改核心逻辑。UI 层用 Quasar 组件 (ui.table, ui.tabs, ui.dialog 等) 替换 PySide6 控件，通过 Tailwind 类定制样式逼近桌面端交互。

**Tech Stack:** Python 3.8+, NiceGUI 1.4+, Quasar (内置), PyInstaller, 现有项目所有 parser/validator/generator 模块

---

## 文件结构规划

```
web_app.py                          # 入口文件
web/
├── __init__.py
├── main_page.py                    # 主布局、协议选择器、标签页路由
├── components/
│   ├── __init__.py
│   ├── protocol_selector.py        # 协议下拉框 + 新一代载波解析级别 + 字节剔除
│   ├── hex_input.py                # 十六进制输入框 (清洗/验证/占位符)
│   ├── parse_table.py              # 解析结果表格 (高亮/双击/右键菜单)
│   ├── byte_highlighter.py         # 字节高亮工具类
│   └── serial_panel.py             # 串口状态面板 (端口/波特率/打开按钮)
├── tabs/
│   ├── __init__.py
│   ├── single_parse.py             # 单帧解析
│   ├── lookup.py                   # 查询 (DI/AFN/OBIS/命令字/业务标识)
│   ├── batch_parse.py              # 批量解析
│   ├── frame_gen.py                # 协议组帧 (动态表单 Schema驱动)
│   ├── preset_cmd.py               # 预设命令 (分组按钮)
│   ├── test_plan.py                # 测试方案 (CRUD + 顺序发送 + Lua编辑器)
│   ├── archive.py                  # 档案管理
│   ├── topology.py                 # 拓扑信息
│   └── diff.py                     # 报文对比
├── styles/
│   └── custom.css                  # 紧凑表格、深色表头、行高、字节高亮类
└── adapters/
    ├── __init__.py
    └── serial_adapter.py           # SerialWorker → asyncio 适配器
web_app.spec                        # PyInstaller 配置
```

---

## 任务分解

### Phase 0: 基础设施与入口

#### Task 0.1: 创建项目骨架与入口文件

**Files:**
- Create: `web_app.py`
- Create: `web/__init__.py`
- Create: `web/main_page.py`
- Create: `web/components/__init__.py`
- Create: `web/tabs/__init__.py`
- Create: `web/styles/custom.css`
- Create: `web/adapters/__init__.py`

- [ ] **Step 1: 写入 web_app.py 入口**

```python
# web_app.py
"""南网协议解析工具 - NiceGUI Web版入口"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from nicegui import ui, app
from web.main_page import MainPage


def main():
    """应用入口"""
    # 全局样式
    ui.add_head_html('<link rel="preconnect" href="https://fonts.googleapis.com">')
    ui.add_head_html('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    ui.add_head_html('<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Microsoft+YaHei:wght@400;500;700&display=swap" rel="stylesheet">')
    
    # 加载自定义 CSS
    css_path = ROOT / "web" / "styles" / "custom.css"
    if css_path.exists():
        ui.add_css(css_path.read_text(encoding="utf-8"))
    
    # 创建主页面
    main_page = MainPage()
    main_page.build()
    
    # 运行
    ui.run(
        title="南网协议解析工具",
        native=False,  # Web模式
        port=8080,
        show=True,
        reload=False,
        favicon="🔌",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
```

- [ ] **Step 2: 写入 web/main_page.py 主布局框架**

```python
# web/main_page.py
"""主页面布局：顶部栏 + 标签页容器"""
from nicegui import ui
from web.components.protocol_selector import ProtocolSelector
from web.components.serial_panel import SerialPanel


class MainPage:
    def __init__(self):
        self.protocol_selector = ProtocolSelector()
        self.serial_panel = SerialPanel()
        self.tabs = {}
    
    def build(self):
        # 顶部栏
        with ui.header().classes("bg-primary text-white q-pa-sm q-gutter-sm items-center").style("height: 56px; min-height: 56px;"):
            ui.label("🔌 南网协议解析工具").classes("text-h6 font-weight-bold q-mr-md")
            self.protocol_selector.build()
            ui.space()
            self.serial_panel.build()
        
        # 主标签页容器
        with ui.tabs().classes("w-full") as self.tab_bar:
            self.tab_single = ui.tab("单帧解析", icon="list_alt")
            self.tab_lookup = ui.tab("查询", icon="search")
            self.tab_batch = ui.tab("批量解析", icon="description")
            self.tab_frame_gen = ui.tab("协议组帧", icon="build")
            self.tab_preset = ui.tab("预设命令", icon="widgets")
            self.tab_test = ui.tab("测试方案", icon="science")
            self.tab_archive = ui.tab("档案管理", icon="archive")
            self.tab_topo = ui.tab("拓扑信息", icon="account_tree")
            self.tab_diff = ui.tab("报文对比", icon="compare_arrows")
        
        with ui.tab_panels(self.tab_bar, value=self.tab_single).classes("w-full h-[calc(100vh-56px)]"):
            # 各标签页延迟导入构建，避免循环依赖
            with ui.tab_panel(self.tab_single):
                from web.tabs.single_parse import SingleParseTab
                SingleParseTab(self.protocol_selector).build()
            
            with ui.tab_panel(self.tab_lookup):
                from web.tabs.lookup import LookupTab
                LookupTab(self.protocol_selector).build()
            
            with ui.tab_panel(self.tab_batch):
                from web.tabs.batch_parse import BatchParseTab
                BatchParseTab(self.protocol_selector).build()
            
            with ui.tab_panel(self.tab_frame_gen):
                from web.tabs.frame_gen import FrameGenTab
                FrameGenTab(self.protocol_selector, self.serial_panel).build()
            
            with ui.tab_panel(self.tab_preset):
                from web.tabs.preset_cmd import PresetCmdTab
                PresetCmdTab(self.protocol_selector, self.serial_panel).build()
            
            with ui.tab_panel(self.tab_test):
                from web.tabs.test_plan import TestPlanTab
                TestPlanTab(self.protocol_selector, self.serial_panel).build()
            
            with ui.tab_panel(self.tab_archive):
                from web.tabs.archive import ArchiveTab
                ArchiveTab(self.protocol_selector, self.serial_panel).build()
            
            with ui.tab_panel(self.tab_topo):
                from web.tabs.topology import TopologyTab
                TopologyTab(self.protocol_selector, self.serial_panel).build()
            
            with ui.tab_panel(self.tab_diff):
                from web.tabs.diff import DiffTab
                DiffTab(self.protocol_selector).build()
```

- [ ] **Step 3: 写入 web/styles/custom.css 核心样式**

```css
/* web/styles/custom.css */
/* === 紧凑表格 === */
.dense-table .q-table__row {
    min-height: 24px !important;
}
.dense-table .q-table__cell {
    padding: 2px 8px !important;
    font-size: 12px !important;
}
.dense-table .q-table__th {
    background-color: #2c3e50 !important;
    color: white !important;
    font-weight: 600 !important;
    padding: 4px 8px !important;
    font-size: 12px !important;
}
.dense-table .q-table__row:nth-child(even) {
    background-color: #f5f5f5 !important;
}
.dense-table .q-table__row--selected {
    background-color: #bbdefb !important;
}

/* === 字节高亮 === */
.byte-highlight {
    background-color: #fff3cd !important;
    font-weight: bold;
}
.byte-highlight-modified {
    background-color: #f8d7da !important;
}
.byte-highlight-added {
    background-color: #fff3cd !important;
}
.byte-highlight-deleted {
    background-color: #e2e3e5 !important;
    text-decoration: line-through;
}

/* === 十六进制输入框 === */
.hex-input .q-field__control {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
}

/* === 代码编辑器 (Lua) === */
.lua-editor .q-field__control {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
    line-height: 1.5 !important;
}

/* === 协议选择器下拉菜单宽度 === */
.protocol-select .q-menu {
    min-width: 320px !important;
}

/* === 卡片紧凑 === */
.compact-card .q-card__section {
    padding: 8px !important;
}

/* === 分割器 === */
.q-splitter__separator {
    background-color: #e0e0e0 !important;
}
```

- [ ] **Step 4: 写入 web/components/protocol_selector.py**

```python
# web/components/protocol_selector.py
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
    ]
    
    CSG_LEVELS = [
        ("自动识别", "auto"),
        ("FC+PB解析(完整MPDU)", "fc_pb"),
        ("FC+eFC解析", "fc_efc"),
        ("仅FC解析", "fc_only"),
        ("应用层报文", "app"),
    ]
    
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
        self._csg_label = None
        self._strip_head_label = None
        self._strip_tail_label = None
    
    def build(self):
        with ui.row().classes("items-center q-gutter-sm"):
            ui.label("当前协议：").classes("text-weight-bold")
            
            self._select = ui.select(
                options={idx: name for name, idx in self.PROTOCOLS},
                value=self.current_protocol,
                on_change=self._on_protocol_change,
            ).classes("protocol-select w-64").props("dense outlined")
            
            # 新一代载波协议专用控件 (默认隐藏)
            self._csg_label = ui.label("解析级别：").classes("text-sm")
            self._csg_level_select = ui.select(
                options={v: k for k, v in self.CSG_LEVELS},
                value=self.current_csg_level,
                on_change=lambda e: setattr(self, 'current_csg_level', e.value),
            ).classes("w-48").props("dense outlined")
            
            self._strip_head_label = ui.label("剔除前:").classes("text-sm")
            self._strip_head_input = ui.number(
                value=0, min=0, max=999, step=1,
                on_change=lambda e: setattr(self, 'strip_head', e.value),
            ).classes("w-24").props("dense outlined suffix=' 字节'")
            
            self._strip_tail_label = ui.label("尾部:").classes("text-sm")
            self._strip_tail_input = ui.number(
                value=0, min=0, max=999, step=1,
                on_change=lambda e: setattr(self, 'strip_tail', e.value),
            ).classes("w-24").props("dense outlined suffix=' 字节'")
            
            # 初始隐藏
            self._toggle_csg_controls(False)
    
    def _on_protocol_change(self, e):
        self.current_protocol = e.value
        is_csg = (self.current_protocol == 9)
        self._toggle_csg_controls(is_csg)
        if self._on_change:
            self._on_change(self.current_protocol)
    
    def _toggle_csg_controls(self, visible: bool):
        for ctrl in [self._csg_label, self._csg_level_select, 
                     self._strip_head_label, self._strip_head_input,
                     self._strip_tail_label, self._strip_tail_input]:
            ctrl.set_visibility(visible)
```

- [ ] **Step 5: 写入 web/components/hex_input.py**

```python
# web/components/hex_input.py
"""十六进制输入框组件：清洗、验证、占位符示例"""
import re
from nicegui import ui
from typing import Optional, Callable, List


class HexInput:
    def __init__(
        self,
        placeholder: str = "请输入十六进制报文，支持空格/逗号/换行分隔，例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
        on_parse: Optional[Callable[[bytes], None]] = None,
        height: str = "100px",
    ):
        self.on_parse = on_parse
        self._textarea = None
        self._placeholder = placeholder
        self._height = height
        self._example_frames = {
            "确认帧": "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
            "复位硬件": "68 0C 00 40 01 00 01 01 02 E8 2D 16",
            "添加从节点": "68 1A 00 40 40 00 01 04 02 E8 02 AA AA AA AA BB BB BB BB 5C 16",
            "启动文件传输": "68 1C 00 40 07 00 01 07 02 E8 01 05 99 99 99 99 99 99 00 10 00 01 00 00 AB CD 0A 8F 16",
        }
    
    def build(self):
        with ui.column().classes("w-full q-gutter-xs"):
            self._textarea = ui.textarea(
                placeholder=self._placeholder,
            ).classes("hex-input w-full").props(f'dense rows=3 style="height: {self._height}; min-height: {self._height};"')
            
            # 示例按钮行
            with ui.row().classes("q-gutter-xs q-mt-xs"):
                for name, frame in self._example_frames.items():
                    ui.button(name, on_click=lambda f=frame: self.load_example(f)).props("dense outline size=sm")
                
                ui.space()
                ui.button("清空", on_click=self.clear).props("dense outline size=sm color=negative")
    
    def load_example(self, frame: str):
        self._textarea.value = frame
    
    def clear(self):
        self._textarea.value = ""
    
    def get_bytes(self) -> Optional[bytes]:
        """获取清洗后的字节数据，失败返回 None 并显示错误通知"""
        raw = self._textarea.value or ""
        if not raw.strip():
            ui.notify("请输入报文内容", type="warning")
            return None
        
        # 清洗：去除 0x 前缀、空格、逗号、换行、制表符
        clean = re.sub(r'0[xX]([0-9A-Fa-f])', r'\1', raw)  # 0xF -> F
        clean = re.sub(r'[^0-9A-Fa-f]', '', clean)
        
        if not clean:
            ui.notify("输入不包含有效十六进制字符", type="negative")
            return None
        
        if len(clean) % 2 != 0:
            ui.notify("十六进制字符串长度必须为偶数", type="negative")
            return None
        
        try:
            frame_bytes = bytes.fromhex(clean)
            if self.on_parse:
                self.on_parse(frame_bytes)
            return frame_bytes
        except ValueError as ex:
            ui.notify(f"十六进制解析失败: {ex}", type="negative")
            return None
    
    @property
    def value(self) -> str:
        return self._textarea.value or ""
    
    @value.setter
    def value(self, val: str):
        self._textarea.value = val
```

- [ ] **Step 6: 写入 web/components/parse_table.py**

```python
# web/components/parse_table.py
"""解析结果表格组件：高亮、双击提取APDU、右键菜单、导出图片"""
from nicegui import ui
from typing import List, Tuple, Optional, Callable, Dict, Any
import json


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
        with ui.column().classes("w-full"):
            # 工具栏
            with ui.row().classes("w-full q-mb-sm items-center justify-end"):
                ui.button("导出图片", icon="download", on_click=self._handle_export).props("dense flat")
            
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
            ).classes("dense-table w-full").props("flat bordered separator=cell virtual-scroll")
            
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
                ui.menu_item("复制字段名", lambda: self._copy_cell('field'))
                ui.menu_item("复制原始值", lambda: self._copy_cell('raw'))
                ui.menu_item("复制解析值", lambda: self._copy_cell('parsed'))
                ui.menu_item("复制说明", lambda: self._copy_cell('comment'))
                ui.separator()
                ui.menu_item("复制整行", self._copy_row)
                ui.menu_item("导出 JSON", self._export_json)
    
    def set_data(self, table_data: List[Tuple], frame_bytes: bytes = b''):
        """设置表格数据
        
        Args:
            table_data: [(field, raw, parsed, comment, byte_start, byte_end, is_child), ...]
            frame_bytes: 原始帧字节，用于字节高亮
        """
        self._rows_data = []
        self._byte_ranges = []
        
        for idx, row in enumerate(table_data):
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
    
    def highlight_bytes(self, frame_bytes: bytes, byte_ranges: List[Tuple[int, int]]):
        """高亮指定字节范围（需配合十六进制显示组件使用）"""
        # 此处留作扩展：可通过 CSS 类名映射实现
        pass
    
    def _on_row_click(self, e):
        """行单击：高亮字节 + 单击回调"""
        import time
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
    
    def _handle_export(self):
        if self.on_export_image:
            self.on_export_image()
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
```

- [ ] **Step 7: 写入 web/components/byte_highlighter.py**

```python
# web/components/byte_highlighter.py
"""字节高亮工具：生成带高亮标记的十六进制字符串"""
from typing import List, Tuple, Optional


class ByteHighlighter:
    """生成带 HTML 高亮标记的十六进制显示字符串"""
    
    @staticmethod
    def highlight_bytes(
        frame_bytes: bytes,
        highlight_ranges: List[Tuple[int, int]],
        bytes_per_line: int = 16,
        show_ascii: bool = True,
        show_offset: bool = True,
    ) -> str:
        """生成带高亮的十六进制字符串 (HTML)
        
        Args:
            frame_bytes: 原始帧字节
            highlight_ranges: 高亮范围列表 [(start, end), ...] 闭区间
            bytes_per_line: 每行字节数
            show_ascii: 是否显示 ASCII
            show_offset: 是否显示偏移地址
        """
        if not frame_bytes:
            return "<span style='color:#999'>(空数据)</span>"
        
        # 合并重叠范围
        merged = ByteHighlighter._merge_ranges(highlight_ranges)
        
        lines = []
        for i in range(0, len(frame_bytes), bytes_per_line):
            chunk = frame_bytes[i:i + bytes_per_line]
            line_parts = []
            
            if show_offset:
                line_parts.append(f"<span style='color:#666;font-family:monospace'>{i:04X}: </span>")
            
            # 十六进制部分
            hex_parts = []
            for j, b in enumerate(chunk):
                offset = i + j
                is_highlighted = any(start <= offset <= end for start, end in merged)
                cls = "byte-highlight" if is_highlighted else ""
                hex_parts.append(f"<span class='{cls}' style='font-family:monospace'>{b:02X}</span>")
            
            line_parts.append(" ".join(hex_parts))
            
            # ASCII 部分
            if show_ascii:
                ascii_parts = []
                for j, b in enumerate(chunk):
                    offset = i + j
                    is_highlighted = any(start <= offset <= end for start, end in merged)
                    cls = "byte-highlight" if is_highlighted else ""
                    char = chr(b) if 32 <= b <= 126 else "."
                    ascii_parts.append(f"<span class='{cls}' style='font-family:monospace'>{char}</span>")
                line_parts.append("  <span style='color:#666'>|</span>  " + "".join(ascii_parts))
            
            lines.append("".join(line_parts))
        
        return "<br>".join(lines)
    
    @staticmethod
    def _merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        if not ranges:
            return []
        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        merged = [sorted_ranges[0]]
        for start, end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + 1:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged
    
    @staticmethod
    def diff_highlight(
        bytes_a: bytes,
        bytes_b: bytes,
        bytes_per_line: int = 16,
    ) -> Tuple[str, str]:
        """生成两帧对比高亮 HTML (A基准, B对比)
        
        Returns:
            (html_a, html_b) - 两个高亮后的 HTML 字符串
        """
        max_len = max(len(bytes_a), len(bytes_b))
        lines_a = []
        lines_b = []
        
        for i in range(0, max_len, bytes_per_line):
            chunk_a = bytes_a[i:i + bytes_per_line]
            chunk_b = bytes_b[i:i + bytes_per_line]
            
            # 十六进制行
            hex_a = []
            hex_b = []
            for j in range(bytes_per_line):
                offset = i + j
                a_val = chunk_a[j] if j < len(chunk_a) else None
                b_val = chunk_b[j] if j < len(chunk_b) else None
                
                if a_val is not None and b_val is not None:
                    if a_val == b_val:
                        cls = ""
                    else:
                        cls = "byte-highlight-modified"
                elif a_val is None:
                    cls = "byte-highlight-added"
                else:
                    cls = "byte-highlight-deleted"
                
                hex_a.append(f"<span class='{cls}' style='font-family:monospace'>{a_val:02X if a_val is not None else '  '}</span>")
                hex_b.append(f"<span class='{cls}' style='font-family:monospace'>{b_val:02X if b_val is not None else '  '}</span>")
            
            lines_a.append(f"<span style='color:#666;font-family:monospace'>{i:04X}: </span>" + " ".join(hex_a))
            lines_b.append(f"<span style='color:#666;font-family:monospace'>{i:04X}: </span>" + " ".join(hex_b))
        
        return "<br>".join(lines_a), "<br>".join(lines_b)
```

- [ ] **Step 8: 写入 web/components/serial_panel.py**

```python
# web/components/serial_panel.py
"""串口状态面板：端口选择、波特率、打开/关闭"""
from nicegui import ui
from typing import Optional, Callable, List
import serial.tools.list_ports


class SerialPanel:
    def __init__(
        self,
        on_open: Optional[Callable[[str, int, str], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_refresh: Optional[Callable[[], None]] = None,
    ):
        self.on_open = on_open
        self.on_close = on_close
        self.on_refresh = on_refresh
        self._port_select = None
        self._baud_select = None
        self._parity_select = None
        self._open_btn = None
        self._status_label = None
        self._is_open = False
    
    def build(self):
        with ui.row().classes("items-center q-gutter-sm"):
            ui.label("串口:").classes("text-sm")
            
            self._port_select = ui.select(
                options=self._get_ports(),
                value=self._get_ports()[0] if self._get_ports() else None,
            ).classes("w-32").props("dense outlined")
            
            ui.button(icon="refresh", on_click=self._refresh_ports).props("dense flat round size=sm").tooltip("刷新串口列表")
            
            ui.label("波特率:").classes("text-sm")
            self._baud_select = ui.select(
                options=["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"],
                value="9600",
            ).classes("w-28").props("dense outlined")
            
            ui.label("校验:").classes("text-sm")
            self._parity_select = ui.select(
                options=["无", "偶", "奇"],
                value="无",
            ).classes("w-20").props("dense outlined")
            
            self._open_btn = ui.button(
                "打开串口",
                icon="toggle_on",
                on_click=self._toggle_port,
            ).props("dense color=positive").classes("q-ml-sm")
            
            self._status_label = ui.label("未连接").classes("text-sm text-grey-7")
    
    def _get_ports(self) -> List[str]:
        try:
            return [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            return ["COM1", "COM2", "COM3", "COM4"]
    
    def _refresh_ports(self):
        ports = self._get_ports()
        self._port_select.options = ports
        if ports:
            self._port_select.value = ports[0]
        self._port_select.update()
        if self.on_refresh:
            self.on_refresh()
    
    def _toggle_port(self):
        if not self._is_open:
            port = self._port_select.value
            baud = int(self._baud_select.value)
            parity_map = {"无": "N", "偶": "E", "奇": "O"}
            parity = parity_map.get(self._parity_select.value, "N")
            
            if port and self.on_open:
                self.on_open(port, baud, parity)
        else:
            if self.on_close:
                self.on_close()
    
    def set_connected(self, connected: bool, port: str = ""):
        self._is_open = connected
        if connected:
            self._open_btn.props(remove="color=positive", add="color=negative")
            self._open_btn.set_text("关闭串口")
            self._open_btn.set_icon("toggle_off")
            self._status_label.set_text(f"已连接: {port}")
            self._status_label.classes(remove="text-grey-7", add="text-green-7")
        else:
            self._open_btn.props(remove="color=negative", add="color=positive")
            self._open_btn.set_text("打开串口")
            self._open_btn.set_icon("toggle_on")
            self._status_label.set_text("未连接")
            self._status_label.classes(remove="text-green-7", add="text-grey-7")
```

- [ ] **Step 9: 写入 web/adapters/serial_adapter.py**

```python
# web/adapters/serial_adapter.py
"""SerialWorker (QThread) → asyncio 适配器
将现有串口线程桥接到 NiceGUI asyncio 事件循环
"""
import asyncio
import threading
from typing import Optional, Callable, Any
from queue import Queue, Empty
from serial_worker import SerialWorker


class SerialAdapter:
    """异步串口适配器：在后台线程运行 SerialWorker，通过 asyncio.Queue 与事件循环通信"""
    
    def __init__(self):
        self._worker: Optional[SerialWorker] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._rx_queue: asyncio.Queue = asyncio.Queue()
        self._tx_queue: Queue = Queue()  # 线程安全队列，供 asyncio 线程投递发送数据
        self._running = False
        self._callbacks = {
            'data_received': [],
            'connection_changed': [],
            'error': [],
            'raw_data_received': [],  # Lua引擎用
        }
    
    def register_callback(self, event: str, callback: Callable):
        """注册回调：data_received(bytes), connection_changed(bool), error(str), raw_data_received(bytes)"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    async def start(self, port: str, baudrate: int, parity: str):
        """异步打开串口"""
        if self._running:
            return
        
        self._worker = SerialWorker()
        self._worker.connection_changed.connect(self._on_connection_changed)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.data_received.connect(self._on_data_received)
        # 原始数据信号 (Lua引擎)
        if hasattr(self._worker, 'raw_data_received'):
            self._worker.raw_data_received.connect(self._on_raw_data_received)
        
        # 在后台线程启动 worker
        def run_worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._worker.open_serial(port, baudrate, parity)
            # 处理发送队列
            while self._running:
                try:
                    data = self._tx_queue.get(timeout=0.1)
                    self._worker.send_data(data)
                except Empty:
                    continue
            loop.close()
        
        self._running = True
        self._worker_thread = threading.Thread(target=run_worker, daemon=True)
        self._worker_thread.start()
        
        # 等待连接建立
        await asyncio.sleep(0.5)
    
    async def stop(self):
        """关闭串口"""
        self._running = False
        if self._worker:
            self._worker.close_serial()
        if self._worker_thread:
            self._worker_thread.join(timeout=2)
        self._worker = None
        self._worker_thread = None
    
    async def send(self, data: bytes):
        """异步发送数据"""
        if self._worker and self._running:
            self._tx_queue.put(data)
    
    def _on_connection_changed(self, connected: bool):
        for cb in self._callbacks['connection_changed']:
            try:
                cb(connected)
            except Exception:
                pass
    
    def _on_error(self, msg: str):
        for cb in self._callbacks['error']:
            try:
                cb(msg)
            except Exception:
                pass
    
    def _on_data_received(self, data: bytes):
        # 投递到 asyncio 队列
        try:
            self._rx_queue.put_nowait(data)
        except Exception:
            pass
        # 同步回调
        for cb in self._callbacks['data_received']:
            try:
                cb(data)
            except Exception:
                pass
    
    def _on_raw_data_received(self, data: bytes):
        for cb in self._callbacks['raw_data_received']:
            try:
                cb(data)
            except Exception:
                pass
    
    async def receive_loop(self):
        """异步接收循环，供上层 await"""
        while self._running:
            try:
                data = await asyncio.wait_for(self._rx_queue.get(), timeout=0.1)
                for cb in self._callbacks['data_received']:
                    try:
                        cb(data)
                    except Exception:
                        pass
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
```

- [ ] **Step 10: 运行验证基础框架**

```bash
cd E:\python\南网解析工具
pip install nicegui pyserial
python web_app.py
```
Expected: 浏览器打开 http://localhost:8080，显示顶部栏(标题+协议选择器+串口面板) + 9个空标签页

- [ ] **Step 11: 提交基础框架**

```bash
git add web_app.py web/ web_app.spec
git commit -m "feat(web): 基础框架 - 入口、主布局、协议选择器、十六进制输入、解析表格、串口面板、串口适配器"
```

---

### Phase 1: 单帧解析标签页

#### Task 1.1: 单帧解析核心功能

**Files:**
- Create: `web/tabs/single_parse.py`
- Modify: `web/main_page.py` (已引入)

- [ ] **Step 1: 写入 web/tabs/single_parse.py**

```python
# web/tabs/single_parse.py
"""单帧解析标签页"""
from nicegui import ui
from typing import Optional, Callable
from web.components.hex_input import HexInput
from web.components.parse_table import ParseTable
from web.components.byte_highlighter import ByteHighlighter
from protocol_parser import ProtocolFrameParser
from plc_rf_parser import PLCRFProtocolParser
from hdlc_parser import HDLCParser
from dlt645_parser import DLT645Parser
from gdw10376_parser import GDW10376Parser
from dl_t698_45_parser import DLT69845Parser
from csg_new_gen_parser import CSGNewGenParser
from validator import (
    NWValidator, PLCRFValidator, HDLCValidator,
    DLT645Validator, GDWValidator, DLT69845Validator, CSGNewGenValidator
)


class SingleParseTab:
    PARSERS = {
        0: ProtocolFrameParser,
        1: PLCRFProtocolParser,
        2: HDLCParser,
        3: HDLCParser,  # DLMS-APDU(国网) 复用 HDLCParser
        4: HDLCParser,
        5: HDLCParser,
        6: DLT645Parser,
        7: GDW10376Parser,
        8: DLT69845Parser,
        9: CSGNewGenParser,
    }
    
    VALIDATORS = {
        0: NWValidator,
        1: PLCRFValidator,
        2: HDLCValidator,
        3: HDLCValidator,
        4: HDLCValidator,
        5: HDLCValidator,
        6: DLT645Validator,
        7: GDWValidator,
        8: DLT69845Validator,
        9: CSGNewGenValidator,
    }
    
    def __init__(self, protocol_selector):
        self.protocol_selector = protocol_selector
        self.current_protocol = 0
        self.parser = self.PARSERS[0]()
        self.validator = self.VALIDATORS[0]()
        self._frame_bytes = b''
        self._parse_table = None
        self._hex_input = None
        self._verify_label = None
        self._raw_bytes_html = None
    
    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 输入区
            with ui.card().classes("w-full").style("max-height: 200px;"):
                ui.label("输入报文").classes("text-h6 q-mb-sm")
                self._hex_input = HexInput(
                    on_parse=self._on_parse,
                    height="120px",
                )
                self._hex_input.build()
                
                # 操作按钮
                with ui.row().classes("q-mt-sm q-gutter-sm"):
                    ui.button("解析报文", icon="search", on_click=self._do_parse).props("dense color=primary")
                    ui.button("校验报文", icon="verified", on_click=self._do_verify).props("dense color=info")
                    ui.button("添加到测试方案", icon="add_task", on_click=self._add_to_test).props("dense color=positive")
                    ui.button("填充CRC-24", icon="security", on_click=self._fill_crc24).props("dense color=orange")
                    ui.button("填充CRC-32", icon="security", on_click=self._fill_crc32).props("dense color=purple")
            
            # 结果区
            with ui.splitter(value=70).classes("w-full h-[calc(100%-220px)]") as splitter:
                with splitter.before:
                    with ui.card().classes("w-full h-full"):
                        ui.label("解析结果").classes("text-h6 q-mb-sm")
                        self._parse_table = ParseTable(
                            on_row_click=self._on_row_highlight,
                            on_row_double_click=self._on_row_double_click,
                            on_export_image=self._export_image,
                        )
                        self._parse_table.build()
                
                with splitter.after:
                    with ui.card().classes("w-full h-full"):
                        with ui.tabs().classes("w-full") as detail_tabs:
                            tab_verify = ui.tab("校验结果", icon="verified")
                            tab_raw = ui.tab("原始字节", icon="memory")
                        
                        with ui.tab_panels(detail_tabs, value=tab_verify).classes("w-full h-[calc(100%-48px)]"):
                            with ui.tab_panel(tab_verify):
                                self._verify_label = ui.label("点击「校验报文」按钮进行协议一致性校验").classes("q-pa-md text-grey-7")
                                self._verify_label.style("white-space: pre-wrap; font-family: monospace; font-size: 12px;")
                            
                            with ui.tab_panel(tab_raw):
                                self._raw_bytes_html = ui.html("").classes("q-pa-md")
                                self._raw_bytes_html.style("overflow: auto; height: 100%; font-family: monospace; font-size: 12px;")
    
    def _on_parse(self, frame_bytes: bytes):
        """HexInput 回调：解析并填充表格"""
        self._frame_bytes = frame_bytes
        self._do_parse_internal(frame_bytes)
    
    def _do_parse(self):
        """解析按钮点击"""
        frame_bytes = self._hex_input.get_bytes()
        if frame_bytes:
            self._do_parse_internal(frame_bytes)
    
    def _do_parse_internal(self, frame_bytes: bytes):
        """内部解析逻辑"""
        try:
            # 协议特定预处理
            if self.current_protocol == 9:  # 新一代载波
                parse_level = self.protocol_selector.current_csg_level
                strip_head = self.protocol_selector.strip_head
                strip_tail = self.protocol_selector.strip_tail
                result = self.parser.parse_to_table(
                    frame_bytes, 
                    parse_level=parse_level,
                    strip_head=strip_head,
                    strip_tail=strip_tail,
                )
            else:
                result = self.parser.parse_to_table(frame_bytes)
            
            self._parse_table.set_data(result, frame_bytes)
            
            # 显示原始字节
            html = ByteHighlighter.highlight_bytes(frame_bytes, [])
            self._raw_bytes_html.set_content(html)
            
            ui.notify(f"解析完成，共 {len(result)} 行", type="positive")
        except Exception as e:
            ui.notify(f"解析失败: {e}", type="negative")
            import traceback
            traceback.print_exc()
    
    def _do_verify(self):
        """校验按钮点击"""
        frame_bytes = self._hex_input.get_bytes()
        if not frame_bytes:
            return
        
        try:
            result = self.validator.verify(frame_bytes)
            # 格式化显示
            lines = [f"[{'通过' if result.valid else '失败'}] {result.summary()}"]
            for check in result.checks:
                icon = "✅" if check.level.value == "pass" else "❌" if check.level.value == "fail" else "⚠️"
                lines.append(f"  {icon} {check.name}: 期望={check.expected}, 实际={check.actual} - {check.message}")
            if result.warnings:
                for w in result.warnings:
                    lines.append(f"  ⚠️ {w}")
            if result.errors:
                for e in result.errors:
                    lines.append(f"  ❌ {e}")
            
            self._verify_label.set_text("\n".join(lines))
            ui.notify(result.summary(), type="positive" if result.valid else "negative")
        except Exception as e:
            ui.notify(f"校验出错: {e}", type="negative")
    
    def _on_row_highlight(self, start: int, end: int):
        """行点击：高亮原始字节"""
        if start is not None and end is not None and self._frame_bytes:
            ranges = [(start, end)] if start <= end else []
            html = ByteHighlighter.highlight_bytes(self._frame_bytes, ranges)
            self._raw_bytes_html.set_content(html)
    
    def _on_row_double_click(self, field: str, start: int, end: int):
        """双击行：提取 APDU 重新解析 (DLMS/HDLC)"""
        if self.current_protocol in (2, 3, 4, 5) and "APDU" in field.upper():
            if start is not None and end is not None and start <= end:
                apdu_bytes = self._frame_bytes[start:end+1]
                # TODO: 弹窗显示 DLMSDeepParser 结果
                ui.notify(f"双击提取 APDU: {len(apdu_bytes)} 字节，深度解析待实现", type="info")
    
    def _add_to_test(self):
        """添加到测试方案"""
        frame_hex = self._frame_bytes.hex().upper()
        # TODO: 发送信号给 TestPlanTab
        ui.notify(f"已添加到测试方案: {frame_hex[:32]}...", type="positive")
    
    def _fill_crc24(self):
        """填充 CRC-24 (新一代载波)"""
        ui.notify("CRC-24 填充待实现", type="info")
    
    def _fill_crc32(self):
        """填充 CRC-32 (新一代载波 MAC帧)"""
        ui.notify("CRC-32 填充待实现", type="info")
    
    def _export_image(self):
        """导出表格图片"""
        ui.notify("导出图片功能待实现 (需 html2canvas)", type="info")
    
    def on_protocol_change(self, protocol_idx: int):
        """协议切换回调"""
        self.current_protocol = protocol_idx
        self.parser = self.PARSERS[protocol_idx]()
        self.validator = self.VALIDATORS[protocol_idx]()
        
        # 更新占位符提示
        placeholders = {
            0: "南网协议示例: 68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
            1: "PLC RF示例: 68 0A 01 00 00 00 01 02 03 04 16",
            2: "HDLC示例: 7E A0 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 7E",
            6: "DLT645示例: 68 12 34 56 78 90 01 01 00 00 00 00 00 00 00 00 16",
            7: "国网协议示例: 68 10 00 00 00 00 01 00 01 00 00 00 00 00 00 00 00 00 00 00 16",
            8: "698.45示例: 68 0A 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 16",
            9: "新一代载波示例: 11 01 01 00 00 00 00 01 00 01 00 00 ...",
        }
        if self._hex_input:
            self._hex_input._placeholder = placeholders.get(protocol_idx, "请输入十六进制报文")
            self._hex_input._textarea.props(f'placeholder="{self._hex_input._placeholder}"')
            self._hex_input._textarea.update()
```

- [ ] **Step 2: 注册协议切换回调**

在 `web/main_page.py` 的 `MainPage.build()` 中，`ProtocolSelector` 创建后添加：
```python
# 协议切换时通知所有标签页
def _on_protocol_change(proto_idx):
    for tab in [self.tab_single, self.tab_lookup, self.tab_batch, 
                self.tab_frame_gen, self.tab_preset, self.tab_test,
                self.tab_archive, self.tab_topo, self.tab_diff]:
        if hasattr(tab, 'on_protocol_change'):
            tab.on_protocol_change(proto_idx)

self.protocol_selector = ProtocolSelector(on_change=_on_protocol_change)
```

- [ ] **Step 3: 运行验证单帧解析**

```bash
python web_app.py
```
Expected: 单帧解析标签页可输入报文、点击解析显示表格、点击行高亮字节、校验显示结果

- [ ] **Step 4: 提交**

```bash
git add web/tabs/single_parse.py web/main_page.py
git commit -m "feat(web): 单帧解析标签页 - 输入/解析/表格/高亮/校验/原始字节"
```

---

### Phase 2: 查询标签页

#### Task 2.1: 查询标签页 (DI/AFN/OBIS/命令字/业务标识)

**Files:**
- Create: `web/tabs/lookup.py`

- [ ] **Step 1: 写入 web/tabs/lookup.py**

```python
# web/tabs/lookup.py
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
            with ui.row().classes("w-full q-gutter-sm items-center"):
                ui.label("搜索：").classes("text-weight-bold")
                self._search_input = ui.input(
                    placeholder="输入关键词搜索 (DI编码/中文/十六进制)...",
                    on_change=self._filter_table,
                ).classes("flex-grow").props("dense outlined clearable")
                
                self._stats_label = ui.label("").classes("text-sm text-grey-7")
            
            # 表格
            with ui.card().classes("w-full h-[calc(100%-80px)]"):
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
                ).classes("dense-table w-full h-full").props("flat bordered separator=cell virtual-scroll")
    
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
```

- [ ] **Step 2: 运行验证查询标签页**

```bash
python web_app.py
```
Expected: 切换协议时查询表格自动更新，搜索框可过滤

- [ ] **Step 3: 提交**

```bash
git add web/tabs/lookup.py
git commit -m "feat(web): 查询标签页 - DI/AFN/OBIS/命令字/业务标识搜索表格"
```

---

### Phase 3: 批量解析标签页

#### Task 3.1: 批量解析

**Files:**
- Create: `web/tabs/batch_parse.py`

- [ ] **Step 1: 写入 web/tabs/batch_parse.py**

```python
# web/tabs/batch_parse.py
"""批量解析标签页"""
from nicegui import ui
from typing import List, Dict, Any
from web.components.hex_input import HexInput
from web.components.parse_table import ParseTable
from web.components.byte_highlighter import ByteHighlighter
from protocol_parser import ProtocolFrameParser
from plc_rf_parser import PLCRFProtocolParser
from hdlc_parser import HDLCParser
from dlt645_parser import DLT645Parser
from gdw10376_parser import GDW10376Parser
from dl_t698_45_parser import DLT69845Parser
from csg_new_gen_parser import CSGNewGenParser


class BatchParseTab:
    PARSERS = {
        0: ProtocolFrameParser,
        1: PLCRFProtocolParser,
        2: HDLCParser,
        3: HDLCParser,
        4: HDLCParser,
        5: HDLCParser,
        6: DLT645Parser,
        7: GDW10376Parser,
        8: DLT69845Parser,
        9: CSGNewGenParser,
    }
    
    def __init__(self, protocol_selector):
        self.protocol_selector = protocol_selector
        self.current_protocol = 0
        self.parser = self.PARSERS[0]()
        self._batch_input = None
        self._summary_table = None
        self._detail_table = None
        self._results = []
    
    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 输入区
            with ui.card().classes("w-full").style("max-height: 250px;"):
                ui.label("批量输入报文 (每行一帧)").classes("text-h6 q-mb-sm")
                self._batch_input = ui.textarea(
                    placeholder="每行一个十六进制报文，支持空格/逗号分隔\n示例:\n68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16\n68 0C 00 40 01 00 01 01 02 E8 2D 16",
                ).classes("w-full").props('dense rows=8 style="height: 180px; font-family: monospace;"')
                
                with ui.row().classes("q-mt-sm q-gutter-sm"):
                    ui.button("批量解析", icon="playlist_add", on_click=self._do_batch_parse).props("dense color=primary")
                    ui.button("清空", icon="clear_all", on_click=self._clear).props("dense outline")
                    ui.button("导出结果", icon="download", on_click=self._export).props("dense outline")
                    ui.space()
                    ui.label("解析级别:").classes("text-sm")
                    ui.select(
                        options={"auto": "自动", "fc_pb": "FC+PB", "fc_only": "仅FC", "app": "应用层"},
                        value="auto",
                    ).props("dense outlined").classes("w-32").bind_value(self, '_parse_level')
            
            # 结果区
            with ui.splitter(value=50).classes("w-full h-[calc(100%-320px)]") as splitter:
                with splitter.before:
                    with ui.card().classes("w-full h-full"):
                        ui.label("批量解析摘要").classes("text-h6 q-mb-sm")
                        columns = [
                            {"name": "idx", "label": "序号", "field": "idx", "width": "50px"},
                            {"name": "status", "label": "状态", "field": "status", "width": "80px"},
                            {"name": "len", "label": "长度", "field": "len", "width": "60px"},
                            {"name": "proto", "label": "协议/类型", "field": "proto"},
                            {"name": "summary", "label": "摘要", "field": "summary"},
                        ]
                        self._summary_table = ui.table(
                            columns=columns,
                            rows=[],
                            row_key="id",
                            selection="single",
                        ).classes("dense-table w-full h-full").props("flat bordered separator=cell virtual-scroll")
                        self._summary_table.on('rowClick', self._on_summary_click)
                
                with splitter.after:
                    with ui.card().classes("w-full h-full"):
                        ui.label("选中帧详细解析").classes("text-h6 q-mb-sm")
                        self._detail_table = ParseTable(
                            on_row_click=lambda s, e: None,
                            on_row_double_click=None,
                        )
                        self._detail_table.build()
    
    def on_protocol_change(self, protocol_idx: int):
        self.current_protocol = protocol_idx
        self.parser = self.PARSERS[protocol_idx]()
        self._results = []
        self._summary_table.rows = []
        self._detail_table.set_data([])
    
    def _do_batch_parse(self):
        text = self._batch_input.value or ""
        if not text.strip():
            ui.notify("请输入报文", type="warning")
            return
        
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        self._results = []
        summary_rows = []
        
        for idx, line in enumerate(lines):
            try:
                # 清洗
                import re
                clean = re.sub(r'0[xX]([0-9A-Fa-f])', r'\1', line)
                clean = re.sub(r'[^0-9A-Fa-f]', '', clean)
                if len(clean) % 2 != 0:
                    raise ValueError("奇数长度")
                frame_bytes = bytes.fromhex(clean)
                
                # 解析
                if self.current_protocol == 9:
                    result = self.parser.parse_to_table(
                        frame_bytes, 
                        parse_level=getattr(self, '_parse_level', 'auto'),
                        strip_head=self.protocol_selector.strip_head,
                        strip_tail=self.protocol_selector.strip_tail,
                    )
                else:
                    result = self.parser.parse_to_table(frame_bytes)
                
                # 摘要
                status = "成功" if result and result[0][0] != "❌ 解析失败" else "失败"
                proto_name = self._get_frame_summary(result)
                
                self._results.append({
                    "id": idx,
                    "frame_bytes": frame_bytes,
                    "result": result,
                    "status": status,
                })
                
                summary_rows.append({
                    "id": idx,
                    "idx": idx + 1,
                    "status": "✅" if status == "成功" else "❌",
                    "len": len(frame_bytes),
                    "proto": proto_name,
                    "summary": self._extract_summary(result)[:80],
                })
            except Exception as ex:
                self._results.append({
                    "id": idx,
                    "frame_bytes": b"",
                    "result": [],
                    "status": "错误",
                    "error": str(ex),
                })
                summary_rows.append({
                    "id": idx,
                    "idx": idx + 1,
                    "status": "❌",
                    "len": 0,
                    "proto": "解析错误",
                    "summary": str(ex)[:80],
                })
        
        self._summary_table.rows = summary_rows
        ui.notify(f"批量解析完成：{len(lines)} 帧", type="positive")
    
    def _get_frame_summary(self, result: List) -> str:
        if not result:
            return "空"
        # 尝试提取关键字段
        for row in result:
            field = row[0]
            if "AFN" in field or "帧类型" in field or "业务标识" in field or "功能码" in field:
                return str(row[3]) or str(row[2]) or field
        return result[0][0]
    
    def _extract_summary(self, result: List) -> str:
        if not result:
            return ""
        parts = []
        for row in result[:5]:
            if row[3]:
                parts.append(row[3])
        return "; ".join(parts)
    
    def _on_summary_click(self, e):
        row = e.args[0] if e.args else {}
        idx = row.get("id", -1)
        if 0 <= idx < len(self._results):
            item = self._results[idx]
            self._detail_table.set_data(item["result"], item["frame_bytes"])
    
    def _clear(self):
        self._batch_input.value = ""
        self._results = []
        self._summary_table.rows = []
        self._detail_table.set_data([])
    
    def _export(self):
        import json
        if not self._results:
            ui.notify("无数据可导出", type="warning")
            return
        data = []
        for item in self._results:
            data.append({
                "frame": item["frame_bytes"].hex().upper(),
                "status": item["status"],
                "result": item["result"],
            })
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        ui.download(json_str.encode(), "batch_parse_result.json")
        ui.notify("已导出 JSON", type="positive")
```

- [ ] **Step 2: 运行验证批量解析**

- [ ] **Step 3: 提交**

---

### Phase 4: 协议组帧标签页 (最复杂)

#### Task 4.1: 协议组帧核心 - Schema驱动动态表单

**Files:**
- Create: `web/tabs/frame_gen.py`

- [ ] **Step 1: 写入 web/tabs/frame_gen.py (分多步，先写框架)**

```python
# web/tabs/frame_gen.py
"""协议组帧标签页 - Schema驱动动态表单"""
from nicegui import ui
from typing import Dict, List, Tuple, Any, Optional
from web.components.hex_input import HexInput
from web.components.parse_table import ParseTable
from protocol_parser import ProtocolFrameParser
from send_frame_lib import ProtocolFrameGenerator
from frame_generator_schema import DI_FIELD_SCHEMA
from gdw10376_parser import GDW10376Parser
from gdw_send_frame_lib import GDWFrameGenerator
from gdw_frame_generator_schema import GDW_AFNFN_SCHEMA
from dl_t698_45_parser import DLT69845Parser
from dl_t698_45_frame_gen import DLT69845FrameGenerator
from dl_t698_45_frame_schema import DLT69845_FIELD_SCHEMA, APDU_TYPE_LIST, OI_PRESET_LIST
from preset_buttons import PresetButtonManager, AddPresetDialog
from gui_utils import apply_chinese_context_menus
import json


class FrameGenTab:
    def __init__(self, protocol_selector, serial_panel):
        self.protocol_selector = protocol_selector
        self.serial_panel = serial_panel
        self.protocol_mode = "south"  # south, gdw, dlt698
        
        # 生成器
        self.generator = ProtocolFrameGenerator()
        self.parser = ProtocolFrameParser()
        self.gdw_generator = GDWFrameGenerator()
        self.gdw_parser = GDW10376Parser()
        self.dlt698_generator = DLT69845FrameGenerator()
        self.dlt698_parser = DLT69845Parser()
        
        # UI 状态
        self._field_widgets: Dict[str, Dict] = {}
        self._current_di_key: Optional[Tuple[int, int, int, int]] = None
        self._current_afn_fn: Optional[Tuple[int, int]] = None
        self._current_dlt698_key: Optional[Tuple[str, str]] = None
        self._custom_templates: List = []
        self._custom_mode = False
        self._axdr_mode = False
        self._axdr_items = []
        
        # UI 组件引用
        self._di_combo = None
        self._afn_fn_combo = None
        self._dlt698_apdu_combo = None
        self._dlt698_sub_combo = None
        self._form_container = None
        self._preview_text = None
        self._src_addr = None
        self._dst_addr = None
        self._seq_input = None
        self._dir_select = None
        self._prm_select = None
    
    def build(self):
        with ui.splitter(value=40).classes("w-full h-full q-pa-md q-gutter-md") as splitter:
            # 左侧：命令选择 + 表单
            with splitter.before:
                with ui.column().classes("w-full h-full q-gutter-sm"):
                    # 命令选择区
                    self._build_command_selector()
                    
                    # 动态表单区
                    with ui.card().classes("w-full h-[calc(100%-200px)]"):
                        ui.label("字段配置").classes("text-h6 q-mb-sm q-px-md")
                        self._form_container = ui.column().classes("w-full h-full q-pa-md overflow-auto")
            
            # 右侧：预览 + 发送
            with splitter.after:
                with ui.column().classes("w-full h-full q-gutter-sm"):
                    with ui.card().classes("w-full h-[60%]").style("min-height: 300px;"):
                        ui.label("生成预览").classes("text-h6 q-mb-sm q-px-md")
                        self._preview_text = ui.textarea().classes("w-full h-full font-mono text-sm").props(
                            'dense readonly rows=20 style="height: 100%; font-family: JetBrains Mono, monospace; font-size: 12px;"'
                        )
                    
                    with ui.card().classes("w-full h-[40%]").style("min-height: 200px;"):
                        ui.label("帧配置").classes("text-h6 q-mb-sm q-px-md")
                        self._build_frame_config()
                    
                    # 底部按钮
                    with ui.row().classes("w-full q-gutter-sm q-mt-sm q-px-md"):
                        ui.button("生成预览", icon="preview", on_click=self._generate_preview).props("dense color=primary")
                        ui.button("发送帧", icon="send", on_click=self._send_frame).props("dense color=positive")
                        ui.button("添加到预设", icon="widgets", on_click=self._add_to_preset).props("dense color=orange")
                        ui.button("添加到测试方案", icon="add_task", on_click=self._add_to_test).props("dense color=green")
                        ui.space()
                        ui.button("导出JSON", icon="download", on_click=self._export_json).props("dense outline")
    
    def _build_command_selector(self):
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full q-gutter-sm items-center q-pa-sm"):
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
            self._dir_select = ui.select(options={"下行(主站→终端)": 0, "上行(终端→主站)": 1}, value=0).props("dense outlined")
            
            ui.label("启动标志(PRM):")
            self._prm_select = ui.select(options={"从动站发起(0)": 0, "启动站发起(1)": 1}, value=1).props("dense outlined")
    
    def _populate_di_combo(self):
        options = {}
        for (di3, di2, di1, di0), desc in self.parser.DI_COMBINATION_MAP.items():
            key = f"{di3:02X}{di2:02X}{di1:02X}{di0:02X}"
            options[key] = f"{key} - {desc}"
        self._di_combo.options = options
        self._di_combo.update()
    
    def _populate_afn_fn_combo(self):
        options = {}
        for afn, fn_map in self.gdw_parser.FN_MAP.items():
            afn_name = self.gdw_parser.AFN_MAP.get(afn, f"未知({afn:02X})")
            for fn, fn_name in fn_map.items():
                key = f"{afn:02X}{fn:02X}"
                options[key] = f"{key} - {afn_name} / Fn={fn:02X} {fn_name}"
        self._afn_fn_combo.options = options
        self._afn_fn_combo.update()
    
    def on_protocol_change(self, protocol_idx: int):
        """协议切换：切换模式 south/gdw/dlt698"""
        mode_map = {0: "south", 1: "south", 2: "south", 3: "south", 4: "south", 5: "south", 
                    6: "south", 7: "gdw", 8: "dlt698", 9: "south"}
        self.protocol_mode = mode_map.get(protocol_idx, "south")
        
        # 显示/隐藏对应选择器
        is_gdw = (self.protocol_mode == "gdw")
        is_dlt698 = (self.protocol_mode == "dlt698")
        is_south = (self.protocol_mode == "south")
        
        self._di_combo.set_visibility(is_south)
        self._afn_fn_combo.set_visibility(is_gdw)
        self._dlt698_select_row.set_visibility(is_dlt698)
        
        # 清空表单
        self._clear_form()
        self._preview_text.value = ""
    
    def _on_di_change(self, e):
        if not e.value:
            return
        key = e.value
        di3 = int(key[0:2], 16)
        di2 = int(key[2:4], 16)
        di1 = int(key[4:6], 16)
        di0 = int(key[6:8], 16)
        self._current_di_key = (di3, di2, di1, di0)
        self._build_form_from_schema(DI_FIELD_SCHEMA.get(key, []))
    
    def _on_afn_fn_change(self, e):
        if not e.value:
            return
        key = e.value
        afn = int(key[0:2], 16)
        fn = int(key[2:4], 16)
        self._current_afn_fn = (afn, fn)
        self._build_form_from_schema(GDW_AFNFN_SCHEMA.get((afn, fn), []))
    
    def _on_dlt698_apdu_change(self, e):
        if not e.value:
            return
        self._current_dlt698_key = (e.value, None)
        # 更新子类型下拉
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
            length = field_def.get("length", 1)
            default = field_def.get("default", "")
            options = field_def.get("options", {})
            display = field_def.get("display", "hex")
            endian = field_def.get("endian", "big")
            reverse = field_def.get("reverse", False)
            help_text = field_def.get("help", "")
            
            with self._form_container:
                with ui.row().classes("w-full q-gutter-sm items-center q-mb-xs"):
                    ui.label(f"{name}:").classes("text-sm").style("min-width: 140px;")
                    
                    if options:
                        # 下拉选择
                        widget = ui.select(
                            options=options,
                            value=default,
                        ).props("dense outlined").classes("flex-grow")
                    elif ftype == "bool":
                        widget = ui.checkbox(value=bool(default)).props("dense")
                    elif ftype in ("uint8", "uint16", "uint32", "int8", "int16", "int32"):
                        widget = ui.input(value=str(default), placeholder=f"{ftype} {display}").props("dense outlined").classes("flex-grow")
                    elif ftype == "bytes":
                        widget = ui.input(value=default, placeholder=f"HEX bytes (长度={length})").props("dense outlined").classes("flex-grow")
                    elif ftype == "string":
                        widget = ui.input(value=default, placeholder="字符串").props("dense outlined").classes("flex-grow")
                    else:
                        widget = ui.input(value=str(default)).props("dense outlined").classes("flex-grow")
                    
                    # 存储字段元数据
                    self._field_widgets[name] = {
                        "widget": widget,
                        "type": ftype,
                        "length": length,
                        "display": display,
                        "endian": endian,
                        "reverse": reverse,
                        "options": options,
                    }
                    
                    if help_text:
                        widget.tooltip(help_text)
    
    def _clear_form(self):
        self._form_container.clear()
        self._field_widgets = {}
    
    def _generate_preview(self):
        """根据表单值生成帧预览"""
        try:
            field_values = {}
            for name, info in self._field_widgets.items():
                widget = info["widget"]
                val = widget.value
                if val is None or val == "":
                    continue
                field_values[name] = val
            
            if self.protocol_mode == "south":
                di_key = self._current_di_key
                if not di_key:
                    ui.notify("请先选择 DI 命令", type="warning")
                    return
                frame_bytes = self.generator.generate_frame(
                    di_key=di_key,
                    field_values=field_values,
                    src_addr=self._src_addr.value,
                    dst_addr=self._dst_addr.value,
                    seq=self._seq_input.value,
                    direction=self._dir_select.value,
                    prm=self._prm_select.value,
                )
            elif self.protocol_mode == "gdw":
                afn_fn = self._current_afn_fn
                if not afn_fn:
                    ui.notify("请先选择 AFN+Fn", type="warning")
                    return
                frame_bytes = self.gdw_generator.generate_frame(
                    afn=afn_fn[0],
                    fn=afn_fn[1],
                    field_values=field_values,
                    src_addr=self._src_addr.value,
                    dst_addr=self._dst_addr.value,
                    seq=self._seq_input.value,
                    direction=self._dir_select.value,
                    prm=self._prm_select.value,
                )
            elif self.protocol_mode == "dlt698":
                key = self._current_dlt698_key
                if not key or not key[1]:
                    ui.notify("请先选择 APDU 类型和子类型", type="warning")
                    return
                frame_bytes = self.dlt698_generator.generate_frame(
                    apdu_type=key[0],
                    sub_type=key[1],
                    field_values=field_values,
                    # ... 其他参数
                )
            else:
                ui.notify("不支持的协议模式", type="negative")
                return
            
            # 显示预览
            hex_str = " ".join(f"{b:02X}" for b in frame_bytes)
            self._preview_text.value = hex_str
            ui.notify(f"生成成功: {len(frame_bytes)} 字节", type="positive")
        except Exception as ex:
            ui.notify(f"生成失败: {ex}", type="negative")
            import traceback
            traceback.print_exc()
    
    def _send_frame(self):
        """发送帧到串口"""
        hex_text = self._preview_text.value
        if not hex_text.strip():
            ui.notify("先生成预览", type="warning")
            return
        try:
            frame_bytes = bytes.fromhex(hex_text.replace(" ", ""))
            # TODO: 通过 serial_panel 发送
            ui.notify("发送功能待连接串口适配器", type="info")
        except Exception as ex:
            ui.notify(f"发送失败: {ex}", type="negative")
    
    def _add_to_preset(self):
        """添加到预设命令"""
        hex_text = self._preview_text.value
        if not hex_text.strip():
            ui.notify("先生成预览", type="warning")
            return
        # TODO: 打开 AddPresetDialog
        ui.notify("添加到预设待实现", type="info")
    
    def _add_to_test(self):
        ui.notify("添加到测试方案待实现", type="info")
    
    def _export_json(self):
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
        """显示命令说明对话框"""
        if self.protocol_mode == "south" and self._current_di_key:
            di3, di2, di1, di0 = self._current_di_key
            desc = self.parser.DI_COMBINATION_MAP.get((di3, di2, di1, di0), "无说明")
            with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 500px; max-width: 800px;"):
                ui.label(f"DI: {di3:02X}{di2:02X}{di1:02X}{di0:02X}").classes("text-h6 q-mb-md")
                ui.label(desc).classes("q-mb-md")
                ui.button("关闭", on_click=dialog.close).props("dense color=primary")
            dialog.open()
        elif self.protocol_mode == "gdw" and self._current_afn_fn:
            afn, fn = self._current_afn_fn
            afn_name = self.gdw_parser.AFN_MAP.get(afn, f"未知({afn:02X})")
            fn_map = self.gdw_parser.FN_MAP.get(afn, {})
            fn_name = fn_map.get(fn, f"未知({fn:02X})")
            with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 500px;"):
                ui.label(f"AFN={afn:02X} {afn_name} / Fn={fn:02X} {fn_name}").classes("text-h6 q-mb-md")
                ui.button("关闭", on_click=dialog.close).props("dense color=primary")
            dialog.open()
```

- [ ] **Step 2: 完善组帧生成逻辑 (send_frame_lib/gdw_send_frame_lib/dlt698_frame_gen 集成)**

- [ ] **Step 3: 运行验证组帧标签页**

- [ ] **Step 4: 提交**

---

### Phase 5: 预设命令标签页

#### Task 5.1: 预设命令

**Files:**
- Create: `web/tabs/preset_cmd.py`

- [ ] **Step 1: 写入 web/tabs/preset_cmd.py**

```python
# web/tabs/preset_cmd.py
"""预设命令标签页"""
from nicegui import ui
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from preset_buttons import PresetButtonManager, AddPresetDialog


class PresetCmdTab:
    def __init__(self, protocol_selector, serial_panel):
        self.protocol_selector = protocol_selector
        self.serial_panel = serial_panel
        self.current_protocol = 0
        self._protocol_mode = "south"  # south 或 gw
        self._container = None
        self._search_input = None
    
    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 搜索栏
            with ui.row().classes("w-full q-gutter-sm items-center"):
                ui.label("搜索：").classes("text-weight-bold")
                self._search_input = ui.input(
                    placeholder="输入按钮名称/分组/描述搜索...",
                    on_change=self._filter_buttons,
                ).classes("flex-grow").props("dense outlined clearable")
            
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
        commands = PresetButtonManager.load_commands(self._protocol_mode)
        
        # 按分组渲染
        groups = {}
        for cmd in commands:
            group = cmd.get("group", "未分组")
            groups.setdefault(group, []).append(cmd)
        
        for group_name, cmds in groups.items():
            with self._container:
                with ui.expansion(group_name, icon="folder").classes("w-full").props("dense"):
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
            ui.menu_item("发送该帧", lambda c=cmd: self._send_frame(c))
            ui.menu_item("编辑", lambda c=cmd: self._edit_preset(c))
            ui.menu_item("删除", lambda c=cmd: self._delete_preset(c))
            ui.menu_item("复制报文", lambda c=cmd: self._copy_frame(c))
        
        btn.on('contextmenu', lambda e, m=menu: m.open(e))
        
        # Tooltip 显示描述和报文
        desc = cmd.get("desc", "")
        frame = cmd.get("frame", "")
        btn.tooltip(f"{desc}\n\n{frame[:100]}...")
    
    def _on_button_click(self, cmd: Dict):
        """点击按钮：发送帧或通知其他标签页"""
        frame_hex = cmd.get("frame", "")
        if frame_hex:
            # TODO: 发送到串口或通知组帧页
            ui.notify(f"点击预设: {cmd['name']}", type="info")
    
    def _send_frame(self, cmd: Dict):
        frame_hex = cmd.get("frame", "")
        if frame_hex:
            # TODO: 通过 serial_adapter 发送
            ui.notify(f"发送: {frame_hex[:32]}...", type="positive")
    
    def _edit_preset(self, cmd: Dict):
        # TODO: 打开编辑对话框
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
        keyword = (e.value or "").strip().lower()
        # 简单实现：重新加载并过滤 (或用 CSS display:none)
        self._load_presets()
        if keyword:
            # 对已渲染的按钮应用过滤 (需要遍历子元素)
            pass
```

- [ ] **Step 2: 运行验证**

- [ ] **Step 3: 提交**

---

### Phase 6: 测试方案标签页

#### Task 6.1: 测试方案 (含 Lua 编辑器)

**Files:**
- Create: `web/tabs/test_plan.py`

- [ ] **Step 1: 写入 web/tabs/test_plan.py (框架+表格+Lua编辑器)**

```python
# web/tabs/test_plan.py
"""测试方案标签页"""
from nicegui import ui
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from test_plan_widget import TEST_PLAN_PATH
from lua_script_engine import LuaScriptEngine, LUA_AVAILABLE, LUA_TEMPLATES


class TestPlanTab:
    def __init__(self, protocol_selector, serial_panel):
        self.protocol_selector = protocol_selector
        self.serial_panel = serial_panel
        self.current_protocol = 0
        self._table = None
        self._items: List[Dict] = []
        self._lua_editor = None
        self._lua_dialog = None
    
    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 工具栏
            with ui.row().classes("w-full q-gutter-sm items-center q-mb-md"):
                ui.button("新建", icon="add", on_click=self._add_item).props("dense color=primary")
                ui.button("导入", icon="upload", on_click=self._import_json).props("dense outline")
                ui.button("导出", icon="download", on_click=self._export_json).props("dense outline")
                ui.space()
                ui.button("顺序发送", icon="play_arrow", on_click=self._run_sequence).props("dense color=positive")
                ui.button("停止", icon="stop", on_click=self._stop_sequence).props("dense color=negative")
            
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
            
            with ui.card().classes("w-full h-[calc(100%-100px)]"):
                self._table = ui.table(
                    columns=columns,
                    rows=[],
                    row_key="id",
                ).classes("dense-table w-full h-full").props("flat bordered separator=cell virtual-scroll")
                
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
        """打开 Lua 脚本编辑器 (Monaco)"""
        with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 800px; max-width: 1000px;"):
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
            editor = ui.editor(
                value=item.get("lua_script", ""),
                language="lua",
                theme="vs-dark",
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
        with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 500px;"):
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
        # TODO: 文件上传
        ui.notify("导入功能待实现", type="info")
    
    def _export_json(self):
        ui.download(json.dumps({"items": self._items}, ensure_ascii=False, indent=2).encode(), "test_plan.json")
        ui.notify("已导出", type="positive")
    
    def _run_sequence(self):
        """顺序发送测试"""
        ui.notify("顺序发送测试待实现 (需串口适配器)", type="info")
    
    def _stop_sequence(self):
        ui.notify("停止测试", type="warning")
```

- [ ] **Step 2: 运行验证**

- [ ] **Step 3: 提交**

---

### Phase 7: 档案管理 / 拓扑信息 / 报文对比

#### Task 7.1: 档案管理标签页

**Files:**
- Create: `web/tabs/archive.py`

- [ ] **Step 1: 写入 web/tabs/archive.py (树形/表格 + 导入导出)**

```python
# web/tabs/archive.py
"""档案管理标签页"""
from nicegui import ui
from typing import List, Dict, Any
from pathlib import Path
import json
from archive_widget import ArchiveWidget  # 复用现有逻辑类


class ArchiveTab:
    def __init__(self, protocol_selector, serial_panel):
        self.protocol_selector = protocol_selector
        self.serial_panel = serial_panel
        self.current_protocol = 0
        self._archive = ArchiveWidget()
        self._tree = None
        self._table = None
    
    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 工具栏
            with ui.row().classes("w-full q-gutter-sm items-center q-mb-md"):
                ui.button("刷新", icon="refresh", on_click=self._refresh).props("dense outline")
                ui.button("导入", icon="upload", on_click=self._import).props("dense outline")
                ui.button("导出", icon="download", on_click=self._export).props("dense outline")
                ui.space()
                ui.label("仅支持南网/国网协议").classes("text-sm text-grey-7")
            
            # 分割器：左侧树形，右侧表格详情
            with ui.splitter(value=30).classes("w-full h-[calc(100%-80px)]") as splitter:
                with splitter.before:
                    with ui.card().classes("w-full h-full"):
                        ui.label("档案目录").classes("text-h6 q-mb-sm q-px-md")
                        self._tree = ui.tree(
                            [],
                            label_key="name",
                            children_key="children",
                        ).classes("w-full h-[calc(100%-48px)] q-pa-sm").props("dense")
                
                with splitter.after:
                    with ui.card().classes("w-full h-full"):
                        ui.label("档案详情").classes("text-h6 q-mb-sm q-px-md")
                        columns = [
                            {"name": "key", "label": "键", "field": "key", "width": "150px"},
                            {"name": "value", "label": "值", "field": "value"},
                        ]
                        self._table = ui.table(
                            columns=columns,
                            rows=[],
                        ).classes("dense-table w-full h-[calc(100%-48px)]").props("flat bordered separator=cell")
            
            self._refresh()
    
    def on_protocol_change(self, protocol_idx: int):
        self.current_protocol = protocol_idx
        if protocol_idx not in (0, 7):
            # 非南网/国网协议隐藏内容
            self._tree.set_nodes([])
            self._table.rows = []
        else:
            self._refresh()
    
    def _refresh(self):
        # 复用 ArchiveWidget 逻辑获取数据
        # 这里简化实现
        nodes = [
            {"id": "collector", "name": "采集器档案", "children": [
                {"id": "meter_1", "name": "电表 001", "children": []},
                {"id": "meter_2", "name": "电表 002", "children": []},
            ]},
            {"id": "module", "name": "模块档案", "children": []},
        ]
        self._tree.set_nodes(nodes)
    
    def _import(self):
        ui.notify("导入功能待实现", type="info")
    
    def _export(self):
        ui.notify("导出功能待实现", type="info")
```

- [ ] **Step 2: 提交**

---

#### Task 7.2: 拓扑信息标签页

**Files:**
- Create: `web/tabs/topology.py`

- [ ] **Step 1: 写入 web/tabs/topology.py**

```python
# web/tabs/topology.py
"""拓扑信息标签页"""
from nicegui import ui
from typing import List, Dict, Any
from topology_widget import TopologyWidget


class TopologyTab:
    def __init__(self, protocol_selector, serial_panel):
        self.protocol_selector = protocol_selector
        self.serial_panel = serial_panel
        self.current_protocol = 0
        self._topo = TopologyWidget()
        self._table = None
        self._search = None
    
    def build(self):
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 工具栏
            with ui.row().classes("w-full q-gutter-sm items-center q-mb-md"):
                ui.button("刷新", icon="refresh", on_click=self._refresh).props("dense outline")
                ui.button("自动刷新", icon="autorenew", on_click=self._toggle_auto).props("dense outline")
                ui.space()
                self._search = ui.input(placeholder="搜索 TEI/地址/角色...", on_change=self._filter).props("dense outlined clearable").classes("w-64")
                ui.label("仅南网/国网协议").classes("text-sm text-grey-7")
            
            # 表格
            with ui.card().classes("w-full h-[calc(100%-80px)]"):
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
                ).classes("dense-table w-full h-full").props("flat bordered separator=cell virtual-scroll")
            
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
```

- [ ] **Step 2: 提交**

---

#### Task 7.3: 报文对比标签页

**Files:**
- Create: `web/tabs/diff.py`

- [ ] **Step 1: 写入 web/tabs/diff.py (复用 FrameDiffEngine)**

```python
# web/tabs/diff.py
"""报文对比标签页"""
from nicegui import ui
from typing import Optional, Dict, Any, List
from frame_diff_engine import FrameDiffEngine
from web.components.byte_highlighter import ByteHighlighter


class DiffTab:
    def __init__(self, protocol_selector):
        self.protocol_selector = protocol_selector
        self.current_protocol = 0
        self._engine = FrameDiffEngine()
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
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md"):
            # 输入区
            with ui.row().classes("w-full q-gutter-md"):
                with ui.column().classes("flex-grow"):
                    ui.label("报文 A (基准)").classes("text-h6 q-mb-sm")
                    self._input_a = ui.textarea(placeholder="粘贴十六进制报文 A...").classes("w-full").props('dense rows=4 style="height: 120px; font-family: monospace;"')
                
                with ui.column().classes("flex-grow"):
                    ui.label("报文 B (对比)").classes("text-h6 q-mb-sm")
                    self._input_b = ui.textarea(placeholder="粘贴十六进制报文 B...").classes("w-full").props('dense rows=4 style="height: 120px; font-family: monospace;"')
            
            # 操作栏
            with ui.row().classes("w-full q-gutter-sm items-center q-mb-md"):
                ui.button("开始对比", icon="compare_arrows", on_click=self._do_diff).props("dense color=primary")
                ui.button("交换 A↔B", icon="swap_horiz", on_click=self._swap).props("dense outline")
                ui.space()
                
                # 选项
                ui.checkbox("字段感知对齐", value=True).props("dense").bind_value(self._options, "field_aware")
                ui.checkbox("忽略校验和", value=True).props("dense").bind_value(self._options, "ignore_checksum")
                ui.checkbox("忽略序列号", value=True).props("dense").bind_value(self._options, "ignore_seq")
                ui.checkbox("仅显示差异", value=False).props("dense").bind_value(self._options, "show_diff_only")
            
            # 结果区
            with ui.splitter(value=50).classes("w-full h-[calc(100%-300px)]") as splitter:
                with splitter.before:
                    with ui.card().classes("w-full h-full"):
                        ui.label("字节级对比").classes("text-h6 q-mb-sm q-px-md")
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
            result = self._engine.diff(
                bytes_a, bytes_b,
                protocol=self.current_protocol,
                field_aware=self._options["field_aware