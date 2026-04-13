import ctypes
from dataclasses import dataclass

class ControlField(ctypes.BigEndianStructure):
    _fields_ = [
        ("dir", ctypes.c_uint8, 1),   # 传输方向(D7)
        ("prm", ctypes.c_uint8, 1),   # 启动标志(D6)
        ("add", ctypes.c_uint8, 1),   # 地址域标识(D5)
        ("ver", ctypes.c_uint8, 2),   # 协议版本(D4~D3)
        ("reserved", ctypes.c_uint8, 3) # 保留(D2~D0)
    ]
    def __init__(self, dir=0, prm=0, add=0, ver=0, reserved=0) -> None:
        '''
        :param dir: 传输方向(D7)
        :param prm: 启动标志(D6)
        :param add: 地址域标识(D5)
        :param ver: 协议版本(D4~D3)
        :param reserved: 保留(D2~D0)
        '''
        self.dir = dir
        self.prm = prm
        self.add = add
        self.ver = ver
        self.reserved = reserved

@dataclass
class Frame:
    start_char: int = 0x68
    length: int = 0
    control: ControlField = ControlField()
    address: bytes = b''
    afn: int = 0
    seq: int = 0
    di: int = 0
    data: bytes = b''
    cs: int = 0
    end_char: int = 0x16
    def __init__(self, control: ControlField = ControlField(), src_addr: bytes = b'', dst_addr: bytes = b'', afn: int = 0, seq: int = 0, di: int = 0, data: bytes = b''):
        self.control = control
        self.address = src_addr[::-1] + dst_addr[::-1]  # 地址域=源地址反转+目的地址反转
        self.afn = afn
        self.seq = seq
        self.di = di.to_bytes(4, 'little')  # DI为4字节，小端序
        self.data = data

    def calculate_checksum(self, data: bytes) -> int:
        """计算校验和 - 八位位组算术和"""
        return sum(data) & 0xFF
    def frame_pack(self) -> bytes:
        """组帧功能实现"""
        # 构建用户数据区
        user_data = bytearray()
        if self.control.add:
            user_data.extend(self.address)
        user_data.append(self.afn)
        user_data.append(self.seq)
        user_data.extend(self.di) # DI为4字节，大端序
        user_data.extend(self.data)

        # 计算长度
        self.length = len(user_data) + 6  # +6字节固定长度

        # 构建完整帧
        packed_frame = bytearray()
        packed_frame.append(self.start_char)
        packed_frame.extend(self.length.to_bytes(2, 'little'))  # 长度L为2字节，小端序
        # 提取ControlField结构的字节值
        control_byte = ctypes.cast(ctypes.addressof(self.control), ctypes.POINTER(ctypes.c_uint8)).contents.value
        packed_frame.append(control_byte)
        packed_frame.extend(user_data)

        # 计算校验和
        self.cs = self.calculate_checksum(packed_frame[3:])  # 从长度字段开始计算
        packed_frame.append(self.cs)
        packed_frame.append(self.end_char)
        return bytes(packed_frame)