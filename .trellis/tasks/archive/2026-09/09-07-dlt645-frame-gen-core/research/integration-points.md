# Research: 接入点清单（GUI / 主程序 / Web / 预设）

- **Query**: 新增协议 6（dlt645）组帧模式必须触碰的具体函数与行号
- **Scope**: internal
- **Date**: 2026-09-07
- **来源**: `frame_gen_widget.py`(3855)、`main_gui.py`(10359)、`reflex_web/reflex_web/reflex_web.py`(10612)、`reflex_web/frame_gen_utils.py`(597)、`preset_buttons.py`(502)

> 全部行号已实测核对（2026-09-07）。模式串统一用 **`"dlt645"`**（对齐现有 `"south"/"gdw"/"dlt698"` 命名风格），协议索引 **6**。

---

## A. GUI 接入点 — `frame_gen_widget.py`

### A.1 现有三模式结构（参照）
| 元素 | 行号 | 说明 |
|---|---|---|
| `preset_added = Signal(str,str,dict)` | `:55` | (protocol_mode, frame_hex, config) |
| `test_plan_added = Signal(str,str)` | `:57` | (name, frame_hex) |
| `self.protocol_mode = "south"` | `:62` | 当前模式 |
| `self.generator = ProtocolFrameGenerator()` | `:63` | 南网 |
| `self.gdw_generator = GDWFrameGenerator()` | `:65` | 国网 |
| `self.dlt698_generator = DLT69845FrameGenerator()` | `:67` | 698.45 |
| `_populate_di_combo` | `:1087` | 南网 DI 下拉填充（调用点 `:119`） |
| `_populate_afn_fn_combo` | `:1099` | 国网 AFN+Fn 下拉（调用点 `:133`） |
| `_populate_dlt698_combo` | `:1367` | 698 APDU 下拉（调用点 `:310`） |
| `_collect_values` | `:2630` | 按 mode 取 schema 收集字段值 |
| `_on_generate` | `:3140` | 分派到 _generate_* |
| `_generate_south_frame` | `:3151` | 南网组帧 |
| `_generate_gdw_frame` | `:3194` | 国网组帧 |
| `_generate_dlt698_frame` | `:3246` | 698 组帧 |
| `_on_send_to_serial` | `:3383` | 串口发送（按钮绑定 `:466`） |
| `_on_add_to_preset_clicked` | `:3394` | 加预设（按钮绑定 `:472`） |
| `set_protocol_mode(mode)` | `:3763` | **模式切换总入口** |
| `reset()` | `:3813` | 复位 |

### A.2 关键分支代码（实测摘录）
`_on_generate`（`:3140-3147`）：
```python
if self.protocol_mode == "south":   self._generate_south_frame()
elif self.protocol_mode == "dlt698":self._generate_dlt698_frame()
else:                               self._generate_gdw_frame()   # gdw
```
`_collect_values` schema 选择（`:2659-2664`）：
```python
if self.protocol_mode == "south":   schema = DI_FIELD_SCHEMA.get(self._current_di_key, {})
elif self.protocol_mode == "dlt698":schema = DLT69845_FIELD_SCHEMA.get(self._current_dlt698_key, {})
else:                               schema = GDW_AFNFN_SCHEMA.get(self._current_afn_fn, {})
```
`set_protocol_mode`（`:3763-3808`）：
```python
if mode not in ("south", "gdw", "dlt698"):   # :3765 白名单
    return
self.protocol_mode = mode
# 隐藏 di_combo/afn_fn_combo/dlt698_combo + 三个 config_group (:3770-3775)
if mode == "south":  ...di_combo+south_config_group (:3778-3782)
elif mode == "dlt698":...dlt698_combo+dlt698_config_group (:3783-3788)
else:                ...afn_fn_combo+gdw_config_group (:3789-3792)
self.eb_gen_group.setVisible(mode == "gdw")   # :3795
```

