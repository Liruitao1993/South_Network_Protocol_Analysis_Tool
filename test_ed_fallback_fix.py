# -*- coding: utf-8 -*-
"""验证：勾选「ED监控协议」后不完整 ED 帧不再被当作 FC 起始符解析

背景：用户粘贴 ED..EE 监控包装帧（勾选 ED监控协议），当帧不完整/格式错误时，
旧逻辑静默回退，把 ED 首字节交给 CSGNewGenParser 当 FC 起始符解析。
修复后三处路径（单帧 parse_single / 解析弹窗 _preprocess / 批量解析）均必须
明确报错，不得回退。

运行: python test_ed_fallback_fix.py
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMessageBox
from unittest.mock import patch

app = QApplication([])

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}" + (f" ({detail})" if detail else ""))
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f" ({detail})" if detail else ""))


def make_valid_ed_frame(business: bytes, ctrl1=0x00, ctrl2=0x02, ch=0x01,
                        ts=0x11223344, pb_cnt=0x01, pb_len=None) -> bytes:
    """构造完整合法的 PLC2.0 ED..EE 包装帧"""
    if pb_len is None:
        pb_len = len(business)
    data域 = bytes([ch]) + ts.to_bytes(4, "little") + bytes([pb_cnt, 0x00]) \
        + pb_len.to_bytes(2, "little") + business
    body = bytes([ctrl1, ctrl2, 0xEF]) + data域
    frame_len = len(body) + 1  # +CS
    calc_cs = sum(bytes([0xED]) + frame_len.to_bytes(2, "little") + body) & 0xFF
    return (bytes([0xED]) + frame_len.to_bytes(2, "little") + body
            + bytes([calc_cs, 0xEE]))


# ── 用户报文（截断形态，帧长声明 549 → 整包 553，实际 135 字节） ──
USER_FRAME_HEX = (
    "ED 25 02 00 02 EF 01 D5 38 87 7E 01 00 08 02 09 01 20 00 04 1B "
    "03 00 16 06 00 00 20 D6 B6 25 00 00 00 00 " + "FF " * 100)
USER_FRAME = bytes.fromhex(USER_FRAME_HEX)

print("1. 前置：头解析器对不完整帧返回失败")
from main_gui import MainWindow
w = MainWindow()
rows, business, off = w._parse_ed_monitor_header(USER_FRAME)
check("不完整帧返回 None", rows is None and business is None,
      f"len={len(USER_FRAME)} 声明整包={(USER_FRAME[1]|USER_FRAME[2]<<8)+4}")

# ── 2. 单帧 parse_single：勾选 ED 后不完整帧必须报错，不回退解析 ──
print("2. 单帧解析 parse_single")
with patch.object(QMessageBox, 'critical') as mock_crit:
    w.current_protocol = 9
    w.ed_monitor_chk.setChecked(True)
    w.single_input.setPlainText(USER_FRAME_HEX)
    w.parse_single()
    check("弹出错误提示（未回退解析）", mock_crit.called)
    msg = mock_crit.call_args[0][2] if mock_crit.called else ""
    check("错误信息说明报文不完整", "不完整或格式错误" in msg, msg[:60])
    check("表格未被填充 FC 解析结果",
          not any("FC" in str(w.result_table_widget.item(r, 0).text())
                  for r in range(w.result_table_widget.rowCount())
                  if w.result_table_widget.item(r, 0)))
    # 不勾选 → 维持现状：原始帧直接交解析器（可能通用报错），但不触发 ED 专属报错
    calls_before = len(mock_crit.call_args_list)
    w.ed_monitor_chk.setChecked(False)
    w.single_input.setPlainText(USER_FRAME_HEX)
    w.parse_single()
    new_msgs = [str(c.args[2]) if len(c.args) > 2 else ""
                for c in mock_crit.call_args_list[calls_before:]]
    check("不勾选时不触发 ED 专属报错",
          not any("ED 监控帧解析失败" in m for m in new_msgs), ";".join(new_msgs)[:60])

# ── 3. 单帧 parse_single：完整合法 ED 帧回归 ──
print("3. 单帧解析：完整合法 ED 帧回归")
biz = bytes.fromhex("0901200004" + "1B03001606000020D6B625" + "00000000")
valid_ed = make_valid_ed_frame(biz)
with patch.object(QMessageBox, 'critical') as mock_crit:
    w.ed_monitor_chk.setChecked(True)
    w.single_input.setPlainText(valid_ed.hex().upper())
    w.parse_single()
    check("完整 ED 帧不报错", not mock_crit.called)
    labels = [str(w.result_table_widget.item(r, 0).text())
              for r in range(w.result_table_widget.rowCount())
              if w.result_table_widget.item(r, 0)]
    check("前置 PLC2.0 监控包装头行", any("PLC2.0" in l for l in labels))
    check("业务帧分隔行存在", any("业务帧" in l for l in labels))

# ── 4. 批量解析：ED 提取失败行明确报错 ──
print("4. 批量解析")
w.current_protocol = 9
# _strip_csg_new_gen_frame_prefix 对 ED 行直接保留 → 提取函数拿到整行
w.batch_input.setPlainText(USER_FRAME_HEX)
w.parse_batch()
check("批量产生 1 条结果", len(w.batch_results) == 1,
      f"n={len(w.batch_results)}")
if w.batch_results:
    r0 = w.batch_results[0]
    check("状态为失败", r0["_status"] == "失败", r0["_status"])
    check("摘要为 ED 帧解析失败", "ED 帧解析失败" in r0["摘要"], r0["摘要"])
    td = r0["_table_data"]
    check("未送 FC 解析器（表格无起始符行）",
          not any("起始符" in str(row[0]) for row in td))

# 合法完整 ED 帧批量回归：正常提取业务帧
w.batch_input.setPlainText(valid_ed.hex().upper())
w.parse_batch()
ok = (len(w.batch_results) == 1
      and w.batch_results[0]["_status"] == "成功"
      and "FC+Payload" in w.batch_results[0]["摘要"])
check("完整 ED 帧批量解析成功", ok,
      w.batch_results[0]["摘要"] if w.batch_results else "无结果")

# ── 5. 解析弹窗（热键/命令行/右键菜单共用路径） ──
print("5. 解析弹窗 _parse_and_show_dialog")
from PySide6.QtWidgets import QLabel
w._parse_and_show_dialog(USER_FRAME, initial_protocol=9)
app.processEvents()
err_labels = [l for l in app.allWidgets()
              if isinstance(l, QLabel) and "ED 监控帧解析失败" in l.text()]
check("弹窗显示 ED 错误提示", len(err_labels) > 0)
for d in list(app.topLevelWidgets()):
    d.close()

print(f"\n结果: {passed} 通过, {failed} 失败")
raise SystemExit(1 if failed else 0)
