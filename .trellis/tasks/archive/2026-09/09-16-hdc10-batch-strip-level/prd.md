# HDC 1.0（协议11）批量解析前缀剥离误用协议10解析级别

## Goal

现场用协议 11（HDC 1.0 双模互联互通）的**批量解析**处理日志行时，输入被判为空、弹「预处理后未保留有效报文内容！」而完全无法解析。根因是前缀剥离函数读错了**解析级别来源**（读协议10 的 `_gw_parse_level`，无视协议11 的 `_hdc10_parse_level`），并在 app 级别下把 HDC 1.0 的**升级业务帧（端口 0x12）**当成非应用层帧丢弃。本任务修复级别来源，并按文档把 app 级别判据放宽到 HDC 1.0 / 国网新一代实际定义的端口集合，桌面与 Web 两端同步。

## Confirmed Facts（代码与实测证据）

### 复现（本轮已实测）

样本（用户现场日志行，`Line NNNN:` 为搜索结果行号）：

```
    Line 16068: 260916-112229-213: B1D[3] mrd:ar[24]:12300000010500003F30AE7B78009001972306005ECCEFB1
    ...
    Line 34125: 260916-115335-299: B1D[3] mrd:ar[24]:12300000010500003F30AE7B59009001972306005ECCEFB1
```

offscreen 实测 `_strip_gw_new_gen_prefix`（`main_gui.py:4764`）：

| `_gw_parse_level`（协议10 值） | `_hdc10_parse_level`（协议11 显示值） | strip 输出 |
| --- | --- | --- |
| `auto` | `auto` | 24 字节 hex（正常，批量解析 20 帧全「成功」） |
| `app` | `auto` | **空字符串** → `_prepare_batch_input` 弹「预处理后未保留有效报文内容！」 |

即：协议11 界面显示「自动识别」，实际却按协议10 残留的 `app` 规则过滤。

### 代码证据

- 级别属性相互独立、控件共用：
  - `main_gui.py:1346` / `main_gui.py:1348` — `_gw_parse_level`（协议10）与 `_hdc10_parse_level`（协议11）分别初始化
  - `main_gui.py:3409-3416` — `_on_gw_parse_level_changed` 按 `current_protocol` 写**不同**属性
  - `main_gui.py:3326-3332` — 切换协议时把对应属性的值回填到**同一个** `gw_parse_level_combo`
- **缺陷点**：`main_gui.py:4781` — `parse_level = getattr(self, "_gw_parse_level", "auto")`，协议11 也读协议10 的值
- **缺陷点**：`main_gui.py:4853-4863` — app 级别只认端口 `11`，`12`（升级业务）/`1A`（鉴权安全）帧被丢弃
- 调用点：`main_gui.py:7383`（`_prepare_batch_input` 首次剥离）与 `main_gui.py:7410`（清洗后重复剥离），两者均不传级别
- 正确范式参照：`main_gui.py:4630-4636` — `_current_parse_params` 已按 `spec.parse_level_family` 正确分派（`hdc10 → _hdc10_parse_level`）
- Web 侧级别来源**正确**（`reflex_web/reflex_web/reflex_web.py:874-878` 按协议分派），但剥离函数 app 判据同样只认 `11`：`reflex_web/reflex_web/web_utils.py:357`
- 协议9 的同名逻辑（`main_gui.py:4886` 定义 / `4972` app 分支、`web_utils.py:258/306`）**不在本任务范围**

### 文档证据（app 判据依据）

- `国网新一代协议/HDC-国网双模协议/双模通信互联互通技术规范 第4-3部分：应用层通信协议.md:161` —
  「报文端口号是 8 比特的字段……**升级业务取值为 0x12，其他业务取值为 0x11**」
- 同上文档报文 ID 表（第 172 行附近的表格）：`0x0030~0x0036` 升级系列报文端口号均为 `0x12`
- 解析器端口表（现行实现，作为代码侧权威）：`hdc10_parser.py:136-140` `APP_PORTS = {0x11, 0x12, 0x1A}`；`gw_new_gen_parser.py:95-99` `PORT_NAMES = {0x11 抄表业务, 0x12 升级业务, 0x1A 鉴权安全}`

### 用户现场结论（本轮问答）

- 现象：弹「预处理后未保留有效报文内容！……」，摘要表 0 行
- 运行方式：打包 EXE（`dist/南网协议解析工具_v1.23.16_20260916142155.exe`）
- 输入：直接粘贴搜索结果行（非整文件、非预处理命令）

## Requirements

### R1 级别来源修复（核心）

