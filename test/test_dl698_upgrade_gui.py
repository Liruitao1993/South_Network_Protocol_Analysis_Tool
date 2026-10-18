# -*- coding: utf-8 -*-
"""协议8 升级页（`dlt698_upgrade_widget`）offscreen 回归 —— 假串口 worker，不碰硬件。

覆盖（design §11 GUI 用例表 + 任务硬要求）：
  [1]  纯助手：fmt_hex / parse_hex_text / parse_exec_time / normalize_hex_address /
       check_package_file（不存在、目录、空文件）+ 源码约束（不 import main_gui、
       不用 send_frame、不关串口、不订阅 frame_received）
  [2]  页面构建：默认值、日志就绪、「开始升级」由连接状态驱动、定时器先于 UI 建好
  [3]  未连接（worker=None / is_open()=False）→ 禁用、点击仍提示且**零字节发送**
  [4]  全通（启动传输 + 3 包写文件 + 执行升级）：write_raw 次数 = 帧数、进度 100%、
       日志含 [TX]/[RX]/[信息] 前缀；执行升级帧以「前导 FE + 半帧 + 续帧」分块交付
  [4b] 分包算术单一来源：「第 x/N 包」/进度分母/未发送包数都取 `UpgradePlan`
  [5]  进度只按**已确认**包累加（第 1 包确认前进度为 0）
  [6]  中间包超时 → 第 1 次重试成功 → 继续到完成（写入次数 = 帧数 + 1）
  [7]  超时用尽 → 状态 failed、不再发送后续包（写入次数停住）、日志「未发送后续 N 包」
  [7b] DAR≠0 → 日志给值与含义、按重试处理
  [8]  中止按钮 → 停表、不再发送、迟到确认不复活状态机
  [9]  拖放：QMimeData.setUrls + QDropEvent → 文件名/大小；反例（非 URL / 目录）不发信号
  [10] 配置持久化往返 + 坏文件宽容；cleanup 幂等、**不关串口**、断信号后不再进帧
  [11] crcmod 缺失 → 可读提示原文、不抛、零发送
  [12] 非本步 OMD / 坏帧 / 噪声 → 忽略不计确认
  [12b] RX 重同步：FE 段后非 68H / 长度域不可信的 68 头 / 末字节非 16H 的错位帧
       三种「头字节卡死」形态必须被丢掉（同一次交付里的真确认仍要被认）；反例：
       真半帧在等时一个字节都不许丢
  [13] 布局护栏：可见按钮 width >= sizeHint 且未设固定宽度上限
  [14] restyle_for_theme 不抛、配色随主题切换
  [15] 反例自检（判据不是恒真）
  [16] 传输中途的控制：换文件被拒（旧计划照旧推进）、点「清除」后按钮门控复位并可原地重跑
  [23] 发送通道：蓝牙（复用蓝牙页连接 + 按一次 ATT 写上限自动算每包上限）
  [24] 通道隔离：收发只认当前通道（蓝牙信号不拨串口通道、RX 不混源）、
       蓝牙页后建 worker / 换线程 / cleanup 只断自己的槽
  [25] 提升波特率（仅串口通道）：升级前先发现场实帧命令 → 留切换时间 → 主机切 115200 →
       才发 698 帧；期间不认任何回帧/超时；文件传完进入「等设备复位」时切回 9600
       （后版本读得通）；中止/失败/清除/页面关闭一律兜底切回；蓝牙通道置灰跳过
  [26] 升级后读版本的**双波特率尝试**（设备升级成功会复位回 9600、失败则可能仍停在
       115200）：9600 读不到 ⇒ 自动切 115200 再试一轮；两种都读不到才算读不到（原因里
       同时给出两个速率）；只在**提升过**时才换（没提升过单速率、零切速）；
       升级前读版本**不**换速率；换到 115200 后收尾仍切回 9600；
       切回失败保留标记（收尾会再试一次）
  [27] 升级前/后版本**比对判定**（变了=升级成功、完全一致=升级失败）：判等优先比原始字节、
       ⚠ 诊断行不参与、只在一边出现的字段算变化；缺基线 / 一侧读不到 / 前后读的不是同一项
       ⇒ 一律「无法判定」（不得硬说成功或失败）；结论进判定条 + 收尾状态行 + 日志，
       但不改状态机（流程照常 done/100%）；判定条配色随主题；日志不复述字段值
  [28] 升级包**路径持久化**：重开页面自动恢复上次的文件（字节/分包/摘要都回来），
       只有换新文件才更新路径；文件没了 ⇒ 不恢复（但保留落盘记录、不弹框）；
       恢复不冲掉手工「文件大小」覆盖值、不写「分包完成」日志；「清除」保留文件与路径

运行: python test/test_dl698_upgrade_gui.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401

import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QObject, QPoint, Qt, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton  # noqa: E402

import _config_sandbox  # noqa: E402

# 构造页面之前屏蔽模态框（否则 offscreen 下永久阻塞）
for _name in ("warning", "information", "critical"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()
patch.object(QMessageBox, "question",
             lambda *a, **k: QMessageBox.StandardButton.Yes).start()

SANDBOX = _config_sandbox.install()

import dlt698_upgrade_widget as upg_ui  # noqa: E402
import frame_deframe  # noqa: E402
from dl_t698_45_frame_gen import DLT69845FrameGenerator  # noqa: E402
import dl_t698_45_upgrade as upg  # noqa: E402

PASS = 0
FAIL = 0

GEN = DLT69845FrameGenerator()
#: Qt 的「没有上限」哨兵（`setMaximumWidth` 一旦写就 ≠ 它）
NO_MAX_WIDTH = 16777215

#: 升级页源码（约束类断言用，不参与运行时）
SRC = open(upg_ui.__file__, encoding="utf-8").read()


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [NG] {name}" + (f"  -> {detail}" if detail else ""))


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 56 - len(title)))


def settle(times: int = 6) -> None:
    """多泵几次事件：重建控件/改尺寸后一次 processEvents 不够（会读到旧几何/旧信号）。"""
    for _ in range(max(1, int(times))):
        QApplication.processEvents()


# ── 假串口 worker ──────────────────────────────────────────────────────


class FakeSerialWorker(QObject):
    """鸭子类型的 SerialWorker 替身：只实现本页用到的接口。

    - `is_open()` 由 `_open` 决定（测试可直接改，用来模拟掉线）
    - `write_raw(data)` **计数**并记下字节；**不自动回帧** —— 回帧由测试显式
      `deliver()`，否则在 write_raw 里同步 emit 会让状态机重入（真实串口不会这样）
    - `close_port()` 计数，用来断言本页**绝不**关端口
    - `set_baudrate()` 记账（真 worker 会先 `flush()` 排空发送缓冲再改 DCB）；`fail_baud=True`
      可模拟「切速失败」，验本页会停下而不是蒙着头继续发帧
    """

    raw_data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, opened: bool = True):
        super().__init__()
        self._open = bool(opened)
        self.sent = []                 # List[bytes]
        self.writes = 0
        self.closed = 0
        self.baud = 9600               # 当前速率（与真 worker 的 `_baudrate` 同义）
        self.baud_calls = []           # 每次 `set_baudrate()` 的入参（顺序可断言）
        self.fail_baud = False         # True ⇒ `set_baudrate()` 返回 False 并发 error

    def is_open(self) -> bool:
        return self._open

    def write_raw(self, data: bytes) -> bool:
        if not self._open:
            return False
        self.writes += 1
        self.sent.append(bytes(data))
        return True

    def set_baudrate(self, baudrate: int) -> bool:
        self.baud_calls.append(int(baudrate))
        if self.fail_baud:
            self.error_occurred.emit("切换波特率失败: 模拟")
            return False
        self.baud = int(baudrate)
        return True

    def close_port(self) -> None:
        self.closed += 1

    def deliver(self, data: bytes) -> None:
        """注入一次「原始串口交付」（可只给半帧，测自组帧）。"""
        self.raw_data_received.emit(bytes(data))


class FakeBleWorker(QObject):
    """假蓝牙 worker（只有升级页用到的接口/信号）—— 与 `FakeSerialWorker` 同形：`.sent`/`.deliver`。

    `send_data` 复刻真 worker 的「整帧一次写」语义：`single_write=True` 且超上限 ⇒ **拒发**并报错。
    """

    notification_received = Signal(str, bytes)
    connection_changed = Signal(bool)
    mtu_updated = Signal(int, list)
    error_occurred = Signal(str)

    def __init__(self, mtu: int = 512, connected: bool = True, name: str = "STA-模块"):
        super().__init__()
        self._mtu = int(mtu)
        self._connected = bool(connected)
        self._name = name
        self.sent = []               # List[bytes]（与假串口 worker 同形，run_to_end 可直接复用）
        self.single_flags = []       # 每帧是否走了「整帧一次写」
        self.rejected = 0

    def is_connected(self) -> bool:
        return self._connected

    def mtu_size(self) -> int:
        return self._mtu

    def single_write_limit(self) -> int:
        return max(20, self._mtu - 3)

    def device_name(self) -> str:
        return self._name

    def device_address(self) -> str:
        return "AA:BB:CC:DD:EE:FF"

    def send_data(self, data: bytes, single_write: bool = False) -> bool:
        if not self._connected:
            self.error_occurred.emit("蓝牙未连接，无法发送")
            return False
        if single_write and len(bytes(data)) > self.single_write_limit():
            self.rejected += 1
            self.error_occurred.emit(
                f"整帧 {len(bytes(data))} 字节超过一次 ATT 写上限 {self.single_write_limit()} 字节")
            return False
        self.sent.append(bytes(data))
        self.single_flags.append(bool(single_write))
        return True

    def deliver(self, data: bytes) -> None:
        self.notification_received.emit("ffe1", bytes(data))

    def set_mtu(self, mtu: int) -> None:
        self._mtu = int(mtu)
        self.mtu_updated.emit(int(mtu), [])

    def set_connected(self, ok: bool) -> None:
        self._connected = bool(ok)
        self.connection_changed.emit(bool(ok))


# ── 帧工具（按协议形状造确认帧，不用字符串比对）───────────────────────


def sa_len_of(frame: bytes) -> int:
    """链路帧里 SA 的**总字节数**（含地址特征字节）。广播（类型3）恒 1 字节。"""
    f = frame[4]
    return 1 if (f >> 6) == 3 else (f & 0x0F) + 2


def tx_parts(frame: bytes):
    """发送帧 → (SA 含特征字节, CA, APDU)。帧形：68|L(2)|C|SA|CA|HCS(2)|APDU|FCS(2)|16。"""
    n = sa_len_of(frame)
    return frame[4:4 + n], frame[4 + n], frame[4 + n + 3:len(frame) - 3]


def resp_apdu(tx_frame: bytes) -> bytes:
    """发送帧的 APDU。ACTION-Request Normal = `07 01 PIID OMD(4B) 参数…`。"""
    return tx_parts(tx_frame)[2]


def ack_for(tx_frame: bytes, dar: int = 0) -> bytes:
    """按 doc 响应形状组确认帧：`87 01 | PIID | OMD(4B) | DAR | 00 00 00`（FCS 正确）。"""
    sa, ca, apdu = tx_parts(tx_frame)
    resp = bytes([0x87, 0x01, apdu[2]]) + apdu[3:7] + bytes([dar, 0, 0, 0])
    return GEN._assemble_frame(sa, ca, 0xC3, resp)


def ack_with_omd(tx_frame: bytes, omd: bytes, dar: int = 0) -> bytes:
    """把确认帧的 OMD 换成**别的**方法（重算 HCS/FCS ⇒ 帧本身合法、只是不该被认）。

    `dar≠0` 时给「别的方法 + 失败结果」的杂帧（复位期设备可能吐出的错报告）。
    """
    sa, ca, apdu = tx_parts(tx_frame)
    resp = bytes([0x87, 0x01, apdu[2]]) + omd + bytes([dar, 0, 0, 0])
    return GEN._assemble_frame(sa, ca, 0xC3, resp)


#: 版本信息（表191）六个字段的样本值
VER_FIELDS = ("JCDZ", "V1.5", "250901", "V1.0", "230602", "SHANDONG")
VER_TEXT = ("厂商代码=JCDZ，软件版本号=V1.5，软件版本日期=2025-09-01，"
            "硬件版本号=V1.0，硬件版本日期=2023-06-02，厂商扩展信息=SHANDONG")


def version_data(*fields: str) -> bytes:
    """版本信息（表191）= `structure{厂商代码,软件版本号,软件版本日期,硬件版本号,硬件版本日期,厂商扩展信息}`。"""
    out = bytes([0x02, len(fields)])
    for f in fields:
        raw = f.encode("ascii")
        out += bytes([0x0A, len(raw)]) + raw
    return out


def ver_ack_for(tx_frame: bytes, fields=VER_FIELDS, dar: int = 0,
                tag: bytes = b"\x01", oad: bytes = None,
                raw_data: bytes = None) -> bytes:
    """读版本帧的响应：`85 01 | PIID | OAD(4B) | Get-Result | 数据`（tag 01=数据 / 00=错误信息 DAR）。

    OAD/PIID 从**被确认的那一帧**里取（回显口径），SA/CA 同源 ⇒ 帧内 HCS/FCS 自动正确；
    `raw_data` 给「不是六个命名字段」的载荷（如厂家扩展内部版本就是个 visible-string）。
    """
    sa, ca, apdu = tx_parts(tx_frame)                 # apdu = 05 01 PIID OAD 00
    oad = bytes(oad or apdu[3:7])
    if raw_data is not None:
        body = bytes(raw_data)
    else:
        body = version_data(*fields) if tag == b"\x01" else bytes([dar])
    resp = bytes([0x85, 0x01, apdu[2]]) + oad + bytes(tag) + body
    return GEN._assemble_frame(sa, ca, 0xC3, resp)


def visible_string(text: str) -> bytes:
    """A-XDR visible-string（`0A <长度> <ASCII>`）—— 内部版本这类非结构载荷用。"""
    raw = text.encode("ascii")
    return bytes([0x0A, len(raw)]) + raw


def omd_of(tx_frame: bytes) -> bytes:
    return resp_apdu(tx_frame)[3:7]


def write_pkg(payload: bytes) -> str:
    fd, path = tempfile.mkstemp(prefix="pkg_", suffix=".bin", dir=str(SANDBOX))
    with os.fdopen(fd, "wb") as fh:
        fh.write(payload)
    return path


def make_tab(worker=None, pkg_bytes: bytes = b"", fresh: bool = True):
    """新页面（可选：注入假 worker + 已选中升级包文件）→ (tab, worker, 路径)。

    ``fresh=True``（默认）先删沙箱配置文件：``cleanup()`` 会落盘参数，若不清，下一个
    页面会把上一个用例改过的「每包字节数 / 重试次数」读回来（用例互相污染 → 断言变假）。
    要看「读回已落盘配置」的用例传 ``fresh=False``。
    """
    cfg = os.path.join(str(SANDBOX), upg_ui.CONFIG_NAME)
    if fresh and os.path.exists(cfg):
        os.remove(cfg)
    tab = upg_ui.Dlt698UpgradeWidget()
    path = write_pkg(pkg_bytes) if pkg_bytes else ""
    if worker is not None:
        tab.set_serial_worker(worker)
    if path:
        tab._on_file_selected(path)
    return tab, worker, path


def _cols(text: str) -> int:
    """显示列宽（CJK 算 2 列）—— 断言「明细行对齐」用，不依赖产品实现的对齐函数。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def panel_pre(tab) -> str:
    """展示区「升级前」栏文本。"""
    return tab.txt_version_pre.toPlainText()


def panel_post(tab) -> str:
    """展示区「升级完成后」栏文本。"""
    return tab.txt_version_post.toPlainText()


def log_text(tab) -> str:
    return tab.log_text.toPlainText()


def last_log(tab) -> str:
    lines = [l for l in log_text(tab).splitlines() if l.strip()]
    return lines[-1] if lines else ""


def tx_hex_tokens(line: str) -> list:
    """``[TX]`` 行里属于 HEX 的 token（丢掉 ``[TX]`` 前缀、步骤名与 ``(共 N 字节)`` 标注）。

    用「恰好 2 个十六进制字符」判定：省略标注与中文步骤名/括号都不会命中。
    """
    hexchars = "0123456789ABCDEF"
    return [t for t in line.split() if len(t) == 2 and all(c in hexchars for c in t)]


def tx_line(log: str, label: str) -> str:
    """取含指定步骤名的 ``[TX]`` 行（找不到返回空串，让断言干净变红而不是抛异常）。"""
    return next((l for l in log.splitlines()
                 if l.startswith("[TX]") and label in l), "")


def start_transfer(tab, w, payload: bytes, block: int = 100) -> None:
    """设每包字节数 + 装文件 + 点「开始升级」（此时只发出启动传输帧）。"""
    tab.spin_block.setValue(block)
    tab._on_file_selected(write_pkg(payload))
    tab.btn_start.click()
    settle()


def run_to_end(tab, w, guard: int = 60) -> None:
    """把状态机推到终态：每轮为「最后发出的那帧」投一张匹配的响应。

    - 读版本信息步骤（`ver_pre`/`ver_post`）投 **GET-Response**；
    - 其余步骤投 ACTION-Response；
    - **「等待设备复位」阶段直接快进**（不等真实 10 秒：调 `_end_reset_wait()` 当即结束倒计时）；
      快进掩盖不了「定时器根本不 tick」—— [22]⑥ 用**真实事件循环**（delay=2 + 真 time.sleep）
      验过 1 秒 QTimer 的递减与自动发帧；
    - 执行升级那一步故意**分块交付**（前导 FE + 半帧 + 余下），验证本页自组帧而不是
      靠一次交付正好一帧。
    """
    for _ in range(guard):
        settle()
        if tab.state in ("done", "failed", "aborted") or not w.sent:
            return
        if tab._phase == upg_ui.PHASE_WAIT_RESET:
            tab._end_reset_wait()                     # 快进倒计时（不等真 10 秒）
            continue
        tx = w.sent[-1]
        ack = ver_ack_for(tx) if tab._phase in upg_ui.VER_PHASES else ack_for(tx)
        if tab._phase == "exec":
            w.deliver(bytes.fromhex("FEFEFE") + ack[:12])
            settle()
            w.deliver(ack[12:])
        else:
            w.deliver(ack)


# ── 用例 ──────────────────────────────────────────────────────────────


