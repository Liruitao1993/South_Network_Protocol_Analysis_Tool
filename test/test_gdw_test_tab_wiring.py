# -*- coding: utf-8 -*-
"""「国网协议测试」页（协议7，AFN/Fn 分类树 + EB 扩展）在 `main_gui` 里的**接线**回归（offscreen）。

只验证 main_gui ↔ gdw_test_widget 的编排（注册表能力 / 懒加载 / 串口·蓝牙注入 /
单帧解析跳转 / 协议显隐 / 主题 / 收尾），页面内部行为由 `test/test_gdw_testbench.py` 负责。

冻结判据（协议注册表）：
- `protocol_registry.get_protocol(7).has_gdw_test is True`；其余 False
- `protocols_with_gdw_test() == (7,)`
- 与 698 的 `has_test`（仅8）/ 645 的 `has_dlt645_test`（仅6）互不干扰

运行: python test/test_gdw_test_tab_wiring.py
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


def _no_raise(fn) -> bool:
    try:
        fn()
        return True
    except Exception as exc:                                # noqa: BLE001
        print(f"      抛异常：{type(exc).__name__}: {exc}")
        return False


def main() -> int:
    app = QApplication.instance() or QApplication([])

    section("[1] 注册表：has_gdw_test 只属协议7")
    check("get_protocol(7).has_gdw_test is True",
          protocol_registry.get_protocol(7).has_gdw_test is True)
    others = [p.index for p in protocol_registry.all_protocols()
              if p.index != 7 and p.has_gdw_test]
    check("其余协议均 has_gdw_test=False", others == [], others)
    check("protocols_with_gdw_test() == (7,)",
          protocol_registry.protocols_with_gdw_test() == (7,),
          protocol_registry.protocols_with_gdw_test())
    check("不影响 698/645 的能力位",
          (protocol_registry.protocols_with_test(),
           protocol_registry.protocols_with_dlt645_test()) == ((8,), (6,)),
          (protocol_registry.protocols_with_test(),
           protocol_registry.protocols_with_dlt645_test()))

    win = main_gui.MainWindow()
    try:
        section("[2] 页签存在与标题")
        idx = getattr(win, "_gdw_test_tab_index", None)
        check("存在国网协议测试页索引", idx is not None, idx)
        if idx is None:
            return 1
        check("标题为「国网协议测试」", win.tab_widget.tabText(idx) == "国网协议测试",
              win.tab_widget.tabText(idx))
        check("紧随 645 测试页之后", idx == win._dlt645_test_tab_index + 1,
              f"gdw={idx} dlt645={win._dlt645_test_tab_index}")
        check("构造后默认隐藏", win.tab_widget.isTabVisible(idx) is False)

        section("[3] 协议显隐（7 独享）")
        for proto, want in ((0, False), (6, False), (7, True), (8, False), (13, False)):
            win.protocol_combo.setCurrentIndex(proto)
            app.processEvents()
            check(f"协议{proto} → {'可见' if want else '隐藏'}",
                  win.tab_widget.isTabVisible(idx) is want)
        win.protocol_combo.setCurrentIndex(7)
        app.processEvents()

        section("[4] 懒加载 + 注入")
        check("未打开前不构造页面", getattr(win, "gdw_test_tab", None) is None)
        win.tab_widget.setCurrentIndex(idx)
        app.processEvents()
        tab = getattr(win, "gdw_test_tab", None)
        check("打开后已构造", tab is not None)
        if tab is None:
            return 1
        check("页面已替换占位符", win.tab_widget.widget(idx) is tab)
        check("复用主窗口串口线程", tab._serial_worker is win.serial_worker)
        check("注入蓝牙取值回调（复用蓝牙工具页连接）",
              callable(getattr(tab, "_bt_provider", None))
              and tab._bt_provider == win._upgrade_bluetooth_source,
              str(tab._bt_provider))
        check("未自建串口引用", not hasattr(tab, "serial_port")
              and not hasattr(tab, "serial"))

        section("[5] 报文表双击 → 单帧解析（同一注入点）")
        tab.frame_to_single_parse.emit("68 1B 00 40 04 00 00 00 00 01 12 90 78 56 34 12 "
                                       "01 00 00 00 00 00 03 01 00 00 16")
        app.processEvents()
        check("单帧解析输入框收到报文",
              "68 1B 00" in win.single_input.toPlainText(),
              win.single_input.toPlainText()[:40])
        check("已切到单帧解析页", win.tab_widget.currentIndex() == 0,
              win.tab_widget.currentIndex())
        win.tab_widget.setCurrentIndex(idx)
        app.processEvents()

        section("[6] 主题切换")
        check("浅色 restyle 不抛", _no_raise(lambda: tab.restyle_for_theme(False)))
        check("暗色 restyle 不抛", _no_raise(lambda: tab.restyle_for_theme(True)))
        check("主窗口主题刷新不抛", _no_raise(win._restyle_for_theme))

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


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
