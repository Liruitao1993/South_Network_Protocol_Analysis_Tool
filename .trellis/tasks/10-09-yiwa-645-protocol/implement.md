# 执行计划：依瓦定制645（协议13）

> 依据：`prd.md` + `design.md`。按序执行；每步末尾的「验证」必须实际跑通再进入下一步。
>
> **运行环境铁律（AGENTS.md 陷阱 62）**：GUI/offscreen 测试**不要**从 `cmd.exe` 直接起 python
> （父进程为 cmd 时 GUI 测试会以 `0xC0000409` 崩溃、输出全空，是**假红**）。
> 本计划所有测试命令在 bash 工具内一律经 **`pwshu`** 执行（`pwsh` → python → 测试）。
> 长任务（打包、全量门禁）交给 `bg_run`，且命令里必须套一层 pwsh。

---

## 阶段 0：前置确认（无代码改动）

- [ ] 0.1 确认工作区状态：`git status --short`，记录**已有的 37 项未提交改动**（`.gitignore`/`2222.iss`/
      `AGENTS.md`/`CLAUDE.md`/`README.md`/`csg_new_gen_parser.py`/`frame_gen_widget.py`/`main_gui.py`/
      `protocol_registry.py` 等），**不要**把它们混进本任务的提交。
      → 审查点：如这些改动属于未完成的工作，先与用户确认提交边界。
- [ ] 0.2 复核协议文档与图片仍在位：
      `协议文档/13.依瓦定制645协议/{依瓦定制645协议.md,images/图1-数据格式.png,images/图-COMMAND位定义.png}`
- [ ] 0.3 基线回归（改动前必须全绿，作为「协议6 零回归」的比较基准）：
      ```bash
      pwshu 'python test/test_dlt645_pv_ext.py'
      pwshu 'python test/test_dlt645_tolerant_parse.py'
      pwshu 'python test/test_protocol_registry.py'
      pwshu 'python test/test_web_landing.py'
      ```
      → 记录各项通过数，写进任务 notes。

---

## 阶段 1：线格式核心（`yw645_wire.py` + `yw645_di.py`）

- [ ] 1.1 写 `yw645_wire.py`：常量、`MODE_*`、地址编解码、长度拼接、`calc_cs`、`apply_mask`、
      `encode_items`/`decode_items`（含形态打分）、`encode_frame`、`frame_total_len`。
      纯 stdlib、零 Qt、**不得 import 任何协议模块**。
- [ ] 1.2 写 `yw645_di.py`：`DI_TABLE`（附录A 两项，含 `enum`）、`DI_INDEX_LITERAL`/`DI_INDEX_SWAPPED`、
      `di_lookup`、`di_payload_note`。
- [ ] 1.3 写 `test/test_yw645_wire.py`（文件头 `import _path_setup  # noqa: E402,F401`）：
      - 地址：`123456789012`→`12 34 56 78 90 12`、`103000000010`→`10 30 00 00 00 10`、
        `45000000013`→`04 50 00 00 00 13`、13 位取低 12 位、广播 `AA×6`、含非数字报错
      - 长度：`10 08`→8、`20 0D`→13、`30 07`→7（**注意：X1/X2/X3 的 L 分别来自实际帧**）、
        `40 24`→36；`0xFFF` 边界；`0x1000` 报错
      - CS：X3/X6/X7/X8/X9 的 cs 值与帧内一致；X1/X2/X4/X5 的计算值等于 prd oracle 列；
        **范围反证**：`calc_cs(b[1:])` 与 `calc_cs(b[:]+cs)` 均不等于正确值
      - 掩码：`36 13` → `03 E0`、`37 13` → `04 E0`、`37 14 64 65 66 67 68 69 6A 6B 6C 6D 63 6E`
        → `04 E1 31 32 33 34 35 36 37 38 39 3A 30 3B`
      - items：请求（无 FL）/回复（带 FL）两种形态互不误判；`decode_items` 对 X2 的 payload
        给出 2 项且 ID 为 `0010`/`0020`
      - `frame_total_len`：9 条示例的期望总长
