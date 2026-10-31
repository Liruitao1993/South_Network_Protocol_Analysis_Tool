# -*- coding: utf-8 -*-
"""协议7「国网协议测试」页 —— **参数存档 / 支持统计 / 日志落盘 / 多页全选** 回归。

覆盖：
  [1] ParamStore：落盘往返、分段落盘（commands/eb/stats）、清参数只清参数
  [2] classify_result 五态矩阵（支持 / 支持但报错 / 回帧不匹配 / 无响应 / 未测）
  [3] summarize / summary_text / per_afn_text / stats_csv 口径
  [4] SessionLog：带时间戳追加、文件落盘、超限滚动、导出、清空只清缓冲
  [5] 页面参数存档：切换命令存/取、未改动不落档、发送队列各用各的参数
  [6] 多页全选：五页一起全选/全清、标签含「本页 + 合计」
  [7] 显示发送的命令：日志行、信息表、报文表都带 AFN/Fn + 命令名
  [8] 支持统计：成功/不匹配/无响应的记录与表格渲染、EB 不计入
  [9] 清理所有参数：命令参数清空、控件打回默认、全局参数与统计保留

运行: python test/test_gdw_test_store.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401

import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QLineEdit, QMessageBox, QSpinBox,
)

import _config_sandbox  # noqa: E402

_cfg_dir = _config_sandbox.install()

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: QMessageBox.StandardButton.Yes).start()

import gdw_test_core as C  # noqa: E402
import gdw_test_store as S  # noqa: E402
import gdw_test_widget as W  # noqa: E402

FAILED = []
CHECKS = [0]


def section(title):
    print(f"\n-- {title} " + "-" * max(0, 66 - len(title)))


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


# ══════════════════════════════════════════════════════════════════════
# [1] ParamStore
# ══════════════════════════════════════════════════════════════════════
def test_param_store():
    section("[1] ParamStore 落盘与会话隔离")
    path = Path(_cfg_dir) / "unit_params.json"
    st = S.ParamStore(path)
    check("初始为空", (st.param_count(), st.stats()), (0, {}))
    st.set_command("03-1", {"v": 1}, {"v": "1"}, "")
    st.set_eb("EB030001", {"a": 1}, {"a": "1"}, "AA")
    st.set_stat("03-1", S.STATE_SUPPORT, "确认")
    check_true("save 成功", st.save(), st.last_error)

    st2 = S.ParamStore(path)
    check("重开后命令参数还在", st2.get_command("03-1").get("ui"), {"v": "1"})
    check("重开后 EB 参数还在", st2.get_eb("EB030001").get("raw"), "AA")
    check("重开后统计还在", st2.get_stat("03-1").get("reason"), "确认")

    data = json.loads(path.read_text(encoding="utf-8"))
    check("文件四个段都在", sorted(k for k in data if isinstance(data[k], dict)),
          ["commands", "eb", "network", "stats"])

    removed = st2.clear_params()
    check("clear_params 返回清掉的条数", removed, 2)
    check("清参数后命令/EB 空", (st2.param_count(), st2.stats().get("03-1") is not None),
          (0, True))
    check("清参数不动统计", st2.get_stat("03-1").get("state"), S.STATE_SUPPORT)
    check("clear_stats 只清统计", st2.clear_stats(), 1)
    check("清统计后为空", st2.stats(), {})

    # 损坏文件不该抛
    bad = Path(_cfg_dir) / "bad_params.json"
    bad.write_text("{not json", encoding="utf-8")
    check("坏 JSON 退化为空存档", S.ParamStore(bad).param_count(), 0)


# ══════════════════════════════════════════════════════════════════════
# [2] classify_result
# ══════════════════════════════════════════════════════════════════════
def test_classify():
    section("[2] classify_result 口径")
    check("matched+ok=True → 支持", S.classify_result(
        {"matched": True, "ok": True, "reason": "确认"})[0], S.STATE_SUPPORT)
    check("matched+ok=False → 支持但报错", S.classify_result(
        {"matched": True, "ok": False, "reason": "错误代码=0x02"})[0], S.STATE_SUPPORT_ERROR)
    check("matched+ok=None → 支持（未判定）", S.classify_result(
        {"matched": True, "ok": None, "reason": "未做字段级判定"})[0], S.STATE_SUPPORT)
    check("not matched → 回帧不匹配", S.classify_result(
        {"matched": False, "ok": None, "reason": "AFN 不符"})[0], S.STATE_MISMATCH)
    check("依据原样保留", S.classify_result(
        {"matched": False, "ok": None, "reason": "AFN 不符：收到 00H，期望 01H"})[1],
        "AFN 不符：收到 00H，期望 01H")
    check("支持态集合", sorted(S.SUPPORTED_STATES), ["support", "support_error"])


# ══════════════════════════════════════════════════════════════════════
# [3] summarize / 文案 / CSV
# ══════════════════════════════════════════════════════════════════════
def test_summarize():
    section("[3] 汇总口径")
    cmds = list(C.all_commands())
    stats = {
        "03-1": {"state": S.STATE_SUPPORT, "reason": "确认", "at": "2026-10-27 11:00:00"},
        "03-2": {"state": S.STATE_SUPPORT_ERROR, "reason": "否认", "at": "2026-10-27 11:00:01"},
        "03-3": {"state": S.STATE_NO_REPLY, "reason": "无应答", "at": "2026-10-27 11:00:02"},
        "04-1": {"state": S.STATE_MISMATCH, "reason": "AFN 不符", "at": "2026-10-27 11:00:03"},
        "bad-key": {"state": S.STATE_SUPPORT, "reason": "不在命令表里", "at": ""},
    }
    summary = S.summarize(cmds, stats)
    check("统计行数 = 命令数", summary["total"], len(cmds))
    counts = summary["counts"]
    check("支持/报错/无响应/不匹配计数",
          (counts[S.STATE_SUPPORT], counts[S.STATE_SUPPORT_ERROR],
           counts[S.STATE_NO_REPLY], counts[S.STATE_MISMATCH]),
          (1, 1, 1, 1))
    check("未测 = 其余全部", counts[S.STATE_UNTESTED], len(cmds) - 4)
    check("AFN 0x03 支持 2/33（含报错）",
          summary["per_afn"][0x03]["supported"], 2)
    check("不存在的 key 不进统计", "bad-key" in str(summary["rows"]), False)
    text = S.summary_text(summary)
    check_true("汇总文案含五态", "支持 2" in text and "执行报错 1" in text
               and "无响应 1" in text and "未测" in text, text)
    check_true("按 AFN 文案", S.per_afn_text(summary).startswith("按 AFN：00H "),
               S.per_afn_text(summary))
    csv_text = S.stats_csv(summary)
    lines = csv_text.splitlines()
    check("CSV 首行是汇总注释", lines[0].startswith("# 共 "), True)
    check("CSV 表头", lines[1], ",".join(S.STATS_HEADERS))
    check("CSV 行数 = 命令数 + 2", len(lines), len(cmds) + 2)


# ══════════════════════════════════════════════════════════════════════
# [4] SessionLog
# ══════════════════════════════════════════════════════════════════════
def test_session_log():
    section("[4] 日志落盘 / 滚动 / 导出")
    logdir = Path(_cfg_dir) / "logs_unit"
    log = S.SessionLog(logdir, prefix="unit", max_bytes=200)
    line = log.append("[TX] 03H F1 测试")
    check_true("返回行带时间戳", line.startswith("[") and "] [TX] 03H F1 测试" in line, line)
    check("本次会话缓冲 1 行", len(log.lines()), 1)
    path = log.path()
    check("文件已创建", path.exists(), True)
    check("文件内容带时间戳", path.read_text(encoding="utf-8").strip().startswith("["), True)

    # 塞够量触发滚动
    for i in range(40):
        log.append(f"填充 {i} " + "x" * 20)
    rotated = sorted(p.name for p in logdir.glob("unit*.log"))
    check_true("超限滚动出 _2 文件", len(rotated) >= 2, rotated)

    dst = Path(_cfg_dir) / "out" / "log.txt"
    n = log.export(dst)
    check("导出行数 = 缓冲行数", n, len(log.lines()))
    check("导出文件行数一致", len(dst.read_text(encoding="utf-8").splitlines()), n)

    log.clear()
    check("clear 只清缓冲", (len(log.lines()), path.exists()), (0, True))
    log.close()

    # 目录不可写时不抛（只记 last_error）
    ro = S.SessionLog(Path(_cfg_dir) / "logs_ok", prefix="p")
    with patch("builtins.open", side_effect=OSError("denied")):
        ro.append("x")
    check_true("写失败只记 last_error", bool(ro.last_error), ro.last_error)
    ro.close()


# ══════════════════════════════════════════════════════════════════════
# 页面夹具
# ══════════════════════════════════════════════════════════════════════
class FakeSerial(QObject):
    """共享串口替身（与 test_gdw_testbench 同一口径）。"""

    raw_data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)
    log_message = Signal(str)
    frame_received = Signal(bytes)

    def __init__(self):
        super().__init__()
        self.sent = []

    def is_open(self):
        return True

    def write_raw(self, data):
        self.sent.append(bytes(data))
        return True

    def close_port(self):
        raise AssertionError("测试页不得关闭共享串口")


def make_widget():
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    worker = FakeSerial()
    w.set_serial_worker(worker)
    w.show()
    app.processEvents()
    return w, worker, app


def pump(app, ms: int = 30):
    """跑一下事件循环，让 10ms 的 `_next_timer` 把队列推进完。"""
    from PySide6.QtTest import QTest
    QTest.qWait(ms)
    app.processEvents()


def _set_first_text(w, value):
    """给当前命令的第一个可输入控件赋文本（找不到返回 None）。"""
    for fld, widget, _d in w._field_widgets:
        if isinstance(widget, QLineEdit):
            widget.setText(value)
            return fld.get("name")
        if isinstance(widget, QSpinBox):
            widget.setValue(int(value) if str(value).isdigit() else 1)
            return fld.get("name")
    return None


# ══════════════════════════════════════════════════════════════════════
# [5] 命令参数存档
# ══════════════════════════════════════════════════════════════════════
def test_widget_params():
    section("[5] 命令参数存档 / 队列各用各的参数")
    w, _worker, app = make_widget()
    w._select_page(C.PAGE_WRITE, notify=True)
    app.processEvents()

    w._trees[C.PAGE_WRITE].setCurrentItem(w._find_leaf(w._trees[C.PAGE_WRITE], "05-1"))
    app.processEvents()
    name = _set_first_text(w, "001122334455")
    check_true("05-1 有可输入字段", name is not None, w._field_widgets)
    w.edit_raw_data.setText("11 22")

    # 切到另一条再切回 → 参数应恢复
    w._trees[C.PAGE_WRITE].setCurrentItem(w._find_leaf(w._trees[C.PAGE_WRITE], "05-2"))
    app.processEvents()
    check("05-2 没有套用 05-1 的参数", w.edit_raw_data.text(), "")
    w._trees[C.PAGE_WRITE].setCurrentItem(w._find_leaf(w._trees[C.PAGE_WRITE], "05-1"))
    app.processEvents()
    widget = next(x[1] for x in w._field_widgets if x[0].get("name") == name)
    got = widget.text() if isinstance(widget, QLineEdit) else widget.value()
    check("切回后字段值恢复", got, "001122334455")
    check("切回后附加数据恢复", w.edit_raw_data.text(), "11 22")
    check("存档里只有改过的命令", w._params.param_count(), 1)

    # 未改动的命令不落档
    w._select_page(C.PAGE_READ, notify=True)
    app.processEvents()
    w._trees[C.PAGE_READ].setCurrentItem(w._find_leaf(w._trees[C.PAGE_READ], "03-1"))
    app.processEvents()
    w._trees[C.PAGE_READ].setCurrentItem(w._find_leaf(w._trees[C.PAGE_READ], "03-2"))
    app.processEvents()
    check("未改动的 03-1 不留档", w._params.get_command("03-1"), {})

    # 队列：两条命令各用自己的参数组帧
    f1 = w._build_frame_for(C.PAGE_WRITE, "05-1")
    f2 = w._build_frame_for(C.PAGE_WRITE, "05-2")
    check_true("两条命令组出的帧不同", f1 != f2, (C.format_hex(f1), C.format_hex(f2)))
    check_true("05-1 的帧含它自己的参数", "11 22 33 44 55" in C.format_hex(f1),
               C.format_hex(f1))

    # 落盘 → 重开恢复
    w._params.save()
    w2 = W.GdwTestWidget()
    check("重开恢复命令参数", w2._params.get_command("05-1").get("raw"), "11 22")
    w.close()
    w2.close()


# ══════════════════════════════════════════════════════════════════════
# [6] 多页全选
# ══════════════════════════════════════════════════════════════════════
def test_select_all_pages():
    section("[6] 多页全选")
    w, _worker, app = make_widget()
    w._set_all_pages(True)
    app.processEvents()
    total = sum(C.leaf_count(key) for key, _l in C.PAGES)
    got = {k: len(v) for k, v in w._checked.items()}
    # 「主动上报」页 19 条全是上行命令（06H/56H 上报、00H/50H 确认否认）：
    # 由被测设备主动发出，本页不下发，因此全选不会勾上它们
    check("六页全选（EB 75 / 读取 47 / 设置 56 / 上报 0 上行 / 自定义 0 / 流程 9）",
          got, {"read": 47, "write": 56, "report": 0, "eb": 75, "custom": 0, "flow": 9})
    # 流程页是脚本化用例，不进命令队列，因此不计入合计
    check("合计等于各页可下发之和（流程页不计）", sum(got.values()) - got["flow"], 47 + 56 + 75)
    check_true("标签含本页与合计", "（本页）" in w.lbl_checked.text()
               and "合计 178 / 178" in w.lbl_checked.text(), w.lbl_checked.text())
    # 树上真的勾上了（不只是字典）
    leaf = w._find_leaf(w._trees[C.PAGE_READ], "03-1")
    check("读取页树上已勾选", leaf.checkState(0).name, "Checked")

    w._set_all_pages(False)
    app.processEvents()
    check("全清后字典为空", {k: len(v) for k, v in w._checked.items()},
          {"read": 0, "write": 0, "report": 0, "eb": 0, "custom": 0, "flow": 0})
    check("全清后树上取消勾选", w._find_leaf(w._trees[C.PAGE_READ], "03-1").checkState(0).name,
          "Unchecked")
    check_true("全清后标签归零", "已选 0 / 47（本页）· 合计 0 /" in w.lbl_checked.text(),
               w.lbl_checked.text())
    w.close()


# ══════════════════════════════════════════════════════════════════════
# [7] 显示发送的命令
# ══════════════════════════════════════════════════════════════════════
def test_command_label():
    section("[7] 日志/表格显示发送的命令")
    w, worker, app = make_widget()
    w._select_page(C.PAGE_READ, notify=True)
    app.processEvents()
    w._trees[C.PAGE_READ].setCurrentItem(w._find_leaf(w._trees[C.PAGE_READ], "03-1"))
    app.processEvents()
    w._checked[C.PAGE_READ] = ["03-1"]
    w._on_send()
    app.processEvents()
    check("已发出一帧", len(worker.sent), 1)

    label = w._cmd_label("03-1")
    check_true("命令名可读（AFN + Fn + 名称）",
               label.startswith("03H F1 ") and "版本" in label, label)

    log_text = w.log_text.toPlainText()
    check_true("日志 TX 行带命令名", f"[TX] {label}" in log_text, log_text.splitlines()[:3])
    check("报文表列头", [w.raw_table.horizontalHeaderItem(i).text() for i in range(5)],
          ["时间", "方向", "命令", "长度", "报文"])
    check("报文表 TX 行带命令名", w.raw_table.item(0, 2).text(), label)
    check("信息表列头", [w.info_table.horizontalHeaderItem(i).text() for i in range(5)],
          ["时间", "命令", "从节点", "结果", "说明"])

    # 喂同命令响应 → 信息表行也带命令名
    w._on_frame(worker.sent[0])
    app.processEvents()
    check("信息表行带命令名", w.info_table.item(0, 1).text(), label)
    check("报文表 RX 行带命令名", w.raw_table.item(1, 2).text(), label)
    w.close()


# ══════════════════════════════════════════════════════════════════════
# [8] 支持统计 + 日志落盘
# ══════════════════════════════════════════════════════════════════════
def test_stats_and_log():
    section("[8] 支持统计 / 日志落盘")
    w, worker, app = make_widget()
    w._select_page(C.PAGE_READ, notify=True)
    app.processEvents()

    # 支持：回一帧同命令响应
    w._trees[C.PAGE_READ].setCurrentItem(w._find_leaf(w._trees[C.PAGE_READ], "03-1"))
    app.processEvents()
    w._checked[C.PAGE_READ] = ["03-1"]
    w.spin_retries.setValue(0)
    w._on_send()
    pump(app)
    frame = worker.sent[0]
    w._on_frame(frame)
    pump(app)
    check("成功 → support", w._params.get_stat("03-1").get("state"), S.STATE_SUPPORT)
    check_true("统计行含时间", bool(w._params.get_stat("03-1").get("at")), w._params.get_stat("03-1"))

    # 回帧不匹配：喂一帧 AFN 不同的（这里用别的命令的帧，AFN/Fn 都不同）
    w._trees[C.PAGE_READ].setCurrentItem(w._find_leaf(w._trees[C.PAGE_READ], "03-2"))
    app.processEvents()
    w._checked[C.PAGE_READ] = ["03-2"]
    w._on_send()
    pump(app)
    cmd10 = next(c for c in C.all_commands() if c.key == "10-1")
    other = W.core.build_frame(cmd10, C.default_values(cmd10))
    w._on_frame(other)
    pump(app)
    # 按协议本质：无关帧不立即定性，先记「收到过但都不属于本命令」，等超时才落状态
    check("无关帧不立即写状态", w._params.get_stat("03-2").get("state"), None)
    w._on_reply_timeout()
    pump(app)
    check("超时后记为「非本命令响应」",
          w._params.get_stat("03-2").get("state"), S.STATE_MISMATCH)

    # 无响应：重试 0 次，直接超时
    w._trees[C.PAGE_READ].setCurrentItem(w._find_leaf(w._trees[C.PAGE_READ], "03-3"))
    app.processEvents()
    w._checked[C.PAGE_READ] = ["03-3"]
    w._on_send()
    pump(app)
    w._on_reply_timeout()
    pump(app)
    check("超时 → no_reply", w._params.get_stat("03-3").get("state"), S.STATE_NO_REPLY)
    check_true("无响应依据含毫秒", "ms" in w._params.get_stat("03-3").get("reason", ""),
               w._params.get_stat("03-3"))

    # 表格渲染
    # 统计只算可下发的下行命令（上行 19 条不参与，避免对被测设备上报内容给结论）
    check("统计表行数 = 可下发命令数", w.stats_table.rowCount(),
          len([c for c in C.all_commands() if c.direction == "down"]))
    check_true("汇总文案已刷新", w.lbl_stats.text().startswith("共 "), w.lbl_stats.text())
    row_for_03 = next(r for r in range(w.stats_table.rowCount())
                      if w.stats_table.item(r, 0).text() == "03H"
                      and w.stats_table.item(r, 1).text() == "F1")
    check("统计表 03-1 显示支持", w.stats_table.item(row_for_03, 5).text(), "支持")

    # EB 页不计入统计（DI 口径无字段级判据）
    w._select_page(C.PAGE_EB, notify=True)
    app.processEvents()
    w._trees[C.PAGE_EB].setCurrentItem(w._find_leaf(w._trees[C.PAGE_EB], "EB030001"))
    app.processEvents()
    w._checked[C.PAGE_EB] = ["EB030001"]
    w._on_send()
    pump(app)
    w._on_frame(worker.sent[-1])
    pump(app)
    check("EB 不写统计", w._params.get_stat("EB030001"), {})

    # 日志落盘
    logfile = w._session_log.path()
    check_true("日志文件已生成", logfile.exists(), logfile)
    body = logfile.read_text(encoding="utf-8")
    check_true("日志文件含 TX/RX", "[TX]" in body and "[RX]" in body, body[:120])
    check_true("日志文件每行带时间戳", all(line.startswith("[") for line in body.splitlines()),
               body.splitlines()[:2])

    # 清空日志/报文：清缓冲不清文件
    pump(app)                                  # 先让队列收尾日志落完
    before = len(logfile.read_text(encoding="utf-8").splitlines())
    w._on_clear()
    app.processEvents()
    check("清空后面板为空", w.log_text.toPlainText(), "")
    check("清空后会话缓冲为空", w._session_log.lines(), [])
    check("清空不动已落盘历史", len(logfile.read_text(encoding="utf-8").splitlines()), before)
    w.close()


# ══════════════════════════════════════════════════════════════════════
# [9] 清理所有参数
# ══════════════════════════════════════════════════════════════════════
def test_clear_params():
    section("[9] 清理所有参数")
    w, _worker, app = make_widget()
    w.edit_src.setText("000000000009")
    w.spin_timeout.setValue(2500)
    w._select_page(C.PAGE_WRITE, notify=True)
    app.processEvents()
    w._trees[C.PAGE_WRITE].setCurrentItem(w._find_leaf(w._trees[C.PAGE_WRITE], "05-1"))
    app.processEvents()
    name = _set_first_text(w, "001122334455")
    w.edit_raw_data.setText("11 22")
    w._params.set_stat("03-1", S.STATE_SUPPORT, "确认")

    w._on_clear_params()
    app.processEvents()
    check("命令参数清空", w._params.param_count(), 0)
    check("支持统计保留", w._params.get_stat("03-1").get("state"), S.STATE_SUPPORT)
    check("全局测试参数保留（源地址）", w.edit_src.text(), "000000000009")
    check("全局测试参数保留（超时）", w.spin_timeout.value(), 2500)
    widget = next(x[1] for x in w._field_widgets if x[0].get("name") == name)
    got = widget.text() if isinstance(widget, QLineEdit) else widget.value()
    check("控件打回默认值", got, "000000000000")
    check("附加数据清空", w.edit_raw_data.text(), "")
    check_true("日志有清理记录", "已清理所有命令参数" in w.log_text.toPlainText(),
               w.log_text.toPlainText()[-80:])

    # 清理后切走再切回，不应把默认值写回存档
    w._trees[C.PAGE_WRITE].setCurrentItem(w._find_leaf(w._trees[C.PAGE_WRITE], "05-2"))
    app.processEvents()
    w._trees[C.PAGE_WRITE].setCurrentItem(w._find_leaf(w._trees[C.PAGE_WRITE], "05-1"))
    app.processEvents()
    check("清理后默认态不再落档", w._params.param_count(), 0)
    w.close()


def main():
    test_param_store()
    test_classify()
    test_summarize()
    test_session_log()
    test_widget_params()
    test_select_all_pages()
    test_command_label()
    test_stats_and_log()
    test_clear_params()

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
