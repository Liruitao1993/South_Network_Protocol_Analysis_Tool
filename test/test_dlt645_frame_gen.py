# -*- coding: utf-8 -*-
"""DLT645 组帧（协议6）测试：生成器 / schema / 掩码编码 / 组帧→解析闭环

覆盖：
  1. 与黄金参照 test/test_dlt645_lme.py:31 build_frame 逐字节一致
  2. 真实抓包 3 帧 golden sample 复现（CCO-2-COM3-260628-124120）
  3. 控制码组装（0x11 请求 / 0x91 应答 / 0xD1 异常应答）
  4. 地址域编码（BCD 低字节在前、广播 99×6、写地址 AA×6）
  5. 17 种 data_type 掩码的 encode→decode 往返
  6. 12 个功能码组帧 → DLT645Parser + DLT645Validator 闭环
  7. 广播校时线序 ss mm hh DD MM YY（第 6 字节是**年**，文档 §7.6）
  8. pack_* 与既有 split_* 的往返
  9. 非法输入中文报错且不崩溃、长度不符仅警告不阻断
"""

import _path_setup  # noqa: E402

import io
import sys

from dlt645_data_codec import (
    decode_err,
    decode_value,
    encode_value,
    split_change_password,
    split_clear_command,
    split_write_request,
)
from dlt645_frame_gen import DLT645FrameGenerator, describe_control, encode_addr, encode_di
from dlt645_frame_schema import (
    DLT645_CMD_SCHEMA,
    ERR,
    REQ,
    RSP,
    build_data,
    build_di_fields,
    get_di_info,
    length_warning,
    list_commands,
)
from dlt645_parser import DLT645Parser
from validator import DLT645Validator

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


def _ref_build_frame(decoded_data, ctrl=0x91, addr=b"\x10\x00\x00\x25\x00\x00"):
    """黄金参照：与 test/test_dlt645_lme.py:31 build_frame 逐行一致"""
    enc = bytes((b + 0x33) & 0xFF for b in decoded_data)
    body = bytes([0x68]) + addr + bytes([0x68, ctrl, len(enc)]) + enc
    cs = sum(body) & 0xFF
    return body + bytes([cs, 0x16])


GEN = DLT645FrameGenerator()


def _closed_loop(name, frame, expect_di=None, expect_text=None):
    """组帧 → 解析 + 校验闭环断言"""
    r = DLT645Parser.parse(frame)
    check(f"{name} parser.valid", bool(r.get("valid")), str(r.get("error")))
    v = DLT645Validator().verify(frame)
    check(f"{name} validator.valid", bool(v.valid), str(v.errors[:2]))
    if expect_di is not None:
        check(f"{name} DI={expect_di}", r.get("di_code") == expect_di, str(r.get("di_code")))
    if expect_text:
        blob = " ".join(str(c) for c in r.get("fields", []))
        check(f"{name} 含「{expect_text}」", expect_text in blob, blob[:200])


# ---------------------------------------------------------------------------
def t_golden_reference():
    print("== 1. 与黄金参照逐字节一致 ==")
    # 读电能请求：地址 000000000033、C=11H、DI=00010000
    mine = GEN.build_frame("000000000033", GEN.build_control(0x11), encode_di("00010000"))
    ref = _ref_build_frame(bytes.fromhex("00000100"), ctrl=0x11,
                           addr=bytes.fromhex("330000000000"))
    check("读电能帧 == test_dlt645_lme.build_frame", mine == ref,
          f"mine={mine.hex().upper()} ref={ref.hex().upper()}")
    check("读电能帧 hex 精确", mine.hex().upper() == "6833000000000068110433333433E516",
          mine.hex().upper())


def t_real_captures():
    print("== 2. 真实抓包 golden sample ==")
    # L114491 集中器→表 读请求
    f1 = GEN.build_frame("000000000033", 0x11, encode_di("00010000"))
    check("抓包 L114491 复现", f1.hex().upper() == "6833000000000068110433333433E516",
          f1.hex().upper())
    # L270631 表地址 000006881225
    f2 = GEN.build_frame("000006881225", 0x11, encode_di("00010000"))
    check("抓包 L270631 复现", f2.hex().upper() == "68251288060000681104333334337716",
          f2.hex().upper())
    # L114504 读应答 C=91H，值 0.00 kWh
    f3 = GEN.build_frame("000000000033", GEN.build_control(0x11, dir_bit=1),
                         encode_di("00010000") + encode_value("0.00", "XXXXXX.XX", "kWh"))
    check("抓包 L114504 复现",
          f3.hex().upper() == "6833000000000068910833333433333333333516",
          f3.hex().upper())
    # 三帧 CS 均须等于「含帧头」累加和
    for tag, f in (("L114491", f1), ("L270631", f2), ("L114504", f3)):
        check(f"{tag} CS 覆盖帧头", f[-2] == sum(f[:-2]) & 0xFF,
              f"in={f[-2]:02X} calc={sum(f[:-2]) & 0xFF:02X}")


