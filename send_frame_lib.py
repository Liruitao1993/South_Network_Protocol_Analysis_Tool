from typing import Dict, List, Optional, Tuple
import struct
from protocol_tool import Frame, ControlField

class ProtocolFrameGenerator:
    def __init__(self):
        self.afn_handlers = {
            ("00", "00"): self.create_afn00_di00,
            ("01", "01"): self.create_afn01_di01,
            ("02", "02"): self.create_afn02_di02,
            ("03", "03"): self.create_afn03_di03,
            ("04", "04"): self.create_afn04_di04,
            ("05", "05"): self.create_afn05_di05,
            ("06", "06"): self.create_afn06_di06,
            ("07", "07"): self.create_afn07_di07,
        }

    def _build_frame(self, di3: int, di2: int, di1: int, di0: int, 
                     src_addr: bytes = b'\x00\x00\x00\x00\x00\x00',
                     dst_addr: bytes = b'\x00\x00\x00\x00\x00\x00',
                     data: bytes = b'',
                     dir_flag: int = 0, prm: int = 1, add_flag: int = 0) -> bytes:
        di = (di3 << 24) | (di2 << 16) | (di1 << 8) | di0
        control = ControlField(dir=dir_flag, prm=prm, add=add_flag, ver=0, reserved=0)
        frame = Frame(control=control, src_addr=src_addr, dst_addr=dst_addr,
                     afn=di1, seq=0, di=di, data=data)
        return frame.frame_pack()

    def create_afn00_di00(self, sub_code: int, **kwargs) -> bytes:
        if sub_code == 0x01:
            wait_time = kwargs.get('wait_time', 0)
            data = struct.pack('>H', wait_time)
            return self._build_frame(0xE8, 0x01, 0x00, 0x01, data=data, dir_flag=0, prm=0)
        elif sub_code == 0x02:
            error_code = kwargs.get('error_code', 0)
            data = struct.pack('B', error_code)
            return self._build_frame(0xE8, 0x01, 0x00, 0x02, data=data, dir_flag=0, prm=0)
        raise ValueError(f"不支持的子功能码: {sub_code}")

    def create_afn01_di01(self, sub_code: int, **kwargs) -> bytes:
        if sub_code == 0x01:
            return self._build_frame(0xE8, 0x02, 0x01, 0x01)
        elif sub_code == 0x02:
            return self._build_frame(0xE8, 0x02, 0x01, 0x02)
        elif sub_code == 0x03:
            return self._build_frame(0xE8, 0x02, 0x01, 0x03)
        raise ValueError(f"不支持的子功能码: {sub_code}")

    def create_afn02_di02(self, sub_code: int, **kwargs) -> bytes:
        if sub_code == 0x01:
            task_info = kwargs.get('task_info', b'')
            return self._build_frame(0xE8, 0x02, 0x02, 0x01, data=task_info, add_flag=1,
                                    src_addr=kwargs.get('src_addr', b'\x00'*6),
                                    dst_addr=kwargs.get('dst_addr', b'\x00'*6))
        elif sub_code == 0x02:
            task_id = kwargs.get('task_id', 0)
            data = struct.pack('>H', task_id)
            return self._build_frame(0xE8, 0x02, 0x02, 0x02, data=data)
        elif sub_code == 0x03:
            return self._build_frame(0xE8, 0x00, 0x02, 0x03)
        elif sub_code == 0x04:
            task_count = kwargs.get('task_count', 0)
            data = struct.pack('>H', task_count)
            return self._build_frame(0xE8, 0x03, 0x02, 0x04, data=data)
        elif sub_code == 0x05:
            task_id = kwargs.get('task_id', 0)
            data = struct.pack('>H', task_id)
            return self._build_frame(0xE8, 0x03, 0x02, 0x05, data=data)
        elif sub_code == 0x06:
            return self._build_frame(0xE8, 0x00, 0x02, 0x06)
        elif sub_code == 0x07:
            task_info = kwargs.get('task_info', b'')
            return self._build_frame(0xE8, 0x02, 0x02, 0x07, data=task_info)
        elif sub_code == 0x08:
            return self._build_frame(0xE8, 0x02, 0x02, 0x08)
        elif sub_code == 0x09:
            return self._build_frame(0xE8, 0x02, 0x02, 0x09)
        raise ValueError(f"不支持的子功能码: {sub_code}")

    def create_afn03_di03(self, sub_code: int, **kwargs) -> bytes:
        if sub_code == 0x01:
            return self._build_frame(0xE8, 0x00, 0x03, 0x01)
        elif sub_code == 0x02:
            return self._build_frame(0xE8, 0x00, 0x03, 0x02)
        elif sub_code == 0x03:
            return self._build_frame(0xE8, 0x00, 0x03, 0x03)
        elif sub_code == 0x04:
            dst_addr = kwargs.get('dst_addr', b'\x00'*6)
            data = dst_addr
            return self._build_frame(0xE8, 0x03, 0x03, 0x04, data=data)
        elif sub_code == 0x05:
            return self._build_frame(0xE8, 0x00, 0x03, 0x05)
        elif sub_code == 0x06:
            node_id = kwargs.get('node_id', 0)
            data = struct.pack('>H', node_id)
            return self._build_frame(0xE8, 0x03, 0x03, 0x06, data=data)
        elif sub_code == 0x07:
            return self._build_frame(0xE8, 0x00, 0x03, 0x07)
        elif sub_code == 0x08:
            node_id = kwargs.get('node_id', 0)
            data = struct.pack('>H', node_id)
            return self._build_frame(0xE8, 0x03, 0x03, 0x08, data=data)
        elif sub_code == 0x09:
            return self._build_frame(0xE8, 0x00, 0x03, 0x09)
        elif sub_code == 0x0A:
            start_index = kwargs.get('start_index', 0)
            query_count = kwargs.get('query_count', 1)
            data = struct.pack('>H', start_index) + struct.pack('B', query_count)
            return self._build_frame(0xE8, 0x03, 0x03, 0x0A, data=data)
        elif sub_code == 0x0B:
            return self._build_frame(0xE8, 0x00, 0x03, 0x0B)
        elif sub_code == 0x0C:
            node_count = kwargs.get('node_count', 1)
            node_addrs = kwargs.get('node_addrs', [])
            data = struct.pack('B', node_count)
            for addr in node_addrs:
                data += addr
            return self._build_frame(0xE8, 0x03, 0x03, 0x0C, data=data)
        elif sub_code == 0x0D:
            start_index = kwargs.get('start_index', 0)
            node_count = kwargs.get('node_count', 1)
            data = struct.pack('>H', start_index) + struct.pack('B', node_count)
            return self._build_frame(0xE8, 0x03, 0x03, 0x0D, data=data)
        elif sub_code == 0x0E:
            start_index = kwargs.get('start_index', 0)
            node_count = kwargs.get('node_count', 1)
            data = struct.pack('>H', start_index) + struct.pack('B', node_count)
            return self._build_frame(0xE8, 0x03, 0x03, 0x0E, data=data)
        elif sub_code == 0x0F:
            start_index = kwargs.get('start_index', 0)
            node_count = kwargs.get('node_count', 1)
            data = struct.pack('>H', start_index) + struct.pack('B', node_count)
            return self._build_frame(0xE8, 0x03, 0x03, 0x0F, data=data)
        raise ValueError(f"不支持的子功能码: {sub_code}")

    def create_afn04_di04(self, sub_code: int, **kwargs) -> bytes:
        if sub_code == 0x01:
            node_count = kwargs.get('node_count', 1)
            node_addrs = kwargs.get('node_addrs', [])
            data = struct.pack('B', node_count)
            for addr in node_addrs:
                data += addr
            return self._build_frame(0xE8, 0x02, 0x04, 0x01, data=data)
        elif sub_code == 0x02:
            node_count = kwargs.get('node_count', 1)
            node_addrs = kwargs.get('node_addrs', [])
            data = struct.pack('B', node_count)
            for addr in node_addrs:
                data += addr
            return self._build_frame(0xE8, 0x02, 0x04, 0x02, data=data)
        elif sub_code == 0x03:
            node_id = kwargs.get('node_id', 0)
            data = struct.pack('>H', node_id)
            return self._build_frame(0xE8, 0x02, 0x04, 0x03, data=data)
        elif sub_code == 0x04:
            control_data = kwargs.get('control_data', b'')
            return self._build_frame(0xE8, 0x02, 0x04, 0x04, data=control_data)
        elif sub_code == 0x05:
            node_count = kwargs.get('node_count', 1)
            node_addrs = kwargs.get('node_addrs', [])
            data = struct.pack('B', node_count)
            for addr in node_addrs:
                data += addr
            return self._build_frame(0xE8, 0x02, 0x04, 0x05, data=data)
        elif sub_code == 0x06:
            node_count = kwargs.get('node_count', 1)
            node_addrs = kwargs.get('node_addrs', [])
            data = struct.pack('B', node_count)
            for addr in node_addrs:
                data += addr
            return self._build_frame(0xE8, 0x02, 0x04, 0x06, data=data)
        raise ValueError(f"不支持的子功能码: {sub_code}")

    def create_afn05_di05(self, sub_code: int, **kwargs) -> bytes:
        if sub_code == 0x01:
            task_data = kwargs.get('task_data', b'')
            return self._build_frame(0xE8, 0x05, 0x05, 0x01, data=task_data, dir_flag=0, prm=0)
        elif sub_code == 0x02:
            event_data = kwargs.get('event_data', b'')
            return self._build_frame(0xE8, 0x05, 0x05, 0x02, data=event_data, dir_flag=0, prm=0)
        raise ValueError(f"不支持的子功能码: {sub_code}")

    def create_afn06_di06(self, sub_code: int, **kwargs) -> bytes:
        if sub_code == 0x01:
            return self._build_frame(0xE8, 0x06, 0x06, 0x01, dir_flag=0, prm=0)
        raise ValueError(f"不支持的子功能码: {sub_code}")

    def create_afn07_di07(self, sub_code: int, **kwargs) -> bytes:
        if sub_code == 0x01:
            file_type = kwargs.get('file_type', 0)
            file_id = kwargs.get('file_id', 0)
            dst_addr = kwargs.get('dst_addr', b'\x99\x99\x99\x99\x99\x99')
            total_segments = kwargs.get('total_segments', 0)
            file_size = kwargs.get('file_size', 0)
            file_checksum = kwargs.get('file_checksum', 0)
            timeout = kwargs.get('timeout', 0)
            data = struct.pack('B', file_type)
            data += struct.pack('B', file_id)
            data += dst_addr
            data += struct.pack('>H', total_segments)
            data += struct.pack('>I', file_size)
            data += struct.pack('>H', file_checksum)
            data += struct.pack('B', timeout)
            return self._build_frame(0xE8, 0x02, 0x07, 0x01, data=data)
        elif sub_code == 0x02:
            segment_no = kwargs.get('segment_no', 0)
            segment_len = kwargs.get('segment_len', 0)
            segment_data = kwargs.get('segment_data', b'')
            segment_checksum = kwargs.get('segment_checksum', 0)
            data = struct.pack('>H', segment_no)
            data += struct.pack('>H', segment_len)
            data += segment_data
            data += struct.pack('>H', segment_checksum)
            return self._build_frame(0xE8, 0x02, 0x07, 0x02, data=data)
        elif sub_code == 0x03:
            return self._build_frame(0xE8, 0x00, 0x07, 0x03)
        elif sub_code == 0x04:
            return self._build_frame(0xE8, 0x00, 0x07, 0x04)
        elif sub_code == 0x05:
            start_index = kwargs.get('start_index', 0)
            query_count = kwargs.get('query_count', 1)
            data = struct.pack('>H', start_index) + struct.pack('B', query_count)
            return self._build_frame(0xE8, 0x03, 0x07, 0x05, data=data)
        raise ValueError(f"不支持的子功能码: {sub_code}")

    def create_frame(self, afn: str, di: str, sub_code: int, **kwargs) -> bytes:
        handler = self.afn_handlers.get((afn, di))
        if handler:
            return handler(sub_code, **kwargs)
        raise ValueError(f"不支持的AFN和DI组合: AFN={afn}, DI={di}")

if __name__ == "__main__":
    generator = ProtocolFrameGenerator()
    frame = generator.create_frame("00", "00", 0x01, wait_time=5)
    print(f"确认帧: {frame.hex()}")
    
    frame = generator.create_frame("01", "01", 0x01)
    print(f"复位硬件帧: {frame.hex()}")
    
    frame = generator.create_frame("03", "03", 0x01)
    print(f"查询厂商代码帧: {frame.hex()}")
