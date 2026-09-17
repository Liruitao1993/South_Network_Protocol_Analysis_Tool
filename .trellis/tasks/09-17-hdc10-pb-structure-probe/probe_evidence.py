# -*- coding: utf-8 -*-
"""协议11 PB 形态探测 —— 现场帧证据探针（可复现）

用途：任务 09-17-hdc10-pb-structure-probe 的根因证据固化。
运行：cd 项目根 && PYTHONPATH=. python3 .trellis/tasks/09-17-hdc10-pb-structure-probe/probe_evidence.py

结论（2026-09-17 实测）：
  1. FC 判定成立：DT=1(SOF) / 标准版本号=0(HDC 1.0) / FCCS 校验通过
  2. 按 data[16] 直接作 MAC 帧头 → ICV@102 == crc32(MSDU[44:102])  → 1/2^32 巧合不可能
  3. 按协议11 的 PBH 假设（MAC 头@17）→ MSDU 长度 = 1792（荒谬）
  4. 尾部 3 字节不是合法 PBCS（各种范围假设均不匹配）
"""

# 现场帧：FC 16B + PB（无 PBH）+ 41B 尾部填充
FRAME_HEX = (
    "01 55 E2 D4 33 F0 FF 03 D3 13 B6 42 00 BE AF B8 "
    "10 00 FF 3F 02 68 62 30 3A 00 CF 08 00 07 00 00 20 00 00 27 16 39 99 00 00 35 47 "
    "99 11 03 00 00 01 72 E3 02 D8 FF 14 06 68 2C 00 43 05 99 47 35 00 00 99 00 89 F8 "
    "10 00 08 05 01 00 20 10 02 00 00 01 10 37 19 A6 2F C5 FF 9E D0 A1 8E 62 EA 7E "
    "08 98 AA 0C BD 16 7A 1A 2B 55 " + "00 " * 41
)


def main():
    from hdc10_parser import HDC10Parser, _crc24, _crc32

    data = bytes.fromhex(FRAME_HEX)
    p = HDC10Parser()
    print(f"帧长 = {len(data)} 字节")
    print(f"FC 16B = {' '.join(f'{b:02X}' for b in data[:16])}")

    # 1. FC 判定
    print("\n[1] FC 判定")
    print(f"  DT = {data[0] & 0x07} (1=SOF帧), 标准版本号 = {(data[12] >> 4) & 0x0F} (0=HDC 1.0)")
    print(f"  FCCS 帧内值 = 0x{int.from_bytes(data[13:16], 'little'):06X}")
    print(f"  FCCS 计算值 = 0x{_crc24(data[:13]):06X}  → "
          f"{'✓ 校验通过' if _crc24(data[:13]) == int.from_bytes(data[13:16], 'little') else '✗ 不通过'}")
    print(f"  _detect_fc = {p._detect_fc(data)}")
    print(f"  data[16] = 0x{data[16]:02X} → bit7(结束)={data[16] >> 7 & 1} "
          f"bit6(起始)={data[16] >> 6 & 1} seq={data[16] & 0x3F}  ← 非合法 PBH")

    # 2. 形态判定：按 data[16] 作 MAC 头
    print("\n[2] 假设「无 PBH」（data[16] 即 MAC 头首字节）")
    mac_len, _ = p._parse_mac_header(data[16:], 0)
    ver = data[16] & 0x0F
    msdu_type = data[16 + 7]
    msdu_len = data[16 + 8] | ((data[16 + 9] & 0x07) << 8)
    msdu_start = 16 + mac_len
    msdu = data[msdu_start:msdu_start + msdu_len]
    icv_got = int.from_bytes(data[msdu_start + msdu_len:msdu_start + msdu_len + 4], 'little')
    icv_calc = _crc32(msdu)
    print(f"  版本={ver}(0=标准帧协议) MAC头长={mac_len} MSDU类型={msdu_type}(48=应用层报文) MSDU长度={msdu_len}")
    print(f"  MSDU 范围 = [{msdu_start}, {msdu_start + msdu_len - 1}]")
    print(f"  ICV@{msdu_start + msdu_len} = 0x{icv_got:08X}   crc32(MSDU) = 0x{icv_calc:08X}  → "
          f"{'✓ 完全相等（决定性证据）' if icv_got == icv_calc else '✗ 不等'}")

    # 3. 反证：按 PBH 假设
    print("\n[3] 反证「有 PBH」（MAC 头从 data[17] 起）")
    b7, b8 = data[17 + 8], data[17 + 9]
    print(f"  MSDU 类型 = {data[17 + 7]}, MSDU 长度 = {b7 | ((b8 & 0x07) << 8)}  ← 荒谬值")

    # 4. PBCS 假设
    print("\n[4] 尾部 3 字节是否为合法 PBCS")
    tail3 = int.from_bytes(data[-3:], 'little')
    print(f"  尾3B 帧内值 = 0x{tail3:06X}（全 0 → 无 PBCS 或日志填充）")
    for label, rng in (("含PBH data[16:-3]", data[16:-3]), ("不含PBH data[17:-3]", data[17:-3])):
        print(f"  crc24({label}) = 0x{_crc24(rng):06X}")

    # 5. 模拟修复
    print("\n[5] 模拟修复：_parse_mac_frame(data[16:], 16)")
    rows = p._parse_mac_frame(data[16:], 16)
    print(f"  行数 = {len(rows)}（改动前协议11 auto 仅 17 行，且无业务内容）")
    for r in rows:
        name = str(r[0]).strip()
        if name in ("报文端口号", "报文ID", "转发数据规约类型", "转发数据长度", "完整性校验值(ICV)",
                    "原始源TEI", "原始目的TEI", "MSDU类型", "MSDU长度", "原始源MAC地址", "原始目的MAC地址"):
            print(f"    {name}: {r[2]}  | {r[3]}")

    # 6. 协议10 对照
    print("\n[6] 协议10 对照（GWNewGenParser）")
    from gw_new_gen_parser import GWNewGenParser
    g = GWNewGenParser().parse_to_table(data, "auto")
    print(f"  行数 = {len(g)}（改动前即如此 —— 两协议结果不一致即为缺陷）")

    # 7. 改动前的协议11 基线
    print("\n[7] 协议11 改动前基线")
    t = p.parse_to_table(data, "auto")
    print(f"  auto 行数 = {len(t)}；末行 = {t[-1]}")


if __name__ == "__main__":
    main()