def t_control_codes():
    print("== 3. 控制码组装 ==")
    check("读请求 C=11H", GEN.build_control(0x11) == 0x11)
    check("读应答 C=91H", GEN.build_control(0x11, dir_bit=1) == 0x91)
    check("读异常应答 C=D1H", GEN.build_control(0x11, dir_bit=1, err=True) == 0xD1)
    check("写应答 C=94H", GEN.build_control(0x14, dir_bit=1) == 0x94)
    check("广播校时 C=08H", GEN.build_control(0x08) == 0x08)
    check("功能码越界报错", _raises(lambda: GEN.build_control(0x20)))
    check("describe_control 含中文", "读数据" in describe_control(0x91), describe_control(0x91))
    check("describe_control 标异常", "异常应答" in describe_control(0xD1))


def t_addr_encoding():
    print("== 4. 地址域编码 ==")
    check("地址低字节在前", encode_addr("260526000028") == bytes.fromhex("280000260526"),
          encode_addr("260526000028").hex())
    check("广播 99×6", encode_addr(GEN.BROADCAST_99) == b"\x99" * 6)
    check("写地址 AA×6（非BCD）", encode_addr(GEN.BROADCAST_AA) == b"\xAA" * 6)
    check("短地址左补零", encode_addr("33") == bytes.fromhex("330000000000"))
    check("bytes 输入视为线上序", encode_addr(b"\x28\x00\x00\x26\x05\x26")
          == b"\x28\x00\x00\x26\x05\x26")
    check("地址超 12 位报错", _raises(lambda: encode_addr("1" * 13)))
    check("地址非法字符报错", _raises(lambda: encode_addr("ZZZZZZZZZZZZ")))
    check("DI 低字节在前", encode_di("04FFAAF9") == bytes.fromhex("F9AAFF04"),
          encode_di("04FFAAF9").hex())
    check("DI 长度不足报错", _raises(lambda: encode_di("0001")))


def t_mask_roundtrip():
    print("== 5. 掩码 encode→decode 往返 ==")
    cases = [
        ("XXXXXX.XX", "123456.78", "kWh", "123456.78"),
        ("XXXXXX.XXXX", "123456.7890", "kWh", "123456.789"),
        ("XXX.X", "220.5", "V", "220.5"),
        ("XX.XXXX", "1.2345", "kW", "1.2345"),
        ("X.XXX", "0.500", "A", "0.5"),
        ("XXX.XXX", "50.000", "Hz", "50.0"),
        ("XXXXXX", "123456", "", "123456"),
        ("XX", "99", "", "99"),
    ]
    for mask, val, unit, expect in cases:
        b = encode_value(val, mask, unit)
        back = decode_value(b, mask, unit) or ""
        check(f"往返 {mask} {val}", expect in back, f"encoded={b.hex()} decoded={back!r}")
    # 电能标准样本：123456.78 → 线上 78 56 34 12（低字节在前）
    check("123456.78 编码字节序",
          encode_value("123456.78", "XXXXXX.XX", "kWh") == bytes.fromhex("78563412"),
          encode_value("123456.78", "XXXXXX.XX", "kWh").hex())
    # 日期 / 时间 / 通信地址
    check("日期 YYYYMMDD 线序 日月年",
          encode_value("2026-09-04", "YYYYMMDD") == bytes.fromhex("040926"),
          encode_value("2026-09-04", "YYYYMMDD").hex())
    check("日期往返", "2026-09-04" in (decode_value(bytes.fromhex("040926"), "YYYYMMDD") or ""))
    check("时间 hhmmss 线序 秒分时",
          encode_value("16:26:30", "hhmmss") == bytes.fromhex("302616"),
          encode_value("16:26:30", "hhmmss").hex())
    check("时间往返", "16:26:30" in (decode_value(bytes.fromhex("302616"), "hhmmss") or ""))
    check("通信地址 N×12 反转",
          encode_value("260526000028", "NNNNNNNNNNNN") == bytes.fromhex("280000260526"))
    # 位串与裸字节按长度校验
    check("BS32 需 4 字节", len(encode_value("00000001", "BS32")) == 4)
    check("BS96 需 12 字节", len(encode_value("00" * 12, "BS96")) == 12)
    check("BS64 需 8 字节", len(encode_value("00" * 8, "BS64")) == 8)
    check("XX...XX 裸字节透传", encode_value("0102030A", "XX...XX") == bytes.fromhex("0102030A"))
    check("空掩码返回空", encode_value("", "") == b"")
    # 非法输入
    check("小数位超掩码报错", _raises(lambda: encode_value("1.234", "XXX.X")))
    check("非数字报错", _raises(lambda: encode_value("12A4", "XXXXXX.XX")))
    check("容量溢出报错", _raises(lambda: encode_value("123456789", "XXXXXX.XX")))
    check("两个小数点报错", _raises(lambda: encode_value("1.2.3", "XXX.X")))
    check("日期格式错报错", _raises(lambda: encode_value("2026-09", "YYYYMMDD")))
    check("时间格式错报错", _raises(lambda: encode_value("16-26-30", "hhmmss")))


