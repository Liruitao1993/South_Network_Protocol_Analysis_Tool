# -*- coding: utf-8 -*-
"""蓝牙通信线程（bluetooth_worker）回归测试 —— 用**假 bleak**，不碰硬件、不需要蓝牙适配器。

做法：在 import 之前把假模块塞进 ``sys.modules["bleak"]``。`bluetooth_worker` 只在
模块顶层 ``from bleak import BleakClient, BleakScanner``，所以注入假模块即可完整接管
扫描 / 连接 / 服务发现 / 订阅 / 写入 / 掉线回调，且**不需要真的蓝牙设备**。

覆盖：
  [1] 扫描：结果按 RSSI 由强到弱、同强度有名称的排前面、scan_finished 计数
  [2] 连接：connected / characteristics_updated / MTU、连接 3 次重试、失败报错
  [3] 订阅：连接后按已选接收特征码自动订阅；重复订阅前先 stop_notify
  [4] 通知 → 分包重组：静默超时合成一帧经 frame_received 投递
  [5] 写入：按 MTU/特征码上限分包、response=False 失败回落 response=True、
      未连接 / 无特征码时报错、写失败报错
  [6] 断开：flush 残包、disconnected / connection_changed(False)
  [7] shutdown 幂等；bleak 缺失时统一提示
  [8] 反例自检（判据有效）

运行: python test/test_bluetooth_worker.py
"""

import _path_setup  # noqa: E402,F401

import asyncio  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402

PASS = 0
FAIL = 0


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


# ── 假 bleak ────────────────────────────────────────────────────────────────

class FakeChar:
    def __init__(self, uuid, properties, description="", max_write=0):
        self.uuid = uuid
        self.properties = list(properties)
        self.description = description
        self.max_write_without_response_size = max_write


class FakeService:
    def __init__(self, uuid, chars):
        self.uuid = uuid
        self.characteristics = list(chars)


class FakeAdv:
    def __init__(self, local_name, rssi):
        self.local_name = local_name
        self.rssi = rssi


class FakeDevice:
    def __init__(self, address, name, rssi=0):
        self.address = address
        self.name = name
        self.rssi = rssi


# 被扫描到的设备（address → (name, rssi)）
SCAN_DEVICES = [
    ("AA:01", "LME_06012", -57),
    ("AA:02", "", -57),
    ("AA:03", "EDQ253_P_A10", -70),
]

# 假设备提供的特征码
RECV_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
SEND_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"
READ_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"
LOW_MTU_SEND_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"


class FakeClient:
    """假 BleakClient：记录调用、可注入失败与掉线。

    注意 ``attempts`` 是**类级**计数：worker 每次重试都会新建一个 client（真实 bleak
    也是如此），用实例级计数会让「第 3 次成功」永远等不到。
    """

    connect_fail_times = 0
    attempts = 0
    mtu = 247
    write_fail_no_response = False
    instances = []

    def __init__(self, address, disconnected_callback=None, timeout=10.0, **kwargs):
        self.address = address
        self.disconnected_callback = disconnected_callback
        self.timeout = timeout
        self.connected = False
        self.mtu_size = type(self).mtu
        self.notified = []          # (uuid, callback)
        self.stopped = []
        self.writes = []            # (uuid, data, response)
        self.disconnect_calls = 0
        self.connect_calls = 0
        self.subscribe_fail_uuids = set()
        self.services = [
            FakeService("00001800-0000-1000-8000-00805f9b34fb", [
                FakeChar(READ_UUID, ["read"], "设备名"),
            ]),
            FakeService("0000fff0-0000-1000-8000-00805f9b34fb", [
                FakeChar(RECV_UUID, ["notify"], "上报通道"),
                FakeChar(SEND_UUID, ["write", "write-without-response"], "下发通道"),
                FakeChar(LOW_MTU_SEND_UUID, ["write"], "窄通道", max_write=24),
            ]),
        ]
        FakeClient.instances.append(self)

    async def connect(self):
        self.connect_calls += 1
        type(self).attempts += 1
        if type(self).attempts <= type(self).connect_fail_times:
            raise OSError("连接被拒绝（假）")
        self.connected = True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.connected = False

    async def get_services(self):
        return self.services

    async def start_notify(self, uuid, callback, **kwargs):
        if uuid in self.subscribe_fail_uuids:
            raise RuntimeError("订阅失败（假）")
        self.notified.append((uuid, callback))

    async def stop_notify(self, uuid):
        self.stopped.append(uuid)

    async def write_gatt_char(self, uuid, data, response=None):
        if response is False and type(self).write_fail_no_response:
            raise RuntimeError("免响应写不支持（假）")
        self.writes.append((uuid, bytes(data), response))

    # 测试辅助：模拟设备上报一个分包
    def emit_notification(self, uuid, data):
        for known_uuid, callback in list(self.notified):
            if known_uuid == uuid:
                callback(FakeNotified(uuid), data)
                return True
        return False

    # 测试辅助：模拟掉线
    def emit_disconnect(self):
        if self.disconnected_callback is not None:
            self.disconnected_callback(self)


