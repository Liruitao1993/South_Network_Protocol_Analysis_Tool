# 执行计划：前导 FE 唤醒字节容忍（协议8/6）

> 版本目标 `APP_VERSION 1.23.75 → 1.23.76`。
> 环境铁律（AGENTS §8 陷阱 62）：**从 cmd 侧发起的批量测试必须套一层 pwsh**，否则 GUI/offscreen 测试
> 会以 `0xC0000409` + 空输出「假红」；命令统一带 `PYTHONIOENCODING=utf-8`。

## 阶段 0 · 证据固化（已完成）

- [x] `research/fe-prefix-evidence.md`：报障帧逐字节复核、规范原文行号、调用路径地图、蓝牙分包算式、
      既有行为锚点。**后续所有实现不得与该文件冲突**；若实测推翻某条，先改该文件再改代码。

## 阶段 1 · 单一来源模块 + 协议8

- [ ] 新增 `wakeup_prefix.py`（纯逻辑无 Qt/无 parser 依赖）：
      `WAKEUP_BYTE` / `WAKEUP_FIELD_NAME="唤醒前导字节"` / `wakeup_prefix_len` / `strip_wakeup_prefix`
      / `wakeup_display` / `shift_row_offsets`（只位移第 5/6 列同时为 `int` 的行）。
      docstring 写清规范出处（698 §6.3.1 b) / 645 §5.3.1）与「只剥帧首连续 0xFE」口径。
- [ ] `dl_t698_45_parser.parse`：保留 `原始数据` 为原始输入；`frame_bytes, skipped = strip_wakeup_prefix(frame_bytes)`
      就地重绑；`skipped > 0` 时写 `result["唤醒前导"]`。
- [ ] `dl_t698_45_parser.parse_to_table`：正常与失败两条路径都插入首行前导行；其余行过 `shift_row_offsets(rows, skip)`；
      `skip == 0` 时走原路径（逐行不变）。
- [ ] **审查点 A**：`python -c` 跑报障帧 →
      ① 39 字节解析成功（HCS/FCS 通过、OAD 40010200、数据 111111111111）；
      ② 表格首行 = `唤醒前导字节 / FE FE FE FE / … / 0 / 3`，`起始字符` 行偏移 = `(4,4)`、`结束符` = `(38,38)`；
      ③ 去掉 FE 的 35 字节帧表格与改动前**逐行相同**（用 `git stash` 前后各跑一次对拍）。

## 阶段 2 · 协议6（解析器 + 表格）

- [ ] `dlt645_parser.py`：`check_structure` / `calc_checksum` / `check_frame` / `parse` 四入口统一先剥离；
      `parse` 新增 `wakeup_len`，`raw_hex` 保留原始输入，`fields` 顶部插入 3 元组前导行；
      `valid` 语义不变。
- [ ] `protocol_registry.DLT645GuiParser.parse_to_table`：取 `wakeup_len` 作 skip；
      新增 `"前导" in field → (0, max(0, skip-1))` 分支（放在最前）；其余分支字面偏移整体 `+skip`；
      `skip == 0` 时逐行不变。
- [ ] **审查点 B**：`FE FE FE FE` + 合法 645 帧 → `valid=True`、CS 通过、表格每行偏移 = 无 FE 时的偏移 + 4；
      `test_dlt645_table_offsets.py` / `test_dlt645_tolerant_parse.py` 全绿。

## 阶段 3 · 校验一致性

- [ ] `validator/dl_t698_45_validator.py`：入口剥离；`n` 与起始/结束/长度一致性全部基于剥离后帧；
      `skip > 0` 时最前面追加 PASS 说明项（名称含「前导」）。
- [ ] `validator/dlt645_validator.py`：同上（含 CS 与数据长度项）。
- [ ] **审查点 C**：同一带 FE 帧「解析成功」且「校验全 PASS」，不出现「解析成功但校验报起始字符错误」；
      无 FE 帧校验项与结论与改动前一致。

## 阶段 4 · 蓝牙分包可见性（报障 2）

- [ ] `bluetooth_worker._write_coro`：`len(chunks) > 1` 时 `log_message` 输出
      「按单包上限 N 字节分 M 包写入（协商 MTU=…）」；不改正则/尺寸/信号顺序。
- [ ] `bluetooth_core` / `bluetooth_tool_widget`：确认 MTU 与单包上限文案仍来自同一来源（如已如此则不动）。
- [ ] 文档侧记录：ATT 层 `MTU−3` 为物理上限（本次实测 20 ⇒ MTU 23）；698 §6.3.1 c) 帧内不得有空闲间隔
      ⇒ 建议「包间延迟」设 0；减少分包只能靠设备端更大 MTU。

## 阶段 5 · 测试

