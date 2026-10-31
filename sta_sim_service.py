# -*- coding: utf-8 -*-
"""从节点模拟服务 —— 国网流程测试页内置的「虚拟表」串口从站。

为什么需要它
------------
流程测试要在同一页面里完成「从节点配置 + 启动对应协议的虚拟表」，而 645 与 698.45
两个虚拟表原本分属协议6 / 协议8 两个独立页面、各自配置串口。这里把两者合成一个服务：

- 一条串口同时当 **645 从站** 和 **698.45 从站**（按帧结构自动分流）；
- 开工时按「组网参数里的从节点协议」自动决定启用哪个引擎；
- 复位 STA（645 广播 14H 写数据）也在这里下发，不依赖其它页面。

引擎完全复用现有实现（``meter_sim.MeterSimEngine`` / ``dlt645_sim.DLT645MeterSim``），
本模块只做「串口 + 分帧 + 分流 + 日志」这一层。
"""

from __future__ import annotations

import time
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

import sta_reset
from dlt645_sim import DLT645MeterSim
from dlt645_sim.archive import DLT645Archive
from meter_sim import MeterSimEngine, SimOptions, load_archive, link_layer

#: 协议代号 —— 与 ``gdw_test_network.PROTO_*`` 保持一致（645-2007 / 698.45）
PROTO_645 = 2
PROTO_698 = 3


