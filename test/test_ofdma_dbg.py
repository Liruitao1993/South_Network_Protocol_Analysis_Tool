# -*- coding: utf-8 -*-
"""调试 0x0005 OFDMA 解析的 ext_data 切分"""

import _path_setup  # noqa: E402

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from csg_new_gen_parser import CSGNewGenParser
from csg_new_gen_cmd_payloads import _parse_cmd_test_frame

p = CSGNewGenParser()

# 从 ED 信封中提取的业务数据（之前测试确认是 152 字节 FC+Payload）
hex_str = "EDA5000002EF0100000000010088000901F0FFFE0000417804205B100000000000000003002B00FFFFFF001F0112000301110101000260F00100001D0004001900010405000109FFFFFF1B02FF01FF0F000020CD683401020304ED53570000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000FFEE"
frame_bytes = bytes.fromhex(hex_str)

# 手动提取业务数据（跳过 ED 信封：ED+帧长2+ctrl1+ctrl2+EF = 6字节，公共头9字节 = 15字节）
biz = frame_bytes[15:-2]  # 去掉最后 CS+EE
print(f"业务数据: {len(biz)} 字节")
print(f"  {biz.hex(' ').upper()}")

# 找到应用层测试命令 payload：业务数据里搜索 F0 01 00 00 (业务标识F0 + 应用版本 + 帧序号)
# 测试命令 payload 起点 = 应用层数据区
# 直接找到 60 F0 01 00 00 1D 00 04 00 ... (控制域 02 60, 业务标识 F0, 版本 01, 序号 00 00, 帧长 1D 00)
idx = biz.hex().upper().find("02" + "60" + "F0" + "01" + "0000" + "1D00")
print(f"测试命令位置: {idx//2 if idx>=0 else 'not found'}")
if idx >= 0:
    start = idx // 2
    cmd = biz[start:]
    print(f"测试命令 payload ({len(cmd)}B): {cmd.hex(' ').upper()}")
    print()
    # 测试帧结构: 测试ID(1) 保留(1) 数据区长度(2)
    print(f"测试ID={cmd[0]:#04x} 保留={cmd[1]:#04x} 数据区长度={int.from_bytes(cmd[2:4],'little')}")
    dl = int.from_bytes(cmd[2:4], "little")
    # 测试数据区
    tdata = cmd[4:4+dl]
    print(f"测试数据区({len(tdata)}B): {tdata.hex(' ').upper()}")
    # 2.0: 协议版本号 文件长度 扩展ID
    print(f"协议版本号={tdata[0]} 文件长度={tdata[1]} 扩展ID={int.from_bytes(tdata[2:4],'little')}")
    ext_data = tdata[4:]
    print(f"ext_data({len(ext_data)}B): {ext_data.hex(' ').upper()}")
    print(f"  [0]={ext_data[0]:02X} [1]={ext_data[1]:02X} [2]={ext_data[2]:02X} [3]={ext_data[3]:02X} [4]={ext_data[4]:02X}")
    print()
    # 按代码解析（从字节3）
    print("=== 代码解析结果 (从data[3]) ===")
    table = _parse_cmd_test_frame(cmd, 0, start)
    for r in table:
        print(f"  {r[0]}: {r[1]} / {r[2]} / {r[3]}")

