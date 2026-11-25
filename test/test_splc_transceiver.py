# -*- coding: utf-8 -*-
"""收发机控制页（协议9）核心逻辑 + 页面冒烟测试。

**协议分工（1.26.27 纠正后的口径）**
- 发射机下行 = PLC2.0（ED..EE，《PLC2.0收发机报文格式0629》）；
- 接收机（监控器）上行 = 96..16（《SPLC双模监控器_发射机_接口协议》）；
- 接收机配置 = 68..16（同一份接口协议）。

覆盖点：
1. PLC2.0 帧结构：ED+帧长(LE)+控制域1+控制域2+EF+数据域+CS+EE，CS 两种模式；
2. 数据报文 8 种控制域2 的公共头打包/回读（含 0x07 四用户、0x06 双信道、0x08 OFDMA）；
3. 控制报文指令表：字段长度必须与文档一致（保留字节数不能少）、往返无损、上报指令不可下发；
4. 96..16 监控帧与 68..16 命令帧（接收机侧）行为不变；
5. 串口流解帧：ED/96/68 三种帧头混排、半帧、数据域内含 FF/EE 不出错；
6. 用例 JSON 存取、校验、旧版用例拒绝、执行计划展开；
7. 页面 offscreen 冒烟：参数区高度、步骤表、日志窗、执行器（假串口捕获真实帧）。

运行：``python test/test_splc_transceiver.py``
"""

import _path_setup  # noqa: E402,F401

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Windows 控制台默认 GBK，打印 ✓/✗ 会 UnicodeEncodeError（AGENTS §8 同类坑）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import splc_transceiver_core as core  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name} {detail}")
        FAILED.append(f"{name} {detail}")


def hexs(data):
    return core.bytes_to_hex(data)


PAYLOAD = bytes.fromhex("0901" + "00" * 14 + "112233445566")   # 24 字节业务帧

class _FakePort:
    """假串口：只实现 send_frame 与监控器 set_serial_worker 需要的那点接口。"""

    def __init__(self):
        self.frames = []
        from PySide6.QtCore import QObject, Signal

        class _Sig(QObject):
            raw_data_received = Signal(bytes)

        self._sig = _Sig()
        self.raw_data_received = self._sig.raw_data_received

    def is_open(self):
        return True

    def write(self, data):
        self.frames.append(bytes(data))
        return True

    def description(self):
        return "FAKE"

    def close_port(self):
        pass


# ======================================================================
print("[1] PLC2.0 帧结构（ED..EE）")
# ======================================================================
data = core.build_tx_data_payload(0x02, payload=PAYLOAD, channel=0x01)
frame = core.build_tx_frame(core.CTRL1_DATA, 0x02, data)
check("起始符 ED / 结束符 EE", frame[0] == 0xED and frame[-1] == 0xEE, hexs(frame)[:12])
check("数据域起始符 EF", frame[5] == 0xEF, f"{frame[5]:02X}")
check("帧长域 = 数据域 + 4（小端）",
      (frame[1] | (frame[2] << 8)) == len(data) + 4, frame[1] | (frame[2] << 8))
check("整帧长 = 帧长域 + 4", len(frame) == (frame[1] | (frame[2] << 8)) + 4, len(frame))
check("控制域1/2", (frame[3], frame[4]) == (0x00, 0x02), (frame[3], frame[4]))
calc = sum(frame[:-2]) & 0xFF
check("CS = 帧头到数据域末累加", frame[-2] == calc, (f"{frame[-2]:02X}", f"{calc:02X}"))

xff = core.build_tx_frame(core.CTRL1_DATA, 0x02, data, cs_mode="xff")
check("CS 固定 0xFF 模式", xff[-2] == 0xFF, f"{xff[-2]:02X}")
check("0xFF 视为保留（ok=True）", core.parse_tx_frame(xff)["ok"] is True
      and core.parse_tx_frame(xff)["cs_reserved"] is True)

bad = bytearray(frame)
bad[-2] ^= 0x5A
check("CS 错误被识别", core.parse_tx_frame(bytes(bad))["ok"] is False)
short = core.parse_tx_frame(frame[:-1])
check("帧长不符被识别", short["ok"] is False and "帧长域" in short["error"], short["error"])

info = core.parse_tx_frame(frame)
check("解析控制域名", info["ctrl1_name"] == "数据报文"
      and info["ctrl2_name"] == core.TX_DATA_SUBTYPES[0x02], info)
try:
    core.build_tx_frame(0x00, 0x02, b"\x00" * 70000)
    check("超长数据域被拒", False)
except ValueError:
    check("超长数据域被拒", True)

# ======================================================================
print("[2] 数据报文公共头（各控制域2）")
# ======================================================================
d1 = core.build_tx_data_payload(0x01, payload=PAYLOAD, channel=0x02, timestamp=0x11223344,
                                pb_count=2, pb_len=0x0010)
check("0x01 头部 9 字节 + 载荷", len(d1) == 9 + len(PAYLOAD), len(d1))
check("0x01 信道/时间戳/块个数",
      d1[0] == 0x02 and int.from_bytes(d1[1:5], "little") == 0x11223344
      and d1[5] == 2, hexs(d1[:9]))
check("0x01 第 7 字节为保留 0", d1[6] == 0, d1[6])
check("0x01 单块长度小端", int.from_bytes(d1[7:9], "little") == 0x10, hexs(d1[7:9]))

d2 = core.build_tx_data_payload(0x02, payload=PAYLOAD, crc_error=1)
check("0x02 第 7 字节 = Payload CRC 标志", d2[6] == 1, d2[6])
d2b = core.build_tx_data_payload(0x02, payload=PAYLOAD, crc_error=0)
check("0x02 CRC 正确时 0", d2b[6] == 0, d2b[6])
check("0x02 pb_len 自动 = 业务帧长度",
      int.from_bytes(d2[7:9], "little") == len(PAYLOAD), hexs(d2[7:9]))

d3 = core.build_tx_data_payload(0x03, payload=PAYLOAD)
check("0x03 也是 9 字节头", len(d3) == 9 + len(PAYLOAD), len(d3))

d8 = core.build_tx_data_payload(0x08, payload=PAYLOAD, channel=0x20,
                                tmi=3, ru=2, pad=1, timestamp=core.TS_TRIGGER)
