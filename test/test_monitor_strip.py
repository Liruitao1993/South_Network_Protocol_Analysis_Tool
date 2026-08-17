# -*- coding: utf-8 -*-
"""监控器剔除字节功能验证（临时脚本）"""

import _path_setup  # noqa: E402

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from monitor_widget import RealtimeMonitorWidget
from csg_new_gen_parser import CSGNewGenParser

app = QApplication([])

CSG = bytes.fromhex("110101000000000100010000")
WRAP = bytes([0xAA, 0xBB, 0xCC]) + CSG + bytes([0x12, 0x34])  # 头3 + CSG + 尾2
CSG_HEX = " ".join(f"{b:02X}" for b in CSG)


def summ(td):
    return f"字段:{len(td)}"


# ---------- 场景A：先收帧（不剔除），后设置剔除参数 → 已收帧应重新解析 ----------
w = RealtimeMonitorWidget()
w.set_protocol(CSGNewGenParser(), summ)
w.deframe_chk.setChecked(False)  # 关闭监控解帧，走静默间隔+剔除路径
w._on_raw_data(WRAP)
QTest.qWait(80)
assert len(w._frames) == 1 and w._frames[0]["length"] == len(WRAP)
print("A1 收帧(未剔除) OK, 长度:", w._frames[0]["length"])

# 设置剔除头3尾2 → 触发重新解析已收帧
w.strip_head_spin.setValue(3)
w.strip_tail_spin.setValue(2)
rec = w._frames[0]
assert rec["length"] == len(CSG), f"重解析后长度错误:{rec['length']}"
assert rec["hex"] == CSG_HEX, "重解析后HEX不符"
assert rec["ok"], f"重解析后应成功: {rec['summary']}"
# 列表行也应更新
assert w.frame_table.item(0, 3).text() == str(len(CSG)), "列表长度列未刷新"
print("A2 改参数后重解析已收帧 OK:", rec["summary"], "首字段:", rec["table_data"][0][0])

# ---------- 场景B：设好参数后新收帧直接剔除解析 ----------
w._on_raw_data(WRAP)
QTest.qWait(80)
rec = w._frames[1]
assert rec["length"] == len(CSG) and rec["hex"] == CSG_HEX and rec["ok"]
print("B 新帧直接剔除解析 OK:", rec["summary"])

# ---------- 场景C：剔除过多保护 ----------
w.strip_head_spin.setValue(30)
w.strip_tail_spin.setValue(30)
rec = w._frames[0]
assert not rec["ok"] and "剔除字节过多" in rec["summary"], rec["summary"]
print("C 剔除过多保护 OK:", rec["summary"])

# ---------- 场景D：改回0 → 恢复原始解析 ----------
w.strip_head_spin.setValue(0)
w.strip_tail_spin.setValue(0)
rec = w._frames[0]
assert rec["length"] == len(WRAP), "改回0应恢复原始长度"
print("D 改回0恢复原始 OK, 长度:", rec["length"])

# ---------- 场景E：双击送单帧 → 送剔除后帧 ----------
sent = []
w.set_send_to_single_handler(lambda h: sent.append(h))
w.strip_head_spin.setValue(3)
w.strip_tail_spin.setValue(2)
w._on_frame_double_clicked(0, 0)
assert sent[0] == CSG_HEX, f"双击应送剔除后帧: {sent[0]}"
print("E 双击送剔除后帧 OK")

print("全部通过")

