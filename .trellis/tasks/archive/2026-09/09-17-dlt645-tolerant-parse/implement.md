# Implement — 协议6 校验和/长度/结构不符时仍继续解析并提示正确值

> 顺序执行；步骤 0 与步骤 5 是硬门。

## 步骤 0（硬门）：改动前基线

- [ ] 0.1 构造三条基线帧并记录**改动前**输出（仓库外脚本）：
  - 合法帧（电压块 `02E60101` 读应答）
  - CS 错误帧（同上，末前 1 字节 +1）
  - 数据长度声明不符帧（把 `data[9]` 改错）
- [ ] 0.2 记录：`valid` / `error` / `fields` 行数与首行；确认现状（合法=13 行、CS 错=0 行）。
- [ ] 0.3 检索仓库内是否已有断言「坏 CS → 空 fields / 无效的DLT645帧格式」，逐个登记（它们属**预期行为变更**，需在步骤 4 更新并记录理由）：
  ```bash
  grep -rn "无效的DLT645帧格式\|check_frame" test/ *.py | grep -v "^Binary"
  ```

## 步骤 1：拆分判据（D1）

- [ ] 1.1 新增 `check_structure(data) -> (bool, str)` 与 `calc_checksum(data) -> int`。
- [ ] 1.2 `check_frame(data)` 改为复用二者（语义不变：结构 + 校验）。
- [ ] 1.3 注释引用 AGENTS.md 陷阱 23 与 `protocol_parser.py:878` 先例。

验证：`python test/test_dlt645_lme.py`（既有行为不回归）。

## 步骤 2：`parse()` 去提前 return（D2）

- [ ] 2.1 `len(data) < 12` → 返回「帧长度不足」+ 原始 hex 两行（不抛异常、不空白）。
- [ ] 2.2 长度 ≥12 → 无论结构与校验是否通过，**一律继续**完整解析。
- [ ] 2.3 新增结果字段：`structure_valid` / `structure_error` / `checksum_expected`（`checksum`、`checksum_valid` 已存在）。
- [ ] 2.4 `valid = struct_ok and cs_ok and not data_length_mismatch`（**语义不变**，保虚拟表拒收坏帧）。
- [ ] 2.5 插入提示行：
  - `❌ 帧结构错误`（仅结构不符时；说明里写清哪个字节不符 + 「字段归属可能不准」）
  - `⚠ 校验和错误`（仅 CS 不符时；原始值列=帧内值、解析值列=`应为 XXH`、说明含**计算规则**）
  - 两者插在既有 `数据长度错误` 行之后、`数据标识 DI` 行之前
  - **行名必须含「校验和」**（GUI 偏移映射依赖）
- [ ] 2.6 长度不符行补「应声明 N 字节」；`校验和`/`帧结束符` 行在不符时显示实际值与应有值。

验证：步骤 4 的新套件。

## 步骤 3：新增 `test/test_dlt645_tolerant_parse.py`

- [ ] 3.1 文件头 `import _path_setup  # noqa: E402,F401`（F401 必须一并抑制）。
- [ ] 3.2 覆盖 A1~A9：
  - A1 CS 错帧 `fields` 非空且含业务字段（电压块应含 `数据标识 DI` 与「光伏逆变器1的电压数据块」行）
  - A2 出现「⚠ 校验和错误」行，含帧内值、`应为 XXH`、计算规则文案
  - A3 `valid is False` / `checksum_valid is False` / `checksum_expected == calc_checksum(frame)`
  - A4 合法帧与基线**逐行一致**（无新增提示行、字段数不变、`valid=True`）
  - A5 长度不符：仍完整解析 + 含「应声明」
  - A6 结构不符（改第 8 字节 / 末字节）：仍解析出字段 + 出现「❌ 帧结构错误」并指明字节
  - A7 长度 <12：不抛异常 + 返回帧长不足说明 + 原始 hex
  - A8 虚拟表不回归：`dlt645_sim` 引擎对 bad-CS 主站帧仍判无效（可直接调引擎或用 `valid` 断言）
  - A9 GUI 链路：`DLT645GuiParser().parse_to_table(cs_bad_frame)` 非空，且「⚠ 校验和错误」行字节区间 == `total_len - 2`
- [ ] 3.3 登记 `release_check.py` 的 `CORE_TESTS`。

验证：`python test/test_dlt645_tolerant_parse.py` 全绿。

## 步骤 4：全量回归

```bash
python test/test_dlt645_tolerant_parse.py    # 新增
python test/test_dlt645_lme.py
python test/test_dlt645_pv_ext.py            # 156
python test/test_dlt645_frame_gen.py         # 161
python test/test_dlt645_frame_gen_gui.py     # 73
python test/test_dlt645_sim.py
python test/test_dlt645_sim_lme_query.py
python test/test_dlt645_sim_event_word.py
python test/test_web_parse_fixes.py          # 75
python release_check.py
```

