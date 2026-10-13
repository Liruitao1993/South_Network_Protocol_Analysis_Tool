# 证据固化：协议9 2.0 测试扩展 0x0009（报文聚合传输测试模式）

> 本文件是本次实现的**事实基线**。后续实现不得与本文件冲突；若实测推翻某条，先改本文件再改代码。

## 1. 需求文档与原文

- 文档：`南网新一代20260226校对/宽带双模通信模块（通感一体物联版）相关测试命令定义_260922.docx`
  （2026-09-22 版；本仓无对应 `.md`，本次以 `read` 提取的正文为依据）
- 1.1 测试帧 ID 表（`测试ID`）：`0x00 进入回环测试模式` / `0x01 进入透明转发模式` /
  `0x02 频段切换命令` / `0x03 1.0测试` / `0x04 2.0测试` / `0x05~0xFF 保留`
- 1.4「PLC2.0测试（信息元素ID=0x04）」按小节顺序编号，**小节号 ↔ 扩展ID**：
  1.4.1 `0x0001` Bitloading测试模式｜1.4.2 `0x0002` Bitloading表下发｜1.4.3 `0x0003` 空间映射测试模式｜
  1.4.4 `0x0004` OFDMA测试模式｜1.4.5 `0x0005` OFMDA多用户下发（文档笔误）｜1.4.6 `0x0006` MAC层OFDMA配置｜
  1.4.7 `0x0007` 非组网场景TEI配置｜1.4.8 `0x0008` 报文Bitloading收发开关｜**1.4.9 `0x0009` 报文聚合传输测试模式**
- **1.4.9 原文（本次新增项）**：
  > 进行数据链路层报文聚合传输测试时，为测试报文聚合支持能力，扩展此报文聚合控制命令，
  > 要求 STA 和 CCO 进行报文聚合，命令的扩展内容如下：

  | 域 | 字节号 | 比特位 | 域大小(比特) | 含义 |
  |---|---|---|---|---|
  | 报文聚合数目 | 3 | 0-7 | 8 | 要求聚合发送的MAC帧个数 |
- 第 2 章「**原有**测试帧」= 表61 扩展命令格式 + `测试模式/配置操作` 取值 1~13
  （值 9 = 「进入 RF 物理层回传测试模式」）。文档自身标为**原有**，且代码 `_LEGACY_TEST_MODE_MAP` /
  `LEGACY_TEST_MODE_MAP` 已覆盖 1~13（+ 15），**本次不涉及**。

## 2. 缺口定位（代码事实）

| 位置 | 现状 |
|---|---|
| `csg_new_gen_cmd_payloads._TEST_EXT_ID_MAP` | `0x0001~0x0008`，**无 0x0009** |
| `csg_new_gen_cmd_payloads._parse_test_ext_payload` 分派表 | `0x0001~0x0008`，**无 0x0009**（落 `未识别扩展ID` 兜底） |
| `csg_new_gen_frame_gen.TEST_EXT_ID_MAP` | `0x0001~0x0008` |
| `csg_new_gen_frame_gen._EXT_BUILDERS` | `0x0001~0x0008` |
| `csg_new_gen_frame_gen.test_modes()` | A 新测试ID 3 项 + B 2.0 扩展 8 项 + C 表61 13 项 = **24** 项 |
| `csg_frame_reverse._fill_ext` | 分支止于 `0x0008`（0x0009 会命中「无对应模式」当参数无法回填时） |
| Web（`reflex_web/`） | **无**任何扩展ID 副本（全仓 grep `Bitloading` 只命中上述三处 + 测试）⇒ 无需同步 |

## 3. 字节口径（关键，决定 `报文聚合数目` 取哪个下标）

- 2.0 测试的数据区结构（解析侧 `_parse_cmd_test_frame`）：`协商版本号(1) | 文件长度(1) | 扩展ID(2,LE) | 扩展数据`。
- 各扩展 ID 的文档表用「字节号 3/4/5…」编号，而**扩展数据**从文档字节 3 开始：
  `csg_new_gen_cmd_payloads._parse_test_ext_0005` 的 docstring 明确写了
  `数据域结构（data[x] = 文档字节 x+3）`；`_parse_test_ext_0007`（TEI 占字节3 bits0-7 + 字节4 bits0-3）、
  `_parse_test_ext_0008`（开关在字节3 bit0）均按此实现。
- ⇒ **`报文聚合数目` = 扩展数据第 0 字节（8bit 整字节）**，即 `ext_data[0]`。

## 4. 既有实现锚点（照抄风格即可，勿另立第二套约定）

- 解析：`_parse_test_ext_0008`（单字节位域 + `_remaining`）、`_f(table, 名称, 原始值, 解析值, 说明, 起, 止)`、
  `_f(...,"❌ 解析失败", ...)` 表示数据不足。
- 组帧：`build_ext_0008`（`pack_bits` 单字节）、`_clip_count(value, name, max)` 做范围校验并抛 `FrameBuildError`、
  `_EXT_BUILDERS` 注册、`test_modes()` 里 `TestMode(key, "B 2.0测试扩展", TEST_EXT_ID_MAP[0xNNNN], 0x04, 0xNNNN, fields=(ModeField(...),))`。
- 仿照回填：`csg_frame_reverse._fill_ext` 的 `elif ext_id == 0x0008 and ext_data: params["enable"] = ext_data[0] & 0x01`。
- 摘要：`batch_core.extract_test_mode_content` 在无 `测试模式/配置操作` 时回退到
  `扩展ID:<名称>`（名称取 `扩展ID` 行的 comment 槽）⇒ 只要登记进 `_TEST_EXT_ID_MAP` 就会自动变成
  `扩展ID:报文聚合传输测试模式`。

## 5. 受影响的既有测试（已确认不会因新增模式而变红）

- `test/test_csg_frame_reverse.py`：遍历 `fg.test_modes()` 做全量反解，断言为 `checked >= 20` 与
  逐模式「key + 参数一致」⇒ 新模式必须能反解（否则变红）。
- `test/test_csg_frame_gen_gui.py::test_all_test_modes_build_linked_frames`：遍历 `mode_combo` 全部模式，
  断言每个模式都能组出带链路层且 FCCS/CRC-32 通过的 SOF 帧，数量断言是 `total >= 24`。
- `test/test_csg_summary.py`：仅覆盖既有帧型（不受影响）。

## 6. 仓库里已过期的模式数量文案（顺带核实，非本次功能）

- `csg_test_frame_gen_widget.py`：docstring 第 5 行「界面不硬编码 **26** 个模式」、第 189 行 `_PAYLOAD_SOURCE_OPTIONS`
  标签「复用现有 **24** 个模式」、第 959 行 tooltip「复用应用层 **26** 个测试模式」——三个数字互不一致，
  且都不等于真实值（24 → 本次 +1 = 25）。
- `AGENTS.md` §5.7 / §10、`README.md`（第 21、394 行）、`main_gui.py:CHANGELOG` 1.23.64/65 条目均写「24 个测试模式」。
