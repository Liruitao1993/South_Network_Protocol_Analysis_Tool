# -*- coding: utf-8 -*-
"""协议6「645协议测试」页在真实 `MainWindow` 里的接线回归。

覆盖：
  [1] 注册表能力：`has_dlt645_test` 只有协议6，`has_test`（698）仍只有协议8
  [2] tab 存在与标题、启动即隐藏、按协议显隐（0/7/8 隐藏、6 显示）
  [3] 懒加载：未点开前不构造控件；点开只建一次；串口与单帧解析注入
  [4] 收尾：`cleanup()` 幂等且不关闭共享串口

运行: python test/test_dlt645_test_tab_wiring.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

_config_sandbox.install()

for _name in ("warning", "information", "critical"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import protocol_registry as registry  # noqa: E402

FAILED = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        return True
    FAILED.append(f"{name}" + (f"\n    {detail}" if detail else ""))
    return False


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 60 - len(title)))


def app():
    return QApplication.instance() or QApplication([])


def test_registry():
    section("[1] 注册表能力位")
    check("has_dlt645_test 只在协议6",
          [p.index for p in registry.all_protocols() if p.has_dlt645_test] == [6],
          str([p.index for p in registry.all_protocols() if p.has_dlt645_test]))
    check("has_test（698）仍只有协议8",
          registry.protocols_with_test() == (8,),
          str(registry.protocols_with_test()))
    check("protocols_with_dlt645_test() == (6,)",
          registry.protocols_with_dlt645_test() == (6,),
          str(registry.protocols_with_dlt645_test()))


def test_wiring():
    section("[2]-[4] MainWindow 接线")
    app()
    import main_gui

    win = main_gui.MainWindow()
    try:
        win._on_protocol_changed(6)
        app().processEvents()
        index = getattr(win, "_dlt645_test_tab_index", -1)
        check("tab 存在", index >= 0, str(index))
        check("标题为「645协议测试」", win.tab_widget.tabText(index) == "645协议测试",
              win.tab_widget.tabText(index))
        check("协议6 下可见", win.tab_widget.isTabVisible(index))

        win._on_protocol_changed(0)
        app().processEvents()
        check("协议0 下隐藏", not win.tab_widget.isTabVisible(index))
        win._on_protocol_changed(8)
        app().processEvents()
        check("协议8 下隐藏（698 测试页仍显示）",
              not win.tab_widget.isTabVisible(index)
              and win.tab_widget.isTabVisible(win._test_tab_index))
        win._on_protocol_changed(7)
        app().processEvents()
        check("协议7 下隐藏", not win.tab_widget.isTabVisible(index))

        check("未点开前不构造控件", not hasattr(win, "dlt645_test_tab"))
        win._on_protocol_changed(6)
        app().processEvents()
        win.tab_widget.setCurrentIndex(index)
        app().processEvents()
        tab = getattr(win, "dlt645_test_tab", None)
        check("点开后惰性创建", tab is not None)
        check("只建一次", win._ensure_dlt645_test_tab() is tab)
        check("注入共享串口", tab._serial_worker is win.serial_worker,
              f"{type(getattr(tab, '_serial_worker', None)).__name__}")
        check("注入蓝牙取值回调（复用蓝牙工具页连接）",
              callable(getattr(tab, "_bt_provider", None))
              and tab._bt_provider == win._upgrade_bluetooth_source,
              str(getattr(tab, "_bt_provider", None)))
        check("创建即按当前主题初始化（_dark 已赋值）",
              isinstance(getattr(tab, "_dark", None), bool))
        check("分类树已建出（DI 表可读，非空壳页面）",
              tab._pages["read"]["tree"].topLevelItemCount() == 11,
              str(tab._pages["read"]["tree"].topLevelItemCount()))

        frame_hex = "68 00 00 00 00 00 00 68 11 04 33 34 34 35 B5 16"
        tab.frame_to_single_parse.emit(frame_hex)
        app().processEvents()
        check("双击报文 → 单帧解析页输入框拿到该帧",
              win.single_input.toPlainText() == frame_hex,
              win.single_input.toPlainText()[:60])
        check("并切到单帧解析页", win.tab_widget.currentIndex() == 0,
              str(win.tab_widget.currentIndex()))

        opened_before = win.serial_worker.is_open()
        tab.cleanup()
        tab.cleanup()          # 幂等
        check("cleanup 幂等且不关闭共享串口",
              win.serial_worker.is_open() == opened_before)
        check("cleanup 后串口引用已摘除", tab._serial_worker is None)
    finally:
        win.close()
        app().processEvents()


def main():
    tests = [("[1] 注册表", test_registry), ("[2]-[4] 接线", test_wiring)]
    for name, fn in tests:
        before = len(FAILED)
        try:
            fn()
        except Exception as exc:                          # noqa: BLE001
            import traceback

            FAILED.append(f"{name} 抛异常：{type(exc).__name__}: {exc}\n"
                          f"{traceback.format_exc()}")
        print(("OK   " if len(FAILED) == before else "FAIL ") + name)

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项 / 共 {CHECKS[0]} 项检查")
        for item in FAILED:
            print(" - " + item)
        return 1
    print(f"全部通过：{CHECKS[0]} 项检查")
    return 0


if __name__ == "__main__":
    sys.exit(main())
