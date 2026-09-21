# -*- coding: utf-8 -*-
"""TCP 监控：协议11（HDC 1.0）自动解析能力 —— 五类帧 + 自动识别排序

用户（2026-09-20）:
    GUI协议11，TCP自动解析能力，能够解析ED封装头、网络层、应用层、ACK、
    SOF帧、信标帧、网间协调帧，等帧类型。

覆盖:
  [1] ED 包装布局判别：真实帧不得被误判 plc2（否则业务帧整体错位 1 字节）
  [2] 协议11 显式选择：DT=0/1/2/3 四类帧控制帧 + MAC 应用层帧的摘要文案
  [3] 自动识别：四类帧控制帧必须归 HDC 1.0（原先全部误判为南网新一代）
  [4] 回归锚点：南网新一代帧不得被重排到 HDC 1.0；协议10 不得被改判
  [5] 边界帧：触发 plc2 误判条件（业务帧第 2 字节低 4 位 ∈{0,1}）的 SACK/网间协调
  [6] 已声明的自动识别边界（MAC/应用层需显式选协议）+ _fallback_summary 兼容

**已声明边界**：自动识别只按 CRC-24 自证的帧控制证据重排，覆盖信标帧 / SOF 帧 /
选择确认帧(SACK) / 网间协调帧四类；MAC/应用层帧需在协议下拉框显式选「HDC 1.0」。
原因是「像 HDC MAC 帧」的结构启发式经实测会误伤南网新一代帧（详见
``monitor.tcp_monitor.hdc_fc_evidence`` 的 docstring）。

运行: python -X utf8 -u test/test_tcp_monitor_proto11_frames.py
"""

import os
import sys

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402
from batch_core import resolve_ed_wrapper  # noqa: E402
from csg_new_gen_parser import CSGNewGenParser  # noqa: E402
from gw_new_gen_parser import GWNewGenParser  # noqa: E402
from hdc10_parser import HDC10Parser, _crc24, looks_like_hdc_fc  # noqa: E402
import main_gui  # noqa: E402
from monitor.tcp_monitor import (  # noqa: E402
    TCPMonitorWidget,
    _strip_wrapper_common_header,
    evidenced_ed_wrapper,
    hdc_fc_evidence,
)
from hdc10_tcp_ed_frames import FRAMES  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

_config_sandbox.install()

PASS = 0
FAIL = 0
FAILED = []

# DT → 用户可见的帧类型名（hdc10_parser.DELIMITER_TYPES 的文案契约）
DT_NAMES = {
    0: "信标帧",
    1: "SOF帧",
    2: "选择确认帧(SACK)",
    3: "网间协调帧",
}

# 协议11 真实 MAC（应用层）帧：MAC 头 + MSDU(网络管理/关联请求) + ICV
HDC10_MAC = bytes.fromhex(
    "00000100019673005C80FF0800960000"
    "200000000124010101010101"
    "000000002000000001240100000000000000000001030001"
    "329FBACA69DE640900000000A860CAF104A18A64E8F2"
    "0000040099F4484C3039000000000000000065F9"
    "0000000000000000000000000000000000000000000000000000"
    "688150C40000000000000000BA711E"
)

# 协议10 真实帧（取自 test/test_gw_new_gen.py）
GW_REAL = bytes.fromhex(
    "C12000010001B2B7000F80FF0000010080000000000100909801022905"
    "0303E0C42855000465ED"
)

# 协议9 真实帧（取自 test/test_csg_new_gen.py）
CSG_FRAMES = {
    "关联请求": bytes.fromhex("110101000000000100010000"),
    # 关键锚点：本帧按 gx 误读后错位 1 字节，恰好能通过 HDC MAC 结构检查
    "FC+PB": bytes.fromhex(
        "11010100110000010001"
        "0000000000001122334455660A000300010203"
    ),
    "MAC级": bytes.fromhex(
        "11010100118001010002"
        "000000000000112233445566000005001122334455"
    ),
    "应用层": bytes.fromhex("11010100120004010005" "0A000000"),
}


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


def wrap_ed_gx(business: bytes, channel: int = 0x01) -> bytes:
    """按 gx 布局（8 字节数据域公共头）装成 ED..EE 监控包装帧。"""
    data = (
        (0x11223344).to_bytes(4, "little")
        + bytes([channel, 0x01])
        + len(business).to_bytes(2, "little")
        + business
    )
    body = bytes([0x00, 0x02, 0xEF]) + data
    frame_len = len(body) + 1
    cs = sum(bytes([0xED]) + frame_len.to_bytes(2, "little") + body) & 0xFF
    return bytes([0xED]) + frame_len.to_bytes(2, "little") + body + bytes([cs, 0xEE])


