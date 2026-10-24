# -*- coding: utf-8 -*-
"""DLT645（协议6）组帧 GUI 集成冒烟测试（offscreen）

对应 implement.md Step 4 的验证要求，直接复现用户场景：
  打开主程序 → 协议选 6 → 「协议组帧」tab 必须可见且可用
覆盖：
  1. FrameGenWidget 切到 dlt645 模式后控件显隐正确、其他协议面板不串
  2. 命令下拉（请求/应答/异常三组）、DI 下拉 1099 条可搜索
  3. UI 生成的帧与纯逻辑生成器输出逐字节一致（读数据/广播校时/写数据）
  4. 组帧后「解析回读」标签显示通过（闭环在 UI 上可见）
  5. MainWindow 协议切到 6 → 组帧 tab 可见；切到 1 → 隐藏；切回 0 → south 模式
"""

import _path_setup  # noqa: E402

import io
import os
import sys

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


def _find_cmd(w, key):
    for i in range(w.dlt645_combo.count()):
        data = w.dlt645_combo.itemData(i)
        if data and tuple(data) == tuple(key):
            return i
    return -1


def _set_di(w, code):
    for i in range(w.dlt645_di_combo.count()):
        if str(w.dlt645_di_combo.itemData(i)).upper() == code:
            w.dlt645_di_combo.setCurrentIndex(i)
            return True
    return False


def _set_field(w, name, value):
    ed = w._dlt645_field_widgets.get(name)
    if ed is None:
        return False
    ed.setText(value)
    return True


def _field_names(w):
    return list(w._dlt645_field_widgets.keys())


