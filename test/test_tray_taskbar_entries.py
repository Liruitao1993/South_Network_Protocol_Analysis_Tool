# -*- coding: utf-8 -*-
"""粘性入口回归：托盘菜单内嵌输入框 + 任务栏缩略图按钮（offscreen，不碰硬件/外壳）。

覆盖：
  [1] 托盘：菜单里有内嵌输入框；回车/点「解析」发出 `parse_text_requested` 并清空输入；
      空输入不发；`set_input_enabled` 能禁用并改占位提示
  [2] 任务栏按钮模块：`qimage_to_hicon`（真实 QImage → 非 0 HICON；空图 → None）；
      `set_buttons([])`/未就绪时返回 False 不抛；`clear()` 幂等
  [3] 任务栏点击路由：合成 `WM_COMMAND` 喂 `nativeEventFilter` ⇒ 命中 id 发 `clicked` 且**吞掉**消息；
      别的 id / 别的消息类型 ⇒ 不发也不吞
  [4] MainWindow 接线：托盘信号连到解析路径；`_parse_text_input` 严格 HEX → `_parse_and_show_dialog`
      （协议按识别结果，识别不出用当前协议）；非 HEX 文本 → `_parse_text_content`；都不像 ⇒ False + 提示
  [5] `_on_taskbar_button` 分派：4 个 id 分别落到 解析剪贴板 / 快捷解析 / 批量解析 / 光伏升级

运行: python test/test_tray_taskbar_entries.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

import ctypes  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
from ctypes import wintypes  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

_config_sandbox.install()
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import app_icons  # noqa: E402
import main_gui  # noqa: E402
from system_integration import sys_tray as tray_mod  # noqa: E402
from system_integration import taskbar_buttons as tb_mod  # noqa: E402

IS_WINDOWS = sys.platform.startswith("win")

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [NG] {name}" + (f"  -> {detail}" if detail else ""))


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 56 - len(title)))


def pump(times: int = 6):
    for _ in range(max(1, times)):
        QApplication.processEvents()


# ── [1] 托盘内嵌输入框 ───────────────────────────────────────────────────────


def test_tray_input():
    section("[1] 托盘菜单内嵌输入框")
    tray = tray_mod.SystemTrayManager(None)
    # 托盘在 headless/offscreen 下可能不可用：直接手动建菜单那一段（create 会先判可用性）
    tray._tray = None
    ok = tray.create()
    if not ok:
        # 无托盘时手工跑菜单构建（把可用性判断绕开，只验菜单/输入框行为）
        from PySide6.QtWidgets import QMenu, QLineEdit, QWidgetAction
        menu = QMenu()
        tray._menu = menu
        tray._input = QLineEdit()
        tray._input.returnPressed.connect(tray._on_input_submitted)
        act = QWidgetAction(menu)
        act.setDefaultWidget(tray._input)
        menu.addAction(act)
    check("菜单里有内嵌输入框（QWidgetAction）",
          tray._input is not None and any(
              isinstance(a, tray_mod.QWidgetAction) for a in tray._menu.actions())
          if tray._menu is not None else False,
          type(tray._input).__name__)

    got = []
    tray.parse_text_requested.connect(got.append)
    tray._input.setText("68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16")
    tray._input.returnPressed.emit()
    check("回车提交 → 发出 parse_text_requested（正文原样）",
          got == ["68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16"], got)
    check("提交后输入框清空", tray._input.text() == "")
    tray._input.setText("   ")
    tray._input.returnPressed.emit()
    check("空/纯空白不提交", len(got) == 1, got)

    tray.set_input_enabled(False, "解析器未就绪")
    check("可禁用输入并改占位提示",
          tray._input.isEnabled() is False and "解析器未就绪" in tray._input.placeholderText())
    tray.set_input_enabled(True)
    check("可恢复可用", tray._input.isEnabled() is True)


# ── [2] 任务栏按钮模块（HICON / 降级） ───────────────────────────────────────


def test_taskbar_module():
    section("[2] 任务栏按钮模块：HICON 转换与优雅降级")
    if not IS_WINDOWS:
        check("非 Windows 平台直接跳过（模块只支持 Windows）", True)
        return
    img = QImage(16, 16, QImage.Format.Format_ARGB32)
    img.fill(0xFF3366FF)
    hicon = tb_mod.qimage_to_hicon(img)
    check("QImage → HICON 非 0", bool(hicon), hicon)
    check("空 QImage → None", tb_mod.qimage_to_hicon(QImage()) is None)
    check("非图像对象 → None", tb_mod.qimage_to_hicon("nope") is None)

    tb = tb_mod.TaskbarButtons()
    check("available() 在本机为 True（Coclass 可建）", tb.available() is True, tb.available())
    window = main_gui.QWidget() if hasattr(main_gui, "QWidget") else None
    from PySide6.QtWidgets import QWidget
    window = QWidget()
    check("空按钮列表 → False（不抛）", tb.set_buttons(window, []) is False)
    tb.clear(window)                      # 未挂过：幂等不抛
    check("clear() 未被挂过时幂等", True)
    window.deleteLater()


# ── [3] 点击路由（合成 WM_COMMAND） ──────────────────────────────────────────


def test_click_routing():
    section("[3] 任务栏按钮点击路由（外壳发 WM_COMMAND）")
    if not IS_WINDOWS:
        check("非 Windows 跳过", True)
        return
    tb = tb_mod.TaskbarButtons()
    tb._ids = [tb_mod.BASE_BUTTON_ID, tb_mod.BASE_BUTTON_ID + 1]
    filt = tb_mod._NativeClickFilter(tb)
    got = []
    tb.clicked.connect(got.append)

    def msg_ptr(message, wparam=0):
        msg = wintypes.MSG()
        msg.message = message
        msg.wParam = wparam
        return ctypes.addressof(msg)

    check("命中按钮 id ⇒ 发 clicked 且吞掉消息",
          filt.nativeEventFilter(b"windows_generic_MSG",
                                 msg_ptr(tb_mod.WM_COMMAND, tb_mod.BASE_BUTTON_ID + 1)) is True
          and got == [tb_mod.BASE_BUTTON_ID + 1], got)
    check("别的 id ⇒ 不发也不吞",
          filt.nativeEventFilter(b"windows_generic_MSG", msg_ptr(tb_mod.WM_COMMAND, 0x1234)) is False
          and len(got) == 1)
    check("别的消息类型 ⇒ 直接放行",
          filt.nativeEventFilter(b"windows_generic_MSG", msg_ptr(0x0001, 0)) is False)
    check("非 Windows 消息类型 ⇒ 放行",
          filt.nativeEventFilter(b"xcb_generic_event_t", msg_ptr(tb_mod.WM_COMMAND, 0)) is False)


# ── [4] MainWindow 解析路径与提示 ────────────────────────────────────────────


def test_mainwindow_parse_path(win):
    section("[4] MainWindow：文本→解析路径（托盘/任务栏共用）")
    calls = {}
    win._parse_and_show_dialog = (
        lambda frame, idx=None: calls.setdefault("dialog", (bytes(frame), idx)))
    win._parse_text_content = lambda text: calls.setdefault("text", text)

    frame_hex = "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16"
    check("严格 HEX → 走 _parse_and_show_dialog",
          win._parse_text_input(frame_hex) is True and calls.get("dialog") is not None,
          calls.get("dialog"))
    check("传入的字节与输入一致",
          calls["dialog"][0] == bytes.fromhex(frame_hex.replace(" ", "")), calls["dialog"][0])
    check("协议索引落在合法范围（识别结果或当前协议）",
          isinstance(calls["dialog"][1], int) and 0 <= calls["dialog"][1] < 15, calls["dialog"][1])

    calls.clear()
    check("非 HEX 文本 → 走「按文本提取报文」路径",
          win._parse_text_input("日志: 收到 68 0E 00 ... 16 共 14 字节") is True
          and "text" in calls, calls)
    calls.clear()
    check("空文本 / 无任何报文 ⇒ False（调用方负责提示）",
          win._parse_text_input("") is False and win._parse_text_input("   ") is False
          and calls == {})

    # 不受理时的提示（状态栏 + 托盘气泡），且提示不再是模态弹窗阻塞
    with patch.object(win, "statusBar") as sb:
        tip = []
        sb.return_value.showMessage = lambda msg, ms=0: tip.append(msg)
        win._tray_manager = None
        win._on_tray_parse_text("这不是报文")
    check("不受理时状态栏给出可读提示", bool(tip) and "HEX" in tip[0], tip)


# ── [5] 任务栏按钮分派 ──────────────────────────────────────────────────────


def test_taskbar_dispatch(win):
    section("[5] 任务栏按钮分派（4 个 id）")
    hit = []
    win._taskbar_parse_clipboard = lambda: hit.append("剪贴板")
    win._on_global_hotkey = lambda: hit.append("快捷")
    win._goto_tab = lambda index: hit.append(("tab", index))
    win.showNormal = lambda: hit.append("show")

    for offset, expect in enumerate(("剪贴板", "快捷")):
        win._on_taskbar_button(main_gui.TASKBAR_BASE_ID + offset)
        check(f"按钮 {offset} → {expect}", hit and hit[-1] == expect, hit)

    win.showNormal = lambda: hit.append("show")
    win._on_taskbar_button(main_gui.TASKBAR_BASE_ID + 2)
    check("按钮 2 → 切到批量解析页",
          hit[-1] == ("tab", getattr(win, "_batch_tab_index", -1)), hit[-1])
    win._on_taskbar_button(main_gui.TASKBAR_BASE_ID + 3)
    check("按钮 3 → 切协议8 + 切到光伏升级页（最后一个 tab 动作是升级页）",
          hit[-1] == ("tab", getattr(win, "_upgrade_tab_index", -1))
          and win.current_protocol == 8, (hit[-2:], win.current_protocol))
    before = len(hit)
    win._on_taskbar_button(main_gui.TASKBAR_BASE_ID + 9)
    check("越界 id ⇒ 什么都不做（不越界索引）", len(hit) == before)


def main():
    print("=" * 64)
    print("粘性入口回归（托盘输入框 + 任务栏缩略图按钮，offscreen）")
    print("=" * 64)
    if QApplication.instance() is None:
        QApplication([])  # noqa: F841 —— 保证实例存在

    test_tray_input()
    test_taskbar_module()
    test_click_routing()

    win = main_gui.MainWindow()
    pump()
    try:
        test_mainwindow_parse_path(win)
        test_taskbar_dispatch(win)
    finally:
        try:
            win._tray_exit = True
            win.close()
            pump()
        except Exception:
            pass

    print()
    print("-" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）")
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
