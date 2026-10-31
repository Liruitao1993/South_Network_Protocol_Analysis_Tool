# -*- coding: utf-8 -*-
"""协议7「国网协议测试」页（`gdw_test_core` + `gdw_test_widget`）回归。

覆盖：
  [1] 单一来源：AFN 页面归属恰好覆盖解析器 AFN_MAP、命令数与 schema 对拍、
      分类树叶子数 == 各页命令数（含 EB / 自定义）、名称与 AFN_MAP/FN_MAP 一致
  [2] 组帧：03-1 / 05-1 / 10-2 / 55-1(福建) / F1-1(扩展) 逐字节 golden；
      全部 122 条命令「默认值组帧 → 自家解析器回读 AFN/Fn 一致且校验通过」
  [3] EB 扩展：DI 线上序、645 帧逐字节（+0x33 加扰 / CS）、写入字段编码、
      转发外层 AFN=02H F1 的报文长度字段自洽、解析器能识别内嵌 EB
  [4] 判定矩阵：00H F1 确认 / F2 否认、错误代码、AFN 不符、Fn 不符、坏 CS、截断
  [5] 页面（offscreen）：五页签与惰性树、选中出预览、勾选顺序下发、
      等应答期间的 `_awaiting` 守卫、超时重试、停止、落盘往返、主题、cleanup
  [6] RX 自组帧：半帧两次交付、噪声重同步
  [7] 源码护栏：不 import main_gui、不用 send_frame、不直接连 raw_data_received、
      不手拼国网帧（组帧只经 core）

运行: python test/test_gdw_testbench.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

_cfg_dir = _config_sandbox.install()

for _name in ("warning", "information", "critical"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import gdw_test_core as C  # noqa: E402
import gdw_test_widget as W  # noqa: E402

FAILED = []
CHECKS = [0]


def section(title):
    print(f"\n-- {title} " + "-" * max(0, 66 - len(title)))


def check(name, got, want):
    CHECKS[0] += 1
    if got == want:
        print(f"  [OK] {name}")
        return True
    FAILED.append(f"{name}\n    got  = {got!r}\n    want = {want!r}")
    print(f"  [NG] {name}  -> {got!r}")
    return False


def check_true(name, cond, detail=""):
    return check(name, bool(cond), True) if cond else _fail(name, detail)


def _fail(name, detail=""):
    CHECKS[0] += 1
    FAILED.append(f"{name}" + (f"\n    {detail}" if detail else ""))
    print(f"  [NG] {name}  -> {detail}")
    return False


def expect_raises(name, fn, exc=C.FrameBuildError):
    CHECKS[0] += 1
    try:
        fn()
    except exc:
        print(f"  [OK] {name}")
        return True
    except Exception as other:                       # noqa: BLE001
        FAILED.append(f"{name}: 抛了 {type(other).__name__}（期望 {exc.__name__}）: {other}")
        return False
    FAILED.append(f"{name}: 没有抛 {exc.__name__}")
    return False


INFO = {"通信模块标识": 1, "中继级别": 0, "报文序列号": 1}
SRC, DST = "123456789012", "000000000001"


# ══════════════════════════════════════════════════════════════════════
def test_sources_and_catalog():
    section("[1] 单一来源与分类树")
    afns = set(C.GDW10376Parser.AFN_MAP)
    check("AFN_PAGE 恰好覆盖解析器 AFN_MAP", sorted(C.AFN_PAGE), sorted(afns))
    check("每个 AFN 只归属一个页面（dict 唯一）", len(C.AFN_PAGE), len(afns))
    check("全部命令数 == schema 条数", C.item_count(), len(C.GDW_AFNFN_SCHEMA))
    check("命令键集合与 schema 键逐条对拍",
          sorted((c.afn, c.fn) for c in C.all_commands()),
          sorted(C.GDW_AFNFN_SCHEMA))
    check("页面叶子总数 == 命令数",
          sum(C.leaf_count(p) for p in (C.PAGE_READ, C.PAGE_WRITE, C.PAGE_REPORT)),
          len(C.GDW_AFNFN_SCHEMA))
    for p in (C.PAGE_READ, C.PAGE_WRITE, C.PAGE_REPORT):
        check(f"{p} 页命令都归属于该页",
              all(C.AFN_PAGE[c.afn] == p for c in C.commands_for_page(p)), True)
    # 名称与 AFN/FN 表同源
    mismatched = []
    for c in C.all_commands():
        entry = C.GDW_AFNFN_SCHEMA[(c.afn, c.fn)]
        want = str(entry.get("name") or "")
        if want and want != c.name:
            mismatched.append((c.key, c.name, want))
    check("命令名与 schema 逐条一致（无第二份名称表）", mismatched, [])
    check("福建增补命令都在树里", len([c for c in C.all_commands() if c.source == "福建增补"]), 39)
    check("扩展命令（F0/F1）来源标记", sorted(C.command_source(a) for a in (0xF0, 0xF1)),
          ["扩展", "扩展"])
    # 树结构
    tree = C.catalog(C.PAGE_REPORT)
    check("上报页有 2 个功能域", [c.name for c in tree], ["基础功能", "福建增补"])
    groups = {g.key: g.name for c in tree for g in c.groups}
    check("AFN 节点名来自 AFN_MAP", groups.get("00"), "00H 确认/否认")
    check("EB 分组 5 组", [g[0] for g in C.eb_groups()], ["EB03", "EB04", "EBE0", "EB55", "EBEE"])
    check("EB 叶子数 75", C.leaf_count(C.PAGE_EB), 75)
    check("EB 有字段定义的条目进表单（56 条）",
          sum(1 for e in C.eb_items() if e.fields), 56)


# ══════════════════════════════════════════════════════════════════════
def test_framing():
    section("[2] 组帧 golden + 全命令回读")
    golden = {
        (3, 1): "68 1B 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 03 01 00 00 16",
        (5, 1): "68 21 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 05 01 00 00 00 00 00 00 01 03 16",
        (0x10, 2): "68 1E 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 10 02 00 01 00 01 10 16",
        (0x55, 1): "68 21 00 40 00 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 55 01 00 00 00 00 00 00 01 4F 16",
        (0xF1, 1): "68 1C 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 F1 01 00 00 EE 16",
    }
    golden_values = {(5, 1): {"主节点地址": "000000000001"},
                     (0x55, 1): {"主节点地址": "000000000001"}}
    for (afn, fn), want in golden.items():
        cmd = C.find_command(afn, fn)
        vals = golden_values.get((afn, fn), C.default_values(cmd))
        frame = C.build_frame(cmd, vals, src=SRC, dst=DST, info=INFO)
        check(f"{afn:02X}H F{fn} 逐字节 golden", frame.hex(" ").upper(), want)

    bad = []
    for cmd in C.all_commands():
        try:
            frame = C.build_frame(cmd, C.default_values(cmd), src=SRC, dst=DST)
            rows = C.parse_table(frame)
            afn_row = next((r for r in rows if r[0] == "应用功能码(AFN)"), None)
            dt_row = next((r for r in rows if r[0] == "数据单元标识(DT)"), None)
            result = C.verify_frame(frame)
            if (afn_row is None or int(afn_row[2]) != cmd.afn or dt_row is None
                    or (result is not None and not result.valid)):
                bad.append((cmd.key, cmd.name))
        except Exception as exc:                     # noqa: BLE001
            bad.append((cmd.key, cmd.name, f"{type(exc).__name__}: {exc}"))
    check("全部 122 条命令组帧后回读 AFN/Fn 且校验通过", bad, [])

    # 值语义：05H F1 的地址字段真的进了帧
    cmd = C.find_command(5, 1)
    frame = C.build_frame(cmd, {"主节点地址": "123456789012"}, src=SRC, dst=DST)
    check("05H F1 地址字段写入数据单元",
          bytes.fromhex("123456789012") in frame, True)

    # 上行模拟：附加数据单元（表 9：D0=1 已处理 + 信道全闲 + 等待时间 1s）
    cmd0 = C.find_command(0, 1)
    up = C.build_frame(cmd0, {}, src=SRC, dst=DST,
                       info={"通信模块标识": 1, "dir": 1, "prm": 0},
                       raw_data=bytes.fromhex("01 FF FF FF 01 00"))
    rows = C.parse_table(up)
    state = next((r for r in rows if r[0] == "  命令状态"), None)
    check_true("上行确认帧带命令状态（附加数据单元生效）",
               state is not None and state[2] == "已处理", state)
    wait_row = next((r for r in rows if r[0] == "  等待时间"), None)
    check_true("上行确认帧解析出等待时间（表 9 的 2 字节）",
               wait_row is not None and wait_row[2] == "1", wait_row)

    # 输入校验
    expect_raises("地址非 12 位十进制 → 可读错误",
                  lambda: C.build_frame(cmd, {}, src="123", dst=DST))
    expect_raises("字段超范围 → 可读错误",
                  lambda: C.build_frame(C.find_command(0xF0, 62), {"保留": 999999}))
    check("hex 解析容忍分隔符/0x/连续写法",
          C.parse_hex("0x68,12 34-56"), bytes([0x68, 0x12, 0x34, 0x56]))
    expect_raises("hex 奇数位拒绝", lambda: C.parse_hex("68 1"))


# ══════════════════════════════════════════════════════════════════════
def test_route_read_14h():
    """AFN=14H 路由数据抄读：F1~F4 下行数据单元（§6.5.12 表 122/125~128）。"""
    section("[2b] 14H 路由数据抄读 F1~F4")

    read_645 = "68 01 00 00 00 00 00 68 11 04 33 33 34 33 B3 16"

    # F1：抄读标志 02H + L>0 + 附属节点地址（线序低字节在前）
    f1 = C.find_command(0x14, 1)
    v1 = C.default_values(f1)
    v1["路由请求数据内容"] = read_645
    v1["从节点附属节点列表"] = [{"从节点附属节点地址": "000000000002"}]
    frame1 = C.build_frame(f1, v1, src=SRC, dst=DST, info=INFO)
    check("14H F1 逐字节 golden", frame1.hex(" ").upper(),
          "68 35 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 "
          "14 01 00 02 00 10 68 01 00 00 00 00 00 68 11 04 33 33 34 33 B3 16 "
          "01 02 00 00 00 00 00 A2 16")
    check("14H F1 抄读标志默认「可以抄读」", C.default_values(f1)["抄读标志"], 2)
    rows1 = {r[0].strip(): r for r in C.parse_table(frame1)}
    check("14H F1 数据长度由内容自动派生（16）", rows1["路由请求数据长度"][2], "16")
    check("14H F1 回读抄读标志", rows1["抄读标志"][2], "可以抄读")
    check("14H F1 附属节点地址低字节在前（界面正序 000000000002）",
          rows1["附属节点1地址"][2], "000000000002")
    check("14H F1 附属节点数量随列表自动填", rows1["从节点附属节点数量"][2], "1")

    # F2：6 字节 BCD 时钟（秒/分/时/日/月/年），默认取程序启动时刻
    f2 = C.find_command(0x14, 2)
    v2 = dict(C.default_values(f2))
    check("14H F2 有 6 个时间字段", len(f2.fields), 6)
    v2.update({"当前时间 秒": "05", "当前时间 分": "06", "当前时间 时": "07",
               "当前时间 日": "08", "当前时间 月": "09", "当前时间 年": "25"})
    frame2 = C.build_frame(f2, v2, src=SRC, dst=DST, info=INFO)
    check("14H F2 逐字节 golden（BCD 秒分时日月年）", frame2.hex(" ").upper(),
          "68 21 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 "
          "14 02 00 05 06 07 08 09 25 5A 16")
    rows2 = {r[0].strip(): r for r in C.parse_table(frame2)}
    # 1.26.9：BCD 字段要还原成十进制（0x25 → 25 年、0x05 → 05 秒）。
    # 旧实现直接 str(byte)，0x14 会被显示成「20 时」——对时链路会看成差 6 小时。
    check("14H F2 回读秒/年（BCD 还原）",
          (rows2["秒"][2], rows2["年(低字节)"][2]), ("05", "25"))
    check("14H F2 回读分/时（BCD 还原）",
          (rows2["分"][2], rows2["时"][2]), ("06", "07"))

    # F3：数据长度 L + 修正通信数据内容（L=0 表示放弃本次通信）
    f3 = C.find_command(0x14, 3)
    v3 = dict(C.default_values(f3))
    v3["修正通信数据内容"] = read_645
    frame3 = C.build_frame(f3, v3, src=SRC, dst=DST, info=INFO)
    check("14H F3 逐字节 golden", frame3.hex(" ").upper(),
          "68 2C 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 "
          "14 04 00 10 68 01 00 00 00 00 00 68 11 04 33 33 34 33 B3 16 A0 16")
    rows3 = {r[0].strip(): r for r in C.parse_table(frame3)}
    check("14H F3 回读数据长度", rows3["数据长度"][2], "16")
    check("14H F3 空内容 → L=0（放弃本次通信）",
          C.build_frame(f3, C.default_values(f3), src=SRC, dst=DST,
                        info=INFO).hex(" ").upper(),
          "68 1C 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 14 04 00 00 14 16")

    # F4：数据项类型 + 交采数据项标识(4B) + 交采数据项内容
    f4 = C.find_command(0x14, 4)
    v4 = dict(C.default_values(f4))
    check("14H F4 默认标识为正向有功总电能（低字节在前 00 00 01 00）",
          v4["交采数据项标识"], "00000100")
    check("14H F4 默认 5 字节（类型+标识）",
          C.build_frame(f4, v4, src=SRC, dst=DST, info=INFO).hex(" ").upper(),
          "68 20 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 "
          "14 08 00 01 00 00 01 00 1A 16")
    v4["交采数据项内容"] = "11 22 33 44"
    frame4 = C.build_frame(f4, v4, src=SRC, dst=DST, info=INFO)
    check("14H F4 带交采内容逐字节 golden", frame4.hex(" ").upper(),
          "68 24 00 40 04 00 00 00 00 01 12 90 78 56 34 12 01 00 00 00 00 00 "
          "14 08 00 01 00 00 01 00 11 22 33 44 C4 16")
    rows4 = {r[0].strip(): r for r in C.parse_table(frame4)}
    check("14H F4 回读数据项类型/标识",
          (rows4["数据项类型"][2], rows4["交采数据项标识"][2]),
          ("DL/T 645-2007", "00 00 01 00"))


def test_f104_range():
    """10H F104 查询升级后模块版本信息：必须带 节点起始序号(2B)+节点数量(1B)。

    文档 2024 版 OCR 缺 F104 小节，现场实测该 CCO 要求给查询范围，否则回
    「错误状态字=2 长度错」—— 空数据单元等于没告诉 CCO 查哪些节点。
    """
    section("[2c] 10H F104 查询范围")
    cmd_f104 = C.find_command(0x10, 104)
    check("F104 有起始序号字段", [f["name"] for f in cmd_f104.fields],
          ["节点起始序号", "节点数量"])
    check("F104 默认查 CCO（序号 0）", C.default_values(cmd_f104),
          {"节点起始序号": 0, "节点数量": 1})
    frame = C.build_frame(cmd_f104, {"节点起始序号": 1, "节点数量": 3},
                          src=SRC, dst=DST, info=INFO)
    rows = {r[0].strip(): r for r in C.parse_table(frame)}
    check("F104 数据单元 = 01 00 03", rows["数据单元"][1], "01 00 03")
    check("F104 回读起始序号", rows["节点起始序号"][2], "1")
    check("F104 回读数量", rows["节点数量"][2], "3")


def _make_up_frame(afn: int, dt1: int, dt2: int, data_unit: bytes) -> bytes:
    """造一条上行帧（C=83，R 全 0，无地址域），布局同现场示例。"""
    payload = bytes([0x83]) + b"\x00" * 6 + bytes([afn, dt1, dt2]) + bytes(data_unit)
    total = len(payload) + 5          # 68 + L(2) + payload + CS + 16
    head = bytes([0x68, total & 0xFF, (total >> 8) & 0xFF]) + payload
    cs = sum(payload) & 0xFF
    return head + bytes([cs, 0x16])


def test_f104_uplink():
    """10H F104 上行（《HPLC 远程升级方案》2.4.2(2) 定义 + 现场实例）。"""
    section("[2d] 10H F104 上行解析")
    up = C.parse_hex(
        "68 21 00 83 00 00 00 00 00 00 10 80 12 01 00 01 01 00 00 00 00 00 15 01 21 03 19 "
        "48 4C 31 41 99 16")
    rows = {r[0].strip(): r for r in C.parse_table(up)}
    check("示例帧识别为 F104（DT2=0x12 按组 12 解释）",
          rows["数据单元标识(DT)"][3].split("（")[0], "F104=查询升级后模块版本信息")
    check("节点总数量", rows["节点总数量"][2], "1")
    check("本次应答数量", rows["本次应答数量"][2], "1")
    check("节点地址按线序还原", rows["节点1地址"][2], "000000000001")
    check("软件版本号 BCD", rows["节点1软件版本号"][2], "15.01")
    check("版本日期 日/月/年", rows["节点1版本日期"][2], "2019-03-21")
    check("模块厂商代码", rows["节点1模块厂商代码"][2], "HL")
    check("芯片代码", rows["节点1芯片代码"][2], "1A")
    # 示例帧的 CS=0x99 与任何求和对不上（求和应为 0x81），解析器必须如实报错而不是掩盖
    check("示例 CS 如实报不匹配", rows["校验和(CS)"][2], "0x81")

    # 多节点：两个节点各 15 字节（地址6 + 信息9）
    node_info_1 = bytes.fromhex("1501210319484C3141")
    node_info_2 = bytes.fromhex("0A0205032058505830")
    multi = (bytes([2, 0, 2])
             + bytes.fromhex("010000000000") + node_info_1
             + bytes.fromhex("020000000000") + node_info_2)
    check("测试用多节点数据单元长度 = 3 + 2×15", len(multi), 33)
    up2 = _make_up_frame(0x10, 0x80, 0x0C, multi)
    rows2 = {r[0].strip(): r for r in C.parse_table(up2)}
    check("多节点：总数量 2", rows2["节点总数量"][2], "2")
    check("多节点：第 2 个地址", rows2["节点2地址"][2], "000000000002")
    check("多节点：第 2 个厂商/芯片",
          (rows2["节点2模块厂商代码"][2], rows2["节点2芯片代码"][2]), ("XP", "X0"))


def test_f104_down_range():
    """10H F104 下行：序号从 0 开始（0=CCO），数量建议 ≤15。"""
    section("[2e] 10H F104 下行查询范围")
    cmd_f104 = C.find_command(0x10, 104)
    check("默认查 CCO（序号 0）", C.default_values(cmd_f104)["节点起始序号"], 0)
    frame = C.build_frame(cmd_f104, {"节点起始序号": 1, "节点数量": 3},
                          src=SRC, dst=DST, info=INFO)
    rows = {r[0].strip(): r for r in C.parse_table(frame)}
    check("数据单元 = 01 00 03", rows["数据单元"][1], "01 00 03")
    check("起始序号 1（第 1 个 STA）", rows["节点起始序号"][2], "1")
    check("数量备注含 0=CCO", "0=CCO" in rows["节点起始序号"][3], True)
    check("数量上限提示 ≤15", "15" in rows["节点数量"][3], True)


# ══════════════════════════════════════════════════════════════════════
def test_eb():
    section("[3] EB 扩展（645 帧 + 转发外层）")
    check("DI 线上序为低字节在前", C._di_wire("EB030001"), bytes([0x01, 0x00, 0x03, 0xEB]))
    check("645 地址 BCD 低字节在前", C._bcd645("000000000001"), bytes([0x01, 0, 0, 0, 0, 0]))
    frame = C.build_eb_645("EB030001", addr="000000000001", ctrl=0x11)
    check("读请求 645 帧逐字节（DI +0x33）",
          frame.hex(" ").upper(),
          "68 01 00 00 00 00 00 68 11 04 34 33 36 1E A1 16")
    check("读请求 CS 自洽", frame[-2], sum(frame[:-2]) & 0xFF)

    write = C.build_eb_645("EB030001", addr="000000000001", ctrl=0x14, data=b"\x01")
    check("写请求 645 帧逐字节（数据也 +0x33）",
          write.hex(" ").upper(),
          "68 01 00 00 00 00 00 68 14 05 34 33 36 1E 34 D9 16")
    check("写请求 CS 自洽", write[-2], sum(write[:-2]) & 0xFF)

    encoded = C.encode_eb_data("EB030001", {"引脚状态": 1})
    check("字段编码器：引脚状态=发生 → 0x01", encoded, b"\x01")

    wrapped = C.build_eb_frame("EB030001", addr="000000000001", data=b"\x01",
                               src=SRC, dst=DST, info=INFO)
    rows = C.parse_table(wrapped)
    msg_len = next((r for r in rows if r[0] == "  报文长度"), None)
    afn_row = next((r for r in rows if r[0] == "应用功能码(AFN)"), ("", "", "", ""))
    check("转发外层 AFN=02H F1", "AFN=02H" in str(afn_row[3]), True)
    check("报文长度 == 内层 645 帧长度",
          int(msg_len[2]) if msg_len else None, len(write))
    # 解析器的内嵌 EB 展开入口（52H/56H 上行用）：用我们组的 645 帧直接喂它自证
    eb_rows = []
    ok_embedded = C.GDW10376Parser()._try_parse_embedded_eb(
        C.build_eb_645("EB030001", addr="000000000001", data=b"\x01"), 0, eb_rows)
    check("解析器按同一口径展开我们的 645 帧（DI/数据 +0x33）", ok_embedded, True)
    check_true("展开出行含 EB 数据标识 EB030001",
               any("EB030001" in str(r[1]) or "EB030001" in str(r[2]) for r in eb_rows),
               eb_rows[:3])
    expect_raises("EB 写入控制码仅 11/13/14",
                  lambda: C.build_eb_645("EB030001", addr="000000000001", ctrl=0x99))
    expect_raises("EB DI 8 位校验", lambda: C._di_wire("EB0300"))


# ══════════════════════════════════════════════════════════════════════
def test_evaluate():
    section("[4] 响应判定")
    cmd = C.find_command(3, 1)
    ok_frame = C.build_frame(cmd, {}, src=SRC, dst=DST, info=INFO)
    res = C.evaluate_response(cmd, ok_frame)
    check("同命令响应：matched=True", res["matched"], True)
    check("无可自证成功字段 → ok=None（不冒充成功）", res["ok"], None)

    # 00H F1 确认
    c0 = C.find_command(0, 1)
    up = C.build_frame(c0, {}, src=SRC, dst=DST,
                       info={"通信模块标识": 1, "dir": 1, "prm": 0},
                       raw_data=bytes([0xC0, 0, 0, 0]))
    r = C.evaluate_response(c0, up)
    check("00H F1 确认 → ok=True", (r["ok"], r["reason"]), (True, "确认"))
    # 00H F2 否认（错误状态字=1）
    c0d = C.find_command(0, 2)
    deny = C.build_frame(c0d, {}, src=SRC, dst=DST,
                         info={"通信模块标识": 1, "dir": 1, "prm": 0},
                         raw_data=bytes([0x01]))
    r = C.evaluate_response(c0d, deny)
    check_true("00H F2 否认 → ok=False 且带状态字说明",
               r["ok"] is False and "错误状态字" in r["reason"], r["reason"])

    # AFN 不符
    r = C.evaluate_response(C.find_command(5, 1), ok_frame)
    check("AFN 不符 → matched=False", (r["matched"], "AFN 不符" in r["reason"]),
          (False, True))
    # 坏 CS
    broken = bytearray(ok_frame); broken[-2] = (broken[-2] + 1) & 0xFF
    r = C.evaluate_response(cmd, bytes(broken))
    check("坏 CS → ok=False", (r["ok"], r["matched"]), (False, False))
    # 截断
    r = C.evaluate_response(cmd, ok_frame[:-3])
    check("截断 → ok=False", r["ok"], False)
    # 空
    r = C.evaluate_response(cmd, b"")
    check("空帧 → ok=False 且有原因", r["ok"] is False and bool(r["reason"]), True)


# ══════════════════════════════════════════════════════════════════════
class FakeSerial(QObject):
    raw_data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)
    log_message = Signal(str)
    frame_received = Signal(bytes)

    def __init__(self):
        super().__init__()
        self.sent = []
        self.opened = True
        self.closed = 0

    def is_open(self):
        return self.opened

    def write_raw(self, data):
        self.sent.append(bytes(data))
        return True

    def close_port(self):                     # 页面不得调用
        self.closed += 1


def pump(ms: int = 60) -> None:
    """跑一会儿事件循环（队列推进用 10ms 单发定时器，不能只 processEvents）。"""
    QTest.qWait(ms)
    QApplication.instance().processEvents()


def make_widget():
    app = QApplication.instance() or QApplication(sys.argv)
    w = W.GdwTestWidget()
    w.resize(1280, 820)
    w.show()
    app.processEvents()
    return w


def test_widget():
    section("[5] 页面（offscreen）")
    w = make_widget()
    worker = FakeSerial()
    w.set_serial_worker(worker)
    app = QApplication.instance()

    check("五个页签", [w.page_tabs.tabText(i) for i in range(w.page_tabs.count())],
          [label for _k, label in C.PAGES])
    # 布局对齐 698：左树 / 中参数 / 右日志（日志必须在最右，别放回底部）
    check("三栏水平分栏", w.main_split.count(), 3)
    check("第三栏就是收发日志", w.main_split.widget(2) is w.log_group, True)
    check("收发表格在底部（横跨）",
          w.detail_tabs.parentWidget() is w and w.main_split.indexOf(w.detail_tabs) == -1, True)
    check("默认在读取数据页", w._page, C.PAGE_READ)
    check("树惰性构建：读取页叶子数", sum(1 for _ in w._iter_leaves(w._trees[C.PAGE_READ])),
          C.leaf_count(C.PAGE_READ))
    # 切到各页 → 构建并计数
    for page in (C.PAGE_WRITE, C.PAGE_REPORT, C.PAGE_EB, C.PAGE_CUSTOM):
        w._select_page(page, notify=True)
        app.processEvents()
        if page == C.PAGE_CUSTOM:
            tree = w._trees[page]
            check("自定义页为空时给空态提示（无叶子）",
                  (sum(1 for _ in w._iter_leaves(tree)), tree.topLevelItemCount(),
                   "暂无自定义" in tree.topLevelItem(0).text(0)),
                  (0, 1, True))
        else:
            got = sum(1 for _ in w._iter_leaves(w._trees[page]))
            check(f"{page} 页叶子数", got, C.leaf_count(page))

    # 选中 03H F1 → 预览
    w._select_page(C.PAGE_READ)
    app.processEvents()
    leaf = w._find_leaf(w._trees[C.PAGE_READ], "03-1")
    check("能找到 03-1 叶子", leaf is not None, True)
    leaf.setSelected(True)
    app.processEvents()
    check("选中后当前命令 = 03H F1", (w._current.afn, w._current.fn), (3, 1))
    preview_lines = w.plain_cmd_preview.toPlainText().splitlines()
    check_true("预览帧以 68 开头、16 结尾",
               len(preview_lines) >= 2 and preview_lines[1].startswith("68")
               and preview_lines[1].endswith("16"), preview_lines[:2])

    # 勾选 2 条 → 顺序下发；等应答期间不得再发
    w._checked[C.PAGE_READ] = ["03-1", "03-2"]
    w._on_send()
    app.processEvents()
    check("第一条已发出", len(worker.sent), 1)
    w._on_send()
    app.processEvents()
    check("等应答期间重复点发送被拦截（_awaiting 守卫）", len(worker.sent), 1)
    w._send_next()
    pump()
    check("直接调用 _send_next 也不重发（同一守卫）", len(worker.sent), 1)
    w._on_frame(worker.sent[0])               # 喂同命令响应 → 推进
    pump()
    check("推进到第二条", len(worker.sent), 2)
    check("第二条是 03H F2", worker.sent[1].hex(" ").upper().split()[22:24], ["03", "02"])
    w._on_frame(worker.sent[1])
    pump()
    check("本轮结束（不在运行态）", w.btn_send.isEnabled(), True)

    # 超时重试
    w._checked[C.PAGE_READ] = ["03-1"]
    w.spin_timeout.setValue(100)
    w.spin_retries.setValue(1)
    w._on_send()
    app.processEvents()
    n = len(worker.sent)
    w._on_reply_timeout()
    app.processEvents()
    check("超时重发同一帧（+1）", len(worker.sent), n + 1)
    check("重发帧与首帧一致", worker.sent[-1], worker.sent[-2])
    w._on_reply_timeout()
    app.processEvents()
    check("重试用尽后停止等待", w._awaiting, False)

    # 停止
    w.spin_retries.setValue(3)
    w._on_send()
    app.processEvents()
    w._on_stop()
    check("停止后按钮复位", (w.btn_send.isEnabled(), w.btn_stop.isEnabled()), (True, False))

    # EB 页写入
    w._select_page(C.PAGE_EB)
    app.processEvents()
    eb_leaf = w._find_leaf(w._trees[C.PAGE_EB], "EB030001")
    eb_leaf.setSelected(True)
    app.processEvents()
    check("EB 页当前数据标识", w._current_eb.di, "EB030001")
    check("EB 预览含 +0x33 后的 DI（34 33 36 1E）",
          "34 33 36 1E" in w.plain_eb_preview.toPlainText().upper(), True)
    w.combo_eb_ctrl.setCurrentIndex(1)        # 14H 写
    app.processEvents()
    check("写模式预览含数据字节（+0x33 = 34）",
          " 34 " in w.plain_eb_preview.toPlainText().upper(), True)

    # 落盘 / 重开（显式改一个非默认地址，验证真的恢复）
    w.edit_src.setText("123456789012")
    w._save_persisted()
    import json
    cfg = json.loads((_cfg_dir / W.CONFIG_NAME).read_text(encoding="utf-8"))
    check("落盘含地址与页面", (cfg["src"], cfg["dst"], cfg["page"]),
          (w.edit_src.text(), w.edit_dst.text(), w._page))
    check("落盘含勾选", cfg["checked"].get(C.PAGE_READ), ["03-1"])
    w2 = W.GdwTestWidget()
    check("重开恢复地址与 EB 控制码", (w2.edit_src.text(), w2.combo_eb_ctrl.currentData()),
          ("123456789012", 0x14))
    w2.cleanup()

    # 主题
    w.restyle_for_theme(True)
    check("深色主题下日志底色为深色",
          "#1e1e1e" in w.log_text.styleSheet().lower(), True)
    w.restyle_for_theme(False)

    # 按钮宽度不裁字（陷阱 63）
    narrow = [b for b in (w.btn_send, w.btn_stop, w.btn_clear, w.btn_all, w.btn_none)
              if b.width() < b.sizeHint().width()]
    check("按钮宽度 >= sizeHint（不裁字）", narrow, [])

    # 几何：日志与中栏同一行（右侧），底部表格在两者之下
    app.processEvents()
    lg, ctr = w.log_group.geometry(), w.center_stack.geometry()
    dt = w.detail_tabs.geometry()
    check_true("日志与参数区同一行（顶边对齐）", abs(lg.top() - ctr.top()) <= 2,
               (lg.top(), ctr.top()))
    check_true("日志在参数区右侧", lg.left() >= ctr.right(), (lg.left(), ctr.right()))
    check_true("底部信息/报文表在两栏之下", dt.top() >= max(lg.bottom(), ctr.bottom()) - 2,
               (dt.top(), lg.bottom(), ctr.bottom()))

    # 空间预算（1000×700 类矮窗口也要保住树/日志）
    check_true("分类树高度 >= 树下限", w._trees[C.PAGE_READ].height() >= W.TREE_MIN_HEIGHT,
               w._trees[C.PAGE_READ].height())
    w.resize(1000, 700)
    QApplication.instance().processEvents()
    check_true("1000×700 下日志仍 >= 日志下限",
               w.log_text.height() >= W.LOG_MIN_HEIGHT, w.log_text.height())
    check_true("1000×700 下分类树仍 >= 树下限",
               w._trees[C.PAGE_READ].height() >= W.TREE_MIN_HEIGHT,
               w._trees[C.PAGE_READ].height())
    check_true("底部详情区不超上限",
               w.detail_tabs.height() <= W.DETAIL_MAX_HEIGHT + 40, w.detail_tabs.height())

    # cleanup 不关端口
    w.cleanup()
    check("cleanup 不关闭串口（端口归主窗口）", worker.closed, 0)


def test_rx_framing():
    section("[6] RX 自组帧与重同步")
    w = make_widget()
    worker = FakeSerial()
    w.set_serial_worker(worker)
    cmd = C.find_command(3, 1)
    frame = C.build_frame(cmd, {}, src=SRC, dst=DST, info=INFO)
    seen = []
    orig = w._on_frame
    w._on_frame = lambda f: (seen.append(bytes(f)), orig(f))[1]  # type: ignore
    # 半帧两次交付
    worker.raw_data_received.emit(frame[:5])
    QApplication.instance().processEvents()
    check("半帧不提前出帧", seen, [])
    worker.raw_data_received.emit(frame[5:])
    QApplication.instance().processEvents()
    check("两次交付拼成一帧", seen, [frame])
    # 噪声前缀
    seen.clear()
    worker.raw_data_received.emit(b"\x11\x22" + frame)
    QApplication.instance().processEvents()
    check("噪声重同步后仍能出帧", seen, [frame])
    w.cleanup()


def test_source_guards():
    section("[7] 源码护栏")
    src = open("gdw_test_widget.py", encoding="utf-8").read()
    check("不 import main_gui", "import main_gui" not in src, True)
    check("不用 worker.send_frame（改通道控制器）", "worker.send_frame" not in src, True)
    check("不直接订阅 raw_data_received", "raw_data_received.connect" not in src, True)
    check("不手拼国网帧（68 帧只在 core）",
          "b\"\\x68\"" not in src and "0x16]" not in src, True)
    core_src = open("gdw_test_core.py", encoding="utf-8").read()
    check("core 不 import Qt", "PySide6" not in core_src, True)
    check("core 组帧只经 GDWFrameGenerator",
          core_src.count("GDWFrameGenerator().generate_frame"), 1)


def main():
    print("=" * 74)
    print("协议7 国网协议测试页 —— gdw_test_core / gdw_test_widget")
    print("=" * 74)
    test_sources_and_catalog()
    test_framing()
    test_route_read_14h()
    test_f104_range()
    test_f104_uplink()
    test_f104_down_range()
    test_eb()
    test_evaluate()
    test_widget()
    test_rx_framing()
    test_source_guards()
    print("\n" + "=" * 74)
    if FAILED:
        print(f"失败 {len(FAILED)} 项 / 通过 {CHECKS[0] - len(FAILED)} 项")
        for f in FAILED:
            print("  * " + f)
        sys.stdout.flush()
        os._exit(1)
    print(f"全部通过（{CHECKS[0]} 项）")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
