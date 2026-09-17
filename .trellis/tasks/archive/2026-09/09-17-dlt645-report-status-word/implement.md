# 实施计划：协议6 位表入库与位号纠错

> 每步都可独立验证；步骤 0 是**强制前置**（不通过则不得进入步骤 2）。

## 步骤 0（前置探针，强制）

在写任何分派逻辑前，先实测两个假设，结果粘进本文件末尾的「探针实测」段：

```bash
cd "/mnt/e/python/南网解析工具" && pwshu 'python -c "
import json, dlt645_parser as dp
m = json.load(open(\"dlt645_di.json\", encoding=\"utf-8\"))[\"di_map\"]
from collections import Counter
print(\"BS96:\", [ (k,v[\"name\"]) for k,v in m.items() if v[\"data_type\"]==\"BS96\" ])
print(\"BS64:\", [ (k,v[\"name\"]) for k,v in m.items() if v[\"data_type\"]==\"BS64\" ])
print(\"BS32:\", [ (k,v[\"name\"]) for k,v in m.items() if v[\"data_type\"]==\"BS32\" ][:8])
"'
```

- **前提 P1**：`BS96` 只被 `04001501`/`04001503` 使用、`BS64` 只被 `04001104` 使用 → 满足则 D3 第 3 步兜底安全。
- **前提 P2**：`decode_value` 的 `di_name` 实参等于 DI 全名。验证：
  ```bash
  pwshu 'python -c "
  import dlt645_data_codec as c
  real = c.decode_value
  c.decode_value = lambda d, dt, u=\"\", n=\"\": print(\"di_name=\", repr(n), \"dt=\", dt) or real(d, dt, u, n)
  import dlt645_parser as dp
  dp.decode_value = c.decode_value
  dp.DLT645Parser().parse(bytes.fromhex(\"6891 1010 34 48 33 37 33 33 33 33 33 33 33 33 33 43 33 33 DF 16\".replace(\" \",\"\")))
  "'
  ```
  （DI `04001501` 的读应答帧：从用户现场帧改造，或直接用测试帧 `68 <addr6> 68 91 10 <DI4> <12B> CS 16`。）
- P1/P2 任一不成立 → 改用「按 DI 号分派」（`dlt645_parser` 已有 `result['di_code']`），并在本文件记录决策。

## 步骤 1：提取补遗两份位表（pdfplumber 按单元格，**不用 markitdown 结果**）

补遗 MD 的位表有转换瑕疵（拆行/丢格/页码混入），必须以 PDF 单元格重取。

- 临时脚本用 **bash heredoc 落盘**（不要用 `write` 工具，2026-09-17 实测其落盘未生效）。
- 通过 `glob.glob` 在 **Python 内**取文件路径，**不要把中文路径写进 shell 参数**再传给 Windows python（实测会被编码成 `E:\python\������������\…` 而失败）。

产出：`REPORT_STATUS_BITS`（96 条，含保留位）、`REPORT_MODE_BITS`（64 条，含保留位），每条注释标注出处（文档名 + 表名）。

**验证**：位表条目数 = 96 / 64；保留位的键集合与文档逐条一致（打印出来人工核对一次）。

## 步骤 2：新增解析函数（`dlt645_data_codec.py`）

1. 新增 `_REPORT_BITS` 两份常量（步骤 1 产出）。
2. 抽 `_format_bits(table, bits_value, *, word_no=None, total_bits=96)` 共用格式化器；把 `decode_status_word`（`:70`）改为调它（**保持既有观感**：故障类只列置位、无置位写 `无故障`；非故障类列「未置位」）。
3. 新增 `decode_report_status_word(name, data)` / `decode_report_mode_word(name, data)`，字节序 `int.from_bytes(data, "little")`。
4. `REPORT_STATUS_NAME_RE` 名称映射。

**验证**：补遗三示例 golden
```bash
pwshu 'python -c "
import dlt645_data_codec as c
print(c.decode_report_status_word(\"主动上报状态字\", bytes.fromhex(\"010000000000000000000000\")))
print(c.decode_report_status_word(\"主动上报状态字\", bytes.fromhex(\"020000000000000000000000\")))
print(c.decode_report_status_word(\"主动上报状态字\", bytes.fromhex(\"000000000000000000000100\")))
"'
```
必须分别含 `负荷开关误动或拒动` / `ESAM错误` / `编程`。