- [ ] 1.4 验证：
      ```bash
      pwshu 'python test/test_yw645_wire.py'
      ```
      → **审查点 A**：线格式是所有下游的地基，此处必须 100% 绿且逐字节 oracle 通过才继续。
- [ ] 1.5 变异反证（≥3 条，各自实测变红后 `git checkout` 或手工还原）：
      ① 地址改为小端 → 地址断言变红；② `len_from_cmd` 改为 `cmd&0x0F` 单字节 → 长度断言变红；
      ③ `calc_cs` 范围改为 `body[1:]` → CS 断言变红；④ `apply_mask` 加减号反转 → 掩码断言变红。

---

## 阶段 2：解析器与校验器

- [ ] 2.1 写 `yw645_parser.py`：`YW645Parser`（`last_meta` / `parse` / `parse_to_table` / `get_summary` /
      `is_frame`(类+模块级) / `calc_checksum`），严格按 `design.md §5` 的元组契约
      （`(名称, 原始值, 解析值, 说明, 起偏移, 末偏移闭区间)`）。
- [ ] 2.2 实现 0x33 自动判别（`design.md §3`）与 items 形态判别（§2.6），结论写入 `last_meta`；
      提供 `assume_masked` 显式覆盖参数。
- [ ] 2.3 容错：`len<12` 降级；CS 错 / 长度不符 → 完整解析 + `⚠` 行（含正确值）+ `valid=False`；
      提示行名含「校验和」子串。
- [ ] 2.4 写 `validator/yw645_validator.py`（继承 `BaseValidator`，`verify` 返回 `ValidationResult`，
      检查项见 prd R8.2），并在 `validator/__init__.py` 导出。
- [ ] 2.5 写 `test/test_yw645_parse.py` + `test/test_yw645_validator.py`：
      - 9 条示例 golden；**每条示例的「未混淆形态」与「已混淆形态」两种输入断言相同字段结果**
      - X7（作者自述虚拟）只断言地址/长度/CS，不断言数据项切分
      - 容错：坏 CS（把 X3 的 `B4` 改 `B5`）、长度域改小/改大、截断帧、末字节非 16H、空帧、
        起始符非 68H → 均**非空表** + `valid=False` + 含 `⚠`
      - `last_meta` 全键存在性断言
      - `make_validator(13)` 可构造；坏 CS 帧对应检查项 FAIL 但 `parse` 仍完整
- [ ] 2.6 验证：
      ```bash
      pwshu 'python test/test_yw645_wire.py'
      pwshu 'python test/test_yw645_parse.py'
      pwshu 'python test/test_yw645_validator.py'
      ```
      → **审查点 B**：解析结果必须与 prd 的 AC2~AC7、AC11 逐条对齐。

---

## 阶段 3：注册表接入 + 批量提取

- [ ] 3.1 `protocol_registry._PROTOS` 追加 index=13（字段见 `design.md §8` 表），
      `lookup_builder_method` 加 `"di_yw645"` 映射。
- [ ] 3.2 `parser_registry._PARSER_SPECS` 加 `"yw645"`。
- [ ] 3.3 `main_gui`：`_extract_yw645_frames`（以 `_extract_modular_frames` 为模板，见 `design.md §6`）
      + `_extract_frames_for_protocol` 加 `yw645` 分支。**不搜索 0x16 定界（prd F5）**。
- [ ] 3.4 `main_gui`：`_create_yw645_lookup_content`（DI 表 + 关键词过滤，结构参考
      `_create_modular_iface_lookup_content`）。
- [ ] 3.5 修正既有「协议个数」硬编码断言（若有）：改为读 `protocol_registry.combo_labels()`。
      → 预期受影响：`test/test_window_state.py` / `test/test_serial_tool_widget.py` /
      `test/test_serial_proto_frame.py`（AGENTS.md 记录过 1.23.58 的同类修正）。**这是必要改动，须记录**。
