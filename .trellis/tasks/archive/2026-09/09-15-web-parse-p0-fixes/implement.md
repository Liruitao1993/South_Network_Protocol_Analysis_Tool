# 实施计划：Web 解析 P0 修复

前置：`prd.md`（R1~R11 + 验收 1~5）、`design.md`（纯函数契约/ED 布局表/兼容取舍）。
命令在项目根执行，中文输出前置 `PYTHONIOENCODING=utf-8`。

---

## 步骤 1 — `web_utils` 纯函数（4 个）

在 `reflex_web/reflex_web/web_utils.py` 新增：`hex_to_bytes_strict` / `apply_strip_once` / `batch_frame_status` / `parse_kwargs_for`（契约见 `design.md` §2）。

**验收**：`python -c "import sys;sys.path.insert(0,'reflex_web');from reflex_web import web_utils as w;print(w.batch_frame_status([]), w.parse_kwargs_for(10,'pb_only',gw_frame_type=2))"` → `('失败', ...) {'parse_level': 'pb_only', 'channel': 'plc', 'frame_type': 2}`

---

## 步骤 2 — State 改为调用纯函数（校验 / 清洗 / 剔除 / 判定 / kwargs）

`reflex_web/reflex_web/reflex_web.py`：

1. `_clean_hex` → 委托 `web_utils.hex_to_bytes_strict`（保留 State 方法名为薄壳，调用点不动）。
2. `_apply_strip` → 委托 `web_utils.strip_frame_bytes`（**不引入缓存**：Web 每次从原始 `frame_hex` 重算，天然幂等）；`parse_frame` 与 `verify_frame` 都走「清洗 → 剔除」同一段。
3. `parse_frame` / `parse_batch` 的 3 段 `if/elif` kwargs → `web_utils.parse_kwargs_for(...)`；新增 `gw_pb_frame_type: int = 1`（协议10/11 PB 帧类型）+ setter。
4. `parse_batch` 失败判定 → `web_utils.batch_frame_status(result)`；`status`/`summary` 覆盖规则按 R2。
5. `_get_validator` → `protocol_registry.make_validator(self.current_protocol)`（删除 12 项 dict）。
6. 协议9 级别下拉补 `mac_only`；协议10/11 新增 PB 帧类型下拉（`pb_only` 时可见）；协议9 的 `pb_frame_type` 下拉在 `mac_only`/`pb_only` 时可见。
7. 协议9/10/11 级别或帧类型选项抽为模块级常量（供测试断言，不解析组件源码文本）。

**验收**：`python -c "import sys;sys.path.insert(0,'reflex_web');import reflex_web.reflex_web"` 无异常（需 reflex 已安装；纯语法回归另用 `python -m py_compile reflex_web/reflex_web/reflex_web.py`）。

---

## 步骤 3 — ED 包装自动识别与双布局（parser + 桌面委托 + 摘要消费者）

1. `csg_new_gen_parser.py`：新增 `_ED_PB_SIZES`、`detect_ed_wrapper(frame_bytes, fallback="plc2")`；`_parse_ed_wrapper(..., wrapper=None)` 支持双布局与两种标题；`parse_to_table(..., ed_wrapper=None)` 透传。
2. `main_gui.py`：`_detect_ed_wrapper` 改为委托（保留方法名/返回语义，删除重复打分）；摘要 ED 分支（`7910`）改判 `监控包装头` 并按标题区分包装名。
3. `reflex_web/reflex_web/web_utils.py:412` ED 摘要分支同上。

**验收**：
- `PYTHONIOENCODING=utf-8 python test/test_ed_gx_wrapper.py` 全过（22 项）
- `PYTHONIOENCODING=utf-8 python test/test_ed_fallback_fix.py` 全过
- `PYTHONIOENCODING=utf-8 python test/test_csg_summary.py`、`test/test_csg_sequence_model.py` 全过

---

## 步骤 4 — 查询页与报文工具

1. `lookup_utils._search_south_di`：`afn = di1` + `AFN_MAP` 名称。
2. `lookup_utils._search_gw_newgen`：改用 `GWNewGenParser` 7 类表；`QUERY_CONFIG[10]` 列改 4 列（类别/代码/名称/说明）。
3. `lookup_utils._search_698_oi`：属性/方法从 `OILookup` 类映射填。
4. `web_utils.tool_crc24_newgen`：`rev=True`。

**验收**：
```
PYTHONIOENCODING=utf-8 python -c "import sys;sys.path.insert(0,'reflex_web');from reflex_web import lookup_utils as L;print(L.get_lookup_data(0,'添加任务'));print(len(L.get_lookup_data(10,'')), L.get_lookup_data(10,'关联')[:1]);print(L.get_lookup_data(8,'')[0])"
```
→ AFN 含 `02H`；协议10 总数 49 且「关联」有命中；协议8 属性列非 `-`。

---

## 步骤 5 — 新增测试 `test/test_web_parse_fixes.py`

按 `prd.md` 验收 1 的 a~j 逐条断言（纯函数 + parser 端到端 + 查询层 + 工具），`import _path_setup` 头；登记进 `release_check.py:CORE_TESTS`。

**验收**：`PYTHONIOENCODING=utf-8 python test/test_web_parse_fixes.py` → 全过、退出码 0。

---

## 步骤 6 — 发布门槛与文档

- `APP_VERSION` → `1.23.12`；`BUILD_DATE` 更新为当天；`main_gui.py:CHANGELOG` 头部条目（Web P0 修复 10 条 + 空表语义统一 + ED 自动识别下沉 + AFN/协议10/698/CRC-24 查询与工具修复）。
- `AGENTS.md §1`（Web 协议覆盖 0-11 修正）、`§7`（测试清单补 `test_web_parse_fixes.py`）。
- `python release_check.py` → PASS ≥ 基线 49、FAIL=0。

---

## 完成定义（DoD）

`prd.md` 验收 1~5 全部满足；步骤 1~5 验收命令通过；`release_check.py` 无 FAIL；改动集中在 Web 胶水层 + ED 单源化，未引入第三份实现。
