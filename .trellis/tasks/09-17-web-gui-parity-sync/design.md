# 技术设计：Web↔GUI 修复同步

> 前提事实均在 2026-09-17 实测确认（命令与输出见 implement.md 的验证步骤）。

## D1 审计方法（R1）

- 数据源：`main_gui.py:CHANGELOG`（按版本倒序）+ 各版本对应提交（`git log --oneline`）。
- 逐版逐条判定，四分类：
  - `继承`：Web 走**同一个类/函数**，改动自动生效。判据必须是 import 链或同一调用点，不能只凭"看起来会走"。
  - `缺失`：GUI 有独立实现，Web 没有对应能力。
  - `同错`：两端各有一份实现且**都有**同一缺陷。
  - `N/A`：纯 GUI（窗口/托盘/主题/菜单/Qt 特有）或 Web 已定不做（监控/档案/拓扑）。
- 已知的**继承证据样张**（写入清单作为判据范式）：
  - 解析器层：`reflex_web/reflex_web/reflex_web.py:483` `from dlt645_parser import DLT645Parser`；协议11 同段 import `HDC10Parser` → 1.23.19/1.23.20/1.23.21/1.23.22 的解析修复**全部自动继承**。
  - 间接继承：`reflex_web/reflex_web/lookup_utils.py:186` `from dlt645_di_lookup import get_dlt645_di_lookup`，而 `dlt645_di_lookup.py:14` 内部 `from dlt645_pv_ext import merge_pv_di_map` → 1.23.21 的光伏扩展 DI 在 Web 查询页生效（Web 无直接 import，但经 lookup 单源）。
- 产出：`docs/Web与GUI同步审计.md`，表格列固定（版本 / GUI 改动 / 判定 / Web 位置或依据 / 处置），供后续版本追加。

## D2 R2.1 — 645 转表收口为单一来源

**现状**：两份逐字相同的实现

| 位置 | 说明 |
| --- | --- |
| `protocol_registry.py:355` `DLT645GuiParser.parse_to_table` | 桌面调用方（`main_gui` 经 `protocol_registry` 取 GUI 解析器包装） |
| `reflex_web/reflex_web/reflex_web.py:511` `_safe_parse_to_table` 的 `not hasattr(parser,"parse_to_table")` 分支 | Web 复制体（注释自称"桌面同款"） |

**方案**：Web 侧删掉复制体，改调桌面同一实现。

```python
def _safe_parse_to_table(self, parser, frame_bytes, **kwargs):
    if not hasattr(parser, "parse_to_table"):
        # 645 转表唯一实现在 protocol_registry.DLT645GuiParser（纯 Python 无 Qt）
        from protocol_registry import DLT645GuiParser
        return DLT645GuiParser(parser).parse_to_table(frame_bytes)
    return parser.parse_to_table(frame_bytes, **kwargs)
```

**可行性依据（已核实）**：
- `protocol_registry.py` 仅 import `dataclasses` / `typing`（无 Qt）→ Web 可安全 import。
- Web **已经在** import 它：`reflex_web.py:568` `_get_validator` 内 `import protocol_registry; return protocol_registry.make_validator(...)`。
- `DLT645GuiParser.__init__(self, parser)` 只需一个 parser 实例，而 Web `_get_parser()` 返回的正是 `DLT645Parser()`。
- 保留方法名 `_safe_parse_to_table` → 调用点零改动。

**否决的方案**：① Web import `main_gui`（拉 PySide6，Web 不该依赖 GUI 栈）；② 新建第三方模块再由桌面转发（`protocol_registry` 本就是"GUI 解析器包装"的家，多一层无收益）。

## D3 R2.2 — 偏移公式修正（单点修改，两端自动生效）

在 `protocol_registry.DLT645GuiParser.parse_to_table` 内：

```python
result = self.parser.parse(data)
frame_len = len(data)                       # 实际帧长（权威）
# 数据域/数据内容末端：受实际帧长约束（帧尾 2 字节 = CS + 结束符）
data_end = max(0, min(10 + data_len - 1, frame_len - 3))
# 校验和/帧结束符：用实际帧长定位（1.23.22 起"声明不符"帧也会走到这里）
cs_pos = max(0, frame_len - 2)
end_pos = max(0, frame_len - 1)
```