- [ ] 3.6 写 `test/test_yw645_extract.py`：单帧 / 多帧拼接 / 前置噪声 / 长度域偏小 / 末字节不符 /
      **四协议混合日志互斥**（南网、国网、645、698.45 各一帧 + 依瓦一帧 → 只提取依瓦）。
- [ ] 3.7 验证：
      ```bash
      pwshu 'python test/test_yw645_extract.py'
      pwshu 'python test/test_protocol_registry.py'
      pwshu 'python test/test_window_state.py'
      pwshu 'python test/test_serial_tool_widget.py'
      pwshu 'python test/test_serial_proto_frame.py'
      ```
      → **审查点 C**：注册表接入后既有测试必须全绿（协议 6 零回归门禁）。

---

## 阶段 4：组帧 + 查询页 + 预设

- [ ] 4.1 写 `yw645_frame_gen.py`：`build_frame` / `YW645FrameGenerator` / `FRAME_TEMPLATES` /
      `build_from_template` / `YW645BuildError`。全部经 `yw645_wire`，**无第二份编码逻辑**。
- [ ] 4.2 写 `yw645_frame_gen_widget.py`（独立文件）：地址+广播、模式下拉（含写模式占位，见 D1）、
      数据项表格（增删/上下移）、输出区、「添加到预设」。
- [ ] 4.3 `frame_gen_widget`：左栏 `QStackedWidget` 追加 `yw645` 页 + 按 `frame_gen_mode` 切换 +
      输出/复制/清空接线（沿用协议 9 的挂载范式）。
- [ ] 4.4 `preset_buttons`：`preset_mode == "yw645"` → `YW645_command.json`（种子 5 条；
      **不得**写进 `DLT645_command.json`/`GW_command.json`）。
- [ ] 4.5 写 `test/test_yw645_frame_gen.py`（纯逻辑 + 闭环）+ `test/test_yw645_gui.py`（offscreen）。
      - 闭环：四类模式各「组帧 → 解析 → `valid=True` 且 CS 通过」
      - 报错：长度 > 0xFFF、地址含非数字、with_fl=True 且数据为空
      - 预设：写入路径隔离断言（patch `main_gui.data_path` **与** `app_paths.data_path`）
      - GUI：Tab 可见性与注册表一致、组帧页可生成、查询页可过滤、预设按钮可取出完整帧
- [ ] 4.6 验证：
      ```bash
      pwshu 'python test/test_yw645_frame_gen.py'
      pwshu 'python test/test_yw645_gui.py'
      pwshu 'python test/test_nanwang_custom_di.py'
      pwshu 'python test/test_dlt645_frame_gen.py'
      ```
      → **审查点 D**：组帧↔解析闭环（AC8）与预设隔离（AC9）通过；协议 6 组帧无回归。

---

## 阶段 5：Web 端

- [ ] 5.1 `reflex_web/reflex_web/landing_web.py` 的 `PROTOCOLS` 追加第 13 行。
- [ ] 5.2 `reflex_web/reflex_web/web_utils.py`：批量提取加 `yw645` 分支 + `get_frame_summary` 支持。
- [ ] 5.3 `reflex_web/reflex_web/lookup_utils.py`：`di_yw645` 数据源（复用 `yw645_di`，**不复制表**）。
- [ ] 5.4 在 Web 组帧下拉处给出「协议13 暂不支持 Web 组帧」可见提示（prd R7.4）。
- [ ] 5.5 写 `test/test_yw645_web.py`（或并入既有 web 测试）：Web 解析协议13 与桌面**对拍**
      （同一帧两端行数与关键字段一致）+ 首页协议表逐行对拍。
- [ ] 5.6 验证：
      ```bash
      pwshu 'python test/test_yw645_web.py'
      pwshu 'python test/test_web_landing.py'
      pwshu 'python test/test_web_parse_fixes.py'
      pwshu 'python test/test_web_gui_parity.py'
      ```
      → **审查点 E**：两端一致、无死链、无漂移。

---