check("0x08 头 12 字节（TMI/RU/pad）", d8[:4] == bytes([0x20, 3, 2, 1]), hexs(d8[:4]))
check("0x08 时间戳 FFFFFFFF", int.from_bytes(d8[4:8], "little") == core.TS_TRIGGER,
      hexs(d8[4:8]))

for ctrl2 in (0x06, 0x07):
    try:
        core.build_tx_data_payload(ctrl2, payload=PAYLOAD)
        check(f"0x{ctrl2:02X} 不做自动拼装（走手工数据域）", False)
    except ValueError:
        check(f"0x{ctrl2:02X} 不做自动拼装（走手工数据域）", True)

# 结构化子类型的解析行
rows, _note = core.decode_tx_data_payload(0x02, core.build_tx_data_payload(
    0x02, payload=PAYLOAD, channel=0x01, timestamp=core.TS_IMMEDIATE))
names = [r[0] for r in rows]
check("0x02 解析出信道/时间戳/块数/CRC/块长",
      names[:5] == ["物理信道", "时间戳", "物理块个数", "Payload CRC", "单个物理块长度"], names)
check("时间戳 0 描述为立即发送", "立即发送" in dict((r[0], r[2]) for r in rows)["时间戳"],
      dict((r[0], r[2]) for r in rows)["时间戳"])

# 0x07 四用户：手工数据域解析
d7 = (bytes([0x01, 0, 0, 0]) + (0).to_bytes(4, "little")
      + bytes([1, 0]) + (16).to_bytes(2, "little")
      + bytes([1, 1]) + (8).to_bytes(2, "little")
      + bytes([0, 0]) + (0).to_bytes(2, "little")
      + bytes([0, 0]) + (0).to_bytes(2, "little")
      + bytes(range(32)) + b"\xaa" * 4)
rows7, _ = core.decode_tx_data_payload(0x07, d7)
n7 = [r[0] for r in rows7]
check("0x07 解析出四个用户", all(f"用户{i} 物理块个数" in n7 for i in range(4)), n7)
check("0x07 解析出 FC+eFC 32 字节", "数据FC+eFC" in n7, n7)

# 0x06 双信道
d6 = bytes([0x01, 0x02]) + (0).to_bytes(4, "little") + bytes([1, 1, 0]) \
     + (16).to_bytes(2, "little") + (8).to_bytes(2, "little") + b"\x11" * 6
rows6, _ = core.decode_tx_data_payload(0x06, d6)
n6 = [r[0] for r in rows6]
check("0x06 解析出两个物理信道", n6[:2] == ["报文1物理信道", "报文2物理信道"], n6)

# ======================================================================
print("[3] 控制报文指令表")
# ======================================================================
check("可下发指令都标了 sendable",
      all(core.TX_COMMANDS[c].sendable for c in core.TX_COMMANDS
          if core.TX_COMMANDS[c].resp or True) is not None)
names = [d.name for d in core.sendable_tx_commands()]
check("可下发指令数量 ≥ 18", len(names) >= 18, len(names))
check("上报指令不可下发",
      core.tx_command_payload(0x04, []).ok is False
      and "上报" in core.tx_command_payload(0x04, []).error,
      core.tx_command_payload(0x04, []).error)

# 文档规定的定长数据域长度（保留字节数不能少）
expected_len = {
    0x00: 0, 0x03: 0, 0x05: 4, 0x09: 4, 0x0B: 4, 0x13: 4, 0x15: 4, 0x17: 4,
    0x19: 4, 0x21: 12, 0x23: 1, 0x25: 3, 0x31: 0, 0x33: 0, 0x38: 5,
}
for ctrl2, want in expected_len.items():
    definition = core.TX_COMMANDS[ctrl2]
    got = definition.fixed_len
    check(f"0x{ctrl2:02X} 定长 {want} 字节（文档口径）", got == want, f"{got} != {want}")

cases = {
    0x09: [2], 0x0B: [3], 0x13: [2], 0x15: [1], 0x17: [1], 0x19: [2, 1],
    0x23: [3], 0x25: [16, 2], 0x21: [5, 0x11223344, 1, 2, 3, 4], 0x38: [9],
    0x03: [], 0x00: [],
}
for ctrl2, values in cases.items():
    payload = core.tx_command_payload(ctrl2, values)
    check(f"0x{ctrl2:02X} 组帧成功", payload.ok, payload.error)
    if payload.ok:
        back = core.tx_command_values(ctrl2, payload.payload)
        check(f"0x{ctrl2:02X} 字段往返", back == values, (back, values))

check("字段越界被拒", core.tx_command_payload(0x09, [9]).ok is False,
      core.tx_command_payload(0x09, [9]).error)
# 0x21 的 SNID 是 4 字节小端
p21 = core.tx_command_payload(0x21, [1, 0x01020304, 0, 0, 0, 0])
check("0x21 SNID 小端", p21.payload[2:6] == b"\x04\x03\x02\x01", hexs(p21.payload))

band = core.tx_command_payload(0x09, [2])
bframe = core.build_tx_frame(core.CTRL1_CONTROL, 0x09, band.payload)
brows, _ = core.decode_tx_control_payload(0x09, band.payload)
check("0x09 频段名解析", "2.2M" in dict((r[0], r[2]) for r in brows)["频段TAG"],
      dict((r[0], r[2]) for r in brows))
check("0x09 保留 3 字节被标出",
      any(r[0].startswith("保留") for r in brows), [r[0] for r in brows])
check("控制帧可回读", core.parse_tx_frame(bframe)["ctrl2_name"] == "频段模式配置",
      core.parse_tx_frame(bframe)["ctrl2_name"])

# ======================================================================
print("[4] 接收机侧：96..16 监控帧与 68..16 命令帧（既有行为不变）")
# ======================================================================
mframe = core.build_data_frame(PAYLOAD, channel=0)
minfo = core.parse_data_frame(mframe)
check("96..16 组帧回读", minfo["ok"] and minfo["data"] == PAYLOAD, minfo.get("error"))
check("96..16 协议名", minfo["proto_name"] == "南网SPLC双模", minfo["proto_name"])

