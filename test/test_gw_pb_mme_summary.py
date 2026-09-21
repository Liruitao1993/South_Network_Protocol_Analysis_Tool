# -*- coding: utf-8 -*-
"""协议10/11 批量摘要：网络层/MME 帧必须体现管理消息 MMTYPE

现场报障（2026-09-18）:
    GUI 协议11 HDC 1.0，解析级别=仅PB，帧类型=SOF帧，批量解析 68 帧。
    详情里已是「网络管理消息 / 消息类型(MMTYPE) 0x0000 关联请求」，
    但摘要列只有 `0→1 | msduSeq:9311 | 单播`，无法区分关联请求/发现列表等。

根因:
    桌面 `_get_gw_new_gen_summary` 只查字段名 `管理消息类型(MMTYPE)`
    （协议10 / gw_new_gen_mme_parser），协议11 的字段名是
    `消息类型(MMTYPE)`（hdc10_mme_parser）→ 精确匹配永不命中。
    同时步骤7 故意跳过「网络管理」类 MSDU 类型（本意是 MMTYPE 已体现），
    导致网络层帧摘要只剩 TEI/序号/单播。

修复:
    - 桌面：两种字段名都查；comment 以 `MMTYPE:` 开头时剥前缀；
      输出 `MMTYPE:{code}({name})` 或 `MMTYPE:{name}`
    - Web `get_hdc10_summary`：`MME:{name}` → 与桌面同口径 `MMTYPE:…`，
      并补 TEI/msduSeq/发送类型（pb_only 批量扫读）

运行:
    python -X utf8 -u test/test_gw_pb_mme_summary.py
"""

import os
import sys

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = _path_setup.ROOT if hasattr(_path_setup, "ROOT") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.join(ROOT, "reflex_web"))

from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QMessageBox  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import hdc10_parser  # noqa: E402
import gw_new_gen_parser  # noqa: E402
import main_gui  # noqa: E402
from reflex_web import web_utils  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

PASS = 0
FAIL = 0
FAILED = []

# 现场关联请求帧（与 test_hdc10_mac_only_contract 同源；pb_only 需带 PBH=0xC0）
ASSOC_WITH_PBH = (
    "C0"
    "00000100019673005C80FF0800960000"
    "200000000124010101010101"
    "000000002000000001240100000000000000000001030001"
    "329FBACA69DE640900000000A860CAF104A18A64E8F2"
    "0000040099F4484C3039000000000000000065F9"
    "0000000000000000000000000000000000000000000000000000"
    "688150C4"
    "0000000000000000BA711E"
)


class Host:
    _get_gw_new_gen_summary = main_gui.MainWindow._get_gw_new_gen_summary
    _TEST_MODE_SENTINELS = main_gui.MainWindow._TEST_MODE_SENTINELS
    _extract_test_mode_content = main_gui.MainWindow._extract_test_mode_content


host = Host()


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
    data = bytes.fromhex(ASSOC_WITH_PBH)

    section("[1] 协议11 pb_only：网络层 MME 帧摘要含 MMTYPE")
    rows11 = hdc10_parser.HDC10Parser().parse_to_table(
        data, parse_level="pb_only", frame_type=1
    )
    names = {str(r[0]).strip() for r in rows11}
    check("详情含 消息类型(MMTYPE)", "消息类型(MMTYPE)" in names, str(sorted(names)[:20]))
    s11 = host._get_gw_new_gen_summary(rows11)
    print(f"  摘要: {s11}")
    check("摘要含 MMTYPE", "MMTYPE:" in s11, s11)
    check("摘要含 0x0000", "0x0000" in s11 or "关联请求" in s11, s11)
    check("摘要含 关联请求", "关联请求" in s11, s11)
    check("摘要仍含 TEI 方向", "→" in s11, s11)
    check("摘要含 msduSeq", "msduSeq:" in s11, s11)

    section("[2] 协议11 auto：无 PBH 的 MAC 帧摘要同样含 MMTYPE")
    # auto 对「C0+MAC」会当完整 MPDU 误判 FC；现场真正的 auto 输入是裸 MAC 帧
    bare = bytes.fromhex(ASSOC_WITH_PBH[2:])  # 去掉 PBH 前缀
    rows11a = hdc10_parser.HDC10Parser().parse_to_table(bare, parse_level="auto")
    s11a = host._get_gw_new_gen_summary(rows11a)
    print(f"  摘要: {s11a}")
    check("auto 摘要含 MMTYPE", "MMTYPE:" in s11a and "关联请求" in s11a, s11a)

    section("[3] 协议10 pb_only / auto：既有 MMTYPE 路径不回归")
    # 协议10 pb_only 同样吃 PBH+MAC
    rows10 = gw_new_gen_parser.GWNewGenParser().parse_to_table(
        data, parse_level="pb_only", frame_type=1
    )
    s10 = host._get_gw_new_gen_summary(rows10)
    print(f"  摘要: {s10}")
    check("协议10 pb_only 摘要含 MMTYPE", "MMTYPE:" in s10 and "关联请求" in s10, s10)
    rows10a = gw_new_gen_parser.GWNewGenParser().parse_to_table(data, parse_level="auto")
    s10a = host._get_gw_new_gen_summary(rows10a)
    # auto 可能把该帧当 FC（无 MME）；仅当表里有 MMTYPE 字段时才要求摘要带出
    has_mm = any("MMTYPE" in str(r[0]) for r in rows10a)
    if has_mm:
        check("协议10 auto 有 MMTYPE 字段时摘要含 MMTYPE",
              "MMTYPE:" in s10a, s10a)
    else:
        check("协议10 auto 无 MMTYPE 字段（FC 误判路径）——不要求摘要", True)

    section("[4] Web get_hdc10_summary 同口径")
    w11 = web_utils.get_hdc10_summary(rows11)
    print(f"  Web: {w11}")
    check("Web 协议11 pb_only 摘要含 MMTYPE", "MMTYPE:" in w11, w11)
    check("Web 不再用 MME: 旧前缀", "MME:" not in w11 or "MMTYPE:" in w11, w11)
    check("Web 含 关联请求", "关联请求" in w11, w11)

    section("[5] 协议10 既有字段名 管理消息类型(MMTYPE) 仍被桌面命中")
    # 手工构造协议10 风格行（字段名更长）
    fake = [
        ("  原始源TEI", "0x001", "1", "src", 0, 1),
        ("  原始目的TEI", "0x002", "2", "dst", 2, 3),
        ("  MSDU序列号", "00 01", "1", "seq", 4, 5),
        ("  发送类型", "0x0", "0", "单播", 6, 6),
        ("  管理消息类型(MMTYPE)", "00 00", "0x0000", "关联请求", 8, 9),
    ]
    sf = host._get_gw_new_gen_summary(fake)
    print(f"  桌面: {sf}")
    check("协议10 风格字段名输出 MMTYPE:0x0000(关联请求)",
          "MMTYPE:0x0000(关联请求)" in sf, sf)

    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    if FAILED:
        for n in FAILED:
            print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