### A.3 新增 dlt645 模式**必须触碰**的函数与行号
| # | 位置 | 改动 |
|---|---|---|
| G1 | `__init__` `:67` 后 | 新增 `self.dlt645_generator = DLT645FrameGenerator()`（新模块） |
| G2 | `set_protocol_mode` `:3765` | 白名单加 `"dlt645"`：`("south","gdw","dlt698","dlt645")` |
| G3 | `set_protocol_mode` `:3770-3775` | 隐藏区新增 `self.dlt645_combo.setVisible(False)` + `self.dlt645_config_group.setVisible(False)` |
| G4 | `set_protocol_mode` `:3789` else 前 | 新增 `elif mode=="dlt645":` 分支：设标题、显示 dlt645_combo + dlt645_config_group、隐藏 mode_custom_rb（按需） |
| G5 | `_on_generate` `:3142-3147` | 新增 `elif self.protocol_mode=="dlt645": self._generate_dlt645_frame()` |
| G6 | 新方法（仿 `:3151`） | 新增 `_generate_dlt645_frame()` |
| G7 | `_collect_values` `:2632-2640` + `:2659-2664` | 新增 dlt645 的「当前命令键」判空 + schema 选择分支（`DLT645_FIELD_SCHEMA`） |
| G8 | 命令选择区（仿 `:102-145` cmd_select_group） | 新增 `dlt645_combo` 控件 + `_populate_dlt645_combo()`（数据源 `get_dlt645_di_lookup()` + `FUNC_NAMES`） |
| G9 | 配置区（仿 `:147-182` south_config_group） | 新增 `dlt645_config_group`：地址输入（单地址 6B，非源/目的）、DIR/异常/后续帧勾选、功能码选择 |
| G10 | `reset` `:3813` | 复位 dlt645_combo 选择 + 当前键 |

> 注：645 地址模型与南网/国网不同——**只有一个从站地址（6B）**，无源/目的双地址；广播校时用全 0x99。config_group 字段需按 645 特性重新设计（不能照抄 south 的 src/dst）。

---

## B. 主程序接入点 — `main_gui.py`

### B.1 关键锚点（实测）
| 元素 | 行号 |
|---|---|
| `self.protocol_combo.addItem("[6] DLT645-2007 电表协议")` | `:1222`（协议 6 已在下拉存在） |
| `self._pending_frame_gen_mode = "south"` | `:1058` |
| `_ensure_frame_gen_tab` | `:2861`（`:2869` 读 mode，`:2870` set_protocol_mode，`:2871` preset_added.connect） |
| index==6 单帧输入占位符 | `:3022-3025`（已有 645 示例） |
| **tab 可见性 `show_frame_gen = index in (0,7,8)`** | `:3052` |
| frame_gen mode 分派 | `:3054-3061`（index0→south,7→gdw,else→dlt698） |
| `frame_gen_tab.set_protocol_mode(mode)` | `:3063` |
| **预设 tab 可见 `index in (0,7,8)`** | `:3068` |
| **虚拟表 tab 可见 `index == 8`** | `:3070`（`:3071-3078` preset_tab.set_protocol 分派） |
| `preset_tab.set_protocol(mode)` | `:3078` |
| 档案 tab 可见 `index in (0,7)` | `:3081` |
| 拓扑 tab 可见 `index in (0,7)` | `:3093` |
| **协议短名映射 `short_names`** | `:5781`，`:5788` = `6: "DLT645-2007 电表协议"`（已存在） |

