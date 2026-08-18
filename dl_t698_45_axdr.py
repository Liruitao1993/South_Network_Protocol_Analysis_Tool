"""DL/T 790.6-2010 A-XDR 编解码器

698.45 协议中 APDU 使用 A-XDR 编码规则。
"""

import struct
from typing import Any, Dict, List, Tuple, Optional


# A-XDR 应用类 Tag (高3位=010)
AXDR_TAG = {
    0x00: "null",
    0x01: "array",
    0x02: "structure",
    0x03: "bool",
    0x04: "bit-string",
    0x05: "double-long",
    0x06: "double-long-unsigned",
    0x09: "octet-string",
    0x0A: "visible-string",
    0x0C: "UTF8-string",
    0x0F: "integer",
    0x10: "long",
    0x11: "unsigned",
    0x12: "long-unsigned",
    0x14: "long64",
    0x15: "long64-unsigned",
    0x16: "enum",
    0x17: "float32",
    0x18: "float64",
    0x19: "date_time",
    0x1A: "date",
    0x1B: "time",
    0x1C: "date_time_s",
    0x50: "OI",
    0x51: "OAD",
    0x52: "ROAD",
    0x53: "OMD",
    0x54: "TI",
    0x55: "TSA",
    0x56: "MAC",
    0x57: "RN",
    0x58: "Region",
    0x59: "RSD",
    0x5A: "CSD",
    0x5B: "MS",
    0x5C: "SID",
    0x5D: "SID_MAC",
    0x5E: "Scaler_Unit",
    0x5F: "RCS",
}

TAG_TYPE = {v: k for k, v in AXDR_TAG.items()}


def get_tag_name(tag: int) -> str:
    return AXDR_TAG.get(tag, f"未知类型(0x{tag:02X})")


