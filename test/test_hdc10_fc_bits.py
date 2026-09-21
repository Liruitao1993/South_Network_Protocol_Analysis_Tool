# -*- coding: utf-8 -*-
"""HDC 1.0（协议11）FC 可变区域跨字节位域位序回归

用户报障：FC 的源TEI 解析错误——现场帧应为 2，却解析成 32；而 MAC 头里的 TEI 正确。

根因：FC 可变区域的跨字节位域按「首字节=高位」组装，而规范各表（表19/23/27/30/34）
的「字节号/比特位」列是 **LSB-first 位流**——位号小的一端是低位。MAC 头一直按
LSB-first 解析（`((b0>>4)&0x0F) | (b1<<4)`、`b2 | ((b3&0x0F)<<8)`），所以 MAC 对、
FC 错。

判定依据（两条独立实证，均落在同一帧）：
  * `广播标志位 = 比特1` → `(b11>>1)&1 = 1`，且该帧目的TEI 确为广播地址 4095；
  * `分集拷贝基本模式 = 比特4-7` → 4，而该帧物理块恰好 136 字节（模式4 = 136B）。

修复：新增 `hdc10_parser._bits_lsb(data, byte_off, bit_off, nbits)`，FC 可变区域
6 个解析函数的 源TEI/目的TEI/帧长/符号数 全部改用它（公式与规范比特位列一一对应）。

本测试的核心断言是**语义不变量**：同一帧的 FC 源TEI/目的TEI 必须等于 MAC 头的
「原始源TEI」/「原始目的TEI」（单跳帧下两者同指发送/接收站点）。

运行: python test/test_hdc10_fc_bits.py
"""

import _path_setup  # noqa: E402,F401

from hdc10_parser import HDC10Parser, _bits_lsb  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}" + (f" ({detail})" if detail else ""))
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f" ({detail})" if detail else ""))


# 现场真实帧（gx 8B 公共头；帧0 = 广播发现列表，帧1.. = 关联请求）
FRAME0 = bytes.fromhex(
    "EDA4000002EFC2D28E02010088000103000002F0FF034113794200E27700C020"
    "00FF2F01BEFA002680110800020000192168001101FFFFFFFFFFFF0800000002"
    "1000111921680011010000909801630119000000000001010000000000000001"
    "30817441BF000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000009BEF8EFFEE"
)
FRAME1 = bytes.fromhex(
    "EDA4000002EF978792020100880001302190001000032414794400E1AB90C000"
    "000100006324005C10FF08009600002000000001320101010101010000000020"
    "0000000132010000000000000000000203000400000132502847570090153430"
    "320200000000000000001904009711484A3430827B0000000B16006324000075"
    "B46D0AD739D44B4E341600003142435303FBC1019C0201200AF7FD0000000000"
    "000000BC5488FFEE"
)


def fc_of(frame: bytes) -> bytes:
    """ED 包装帧 → 业务 FC（gx 8B 公共头：ED头6B + 数据域公共头8B）"""
    return frame[6 + 8:][:16]


def rows_of(biz: bytes):
    return HDC10Parser().parse_to_table(biz, parse_level="auto")


def field(rows, name):
    for r in rows:
        if str(r[0]).strip() == name:
            return r[2]
    return None


print("1. _bits_lsb：位号小的一端是低位（LSB-first 位流）")
check("低字节在前 12bit：02 F0 → 2", _bits_lsb(bytes.fromhex("02F0"), 0, 0, 12) == 2)
check("高半字节在首字节：F0 FF（bit4起）→ 0xFFF",
      _bits_lsb(bytes.fromhex("F0FF"), 0, 4, 12) == 0xFFF)
check("单比特标志：0x42 比特1 → 1", _bits_lsb(b"\x42", 0, 1, 1) == 1)
check("不越界（数据不足时按已读位返回）",
      _bits_lsb(b"\x01", 0, 0, 12) == 1)


