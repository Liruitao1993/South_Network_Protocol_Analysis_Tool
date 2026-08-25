# Implement: 协议8 安徽补充规约对象解析增强

## 前置核对

- [ ] 确认文档 OI 与现有映射无冲突（0x20xx/0x35xx/0x8000 已存在，仅补缺失 17 个）
- [ ] 确认 AXDRCoder 支持 long64-unsigned / date_time_s / bit-string / structure / array / boolean（已确认）

## 实现步骤（按依赖序）

### 1. OI 名称与类绑定（dl_t698_45_oi_lookup.py）

增加 17 个 OI 到 `OI_NAME_MAP` 与 `OI_TO_CLASS_ID`：
- 0x2801 发电量 IC6、0x2802 发电时间 IC6
- 0x3060/3061/3062/3063/3065/3066/3095/3096 IC7（光伏开关/逆变器控制/通信异常事件）
- 0x3097 光伏越限事件单元 IC8、0x3361 逆变器控制事件记录单元 IC8、0x3363 控制指令事件单元 IC8
- 0x4039 逆变器档案单元 IC8、0x4820 光伏逆变器 IC19、0x4822 分布式电源调控调度计划表 IC8、0x4823 分布式电源调控调度计划单元 IC8

`CLASS_ID_MAP` 补充类 6/7/8/19 相关属性名与 4820 的方法 127/128 名（若 OILookup 的处理含方法则同步）。

### 2. generate_oi_lookup.py 保留段

因 OI_NAME_MAP 是生成脚本产物，在脚本中新增 `ANHUI_EXTRA = {...}` 常量并在合并处追加，保证重跑不丢失手动项。同时注释标注。

### 3. 单位/属性提示（dl_t698_45_data_decode.py）

`OI_UNIT_HINT` 新增/修正：
- 0x2801: ("kWh", -4)、0x2802: ("min", 0) （发电时间单位分）
- 0x2004 有功功率: ("W", -1)、0x2005 无功功率: ("var", -1)——现有缺失，且 infer_unit_hint 会兜底成 W/-3 与文档 -1 不符，必须显式登记
- 0x200A 功率因数: ("", -3)——现有缺失（无单位）
- 0x2000 电压 V/-1、0x2001 电流 A/-3、0x200F 电网频率 Hz/-2 已有且与文档一致，不重复
- 0x4039/0x4820 等无需单位提示（structure/enum 为主）

### 4. 属性模板（CLASS_ATTR_TEMPLATES + 新解码器）

按类/属性新增模板：
- (6, 2/4/5/6) 发电量/发电时间：新增 type `long64_value`/`double_long_unsigned_value`，带 attr_map 区分总/当日/当月/当年与单位换算
- (7, 2) 事件记录表：type `event_record_array`，按 OI 分派标准事件/控制事件记录单元
- (8, 2) 各 structure 单元：type `struct_decode`，带 struct_spec
- (19, 2/3/5/6) 光伏逆变器：属性2 基础信息 structure、属性3 运行状态 enum、属性5 额定容量 double-long-unsigned kW、属性6 本地调控参数 structure

新增编码函数：
- `_decode_long64_value` / `_decode_double_long_unsigned_value`（单值 + 换算）
- `_decode_struct_by_spec`（structure 成员 spec 驱动）
- `_decode_event_record_array`（标准/控制事件记录单元 array）
- `_decode_bit_string_status`（bit-string 状态字逐位命名）
- `_map_enum`（enum 值→名称，兜底显示原值）

### 5. 方法参数解码（dl_t698_45_data_decode.py + dl_t698_45_apdu_parser.py 最小接入）

在 `dl_t698_45_data_decode.py` 新增 `ACTION_METHOD_SPECS = {(oi, method_id): SPEC}` 与 `decode_action_parameter(oi, method_id, data_dict)`：
- (4820, 127) 开关机 enum{开机0/关机1}
- (4820, 128) 控制负荷 structure{调节方式 enum(0-6), 调节值 Data}
- (4822, 127) 添加调控计划 array 调控调度计划单元
- (4822, 128) 删除调控计划 array long-unsigned
- (4822, 129) 清除调控计划 NULL
- (8000, 129) 跳闸 array structure{遥控单元 OAD, 告警延时 unsigned 分, 限电时间 long-unsigned 分, 自动合闸 bool}
- (8000, 130) 合闸 array structure{遥控单元 OAD, 命令 enum{合闸允许0/直接合闸1}}

`dl_t698_45_apdu_parser.py` 的 `_parse_action_request` Normal 分支（L1600-1608）与 NormalList 分支（L1620-1632）在 `result["参数"]` 解析后调用 `decode_action_parameter`，用 `result["OMD"]["解析值"]` 取 OI/方法标识，结果补「方法参数」键。未匹配 spec 返回 None 不破坏原解析。

### 6. 测试（test/test_dl_t698_45_data_decode.py 新增用例）

- test_anhui_generation_volume：2801 属性2 long64-unsigned → 总发电量 kWh 换算
- test_anhui_generation_time：2802 属性2 → 总发电时间 分
- test_anhui_struct_event_unit：3361/3097 structure 成员解码
- test_anhui_event_record_array：3060 属性2 事件记录表 array
- test_anhui_inverter_basic_info：4820 属性2 基础信息 + 属性3 运行状态 enum + 属性5 额定容量
- test_anhui_inverter_archive：4039 属性2 structure
- test_anhui_action_jump：8000 方法129 跳闸参数
- test_anhui_action_switch：4820 方法127 开关机
- test_anhui_lookup_names：OILookup 覆盖 17 OI、类绑定正确

## 验证命令

```bash
cd "E:\python\南网解析工具"
python -m py_compile dl_t698_45_oi_lookup.py dl_t698_45_data_decode.py dl_t698_45_apdu_parser.py generate_oi_lookup.py
python test/test_dl_t698_45_data_decode.py   # 新增用例 + 原有全过
python test/test_dl_t698_45.py
python test/test_dl_t698_45_fujian.py
python test/test_gdw_fujian.py
python test/test_oad_enrichment.py
```

## 回滚点

- 每完成一步，确认 py_compile + 相关测试通过再继续。
- 全部改动集中在 4 文件，git checkout 可整体回滚。
