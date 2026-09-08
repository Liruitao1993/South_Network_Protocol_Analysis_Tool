# -*- coding: utf-8 -*-
"""DLT645 LME自定义接口解析测试（手册 LME产品相关信息生产运维接口手册_V2.4）

覆盖：
  4.2 查询HPLC单模STA详细信息（DI=04FFAAF9）—— 手册示例帧 + 合成完整帧
  4.6 查询HPLC双模STA内部详细信息（DI=FF00DD01）—— 请求/应答
  4.7 设置HPLC双模STA详细信息（DI=FF00DD01）—— 设置请求/结果应答
  真实抓包帧结构回归、标准645帧不回归、validator 超长豁免
"""

import _path_setup  # noqa: E402

import sys
import io

from dlt645_parser import DLT645Parser
from lme_info_entry_parser import (
    parse_lme_info_entries,
)

FAILURES = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def build_frame(decoded_data, ctrl=0x91, addr=b"\x10\x00\x00\x25\x00\x00"):
    """decoded_data: 减0x33后的真实数据域（含DI 4字节）；addr为帧内地址字节（低字节在前）"""
    enc = bytes((b + 0x33) & 0xFF for b in decoded_data)
    body = bytes([0x68]) + addr + bytes([0x68, ctrl, len(enc)]) + enc
    cs = sum(body) & 0xFF
    return body + bytes([cs, 0x16])


def build_frame_raw(raw_data, ctrl=0x91, addr=b"\x10\x00\x00\x25\x00\x00"):
    """raw_data: 线上数据域（已加0x33）"""
    body = bytes([0x68]) + addr + bytes([0x68, ctrl, len(raw_data)]) + raw_data
    cs = sum(body) & 0xFF
    return body + bytes([cs, 0x16])


def field_map(result):
    """归一化字段表：{字段名: (解析值或原始值, 说明, 原始值)}，兼容3/4元组"""
    m = {}
    for item in result["fields"]:
        if len(item) == 4:
            name, raw, parsed, desc = item
        else:
            name, raw, desc = item
            parsed = ""
        key = name.replace("  └ ", "").strip()
        m[key] = (parsed if parsed else raw, desc, raw)
    return m


def tlv_header(data_id, cat, enc, length):
    return (data_id | (cat << 6) | (enc << 9) | (length << 11)).to_bytes(2, "little")


