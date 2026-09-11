# -*- coding: utf-8 -*-
"""协议9 单帧解析「选中行→输入框字节高亮」GUI 回归测试（offscreen）

复现用户场景：2096 字节 4-PB 帧解析后，选中「物理块检查序列[i]」行，
输入框必须高亮到该 PB 末尾 3 字节 PBCS 的对应报文位置。

覆盖：
  1. 走真实链路 parse_single() → 表格填充 → setCurrentCell 触发 currentCellChanged
  2. 4 行 PBCS 高亮字符格式落在 _byte_ranges 声明的字节上（黄色 #ffeb3b）
  3. 输入框可视区同步滚动到高亮位置（textCursor 落在高亮区间内）——
     长报文换行后靠后字节的高亮否则在滚动区外不可见
  4. 对照：FC 校验序列行高亮同样生效
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


def _bg_at(win, pos):
    from PySide6.QtGui import QTextCursor
    cur = QTextCursor(win.single_input.document())
    cur.setPosition(pos)
    br = cur.charFormat().background()
    return br.color().name() if br.style() != 0 else "NoBrush"


def main():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    import main_gui
    from test_csg_pb_size_pbcs import REAL_FRAME_HEX

    frame = bytes.fromhex("".join(REAL_FRAME_HEX.split()))
    win = main_gui.MainWindow()
    win.current_protocol = 9
    # 模拟用户粘贴：带换行的原始 hex（parse_single 会规范化为单行并重建表格）
    win.single_input.setPlainText(
        " ".join(f"{b:02X}" for b in frame[:1048]) + "\n"
        + " ".join(f"{b:02X}" for b in frame[1048:])
    )
    win.parse_single()
    app.processEvents()

    table = win.result_table_widget
    names = [
        str(table.item(r, 0).text()) if table.item(r, 0) else ""
        for r in range(table.rowCount())
    ]
    pbcs_rows = [r for r, n in enumerate(names) if "物理块检查序列" in n]
    check("表格含 4 行物理块检查序列", len(pbcs_rows) == 4, f"实际 {len(pbcs_rows)}")
    check("输入框已规范化为单行 hex",
          "\n" not in win.single_input.toPlainText())

    hex_display = win.single_input.toPlainText()
    for i, row in enumerate(pbcs_rows):
        bs, be = win._byte_ranges[row]
        check(f"PBCS[{i}] 行字节范围有效", bs is not None and be >= bs,
              f"range=({bs},{be})")
        win.result_table_widget.setCurrentCell(row, 0)
        app.processEvents()
        check(f"PBCS[{i}] 高亮落在对应报文位置",
              _bg_at(win, bs * 3 + 1) == "#ffeb3b",
              f"range=({bs},{be}) bg={_bg_at(win, bs * 3 + 1)} "
              f"text={hex_display[bs * 3:be * 3 + 3]!r}")
        cur_pos = win.single_input.textCursor().position()
        check(f"PBCS[{i}] 输入框滚动到高亮位置",
              bs * 3 <= cur_pos <= be * 3 + 2,
              f"cursor={cur_pos} 期望区间 [{bs * 3},{be * 3 + 2}]")

    # 对照：FC 校验序列行
    fc_row = [r for r, n in enumerate(names) if n.strip() == "FC校验序列(FCS)"]
    check("表格含 FC校验序列(FCS) 行", len(fc_row) == 1)
    if fc_row:
        row = fc_row[0]
        bs, be = win._byte_ranges[row]
        win.result_table_widget.setCurrentCell(row, 0)
        app.processEvents()
        check("FC FCS 行高亮生效", _bg_at(win, bs * 3 + 1) == "#ffeb3b",
              f"range=({bs},{be})")

    print("=" * 50)
    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} 项失败: {FAILURES}")
        os._exit(1)
    print(f"[OK] 全部 {PASS} 项检查通过")
    # Qt offscreen 在解释器退出析构时可能原生崩溃(与测试结论无关)，显式退出避免污染退出码
    os._exit(0)


if __name__ == "__main__":
    main()
