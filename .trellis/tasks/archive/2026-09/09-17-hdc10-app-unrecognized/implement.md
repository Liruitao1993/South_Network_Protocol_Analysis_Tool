# Implement — HDC 1.0 应用层未识别内容收口

> 顺序执行。每个步骤后跑对应验证；步骤 0 与步骤 7 是硬门（gate）。

## 步骤 0（硬门）：改动前基线对拍

目的：拿到「改动前」的逐帧解析快照，用于后续证明**已知业务输出未变**（R6），并定位判据变化的确切影响面。

- [ ] 0.1 写临时脚本（**放仓库外**，如 `%TEMP%\hdc10audit\baseline.py`，避免触发编辑器/格式化链路）：对 `test/hdc10_real_frames.pkl` 全 60 帧跑 `_parse_pb_only(fb, 1)`，把 `(key, 全部行)` 序列化到 `baseline.json`。
- [ ] 0.2 同脚本记录：`msdu_type` 分布、进入应用层解析的帧、`未定义(厂商扩展)`/`未识别的业务数据` 出现位置。
- [ ] 0.3 人工过一遍差异预期：改动后**允许**变化的是 →(a) `msdu_type ∈ {48,128}` 的帧从「未定义」变为应用层解析；(b) fallback 中出现 `MSG_ID_NAMES` 命中者被命名；(c) `sec_mode != 0` 的帧多一行提示。**不允许**变化的是 → 其余所有行。
- [ ] 0.4 保存基线文件路径到任务 `implement.md` 末尾的「验证记录」段落。

验证：

```bash
python  # 运行仓库外脚本，输出 baseline.json
```

**审查门**：0.3 的差异预期清单必须写下来（就是步骤 5 对拍时的验收口径）。

## 步骤 1：类型值域单一来源（D1）

- [ ] 1.1 在 `hdc10_parser.py` 靠近 `MSDU_TYPES`(:115) / `SINGLEHOP_MSG_TYPES`(:128) 处新增 `APP_MSDU_TYPES`（`{48, 128}`）与 `IPV4_MSDU_TYPES`（`{49, 129}`）两个 `frozenset`，注释注明表10/表13 来源。
- [ ] 1.2 不改动现有两张表的内容（它们是字段名的单一来源，值域判据用新常量）。

验证：`python -c "from hdc10_parser import APP_MSDU_TYPES, IPV4_MSDU_TYPES; print(APP_MSDU_TYPES, IPV4_MSDU_TYPES)"`

## 步骤 2：`_parse_msdu_payload` 分派收口（D2）

- [ ] 2.1 按 D2 顺序重排分支：`== 0` → MME（不动）｜`in APP_MSDU_TYPES` → 应用层（新增）｜`in IPV4_MSDU_TYPES` → IPv4 提示行（新增）｜`is None` → 首字节启发式（现状移入）｜其余 → 现状「未定义」分支（文案补「MAC头声明类型:X」）。
- [ ] 2.2 保持 `except Exception` 现状**不动**（P2-7 属范围外），但确认应用层分支不吞异常。
- [ ] 2.3 不引入实例状态（陷阱 41）。

验证：`python test/test_hdc10.py`（20 项回归）。

## 步骤 3：`_parse_app_only` 收口（D3）

- [ ] 3.1 按 D3 重写入口判据：`len < 4` → 长度不足错误行 + 原始数据；`data[0] in APP_PORTS or data[3] == 0` → 应用层；`_detect_fc` → 完整帧（保留）；否则 → 应用层 + 「按应用层解释(推测)」注明。
- [ ] 3.2 确认三条路径的文案不重复、不含「未识别格式的应用层数据」以外的空白返回。

验证：`python test/test_hdc10_batch_strip_level.py`（29 项）+ 手工用 `parse_level='app'` 试 `0x11`/`0x13`/完整 MPDU 三种输入。

## 步骤 4：fallback 命名（D4，覆盖 P0-1/P0-2）

- [ ] 4.1 改 `_parse_app_payload` 的 else 分支：`MSG_ID_NAMES.get(msg_id)` 命中 → 业务名行 + 「⚠ 格式未定义」说明 + 原始数据；未命中 → 现状文案 + 「未在本规范报文ID表中定义」。
- [ ] 4.2 确认 `0x00A0`/`0x00A4` **无需新增专用分支**即被命名（若发现仍需专门分支，说明设计遗漏，回到 design.md 修正）。
- [ ] 4.3 检查 `port` 参数在该分支是否应参与展示（端口名从 `APP_PORTS` 取，便于 0x1A 场景）。