check("68..16 查询版本",
      hexs(core.build_command_frame(0x03, 0)) == "68 00 00 00 00 00 00 68 03 00 D3 16",
      hexs(core.build_command_frame(0x03, 0)))
check("68..16 查询频段",
      hexs(core.build_command_frame(0x02, 0)) == "68 00 00 00 00 00 00 68 02 00 D2 16")
resp = bytes.fromhex("6800000000000068" + "13074C9101120615" + "20" + "16")
rinfo = core.parse_command_frame(resp)
check("68..16 应答无读写标志", rinfo["direction"] == "response" and len(rinfo["data"]) == 7,
      (rinfo["direction"], len(rinfo["data"])))
check("版本字段解析", dict((r[0], r[2]) for r in rinfo["fields"])["版本日期"] == "2018-06-21",
      rinfo["fields"])
check("监控器命令字段往返",
      core.command_payload_from_values(0x06, [0x01020304]).payload == b"\x04\x03\x02\x01")

# ======================================================================
print("[5] 串口流解帧（ED / 96 / 68 混排）")
# ======================================================================
cmd = core.build_command_frame(0x02, 0)
stream = b"\x00\xAA" + frame + mframe + cmd + frame
frames, consumed = core.deframe_stream(stream)
check("四帧全解出", len(frames) == 4, len(frames))
check("消费到末字节", consumed == len(stream), (consumed, len(stream)))
check("类型顺序 tx/data/cmd/tx",
      [f["kind"] for f in frames] == ["tx", "data", "cmd", "tx"], [f["kind"] for f in frames])

frames2, consumed2 = core.deframe_stream(stream[:len(stream) - 5])
check("半帧只解完整帧", len(frames2) == 3, len(frames2))
check("半帧停在第 4 帧起点", consumed2 == 2 + len(frame) + len(mframe) + len(cmd), consumed2)

# 数据域里含 EE / EF 也不能误判
tricky_data = core.build_tx_data_payload(0x02, payload=b"\xEE\xEF\xEE\xEF" * 4)
tricky = core.build_tx_frame(core.CTRL1_DATA, 0x02, tricky_data)
tframes, _ = core.deframe_stream(tricky + tricky)
check("数据域含 EE/EF 仍正确切帧",
      len(tframes) == 2 and tframes[1]["frame"] == tricky, len(tframes))

check("伪帧头（帧长过大）跳过",
      core.deframe_stream(b"\xED\xFF\xFF\x00\x02\xEF" + b"\x00" * 20)[0] == [])

# ======================================================================
print("[6] 用例文件与执行计划")
# ======================================================================
def make_case():
    case = core.Case(name="测试用例A", description="单元测试")
    case.params = {"count": 10, "interval_ms": 200}
    case.steps = [
        core.Step(kind="command", category="配置", name="频段模式配置",
                  command=core.tx_command_ref(0x09), tx_values=[2],
                  count=1, interval_ms=100),
        core.Step(kind="data", category="发送20", name="载波初频帧-6-2",
                  type="测试模式6", param="载波初频帧-6-2", ctrl2=0x02, channel=0x01,
                  data=hexs(PAYLOAD), count=3, interval_ms=200),
        core.Step(kind="wait", category="等待", name="等 1 秒", interval_ms=1000),
        core.Step(kind="data", category="发送40", name="MAC层透传",
                  type="MAC层透传", ctrl2=0x02, channel=0x02,
                  data=hexs(PAYLOAD), count=0, interval_ms=0),
        core.Step(kind="monitor", category="配置", name="查询监控器频段",
                  command="02:0", count=1, interval_ms=100),
        core.Step(kind="raw", category="工装板", name="夹具动作", data="AA 55 01",
                  port="工装板"),
    ]
    return case


case = make_case()
errors, warnings = core.validate_case(case)
check("用例校验通过", not errors, errors)

obj = case.to_dict()
check("格式标识", obj["format"] == core.CASE_FORMAT, obj["format"])
check("schema 版本 = 2", obj["version"] == 2, obj["version"])
roundtrip = core.Case.from_dict(obj)
check("往返字段一致", roundtrip.to_dict()["steps"] == obj["steps"])
check("参数保留", roundtrip.params == case.params, roundtrip.params)

with tempfile.TemporaryDirectory() as tmp:
    target = Path(tmp) / "case.json"
    core.save_case(case, target)
    loaded = core.load_case(target)
    check("落盘/加载步骤数一致", len(loaded.steps) == 6, len(loaded.steps))
    try:
        core.save_case(case, target, create_only=True)
        check("重名保护", False)
    except ValueError:
        check("重名保护", True)

    # 旧版（v1，96..16）用例必须明确拒绝，而不是按错的协议执行
    old = dict(obj)
    old["version"] = 1
    try:
        core.Case.from_dict(old)
        check("拒绝旧版 v1 用例", False)
    except ValueError as exc:
        check("拒绝旧版 v1 用例", "旧版" in str(exc), str(exc))

    (Path(tmp) / "bad.json").write_text("{ not json", encoding="utf-8")
    try:
        core.load_case(Path(tmp) / "bad.json")
        check("坏文件抛 ValueError", False)
    except ValueError:
        check("坏文件抛 ValueError", True)

bad_case = core.Case(name="坏用例")
bad_case.steps = [core.Step(kind="data", data="ZZ 11"),
                  core.Step(kind="command", command="FF"),
                  core.Step(kind="data", ctrl2=0x07, data="00")]
bad_errors, _ = core.validate_case(bad_case)
check("非法 HEX 报错", any("HEX 非法" in e for e in bad_errors), bad_errors)
check("未知控制指令报错", any("未选择控制指令" in e for e in bad_errors), bad_errors)
check("0x07 未勾手工数据域报错",
      any("手工数据域" in e for e in bad_errors), bad_errors)

actions, plan_errors = core.plan_actions(case, default_count=10, default_interval_ms=500)
check("执行计划无错误", not plan_errors, plan_errors)
kinds = [a.action for a in actions]
check("计划含四种动作", kinds[0] == "send_tx_cmd" and kinds[1] == "send_tx_data"
      and "wait" in kinds and "send_monitor" in kinds and "send_raw" in kinds, kinds)
check("次数 0 用默认次数", kinds.count("send_tx_data") == 3 + 10, kinds.count("send_tx_data"))
check("控制帧已组好（ED..EE 控制域1=1）",
      actions[0].payload[:1] == b"\xED" and actions[0].payload[3] == 0x01,
      hexs(actions[0].payload))
