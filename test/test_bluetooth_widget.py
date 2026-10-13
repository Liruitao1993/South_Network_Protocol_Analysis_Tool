# -*- coding: utf-8 -*-
"""蓝牙工具页（bluetooth_tool_widget）offscreen 回归测试 —— 假 worker / 假串口，不碰硬件。

覆盖：
  [1] 纯助手：looks_like_hex / parse_plain_text（含「HEX 写错不许静默按文本发」）、
      format_payload / rssi_* / parse_button_lines
  [2] 页面构建：协议下拉、发送格式下拉、默认设置、日志就绪
  [3] 扫描信号 → 设备表、只显示有名称的过滤、排序
  [4] 连接信号 → 连接信息、MTU 文案、已连接状态、设备表「已连接」标记
  [5] 特征码自动选择 + 落盘；「特征码…」对话框回填与保存
  [6] 收到帧：日志、按协议解析（注入 provider）、虚拟模式转发串口
  [7] 发送：HEX/ASCII/自动三种格式、非法 HEX 不发、自定义报文按钮单击发送、
      「送入单帧解析」回调
  [8] 自定义按钮：新增/批量/导出/导入/上移下移/删除/清空（对话框打桩）
  [9] 持久化往返（新页面读回同一份配置）
  [10] 日志：自动保存文件内容与窗口一致、写统计尾并关闭
  [11] cleanup 幂等、restyle_for_theme 不抛
  [12] MTU / 写上限实时化：默认值文案、实时更新标签与缓存、不重订阅、对话框刷新
  [13] 自定义按钮的「协议 + 地址」：下拉联动、动态字段、预览、发送时替换+重算、失败不发
  [14] 自定义报文区空间治理：滚动封顶、日志不被挤没、收起/展开、分栏尺寸记忆
  [15] 反例自检

运行: python test/test_bluetooth_widget.py
"""

import _path_setup  # noqa: E402,F401

import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QGroupBox,
    QLabel,
    QMessageBox,
    QSplitter,
)

import _config_sandbox  # noqa: E402

# 构造页面之前屏蔽模态框（否则 offscreen 下永久阻塞）
for _name in ("warning", "information", "critical"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()
patch.object(QMessageBox, "question",
             lambda *a, **k: QMessageBox.StandardButton.Yes).start()

SANDBOX = _config_sandbox.install()

import bluetooth_core as core  # noqa: E402
import bluetooth_tool_widget as btw  # noqa: E402
import frame_addr_fix as fix  # noqa: E402

PASS = 0
FAIL = 0


def _console_safe(text) -> str:
    """把要打印的文本降级到控制台能编码的字符集（Windows 控制台常为 GBK）。

    页面提示文案里含 ``⚠``/``✓`` 等符号，直接把 detail 打出去会抛 UnicodeEncodeError
    把整个测试脚本带崩 —— 测试失败信息不该反过来杀掉测试进程。
    """
    raw = str(text)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return raw.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except (LookupError, UnicodeError):
        return raw.encode("ascii", errors="replace").decode("ascii")


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [NG] {name}" + (f"  -> {_console_safe(detail)}" if detail else ""))


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 56 - len(title)))


# ── 假 worker / 假串口 ──────────────────────────────────────────────────────

RECV_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
SEND_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"


class FakeBluetoothWorker(QObject):
    """鸭子类型的 BLE worker：与本页用到的 `BluetoothWorker` 同形。"""

    scan_started = Signal()
    device_found = Signal(str, str, int)
    scan_finished = Signal(int)
    scan_error = Signal(str)
    connecting = Signal(str, str)
    connected = Signal(str, str)
    connect_error = Signal(str)
    disconnected = Signal()
    connection_changed = Signal(bool)
    characteristics_updated = Signal(list)
    mtu_updated = Signal(int, list)
    subscribe_finished = Signal(list, bool)
    notification_received = Signal(str, bytes)
    frame_received = Signal(str, bytes)
    send_progress = Signal(int, int, bytes)
    data_sent = Signal(bytes)
    log_message = Signal(str)
    error_occurred = Signal(str)
    stats_changed = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._connected = False
        self._name = ""
        self._address = ""
        self._mtu = 247
        self._recv = []
        self._send = []
        self._stats = (0, 0)
        self.started_scan = 0
        self.connected_to = []
        self.disconnects = 0
        self.sent = []
        self.timeout = core.DEFAULT_PACKET_TIMEOUT
        self.delay = core.DEFAULT_SEND_PACKET_DELAY
        self.shutdowns = 0
        self.fail_send = False
        self.fail_subscribe = False
        self.char_sets = 0      # set_characteristics 调用次数（实时上限更新**不得**触发重订阅）

    # 查询
    def is_connected(self):
        return self._connected

    def is_scanning(self):
        return False

    def device_name(self):
        return self._name

    def device_address(self):
        return self._address

    def mtu_size(self):
        return self._mtu

    def characteristics(self):
        return []

    def recv_uuids(self):
        return list(self._recv)

    def send_uuids(self):
        return list(self._send)

    def stats(self):
        return self._stats

    def reset_stats(self):
        self._stats = (0, 0)
        self.stats_changed.emit(*self._stats)

    def packet_timeout(self):
        return self.timeout

    def pending_bytes(self):
        return 0

    def bleak_available(self):
        return True

    # 动作
    def set_packet_timeout(self, seconds):
        self.timeout = float(seconds)

    def set_send_options(self, packet_delay=None, max_chunk=None):
        if packet_delay is not None:
            self.delay = float(packet_delay)

    def start_scan(self, timeout=None):
        self.started_scan += 1
        return True

    def connect_device(self, address, name=""):
        self.connected_to.append((address, name))
        return True

    def disconnect_device(self):
        self.disconnects += 1
        return True

    def set_characteristics(self, recv, send):
        self.char_sets += 1
        self._recv = list(recv or [])
        self._send = list(send or [])
        # 与真实 worker 同形：订阅阶段结束就发一次（一键探测据此决定何时才写）
        if self._connected:
            if self.fail_subscribe and self._recv:
                self.subscribe_finished.emit([], False)
            else:
                self.subscribe_finished.emit(list(self._recv), True)

    def send_data(self, data):
        if self.fail_send:
            self.error_occurred.emit("发送被拒（假）")
            return False
        self.sent.append(bytes(data))
        return True

    def shutdown(self, timeout=3.0):
        self.shutdowns += 1

    # 测试辅助：把当前状态与真实 worker 对齐后发信号
    def become_connected(self, name="LME_06012", address="AA:01", mtu=247):
        self._connected = True
        self._name = name
        self._address = address
        self._mtu = mtu
        self.connected.emit(name, address)
        self.connection_changed.emit(True)

    def become_disconnected(self):
        self._connected = False
        self.disconnected.emit()
        self.connection_changed.emit(False)


class FakeSerialWorker(QObject):
    """鸭子类型的串口 worker（虚拟模式透传用）。"""

    raw_data_received = Signal(bytes)
    error_occurred = Signal(str)
    connection_changed = Signal(bool)

    def __init__(self, is_open=True):
        super().__init__()
        self._open = bool(is_open)
        self.written = []
        self.write_ok = True

    def is_open(self):
        return self._open

    def write_raw(self, data):
        if not self.write_ok:
            return False
        self.written.append(bytes(data))
        return True


def make_tab(worker=None, serial=None):
    tab = btw.BluetoothToolWidget()
    if worker is not None:
        tab.set_bluetooth_worker(worker)
    if serial is not None:
        tab.set_serial_worker(serial)
    return tab


def drain(tab):
    """把日志队列刷进窗口（正常情况下由定时器刷，测试里手动驱动）。"""
    tab._flush_log_queue()


def log_text(tab):
    drain(tab)
    return tab.log_text.toPlainText()


def settle(times: int = 6):
    """让布局/滚动条彻底安定：重建大量控件或改动分栏后，一次 `processEvents` 不够
    （滚动条范围要等内部控件 resize 后才更新，否则断言会读到 0 而误判）。"""
    for _ in range(max(1, int(times))):
        QApplication.processEvents()


# ── [1] 纯助手 ──────────────────────────────────────────────────────────────