class FakeNotified:
    def __init__(self, uuid):
        self.uuid = uuid


class FakeScanner:
    """假 BleakScanner：discover 返回固定设备表，但**逐个上报并真实耗时**。

    ⚠ 必须真的花时间（原来只 `sleep(0)`）：真实 BLE 扫描持续数秒，而「扫描中重复
    `start_scan` 被拒」「`scan_finished` 只发一次」这两条判据**依赖扫描仍在进行**。
    立即返回会让扫描在主线程走到下一行断言之前就结束 ⇒ 第二次 start_scan 被受理
    ⇒ 扫两遍、设备重复、`scan_finished == [3, 3]`，用例**随机变红**（实测 8 次跑 2 次失败）。
    """

    discover_kwargs = {}
    #: 每个设备"上报"前的耗时（秒）。3 个设备共 0.24s，远小于用例传入的 1.0s 扫描窗口。
    DEVICE_DELAY = 0.08

    @classmethod
    async def discover(cls, timeout=5.0, return_adv=False, **kwargs):
        cls.discover_kwargs = {"timeout": timeout, "return_adv": return_adv}
        result = {}
        for address, name, rssi in SCAN_DEVICES:
            await asyncio.sleep(cls.DEVICE_DELAY)
            device = FakeDevice(address, name, rssi)
            if return_adv:
                result[address] = (device, FakeAdv(name, rssi))
            else:
                result[address] = device
        return result


_fake_bleak = types.ModuleType("bleak")
_fake_bleak.BleakClient = FakeClient
_fake_bleak.BleakScanner = FakeScanner
sys.modules["bleak"] = _fake_bleak

from PySide6.QtCore import QCoreApplication  # noqa: E402

import bluetooth_core as core  # noqa: E402
import bluetooth_worker as bw  # noqa: E402


# ── 工具 ────────────────────────────────────────────────────────────────────

def wait_for(predicate, timeout=8.0):
    """等条件成立（驱动 Qt 事件循环，让跨线程信号真正投递到主线程）。"""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


class Recorder:
    """收集 worker 的信号（跨线程需要事件循环才能收到）。"""

    def __init__(self, worker):
        self.devices = []
        self.frames = []
        self.logs = []
        self.errors = []
        self.sent = []
        self.connections = []
        self.characteristics = []
        self.mtu_updates = []
        self.scan_finished = []
        self.scan_errors = []
        self.connect_errors = []
        self.disconnected = 0
        self.progress = []
        self.subscribes = []
        worker.device_found.connect(lambda n, a, r: self.devices.append((n, a, r)))
        worker.frame_received.connect(lambda u, d: self.frames.append((u, bytes(d))))
        worker.log_message.connect(self.logs.append)
        worker.error_occurred.connect(self.errors.append)
        worker.data_sent.connect(lambda d: self.sent.append(bytes(d)))
        worker.connection_changed.connect(self.connections.append)
        worker.characteristics_updated.connect(lambda c: self.characteristics.append(list(c)))
        worker.mtu_updated.connect(lambda m, c: self.mtu_updates.append((m, list(c))))
        worker.scan_finished.connect(self.scan_finished.append)
        worker.scan_error.connect(self.scan_errors.append)
        worker.connect_error.connect(self.connect_errors.append)
        worker.disconnected.connect(lambda: setattr(self, "disconnected", self.disconnected + 1))
        worker.send_progress.connect(lambda i, t, c: self.progress.append((i, t, bytes(c))))
        worker.subscribe_finished.connect(
            lambda uuids, ok: self.subscribes.append((list(uuids), bool(ok))))


