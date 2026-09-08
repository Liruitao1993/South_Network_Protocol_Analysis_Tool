# Research: 解析侧现状与「反向 encode」能力缺口

- **Query**: `dlt645_parser.py` 控制码/功能码分支与数据域入口；`dlt645_data_codec.py` 各函数处理的数据类型；据此列出组帧需要的反向 encode 清单，标注可复用/需新写
- **Scope**: internal
- **Date**: 2026-09-07
- **来源**: `dlt645_parser.py`（263 行，全文）、`dlt645_data_codec.py`（286 行，全文）

> **总结论**：现有 dlt645 代码 **100% 是 decode（解析）方向，没有任何 encode（组帧）函数**。组帧功能需新写全部反向能力，但 decode 逻辑提供了精确的「逆运算参照」（线序、BCD、小数点、+0x33、CS），可据此反推 encode。

---

## 1. `dlt645_parser.py` 解析流程与分支

### 入口与帧校验
- `DLT645Parser.parse(data)`（`:42`）：主入口，返回 dict（含 valid/address/control/data/di_code/di_desc/fields 等）。
- `check_frame(data)`（`:33-40`）：`len>=12` + `data[0]==0x68` + `data[7]==0x68` + `data[-1]==0x16` + `sum(data[0:-2])&0xFF == data[-2]`。

### 地址 / 控制码 / 长度提取
- `:68` `address = data[1:7][::-1].hex().upper()`（**地址逆序还原**）。
- `:69` `control = data[8]`；`:70` `data_length = data[9]`。
- `:71-78` 长度一致性校验（声明 L vs 实际 len-12）。

### 数据域入口（减 0x33）
- `:81-87` `result['data'] = bytes([(b - 0x33) & 0xFF for b in ...])`——**数据域减 0x33 入口**。

### 功能码 / 控制码分支
- `:93` `func_code = control & 0x1F`。
- `:94` `addr_in_data`：func ∈ {0x13,0x15} 且 len(data)==6 → 数据域即 6B 地址（无 DI），`:96` `data[0:6][::-1]` 逆序。
- `:98` `timing_in_data`：func==0x08 且 len==6 → 广播校时数据（无 DI）。
- `:100` `err_in_data`：`control & 0x40`（D6 异常）且 len==1 → 错误信息字 ERR。
- `:101` `no_di = addr_in_data or timing_in_data or err_in_data`。
- `:104-107` DI 解析：`int.from_bytes(data[0:4],'little')` → `%08X`。
- `:119-150` 控制码文本解析：
  - `:127` `ctrl & 0x80` → DIR=1 从站应答；`:138` else → DIR=0 主站请求。
  - `:124` `is_exception = ctrl & 0x40`（D6）。
  - `:133` `ctrl & 0x20`（D5 后续帧标志）。
  - `:122` `func = ctrl & 0x1F`。
- `:152-160` LME 自定义 DI 分派：`di_code ∈ {04FFAAF9, FF00DD01}` → `parse_lme_dlt645`。

### 数据域字段展开分支（`:178-249`）
| 条件 | 处理 | 调用 |
|---|---|---|
| `err_in_data`（`:178`） | 异常应答 ERR 1B | `decode_err` |
| `addr_in_data`（`:184`） | 读/写通信地址 6B | 直接逆序 hex |
| `timing_in_data`（`:192`） | 广播校时 ss mm hh DD MM 星期 | 内联 `_bcd`（`:194`） |
| func∈{0x1A,0x1B} 且主站（`:204`） | 电表/事件清零请求 | `split_clear_command` |
| len(data)>=4 通用（`:211`） | 展开 DI + body | 下列子分支 |
| ↳ DIR=1 且 func∈{0x11,0x12}（`:220`） | 读数据应答，按 data_type 解码 | `decode_value` |
| ↳ DIR=0 且 func==0x14（`:232`） | 写数据请求 | `split_write_request` |
| ↳ DIR=0 且 func==0x18（`:243`） | 修改密码请求 | `split_change_password` |

---

## 2. `dlt645_data_codec.py` 现有能力（全 decode）

| 函数/常量 | 行号 | 处理内容 | 数据类型/单位 |
|---|---|---|---|
| `ERR_BITS` | `:16-25` | 附录 C 错误码位表（bit0~6） | 位域 |
| `STATUS_WORD_BITS` | `:29-59` | 状态字 1~7 位定义（附录 C） | 位域 BS32 |
| `decode_status_word(name,data)` | `:70-93` | 按 DI 名「状态字 N」展开位；`int.from_bytes(data[:2],'little')` | 位串（前 2 字节） |
| `FUNC_NAMES` | `:97-110` | 12 个功能码 → 中文名 | — |
| `_bcd_digits(b)` | `:113-125` | **反转字节序**拼 BCD 数字串；含非 BCD nibble 返回 None | BCD（低字节在前） |
| `decode_value(data,data_type,unit,di_name)` | `:128-195` | 按 data_type 解码：BS 状态字 / YYYYMMDD 日期（线序 DD MM YY，`:157`）/ hhmmss 时间（线序 ss mm hh，`:165`）/ BCD 数值（含小数点 `:172-183`、单位、`,MDHM` 后缀） | BCD/日期/时间/位串 |
| `decode_err(b)` | `:198-208` | ERR 1B 位域 → 中文错误 | 位域 |
| `split_write_request(data)` | `:211-237` | 写数据 14H 拆分：DI(4)+PA P0P1P2(4)+C0~C3(4)+payload(m) | BCD 密码/操作者 |
| `split_change_password(data)` | `:240-258` | 改密码 18H：DI(4)+原密码组(4)+新密码组(4) | BCD |
| `split_clear_command(data)` | `:261-285` | 清零 1A/1B：PA P0P1P2(4)+C0~C3(4)+对象标识(4，FFFFFFFF=全部) | BCD/hex |