- [ ] 4.1 全绿；对步骤 0.3 登记的旧断言按新行为更新，并在本文件「验证记录」写明理由。
- [ ] 4.2 `release_check.py` FAIL=0 / WARN=0。

## 步骤 5（硬门）：变异反证

逐条改坏 → 确认测试**变红** → 还原：

- [ ] 5.1 恢复「`if not check_frame(data): return`」→ A1/A2 变红
- [ ] 5.2 去掉 `checksum_expected` → A3 变红
- [ ] 5.3 把 `valid` 恒置 True → A8 变红

**审查门**：三条都要实际观察到变红。

## 步骤 6：版本与文档（主会话执行）

- [ ] 6.1 `main_gui.py`：`APP_VERSION` → `1.23.22`、`BUILD_DATE` → 当日、`CHANGELOG` 顶部条目。
- [ ] 6.2 `AGENTS.md`：§5.4 或 §8 新增说明（协议6 容错解析：结构/校验/长度不符均继续解析 + 提示正确 CS；与协议0 先例一致）；§10 摘要。
- [ ] 6.3 `README.md` 徽章；`python release_check.py --sync-iss`。

## 验证记录

| 项目 | 结果 |
| --- | --- |
| 基线（改动前） | 合法帧 13 行/`valid=True`；CS 错帧 **0 行**/`error='无效的DLT645帧格式'`；长度不符 14 行；结构错 0 行；短帧(8B) 0 行（脚本：`C:/Users/lirt3/AppData/Local/Temp/csfix/baseline.py`） |
| 步骤 0.3 旧断言检索 | **空**——`grep -rn "无效的DLT645帧格式\|check_frame" test/ *.py` 全仓只命中 `dlt645_parser.py` 本身（定义+原调用点）；无任何既有测试依赖「坏 CS → 空 fields」。故**无需更新旧断言**，新增套件纯新增 |
| 步骤 5 变异反证 ×3 | 全部实测变红（在**最终版本** 2d01d377 上复跑）：m1 恢复提前 return → 7 条失败（A1×6 + A2×1，`字段数=0`）；m2 去掉 `checksum_expected` → 24 条（A2/A3/A4 等，`应为 00H`）；m3 `valid` 恒 True → 14 条（A3/A5/A6×3/A8×8）。每次还原后 md5 回到原值 |
| 套件通过数 | 新增 `test_dlt645_tolerant_parse.py` **135 项**；`test_dlt645_lme` 全过；`test_dlt645_pv_ext` **156**；`test_dlt645_frame_gen` **161**；`test_dlt645_frame_gen_gui` **73**；`test_dlt645_sim` OK；`test_dlt645_sim_lme_query` **95**；`test_dlt645_sim_event_word` **66**；`test_web_parse_fixes` **75** |
| release_check | **PASS=67 FAIL=0 WARN=0**（新套件已登记 CORE_TESTS 并 `[PASS]`） |
| ruff（项目 `ruff.toml`，仓库根运行） | `dlt645_parser.py` / `test/test_dlt645_tolerant_parse.py` / `release_check.py` → `All checks passed!` |

### 与 design.md 的偏差（1 处，A4 优先）

- design D2-3.4 写「`校验和` 行：**通过时**显示 `CS校验通过`」——但 A4 要求合法帧与改动前**逐行一致**。
  实测 `dlt645_parser.py` 合法帧第 12 行为 `('校验和', '54H', 'CS校验')`，改成 `CS校验通过` 即破坏 A4。
  **决定：合法时保留原文案 `CS校验`（A4 优先，PRD 高于 design）；不符时才显示 `应为 XXH（帧内值错误）`。**
  同理 `帧结束符` 行仅在结束符错误时显示实际值。二者均已在新增用例里钉住（A4 快照 + 非法场景断言）。

### 改动边界外的观察（供主会话决策，未动代码）

- **`dlt645_sim/engine.py:115` 的 `valid` 判断实际是 no-op**（`if not parsed.get("valid", True): ... pass`），
  真正决定引擎能否继续的是 `parsed.get("control")` 是否存在。实测同一条坏 CS 主站读请求：
  旧版控件码缺省为 `0` → 引擎回异常应答 `C0H / ERR=0x02`（`last_error='暂不支持功能码 0x00'`）；
  新版控件码为 `0x11` → 引擎回**正常读应答** `91H`（`last_error=None`）。
  即：**`valid` 语义未变（A8 通过），但虚拟表对坏 CS 帧的实际行为变了**（因该处判定为空操作）。
  按本任务范围（`dlt645_sim/` 属 Out of Scope）**未改引擎**；如需「虚拟表拒收坏 CS 帧」需另立任务修 `engine.py:115`。
  取证脚本：`C:/Users/lirt3/AppData/Local/Temp/csfix/engine_side_effect.py`。
