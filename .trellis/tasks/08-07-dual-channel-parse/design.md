# 设计：南网/国网新一代双通道（PLC/HRF）解析

## 架构总览

在现有解析器中增加 `channel` 参数（`"plc"` 或 `"hrf"`），控制 FC 可变区域的解析路径。GUI 新增通道下拉框，切换时传入解析器。

```
┌──────────────────────────────────────────────┐
│ GUI                                          │
│  [解析级别] [通道: PLC▼] [帧类型]             │
└───────────────┬──────────────────────────────┘
                │ channel = "plc" / "hrf"
                ▼
┌──────────────────────────────────────────────┐
│ 解析器（CSGNewGenParser / GWNewGenParser）    │
│                                              │
│  parse_to_table(..., channel="plc")          │
│    └─ _parse_fc / _parse_mpdu_frame          │
│         └─ channel == "hrf" ?                │
│            ├─ 是 → HRF 可变区域解析分支       │
│            └─ 否 → 原有 PLC 解析路径         │
└──────────────────────────────────────────────┘
```

## 数据结构

### 新增常量表

```python
# 两个解析器共用
MCS_TABLE = {
    0: {"diversity": 4, "modulation": "BPSK", "code_rate": "1/2"},
    1: {"diversity": 2, "modulation": "BPSK", "code_rate": "1/2"},
    2: {"diversity": 2, "modulation": "QPSK", "code_rate": "1/2"},
    3: {"diversity": 1, "modulation": "QPSK", "code_rate": "1/2"},
    4: {"diversity": 1, "modulation": "QPSK", "code_rate": "4/5"},
    5: {"diversity": 1, "modulation": "16QAM", "code_rate": "1/2"},
    6: {"diversity": 1, "modulation": "16QAM", "code_rate": "4/5"},
}

HRF_PB_SIZE_TABLE = {
    0: 16, 1: 40, 2: 72, 3: 136, 4: 264, 5: 520,
}
```

### config.json 新增

```json
{
  "csg_channel": "plc",
  "gw_channel": "plc"
}
```

## 详细设计

### 1. GUI 层（main_gui.py）

**南网侧**：在 `csg_parse_level_combo` 旁边加 `csg_channel_combo`
- 选项："PLC 载波" / "HRF 无线"
- 默认 "plc"
- 切换回调：`_on_csg_channel_changed` → 设置 `self._csg_channel` → 若输入有内容自动重新解析
- 可见性：协议索引 9 时显示

**国网侧**：在 `gw_parse_level_combo` 旁边加 `gw_channel_combo`
- 选项同上
- 切换回调：`_on_gw_channel_changed`
- 可见性：协议索引 10 时显示

**传入解析器**：在 `_get_current_parser()` 的 CSG/GW 包装类中增加 `channel` 参数透传到 `parse_to_table()`。

### 2. 南网新一代解析器（csg_new_gen_parser.py）

**parse_to_table 增加 channel 参数**（默认 `"plc"` 保持兼容）。

**`_parse_mpdu_frame` 增加 HRF 分支**：
- 信标帧（类型0）：channel=hrf 时调用新方法 `_parse_mpdu_beacon_hrf`
- SOF 帧（类型1）：channel=hrf 时调用新方法 `_parse_mpdu_sof_hrf`
- SACK 帧（类型2）：channel=hrf 时调用新方法 `_parse_mpdu_sack_hrf`
- 网间协调帧（类型3）：暂用 PLC 逻辑（HRF 也类似，后续再细化）

**`_get_pb_size` 增加 channel 参数**：
- channel=hrf 时从 `HRF_PB_SIZE_TABLE` 查
- channel=plc 时走原有逻辑

**PB 遍历**：HRF 模式下只解析 1 个 PB（`_parse_pb_block` 只跑 1 次）。

**新增方法**：
- `_parse_mpdu_sof_hrf(rows, data, offset)` — 无线 SOF 可变区域解析
- `_parse_mpdu_beacon_hrf(rows, data, offset)` — 无线信标可变区域解析
- `_parse_mpdu_sack_hrf(rows, data, offset)` — 无线 SACK 可变区域解析

### 3. 国网新一代解析器（gw_new_gen_parser.py）

**parse_to_table 增加 channel 参数**（默认 `"plc"`）。

**`_parse_fc_vf` 增加 HRF 分支**：
- 信标帧：channel=hrf 时调用 `_parse_fc_vf_beacon_hrf`
- SOF 帧：channel=hrf 时调用 `_parse_fc_vf_sof_hrf`
- SACK 帧：channel=hrf 时调用 `_parse_fc_vf_sack_hrf`

**新增 PB size 查表函数** `_get_hrf_pb_size(idx)`（6 种）。

**新增方法**：
- `_parse_fc_vf_beacon_hrf` — 国网版无线信标可变区域
- `_parse_fc_vf_sof_hrf` — 国网版无线 SOF 可变区域
- `_parse_fc_vf_sack_hrf` — 国网版无线 SACK 可变区域

### 4. 可变区域字段映射（关键）

**南网 HRF 信标可变区域**（68bit，字节1-12低3b）：
参考文档 4-第4部分 行1347-1369（表42）
- 信标时间戳：32bit
- 信标周期计数：32bit
- 源TEI：12bit
- MCS：4bit
- 载荷PB大小：4bit
- 保留：4bit
- SNID 高位：1bit
- 保留：3bit

**南网 HRF SOF 可变区域**（表45，行1412-1452）：
- 源TEI：12bit
- 目的TEI：12bit
- 链路标识符：8bit
- 帧长：12bit（单位100μs）
- 载荷PB大小：4bit
- MCS：4bit
- TEI过滤标志：1bit
- 重传标志：1bit
- 保留：34bit
- SNID高位：1bit

**国网 HRF 信标**（表18，国网版第4-2部分 行814）
**国网 HRF SOF**（表19，行835）

具体 bit 分配需在实现时仔细对照文档，按字节/位操作解析。

## 兼容性

- `channel` 参数默认 `"plc"`，所有现有调用不受影响
- 批量解析、监控器等未修改路径行为不变
- 未传 `channel` 的外部调用保持 PLC 行为

## 风险

- **位操作复杂**：FC 可变区域 68bit 跨字节分配，HRF 版字段排布与 PLC 完全不同，需要逐位核对文档
- **两协议文档差异**：南网版和国网版的 HRF 可变区域字段布局可能不同（相似但不一定完全一致），需分开实现
- **PB 解析边界**：HRF 只有 1 个 PB，大小从 PB 大小字段取（PLC 是从 TMI 推导），需注意传入 `_parse_pb_block` 的 PB 大小来源

## 回滚

- 移除 GUI 通道下拉框及相关方法
- 解析器中移除 channel 参数和 HRF 相关方法
- config.json 残留字段无害
