"""批量解析结果 → 输入日志行回跳 offscreen 回归测试

覆盖：
  1. 纯 hex 行（含噪声行/空行）：_src_line 记录显示行号
  2. 点击摘要行 → 输入框光标跳到对应行并选中（blockNumber 校验）
  3. ED 广西台体包装行：_src_line 指向包装行（非业务帧行）
  4. 监控前缀日志行（"> 接收机 Has Get" + 15B 头）：strip 行映射回跳正确
  5. 首部空白行偏移计入 _src_line

直接运行: python test_batch_src_line_jump.py
"""

import os

import _path_setup  # noqa: E402,F401

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


def _spaced(hex_str):
    return " ".join(hex_str[i : i + 2] for i in range(0, len(hex_str), 2))


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from _batch_wait import wait_batch
    from test_csg_sequence_model import SOF_DOWN, SOF_UP
    from test_ed_gx_wrapper import _build_gx_frame

    import main_gui

    win = main_gui.MainWindow()
    win.current_protocol = 9
    app.processEvents()

    gx_frame = _build_gx_frame(SOF_DOWN)

    # ── 1+5: 首部空行 + 噪声行 + 空行 + ED 包装行 ──
    lines = [
        "",  # 0 首部空行（lead 偏移）
        "260908-193711-079: 900[1] BOOT: boot start",  # 1 噪声
        _spaced(SOF_DOWN.hex().upper()),  # 2 帧1
        "",  # 3 空行
        _spaced(SOF_UP.hex().upper()),  # 4 帧2
        _spaced(gx_frame.hex().upper()),  # 5 ED 广西台体包装行
    ]
    win.batch_input.setPlainText("\n".join(lines))
    win.parse_batch()
    wait_batch(win)

    check("解析 3 帧", len(win.batch_results) == 3, f"n={len(win.batch_results)}")
    src_lines = [r.get("_src_line") for r in win.batch_results]
    check("行号记录(含lead偏移)", src_lines == [2, 4, 5], f"src_lines={src_lines}")

    # ── 2: 点击摘要行回跳 ──
    win._on_batch_row_selected(1)
    app.processEvents()
    cur = win.batch_input.textCursor()
    check(
        "点击第2帧回跳行4",
        cur.blockNumber() == 4,
        f"block={cur.blockNumber()}",
    )
    check(
        "回跳选中整行",
        cur.hasSelection()
        and SOF_UP.hex()[:16].upper() in cur.selectedText().replace(" ", ""),
        f"sel={cur.selectedText()[:24]}",
    )

    win._on_batch_row_selected(2)
    app.processEvents()
    check(
        "点击ED帧回跳包装行5",
        win.batch_input.textCursor().blockNumber() == 5,
        f"block={win.batch_input.textCursor().blockNumber()}",
    )

    # ── 4: 监控前缀日志行（strip 行映射）──
    mon_lines = [
        "15:49:51 254  -> 接收机 Has Get "
        + _spaced("EDA5000002EF017E4E978601008800")
        + " "
        + _spaced(SOF_DOWN.hex().upper()),
        "noise line",
        "15:49:52 255  -> 接收机 Has Get "
        + _spaced("EDA5000002EF017E4E978601008800")
        + " "
        + _spaced(SOF_UP.hex().upper()),
    ]
    win.batch_input.setPlainText("\n".join(mon_lines))
    win.parse_batch()
    wait_batch(win)
    src2 = [r.get("_src_line") for r in win.batch_results]
    check("监控前缀行映射", src2 == [0, 2], f"src2={src2}")
    if src2 == [0, 2]:
        win._on_batch_row_selected(1)
        app.processEvents()
        check(
            "监控日志回跳行2",
            win.batch_input.textCursor().blockNumber() == 2,
            f"block={win.batch_input.textCursor().blockNumber()}",
        )

    win.close()
    win.deleteLater()
    app.processEvents()

    print("=" * 56)
    if FAILURES:
        print(f"共 {len(FAILURES)} 项失败: {FAILURES}")
        raise SystemExit(1)
    print(f"全部测试通过（{PASS} 项）✓")


if __name__ == "__main__":
    main()
