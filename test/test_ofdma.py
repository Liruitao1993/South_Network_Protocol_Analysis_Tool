# -*- coding: utf-8 -*-
"""测试 EDA5 UL-OFDMA trigger 帧解析"""

import _path_setup  # noqa: E402

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication
from main_gui import MainWindow

app = QApplication([])
w = MainWindow()
w.current_protocol = 9

hex_str = "EDA5000002EF0100000000010088000901F0FFFE0000417804205B100000000000000003002B00FFFFFF001F0112000301110101000260F00100001D0004001900010405000109FFFFFF1B02FF01FF0F000020CD683401020304ED53570000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000FFEE"

frame_bytes = bytes.fromhex(hex_str)
print(f"总长度: {len(frame_bytes)} 字节")
print(f"前8字节: {frame_bytes[:8].hex(' ').upper()}")

# 看看 ED 提取结果
biz, dtype = w._extract_business_from_ed_frame(hex_str)
print(f"ED提取: business_len={len(biz)//2}B, type={dtype}")

# 尝试直接调 CSGNewGenParser 解析 business
if biz:
    from csg_new_gen_parser import CSGNewGenParser
    p = CSGNewGenParser()
    biz_bytes = bytes.fromhex(biz)
    print(f"\n业务数据长度: {len(biz_bytes)} 字节")
    print(f"业务数据前16字节: {biz_bytes[:16].hex(' ').upper()}")
    result = p.parse_to_table(biz_bytes)
    print(f"解析行数: {len(result)}")
    with open("test_ofdma_out.txt", "w", encoding="utf-8") as f:
        for i, row in enumerate(result):
            name = str(row[0])
            raw = str(row[1])
            parsed = str(row[2])
            comment = str(row[3])
            start = row[4]
            end = row[5]
            f.write(f"[{i:3d}] {name} | raw={raw} | parsed={parsed} | {comment} | offset={start}-{end}\n")
    print("结果写入 test_ofdma_out.txt")