def t_read_closed_loop():
    print("== 6. 读数据闭环 ==")
    f = GEN.generate_frame((REQ, 0x11), {"数据标识 DI": "00010000"}, addr="000000000033")
    check("读请求帧 hex", f.hex().upper() == "6833000000000068110433333433E516", f.hex().upper())
    _closed_loop("读请求", f, expect_di="00010000", expect_text="正向有功")

    # 读应答：DI + 123456.78 kWh
    rsp = GEN.generate_frame((RSP, 0x11),
                             {"数据标识 DI": "00010000", "数据值": "123456.78"},
                             addr="000000000033")
    _closed_loop("读应答", rsp, expect_di="00010000", expect_text="123456.78")
    check("读应答 C=91H", rsp[8] == 0x91, f"{rsp[8]:02X}")


def t_timing():
    print("== 7. 广播校时（线序 ss mm hh DD MM YY）==")
    f = GEN.generate_frame((REQ, 0x08), {"校时时间": "2026-09-04 16:26:30"})
    check("校时地址域 99×6", f[1:7] == b"\x99" * 6, f[1:7].hex())
    check("校时 C=08H L=06H", f[8] == 0x08 and f[9] == 0x06, f"{f[8]:02X} {f[9]:02X}")
    data = GEN.descramble(f[10:-2])
    check("校时线序 30 26 16 04 09 26", data == bytes.fromhex("302616040926"), data.hex())
    _closed_loop("广播校时", f, expect_text="2026-09-04 16:26:30")
    # 留空自动取当前时间：长度必须是 6 字节
    f2 = GEN.generate_frame((REQ, 0x08), {"校时时间": ""})
    check("校时留空自动取当前时间", len(GEN.descramble(f2[10:-2])) == 6)
    check("校时格式错报错",
          _raises(lambda: GEN.generate_frame((REQ, 0x08), {"校时时间": "2026-09-04"})))


def t_write_and_password():
    print("== 8. 写数据 / 修改密码 ==")
    w = GEN.generate_frame((REQ, 0x14), {
        "数据标识 DI": "00010000", "写入数据": "123456.78",
        "密码权限 PA": "04", "密码 P0P1P2": "111111",
        "操作者代码 C0~C3": "12345678",
    }, addr="000000000033")
    data = GEN.descramble(w[10:-2])
    check("写数据 L=16(0x10)", w[9] == 0x10, f"{w[9]:02X}")
    rows = split_write_request(data)
    check("写数据 split 往返 4 行", len(rows) == 4, str(len(rows)))
    check("写数据 PA=04", rows[0][1] == "04", rows[0][1])
    check("写数据 密码=111111", rows[1][2] == "111111", rows[1][2])
    check("写数据 操作者=12345678", rows[2][2] == "12345678", rows[2][2])
    check("写数据 载荷=78563412", rows[3][1] == "78563412", rows[3][1])
    _closed_loop("写数据", w, expect_di="00010000")

    p = GEN.generate_frame((REQ, 0x18), {
        "数据标识 DI": "04000901", "原密码权限 PA": "00", "原密码 P0P1P2": "000000",
        "新密码权限 PA": "02", "新密码 P0P1P2": "123456",
    }, addr="000000000033")
    pdata = GEN.descramble(p[10:-2])
    check("改密码 L=0CH", p[9] == 0x0C, f"{p[9]:02X}")
    prows = split_change_password(pdata)
    check("改密码 split 往返 4 行", len(prows) == 4, str(len(prows)))
    check("改密码 新权限=02", prows[2][1] == "02", prows[2][1])
    check("改密码 新密码=123456", prows[3][2] == "123456", prows[3][2])
    _closed_loop("改密码", p)


