# 实现计划：南网/国网新一代双通道（PLC/HRF）解析

## 执行顺序

### Step 1: 新增常量表 + 工具函数
- `csg_new_gen_parser.py`：新增 `MCS_TABLE`、`HRF_PB_SIZE_TABLE`
- `gw_new_gen_parser.py`：新增同样的两张表（各自一份，避免跨模块依赖）
- 验证：单元测试查表

### Step 2: 南网新一代解析器 HRF 分支
- `parse_to_table` 增加 `channel="plc"` 参数
- `_parse_mpdu_frame` 增加 channel 传递
- 新增 `_parse_mpdu_sof_hrf` — 无线 SOF FC 可变区域解析
- 新增 `_parse_mpdu_beacon_hrf` — 无线信标 FC 可变区域解析
- 新增 `_parse_mpdu_sack_hrf` — 无线 SACK 可变区域解析
- `_get_pb_size` 增加 channel 参数（hrf 走 HRF_PB_SIZE_TABLE）
- PB 遍历时 hrf 模式只取 1 个 PB
- 验证：用用户提供的国网无线帧先测结构（南网的后续找报文验证）

### Step 3: 国网新一代解析器 HRF 分支
- `parse_to_table` 增加 `channel="plc"` 参数
- `_parse_fc` / `_parse_fc_vf` 增加 channel 传递
- 新增 `_parse_fc_vf_beacon_hrf` — 国网无线信标可变区域
- 新增 `_parse_fc_vf_sof_hrf` — 国网无线 SOF 可变区域
- 新增 `_parse_fc_vf_sack_hrf` — 国网无线 SACK 可变区域
- 验证：用用户提供的 `00 3A CF 9E E0 A8 12 69 A7 A0 BE 06 00 42 6D 29` 测试

### Step 4: GUI 通道下拉框（南网侧）
- `create_single_parse_tab` 解析级别旁加通道下拉框
- 协议切换时可见性控制（协议9可见）
- 切换回调 + 自动重解析
- `_get_current_parser` CSG 包装类传 channel
- 持久化到 config.json

### Step 5: GUI 通道下拉框（国网侧）
- 对应位置加通道下拉框
- 协议10可见
- 切换回调 + 自动重解析
- `_get_current_parser` GW 包装类传 channel
- 持久化

### Step 6: 批量解析 + 监控器适配（可选，MVP 不含）
- 批量解析传入 channel
- 监控器传入 channel
- 本次 MVP 跳过，单帧先验证

### Step 7: 验证
1. 南网 PLC 模式解析现有报文，结果不变（回归）
2. 国网 PLC 模式解析现有报文，结果不变（回归）
3. 国网 HRF 模式解析用户提供的信标帧，字段正确
4. 南网 HRF 模式用构造报文测试字段映射
5. MCS 表显示正确
6. PB 大小查表正确（6 种）
7. 通道切换自动重解析
8. 持久化（关了重开还在）

## 高风险点

- **位操作**：68bit 可变区域跨字节拆分，字段 bit 偏移需仔细核对文档
- **南网 vs 国网 HRF 格式差异**：两版文档的无线可变区域字段排布可能不一致，需分别实现
- **解析器包装类改造**：`CSGGenGuiParser` / `GWGenGuiParser` 包装类需新增 channel 参数传递
- **国网 PB 大小**：国网 PLC 模式本来就没有显式 PB size 表，HRF 模式新增的表只用在 HRF 分支

## 回滚点

- Step 1：删除新常量表（无害）
- Step 2/3：解析器内新方法独立，删除即可；channel 参数有默认值，移除调用即可
- Step 4/5：删除 GUI 控件代码块，config.json 残留无害
