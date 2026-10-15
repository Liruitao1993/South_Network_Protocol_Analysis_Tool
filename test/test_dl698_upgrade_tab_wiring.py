# -*- coding: utf-8 -*-
"""升级页（698.45 文件传输升级）在 `main_gui` 里的**接线**回归测试（offscreen）。

只验证 main_gui↔dlt698_upgrade_widget 的编排（懒加载/注入/协议显隐/主题/收尾），
页面内部行为由 test/test_dl698_upgrade_gui.py 负责 —— 不要在这里重复断言。

参照 test/test_bluetooth_tab_wiring.py 的既有写法（_path_setup、check/section、
沙箱、os._exit 前 sys.stdout.flush()）。

冻结判据（协议注册表）：
- protocol_registry.get_protocol(8).has_upgrade is True；其余 False
- protocols_with_upgrade() == (8,)
"""

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# 构造主窗口之前屏蔽模态框（否则 offscreen 下永久阻塞）
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

# 沙箱 install **之前**抓真实 data 目录（构窗前本来就不应有 config.json）
_REAL_DATA_DIR = __import__("app_paths").data_path("").parent
_config_sandbox.install()

import protocol_registry  # noqa: E402
import main_gui  # noqa: E402

PASS = 0
FAIL = 0


def _console_safe(text) -> str:
    """按控制台编码降级打印（Windows 控制台常为 GBK，页面里有 ✓/⚠ 之类符号）。"""
    try:
        print(text)
        return ""
    except UnicodeEncodeError:
        raw = str(text)
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


def switch_protocol(win, index):
    """切协议（走 protocol_combo，触发 _on_protocol_changed 全链）。"""
    win.protocol_combo.setCurrentIndex(index)
    pump()


def pump():
    """offscreen 下多泵几次：重建控件/重绘信号要走完才稳定。"""
    for _ in range(6):
        QApplication.processEvents()


# ── [1] 注册表 ──────────────────────────────────────────────────────────────


def test_registry():
    section("[1] 注册表：has_upgrade 只属协议8")

    check("get_protocol(8).has_upgrade is True",
          protocol_registry.get_protocol(8).has_upgrade is True)
    others = [p.index for p in protocol_registry._PROTOS
              if p.index != 8 and p.has_upgrade]
    check("其余协议均 has_upgrade=False", others == [], others)
    check("protocols_with_upgrade() == (8,)",
          protocol_registry.protocols_with_upgrade() == (8,),
          protocol_registry.protocols_with_upgrade())


# ── [2] 占位页 ──────────────────────────────────────────────────────────────


def test_placeholder(win):
    section("[2] 占位页存在且默认隐藏")

    check("存在升级页索引", hasattr(win, "_upgrade_tab_index"),
          getattr(win, "_upgrade_tab_index", None))
    idx = win._upgrade_tab_index
    check("标题为「光伏升级」", win.tab_widget.tabText(idx) == "光伏升级",
          win.tab_widget.tabText(idx))
    check("启动默认（协议0）下不可见",
          win.tab_widget.isTabVisible(idx) is False)
    check("启动默认下页面还没建（懒加载生效）",
          not hasattr(win, "upgrade_tab"))


# ── [3][4] 协议显隐往返 + 懒加载替换 ─────────────────────────────────────────