def main():
    global PASS
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                     errors="replace")

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    import frame_gen_widget as fgw
    from dlt645_frame_gen import DLT645FrameGenerator, encode_di
    from dlt645_parser import DLT645Parser

    # 弹窗桩：offscreen 下真 QMessageBox 会阻塞测试
    class _FakeMB:
        calls = []

        @staticmethod
        def warning(*a, **k):
            _FakeMB.calls.append(("warning", a[2] if len(a) > 2 else ""))

        @staticmethod
        def critical(*a, **k):
            _FakeMB.calls.append(("critical", a[2] if len(a) > 2 else ""))

        @staticmethod
        def information(*a, **k):
            _FakeMB.calls.append(("information", a[2] if len(a) > 2 else ""))

    fgw.QMessageBox = _FakeMB
    GEN = DLT645FrameGenerator()

    print("== 1. 模式切换与控件显隐 ==")
    w = fgw.FrameGenWidget()
    w.set_protocol_mode("dlt645")
    check("protocol_mode == dlt645", w.protocol_mode == "dlt645", w.protocol_mode)
    check("命令下拉可见", not w.dlt645_combo.isHidden())
    check("帧配置面板可见", not w.dlt645_config_group.isHidden())
    check("标题改为「命令选择」", w.cmd_select_group.title() == "命令选择",
          w.cmd_select_group.title())
    check("南网 DI 下拉已隐藏", w.di_combo.isHidden())
    check("国网 AFN 下拉已隐藏", w.afn_fn_combo.isHidden())
    check("698 APDU 下拉已隐藏", w.dlt698_combo.isHidden())
    check("EB 生成器仅协议7 显示（此处隐藏）", w.eb_gen_group.isHidden())

    print("== 2. 下拉数据源 ==")
    cmds = [tuple(w.dlt645_combo.itemData(i)) for i in range(w.dlt645_combo.count())
            if w.dlt645_combo.itemData(i)]
    from dlt645_frame_schema import DLT645_CMD_SCHEMA, REQ
    _want_req = len([k for k in DLT645_CMD_SCHEMA if k[0] == REQ])
    check("命令下拉含全部请求命令（含无线扩展 06H/1EH）",
          sum(1 for c in cmds if c[0] == "req") == _want_req,
          f"{len(cmds)} 项，req 期望 {_want_req}")
    check("下拉含无线模组扩展 06H 与 1EH",
          ("req", 0x06) in cmds and ("req", 0x1E) in cmds)
    check("命令下拉含应答与异常应答",
          any(c[0] == "rsp" for c in cmds) and any(c[0] == "err" for c in cmds))
    check("命令项文本带分组前缀",
          w.dlt645_combo.itemText(0).startswith("【主站请求】"), w.dlt645_combo.itemText(0))
    di_count = w.dlt645_di_combo.count()
    check(f"DI 下拉全量装载（{di_count} 条）", di_count >= 1099, str(di_count))
    check("DI 下拉首项含中文名", "电能" in w.dlt645_di_combo.itemText(0)
          or len(w.dlt645_di_combo.itemText(0)) > 8, w.dlt645_di_combo.itemText(0))

    print("== 3. 读数据 11H：UI 生成 == 纯逻辑生成 ==")
    _FakeMB.calls.clear()
    idx = _find_cmd(w, ("req", 0x11))
    check("能找到读数据命令", idx >= 0)
    w.dlt645_combo.setCurrentIndex(idx)
    check("切命令后 DI 行可见", not w.dlt645_di_row.isHidden())
    check("控制码标签显示 C=0x11", "0x11" in w.dlt645_ctrl_label.text(),
          w.dlt645_ctrl_label.text())
    check("默认地址 000000000000", w._dlt645_addr_value() == "000000000000",
          w._dlt645_addr_value())
    check("选中 DI 00010000", _set_di(w, "00010000"))
    check("DI 元数据标签含名称与格式",
          "正向有功" in w.dlt645_di_info.text() and "XXXXXX.XX" in w.dlt645_di_info.text(),
          w.dlt645_di_info.text())
    check("读请求数据域仅 DI：不显示值字段", _field_names(w) == [], str(_field_names(w)))
    w._generate_dlt645_frame()
    expect = GEN.build_frame("000000000000", GEN.build_control(0x11),
                             encode_di("00010000"))
    got = w.result_hex.toPlainText().replace(" ", "")
    check("UI 生成帧 == 纯逻辑生成帧", got == expect.hex().upper(),
          f"got={got} expect={expect.hex().upper()}")
    check("生成帧 hex 精确", got == "6800000000000068110433333433B216", got)
    check("解析回读标签显示通过", "通过" in w.dlt645_verify_label.text(),
          w.dlt645_verify_label.text())
    check("无错误弹窗", not _FakeMB.calls, str(_FakeMB.calls))

    print("== 4. 广播校时 08H：地址自动切 99×6 + 年字节 ==")
    _FakeMB.calls.clear()
    w.set_protocol_mode("dlt645")
    w._dlt645_addr_touched = False
    idx = _find_cmd(w, ("req", 0x08))
    w.dlt645_combo.setCurrentIndex(idx)
    check("校时命令地址域自动填 999999999999",
          w._dlt645_addr_value() == "999999999999", w._dlt645_addr_value())
    check("校时命令隐藏 DI 行", w.dlt645_di_row.isHidden())
    check("校时字段存在", _set_field(w, "校时时间", "2026-09-04 16:26:30"),
          str(_field_names(w)))
    w._generate_dlt645_frame()
    got = w.result_hex.toPlainText().replace(" ", "")
    f = bytes.fromhex(got)
    check("校时帧地址域 99×6", f[1:7] == b"\x99" * 6, f[1:7].hex())
    check("校时帧数据域线序 ss mm hh DD MM YY",
          GEN.descramble(f[10:-2]) == bytes.fromhex("302616040926"),
          GEN.descramble(f[10:-2]).hex())
    r = DLT645Parser.parse(f)
    blob = " ".join(str(c) for c in r.get("fields", []))
    check("解析回读校时时间正确", "2026-09-04 16:26:30" in blob, blob[:160])
    check("校时无错误弹窗", not _FakeMB.calls, str(_FakeMB.calls))

    print("== 5. 写数据 14H：真 BCD 编码 + 密码/操作者字段 ==")
    _FakeMB.calls.clear()
    w.set_protocol_mode("dlt645")
    idx = _find_cmd(w, ("req", 0x14))
    w.dlt645_combo.setCurrentIndex(idx)
    _set_di(w, "00010000")
    names = _field_names(w)
    check("写数据字段含 数据值/密码/操作者/裸hex 兜底",
          all(k in names for k in ("数据值", "密码权限 PA", "密码 P0P1P2",
                                   "操作者代码 C0~C3", "写入数据(裸hex)")), str(names))
    _set_field(w, "数据值", "123456.78")
    _set_field(w, "密码权限 PA", "04")
    _set_field(w, "密码 P0P1P2", "111111")
    _set_field(w, "操作者代码 C0~C3", "12345678")
    w._set_dlt645_addr("000000000033")
    w._generate_dlt645_frame()
    got = w.result_hex.toPlainText().replace(" ", "")
    f = bytes.fromhex(got)
    data = GEN.descramble(f[10:-2])
    check("写数据 L=16(0x10)", f[9] == 0x10, f"{f[9]:02X}")
    check("写入数据为真 BCD 78563412（非 hex 直填）",
          data[12:] == bytes.fromhex("78563412"), data.hex())
    check("写数据解析回读通过", "通过" in w.dlt645_verify_label.text(),
          w.dlt645_verify_label.text())
    check("写数据无错误弹窗", not _FakeMB.calls, str(_FakeMB.calls))

    print("== 6. 非法输入：中文报错且不崩溃 ==")
    _FakeMB.calls.clear()
    _set_field(w, "数据值", "")
    _set_field(w, "写入数据(裸hex)", "")
    w._set_dlt645_addr("ZZZZ")
    w._generate_dlt645_frame()
    check("非法地址触发警告弹窗", any(c[0] == "warning" for c in _FakeMB.calls),
          str(_FakeMB.calls))
    check("错误消息为中文",
          any(any("\u4e00" <= ch <= "\u9fff" for ch in str(c[1])) for c in _FakeMB.calls),
          str(_FakeMB.calls))

    print("== 7. 切回其他协议：面板不串 ==")
    w._set_dlt645_addr("000000000000")
    w.set_protocol_mode("south")
    check("south 模式：645 面板隐藏", w.dlt645_combo.isHidden()
          and w.dlt645_config_group.isHidden())
    check("south 模式：DI 下拉可见", not w.di_combo.isHidden())
    w.set_protocol_mode("gdw")
    check("gdw 模式：AFN 下拉可见", not w.afn_fn_combo.isHidden())
    check("gdw 模式：EB 生成器可见", not w.eb_gen_group.isHidden())
    check("gdw 模式：645 面板隐藏", w.dlt645_config_group.isHidden())
    w.set_protocol_mode("dlt698")
    check("dlt698 模式：APDU 下拉可见", not w.dlt698_combo.isHidden())
    check("dlt698 模式：645 面板隐藏", w.dlt645_config_group.isHidden())
    w.set_protocol_mode("dlt645")
    check("切回 dlt645：面板恢复可见", not w.dlt645_config_group.isHidden())
    w.reset()
    check("reset 后不崩溃且地址复位", w._dlt645_addr_value() == "000000000000",
          w._dlt645_addr_value())

    print("== 7b. 实时解析预览（信号→防抖调度→刷新，真实链路）==")
    # 注意：不得直接调 _do_realtime_update_dlt645——那会绕过信号接线，
    # 正是「预览不刷新」这个 bug 当初漏网的原因。必须靠控件信号→
    # _schedule_realtime_update→200ms 防抖定时器→_do_realtime_update 链路。
    from PySide6.QtTest import QTest
    w.set_protocol_mode("dlt645")
    idx = _find_cmd(w, ("req", 0x11))
    w.dlt645_combo.setCurrentIndex(idx)
    _set_di(w, "02010100")
    QTest.qWait(300)
    check("信号链路触发后预览表有行", w.preview_table.rowCount() > 0,
          str(w.preview_table.rowCount()))
    names = [str(w.preview_table.item(i, 0).text())
             for i in range(w.preview_table.rowCount())]
    check("实时预览含帧头/控制码/数据标识行",
          any("起始符" in n for n in names) and any("控制码" in n for n in names)
          and any("数据标识" in n for n in names), str(names))
    parsed_vals = [str(w.preview_table.item(i, 2).text())
                   for i in range(w.preview_table.rowCount())]
    check("实时预览含 DI 名称（A相电压）", any("A相电压" in v for v in parsed_vals),
          str(parsed_vals))
    check("实时预览同步刷新生成结果 hex",
          w.result_hex.toPlainText().replace(" ", "") ==
          GEN.build_frame("000000000000", GEN.build_control(0x11),
                          encode_di("02010100")).hex().upper(),
          w.result_hex.toPlainText())

    _set_di(w, "00010000")
    QTest.qWait(300)
    vals1 = [str(w.preview_table.item(i, 2).text())
             for i in range(w.preview_table.rowCount())]
    check("改 DI 后预览跟随（当前正向有功总电能）",
          any("正向有功总电能" in v for v in vals1), str(vals1))

    idx = _find_cmd(w, ("rsp", 0x11))
    w.dlt645_combo.setCurrentIndex(idx)
    _set_di(w, "00010000")
    check("读应答显示「数据值」字段", "数据值" in _field_names(w), str(_field_names(w)))
    _set_field(w, "数据值", "123456.78")
    QTest.qWait(300)
    vals2 = [str(w.preview_table.item(i, 2).text())
             for i in range(w.preview_table.rowCount())]
    check("改值后预览刷新且含 123456.78", any("123456.78" in v for v in vals2),
          str(vals2))

    w.preview_table.setRowCount(0)
    w._generate_dlt645_frame()
    QTest.qWait(300)
    check("点生成帧后预览也刷新", w.preview_table.rowCount() > 0,
          str(w.preview_table.rowCount()))

    _FakeMB.calls.clear()
    w._set_dlt645_addr("ZZ")
    QTest.qWait(300)
    check("非法输入实时路径静默清空预览", w.preview_table.rowCount() == 0,
          str(w.preview_table.rowCount()))
    check("非法输入实时路径不弹窗", not _FakeMB.calls, str(_FakeMB.calls))
    w._set_dlt645_addr("000000000000")
    QTest.qWait(300)

    print("== 7c. 地址类型与历史地址 ==")
    items = [w.dlt645_addr.itemText(i) for i in range(w.dlt645_addr.count())]
    check("地址下拉含内置类型(广播/通配/全零)",
          all(x in items for x in ("999999999999", "AAAAAAAAAAAA", "000000000000")),
          str(items))
    w._set_dlt645_addr("AAAAAAAAAAAA")
    check("通配地址类型标签", "通配地址" in w.dlt645_addr_type_label.text(),
          w.dlt645_addr_type_label.text())
    w._set_dlt645_addr("999999999999")
    check("广播地址类型标签", "广播地址" in w.dlt645_addr_type_label.text(),
          w.dlt645_addr_type_label.text())
    w._set_dlt645_addr("000000000000")
    check("全零地址类型标签优先于历史", "全零地址" in w.dlt645_addr_type_label.text(),
          w.dlt645_addr_type_label.text())
    items = [w.dlt645_addr.itemText(i) for i in range(w.dlt645_addr.count())]
    check("历史地址进入下拉(写数据用例的 000000000033)", "000000000033" in items,
          str(items))
    w._set_dlt645_addr("000000000033")
    check("历史地址类型标签", "历史地址" in w.dlt645_addr_type_label.text(),
          w.dlt645_addr_type_label.text())
    w._set_dlt645_addr("123456789012")
    check("手动地址类型标签", "单地址" in w.dlt645_addr_type_label.text(),
          w.dlt645_addr_type_label.text())

    print("== 8. MainWindow：协议 6 下组帧 tab 可见（用户场景）==")
    import main_gui
    mw = main_gui.MainWindow()
    mw._ensure_frame_gen_tab()
    tab_idx = mw._frame_gen_tab_index

    mw.protocol_combo.setCurrentIndex(6)
    check("协议6：current_protocol == 6", mw.current_protocol == 6,
          str(mw.current_protocol))
    check("协议6：组帧 tab 可见", mw.tab_widget.isTabVisible(tab_idx))
    check("协议6：组帧页模式为 dlt645",
          mw.frame_gen_tab.protocol_mode == "dlt645", mw.frame_gen_tab.protocol_mode)
    check("协议6：645 命令下拉可见", not mw.frame_gen_tab.dlt645_combo.isHidden())

    mw.protocol_combo.setCurrentIndex(1)
    check("协议1（PLC RF）：组帧 tab 隐藏", not mw.tab_widget.isTabVisible(tab_idx))

    mw.protocol_combo.setCurrentIndex(0)
    check("协议0：组帧 tab 可见", mw.tab_widget.isTabVisible(tab_idx))
    check("协议0：模式回到 south", mw.frame_gen_tab.protocol_mode == "south",
          mw.frame_gen_tab.protocol_mode)

    mw.protocol_combo.setCurrentIndex(7)
    check("协议7：模式为 gdw", mw.frame_gen_tab.protocol_mode == "gdw")
    mw.protocol_combo.setCurrentIndex(8)
    check("协议8：模式为 dlt698", mw.frame_gen_tab.protocol_mode == "dlt698")

    mw.close()
    mw.deleteLater()

    print(f"\n=== {PASS} 项通过，{len(FAILURES)} 项失败 ===")
    if FAILURES:
        for n in FAILURES:
            print("  FAIL:", n)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
