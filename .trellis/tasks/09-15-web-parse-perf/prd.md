# Web 解析性能与内存（parser 缓存 / 分段 yield / 摘要索引 / 流式导出）

## Goal

消除 Web 解析链路上的性能与内存隐患：每请求新建 parser、批量准备阶段阻塞单进程事件循环、摘要线性扫表、全量结果常驻内存与导出整串复制（父任务 `research/web-parse-audit.md` §4 的 P1~P9）。

依赖：`09-15-web-shared-parse-core`（摘要与提取先单源化，避免在复刻体上做优化）。

## Confirmed Facts

- P1 每请求新建 parser：`reflex_web.py:417-481`；`ProtocolFrameParser.__init__→_load_custom_di()` 每次读 `custom_di.json`（`protocol_parser.py:787-795`）；`DLT69845Parser.__init__` 每次建 crcmod（`dl_t698_45_parser.py:37-38`）；桌面用 `parser_registry.get_parser` 共享实例（`parser_registry.py:47-54`）。
- P2 批量准备阶段（剥离→清洗→提取）零 yield，首个 yield 在第 100 帧（`reflex_web.py:973`）；`handle_batch_upload` 明示允许 50MB 输入（`749-751`）。
- P3 逐帧二次正则清洗（`reflex_web.py:901-903`，提取阶段已保证纯 hex）。
- P4 逐字符 Python 级 hex 过滤（`web_utils.py:311/362/365/368/377`）。
- P5 摘要线性 `_find_field` 反复扫表（`web_utils.py:393-398`，一次摘要最多 ~20 次全表扫描）vs 桌面先建 `fields` dict（`main_gui.py:7907/8080/8237-8241`）。
- P6 全量结果常驻 `_batch_all_results` + 导出 `json.dumps(indent=2)` 再复制一份（`web_utils.py:975-1000`）；P7 `rx.download(data=...)` 整串（`reflex_web.py:1139-1156`）。
- P8 Wrapper 提取兜底把整段文本当单帧（`web_utils.py:301`，无长度上限）。
- P9 明细表无分页（`reflex_web.py:4683-4700`）；`batch_display_limit=300` 已在摘要层限流。

## Requirements

### R1 parser 实例复用

- Web 复用 `parser_registry.get_parser`（或提供等价模块级缓存），避免每请求构造。
- 若复用共享实例：必须确认**有状态 parser 的跨请求污染**（协议9 `_channel`/`_concat_segments`/`_pb_size`）不产生错误结果——否则改为「按请求新建但缓存重资源部分」（如 `custom_di.json` 的加载结果、crcmod 实例）。

### R2 批量阶段让出事件循环

- 剥离/清洗/提取阶段分段 `yield`（每 N 行或每 X ms），保证进度条推进与其他请求不被饿死；或把该阶段放入 `asyncio.to_thread` 后回主循环。
- 提供取消入口（长任务可中断）。

### R3 去除冗余计算

- 逐帧去掉二次 `re.sub`（提取阶段契约已是纯 hex，异常走 per-frame except）。
- `web_utils` 的逐字符 hex 过滤改 `str.translate` 或一次性处理；大输入避免整串多次复制。
- 摘要改「一次建索引」（与桌面同款），删除线性 `_find_field` 热路径。

### R4 内存与导出

- `_batch_all_results` 设上限/按需重解析策略（例如只保留最近 N 帧明细，其余按需重解析）；导出改流式（临时文件 + FileResponse 或分块响应），峰值内存不随结果集倍增。
- Wrapper 提取兜底加长度上限，超限改为「未识别到有效帧」。

### R5 回归基线

- 用可复现基准（脚本：构造 N 帧日志 → 计时/内存）记录优化前后数据，写入任务 `research/`。

## Acceptance Criteria

1. 基准实测（≥1MB / ≥5000 帧输入）：批量解析总耗时下降、准备阶段有事件循环让出（可用「进度回调在准备阶段被调用」或 asyncio 任务并发探针证明）、进程峰值内存不随结果集线性膨胀。
2. 解析结果与优化前逐帧一致（同一输入 → 相同 status/摘要集合，用对拍断言）。
3. `reflex_web` 服务端在 50MB 输入下不再长时间无响应（可用本地起服 + 长任务并发请求验证）。
4. `python release_check.py` 无 FAIL；新增基准脚本不进入 `CORE_TESTS`（除非可稳定快速运行）。
5. `AGENTS.md`/`CHANGELOG` 记录性能结论（含数字）。

## Out of Scope

- 前端渲染性能（虚拟滚动/分页）——若需要，随 `web-batch-alignment` 的显示上限议题单独立项。
- 服务端持久化/任务队列改造（若基准显示需要，另立需求）。

## Risks / Deferred

- parser 实例复用的收益与污染风险并存：先做「重资源缓存」再评估是否共享实例，逐协议验证（协议9/10/11 有跨帧状态）。
- 流式导出涉及 Reflex/Starlette 集成方式（`rx.download` vs 自定义路由），需在实现前确认可用的 API 形态。