def reset_fakes():
    FakeClient.instances = []
    FakeClient.connect_fail_times = 0
    FakeClient.attempts = 0
    FakeClient.mtu = 247
    FakeClient.write_fail_no_response = False


# ── [1] 扫描 ────────────────────────────────────────────────────────────────

def test_scan(worker, rec):
    section("[1] 扫描")

    check("bleak_available 为 True", worker.bleak_available() is True)
    check("start_scan 受理", worker.start_scan(1.0) is True)
    check("扫描中重复 start_scan 被拒", worker.start_scan(1.0) is False)
    check("等扫描结束", wait_for(lambda: len(rec.scan_finished) == 1))
    check("scan_finished 计数正确", rec.scan_finished == [3], rec.scan_finished)
    check("return_adv=True 被使用（才能拿到 RSSI/本地名）",
          FakeScanner.discover_kwargs.get("return_adv") is True, FakeScanner.discover_kwargs)
    order = [(a, r) for _n, a, r in rec.devices]
    check("按 RSSI 由强到弱排序", order == [("AA:01", -57), ("AA:02", -57), ("AA:03", -70)],
          order)
    names = [n for n, _a, _r in rec.devices]
    check("同强度时有名称的排前面", names[:2] == ["LME_06012", ""], names)


# ── [2] 连接 ────────────────────────────────────────────────────────────────

def test_connect(worker, rec):
    section("[2] 连接")

    worker.set_characteristics([RECV_UUID], [SEND_UUID])
    check("connect_device 受理", worker.connect_device("AA:01", "LME_06012") is True)
    check("等连接完成", wait_for(lambda: bool(rec.characteristics) and True in rec.connections))
    check("is_connected 为 True", worker.is_connected() is True)
    check("device_name / address 记录正确",
          worker.device_name() == "LME_06012" and worker.device_address() == "AA:01",
          (worker.device_name(), worker.device_address()))
    check("MTU 读取正确（假设备 247）", worker.mtu_size() == 247, worker.mtu_size())
    check("connection_changed(True) 已发", True in rec.connections, rec.connections)

    chars = rec.characteristics[-1]
    check("特征码数正确（4 个）", len(chars) == 4, len(chars))
    by_uuid = {c["uuid"]: c for c in chars}
    check("notify 特征码标记 can_recv",
          by_uuid[RECV_UUID]["can_recv"] is True and by_uuid[RECV_UUID]["can_send"] is False)
    check("write 特征码标记 can_send",
          by_uuid[SEND_UUID]["can_send"] is True and by_uuid[SEND_UUID]["can_recv"] is False)
    check("只读特征码两个方向都 False",
          by_uuid[READ_UUID]["can_recv"] is False and by_uuid[READ_UUID]["can_send"] is False)
    check("描述与 max_write 透传",
          by_uuid[LOW_MTU_SEND_UUID]["max_write"] == 24
          and by_uuid[LOW_MTU_SEND_UUID]["description"] == "窄通道")
    check("short_uuid 已生成", by_uuid[RECV_UUID]["short"] == "0xFFF1",
          by_uuid[RECV_UUID]["short"])

    client = FakeClient.instances[-1]
    check("连接后按已选接收特征码自动订阅",
          [u for u, _cb in client.notified] == [RECV_UUID], client.notified)
    check("订阅前先 stop_notify（防重复订阅报错）", client.stopped == [RECV_UUID],
          client.stopped)

    check("已连接时再连被拒", worker.connect_device("AA:03", "x") is False)