### B.2 放开协议 6 组帧**必须改**的每一处
| # | 位置 | 改动 |
|---|---|---|
| M1 | `:3052` | `show_frame_gen = index in (0,6,7,8)` |
| M2 | `:3054-3060` | mode 分派加 `elif index==6: mode="dlt645"` |
| M3 | `:3068` | 预设 tab 可见加 6：`index in (0,6,7,8)` |
| M4 | `:3071-3077` | preset_tab.set_protocol 的 mode 分派加 `index==6→"dlt645"`（**注意此块当前嵌在 `if index in (0,7,8)` 内，需同步改为含 6**） |
| M5 | `:3070` | **需用户决定**：虚拟表 tab 是否对协议 6 开放（当前仅 index==8） |
| M6 | `:3081` | **需用户决定**：档案 tab 是否对 645 开放（当前 0,7；645 解析已有 archive 用途？） |
| — | `:1222`, `:5788`, `:3022` | 协议 6 下拉/短名/占位符**已存在，无需改** |

---

## C. Web 接入点 — `reflex_web/`

### C.1 `reflex_web.py` 关键锚点（实测）
| 元素 | 行号 |
|---|---|
| `_build_frame_bytes(self)` | `:2318` |
| `p == 0`（南网）分支 | `:2325-2381` |
| `p == 7`（国网）分支 | `:2383-2430` |
| `p == 8`（698.45）分支 | `:2432-2512` |
| **`raise ValueError(f"协议 {p} 暂不支持组帧")`** | `:2514` |
| `async def generate_frame` | `:2516` |
| gen_* 状态变量（gen_di_key/gen_afn_fn/gen_dlt698_apdu/gen_dlt698_sub） | `:84-88` |
| 下拉选项 di_options/afn_fn_options/dlt698_* | `:149-152` |
| on_load 加载 _load_di_options/_load_afn_fn_options/_load_dlt698_options | `:336-340`（`_load_di_options` 从 DI_FIELD_SCHEMA 生成，约 `:1929`） |

### C.2 `frame_gen_utils.py` 契约（实测）
- `collect_field_values(field_schema, gen_field_values:List[str], gen_list_rows:List[List[List[str]]], gen_sub_fields:List[List[str]]) -> Dict[str,Any]`（`:129-190`）：
  - **位置对齐列表**：`gen_field_values[i]`=字段 i 原始值；`gen_sub_fields[i][j]`=字段 i 第 j 子字段；`gen_list_rows[i][r][j]`=字段 i 第 r 行第 j item。
  - 有 `sub_fields`（`:149-163`）：按 sub_name 收集，父值由生成器 Pass3 打包，本函数不算父值。
  - `list`（`:165-177`）/`oad_list`（`:179-182`）特判；其余用 `parse_field_value`（`:188`）；空值取 default（`:186-187`）。
- `generate_custom_data(templates) -> bytes`（`:193-230+`）：对应 GUI `_generate_custom_data`；checksum 占位末尾回填 `sum(data)&0xFF`（`:197,209-211`）。

### C.3 Web 新增 dlt645**必须改**
| # | 位置 | 改动 |
|---|---|---|
| W1 | `_build_frame_bytes` `:2514` 前 | 新增 `if p == 6:` 分支（仿 `:2325` 南网：import DLT645FrameGenerator + collect_field_values + generate_frame） |
| W2 | 状态变量 `:84-88` 后 | 新增 dlt645 gen_* 状态（如 `gen_dlt645_cmd`、地址、DIR 等） |
| W3 | 下拉选项 `:149-152` 后 | 新增 `dlt645_cmd_options`（或复用 DI 下拉） |
| W4 | on_load `:336-340` | 新增 `_load_dlt645_options`（数据源 `get_dlt645_di_lookup()` + `FUNC_NAMES`） |
| W5 | UI badge（约 `:6463`） | 「支持组帧」判断加 `current_protocol==6` |
| — | `collect_field_values` | **无需改**（通用契约，dlt645 复用） |

> ⚠️ 注意区分：`reflex_web.py:168-170` 的 `eb_di_options`/`gen_eb_di` 是**国网 EB 数据标识的 645 子生成器**（`gen_eb_645_frame` 约 `:1550`），**不是独立协议 6**，勿混淆。

---

## D. 预设命令库 — `preset_buttons.py`

