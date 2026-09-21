# -*- coding: utf-8 -*-
"""协议11（HDC 1.0）ED..EE 监控包装帧批量解析回归

用户报障：协议11 下粘贴 ED..EE 包装帧（真实日志每帧 168B，帧尾 CS+EE = ``FF EE``）
无法解析——被当成应用层报文（端口 0xED / 业务 0x0A4 配电信息上报）。

根因（两条同时命中）：
  1. 协议11 的 ``extract_strategy="line"``，默认分支「每行一帧」**完全不做 ED 解包**
     （ED 解包只存在于协议9 的 ``csg_line`` 策略）→ 首字节 0xED 落到应用层解析；
  2. 既有解包路径硬编码 ``startswith("EDA5")`` + 固定剥 15 字节，而用户帧是 ``EDA4``
     且公共头是 gx（8B，应剥 14 字节）→ 双重不命中；即便泛化前缀也会多剥 1 字节错位。

修复：``batch_core`` 新增通用 ED 解包（``split_ed_frames`` / ``unwrap_ed_line`` /
``ed_wrapper_prefix_len``，公共头 plc2 9B / gx 8B 由 ``detect_ed_wrapper`` 判别），
协议10/11 的行提取改为 ED-aware（桌面 ``main_gui._extract_line_frames``、Web 同源）。

运行: python test/test_hdc10_ed_wrapper.py
"""

import os

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}" + (f" ({detail})" if detail else ""))
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f" ({detail})" if detail else ""))


# ── 用户现场真实帧（TMI 日志，gx 8B 公共头，帧长字段=0xA4=164 → 整帧 168B） ──
FRAME0 = bytes.fromhex(
    "EDA4000002EFC2D28E02010088000103000002F0FF034113794200E27700C020"
    "00FF2F01BEFA002680110800020000192168001101FFFFFFFFFFFF0800000002"
    "1000111921680011010000909801630119000000000001010000000000000001"
    "30817441BF000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000009BEF8EFFEE"
)
FRAME1 = bytes.fromhex(
    "EDA4000002EF978792020100880001302190001000032414794400E1AB90C000"
    "000100006324005C10FF08009600002000000001320101010101010000000020"
    "0000000132010000000000000000000203000400000132502847570090153430"
    "320200000000000000001904009711484A3430827B0000000B16006324000075"
    "B46D0AD739D44B4E341600003142435303FBC1019C0201200AF7FD0000000000"
    "000000BC5488FFEE"
)
FRAME2 = bytes.fromhex(
    "EDA4000002EF0CA09C020100880001302190001000032414794400E1AB90C000"
    "000100006324005C10FF08009600002000000001320101010101010000000020"
    "0000000132010000000000000000000203000400000132502847570090153430"
    "320200000000000000001904009711484A3430827B0000000B16006324000075"
    "B46D0AD739D44B4E341600003142435303FBC1019C0201200AF7FD0000000000"
    "000000BC5488FFEE"
)
# 既有 plc2（9B 公共头）TCP 包装样本：必须仍按 15 字节剥离（回归护栏）
EDA5_SAMPLE = (
    "EDA5000002EF0149C84C27010088000900F0FF010000417804005B10EA9809"
    "0000000003001300FF0F00001F0102000301110101000260F0010000050002"
    "00010002AD4353F8004A95AF" + "00" * 50 + "FFEE"
)
# 不完整 ED 帧（声明 549 → 整包 553，实际 135B 且以 FF 结尾，非 EE 终止）
INCOMPLETE_ED = (
    "ED 25 02 00 02 EF 01 D5 38 87 7E 01 00 08 02 09 01 20 00 04 1B "
    "03 00 16 06 00 00 20 D6 B6 25 00 00 00 00 " + "FF " * 100
).replace(" ", "")

print("1. 包装头长度判别（plc2 9B / gx 8B）")
import batch_core  # noqa: E402

check("真实帧判别为 gx → 剥 14B", batch_core.ed_wrapper_prefix_len(FRAME0.hex()) == 14,
      str(batch_core.ed_wrapper_prefix_len(FRAME0.hex())))
check("plc2 样本判别为 15B",
      batch_core.ed_wrapper_prefix_len(EDA5_SAMPLE) == 15,
      str(batch_core.ed_wrapper_prefix_len(EDA5_SAMPLE)))
check("不完整 ED 帧（非 EE 终止）不判为包装帧",
      batch_core.ed_wrapper_prefix_len(INCOMPLETE_ED) == 0)
check("非 ED 行不判为包装帧",
      batch_core.ed_wrapper_prefix_len("0900F0FF0100") == 0)

print("2. 一行多帧切分（监控日志常把多帧拼一行）")
joined = (FRAME0 + FRAME1 + FRAME2).hex().upper()
parts = batch_core.split_ed_frames(joined)
check("切出 3 帧", len(parts) == 3, f"n={len(parts)}")
check("逐帧与原始字节一致",
      [bytes.fromhex(p) for p in parts] == [FRAME0, FRAME1, FRAME2])
check("尾部残帧被丢弃（不产半帧）",
      len(batch_core.split_ed_frames(joined[:len(joined) - 40])) == 2)
check("非 ED 串返回空", batch_core.split_ed_frames("0900F0FF") == [])

print("3. ED 解包（协议11）")
unwrapped = batch_core.unwrap_ed_line(joined, 11)
check("解出 3 条业务帧", unwrapped is not None and len(unwrapped) == 3,
      f"n={len(unwrapped) if unwrapped else None}")
