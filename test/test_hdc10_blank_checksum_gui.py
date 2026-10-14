# -*- coding: utf-8 -*-
"""协议11「填充CRC-24」按协议门控 GUI 回归（offscreen）

复现用户场景：协议选 [11] HDC 1.0，输入台体日志帧（FCCS/PBCS 留空为全 0），
点「填充CRC-24」。修复前 eFC 分支**没有协议门控**——`byte0&7==1` 且
`byte19 bit0==1` 即命中，把 `crc24(字节16-28)` 写进**字节 29-31**，
而协议11（HDC 1.0）的 FC 之后直接是物理块，字节 29-31 落在 MAC 帧头里
（实测「组网序列号」由 0x01 被改成 0xE1）——静默改坏业务字段。

覆盖：
  1. 协议11 下 eFC/PBCS 被门控跳过，字节 29-31 与重解析结果均不被改动
  2. FCCS(字节13-15) 仍对所有协议生效（协议11 也应能补上 FCCS）
  3. 协议9（南网新一代）PBCS 一键回填不受影响
  4. 协议11 + 级别「FC+PB解析(完整MPDU)」走界面 parse_single 能读出业务内容
"""

import _path_setup  # noqa: E402,F401

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPORTED_HEX = """
01 00 00 00 00 F0 FF FE 63 11 26 42 00 00 00 00
C0 00 00 FF 1F 00 01 00 30 08 00 FF 00 00 01 00
00 11 06 00 00 01 61 10 00 C5 0F 88 0D
"""
REPORTED = bytes.fromhex("".join(REPORTED_HEX.split())) + bytes(152 - 45)

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


def input_bytes(win):
    return bytes.fromhex(win.single_input.toPlainText().replace(" ", ""))


def find(rows, name):
    for r in rows:
        if str(r[0]).strip() == name:
            return r
    return None


def raw(rows, name):
    r = find(rows, name)
    return None if r is None else str(r[1])


def norm(name):
    """去掉 GUI 表格字段列的树形前缀（`  └ ` 之类）与首尾空白。"""
    import re
    return re.sub(r"^[\s\u2514\u251c\u2502\u2500\u2003]+", "", name).strip()


def table_rows(win):
    """返回 [(规范化字段名, 原始值, 解析值)]。"""
    t = win.result_table_widget
    return [(norm(str(t.item(i, 0).text()) if t.item(i, 0) else ""),
             str(t.item(i, 1).text()) if t.item(i, 1) else "",
             str(t.item(i, 2).text()) if t.item(i, 2) else "")
            for i in range(t.rowCount())]