## 阶段 6：打包、文档、门禁

- [ ] 6.1 `南网协议解析工具.spec`：`hiddenimports` 补 `yw645_parser`/`yw645_wire`/`yw645_di`/
      `yw645_frame_gen`/`yw645_frame_gen_widget`/`validator.yw645_validator`；
      `datas` 补 `YW645_command.json`。
- [ ] 6.2 `reflex_web/reflex_web_exe.spec` + `reflex_web/deploy_common.py`（若新增随包 JSON）。
- [ ] 6.3 测试登记进 `release_check.py:CORE_TESTS`（7 个 `test_yw645*.py`）。
- [ ] 6.4 文档同步：
      - `main_gui.py:CHANGELOG` 头部新增 1.23.68 条目（含 D1~D5 处置与「串口不加协议13 策略」的范围声明）
      - `main_gui.py:APP_VERSION` → `1.23.68`、`BUILD_DATE` 更新
      - `README.md` 协议表 + 下载区
      - `AGENTS.md`：§1 协议表加第 13 行、§3 目录树加新模块、§5 新增 §5.11 依瓦定制645 小节、
        §6 接入点、§7 测试清单、§8 新增陷阱（记 0x16 不可作定界 / 0x33 双形态 / 文档 D1~D5）、§10 摘要
- [ ] 6.5 全量门禁（bg_run，cmd 侧必须套 pwsh）：
      ```
      pwsh.exe -NoProfile -NoLogo -NonInteractive -Command "Set-Location 'E:\python\南网解析工具'; $env:PYTHONIOENCODING='utf-8'; python release_check.py --with-gui"
      ```
      → **审查点 F（最终门禁）**：`FAIL=0`。失败项若输出为空且退出码 `3221226505` → 按 AGENTS.md 陷阱 62
      判为假红，改用 pwsh 父进程重跑，**不要改代码**。
- [ ] 6.6 打包实测（可选但推荐）：
      ```bash
      pwshu 'pyinstaller 南网协议解析工具.spec --noconfirm'
      ```
      打包后必须**实测**：切到协议13 能解析 X6 帧、校验器可用（`make_validator` 走 importlib，
      漏 hiddenimports 只在 exe 里暴露）。

---

## 阶段 7：收尾

- [ ] 7.1 一致性复核（逐条对照 `prd.md` 的 AC1~AC16，把实际证据（测试名/输出）记进任务 notes）。
- [ ] 7.2 整理 diff，确认**未混入**阶段 0.1 记录的既有 37 项改动之外的内容。
- [ ] 7.3 提交（一次或按阶段拆分均可；CHANGELOG 与代码同提交）。
- [ ] 7.4 归档任务（`trellis-finish-work`），并把新踩到的坑回写 `AGENTS.md` §8。

---

## 回滚点

| 回滚点 | 操作 |
| --- | --- |
| 阶段 1~2 失败 | 删除 `yw645_wire.py`/`yw645_di.py`/`yw645_parser.py`/`test/test_yw645*`（**未接入注册表，无外部影响**） |
| 阶段 3 失败 | `git checkout protocol_registry.py parser_registry.py main_gui.py`（回到未接入状态） |
| 阶段 4 失败 | `git checkout frame_gen_widget.py preset_buttons.py`，删 `yw645_frame_gen*.py` |
| 阶段 5 失败 | `git checkout reflex_web/` |
| 整体放弃 | 从 `_PROTOS` 移除 index 13 + 删除全部新文件；无数据迁移、无配置格式变更 |

## 进度记录（执行时填写）

| 阶段 | 状态 | 证据（命令 + 通过数） |
| --- | --- | --- |
| 0 前置 | ☐ | |
| 1 线格式 | ☐ | |
| 2 解析+校验 | ☐ | |
| 3 注册表+提取 | ☐ | |
| 4 组帧+查询+预设 | ☐ | |
| 5 Web | ☐ | |
| 6 打包+文档+门禁 | ☐ | |
| 7 收尾 | ☐ | |
