# 协议9 新增 2.0 测试扩展 0x0009（报文聚合传输测试模式）

## Goal

支持《宽带双模通信模块（通感一体物联版）相关测试命令定义_260922》新增的 2.0 测试扩展
**扩展ID = 0x0009「报文聚合传输测试模式」**（数据区 1 字节 = `报文聚合数目`，8bit），
并让它在**解析 / 组帧 / 仿照报文回填 / 批量摘要**四处与既有扩展 `0x0001~0x0008` 完全同构。

用户口径已确认（本轮问答）：**「测试模式9」= 文档 1.4.9 = 扩展ID 0x0009**。
文档第 2 章「原有测试帧」（表61 模式 1~13，含值 9 = RF物理层回传测试模式）代码已支持，**不在本次范围**。

## 需求事实

- 文档 1.4 节逐项 vs 代码：`0x0001~0x0008` 已支持；**`0x0009` 三处表全部缺失**
  （`_TEST_EXT_ID_MAP`、`_parse_test_ext_payload` 分派、`_EXT_BUILDERS`）。
- 文档 0x0009 表：`报文聚合数目 | 字节3 | 位0-7 | 8bit | 要求聚合发送的MAC帧个数`。
- 字节口径：既有实现的 `data[x] = 文档字节 x+3`（见 `_parse_test_ext_0005` docstring 与 0x0007/0x0008 代码）
  ⇒ `报文聚合数目 = ext_data[0]`（整字节）。
- 全仓 grep 确认 `reflex_web/` **无**扩展ID 副本 ⇒ Web 端无同步工作（解析链路共用同一解析器）。

## Requirements

### R1 解析（`csg_new_gen_cmd_payloads.py`）

- R1.1 `_TEST_EXT_ID_MAP` 追加 `0x0009: "报文聚合传输测试模式"`。
- R1.2 新增 `_parse_test_ext_0009(data, base_offset)`：输出
  `报文聚合数目`（原始值 `0xNN`、解析值十进制、说明含「要求聚合发送的MAC帧个数」），
  其后字节走 `_remaining`；`len(data) < 1` 时按既有风格输出 `❌ 解析失败` 行（不抛异常、不返回空表，AGENTS §8 陷阱 23）。
- R1.3 `_parse_test_ext_payload` 分派表登记 `0x0009`；未登记值仍走「未识别扩展ID」兜底（不得改动兜底行为）。
- R1.4 字段名必须含「报文聚合数目」且不得与既有字段名冲突（批量摘要按字段名匹配）。

### R2 组帧（`csg_new_gen_frame_gen.py`）

- R2.1 `TEST_EXT_ID_MAP` 追加 `0x0009`（与 R1.1 同值同文，两份表本就成对维护）。
- R2.2 新增 `build_ext_0009(*, agg_count: int = 1) -> bytes`：1 字节；`_clip_count(agg_count, "报文聚合数目", 0xFF)`；
  默认值 `1`（文档未规定默认；0 无意义，1 = 聚合 1 个 MAC 帧）。
- R2.3 `_EXT_BUILDERS` 登记 `0x0009`（`build_test_pdu(0x04, ext_id=0x0009, ...)` 即可用）。
- R2.4 `test_modes()` 追加 `TestMode("ext_agg", "B 2.0测试扩展", TEST_EXT_ID_MAP[0x0009], 0x04, 0x0009, fields=(ModeField("agg_count", "报文聚合数目", "int", 1),))`
  —— 组帧页模式下拉、模式参数表单由它自动生成（界面不硬编码）。
- R2.5 越界 / 非整数 → `FrameBuildError`（复用 `_clip_count` 语义），不得静默截断。

### R3 仿照报文回填（`csg_frame_reverse.py`）

- R3.1 `_fill_ext` 增加 `elif ext_id == 0x0009 and ext_data: params["agg_count"] = ext_data[0]`。
- R3.2 反解 `key` 必须为 `ext_agg`、参数 `agg_count` 必须与原值相等、`unmapped` 为空
  （保证「粘贴 0x0009 的 2.0 测试帧 → 回填 → 原样重建」成立）。

### R4 批量摘要（经 R1.1 自动生效，需断言）

- R4.1 0x0009 测试帧摘要回退段由 `保留扩展ID(0x0009)` 变为 `扩展ID:报文聚合传输测试模式`。
- R4.2 非测试帧与非 2.0 测试帧的摘要**逐字符不变**（`export_...`/`extract_test_mode_content` 的 gate 不受影响）。

### R5 一致性与不回归

- R5.1 既有 24 个测试模式（A 3 + B 8 + C 13）的解析 / 组帧 / 反解输出**逐行逐字节不变**；模式数变为 **25**。
- R5.2 桌面与 Web 共用同一解析器；**不在 Web 侧新增任何副本**。
- R5.3 未登记的扩展 ID（如 `0x000A`）行为不变（仍 `保留扩展ID(0x000A)` + 未识别数据行）。
- R5.4 顺带修正 3 处**过期且互不一致**的模式数量文案（`csg_test_frame_gen_widget.py` 的 26 / 24 / 26），
  改为从 `fg.test_modes()` 取真值（单一来源，防再次漂移）。

### R6 测试

