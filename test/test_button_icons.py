# -*- coding: utf-8 -*-
"""单帧解析按钮行图标回归测试（offscreen）

背景缺陷：「分享此帧」曾调 set_btn_icon(btn, "share")，而 Qt 标准图标映射表无
"share" 键且未知键静默跳过 → 该按钮无图标、与同排不一致。修复：改用 Lucide
share-2（app_icons），并给 set_btn_icon 未知键补一次告警。

覆盖：
  1. 单帧解析按钮行全部按钮图标非空（解析/校验/添加/分享/清空/填充CRC-24/32）
  2. 分享按钮图标尺寸与同排一致（16×16）
  3. set_btn_icon 未知键仍安全跳过（不崩溃、图标不变）
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
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication, QPushButton
    app = QApplication.instance() or QApplication([])

    import main_gui
    win = main_gui.MainWindow()

    named = [
        ("解析报文", win.parse_btn),
        ("校验报文", win.verify_btn),
        ("添加到测试方案", win.add_to_test_btn),
        ("分享此帧", win.share_frame_btn),
        ("填充CRC-24", win.fill_crc24_btn),
        ("填充CRC-32", win.fill_crc32_btn),
    ]
    clears = [b for b in win.findChildren(QPushButton) if b.text() == "清空"]
    check("找到清空按钮", len(clears) >= 1)
    if clears:
        named.append(("清空", clears[0]))

    for text, btn in named:
        check(f"「{text}」按钮图标非空", not btn.icon().isNull(),
              f"icon isNull={btn.icon().isNull()}")

    check("分享按钮图标尺寸 16×16",
          win.share_frame_btn.iconSize() == QSize(16, 16),
          f"got {win.share_frame_btn.iconSize()}")

    # 未知键安全跳过：不崩溃且不改图标
    from gui_utils import set_btn_icon
    probe = QPushButton("probe")
    before_null = probe.icon().isNull()
    set_btn_icon(probe, "definitely-not-a-key")
    check("set_btn_icon 未知键安全跳过", probe.icon().isNull() == before_null)

    print("=" * 50)
    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} 项失败: {FAILURES}")
        raise SystemExit(1)
    print(f"[OK] 全部 {PASS} 项检查通过")


if __name__ == "__main__":
    main()