def test_helpers():
    section("[1] 纯助手与源码约束")
    check("fmt_hex 空格大写", upg_ui.fmt_hex(bytes.fromhex("681a00")) == "68 1A 00")
    # 用户报障：62B 的启动传输帧被截成 48B（尾部校验值/结束符看不到）→ 现 ≤200B 整帧打印
    out62 = upg_ui.fmt_hex(bytes(range(62)))
    check("fmt_hex ≤200B 整帧显示（62B 一个字节不少、无省略标注）",
          out62.split() == [f"{i:02X}" for i in range(62)] and " ... " not in out62, out62)
    out200 = upg_ui.fmt_hex(b"\xAA" * 200)
    check("fmt_hex 恰 200B 仍是整帧（边界）",
          out200.split() == ["AA"] * 200 and " ... " not in out200)
    out250 = upg_ui.fmt_hex(bytes(range(250)), limit=200)
    body, _, cnt = out250.partition("  (共 ")
    head, sep, tail = body.partition(" ... ")
    tokens = (head + " " + tail).split()
    check("fmt_hex >limit：中间 `...` 省略（头 100B + 尾 100B）",
          bool(sep) and head.split() == [f"{i:02X}" for i in range(100)]
          and tail.split() == [f"{i:02X}" for i in range(150, 250)], out250)
    check("fmt_hex >limit：被省略的 100~149 一个都不在输出里",
          not any(f"{i:02X}" in tokens for i in range(100, 150)))
    check("fmt_hex >limit：标注总长", cnt == "250 字节)", out250)
    check("fmt_hex limit=0 = 不限制",
          len(upg_ui.fmt_hex(b"\xAA" * 500, limit=0).split()) == 500)
    check("parse_hex_text 合法（含空格/下划线）",
          upg_ui.parse_hex_text("7F 7E_D9 D2") == bytes.fromhex("7F7ED9D2"))
    check("parse_hex_text 空串 = b''（可区分「没填」与「填错」）",
          upg_ui.parse_hex_text("  ") == b"")
    check("parse_hex_text 非法 = None", upg_ui.parse_hex_text("XYZ") is None)
    check("parse_exec_time → 7 字节（年 2B 大端 + 月日时分秒）",
          upg_ui.parse_exec_time("2026-10-15 08:30:00")
          == bytes.fromhex("07EA") + bytes([10, 15, 8, 30, 0]))
    check("parse_exec_time 无长度域（长度恰 7）",
          len(upg_ui.parse_exec_time("2026-01-01 00:00:00")) == 7)
    check("parse_exec_time 非法文案 → None",
          upg_ui.parse_exec_time("明天上午") is None and upg_ui.parse_exec_time("") is None)
    check("normalize_hex_address 补齐到长度（右侧补 00）",
          upg_ui.normalize_hex_address("AA", 6) == bytes.fromhex("AA0000000000"))
    check("normalize_hex_address 截断超长",
          upg_ui.normalize_hex_address("AAAAAAAAAAAAFF", 6) == bytes.fromhex("AAAAAAAAAAAA"))
    check("check_package_file：正常文件返回空串",
          upg_ui.check_package_file(write_pkg(b"abc")) == "")
    check("check_package_file：不存在",
          "不存在" in upg_ui.check_package_file(os.path.join(str(SANDBOX), "nope.bin")))
    check("check_package_file：目录被拒",
          "目录" in upg_ui.check_package_file(str(SANDBOX)))
    check("check_package_file：0 字节被拒", "为空" in upg_ui.check_package_file(write_pkg(b"")))

    # 只禁**语句级** import：docstring 里写「不得 import main_gui」是说明，不是依赖
    check("源码不 import main_gui（避免与主窗口成环）",
          "\nimport main_gui" not in SRC and "\nfrom main_gui" not in SRC)
    check("源码不用 send_frame（逐包 [发送] 刷屏）", ".send_frame(" not in SRC)
    check("源码不关串口（close_port 只在 docstring 里出现）", ".close_port(" not in SRC)
    check("源码不订阅 frame_received（698 帧会被截断）",
          "frame_received.connect" not in SRC and "raw_data_received.connect" in SRC)
    check("源码用 write_raw 发送", "write_raw(" in SRC)
    check("源码对 dl_t698_45_upgrade 惰性 import（函数内）",
          "import dl_t698_45_upgrade" in SRC
          and "\nimport dl_t698_45_upgrade" not in SRC)
    check("源码 frame_deframe 顶层 import（纯 stdlib，允许）",
          "\nimport frame_deframe\n" in SRC)
    check("假确认帧本身自证（frame_deframe 判出整帧长度、末字节 16H）",
          (lambda a: frame_deframe.frame_length_for("dlt698_45", bytearray(a)) == len(a)
           and a[-1] == 0x16)(ack_for(upg.build_write_block(
              upg.WILDCARD_SA, 0, 1, 0, b"AB"))))


def test_build():
    section("[2] 页面构建")
    tab, _, _ = make_tab()
    check("初始状态 idle", tab.state == "idle")
    check("默认每包字节数 600", tab.spin_block.value() == 600)
    check("默认超时 3000ms", tab.spin_timeout.value() == 3000)
    check("默认重试 3 次", tab.spin_retries.value() == 3)
    check("默认勾选自动执行升级", tab.chk_auto_exec.isChecked() is True)
    check("默认 SA 类型=通配", tab.combo_sa_type.currentData() == 1)
    check("默认 SA 长度=6", tab.combo_sa_len.currentData() == 6)
    check("默认 SA 地址 AAAA…", tab.edit_sa.text().upper() == "AAAAAAAAAAAA")
    check("默认执行升级时间=立即执行", tab.combo_exec_mode.currentData() == "now")
    check("默认文件大小=手工覆盖关（0）", tab.spin_size.value() == 0)
    check("未注入 worker 时开始按钮禁用", tab.btn_start.isEnabled() is False)
    check("未注入 worker 时按钮有提示", upg_ui.TIP_NOT_CONNECTED in tab.btn_start.toolTip())
    check("中止按钮初始禁用", tab.btn_abort.isEnabled() is False)
    check("拖放区已开启 setAcceptDrops", tab.drop_area.acceptDrops())
    check("日志区只读 + 2000 行封顶",
          tab.log_text.isReadOnly() and tab.log_text.maximumBlockCount() == 2000)
    check("日志就绪有提示", "升级页就绪" in log_text(tab))
    check("_save_timer 存在且单发（先于 _build_ui 建好）",
          tab._save_timer is not None and tab._save_timer.isSingleShot())
    check("_wait_timer 单发", tab._wait_timer.isSingleShot())
    check("默认 SA 组帧结果 = 通配 45 AA*6",
          tab._sa_ca()[0] == bytes.fromhex("45AAAAAAAAAAAA"), tab._sa_ca()[0].hex().upper())
    tab.cleanup()


def test_disconnected():
    section("[3] 未连接：禁用 + 零字节发送")
    closed = FakeSerialWorker(opened=False)
    tab, _, _ = make_tab(closed)
    check("is_open False → 开始按钮禁用", tab.btn_start.isEnabled() is False)
    tab._on_start()                            # 按钮禁用时 click() 不触发，直接调处理函数
    settle()
    check("未连接时点击仍给提示（处理函数级守卫）", "未连接串口" in log_text(tab),
          last_log(tab))
    check("未连接时零字节发送", closed.writes == 0 and closed.sent == [])

    tab2, _, _ = make_tab()
    tab2.btn_start.click()
    settle()
    check("worker=None 时同样零发送", tab2._serial_worker is None and tab2._sent_frames == 0)
    tab2.cleanup()

    w = FakeSerialWorker(opened=True)
    tab3, _, _ = make_tab(w)
    check("连上后开始按钮可用", tab3.btn_start.isEnabled() is True)
    w.connection_changed.emit(False)
    check("断开信号 → 立即禁用", tab3.btn_start.isEnabled() is False)
    w.connection_changed.emit(True)
    check("重连信号 → 恢复可用", tab3.btn_start.isEnabled() is True)
    # 传输中途掉线：下一次 write_raw 返回 False → 明确失败，不再空转
    start_transfer(tab3, w, bytes(range(200)), block=100)
    w._open = False
    tab3._send_current_step()
    settle()
    check("中途掉线 → failed 且有 [失败] 日志",
          tab3.state == "failed" and "[失败]" in log_text(tab3), tab3.state)
    tab3.cleanup()


def test_happy_path():
    section("[4] 全通：启动传输 + 3 包写文件 + 执行升级")
    payload = bytes(range(256)) + b"\xA5" * 294      # 550 B / 每包 200 → 3 包
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    start_transfer(tab, w, payload, block=200)
    check("分包数 = 3", len(tab._blocks) == 3, [len(b) for b in tab._blocks])
    check("开始只发出 1 帧（启动传输）", w.writes == 1, w.writes)
    check("首帧 OMD = F0010700", omd_of(w.sent[0]) == upg.OMD_START)
    run_to_end(tab, w)
    settle()
    check("状态 done", tab.state == "done", tab.state)
    check("进度 100%", tab.progress.value() == 100, tab.progress.value())
    check("进度文案明确 100%", "100%" in tab.lbl_progress.text(), tab.lbl_progress.text())
    check("帧数 = 1 启动 + 3 写 + 1 执行 = 5", w.writes == 5, w.writes)
    check("write_raw 次数 == 页内计数 == 记录帧数",
          tab._sent_frames == w.writes == len(w.sent))
    check("写文件 OMD 正确", omd_of(w.sent[1]) == upg.OMD_WRITE)
    check("执行升级 OMD 正确", omd_of(w.sent[-1]) == upg.OMD_EXEC)
    check("PIID 每帧自增（0..4）",
          [tx_parts(f)[2][2] for f in w.sent] == [0, 1, 2, 3, 4],
          [tx_parts(f)[2][2] for f in w.sent])
    check("末包字节数 = 150", len(tab._blocks[-1]) == 150)
    log = log_text(tab)
    check("日志含 [TX] 且带步骤名「启动传输」", "[TX]" in log and "(启动传输)" in log)
    check("日志含 [TX] 第 i 包", "(第 1/3 包)" in log and "(第 3/3 包)" in log)
    check("日志含 [TX] 执行升级", "(执行升级)" in log)
    # 日志格式（用户报障：TX 只显示部分帧内容）：小帧整帧、大帧中间省略
    s_line = tx_line(log, "(启动传输)")
    b_line = tx_line(log, "(第 1/3 包)")
    check("启动传输 TX 行整帧显示（无 `...`，字节数 = 实际帧长）",
          " ... " not in s_line and len(tx_hex_tokens(s_line)) == len(w.sent[0]),
          s_line)
    check("写文件 TX 行（>200B）只显头尾 200B + `...` + 总长",
          " ... " in b_line and len(tx_hex_tokens(b_line)) == 200
          and f"(共 {len(w.sent[1])} 字节)" in b_line, b_line)
    check("写文件 TX 行头段是帧起始 68、尾段是帧尾 16",
          tx_hex_tokens(b_line)[:1] == ["68"] and tx_hex_tokens(b_line)[-1:] == ["16"])
    # 两个读版本开关默认不勾 ⇒ 帧数与日志都不该出现读版本步骤
    check("默认不勾读版本 ⇒ 多一帧都没有、日志无读版本步骤",
          w.writes == 5 and "(升级前读版本信息)" not in log
          and "(升级完成后读版本信息)" not in log
          and "版本信息（升级前" not in log and "版本信息（升级完成后" not in log,
          f"{w.writes} / {[l for l in log.splitlines() if '版本信息（' in l]}")
    check("日志含 [RX] 且写 DAR=0 成功", "[RX]" in log and "DAR=0 成功" in log)
    check("日志含 [信息]", "[信息]" in log)
    check("已确认字节 == 文件字节数", tab._confirmed_bytes == len(payload),
          f"{tab._confirmed_bytes} vs {len(payload)}")
    check("状态行含帧数", "已发送 5 帧" in tab.lbl_status.text(), tab.lbl_status.text())
    check("中止/重试按钮复位", tab.btn_abort.isEnabled() is False
          and tab.spin_block.isEnabled() is True)
    tab.cleanup()


def test_plan_single_source():
    section("[4b] 分包算术单一来源（UpgradePlan）")
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    start_transfer(tab, w, bytes(range(200)), block=100)   # 2 包
    check("分包算术确实走 UpgradePlan（有 plan 对象）",
          tab._plan is not None and tab._plan.num_blocks == 2)

    class FakePlan:
        total_bytes = 999
        block_size = 7
        num_blocks = 42
        last_block_bytes = 3

    tab._plan = FakePlan()
    tab._phase = "blocks"
    tab._block_idx = 40
    check("「第 x/N 包」的 N 取 plan.num_blocks（不是自己算的 ceil）",
          tab._step_label() == "第 41/42 包", tab._step_label())
    tab._refresh_progress()
    check("进度分母取 plan.total_bytes",
          "999" in tab.lbl_progress.text(), tab.lbl_progress.text())
    tab._confirmed_bytes = 999
    tab._refresh_progress()
    check("已确认达 total_bytes ⇒ 100%", tab.progress.value() == 100,
          tab.progress.value())
    tab._block_idx = 41
    check("_pending_blocks 用 plan 计数", tab._pending_blocks() == 0,
          tab._pending_blocks())
    tab._block_idx = 39
    check("_pending_blocks = num_blocks - (i+1)", tab._pending_blocks() == 2,
          tab._pending_blocks())
    tab._on_abort()
    tab.cleanup()


def test_progress_only_on_ack():
    section("[5] 进度只按已确认累加")
    payload = bytes(range(120)) * 2           # 240 B / 每包 100 → 3 包
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    start_transfer(tab, w, payload, block=100)
    check("启动传输已发但未确认 → 进度 0",
          tab.progress.value() == 0 and tab._confirmed_bytes == 0)
    w.deliver(ack_for(w.sent[-1]))            # 确认启动传输
    settle()
    check("启动传输确认后仍 0（尚无数据包被确认）",
          tab._confirmed_bytes == 0 and tab.progress.value() == 0, tab.progress.value())
    check("确认后发出第 1 包", w.writes == 2 and omd_of(w.sent[-1]) == upg.OMD_WRITE)
    w.deliver(ack_for(w.sent[-1]))            # 确认第 1 包（100 B）
    settle()
    check("第 1 包确认后进度 = int(100*100/240)",
          tab._confirmed_bytes == 100 and tab.progress.value() == 41,
          f"{tab._confirmed_bytes} / {tab.progress.value()}")
    check("进度文案含「第 2/3 包」", "第 2/3 包" in tab.lbl_progress.text(),
          tab.lbl_progress.text())
    before = tab._confirmed_bytes
    for _ in range(4):
        settle()
    check("等待期间进度不自己涨", tab._confirmed_bytes == before)
    # 发了第 2 包但没确认 → 不计入
    check("第 2 包已发未确认（进度仍 100）",
          w.writes == 3 and tab._confirmed_bytes == 100, w.writes)
    tab._on_abort()
    tab.cleanup()


def test_retry_then_ok():
    section("[6] 中间包超时后重试成功")
    payload = bytes(range(200))               # 200 B / 每包 100 → 2 包
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    start_transfer(tab, w, payload, block=100)
    w.deliver(ack_for(w.sent[-1]))            # 启动传输 OK
    settle()
    check("已发第 1 包", w.writes == 2)
    w.deliver(ack_for(w.sent[-1]))            # 第 1 包 OK
    settle()
    check("已发第 2 包", w.writes == 3 and tab._block_idx == 1, w.writes)
    timeout_before = w.writes
    tab._on_timeout()                          # 第 2 包超时（等价单发 QTimer 到期）
    settle()
    check("超时后重发同一包（写入 +1）", w.writes == timeout_before + 1, w.writes)
    check("重试用掉 1 次", tab._attempt == 1)
    check("日志出现 [超时] 前缀", "[超时]" in log_text(tab), last_log(tab))
    check("超时日志含「已重试 1/3」", "已重试 1/3" in log_text(tab), last_log(tab))
    check("重发的 PIID 也自增",
          tx_parts(w.sent[-1])[2][2] == tx_parts(w.sent[-2])[2][2] + 1)
    w.deliver(ack_for(w.sent[-1]))            # 重发后确认 OK
    settle()
    check("重试成功后继续到执行升级", omd_of(w.sent[-1]) == upg.OMD_EXEC, tab.state)
    w.deliver(ack_for(w.sent[-1]))
    settle()
    check("最终 done", tab.state == "done")
    check("总写入 = 干净轮次 4 + 1 次重试 = 5", w.writes == 5, w.writes)
    check("重试不重复计进度", tab._confirmed_bytes == 200, tab._confirmed_bytes)
    tab.cleanup()


def test_retries_exhausted():
    section("[7] 超时用尽 → 停止且不再发送后续包")
    payload = bytes(range(250))               # 250 B / 每包 50 → 5 包
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    tab.spin_retries.setValue(2)
    start_transfer(tab, w, payload, block=50)
    w.deliver(ack_for(w.sent[-1]))            # 启动传输 OK → 第 1 包
    settle()
    w.deliver(ack_for(w.sent[-1]))            # 第 1 包 OK → 第 2 包
    settle()
    check("停在第 2 包", tab._block_idx == 1 and w.writes == 3, w.writes)
    frozen = w.writes
    # 「重试次数」= 同一包的**重发**次数：首次发送不计，故 retries=2 需要
    # 「1 次原发 + 2 次重发」共 3 轮超时才判定用尽。
    tab._on_timeout()
    settle()
    check("第 1 次超时 → 重发（attempt 1/2）",
          tab.state == "transferring" and w.writes == frozen + 1, w.writes)
    tab._on_timeout()
    settle()
    check("第 2 次超时 → 重发（attempt 2/2）", w.writes == frozen + 2, w.writes)
    tab._on_timeout()
    settle()
    check("重试用尽 → failed", tab.state == "failed", tab.state)
    check("不再发送后续包（写入次数停 = 冻结 + 2 次重发）",
          w.writes == frozen + 2, f"{w.writes} vs {frozen + 2}")
    log = log_text(tab)
    check("日志「第 2 包失败，已停止，未发送后续 3 包」",
          "第 2 包失败" in log and "已停止" in log and "未发送后续 3 包" in log,
          last_log(tab))
    check("中止按钮复位", tab.btn_abort.isEnabled() is False)
    tab._on_timeout()
    check("failed 后超时不再发送", w.writes == frozen + 2)
    w.deliver(ack_for(w.sent[-1]))
    settle()
    check("failed 后确认帧也不再推进", w.writes == frozen + 2 and tab.state == "failed")
    tab.cleanup()


def test_dar_rejected():
    section("[7b] DAR≠0 按重试处理、日志给值与含义")
    payload = bytes(range(120))
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    start_transfer(tab, w, payload, block=100)
    n = w.writes
    w.deliver(ack_for(w.sent[-1], dar=3))     # 启动传输回「拒绝读写」
    settle()
    log = log_text(tab)
    check("日志出现 DAR=3", "DAR=3" in log, last_log(tab))
    check("DAR 含义（拒绝读写）出现在日志", "拒绝读写" in log)
    check("DAR≠0 触发重发（写入 +1）", w.writes == n + 1, w.writes)
    check("DAR≠0 不判 done", tab.state != "done")
    check("DAR≠0 用 [失败] 前缀（与 [超时] 可区分）",
          "[失败]" in log and "已重试 1/3" in log, last_log(tab))
    tab._on_abort()
    tab.cleanup()


def test_abort():
    section("[8] 中止按钮")
    payload = bytes(range(240))               # 240 / 60 → 4 包
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    start_transfer(tab, w, payload, block=60)
    w.deliver(ack_for(w.sent[-1]))            # 启动传输 OK → 第 1 包
    settle()
    frozen = w.writes
    tab.btn_abort.click()
    settle()
    check("状态 aborted", tab.state == "aborted", tab.state)
    check("等待定时器已停", tab._wait_timer.isActive() is False)
    check("中止后不再发送", w.writes == frozen)
    check("日志写明中止位置", "已中止" in log_text(tab) and "第 1/4 包" in log_text(tab),
          last_log(tab))
    w.deliver(ack_for(w.sent[-1]))
    settle()
    check("中止后收到确认也不再发送", w.writes == frozen and tab.state == "aborted")
    check("中止后可重新开始（开始按钮恢复）", tab.btn_start.isEnabled() is True)
    tab.cleanup()