def test_connect_retry():
    section("[2b] 连接重试与失败")

    reset_fakes()
    FakeClient.connect_fail_times = 2       # 前两次失败、第三次成功
    worker = bw.BluetoothWorker()
    rec = Recorder(worker)
    worker.connect_device("AA:01", "重试设备")
    check("重试后成功", wait_for(lambda: True in rec.connections), rec.connections)
    check("确实尝试了 3 次（每次都新建 client）",
          FakeClient.attempts == 3 and len(FakeClient.instances) == 3,
          (FakeClient.attempts, len(FakeClient.instances)))
    worker.shutdown()

    reset_fakes()
    FakeClient.connect_fail_times = 99      # 一直失败
    worker = bw.BluetoothWorker()
    rec = Recorder(worker)
    worker.connect_device("AA:01", "坏设备")
    check("全部失败后报 connect_error", wait_for(lambda: bool(rec.connect_errors)))
    check("失败时 is_connected 为 False", worker.is_connected() is False)
    check("失败时也发 connection_changed(False)", False in rec.connections, rec.connections)
    check("connect_error 里带异常类型",
          "OSError" in rec.connect_errors[-1], rec.connect_errors[-1])
    worker.shutdown()


# ── [3] 通知 → 重组 ─────────────────────────────────────────────────────────

def test_notify_and_reassemble(worker, rec):
    section("[3] 通知分包重组")

    client = FakeClient.instances[-1]
    worker.set_packet_timeout(0.15)
    client.emit_notification(RECV_UUID, b"\x68\x12")
    client.emit_notification(RECV_UUID, b"\x00\x41")
    client.emit_notification(RECV_UUID, b"\x16")
    check("未超时前不出帧", rec.frames == [], rec.frames)
    check("等待重组字节数可见", wait_for(lambda: worker.pending_bytes() == 5),
          worker.pending_bytes())
    check("静默超时后合成一帧",
          wait_for(lambda: len(rec.frames) == 1), rec.frames)
    check("重组内容完整正确",
          rec.frames[-1] == (RECV_UUID, b"\x68\x12\x00\x41\x16"), rec.frames)
    check("统计收到 5 字节", worker.stats()[0] == 5, worker.stats())

    # 两个不同特征码的通知各自成帧
    rec.frames.clear()
    worker.set_characteristics([RECV_UUID, LOW_MTU_SEND_UUID], [SEND_UUID])
    check("重新订阅生效", wait_for(lambda: len(client.notified) >= 3), client.notified)
    client.emit_notification(RECV_UUID, b"\x01")
    client.emit_notification(LOW_MTU_SEND_UUID, b"\x02")
    check("不同特征码独立成帧", wait_for(lambda: len(rec.frames) == 2), rec.frames)
    check("两帧归属各自的特征码",
          {u for u, _d in rec.frames} == {RECV_UUID, LOW_MTU_SEND_UUID}, rec.frames)

    # 订阅失败只记日志、不中断
    rec.logs.clear()
    client.subscribe_fail_uuids = {READ_UUID}
    worker.set_characteristics([READ_UUID, RECV_UUID], [SEND_UUID])
    check("部分订阅失败有日志告知",
          wait_for(lambda: any("订阅失败" in m for m in rec.logs)), rec.logs)
    client.subscribe_fail_uuids = set()
    worker.set_characteristics([RECV_UUID], [SEND_UUID])


# ── [4] 写入 ────────────────────────────────────────────────────────────────

