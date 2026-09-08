# Research: LME 自定义接口组帧可行性 + 测试参考模式

- **Query**: `lme_info_entry_parser.py` TLV 头编解码与 04FFAAF9 固定布局，能否反向拼装（14H/11H）；`test/` 三个测试文件的 build_frame/断言写法与项目测试约定
- **Scope**: internal
- **Date**: 2026-09-07
- **来源**: `lme_info_entry_parser.py`(954)、`test/test_dlt645_lme.py`(389)、`test/test_gdw_fujian.py`(500)、`test/test_web_frame_gen_utils.py`(499)

---

# 第一部分：LME 自定义接口组帧可行性（调研点 9）

## 1. TLV 头编码/解码实现

### 解码（现有）
`_parse_dual_tlv_rows(data, with_value, include_info_byte)`（`lme_info_entry_parser.py:543-637`）：
- 结构（`:547-548` 注释）：`[条目信息 1B(填0)] + M 1B + M×(2B头 + L字节数据)`。
- **头部 16 位（小端）位域**（`:578-583`）：
  ```python
  header = data[idx] | (data[idx+1] << 8)     # 小端 16 位
  data_id     = header & 0x3F                 # b0~5   数据ID（6bit）
  category_id = (header >> 6) & 0x07          # b6~8   分类ID（3bit）
  encoding    = (header >> 9) & 0x03          # b9~10  编码格式（2bit）1=ASCII 2=BIN 3=BCD
  length      = (header >> 11) & 0x1F         # b11~15 长度L（5bit，最大31）
  ```
- 兼容「有/无条目信息字节」两种组包（`:559` `data[4]==0 and data[5]>0`）。

### 编码（测试中已有权威实现！）
`test/test_dlt645_lme.py:60-61` **已实现 TLV 头编码**：
```python
def tlv_header(data_id, cat, enc, length):
    return (data_id | (cat << 6) | (enc << 9) | (length << 11)).to_bytes(2, "little")
```
→ **反向拼装完全可行**，编码公式是解码的精确逆运算，且已被测试验证（`:185-190` 用 `tlv_header` 构造 M=17 的真实结构帧并通过解析回读）。

### 请求头（4.6 查询，无 encoding/length）
`parse_dual_entry_query_request`（`:662-695`）：请求头 = `数据ID(6bit) | 分类ID(3bit) | 保留(7bit)`（`:686-688`），即 `header = data_id | (cat<<6)`，保留位应填 0。

## 2. 04FFAAF9 固定布局解析位置

`parse_sta_version_single(data)`（`:751-867`）：
- DI 占前 4 字节，字段从 `off=4` 开始（`:783`）。
- **固定布局**（非 TLV）：外部厂商代码(2B ASCII 逆序 `:786`)、外部芯片代码(2B `:788`)、外部版本号(2B BIN 逆序 `:790`)、外部版本日期(3B BCD 日月年 `:793`)、MCU 内部版本(2B `:797`)、APS/NWK/PHY 版本(各 1B 层级标志+2B BCD `:801-818`)、DSP(2B `:819`)、过零标志(1B `:822`)、编译时间(19B ASCII `:831`)、三相过零频率/占空比(各 2B little `:834-842`)、**硬件信息段变长**（1B 长度 + N B ASCII + 2B CRC16 + 1B Flash 容量 `:844-861`）。
- 完整 251 字节（`:4` 注释、`:865` 提示）。

## 3. 总入口分派

`parse_lme_dlt645(di_code, ctrl, data)`（`:870-908`）：
- `dir_bit=(ctrl>>7)&0x1`；`func=ctrl&0x1F`（`:883-884`）。
- DI=`04FFAAF9`（`DI_STA_VERSION_SINGLE:15`）：DIR=1&func=0x11→应答解析；DIR=0&func=0x11→查询请求（`:886-892`）。
- DI=`FF00DD01`（`DI_DUAL_ENTRY:16`）：DIR=0&0x11→查询请求；DIR=1&0x11→应答；**DIR=0&0x14→设置请求**；DIR=1&0x14→设置应答（`:894-906`）。

## 4. 结论：能否反向拼装（设置请求 14H / 查询请求 11H）

