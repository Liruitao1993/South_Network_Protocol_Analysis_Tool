# -*- coding: utf-8 -*-
"""协议7「国网协议测试」页 —— **1 对 2 组网遍历测试** 回归。

覆盖：
  [1] 组网参数模型：从节点归一/校验、序列化往返、非法值兜底、摘要
  [2] 字段语义绑定：列表命令一次放两节点、单节点命令按节点取值、手改优先、开关生效
  [3] 节点展开：52H F11/52H F1/10H F3 展开为 2 帧、列表类命令不展开、无节点时退化单发
  [4] 树级联勾选：勾父=整组全选、父半勾、全勾/全清、跨页全选
  [5] 页面组网参数：控件 ↔ 模型往返、落盘重开还在、提示文案
  [6] 统计粒度：命令 × 从节点两行、AFN 汇总按命令去重
  [7] 遍历报告：HTML 结构/环境段/AFN 汇总/逐条/交互明细/转义
  [8] 端到端：配 2 节点 → 勾 52H F11 → 发两帧（各带自己的节点地址）

运行: python test/test_gdw_test_network.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

_cfg_dir = _config_sandbox.install()

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: QMessageBox.StandardButton.Yes).start()

import gdw_test_core as C  # noqa: E402
import gdw_test_network as N  # noqa: E402
import gdw_test_report as R  # noqa: E402
import gdw_test_store as S  # noqa: E402
import gdw_test_widget as W  # noqa: E402

FAILED = []
CHECKS = [0]

NODE_A = "001122334455"
NODE_B = "006677889900"


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


def make_net(a=NODE_A, b=NODE_B, proto_b=N.PROTO_698_45):
    return N.NetworkConfig(
        slaves=[N.SlaveNode(a, N.PROTO_645_2007, True),
                N.SlaveNode(b, proto_b, True)],
        cco_addr="123456789012", carrier_band=1, radio_channel=5,
    )


# ══════════════════════════════════════════════════════════════════════
# [1] 组网参数模型
# ══════════════════════════════════════════════════════════════════════
def test_network_model():
    section("[1] 组网参数模型")
    check("地址归一补零", N.normalize_addr("1122334455"), "001122334455")
    check("地址非数字被拒", N.normalize_addr("11223344556X"), "")
    check("地址超长被拒", N.normalize_addr("1234567890123"), "")
    check("addr_ok 要求 12 位", (N.addr_ok("001122334455"), N.addr_ok("1122334455")),
          (True, False))

    net = make_net()
    check("启用节点 2 个", len(net.active_slaves()), 2)
    net.slaves[1].enabled = False
    check("未启用节点被排除", [n.addr for n in net.active_slaves()], [NODE_A])
    net.slaves[1].enabled = True
    net.slaves[1].addr = ""
    check("空地址节点被排除", [n.addr for n in net.active_slaves()], [NODE_A])
    check("统计占位仍计启用节点", len(net.nodes_or_placeholder()), 2)

    data = make_net().as_dict()
    back = N.NetworkConfig.from_dict(data)
    check("序列化往返：节点", [(n.addr, n.proto, n.enabled) for n in back.slaves],
          [(NODE_A, N.PROTO_645_2007, True), (NODE_B, N.PROTO_698_45, True)])
    check("序列化往返：CCO/频段", (back.cco_addr, back.carrier_band, back.radio_channel),
          ("123456789012", 1, 5))
    check("序列化往返：开关", (back.auto_fill, back.fanout), (True, True))

    broken = N.NetworkConfig.from_dict({
        "slaves": [{"addr": "x", "proto": 99}, "粗"],
        "carrier_band": 88, "radio_mod": 42, "radio_channel": "z",
        "auto_fill": 0,
    })
    check("非法协议类型兜底 645-2007", broken.slaves[0].proto, N.PROTO_645_2007)
    check("非法频段兜底第一个", broken.carrier_band in N.CARRIER_BANDS, True)
    check("非法信道号兜底 1", broken.radio_channel, 1)
    check("自动填充开关读成布尔", broken.auto_fill, False)
    check("从节点数量补齐 2 条", len(broken.slaves), 2)

    env = dict(N.summary_env(make_net()))
    check("摘要含 CCO", env.get("CCO 地址"), "123456789012")
    check_true("摘要含两个从节点", "从节点 1" in env and "从节点 2" in env, env)
    check_true("摘要含频段文案", "1.758" not in env["载波频段"] and "2.441" in env["载波频段"],
               env["载波频段"])


# ══════════════════════════════════════════════════════════════════════
# [2] 字段语义绑定
# ══════════════════════════════════════════════════════════════════════
def test_binding():
    section("[2] 字段语义绑定")
    net = make_net()
    add = cmd("11-1")
    values, applied = N.apply_binding(C.default_values(add), add, net)
    rows = values.get("从节点列表")
    check("添加从节点：一次填两个节点", len(rows), 2)
    check("列表里带各自协议类型", [r.get("通信协议类型") for r in rows],
          [N.PROTO_645_2007, N.PROTO_698_45])
    check("绑定字段名", applied, ["从节点列表"])

    conc = cmd("52-11")
    v1, _ = N.apply_binding({}, conc, net, net.active_slaves()[0])
    v2, _ = N.apply_binding({}, conc, net, net.active_slaves()[1])
    check("并发抄表按节点取地址", (v1.get("通信对象地址"), v2.get("通信对象地址")),
          (NODE_A, NODE_B))
    check("并发抄表按节点取规约", (v1.get("规约类型"), v2.get("规约类型")),
          (N.PROTO_645_2007, N.PROTO_698_45))

    # 列表行键名必须取 item_fields 名，否则地址会静默回落到全 0
    sub_cmd = cmd("14-1")
    vs, aps = N.apply_binding(C.default_values(sub_cmd), sub_cmd, net)
    check("14H F1 附属节点列表按 item 名绑定", aps, ["从节点附属节点列表"])
    check("14H F1 附属节点地址取真实表地址",
          [r.get("从节点附属节点地址") for r in vs.get("从节点附属节点列表", [])],
          [NODE_A, NODE_B])
    sub13 = cmd("13-1")
    v13, _ = N.apply_binding(C.default_values(sub13), sub13, net)
    check("13H F1 附属节点地址同样按 item 名绑定",
          [r.get("从节点附属节点地址") for r in v13.get("从节点附属节点列表", [])],
          [NODE_A, NODE_B])

    cco_cmd = cmd("05-1")
    vc, _ = N.apply_binding({}, cco_cmd, net)
    check("设置主节点地址 = CCO 地址", vc.get("主节点地址"), "123456789012")

    # 04H F3 报文通信测试：目标地址吃表地址、报文长度随内容派生（否则 CCO 回「表号不存在」）
    com_cmd = cmd("04-3")
    vcom = C.default_values(com_cmd)
    vcom["报文内容"] = "68 01 00 00 00 00 00 68 11 04 33 33 34 33 B3 16"
    vcom, apc = N.apply_binding(vcom, com_cmd, net, net.active_slaves()[0])
    check("04H F3 目标地址按从节点绑定", apc, ["目标地址", "通信协议类型"])
    frame = C.build_frame(com_cmd, vcom, src="123456789012", dst=NODE_A)
    row = {r[0].strip(): r for r in C.parse_table(frame)}
    check("04H F3 目标地址回读一致", row["目标地址"][2], NODE_A)
    check("04H F3 报文长度自动派生 16", row["报文长度"][2], "16")

    band_cmd = cmd("05-16")
    vb, _ = N.apply_binding({}, band_cmd, net)
    check("载波频段进 05H F16", vb.get("宽带载波频段"), 1)

    radio_cmd = cmd("05-17")
    vr, ap = N.apply_binding({}, radio_cmd, net)
    check("无线参数进 05H F17", (vr.get("无线信道编号"), vr.get("信道协商使能")), (5, 1))
    check("无线三条字段都绑上", sorted(ap), sorted(["无线调制方式", "无线信道编号", "信道协商使能"]))

    # 手改优先
    vd, apd = N.apply_binding({"通信对象地址": "999999999999"}, conc, net,
                              net.active_slaves()[0], dirty=["通信对象地址"])
    check("手改字段不被覆盖", vd.get("通信对象地址"), "999999999999")
    check("未手改字段照旧填", "规约类型" in apd, True)

    # 开关
    net.auto_fill = False
    vf, apf = N.apply_binding({}, conc, net, net.active_slaves()[0])
    check("关掉自动填充后不写值", (vf.get("通信对象地址"), apf), (None, []))

    # 不认识的字段不硬塞
    net.auto_fill = True
    plain = cmd("10-1")
    vp, app = N.apply_binding({}, plain, net)
    check("无绑定字段的命令不受影响", (vp, app), ({}, []))


# ══════════════════════════════════════════════════════════════════════
# [3] 节点展开
# ══════════════════════════════════════════════════════════════════════
def test_fanout():
    section("[3] 节点展开")
    net = make_net()
    for key in ("52-11", "52-1", "10-3", "05-200", "11-3"):
        check_true(f"{key} 判定为按节点展开", N.is_node_scoped(cmd(key)), key)
    for key in ("11-1", "10-2", "13-1", "05-1", "10-1"):
        check(f"{key} 不展开（列表/无单节点字段）", N.is_node_scoped(cmd(key)), False)

    plan, skipped = N.plan_targets([("write", "52-11")], cmd, net)
    check("单节点命令展开成 2 帧", plan,
          [("write", "52-11", NODE_A), ("write", "52-11", NODE_B)])
    check("没有跳过项", skipped, [])
    plan2, _ = N.plan_targets([("write", "11-1")], cmd, net)
    check("列表命令只 1 帧", plan2, [("write", "11-1", "")])

    # 上行命令（06H 上报）不得下发，单列到 skipped
    plan3, skipped3 = N.plan_targets([("report", "06-1"), ("write", "05-1")], cmd, net)
    check("上行命令被跳过", skipped3, [("report", "06-1")])
    check("只下发下行命令", [k for _p, k, _n in plan3], ["05-1"])

    net.fanout = False
    check("关掉展开开关后退化为单发",
          N.plan_targets([("write", "52-11")], cmd, net)[0], [("write", "52-11", "")])

    net.fanout = True
    net.slaves[0].addr = ""
    net.slaves[1].addr = ""
    check("没有可用从节点时仍能发（不吞命令）",
          N.plan_targets([("write", "52-11")], cmd, net)[0], [("write", "52-11", "")])


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
        raise AssertionError("测试页不得关闭共享串口")


def make_widget():
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    worker = FakeSerial()
    w.set_serial_worker(worker)
    w.show()
    app.processEvents()
    return w, worker, app


def pump(app, ms: int = 40):
    QTest.qWait(ms)
    app.processEvents()


def configure_net(w, app, a=NODE_A, b=NODE_B, proto_b=N.PROTO_698_45):
    w.node_widgets[0]["addr"].setText(a)
    w.node_widgets[1]["addr"].setText(b)
    for idx, proto in ((0, N.PROTO_645_2007), (1, proto_b)):
        combo = w.node_widgets[idx]["proto"]
        combo.setCurrentIndex(max(0, combo.findData(proto)))
    w.edit_cco_addr.setText("123456789012")
    w._on_network_edited()
    app.processEvents()


# ══════════════════════════════════════════════════════════════════════
# [4] 树级联勾选
# ══════════════════════════════════════════════════════════════════════
def subtree_leaves(item):
    """某组节点下的全部叶子（用于断言级联范围）。"""
    out = []
    for i in range(item.childCount()):
        child = item.child(i)
        if child.data(0, W.LEAF_KEY_ROLE):
            out.append(child)
        else:
            out.extend(subtree_leaves(child))
    return out


def test_cascade():
    section("[4] 树级联勾选")
    w, _worker, app = make_widget()
    w._select_page(C.PAGE_READ, notify=False)
    tree = w._trees[C.PAGE_READ]
    cat = tree.topLevelItem(0)
    grp = cat.child(0)

    check("组节点可勾选", bool(cat.flags() & Qt.ItemFlag.ItemIsUserCheckable), True)
    grp.setCheckState(0, Qt.CheckState.Checked)
    app.processEvents()
    picked = [leaf for leaf in w._iter_leaves(tree)
              if leaf.checkState(0) == Qt.CheckState.Checked]
    check("勾一个 AFN 组 = 该组全部子命令", len(picked), len(subtree_leaves(grp)))
    check("_checked 与树一致", len(w._checked[C.PAGE_READ]), len(subtree_leaves(grp)))
    check("未全选时上级为半勾", cat.checkState(0), Qt.CheckState.PartiallyChecked)

    grp.setCheckState(0, Qt.CheckState.Unchecked)
    app.processEvents()
    check("取消组 = 该组全部取消", len(w._checked[C.PAGE_READ]), 0)
    check("全不选时上级为未勾", cat.checkState(0), Qt.CheckState.Unchecked)

    cat.setCheckState(0, Qt.CheckState.Checked)
    app.processEvents()
    cat_leaves = subtree_leaves(cat)
    check("勾功能域 = 该域全部叶子", len(w._checked[C.PAGE_READ]), len(cat_leaves))
    check("功能域自身为勾", cat.checkState(0), Qt.CheckState.Checked)

    # 取消该域里的一个子命令 → 父变半勾
    cat_leaves[0].setCheckState(0, Qt.CheckState.Unchecked)
    app.processEvents()
    check("取消单个子命令后父变半勾", cat.checkState(0), Qt.CheckState.PartiallyChecked)
    check("计数随之减 1", len(w._checked[C.PAGE_READ]), len(cat_leaves) - 1)

    # 跨页全选后再全清
    w._set_all_pages(True)
    app.processEvents()
    # 上行命令（主动上报页 19 条）不参与全选，可下发 = 122 - 19 + 75(EB) = 178
    # 流程页（9 条用例）不进命令队列，不计入合计
    total = sum(w._sendable_count(k) for k, _l in C.PAGES)
    checked_total = sum(len(v) for k, v in w._checked.items() if k != C.PAGE_FLOW)
    check("多页全选后合计正确", (checked_total, total), (178, 178))
    w._set_all_pages(False)
    app.processEvents()
    check("多页全清后为 0", sum(len(v) for v in w._checked.values()), 0)
    w.close()


# ══════════════════════════════════════════════════════════════════════
# [5] 页面组网参数
# ══════════════════════════════════════════════════════════════════════
def test_widget_network():
    section("[5] 页面组网参数")
    w, _worker, app = make_widget()
    configure_net(w, app)
    net = w._collect_network()
    check("控件 → 模型：两个节点", [(n.addr, n.proto) for n in net.slaves],
          [(NODE_A, N.PROTO_645_2007), (NODE_B, N.PROTO_698_45)])
    check("控件 → 模型：CCO", net.cco_addr, "123456789012")
    check_true("提示文案含两个地址",
               NODE_A in w.lbl_network_hint.text() and NODE_B in w.lbl_network_hint.text(),
               w.lbl_network_hint.text())

    # 落盘 → 重开恢复
    w._save_persisted()
    w2, _w2, app2 = make_widget()
    check("重开后节点地址恢复",
          [n.addr for n in w2._collect_network().slaves], [NODE_A, NODE_B])
    check("重开后 CCO 恢复", w2.edit_cco_addr.text(), "123456789012")

    # 列表命令：预览帧里必须真有两个节点（回归：dirty 按控件值判定，曾把列表绑定量掉）
    w._select_page(C.PAGE_WRITE, notify=False)
    w._trees[C.PAGE_WRITE].setCurrentItem(w._find_leaf(w._trees[C.PAGE_WRITE], "11-1"))
    app.processEvents()
    add_preview = w.plain_cmd_preview.toPlainText()
    check_true("添加从节点预览含节点 A", "55 44 33 22 11 00" in add_preview, add_preview[:140])
    check_true("添加从节点预览含节点 B", "00 99 88 77 66 00" in add_preview, add_preview[:140])

    # 非单节点命令不该出现「按从节点展开」
    w._trees[C.PAGE_WRITE].setCurrentItem(w._find_leaf(w._trees[C.PAGE_WRITE], "05-1"))
    app.processEvents()
    cco_preview = w.plain_cmd_preview.toPlainText()
    check_true("设置 CCO 地址预览填了 CCO", "12 34 56 78 90 12" in cco_preview, cco_preview[:140])
    check("非单节点命令不提示展开", "按从节点展开" in cco_preview, False)

    # 关掉自动填充 → 提示与行为同步
    w.check_autofill.setChecked(False)
    app.processEvents()
    check_true("关自动填充后提示变化", "自动填充已关闭" in w.lbl_network_hint.text(),
               w.lbl_network_hint.text())
    check("关自动填充后绑定不写值",
          N.apply_binding({}, cmd("52-11"), w._collect_network(),
                          w._collect_network().active_slaves()[0])[1], [])
    w.close()
    w2.close()


# ══════════════════════════════════════════════════════════════════════
# [6] 统计粒度
# ══════════════════════════════════════════════════════════════════════
def test_stats_grain():
    section("[6] 统计按 命令 × 从节点")
    net = make_net()
    stats = {
        S.stat_key("10-3", NODE_A): {"state": S.STATE_SUPPORT, "reason": "确认", "at": "t1"},
        S.stat_key("10-3", NODE_B): {"state": S.STATE_NO_REPLY, "reason": "超时", "at": "t2"},
        "11-1": {"state": S.STATE_SUPPORT_ERROR, "reason": "错误代码=0x02", "at": "t3"},
    }
    summary = S.summarize(C.all_commands(), stats, net.active_slaves())
    rows_10_3 = [r for r in summary["rows"] if r[0] == "10H" and r[1] == "F3"]
    check("单节点命令每节点一行", len(rows_10_3), 2)
    check("两行各带自己的节点与状态",
          [(r[3], r[5]) for r in rows_10_3],
          [(NODE_A, "支持"), (NODE_B, "无响应")])
    rows_11_1 = [r for r in summary["rows"] if r[0] == "11H" and r[1] == "F1"]
    check("列表命令只有一行、节点为空", [(r[3], r[5]) for r in rows_11_1], [("—", "支持（执行报错）")])
    check("AFN 汇总按命令去重", summary["per_afn"][0x10]["total"],
          len([c for c in C.all_commands() if c.afn == 0x10]))
    check("该命令任一节点支持即算支持", summary["per_afn"][0x10]["supported"], 1)
    check("命令×节点 总计", summary["total"],
          len(list(C.all_commands())) + len([c for c in C.all_commands()
                                             if N.is_node_scoped(c)]))


# ══════════════════════════════════════════════════════════════════════
# [7] 遍历报告
# ══════════════════════════════════════════════════════════════════════
def test_report():
    section("[7] 遍历报告（HTML）")
    net = make_net()
    stats = {S.stat_key("10-3", NODE_A): {"state": S.STATE_SUPPORT, "reason": "确认", "at": "t1"},
             S.stat_key("10-3", NODE_B): {"state": S.STATE_MISMATCH, "reason": "AFN 不符",
                                          "at": "t2"}}
    summary = S.summarize(C.all_commands(), stats, net.active_slaves())
    env = R.report_env_rows(net, channel="串口", src="000000000000", dst="123456789012",
                            timeout_ms=1500, retries=1, tx=8, rx=7)
    html_body = R.build_report(
        env_rows=env, summary=summary,
        interactions=[{"time": "11:00:00", "direction": "TX",
                       "label": "52H F11 CCO并发抄表_福建 <b>", "node": NODE_A,
                       "result": "已发送", "frame": "68 01 <script>"}],
        log_path="logs/gdw_test_20261027.log")
    check_true("是完整 HTML", html_body.startswith("<!DOCTYPE html>")
               and html_body.rstrip().endswith("</html>"), html_body[:40])
    for keyword in ("测试环境", "AFN 支持汇总", "逐条命令结果", "交互报文明细"):
        check_true(f"含章节「{keyword}」", keyword in html_body)
    check_true("环境段带入 CCO 与节点", "123456789012" in html_body and NODE_B in html_body)
    check_true("明细带入报文", "68 01" in html_body)
    check_true("命令名做了 HTML 转义", "&lt;b&gt;" in html_body and "<script>" not in html_body)
    check_true("无外链资源（单文件可离线打开）",
               "http://" not in html_body and "https://" not in html_body)
    check_true("含支持/无响应徽标", 'class="ok"' in html_body and 'class="err"' in html_body)


# ══════════════════════════════════════════════════════════════════════
# [8] 端到端：1 对 2 展开发送
# ══════════════════════════════════════════════════════════════════════
def test_end_to_end():
    section("[8] 端到端 1 对 2 展开")
    w, worker, app = make_widget()
    configure_net(w, app)
    w._select_page(C.PAGE_WRITE, notify=True)
    app.processEvents()
    w._trees[C.PAGE_WRITE].setCurrentItem(w._find_leaf(w._trees[C.PAGE_WRITE], "52-11"))
    app.processEvents()
    preview = w.plain_cmd_preview.toPlainText()
    check_true("预览注明按节点展开", "按从节点展开" in preview and NODE_A in preview, preview)
    check_true("预览帧已带节点地址", "001122334455" not in preview.replace(" ", "")
               or "00 11 22 33 44 55" in preview, preview)

    w._checked[C.PAGE_WRITE] = ["52-11"]
    w._on_send()
    pump(app)
    check("发出第一帧", len(worker.sent), 1)
    first = C.format_hex(worker.sent[0])
    check_true("第一帧用节点 A 地址", "00 11 22 33 44 55" in first, first)

    # 喂应答推进到节点 B
    w._on_frame(worker.sent[0])
    pump(app)
    check("推进到第二个节点", len(worker.sent), 2)
    second = C.format_hex(worker.sent[1])
    check_true("第二帧用节点 B 地址", "00 66 77 88 99 00" in second, second)
    check_true("两帧地址不同", first != second)
    w._on_frame(worker.sent[1])          # 喂节点 B 的应答，让两行都落到统计里
    pump(app)

    # 统计按节点分开
    rows = [r for r in w._last_summary["rows"] if r[0] == "52H" and r[1] == "F11"]
    check("统计出现两行", len(rows), 2)
    check("节点列分别是 A/B", [r[3] for r in rows], [NODE_A, NODE_B])
    check_true("状态已记录", all(r[5] != "未测" for r in rows), rows)

    # 信息表带从节点列
    check("信息表列头含从节点",
          [w.info_table.horizontalHeaderItem(i).text() for i in range(5)],
          ["时间", "命令", "从节点", "结果", "说明"])
    w._on_stop()
    pump(app)

    # 报告导出（文件对话框打桩到沙箱）
    target = Path(_cfg_dir) / "report_test.html"
    with patch.object(W.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))):
        w._on_export_report()
    check_true("报告文件已生成", target.exists(), target)
    if target.exists():
        body = target.read_text(encoding="utf-8")
        check_true("报告含本次遍历的命令名", "CCO并发抄表" in body, body[:200])
        check_true("报告含交互明细", "68 " in body)
    w.close()


# ══════════════════════════════════════════════════════════════════════
# [9] 前置流程：建档 → 查从节点信息 → 入网判定
# ══════════════════════════════════════════════════════════════════════
def up_frame(afn, fn, data_unit, dt2=None):
    """造一条上行帧（DIR=1，无地址域）；``dt2`` 指定时直接按 (dt1=fn 位, dt2) 组 DT。"""
    if dt2 is not None:
        # fn 参数此时按 DT1 的位图理解（如 0x08 = D3）
        payload = bytes([0x83]) + b"\x00" * 6 + bytes([afn, fn & 0xFF, dt2 & 0xFF]) + bytes(data_unit)
        total = len(payload) + 5
        return (bytes([0x68, total & 0xFF, (total >> 8) & 0xFF]) + payload
                + bytes([sum(payload) & 0xFF, 0x16]))

    import gdw_send_frame_lib as G

    info = dict(C.DEFAULT_INFO)
    info.update({"dir": 1, "prm": 0, "通信模块标识": 0})
    return G.GDWFrameGenerator().generate_frame(
        afn, fn, {}, info, "000000000000", "000000000000", [], data_unit)


def f2_up(addrs):
    """10H F2 上行数据单元：总数(2B) + 应答数(1B) + n×[地址(6B BCD 低字节在前)+信息(2B)]。"""
    body = bytes([len(addrs) & 0xFF, 0, len(addrs)])
    for addr in addrs:
        body += bytes.fromhex(str(addr).rjust(12, "0"))[::-1] + bytes([0x10, 0x02])
    return body


def test_preflight_logic():
    section("[9a] 前置流程纯逻辑")
    empty = N.NetworkConfig()
    targets, overrides, notes = N.build_preflight(empty)
    check("无档案 → 不发任何帧", (targets, overrides), ([], {}))
    check_true("无档案 → 给出提示", bool(notes), notes)

    net = make_net()
    targets, overrides, notes = N.build_preflight(net, C.find_command)
    check("有档案 → 初始化/建档/查总数/查档案/查拓扑五帧",
          [k for _p, k, _n in targets],
          [N.PREFLIGHT_INIT, N.PREFLIGHT_ADD_NODES, N.PREFLIGHT_NODE_COUNT,
           N.PREFLIGHT_NODE_INFO, N.PREFLIGHT_TOPOLOGY])
    check("第一步是参数区初始化（否则 11H F1 回表号重复）",
          targets[0][1], N.PREFLIGHT_INIT)
    check_true("说明里点明初始化会清档案", any("表号重复" in n for n in notes), notes)
    check("10H F2 查询范围跟档案个数（字段名取自 schema）",
          overrides[N.PREFLIGHT_NODE_INFO], {"从节点起始序号": 1, "从节点数量": 2})
    check("10H F20 拓扑查询 1 起、数量 1+从节点数（字段名取自 schema）",
          overrides[N.PREFLIGHT_TOPOLOGY], {"节点起始序号": 1, "节点数量": 3})

    # 建档（11H F1）必须有显式覆盖值：不能只靠界面「自动填充」开关兜底
    # （开关关掉 / 存档存了关闭态时会发出「数量 0、没有地址」的空档案帧）
    add = overrides.get(N.PREFLIGHT_ADD_NODES) or {}
    check_true("建档有显式覆盖值", bool(add), sorted(overrides))
    check("建档数量 = 档案个数", add.get("从节点数量"), 2)
    check("建档列表逐节点带地址与协议",
          [(i.get("从节点地址"), i.get("通信协议类型")) for i in add.get("从节点列表") or []],
          [(n.addr, n.proto) for n in net.active_slaves()])

    # 关掉自动填充也必须照常建档（回归：曾依赖该开关，关掉就发空档案）
    w_off, _wk, _app = make_widget()
    configure_net(w_off, _app, a="0000000033", b="000006881225")
    w_off.check_autofill.setChecked(False)
    _app.processEvents()
    plan, _ov, _notes = N.build_preflight(w_off._collect_network(), C.find_command)
    built = C.build_frame(C.find_command(0x11, 1), _ov[N.PREFLIGHT_ADD_NODES],
                          src="000000000001", dst="123456789012")
    hexed = C.format_hex(built)
    check_true("自动填充关闭时建档帧仍带两个从节点",
               " 11 01 00 02 " in hexed + " ", hexed)
    w_off.close()

    rows = [
        ("  从节点总数量", "0x0200", "2", "", 0, 1),
        ("  本次应答数量", "0x02", "2", "", 2, 2),
        ("  从节点1地址", NODE_A, NODE_A, "BCD编码", 3, 8),
        ("  从节点1中继级别", "0x10", "0", "", 9, 9),
        ("  从节点2地址", NODE_B, NODE_B, "BCD编码", 11, 16),
        ("  从节点2地址", NODE_B, NODE_B, "BCD编码", 11, 16),   # 重复行只算一次
    ]
    check("上行行里取地址（去重、只取地址）", N.slave_addrs_from_rows(rows), [NODE_A, NODE_B])

    report = N.join_report(net.slaves, [NODE_A, NODE_B])
    check_true("两节点都上报 → 全部入网", report["all_joined"], report)
    report = N.join_report(net.slaves, [NODE_A, "009999999999"])
    check("缺一个 → 列出缺的", report["missing"], [NODE_B])
    check("档案外的 → 列进 extra", report["extra"], ["009999999999"])
    check("部分入网不算完成", report["all_joined"], False)


def f20_up(entries):
    """10H F20 上行：总数量(2B)+起始序号(2B)+本次数量(1B)+n×[地址(6B)+拓扑(5B)]。

    ``entries`` = [(address, tei, info_byte)]，``info_byte`` 的 D4~D6 是节点角色
    （1=STA 末梢 / 2=PCO 代理 / 4=CCO / 0=无效）。
    """
    body = bytes([(len(entries) + 1) & 0xFF, 0, 1, 0, len(entries) & 0xFF])
    for addr, tei, info in entries:
        body += bytes.fromhex(str(addr).rjust(12, "0"))[::-1] + bytes([tei & 0xFF, 0, 0, 0, info])
    return body


def last_tx_frame(worker, afn: int, fn: int) -> str:
    """最近一帧指定 AFN/Fn 的下行帧（HEX）。

    **别用 `worker.sent[-1]`**：重试/时序抖动时最后一帧可能不是你要看的那条，
    断言会随机取到别的帧（曾把「建档帧数量 02」误判成 00）。
    """
    for frame in reversed(worker.sent):
        rows = {r[0].strip(): r for r in C.parse_table(frame)}
        afn_row = rows.get("应用功能码(AFN)")
        dt_row = rows.get("数据单元标识(DT)")
        if afn_row is None or dt_row is None:
            continue
        if int(afn_row[2]) != afn:
            continue
        if W._fn_from_dt_row(dt_row) != fn:
            continue
        return C.format_hex(frame)
    return ""


def test_preflight_widget():
    section("[9b] 前置流程端到端（初始化 → 建档 → 核对档案 → 拓扑判入网）")
    w, worker, app = make_widget()
    configure_net(w, app, a="0000000033", b="000006881225")
    w.check_fanout.setChecked(False)
    w.spin_timeout.setValue(400)
    w.spin_retries.setValue(0)
    w.PREFLIGHT_POLL_GAP_MS = 20
    w.PREFLIGHT_POLLS = 3
    check("初始入网状态", w.lbl_join_state.text(), "入网：未查询")

    w._on_preflight()
    pump(app)
    check("① 第一帧是参数区初始化", w._pending_key, N.PREFLIGHT_INIT)
    first = C.format_hex(worker.sent[0])
    check_true("① 初始化帧 AFN=01H F2", " 01 02 00 " in first + " ", first)

    w._on_frame(up_frame(0x00, 1, b""))            # 初始化确认
    pump(app)
    check("② 推进到添加从节点", w._pending_key, N.PREFLIGHT_ADD_NODES)
    build = last_tx_frame(worker, 0x11, 0x01)
    check("② 建档帧装两个从节点（数量 02）",
          build.split(" 11 01 00 ")[1][:2] if " 11 01 00 " in build else "", "02")

    w._on_frame(up_frame(0x00, 1, b""))            # 建档确认
    pump(app)
    check("③ 推进到查档案总数", w._pending_key, N.PREFLIGHT_NODE_COUNT)

    w._on_frame(up_frame(0x10, 1, bytes.fromhex("02004000")))
    pump(app)
    check("④ 推进到查从节点信息（核对档案）", w._pending_key, N.PREFLIGHT_NODE_INFO)
    check_true("④ 查询数量按档案个数（02）",
               " 10 02 00 01 00 02 " in last_tx_frame(worker, 0x10, 0x02) + " ",
               last_tx_frame(worker, 0x10, 0x02))

    # F2 只证明档案已下装（两个都在），不代表入网
    w._on_frame(up_frame(0x10, 2, f2_up(["0000000033", "000006881225"])))
    pump(app)
    check("⑤ 推进到查双模拓扑（入网判据）", w._pending_key, N.PREFLIGHT_TOPOLOGY)
    topo_tx = C.format_hex(worker.sent[-1])
    check_true("⑤ 拓扑查询起始序号 1、数量 03（1+从节点数）",
               " 10 08 02 01 00 03 " in topo_tx + " ", topo_tx)

    # 首轮拓扑只有一个节点（角色 STA）→ 不满足 → 轮询
    w._on_frame(up_frame(0x10, 0x08, f20_up([("0000000033", 1, 0x10)]), dt2=0x02))
    pump(app, 60)
    check_true("首轮拓扑不全 → 已排轮询", (w._preflight or {}).get("polls", 0) >= 1, w._preflight)
    for _ in range(6):
        if w._awaiting and w._pending_key == N.PREFLIGHT_TOPOLOGY:
            w._on_frame(up_frame(0x10, 0x08,
                                 f20_up([("0000000033", 1, 0x10),
                                         ("000006881225", 2, 0x10)]),
                                 dt2=0x02))
        pump(app, 60)
        if w._preflight is None:
            break

    check("拓扑报全 → 入网 2/2 且档案 2/2", w.lbl_join_state.text(), "入网：2/2 ✓｜档案 2/2")
    check("入网地址落库（12 位归一）", w._joined_addrs, ["000000000033", "000006881225"])
    log = w.log_text.toPlainText()
    check_true("日志区分档案核对与入网",
               "档案核对通过" in log and "入网完成" in log, log[-400:])
    w.close()


def test_preflight_archive_only():
    """档案有、拓扑里没有 ⇒ 不算入网（用户口径：F2 只是档案）。"""
    section("[9c] 档案 ≠ 入网（F20 角色无效 / 缺节点）")
    net = make_net()
    archive_rows = [
        ("  从节点总数量", "0x0200", "2", "", 0, 1),
        ("  从节点1地址", NODE_A, NODE_A, "BCD编码", 3, 8),
        ("  从节点2地址", NODE_B, NODE_B, "BCD编码", 11, 16),
    ]
    arch = N.archive_report(net.slaves, N.slave_addrs_from_rows(archive_rows))
    check_true("档案核对通过", arch["all_matched"], arch)

    # 拓扑：两个地址都在，但角色都是「无效」
    invalid_rows = [
        ("  节点1地址", NODE_A, NODE_A, "", 5, 10),
        ("  节点1节点角色", "0x00", "无效", "", 15, 15),
        ("  节点2地址", NODE_B, NODE_B, "", 16, 21),
        ("  节点2节点角色", "0x00", "无效", "", 26, 26),
    ]
    seen = N.topology_addrs_from_rows(invalid_rows)
    check("角色无效 → 拓扑里不算在网", seen, [])
    report = N.join_report(net.slaves, seen)
    check("档案全有但入网 0", (len(report["joined"]), report["all_joined"]), (0, False))

    # 角色有效才算
    valid_rows = [
        ("  节点1地址", NODE_A, NODE_A, "", 5, 10),
        ("  节点1节点角色", "0x10", "STA(末梢)", "", 15, 15),
        ("  节点1节点层级", "0x01", "1", "", 15, 15),
        ("  节点2地址", NODE_B, NODE_B, "", 16, 21),
        ("  节点2节点角色", "0x10", "STA(末梢)", "", 26, 26),
    ]
    seen = N.topology_addrs_from_rows(valid_rows)
    check("角色有效 → 在网", seen, [NODE_A, NODE_B])
    detail = N.topology_detail(valid_rows)
    check("拓扑细节带角色/层级", (detail[NODE_A]["角色"], detail[NODE_A]["层级"]),
          ("STA(末梢)", "1"))
    check_true("两节点在网 → 入网完成", N.join_report(net.slaves, seen)["all_joined"], seen)



def main():
    test_network_model()
    test_binding()
    test_fanout()
    test_cascade()
    test_widget_network()
    test_stats_grain()
    test_report()
    test_end_to_end()
    test_preflight_logic()
    test_preflight_widget()
    test_preflight_archive_only()

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