验证：手工构造 `1A A0 00 00 + 数据` → 应出现「鉴权安全」+「格式未定义」。

## 步骤 5：安全模式提示（D5）+ 摘要黑名单两端同步

- [ ] 5.1 `_parse_application_layer` 在「安全模式」行后插入 `sec_mode != 0` 的提示行。
- [ ] 5.2 `main_gui.py` 的 `_GW_APP_META_FIELDS` 与 `reflex_web/reflex_web/web_utils.py` 对应常量**逐字**新增 `"⚠ 安全保护"`。
- [ ] 5.3 用步骤 0 的基线对拍：**除 0.3 允许的三类变化外零差异**（硬门）。

验证：`python test/test_gw_app_summary_detail.py`（42 项）+ 对拍脚本零非预期差异。

## 步骤 6：新增测试套件 `test/test_hdc10_app_dispatch.py`

- [ ] 6.1 文件头 `import _path_setup  # noqa: E402,F401`（F401 必须一并抑制，否则 ruff --fix 会删）。
- [ ] 6.2 覆盖 A1~A9：A1/A2 命名+未定义注明；A3 非白名单端口通用头完整；A4 `msdu_type=48` 进应用层；A5 `msdu_type=None` 不误判；A6 `_parse_app_only` 完整 MPDU 走 FC；A7 `0x2004` 提示行 + 校时字段与基线逐行一致；A8 真实帧全量不抛异常 + `msdu_type=48` 进应用层（**只用 `key[1] != '-'` 的真实业务帧断言**）；A9 fuzz 936 组合零崩溃。
- [ ] 6.3 加入对拍断言：`_GW_APP_META_FIELDS` 两端含新键（防单边改）。
- [ ] 6.4 登记进 `release_check.py` 的 `CORE_TESTS`。

验证：`python test/test_hdc10_app_dispatch.py` 全绿。

## 步骤 7（硬门）：变异反证（A12）

逐条临时改坏、确认测试**变红**，再还原：

- [ ] 7.1 移除 `_parse_msdu_payload` 的 `APP_MSDU_TYPES` 分支 → A4 必须变红。
- [ ] 7.2 把 `_parse_app_only` 判据改回 `data[0] in (0x11,0x12,0x1A)` → A3 必须变红。
- [ ] 7.3 去掉 `MSG_ID_NAMES` 查表 → A1/A2 必须变红。
- [ ] 7.4 移除安全模式提示行 → A7 必须变红。

**审查门**：四条都要实际观察到变红（不是推断）。若某条不变红，说明测试未覆盖该路径，回步骤 6 补。

## 步骤 8：全量回归

```bash
python test/test_hdc10_app_dispatch.py     # 新增
python test/test_hdc10.py                  # 20
python test/test_hdc10_meter_reading.py     # 13
python test/test_hdc10_real.py
python test/test_hdc10_batch_strip_level.py # 29
python test/test_gw_new_gen.py              # 44
python test/test_gw_app_summary_detail.py   # 42
python test/test_web_parse_fixes.py         # 75
python release_check.py                     # FAIL=0 / WARN=0
```

- [ ] 8.1 全部通过；`release_check.py` 无新增 FAIL/WARN。
- [ ] 8.2 若出现失败：先判断是「预期变化需更新断言」还是「真回归」——前者必须在 implement.md 记录原因。

## 步骤 9：文档与版本

- [ ] 9.1 `main_gui.py`：`CHANGELOG` 顶部新增 1.23.20 条目；`APP_VERSION` → `1.23.20`；`BUILD_DATE` → 当日。
- [ ] 9.2 `AGENTS.md`：§8 新增陷阱条目（应用层判据以 MAC 头类型字段为准、值域常量单一来源、规范未定义业务的呈现约定、真实帧夹具含填充帧的判别方法）；§10 摘要。
- [ ] 9.3 `README.md` 版本徽章；`python release_check.py --sync-iss` 同步两个 `.iss`。
- [ ] 9.4 清理仓库外临时脚本与基线目录。

