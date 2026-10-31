"""
快捷解析小窗（quick_parse_panel.py）offscreen 测试

运行：python test/test_quick_parse_panel.py
覆盖：
- 空态（收起为单输入框）/ 真实帧解析展开 / 清空后收回
- 协议自动识别（68..16→南网0、7E→HDLC 2）
- 非法 hex 错误态、校验徽章三态（通过/失败/不支持）
- Esc 关闭、toggle_panel 显隐切换、剪贴板预填
- 手动切换协议 → parse_fn 收到新 idx
- 「完整视图」→ open_full_fn 被调用且小窗隐藏
- 输入框 Enter 打开完整视图（Shift+Enter 保留换行 / 空输入不触发）
- _ever_activated 初始化：未激活即收到 ActivationChange 不崩溃
- 拖动/缩放设施（QSizeGrip 存在、拖动状态初始值）
- 双卡结构：输入卡（徽章+输入）与结果卡（提示+表格+操作行）独立显隐
- MainWindow 集成：_on_global_hotkey 唤出小窗并真实解析南网帧
- ED 包装帧（协议9）校验口径与解析对齐（剥离监控头后校验）
- 预填协议优先级：自动识别优先（识别得出即切换），识别不出兜底主窗体协议
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys

import _path_setup  # noqa: F401,E402  项目根加入 sys.path（test/ 共享引导）
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from system_integration.quick_parse_panel import QuickParsePanel

PROTO_ITEMS = [
      ("[0] 南网协议", 0),
      ("[1] PLC RF", 1),
      ("[2] HDLC/国网DLMS", 2),
      ("[3] DLMS-APDU(国网)", 3),
      ("[4] DLMS Wrapper", 4),
      ("[5] DLMS-APDU 裸报文", 5),
      ("[6] DLT645-2007", 6),
      ("[7] 国网协议", 7),
      ("[8] 698.45协议", 8),
      ("[9] 新一代载波", 9),
      ("[10] 国网新一代", 10),
      ("[11] HDC 1.0", 11),
]

SOUTH_FRAME = "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16"
HDLC_FRAME = "7E A0 0A 00 02 00 23 13 96 05 01 60 5C 7E"

_passed = 0


def check(cond, msg):
      global _passed
      assert cond, f"FAIL: {msg}"
      _passed += 1
      # GBK 控制台无法编码 ✓/⚠ 等字符（项目测试约定，见 AGENTS.md §7）：
      # 消息里断言文案可能含 UI 字符，按 GBK 可编码范围清洗后输出
      safe = msg.encode("gbk", "replace").decode("gbk")
      print(f"  [OK] {safe}")


_DEFAULT_ROWS = object()


def make_panel(parse_rows=_DEFAULT_ROWS, valid_ret=(True, "[通过]通过12项")):
      """构造带 fake 回调的面板。

      parse_rows: 默认两行成功；None=返回解析失败；"raise"=抛异常；list=自定义行
      """
      calls = {"parse": [], "validate": [], "open_full": []}

      def fake_clean(text):
            return "".join(ch for ch in text if ch in "0123456789abcdefABCDEF")

      def fake_parse(fb, idx):
            calls["parse"].append((fb, idx))
            if parse_rows == "raise":
                  raise RuntimeError("boom")
            if parse_rows is None:
                  return None, "解析失败：模拟错误", None
            if parse_rows is _DEFAULT_ROWS:
                  rows = [("字段A", "68", "", "起始符"), ("字段B", "16", "", "结束符")]
            else:
                  rows = parse_rows
            return rows, None, None

      def fake_validate(fb, idx):
            calls["validate"].append((fb, idx))
            return valid_ret

      def fake_open(fb, idx):
            calls["open_full"].append((fb, idx))

      panel = QuickParsePanel(
            protocol_items=PROTO_ITEMS,
            clean_fn=fake_clean,
            parse_fn=fake_parse,
            validate_fn=fake_validate,
            open_full_fn=fake_open,
            is_dark_fn=lambda: False,
      )
      return panel, calls


def main():
      app = QApplication(sys.argv)

      print("== 1. 初始空态（单输入卡收起形态） ==")
      panel, calls = make_panel()
      check(not panel.table.isVisibleTo(panel), "初始表格隐藏（空态）")
      check(not panel.status_label.isVisibleTo(panel), "空态提示隐藏（收起形态）")
      check(not panel.header.isVisibleTo(panel), "徽章行隐藏（收起形态）")
      check(not panel.footer.isVisibleTo(panel), "底部操作行隐藏（收起形态）")
      check(not panel.result_card.isVisibleTo(panel), "空态结果卡整体隐藏")
      check(panel.input_card.isVisibleTo(panel), "空态仅输入卡可见")

      print("== 2. 真实帧解析 + 协议自动识别（南网） ==")
      panel.input.setPlainText(SOUTH_FRAME)
      panel._do_parse()
      check(panel.table.isVisibleTo(panel), "解析后表格可见")
      check(
            panel.header.isVisibleTo(panel) and panel.footer.isVisibleTo(panel),
            "解析后展开为完整卡片（徽章行+操作行）",
      )
      check(
            panel.result_card.isVisibleTo(panel)
            and panel.input_card.isVisibleTo(panel)
            and panel.result_card is not panel.input_card,
            "解析后为两张独立卡片（输入卡+结果卡并存）",
      )
      check(panel.table.rowCount() == 2, f"字段行数=2（实际 {panel.table.rowCount()}）")
      check(
            panel.len_label.text() == "14 字节",
            f"帧长标签=14 字节（实际 {panel.len_label.text()}）",
      )
      check(panel.proto_combo.currentData() == 0, "68..16 帧自动识别为协议 0（南网）")
      check(calls["parse"][-1][1] == 0, "parse_fn 收到 idx=0")

      print("== 3. HDLC 帧自动识别 ==")
      panel.input.setPlainText(HDLC_FRAME)
      panel._do_parse()
      check(panel.proto_combo.currentData() == 2, "7E 开头自动识别为协议 2（HDLC）")

      print("== 3b. 清空输入收回单输入框形态 ==")
      h_expanded = panel.height()
      panel.input.setPlainText("")
      panel._do_parse()
      check(not panel.table.isVisibleTo(panel), "清空后表格隐藏")
      check(
            not panel.header.isVisibleTo(panel) and not panel.footer.isVisibleTo(panel),
            "清空后徽章行/操作行隐藏（收起形态）",
      )
      check(
            panel.height() < h_expanded - 60,
            f"窗口高度收回（展开 {h_expanded}px → 收起 {panel.height()}px）",
      )

      print("== 3c. 拖动/缩放设施 ==")
      from PySide6.QtWidgets import QSizeGrip

      grip = panel.findChild(QSizeGrip)
      check(grip is not None, "右下角缩放柄存在")
      assert grip is not None
      check(grip.parent() is panel, "缩放柄挂在外层窗口（不遮挡卡片内容）")
      # 可见斜纹缩放柄（空态也能看到，解决宽度调整热区不明显问题）
      from system_integration.quick_parse_panel import _VisibleSizeGrip

      check(isinstance(grip, _VisibleSizeGrip), "缩放柄为可见斜纹样式 _VisibleSizeGrip")
      check(
            grip.width() >= 18 and grip.height() >= 18,
            f"缩放柄热区≥18px（{grip.width()}x{grip.height()}）",
      )
      check(
            panel._drag_offset is None and panel._user_geom is False,
            "拖动状态初始值正确",
      )

      print("== 3d. _ever_activated 初始化（失焦事件不崩溃）==")
      p_ev, _ = make_panel()
      check(p_ev._ever_activated is False, "_ever_activated 构造期初始化为 False")
      # 窗口尚未激活就收到 ActivationChange（如唤出瞬间其他窗口持有焦点）不得抛异常
      p_ev.changeEvent(QEvent(QEvent.Type.ActivationChange))
      check(True, "未激活窗口的 ActivationChange 不抛 AttributeError")
      p_ev._ever_activated = True
      p_ev.show()
      p_ev.changeEvent(QEvent(QEvent.Type.ActivationChange))
      check(
            not p_ev.isVisible() or p_ev.isActiveWindow(),
            "已激活窗口失焦时自动隐藏（offscreen 可能始终算激活）",
      )

      print("== 4. 非法 hex 错误态 ==")
      panel.input.setPlainText("xyz不是报文")
      panel._do_parse()
      check(not panel.table.isVisibleTo(panel), "非法输入表格隐藏")
      check("⚠" in panel.status_label.text(), "错误态显示 ⚠ 提示")
      check(panel.footer.isVisibleTo(panel), "非法输入保持展开显示错误提示")
      check(panel.result_card.isVisibleTo(panel), "错误态结果卡弹出（⚠ 在结果卡内）")

      print("== 5. 校验徽章三态 ==")
      p2, _ = make_panel(valid_ret=(True, "[通过]通过12项"))
      p2.input.setPlainText(SOUTH_FRAME)
      p2._do_parse()
      check(
            "校验通过" in p2.valid_label.text(),
            f"valid=True → 通过徽章（{p2.valid_label.text()}）",
      )
      p3, _ = make_panel(valid_ret=(False, "[失败]校验和错误"))
      p3.input.setPlainText(SOUTH_FRAME)
      p3._do_parse()
      check("校验失败" in p3.valid_label.text(), "valid=False → 失败徽章")
      p4, _ = make_panel(valid_ret=(None, ""))
      p4.input.setPlainText(SOUTH_FRAME)
      p4._do_parse()
      check(p4.valid_label.text() == "—", "valid=None → 灰色—")

      print("== 5b. 暗色主题毛玻璃配色（单一主面板）==")
      p6, _ = make_panel()
      p6._is_dark_fn = lambda: True
      p6._restyle()
      p6._sync_card_chrome(expanded=True)  # 展开态面板呈现毛玻璃底色
      check(
            "rgba(30, 33, 46" in p6.input_card.styleSheet()
            and "#qpPanel" in p6.input_card.styleSheet(),
            "暗色主题面板背景与选择器正确（毛玻璃深蓝灰）",
      )
      check(
            "border-radius: 14px" in p6.input_card.styleSheet(),
            "面板圆角 14px（玻璃化统一圆角）",
      )
      # 面板约 45% 透明度（alpha 115 = 0x73）
      import re as _re

      m = _re.search(r"rgba\(30,\s*33,\s*46,\s*(\d+)\)", p6.input_card.styleSheet())
      check(
            m is not None and 90 <= int(m.group(1)) <= 140,
            f"暗色面板约 45% 半透明（alpha={m.group(1) if m else 'N/A'}）",
      )
      # 亚克力毛玻璃接口已接入（Windows 真正模糊，其他平台静默降级）
      import importlib

      acrylic_effect = importlib.import_module("system_integration.acrylic_effect")
      enable_acrylic = getattr(acrylic_effect, "enable_acrylic", None)

      check(
            callable(enable_acrylic),
            "system_integration.acrylic_effect 提供 enable_acrylic",
      )
      check(hasattr(p6, "_apply_acrylic"), "面板提供 _apply_acrylic 着色入口")

      print("== 5d. 空态仅输入框（卡片无边框/底色/投影，输入框高度可拉伸）==")
      p8, _ = make_panel()
      p8.show()
      app.processEvents()
      empty_qss = p8.input_card.styleSheet()
      check(
            "background: transparent" in empty_qss and "border: none" in empty_qss,
            "空态输入卡透明无边框（仅显示输入框本身）",
      )
      check(
            p8._shadows[0].isEnabled() is False, "空态输入卡投影已禁用（无粗边框/阴影）"
      )
      # 空态细光晕：外层边距 6px + 面板内边距 2px ≈ 输入框距窗口边缘 8px（原 28px）
      p8_outer, p8_inner = p8.layout(), p8.panel.layout()
      assert p8_outer is not None and p8_inner is not None
      check(
            p8_outer.contentsMargins().left() == 6,
            f"空态外层边距收窄为 6px 光晕（实际 {p8_outer.contentsMargins().left()}px）",
      )
      check(
            p8_inner.contentsMargins().left() == 2,
            f"空态面板内边距收窄为 2px（实际 {p8_inner.contentsMargins().left()}px）",
      )
      check(
            p8.input.mapTo(p8, p8.input.rect().topLeft()).x() == 8,
            "空态输入框距窗口边缘 8px（细光晕）",
      )
      check(
            p8.input.maximumHeight() > 100000,
            f"空态输入框解除高度上限可纵向拉伸（max={p8.input.maximumHeight()}）",
      )
      h_before = p8.input.height()
      p8.resize(p8.width(), p8.height() + 160)
      app.processEvents()
      check(
            p8.input.height() >= h_before + 120,
            f"空态窗口拉高后输入框跟随变高（{h_before}px → {p8.input.height()}px）",
      )
      # 输入内容后展开：卡片恢复毛玻璃底色（无描边），输入框限高、余量给结果表
      p8.input.setPlainText(SOUTH_FRAME)
      p8._do_parse()
      app.processEvents()
      exp_qss = p8.input_card.styleSheet()
      check(
            "background: " in exp_qss
            and "transparent" not in exp_qss.split("border-radius")[0]
            and "border:" not in exp_qss.split("border-radius")[0],
            "展开态输入卡恢复毛玻璃底色（无描边，靠投影圈定边界）",
      )
      check(
            p8.input.maximumHeight() <= 100,
            f"展开态输入框限高（max={p8.input.maximumHeight()}px）",
      )
      # 展开态边距恢复：外层 12px 投影边距 + 面板内边距 16px
      assert p8_outer is not None and p8_inner is not None
      check(
            p8_outer.contentsMargins().left() == 12
            and p8_inner.contentsMargins().left() == 16,
            "展开态边距恢复（外层 12px / 面板内边距 16px）",
      )

      print("== 5c. 浅色主题毛玻璃面板约 59% 透明度 ==")
      p6b, _ = make_panel()
      p6b._is_dark_fn = lambda: False
      p6b._restyle()
      p6b._sync_card_chrome(expanded=True)  # 展开态面板呈现毛玻璃底色
      ml = _re.search(
            r"rgba\(250,\s*250,\s*252,\s*(\d+)\)", p6b.input_card.styleSheet()
      )
      check(
            ml is not None and 100 <= int(ml.group(1)) <= 160,
            f"浅色面板约 59% 半透明（alpha={ml.group(1) if ml else 'N/A'}）",
      )

      print("== 6. 解析异常容错 ==")
      p5, c5 = make_panel(parse_rows="raise")
      p5.input.setPlainText(SOUTH_FRAME)
      p5._do_parse()  # 不应抛异常
      check("⚠" in p5.status_label.text(), "parse_fn 抛异常时显示错误态不崩溃")

      print("== 7. Esc 关闭 ==")
      panel.show()
      app.processEvents()
      check(panel.isVisible(), "show 后可见")
      panel.keyPressEvent(
            QKeyEvent(
                  QEvent.Type.KeyPress,
                  Qt.Key.Key_Escape,
                  Qt.KeyboardModifier.NoModifier,
            )
      )
      check(not panel.isVisible(), "Esc 后隐藏")

      print("== 8. toggle_panel 显隐切换 + 剪贴板预填 ==")
      app.clipboard().setText(SOUTH_FRAME)
      panel.toggle_panel()
      app.processEvents()
      check(panel.isVisible(), "热键 toggle 后显示")
      check(
            panel.table.isVisibleTo(panel) and panel.table.rowCount() == 2,
            "剪贴板合法 hex 预填并已解析",
      )
      panel.toggle_panel()
      check(not panel.isVisible(), "再次 toggle 隐藏")

      print("== 9. 手动切换协议重解析 ==")
      panel.toggle_panel()  # 重新显示（会再次预填）
      calls["parse"].clear()
      panel.proto_combo.setCurrentIndex(panel.proto_combo.findData(8))
      check(
            calls["parse"] and calls["parse"][-1][1] == 8,
            f"手动切到协议 8 后 parse_fn 收到 idx=8（实际 {calls['parse'][-1] if calls['parse'] else None}）",
      )

      print("== 10. 完整视图回调 ==")
      panel._open_full()
      check(not panel.isVisible(), "点完整视图后小窗隐藏")
      check(
            len(calls["open_full"]) == 1 and calls["open_full"][0][1] == 8,
            "open_full_fn 收到当前帧字节与协议 idx",
      )

      print("== 10b. Enter 打开完整视图（键位提示同文）==")
      p_en, c_en = make_panel()
      p_en.input.setPlainText(SOUTH_FRAME)
      p_en._do_parse()
      QApplication.sendEvent(
            p_en.input,
            QKeyEvent(
                  QEvent.Type.KeyPress,
                  Qt.Key.Key_Return,
                  Qt.KeyboardModifier.NoModifier,
            ),
      )
      check(
            len(c_en["open_full"]) == 1 and c_en["open_full"][0][1] == 0,
            f"输入框 Enter 打开完整视图并带当前协议（实际 {c_en['open_full']}）",
      )
      check(not p_en.isVisible(), "Enter 触发后面板隐藏")
      p_en.show()
      c_en["open_full"].clear()
      QApplication.sendEvent(
            p_en.input,
            QKeyEvent(
                  QEvent.Type.KeyPress,
                  Qt.Key.Key_Return,
                  Qt.KeyboardModifier.ShiftModifier,
            ),
      )
      check(not c_en["open_full"], "Shift+Enter 保留换行不触发完整视图")
      p_en2, c_en2 = make_panel()
      QApplication.sendEvent(
            p_en2.input,
            QKeyEvent(
                  QEvent.Type.KeyPress,
                  Qt.Key.Key_Return,
                  Qt.KeyboardModifier.NoModifier,
            ),
      )
      check(not c_en2["open_full"], "空输入 Enter 不触发完整视图且不崩溃")

      print("== 11. 复制结果 ==")
      panel.show()
      panel.input.setPlainText(SOUTH_FRAME)
      panel._do_parse()
      panel._copy_result()
      clip = app.clipboard().text()
      check("字段A" in clip and "起始符" in clip, "复制结果含字段行 TSV 文本")

      print("== 11b. 调整窗口大小时输入框高度固定（仅结果卡伸缩） ==")
      p7, _ = make_panel()
      p7.show()
      app.processEvents()
      p7.input.setPlainText(SOUTH_FRAME)
      p7._do_parse()
      app.processEvents()
      ih0, rh0 = p7.input.height(), p7.result_card.height()
      check(
            ih0 > 0 and rh0 > 0,
            f"展开态输入框与结果卡均已布局（输入框 {ih0}px / 结果卡 {rh0}px）",
      )
      p7.resize(p7.width(), p7.height() + 200)
      app.processEvents()
      check(
            p7.input.height() == ih0,
            f"窗口增高 200px 后输入框高度不变（仍 {p7.input.height()}px）",
      )
      check(
            p7.result_card.height() >= rh0 + 150,
            f"多余高度全部给结果卡（{rh0}px → {p7.result_card.height()}px）",
      )
      p7.resize(p7.width(), p7.height() - 150)
      app.processEvents()
      check(
            p7.input.height() == ih0,
            f"窗口回缩后输入框高度仍不变（{p7.input.height()}px）",
      )

      print("== 12. MainWindow 集成（真实解析南网帧） ==")
      import main_gui

      w = main_gui.MainWindow()
      # A 方案：小窗协议跟随主窗体；为保证南网帧解析正确，固定主窗体协议为 0
      w.protocol_combo.setCurrentIndex(0)
      app.processEvents()
      app.clipboard().setText(SOUTH_FRAME)
      w._on_global_hotkey()
      app.processEvents()
      qp = getattr(w, "_quick_panel", None)
      check(qp is not None, "热键后 _quick_panel 已懒创建")
      assert qp is not None
      check(qp.isVisible(), "小窗可见")
      check(
            qp.table.isVisibleTo(qp) and qp.table.rowCount() > 2,
            f"真实南网帧解析出字段行（{qp.table.rowCount()} 行）",
      )
      check(qp.proto_combo.currentData() == 0, "集成：小窗协议跟随主窗体（=0）")
      # 校验徽章（南网真帧校验）
      check(
            "校验" in qp.valid_label.text(),
            f"校验徽章已设置（{qp.valid_label.text()}）",
      )
      # A 方案：主窗体切协议时小窗下拉跟随（仅当小窗存在）
      w.protocol_combo.setCurrentIndex(7)  # 主切到 7=国网协议
      app.processEvents()
      check(
            qp.proto_combo.currentData() == 7,
            f"A 方案：主窗体切协议 → 小窗下拉跟随（实际 {qp.proto_combo.currentData()}）",
      )
      # 先把主窗体协议切回 0，避免协议 mismatch 干扰
      w.protocol_combo.setCurrentIndex(0)
      app.processEvents()
      qp.input.setPlainText(SOUTH_FRAME)
      qp._do_parse()
      app.processEvents()
      qp._open_full()
      app.processEvents()
      check(
            w.single_input.toPlainText().strip() == SOUTH_FRAME.replace(",", " "),
            f"主程序单帧解析输入框收到报文（实际 {w.single_input.toPlainText()[:30]}...）",
      )
      check(
            w.protocol_combo.currentIndex() == 0 and w.tab_widget.currentIndex() == 0,
            f"主程序协议下拉=0、tab=单帧解析页（实际 protocol={w.protocol_combo.currentIndex()}, tab={w.tab_widget.currentIndex()}）",
      )
      check(not qp.isVisible(), "「在主窗口打开」后小窗隐藏")
      # 小窗已被 _open_full 隐藏：热键先重新唤出（预填剪贴板），再按才隐藏
      w._on_global_hotkey()
      check(qp.isVisible(), "热键重新唤出小窗（此前已被「在主窗口打开」隐藏）")
      w._on_global_hotkey()
      check(not qp.isVisible(), "再次热键隐藏小窗")

      print("== 12b. ED 包装帧（协议9）校验口径与解析对齐 ==")
      # 构造合法 ED..EE 包装：ED+帧长(LE)+ctrl1(00)+ctrl2(01)+EF+9字节公共头+业务帧+CS+EE
      ed_bytes = bytes.fromhex(
            "ED 19 00 00 01 EF 01 00 00 00 00 01 00 0C 00 "
            "11 01 01 00 00 00 00 01 00 01 00 00 19 EE".replace(" ", "")
      )
      rows_ed, err_ed, _note_ed = w._quick_panel_parse(ed_bytes, 9)
      check(
            rows_ed and err_ed is None,
            f"ED 包装帧协议9解析成功（剥离监控头后，实际 err={err_ed}）",
      )
      valid_ed, summary_ed = w._quick_panel_validate(ed_bytes, 9)
      check(
            valid_ed is True,
            f"ED 包装帧校验与解析对齐（剥离后校验，实际 {valid_ed}/{summary_ed}）",
      )
      # 对照：裸业务帧同口径通过；剥离失败路径（截断帧）不崩溃
      valid_bare, _ = w._quick_panel_validate(ed_bytes[15:27], 9)
      check(valid_bare is True, "裸业务帧校验通过（口径一致）")
      valid_trunc, _ = w._quick_panel_validate(ed_bytes[:10], 9)
      check(
            valid_trunc in (True, False, None),
            f"截断 ED 帧校验不崩溃（回退原帧/兜底，实际 {valid_trunc}）",
      )

      print("== 12c. 预填协议：自动识别优先，主窗体协议兜底 ==")
      # 识别优先：主窗体=7（国网），剪贴板为南网 68..16 帧 → 识别为 0 并切换
      w.protocol_combo.setCurrentIndex(7)
      app.processEvents()
      app.clipboard().setText(SOUTH_FRAME)
      w._on_global_hotkey()  # 小窗当前隐藏 → 唤出并预填
      app.processEvents()
      check(qp.isVisible(), "12c：小窗唤出成功")
      check(
            qp.proto_combo.currentData() == 0,
            f"自动识别优先：南网帧识别为 0（不锁定主窗体 7，实际 {qp.proto_combo.currentData()}）",
      )
      # 兜底：主窗体=7，剪贴板为不可识别帧 → 保持主窗体协议 7
      w._on_global_hotkey()  # 先隐藏（toggle）
      app.processEvents()
      app.clipboard().setText("00 11 22 33 44")
      w.protocol_combo.setCurrentIndex(7)
      app.processEvents()
      w._on_global_hotkey()  # 再唤出触发预填
      app.processEvents()
      check(
            qp.proto_combo.currentData() == 7,
            f"不可识别帧兜底：保持主窗体协议 7（实际 {qp.proto_combo.currentData()}）",
      )

      # 收尾：MainWindow 会起 GlobalHotkeyThread 等后台线程，不停止会在进程退出时
      # 报「QThread: Destroyed while thread is still running」，退出码变 0xC0000409
      # （断言全过却看起来失败）。
      try:
            w._shutdown_threads()
      except Exception:
            pass
      try:
            w.close()
      except Exception:
            pass
      app.processEvents()

      print(f"\n全部通过：{_passed} 项断言")


if __name__ == "__main__":
      main()
