# -*- coding: utf-8 -*-
"""模拟完整 parse_batch，输入完整 EDA5 帧"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from PySide6.QtWidgets import QApplication
from main_gui import MainWindow

app = QApplication([])
w = MainWindow()
w.current_protocol = 9

hex_str = "EDA5000002EF0100000000010088000901F0FFFE0000417804205B100000000000000003002B00FFFFFF001F0112000301110101000260F00100001D0004001900010405000109FFFFFF1B02FF01FF0F000020CD683401020304ED53570000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000FFEE"

w.batch_input.setPlainText(hex_str)
w.parse_batch()

print(f"batch_results 数量: {len(w.batch_results)}")
for i, r in enumerate(w.batch_results):
    print(f"\n帧{i}: status={r.get('_status')} 摘要={r.get('摘要')}")
    td = r.get("_table_data", [])
    if td:
        # 找失败行
        fails = [x for x in td if "失败" in str(x[0]) or "异常" in str(x[0])]
        print(f"  失败行: {len(fails)}")
        for f in fails[:3]:
            print(f"    {f[0]}: {f[3]}")
        print(f"  总行数: {len(td)}")