def biz_of(frame: bytes) -> bytes:
    """ED 包装帧 → 业务帧（去 ED 头6B + CS/EE 2B，跳 gx 8B 公共头）= FC+PB"""
    return frame[6:166][8:]


def fc_of(frame: bytes) -> bytes:
    """ED 包装帧 → 业务 FC（前 16 字节）"""
    return biz_of(frame)[:16]

print("2. 现场帧：FC 源TEI/目的TEI 必须等于 MAC 头原始TEI（语义不变量）")
for label, frame in (("帧0(广播发现列表)", FRAME0), ("帧1(关联请求)", FRAME1)):
    biz = biz_of(frame)
    rows = rows_of(biz)
    fc_src = field(rows, "源TEI")
    fc_dst = field(rows, "目的TEI")
    mac_src = field(rows, "原始源TEI")
    mac_dst = field(rows, "原始目的TEI")
    check(f"{label} FC源TEI == MAC原始源TEI",
          fc_src is not None and fc_src == mac_src, f"FC={fc_src} MAC={mac_src}")
    check(f"{label} FC目的TEI == MAC原始目的TEI",
          fc_dst is not None and fc_dst == mac_dst, f"FC={fc_dst} MAC={mac_dst}")

print("3. 用户报障点：帧0 FC 源TEI = 2（不是 32）")
rows0 = rows_of(biz_of(FRAME0))
check("帧0 FC 源TEI == 2", field(rows0, "源TEI") == "2", str(field(rows0, "源TEI")))
check("帧0 FC 源TEI != 32（旧错值）", field(rows0, "源TEI") != "32")
check("帧0 FC 目的TEI == 4095（广播）", field(rows0, "目的TEI") == "4095")
check("帧0 广播标志位 == 1（与目的TEI 广播一致）",
      field(rows0, "广播标志") == "1", str(field(rows0, "广播标志")))

print("4. 分集拷贝基本模式 与 物理块长度自洽（模式4 = 136B）")
check("分集拷贝基本模式 == 4", field(rows0, "分集拷贝基本模式") == "4",
      str(field(rows0, "分集拷贝基本模式")))
check("物理块为 136 字节",
      any("136字节" in str(r[2]) for r in rows0 if str(r[0]).strip() == "物理块(PB)"),
      str([r[2] for r in rows0 if "物理块" in str(r[0])]))

print("5. 帧长/符号数改用同一 LSB-first 口径（与源TEI 同表同形）")
fc0 = fc_of(FRAME0)
check("帧长 = 字节8 | 字节9低4位<<8", field(rows0, "帧长(FL)") ==
      f"{_bits_lsb(fc0, 8, 0, 12) * 10}us", str(field(rows0, "帧长(FL)")))
check("符号数 = 字节10 | 字节11比特0<<8",
      field(rows0, "符号数") == str(_bits_lsb(fc0, 10, 0, 9)),
      str(field(rows0, "符号数")))

print("6. 6 个 FC 可变区域解析器均无「首字节=高位」残留写法")
import inspect  # noqa: E402

import hdc10_parser  # noqa: E402

for fn_name in ("_parse_fc_vf_sof_plc", "_parse_fc_vf_beacon_plc",
                "_parse_fc_vf_beacon_hrf", "_parse_fc_vf_sack_plc",
                "_parse_fc_vf_sof_hrf", "_parse_fc_vf_sack_hrf"):
    src = inspect.getsource(getattr(hdc10_parser.HDC10Parser, fn_name))
    bad = [ln.strip() for ln in src.splitlines()
           if ("src_tei = (" in ln or "dst_tei = (" in ln
               or "frame_len = (" in ln or "sym_count = (" in ln)]
    check(f"{fn_name} 无旧位序公式", not bad, "; ".join(bad))

print(f"\n结果: {passed} 通过, {failed} 失败")
raise SystemExit(1 if failed else 0)
