# 实施计划：应用层报文摘要业务名与关键业务字段

> 执行顺序即 checklist；每步末尾给验证命令。**任何一步验证失败即停**，不得带红结果继续。

## 步骤 0 · 准备与基线（不改代码）

- [ ] 记录现场帧的**改动前摘要**作为对照基线（协议11 app 级别）：预期 `端口:18 | 报文:0x0030`（本任务后应变为含 `开始升级 | 升级ID:… | 升级时间窗:…`）。
- [ ] 确认既有摘要测试的断言形态：`test/test_gw_monitor_summary.py` 全部为**子串包含**式（`"端口:抄表业务" in s1`）→ 追加式改动不会破坏；实施后仍需全跑一遍确认（尤其第 4 项「MAC头未解析则退化为应用层摘要」与第 9 项「普通通信测试无测试模式片段」）。
- [ ] 确认协议10/11 的 app 级别表结构（prd 的实测表）仍与规划一致（防止上游 `hdc10_parser`/`gw_new_gen_parser` 已变更）。

**验证**：
```bash
"/mnt/d/Program Files/Python313/python.exe" -X utf8 - <<'EOF'
import sys; sys.path.insert(0, ".")
import hdc10_parser, gw_new_gen_parser
f = bytes.fromhex('12300000010500003F30AE7B78009001972306005ECCEFB1')
for name, p in (("协议11", hdc10_parser.HDC10Parser()), ("协议10", gw_new_gen_parser.GWNewGenParser())):
    rows = p.parse_to_table(f, parse_level="app")
    print(name, len(rows), [str(r[0]).strip() for r in rows])
EOF
```
**回滚点 0**：无改动。

## 步骤 1 · 桌面：新增提取规则（纯函数）

- [ ] 在 `main_gui.py` 模块级（紧跟 `_gw_app_port_prefixes` 之后）新增：

```python
# 应用层报文摘要：业务名 + 关键业务字段（协议10/11 共用同一规则）
# 元数据字段（非业务语义）不占关键字段位；两协议字段名写法并集，避免漏排。
_GW_APP_META_FIELDS = (
    "报文端口号", "报文ID", "安全模式", "安全机制", "业务报文ID", "报文控制字",
    "协议版本号", "报文头长度", "控制/保留", "数据长度", "报文序号",
    "转发数据规约类型", "规约类型", "发送类型", "MSDU类型",
)
_GW_APP_SUMMARY_KEY_FIELDS = 2  # 关键业务字段个数（用户选定 2；改这里即可调）


def _gw_app_biz_summary(table_data) -> tuple:
    """从应用层报文表中提取 (业务名, [关键业务字段…])。

    业务名按优先级：① `── 业务数据 ──` 区头之后的首个普通行字段名（协议11 布局）；
    ② 「报文ID」解析值（仅当它不是 hex 形式，即协议10 已给出业务名的场景）。

    关键字段：字段名带前导空格、非元数据、非分隔行/业务名行、解析值非空、
    且解析值不是「N字节」占位符，按出现顺序取前 _GW_APP_SUMMARY_KEY_FIELDS 个。
    """
    import re

    if not table_data:
        return "", []

    def _name_of(item):
        return str(item[0]).strip() if item and item[0] is not None else ""

    def _parsed_of(item):
        return str(item[2]).strip() if item and len(item) > 2 and item[2] not in (None, "") else ""

    def _is_meta(name):
        return any(name == m or name.startswith(m) for m in _GW_APP_META_FIELDS)

    # ── 业务名 ──
    biz_name = ""
    biz_row_idx = -1
    for i, item in enumerate(table_data):
        if _name_of(item).startswith("── 业务数据"):
            for j in range(i + 1, len(table_data)):
                nm, pv = _name_of(table_data[j]), _parsed_of(table_data[j])
                if not nm or nm.startswith("──") or nm.startswith(("❌", "⚠")):
                    continue
                if nm == str(table_data[j][0]) :  # 无前导空格 → 非业务区行
                    continue
                biz_name, biz_row_idx = nm, j
                break
            break
    if not biz_name:
        for item in table_data:
            if _name_of(item) == "报文ID":
                pv = _parsed_of(item)
                if pv and not re.fullmatch(r"(0[xX])?[0-9A-Fa-f]+", pv):
                    biz_name = pv
                break

    # ── 关键业务字段 ──
    fields = []
    for i, item in enumerate(table_data):
        raw_name = str(item[0]) if item and item[0] is not None else ""
        nm, pv = _name_of(item), _parsed_of(item)
        if i == biz_row_idx or not nm or not pv:
            continue
        if not raw_name.startswith(" ") and nm == raw_name.strip():  # 无缩进 → 不是字段行
            continue
        if nm.startswith("──") or nm.startswith(("❌", "⚠")) or _is_meta(nm):
            continue
        if re.fullmatch(r"\d+字节", pv):  # 字节数占位（区头/长度行）
            continue
        fields.append(f"{nm}:{pv}")
        if len(fields) >= _GW_APP_SUMMARY_KEY_FIELDS:
            break
    return biz_name, fields
```

