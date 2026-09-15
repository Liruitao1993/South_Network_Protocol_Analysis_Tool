# 实施计划：Web 批量摘要分页 + 高度自适应 + 全宽

前置：`prd.md`（本任务总范围）、`design.md`（分页数据流/契约）。**本轮只交付「显示侧」**（原 prd R5 的分页 + 新增 R7 布局），其余逻辑对齐项（摘要同源/跨行 payload/EDA5/行号/导出字段详情）仍待办。

命令在项目根执行；Web 侧验证可直接打已跑的 dev 服务（`http://localhost:3000`）。

---

## 步骤 1 — `web_utils.paginate`（纯函数）

按 `design.md` §3 实现；越界夹取、空列表 `([], 1)`、`page_size<=0` 视为 1。

**验收**：`python -c "import sys;sys.path.insert(0,'reflex_web');from reflex_web import web_utils as w;print(w.paginate(list(range(250)),1,100), w.paginate([],0,100), w.paginate(list(range(5)),9,2))"` → `([100..199], 3)` / `([], 1)` / `([4], 3)`

---

## 步骤 2 — State 分页（`reflex_web.py`）

1. 新增 `batch_page/batch_page_size/batch_page_count/_batch_summaries`，删除 `batch_display_limit`。
2. `parse_batch`：摘要全量落 `_batch_summaries` → `batch_page_count = paginate(...)[1]` → `batch_page = 0` → `_load_batch_page()`。
3. `_load_batch_page()` / `batch_goto_page(page)` / `set_batch_page_size(size)`；`clear_batch` 清空新字段。
4. `select_batch_item`：`batch_selected_idx` 存全局 id；明细按 `batch_results[idx]["id"]` 取。

**验收**：State 级断言（见步骤 4 的测试）通过。

---

## 步骤 3 — UI（摘要卡片 + 明细卡片 + 全局 CSS）

1. 摘要列表：行号全局化、去掉 `[:batch_display_limit]` 与 300 条提示、高度 `calc(100vh - 340px)`。
2. 页码条 + 每页条数 select。
3. 明细滚动区高度 `calc(100vh - 380px)`。
4. 工具栏 `共 {batch_total_frames} 帧`。
5. `GLOBAL_CSS`：两个容器去 `max-width`。

**验收**：`python -c "import sys;sys.path.insert(0,'reflex_web');import reflex_web.reflex_web as m;print(len(str(m.index())))"` 无异常；浏览器实测（步骤 5）。

---

## 步骤 4 — 新增 `test/test_web_batch_paging.py`

- `paginate` 纯函数：切片正确、越界夹取、空列表、page_size 非法值。
- State 端到端（`State(_reflex_internal_init=True)` + `async for _ in st.parse_batch()`）：喂 250 行日志 → `batch_total_frames==250`、`batch_page_count==3`、首页 100 条且 `id` 0..99 → `batch_goto_page(2)` → `id` 200..249 → `select_batch_item(0)` 取到全局 id=200 的明细 → `set_batch_page_size("500")` 后单页 250 条。
- 登记进 `release_check.py:CORE_TESTS`。

**验收**：`PYTHONIOENCODING=utf-8 python test/test_web_batch_paging.py` 全过。

---

## 步骤 5 — 浏览器实测（dev 服务已在跑）

1. 生成 250 行日志（协议9 SOF 帧重复）粘贴 → 批量解析。
2. 断言：`共 250 帧`；页码条 `第 1 / 3 页`；点击「下一页」→ 行号从 `#101` 起；「末页」→ `#201..#250`；点末页首行 → 明细显示且高亮跟随。
3. 断言：`.app-container` 宽度 ≈ 视口宽 - padding（不再 1320 封顶）；摘要区高度 ≈ `100vh-340`（一屏 >10 行）。
4. 若首屏看不到 250 行 → 属预期（分页），翻页可达全部。

**验收**：以上 4 条在真实页面成立（记录实测数值）。

---

## 步骤 6 — 门槛与文档

- `python release_check.py` 无 FAIL；`main_gui.py:CHANGELOG`（1.23.12 条目追加「Web 批量分页/自适应高度/全宽」）、`AGENTS.md §7` 测试清单 + §10 摘要。
- `web-parse-audit.md` §1 B? 与 `09-15-web-batch-alignment/prd.md` 标注「显示侧已完成，逻辑对齐待办」。

## 完成定义（DoD）

`design.md` 的分页/高度/全宽三条全部落地并有测试；浏览器实测 4 条通过；`release_check` 无 FAIL。
