# 设计：645虚拟表 LME 模块版本查询下发

## 架构与边界

```
┌── dlt645_sim/lme_query.py（新增，纯逻辑无 Qt，可单测）─────────────────┐
│ build_single_sta_query(addr)   → 4.2  C=11H  data=DI(04FFAAF9)         │
│ build_dual_query(addr, entries)→ 4.6  C=11H  data=DI+00+M+M×2B头        │
│ build_dual_set(addr, items)    → 4.7  C=14H  data=DI+00+M+M×(2B头+L)   │
│ parse_entry_items(text) / parse_set_items(text) / 中文 ValueError 校验  │
│ 依赖：DLT645FrameGenerator（唯一 645 封装）+ lme_info_entry_parser      │
│      （pack_lme_query_header / pack_lme_query_request / LME_INFO_ENTRIES）│
└────────────────────────────────────────────────────────────────────────┘
                    │ bytes（未下发、未加扰口径→由 generator 统一封装）
                    ▼
┌── dlt645_meter_sim_widget.py（改）─────────────────────────────────────┐
│ Dlt645SerialSlaveThread                                                 │
│   新增 slave_frame = Signal(str)                                        │
│   run(): ctrl & 0x80 → 不当请求，emit slave_frame(hex)、日志「◀ 模块回包」│
│          ctrl & 0x80 == 0 → 原路径（engine.handle_frame → 回写）         │
│   write_frame(bytes) 复用（下发）                                        │
│                                                                          │
│ Dlt645VirtualMeterWidget                                                │
│   新增分组「模块版本查询（LME 自定义下发）」                              │
│   生成帧 → lme_query.build_* → 只读框 + 日志（控制码/L 说明）             │
│   下发到串口 → 4.7 先确认框 → write_frame                                 │
│   slave_frame → DLT645Parser.parse → _fill_resp_table + 日志            │
│   离线区 DIR=1 输入 → 直接 parse → _fill_resp_table（不再"忽略"）         │
│   _resp_rows(parsed) 提取 3/4 元组行（LME 4 元组兼容，同 main_gui L10114）│
└────────────────────────────────────────────────────────────────────────┘
                    │ 解析链路零改动
                    ▼
     dlt645_parser.py → lme_info_entry_parser.parse_lme_dlt645（已就绪）
```

**不碰**：`dlt645_parser.py`、`lme_info_entry_parser.py`（解析/条目字典/请求头打包均为复用；仅若需 `pack_lme_set_request` 则新增函数而不改既有签名）、`dlt645_frame_schema.py`、`dlt645_frame_gen.py`、`dlt645_sim/engine.py`（从站应答行为不变）、Reflex Web。

## 契约

### 帧数据域（未加扰，交给 `build_frame`）

| 接口 | C | 数据域（逻辑字节，+0x33 由 build_frame 负责） |
|---|---|---|
| 4.2 单模 STA 详细版本 | `11H` | `2C DD 32 37`（= DI `04FFAAF9` 线上序） |
| 4.6 双模 STA 内部详细信息 | `11H` | `01 DD 00 FF` + `00` + `M` + `M×2B 请求头`（数据ID 6bit \| 分类ID 3bit \| 保留 7bit） |
| 4.7 设置双模 STA 详细信息 | `14H` | `01 DD 00 FF` + `00` + `M` + `M×(2B TLV 头 + L 字节数据)`（数据ID 6bit \| 分类ID 3bit \| 编码 2bit \| 长度 5bit） |

- `M=0`（条目留空）仅 4.6 合法（读模块全部支持条目）；4.7 要求至少 1 条。
- 4.7 TLV 的编码格式取 `LME_INFO_ENTRIES[cat][data_id][1]`（1 ASCII / 2 BIN / 3 BCD）；条目不在字典 → 编码 BIN(2)、长度取输入字节数；长度上限 31（5bit），超限抛错。
- 地址：`encode_addr` 统一低字节在前；默认 `AAAAAAAAAAAA`（手册 §5.1.1 示例口径，点对点测试底板）。

### 纯逻辑 API（`dlt645_sim/lme_query.py`）

```python
QUERY_SINGLE_STA = "4.2"     # 单模STA详细版本
QUERY_DUAL_STA   = "4.6"     # 双模STA内部详细信息（读）
SET_DUAL_STA     = "4.7"     # 双模STA详细信息（写）

def build_single_sta_query(addr: str = "AAAAAAAAAAAA") -> bytes
def build_dual_query(addr: str, entries) -> bytes       # entries: "0/15,1/3" | [(0,15),(1,3)] | ""（M=0）
def build_dual_set(addr: str, items) -> bytes           # items: "0/15:0500,0/12:260911120000" | [(cat,id,"0500")]
def build_query(kind: str, addr: str, text: str) -> bytes   # UI 分派入口，text 语义随 kind
def decode_reply(frame: bytes) -> dict                  # DLT645Parser.parse 薄封装（供 UI/测试共用）
def reply_rows(parsed: dict) -> list[tuple]             # fields → (字段,原始值,解析值,说明)，兼容 3/4 元组
```

