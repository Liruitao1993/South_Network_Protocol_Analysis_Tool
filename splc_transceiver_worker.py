# -*- coding: utf-8 -*-
"""收发机控制页的串口线程（发射机 / 接收机 / 工装板 三个独立端口）。

为什么不复用 ``serial_worker.SerialWorker``：
``SerialWorker._process_buffer`` 只认「FT1.2 / DL-T645」两种 ``68H`` 帧结构，会把
本页的 96..16 业务帧与「68+6保留+68」命令帧当成残帧反复扫描 —— 接收机侧要的是
**原始字节流**（交给解帧器与监控器），发射机侧只要「能写」。所以这里提供一个极简
线程：读到的字节原样 ``raw_data_received`` 抛给 GUI 线程，写只做 ``write``。

信号名刻意与 ``SerialWorker`` 对齐（``raw_data_received`` / ``connection_changed`` /
``error_occurred`` / ``log_message``），这样 ``RealtimeMonitorWidget.set_serial_worker()``
可以直接绑定，不需要任何适配层。
"""

from __future__ import annotations

from threading import Lock
from typing import Optional

import serial
import serial.tools.list_ports

from PySide6.QtCore import QThread, Signal

import thread_registry


class SplcSerialPort(QThread):
    """一个串口端口的读线程（写由 GUI 线程直接调用）。"""

    #: 收到的原始字节流（未解帧）
    raw_data_received = Signal(bytes)
    #: 连接状态变化
    connection_changed = Signal(bool)
    #: 错误信息
    error_occurred = Signal(str)
    #: 日志
    log_message = Signal(str)

    def __init__(self, role: str = "tx", parent=None):
        super().__init__(parent)
        self._role = role
        thread_registry.track(self, f"SplcSerialPort[{role}]")
        self._ser: Optional[serial.Serial] = None
        self._port = ""
        self._baudrate = 921600
        self._bytesize = 8
        self._parity = "N"
        self._stopbits = 1.0
        self._running = False
        self._write_lock = Lock()

    # ------------------------------------------------------------ 配置
    @property
    def role(self) -> str:
        return self._role

    def configure(self, port: str, baudrate: int = 921600, parity: str = "N") -> None:
        """配置串口参数（打开前调用）。"""
        self._port = str(port or "")
        try:
            self._baudrate = int(baudrate)
        except (TypeError, ValueError):
            self._baudrate = 921600
        self._parity = parity

    def description(self) -> str:
        return f"{self._port or '未选串口'} @ {self._baudrate}"

    # ------------------------------------------------------------ 开关
    def open_port(self) -> bool:
        if self._ser is not None and self._ser.is_open:
            return True
        if not self._port:
            self.error_occurred.emit("未选择串口")
            return False
        try:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=self._bytesize,
                parity=self._parity if self._parity in ("N", "E", "O") else "N",
                stopbits=self._stopbits,
                timeout=0.05,
            )
        except (serial.SerialException, ValueError, OSError) as exc:
            self.error_occurred.emit(f"打开串口失败：{exc}")
            self._ser = None
            return False
        self._running = True
        if not self.isRunning():
            self.start()
        self.connection_changed.emit(True)
        self.log_message.emit(f"[串口] 已打开 {self.description()}")
        return True

    def close_port(self) -> None:
        self._running = False
        ser = self._ser
        self._ser = None
        if ser is not None and ser.is_open:
            try:
                ser.close()
            except Exception:  # noqa: BLE001 - 关闭失败不影响退出
                pass
        # 读线程可能正卡在 read()，等它自己收尾（timeout=0.05 保证最多 50ms）
        if self.isRunning():
            self.wait(500)
        self.connection_changed.emit(False)
        self.log_message.emit(f"[串口] 已关闭 {self._port}")

    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def is_connected(self) -> bool:
        """与 ``SerialWorker`` 同名（状态栏/通道控制器统一调用）。"""
        return self.is_open()

    # ------------------------------------------------------------ 收发
    def write(self, data: bytes) -> bool:
        """写字节（不额外发日志，由调用方决定怎么记）。"""
        if self._ser is None or not self._ser.is_open:
            self.error_occurred.emit("串口未打开")
            return False
        try:
            with self._write_lock:
                self._ser.write(bytes(data))
                self._ser.flush()
            return True
        except (serial.SerialException, OSError) as exc:
            self.error_occurred.emit(f"发送失败：{exc}")
            return False

    def run(self) -> None:
        while self._running and self._ser is not None and self._ser.is_open:
            try:
                waiting = self._ser.in_waiting
                if waiting:
                    chunk = self._ser.read(waiting)
                    if chunk:
                        self.raw_data_received.emit(chunk)
                else:
                    self.msleep(5)
            except (serial.SerialException, OSError) as exc:
                if self._running:
                    self.error_occurred.emit(f"读取异常：{exc}")
                break
        self._running = False
        ser = self._ser
        self._ser = None
        if ser is not None and ser.is_open:
            try:
                ser.close()
            except Exception:  # noqa: BLE001
                pass
        self.connection_changed.emit(False)

    # ------------------------------------------------------------ 枚举
    @staticmethod
    def list_ports() -> list:
        """可用串口设备名列表。"""
        try:
            return [p.device for p in serial.tools.list_ports.comports()]
        except Exception:  # noqa: BLE001 - 枚举失败不应崩界面
            return []