def test_drop_area():
    section("[9] 拖放")
    payload = bytes([1, 2, 3]) * 700          # 2100 B / 默认 600 → 4 包
    path = write_pkg(payload)
    tab, _, _ = make_tab()

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    ev = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    got = []
    tab.drop_area.file_dropped.connect(lambda p: got.append(p))
    tab.drop_area.dragEnterEvent(ev)
    tab.drop_area.dropEvent(ev)
    settle()
    # QUrl.toLocalFile() 在 Windows 上把分隔符写成 `/`，与 tempfile 给的 `\` 不同 → 归一后比
    check("dropEvent 触发 file_dropped 且指向所拖文件",
          len(got) == 1 and os.path.normcase(got[0]) == os.path.normcase(path), got)
    check("文件名显示正确", tab.lbl_file_name.text() == os.path.basename(path),
          tab.lbl_file_name.text())
    check("大小显示正确", tab.lbl_file_size.text() == f"大小 {len(payload):,} B",
          tab.lbl_file_size.text())
    check("包内容已读入", len(tab._data) == len(payload))
    check("文件大小同步到 spin", tab.spin_size.value() == len(payload))
    check("分包数 = ceil(2100/600) = 4", len(tab._blocks) == 4,
          [len(b) for b in tab._blocks])

    before = tab._path
    txt = QMimeData()
    txt.setText("68 1A 00 …")
    ev2 = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, txt,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tab.drop_area.dropEvent(ev2)
    settle()
    check("非文件拖放被拒（已选文件不变）", tab._path == before)
    check("拒因写进日志", "只接受本机文件" in log_text(tab), last_log(tab))

    dir_mime = QMimeData()
    dir_mime.setUrls([QUrl.fromLocalFile(str(SANDBOX))])
    ev3 = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, dir_mime,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tab.drop_area.dropEvent(ev3)
    settle()
    check("拖目录被拒且不改已选文件", tab._path == before)
    check("目录拒因在日志", "目录" in log_text(tab), last_log(tab))

    # 反例自检：dragEnterEvent 只认 URL
    plain = QMimeData()
    plain.setText("hello")
    ev4 = QDropEvent(QPoint(1, 1), Qt.DropAction.MoveAction, plain,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    check("反例：非 URL 拖放不 accept（proposedAction 仍为 NoAction）",
          not (ev4.proposedAction() == Qt.DropAction.MoveAction
               and ev4.isAccepted()))
    tab.drop_area.dragEnterEvent(ev4)
    check("非 URL 拖放 dragEnter 不接受", ev4.proposedAction() != Qt.DropAction.MoveAction
          or not ev4.isAccepted())
    tab.cleanup()


def test_persist_and_cleanup():
    section("[10] 配置持久化 / cleanup")
    cfg_path = os.path.join(str(SANDBOX), upg_ui.CONFIG_NAME)
    if os.path.exists(cfg_path):
        os.remove(cfg_path)

    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    tab.spin_block.setValue(1234)
    tab.spin_retries.setValue(5)
    tab.combo_exec_mode.setCurrentIndex(1)     # 指定时间
    tab.edit_exec_time.setText("2026-10-15 08:30:00")
    tab.chk_auto_exec.setChecked(False)
    tab.sec_params.set_expanded(False)
    check("_save_persisted 落盘成功", tab._save_persisted() is True)
    check("配置写在沙箱（app_paths.data_path 属性访问生效）",
          os.path.exists(cfg_path), cfg_path)
    with open(cfg_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    check("落盘内容含新值", raw["block_size"] == 1234 and raw["retries"] == 5)
    check("无 .tmp 残留", not os.path.exists(cfg_path + ".tmp"), cfg_path + ".tmp")
    tab.cleanup()

    tab2, _, _ = make_tab(fresh=False)
    check("新页面读回 block_size", tab2.spin_block.value() == 1234)
    check("新页面读回 retries", tab2.spin_retries.value() == 5)
    check("新页面读回 exec_mode=sched", tab2.combo_exec_mode.currentData() == "sched")
    check("新页面读回 exec_time", tab2.edit_exec_time.text() == "2026-10-15 08:30:00")
    check("新页面读回 auto_exec=False", tab2.chk_auto_exec.isChecked() is False)
    check("新页面读回折叠状态", tab2.sec_params.is_expanded() is False)
    w2 = FakeSerialWorker()
    tab2.set_serial_worker(w2)
    tab2.cleanup()
    check("cleanup 不关串口", w2.closed == 0, w2.closed)
    w2.deliver(bytes.fromhex("681A00C345AAAAAAAAAAAA00E23C870100F001070000000000AE1116"))
    settle()
    # 判别力：整帧会被处理掉、不留字节 ⇒ 必须再投一段**半帧**（未断开时会累积 14 字节）
    # —— 只投整帧时，这条断言在「cleanup 忘了断信号」的缺陷下也是绿的（实测）。
    w2.deliver(bytes.fromhex("FEFEFE") + bytes.fromhex("681A00C345AAAAAAAAAAAA"))
    settle()
    check("cleanup 断信号后不再进帧（半帧也不进缓冲）",
          len(tab2._rx_buf) == 0, len(tab2._rx_buf))
    check("cleanup 后 worker 已摘除", tab2._serial_worker is None)
    check("cleanup 幂等（第二次不抛）", (tab2.cleanup(), True)[-1])

    with open(cfg_path, "w", encoding="utf-8") as fh:
        fh.write("{ 这不是 JSON ]")
    tab3, _, _ = make_tab(fresh=False)
    check("坏 JSON → 回落默认（不抛）", tab3.spin_block.value() == 600)
    tab3.cleanup()
    with open(cfg_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"block_size": "abc", "retries": 9999, "sa_type": 77}))
    tab4, _, _ = make_tab(fresh=False)
    check("值坏（非数/越界）→ 回落默认",
          tab4.spin_block.value() == 600 and tab4.spin_retries.value() == 3
          and tab4.combo_sa_type.currentData() == 1)
    tab4.cleanup()
    # 收尾：清掉沙箱配置，后续用例从默认值起步（避免跨用例耦合）
    if os.path.exists(cfg_path):
        os.remove(cfg_path)


def test_missing_crcmod():
    section("[11] crcmod 缺失路径（惰性 import + 可读提示）")
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w, bytes(range(64)))
    check("本页顶层不持有 dl_t698_45_upgrade 名字",
          not hasattr(upg_ui, "dl_t698_45_upgrade"))
    tab.spin_block.setValue(50)
    with patch.dict(sys.modules, {"dl_t698_45_upgrade": None}):
        tab._upg = None
        tab.btn_start.click()
        settle()
        check("缺失时 _upgrade_module 返回 None（不抛）", tab._upgrade_module() is None)
    log = log_text(tab)
    check("提示原文「协议8 需要 crcmod，请 pip install crcmod」",
          "协议8 需要 crcmod，请 pip install crcmod" in log, last_log(tab))
    check("crcmod 缺失时零发送", w.writes == 0, w.writes)
    check("crcmod 缺失时状态仍是 idle（不半启动）", tab.state == "idle", tab.state)
    tab.cleanup()


def test_unknown_frames_ignored():
    section("[12] 非本步/坏帧：忽略不计确认（design §10）")
    payload = bytes(range(120))
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    start_transfer(tab, w, payload, block=100)
    frozen = w.writes
    check("当前在 starting", tab.state == "starting", tab.state)

    w.deliver(ack_with_omd(w.sent[-1], upg.OMD_WRITE))
    settle()
    check("OMD 不符 → 忽略，不推进", w.writes == frozen and tab.state == "starting",
          tab.state)
    check("忽略行说明原因（OMD 不符）", "OMD 不符" in last_log(tab), last_log(tab))

    bad = bytearray(ack_for(w.sent[-1]))
    bad[-4] ^= 0xFF
    w.deliver(bytes(bad))
    settle()
    check("坏帧（FCS 被改坏）不当确认", w.writes == frozen)
    check("坏帧有日志（FCS 校验不通过）", "FCS 校验不通过" in last_log(tab), last_log(tab))

    n0 = w.writes
    w.deliver(b"\x00\x11\x22\x33")
    settle()
    check("噪声字节不推进状态机", w.writes == n0)
    check("噪声被重同步丢弃（不把后面的真帧卡死）",
          len(tab._rx_buf) == 0 and "非帧起点" in last_log(tab), last_log(tab))

    # 噪声之后到齐的真确认仍然生效（重同步的**目的**，不是只丢字节）
    w.deliver(b"\xEE" + ack_for(w.sent[-1]))
    settle()
    check("噪声后的真确认照样被认（推进到第 1 包）",
          w.writes == n0 + 1 and tab.state == "transferring",
          f"{w.writes} / {tab.state}")

    # 非 ACTION-Response（例如 GET-Response）→ 忽略
    sa, ca, apdu = tx_parts(w.sent[-1])
    other = GEN._assemble_frame(sa, ca, 0xC3,
                                bytes([0x85, 0x01, apdu[2]]) + apdu[3:7] + bytes([0, 0]))
    n1 = w.writes
    w.deliver(other)
    settle()
    check("GET-Response 不当确认", w.writes == n1)
    check("非 ACTION-Response 的忽略行", "不是 ACTION-Response" in last_log(tab),
          last_log(tab))
    tab._on_abort()
    tab.cleanup()


def test_resync_edges():
    section("[12b] RX 重同步：三种「头字节卡死」形态必须能丢掉")
    payload = bytes(range(120))

    def started():
        w = FakeSerialWorker()
        tab, _, _ = make_tab(w)
        start_transfer(tab, w, payload, block=100)     # 启动传输已发，等确认
        return tab, w

    # ① 前导 FE 之后不是 68H（线噪进了前导段）
    tab, w = started()
    n0 = w.writes
    w.deliver(bytes.fromhex("FEFE99") + ack_for(w.sent[-1]))
    settle()
    check("① FE 段后非 68H：丢掉后同一次交付里的真确认照样被认",
          w.writes == n0 + 1 and tab.state == "transferring" and len(tab._rx_buf) == 0,
          f"{w.writes} / {tab.state} / {len(tab._rx_buf)}")
    check("① 丢弃写进日志", "非帧起点" in log_text(tab), last_log(tab))
    tab.cleanup()

    # ② 以 68H 开头但长度域不可信（错帧/串扰）
    tab, w = started()
    n0 = w.writes
    w.deliver(bytes.fromhex("68FF3F0011") + ack_for(w.sent[-1]))
    settle()
    check("② 长度域不可信的 68 头：丢掉后真确认照样被认",
          w.writes == n0 + 1 and tab.state == "transferring" and len(tab._rx_buf) == 0,
          f"{w.writes} / {tab.state} / {len(tab._rx_buf)}")
    tab.cleanup()

    # ③ 按长度域已到齐而末字节不是 16H（错位帧）
    tab, w = started()
    ack = ack_for(w.sent[-1])
    need = frame_deframe.frame_length_for("dlt698_45", bytearray(ack))
    bad = bytearray(ack)
    bad[need - 1] = 0x17                               # 末字节不给 16H 自证
    n0 = w.writes
    w.deliver(bytes(bad) + ack)
    settle()
    check("③ 末字节非 16H 的错位帧：头条丢掉后真确认照样被认",
          w.writes == n0 + 1 and tab.state == "transferring" and len(tab._rx_buf) == 0,
          f"{w.writes} / {tab.state} / {len(tab._rx_buf)}")
    tab.cleanup()

    # ④ 反例自检：**真半帧在等**时一个字节都不能丢（否则会把帧切碎）
    tab, w = started()
    ack = ack_for(w.sent[-1])
    w.deliver(bytes.fromhex("FEFE") + ack[:10])
    settle()
    check("④ 半帧在等 → 缓冲原样保留（12 字节不丢）", len(tab._rx_buf) == 12,
          len(tab._rx_buf))
    check("④ 半帧期间没有重同步丢弃日志", "非帧起点" not in log_text(tab), last_log(tab))
    n0 = w.writes
    w.deliver(ack[10:])
    settle()
    check("④ 续帧到达后被正常取出并计确认",
          w.writes == n0 + 1 and tab.state == "transferring" and len(tab._rx_buf) == 0,
          f"{w.writes} / {tab.state} / {len(tab._rx_buf)}")
    tab.cleanup()


def test_layout_guard():
    section("[13] 布局护栏：按钮不裁字、无固定宽度上限")
    tab, _, _ = make_tab()
    tab.resize(1100, 800)
    tab.show()
    settle(8)
    btns = [b for b in tab.findChildren(QPushButton) if b.isVisible()]
    check("可见按钮数量合理（>=5）", len(btns) >= 5, len(btns))
    tight = [(b.text(), b.width(), b.sizeHint().width())
             for b in btns if b.width() < b.sizeHint().width()]
    check("所有可见按钮 width >= sizeHint", not tight, tight)
    capped = [(b.text(), b.maximumWidth())
              for b in btns if b.maximumWidth() != NO_MAX_WIDTH]
    check("没有任何按钮设了固定宽度上限", not capped, capped)
    fixed = [(b.text(), b.minimumWidth(), b.maximumWidth())
             for b in btns if b.minimumWidth() == b.maximumWidth()]
    check("没有 setFixedWidth 形态（min==max）", not fixed, fixed)
    check("源码没有对控件调用 setFixedWidth/setMaximumWidth（docstring 里的禁令除外）",
          "setFixedWidth(" not in SRC and "setMaximumWidth(" not in SRC)
    hdr = tab.sec_params.header_button
    check("折叠区标题按钮同样不裁字", hdr.width() >= hdr.sizeHint().width(),
          (hdr.width(), hdr.sizeHint().width()))
    check("折叠区标题按钮无宽度上限", hdr.maximumWidth() == NO_MAX_WIDTH,
          hdr.maximumWidth())
    check("拖放区可见", tab.drop_area.isVisible())
    check("进度条可见", tab.progress.isVisible())
    # 版本信息展示区：位置（参数栏之下、日志之上）+ 并排两栏 + 高度放得下 7 行（不许「要滚动才看得见」）
    check("展示区在参数栏之下、日志之上",
          tab.grp_version.isVisible()
          and tab.sec_params.y() < tab.grp_version.y() < tab.log_text.y(),
          (tab.sec_params.y(), tab.grp_version.y(), tab.log_text.y()))
    check("展示区是并排两栏（同一行、等宽）",
          tab.txt_version_pre.y() == tab.txt_version_post.y()
          and abs(tab.txt_version_pre.width() - tab.txt_version_post.width()) <= 2,
          (tab.txt_version_pre.geometry(), tab.txt_version_post.geometry()))
    need = tab.txt_version_pre.fontMetrics().lineSpacing() * 7
    check("每栏高度放得下「标题 + 6 个字段」（不裁行）",
          tab.txt_version_pre.height() >= need and tab.txt_version_post.height() >= need,
          (tab.txt_version_pre.height(), need))
    check("两栏初始为空态文案",
          panel_pre(tab) == "升级前：（未读取）"
          and panel_post(tab) == "升级完成后：（未读取）",
          (panel_pre(tab), panel_post(tab)))
    # 通道状态标签：可见、有内容、确实被绘制（visibleRegion 抓「控件在但没画出来」）
    check("通道状态标签可见且有内容（未裁成空白）",
          tab.lbl_channel_state.isVisible() and bool(tab.lbl_channel_state.text())
          and not tab.lbl_channel_state.visibleRegion().isEmpty(),
          (tab.lbl_channel_state.text(), tab.lbl_channel_state.visibleRegion()))
    check("通道状态标签允许换行（窄窗口不截断）",
          tab.lbl_channel_state.wordWrap() is True)
    tab.hide()
    settle()
    tab.cleanup()


def test_theme():
    section("[14] restyle_for_theme")
    tab, _, _ = make_tab()
    light_qss = tab.log_text.styleSheet()
    tab.restyle_for_theme(True)
    dark_qss = tab.log_text.styleSheet()
    check("暗色后日志样式表已换", dark_qss != light_qss and "#1E1E1E" in dark_qss, dark_qss)
    check("暗色后拖放区样式已换", "#1E1E1E" in tab.drop_area.styleSheet())
    check("暗色后提示文字有色", "color:" in tab.lbl_drop_hint.styleSheet())
    tab._log("[信息] 暗色下的一行", "rx")
    check("换肤后仍可写日志（不抛）", "暗色下的一行" in log_text(tab))
    tab.restyle_for_theme(False)
    check("切回浅色不抛", "#FFFFFF" in tab.log_text.styleSheet())
    tab.cleanup()


def test_negatives():
    section("[15] 反例自检（判据不是恒真）")
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    check("反例：未点开始前 write_raw 为 0", w.writes == 0)
    tab.spin_block.setValue(100)
    tab._on_file_selected(write_pkg(bytes(range(200))))
    check("反例：未确认时 _confirmed_bytes 为 0", tab._confirmed_bytes == 0)
    check("反例：已分包但没开始（状态仍 idle）", tab.state == "idle" and len(tab._blocks) == 2)

    before = tab._data
    tab._on_file_selected("")
    check("反例：空路径不改已读数据", tab._data == before and len(tab._data) == 200)

    t2, _, _ = make_tab(w)
    t2.btn_start.click()
    settle()
    check("反例：没选文件时不发送", t2._sent_frames == 0 and "请先拖入" in log_text(t2),
          last_log(t2))
    check("反例：没选文件时状态仍 idle", t2.state == "idle")
    t2.cleanup()
    tab.cleanup()


def test_mid_transfer_controls():
    section("[16] 传输中途：换文件被拒 / 清除后按钮门控复位")
    payload = bytes(range(120))                # 120 B / 每包 60 → 2 包

    # ① 传输中换文件 → 忽略（旧计划不变），旧包的确认仍照旧推进
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    start_transfer(tab, w, payload, block=60)
    w.deliver(ack_for(w.sent[-1]))             # 启动传输 OK → 第 1 包
    settle()
    w.deliver(ack_for(w.sent[-1]))             # 第 1 包 OK → 第 2 包
    settle()
    check("前置：第 2 包在飞（idx=1）",
          tab._block_idx == 1 and tab.state == "transferring", tab.state)
    before_blocks = [len(b) for b in tab._blocks]
    before_data = tab._data
    tab._on_file_selected(write_pkg(bytes([0xAA] * 30)))
    settle()
    check("传输中换文件被拒（分包/数据一律不变）",
          [len(b) for b in tab._blocks] == before_blocks and tab._data == before_data
          and tab._plan.total_bytes == len(payload),
          [len(b) for b in tab._blocks])
    check("拒因写进日志", "升级进行中" in log_text(tab), last_log(tab))
    n = w.writes
    w.deliver(ack_for(w.sent[-1]))             # 旧第 2 包确认 → 自动走执行升级
    settle()
    check("旧计划继续推进（不因换文件越界/发错包）",
          w.writes == n + 1 and omd_of(w.sent[-1]) == upg.OMD_EXEC
          and tab.state == "finishing", f"{w.writes} / {tab.state}")
    w.deliver(ack_for(w.sent[-1]))
    settle()
    check("仍能正常收尾 done", tab.state == "done", tab.state)
    tab.cleanup()

    # ② 传输中点「清除」→ 状态 idle 且按钮门控复位（可原地重跑）
    w2 = FakeSerialWorker()
    tab2, _, _ = make_tab(w2)
    start_transfer(tab2, w2, payload, block=60)
    w2.deliver(ack_for(w2.sent[-1]))
    settle()
    tab2.btn_clear.click()
    settle()
    check("清除后状态 idle", tab2.state == "idle", tab2.state)
    check("清除后「开始升级」恢复可用（串口仍连接）", tab2.btn_start.isEnabled() is True)
    check("清除后「中止」复位禁用", tab2.btn_abort.isEnabled() is False)
    check("清除后每包字节数可编辑", tab2.spin_block.isEnabled() is True)
    check("清除日志写明本轮已停", "本轮传输已停止" in log_text(tab2), last_log(tab2))
    n2 = w2.writes
    tab2.btn_start.click()
    settle()
    check("清除后可原地重跑（再次发出启动传输帧）",
          w2.writes == n2 + 1 and omd_of(w2.sent[-1]) == upg.OMD_START,
          f"{w2.writes} / {tab2.state}")
    tab2._on_abort()
    tab2.cleanup()


#: 读版本帧的 APDU 形状：`05 01 <PIID> <OAD> 00`（GET-Request Normal + TimeTag 无）
def is_ver_frame(frame: bytes, oad: bytes = None) -> bool:
    """`oad=None` 时断言为「通用版本」`43000300`（默认选择）；传 `INT_OAD` 断言内部版本。"""
    apdu = resp_apdu(frame)
    return (len(apdu) == 8 and apdu[0] == 0x05 and apdu[1] == 0x01
            and apdu[3:7] == bytes(oad or upg.OAD_VERSION) and apdu[7] == 0x00)


