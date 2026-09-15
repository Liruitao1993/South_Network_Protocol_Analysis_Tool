# 设计：Web 批量摘要分页 + 视口自适应高度 + 全宽布局

## 1. 现状与根因（实测）

| 现象 | 代码事实 |
|---|---|
| 摘要只显示前 300 条 | `State.batch_display_limit = 300`（`reflex_web/reflex_web/reflex_web.py:74`）；`batch_results` 只 append 前 300（`:919`），UI 再切一次 `[:limit]`（`:4576`），超出给琥珀色提示（`:4643`） |
| 一屏只看 3~4 行 | 摘要滚动区写死 `height="360px"`（`:4639`）；右侧明细写死 `350px`（`:4746`） |
| 宽屏两侧留白 | `GLOBAL_CSS` 的 `.app-container` / `.app-header-inner` 写死 `max-width: 1320px` |

**为什么不能"直接全部下发"**：`batch_results` 是 Reflex State 字段，变更时整个字段经 WebSocket 序列化下发（后端已有 `State ... serializes to 23987412 bytes` 告警，出现在 27465 帧的会话）。27465 条摘要 ≈ 单次 5MB+，且 `rx.foreach` 会渲染等量卡片（十几万 DOM 节点）→ 页面卡死。桌面版无此约束（`QTableWidget` 原生虚拟化）。
→ 结论：**分页**（用户建议的方向）同时解决状态膨胀与渲染量；虚拟滚动需自研、Reflex 无官方支持，本任务不做（记录为可选后续）。

## 2. 数据流（改后）

```
parse_batch
  ├─ all_results      （含 frame_bytes + 完整 result 行）→ _batch_all_results（私有，永不下发）
  └─ summaries        （{id,status,proto,summary,len} × 全量）→ _batch_summaries（私有）
                                  │
                    _load_batch_page()  只把当前页切片写入
                                  ▼
                        batch_results（公有，≤ page_size）
                                  │
        batch_page / batch_page_count / batch_page_size / batch_total_frames（公有，标量）
```
选中贯通：`select_batch_item(page_idx)` → `frame_id = batch_results[page_idx]["id"]`（全局 id）→ 取 `_batch_all_results[frame_id]` 明细；`batch_selected_idx` 存**全局 id**（修复跨页高亮失效）。

## 3. 纯函数契约（`web_utils`，可脚本测试）

```python
def paginate(items: list, page: int, page_size: int) -> tuple:
    """→ (page_slice, page_count)；page 越界自动夹取到 [0, page_count-1]；
    空列表 → ([], 1)；page_size<=0 → 视为 1。"""
```

## 4. State 变更

新增/改动（`reflex_web.py`）：
```python
batch_page: int = 0
batch_page_size: int = 100        # 可选 100/200/500/1000
batch_page_count: int = 0
_batch_summaries: list[dict] = [] # 全量摘要（下划线 → 不序列化到前端）
# 删除 batch_display_limit（由分页取代，避免两处上限口径）

def _load_batch_page(self)        # 切片 + 写 batch_results（不改 batch_page 合法性由 paginate 夹取）
def batch_goto_page(self, page: int)   # 首页/上页/下页/末页 共用一个入口
def set_batch_page_size(self, size: str)
```
`parse_batch` 末尾：`_batch_summaries = summaries` → `batch_page_count` → `batch_page = 0` → `_load_batch_page()`；`clear_batch` 一并清空新字段。

## 5. UI 变更

- 摘要滚动区：`height="calc(100vh - 340px)"` + `min_height="320px"`（明细区 `calc(100vh - 380px)`）。
- 页码条（摘要卡片底部）：`共 N 帧 · 第 x / y 页` + `首页/上一页/下一页/末页` + 每页条数 select；按钮在首/末页禁用（`disabled`）。
- 行号 `#` 用全局 `item["id"] + 1`（跨页连续，与桌面序号一致）。
- 工具栏 `共 {batch_total_frames} 帧`（原为当前页长度）。
- `GLOBAL_CSS`：`.app-container` / `.app-header-inner` 去 `max-width`（保留 padding，窄屏自适应）。

## 6. 兼容与取舍

- 导出仍基于后端全量 `_batch_all_results`（不受分页影响）。
- 进度条/完成文案不变。
- 每页 100 → 单次 delta 约 25KB；每页 1000 → 约 250KB（用户可自行权衡）。
- 桌面版不动（本任务为 Web 侧）。
