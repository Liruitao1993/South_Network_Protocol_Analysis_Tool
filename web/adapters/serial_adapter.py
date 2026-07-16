# -*- coding: utf-8 -*-
"""串口适配器：直接使用 pyserial，不依赖 QThread
在后台线程中运行串口读取，通过回调通知 NiceGUI 事件循环
"""
import threading
from typing import Optional, Callable, List
from queue import Queue, Empty
import serial
import serial.tools.list_ports


class SerialAdapter:
    """串口适配器：后台线程读取，回调通知"""

    def __init__(self):
        self._ser: Optional[serial.Serial] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._tx_queue: Queue = Queue()
        self._running = False
        self._callbacks = {
            'data_received': [],
            'connection_changed': [],
            'error': [],
            'raw_data_received': [],
        }

    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def open(self, port: str, baudrate: int, parity: str) -> bool:
        if self._running:
            return True
        parity_map = {"无": "N", "偶": "E", "奇": "O", "N": "N", "E": "E", "O": "O"}
        parity_val = parity_map.get(parity, "N")
        try:
            self._ser = serial.Serial(
                port=port, baudrate=baudrate,
                bytesize=8, parity=parity_val, stopbits=1,
                timeout=0.1,
            )
        except Exception as e:
            self._notify('error', str(e))
            return False
        self._running = True
        self._worker_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._worker_thread.start()
        self._notify('connection_changed', True)
        return True

    def _read_loop(self):
        while self._running and self._ser and self._ser.is_open:
            try:
                try:
                    data = self._tx_queue.get_nowait()
                    self._ser.write(data)
                except Empty:
                    pass
                data = self._ser.read(256)
                if data:
                    self._notify('data_received', data)
                    self._notify('raw_data_received', data)
            except Exception as e:
                self._notify('error', str(e))
                break

    def _notify(self, event: str, *args):
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args)
            except Exception:
                pass

    def close(self):
        self._running = False
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        if self._worker_thread:
            self._worker_thread.join(timeout=2)
        self._worker_thread = None
        self._notify('connection_changed', False)

    def send(self, data: bytes):
        if self._ser and self._running:
            self._tx_queue.put(data)

    @property
    def is_open(self) -> bool:
        return self._running and self._ser is not None and self._ser.is_open

    @staticmethod
    def list_ports() -> List[str]:
        try:
            return [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            return []
