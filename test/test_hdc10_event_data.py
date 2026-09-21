# -*- coding: utf-8 -*-
"""协议11（HDC 1.0）事件上报报文（0x0008）数据域解析

用户（2026-09-20）:
    协议11，新增的应用手册和即装即采等扩展应用层协议，也需要集成到解析能力中。

依据（新提供并已转 MD 的两份文档）:
  1) ``协议文档/11.HDC协议/HPLC技术应用手册-中国电科院V2.7.md``
     附录 B.1「HPLC 相关协议」—— 停电/复电上报的事件上报 DATA 域扩展，
     位图方式（事件类型 1/2）与地址方式（事件类型 3/4）
  2) ``协议文档/11.HDC协议/2024年2批HDC模块即装即采增补协议要求(山东).md``
     附件3《Q/GDW 11612.43 协议扩增》—— 事件类型 51「设备信息」，
     含设备地址/协议类型/设备描述符 + M 台下挂设备清单
  并与 HDC 第4-3部分 §5.6.1.10 表30 / 表31 逐字段一致（互为印证）。

报文头（表26）：协议版本号(6b) / 报文头长度(6b，单位4字节字) / 方向位(1b) /
启动位(1b) / 功能码(6b) / 转发数据长度(12b) / 报文序号(2B) / 电能表地址(6B)，
故数据（DATA）自字节12 起。

覆盖:
  [1] 位图方式（事件类型 1/2）：起始TEI + 节点位图置位展开
  [2] 地址方式（事件类型 3/4）：电表个数 + N×(地址6B + 带电状态1B)
  [3] 设备信息（事件类型 51，即装即采附件3）：设备信息 + 下挂设备清单
  [4] 健壮性：保留事件类型 / 各段数据不足
  [5] 报文头长度 = 3×4B=12B（与数据域自字节12 起自洽）
  [6] 事件类型表防漂移

运行: python -X utf8 -u test/test_hdc10_event_data.py
"""

import os
import sys

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hdc10_parser import EVENT_TYPES, HDC10Parser  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

PASS = 0
FAIL = 0
FAILED = []

METER_ADDR = bytes.fromhex("123456789012")


def section(title):
    print(f"\n{title}")


