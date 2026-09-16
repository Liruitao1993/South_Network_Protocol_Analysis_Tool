"""批量解析后台工作线程（任务 09-15-gui-batch-parse-perf 步骤 2）

原状：``MainWindow.parse_batch`` 在主线程从剥离到填表全程同步执行，
33 MB 样本日志（49,532 帧）需约 21 s，期间界面完全冻结、无进度、无取消。

本模块把「逐帧解析 + 摘要生成」移到 QThread，UI 线程只保留：
  - 前缀剥离 / 清洗 / 帧提取 / 快照与行号映射（约 1.5 s，且行号语义必须同步可见）
  - 按批（而非逐帧）回填摘要表

契约（与 ``main_gui`` 的接线一一对应）：
  - 工作线程**不触碰任何 widget**：所有 UI 读取都靠 ``__init__`` 的参数快照
    （``protocol_index`` / ``parse_level`` / ``frame_type`` / ``channel``），
    摘要与帧类型名通过回调传入并显式带上 ``protocol_index``。
  - **不使用** ``parser_registry.get_parser`` 的共享单例：解析器带帧级可变状态
    （``csg_new_gen_parser`` 每帧重置 ``_pb_size`` / ``_cmt_index`` / ``_pb_count``），
    与单帧解析页、实时监控共享同一实例会互相污染，故工作线程自建实例。
  - 每帧结果 dict 的键名与改动前 ``parse_batch`` 逐字兼容
    （``_input`` / ``_status`` / ``_type_name`` / ``_src_line`` / ``摘要`` /
    ``错误``），确保详情、导出、行号回跳语义不变。
  - 分片 200 帧 emit 一次 ``progress``（≈ 78 ms/片）→ 取消响应远小于验收线 1 s。

单帧解析的唯一实现在**模块级** :func:`parse_one_frame`（步骤 3）：worker 与
「详情按需重解析」（``main_gui._get_frame_table_data``）共用同一份分支逻辑，
否则 ED 帧的详情会与批量解析时的结果不一致。worker 侧只是它的薄封装，
并把 ``_table_data`` 丢弃（常驻内存 229 MB → 约 4 MB 的根源）。

调用方：``main_gui._start_batch_parse`` / ``main_gui._get_frame_table_data``。
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QThread, Signal

import parser_registry
import protocol_registry
import thread_registry

# 每片帧数：太小 → 信号过于频繁；太大 → 取消/进度响应变迟钝（200 帧 ≈ 48 ms）
CHUNK_SIZE = 200
# 每片 emit 后等 UI 回执的上限（秒）。背压：让信号队列最多积压 1 批，
# 否则 `QApplication.processEvents()` 会一次连续回填上百批，主线程长时间出不来；
# 超时则继续（UI 忙时降级为无背压，不会卡死工作线程）
ACK_TIMEOUT = 0.05

# ── 跨帧状态（解析器实例级）锁存 ──────────────────────────────────
# 解析器实例带帧级可变状态，绝大多数在 `parse_to_table` 入口被重置
# （如 csg_new_gen_parser 的 `_pb_size`/`_cmt_index`/`_pb_count`/`_concat_*`），
# 但**个别属性**是「A 帧赋值、B 帧读取」（包括“解析抛异常的帧也会留下半途
# 状态”）——于是同一帧在不同历史下会得到不同表格。实测协议9 真实 33 MB
# 日志（49,532 帧）：934 帧会多/少一行 `⚠️ eFC数据不足`，差分出的状态键为
# `_efc_symbol_count` / `_ofdma_frame_type` / `_ofdma_station_count`
# （这三个只在 FC 可变区域 / OFDMA 分支里被重置）。
#
# 详情按需重解析用的是**另一个**实例（历史必然不同，且会跳过 `_has_detail=False`
# 的帧），因此必须把「解析该帧时的帧前取值」锁进记录、并在重解析前还原
# （帧前等于默认值时不存 → 不占内存；还原时 None = 写回默认值，
# 同时清掉重解析实例自身的残留历史）。
#
# 新增协议 / 新发现同类跨帧状态时的登记方法：用探针脚本对同一批真实帧分别做
# 「全量顺序解析」与「跳过空详情帧的顺序解析」，在本帧前 diff `解析器.__dict__`，
# 差异键即需登记的属性（见任务 09-15-gui-batch-parse-perf 的报告）。
_CROSS_FRAME_STATE: dict[int, tuple[tuple[str, ...], tuple]] = {
    9: (
        ("_efc_symbol_count", "_ofdma_frame_type", "_ofdma_station_count"),
        (0, -1, 0),
    ),
}


def _real_parser(parser):
    """剥掉 GUI 包装层，返回真正持有解析状态的解析器对象。

    `protocol_registry.build_gui_parser` 对协议 9/10/11/6 等返回的是包装对象
    （`CSGGenGuiParser` 等），真解析器在 `.parser` 上。
    快照/还原必须落在**真解析器**上，否则属性会写到包装对象上（实测：
    写成 no-op，详情与批量解析持续不一致）。
    """
    seen = 0
    while seen < 5 and hasattr(parser, "parser"):
        inner = parser.parser
        if inner is None or inner is parser:
            break
        parser = inner
        seen += 1
    return parser


def capture_cross_frame_state(parser, protocol_index: int):
    """取「即将解析这一帧时」的跨帧状态（与默认值相同则返回 None，不占内存）。"""
    spec = _CROSS_FRAME_STATE.get(protocol_index)
    if spec is None:
        return None
    attrs, defaults = spec
    real = _real_parser(parser)
    values = tuple(
        getattr(real, attr, default) for attr, default in zip(attrs, defaults)
    )
    return None if values == defaults else values


def apply_cross_frame_state(parser, protocol_index: int, state):
    """重解析前还原跨帧状态（``state=None`` 时显式写回默认值，清掉实例上的残留历史）。"""
    spec = _CROSS_FRAME_STATE.get(protocol_index)
    if spec is None:
        return
    attrs, defaults = spec
    values = defaults if state is None else tuple(state)
    real = _real_parser(parser)
    for attr, value in zip(attrs, values):
        setattr(real, attr, value)


def resolve_ed_wrapper(frame_bytes: bytes, mode: str) -> str:
    """ED 包装格式判别（widget-free）：mode 为 "plc2"/"gx" 时直接用手动值。

    ``mode`` 为 ``auto``（或非法值）时逐帧调解析器的 ``detect_ed_wrapper``
    打分识别（fallback=plc2）。桌面 ``main_gui._ed_wrapper_for_frame`` 委托
    本函数，避免第二份口径。
    """
    if mode in ("plc2", "gx"):
        return mode
    from csg_new_gen_parser import detect_ed_wrapper

    return detect_ed_wrapper(frame_bytes, fallback="plc2")


def parse_one_frame(
    frame_item,
    index: int,
    *,
    protocol_index: int,
    parser: Any,
    summary_fn: Callable,
    type_name_fn: Callable,
    ed_parse_fn: Callable,
    lead_lines: int = 0,
    strip_map: Sequence | None = None,
    log_fn: Callable | None = None,
) -> dict:
    """单帧解析 → 结果 dict（**唯一实现**，worker 与详情按需重解析共用）。

    Args:
        frame_item: 提取器输出元素——``(hex, ed_type, line_no)`` 元组（协议9 等
            行式协议）或纯 hex 串（流式扫描协议，无行号）
        index: 帧序号（仅用于 ``log_fn`` 的前 5 帧日志）
        protocol_index: 协议索引快照
        parser: 解析器实例（调用方自建，见模块 docstring 的线程安全说明）
        summary_fn: ``(table_data, protocol_index) -> str``
        type_name_fn: ``(table_data, status, protocol_index) -> str``
        ed_parse_fn: ``(frame_bytes) -> (wrapper, rows, business, offset)``
            （协议9 ED 监控包装头解析，widget-free 闭包）
        lead_lines: 首部空白行偏移（仅影响 ``_src_line``）
        strip_map: 前缀剥离行映射（仅影响 ``_src_line``）
        log_fn: 可选调试日志回调（仅前 5 帧）

    Returns:
        结果 dict：``_input`` / ``_status`` / ``_type_name`` / ``_src_line`` /
        ``摘要`` / ``错误``（仅异常帧）/ ``_table_data``（**完整解析表**，调用方
        自行决定是否常驻）/ ``_has_detail``（``bool(_table_data)``：该帧能否
        产出非空详情表；详情按需重解析的判据）/ ``_ed_type``（协议9 提取器给出
        的 ED 类型，非 ED 帧为 ``""``；决定 ED 三分支的走向，必须随记录锁存）/
        ``_ctx``（**仅当帧前跨帧状态非默认时才有此键**：详情按需重解析必须先
        还原它才能复现同一分支，见 `_CROSS_FRAME_STATE`）。

    说明：``_has_detail`` 刻意取「表格非空」而非「解析成功且非空」——失败帧的
    表里同样有 ``❌`` 行（详情面板/导出 Sheet2 原本就会展示它），按「成功」判定
    会让这些帧的详情由有变无、「包含表格数据」列由「是」变「否」，与改动前的
    导出逐字段结果不一致。
    """
    # 协议9返回元组(frame_hex, ed_data_type, line_no)，行式协议返回
    # (hex, "", line_no)，流式扫描协议返回纯字符串（无行号）
    src_line_raw = -1
    if isinstance(frame_item, tuple):
        frame_hex = frame_item[0]
        ed_data_type = frame_item[1] if len(frame_item) > 1 else ""
        if len(frame_item) >= 3:
            src_line_raw = frame_item[2]
    else:
        frame_hex = frame_item
        ed_data_type = ""
    # 回跳显示日志行号 = 首部空白偏移 + 前缀剥离行映射
    src_line = -1
    if src_line_raw >= 0:
        if strip_map and 0 <= src_line_raw < len(strip_map):
            src_line = lead_lines + strip_map[src_line_raw]
        else:
            src_line = lead_lines + src_line_raw

    if index < 5 and log_fn is not None:
        log_fn(
            f"解析帧{index + 1}: [{len(frame_hex) // 2:3d}B] "
            f"开始={frame_hex[:4]}... "
            f"ed_type={ed_data_type or '无'}"
        )

    table_data: list = []
    frame_ctx = None
    try:
        frame_bytes = bytes.fromhex(frame_hex)
        # 协议9：ED 开头但提取失败（报文不完整/格式错误）→ 明确报错，
        # 绝不把 ED 首字节当 FC 起始符送解析器
        if protocol_index == 9 and frame_hex.startswith("ED") and not ed_data_type:
            table_data = [
                (
                    "❌ 解析失败",
                    "",
                    "",
                    "ED 监控帧解析失败：报文不完整或格式错误，"
                    "首字节 ED 不能作为业务帧起始符解析",
                    None,
                    None,
                )
            ]
            summary = "ED 帧解析失败（报文不完整或格式错误）"
            status = "失败"
        # 协议9：合法 ED 帧但无业务数据（控制报文、空数据报文等）
        # 直接解析监控头，不送 CSGNewGenParser
        elif (
            protocol_index == 9
            and ed_data_type
            and ed_data_type.startswith("ED:")
            and frame_hex.startswith("ED")
        ):
            wrapper, meta_rows, _business_bytes, business_offset = ed_parse_fn(
                frame_bytes
            )
            if meta_rows is not None:
                # 去掉最后一行"── 业务帧 ──"，因为没有业务数据
                if meta_rows and meta_rows[-1][0].startswith("── 业务帧"):
                    meta_rows = meta_rows[:-1]
                meta_rows.append(
                    (
                        "── 业务帧 ──",
                        "",
                        "",
                        f"无业务数据（{ed_data_type[3:]}）",
                        business_offset,
                        business_offset,
                    )
                )
                table_data = meta_rows
                ed_wrap_name = (
                    "广西台体监控包装帧" if wrapper == "gx" else "PLC2.0监控包装帧"
                )
                summary = f"[ED:{ed_data_type[3:]}] {ed_wrap_name}"
                status = "成功"
            else:
                table_data = [("❌ 解析失败", "", "", "ED 监控帧格式错误", None, None)]
                summary = "ED 帧格式错误"
                status = "失败"
        else:
            # 帧前跨帧状态（详情按需要在同一状态下重放，否则分支判定不同）
            frame_ctx = capture_cross_frame_state(parser, protocol_index)
            # 调用 parse_to_table 生成表格数据（parser 实例由调用方自建）
            table_data = parser.parse_to_table(frame_bytes)

            # 从表格数据生成摘要
            summary = summary_fn(table_data, protocol_index)
            # ED 监控帧数据来源标记
            if ed_data_type:
                summary = f"[ED:{ed_data_type}] {summary}"

            # 检查解析是否失败（校验错误、长度不匹配、未产出任何字段）
            # 空表 = 解析器没有产出字段 → 失败；❌ 行可能写在表中途
            # （如 csg_new_gen_parser.py:754），必须全表扫描
            is_parse_failed = (not table_data) or any(
                str(item[0]).startswith("❌") for item in table_data if item
            )
            if is_parse_failed:
                status = "失败"
                # 提取失败原因作为摘要
                summary = "解析无结果（未产出字段）" if not table_data else summary
                for item in table_data:
                    if item and str(item[0]).startswith("❌"):
                        summary = item[3] if item[3] else "解析失败"
                        break
            else:
                status = "成功"

        # 保存结果（表格数据供详情查看；_type_name 供「按类型全选」）
        proto_type = type_name_fn(table_data, status, protocol_index)
        record = {
            "_input": frame_hex,
            "_status": status,
            "_table_data": table_data,
            "_has_detail": bool(table_data),
            "_ed_type": ed_data_type,
            "_type_name": proto_type,
            "_src_line": src_line,
            "摘要": summary,
        }
        if frame_ctx is not None:
            # 仅在帧前跨帧状态非默认时锁存（详情按需重解析靠它复现同一分支）
            record["_ctx"] = frame_ctx
        return record

    except Exception as e:  # noqa: BLE001 —— 单帧异常隔离，不中断整批
        return {
            "_input": frame_hex,
            "_status": "异常",
            # 必须给值：否则表格填充回落到上一帧的 _type_name
            "_type_name": "异常",
            "_src_line": src_line,
            "_has_detail": False,
            "_ed_type": "",
            "错误": str(e),
            "摘要": str(e)[:50],
        }


class BatchParseWorker(QThread):
    """批量解析工作线程：逐帧 ``parse_to_table`` + 摘要，攒批回传 UI。

    信号：
        progress(done, total, ok, fail, batch)  每 200 帧一批（done=已处理帧数）
        finished_ok(ok, fail)                    全部完成
        cancelled(ok, fail)                      用户取消（已完成部分保留）
        failed(msg)                              不可恢复错误（如 parser 构建失败）
    """

    # 信号：done, total, ok, fail, 本批结果
    progress = Signal(int, int, int, int, list)
    finished_ok = Signal(int, int)
    cancelled = Signal(int, int)
    failed = Signal(str)

    def __init__(
        self,
        frames: Sequence,
        *,
        protocol_index: int,
        parse_level: str | None = None,
        frame_type: Any = None,
        channel: str = "plc",
        lead_lines: int = 0,
        strip_map: list[int] | None = None,
        summary_fn: Callable,
        type_name_fn: Callable,
        ed_parse_fn: Callable,
        log_fn: Callable | None = None,
        chunk_size: int = CHUNK_SIZE,
        parent=None,
    ):
        """
        Args:
            frames: ``_extract_frames_for_protocol`` 的输出（元素为 hex 串或
                ``(hex, ed_type, line_no)`` 元组）
            protocol_index: 协议索引快照
            parse_level / frame_type / channel: 解析级别参数快照
            lead_lines: 首部空白行偏移（``MainWindow._batch_lead_lines``）
            strip_map: 前缀剥离行映射（``MainWindow._last_strip_line_map``），
                可为 None（无映射时直接用原始行号）
            summary_fn: 必填，``(table_data, protocol_index) -> str``
                （即 ``MainWindow._get_summary_from_table_data``）
            type_name_fn: 必填，``(table_data, status, protocol_index) -> str``
                （即 ``MainWindow._get_frame_type_name``）
            ed_parse_fn: 必填，``(frame_bytes) -> (wrapper, rows, business, offset)``
                协议9 ED 监控包装帧解析（widget-free 闭包）；非协议9 不会被调用
            log_fn: 可选调试日志回调（沿用主窗口 ``_debug_log``，仅前 5 帧）
            chunk_size: 分片粒度
        """
        super().__init__(parent)
        # 登记后关闭兜底回收（_shutdown_threads）才能覆盖本线程
        thread_registry.track(self, "批量解析")

        self._frames = list(frames)
        self._protocol_index = protocol_index
        self._parse_level = parse_level
        self._frame_type = frame_type
        self._channel = channel
        self._lead_lines = lead_lines
        self._strip_map = strip_map
        self._summary_fn = summary_fn
        self._type_name_fn = type_name_fn
        self._ed_parse_fn = ed_parse_fn
        self._log_fn = log_fn
        self._chunk_size = (
            chunk_size if isinstance(chunk_size, int) and chunk_size > 0 else CHUNK_SIZE
        )

        self._is_cancelled = False
        self._parser: Any = None
        # 背压回执：UI 消费完一批后 set，worker 才继续下一片
        self._ack = threading.Event()

    # ──────────────────────────── 控制 ────────────────────────────

    def cancel(self):
        """请求取消：下一分片边界（≤ chunk_size 帧）返回，已完成结果照常回传。"""
        self._is_cancelled = True
        self._ack.set()  # 解除背压等待，立即复检取消标志

    def ack(self):
        """UI 已消费当前批次（由 `_on_batch_progress` 调用）：解除背压。"""
        self._ack.set()

    @property
    def total(self) -> int:
        """总帧数（供 UI 显示进度分母）"""
        return len(self._frames)

    # ──────────────────────────── 解析器 ────────────────────────────

    def _build_parser(self):
        """自建解析器实例（不复用共享单例，见模块 docstring 的线程安全说明）"""
        spec = protocol_registry.get_protocol(self._protocol_index)
        base = parser_registry.get_parser_class(spec.parser_key)()
        return protocol_registry.build_gui_parser(
            self._protocol_index,
            base,
            parse_level=self._parse_level,
            frame_type=self._frame_type,
            channel=self._channel,
        )

    # ──────────────────────────── 单帧 ────────────────────────────

    def _parse_one(self, index: int, frame_item) -> dict:
        """单帧解析（薄封装）：复用模块级 :func:`parse_one_frame`。

        步骤 3 起不再常驻 ``_table_data``（49,532 帧 ≈ 229 MB → 约 4 MB）：
        详情/导出改用 ``_has_detail`` + 锁存的 ``_input`` 按需重解析
        （``main_gui._get_frame_table_data``），两者共用同一份分支逻辑。
        """
        record = parse_one_frame(
            frame_item,
            index,
            protocol_index=self._protocol_index,
            parser=self._parser,
            summary_fn=self._summary_fn,
            type_name_fn=self._type_name_fn,
            ed_parse_fn=self._ed_parse_fn,
            lead_lines=self._lead_lines,
            strip_map=self._strip_map,
            log_fn=self._log_fn,
        )
        record.pop("_table_data", None)
        return record

    # ──────────────────────────── 主循环 ────────────────────────────

    def run(self):  # noqa: D102 —— QThread 入口
        try:
            self._parser = self._build_parser()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"构建解析器失败：{e}")
            return

        total = len(self._frames)
        ok = 0
        fail = 0
        done = 0
        batch: list = []

        for index, frame_item in enumerate(self._frames):
            if self._is_cancelled:
                return self._emit_cancelled(ok, fail, batch, done, total)
            try:
                result = self._parse_one(index, frame_item)
            except Exception as e:  # noqa: BLE001 —— _parse_one 已兜底，双保险
                result = {
                    "_input": "",
                    "_status": "异常",
                    "_type_name": "异常",
                    "_src_line": -1,
                    "_has_detail": False,
                    "_ed_type": "",
                    "错误": str(e),
                    "摘要": str(e)[:50],
                }
            if result.get("_status") == "成功":
                ok += 1
            else:
                fail += 1
            batch.append(result)
            done = index + 1

            if len(batch) >= self._chunk_size:
                # emit 后本线程不再引用该 list（避免两侧同时改同一对象）
                self._ack.clear()
                self.progress.emit(done, total, ok, fail, batch)
                batch = []
                # 背压：等 UI 消费完再继续，队列不会积压大量回填任务
                self._ack.wait(ACK_TIMEOUT)
                if self._is_cancelled:
                    return self._emit_cancelled(ok, fail, batch, done, total)

        if batch:
            self.progress.emit(done, total, ok, fail, batch)
            batch = []
        if self._is_cancelled:
            return self._emit_cancelled(ok, fail, batch, done, total)
        self.finished_ok.emit(ok, fail)

    def _emit_cancelled(self, ok: int, fail: int, batch: list, done: int, total: int):
        """取消收尾：先回传「未满一片」的结果，再发 `cancelled`。

        逐帧解析是本线程的主要耗时，取消因此常落在**分片中途**（`_is_cancelled`
        在每帧循环顶检查，命中时 `batch` 里已有若干帧结果）。若直接丢弃：
          - UI 实际持有的结果数 < `cancelled(ok, fail)` 的计数 → 状态栏
            「已取消 — 已解析 N / M 帧」不诚实（N 大于表格行数）；
          - 已解析结果白解析，违背 R2「取消后已解析部分保留且可用」。

        刻意**不**等 UI 回执（`self._ack.wait`）：取消必须在验收线（1 s）内返回；
        本方法返回后线程即结束，不会再积压大量分片。
        """
        if batch:
            self.progress.emit(done, total, ok, fail, batch)
        self.cancelled.emit(ok, fail)


__all__ = [
    "BatchParseWorker",
    "parse_one_frame",
    "apply_cross_frame_state",
    "capture_cross_frame_state",
    "resolve_ed_wrapper",
    "CHUNK_SIZE",
    "ACK_TIMEOUT",
]
