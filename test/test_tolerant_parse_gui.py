# -*- coding: utf-8 -*-
"""「校验该帧」开关的 GUI 回归（698.45 容错解析）。

验证：
1. 单帧页有「校验该帧」勾选框，协议8 下可用且默认勾选；
2. 勾选时半截帧 → 表格只有「❌ 解析失败」；
3. 取消勾选 → 按实收字节解析，表格出现头部字段与「原始报文」，且不弹错误框；
4. 切到别的协议 → 勾选框禁用；
5. 勾选状态写入 config.json 的 single_parse.verify。

运行: python test/test_tolerant_parse_gui.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

DIALOGS = []
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name,
                 staticmethod(lambda *a, _n=_name, **k: DIALOGS.append((_n, a[2] if len(a) > 2 else "")))
                 ).start()

import _config_sandbox  # noqa: E402

SANDBOX = Path(_config_sandbox.install())

import main_gui  # noqa: E402

PARTIAL_HEX = (
    "6814024305111111111111109790070100F00108000202120000098201F4F85D0920693300085DED0008AD340008E5E90008"
    "E5810008F1250108000000000000000000000000000000008D010108B993000800000000FB33000829120108953300089533"
    "000895330008BDF60008953300089533000825CC0008B9CC0008D1CC0008DDCC0008E9CC0008AD8D0008B98D0008C58D0008"
    "D18D0008DD8D0008E98D0008F58D00089533000895330008F98100080000000000000000F5CC000895330008953300089533"
    "00089533000831160108591601088D160108953300089533000895330008953300089533000895330008B11F0108BD1F0108"
    "C91F010831CC"
)

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def _table_names(win):
    table = win.result_table_widget
    names = []
    for r in range(table.rowCount()):
        item = table.item(r, 0)
        names.append(item.text() if item is not None else "")
    return names


def test_verify_checkbox(app):
    win = main_gui.MainWindow()
    win.resize(1280, 860)
    win.show()
    for _ in range(4):
        app.processEvents()

    chk = getattr(win, "verify_frame_chk", None)
    check("单帧页有「校验该帧」勾选框", chk is not None)
    if chk is None:
        win.close()
        return

    win.protocol_combo.setCurrentIndex(8)
    for _ in range(3):
        app.processEvents()
    check("协议8 下勾选框可用", chk.isEnabled())
    check("默认勾选（严格解析）", chk.isChecked())

    # 1) 勾选：半截帧 → 只有解析失败
    win.single_input.setPlainText(PARTIAL_HEX)
    win.parse_single()
    app.processEvents()
    names = _table_names(win)
    check("勾选时半截帧报解析失败",
          bool(names) and names[0].startswith("❌"), names[:3])
    check("勾选时不出现容错行", "原始报文" not in names)

    # 2) 取消勾选：容错解析
    DIALOGS.clear()
    chk.setChecked(False)
    win.parse_single()
    app.processEvents()
    names = _table_names(win)
    check("容错模式不再报整体失败", not any(n.startswith("❌") for n in names), names[:5])
    check("容错模式出现原始报文行", "原始报文" in names, names)
    check("容错模式出现头部字段",
          all(k in names for k in ("起始字符", "长度域", "控制域", "地址特征")), names[:8])
    check("容错模式没有弹错误框", not DIALOGS, DIALOGS)

    # 3) 持久化
    win._save_app_config()
    cfg = json.loads((SANDBOX / "config.json").read_text(encoding="utf-8"))
    check("取消勾选写入 config", cfg.get("single_parse", {}).get("verify") is False,
          str(cfg.get("single_parse")))

    # 4) 其它协议禁用
    win.protocol_combo.setCurrentIndex(0)
    for _ in range(3):
        app.processEvents()
    check("非 698.45 协议下勾选框禁用", not chk.isEnabled())

    # 回到 698.45：勾选状态保留（未勾选）
    win.protocol_combo.setCurrentIndex(8)
    for _ in range(3):
        app.processEvents()
    check("切回协议8 后保留未勾选状态", chk.isEnabled() and not chk.isChecked())

    win.close()


def run_all():
    app = QApplication.instance() or QApplication([])
    failures = 0
    try:
        test_verify_checkbox(app)
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"ERR   test_verify_checkbox: {type(exc).__name__}: {exc}")
    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    return 1 if (FAIL or failures) else 0


if __name__ == "__main__":
    code = run_all()
    sys.stdout.flush()
    os._exit(code)
