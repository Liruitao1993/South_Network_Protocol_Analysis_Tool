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