### D.1 关键锚点（实测）
| 元素 | 行号 |
|---|---|
| `NW_COMMAND_PATH = data_path("NW_command.json")` | `:28` |
| `GW_COMMAND_PATH` / `DLT698_COMMAND_PATH` | `:29` / `:30` |
| 模块级 `_get_path(protocol)` | `:33-38`（south→NW, dlt698→DLT698, else→GW） |
| `PresetButtonManager`（load/save/add/remove） | `:41` |
| `AddPresetDialog` | `:94`；`proto_names` `:111`（south/gdw/dlt698） |
| `PresetButtonWidget.set_protocol` | `:212`；白名单 `:214` `protocol in ("south","gdw","dlt698")`；`proto_display` `:217` |
| 实例 `_get_path`（self） | `:274-280`（south→_nw_path, dlt698→None, else→_gw_path） |
| `_on_button_clicked` | `:354`；`proto_display` `:366` |
| `_on_serial_frame_received` | `:391`；parser 分支 `:396-403`（south→ProtocolFrameParser, else→GDW10376Parser） |

### D.2 预设 JSON 结构（`DLT698_command.json:1-31`）
```json
{ "commands": [ {
    "protocol": "dlt698", "button_name": "柔控命令", "group_name": "常用查询",
    "frame_hex": "68 1F 00 ... 16",           // 空格分隔
    "description": "...",
    "config": { "protocol_mode":"dlt698", "current_di_key":null, "current_afn_fn":null,
                "custom_mode":false, "south":{...}, "gdw":{...}, "dlt698":{...} }
} ] }
```

### D.3 新增 dlt645 预设**必须改**
| # | 位置 | 改动 |
|---|---|---|
| P1 | 新文件 | 新增 `DLT645_command.json`（结构同上，`protocol:"dlt645"`，config 加 `dlt645:{...}`）；常量 `DLT645_COMMAND_PATH = data_path("DLT645_command.json")`（仿 `:30`） |
| P2 | 模块级 `_get_path` `:33-38` | 加 `if protocol=="dlt645": return DLT645_COMMAND_PATH` |
| P3 | `AddPresetDialog.proto_names` `:111` | 加 `"dlt645":"DLT645-2007 协议"` |
| P4 | `set_protocol` 白名单 `:214` | 加 `"dlt645"` |
| P5 | `set_protocol.proto_display` `:217` | 加 `"dlt645":"645"` |
| P6 | 实例 `_get_path` `:274-280` | 加 dlt645 分支（返回 None 走模块默认，或专用路径） |
| P7 | `_on_button_clicked.proto_display` `:366` | 加 `"dlt645":"645"` |
| P8 | `_on_serial_frame_received` `:396-403` | 加 `elif self._protocol=="dlt645": parser=DLT645Parser()` 分支（回读解析，`DLT645Parser.parse` 返回 dict 非 table，需适配 key_fields） |
| P9 | `load_buttons`（`:288`） | 按 protocol 过滤逻辑确认兼容 "dlt645"（现用 `cmd.get("protocol",self._protocol)==self._protocol`，天然兼容） |

---

## Caveats

- **地址模型差异**：645 单地址（6B 从站地址）vs 南网/国网双地址（src/dst）。GUI config_group、Web 状态变量、preset config 的 `south:{src_addr,dst_addr}` 结构不能照搬，需为 645 设计单地址字段。
- **`_on_serial_frame_received` 解析器返回结构不同**：`DLT645Parser.parse` 返回 dict（含 `fields` 列表），而 `ProtocolFrameParser/GDW10376Parser` 用 `parse_to_table`；P8 需写适配层提取关键字段。
- 虚拟表 tab（M5）、档案 tab（M6）是否对协议 6 开放属**产品范围决策**，见摘要。
- Web badge 行号（约 `:6463`）来自前次会话，本次未逐行复核，落地前需再确认。
