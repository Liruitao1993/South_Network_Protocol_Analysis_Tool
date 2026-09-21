"""串口通信工作线程

基于 PySide6 QThread + pyserial，提供：
- 串口打开/关闭
- 后台读取循环
- FT1.2 帧自动识别与提取
- 发送十六进制帧
- 信号通知GUI层
"""

from typing import Optional
import time
import serial
import serial.tools.list_ports

from PySide6.QtCore import QThread, Signal

import thread_registry


class SerialWorker(QThread):
    """串口后台工作线程"""

    # 信号定义
    frame_received = Signal(bytes)       # 收到一帧完整数据
    raw_data_received = Signal(bytes)   # 收到原始串口数据（未经帧解析）
    log_message = Signal(str)            # 日志消息（供文本框显示）
    connection_changed = Signal(bool)    # 连接状态变化
    error_occurred = Signal(str)         # 错误信息

    def __init__(self, parent=None):
        super().__init__(parent)
        thread_registry.track(self, "SerialWorker")
        self._ser: Optional[serial.Serial] = None
        self._port: str = ""
        self._baudrate: int = 9600
        self._bytesize: int = 8
        self._parity: str = "N"
        self._stopbits: float = 1.0
        self._running: bool = False
        self._buffer: bytearray = bytearray()

    def configure(self, port: str, baudrate: int = 9600,
                  bytesize: int = 8, parity: str = "N", stopbits: float = 1.0):
        """配置串口参数（打开前调用）"""
        self._port = port
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._parity = parity
        self._stopbits = stopbits

    def open_port(self) -> bool:
        """打开串口，成功返回 True"""
        if self._ser and self._ser.is_open:
            return True
        try:
            parity_map = {"无": "N", "偶": "E", "奇": "O"}
            parity_val = parity_map.get(self._parity, self._parity)
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=self._bytesize,
                parity=parity_val,
                stopbits=self._stopbits,
                timeout=0.1,
            )
            self._running = True
            if not self.isRunning():
                self.start()
            self.connection_changed.emit(True)
            self.log_message.emit(f"[串口] 已打开 {self._port} @ {self._baudrate}")
            return True
        except serial.SerialException as e:
            self.error_occurred.emit(f"打开串口失败: {e}")
            return False

    def close_port(self):
        """关闭串口"""
        self._running = False
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        self.connection_changed.emit(False)
        self.log_message.emit("[串口] 已关闭")

    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def send_frame(self, frame_bytes: bytes) -> bool:
        """发送一帧字节数据"""
        if not self._ser or not self._ser.is_open:
            self.error_occurred.emit("串口未打开")
            return False
        try:
            self._ser.write(frame_bytes)
            hex_str = frame_bytes.hex().upper()
            formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
            self.log_message.emit(f"[发送] {formatted}")
            return True
        except serial.SerialException as e:
            self.error_occurred.emit(f"发送失败: {e}")
            return False

    def send_hex_string(self, hex_str: str) -> bool:
        """发送十六进制字符串（自动去除空格）"""
        clean = hex_str.replace(" ", "").strip()
        if not clean:
            return False
        try:
            data = bytes.fromhex(clean)
            return self.send_frame(data)
        except ValueError as e:
            self.error_occurred.emit(f"发送数据格式错误: {e}")
            return False

    def run(self):
        """后台读取循环"""
        while self._running and self._ser and self._ser.is_open:
            try:
                if self._ser.in_waiting:
                    raw = self._ser.read(self._ser.in_waiting)
                    self.raw_data_received.emit(raw)  # 发射原始数据信号
                    self._buffer.extend(raw)
                    self._process_buffer()
                else:
                    time.sleep(0.01)
            except serial.SerialException:
                break
            except Exception as e:
                self.log_message.emit(f"[串口错误] 接收循环异常: {e}")
        self._running = False
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        self.connection_changed.emit(False)

    @staticmethod
    def _fmt_frame(frame: bytes) -> str:
        """帧字节 → 空格分隔大写十六进制"""
        hex_str = frame.hex().upper()
        return " ".join(hex_str[i:i + 2] for i in range(0, len(hex_str), 2))

    def _process_buffer(self):
        """从缓冲区提取完整帧，支持两种 68H 起始格式：

        - **DL/T645-2007/1997**（协议6）：``68H + 地址(6B) + 68H + C(1B) + L(1B)
          + 数据(L B) + CS(1B) + 16H``，总长 = ``12 + L``（与 ``dlt645_parser``
          同一公式）；现场帧常带 4 字节 ``FEH`` 唤醒前导，由 ``find`` 自然跳过。
        - **FT1.2**（IEC 62056-21 / 南网等）：``68H + 长度(2B 小端) + … + 16H``。

        判别依据：首个 68H 之后**偏移 +7** 处是否也是 68H（地址占 6 字节，
        第 2 个起始符落在 index 7；与 ``dlt645_parser`` 的 ``data[7] != 0x68`` 同口径）。
        **必须先判 DL/T645**：FT1.2 把 68H 后 2 字节当长度域，而 DL/T645 那里是
        地址低字节——`68 01 00 …` 会被算成长度 1（<8）而整帧丢弃，表现为
        「串口只有发送没有接收」（用户报障，协议6）。
        """
        buf = self._buffer
        i = 0
        while i < len(buf):
            pos = buf.find(b'\x68', i)
            if pos == -1:
                break
            # ── DL/T645：双 68H 起始符（地址 6 字节 → 第 2 个 68H 在 +7）──
            if pos + 7 < len(buf) and buf[pos + 7] == 0x68:
                if pos + 10 > len(buf):
                    break                       # 帧头未收齐，等下一批
                total = 12 + buf[pos + 9]       # 68+地址6+68+C+L+数据L+CS+16
                if pos + total > len(buf):
                    break                       # 帧体未收齐
                if buf[pos + total - 1] == 0x16:
                    frame = bytes(buf[pos:pos + total])
                    self.frame_received.emit(frame)
                    self.log_message.emit(f"[接收] {self._fmt_frame(frame)}")
                    del buf[:pos + total]
                    i = 0
                    continue
                i = pos + 1
                continue
            # ── FT1.2 ──
            if pos + 6 > len(buf):
                break
            # 解析长度域（小端）
            length = buf[pos + 1] | (buf[pos + 2] << 8)
            if length < 8 or length > 2048:
                i = pos + 1
                continue
            end_pos = pos + length
            if end_pos > len(buf):
                break
            # 验证结束符
            if buf[end_pos - 1] == 0x16:
                frame = bytes(buf[pos:end_pos])
                self.frame_received.emit(frame)
                self.log_message.emit(f"[接收] {self._fmt_frame(frame)}")
                del buf[:end_pos]
                i = 0
                continue
            # 长度域对应的结束符不是 0x16，尝试查找下一个 0x16 作为备选边界
            alt_end = buf.find(b'\x16', pos + 3)
            if alt_end != -1 and 7 <= alt_end - pos <= 2048:
                frame = bytes(buf[pos:alt_end + 1])
                self.frame_received.emit(frame)
                self.log_message.emit(f"[接收(容错)] {self._fmt_frame(frame)}")
                del buf[:alt_end + 1]
                i = 0
                continue
            i = pos + 1
        # 如果缓冲区太大且没有有效帧头，清理旧数据
        if len(buf) > 4096:
            # 保留最后 1024 字节
            self._buffer = bytearray(buf[-1024:])

    @staticmethod
    def list_ports() -> list:
        """列出可用串口"""
        return [p.device for p in serial.tools.list_ports.comports()]