### 错误信息（中文，UI 直接弹）

- `"目标地址必须是 12 位十六进制（当前 …）"`
- `"4.6 条目格式应为 分类/数据ID（当前 …），如 0/15"`
- `"4.7 条目格式应为 分类/数据ID:数据hex（当前 …），如 0/15:0500"`
- `"条目数据长度 N 超出 5bit 上限 31 字节（分类c/数据d）"`
- `"LME 分类ID 应为 0~7（当前 …）"` / `"LME 数据ID 应为 0~63（当前 …）"`（复用 `pack_lme_query_header`）

## UI（运行页，顺序：串口从站 → **模块版本查询** → 离线模拟 → 日志 → 结果表）

形态（已确认）：**三个常驻一键按钮 + 可审帧框**，不做"查询类型下拉 + 两步生成"。

```
┌ 模块版本查询（LME 自定义下发） ─────────────────────────────────────────┐
│ 目标地址 [AAAAAAAAAAAA]                                                  │
│ [读模块版本(4.2)] [读内部详细信息(4.6)] [设置(4.7)]                        │
│ 条目 [0/15,1/3                        ]  ← 4.2 时隐藏并清空               │
│ 帧   [68 AA AA AA AA AA AA 68 11 04 …]  [下发到串口] [复制hex]（只读等宽） │
└──────────────────────────────────────────────────────────────────────────┘
```

| 按钮 | kind | 请求 | 参数 | 点后行为 |
|---|---|---|---|---|
| 读模块版本(4.2) | primary | 4.2 | 无（条目框隐藏清空） | 组帧→帧框→日志→已监听则下发 |
| 读内部详细信息(4.6) | primary | 4.6 | 条目（可空=读全量） | 同上 |
| 设置(4.7) | warning/danger | 4.7 | 条目:hex（必填） | 组帧→帧框→**确认框列条目**→确认才下发 |
| 下发到串口 | success | 帧框内容 | — | 重发（4.7 先确认）；未监听→既有提示 |
| 复制hex | ghost | 帧框内容 | — | 剪贴板 |

- 条目框 hint/tooltip 随当前按钮更新（`分类/数据ID` ↔ `分类/数据ID:hex数据`）；按钮不改变已填文本，仅切换语义与显隐。
- 组帧失败 → `warning` 中文提示，**不覆盖帧框**、不下发。
- 回包：`slave_frame` → parse → `_fill_resp_table` + 日志 `◀ 模块回包解析: 接口名`。
- 结果表复用 `_fill_resp_table`（既有 4 元组兼容写法），不新建表控件。

## 关键取舍

1. **不改 `dlt645_frame_schema.py`**（4.7 LME 走 sim 层构造）：该 schema 服务于 GUI/Web「协议组帧」页，改写 (REQ,0x14)+FF00DD01 的数据域布局会改变既有组帧输出口径并牵动两个前端；虚拟表这条链只需自己构造，且 `lme_query` 直接复用同一 `DLT645FrameGenerator` 封装，口径仍单一。
2. **条目用文本输入而非下拉**：`LME_INFO_ENTRIES` 有 ~120 条，本次只做"下发查询"，文本 `分类/数据ID` 输入最小可用；tooltip/提示行给出格式与"留空=读全量"。若后续要做选择器，`lme_entry_options()` 已提供数据源。
3. **4.7 下发加确认框**：写类条目可能改模块参数（分类0/数据15 本地接口默认信息 = 波特率/校验位，分类0/数据30 继电器控制），误发有实机代价；只对 4.7 加确认，查询类不加。
4. **离线 DIR=1 直解**：让新功能在无硬件时也能验证，同时纠正现状里"模块回包仅打一行忽略日志"的体验；DIR=0 行为不变，因此对既有离线模拟零回归。
5. **回包解析复用 `DLT645Parser`**：LME 深度解析已在解析器内分派，虚拟表不复制二进制解析逻辑（避免第二套口径）。

## 兼容 / 回退

- 新增文件 + 新增控件 + 新增信号：删除 `dlt645_sim/lme_query.py`、移除分组与 `slave_frame` 连接即完全恢复旧行为；引擎与解析链路未被修改。
- 4.7 帧布局若与实机不符（见 prd 风险项），回退点是 `build_dual_set` 一处数据域前缀；解析侧不受影响（本次未改解析）。
- 测试文件独立，不影响既有 4 个 645 测试脚本。
