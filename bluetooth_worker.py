"""BLE 通信线程（Qt 侧）：扫描 / 连接 / 特征码发现 / 订阅通知 / 写入 / 分包重组。

**来源**：集成自工程内的 `蓝牙转串口工具02`。原实现把这几件事散在
`main_pyside6.py` 的四个 QThread 里（扫描线程 / 连接线程 / 处理线程 + 主线程回调），
这里收敛为**一个** `BluetoothWorker`，接口与 `serial_worker.SerialWorker` 同构，
于是蓝牙页可以按「串口工具页」的方式接线：

    worker = BluetoothWorker()
    worker.device_found.connect(...) / frame_received.connect(...)
    worker.start_scan() / connect_device(addr, name) / send_data(payload)

线程模型：
  - 本对象在 GUI 线程创建，内部起**一个独立线程跑私有 asyncio 事件循环**，
    所有蓝牙操作经 ``asyncio.run_coroutine_threadsafe`` 投递；
  - bleak 的通知回调在事件循环线程执行 → 投给 `BleReassembler` 累积，
    由循环内的巡检任务按「静默超时」切帧后 ``emit frame_received``；
  - Qt 信号跨线程自动排队到 GUI 线程（自定义线程内 emit 同样是 queued），
    界面侧无需自己加锁；**界面显示的文本一律由界面格式化**，本模块只发结构化信号。

与原始实现的差异（有意为之，均在 README/AGENTS 里记录）：
  - 写入分包按协商 MTU 计算（原实现硬编码 200 字节），低 MTU 设备不再写失败；
  - 分包重组只有「静默超时切帧」一种语义（原实现的「立即单包直发」与
    「分包重组」自相矛盾，且 README 只承诺前者）；
  - 断开前会把未成帧的残包交出去（``frame_received``），不静默丢数据。
"""

from __future__ import annotations

import asyncio
import threading
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from bluetooth_core import (
    DEFAULT_CONNECT_RETRIES,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_MAX_CHUNK,
    DEFAULT_PACKET_TIMEOUT,
    DEFAULT_SCAN_TIMEOUT,
    DEFAULT_SEND_PACKET_DELAY,
    MIN_CHUNK,
    MTU_POLL_INTERVAL,
    MTU_POLL_TIMEOUT,
    BleReassembler,
    chunk_size_for_mtu,
    mtu_is_unnegotiated,
    short_uuid,
    split_chunks,
)

try:  # 允许「未安装 bleak」时整程序仍能启动：用到蓝牙功能时才报错
    from bleak import BleakClient, BleakScanner
except Exception:  # pragma: no cover - 依赖缺失路径
    BleakClient = None  # type: ignore[assignment]
    BleakScanner = None  # type: ignore[assignment]

# bleak 未安装时的统一提示
BLEAK_MISSING_HINT = "未安装 bleak 库：请执行 pip install bleak（Windows 建议同时装 winrt）"

#: `chunk_size_for_mtu` 的「不设人为上限」哨兵：只按 `MTU − 3`（ATT 头）取物理上限。
#: 升级页要求「一整帧 698 报文一次 ATT 写」，不能叠蓝牙页那个 200 字节的保护性上限。
_NO_CHUNK_CAP = 1 << 20


