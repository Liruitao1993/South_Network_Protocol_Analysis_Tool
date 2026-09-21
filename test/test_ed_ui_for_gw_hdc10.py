# -*- coding: utf-8 -*-
"""协议9/10/11 共用：ED监控勾选 + 4字节反转 + 字节剔除（注册表能力）

用户需求（2026-09-19）:
    GUI 协议11 单帧解析也会遇到带 ED 封装的报文，
    需要把协议9 的「ED监控协议」勾选、4字节反转等操作复制到协议10/11。

覆盖:
  [1] protocol_registry：9/10/11 has_ed_monitor & has_reverse_4byte；协议8 均为 False
  [2] 主窗口切换协议后控件可见性（offscreen）
  [3] 协议11 勾选 ED → 解包业务帧并出现监控包装字段
  [4] 协议11 未勾选 ED + 业务帧 DT 合法 → 仍自动解包（兼容既有行为）
  [5] 协议11 勾选 4字节反转 → 输入按组翻转后再解析
  [6] 协议11 勾选 ED 且帧不完整 → 明确报错（与协议9 同口径）
  [7] 协议10 同路径抽样

运行:
    python -X utf8 -u test/test_ed_ui_for_gw_hdc10.py
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
import protocol_registry  # noqa: E402
from main_gui import MainWindow  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

_config_sandbox.install()

PASS = 0
FAIL = 0
FAILED = []

# 协议11 关联请求 MAC 帧（无 PBH，首字节 0x00 → DT=0，可作 ED 业务帧）
HDC10_MAC = bytes.fromhex(
    "00000100019673005C80FF0800960000"
    "200000000124010101010101"
    "000000002000000001240100000000000000000001030001"
    "329FBACA69DE640900000000A860CAF104A18A64E8F2"
    "0000040099F4484C3039000000000000000065F9"
    "0000000000000000000000000000000000000000000000000000"
    "688150C40000000000000000BA711E"
)


def make_ed_frame(business: bytes, ctrl1=0x00, ctrl2=0x02) -> bytes:
    """PLC2.0 ED..EE 包装（公共头 9 字节）"""
    ch, ts, pb_cnt = 0x01, 0x11223344, 0x01
    pb_len = len(business)
    data域 = (
        bytes([ch])
        + ts.to_bytes(4, "little")
        + bytes([pb_cnt, 0x00])
        + pb_len.to_bytes(2, "little")
        + business
    )
    body = bytes([ctrl1, ctrl2, 0xEF]) + data域
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
    section("[1] 注册表能力字段")
    for idx in (9, 10, 11):
        spec = protocol_registry.get_protocol(idx)
        check(f"协议{idx} has_ed_monitor", spec.has_ed_monitor)
        check(f"协议{idx} has_reverse_4byte", spec.has_reverse_4byte)
    spec8 = protocol_registry.get_protocol(8)
    check("协议8 无 ED/反转能力", not spec8.has_ed_monitor and not spec8.has_reverse_4byte)

    section("[2] 主窗口控件可见性")
    w = MainWindow()
    w._on_protocol_changed(11)
    check("协议11 ED勾选可见", w.ed_monitor_chk.isVisibleTo(w))
    check("协议11 ED包装格式下拉可见", w.ed_wrapper_combo.isVisibleTo(w))
    check("协议11 4字节反转可见", w.csg_reverse_4byte_chk.isVisibleTo(w))
    check("协议11 字节剔除头可见", w.csg_strip_head_spin.isVisibleTo(w))
    w._on_protocol_changed(10)
    check("协议10 ED勾选可见", w.ed_monitor_chk.isVisibleTo(w))
    check("协议10 4字节反转可见", w.csg_reverse_4byte_chk.isVisibleTo(w))
    w._on_protocol_changed(8)
    check("协议8 ED勾选隐藏", not w.ed_monitor_chk.isVisibleTo(w))
    check("协议8 4字节反转隐藏", not w.csg_reverse_4byte_chk.isVisibleTo(w))
    w._on_protocol_changed(9)
    check("协议9 ED勾选仍可见", w.ed_monitor_chk.isVisibleTo(w))

    section("[3] 协议11 勾选 ED：解包并出现监控字段 + MAC 业务")
    ed_frame = make_ed_frame(HDC10_MAC)
    w._on_protocol_changed(11)
    w.ed_monitor_chk.setChecked(True)
    w.csg_reverse_4byte_chk.setChecked(False)
    w.csg_strip_head_spin.setValue(0)
    w.csg_strip_tail_spin.setValue(0)
    w.single_input.setPlainText(ed_frame.hex())
    w.parse_single()
    labels = [
        str(w.result_table_widget.item(r, 0).text())
        for r in range(w.result_table_widget.rowCount())
        if w.result_table_widget.item(r, 0)
    ]
    check("结果非空", len(labels) > 0, str(len(labels)))
    check("含监控包装字段", any("监控" in x or "ED" in x or "RSSI" in x or "时间戳" in x or "业务帧" in x
                               for x in labels), str(labels[:12]))
    check("含 MAC/关联业务字段",
          any("MSDU" in x or "MMTYPE" in x or "消息类型" in x or "关联" in x for x in labels),
          str(labels[:20]))

    section("[4] 协议11 未勾选 ED：业务 DT 合法时仍自动解包")
    w.ed_monitor_chk.setChecked(False)
    w.single_input.setPlainText(ed_frame.hex())
    w.parse_single()
    labels2 = [
        str(w.result_table_widget.item(r, 0).text())
        for r in range(w.result_table_widget.rowCount())
        if w.result_table_widget.item(r, 0)
    ]
    check("自动解包后含业务字段",
          any("MSDU" in x or "消息类型" in x or "关联" in x for x in labels2),
          str(labels2[:20]))

    section("[5] 协议11 4字节反转")
    # 4 字节一组：输入 00000100 → 反转后 00010000；用 parse 后回写到输入框的 hex 验证
    sample = "0102030405060708"
    w.ed_monitor_chk.setChecked(False)
    w.csg_reverse_4byte_chk.setChecked(True)
    w.csg_strip_head_spin.setValue(0)
    w.csg_strip_tail_spin.setValue(0)
    w.single_input.setPlainText(sample)
    # 直接调用反转逻辑（parse_single 会把 hex 回写为反转后的字节）
    reversed_hex = w._reverse_4byte_groups(sample)
    check("反转结果 = 0403020108070605", reversed_hex == "0403020108070605", reversed_hex)
    w.parse_single()
    back = w.single_input.toPlainText().replace(" ", "").upper()
    check("解析后输入框已是反转字节", back.startswith("0403020108070605"), back)
    w.csg_reverse_4byte_chk.setChecked(False)

    section("[6] 协议11 勾选 ED 且帧不完整 → 明确报错")
    truncated = ed_frame[:12]  # 远短于声明长度
    errs = []
    original_critical = QMessageBox.critical

    def _capture(*a, **k):
        errs.append(a)
        return 0

    with patch.object(QMessageBox, "critical", _capture):
        w.ed_monitor_chk.setChecked(True)
        w.single_input.setPlainText(truncated.hex())
        w.parse_single()
    check("出现 ED 错误弹窗", any("ED" in str(a) for a in errs), str(errs[:2]))

    section("[7] 协议10 抽样")
    w._on_protocol_changed(10)
    w.ed_monitor_chk.setChecked(True)
    w.csg_reverse_4byte_chk.setChecked(False)
    w.single_input.setPlainText(ed_frame.hex())
    w.parse_single()
    labels10 = [
        str(w.result_table_widget.item(r, 0).text())
        for r in range(w.result_table_widget.rowCount())
        if w.result_table_widget.item(r, 0)
    ]
    check("协议10 ED 解包后非空", len(labels10) > 0, str(labels10[:8]))
    check("协议10 含监控或业务字段",
          any(("监控" in x or "ED" in x or "MSDU" in x or "MMTYPE" in x or "MAC" in x
               or "业务帧" in x or "物理" in x) for x in labels10),
          str(labels10[:20]))

    w.close()
    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    if FAILED:
        for n in FAILED:
            print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
