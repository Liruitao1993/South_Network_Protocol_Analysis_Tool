# -*- coding: utf-8 -*-
"""协议9「填充CRC-24」按钮 PBCS 一键回填 GUI 回归测试（offscreen）

复现用户场景：输入 4×520 物理块、PBCS 全零的抓包帧，点击「填充CRC-24」，
4 个物理块的 PBCS 必须被重算写回，重解析后 4 行均「校验通过」。

覆盖：
  1. _fill_crc24 对多 PB 帧逐块回填 PBCS（偏移/值与解析器计划一致）
  2. 回填后输入框 hex 更新，parse_single 重解析 4 行 PBCS 校验通过
  3. 提示消息列出每个 PBCS 填充项；信标帧输入时给出「未填充」说明
"""

import _path_setup  # noqa: E402

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


def main():
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])

    msgs = []
    QMessageBox.information = staticmethod(
        lambda parent, title, text, *a, **k: msgs.append(text))
    QMessageBox.warning = staticmethod(
        lambda parent, title, text, *a, **k: msgs.append(text))

    import main_gui
    from test_csg_pb_size_pbcs import REAL_FRAME_HEX, _bplc_sof_fc, _pb

    frame = bytes.fromhex("".join(REAL_FRAME_HEX.split()))
    win = main_gui.MainWindow()
    win.current_protocol = 9
    win.single_input.setPlainText(" ".join(f"{b:02X}" for b in frame))

    win._fill_crc24()
    app.processEvents()
    filled_text = "\n".join(msgs)
    for idx, val in enumerate((0xE8976A, 0xC178D2, 0x8C0F7E, 0x1512FB)):
        check(f"提示含 PBCS[{idx}] 填充项",
              f"PBCS[{idx}]=0x{val:06X}" in filled_text, filled_text[:200])

    new_bytes = bytes.fromhex(win.single_input.toPlainText().replace(" ", ""))
    expect = [(533, 0xE8976A), (1053, 0xC178D2), (1573, 0x8C0F7E), (2093, 0x1512FB)]
    for off, val in expect:
        got = int.from_bytes(new_bytes[off:off + 3], "little")
        check(f"输入框字节{off}-{off + 2} 已写回 0x{val:06X}", got == val,
              f"实际 0x{got:06X}")
    check("FC FCS 未被破坏", new_bytes[13:16] == frame[13:16])

    win.parse_single()
    app.processEvents()
    table = win.result_table_widget
    names = [str(table.item(r, 0).text()) if table.item(r, 0) else ""
             for r in range(table.rowCount())]
    pbcs_rows = [r for r, n in enumerate(names) if "物理块检查序列" in n]
    ok_cnt = 0
    for r in pbcs_rows:
        if "校验通过" in str(table.item(r, 2).text()):
            ok_cnt += 1
    check("重解析后 4 行 PBCS 均校验通过", ok_cnt == 4, f"通过 {ok_cnt}/4")

    # 信标帧：给出未填充说明，不写坏字节
    msgs.clear()
    beacon = bytearray(_bplc_sof_fc(pb_count=1, cmt_index=4))
    beacon[0] = (beacon[0] & 0xF8)  # 定界符=0 信标
    beacon += _pb(0, 136)
    win.single_input.setPlainText(" ".join(f"{b:02X}" for b in bytes(beacon)))
    before = win.single_input.toPlainText()
    win._fill_crc24()
    app.processEvents()
    check("信标帧提示 PBCS 未填充", any("PBCS: 未填充" in m for m in msgs),
          "\n".join(msgs)[:200])
    check("信标帧 PB 字节未被改动",
          win.single_input.toPlainText().replace(" ", "")[32:]
          == before.replace(" ", "")[32:])

    print("=" * 50)
    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} 项失败: {FAILURES}")
        os._exit(1)
    print(f"[OK] 全部 {PASS} 项检查通过")
    # Qt offscreen 在解释器退出析构时可能原生崩溃(与测试结论无关)，显式退出避免污染退出码
    os._exit(0)


if __name__ == "__main__":
    main()