## 验证记录

（执行时填写：基线文件路径、对拍差异清单、四条变异反证的实测输出、各套件通过数）

| 项目 | 结果 |
| --- | --- |
| 基线对拍差异 | 仅 3 帧变化（idx 9 / 48 / 50），其余 57 帧逐行逐字节一致（sha256 指纹 `e20b9e23…99631` 前后相同）。**口径提醒**：该数字仅针对 `_parse_pb_only(fb, 1)`；放大到 6 个解析级别 + 合成帧共 1566 用例时 896 例有差异——全部属设计允许的四类（app 级别 60/60 帧由「未识别格式」变为应用层解析 + `⚠ 推测解析`，即 A3/R2 的**预期**行为），**未归类差异 = 0** |
| 变异反证 | 5 条全部实际观察到变红（FAIL=8 / 4 / 11 / 6 / 1），逐条还原并 sha256 校验通过；第 5 条对应 `_parse_app_only` 的 `and not has_fc` 守卫（防 NID 高字节=0 的合法完整 MPDU 被错位解析） |
| 套件通过数（终值） | 新套件 **94/94**（独立检查后的 F1 修补 +3 项）；hdc10 20/20；meter_reading 13/13；real 3/3；batch_strip_level 29/29；gw_new_gen 44/44；gw_app_summary_detail 42/42；web_parse_fixes 75/75 |
| release_check | **PASS=65 FAIL=0 WARN=0**（1.23.20 版本链全对齐：APP_VERSION / CHANGELOG 顶部 / README 徽章 / 两个 `.iss`） |

### 基线文件（仓库外，临时产物）

- 目录：`C:/Users/lirt3/AppData/Local/Temp/hdc10audit/`
- `baseline.json`（改动前 60 帧全量快照）／`after.json`（改动后）／`golden_synth.json`（合成帧 golden）
- 脚本：`baseline.py`（快照）、`diff.py`（逐帧差分）、`golden_synth.py`（golden 生成）、
  `gen_consts.py`（内嵌常量生成）、`mutate.py`（变异反证驱动）、`hdc10_parser.orig.py`（还原备份）
- 临时产物全部在仓库外；执行过程中曾误落仓库根的 `golden_synth.json` 已移出并复核 `git status` 干净

### 步骤 0.3 差异预期清单（步骤 5 的验收口径）

改动后**允许**变化的只有下列四类，实测**仅**这四类：

| 类 | 内容 | 实测帧 |
| --- | --- | --- |
| (a) | `msdu_type ∈ {48,128}` 的帧由「类型X: 未定义(厂商扩展)」变为应用层解析 | idx 48（128）、idx 50（48） |
| (b) | fallback 中 `MSG_ID_NAMES` 命中者被命名（+「⚠ 格式未定义」+ 说明注明依据） | 无（夹具中无此类业务ID） |
| (c) | `sec_mode != 0` 的帧多一行「⚠ 安全保护」提示 | idx 50（sec=1） |
| (d) | **必需补充类**：`msdu_type` 表外（47）的帧不再按首字节启发式进应用层解析（PRD P1-4/R3 要求的另一半修复，design D2 else 分支的必然结果） | idx 9 |

> (d) 未列在 implement.md 0.3 原文的三类里，但它是 design D2 分派重排的**直接蕴含**，也是 PRD
> 「双向误判」验收的一半；已在测试中以「A8 分派与 MAC 头声明类型逐帧一致」钉住。

## 独立检查（Phase 2.2）结论与修补

独立检查子代理复核**通过**（回归数字逐条复现一致、5 条变异反证自行复现、范围未越界；并用「HEAD 版解析器」独立对拍 1566 用例，未归类差异 0），同时抓出 **1 项本轮引入的真实缺陷**：

