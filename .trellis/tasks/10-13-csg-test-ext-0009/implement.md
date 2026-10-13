# 执行计划：协议9 2.0 测试扩展 0x0009

> 目标版本 `APP_VERSION 1.23.76 → 1.23.77`。
> 环境铁律（AGENTS §8 陷阱 62）：从 cmd 侧发起的批量测试要套一层 pwsh，否则 GUI/offscreen 测试会以
> `0xC0000409` + 空输出「假红」；命令统一带 `PYTHONIOENCODING=utf-8`。
> 并发铁律：`main_gui.py` / `reflex_web/` 有其它会话在改 —— 提交时只挑本任务 hunk，禁止 `git add -A`。

## 阶段 0 · 证据固化（已完成）

- [x] `research/doc-0x0009-facts.md`：文档原文表、1.4 小节号↔扩展ID 对应、字节口径（`ext_data[x] = 文档字节 x+3`）、
      代码缺口定位、既有实现锚点、受影响的既有测试、过期模式数量文案清单。**后续实现不得与该文件冲突。**

## 阶段 1 · 解析（`csg_new_gen_cmd_payloads.py`）

- [ ] `_TEST_EXT_ID_MAP` 追加 `0x0009: "报文聚合传输测试模式"`。
- [ ] 新增 `_parse_test_ext_0009(data, base_offset)`：`报文聚合数目`（整字节，无位域）；
      `len(data) < 1` → `❌ 解析失败`；尾部走 `_remaining`。
- [ ] `_parse_test_ext_payload` 分派表登记 `0x0009`。
- [ ] **审查点 A**：构造 2.0 测试帧（测试ID=0x04 / 扩展ID=0x0009 / 数据 1 字节）跑 `parse_to_table`：
      ① `扩展ID` 行说明 = `报文聚合传输测试模式`；② 出现 `报文聚合数目` 行且解析值正确；
      ③ 未登记 `0x000A` 仍为 `保留扩展ID(0x000A)`。

## 阶段 2 · 组帧（`csg_new_gen_frame_gen.py`）

- [ ] `TEST_EXT_ID_MAP` 追加 `0x0009`（与阶段 1 同值同文）。
- [ ] 新增 `build_ext_0009(*, agg_count: int = 1) -> bytes`：`bytes([_clip_count(agg_count, "报文聚合数目", 0xFF)])`。
- [ ] `_EXT_BUILDERS[0x0009] = build_ext_0009`。
- [ ] `test_modes()` 追加 `ext_agg`（`fields=(ModeField("agg_count", "报文聚合数目", "int", 1),)`）。
- [ ] **审查点 B**：`build_test_pdu(0x04, ext_id=0x0009, agg_count=5).hex()` 逐字节核对；
      `agg_count=256` / `-1` / `"x"` 抛 `FrameBuildError`；`test_modes()` 长度 24 → 25。

## 阶段 3 · 仿照回填（`csg_frame_reverse.py`）

- [ ] `_fill_ext` 增加 `elif ext_id == 0x0009 and ext_data: params["agg_count"] = ext_data[0]`。
- [ ] **审查点 C**：阶段 2 组出的应用层帧 → `reverse_frame` → `key == "ext_agg"`、`agg_count` 一致、
      `unmapped == []`；用回填参数重建 == 原帧。

## 阶段 4 · 过期模式数量文案（顺带修正，R5.4）

- [ ] `csg_test_frame_gen_widget.py`：模块级 `_MODE_COUNT = len(fg.test_modes())`；
      `_PAYLOAD_SOURCE_OPTIONS` 标签与 `payload_src_combo` tooltip 改用 `_MODE_COUNT`；
      docstring 第 5 行去掉写死的数字。
- [ ] **审查点 D**：`_PAYLOAD_SOURCE_OPTIONS` 标签与实际模式数一致（25），tooltip 同值。

## 阶段 5 · 测试

