# -*- coding: utf-8 -*-
"""ED 包装头文案按协议分语义：协议10/11 不得显示「广西台体」

用户（2026-09-20）:
    广西的 ED 封装与国网 HDC 的 ED 封装定义相同，但选择协议 10/11 时，
    解析结果字段应展示「国网HDC」封包头解释，而不是「广西台体监控包装头」。

单一来源: batch_core.ed_wrapper_display(protocol_index, wrapper)

运行: python -X utf8 -u test/test_ed_wrapper_labels.py
"""

import os
import sys

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402
from batch_core import ed_wrapper_display, ed_wrapper_summary_name  # noqa: E402
from main_gui import MainWindow  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

_config_sandbox.install()

PASS = 0
FAIL = 0
FAILED = []

HDC10_MAC = bytes.fromhex(
    "00000100019673005C80FF0800960000"
    "200000000124010101010101"
    "000000002000000001240100000000000000000001030001"
    "329FBACA69DE640900000000A860CAF104A18A64E8F2"
    "0000040099F4484C3039000000000000000065F9"
    "0000000000000000000000000000000000000000000000000000"
    "688150C40000000000000000BA711E"
)


def make_ed_frame(business: bytes, layout="gx") -> bytes:
    if layout == "gx":
        # 8B 公共头: 时间戳4 + 信道1 + 块数1 + 块长2
        data域 = (
            (0x11223344).to_bytes(4, "little")
            + bytes([0x01, 0x01])
            + len(business).to_bytes(2, "little")
            + business
        )
    else:
        data域 = (
            bytes([0x01])
            + (0x11223344).to_bytes(4, "little")
            + bytes([0x01, 0x00])
            + len(business).to_bytes(2, "little")
            + business
        )
    body = bytes([0x00, 0x02, 0xEF]) + data域
    frame_len = len(body) + 1
    cs = sum(bytes([0xED]) + frame_len.to_bytes(2, "little") + body) & 0xFF
    return bytes([0xED]) + frame_len.to_bytes(2, "little") + body + bytes([cs, 0xEE])


def section(title):
    print(f"\n{title}")