def wrap_ed_plc2(business: bytes) -> bytes:
    """按 plc2 布局（9 字节数据域公共头）装成 ED..EE 监控包装帧。"""
    data = (
        bytes([0x01])
        + (0x11223344).to_bytes(4, "little")
        + bytes([0x01, 0x00])
        + len(business).to_bytes(2, "little")
        + business
    )
    body = bytes([0x00, 0x02, 0xEF]) + data
    frame_len = len(body) + 1
    cs = sum(bytes([0xED]) + frame_len.to_bytes(2, "little") + body) & 0xFF
    return bytes([0xED]) + frame_len.to_bytes(2, "little") + body + bytes([cs, 0xEE])


def build_fc(dt: int, var8: bytes, nid_low: int = 0x01) -> bytes:
    """构造合法 HDC 1.0 帧控制（FCCS 用解析器自带 CRC-24 自洽计算）。"""
    body = bytes([dt, nid_low, 0x00, 0x00]) + var8 + bytes([0x00])
    return body + _crc24(body).to_bytes(3, "little")


def make_widget(gw_parser=None, csg_parser=None, hdc_parser=None):
    """构造与 main_gui 接线一致的监控器（摘要函数为**绑定**方法）。"""

    class Host:
        _get_gw_new_gen_summary = main_gui.MainWindow._get_gw_new_gen_summary
        _get_csg_new_gen_summary = main_gui.MainWindow._get_csg_new_gen_summary
        _TEST_MODE_SENTINELS = main_gui.MainWindow._TEST_MODE_SENTINELS
        _extract_test_mode_content = staticmethod(
            main_gui.MainWindow._extract_test_mode_content
        )

    host = Host()
    w = TCPMonitorWidget()
    w.set_parsers(
        gw_parser if gw_parser is not None else GWNewGenParser(),
        csg_parser if csg_parser is not None else CSGNewGenParser(),
        gw_summary_fn=host._get_gw_new_gen_summary,
        csg_summary_fn=host._get_csg_new_gen_summary,
        hdc10_parser=hdc_parser if hdc_parser is not None else HDC10Parser(),
        hdc10_summary_fn=host._get_gw_new_gen_summary,
    )
    return w


def select(w, mode: str):
    w.proto_combo.setCurrentIndex(w.proto_combo.findText(mode))


