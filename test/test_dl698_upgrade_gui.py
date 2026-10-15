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

    def is_open(self) -> bool:
        return self._open

    def write_raw(self, data: bytes) -> bool:
        if not self._open:
            return False
        self.writes += 1
        self.sent.append(bytes(data))
        return True

    def close_port(self) -> None:
        self.closed += 1

    def deliver(self, data: bytes) -> None:
        """注入一次「原始串口交付」（可只给半帧，测自组帧）。"""
        self.raw_data_received.emit(bytes(data))


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
