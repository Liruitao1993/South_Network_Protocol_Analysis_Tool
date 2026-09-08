# DLT645 通用组帧器与 GUI/Web 集成

## Goal

为协议 6（DL/T 645-2007）补齐组帧能力：新建 645 帧生成器与字段 schema，让 GUI「协议组帧」tab 与 Reflex Web 组帧页在协议 6 下可用，产出的帧必须能被本工具自己的解析器与校验器正确回读。

用户价值：目前协议 6 只能解析不能造帧，用户想抄表/校时/写参数时必须手写 hex 并手算 +0x33 加扰与 CS，极易出错；本任务让协议 6 与协议 0/7/8 一样具备「选命令 → 填字段 → 一键生成 → 直接发送」的闭环。

## Background（已确认事实，带 file:line 锚点）

帧规则以 `DLT645-2007.md` + `dlt645_parser.py` + `test/test_dlt645_lme.py` 三方交叉验证，详见 `research/protocol-rules.md`：

- 帧结构：`68H` + 地址域 6B（**低字节在前**）+ `68H` + 控制码 C + 数据长度 L + 数据域 DATA + CS + `16H`
- 数据域 **每字节 +0x33 加扰**（DI 与数据 alike）
- CS = `sum(帧起始符 … 数据域最后一个字节) & 0xFF`，**含两个 68H 与地址域**
- DI 4 字节 little-endian 传输（`04FFAAF9` → 线上 `F9 AA FF 04`）
- 广播地址 `999999999999H`
- 12 个功能码（`dlt645_data_codec.py:97-110` `FUNC_NAMES`）：08H 广播校时 / 11H 读数据 / 12H 读后续 / 13H 读地址 / 14H 写数据 / 15H 写地址 / 16H 冻结 / 17H 改速率 / 18H 改密码 / 19H 最大需量清零 / 1AH 电表清零 / 1BH 事件清零

现状缺口：

- 协议 6 无任何 encode 能力——`dlt645_data_codec.py` / `dlt645_parser.py` 逐函数核对确认 **100% decode 方向**（`research/parser-codec-encode-gaps.md`）
- 组帧 tab 对协议 6 隐藏：`main_gui.py:3052` `show_frame_gen = index in (0, 7, 8)`；`frame_gen_widget.py:3765` `set_protocol_mode` 只接受 `south`/`gdw`/`dlt698`；Web `reflex_web.py:2514` 落到 `raise ValueError(f"协议 {p} 暂不支持组帧")`
- 预设命令 tab 同样只 `(0, 7, 8)`（`main_gui.py:3068`），无 `DLT645_command.json`
- 三套既有范本的 `bcd` 字段类型**不是真 BCD 编码**，而是 `bytes.fromhex()`（把输入当已编码 hex，`send_frame_lib.py:471-482`、`gdw_send_frame_lib.py:271-282`）；645 必须新写「十进制数值 → BCD + 小数点位 + 低字节在前」类型，这是与范本的最大差异（`research/existing-generator-patterns.md`）
- `dlt645_di.json` 结构为 `{description, version:"1.2.0", di_map:{...}}`，**1099 条** DI，每条 4 键（`name`/`unit`/`data_type`/`length`），**无读写属性、无分类**（`research/di-schema-source.md`）
- **关键正面发现**：1099 条 DI 只用到 **17 种 `data_type` 掩码**（`XXXXXX.XX` 740 / `XXXXXX.XXXX` 130 / `XXX.X` 129 / `XX.XXXX,MDHM` 32 / `XX.XXXX` 22 / `X.XXX` 8 / 空 8 / `XXX.XXX` 7 / `BS32` 7 / `XXXXXX` 6 / `XX` 2 / `BS96` 2 / `XX...XX` 2 / `YYYYMMDD` 1 等），掩码本身已编码「数字位数 + 小数点位置」——DI 驱动字段模板只需实现 ~17 个掩码处理器即可覆盖全量 DI，无需手写 1099 份 schema
- `length` 分布：4B 748 条 / 2B 137 / 5B 130 / 3B 36 / 8B 33 / 0B 8 / 1B 2 / 12B 2；两个 LME 自定义 DI（`04FFAAF9` len=251、`FF00DD01` len=255）的 `data_type` 为 `XX...XX`（即裸字节）
- **DI 表是手写硬编码的**：`generate_dlt645_di.py` 直接在 Python 里逐条写 `di_map[di_key] = {...}`，并非从 PDF/文档抽取；`DLT645-2007.md` 全文无「读写/只读/可写/R\/W」任何字样（已检索确认）——补全读写属性等于手改 1099 条硬编码

