# -*- coding: utf-8 -*-
"""协议7 测试页 —— **AFN/Fn 支持判定口径**（按 Q/GDW 10376.2 报文本质）。

覆盖：
  [1] 命令分类：只需确认（01/04/05/11/12 及福建 51/54/55 + 主动上报）vs 必须同命令数据
  [2] 确认帧：设置类 → 支持；抄表类 → 只算受理（非终态）
  [3] 否认帧：错误状态字 4/10 → 不支持；其余（0/9/11/12/109/110/111）→ 支持但执行报错
  [4] 同命令上行数据 → 支持；同命令但字段级失败 → 支持但执行报错
  [5] 无关帧/坏帧 → 非终态（不误判）
  [6] 页面状态机：确认推进、抄表等数据、超时记「仅确认·无数据」、否认立即推进
  [7] 汇总口径：「仅确认·无数据」不计入支持

运行: python test/test_gdw_test_expect.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

_config_sandbox.install()

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: QMessageBox.StandardButton.Yes).start()

import gdw_test_core as C  # noqa: E402
import gdw_test_expect as E  # noqa: E402
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


def cmd(key):
    return next(c for c in C.all_commands() if c.key == key)


def confirm_frame() -> bytes:
    """AFN=00H F1 确认：4B 信道状态 + 2B 等待时间。"""
    base = next(c for c in C.all_commands() if (c.afn, c.fn) == (0, 1))
    return C.build_frame(base, C.default_values(base), raw_data=bytes.fromhex("FF000002"))


def deny_frame(code: int) -> bytes:
    """AFN=00H F2 否认：1B 错误状态字。"""
    base = next(c for c in C.all_commands() if (c.afn, c.fn) == (0, 2))
    return C.build_frame(base, C.default_values(base), raw_data=bytes([code]))


# ══════════════════════════════════════════════════════════════════════
# [1] 分类
# ══════════════════════════════════════════════════════════════════════
def test_classification():
    section("[1] 命令分类（文档出处见模块注释）")
    for key in ("01-1", "04-1", "05-1", "05-16", "11-1", "12-1", "10-1"):
        afn = cmd(key).afn
        expect = "confirm" if afn in E.EXPECT_CONFIRM_AFNS else "data"
        check(f"{key}（AFN {afn:02X}H）→ {expect}", E.expect_mode(cmd(key)), expect)
    check("03H 查询数据需数据", E.expect_mode(cmd("03-1")), "data")
    check("04H 链路接口检测只需确认", E.expect_mode(cmd("04-1")), "confirm")
    check("11H 路由设置类只需确认", E.expect_mode(cmd("11-1")), "confirm")
    check("12H 路由控制类只需确认", E.expect_mode(cmd("12-1")), "confirm")
    check("10H 路由查询类需数据", E.expect_mode(cmd("10-1")), "data")
    check("52H F11 并发抄表需数据", E.expect_mode(cmd("52-11")), "data")
    check("51H 福建初始化只需确认", E.expect_mode(cmd("51-1")), "confirm")
    check("56H 福建主动上报归为上行（不下发）", E.expect_mode(cmd("56-2")), "uplink")
    check("F0H LME 查询需数据", E.expect_mode(cmd("F0-62")), "data")

    summary = E.expect_summary(C.all_commands())
    check("可下发 + 仅接收 = 命令总数",
          summary["confirm"] + summary["data"] + summary["uplink"], len(list(C.all_commands())))
    check("上行命令数 = schema 里 direction=up 的条数", summary["uplink"],
          len([c for c in C.all_commands() if c.direction == "up"]))
    check_true("确认即支持的条数少于需数据（新口径）",
               summary["confirm"] < summary["data"], summary)

    # 未知 AFN（自定义）保守按 data
    class Fake:
        afn = 0x7E
        fn = 1
        direction = "down"
    check("未收录 AFN 保守按 data", E.expect_mode(Fake()), "data")

    class NoDir:
        afn = 0x7E
        fn = 1
    check("缺 direction 的自定义命令按可下发处理", E.is_sendable(NoDir()), True)
    check("显式 up 才算上行", (E.is_uplink_only(cmd("06-1")), E.is_uplink_only(cmd("05-1"))),
          (True, False))


# ══════════════════════════════════════════════════════════════════════
# [2] 确认帧
# ══════════════════════════════════════════════════════════════════════
def test_confirm():
    section("[2] 确认帧（AFN=00H F1）")
    j = E.judge(cmd("05-1"), confirm_frame())
    check("设置类收到确认 → 支持", j["verdict"], E.V_CONFIRM)
    check("设置类确认是终态", j["final"], True)
    check_true("依据带命令状态", "命令状态" in j["reason"], j["reason"])

    j2 = E.judge(cmd("03-1"), confirm_frame())
    check("抄表类收到确认 → 只算受理", j2["verdict"], E.V_WAITING)
    check("抄表类确认不是终态（要继续等数据）", j2["final"], False)
    check_true("依据写明等待数据", "等待" in j2["reason"], j2["reason"])


# ══════════════════════════════════════════════════════════════════════
# [3] 否认帧
# ══════════════════════════════════════════════════════════════════════
def test_deny():
    section("[3] 否认帧（AFN=00H F2，表 10 错误状态字）")
    for code, desc in ((4, "信息类不存在"), (10, "主节点不支持此命令")):
        j = E.judge(cmd("05-1"), deny_frame(code))
        check(f"错误状态字 {code}（{desc}）→ 不支持", j["verdict"], E.V_UNSUPPORTED)
        check(f"错误状态字 {code} 是终态", j["final"], True)
        check_true(f"依据带原文「{desc}」", desc in j["reason"], j["reason"])

    for code in (0, 9, 11, 12, 109, 110, 111):
        j = E.judge(cmd("05-1"), deny_frame(code))
        check(f"错误状态字 {code}（{E.error_status_text(code)}）→ 支持但报错",
              j["verdict"], E.V_DENY_FAIL)
        check_true(f"错误状态字 {code} 依据带中文含义",
                   E.error_status_text(code) in j["reason"], j["reason"])

    check("未收录错误码也有兜底文案", E.error_status_text(200), "错误状态字 200（未收录）")
    check("错误码 → 统计状态映射",
          [E.verdict_state(v) for v in (E.V_CONFIRM, E.V_DATA, E.V_DENY_FAIL, E.V_UNSUPPORTED)],
          ["support", "support", "support_error", "unsupported"])


# ══════════════════════════════════════════════════════════════════════
# [4][5] 数据帧 / 无关帧
# ══════════════════════════════════════════════════════════════════════
def test_data_and_other():
    section("[4][5] 同命令数据 / 无关帧 / 坏帧")
    c = cmd("03-1")
    j = E.judge(c, C.build_frame(c, C.default_values(c)))
    check("同 AFN/Fn 数据 → 支持", j["verdict"], E.V_DATA)
    check("数据终态", j["final"], True)

    other = C.build_frame(cmd("10-1"), {})
    j2 = E.judge(c, other)
    check("别的命令帧 → 非本命令响应", j2["verdict"], E.V_MISMATCH)
    check("无关帧不是终态（继续等）", j2["final"], False)
    check_true("依据写明收到/期望", "10H" in j2["reason"] and "03H" in j2["reason"], j2["reason"])

    short = bytes.fromhex("680400000000")
    j3 = E.judge(c, short)
    check("坏帧不判支持", (j3["verdict"], j3["final"]), (E.V_BAD, False))

    # 抄表类同命令帧但校验坏 → 不误判成功
    bad = bytearray(C.build_frame(c, C.default_values(c)))
    bad[-2] ^= 0xFF
    j4 = E.judge(c, bytes(bad))
    check_true("校验坏的帧不判支持", j4["verdict"] in (E.V_BAD, E.V_MISMATCH), j4["verdict"])

    # 确认/否认不影响「数据类必须数据」的原则
    check("抄表类否认也是终态（设备明确拒绝）",
          E.judge(c, deny_frame(9))["final"], True)


# ══════════════════════════════════════════════════════════════════════
# 页面夹具
# ══════════════════════════════════════════════════════════════════════
class FakeSerial(QObject):
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
        return None


def make_widget():
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    worker = FakeSerial()
    w.set_serial_worker(worker)
    w.show()
    app.processEvents()
    return w, worker, app


def pump(app, ms=40):
    QTest.qWait(ms)
    app.processEvents()


def send_one(w, worker, app, page, key):
    w._select_page(page, notify=False)
    w._trees[page].setCurrentItem(w._find_leaf(w._trees[page], key))
    app.processEvents()
    w._checked[page] = [key]
    before = len(worker.sent)
    w._on_send()
    pump(app)
    assert len(worker.sent) == before + 1, "命令没发出去"
    return worker.sent[-1]


# ══════════════════════════════════════════════════════════════════════
# [6][7] 页面状态机与汇总
# ══════════════════════════════════════════════════════════════════════
def test_widget_flow():
    section("[6] 页面状态机")
    w, worker, app = make_widget()
    w.spin_retries.setValue(0)

    # 设置类：确认 → 支持，且立刻推进
    send_one(w, worker, app, C.PAGE_WRITE, "05-1")
    w._on_frame(confirm_frame())
    pump(app)
    check("设置类确认 → support", w._params.get_stat("05-1").get("state"), S.STATE_SUPPORT)
    check("设置类确认后已释放等待", w._awaiting, False)
    check_true("信息表结果写明「支持（确认）」",
               "支持（确认）" in w.info_table.item(0, 3).text(), w.info_table.item(0, 3).text())

    # 抄表类：确认只受理，不推进；超时 → 仅确认·无数据
    send_one(w, worker, app, C.PAGE_READ, "03-1")
    w._on_frame(confirm_frame())
    pump(app)
    check("抄表类确认后仍在等数据", w._awaiting, True)
    check("抄表类确认不写终态", w._params.get_stat("03-1").get("state"), None)
    check_true("日志提示等待数据", "等待同命令数据" in w.log_text.toPlainText(),
               w.log_text.toPlainText().splitlines()[-1])
    w._on_reply_timeout()
    pump(app)
    stat = w._params.get_stat("03-1")
    check("超时 → 仅确认·无数据", stat.get("state"), S.STATE_CONFIRM_ONLY)
    check_true("依据说明没收到同命令数据", "同 AFN/Fn" in stat.get("reason", ""), stat)

    # 抄表类：拿到同命令数据 → 支持
    send_one(w, worker, app, C.PAGE_READ, "03-2")
    data = C.build_frame(cmd("03-2"), C.default_values(cmd("03-2")))
    w._on_frame(data)
    pump(app)
    check("同命令数据 → support", w._params.get_stat("03-2").get("state"), S.STATE_SUPPORT)

    # 否认 code=10 → 不支持，立即推进
    send_one(w, worker, app, C.PAGE_WRITE, "05-2")
    w._on_frame(deny_frame(10))
    pump(app)
    check("否认(10) → unsupported", w._params.get_stat("05-2").get("state"), S.STATE_UNSUPPORTED)
    check("否认后已释放等待", w._awaiting, False)

    section("[7] 汇总口径")
    summary = w._stats_summary()
    counts = summary["counts"]
    check("不支持计入 unsupported", counts[S.STATE_UNSUPPORTED], 1)
    check("仅确认无数据单独计", counts[S.STATE_CONFIRM_ONLY], 1)
    check("支持计数含确认与数据", counts[S.STATE_SUPPORT], 2)
    text = w.lbl_stats.text()
    check_true("汇总文案列出新状态",
               "不支持 1" in text and "仅确认无数据 1" in text, text)
    check("仅确认不计入 AFN 支持数",
          summary["per_afn"][0x03]["supported"], 1)      # 只有 03-2 数据那条算
    w.close()


# ══════════════════════════════════════════════════════════════════════
# [8] 历史兼容：配置从「按节点展开」改为「不展开」时旧结论不丢
# ══════════════════════════════════════════════════════════════════════
def test_aggregate_compat():
    section("[8] 统计键变更后的聚合兼容")
    import gdw_test_network as N
    net = N.NetworkConfig(slaves=[N.SlaveNode("001122334455", 2, True),
                                  N.SlaveNode("006677889900", 3, True)])
    # 03H F1 不按节点展开，但历史记录是 key@地址 形式
    stats = {S.stat_key("03-1", "001122334455"): {"state": S.STATE_SUPPORT,
                                                  "reason": "有数据", "at": "t1"},
             S.stat_key("03-1", "006677889900"): {"state": S.STATE_CONFIRM_ONLY,
                                                  "reason": "仅确认", "at": "t2"}}
    summary = S.summarize(C.all_commands(), stats, net.nodes_or_placeholder())
    row = next(r for r in summary["rows"] if r[0] == "03H" and r[1] == "F1")
    check("不展开时聚合各节点结果（任一支持即支持）", row[5], "支持")
    check("聚合优先取最「强」的结论", "有数据" in row[6], True)

    # 全部节点都无响应时聚合出「无响应」
    stats2 = {S.stat_key("03-1", "001122334455"): {"state": S.STATE_NO_REPLY, "reason": "a", "at": ""},
              S.stat_key("03-1", "006677889900"): {"state": S.STATE_NO_REPLY, "reason": "b", "at": ""}}
    summary2 = S.summarize(C.all_commands(), stats2, net.nodes_or_placeholder())
    row2 = next(r for r in summary2["rows"] if r[0] == "03H" and r[1] == "F1")
    check("全无响应聚合为无响应", row2[5], "无响应")


# ══════════════════════════════════════════════════════════════════════
# [9] 上行命令：不下发、不判支持（错误测试方法的防线）
# ══════════════════════════════════════════════════════════════════════
def test_uplink_not_sendable():
    section("[9] 上行命令只接收、不下发")
    cmds = list(C.all_commands())
    uplink = E.uplink_commands(cmds)
    check("上行命令共 19 条（00H/50H 应答 + 06H/56H 上报）", len(uplink), 19)
    check("全部 direction=up", {c.direction for c in uplink}, {"up"})
    check("可下发 103 条", len(E.sendable_commands(cmds)), 103)
    for key in ("06-1", "06-5", "56-2", "00-1", "50-2"):
        check(f"{key} 归为上行", E.expect_mode(cmd(key)), "uplink")

    # 页面：树上不可勾、全选勾不上、混进勾选清单会被跳过并记日志
    w, worker, app = make_widget()
    w._select_page(C.PAGE_REPORT, notify=False)
    leaf = w._find_leaf(w._trees[C.PAGE_REPORT], "06-1")
    check("上行叶子不可勾选",
          bool(leaf.flags() & Qt.ItemFlag.ItemIsUserCheckable), False)
    w._set_all_checked(True)
    app.processEvents()
    check("上报页全选勾不到任何可下发项", len(w._checked.get(C.PAGE_REPORT, [])), 0)
    check_true("标签说明另有仅接收项",
               "另有 19 条仅接收" in w.lbl_checked.text(), w.lbl_checked.text())

    w._checked[C.PAGE_REPORT] = ["06-1", "06-2"]
    check("混入上行后发送计划为空", w._targets(), [])
    check_true("日志明确跳过原因",
               "上行命令不下发" in w.log_text.toPlainText(), w.log_text.toPlainText()[-80:])

    # 统计不把上行命令算进分母
    check("统计命令集不含上行",
          all(c.direction == "down" for c in w._stats_commands()), True)
    check("报告附录列出上行命令", len(w._uplink_command_rows()), 19)
    w.close()


def test_error_hints():
    section("[9] 否认错误码处置建议")
    check_true("长度错给出补充数据单元的建议", "附加数据" in E.error_hint(2), E.error_hint(2))
    check_true("表号不存在提示地址线序/建档",
               "低字节在前" in E.error_hint(7) and "11H F1" in E.error_hint(7), E.error_hint(7))
    check_true("不在网提示先建档组网", "11H F102" in E.error_hint(12), E.error_hint(12))
    check("未收录错误码返回空", E.error_hint(200), "")
    check("None 不炸", E.error_hint(None), "")

    # 判定结果里带上建议（页面日志直接可读）
    verdict = E.judge(cmd("10-104"), deny_frame(2))
    check("否认判定带 error_code", verdict.get("error_code"), 2)
    check_true("hint 已随判定返回", "附加数据" in str(verdict.get("hint")), verdict.get("hint"))
    check_true("表号不存在建议已挂到判定",
               "低字节在前" in str(E.judge(cmd("04-3"), deny_frame(7)).get("hint")))


def main():
    test_classification()
    test_confirm()
    test_deny()
    test_data_and_other()
    test_widget_flow()
    test_aggregate_compat()
    test_uplink_not_sendable()
    test_error_hints()

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