#: 厂家扩展「内部版本」的 OAD（页面「读版本内容」下拉第 2 项）
INT_OAD = bytes.fromhex("FF100400")

#: **现场实帧**：内部版本读命令的响应（带 4 字节 FEH 前导；6 项 visible-string 4/4/6/4/6/8，
#: 与表191 版本信息同形）—— 用户 2026-10-15 在设备上实测抓的，HCS/FCS 均通过。
REAL_INT_RESP = bytes.fromhex(
    "FE FE FE FE 68 47 00 C3 05 03 24 08 04 26 20 00 5A E2 "
    "85 01 00 FF 10 04 00 01 "
    "02 06 0A 04 4C 48 49 4E 0A 04 30 30 33 39 0A 06 32 36 30 38 30 33 "
    "0A 04 30 30 31 41 0A 06 32 35 31 30 31 33 0A 08 47 57 47 53 58 58 58 58 "
    "00 00 14 CD 16".replace(" ", ""))
#: 该帧解析出来应有的 6 个字段（名称 → 值；日期已补全为 20YY-MM-DD）
REAL_INT_FIELDS = [
    ("厂商代码", "LHIN"),
    ("软件版本号", "0039"),
    ("软件版本日期", "2026-08-03"),
    ("硬件版本号", "001A"),
    ("硬件版本日期", "2025-10-13"),
    ("厂商扩展信息", "GWGSXXXX"),
]


def test_version_read_flow():
    section("[17] 可选「升级前/升级完成后读版本信息」")
    payload = bytes(range(200)) + b"\xA5" * 100          # 300 B / 每包 100 → 3 包
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    check("两个勾选框存在且默认不勾",
          tab.chk_read_before.isChecked() is False and tab.chk_read_after.isChecked() is False)
    tab.spin_block.setValue(100)
    tab._on_file_selected(write_pkg(payload))
    tab.chk_read_before.setChecked(True)
    tab.chk_read_after.setChecked(True)
    tab.btn_start.click()
    settle()
    check("勾选后先发读版本帧（不是启动传输）",
          w.writes == 1 and is_ver_frame(w.sent[0]) and tab._phase == "ver_pre",
          f"{w.writes} / {tab._phase}")
    check("读版本帧用页面 SA（默认通配 0x45 + AA×6）",
          tx_parts(w.sent[0])[0] == upg.WILDCARD_SA, tx_parts(w.sent[0])[0].hex().upper())
    check("TX 日志标出步骤名「升级前读版本信息」且帧整帧显示（25 字节无省略）",
          "(升级前读版本信息)" in tx_line(log_text(tab), "(升级前读版本信息)")
          and len(tx_hex_tokens(tx_line(log_text(tab), "(升级前读版本信息)"))) == len(w.sent[0]),
          tx_line(log_text(tab), "(升级前读版本信息)"))
    check("开始日志写明两个开关状态", "升级前读版本=是" in log_text(tab)
          and "升级后读版本=是" in log_text(tab))
    check("传输中两个勾选框被冻结（与每包字节数同口径）",
          tab.chk_read_before.isEnabled() is False
          and tab.chk_read_after.isEnabled() is False
          and tab.spin_block.isEnabled() is False)

    w.deliver(ver_ack_for(w.sent[-1]))
    settle()
    check("读版本确认后进入启动传输（第 2 帧 OMD=F0010700）",
          w.writes == 2 and omd_of(w.sent[1]) == upg.OMD_START and tab._phase == "start",
          f"{w.writes} / {tab._phase}")
    # 用户反馈的显示改版：解析内容必须写在**帧的下面若干行**，不能贴在帧尾（NoWrap 下要横向拖）
    lines = log_text(tab).splitlines()
    rx_idx = next((i for i, l in enumerate(lines)
                   if l.startswith("[RX]") and "68 " in l), -1)
    check("找得到读版本的 [RX] 帧行", rx_idx >= 0, lines[-3:])
    check("帧行本身**不带**解析内容（不再贴在帧尾）",
          rx_idx >= 0 and "版本信息" not in lines[rx_idx], lines[rx_idx] if rx_idx >= 0 else "")
    after = lines[rx_idx + 1:rx_idx + 9] if rx_idx >= 0 else []
    check("下一行是「→ 版本信息（升级前·通用）读取成功（6 项）」",
          after[:1] == ["  → 版本信息（升级前·通用）读取成功（6 项）"], after[:1])
    detail = after[1:7]
    expected = [
        ("厂商代码", "JCDZ", "0A044A43445A"),
        ("软件版本号", "V1.5", "0A0456312E35"),
        ("软件版本日期", "2025-09-01", "0A06323530393031"),
        ("硬件版本号", "V1.0", "0A0456312E30"),
        ("硬件版本日期", "2023-06-02", "0A06323330363032"),
        ("厂商扩展信息", "SHANDONG", "0A085348414E444F4E47"),
    ]
    check("再往下是逐字段明细（表191 六个字段 + 日期补全 + 原始字节，共 6 行）",
          len(detail) == 6 and all(
              d.strip().startswith(name) and f"= {value}" in d and f"[{raw}]" in d
              for d, (name, value, raw) in zip(detail, expected)), detail)
    check("明细行的 '=' 按显示宽度对齐（CJK 算 2 列）",
          len({_cols(d.split("=")[0]) for d in detail}) == 1 if detail else False, detail)
    check("版本信息展示区（升级前栏）显示明细（含表头/字段/值）",
          "升级前 · 通用 ·" in panel_pre(tab) and "厂商代码" in panel_pre(tab)
          and "JCDZ" in panel_pre(tab), panel_pre(tab))
    check("展示区此时「升级完成后」栏还是未读取",
          panel_post(tab) == "升级完成后：（未读取）", panel_post(tab))

    run_to_end(tab, w)
    settle()
    check("状态 done", tab.state == "done", tab.state)
    check("进度 100%", tab.progress.value() == 100 and "100%" in tab.lbl_progress.text())
    check("帧序 = 读版本 + 启动 + 3 包 + 执行 + 读版本 = 7",
          w.writes == 7 and [omd_of(f) for f in w.sent[1:2]] == [upg.OMD_START], w.writes)
    check("PIID 每帧自增（0..6）",
          [resp_apdu(f)[2] for f in w.sent] == [0, 1, 2, 3, 4, 5, 6],
          [resp_apdu(f)[2] for f in w.sent])
    check("末帧是读版本帧（升级完成后）", is_ver_frame(w.sent[-1]))
    check("结束后勾选框恢复可编辑",
          tab.chk_read_before.isEnabled() is True and tab.chk_read_after.isEnabled() is True)
    check("已确认字节 == 文件字节数", tab._confirmed_bytes == len(payload),
          f"{tab._confirmed_bytes} vs {len(payload)}")
    log = log_text(tab)
    check("日志含「升级完成后」的读版本明细（两次都成功）",
          log.count("→ 版本信息（升级前·通用）读取成功（6 项）") == 1
          and log.count("→ 版本信息（升级完成后·通用）读取成功（6 项）") == 1
          and sum(1 for l in log.splitlines() if "厂商代码" in l and "JCDZ" in l) == 2,
          [l for l in log.splitlines() if "版本信息" in l])
    check("执行升级已确认 → 进入「等待设备复位」而不是立刻读",
          "执行升级已确认，等待设备复位升级" in log, last_log(tab))
    check("展示区两栏各自留下结果（升级前 + 升级完成后）",
          "升级前 · 通用 ·" in panel_pre(tab) and "升级完成后 · 通用 ·" in panel_post(tab)
          and "厂商代码" in panel_pre(tab) and "厂商代码" in panel_post(tab),
          panel_pre(tab) + " / " + panel_post(tab))

    # 展示区只放**本轮**结果：`开始升级` 与 `清除` 都必须重置（不留上一轮残留误导现场判读）
    tab.btn_start.click()                    # 再开一轮（同一文件仍在）→ 复位
    settle()
    check("再次「开始升级」→ 两栏立即回到空态",
          panel_pre(tab) == "升级前：（未读取）"
          and panel_post(tab) == "升级完成后：（未读取）",
          (panel_pre(tab), panel_post(tab)))
    w.deliver(ver_ack_for(w.sent[-1]))       # 新一轮读版本成功 → 又有内容
    settle()
    check("新一轮读版本后「升级前」栏重新有内容（证明上面的「空态」不是恒真）",
          "升级前 · 通用 ·" in panel_pre(tab) and "厂商代码" in panel_pre(tab),
          panel_pre(tab))
    tab.btn_clear.click()
    settle()
    check("「清除」→ 两栏回到空态",
          panel_pre(tab) == "升级前：（未读取）"
          and panel_post(tab) == "升级完成后：（未读取）",
          (panel_pre(tab), panel_post(tab)))

    # 勾选状态持久化（落盘 → 新实例读回）
    check("落盘成功", tab._save_persisted() is True)
    tab2, _, _ = make_tab(fresh=False)
    check("新实例读回两个开关 = 勾选",
          tab2.chk_read_before.isChecked() is True and tab2.chk_read_after.isChecked() is True)
    tab.cleanup()
    tab2.cleanup()


def test_version_read_nonblocking():
    section("[18] 读版本失败**不阻断**升级（超时用尽 → 记日志继续）")
    payload = bytes(range(200))
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    tab.spin_block.setValue(100)
    tab.spin_retries.setValue(1)
    tab._on_file_selected(write_pkg(payload))
    tab.chk_read_before.setChecked(True)
    tab.chk_read_after.setChecked(True)
    tab.btn_start.click()
    settle()
    check("先发读版本帧", w.writes == 1 and is_ver_frame(w.sent[0]), w.writes)

    tab._on_timeout()                     # 第 1 次超时 → 重发（retries=1）
    settle()
    check("超时按既有口径重发（帧数 +1、PIID 自增）",
          w.writes == 2 and resp_apdu(w.sent[1])[2] == 1, w.writes)
    tab._on_timeout()                     # 用尽 → 不阻断
    settle()
    log = log_text(tab)
    check("日志写明读版本未成功 + 继续升级", "读版本信息未成功" in log
          and "继续升级流程" in log, last_log(tab))
    check("升级继续：第 3 帧是启动传输（不是失败停住）",
          w.writes == 3 and omd_of(w.sent[2]) == upg.OMD_START and tab.state == "starting",
          f"{w.writes} / {tab.state} / {[omd_of(f) for f in w.sent]}")
    check("全过程没有失败态弹框路径", tab.state != "failed", tab.state)
    # 失败也要在展示区**说出来**（PRD：未读到 → `—— 未读到：<原因>`；不是留空让人以为没读）
    check("读版本失败 → 展示区该栏写明未读到的原因",
          "升级前 · 通用 ·" in panel_pre(tab) and "未读到：" in panel_pre(tab)
          and "3000ms" in panel_pre(tab), panel_pre(tab))
    check("失败的一栏不是空态、也未串到另一栏",
          panel_post(tab) == "升级完成后：（未读取）", panel_post(tab))

    for _ in range(20):                   # 走完 启动 + 2 包 + 执行 + 等待复位 + 读版本(超时)
        settle()
        if tab.state in ("done", "failed", "aborted") or not w.sent:
            break
        if tab._phase == upg_ui.PHASE_WAIT_RESET:
            tab._end_reset_wait()         # 快进倒计时（本用例只关心「读失败不阻断」）
            continue
        if tab._phase in upg_ui.VER_PHASES:
            tab._on_timeout()             # 升级后读版本同样超时 → 仍不阻断
            continue
        w.deliver(ack_for(w.sent[-1]))
    settle()
    check("升级本身照常完成（done，进度 100%）",
          tab.state == "done" and tab.progress.value() == 100, tab.state)
    check("已确认字节 == 文件字节数（读版本失败不影响写文件）",
          tab._confirmed_bytes == len(payload), tab._confirmed_bytes)
    log = log_text(tab)
    check("升级后读版本失败也记日志并正常收尾",
          "升级流程已结束" in log and "读版本信息未成功" in log, last_log(tab))
    check("成功收尾文案说明读版本未成功",
          "读版本信息未成功，原因见日志" in log, last_log(tab))
    # 第二次（升级完成后）读版本失败**不得**把第一栏的内容冲掉 —— 两栏各写各的
    check("升级完成后读版本失败也写进该栏（原因），且没覆盖「升级前」栏",
          "升级完成后 · 通用 ·" in panel_post(tab) and "未读到：" in panel_post(tab)
          and "升级前 · 通用 ·" in panel_pre(tab) and "未读到：" in panel_pre(tab),
          (panel_pre(tab), panel_post(tab)))
    tab.cleanup()


def test_version_read_mismatch_retries():
    section("[19] 读版本响应不对（DAR≠0 / OAD 不符）按重试处理")
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    tab.spin_block.setValue(100)
    tab.spin_retries.setValue(2)
    tab._on_file_selected(write_pkg(bytes(range(100))))
    tab.chk_read_before.setChecked(True)
    tab.btn_start.click()
    settle()

    w.deliver(ver_ack_for(w.sent[-1], dar=3, tag=b"\x00"))     # 设备回「拒绝读写」
    settle()
    log = log_text(tab)
    check("DAR=3 → 日志给 DAR 说明并按重试重发",
          "DAR=3" in log and "拒绝读写" in log and w.writes == 2, last_log(tab))
    check("重发的仍是读版本帧", is_ver_frame(w.sent[-1]))

    w.deliver(ver_ack_for(w.sent[-1], oad=bytes.fromhex("43000400")))   # OAD 不符
    settle()
    check("OAD 不符 → 忽略并继续等（不计确认、不再重发）",
          "忽略" in log_text(tab) and w.writes == 2, last_log(tab))

    w.deliver(ver_ack_for(w.sent[-1]))                        # 正确响应
    settle()
    check("正确响应到达 → 推进到启动传输",
          w.writes == 3 and omd_of(w.sent[-1]) == upg.OMD_START and tab._phase == "start",
          f"{w.writes} / {tab._phase}")
    tab._on_abort()
    tab.cleanup()


def test_version_read_target_select():
    section("[20] 「读版本内容」可选：通用 43000300 / 厂家扩展内部版本 FF100400")
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    check("下拉存在且默认「通用版本信息」",
          tab.combo_read_target.count() == 2 and tab._read_target_key() == "common"
          and "43000300" in tab.combo_read_target.currentText(),
          tab.combo_read_target.currentText())
    items = [(tab.combo_read_target.itemData(i), tab.combo_read_target.itemText(i))
             for i in range(2)]
    check("两项的键与 OAD 文案分别对应 43000300 / FF100400",
          [k for k, _t in items] == ["common", "internal"]
          and "43000300" in items[0][1] and "FF100400" in items[1][1],
          items)
    upg_mod = tab._upgrade_module()
    check("页面把「通用/内部」映射到协议模块的两个 OAD 常量（唯一来源）",
          tab._read_oad(upg_mod) == upg_mod.OAD_VERSION
          and upg_mod.OAD_INTERNAL_VERSION == INT_OAD)

    # 切到内部版本 + 勾选前后读版本
    tab.spin_block.setValue(100)
    tab._on_file_selected(write_pkg(bytes(range(100))))          # 1 包
    tab.combo_read_target.setCurrentIndex(1)
    tab.chk_read_before.setChecked(True)
    tab.chk_read_after.setChecked(True)
    tab.btn_start.click()
    settle()
    check("第一帧就是内部版本读命令（APDU OAD=FF100400）",
          w.writes == 1 and is_ver_frame(w.sent[0], INT_OAD), hexs_or_none(w, 0))
    check("开始日志写明读版本内容 = 内部版本",
          "读版本内容=内部版本" in log_text(tab), last_log(tab))

    # 互斥：设备若回的是**通用版本**的响应，必须不认（否则「选择」形同虚设）
    w.deliver(ver_ack_for(w.sent[-1], oad=upg_mod.OAD_VERSION))
    settle()
    check("通用版本响应喂给内部版本读取 ⇒ 忽略（OAD 不符）、不推进",
          w.writes == 1 and tab._phase == "ver_pre", f"{w.writes} / {tab._phase}")
    check("忽略原因写进日志", "OAD 不符" in log_text(tab), last_log(tab))

    # 正确的内部版本响应（**现场实帧**，带 4 字节 FE 前导）→ 逐字段明细 + 展示区
    w.deliver(REAL_INT_RESP)
    settle()
    log = log_text(tab)
    lines = log.splitlines()
    rx_idx = next((i for i, l in enumerate(lines)
                   if l.startswith("[RX]") and "68 47 00 C3" in l), -1)
    check("现场帧（带 FE 前导）被当作一帧收下并单独成行", rx_idx >= 0, lines[-4:])
    check("帧行下一行是内部版本的标签行（明细在帧**下面**，不是帧尾）",
          rx_idx >= 0 and lines[rx_idx + 1] == "  → 版本信息（升级前·内部）读取成功（6 项）",
          lines[rx_idx + 1:rx_idx + 2])
    detail = lines[rx_idx + 2:rx_idx + 8] if rx_idx >= 0 else []
    check("内部版本 6 项逐字段命名解析（表191 名字 + YYMMDD 补全）",
          len(detail) == 6 and all(
              d.strip().startswith(name) and f"= {value}" in d
              for d, (name, value) in zip(detail, REAL_INT_FIELDS)), detail)
    check("明细行带原始字节", all("[" in d and "]" in d for d in detail), detail)
    check("展示区（升级前栏）显示内部版本 6 项",
          "升级前 · 内部 ·" in panel_pre(tab) and all(
              name in panel_pre(tab) and value in panel_pre(tab)
              for name, value in REAL_INT_FIELDS), panel_pre(tab))
    check("推进到启动传输", w.writes == 2 and omd_of(w.sent[1]) == upg.OMD_START, w.writes)

    # 传输中「读版本内容」也被冻结
    check("传输中「读版本内容」下拉被冻结", tab.combo_read_target.isEnabled() is False)
    run_to_end(tab, w)
    settle()
    check("全过程完成（done）", tab.state == "done" and tab.progress.value() == 100, tab.state)
    check("升级后那一帧同样是内部版本读命令",
          is_ver_frame(w.sent[-1], INT_OAD) and w.writes == 5, f"{w.writes}")
    check("升级后版本内容也标「·内部」",
          "→ 版本信息（升级完成后·内部）读取成功（6 项）" in log_text(tab),
          [l for l in log_text(tab).splitlines() if "版本信息" in l])
    check("结束后下拉恢复可编辑", tab.combo_read_target.isEnabled() is True)

    # 选择持久化
    check("落盘成功", tab._save_persisted() is True)
    tab2, _, _ = make_tab(fresh=False)
    check("新实例读回「内部版本」选择",
          tab2._read_target_key() == "internal"
          and tab2.combo_read_target.currentIndex() == 1,
          tab2.combo_read_target.currentText())
    tab.cleanup()
    tab2.cleanup()


def hexs_or_none(w, i):
    """调试细节：第 i 帧的 APDU hex（越界给空串，避免断言失败时先抛异常）。"""
    try:
        return resp_apdu(w.sent[i]).hex(" ").upper()
    except Exception:
        return ""


def test_version_read_single_value_fallback():
    section("[21] 非结构版本的兜底解析（单个 visible-string → 一行「数据」）")
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    tab.spin_block.setValue(100)
    tab._on_file_selected(write_pkg(bytes(range(100))))
    tab.combo_read_target.setCurrentIndex(1)                  # 内部版本
    tab.chk_read_before.setChecked(True)
    tab.btn_start.click()
    settle()
    text = "V1.0.3-INT"
    w.deliver(ver_ack_for(w.sent[-1], raw_data=visible_string(text)))
    settle()
    log = log_text(tab)
    check("非结构响应 → 标签行「读取成功（1 项）」",
          "→ 版本信息（升级前·内部）读取成功（1 项）" in log,
          [l for l in log.splitlines() if "版本信息" in l])
    check("兜底行名「数据」+ 值 + 原始字节",
          any(l.strip().startswith("数据") and f"= {text}" in l and "[0A" in l
              for l in log.splitlines()), log.splitlines()[-4:])
    check("展示区同样兜底显示（不空、不抛）",
          "升级前 · 内部 ·" in panel_pre(tab) and text in panel_pre(tab), panel_pre(tab))
    check("流程照常推进到启动传输",
          w.writes == 2 and omd_of(w.sent[1]) == upg.OMD_START, w.writes)
    tab._on_abort()
    tab.cleanup()


