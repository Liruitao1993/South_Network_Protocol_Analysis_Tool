"""顶部栏「协议选择 / 串口配置」折叠测试（1.23.41）

覆盖：
  [1] 默认展开：两组 toggle 勾选、GroupBox 可见、标题无协议名、状态栏串口标签隐藏
  [2] 折叠协议：GroupBox 隐藏、标题中间出现当前协议名、展开后恢复默认标题
  [3] 折叠串口：GroupBox 隐藏、状态栏标签显示端口/波特率/校验/状态；展开后隐藏
  [4] 协议切换：折叠态下切协议，标题中间协议名跟随
  [5] 配置往返：折叠态 _save_app_config → 新实例恢复折叠 + 标题/状态栏
  [6] 状态同步：改串口下拉 / 连接状态文案 → 状态栏文本跟随
  [7] 不写入 ui 段（防 ThemeManager.to_config 整体重建时丢失）

运行：
    python test/test_top_bar_collapse.py
"""

import os

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json  # noqa: E402
import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402
import main_gui  # noqa: E402
import protocol_registry  # noqa: E402
from main_gui import APP_VERSION, BUILD_DATE, MainWindow  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

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
    print(f"\n== {title} ==")


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def make_win():
    _app()
    return MainWindow()


BASE = f"协议解析工具 v{APP_VERSION} ({BUILD_DATE})"
DEFAULT_TITLE = f"{BASE} - 作者: liruitao"