class BluetoothWorker(QObject):
    """BLE 通信工作对象（信号/方法口径对齐 `serial_worker.SerialWorker`）。"""

    # 扫描
    scan_started = Signal()
    device_found = Signal(str, str, int)      # 名称, 地址, RSSI
    scan_finished = Signal(int)               # 发现设备数
    scan_error = Signal(str)

    # 连接
    connecting = Signal(str, str)             # 地址, 名称
    connected = Signal(str, str)              # 名称, 地址
    connect_error = Signal(str)
    disconnected = Signal()
    connection_changed = Signal(bool)

    # 特征码与数据
    characteristics_updated = Signal(list)        # [{uuid, properties, description, can_recv, ...}]
    # MTU / 特征码写上限**实时变化**（1.23.80）：(协商到的 MTU, 最新特征码 dict 列表)。
    # 与 `characteristics_updated` **不可互相替代**：后者的语义是「特征码枚举完成」，
    # 界面收到后会走「沿用/优选 → set_characteristics（重新订阅）」，用它刷上限会产生
    # 多余重订阅与日志；本信号只用于更新读数，界面**不得**回写特征码选择。
    # MTU 由操作系统异步协商（Windows 上应用层只能读不能请求），连接时读到的可能还是
    # ATT 默认值 23 ⇒ worker 会轮询等一会儿，并在**每次发送前**重读（见 `_refresh_live_limits`）。
    mtu_updated = Signal(int, list)
    # 订阅完成（1.23.79）：(已成功订阅的 uuid 列表, 是否无失败)。**一键探测**必须先等到它再写，
    # 否则首个回包会在订阅生效前丢掉；`set_characteristics` 传空接收通道时也发一次（列表为空）。
    subscribe_finished = Signal(list, bool)
    notification_received = Signal(str, bytes)    # 特征码 UUID, 单个通知分包（原始）
    frame_received = Signal(str, bytes)           # 特征码 UUID, 重组后的完整报文
    send_progress = Signal(int, int, bytes)       # 第几包 / 共几包 / 本包内容
    data_sent = Signal(bytes)                     # 一次发送完成（原始完整内容）

    # 通用
    log_message = Signal(str)
    error_occurred = Signal(str)
    stats_changed = Signal(int, int)              # 累计接收 / 发送字节

    MONITOR_TICK = 0.05          # 秒：重组巡检周期
    LOOP_READY_TIMEOUT = 5.0     # 秒：事件循环线程启动等待

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_ready = threading.Event()

        self._client = None
        self._connected = False
        self._device_name = ""
        self._device_address = ""
        self._characteristics: List[dict] = []
        # 特征码**活对象**（uuid → bleak 特征码对象）：只用于在发送前重读实时上限
        # （bleak 的 `max_write_without_response_size` 是实时 property）。
        # **不进**投给界面的 dict（界面 dict 保持纯数据）。
        self._char_objects: dict = {}
        self._recv_uuids: List[str] = []
        self._send_uuids: List[str] = []

        self._reassembler = BleReassembler(DEFAULT_PACKET_TIMEOUT)
        self._monitor_task = None
        self._scanning = False
        self._closing = False

        self._mtu = 0
        self._packet_delay = DEFAULT_SEND_PACKET_DELAY
        self._max_chunk = DEFAULT_MAX_CHUNK
        self._rx_bytes = 0
        self._tx_bytes = 0

    # ── 状态查询 ──────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return bool(self._connected)

    def is_scanning(self) -> bool:
        return bool(self._scanning)

    def device_name(self) -> str:
        return self._device_name

    def device_address(self) -> str:
        return self._device_address

    def mtu_size(self) -> int:
        return int(self._mtu)

    def characteristics(self) -> List[dict]:
        return list(self._characteristics)

    def recv_uuids(self) -> List[str]:
        return list(self._recv_uuids)

    def send_uuids(self) -> List[str]:
        return list(self._send_uuids)

    def stats(self):
        return self._rx_bytes, self._tx_bytes

    def reset_stats(self) -> None:
        self._rx_bytes = 0
        self._tx_bytes = 0
        self.stats_changed.emit(self._rx_bytes, self._tx_bytes)

    def packet_timeout(self) -> float:
        return self._reassembler.timeout

    def pending_bytes(self) -> int:
        """尚未成帧的缓冲字节数（界面「等待重组」显示用）。"""
        return self._reassembler.pending_bytes()

    def bleak_available(self) -> bool:
        return BleakScanner is not None and BleakClient is not None

    # ── 参数 ──────────────────────────────────────────────────────────────

    def set_packet_timeout(self, seconds: float) -> None:
        """设置 BLE 通知静默切帧超时（秒）。"""
        self._reassembler.set_timeout(float(seconds))

    def set_send_options(self, packet_delay: Optional[float] = None,
                         max_chunk: Optional[int] = None) -> None:
        """设置写入包间延迟（秒）与单包上限（字节）。"""
        if packet_delay is not None:
            self._packet_delay = max(0.0, float(packet_delay))
        if max_chunk is not None:
            self._max_chunk = max(MIN_CHUNK, int(max_chunk))

    # ── 事件循环 ──────────────────────────────────────────────────────────

    def _ensure_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """惰性启动私有事件循环线程（连接后常驻，用于承接通知回调）。"""
        loop = self._loop
        if loop is not None and loop.is_running():
            return loop
        if self._closing:
            return None
        self._loop_ready.clear()

        def _runner() -> None:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            self._loop = new_loop
            self._loop_ready.set()
            try:
                new_loop.run_forever()
            finally:
                # 退出前取消残留任务，避免 "Task was destroyed but it is pending"
                try:
                    pending = asyncio.all_tasks(new_loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        new_loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                    new_loop.run_until_complete(new_loop.shutdown_asyncgens())
                except Exception:
                    pass
                new_loop.close()

        self._loop_thread = threading.Thread(
            target=_runner, name="bluetooth-loop", daemon=True
        )
        self._loop_thread.start()
        self._loop_ready.wait(timeout=self.LOOP_READY_TIMEOUT)
        return self._loop

    def _submit(self, coro) -> bool:
        """把协程投递到事件循环线程；线程不可用时关掉协程并报错。"""
        loop = self._ensure_loop()
        if loop is None:
            coro.close()
            self.error_occurred.emit("蓝牙线程已关闭，无法执行该操作")
            return False
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError as exc:  # 循环已停止
            coro.close()
            self.error_occurred.emit(f"蓝牙线程不可用：{exc}")
            return False
        return True

    def _report_missing_bleak(self) -> None:
        self.error_occurred.emit(BLEAK_MISSING_HINT)
        self.log_message.emit(BLEAK_MISSING_HINT)

    # ── 扫描 ──────────────────────────────────────────────────────────────

    def start_scan(self, timeout: Optional[float] = None) -> bool:
        """扫描周边 BLE 设备（结果逐个经 ``device_found`` 投递）。"""
        if not self.bleak_available():
            self._report_missing_bleak()
            return False
        if self._scanning:
            self.log_message.emit("扫描已在进行中…")
            return False
        seconds = float(timeout) if timeout else DEFAULT_SCAN_TIMEOUT
        self._scanning = True
        if not self._submit(self._scan_coro(seconds)):
            self._scanning = False
            return False
        self.scan_started.emit()
        self.log_message.emit(f"开始扫描 BLE 设备（{seconds:.1f}s）…")
        return True

    async def _scan_coro(self, timeout: float) -> None:
        try:
            found = await BleakScanner.discover(timeout=timeout, return_adv=True)
        except Exception as exc:
            self._scanning = False
            message = f"扫描失败：{type(exc).__name__}: {exc}"
            self.scan_error.emit(message)
            self.log_message.emit(message)
            return

        items = []
        for address, payload in dict(found or {}).items():
            device, adv = (payload if isinstance(payload, (tuple, list)) and len(payload) == 2
                           else (payload, None))
            name = str(getattr(adv, "local_name", "") or "") or str(getattr(device, "name", "") or "")
            rssi = getattr(adv, "rssi", None)
            if rssi is None:
                rssi = getattr(device, "rssi", 0)
            try:
                rssi_value = int(rssi)
            except (TypeError, ValueError):
                rssi_value = 0
            # 由强到弱；同强度下**有名称的排前面**（无名设备多是随机地址）
            items.append((name, str(address), rssi_value))
        items.sort(key=lambda item: (-item[2], item[0] == ""))

        for name, address, rssi_value in items:
            self.device_found.emit(name, address, rssi_value)
        self._scanning = False
        self.scan_finished.emit(len(items))
        self.log_message.emit(f"扫描完成：发现 {len(items)} 个 BLE 设备")

    # ── 连接 / 断开 ───────────────────────────────────────────────────────

    def connect_device(self, address: str, name: str = "") -> bool:
        """连接指定地址的设备（失败自动重试，结果经 ``connected``/``connect_error``）。"""
        if not self.bleak_available():
            self._report_missing_bleak()
            return False
        if self._connected:
            self.log_message.emit("已连接，请先断开")
            return False
        if not str(address or "").strip():
            self.connect_error.emit("未选择设备")
            return False
        self.connecting.emit(str(address), str(name or ""))
        self.log_message.emit(f"正在连接 {name or address} …")
        return self._submit(self._connect_coro(str(address), str(name or "")))

    async def _connect_coro(self, address: str, name: str) -> None:
        last_error = ""
        for attempt in range(1, DEFAULT_CONNECT_RETRIES + 1):
            try:
                client = BleakClient(
                    address,
                    disconnected_callback=self._on_disconnected_cb,
                    timeout=DEFAULT_CONNECT_TIMEOUT,
                )
                await client.connect()
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self.log_message.emit(f"连接失败（{attempt}/{DEFAULT_CONNECT_RETRIES}）：{last_error}")
                if attempt < DEFAULT_CONNECT_RETRIES:
                    await asyncio.sleep(0.5)
                continue

            self._client = client
            self._connected = True
            self._device_address = address
            self._device_name = name or address
            try:
                self._mtu = int(getattr(client, "mtu_size", 0) or 0)
            except Exception:
                self._mtu = 0
            self._characteristics = await self._collect_characteristics(client)
            self.characteristics_updated.emit(list(self._characteristics))
            self._start_monitor()
            self.connected.emit(self._device_name, address)
            self.connection_changed.emit(True)
            self.log_message.emit(
                f"已连接 {self._device_name}（{address}，MTU={self._mtu or '未知'}，"
                f"特征码 {len(self._characteristics)} 个）"
            )
            if self._recv_uuids:
                await self._subscribe_coro()
            # MTU 协商是异步的：放在 connected / 订阅**之后**等结果，界面不被拖住（1.23.80）
            await self._poll_mtu_if_needed(client)
            return

        self.connect_error.emit(last_error or "连接失败")
        self.connection_changed.emit(False)

    def disconnect_device(self) -> bool:
        """主动断开连接（未连接时返回 False）。"""
        if self._client is None and not self._connected:
            self.log_message.emit("当前未连接蓝牙设备")
            return False
        self.log_message.emit("正在断开连接…")
        return self._submit(self._disconnect_coro())

    async def _disconnect_coro(self) -> None:
        client, self._client = self._client, None
        self._connected = False
        self._char_objects.clear()   # 活对象随连接失效，防被重读
        self._cancel_monitor()
        for uuid, frame in self._reassembler.flush():
            self.frame_received.emit(uuid, frame)
        if client is not None:
            try:
                await client.disconnect()
            except Exception as exc:
                self.log_message.emit(f"断开时出现异常：{type(exc).__name__}: {exc}")
        self.disconnected.emit()
        self.connection_changed.emit(False)
        self.log_message.emit("已断开蓝牙连接")

    def _on_disconnected_cb(self, client) -> None:
        """bleak 的掉线回调（在事件循环线程执行）。"""
        if self._closing or not self._connected:
            return
        self._client = None
        self._connected = False
        self._char_objects.clear()   # 活对象随连接失效，防被重读
        self._cancel_monitor()
        for uuid, frame in self._reassembler.flush():
            self.frame_received.emit(uuid, frame)
        self.disconnected.emit()
        self.connection_changed.emit(False)
        self.log_message.emit("蓝牙设备已断开连接")

    # ── MTU / 写上限实时化（1.23.80）────────────────────────────────────────
    #
    # ATT_MTU 由**操作系统异步协商**（Windows 上应用层只能读、不能请求），连接瞬间读到的
    # 可能还是 ATT 默认值 23（负载 20）⇒ 现场表现是「同一台设备有时 20 字节、有时 512 字节」。
    # 两条措施：① 连接后轮询等协商结果；② **每次发送前重读**，分包按发送那一刻的真实上限。

    def _refresh_live_limits(self) -> bool:
        """重读 MTU 与各特征码实时上限；**有变化才**更新 + 发信号 + 记日志。

        Returns:
            是否有变化。无 client / 未连接 / 读数异常时静默返回 False（不抛）。
        """
        client = self._client
        if client is None or not self._connected:
            return False
        try:
            mtu = int(getattr(client, "mtu_size", 0) or 0)
        except Exception:
            mtu = 0
        mtu_changed = bool(mtu) and mtu != self._mtu
        old_mtu = self._mtu
        if mtu_changed:
            self._mtu = mtu

        limit_changed = False
        for info in self._characteristics:
            obj = self._char_objects.get(str(info.get("uuid", "")))
            if obj is None:
                continue
            try:
                value = int(getattr(obj, "max_write_without_response_size", 0) or 0)
            except Exception:
                continue
            if value and value != int(info.get("max_write") or 0):
                info["max_write"] = value
                limit_changed = True

        if not (mtu_changed or limit_changed):
            return False

        # 日志口径与 `_chunk_plan` 一致：只说读数，不在这里推导分包尺寸（推导唯一实现在
        # `core.chunk_size_for_mtu` / `_chunk_plan`）
        best = max([int(c.get("max_write") or 0) for c in self._characteristics] or [0])
        if mtu_changed:
            self.log_message.emit(
                f"MTU 协商更新：{old_mtu or '未知'} → {self._mtu}"
                + (f"（特征码免响应写上限 {best} 字节）" if best else "")
            )
        else:
            self.log_message.emit(f"特征码免响应写上限更新为 {best} 字节（协商 MTU={self._mtu}）")
        self.mtu_updated.emit(int(self._mtu), [dict(c) for c in self._characteristics])
        return True

    async def _poll_mtu_if_needed(self, client) -> None:
        """连接后轮询等 MTU 协商结果（仅当仍是默认值/未知时）。

        位置在 `connected` 与订阅**之后** ⇒ 界面与订阅不被等待拖住；等待期间用户已经可以
        收发（发送前还会重读一次）。超时**只提示一行**，不得报错：对端确实只支持默认值时
        与「结果还没回报」在读数上不可区分。
        """
        if not mtu_is_unnegotiated(self._mtu):
            return
        waited = 0.0
        while waited < MTU_POLL_TIMEOUT:
            await asyncio.sleep(MTU_POLL_INTERVAL)
            waited += MTU_POLL_INTERVAL
            if self._closing or not self._connected or self._client is not client:
                return  # 断开 / 换设备 / 退出：静默收尾
            if self._refresh_live_limits():
                return  # 协商结果到了（日志与信号已在刷新里发出）
        if not self._closing and self._connected and self._client is client:
            self.log_message.emit(
                f"{MTU_POLL_TIMEOUT:.1f} 秒内未收到 MTU 协商结果，按当前值分包"
                f"（MTU={self._mtu or '未知'}；对端可能只支持 ATT 默认值，不影响收发）"
            )

    # ── 特征码 / 订阅 ─────────────────────────────────────────────────────

    async def _collect_characteristics(self, client) -> List[dict]:
        try:
            services = client.services
        except Exception:
            services = None
        if services is None:
            try:
                services = await client.get_services()
            except Exception:
                services = None

        infos: List[dict] = []
        objects: dict = {}
        for service in services or []:
            for char in getattr(service, "characteristics", None) or []:
                props = [str(p) for p in (getattr(char, "properties", None) or [])]
                uuid = str(getattr(char, "uuid", ""))
                infos.append({
                    "uuid": uuid,
                    "short": short_uuid(uuid),
                    "service_uuid": str(getattr(service, "uuid", "")),
                    "service_short": short_uuid(getattr(service, "uuid", "")),
                    "properties": props,
                    "description": str(getattr(char, "description", "") or ""),
                    "can_recv": ("notify" in props) or ("indicate" in props),
                    "can_send": ("write" in props) or ("write-without-response" in props),
                    "max_write": int(getattr(char, "max_write_without_response_size", 0) or 0),
                })
                objects[uuid] = char
        self._char_objects = objects
        return infos

    def set_characteristics(self, recv_uuids, send_uuids) -> None:
        """设置接收/发送特征码；已连接时立即重新订阅接收方向。"""
        self._recv_uuids = [str(u) for u in (recv_uuids or []) if str(u or "").strip()]
        self._send_uuids = [str(u) for u in (send_uuids or []) if str(u or "").strip()]
        if self._connected and self._recv_uuids:
            self._submit(self._subscribe_coro())
        elif self._connected:
            # 无接收通道（如探测「只验证写入」的候选）：立刻宣告「订阅阶段结束」，
            # 否则等待 subscribe_finished 的调用方会一直挂着（一键探测的时序依赖它）
            self.subscribe_finished.emit([], True)

    async def _subscribe_coro(self) -> bool:
        client = self._client
        if client is None:
            self.subscribe_finished.emit([], False)
            return False
        subscribed = 0
        done: List[str] = []
        for uuid in self._recv_uuids:
            try:
                # 二次订阅同一特征码前先停：部分后端对重复 start_notify 直接报错
                try:
                    await client.stop_notify(uuid)
                except Exception:
                    pass
                await client.start_notify(uuid, self._on_notify)
                subscribed += 1
                done.append(str(uuid))
            except Exception as exc:
                self.log_message.emit(
                    f"订阅失败（{short_uuid(uuid)}）：{type(exc).__name__}: {exc}"
                )
        if subscribed:
            self.log_message.emit(f"已订阅 {subscribed} 个接收特征码，等待设备上报…")
        # 订阅阶段结束（成功与失败都发）：一键探测据此决定何时才写
        self.subscribe_finished.emit(done, subscribed > 0)
        return subscribed > 0

    def _on_notify(self, sender, data) -> None:
        """bleak 通知回调（事件循环线程）：计数 + 投给重组器。"""
        if self._closing:
            return
        chunk = bytes(data or b"")
        if not chunk:
            return
        uuid = str(getattr(sender, "uuid", "") or "")
        self._rx_bytes += len(chunk)
        self.notification_received.emit(uuid, chunk)
        self._reassembler.feed(uuid, chunk)
        self.stats_changed.emit(self._rx_bytes, self._tx_bytes)

    # ── 分包重组巡检 ──────────────────────────────────────────────────────

    def _start_monitor(self) -> None:
        loop = self._loop
        if loop is None:
            return
        task = self._monitor_task
        if task is not None and not task.done():
            return
        self._monitor_task = loop.create_task(self._monitor_coro())

    def _cancel_monitor(self) -> None:
        task, self._monitor_task = self._monitor_task, None
        if task is None or task.done():
            return
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)   # 可能从 GUI 线程调用
        else:
            task.cancel()

    async def _monitor_coro(self) -> None:
        """按静默超时切帧：轮询重组器并把完整报文发给界面。"""
        while not self._closing:
            await asyncio.sleep(self.MONITOR_TICK)
            for uuid, frame in self._reassembler.poll():
                self.frame_received.emit(uuid, frame)

    # ── 写入 ──────────────────────────────────────────────────────────────

    def send_data(self, data: bytes, single_write: bool = False) -> bool:
        """向已选发送特征码写入数据（默认按 MTU 分包 + 包间延迟）。

        ``single_write=True``（升级页用）：**整段数据必须一次 ATT 写发出**，超过
        :meth:`single_write_limit` 就**拒绝发送并报错**（不静默分包 —— 分包会让设备收到
        被切断的 698 帧）。
        """
        payload = bytes(data or b"")
        if not payload:
            self.error_occurred.emit("发送内容为空")
            return False
        if not self._connected or self._client is None:
            self.error_occurred.emit("蓝牙未连接，无法发送")
            return False
        targets = self._write_targets()
        if not targets:
            self.error_occurred.emit("未选择发送特征码（先点「特征码…」选择）")
            return False
        if single_write:
            limit = self.single_write_limit(targets)
            if len(payload) > limit:
                self.error_occurred.emit(
                    f"整帧 {len(payload)} 字节超过一次 ATT 写上限 {limit} 字节："
                    "请调小「每包字节数」（或重连让 MTU 重新协商）")
                return False
        return self._submit(self._write_coro(list(targets), payload, single_write))

    def _limit_plan(self, targets: List[str]) -> tuple:
        """一次 ATT 写的**物理**上限 + 来源说明（**不叠** `_max_chunk`）。

        Returns: ``(limit, source_text)``；特征码给了免响应写上限就用它，否则用 `MTU − 3`。
        这是本 worker 里「一次 ATT 写能承载多少字节」的**唯一实现**：蓝牙页的分包上限
        （`_chunk_plan` = 本上限再夹 `_max_chunk`）与升级页的「整帧一次写出」共用它。
        """
        best = 0
        for char in self._characteristics:
            if char.get("uuid") in targets:
                best = max(best, int(char.get("max_write") or 0))
        if best > 0:
            return max(MIN_CHUNK, best), f"特征码免响应写上限 {best} 字节"
        mtu = int(self._mtu or 0)
        if mtu > 3:
            return chunk_size_for_mtu(mtu, _NO_CHUNK_CAP), f"协商 MTU {mtu} − 3（ATT 头）"
        return chunk_size_for_mtu(0, _NO_CHUNK_CAP), "MTU 未知，回落 ATT 最小可用值 23 − 3"

    def single_write_limit(self, targets: Optional[List[str]] = None) -> int:
        """**一次 ATT 写**能承载的最大负载字节数（升级页按它反推每包块长）。

        与蓝牙页「单包上限」的区别：这里不夹 `_max_chunk`（那是蓝牙页对连续写的保护值），
        因为升级页要求**一整帧 698 报文一次写出**（否则设备得自己重组 ATT 分包）。
        """
        return self._limit_plan(self._write_targets(targets))[0]

    def _write_targets(self, targets: Optional[List[str]] = None) -> List[str]:
        """实际写入目标：显式给的 > 已选发送特征码 > 第一个接收特征码。"""
        if targets:
            return [str(u) for u in targets]
        return list(self._send_uuids or self._recv_uuids[:1])

    def _chunk_plan(self, targets: List[str]) -> tuple:
        """单包写入尺寸 + **尺寸来源说明**（R6：说明必须与尺寸同一来源，界面不另算一份）。

        Returns: ``(chunk_size, source_text)``
        """
        limit, source = self._limit_plan(targets)
        return max(MIN_CHUNK, min(self._max_chunk, limit)), source

    def _chunk_size_for(self, targets: List[str]) -> int:
        """按「目标特征码免响应写上限 / 协商 MTU」取单包尺寸（夹到上限）。"""
        return self._chunk_plan(targets)[0]

    async def _write_coro(self, targets: List[str], payload: bytes,
                          single_write: bool = False) -> None:
        client = self._client
        if client is None:
            self.error_occurred.emit("蓝牙未连接，无法发送")
            return
        # 发送前重读实时上限（1.23.80）：MTU 可能刚协商完 —— 分包必须按**此刻**的真实值，
        # 否则重连前读到的 20（ATT 默认）会让每一次发送都白拆包
        self._refresh_live_limits()
        if single_write:
            limit = self.single_write_limit(targets)
            if len(payload) > limit:      # 与 `send_data` 同一判据（这里挡「投递后 MTU 又变小」）
                self.error_occurred.emit(
                    f"整帧 {len(payload)} 字节超过一次 ATT 写上限 {limit} 字节，已取消发送")
                return
            chunks, chunk_size, chunk_source = [payload], limit, "整帧一次写出（升级通道）"
        else:
            chunk_size, chunk_source = self._chunk_plan(targets)
            chunks = split_chunks(payload, chunk_size)
        # 分包不可消除（ATT 层物理上限）：把「为什么分包 / 单包上限是多少」写在日志里，
        # 免去用户「25 字节为什么发两包」的困惑（R6.1）。
        if len(chunks) > 1:
            self.log_message.emit(
                f"数据 {len(payload)} 字节按单包上限 {chunk_size} 字节分为 {len(chunks)} 包"
                f"（{chunk_source}；协商 MTU={self._mtu or '未知'}）"
                "　※ ATT 层限制，应用层无法一次写出更多字节"
            )
        for index, chunk in enumerate(chunks, start=1):
            if not self._connected or self._client is not client:
                self.log_message.emit(
                    f"写入中断：连接已断开（已发出 {index - 1}/{len(chunks)} 包）"
                )
                return
            for uuid in targets:
                try:
                    await client.write_gatt_char(uuid, chunk, response=False)
                except Exception as exc:
                    # 免响应写失败时退回「有响应写」：部分设备只声明 write
                    try:
                        await client.write_gatt_char(uuid, chunk, response=True)
                    except Exception as exc2:
                        message = (
                            f"写入失败（{short_uuid(uuid)}，第 {index}/{len(chunks)} 包）："
                            f"{type(exc2).__name__}: {exc2}"
                        )
                        self.error_occurred.emit(message)
                        self.log_message.emit(message)
                        return
                    del exc
            self._tx_bytes += len(chunk) * len(targets)
            if len(chunks) > 1:
                self.send_progress.emit(index, len(chunks), chunk)
            if index < len(chunks) and self._packet_delay > 0:
                await asyncio.sleep(self._packet_delay)
        self.data_sent.emit(payload)
        self.stats_changed.emit(self._rx_bytes, self._tx_bytes)

    # ── 关闭 ──────────────────────────────────────────────────────────────

    def shutdown(self, timeout: float = 3.0) -> None:
        """断开连接并停掉事件循环线程（**幂等**，供窗口关闭/页面销毁调用）。"""
        if self._closing:
            return
        self._closing = True
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown_coro(), loop).result(timeout=timeout)
            except Exception:
                pass
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
        thread = self._loop_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._loop = None
        self._loop_thread = None
        if self._connected:
            self._connected = False
            self.connection_changed.emit(False)

    async def _shutdown_coro(self) -> None:
        client, self._client = self._client, None
        self._connected = False
        self._cancel_monitor()
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
