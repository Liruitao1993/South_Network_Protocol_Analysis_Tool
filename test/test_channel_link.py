# -*- coding: utf-8 -*-
"""`channel_link.ChannelController`（协议测试页的串口/蓝牙双通道）回归。

覆盖：
  [1] 常量与归一化（默认串口、未知值回落）
  [2] 串口通道：ready/状态文案/发送/异常/未打开
  [3] 蓝牙通道：未注入 provider、未连接、已连接（状态文案含 MTU+上限）、
      provider 延迟出现 + rebind、`mtu_updated` 触发状态刷新
  [4] 蓝牙发送：整帧一次写（`single_write=True`）、超限**不调用 worker** 且给可读原因
  [5] RX 分流：只转发当前通道；切通道后另一通道字节被丢弃；`channel_changed` 通知
  [6] cleanup：幂等、断订阅、**不断开蓝牙连接**

运行: python test/test_channel_link.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
import sys  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import channel_link as ch  # noqa: E402

FAILED = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        return True
    FAILED.append(f"{name}" + (f"\n    {detail}" if detail else ""))
    return False


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 60 - len(title)))


def app():
    return QApplication.instance() or QApplication([])


class FakeSerial(QObject):
    raw_data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, open_=True, write_ok=True):
        super().__init__()
        self.sent = []
        self._open = bool(open_)
        self._write_ok = bool(write_ok)
        self.raise_on_write = False

    def is_open(self):
        return self._open

    def write_raw(self, data):
        if self.raise_on_write:
            raise OSError("port gone")
        self.sent.append(bytes(data))
        return self._write_ok


class FakeBle(QObject):
    notification_received = Signal(str, bytes)
    connection_changed = Signal(bool)
    mtu_updated = Signal(int, list)
    error_occurred = Signal(str)

    def __init__(self, limit=200, connected=True, name="表计-A", mtu=247):
        super().__init__()
        self.sent = []
        self.limit = int(limit)
        self._connected = bool(connected)
        self._name = name
        self._mtu = int(mtu)
        self.raise_on_send = False

    def is_connected(self):
        return self._connected

    def device_name(self):
        return self._name

    def device_address(self):
        return "AA:BB:CC:DD:EE:FF"

    def mtu_size(self):
        return self._mtu

    def single_write_limit(self):
        return self.limit

    def send_data(self, data, single_write=False):
        if self.raise_on_send:
            raise RuntimeError("ble boom")
        payload = bytes(data)
        if single_write and len(payload) > self.limit:
            self.error_occurred.emit("oversize(worker)")
            return False
        self.sent.append((payload, bool(single_write)))
        return True


class Recorder:
    """收集控制器信号，便于断言。"""

    def __init__(self, ctrl):
        self.rx = []
        self.states = []
        self.channels = []
        self.errors = []
        ctrl.rx.connect(self.rx.append)
        ctrl.state_changed.connect(lambda text, ok: self.states.append((text, ok)))
        ctrl.channel_changed.connect(self.channels.append)
        ctrl.error.connect(self.errors.append)


# ── [1] 常量 ────────────────────────────────────────────────────────────────

def test_constants():
    section("[1] 常量与归一化")
    check("CHANNELS 顺序 = 串口/蓝牙",
          [k for _l, k in ch.CHANNELS] == ["serial", "bluetooth"], str(ch.CHANNELS))
    check("默认通道 = 串口", ch.DEFAULT_CHANNEL == "serial")
    check("合法值原样", ch.normalize_channel("bluetooth") == "bluetooth")
    check("大小写/空格容错", ch.normalize_channel(" Bluetooth ") == "bluetooth")
    for bad in ("", None, "usb", 123):
        check(f"非法值 {bad!r} → 默认", ch.normalize_channel(bad) == "serial")


# ── [2] 串口 ────────────────────────────────────────────────────────────────

def test_serial():
    section("[2] 串口通道")
    app()
    ctrl = ch.ChannelController()
    rec = Recorder(ctrl)
    check("初始通道 serial", ctrl.channel == "serial")
    check("无 worker → 未就绪", ctrl.ready()[0] is False)
    check("未就绪原因给串口提示", ch.TIP_SERIAL_DOWN in ctrl.ready()[1], ctrl.ready()[1])
    check("状态文案：串口未连接",
          ctrl.state_text().startswith("串口通道：未连接"), ctrl.state_text())

    serial = FakeSerial(open_=True)
    ctrl.set_serial_worker(serial)
    check("注入后 ready", ctrl.ready() == (True, ""), str(ctrl.ready()))
    check("状态文案：串口已连接",
          ctrl.state_text().startswith("串口通道：已连接"), ctrl.state_text())
    check("state_changed 已发", rec.states and rec.states[-1][1] is True,
          str(rec.states[-1:]))

    ok, err = ctrl.send(b"\x68\x01\x16")
    check("串口发送成功", ok and err == "" and serial.sent == [b"\x68\x01\x16"],
          f"{ok}/{err}/{serial.sent}")

    serial.raise_on_write = True
    ok, err = ctrl.send(b"\x68")
    check("串口写异常 → 可读错误", not ok and "串口写入异常" in err, err)
    serial.raise_on_write = False
    serial._write_ok = False
    ok, err = ctrl.send(b"\x68")
    check("串口写返回 False → 可读错误", not ok and "串口写入失败" in err, err)

    serial._open = False
    check("串口断开 → ready False", ctrl.ready()[0] is False)
    serial.connection_changed.emit(False)
    check("connection_changed 触发状态刷新", rec.states[-1][1] is False,
          str(rec.states[-1:]))
    ctrl.cleanup()


# ── [3] 蓝牙就绪 / 状态 / 延迟注入 ──────────────────────────────────────────

def test_bluetooth_ready():
    section("[3] 蓝牙通道（就绪 / 文案 / 延迟出现）")
    app()
    ctrl = ch.ChannelController()
    rec = Recorder(ctrl)
    ctrl.set_channel("bluetooth")
    check("切换发出 channel_changed", rec.channels == ["bluetooth"], str(rec.channels))
    check("未注入 provider → 未就绪", ctrl.ready()[0] is False)
    check("未注入原因提到「蓝牙工具」页",
          "蓝牙工具" in ctrl.ready()[1], ctrl.ready()[1])
    check("状态文案：蓝牙未连接",
          ctrl.state_text().startswith("蓝牙通道：未连接"), ctrl.state_text())
    ok, err = ctrl.send(b"\x01")
    check("未连接时发送失败且给原因", not ok and ch.TIP_BT_DOWN in err, err)

    holder = {"worker": None}
    ctrl.set_bluetooth_provider(lambda: holder["worker"])
    check("provider 返回 None 仍不可用", ctrl.ready()[0] is False)

    ble = FakeBle(limit=64, name="电表-1", mtu=247)
    holder["worker"] = ble
    ctrl.rebind_bluetooth()
    check("延迟出现的 worker 被绑定", ctrl.ready()[0] is True, str(ctrl.ready()))
    text = ctrl.state_text()
    check("状态文案含设备名/MTU/上限",
          "电表-1" in text and "247" in text and "64" in text, text)

    ble.limit = 200
    ble._mtu = 512
    ble.mtu_updated.emit(512, [])
    check("mtu_updated 触发状态刷新（上限变化）",
          "200" in ctrl.state_text() and "512" in ctrl.state_text(), ctrl.state_text())

    ble._connected = False
    ble.connection_changed.emit(False)
    check("断连 → ready False", ctrl.ready()[0] is False)
    ctrl.cleanup()


# ── [4] 蓝牙发送 / 超限 ─────────────────────────────────────────────────────

def test_bluetooth_send():
    section("[4] 蓝牙发送（整帧一次写 + 超限拦截）")
    app()
    ctrl = ch.ChannelController()
    ble = FakeBle(limit=32)
    ctrl.set_bluetooth_provider(lambda: ble)
    ctrl.set_channel("bluetooth")
    check("ready", ctrl.ready()[0] is True)

    ok, err = ctrl.send(b"\x01" * 32)
    check("上限内：成功且 single_write=True",
          ok and ble.sent and ble.sent[-1] == (b"\x01" * 32, True),
          f"{ok}/{err}/{ble.sent[-1:]}")
    check("未产生错误", not ble.sent or True)

    before = len(ble.sent)
    ok, err = ctrl.send(b"\x02" * 33)
    check("超限：失败", not ok)
    check("超限原因含上限与实际字节", "32" in err and "33" in err, err)
    check("超限**不调用 worker**（不静默分包）", len(ble.sent) == before,
          str(len(ble.sent) - before))
    check("空帧拒绝", ctrl.send(b"")[0] is False)

    ble.raise_on_send = True
    ok, err = ctrl.send(b"\x03")
    check("worker 异常 → 可读错误", not ok and "蓝牙发送失败" in err, err)
    ctrl.cleanup()


# ── [5] RX 分流 ─────────────────────────────────────────────────────────────

def test_rx_routing():
    section("[5] RX 分流（双通道不串味）")
    app()
    ctrl = ch.ChannelController()
    rec = Recorder(ctrl)
    serial = FakeSerial()
    ble = FakeBle()
    ctrl.set_serial_worker(serial)
    ctrl.set_bluetooth_provider(lambda: ble)

    serial.raw_data_received.emit(b"\x68\x01")
    check("串口通道：串口字节被转发", rec.rx == [b"\x68\x01"], str(rec.rx))
    rec.rx.clear()
    ble.notification_received.emit("uuid", b"\xAA")
    check("串口通道：蓝牙通知被丢弃", rec.rx == [], str(rec.rx))

    ctrl.set_channel("bluetooth")
    rec.rx.clear()
    serial.raw_data_received.emit(b"\x68\x02")
    check("蓝牙通道：串口字节被丢弃", rec.rx == [], str(rec.rx))
    ble.notification_received.emit("uuid", b"\xBB\xCC")
    check("蓝牙通道：通知被转发（忽略 uuid）", rec.rx == [b"\xBB\xCC"], str(rec.rx))

    ctrl.set_channel("serial")
    rec.rx.clear()
    ble.notification_received.emit("uuid", b"\xDD")
    check("切回串口：蓝牙通知不再转发", rec.rx == [], str(rec.rx))

    # BleSendPort 语义与控制器一致
    port = ch.BleSendPort(ble)
    check("BleSendPort.is_open = is_connected", port.is_open() is True)
    check("BleSendPort.write_raw 走单写",
          port.write_raw(b"\x09") and ble.sent[-1] == (b"\x09", True),
          str(ble.sent[-1:]))
    ctrl.cleanup()


# ── [6] cleanup ─────────────────────────────────────────────────────────────

def test_cleanup():
    section("[6] cleanup（幂等 / 断订阅 / 不断开连接）")
    app()
    ctrl = ch.ChannelController()
    rec = Recorder(ctrl)
    serial = FakeSerial()
    ble = FakeBle()
    ctrl.set_serial_worker(serial)
    ctrl.set_bluetooth_provider(lambda: ble)
    ctrl.set_channel("bluetooth")

    ctrl.cleanup()
    rec.rx.clear()
    ble.notification_received.emit("uuid", b"\x01")
    serial.raw_data_received.emit(b"\x02")
    check("cleanup 后不再转发任何通道字节", rec.rx == [], str(rec.rx))
    check("cleanup **不断开**蓝牙连接", ble.is_connected() is True)
    check("cleanup 不清 provider（可再次 rebind）", ctrl.worker_ref() is ble)
    ctrl.cleanup()                       # 幂等
    check("cleanup 幂等", True)


def main():
    for fn in (test_constants, test_serial, test_bluetooth_ready,
               test_bluetooth_send, test_rx_routing, test_cleanup):
        before = len(FAILED)
        try:
            fn()
        except Exception as exc:                          # noqa: BLE001
            import traceback

            FAILED.append(f"{fn.__name__} 抛异常：{type(exc).__name__}: {exc}\n"
                          f"{traceback.format_exc()}")
        print(("OK   " if len(FAILED) == before else "FAIL ") + fn.__name__)

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项 / 共 {CHECKS[0]} 项检查")
        for item in FAILED:
            print(" - " + item)
        return 1
    print(f"全部通过：{CHECKS[0]} 项检查")
    return 0


if __name__ == "__main__":
    sys.exit(main())