def test_helpers():
    section("[1] 纯助手")

    check("looks_like_hex：空格 HEX", btw.looks_like_hex("68 12 00 41 16") is True)
    check("looks_like_hex：连续 HEX", btw.looks_like_hex("68120041 16") is True)
    check("looks_like_hex：0x 前缀", btw.looks_like_hex("0x68 0x12") is True)
    check("looks_like_hex：文本含 + 判为文本", btw.looks_like_hex("AT+INFO?") is False)
    check("looks_like_hex：空串 False", btw.looks_like_hex("   ") is False)
    check("looks_like_hex：只有分隔符 False", btw.looks_like_hex(" , ; ") is False)

    payload, err = btw.parse_plain_text("68 12 00 41 16")
    check("auto：HEX 解析", payload == b"\x68\x12\x00\x41\x16" and err == "", (payload, err))
    payload, err = btw.parse_plain_text("AT+INFO?")
    check("auto：文本回落 UTF-8", payload == b"AT+INFO?" and err == "", (payload, err))
    payload, err = btw.parse_plain_text("68 12 0G")
    check("auto：HEX 写错必须报错（**不**静默按文本发）",
          payload is None and "无效" in err, (payload, err))
    payload, err = btw.parse_plain_text("6812 0")
    check("auto：奇数长度连续 HEX 报错", payload is None and err != "", (payload, err))
    payload, err = btw.parse_plain_text("AT", "hex")
    check("强制 hex：非 HEX 报错", payload is None and err != "", (payload, err))
    payload, err = btw.parse_plain_text("68 12", "hex")
    check("强制 hex：正常解析", payload == b"\x68\x12", (payload, err))
    payload, err = btw.parse_plain_text("68 12", "ascii")
    check("强制 ascii：按文本发", payload == b"68 12", (payload, err))
    payload, err = btw.parse_plain_text("   ")
    check("空内容报错", payload is None and "空" in err, (payload, err))

    check("format_payload HEX", btw.format_payload(b"\x68\x12") == "68 12")
    check("format_payload ASCII 不可打印回落 .",
          btw.format_payload(b"AB\x00C", as_hex=False) == "AB.C")
    check("format_payload 空", btw.format_payload(b"") == "")

    check("rssi_level 分档", [btw.rssi_level(v) for v in (-50, -60, -75, -85, -95, 0)]
          == [4, 3, 2, 1, 0, 0],
          [btw.rssi_level(v) for v in (-50, -60, -75, -85, -95, 0)])
    check("rssi_text 未知回落 --", btw.rssi_text(0) == "--", btw.rssi_text(0))
    check("rssi_text 带信号格", btw.rssi_text(-57).startswith("-57 dBm"), btw.rssi_text(-57))

    buttons, errors = btw.parse_button_lines(
        "# 注释\n查询,68 12 00 41 16,HEX\n文本,AT+INFO?,ASCII\n坏行,68 1G,HEX\n空内容,,HEX"
    )
    check("批量解析：注释/空行跳过、2 条成功", len(buttons) == 2, buttons)
    check("批量解析：报出坏行与空内容", len(errors) == 2, errors)
    check("批量解析：HEX 标记正确",
          buttons[0]["isHex"] is True and buttons[1]["isHex"] is False, buttons)
    check("批量解析：缺省格式按 HEX",
          btw.parse_button_lines("a,68 12")[0][0]["isHex"] is True)
    check("批量解析：缺名称回落 报文N",
          btw.parse_button_lines(",68 12")[0][0]["name"] == "报文1")
    many = btw.parse_button_lines("\n".join(f"b{i},01" for i in range(70)))
    check("批量解析：超上限只收上限条数并报错",
          len(many[0]) == core.MAX_CUSTOM_BUTTONS and bool(many[1]), len(many[0]))


# ── [2] 页面构建 ────────────────────────────────────────────────────────────

def test_build():
    section("[2] 页面构建")

    tab = make_tab()
    check("协议下拉有内容（不解析 + 各协议）", tab.combo_protocol.count() >= 2,
          tab.combo_protocol.count())
    check("协议下拉首项为「不解析」", tab.combo_protocol.currentData() is None,
          tab.combo_protocol.currentData())
    check("发送格式三项", tab.combo_send_format.count() == len(btw.SEND_FORMATS))
    check("默认 HEX 显示勾选", tab.chk_show_hex.isChecked() is True)
    check("默认切帧超时为内核默认",
          abs(tab.spin_timeout.value() - core.DEFAULT_PACKET_TIMEOUT) < 1e-6,
          tab.spin_timeout.value())
    check("切帧超时范围与内核一致（下限）",
          abs(tab.spin_timeout.minimum() - core.PACKET_TIMEOUT_RANGE[0]) < 1e-6)
    check("默认无自定义按钮", tab._buttons == [])
    check("自定义区标题带计数", "0" in tab.custom_group.title(), tab.custom_group.title())
    check("初始日志有就绪提示", "就绪" in log_text(tab), log_text(tab)[:80])
    check("设备表列为 4 列", tab.device_table.columnCount() == len(btw.DEVICE_COLUMNS))
    check("连接信息初始为 —", tab.lbl_info_mtu.text() == "—", tab.lbl_info_mtu.text())
    check("状态行可读", "未连接" in tab.lbl_status.text(), tab.lbl_status.text())
    tab.cleanup()


# ── [3] 扫描 → 设备表 ───────────────────────────────────────────────────────

def test_scan_ui():
    section("[3] 扫描 → 设备表")

    worker = FakeBluetoothWorker()
    tab = make_tab(worker)

    tab.btn_scan.click()
    QApplication.processEvents()
    check("点扫描会调 worker.start_scan", worker.started_scan == 1, worker.started_scan)
    check("扫描中「扫描设备」置灰", tab.btn_scan.isEnabled() is False)
    check("扫描中「停止扫描」可用", tab.btn_stop_scan.isEnabled() is True)

    worker.device_found.emit("LME_06012", "AA:01", -57)
    worker.device_found.emit("", "AA:02", -57)
    worker.device_found.emit("EDQ253", "AA:03", -70)
    worker.scan_finished.emit(3)
    QApplication.processEvents()
    check("设备表 3 行", tab.device_table.rowCount() == 3, tab.device_table.rowCount())
    check("排序：强信号在前、同强度有名称优先",
          [tab.device_table.item(i, 1).text() for i in range(3)]
          == ["AA:01", "AA:02", "AA:03"],
          [tab.device_table.item(i, 1).text() for i in range(3)])
    check("无名设备显示为（无名）",
          tab.device_table.item(1, 0).text() == "（无名）",
          tab.device_table.item(1, 0).text())
    check("信号列有 dBm 文案",
          "dBm" in tab.device_table.item(0, 2).text(),
          tab.device_table.item(0, 2).text())
    check("扫描结束按钮恢复", tab.btn_scan.isEnabled() is True)

    tab.chk_named_only.setChecked(True)
    QApplication.processEvents()
    check("只显示有名称的设备 → 2 行", tab.device_table.rowCount() == 2,
          tab.device_table.rowCount())
    tab.chk_named_only.setChecked(False)
    QApplication.processEvents()
    check("取消过滤 → 恢复 3 行", tab.device_table.rowCount() == 3)

    tab._on_scan_error("扫描失败：假错误")
    QApplication.processEvents()
    check("扫描错误写进日志", "假错误" in log_text(tab))
    tab.cleanup()


# ── [4][5] 连接与特征码 ─────────────────────────────────────────────────────

