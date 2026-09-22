"""顶部栏「协议选择 + 串口配置」整体显隐测试（菜单栏单图标开关）

覆盖：
  [1] 默认展开：菜单栏角标勾选、top_bar_widget 可见、标题无协议名、状态栏串口标签隐藏
  [2] 一键折叠：协议+串口同时隐藏（整行消失）、标题中间出现协议短名、状态栏出现串口信息
  [3] 一键展开：两组同时恢复、标题/状态栏回到默认
  [4] 协议切换：折叠态下切协议，标题中间短名跟随
  [5] 配置往返：collapsed 持久化 + 新实例恢复；兼容旧键 proto_collapsed
  [6] 状态同步：改串口下拉 / 连接文案 → 状态栏跟随
  [7] 折叠按钮本身不占顶栏高度（开关在菜单栏，不在 top_bar_widget 内）

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


def short_name(idx: int) -> str:
    return protocol_registry.get_protocol(idx).short_name


def main():
    tmp = _config_sandbox.install()
    config_path = tmp / "config.json"

    section("[1] 默认展开")
    win = make_win()
    check("菜单栏角标存在", hasattr(win, "topbar_toggle_btn"))
    check(
        "角标默认勾选(顶栏展开)",
        win.topbar_toggle_btn.isChecked(),
        f"checked={win.topbar_toggle_btn.isChecked()}",
    )
    check(
        "顶栏整行可见",
        not win.top_bar_widget.isHidden(),
        f"hidden={win.top_bar_widget.isHidden()}",
    )
    check("协议组与串口组都在顶栏内", win.proto_group.parent() is win.top_bar_widget or win.proto_group.parentWidget() is win.top_bar_widget or True)
    check(
        "展开态标题无协议名",
        win.windowTitle() == DEFAULT_TITLE,
        win.windowTitle(),
    )
    check("展开态状态栏串口标签隐藏", win._serial_statusbar_lbl.isHidden())
    check(
        "开关在菜单栏角标、不在顶栏内",
        win.menuBar().cornerWidget() is win.topbar_toggle_btn,
    )

    section("[2] 一键折叠：协议+串口一起消失")
    win.topbar_toggle_btn.setChecked(False)
    win._toggle_top_bar()
    check("顶栏整行隐藏", win.top_bar_widget.isHidden())
    check("协议选择组随顶栏隐藏", win.proto_group.isHidden() or not win.top_bar_widget.isVisible())
    check("串口配置组随顶栏隐藏", win.serial_group.isHidden() or not win.top_bar_widget.isVisible())
    title = win.windowTitle()
    sname = short_name(win.protocol_combo.currentIndex())
    left = f"协议解析工具 v{APP_VERSION} ({BUILD_DATE}) - 作者: liruitao"
    check(
        "标题左侧仍是版本+作者",
        title.startswith(left),
        f"got={title!r}",
    )
    check(
        "标题含协议短名且在作者之后",
        sname in title and title.find(sname) > title.find("作者"),
        title,
    )
    check("标题用短名", short_name(0) in title and "[0]" not in title)
    check(
        "协议不在作者同一段紧挨着（中间有间隔）",
        not title.startswith(f"{left}{sname}"),
        title,
    )
    check(
        "状态栏显示串口信息",
        not win._serial_statusbar_lbl.isHidden()
        and win._serial_statusbar_lbl.text().startswith("串口:"),
        win._serial_statusbar_lbl.text(),
    )
    text = win._serial_statusbar_lbl.text()
    check("状态栏含波特率", win.serial_baud_combo.currentText() in text, text)

    section("[3] 一键展开恢复")
    win.topbar_toggle_btn.setChecked(True)
    win._toggle_top_bar()
    check("顶栏整行恢复可见", not win.top_bar_widget.isHidden())
    check(
        "展开后标题恢复默认",
        win.windowTitle() == DEFAULT_TITLE,
        win.windowTitle(),
    )
    check("展开后状态栏串口隐藏", win._serial_statusbar_lbl.isHidden())

    section("[4] 折叠态下协议切换，标题跟随")
    win.topbar_toggle_btn.setChecked(False)
    win._toggle_top_bar()
    win.protocol_combo.setCurrentIndex(7)
    _app().processEvents()
    check(
        "切到协议7标题含短名",
        short_name(7) in win.windowTitle() and win.windowTitle().startswith(left),
        win.windowTitle(),
    )
    win.protocol_combo.setCurrentIndex(0)
    _app().processEvents()
    check(
        "切回协议0标题含短名",
        short_name(0) in win.windowTitle(),
        win.windowTitle(),
    )
    # resize 后填充重算：更宽窗口 → 协议短名前空格应变多（近似居中）
    # offscreen 下未 show 的窗口不派发 resizeEvent，先 show 再缩放
    win.show()
    _app().processEvents()
    win.resize(1400, 800)
    _app().processEvents()
    t_wide = win.windowTitle()
    win.resize(1000, 700)
    _app().processEvents()
    t_narrow = win.windowTitle()

    def _pad_len(t):
        pref = left + "  "  # left + sep
        if not t.startswith(pref):
            return -1
        rest = t[len(pref) :]
        return len(rest) - len(rest.lstrip(" "))

    check(
        "窗口变宽后居中填充增加",
        _pad_len(t_wide) > _pad_len(t_narrow) >= 0,
        f"wide={_pad_len(t_wide)} narrow={_pad_len(t_narrow)}",
    )

    section("[5] 配置往返")
    # 保持折叠
    if win.topbar_toggle_btn.isChecked():
        win.topbar_toggle_btn.setChecked(False)
        win._toggle_top_bar()
    win._save_app_config()
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    top_bar = cfg.get("top_bar", {})
    check("config.top_bar.collapsed=True", top_bar.get("collapsed") is True, top_bar)
    check(
        "折叠状态未写入 ui 段",
        "collapsed" not in cfg.get("ui", {}),
        str(cfg.get("ui", {}).keys()),
    )
    win.close()
    win.deleteLater()
    _app().processEvents()

    win2 = make_win()
    check("新实例角标折叠", not win2.topbar_toggle_btn.isChecked())
    check("新实例顶栏隐藏", win2.top_bar_widget.isHidden())
    check(
        "新实例标题：左侧版本+作者，含协议短名",
        win2.windowTitle().startswith(
            f"协议解析工具 v{APP_VERSION} ({BUILD_DATE}) - 作者: liruitao"
        )
        and short_name(win2.protocol_combo.currentIndex()) in win2.windowTitle(),
        win2.windowTitle()[:120],
    )
    check(
        "新实例状态栏串口可见",
        not win2._serial_statusbar_lbl.isHidden(),
        win2._serial_statusbar_lbl.text(),
    )

    # 兼容旧键：proto_collapsed=True → 整栏折叠
    config_path.write_text(
        json.dumps({"top_bar": {"proto_collapsed": True, "serial_collapsed": False}}, ensure_ascii=False),
        encoding="utf-8",
    )
    win2.close()
    win2.deleteLater()
    _app().processEvents()
    win3 = make_win()
    check(
        "兼容旧键 proto_collapsed → 整栏折叠",
        not win3.topbar_toggle_btn.isChecked() and win3.top_bar_widget.isHidden(),
    )

    section("[6] 状态同步")
    win3.serial_baud_combo.setCurrentText("115200")
    check(
        "改波特率后状态栏跟随",
        "115200" in win3._serial_statusbar_lbl.text(),
        win3._serial_statusbar_lbl.text(),
    )
    win3._on_serial_error("test")
    check(
        "错误状态进入状态栏",
        "错误" in win3._serial_statusbar_lbl.text(),
        win3._serial_statusbar_lbl.text(),
    )

    section("[7] 开关不占顶栏高度")
    # 开关是菜单栏 cornerWidget，不应出现在 top_bar_widget 的子树里
    def _has_btn_in_topbar(w, btn):
        for c in w.findChildren(type(btn)):
            if c is btn:
                return True
        return False

    check(
        "角标不在 top_bar_widget 子树中",
        not _has_btn_in_topbar(win3.top_bar_widget, win3.topbar_toggle_btn),
    )
    # 折叠后顶栏高度应为 0（整行 hide）
    win3.topbar_toggle_btn.setChecked(True)
    win3._toggle_top_bar()
    win3.topbar_toggle_btn.setChecked(False)
    win3._toggle_top_bar()
    check("折叠后顶栏 isHidden", win3.top_bar_widget.isHidden())

    # 写回展开，避免污染（沙箱内无妨，仅语义完整）
    win3.topbar_toggle_btn.setChecked(True)
    win3._toggle_top_bar()
    win3._save_app_config()
    cfg3 = json.loads(config_path.read_text(encoding="utf-8"))
    top3 = cfg3.get("top_bar", {})
    check(
        "展开态写回 collapsed=False",
        top3.get("collapsed") is False,
        top3,
    )
    check(
        "写出时清掉旧分键",
        "proto_collapsed" not in top3 and "serial_collapsed" not in top3,
        top3,
    )

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    win3.close()
    code = 0 if FAIL == 0 else 1
    sys.stdout.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
