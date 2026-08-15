# -*- coding: utf-8 -*-
"""模拟 GUI 批量解析完整流程，看 EDA5 帧的最终结果"""
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

# 1. ED 提取
biz, dtype = w._extract_business_from_ed_frame(hex_str)
print(f"ED提取: {len(biz)//2}B, type={dtype}")

# 2. 帧提取
frames = w._extract_csg_new_gen_frames(hex_str)
print(f"帧提取: {len(frames)} 帧")
for i, (fh, dt) in enumerate(frames):
    print(f"  帧{i}: hex_len={len(fh)//2}B, ed_type={dt}")

# 3. 直接解析提取出的业务帧
from csg_new_gen_parser import CSGNewGenParser
p = CSGNewGenParser()
biz_bytes = bytes.fromhex(biz)
result = p.parse_to_table(biz_bytes)
print(f"\n解析: {len(result)} 行")
print(f"失败行: {[r for r in result if '失败' in str(r[0])]}")

# 4. 摘要
w.current_protocol = 9
summary = w._get_summary_from_table_data(result)
print(f"摘要: {summary}")

# 5. 检查 OFDMA 相关
print("\n=== OFDMA/eFC 相关行 ===")
for r in result:
    if any(k in str(r[0]) for k in ["OFDMA", "eFC", "站点", "扩展ID", "帧类型", "测试ID"]):
        print(f"  {r[0]}: {r[1]} / {r[2]} / {r[3]}")
