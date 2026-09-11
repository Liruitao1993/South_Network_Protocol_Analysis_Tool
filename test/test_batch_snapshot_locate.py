# -*- coding: utf-8 -*-
"""批量解析「原始日志快照」右键定位 回归测试（任务 09-10-batch-snapshot-locate）

覆盖：
  [1] 纯逻辑：hex_stream / find_frame_in_stream（单行/跨行/重发消歧/大小写/短输入/
      时间戳逐行剥离不污染帧体/监控头邻接不误拆）
  [2] 快照链：set_batch_snapshot、CRLF 归一、输入框改写不污染快照、缓存失效、
      clear_batch 清理、parse_batch 兜底
  [3] offscreen GUI：协议9 监控日志 parse_batch → _locate_frame_in_snapshot 弹窗
      命中行号、重发帧消歧、查看器复用、搜索计数循环、Ctrl+F、右键菜单构建与
      启用态、无快照提示路径

注意：extraSelections() 返回的列表必须持有引用——shiboken 临时列表析构会连带
其内 QTextCursor 包装失效（链式访问 [0].cursor 会 RuntimeError: already deleted）。

直接运行: python test/test_batch_snapshot_locate.py
"""
import _path_setup  # noqa: E402

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FAILURES = []
PASS = 0


def check(name, cond, detail=""):
    global PASS
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASS += 1
    else:
        FAILURES.append(name)


# ============================ [1] 纯逻辑层 ============================

import batch_source_view as bsv  # noqa: E402

F1 = "ED0700000000010001E80005EF16"  # 14B 样本帧
F2 = "ED0F00000000010001E80006F017"

check("normalize_hex 空格/大小写", bsv.normalize_hex("ed 07 00 ff") == "ED0700FF")

snap = (
    "2026-09-10 10:00:00 1 -> 接收机 Has Get "
    + " ".join(f"{i:02X}" for i in range(15))
    + "\n"
    "ED 07 00 00 00 00 01 00 01 E8 00 05 EF 16\n"
    "====== separator ======\n"
    + F2.lower()
    + "\n"
)
check("单行命中（帧体在第1行，行首时间戳不混入）", bsv.find_frame_in_text(snap, F1) == [(1, 1)])
check("小写帧 hex 命中第3行", bsv.find_frame_in_text(snap, F2) == [(3, 3)])

# 跨行帧：续行行首时间戳剥离后帧体在流中连续
cross = (
    "2026-08-05 20:40:29:713 'ED 07 00 00 00 00\n"
    "2026-08-05 20:40:29:800 01 00 01 E8 00 05 EF 16'O\n"
)
check("跨行帧命中 (0,1)", bsv.find_frame_in_text(cross, F1) == [(0, 1)])

dup = f"{F1}\nnoise\n{F1}\nnoise\n{F1}\n"
check("重发帧 3 命中非重叠", bsv.find_frame_in_text(dup, F1) == [(0, 0), (2, 2), (4, 4)])
check(
    "帧内重叠不产生假命中",
    bsv.find_frame_in_text("AAAABBBBCCCCDDDD" + F1 + "\n", F1) == [(0, 0)],
)

check("短输入(<2B)拒绝", bsv.find_frame_in_text(snap, "ABCD") == [])
check("未命中返回空", bsv.find_frame_in_text(snap, "A1B2C3D4E5F60718293A4B5C6D7E8F90") == [])

stream, line_of = bsv.hex_stream(snap)
check("hex_stream 流长与行映射一致", len(stream) == len(line_of) and stream == stream.upper())
check(
    "find_frame_in_stream 与一次性版一致",
    bsv.find_frame_in_stream(stream, line_of, F1) == [(1, 1)],
)

# 监控行内帧体（15B 监控头与帧体同处一行且头含 hex）：邻接不误拆
monitor_body = "68110101000000000100010000"
monitor_line_text = (
    "15:49:51 254  -> 接收机 Has Get "
    "ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 "
    "68 11 01 01 00 00 00 00 01 00 01 00 00"
)
check("监控行帧体命中", bsv.find_frame_in_text(monitor_line_text, monitor_body) == [(0, 0)])