def test_connect_and_characteristics():
    section("[4][5] 连接 / 特征码")

    worker = FakeBluetoothWorker()
    tab = make_tab(worker)
    tab.device_found_saved = None

    # 未选设备时点连接 → 只提示、不调用 worker
    tab.btn_connect.click()
    QApplication.processEvents()
    check("未选设备不发起连接", worker.connected_to == [], worker.connected_to)

    worker.device_found.emit("LME_06012", "AA:01", -57)
    worker.scan_finished.emit(1)
    QApplication.processEvents()
    tab.device_table.selectRow(0)
    tab.btn_connect.click()
    QApplication.processEvents()
    check("选中设备后发起连接", worker.connected_to == [("AA:01", "LME_06012")],
          worker.connected_to)

    worker.become_connected()
    QApplication.processEvents()
    check("连接信息显示设备名", tab.lbl_info_device.text() == "LME_06012",
          tab.lbl_info_device.text())
    check("MTU 文案含单包上限（247 → 200）",
          "247" in tab.lbl_info_mtu.text() and "200" in tab.lbl_info_mtu.text(),
          tab.lbl_info_mtu.text())
    check("连接后「断开」可用", tab.btn_disconnect.isEnabled() is True)
    check("连接后「连接」置灰", tab.btn_connect.isEnabled() is False)
    check("设备表标记已连接",
          any(tab.device_table.item(i, 3).text() == "已连接"
              for i in range(tab.device_table.rowCount())))
    check("连接事件写进日志", "已连接" in log_text(tab))

    chars = [
        {"uuid": RECV_UUID, "short": "0xFFF1", "service_short": "0xFFF0",
         "service_uuid": "0000fff0-0000-1000-8000-00805f9b34fb",
         "properties": ["notify"], "description": "上报通道",
         "can_recv": True, "can_send": False, "max_write": 0},
        {"uuid": SEND_UUID, "short": "0xFFF2", "service_short": "0xFFF0",
         "service_uuid": "0000fff0-0000-1000-8000-00805f9b34fb",
         "properties": ["write"], "description": "下发通道",
         "can_recv": False, "can_send": True, "max_write": 0},
    ]
    worker.characteristics_updated.emit(chars)
    QApplication.processEvents()
    check("特征码数量写进连接信息", "2" in tab.lbl_info_chars.text(), tab.lbl_info_chars.text())
    check("未选过时自动选择收发通道",
          worker.recv_uuids() == [RECV_UUID] and worker.send_uuids() == [SEND_UUID],
          (worker.recv_uuids(), worker.send_uuids()))
    check("自动选择有日志说明", "自动选择特征码" in log_text(tab))

    # 「特征码…」对话框：打桩返回接受 + 指定选择
    class FakeDialog:
        def __init__(self, *a, **k):
            self.args = a

        DialogCode = QDialog.DialogCode

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_recv(self):
            return [RECV_UUID]

        def selected_send(self):
            return []

    with patch.object(btw, "CharacteristicSelectDialog", FakeDialog):
        tab.btn_chars.click()
        QApplication.processEvents()
    check("对话框结果下发到 worker", worker.send_uuids() == [],
          worker.send_uuids())
    check("未选发送通道有提醒", "未选发送特征码" in log_text(tab))

    # 断开
    tab.btn_disconnect.click()
    QApplication.processEvents()
    check("断开调用 worker", worker.disconnects == 1, worker.disconnects)
    worker.become_disconnected()
    QApplication.processEvents()
    check("断开后连接信息复原", tab.lbl_info_mtu.text() == "—", tab.lbl_info_mtu.text())
    check("断开后「连接」恢复可用", tab.btn_connect.isEnabled() is True)
    tab.cleanup()


# ── [6][7] 收发与解析 ───────────────────────────────────────────────────────

def test_rx_tx_and_parse():
    section("[6][7] 收发 / 解析联动")

    worker = FakeBluetoothWorker()
    serial = FakeSerialWorker()
    tab = make_tab(worker, serial)
    calls = []

    def provider(frame, protocol):
        calls.append((bytes(frame), protocol))
        return "假摘要", [("字段A", "原始", "解析值", "说明")]

    tab.set_parse_provider(provider)
    tab.set_send_to_single_handler(lambda hexs: calls.append(("single", hexs)))
    worker.become_connected()
    QApplication.processEvents()

    # 未勾解析（默认勾选）先验证解析输出
    tab._select_protocol(7)
    tab.chk_parse.setChecked(True)
    worker.frame_received.emit(RECV_UUID, b"\x68\x12\x00\x41\x16")
    QApplication.processEvents()
    text = log_text(tab)
    check("收到帧写进日志（带特征码短名）", "[RX·0xFFF1]" in text, text[-300:])
    check("解析回调被调用（报文与协议正确）",
          calls[:1] == [(b"\x68\x12\x00\x41\x16", 7)], calls)
    check("解析摘要写进日志", "假摘要" in text)
    check("解析字段行写进日志（缩进 + 说明）",
          "字段A = 解析值  说明" in text, text[-300:])

    # 关掉解析 → 不再调用 provider
    calls.clear()
    tab.chk_parse.setChecked(False)
    worker.frame_received.emit(RECV_UUID, b"\x01\x02")
    QApplication.processEvents()
    check("关掉解析后不再调用 provider", calls == [], calls)
    check("关掉解析后仍显示原始帧", "[RX·0xFFF1]" in log_text(tab))

    # ASCII 显示
    tab.chk_show_hex.setChecked(False)
    worker.frame_received.emit(RECV_UUID, b"AB\x00C")
    QApplication.processEvents()
    check("取消 HEX 后按 ASCII 显示", "AB.C" in log_text(tab))

    # 虚拟模式：BLE → 串口
    tab.chk_virtual.setChecked(True)
    QApplication.processEvents()
    check("虚拟模式读到串口已连接", tab.lbl_serial_state.text() == "串口：已连接",
          tab.lbl_serial_state.text())
    serial.written.clear()
    worker.frame_received.emit(RECV_UUID, b"\xAA\xBB")
    QApplication.processEvents()
    check("虚拟模式把 BLE 数据写进串口", serial.written == [b"\xAA\xBB"], serial.written)

    # 虚拟模式：串口 → BLE
    worker.sent.clear()
    serial.raw_data_received.emit(b"\x01\x02\x03")
    QApplication.processEvents()
    check("虚拟模式把串口数据写进 BLE", worker.sent == [b"\x01\x02\x03"], worker.sent)

    # 串口未连接时明确丢弃提示
    serial._open = False
    serial.connection_changed.emit(False)
    QApplication.processEvents()
    worker.sent.clear()
    serial.raw_data_received.emit(b"\x09")
    QApplication.processEvents()
    check("串口未连接时串口数据不写 BLE", worker.sent == [], worker.sent)
    serial.written.clear()
    worker.frame_received.emit(RECV_UUID, b"\x08")
    QApplication.processEvents()
    check("串口未连接时 BLE 数据不写串口", serial.written == [], serial.written)
    check("丢包有提醒（不静默）", "丢弃" in log_text(tab))

    tab.chk_virtual.setChecked(False)

    # 发送：三种格式
    worker.sent.clear()
    tab.edit_send.setText("68 12 00 41 16")
    tab.combo_send_format.setCurrentIndex(
        [i for i in range(tab.combo_send_format.count())
         if tab.combo_send_format.itemData(i) == "auto"][0])
    tab.btn_send.click()
    QApplication.processEvents()
    check("auto 发 HEX", worker.sent == [b"\x68\x12\x00\x41\x16"], worker.sent)

    worker.sent.clear()
    tab.edit_send.setText("AT+INFO?")
    tab.btn_send.click()
    QApplication.processEvents()
    check("auto 发文本", worker.sent == [b"AT+INFO?"], worker.sent)

    worker.sent.clear()
    tab.edit_send.setText("68 12 0G")
    tab.btn_send.click()
    QApplication.processEvents()
    check("auto：HEX 写错**不发送**", worker.sent == [], worker.sent)
    check("auto：写错有提示", "无效" in tab.lbl_send_hint.text(), tab.lbl_send_hint.text())
    check("auto：写错有日志（不会静默）", "无效" in log_text(tab))

    worker.sent.clear()
    tab.edit_send.setText("AT+INFO?")
    tab.combo_send_format.setCurrentIndex(
        [i for i in range(tab.combo_send_format.count())
         if tab.combo_send_format.itemData(i) == "hex"][0])
    tab.btn_send.click()
    QApplication.processEvents()
    check("强制 hex：文本内容被拒", worker.sent == [], worker.sent)

    worker.sent.clear()
    tab.edit_send.setText("68 12")
    tab.combo_send_format.setCurrentIndex(
        [i for i in range(tab.combo_send_format.count())
         if tab.combo_send_format.itemData(i) == "ascii"][0])
    tab.btn_send.click()
    QApplication.processEvents()
    check("强制 ascii：按文本发", worker.sent == [b"68 12"], worker.sent)

    # 发送失败（worker 拒绝）不静默
    worker.fail_send = True
    tab.edit_send.setText("68 12")
    tab.btn_send.click()
    QApplication.processEvents()
    check("worker 拒绝发送有日志提醒", "未被受理" in log_text(tab))
    check("worker 报错写进日志", "发送被拒" in log_text(tab))
    worker.fail_send = False

    # 送入单帧解析（先把格式切回 auto：上一段测强制 ascii 时改过下拉，别把状态带进来）
    calls.clear()
    tab.edit_send.setText("68 12 00 41 16")
    tab.combo_send_format.setCurrentIndex(
        [i for i in range(tab.combo_send_format.count())
         if tab.combo_send_format.itemData(i) == "auto"][0])
    tab.btn_send_parse.click()
    QApplication.processEvents()
    check("送入单帧解析回调收到 HEX 文本",
          calls == [("single", "68 12 00 41 16")], calls)

    # 统计
    worker.stats_changed.emit(100, 200)
    QApplication.processEvents()
    check("统计显示在状态行", "100" in tab.lbl_status.text() and "200" in tab.lbl_status.text(),
          tab.lbl_status.text())
    tab.btn_reset_stats.click()
    QApplication.processEvents()
    check("统计清零后状态行归零", " 0 B" in tab.lbl_status.text(), tab.lbl_status.text())

    tab.cleanup()