- R6.1 新增 `test/test_csg_test_ext_0009.py`（文件头 `import _path_setup  # noqa: E402,F401`，AGENTS §7），
  覆盖：解析 goldens（0x00/0x01/0x05/0xFF 边界 + 数据不足 + 未登记扩展ID 护栏）、
  组帧逐字节（`0x04/0x00/数据区长度 LE/协商版本号/文件长度/扩展ID LE/1 字节数据域`）与越界报错、
  **build → 解析闭环**、**应用层帧 → `reverse_frame` 回填闭环**、摘要片段、`test_modes()` 含 `ext_agg`。
- R6.2 登记进 `release_check.py:CORE_TESTS`（新增项）。
- R6.3 既有套件回归：`test_csg_new_gen.py`、`test_csg_summary.py`、`test_csg_frame_reverse.py`、
  `test_csg_frame_gen_gui.py`、`test_csg_link_frame_gen.py`、`test_csg_frame_templates.py`、
  `test_csg_batch_*`、`test_collapsible_section.py` 全绿（后两项为 GUI_TESTS）。
- R6.4 **变异反证**（跑完必须还原）：① 解析改读 `ext_data[1]`；② 组帧写 2 字节；③ 反解不填 `agg_count`
  —— 三条各自使 R6.1 的对应断言变红。

### R7 文档与版本

- R7.1 `main_gui.py:CHANGELOG` 头部新增条目；`APP_VERSION` `1.23.76 → 1.23.77`；
  `python release_check.py --sync-iss` 同步两个 `.iss`（README 徽章若 WARN 则同步）。
- R7.2 `AGENTS.md`：§5.7 组帧段落「24 个测试模式」→ 25 且登记本测试文件；§10 追加 1.23.77 摘要；
  `README.md` 第 21 / 394 行的模式数同步。
- R7.3 `python release_check.py --with-gui` → **FAIL=0**（经 pwsh，见 AGENTS §8 陷阱 62）。

## Acceptance Criteria

- [ ] AC1 协议9 下解析 2.0 测试帧（测试ID=0x04、扩展ID=0x0009）：
      `测试ID` 行 = 2.0测试、`扩展ID` 行说明 = 报文聚合传输测试模式、新增 `报文聚合数目` 行（解析值 = 十进制、原始值 `0xNN`）。
- [ ] AC2 `报文聚合数目 = 0x00 / 0xFF` 边界正确；数据区不足（`data_len=0`）给 `❌ 解析失败` 且不抛异常。
- [ ] AC3 未登记扩展ID（`0x000A`）仍输出 `保留扩展ID(0x000A)` + 未识别数据行（不回归）。
- [ ] AC4 组帧：`build_test_pdu(0x04, ext_id=0x0009, agg_count=N)` 逐字节正确（含数据区长度 LE = 5，扩展数据 1 字节）；
      `agg_count` 越界（256 / -1 / 非整数）抛 `FrameBuildError`。
- [ ] AC5 闭环：组帧输出 → `CSGNewGenParser().parse_to_table(..., parse_level="auto" 或 "app")` → 断言的字段与原参数一致；
      组帧页 `mode_combo` 出现 `B 2.0测试扩展 · 报文聚合传输测试模式`（`test_modes()` 25 项）。
- [ ] AC6 仿照回填：0x0009 应用层帧 → `reverse_frame` 的 `state["mode"]["key"] == "ext_agg"`、
      `params["agg_count"]` 与原值一致、`unmapped == []`；用回填参数重建与原文逐字节相同。
- [ ] AC7 批量摘要：该帧摘要含 `扩展ID:报文聚合传输测试模式`；既有 24 个模式的摘要与解析输出不变
      （`test_csg_summary.py`、`test_csg_new_gen.py`、`test_csg_frame_reverse.py`、`test_csg_frame_gen_gui.py` 全绿）。
- [ ] AC8 `python test/test_csg_test_ext_0009.py` 全绿；3 条变异反证实测变红后还原。
- [ ] AC9 `python release_check.py --with-gui` → FAIL=0；`.iss` / README 徽章与 `APP_VERSION` 一致。
- [ ] AC10 文档同步：CHANGELOG / AGENTS（§5.7、§10）/ README 模式数与新增测试文件已更新。

## Scope 边界（明确不做）

- **不**新增其它扩展 ID（`0x000A~0xFFFF` 保持「保留」语义）。
- **不**改 2.0 测试的数据区外层结构（协商版本号 / 文件长度 / 扩展ID）、不改 `0x0005` 的 FC/eFC 既有建模。
- **不**动第 2 章表61 模式 1~13（本次属「原有测试帧」，代码已覆盖）。
- **不**新建 Web 侧副本；**不**改 `reflex_web/` 任何文件。
- **不**改批量提取策略、组帧页布局、模板存档格式（本次改动只让新模式走既有通路）。

## 存疑 / 实现中确认

- D1 `报文聚合数目` 的合法取值范围：文档只给 8bit（0~255），未给业务下限。实现按 8bit 全量接受，
  默认组帧值取 1（= 聚合 1 个 MAC 帧，等价于不聚合），不额外加业务校验（避免臆造规范）。
- D2 `_fill_ext` 的 0x0009 分支是否需处理「数据域多于 1 字节」（文档定义为固定 1 字节）：
  多出的字节保持「忽略但可被重建」的既有语义（`file_len` 与 `ext_data` 长度不符时会进 `unmapped`，与其它模式同口径）。
