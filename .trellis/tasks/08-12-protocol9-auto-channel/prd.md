# PRD：协议9 通道自动识别（PLC / HRF）

## 背景

协议9（通感一体化）是双模协议（PLC 载波 + HRF 高速无线）。当前用户在 GUI 手动选择「PLC 载波 / HRF 无线」通道（`csg_channel_combo`），解析级别 `parse_to_table(channel=...)` 按所选通道解析 FC 可变区域。用户在真实抓包中无法总是预先知道通道，需要自动识别。

## 需求

1. `CSGNewGenParser.parse_to_table` 支持 `channel="auto"`：MPDU 级输入自动判别 PLC / HRF 并选择对应 FC 可变区域解析路径。
2. GUI 通道下拉（`main_gui.py` `csg_channel_combo`）新增「自动识别」项（data=`"auto"`），**设为默认**；配置持久化跟随现有 `_csg_channel` 机制。
3. 判别结果在解析结果中可见：新增一行「通道判定」显示识别出的通道及依据。

## 判别算法（已与文档核对 + 实测验证）

MPDU（≥16B，接入指示=1）入口，定界符=1（SOF 帧）时按三种假设分别预测 MPDU 帧长，与实际帧长一致者胜：

| 假设 | 依据 | PB大小 | 预测帧长 |
|---|---|---|---|
| HRF | 表45：载荷PB大小 = byte6[4-7]（表44: 0=16,1=40,2=72,3=136,4=264,5=520） | 表44 | 16 + PB |
| PLC-BPLC | 表20：物理块个数 = byte7[0-3]，载波映射表索引 = byte7[4-7]（136/520） | ROBO | 16 + 个数×PB |
| PLC-ISAC | 表23：物理块个数 = byte4[2-5]，TMI = byte6[1-5]（0=136,1=520,2=72,3=264） | 表13 | 16 + 个数×PB |

强信号优先（无需长度比对）：
- 载荷PB大小=40 → HRF（表44 值1 为 HRF 独有，PLC 无 40B PB）
- 物理块个数>1 → PLC（无线仅支持 1 个物理块，图6）
- 解析到 MAC 帧后版本2（单跳帧协议）→ HRF（表6 仅无线支持）

其他情况：
- 定界符≠1：信标帧可按「PLC 信标 PB 仅 136/520 → 帧长 152/536；其余 → HRF」判定；SACK/NET（仅 16B FC）默认 PLC（无载荷，影响小）
- 非 MPDU 输入（MAC/MSDU/应用层裸数据）：无 FC 无需判别，默认 plc；MAC 帧版本2 由 `_parse_mac_frame` 自动走单跳解析（既有行为）
- 平局（多假设同时命中）：优先 PLC（更常见），解析后若 MAC 帧版本2 再修正为 HRF

## 约束

- 仅改 `csg_new_gen_parser.py`（判别 + auto 分支）+ `main_gui.py`（下拉加「自动识别」默认项）。
- 不改变现有 `channel="plc"/"hrf"` 显式指定行为（回归全绿）。
- 判别函数不得产生表格副作用（只读 FC 字节）。

## 验收标准

1. 用户实际 PLC 帧（152B，`09 00 F0 FF ...`）`channel="auto"` 解析 → 通道判定=PLC，可变区域按表20 解析（与显式 plc 结果一致）。
2. 合成 HRF MPDU（152B）`channel="auto"` 解析 → 通道判定=HRF，可变区域按表45 解析（与显式 hrf 结果一致）。
3. 显式 `channel="plc"/"hrf"` 行为不变；`test_csg_new_gen.py` / `test_csg_hrf_mac.py` 全绿。
4. GUI 通道下拉含「自动识别」且默认选中；切换协议/重启后配置持久化。