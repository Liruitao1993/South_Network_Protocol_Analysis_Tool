# -*- coding: utf-8 -*-
"""协议8 升级页「升级对象=模块」：模块版本读取命令 + 645 应答解析回归。

用户需求（2026-11-11）：协议8 光伏升级页增加「升级对象」选择；勾「模块」时
读升级前/升级后版本**改用模块的版本信息读取命令**，应答要把版本号解出来，
解析**复用 645 协议已实现的解析器**（不另写一份）。

模块版本读取命令（用户提供的现场实帧，**原样下发**）::

    68 AA AA AA AA AA AA 68 11 3A | DI=FF00DD01 + 条目信息(1B=0) + M(1B=26) + 26×2B 请求头 | A6 16

要点（判据都钉在这里）：
  [1] 常量与用户报文**逐字节一致**；CS 按 645 口径自证（**含起始符 68H**）
  [2] build_module_version_frame：换地址重算 CS（同址重建 === 原帧）
  [3] parse_module_version_response：真实应答 → 版本号解出来（复用 LME 条目解析）
  [4] 反例：非 645 / 末字节非 16H / L 不符 / CS 错 / 控制码非应答 / DI 不符 / 空应答
  [5] 分帧策略按「对象 × 阶段」切换：模块 + 读版本阶段 → dlt645，
      模块 + 文件传输阶段 → dlt698_45（否则 698 应答会被切坏 ⇒ 整轮超时）
  [6] GUI 接线：下拉存在、模块下 OAD 下拉禁用并给提示、持久化往返
  [7] 发送：模块 + 读版本阶段发出的就是那条 645 命令帧
  [8] 应答：喂一条 645 版本应答 → 版本信息被记录、日志给明细、流程推进

运行：``python test/test_dl698_upgrade_module_version.py``（offscreen）
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
import sys  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

# 构造页面之前屏蔽模态框（offscreen 下弹框会永久阻塞）
for _name in ("warning", "information", "critical"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()
patch.object(QMessageBox, "question",
             lambda *a, **k: QMessageBox.StandardButton.Yes).start()

SANDBOX = _config_sandbox.install()

import dlt698_upgrade_widget as ui  # noqa: E402
import frame_deframe  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f"  -- {detail}" if detail else ""))


#: 用户给的实帧（去掉空格）
USER_FRAME_HEX = (
    "68AAAAAAAAAAAA68113A34103332334D343335333633373338333933743375337633773378"
    "3379337A337B337C337D337E337F33803381338733883389338A338B339133" "A616"
)


def make_645_response(values, di_hex="01DD00FF", ctrl=0x91):
    """构造一条 645 读数据应答帧（DI + 条目信息 + M + TLV 条目）。

    ``values``：``[(分类, 数据ID, 编码, 值字节)]``。
    """
    entries = b""
    for cat, did, enc, val in values:
        length = len(val)
        header = ((did & 0x3F) | ((cat & 0x07) << 6)
                  | ((enc & 0x03) << 9) | ((length & 0x1F) << 11))
        entries += header.to_bytes(2, "little") + val
    payload = bytes.fromhex(di_hex) + bytes([0x00, len(values)]) + entries
    data = bytes((b + 0x33) & 0xFF for b in payload)
    body = bytes.fromhex("AAAAAAAAAAAA") + bytes([0x68, ctrl, len(data)]) + data
    return bytes([0x68]) + body + bytes([(0x68 + sum(body)) & 0xFF, 0x16])


DI_FF00DD01 = "01DD00FF"       # FF00DD01 的线序（小端）

# ======================================================================
print("[1] 模块版本命令常量与用户报文逐字节一致 + CS 自证")
# ======================================================================
check("常量 == 用户报文",
      ui.MODULE_VERSION_COMMAND.hex().upper() == USER_FRAME_HEX,
      f"{ui.MODULE_VERSION_COMMAND.hex().upper()} != {USER_FRAME_HEX}")
check("DI 常量是 FF00DD01", ui.MODULE_VERSION_DI == "FF00DD01", ui.MODULE_VERSION_DI)

frame = ui.MODULE_VERSION_COMMAND
check("起始符/地址/第二个起始符", frame[0] == 0x68 and frame[7] == 0x68)
check("控制码 11H（读数据请求）+ L=3AH",
      frame[8] == 0x11 and frame[9] == 0x3A, f"{frame[8]:02X}/{frame[9]:02X}")
check("整帧长度 = L + 12", len(frame) == frame[9] + 12, f"{len(frame)}")
check("数据域减 33H 后 DI = FF00DD01",
      bytes((b - 0x33) & 0xFF for b in frame[10:14])[::-1].hex().upper() == "FF00DD01",
      frame[10:14].hex())
check("条目信息=0、M=26",
      (frame[14] - 0x33) == 0 and (frame[15] - 0x33) == 26,
      f"{frame[14] - 0x33}/{frame[15] - 0x33}")
# CS 必须**含起始符 68H**（不含时算得 3EH，含起始符才是帧内的 A6H）
check("CS 自证（含起始符口径）",
      sum(frame[:-2]) & 0xFF == frame[-2] == 0xA6,
      f"{sum(frame[:-2]) & 0xFF:02X} / {frame[-2]:02X}")
check("CS 是「含起始符」才成立的：不含时对不上",
      sum(frame[1:-2]) & 0xFF != frame[-2])
check("与 645 解析器 calc_checksum 同口径",
      __import__("dlt645_parser").DLT645Parser.calc_checksum(frame) == frame[-2])

# ======================================================================
print("[2] build_module_version_frame：换地址重算 CS")
# ======================================================================
check("同址重建 === 原帧",
      ui.build_module_version_frame(bytes.fromhex("AAAAAAAAAAAA")) == frame)
alt = ui.build_module_version_frame(bytes.fromhex("075506980033"))
check("换址后地址域正确", alt[1:7] == bytes.fromhex("075506980033"), alt[1:7].hex())
check("换址后 CS 按新地址重算且自证",
      alt[-2] == (sum(alt[:-2]) & 0xFF) and alt[-2] != frame[-2],
      f"{alt[-2]:02X} vs {frame[-2]:02X}")
check("换址后数据域不变（仍是 DI+条目）", alt[10:-2] == frame[10:-2])
check("换址后仍是 16H 收尾、长度不变",
      alt[-1] == 0x16 and len(alt) == len(frame))
check("地址不足 6 字节时补零不抛",
      len(ui.build_module_version_frame(b"\x01\x02")) == len(frame))

# ======================================================================
print("[3] parse_module_version_response：真实应答 → 版本号解出来（复用 LME 解析器）")
# ======================================================================
resp = make_645_response([
    (1, 3, 0, bytes([0x21, 0x03])),                        # 总工程版本 bin_ver
    (1, 1, 2, b"2026-11-11 10:00:00"),                     # 编译时间
], di_hex=DI_FF00DD01)
r = ui.parse_module_version_response(resp)
check("应答解析成功", r["ok"], r["reason"])
names = [row["名称"] for row in r["rows"]]
values = {row["名称"]: row["值"] for row in r["rows"]}
ver_name = [n for n in names if "总工程版本" in n]
check("解出「总工程版本」条目", bool(ver_name), names)
check("版本号解出（21 03 → V0321）",
      ver_name and values[ver_name[0]] == "V0321", values.get(ver_name[0] if ver_name else ""))
check("解出「编译时间」条目（ASCII 原样）",
      any("编译时间" in n for n in names), names)
check("行格式与 698 侧一致（名称/值/原始）",
      all(set(row) == {"名称", "值", "原始"} for row in r["rows"]),
      r["rows"][:1])
check("note 给出接口名（LME 4.6 应答）", "LME" in r["version"], r["version"])
check("rows 不含标题分隔行",
      all(not row["名称"].startswith("──") for row in r["rows"]))

# 前导 FEH 容忍
check("带 FEH 前导也能解",
      ui.parse_module_version_response(b"\xfe\xfe" + resp)["ok"])

# ======================================================================
print("[4] 反例：非 645 / 形状不符 / 校验错 / 控制码不是应答 / DI 不符 / 空应答")
# ======================================================================
r = ui.parse_module_version_response(bytes.fromhex("681D004305AAAAAAAAAAAAA0"))
check("非 645 结构（第 8 字节非 68H）被拒", not r["ok"] and "645" in r["reason"], r["reason"])

r = ui.parse_module_version_response(resp[:-1] + b"\x99")
check("末字节非 16H 被拒", not r["ok"] and "16H" in r["reason"], r["reason"])

bad_len = bytearray(resp)
bad_len[9] = (bad_len[9] + 1) & 0xFF
r = ui.parse_module_version_response(bytes(bad_len))
check("长度域与帧长不符被拒", not r["ok"] and "长度" in r["reason"], r["reason"])

bad_cs = bytearray(resp)
bad_cs[-2] = (bad_cs[-2] + 1) & 0xFF
r = ui.parse_module_version_response(bytes(bad_cs))
check("CS 错被拒（给帧内值与正确值）",
      not r["ok"] and "校验和" in r["reason"] and "0x" in r["reason"], r["reason"])

req_dir = make_645_response([(1, 3, 0, b"\x21\x03")], di_hex=DI_FF00DD01, ctrl=0x11)
r = ui.parse_module_version_response(req_dir)
check("控制码 D7=0（请求帧）被拒", not r["ok"] and "应答" in r["reason"], r["reason"])

other_func = make_645_response([(1, 3, 0, b"\x21\x03")], di_hex=DI_FF00DD01, ctrl=0x94)
r = ui.parse_module_version_response(other_func)
check("功能码不是 11H（如 14H 设置应答）被拒",
      not r["ok"] and "11H" in r["reason"], r["reason"])

wrong_di = make_645_response([(1, 3, 0, b"\x21\x03")], di_hex="010000FF")
r = ui.parse_module_version_response(wrong_di)
check("DI 不符（FF00DD01 之外）被拒",
      not r["ok"] and "DI" in r["reason"], r["reason"])

empty = make_645_response([], di_hex=DI_FF00DD01)
r = ui.parse_module_version_response(empty)
check("M=0 空应答被拒（不臆造版本号）",
      not r["ok"] and "条目" in r["reason"], r["reason"])

check("空 bytes 不抛、给原因", not ui.parse_module_version_response(b"")["ok"])

# ======================================================================
print("[5] 分帧策略按「对象 × 阶段」切换（模块的文件传输仍走 698）")
# ======================================================================
app = QApplication.instance() or QApplication(sys.argv)


def new_page():
    page = ui.Dlt698UpgradeWidget()
    page.restyle_for_theme(False)
    return page


page = new_page()
check("默认升级对象 = 光伏设备",
      page._upgrade_target_key() == "pv", page._upgrade_target_key())
check("光伏设备 + 读版本阶段 → dlt698_45",
      page._deframe_strategy() == "dlt698_45", page._deframe_strategy())

page.combo_upgrade_target.setCurrentIndex(
    [k for _l, k, _s in ui.UPGRADE_TARGETS].index("module"))
check("切到模块后键值正确", page._is_module_target())

page._phase = ui.PHASE_VER_PRE
check("模块 + 升级前读版本 → dlt645",
      page._deframe_strategy() == "dlt645", page._deframe_strategy())
page._phase = ui.PHASE_VER_POST
check("模块 + 升级完成后读版本 → dlt645",
      page._deframe_strategy() == "dlt645", page._deframe_strategy())
for ph in (ui.PHASE_START, ui.PHASE_BLOCKS, ui.PHASE_STATUS, ui.PHASE_EXEC):
    page._phase = ph
    check(f"模块 + 文件传输阶段({ph}) → 仍 dlt698_45（否则 698 应答被切坏）",
          page._deframe_strategy() == "dlt698_45", page._deframe_strategy())

# 分帧实测：645 应答在模块读版本阶段能切出整帧；698 帧在该阶段切不出（反证策略真的生效）
page._phase = ui.PHASE_VER_PRE
check("645 应答在 dlt645 策略下切出整帧",
      page._complete_frame_len(resp) == len(resp),
      f"{page._complete_frame_len(resp)} vs {len(resp)}")
check("同一帧按 698 口径切不出来（反证：策略切换是必需的）",
      frame_deframe.frame_length_for("dlt698_45", resp) == 0,
      frame_deframe.frame_length_for("dlt698_45", resp))

# ======================================================================
print("[6] GUI：模块下 OAD 下拉禁用 + 提示；持久化往返")
# ======================================================================
check("模块下「读版本内容」(OAD) 下拉禁用", not page.combo_read_target.isEnabled())
check("模块下提示写明 645 FF00DD01",
      "FF00DD01" in page.lbl_target_hint.text(), page.lbl_target_hint.text())
page.combo_upgrade_target.setCurrentIndex(0)
check("切回光伏设备后 OAD 下拉恢复可用", page.combo_read_target.isEnabled())
check("光伏设备提示写 698 OAD",
      "698" in page.lbl_target_hint.text(), page.lbl_target_hint.text())

settings = page._collect_settings()
check("落盘含 upgrade_target", settings.get("upgrade_target") == "pv", settings.get("upgrade_target"))
page.combo_upgrade_target.setCurrentIndex(1)
page._save_persisted()                     # 去抖定时器不会在无事件循环时触发 ⇒ 直接落盘
page.combo_upgrade_target.setCurrentIndex(0)   # 先改回光伏，验证读回的是盘里的「模块」
page._load_persisted()
check("模块选择能落盘并读回", page._upgrade_target_key() == "module",
      page._upgrade_target_key())
check("读回后 OAD 下拉仍禁用（联动一并恢复）", not page.combo_read_target.isEnabled())

# 冻结：传输中不许改对象
page._freeze_plan_inputs(True)
check("冻结时升级对象下拉禁用", not page.combo_upgrade_target.isEnabled())
check("冻结时模块下 OAD 下拉仍禁用", not page.combo_read_target.isEnabled())
page._freeze_plan_inputs(False)
check("解冻后升级对象下拉可用", page.combo_upgrade_target.isEnabled())

# ======================================================================
print("[7] 发送：模块 + 读版本阶段发出的就是那条 645 命令帧")
# ======================================================================


class FakeWorker(QObject):
    """最小 write_raw 桩：只记字节、不自动回帧（回帧由测试显式调 `page._on_frame`）。"""

    raw_data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

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

    def set_baudrate(self, *_a, **_k):
        return True


worker = FakeWorker()
page2 = new_page()
page2.set_serial_worker(worker)
page2.combo_upgrade_target.setCurrentIndex(1)
page2._state = ui.STATE_STARTING
page2._phase = ui.PHASE_VER_PRE
page2._send_current_step()
check("发出 1 帧", len(worker.sent) == 1, worker.sent)
check("发的是模块版本命令（与用户报文逐字节一致）",
      worker.sent and worker.sent[0] == ui.MODULE_VERSION_COMMAND,
      worker.sent[0].hex().upper() if worker.sent else "")

# 光伏设备下读版本阶段发的必须是 698 帧（反证没有把两条路径搞混）
worker2 = FakeWorker()
page3 = new_page()
page3.combo_upgrade_target.setCurrentIndex(0)   # 显式切回光伏（盘里可能存着模块）
page3.set_serial_worker(worker2)
page3._state = ui.STATE_STARTING
page3._phase = ui.PHASE_VER_PRE
page3._send_current_step()
check("光伏设备读版本发的是 698 帧（68 … 16，非 645 形状）",
      worker2.sent and worker2.sent[0][0] == 0x68 and worker2.sent[0][7] != 0x68,
      worker2.sent[0].hex().upper()[:40] if worker2.sent else "")
check("两条路径发出的帧不同（没有误用同一帧）",
      worker2.sent and worker.sent and worker2.sent[0] != worker.sent[0])

# ======================================================================
print("[8] 应答：喂 645 版本应答 → 记录版本、日志给明细、流程推进")
# ======================================================================
page4 = new_page()
page4.set_serial_worker(FakeWorker())
page4.combo_upgrade_target.setCurrentIndex(1)
page4._state = ui.STATE_STARTING
page4._phase = ui.PHASE_VER_PRE
page4._on_frame(resp)
info = page4._ver_info["pre"]
check("升级前版本被记录", info is not None and info["rows"], info)
check("记录的 target 是「模块」", info and info["target"] == "模块", info and info["target"])
check("记录的字段里能翻到版本号",
      any("V0321" in str(row.get("值")) for row in (info["rows"] if info else [])),
      [row.get("值") for row in (info["rows"] if info else [])])
log = page4.log_text.toPlainText()
check("日志有 [RX] 帧行", "[RX]" in log, log[-200:])
check("日志给出逐条明细（含总工程版本）", "总工程版本" in log, log[-300:])
check("展示区（升级前栏）有内容", "总工程版本" in page4.txt_version_pre.toPlainText(),
      page4.txt_version_pre.toPlainText()[:120])

# 非本步回帧（DI 不符）⇒ 忽略、不记版本
page4._reset_version_info()
page4._phase = ui.PHASE_VER_PRE
page4._on_frame(wrong_di)
check("DI 不符的回帧被忽略（版本仍为空）",
      page4._ver_info["pre"] is None, page4._ver_info["pre"])

# 前后一致 ⇒ 判「升级失败」；版本变了 ⇒ 判「升级成功」（复用既有比对机制）
page5 = new_page()
page5.combo_upgrade_target.setCurrentIndex(1)
resp_changed = make_645_response([
    (1, 3, 0, bytes([0x22, 0x03])),
    (1, 1, 2, b"2026-11-12 10:00:00"),
], di_hex=DI_FF00DD01)
page5._record_version_info(ui.PHASE_VER_PRE, ui.parse_module_version_response(resp))
page5._record_version_info(ui.PHASE_VER_POST, ui.parse_module_version_response(resp_changed))
check("模块：版本变了 ⇒ 判定升级成功",
      page5._ver_verdict["level"] == ui.VERDICT_CHANGED, page5._ver_verdict)
page5._record_version_info(ui.PHASE_VER_POST, ui.parse_module_version_response(resp))
check("模块：前后一致 ⇒ 判定升级失败",
      page5._ver_verdict["level"] == ui.VERDICT_SAME, page5._ver_verdict)

# ======================================================================
print("[9] 模块对象：块传完**跳过**「查询传输块状态字」位图（点对点发包，设备不回复位图）")
# ======================================================================
# 模块 + 勾「传完后自动执行升级」⇒ 直接进执行升级，全程**不发**状态字帧
w6 = FakeWorker()
page6 = new_page()
page6.combo_upgrade_target.setCurrentIndex(1)
page6.set_serial_worker(w6)
page6.chk_auto_exec.setChecked(True)
page6._state = ui.STATE_TRANSFERRING
page6._phase = ui.PHASE_BLOCKS
page6._begin_status_gate()
check("模块：跳过位图后不处于 PHASE_STATUS",
      page6._phase != ui.PHASE_STATUS, page6._phase)
check("模块：直接进入执行升级阶段", page6._phase == ui.PHASE_EXEC, page6._phase)
check("模块：发出的是「执行升级」帧（1 帧，不是状态字帧）",
      len(w6.sent) == 1, [f.hex().upper()[:24] for f in w6.sent])
check("模块：日志写明跳过位图",
      "跳过「查询传输块状态字」" in page6.log_text.toPlainText(),
      page6.log_text.toPlainText()[-160:])

# 模块 + 不勾自动执行 ⇒ 跳过位图后直接收尾（不发任何帧）
w7 = FakeWorker()
page7 = new_page()
page7.combo_upgrade_target.setCurrentIndex(1)
page7.set_serial_worker(w7)
page7.chk_auto_exec.setChecked(False)
page7._state = ui.STATE_TRANSFERRING
page7._phase = ui.PHASE_BLOCKS
page7._begin_status_gate()
check("模块 + 不自动执行：跳过位图后直接收尾（无状态字帧、无执行帧）",
      not w7.sent and page7._state == ui.STATE_DONE,
      (len(w7.sent), page7._state))

# 反证：光伏设备仍必须走位图闸门（发状态字读取帧、停在 PHASE_STATUS）
w8 = FakeWorker()
page8 = new_page()
page8.combo_upgrade_target.setCurrentIndex(0)
page8.set_serial_worker(w8)
page8.chk_auto_exec.setChecked(True)
page8._state = ui.STATE_TRANSFERRING
page8._phase = ui.PHASE_BLOCKS
page8._begin_status_gate()
check("光伏设备：仍进入 PHASE_STATUS（位图闸门保留）",
      page8._phase == ui.PHASE_STATUS, page8._phase)
check("光伏设备：确实发出了状态字读取帧", len(w8.sent) == 1, len(w8.sent))
check("两条路径帧不同（模块没发状态字读取）",
      w8.sent and w6.sent and w8.sent[0] != w6.sent[0])

# 位图校验通过的既有路径仍然可用（模块跳过与位图通过共用同一份后续逻辑）
w9 = FakeWorker()
page9 = new_page()
page9.combo_upgrade_target.setCurrentIndex(0)
page9.set_serial_worker(w9)
page9.chk_auto_exec.setChecked(True)
page9._state = ui.STATE_FINISHING
page9._phase = ui.PHASE_STATUS
page9._on_ack()
check("位图通过后进入执行升级（复用同一份后续逻辑）",
      page9._phase == ui.PHASE_EXEC and len(w9.sent) == 1,
      (page9._phase, len(w9.sent)))

# ======================================================================
print("[10] 发包间隔(ms)：文件传输阶段每包之间可等待，0 = 立刻发（旧行为）")
# ======================================================================
import time  # noqa: E402


def wait_ms(ms: int) -> None:
    """真实跑事件循环 ms 毫秒（QTimer 才会 tick；offscreen 下也能用）。"""
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)
        if time.monotonic() >= end:
            break
    app.processEvents()


def prep_blocks(page, worker, data=b"0123456789abcdefghij", block=8):
    """把页面摆到「文件传输中、第 1 包刚确认」的位置，返回总包数。"""
    import dl_t698_45_upgrade as upg_mod
    page.set_serial_worker(worker)
    page._data = data
    page._blocks = upg_mod.split_blocks(data, block)
    page._plan = upg_mod.UpgradePlan.for_data(data, block)
    page._block_idx = 0
    page._confirmed_bytes = 0
    page._state = ui.STATE_TRANSFERRING
    page._phase = ui.PHASE_BLOCKS
    return page._num_blocks()


check("默认发包间隔为 0（与旧行为一致）",
      ui.DEFAULTS["pkt_gap_ms"] == 0 and page.spin_pkt_gap.value() == 0,
      page.spin_pkt_gap.value())

# ① 间隔 0 ⇒ 确认后立刻发下一包（同步，不等事件循环）
w10 = FakeWorker()
p10 = new_page()
p10.combo_upgrade_target.setCurrentIndex(0)
n_blocks = prep_blocks(p10, w10)
check("分包为 3 包（10+10+2）", n_blocks == 3, n_blocks)
p10._send_current_step()          # 发第 1 包
base = len(w10.sent)
check("第 1 包已发出", base == 1, base)
p10._on_ack()                     # 第 1 包确认
check("间隔 0：下一包**立刻**发出", len(w10.sent) == base + 1, len(w10.sent))
check("间隔 0：不启动间隔定时器", not p10._pkt_gap_timer.isActive())
check("间隔 0：块号已推进到第 2 包", p10._block_idx == 1, p10._block_idx)

# ② 间隔 300ms ⇒ 确认后先等，定时器到点才发
w11 = FakeWorker()
p11 = new_page()
p11.combo_upgrade_target.setCurrentIndex(0)
prep_blocks(p11, w11)
p11.spin_pkt_gap.setValue(300)
p11._send_current_step()
before = len(w11.sent)
p11._on_ack()
check("有间隔：确认后**不立刻**发下一包", len(w11.sent) == before, len(w11.sent))
check("有间隔：间隔定时器已启动", p11._pkt_gap_timer.isActive())
check("有间隔：块号已先推进（进度显示在飞的那包）", p11._block_idx == 1, p11._block_idx)
check("有间隔：日志写明等待写盘",
      "发包间隔" in p11.log_text.toPlainText(), p11.log_text.toPlainText()[-150:])

# 间隔期间到达的帧必须**不当确认**（设备重发上一条确认不能把没发的包记成已确认）
confirmed_before = p11._confirmed_bytes
p11._on_frame(make_645_response([(1, 3, 0, bytes([0x21, 0x03]))], di_hex=DI_FF00DD01))
check("间隔期间收到帧：不当确认（已确认字节未变）",
      p11._confirmed_bytes == confirmed_before, p11._confirmed_bytes)
check("间隔期间收到帧：日志说明被忽略",
      "发包间隔等待中" in p11.log_text.toPlainText(),
      p11.log_text.toPlainText()[-200:])

wait_ms(420)                      # 等过 300ms 间隔
check("间隔到点后自动发出下一包", len(w11.sent) == before + 1, len(w11.sent))
check("间隔到点后定时器已停", not p11._pkt_gap_timer.isActive())

# ③ 末包确认后**不**走间隔（直接进位图闸门/收尾）
w12 = FakeWorker()
p12 = new_page()
p12.combo_upgrade_target.setCurrentIndex(0)
prep_blocks(p12, w12)
p12.spin_pkt_gap.setValue(300)
p12._block_idx = p12._num_blocks() - 1        # 摆在最后一包
p12._confirmed_bytes = 999
p12._on_ack()
check("末包确认后不进间隔等待（直接推进到下一步）",
      not p12._pkt_gap_timer.isActive() and p12._phase != ui.PHASE_BLOCKS,
      (p12._pkt_gap_timer.isActive(), p12._phase))

# ④ 中止/清除会取消间隔等待，之后不再冒出帧
w13 = FakeWorker()
p13 = new_page()
p13.combo_upgrade_target.setCurrentIndex(0)
prep_blocks(p13, w13)
p13.spin_pkt_gap.setValue(400)
p13._send_current_step()
n13 = len(w13.sent)
p13._on_ack()
check("中止前：定时器在等", p13._pkt_gap_timer.isActive())
p13._on_clear()                    # 清除 = 停掉本轮
check("清除后：间隔定时器已停", not p13._pkt_gap_timer.isActive())
wait_ms(520)
check("清除后：等待期间不会冒出任何帧", len(w13.sent) == n13, len(w13.sent))

# ⑤ 持久化 + 冻结
p14 = new_page()
p14.spin_pkt_gap.setValue(250)
p14._save_persisted()
p14.spin_pkt_gap.setValue(0)
p14._load_persisted()
check("发包间隔能落盘并读回", p14.spin_pkt_gap.value() == 250, p14.spin_pkt_gap.value())
check("落盘字段名是 pkt_gap_ms",
      p14._collect_settings().get("pkt_gap_ms") == 250,
      p14._collect_settings().get("pkt_gap_ms"))
p14._freeze_plan_inputs(True)
check("冻结时发包间隔不可改", not p14.spin_pkt_gap.isEnabled())
p14._freeze_plan_inputs(False)
check("解冻后发包间隔可改", p14.spin_pkt_gap.isEnabled())
check("越界值被夹回范围（负值 → 0）",
      ui.PKT_GAP_MS_MIN == 0 and ui.PKT_GAP_MS_MAX == 10000)

# ⑥ 定时器槽自带终态防护（将来某条收尾路径漏 stop 也绝不冒帧）
w15 = FakeWorker()
p15 = new_page()
p15.combo_upgrade_target.setCurrentIndex(0)
prep_blocks(p15, w15)
n15 = len(w15.sent)
p15._state = ui.STATE_ABORTED
p15._on_pkt_gap_ready()          # 直接触发槽（模拟漏 stop 的定时器到点）
check("终态下间隔到点：不发帧", len(w15.sent) == n15, len(w15.sent))
p15._state = ui.STATE_FAILED
p15._on_pkt_gap_ready()
check("failed 态下间隔到点：不发帧", len(w15.sent) == n15, len(w15.sent))

# ======================================================================
print("=" * 60)
if FAIL:
    print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    sys.exit(1)
print(f"全部通过（{PASS} 项）✓")
