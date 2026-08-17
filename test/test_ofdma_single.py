# -*- coding: utf-8 -*-
"""验证单帧解析 parse_single 路径"""

import _path_setup  # noqa: E402

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

# 单帧解析流程
w.single_input.setPlainText(hex_str)
w.parse_single()

# 检查结果表
print("=== 单帧解析结果 ===")
# parse_single 填充 result_table，检查是否有失败
print("(parse_single 已执行)")

# 直接调用底层看 ED 提取 + 解析
biz, dtype = w._extract_business_from_ed_frame(hex_str)
print(f"ED提取: {len(biz)//2}B type={dtype}")
if biz:
    from csg_new_gen_parser import CSGNewGenParser
    p = CSGNewGenParser()
    biz_bytes = bytes.fromhex(biz)
    result = p.parse_to_table(biz_bytes)
    fails = [r for r in result if "失败" in str(r[0])]
    print(f"解析行数: {len(result)}, 失败行: {len(fails)}")
    for f in fails:
        print(f"  ❌ {f[0]}: {f[3]}")

# 检查 _parse_ed_monitor_header 是否处理这种帧
meta, business, bo = w._parse_ed_monitor_header(bytes.fromhex(hex_str))
print(f"\n_parse_ed_monitor_header: meta={'OK' if meta else 'None'} business_len={len(business) if business else 0}")

