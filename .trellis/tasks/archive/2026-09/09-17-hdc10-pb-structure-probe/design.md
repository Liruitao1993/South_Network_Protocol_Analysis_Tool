# 设计：协议11 PB 结构探测

## 1. 边界与不变量

**唯一改动文件**：`hdc10_parser.py`

| 函数 | 位置 | 改动 |
| --- | --- | --- |
| `HDC10Parser._parse_pb_block` | `hdc10_parser.py:867` | else 分支（`:988`「非帧起始PB」）改为「先做形态探测，再决定回退」 |
| `HDC10Parser._parse_pb_and_mac_header` | `hdc10_parser.py:3026` | `fc_mac` 路径：`data[0]` 无条件当 PBH → 改为复用同一形态判定 |
| `HDC10Parser._probe_pb_form`（新增） | 紧随 `_parse_pb_block` 之后 | 形态探测（打分对拍），单一判据来源 |
| `HDC10Parser._parse_mac_only` | `hdc10_parser.py:3011` | **不改逻辑**，仅确认其 `data[0] & 0x80` 探测与 `_probe_pb_form` 结论不冲突（`mac_only` 输入无 FC，判据天然更弱） |

**不变量**（硬约束）：

1. `dt == 0`（信标帧）路径完全不变 —— 信标 FC 后直接是信标载荷，无 PBH（AGENTS §8 陷阱 15）
2. `pbh` 合法（`bit6 | bit7` 至少一个置位）时走**现有逻辑一字不改**
3. `_parse_mac_frame(data, base_offset, hdr_start=0)` 的既有契约不变
   （`data` 为切片、`base_offset` 为切片首字节在原帧中的**绝对**偏移、`hdr_start` 为 MAC 头在切片内的起点）
4. 表格行 6 元组结构 `(字段, 原始值, 十进制/解析值, 说明, 起始偏移, 结束偏移)` 不变
5. 多 PB 聚合（`_scan_all_pb`，`:999`）路径不变

## 2. 形态探测算法（`_probe_pb_form`）

### 问题本质

`data[0] = 0x10` 在字节层面**不可区分**：

- 解释 A（有 PBH）：PBH → `序列号=16, 帧起始=0, 帧结束=0`（规范不允许首块如此）
- 解释 B（无 PBH）：MAC 头首字节 → `版本=0（标准帧协议）+ 源TEI 低 8 位 = 0x10`

因此**必须用内容证据裁决**，而非位域。

### 打分对拍

对两个假设 `pbh_len ∈ {1, 0}` 分别按同一组**内容判据**打分，取高分者；
**平局或双方都低于阈值时保持现有行为（视为有 PBH）** —— 保守优先，保证 R5 无回归。

判据（对假设 `L = pbh_len`，`mac_off = L`）：

| 判据 | 条件 | 分值 |
| --- | --- | --- |
| C1 MAC 版本合法 | `len(data) > mac_off` 且 `(data[mac_off] & 0x0F) in (0, 1)`；版本 0 时要求剩余 ≥ 28 字节（标准头含 MAC 地址） | +2 |
| C2 MAC 头自洽 | 版本 0：`MAC地址标志`（`data[mac_off+11] & 0x01`）与剩余长度自洽；版本 1：剩余 ≥ 4 | +1 |
| C3 MSDU 类型已知 | 版本 0 取 `data[mac_off+7]`、版本 1 取 `data[mac_off+1]`，值 ∈ `{0} ∪ APP_MSDU_TYPES ∪ IPV4_MSDU_TYPES`（`{48,128}` / `{49,129}`） | +2 |
| C4 MSDU 长度合法 | 版本 0：`b8 \| ((b9 & 0x07) << 8)`；版本 1：`(b2 << 3) \| (b3 & 0x07)`；要求 `> 0` 且 `mac_off + mac_hdr_len + msdu_len <= len(data)` | +1 |
| C5 **ICV 校验通过** | `crc32(msdu) == int.from_bytes(帧尾 ICV 4 字节, 'little')`（按 MSDU 长度精确定位） | **+3** |
| C6 应用层可定位 | 在 `[mac_off + mac_hdr_len, +msdu_len)` 范围内能定位合法通用头：`data[i] ∈ APP_PORTS` 且 `报文ID` 合法（低 12 位 ∈ `MSG_ID_NAMES`）且 `报文控制字 == 0` | **+3** |

阈值：`score >= 2` 才认为该假设成立（仅 C2/C4 这类弱判据不足以裁决）。
两条假设的 `pbh_len=1` 与 `pbh_len=0` 互为对照 —— 例如对现场帧：
`L=1`（MAC 头从 `0x00` 起）→ C1/C3/C4 全败（MSDU 长度 1792）、`L=0` → C1~C6 全过（C5 独得 +3）→ **选 L=0**。

### 与既有实现的关系

- `_detect_mac_header(data)`（`:358`）**复用**为 C1 的一级快速筛选，但**不作为唯一判据**
  （它对 `ver=1` 且长度任意时恒真，单独用会把中间 PB 误判为 MAC 帧）
- **不移植** `gw_new_gen_parser._locate_pbh_mac`：它依赖 FC 的源/目的 TEI 强匹配，
  而两协议对 FC 可变区域（`FC[4:12]`）的解释不同（本任务非目标），TEI 不可靠；
  且 parser 间避免横向耦合（AGENTS §9.4）。判据全部取自**帧内自洽性**，不依赖 FC