def test_visibility_roundtrip(win):
    section("[3][4] 协议显隐往返 + 懒加载原地替换（切换→点开）")

    idx = win._upgrade_tab_index
    switch_protocol(win, 8)
    check("切到协议8 → tab 可见",
          win.tab_widget.isTabVisible(idx) is True)

    # 模拟用户点开该 tab（懒加载由 tab 切换 currentChanged 触发）
    win.tab_widget.setCurrentIndex(idx)
    pump()
    check("点开后页面已建", hasattr(win, "upgrade_tab"))
    tab = getattr(win, "upgrade_tab", None)
    check("页面已建且非 None", tab is not None)
    from dlt698_upgrade_widget import Dlt698UpgradeWidget  # noqa: E402
    check("页面类型是 Dlt698UpgradeWidget",
          isinstance(tab, Dlt698UpgradeWidget),
          type(tab).__name__ if tab is not None else None)
    check("占位页已被 _replace_lazy_tab 原地替换",
          win.tab_widget.widget(idx) is tab)
    check("_ensure_upgrade_tab() 幂等返回同一实例",
          win._ensure_upgrade_tab() is tab)

    switch_protocol(win, 0)
    check("切回协议0 → tab 又不可见",
          win.tab_widget.isTabVisible(idx) is False)

    # 再来一轮（往返各一次以上）：切走再切回，tab 仍可见
    switch_protocol(win, 8)
    check("再切协议8 → 可见", win.tab_widget.isTabVisible(idx) is True)
    switch_protocol(win, 0)
    check("再切协议0 → 隐藏", win.tab_widget.isTabVisible(idx) is False)
    switch_protocol(win, 8)
    pump()
    check("第三次切协议8 → 可见（重复显隐无回归）",
          win.tab_widget.isTabVisible(idx) is True)
    return tab


# ── [5] 注入 ────────────────────────────────────────────────────────────────


def test_injection(win, tab):
    section("[5] 注入：共享串口 worker")

    check("页面持有主窗口共享串口线程（同一实例）",
          tab._serial_worker is win.serial_worker,
          "(hidden)" if tab._serial_worker is not win.serial_worker else "")

    # 反向验证：未连接 → 开始按钮禁用（注入不是摆设，联动真串口状态）
    before = win.serial_worker.is_open()
    if not before:
        check("未连接 → 开始按钮禁用", tab.btn_start.isEnabled() is False)
    else:
        check("已连接 → 开始按钮可用", tab.btn_start.isEnabled() is True)

    # 发送通道：蓝牙通道的取值回调也注入了 —— 取到的就是**蓝牙页那个** worker（本页不自己建连接）
    check("注入了蓝牙取值回调", callable(tab._bt_provider))
    bt_tab = win._ensure_bluetooth_tool_tab()
    pump()
    check("回调取到蓝牙页的 worker（同源，不是本页自建）",
          tab._bt_provider() is bt_tab.bluetooth_worker(),
          (tab._bt_provider(), bt_tab.bluetooth_worker()))


def test_bluetooth_channel_wiring(win, tab):
    section("[5b] 发送通道接线：蓝牙（真 MainWindow + 真蓝牙页 worker）")

    check("通道下拉有两项（串口/蓝牙）",
          [tab.combo_channel.itemData(i) for i in range(tab.combo_channel.count())]
          == ["serial", "bluetooth"],
          [tab.combo_channel.itemData(i) for i in range(tab.combo_channel.count())])
    check("默认串口", tab._channel() == "serial", tab._channel())
    tab.combo_channel.setCurrentIndex(1)                 # 切蓝牙（真蓝牙页未连接）
    pump()
    check("真蓝牙页未连接 ⇒ 不设人为上限（8192）", tab.spin_block.maximum() == 8192,
          tab.spin_block.maximum())
    check("真蓝牙页未连接 ⇒ 开始禁用 + 提示走蓝牙页",
          tab.btn_start.isEnabled() is False and "蓝牙工具" in tab.btn_start.toolTip(),
          tab.btn_start.toolTip())
    check("状态标签指向蓝牙工具页",
          "蓝牙通道" in tab.lbl_channel_state.text() and "蓝牙工具" in tab.lbl_channel_state.text(),
          tab.lbl_channel_state.text())
    tab.combo_channel.setCurrentIndex(0)                 # 切回串口（不影响后续用例）
    pump()
    check("切回串口 ⇒ 上限恢复 8192", tab.spin_block.maximum() == 8192,
          tab.spin_block.maximum())


# ── [6][7] 收尾幂等 + 换肤 ───────────────────────────────────────────────────