- [ ] 用步骤 0 的表结构实测：协议11 表 → `("开始升级", ["升级ID:2075013183", "升级时间窗:120分钟"])`；协议10 表 → `("开始升级", ["升级ID:2075013183", "升级时间窗:120分钟"])`。

**验证**：同上脚本 + 调 `_gw_app_biz_summary` 打印两协议结果。
**回滚点 1**：`git checkout -- main_gui.py`

## 步骤 2 · 桌面：接入摘要生成

- [ ] `main_gui.py:_get_gw_new_gen_summary`（约 8448 行）在应用层段 `msg_id` 之后插入业务段：

```python
        biz_name, biz_fields = _gw_app_biz_summary(table_data)
        if biz_name and biz_name != msg_id and biz_name not in " | ".join(parts):
            parts.append(biz_name)      # 业务名单独成段（协议10 的 报文:开始升级 已含则不重复）
        parts.extend(biz_fields)        # 关键业务字段各成一段
```

- [ ] 确认物理层/网络层/测试模式段落**一行未改**（`git diff` 逐块核对）。

**验证**（期望：协议11 → `端口:18 | 报文:0x0030 | 开始升级 | 升级ID:2075013183 | 升级时间窗:120分钟`；协议10 → `端口:升级业务 | 报文:开始升级(下行) | 升级ID:2075013183 | 升级时间窗:120分钟`）：
```bash
QT_QPA_PLATFORM=offscreen python -X utf8 test/test_gw_monitor_summary.py
```
**回滚点 2**：`git checkout -- main_gui.py`

## 步骤 3 · Web 同步

- [ ] `reflex_web/reflex_web/web_utils.py`：新增同名的 `_GW_APP_META_FIELDS` / `_GW_APP_SUMMARY_KEY_FIELDS` / `_gw_app_biz_summary`（与桌面逐字相同的规则）。
- [ ] `get_hdc10_summary`（:777）**应用层段**改为与桌面同口径：`端口:` 取解析值、`报文:{值}` + 方向（从「应用层报文」行 comment 取 `下行`/`上行`）、追加业务名与关键字段、`序号/规约/数据长度` 同文案；物理层/MSDU/MME 段保持不动。
- [ ] `get_frame_summary`（:840）：`if protocol_index in (9, 10)` → 改为只判 `9`；`10` 与 `11` 均走 `get_hdc10_summary`（顺带修掉 AGENTS §8 陷阱 31 记录的协议10 漂移）。
- [ ] 更新该函数 docstring：说明「应用层段与桌面 `_get_gw_new_gen_summary` 同口径，对拍见 `test_gw_app_summary_detail.py`」。

**验证**：两端对拍脚本（应用层表 × 协议10/11 逐字符相等）。
**回滚点 3**：`git checkout -- reflex_web/`

## 步骤 4 · 新增测试 `test/test_gw_app_summary_detail.py`

