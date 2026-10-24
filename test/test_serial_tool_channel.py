# -*- coding: utf-8 -*-
"""串口工具「通道」回归（1.23.99）：串口 / 蓝牙复用。

覆盖：
  [1] 默认走串口通道，通道下拉只有 串口/蓝牙 两项
  [2] 切到蓝牙但未连接 → 发送禁用 + 提示去「蓝牙工具」页连接
  [3] 蓝牙已连接 → 发送可用、状态显示设备名、写入口转调 send_data
  [4] 通道隔离：非当前通道收到的字节一律丢弃（两侧都验）
  [5] 通道持久化（_collect_params / _apply_params）

运行: QT_QPA_PLATFORM=offscreen python -u test/test_serial_tool_channel.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # noqa: BLE001
    pass

from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

# 沙箱：本页会落盘 serial_tool_config.json，必须重定向（否则污染开发机数据目录）
_config_sandbox.install()

import serial_tool_widget as stw  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

APP = QApplication.instance() or QApplication([])

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {msg}")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg}")


class FakeSerial(QObject):
    """鸭子类型的串口 worker（与真实 SerialWorker 同形）。"""

    raw_data_received = Signal(bytes)
    error_occurred = Signal(str)
    connection_changed = Signal(bool)

    def __init__(self, is_open=True):
        super().__init__()
        self.written = []
        self._is_open = bool(is_open)

    def is_open(self):
        return self._is_open

    def write_raw(self, data):
        self.written.append(bytes(data))
        return True


class FakeBluetooth(QObject):
    """鸭子类型的蓝牙 worker（只实现串口工具用到的信号与方法）。"""

    frame_received = Signal(str, bytes)
    notification_received = Signal(str, bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)
    mtu_updated = Signal(int, list)

    def __init__(self, connected=False, name="BLE-测试设备"):
        super().__init__()
        self.sent = []
        self._connected = bool(connected)
        self._name = name

    def is_connected(self):
        return self._connected

    def device_name(self):
        return self._name

    def device_address(self):
        return "AA:BB:CC:DD:EE:FF"

    def send_data(self, data, single_write=False):
        if not self._connected:
            return False
        self.sent.append(bytes(data))
        return True

    def set_connected(self, ok):
        """模拟真实 BluetoothWorker：连接态变化时同步发信号。"""
        self._connected = bool(ok)
        self.connection_changed.emit(self._connected)


def _index_of(widget, key):
    return widget.combo_channel.findData(key)


# ── [1] 默认通道 ─────────────────────────────────────────────────────
def test_default_channel():
    w = stw.SerialToolWidget()
    check(w.channel() == stw.CHANNEL_SERIAL, "默认通道是串口")
    check(w.combo_channel.count() == 2, "通道下拉只有 2 项")
    check(w.combo_channel.itemData(1) == stw.CHANNEL_BLUETOOTH, "第二项是蓝牙")
    check(w.btn_start.isEnabled() is False, "未连接时「开始发送」禁用")
    check(w.lbl_conn.text() in ("未连接", "已连接"), "状态标签已初始化")


# ── [2] 切蓝牙但未连接 ──────────────────────────────────────────────
def test_switch_to_bluetooth_without_worker():
    w = stw.SerialToolWidget()
    w.combo_channel.setCurrentIndex(_index_of(w, stw.CHANNEL_BLUETOOTH))
    check(w.channel() == stw.CHANNEL_BLUETOOTH, "已切到蓝牙通道")
    check(w.btn_start.isEnabled() is False, "蓝牙未连接 → 发送禁用")
    check("蓝牙未连接" in w.lbl_conn.text(), "状态显示「蓝牙未连接」")
    check("蓝牙工具" in w.lbl_port.text(), "提示去「蓝牙工具」页连接")
    check(w._channel_ready() is False, "_channel_ready() 为 False")
    check(w._send_target().write_raw(b"\x01") is False,
          "未连接时写入返回 False（不假装成功）")


# ── [3] 蓝牙已连接 ──────────────────────────────────────────────────
def test_bluetooth_connected():
    w = stw.SerialToolWidget()
    bt = FakeBluetooth(connected=True, name="NB-698-模块")
    w.set_bluetooth_provider(lambda: bt)
    w.combo_channel.setCurrentIndex(_index_of(w, stw.CHANNEL_BLUETOOTH))
    check(w.btn_start.isEnabled() is True, "蓝牙已连接 → 发送可用")
    check("NB-698-模块" in w.lbl_conn.text(), "状态显示蓝牙设备名")
    check(w._channel_ready() is True, "_channel_ready() 为 True")

    target = w._send_target()
    ok = target.write_raw(b"\x68\xAA\x16")
    check(ok is True and bt.sent == [b"\x68\xAA\x16"],
          "写入口把 write_raw 转成 send_data")

    # 蓝牙断开 → 立刻反映到界面与可用性
    bt.set_connected(False)
    check(w.btn_start.isEnabled() is False, "蓝牙断开 → 发送再次禁用")
    check(w._send_target().write_raw(b"\x68") is False, "断开后写入失败")


# ── [4] 通道隔离 ────────────────────────────────────────────────────
def test_channel_isolation():
    w = stw.SerialToolWidget()
    ser = FakeSerial(True)
    bt = FakeBluetooth(True)
    w.set_serial_worker(ser)
    w.set_bluetooth_provider(lambda: bt)

    # 串口通道：串口数据进、蓝牙帧丢
    w.combo_channel.setCurrentIndex(_index_of(w, stw.CHANNEL_SERIAL))
    base = w._rx_bytes
    ser.raw_data_received.emit(b"\x68\x01")
    check(w._rx_bytes == base + 2, "串口通道：串口数据进入接收")
    base = w._rx_bytes
    bt.frame_received.emit("uuid-rx", b"\x68\x02")
    check(w._rx_bytes == base, "串口通道：蓝牙帧被丢弃（不串台）")

    # 蓝牙通道：蓝牙帧进、串口数据丢
    w.combo_channel.setCurrentIndex(_index_of(w, stw.CHANNEL_BLUETOOTH))
    base = w._rx_bytes
    ser.raw_data_received.emit(b"\x68\x03")
    check(w._rx_bytes == base, "蓝牙通道：串口数据被丢弃（不串台）")
    base = w._rx_bytes
    bt.frame_received.emit("uuid-rx", b"\x68\x04")
    check(w._rx_bytes == base + 2, "蓝牙通道：蓝牙帧进入接收")


# ── [5] 通道持久化 ──────────────────────────────────────────────────
def test_channel_persisted():
    w = stw.SerialToolWidget()
    w.set_bluetooth_provider(lambda: FakeBluetooth(True))
    w.combo_channel.setCurrentIndex(_index_of(w, stw.CHANNEL_BLUETOOTH))
    params = w._collect_params()
    check(params.get("channel") == stw.CHANNEL_BLUETOOTH, "_collect_params 记录蓝牙通道")

    # 回到串口，再用刚存的参数恢复 → 应回到蓝牙
    w.combo_channel.setCurrentIndex(_index_of(w, stw.CHANNEL_SERIAL))
    check(w.channel() == stw.CHANNEL_SERIAL, "已切回串口")
    w._params = dict(params)
    w._apply_params()
    check(w.channel() == stw.CHANNEL_BLUETOOTH, "_apply_params 能恢复蓝牙通道")

    # 非法值回落串口
    w._params = dict(params, channel="bogus")
    w._apply_params()
    check(w.channel() == stw.CHANNEL_SERIAL, "非法通道值回落为串口")


# ── 执行 ────────────────────────────────────────────────────────────
def _run_all():
    global FAIL
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        print(f"\n[{fn.__name__}]")
        try:
            fn()
        except Exception as exc:      # noqa: BLE001
            FAIL += 1
            print(f"  [ERR ] {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    print("=" * 60)
    print("串口工具 · 通道（串口 / 蓝牙复用）回归")
    print("=" * 60)
    _run_all()
    print("\n" + "=" * 60)
    print(f"结果：{PASS} 通过，{FAIL} 失败")
    print("=" * 60)
    raise SystemExit(1 if FAIL else 0)