def test_reset_wait_before_post_read():
    section("[22] 「升级完成后读版本」前的等设备复位（默认 10 秒、可设、不勾自动执行也读）")
    payload = bytes(range(200))                       # 每包 100 → 2 包
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    check("等待秒数 spin 默认 10、范围 0~600",
          tab.spin_read_after_delay.value() == 10
          and (tab.spin_read_after_delay.minimum(), tab.spin_read_after_delay.maximum()) == (0, 600),
          (tab.spin_read_after_delay.value(), tab.spin_read_after_delay.minimum(),
           tab.spin_read_after_delay.maximum()))
    tab.spin_block.setValue(100)
    tab._on_file_selected(write_pkg(payload))
    tab.chk_auto_exec.setChecked(False)               # 关键：**不发**执行升级命令
    tab.chk_read_after.setChecked(True)
    tab.spin_read_after_delay.setValue(10)
    tab.btn_start.click()
    settle()
    check("不勾自动执行 ⇒ 流程是 启动 + 2 包（无执行升级帧）",
          w.writes == 1 and omd_of(w.sent[0]) == upg.OMD_START, w.writes)
    w.deliver(ack_for(w.sent[-1]))                    # 启动传输 → 第 1 包
    settle()
    w.deliver(ack_for(w.sent[-1]))                    # 第 1 包 → 第 2 包（末包）
    settle()
    w.deliver(ack_for(w.sent[-1]))                    # 末包确认 → 进等待
    settle()
    check("末包确认后进入「等待设备复位」，且**一帧都没新发**",
          tab._phase == "wait_reset" and w.writes == 3, f"{tab._phase} / {w.writes}")
    check("等待定时器在跑、剩余 10 秒",
          tab._reset_timer.isActive() and tab._reset_left == 10, tab._reset_left)
    check("状态行显示倒计时",
          "等待设备复位（剩余 10 秒）" in tab.lbl_status.text(), tab.lbl_status.text())
    check("日志写明等待（可查是等多久）",
          "等待设备复位升级：10 秒后再读版本信息" in log_text(tab), last_log(tab))
    check("未发执行升级 ⇒ 没有执行升级帧", all(omd_of(f) != upg.OMD_EXEC for f in w.sent))
    check("等待期间「升级后等待(s)」被冻结（传输中改它会让在飞计划不同源）",
          tab.spin_read_after_delay.isEnabled() is False,
          tab.spin_read_after_delay.isEnabled())

    tab._on_reset_wait_tick()                          # 模拟 1 秒
    settle()
    check("每秒递减 + 状态行跟着走",
          tab._reset_left == 9 and "剩余 9 秒" in tab.lbl_status.text(),
          (tab._reset_left, tab.lbl_status.text()))
    n = w.writes
    w.deliver(ack_for(w.sent[-1]))                     # 等待期间来的帧 ⇒ 不当确认
    settle()
    check("等待期间收到的帧被忽略（不当确认、不推进、零新帧）",
          "忽略（等待设备复位中）" in log_text(tab) and w.writes == n
          and tab._phase == "wait_reset", f"{w.writes} / {tab._phase}")

    # 复位期设备可能吐「别的方法 + 失败结果」的杂帧。判别性最强的一例是 **OMD=执行升级 +
    # DAR≠0**：等待阶段 `_expected_omd` 落到 EXEC，判定若放行就会按「DAR≠0 → 重试」**凭空
    # 发出一帧执行升级**（本轮用户根本没勾自动执行）。
    w.deliver(ack_with_omd(w.sent[-1], upg.OMD_EXEC, 5))
    settle()
    check("等待期间收到「执行升级 OMD + DAR≠0」杂帧也不发执行升级帧",
          w.writes == n and tab._phase == "wait_reset" and tab._reset_left == 9,
          f"{w.writes} / {tab._phase} / {tab._reset_left}")

    # 超时槽（`_wait_timer`）万一在等待期被触发：不许重发（重发的是 EXEC 帧）、不许判失败
    tab._on_timeout()
    settle()
    check("等待期间 _on_timeout() 不重发、不判失败（仍在等）",
          w.writes == n and tab._phase == "wait_reset" and tab.state == "finishing"
          and tab._reset_timer.isActive(),
          f"{w.writes} / {tab._phase} / {tab.state}")
    check("这类超时被记进日志（现场可查）",
          "忽略超时/重试判定" in log_text(tab), last_log(tab))

    for _ in range(9):                                 # 走完剩余 9 秒
        tab._on_reset_wait_tick()
    settle()
    check("倒计时归零 ⇒ 自动发出「升级完成后读版本」帧",
          w.writes == n + 1 and is_ver_frame(w.sent[-1]) and tab._phase == "ver_post",
          f"{w.writes} / {tab._phase}")
    check("等待结束有日志", "等待结束，开始读版本信息（升级完成后）" in log_text(tab),
          last_log(tab))
    check("定时器已停", tab._reset_timer.isActive() is False)

    n_zero = w.writes
    for _ in range(5):                                 # 归零后残留的 tick（诈尸）不许复燃
        tab._on_reset_wait_tick()
    settle()
    check("归零后再跳 tick 不会重复发读版本帧",
          w.writes == n_zero and tab._phase == "ver_post", f"{w.writes} / {n_zero}")

    w.deliver(ver_ack_for(w.sent[-1]))
    settle()
    log = log_text(tab)
    check("读完后正常收尾（done / 100%）",
          tab.state == "done" and tab.progress.value() == 100, tab.state)
    check("收尾文案说明「未发执行升级 + 已读升级后版本」",
          "文件传输完成（未发送执行升级命令，已读升级后版本信息）" in log, last_log(tab))
    check("展示区「升级完成后」栏有内容",
          "升级完成后 · 内部 ·" in panel_post(tab) or "升级完成后 · 通用 ·" in panel_post(tab),
          panel_post(tab))
    check("结束后「升级后等待(s)」恢复可编辑",
          tab.spin_read_after_delay.isEnabled() is True)
    tab.cleanup()

    # ② 等待 = 0 ⇒ 不发定时器、立即读
    w2 = FakeSerialWorker()
    tab2, _, _ = make_tab(w2)
    tab2.spin_block.setValue(100)
    tab2._on_file_selected(write_pkg(bytes(range(100))))
    tab2.chk_auto_exec.setChecked(True)
    tab2.chk_read_after.setChecked(True)
    tab2.spin_read_after_delay.setValue(0)
    tab2.btn_start.click()
    settle()
    w2.deliver(ack_for(w2.sent[-1]))                   # 启动 → 1 包
    settle()
    w2.deliver(ack_for(w2.sent[-1]))                   # 末包 → 执行升级
    settle()
    check("勾了自动执行 ⇒ 执行升级帧已发", omd_of(w2.sent[-1]) == upg.OMD_EXEC)
    w2.deliver(ack_for(w2.sent[-1]))                   # 执行升级确认 → 等待 0 秒
    settle()
    check("等待 0 秒 ⇒ 不发定时器、立即发读版本帧",
          tab2._reset_timer.isActive() is False and is_ver_frame(w2.sent[-1])
          and tab2._phase == "ver_post", f"{tab2._phase} / {tab2._reset_timer.isActive()}")
    check("日志写明「等待设为 0 秒」",
          "等待设为 0 秒 ⇒ 立即读版本信息" in log_text(tab2), last_log(tab2))
    w2.deliver(ver_ack_for(w2.sent[-1]))
    settle()
    check("勾自动执行 + 读后版本 ⇒ 收尾文案是「升级流程完成（已读升级后版本信息）」",
          tab2.state == "done" and "升级流程完成（已读升级后版本信息）" in log_text(tab2),
          last_log(tab2))
    tab2.cleanup()

    # ③ 等待中「中止」⇒ aborted、定时器停、零新帧
    w3 = FakeSerialWorker()
    tab3, _, _ = make_tab(w3)
    tab3.spin_block.setValue(100)
    tab3._on_file_selected(write_pkg(bytes(range(100))))
    tab3.chk_auto_exec.setChecked(False)
    tab3.chk_read_after.setChecked(True)
    tab3.btn_start.click()
    settle()
    w3.deliver(ack_for(w3.sent[-1]))                   # 启动 → 包
    settle()
    w3.deliver(ack_for(w3.sent[-1]))                   # 末包 → 等待
    settle()
    n3 = w3.writes
    tab3._on_abort()
    settle()
    check("等待中中止 ⇒ aborted + 定时器停 + 零新帧",
          tab3.state == "aborted" and tab3._reset_timer.isActive() is False
          and w3.writes == n3, f"{tab3.state} / {w3.writes}")
    check("中止把剩余秒数一并清零（不留下一轮）", tab3._reset_left == 0, tab3._reset_left)
    check("中止日志写明停在「等待设备复位」",
          "等待设备复位（剩余" in log_text(tab3), last_log(tab3))
    for _ in range(12):                                # 中止后即使定时器残留再跳也不发
        tab3._on_reset_wait_tick()
    settle()
    check("中止后定时器 tick 不复活流程", w3.writes == n3 and tab3.state == "aborted")
    tab3.cleanup()

    # ④ 等待中「清除」⇒ idle、定时器停、零新帧
    w4 = FakeSerialWorker()
    tab4, _, _ = make_tab(w4)
    tab4.spin_block.setValue(100)
    tab4._on_file_selected(write_pkg(bytes(range(100))))
    tab4.chk_auto_exec.setChecked(False)
    tab4.chk_read_after.setChecked(True)
    tab4.btn_start.click()
    settle()
    w4.deliver(ack_for(w4.sent[-1]))
    settle()
    w4.deliver(ack_for(w4.sent[-1]))
    settle()
    n4 = w4.writes
    tab4.btn_clear.click()
    settle()
    check("等待中清除 ⇒ idle + 定时器停 + 零新帧",
          tab4.state == "idle" and tab4._reset_timer.isActive() is False
          and w4.writes == n4, f"{tab4.state} / {w4.writes}")
    tab4.cleanup()

    # ⑤ 落盘/读回等待秒数
    tab5, _, _ = make_tab()
    tab5.spin_read_after_delay.setValue(37)
    check("落盘成功", tab5._save_persisted() is True)
    tab6, _, _ = make_tab(fresh=False)
    check("新实例读回等待秒数 = 37", tab6.spin_read_after_delay.value() == 37,
          tab6.spin_read_after_delay.value())
    tab5.cleanup()
    tab6.cleanup()

    # ⑥ 真实事件循环（**不手工 tick**）：证明 1 秒 QTimer 真在走、归零自动发帧、且不发第二帧。
    #    上面各段都靠手工 tick/快进：那样「定时器根本没启动/间隔写错」也能全绿 ⇒ 这里补真实时间。
    w_r = FakeSerialWorker()
    tab_r, _, _ = make_tab(w_r)
    tab_r.spin_block.setValue(100)
    tab_r._on_file_selected(write_pkg(bytes(range(100))))
    tab_r.chk_auto_exec.setChecked(False)
    tab_r.chk_read_after.setChecked(True)
    tab_r.spin_read_after_delay.setValue(2)             # 2 秒（真等，别用 10 秒拖慢套件）
    tab_r.btn_start.click()
    settle()
    w_r.deliver(ack_for(w_r.sent[-1]))                  # 启动 → 1 包
    settle()
    w_r.deliver(ack_for(w_r.sent[-1]))                  # 末包 → 进等待
    settle()
    n_r = w_r.writes
    seen = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < 4.0:
        settle()
        txt = tab_r.lbl_status.text()
        if not seen or seen[-1] != txt:
            seen.append(txt)
        if w_r.writes > n_r:
            break
        time.sleep(0.02)
    elapsed = time.monotonic() - t0
    check("真定时器每秒刷新状态行（看到「剩余 1 秒」）",
          any("剩余 1 秒" in s for s in seen), seen)
    check("真定时器约 2 秒后自动发出读版本帧（不靠手工 tick；≤3.5s）",
          w_r.writes == n_r + 1 and is_ver_frame(w_r.sent[-1]) and elapsed <= 3.5,
          f"{w_r.writes} / {elapsed:.2f}s")
    check("真定时器归零后已停", tab_r._reset_timer.isActive() is False)
    n_r2 = w_r.writes
    t1 = time.monotonic()
    while time.monotonic() - t1 < 1.4:                  # 再跨一个 tick 周期
        settle()
        time.sleep(0.02)
    check("发帧后再跨一个 tick 周期也不重复发（定时器不复活）",
          w_r.writes == n_r2 and tab_r._phase == "ver_post", f"{w_r.writes} / {n_r2}")
    w_r.deliver(ver_ack_for(w_r.sent[-1]))
    settle()
    check("真实事件循环这一轮正常收尾（done / 100%）",
          tab_r.state == "done" and tab_r.progress.value() == 100, tab_r.state)
    tab_r.cleanup()

    # ⑦ 连续两轮：第一轮「等待中清除」→ 残留 tick 不许影响第二轮（诈尸检查）
    w_two = FakeSerialWorker()
    tab_two, _, _ = make_tab(w_two)
    tab_two.spin_block.setValue(100)
    tab_two._on_file_selected(write_pkg(bytes(range(100))))
    tab_two.chk_auto_exec.setChecked(False)
    tab_two.chk_read_after.setChecked(True)
    tab_two.spin_read_after_delay.setValue(10)
    tab_two.btn_start.click()
    settle()
    w_two.deliver(ack_for(w_two.sent[-1]))              # 启动 → 1 包
    settle()
    w_two.deliver(ack_for(w_two.sent[-1]))              # 末包 → 等待
    settle()
    check("第一轮确实停在等待（前置成立，后面的复位断言才有意义）",
          tab_two._phase == "wait_reset" and tab_two._reset_left == 10,
          f"{tab_two._phase} / {tab_two._reset_left}")
    n_two = w_two.writes
    tab_two.btn_clear.click()                           # 等待中清除 ⇒ 本轮作废
    settle()
    check("清除把等待定时器与剩余秒数一并复位",
          tab_two._reset_timer.isActive() is False and tab_two._reset_left == 0,
          (tab_two._reset_timer.isActive(), tab_two._reset_left))
    for _ in range(5):                                  # 清除前已在队列里的残留 tick
        tab_two._on_reset_wait_tick()
    settle()
    check("清除后的残留 tick 一帧都不发、状态不变",
          w_two.writes == n_two and tab_two.state == "idle", f"{w_two.writes} / {tab_two.state}")
    tab_two.spin_read_after_delay.setValue(3)
    tab_two.btn_start.click()                           # 第二轮（同一文件仍在）
    settle()
    check("第二轮从头开始（启动传输帧，不是被上一轮尾巴带跑）",
          tab_two._phase == upg_ui.PHASE_START
          and omd_of(w_two.sent[-1]) == upg.OMD_START, tab_two._phase)
    run_to_end(tab_two, w_two)                          # 快进等待（⑥ 已用真实时间验过定时器）
    settle()
    check("第二轮跑完且只发了一帧读版本（升级完成后）",
          tab_two.state == "done"
          and sum(1 for f in w_two.sent[n_two:] if is_ver_frame(f)) == 1,
          f"{tab_two.state} / {[is_ver_frame(f) for f in w_two.sent[n_two:]]}")
    check("第二轮收尾文案正确（未发执行升级 + 已读升级后版本）",
          "文件传输完成（未发送执行升级命令，已读升级后版本信息）" in log_text(tab_two),
          last_log(tab_two))
    tab_two.cleanup()

    # ⑧ 等待中 cleanup()（关窗口）/ 收尾：定时器必须停
    #    注意**不**断言「残留手工 tick 之后 phase 不变」：`cleanup()` 对**任何**阶段都不动
    #    `_state/_phase`（普通传输中 cleanup 同样留着 transferring），等待期也不该例外；
    #    而且真定时器已被停 ⇒ 现实里不会有 tick 到达（手工调 slot 是测试专属路径）。
    w_cl = FakeSerialWorker()
    tab_cl, _, _ = make_tab(w_cl)
    tab_cl.spin_block.setValue(100)
    tab_cl._on_file_selected(write_pkg(bytes(range(100))))
    tab_cl.chk_auto_exec.setChecked(False)
    tab_cl.chk_read_after.setChecked(True)
    tab_cl.spin_read_after_delay.setValue(10)
    tab_cl.btn_start.click()
    settle()
    w_cl.deliver(ack_for(w_cl.sent[-1]))
    settle()
    w_cl.deliver(ack_for(w_cl.sent[-1]))
    settle()
    check("⑧ 前置：进了等待且倒计时在跑",
          tab_cl._phase == "wait_reset" and tab_cl._reset_timer.isActive(),
          (tab_cl._phase, tab_cl._reset_timer.isActive()))
    n_cl = w_cl.writes
    tab_cl.cleanup()
    check("cleanup() 停掉等待定时器", tab_cl._reset_timer.isActive() is False)
    settle()
    check("cleanup() 后不再往串口写（worker 已摘）", w_cl.writes == n_cl, w_cl.writes)


def check_cap_tight(tab, ble) -> tuple:
    """蓝牙上限的**性质**断言：`spin` 上限组出的整帧 ≤ 一次写上限，且再大 1 字节就超。

    不拿产品自己的计算结果当期望（那会变恒真）——直接量真实组帧长度。
    """
    cap = tab.spin_block.maximum()
    sa, ca, _err = tab._sa_ca()
    limit = ble.single_write_limit()
    ok = (len(upg.build_write_block(sa, ca, 0, 0, bytes(cap))) <= limit
          and len(upg.build_write_block(sa, ca, 0, 0, bytes(cap + 1))) > limit)
    return ok, (cap, limit)


