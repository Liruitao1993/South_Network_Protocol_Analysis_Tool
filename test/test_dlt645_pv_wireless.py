# -*- coding: utf-8 -*-
"""南网光伏无线模组接口手册（V1.6）扩展解析回归。

覆盖：
  [1] DI 表规模 / is_wireless_di / 04E60001 被无线版覆盖
  [2] §4.4.2 无线频段（调制/信道 BCD/协商使能）
  [3] §4.4.3 地址列表（数量 + 5 个地址，BCD 低位在前）
  [4] §4.4.4 数据转发（波特率特征字/校验/**超时 T 为 BCD**）
  [5] §4.4.5 86H 主动上报的控制码语义
  [6] §4.4.6 拓扑（数量/父节点全 FF = 未入网）
  [7] §4.3.1 1EH 在网状态
  [8] §4.1.3 D1H 异常应答 ERR=0x80（未入网）位展开
  [9] 升级类 DI（构造帧）：块状态字 / 状态信息 / 文件信息 / 块序号 / 块大小 / 执行时间 / 版本
  [10] 反例：普通 645 DI 不走本模块

运行: QT_QPA_PLATFORM=offscreen python -u test/test_dlt645_pv_wireless.py
"""

import _path_setup  # noqa: E402,F401

import sys  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # noqa: BLE001
    pass

import dlt645_pv_wireless as wl  # noqa: E402
from dlt645_parser import DLT645Parser  # noqa: E402

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {msg}")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg}")


PARSER = DLT645Parser()


def build(addr_hex: str, ctrl: int, payload: bytes) -> bytes:
    """按 DL/T645 组帧：数据域每字节 +33H，CS = 68H 到数据域末字节的算术和 &0xFF。"""
    data = bytes((b + 0x33) & 0xFF for b in payload)
    head = bytes.fromhex(addr_hex) + b"\x68" + bytes([ctrl, len(data)]) + data
    body = b"\x68" + head
    return body + bytes([sum(body) & 0xFF, 0x16])


def parse(hexstr: str) -> dict:
    return PARSER.parse(bytes.fromhex(hexstr.replace(" ", "")))


def row_value(result: dict, key: str) -> str:
    for row in result["fields"]:
        if key in str(row[0]):
            return str(row[2])
    return ""


def row_raw(result: dict, key: str) -> str:
    for row in result["fields"]:
        if key in str(row[0]):
            return str(row[1])
    return ""


def all_values(result: dict) -> str:
    return " ".join(str(r[2]) for r in result["fields"])


# ── 手册 §4.4 原文示例 ────────────────────────────────────────────────
F_BAND = "68 99 00 00 00 00 88 68 91 08 35 33 19 37 35 65 33 34 43 16"
F_ADDR = ("68 99 00 00 00 00 88 68 91 23 34 33 19 37 38 64 43 BB 39 33 33 36 45 BB 39 "
          "33 33 85 45 BB 39 33 33 86 45 BB 39 33 33 A4 33 CB 39 88 3A 50 16")
F_FORWARD = "68 03 12 88 60 00 00 68 11 0A 33 33 1E 35 3B 35 43 33 33 33 93 16"
F_EVENT = ("68 03 12 88 60 00 00 68 86 1A 34 38 A3 36 73 67 47 47 3C 59 67 34 33 33 33 "
           "33 33 33 33 33 33 33 33 33 33 33 14 16")
F_TOPO = ("68 99 00 00 00 00 88 68 91 50 33 34 C3 37 38 64 43 BB 39 33 33 33 32 32 32 "
          "32 32 32 33 33 36 45 BB 39 33 33 AC 86 45 BB 39 33 33 33 33 85 45 BB 39 33 33 AB "
          "BB 33 33 33 33 CC 33 33 86 45 BB 39 33 33 B6 BB 33 33 33 33 CC 33 33 A4 33 CB 39 "
          "88 3A 33 32 32 32 32 32 32 33 33 BB 16")


# ── [1] DI 表 ───────────────────────────────────────────────────────
def test_di_table():
    check(len(wl.WIRELESS_DI_MAP) == 12, f"DI 表有 12 个数据标识（实际 {len(wl.WIRELESS_DI_MAP)}）")
    for code in ("02EB0000", "04E60001", "04E60002", "04900100", "04900107", "028100FF"):
        check(wl.is_wireless_di(code), f"{code} 命中无线扩展")
    check(not wl.is_wireless_di("00010000"), "普通 645 DI 不命中无线扩展")
    merged = wl.merge_wireless_di_map({"04E60001": {"name": "旧名字", "unit": "", "data_type": "", "length": 16}})
    check(merged["04E60001"]["name"] == "下挂光伏逆变器地址列表",
          "04E60001 被无线版覆盖（长度模型 1+6×M 取代附件1 的长度列 16）")


