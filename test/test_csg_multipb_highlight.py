# -*- coding: utf-8 -*-
"""多物理块重组解析高亮偏移回归测试

背景：MAC 帧跨多个 PB 时，重组解析（MAC头/MSDU/应用层行）的偏移处于
concat 拼接缓冲区坐标，未翻译回原始帧会导致点击行高亮错位（用户报告：
4-PB 帧重组后点击行无法定位原始报文位置）。

覆盖：
  1. 合成 2-PB 跨块 MAC 帧：所有「raw 为完整 hex 切片」的行偏移必须与
     原始帧切片自洽（row raw == frame[start:end+1]）
  2. 存在落在第二个 PB 体区域的重组解析行（证明跨块行被正确翻译）
  3. 单 PB 帧映射恒等（既有行为不变）
  4. 非 PB 帧（直接应用层输入）不受上一帧映射残留影响

直接运行: python test_csg_multipb_highlight.py
"""

import _path_setup  # noqa: E402

import zlib

FAILURES = []
PASS = 0


def check(name, cond, detail=""):
    global PASS
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASS += 1
    else:
        FAILURES.append(name)


PB_TOTAL = 520
PB_HDR = 4
PB_BODY = 512  # 520 - PBH4 - 保留1 - PBCS3


def _build_mac_frame(total_len: int) -> bytes:
    """构造版本1 MAC 帧：12B 头(含MSDU长度) + 短 MSDU 头(2B) + 应用层载荷 + CRC-32"""
    app_payload = bytes((i * 7 + 1) & 0xFF for i in range(total_len - 12 - 2 - 4))
    msdu = bytes([0x01, 0x01]) + app_payload  # VLAN=0x01 类型=0x01
    # 12B 头: b0=0x03(版本1) b1=0 字节2-3=MSDU长度(小端) 其余置0
    mac = bytes([0x03, 0x00]) + len(msdu).to_bytes(2, "little") + bytes(8) + msdu
    mac += zlib.crc32(mac).to_bytes(4, "little")
    return mac


def _build_multipb_frame(mac: bytes, pb_count: int, pb_total: int = 520) -> bytes:
    """FC(SOF, pb_count, PB=520) + N×(PBH4+body512+保留1+PBCS3)，MAC 跨块拼接"""
    body_size = pb_total - 8
    fc = bytearray(16)
    fc[0] = 0x09  # SOF + 接入指示
    fc[7] = (pb_count & 0x0F) | 0xD0  # 物理块个数 | TMI=0xD → PB=520 (BPLC 表20)
    fc[12] = 0x10  # 标准版本=1 (BPLC)
    frame = bytes(fc)
    pos = 0
    for i in range(pb_count):
        body = mac[pos : pos + body_size]
        body = body + b"\x00" * (body_size - len(body))
        pos += body_size
        pbh = (i).to_bytes(2, "little") + bytes([0x00, 0x00])  # 序号+聚合标志0
        pb_bytes = pbh + body
        crc = zlib.crc32(pb_bytes + b"\x00") & 0xFFFFFF  # 含保留字节占位
        frame += pb_bytes + b"\x00" + crc.to_bytes(3, "little")
    return frame


def _row_offset_consistency(table, frame_bytes):
    """raw 为完整 hex 切片的行：偏移必须与原始帧切片一致；返回(检查数, 错配列表)"""
    checked, bad = 0, []
    for name, raw, parsed, desc, s, e in table:
        if s is None or e is None:
            continue
        hexraw = "".join(str(raw).split())
        if not hexraw or not all(c in "0123456789abcdefABCDEF" for c in hexraw):
            continue
        if len(hexraw) != (e - s + 1) * 2:
            continue
        checked += 1
        if frame_bytes[s : e + 1].hex().upper() != hexraw.upper():
            bad.append((name, s, e))
    return checked, bad


def main():
    from csg_new_gen_parser import CSGNewGenParser

    # ── 1+2: 2-PB 跨块 MAC 帧 ──
    mac = _build_mac_frame(700)  # > 516 → 跨 2 个 PB
    frame = _build_multipb_frame(mac, 2)
    p = CSGNewGenParser()
    table = p.parse_to_table(frame)
    checked, bad = _row_offset_consistency(table, frame)
    check("2-PB 行偏移自洽(检查%d行)" % checked, checked >= 8 and not bad, f"bad={bad[:5]}")
    pb0_body_end = 16 + PB_HDR + PB_BODY
    deep = [r for r in table if r[4] is not None and r[4] > pb0_body_end]
    check("存在跨块(第二PB体)重组行", len(deep) > 0, f"deep={len(deep)}")
    # 业务数据单元行：偏移必须落在跨块映射后的原始位置（raw 首字节自洽）
    sdu_rows = [r for r in table if str(r[0]).strip() == "业务数据单元"]
    if sdu_rows:
        r = sdu_rows[0]
        ok = (
            r[4] is not None
            and frame[r[4] : r[4] + 4].hex().upper()
            == "".join(str(r[1]).split())[:8].upper()
        )
        check("业务数据单元行偏移自洽", ok, f"row=({r[4]},{r[5]}) raw={str(r[1])[:16]}")
    mac_rows = [r for r in table if str(r[0]).strip() in ("帧头类型", "版本", "MSDU长度")]
    check("MAC 头重组行存在", len(mac_rows) >= 3, f"names={[r[0] for r in mac_rows]}")

    # ── 3: 单 PB 恒等（既有行为）──
    mac1 = _build_mac_frame(300)
    frame1 = _build_multipb_frame(mac1, 1)
    table1 = CSGNewGenParser().parse_to_table(frame1)
    checked1, bad1 = _row_offset_consistency(table1, frame1)
    check("单PB行偏移自洽(检查%d行)" % checked1, checked1 >= 6 and not bad1, f"bad={bad1[:5]}")

    # ── 3b: 4-PB 跨块（用户真实场景规模：1982 字节业务数据单元）──
    mac4 = _build_mac_frame(2000)
    frame4 = _build_multipb_frame(mac4, 4)
    table4 = CSGNewGenParser().parse_to_table(frame4)
    checked4, bad4 = _row_offset_consistency(table4, frame4)
    check("4-PB 行偏移自洽(检查%d行)" % checked4, checked4 >= 10 and not bad4,
          f"bad={bad4[:5]}")
    deep4 = [r for r in table4 if r[4] is not None and r[4] > pb0_body_end]
    check("4-PB 存在跨块重组行", len(deep4) > 0, f"deep={len(deep4)}")

    # ── 4: 非 PB 帧不受上一帧映射残留影响 ──
    p2 = CSGNewGenParser()
    p2.parse_to_table(frame)  # 先解析多 PB 帧（设置映射）
    app_only = mac1[12:]  # 直接 MSDU 负载输入（无 FC/PB）
    table2 = p2.parse_to_table(app_only)
    checked2, bad2 = _row_offset_consistency(table2, app_only)
    check("非PB帧无映射残留(检查%d行)" % checked2, checked2 >= 2 and not bad2, f"bad={bad2[:5]}")

    print("=" * 56)
    if FAILURES:
        print(f"共 {len(FAILURES)} 项失败: {FAILURES}")
        raise SystemExit(1)
    print(f"全部测试通过（{PASS} 项）✓")


if __name__ == "__main__":
    main()