def test_bluetooth_channel():
    section("[23] 发送通道：蓝牙（复用蓝牙页连接 + 按一次 ATT 写上限自动算每包上限）")

    # ① 默认串口：不碰蓝牙、上限仍是 8192
    tab, sw, _ = make_tab(FakeSerialWorker())
    check("默认通道 = 串口", tab._channel() == "serial" and tab.combo_channel.currentIndex() == 0,
          tab.combo_channel.currentText())
    check("串口通道下每包上限仍是 8192（蓝牙逻辑不介入）", tab.spin_block.maximum() == 8192,
          tab.spin_block.maximum())
    check("状态标签说明串口来源", "串口通道" in tab.lbl_channel_state.text()
          and "串口配置" in tab.lbl_channel_state.text(), tab.lbl_channel_state.text())
    tab.cleanup()

    # ② 蓝牙未连接：不设假上限 + 开始禁用 + 零发送
    ble = FakeBleWorker(connected=False)
    tab, _, _ = make_tab(FakeSerialWorker())
    tab.set_bluetooth_provider(lambda: ble)
    tab.combo_channel.setCurrentIndex(1)
    settle()
    check("未连接 ⇒ 不设人为上限（仍是 8192，不用假上限误导）",
          tab.spin_block.maximum() == 8192, tab.spin_block.maximum())
    check("状态标签指向蓝牙工具页", "未连接" in tab.lbl_channel_state.text()
          and "蓝牙工具" in tab.lbl_channel_state.text(), tab.lbl_channel_state.text())
    check("开始升级禁用且提示走蓝牙页",
          tab.btn_start.isEnabled() is False and "蓝牙工具" in tab.btn_start.toolTip(),
          tab.btn_start.toolTip())
    tab._on_start()                                          # 走处理函数级守卫（按钮已禁用，click 不触发）
    settle()
    check("未连接点开始 ⇒ 零字节发送 + 日志提示走蓝牙页",
          ble.sent == [] and "蓝牙通道未就绪" in log_text(tab), last_log(tab))

    # ③ MTU 未协商（ATT 默认 23）：仍不设上限 + 明确原因
    ble.set_connected(True)
    ble.set_mtu(23)
    settle()
    check("MTU 23 ⇒ 不设上限 + 原因写进标签",
          tab.spin_block.maximum() == 8192 and "未协商" in tab.lbl_channel_state.text(),
          (tab.spin_block.maximum(), tab.lbl_channel_state.text()))
    check("MTU 未协商时开始仍禁用", tab.btn_start.isEnabled() is False)
    n_sent = len(ble.sent)                       # 未协商时点开始：拦在**发帧之前**（零字节）
    tab._on_start()
    settle()
    check("MTU 未协商点开始 ⇒ 零字节发送", len(ble.sent) == n_sent == 0, len(ble.sent))

    # ④ MTU 协商到 512：上限自动收敛 + 值被夹 + 标签给出计算过程
    tab.spin_block.setValue(600)
    ble.set_mtu(512)
    settle()
    ok, detail = check_cap_tight(tab, ble)
    check("MTU 512 ⇒ 每包上限自动算好且「整帧 ≤ 一次写上限」紧致成立", ok, detail)
    check("原值 600 被自动收敛到上限", tab.spin_block.value() == tab.spin_block.maximum(),
          (tab.spin_block.value(), tab.spin_block.maximum()))
    label = tab.lbl_channel_state.text()
    check("标签写明 MTU / 一次写上限 / 每包最大",
          "MTU 512" in label and "509" in label and str(tab.spin_block.maximum()) in label, label)
    check("开始升级恢复可用", tab.btn_start.isEnabled() is True)

    # ⑤ 真跑一轮：TX 走「整帧一次写」，RX 走蓝牙通知信号
    tab.chk_auto_exec.setChecked(False)
    tab.chk_read_after.setChecked(True)
    tab.spin_read_after_delay.setValue(0)
    tab._on_file_selected(write_pkg(bytes(range(200))))     # 1 包
    tab.btn_start.click()
    settle()
    check("第一帧走蓝牙发出（启动传输）",
          len(ble.sent) == 1 and omd_of(ble.sent[0]) == upg.OMD_START, len(ble.sent))
    check("每一帧都是「整帧一次写」（single_write=True）",
          all(ble.single_flags) and ble.rejected == 0, ble.single_flags)
    check("写文件帧不超过一次写上限",
          len(ble.sent[-1]) <= ble.single_write_limit(), len(ble.sent[-1]))
    check("传输中通道下拉被冻结", tab.combo_channel.isEnabled() is False)
    run_to_end(tab, ble)                                    # 同形接口 ⇒ 直接复用
    settle()
    check("蓝牙通道整轮跑通（done / 100%）",
          tab.state == "done" and tab.progress.value() == 100, tab.state)
    check("收到蓝牙通知后能推进状态机（RX 走 notification_received）",
          len(ble.sent) >= 3 and tab._confirmed_bytes == 200,
          (len(ble.sent), tab._confirmed_bytes))
    check("结束后通道下拉恢复可编辑", tab.combo_channel.isEnabled() is True)
    check("单帧写被拒次数为 0（上限算准了，没有半途失败）", ble.rejected == 0)
    check("整轮每一帧都 ≤ 一次写上限（含写文件帧，不只是启动传输）",
          all(len(f) <= ble.single_write_limit() for f in ble.sent),
          ([len(f) for f in ble.sent], ble.single_write_limit()))

    # ⑥ 中途掉线 ⇒ 开始禁用；重连后又能开始
    ble.set_connected(False)
    settle()
    check("掉线 ⇒ 开始禁用 + 标签提示未连接",
          tab.btn_start.isEnabled() is False and "未连接" in tab.lbl_channel_state.text(),
          tab.lbl_channel_state.text())
    ble.set_connected(True)
    settle()
    check("重连 ⇒ 开始恢复可用（上限重算）", tab.btn_start.isEnabled() is True)
    ok2, detail2 = check_cap_tight(tab, ble)
    check("重连后上限仍然紧致（重算过）", ok2, detail2)

    # ⑦ MTU 变小 ⇒ 上限跟着变小、值再夹一次
    tab.spin_block.setValue(tab.spin_block.maximum())
    ble.set_mtu(200)
    settle()
    ok3, detail3 = check_cap_tight(tab, ble)
    check("MTU 200 ⇒ 上限下调且仍紧致", ok3 and tab.spin_block.maximum() < 475, detail3)
    check("值再次被夹到新上限", tab.spin_block.value() <= tab.spin_block.maximum())

    # ⑧ 通道选择持久化 + 切回串口恢复原上限
    check("落盘成功", tab._save_persisted() is True)
    tab2, _, _ = make_tab(fresh=False)
    check("新实例读回「蓝牙」通道",
          tab2._channel() == "bluetooth" and tab2.combo_channel.currentIndex() == 1,
          tab2.combo_channel.currentText())
    tab.combo_channel.setCurrentIndex(0)                    # 切回串口
    settle()
    check("切回串口 ⇒ 每包上限恢复 8192", tab.spin_block.maximum() == 8192,
          tab.spin_block.maximum())
    check("切回串口 ⇒ 状态标签切回串口来源",
          "串口通道" in tab.lbl_channel_state.text())
    n_ble = len(ble.sent)
    sw = tab._serial_worker
    tab.btn_start.click()
    settle()
    check("切回串口后发送走串口 worker（蓝牙不再收帧）",
          len(ble.sent) == n_ble and len(sw.sent) > 0, (len(ble.sent), len(sw.sent)))
    tab._on_abort()
    tab.cleanup()
    tab2.cleanup()


def test_bluetooth_channel_isolation():
    section("[24] 通道隔离：收发只认当前通道 + 蓝牙页后建/换线程也对得上")

    # ① 串口通道下：蓝牙页的连接状态与报错**不许**拨动本页按钮/标签/日志
    tab, sw, _ = make_tab(FakeSerialWorker(opened=False))
    ble = FakeBleWorker(mtu=512, connected=False)
    tab.set_bluetooth_provider(lambda: ble)
    ble.set_connected(True)                    # 蓝牙页自己连上了（与串口无关）
    settle()
    check("串口通道：蓝牙连上不启用「开始升级」（串口仍未开）",
          tab.btn_start.isEnabled() is False, tab.btn_start.isEnabled())
    check("串口通道：标签仍说串口未连接",
          "串口通道" in tab.lbl_channel_state.text()
          and "未连接" in tab.lbl_channel_state.text(), tab.lbl_channel_state.text())
    sw._open = True
    sw.connection_changed.emit(True)
    settle()
    check("串口通道：串口连接信号照旧驱动按钮", tab.btn_start.isEnabled() is True)
    ble.set_connected(False)                   # 蓝牙掉线（串口还开着）
    settle()
    check("串口通道：蓝牙掉线不误禁用按钮", tab.btn_start.isEnabled() is True)
    n_log = len(log_text(tab).splitlines())
    ble.error_occurred.emit("（蓝牙页自己的）写入失败")
    settle()
    check("串口通道：蓝牙页自己的报错不抄进本页日志",
          len(log_text(tab).splitlines()) == n_log, log_text(tab).splitlines()[n_log:])

    # ② RX 不跨通道（串口通道跑着 → 蓝牙通知里的确认一律不吃）
    tab.chk_auto_exec.setChecked(False)
    tab.chk_read_after.setChecked(False)
    start_transfer(tab, sw, bytes(range(120)), block=100)
    tx = sw.sent[-1]
    ble.deliver(ack_for(tx))                   # 本步确认**只**从蓝牙来
    settle()
    check("串口通道不吃蓝牙通知（没推进：仍 1 帧 / starting）",
          len(sw.sent) == 1 and tab.state == "starting", (len(sw.sent), tab.state))
    sw.deliver(ack_for(tx))                    # 真来源照旧有效
    settle()
    check("串口的确认照旧推进（2 帧 / transferring）",
          len(sw.sent) == 2 and tab.state == "transferring", (len(sw.sent), tab.state))
    tab._on_abort()
    tab.cleanup()

    # ③ RX 不跨通道（蓝牙通道跑着 → 串口数据不被当确认）
    tab2, sw2, _ = make_tab(FakeSerialWorker())
    ble2 = FakeBleWorker(mtu=512, connected=True)
    tab2.set_bluetooth_provider(lambda: ble2)
    tab2.combo_channel.setCurrentIndex(1)
    settle()
    tab2.chk_auto_exec.setChecked(False)
    tab2.chk_read_after.setChecked(False)
    tab2._on_file_selected(write_pkg(bytes(range(120))))
    tab2.btn_start.click()
    settle()
    n_ble = len(ble2.sent)
    sw2.deliver(ack_for(ble2.sent[-1]))        # 本步确认**只**从串口来
    settle()
    check("蓝牙通道不吃串口数据（没推进）",
          len(ble2.sent) == n_ble and tab2.state == "starting", (len(ble2.sent), tab2.state))
    ble2.deliver(ack_for(ble2.sent[-1]))
    settle()
    check("蓝牙的确认照旧推进", len(ble2.sent) == n_ble + 1 and tab2.state == "transferring",
          (len(ble2.sent), tab2.state))
    tab2._on_abort()
    tab2.cleanup()

    # ④ 蓝牙页后建：本页先落盘「蓝牙」，worker 之后才出现 → 切回本页（show）自动对上
    holder = {"w": None}
    tab3, _, _ = make_tab(None)
    tab3.set_bluetooth_provider(lambda: holder["w"])
    tab3.combo_channel.setCurrentIndex(1)
    settle()
    check("蓝牙页还没建 worker ⇒ 不设假上限 + 开始禁用",
          tab3.spin_block.maximum() == 8192 and tab3.btn_start.isEnabled() is False,
          (tab3.spin_block.maximum(), tab3.btn_start.isEnabled()))
    holder["w"] = FakeBleWorker(mtu=512, connected=True)
    tab3.show()                                # 用户从蓝牙页切回本页
    settle()
    ok, detail = check_cap_tight(tab3, holder["w"])
    check("切回本页即自动对上（上限算好 + 开始可用）",
          ok and tab3.btn_start.isEnabled() is True, detail)
    holder["w"].set_mtu(247)
    settle()
    check("对上之后 MTU 变化能实时重算（247 ⇒ 211）",
          tab3.spin_block.maximum() == 211, tab3.spin_block.maximum())
    tab3.hide()
    tab3.cleanup()

    # ⑤ 蓝牙页换线程（`set_bluetooth_worker`）：旧线程**不再**投到本页；cleanup 只断自己的槽
    wa, wb = FakeBleWorker(mtu=512, name="A"), FakeBleWorker(mtu=247, name="B")
    cur = {"w": wa}
    tab4, _, _ = make_tab(None)
    tab4.set_bluetooth_provider(lambda: cur["w"])
    tab4.combo_channel.setCurrentIndex(1)
    settle()
    check("绑定 A：标签写着 A 的 MTU", "A（MTU 512" in tab4.lbl_channel_state.text(),
          tab4.lbl_channel_state.text())
    cur["w"] = wb                              # 蓝牙页换了线程
    tab4._apply_block_limit()                  # 任一重算入口（SA 变 / 切回本页 / MTU 更新）
    settle()
    check("换线程后跟着换（标签换成 B）且旧线程已解绑",
          "B（MTU 247" in tab4.lbl_channel_state.text()
          and tab4._bt_worker is wb, tab4.lbl_channel_state.text())
    n4 = len(log_text(tab4).splitlines())
    wa.error_occurred.emit("旧线程的报错")
    settle()
    check("旧线程的报错不再投到本页（信号断干净）",
          len(log_text(tab4).splitlines()) == n4, log_text(tab4).splitlines()[n4:])
    wb.error_occurred.emit("新线程的报错")
    settle()
    check("新线程的报错进得来", "新线程的报错" in log_text(tab4))
    seen = []
    wb.notification_received.connect(lambda u, d: seen.append((u, d)))
    tab4.cleanup()
    n5 = len(log_text(tab4).splitlines())
    wb.error_occurred.emit("cleanup 之后")
    wb.deliver(b"\x68")
    settle()
    check("cleanup 后本页不再吃该线程（日志/缓冲都不动）",
          len(log_text(tab4).splitlines()) == n5 and len(tab4._rx_buf) == 0,
          log_text(tab4).splitlines()[n5:])
    check("cleanup 只断自己的槽：蓝牙页自己的槽照旧收到通知",
          len(seen) == 1, seen)
    tab4.hide()