- [ ] 文件头：docstring → `import _path_setup  # noqa: E402,F401` → 业务 import。
- [ ] 用例组（与 prd R5 一一对应）：
  1. **纯函数**：协议11/协议10 表 → `("开始升级", ["升级ID:2075013183", "升级时间窗:120分钟"])`；元数据不入选；未知结构 → `("", [])`。
  2. **协议11 端到端**：现场帧 → 精确摘要（验收 1），且 ≠ 旧摘要。
  3. **可区分性**：用户 20 行样本（app 级别、批量解析）→ 20 条摘要互不相同，且分钟数分别等于样本值。
  4. **协议10 端到端**：同帧 → 含业务名与 2 字段，业务名不重复（`s.count("开始升级") == 1`）。
  5. **元数据排除**：断言摘要不含 `安全模式:`/`报文控制字:`/`协议版本号:`/`数据长度:`（按协议分别断言）。
  6. **回归**：构造网络层/物理层表 + 0xF0 测试帧表 → 与改动前逐字符一致（基线来自步骤 0 记录 + `test_gw_monitor_summary.py` 既有断言）。
  7. **两端对拍**：桌面 vs `web_utils.get_hdc10_summary`（应用层表 × 协议10/11）；`get_frame_summary(table, 10)` == `get_hdc10_summary(table)` 且 ≠ `get_csg_new_gen_summary(table)`。
- [ ] 若既有测试出现整串断言冲突（预期无，全为子串式）→ **逐条核对后更新期望值并在 CHANGELOG 说明**，不静默改。
- [ ] 登记 `release_check.py:CORE_TESTS`。

**验证**：`QT_QPA_PLATFORM=offscreen python -X utf8 test/test_gw_app_summary_detail.py`
**回滚点 4**：删除该测试文件（不影响产品代码）。

## 步骤 5 · 变异反证

- [ ] 变异 A：`_GW_APP_SUMMARY_KEY_FIELDS = 0` → 业务字段断言必须变红。
- [ ] 变异 B：业务名提取整段短路（`return "", []`）→ 业务名断言与可区分性断言变红。
- [ ] 变异 C：`_gw_app_biz_summary` 不排除元数据 → 「元数据排除」断言变红。
- [x] 每处用**运行时打桩或临时编辑 + 立即还原**，完成后确认 `PASS` 全绿、`git diff` 无残留（防上一轮踩过的「还原失败/变异残留」）。

## 步骤 6 · 全量回归

- [x] `test/test_gw_app_summary_detail.py`（新增，PASS=42 / FAIL=0）
- [x] `test/test_gw_monitor_summary.py`、`test/test_gw_batch_parse.py`、`test/test_gw_new_gen.py`、`test/test_gw_parse_levels.py`、`test/test_hdc10.py`、`test/test_csg_summary.py`、`test/test_web_parse_fixes.py`、`test/test_gui_batch_perf.py`
- [x] `python release_check.py`（见「执行结果」）

**Review gate**：跑一遍 `trellis-check` 子代理独立复核（对照 prd 验收 1~7 取证 + 越界核查 + 自做变异反证）。

## 步骤 7 · 文档与版本收口

- [x] `APP_VERSION` → **1.23.18**（`BUILD_DATE` 于打包当日更新，属发布动作不在本任务内）。
- [x] `CHANGELOG` 顶部条目（现象/规则/两协议覆盖/两端同步含 Web 协议10 分派修正/测试与变异反证；明确记录 Web 应用层摘要文案变更为与桌面对齐）。
- [x] `python release_check.py --sync-iss`；`README.md` 徽章同步（PASS=11 / FAIL=0）。
- [x] `AGENTS.md`：§8 陷阱 44 + §10 摘要 + §1/§2 版本陈述。

## 步骤 8 · 提交与归档

- [x] 提交信息：`feat(summary): 协议10/11 应用层报文摘要显示业务名与关键业务字段`
- [x] `task.py archive .trellis/tasks/09-16-gw-app-summary-detail`

