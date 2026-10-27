# -*- coding: utf-8 -*-
"""「协议测试」页（698.45 按 OAD 分类的预置测试库）在 `main_gui` 里的**接线**回归（offscreen）。

只验证 main_gui ↔ dlt698_test_widget 的编排（注册表能力/懒加载/串口注入/协议显隐/
主题/收尾/「远程升级」跳转），页面内部行为由 `test/test_dlt698_testbench.py` 负责 ——
不要在这里重复断言组帧或解析。

冻结判据（协议注册表）：
- `protocol_registry.get_protocol(8).has_test is True`；其余 False
- `protocols_with_test() == (8,)`

运行: python test/test_dlt698_test_tab_wiring.py
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

_config_sandbox.install()

import protocol_registry  # noqa: E402
import main_gui  # noqa: E402

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
    print(f"\n== {title}")


def main() -> int:
    app = QApplication.instance() or QApplication([])

    section("[1] 注册表：has_test 只属协议8")
    check("get_protocol(8).has_test is True",
          protocol_registry.get_protocol(8).has_test is True)
    others = [p.index for p in protocol_registry.all_protocols()
              if p.index != 8 and p.has_test]
    check("其余协议均 has_test=False", others == [], others)
    check("protocols_with_test() == (8,)",
          protocol_registry.protocols_with_test() == (8,),
          protocol_registry.protocols_with_test())

    win = main_gui.MainWindow()
    try:
        section("[2] 页签存在与标题")
        idx = getattr(win, "_test_tab_index", None)
        check("存在测试页索引", idx is not None, idx)
        if idx is None:
            return 1
        check("标题为「协议测试」", win.tab_widget.tabText(idx) == "协议测试",
              win.tab_widget.tabText(idx))
        check("紧随升级页之后（同为协议8 专属）",
              idx == win._upgrade_tab_index + 1,
              f"test={idx} upgrade={win._upgrade_tab_index}")
        check("构造后默认隐藏", win.tab_widget.isTabVisible(idx) is False)

        section("[3] 协议显隐")
        win.protocol_combo.setCurrentIndex(0)
        app.processEvents()
        check("协议0 → 隐藏", win.tab_widget.isTabVisible(idx) is False)
        win.protocol_combo.setCurrentIndex(8)
        app.processEvents()
        check("协议8 → 可见", win.tab_widget.isTabVisible(idx) is True)
        win.protocol_combo.setCurrentIndex(7)
        app.processEvents()
        check("协议7 → 隐藏", win.tab_widget.isTabVisible(idx) is False)
        win.protocol_combo.setCurrentIndex(8)
        app.processEvents()
        check("再切协议8 → 可见", win.tab_widget.isTabVisible(idx) is True)

        section("[4] 懒加载 + 串口注入")
        check("未打开前不构造页面", getattr(win, "test_tab", None) is None)
        win.tab_widget.setCurrentIndex(idx)
        app.processEvents()
        tab = getattr(win, "test_tab", None)
        check("打开后已构造", tab is not None)
        if tab is None:
            return 1
        check("页面已替换占位符",
              win.tab_widget.widget(idx) is tab)
        check("复用主窗口串口线程", tab._serial_worker is win.serial_worker)
        check("注入蓝牙取值回调（复用蓝牙工具页连接）",
              callable(getattr(tab, "_bt_provider", None))
              and tab._bt_provider == win._upgrade_bluetooth_source,
              str(tab._bt_provider))
        check("未自建串口引用", not hasattr(tab, "serial_port") and
              not hasattr(tab, "serial"))

        section("[5] 「远程升级」跳转到光伏升级页")
        tab.open_upgrade.emit()
        app.processEvents()
        check("当前页切到光伏升级",
              win.tab_widget.currentIndex() == win._upgrade_tab_index,
              win.tab_widget.currentIndex())

        section("[6] 主题切换")
        check("浅色 restyle 不抛", _no_raise(lambda: tab.restyle_for_theme(False)))
        check("暗色 restyle 不抛", _no_raise(lambda: tab.restyle_for_theme(True)))
        win._restyle_for_theme()
        check("主窗口主题刷新不抛", True)

        section("[7] 收尾不关串口")
        check("存在 cleanup", hasattr(tab, "cleanup"))
        opened_before = bool(win.serial_worker.is_open())
        win.close()
        app.processEvents()
        check("关闭后串口状态未被强制改变",
              bool(win.serial_worker.is_open()) == opened_before)
    finally:
        try:
            win.deleteLater()
        except RuntimeError:
            pass

    print("\n" + "-" * 56)
    print(f"结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    return 0 if FAIL == 0 else 1


def _no_raise(fn) -> bool:
    try:
        fn()
        return True
    except Exception as exc:                                # noqa: BLE001
        print(f"      抛异常：{type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