## 3. 回退路径行为

选定「无 PBH」后：

```python
table.append(("── 物理块(PB) ──", "", f"{len(data)}字节",
              "⚠ 未检测到合法物理块头(PBH)，按无 PBH 形态解析（依据：MAC 头/ICV 自洽）", ...))
mac_table = self._parse_mac_frame(data, base_offset)   # hdr_start 默认 0 → 即 data[0]
table.extend(mac_table)
```

要点：

- **尾部处理**：无 PBH 时无法可靠判断是否存在 `PBCS(3B)`，故**不预先剥离**。
  `_parse_mac_frame` 依赖 MSDU 声明长度精确定位 ICV，多余字节会作为既有的
  「帧尾多余数据」行显示（本帧即 41 字节 `00` 填充）—— 信息不丢且不误判
- 若尾部 3 字节恰好构成合法 PBCS（`crc24(data[:-3]) == int.from_bytes(data[-3:], 'little')`），
  额外输出一行「尾部 PBCS ✓」作为**加分标注**（不影响解析主流程）
- **不做**「剥离 3 字节后再解」的猜测式处理 —— 避免重演「PBH 硬判」的同类错误

## 4. `fc_mac` 入口（`_parse_pb_and_mac_header`）

现状：无条件 `pbh = data[0]` + `mac_data = data[1:]` → PBH 缺失时 MAC 头整体错位 1 字节。
改为与 `_parse_pb_block` 同源：

```python
pbh_len, _score = self._probe_pb_form(data)
# pbh_len == 1 → 现有行为（输出 PB头 行 + 从 data[1:] 解 MAC 头）
# pbh_len == 0 → 输出形态提示行 + 从 data[0:] 解 MAC 头（不输出 PB头 行）
```

**必须同源**：第二处独立判据即是 AGENTS 反复记录的「两份清单漂移」缺陷模式（§8 陷阱 44/47）。

## 5. 兼容性与风险

| 风险 | 处置 |
| --- | --- |
| 把真实「中间 PB」（PBH 合法但 `sof=eof=0`）误判为无 PBH | 中间 PB 的 `data[0]` 是 PBH（低 6 位=序列号），其后的 `data[1:]` 是 MAC 帧体中部 —— C1/C3/C4 极难同时命中，且阈值 ≥2 要求内容自洽 |
| 合法 PBH 帧（`0x40/0x80/0xC0` 开头）行为改变 | `bit6\|bit7` 置位即走原路径，探测根本不触发 ✓ |
| 日志截断帧（无尾部填充） | C4 放宽为 `<= len(data)`；C5 在 ICV 不完整时自然不加分，其余判据仍可裁决 |
| `pb_only` 输入无 FC | `_parse_pb_block` 的探测不依赖 FC ✓（这正是选择「帧内自洽」判据的原因） |
| 多 PB 聚合回归 | `_scan_all_pb` 不变；探测只在**首个 PB 的 PBH 非法**时介入 |

## 6. 验证策略

1. **现场帧 golden**：`auto`/`fc_pb`/`fc_mac`/`pb_only` 四入口均含应用层报文段（A1/A5）
2. **双协议对拍**：同帧在 `GWNewGenParser`（协议10）与 `HDC10Parser`（协议11）下的
   MAC/应用层关键字段逐项相等（A2）
3. **回归指纹**：`test/hdc10_real_frames.pkl` 60 帧在 `pb_only` 下逐行 sha256 对拍，
   与改动前基线一致（A4）—— 基线在改动**前**先采集
4. **变异反证**：把 `_probe_pb_form` 强制返回 `(1, 99)`（等价还原硬判）→ 期望 A1/A2/A5 断言变红（A7）

## 7. 回滚

改动集中在 `hdc10_parser.py` 单文件（2 处修改 + 1 个新增 helper）与新增测试文件。

- 回滚点：提交前可 `git checkout -- hdc10_parser.py`；提交后 `git revert <sha>`
- 无数据/配置迁移，无跨版本兼容负担（解析器纯函数）

## 8. 实际改动清单（执行后回填）

`hdc10_parser.py`（1 文件 5 处）：
1. 模块常量 `_PB_PROBE_MIN_SCORE = 4`（`APP_PORTS` 之后）
2. 新增 `HDC10Parser._probe_pb_form(self, data) -> Tuple[int, int]`，返回 `(pbh_len, score)`；
   score ≥ 阈值才采信探测结果，否则回落「有 PBH」（与改动前一致）
3. `_parse_pb_block` 的 SOF 分支：未显式给出帧类型时改走探测，命中「无 PBH」时输出
   「物理块(PB) - 未检测到合法物理块头」行交代形态与依据
4. `_parse_pb_and_mac_header`：PBH 剥离改走探测；**并修正 `_parse_mac_header` 的偏移传参**
   （`base_offset + 1` → `0`，配合已切片的数据），这是 fc_mac 级别错位的根因
5. `_parse_meter_reading`：补齐字节6/7（设备超时时间 / 选项字 / 上行 16bit 选项字）

新增 `test/test_hdc10_pb_structure_probe.py`（39 项）并登记 `release_check.py:CORE_TESTS`。
版本链：`APP_VERSION = 1.23.24` + `BUILD_DATE = 2026-09-17`、CHANGELOG、README「更新记录」、
AGENTS.md（§8 陷阱 51 新增 + §10 摘要）、两个 `.iss` 由 `release_check.py --sync-iss` 同步。