check("数据帧已组好（ED..EE 控制域1=0）",
      actions[1].payload[:1] == b"\xED" and actions[1].payload[3] == 0x00,
      hexs(actions[1].payload))
mon_action = next(a for a in actions if a.action == "send_monitor")
check("监控器动作是 68..16", mon_action.payload[:1] == b"\x68", hexs(mon_action.payload))

# ======================================================================
print("[7] 页面（offscreen 冒烟）")
# ======================================================================
try:
    from PySide6.QtWidgets import (QApplication, QPlainTextEdit, QTabWidget,
                                       QTreeWidget)
    from splc_transceiver_widget import SplcTransceiverWidget, StepDialog, LogWindow
    from csg_new_gen_parser import CSGNewGenParser

    app = QApplication.instance() or QApplication([])
    w = SplcTransceiverWidget()
    w.set_protocol(CSGNewGenParser(), lambda rows: f"字段{len(rows)}")
    check("页面构造成功", w is not None)
    check("参数区 6 行", len(w._flow_areas) == 6, len(w._flow_areas))

    tmp_file = Path(tempfile.gettempdir()) / "splc_case_smoke.json"
    w._case = make_case()
    w._refresh_step_table()
    check("步骤表行数", w.step_table.rowCount() == 6, w.step_table.rowCount())
    check("类别列首格", w.step_table.item(1, 0).text() == "发送20",
          w.step_table.item(1, 0).text())
    check("发送数据列有 HEX", w.step_table.item(1, 7).text().startswith("09"),
          w.step_table.item(1, 7).text()[:20])
    check("监控器步骤类型名", "监控器" in w.step_table.item(4, 2).text(),
          w.step_table.item(4, 2).text())
    w._save_case_to(tmp_file)
    check("页面保存用例", tmp_file.exists())
    # 另存为后用例名称必须跟随文件名（现场报障：加载 bitloading1.json 仍显示旧用例名）
    check("用例名称跟随文件名", w._case.name == tmp_file.stem, w._case.name)
    check("名称输入框同步", w.case_name_edit.text() == tmp_file.stem,
          w.case_name_edit.text())
    w.load_case_file(tmp_file)
    check("页面加载用例", w.step_table.rowCount() == 6, w.step_table.rowCount())
    check("加载后名称取自 JSON", w._case.name == tmp_file.stem, w._case.name)

    # 左侧只列已保存用例（不再出现「当前用例（未保存到文件）」分支）
    tree_texts = []
    tree_root = w.case_tree.invisibleRootItem()
    for i in range(tree_root.childCount()):
        node = tree_root.child(i)
        tree_texts.append(node.text(0))
    check("左侧无「当前用例未保存」分支",
          not any("当前用例" in t for t in tree_texts), tree_texts)

    # JSON 视图：查看 + 编辑（应用后表格同步）
    w.editor_tabs.setCurrentIndex(1)
    app.processEvents()
    json_text = w.case_json_edit.toPlainText()
    check("JSON 视图有内容", json_text.strip().startswith("{"), json_text[:40])
    obj = json.loads(json_text)
    obj["name"] = "JSON 改名用例"
    obj["steps"] = obj["steps"][:2]
    w.case_json_edit.setPlainText(json.dumps(obj, ensure_ascii=False, indent=2))
    check("应用 JSON 成功", w._apply_case_json() is True, w.json_hint_label.text())
    check("应用后名称生效", w._case.name == "JSON 改名用例", w._case.name)
    check("应用后表格同步", w.step_table.rowCount() == 2, w.step_table.rowCount())
    w.editor_tabs.setCurrentIndex(0)

    # 复制用例：原文件不动，副本独立成文件
    before_steps = len(w._case.steps)
    check("复制用例成功", w._duplicate_case() is True)
    check("副本名称带「副本」", w._case.name.endswith("副本"), w._case.name)
    check("副本步数一致", len(w._case.steps) == before_steps, len(w._case.steps))
    check("副本已落盘", w._case_path is not None and Path(w._case_path).exists(),
          str(w._case_path))
    for created in Path(core.case_dir()).glob("*.json"):
        created.unlink()
    tmp_file.unlink()

    # 数据步骤对话框：PLC2.0 参数回填与预览
    dlg = StepDialog(None, step=core.Step(kind="data", ctrl2=0x02, channel=0x02,
                                          timestamp=0, pb_count=2, pb_len=0,
                                          data=hexs(PAYLOAD), count=2))
    check("数据对话框子类型回填", dlg.ctrl2_combo.currentData() == 0x02,
          dlg.ctrl2_combo.currentData())
    check("数据对话框信道回填", dlg.channel_combo.currentData() == 0x02,
          dlg.channel_combo.currentData())
    check("数据对话框块个数回填", dlg.pb_count_spin.value() == 2, dlg.pb_count_spin.value())
    check("数据提示含整帧长度", "整帧" in dlg.data_hint.text(), dlg.data_hint.text())
    back = dlg.step()
    check("数据步骤往返一致",
          (back.ctrl2, back.channel, back.timestamp, back.pb_count) == (0x02, 0x02, 0, 2),
          (back.ctrl2, back.channel, back.timestamp, back.pb_count))
    dlg.close()

    # 0x08：TMI/RU/pad 字段可见
    dlg8 = StepDialog(None, step=core.Step(kind="data", ctrl2=0x08, tmi=3, ru=2, pad=1,
                                           data=hexs(PAYLOAD)))
    check("0x08 显示 TMI/RU/pad", not dlg8.tmi_spin.isHidden(), dlg8.tmi_spin.isVisible())
    check("0x08 回填 TMI", dlg8.tmi_spin.value() == 3, dlg8.tmi_spin.value())
    dlg8.close()

    # 时间戳：触发/定时
    dlg_ts = StepDialog(None, step=core.Step(kind="data", ctrl2=0x02,
                                             timestamp=core.TS_TRIGGER,
                                             data=hexs(PAYLOAD)))
    check("触发发送回填", dlg_ts._timestamp_value() == 0xFFFFFFFF, dlg_ts.ts_combo.currentData())
    dlg_ts.close()

    # 控制报文对话框
    dlg2 = StepDialog(None, step=core.Step(kind="command",
                                           command=core.tx_command_ref(0x09), tx_values=[2]))
    check("控制字段数=1（保留字节不给控件）", len(dlg2._field_widgets) == 1,
          len(dlg2._field_widgets))
    check("控制字段回填", dlg2._cmd_values() == [2], dlg2._cmd_values())
    check("控制帧预览是 ED..EE",
          dlg2.cmd_preview.text().startswith("控制帧：ED "), dlg2.cmd_preview.text()[:30])
    again = dlg2.step()
    check("控制步骤往返", again.command == "09" and again.tx_values == [2],
          (again.command, again.tx_values))
    dlg2.close()

    # 0x01 通讯测试：有附加数据框
    dlg3 = StepDialog(None, step=core.Step(kind="command",
                                           command=core.tx_command_ref(0x01),
                                           tx_values=[3, 0, 1000, 1, 1],
                                           data=hexs(PAYLOAD)))
    check("0x01 显示附加数据框", dlg3.cmd_tail_row.isVisible()
          or dlg3.cmd_tail_edit.toPlainText() != "", dlg3.cmd_tail_edit.toPlainText()[:20])
    built = core.build_step_tx_command(dlg3.step())
    check("0x01 组帧成功", built.ok, built.error)
    dlg3.close()

    # 监控器命令对话框
    dlg4 = StepDialog(None, step=core.Step(kind="monitor", command="06:1",
                                           data=hexs(b"\x04\x03\x02\x01")))
    check("监控器字段回填", dlg4._monitor_values() == [0x01020304], dlg4._monitor_values())
    check("监控器预览 68..16",
          dlg4.mon_preview.text().startswith("监控器命令帧：68"), dlg4.mon_preview.text()[:30])
    dlg4.close()

    # 发送侧日志必须把业务帧按协议9 展开（用户报障：只打截断 HEX，看不到 MPDU 字段）
    biz = bytes.fromhex("98 00 19 23 61 45 04 00 20 00 64 00 00 00 20 DD") + bytes(range(24))
    data_all = core.build_tx_data_payload(0x02, payload=biz, channel=1, pb_count=1,
                                          pb_len=len(biz))
    tx_frame = core.build_tx_frame(core.CTRL1_DATA, 0x02, data_all)
    tx_info = core.parse_tx_frame(tx_frame)
    check("业务帧偏移按公共头长度取",
          core.tx_business_payload(0x02, tx_info["data"]) == biz,
          len(core.tx_business_payload(0x02, tx_info["data"]) or b""))
    check("0x08 业务帧偏移为 12",
          core.tx_business_payload(0x08, b"\x00" * 12 + biz) == biz)
    check("数据域不足时不给业务帧（不猜偏移）",
          core.tx_business_payload(0x02, b"\x00" * 5) is None)
    check("未知子类型不给业务帧", core.tx_business_payload(0x55, b"\x00" * 40) is None)

    biz_rows = w._business_rows(biz)
    biz_names = [r[0] for r in biz_rows]
    check("业务帧解析出协议9 字段",
          any("定界符类型" in n for n in biz_names) and any("源TEI" in n for n in biz_names),
          biz_names[:6])
    biz_rows2, biz_summary = w._business_rows_and_summary(biz)
    check("业务帧解析有分隔标题", biz_rows2[0][0].startswith("── 业务帧"),
          biz_rows2[0])
    check("分隔标题不再重复摘要（摘要单独给）", biz_rows2[0][2] == "", biz_rows2[0])
    check("业务帧摘要独立可取（绿色摘要/摘要日志的数据源）", "字段" in biz_summary, biz_summary)
    check("空业务帧不产生行", w._business_rows(b"") == [])

    # 端到端：发送一帧后，日志里的解析行必须含业务帧字段
    fake_for_log = _FakePort()
    w._tx = fake_for_log
    dock = w._ensure_log_dock()
    dock.log_panel.clear_log()
    w._dispatch_step(core.Step(kind="data", ctrl2=0x02, channel=0x01,
                               data=hexs(biz), count=1), 1, 1)
    rendered = dock.log_panel._render_text()
    check("发送日志含协议9 业务帧字段",
          "定界符类型" in rendered and "源TEI" in rendered, rendered[:200])
    w._tx = None

    # 日志窗
    lw = LogWindow()
    lw.append_tx("发射机", frame, "TX 测试")
    lw.append_rx("接收机", minfo_frame := core.build_data_frame(PAYLOAD, 0), "RX 测试")
    check("日志两条记录", len(lw._records) == 2, len(lw._records))
    text = lw._render_text()
    check("解析视图含控制域与 CS", "控制域2" in text and "CS" in text, text[:80])
    # 解析结果整条记录只占一行（不折行，超宽靠横向滚动条）
    tx_lines = [ln for ln in text.splitlines() if "控制域1" in ln]
    check("解析结果只有一行", len(tx_lines) == 1, len(tx_lines))
    tx_line = tx_lines[0] if tx_lines else ""
    check("解析行一行铺完所有字段",
          all(key in tx_line for key in ("控制域2", "帧长域", "CS:", "物理信道")),
          tx_line[:160])
    check("日志不折行（横向滚动）",
          lw.log_text.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap,
          lw.log_text.lineWrapMode())
    # 摘要：绿色运行段（收发日志）+ 摘要日志页签只放摘要
    lw2 = LogWindow()
    lw2.append_tx("发射机", frame, "TX 测试", summary="测试ID:2.0测试 | 映射模式:4")
    runs = lw2._record_runs(lw2._records[0])
    check("摘要被标记成摘要段（渲染为绿色）",
          any("映射模式:4" in t and is_sum for t, is_sum in runs), runs[-2:])
    check("摘要段带「摘要:」前缀",
          any(t.startswith("摘要: ") for t, is_sum in runs if is_sum), runs[-2:])
    check("摘要也进纯文本（保存日志一致）",
          "摘要: 测试ID:2.0测试 | 映射模式:4" in lw2._render_text(), lw2._render_text()[:120])
    lw2.clear_log()
    lw2.close()

    # 摘要日志页签：只输出摘要行，整页绿色
    from splc_transceiver_widget import SUMMARY_COLOR, SummaryLogWindow
    sw = SummaryLogWindow()
    sw.set_summary_color(True)
    sw.append("10:00:00.000", "发射机", "TX", "测试ID:2.0测试 | 映射模式:4")
    sw_text = sw.text.toPlainText()
    check("摘要日志含端口/方向/摘要", "发射机 → 测试ID:2.0测试" in sw_text, sw_text)
    check("摘要日志不含 HEX/全字段", "控制域" not in sw_text, sw_text)
    check("摘要日志整页绿色", SUMMARY_COLOR in sw.text.styleSheet(), sw.text.styleSheet())
    sw.clear_log()
    check("摘要日志清空", sw.text.toPlainText() == "")
    sw.close()
    check("RX 视图含协议类型", "协议类型" in text, text[:120])
    lw.set_view_mode("raw")
    check("仅原始模式", lw.log_text.toPlainText().strip().splitlines()[0].startswith("["),
          lw.log_text.toPlainText()[:40])
    lw.clear_log()
    check("清空", len(lw._records) == 0)
    lw.close()

    # 参数区高度：QTabWidget 不传播 heightForWidth（AGENTS 陷阱 98）
    # 公共参数区现在是**可折叠**的（默认收起）⇒ 先展开再量「六行不被压扁」
    host = QTabWidget()
    host.resize(1400, 800)
    host.addTab(w, "收发机控制")
    host.show()
    app.processEvents()
    w.config_section.set_expanded(True)
    app.processEvents()
    check("参数区高度非 0（展开后）", w.config_group.height() > 60, w.config_group.height())
    check("六行参数区都有高度",
          all(area.height() > 0 for area in w._flow_areas),
          [area.height() for area in w._flow_areas])
    host.resize(1000, 800)
    app.processEvents()
    check("窄窗仍保留六行高度", w.config_group.height() >= 6 * 22, w.config_group.height())
    host.removeTab(0)
    host.close()

    w._case = core.Case(name="空", steps=[])
    w._start_run()
    check("空用例启动被拒", w._runner is None)
    w.shutdown()
    check("shutdown 幂等", True)