def main():
    tmp = _config_sandbox.install()
    config_path = tmp / "config.json"

    section("[1] 默认展开")
    win = make_win()
    check(
        "协议 toggle 默认勾选(展开)",
        win.proto_toggle_btn.isChecked(),
        f"checked={win.proto_toggle_btn.isChecked()}",
    )
    check(
        "串口 toggle 默认勾选(展开)",
        win.serial_toggle_btn.isChecked(),
    )
    check(
        "协议 Group 默认可见",
        not win.proto_group.isHidden(),
        f"hidden={win.proto_group.isHidden()}",
    )
    check(
        "串口 Group 默认可见",
        not win.serial_group.isHidden(),
    )
    check(
        "展开态标题无协议名",
        win.windowTitle() == DEFAULT_TITLE,
        win.windowTitle(),
    )
    check(
        "展开态状态栏串口标签隐藏",
        win._serial_statusbar_lbl.isHidden(),
    )

    section("[2] 折叠协议 → 窗口标题中间")
    win.proto_toggle_btn.setChecked(False)
    win._toggle_proto_group()
    short0 = protocol_registry.get_protocol(win.protocol_combo.currentIndex()).short_name
    expect_title = f"{BASE} · {short0} · 作者: liruitao"
    check("折叠后协议 Group 隐藏", win.proto_group.isHidden())
    check(
        "标题中间显示协议短名",
        win.windowTitle() == expect_title,
        f"got={win.windowTitle()!r} expect={expect_title!r}",
    )
    check("折叠按钮文案 ▶", "▶" in win.proto_toggle_btn.text())
    check("标题用短名而非下拉全名", short0 in win.windowTitle() and "[0]" not in win.windowTitle(), win.windowTitle())

    win.proto_toggle_btn.setChecked(True)
    win._toggle_proto_group()
    check("展开后协议 Group 恢复", not win.proto_group.isHidden())
    check(
        "展开后标题恢复默认",
        win.windowTitle() == DEFAULT_TITLE,
        win.windowTitle(),
    )

    section("[3] 折叠串口 → 状态栏")
    win.serial_toggle_btn.setChecked(False)
    win._toggle_serial_group()
    lbl = win._serial_statusbar_lbl
    check("折叠后串口 Group 隐藏", win.serial_group.isHidden())
    check("折叠后状态栏标签可见", not lbl.isHidden())
    text = lbl.text()
    check("状态栏含 串口:", text.startswith("串口:"), text)
    check("状态栏含波特率", win.serial_baud_combo.currentText() in text, text)
    check("状态栏含校验", win.serial_parity_combo.currentText() in text, text)

    win.serial_toggle_btn.setChecked(True)
    win._toggle_serial_group()
    check("展开后状态栏串口标签隐藏", lbl.isHidden())

    section("[4] 协议切换时标题跟随（折叠态）")
    win.proto_toggle_btn.setChecked(False)
    win._toggle_proto_group()
    # 切到国网协议（索引 7）
    win.protocol_combo.setCurrentIndex(7)
    _app().processEvents()
    short7 = protocol_registry.get_protocol(7).short_name
    expect7 = f"{BASE} · {short7} · 作者: liruitao"
    check(
        "切协议后标题中间更新",
        win.windowTitle() == expect7,
        f"got={win.windowTitle()!r}",
    )
    # 切回南网
    win.protocol_combo.setCurrentIndex(0)
    _app().processEvents()
    short0b = protocol_registry.get_protocol(0).short_name
    check(
        "再切回协议标题仍跟随",
        win.windowTitle() == f"{BASE} · {short0b} · 作者: liruitao",
        win.windowTitle(),
    )

    section("[5] 配置往返：折叠态持久化")
    # 保持：协议折叠 + 串口折叠
    if win.proto_toggle_btn.isChecked():
        win.proto_toggle_btn.setChecked(False)
        win._toggle_proto_group()
    if win.serial_toggle_btn.isChecked():
        win.serial_toggle_btn.setChecked(False)
        win._toggle_serial_group()
    win._save_app_config()
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    top_bar = cfg.get("top_bar", {})
    check("config.top_bar.proto_collapsed=True", top_bar.get("proto_collapsed") is True, top_bar)
    check("config.top_bar.serial_collapsed=True", top_bar.get("serial_collapsed") is True, top_bar)
    check(
        "折叠状态未写入 ui 段",
        "proto_collapsed" not in cfg.get("ui", {})
        and "serial_collapsed" not in cfg.get("ui", {}),
        str(cfg.get("ui", {}).keys()),
    )
    win.close()
    win.deleteLater()
    _app().processEvents()

    win2 = make_win()
    check("新实例协议 toggle 折叠", not win2.proto_toggle_btn.isChecked())
    check("新实例串口 toggle 折叠", not win2.serial_toggle_btn.isChecked())
    check("新实例协议 Group 隐藏", win2.proto_group.isHidden())
    check("新实例串口 Group 隐藏", win2.serial_group.isHidden())
    short_new = protocol_registry.get_protocol(
        win2.protocol_combo.currentIndex()
    ).short_name
    check(
        "新实例标题含协议短名",
        short_new in win2.windowTitle() and "·" in win2.windowTitle(),
        win2.windowTitle(),
    )
    check(
        "新实例状态栏串口可见",
        not win2._serial_statusbar_lbl.isHidden(),
        win2._serial_statusbar_lbl.text(),
    )

    section("[6] 状态同步：改串口参数 / 连接文案")
    win2.serial_baud_combo.setCurrentText("115200")
    check(
        "改波特率后状态栏跟随",
        "115200" in win2._serial_statusbar_lbl.text(),
        win2._serial_statusbar_lbl.text(),
    )
    win2.serial_status_label.setText("已连接")
    win2._update_serial_statusbar()
    check(
        "连接状态进入状态栏",
        "已连接" in win2._serial_statusbar_lbl.text(),
        win2._serial_statusbar_lbl.text(),
    )
    win2.serial_status_label.setText("错误: test")
    win2._on_serial_error("test")
    check(
        "错误状态进入状态栏",
        "错误" in win2._serial_statusbar_lbl.text(),
        win2._serial_statusbar_lbl.text(),
    )

    section("[7] 展开串口后状态栏隐藏 + 配置恢复展开")
    win2.serial_toggle_btn.setChecked(True)
    win2._toggle_serial_group()
    check("展开串口后状态栏隐藏", win2._serial_statusbar_lbl.isHidden())
    win2.proto_toggle_btn.setChecked(True)
    win2._toggle_proto_group()
    check(
        "展开协议后标题恢复",
        win2.windowTitle() == DEFAULT_TITLE,
        win2.windowTitle(),
    )
    win2._save_app_config()
    cfg2 = json.loads(config_path.read_text(encoding="utf-8"))
    top2 = cfg2.get("top_bar", {})
    check("展开态写回 collapsed=False", top2.get("proto_collapsed") is False and top2.get("serial_collapsed") is False, top2)

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    win2.close()
    code = 0 if FAIL == 0 else 1
    sys.stdout.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