可直接复用的资产：

- **黄金参照实现**：`test/test_dlt645_lme.py:31` `build_frame(decoded_data, ctrl, addr)`——+0x33、CS 范围、地址序、68/68/16 包裹全部正确，新生成器输出须与之逐字节一致
- `archive_widget.py:849` `_build_dlt645_read_energy_frame()`——标准正确的硬编码 645 构帧，可作为交叉验证样本
- LME `FF00DD01` 的 TLV 头拼装可逆：`tlv_header` 公式（`test_dlt645_lme.py:60-61`）是解码逻辑（`lme_info_entry_parser.py:578-583`）的精确逆运算，已有回读测试
- `dlt645_di_lookup.py` 提供 DI → 名称/单位/数据格式查询（含 `dlt645_di_custom.json` 合并优先级）

## Requirements

- **R1** 新建 645 帧生成器模块，负责地址域字节序、控制码组装、数据域 +0x33、L 与 CS 自动计算、`68…16` 包裹；不得由 GUI 层手写这些逻辑
- **R2** 新建 645 字段 schema，命令下拉分「请求 / 应答」两组（见已决事项 OQ4），覆盖 R1 所需命令的字段定义（含真 BCD/小数点/ASCII/逆序等 645 特有编码类型）
- **R3** GUI「协议组帧」tab 在协议 6 下可见可用：命令选择、字段表单、实时预览、生成、串口发送、存为预设、加入测试方案，行为与协议 0/7/8 一致
- **R4** Reflex Web 组帧页支持协议 6（`_build_frame_bytes` 增加 p==6 分支），字段收集复用 `frame_gen_utils.collect_field_values` 契约
- **R5** 协议 6 预设命令库：新增独立预设 JSON 与 `PresetButtonWidget.set_protocol` 的 dlt645 支持，不得再出现「698 预设被误存进 GW_command.json」那类串档
- **R6** 生成的每一帧必须能被 `DLT645Parser.parse` 与 `DLT645Validator.verify` 判为合法，且字段回读值与输入一致（组帧→解析闭环）
- **R7** 数据域截断/非法输入（非 hex、长度越界、地址不足 6B）必须给出明确错误提示，不得抛未捕获异常
- **R8** 新增独立测试脚本，遵循项目既有约定：纯脚本 + `check()` 计数、`import _path_setup`、UTF-8 stdout 兜底，不用 pytest 装饰器

## Acceptance Criteria

