# GUI 协议组帧页新增「EB 数据标识 645/698 帧生成器」

## 背景

Web 版（Reflex）已有 EB 数据标识 645/698 组帧能力（附件1 本地通信模块扩展协议），但 GUI 组帧页（`frame_gen_widget.py`）没有。GUI 当前：福建增补 AFN 50H~56H 组帧已可用（`GDW_AFNFN_SCHEMA` 自动含），但 52H-F1 透明转发 / 56H-F2 事件上报的「报文内容」只能手填 hex。

**目标**：把 Web 版 EB 645/698 生成器移植进 GUI，放在协议7（国网）组帧模式，选择 EB 数据标识 → 按字段表单配置数据内容 → 生成 645 帧或 698.45 完整帧 → 一键填入当前命令的「报文内容」字段。

## 核心决策

1. **纯逻辑层直接复用**：Web 版的核心逻辑 `build_eb_698_frame` / `build_dlt698_sa` / `build_eb_698_apdu`（`reflex_web/frame_gen_utils.py`）、`encode_eb_di_data` + `EB_DI_FIELDS`（`gdw_eb_di_fields.py`）、`get_eb_di_lookup`（`gdw_eb_di_lookup.py`）都是无 Qt/Reflex 依赖的纯 Python。GUI 直接 import 复用，不做重复实现。已实测这些函数在项目根目录下可正常调用。
   - 645 帧组装逻辑很简短（`68 A0..A5 68 C L DI3 DI2 DI1 DI0 DATA CS 16`），在 GUI 里内联实现（同 Web `gen_eb_645_frame`），不引 `reflex_web/reflex_web/reflex_web.py`（依赖 Reflex）。
2. **放 GUI 左侧面板，独立 GroupBox**：`frame_gen_widget.py` 左侧是命令选择 → 帧配置 → 字段表单 → 生成按钮。EB 生成器作为一个新的可折叠 `QGroupBox`（`eb_gen_group`），放在字段表单区之上、命令选择/帧配置之下，仅 `protocol_mode == "gdw"` 时可见（与 Web 版定位一致：协议7 透明转发报文内容辅助）。
3. **「填入报文内容」= 写字段 widget**：GUI 已有 `_field_widgets[name]["widget"]` 结构。填入时按当前 GDW 命令 schema 查找 `name == "报文内容"`（或首个 bytes 字段）对应的 widget，若是 `QLineEdit` 直接 `setText`（会触发 `textChanged` → 实时组帧自动更新）。与 Web 版 `apply_eb_frame_to_content` 行为一致。
4. **表单渲染复用现有字段渲染**：EB 数据内容的字段表单复用 `_create_field_widget`（已支持 uint8/uint16/uint32/enum/bytes/ascii/bcd/list 等，正好覆盖 `EB_DI_FIELDS` 用到的类型：enum/uint8/uint16/uint32/bcd/bcd_time/ascii/hex/bs8/list）。bcd_time 需在 `_create_field_widget` 走默认 QLineEdit 分支（已有 else 兜底）。
5. **生成结果展示**：生成按钮点击后把帧 hex 写入 `result_hex`（大写、空格分隔），并额外显示在 EB 生成器内的只读行（方便区分是 EB 帧而非主帧）。

## 涉及文件

| 文件 | 改动 |
| --- | --- |
| `frame_gen_widget.py` | 主体：新增 EB 生成器 UI + 逻辑（约 350 行） |
| `frame_gen_widget.py` `set_protocol_mode` | 在 `gdw` 分支显示 `eb_gen_group`，其它模式隐藏 |
| `frame_gen_widget.py` `reset` | 重置 EB 生成器状态 |
| `test/test_gdw_fujian.py` | 新增 EB 645/698 组帧 GUI 无关断言（用纯逻辑函数，不引 Qt） |
| `main_gui.py` | 追加 CHANGELOG 条目 |
| `AGENTS.md` | §10/§11 相关条目（EB 生成器 GUI 支持） |

## 实施步骤

### 1. 新增 `EBFrameGenPanel`（或直接方法组）到 `FrameGenWidget`

在 `frame_gen_widget.py` 的 `setup_ui` 中，`self.mode_group` 之后、`form_scroll` 之前插入 `eb_gen_group`（QGroupBox「EB 数据标识 645/698 帧生成器（协议7）」，checkable=True，默认展开）。内含：

