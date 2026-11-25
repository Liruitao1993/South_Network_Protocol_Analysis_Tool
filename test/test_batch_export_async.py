# -*- coding: utf-8 -*-
"""批量导出：后台线程化回归（用户报障：62,999 帧导出 Excel 时程序「未响应」）。

现场：协议9 批量解析 62,999 帧（21,712 帧带详情），点「导出 Excel」后窗口标题变成
「(未响应)」。根因是导出**全在主线程同步**：逐帧详情重解析 + 每帧约 20 行 × 5 列
写 openpyxl（约 200 万格）+ `wb.save()`；实测 21,712 帧仅写盘就 60~80 秒，
期间事件循环完全停摆。

本测试锁住：
  1. 导出器提供 progress_cb / should_cancel，且取消时抛 ExportCancelled；
  2. `_BatchExportWorker` 在**工作线程**跑（主线程不阻塞），进度单调、结果正确；
  3. 取消后**删除半成品文件**（不留损坏的 xlsx 给用户误用）；
  4. 导出器 Sheet1「包含详细数据」不再二次解析（判据读 _has_detail，与旧结果一致）；
  5. GUI 接线：`export_batch("excel")` 走 `_export_batch_background`，
     主窗口不再直接调用 `export_to_excel`。

运行: python test/test_batch_export_async.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from enhanced_export import EnhancedBatchResultExporter, ExportCancelled  # noqa: E402

PASSED = 0
FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK  {name}")
    else:
        FAILED += 1
        print(f"  FAIL {name}  {detail}")


ROWS = [(f"字段{i}", "0xAB", f"值{i}", "说明" * 3, i, i) for i in range(8)]


def _records(n, detail=True):
    return [
        {
            "_input": f"ED 04 00 0{i % 10} 00 EF FF EE",
            "_status": "成功",
            "_has_detail": detail,
            "_table_data": ROWS if detail else [],
            "摘要": f"第{i}帧",
        }
        for i in range(n)
    ]


# ----------------------------------------------------------------------
# 1. 导出器：进度 / 取消 / 详细数据判据
# ----------------------------------------------------------------------
def test_exporter_progress_and_cancel():
    tmp = Path(tempfile.mkdtemp(prefix="export_"))
    out = tmp / "a.xlsx"

    seen = []
    EnhancedBatchResultExporter(str(tmp)).export_to_excel(
        _records(600), "test", output_file=str(out),
        progress_cb=lambda d, t, ph: seen.append((d, t, ph)),
    )
    check("导出成功生成文件", out.exists() and out.stat().st_size > 0)
    check("进度回调有中间态", len(seen) >= 2, len(seen))
    check("进度刻度统一为 100", all(t == 100 for _, t, _ in seen), seen[:2])
    check("进度单调不减",
          all(seen[i][0] <= seen[i + 1][0] for i in range(len(seen) - 1)),
          seen[:5])
    check("进度到 100 收尾", seen and seen[-1][0] == 100, seen[-1:])
    check("末次带「写入文件」阶段",
          any("写入" in ph for _, _, ph in seen), [p for _, _, p in seen][-3:])

    # 取消：每 200 帧查一次 → 第 1 次检查即取消
    out2 = tmp / "b.xlsx"
    calls = {"n": 0}

    def _cancel():
        calls["n"] += 1
        return True

    try:
        EnhancedBatchResultExporter(str(tmp)).export_to_excel(
            _records(600), "test", output_file=str(out2), should_cancel=_cancel
        )
        check("取消必须抛 ExportCancelled", False)
    except ExportCancelled:
        check("取消抛 ExportCancelled", True)
    check("取消后不留半成品", not out2.exists())
    check("取消检查被调用", calls["n"] >= 1, calls["n"])


def test_detail_flag_no_second_parse():
    """Sheet1 第 6 列判据读 `_has_detail`，不得再调一次 resolver。"""
    tmp = Path(tempfile.mkdtemp(prefix="export_"))
    out = tmp / "c.xlsx"
    calls = {"n": 0}

    def _resolver(result):
        calls["n"] += 1
        return ROWS

    recs = [
        {"_input": "AA", "_status": "成功", "_has_detail": True, "_table_data": ROWS},
        {"_input": "BB", "_status": "失败", "_has_detail": False},
    ]
    EnhancedBatchResultExporter(str(tmp)).export_to_excel(
        recs, "test", output_file=str(out), table_data_resolver=_resolver
    )
    # 只有 Sheet2 需要详情 → 只有「没有 _table_data 键」的失败帧会被解析一次。
    # 旧实现里 Sheet1 第 6 列还会再调一次 resolver（每帧多解析一遍），故这里
    # 断言 ==1（按帧数计）就是「Sheet1 没有第二次解析」的证据。
    check("每帧详情只解析一次（Sheet1 不再重复解析）", calls["n"] == 1, calls["n"])

    from openpyxl import load_workbook

    ws = load_workbook(out)["汇总表"]
    check("Sheet1 详细数据列 = 是", ws.cell(row=2, column=6).value == "是")
    check("Sheet1 详细数据列 = 否", ws.cell(row=3, column=6).value == "否")


# ----------------------------------------------------------------------
# 2. 后台 worker
# ----------------------------------------------------------------------
def test_worker_runs_off_main_thread():
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

    import main_gui

    app = QCoreApplication.instance() or QCoreApplication([])
    tmp = Path(tempfile.mkdtemp(prefix="export_"))
    out = tmp / "d.xlsx"

    worker = main_gui._BatchExportWorker(
        fmt="excel",
        results=_records(1500),
        protocol_name="test",
        file_path=str(out),
        table_data_resolver=None,
    )
    progress = []
    result = {}
    loop = QEventLoop()

    def _on_progress(d, t, ph):
        progress.append((d, t, ph, time.time()))
        # 进度回调在主线程：只要能持续收到，就证明事件循环没被堵死
        app.processEvents()

    def _on_done(ok, msg):
        result["ok"] = ok
        result["msg"] = msg
        loop.quit()

    worker.progress.connect(_on_progress)
    worker.done.connect(_on_done)

    t0 = time.time()
    worker.start()
    QTimer.singleShot(180_000, loop.quit)
    loop.exec()
    worker.wait(10_000)
    elapsed = time.time() - t0

    check("导出完成", result.get("ok") is True, result)
    check("文件生成", out.exists() and out.stat().st_size > 0)
    check("工作线程收到多次进度（主线程未被阻塞）", len(progress) >= 2, len(progress))
    check("耗时合理（<180s）", elapsed < 180, f"{elapsed:.1f}s")


def test_worker_cancel_removes_file():
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

    import main_gui

    app = QCoreApplication.instance() or QCoreApplication([])
    tmp = Path(tempfile.mkdtemp(prefix="export_"))
    out = tmp / "e.xlsx"

    worker = main_gui._BatchExportWorker(
        fmt="excel",
        results=_records(3000),
        protocol_name="test",
        file_path=str(out),
        table_data_resolver=None,
    )
    result = {}
    loop = QEventLoop()

    def _on_done(ok, msg):
        result["ok"] = ok
        result["msg"] = msg
        loop.quit()

    worker.done.connect(_on_done)
    worker.start()
    # 进度一出现就取消
    worker.progress.connect(lambda d, t, ph: worker.cancel())
    QTimer.singleShot(180_000, loop.quit)
    loop.exec()
    worker.wait(10_000)

    check("取消返回 ok=False", result.get("ok") is False, result)
    check("取消标记为 __cancelled__", result.get("msg") == "__cancelled__", result)
    check("取消后不留半成品", not out.exists())


# ----------------------------------------------------------------------
# 3. GUI 接线
# ----------------------------------------------------------------------
def test_gui_wiring():
    src = Path(__file__).resolve().parent.parent / "main_gui.py"
    text = src.read_text(encoding="utf-8")
    idx = text.find("    def export_batch(self, fmt=None):")
    end = text.find("    def _get_frame_type_name(", idx)
    body = text[idx:end]
    check("export_batch 不再直接调用 export_to_excel",
          "export_to_excel(" not in body)
    check("export_batch 走后台入口",
          "_export_batch_background(" in body)
    check("后台入口存在", "def _export_batch_background(" in text)
    check("后台入口用非缓存 resolver",
          "_batch_detail_resolver(cache=False)" in text)
    check("worker 取消会删半成品", "_cleanup_partial" in text)

    # 进度显示走状态栏：QProgressDialog 在 setValue() 时会进模态/自动事件循环，
    # 实测在离屏与主线程忙碌场景把导出卡死（4 次冒烟全卡在这里）。
    bg_idx = text.find("    def _export_batch_background(")
    bg_end = text.find("    def cancel_batch_export(", bg_idx)
    bg_body = text[bg_idx:bg_end]
    check("后台入口不再使用 QProgressDialog",
          "QProgressDialog(" not in bg_body)
    check("进度走状态栏", "statusBar().showMessage" in bg_body)
    check("有取消入口", "def cancel_batch_export(" in text)


def test_excel_uses_write_only():
    """锁住提速方案：Excel 导出必须用 write_only + 行式 append。

    现场 21,712 帧：普通 Workbook 逐格 `ws.cell()` + 逐格设样式 = **875 秒**；
    write_only + `append` = **40 秒**（22 倍）。这条断言防止有人「顺手」改回
    逐格写入 —— 那不是风格问题，是把「未响应」重新做回来。
    """
    src = Path(__file__).resolve().parent.parent / "enhanced_export.py"
    text = src.read_text(encoding="utf-8")
    idx = text.find("    def export_to_excel(")
    end = text.find("    def validate_export_data(", idx)
    body = text[idx:end]
    check("Excel 导出使用 write_only", "Workbook(write_only=True)" in body)
    check("行式写入用 append", ".append(" in body)
    check("不再逐格 ws.cell( 写数据", "ws_detail.cell(" not in body, "仍有逐格写入")
    check("帧标题用 WriteOnlyCell", "WriteOnlyCell(" in body)
    check("进度刻度为全局百分比", "SHEET1_END" in body and "SHEET2_END" in body)


def test_raw_log_sheet_keeps_everything():
    """Sheet3「原始日志」必须逐行保留原文（用户口径：不能损失原始信息）。

    现场 62,999 非空行里只有 21,712 个报文帧，其余是「流程日志：…」文字行 ——
    这些同样是排查依据，所以导出文件自身必须带一份完整原文。
    """
    from openpyxl import load_workbook

    tmp = Path(tempfile.mkdtemp(prefix="export_"))
    out = tmp / "log.xlsx"
    # 交错构造：偶数行是日志文字，奇数行是报文；含空行，验证空行也不丢
    lines = []
    for i in range(50):
        lines.append(f"2026-04-30 03:11:{i:02d} 719: 流程日志：步骤{i}")
        if i % 5 == 0:
            lines.append("")
        lines.append("2026-04-30 03:11:06 978: --RX(3): data := 'ED 04 00 01'")
    raw = "\n".join(lines)

    EnhancedBatchResultExporter(str(tmp)).export_to_excel(
        _records(3), "test", output_file=str(out), raw_log_text=raw
    )
    wb = load_workbook(out, read_only=True)
    check("含「原始日志」Sheet", "原始日志" in wb.sheetnames, wb.sheetnames)
    ws = wb["原始日志"]
    got = [row[1] for row in ws.iter_rows(min_row=2, values_only=True)]
    check("原文行数一致（含空行）", len(got) == len(lines), (len(got), len(lines)))

    def _norm(v):
        # Excel 空单元格读回来是 None，写入端是 ""，两者等价（位置/行数不变即未丢行）
        return "" if v is None else v

    check(
        "原文逐行相同",
        [_norm(x) for x in got] == [_norm(x) for x in lines],
        "首处不同: "
        + str(next((i for i, (a, b) in enumerate(zip(got, lines))
                    if _norm(a) != _norm(b)), "无")),
    )
    check("空行也保留（行数与位置不变）",
          sum(1 for x in got if _norm(x) == "") == lines.count(""),
          [i for i, x in enumerate(got) if _norm(x) == ""][:3])

    # 不传原文时不生成该 Sheet（JSON 路径 / 旧调用方行为不变）
    out2 = tmp / "nolog.xlsx"
    EnhancedBatchResultExporter(str(tmp)).export_to_excel(
        _records(3), "test", output_file=str(out2)
    )
    wb2 = load_workbook(out2, read_only=True)
    check("未传原文则不生成 Sheet3", "原始日志" not in wb2.sheetnames, wb2.sheetnames)


def test_count_frames_not_lines():
    """「共 N 帧」必须是真实帧数，不能退回「非空行数」（用户报障：62999 当成帧数）。

    现场那份日志：非空行 62,999，但真实报文帧只有 21,712 —— 旧实现把行数当帧数，
    用户以为丢了 4 万多帧原始数据。
    """
    src = Path(__file__).resolve().parent.parent / "main_gui.py"
    text = src.read_text(encoding="utf-8")
    idx = text.find("    def _do_count_frames(self):")
    end = text.find("    def _copy_batch_detail_hex(", idx)
    body = text[idx:end]
    check("不再按非空行近似统计",
          "sum(1 for line in text.splitlines() if line.strip())" not in body
          or "_strip_csg_new_gen_frame_prefix" in body)
    check("协议9 走真实剥离", "_strip_csg_new_gen_frame_prefix" in body)
    check("协议10/11 走真实剥离", "_strip_gw_new_gen_prefix" in body)
    check("统计与批量同序（先清洗再提取）",
          "_clean_hex_input(" in body and "_extract_frames_for_protocol(" in body)
    check("行数与帧数并列显示", "日志 {total_lines} 行" in body)


def main():
    for fn in (
        test_exporter_progress_and_cancel,
        test_detail_flag_no_second_parse,
        test_excel_uses_write_only,
        test_raw_log_sheet_keeps_everything,
        test_count_frames_not_lines,
        test_worker_runs_off_main_thread,
        test_worker_cancel_removes_file,
        test_gui_wiring,
    ):
        print(f"\n[{fn.__name__}]")
        fn()
    print(f"\n{'=' * 50}\n{PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