# ============================ [2][3] GUI 集成 ============================


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    import main_gui
    from PySide6.QtCore import QEvent, QModelIndex, QPoint, Qt
    from PySide6.QtGui import QKeyEvent

    win = main_gui.MainWindow()
    app.processEvents()
    try:
        win._clipboard_monitor.set_enabled(False)  # 屏蔽剪贴板提示弹窗干扰
    except Exception:
        pass

    # ── [2] 快照链 ──
    win._set_batch_snapshot("HEADER line\n" + F1 + "\n", "t.log")
    check("set_batch_snapshot 建立快照", win._batch_snapshot_text.startswith("HEADER line\n"))
    check("快照名记录", win._batch_snapshot_name == "t.log")
    win._set_batch_snapshot("crlf\r\nline\r\n", None)
    check("CRLF 归一为 LF", "\r" not in win._batch_snapshot_text)
    win._set_batch_snapshot(snap, "t.log")

    # 回填式预处理只改输入框（CLI/脚本回填路径），快照不动
    win.batch_input.setPlainText("CLEANED ONLY")
    check("输入框改写不影响快照", win._batch_snapshot_text == snap)
    # 快照缓存随新快照失效
    win._set_batch_snapshot(snap + "extra\n", "t.log")
    check("重建快照使流缓存失效", win._snapshot_hex_cache is None)

    # ── [3] 真实链路：协议9 监控日志 → parse_batch → 右键定位 ──
    win._on_protocol_changed(9)
    app.processEvents()

    def mk_monitor_line(frame_spaced, seq):
        ts = "2026-09-10 10:00:0{}".format(seq % 10)
        head = " ".join(f"{i:02X}" for i in range(15))
        return f"{ts} {seq} -> 接收机 Has Get {head} {frame_spaced}"

    f1_spaced = " ".join(F1[i : i + 2] for i in range(0, len(F1), 2))
    f2_spaced = " ".join(F2[i : i + 2] for i in range(0, len(F2), 2))
    log = "\n".join(
        [
            mk_monitor_line(f1_spaced, 1),
            mk_monitor_line(f2_spaced, 2),
            mk_monitor_line(f1_spaced, 3),  # F1 重发（第 3 行）
        ]
    )
    win.batch_input.setPlainText(log)
    win._set_batch_snapshot(log, "monitor.log")
    win.parse_batch()
    app.processEvents()
    n = len(win.batch_results)
    check("批量解析产出帧", n >= 3, f"results={n}")
    hexes = [r["_input"].replace(" ", "").upper() for r in win.batch_results]
    f1_idxs = [i for i, h in enumerate(hexes) if F1 in h]
    f2_idxs = [i for i, h in enumerate(hexes) if F2 in h]
    check(
        "监控日志产出 2 次 F1 与 1 次 F2 帧",
        len(f1_idxs) >= 2 and len(f2_idxs) >= 1,
        f"hexes={[h[:20] for h in hexes]}",
    )
    if not f1_idxs or not f2_idxs:
        print("!! 样本帧未被协议9提取，跳过定位断言")
        raise SystemExit(1)

    def first_sel_line(viewer):
        sels = viewer.view.extraSelections()  # 持引用，防 shiboken 析构 cursor
        return sels[0].cursor.blockNumber() if sels else -1

    # 定位第一个 F1 帧 → 快照第 1 行（0-based=0）
    win._locate_frame_in_snapshot(f1_idxs[0])
    v = win._src_viewer
    check("查看器已创建并弹出", v is not None and v.isVisible())
    check("弹窗内容=快照原文", v.view.toPlainText() == win._batch_snapshot_text)
    hit_line = first_sel_line(v)
    check("帧黄底高亮 + 第 1 次 F1 定位 0-based=0", hit_line == 0, f"line={hit_line}")

    # 重发消歧：第二个 F1 帧命中第 3 行（0-based=2）
    win._locate_frame_in_snapshot(f1_idxs[1])
    hit_line2 = first_sel_line(v)
    check("重发帧消歧到后一次命中(0-based=2)", hit_line2 == 2, f"{hit_line2} vs {hit_line}")

    # 查看器复用单实例
    win._locate_frame_in_snapshot(f2_idxs[0])
    check("复用同一查看器实例", win._src_viewer is v)
    hit_line3 = first_sel_line(v)
    check("F2 定位到第 2 行(0-based=1)", hit_line3 == 1, f"line={hit_line3}")

    # 搜索定位（帧黄底 + 搜索命中橙底共存）
    v.find_edit.setText("接收机")
    v.find_next()
    check("搜索命中计数 1/3", v.find_count.text() == "1/3", v.find_count.text())
    v.find_next()
    check("下一个推进 2/3", v.find_count.text() == "2/3", v.find_count.text())
    v.find_prev()
    check("上一个回退 1/3", v.find_count.text() == "1/3", v.find_count.text())
    n_extras = len(v.view.extraSelections())
    check("搜索3命中+帧黄底合并", n_extras >= 4, f"extras={n_extras}")
    v.toggle_find_bar(False)
    check("收起搜索后帧黄底保留", len(v.view.extraSelections()) == 1)

    QApplication.sendEvent(
        v,
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_F,
            Qt.KeyboardModifier.ControlModifier,
        ),
    )
    check("Ctrl+F 显示查找条", v.find_bar.isVisible())

    # clear_batch：快照与查看器销毁
    win.clear_batch()
    check("clear_batch 清快照", win._batch_snapshot_text == "" and win._snapshot_hex_cache is None)
    check("clear_batch 关查看器", win._src_viewer is None)
    check("clear_batch 后 batch_results 空", win.batch_results == [])

    # ── 右键菜单构建 ──
    table = win.batch_summary_table
    menu = win._build_batch_summary_menu(table, QPoint(-1, -1))
    titles = [a.text() for a in menu.actions()]
    check(
        "菜单项齐全",
        titles[0].startswith("转到原始报文位置")
        and "Ctrl+G" in titles[0]
        and titles[1] == "复制本帧HEX"
        and "复制选中行" in titles
        and "复制全部" in titles,
        str(titles),
    )
    check("空表右键定位项禁用", not menu.actions()[0].isEnabled())

    # 重新解析产出数据行 → 启用态 + 右键先选中
    win.batch_input.setPlainText(
        "\n".join([mk_monitor_line(f1_spaced, 1), mk_monitor_line(f2_spaced, 2)])
    )
    win._set_batch_snapshot(win.batch_input.toPlainText(), "m.log")
    win.parse_batch()
    app.processEvents()
    check("解析后有摘要行", table.rowCount() >= 2, f"rows={table.rowCount()}")
    if table.rowCount() >= 2:
        rect = table.visualItemRect(table.item(1, 0))
        menu2 = win._build_batch_summary_menu(table, rect.center())
        check("有数据行右键定位项启用", menu2.actions()[0].isEnabled())
        check("右键落选区外先选中该行", table.selectionModel().isRowSelected(1, QModelIndex()))

    # 无快照时点定位 → 弹信息提示且不建查看器（monkeypatch 捕获）
    win._batch_snapshot_text = ""
    win._src_viewer = None
    calls = []
    orig_info = main_gui.QMessageBox.information
    main_gui.QMessageBox.information = staticmethod(lambda *a, **k: calls.append(a))
    try:
        win._locate_frame_in_snapshot(0)
    finally:
        main_gui.QMessageBox.information = orig_info
    check("无快照弹提示且不建查看器", len(calls) == 1 and win._src_viewer is None)

    # parse_batch 兜底：手敲无快照 → 解析时以框现文为快照
    win._batch_snapshot_text = ""
    win.batch_input.setPlainText(mk_monitor_line(f1_spaced, 9))
    win.parse_batch()
    app.processEvents()
    check("parse_batch 兜底建立快照", win._batch_snapshot_text.startswith("2026-09-10"))
    check("兜底快照名", win._batch_snapshot_name == "输入框内容")

    # ── 快捷键 Ctrl+G + 弹窗保持跟随 + 命中缓存 ──
    from PySide6.QtGui import QShortcut as _QS  # noqa: F401  (仅确认可导入)

    win._src_viewer = None
    win.batch_input.setPlainText(
        "\n".join([mk_monitor_line(f1_spaced, 1), mk_monitor_line(f2_spaced, 2)])
    )
    win._set_batch_snapshot(win.batch_input.toPlainText(), "m.log")
    win.parse_batch()
    app.processEvents()
    hexes2 = [r["_input"].replace(" ", "").upper() for r in win.batch_results]
    table.selectRow(0)
    app.processEvents()

    # 命中缓存：同帧二次定位不重算 find
    n_hex0 = next(i for i, h in enumerate(hexes2) if F1 in h)
    calls = {"n": 0}
    orig_find = bsv.find_frame_in_stream

    def counting_find(*a, **k):
        calls["n"] += 1
        return orig_find(*a, **k)

    main_gui.batch_source_view.find_frame_in_stream = counting_find
    try:
        win._locate_frame_in_snapshot(n_hex0)
        v2 = win._src_viewer
        check("首次定位调用 find 一次", calls["n"] == 1, f"n={calls['n']}")
        win._locate_frame_in_snapshot(n_hex0)
        check("重复定位命中缓存不重算", calls["n"] == 1, f"n={calls['n']}")

        # Ctrl+G 快捷键：焦点在摘要表按 Ctrl+G → 定位当前行（弹窗已开→静默刷新）
        table.setFocus()
        QApplication.sendEvent(
            table,
            QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_G,
                Qt.KeyboardModifier.ControlModifier,
            ),
        )
        sels_g = v2.view.extraSelections()
        check(
            "Ctrl+G 定位第 1 帧到快照行0",
            len(sels_g) >= 1 and sels_g[0].cursor.blockNumber() == 0,
            f"line={sels_g[0].cursor.blockNumber() if sels_g else -1}",
        )

        # 弹窗保持：切到第 2 行 → 自动静默跟随高亮（不重新抢焦点）
        table.selectRow(1)
        app.processEvents()
        sels2 = v2.view.extraSelections()
        check(
            "弹窗打开时切行自动跟随定位",
            len(sels2) >= 1 and sels2[0].cursor.blockNumber() == 1,
            f"line={sels2[0].cursor.blockNumber() if sels2 else -1}",
        )
        check("跟随定位不重开/不弹提示", v2.isVisible())

        # 关闭弹窗后切行不再触发跟随（find 调用数不变）
        before = calls["n"]
        v2.close()
        table.selectRow(0)
        app.processEvents()
        check("弹窗关闭后切行不跟随", calls["n"] == before, f"{calls['n']} vs {before}")
    finally:
        main_gui.batch_source_view.find_frame_in_stream = orig_find
        win._src_viewer = None

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项: {FAILURES}")
        raise SystemExit(1)
    print(f"全部测试通过（{PASS} 项）")


if __name__ == "__main__":
    main()