def test_baud_boost():
    section("[25] 提升波特率：升级前发命令 → 主机切 115200 → 收尾切回 9600")
    payload = bytes(range(200))                        # 每包 100 → 2 包
    #: OMD=执行升级 + DAR≠0 的杂帧：判据若放行，会**凭空发一帧执行升级**（最强判别用例）
    EXEC_BAD = ack_with_omd(upg.build_write_block(upg.WILDCARD_SA, 0, 1, 0, b"AB"),
                            upg.OMD_EXEC, 5)

    check("源码切速只用 set_baudrate（不重开端口：open_port/configure 一个都不出现）",
          "set_baudrate" in SRC and ".open_port(" not in SRC and ".configure(" not in SRC)

    # ① 默认值 + 不勾就什么都不做
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    check("「提升波特率」默认不勾", tab.chk_boost_baud.isChecked() is False)
    check("「切换等待(ms)」默认 300、范围 0~10000",
          tab.spin_boost_wait.value() == 300
          and (tab.spin_boost_wait.minimum(), tab.spin_boost_wait.maximum()) == (0, 10000),
          (tab.spin_boost_wait.value(), tab.spin_boost_wait.minimum(),
           tab.spin_boost_wait.maximum()))
    tab.spin_block.setValue(100)
    tab._on_file_selected(write_pkg(payload))
    tab.btn_start.click()
    settle()
    check("不勾 ⇒ 第 1 帧直接是启动传输、零次切速",
          w.sent[0] != upg_ui.BAUD_BOOST_COMMAND and omd_of(w.sent[0]) == upg.OMD_START
          and w.baud_calls == [], (w.baud_calls, w.writes))
    check("不勾 ⇒ 开始日志写明提升波特率=否", "提升波特率=否" in log_text(tab))
    tab._on_abort()
    tab.cleanup()

    # ② 勾选：命令 → （留切换时间）→ 主机切速 → 才发 698 帧
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    tab.spin_block.setValue(100)
    tab._on_file_selected(write_pkg(payload))
    tab.chk_boost_baud.setChecked(True)
    tab.spin_boost_wait.setValue(400)
    tab.chk_read_after.setChecked(True)
    tab.spin_read_after_delay.setValue(0)              # 后版本立即读（本用例不空等 10 秒）
    tab.btn_start.click()
    settle()
    check("第 1 帧就是「提升波特率」命令（逐字节等于现场实帧）",
          w.writes == 1 and w.sent[0] == upg_ui.BAUD_BOOST_COMMAND,
          w.sent[0].hex(" ").upper())
    check("命令帧 31 字节、末字节 16H、长度域 = 整帧 − 2",
          len(upg_ui.BAUD_BOOST_COMMAND) == 31
          and upg_ui.BAUD_BOOST_COMMAND[-1] == 0x16
          and int.from_bytes(upg_ui.BAUD_BOOST_COMMAND[1:3], "little")
          == len(upg_ui.BAUD_BOOST_COMMAND) - 2,
          (len(upg_ui.BAUD_BOOST_COMMAND),
           int.from_bytes(upg_ui.BAUD_BOOST_COMMAND[1:3], "little")))
    check("阶段=baud_boost、状态 starting，且**还没**发任何 698 帧",
          tab._phase == "baud_boost" and tab.state == "starting", tab._phase)
    check("等待定时器在跑、主机速率**没动**（等待被真正遵守）",
          tab._boost_timer.isActive() and w.baud == 9600 and tab._boosted is False,
          (w.baud, tab._boosted))
    check("TX 日志标出「提升波特率命令」",
          "(提升波特率命令)" in tx_line(log_text(tab), "(提升波特率命令)"),
          tx_line(log_text(tab), "(提升波特率命令)"))
    check("开始日志写明提升波特率=是", "提升波特率=是" in log_text(tab))
    check("传输中勾选框/切换等待/通道一并冻结",
          tab.chk_boost_baud.isEnabled() is False
          and tab.spin_boost_wait.isEnabled() is False
          and tab.combo_channel.isEnabled() is False,
          (tab.chk_boost_baud.isEnabled(), tab.spin_boost_wait.isEnabled()))

    # 提升波特率期间：既没有在飞的 698 请求，任何回帧/超时都不成立
    n = w.writes
    w.deliver(EXEC_BAD)
    settle()
    check("提升波特率期间收到「执行升级 OMD + DAR≠0」杂帧 ⇒ 忽略（不凭空发执行升级帧）",
          w.writes == n and tab._phase == "baud_boost"
          and "忽略（提升波特率中" in log_text(tab), (w.writes, tab._phase))
    tab._on_timeout()
    settle()
    check("提升波特率期间 _on_timeout() 不重发、不判失败",
          w.writes == n and tab.state == "starting" and tab._phase == "baud_boost",
          (w.writes, tab.state))
    check("这类超时被记进日志（现场可查）",
          "提升波特率期间无在飞的请求 ⇒ 忽略超时/重试判定" in log_text(tab), last_log(tab))

    time.sleep(0.12)                                   # 400ms 未到
    settle()
    check("等待未满 400ms ⇒ 仍不切速率", w.baud == 9600 and tab._boosted is False,
          (w.baud, tab._boosted))
    time.sleep(0.35)                                   # 累计 > 400ms
    settle()
    check("到点 ⇒ 主机切到 115200（恰好一次）",
          w.baud == 115200 and w.baud_calls == [115200] and tab._boosted is True,
          (w.baud, w.baud_calls))
    check("切完立刻继续升级：下一帧是启动传输、PIID 从 0 起（命令帧不占 PIID）",
          w.writes == n + 1 and omd_of(w.sent[-1]) == upg.OMD_START
          and resp_apdu(w.sent[-1])[2] == 0 and tab._phase == "start",
          f"{w.writes} / {tab._phase} / {resp_apdu(w.sent[-1])[2]}")
    check("切速日志写明「切回时机」",
          "主机串口已切到 115200" in log_text(tab) and "先切回 9600" in log_text(tab)
          and "两种速率上各试一遍" in log_text(tab),
          last_log(tab))

    # ③ 写文件跑在高速率上；传完/等复位升级时才切回
    w.deliver(ack_for(w.sent[-1]))
    settle()
    w.deliver(ack_for(w.sent[-1]))
    settle()
    check("写文件期间没人提前切回去（仍 115200）",
          w.baud == 115200 and tab._boosted is True and tab._phase == "blocks",
          (w.baud, tab._phase))
    w.deliver(ack_for(w.sent[-1]))                     # 末包确认 → 执行升级帧
    settle()
    check("执行升级帧仍在 115200 发出（设备此刻还在高速率）",
          omd_of(w.sent[-1]) == upg.OMD_EXEC and w.baud == 115200, w.baud)
    w.deliver(ack_for(w.sent[-1]))                     # 执行升级确认 → 进「等设备复位」
    settle()
    check("传完 + 执行升级确认 ⇒ 已切回 9600（恰好一次）",
          w.baud == 9600 and w.baud_calls == [115200, 9600] and tab._boosted is False,
          (w.baud, w.baud_calls))
    check("切回日志写明原因（文件传输完成，等待设备升级）",
          "文件传输完成，等待设备升级：串口波特率已切回 9600" in log_text(tab), last_log(tab))
    check("升级后读版本帧发出时主机已在 9600（读得通才谈得上读）",
          is_ver_frame(w.sent[-1]) and w.baud == 9600, (w.baud, is_ver_frame(w.sent[-1])))
    w.deliver(ver_ack_for(w.sent[-1]))
    settle()
    check("收尾 done 且速率停在默认值",
          tab.state == "done" and w.baud == 9600, (tab.state, w.baud))
    tab.cleanup()
    check("cleanup 幂等且不再多切一次", w.baud_calls == [115200, 9600], w.baud_calls)

    # ④ 倒计时等待（delay=10）：切回发生在**进入等待那一刻**，不是等倒计时走完
    w2 = FakeSerialWorker()
    tab2, _, _ = make_tab(w2)
    tab2.spin_block.setValue(100)
    tab2._on_file_selected(write_pkg(payload))
    tab2.chk_boost_baud.setChecked(True)
    tab2.spin_boost_wait.setValue(0)                   # 0ms ⇒ 下一轮事件循环就切
    tab2.chk_read_after.setChecked(True)
    tab2.spin_read_after_delay.setValue(10)
    tab2.btn_start.click()
    settle()
    check("切换等待=0 ⇒ 不空等，命令发出后立刻切到 115200",
          w2.baud == 115200 and tab2._phase == "start", (w2.baud, tab2._phase))
    w2.deliver(ack_for(w2.sent[-1]))
    settle()
    w2.deliver(ack_for(w2.sent[-1]))
    settle()
    w2.deliver(ack_for(w2.sent[-1]))                   # 末包 → 执行升级帧
    settle()
    w2.deliver(ack_for(w2.sent[-1]))                   # 执行升级确认 → 等设备复位
    settle()
    check("进入「等待设备复位」的那一刻就已切回 9600（倒计时还没走）",
          tab2._phase == "wait_reset" and tab2._reset_left == 10 and w2.baud == 9600,
          (tab2._phase, tab2._reset_left, w2.baud))
    n2 = w2.writes
    check("等待期间一帧都没新发（命令1 + 启动1 + 2包 + 执行1 = 5，切速不带出流量）",
          n2 == 5, n2)
    tab2._end_reset_wait()                             # 快进倒计时
    settle()
    check("倒计时走完才发升级后读版本帧，且仍跑在 9600",
          w2.writes == n2 + 1 and is_ver_frame(w2.sent[-1]) and w2.baud == 9600,
          (w2.writes, w2.baud))
    w2.deliver(ver_ack_for(w2.sent[-1]))
    settle()
    check("正常收尾 done", tab2.state == "done", tab2.state)
    tab2.cleanup()

    # ⑤ 终态兜底：中止也要还回默认速率（不把共享串口留在 115200）
    w3 = FakeSerialWorker()
    tab3, _, _ = make_tab(w3)
    tab3.spin_block.setValue(100)
    tab3._on_file_selected(write_pkg(payload))
    tab3.chk_boost_baud.setChecked(True)
    tab3.spin_boost_wait.setValue(0)
    tab3.btn_start.click()
    settle()
    w3.deliver(ack_for(w3.sent[-1]))
    settle()
    check("前置：已提升且在传输中", w3.baud == 115200 and tab3.state == "transferring",
          (w3.baud, tab3.state))
    tab3.btn_abort.click()
    settle()
    check("中止 ⇒ 切回 9600 且状态 aborted",
          tab3.state == "aborted" and w3.baud == 9600 and tab3._boosted is False,
          (tab3.state, w3.baud))
    check("中止时的切回写进日志", "本轮已结束：串口波特率已切回 9600" in log_text(tab3),
          last_log(tab3))
    check("中止后勾选框解冻（可原地重跑）", tab3.chk_boost_baud.isEnabled() is True)
    tab3.cleanup()

    # ⑥ 切速失败 ⇒ 停下并说明（不蒙着头继续按旧速率发帧）
    w4 = FakeSerialWorker()
    tab4, _, _ = make_tab(w4)
    tab4.spin_block.setValue(100)
    tab4._on_file_selected(write_pkg(payload))
    tab4.chk_boost_baud.setChecked(True)
    tab4.spin_boost_wait.setValue(0)
    w4.fail_baud = True
    tab4.btn_start.click()
    settle()
    check("切速失败 ⇒ failed、只发了那条命令、日志给出原因",
          tab4.state == "failed" and w4.writes == 1
          and "切换波特率到 115200 失败" in log_text(tab4),
          (tab4.state, w4.writes, last_log(tab4)))
    check("切速失败不算「已提升」（不会去切回一个没切成的速率）",
          tab4._boosted is False and w4.baud_calls == [115200], w4.baud_calls)
    tab4.cleanup()

    # ⑦ 蓝牙通道：没有波特率这一说 ⇒ 置灰 + 跳过 + 只记日志，不动串口速率
    w5 = FakeSerialWorker()
    bt = FakeBleWorker()
    tab5, _, _ = make_tab(w5)
    tab5.set_bluetooth_provider(lambda: bt)
    tab5.spin_block.setValue(100)
    tab5._on_file_selected(write_pkg(payload))
    tab5.chk_boost_baud.setChecked(True)
    tab5.combo_channel.setCurrentIndex(1)
    settle()
    check("蓝牙通道下「提升波特率」置灰", tab5.chk_boost_baud.isEnabled() is False)
    tab5.btn_start.click()
    settle()
    check("蓝牙通道下不发命令、不动串口速率，升级照常从启动传输开始",
          upg_ui.BAUD_BOOST_COMMAND not in w5.sent and w5.baud_calls == []
          and len(bt.sent) == 1 and omd_of(bytes(bt.sent[-1])) == upg.OMD_START,
          (w5.writes, len(bt.sent)))
    check("跳过这件事写进日志（不静默）",
          "蓝牙通道不支持「提升波特率」" in log_text(tab5), last_log(tab5))
    tab5._on_abort()
    tab5.cleanup()

    # ⑧ cleanup（页面被拆掉）也还回默认速率 + 等待中的切速作废
    w6 = FakeSerialWorker()
    tab6, _, _ = make_tab(w6)
    tab6.spin_block.setValue(100)
    tab6._on_file_selected(write_pkg(payload))
    tab6.chk_boost_baud.setChecked(True)
    tab6.spin_boost_wait.setValue(0)
    tab6.btn_start.click()
    settle()
    check("前置：已切到 115200", w6.baud == 115200, w6.baud)
    tab6.cleanup()
    check("页面关闭 ⇒ 切回 9600", w6.baud == 9600 and tab6._boosted is False, w6.baud)

    w7 = FakeSerialWorker()
    tab7, _, _ = make_tab(w7)
    tab7.chk_boost_baud.setChecked(True)
    tab7.spin_boost_wait.setValue(600)
    tab7.spin_block.setValue(100)
    tab7._on_file_selected(write_pkg(payload))
    tab7.btn_start.click()
    settle()
    tab7.cleanup()                                     # 还在「等设备切速」时把页面拆掉
    check("页面关闭时等待中的切速作废（定时器已停）", tab7._boost_timer.isActive() is False)
    time.sleep(0.7)
    settle()
    check("拆掉后即使等满了也不动共享串口速率",
          w7.baud == 9600 and w7.baud_calls == [], (w7.baud, w7.baud_calls))

    # ⑨ 配置持久化往返
    cfg_path = os.path.join(str(SANDBOX), upg_ui.CONFIG_NAME)
    if os.path.exists(cfg_path):
        os.remove(cfg_path)
    t8, _, _ = make_tab(fresh=False)
    t8.chk_boost_baud.setChecked(True)
    t8.spin_boost_wait.setValue(1200)
    check("落盘成功", t8._save_persisted() is True)
    t8.cleanup()
    t9, _, _ = make_tab(fresh=False)
    check("读回 boost_baud / boost_wait_ms",
          t9.chk_boost_baud.isChecked() is True and t9.spin_boost_wait.value() == 1200,
          (t9.chk_boost_baud.isChecked(), t9.spin_boost_wait.value()))
    t9.cleanup()
    with open(cfg_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"boost_baud": False, "boost_wait_ms": "abc"}))
    t10, _, _ = make_tab(fresh=False)
    check("boost_wait_ms 非数 ⇒ 回落默认 300（与每包字节数/等待秒数同一口径）",
          t10.chk_boost_baud.isChecked() is False and t10.spin_boost_wait.value() == 300,
          (t10.chk_boost_baud.isChecked(), t10.spin_boost_wait.value()))
    t10.cleanup()
    with open(cfg_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"boost_wait_ms": 999999}))
    t11, _, _ = make_tab(fresh=False)
    check("boost_wait_ms 越界 ⇒ 回落默认 300，控件仍夹在 0~10000 内",
          t11.spin_boost_wait.value() == 300
          and t11.spin_boost_wait.maximum() == 10000, t11.spin_boost_wait.value())
    t11.cleanup()
    if os.path.exists(cfg_path):
        os.remove(cfg_path)


def _prep_boosted_tab(payload: bytes = None):
    """公共前置：勾「提升波特率」+ 勾「升级后读版本」(立即读) + 每种速率只试 1 次。

    `spin_retries=0` 是为了让「一种速率用尽重试」= **一次** `_on_timeout()`，用例可逐次
    驱动到「9600 失败」「115200 也失败」两个节点，不必等真实计时。
    """
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    tab.spin_block.setValue(100)
    tab._on_file_selected(
        write_pkg(payload if payload is not None else bytes(range(200))))   # 每包 100 → 2 包
    tab.chk_boost_baud.setChecked(True)
    tab.spin_boost_wait.setValue(0)
    tab.chk_read_after.setChecked(True)
    tab.spin_read_after_delay.setValue(0)      # 0 = 立即读，跳过真实 10 秒倒计时
    tab.spin_retries.setValue(0)
    return tab, w


def _run_to_post_read_frame(tab, w, guard: int = 8) -> None:
    """点「开始升级」→ 逐帧喂确认 → 推到**升级后读版本帧已发出**（phase == ver_post）。

    覆盖「提升波特率命令(不喂确认) → 启动传输 → 2 包 → 执行升级 → 等复位(0s)」。
    """
    tab.btn_start.click()
    settle()
    for _ in range(guard):
        if tab._phase == "ver_post":
            return
        w.deliver(ack_for(w.sent[-1]))
        settle()
    raise AssertionError(f"没推到升级后读版本：phase={tab._phase} writes={w.writes}")


def test_post_read_dual_baud():
    section("[26] 升级后读版本的双波特率尝试（设备升级失败可能仍停在 115200）")

    # ① 前置与「切回时机」：提升过 + 传完 ⇒ 9600 先读（读不到再换 115200）
    tab, w = _prep_boosted_tab()
    _run_to_post_read_frame(tab, w)
    check("前置：升级后读版本帧已在 9600 发出（phase=ver_post）",
          tab._phase == "ver_post" and is_ver_frame(w.sent[-1]) and w.baud == 9600
          and w.baud_calls == [115200, 9600],
          (tab._phase, w.baud_calls))
    check("前置：本轮计划是「9600 → 115200」两种速率",
          tab._post_bauds == [9600, 115200] and tab._post_baud_idx == 0,
          (tab._post_bauds, tab._post_baud_idx))
    check("前置：提升过这件事被黏性记住（切回后仍是 True）",
          tab._boost_used is True and tab._boosted is False,
          (tab._boost_used, tab._boosted))

    # ② 9600 读不到 ⇒ 切 115200 重发（不是判失败）
    n = w.writes
    piid_before = resp_apdu(w.sent[-1])[2]
    tab._on_timeout()
    settle()
    check("9600 读不到 ⇒ 自动切到 115200 并把该步重发一次",
          w.baud == 115200 and w.baud_calls == [115200, 9600, 115200]
          and w.writes == n + 1 and tab._phase == "ver_post",
          (w.baud, w.baud_calls, w.writes, tab._phase))
    check("重发帧仍是读版本帧、PIID 自增（不是其它步骤的帧）",
          is_ver_frame(w.sent[-1])
          and resp_apdu(w.sent[-1])[2] == (piid_before + 1) & 0x7F,
          (hexs_or_none(w, -1), piid_before))
    check("换速率不改「已提升」标记（收尾仍要带回来）", tab._boosted is True)
    check("换速率的前因后果写进日志（不静默）",
          "9600 波特率下读不到升级后版本信息" in log_text(tab)
          and "已切到 115200 再试一次" in log_text(tab), last_log(tab))

    # ③ 在 115200 读到 ⇒ 照常成功收尾，且**速率被带回来**
    w.deliver(ver_ack_for(w.sent[-1]))
    settle()
    check("115200 下读到 ⇒ 状态 done、进度 100%",
          tab.state == "done" and tab.progress.value() == 100, tab.state)
    check("成功读到的内容进了「升级完成后」展示区（不是只写日志）",
          "升级完成后 · 通用 ·" in panel_post(tab)
          and "厂商代码" in panel_post(tab), panel_post(tab))
    check("收尾把端口带回 9600（绝不留 115200）",
          w.baud == 9600 and tab._boosted is False
          and w.baud_calls == [115200, 9600, 115200, 9600],
          (w.baud, w.baud_calls))
    tab.cleanup()

    # ④ 两种速率都读不到 ⇒ 才算读不到（原因里同时给出两个速率）
    tab2, w2 = _prep_boosted_tab()
    _run_to_post_read_frame(tab2, w2)
    tab2._on_timeout()                       # 9600 用尽
    settle()
    n2 = w2.writes
    tab2._on_timeout()                       # 115200 用尽 ⇒ 没有下一种速率了
    settle()
    check("两种速率都读不到 ⇒ 不再换速率、不再发帧",
          w2.writes == n2 and w2.baud_calls == [115200, 9600, 115200, 9600],
          (w2.writes, w2.baud_calls))
    check("升级本身照常收尾（读版本失败不阻断、状态 done）",
          tab2.state == "done" and tab2.progress.value() == 100, tab2.state)
    check("失败原因里**两个速率都写明**（现场能看出都试过了）",
          "9600 波特率下" in panel_post(tab2) and "115200 波特率下" in panel_post(tab2),
          panel_post(tab2))
    check("日志明说两种波特率都读不到",
          "9600 / 115200 两种波特率都读不到升级后版本信息" in log_text(tab2), last_log(tab2))
    check("收尾仍把端口带回 9600", w2.baud == 9600 and tab2._boosted is False, w2.baud)
    tab2.cleanup()

    # ⑤ 没勾提升波特率 ⇒ 单速率、零切速（与旧版行为逐字相同：设备一直跑在默认速率）
    w3 = FakeSerialWorker()
    tab3, _, _ = make_tab(w3)
    tab3.spin_block.setValue(100)
    tab3._on_file_selected(write_pkg(bytes(range(200))))
    tab3.chk_boost_baud.setChecked(False)
    tab3.chk_read_after.setChecked(True)
    tab3.spin_read_after_delay.setValue(0)
    tab3.spin_retries.setValue(0)
    _run_to_post_read_frame(tab3, w3)
    check("没提升过 ⇒ 计划里只有一种速率",
          tab3._post_bauds == [9600] and tab3._boost_used is False, tab3._post_bauds)
    n3 = w3.writes
    tab3._on_timeout()
    settle()
    check("没提升过 ⇒ 读不到就判读不到，**一次都不切速率**",
          w3.baud_calls == [] and w3.baud == 9600 and w3.writes == n3
          and tab3.state == "done",
          (w3.baud_calls, w3.writes, tab3.state))
    check("没提升过 ⇒ 原因文案保持旧样（不带速率前缀）",
          "9600 波特率下" not in panel_post(tab3), panel_post(tab3))
    tab3.cleanup()

    # ⑥ 升级**前**读版本失败**不**换速率（设备此刻一定在提升速率上，换了反而发不出去）
    w4 = FakeSerialWorker()
    tab4, _, _ = make_tab(w4)
    tab4.spin_block.setValue(100)
    tab4._on_file_selected(write_pkg(bytes(range(100))))
    tab4.chk_boost_baud.setChecked(True)
    tab4.spin_boost_wait.setValue(0)
    tab4.chk_read_before.setChecked(True)
    tab4.spin_retries.setValue(0)
    tab4.btn_start.click()
    settle()
    check("前置：升级前读版本帧已在 115200 发出",
          tab4._phase == "ver_pre" and w4.baud == 115200 and is_ver_frame(w4.sent[-1]),
          (tab4._phase, w4.baud))
    tab4._on_timeout()
    settle()
    check("升级前读版本失败 ⇒ **不**换速率，直接推进启动传输",
          w4.baud == 115200 and w4.baud_calls == [115200]
          and tab4._phase == "start" and omd_of(w4.sent[-1]) == upg.OMD_START,
          (w4.baud_calls, tab4._phase))
    tab4._on_abort()
    tab4.cleanup()
    check("中止照样把端口带回 9600", w4.baud == 9600 and tab4._boosted is False, w4.baud)

    # ⑦ 切回失败 ⇒ 标记保留（收尾还会再试一次），不许一次失败就永久留在 115200
    w5 = FakeSerialWorker()
    tab5, _, _ = make_tab(w5)
    tab5.spin_block.setValue(100)
    tab5._on_file_selected(write_pkg(bytes(range(100))))
    tab5.chk_boost_baud.setChecked(True)
    tab5.spin_boost_wait.setValue(0)
    tab5.btn_start.click()
    settle()
    check("前置：已在 115200", w5.baud == 115200 and tab5._boosted is True, w5.baud)
    w5.fail_baud = True
    tab5._restore_baud("用例⑦")
    check("切回失败 ⇒ 「已提升」标记**保留**（否则再没人把端口带回来）",
          tab5._boosted is True, tab5._boosted)
    check("切回失败写进日志（含手动核对提示）",
          "切回 9600 波特率失败" in log_text(tab5)
          and "手动核对" in log_text(tab5), last_log(tab5))
    w5.fail_baud = False
    tab5._restore_baud("用例⑦")
    check("再试成功 ⇒ 标记清掉、速率真的回到 9600",
          tab5._boosted is False and w5.baud == 9600, (tab5._boosted, w5.baud))
    tab5._on_abort()
    tab5.cleanup()

    # ⑧ 反例自检：判据不是恒真/恒假
    check("反例：`_post_baud_reason()` 对单速率**原样返回**、对双速率才加前缀",
          upg_ui_helper_single_reason() == "X"
          and upg_ui_helper_dual_reason() == "9600 波特率下 X；115200 波特率下 Y")


def upg_ui_helper_single_reason() -> str:
    """`_post_baud_reason()` 的单速率分支（脱离页面直接调，见 [26]⑧）。"""
    tab, w = _prep_boosted_tab()
    tab._post_baud_fails = [(9600, "X")]
    out = tab._post_baud_reason()
    tab._on_abort()
    tab.cleanup()
    return out


def upg_ui_helper_dual_reason() -> str:
    """`_post_baud_reason()` 的双速率分支（见 [26]⑧）。"""
    tab, w = _prep_boosted_tab()
    tab._post_baud_fails = [(9600, "X"), (115200, "Y")]
    out = tab._post_baud_reason()
    tab._on_abort()
    tab.cleanup()
    return out


def _verdict_run(pre_fields=VER_FIELDS, post_fields=VER_FIELDS, *,
                 read_before=True, read_after=True, post_fail=False):
    """跑到收尾并按给定字段投版本响应：版本变了 / 没变 / 读不到 三种情形共用。

    `post_fail=True` 不投响应、直接让「升级完成后读版本」超时（retries=0 ⇒ 一次就到底），
    用来验「读不到版本时判定条不得宣称成功或失败」。
    """
    w = FakeSerialWorker()
    tab, _, _ = make_tab(w)
    tab.spin_block.setValue(100)
    tab._on_file_selected(write_pkg(bytes(range(200))))      # 每包 100 → 2 包
    tab.chk_read_before.setChecked(bool(read_before))
    tab.chk_read_after.setChecked(bool(read_after))
    tab.spin_read_after_delay.setValue(0)                    # 0 = 立即读，不等真 10 秒
    tab.spin_retries.setValue(0)                             # 超时一次即到底（读不到的情形）
    tab.btn_start.click()
    settle()
    for _ in range(40):
        if tab.state in ("done", "failed", "aborted"):
            return tab, w
        if tab._phase == upg_ui.PHASE_WAIT_RESET:
            tab._end_reset_wait()
            settle()
            continue
        tx = w.sent[-1]
        if tab._phase == upg_ui.PHASE_VER_PRE:
            w.deliver(ver_ack_for(tx, fields=pre_fields))
            settle()
        elif tab._phase == upg_ui.PHASE_VER_POST:
            if post_fail:
                tab._on_timeout()
                settle()
            else:
                w.deliver(ver_ack_for(tx, fields=post_fields))
                settle()
        else:
            w.deliver(ack_for(tx))
            settle()
    raise AssertionError(f"没走到终态：phase={tab._phase} state={tab.state}")


