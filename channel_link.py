# -*- coding: utf-8 -*-
"""协议测试页的**发送通道**（串口 / 蓝牙）控制器 —— Qt 但**不含任何协议细节**。

背景
----
「光伏升级」页 1.23.85 起已支持双通道：串口走共享 ``SerialWorker``，蓝牙走「蓝牙工具」页
**已经建立的连接**（本页不建也不断），整帧一次 ATT 写、页内自己分帧。698 / 645 两个
「协议测试」页需要同一套能力，且两页的收发形态完全一致（单条请求 → 等一帧应答）。

本模块把「选通道 / 取蓝牙 worker / 收发 / 状态文案 / 超限预检」收在一处，
页面只关心「把字节交给 controller.send()」「订阅 controller.rx」——
**不要**在页面里再写一份 MTU/上限/双通道过滤逻辑（那是漂移的根因）。

边界
----
- 蓝牙连接生命周期完全归「蓝牙工具」页：本模块只经 ``provider`` 取 worker、只断信号，**不断连接**。
- 协议帧必须**整帧一次 ATT 写**：超过 ``worker.single_write_limit()`` 时直接返回可读错误，
  **不调用 worker、不静默分包**（分包会让设备收到被切断的 698/645 帧）。
- RX 分流：两个来源的字节都进本模块，**只转发当前通道**的；切通道时页面应清空自己的分帧缓冲。
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from PySide6.QtCore import QObject, Signal

#: 顶部下拉的显示项（顺序即 UI 顺序）
CHANNELS: Tuple[Tuple[str, str], ...] = (("串口", "serial"), ("蓝牙", "bluetooth"))
SERIAL = "serial"
BLUETOOTH = "bluetooth"
DEFAULT_CHANNEL = SERIAL

#: 未连接/不可用时的统一提示（页面弹框直接复用）
TIP_SERIAL_DOWN = "串口未连接：请先在顶部「串口配置」打开端口（本页复用该串口）"
TIP_BT_DOWN = "蓝牙未连接：请先在「蓝牙工具」页扫描并连接设备（协议测试页复用该连接）"


def normalize_channel(value) -> str:
    """通道值归一化：非法 / 空 → :data:`DEFAULT_CHANNEL`。"""
    key = str(value or "").strip().lower()
    return key if key in (SERIAL, BLUETOOTH) else DEFAULT_CHANNEL


class BleSendPort:
    """把 ``BluetoothWorker`` 适配成与 ``SerialWorker`` 同构的**发送口**。

    - ``write_raw(frame)`` → ``worker.send_data(frame, single_write=True)``（整帧一次 ATT 写）；
    - ``is_open()`` → ``worker.is_connected()``。

    接收不走这里：页面订阅 ``ChannelController.rx``（来源是 ``notification_received``）。
    """

    def __init__(self, worker):
        self._worker = worker

    def is_open(self) -> bool:
        return bool(self._worker is not None and self._worker.is_connected())

    def write_raw(self, data: bytes) -> bool:
        if self._worker is None:
            return False
        return bool(self._worker.send_data(bytes(data), single_write=True))


class ChannelController(QObject):
    """串口 / 蓝牙双通道的收发控制器。

    信号
    ----
    - ``rx(bytes)``：**当前通道**收到的原始字节（另一通道的字节被丢弃）；
    - ``state_changed(str, bool)``：``(可读状态文案, 当前通道是否就绪)``；
    - ``channel_changed(str)``：通道已切换（页面据此清分帧缓冲）；
    - ``error(str)``：发送失败 / 超限 / 底层异常（页面记日志）。
    """

    rx = Signal(bytes)
    state_changed = Signal(str, bool)
    channel_changed = Signal(str)
    error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._channel = DEFAULT_CHANNEL
        self._serial = None
        self._bt_provider: Optional[Callable[[], object]] = None
        self._bt_worker = None

    # ── 通道 ──────────────────────────────────────────────────────────
    @property
    def channel(self) -> str:
        return self._channel

    def set_channel(self, value) -> None:
        key = normalize_channel(value)
        if key == self._channel:
            self._refresh_state()
            return
        self._channel = key
        if key == BLUETOOTH:
            self.rebind_bluetooth()
        self.channel_changed.emit(key)
        self._refresh_state()

    # ── 串口 ──────────────────────────────────────────────────────────
    def set_serial_worker(self, worker) -> None:
        """注入主窗口共享串口线程；只订阅信号，绝不开/关端口。"""
        if self._serial is worker:
            self._refresh_state()
            return
        if self._serial is not None:
            self._disconnect_serial(self._serial)
        self._serial = worker
        if worker is not None:
            self._connect_serial(worker)
        self._refresh_state()

    def _connect_serial(self, worker) -> None:
        for signal, slot in self._serial_slots(worker):
            try:
                signal.connect(slot)
            except (RuntimeError, TypeError):
                pass

    def _disconnect_serial(self, worker) -> None:
        for signal, slot in self._serial_slots(worker):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _serial_slots(self, worker) -> tuple:
        return ((worker.raw_data_received, self._on_serial_bytes),
                (worker.connection_changed, self._on_any_state),
                (worker.error_occurred, self._on_serial_error))

    def _on_serial_bytes(self, data: bytes) -> None:
        if self._channel != SERIAL:
            return
        payload = bytes(data or b"")
        if payload:
            self.rx.emit(payload)

    def _on_serial_error(self, message: str) -> None:
        if self._channel == SERIAL:
            self.error.emit(str(message))

    # ── 蓝牙 ──────────────────────────────────────────────────────────
    def set_bluetooth_provider(self, provider) -> None:
        """注入「取蓝牙通信线程」的取值回调（主窗口接到「蓝牙工具」页）。"""
        self._bt_provider = provider
        self.rebind_bluetooth()

    def worker_ref(self):
        """当前蓝牙 worker（provider 缺失/异常 → None）。"""
        fn = self._bt_provider
        if not callable(fn):
            return None
        try:
            return fn()
        except Exception:                       # noqa: BLE001 —— provider 异常不影响页面
            return None

    def rebind_bluetooth(self) -> None:
        """重新解析 provider 并换绑信号（蓝牙页可能后连/重建 worker）。"""
        worker = self.worker_ref()
        if worker is not self._bt_worker:
            if self._bt_worker is not None:
                self._disconnect_bt(self._bt_worker)
            self._bt_worker = worker
            if worker is not None:
                self._connect_bt(worker)
        self._refresh_state()

    def _connect_bt(self, worker) -> None:
        for signal, slot in self._bt_slots(worker):
            try:
                signal.connect(slot)
            except (RuntimeError, TypeError):
                pass

    def _disconnect_bt(self, worker) -> None:
        for signal, slot in self._bt_slots(worker):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _bt_slots(self, worker) -> tuple:
        return ((worker.notification_received, self._on_bt_notification),
                (worker.connection_changed, self._on_any_state),
                (worker.mtu_updated, self._on_any_state),
                (worker.error_occurred, self._on_bt_error))

    def _on_bt_notification(self, _uuid: str, data: bytes) -> None:
        if self._channel != BLUETOOTH:
            return
        payload = bytes(data or b"")
        if payload:
            self.rx.emit(payload)

    def _on_bt_error(self, message: str) -> None:
        if self._channel == BLUETOOTH:
            self.error.emit(str(message))

    def _on_any_state(self, *_args) -> None:
        self._refresh_state()

    # ── 状态 / 就绪 / 发送 ────────────────────────────────────────────
    def ready(self) -> Tuple[bool, str]:
        """当前通道是否可用 → ``(就绪, 不可用原因)``；就绪时原因为空串。"""
        if self._channel == BLUETOOTH:
            worker = self.worker_ref()
            if worker is not self._bt_worker:
                self.rebind_bluetooth()
                worker = self._bt_worker
            if worker is None or not bool(getattr(worker, "is_connected", lambda: False)()):
                text = ("蓝牙通道未注入（协议测试页没有拿到「蓝牙工具」页的通信线程）"
                        if worker is None and not callable(self._bt_provider)
                        else TIP_BT_DOWN)
                return False, text
            return True, ""
        worker = self._serial
        if worker is None or not bool(getattr(worker, "is_open", lambda: False)()):
            return False, TIP_SERIAL_DOWN
        return True, ""

    def state_text(self) -> str:
        """顶部状态行文案（与升级页同口径）。"""
        if self._channel == BLUETOOTH:
            worker = self._bt_worker if self._bt_worker is self.worker_ref() else self.worker_ref()
            if worker is None or not bool(getattr(worker, "is_connected", lambda: False)()):
                return "蓝牙通道：未连接（请先在「蓝牙工具」页扫描并连接设备）"
            name = ""
            try:
                name = str(worker.device_name() or worker.device_address() or "")
            except Exception:                   # noqa: BLE001
                name = ""
            name = name or "已连接设备"
            mtu = int(getattr(worker, "mtu_size", lambda: 0)() or 0)
            limit = int(getattr(worker, "single_write_limit", lambda: 0)() or 0)
            return (f"蓝牙通道：{name}（MTU {mtu}，一次 ATT 写上限 {limit} 字节；"
                    "协议帧必须整帧一次写）")
        worker = self._serial
        state = "已连接" if (worker is not None
                            and bool(getattr(worker, "is_open", lambda: False)())) else "未连接"
        return f"串口通道：{state}（端口/波特率在顶部「串口配置」设置）"

    def _refresh_state(self) -> None:
        ok, _reason = self.ready()
        self.state_changed.emit(self.state_text(), ok)

    def send(self, frame: bytes) -> Tuple[bool, str]:
        """发送一帧 → ``(成功, 可读原因)``。

        蓝牙通道先按 ``single_write_limit()`` 预检：超限**不调用 worker**（升级页那句
        「请调小每包字节数」对测试页是误导），直接给本页能照做的原因。
        """
        payload = bytes(frame or b"")
        if not payload:
            return False, "发送内容为空"
        if self._channel == BLUETOOTH:
            worker = self.worker_ref()
            if worker is not self._bt_worker:
                self.rebind_bluetooth()
                worker = self._bt_worker
            if worker is None or not bool(getattr(worker, "is_connected", lambda: False)()):
                return False, TIP_BT_DOWN
            try:
                limit = int(worker.single_write_limit())
            except Exception as exc:            # noqa: BLE001
                return False, f"蓝牙一次写上限读取失败：{type(exc).__name__}: {exc}"
            if limit > 0 and len(payload) > limit:
                return False, (f"蓝牙一次 ATT 写上限 {limit} 字节，该帧 {len(payload)} 字节"
                               "（协议帧必须整帧一次写，不能分包）")
            try:
                ok = bool(worker.send_data(payload, single_write=True))
            except Exception as exc:            # noqa: BLE001
                return False, f"蓝牙发送失败：{type(exc).__name__}: {exc}"
            return (True, "") if ok else (False, "蓝牙写入失败（详见「蓝牙工具」页日志）")
        worker = self._serial
        if worker is None or not bool(getattr(worker, "is_open", lambda: False)()):
            return False, TIP_SERIAL_DOWN
        try:
            ok = bool(worker.write_raw(payload))
        except Exception as exc:                # noqa: BLE001
            return False, f"串口写入异常：{type(exc).__name__}: {exc}"
        return (True, "") if ok else (False, "串口写入失败（端口可能已被占用/拔出）")

    def cleanup(self) -> None:
        """断掉全部订阅（幂等）；**不断开蓝牙连接**（生命周期归「蓝牙工具」页）。"""
        if self._serial is not None:
            self._disconnect_serial(self._serial)
            self._serial = None
        if self._bt_worker is not None:
            self._disconnect_bt(self._bt_worker)
            self._bt_worker = None


__all__ = [
    "BLUETOOTH",
    "BleSendPort",
    "CHANNELS",
    "ChannelController",
    "DEFAULT_CHANNEL",
    "SERIAL",
    "TIP_BT_DOWN",
    "TIP_SERIAL_DOWN",
    "normalize_channel",
]
