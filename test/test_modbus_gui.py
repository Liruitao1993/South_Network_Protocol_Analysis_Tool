# -*- coding: utf-8 -*-
"""Modbus（协议15）GUI 回归：顶栏寄存器列表下拉 + 查询页面板 + 管理对话框。

验证：
1. 协议15 下顶栏「寄存器列表」下拉与「管理…」可见，查询页标题为「寄存器列表」；
2. 默认「通用解析」⇒ 表格里没有品牌语义（只有「寄存器 0x0000」这种通用行）；
3. 选择某份寄存器列表后**自动重解析**，表格出现品牌寄存器名与换算后的工程量；
4. 选择结果落盘到 modbus_registers.json（selected 字段）；
5. 管理对话框能读取/保存寄存器列表，保存后主窗口下拉即时刷新；
6. 切回其它协议后相关控件隐藏。

运行: python test/test_modbus_gui.py
"""

from __future__ import annotations

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
    patch.object(
        QMessageBox, _name,
        staticmethod(lambda *a, _n=_name, **k: DIALOGS.append((_n, a[2] if len(a) > 2 else ""))),
    ).start()

import _config_sandbox  # noqa: E402

SANDBOX = Path(_config_sandbox.install())

import modbus_core as mc  # noqa: E402
import modbus_register_store as store  # noqa: E402

STORE_PATH = SANDBOX / "modbus_registers.json"
store.set_store_path(STORE_PATH)

import main_gui  # noqa: E402
from modbus_register_widget import ModbusRegisterDialog, ModbusRegisterPanel  # noqa: E402

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


def _names(win):
    table = win.result_table_widget
    names = []
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        names.append(item.text() if item is not None else "")
    return names


def _frame(body_hex: str) -> str:
    body = bytes.fromhex(body_hex)
    return (body + mc.crc16_bytes(body)).hex().upper()


def test_modbus_gui(app):
    win = main_gui.MainWindow()
    win.resize(1400, 900)
    win.show()
    for _ in range(4):
        app.processEvents()

    win.protocol_combo.setCurrentIndex(15)
    for _ in range(3):
        app.processEvents()

    check("顶栏寄存器列表下拉可见", win.modbus_profile_combo.isVisible())
    check("顶栏「管理…」按钮可见", win.modbus_manage_btn.isVisible())
    check(
        "下拉含通用解析 + 内置示例",
        win.modbus_profile_combo.count() >= 3
        and win.modbus_profile_combo.itemData(0) == "",
        [win.modbus_profile_combo.itemText(i) for i in range(win.modbus_profile_combo.count())],
    )
    check("默认选择通用解析", (win.modbus_profile_combo.currentData() or "") == "")

    panel = getattr(win, "modbus_lookup_panel", None)
    check("查询页创建寄存器列表面板", isinstance(panel, ModbusRegisterPanel))
    check(
        "查询页标题为「寄存器列表」",
        win.tab_widget.tabText(win.tab_widget.indexOf(win.protocol_lookup_tab)) == "寄存器列表",
    )

    # 通用解析：只有通用行
    win.single_input.setPlainText(_frame("010304006400C8"))
    win.parse_single()
    app.processEvents()
    names = _names(win)
    check("通用模式出现寄存器行", any("寄存器 0x0000" in name for name in names), names)
    check("通用模式无品牌语义", not any("A相电压" in name for name in names), names)

    # 选择示例寄存器列表 → 自动重解析
    index = win.modbus_profile_combo.findData("example-single-phase")
    check("内置示例存在", index > 0)
    win.modbus_profile_combo.setCurrentIndex(index)
    for _ in range(3):
        app.processEvents()
    names = _names(win)
    check("切换后出现品牌寄存器名", any("A相电压" in name for name in names), names)
    check("换算后的工程量出现", any("10 V" in str(win.result_table_widget.item(r, 2).text())
                                 for r in range(win.result_table_widget.rowCount())
                                 if win.result_table_widget.item(r, 2) is not None), names)
    check("选中项落盘", store.selected_id() == "example-single-phase")
    check(
        "配置文件写入 selected",
        '"selected": "example-single-phase"' in STORE_PATH.read_text(encoding="utf-8"),
    )

    # 查询页下拉与顶栏同步
    if isinstance(panel, ModbusRegisterPanel):
        check("查询页下拉与顶栏一致", panel.current_id() == "example-single-phase")

    # 管理对话框：读取 + 保存
    dialog = ModbusRegisterDialog(win, select_id="example-single-phase")
    check("对话框加载寄存器行", dialog.table.rowCount() == 8, dialog.table.rowCount())
    regs = dialog._collect_registers(strict=True)
    check("对话框读取寄存器条目", len(regs) == 8 and regs[0]["addr"] == 0)

    dialog.name_edit.setText("GUI 测试表")
    dialog.table.item(0, 1).setText("电压（改名）")
    DIALOGS.clear()
    dialog._on_save()
    app.processEvents()
    saved = store.get_profile("example-single-phase")
    check("保存后名称更新", saved is not None and saved["name"] == "GUI 测试表")
    check("保存后寄存器名更新", saved["registers"][0]["name"] == "电压（改名）")
    check("保存成功提示", any(name == "information" for name, _ in DIALOGS), DIALOGS)
    dialog.close()

    # 主窗口刷新（对话框关闭后会调用）
    win._on_modbus_profiles_changed()
    app.processEvents()
    labels = [win.modbus_profile_combo.itemText(i) for i in range(win.modbus_profile_combo.count())]
    check("主窗口下拉刷新到新名称", any("GUI 测试表" in label for label in labels), labels)

    # 切回南网：控件隐藏
    win.protocol_combo.setCurrentIndex(0)
    for _ in range(3):
        app.processEvents()
    check("切回其它协议后下拉隐藏", not win.modbus_profile_combo.isVisible())
    check("切回其它协议后管理按钮隐藏", not win.modbus_manage_btn.isVisible())

    win.close()


def run_all():
    app = QApplication.instance() or QApplication([])
    failures = 0
    try:
        test_modbus_gui(app)
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"ERR   test_modbus_gui: {type(exc).__name__}: {exc}")
    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    return 1 if (FAIL or failures) else 0


if __name__ == "__main__":
    code = run_all()
    sys.stdout.flush()
    os._exit(code)