# ── [8] 自定义报文按钮 ──────────────────────────────────────────────────────

def test_custom_buttons():
    section("[8] 自定义报文按钮")

    worker = FakeBluetoothWorker()
    tab = make_tab(worker)
    worker.become_connected()
    QApplication.processEvents()

    class FakeEditDialog:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def value(self):
            return {"name": "查询", "data": "68 12 00 41 16", "isHex": True}

    with patch.object(btw, "ButtonEditDialog", FakeEditDialog):
        tab.btn_custom_add.click()
        QApplication.processEvents()
    check("新增按钮成功", len(tab._buttons) == 1, tab._buttons)
    check("网格里出现按钮", len(tab._custom_buttons) == 1, len(tab._custom_buttons))
    check("标题带计数", "1" in tab.custom_group.title(), tab.custom_group.title())

    class FakeBatchDialog:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def buttons(self):
            return [{"name": "文本", "data": "AT+INFO?", "isHex": False}]

    with patch.object(btw, "BatchButtonDialog", FakeBatchDialog):
        tab.btn_custom_batch.click()
        QApplication.processEvents()
    check("批量新增追加", len(tab._buttons) == 2, tab._buttons)
    check("网格按钮数同步", len(tab._custom_buttons) == 2)

    # 单击按钮 → 按各自格式发送
    worker.sent.clear()
    tab._custom_buttons[0].click()
    QApplication.processEvents()
    check("HEX 按钮按 HEX 发送", worker.sent == [b"\x68\x12\x00\x41\x16"], worker.sent)
    worker.sent.clear()
    tab._custom_buttons[1].click()
    QApplication.processEvents()
    check("ASCII 按钮按文本发送", worker.sent == [b"AT+INFO?"], worker.sent)

    # 移位
    tab._move_custom_button(0, 1)
    check("下移交换顺序",
          [b["name"] for b in tab._buttons] == ["文本", "查询"],
          [b["name"] for b in tab._buttons])
    tab._move_custom_button(0, -1)
    check("上移无效时不越界（已在首位）",
          [b["name"] for b in tab._buttons] == ["文本", "查询"],
          [b["name"] for b in tab._buttons])
    tab._move_custom_button(1, -1)
    check("上移生效", [b["name"] for b in tab._buttons] == ["查询", "文本"],
          [b["name"] for b in tab._buttons])

    # 编辑
    class FakeEditDialog2(FakeEditDialog):
        def value(self):
            return {"name": "改名", "data": "AA BB", "isHex": True}

    with patch.object(btw, "ButtonEditDialog", FakeEditDialog2):
        tab._edit_custom_button(0)
        QApplication.processEvents()
    check("编辑生效", tab._buttons[0]["name"] == "改名", tab._buttons[0])

    # 导出 / 导入
    export_path = os.path.join(str(SANDBOX), "bt_buttons.json")
    with patch.object(btw.QFileDialog, "getSaveFileName",
                      lambda *a, **k: (export_path, "")):
        tab.btn_custom_export.click()
        QApplication.processEvents()
    check("导出文件存在", os.path.exists(export_path))
    with open(export_path, "r", encoding="utf-8") as handle:
        exported = json.load(handle)
    check("导出内容为按钮列表", isinstance(exported, list) and len(exported) == 2, exported)

    tab._set_buttons([])
    check("清空后无按钮", tab._buttons == [])
    with patch.object(btw.QFileDialog, "getOpenFileName",
                      lambda *a, **k: (export_path, "")):
        tab.btn_custom_import.click()
        QApplication.processEvents()
    check("导入还原 2 条", len(tab._buttons) == 2, tab._buttons)
    check("导入后网格重建", len(tab._custom_buttons) == 2)

    # 删除（question 已打桩为 Yes）
    tab._delete_custom_button(0)
    QApplication.processEvents()
    check("删除生效", len(tab._buttons) == 1, tab._buttons)

    # 全部清除
    tab.btn_custom_clear.click()
    QApplication.processEvents()
    check("全部清除生效", tab._buttons == [], tab._buttons)
    check("清空后显示占位提示", len(tab._custom_buttons) == 0)

    tab.cleanup()


# ── [9] 持久化 ──────────────────────────────────────────────────────────────

def test_persist():
    section("[9] 持久化往返")

    tab = make_tab()
    tab.chk_show_hex.setChecked(False)
    tab.chk_auto_scroll.setChecked(False)
    tab.spin_timeout.setValue(1.25)
    tab.spin_packet_delay.setValue(0.3)
    tab.chk_named_only.setChecked(True)
    tab.spin_parse_lines.setValue(120)
    tab.combo_send_format.setCurrentIndex(
        [i for i in range(tab.combo_send_format.count())
         if tab.combo_send_format.itemData(i) == "ascii"][0])
    tab._set_buttons([{"name": "A", "data": "68 12", "isHex": True}])
    tab._recv_uuids = [RECV_UUID]
    tab._send_uuids = [SEND_UUID]
    tab._save_persisted()
    tab.cleanup()

    check("配置文件落在沙箱", os.path.exists(str(SANDBOX / btw.CONFIG_NAME)))

    tab2 = make_tab()
    check("HEX 显示读回", tab2.chk_show_hex.isChecked() is False)
    check("自动滚动读回", tab2.chk_auto_scroll.isChecked() is False)
    check("切帧超时读回", abs(tab2.spin_timeout.value() - 1.25) < 1e-6, tab2.spin_timeout.value())
    check("包间延迟读回", abs(tab2.spin_packet_delay.value() - 0.3) < 1e-6)
    check("只显示有名称读回", tab2.chk_named_only.isChecked() is True)
    check("解析行数上限读回", tab2.spin_parse_lines.value() == 120)
    check("发送格式读回", tab2._send_mode() == "ascii", tab2._send_mode())
    check("自定义按钮读回", tab2._buttons == [{"name": "A", "data": "68 12", "isHex": True}],
          tab2._buttons)
    check("特征码选择读回",
          tab2._recv_uuids == [RECV_UUID] and tab2._send_uuids == [SEND_UUID],
          (tab2._recv_uuids, tab2._send_uuids))
    check("读回后按钮网格已建好", len(tab2._custom_buttons) == 1)
    tab2.cleanup()

    # 坏配置宽容
    cfg = SANDBOX / btw.CONFIG_NAME
    cfg.write_text("{ 坏 JSON", encoding="utf-8")
    tab3 = make_tab()
    check("坏配置回落默认（不抛）",
          tab3._buttons == [] and abs(tab3.spin_timeout.value()
                                      - core.DEFAULT_PACKET_TIMEOUT) < 1e-6,
          (tab3._buttons, tab3.spin_timeout.value()))
    tab3.cleanup()


# ── [10] 日志文件 ───────────────────────────────────────────────────────────

