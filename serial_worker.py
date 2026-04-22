"""串口通信工作线程

基于 PySide6 QThread + pyserial，提供：
- 串口打开/关闭
- 后台读取循环
- FT1.2 帧自动识别与提取
- 发送十六进制帧
- 信号通知GUI层
"""

from typing import Optional
import serial
import serial.tools.list_ports

from PySide6.QtCore import QThread, Signal


class SerialWorker(QThread):
    """串口后台工作线程"""

    # 信号定义
    frame_received = Signal(bytes)       # 收到一帧完整数据
    log_message = Signal(str)            # 日志消息（供文本框显示）
    connection_changed = Signal(bool)    # 连接状态变化
    error_occurred = Signal(str)         # 错误信息

    def __init__(self, parent=None):
        super().__init__(parent)
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
                    self._buffer.extend(raw)
                    self._process_buffer()
            except serial.SerialException:
                break
            except Exception:
                pass
        self._running = False
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        self.connection_changed.emit(False)

    def _process_buffer(self):
        """从缓冲区提取完整 FT1.2 帧"""
        buf = self._buffer
        i = 0
        while i < len(buf) - 7:
            # 寻找 68 起始
            pos = buf.find(b'\x68', i)
            if pos == -1:
                break
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
            if buf[end_pos - 1] != 0x16:
                i = pos + 1
                continue
            # 提取帧
            frame = bytes(buf[pos:end_pos])
            self.frame_received.emit(frame)
            hex_str = frame.hex().upper()
            formatted = " ".join(hex_str[j:j+2] for j in range(0, len(hex_str), 2))
            self.log_message.emit(f"[接收] {formatted}")
            # 删除已处理数据
            del buf[:end_pos]
            i = 0
        # 如果缓冲区太大且没有有效帧头，清理旧数据
        if len(buf) > 4096:
            # 保留最后 1024 字节
            self._buffer = bytearray(buf[-1024:])

    @staticmethod
    def list_ports() -> list:
        """列出可用串口"""
        return [p.device for p in serial.tools.list_ports.comports()]