替换现有 `total_len = 10 + data_len + 2`（`protocol_registry.py:363`）及其三个使用点：「数据内容」/「数据域」末端 → `data_end`；「校验和」→ `cs_pos`；「帧结束符」→ `end_pos`。变量 `total_len` 删除（避免 F841）。

**逐行不变的证明**：合法帧满足 `frame_len == 10 + data_len + 2`，此时
`data_end == 10 + data_len - 1` 且 `cs_pos == 声明总长 - 2`、`end_pos == 声明总长 - 1` → 与旧公式完全相同。故**合法帧输出逐行不变**（硬约束，测试对拍守住）。

**边界**：
- `frame_len < 12`：`DLT645Parser.parse` 走降级分支，表中无「校验和」行，公式不触发；`max(0, ...)` 保证即使触发也不产生负偏移。
- `frame_len == 0`：不可达（`web_utils.hex_to_bytes_strict` 与桌面 `_clean_hex_input` 均拒绝空输入）。
- `⚠ 校验和错误` 行名含「校验和」→ 自动落到 `cs_pos`（这正是修复目标之一）。
- **勿改**提示行名（陷阱 49：行名必须含「校验和」，否则高亮落字节 0）。

## D4 R3 — 测试模式摘要共享落点

**新建 `frame_summary.py`**（项目根，纯逻辑无 Qt，模块级仅 stdlib）：把 `main_gui.py:8219` `MainWindow._extract_test_mode_content` 的函数体**原样搬入**为模块函数 `extract_test_mode_content(table_data) -> str`。

两端接线：

| 端 | 位置 | 做法 |
| --- | --- | --- |
| 桌面 | `main_gui.py:8219` | `@staticmethod` 保留，函数体改为一行 `return frame_summary.extract_test_mode_content(table_data)` |
| Web | `web_utils.get_csg_new_gen_summary`（协议9） | 追加 `frame_summary.extract_test_mode_content(table_data)` 片段 |
| Web | `web_utils.get_hdc10_summary`（协议10/11） | 同上 |

**保留桌面转发的理由**：`test/test_csg_summary.py` 以「Host 复用 `MainWindow` 未绑定方法」的方式调用它（AGENTS 1.23.10 记录），改名会连带改测试；保留转发还让两个调用点（`main_gui.py:8546`、`:8787`）零改动。

**插入位置必须与桌面同序**：协议9 要放在 `get_csg_new_gen_summary` 的**对应首个分支**——测试帧帧类型是「命令帧」，放在通用命令分支之后会被淹没（桌面 1.23.10 踩过同一坑）。

**Web 摘要分派现状**（`web_utils.get_frame_summary`，`web_utils.py:1008`）：协议9 → `get_csg_new_gen_summary`；协议11 → `get_hdc10_summary`；协议10 → 应用层报文走 `get_hdc10_summary`、物理/网络层帧走 `get_csg_new_gen_summary`。R3 只需改这两个被调函数，分派本身不动。

## D5 R4 — Web 查询页 CRUD

### D5.1 南网自定义 DI（协议0）

- Web State 新增事件：`add_custom_di`（DI 码 8 位 hex + 名称）、`delete_custom_di`（DI 码）。
- 底层复用 `custom_di_store`（1.23.11 已建单源，纯逻辑无 Qt）：`validate_key_text` / `make_key` / `upsert_entry` / `remove_keys` / `save_custom_di`；内置 DI 拒删判据用 `custom_key_set()`（与桌面同）。
- UI：`lookup_tab()`（`reflex_web.py:10642`）在搜索行下方加一行（仅 `current_protocol == 0` 显示）：DI 码输入 + 名称输入 + 「添加/覆盖」按钮；查询结果表每行加「删除」（仅自定义行显示）。

### D5.2 **路径注入（必须做，否则违反数据外置约定）**

`custom_di_store` 内部经 `app_paths.data_path` 定位文件（desktop 语义）。Web 直接调用会把自定义 DI 写进 **Web 部署目录**——违反 AGENTS §8 陷阱 39（运行时数据必须在部署目录之外、升级替换目录即丢）。

方案：给 `custom_di_store.load_custom_di` / `save_custom_di`（及其调用链）增加**可选路径参数**，默认值保持 `app_paths.data_path("custom_di.json")`：

```python
def load_custom_di(path: str | Path | None = None) -> list[dict]: ...
def save_custom_di(entries, path: str | Path | None = None) -> None: ...
```