def test_log_file():
    section("[10] 日志自动保存")

    worker = FakeBluetoothWorker()
    tab = make_tab(worker)
    worker.become_connected()
    QApplication.processEvents()

    tab.chk_auto_save_log.setChecked(True)
    QApplication.processEvents()
    check("自动保存已开启", tab._log_writer is not None)
    check("日志状态行显示正在保存", "正在保存" in tab.lbl_log_state.text(),
          tab.lbl_log_state.text())
    log_dir = tab.log_dir()
    check("默认日志目录为数据目录下的 Output",
          os.path.basename(log_dir) == "Output", log_dir)

    worker.frame_received.emit(RECV_UUID, b"\x68\x12")
    worker.frame_received.emit(RECV_UUID, b"\xAA\xBB")
    QApplication.processEvents()
    text = log_text(tab)
    path = tab._log_writer.path

    lines = [ln for ln in text.splitlines() if "RX·" in ln]
    check("窗口里有 2 条接收日志", len(lines) == 2, len(lines))

    tab._close_log_file()
    check("关闭后写入器释放", tab._log_writer is None)
    check("关闭后状态行显示已保存", "已保存" in tab.lbl_log_state.text(),
          tab.lbl_log_state.text())

    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    check("文件头写了标题", btw.LOG_HEADER_TITLE in content, content[:200])
    check("文件里能看到接收日志（内容镜像）",
          content.count("RX·") == 2, content.count("RX·"))
    check("文件尾写了统计行", "收发统计" in content)
    check("文件尾写了停止时间", "停止时间" in content)

    # 写失败 → 关闭自动保存并提示（打桩 `write_line` 返回 False，并留一条 error 说明）
    # 注意：`error` 是 `LogFileWriter` 的**实例属性**，patch.object 打不到它，
    # 只能在假的 write_line 里自己塞。
    def _fail_write(self, *_args, **_kwargs):
        self.error = "磁盘满（假）"
        return False

    tab2 = make_tab()
    with patch.object(btw.LogFileWriter, "write_line", _fail_write):
        tab2.chk_auto_save_log.setChecked(True)
        QApplication.processEvents()
        tab2._append_log("触发写失败", "sys")
    check("写失败后自动关掉自动保存", tab2.chk_auto_save_log.isChecked() is False)
    check("写失败有日志说明", "写日志文件失败" in log_text(tab2), log_text(tab2)[-200:])
    tab2.cleanup()
    tab.cleanup()


# ── [11] 收尾与主题 ─────────────────────────────────────────────────────────

def test_cleanup_and_theme():
    section("[11] 收尾 / 主题")

    worker = FakeBluetoothWorker()
    tab = make_tab(worker)
    check("cleanup 幂等（两次不抛）", (tab.cleanup(), tab.cleanup()) == (None, None))
    check("cleanup 会 shutdown 蓝牙线程", worker.shutdowns >= 1, worker.shutdowns)
    check("cleanup 停止定时器", tab._status_timer.isActive() is False)

    # restyle_for_theme 不抛，且设备表可重建
    worker2 = FakeBluetoothWorker()
    tab2 = make_tab(worker2)
    worker2.device_found.emit("N", "AA:09", -60)
    worker2.scan_finished.emit(1)
    QApplication.processEvents()
    try:
        tab2.restyle_for_theme(True)
        tab2.restyle_for_theme(False)
        ok = True
    except Exception as exc:  # noqa: BLE001
        ok = False
        check("restyle_for_theme 不抛", False, exc)
    if ok:
        check("restyle_for_theme 不抛", True)
        check("restyle 后设备表仍完整", tab2.device_table.rowCount() == 1,
              tab2.device_table.rowCount())
    tab2.cleanup()

    # 注入接口可用（main_gui 接线契约）
    tab3 = make_tab()
    calls = []
    tab3.set_parse_provider(lambda f, p: ("s", [("a", "b", "c", "")]))
    tab3.set_protocol_provider(lambda: 5)
    tab3.set_send_to_single_handler(lambda h: calls.append(h))
    check("协议回调生效", tab3._protocol_from_main() == 5)
    check("注入后协议下拉已重建（含「不解析」）",
          tab3.combo_protocol.count() >= 2, tab3.combo_protocol.count())
    tab3._on_parse_toggled(True)
    QApplication.processEvents()
    check("勾选解析且原本未选时跟随主窗口协议",
          tab3.combo_protocol.currentData() == 5, tab3.combo_protocol.currentData())
    tab3.cleanup()


# ── [12] 反例自检 ───────────────────────────────────────────────────────────

STD_UUID = "0000%s-0000-1000-8000-00805f9b34fb"


def _bch(code, send=False, recv=False, desc="", svc="fff0"):
    """构造一条特征码信息（与 worker `_collect_characteristics` 同形）。"""
    uuid = STD_UUID % code
    service = STD_UUID % svc
    return {"uuid": uuid, "short": core.short_uuid(uuid),
            "service_uuid": service, "service_short": core.short_uuid(service),
            "properties": [], "description": desc,
            "can_send": bool(send), "can_recv": bool(recv), "max_write": 20}


CHARS_MIXED = [
    _bch("2a00", desc="Device Name", svc="1800"),               # 标准 GATT（只有读）
    _bch("2a19", send=True, desc="Battery Level", svc="180f"),  # 第一个「可写」（旧逻辑会选它）
    _bch("ffe1", send=True, recv=True, desc="", svc="ffe0"),    # 真正的透传回环
    _bch("fe59", send=True, desc="DFU Control", svc="fe59"),    # 降权
]