def test_write(worker, rec):
    section("[4] 写入分包")

    client = FakeClient.instances[-1]
    client.writes.clear()
    payload = bytes(range(256)) + b"\x00" * 194     # 450 字节
    check("send_data 受理", worker.send_data(payload) is True)
    check("等发送完成", wait_for(lambda: bool(rec.sent)), rec.sent)

    sizes = [len(d) for _u, d, _r in client.writes]
    check("按 MTU 247 → 单包 200，共 3 包", sizes == [200, 200, 50], sizes)
    check("拼接后与原始数据一致",
          b"".join(d for _u, d, _r in client.writes) == payload)
    check("全部走免响应写（response=False）",
          all(r is False for _u, _d, r in client.writes),
          [r for _u, _d, r in client.writes])
    check("写入目标就是已选发送特征码",
          {u for u, _d, _r in client.writes} == {SEND_UUID},
          {u for u, _d, _r in client.writes})
    check("data_sent 回传原始完整内容", rec.sent[-1] == payload, len(rec.sent[-1]))
    check("多包时发 send_progress",
          [i for i, _t, _c in rec.progress] == [1, 2, 3], rec.progress)
    check("发送字节统计累加", worker.stats()[1] == 450, worker.stats())
    check("分包时日志说明「单包上限 / 包数 / MTU」（报障：25 字节为何分两包）",
          any("单包上限 200 字节分为 3 包" in m and "MTU=247" in m for m in rec.logs),
          [m for m in rec.logs if "单包上限" in m])

    # 特征码自带 max_write（24）时，单包按它算而不是按 MTU
    worker.set_characteristics([RECV_UUID], [LOW_MTU_SEND_UUID])
    check("重新订阅接收通道", wait_for(lambda: worker.send_uuids() == [LOW_MTU_SEND_UUID]))
    client.writes.clear()
    rec.sent.clear()
    worker.send_data(bytes(range(60)))
    check("等窄通道发送完成", wait_for(lambda: bool(rec.sent)))
    sizes = [len(d) for _u, d, _r in client.writes]
    check("按特征码 max_write=24 分包", sizes == [24, 24, 12], sizes)
    check("日志给出来源（特征码免响应写上限 24，非 MTU）",
          any("单包上限 24 字节" in m and "特征码免响应写上限 24" in m for m in rec.logs),
          [m for m in rec.logs if "单包上限" in m])

    # 免响应写失败 → 回落有响应写
    FakeClient.write_fail_no_response = True
    client.writes.clear()
    rec.sent.clear()
    worker.send_data(b"\xAA\xBB")
    check("回落有响应写仍能发出", wait_for(lambda: bool(rec.sent)), rec.errors)
    check("回落时 response=True",
          all(r is True for _u, _d, r in client.writes), client.writes)
    FakeClient.write_fail_no_response = False

    # 边界：空内容 / 未连接 / 无发送特征码
    rec.errors.clear()
    check("空内容被拒并报错",
          worker.send_data(b"") is False and any("空" in e for e in rec.errors), rec.errors)
    worker.set_characteristics([], [])
    rec.errors.clear()
    worker.send_data(b"\x01")
    check("无发送特征码时报错（不静默）",
          wait_for(lambda: any("特征码" in e for e in rec.errors)), rec.errors)


# ── [5] 断开 / 掉线 / 关闭 ──────────────────────────────────────────────────

def test_disconnect(worker, rec):
    section("[5] 断开 / 掉线 / 关闭")

    worker.set_characteristics([RECV_UUID], [SEND_UUID])
    client = FakeClient.instances[-1]
    client.emit_notification(RECV_UUID, b"\xAA\xBB")
    rec.frames.clear()
    check("断开", worker.disconnect_device() is True)
    check("等断开完成", wait_for(lambda: rec.disconnected >= 1))
    check("断开时把未成帧残包交出来（不静默丢）",
          rec.frames == [(RECV_UUID, b"\xAA\xBB")], rec.frames)
    check("断开后 is_connected 为 False", worker.is_connected() is False)
    check("断开后 connection_changed(False) 已发",
          wait_for(lambda: False in rec.connections), rec.connections)
    check("未连接时再断开返回 False", worker.disconnect_device() is False)


