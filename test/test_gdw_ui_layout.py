# -*- coding: utf-8 -*-
"""国网协议测试页（协议7）顶部参数区的整洁度回归。

覆盖
----
1. **串口状态只用一个图标 + 颜色**（用户口径 2026-10-28）：不占版面写长句；
   完整文案（端口/波特率在哪设、蓝牙要怎么连）留在 tooltip。
2. **折叠分层**：「地址与模块标识」这类装好不动的默认收起，
   「组网参数」这类现场要改的默认展开；折叠状态随存档保存/恢复。
3. **常驻项不折叠**：发送通道、序列号、超时、重试、两个清理按钮始终可见。
4. **组网参数逐行对齐**：从节点地址/协议宽度一致，操作按钮贴右。

跑法：``python test/test_gdw_ui_layout.py``（需要 offscreen Qt）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import _config_sandbox

    _config_sandbox.install()
except Exception:
    pass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402

import collapsible_section  # noqa: E402
import gdw_test_widget as W  # noqa: E402

FAILED = []
CHECKS = [0]


def section(title):
    print(f"\n-- {title} " + "-" * max(0, 62 - len(title)))


def check(name, got, want):
    CHECKS[0] += 1
    if got == want:
        print(f"  [OK] {name}")
        return True
    FAILED.append(f"{name}\n    got  = {got!r}\n    want = {want!r}")
    print(f"  [NG] {name}  -> {got!r}")
    return False


def check_true(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        print(f"  [OK] {name}")
        return True
    FAILED.append(f"{name}\n    detail = {detail!r}")
    print(f"  [NG] {name}  detail={detail!r}")
    return False


def _icon_colors(pixmap):
    """pixmap 里所有不透明像素的颜色集合（用来断言图标是绿/红）。"""
    image = pixmap.toImage()
    seen = set()
    for y in range(image.height()):
        for x in range(image.width()):
            color = QColor(image.pixelColor(x, y))
            if color.alpha() > 0:
                seen.add(color.name().lower())
    return seen


def _is_inside(widget, ancestor) -> bool:
    node = widget.parentWidget()
    while node is not None:
        if node is ancestor:
            return True
        node = node.parentWidget()
    return False


def test_channel_icon():
    section("[1] 串口状态 = 一个图标 + 颜色（文字只进 tooltip）")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()

    w._on_channel_state("串口通道：未连接（端口/波特率在顶部「串口配置」设置）", False)
    app.processEvents()
    down_pm = w.lbl_channel_state.pixmap()
    down_colors = _icon_colors(down_pm)
    check("未连接：标签不写长文案", w.lbl_channel_state.text(), "")
    check_true("未连接：完整文案进 tooltip",
               "串口配置" in w.lbl_channel_state.toolTip(),
               w.lbl_channel_state.toolTip())
    check_true("未连接：图标为红色",
               any(c in down_colors for c in ("#b42318",)) or
               any(c.startswith("#b4") or c.startswith("#b5") for c in down_colors),
               sorted(down_colors))

    w._on_channel_state("串口通道：已连接（COM10，115200 8E1）", True)
    app.processEvents()
    up_pm = w.lbl_channel_state.pixmap()
    up_colors = _icon_colors(up_pm)
    check_true("已连接：图标为绿色",
               any(c.startswith("#19") or c.startswith("#1a") for c in up_colors),
               sorted(up_colors))
    check_true("已连接/未连接用的是不同图标（像素不同）",
               up_pm.toImage() != down_pm.toImage(), "两张图标完全一致")
    check_true("已连接：tooltip 跟随最新状态",
               "115200" in w.lbl_channel_state.toolTip(), w.lbl_channel_state.toolTip())
    w.close()


def test_sections():
    section("[2] 折叠分层：固定项收起、现场要改的展开")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    by_key = {s.key: s for s in w._sections}
    check("折叠区共两处", sorted(by_key), ["gdw_params_addr", "gdw_params_network"])
    check("「地址与模块标识」默认收起", by_key["gdw_params_addr"].is_expanded(), False)
    check("收起时内容确实隐藏", by_key["gdw_params_addr"].is_content_hidden(), True)
    check("「组网参数」默认展开", by_key["gdw_params_network"].is_expanded(), True)
    check("展开时内容可见", by_key["gdw_params_network"].is_content_hidden(), False)
    check_true("折叠区标题写明用途",
               "地址" in by_key["gdw_params_addr"].title()
               and "组网参数" in by_key["gdw_params_network"].title(),
               (by_key["gdw_params_addr"].title(), by_key["gdw_params_network"].title()))

    # 地址类控件在折叠区里，常驻控件不在
    addr_sec = by_key["gdw_params_addr"]
    check_true("源地址在折叠区内", _is_inside(w.edit_src, addr_sec), w.edit_src.parent())
    check_true("模块标识在折叠区内", _is_inside(w.combo_module, addr_sec))
    net_sec = by_key["gdw_params_network"]
    check_true("从节点地址在组网折叠区内", _is_inside(w.node_widgets[0]["addr"], net_sec))
    check_true("「准备测试网络」在组网区内", _is_inside(w.btn_preflight, net_sec))
    w.close()


def test_common_row_always_visible():
    section("[3] 常驻项不折叠（通道 / 序号 / 超时 / 重试 / 清理）")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    addr_sec = next(s for s in w._sections if s.key == "gdw_params_addr")
    for name, widget in (("发送通道", w.combo_channel), ("序列号", w.spin_seq),
                         ("超时", w.spin_timeout), ("重试", w.spin_retries),
                         ("清空日志/报文", w.btn_clear), ("清理所有参数", w.btn_clear_params),
                         ("通道状态图标", w.lbl_channel_state)):
        check_true(f"{name} 不在折叠区内（始终可见）",
                   not _is_inside(widget, addr_sec) and not _is_inside(widget, w.network_section),
                   widget.parent())
    # 数字不被步进按钮压住：宽度要容得下 3~4 位 + 单位后缀
    check_true("序列号框宽度够放 255", w.spin_seq.width() >= 90, w.spin_seq.width())
    check_true("超时框宽度够放 60000 ms", w.spin_timeout.width() >= 100, w.spin_timeout.width())
    w.close()


def test_network_rows_aligned():
    section("[4] 组网参数逐行对齐（同一行标签紧贴控件）")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    w.show()
    app.processEvents()
    widths = {(n["addr"].width(), n["proto"].width()) for n in w.node_widgets}
    check("两个从节点的地址/协议宽度一致", len(widths), 1)
    for idx, node in enumerate(w.node_widgets):
        check_true(f"从节点{idx + 1} 地址框够放 12 位", node["addr"].width() >= 110,
                   node["addr"].width())
        check_true(f"从节点{idx + 1} 协议框够放协议名", node["proto"].width() >= 120,
                   node["proto"].width())
    # 每行独立布局：从节点2 的标签不该被从节点1 的列宽推开（x 坐标接近）
    rows = [n["addr"].mapTo(w, n["addr"].rect().topLeft()).x() for n in w.node_widgets]
    check_true("两行地址框左边缘对齐", abs(rows[0] - rows[1]) <= 2, rows)
    # 操作按钮贴右
    check_true("「准备测试网络」不在组网区最左侧",
               w.btn_preflight.mapTo(w, w.btn_preflight.rect().topLeft()).x() > w.width() * 0.6,
               (w.btn_preflight.mapTo(w, w.btn_preflight.rect().topLeft()).x(), w.width()))
    w.close()


def test_persist():
    section("[5] 折叠状态随存档保存/恢复")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    addr_sec = next(s for s in w._sections if s.key == "gdw_params_addr")
    net_sec = w.network_section

    addr_sec.set_expanded(True)
    net_sec.set_expanded(False)
    app.processEvents()
    state = w._collect_settings().get("sections")
    check("存档写出两处折叠状态",
          state, {"gdw_params_addr": True, "gdw_params_network": False})

    # 新实例按存档恢复（不落盘，直接套用到新建控件）
    w2 = W.GdwTestWidget()
    applied = collapsible_section.apply_state(w2._sections, state)
    check("恢复命中的 key", sorted(applied), ["gdw_params_addr", "gdw_params_network"])
    by_key2 = {s.key: s for s in w2._sections}
    check("恢复后地址区展开", by_key2["gdw_params_addr"].is_expanded(), True)
    check("恢复后组网区收起", by_key2["gdw_params_network"].is_expanded(), False)
    check("恢复不会把内容搞反（收起的确实隐藏）",
          by_key2["gdw_params_network"].is_content_hidden(), True)

    # 坏数据不能让界面打不开
    bad = collapsible_section.apply_state(w2._sections, {"gdw_params_addr": "???", "x": 1})
    check("非法状态被跳过而不抛异常", bad, [])
    w.close()
    w2.close()


def test_sta_serial_persist():
    section("[6] 从节点模拟（虚拟表）串口参数随配置存档")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    w.combo_sta_port.clear()
    w.combo_sta_port.addItem("COM5")
    w.combo_sta_port.setCurrentText("COM5")
    w.combo_sta_baud.setCurrentText("9600")
    w.combo_sta_parity.setCurrentText("E")
    w.combo_sta_stop.setCurrentText("2")
    app.processEvents()

    settings = w._collect_settings()
    check("串口写进配置（端口/波特率/校验/停止位）",
          (settings.get("sta_port"), settings.get("sta_baud"),
           settings.get("sta_parity"), settings.get("sta_stop")),
          ("COM5", "9600", "E", "2"))

    # 落盘再开一个新实例：参数要恢复（现场固定 COM5 9600 E 1，不该每次重选）
    w._save_persisted()
    w2 = W.GdwTestWidget()
    app.processEvents()
    check("重开后串口参数恢复",
          (w2.combo_sta_baud.currentText(), w2.combo_sta_parity.currentText(),
           w2.combo_sta_stop.currentText()),
          ("9600", "E", "2"))
    check("重开后端口恢复（含当前未插上的口）", w2.combo_sta_port.currentText(), "COM5")

    # 「刷新」不能把已选端口重置成列表第一个
    w2._refresh_sta_ports()
    check("刷新串口列表后仍保留已选端口", w2.combo_sta_port.currentText(), "COM5")
    w.close()
    w2.close()


def test_flow_step_history():
    section("[7] 跑完的用例点回去能看到逐步结果（不再全「待执行」）")
    import gdw_test_flows as F

    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    w._select_page(__import__("gdw_test_core").PAGE_FLOW, notify=True)
    app.processEvents()

    # 还没跑过：全部待执行
    w._on_flow_case_selected("identify")
    app.processEvents()
    check("未跑过的用例全是待执行", w.flow_table.item(1, 2).text(), "待执行")

    # 模拟一次失败执行后的快照
    w._flow_history["identify"] = {
        "states": ["ok", "fail", "skip", "ok", "ok"],
        "notes": ["", "超时（60s）", "", "", ""],
        "current": -1,
    }
    w._set_flow_result("identify", "失败")
    w._on_flow_case_selected("identify")
    app.processEvents()
    check("第 1 步回显通过", w.flow_table.item(0, 2).text(), "✓ 通过")
    check("第 2 步回显失败", w.flow_table.item(1, 2).text(), "✗ 失败")
    check("失败原因一起回显", w.flow_table.item(1, 3).text(), "超时（60s）")
    check("第 3 步回显跳过", w.flow_table.item(2, 2).text(), "跳过")
    check("树第三列仍是失败", w._flow_result_of("identify"), "✗ 失败")

    # 历史里的「执行中」不能残留成永远转圈
    w._flow_history["archive"] = {"states": ["running", "pending"], "notes": ["", ""], "current": -1}
    w._on_flow_case_selected("archive")
    app.processEvents()
    check("非当前步的「执行中」回显为待执行", w.flow_table.item(0, 2).text(), "待执行")

    # 步骤数变了（流程改过）也不能崩，多出的按待执行
    w._flow_history["broadcast"] = {"states": ["ok"], "notes": [""], "current": -1}
    w._on_flow_case_selected("broadcast")
    app.processEvents()
    check_true("步骤数 > 历史长度时按待执行补齐",
               w.flow_table.rowCount() == len(F.flow_case("broadcast").steps)
               and w.flow_table.item(1, 2).text() == "待执行",
               (w.flow_table.rowCount(), w.flow_table.item(1, 2).text()))
    w.close()


def test_flow_run_order():
    section("[8] 全选流程用例按「自上而下」顺序执行（不能倒序）")
    import gdw_test_core as core
    import gdw_test_flows as F

    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    w._select_page(core.PAGE_FLOW, notify=True)
    app.processEvents()
    w._set_all_checked(True)
    app.processEvents()

    tree_order = [c.name for c in F.FLOW_CASES]          # 用例定义的界面顺序
    cases = w._flow_selected_cases()
    check("全选后 9 条都进来了", len(cases), 9)
    check("执行顺序 = 界面自上而下", [c.name for c in cases], tree_order)

    # 勾选记录的保存顺序也要正序（以前是 LIFO 栈导致的倒序）
    checked = w._checked.get(core.PAGE_FLOW, [])
    check("勾选记录顺序 = 用例定义顺序",
          checked, [c.fid for c in F.FLOW_CASES])

    # 只勾中间两条：仍按树序执行
    w._set_all_checked(False)
    for fid in ("meter_read", "identify"):               # 故意倒着勾
        leaf = w._find_leaf(w._trees[core.PAGE_FLOW], fid)
        leaf.setCheckState(0, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.CheckState.Checked)
    app.processEvents()
    picked = [c.fid for c in w._flow_selected_cases()]
    check("勾选顺序不影响执行顺序（按树序）", picked, ["identify", "meter_read"])
    w.close()


def main():
    test_channel_icon()
    test_sections()
    test_common_row_always_visible()
    test_network_rows_aligned()
    test_persist()
    test_sta_serial_persist()
    test_flow_step_history()
    test_flow_run_order()

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项 / 通过 {CHECKS[0] - len(FAILED)} 项：")
        for item in FAILED:
            print(f"  - {item}")
        raise SystemExit(1)
    print(f"全部通过（{CHECKS[0]} 项）")


if __name__ == "__main__":
    main()
    os._exit(0)