# ── [2] 无线频段 ────────────────────────────────────────────────────
def test_band():
    r = parse(F_BAND)
    check(r["di_code"] == "04E60002", "DI 识别为 04E60002")
    check("读模组数据应答" in r["control_desc"], f"控制码语义（{r['control_desc']}）")
    check(row_value(r, "无线调制方式").startswith("2"), "调制方式 = 2（500kHz）")
    check(row_value(r, "无线信道编号").startswith("32"), "信道 = 32（2 字节 BCD 低字节在前，不是 0x0032=50）")
    check("允许" in row_value(r, "信道协商使能"), "信道协商使能 = 1（允许）")


# ── [3] 地址列表 ────────────────────────────────────────────────────
def test_addr_list():
    r = parse(F_ADDR)
    check(r["di_code"] == "04E60001", "DI 识别为 04E60001（无线版优先）")
    check(row_value(r, "有效数量").startswith("5"), "有效数量 M = 5")
    text = all_values(r)
    for addr in ("000006881031", "000006881203", "000006881252", "000006881253", "075506980071"):
        check(addr in text, f"解析出地址 {addr}")


# ── [4] 数据转发（T 必须是 BCD）─────────────────────────────────────
def test_forward():
    r = parse(F_FORWARD)
    check(r["di_code"] == "02EB0000", "DI 识别为 02EB0000")
    check("数据转发送达请求" in r["control_desc"], "控制码 = 数据转发送达请求")
    check(row_value(r, "波特率特征字").endswith("2400bps"), "波特率特征字 0x08 → bit3 → 2400bps")
    check("偶校验" in row_value(r, "校验方式"), "校验方式 0x02 → 偶校验")
    t_text = row_value(r, "超时")
    check("1000 ms" in t_text, f"超时 T 按 BCD 读 0x10 → 10 → 1000ms（实际 {t_text}）")
    check("1600" not in t_text, "不能按整数读成 16 → 1600ms（手册 §3.1 明确 T 为 BCD）")


# ── [5] 86H 主动上报 ────────────────────────────────────────────────
def test_event_report():
    r = parse(F_EVENT)
    check(r["control"] == 0x86, "控制码 = 86H")
    check("主动上报" in r["control_desc"], f"86H 语义 = 主动上报（{r['control_desc']}）")
    check("未知功能码06H" not in r["control_desc"], "不再显示「未知功能码06H」（扩展语义已接管）")
    check(r["di_code"] == "03700501", "上报 DI 读出 03700501")


# ── [6] 拓扑 ────────────────────────────────────────────────────────
def test_topology():
    r = parse(F_TOPO)
    check(r["di_code"] == "04900100", "DI 识别为 04900100")
    check(row_value(r, "数量").startswith("5"), "节点数量 N = 5")
    check(row_value(r, "节点1 父节点") == "未入网", "节点1 父节点全 FF → 未入网")
    check(row_value(r, "节点2 父节点") == "000006881253", "节点2 父节点反转 BCD = 000006881253")


# ── [7] 1EH 在网状态 ───────────────────────────────────────────────
def test_online_state():
    payload = bytes.fromhex("FF008102") + bytes([1])      # DI=028100FF + 在网
    frame = build("A6A5A4A3A2A1", 0x1E, payload)
    r = PARSER.parse(frame)
    check(r["di_code"] == "028100FF", "DI 识别为 028100FF")
    check("在网状态上报" in r["control_desc"], f"1EH 语义 = 在网状态上报（{r['control_desc']}）")
    check(row_value(r, "在网状态") == "在网", "状态 0x01 → 在网")
    check(r["valid"] is True, "构造帧结构与校验通过")

    frame0 = build("A6A5A4A3A2A1", 0x1E, bytes.fromhex("FF008102") + bytes([0]))
    check(row_value(PARSER.parse(frame0), "在网状态") == "离网", "状态 0x00 → 离网")


# ── [8] 异常应答 ERR=0x80 ───────────────────────────────────────────
def test_exception_err():
    frame = build("031288600000", 0xD1, bytes([0x80]))
    r = PARSER.parse(frame)
    check(r["control"] == 0xD1, "控制码 = D1H")
    text = all_values(r)
    check("未入网" in text, "ERR=0x80 展开出「无线接口转换器未入网」")


