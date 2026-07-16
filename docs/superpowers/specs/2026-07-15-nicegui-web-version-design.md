# NiceGUI Web版南网协议解析工具 - 设计规格文档

**版本**: 1.0  
**日期**: 2026-07-15  
**状态**: 已批准，进入实施阶段

---

## 1. 项目概述

基于 NiceGUI 框架开发 Web 版南网协议解析工具，完整复刻现有 PySide6 桌面端的所有功能（10个协议、9大标签页），支持打包为单文件 EXE 部署。

### 1.1 目标
- **功能对等**：100% 覆盖现有 `main_gui.py` 所有功能
- **架构复用**：零修改复用现有解析器、验证器、组帧器、Diff引擎、Lua引擎
- **部署一致**：PyInstaller 单文件 EXE，与现有 `南网协议解析工具.spec` 体验一致
- **视觉风格**：NiceGUI 原生 Quasar 组件 + 少量定制 CSS，接近桌面端交互体验

### 1.2 非目标
- 前后端分离架构
- 实时协作/多用户
- 移动端适配（优先桌面浏览器）

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      NiceGUI 单体应用                             │
├─────────────────────────────────────────────────────────────────┤
│  web_app.py                    ← 入口，NiceGUI app 构建           │
│  ├── web/main_page.py          ← 主布局、标签页路由、协议选择器    │
│  ├── web/tabs/                 ← 9大标签页实现                   │
│  │   ├── single_parse.py       ← 单帧解析                        │
│  │   ├── lookup.py             ← 查询                            │
│  │   ├── batch_parse.py        ← 批量解析                        │
│  │   ├── frame_gen.py          ← 协议组帧                        │
│  │   ├── preset_cmd.py         ← 预设命令                        │
│  │   ├── test_plan.py          ← 测试方案                        │
│  │   ├── archive.py            ← 档案管理                        │
│  │   ├── topology.py           ← 拓扑信息                        │
│  │   └── diff.py               ← 报文对比                        │
│  ├── web/components/           ← 共享组件                        │
│  │   ├── protocol_selector.py  ← 协议下拉框 + 级别选择            │
│  │   ├── hex_input.py          ← 十六进制输入框 (清洗/验证)        │
│  │   ├── parse_table.py        ← 解析结果表格 (高亮/双击/右键)     │
│  │   ├── byte_highlighter.py   ← 字节高亮工具                    │
│  │   └── serial_panel.py       ← 串口状态面板                    │
│  └── web/styles/custom.css     ← 定制样式 (紧凑表格/深色表头)     │
├─────────────────────────────────────────────────────────────────┤
│  核心逻辑层 (100% 复用现有模块，零修改)                           │
│  ├── protocol_parser.py        ← 南网协议解析器                   │
│  ├── gdw10376_parser.py        ← 国网协议解析器                   │
│  ├── plc_rf_parser.py          ← PLC RF解析器                    │
│  ├── hdlc_parser.py            ← HDLC/DLMS解析器                 │
│  ├── dlt645_parser.py          ← DLT645解析器                    │
│  ├── dl_t698_45_parser.py      ← 698.45链路层解析器              │
│  ├── dl_t698_45_apdu_parser.py ← 698.45 APDU解析器               │
│  ├── csg_new_gen_parser.py     ← 新一代载波解析器                 │
│  ├── validator/*.py            ← 验证引擎 (BaseValidator+)        │
│  ├── frame_diff_engine.py      ← 对比引擎                        │
│  ├── send_frame_lib.py         ← 南网组帧                        │
│  ├── gdw_send_frame_lib.py     ← 国网组帧                        │
│  ├── dl_t698_45_frame_gen.py   ← 698.45组帧                     │
│  ├── lua_script_engine.py      ← Lua脚本引擎                     │
│  └── serial_worker.py          ← 串口通信 (需异步适配)            │
├─────────────────────────────────────────────────────────────────┤
│  数据持久化 (JSON文件，读写复用现有逻辑)                          │
│  ├── config.json, test_plan.json, archive_data.json, ...         │
│  ├── custom_di.json, gdw_custom_afn.json, dlt645_di_custom.json  │
│  └── NW_command.json, GW_command.json, command.json              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 关键适配点

| 原 PySide6 机制 | Web 适配方案 |
|----------------|-------------|
| `QThread` (SerialWorker) | `asyncio.to_thread` + `asyncio.Queue` + `ui.timer` 轮询 |
| `QTableWidget` 字节高亮 | `ui.table` + `cell_class_name` + CSS 类映射 |
| 双击行提取 APDU | `table.on('rowDblClick', handler)` |
| 右键菜单 (中文复制/粘贴) | `ui.menu` + `ui.item` + `navigator.clipboard` API |
| 动态表单 (组帧 Schema) | `DI_FIELD_SCHEMA` 循环生成 `ui.input`/`ui.select` |
| Monaco/Lua 编辑器 | `ui.editor` (Monaco) + `lua_script_engine.py` 复用 |
| 文件对话框 | `ui.upload` / `ui.dialog` + `input type=file` / `pywebview` 桥接 |

---

## 3. 标签页功能规格

### 3.1 单帧解析
- **输入区**：`ui.textarea` (monospace, placeholder示例帧) + 协议选择器联动提示
- **操作按钮**：解析、校验、添加到测试方案、清空、填充CRC-24、填充CRC-32
- **结果表格**：`ui.table` 4列 (字段、原始值、解析值、说明) + 行点击高亮输入框对应字节
- **校验结果**：可折叠卡片展示 `ValidationResult` 各检查项 (✅/❌/⚠️)
- **导出图片**：`html2canvas` 前端截图下载 PNG

### 3.2 查询
- **南网/国网**：DI/AFN+Fn 表格 (6列)，搜索框过滤，自定义增删按钮，持久化到 `custom_di.json`/`gdw_custom_afn.json`
- **PLC RF**：命令字表格 (2列)，搜索过滤
- **HDLC/DLMS**：OBIS 码表格 (3列)，搜索过滤
- **DLT645**：DI 映射表格，搜索过滤
- **698.45**：OI 对象标识查询表格
- **新一代载波**：业务标识查询表格 (按帧类型分组)

### 3.3 批量解析
- **输入**：大文本域 (支持日志格式：时间戳+序号+监控前缀+报文)
- **解析**：按协议提取帧 (`_extract_frames_for_protocol` 逻辑复用)
- **结果**：摘要表格 (序号、时间、方向、长度、业务摘要、状态) + 点击行展开详细解析
- **导出**：Excel (openpyxl) / JSON / CSV

### 3.4 协议组帧
- **三种模式**：`south`/`gdw`/`dlt698` (由协议索引决定)
- **左侧**：命令选择器 (DI Combo / AFN+Fn Combo / APDU类型+OI预设)
- **右侧**：动态表单 (Schema驱动渲染字段: 输入框/下拉/十六进制/校验位)
- **底部**：预览十六进制、发送、添加到预设、添加到测试方案
- **自定义模式**：字段模板表格 (名称/长度/类型/字节序/显示/反转)

### 3.5 预设命令
- **分组按钮**：按 JSON 分类渲染按钮网格
- **右键菜单**：编辑/删除/发送/添加到测试方案
- **持久化**：`NW_command.json` / `GW_command.json` / `command.json`

### 3.6 测试方案
- **表格 CRUD**：名称、帧HEX、匹配规则(HEX/ASCII/XX通配)、超时ms、性质(普通/Lua脚本)
- **顺序发送**：串口逐行发送，匹配响应，结果列实时更新 (通过/失败/超时)
- **Lua脚本编辑器**：`ui.editor` (Monaco, Lua高亮) + 运行/停止按钮，集成 `LuaScriptEngine`
- **持久化**：`test_plan.json` 自动保存

### 3.7 档案管理
- **仅南网/国网协议可见**
- **树形/表格切换**：设备档案 (TEI、地址、角色、版本、组网时间)
- **搜索/筛选**：TEI精确匹配、多字段模糊
- **统计**：组网完成时间、在线率、角色分布
- **导入/导出**：JSON

### 3.8 拓扑信息
- **仅南网/国网协议可见**
- **网络图**：`topology_graph.py` 复用，`ui.echart` 或 `ui.mermaid` 渲染
- **表格视图**：节点列表 (TEI、地址、角色、父节点、信号强度、最后通信)
- **搜索**：TEI/地址/角色
- **组网完成判定**：比例/数量模式

### 3.9 报文对比
- **双输入区**：A基准 / B对比，支持从单帧解析载入
- **字节级对比**：字段感知对齐 + 差异高亮 (修改/新增/删除色块)
- **字段级语义对比**：表格 (偏移、长度、A值、B值、差异类型、业务含义)
- **人话解读**：自然语言解释差异业务影响
- **配置**：忽略校验和/序列号、仅显示差异
- **导出报告**：HTML/JSON

---

## 4. 共享组件规格

### 4.1 协议选择器 (`ProtocolSelector`)
```python
class ProtocolSelector:
    """协议下拉框 + 新一代载波解析级别 + 字节剔除"""
    protocols = [
        "南网协议 (Q/CSG1209021-2019)",
        "PLC RF协议 (万胜海外 V1_04)",
        "HDLC/国网DLMS (IEC 62056-46)",
        "DLMS-APDU(国网)",
        "DLMS Wrapper裸报文",
        "DLMS-APDU裸报文",
        "DLT645-2007 电表协议",
        "国网协议 (Q/GDW 10376.2-2024)",
        "698.45协议 (DL/T 698.45-2017)",
        "新一代载波协议 (通感一体化)",
    ]
    csg_levels = ["auto", "fc_pb", "fc_efc", "fc_only", "app"]
    strip_bytes = (head: int, tail: int)  # 仅索引9可见
```

### 4.2 十六进制输入框 (`HexInput`)
- 自动清洗：去除空格/逗号/换行/0x前缀
- 实时校验：奇数长度/非法字符红色提示
- 占位符示例：随协议动态更新

### 4.3 解析结果表格 (`ParseTable`)
- **数据源**：`parser.parse_to_table(frame_bytes)` → `List[Tuple[field, raw, parsed, desc, byte_start, byte_end]]`
- **列渲染**：字段名(左对齐)、原始值(monospace)、解析值、说明
- **行高亮**：`cell_class_name` 映射 `byte-{offset}` CSS 类
- **双击事件**：提取该行字节范围 → 若为 DLMS APDU → 弹窗深度解析
- **右键菜单**：复制行/复制字段/复制原始十六进制

### 4.4 串口面板 (`SerialPanel`)
- 端口下拉 (自动刷新)、波特率、校验位
- 打开/关闭按钮 + 状态指示灯 (绿/灰/红)
- 接收区：`ui.log` 或 `ui.textarea` 只读，自动滚动
- 发送区：单行输入 + 发送按钮 (十六进制/ASCII切换)

---

## 5. 串口异步适配方案

### 5.1 原 `SerialWorker` (QThread)
```python
# 信号: data_received(bytes), connection_changed(bool), error_occurred(str)
# 方法: open(port, baud, parity), close(), send(bytes)
```

### 5.2 Web 适配器 (`SerialAdapter`)
```python
class SerialAdapter:
    def __init__(self):
        self._worker = SerialWorker()  # 原对象，移至线程池
        self._rx_queue = asyncio.Queue()
        self._connected = False
        # 绑定原信号到队列
        self._worker.data_received.connect(lambda d: self._rx_queue.put_nowait(d))
        self._worker.connection_changed.connect(lambda c: setattr(self, '_connected', c))
    
    async def open(self, port, baud, parity):
        await asyncio.to_thread(self._worker.open, port, baud, parity)
    
    async def send(self, data: bytes):
        await asyncio.to_thread(self._worker.send, data)
    
    async def receive_loop(self, callback):
        """供 ui.timer 定期调用"""
        while not self._rx_queue.empty():
            data = self._rx_queue.get_nowait()
            await callback(data)
```

### 5.3 NiceGUI 集成
```python
serial = SerialAdapter()

async def on_rx(data):
    # 更新接收日志、触发 Lua 桥接、自动解析等
    ...

# 定时器轮询 (50ms)
ui.timer(0.05, lambda: asyncio.create_task(serial.receive_loop(on_rx)))
```

---

## 6. 样式定制 (`web/styles/custom.css`)

```css
/* 紧凑表格 */
.q-table__row { height: 22px; }
.q-table th { background: #2c3e50; color: white; font-weight: 600; }
.q-table td { font-size: 12px; padding: 2px 8px; }
.q-table__grid-header { border-bottom: 2px solid #34495e; }

/* 字节高亮 */
.byte-highlight { background: #fff3cd !important; }
.byte-modified { background: #f8d7da !important; }
.byte-added { background: #d4edda !important; }
.byte-deleted { background: #e2e3e5 !important; }

/* 卡片紧凑 */
.q-card { padding: 8px; margin: 4px 0; }
.q-card__section { padding: 8px; }

/* 输入框 monospace */
.hex-input textarea { font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 13px; }

/* 标签页指示器 */
.q-tabs__indicator { background: #2196f3; height: 3px; }
```

---

## 7. PyInstaller 打包配置 (`web_app.spec`)

```python
a = Analysis(
    ['web_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('custom_di.json', '.'),
        ('dlt645_di.json', '.'),
        ('gdw_custom_afn.json', '.'),
        ('icons', 'icons'),
        ('web/styles/custom.css', 'web/styles'),
        ('南网新一代20260226校对', '南网新一代20260226校对'),  # 协议文档
    ],
    hiddenimports=[
        'nicegui', 'nicegui.events', 'nicegui.elements',
        'pandas', 'openpyxl', 'crcmod', 'serial', 'lupa',
        'protocol_parser', 'gdw10376_parser', 'plc_rf_parser',
        'hdlc_parser', 'dlt645_parser', 'dl_t698_45_parser',
        'csg_new_gen_parser', 'frame_diff_engine', 'lua_script_engine',
        'validator.nw_validator', 'validator.gdw_validator',
        'validator.hdlc_validator', 'validator.plc_rf_validator',
        'validator.dlt645_validator', 'validator.dl_t698_45_validator',
        'validator.csg_new_gen_validator',
        # NiceGUI 依赖
        'starlette', 'fastapi', 'uvicorn', 'websockets',
        'watchfiles', 'pywebview', 'packaging',
    ],
    excludes=['PyQt5', 'PyQt6', 'PySide6', 'matplotlib', 'scipy', 'numpy', 'PIL', 'tkinter'],
)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name='南网协议解析工具_Web',
    debug=False, strip=False, upx=True,
    console=False,  # GUI模式，启动浏览器
    icon='app_icon.ico',
)
```

> **注意**：NiceGUI 默认启动浏览器需 `console=False` 且 `native_window=True` (pywebview) 或手动 `webbrowser.open`。EXE 体积约 80-120MB。

---

## 8. 实施里程碑

| 里程碑 | 交付物 | 预估工时 |
|--------|--------|----------|
| **M1** | `web_app.py` 骨架 + 协议选择器 + 单帧解析Tab (核心表格/高亮/校验) | 2-3天 |
| **M2** | 查询Tab (6种协议) + 批量解析Tab | 2天 |
| **M3** | 协议组帧Tab (三模式 Schema动态表单，最复杂) | 3-4天 |
| **M4** | 预设命令Tab + 测试方案Tab (含Lua编辑器) | 2-3天 |
| **M5** | 档案管理Tab + 拓扑信息Tab + 报文对比Tab | 2天 |
| **M6** | 串口适配集成 + PyInstaller打包验证 + 端到端回归测试 | 2天 |
| **总计** | **完整可交付 Web 版 EXE** | **13-16天** |

---

## 9. 验收标准

1. **功能完整性**：9大标签页均可正常打开、操作、产出预期结果
2. **协议覆盖**：10种协议单帧/批量解析、查询、组帧、校验均通过现有测试用例
3. **串口通信**：打开端口、发送帧、接收解析、测试方案顺序发送全流程跑通
4. **数据持久化**：所有自定义数据 (DI/AFN/测试方案/档案/预设) 读写 JSON 正常
5. **打包部署**：`pyinstaller web_app.spec` 生成单文件 EXE，双击启动浏览器正常工作
6. **性能**：单帧解析 <100ms，批量1000帧 <5s，表格渲染 500行无卡顿
7. **回归**：现有 `test_*.py` 全部通过，PySide6 版本功能不受影响

---

## 10. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| NiceGUI 表格大数据渲染性能 | 批量解析/对比表格可能卡顿 | 分页/虚拟滚动 (`pagination` + `virtual-scroll`)，必要时仅渲染可见行 |
| 串口异步适配不稳定 | 发送/接收乱序、丢包 | 充分单元测试 `SerialAdapter`，保留 PySide6 版本作为对照基准 |
| PyInstaller 隐藏导入遗漏 | EXE 启动报错 | 依次运行 `test_*.py` 捕获 `ModuleNotFoundError` 补全 `hiddenimports` |
| Monaco 编辑器体积大 | EXE 膨胀 | `lupa` 可选依赖，未安装时禁用 Lua Tab；或动态加载 Monaco CDN |
| 跨平台路径/编码 | Windows 中文路径读写异常 | 统一 `Path(__file__).parent` 定位，UTF-8 读写 JSON |

---

**文档版本**: v1.0  
**下一步**: 调用 `writing-plans` skill 生成详细实施计划