class AXDRCoder:
    """A-XDR 编解码器"""

    def decode(self, data: bytes, offset: int = 0) -> Tuple[dict, int]:
        """解码一个 A-XDR 数据项

        Returns: (解码结果, 消耗字节数)
        """
        if offset >= len(data):
            raise ValueError(f"偏移量越界: {offset} >= {len(data)}")

        tag = data[offset]
        tag_name = get_tag_name(tag)
        decoder = getattr(self, f'_decode_{tag_name.replace("-", "_")}', None)

        if decoder is None:
            raise NotImplementedError(f"类型 '{tag_name}' 的解码器尚未实现")

        result, consumed = decoder(data, offset)
        result["tag"] = tag
        result["tag_name"] = tag_name
        # 完整 A-XDR 编码字节（含类型 tag + 长度头），便于展示 09 08 等头字节去向
        result["原始编码"] = data[offset:offset + consumed].hex().upper()
        return result, consumed

    def _decode_length(self, data: bytes, offset: int) -> Tuple[int, int]:
        """BER 长度解码

        Returns: (长度值, 消耗字节数)
        """
        if offset >= len(data):
            raise ValueError("长度数据不足")
        first = data[offset]
        if first & 0x80 == 0:
            return first, 1
        num_bytes = first & 0x7F
        if num_bytes == 0:
            raise ValueError("不定长编码不支持")
        if offset + 1 + num_bytes > len(data):
            raise ValueError("长度数据不足")
        length = int.from_bytes(data[offset + 1:offset + 1 + num_bytes], 'big')
        return length, 1 + num_bytes

    # --- 基础类型解码器 ---

    def _decode_null(self, data: bytes, offset: int) -> Tuple[dict, int]:
        return {"类型": "null", "原始值": "", "解析值": None, "说明": "空值"}, 1

    def _decode_bool(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 1 >= len(data):
            raise ValueError("bool 数据不足")
        val = data[offset + 1] != 0
        return {"类型": "bool", "原始值": f"0x{data[offset + 1]:02X}",
                "解析值": val, "说明": "布尔值"}, 2

    def _decode_integer(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 1 >= len(data):
            raise ValueError("integer 数据不足")
        val = int.from_bytes(data[offset + 1:offset + 2], 'little', signed=True)
        return {"类型": "integer", "原始值": data[offset + 1:offset + 2].hex().upper(),
                "解析值": val, "说明": "1字节有符号整数"}, 2

    def _decode_unsigned(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 1 >= len(data):
            raise ValueError("unsigned 数据不足")
        val = data[offset + 1]
        return {"类型": "unsigned", "原始值": f"0x{val:02X}",
                "解析值": val, "说明": "1字节无符号整数"}, 2

    def _decode_long(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 2 >= len(data):
            raise ValueError("long 数据不足")
        val = int.from_bytes(data[offset + 1:offset + 3], 'little', signed=True)
        return {"类型": "long", "原始值": data[offset + 1:offset + 3].hex().upper(),
                "解析值": val, "说明": "2字节有符号整数(小端)"}, 3

    def _decode_long_unsigned(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 2 >= len(data):
            raise ValueError("long-unsigned 数据不足")
        val = int.from_bytes(data[offset + 1:offset + 3], 'little')
        return {"类型": "long-unsigned", "原始值": data[offset + 1:offset + 3].hex().upper(),
                "解析值": val, "说明": "2字节无符号整数(小端)"}, 3

    def _decode_double_long(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 4 >= len(data):
            raise ValueError("double-long 数据不足")
        val = int.from_bytes(data[offset + 1:offset + 5], 'little', signed=True)
        return {"类型": "double-long", "原始值": data[offset + 1:offset + 5].hex().upper(),
                "解析值": val, "说明": "4字节有符号整数(小端)"}, 5

    def _decode_double_long_unsigned(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 4 >= len(data):
            raise ValueError("double-long-unsigned 数据不足")
        val = int.from_bytes(data[offset + 1:offset + 5], 'little')
        return {"类型": "double-long-unsigned", "原始值": data[offset + 1:offset + 5].hex().upper(),
                "解析值": val, "说明": "4字节无符号整数(小端)"}, 5

    def _decode_long64(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 8 >= len(data):
            raise ValueError("long64 数据不足")
        val = int.from_bytes(data[offset + 1:offset + 9], 'little', signed=True)
        return {"类型": "long64", "原始值": data[offset + 1:offset + 9].hex().upper(),
                "解析值": val, "说明": "8字节有符号整数(小端)"}, 9

    def _decode_long64_unsigned(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 8 >= len(data):
            raise ValueError("long64-unsigned 数据不足")
        val = int.from_bytes(data[offset + 1:offset + 9], 'little')
        return {"类型": "long64-unsigned", "原始值": data[offset + 1:offset + 9].hex().upper(),
                "解析值": val, "说明": "8字节无符号整数(小端)"}, 9

    def _decode_enum(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 1 >= len(data):
            raise ValueError("enum 数据不足")
        val = data[offset + 1]
        return {"类型": "enum", "原始值": f"0x{val:02X}",
                "解析值": val, "说明": "枚举值"}, 2

    def _decode_float32(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 4 >= len(data):
            raise ValueError("float32 数据不足")
        val = struct.unpack('<f', data[offset + 1:offset + 5])[0]
        return {"类型": "float32", "原始值": data[offset + 1:offset + 5].hex().upper(),
                "解析值": val, "说明": "IEEE 754 单精度浮点"}, 5

    def _decode_float64(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 8 >= len(data):
            raise ValueError("float64 数据不足")
        val = struct.unpack('<d', data[offset + 1:offset + 9])[0]
        return {"类型": "float64", "原始值": data[offset + 1:offset + 9].hex().upper(),
                "解析值": val, "说明": "IEEE 754 双精度浮点"}, 9

    # --- 字符串类型 ---

    def _decode_octet_string(self, data: bytes, offset: int) -> Tuple[dict, int]:
        length, llen = self._decode_length(data, offset + 1)
        if offset + 1 + llen + length > len(data):
            raise ValueError("octet-string 数据不足")
        val = data[offset + 1 + llen:offset + 1 + llen + length]
        return {"类型": "octet-string", "原始值": val.hex().upper(),
                "解析值": val.hex().upper(), "说明": f"{length}字节"}, 1 + llen + length

    def _decode_visible_string(self, data: bytes, offset: int) -> Tuple[dict, int]:
        length, llen = self._decode_length(data, offset + 1)
        if offset + 1 + llen + length > len(data):
            raise ValueError("visible-string 数据不足")
        val = data[offset + 1 + llen:offset + 1 + llen + length]
        try:
            s = val.decode('ascii')
        except:
            s = val.hex().upper()
        return {"类型": "visible-string", "原始值": val.hex().upper(),
                "解析值": s, "说明": f"{length}字节ASCII"}, 1 + llen + length

    def _decode_UTF8_string(self, data: bytes, offset: int) -> Tuple[dict, int]:
        length, llen = self._decode_length(data, offset + 1)
        if offset + 1 + llen + length > len(data):
            raise ValueError("UTF8-string 数据不足")
        val = data[offset + 1 + llen:offset + 1 + llen + length]
        try:
            s = val.decode('utf-8')
        except:
            s = val.hex().upper()
        return {"类型": "UTF8-string", "原始值": val.hex().upper(),
                "解析值": s, "说明": f"{length}字节UTF-8"}, 1 + llen + length

    def _decode_bit_string(self, data: bytes, offset: int) -> Tuple[dict, int]:
        length, llen = self._decode_length(data, offset + 1)
        if offset + 1 + llen + length > len(data):
            raise ValueError("bit-string 数据不足")
        val = data[offset + 1 + llen:offset + 1 + llen + length]
        return {"类型": "bit-string", "原始值": val.hex().upper(),
                "解析值": val.hex().upper(), "说明": f"{length}字节"}, 1 + llen + length

    # --- 复合类型 ---

    def _decode_array(self, data: bytes, offset: int) -> Tuple[dict, int]:
        length, llen = self._decode_length(data, offset + 1)
        items = []
        pos = offset + 1 + llen
        end = pos + length
        while pos < end:
            item, consumed = self.decode(data, pos)
            items.append(item)
            pos += consumed
        return {"类型": "array", "原始值": data[offset:pos].hex().upper(),
                "解析值": items, "说明": f"{len(items)}个元素"}, pos - offset

    def _decode_structure(self, data: bytes, offset: int) -> Tuple[dict, int]:
        length, llen = self._decode_length(data, offset + 1)
        items = []
        pos = offset + 1 + llen
        end = pos + length
        while pos < end:
            item, consumed = self.decode(data, pos)
            items.append(item)
            pos += consumed
        return {"类型": "structure", "原始值": data[offset:pos].hex().upper(),
                "解析值": items, "说明": f"{len(items)}个成员"}, pos - offset

    # --- 时间类型 ---

    def _decode_date_time(self, data: bytes, offset: int) -> Tuple[dict, int]:
        """date_time: 10字节"""
        if offset + 10 >= len(data):
            raise ValueError("date_time 数据不足")
        val = data[offset + 1:offset + 11]
        year = int.from_bytes(val[0:2], 'little')
        month = val[2]
        day = val[3]
        week = val[4]
        hour = val[5]
        minute = val[6]
        second = val[7]
        ms = val[8] | (val[9] << 8)
        week_map = {0: "星期日", 1: "星期一", 2: "星期二", 3: "星期三",
                    4: "星期四", 5: "星期五", 6: "星期六", 0xFF: "无效"}
        dt_str = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}.{ms:03d}"
        return {"类型": "date_time", "原始值": val.hex().upper(),
                "解析值": dt_str,
                "说明": f"年={year}, 月={month}, 日={day}, 星期={week_map.get(week, week)}, 时={hour}, 分={minute}, 秒={second}, 毫秒={ms}"}, 11

    def _decode_date(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 5 >= len(data):
            raise ValueError("date 数据不足")
        val = data[offset + 1:offset + 6]
        year = int.from_bytes(val[0:2], 'little')
        month = val[2]
        day = val[3]
        week = val[4]
        week_map = {0: "星期日", 1: "星期一", 2: "星期二", 3: "星期三",
                    4: "星期四", 5: "星期五", 6: "星期六", 0xFF: "无效"}
        return {"类型": "date", "原始值": val.hex().upper(),
                "解析值": f"{year}-{month:02d}-{day:02d}",
                "说明": f"年={year}, 月={month}, 日={day}, 星期={week_map.get(week, week)}"}, 6

    def _decode_time(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 4 >= len(data):
            raise ValueError("time 数据不足")
        val = data[offset + 1:offset + 5]
        hour = val[0]
        minute = val[1]
        second = val[2]
        return {"类型": "time", "原始值": val.hex().upper(),
                "解析值": f"{hour:02d}:{minute:02d}:{second:02d}",
                "说明": f"时={hour}, 分={minute}, 秒={second}"}, 5

    def _decode_date_time_s(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 7 >= len(data):
            raise ValueError("date_time_s 数据不足")
        val = data[offset + 1:offset + 8]
        # 年 2 字节大端（文档 H.1 例: 07 E0 = 2016）
        year = int.from_bytes(val[0:2], 'big')
        month = val[2]
        day = val[3]
        hour = val[4]
        minute = val[5]
        second = val[6]
        return {"类型": "date_time_s", "原始值": val.hex().upper(),
                "解析值": f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}",
                "说明": f"年={year}, 月={month}, 日={day}, 时={hour}, 分={minute}, 秒={second}"}, 8

    # --- 698.45 扩展类型 ---

    def _decode_OI(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 2 >= len(data):
            raise ValueError("OI 数据不足")
        val = int.from_bytes(data[offset + 1:offset + 3], 'little')
        return {"类型": "OI", "原始值": data[offset + 1:offset + 3].hex().upper(),
                "解析值": f"0x{val:04X}", "说明": f"对象标识={val}"}, 3

    def _decode_OAD(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 4 >= len(data):
            raise ValueError("OAD 数据不足")
        val = data[offset + 1:offset + 5]
        oi = int.from_bytes(val[0:2], 'little')
        attr = val[2]
        attr_no = attr & 0x1F
        attr_feat = (attr >> 5) & 0x07
        index = val[3]
        index_desc = "全部内容" if index == 0 else f"第{index}个元素"
        return {"类型": "OAD", "原始值": val.hex().upper(),
                "解析值": {"OI": f"0x{oi:04X}", "属性编号": attr_no, "属性特征": attr_feat, "元素索引": index},
                "说明": f"OI=0x{oi:04X}, 属性={attr_no}, 特征={attr_feat}, 索引={index_desc}"}, 5

    def _decode_OMD(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 4 >= len(data):
            raise ValueError("OMD 数据不足")
        val = data[offset + 1:offset + 5]
        oi = int.from_bytes(val[0:2], 'little')
        method = val[2]
        mode = val[3]
        return {"类型": "OMD", "原始值": val.hex().upper(),
                "解析值": {"OI": f"0x{oi:04X}", "方法标识": method, "操作模式": mode},
                "说明": f"OI=0x{oi:04X}, 方法={method}, 模式={mode}"}, 5

    def _decode_TI(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 3 >= len(data):
            raise ValueError("TI 数据不足")
        val = data[offset + 1:offset + 4]
        unit = val[0]
        interval = int.from_bytes(val[1:3], 'little')
        unit_map = {0: "秒", 1: "分", 2: "时", 3: "日", 4: "月", 5: "年"}
        return {"类型": "TI", "原始值": val.hex().upper(),
                "解析值": {"单位": unit_map.get(unit, f"未知({unit})"), "间隔值": interval},
                "说明": f"间隔={interval} {unit_map.get(unit, '')}"}, 4

    def _decode_TSA(self, data: bytes, offset: int) -> Tuple[dict, int]:
        length, llen = self._decode_length(data, offset + 1)
        if offset + 1 + llen + length > len(data):
            raise ValueError("TSA 数据不足")
        val = data[offset + 1 + llen:offset + 1 + llen + length]
        return {"类型": "TSA", "原始值": val.hex().upper(),
                "解析值": val.hex().upper(), "说明": f"目标服务器地址({length}字节)"}, 1 + llen + length

    def _decode_MAC(self, data: bytes, offset: int) -> Tuple[dict, int]:
        length, llen = self._decode_length(data, offset + 1)
        if offset + 1 + llen + length > len(data):
            raise ValueError("MAC 数据不足")
        val = data[offset + 1 + llen:offset + 1 + llen + length]
        return {"类型": "MAC", "原始值": val.hex().upper(),
                "解析值": val.hex().upper(), "说明": f"MAC({length}字节)"}, 1 + llen + length

    def _decode_RN(self, data: bytes, offset: int) -> Tuple[dict, int]:
        length, llen = self._decode_length(data, offset + 1)
        if offset + 1 + llen + length > len(data):
            raise ValueError("RN 数据不足")
        val = data[offset + 1 + llen:offset + 1 + llen + length]
        return {"类型": "RN", "原始值": val.hex().upper(),
                "解析值": val.hex().upper(), "说明": f"随机数({length}字节)"}, 1 + llen + length

    def _decode_Scaler_Unit(self, data: bytes, offset: int) -> Tuple[dict, int]:
        if offset + 4 >= len(data):
            raise ValueError("Scaler_Unit 数据不足")
        val = data[offset + 1:offset + 5]
        scaler = int.from_bytes(val[0:1], 'little', signed=True)
        unit = val[1]
        return {"类型": "Scaler_Unit", "原始值": val.hex().upper(),
                "解析值": {"换算": scaler, "单位": unit},
                "说明": f"10^{scaler}, 单位={unit}"}, 5

    # --- 编码方法 ---

    def encode(self, value: Any, tag: int) -> bytes:
        """将 Python 值编码为 A-XDR 字节"""
        tag_name = get_tag_name(tag)
        encoder = getattr(self, f'_encode_{tag_name.replace("-", "_")}', None)
        if encoder is None:
            raise NotImplementedError(f"类型 '{tag_name}' 的编码器尚未实现")
        return bytes([tag]) + encoder(value)

    def _encode_null(self, value):
        return b''

    def _encode_integer(self, value: int) -> bytes:
        return struct.pack('<b', value)

    def _encode_unsigned(self, value: int) -> bytes:
        return struct.pack('<B', value)

    def _encode_long(self, value: int) -> bytes:
        return struct.pack('<h', value)

    def _encode_long_unsigned(self, value: int) -> bytes:
        return struct.pack('<H', value)

    def _encode_double_long(self, value: int) -> bytes:
        return struct.pack('<i', value)

    def _encode_double_long_unsigned(self, value: int) -> bytes:
        return struct.pack('<I', value)

    def _encode_long64(self, value: int) -> bytes:
        return struct.pack('<q', value)

    def _encode_long64_unsigned(self, value: int) -> bytes:
        return struct.pack('<Q', value)

    def _encode_enum(self, value: int) -> bytes:
        return struct.pack('<B', value)

    def _encode_float32(self, value: float) -> bytes:
        return struct.pack('<f', value)

    def _encode_float64(self, value: float) -> bytes:
        return struct.pack('<d', value)

    def _encode_octet_string(self, value: bytes) -> bytes:
        length = len(value)
        if length < 128:
            return bytes([length]) + value
        else:
            length_bytes = length.to_bytes((length.bit_length() + 7) // 8, 'big')
            return bytes([0x80 | len(length_bytes)]) + length_bytes + value

    def _encode_OI(self, value: int) -> bytes:
        return struct.pack('<H', value)

    def _encode_OAD(self, value: dict) -> bytes:
        oi = value.get("OI", 0)
        if isinstance(oi, str) and oi.startswith("0x"):
            oi = int(oi, 16)
        attr = value.get("属性编号", 0) | (value.get("属性特征", 0) << 5)
        index = value.get("元素索引", 0)
        return struct.pack('<HBB', oi, attr, index)

    def _encode_OMD(self, value: dict) -> bytes:
        oi = value.get("OI", 0)
        if isinstance(oi, str) and oi.startswith("0x"):
            oi = int(oi, 16)
        method = value.get("方法标识", 0)
        mode = value.get("操作模式", 0)
        return struct.pack('<HBB', oi, method, mode)

    def _encode_bool(self, value) -> bytes:
        return struct.pack('<B', 1 if value else 0)

    def _encode_bit_string(self, value: bytes) -> bytes:
        length = len(value)
        return self._encode_length(length) + value

    def _encode_visible_string(self, value: str) -> bytes:
        data = value.encode('ascii', errors='replace')
        length = len(data)
        return self._encode_length(length) + data

    def _encode_UTF8_string(self, value: str) -> bytes:
        data = value.encode('utf-8')
        length = len(data)
        return self._encode_length(length) + data

    def _encode_date_time(self, value) -> bytes:
        """date_time: octet-string SIZE(10)"""
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_date(self, value) -> bytes:
        """date: octet-string SIZE(5)"""
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_time(self, value) -> bytes:
        """time: octet-string SIZE(3)"""
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_date_time_s(self, value) -> bytes:
        """date_time_s: octet-string SIZE(7)"""
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_TI(self, value) -> bytes:
        """TI: octet-string SIZE(6)"""
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_TSA(self, value) -> bytes:
        """TSA: octet-string SIZE(7)"""
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_MAC(self, value) -> bytes:
        """MAC: octet-string SIZE(4/8/16)"""
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_RN(self, value) -> bytes:
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_Region(self, value) -> bytes:
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_Scaler_Unit(self, value) -> bytes:
        return self._encode_octet_string(value if isinstance(value, bytes) else bytes.fromhex(str(value).replace(' ', '')))

    def _encode_array(self, value: list) -> bytes:
        """编码数组: [count] [element1] [element2]..."""
        count = len(value)
        result = self._encode_length(count)
        for elem in value:
            tag = elem.get("tag", 0x11)  # default unsigned
            result += self.encode(elem.get("value", 0), tag)
        return result

    def _encode_structure(self, value: list) -> bytes:
        """编码结构体: [count] [element1]... 同 array"""
        return self._encode_array(value)

    @staticmethod
    def _encode_length(length: int) -> bytes:
        """BER 长度编码"""
        if length < 128:
            return bytes([length])
        length_bytes = length.to_bytes((length.bit_length() + 7) // 8, 'big')
        return bytes([0x80 | len(length_bytes)]) + length_bytes
