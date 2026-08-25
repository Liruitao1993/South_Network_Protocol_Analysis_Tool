# Design: 协议8 安徽补充规约对象解析增强

## 数据流（既有链路，无结构变更）

```
parse_batch / parse_single
  → DLT69845Parser（链路层）→ DLT69845APDUParser（APDU）
    → AXDRCoder.decode(data) → data_dict（含 类型/解析值）
      → _decode_oad_business(oad, data_dict)
        → decode_oad_data(oi, attr_id, data_dict)   ← 增强点
          → CLASS_ATTR_TEMPLATES 查模板 → 分派解码函数
```

`decode_oad_data` 是唯一业务解码入口，`_decode_oad_business` 已接入 APDU 的 GET/SET/ACTION/REPORT 各分支。**无需改 APDU 解析器主体结构**，只需增加新模板与解码函数 + 方法参数解码。

## 关键决策

### D1: 模板驱动，复用现有 `CLASS_ATTR_TEMPLATES` 机制

现有模板键 `(class_id, attr_id)` → `{type, name, ...}`，decode_oad_data 按 `type` 分派。为支持安徽新对象：

- 新增 `type` 值：`"long64_value"`（long64-unsigned 单值）、`"double_long_unsigned_value"`、`"struct_decode"`（自定义 structure 解码回调）、`"event_record_array"`（事件记录表 array 展开）、`"control_event_unit"`（控制事件记录单元）、`"bit_string_status"`（bit-string 状态字命名）。
- 每个模板可带 `"unit"`/`"scale"`（覆盖 infer_unit_hint）、`"attr_map"`（属性编号→字段名/单位/换算，如 2801 属性2/4/5/6）、`"struct_spec"`（structure 成员定义）。
- `infer_unit_hint` 保留为默认回退；新增 OI 优先在 `OI_UNIT_HINT` 显式登记。

属性 per-attr 差异（2801/2802 的 属性2/4/5/6 同字段不同换算）用模板的 `"attr_map"` 在 decode_oad_data 里按 `attr_id` 匹配子定义，替代单一 `unit_hint`。

### D2: structure 解码用「成员规格字典」驱动

文档大量 structure 定义（3097 光伏越限事件单元、3361 逆变器控制事件记录单元、3363 控制指令事件单元、4039 逆变器档案单元、4820 属性6 本地调控参数、4823 调控调度计划单元）。统一用：

```python
STRUCT_SPECS = {
    # OI 或其(oi,attr) → [{"name":..., "type":"enum|unsigned|...","enum_map":{0:".."}, "unit":..., "scale":...}, ...]
}
```

解码函数 `_decode_struct_by_spec(data_dict, spec)` 遍历 structure 成员（AXDR 已解出成员 dict 列表），按 type/enum_map 命名、按 unit/scale 换算。嵌套 structure/array 用递归。

### D3: 事件记录表统一走标准/控制事件记录单元

- `标准事件记录单元` = {序号, 发生时间, 恢复时间(可选), 发生源 TSA/instance-specific, 上报状态} —— 现有 `_decode_energy_array_q` 等不适用，新增 `_decode_event_record_array`。
- `逆变器控制事件记录单元`（3361）= {序号, 发生/结束时间, 发生源, 上报状态, 调节类型 enum(远程0/自动1/电压越限2...), 调节方式 enum(有功1...), 调节值 Data}。
- 3060-3063 属性2 复用 3361 结构；3065/3066/3095/3096 属性2 复用标准事件记录单元。

### D4: 方法参数解码（ACTION-Request）

文档定义方法：4820 方法127 开关机(enum 开机0/关机1)、方法128 控制负荷(structure 调节方式+调节值)；4822 方法127 添加/128 删除/129 清除调控计划；8000 方法129 跳闸/130 合闸。

方法参数解码函数 `decode_action_parameter(oi, method_id, data_dict)` 放 `dl_t698_45_data_decode.py`（纯函数，可单测）。APDU 解析器仅在 `_parse_action_request` 的 Normal / NormalList 分支 `result["参数"]` 解析后调用一次，补「方法参数」键——用 `result["OMD"]["解析值"]` 的 OI/方法标识定位 spec。不匹配的 (OI, method) 返回 None，不影响既有解析。

### D5: 新增 OI 名称与类绑定（生成脚本机制已确认）

`generate_oi_lookup.py` 的机制：**OI_NAME_MAP 从源码原样提取回写**（L262-268，手动追加即保留），**OI_TO_CLASS_ID / CLASS_ID_MAP 从脚本内置字典生成**（L300/L273）。

因此：
- `OI_NAME_MAP`：直接在 `dl_t698_45_oi_lookup.py` 手动追加安徽 OI，脚本重跑会原样保留。
- `OI_TO_CLASS_ID` 与 `CLASS_ID_MAP`：必须在 `generate_oi_lookup.py` 的 `oi_to_class` / `CLASS_ID_MAP` 字典里加安徽项，同时在源码手动同步——否则脚本重跑会丢掉安徽的类绑定。
- 各文件追加处标注"安徽分布式电源接入单元补充规约（2025）手动追加"。

### D6: 状态字/原因码 bit-string 与 enum 映射

- 2042 断路器运行状态字 bit-string(8)：bit0 命令状态/bit1 实际状态/bit2 合闸允许/bit3 用户行为/bit4 手自动/bit5 强磁保护。新增 `decode_bit_string_status` 逐位命名。
- 2608 断路器变位原因 enum（0~63 全表）；2606 设备故障原因。合并入现有 enum 映射字典（若现有 OILookup 无则新增）。

## 数据流（方法参数）

```
ACTION-Request 解析 → 得到 (OI, method_id, 参数 A-XDR)
  → decode_action_parameter(oi, method_id, data_dict)
    → ACTION_METHOD_SPECS 查规格 → 分派（enum/struct/array 解码）
  → result["方法参数"] = {...}
```

## 兼容性

- 新模板/解码函数为**纯新增**，不修改现有 `CLASS_ATTR_TEMPLATES` 已有条目。
- `decode_oad_data` 入口签名不变，新 type 值在既有 if 链后追加 else-if，不影响旧返回。
- 名称/类绑定为追加，不改既有 OI 的已有名称。
- 方法参数解码为独立函数，未匹配 spec 时返回 None，不破坏现有 ACTION 解析。

## 风险与回滚

- 风险：结构定义与实报文可能有偏差（文档个别单元格乱序/错字，如 3062 含重复文本）。对策：以主表（134-146 行）明确结构为准，散乱表格（138/142/146/150 行）仅取 enum 表补充；解码失败时保留原始 A-XDR，不返回错误。
- 回滚：全部改动集中在 `dl_t698_45_data_decode.py` / `dl_t698_45_oi_lookup.py` / `dl_t698_45_apdu_parser.py` / `generate_oi_lookup.py` 四个文件，git checkout 即可回滚。
