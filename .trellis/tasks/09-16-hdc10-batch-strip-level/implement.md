# 实施计划：HDC 1.0（协议11）批量解析前缀剥离级别来源与 app 端口判据

> 执行顺序即 checklist 顺序；每步末尾给验证命令。**任何一步验证失败即停，不得带着红结果进入下一步。**

## 步骤 0 · 复现基线（先固化失败，再改代码）

- [ ] 用 offscreen 脚本复现「协议11 + `_gw_parse_level='app'` 残留 → strip 输出空」与「协议11 + auto → 20 帧全成功」两条路径，记录输出作为改前基线。
  ```bash
  # 复现方式（stdin 运行，不落临时文件）见本任务对话记录；
  # 关键断言：_gw_parse_level='app' 时 strip 返回 ''，'auto' 时返回 24 字节 hex
  ```
- [ ] 记录用户 20 行样本（含 `Line NNNN:` 前缀、前导 4 空格）到测试文件的常量里，供端到端用例使用。

**回滚点 0**：无代码改动，基线仅记录。

## 步骤 1 · 桌面：级别来源修复（缺陷 A）

- [ ] `main_gui.py:4764` 改签名为 `_strip_gw_new_gen_prefix(self, text: str, parse_level: Optional[str] = None) -> str`。
- [ ] `main_gui.py:4781` 改为：
  ```python
  if parse_level is None:
      # 与真正用于解析的级别同源：协议11 → _hdc10_parse_level；协议10 → _gw_parse_level
      # （_current_parse_params 已按 spec.parse_level_family 分派，是唯一分派点）
      parse_level = self._current_parse_params().get("parse_level") or "auto"
  ```
- [ ] 更新 docstring：说明级别来源、协议10/11 差异、为何不硬编码 `_gw_parse_level`，并引 AGENTS §8 陷阱编号（步骤 7 补写）。
- [ ] 调用点 `main_gui.py:7383` / `main_gui.py:7410` 保持不传参，但把注释从「app 级别时扫描 '11'」更正为「按当前协议级别定位帧起始（app 级别扫描应用层端口）」。
- [ ] 若该函数其它调用点被遗漏，用 `grep -n "_strip_gw_new_gen_prefix(" main_gui.py` 复核（预期仅 7383 / 7410 两处）。

**验证**：
```bash
python -c "import ast,sys; ast.parse(open('main_gui.py',encoding='utf-8').read())"
python test/test_gw_batch_parse.py
```
**回滚点 1**：`git checkout -- main_gui.py`

## 步骤 2 · 桌面：app 端口判据放宽（缺陷 B）

- [ ] 在 `main_gui.py` 模块级（`_strip_gw_new_gen_prefix` 附近）新增：

  ```python
  # HDC 1.0 / 国网新一代应用层端口号（hex 串），判定 app 级别的帧起始
  # 依据：《第4-3部分 应用层通信协议》§5.2.2「升级业务取值为 0x12，其他业务取值为 0x11」
  # 权威来源=解析器端口表（hdc10_parser.APP_PORTS / gw_new_gen_parser.PORT_NAMES），
  # 避免在这里出现第三份硬编码端口副本（曾因此漏掉 0x12 升级业务帧）。
  _GW_APP_PORT_PREFIXES_FALLBACK = ("11", "12", "1A")

  def _gw_app_port_prefixes(protocol_index: int) -> tuple:
      """应用层端口（hex 串）集合；取解析器端口表，import 失败时回落内置三元组。"""
      try:
          if protocol_index == 11:
              import hdc10_parser
              ports = hdc10_parser.APP_PORTS
          else:
              import gw_new_gen_parser
              ports = gw_new_gen_parser.PORT_NAMES
          return tuple(f"{p:02X}" for p in ports)
      except Exception:
          return _GW_APP_PORT_PREFIXES_FALLBACK
  ```

