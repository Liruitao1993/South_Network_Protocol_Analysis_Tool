# 执行计划：Web↔GUI 修复同步

> 每步附验证命令；`[GATE]` 为必须停下评审的门。
> 命令均在项目根执行（WSL 侧 bash；`python3` 走 WSL，涉及 Qt/offscreen 的用 `pwshu` 或 WSL python，按现有测试惯例）。

## 步骤 1 前置核实（只读，不产码）

- [ ] 1.1 核实 `GDW10376Parser` 自定义 AFN API 与落盘位置：
  `grep -n "custom_afn\|def .*afn" gdw10376_parser.py | head -20`，确认增/删方法名、去重语义、写盘函数是否硬编码 `app_paths`
- [ ] 1.2 复核桌面测试模式摘要的两个调用点上下文（`main_gui.py:8546`、`:8787`），记下协议9 的**首个分支**位置
- [ ] 1.3 复核 `web_utils.get_csg_new_gen_summary` / `get_hdc10_summary` 的现有片段顺序与返回拼接方式
- [ ] 1.4 复核 `custom_di_store.load_custom_di/save_custom_di` 的完整调用链（谁会传入路径）
- [ ] 1.5 复核 Web 查询页 `lookup_tab()`（`reflex_web.py:10642`）结构，确定增删控件的插入位置

**验证**：把结论写进任务 notes（`python3 .trellis/scripts/task.py set-meta ...`）；若 1.1 结论触发 D5.3 降级，先在清单里登记再继续。

## 步骤 2 R1 审计清单 v1（`docs/Web与GUI同步审计.md`）

- [ ] 2.1 逐版读 `main_gui.py:CHANGELOG` 的 1.23.0~1.23.22 条目，每条一行
- [ ] 2.2 每条判定 `继承`/`缺失`/`同错`/`N/A`，`继承` 必须给 import 链或同一调用点依据
- [ ] 2.3 已知三项缺口按 D2/D4/D5 的判定写入（645 转表 `同错`；测试模式摘要 `缺失`；查询页 CRUD `缺失`）
- [ ] 2.4 清单末尾加「后续区间（1.22.x 及更早）」待办小节

**[GATE] 评审**：若审计发现**新的** `同错` 或 `缺失`（非 R2~R4 三项），暂停并与用户确认是否纳入本任务范围，再决定继续或拆任务。

**验证**：`grep -c "^| 1\.23\." docs/Web与GUI同步审计.md` 条数与 CHANGELOG 该区间条目数一致；抽查任意 3 条能按依据复核。

## 步骤 3 R2 — 645 转表偏移修复 + 单一来源

- [ ] 3.1 改 `protocol_registry.DLT645GuiParser.parse_to_table`（`:363` 一带）：删除 `total_len`，引入 `frame_len` / `data_end` / `cs_pos` / `end_pos`（公式见 design D3）
- [ ] 3.2 Web `reflex_web/reflex_web/reflex_web.py:511` `_safe_parse_to_table` 的 645 分支改为 `from protocol_registry import DLT645GuiParser` + `DLT645GuiParser(parser).parse_to_table(frame_bytes)`；删除 `:520` 起的整段复制体
- [ ] 3.3 新增 `test/test_dlt645_table_offsets.py`：合法帧逐行不变（对拍基准）· 实测帧 `68AAAAAAAAAAAA6811082CDD32375316` → `校验和[14,14]` / `⚠ 校验和错误[14,14]` / `帧结束符[15,15]` · `frame_len<12` 无负偏移 · 空表 · **单一来源守卫**（`reflex_web.py` 不再含 `total_len = 10 + data_len + 2` 且 import 了 `DLT645GuiParser`）
- [ ] 3.4 登记 `release_check.py:CORE_TESTS`

**验证**：
```
python test/test_dlt645_table_offsets.py
python test/test_dlt645_tolerant_parse.py      # 1.23.22 回归，合法帧逐行不变
python test/test_dlt645_pv_ext.py              # 光伏扩展回归（同一转表）
python test/test_nanwang_custom_di.py
```

**回滚点**：仅 3.1/3.2 两处改动，`git checkout` 单文件即可。

## 步骤 4 R3 — 测试模式摘要共享

- [ ] 4.1 新建 `frame_summary.py`（纯逻辑无 Qt），搬入 `main_gui.py:8219` 的函数体为 `extract_test_mode_content(table_data)`
- [ ] 4.2 `main_gui.MainWindow._extract_test_mode_content` 改一行转发（**保留方法名**，`test/test_csg_summary.py` 依赖）
- [ ] 4.3 Web `web_utils.get_csg_new_gen_summary` 追加片段（位置对齐桌面协议9 首个分支）
- [ ] 4.4 Web `web_utils.get_hdc10_summary` 追加片段（位置对齐桌面协议10/11 既有片段之后）
- [ ] 4.5 新增 `test/test_web_gui_parity.py` 的 R3 部分：真实测试帧（协议9 表61 / 协议10 检测扩展命令 / 协议11）桌面 vs Web 摘要逐字符一致；协议9 非测试帧摘要不变