class StaSimService(QThread):
    """串口从站：按需启用 645 / 698.45 引擎，自动分流应答。"""

    log = Signal(str)
    frame_exchanged = Signal(str, list)      # 请求 hex, [应答 hex, ...]

    def __init__(self, port: str, baud: int = 115200, parity: str = "N",
                 stopbits: float = 1, protocols: Optional[set] = None,
                 meter_address: str = "", parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = int(baud)
        self.parity = parity
        self.stopbits = float(stopbits)
        self.protocols = set(protocols or {PROTO_645, PROTO_698})
        self.meter_address = (meter_address or "").strip()
        self._running = False
        self._engine_645: Optional[DLT645MeterSim] = None
        self._engine_698: Optional[MeterSimEngine] = None
        self._tx: List[bytes] = []
        #: 最近发出的应答帧（供流程测试判定「CCO 上报的数据是否与虚拟表应答一致」）
        self.recent_responses: List[bytes] = []

    # ── 引擎 ────────────────────────────────────────────────────────
    def _engine_for_645(self) -> DLT645MeterSim:
        if self._engine_645 is None:
            self._engine_645 = DLT645MeterSim(
                address=self.meter_address or "000000000000",
                archive=DLT645Archive(),
            )
        return self._engine_645

    def _engine_for_698(self) -> MeterSimEngine:
        if self._engine_698 is None:
            options = SimOptions()
            if self.meter_address:
                options.meter_address = self.meter_address
            self._engine_698 = MeterSimEngine(load_archive(), options)
        return self._engine_698

    # ── 对外 ────────────────────────────────────────────────────────
    def send_frame(self, frame: bytes) -> bool:
        """把一帧排进发送队列（线程独占串口句柄，不能从 GUI 线程直写）。"""
        if not self._running:
            return False
        self._tx.append(bytes(frame))
        return True

    def protocol_text(self) -> str:
        names = []
        if PROTO_645 in self.protocols:
            names.append("645-2007")
        if PROTO_698 in self.protocols:
            names.append("698.45")
        return " + ".join(names) or "（未启用）"

    def stop(self) -> None:
        self._running = False

    # ── 线程主体 ────────────────────────────────────────────────────
    def run(self) -> None:  # noqa: C901 - 串口循环，逻辑线性
        try:
            import serial
        except Exception as exc:            # pragma: no cover
            self.log.emit(f"❌ 串口库不可用：{exc}")
            return
        try:
            ser = serial.Serial()
            ser.port = self.port
            ser.baudrate = self.baud
            ser.parity = self.parity
            ser.stopbits = self.stopbits
            ser.timeout = 0.2
            ser.open()
        except Exception as exc:
            self.log.emit(f"❌ 串口打开失败: {exc}")
            return

        self._running = True
        self.log.emit(f"● 从节点模拟已启动 {self.port}@{self.baud}（{self.protocol_text()}）")
        buf = b""
        try:
            while self._running:
                try:
                    n = ser.in_waiting
                    if n:
                        buf += ser.read(n)
                    else:
                        time.sleep(0.05)

                    while self._tx:
                        out = self._tx.pop(0)
                        try:
                            ser.write(out)
                            self.log.emit(f"⇱ 已下发({len(out)}B): {out.hex(' ')}")
                        except Exception as exc:
                            self.log.emit(f"❌ 下发失败: {exc}")

                    buf = self._dispatch_645(buf, ser)
                    buf = self._dispatch_698(buf, ser)
                except Exception as exc:     # 单帧异常不该杀掉整个从站
                    self.log.emit(f"❌ 监听异常: {exc}")
                    time.sleep(0.2)
        finally:
            try:
                ser.close()
            except Exception:
                pass
            self.log.emit("○ 从节点模拟已停止")

    # ── 分流 ────────────────────────────────────────────────────────
    def _dispatch_645(self, buf: bytes, ser) -> bytes:
        """先摘 645 帧（结构强、不会误吞 698 长帧）。"""
        if PROTO_645 not in self.protocols:
            return buf
        try:
            frames = link_layer.extract_645_frames(buf)
        except Exception:
            return buf
        for frame in frames:
            buf = buf.replace(frame, b"", 1)
            self._handle_645(frame, ser)
        return buf

    def _handle_645(self, frame: bytes, ser) -> None:
        info = sta_reset.parse_frame(frame)
        if info is not None:
            self.log.emit(f"← 收到 645 帧({len(frame)}B): {frame.hex(' ')}")
            self.log.emit(f"  {sta_reset.describe(frame)}")
            if info["broadcast"]:
                self.log.emit("  → 广播复位命令：按 645「广播不要求应答」静默处理")
                self.frame_exchanged.emit(frame.hex(" "), [])
                return
            rsp = sta_reset.build_ack_frame(frame)
            try:
                ser.write(rsp)
                self.log.emit(f"→ 回复({len(rsp)}B): {rsp.hex(' ')}")
                self.frame_exchanged.emit(frame.hex(" "), [rsp.hex(" ")])
            except Exception as exc:
                self.log.emit(f"❌ 回复失败: {exc}")
            return
        try:
            resps = self._engine_for_645().handle_frame(frame)
        except Exception as exc:
            self.log.emit(f"❌ 645 处理异常: {exc}")
            return
        self.log.emit(f"← 收到 645 请求({len(frame)}B): {frame.hex(' ')}")
        for msg in getattr(self._engine_for_645(), "logs", [])[-6:]:
            self.log.emit("  " + str(msg))
        self._write_all(ser, frame, resps)

    def _dispatch_698(self, buf: bytes, ser) -> bytes:
        if PROTO_698 not in self.protocols:
            return buf
        try:
            frames, _consumed, rest = link_layer.extract_frames(buf)
        except Exception:
            return buf
        if not frames:
            return buf
        buf = rest if rest is not None else b""
        for frame in frames:
            try:
                resps = self._engine_for_698().handle_frame(frame)
            except Exception as exc:
                self.log.emit(f"❌ 698 处理异常: {exc}")
                continue
            self.log.emit(f"← 收到 698 请求({len(frame)}B): {frame.hex(' ')}")
            for msg in getattr(self._engine_for_698(), "logs", [])[-6:]:
                self.log.emit("  " + str(msg))
            self._write_all(ser, frame, resps)
        return buf

    def _write_all(self, ser, request: bytes, resps: List[bytes]) -> None:
        hexes: List[str] = []
        for rsp in resps or []:
            try:
                ser.write(rsp)
                hexes.append(rsp.hex(" "))
                self.log.emit(f"→ 回复({len(rsp)}B): {rsp.hex(' ')}")
                self.recent_responses.append(bytes(rsp))
                del self.recent_responses[:-50]
            except Exception as exc:
                self.log.emit(f"❌ 回复失败: {exc}")
        self.frame_exchanged.emit(request.hex(" "), hexes)