**处理的数据类型全集**：BCD（低字节在前 + 小数点）、ASCII（无，645 主体不含 ASCII，仅 LME 接口有）、日期 YYYYMMDD（线序 DD MM YY）、时间 hhmmss（线序 ss mm hh）、位域（状态字 BS/ERR）、hex 裸值。

---

## 3. 组帧需要的「反向 encode 能力清单」

| # | encode 能力 | 反向参照（现有 decode） | 状态 |
|---|---|---|---|
| E1 | **BCD 编码**：数字串 → BCD 字节（**低字节在前**），含小数点定位 | `_bcd_digits`(`:113`) 反转逻辑 + `decode_value`(`:172-183`) 小数点 | ❌ **需新写**（`gdw_send_frame_lib.py:151` `_bcd_encode` 可参考） |
| E2 | **日期编码**：YYYYMMDD → 线序 DD MM YY（3B BCD） | `decode_value`(`:153-160`) | ❌ **需新写** |
| E3 | **时间编码**：hhmmss → 线序 ss mm hh（3B BCD） | `decode_value`(`:163-167`) | ❌ **需新写** |
| E4 | **状态字/位域编码**：勾选位 → 位串字节 | `decode_status_word`(`:70`) / `STATUS_WORD_BITS` | ❌ **需新写**（写场景较少，可选） |
| E5 | **+0x33 加扰** | `parse`(`:84/87`) 减 0x33；`test_dlt645_lme.py:33` 加 0x33 | ❌ **需新写**（一行 `(b+0x33)&0xFF`） |
| E6 | **CS 计算**：`sum(帧起始..数据域末)&0xFF` | `check_frame`(`:39`)；`test_dlt645_lme.py:35` | ❌ **需新写**（一行） |
| E7 | **地址域编码**：12 位 hex → 6B BCD **逆序** | `parse`(`:68`) 逆序还原 | ❌ **需新写**（`bytes.fromhex(addr)[::-1]`） |
| E8 | **DI 编码**：8 位 hex DI → 4B **低字节在前** | `parse`(`:105`) little-endian | ❌ **需新写**（`bytes.fromhex(di)[::-1]`） |
| E9 | **控制码组装**：`(dir<<7)\|(err<<6)\|(more<<5)\|(func&0x1F)` | `parse`(`:119-150`) | ❌ **需新写** |
| E10 | **写数据 14H 数据域组装**：DI+PA P0P1P2+C0~C3+DATA | `split_write_request`(`:211`) | ❌ **需新写**（逆拆分） |
| E11 | **改密码 18H 数据域组装**：DI+原密码组+新密码组 | `split_change_password`(`:240`) | ❌ **需新写** |
| E12 | **清零 1A/1B 数据域组装**：PA P0P1P2+C0~C3+对象标识(FFFFFFFF) | `split_clear_command`(`:261`) | ❌ **需新写** |
| E13 | **广播校时 08H 数据域**：ss mm hh DD MM 星期/YY（6B BCD） | `parse`(`:192-203`) | ❌ **需新写**（第 6 字节语义待确认，见 protocol-rules.md Caveat 2） |
| E14 | **冻结 16H 数据域**：mm hh DD MM（4B BCD，含 99 通配） | 无 decode 分支（parser 未特化 16H） | ❌ **需新写**（文档 `DLT645-2007.md:820`） |
| E15 | **改速率 17H 数据域**：Z 特征字 1B | 无 decode 分支 | ❌ **需新写**（文档 `:872`） |
| E16 | **读/写通信地址 13H/15H 数据域**：6B 地址（或空） | `parse`(`:94-96`) | ❌ **需新写** |
| E17 | **读数据 11H / 读后续 12H**：DI(4) [+ SEQ(1)] | `parse`(`:211`) | ❌ **需新写**（最简单，仅 DI） |
| E18 | **密码/操作者 BCD 编码**：3B 密码 + 4B 操作者 | `split_*` 显示逻辑 | ❌ **需新写** |

**可复用（无需重写，直接调用或参照）**：
- `FUNC_NAMES`（`:97`）：组帧命令下拉的功能码中文名可直接复用。
- `ERR_BITS` / `STATUS_WORD_BITS`：若组「异常应答/状态字」写场景可参照，但请求帧组帧一般不需要。
- `_bcd_digits` 的反转逻辑：encode 时按同样字节序反向操作。

**结论**：现有 codec **无一函数可直接用于组帧**（方向相反），但 decode 实现是 encode 的精确逆向规格说明书。建议新建独立模块（如 `dlt645_send_frame_lib.py` + `dlt645_frame_schema.py`），仿南网/国网通用 `_pack_field` 引擎（见 `existing-generator-patterns.md`），而非改动 `dlt645_data_codec.py`。

---

## Caveats

- 广播校时（E13）第 6 字节语义（星期 vs 年）文档与实现有差异，组帧前需用户确认。
- 冻结（E14）、改速率（E15）在 parser 中无专用 decode 分支，encode 规格只能来自 `DLT645-2007.md`（行号见 protocol-rules.md 第 4 节）。
- 写数据（E10）需要「哪些 DI 可写」的判断，依赖 DI 读写属性（`dlt645_di.json` 缺，见 di-schema-source.md）。