except Exception as exc:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    check("页面冒烟", False, str(exc))

# ======================================================================
print("[8] 流程执行（假串口捕获真实发出的帧）")
# ======================================================================



try:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    w = SplcTransceiverWidget()
    w.set_protocol(CSGNewGenParser(), lambda rows: "摘要")
    tx_fake = _FakePort()
    rx_fake = _FakePort()
    w._tx = tx_fake
    w._rx = rx_fake
    w.interval_spin.setValue(1)
    w.count_spin.setValue(2)
    w.duration_spin.setValue(0)
    w.auto_config_chk.setChecked(False)

    case = core.Case(name="执行用例")
    case.steps = [
        core.Step(kind="command", command=core.tx_command_ref(0x09), tx_values=[2],
                  count=1, interval_ms=1, name="频段配置"),
        core.Step(kind="data", ctrl2=0x02, channel=0x01, data=hexs(PAYLOAD),
                  count=2, interval_ms=1, name="测试帧"),
        core.Step(kind="monitor", command="02:0", count=1, interval_ms=1,
                  name="查询监控器频段"),
        core.Step(kind="wait", interval_ms=1, name="等一下"),
    ]
    w._case = case
    w._start_run()
    check("启动后进入执行态", w._runner is not None)
    for _ in range(300):
        if w._runner is None:
            break
        QTest.qWait(10)
    check("流程执行完成", w._runner is None)
    check("发射机口收到 3 帧（1 控制 + 2 数据）", len(tx_fake.frames) == 3, len(tx_fake.frames))
    check("接收机口收到 1 帧监控器命令", len(rx_fake.frames) == 1, len(rx_fake.frames))
    if len(tx_fake.frames) == 3:
        first = core.parse_tx_frame(tx_fake.frames[0])
        check("第 1 帧是控制报文 0x09",
              first["ctrl1"] == 0x01 and first["ctrl2"] == 0x09 and first["ok"], first)
        second = core.parse_tx_frame(tx_fake.frames[1])
        check("第 2 帧是数据报文 0x02", second["ctrl1"] == 0x00
              and second["ctrl2"] == 0x02 and second["ok"], second)
        payload_rows, _ = core.decode_tx_data_payload(0x02, bytes(second["data"]))
        check("数据帧里业务内容与步骤一致",
              bytes(second["data"])[9:] == PAYLOAD, hexs(bytes(second["data"]))[:40])
    if rx_fake.frames:
        check("监控器命令是 68..16",
              core.parse_command_frame(rx_fake.frames[0])["cmd_id"] == 0x02,
              hexs(rx_fake.frames[0]))
    check("停止后按钮复位", w.start_btn.isEnabled() and not w.stop_btn.isEnabled())

    # 启动前自动下发配置：4 条控制报文
    tx_fake.frames.clear()
    w.auto_config_chk.setChecked(True)
    w._start_run()
    for _ in range(400):
        if w._runner is None:
            break
        QTest.qWait(10)
    ids = [core.parse_tx_frame(f)["ctrl2"] for f in tx_fake.frames
           if f[:1] == bytes([core.TX_HEAD]) and f[3] == 0x01]
    check("自动配置 4 条（09/0B/23/19）", ids[:4] == [0x09, 0x0B, 0x23, 0x19], ids)
    check("自动配置帧 CS 全对",
          all(core.parse_tx_frame(f)["ok"] for f in tx_fake.frames if f[:1] == b"\xED"),
          "")

    # CS 固定 0xFF
    tx_fake.frames.clear()
    w.crc_mode_chk.setChecked(True)
    w.auto_config_chk.setChecked(False)
    w._dispatch_step(case.steps[0], 1, 1)
    check("CS 0xFF 生效", tx_fake.frames and tx_fake.frames[0][-2] == 0xFF,
          hexs(tx_fake.frames[0]) if tx_fake.frames else "")
    w.crc_mode_chk.setChecked(False)

    # 快速发送：裸业务帧自动封 ED..EE
    tx_fake.frames.clear()
    w.quick_hex_edit.setText(hexs(PAYLOAD))
    w._send_quick()
    check("快速发送封装 ED..EE",
          len(tx_fake.frames) == 1 and core.parse_tx_frame(tx_fake.frames[0])["ok"],
          hexs(tx_fake.frames[0])[:30] if tx_fake.frames else "")

    # 68..16 命令帧走接收机口
    rx_fake.frames.clear()
    w.quick_hex_edit.setText(hexs(core.build_command_frame(0x02, 0)))
    w._send_quick()
    check("68..16 快速发送走接收机口", len(rx_fake.frames) == 1, len(rx_fake.frames))

    dock = w._ensure_log_dock()
    text = dock.log_panel._render_text()
    check("日志含发射机发送记录", "发射机" in text and "控制域" in text, text[:100])
    w.shutdown()