### ✅ 能（双模 TLV 接口 FF00DD01）
- **查询请求 11H**（4.6）：`[条目信息0] + M + M×(2B请求头)`，请求头 = `data_id | (cat<<6)`（保留 7bit 填 0）。测试 `:127-128` 已构造并回读通过。
- **设置请求 14H**（4.7）：`[条目信息0] + M + M×(2B头 + L字节设置数据)`，头用 `tlv_header(data_id,cat,enc,length)`。测试 `:143,150` 已构造 `d4` 并用 ctrl=0x14 回读为「4.7 设置请求」。
- **难点**：
  1. 设置数据的**编码格式**须与条目定义匹配（1=ASCII/2=BIN/3=BCD，见 `LME_INFO_ENTRIES:21` 第 2 元素），且部分值有语义映射（如波特率 `BAUD_MAP:179`、模块类型 `MODULE_TYPE_MAP:154`），组帧 UI 需把这些映射反向做成下拉。
  2. **长度 5bit 上限 31 字节**（`:583`），超长条目（如硬件信息组 31B 刚好卡上限、编译时间 20B）需注意；`LME_INFO_ENTRIES` 中最大长度条目为 32B（模块资产编码 `:80`）**超过 5bit=31 上限**——组帧时须校验/报错。
  3. 条目信息字节「有/无」两种组包并存（`:559`），组帧须固定选一种（建议带条目信息字节=0，与测试 `:128,143` 一致）。

### ⚠️ 较难（单模固定布局 04FFAAF9）
- 查询请求 11H：DIR=0&func=0x11 **无数据单元**（`:889-892`），组帧只需 DI 4 字节 → **简单可行**。
- 但 04FFAAF9 **无设置接口**（手册仅 4.2 查询），且应答是 251B 固定布局（含变长硬件段 + 未定义多项式的 CRC16 `:852-853`），**反向拼装应答帧意义不大且 CRC16 无法计算**（手册未定义多项式）。

### 建议
LME 组帧**优先支持 FF00DD01 的查询请求(11H)与设置请求(14H)**（TLV 可逆、测试已验证）；04FFAAF9 仅支持查询请求（无数据单元）；不建议组 04FFAAF9 应答帧。

---

# 第二部分：测试参考模式（调研点 10）

## 1. 项目测试约定（✅ 已核实：纯脚本 + check()/assert，不用 pytest 装饰器）

- **无 pytest 装饰器**：三个测试文件均无 `@pytest.mark`/`import pytest`；用 `if __name__=="__main__":` 直接调用测试函数。
- **两种计数风格并存**：
  - `test_dlt645_lme.py`：模块级 `FAILURES=[]`（`:21`）+ `check(name,cond,detail)`（`:24-28`，打印 `[PASS]/[FAIL]`，失败 append），末尾 `assert not FAILURES`（`:382`）。
  - `test_web_frame_gen_utils.py`：全局 `PASS=0/FAIL=0`（`:18-19`）+ `check()`（`:22-29` 计数），末尾 `print(f"结果: {PASS} 通过, {FAIL} 失败")` + `sys.exit(1 if FAIL else 0)`（`:498-499`）。
  - `test_gdw_fujian.py`：用裸 `assert` + 每函数末尾 `print("PASS test_xxx")`（`:95,115,...`）。
- **路径引导**：均 `import _path_setup`（`test_dlt645_lme.py:11`、`test_web_frame_gen_utils.py:9`、`test_gdw_fujian.py:14`）；web 测试额外 `sys.path.insert` 加 `reflex_web`（`:15-16`）。
- **UTF-8 兜底**：`test_dlt645_lme.py:65-66` 重包 `sys.stdout` 为 utf-8（Windows 控制台中文）。

## 2. `test_dlt645_lme.py` 的 build_frame/build_frame_raw/build_ctrl（组帧权威口径）

```python
# :31-36  decoded_data=减0x33后真实数据域(含DI); addr=帧内地址(低字节在前)
def build_frame(decoded_data, ctrl=0x91, addr=b"\x10\x00\x00\x25\x00\x00"):
    enc = bytes((b + 0x33) & 0xFF for b in decoded_data)          # +0x33 加扰
    body = bytes([0x68]) + addr + bytes([0x68, ctrl, len(enc)]) + enc
    cs = sum(body) & 0xFF                                          # CS 起止=body 全部
    return body + bytes([cs, 0x16])

# :39-43  raw_data=线上数据域(已加0x33)，不再加扰
def build_frame_raw(raw_data, ctrl=0x91, addr=b"\x10\x00\x00\x25\x00\x00"):
    body = bytes([0x68]) + addr + bytes([0x68, ctrl, len(raw_data)]) + raw_data
    return body + bytes([sum(body) & 0xFF, 0x16])

# :328-331  build_ctrl(dd, ctrl, addr=b"\x00"*6)：同 build_frame，地址默认全0
```
**这三个函数就是 dlt645 组帧的权威参照实现**（加扰 +0x33、CS=sum(body)&0xFF、地址低字节在前、68/68/16 包裹）。新生成器 `DLT645FrameGenerator` 的输出必须与 `build_frame` 逐字节一致。