def test_version_verdict():
    section("[27] 升级前/后版本比对判定（变了=升级成功，完全一致=升级失败）")
    W = upg_ui.Dlt698UpgradeWidget

    # ① 纯比对口径：**原始字节优先**（值只是展示格式，不能拿它判等）
    pre = W._version_entries([
        {"名称": "软件版本日期", "值": "2025-09-01", "原始": "0A06323530393031"},
        {"名称": "厂商代码", "值": "JCDZ", "原始": "0A044A43445A"},
    ])
    same_raw_other_text = W._version_entries([
        {"名称": "软件版本日期", "值": "2025-9-1", "原始": "0A06323530393031"},
        {"名称": "厂商代码", "值": "jcdz", "原始": "0a044a43445a"},
    ])
    diffs = W._compare_version_entries(pre, same_raw_other_text)
    check("原始字节相同 ⇒ 即使值的大小写/格式不同也判「没变」",
          diffs and not any(d["changed"] for d in diffs), diffs)
    other_raw = W._version_entries([
        {"名称": "软件版本日期", "值": "2025-09-01", "原始": "0A06323531303130"},
        {"名称": "厂商代码", "值": "JCDZ", "原始": "0A044A43445A"},
    ])
    diffs = W._compare_version_entries(pre, other_raw)
    check("原始字节不同 ⇒ 即使值显示一样也判「变了」",
          [d["name"] for d in diffs if d["changed"]] == ["软件版本日期"], diffs)
    added = W._compare_version_entries(pre, pre + [("厂商扩展信息", "NEW", "0A034E4557")])
    check("只在一边出现的字段 ⇒ 算变化（新增/消失不得被忽略）",
          [d["name"] for d in added if d["changed"]] == ["厂商扩展信息"], added)
    # 解析器的 ⚠ 诊断行不是版本字段：它变没变不能决定升级成败
    warn_row = {"名称": "⚠ 长度未自证", "值": "表191 声明 X，本次实发 Y", "原始": ""}
    filtered = W._compare_version_entries(
        W._version_entries(list(pre)), W._version_entries(list(pre) + [warn_row]))
    check("⚠ 诊断行被排除在比对之外（不参与判定）",
          not any(d["changed"] for d in filtered)
          and all("⚠" not in d["name"] for d in filtered), filtered)
    check("长值在判定条上被截断（完整值仍在明细面板/日志）",
          W._verdict_value("X" * 60).endswith("…")
          and len(W._verdict_value("X" * 60)) == upg_ui.VERDICT_VALUE_MAX + 1)
    check("空值显示为 (空)", W._verdict_value("") == "(空)")

    # ② 初始态：还没读 ⇒ 「尚未比对」，不能先摆一个结论
    tab0, w0, _ = make_tab()
    check("初始判定条说「尚未比对」（不是失败、也不是成功）",
          tab0._ver_verdict["level"] == upg_ui.VERDICT_PENDING
          and "尚未比对" in tab0.lbl_verdict.text(), tab0.lbl_verdict.text())
    check("初始判定条不预支字段值（明细只在下面两栏）",
          "厂商代码" not in tab0.lbl_verdict.text(), tab0.lbl_verdict.text())
    tab0.cleanup()

    # ③ 升级前后**完全一致** ⇒ 判定升级失败
    tab, w = _verdict_run()                                  # pre/post 都用默认 VER_FIELDS
    text = tab.lbl_verdict.text()
    log = log_text(tab)
    check("版本一致 ⇒ 判定级别 same", tab._ver_verdict["level"] == upg_ui.VERDICT_SAME,
          tab._ver_verdict)
    check("判定条写明「判定升级失败」且用 ❌ 标出",
          "判定升级失败" in text and "❌" in text and "完全一致" in text, text)
    check("判定条给足依据（6 项全部相同 + 提示设备没换新固件）",
          "6 项全部相同" in text and "没换新固件" in text, text)
    check("收尾状态行也带结论（现场最后看的就是这行）",
          "判定：升级失败（版本未变化）" in tab.lbl_status.text(), tab.lbl_status.text())
    check("日志同步记一条失败级判定（现场回看可查）",
          "[失败] 版本比对：判定升级失败" in log,
          [x for x in log.splitlines() if "版本比对" in x])
    check("判定不打断流程：状态仍 done、进度 100%（流程完成 ≠ 固件升级成功）",
          tab.state == "done" and tab.progress.value() == 100, tab.state)
    check("判定行不复述字段值（字段值只该在明细里出现一次，不刷屏）",
          sum(1 for x in log.splitlines() if "厂商代码" in x and "JCDZ" in x) == 2,
          [x for x in log.splitlines() if "厂商代码" in x])
    tab.cleanup()

    # ④ 软件版本变了 ⇒ 判定升级成功，并给出「旧 → 新」
    NEW = ("JCDZ", "V2.0", "251015", "V1.0", "230602", "SHANDONG")
    tab2, w2 = _verdict_run(post_fields=NEW)
    text2 = tab2.lbl_verdict.text()
    log2 = log_text(tab2)
    check("版本变了 ⇒ 判定级别 changed",
          tab2._ver_verdict["level"] == upg_ui.VERDICT_CHANGED, tab2._ver_verdict)
    check("判定条写明「判定升级成功」且用 ✅ 标出",
          "判定升级成功" in text2 and "✅" in text2 and "版本已变化" in text2, text2)
    check("判定条给出逐项变更（软件版本号 V1.5 → V2.0）",
          "软件版本号：V1.5 → V2.0" in text2, text2)
    check("判定条给出变更计数（只算真正变的项：版本号 + 日期 = 2/6）",
          "2/6 项" in text2 and "硬件版本号" not in text2 and "厂商代码" not in text2, text2)
    check("收尾状态行带成功结论",
          "判定：升级成功（版本已变化）" in tab2.lbl_status.text(), tab2.lbl_status.text())
    check("日志记一条成功级判定",
          "[信息] 版本比对：判定升级成功" in log2,
          [x for x in log2.splitlines() if "版本比对" in x])
    tab2.cleanup()

    # ⑤ 只有「软件版本日期」变（版本号没变）也算变了 —— 判定只看差异，不猜哪一项才算数
    DATE_ONLY = ("JCDZ", "V1.5", "251015", "V1.0", "230602", "SHANDONG")
    tab3, w3 = _verdict_run(post_fields=DATE_ONLY)
    check("只有日期变 ⇒ 仍是「升级成功」（按差异判定，不挑字段）",
          tab3._ver_verdict["level"] == upg_ui.VERDICT_CHANGED
          and "软件版本日期：2025-09-01 → 2025-10-15" in tab3.lbl_verdict.text(),
          tab3.lbl_verdict.text())
    tab3.cleanup()

    # ⑥ 没勾「升级前读版本」⇒ 没有基线 ⇒ 无法判定（不得硬说成功/失败）
    tab4, w4 = _verdict_run(read_before=False)
    check("缺升级前版本 ⇒ 无法判定",
          tab4._ver_verdict["level"] == upg_ui.VERDICT_UNKNOWN
          and "没有升级前版本" in tab4.lbl_verdict.text(), tab4.lbl_verdict.text())
    check("缺基线时状态行不给任何结论",
          "判定：升级成功" not in tab4.lbl_status.text()
          and "判定：升级失败" not in tab4.lbl_status.text(), tab4.lbl_status.text())
    check("缺基线仍照常收尾（done / 100%）",
          tab4.state == "done" and tab4.progress.value() == 100, tab4.state)
    tab4.cleanup()

    # ⑦ 升级完成后读不到版本 ⇒ 无法判定（读不到 ≠ 升级失败）
    tab5, w5 = _verdict_run(post_fail=True)
    check("升级后版本读不到 ⇒ 无法判定（不得判成失败）",
          tab5._ver_verdict["level"] == upg_ui.VERDICT_UNKNOWN
          and "无法判定" in tab5.lbl_verdict.text(), tab5.lbl_verdict.text())
    check("读不到时判定条写明「升级完成后未读到」",
          "升级完成后未读到" in tab5.lbl_verdict.text(), tab5.lbl_verdict.text())
    check("读不到时状态行不下结论",
          "判定：升级成功" not in tab5.lbl_status.text()
          and "判定：升级失败" not in tab5.lbl_status.text(), tab5.lbl_status.text())
    check("读不到仍照常收尾（done）", tab5.state == "done", tab5.state)
    tab5.cleanup()

    # ⑧ 前后读的不是同一项版本内容 ⇒ 值不同也不能当「变了」（口径都不一致）
    tab6, _, _ = make_tab()
    tab6._ver_info = {
        "pre": {"target": "通用", "time": "10:00:00", "note": "", "reason": "",
                "rows": [{"名称": "软件版本号", "值": "V1.5", "原始": "0A0456312E35"}]},
        "post": {"target": "内部", "time": "10:01:00", "note": "", "reason": "",
                 "rows": [{"名称": "软件版本号", "值": "V9.9", "原始": "0A0456392E39"}]},
    }
    tab6._recompute_verdict()
    tab6._render_version_panel()
    check("前后读的不是同一项 ⇒ 无法判定（不把口径差异当升级成功）",
          tab6._ver_verdict["level"] == upg_ui.VERDICT_UNKNOWN
          and "不是同一项" in tab6.lbl_verdict.text(), tab6.lbl_verdict.text())
    tab6.cleanup()

    # ⑨ 判定条跟随主题换色（暗色/浅色各自可读）
    tab7, _, _ = make_tab()
    tab7._ver_info = {
        "pre": {"target": "通用", "time": "10:00:00", "note": "", "reason": "",
                "rows": [{"名称": "软件版本号", "值": "V1.5", "原始": "0A0456312E35"}]},
        "post": {"target": "通用", "time": "10:01:00", "note": "", "reason": "",
                 "rows": [{"名称": "软件版本号", "值": "V1.5", "原始": "0A0456312E35"}]},
    }
    tab7._recompute_verdict()
    tab7.restyle_for_theme(False)
    light = tab7.lbl_verdict.styleSheet()
    tab7.restyle_for_theme(True)
    dark = tab7.lbl_verdict.styleSheet()
    check("判定条配色随主题切换（浅色/暗色不同色）",
          upg_ui.LOG_PALETTES[False]["fail"] in light
          and upg_ui.LOG_PALETTES[True]["fail"] in dark and light != dark,
          (light, dark))
    check("判定条在主题切换后仍保留结论文案",
          "判定升级失败" in tab7.lbl_verdict.text(), tab7.lbl_verdict.text())
    tab7.cleanup()

    # ⑩ 两侧都「成功但无数据」（DAR=0 且响应不带版本内容）⇒ 空 vs 空不是「版本一致」
    tab8, _, _ = make_tab()
    empty = {"target": "通用", "time": "10:00:00", "note": "", "reason": "", "rows": []}
    tab8._ver_info = {"pre": dict(empty), "post": dict(empty, time="10:01:00")}
    tab8._recompute_verdict()
    tab8._render_version_panel()
    check("两侧都没带版本内容 ⇒ 无法判定（不得判成「完全一致=失败」）",
          tab8._ver_verdict["level"] == upg_ui.VERDICT_UNKNOWN
          and "都没带版本内容" in tab8.lbl_verdict.text(), tab8.lbl_verdict.text())
    check("无数据时提示去确认 OAD 是否被设备支持",
          "OAD" in tab8.lbl_verdict.text(), tab8.lbl_verdict.text())
    tab8.cleanup()

    # ⑪ 两侧都只有兜底文本（无逐字段明细）⇒ 退化为比对那段文本
    tab9, _, _ = make_tab()
    tab9._ver_info = {
        "pre": {"target": "通用", "time": "10:00:00", "rows": [], "reason": "",
                "note": "V1.5"},
        "post": {"target": "通用", "time": "10:01:00", "rows": [], "reason": "",
                 "note": "V2.0"},
    }
    tab9._recompute_verdict()
    tab9._render_version_panel()
    check("只有兜底文本时也比对（V1.5 → V2.0 判成功）",
          tab9._ver_verdict["level"] == upg_ui.VERDICT_CHANGED
          and "V1.5 → V2.0" in tab9.lbl_verdict.text(), tab9.lbl_verdict.text())
    tab9.cleanup()


def test_package_path_persist():
    section("[28] 升级包路径持久化（重开程序显示上次的文件，只有换新文件才更新）")
    cfg_path = os.path.join(str(SANDBOX), upg_ui.CONFIG_NAME)

    def cfg():
        with open(cfg_path, encoding="utf-8") as fh:
            return json.load(fh)

    if os.path.exists(cfg_path):
        os.remove(cfg_path)

    # ① 选过文件 ⇒ 重开页面自动恢复（路径/字节/分包/摘要全都回来）
    path_a = write_pkg(bytes(range(180)))
    t1, _, _ = make_tab()
    t1.spin_block.setValue(100)
    t1._on_file_selected(path_a)
    check("选择后路径进内存", t1._path == path_a, t1._path)
    check("落盘内容带 file_path",
          t1._save_persisted() is True and cfg()["file_path"] == path_a, cfg().get("file_path"))
    t1.cleanup()

    t2, _, _ = make_tab(fresh=False)
    check("重开页面自动恢复上次的文件路径", t2._path == path_a, t2._path)
    check("拖放区显示文件名（basename）",
          t2.lbl_file_name.text() == os.path.basename(path_a), t2.lbl_file_name.text())
    check("完整路径挂在 tooltip（同名不同目录分得清）",
          t2.lbl_file_name.toolTip() == path_a, t2.lbl_file_name.toolTip())
    check("恢复后文件字节已读、分包已建（可直接开始）",
          t2._data == bytes(range(180)) and t2._num_blocks() == 2,
          (len(t2._data), t2._num_blocks()))
    check("恢复后大小标签按真实字节数", "180" in t2.lbl_file_size.text(), t2.lbl_file_size.text())
    check("恢复日志写明完整路径（现场可查是哪个包）", path_a in log_text(t2), last_log(t2))
    check("恢复不写「分包完成」日志（开页面不刷屏）",
          "分包完成" not in log_text(t2), [x for x in log_text(t2).splitlines() if "分包" in x])
    check("恢复后能通过开始前校验（不是只显示个名字）",
          t2._validate_inputs() == "", t2._validate_inputs())

    # ② 恢复不冲掉手工「文件大小」覆盖值（那是用户落盘参数，不是文件的从属值）
    t2.spin_size.setValue(12345)
    check("落盘成功", t2._save_persisted() is True)
    t2.cleanup()
    t3, _, _ = make_tab(fresh=False)
    check("恢复不冲掉手工「文件大小」覆盖值",
          t3.spin_size.value() == 12345 and t3._path == path_a,
          (t3.spin_size.value(), t3._path))
    t3.spin_size.setValue(0)
    check("复位覆盖值后落盘", t3._save_persisted() is True)
    t3.cleanup()

    # ③ **只有换新文件才更新路径**（这是用户的原话口径）
    path_b = write_pkg(b"\xBB" * 64)
    t4, _, _ = make_tab(fresh=False)
    check("新实例仍是上次的路径", t4._path == path_a, t4._path)
    t4._on_file_selected(path_b)
    check("换了新文件 ⇒ 路径与字节都更新",
          t4._path == path_b and t4._data == b"\xBB" * 64, (t4._path, len(t4._data)))
    check("落盘也更新成新路径",
          t4._save_persisted() is True and cfg()["file_path"] == path_b, cfg().get("file_path"))
    t4.cleanup()

    # ④ 文件没了 ⇒ 不恢复（不能显示成一个「看着能开始」的假状态），但**不删**用户的记录
    os.remove(path_b)
    t5, _, _ = make_tab(fresh=False)
    check("文件不存在 ⇒ 不恢复（保持未选择，避免误开始）",
          t5._path == "" and t5._data == b"" and t5.lbl_file_name.text() == "未选择文件",
          (t5._path, t5.lbl_file_name.text()))
    check("拖放区写明原因", "上次的升级包不可用" in t5.lbl_drop_hint.text(),
          t5.lbl_drop_hint.text())
    check("日志记一条告警（现场可查）",
          "[警告]" in log_text(t5) and "上次的升级包不可用" in log_text(t5), last_log(t5))
    check("开始前校验拦住（提示先选文件）",
          t5._validate_inputs() == "请先拖入（或浏览选择）升级包文件", t5._validate_inputs())
    check("落盘路径**仍保留**（U 盘/网络盘可能回来，不替用户删记录）",
          cfg()["file_path"] == path_b, cfg().get("file_path"))
    t5._on_file_selected(path_a)
    check("换到可用文件后拖放区告警撤掉、提示回到常态",
          t5._restore_note == "" and t5.lbl_drop_hint.text() == upg_ui.DROP_HINT_IDLE,
          t5.lbl_drop_hint.text())
    t5.cleanup()

    # ⑤「清除」保留文件与路径（文档口径：清除只清日志/进度，便于原地重跑）
    t6, _, _ = make_tab(fresh=False)
    t6.btn_clear.click()
    settle()
    check("「清除」保留文件与路径",
          t6._path == path_a and t6._collect_settings()["file_path"] == path_a,
          (t6._path, t6._collect_settings()["file_path"]))
    t6.cleanup()

    # ⑥ 恢复路径下 crcmod 缺失：只写日志、**不弹模态**（开页面弹框会打断现场）
    calls = []
    with patch.object(upg_ui.QMessageBox, "warning", lambda *a, **k: calls.append(a)):
        with patch.dict(sys.modules, {"dl_t698_45_upgrade": None}):
            t7, _, _ = make_tab(fresh=False)
    check("恢复路径下 crcmod 缺失不弹框（只写日志）", calls == [], calls)
    check("crcmod 缺失时仍恢复文件名（只是分包算不出，开始时会照常给提示）",
          t7._path == path_a and t7.lbl_file_name.text() == os.path.basename(path_a),
          (t7._path, t7.lbl_file_name.text()))
    check("crcmod 缺失时确实写了可读提示",
          upg_ui.MISSING_CRCMOD in log_text(t7), last_log(t7))
    t7.cleanup()

    if os.path.exists(cfg_path):
        os.remove(cfg_path)


def main():
    print("=" * 64)
    print("协议8 升级页 dlt698_upgrade_widget offscreen 回归")
    print("=" * 64)

    app = QApplication.instance() or QApplication([])
    del app

    test_helpers()
    test_build()
    test_disconnected()
    test_happy_path()
    test_plan_single_source()
    test_progress_only_on_ack()
    test_retry_then_ok()
    test_retries_exhausted()
    test_dar_rejected()
    test_abort()
    test_drop_area()
    test_persist_and_cleanup()
    test_missing_crcmod()
    test_unknown_frames_ignored()
    test_resync_edges()
    test_layout_guard()
    test_theme()
    test_negatives()
    test_mid_transfer_controls()
    test_version_read_flow()
    test_version_read_nonblocking()
    test_version_read_mismatch_retries()
    test_version_read_target_select()
    test_version_read_single_value_fallback()
    test_reset_wait_before_post_read()
    test_bluetooth_channel()
    test_bluetooth_channel_isolation()
    test_baud_boost()
    test_post_read_dual_baud()
    test_version_verdict()
    test_package_path_persist()

    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