check("业务帧 152B（FC16 + PB136）",
      len(unwrapped[0][0]) // 2 == 152, str(len(unwrapped[0][0]) // 2))
check("业务帧以 FC 起始（非 0xED）", unwrapped[0][0].startswith("0103000002F0FF03"),
      unwrapped[0][0][:16])
check("ed_data_type 标记 FC+Payload", unwrapped[0][1] == "FC+Payload数据",
      unwrapped[0][1])
check("非 ED 行返回 None（调用方回退）",
      batch_core.unwrap_ed_line("0900F0FF0100", 11) is None)

print("4. 解包结果可被 HDC 解析器完整解析")
from hdc10_parser import HDC10Parser  # noqa: E402

rows = HDC10Parser().parse_to_table(bytes.fromhex(unwrapped[0][0]), parse_level="auto")
mmtype = next((r[2] for r in rows if str(r[0]).strip() == "消息类型(MMTYPE)"), None)
check("解出 MMTYPE 0x0008 发现列表", mmtype == "0x0008", str(mmtype))
check("FCCS 校验正确", any("校验正确" in str(r[3]) for r in rows if "FCCS" in str(r[0])))
check("PBCS 校验正确", any("PBCS" in str(r[0]) and "正确" in str(r[3]) for r in rows))

print("5. 协议11 行提取（batch_core.extract_frames_for_protocol）")
frames11 = batch_core.extract_frames_for_protocol(joined, 11)
check("协议11 提取 3 帧（原先 1 帧且未解包）", len(frames11) == 3, f"n={len(frames11)}")
check("提取帧为解包后业务帧",
      frames11[0][0].startswith("0103000002F0FF03"), frames11[0][0][:16])
check("带 ed_data_type", frames11[0][1] == "FC+Payload数据", frames11[0][1])
frames10 = batch_core.extract_frames_for_protocol(joined, 10)
check("协议10 同步生效（gw_line_min4）", len(frames10) == 3, f"n={len(frames10)}")
frames6 = batch_core.extract_frames_for_protocol(joined, 6)
check("协议6(DLT645) 不受影响（仍原样一行一帧）",
      len(frames6) == 1 and frames6[0][0] == joined, f"n={len(frames6)}")

print("6. 桌面端到端：协议11 批量解析真实帧")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from _batch_wait import wait_batch  # noqa: E402
import main_gui  # noqa: E402

win = main_gui.MainWindow()
win.current_protocol = 11
if hasattr(win, "_hdc10_parse_level"):
    win._hdc10_parse_level = "auto"
win.batch_input.setPlainText(joined)
win.parse_batch()
wait_batch(win)
check("批量产生 3 条结果", len(win.batch_results) == 3, f"n={len(win.batch_results)}")
if len(win.batch_results) == 3:
    check("全部状态成功",
          all(r["_status"] == "成功" for r in win.batch_results),
          str([r["_status"] for r in win.batch_results]))
    td = win._get_frame_table_data(0)
    check("详情含 MMTYPE 0x0008（发现列表）",
          any("0x0008" in str(row[2]) and "MMTYPE" in str(row[0]) for row in td))
    check("详情不含「应用层报文」误判",
          not any("应用层报文" in str(row[0]) for row in td))

# 一帧一行（每行独立）也应解包
win.batch_input.setPlainText("\n".join(
    f.hex().upper() for f in (FRAME0, FRAME1, FRAME2)))
win.parse_batch()
wait_batch(win)
check("一帧一行同样解出 3 帧", len(win.batch_results) == 3,
      f"n={len(win.batch_results)}")

print("7. 单帧解析路径（用户报障：单帧框贴 ED 帧仍按应用层解析）")
win.current_protocol = 11
win.single_input.setPlainText(FRAME0.hex().upper())
win.parse_single()
app.processEvents()
single_labels = [
    (str(win.result_table_widget.item(r, 0).text()),
     str(win.result_table_widget.item(r, 2).text()))
    for r in range(win.result_table_widget.rowCount())
    if win.result_table_widget.item(r, 0)
]
check("单帧解析含 MMTYPE 0x0008（发现列表）",
      any("MMTYPE" in a and "0x0008" in b for a, b in single_labels),
      str(single_labels[:3]))
check("单帧解析前置 ED 监控包装头行",
      any("监控包装头" in a for a, _ in single_labels))
check("单帧解析不含「应用层报文」误判",
      not any("应用层报文" in a for a, _ in single_labels))

print("8. 快捷解析弹窗路径（热键/命令行/右键菜单共用）")
from PySide6.QtWidgets import QTableWidget  # noqa: E402

win._parse_and_show_dialog(FRAME0, initial_protocol=11)
app.processEvents()
dlg_found = False
for t in app.allWidgets():
    if not isinstance(t, QTableWidget):
        continue
    for r in range(t.rowCount()):
        i0, i2 = t.item(r, 0), t.item(r, 2)
        if i0 and i2 and "MMTYPE" in i0.text() and "0x0008" in i2.text():
            dlg_found = True
check("快捷弹窗协议11 解出 MMTYPE 0x0008", dlg_found)
for d in list(app.topLevelWidgets()):
    d.close()
win.close()
win.deleteLater()
app.processEvents()

print(f"\n结果: {passed} 通过, {failed} 失败")
raise SystemExit(1 if failed else 0)
