# 实施计划：测试帧摘要体现测试模式

前置：`prd.md`（R1~R4 + 验收 1~7）、`design.md`（契约/字段消费表/接入点）。按步骤执行，每步自带验收命令；末步统一跑 `release_check.py`。

环境：命令在项目根执行；中文输出设 `PYTHONIOENCODING=utf-8`。

---

## 步骤 1 — `main_gui.MainWindow._extract_test_mode_content`（纯 staticmethod）

在 `_get_csg_new_gen_summary` 之前（`_extract_csg_core_content` 附近）新增 staticmethod，按 `design.md` §3 字段消费表实现：

- 建索引：`fs = {str(name).strip(): item for item in table_data}`（同名取首个）。
- 判定与片段顺序：`测试模式/配置操作` → `安全测试模式` → `新一代测试模式` → （仅当无前者时）`测试ID`/`扩展ID` → `测试数据区` 的 `通信频段`。
- 上行测试帧：无上述字段但存在 `上行负载` → `测试帧上行（确认/否认，无数据单元）`。
- comment 清洗：去掉尾缀 `（高4位）`；comment 空则用 raw；raw 也空则只输出字段名。
- 全无痕迹 → 返回 `""`。

**验收**：`python -c "import main_gui; print(main_gui.MainWindow._extract_test_mode_content([('测试模式/配置操作','3','3','PLC物理层透传测试模式（高4位）',1,1)]))"` → `测试模式:PLC物理层透传测试模式(3)`

---

## 步骤 2 — 接入协议9 摘要

`_extract_csg_core_content` 顶部（在 `ft_desc`/`svc_desc` 取值之后、`否认`分支之前）插入测试帧分支：

```python
        svc_item = fields.get("业务标识")
        is_test_frame = bool(svc_item) and (
            str(svc_item[2]).strip() == "240"
            or "F0" in str(svc_item[1]).upper()
            or "测试帧" in str(svc_item[3])
        )
        if is_test_frame:
            mode_text = self._extract_test_mode_content(table_data)
            if mode_text:
                return mode_text
```

（`self._extract_test_mode_content` 在 staticmethod 下同样可用；`_extract_csg_core_content` 保持实例方法。）

**验收**：真实抓包帧（`test/test_csg_batch_parse_level.py` 的 TCP 帧）经 `CSGNewGenParser().parse_to_table(app)` → 摘要含 `业务标识:测试帧(0xF0)` 与 `测试ID:频段切换命令`。

---

## 步骤 3 — 接入协议10/11 摘要

`_get_gw_new_gen_summary` 在 `return " | ".join(parts) if parts else "-"` 之前追加：

```python
        # 9. 测试类报文：测试模式/配置操作（检测扩展命令）
        test_mode_text = self._extract_test_mode_content(table_data)
        if test_mode_text:
            parts.append(test_mode_text)
```

**验收**：`_parse_comm_test` 构造 `test_mode=3` payload → `Host._get_gw_new_gen_summary(rows)` 含 `测试模式:HPLC物理层透传测试模式(3)`。

---

## 步骤 4 — `test/test_csg_summary.py` 重构 + 新增

- 删除文件内复刻的 `get_csg_new_gen_summary` / `extract_csg_core_content`，改挂 `main_gui.MainWindow` 未绑定方法（Host 类，同时提供两个方法）。
- 既有 6 个用例改用 Host 调用（断言不变）。
- 新增 4 个用例（真实抓包 0xF0 帧 / 构造 1.0 测试帧 / 上行测试帧 / 非测试帧 helper 返回空）。

**验收**：`PYTHONIOENCODING=utf-8 python test/test_csg_summary.py` → 全过、退出码 0。

---

## 步骤 5 — `test/test_gw_monitor_summary.py` 新增

构造检测扩展命令 payload（字节1高4位=测试模式；模式 3 与 13 两例），用 `gw_new_gen_cmd_payloads._parse_comm_test` 出真实行，断言摘要含 `测试模式:HPLC物理层透传测试模式(3)` / `安全测试模式:`。

**验收**：`PYTHONIOENCODING=utf-8 python test/test_gw_monitor_summary.py` → 全过。

---

## 步骤 6 — 发布门槛与文档

- `python release_check.py`（两个测试已在 `CORE_TESTS`，无需改清单）→ 无 FAIL。
- `main_gui.py:CHANGELOG` 头部 1.23.10 条目（本功能 + 摘要单源重构）；`APP_VERSION` → `1.23.10`。
- `AGENTS.md` §3 说明（摘要函数职责）、§10 摘要；`README.md` 功能/使用说明补一句「测试帧摘要体现测试模式」。
- `.trellis/spec/frontend/component-guidelines.md` 若有可复用教训（摘要单源、staticmethod 免 GUI 测试）则补一节。

---

## 完成定义（DoD）

`prd.md` 验收 1~7 全部满足；步骤 1~5 验收命令通过；`release_check.py` 无 FAIL。