## 风险与应对

| 风险 | 应对 |
| --- | --- |
| 关键字段提取误纳入元数据 | 黑名单为两协议字段名并集 + 用「前导空格 + 非 `N字节`」双约束；测试用例 5 专门钉住 |
| Web 与桌面文案漂移 | 应用层段逐段复刻 + 对拍断言；对拍范围限定应用层（物理层差异属另案） |
| 与在跑的 `09-15-web-batch-alignment` 冲突 | 本任务只动「摘要字段提取 + 协议10 分派」两处；改动前先看该任务目录的最新笔记，若已覆盖同点则改为合并/让位 |
| 变异残留（上一轮踩过） | 变异统一用运行时打桩；若必须改文件则同命令内完成「注入→测试→还原→`git diff` 校验」 |

## 执行结果

### 落地文件

- `main_gui.py`：模块级 `_GW_APP_META_FIELDS`（两协议字段名并集，含 `转发数据规约类型`/`转发数据长度`）、`_GW_APP_SUMMARY_KEY_FIELDS = 2`、`_gw_app_biz_summary(table_data)`；`_get_gw_new_gen_summary` 在 `报文:{msg_id}` 后插入业务段（守门 `if port or msg_id:`，业务名等于 `msg_id` 或已出现时不重复追加）。
- `reflex_web/reflex_web/web_utils.py`：同规则常量 + `_field_value`/`_field_comment`（**去缩进后字段名精确相等**，替代原先子串匹配的 `_find_field`）+ `_gw_app_biz_summary`；`get_hdc10_summary` 应用层段与桌面同口径；`get_frame_summary` 协议 10 按表类型分流（应用层表 → `get_hdc10_summary`，否则保持原协议 9 摘要路径，避免丢 TEI）；新增 `_as_int` 容错转换并替换 3 处 `int()`。
- `test/test_gw_app_summary_detail.py`（新，42 项）、`release_check.py:CORE_TESTS`、`AGENTS.md`、`README.md`、`CHANGELOG`、`南网解析工具.iss`、`2222.iss`。

### 两轮独立复核（trellis-check）

- 第一轮发现 **D1**：关键字段扫描未限定应用层段 → 真实夹具 `test/hdc10_real_frames.pkl` 中 6/6 带应用层的表关键字段被 FC/MAC 字段（`版本`/`原始源TEI`/`定界符类型`/`网络类型`）占满；**D3**：Web 协议 10 网络层摘要丢 `TEI`。
- 第二轮确认 D1/D3/D2 全部修好：720 张表污染 509 → **0**；非应用层表 **354/354** 不退化；#25/#1097 帧复验通过；变异可打红。
- 复核同时指出 `web_utils.py` 被整体重排版（格式噪声）→ 已以 HEAD（LF、单引号）为基重建功能块，现 **228+/44-**。
- 变异反证实测（等价实现替换法）：三处变异分别 FAIL **9 / 14 / 4**（复核侧测得 8 / 13 / 3，差异为断言计数口径）。

### 关键决策

- **扫描窗口 + 元数据黑名单 + 仅应用层守门**三重约束：实测证明仅「有应用层才提取」的守门不够（默认 auto/fc_pb 级别下 FC/MAC 字段排在应用层之前）。
- **Web 协议 10 按表类型分流**：应用层表走增强实现，物理层/网络层保持原路径；两端全量对齐明确留给 `09-15-web-shared-parse-core`。
- 协议 9 摘要、详情面板、导出、监控器摘要**不动**（范围外）。

### 遗留（不修）

- lens/ruff 报出的 100+ 项静态告警均为**既有代码**技术债（PySide6 枚举访问写法、`_find_field` 返回 `tuple|None`、`QLayout.takeAt` 覆盖签名、项目根模块惰性 import），经 `git diff` 核验不在本轮改动内；本轮仅将 `int()` 相关的 3 处换成 `_as_int`。
- `BUILD_DATE` 与重新打包 EXE 属发布动作，未在本任务内执行。