def check(desc, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {desc}")
    else:
        FAIL += 1
        FAILED.append(desc)
        print(f"  ✗ {desc}" + (f"\n      {detail}" if detail else ""))


def main():
    section("[1] 纯函数 ed_wrapper_display")
    p9_gx = ed_wrapper_display(9, "gx")
    p11_gx = ed_wrapper_display(11, "gx")
    p10_gx = ed_wrapper_display(10, "gx")
    check("协议9 gx 标题=广西台体", "广西台体" in p9_gx["title"], p9_gx["title"])
    check("协议11 gx 标题=国网HDC", "国网HDC" in p11_gx["title"] and "广西" not in p11_gx["title"],
          p11_gx["title"])
    check("协议10 gx 标题=国网HDC", "国网HDC" in p10_gx["title"], p10_gx["title"])
    check("协议11 gx 摘要名=国网HDC监控包装帧",
          p11_gx["summary_name"] == "国网HDC监控包装帧", p11_gx["summary_name"])
    check("协议11 gx 起始注释不含广西", "广西" not in p11_gx["start_comment"],
          p11_gx["start_comment"])
    check("协议11 gx 结束注释含 HDC", "HDC" in p11_gx["end_comment"], p11_gx["end_comment"])
    check("协议11 gx 下拉文案=国网HDC(8字节公共头)",
          "国网HDC" in p11_gx["combo_label"], p11_gx["combo_label"])
    p9_plc2 = ed_wrapper_display(9, "plc2")
    p11_plc2 = ed_wrapper_display(11, "plc2")
    check("协议9 plc2 仍为 PLC2.0", "PLC2.0" in p9_plc2["title"], p9_plc2["title"])
    check("协议11 plc2 标题含国网HDC且标注 PLC2.0 布局",
          "国网HDC" in p11_plc2["title"] and "PLC2.0" in p11_plc2["title"],
          p11_plc2["title"])
    check("summary_name 从标题推断 HDC",
          ed_wrapper_summary_name(p11_gx["title"]) == "国网HDC监控包装帧",
          ed_wrapper_summary_name(p11_gx["title"]))
    check("summary_name 从标题推断广西",
          ed_wrapper_summary_name(p9_gx["title"]) == "广西台体监控包装帧")

    section("[2] 协议11 单帧：gx 布局 ED 帧字段用国网HDC，不含广西台体")
    ed_gx = make_ed_frame(HDC10_MAC, "gx")
    w = MainWindow()
    w._on_protocol_changed(11)
    w.ed_monitor_chk.setChecked(True)
    w.ed_wrapper_combo.setCurrentIndex(w.ed_wrapper_combo.findData("gx"))
    w.single_input.setPlainText(ed_gx.hex())
    w.parse_single()
    labels = [
        str(w.result_table_widget.item(r, 0).text())
        for r in range(w.result_table_widget.rowCount())
        if w.result_table_widget.item(r, 0)
    ]
    comments = [
        str(w.result_table_widget.item(r, 3).text())
        for r in range(w.result_table_widget.rowCount())
        if w.result_table_widget.item(r, 3)
    ]
    all_txt = " ".join(labels) + " " + " ".join(comments)
    print("  首行:", labels[0] if labels else "")
    check("标题为国网HDC监控包装头",
          any("国网HDC监控包装头" in x for x in labels), str(labels[:3]))
    check("结果中无「广西台体」", "广西台体" not in all_txt,
          [x for x in labels + comments if "广西" in x][:3])
    check("仍含业务/监控字段",
          any("MSDU" in x or "消息类型" in x or "起始符" in x for x in labels),
          str(labels[:15]))
    check("下拉 gx 项文案为国网HDC",
          "国网HDC" in w.ed_wrapper_combo.itemText(w.ed_wrapper_combo.findData("gx")),
          w.ed_wrapper_combo.itemText(w.ed_wrapper_combo.findData("gx")))

    section("[3] 协议9 回归：同布局仍显示广西台体")
    w._on_protocol_changed(9)
    w.ed_monitor_chk.setChecked(True)
    w.ed_wrapper_combo.setCurrentIndex(w.ed_wrapper_combo.findData("gx"))
    w.single_input.setPlainText(ed_gx.hex())
    w.parse_single()
    labels9 = [
        str(w.result_table_widget.item(r, 0).text())
        for r in range(w.result_table_widget.rowCount())
        if w.result_table_widget.item(r, 0)
    ]
    check("协议9 标题仍为广西台体",
          any("广西台体监控包装头" in x for x in labels9), str(labels9[:3]))
    check("协议9 下拉 gx 项仍为广西台体",
          "广西台体" in w.ed_wrapper_combo.itemText(w.ed_wrapper_combo.findData("gx")),
          w.ed_wrapper_combo.itemText(w.ed_wrapper_combo.findData("gx")))

    section("[4] 协议10 抽样")
    w._on_protocol_changed(10)
    w.ed_monitor_chk.setChecked(True)
    w.ed_wrapper_combo.setCurrentIndex(w.ed_wrapper_combo.findData("gx"))
    w.single_input.setPlainText(ed_gx.hex())
    w.parse_single()
    labels10 = [
        str(w.result_table_widget.item(r, 0).text())
        for r in range(w.result_table_widget.rowCount())
        if w.result_table_widget.item(r, 0)
    ]
    all10 = " ".join(labels10)
    check("协议10 标题含国网HDC", any("国网HDC" in x for x in labels10), str(labels10[:3]))
    check("协议10 无广西台体", "广西台体" not in all10,
          [x for x in labels10 if "广西" in x])

    w.close()
    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    if FAILED:
        for n in FAILED:
            print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