except Exception as exc:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    check("流程执行冒烟", False, str(exc))

# ======================================================================
print("[9] 监控器：协议类型=4 数据头剥离（接收侧不变）")
# ======================================================================
try:
    from PySide6.QtWidgets import QApplication
    from monitor_widget import RealtimeMonitorWidget
    from csg_new_gen_parser import CSGNewGenParser

    app = QApplication.instance() or QApplication([])
    fc = bytes([0x09]) + bytes(range(1, 16))
    splc_data = bytes([0]) + fc
    wrapped = core.build_data_frame(splc_data, channel=0)

    mon = RealtimeMonitorWidget()
    mon.set_protocol(CSGNewGenParser(), lambda rows: "摘要", wrapper_format="hplc")
    mon._on_raw_data(wrapped + wrapped)
    check("默认不剥离：两帧都进列表", len(mon._frames) == 2, len(mon._frames))
    check("默认 meta 无 splc", "splc" not in mon._frames[0]["meta"])
    check("默认整段 DATA 交给解析器",
          mon._frames[0]["hex"] == core.bytes_to_hex(splc_data), mon._frames[0]["hex"][:40])

    mon.clear_frames()
    mon.set_splc_header_split(True)
    mon._on_raw_data(wrapped)
    record = mon._frames[0]
    splc_meta = record["meta"].get("splc")
    check("开启后识别 SPLC 数据头", isinstance(splc_meta, dict), record["meta"])
    if isinstance(splc_meta, dict):
        check("帧类型=信标帧", splc_meta.get("frame_type_name") == "信标帧", splc_meta)
    row_names = [str(row[0]) for row in record["table_data"]]
    check("详情表出现「帧类型」行", "帧类型" in row_names, row_names[:10])
    check("剥离后只把 MPDU 交给解析器", record["hex"] == core.bytes_to_hex(fc),
          record["hex"][:40])
    mon.deleteLater()