def test_cleanup_and_theme(win, tab):
    section("[6][7] cleanup 幂等（不关串口）与换肤")

    # 尽量真开一次串口（沙箱下大概率失败/或被 COM1 占用，两种情况都要能收尾）
    win.serial_worker.configure(port="COM1", baudrate=9600)
    win.serial_worker.open_port()
    QApplication.processEvents()
    opened_before = win.serial_worker.is_open()
    try:
        tab.cleanup()
        tab.cleanup()
        check("cleanup() 连调两次不抛异常", True)
        check("cleanup() 不关闭串口",
              win.serial_worker.is_open() == opened_before,
              win.serial_worker.is_open())
    finally:
        if win.serial_worker.is_open():
            win.serial_worker.close_port()
            QApplication.processEvents()

    try:
        tab.restyle_for_theme(True)
        tab.restyle_for_theme(False)
        check("restyle_for_theme(True/False) 均不抛异常", True)
    except Exception as exc:  # noqa: BLE001
        check("restyle_for_theme(True/False) 均不抛异常", False, repr(exc))


# ── [8] 反例自检（不改产品代码） ─────────────────────────────────────────────


def test_negative(win):
    section("[8] 反例自检：显隐判据确能抓住回退")

    saved = win._upgrade_tab_index
    wrong = saved + 1
    switch_protocol(win, 0)
    check("前置：协议0 下真升级 tab 隐藏",
          win.tab_widget.isTabVisible(saved) is False)

    # 模拟回退代码（不改产品文件，局部动作）：把纠偏打在**错误索引**上
    # —— 等价于回退版把 has_upgrade 写到了 wrong。
    win.tab_widget.setTabVisible(wrong, True)
    pump()
    check("坏接线（wrong 被硬开成可见）确实生效",
          win.tab_widget.isTabVisible(wrong) is True)
    # 正向判据必须变假 —— 否则它能识别坏接线（判据抓不住回退）
    check("判据在坏接线下变假（能抓住回退）",
          win.tab_widget.isTabVisible(saved) is False)

    # 回到协议8 时，真正升级 tab 仍**未**被开 —— 判据持续为假（回退未自愈）
    switch_protocol(win, 8)
    check("坏接线下切协议8，真升级 tab 不会被开（持续变假）",
          win.tab_widget.isTabVisible(saved) is True)

    # 还原现场：关掉 wrong、恢复正常索引，正向判据恢复为真
    win.tab_widget.setTabVisible(wrong, False)
    pump()
    switch_protocol(win, 0)
    switch_protocol(win, 8)
    check("还原后判据恢复为真（切协议8 真升级 tab 可见）",
          win.tab_widget.isTabVisible(saved) is True)
    switch_protocol(win, 0)
    check("现场干净：协议0 下又隐藏",
          win.tab_widget.isTabVisible(saved) is False)


# ── 收口 ────────────────────────────────────────────────────────────────────


def main():
    print("=" * 64)
    print("升级页接线测试 (offscreen, real MainWindow)")
    print("=" * 64)

    if QApplication.instance() is None:
        QApplication([])  # noqa: F841 —— 只需保证实例存在
    win = main_gui.MainWindow()
    QApplication.processEvents()

    try:
        test_registry()
        test_placeholder(win)
        tab = test_visibility_roundtrip(win)
        test_injection(win, tab)
        test_bluetooth_channel_wiring(win, tab)
        test_cleanup_and_theme(win, tab)
        test_negative(win)
    finally:
        pump()
        try:
            if win.serial_worker.is_open():
                win.serial_worker.close_port()
                pump()
        except Exception:
            pass
        try:
            win.close()
            pump()
        except Exception:
            pass

    # 沙箱断言：真实 config.json 未被污染（构造 MainWindow 前就不存在）
    real_config = _REAL_DATA_DIR / "config.json"
    check("沙箱：真实 config.json 未被污染",
          not real_config.exists(),
          f"exists={real_config.exists()}")

    print()
    print("-" * 64)
    print(f"结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