**验证**：
```
python test/test_web_gui_parity.py
python test/test_csg_summary.py
python test/test_gw_monitor_summary.py
python test/test_gw_app_summary_detail.py
```

**回滚点**：`frame_summary.py` 为新增文件，删掉即可；桌面仅一行转发。

## 步骤 5 R4 — Web 查询页 CRUD

- [ ] 5.1 `custom_di_store.load_custom_di` / `save_custom_di` 加**可选** `path` 参数（默认保持 `app_paths.data_path`），桌面调用点不传 → 行为零变化
- [ ] 5.2 Web State 加 `add_custom_di` / `delete_custom_di` 事件：校验（`validate_key_text`）→ `upsert_entry`/`remove_keys` → `save_custom_di(path=Web 数据根)` → `do_lookup()` 重查；内置 DI 用 `custom_key_set()` 拒删并给可读提示
- [ ] 5.3 `lookup_tab()` 加控件（仅协议0 显示）：DI 码输入 + 名称输入 + 「添加/覆盖」；结果表自定义行加「删除」
- [ ] 5.4 按步骤 1.1 结论决定国网 AFN：能注入路径 → 同手法接 `GDW10376Parser`；否则执行 D5.3 降级并在清单留档
- [ ] 5.5 `test/test_web_gui_parity.py` 的 R4 部分：路径注入（沙箱 patch）· 增删逻辑 · 内置拒删 · 桌面/Web 各落各自数据根

**验证**：
```
python test/test_web_gui_parity.py
python test/test_nanwang_custom_di.py     # 桌面 CRUD 回归（92 项）
python test/test_web_parse_fixes.py       # Web State 真实实例回归
python test/test_web_data_paths.py        # 数据外置约定回归
```

**回滚点**：`custom_di_store` 参数默认值不变；Web 侧改动集中在 `reflex_web.py` 查询页段。

## 步骤 6 R1 审计清单 v2 + 全量验证

- [ ] 6.1 回填本次三项处置（判定 / 修复位置 / 测试名）
- [ ] 6.2 **变异反证**（必须实测变红后还原）：
  1. 偏移公式改回 `total_len = 10 + data_len + 2` → `test_dlt645_table_offsets` 红
  2. 删掉 Web 摘要中的测试模式片段 → `test_web_gui_parity` 红
  3. 把 Web 645 分支改回复制体 → 单一来源守卫红
- [ ] 6.3 全量：
```
python test/test_dlt645_table_offsets.py
python test/test_web_gui_parity.py
python test/test_web_parse_fixes.py
python test/test_web_batch_paging.py
python test/test_hdc10.py
python test/test_gw_new_gen.py
python test/test_csg_new_gen.py
python test/test_dlt645_tolerant_parse.py
python test/test_dlt645_pv_ext.py
python test/test_nanwang_custom_di.py
python test/test_web_data_paths.py
python test/test_web_landing.py
python release_check.py
```
- [ ] 6.4 确认 `release_check.py` PASS 且 **FAIL=0**；新增测试已在 `CORE_TESTS`

## 步骤 7 收尾

- [ ] 7.1 `main_gui.py:CHANGELOG` 头部加条目（版本 `1.23.23`，日期 2026-09-17）
- [ ] 7.2 `AGENTS.md` 更新：§8 陷阱 49（补「声明长度不符时偏移须用实际帧长」）、陷阱 31（645 转表已收口，从"两份实现"清单移除）、§10 变更日志加 1.23.23 摘要
- [ ] 7.3 `APP_VERSION` bump 至 `1.23.23`（若确认发版）；`python release_check.py --sync-iss`
- [ ] 7.4 `git add` + 提交（单提交聚合，便于回滚）

**验证**：`git status` 干净；`python release_check.py` 通过。

## 评审门汇总

| 门 | 位置 | 内容 |
| --- | --- | --- |
| G1 | 步骤 2 末 | 审计清单 v1 —— 是否发现需纳入范围的新缺口 |
| G2 | 步骤 5 末 | CRUD 交互等价性取舍（单条 vs 多选）与国网 AFN 是否降级 |
| G3 | 步骤 6 末 | 全量测试 + 变异反证结果 |

---

## 执行结果（2026-09-21 收口，版本 1.23.42）