def test_dlt645_lme():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    # ========== 1. 手册4.2 示例帧（手册自带，长度0x3A=58字节） ==========
    MANUAL_42_RAW = bytes.fromhex(
        "2CDD3237 7B7F 6369 343D 5C434C 3434 74 3534 81 3835 83 3443 4573 88"
        " 8296A7 5365 6C53 6563 646C 6463 6D 64636D 40"
        " 65BB4333 65BB4333 65BB4333 65".replace(" ", "")
    )
    r1 = DLT645Parser.parse(build_frame_raw(MANUAL_42_RAW, ctrl=0x91))
    check("4.2示例帧 帧合法", r1["valid"], r1.get("error"))
    check("4.2示例帧 DI=04FFAAF9", r1["di_code"] == "04FFAAF9", r1["di_code"])
    fm1 = field_map(r1)
    check("4.2 外部厂商代码=LH", fm1.get("外部厂商代码", ("",))[0] == "LH", str(fm1.get("外部厂商代码")))
    check("4.2 外部芯片代码=60", fm1.get("外部芯片代码", ("",))[0] == "60", str(fm1.get("外部芯片代码")))
    check("4.2 外部版本号=V0A01", fm1.get("外部版本号", ("",))[0] == "V0A01", str(fm1.get("外部版本号")))
    check("4.2 外部版本日期=2019-10-29", fm1.get("外部版本日期", ("",))[0] == "2019-10-29", str(fm1.get("外部版本日期")))
    check("4.2 MCU内部版本号=v0101", fm1.get("MCU内部版本号", ("",))[0] == "v0101", str(fm1.get("MCU内部版本号")))
    check("4.2 应用层版本号=A0102", fm1.get("应用层(APS)版本号", ("",))[0] == "A0102", str(fm1.get("应用层(APS)版本号")))
    check("4.2 网络层版本号=N0205", fm1.get("网络层(NWK)版本号", ("",))[0] == "N0205", str(fm1.get("网络层(NWK)版本号")))
    check("4.2 物理层版本号=P1001", fm1.get("物理层(PHY)版本号", ("",))[0] == "P1001", str(fm1.get("物理层(PHY)版本号")))
    check("4.2 DSP版本号=V4012", fm1.get("DSP版本号", ("",))[0] == "V4012", str(fm1.get("DSP版本号")))
    check("4.2 编译时间含Oct 29 2019", "Oct 29 2019" in fm1.get("编译时间", ("",))[0], str(fm1.get("编译时间")))
    check("4.2 短帧报数据不完整", any("不完整" in n for n in fm1), "58字节短帧应提示不完整")

    r1q = DLT645Parser.parse(build_frame(bytes.fromhex("F9AAFF04"), ctrl=0x11))
    check("4.2 读请求 接口名含4.2", "4.2" in r1q["di_desc"], r1q["di_desc"])

    # ========== 2. 合成完整255字节单模STA帧（频率/占空比/硬件信息/Flash） ==========
    d2 = bytearray(255)
    d2[0:4] = bytes([0xF9, 0xAA, 0xFF, 0x04])           # DI
    d2[4:6] = b"HL"                                      # 线上先传H再传L（逆序）-> 显示 LH
    d2[6:8] = b"06"                                      # 线上 0,6 -> 显示 60
    d2[8:10] = bytes([0x01, 0x0A])                       # 外版本 V0A01
    d2[10:13] = bytes([0x29, 0x10, 0x19])                # 日期 19-10-29
    d2[13:15] = bytes([0x01, 0x01])                      # MCU v0101
    d2[15] = ord("A")
    d2[16:18] = bytes([0x02, 0x01])                      # A0102
    d2[18] = ord("N")
    d2[19:21] = bytes([0x05, 0x02])                      # N0205
    d2[21] = ord("P")
    d2[22:24] = bytes([0x01, 0x10])                      # P1001
    d2[24:26] = bytes([0x12, 0x40])                      # DSP V4012
    d2[26] = 0x07                                        # 过零标志 ABC
    d2[27:46] = b"Oct 29 2019 10:10:22"[:19]             # 编译时间 19B
    for ph_off in range(46, 58, 4):
        d2[ph_off:ph_off + 2] = (5000).to_bytes(2, "little")    # 频率 50.00Hz
        d2[ph_off + 2:ph_off + 4] = (500).to_bytes(2, "little")  # 占空比 50.0%
    d2[58] = 5                                           # 硬件信息长度
    d2[59:64] = b"LMEX1"                                 # 硬件型号
    d2[64:66] = bytes([0x34, 0x12])                      # CRC-16（仅展示）
    d2[66] = 4                                           # Flash n=4 -> 2^5=32
    r2 = DLT645Parser.parse(build_frame(bytes(d2), ctrl=0x91))
    fm2 = field_map(r2)
    check("4.2完整帧 合法", r2["valid"], r2.get("error"))
    check("4.2完整帧 频率50.00Hz", fm2.get("A相过零检测频率", ("",))[0] == "50.00 Hz", str(fm2.get("A相过零检测频率")))
    check("4.2完整帧 占空比50.0%", fm2.get("A相过零检测占空比", ("",))[0] == "50.0 %", str(fm2.get("A相过零检测占空比")))
    check("4.2完整帧 硬件信息=LMEX1", fm2.get("硬件信息", ("",))[0] == "LMEX1", str(fm2.get("硬件信息")))
    check("4.2完整帧 Flash=32", "32" in fm2.get("Flash容量", ("",))[0], str(fm2.get("Flash容量")))
    check("4.2完整帧 无不完整提示", not any("不完整" in n for n in fm2))

    # ========== 3. 4.6 双模STA查询请求（DIR=0 FUNC=11，请求分类0/数据15） ==========
    hdr = 15 | (0 << 6)                                   # 数据ID=15 分类ID=0
    d3 = bytes([0x01, 0xDD, 0x00, 0xFF, 0x00, 0x01]) + hdr.to_bytes(2, "little")
    r3 = DLT645Parser.parse(build_frame(d3, ctrl=0x11))
    check("4.6请求 接口名", "4.6" in r3["di_desc"], r3["di_desc"])
    fm3 = field_map(r3)
    check("4.6请求 M=1", fm3.get("条目数 M", ("",))[0] == "1", str(fm3.get("条目数 M")))
    check("4.6请求 条目=本地接口默认信息",
          any("本地接口默认信息" in n for n in fm3), str(list(fm3)[:6]))

    d3b = bytes([0x01, 0xDD, 0x00, 0xFF, 0x00, 0x00])
    r3b = DLT645Parser.parse(build_frame(d3b, ctrl=0x11))
    check("4.6请求 M=0 读全部",
          any("全部" in (v[0] + v[1]) for v in field_map(r3b).values()))

    # ========== 4. 4.6 双模STA查询应答（TLV：分类0/数据15 波特率BR_9600+无校验） ==========
    hdr4 = 15 | (0 << 6) | (2 << 9) | (2 << 11)           # id15 cat0 enc=BIN len=2
    d4 = bytes([0x01, 0xDD, 0x00, 0xFF, 0x00, 0x01]) + hdr4.to_bytes(2, "little") + bytes([0x05, 0x00])
    r4 = DLT645Parser.parse(build_frame(d4, ctrl=0x91))
    val4 = " ".join(v[0] for v in field_map(r4).values())
    check("4.6应答 BR_9600", "BR_9600" in val4, val4[:200])
    check("4.6应答 无校验", "无校验" in val4, val4[:200])

    # ========== 5. 4.7 设置请求 + 设置结果应答 ==========
    r5q = DLT645Parser.parse(build_frame(d4, ctrl=0x14))
    check("4.7设置请求 接口名", "4.7" in r5q["di_desc"] and "设置请求" in r5q["di_desc"], r5q["di_desc"])
    hdr5 = 15 | (0 << 6) | (0 << 9)                        # 结果码=0 成功
    d5 = bytes([0x01, 0xDD, 0x00, 0xFF, 0x01]) + hdr5.to_bytes(2, "little")
    r5 = DLT645Parser.parse(build_frame(d5, ctrl=0x94))
    val5 = " ".join(v[0] for v in field_map(r5).values())
    check("4.7设置应答 接口名", "4.7" in r5["di_desc"] and "设置应答" in r5["di_desc"], r5["di_desc"])
    check("4.7设置应答 设置成功", "设置成功" in val5, val5[:200])

    hdr5b = 15 | (0 << 6) | (1 << 9)
    d5b = bytes([0x01, 0xDD, 0x00, 0xFF, 0x01]) + hdr5b.to_bytes(2, "little")
    r5b = DLT645Parser.parse(build_frame(d5b, ctrl=0x94))
    check("4.7设置应答 结果码1=不支持",
          "参数不支持设置" in " ".join(v[0] for v in field_map(r5b).values()))

    # ========== 6. 截断帧不异常 ==========
    d6 = d4[:9]                                           # TLV数据被砍
    r6 = DLT645Parser.parse(build_frame(d6, ctrl=0x91))
    val6 = " ".join(str(v) for vals in field_map(r6).values() for v in vals)
    check("截断帧 不异常且提示截断/不完整", "截断" in val6 or "不完整" in val6, val6[:200])

    # ========== 7. 标准645帧不回归 ==========
    d7 = bytes([0x00, 0x00, 0x01, 0x00]) + bytes([0x01, 0x00, 0x00, 0x00])  # DI=00010000 + 4B数据
    r7 = DLT645Parser.parse(build_frame(d7, ctrl=0x91))
    check("标准帧 DI=00010000", r7["di_code"] == "00010000", r7["di_code"])
    check("标准帧 描述=当前正向有功总电能", "正向有功" in r7["di_desc"], r7["di_desc"])
    check("标准帧 走数据值解码行", "数据值" in field_map(r7), str(list(field_map(r7))))

    # ========== 8. 真实抓包帧结构回归（双模STA应答 M=17） ==========
    # 硬件信息组31B：B0芯片型号=4, B1~4 Flash=42590002, B5电容=1, B6过零电路=1,
    # B7天线=1, B8 PA=1, B9特征电流=0, B10射频开关=0, B11~30硬件编码ASCII
    hw_group = bytes([0x04]) + bytes.fromhex("42590002") + bytes([1, 1, 1, 1, 0, 0]) \
        + b"LSX830A-GPR001C-D2" + b"\x00" * 2
    hw_group = hw_group[:31].ljust(31, b"\x00")
    d8 = bytearray([0x01, 0xDD, 0x00, 0xFF, 0x00, 0x11])          # DI + 条目信息0 + M=17
    d8 += tlv_header(2, 7, 2, 3) + bytes([0x00, 0x00, 0x03])       # 分类7/数据2=软件信息组
    d8 += tlv_header(1, 7, 2, 31) + hw_group                       # 分类7/数据1=硬件信息组
    d8 += tlv_header(60, 7, 2, 2) + bytes([0xAB, 0xCD])            # 分类7未知条目（厂商扩展）
    d8 += tlv_header(1, 0, 1, 2) + bytes([0x48, 0x4C])             # [基本信息]外部厂商代码 -> LH
    for _ in range(13):                                            # 其余13条：[运行信息]复位计数
        d8 += tlv_header(1, 4, 2, 2) + bytes([0x00, 0x00])
    r8 = DLT645Parser.parse(build_frame(bytes(d8), ctrl=0x91))
    check("真实结构帧 帧合法", r8["valid"], r8.get("error"))
    check("真实结构帧 DI=FF00DD01", r8["di_code"] == "FF00DD01", r8["di_code"])
    fm8 = field_map(r8)
    check("真实结构帧 M=17", fm8.get("条目数 M", ("",))[0] == "17", str(fm8.get("条目数 M")))
    val8 = " ".join(v[0] for v in fm8.values())
    check("真实结构帧 含厂商LH", "LH" in val8, val8[:300])
    # 分类7 OTP信息组结构化解码
    check("分类7/数据1=硬件信息组",
          any("硬件信息组" in k for k in fm8), str(list(fm8)[:5]))
    # 竖排：子字段各占一行（key=子字段名，value=解析值）
    keys8 = " ".join(fm8.keys())
    check("硬件信息组 竖排子行",
          "芯片型号" in keys8 and "硬件编码" in keys8 and "载波PA功放型号" in keys8, keys8[:300])
    check("硬件编码 值", '"LSX830A-GPR001C-D2"' in val8, val8[:400])
    check("芯片型号/Flash 值",
          "LME3960C" in val8 and "42590002" in val8, val8[:400])
    check("软件信息组 竖排 模块类型3=电表通信单元",
          "3（电表通信单元）" in val8, val8[:400])
    check("父行提示展开子字段", "展开 9 个子字段" in val8, val8[:200])
    # 分类7未知条目仍标注厂商扩展
    unknown_rows = [v for k, v in fm8.items() if "数据60" in k]
    check("分类7未知条目 标注厂商扩展",
          unknown_rows and "厂商扩展" in unknown_rows[0][1], str(unknown_rows))
    # 分类7已定义条目不标厂商扩展
    hw_desc = [v[1] for k, v in fm8.items() if "硬件信息组" in k]
    check("硬件信息组 不误标厂商扩展", hw_desc and "厂商扩展" not in hw_desc[0], str(hw_desc))
    old = parse_lme_info_entries(r8["data"])
    check("旧接口 2元组且>=15条", all(len(t) == 2 for t in old) and len(old) >= 15, f"{len(old)} entries")
    check("旧接口 含外部厂商代码=LH",
          any(n == "外部厂商代码" and v == "LH" for n, v in old), str(old[:5]))

    # ========== 8b. 过零检测信息 + NTB采样信息 结构化解码 ==========
    # STA变体13B：flag + 下降沿ABC 3对
    zc13 = bytes([0x01]) + (4996).to_bytes(2, "little") + (4).to_bytes(2, "little") + bytes(8)
    assert len(zc13) == 13
    # CCO变体25B：下降沿ABC + 上升沿ABC 共6对（A相50Hz/50%，其余0）
    zc25 = bytes([0xFF])
    zc25 += (5000).to_bytes(2, "little") + (500).to_bytes(2, "little")  # A下降
    zc25 += bytes(8)                                                    # B/C下降
    zc25 += (5000).to_bytes(2, "little") + (500).to_bytes(2, "little")  # A上升
    zc25 += bytes(8)                                                    # B/C上升
    assert len(zc25) == 25
    ntb = (100).to_bytes(2, "little") + bytes([1, 0]) + (7).to_bytes(4, "little") + (9).to_bytes(4, "little")
    assert len(ntb) == 12
    d8b = bytearray([0x01, 0xDD, 0x00, 0xFF, 0x00, 0x03])
    d8b += tlv_header(20, 2, 2, 13) + zc13
    d8b += tlv_header(22, 2, 2, 25) + zc25   # 未知数据ID，长度25走过零解码？仅验证25B分支
    d8b += tlv_header(21, 2, 2, 12) + ntb
    r8b = DLT645Parser.parse(build_frame(bytes(d8b), ctrl=0x91))
    fm8b = field_map(r8b)
    keys8b = " ".join(fm8b.keys())
    val8b = " ".join(v[0] for v in fm8b.values())
    check("过零信息 竖排子行",
          "A相(下降沿)过零检测频率" in keys8b and "A相(下降沿)过零检测占空比" in keys8b, keys8b[:300])
    check("过零信息 下降沿49.96Hz", "49.96 Hz" in val8b, val8b[:400])
    check("过零信息 STA标注仅下降沿", "仅下降沿数据" in val8b, val8b[:400])
    check("NTB采样 竖排子行",
          "采样偏差补偿" in keys8b and "评估计数偏差" in keys8b
          and "本地时钟计数修正" in keys8b and "本地误差补偿方向" in keys8b, keys8b[:300])
    check("NTB采样 值正确",
          "100" in val8b and "加快本地时间计数" in val8b, val8b[:400])
    # 25B 过零解码器单元验证（CCO变体含上升沿）
    from lme_info_entry_parser import _fmt_zero_cross_info
    zc25_decoded = _fmt_zero_cross_info(zc25)
    check("过零信息 CCO变体含上升沿",
          "A相(上升沿)过零检测频率:50.00 Hz" in zc25_decoded
          and "仅下降沿" not in zc25_decoded, zc25_decoded[:300])

    # ========== 9. validator LME超长豁免 ==========
    from validator.dlt645_validator import DLT645Validator
    val = DLT645Validator()
    v9 = val.verify(build_frame(bytes(d2), ctrl=0x91))
    warn9 = [c for c in v9.checks if c.name == "数据长度"]
    check("validator LME 255B 不WARN", warn9 and warn9[0].level.name == "PASS",
          str([(c.level.name, c.message) for c in warn9]))

    d9b = bytearray(b"\x00" * 210)
    d9b[0:4] = bytes([0x99, 0x99, 0x99, 0x99])
    v9b = val.verify(build_frame(bytes(d9b), ctrl=0x91))
    warn9b = [c for c in v9b.checks if c.name == "数据长度" and c.level.name == "WARN"]
    check("validator 未知DI超长 仍WARN", len(warn9b) == 1)

    # ========== 10. 读/写通信地址帧（数据域为6B表地址，无DI） ==========
    # 官方工具样例帧：93H=读地址应答，数据域减33H为 28 00 00 26 05 26
    addr_frame = bytes.fromhex("682800002605 266893065B33335938598D16".replace(" ", ""))
    ra = DLT645Parser.parse(addr_frame)
    check("读地址应答 帧合法", ra["valid"], ra.get("error"))
    check("读地址应答 无误判DI", ra.get("di_code", "") == "", ra.get("di_code"))
    fa = field_map(ra)
    check("读地址应答 通信地址行", "通信地址（数据域）" in fa, str(list(fa)))
    check("读地址应答 地址=260526000028",
          fa.get("通信地址（数据域）", ("",))[0] == "260526000028", str(fa.get("通信地址（数据域）")))
    check("读地址应答 原始序=28 00 00 26 05 26",
          fa.get("通信地址（数据域）", ("", ""))[2] == "28 00 00 26 05 26", str(fa.get("通信地址（数据域）")))
    check("读地址应答 无未知数据标识",
          not any("未知数据标识" in str(v) for v in fa.values()))

    # 写地址请求（C=15H，数据域6B新地址）
    wa_data = bytes([0x28, 0x00, 0x00, 0x26, 0x05, 0x26])
    rw = DLT645Parser.parse(build_frame(wa_data, ctrl=0x15))
    fw = field_map(rw)
    check("写地址请求 通信地址行",
          "通信地址（数据域）" in fw and fw["通信地址（数据域）"][0] == "260526000028",
          str(fw.get("通信地址（数据域）")))

    # 广播校时（C=08H，数据域线序 ss mm hh DD MM YY）
    # 依据 DL/T645-2007 §7.6：数据域 YYMMDDhhmmss，第 6 字节是**年**而非星期
    def bcd(v):
        return ((v // 10) << 4) | (v % 10)
    tdata = bytes([bcd(30), bcd(26), bcd(16), bcd(4), bcd(9), bcd(26)])  # 2026-09-04 16:26:30
    rt = DLT645Parser.parse(build_frame(tdata, ctrl=0x08))
    ft = field_map(rt)
    check("广播校时 校时数据行", "校时数据（数据域）" in ft, str(list(ft)))
    check("广播校时 时间解析",
          "2026-09-04 16:26:30" in ft.get("校时数据（数据域）", ("",))[0],
          str(ft.get("校时数据（数据域）")))

    # ========== 11. 标准DLT645数据值解码 ==========
    # 读正向有功总电能应答：DI=00010000 + 123456.78kWh（线序 78 56 34 12）
    r11 = DLT645Parser.parse(build_frame(bytes.fromhex("00000100 78563412".replace(" ", ""))))
    f11 = field_map(r11)
    check("电能值解码 123456.78", "123456.78 kWh" in f11.get("数据值", ("",))[0],
          str(f11.get("数据值")))
    # 日期 DI 04000101 YYYYMMDD：线序 DD MM YY = 04 09 26
    r11b = DLT645Parser.parse(build_frame(bytes.fromhex("01010004 040926".replace(" ", ""))))
    f11b = field_map(r11b)
    check("日期解码 2026-09-04", "2026-09-04" in " ".join(v[0] for v in f11b.values()),
          str(f11b.get("数据值")))
    # 非BCD数据回退hex不报错（伪数据）
    r11c = DLT645Parser.parse(build_frame(bytes.fromhex("00000100 AABBCCDD".replace(" ", ""))))
    f11c = field_map(r11c)
    check("非BCD回退hex", "AABBCCDD" in f11c.get("数据值", ("", ""))[2], str(f11c.get("数据值")))

    # ========== 12. 异常应答 ERR（位域，bit2=密码错 → 0x04） ==========
    err_frame_data = bytes([0x04])  # 密码错/未授权
    # 控制码 D1H = DIR1+D6+FUNC01
    def build_ctrl(dd, ctrl, addr=b"\x00" * 6):
        enc = bytes((b + 0x33) & 0xFF for b in dd)
        body = bytes([0x68]) + addr + bytes([0x68, ctrl, len(enc)]) + enc
        return body + bytes([sum(body) & 0xFF, 0x16])
    r12 = DLT645Parser.parse(build_ctrl(err_frame_data, 0xD1))
    f12 = field_map(r12)
    check("异常应答 ERR位域解码", "密码错/未授权" in f12.get("错误信息字 ERR", ("",))[0],
          str(f12.get("错误信息字 ERR")))
    multi_err = field_map(DLT645Parser.parse(build_ctrl(bytes([0x03]), 0xD1)))
    mev = multi_err.get("错误信息字 ERR", ("",))[0]
    check("异常应答 多错误位(bit0其他+bit1无请求)",
          "其他错误" in mev and "无请求数据" in mev, mev)
    check("异常应答 控制码标签", "异常应答" in r12["control_desc"], r12["control_desc"])
    check("异常应答 无误判DI", r12.get("di_code", "") == "")

    # ========== 12b. 电表运行状态字按附录C位定义展开 ==========
    # 状态字4（DI=04000504，线序 04 05 00 04）A相故障：bit7断相+bit3过压=0x88
    r12b = DLT645Parser.parse(build_frame(bytes.fromhex("04050004 88000000".replace(" ", ""))))
    sv = field_map(r12b).get("数据值", ("",))[0]
    check("状态字4 断相/过压置位", "断相" in sv and "过压" in sv, sv[:200])
    # 状态字1（DI=04000501，线序 01 05 00 04）：bit6有功方向=0x40
    r12c = DLT645Parser.parse(build_frame(bytes.fromhex("01050004 40000000".replace(" ", ""))))
    svc = field_map(r12c).get("数据值", ("",))[0]
    check("状态字1 有功方向置位", "有功功率方向" in svc and "置位" in svc, svc[:200])

    # ========== 13. 写数据/改密码/清零命令请求拆分 ==========
    # 写数据14H：DI(00010000) + 密码权限04/密码123456 + 操作者00000001 + 数据BCD
    wd = bytes.fromhex("00000100") + bytes([0x04, 0x12, 0x34, 0x56,
                                            0x00, 0x00, 0x00, 0x01]) + bytes.fromhex("7856")
    r13 = DLT645Parser.parse(build_ctrl(wd, 0x14))
    f13 = field_map(r13)
    check("写帧 密码权限", "权限级别 04" in f13.get("密码权限 PA", ("",))[0], str(list(f13)[:8]))
    check("写帧 密码P0P1P2", f13.get("密码 P0P1P2", ("",))[0] == "123456", str(f13.get("密码 P0P1P2")))
    check("写帧 操作者代码", f13.get("操作者代码 C0~C3", ("",))[0] == "00000001",
          str(f13.get("操作者代码 C0~C3")))
    check("写帧 写入数据", "写入数据" in f13, str(list(f13)))

    # 修改密码18H：DI + 原密码组(04/111111) + 新密码组(04/222222)
    cp = bytes.fromhex("00000904") + bytes([0x04, 0x11, 0x11, 0x11]) + bytes([0x04, 0x22, 0x22, 0x22])
    r13b = DLT645Parser.parse(build_ctrl(cp, 0x18))
    f13b = field_map(r13b)
    check("改密码 控制码标签", "修改密码" in r13b["control_desc"], r13b["control_desc"])
    check("改密码 新密码组", any("新密码 密码 P0P1P2" in k for k in f13b)
          and "222222" in " ".join(v[0] for v in f13b.values()), str(list(f13b)))

    # 事件清零1BH：密码4B + 操作者4B + 对象FFFFFFFF
    ev = bytes([0x02, 0x99, 0x99, 0x98, 0x00, 0x00, 0x00, 0x01]) + b"\xFF" * 4
    r13c = DLT645Parser.parse(build_ctrl(ev, 0x1B))
    f13c = field_map(r13c)
    check("事件清零 标签", "事件清零" in r13c["control_desc"], r13c["control_desc"])
    check("事件清零 全部对象", "全部对象" in f13c.get("操作对象标识", ("",))[0],
          str(f13c.get("操作对象标识")))
    check("事件清零 密码行", "密码 P0P1P2" in " ".join(f13c.keys()), str(list(f13c)))

    assert not FAILURES, f"{len(FAILURES)} 项失败: {FAILURES}"


if __name__ == "__main__":
    test_dlt645_lme()
    print()
    print("=== 全部通过 ===")
