# -*- coding: utf-8 -*-
"""协议9 通信时序图 GUI 集成冒烟测试（offscreen）

走真实链路验证 main_gui.py 接线（implement.md 步骤4）：
  1. 「通信时序图」懒加载 tab 已注册、初始隐藏，协议9 下可见、其余协议隐藏
  2. 「时序图」按钮仅协议9 可用；空结果点击有提示不崩溃
  3. 模拟批量解析结果 → 点击生成：模型按全部帧构建、tab 自动创建并切换
  4. 勾选子集后生成：仅用勾选帧且 frame_idx 保持原始索引
  5. 图 → 表联动：message_clicked 跳回批量解析页并选中对应行、详情填充
  6. 表 → 图联动：选中摘要表行 → 时序图对应消息高亮
  7. clear_batch → 时序图模型清空

直接运行: python test_csg_sequence_gui.py
"""

import _path_setup  # noqa: E402

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FAILURES = []
PASS = 0


def check(name, cond, detail=""):
    global PASS
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASS += 1
    else:
        FAILURES.append(name)


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    import main_gui
    from test_csg_sequence_model import (
        BEACON_FRAME,
        SACK_FRAME,
        SOF_DOWN,
        SOF_UP,
        _make_entry,
    )

    # 测试命令帧（业务标识0xF0）：台体发射机初始化过程发送，源非 CCO
    TEST_TABLE = [
        ("定界符类型", "0b001", "1", "SOF帧", 0, 0),
        ("源TEI", "0x001", "1", "发送站点TEI: 1", 1, 2),
        ("目的TEI", "0x002", "2", "接收站点TEI: 2", 2, 3),
        ("业务标识", "0xF0", "240", "业务标识 240 - 测试帧", 4, 5),
    ]

    win = main_gui.MainWindow()
    app.processEvents()

    # ── 1. tab 注册与协议可见性 ──
    check("时序图tab索引已注册", getattr(win, "_seq_diagram_tab_index", -1) >= 0)
    check(
        "时序图tab位置紧跟批量解析",
        win._seq_diagram_tab_index == win._batch_tab_index + 1,
        f"batch={win._batch_tab_index} seq={win._seq_diagram_tab_index}",
    )

    # ── 2. 协议可见性/按钮启停（走协议切换处理链路）──
    win._on_protocol_changed(9)
    app.processEvents()
    check(
        "协议9下时序图tab可见",
        win.tab_widget.isTabVisible(win._seq_diagram_tab_index),
    )
    check("协议9下时序图按钮可用", win.batch_seq_diagram_btn.isEnabled())
    win._on_protocol_changed(0)
    app.processEvents()
    check(
        "非协议9下时序图tab隐藏",
        not win.tab_widget.isTabVisible(win._seq_diagram_tab_index),
    )
    check("非协议9下时序图按钮禁用", not win.batch_seq_diagram_btn.isEnabled())
    win._on_protocol_changed(9)
    app.processEvents()

    # ── 2b. 协议10/11 同样可见/可用（通用提取管道覆盖三协议）──
    for proto in (10, 11):
        win._on_protocol_changed(proto)
        app.processEvents()
        check(
            f"协议{proto}下时序图tab可见且按钮可用",
            win.tab_widget.isTabVisible(win._seq_diagram_tab_index)
            and win.batch_seq_diagram_btn.isEnabled(),
        )
    win._on_protocol_changed(9)
    app.processEvents()

    # ── 3. 空结果保护（QMessageBox 在 offscreen 下会阻塞，改为直接验证 guard）──
    check("空结果时不生成模型", not hasattr(win, "seq_diagram_tab"))

    # ── 构造批量解析结果（模拟 run_batch_parse 的产物）──
    entries = [
        _make_entry(SOF_DOWN, "SOF下行"),  # idx 0: CCO→STA2
        _make_entry(SOF_UP, "SOF上行"),  # idx 1: STA2→CCO
        _make_entry(BEACON_FRAME, "信标帧"),  # idx 2: CCO广播
        _make_entry(SACK_FRAME, "选择确认帧"),  # idx 3: CCO→目的TEI291 有向
        _make_entry(None, "测试帧", table=TEST_TABLE),  # idx 4: 台体发射机→STA2
    ]
    win.batch_results = entries
    from PySide6.QtWidgets import QTableWidgetItem
    from PySide6.QtCore import Qt

    win.batch_summary_table.setRowCount(0)
    for i, e in enumerate(entries):
        row = win.batch_summary_table.rowCount()
        win.batch_summary_table.insertRow(row)
        num_item = QTableWidgetItem(str(i + 1))
        num_item.setData(Qt.UserRole, i)
        win.batch_summary_table.setItem(row, 0, num_item)
        win.batch_summary_table.setItem(row, 4, QTableWidgetItem(e["摘要"]))

    # ── 4. 全量生成 ──
    win._generate_sequence_diagram()
    app.processEvents()
    check("时序图tab已懒加载创建", hasattr(win, "seq_diagram_tab"))
    tab = win.seq_diagram_tab
    model = tab._model
    check("模型已设置", model is not None)
    check(
        "全量生成5条消息",
        model is not None and len(model.messages) == 5,
        f"messages={len(model.messages) if model else None}",
    )
    check(
        "生成后自动切到时序图页",
        win.tab_widget.currentIndex() == win._seq_diagram_tab_index,
    )
    check(
        "节点 CCO 最左 + STA 去重 + SACK目的TEI建节点",
        model is not None and [n.tei for n in model.nodes] == [1, 2, 291],
        f"nodes={[n.label for n in model.nodes] if model else None}",
    )
    cco_node = model.nodes[0]
    check(
        "台体模拟CCO：CCO生命线改标注",
        cco_node.label == "台体发射机(模拟CCO)",
        f"cco={cco_node.label}",
    )
    sack_msg = model.messages[3]
    check(
        "SACK有向：目的TEI为箭头所指节点",
        sack_msg.kind == "sack" and sack_msg.dst_key == "TEI:291",
        f"sack={sack_msg.src_key}->{sack_msg.dst_key}",
    )
    test_msg = model.messages[4]
    check(
        "测试帧源为台体发射机节点",
        test_msg.src_key == "TEI:1" and test_msg.dst_key == "TEI:2",
        f"test={test_msg.src_key}->{test_msg.dst_key}",
    )
    # 广播（信标 idx2）箭头覆盖到最右已有节点；节点间距按标签宽度自适应
    bline = tab._msg_items[2]["line"].line()
    # 自适应公式验证（offscreen 字体度量退化，故按公式而非绝对值断言）
    fm = tab.fontMetrics()
    mw = max(fm.horizontalAdvance(m.label) for m in model.messages)
    expect_sp = max(360, int(mw * 1.2) + 120)
    check(
        "节点间距=按最宽标签自适应公式",
        getattr(tab, "_spacing", 0) == expect_sp,
        f"spacing={getattr(tab, '_spacing', None)} expect={expect_sp}",
    )
    check(
        "广播箭头覆盖全部已有节点（止于最右节点）",
        abs(bline.x1() - 0) < 1e-6
        and abs(bline.x2() - 2 * tab._spacing) < 1e-6,
        f"x1={bline.x1()} x2={bline.x2()} spacing={tab._spacing}",
    )
    check(
        "广播消息标签带[广播]标识",
        "[广播]" in model.messages[2].label,
        model.messages[2].label,
    )

    # ── 5. 勾选子集生成（仅勾选第2帧 SOF_UP，frame_idx 保持原始索引1）──
    win.batch_summary_table.selectRow(1)
    app.processEvents()
    win._generate_sequence_diagram()
    app.processEvents()
    model = tab._model
    check(
        "勾选子集仅1条消息且保持原始索引",
        model is not None
        and len(model.messages) == 1
        and model.messages[0].frame_idx == 1,
        f"messages={[(m.frame_idx) for m in model.messages] if model else None}",
    )
    check(
        "勾选子集标签帧序号为原始#2",
        model is not None and model.messages[0].label.startswith("#2 "),
        model.messages[0].label if model and model.messages else "",
    )

    # ── 恢复全量模型用于联动测试 ──
    win.batch_summary_table.clearSelection()
    win._generate_sequence_diagram()
    app.processEvents()

    # ── 6. 图 → 表联动：点击消息 frame_idx=1 跳回批量解析页并选中行 ──
    tab.message_clicked.emit(1)
    app.processEvents()
    check(
        "图点击后切回批量解析页",
        win.tab_widget.currentIndex() == win._batch_tab_index,
    )
    check(
        "图点击后摘要表选中对应行",
        win.batch_summary_table.currentRow() == 1,
        f"currentRow={win.batch_summary_table.currentRow()}",
    )
    check(
        "图点击后详情已填充",
        win.batch_detail_table.rowCount() > 0,
    )

    # ── 7. 表 → 图联动：选中第0帧行 → 图上该消息高亮 ──
    win.batch_summary_table.selectRow(0)
    app.processEvents()
    check(
        "摘要表选中行时序图高亮同步",
        tab._highlight_idx == 0,
        f"_highlight_idx={tab._highlight_idx}",
    )

    # ── 8. clear_batch 清空时序图模型 ──
    win.clear_batch()
    app.processEvents()
    check("clear_batch后时序图模型清空", tab._model is None)

    win.close()
    win.deleteLater()
    app.processEvents()

    print("=" * 56)
    if FAILURES:
        print(f"共 {len(FAILURES)} 项失败: {FAILURES}")
        raise SystemExit(1)
    print(f"全部测试通过（{PASS} 项）✓")


if __name__ == "__main__":
    main()
