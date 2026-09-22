"""原始 TCP 载荷的协议识别与「原始数据」兜底回归测试（R2 / R3）。

覆盖：
  [1] 自动识别命中**可自证**形态：DLMS Wrapper / DLMS-APDU 裸报文 / DLT645-2007 / 698.45
  [2] 兜底：未识别载荷 → 协议列「原始数据」、摘要含长度、解析行 >= 3（AC3.1/AC3.2）
  [3] APDU 标签提示：首字节命中 698.45 / DLMS 标签表时给出「疑似 … APDU: …」
  [4] 任意二进制（非 ASCII / 0x00 / 0xED）不抛异常（AC3.3）
  [5] 显式选择优先；显式选择下解析失败要如实说明而不是瞎猜
  [6] 已声明边界：南网/国网 不参与自动识别（错解析比不解析更糟）
  [7] 反例自检：破坏 CRC 的 698.45 帧不得被判成 698.45；非 645 帧不得被判成 645

样本来源：仓库既有测试与协议注册表 placeholder（见各常量注释），非凭空构造。

运行: QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_proto_detect.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

_config_sandbox.install()

from monitor.tcp_monitor import TCPMonitorWidget  # noqa: E402

PASS = 0
FAIL = 0

# 南网协议 placeholder（protocol_registry 协议0）
NW_FRAME = bytes.fromhex("680E000000000100 01E80005EF16".replace(" ", ""))
# 国网协议 placeholder（protocol_registry 协议7，CS 按校验器算法修正为 0x47）
GDW_FRAME = bytes.fromhex("680F004300000000000000000000030100 47 16".replace(" ", ""))
# 698.45（test/test_dl_t698_45.py:15，HCS/FCS 双通过）
D698_FRAME = bytes.fromhex("680E00410107080988030100000000 348716".replace(" ", ""))
# DLT645-2007（protocol_registry 协议6 placeholder，CS=0xAD 经校验器验证通过）
D645_FRAME = bytes.fromhex("68AAAAAAAAAAAA 68 11 04 33333333 AD 16".replace(" ", ""))
# DLMS Wrapper（test/test_dlms.py:11 用户提供样本）
WRAPPER_FRAME = bytes.fromhex(
    "000100010066003ADB0857534766713466132F3000000001F6B4630154326C0253D44DB170"
    "20D3A4C52FD669E3E39C8B0EE836B4F19A3ADF7E11B4FD7B92211C842E"
)
# DLMS-APDU 裸报文（protocol_registry 协议5 placeholder 形态）
APDU_FRAME = bytes.fromhex("C001C1000100000001 00".replace(" ", ""))


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n{title}")


def select(w, target):
    """选中协议下拉项；``target`` 可以是协议索引（``None`` = 自动识别）或协议显示名。

    下拉里还没有该项时补一项（B7 之前下拉只有 4 项，而原始载荷路径本身按
    itemData 的协议索引工作）；AC2.1「下拉含全协议」由 B7 的 UI 测试单独覆盖。
    """
    import protocol_registry as pr

    if target is None:
        label, data = "自动识别", None
    elif isinstance(target, int):
        label, data = pr.get_protocol(target).short_name, target
    else:
        label, data = str(target), None
        for spec in pr._PROTOS:
            if target in (spec.short_name, spec.name) or target in tuple(spec.aliases):
                data = spec.index
                break
    idx = w.proto_combo.findText(label)
    if idx < 0:
        w.proto_combo.addItem(label, data)
        idx = w.proto_combo.findText(label)
    w.proto_combo.setCurrentIndex(idx)
    assert w._selected_protocol_index() == data, (
        f"下拉选择未生效：{label} → {w._selected_protocol_index()}（期望 {data}）"
    )


def main():
    print("=" * 64)
    print("TCP 原始载荷协议识别与兜底（B3 / R2 / R3）")
    print("=" * 64)
    QApplication.instance() or QApplication([])
    w = TCPMonitorWidget()
    select(w, "自动识别")

    section("[1] 自动识别命中可自证形态")
    for label, frame in (
        ("DLMS Wrapper", WRAPPER_FRAME),
        ("DLMS-APDU", APDU_FRAME),
        ("DLT645-2007", D645_FRAME),
        ("698.45", D698_FRAME),
    ):
        proto, summary, rows = w._parse_and_summarize(frame)
        check(
            f"{label}：识别为 {label}",
            proto == label,
            f"实际 {proto} | {summary[:40]}",
        )
        check(f"{label}：解析行非空（>=2）", len(rows) >= 2, str(len(rows)))
        check(f"{label}：摘要非空且非 '-'", bool(summary) and summary != "-", summary[:40])

    section("[2] 未识别载荷 → 原始数据兜底（AC3.1/AC3.2）")
    junk = bytes.fromhex("DEADBEEF00112233445566778899AABB")
    proto, summary, rows = w._parse_and_summarize(junk)
    check("协议列 = 原始数据", proto == "原始数据", proto)
    check("摘要含载荷长度", f"{len(junk)} 字节" in summary, summary)
    check("解析行 >= 3", len(rows) >= 3, str(len(rows)))
    check("含「TCP 载荷」行", any("TCP 载荷" in str(r[0]) for r in rows),
          str([str(r[0]) for r in rows]))
    check("含「首字节」行", any("首字节" in str(r[0]) for r in rows))
    check("含原始数据行且带完整字节指引",
          any("原始数据" in str(r[0]) and "原始报文" in str(r[3]) for r in rows))

    section("[3] APDU 标签提示")
    proto, summary, rows = w._parse_and_summarize(b"\xC0")
    check("单字节 0xC0：兜底为原始数据", proto == "原始数据", proto)
    check("摘要给出疑似 DLMS APDU", "疑似 DLMS APDU" in summary, summary)
    proto, summary, rows = w._parse_and_summarize(b"\x01")
    check("单字节 0x01：摘要给出疑似 698.45 APDU",
          "疑似 698.45 APDU" in summary, summary)

    section("[4] 任意二进制不抛异常（AC3.3）")
    for name, payload in (
        ("含 0x00", b"\x00" * 8),
        ("含 0xED", b"\xED\x00\xED\xED\x00"),
        ("非 ASCII", bytes(range(0x80, 0x90))),
        ("超长 4KB", bytes(range(256)) * 16),
        ("空", b""),
    ):
        try:
            proto, summary, rows = w._parse_and_summarize(payload)
            ok = bool(proto) and bool(summary)
        except Exception as e:
            ok = False
            summary = f"{type(e).__name__}: {e}"
        check(f"{name} 载荷不抛异常且给出结果", ok, str(summary)[:50])

    section("[5] 显式选择优先 / 失败如实说明")
    select(w, "DLT645-2007")
    proto, _s, _r = w._parse_and_summarize(D645_FRAME)
    check("显式 645：645 帧识别为 DLT645-2007", proto == "DLT645-2007", proto)
    select(w, "698.45协议")
    proto, _s, _r = w._parse_and_summarize(D698_FRAME)
    check("显式 698.45：698.45 帧识别为 698.45", proto == "698.45", proto)
    proto, summary, rows = w._parse_and_summarize(b"\xff\xff\xff\xff")
    check("显式选择下无法解析 → 原始数据 + 如实说明",
          proto == "原始数据" and "未匹配" in summary,
          f"{proto} | {summary}")

    section("[6] 已声明边界：南网/国网 不参与自动识别")
    select(w, "自动识别")
    for label, frame in (("南网", NW_FRAME), ("国网", GDW_FRAME)):
        proto, summary, rows = w._parse_and_summarize(frame)
        print(f"    {label} 帧自动识别结果 = {proto} | {summary[:50]}")
        check(
            f"{label} 帧不被错解析成其他协议（边界：需显式选择）",
            proto == "原始数据",
            proto,
        )
    # 显式选择后能正确解析（证明不是解析能力缺失，只是不自动判）
    select(w, "南网协议")
    proto, _s, _r = w._parse_and_summarize(NW_FRAME)
    check("显式选南网后可解析", proto == "南网协议", proto)
    select(w, "国网协议")
    proto, _s, _r = w._parse_and_summarize(GDW_FRAME)
    check("显式选国网后可解析", proto == "国网协议", proto)

    section("[7] 反例自检：判据有效")
    # 破坏 698.45 的一个数据字节 → HCS/FCS 必然不通过 → 不得判成 698.45
    broken = bytearray(D698_FRAME)
    broken[10] ^= 0xFF
    select(w, "自动识别")
    proto, summary, _rows = w._parse_and_summarize(bytes(broken))
    check("CRC 被破坏的 698.45 帧不被判成 698.45（判据有效）",
          proto != "698.45", f"{proto} | {summary[:40]}")
    # 非 645 帧不得被判成 645（结构前置检查有效）
    proto, _s, _r = w._parse_and_summarize(NW_FRAME)
    check("南网帧不被判成 DLT645-2007", proto != "DLT645-2007", proto)
    # 非 Wrapper 帧不得被判成 Wrapper
    proto, _s, _r = w._parse_and_summarize(D645_FRAME)
    check("645 帧不被判成 DLMS Wrapper", proto != "DLMS Wrapper", proto)

    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）✓")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