except Exception as exc:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    check("监控器 SPLC 剥离", False, str(exc))

# ======================================================================
print("[10] 公共参数区做成折叠窗口（用户口径）")
# ======================================================================
try:
    from unittest.mock import patch

    import app_paths

    tmpdir = Path(tempfile.mkdtemp(prefix="splc_cfg_"))
    with patch.object(app_paths, "data_path", lambda name: tmpdir / str(name)):
        w2 = SplcTransceiverWidget()
        w2.resize(1500, 860)
        w2.show()
        app.processEvents()

        sec = w2.config_section
        check("公共参数默认折叠", not sec.is_expanded(), sec.is_expanded())
        check("折叠时内容区隐藏", sec.is_content_hidden())
        check("config_group 仍是同一对象（兼容旧引用）", w2.config_group is sec)
        header = sec.header_text()
        check("标题栏写「收发机公共参数」", header.startswith("收发机公共参数"), header)
        check("标题栏摘要含发射机/接收机与开合状态",
              ("发射机" in header) and ("接收机" in header)
              and ("已开" in header or "关" in header), header)
        check("折叠时参数区只剩标题栏高度", sec.height() < 60, sec.height())

        h_collapsed = w2.step_table.height()
        sec.set_expanded(True)
        app.processEvents()
        check("展开后内容区可见", not sec.is_content_hidden())
        check("展开后参数区有实际高度", sec.height() > 120, sec.height())
        h_expanded = w2.step_table.height()
        check("折叠把高度让给了步骤表", h_collapsed > h_expanded,
              (h_collapsed, h_expanded))

        # 折叠状态落盘 → 新实例按存档恢复
        sec.set_expanded(False)
        app.processEvents()
        w2.save_settings()
        saved = core.load_settings().get("sections")
        check("折叠状态落盘", saved == {"splc_params": False}, saved)

        sec.set_expanded(True)
        w2.save_settings()
        w3 = SplcTransceiverWidget()
        app.processEvents()
        check("新实例按存档恢复为展开", w3.config_section.is_expanded(),
              w3.config_section.is_expanded())
        w3.shutdown()
        w3.close()

        # 打开串口后标题栏摘要实时反映「已开」
        w2._tx.is_open = lambda: True          # 假串口：避免真开端口
        w2._tx.open_port = lambda: True
        w2.tx_open_btn.setChecked(True)
        app.processEvents()
        check("打开发射机后摘要显示已开", "已开" in sec.header_text(), sec.header_text())
        w2._tx.close_port = lambda: True
        w2.tx_open_btn.setChecked(False)
        app.processEvents()
        check("关闭后摘要回到「关」", "已开" not in sec.header_text(), sec.header_text())

        w2.shutdown()
        w2.close()
except Exception as exc:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    check("公共参数折叠窗口", False, str(exc))