def test_drop_and_missing_bleak():
    section("[5b] 掉线回调 / bleak 缺失")

    reset_fakes()
    worker = bw.BluetoothWorker()
    rec = Recorder(worker)
    worker.set_characteristics([RECV_UUID], [SEND_UUID])
    worker.connect_device("AA:01", "掉线设备")
    check("先连上", wait_for(lambda: worker.is_connected()))
    check("已订阅接收通道", wait_for(lambda: bool(FakeClient.instances[-1].notified)))
    client = FakeClient.instances[-1]
    client.emit_notification(RECV_UUID, b"\x01\x02\x03")
    rec.frames.clear()
    client.emit_disconnect()
    check("掉线触发 disconnected", wait_for(lambda: rec.disconnected >= 1))
    check("掉线交出残包", rec.frames == [(RECV_UUID, b"\x01\x02\x03")], rec.frames)
    check("掉线后状态清空", worker.is_connected() is False)
    worker.shutdown()
    check("shutdown 幂等（再调不抛）", worker.shutdown() is None)

    # bleak 缺失：bleak_available False + 统一提示，且不抛异常
    saved_client = bw.BleakClient
    saved_scanner = bw.BleakScanner
    try:
        bw.BleakClient = None
        bw.BleakScanner = None
        worker = bw.BluetoothWorker()
        rec = Recorder(worker)
        check("bleak 缺失时 bleak_available False", worker.bleak_available() is False)
        check("bleak 缺失时 start_scan 返回 False", worker.start_scan() is False)
        check("bleak 缺失时 connect_device 返回 False",
              worker.connect_device("AA:01") is False)
        check("bleak 缺失给出统一安装提示",
              any(bw.BLEAK_MISSING_HINT in e for e in rec.errors), rec.errors)
        worker.shutdown()
    finally:
        bw.BleakClient = saved_client
        bw.BleakScanner = saved_scanner


# ── [6] 反例自检 ────────────────────────────────────────────────────────────

def test_subscribe_finished():
    section("[7] 订阅完成信号（一键探测的时序依赖）")

    reset_fakes()
    worker = bw.BluetoothWorker()
    rec = Recorder(worker)
    try:
        worker.set_characteristics([RECV_UUID], [SEND_UUID])
        check("未连接时 set_characteristics 不发信号（没有订阅动作）",
              rec.subscribes == [], str(rec.subscribes))
        check("连接受理", worker.connect_device("AA:07", "LME_06012") is True)
        check("连接后自动订阅并发出完成信号（成功）",
              wait_for(lambda: rec.subscribes == [([RECV_UUID], True)]), str(rec.subscribes))

        client = FakeClient.instances[-1]
        rec.subscribes.clear()
        client.subscribe_fail_uuids = {RECV_UUID}
        worker.set_characteristics([RECV_UUID], [SEND_UUID])
        check("订阅失败 → (空成功列表, False)",
              wait_for(lambda: rec.subscribes == [([], False)]), str(rec.subscribes))

        rec.subscribes.clear()
        worker.set_characteristics([], [SEND_UUID])
        check("无接收通道 → 立刻发 ([], True)（否则探测会一直挂着）",
              wait_for(lambda: rec.subscribes == [([], True)]), str(rec.subscribes))
    finally:
        worker.shutdown()


def live_char(client, uuid):
    """取假 client 上的**活特征码对象**（worker 发送前就是重读它）。"""
    for service in getattr(client, "services", None) or []:
        for char in getattr(service, "characteristics", None) or []:
            if str(getattr(char, "uuid", "")) == uuid:
                return char
    return None