- [ ] `_strip_gw_new_gen_prefix` 入口按当前协议算一次集合：`app_prefixes = _gw_app_port_prefixes(getattr(self, "current_protocol", 10))`。
- [ ] app 分支 `main_gui.py:4853-4863` 的 `hex_clean[i:i+2] == "11"` 改为 `hex_clean[i:i+2] in app_prefixes`（其余语义不动：偶字节步进、剩余 ≥ 8、命中截断）。
- [ ] 顺带确认 `_strip_gw_new_gen_prefix` 的其它分支（引号状态机、普通行取最后冒号后）**一行不改**。

**验证**（改后行为：`12` 开头的升级业务帧在 app 级别下必须被保留）：
```bash
python -c "
import os,sys; os.environ['QT_QPA_PLATFORM']='offscreen'; sys.path.insert(0,'.')
from PySide6.QtWidgets import QApplication; app=QApplication([])
import main_gui; w=main_gui.MainWindow()
line='    Line 16068: 260916-112229-213: B1D[3] mrd:ar[24]:12300000010500003F30AE7B78009001972306005ECCEFB1'
out = w._strip_gw_new_gen_prefix(line, 'app')
assert out.endswith('5ECCEFB1'), out            # 12 开头升级业务帧被保留
assert len(out) // 2 == 24, len(out) // 2       # 整帧 24 字节，未被误截断
print('ok', out)"
```

**回滚点 2**：`git checkout -- main_gui.py`

## 步骤 3 · Web 端同步

- [ ] `reflex_web/reflex_web/web_utils.py:333` 改签名 `strip_gw_new_gen_prefix(text: str, parse_level: str = "auto", protocol_index: int = 10) -> str`。
- [ ] app 分支（`:353-364`）的 `== '11'` 改为集合成员判定，集合由与桌面同源的方式取得（模块内小函数 `_gw_app_port_prefixes(protocol_index)`，实现与桌面一致，含同样的兜底与注释）。
- [ ] 更新 docstring：端口依据 + 与桌面同源说明。
- [ ] `reflex_web/reflex_web/reflex_web.py:874-878` 两个调用点补 `protocol_index=10` / `protocol_index=11`（级别分派本身已正确，不改）。
- [ ] 不改 `strip_csg_new_gen_prefix`（协议9）。

**验证**：
```bash
python web/reflex_web --help 2>/dev/null;  # 无此命令则跳过
python -c "import ast; ast.parse(open('reflex_web/reflex_web/web_utils.py',encoding='utf-8').read()); ast.parse(open('reflex_web/reflex_web/reflex_web.py',encoding='utf-8').read())"
python test/test_web_parse_fixes.py
```

**回滚点 3**：`git checkout -- reflex_web/`

## 步骤 4 · 新增回归测试 `test/test_hdc10_batch_strip_level.py`

- [ ] 文件头：docstring → `import _path_setup  # noqa: E402,F401` → 业务 import（AGENTS §7 强制）。
- [ ] 沙箱：参照 `test/test_window_state.py::Sandbox`，同时 patch `main_gui.data_path` **与** `app_paths.data_path`（AGENTS §8 陷阱 42），保证 offscreen 关窗不写真实 `config.json`。
- [ ] 用例组（每条都打印/断言，风格与既有 offscreen 测试一致）：
  1. **纯函数矩阵**：`_strip_gw_new_gen_prefix(text, level)` 对 `auto`（原样保留）、`app`（`11`/`12`/`1A` 起始保留；`2000…` 之类非端口起始丢弃）、`pb_only`（原样）的输出。
  2. **级别来源**：Host 宿主（复用 `MainWindow` 未绑定方法 + 极简属性）分别构造 `current_protocol=11` 与 `10`，断言 `_gw_parse_level='app'` + `_hdc10_parse_level='auto'` 在协议11 下输出 == auto 输出（修复前为空）。
  3. **端口集合对拍**：`_gw_app_port_prefixes(11)` == `tuple(f"{p:02X}" for p in hdc10_parser.APP_PORTS)`；`(10)` 同理对齐 `gw_new_gen_parser.PORT_NAMES`。
  4. **两端对拍**：桌面 strip vs `web_utils.strip_gw_new_gen_prefix`，同输入 × `{auto, app}` × 协议 `{10, 11}` 输出逐字符相等。
  5. **端到端（核心验收）**：offscreen `MainWindow` → 协议11 → `batch_input` 灌入 20 行样本 → `parse_batch()` + `wait_batch(win)` → 断言帧数 20、状态全「成功」、类型含 `[11]`、摘要含 `报文:0x0030`；并断言此时 `win._gw_parse_level` 无关紧要（先置 `'app'` 再跑）。
  6. **协议10 回归**：同一 20 行样本在协议10 下 auto 仍可用（不受本次改动破坏）。
  7. **非 app 级别不变**：`auto/fc_only/pb_only` 输出与步骤 0 基线一致（可硬编码期望串）。