辅助：`field_map(result)`（`:46-57`）归一化解析结果 fields 为 `{字段名:(解析值,说明,原始值)}`，兼容 3/4 元组；`tlv_header`（`:60`）见第一部分。

## 3. 「组帧 → 解析回读」断言写法

### `test_gdw_fujian.py:261-287`（组帧→回读范本）
```python
def test_fujian_frame_generation():
    gen = GDWFrameGenerator(); parser = GDW10376Parser()
    frame = gen.generate_frame(afn=0x52, fn=1, field_values={...}, info_config={...},
                               src_addr="000000000001", dst_addr="001122334455")
    assert frame[0] == 0x68                       # 帧结构断言
    assert frame[22] == 0x52                       # 关键字段位置断言
    rows = parser.parse_to_table(frame)            # 回读
    assert any("数据转发（福建增补）" in str(r[3]) for r in rows)   # 回读语义断言
    len_rows = row_values(rows, "报文长度")        # 自动计算字段回读断言
    assert len_rows and len_rows[0][2] == str(len(f645))
```
- `make_645_frame(ctrl, di_bytes, data_bytes, addr)`（`:47-51`）：内嵌 645 帧构造（供 645-over-国网 转发测试）。

### `test_web_frame_gen_utils.py:43-90`（纯函数 vs GUI 字节一致范本）
```python
def test_collect_south():
    gen = ProtocolFrameGenerator(); schema = DI_FIELD_SCHEMA[di_key]; fields = schema["fields"]
    # 位置对齐列表构造（gen_field_values/gen_sub_fields/gen_list_rows）
    field_values = collect_field_values(fields, gen_field_values, gen_list_rows, gen_sub_fields)
    frame_pure = gen.generate_frame(di_key, field_values, ...)   # 纯函数路径
    frame_gui  = gen.generate_frame(di_key, gui_values, ...)      # 手工构造路径
    check("南网字节一致", frame_pure == frame_gui, ...)           # 核心断言：两路径字节相等
```
- `:461-481` State 集成测试：`State()` → `set_protocol('7')` → `set_gen_afn_fn(...)` → 设字段 → `gen_eb_645_frame()` → `bytes.fromhex(s.gen_eb_frame)` → 断言 `b2[0]==0x68 and b2[-1]==0x16`（**Web 状态机组帧→回读字节断言范本**）。

## 4. 新测试文件应遵循的结构与命名（结论）

**建议文件名**：`test/test_dlt645_frame_gen.py`（对齐 `test_dlt645_lme.py` 命名）。

**应遵循的结构**：
1. `# -*- coding: utf-8 -*-` + 模块 docstring（覆盖范围）。
2. `import _path_setup` 引导路径；UTF-8 stdout 兜底（仿 `test_dlt645_lme.py:65-66`）。
3. `check(name, cond, detail="")` 计数函数（FAILURES 列表或 PASS/FAIL 计数，二选一，对齐现有两风格之一）。
4. **核心断言三件套**：
   - a) **字节级**：`DLT645FrameGenerator().generate_frame(...) == build_frame(decoded_data, ctrl, addr)`（复用 `test_dlt645_lme.py:31` 的 build_frame 作黄金参照）。
   - b) **组帧→解析回读**：`DLT645Parser.parse(frame)` 后断言 `di_code`/`control_desc`/字段值（仿 `test_gdw_fujian.py:280-286`）。
   - c) **逐功能码覆盖**：11H 读数据、14H 写数据、08H 广播校时、16H 冻结、18H 改密码、1A/1B 清零、13H/15H 地址、17H 速率。
5. 末尾 `if __name__=="__main__":` 调用全部测试函数 + 汇总打印 + `sys.exit(1 if FAIL else 0)`。
6. **不用 pytest 装饰器**（项目约定，已核实）。

---

## Caveats

- LME 设置数据编码格式映射（BAUD_MAP/MODULE_TYPE_MAP 等）反向做 UI 下拉的工作量较大，建议 MVP 阶段 LME 组帧只支持「查询请求 11H」（无需数据值编码），设置请求 14H 作为后续增强。
- `LME_INFO_ENTRIES` 中长度 >31 的条目（如模块资产编码 32B `:80`、模块备案信息 30B 刚好、硬件信息组 31B 刚好）与 TLV 长度 5bit 上限冲突，组帧须显式校验。
- 测试黄金参照 `build_frame` 默认 ctrl=0x91（读数据应答），组「请求帧」测试时须传对应请求控制码（如 0x11/0x14/0x08）。
- 广播校时第 6 字节语义（星期 vs 年）在 parser(`:198-200` 当星期) 与文档帧格式表间有差异，组帧测试须先与用户确认口径（见 protocol-rules.md Caveat 2）。