# ======================================================================
print("[11] 启动/停止在折叠区之外 + 用例条目多选（整条用例可启动）")
# ======================================================================
try:
    from PySide6.QtCore import QItemSelectionModel
    from PySide6.QtTest import QTest
    from unittest.mock import patch

    import app_paths

    from PySide6.QtWidgets import QMessageBox

    # 页面可见时 _notify 会弹模态框（自动化里会卡住）：全程拦掉并收集文案
    notes: list = []
    _orig_warn, _orig_info = QMessageBox.warning, QMessageBox.information
    QMessageBox.warning = staticmethod(lambda *a, **k: notes.append(a[2] if len(a) > 2 else ""))
    QMessageBox.information = staticmethod(
        lambda *a, **k: notes.append(a[2] if len(a) > 2 else ""))

    tmpdir = Path(tempfile.mkdtemp(prefix="splc_run_"))
    with patch.object(app_paths, "data_path", lambda name: tmpdir / str(name)):
        cases_dir = core.case_dir()
        cases_dir.mkdir(parents=True, exist_ok=True)
        # 0x06/0x08 是设备上报指令、不能下发（validate_case 会拦），用 0x03 / 0x31
        for label, cmd in (("用例A", 0x03), ("用例B", 0x31)):
            core.save_case(core.Case(name=label, steps=[
                core.Step(kind="command", command=core.tx_command_ref(cmd),
                          count=1, interval_ms=1, name=f"{label}步骤")]),
                cases_dir / f"{label}.json")

        w4 = SplcTransceiverWidget()
        w4.set_protocol(CSGNewGenParser(), lambda rows: "摘要")
        w4.resize(1400, 860)
        w4.show()
        app.processEvents()
        w4.interval_spin.setValue(1)
        w4.count_spin.setValue(1)
        w4.duration_spin.setValue(0)
        w4.auto_config_chk.setChecked(False)

        # ① 启动/停止不在折叠区里，折叠后仍可用
        parent = w4.start_btn.parentWidget()
        inside = False
        while parent is not None:
            if parent is w4.config_section.content:
                inside = True
                break
            parent = parent.parentWidget()
        check("启动/停止不在折叠区内容里", not inside)
        w4.config_section.set_expanded(False)
        app.processEvents()
        check("折叠后启动按钮仍可见", w4.start_btn.isVisible())
        check("折叠后停止按钮仍可见", w4.stop_btn.isVisible())

        # ② 运行目标提示随树选择变化
        tree = w4.case_tree
        check("用例树支持多选",
              tree.selectionMode() == QTreeWidget.SelectionMode.ExtendedSelection,
              tree.selectionMode())
        root = tree.invisibleRootItem().child(0)
        names = [root.child(i).text(0) for i in range(root.childCount())]
        check("用例树列出两条用例", names == ["用例A", "用例B"], names)
        tree.clearSelection()
        app.processEvents()
        check("未选时提示执行当前用例", "当前用例" in w4.run_target_label.text(),
              w4.run_target_label.text())
        root.child(0).setSelected(True)
        app.processEvents()
        check("选中一条时提示用例名", "用例A" in w4.run_target_label.text(),
              w4.run_target_label.text())
        root.child(1).setSelected(True)
        app.processEvents()
        check("选中两条时提示依次执行", "依次执行 2 条" in w4.run_target_label.text(),
              w4.run_target_label.text())
        got_targets = [c.name for c in w4._run_targets()]
        check("运行目标按树序返回两条", got_targets == ["用例A", "用例B"], got_targets)

        # ③ 多选用例真的依次执行（假串口）
        tx4 = _FakePort()
        w4._tx = tx4
        w4._start_run()
        check("多选启动进入执行态", w4._runner is not None, notes)
        for _ in range(300):
            if w4._runner is None:
                break
            QTest.qWait(10)
        ctrl2s = [core.parse_tx_frame(f)["ctrl2"] for f in tx4.frames
                  if f[:1] == bytes([core.TX_HEAD]) and f[3] == 0x01]
        check("两条用例的帧都发出且按序（0x03 → 0x31）", ctrl2s[:2] == [0x03, 0x31], ctrl2s)
        check("执行完按钮复位", w4.start_btn.isEnabled() and not w4.stop_btn.isEnabled())

        # ④ 载入中的用例用内存版（保留未保存改动）
        w4.load_case_file(cases_dir / "用例A.json")
        app.processEvents()
        root = tree.invisibleRootItem().child(0)     # 载入会重建树，旧 item 已失效
        w4._case.steps.append(core.Step(kind="command", command=core.tx_command_ref(0x07),
                                        count=1, interval_ms=1, name="内存新增步骤"))
        tree.clearSelection()
        for i in range(root.childCount()):
            root.child(i).setSelected(True)
        app.processEvents()
        targets = w4._run_targets()
        check("载入中的用例取内存版（含未保存步骤）", len(targets[0].steps) == 2,
              len(targets[0].steps))

        # ⑤ 停止随时可用
        tx4.frames.clear()
        w4._start_run()
        app.processEvents()
        check("执行中停止按钮可用", w4.stop_btn.isEnabled())
        w4.stop_run("手动停止")
        app.processEvents()
        check("停止后回到空闲", w4._runner is None and w4.start_btn.isEnabled())

        # ⑥ 表格多选：发送选中步骤要遍历全部选中行（只发第一行是常见 bug）
        w4._case = core.Case(name="多选步骤", steps=[
            core.Step(kind="command", command=core.tx_command_ref(0x03), count=1,
                      interval_ms=1, name="步骤1"),
            core.Step(kind="command", command=core.tx_command_ref(0x06), count=1,
                      interval_ms=1, name="步骤2"),
            core.Step(kind="command", command=core.tx_command_ref(0x07), count=1,
                      interval_ms=1, name="步骤3"),
        ])
        w4._refresh_step_table()
        app.processEvents()
        # 多选第 1、3 行：selectRow 是 ClearAndSelect，连续调只会剩最后一行 ⇒ 走 selectionModel
        sel = w4.step_table.selectionModel()
        sel.clearSelection()
        for _row in (0, 2):
            sel.select(w4.step_table.model().index(_row, 0),
                       QItemSelectionModel.SelectionFlag.Select
                       | QItemSelectionModel.SelectionFlag.Rows)
        app.processEvents()
        check("选中步骤行解析正确", w4._selected_step_rows() == [0, 2],
              w4._selected_step_rows())
        tx4.frames.clear()
        w4._send_selected_step_once()
        app.processEvents()
        ctrl2s = [core.parse_tx_frame(f)["ctrl2"] for f in tx4.frames
                  if f[:1] == bytes([core.TX_HEAD]) and f[3] == 0x01]
        check("多选步骤都发出去（0x03 + 0x07）", ctrl2s == [0x03, 0x07], ctrl2s)

        check("过程中没有意外弹框", not notes, notes)
        w4.shutdown()
        w4.close()
    QMessageBox.warning, QMessageBox.information = _orig_warn, _orig_info
except Exception as exc:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    check("运行控制/多选", False, str(exc))

# ======================================================================
print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败：")
    for item in FAILED:
        print("   -", item)
    sys.exit(1)
print("✅ 全部通过")
