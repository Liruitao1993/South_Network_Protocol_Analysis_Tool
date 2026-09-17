# 技术设计：协议6 位表入库与位号纠错

> 下文事实均在 2026-09-17 实测确认（命令与输出见 `implement.md` 的验证步骤）。

## D1 落点：`dlt645_data_codec.py`（唯一来源）

该文件（500 行，纯 stdlib 无 Qt）已有同族常量与函数：

| 位置 | 内容 |
| --- | --- |
| `dlt645_data_codec.py:15` | `ERR_BITS` 错误信息字（附录C） |
| `dlt645_data_codec.py:29` | `STATUS_WORD_BITS` 电表运行状态字 1~7（**现状位号错**） |
| `dlt645_data_codec.py:62` | `STATUS_WORD_PHASE = {4:"A相",5:"B相",6:"C相"}` |
| `dlt645_data_codec.py:64` | `STATUS_WORD_NAME_RE` 名称→字号 |
| `dlt645_data_codec.py:70` | `decode_status_word(name, data) -> Optional[str]` |
| `dlt645_data_codec.py:131` | `decode_value(data, data_type, unit="", di_name=...)`，BS 位域分支在 `:145-152` |

**决策**：新增常量与函数放同一文件，**不新建模块**。理由：① 桌面 `dlt645_parser.py:7` 与 Web 走同一 import，645 虚拟表也从这里取值，一处改两端生效；② 建新模块会形成「第四份位表清单」，正是 `.trellis/spec/guides/code-reuse-thinking-guide.md` 要避免的。

## D2 新增常量与函数接口

```python
# 主动上报状态字（国网第4号补遗，DI 04001501 / 04001503，BS96，12 字节）
# {bit: 事件名}；预留位显式写 "保留"，便于置位时给出「未定义」文案
REPORT_STATUS_BITS = {0: "负荷开关误动或拒动", 1: "ESAM错误", ..., 95: "节假日编程"}

# 主动上报模式字（国网第4号补遗，DI 04001104，BS64，8 字节）
REPORT_MODE_BITS = {...}                      # {bit: 名称}

REPORT_STATUS_NAME_RE = {"主动上报状态字": "status", "复位主动上报状态字": "status",
                         "主动上报模式字": "mode"}

def decode_report_status_word(name: str, data: bytes) -> Optional[str]: ...
def decode_report_mode_word(name: str, data: bytes) -> Optional[str]: ...
def _format_bits(table, bits_value, *, word_no=None, total_bits=96) -> str: ...
```

- `_format_bits` 是新增的**共用格式化器**：`decode_status_word` 与新函数都调它，避免出现两份「置位/未置位」文案拼装。它负责：
  - 位宽按声明（96/64/16 位）输出 `bit位值=<二进制>`；
  - 保留位置位 → 打 `BitN 保留位（补遗未定义事件）` 标记（不进「已定义事件」列表）；
  - 故障类状态字（4/5/6）沿用「只列置位、无置位则写 `无故障`」的既有约定（**不改既有观感**）。
- 返回 `None` 的语义：位表未命中 → 由 `decode_value` 走 R4 的兜底文案（保持既有 `Optional[str]` 契约）。

## D3 分派：`decode_value` 如何选中合适的表

现状（`:145-152`）只有一条 BS 分支：按 `di_name` 命中 `STATUS_WORD_NAME_RE` → `decode_status_word`，否则回落 `二进制(N位)：…；状态字位定义见DL/T645-2007附录C`。

新分派顺序（**先按 DI 名，再按 data_type 兜底**）：

1. `di_name` 命中 `REPORT_STATUS_NAME_RE` → 96 位（`status`）或 64 位（`mode`）表；
2. `di_name` 命中 `STATUS_WORD_NAME_RE` → 修正后的 `STATUS_WORD_BITS`；
3. 兜底：`data_type` 为 `BS96` → 状态字表（96）；`BS64` → 模式字表（64）；其余 → R4 文案。

**必须先用探针确认两件事**（写死假设会出错）：
- `decode_value` 收到的 `di_name` 究竟是 `di_desc` 全名还是别的。调用点 `dlt645_parser.py:324` 传 `result.get('di_desc','')`，`dlt645_parser.py:339` 传 `di_unit` —— 实测打印一次 `di_desc` 是否等于「主动上报状态字」。
- `BS96` / `BS64` 在 `dlt645_di.json`（1099 条）里**是否只被这三个 DI 使用**；若还有别的 DI 也用，则第 3 步会把无关 DI 误判 → 必须限定为「data_type 相符 **且** di_map 名为主动上报*」或干脆只用第 1 步。

## D4 位号正确性依据（双源互证 + 文档自证）

- **状态字 1~7**：`DLT645-2007.md:1658-1730`（附录C，含 Bit15–8 保留行）。
- **96 位状态字**：补遗 96 位表；其 A 相组 `Bit16–23` 与附录C 状态字4 `Bit7–0` **逐位一致**（仅是「潮流方向」↔「功率反向」用词差异）→ 两份独立文档互证。
- **64 位模式字**：补遗 64 位表；用 R2 不变量 `状态字 Bit(32+n) ≡ 模式字 Bit(n)（n=32..63）` 交叉验证。
- **字节序**：补遗三个报文示例自证（`01`→Bit0、`02`→Bit1、字节[10]`01`→Bit80），即**低字节在前**。
- 位表**逐位字面量**入库（不写生成器）：位表是规范事实，不是可推导结构；生成器会掩盖出处。

## D5 文案纠错

| 场景 | 现状 | 改为 |
| --- | --- | --- |
| 主动上报状态字/模式字 | `二进制(96位)：…；状态字位定义见DL/T645-2007附录C`（**出处错**） | 事件名 + 保留位标注；出处标注「国网第4号补遗」 |
| 状态字 1~7 | 展开（位号错） | 展开（位号正确） |
| 未知 BS 位域 | 单一出处「见附录C」 | 两个出处并列，或不提出处、只报位宽 |

## D6 兼容与不变式

- 字段元组结构保持 3/4 元组不变（`dlt645_parser` 消费方与 Web 转表都依赖元组长度）。
- `valid` 语义不变（`dlt645_sim/engine.py:114`、「645虚拟表」读 `parsed.get("valid", True)`）。
- 不新增 pip 依赖；不引入 Qt；不 import `main_gui`。
- `encode_value`（组帧侧）**本次不改** —— `STATUS_WORD_BITS` 不被组帧侧引用（实测 `grep STATUS_WORD_BITS` 仅 `dlt645_data_codec.py` 自身；新增位表同样只服务解析）。

## D7 风险与回退

| 风险 | 处置 |
| --- | --- |
| 位表逐位录入出错 | 三个文档示例 golden + 附录C 互证 + R2 不变量断言；任一失败即视为发布阻塞 |
| `di_name` 实际不是 DI 全名 | D3 探针先行；不符则改为按 DI 号分派（`dlt645_parser` 已持有 `di_code`） |
| `BS96`/`BS64` 被其他 DI 复用 | D3 探针先行；必要时把「DI 名」作为唯一判据 |
| 保留位被真实表计使用 | 输出「保留位（补遗未定义事件）」，不臆造事件名 —— 用户报障的那条帧（Bit76）即此情形 |
| 状态字 1~3/7 输出变化影响既有用户 | 变化在 CHANGELOG 逐条列出（A7），并在测试中固化新口径 |

**回退点**：位号修正（R3）与位表新增（R1/R2）是两条独立改动，可分别回退；文案（R4）独立。
