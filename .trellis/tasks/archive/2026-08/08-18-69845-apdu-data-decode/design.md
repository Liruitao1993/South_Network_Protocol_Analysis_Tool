# Design：协议8（698.45）APDU 数据内容深度解析

## 1. 目标

在现有链路层/APDU 结构解析之上，为 APDU 数据内容（DATA）增加**业务格式解码**：按 698.45 对象属性定义，把 A-XDR 原始数据解码为可读业务值（数值+单位、时间、枚举说明）。

## 2. 现状（已确认）

- `DLT69845APDUParser.parse()` 解析 APDU：服务码/PIID/OAD/DAR/数据（A-XDR 原始）
- `OILookup`：OI_NAME_MAP（762 OI→名称）、OI_TO_CLASS_ID、CLASS_ID_MAP（29 类→{attributes: {编号: 属性名}, methods}）
- `AXDRCoder`：支持全部基础类型编解码（array/structure/octet-string/double-long/Scaler_Unit/date_time_s/enum/bool 等）
- 缺口：`_parse_get_response` 等解析出 `数据`（如 octet-string 原始值），但**无业务解码**——不知道 OAD 对应的数据是电压还是电能量、单位是什么、如何换算

## 3. 设计

### 3.1 新增 `dl_t698_45_data_decode.py`：业务数据解码模块

**核心：按 (class_id, attr_id) → 数据格式模板**。类决定属性数据类型（文档 §8.2），OI 决定具体业务语义（名称/单位）。

```python
# 类属性 → A-XDR 结构模板（class_id, attr_id）→ 模板
CLASS_ATTR_TEMPLATES = {
    # 电能量类 (1): 属性2 总及费率电能量数组
    (1, 2): {"type": "energy_array", "name": "总及费率电能量数组"},
    (1, 4): {"type": "energy_array", "name": "扩展精度总及费率电能量数组", "extended": True},
    (1, 30): {"type": "energy_array_q", "name": "带品质的总及费率电能量数组"},
    # 最大需量类 (2): 属性2 总及费率最大需量数组（值+发生时间）
    (2, 2): {"type": "demand_array", "name": "总及费率最大需量数组"},
    # 分相变量类 (3): 属性2 分相数值数组（A/B/C相）+ 属性3 Scaler_Unit
    (3, 2): {"type": "phase_array", "name": "分相数值数组"},
    (3, 31): {"type": "phase_array_q", "name": "带品质的分相数值数组"},
    # 功率类 (4): 属性2 总及分相数值数组
    (4, 2): {"type": "phase_array", "name": "总及分相数值数组"},
    # 数据变量类 (7): 属性2 数据（值）+ 属性3 换算及单位
    (7, 2): {"type": "data_value", "name": "数据"},
    # 事件对象类 (7 事件?): 属性2 事件记录（structure）
    ...
}
```

### 3.2 业务解码器

按模板类型解码（输入：AXDRCoder 已解码的 dict 结构 + OI 业务信息）：

| 模板 | A-XDR 结构 | 业务输出 |
|---|---|---|
| `energy_array` | array of long-unsigned/double-long-unsigned | 每元素换算后 `1234.56 kWh`（费率0=总） |
| `energy_array_q` | array of structure {值, 品质VQDS} | 值+品质说明（有效/无效/非当前等） |
| `demand_array` | array of structure {需量值 CHOICE, 发生时间 date_time_s} | `12.34 kW @ 2024-05-01 12:00:00` |
| `phase_array` | array（A/B/C 相值） | 逐相 `220.5 V` / `5.2 A` |
| `data_value` | 单值（数值） | 换算后值+单位 |
| `time` | date_time/date_time_s/date/time | `2024-05-01 12:00:00` |
| `enum` | enum | 值→文档说明 |
| `scaler_unit` | structure {换算, 单位} | `×10⁻¹ kWh` 等 |

**Scaler_Unit 换算**：`value × 10^scaler`（scaler 有符号整数）。电能量常用 scaler=-3（0.001）→ 原始 `1234567` → `1234.567 kWh`；电压 scaler=-1 → 原始 `2205` → `220.5 V`。

### 3.3 OI 业务信息补充

现有 `OI_NAME_MAP` 有 OI 名称（如 0x0000 = 组合有功电能）。需要补充**单位/默认换算**（文档附录 B 或对象实例约定）：
- 电能量 OI：默认单位 kWh，scaler 由属性3 提供（响应中通常含换算属性）或默认 -3
- 电压 OI（0x2000 等分相变量）：V，scaler -1
- 电流：A，scaler -3 或 -1
- 功率：W/kW，scaler 依对象

设计：`OI_UNIT_HINT = { 0x0000: ("kWh", -3), 0x2000: ("V", -1), ... }`——仅在响应未带属性3 时作为默认；若响应含属性3（Scaler_Unit），优先用响应值。

### 3.4 APDU 解析器接入

在 `_parse_get_response` / `_parse_set_request` / `_parse_action_request` / `_parse_report_notification` 的 `数据` 解码后，调用业务解码：

```python
# 解码后的原始 A-XDR 数据（如 octet-string/double-long-unsigned）
raw_data = result["数据"]
# 业务解码：按 OAD 查类模板 + OI 单位提示
biz = decode_oad_data(oad_oi, oad_attr, raw_data, axdr_coder)
if biz:
    result["数据"] = raw_data            # 保留原始
    result["数据业务"] = biz             # 新增业务解读
```

`decode_oad_data(oi, attr_id, data_dict)`：
1. `class_id = OILookup.OI_TO_CLASS_ID.get(oi)`
2. `template = CLASS_ATTR_TEMPLATES.get((class_id, attr_id))`；无模板 → 返回 None（保留原始）
3. 按模板解码 data_dict → 业务值列表/字符串

**列表对象（NormalList）**：`GetResponseNormalList` 的每个 item 独立调用。

### 3.5 GUI 表格展示（dl_t698_45_parser.py）

`_add_apdu_to_table` 增加对 `数据业务` 键的处理：若值是 dict/列表，递归展开显示业务行（如 `数据业务 → 总电能量: 1234.56 kWh`）；若字符串，直接一行。

不破坏现有 `数据` 行（原始 A-XDR 仍显示）。

### 3.6 文件清单

- 新增：`dl_t698_45_data_decode.py`（模板表 + 业务解码器 + OI 单位提示）
- 修改：`dl_t698_45_apdu_parser.py`（接入业务解码）
- 修改：`dl_t698_45_parser.py`（GUI 表格展示业务值）
- 修改：`dl_t698_45_oi_lookup.py`（可选：OI_UNIT_HINT 或独立映射）
- 修改：`test/test_dl_t698_45.py`（数据解码测试）

## 4. 兼容性

- 业务解码结果放在**新增键**（`数据业务`），原始 `数据` 不变 → 现有解析/测试不破坏
- 无模板的 OAD 数据 → 保持现状（原始 A-XDR）
- 解码失败 → 捕获异常，回退原始值，不报错

## 5. 风险

| 风险 | 缓解 |
|---|---|
| Scaler_Unit 取值不确定 | 优先用响应中属性3；无则用 OI_UNIT_HINT 默认；再无可显示原始值 |
| instance-specific 数值类型多样 | 按 A-XDR 实际类型（long/double-long/long-unsigned）通用处理，Scaler 换算统一 |
| 事件/冻结记录结构复杂 | 先做常用测量/需量/时间/枚举，复杂记录保留原始解码（后续迭代） |
| 测试帧构造 | 用 DLT69845FrameGenerator 构造 + 文档示例字节对照 |
