# 执行计划：HDC 1.0 抄表报文 NameError 修复

> 轻量任务（一行修复 + 回归测试）。产物：`prd.md`（需求与验收）+ 本文件（执行清单）。

## 步骤 1 · 修复

- [ ] `hdc10_parser.py::_parse_meter_reading` 在 `hdr_bytes` 计算之后、使用之前补
      `proto_ver = b0 & 0x3F`（与同文件 `_parse_confirm:2222` 等 6 处同款写法）。
- [ ] 保持该函数其余逻辑与字段公式**一字不动**（避免夹带行为变更）。

**变异反证点**：本步骤的赋值删除后，步骤 2 的测试必须变红。

## 步骤 2 · 回归测试（新增 `test/test_hdc10_meter_reading.py`）

- [ ] 文件头 `import _path_setup  # noqa: E402,F401`（项目强制约定）
- [ ] **用户现场帧 golden**：88 字节终端主动并发抄表帧 × `parse_level="app"`，逐字段断言
      （端口 0x11 / 报文ID 0x0003 / 协议版本 1 / 报文头 8B / 配置字 0 / 规约类型 3=DL/T698.45 /
      转发数据长度 75 / 报文序号 17543 / DATA 起始 `68 49 00 43 …`）
- [ ] **DATA 长度自洽**：`转发数据长度` == 帧长 − 报文体偏移(4) − 报文头(8)（=75）
- [ ] **三类报文**：`0x001`/`0x002`/`0x003` 构造帧（复用现场帧改报文ID 字节 + 保持长度域）
      均可解析、均无 NameError、业务名分别为「终端主动抄表 / 路由主动抄表 / 终端主动并发抄表」
- [ ] **双级别**：同帧 `auto` 级别输出与修复前一致（把修复前实测输出固化为断言）
- [ ] **异常路径**：短帧（<8 字节）走「抄表报文(过短)」分支不崩
- [ ] **静态守卫**：`ruff check --select F821 hdc10_parser.py` 无命中（防同类复发）
- [ ] 登记 `release_check.py:CORE_TESTS`

## 步骤 3 · 验证

- [ ] `python test/test_hdc10_meter_reading.py` → PASS 全绿
- [ ] `python test/test_hdc10.py`、`test/test_hdc10_batch_strip_level.py`、`test/test_hdc10_real.py`
      （真实夹具 119 帧）、`test/test_gw_new_gen.py` → 无回归
- [ ] `python release_check.py` → FAIL=0 / WARN=0
- [ ] **变异反证**：临时删掉 `proto_ver = b0 & 0x3F` → 测试变红 → 还原 → 全绿
- [ ] 复核（`trellis-check` 子代理）：对照 prd 验收 1~7 取证 + 越界核查

## 步骤 4 · 文档与版本

- [ ] `main_gui.py`：`APP_VERSION` → **1.23.19**；`CHANGELOG` 顶部条目
      （现象 / 根因 / 触发四条 / 文档依据 / 测试与变异反证）
- [ ] `AGENTS.md`：§8 新增陷阱（HDC 1.0 抄表报文 NameError + 触发条件）；
      §10 最近版本摘要；§1/§2 版本陈述
- [ ] `python release_check.py --sync-iss`；`README.md` 徽章同步

## 步骤 5 · 提交与归档

- [ ] 提交信息：`fix(hdc10): 抄表报文解析补 proto_ver 赋值（app 级别 NameError）`
- [ ] `task.py archive .trellis/tasks/09-17-hdc10-meter-reading-fix`

## 风险与应对

| 风险 | 应对 |
| --- | --- |
| `proto_ver` 取值口径写错（应为 `b0 & 0x3F`，非 `b0`） | 与同文件 6 处对齐 + 文档 §5.3.1.2「6 比特」+ 现场帧 b0=0x01 实测 |
| 顺手改了本函数其他公式引入回归 | 步骤 1 明令「其余一字不动」；`auto` 级别输出固化断言 |
| 只测现场帧，其他两个 msg_id 仍不可用 | 步骤 2 显式覆盖 0x001/0x002/0x003 |
| 同类缺陷还有别的（动态路径） | F821 静态已扫全仓（0 命中其余）；动态排查列 Out of Scope |
| 工作区已有的 `main_gui.py`/`web_utils.py` 格式噪声混入提交 | 提交时**逐个 add** 本次改动文件，不用 `git add -A` |

## 执行结果

### 落地改动

| 文件 | 改动 |
| --- | --- |
| `hdc10_parser.py` | `_parse_meter_reading` 补 `proto_ver = b0 & 0x3F`（+4 行注释说明）；**其余字段公式一字未动** |
| `test/test_hdc10_meter_reading.py` | 新增，**13/13 通过** |
| `release_check.py` | `CORE_TESTS` 登记新套件 |
| `main_gui.py` | `APP_VERSION` → 1.23.19、`BUILD_DATE` → 2026-09-17、CHANGELOG 顶部条目 |
| `AGENTS.md` | §1/§2 版本陈述、§8 陷阱 45（含误报判定）、§10 摘要 |
| `README.md` / `两个 .iss` | 版本对齐（`--sync-iss` 自动回写） |

### 验证结果

- **新测试**：13/13 通过（现场帧 golden 逐字段 / 三类报文 / auto 基线 / DATA 自洽 / 短帧边界 / 行结构 / F821）
- **回归**：`test_hdc10` 20/20、`test_hdc10_batch_strip_level` 29、`test_gw_new_gen` 44、`test_gw_app_summary_detail` 42 全绿
- **变异反证**：内存变异（删掉 `proto_ver` 赋值，不动原文件）→ 精确复现 `NameError: name 'proto_ver' is not defined` ✓
- **现场帧修复后实测**：报文ID `0x0003` / 协议版本 `1` / 报文头 `2×4B=8B` / 配置字 `0` / 规约类型 `3`=DL/T698.45 / 转发数据长度 `75` / 报文序号 `17543` / DATA 起于偏移 12
- **静态**：`ruff check --select F821` 全仓 0 命中
- `release_check.py --sync-iss`：PASS=11 / FAIL=0 / WARN=0

### 本任务触发的既有告警盘点（均不修，已存档 AGENTS §8 陷阱 45）

| 位置 | 类型 | 判定证据 |
| --- | --- | --- |
| `main_gui.py` 88 条 | PySide6 枚举访问 / `QLayout.takeAt` 覆盖签名 / `QWidget` 动态属性等 | `git diff main_gui.py \| grep -c "NoEditTriggers\|SelectRows\|ScrollBarAlwaysOff\|def takeAt\|update_stats("` = **0** |
| `hdc10_parser.py` L1516 | `bcsha_phases` possibly unbound | 使用点所在 `if ln > 20` **蕴含**赋值处的 `if ln >= 7` → 不可达 |
| `hdc10_parser.py` L1655 | `msdu_len` 类型收窄 `int \| None` | `extra_bytes` 非空仅来自 `if msdu_len is not None` 分支（`elif` 分支保持 `b''`）→ `if extra_bytes:` 为假时不执行 |
| `release_check.py` L25/26 | `sys.stdout.reconfigure` 不在 `TextIO` 协议 | Python 3.7+ 真实 API，运行正常；类型标注局限 |