def test_char_autodetect_and_probe():
    section("[11] 特征码自动优选 / 一键探测 / 按设备记忆（1.23.79）")

    # ── 自动优选：必须命中 0xFFE1（反例：旧「取第一个可用」会选 0x2A19）──
    worker = FakeBluetoothWorker()
    tab = make_tab(worker)
    worker.become_connected(name="透传模块", address="AA:11")
    QApplication.processEvents()
    worker.characteristics_updated.emit(CHARS_MIXED)
    QApplication.processEvents()
    check("自动优选：发送 = 0xFFE1（不是第一个可写的 0x2A19）",
          worker.send_uuids() == [STD_UUID % "ffe1"], str(worker.send_uuids()))
    check("自动优选：接收 = 同一条码（回环）",
          worker.recv_uuids() == [STD_UUID % "ffe1"], str(worker.recv_uuids()))
    text11 = log_text(tab)
    check("自动优选：日志含「自动选择特征码」+ 依据（厂商透传族谱）",
          "自动选择特征码" in text11 and "厂商透传族谱" in text11, text11[-160:])
    check("状态行给出收发摘要",
          "发送 → 0xFFE1" in tab.lbl_status.text()
          and "接收 → 0xFFE1" in tab.lbl_status.text(), tab.lbl_status.text())
    check("按设备地址落盘记忆（source=auto）",
          tab._settings["char_map"].get("AA:11", {}).get("send") == [STD_UUID % "ffe1"]
          and tab._settings["char_map"]["AA:11"]["source"] == "auto",
          str(tab._settings.get("char_map")))

    # ── 同设备重连 → 沿用；换设备 → 重新优选 ──
    worker.become_disconnected()
    worker.become_connected(name="透传模块", address="AA:11")
    QApplication.processEvents()
    worker.characteristics_updated.emit(CHARS_MIXED)
    QApplication.processEvents()
    check("同设备重连：沿用上次选择（日志注明）",
          "沿用上次" in log_text(tab), log_text(tab)[-160:])
    worker.become_disconnected()
    worker.become_connected(name="别的模块", address="AA:22")
    QApplication.processEvents()
    worker.characteristics_updated.emit(CHARS_MIXED)
    QApplication.processEvents()
    check("换设备（未记过）→ 重新优选并记住新地址",
          "自动选择特征码" in log_text(tab) and "AA:22" in tab._settings["char_map"],
          str(sorted(tab._settings["char_map"])))

    # ── 一键探测：命中（单候选，写完有回包）──
    worker.become_disconnected()
    worker.become_connected(name="单通道模块", address="AA:33")
    QApplication.processEvents()
    tab._settings["char_map"] = {}
    worker.characteristics_updated.emit([_bch("ffe1", send=True, recv=True, svc="ffe0")])
    QApplication.processEvents()
    tab.edit_send.setText("68 12 00")
    worker.sent.clear()
    tab.btn_probe_chars.click()
    QApplication.processEvents()
    check("探测：写入的是发送框内容（优先于默认帧）",
          worker.sent == [bytes.fromhex("681200")], str(worker.sent))
    check("探测中：发送与探测按钮都禁用",
          tab.btn_probe_chars.isEnabled() is False and tab.btn_send.isEnabled() is False)
    check("探测中：状态行不误导（仍显示当前通道）", "发送 →" in tab.lbl_status.text())
    worker.data_sent.emit(bytes.fromhex("681200"))
    QApplication.processEvents()
    worker.frame_received.emit(STD_UUID % "ffe1", b"\x68\x12")
    QApplication.processEvents()
    text11 = log_text(tab)
    check("探测命中：日志给出确认与回包字节数",
          "一键探测已确认" in text11 and "收到 2 字节回包" in text11, text11[-200:])
    check("探测命中：锁定该通道并按设备记忆 source=probe",
          worker.send_uuids() == [STD_UUID % "ffe1"]
          and tab._settings["char_map"]["AA:33"]["source"] == "probe",
          str(tab._settings["char_map"].get("AA:33")))
    check("探测结束：按钮恢复、只写过一次数据",
          tab.btn_probe_chars.isEnabled() is True and len(worker.sent) == 1,
          f"{tab.btn_probe_chars.isEnabled()} / {len(worker.sent)}")

    # ── 一键探测：全败（两个候选都有接收通道，但都没回包）──
    tab._settings["char_map"] = {}
    worker.become_disconnected()
    worker.become_connected(name="不回包模块", address="AA:44")
    QApplication.processEvents()
    worker.characteristics_updated.emit([
        _bch("ffe1", send=True, recv=True, svc="ffe0"),
        _bch("ffe2", send=True, recv=True, svc="ffe0"),
    ])
    QApplication.processEvents()
    before_send = list(worker.send_uuids())
    tab.edit_send.setText("")
    worker.sent.clear()
    tab.btn_probe_chars.click()
    QApplication.processEvents()
    for _ in range(2):                      # 两个候选都「写完没回包」
        worker.data_sent.emit(b"AT")
        QApplication.processEvents()
        tab._probe_timeout()
        QApplication.processEvents()
    text11 = log_text(tab)
    check("探测全败：逐候选给出原因（写入成功但无回包）",
          text11.count("✗") >= 2 and "无回包" in text11, text11[-240:])
    check("探测全败：保留原选择、不写 probe 记忆",
          worker.send_uuids() == before_send
          and tab._settings["char_map"].get("AA:44", {}).get("source") != "probe",
          f"{worker.send_uuids()} / {tab._settings['char_map'].get('AA:44')}")
    check("探测全败：按钮恢复可用", tab.btn_probe_chars.isEnabled() is True)

    # ── 探测载荷：空发送框 → 默认帧；HEX 写错 → 拒绝且不写 ──
    tab.edit_send.setText("")
    worker.sent.clear()
    tab.btn_probe_chars.click()
    QApplication.processEvents()
    check("发送框为空 → 使用默认探测帧（日志注明 + 写出 AT）",
          worker.sent == [b"AT"] and "使用默认探测帧" in log_text(tab), str(worker.sent))
    worker.data_sent.emit(b"AT")
    QApplication.processEvents()
    worker.frame_received.emit(STD_UUID % "ffe1", b"\x00")
    QApplication.processEvents()
    tab.edit_send.setText("68 1")           # HEX 位数不成对 → 必须拒绝
    worker.sent.clear()
    tab.btn_probe_chars.click()
    QApplication.processEvents()
    check("探测载荷 HEX 写错 → 拒绝且不写任何数据",
          worker.sent == [] and "未写入任何数据" in log_text(tab), str(worker.sent))
    tab.edit_send.setText("")

    # ── 「特征码…」对话框：预选 + 优选置顶 + 不可用方向文字标注 ──
    dialog = btw.CharacteristicSelectDialog(CHARS_MIXED)
    try:
        check("对话框：发送列首条 = 优选码 0xFFE1 且已预选",
              "0xFFE1" in dialog._send_list.item(0).text()
              and dialog._send_list.item(0).checkState() == Qt.CheckState.Checked,
              dialog._send_list.item(0).text())
        check("对话框：接收列同样预选 0xFFE1",
              "0xFFE1" in dialog._recv_list.item(0).text()
              and dialog._recv_list.item(0).checkState() == Qt.CheckState.Checked,
              dialog._recv_list.item(0).text())
        send_labels = [dialog._send_list.item(i).text()
                       for i in range(dialog._send_list.count())]
        check("对话框：不可写方向**文字标注**（置灰在 QSS 主题下看不见）",
              any("（不可写）" in t for t in send_labels), str(send_labels))
        hints = [w.text() for w in dialog.findChildren(QLabel) if "推荐：" in w.text()]
        check("对话框：顶部给出推荐依据", bool(hints), str(hints[:1])[:120])
        check("对话框：点确定返回优选结果",
              dialog.selected_send() == [STD_UUID % "ffe1"]
              and dialog.selected_recv() == [STD_UUID % "ffe1"],
              f"{dialog.selected_send()} / {dialog.selected_recv()}")
    finally:
        dialog.deleteLater()

    tab.cleanup()


# ── [12] MTU / 写上限实时化（1.23.80）─────────────────────────────────────

def test_mtu_live_limits():
    section("[12] MTU / 写上限实时化（1.23.80）")

    worker = FakeBluetoothWorker()
    tab = make_tab(worker)
    # 模拟「连接那一刻协商结果还没回来」：MTU 仍是 ATT 默认值
    worker.become_connected(mtu=core.MTU_DEFAULT)
    QApplication.processEvents()
    check("MTU 为默认值时文案明示「ATT 默认值 / 协商结果未回」",
          "23" in tab.lbl_info_mtu.text() and "ATT 默认值" in tab.lbl_info_mtu.text()
          and "20" in tab.lbl_info_mtu.text(),
          tab.lbl_info_mtu.text())

    chars = [
        {"uuid": RECV_UUID, "short": "0xFFF1", "service_short": "0xFFF0",
         "service_uuid": "0000fff0-0000-1000-8000-00805f9b34fb",
         "properties": ["notify"], "description": "上报通道",
         "can_recv": True, "can_send": False, "max_write": 0},
        {"uuid": SEND_UUID, "short": "0xFFF2", "service_short": "0xFFF0",
         "service_uuid": "0000fff0-0000-1000-8000-00805f9b34fb",
         "properties": ["write", "write-without-response"], "description": "下发通道",
         "can_recv": False, "can_send": True, "max_write": 20},
    ]
    worker.characteristics_updated.emit(chars)
    QApplication.processEvents()
    sets_before = worker.char_sets
    recv_before, send_before = worker.recv_uuids(), worker.send_uuids()

    # 协商结果到了（worker 侧 `_refresh_live_limits` 会发这个信号）
    chars2 = [dict(c) for c in chars]
    chars2[1]["max_write"] = 244
    worker.mtu_updated.emit(247, chars2)
    QApplication.processEvents()
    check("MTU 标签更新为协商后的值（无需重连）",
          "247" in tab.lbl_info_mtu.text() and "ATT 默认值" not in tab.lbl_info_mtu.text(),
          tab.lbl_info_mtu.text())
    check("新上限写进界面缓存（对话框下次打开即最新）",
          any(int(c.get("max_write") or 0) == 244 for c in tab._chars),
          [(c.get("short"), c.get("max_write")) for c in tab._chars])
    check("实时更新**不**重订阅、不改写特征码选择",
          worker.char_sets == sets_before
          and worker.recv_uuids() == recv_before and worker.send_uuids() == send_before,
          (worker.char_sets, sets_before, worker.recv_uuids(), worker.send_uuids()))

    # 打开中的「特征码…」对话框：刷新读数但保留勾选
    dialog = btw.CharacteristicSelectDialog(chars, [RECV_UUID], [SEND_UUID])
    tab._chars_dialog = dialog
    try:
        checked = dialog.selected_send()
        row = next(i for i in range(dialog._send_list.count())
                   if "0xFFF2" in dialog._send_list.item(i).text())
        dialog.refresh_chars(chars2)
        check("对话框刷新后保留勾选", dialog.selected_send() == checked, dialog.selected_send())
        check("对话框刷新后显示新上限",
              "244" in dialog._send_list.item(row).toolTip(),
              dialog._send_list.item(row).toolTip()[:80])
    finally:
        tab._chars_dialog = None
        dialog.deleteLater()

    # 模态期间到达：`_on_choose_characteristics` 必须把引用交给页面并转调 refresh_chars
    class RecordingDialog:
        refreshed = 0
        last = None
        DialogCode = QDialog.DialogCode

        def __init__(self, *a, **k):
            type(self).refreshed = 0
            type(self).last = None

        def exec(self):
            # 模拟「对话框开着的时候 MTU 协商结果到达」
            worker.mtu_updated.emit(247, chars2)
            QApplication.processEvents()
            return QDialog.DialogCode.Rejected

        def selected_recv(self):
            return []

        def selected_send(self):
            return []

        def refresh_chars(self, characteristics):
            type(self).refreshed += 1
            type(self).last = characteristics

    with patch.object(btw, "CharacteristicSelectDialog", RecordingDialog):
        tab.btn_chars.click()
        QApplication.processEvents()
    check("对话框打开期间到达的实时上限会被刷新",
          RecordingDialog.refreshed == 1
          and any(int(c.get("max_write") or 0) == 244
                  for c in (RecordingDialog.last or [])),
          (RecordingDialog.refreshed, RecordingDialog.last))
    check("对话框关闭后引用被清空（不留悬空引用）", tab._chars_dialog is None)

    tab.cleanup()


