# 技术设计：协议8 A-XDR 数据域大端化

## 1. 根因

协议8 存在**两层字节序**，实现只做对了一层：

| 层 | 字段 | 标准要求 | 现状 |
|---|---|---|---|
| 链路层 | 长度域 L(2B)、HCS(2B)、FCS(2B)、地址域 SA 反转 | **小端**（文档 L347） | 正确（`dl_t698_45_parser.py` L62/L214/L239 用 `little`）|
| APDU | A-XDR 全部多字节字段（DL/T 790.6-2010） | **大端** | **错误**（`dl_t698_45_axdr.py` 14 处 `little` + `struct.unpack('<f'/'<d')`）|

判据（协议文档自带，可复查 `协议文档/8.698.45协议/面向对象的用电信息数据交换协议(20210910).md`）：

- §7.1（L599）：APDU 编码规则遵循 A-XDR，详见 DL/T 790.6—2010。
- 附录 H.1.1（L5574-5626）：
  - `00 B4` = 心跳周期 **180s**（小端会读成 46080）
  - `07 E0` = **2016** 年；`00 A4`=164、`02 5F`=607、`02 DA`=730（毫秒）
  - 三者只有按大端成立。

本项目内**已有的正确先例**（说明大端才是既定结论，只是没落到通用解码器上）：

- `dl_t698_45_axdr.py` L310-311：`date_time_s` 年份已按大端，注释直接引用「文档 H.1 例: 07 E0 = 2016」。
- `dl_t698_45_axdr.py` L310 注释 + `dl_t698_45_apdu_parser.py` L310-311：EB 扩展数据标识内容按大端
  （645 减33逆序规则），注释写明「多字节 uint 高位在前（大端）」，`test_dl_t698_45_fujian.py` 有断言。
- `dl_t698_45_frame_gen.py` L211：组帧的 OAD 用 `struct.pack(">H", oi)`（大端）。
- 协议12 的同类修复（AGENTS.md 陷阱 61）已把「链路层小端 / A-XDR 大端」写成上线契约。

矛盾点即 bug 现场：**同一帧里 OAD 的 OI 用大端（0x2004 正确），紧随其后的数据元素却用小端**，
于是 `FF FF 9E D0` 被读成 `0xD09EFFFF = -794886145`（官方工具/标准：`0xFFFF9ED0 = -24880`）。

## 2. 改动清单

### W1 A-XDR 大端化（`dl_t698_45_axdr.py`）

解码（`'little'` → `'big'`，多字节才有效果；单字节保持但注释说明）：

| 行 | 方法 | 类型 | 附加动作 |
|---|---|---|---|
| L146 | `_decode_double_long` | 4B 有符号 | 说明「(小端)」→「(大端)」|
| L153 | `_decode_double_long_unsigned` | 4B 无符号 | 同上 |
| L132 / L139 | `_decode_long` / `_decode_long_unsigned` | 2B | 同上 |
| L160 / L167 | `_decode_long64` / `_decode_long64_unsigned` | 8B | 同上 |
| L181 / L188 | `_decode_float32` / `_decode_float64` | IEEE754 | `'<f'/'<d'` → `'>f'/'>d'` |
| L266 / L285 | `_decode_date_time` / `_decode_date` | 年(2B) | 大端；`_decode_date_time` 毫秒同步改为 `(val[8]<<8)|val[9]` |
| L326 / L334 / L348 | `_decode_OI` / `_decode_OAD` / `_decode_OMD` | OI(2B) | 大端（与 apdu_parser/frame_gen 一致）|
| L360 | `_decode_TI` | 间隔值(2B) | 大端 |
| L394 | `_decode_Scaler_Unit` | scaler(1B) | 无需改（单字节），仅确认 |

编码（同文件 L413-474，`'<'` → `'>'`）：`_encode_long/long_unsigned/double_long/
double_long_unsigned/long64/long64_unsigned/float32/float64/OI/OAD/OMD`。
单字节 `'<b'/'<B'` 保留（无端序），但为可读性可统一成无前缀形式并注释。

> 关键点：编码侧必须同步，否则「组帧→解析」自洽性被打破（AC4）。

### W2 组帧侧（`dl_t698_45_frame_gen.py`）

属 APDU/A-XDR 的 2 字节字段改为大端；链路层不动：

