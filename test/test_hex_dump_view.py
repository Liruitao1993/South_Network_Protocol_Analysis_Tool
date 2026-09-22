"""`hex_dump_view.HexDumpView` 字节视图回归测试。

覆盖：
  [1] 渲染格式：16 字节/行、偏移列、ASCII 列、不可打印字符转 `.`
  [2] 字节下标 ↔ 文档字符位置映射（用文档文本反查核对，不是自证）
  [3] 高亮：区间内字节底色为高亮色、区间外不是；跨行区间正确
  [4] 边界：空字节、4096 字节、越界下标
  [5] 反例自检：用错误的映射公式（col*2）反查必然对不上，证明 [2] 判据有效

运行: QT_QPA_PLATFORM=offscreen python -u test/test_hex_dump_view.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402

from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import hex_dump_view as hdv  # noqa: E402

PASS = 0
FAIL = 0


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


def bg_of_byte(view, index):
    """读取第 index 字节起始字符处的背景色（直接读文档格式，非自证）。"""
    pos = view.char_pos_of_byte(index)
    if pos is None:
        return None
    cur = QTextCursor(view.document())
    cur.setPosition(pos)
    cur.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
    return cur.charFormat().background().color()


def hex_at(view, index):
    """用文档文本反查第 index 字节渲染出的两个 hex 字符。"""
    pos = view.char_pos_of_byte(index)
    if pos is None:
        return None
    return view.toPlainText()[pos:pos + 2]


def main():
    print("=" * 64)
    print("HexDumpView 字节视图（B1）")
    print("=" * 64)
    QApplication.instance() or QApplication([])  # 保证有 QApplication 实例

    section("[1] 渲染格式")
    data = bytes(range(32))
    view = hdv.HexDumpView()
    view.set_bytes(data)
    lines = view.toPlainText().split("\n")
    check("32 字节 → 2 行", len(lines) == 2, f"行数={len(lines)}")
    check("每行固定 77 字符", all(len(x) == hdv.ROW_LEN for x in lines),
          f"{[len(x) for x in lines]}")
    check("首行偏移列 = 00000000", lines[0].startswith("00000000  "), lines[0][:10])
    check("次行偏移列 = 00000010", lines[1].startswith("00000010  "), lines[1][:10])
    check("首行首字节 hex = 00", lines[0][10:12] == "00", lines[0][10:12])
    check("次行首字节 hex = 10（第 16 字节的值）", lines[1][10:12] == "10", lines[1][10:12])
    check("含 ASCII 分隔符", lines[0][59] == "|" and lines[0][-1] == "|",
          repr(lines[0][57:]))

    print(f"    渲染样例: {lines[0]}")

    # 不可打印 → '.'（ASCII 列右侧用空格补齐到 16，故只取前 6 个字符核对）
    view.set_bytes(b"\x00\x01\xedA\x7f\x20")
    line = view.toPlainText()
    ascii_part = line[line.index("|") + 1: line.rindex("|")]
    check("0x00/0x01/0xED/0x7F → '.'，0x41/0x20 原样",
          ascii_part[:6] == "...A. ", repr(ascii_part[:6]))
    check("ASCII 列补齐到 16 字符", len(ascii_part) == 16, str(len(ascii_part)))

    section("[2] 字节下标 ↔ 字符位置映射")
    view.set_bytes(bytes(range(48)))
    ok = True
    detail = []
    for idx in (0, 1, 5, 15, 16, 17, 31, 32, 47):
        got = hex_at(view, idx)
        want = f"{idx:02X}"
        if got != want:
            ok = False
            detail.append(f"byte{idx}: got={got} want={want}")
    check("各下标处文档文本确为该字节 hex", ok, " ".join(detail) or "0/1/5/15/16/17/31/32/47")
    check("char_pos_of_byte(0) == 10", view.char_pos_of_byte(0) == 10,
          str(view.char_pos_of_byte(0)))
    check("char_pos_of_byte(16) == 78 + 10", view.char_pos_of_byte(16) == 88,
          str(view.char_pos_of_byte(16)))
    check("越界返回 None", view.char_pos_of_byte(48) is None and view.char_pos_of_byte(-1) is None)

    section("[3] 高亮")
    view.set_bytes(bytes(range(48)))
    view.highlight_range(3, 5)
    bg_in = [bg_of_byte(view, i) for i in (3, 4, 5)]
    bg_out = [bg_of_byte(view, i) for i in (2, 6)]
    check("区间内 3 个字节都是高亮色",
          all(c == hdv.HIGHLIGHT_COLOR for c in bg_in), str(bg_in))
    check("区间外不是高亮色", all(c != hdv.HIGHLIGHT_COLOR for c in bg_out), str(bg_out))

    # 跨行
    view.highlight_range(15, 17)
    bg_cross = [bg_of_byte(view, i) for i in (15, 16, 17)]
    bg_cross_out = [bg_of_byte(view, i) for i in (14, 18)]
    check("跨行区间 15..17 全部高亮",
          all(c == hdv.HIGHLIGHT_COLOR for c in bg_cross), str(bg_cross))
    check("跨行区间外未被高亮",
          all(c != hdv.HIGHLIGHT_COLOR for c in bg_cross_out), str(bg_cross_out))

    view.clear_highlight()
    check("clear_highlight 后全部恢复",
          all(bg_of_byte(view, i) != hdv.HIGHLIGHT_COLOR for i in range(48)))

    view.highlight_range(0, 1000)
    check("end 越界被夹到末字节",
          bg_of_byte(view, 47) == hdv.HIGHLIGHT_COLOR)
    view.highlight_range(None, None)
    check("None 视为清除", bg_of_byte(view, 0) != hdv.HIGHLIGHT_COLOR)

    section("[4] 边界")
    view.set_bytes(b"")
    check("空字节：byte_length=0", view.byte_length == 0)
    check("空字节：文本为空", view.toPlainText() == "", repr(view.toPlainText()))
    check("空字节：char_pos 返回 None", view.char_pos_of_byte(0) is None)
    view.highlight_range(0, 3)
    check("空字节高亮不崩", True)

    big = bytes(range(256)) * 16  # 4096
    view.set_bytes(big)
    check("4096 字节 → 256 行",
          len(view.toPlainText().split("\n")) == 256,
          str(len(view.toPlainText().split("\n"))))
    check("4096 字节末字节 hex 正确", hex_at(view, 4095) == "FF", str(hex_at(view, 4095)))

    section("[5] 反例自检：错误映射公式必须对不上")
    view.set_bytes(bytes(range(32)))
    text = view.toPlainText()
    wrong_pos = hdv.ROW_STRIDE * 0 + hdv._PREFIX_LEN + 5 * 2  # 错误：col*2
    check(
        "用 col*2 反查会取到错字节（证明 [2] 判据有效）",
        text[wrong_pos:wrong_pos + 2] != "05",
        f"错公式取到 {text[wrong_pos:wrong_pos + 2]!r}",
    )

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
