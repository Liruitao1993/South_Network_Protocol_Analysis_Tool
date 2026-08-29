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
- 拖动/缩放设施（QSizeGrip 存在、拖动状态初始值）
- 双卡结构：输入卡（徽章+输入）与结果卡（提示+表格+操作行）独立显隐
- MainWindow 集成：_on_global_hotkey 唤出小窗并真实解析南网帧
"""

import _path_setup  # noqa: E402

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys

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
      print(f"  ✓ {msg}")


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
      # 输入内容后展开：卡片恢复细边框，输入框限高、余量给结果表
      p8.input.setPlainText(SOUTH_FRAME)
      p8._do_parse()
      app.processEvents()
      exp_qss = p8.input_card.styleSheet()
      check(
            "background: transparent" not in exp_qss and "border: 1px solid" in exp_qss,
            "展开态输入卡恢复 1px 细毛玻璃边框",
      )
      check(p8._shadows[0].isEnabled() is True, "展开态投影恢复")
      check(
            p8.input.maximumHeight() <= 100,
            f"展开态输入框限高（max={p8.input.maximumHeight()}px）",
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
      check(qp.proto_combo.currentData() == 0, "集成：协议自动识别为 0")
      # 校验徽章（南网真帧校验）
      check(
            "校验" in qp.valid_label.text(),
            f"校验徽章已设置（{qp.valid_label.text()}）",
      )
      # 再按热键隐藏
      w._on_global_hotkey()
      check(not qp.isVisible(), "再次热键隐藏小窗")

      print(f"\n全部通过：{_passed} 项断言")


if __name__ == "__main__":
      main()