# ── [9] 升级类 DI（构造帧）──────────────────────────────────────────
def test_upgrade_dis():
    # 04900105 最大升级块大小：0xF1 0x00 → 小端 241
    r = PARSER.parse(build("031288600000", 0x91, bytes.fromhex("05019004") + bytes([0xF1, 0x00])))
    check(r["di_code"] == "04900105", "DI 04900105 识别")
    check(row_value(r, "最大升级块大小").startswith("241"), "块大小 241 字节")

    # 04900101 块状态字：0b00000101 → bit0/bit2
    r = PARSER.parse(build("031288600000", 0x91, bytes.fromhex("01019004") + bytes([0b00000101])))
    check(row_raw(r, "传输进度").startswith("2"), "块状态字两位置位（bit0 + bit2）")
    check(row_value(r, "连续性") == "存在空洞（中间有未传输块）", "bit1 未置位 → 判定存在空洞")

    # 04900102 状态信息：文件名 32 + CRC32 4 + 状态 1
    name = "fw_v1.bin".encode().ljust(32, b"\x00")
    body = name + bytes([0x78, 0x56, 0x34, 0x12]) + bytes([6])
    r = PARSER.parse(build("031288600000", 0x91, bytes.fromhex("02019004") + body))
    check(row_value(r, "升级文件名") == "fw_v1.bin", "升级文件名 ASCII 解析")
    check(row_value(r, "升级状态") == "升级成功", "状态 6 → 升级成功")

    # 04900106 执行升级时间：2026-10-24 14:30 → 低字节在前 30 14 24 10 26
    r = PARSER.parse(build("031288600000", 0x91,
                           bytes.fromhex("06019004") + bytes([0x30, 0x14, 0x24, 0x10, 0x26])))
    check("2026-10-24 14:30" in row_value(r, "执行升级时间"),
          f"BCD 时间解出 2026-10-24 14:30（实际 {row_value(r, '执行升级时间')}）")

    # 04900106 全 FF = 立即执行
    r = PARSER.parse(build("031288600000", 0x91, bytes.fromhex("06019004") + b"\xFF" * 5))
    check("立即执行" in row_value(r, "执行升级时间"), "全 FF → 立即执行")

    # 04900107 版本信息（ASCII）
    r = PARSER.parse(build("031288600000", 0x91, bytes.fromhex("07019004") + b"V1.6"))
    check(row_value(r, "版本信息") == "V1.6", "版本信息 ASCII 解析")

    # 04900104 块序号 + 数据
    r = PARSER.parse(build("031288600000", 0x14,
                           bytes.fromhex("04019004") + bytes([0x03, 0x00, 0xAA, 0xBB])))
    check(row_value(r, "升级块序号") == "3", "块序号 0x0003 → 3")
    check(row_raw(r, "升级块数据") == "AABB", "块数据原样展示")


# ── [10] 反例：普通 645 DI 不走本模块 ───────────────────────────────
def test_not_wireless():
    payload = bytes.fromhex("00000001") + bytes([0x12, 0x34, 0x56, 0x78])
    r = PARSER.parse(build("000000000001", 0x91, payload))
    check(r["di_code"] == "01000000", "普通 DI 正常识别")
    check("光伏逆变器数据转发" not in r["di_desc"], "普通 DI 不被无线扩展接管")
    check(not any("无线扩展" in (str(row[3]) if len(row) > 3 else "") for row in r["fields"]), "字段里没有无线扩展行")


# ── 工具函数单测 ────────────────────────────────────────────────────
def test_helpers():
    check(wl.baud_text(0x01) == "115200bps", "特征字 bit0 → 115200bps")
    check(wl.baud_text(0x00).startswith("无"), "特征字 0 → 无（无效）")
    check("非法" in wl.baud_text(0x03), "多位置位 → 标记非法")
    check(wl.parity_text(2) == "偶校验", "校验 2 → 偶校验")
    check("保留值" in wl.parity_text(8), "校验 8 → 保留值")
    check(wl.upgrade_status_text(6) == "升级成功", "状态 6 → 升级成功")
    check("未定义" in wl.upgrade_status_text(99), "未定义状态如实标注")
    check("未入网" in wl.err_bits_text(0x80), "ERR 0x80 位展开含未入网")
    check("升级" in wl.di_summary(), f"DI 摘要：{wl.di_summary()}")


if __name__ == "__main__":
    print("=" * 62)
    print("南网光伏无线模组接口手册 V1.6 · 解析扩展回归")
    print("=" * 62)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        print(f"\n[{fn.__name__}]")
        try:
            fn()
        except Exception as exc:      # noqa: BLE001
            FAIL += 1
            print(f"  [ERR ] {type(exc).__name__}: {exc}")
    print("\n" + "=" * 62)
    print(f"结果：{PASS} 通过，{FAIL} 失败")
    print("=" * 62)
    raise SystemExit(1 if FAIL else 0)