# ── [13] 自定义按钮的「协议 + 地址」（1.23.81）──────────────────────────────

DLT645_FRAME = "68 00 00 00 00 00 00 68 11 04 33 33 34 33 B2 16"


def test_button_address():
    section("[13] 自定义按钮：协议 + 地址替换（1.23.81）")

    # ── 对话框：协议下拉 + 动态地址框 + 实时预览 ──
    dialog = btw.ButtonEditDialog()
    try:
        check("协议下拉含「（不处理）」+ 6 个支持协议",
              dialog.combo_protocol.count() == 1 + len(fix.SUPPORTED_PROTOCOLS),
              dialog.combo_protocol.count())
        check("默认不处理 → 地址区隐藏",
              dialog.combo_protocol.currentData() is None and dialog.addr_group.isVisible() is False)

        dialog.combo_protocol.setCurrentIndex(dialog.combo_protocol.findData(6))
        QApplication.processEvents()
        check("协议6 → 出现 1 个地址框（表地址）",
              list(dialog._addr_edits) == ["addr"]
              and dialog.addr_form.labelForField(dialog._addr_edits["addr"]) is not None,
              list(dialog._addr_edits))
        dialog.combo_protocol.setCurrentIndex(dialog.combo_protocol.findData(0))
        QApplication.processEvents()
        check("协议0 → 两个地址框（源/目的）",
              list(dialog._addr_edits) == ["src", "dst"], list(dialog._addr_edits))
        check("字段提示来自声明（含写法说明）",
              "12 位" in dialog._addr_edits["src"].placeholderText(),
              dialog._addr_edits["src"].placeholderText())

        # 切到 698 需要两个框（SA/CA），并保持已有输入不丢
        dialog._addr_edits["src"].setText("000000000009")
        dialog.combo_protocol.setCurrentIndex(dialog.combo_protocol.findData(8))
        QApplication.processEvents()
        check("协议8 → SA/CA 两框", list(dialog._addr_edits) == ["sa", "ca"],
              list(dialog._addr_edits))
        dialog.combo_protocol.setCurrentIndex(dialog.combo_protocol.findData(0))
        QApplication.processEvents()
        check("切回协议0 → 之前填的源地址保留",
              dialog._addr_edits["src"].text() == "000000000009",
              dialog._addr_edits["src"].text())

        # 预览：内容框放真帧 → 提示给出字节与校验变化
        dialog.edit_content.setPlainText(DLT645_FRAME)
        dialog.combo_protocol.setCurrentIndex(dialog.combo_protocol.findData(6))
        QApplication.processEvents()
        dialog._addr_edits["addr"].setText("000000000033")
        QApplication.processEvents()
        hint = dialog.lbl_addr_hint.text()
        check("地址提示给出「将写入的字节」", "33 00 00 00 00 00" in hint, hint[:160])
        check("内容框可解析时给出替换后预览（含校验变化）",
              "按当前报文预览" in hint and "校验和" in hint, hint[:200])

        dialog._addr_edits["addr"].setText("00 01")
        QApplication.processEvents()
        check("非法地址（在线字节长度不符）→ 提示报错", "⚠" in dialog.lbl_addr_hint.text(),
              dialog.lbl_addr_hint.text()[:120])
        dialog._addr_edits["addr"].setText("000000000033")
        QApplication.processEvents()

        # value() 往返
        saved = dialog.value()
        check("value() 带 protocol 与 addr", saved.get("protocol") == 6
              and saved.get("addr") == {"addr": "000000000033"}, saved)
        check("value() 仍保留原字段", saved.get("data") == DLT645_FRAME and saved.get("isHex") is True)

        # 选了协议但地址为空 → 不允许保存
        dialog._addr_edits["addr"].setText("")
        QApplication.processEvents()
        accepted = {"v": False}
        with patch.object(btw.QDialog, "accept", lambda self: accepted.update(v=True)):
            dialog._on_accept()
        check("选了协议但地址为空 → 拦下（不 accept）", accepted["v"] is False, accepted)

        # 编辑时回填已有参数
        dialog2 = btw.ButtonEditDialog(button={
            "name": "抄读", "data": DLT645_FRAME, "isHex": True,
            "protocol": 6, "addr": {"addr": "000000000099"},
        })
        try:
            check("编辑回填：协议与地址都回来了",
                  dialog2.combo_protocol.currentData() == 6
                  and dialog2._addr_edits["addr"].text() == "000000000099",
                  (dialog2.combo_protocol.currentData(), dialog2._addr_edits["addr"].text()))
        finally:
            dialog2.deleteLater()
    finally:
        dialog.deleteLater()

    # ── 发送路径：点按钮时替换 + 重算；发送框保持原模板 ──
    worker = FakeBluetoothWorker()
    tab = make_tab(worker)
    worker.become_connected()          # 发送路径要求已连接（否则只提示、不落到 worker）
    QApplication.processEvents()
    bound = [{
        "name": "抄读（换地址）", "data": DLT645_FRAME, "isHex": True,
        "protocol": 6, "addr": {"addr": "000000000033"},
    }]
    tab._set_buttons(bound)
    tab.btn_send.setEnabled(True)
    worker.sent.clear()
    tab._on_custom_clicked(0)
    QApplication.processEvents()
    expect = fix.apply(bytes.fromhex(DLT645_FRAME.replace(" ", "")), 6, {"addr": "000000000033"})
    check("点按钮发出的是**替换后**的帧",
          expect.ok and worker.sent == [expect.frame], (worker.sent, expect.error))
    check("替换后帧地址为 33 00 00 00 00 00 且校验已重算",
          bool(worker.sent) and worker.sent[0][1:7] == bytes.fromhex("330000000000")
          and worker.sent[0][-2] == 0xE5,
          worker.sent[0].hex(" ") if worker.sent else "")
    check("发送框仍是**原始模板**（未被改写）",
          tab.edit_send.text() == DLT645_FRAME, tab.edit_send.text())
    check("日志说明改了什么（地址 + 校验 旧→新）",
          "地址域 表地址" in log_text(tab) and "校验和" in log_text(tab),
          log_text(tab)[-200:])

    # 未绑定协议/地址的按钮 → 行为与改动前一致（原始字节）
    tab._set_buttons([{"name": "原样", "data": DLT645_FRAME, "isHex": True}])
    worker.sent.clear()
    tab._on_custom_clicked(0)
    QApplication.processEvents()
    check("未绑定参数的按钮逐字节原样发送",
          worker.sent == [bytes.fromhex(DLT645_FRAME.replace(" ", ""))], worker.sent)

    # 地址非法 → 一个字节都不发 + 日志外显
    tab._set_buttons([{
        "name": "坏地址", "data": DLT645_FRAME, "isHex": True,
        "protocol": 6, "addr": {"addr": "00 01"},
    }])
    worker.sent.clear()
    tab._on_custom_clicked(0)
    QApplication.processEvents()
    check("地址非法 → 不发送任何字节", worker.sent == [], worker.sent)
    check("地址非法 → 日志写明未发送原因", "未发送" in log_text(tab), log_text(tab)[-160:])

    # 按钮 tooltip 标注绑定的协议/地址
    tab._set_buttons(bound)
    QApplication.processEvents()
    check("按钮 tooltip 标注地址替换（协议与地址）",
          "地址替换" in tab._custom_buttons[0].toolTip()
          and "000000000033" in tab._custom_buttons[0].toolTip(),
          tab._custom_buttons[0].toolTip())

    # 落盘往返：protocol/addr 不丢
    check("落盘后按钮参数保留（_buttons 里的规范化结果）",
          tab._buttons[0].get("protocol") == 6
          and tab._buttons[0].get("addr") == {"addr": "000000000033"},
          tab._buttons[0])
    tab.cleanup()