def main():
    w = make_widget()

    # ── [1] ED 包装布局判别 ────────────────────────────────────
    section("[1] ED 包装布局判别：真实帧必须判为 gx(8B 公共头)")
    check("固件帧数 >= 40", len(FRAMES) >= 40, f"实际 {len(FRAMES)}")
    dts = sorted({dt for dt, _ in FRAMES})
    check("固件覆盖 DT=0/1/2/3", dts == [0, 1, 2, 3], str(dts))

    # 说明：本固件全部为 gx 布局、业务帧第 2 字节均为 0x94，**不触发** plc2 误判
    # 条件，因此本段锁定的是「真实帧未被改坏」；布局判别的有效性由 [5] 对抗帧证明。
    bad_wrapper = [
        (dt, hex_str[:24])
        for dt, hex_str in FRAMES
        if evidenced_ed_wrapper(bytes.fromhex(hex_str), 11) != "gx"
    ]
    check("全部真实帧判为 gx", not bad_wrapper, str(bad_wrapper[:3]))

    # 直接锁「解包所用布局 == gx」。不走 looks_like_hdc_fc 中转，否则与
    # evidenced_ed_wrapper 的定义（试剥两种布局取 CRC 自证者）近乎同义反复。
    mismatch = [
        hex_str[:24]
        for _dt, hex_str in FRAMES
        if TCPMonitorWidget._unwrap_ed_for_parse(
            w, bytes.fromhex(hex_str), 11
        )[1] != _strip_wrapper_common_header(bytes.fromhex(hex_str), "gx")
    ]
    check("解包布局与 gx 一致（未错位 1 字节）", not mismatch, str(mismatch[:3]))

    # ── [2] 协议11 显式：四类帧控制帧 + MAC 应用层 ──────────────
    section("[2] 协议11（HDC 1.0）显式选择：五类帧解析与摘要")
    select(w, "HDC 1.0")

    per_dt = {}
    for dt, hex_str in FRAMES:
        per_dt.setdefault(dt, []).append(hex_str)

    for dt in (0, 1, 2, 3):
        samples = per_dt.get(dt, [])
        if not samples:
            check(f"DT={dt} 有样本", False)
            continue
        ok_proto = ok_dt = ok_summary = ok_wrap = 0
        for hex_str in samples:
            proto, summary, parsed = w._parse_and_summarize(bytes.fromhex(hex_str))
            if proto == "HDC 1.0":
                ok_proto += 1
            if any(
                str(r[0]) == "定界符类型(DT)" and str(r[2]) == str(dt)
                for r in parsed
            ):
                ok_dt += 1
            if DT_NAMES[dt] in summary:
                ok_summary += 1
            if "国网HDC" in summary:
                ok_wrap += 1
        n = len(samples)
        check(f"DT={dt} {DT_NAMES[dt]}: 协议名 HDC 1.0 ({ok_proto}/{n})",
              ok_proto == n)
        check(f"DT={dt} {DT_NAMES[dt]}: 解出定界符类型(DT) ({ok_dt}/{n})",
              ok_dt == n)
        check(f"DT={dt} {DT_NAMES[dt]}: 摘要含帧类型名 ({ok_summary}/{n})",
              ok_summary == n)
        check(f"DT={dt} {DT_NAMES[dt]}: 摘要含国网HDC包装头 ({ok_wrap}/{n})",
              ok_wrap == n)

    # MAC（应用层）帧
    proto, summary, parsed = w._parse_and_summarize(wrap_ed_gx(HDC10_MAC))
    labels = [str(r[0]) for r in parsed]
    all_txt = " ".join(str(x) for r in parsed for x in r[:4])
    print(f"  应用层MAC: 协议={proto} 摘要={summary}")
    check("应用层MAC: 协议名 HDC 1.0", proto == "HDC 1.0", proto)
    check("应用层MAC: 含国网HDC包装头",
          any("国网HDC监控包装头" in x for x in labels), str(labels[:3]))
    check("应用层MAC: 解析到 MAC/MSDU 层",
          any(("MSDU" in x or "MMTYPE" in x or "版本" in x) for x in labels),
          str(labels[:12]))
    check("应用层MAC: 摘要含 MMTYPE",
          "MMTYPE" in summary, summary)
    check("应用层MAC: 无广西台体文案", "广西台体" not in all_txt)

    # ── [3] 自动识别：四类帧控制帧归 HDC 1.0 ───────────────────
    section("[3] 自动识别：四类帧控制帧必须归 HDC 1.0（原先全判南网新一代）")
    select(w, "自动识别")
    misrouted = {}
    for dt, hex_str in FRAMES:
        frame = bytes.fromhex(hex_str)
        if not hdc_fc_evidence(frame):
            misrouted.setdefault(dt, []).append(("无证据", hex_str[:24]))
            continue
        proto, summary, _parsed = w._parse_and_summarize(frame)
        if proto != "HDC 1.0":
            misrouted.setdefault(dt, []).append((proto, summary[:40]))
    check("全部真实帧自动识别为 HDC 1.0", not misrouted,
          str({k: v[:2] for k, v in misrouted.items()}))

    # ── [4] 回归：南网新一代 / 协议10 不得被重排 ────────────────
    section("[4] 回归锚点：南网新一代与协议10 帧不得被判成 HDC 1.0")
    for name, biz in CSG_FRAMES.items():
        frame = wrap_ed_plc2(biz)
        check(f"南网[{name}] 无国网 FC 证据", not hdc_fc_evidence(frame))
        proto, summary, _parsed = w._parse_and_summarize(frame)
        check(f"南网[{name}] 自动识别仍为南网新一代", proto == "南网新一代",
              f"{proto} | {summary[:40]}")

    gw_frame = wrap_ed_gx(GW_REAL)
    check("协议10 真实帧无国网 FC 证据", not hdc_fc_evidence(gw_frame))
    proto, _summary, _parsed = w._parse_and_summarize(gw_frame)
    check("协议10 真实帧自动识别不判为 HDC 1.0", proto != "HDC 1.0", proto)

    # ── [5] 边界帧：plc2 误判触发条件 ──────────────────────────
    section("[5] 边界帧：触发 batch_core 打分误判的 SACK/网间协调")
    # 触发条件：DT∈{2,3} 且 NID 最低字节低 4 位 ∈{0,1}
    adversarial = {
        "SACK(DT=2,NID低=0x00)": build_fc(
            2, bytes([0x10, 0x02, 0x01, 0x00, 0x02, 0x50, 0x80, 0x00]), 0x00
        ),
        "网间协调(DT=3,NID低=0x00)": build_fc(
            3, bytes([0x0E, 0x01, 0x3C, 0x00, 0x01, 0x02, 0x03, 0x05]), 0x00
        ),
        "SOF(DT=1,NID低=0x10)": build_fc(
            1, bytes([0x02, 0xF0, 0xFF, 0x00, 0x10, 0x00, 0x42, 0x00]), 0x10
        ),
    }
    for name, biz in adversarial.items():
        frame = wrap_ed_gx(biz)
        dt = biz[0] & 0x07
        check(f"{name}: FCCS 判据成立", looks_like_hdc_fc(biz))
        check(f"{name}: 证据判为 gx", evidenced_ed_wrapper(frame, 11) == "gx",
              f"batch_core={resolve_ed_wrapper(frame, 'auto', protocol_index=11)!r}")
        select(w, "HDC 1.0")
        proto, summary, parsed = w._parse_and_summarize(frame)
        print(f"    {name}: 协议={proto} 摘要={summary}")
        check(f"{name}: 协议名 HDC 1.0", proto == "HDC 1.0", proto)
        check(f"{name}: 摘要含 {DT_NAMES[dt]}", DT_NAMES[dt] in summary, summary)
        check(f"{name}: 未降级为应用层垃圾解析",
              "原始数据" not in summary and "报文:" not in summary, summary)

    # 记录（**不作断言**）：batch_core 打分在该 SACK 帧上会选错 plc2 —— 这是本次
    # 改动的动因。故意不断言它：若有人按正路修好 batch_core.resolve_ed_wrapper，
    # 断言会失败，等于给正确的修复上锁。这里只记录现状。
    sack_adv = wrap_ed_gx(adversarial["SACK(DT=2,NID低=0x00)"])
    print(
        "    （现状记录：batch_core.resolve_ed_wrapper 对该 SACK 帧判 "
        f"{resolve_ed_wrapper(sack_adv, 'auto', protocol_index=11)!r}，"
        "本次修复不依赖该结果）"
    )

    # ── [6] 已声明的自动识别边界 + _fallback_summary 字段名兼容 ──
    section("[6] 自动识别边界（已声明）与 _fallback_summary 兼容")
    select(w, "自动识别")
    proto, summary, _parsed = w._parse_and_summarize(wrap_ed_gx(HDC10_MAC))
    print(f"    自动识别下的 HDC MAC 帧 = {proto} | {summary[:40]}")
    # 自动识别只按 CRC-24 自证的**帧控制**证据重排（信标/SOF/SACK/网间协调）。
    # MAC/应用层帧没有 FC 可自证，且「像 HDC MAC 帧」的结构启发式已被实证会
    # 误伤南网新一代帧（见 tcp_monitor.hdc_fc_evidence docstring），故不在自动
    # 识别覆盖范围内，需显式选「HDC 1.0」。此处钉住该**已声明边界**，避免
    # 「自动识别已支持应用层」被误当成既成事实。
    check("自动识别不覆盖 MAC/应用层帧（边界已声明）", proto != "HDC 1.0", proto)
    select(w, "HDC 1.0")
    proto2, _s2, _p2 = w._parse_and_summarize(wrap_ed_gx(HDC10_MAC))
    check("显式选 HDC 1.0 后 MAC 帧正确", proto2 == "HDC 1.0", proto2)

    # _fallback_summary：summary_fn 缺失/抛异常时的兜底路径（现场会被走到）。
    # 协议11 字段名为「定界符类型(DT)」且 comment 无冒号；协议10 为「定界符类型」
    # 且 comment 形如 "DT=1: SOF帧" —— 两种都要认，否则协议11 摘要只剩 "-"。
    fb11 = w._fallback_summary([
        ("定界符类型(DT)", "0b010", "2", "选择确认帧(SACK)", 0, 0),
        ("网络标识(NID)", "00 00 01", "65536", "网络标识: 65536", 1, 3),
    ])
    check("_fallback_summary 认协议11 的「定界符类型(DT)」",
          "选择确认帧(SACK)" in fb11, fb11)
    fb10 = w._fallback_summary([
        ("  定界符类型", "0x01 D[2:0]=001", "1 (SOF帧)", "DT=1: SOF帧", 0, 1),
    ])
    check("_fallback_summary 认协议10 字段名并去掉 'DT=n: ' 前缀",
          fb10 == "SOF帧", fb10)

    w.close()
    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    for n in FAILED:
        print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    # Qt offscreen 在解释器收尾阶段会崩（0xC0000409），使进程退出码非零、
    # 被 release_check 误判为失败（测试自身断言其实全过）。打印后直接交出退出码。
    _code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_code)
