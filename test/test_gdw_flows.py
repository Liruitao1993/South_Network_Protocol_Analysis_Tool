# -*- coding: utf-8 -*-
"""流程测试页回归：用例定义 / 引擎状态机 / 内容校验 / 页面集成。

跑法：``python test/test_gdw_flows.py``（需要 offscreen Qt）。
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

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import gdw_test_core as C  # noqa: E402
import gdw_test_flows as F  # noqa: E402
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


def pump(ms=60):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ══════════════════════════════════════════════════════════════════════
# [1] 用例定义
# ══════════════════════════════════════════════════════════════════════
def test_cases():
    section("[1] 8 个流程 + 抄表测试的用例定义")
    names = [c.name for c in F.FLOW_CASES]
    check("用例数与 xlsx 一致（9 条）", len(names), 9)
    check("顺序与 xlsx 70~78 行一致", names, [
        "识别流程", "档案同步流程", "点抄流程", "从节点主动注册流程",
        "能源控制器主动方式抄表", "路由模块主动方式抄表",
        "广播流程（通信时延相关报文机制）", "宽带增补协议测试流程", "抄表测试",
    ])
    check_true("每条用例都有步骤与出处",
               all(c.steps and c.source for c in F.FLOW_CASES),
               [c.fid for c in F.FLOW_CASES if not (c.steps and c.source)])
    # 引用的命令必须真实存在，否则跑到一半才报「未找到命令」
    have = {c.key for c in C.all_commands()}
    used = {s.key for c in F.FLOW_CASES for s in c.steps if s.key}
    check("步骤引用的命令全部存在", sorted(used - have), [])
    check_true("需要从节点配合的用例已标记",
               set(F.cases_needing_slave()) >= {"点抄流程", "从节点主动注册流程", "路由模块主动方式抄表"},
               F.cases_needing_slave())
    # 每步超时必须为正
    bad = [(c.fid, s.title) for c in F.FLOW_CASES for s in c.steps if s.timeout <= 0]
    check("每步超时 > 0", bad, [])


# ══════════════════════════════════════════════════════════════════════
# [2] 引擎状态机
# ══════════════════════════════════════════════════════════════════════
def test_runner():
    section("[2] 引擎：动作推进 / 失败传播 / 可选步 / 停止")
    case = F.flow_case("archive")
    runner = F.FlowRunner(case)
    action = runner.start()
    check("首动作是 send 01H F2", (action.kind, action.step.key), ("send", "01-2"))
    action = runner.advance(True)
    check("确认后进入建档", action.step.key, "11-1")
    action = runner.advance(True)
    check("建档后查数量", action.step.key, "10-1")
    action = runner.advance(True)
    check("查数量后核对档案", (action.step.key, action.step.check), ("10-2", F.CHECK_ARCHIVE))
    action = runner.advance(True)
    check("最后一步是 note，直接收尾", action.kind, "done")
    check_true("全程通过", runner.passed, runner.states)
    check("步数统计", runner.summary(), (5, 0, 0))

    # 失败终止 + 用例判失败
    runner2 = F.FlowRunner(case)
    runner2.start()
    runner2.advance(True)
    action = runner2.advance(False, "否认（表号重复）")
    check("失败步被记录", runner2.states[1], F.STEP_FAIL)
    check("说明带原因", runner2.notes[1], "否认（表号重复）")
    check("失败后用例整体判失败", runner2.failed, True)

    # 可选步失败不影响结论（识别流程的 03H F10 主动查询是 optional）
    ident = F.flow_case("identify")
    opt_idx = next(i for i, s in enumerate(ident.steps) if s.optional)
    r3 = F.FlowRunner(ident)
    action = r3.start()
    while action.index < opt_idx:
        check_true(f"推进到可选步前：{action.step.title[:16]}", action.index < opt_idx, action.index)
        action = r3.advance(True)
    action = r3.advance(False, "超时")   # 可选步失败
    check("可选步失败记为跳过", (r3.states[opt_idx], r3.failed), (F.STEP_SKIP, False))
    check("可选步后仍在推进", action.kind != "done", True)

    # 停止
    r4 = F.FlowRunner(F.flow_case("register"))
    r4.start()
    r4.stop("用户停止")
    check("停止后 finished", r4.finished, True)
    check("停止不算通过", r4.passed, False)

    check("空用例直接 done", F.FlowRunner(F.FlowCase("x", "空", "", [])).start().kind, "done")


# ══════════════════════════════════════════════════════════════════════
# [3] 上游等待匹配
# ══════════════════════════════════════════════════════════════════════
def test_wait_match():
    section("[3] 被动等待（模块主动上行）的匹配")
    # 用「能源控制器主动方式抄表」：里面有 14H F3 / 13H F1 的 wait 步
    # （路由主动抄表已改为 serve 步，不再有 wait，不能拿它遍历）
    case = F.flow_case("master_read")
    runner = F.FlowRunner(case)
    action = runner.start()
    steps_guard = 0
    while action.kind != "wait" and action.kind != "done" and steps_guard < 200:
        action = runner.advance(True)
        steps_guard += 1
    check("找到 wait 步（没有死循环）", action.kind, "wait")
    check("主动抄表第一处 wait 是 14H F3", (action.step.afn, action.step.fn), (0x14, 0x03))
    check_true("匹配同 AFN/Fn", F.match_uplink(action, 0x14, 0x03), action.step.title)
    check("不同 Fn 不匹配", F.match_uplink(action, 0x14, 0x01), False)
    check("不同 AFN 不匹配", F.match_uplink(action, 0x13, 0x01), False)


def test_register_uplink():
    section("[3b] 主动注册等 06H F4（新标准），06H F1 仅作兼容")
    case = F.flow_case("register")
    runner = F.FlowRunner(case)
    action = runner.start()
    while action.kind != "wait":
        action = runner.advance(True)
    check("注册流程等 06H F4（上报从节点信息及设备类型）",
          (action.step.afn, action.step.fn), (0x06, 0x04))
    check("06H F4 命中主判据", F.match_uplink(action, 0x06, 0x04), True)
    check("06H F1 仍命中（旧标准兼容）", F.match_uplink(action, 0x06, 0x01), True)
    check("06H F2 不命中", F.match_uplink(action, 0x06, 0x02), False)
    check("06H F4 是主判据", F.is_primary_uplink(action.step, 0x06, 0x04), True)
    check("06H F1 不是主判据（要告警提示）", F.is_primary_uplink(action.step, 0x06, 0x01), False)

    # 页面侧：命中兼容帧要给出「新标准应该报什么」的提示
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    check("06H F4 无额外提示", w._flow_note_uplink(action.step, 0x06, 0x04), "")
    legacy_note = w._flow_note_uplink(action.step, 0x06, 0x01)
    check_true("06H F1 提示旧标准 + 新标准要求",
               ("兼容旧标准" in legacy_note) and ("06H F4" in legacy_note), legacy_note)

    # 端到端：流程真的停在「等上报」时，分别喂 06H F4 / 06H F1 上行看判定
    def up(afn, dt1, dt2, data=b""):
        payload = bytes([0x83]) + b"\x00" * 6 + bytes([afn, dt1, dt2]) + bytes(data)
        total = len(payload) + 5
        return bytes([0x68, total & 0xFF, 0]) + payload + bytes([sum(payload) & 0xFF, 0x16])

    for label, (dt1, dt2), want_legacy in (("06H F4", (0x08, 0x00), False),
                                           ("06H F1", (0x01, 0x00), True)):
        r = F.FlowRunner(F.flow_case("register"))
        act = r.start()
        while act.kind != "wait":
            act = r.advance(True)
        w._flow_runner, w._flow_action = r, act
        check_true(f"{label} 上行被流程消费", w._flow_on_frame(up(0x06, dt1, dt2)))
        check(f"{label} 步判通过", r.states[act.index], F.STEP_OK)
        check_true(f"{label} 备注{'标兼容' if want_legacy else '不标兼容'}",
                   ("兼容旧标准" in r.notes[act.index]) == want_legacy, r.notes[act.index])
        w._flow_timer.stop()
    w._flow_runner = None
    w.close()


def test_route_read_flow():
    section("[3c] 路由主动抄表：重启 → 服务路由请求（14H F1 回抄读内容）→ 12H F2 暂停")
    case = F.flow_case("route_read")
    steps = case.steps
    keys = [s.key for s in steps]
    check_true("有「路由重启 12H F1」这一步", "12-1" in keys, keys)
    idx_restart = keys.index("12-1")
    idx_serve = next(i for i, s in enumerate(steps) if s.kind == F.KIND_SERVE)
    last = steps[-1]
    check_true("重启在服务步之前", idx_restart < idx_serve, (idx_restart, idx_serve))
    check("服务步复用 14H F1 的组帧参数", steps[idx_serve].key, "14-1")
    check("服务步等 06H F2 抄读数据结束", steps[idx_serve].until, (0x06, 0x02))
    check("服务步要应答 14H F1 与 14H F2", steps[idx_serve].serve, ((0x14, 0x01), (0x14, 0x02)))
    check("服务步做数据一致性校验", steps[idx_serve].check, F.CHECK_READ_MATCH)
    check("最后一步是路由暂停 12H F2", (last.kind, last.key), (F.KIND_SEND, "12-2"))
    check_true("流程里不再把 13H F1 当路由主动抄表的上行",
               not any(s.kind == F.KIND_WAIT and (s.afn, s.fn) == (0x13, 0x01) for s in steps),
               [(s.afn, s.fn) for s in steps if s.kind == F.KIND_WAIT])


def test_broadcast_payloads():
    section("[3e] 广播流程：03H F9 / 05H F3 必须带协议类型 + 长度 + 报文内容")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    w.node_widgets[0]["addr"].setText("0000000033")
    w.node_widgets[0]["proto"].setCurrentIndex(
        max(0, w.node_widgets[0]["proto"].findData(2)))          # 645-2007
    w.node_widgets[1]["addr"].setText("000006881225")
    w.node_widgets[1]["proto"].setCurrentIndex(
        max(0, w.node_widgets[1]["proto"].findData(3)))          # 698.45
    w._on_network_edited()
    app.processEvents()

    case = F.flow_case("broadcast")
    step9 = next(s for s in case.steps if s.key == "03-9")
    frames = w._build_flow_frames(step9)
    check("03H F9 按从节点各发一帧", len(frames), 2)
    rows = {r[0].strip(): r for r in C.parse_table(frames[0][0])}
    check("03H F9 带通信协议类型（645 节点=2）", rows["通信协议类型"][2], "2")
    check("03H F9 报文长度 = 报文内容字节数（16，不是 0）", rows["报文长度"][2], "16")
    check_true("03H F9 报文内容是 645 正向有功总电能读帧",
               rows["报文内容"][1].startswith("68 33 00 00 00 00 00 68 11 04 33 33 34 33"),
               rows["报文内容"][1])
    rows698 = {r[0].strip(): r for r in C.parse_table(frames[1][0])}
    check("03H F9 698 节点协议类型=3", rows698["通信协议类型"][2], "3")
    check("03H F9 698 报文长度与内容一致",
          rows698["报文长度"][2], str(len(bytes.fromhex(rows698["报文内容"][1].replace(" ", "")))))

    step3 = next(s for s in case.steps if s.key == "05-3")
    frames3 = w._build_flow_frames(step3)
    rows3 = {r[0].strip(): r for r in C.parse_table(frames3[0][0])}
    check("05H F3 控制字按 645-2007 = 02H", rows3["控制字"][2], "2")
    check("05H F3 报文长度 = 16", rows3["报文长度"][2], "16")
    check_true("05H F3 报文内容非空",
               rows3["报文内容"][1].startswith("68 33 00 00 00 00 00 68 11 04"),
               rows3["报文内容"][1])
    rows3_698 = {r[0].strip(): r for r in C.parse_table(frames3[1][0])}
    check("05H F3 698 表用控制字 00H（透明传输，表 43 的 03H 是相位识别）",
          rows3_698["控制字"][2], "0")

    # 解析侧：下行与上行结构不同，不能互相串
    down = frames[0][0]
    up9 = w._build_flow_frames(step9)  # 占位，避免未使用
    _ = up9
    check("F9 下行解析出协议类型", rows["通信协议类型"][3], "DL/T 645-2007")
    w.close()


def test_no_reply_and_698():
    section("[3f] 14H F3 回完即推进（不等应答）+ 698 读报文逐字节对齐现场样例")
    # ① 14H F3 下行不该等应答
    case = F.flow_case("master_read")
    step43 = next(s for s in case.steps if s.key == "14-3")
    check("14H F3 下行标了 no_reply", step43.no_reply, True)
    check_true("提示里写明不等应答", "不等应答" in step43.hint, step43.hint)
    check("其它发送步不受影响（13H F1 仍等应答）",
          next(s for s in case.steps if s.key == "13-1").no_reply, False)

    # 行为：发完立刻完成，不启等待定时器
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()

    class FakeChannel:
        def __init__(self):
            self.sent = []

        def ready(self):
            return True

        def state_text(self):
            return "fake"

        def send(self, frame):
            self.sent.append(bytes(frame))
            return True, ""

        def cleanup(self):
            pass

        def rebind_bluetooth(self):
            pass

    w._channel = FakeChannel()
    w.node_widgets[0]["addr"].setText("0000000033")
    w.node_widgets[0]["proto"].setCurrentIndex(
        max(0, w.node_widgets[0]["proto"].findData(2)))
    w.node_widgets[1]["use"].setChecked(False)          # 只留一个从节点，帧数确定
    w._on_network_edited()
    app.processEvents()

    # 正常推进到 14-3 那一步（不要手工构造 Action：runner.index 得跟着走）
    runner = F.FlowRunner(case)
    from PySide6.QtWidgets import QTableWidgetItem

    w.flow_table.setRowCount(len(case.steps))
    for i in range(len(case.steps)):
        for c in range(4):
            w.flow_table.setItem(i, c, QTableWidgetItem(""))
    w._flow_runner = runner
    action = runner.start()
    while action.kind != "done" and not (action.step and action.step.key == "14-3"):
        action = runner.advance(True)
    check("推进到了 14H F3 下行这一步", action.kind, F.KIND_SEND)
    idx = action.index
    w._flow_action = action
    w._run_flow_action(action)
    app.processEvents()
    check("只发 1 帧（1 个启用的从节点）", len(w._channel.sent), 1)
    check("14H F3 步骤立刻判通过（没有等 6s 超时）", runner.states[idx], F.STEP_OK)
    check_true("备注写明不等应答", "不等应答" in (runner.notes[idx] or ""), runner.notes[idx])
    w._flow_runner = None
    w._flow_timer.stop()
    # 恢复组网参数（这条用例会落盘，别污染后面的用例）
    w.node_widgets[1]["use"].setChecked(True)
    w._on_network_edited()
    app.processEvents()

    # ② 698 读报文 = 现场实测报文（逐字节）
    import gdw_meter_request as req

    check("698 GET 报文逐字节对齐现场样例",
          C.format_hex(req.build_698_read_total_active("0000000033")),
          "68 17 00 43 05 33 00 00 00 00 00 00 C7 52 05 01 01 00 10 02 00 00 92 2E 16")
    frame698 = req.build_698_read_total_active("0000000033")
    check_true("带「时间标签=无」的 00 字节（APDU 尾部）", frame698[21] == 0x00, frame698.hex(" "))
    check("报文长度 L = 23（含时间标签）", int.from_bytes(frame698[1:3], "little"), 23)
    check("报文长度 = 整帧长 - 2", int.from_bytes(frame698[1:3], "little"), len(frame698) - 2)
    w.close()


def test_read_content_supported_by_sim():
    section("[3g] 抄读内容必须是虚拟表支持的 OAD / DI（否则 CCO 抄不到响应）")
    import gdw_meter_request as req

    # ① 默认挑到的就是正向有功总电能
    check("698 选到 00100200（档案支持）", req.pick_698_oad(), "00100200")
    check("645 选到 00010000（档案支持）", req.pick_645_di(), "00010000")
    check("档案里没有该 OAD 时退让到支持的电能量项",
          req.pick_698_oad("FFFFFFFF"), "00000200")

    # ② 真正喂给虚拟表引擎：两个协议都必须回数据，不能回「对象不存在」
    f698 = req.build_698_read_total_active("0000000033")
    from meter_sim import MeterSimEngine, SimOptions
    from meter_sim.archive import load_archive

    eng = MeterSimEngine(load_archive(), SimOptions(meter_address="0000000033"))
    resps = eng.handle_frame(f698)
    check_true("698 读帧被虚拟表应答", bool(resps), eng.logs)
    check_true("698 应答是 GET-Response 且带数据（不是对象不存在）",
               bool(resps) and resps[0][14] == 0x85, resps[0].hex(" ") if resps else "")

    from dlt645_sim import DLT645MeterSim

    f645 = req.build_645_read_total_active("0000000033")
    out = DLT645MeterSim(address="0000000033").handle_frame(f645)
    if isinstance(out, (list, tuple)):          # 引擎可能返回 0..n 帧
        out = out[0] if out else b""
    check_true("645 读帧被虚拟表应答", isinstance(out, bytes) and len(out) > 12, out)
    check_true("645 应答控制码是 91H（从站正确应答）",
               isinstance(out, bytes) and len(out) > 8 and out[8] == 0x91,
               out.hex(" ") if out else "")

    # ③ 帧内容本身仍与现场样例一致（别为了「支持」改动报文结构）
    check("698 读帧仍逐字节等于现场样例",
          C.format_hex(f698),
          "68 17 00 43 05 33 00 00 00 00 00 00 C7 52 05 01 01 00 10 02 00 00 92 2E 16")


def test_serve_and_ack_policy():
    section("[3d] 确认帧策略 + 14H F1/F2 业务应答 + 结果列")
    section("[3d] 确认帧策略 + 14H F1/F2 业务应答 + 结果列")
    # ① 确认帧只给主动上报类；14H F1（请求抄读内容）不能再回确认
    check("06H F1 上报 → 需确认", F.needs_confirm(0x06, 0x01), True)
    check("06H F4 上报 → 需确认", F.needs_confirm(0x06, 0x04), True)
    check("06H F2 抄读数据上报 → 需确认", F.needs_confirm(0x06, 0x02), True)
    check("14H F1 请求抄读内容 → 不回确认（要回抄读内容）", F.needs_confirm(0x14, 0x01), False)
    check("14H F2 请求时钟 → 不回确认（要回系统时间）", F.needs_confirm(0x14, 0x02), False)
    check("14H F3 延时修正请求 → 仍回确认", F.needs_confirm(0x14, 0x03), True)

    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()

    class FakeChannel:
        def __init__(self):
            self.sent = []

        def ready(self):
            return True

        def state_text(self):
            return "fake"

        def send(self, frame):
            self.sent.append(bytes(frame))
            return True, ""

        def cleanup(self):
            pass

        def rebind_bluetooth(self):
            pass

    w._channel = FakeChannel()
    w.node_widgets[0]["addr"].setText("0000000033")
    w.node_widgets[0]["proto"].setCurrentIndex(
        max(0, w.node_widgets[0]["proto"].findData(2)))     # 645-2007
    w._on_network_edited()
    app.processEvents()

    # ② 14H F1 上行（相位 + 从节点地址 6B + 序号 2B）→ 回 14H F1 抄读内容，且不额外发确认帧
    def up_frame(afn: int, fn: int, data: bytes = b"", seq: int = 1) -> bytes:
        """手搓 376.2 上行帧：信息域 6B(末字节=序号) + AFN + DT1 + DT2 + 数据 + CS + 16。"""
        body = bytes([0xC3, 0, 0, 0, 0, 0, seq & 0xFF, afn, fn, 0x00]) + data
        cs = sum(body) & 0xFF
        total = len(body) + 5
        return bytes([0x68, total & 0xFF, 0x00]) + body + bytes([cs, 0x16])

    # 界面序号故意设成 0x92，请求帧用 0x0E：应答必须回显 0x0E（用户口径）
    w.spin_seq.setValue(0x92)
    up14 = up_frame(0x14, 0x01, bytes([1]) + bytes.fromhex("330000000000") + bytes([1, 0]),
                    seq=0x0E)
    w._on_frame(up14)
    app.processEvents()
    check("收到 14H F1 回了 1 帧（不是确认帧）", len(w._channel.sent), 1)
    reply = {r[0].strip(): r for r in C.parse_table(w._channel.sent[0])}
    check("应答是 14H F1 下行", int(reply["应用功能码(AFN)"][2]), 0x14)
    check("抄读标志=可以抄读(02H)", reply["抄读标志"][2], "可以抄读")
    # 外层 1376.2 头部照现场参考报文：控制域 01H（PRM=0 从动站 + 通信方式=1）、
    # 信息域首字节 08H（D3 冲突检测=1）
    check("控制域=01H（从动站 + 窄带载波）", reply["控制域"][1].upper(), "0X01")
    check("PRM=0（应答帧，来自从动站）", reply["D6 启动标志(PRM)"][2], "0")
    check_true("通信方式=1（窄带电力线载波）",
               reply["D5~D0 通信方式"][2].startswith("1"), reply["D5~D0 通信方式"][2])
    check("信息域冲突检测=1（D3）", reply["D3 冲突检测"][2], "1")
    check("通信模块标识=0（无地址域）", reply["D2 通信模块标识"][2], "0")
    # 报文序列号必须回显请求帧的（用户口径），不能用自己的自增序号
    check("报文序列号回显请求帧（0x0E）", reply["报文序列号"][1].upper(), "0X0E")
    check("界面序号没有被应答改动", w.spin_seq.value(), 0x92)
    # 表 125：02H 可以抄读时 n ≥ 0，抄读内容里已带表地址 → 不填附属节点地址（用户口径）
    check("附属节点数量=0（不填附属节点地址）", reply["从节点附属节点数量"][2], "0")
    check_true("应答里没有附属节点地址",
               not any("附属节点" in k and "地址" in k for k in reply), sorted(reply))
    check_true("抄读内容是 645 正向有功总电能读帧",
               reply.get("路由请求数据内容", ("", "", ""))[1].startswith(
                   "68 33 00 00 00 00 00 68 11 04 33 33 34 33"),
               reply.get("路由请求数据内容"))
    check("自动应答计数 +1", w._flow_served, 1)

    # ③ 14H F2 上行（请求集中器时钟，无数据单元）→ 回当前系统时间
    w._channel.sent.clear()
    up_clock = up_frame(0x14, 0x02, seq=0x37)
    w._on_frame(up_clock)
    app.processEvents()
    check("收到 14H F2 回了 1 帧", len(w._channel.sent), 1)
    clock = {r[0].strip(): r for r in C.parse_table(w._channel.sent[0])}
    check("应答是 14H F2 下行", int(clock["应用功能码(AFN)"][2]), 0x14)
    check("14H F2 也回显请求序列号（0x37）", clock["报文序列号"][1].upper(), "0X37")
    from datetime import datetime as _dt

    now = _dt.now()
    check("时间是当前系统时间（时/分/秒）",
          (clock["时"][2].zfill(2), clock["分"][2].zfill(2), clock["秒"][2].zfill(2)),
          (f"{now.hour:02d}", f"{now.minute:02d}", f"{now.second:02d}"))

    # ④ 06H F1 依旧回确认帧（00H F1）
    w._channel.sent.clear()
    up06 = up_frame(0x06, 0x01, bytes([0, 0]))
    w._on_frame(up06)
    app.processEvents()
    check("06H F1 回了确认帧", len(w._channel.sent), 1)
    ack = {r[0].strip(): r for r in C.parse_table(w._channel.sent[0])}
    check("确认帧 AFN=00H", int(ack["应用功能码(AFN)"][2]), 0x00)

    # ⑤ 左树第三列「测试结果」
    tree = w._trees[C.PAGE_FLOW]
    w._select_page(C.PAGE_FLOW, notify=True)
    app.processEvents()
    check("树表头第三列是「测试结果」", tree.headerItem().text(2), "测试结果")
    w._set_flow_result("route_read", "通过")
    app.processEvents()
    leaf = None
    for it in w._iter_leaves(tree):
        data = it.data(0, W.LEAF_KEY_ROLE)
        if data and data[1] == "route_read":
            leaf = it
            break
    check_true("流程行显示出测试结果", leaf is not None and leaf.text(2) == "✓ 通过",
               leaf.text(2) if leaf is not None else "未找到流程行")
    w._set_flow_result("register", "进行中")
    app.processEvents()
    check("进行中显示「进行中…」", w._flow_result_of("register"), "进行中…")
    check("未跑过的用例显示占位", w._flow_result_of("identify"), "—")
    w.close()


# ══════════════════════════════════════════════════════════════════════
# [4] 内容校验
# ══════════════════════════════════════════════════════════════════════
def test_checks():
    section("[4] 步骤内容校验（档案/拓扑/延迟/T2/路由状态）")
    archive = ["000000000033", "000006881225"]

    # 10H F2：两个地址都在 → 通过
    rows_ok = [
        ("  从节点总数量", "0x0200", "2", "", 0, 1),
        ("  从节点1地址", archive[0], archive[0], "", 3, 8),
        ("  从节点2地址", archive[1], archive[1], "", 11, 16),
    ]
    check_true("档案含全部地址 → 通过",
               F.run_check(F.CHECK_ARCHIVE, rows_ok, archive)[0],
               F.run_check(F.CHECK_ARCHIVE, rows_ok, archive))
    rows_missing = rows_ok[:2]
    ok, note = F.run_check(F.CHECK_ARCHIVE, rows_missing, archive)
    check("档案缺一个 → 失败", ok, False)
    check_true("说明点出缺哪个", archive[1] in note, note)

    # 10H F20：角色无效不算在网
    topo_invalid = [
        ("  节点1地址", archive[0], archive[0], "", 5, 10),
        ("  节点1节点角色", "0x00", "无效", "", 15, 15),
        ("  节点2地址", archive[1], archive[1], "", 16, 21),
        ("  节点2节点角色", "0x00", "无效", "", 26, 26),
    ]
    check("拓扑角色无效 → 不算入网", F.run_check(F.CHECK_TOPOLOGY, topo_invalid, archive)[0], False)
    topo_valid = [
        ("  节点1地址", archive[0], archive[0], "", 5, 10),
        ("  节点1节点角色", "0x10", "STA(末梢)", "", 15, 15),
        ("  节点2地址", archive[1], archive[1], "", 16, 21),
        ("  节点2节点角色", "0x10", "STA(末梢)", "", 26, 26),
    ]
    check_true("拓扑角色有效 → 入网完成", F.run_check(F.CHECK_TOPOLOGY, topo_valid, archive)[0],
               F.run_check(F.CHECK_TOPOLOGY, topo_valid, archive))

    # 03H F9：广播通信延迟时间必须 > 0
    delay_ok = [("  广播通信延迟时间", "0x000A", "10", "单位 10ms", 0, 1)]
    check_true("T1=10 → 通过", F.run_check(F.CHECK_DELAY, delay_ok)[0],
               F.run_check(F.CHECK_DELAY, delay_ok))
    delay_zero = [("  广播通信延迟时间", "0x0000", "0", "", 0, 1)]
    check("T1=0 → 失败", F.run_check(F.CHECK_DELAY, delay_zero)[0], False)

    # 05H F3：确认帧带等待时间 T2
    ack_ok = [("  等待时间", "0x0005", "5", "单位 s", 0, 1)]
    check_true("T2=5 → 通过", F.run_check(F.CHECK_BROADCAST_ACK, ack_ok)[0],
               F.run_check(F.CHECK_BROADCAST_ACK, ack_ok))

    # 10H F4：工作标志停止 + 路由完成
    state_ok = [("  工作标志(D1)", "0x01", "停止工作", "", 0, 0),
                ("  运行状态字", "0x01", "路由完成=是, 工作中=否, 事件=无", "", 0, 0)]
    check_true("停止工作 + 路由完成 → 通过", F.run_check(F.CHECK_ROUTE_STATE, state_ok)[0],
               F.run_check(F.CHECK_ROUTE_STATE, state_ok))

    check("无校验名的步骤直接通过", F.run_check("", [])[0], True)
    check("空解析行 → 失败", F.run_check(F.CHECK_ARCHIVE, [])[0], False)


# ══════════════════════════════════════════════════════════════════════
# [5] 页面集成
# ══════════════════════════════════════════════════════════════════════
def test_page():
    section("[5] 流程测试页（第 6 页签 / 用例树 / 步骤表）")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    w.show()
    app.processEvents()
    labels = [w.page_tabs.tabText(i) for i in range(w.page_tabs.count())]
    check("页签在「自定义」右边", labels[-2:], ["自定义", "流程测试"])
    check("流程页叶子数 = 用例数", C.leaf_count(C.PAGE_FLOW), len(F.FLOW_CASES))

    w._select_page(C.PAGE_FLOW, notify=True)
    app.processEvents()
    check("切页后显示流程面板", w.center_stack.currentIndex(), 2)

    tree = w._trees[C.PAGE_FLOW]
    leaf = tree.topLevelItem(0).child(0).child(1)      # 档案同步流程
    tree.setCurrentItem(leaf)
    app.processEvents()
    check("选中用例标题", w.lbl_flow_title.text(), "档案同步流程（5 步）")
    check("步骤表行数 = 步骤数", w.flow_table.rowCount(), 5)
    check("首行是参数区初始化", "参数区初始化" in w.flow_table.item(0, 1).text(), True)

    # 流程页不参与命令合计
    check("流程页可下发数计 0", w._sendable_count(C.PAGE_FLOW), 0)

    # 勾选两条 → 顺序执行队列
    w._checked[C.PAGE_FLOW] = ["identify", "archive"]
    w._flow_case = None
    cases = w._flow_selected_cases()
    check("勾选的流程按树序取出", [c.fid for c in cases], ["identify", "archive"])
    w.close()


def test_prerequisite():
    section("[6] 前置序列（重新建档 + 组网，含 STA 复位与拓扑轮询）")
    steps = F.prerequisite_steps()
    keys = [s.key for s in steps if s.key]
    check("前置含初始化/建档/查数/查档案", keys[:4], ["01-2", "11-1", "10-1", "10-2"])
    check("第 5 步就是 STA 复位", steps[4].kind, F.KIND_RESET_STA)
    check("复位步标记需要从节点配合", steps[4].needs_slave, True)
    check("第 6 步启动组网", steps[5].key, "11-102")
    check("第 7 步轮询拓扑（带组网等待窗口）", (steps[6].kind, steps[6].key, steps[6].check),
          (F.KIND_POLL, "10-20", F.CHECK_TOPOLOGY))
    check("组网窗口默认 5 分钟", steps[6].timeout, F.JOIN_WINDOW)
    check("轮询步也要求从节点配合", steps[6].needs_slave, True)

    # 依赖从节点的用例都带完整前置，而不是一句「前提：档案已建」
    for fid in ("spot_read", "master_read", "route_read", "meter_read", "register"):
        case = F.flow_case(fid)
        kinds = [s.kind for s in case.steps]
        check_true(f"{case.name} 含完整前置（初始化→复位→组网→轮询）",
                   kinds[:4] == [F.KIND_SEND] * 4
                   and F.KIND_RESET_STA in kinds and F.KIND_POLL in kinds, kinds)
        check_true(f"{case.name} 不再只有「前提」说明步",
                   not any(s.kind == F.KIND_NOTE and "前提" in s.title for s in case.steps),
                   [s.title for s in case.steps if s.kind == F.KIND_NOTE])


def test_confirm_rules():
    section("[7] 主动上报要回确认帧的判定")
    check("06H F1 上报从节点信息 → 需确认", F.needs_confirm(0x06, 0x01), True)
    check("06H 任意 Fn（整类主动上报）→ 需确认", F.needs_confirm(0x06, 0x13), True)
    check("56H 福建增补上报 → 需确认", F.needs_confirm(0x56, 0x01), True)
    check("03H F10 模块上报信息 → 需确认", F.needs_confirm(0x03, 0x10), True)
    # 14H F1 不是「上报」，是「请求抄读内容」：要回的是抄读内容，不是确认帧
    # （1.26.9 用户口径；回确认会让被测以为请求被拒）
    check("14H F1 路由请求抄读 → 不回确认（改回抄读内容）",
          F.needs_confirm(0x14, 0x01), False)
    check("14H F2 请求集中器时钟 → 不回确认（改回系统时间）",
          F.needs_confirm(0x14, 0x02), False)
    check("13H F1 抄读数据（是命令应答）→ 不确认", F.needs_confirm(0x13, 0x01), False)
    check("10H F2 档案数据（是命令应答）→ 不确认", F.needs_confirm(0x10, 0x02), False)


def test_widget_confirm_and_reset():
    section("[8] 页面：收到上报自动回确认 / STA 复位走虚拟表通道")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()

    class FakeChannel:
        def __init__(self):
            self.sent = []

        def ready(self):
            return True

        def state_text(self):
            return "fake"

        def send(self, frame):
            self.sent.append(bytes(frame))
            return True, ""

        def cleanup(self):
            pass

        def rebind_bluetooth(self):
            pass

    w._channel = FakeChannel()

    def up(afn, dt1, dt2, data=b"", seq=0x11):
        payload = bytes([0x83]) + b"\x00" * 5 + bytes([seq]) + bytes([afn, dt1, dt2]) + bytes(data)
        total = len(payload) + 5
        return bytes([0x68, total & 0xFF, 0]) + payload + bytes([sum(payload) & 0xFF, 0x16])

    w._on_frame(up(0x06, 0x01, 0x00, bytes.fromhex("010001330000000000")))
    app.processEvents()
    check("收到 06H F1 上报后回了 1 帧", len(w._channel.sent), 1)
    ack = w._channel.sent[0]
    rows = {r[0].strip(): r for r in C.parse_table(ack)}
    check("回的是确认帧 F1", rows.get("数据单元标识(DT)")[3], "F1=确认")
    check("AFN=00H", rows.get("应用功能码(AFN)")[2], "0")
    check("序列号沿用上报帧（0x11）", rows.get("报文序列号")[2], "17")
    check_true("原帧无地址域 → 确认帧也不带",
               rows.get("地址域") is None, rows.get("地址域"))

    # 非上报类应答不确认
    before = len(w._channel.sent)
    w._on_frame(up(0x13, 0x01, 0x00, bytes.fromhex("0102")))
    app.processEvents()
    check("13H F1 数据应答不回确认", len(w._channel.sent), before)

    # STA 复位优先走虚拟表通道
    sent_reset = []
    w.set_sta_reset_provider(lambda frame: (sent_reset.append(bytes(frame)), True)[1])
    w._flow_runner = F.FlowRunner(F.flow_case("archive"))
    w._run_sta_reset(F.FlowStep(F.KIND_RESET_STA, "复位", timeout=6.0))
    check("复位帧走虚拟表通道", len(sent_reset), 1)
    check_true("复位帧是 645 广播 14H 写数据",
               sent_reset[0].hex().startswith("68" + "aa" * 6 + "6814"),
               sent_reset[0].hex(" "))
    w._flow_runner = None
    w.close()


def test_power_on():
    section("[9] 识别流程用「硬件初始化」触发 CCO 上电动作")
    case = F.flow_case("identify")
    first = case.steps[0]
    check("第一步是硬件初始化", (first.kind, first.key), (F.KIND_SEND, "01-1"))
    check_true("标题点明是上电/重启动作", "上电" in first.title or "重启" in first.title, first.title)
    check("第二步就直接等上报（不再横插 5s 重启等待，否则会漏帧）",
          case.steps[1].kind, F.KIND_WAIT)
    check("等服务时长为 60s", case.steps[1].timeout, 60.0)
    check("第三步是主动查询 03H F10（模块没主动上报时的兜底）",
          (case.steps[2].kind, case.steps[2].key), (F.KIND_SEND, "03-10"))
    check_true("不再用「前提」说明步代替上电",
               not any(s.kind == F.KIND_NOTE for s in case.steps),
               [s.title for s in case.steps if s.kind == F.KIND_NOTE])
    # 01-1 本身无数据单元，可直接下发
    cmd = next(c for c in C.all_commands() if c.key == "01-1")
    check("硬件初始化无数据单元", cmd.fields, ())


def test_early_uplink():
    section("[10] 早到的上行要能命中缓存（硬件初始化后 CCO 立刻上报 03H F10）")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()

    class FakeChannel:
        def __init__(self):
            self.sent = []

        def ready(self):
            return True

        def state_text(self):
            return "fake"

        def send(self, frame):
            self.sent.append(bytes(frame))
            return True, ""

        def cleanup(self):
            pass

        def rebind_bluetooth(self):
            pass

    def up(afn, dt1, dt2, data=b""):
        payload = bytes([0x83]) + b"\x00" * 6 + bytes([afn, dt1, dt2]) + bytes(data)
        total = len(payload) + 5
        return bytes([0x68, total & 0xFF, 0]) + payload + bytes([sum(payload) & 0xFF, 0x16])

    w._channel = FakeChannel()
    w._select_page(C.PAGE_FLOW, notify=True)
    app.processEvents()
    tree = w._trees[C.PAGE_FLOW]
    tree.setCurrentItem(tree.topLevelItem(0).child(0).child(0))     # 识别流程
    app.processEvents()
    w._on_flow_start()
    pump()

    # 关键时序：硬件初始化还没被确认，03H F10 就已经上报上来了
    w._on_frame(up(0x03, 0x02, 0x01, bytes.fromhex("0100")))
    pump()
    check_true("未匹配的早到帧进了缓存",
               any(a == 0x03 and f == 10 for _t, a, f, _u in w._flow_rx_buffer),
               w._flow_rx_buffer)

    w._on_frame(up(0x00, 1, 0))          # 硬件初始化确认 → 进入 wait 步
    pump()
    check("wait 步命中缓存判通过", w._flow_runner.states[1], F.STEP_OK)
    check_true("日志说明是缓存命中", "命中缓存" in w.log_text.toPlainText(),
               w.log_text.toPlainText()[-200:])
    # 同一帧不会被后续 wait 重复消费
    check("缓存条目已标记消费", w._flow_rx_buffer[0][3], True)
    w._flow_runner = None
    w.close()


def test_fn_encoding():
    section("[11] 步骤里的 Fn 用十进制（F10 不是 0x10）")
    waits = [(c.fid, s.afn, s.fn) for c in F.FLOW_CASES for s in c.steps
             if s.kind == F.KIND_WAIT]
    check("识别流程等 03H F10（fn=10）",
          [x for x in waits if x[0] == "identify"][0][1:], (0x03, 10))
    check_true("没有把 F10 写成 0x10 的步骤",
               all(fn <= 0xFF and not (afn == 0x03 and fn == 0x10) for _f, afn, fn in waits),
               waits)
    # 解析器的 Fn 必须是十进制，才能和步骤里的 fn 对上
    frame = bytes.fromhex("68 15 00 83 00 00 00 00 00 00 03 02 01 01 00 00 00 00 00 00 9A 16")
    rows = {r[0].strip(): r for r in C.parse_table(frame)}
    dt = rows.get("数据单元标识(DT)")
    check_true("03H DT=02 01 解析为 F10", dt and "F10" in str(dt[3]), dt)


def test_sta_sim_service():
    section("[12] 从节点模拟服务：一条串口同时当 645 / 698 从站")
    import sta_sim_service as sim

    class FakeSerial:
        def __init__(self):
            self.out = []

        def write(self, data):
            self.out.append(bytes(data))
            return len(data)

    svc = sim.StaSimService("COM_TEST", protocols={sim.PROTO_645, sim.PROTO_698},
                            meter_address="000000000033")
    check("协议文案含两种", svc.protocol_text(), "645-2007 + 698.45")
    check("只启 645 时文案", sim.StaSimService("X", protocols={sim.PROTO_645}).protocol_text(),
          "645-2007")
    check("只启 698 时文案", sim.StaSimService("X", protocols={sim.PROTO_698}).protocol_text(),
          "698.45")

    ser = FakeSerial()
    # 645 读正向有功总电能
    frame645 = C.parse_hex("68 33 00 00 00 00 00 68 11 04 33 33 34 33 E5 16")
    svc._dispatch_645(frame645, ser)
    check("645 请求有应答", len(ser.out), 1)
    check_true("645 应答是 91H 正常帧", ser.out[0][8:9] == b"\x91", ser.out[0].hex(" "))

    # 645 广播复位：不回应答
    ser.out.clear()
    reset = C.parse_hex("68 AA AA AA AA AA AA 68 14 0C 34 37 D3 37 33 6A 3D D3 33 33 33 33 DA 16")
    svc._dispatch_645(reset, ser)
    check("广播复位不回应答", len(ser.out), 0)

    # 698 读正向有功电能
    from dl_t698_45_frame_gen import DLT69845FrameGenerator

    ser.out.clear()
    req = DLT69845FrameGenerator().generate_get_request_normal(
        bytes([0x05]) + bytes.fromhex("330000000000"), 0, 0x01, bytes.fromhex("00100200"))
    svc._dispatch_698(req, ser)
    check("698 请求有应答", len(ser.out), 1)
    check_true("698 应答是 0xC3 响应帧", ser.out[0][3:4] == b"\xC3", ser.out[0].hex(" ")[:60])

    # 未启用协议不应答
    only645 = sim.StaSimService("X", protocols={sim.PROTO_645})
    ser.out.clear()
    only645._dispatch_698(req, ser)
    check("只启 645 时 698 请求不应答", len(ser.out), 0)

    # 帧拼接（粘包）也能拆开
    ser.out.clear()
    two = frame645 + reset
    svc._dispatch_645(two, ser)
    check("粘包两帧都处理（复位不答 → 只 1 条应答）", len(ser.out), 1)


def test_sta_sim_page():
    section("[13] 流程页内置从节点模拟：协议自动判定 / 未启动时拦截")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()
    w.show()
    app.processEvents()
    w._select_page(C.PAGE_FLOW, notify=True)
    app.processEvents()
    check("页面有启动按钮", w.btn_sta_sim.text(), "启动从节点模拟")
    check("初始未启动", w.lbl_sta_sim.text(), "○ 未启动")

    # 两个从节点：645 + 698 → 两种协议都要启
    w.node_widgets[0]["addr"].setText("0000000033")
    w.node_widgets[0]["proto"].setCurrentIndex(max(0, w.node_widgets[0]["proto"].findData(2)))
    w.node_widgets[1]["addr"].setText("000006881225")
    w.node_widgets[1]["proto"].setCurrentIndex(max(0, w.node_widgets[1]["proto"].findData(3)))
    w._on_network_edited()
    app.processEvents()
    check("按组网参数判定需启两种协议", w._sta_protocols(), {1, 2})

    # 只留 698 从节点 → 只需 698
    w.node_widgets[0]["use"].setChecked(False)
    w._on_network_edited()
    app.processEvents()
    check("只启用 698 从节点 → 只启 698", w._sta_protocols(), {2})
    w.node_widgets[0]["use"].setChecked(True)
    w._on_network_edited()
    app.processEvents()

    # 未选端口时不启动（这里是「（未检测到串口）」占位）
    w.combo_sta_port.clear()
    w.combo_sta_port.addItem("（未检测到串口）")
    check("占位端口不启动", w._start_sta_sim("（未检测到串口）"), False)
    w.close()


def test_ack_payload():
    section("[14] 确认帧 = 4 字节 BS + 2 字节等待时间（表 9）")
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()

    class FakeChannel:
        def __init__(self):
            self.sent = []

        def ready(self):
            return True

        def state_text(self):
            return "fake"

        def send(self, frame):
            self.sent.append(bytes(frame))
            return True, ""

        def cleanup(self):
            pass

        def rebind_bluetooth(self):
            pass

    w._channel = FakeChannel()
    # 06H F5 主动上报（现场日志里那条）
    report = C.parse_hex(
        "68 30 00 C3 00 00 10 33 00 01 06 10 00 01 02 1E 68 33 00 00 00 00 00 68 91 12 34 48 "
        "33 37 33 33 33 33 33 33 33 33 33 33 33 33 DD DD AA 16")
    w._on_frame(report)
    app.processEvents()
    check("回了确认帧", len(w._channel.sent), 1)
    ack = w._channel.sent[0]
    rows = {r[0].strip(): r for r in C.parse_table(ack)}
    check("确认帧数据单元 6 字节（4B BS + 2B 等待时间）", rows.get("数据单元")[2], "6字节")
    check_true("BS = FE FF FF FF，等待时间 = 01 00（1s）",
               rows.get("数据单元")[1].replace(" ", "").upper() == "FEFFFFFF0100",
               rows.get("数据单元")[1])
    check("确认帧总长 21（6 字节数据单元）", len(ack), 21)
    check_true("帧以 68 开头 16 结尾", ack[0] == 0x68 and ack[-1] == 0x16, ack.hex(" "))
    # 解析侧：表 9 三段都必须解出来
    check("解析出命令状态 D0=未处理", rows.get("命令状态")[2], "未处理")
    check("解析出等待时间 1s", rows.get("等待时间")[2], "1")
    check_true("信道状态按 D1~D31 解（31 个信道全部空闲）",
               "全部空闲" in rows.get("信道状态")[2], rows.get("信道状态")[2])
    check_true("信道 1~7 明细逐信道可读",
               rows.get("信道1~7状态")[2].count("闲") == 7, rows.get("信道1~7状态"))
    check_true("信道 24~31 明细逐信道可读",
               rows.get("信道24~31状态")[2].count("闲") == 8, rows.get("信道24~31状态"))

    # 解析侧：真实形态的上行确认帧（D0=已处理、信道3 忙、等待时间 2s）
    cmd0 = C.find_command(0, 1)
    #  BS 小端 F7 FF FF FF → D0=1 已处理；D3=0 → 信道3 忙；其余信道闲
    real = C.build_frame(cmd0, {}, src="000000000001", dst="123456789012",
                         info={"通信模块标识": 1, "dir": 1, "prm": 0},
                         raw_data=bytes.fromhex("F7 FF FF FF 02 00"))
    real_rows = {r[0].strip(): r for r in C.parse_table(real)}
    check("D0=1 → 已处理", real_rows.get("命令状态")[2], "已处理")
    check("等待时间 2s", real_rows.get("等待时间")[2], "2")
    check_true("忙信道列出序号（信道3）",
               real_rows.get("信道状态")[2].startswith("忙：信道3"),
               real_rows.get("信道状态")[2])
    check("信道1~7 明细标出信道3忙", real_rows.get("信道1~7状态")[2].split()[2], "3忙")

    # 少于 6 字节（只发 4B BS）也要明确提示缺等待时间，而不是静默通过
    short = C.build_frame(cmd0, {}, src="000000000001", dst="123456789012",
                          info={"通信模块标识": 1, "dir": 1, "prm": 0},
                          raw_data=bytes.fromhex("FE FF FF FF"))
    short_rows = {r[0].strip(): r for r in C.parse_table(short)}
    check("4B BS 无等待时间 → 解析标「缺失」", short_rows.get("等待时间")[2], "缺失")

    # 00H F1 与 00H F2 数据单元结构不同，解析不能混用（表 9 vs 表 10）
    check_true("F1 确认不出现「错误状态字」行（表 10 才有）",
               not any("错误状态字" in k for k in rows), sorted(rows))
    check_true("F1 确认解析出信道状态与等待时间",
               ("信道状态" in rows) and ("等待时间" in rows), sorted(rows))

    deny = C.build_frame(C.find_command(0, 2), {}, src="000000000001", dst="123456789012",
                         info={"通信模块标识": 1, "dir": 1, "prm": 0},
                         raw_data=bytes([11]))          # 11 = 从节点不应答
    deny_rows = {r[0].strip(): r for r in C.parse_table(deny)}
    check("F2 否认解析出错误状态字=11", deny_rows.get("错误状态字")[2], "11")
    check_true("F2 否认的错误状态字带表 10 含义",
               "从节点不应答" in deny_rows.get("错误状态字")[3], deny_rows.get("错误状态字"))
    check_true("F2 否认不出现信道状态/等待时间（那是 F1 的字段）",
               not any(k in deny_rows for k in ("信道状态", "等待时间", "命令状态")), sorted(deny_rows))
    w.close()


def test_read_payload():
    section("[15] 抄表报文按从节点协议填充（645 / 698）")
    import gdw_meter_request as req

    f645 = req.build_645_read_total_active("000000000033")
    check("645 读正向有功总电能逐字节",
          C.format_hex(f645), "68 33 00 00 00 00 00 68 11 04 33 33 34 33 E5 16")
    f698 = req.build_698_read_total_active("000000000033")
    check_true("698 是 GET 请求帧", f698[:1] == b"\x68" and f698[3] == 0x43, f698.hex(" "))
    check_true("698 报文含 OAD 00100200", "00100200" in f698.hex(), f698.hex(" "))
    check("协议映射 645-2007", req.msg_proto_for_node(2), 2)
    check("协议映射 698", req.msg_proto_for_node(3), 3)

    # 13H F1 组帧：地址逆序 + 报文长度派生 + 载荷按协议
    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()

    class FakeChannel:
        def __init__(self):
            self.sent = []

        def ready(self):
            return True

        def state_text(self):
            return "fake"

        def send(self, frame):
            self.sent.append(bytes(frame))
            return True, ""

        def cleanup(self):
            pass

        def rebind_bluetooth(self):
            pass

    w._channel = FakeChannel()
    w.node_widgets[0]["addr"].setText("0000000033")
    w.node_widgets[0]["proto"].setCurrentIndex(2)      # 645-2007
    w.node_widgets[1]["addr"].setText("000006881225")
    w.node_widgets[1]["proto"].setCurrentIndex(3)      # 698.45
    w._on_network_edited()
    app.processEvents()

    step = F.FlowStep(F.KIND_SEND, "监控从节点", key="13-1", timeout=6.0)
    frames = w._build_flow_frames(step)
    check("按从节点各发一帧", len(frames), 2)
    rows0 = {r[0].strip(): r for r in C.parse_table(frames[0][0])}
    rows1 = {r[0].strip(): r for r in C.parse_table(frames[1][0])}
    check("645 节点协议类型=2", rows0["通信协议类型"][2], "2")
    check("645 节点报文长度=16（不再是 0）", rows0["报文长度"][2], "16")
    check_true("645 节点载荷是 645 读帧",
               rows0["报文内容"][1].startswith("68 33 00 00 00 00 00 68 11 04"),
               rows0["报文内容"][1][:40])
    check("698 节点协议类型=3", rows1["通信协议类型"][2], "3")
    check("698 节点报文长度=25（含时间标签）", rows1["报文长度"][2], "25")
    check_true("698 节点载荷是 GET 帧",
               rows1["报文内容"][1].startswith("68 17 00 43"), rows1["报文内容"][1][:40])
    # 地址必须低字节在前（000000000033 → 33 00 00 00 00 00）
    check_true("附属节点地址低字节在前",
               "33 00 00 00 00 00" in C.format_hex(frames[0][0]),
               C.format_hex(frames[0][0])[:90])
    w.close()


def test_two_round_read():
    section("[16] 抄表两轮（延时无关 / 延时相关）+ 数据一致性判定")
    # 结构：两轮都必须在
    for fid in ("spot_read", "master_read", "meter_read"):
        case = F.flow_case(fid)
        keys = [s.key for s in case.steps if s.key]
        waits = [(s.afn, s.fn) for s in case.steps if s.kind == F.KIND_WAIT]
        reads = [s for s in case.steps if s.kind == F.KIND_SEND and s.key == "13-1"]
        check_true(f"{case.name} 有两轮 13H F1", len(reads) >= 2, len(reads))
        check_true(f"{case.name} 第一轮延时标志=0",
                   reads[0].values.get("通信延时相关性标志") == 0, reads[0].values)
        check_true(f"{case.name} 第二轮延时标志=1",
                   reads[1].values.get("通信延时相关性标志") == 1, reads[1].values)
        check_true(f"{case.name} 第二轮接受 14H F3 上行",
                   (0x14, 0x03) in tuple(reads[1].accept), reads[1].accept)
        check_true(f"{case.name} 等待 14H F3 与 13H F1",
                   (0x14, 0x03) in waits and (0x13, 0x01) in waits, waits)
        check_true(f"{case.name} 两轮都有数据一致性校验",
                   reads[0].check == F.CHECK_READ_MATCH
                   and any(s.kind == F.KIND_WAIT and s.check == F.CHECK_READ_MATCH
                           for s in case.steps),
                   [s.check for s in reads])

    # 判定：与虚拟表应答一致才通过
    resp = C.parse_hex("68 33 00 00 00 00 00 68 91 08 33 33 34 33 AB 89 67 45 49 16")
    payload = bytes([0x00, 0x01]) + resp
    rows = [("  报文内容", payload.hex(" ").upper(), f"{len(payload)}字节", "", 0, 0)]
    ok, note = F.run_check(F.CHECK_READ_MATCH, rows, (), [resp])
    check_true("数据一致 → 通过", ok, note)

    bad = C.parse_hex("68 33 00 00 00 00 00 68 91 08 33 33 34 33 01 02 03 04 49 16")
    rows_bad = [("  报文内容", (bytes([0x00, 0x01]) + bad).hex(" ").upper(), "", "", 0, 0)]
    ok, note = F.run_check(F.CHECK_READ_MATCH, rows_bad, (), [resp])
    check("数据不一致 → 失败", ok, False)
    check_true("说明给出差异", "不一致" in note, note)

    # 只对 AFN/Fn 对上是**不够**的：把请求帧当上报必须判失败
    req = C.parse_hex("68 33 00 00 00 00 00 68 11 04 33 33 34 33 E5 16")
    rows_req = [("  报文内容", (bytes([0x00, 0x01]) + req).hex(" ").upper(), "", "", 0, 0)]
    check("上报是请求帧而非应答 → 失败",
          F.run_check(F.CHECK_READ_MATCH, rows_req, (), [resp])[0], False)

    # 没有虚拟表应答记录时，仍要求是有效应答帧（不能空判）
    ok, note = F.run_check(F.CHECK_READ_MATCH, rows, (), [])
    check_true("无应答记录时做结构校验并通过", ok, note)
    check("无应答记录且上报是请求帧 → 失败",
          F.run_check(F.CHECK_READ_MATCH, rows_req, (), [])[0], False)

    # 报文内容为空 → 失败
    check("上报内容为空 → 失败",
          F.run_check(F.CHECK_READ_MATCH, [("  报文内容", "", "", "", 0, 0)], (), [resp])[0], False)


    # 现场真实一例：CCO 上报的 698 应答（53B）必须能被摘出并与虚拟表应答一致
    real_resp = C.parse_hex(
        "68 33 00 C3 05 33 00 00 00 00 00 00 5E 7F 85 01 01 00 10 02 00 01 01 05 06 00 00 00 "
        "01 06 00 00 00 01 06 00 00 00 01 06 00 00 00 01 06 00 00 00 01 00 AA 59 16")
    real_rx = C.parse_hex(
        "68 54 00 83 04 00 10 33 00 1A 33 00 00 00 00 00 11 11 96 35 13 00 13 01 00 00 00 03 35 "
        "68 33 00 C3 05 33 00 00 00 00 00 00 5E 7F 85 01 01 00 10 02 00 01 01 05 06 00 00 00 01 "
        "06 00 00 00 01 06 00 00 00 01 06 00 00 00 01 06 00 00 00 01 00 AA 59 16 B2 16")
    ok, note = F.run_check(F.CHECK_READ_MATCH, C.parse_table(real_rx), (), [real_resp])
    check_true("现场实例：53B 698 应答能摘出并判定一致", ok, note)
    check("698 帧按「总长 = L + 2」正确切分", len(F.extract_meter_frames(real_resp)[0]), 53)


def test_delay_correct():
    section("[17] 14H F3：收到延时修正请求后按下行回送报文")
    import gdw_meter_request as req

    app = QApplication.instance() or QApplication([])
    w = W.GdwTestWidget()

    class FakeChannel:
        def __init__(self):
            self.sent = []

        def ready(self):
            return True

        def state_text(self):
            return "fake"

        def send(self, frame):
            self.sent.append(bytes(frame))
            return True, ""

        def cleanup(self):
            pass

        def rebind_bluetooth(self):
            pass

    w._channel = FakeChannel()
    w.node_widgets[0]["addr"].setText("0000000033")
    w.node_widgets[0]["proto"].setCurrentIndex(3)      # 698.45
    w._on_network_edited()
    app.processEvents()

    content = req.build_698_read_total_active("000000000033")
    data = (bytes.fromhex("330000000000") + (1500).to_bytes(2, "little")
            + bytes([len(content)]) + content)
    body = bytes([0x83]) + b"\x00" * 6 + bytes([0x14, 0x04, 0x00]) + data
    total = len(body) + 5
    up_f3 = bytes([0x68, total & 0xFF, 0]) + body + bytes([sum(body) & 0xFF, 0x16])

    w._flow_runner = F.FlowRunner(F.flow_case("meter_read"))
    w._flow_action = type("A", (), {"kind": "wait", "index": 0,
                                    "step": F.FlowStep(F.KIND_WAIT, "等 14H F3",
                                                       afn=0x14, fn=3)})()
    w._on_frame(up_f3)
    cap = w._flow_delay_req or {}
    check("捕获到预计延迟时间", cap.get("delay_ms"), 1500)
    check("捕获到待修正报文", len(cap.get("content") or b""), len(content))
    check("捕获到从节点地址", cap.get("addr"), "000000000033")

    frame = w._build_flow_frames(F.FlowStep(F.KIND_SEND, "回复 14H F3 下行",
                                            key="14-3", timeout=6.0))[0][0]
    rows = {r[0].strip(): r for r in C.parse_table(frame)}
    check("下行数据长度 = 报文长度", rows.get("数据长度")[2], str(len(content)))
    check("下行报文与上行请求一致",
          rows.get("修正通信数据内容")[1], content.hex(" ").upper())
    note = req.apply_delay_correction(content, 1500)[1]
    check_true("修正说明可读（明确写了回送策略）",
               ("回送" in note) and ("1500" in note), note)
    w._flow_runner = None
    w.close()


def main():
    test_cases()
    test_runner()
    test_wait_match()
    test_register_uplink()
    test_route_read_flow()
    test_serve_and_ack_policy()
    test_broadcast_payloads()
    test_no_reply_and_698()
    test_read_content_supported_by_sim()
    test_checks()
    test_page()
    test_prerequisite()
    test_confirm_rules()
    test_widget_confirm_and_reset()
    test_power_on()
    test_early_uplink()
    test_fn_encoding()
    test_sta_sim_service()
    test_sta_sim_page()
    test_ack_payload()
    test_read_payload()
    test_two_round_read()
    test_delay_correct()

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