- **F1（已修）**：初版 fallback 对**任意**命名业务都印「本规范…未给出该报文的字段格式」，但 24 个业务ID 中只有 `0x0A0`/`0x0A4` 真无定义，其余 22 个属「有定义、仅端口未命中分支」→ **44 种端口×业务ID 组合输出错误依据**（违背 R1）。修法：新增 `MSG_ID_NO_FORMAT_DEFINED` 显式建模**规范文档事实**，fallback 分两种措辞（`⚠ 未按业务格式解析` / `⚠ 格式未定义`），并补 A13 表驱动断言（24×3 组合）。该表**不是**分派链的第二份清单——哪个组合有解析仍由 `if/elif` 链权威决定。
- **R4（已修）**：IPv4 提示行行名硬编码「IP报文」与表13 的「IPV4报文」不一致 → 改用 `type_label`（仍取自类型表，不另写字面量）。
- **R2（部分缓解）**：仓内原仅 A7 钉了「校时」一个业务的 app 级别基线；A13 表驱动已覆盖 24 个业务ID 在三种端口下的呈现，另有 5 条变异反证提供行为层防护。
- **R5（已完成）**：版本/文档同步（CHANGELOG 1.23.20、AGENTS.md 新陷阱 47 + 陷阱 45 定位方式修正、README 徽章、`--sync-iss`）。
- 残余风险（本次未覆盖）：GUI 实机未目视冒烟（仅 offscreen/逻辑层）；Web 端未起 Reflex 做端到端；`_ruff_f821()` 在无 ruff 环境退化为空过。
- 提醒下一维护者：`AGENTS.md §8 陷阱 45` 已把两条静态告警改为**按符号名**定位并附复核命令——**行号会随改动漂移**，不要按行号判断是否新引入。

## 实现偏离说明（需主会话确认）

1. **`_parse_app_only` 判据加 `and not has_fc`（偏离 design D3 字面顺序）**
   D3 字面为「端口表命中 **或** 控制字合规 → 应用层」**先于** FC 检测。实测 FC 的 byte3 是
   **网络标识(NID)高字节**（`hdc10_parser._parse_fc`），取 0 的概率约 1/256 → 字面实现会把
   「NID 高字节为 0 的合法完整 MPDU」按应用层错位解析，违反 A6「仍走 FC 检测路径，行为不回归」。
   现实现为 `data[0] in APP_PORTS or (data[3] == 0 and not has_fc)`，并新增断言 A6d 钉住该路径
   （变异 7.5 去掉守卫 → A6d 变红，实测确认）。A3/A3b 行为不受影响（实测通过）。
2. **未命名业务ID 的说明文案补了一句依据**（design D4 括号内要求）：
   `未识别的业务数据(0x005)：未在本规范报文ID表中定义`。只影响原本走 fallback 的表外 ID。
3. **A9 的组合数口径**：PRD 原写「22 个业务ID × 3 × 13 = 936」（算式与 936 不符），已按 `MSG_ID_NAMES` 实测 **24** 项修正为「24×3×13 = 936」，另加 78 组表外 ID（0x000/0x347）fuzz。
4. **两端 `_GW_APP_META_FIELDS` 元素顺序本就不同**（集合相同，行为无关：黑名单判定是 `any()`）→
   对拍断言用**集合相等**而非元组相等；未顺手重排顺序（避免超范围改动）。
5. **`printable`/ASCII 提示等既有 fallback 文案一字未改**（0.3 门要求）——`类型47` 等提示文本
   保持原样，未额外加「MAC头声明」前缀（原文已含 `类型X` 声明值）。

## 未完成 / 留待主会话

- 步骤 9 全部：`CHANGELOG` 1.23.20 条目、`APP_VERSION`/`BUILD_DATE`、`AGENTS.md §8` 新增陷阱条目
  （建议编号 47：应用层判据以 MAC 头类型字段为准、值域常量单一来源、规范未定义业务的呈现约定、
  真实帧夹具含填充帧的判别法）、`§10` 摘要、`README.md` 徽章、`release_check.py --sync-iss`。
- `0x00A0`/`0x00A4` 的**字段级**解析与抄表 DATA 内嵌 645/698.45、IPv4 载荷深度解析：PRD 明确范围外。
- 本机静态分析（pi-lens/pyright）对 `main_gui.py`(88 项)、`web_utils.py`(13 项)、
  `hdc10_parser.py`(2 项：`bcsha_phases` possibly unbound / `msdu_len` 类型收窄) 的告警均为**改动前既有**：
  hdc10_parser 两条已由 AGENTS.md §8 陷阱 45 记录为不可达路径误报（行号 +8 = 新增常量行数，文本逐字相同），
  未按告警改造；ruff（项目权威，F 类）改动前后均为 14 项、分布逐条相同。