- [ ] 登记进 `release_check.py:CORE_TESTS`（与既有测试清单一致的做法）。

**验证**：
```bash
python test/test_hdc10_batch_strip_level.py
```

**回滚点 4**：删除该测试文件（不影响产品代码）。

## 步骤 5 · 变异反证（测试有效性自检）

- [ ] 临时把端口集合改回 `("11",)` → 断言 1/5 必须变红。
- [ ] 临时把级别来源改回 `getattr(self, "_gw_parse_level", "auto")` → 断言 2/5 必须变红。
- [ ] 两处都还原，重跑全绿（AGENTS §8 陷阱 38：不做变异反证的守卫测试可能恒真）。

**验证**：
```bash
python test/test_hdc10_batch_strip_level.py   # 变异时红、还原后绿
```

## 步骤 6 · 全量回归

- [ ] `python test/test_hdc10.py`
- [ ] `python test/test_gw_batch_parse.py`
- [ ] `python test/test_gw_parse_levels.py`
- [ ] `python test/test_gw_monitor_summary.py`
- [ ] `python test/test_web_parse_fixes.py`
- [ ] `python test/test_gui_batch_perf.py`（批量后台化契约，确认未破坏）
- [ ] `python release_check.py`（无 FAIL/WARN；如需同步 iss 版本号用 `--sync-iss`）

**Review gate（步骤 6 后）**：跑一遍 trellis-check 子代理复核（对照 prd 验收 1~7 逐条取证），通过后才进入文档收口。

## 步骤 7 · 文档与版本收口

- [ ] `main_gui.py:APP_VERSION` → `1.23.17`；`BUILD_DATE` → 打包当日日期。
- [ ] `main_gui.py:CHANGELOG` 头部新增 1.23.17 条目（现象/根因/修复/两端同步/测试）。
- [ ] `python release_check.py --sync-iss` 同步两个 `.iss` 的 `MyAppVersion`，再跑一次 `python release_check.py`。
- [ ] `README.md` 版本徽章（如有）随 release_check 提示同步。
- [ ] `AGENTS.md`：
  - §8 新增陷阱：**「协议10/11 共用解析级别控件但属性独立；批量前缀剥离必须走 `_current_parse_params` 取级别，app 级别端口判据取解析器端口表」**（编号顺延，含本任务的证据与文件行号）。
  - §10 变更日志补 1.23.17 摘要。
- [ ] 本任务 `implement.md` 勾选完成项；必要时补 `research/`（无需额外研究则跳过）。

**验证**：
```bash
python release_check.py
```

## 步骤 8 · 提交与收口

- [ ] `git add -A` → 提交信息遵循 `chinese-commit-conventions`（`fix(hdc10): 协议11 批量解析前缀剥离误用协议10 解析级别`）。
- [ ] `python ./.trellis/scripts/task.py archive .trellis/tasks/09-16-hdc10-batch-strip-level`。

## 风险与应对

| 风险 | 应对 |
| --- | --- |
| `_current_parse_params()` 在 strip 内被调用可能触发控件读取 | 该方法只读属性 + `protocol_registry` 查表，不建 parser；且 strip 只在主线程（`_prepare_batch_input`）调用，安全 |
| `hdc10_parser` / `gw_new_gen_parser` 惰性 import 失败 | 兜底三元组 `("11","12","1A")`，并由对拍测试保证主路径命中 |
| Web 侧 import 解析器模块引入重依赖 | 两模块均为纯逻辑（无 PyQt/reflex）；`web_utils` 已把项目根加入 `sys.path` |
| offscreen 测试污染真实 `config.json` | 双 patch `main_gui.data_path` + `app_paths.data_path`，并有断言读取真实文件未被改写 |