- 桌面调用点**不传** → 行为零变化（兼容）。
- Web 传 `reflex_web.app_data` 解析出的路径 → 落 Web 数据根（`nw_web_data/`），符合陷阱 39。

### D5.3 国网自定义 AFN（协议7）

桌面无 store 单源，直调 `gdw_parser.add_custom_afn(afn, afn_name)`（`main_gui.py:4380`），落 `gdw_custom_afn.json`，由 `GDW10376Parser` 内部管理。

方案：Web 调**同一 parser 方法**（Web 已 import `GDW10376Parser`）。实现第 1 步先核实：
1. `GDW10376Parser` 的增删方法名（`add_custom_afn` / 是否存在 `remove_custom_afn`）与去重/覆盖语义；
2. 其落盘函数是否同样硬编码 `app_paths` → 若是，按 D5.2 同手法加可选路径参数。

若核实发现注入代价过大（例如落盘点分散在 3 处以上），**降级方案**：Web 侧该协议只做「查看 + 明确提示读桌面端维护」，并在 `docs/Web与GUI同步审计.md` 记为后续候选（不静默降级，必须在清单里留档）。

### D5.4 交互等价性取舍

- 桌面 `delete_selected_custom_di_interactive` 支持**多选批量删除**；Web 第一版做**单条删除 + 删除后自动重查**。
- 理由：Reflex 表格多选需前端选中集合 + 全选/清空交互，属独立 UI 工作量；单条删除已覆盖现场主要用法。
- 该差异**必须写进审计清单**（判定 `缺失（有意延后）`），不假装等价。

## D6 测试与守卫

| 测试文件 | 覆盖 |
| --- | --- |
| `test/test_dlt645_table_offsets.py`（新） | 偏移矩阵：合法帧逐行不变（与改动前对拍）· 声明不符帧 `14/14/15` · `frame_len<12` 降级不产生负偏移 · 空表 · **单一来源守卫**（`reflex_web.py` 源码中不得再出现 `total_len = 10 + data_len + 2`，且必须 import `DLT645GuiParser`） |
| `test/test_web_gui_parity.py`（新） | R3：真实帧（协议9 测试帧 / 协议10 检测扩展命令 / 协议11）桌面摘要 vs Web 摘要**逐字符**一致；协议9 非测试帧不受影响 · R4：`custom_di_store` 路径注入（沙箱）+ 增删逻辑 + 内置拒删 + 两端各自落盘根 |
| `test/test_csg_summary.py`（改） | 若转发签名/行为不变则零改动；补一条「桌面转发 == `frame_summary.extract_test_mode_content`」一致性断言 |

**变异反证（至少 2 条，必须实测变红后还原）**：
1. 偏移公式改回 `total_len = 10 + data_len + 2` → `test_dlt645_table_offsets` 变红；
2. 删掉 Web 摘要里的测试模式片段 → `test_web_gui_parity` 变红。

**沙箱注意**（陷阱 42 教训）：offscreen 测试须同时 patch `main_gui.data_path` **与** `app_paths.data_path`，否则会把真实 `config.json` / 数据文件写掉；Web 侧 patch `app_data` 的解析函数。

## 兼容性与回滚

- 全部为源码改动 + 新增文件，**无数据迁移**；`custom_di_store` 路径参数默认值不变 → 桌面行为零变化。
- 回滚：`git revert` 单个提交即可（改动聚合在一个提交内）。
- 部署影响：Web 新增写入落 `nw_web_data/`（已由启动脚本注入 `NW_WEB_DATA_DIR`），部署脚本与忽略规则**无需改动**（`custom_di.json` 不在 `deploy_common` 的随包资产白名单里，属运行时数据）。

## 风险与未决

| 风险 | 处置 |
| --- | --- |
| `GDW10376Parser` 落盘硬编码、注入代价大 | D5.3 降级方案 + 清单留档 |
| Web 摘要插入位置与桌面不同序 → 协议9 被淹没 | 测试用**真实测试帧**对拍（非构造帧），并在实现时对照桌面 `_extract_csg_core_content` 的首分支位置 |
| 端到端无浏览器验证 | 用 reflex `State(_reflex_internal_init=True)` 真实实例断言（`test/test_web_parse_fixes.py` 已有先例）；playwright 可选 |
| 审计遗漏（1.23.0 及更早） | 本任务范围锁定 1.23.0~1.23.22；更早版本由清单的「后续区间」小节记录为待办 |