def t_clear_commands():
    print("== 9. 清零类（19H/1AH 8字节无DI，1BH 12字节含事件标识）==")
    for func, name, expect_len in ((0x19, "最大需量清零", 8), (0x1A, "电表清零", 8)):
        f = GEN.generate_frame((REQ, func), {
            "密码权限 PA": "02", "密码 P0P1P2": "111111",
            "操作者代码 C0~C3": "00000000"}, addr="000000000033")
        d = GEN.descramble(f[10:-2])
        check(f"{name} L={expect_len}", len(d) == expect_len, f"{len(d)}")
        rows = split_clear_command(d)
        check(f"{name} split 往返 PA=02", rows and rows[0][1] == "02", str(rows[:1]))
        _closed_loop(name, f)

    f = GEN.generate_frame((REQ, 0x1B), {
        "密码权限 PA": "02", "密码 P0P1P2": "111111",
        "操作者代码 C0~C3": "00000000", "事件标识": "FFFFFFFF"}, addr="000000000033")
    d = GEN.descramble(f[10:-2])
    check("事件清零 L=0CH", len(d) == 12, f"{len(d)}")
    rows = split_clear_command(d)
    check("事件清零 全部对象", any("全部对象" in r[2] for r in rows), str(rows[-1:]))
    _closed_loop("事件清零", f)


def t_other_commands():
    print("== 10. 冻结 / 速率 / 地址 / 应答 / 异常应答 ==")
    fz = GEN.generate_frame((REQ, 0x16), {"冻结时间": "09-04-16-26"}, addr="000000000033")
    check("冻结 L=04H 线序 mm hh DD MM",
          GEN.descramble(fz[10:-2]) == bytes.fromhex("26160409"),
          GEN.descramble(fz[10:-2]).hex())
    _closed_loop("冻结命令", fz)

    bd = GEN.generate_frame((REQ, 0x17), {"速率特征字": "44"}, addr="000000000033")
    check("改速率 L=01H", bd[9] == 0x01 and GEN.descramble(bd[10:-2]) == b"\x44")
    _closed_loop("更改通信速率", bd)

    ra = GEN.generate_frame((REQ, 0x13), {})
    check("读地址 地址域 AA×6", ra[1:7] == b"\xAA" * 6, ra[1:7].hex())
    check("读地址 L=00H", ra[9] == 0x00, f"{ra[9]:02X}")
    _closed_loop("读通信地址请求", ra)

    wa = GEN.generate_frame((REQ, 0x15), {"新通信地址": "260526000028"})
    check("写地址 地址域 AA×6", wa[1:7] == b"\xAA" * 6)
    check("写地址 数据域为新地址（低字节在前）",
          GEN.descramble(wa[10:-2]) == bytes.fromhex("280000260526"),
          GEN.descramble(wa[10:-2]).hex())
    _closed_loop("写通信地址请求", wa)

    # 读地址应答：数据域为表地址
    ras = GEN.generate_frame((RSP, 0x13), {"通信地址": "260526000028"},
                             addr="260526000028")
    _closed_loop("读通信地址应答", ras, expect_text="260526000028")

    # 写应答 94H：仅 DI
    wr = GEN.generate_frame((RSP, 0x14), {"数据标识 DI": "00010000"}, addr="000000000033")
    check("写应答 C=94H L=04H", wr[8] == 0x94 and wr[9] == 0x04, f"{wr[8]:02X} {wr[9]:02X}")
    _closed_loop("写数据应答", wr, expect_di="00010000")

    # 写地址应答 95H：L=00H
    was = GEN.generate_frame((RSP, 0x15), {}, addr="260526000028")
    check("写地址应答 L=00H", was[9] == 0x00 and was[8] == 0x95)
    _closed_loop("写通信地址应答", was)

    # 异常应答 D1H：ERR 位域
    er = GEN.generate_frame((ERR, 0x11), {"错误信息字 ERR": "04"}, addr="000000000033")
    check("异常应答 C=D1H", er[8] == 0xD1, f"{er[8]:02X}")
    check("异常应答 ERR=04", GEN.descramble(er[10:-2]) == b"\x04")
    check("ERR 位域解码=密码错", "密码错" in (decode_err(b"\x04") or ""), decode_err(b"\x04"))
    _closed_loop("读数据异常应答", er)

    # 清零类正常应答：数据域为空
    ca = GEN.generate_frame((RSP, 0x1A), {}, addr="000000000033")
    check("电表清零应答 L=00H C=9AH", ca[8] == 0x9A and ca[9] == 0x00, f"{ca[8]:02X}")