**步骤 1 前置核实**：以代码实测代替 grep 记录——①645 转表 API 与 Web 调用点（`reflex_web._safe_parse_to_table`）；②桌面测试模式摘要两个调用点（`main_gui:8863` 协议9 首个分支 / `:9137` 协议10-11 第 9 步）；③Web `get_csg_new_gen_summary` / `get_hdc10_summary` 片段顺序；④`custom_di_store` 调用链；⑤Web 查询页 `lookup_tab()` 结构。**结论：`batch_core.py`（另一任务线的共享核心）已含 `extract_test_mode_content` + `TEST_MODE_SENTINELS` 的逐字搬移版**，因此 R3 不新建 `frame_summary.py`（原计划），改为直接复用 `batch_core` 单源——已删除临时新建的 `frame_summary.py`。

**步骤 2（R1 审计清单）**：`docs/Web与GUI同步审计.md` 完成。1.23.0~1.23.22 共 **167 条**逐条判定（继承 88 / 缺失 21 / 同错 0 / N/A 58，另 1 条 1.23.22 派生缺陷判同错），全部附 `文件:行号` 依据；含未覆盖区间 1.23.23~1.23.40（仅列标题）与 1.22.x 待办。

**G1 门**：除三项已知缺口外新发现 6 项 Web 缺失（时序图 / 批量日志快照跳转 / 脚本预处理 / pcap / 批量取消 / 协议6 预设）→ 用户决定**拆为后续子任务** `.trellis/tasks/09-21-web-missing-capabilities`（已建 PRD）。

**步骤 3（R2）**：`protocol_registry.DLT645GuiParser.parse_to_table` 偏移改按实际帧长（`frame_len`/`data_end`/`cs_pos`/`end_pos`）；Web 删除复制体改 import 单源；新增 `test/test_dlt645_table_offsets.py`（40 项，含单一来源守卫）；已登记 `CORE_TESTS`。合法帧输出逐行不变（回归 `test_dlt645_tolerant_parse.py` 135 项、`test_dlt645_pv_ext.py` 156 项全过）。

**步骤 4（R3）**：桌面 `_extract_test_mode_content` 改为一行转发 `batch_core.extract_test_mode_content`（`_TEST_MODE_SENTINELS` 同源）；Web `web_utils` 接入同一函数，`get_csg_new_gen_summary` 经新增 `_append_test_mode_segment`（带去重守卫，协议9 测试帧不重复追加）与 `get_hdc10_summary` 各补片段；新增 `test/test_web_gui_parity.py` R3 段（两端片段对拍 + 非测试帧不污染 + 单一来源守卫）。

**步骤 5（R4）**：`custom_di_store` 读写加可选 `path`；Web 协议0 自定义 DI 增/覆盖/删（含勾选列 + 批量「删除选中」，内置忽略并计数）；**G2 门用户决定：国网 AFN+Fn CRUD 纳入本次、删除需多选批量** → 追加 R4b：协议7 自定义 AFN+Fn 增删（`lookup_utils.add_gdw_custom_fn` / `remove_gdw_custom_fns` 薄封装 `GDW10376Parser` 既有 API）+ `gdw_afn_lookup.refresh()` 解决查询缓存不刷新；查询表新增「自定义」★ 列。G2 另一项：删除粒度由「逐行单删」升级为「勾选 + 批量删除」。

**步骤 6**：变异反证 3 条全部实测变红后还原 —— ①偏移公式回退（`test_dlt645_table_offsets` 8 项红）②去掉 Web 摘要片段（`test_web_gui_parity` 6 项红；协议11 路径单独变异再红 2 项）③645 复制体回潮（`test_dlt645_table_offsets` 4 项红）。全量 `release_check.py`：**PASS=86 / FAIL=1 / WARN=1**，唯一 FAIL 为 `test/test_hdc10_batch_strip_level.py`（「帧类型含 [11]」），属**另一条工作线的批量重构**（`_type_name` 由 `batch_parse_worker`/`batch_core` 生成），本任务未触及该链路。

**步骤 7**：CHANGELOG 新增 1.23.42；`APP_VERSION` 1.23.42 + `release_check.py --sync-iss`；AGENTS.md §1/§2 版本陈述、§8 陷阱 31（已收口清单）、新增陷阱 55、§10 摘要均已同步。

**已知遗留**：① 审计发现的 6 项 Web 缺失 → 后续任务；② 工作区内还有另一会话（顶部栏折叠 1.23.41）与 ED/TCP 监控等未提交改动，本次按用户要求一并提交；③ `test/test_hdc10_batch_strip_level.py` 的 FAIL 归另一条工作线。