def test_mtu_poll():
    section("[7] MTU 协商轮询（1.23.80）")

    interval, timeout = bw.MTU_POLL_INTERVAL, bw.MTU_POLL_TIMEOUT
    bw.MTU_POLL_INTERVAL, bw.MTU_POLL_TIMEOUT = 0.02, 0.4
    try:
        # ── 迟到协商：连接时还是 ATT 默认值，轮询期间结果到达 ──
        reset_fakes()
        FakeClient.mtu = core.MTU_DEFAULT
        worker = bw.BluetoothWorker()
        rec = Recorder(worker)
        worker.set_characteristics([RECV_UUID], [SEND_UUID])
        worker.connect_device("AA:01", "迟到设备")
        check("连接受理", wait_for(lambda: worker.is_connected() is True))
        check("连接时读到的是 ATT 默认值（协商结果未回）",
              worker.mtu_size() == core.MTU_DEFAULT, worker.mtu_size())
        check("连接信号先于等待发出（界面不被拖住）",
              wait_for(lambda: True in rec.connections and bool(rec.characteristics)),
              (rec.connections, len(rec.characteristics)))

        client = FakeClient.instances[-1]
        # 只改 MTU：**单次属性写**，读侧没有中间态窗口。特征码上限的实时重读由下面
        # 「发送前重读」两段覆盖（那里测试线程写完才发起发送，天然无竞态）。
        client.mtu_size = 247
        check("轮询把 MTU 自动更新为协商值（无需重连）",
              wait_for(lambda: worker.mtu_size() == 247), worker.mtu_size())
        check("更新写进日志（口径：旧 → 新 + 特征码上限）",
              wait_for(lambda: any("MTU 协商更新：23 → 247" in m
                                   and "特征码免响应写上限 24 字节" in m for m in rec.logs)),
              [m for m in rec.logs if "协商更新" in m])
        check("发出 mtu_updated（携带完整特征码列表，4 条）",
              wait_for(lambda: any(m == 247 and len(c) == 4 for m, c in rec.mtu_updates)),
              rec.mtu_updates[-1:])
        worker.shutdown()

        # ── 对端只支持 ATT 默认值：超时只提示一行，不报错、不发信号 ──
        reset_fakes()
        FakeClient.mtu = core.MTU_DEFAULT
        worker = bw.BluetoothWorker()
        rec = Recorder(worker)
        worker.connect_device("AA:01", "只支持默认值")
        check("连接受理（默认值设备）", wait_for(lambda: worker.is_connected() is True))
        check("超时后只提示一行（不是错误）",
              wait_for(lambda: any("未收到 MTU 协商结果" in m for m in rec.logs)),
              [m for m in rec.logs if "MTU" in m])
        check("没有把它当错误上报", rec.errors == [], rec.errors)
        check("读数不变、且**不**发 mtu_updated（无变化不该刷界面）",
              worker.mtu_size() == core.MTU_DEFAULT and rec.mtu_updates == [],
              (worker.mtu_size(), rec.mtu_updates))
        worker.shutdown()

        # ── 发送前重读：协商结果在连接**之后**才到，本次发送就按新值分包 ──
        reset_fakes()
        FakeClient.mtu = core.MTU_DEFAULT
        worker = bw.BluetoothWorker()
        rec = Recorder(worker)
        worker.set_characteristics([RECV_UUID], [SEND_UUID])
        worker.connect_device("AA:01", "发送前才协商好")
        check("连接受理（发送前重读）", wait_for(lambda: worker.is_connected() is True))
        check("等轮询收尾", wait_for(lambda: any("未收到 MTU 协商结果" in m for m in rec.logs)))
        client = FakeClient.instances[-1]
        client.writes.clear()
        rec.sent.clear()
        rec.mtu_updates.clear()
        client.mtu_size = 247
        check("send_data 受理", worker.send_data(bytes(range(256)) + b"\x00" * 44) is True)
        check("等发送完成", wait_for(lambda: bool(rec.sent)), rec.errors)
        sizes = [len(d) for _u, d, _r in client.writes]
        check("按发送那一刻的实时 MTU 分包（300 字节：20 会切 15 包，247 只切 2 包）",
              sizes == [200, 100], sizes)
        check("日志来源写的是实时协商值（协商 MTU 247 − 3）",
              wait_for(lambda: any("单包上限 200 字节" in m and "协商 MTU 247" in m
                                   for m in rec.logs)),
              [m for m in rec.logs if "单包上限" in m])
        check("发送前刷新也发 mtu_updated（界面同步跟上）",
              bool(rec.mtu_updates) and rec.mtu_updates[-1][0] == 247, rec.mtu_updates[-1:])

        # 同一连接内特征码实时上限也会变（Windows 上两者同源，但读取路径不同）
        worker.set_characteristics([RECV_UUID], [LOW_MTU_SEND_UUID])
        check("切到窄通道（连接时上限 24）",
              wait_for(lambda: worker.send_uuids() == [LOW_MTU_SEND_UUID]))
        client.writes.clear()
        rec.sent.clear()
        live_char(client, LOW_MTU_SEND_UUID).max_write_without_response_size = 150
        worker.send_data(bytes(range(256)) + b"\x00" * 44)
        check("等窄通道发送完成", wait_for(lambda: bool(rec.sent)), rec.errors)
        sizes = [len(d) for _u, d, _r in client.writes]
        check("按特征码**实时**上限分包（24 → 150：300 字节切 150+150）",
              sizes == [150, 150], sizes)
        check("日志来源写的是特征码实时上限 150",
              wait_for(lambda: any("单包上限 150 字节" in m and "特征码免响应写上限 150" in m
                                   for m in rec.logs)),
              [m for m in rec.logs if "单包上限" in m])
        check("刷新信号里带的就是最新上限（150，不是连接时的 24）",
              bool(rec.mtu_updates)
              and {c["uuid"]: c["max_write"] for c in rec.mtu_updates[-1][1]}
              .get(LOW_MTU_SEND_UUID) == 150,
              rec.mtu_updates[-1:])
        worker.shutdown()

        # ── 断开打断轮询：静默收尾，不抛异常、不再提示 ──
        reset_fakes()
        FakeClient.mtu = core.MTU_DEFAULT
        # 这段的轮询超时取 1.5s：**远大于**「断开被处理」的耗时（否则断言会退化成
        # 「断开与超时谁先到」的竞态），又**小于**下面的观察窗口 —— 若「断开打断轮询」失效，
        # 轮询会在 1.5s 打出超时提示，断言即可抓住
        bw.MTU_POLL_TIMEOUT = 1.5
        worker = bw.BluetoothWorker()
        rec = Recorder(worker)
        worker.connect_device("AA:01", "连上就断")
        check("连接受理（连上就断）", wait_for(lambda: worker.is_connected() is True))
        worker.disconnect_device()
        check("断开完成", wait_for(lambda: worker.is_connected() is False))
        time.sleep(1.8)                     # 超过轮询超时
        QCoreApplication.processEvents()
        check("断开后轮询静默收尾（没有超时提示、没有错误）",
              not any("未收到 MTU 协商结果" in m for m in rec.logs) and rec.errors == [],
              (rec.logs[-3:], rec.errors))
        worker.shutdown()
    finally:
        bw.MTU_POLL_INTERVAL, bw.MTU_POLL_TIMEOUT = interval, timeout


def test_negatives():
    section("[6] 反例自检（判据有效）")

    reset_fakes()
    worker = bw.BluetoothWorker()
    check("未连接时 is_connected False", worker.is_connected() is False)
    rec = Recorder(worker)
    worker.send_data(b"\x01")
    check("未连接发送被拒并报错",
          wait_for(lambda: any("未连接" in e for e in rec.errors)), rec.errors)
    check("假客户端确实没收到写入（空实例表）", FakeClient.instances == [])
    check("未扫描时 is_scanning False", worker.is_scanning() is False)
    worker.shutdown()


def main():
    print("=" * 64)
    print("蓝牙通信线程 bluetooth_worker 回归（假 bleak）")
    print("=" * 64)

    app = QCoreApplication.instance() or QCoreApplication([])
    del app

    reset_fakes()
    worker = bw.BluetoothWorker()
    rec = Recorder(worker)
    try:
        test_scan(worker, rec)
        test_connect(worker, rec)
        test_notify_and_reassemble(worker, rec)
        test_write(worker, rec)
        test_disconnect(worker, rec)
    finally:
        worker.shutdown()

    test_connect_retry()
    test_drop_and_missing_bleak()
    test_subscribe_finished()
    test_mtu_poll()
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
