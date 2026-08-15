# -*- coding: utf-8 -*-
"""穷举 ext_data 各种偏移，找能解出站点个数=2(文档说只写2站点)的布局"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

# 用户帧 ext_data (21字节)
ext = bytes([0x01,0x09,0xFF,0xFF,0xFF,0x1B,0x02,0xFF,0x01,0xFF,0x0F,0x00,0x00,0x20,0xCD,0x68,0x34,0x01,0x02,0x03,0x04])

print("ext_data:", ext.hex(" ").upper())
print("len:", len(ext))
print()

# 站点个数位置假设：byte_offset 处的高4位/低4位/整字节 = 2
print("=== 找值=2 的字节 ===")
for i, b in enumerate(ext):
    if b == 2:
        print(f"  ext[{i}]={b:02X} (整字节=2)")
    if (b >> 4) == 2:
        print(f"  ext[{i}]={b:02X} 高4位=2")
    if (b & 0xF) == 2:
        print(f"  ext[{i}]={b:02X} 低4位=2")

# 站点个数在文档表格7是"字节4 比特位4-7"，即 offset4 的高4位
# 若字段基准偏移 d，则站点个数 = ext[4-d] 高4位（当 d>=0）或 ext[4+d]（当d<0）
print()
print("=== 字段基准偏移测试：站点个数应为2 ===")
for d in range(-6, 7):
    pos = 4 - d  # 文档字节4 对应 ext 的哪一位
    if 0 <= pos < len(ext):
        sta_cnt = (ext[pos] >> 4) & 0xF
        if sta_cnt == 2:
            print(f"  偏移d={d}: 站点个数从 ext[{pos}] 高4位 = {sta_cnt}  ✓ 站点个数=2!")
            # 这偏移下帧类型=ext[3-d] bit0
            ft_pos = 3 - d
            if 0 <= ft_pos < len(ext):
                ft = ext[ft_pos] & 1
                print(f"    → 帧类型=ext[{ft_pos}]bit0={ft} ({'UL' if ft else 'DL'}OFDMA)")
            # 站点0 = ext[5-d:8-d]
            s0 = 5 - d
            if 0 <= s0+2 < len(ext):
                tei = ext[s0] | ((ext[s0+1]&0xF)<<8)
                ru = (ext[s0+1]>>4)&0xF
                tmi = ext[s0+2]&0x1F
                pb = (ext[s0+2]>>5)&7
                print(f"    → 站点0(TEI={tei}, RU={ru}, TMI={tmi}, PB={pb})  bytes {s0}-{s0+2}")
                s1 = s0 + 3
                if 0 <= s1+2 < len(ext):
                    tei1 = ext[s1] | ((ext[s1+1]&0xF)<<8)
                    ru1 = (ext[s1+1]>>4)&0xF
                    tmi1 = ext[s1+2]&0x1F
                    pb1 = (ext[s1+2]>>5)&7
                    print(f"    → 站点1(TEI={tei1}, RU={ru1}, TMI={tmi1}, PB={pb1})  bytes {s1}-{s1+2}")