def main():
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])

    msgs = []
    QMessageBox.information = staticmethod(
        lambda parent, title, text, *a, **k: msgs.append(text))
    QMessageBox.warning = staticmethod(
        lambda parent, title, text, *a, **k: msgs.append(text))

    import main_gui
    from csg_new_gen_parser import _crc24_func
    from hdc10_parser import HDC10Parser
    from test_csg_pb_size_pbcs import REAL_FRAME_HEX

    # 前置条件：该帧确实会命中旧 eFC 分支（DT=1 且 byte19 bit0=1）
    check("报障帧命中旧 eFC 分支前置条件（DT=1 且 byte19 bit0=1）",
          (REPORTED[0] & 0x07) == 1 and (REPORTED[19] & 0x01) == 1,
          f"byte0=0x{REPORTED[0]:02X} byte19=0x{REPORTED[19]:02X}")
    efc = _crc24_func(bytes(REPORTED[16:29]))
    check("旧代码会写入的 eFC 值非 0（确有改坏字节29-31 的风险）", efc != 0)
    check("旧代码写入值与字节29-31 原值不同（该断言能真正抓到回归）",
          efc.to_bytes(3, "little") != REPORTED[29:32],
          f"eFC=0x{efc:06X} 原值={REPORTED[29:32].hex(' ')}")

    win = main_gui.MainWindow()
    win.current_protocol = 11

    # ── [1] 协议11：「填充CRC-24」不得写坏 MAC 帧头 ─────────────
    win.single_input.setPlainText(" ".join(f"{b:02X}" for b in REPORTED))
    before = input_bytes(win)
    msgs.clear()
    win._fill_crc24()
    app.processEvents()
    filled_text = "\n".join(msgs)
    after = input_bytes(win)

    check("提示明确 eFC/PBCS 未填充（并说明仅协议9 适用）",
          "eFC/PBCS: 未填充" in filled_text and "协议11" in filled_text,
          filled_text[:200])
    check("字节 29-31 未被写入（MAC 帧头不被改坏）",
          after[29:32] == before[29:32],
          f"{before[29:32].hex(' ')} -> {after[29:32].hex(' ')}")
    check("组网序列号重解析仍为 0x01（旧代码会变 0xE1）",
          raw(HDC10Parser().parse_to_table(after, "fc_pb"), "组网序列号")
          == "0x01",
          str(raw(HDC10Parser().parse_to_table(after, "fc_pb"), "组网序列号")))
    check("FCCS(字节13-15) 已按 CRC-24 小端写入",
          after[13:16] == _crc24_func(before[:13]).to_bytes(3, "little"),
          after[13:16].hex(" "))
    check("填充后 FCCS 行显示校验正确（两处 CRC-24 实现同源）",
          "✓ 校验正确" in str(
              find(HDC10Parser().parse_to_table(after, "fc_pb"),
                   "帧控制校验序列(FCCS)")[3]))
    check("除 13-15 外其余字节未被改动",
          after[:13] == before[:13] and after[16:] == before[16:])
    check("不再追加 PBCS 回填项（协议11 无逐物理块 PBCS 布局）",
          "PBCS[" not in filled_text, filled_text[:200])
    check("提示列出 FC FCS 填充项", "FC FCS=0xB3A813" in filled_text,
          filled_text[:200])

    # ── [2] 协议9：PBCS 一键回填不受影响 ───────────────────────
    csg_frame = bytes.fromhex("".join(REAL_FRAME_HEX.split()))
    win.current_protocol = 9
    win.single_input.setPlainText(" ".join(f"{b:02X}" for b in csg_frame))
    msgs.clear()
    win._fill_crc24()
    app.processEvents()
    csg_text = "\n".join(msgs)
    csg_after = input_bytes(win)
    check("协议9 提示含 4 个 PBCS 填充项",
          all(f"PBCS[{i}]=" in csg_text for i in range(4)), csg_text[:300])
    offs = (533, 1053, 1573, 2093)
    check("协议9 四个 PBCS 位点均已写入非 0 值",
          all(int.from_bytes(csg_after[o:o + 3], "little") != 0 for o in offs),
          str([csg_after[o:o + 3].hex(" ") for o in offs]))
    check("协议9 未出现 eFC/PBCS 跳过提示", "eFC/PBCS: 未填充" not in csg_text)

    # ── [3] 协议11 走界面 parse_single（级别「FC+PB解析(完整MPDU)」）──
    win.current_protocol = 11
    idx = win.gw_parse_level_combo.findData("fc_pb")
    win.gw_parse_level_combo.setCurrentIndex(idx)
    app.processEvents()
    check("解析级别已切到 fc_pb（协议11 存于 _hdc10_parse_level）",
          win._hdc10_parse_level == "fc_pb", str(win._hdc10_parse_level))
    win.single_input.setPlainText(" ".join(f"{b:02X}" for b in REPORTED))
    win.parse_single()
    app.processEvents()
    rows = table_rows(win)
    names = [n for n, _r, _v in rows]
    check("界面解析未失败", not any(n.startswith("❌") for n in names),
          str([n for n in names if n.startswith("❌")]))
    check("界面按完整 MPDU 解析（含 DT 与 FCCS 行）",
          "定界符类型(DT)" in names and "帧控制校验序列(FCCS)" in names)
    cells = {n: (r, v) for n, r, v in rows}
    check("界面读出业务内容（报文端口号 0x11 / 报文ID 0x0006）",
          "0x11" in cells.get("报文端口号", ("", ""))
          and "0x0006" in cells.get("报文ID", ("", "")),
          f"{cells.get('报文端口号')} {cells.get('报文ID')}")
    check("界面标注 ⚠ FCCS 未通过（留空不误报为校验失败）",
          "⚠ FCCS 未通过" in names)
    check("界面标注 ⚠ PBCS未填充", "⚠ PBCS未填充" in names, str(names[-6:]))

    print("\n" + "=" * 58)
    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} 项失败: {FAILURES}")
        sys.stdout.flush()   # os._exit 不冲刷缓冲区，不冲会丢掉失败明细
        os._exit(1)
    print(f"[OK] 全部 {PASS} 项检查通过")
    # Qt offscreen 退出析构可能原生崩溃（与结论无关），显式退出避免污染退出码
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