def t_di_fields():
    print("== 11. DI 驱动字段模板 ==")
    check("dlt645_di.json 可查 DI", get_di_info("00010000")["name"] == "当前正向有功总电能",
          str(get_di_info("00010000")))
    f = build_di_fields("00010000")
    check("电能 DI → 单个数值字段", len(f) == 1 and f[0]["type"] == "di_value", str(f))
    check("字段提示含格式与单位",
          "XXXXXX.XX" in f[0]["hint"] and "kWh" in f[0]["hint"], f[0]["hint"])

    fd = build_di_fields("01010000")     # 最大需量及发生时间 XX.XXXX,MDHM
    check("需量 DI → 值+时间两字段",
          [x["type"] for x in fd] == ["demand", "demand_time"], str(fd))

    check("日期 DI → 日期字段",
          build_di_fields("04000101")[0]["type"] == "di_value")
    check("通信地址 DI → 地址字段",
          build_di_fields("04000401")[0]["type"] == "addr")
    check("状态字 DI → 位串字段",
          build_di_fields("04000501")[0]["type"] == "hex", str(build_di_fields("04000501")))
    check("LME 04FFAAF9 → 无数据单元（空字段）",
          build_di_fields("04FFAAF9") == [], str(build_di_fields("04FFAAF9")))
    check("曲线数据块（length=0）→ 无字段", build_di_fields("061001FF") == [])
    check("未知 DI → 裸字节兜底不抛异常",
          build_di_fields("EEEEEEEE")[0]["type"] == "hex")

    # 需量组帧：值 + 发生时间
    dm = GEN.generate_frame((RSP, 0x11), {
        "数据标识 DI": "01010000", "需量值": "12.3456", "发生时间": "09-04-16-26"},
        addr="000000000033")
    d = GEN.descramble(dm[10:-2])
    check("需量数据域 = 3B值 + 4B时间", len(d) == 11, f"{len(d)}: {d.hex()}")
    check("需量值 12.3456 → 56 34 12", d[4:7] == bytes.fromhex("563412"), d[4:7].hex())
    check("需量时间线序 mm hh DD MM", d[7:11] == bytes.fromhex("26160409"), d[7:11].hex())

    cmds = list_commands()
    check("命令下拉含请求/应答/异常三组",
          {g for _, g, _ in cmds} == {"主站请求", "从站应答", "异常应答"}, str(len(cmds)))
    check("12 个请求命令齐全",
          sum(1 for k, g, _ in cmds if g == "主站请求") == len(
              [k for k in DLT645_CMD_SCHEMA if k[0] == REQ]),
          str([k for k in DLT645_CMD_SCHEMA if k[0] == REQ]))


def t_length_warning():
    print("== 12. 长度警告不阻断 ==")
    fv = {"数据标识 DI": "00010000", "写入数据": "1.23"}
    w = length_warning((REQ, 0x14), fv)
    check("长度相符无警告", w == "", w)
    # 需量掩码声明 8 字节，实际编码 7 字节 → 应给警告但仍能组帧
    w2 = length_warning((RSP, 0x11), {"数据标识 DI": "01010000", "需量值": "1.0",
                                      "发生时间": "01-01-00-00"})
    check("长度不符给中文警告", "字节" in w2 and "仍可生成" in w2, w2)
    f = GEN.generate_frame((RSP, 0x11), {"数据标识 DI": "01010000", "需量值": "1.0",
                                         "发生时间": "01-01-00-00"})
    check("警告不阻断组帧", len(f) > 12 and f[0] == 0x68 and f[-1] == 0x16)