def check(desc, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {desc}")
    else:
        FAIL += 1
        FAILED.append(desc)
        print(f"  ✗ {desc}" + (f"\n      {detail}" if detail else ""))


def build_event(data_domain: bytes, func_code: int = 2,
                direction: int = 1, start: int = 1) -> bytes:
    """构造事件上报应用层报文：报文头(12B) + DATA

    报文头长度 = byte0[6:7](高2b) + byte1[0:3](低4b)，单位 4 字节字；
    事件报文头 12 字节 → 3。
    """
    hdr_len = 3
    b0 = 0x01 | (((hdr_len >> 4) & 0x03) << 6)
    b1 = ((hdr_len & 0x0F)
          | (direction << 4) | (start << 5) | ((func_code & 0x03) << 6))
    dl = len(data_domain)
    b2 = ((func_code >> 2) & 0x07) | ((dl & 0x0F) << 4)
    b3 = (dl >> 4) & 0xFF
    return (bytes([b0, b1, b2, b3])
            + (0x0001).to_bytes(2, "little")
            + METER_ADDR
            + data_domain)


def rows_of(data_domain: bytes):
    return HDC10Parser()._parse_event(build_event(data_domain), 0)


def _cell(rows, name, idx):
    for r in rows:
        if str(r[0]).strip() == name:
            return str(r[idx]).strip()
    return None


def raw(rows, name):
    return _cell(rows, name, 1)


def val(rows, name):
    return _cell(rows, name, 2)


def cmt(rows, name):
    return _cell(rows, name, 3)


def main():
    # ── [1] 位图方式 ────────────────────────────────────────────
    section("[1] 位图方式（事件类型 1=停电 / 2=上电）")
    # 起始TEI=0x0102，位图 0b00000101 0b00000010 → 置位位号 0,2（首字节）+ 1（次字节）
    dom = bytes([1]) + (0x0102).to_bytes(2, "little") + bytes([0b00000101, 0b00000010])
    r = rows_of(dom)
    check("事件类型 = 停电事件（位图方式）",
          val(r, "事件类型") == "停电事件（位图方式）", str(val(r, "事件类型")))
    check("原始值 0x01", raw(r, "事件类型") == "0x01", str(raw(r, "事件类型")))
    check("发生事件站点起始TEI = 258",
          val(r, "发生事件站点起始TEI") == "258",
          str(val(r, "发生事件站点起始TEI")))
    # 位图置位展开：首字节 bit0/bit2 → TEI 258/260；次字节 bit1 → 258+8+1=267
    check("节点位图置位展开 = 258, 260, 267",
          cmt(r, "发生事件的节点位图") == "置位TEI: 258, 260, 267",
          str(cmt(r, "发生事件的节点位图")))
    check("节点位图字节数 = 2", "2字节" in str(val(r, "发生事件的节点位图")),
          str(val(r, "发生事件的节点位图")))
    check("上电事件（位图方式）= 2",
          val(rows_of(bytes([2, 0x01, 0x00])), "事件类型") == "上电事件（位图方式）")

    # ── [2] 地址方式 ────────────────────────────────────────────
    section("[2] 地址方式（事件类型 3=停电 / 4=上电）")
    dom = (bytes([3]) + (2).to_bytes(2, "little")
           + bytes.fromhex("111111111111") + bytes([0])
           + bytes.fromhex("222222222222") + bytes([1]))
    r = rows_of(dom)
    check("事件类型 = 停电事件（地址方式）",
          val(r, "事件类型") == "停电事件（地址方式）", str(val(r, "事件类型")))
    check("发生事件的电表个数 = 2",
          val(r, "发生事件的电表个数") == "2",
          str(val(r, "发生事件的电表个数")))
    check("电表1地址 = 111111111111（BCD 正序显示）",
          val(r, "电表1地址") == "111111111111", str(val(r, "电表1地址")))
    check("电表1带电状态 = 0（停电）",
          val(r, "电表1带电状态") == "0"
          and cmt(r, "电表1带电状态") == "0-停电 1-未停电",
          f"{val(r, '电表1带电状态')} / {cmt(r, '电表1带电状态')}")
    check("电表2地址 = 222222222222",
          val(r, "电表2地址") == "222222222222", str(val(r, "电表2地址")))
    check("电表2带电状态 = 1（未停电）",
          val(r, "电表2带电状态") == "1", str(val(r, "电表2带电状态")))
    check("上电事件（地址方式）= 4",
          val(rows_of(bytes([4, 0x00, 0x00])), "事件类型") == "上电事件（地址方式）")

    # ── [3] 设备信息（即装即采附件3，事件类型 51）───────────────
    section("[3] 设备信息（事件类型 51，即装即采附件3）")
    dom = (bytes([51])
           + bytes.fromhex("123456789012")      # 设备地址 BCD 6B
           + bytes([0x02])                       # 设备通信协议类型
           + bytes([5]) + b"DDZY1"               # 描述符长度 N + 描述符
           + bytes([2])                          # 下挂设备数量 M
           + bytes([6]) + bytes.fromhex("112233445566")
           + bytes([4]) + b"LKT1" + bytes([0x03])
           + bytes([6]) + bytes.fromhex("AABBCCDDEEFF")
           + bytes([7]) + b"DFDL33-" + bytes([0x02]))
    r = rows_of(dom)
    check("事件类型 = 设备信息（上报下挂设备）",
          val(r, "事件类型") == "设备信息（上报下挂设备）", str(val(r, "事件类型")))
    check("原始值 0x33 (=51)", raw(r, "事件类型") == "0x33", str(raw(r, "事件类型")))
    # BCD 通信地址按本文件既有约定**倒序显示**（线上低字节在前，与电能表地址一致）：
    # 线上 123456789012 → 显示 129078563412
    check("设备地址 = 129078563412（BCD 倒序显示）",
          val(r, "设备地址") == "129078563412", str(val(r, "设备地址")))
    check("设备通信协议类型 = DL/T645-2007",
          val(r, "设备通信协议类型") == "2"
          and cmt(r, "设备通信协议类型") == "DL/T645-2007",
          f"{val(r, '设备通信协议类型')} / {cmt(r, '设备通信协议类型')}")
    check("设备描述符长度 = 5字节",
          val(r, "设备描述符长度") == "5字节", str(val(r, "设备描述符长度")))
    check("设备描述符 = DDZY1（ASCII）",
          raw(r, "设备描述符") == "DDZY1", str(raw(r, "设备描述符")))
    check("下挂设备数量M = 2", val(r, "下挂设备数量M") == "2",
          str(val(r, "下挂设备数量M")))
    check("下挂设备1通信地址长度 = 6字节",
          val(r, "下挂设备1通信地址长度") == "6字节",
          str(val(r, "下挂设备1通信地址长度")))
    check("下挂设备1通信地址 = 665544332211（线上 112233445566 倒序）",
          val(r, "下挂设备1通信地址") == "665544332211",
          str(val(r, "下挂设备1通信地址")))
    check("下挂设备1设备描述符 = LKT1",
          raw(r, "下挂设备1设备描述符") == "LKT1",
          str(raw(r, "下挂设备1设备描述符")))
    check("下挂设备1通信协议类型 = DL/T698.45",
          cmt(r, "下挂设备1通信协议类型") == "DL/T698.45",
          str(cmt(r, "下挂设备1通信协议类型")))
    check("下挂设备2通信地址 = FFEEDDCCBBAA（线上 AABBCCDDEEFF 倒序）",
          val(r, "下挂设备2通信地址") == "FFEEDDCCBBAA",
          str(val(r, "下挂设备2通信地址")))
    check("下挂设备2设备描述符 = DFDL33-",
          raw(r, "下挂设备2设备描述符") == "DFDL33-",
          str(raw(r, "下挂设备2设备描述符")))
    check("下挂设备2通信协议类型 = DL/T645-2007",
          cmt(r, "下挂设备2通信协议类型") == "DL/T645-2007",
          str(cmt(r, "下挂设备2通信协议类型")))
    check("无剩余字节告警", val(r, "剩余数据") is None, str(val(r, "剩余数据")))

    # ── [4] 健壮性 ──────────────────────────────────────────────
    section("[4] 健壮性：保留事件类型 / 数据不足")
    r = rows_of(bytes([99, 0xAA, 0xBB]))
    check("保留事件类型 → 保留(99)",
          val(r, "事件类型") == "保留(99)", str(val(r, "事件类型")))
    check("保留事件类型 → 原始数据保留",
          raw(r, "事件数据") == "AA BB", str(raw(r, "事件数据")))
    check("位图方式数据不足 → 明确提示",
          "数据不足" in str(cmt(rows_of(bytes([1, 0x01])), "事件数据")),
          str(cmt(rows_of(bytes([1, 0x01])), "事件数据")))
    check("地址方式数据不足 → 明确提示",
          "数据不足" in str(cmt(rows_of(bytes([3, 0x01])), "事件数据")),
          str(cmt(rows_of(bytes([3, 0x01])), "事件数据")))
    check("地址方式电表清单截断 → 不抛异常",
          rows_of(bytes([3, 0x03, 0x00]) + bytes(7)) is not None)
    check("设备信息数据不足 → 明确提示",
          "数据不足" in str(cmt(rows_of(bytes([51, 0x01, 0x02])), "设备信息")),
          str(cmt(rows_of(bytes([51, 0x01, 0x02])), "设备信息")))
    check("设备描述符长度超出报文 → 明确提示",
          "数据不足" in str(cmt(rows_of(bytes([51]) + bytes(6) + bytes([2])
                                        + bytes([200]) + bytes([1])),
                                "设备描述符")),
          str(cmt(rows_of(bytes([51]) + bytes(6) + bytes([2])
                          + bytes([200]) + bytes([1])), "设备描述符")))
    check("空数据域 → 只出报文头，不抛异常",
          val(rows_of(b""), "事件类型") is None)

    # ── [5] 报文头长度自洽 ──────────────────────────────────────
    section("[5] 报文头长度 = 3×4B=12B（数据域自字节12 起）")
    r = rows_of(bytes([1, 0x01, 0x00]))
    check("事件上报报文 = 12字节头",
          val(r, "事件上报报文") == "12字节头", str(val(r, "事件上报报文")))
    check("方向位 = 1（上行）", val(r, "方向位") == "1", str(val(r, "方向位")))
    check("功能码 = 2（STA主动上报·模块触发）",
          val(r, "功能码") == "2", str(val(r, "功能码")))
    check("电能表地址 = 129078563412（BCD 倒序显示）",
          val(r, "电能表地址") == "129078563412", str(val(r, "电能表地址")))
    # ── [6] 事件类型表防漂移 ────────────────────────────────────
    section("[6] 事件类型表与两份规范一一对应（防漂移）")
    expect = {
        1: ("停电事件（位图方式）", "bitmap"),
        2: ("上电事件（位图方式）", "bitmap"),
        3: ("停电事件（地址方式）", "addr"),
        4: ("上电事件（地址方式）", "addr"),
        51: ("设备信息（上报下挂设备）", "device"),
    }
    check("EVENT_TYPES 与规范一致", EVENT_TYPES == expect,
          str({k: (EVENT_TYPES.get(k), v) for k, v in expect.items()
               if EVENT_TYPES.get(k) != v}))

    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    for n in FAILED:
        print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