- 桌面 `MainWindow._strip_gw_new_gen_prefix` 的解析级别必须与**同一帧真正用于解析的级别一致**，来源唯一为 `_current_parse_params()` 的口径（协议11 → `_hdc10_parse_level`；协议10 → `_gw_parse_level`）。
- 协议10 的残留级别**不得**再影响协议11 的批量解析；反之亦然。
- 非 app 级别（`auto`/`fc_pb`/`fc_only`/`mac_only`/`pb_only`/`fc_mac`）行为不变。

### R2 app 级别端口判据按文档放宽

- app 级别的帧起始判据由「只认 `11`」放宽到「HDC 1.0 / 国网新一代应用层端口集合」：`0x11`（其他业务）、`0x12`（升级业务）、`0x1A`（鉴权安全）。
- 端口集合**不新增第三份硬编码**：取值与解析器端口表同源（`hdc10_parser.APP_PORTS` / `gw_new_gen_parser.PORT_NAMES`）。
- 保持既有语义不变的部分：仍按**偶数字节位置**逐字节扫描、仍要求「命中位置起剩余 ≥ 8 hex 字符」、仍取命中位置起的剩余串作为应用层报文。

### R3 两端同步

- Web `reflex_web/reflex_web/web_utils.py::strip_gw_new_gen_prefix` 的 app 判据同步放宽（其级别分派已正确，不改）。
- 两端对同一输入 + 同一级别必须产出**逐字节相同**的结果（防漂移，需对拍断言）。

### R4 回归测试

- 新增 `test/test_hdc10_batch_strip_level.py`，覆盖：
  - 级别来源回归（协议11 下 `_gw_parse_level="app"` 不再影响；协议10 下 `_hdc10_parse_level` 不影响协议10）
  - app 判据（`11`/`12`/`1A` 起始帧保留；非应用层起始帧仍丢弃）
  - 端到端：用户 20 行样本在协议11 下批量解析 → 帧数 20、状态全「成功」（修复前为 0 帧 / 空内容警告）
  - 两端对拍（桌面 strip vs `web_utils.strip_gw_new_gen_prefix`）
  - 非 app 级别行为回归（输出与改动前一致）
- offscreen 测试必须沙箱 `main_gui.data_path` 与 `app_paths.data_path`（AGENTS §8 陷阱 42），不得改写真实 `config.json`。

### R5 文档同步

- `main_gui.py:CHANGELOG` 新增条目（含 `APP_VERSION` bump 到 1.23.17 与 `BUILD_DATE` 更新）。
- `AGENTS.md` §8 新增陷阱条目（级别来源分裂 + app 端口判据），§10 补版本摘要。

## Acceptance Criteria

1. 协议11 下，`_gw_parse_level` 残留为 `app`（或任何值）时，用户 20 行样本批量解析结果与 `_gw_parse_level="auto"` 时**完全一致**（20 帧、全「成功」、摘要含 `报文:0x0030`）。
2. 协议11 下把级别显式切为「应用层报文(app)」时，`12` 开头升级业务帧**保留**（不再被丢弃）。
3. 协议10 下 app 级别同样保留 `12`/`1A` 起始帧；协议10 的既有测试（`test/test_gw_batch_parse.py` 等）全绿。
4. 非 app 级别（`auto`/`fc_only`/`pb_only`…）的 strip 输出与改动前逐字符一致（由回归断言钉住）。
5. 桌面与 Web 的 strip 对同一输入同级别输出一致（对拍断言）。
6. `python test/test_hdc10_batch_strip_level.py` 全绿；`python test/test_gw_batch_parse.py`、`python test/test_hdc10.py`、`python test/test_web_parse_fixes.py` 全绿；`python release_check.py` 无 FAIL / WARN。
7. 变异反证：把端口集合改回只认 `11`，或把级别来源改回 `_gw_parse_level`，对应断言必须**变红**（证明测试有效）。

## Out of Scope

- 协议9 的 `_strip_csg_new_gen_frame_prefix` app 判据（南网新一代，端口定义与依据文档不同，另案）。
- `_prepare_batch_input` 里协议10/11 的**重复剥离调用**（清洗前后各一次）——保留现状，避免夹带行为变化。
- 协议11 的摘要/详情/组帧/监控等能力（另见 `09-12-*` 系列与 `09-15-web-*` 系列）。
- 重构 `_strip_gw_new_gen_prefix` 的引号状态机。

## Risks / Deferred

- app 级别判据放宽后，理论上可能出现「数据域中偶数字节等于 11/12/1A 而被误截断」——该风险在放宽前已存在（原逻辑同样扫描全串），本任务不新增风险维度；如需更严判据（如要求命中位置为帧首）属独立改进。
- 端口集合若未来新增（文档修订），需同步解析器端口表——已通过「集合取自解析器表」＋对拍测试把漂移面收敛到一处。
