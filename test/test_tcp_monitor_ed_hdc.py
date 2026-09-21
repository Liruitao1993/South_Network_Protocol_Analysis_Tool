# -*- coding: utf-8 -*-
"""TCP 监控：协议11 HDC 1.0 下 ED 封装头 + 业务解析

用户（2026-09-20）:
    完善 TCP 监控：选择国网 HDC 1.0 协议时，需按国网口径解析 ED 头部封装内容，
    并对内容（业务帧）进行解析。

覆盖:
  [1] batch_core.build_ed_header_rows / unwrap_ed_for_parse（协议9 vs 11 文案）
  [2] FlowBuffer 保留完整 ED 帧（不再写死剥 9 字节）
  [3] TCPMonitorWidget：HDC 1.0 下拉；解析结果含 国网HDC包装头 + MAC/MME 字段
  [4] 协议9 同帧仍显示广西台体/PLC2 语境

运行: python -X utf8 -u test/test_tcp_monitor_ed_hdc.py
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
from batch_core import build_ed_header_rows, unwrap_ed_for_parse  # noqa: E402
from gw_new_gen_parser import GWNewGenParser  # noqa: E402
from hdc10_parser import HDC10Parser  # noqa: E402
import main_gui  # noqa: E402
from monitor.tcp_monitor import FlowBuffer, TCPMonitorWidget  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

_config_sandbox.install()

PASS = 0
FAIL = 0
FAILED = []

HDC10_MAC = bytes.fromhex(
    "00000100019673005C80FF0800960000"
    "200000000124010101010101"
    "000000002000000001240100000000000000000001030001"
    "329FBACA69DE640900000000A860CAF104A18A64E8F2"
    "0000040099F4484C3039000000000000000065F9"
    "0000000000000000000000000000000000000000000000000000"
    "688150C40000000000000000BA711E"
)


def make_ed_frame(business: bytes, layout="gx") -> bytes:
    if layout == "gx":
        data域 = (
            (0x11223344).to_bytes(4, "little")
            + bytes([0x01, 0x01])
            + len(business).to_bytes(2, "little")
            + business
        )
    else:
        data域 = (
            bytes([0x01])
            + (0x11223344).to_bytes(4, "little")
            + bytes([0x01, 0x00])
            + len(business).to_bytes(2, "little")
            + business
        )
    body = bytes([0x00, 0x02, 0xEF]) + data域
    frame_len = len(body) + 1
    cs = sum(bytes([0xED]) + frame_len.to_bytes(2, "little") + body) & 0xFF
    return bytes([0xED]) + frame_len.to_bytes(2, "little") + body + bytes([cs, 0xEE])


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


def main():
    ed_gx = make_ed_frame(HDC10_MAC, "gx")

    section("[1] batch_core ED 行：协议11 国网HDC / 协议9 广西台体")
    rows11 = build_ed_header_rows(ed_gx, 11, "gx")
    rows9 = build_ed_header_rows(ed_gx, 9, "gx")
    check("协议11 标题国网HDC", rows11 and "国网HDC" in rows11[0][0], str(rows11[:1]))
    check("协议11 无广西台体", not any("广西" in str(r[0]) + str(r[3]) for r in rows11))
    check("协议9 标题广西台体", rows9 and "广西台体" in rows9[0][0], str(rows9[:1]))
    ed_rows11, biz11 = unwrap_ed_for_parse(ed_gx, 11)
    check("unwrap 协议11 业务非空", bool(biz11) and biz11 == HDC10_MAC,
          f"biz_len={len(biz11)}")
    check("unwrap 协议11 ED 行含国网HDC",
          ed_rows11 and "国网HDC" in ed_rows11[0][0])

    section("[2] FlowBuffer 保留完整 ED 帧")
    buf = FlowBuffer()
    buf.append(ed_gx, 1.0)
    frames = buf.pop_frames()
    check("切出 1 帧", len(frames) == 1, str(len(frames)))
    check("帧内容=完整 ED 帧", frames and frames[0][1] == ed_gx,
          f"len={len(frames[0][1]) if frames else 0} vs {len(ed_gx)}")

    section("[3] TCPMonitorWidget 协议=HDC 1.0")
    w = TCPMonitorWidget()
    # 注入与主窗口一致的摘要
    gw_sum = main_gui.MainWindow._get_gw_new_gen_summary

    class Host:
        _get_gw_new_gen_summary = gw_sum
        _TEST_MODE_SENTINELS = main_gui.MainWindow._TEST_MODE_SENTINELS
        _extract_test_mode_content = staticmethod(
            main_gui.MainWindow._extract_test_mode_content
        )

    host = Host()
    w.set_parsers(
        GWNewGenParser(),
        None,  # 无南网 parser，强制走指定模式
        gw_summary_fn=host._get_gw_new_gen_summary,
        csg_summary_fn=None,
        hdc10_parser=HDC10Parser(),
        hdc10_summary_fn=host._get_gw_new_gen_summary,
    )
    items = [w.proto_combo.itemText(i) for i in range(w.proto_combo.count())]
    check("下拉含 HDC 1.0", "HDC 1.0" in items, str(items))
    idx = w.proto_combo.findText("HDC 1.0")
    w.proto_combo.setCurrentIndex(idx)
    proto_name, summary, parsed = w._parse_and_summarize(ed_gx)
    print(f"  协议={proto_name} 摘要={summary}")
    print(f"  前8字段={[r[0] for r in parsed[:8]]}")
    check("协议名 HDC 1.0", proto_name == "HDC 1.0", proto_name)
    labels = [str(r[0]) for r in parsed]
    all_txt = " ".join(str(x) for r in parsed for x in r[:4])
    check("解析含国网HDC包装头", any("国网HDC监控包装头" in x for x in labels),
          str(labels[:4]))
    check("解析无广西台体", "广西台体" not in all_txt)
    check("解析含业务字段(MSDU/MMTYPE/关联)",
          any(("MSDU" in x or "MMTYPE" in x or "消息类型" in x or "关联" in x)
              for x in labels),
          str(labels[:20]))
    check("摘要含国网HDC或关联请求",
          "国网HDC" in summary or "关联请求" in summary or "MMTYPE" in summary,
          summary)

    section("[4] TCPMonitorWidget 协议=南网新一代：同帧文案不同")
    # 注入南网 parser
    try:
        from csg_new_gen_parser import CSGNewGenParser
        csg = CSGNewGenParser()
    except Exception as e:
        check("导入 CSGNewGenParser", False, str(e))
        csg = None
    if csg is not None:
        w.set_parsers(
            GWNewGenParser(),
            csg,
            gw_summary_fn=host._get_gw_new_gen_summary,
            csg_summary_fn=main_gui.MainWindow._get_csg_new_gen_summary,
            hdc10_parser=HDC10Parser(),
            hdc10_summary_fn=host._get_gw_new_gen_summary,
        )
        w.proto_combo.setCurrentIndex(w.proto_combo.findText("南网新一代"))
        proto9, summary9, parsed9 = w._parse_and_summarize(ed_gx)
        print(f"  协议={proto9} 摘要={summary9[:80]}")
        all9 = " ".join(str(x) for r in parsed9 for x in r[:4])
        check("协议名 南网新一代", proto9 == "南网新一代", proto9)
        check("协议9 路径文案为广西台体/PLC2 而非强制HDC",
              "广西台体" in all9 or "PLC2.0" in all9 or "国网HDC" not in all9,
              [str(r[0]) for r in parsed9[:3]])

    w.close()
    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    if FAILED:
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