# ── [14] 自定义报文区空间治理（1.23.82）──────────────────────────────────

def _custom_buttons(count: int):
    return [{"name": f"报文{i}", "data": "68 11", "isHex": True} for i in range(count)]


def test_custom_area_space():
    section("[14] 自定义报文区空间治理（1.23.82）")

    tab = make_tab(FakeBluetoothWorker())
    tab.resize(1200, 800)
    tab.show()
    settle()

    check("按钮区在专用滚动容器内（最小高度不被内层网格撑大）",
          isinstance(tab.custom_scroll, btw.ButtonScrollArea)
          and tab.custom_scroll.widget() is tab.custom_host)
    check("竖向分栏器存在、且不允许把任一侧拖成 0",
          isinstance(tab.right_splitter, QSplitter)
          and tab.right_splitter.orientation() == Qt.Orientation.Vertical
          and tab.right_splitter.childrenCollapsible() is False)
    check("分栏上侧就是日志组",
          tab.right_splitter.count() == 2
          and isinstance(tab.right_splitter.widget(0), QGroupBox))

    # ── 上下限：下限 1 行、上限按内容（空间够就不滚动）──
    tab._set_buttons(_custom_buttons(10))
    settle()
    low, high = tab._custom_scroll_limits()
    row_h = max(b.sizeHint().height() for b in tab._custom_buttons)
    check("下限 = 1 行按钮高度",
          low == row_h + tab.custom_grid.spacing() * 0 + 8, (low, row_h))
    check("上限 = 内容高度（10 个按钮 = 4 行，> 3 行）",
          high >= 4 * row_h and high > 3 * row_h, (high, row_h))
    check("限制已套用到容器",
          tab.custom_scroll.maximumHeight() == high
          and tab.custom_scroll.minimumSizeHint().height() == low,
          (tab.custom_scroll.maximumHeight(), tab.custom_scroll.minimumSizeHint().height()))

    # ── D1：腾出空间后按钮要显示全（不再无谓滚动）──
    tab.right_splitter.setSizes([200, 600])
    settle(8)
    check("日志上拖腾出空间后：10 个按钮**全部显示、无滚动条**",
          tab.custom_scroll.verticalScrollBar().maximum() == 0,
          (tab.custom_scroll.height(), high,
           tab.custom_scroll.verticalScrollBar().maximum()))
    check("按钮区确实吃到了腾出的空间（高度 = 内容高度）",
          tab.custom_scroll.height() >= high - 2,
          (tab.custom_scroll.height(), high))

    # ── 空间真不够时仍然滚动（64 个按钮 = 22 行）──
    tab._set_buttons(_custom_buttons(64))
    settle(8)
    high64 = tab._custom_scroll_limits()[1]
    bar = tab.custom_scroll.verticalScrollBar()
    check("按钮多于可用空间时才出现滚动条",
          bar.maximum() > 0 and tab.custom_scroll.height() <= high64,
          (tab.custom_scroll.height(), high64, bar.maximum()))
    check("按钮没有被压扁（高度 ≥ sizeHint；否则是「压扁」不是「滚动」）",
          all(b.height() >= b.sizeHint().height() - 1 for b in tab._custom_buttons),
          [(b.height(), b.sizeHint().height()) for b in tab._custom_buttons[:3]])

    # ── 默认分栏下日志仍不被挤没 ──
    tab.right_splitter.setSizes(list(core.RIGHT_SPLIT_DEFAULT))
    settle(8)
    log_group = tab.right_splitter.widget(0)
    check("默认分栏 + 64 个按钮：日志不被挤没",
          log_group.height() >= 200
          and log_group.height() >= log_group.minimumSizeHint().height(),
          (log_group.height(), log_group.minimumSizeHint().height()))

    # ── D2：编辑工具栏常驻（不随折叠收起）──
    check("编辑按钮不在折叠内容里（折叠区外面）",
          not tab.custom_group.content.isAncestorOf(tab.btn_custom_add))

    expanded_height = tab.custom_group.height()
    tab.custom_group.set_expanded(False)
    settle()
    check("收起后按钮网格被隐藏", tab.custom_group.is_content_hidden() is True)
    check("收起后本区只剩标题行", tab.custom_group.height() <= expanded_height - 10,
          (expanded_height, tab.custom_group.height()))
    check("**收起后编辑按钮仍可见可用**（常驻底部）",
          tab.btn_custom_add.isVisible() is True
          and tab.btn_custom_clear.isVisible() is True)
    check("收起状态写进配置（custom_collapsed=True）",
          tab._settings.get("custom_collapsed") is True, tab._settings.get("custom_collapsed"))
    tab.custom_group.set_expanded(True)
    settle()
    check("再展开恢复正常且配置同步",
          tab.custom_group.is_content_hidden() is False
          and tab._settings.get("custom_collapsed") is False)

    # ── 分栏尺寸采集与重启恢复 ──
    tab.right_splitter.setSizes([520, 300])
    settle()
    sizes = tab.right_splitter.sizes()
    check("分栏尺寸被写进设置", tab._collect_settings().get("right_split") == list(sizes), sizes)
    tab.custom_group.set_expanded(False)
    settle()
    tab._save_persisted()
    tab.cleanup()

    tab2 = make_tab(FakeBluetoothWorker())
    tab2.resize(1200, 800)
    tab2.show()
    settle()
    check("重启后保持收起状态", tab2.custom_group.is_content_hidden() is True)
    check("重启后编辑按钮仍然可见", tab2.btn_custom_add.isVisible() is True)
    got = tab2.right_splitter.sizes()
    check("重启后恢复分栏尺寸（±6px 容差）",
          len(got) == 2 and abs(got[0] - sizes[0]) <= 6 and abs(got[1] - sizes[1]) <= 6,
          (list(sizes), got))
    tab2.cleanup()


def test_negatives():
    section("[15] 反例自检（判据有效）")

    worker = FakeBluetoothWorker()
    tab = make_tab(worker)
    check("未连接时发送不落到 worker",
          (tab.edit_send.setText("68 12"), tab.btn_send.click(),
           QApplication.processEvents(), worker.sent == [])[-1])
    check("未连接时日志有提示", "未连接" in log_text(tab) or "请先连接" in log_text(tab))
    check("未连接时特征码按钮置灰", tab.btn_chars.isEnabled() is False)
    check("自动格式下纯文本不会被当成 HEX",
          btw.parse_plain_text("zz")[0] == b"zz")
    check("parse_button_lines 对空文本返回空",
          btw.parse_button_lines("")[0] == [])
    tab.cleanup()


def main():
    print("=" * 64)
    print("蓝牙工具页 bluetooth_tool_widget offscreen 回归")
    print("=" * 64)

    app = QApplication.instance() or QApplication([])
    del app

    test_helpers()
    test_build()
    test_scan_ui()
    test_connect_and_characteristics()
    test_rx_tx_and_parse()
    test_custom_buttons()
    test_persist()
    test_log_file()
    test_cleanup_and_theme()
    test_char_autodetect_and_probe()
    test_mtu_live_limits()
    test_button_address()
    test_custom_area_space()
    test_negatives()

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