## 步骤 3：`decode_value` 分派（`:145-152`）

按 design.md D3 顺序接入；未命中新表时**保持**原 `decode_status_word` 路径。

**验证**：用户现场帧（prd A2）→ 含 `Bit76` 且标注保留位、**不含**「见附录C」。
```bash
pwshu 'python main_gui.py --parse "68 66 51 11 07 25 20 68 91 10 34 48 33 37 33 33 33 33 33 33 33 33 33 43 33 33 DF 16" --protocol 6'
```

## 步骤 4：修正 `STATUS_WORD_BITS`（R3）

- 按 prd R3 表逐字重写 8 个字号（1~7）。
- 补保留位占位（1/2 的 Bit8–15、3 的 Bit15–9、7 的 Bit8–15）。
- 状态字 3 的 `供电方式` 改 **2 位域（bit2-1）**：`0b00 主电源 / 0b01 辅助电源 / 0b10 电池供电`，并把它从「逐位」列表移出（位域与位不混列）。
- 状态字 4/5/6 的 `Bit1` 由 `潮流方向异常` 改为 `潮流方向`（附录C 用词），`Bit8` 保持 `断流`。

**验证**：
```bash
pwshu 'python -c "
import dlt645_data_codec as c
print(c.decode_value(bytes.fromhex(\"0200\"), \"XXXX\", \"\", \"电表运行状态字4\"))      # 期望含 A相欠压
print(c.decode_value(bytes.fromhex(\"0200\"), \"XXXX\", \"\", \"电表运行状态字7\"))      # 期望含 电流逆相序
print(c.decode_value(bytes.fromhex(\"0200\"), \"XXXX\", \"\", \"电表运行状态字1\"))      # 期望含 需量积算方式
"'
```

## 步骤 5：文案纠错（R4）

改 `:152` 附近的兜底文案为 design.md D5 表；确保有表时不再出现「见附录C」。

## 步骤 6：新增测试 `test/test_dlt645_status_word_bits.py`

- 文件头 `import _path_setup  # noqa: E402,F401`（**必须同时压 F401**，否则被 ruff 自动修复删行）。
- 用例清单（每条一个断言块）：
  1. 补遗三示例 golden（96 位）；
  2. 用户现场帧（DI `04001501`）→ Bit76 保留位文案；
  3. 64 位模式字（含一个真实置位）；
  4. R2 不变量：`状态字 Bit(32+n) ≡ 模式字 Bit(n)`（n=32..63）断言；
  5. 状态字 1~7 逐位对拍：把 prd R3 表写成字面量双清单对拍（**不得从被测常量派生期望值**，否则恒真）；
  6. 状态字 4 = `0x0002` → `A相欠压`、不含 `潮流方向异常`；
  7. 状态字 3 供电方式 3 种取值；
  8. 短数据 / 空数据 / 未知位域 → 不抛异常且给兜底文案；
  9. 桌面与 Web 输出一致：断言 `protocol_registry.DLT645GuiParser` 转表与 Web `_safe_parse_to_table` 的「数据值」列逐字符相同。
- 登记 `release_check.py:CORE_TESTS`。

**验证**：`pwshu 'python test/test_dlt645_status_word_bits.py'` 全过。

## 步骤 7：变异反证（≥3 条，逐条实测变红后还原）

| # | 变异 | 期望 |
| --- | --- | --- |
| M1 | 把 `STATUS_WORD_BITS[4]` 的 Bit1/Bit3 换回旧位号 | 用例 5/6 变红 |
| M2 | 删掉保留位标注（置位时当已定义事件输出） | 用例 2 变红 |
| M3 | 96 位表按 `int.from_bytes(data[:8])`（当 64 位）解 | 用例 1/2 变红 |
| M4（可选） | 兜底文案改回单一「见附录C」 | 用例 2 变红 |

变异用**备份+还原**方式（`cp` 到 `/tmp`，改完跑、再还原），不得留下未还原的改动。