## 执行结果（2026-09-16 落地）

| 步骤 | 状态 | 证据 |
| --- | --- | --- |
| 0 复现基线 | ✅ | 源码 offscreen 实测：`_gw_parse_level='app'` + 协议11 → `_strip_gw_new_gen_prefix` 返回 `''`；`'auto'` → 返回 24 字节 hex（与修复后同） |
| 1 桌面级别来源 | ✅ | `main_gui.py:4836` `parse_level = self._current_parse_params().get("parse_level") or "auto"` |
| 2 桌面端口判据 | ✅ | `_gw_app_port_prefixes`（`main_gui.py:1027`，集合取自 `hdc10_parser.APP_PORTS` / `GWNewGenParser.PORT_NAMES`）；app 分支 `main_gui.py:4914` 改集合成员判定 |
| 3 Web 同步 | ✅ | `web_utils.strip_gw_new_gen_prefix(text, parse_level, protocol_index=10)` + 同集合来源；`reflex_web.py:876/880` 分别传 10/11 |
| 4 新增测试 | ✅ | `test/test_hdc10_batch_strip_level.py` 29 项全绿；已登记 `release_check.py:CORE_TESTS` |
| 5 变异反证 | ✅ | 变异A（集合退回 `("11",)`）→ `PASS=20 FAIL=9` 退出码 1；变异B（级别退回 `_gw_parse_level`）→ `PASS=28 FAIL=1` 退出码 1（红项=「协议11：协议10 残留 app 不再影响」）；两处还原后 `PASS=29 FAIL=0` |
| 6 全量回归 | ✅ | `test_hdc10` 20/20、`test_gw_batch_parse` 通过、`test_gw_parse_levels` 通过、`test_gw_monitor_summary` 18/18、`test_web_parse_fixes` 75/75、`test_gui_batch_perf` 99/99、目标套件 29/29；`release_check.py` 全量自检（含 CORE_TESTS）见下方 |
| 7 文档/版本收口 | ✅ | `APP_VERSION=1.23.17`；CHANGELOG 顶部条目；`AGENTS.md` §8 陷阱 43 + §10 摘要（含「strip 依赖 `_current_parse_params`、pb_only 下读控件」提示）；`README.md` 徽章 1.23.17；两个 `.iss` 经 `release_check.py --sync-iss --skip-tests` 同步（该次 PASS=10 FAIL=0，README WARN 已随徽章修正消除） |
| 8 提交 | ⏳ | 待提交 |

### 独立复核（trellis-check 子代理，只读）

- 7 条验收点**逐条通过**（含它自行补做的 1A 起始帧探针、两侧循环边界逐行对比、变异反证独立复现并与 CHANGELOG 数字吻合）。
- **无阻断性缺陷**；越界核查均通过（协议9 剥离未动、协议10/11 重复剥离保留、无第三份硬编码端口副本、spec hiddenimports 已含 `hdc10_parser`/`gw_new_gen_parser`）。
- 3 条提示（已处理/记录）：① 端到端用例（步骤 4 的 [5]）是**组合守卫**——单独回退任一缺陷时它仍绿（因 app 判据放宽后 `12` 开头帧在位置 0 命中，截断为空操作），单变异的守门责任由 [1][2][3][4] 承担，CHANGELOG 的数字表述与此一致；② `strip` 新增对 `_current_parse_params()` 的依赖（后者在 `pb_only` 下读控件）——已写入 AGENTS §8 陷阱 43「新增调用方注意」；③ `str | None` 与 README「Python 3.8+」为仓库既有情况，不属本任务范围。
- 复核者声明**未修改任何产品文件**（改前/改后 sha256 一致，行尾 CRLF 保持）；本任务侧已独立复验：`ast.parse` 通过、`file` 报 CRLF、关键行完整（`if protocol_index == 11:` 在位）、目标套件仍 `PASS=29 FAIL=0`。
