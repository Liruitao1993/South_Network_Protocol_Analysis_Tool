# -*- coding: utf-8 -*-
"""monitor_widget 功能验证（临时脚本，验证后可删除）"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from monitor_widget import RealtimeMonitorWidget
from csg_new_gen_parser import CSGNewGenParser
from gw_new_gen_parser import GWNewGenParser

app = QApplication([])

# 南网新一代测试帧（占位符示例帧）
CSG_FRAME = bytes.fromhex("11 01 01 00 00 00 00 01 00 01 00 00".replace(" ", ""))
# 国网新一代测试帧
GW_FRAME = bytes.fromhex("ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00".replace(" ", ""))

sent_to_single = []


def summary_fn(table_data):
    # 简化摘要：取首行字段名
    return f"字段数:{len(table_data)}"


# ---------- 用例1：南网新一代，分段发送组帧 ----------
w = RealtimeMonitorWidget()
w.interval_spin.setValue(30)
w.set_protocol(CSGNewGenParser(), summary_fn)
w.set_send_to_single_handler(lambda h: sent_to_single.append(h))
# 本用例验证静默间隔组帧，关闭监控包装解帧(默认开启)以走静默定时器路径
w.deframe_chk.setChecked(False)

# 模拟串口分两帧分段到达（间隔<30ms → 应组为一帧）
w._on_raw_data(CSG_FRAME[:5])
w._on_raw_data(CSG_FRAME[5:])
QTest.qWait(80)  # 等静默超时触发组帧
assert len(w._frames) == 1, f"组帧失败: {len(w._frames)}"
rec = w._frames[0]
assert rec["length"] == len(CSG_FRAME), f"长度错误: {rec['length']}"
assert rec["table_data"], "解析结果为空"
assert rec["summary"].startswith("字段数:"), f"摘要异常: {rec['summary']}"
assert w.frame_table.rowCount() == 1
print(f"[用例1] 分段组帧+解析 OK, 摘要={rec['summary']}, 首字段={rec['table_data'][0][0]}")

# ---------- 用例2：两帧分开到达（间隔>30ms → 两帧）----------
w._on_raw_data(CSG_FRAME)
QTest.qWait(80)
w._on_raw_data(CSG_FRAME)
QTest.qWait(80)
assert len(w._frames) == 3, f"应为3帧: {len(w._frames)}"
print("[用例2] 独立两帧识别 OK")

# ---------- 用例3：选中帧 → 详情+HEX ----------
w.frame_table.setCurrentCell(0, 0)
QTest.qWait(10)
assert w.detail_table.rowCount() == len(w._frames[0]["table_data"]), "详情行数不符"
assert w.hex_text.toPlainText() == w._frames[0]["hex"], "HEX不符"
# 点击详情行 → 高亮（只要有字节范围即生成 ExtraSelection）
w.detail_table.setCurrentCell(0, 0)
QTest.qWait(10)
print(f"[用例3] 详情展示 OK, 详情行数={w.detail_table.rowCount()}, 高亮数={len(w.hex_text.extraSelections())}")

# ---------- 用例4：双击送单帧 ----------
w._on_frame_double_clicked(1, 0)
assert len(sent_to_single) == 1 and sent_to_single[0] == w._frames[1]["hex"], "双击送单帧失败"
print("[用例4] 双击送单帧 OK")

# ---------- 用例5：暂停丢弃数据 ----------
w.pause_btn.setChecked(True)
n = len(w._frames)
w._on_raw_data(CSG_FRAME)
QTest.qWait(80)
assert len(w._frames) == n, "暂停时不应新增帧"
w.pause_btn.setChecked(False)
print("[用例5] 暂停接收 OK")

# ---------- 用例6：国网新一代协议切换（清空+解析）----------
w.set_protocol(GWNewGenParser(), summary_fn)
assert len(w._frames) == 0 and w.frame_table.rowCount() == 0, "切换协议未清空"
w._on_raw_data(GW_FRAME)
QTest.qWait(80)
assert len(w._frames) == 1, f"国网帧未识别: {len(w._frames)}"
rec = w._frames[0]
print(f"[用例6] 国网新一代协议 OK, 摘要={rec['summary']}, 首字段={rec['table_data'][0][0] if rec['table_data'] else '无'}")

# ---------- 用例7：清空 ----------
w.clear_frames()
assert len(w._frames) == 0 and w.frame_table.rowCount() == 0 and w.detail_table.rowCount() == 0
print("[用例7] 清空 OK")

print("\n全部用例通过")