| 行 | 字段 | 改为 |
|---|---|---|
| L54 / L62 | LINK-Request/Response 心跳周期 | `' >H'` |
| L174 | 组帧 schema「心跳周期」| `'>H'` |
| L178 | 客户机APDU最大长度 | `'>H'` |
| L182 | 期望帧最大帧长 | `'>H'` |
| L184 | 期望超时时间 | `'>H'` |
| L18 / L34 | FCS / 长度域 | **保持小端** |
| L211 | OAD | 已是大端，保持 |

### W3 LINK 预连接不带 tag（`dl_t698_45_apdu_parser.py` L1204-1260）

标准表38/39：`LINK-Request::=SEQUENCE{ PIID-ACD, 请求类型 ENUMERATED, 心跳周期, date_time }`；
`LINK-Response::=SEQUENCE{ PIID, 结果 Result, 请求时间, 收到时间, 响应时间, 时钟可信标志 }`。
SEQUENCE 内定长字段**不带 tag、不带长度域**（同协议12 陷阱 61 的规则），目前实现却调用
`self.axdr.decode()` 逐个当带 tag 元素解 → 标准示例在 `0xB4`/`0x80` 处报「未知类型」。

改法：改为按定长切分读取（1B PIID / 1B 请求类型·结果 / 2B 心跳周期(大端) /
10B date_time ×N / bit7 时钟可信标志），日期用现有 `_decode_date_time` 语义解析但**不带 tag 前缀**。

> 验收锚点：AC2/AC3（标准示例能解析且时间正确）。风险：若某些厂家帧确实带 tag，会由「解析失败」
> 变为「解析错位」——但标准示例是唯一权威判据，且当前实现连标准示例都失败，故不构成回退风险。

### W4 相邻检查（只查不改，除非是同类小端硬编码）

- `dl_t698_45_data_decode.py`：消费 A-XDR 解析值做单位换算；检查 L227/L232（已大端）之外有无 `'little'`。
- `dl_t698_45_oi_lookup.py` / `validator/dl_t698_45_validator.py`：CRC 与小端无关，确认不动。
- `meter_sim_data.json` + `meter_sim/archive.py`：194 个 OI 的 A-XDR 原始值来源需确认（真实表/开源 config
  即大端，修完反而正确；若曾用本工具编码器生成，则需重新生成）。**只记录结论，不擅自重生成**。
- `reflex_web/`：Web 复用同一 parser，无需单独改。

## 3. 契约（写入 spec / AGENTS.md）

> 协议8 两层字节序：链路层（L/HCS/FCS/地址）+ 组帧长度域 = **小端**；APDU 内 A-XDR
> 全部多字节字段 = **大端**。两层不可互相套用；`int.from_bytes` 必须显式写字节序。

## 4. 兼容性与风险

- **用户可见变化**：协议8 所有多字节解析值都会变（从错误变正确）。这是本次修复的目的，
  需在 CHANGELOG 明确写出「修复字节序错误，历史解析值作废」。
- **自洽性**：解析↔组帧必须同时改，否则本工具「组帧后回解析」出现新矛盾。
- **历史数据**：`meter_sim_data.json` 若由本工具编码器生成过，需人工确认（W4）。
- **回归面**：`test/test_dl_t698_45*.py`、`test_dlt698_preset.py` 中的期望值可能按小端写死，需重写并在
  commit 说明；协议0/6/7/9/10/11/12 测试必须保持全绿（未触及）。

## 5. 验证策略

1. **oracle 测试**（新增 `test/test_dl_t698_45_endian.py`）：直接引用文档 H.1.1 三个示例 + 用户实测帧，
   断言 180 / 2016 / 164 / 607 / 730 / -24880。
2. **既有测试**：`test_dl_t698_45.py`、`test_dl_t698_45_data_decode.py`、`test_dl_t698_45_fujian.py`、
   `test_dlt698_preset.py` 全跑。
3. **跨协议抽查**：`test_dl_t698_45_fujian.py`（EB 大端路径不得回退）＋至少一个非 698 测试
   （如 `test_gdw_fujian.py`）确认未被误伤。
4. **自洽检查**：脚本级「构造 A-XDR 值 → encode → decode → 相等」往返断言（覆盖 8 个整型 + 2 个浮点）。

## 6. 回滚

改动集中在 3 个文件 + 测试/文档；`git revert <commit>` 即可整体回退，无数据迁移、无外部依赖。