- 承载格式下拉：`645 帧（68 封装）` / `698.45 完整帧`
- EB 数据标识下拉（`get_eb_di_lookup().get_all()` 填充，`code + 名称` 作条目文本，code 作 data）
- **645 模式**：控制码下拉（91/11/14/94/81/01，同 Web）、地址域 A0~A5 hex 输入、数据内容 hex 输入（或字段表单）
- **698 模式**：服务类型下拉（8 种，同 Web `EB698_SERVICE_TEMPLATES`）、数据内容来源（按字段 / 自由 hex）、698 链路层头部（SA 类型/长度/hex、CA、DIR、PRM、功能码）、数据字段表单
- 按钮：`生成帧`、`填入报文内容`、消息 label（成功/错误）

### 2. 数据字段表单（EB 数据内容）

选 EB 数据标识后，若 `EB_DI_FIELDS` 有定义则用 `_create_field_widget` 渲染字段表单到 EB 生成器内的一个滚动容器 `_eb_fields_container`；否则仅自由 hex 输入。`_collect_eb_values` 复用 `_collect_values` 的收集逻辑（list 用 `widget._items`）。

### 3. 生成逻辑

```python
def _gen_eb_frame(self):
    # 645: 68 addr 68 C L DI DI DI DI DATA CS 16 （同 web gen_eb_645_frame）
    # 698: from frame_gen_utils import build_eb_698_frame, build_dlt698_sa
    #      sa = build_dlt698_sa(addr_type, logic_addr, addr_len, sa_raw)
    #      frame = build_eb_698_frame(di, service, data_hex, sa=sa, ca, dir_bit, prm_bit, func_code)
    # 数据内容：字段模式用 encode_eb_di_data(di, values)，自由模式直接 hex
    # 写 self.eb_gen_frame（hex 小写无空格），显示到 result_hex（大写空格分隔）
```

`build_dlt698_sa(addr_type, logic_addr, addr_len, sa_raw)` 的 addr_type 即地址类型（0/1/2/3），logic_addr 固定取 0（GUI 当前 698 页面有 logic 下拉，这里简化为 0，或用 addr_len 传 6/16）。为对齐 Web，复用其参数：`addr_type`(0~3)、`addr_len`、`sa_raw`；`logic_addr` 固定 0。

### 4. 填入报文内容

```python
def _apply_eb_to_content(self):
    schema = GDW_AFNFN_SCHEMA.get(self._current_afn_fn, {})
    target = None
    for f in schema.get("fields", []):
        if f.get("name") == "报文内容":
            target = f; break
    if target is None:
        for f in schema.get("fields", []):
            if f.get("type") == "bytes":
                target = f; break
    wi = self._field_widgets.get(target["name"]) if target else None
    if not wi or not isinstance(wi.get("widget"), QLineEdit):
        msg("当前命令无「报文内容」字段"); return
    wi["widget"].setText(self.eb_gen_frame)
```

### 5. 模式切换/重置接线

`set_protocol_mode`：`self.eb_gen_group.setVisible(mode == "gdw")`；`reset` 里重置 EB 控件与 `_eb_fields_container`。

### 6. 测试

在 `test/test_gdw_fujian.py` 增加：
- `test_eb_645_frame`：645 帧结构 `68..68..16`、CS 校验、`EB030002` 字节序
- `test_eb_698_frame`：复用 `build_eb_698_frame`，对照附件1 文档示例逐字节（直接复用 web 测试断言逻辑）

### 7. 文档

`main_gui.py` CHANGELOG 追加一条；`AGENTS.md` 相关小节更新。

## 验收标准

1. GUI 协议7 组帧页出现「EB 数据标识 645/698 帧生成器」，可选 EB 标识 → 生成 645/698 帧 → 填入 52H-F1 报文内容字段，实时预览正确更新
2. 698 帧与 Web 版 / 附件1 文档示例逐字节一致（复跑 `test/test_web_frame_gen_utils.py` 不回归）
3. `python test/test_gdw_fujian.py` 新增用例通过
4. 南网/698.45 组帧模式不显示 EB 生成器，原有功能不破坏
5. GUI 启动无异常，组帧页在协议 0/7/8 切换正常
