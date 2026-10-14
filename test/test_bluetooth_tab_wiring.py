# -*- coding: utf-8 -*-
"""蓝牙工具标签页在 `main_gui` 里的**接线**回归测试（offscreen）。

为什么单独有一份（而不是并进 `test_bluetooth_widget.py`）：
后者只测「页面自己」（注入假 worker / 假串口），**完全不碰 `main_gui`**。而
「本项目具备蓝牙通信能力」这件事的全部风险恰恰在接线处 —— 懒加载分支、共享串口
注入、三个回调注入、主题钩子、收尾调用。这些接线错了，页面单测照样全绿。

覆盖（编号即执行顺序）：
  [1] 占位页存在于「串口工具」之后，标题/图标正确、**始终可见**
  [2] 懒加载：未切过去时 `bluetooth_tool_tab` 属性不存在（不预热解析器）
  [3] 切过去后按 `_replace_lazy_tab` 原地替换（同索引、标题与图标不变）
  [4] 注入齐全：共享串口线程 / 解析回调 / 协议回调 / 送入单帧回调
  [5] 协议回调返回主窗口当前协议
  [6] 幂等：重复触发只建一次，返回同一实例
  [7] 「送入单帧解析」真能落到主窗口单帧页
  [8] 反例自检（判据有效）
  [9] 主题钩子不抛；`_shutdown_threads` 会调用本页 `cleanup()`
  [10] 静态守卫：`main_gui` 任何地方都不得对蓝牙页调 `setTabVisible(..., False)`

运行: python test/test_bluetooth_tab_wiring.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# 构造主窗口之前屏蔽模态框（否则 offscreen 下永久阻塞）
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

_config_sandbox.install()

import main_gui  # noqa: E402

PASS = 0
FAIL = 0


def _console_safe(text) -> str:
    """按控制台编码降级打印（Windows 控制台常为 GBK，页面上有 ✓/⚠ 之类符号）。"""
    raw = str(text)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return raw.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except (LookupError, UnicodeError):
        return raw.encode("ascii", errors="replace").decode("ascii")


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [NG] {name}" + (f"  -> {_console_safe(detail)}" if detail else ""))


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 56 - len(title)))


def new_window():
    win = main_gui.MainWindow()
    return win


def open_bluetooth_tab(win):
    """模拟用户点开「蓝牙工具」标签页。"""
    win.tab_widget.setCurrentIndex(win._bluetooth_tool_tab_index)
    QApplication.processEvents()
    return getattr(win, "bluetooth_tool_tab", None)


# ── [1] 占位页 ──────────────────────────────────────────────────────────────


def test_placeholder(win):
    section("[1] 占位页（始终可见）")

    check("存在蓝牙页索引", hasattr(win, "_bluetooth_tool_tab_index"),
          getattr(win, "_bluetooth_tool_tab_index", None))
    idx = win._bluetooth_tool_tab_index
    check("标题为「蓝牙工具」", win.tab_widget.tabText(idx) == "蓝牙工具",
          win.tab_widget.tabText(idx))
    check("图标非空", not win.tab_widget.tabIcon(idx).isNull())
    check("标签页可见（不随协议隐藏）", win.tab_widget.isTabVisible(idx) is True)
    check("排在「串口工具」之后",
          win._bluetooth_tool_tab_index == win._serial_tool_tab_index + 1,
          f"{win._serial_tool_tab_index} -> {win._bluetooth_tool_tab_index}")


# ── [2][3] 懒加载 ───────────────────────────────────────────────────────────


def test_lazy(win):
    section("[2][3] 懒加载与原地替换")

    check("未打开时还没建页面（懒加载生效）",
          not hasattr(win, "bluetooth_tool_tab"))
    placeholder = win.tab_widget.widget(win._bluetooth_tool_tab_index)
    check("占位页是个空 QWidget", placeholder is win._bluetooth_tool_placeholder)

    before_title = win.tab_widget.tabText(win._bluetooth_tool_tab_index)
    before_icon = win.tab_widget.tabIcon(win._bluetooth_tool_tab_index)

    tab = open_bluetooth_tab(win)
    check("切过去后页面已建好", tab is not None)
    check("索引未变", win.tab_widget.widget(win._bluetooth_tool_tab_index) is tab)
    check("标题保持不变", win.tab_widget.tabText(win._bluetooth_tool_tab_index) == before_title)
    check("图标保持不变（insertTab 带回了图标）",
          win.tab_widget.tabIcon(win._bluetooth_tool_tab_index).cacheKey() == before_icon.cacheKey())
    return tab


# ── [4][5] 注入 ─────────────────────────────────────────────────────────────


def test_injection(win, tab):
    section("[4][5] 注入齐全")

    check("共享串口线程已注入（不是另开 COM 口）",
          tab._serial_worker is win.serial_worker, tab._serial_worker)
    check("解析回调已注入", tab._parse_provider is not None)
    check("解析回调就是主窗口那一个（口径同单帧页）",
          tab._parse_provider == win._serial_parse_provider)
    check("协议回调已注入", tab._protocol_provider is not None)
    check("送入单帧回调已注入",
          tab._send_to_single_handler == win._send_frame_to_single_parse)

    protocol = win._bluetooth_protocol_provider()
    check("协议回调返回主窗口当前协议",
          protocol == win.current_protocol, f"{protocol} vs {win.current_protocol}")

    # 页面自己也要能问出「跟随值」
    followed = tab._protocol_from_main()
    check("页面读到跟随协议", followed == win.current_protocol, followed)


# ── [6] 幂等 ────────────────────────────────────────────────────────────────


def test_idempotent(win, tab):
    section("[6] 幂等")

    again = win._ensure_lazy_tab(win._bluetooth_tool_tab_index)
    check("重复触发不报错（返回 None）", again is None, again)
    check("仍是同一个实例", win.bluetooth_tool_tab is tab)
    check("按钮仍然可用（没被重建砸掉）", tab.btn_scan is not None)


# ── [7] 主题与收尾 ──────────────────────────────────────────────────────────


def test_theme_and_shutdown(win, tab):
    section("[9] 主题钩子与收尾")

    try:
        win._restyle_for_theme()
        ok, detail = True, ""
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    check("_restyle_for_theme 不抛（已挂上蓝牙页）", ok, detail)

    calls = []
    original = tab.cleanup

    def spy():
        calls.append(1)
        return original()

    tab.cleanup = spy
    try:
        win._shutdown_threads()
    except Exception as exc:  # noqa: BLE001 - 收尾各步独立 try，这里只关心是否调到本页
        check("_shutdown_threads 不抛", False, f"{type(exc).__name__}: {exc}")
    else:
        check("_shutdown_threads 不抛", True)
    check("_shutdown_threads 调用了本页 cleanup()（否则 BLE 线程与日志尾丢失）",
          len(calls) >= 1, calls)
    tab.cleanup = original


# ── [8] 送入单帧解析 ────────────────────────────────────────────────────────


def test_send_to_single(win, tab):
    section("[7] 送入单帧解析")

    tab.combo_send_format.setCurrentIndex(
        [i for i in range(tab.combo_send_format.count())
         if tab.combo_send_format.itemData(i) == "auto"][0])
    tab.edit_send.setText("68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16")
    tab.btn_send_parse.click()
    QApplication.processEvents()

    text = win.single_input.toPlainText()
    check("内容进了主窗口单帧页输入框",
          "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16" in text, text[:80])
    check("切回了单帧解析页", win.tab_widget.currentIndex() == 0,
          win.tab_widget.currentIndex())


# ── [9] 静态守卫 ────────────────────────────────────────────────────────────


def test_static_guard():
    section("[10] 静态守卫：蓝牙页不许被 setTabVisible 藏起来")

    src = Path(main_gui.__file__).read_text(encoding="utf-8")
    bad = [ln.strip() for ln in src.splitlines()
           if "_bluetooth_tool_tab_index" in ln and "setTabVisible" in ln]
    check("main_gui 里没有对蓝牙页的 setTabVisible 调用", bad == [], bad)

    # 收敛判据有效性：串口工具页同款写法也不该出现（对照组）
    bad_serial = [ln.strip() for ln in src.splitlines()
                  if "_serial_tool_tab_index" in ln and "setTabVisible" in ln]
    check("对照组：串口工具页同样没被 setTabVisible", bad_serial == [], bad_serial)

    check("懒加载分支里挂了蓝牙页",
          "self._ensure_bluetooth_tool_tab()" in src)
    check("主题钩子里挂了蓝牙页",
          "self.bluetooth_tool_tab.restyle_for_theme(" in src)
    check("收尾里挂了蓝牙页",
          'bluetooth_tool = getattr(self, "bluetooth_tool_tab", None)' in src)


# ── [10] 反例自检 ───────────────────────────────────────────────────────────


def test_negatives(win, tab):
    section("[8] 反例自检（判据有效）")

    # 判据不可能恒真：故意给一个不存在的属性名，同样的断言必须为假
    check("属性判据不是恒真",
          not hasattr(win, "definitely_not_a_tab_attribute"))

    # 协议回调确实读的是 main_gui 的值：改掉它，回调结果跟着变
    original = win.current_protocol
    try:
        win.current_protocol = 99
        check("协议回调不是硬编码（跟随值变了它就变）",
              win._bluetooth_protocol_provider() == 99,
              win._bluetooth_protocol_provider())
    finally:
        win.current_protocol = original

    # 注入不是「有就行」：把解析回调抹掉，正向判据必须变假
    saved = tab._parse_provider
    check("抹掉前正向判据为真", tab._parse_provider is not None)
    tab._parse_provider = None
    check("解析回调判据不是恒真（抹掉后为假）", (tab._parse_provider is not None) is False)
    tab._parse_provider = saved
    check("还原后判据恢复为真", tab._parse_provider is not None)


def main():
    print("=" * 64)
    print("蓝牙工具标签页接线（main_gui）offscreen 回归")
    print("=" * 64)

    app = QApplication.instance() or QApplication([])
    win = new_window()
    try:
        test_placeholder(win)
        tab = test_lazy(win)
        if tab is None:
            check("页面建好了（后续用例的前置）", False)
        else:
            test_injection(win, tab)
            test_idempotent(win, tab)
            test_send_to_single(win, tab)
            test_negatives(win, tab)
            # 收尾放最后：它会停掉所有后台线程
            test_theme_and_shutdown(win, tab)
        test_static_guard()
    finally:
        try:
            win.close()
        except Exception:
            pass

    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
