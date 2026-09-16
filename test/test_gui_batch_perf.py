"""批量解析后台化回归测试（任务 09-15-gui-batch-parse-perf）

覆盖**步骤 1（解耦）+ 步骤 2（后台解析 / 进度 / 取消）**的不变量：

  [1] worker 纯逻辑（假 parser 驱动）——分片进度序列 / 取消落在分片中途 /
      单帧异常隔离 / 空表与 ❌ 判失败 / 构建解析器失败走 failed
  [2] `_current_parse_params` —— 12 个协议索引的参数快照（不读 widget）
  [3] `resolve_ed_wrapper` —— 单一来源判别，广西台体 gx 帧不退化成 plc2
  [4] 端到端（完成路径）—— 进度次数与单调性、末次 done == total、
      表格行数 == 结果集长度
  [5] 端到端（取消路径）—— 取消耗时 < 1 s、Σ回传条数 == 结果集 == 表格行数
      （「取消丢掉未满一片」是本任务复核修掉的缺陷，这里钉死回归）
  [6] UI 响应性 —— 解析期间事件循环仍在跑（心跳计数）

步骤 3（详情按需 / `_has_detail` / `_ctx`）、步骤 4（过滤对拍 / 去抖），
以及步骤 5 余项（内存 < 40 MB / 导出字段）随各自步骤追加。

运行: QT_QPA_PLATFORM=offscreen python -u test/test_gui_batch_perf.py
（必须带 `-u`：脚本末尾 `os._exit()` 不会 flush 缓冲的 stdout）
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import sys
import time
from contextlib import contextmanager
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

# 构造 MainWindow 之前必须屏蔽模态框，否则 offscreen 下永久阻塞
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

from _batch_wait import wait_batch  # noqa: E402

app = QApplication.instance() or QApplication([])

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n{title}")


def pump(ms=5):
    """交给事件循环 ms 毫秒（等待而不忙等；比 sleep 更贴近真实 GUI 时序）。"""
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, ms)


def pump_until(pred, timeout=30.0):
    """泵事件循环直到 pred() 为真；返回是否在超时前满足。"""
    deadline = time.monotonic() + timeout
    while not pred():
        pump()
        if time.monotonic() > deadline:
            return False
    return True


# ══════════════════════════════════════════════════════════════
# [1] worker 纯逻辑（不建 MainWindow，不碰任何 widget）
# ══════════════════════════════════════════════════════════════


class FakeParser:
    """`parse_to_table` 行为可编程的假解析器。"""

    def __init__(self, rows=None, raises_at=None):
        self.rows = (
            rows if rows is not None else [("名称", "00", "0", "说明", None, None)]
        )
        self.raises_at = raises_at or set()  # 1-based 调用序号 → 抛异常
        self.calls = 0

    def parse_to_table(self, frame_bytes, **kw):
        self.calls += 1
        if self.calls in self.raises_at:
            raise ValueError(f"模拟第 {self.calls} 帧解析异常")
        return list(self.rows)


def make_worker(frames, parser, chunk_size=200, **kw):
    """构造 worker 并注入假解析器（绕开真实 parser 的构建）。

    parser 为 None 时让 `_build_parser` 抛异常（测 failed 路径）。
    """
    import batch_parse_worker as bpw

    def build_ok():
        return parser

    def build_boom():
        raise RuntimeError("构建解析器失败：模拟")

    w = bpw.BatchParseWorker(
        frames,
        protocol_index=kw.pop("protocol_index", 9),
        summary_fn=kw.pop("summary_fn", lambda td, p: "摘要"),
        type_name_fn=kw.pop("type_name_fn", lambda td, s, p: f"类型:{s}"),
        ed_parse_fn=kw.pop("ed_parse_fn", lambda b: (None, None, None, 0)),
        chunk_size=chunk_size,
        **kw,
    )
    w._build_parser = build_boom if parser is None else build_ok
    return w


class SignalTap:
    """在 worker **构造瞬间**挂上监听（否则第一片可能在挂载前就已发出）。

    用 DirectConnection：槽在发出信号的那个线程内同步执行，无需事件循环。
    注意：必须先进入本上下文、再构造 worker —— 推荐直接用 `tapped_worker()`。
    """

    def __enter__(self):
        import batch_parse_worker as bpw

        self.progress = []  # (done, ok, fail, 本批条数)
        self.batches = []  # 每批结果列表（供逐条断言）
        self.finished = []
        self.cancelled = []
        self.failed = []
        self.parsed: dict[str, int] | None = None  # cancel_at 模式下：实际解析帧数
        self._orig = bpw.BatchParseWorker.__init__

        def patched(inst, *a, **k):
            self._orig(inst, *a, **k)
            inst.progress.connect(self._on_progress, Qt.ConnectionType.DirectConnection)
            inst.finished_ok.connect(
                lambda o, f: self.finished.append((o, f)),
                Qt.ConnectionType.DirectConnection,
            )
            inst.cancelled.connect(
                lambda o, f: self.cancelled.append((o, f)),
                Qt.ConnectionType.DirectConnection,
            )
            inst.failed.connect(
                lambda m: self.failed.append(m), Qt.ConnectionType.DirectConnection
            )

        setattr(bpw.BatchParseWorker, "__init__", patched)  # noqa: B010 —— 测试有意打桩
        return self

    def _on_progress(self, done, total, ok, fail, batch):
        self.progress.append((done, ok, fail, len(batch)))
        self.batches.append(batch)

    def __exit__(self, *exc):
        import batch_parse_worker as bpw

        setattr(bpw.BatchParseWorker, "__init__", self._orig)  # noqa: B010
        return False

    @property
    def dones(self):
        return [p[0] for p in self.progress]

    @property
    def delivered(self):
        return sum(p[3] for p in self.progress)

    @property
    def results(self):
        """所有回传帧的结果记录（按回传顺序展平）。"""
        return [r for batch in self.batches for r in batch]


@contextmanager
def tapped_worker(frames, parser, chunk_size=200, cancel_at=None, **kw):
    """构造带监听的 worker，yield `(worker, tap)`。

    **worker 必须在 tap 生效之后才构造**——挂在 `with` 之前会漏掉第一片。
    `cancel_at=N`：在第 N 帧调用 `cancel()`（用于制造「分片中途取消」）。
    """
    with SignalTap() as tap:
        w = make_worker(frames, parser, chunk_size=chunk_size, **kw)
        if cancel_at is not None:
            state = {"n": 0}
            tap.parsed = state
            real = w._parse_one

            def counting(index, frame_item):
                state["n"] += 1
                if state["n"] == cancel_at:
                    w.cancel()
                return real(index, frame_item)

            w._parse_one = counting
        yield w, tap


def frames_of(n):
    """worker 输入元素：`(hex, ed_type, src_line)`（与提取器输出同形）。

    ed_type 必须是**字符串**（提取器对非 ED 帧给 `""`、对 ED 帧给 `"ED:xxx"`）；
    给非字符串会在协议 9 分支触发 `ed_data_type.startswith(...)` 抛错。
    """
    return [("AA" + "00" * 20, "", i) for i in range(n)]


def test_worker_chunked_progress():
    section("[1] worker 纯逻辑：分片进度序列 + 完成路径")
    with tapped_worker(frames_of(1000), FakeParser()) as (w, tap):
        w.run()

    check(
        "1000 帧按 200 分片 → 5 次进度",
        tap.dones == [200, 400, 600, 800, 1000],
        f"dones={tap.dones}",
    )
    check(
        "done 严格单调递增",
        all(a < b for a, b in zip(tap.dones, tap.dones[1:])),
        f"dones={tap.dones}",
    )
    check("末次 done == total", tap.dones[-1] == 1000)
    check("Σ回传条数 == 总帧数", tap.delivered == 1000, f"Σ={tap.delivered}")
    check(
        "完成信号 finished_ok(1000, 0)", tap.finished == [(1000, 0)], f"{tap.finished}"
    )
    check("完成路径不发 cancelled", not tap.cancelled)


def test_worker_cancel_mid_chunk():
    section("[1] worker 纯逻辑：取消落在分片中途（未满一片不得丢弃）")
    # 450 帧 / 分片 200：第 1 片 200 帧回传后 batch 重置，第 250 帧取消 ⇒ 未满一片 50 帧
    with tapped_worker(frames_of(450), FakeParser(), cancel_at=250) as (w, tap):
        w.run()
    n_parsed = tap.parsed["n"] if tap.parsed else -1
    sizes = [p[3] for p in tap.progress]
    counted = tap.cancelled[0][0] + tap.cancelled[0][1] if tap.cancelled else None

    check("命中「分片中途取消」：批次 [200, 50]", sizes == [200, 50], f"批次={sizes}")
    check(
        "cancelled 计数 == 实际回传条数（未满一片不丢）",
        counted == tap.delivered,
        f"cancelled={counted} 回传={tap.delivered}",
    )
    check(
        "cancelled 计数 == 实际解析帧数",
        counted == n_parsed,
        f"cancelled={counted} 解析={n_parsed}",
    )
    check("取消路径不发 finished_ok", not tap.finished)
    check("取消路径正好发一次 cancelled", len(tap.cancelled) == 1, f"{tap.cancelled}")


def test_worker_exception_isolation():
    section("[1] worker 纯逻辑：单帧异常隔离")
    with tapped_worker(frames_of(5), FakeParser(raises_at={3})) as (w, tap):
        w.run()

    check(
        "异常帧不影响后续帧：计数 ok=4 fail=1",
        tap.finished == [(4, 1)],
        f"{tap.finished}",
    )
    check("5 帧全部产出结果", len(tap.results) == 5, f"n={len(tap.results)}")

    bad = tap.results[2]  # 第 3 帧（1-based 第 3 次 parse_to_table）抛出
    check(
        "异常帧 _status == '异常'",
        bad.get("_status") == "异常",
        f"{bad.get('_status')}",
    )
    check(
        "异常帧 _type_name == '异常'（不得回落到上一帧类型）",
        bad.get("_type_name") == "异常",
        f"{bad.get('_type_name')}",
    )
    check("异常帧带 错误 字段", bool(bad.get("错误")), f"{bad.get('错误')!r}")
    check("异常帧 _src_line 保留", bad.get("_src_line") == 2, f"{bad.get('_src_line')}")
    check("后续帧照常成功", tap.results[3].get("_status") == "成功")


def test_worker_failure_detection():
    section("[1] worker 纯逻辑：失败判定（空表 / 表中途 ❌）")
    cases = [
        ("空表 → 失败", FakeParser(rows=[]), "失败"),
        (
            "表中途 ❌ → 失败",
            FakeParser(
                rows=[
                    ("名称", "00", "0", "正常行", None, None),
                    ("❌ 解析失败", "", "", "长度不匹配", None, None),
                ]
            ),
            "失败",
        ),
        ("正常表 → 成功", FakeParser(), "成功"),
    ]
    for label, parser, want in cases:
        with tapped_worker(frames_of(1), parser) as (w, tap):
            w.run()
        got = tap.results[0].get("_status") if tap.results else "(无结果)"
        check(label, got == want, f"得到 {got}")


def test_worker_build_parser_fails():
    section("[1] worker 纯逻辑：构建解析器失败走 failed（不冒泡）")
    with tapped_worker(frames_of(1), None) as (w, tap):
        w.run()
    check(
        "failed 信号携带原因",
        bool(tap.failed) and "构建解析器失败" in tap.failed[0],
        f"{tap.failed!r}",
    )
    check("不发 finished_ok", not tap.finished)
    check("不发 progress", not tap.progress)
    check("不发 cancelled", not tap.cancelled)


# ══════════════════════════════════════════════════════════════
# [3] 无需 MainWindow 的契约
# ══════════════════════════════════════════════════════════════


def test_resolve_ed_wrapper_single_source():
    section("[3] resolve_ed_wrapper：单一来源判别（手动档直通 / auto 逐帧打分）")
    from test_ed_gx_wrapper import _build_gx_frame, _build_plc2_frame

    from batch_parse_worker import resolve_ed_wrapper

    business = bytes.fromhex("09012000041B03001606000020D6B62500000000")
    gx = _build_gx_frame(business)
    plc2 = _build_plc2_frame(business)

    check("手动 plc2 直通", resolve_ed_wrapper(gx, "plc2") == "plc2")
    check("手动 gx 直通", resolve_ed_wrapper(plc2, "gx") == "gx")
    check(
        "auto 识别 gx",
        resolve_ed_wrapper(gx, "auto") == "gx",
        "广西台体帧不得退化成 plc2",
    )
    check("auto 识别 plc2", resolve_ed_wrapper(plc2, "auto") == "plc2")
    check("非法 mode 回落 auto 识别", resolve_ed_wrapper(gx, "不存在的档") == "gx")


# ══════════════════════════════════════════════════════════════
# [2][4][5][6] 端到端（真实 MainWindow）
# ══════════════════════════════════════════════════════════════


def make_window():
    from main_gui import MainWindow

    win = MainWindow()
    win.current_protocol = 9
    # 自动识别信道，避免本机配置残留为 HRF 影响 PLC 用例
    win.csg_channel_combo.setCurrentIndex(0)
    pump(0)
    return win


def test_current_parse_params_all_protocols():
    section("[2] _current_parse_params：12 个协议索引的参数快照")
    import protocol_registry as pr

    win = make_window()
    keys = {"index", "parse_level", "frame_type", "channel"}
    bad = []
    for spec in pr._PROTOS:
        try:
            params = win._current_parse_params(spec.index)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{spec.index}:{exc}")
            continue
        if set(params) != keys:
            bad.append(f"{spec.index}:键集={sorted(params)}")
        elif params["index"] != spec.index:
            bad.append(f"{spec.index}:index={params['index']}")
        elif params["channel"] is None:
            bad.append(f"{spec.index}:channel 为 None（worker 会原样下发）")
    check("12 个协议均返回合法参数快照", not bad, f"异常项={bad}")

    none_family = [s.index for s in pr._PROTOS if not s.parse_level_family]
    check(
        "无解析级别族的协议 parse_level 为 None",
        all(win._current_parse_params(i)["parse_level"] is None for i in none_family),
        f"协议={none_family}",
    )

    # 单源：改状态属性后快照必须跟随（证明不是各自去读 widget）
    win._csg_parse_level = "fc_only"
    got_level = win._current_parse_params(9)["parse_level"]
    win._csg_parse_level = "auto"
    check(
        "_csg_parse_level 改动被快照跟随（单源）",
        got_level == "fc_only",
        f"{got_level}",
    )

    built_fail = []
    for spec in pr._PROTOS:
        try:
            if win._get_current_parser(spec.index) is None:
                built_fail.append(spec.index)
        except Exception as exc:  # noqa: BLE001
            built_fail.append(f"{spec.index}:{exc}")
    check(
        "12 个协议的 _get_current_parser 均可构建", not built_fail, f"失败={built_fail}"
    )
    win.close()


def test_end_to_end_finish_path():
    section("[4] 端到端（完成路径）：进度 / 行数")
    win = make_window()
    frame = "09" + "00" * 19  # 40 hex，低半字节 9 ⇒ 可被协议 9 提取
    n = 1200
    win.batch_input.setPlainText("\n".join([frame] * n))
    pump(0)

    with SignalTap() as tap:
        win.parse_batch()  # 立即返回（预处理同步 + worker 后台）
        started = win._batch_worker is not None
        finished = wait_batch(win, timeout=60.0)
        pump(0)

    check("parse_batch 立即返回并启动 worker", started)
    check("worker 在超时前收尾", finished)
    check("进度至少 2 次", len(tap.progress) >= 2, f"次数={len(tap.progress)}")
    check(
        "done 单调不减",
        all(a <= b for a, b in zip(tap.dones, tap.dones[1:])),
        f"dones={tap.dones[:8]}",
    )
    check(
        "末次 done == total",
        tap.dones and tap.dones[-1] == n,
        f"last={tap.dones[-1:]} n={n}",
    )
    check(
        "表格行数 == 结果集长度",
        win.batch_summary_table.rowCount() == len(win.batch_results),
        f"行={win.batch_summary_table.rowCount()} 结果={len(win.batch_results)}",
    )
    check(
        "结果集长度 == 总帧数", len(win.batch_results) == n, f"{len(win.batch_results)}"
    )
    check(
        "完成信号 ok+fail == 总帧数",
        tap.finished and sum(tap.finished[0]) == n,
        f"{tap.finished}",
    )
    check("worker 已收起", win._batch_worker is None)
    win.close()


def test_end_to_end_cancel_path():
    section("[5] 端到端（取消路径）：< 1 s + 三量一致 + UI 心跳")
    win = make_window()
    frame = "09" + "00" * 19
    n = 20000
    win.batch_input.setPlainText("\n".join([frame] * n))
    pump(0)

    # 心跳：事件循环若被阻塞，ticks 不会增长（同步实现下甚至走不到这个循环）
    tick_times: list[float] = []
    timer = QTimer()
    timer.setInterval(0)
    timer.timeout.connect(lambda: tick_times.append(time.monotonic()))
    timer.start()

    with SignalTap() as tap:
        win.parse_batch()
        # 跑一会儿让 worker 进入分片循环（含背压往返）
        deadline = time.monotonic() + 0.6
        while time.monotonic() < deadline and win._batch_worker is not None:
            pump(2)
        ticks_during = len(tick_times)
        max_gap_ms = (
            max((b - a) * 1000 for a, b in zip(tick_times, tick_times[1:]))
            if len(tick_times) > 1
            else 0.0
        )

        t1 = time.monotonic()
        if win._batch_worker is not None:
            win._cancel_batch_parse()
        stopped = pump_until(lambda: win._batch_worker is None, timeout=5.0)
        cancel_ms = (time.monotonic() - t1) * 1000

    timer.stop()
    pump(0)

    final = len(win.batch_results)
    rows = win.batch_summary_table.rowCount()
    check(
        "解析中事件循环持续被驱动（心跳 ≥ 5；同步实现下根本走不到这里）",
        ticks_during >= 5,
        f"ticks={ticks_during}",
    )
    check(
        "解析中无长时间阻塞（相邻心跳间隔 ≤ 500 ms）",
        max_gap_ms <= 500,
        f"最大间隔={max_gap_ms:.1f} ms",
    )
    check("取消后 worker 已收起", stopped and win._batch_worker is None)
    check("取消耗时 < 1000 ms", cancel_ms < 1000, f"{cancel_ms:.1f} ms")
    check("取消后已解析结果保留（> 0）", final > 0, f"n={final}")
    check(
        "取消后 结果集长度 == 表格行数（状态栏诚实）",
        rows == final,
        f"行={rows} 结果={final}",
    )
    check(
        "Σ回传条数 == 结果集长度（未满一片不丢）",
        tap.delivered == final,
        f"Σ回传={tap.delivered} 结果={final}",
    )
    check(
        "进度 done 不超过总帧数",
        not tap.dones or max(tap.dones) <= n,
        f"max={max(tap.dones or [0])}",
    )
    check(
        "取消后结果不再常驻 _table_data（步骤 3 契约）",
        all("_table_data" not in r for r in win.batch_results),
    )
    claimed = [i for i, r in enumerate(win.batch_results[:50]) if r.get("_has_detail")]
    check(
        "取消后已解析帧仍可取到详情（_has_detail 为真者必非空）",
        all(win._get_frame_table_data(i) for i in claimed),
        f"有详情的帧 {len(claimed)} 条",
    )
    win.close()


def test_worker_record_shape_step3():
    section(
        "[7] worker 记录形状（步骤 3）：去 _table_data，改 _has_detail/_ed_type/_ctx"
    )
    with tapped_worker(frames_of(2), FakeParser()) as (w, tap):
        w.run()
    rec = tap.results[0]
    check(
        "记录不含 _table_data（去缓存）", "_table_data" not in rec, f"键={sorted(rec)}"
    )
    check(
        "_has_detail 为 True（表非空）",
        rec.get("_has_detail") is True,
        f"{rec.get('_has_detail')}",
    )
    check(
        "_ed_type 为 ''（非 ED 帧）",
        rec.get("_ed_type") == "",
        f"{rec.get('_ed_type')!r}",
    )
    check("_ctx 未锁存（无跨帧状态）", "_ctx" not in rec)
    check(
        "原有键仍齐备",
        {"_input", "_status", "_type_name", "_src_line", "摘要"} <= set(rec),
        f"键={sorted(rec)}",
    )

    with tapped_worker(frames_of(1), FakeParser(rows=[])) as (w2, tap2):
        w2.run()
    rec2 = tap2.results[0]
    check(
        "空表：_status=失败 且 _has_detail=False",
        rec2.get("_status") == "失败" and rec2.get("_has_detail") is False,
        f"{rec2.get('_status')}/{rec2.get('_has_detail')}",
    )

    with tapped_worker(
        frames_of(1),
        FakeParser(rows=[("❌ 解析失败", "", "", "长度不匹配", None, None)]),
    ) as (w3, tap3):
        w3.run()
    rec3 = tap3.results[0]
    check(
        "失败帧带 ❌ 行 → _has_detail=True（详情/导出原本就展示该 ❌ 行）",
        rec3.get("_status") == "失败" and rec3.get("_has_detail") is True,
        f"{rec3.get('_status')}/{rec3.get('_has_detail')}",
    )

    with tapped_worker(frames_of(1), FakeParser(raises_at={1})) as (w4, tap4):
        w4.run()
    rec4 = tap4.results[0]
    check(
        "异常帧：_has_detail=False 且 _ed_type=''",
        rec4.get("_has_detail") is False and rec4.get("_ed_type") == "",
        f"{rec4.get('_has_detail')}/{rec4.get('_ed_type')!r}",
    )


def test_cross_frame_state_helpers():
    section("[7] 跨帧状态锁存：剥包装层 + 默认值写回（实测 934/49532 帧差异的修因）")
    import batch_parse_worker as bpw

    class _Inner:
        """模拟 CSGNewGenParser 的跨帧状态属性（真解析器在 `.parser` 上）"""

        def __init__(self):
            self._efc_symbol_count = 0
            self._ofdma_frame_type = -1
            self._ofdma_station_count = 0

    class _Wrapper:  # 模拟 protocol_registry.CSGGenGuiParser（真解析器在 .parser）
        def __init__(self):
            self.parser = _Inner()

    p = _Wrapper()
    check("协议9 默认值 → 不锁存（None）", bpw.capture_cross_frame_state(p, 9) is None)
    check("未登记协议 → 恒 None", bpw.capture_cross_frame_state(p, 0) is None)
    p.parser._efc_symbol_count = 1
    p.parser._ofdma_frame_type = 2
    p.parser._ofdma_station_count = 3
    check(
        "非默认值 → 锁存到**真解析器**上（不是包装对象）",
        bpw.capture_cross_frame_state(p, 9) == (1, 2, 3),
        f"{bpw.capture_cross_frame_state(p, 9)}",
    )
    bpw.apply_cross_frame_state(p, 9, None)
    check(
        "还原 None → 写回默认值（清掉实例残留历史）",
        (
            p.parser._efc_symbol_count,
            p.parser._ofdma_frame_type,
            p.parser._ofdma_station_count,
        )
        == (0, -1, 0),
    )
    bpw.apply_cross_frame_state(p, 9, (1, 2, 3))
    check(
        "还原快照 → 三个属性均复原",
        (
            p.parser._efc_symbol_count,
            p.parser._ofdma_frame_type,
            p.parser._ofdma_station_count,
        )
        == (1, 2, 3),
    )
    check(
        "未登记协议不写属性",
        bpw.apply_cross_frame_state(p, 0, None) is None
        and p.parser._ofdma_frame_type == 2,
    )


def test_detail_on_demand_mainwindow():
    section("[7] 详情按需：LRU 命中/淘汰、失败帧、越界、不留 _table_data")
    win = make_window()
    frame = "09" + "00" * 19
    win.batch_input.setPlainText("\n".join([frame] * 3))
    pump(0)
    win.parse_batch()
    wait_batch(win)
    check(
        "结果集不含 _table_data", all("_table_data" not in r for r in win.batch_results)
    )
    check("结果集长度 = 3", len(win.batch_results) == 3, f"{len(win.batch_results)}")

    td0 = win._get_frame_table_data(0)
    check("首次取详情非空（冷帧重解析）", bool(td0), f"行数={len(td0)}")
    check("首次取详情写入 LRU", 0 in win._detail_cache, f"{list(win._detail_cache)}")
    check(
        "再次取详情命中 LRU（同一对象，不再重解析）",
        win._get_frame_table_data(0) is td0,
    )

    win._detail_cache_max = 1
    win._get_frame_table_data(1)
    check(
        "LRU 超上限淘汰最旧（只留最后访问）",
        list(win._detail_cache) == [1],
        f"{list(win._detail_cache)}",
    )
    win._detail_cache.clear()
    win._detail_cache_max = 50

    win.batch_results.append(
        {"_input": "ED0102", "_status": "失败", "_has_detail": False, "_ed_type": ""}
    )
    idx = len(win.batch_results) - 1
    check("无详情帧（_has_detail=False）返回 []", win._get_frame_table_data(idx) == [])
    check("越界下标返回 []", win._get_frame_table_data(10**6) == [])
    check("负下标返回 []", win._get_frame_table_data(-1) == [])

    run = win._batch_detail_resolver()
    check("resolver：本结果集的 dict → 命中同一详情", run(win.batch_results[0]) == td0)
    row = ("a", "b", "c", "d", None, None)
    check(
        "resolver：集外 dict（测试自造）回落自带 _table_data",
        run({"_table_data": [row]}) == [row],
    )
    win.close()


def test_detail_matches_sequential_parse():
    section("[7] 对拍：详情重解析 == 批量顺序解析（ED plc2/gx + ED 失败帧 + 普通帧）")
    from test_ed_gx_wrapper import _build_gx_frame, _build_plc2_frame

    business = bytes.fromhex("09012000041B03001606000020D6B62500000000")
    # ED 开头但内部声明长度与实际不符 → 提取失败 → ❌ 失败帧
    # （与 test_ed_fallback_fix.py 的 USER_FRAME_HEX 同构）
    bad_ed = (
        "ED25020002EF01D538877E0100080209012000041B"
        "03001606000020D6B62500000000" + "FF" * 100
    )
    lines = [
        "09" + "00" * 19,  # 普通 hex 帧
        _build_plc2_frame(business).hex().upper(),  # PLC2.0 ED 包装（有业务数据）
        _build_gx_frame(business).hex().upper(),  # 广西台体 ED 包装（有业务数据）
        bad_ed,  # ED 开头但提取失败 → 失败帧（带 ❌ 行）
    ]
    win = make_window()
    win.batch_input.setPlainText("\n".join(lines))
    pump(0)
    # `_prepare_batch_input` 在无有效输入/未提取到帧时返回 None（已弹告警）
    prepared = win._prepare_batch_input()
    if prepared is None:
        check("预处理成功（前置条件）", False, "_prepare_batch_input 返回 None")
        win.close()
        return
    frames, params = prepared
    check(
        "提取到多帧（含 ED）",
        len(frames) >= 4,
        f"{len(frames)}",
    )

    # 参照：与批量解析同参、顺序喂入一个**独立**自建解析器
    # （= 改动前批量缓存的 _table_data；刻意不复用详情路径那个实例，
    # 以免「参照与待测共用同一实例」把状态差异掩盖掉）
    import batch_parse_worker as bpw
    import protocol_registry
    from parser_registry import get_parser_class

    _spec = protocol_registry.get_protocol(params["index"])
    ref_parser = protocol_registry.build_gui_parser(
        params["index"],
        get_parser_class(_spec.parser_key)(),
        parse_level=params["parse_level"],
        frame_type=params["frame_type"],
        channel=params["channel"],
    )
    ref = []
    for i, item in enumerate(frames):
        ref.append(
            bpw.parse_one_frame(
                item,
                i,
                protocol_index=params["index"],
                parser=ref_parser,
                summary_fn=win._get_summary_from_table_data,
                type_name_fn=win._get_frame_type_name,
                ed_parse_fn=win._batch_ed_parser(win._ed_wrapper_mode()),
                lead_lines=0,
                strip_map=None,
            )["_table_data"]
        )

    win.parse_batch()
    wait_batch(win)
    check(
        "批量结果条数 = 提取帧数",
        len(win.batch_results) == len(frames),
        f"{len(win.batch_results)} vs {len(frames)}",
    )
    bad = []
    for i in range(min(len(frames), len(win.batch_results))):
        if win._get_frame_table_data(i) != ref[i]:
            bad.append(i)
    check(
        "逐帧详情与批量顺序解析逐字段相同（含 ED plc2/gx 与 ❌ 失败行）",
        not bad,
        f"不一致={bad}",
    )
    statuses = [r.get("_status") for r in win.batch_results]
    check("含失败帧（❌ 行）样本", "失败" in statuses, f"状态={statuses}")
    win.close()


def test_export_has_detail_column():
    section("[7] 导出：「包含表格数据」列语义与改动前一致 + resolver 生效")
    import tempfile

    from enhanced_export import EnhancedBatchResultExporter

    win = make_window()
    frame = "09" + "00" * 19
    win.batch_input.setPlainText("\n".join([frame] * 4))
    pump(0)
    win.parse_batch()
    wait_batch(win)
    check("结果非空", bool(win.batch_results), f"{len(win.batch_results)}")

    with tempfile.TemporaryDirectory() as d:
        exp = EnhancedBatchResultExporter(d)
        # 注意：默认文件名只到秒 → 两次导出必须显式指定不同 output_file，
        # 否则同秒会被覆盖（本用例曾因此把 resolvor 版当成无 resolver 版断言）
        p_no_resolver = exp.export_to_json(
            list(win.batch_results),
            "csg",
            output_file=os.path.join(d, "no_resolver.json"),
        )
        p_resolver = exp.export_to_json(
            win.batch_results,
            "csg",
            output_file=os.path.join(d, "with_resolver.json"),
            table_data_resolver=win._batch_detail_resolver(),
        )
        with open(p_no_resolver, encoding="utf-8") as f:
            rows_no = json.load(f)["results"]
        with open(p_resolver, encoding="utf-8") as f:
            rows_yes = json.load(f)["results"]

    # resolver=None = 旧逐字行为（记录里没 _table_data → 「否」），兼容契约
    check(
        "resolver=None：无 _table_data 记录 → 「否」（向后兼容不变）",
        all(r["包含表格数据"] == "否" for r in rows_no),
        f"{[r['包含表格数据'] for r in rows_no]}",
    )
    want = ["是" if r.get("_has_detail") else "否" for r in win.batch_results]
    check(
        "注入 resolver：「包含表格数据」与 _has_detail 逐帧一致",
        [r["包含表格数据"] for r in rows_yes] == want,
        f"{[r['包含表格数据'] for r in rows_yes]} vs {want}",
    )
    check("成功帧全为「是」（不得整列变「否」）", "是" in want, f"{want}")
    win.close()


def _select_status(win, status):
    """按下拉项 data 选择状态过滤（不依赖索引顺序）。"""
    for i in range(win.batch_status_filter.count()):
        if win.batch_status_filter.itemData(i) == status:
            win.batch_status_filter.setCurrentIndex(i)
            return
    raise AssertionError(f"状态下拉缺少 {status!r}")


def _visible_rows(win):
    table = win.batch_summary_table
    return [r for r in range(table.rowCount()) if not table.isRowHidden(r)]


def _filter_oracle(win, keyword: str, status_filter: str) -> list[int]:
    """过滤契约的**独立实现**（据需求写出，不是拷产品代码），返回应可见行号。

    状态：success→成功 / fail→失败 / error→异常 / all→全过；
    关键词（已小写）匹配「摘要」或第 3 列文本或 `_input`。
    """
    table = win.batch_summary_table
    want_status = {"success": "成功", "fail": "失败", "error": "异常"}.get(
        status_filter
    )
    kw = keyword.strip().lower()
    rows = []
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is None:
            continue
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(win.batch_results):
            continue
        r = win.batch_results[idx]
        if want_status is not None and r.get("_status", "") != want_status:
            continue
        if kw:
            proto_item = table.item(row, 3)
            proto = proto_item.text().lower() if proto_item else ""
            if not (
                kw in str(r.get("摘要", "")).lower()
                or kw in proto
                or kw in str(r.get("_input", "")).lower()
            ):
                continue
        rows.append(row)
    return rows


def test_filter_matches_oracle_and_fast():
    section("[7] 过滤：结果集合对拍（独立实现）+ 单次耗时 + 去抖")
    from test_csg_sequence_model import SOF_DOWN

    win = make_window()
    # 混合状态：全 0 帧（多为失败/异常）+ 真实 SOF 帧（成功）
    lines = ["09" + "00" * 19] * 2000 + [SOF_DOWN.hex().upper()] * 600
    win.batch_input.setPlainText("\n".join(lines))
    pump(0)
    win.parse_batch()
    if not wait_batch(win, timeout=120.0):
        check("批量解析完成（过滤用例前提）", False, "wait_batch 超时")
        win.close()
        return
    pump(0)
    total = win.batch_summary_table.rowCount()
    check("批量解析产出结果（过滤用例前提）", total > 0, f"行数={total}")
    if not total:
        win.close()
        return

    # 造出三种状态：否则全部成功的输入会让「只看失败/异常」变成 0==0 的无效断言
    # （只改夹具里的 `_status`；过滤实现与 oracle 读的是同一批 dict，对比仍然公平）
    for i, r in enumerate(win.batch_results):
        if i % 13 == 0:
            r["_status"] = "失败"
        elif i % 13 == 1:
            r["_status"] = "异常"
    n_fail = sum(1 for r in win.batch_results if r["_status"] == "失败")
    n_err = sum(1 for r in win.batch_results if r["_status"] == "异常")
    check(
        "夹具含三种状态（断言非平凡）",
        n_fail > 0 and n_err > 0,
        f"失败={n_fail} 异常={n_err} 成功={total - n_fail - n_err}",
    )

    cases = [
        ("all", "", "无过滤"),
        ("all", "9000", "关键词命中 HEX 前缀"),
        ("all", "绝不可能命中的字符串", "关键词全不命中"),
        ("fail", "", "只看失败"),
        ("error", "", "只看异常"),
        ("success", "", "只看成功"),
    ]
    for status, kw, label in cases:
        _select_status(win, status)
        win.batch_search_edit.setText(kw)
        win._on_batch_filter_changed()  # 绕过去抖，只断言最终态
        pump(0)
        got, want = _visible_rows(win), _filter_oracle(win, kw, status)
        check(
            f"过滤结果与契约一致（{label}）",
            got == want,
            f"实际 {len(got)} 行 / 期望 {len(want)} 行"
            + ("" if got == want else f"  差异前5={sorted(set(got) ^ set(want))[:5]}"),
        )

    # 最坏形态：无任何条件时全表重算
    _select_status(win, "all")
    win.batch_search_edit.setText("")
    t0 = time.monotonic()
    win._on_batch_filter_changed()
    dur = (time.monotonic() - t0) * 1000
    check(f"单次过滤 < 200 ms（{total} 行全表）", dur < 200, f"{dur:.1f} ms")

    # 去抖：仅关键词走去抖；状态下拉即时生效
    win._on_batch_filter_changed()
    baseline = len(_visible_rows(win))
    win.batch_search_edit.setText("绝不可能命中的字符串")
    check(
        "关键词去抖：改文本后立即尚未重算",
        len(_visible_rows(win)) == baseline,
        f"{len(_visible_rows(win))} vs {baseline}",
    )
    check("去抖计时器已启动", win._batch_filter_timer.isActive())
    pump_until(lambda: not win._batch_filter_timer.isActive(), timeout=5.0)
    pump(0)
    check(
        "关键词去抖：计时结束后已按新关键词过滤",
        len(_visible_rows(win)) == 0,
        f"可见 {len(_visible_rows(win))} 行",
    )

    win.batch_search_edit.setText("")
    pump_until(lambda: not win._batch_filter_timer.isActive(), timeout=5.0)
    pump(0)
    _select_status(win, "success")  # 状态下拉直连槽，不走去抖
    pump(0)
    check(
        "状态下拉即时生效（不走去抖）",
        _visible_rows(win) == _filter_oracle(win, "", "success"),
        f"可见 {len(_visible_rows(win))} 行",
    )
    win.close()


def main():
    print("=" * 64)
    print("批量解析后台化回归测试（09-15-gui-batch-parse-perf 步骤 1+2+3+4）")
    print("=" * 64)

    test_worker_chunked_progress()
    test_worker_cancel_mid_chunk()
    test_worker_exception_isolation()
    test_worker_failure_detection()
    test_worker_build_parser_fails()
    test_resolve_ed_wrapper_single_source()
    test_current_parse_params_all_protocols()
    test_end_to_end_finish_path()
    test_end_to_end_cancel_path()

    test_worker_record_shape_step3()
    test_cross_frame_state_helpers()
    test_detail_on_demand_mainwindow()
    test_detail_matches_sequential_parse()
    test_export_has_detail_column()

    test_filter_matches_oracle_and_fast()

    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）✓")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
