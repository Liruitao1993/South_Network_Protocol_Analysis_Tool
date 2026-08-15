# -*- coding: utf-8 -*-
"""精确验证用户帧的 ext_data 切分与 0x0005 解析"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from csg_new_gen_cmd_payloads import _parse_test_ext_0005, _parse_test_ext_0005 as p5
import struct

# 从解析输出反推：测试ID offset 46, 数据区长度 offset 48-49, 测试数据区 offset 50
# 构造测试命令 payload（从业务数据 offset 46 开始）
# 用户帧业务数据（ED提取后）的 offset 46 附近
hex_str = "EDA5000002EF0100000000010088000901F0FFFE0000417804205B100000000000000003002B00FFFFFF001F0112000301110101000260F00100001D0004001900010405000109FFFFFF1B02FF01FF0F000020CD683401020304ED53570000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000FFEE"
frame_bytes = bytes.fromhex(hex_str)
biz = frame_bytes[15:-2]  # 业务数据（跳过 ED 信封 6 字节 + 公共头 9 字节）

# 在业务数据里定位测试命令（搜 F0 业务标识）
# 应用层: ... 01 11 01 01 00 02 60 F0 01 00 00 1D 00 04 00 19 00 01 04 05 00 01 09 ...
# 测试命令 payload 从测试ID开始: 04 00 19 00 01 04 05 00 01 09 FF FF FF 1B 02 FF 01 FF 0F 00 00 20 CD 68 34 01 02 03 04 ED 53 57 00 00
# 搜 04 00 19 00 (测试ID 04 + 保留 00 + 数据区长度 19 00)
target = bytes([0x04, 0x00, 0x19, 0x00])
idx = biz.find(target)
print(f"测试命令定位: {idx}")
if idx < 0:
    # 尝试其他
    target2 = bytes([0x04, 0x00])
    idx = biz.find(target2)
    print(f"  fallback 04 00: {idx}")

payload = biz[idx:]
print(f"测试命令 payload ({len(payload)}B):")
print(f"  {payload.hex(' ').upper()}")

# 测试帧结构
test_id = payload[0]
reserved = payload[1]
data_len = int.from_bytes(payload[2:4], "little")
print(f"测试ID={test_id:#04x} 保留={reserved:#04x} 数据区长度={data_len}")

# 测试数据区
tdata = payload[4:4+data_len]
print(f"测试数据区 ({len(tdata)}B): {tdata.hex(' ').upper()}")
print(f"  协议版本号={tdata[0]} 文件长度={tdata[1]} 扩展ID={int.from_bytes(tdata[2:4],'little')}")
ext = tdata[4:]
print(f"ext_data ({len(ext)}B): {ext.hex(' ').upper()}")

# 按文档表格从字节3解析
print()
print("=== 按文档从 ext_data[3] 解析 ===")
for i, b in enumerate(ext):
    print(f"  ext[{i}]={b:02X}")
print()
# 手工解析站点
fc_type = (ext[3] >> 0) & 1
band = (ext[3] >> 1) & 7
efc_sym = (ext[3] >> 4) & 0xF
tf_sym = (ext[4] >> 0) & 0xF
sta_cnt = (ext[4] >> 4) & 0xF
print(f"帧类型={fc_type}({'UL' if fc_type else 'DL'}OFDMA) 频段={band} eFC符号数={efc_sym}")
print(f"TF符号数={tf_sym} 站点个数={sta_cnt}")
print()
# 站点
off = 5
for s in range(sta_cnt):
    if off + 3 > len(ext):
        print(f"站点{s}: 数据不足")
        break
    tei = ext[off] | ((ext[off+1] & 0xF) << 8)
    ru = (ext[off+1] >> 4) & 0xF
    tmi = ext[off+2] & 0x1F
    pb = (ext[off+2] >> 5) & 7
    print(f"站点{s}: TEI={tei} RU={ru} TMI={tmi} PB={pb}  [bytes {off}-{off+2}: {ext[off:off+3].hex(' ').upper()}]")
    off += 3