- [x] **AC1** 协议 6 下「协议组帧」tab 可见；切到其他协议时按既有规则隐藏，切回协议 6 状态不残留（`main_gui.py:3052` 已改为 `index in (0, 6, 7, 8)`；`test/test_dlt645_frame_gen_gui.py` 第 8 节用真实 MainWindow 验证：协议6 tab 可见且模式=dlt645、协议1 隐藏、协议0/7/8 分别回到 south/gdw/dlt698）
- [x] **AC2** 生成「读数据 11H + DI=00010000（正向有功总电能）+ 地址 000000000000」的帧，与 `test/test_dlt645_lme.py:31` `build_frame` 的输出**逐字节一致**（`68 00×6 68 11 04 33 33 34 33 B2 16`）
- [x] **AC3** 生成「广播校时 08H + 广播地址 999999999999」的帧，数据域为 秒/分/时/日/月/**年** BCD 且逐字节 +0x33，回读解析显示的时间与输入一致（注：文档 §7.6 确认第 6 字节是**年**而非星期，已同步修正 `dlt645_parser.py` 与 `test_dlt645_lme.py` 的错误口径）
- [x] **AC4** 生成「写数据 14H」「修改密码 18H」「电表清零 1AH」「事件清零 1BH」「读写地址 13H/15H」各至少一帧，均通过 AC6 闭环
- [x] **AC5** 电能类字段输入十进制（如 `123456.78`）能正确编成 BCD + 小数点 + 低字节在前（线上 `78 56 34 12` 加扰后），而非把输入当 hex 直填
- [x] **AC6** 每种命令生成的帧送入 `DLT645Parser.parse` → `valid=True`、DI 与描述正确；送入 `DLT645Validator.verify` → `valid=True`；解析表格中的字段值与组帧输入逐项相符
- [x] **AC7** Web 端协议 6 组帧产出与 GUI 端**同输入同输出**（逐字节一致）（test_web_frame_gen_utils `test_dlt645_web`：读电能/写数据/LME 查询三组均与纯逻辑生成器逐字节一致，74 项全过）
- [x] **AC8** 协议 6 下可保存预设命令并在新会话中恢复、可直接发送到串口、可加入测试方案（`DLT645_command.json` 种子 5 条经 `PresetButtonManager.load_commands('dlt645')` 验证可加载；预设 tab 对协议6 可见；发送/加测试方案按钮为协议无关路径）
- [x] **AC9** 非法输入（奇数长度 hex、地址 >6B、BCD 字段含非数字）返回中文错误提示且不崩溃
- [x] **AC10** 既有协议 0/7/8 组帧无回归：`test_web_frame_gen_utils.py` 63 通过 0 失败、`test_gdw_fujian.py` 19 项全过、`test_dlt645_lme.py` 全部通过；改动文件 `python -m py_compile` exit=0
  - 注：`test_quick_parse_panel.py` **84 项断言全过**，但进程退出阶段报 `0xC0000409`（exit=-1073740791）。已做对照实验定性：① `-X importtime` 证实该测试运行中 `frame_gen_widget`/`dlt645_*` **一次都未被加载**（0 命中，组帧 tab 是惰加载）；② 将 `main_gui.py` **完全还原到 HEAD**（`git diff` 为空）后重跑，退出码仍为 -1073740791。故该崩溃为 **Qt offscreen 退出阶段的既有问题，与本任务无关**，待单独排查
- [x] **AC11** 应答方向：生成「读应答 91H + DI=00010000 + 值 123456.78」的帧，送入解析器 valid=True 且回读值为 `123456.78 kWh`；写应答 94H（仅 DI 无值）同样闭环
- [x] **AC12** 异常应答：ERR 以裸字节输入（不做位域下拉），生成帧送入解析器后表格能按 `ERR_BITS` 展开中文位语义（如 0x04 → 密码错/未授权）

## Out of Scope

- 虚拟表 tab（`main_gui.py:3070`，当前仅 index==8，本质是 698.45 从站模拟器）与档案管理 tab（`main_gui.py:3081`，当前 0/7）对协议 6 开放——前者等于重写一套 645 从站模拟器，与组帧无交集；待用户确认（OQ5）
- LME `FF00DD01` **设置请求 14H** 的结构化组帧（反向值编码器 + 语义映射反向下拉）——已切为后续独立任务（见已决事项 OQ3）
- LME `04FFAAF9` 应答帧的反向拼装：该接口无设置方向，应答含变长硬件段与**多项式未定义**的 CRC16，不可靠反造
- 协议 1~5（PLC RF / HDLC / DLMS 系列）与 9~11（新一代载波 / 国网新一代 / HDC 1.0）的组帧
- 既有 EB 645 生成器的口径修正——由兄弟任务 `09-07-eb-645-standard-fix` 承担

## 已决事项

- **OQ1 已决（用户 2026-09-07 确认）：命令组织采用混合式**——12 个功能码作为命令骨架；其中 11H 读数据 / 12H 读后续 / 14H 写数据的 DI 由 `dlt645_di.json`（1099 条）驱动下拉，选中 DI 后按 `data_type`/`length`/`unit` 自动推导字段表单（真 BCD/小数点/ASCII/逆序）；08H 校时 / 13H·15H 地址 / 16H 冻结 / 17H 速率 / 18H 改密码 / 19H·1AH·1BH 清零等无 DI 命令使用固定字段模板。理由：645 命令语义天然分「带 DI 的数据读写」与「不带 DI 的功能命令」两类，且 DI 表已带足够元数据可自动推导，无需手写 1099 份 schema
- **OQ2 已决（用户 2026-09-07 确认）：写数据 14H 不校验 DI 可写性，全放行**——任意 DI 均可组写帧；UI 展示选中 DI 的 `name`/`data_type`/`length`/`unit` 供人工判断；仅当用户填入的数据长度与 DI 声明 `length` 不符时给出**警告但不阻断**。理由：本工具是协议调试工具，不应替用户猜某块表支持写什么；写错时电表回异常应答，而 ERR 位域解码已在 `2d04c90` 完成，用户能直接看到「密码错/参数超范围」等明确原因，闭环成立。放弃「补全读写属性」（需手改 1099 条硬编码，且厂家表计可写集本就不一致）与「手工白名单」（必然不全，拦住本可写的 DI 体验更差）
- **OQ3 已决（用户 2026-09-07 确认）：LME 自定义接口本次只做查询请求 11H 的结构化模板**——`04FFAAF9`（无数据单元）与 `FF00DD01`（条目信息 1B=0 + M 1B + M×2B 请求头，M=0 表示读全量）用 `CATEGORY_NAMES` + `LME_INFO_ENTRIES` 做分类/条目二级下拉自动生成，**不需值编码**；设置请求 14H（需 6~10 个反向值编码器 + 语义映射反向下拉）切为后续独立任务。理由：查询侧零值编码成本，且与 9/3–9/4 刚完成的 LME 解析形成「造请求 → 收应答 → 解得开」闭环
- **OQ4 已决（用户 2026-09-07 确认）：请求与应答双向都做，但异常应答 ERR 只给裸字节输入框**——命令下拉分两组：请求（08H/11H/12H/13H/14H/15H/16H/17H/18H/19H/1AH/1BH）与应答（读应答 91H、写应答 94H、地址应答、异常应答）。关键依据：读应答 91H 数据域 = DI + 数据值，与写数据 14H **值编码完全同构**，~17 个掩码编码器写一次两边共用，边际成本低；且 `test_dlt645_lme.py` 大量用 `ctrl=0x91` 造应答帧作测试样本，协议 8 已有「虚拟表」从站模拟器，证明「造应答」在本工具有既定用途。ERR **不做位域下拉**（只裸字节），但解析回读仍按 `ERR_BITS` 展开中文（AC12）
- **广播校时第 6 字节 = 年（YY）**——**原结论已被文档推翻并修正**：`DLT645-2007.md` §7.6（L790-L804）明写「数据域：YYMMDDhhmmss（年.月.日.时.分.秒），L=06H」，帧格式表线序为 `ss mm hh DD MM YY`，**无星期字段**。此前「第 6 字节 = 星期」的结论是用 `dlt645_parser.py:198-200` + `test_dlt645_lme.py:300-307` 交叉验证得出的，但两者同错（实现错 + 测试跟着错），属自证循环。已修正解析器与测试断言
- **控制码 UI 命名**：按标准位名显示「传输方向 DIR（D7）」+「功能码（D3~D0）」，并附只读说明解释 D7 在请求/应答中语义相反，避免用户误填

## Open Questions（阻塞规划收敛）

- **OQ5** 虚拟表 / 档案 tab 是否随本次对协议 6 开放（默认不开，见 Out of Scope）

## Notes

- 本任务为复杂任务，`task.py start` 前必须补齐 `design.md` 与 `implement.md`，并在 `implement.jsonl` / `check.jsonl` 填入真实 spec 与 research 条目（seed `_example` 行不算）
- 研究结论全文见 `research/` 下 6 个文件：`protocol-rules.md`、`parser-codec-encode-gaps.md`、`di-schema-source.md`、`existing-generator-patterns.md`、`integration-points.md`、`lme-and-tests.md`
