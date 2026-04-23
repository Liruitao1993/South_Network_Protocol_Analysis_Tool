"""国网协议帧生成器 (Q/GDW 10376.2-2024)

提供基于 AFN+Fn 的通用组帧引擎，支持：
- 信息域R（7字节）配置与组装
- 地址域A（BCD编码，条件性）组装
- 应用数据域（AFN + DT + 数据单元）组装
- 与南网组帧引擎同构的字段Schema驱动打包
"""

from typing import Dict, Any, List, Optional, Tuple
import struct
from gdw10376_tool import GDWFrame, GDWControlField
from gdw_frame_generator_schema import GDW_AFNFN_SCHEMA


class GDWFrameGenerator:
    """国网协议帧生成器"""

    def __init__(self):
        pass

    def generate_frame(self,
                       afn: int,
                       fn: int,
                       field_values: Dict[str, Any],
                       info_config: Dict[str, Any],
                       src_addr: str = "000000000000",
                       dst_addr: str = "000000000000",
                       relay_addrs: List[str] = None) -> bytes:
        """通用组帧入口

        Args:
            afn: 应用功能码 (0x00~0xFF)
            fn: 信息类标识码 (1~248)
            field_values: 数据单元字段值字典
            info_config: 信息域配置字典
                - 路由标识 (0/1)
                - 附属节点标识 (0/1)
                - 通信模块标识 (0/1)  -- 决定是否有地址域
                - 冲突检测 (0/1)
                - 中继级别 (0~15)
                - 纠错编码标识 (0~15)
                - 信道标识 (0~15)
                - 预计应答字节数 (0~255)
                - 通信速率 (0~32767)
                - 速率单位标识 (0/1)
                - 报文序列号 (0~255)
            src_addr: 源地址A1，12位十进制字符串（BCD编码）
            dst_addr: 目的地址A3，12位十进制字符串（BCD编码）
            relay_addrs: 中继地址A2列表，每项12位十进制字符串

        Returns:
            完整协议帧字节流
        """
        # 1. 构建信息域R
        info_domain = self._build_info_domain(info_config)

        # 2. 构建地址域A
        comm_module_flag = info_config.get("通信模块标识", 0)
        relay_level = info_config.get("中继级别", 0)
        address = self._build_address_domain(
            comm_module_flag, relay_level,
            src_addr, dst_addr, relay_addrs or []
        )

        # 3. 构建应用数据域
        app_data = self._build_application_data(afn, fn, field_values)

        # 4. 构建控制域
        dir_flag = info_config.get("dir", 0)
        prm = info_config.get("prm", 1)
        comm_type = info_config.get("通信方式", 0)
        control = GDWControlField(comm_type=comm_type, prm=prm, dir=dir_flag)

        # 5. 组装帧
        frame = GDWFrame(
            control=control,
            info_domain=info_domain,
            address=address,
            afn=afn,
            dt=self._fn_to_dt(fn),
            data=app_data,
        )
        return frame.frame_pack()

    def _build_info_domain(self, config: Dict[str, Any]) -> bytes:
        """组装6字节信息域R（下行报文）"""
        # 字节1: 路由标识(D0) + 附属节点标识(D1) + 通信模块标识(D2) + 冲突检测(D3) + 中继级别(D4-D7)
        byte1 = 0
        byte1 |= (config.get("路由标识", 0) & 0x01) << 0
        byte1 |= (config.get("附属节点标识", 0) & 0x01) << 1
        byte1 |= (config.get("通信模块标识", 0) & 0x01) << 2
        byte1 |= (config.get("冲突检测", 0) & 0x01) << 3
        byte1 |= (config.get("中继级别", 0) & 0x0F) << 4

        # 字节2: 纠错编码标识(D0-D3) + 信道标识(D4-D7)
        byte2 = 0
        byte2 |= (config.get("纠错编码标识", 0) & 0x0F) << 0
        byte2 |= (config.get("信道标识", 0) & 0x0F) << 4

        # 字节3: 预计应答字节数
        byte3 = config.get("预计应答字节数", 0) & 0xFF

        # 字节4-5: 速率单位标识(D15) + 通信速率(D0-D14)
        rate = config.get("通信速率", 0) & 0x7FFF
        rate_unit = config.get("速率单位标识", 0) & 0x01
        rate_bytes = (rate | (rate_unit << 15)).to_bytes(2, 'little')

        # 字节6: 报文序列号
        byte6 = config.get("报文序列号", 0) & 0xFF

        return bytes([byte1, byte2, byte3, rate_bytes[0], rate_bytes[1], byte6])

    def _build_address_domain(self,
                              comm_module_flag: int,
                              relay_level: int,
                              src_addr: str,
                              dst_addr: str,
                              relay_addrs: List[str]) -> bytes:
        """组装地址域A（BCD编码）

        通信模块标识=0时: 无地址域
        通信模块标识=1时: 源地址A1(6B) + 中继地址A2(6B×中继级别) + 目的地址A3(6B)
        """
        if comm_module_flag == 0:
            return b''

        addr = b''
        addr += self._bcd_encode(src_addr, 6)

        # 中继地址: 根据中继级别，取前relay_level个
        for i in range(relay_level):
            if i < len(relay_addrs):
                addr += self._bcd_encode(relay_addrs[i], 6)
            else:
                addr += b'\x00' * 6  # 不足补零

        addr += self._bcd_encode(dst_addr, 6)
        return addr

    @staticmethod
    def _bcd_encode(addr_str: str, length: int) -> bytes:
        """将十进制地址字符串编码为BCD字节

        Args:
            addr_str: 如 "123456789012"
            length: 目标字节数
        """
        addr_str = addr_str.strip()
        if not addr_str:
            return b'\x00' * length

        # 只保留数字
        digits = ''.join(c for c in addr_str if c.isdigit())
        # 补齐到偶数位
        if len(digits) % 2 == 1:
            digits = '0' + digits

        result = bytearray()
        for i in range(0, len(digits), 2):
            high = int(digits[i])
            low = int(digits[i + 1])
            result.append((high << 4) | low)

        # 截断或补齐
        if len(result) < length:
            result.extend(b'\x00' * (length - len(result)))
        elif len(result) > length:
            result = result[:length]

        return bytes(result)

    def _build_application_data(self, afn: int, fn: int,
                                field_values: Dict[str, Any]) -> bytes:
        """组装应用数据域: AFN(已在外层) + DT(已在外层) + 数据单元"""
        schema = GDW_AFNFN_SCHEMA.get((afn, fn))
        if not schema:
            return b''

        fields = schema.get("fields", [])
        if not fields:
            return b''

        # 复用南网引擎的字段打包逻辑（内联简化版）
        return self._pack_fields(fields, field_values)

    def _pack_fields(self, fields: List[Dict[str, Any]],
                     values: Dict[str, Any]) -> bytes:
        """按Schema打包字段（兼容南网字段类型）"""
        # 预处理: 计算count_field和length_field引用
        processed = dict(values)
        for field in fields:
            name = field["name"]
            if field.get("type") == "list" and "count_field" in field:
                ref = field["count_field"]
                items = processed.get(name, [])
                processed[ref] = len(items) if isinstance(items, list) else 0
            if "length_field" in field:
                ref = field["length_field"]
                val = processed.get(name)
                if val is not None:
                    raw = self._to_raw_bytes(field, val)
                    processed[ref] = len(raw) + field.get("length_offset", 0)

        # 按顺序打包
        result = b""
        for field in fields:
            name = field["name"]
            val = processed.get(name)
            if val is None and field.get("optional", False):
                continue
            result += self._pack_field(field, val)
        return result

    def _pack_field(self, field: Dict[str, Any], value: Any) -> bytes:
        """打包单个字段"""
        if value is None:
            return b""

        ftype = field["type"]

        if ftype in ("uint8", "enum"):
            return struct.pack("B", int(value))
        elif ftype == "uint16":
            endian = field.get("endian", "little")
            fmt = ">H" if endian == "big" else "<H"
            return struct.pack(fmt, int(value))
        elif ftype == "uint32":
            endian = field.get("endian", "little")
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
            data = b""
            if "count_type" in field:
                ct = field["count_type"]
                if ct == "uint8":
                    data += struct.pack("B", len(items))
                elif ct == "uint16":
                    data += struct.pack(">H", len(items))
            for item in items:
                for item_field in item_fields:
                    iname = item_field["name"]
                    ival = item.get(iname, item_field.get("default"))
                    data += self._pack_field(item_field, ival)
            return data
        else:
            raise ValueError(f"不支持的字段类型: {ftype}")

    def _to_raw_bytes(self, field: Dict[str, Any], value: Any) -> bytes:
        """计算字段原始字节长度"""
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
            return self._pack_field(field, value)

    @staticmethod
    def _fn_to_dt(fn: int) -> bytes:
        """将Fn转换为DT (DT1 + DT2)"""
        if fn < 1 or fn > 248:
            raise ValueError(f"Fn必须在1~248之间: {fn}")
        dt2 = (fn - 1) // 8
        dt1 = 1 << ((fn - 1) % 8)
        return bytes([dt1, dt2])

    def get_supported_afn_fn(self) -> List[Tuple[int, int, str]]:
        """返回所有支持的(AFN, Fn, 名称)列表"""
        result = []
        for (afn, fn), schema in sorted(GDW_AFNFN_SCHEMA.items()):
            name = schema.get("name", "")
            direction = schema.get("direction", "both")
            if direction == "down" or direction == "both":
                result.append((afn, fn, name))
        return result

    def get_schema(self, afn: int, fn: int) -> Optional[Dict[str, Any]]:
        """获取指定AFN+Fn的Schema"""
        return GDW_AFNFN_SCHEMA.get((afn, fn))

    def generate_data(self, afn: int, fn: int,
                      field_values: Dict[str, Any]) -> bytes:
        """仅生成数据单元字节（用于测试）"""
        return self._build_application_data(afn, fn, field_values)


if __name__ == "__main__":
    gen = GDWFrameGenerator()

    # 测试: AFN=01H, F1 硬件初始化 (无数据单元)
    info = {
        "dir": 0, "prm": 1, "通信方式": 3,
        "路由标识": 0, "附属节点标识": 0, "通信模块标识": 0,
        "冲突检测": 0, "中继级别": 0, "纠错编码标识": 0,
        "信道标识": 0, "预计应答字节数": 0,
        "通信速率": 0, "速率单位标识": 0, "报文序列号": 0,
    }
    frame = gen.generate_frame(0x01, 1, {}, info)
    print(f"硬件初始化帧: {frame.hex()}")

    # 测试: AFN=02H, F1 转发通信协议数据帧
    info["通信模块标识"] = 1
    fields = {
        "通信协议类型": 2,
        "报文长度": 4,
        "报文内容": "68111111",
    }
    frame = gen.generate_frame(0x02, 1, fields, info,
                                src_addr="123456789012",
                                dst_addr="999999999999")
    print(f"数据转发帧: {frame.hex()}")