- [ ] 新增 `test/test_wakeup_fe_prefix.py`（`import _path_setup  # noqa: E402,F401`）：
      - [1] `wakeup_prefix.py` 纯逻辑：0/1/2/4 个 FE、全 FE、无 FE 恒等、`shift_row_offsets` 跳过 None。
      - [2] 协议8：报障帧 golden（状态/HCS/FCS/OAD/数据）、局部前缀（FE×1、FE×2）、全 FE 降级、
            表格首行与偏移整体位移、**无 FE 帧输出与锚点快照逐行相同**。
      - [3] 协议6：`FE×4 + 合法帧` → parse/valid/CS、`DLT645GuiParser` 每行偏移 +4、无需 FE 时逐行不变、
            虚拟表 `dlt645_sim` 行为不变。
      - [4] 两个校验器：带 FE 帧全 PASS（含「前导」项）；无 FE 帧项与结论不变。
      - [5] 护栏：协议 0/7/9/10/11/12/13 对带 FE 输入的结论与改动前一致（仍报错/仍按原样解析）。
      - [6] 批量与 Web：混合日志（含 FE 的 698 帧 + 其它帧）提取正确；Web 单帧解析结果与桌面逐行对拍。
      - [7] offscreen GUI：单帧页粘贴报障帧 → 解析成功且首行为前导行；
            `MainWindow._serial_parse_provider`（串口/蓝牙共用）对报障帧返回非失败摘要。
      - [8] 变异反证（跑完必须还原）：
            ① `wakeup_prefix_len` 恒返回 0 ⇒ [2] 变红；② 表格不位移 ⇒ 偏移断言变红；
            ③ 校验器不剥离 ⇒ [4] 变红；④ 645 表格分支不加 `+skip` ⇒ [3] 变红。
- [ ] `test_bluetooth_worker.py` 补分包日志断言（尺寸不变 + 日志含单包上限与 MTU）。
- [ ] 新增测试登记 `release_check.py:CORE_TESTS`。
- [ ] 既有套件回归（经 pwsh）：
      `test_dl_t698_45.py`、`test_dl_t698_45_endian.py`、`test_dl_t698_45_extract.py`、
      `test_dl_t698_45_data_decode.py`、`test_dlt645_tolerant_parse.py`、`test_dlt645_table_offsets.py`、
      `test_dlt645_lme.py`、`test_dlt645_pv_ext.py`、`test_dlt645_sim.py`、`test_dlt645_frame_gen.py`、
      `test_bluetooth_core.py`、`test_bluetooth_worker.py`、`test_bluetooth_widget.py`、
      `test_web_parse_fixes.py`、`test_web_gui_parity.py`、`test_gui_batch_perf.py`。
- [ ] **审查点 D**：以上全绿 + 4 条变异反证均实测变红（记录输出）。

## 阶段 6 · 文档与版本

- [ ] `main_gui.py:CHANGELOG` 头部新增 1.23.76 条目（要点：前导 FE 合规修复 + 覆盖范围 + 蓝牙分包说明 +
      依据行号 + 测试与变异反证）。
- [ ] `APP_VERSION` → `1.23.76`；`BUILD_DATE` 仅在本次要打包时才更新。
- [ ] `python release_check.py --sync-iss` 同步两个 `.iss`。
- [ ] `AGENTS.md`：§5.4（645）/§5.6（698）各加一句前导 FE 约定；§8 新增陷阱（编号 75）：
      前导 FE 单一来源 + 表格偏移整体位移 + 只对 68 家族 6/8 生效 + 蓝牙分包不可消除；
      §10 追加 1.23.76 摘要。
- [ ] `README.md`：若其协议6/8 描述涉及起始符判据则同步，否则不动。
- [ ] `python release_check.py --with-gui` → **FAIL=0**（经 pwsh）。
- [ ] 提交：只提交本任务 hunk（并发会话在改 `main_gui.py`/`reflex_web.py`，禁止 `git add -A`）。

## 审查点汇总

| 审查点 | 时机 | 判据 |
|---|---|---|
| A | 阶段 1 后 | 报障帧成功 + 偏移对齐 + 无 FE 帧逐行不变 |
| B | 阶段 2 后 | 645 带 FE 帧 valid + 偏移 +4 + 既有套件绿 |
| C | 阶段 3 后 | 解析与校验结论一致 |
| D | 阶段 5 后 | 新测试全绿 + 4 条变异反证变红 + 既有套件全绿 |
| E | 提交前 | release_check FAIL=0、.iss 同步、文档齐 |

## 回滚点

1. 阶段 1 失败 → 删除 `wakeup_prefix.py` + `git checkout dl_t698_45_parser.py`。
2. 阶段 2/3 失败 → `git checkout dlt645_parser.py protocol_registry.py validator/`。
3. 无持久化/配置迁移 ⇒ 回滚不需清理任何运行时数据。
