from typing import Dict, List, Optional, Tuple, Any
import struct
from protocol_tool import Frame, ControlField
from frame_generator_schema import DI_FIELD_SCHEMA

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

    # ==================== 通用组帧引擎（基于DI_FIELD_SCHEMA） ====================

    def get_supported_di_keys(self) -> List[Tuple[int, int, int, int]]:
        """返回当前支持的DI键列表（来自DI_FIELD_SCHEMA）"""
        return list(DI_FIELD_SCHEMA.keys())

    def get_di_schema(self, di_key: Tuple[int, int, int, int]) -> Optional[Dict[str, Any]]:
        """获取指定DI的字段Schema"""
        return DI_FIELD_SCHEMA.get(di_key)

    def generate_data(self, di_key: Tuple[int, int, int, int], field_values: Dict[str, Any]) -> bytes:
        """根据DI字段Schema和字段值生成用户数据区字节流

        Args:
            di_key: DI四元组 (di3, di2, di1, di0)
            field_values: 字段名 -> 值的字典

        Returns:
            打包后的用户数据区字节
        """
        schema = DI_FIELD_SCHEMA.get(di_key)
        if not schema:
            raise ValueError(f"不支持的DI组合: {di_key}")

        fields = schema["fields"]
        values: Dict[str, Any] = {}

        # 第一遍：收集所有字段值（含默认值）
        for field in fields:
            name = field["name"]
            val = field_values.get(name, field.get("default"))
            if val is None:
                if field.get("required", False):
                    raise ValueError(f"缺少必填字段: {name}")
                continue
            values[name] = val

        # 第二遍：处理 count_field 引用（列表字段需自动计算数量并回填）
        for field in fields:
            name = field["name"]
            if field.get("type") == "list" and "count_field" in field:
                ref_name = field["count_field"]
                items = values.get(name, [])
                values[ref_name] = len(items) if isinstance(items, list) else 0

        # 第三遍：处理 length_field 引用（变长字段需提前计算长度并回填）
        for field in fields:
            name = field["name"]
            if "length_field" in field:
                ref_name = field["length_field"]
                val = values.get(name)
                if val is not None:
                    raw_len = len(self._to_raw_bytes(field, val))
                    values[ref_name] = raw_len

        # 第四遍：按顺序打包所有字段
        result = b""
        for field in fields:
            name = field["name"]
            val = values.get(name)
            if val is None and field.get("optional", False):
                continue
            result += self._pack_field(field, val)

        return result

    def generate_frame(self, di_key: Tuple[int, int, int, int], field_values: Dict[str, Any],
                       src_addr: bytes = b'\x00' * 6,
                       dst_addr: bytes = b'\x00' * 6,
                       dir_flag: int = 0, prm: int = 1, add_flag: int = 0) -> bytes:
        """通用组帧入口：根据DI键和字段值生成完整协议帧

        Args:
            di_key: DI四元组
            field_values: 字段值字典
            src_addr: 源地址（6字节），低字节在前存储时会自动反转
            dst_addr: 目的地址（6字节），低字节在前存储时会自动反转
            dir_flag: 传输方向（0=下行，1=上行）
            prm: 启动标志（0=从动站，1=启动站）
            add_flag: 地址域标识（0=不带地址，1=带地址）

        Returns:
            完整协议帧字节流
        """
        data = self.generate_data(di_key, field_values)
        di3, di2, di1, di0 = di_key
        return self._build_frame(di3, di2, di1, di0,
                                 src_addr=src_addr, dst_addr=dst_addr, data=data,
                                 dir_flag=dir_flag, prm=prm, add_flag=add_flag)

    # ------------------- 内部打包工具方法 -------------------

    def _pack_field(self, field: Dict[str, Any], value: Any) -> bytes:
        """根据字段Schema将单个值打包为字节"""
        if value is None:
            return b""

        ftype = field["type"]

        if ftype in ("uint8", "enum"):
            return struct.pack("B", int(value))

        elif ftype == "uint16":
            endian = field.get("endian", "big")
            fmt = ">H" if endian == "big" else "<H"
            return struct.pack(fmt, int(value))

        elif ftype == "uint32":
            endian = field.get("endian", "big")
            fmt = ">I" if endian == "big" else "<I"
            return struct.pack(fmt, int(value))

        elif ftype == "bytes":
            if isinstance(value, str):
                value = bytes.fromhex(value.replace(" ", ""))
            if field.get("reverse"):
                value = value[::-1]
            if "length" in field:
                length = field["length"]
                if len(value) < length:
                    value = value + b"\x00" * (length - len(value))
                elif len(value) > length:
                    value = value[:length]
            return value

        elif ftype == "ascii":
            data = value.encode("ascii", errors="ignore")
            length = field.get("length")
            if length:
                data = data[:length].ljust(length, b"\x00")
            return data

        elif ftype == "bcd":
            if isinstance(value, str):
                data = bytes.fromhex(value.replace(" ", ""))
            else:
                data = bytes(value)
            length = field.get("length")
            if length:
                if len(data) < length:
                    data = data + b"\x00" * (length - len(data))
                elif len(data) > length:
                    data = data[:length]
            return data

        elif ftype == "list":
            item_fields = field["item_fields"]
            items = value if isinstance(value, list) else []

            # 打包数量前缀（仅当使用 count_type 时；count_field 由外部字段负责）
            if "count_type" in field:
                count_type = field["count_type"]
                if count_type == "uint8":
                    data = struct.pack("B", len(items))
                elif count_type == "uint16":
                    data = struct.pack(">H", len(items))
                else:
                    data = b""
            else:
                data = b""

            # 打包每一项
            for item in items:
                for item_field in item_fields:
                    item_name = item_field["name"]
                    item_val = item.get(item_name, item_field.get("default"))
                    data += self._pack_field(item_field, item_val)
            return data

        else:
            raise ValueError(f"不支持的字段类型: {ftype}")

    def _to_raw_bytes(self, field: Dict[str, Any], value: Any) -> bytes:
        """将值转换为原始字节（不计算固定长度填充），用于length_field长度计算"""
        if value is None:
            return b""

        ftype = field["type"]
        if ftype == "bytes":
            if isinstance(value, str):
                value = bytes.fromhex(value.replace(" ", ""))
            if field.get("reverse"):
                value = value[::-1]
            return value

        elif ftype == "ascii":
            return value.encode("ascii", errors="ignore")

        elif ftype == "bcd":
            if isinstance(value, str):
                return bytes.fromhex(value.replace(" ", ""))
            return bytes(value)

        else:
            # 其他类型使用标准打包（uint/enum/list等长度固定或可预期）
            return self._pack_field(field, value)


if __name__ == "__main__":
    generator = ProtocolFrameGenerator()
    frame = generator.create_frame("00", "00", 0x01, wait_time=5)
    print(f"确认帧: {frame.hex()}")
    
    frame = generator.create_frame("01", "01", 0x01)
    print(f"复位硬件帧: {frame.hex()}")
    
    frame = generator.create_frame("03", "03", 0x01)
    print(f"查询厂商代码帧: {frame.hex()}")