def t_invalid_inputs():
    print("== 13. 非法输入中文报错 ==")
    check("缺 DI 报错", _raises(lambda: GEN.generate_frame((REQ, 0x11), {})))
    check("写数据缺值报错",
          _raises(lambda: GEN.generate_frame((REQ, 0x14), {"数据标识 DI": "00010000"})))
    check("未知命令报错", _raises(lambda: GEN.generate_frame((REQ, 0x1F), {})))
    check("未知方向报错", _raises(lambda: GEN.generate_frame(("bad", 0x11), {})))
    check("奇数 hex 报错",
          _raises(lambda: GEN.generate_frame((REQ, 0x17), {"速率特征字": "4"})))
    check("错误消息为中文", _raises_with_chinese(
        lambda: GEN.generate_frame((REQ, 0x14), {"数据标识 DI": "00010000"})))
    # 数据域超 255 字节
    check("数据域超 255 报错",
          _raises(lambda: GEN.build_frame("000000000033", 0x11, b"\x00" * 256)))


def _raises(fn):
    try:
        fn()
    except ValueError:
        return True
    except Exception:
        return False
    return False


def _raises_with_chinese(fn):
    try:
        fn()
    except ValueError as e:
        return any("\u4e00" <= ch <= "\u9fff" for ch in str(e))
    except Exception:
        return False
    return False


def t_lme_query():
    print("== 14. LME 查询请求结构化模板 ==")
    from dlt645_frame_schema import build_di_fields
    f = GEN.generate_frame((REQ, 0x11),
                           {"数据标识 DI": "FF00DD01", "条目列表": "0/1,0/2"},
                           addr="000000000033")
    d = GEN.descramble(f[10:-2])
    check("FF00DD01 请求 = DI+条目信息0+M+M×2B",
          d.hex() == "01dd00ff000201000200", d.hex())
    check("FF00DD01 请求头位域（数据ID6|分类3|保留7）",
          d[6:8] == (1 | 0 << 6).to_bytes(2, "little")
          and d[8:10] == (2 | 0 << 6).to_bytes(2, "little"), d.hex())
    _closed_loop("FF00DD01 查询请求", f, expect_di="FF00DD01")
    f0 = GEN.generate_frame((REQ, 0x11), {"数据标识 DI": "FF00DD01", "条目列表": ""},
                            addr="000000000033")
    check("条目留空 = M=0 读全量",
          GEN.descramble(f0[10:-2]).hex() == "01dd00ff0000",
          GEN.descramble(f0[10:-2]).hex())
    f4 = GEN.generate_frame((REQ, 0x11), {"数据标识 DI": "04FFAAF9"},
                            addr="000000000033")
    check("04FFAAF9 请求无数据单元（仅 DI 4B）",
          len(GEN.descramble(f4[10:-2])) == 4, GEN.descramble(f4[10:-2]).hex())
    fb = build_di_fields("FF00DD01")
    check("FF00DD01 字段模板 = 条目列表",
          [x["type"] for x in fb] == ["lme_entries"], str(fb))
    check("04FFAAF9 字段模板为空", build_di_fields("04FFAAF9") == [])
    check("条目格式错报错",
          _raises(lambda: GEN.generate_frame(
              (REQ, 0x11), {"数据标识 DI": "FF00DD01", "条目列表": "abc"})))
    f7 = GEN.generate_frame((REQ, 0x11),
                            {"数据标识 DI": "FF00DD01", "条目列表": "7/1"},
                            addr="000000000033")
    d7 = GEN.descramble(f7[10:-2])
    check("分类7 条目头 = 数据ID1|分类7<<6",
          d7[6:8] == (1 | 7 << 6).to_bytes(2, "little"), d7.hex())


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    t_golden_reference()
    t_real_captures()
    t_control_codes()
    t_addr_encoding()
    t_mask_roundtrip()
    t_read_closed_loop()
    t_timing()
    t_write_and_password()
    t_clear_commands()
    t_other_commands()
    t_di_fields()
    t_length_warning()
    t_invalid_inputs()
    t_lme_query()
    print(f"\n=== {PASS} 项通过，{len(FAILURES)} 项失败 ===")
    if FAILURES:
        for n in FAILURES:
            print("  FAIL:", n)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