- [ ] 新增 `test/test_csg_test_ext_0009.py`（`import _path_setup  # noqa: E402,F401`）：
      [1] 映射表与 `test_modes()`（含 `ext_agg`、key 唯一）；
      [2] 解析 goldens（0x00 / 0x01 / 0x05 / 0xFF / 数据不足 / 未登记扩展ID 护栏）；
      [3] 组帧逐字节（数据区长度 = 5、扩展ID LE、数据域 1 字节）+ 越界报错；
      [4] **闭环**（组帧 → `CSGNewGenParser.parse_to_table` → 字段相等）；
      [5] **反解闭环**（应用层帧 → `reverse_frame` → 重建逐字节相同）；
      [6] 摘要片段（`batch_core.extract_test_mode_content` 含 `扩展ID:报文聚合传输测试模式`）；
      [7] 变异反证记录位（脚本内提供 `--mutate` 说明或注释，实测由人工执行）。
- [ ] 登记 `release_check.py:CORE_TESTS`（加在 `test/test_csg_frame_reverse.py` 之后）。
- [ ] 既有套件回归（经 pwsh）：`test_csg_new_gen.py`、`test_csg_summary.py`、`test_csg_frame_reverse.py`、
      `test_csg_frame_templates.py`、`test_csg_link_frame_gen.py`、`test_csg_batch_prefix.py`、
      `test_csg_batch_parse_level.py`、`test_csg_hrf_mac.py`；GUI 侧 `test_csg_frame_gen_gui.py`、
      `test_collapsible_section.py`。
- [ ] **变异反证 3 条**（跑完必须还原）：① 解析改读 `ext_data[1]`；② 组帧写 2 字节 `u16le`；
      ③ 反解不填 `agg_count`。三条各自使 [2]/[3]/[5] 的断言变红。
- [ ] **审查点 E**：新测试全绿 + 3 条反证变红 + 既有套件全绿。

## 阶段 6 · 文档与版本

- [ ] `main_gui.py:CHANGELOG` 头部新增 1.23.77 条目（要点：新增扩展 ID、依据文档章节、四处一致性、测试与反证）。
- [ ] `APP_VERSION` → `1.23.77`；`python release_check.py --sync-iss` 同步两个 `.iss`（README 徽章 WARN 则同步）。
- [ ] `AGENTS.md`：§5.7「24 个测试模式」→ 25、登记 `test/test_csg_test_ext_0009.py`；§10 追加 1.23.77 摘要。
- [ ] `README.md`：第 21 行 / 第 394 行模式数 24 → 25。
- [ ] `python release_check.py --with-gui` → **FAIL=0**（经 pwsh）。
- [ ] **审查点 F**：release_check FAIL=0、`.iss` 与 `APP_VERSION` 一致、文档齐。

## 审查点汇总

| 审查点 | 时机 | 判据 |
|---|---|---|
| A | 阶段 1 后 | 解析出扩展名 + `报文聚合数目` 行；未登记 ID 不回归 |
| B | 阶段 2 后 | 组帧逐字节正确 + 越界报错 + 模式数 25 |
| C | 阶段 3 后 | 反解 key/参数一致且 `unmapped` 为空 |
| D | 阶段 4 后 | 三处模式数量文案与真值同源 |
| E | 阶段 5 后 | 新测试全绿 + 3 条反证变红 + 既有套件全绿 |
| F | 提交前 | release_check FAIL=0、`.iss`/README 同步、文档齐 |

## 回滚点

1. 阶段 1~3 任一失败 → `git checkout csg_new_gen_cmd_payloads.py csg_new_gen_frame_gen.py csg_frame_reverse.py`
   （纯新增分支，无持久化影响）。
2. 阶段 5 失败 → 删除 `test/test_csg_test_ext_0009.py` + 从 `release_check.py:CORE_TESTS` 移除该行。
3. 无配置/数据格式变更 ⇒ 回滚不需要清理任何运行时数据。