## 步骤 8：全量回归

```bash
pwshu 'python release_check.py'
```
要求 PASS 全绿、FAIL=0、WARN=0。同时确认 645 相关既有测试不退化：
`test_dlt645_lme.py` / `test_dlt645_pv_ext.py` / `test_dlt645_tolerant_parse.py` / `test_dlt645_sim*.py`。

## 步骤 9：文档同步

- `main_gui.py:CHANGELOG` 新增条目（版本/日期/要点），**必须逐条列出状态字 1~3/7 的输出变化**（A7）。
- `README.md` 更新记录追加。
- `AGENTS.md`：§5.4 加「主动上报状态字/模式字位表」说明与文档依据；§8 增陷阱条目（位表瑕疵 + 96/64 位字节序 + 保留位处置 + di.json 不得手改）；§10 摘要。
- 本任务 `prd.md`「探针实测」段回填步骤 0 结果。

## 回退点

- 步骤 2（新增位表）与步骤 4（位号修正）相互独立，可分别 `git checkout -- <file>` 回退。
- 步骤 5（文案）独立。
- 任一步骤验证失败 → 停在该步骤，不得继续后续步骤。

## 探针实测

（步骤 0 执行后回填 P1/P2 结果）

## 探针实测（2026-09-17 执行）

**P1 成立** — `dlt645_di.json` 的 `di_map`（1099 条）中：
- `BS96` → 仅 `04001501`（主动上报状态字，`length=12`）与 `04001503`（复位主动上报状态字，`length=12`）
- `BS64` → 仅 `04001104`（主动上报模式字，`length=8`）

⇒ D3 第 3 步「按 data_type 兜底」安全（实现仍保留「第 1 步按 DI 名优先」，无名时才按位宽推断）。

**P2 成立** — `decode_value` 收到的 `di_name` 是 DI 全名（实测 `04000501` → `di_desc='电表运行状态字1'`；`04001501` 完整链输出主动上报状态字展开）⇒ 按名匹配可行。

## 实施记录（与计划的差异，均已实测）

1. **两位域项的 key 必须是 LSB 位号**：计划写 `2: ("供电方式", 2, ...)`，实测取值左移一位（`0x02` 得「主电源」而应为「辅助电源」）→ 改为 `1: ("供电方式", 2, SUPPLY_MODE_NAMES)`。
2. **保留位不进「未置位」列表**：计划只写「补保留占位」。实现为「表内显式 `None` 占位（位表完整性）+ 置位时点名 + 未置位不进列表」（96 位表若列未置位会输出近百项噪声）；U9 改用「覆盖位集合」而非 `table.keys()` 校验（位域展开）。
3. **状态字3 的 Bit8**：附录C 只写「Bit15..Bit9 保留」未提 Bit8 → 按保留占位，不臆造事件。
4. **`test/test_dlt645_lme.py` 12b/12c 计划外修正**：原用例固化了错误位号（12b 注释「bit3 过压」实为**失流**；12c 用 `0x40`=Bit6 属保留位，且子串断言 `"有功功率方向" in svc` 会命中**未置位列表**而假绿）→ 改为附录C 口径（12b `0x88`=断相+失流；12c `0x10`=Bit4 有功方向，断言切分 `split("未置位")[0]` 段）。
5. **U11 的环境分支**：WSL 解释器无 reflex → 退化为源码守卫（断言 Web 侧无第二份位表、消费同一 `parse()["fields"]`）；Windows python（release_check 口径）执行真实 `State` 对拍。两端均 130 项全绿。
6. **变异反证实测**：M1（状态字4 换回旧错位）9 红 / M2（去掉保留位标注）2 红 / M3（96 位当 64 位解）3 红；还原后 md5 一致、130 全绿。
7. **版本**：`APP_VERSION` 1.23.22 → **1.23.23**（新增功能 + 行为变更），同步 `README.md`（badge/版本句/更新记录）、`南网解析工具.iss`（`--sync-iss`）、`main_gui.py:CHANGELOG`（逐条列出状态字 1~3/7 的输出变化，满足 A7）、`AGENTS.md`（§5.4 位域依据 / §8 陷阱 50 / §10 摘要）。
