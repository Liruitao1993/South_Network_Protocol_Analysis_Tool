"""TCP 监控 UI 能力回归测试（R4/R5/R6/R7/R8 + AC2.1）。

覆盖：
  [1] 协议下拉含全协议（AC2.1）且按 itemData 携带协议索引
  [2] 帧表列序与「源 → 目的」列（AC6.1）；未识别帧灰色弱化（AC6.2）
  [3] 字节视图：选中帧后长度一致（AC4.3）；字段行选中触发高亮（AC4.2）；空/4KB 不崩（AC4.4）
  [4] 解析结果 表/字段树 切换（AC5.1）、字段数一致（AC5.2）、树选中触发高亮（AC5.3）
  [5] 切换协议重解析：协议/摘要变化但帧数/顺序/字节不变（AC7.1/AC7.2）
  [6] 过滤：仅未识别（AC8.1/AC8.2）、协议过滤、空状态不崩（AC8.3）

运行: QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_ui_views.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

_config_sandbox.install()

import hex_dump_view as hdv  # noqa: E402
from monitor.tcp_monitor import TCPMonitorWidget  # noqa: E402

PASS = 0
FAIL = 0

D645_FRAME = bytes.fromhex("68AAAAAAAAAAAA 68 11 04 33333333 AD 16".replace(" ", ""))
D698_FRAME = bytes.fromhex("680E00410107080988030100000000 348716".replace(" ", ""))
JUNK_FRAME = bytes.fromhex("DEADBEEF00112233445566778899AABB")


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


def seed_frames(w, entries):
    """把 (frame, direction, src, dst) 灌进缓存并按真实路径重建帧表。"""
    w._frame_cache.clear()
    for frame, direction, src, dst in entries:
        proto, summary, parsed = w._parse_and_summarize(frame)
        w._frame_cache.append({
            "ts": 1000.0, "direction": direction, "frame": frame,
            "protocol": proto, "summary": summary, "parsed": parsed,
            "src": src, "dst": dst,
        })
    w._rebuild_frame_table()


def bg_at_byte(view, index):
    pos = view.char_pos_of_byte(index)
    if pos is None:
        return None
    cur = QTextCursor(view.document())
    cur.setPosition(pos)
    cur.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
    return cur.charFormat().background().color()


def main():
    print("=" * 64)
    print("TCP 监控 UI 能力（B4~B8）")
    print("=" * 64)
    QApplication.instance() or QApplication([])
    w = TCPMonitorWidget()

    section("[1] 协议下拉（AC2.1）")
    items = [w.proto_combo.itemText(i) for i in range(w.proto_combo.count())]
    print(f"    下拉项: {items}")
    for need in ("自动识别", "南网协议", "DLMS Wrapper", "DLT645-2007",
                 "国网协议", "698.45协议", "国网新一代", "南网新一代", "HDC 1.0"):
        check(f"下拉含「{need}」", need in items)
    check("自动识别 itemData=None", w.proto_combo.itemData(0) is None)
    idx645 = w.proto_combo.findText("DLT645-2007")
    check("DLT645-2007 itemData=6", w.proto_combo.itemData(idx645) == 6,
          str(w.proto_combo.itemData(idx645)))
    check("DLMS-APDU 裸报文项存在（短名含 APDU）",
          any("APDU" in x for x in items), str([x for x in items if "APDU" in x]))

    section("[2] 帧表列序 / 源→目的 / 未识别弱化（AC6.1/AC6.2）")
    w.proto_combo.setCurrentIndex(0)  # 自动识别
    seed_frames(w, [
        (D645_FRAME, 0, "10.0.0.1:5000", "10.0.0.2:8080"),
        (JUNK_FRAME, 1, "10.0.0.2:8080", "10.0.0.1:5000"),
    ])
    headers = [w.frame_table.horizontalHeaderItem(i).text()
               for i in range(w.frame_table.columnCount())]
    check("列序 = 时间/方向/源 → 目的/长度/协议/摘要",
          headers == ["时间", "方向", "源 → 目的", "长度", "协议", "摘要"], str(headers))
    check("2 帧 → 2 行", w.frame_table.rowCount() == 2, str(w.frame_table.rowCount()))
    check("第 1 行源→目的按方向推导",
          w.frame_table.item(0, 2).text() == "10.0.0.1:5000 → 10.0.0.2:8080",
          w.frame_table.item(0, 2).text())
    check("第 2 行方向为 ← 且源目的对调",
          w.frame_table.item(1, 1).text() == "←"
          and w.frame_table.item(1, 2).text() == "10.0.0.2:8080 → 10.0.0.1:5000",
          f"{w.frame_table.item(1, 1).text()} {w.frame_table.item(1, 2).text()}")
    check("长度列 = 帧字节数",
          w.frame_table.item(0, 3).text() == str(len(D645_FRAME)),
          w.frame_table.item(0, 3).text())
    check("未识别帧协议列为「原始数据」",
          w.frame_table.item(1, 4).text() == "原始数据", w.frame_table.item(1, 4).text())
    grey = w.frame_table.item(1, 4).foreground().color().name()
    check("未识别帧被灰色弱化", grey == "#999999", grey)
    check("已识别帧未被弱化",
          w.frame_table.item(0, 4).foreground().color().name() != "#999999",
          w.frame_table.item(0, 4).foreground().color().name())

    section("[3] 字节视图（AC4.2/AC4.3/AC4.4）")
    w._on_frame_selected(0, 0)
    check("选中帧后字节视图长度 = 帧长",
          w.frame_byte_view.byte_length == len(D645_FRAME),
          f"{w.frame_byte_view.byte_length} vs {len(D645_FRAME)}")
    check("字节视图内容与帧一致（首字节 hex）",
          w.frame_byte_view.toPlainText()[10:12] == f"{D645_FRAME[0]:02X}",
          w.frame_byte_view.toPlainText()[10:12])
    # 字段行选中 → 高亮（用带字节范围的解析行驱动）
    w._fill_parse_table([
        ["控制码", "0x11", "11H", "读数", 7, 8],
        ["数据长度", "4", "4 字节", "", 9, 9],
    ])
    w.parse_table.setCurrentCell(0, 0)
    w._on_parse_row_selected(0, 0)
    check("字段行选中高亮区间内字节",
          bg_at_byte(w.frame_byte_view, 7) == hdv.HIGHLIGHT_COLOR
          and bg_at_byte(w.frame_byte_view, 8) == hdv.HIGHLIGHT_COLOR,
          str(bg_at_byte(w.frame_byte_view, 7)))
    check("区间外未高亮",
          bg_at_byte(w.frame_byte_view, 6) != hdv.HIGHLIGHT_COLOR)
    w._on_frame_selected(1, 0)
    check("切换到未识别帧：字节视图随之更新",
          w.frame_byte_view.byte_length == len(JUNK_FRAME),
          str(w.frame_byte_view.byte_length))
    w.frame_byte_view.set_bytes(b"")
    check("空字节不崩", w.frame_byte_view.byte_length == 0)
    w.frame_byte_view.set_bytes(bytes(range(256)) * 16)
    check("4096 字节渲染不崩",
          w.frame_byte_view.byte_length == 4096
          and len(w.frame_byte_view.toPlainText().split("\n")) == 256)

    section("[4] 解析结果 表/字段树（AC5.1/AC5.2/AC5.3）")
    views = [w.parse_view_combo.itemText(i) for i in range(w.parse_view_combo.count())]
    check("提供 表 / 字段树 两个视图", views == ["表", "字段树"], str(views))
    # 切到「解析结果」页：否则整页被 QTabWidget 隐藏，isVisibleTo 恒为 False
    w.detail_tabs.setCurrentIndex(1)
    seed_frames(w, [(D698_FRAME, 0, "a:1", "b:2")])
    w._on_frame_selected(0, 0)
    table_rows = w.parse_table.rowCount()
    tree_rows = w.parse_tree.topLevelItemCount()
    check("解析表有数据", table_rows > 0, str(table_rows))
    check("字段树有数据", tree_rows > 0, str(tree_rows))
    w.parse_view_combo.setCurrentIndex(1)  # 字段树
    # 用 isVisibleTo(w)：headless 下顶层窗口未 show()，isVisible() 恒为 False
    check("切到字段树：树可见、表隐藏",
          w.parse_tree.isVisibleTo(w) and not w.parse_table.isVisibleTo(w))
    w.parse_view_combo.setCurrentIndex(0)  # 表
    check("切回表：表可见、树隐藏",
          w.parse_table.isVisibleTo(w) and not w.parse_tree.isVisibleTo(w))
    # 字段树选中 → 高亮（找一个带字节范围的节点）
    target = None
    for i in range(w.parse_tree.topLevelItemCount()):
        it = w.parse_tree.topLevelItem(i)
        if isinstance(it.data(0, Qt.ItemDataRole.UserRole), int):
            target = it
            break
    if target is None:
        check("字段树含带字节范围的节点", False, "未找到（该样本无偏移信息）")
    else:
        target.setSelected(True)
        w._on_parse_tree_selected()
        start = target.data(0, Qt.ItemDataRole.UserRole)
        end = target.data(0, Qt.ItemDataRole.UserRole + 1)
        check("字段树选中触发字节高亮",
              bg_at_byte(w.frame_byte_view, start) == hdv.HIGHLIGHT_COLOR,
              f"byte{start}..{end}")

    section("[5] 切换协议重解析（AC7.1/AC7.2）")
    seed_frames(w, [(D645_FRAME, 0, "a:1", "b:2"), (JUNK_FRAME, 0, "a:1", "b:2")])
    before_protos = [i["protocol"] for i in w._frame_cache]
    before_frames = [i["frame"] for i in w._frame_cache]
    check("重解析前 645 帧识别为 DLT645-2007",
          before_protos[0] == "DLT645-2007", str(before_protos))
    idx_nw = w.proto_combo.findText("南网协议")
    w.proto_combo.setCurrentIndex(idx_nw)   # 触发 currentIndexChanged → 重解析
    after_protos = [i["protocol"] for i in w._frame_cache]
    check("重解析后协议列按新选择变化",
          after_protos != before_protos, f"{before_protos} → {after_protos}")
    check("帧数量不变", len(w._frame_cache) == len(before_frames),
          f"{len(w._frame_cache)}")
    check("帧字节与顺序不变",
          [i["frame"] for i in w._frame_cache] == before_frames)
    check("帧表行数与缓存一致",
          w.frame_table.rowCount() == len(w._frame_cache),
          f"{w.frame_table.rowCount()} vs {len(w._frame_cache)}")

    # AC7.3：>200 帧走分批路径，必须能跑完且最终一致（不阻塞 UI）
    w.proto_combo.setCurrentIndex(0)
    seed_frames(w, [(JUNK_FRAME, 0, "a:1", "b:2")] * 250)
    w.proto_combo.setCurrentIndex(w.proto_combo.findText("南网协议"))
    check("250 帧触发分批（队列非空）",
          bool(getattr(w, "_reparse_queue", None)),
          f"队列={len(getattr(w, '_reparse_queue', []) or [])}")
    for _ in range(60):
        QApplication.processEvents()
        if not getattr(w, "_reparse_queue", None):
            break
    check("分批重解析跑完（队列已清空）",
          not getattr(w, "_reparse_queue", None),
          f"残留={len(getattr(w, '_reparse_queue', []) or [])}")
    check("分批后帧表 250 行",
          w.frame_table.rowCount() == 250, str(w.frame_table.rowCount()))
    check("分批后帧数量不变", len(w._frame_cache) == 250, str(len(w._frame_cache)))

    section("[6] 过滤（AC8.1/AC8.2/AC8.3）")
    w.proto_combo.setCurrentIndex(0)  # 回自动识别并重解析
    seed_frames(w, [
        (D645_FRAME, 0, "a:1", "b:2"),
        (JUNK_FRAME, 0, "a:1", "b:2"),
        (JUNK_FRAME, 1, "b:2", "a:1"),
    ])
    check("过滤前 3 行", w.frame_table.rowCount() == 3, str(w.frame_table.rowCount()))
    w.unrecognized_only_cb.setChecked(True)
    check("仅未识别 → 只剩 2 行", w.frame_table.rowCount() == 2,
          str(w.frame_table.rowCount()))
    check("过滤只影响显示：缓存仍 3 条", len(w._frame_cache) == 3,
          str(len(w._frame_cache)))
    w.unrecognized_only_cb.setChecked(False)
    check("取消过滤恢复 3 行", w.frame_table.rowCount() == 3,
          str(w.frame_table.rowCount()))
    fi = w.proto_filter_combo.findData("DLT645-2007")
    w.proto_filter_combo.setCurrentIndex(fi)
    check("协议过滤 → 只剩 645 帧", w.frame_table.rowCount() == 1,
          str(w.frame_table.rowCount()))
    check("过滤后点行仍能定位正确解析结果",
          w._row_cache_index(0) == 0, str(w._row_cache_index(0)))
    w.proto_filter_combo.setCurrentIndex(0)
    # 空状态：全部过滤掉不崩
    w.proto_filter_combo.setCurrentIndex(w.proto_filter_combo.findData("698.45协议"))
    check("无匹配时 0 行不崩", w.frame_table.rowCount() == 0,
          str(w.frame_table.rowCount()))
    w._on_frame_selected(0, 0)
    check("空表下选中不崩", True)
    w.proto_filter_combo.setCurrentIndex(0)

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
