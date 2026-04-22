import ctypes
from dataclasses import dataclass


class GDWControlField(ctypes.LittleEndianStructure):
    """国网协议控制域 C (1字节)

    位定义（从低位到高位，小端序）：
    - comm_type: D5~D0 通信方式 (6 bits)
    - prm: D6 启动标志位 (1 bit)
    - dir: D7 传输方向位 (1 bit)
    """
    _fields_ = [
        ("comm_type", ctypes.c_uint8, 6),  # D5~D0: 通信方式
        ("prm", ctypes.c_uint8, 1),        # D6: 启动标志位
        ("dir", ctypes.c_uint8, 1),        # D7: 传输方向位
    ]

    def __init__(self, comm_type=0, prm=0, dir=0) -> None:
        self.comm_type = comm_type
        self.prm = prm
        self.dir = dir

    def to_byte(self) -> int:
        """将控制域转换为单字节整数值"""
        return (self.dir << 7) | (self.prm << 6) | (self.comm_type & 0x3F)

    @classmethod
    def from_byte(cls, byte_val: int) -> "GDWControlField":
        """从单字节整数值解析控制域"""
        return cls(
            comm_type=byte_val & 0x3F,
            prm=(byte_val >> 6) & 0x01,
            dir=(byte_val >> 7) & 0x01,
        )


# 通信方式映射表
COMM_TYPE_MAP = {
    0: "保留",
    1: "集中式路由载波通信",
    2: "分布式路由载波通信",
    3: "HPLC载波通信",
    4: "双模通信(HDC)",
    5: "备用",
    6: "备用",
    7: "备用",
    8: "备用",
    9: "备用",
    10: "微功率无线通信",
    11: "备用",
    12: "备用",
    13: "备用",
    14: "备用",
    15: "备用",
    16: "备用",
    17: "备用",
    18: "备用",
    19: "备用",
    20: "以太网通信",
}

# DIR映射
DIR_MAP = {
    0: "下行报文(集中器发出)",
    1: "上行报文(通信模块发出)",
}

# PRM映射
PRM_MAP = {
    0: "来自从动站",
    1: "来自启动站",
}


@dataclass
class GDWFrame:
    """国网协议帧结构 (Q/GDW 10376.2—2024)"""
    start_char: int = 0x68
    length: int = 0
    control: GDWControlField = None
    info_domain: bytes = b''
    address: bytes = b''
    afn: int = 0
    dt: bytes = b''
    data: bytes = b''
    cs: int = 0
    end_char: int = 0x16

    def __post_init__(self):
        if self.control is None:
            self.control = GDWControlField()

    def calculate_checksum(self, data: bytes) -> int:
        """计算校验和 - 控制域和用户数据区所有字节的八位位组算术和"""
        return sum(data) & 0xFF

    def frame_pack(self) -> bytes:
        """组帧功能实现"""
        # 构建用户数据区 = 信息域 + 地址域 + 应用数据域
        user_data = bytearray()
        user_data.extend(self.info_domain)
        user_data.extend(self.address)
        user_data.append(self.afn)
        user_data.extend(self.dt)
        user_data.extend(self.data)

        # 计算长度 L = 用户数据长度 + 6 (起始字符1 + 长度2 + 控制域1 + 校验和1 + 结束字符1)
        self.length = len(user_data) + 6

        # 构建完整帧
        packed_frame = bytearray()
        packed_frame.append(self.start_char)
        packed_frame.extend(self.length.to_bytes(2, 'little'))  # 长度L为2字节，小端序
        packed_frame.append(self.control.to_byte())
        packed_frame.extend(user_data)

        # 计算校验和: 控制域 + 用户数据区
        self.cs = self.calculate_checksum(packed_frame[3:])
        packed_frame.append(self.cs)
        packed_frame.append(self.end_char)
        return bytes(packed_frame)
