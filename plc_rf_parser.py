"""
PLC RF模块与电能表之间的数据接口规范解析器
协议版本：V1_04_251205
适用范围：海外市场PLC/RF模块与电能表通信（I4接口）
"""

import struct
from typing import Dict, Any, Optional, List, Tuple
from dlms_parser import DLMSParser


class PLCRFProtocolParser:
    """PLC RF协议帧解析器"""

    # 帧起始符
    FRAME_START = 0x02

    # 控制域定义
    CONTROL_MAP = {
        0xC0: "模块→电表（下行）",
        0xC4: "电表→模块（上行）",
    }

    # 命令字映射 (Command Code -> 中文含义)
    COMMAND_MAP = {
        0x1001: "模块通用信息",
        0x1101: "启动升级命令（初始化）",
        0x1102: "发送升级包数据",
        0x1103: "激活模块固件",
        0x1201: "数据推送（DataNotification）",
        0x1202: "事件推送（EventNotification）",
        0x1301: "DLMS数据帧封装",
        0x2001: "模块获取电表表号",
        0x2002: "心跳机制",
        0x2003: "模块将自身信息传输至电表",
        0x2004: "获取电表信息",
        0x2101: "从电表获取G3-PLC信息",
        0x2102: "模块将G3-PLC信息传输至电表",
    }

    # 模块厂家代码
    MANUFACTURER_MAP = {
        0x00: "无",
        0x01: "东软",
        0x02: "矩泉",
        0x03: "有方",
        0x04: "华为",
        0x05: "中兴",
        0x06: "瑞瀛",
        0x07: "智微宽载",
    }

    # 模块类型
    MODULE_TYPE_MAP = {
        0x00: "无",
        0x01: "2G(GPRS)",
        0x02: "3G(EDGE)",
        0x03: "3G(UMTS)",
        0x04: "3G(HSDPA)",
        0x05: "3G(CDMA)",
        0x06: "4G(LTE)",
        0x07: "4G(LTE-M)",
        0x08: "4G(LTE-NB1)",
        0x09: "4G(LTE-NB2)",
        0x0A: "WIFI 4",
        0x0B: "WIFI 6",
        0x0C: "以太网",
        0x0D: "HPLC",
        0x0E: "G3-PLC",
        0x0F: "RF",
    }

    # HPLC频段定义
    HPLC_BAND_MAP = {
        0: {"范围": "1.953~11.96 MHz", "载波编号": "80~490"},
        1: {"范围": "2.441~5.615 MHz", "载波编号": "100~230"},
        2: {"范围": "0.781~2.930 MHz", "载波编号": "32~120"},
        3: {"范围": "1.758~2.930 MHz", "载波编号": "72~120"},
    }

    # 状态字定义
    STATUS_MAP = {
        0x00: "失败/离线",
        0x01: "成功/在线",
    }

    def __init__(self):
        self.dlms_parser = DLMSParser()

    # CRC16查找表（与4.md文档中的C代码一致）
    CRC16_TABLE = [
        0x0000, 0x1189, 0x2312, 0x329b, 0x4624, 0x57ad, 0x6536, 0x74bf,
        0x8c48, 0x9dc1, 0xaf5a, 0xbed3, 0xca6c, 0xdbe5, 0xe97e, 0xf8f7,
        0x1081, 0x0108, 0x3393, 0x221a, 0x56a5, 0x472c, 0x75b7, 0x643e,
        0x9cc9, 0x8d40, 0xbfdb, 0xae52, 0xdaed, 0xcb64, 0xf9ff, 0xe876,
        0x2102, 0x308b, 0x0210, 0x1399, 0x6726, 0x76af, 0x4434, 0x55bd,
        0xad4a, 0xbcc3, 0x8e58, 0x9fd1, 0xeb6e, 0xfae7, 0xc87c, 0xd9f5,
        0x3183, 0x200a, 0x1291, 0x0318, 0x77a7, 0x662e, 0x54b5, 0x453c,
        0xbdcb, 0xac42, 0x9ed9, 0x8f50, 0xfbef, 0xea66, 0xd8fd, 0xc974,
        0x4204, 0x538d, 0x6116, 0x709f, 0x0420, 0x15a9, 0x2732, 0x36bb,
        0xce4c, 0xdfc5, 0xed5e, 0xfcd7, 0x8868, 0x99e1, 0xab7a, 0xbaf3,
        0x5285, 0x430c, 0x7197, 0x601e, 0x14a1, 0x0528, 0x37b3, 0x263a,
        0xdecd, 0xcf44, 0xfddf, 0xec56, 0x98e9, 0x8960, 0xbbfb, 0xaa72,
        0x6306, 0x728f, 0x4014, 0x519d, 0x2522, 0x34ab, 0x0630, 0x17b9,
        0xef4e, 0xfec7, 0xcc5c, 0xddd5, 0xa96a, 0xb8e3, 0x8a78, 0x9bf1,
        0x7387, 0x620e, 0x5095, 0x411c, 0x35a3, 0x242a, 0x16b1, 0x0738,
        0xffcf, 0xee46, 0xdcdd, 0xcd54, 0xb9eb, 0xa862, 0x9af9, 0x8b70,
        0x8408, 0x9581, 0xa71a, 0xb693, 0xc22c, 0xd3a5, 0xe13e, 0xf0b7,
        0x0840, 0x19c9, 0x2b52, 0x3adb, 0x4e64, 0x5fed, 0x6d76, 0x7cff,
        0x9489, 0x8500, 0xb79b, 0xa612, 0xd2ad, 0xc324, 0xf1bf, 0xe036,
        0x18c1, 0x0948, 0x3bd3, 0x2a5a, 0x5ee5, 0x4f6c, 0x7df7, 0x6c7e,
        0xa50a, 0xb483, 0x8618, 0x9791, 0xe32e, 0xf2a7, 0xc03c, 0xd1b5,
        0x2942, 0x38cb, 0x0a50, 0x1bd9, 0x6f66, 0x7eef, 0x4c74, 0x5dfd,
        0xb58b, 0xa402, 0x9699, 0x8710, 0xf3af, 0xe226, 0xd0bd, 0xc134,
        0x39c3, 0x284a, 0x1ad1, 0x0b58, 0x7fe7, 0x6e6e, 0x5cf5, 0x4d7c,
        0xc60c, 0xd785, 0xe51e, 0xf497, 0x8028, 0x91a1, 0xa33a, 0xb2b3,
        0x4a44, 0x5bcd, 0x6956, 0x78df, 0x0c60, 0x1de9, 0x2f72, 0x3efb,
        0xd68d, 0xc704, 0xf59f, 0xe416, 0x90a9, 0x8120, 0xb3bb, 0xa232,
        0x5ac5, 0x4b4c, 0x79d7, 0x685e, 0x1ce1, 0x0d68, 0x3ff3, 0x2e7a,
        0xe70e, 0xf687, 0xc41c, 0xd595, 0xa12a, 0xb0a3, 0x8238, 0x93b1,
        0x6b46, 0x7acf, 0x4854, 0x59dd, 0x2d62, 0x3ceb, 0x0e70, 0x1ff9,
        0xf78f, 0xe606, 0xd49d, 0xc514, 0xb1ab, 0xa022, 0x92b9, 0x8330,
        0x7bc7, 0x6a4e, 0x58d5, 0x495c, 0x3de3, 0x2c6a, 0x1ef1, 0x0f78
    ]

    def calculate_crc16(self, data: bytes) -> int:
        """计算CRC16校验值（使用查表法，与4.md文档C代码一致）
        
        根据4.md文档附录A定义：
        - 计算范围：从Length（包含）到UserData（包含）之间的数据
        - 存储格式：CRC16采用小端格式（Little-Endian）
        - 初始值：0xFFFF
        - 最终异或值：0xFFFF
        - 多项式：CRC-CCITT (0x1021) 查表实现
        """
        fcs = 0xFFFF
        for byte in data:
            fcs = ((fcs >> 8) ^ self.CRC16_TABLE[(fcs ^ byte) & 0xFF]) & 0xFFFF
        return fcs ^ 0xFFFF
    
    def verify_crc(self, frame_bytes: bytes) -> tuple:
        """验证CRC16校验，返回(接收值, 计算值, 是否匹配)
        
        根据4.md文档定义：
        - CRC16计算范围：从Length（包含）到UserData（包含）
        - CRC16存储格式：小端格式（Little-Endian）
        - 备注：整个数据帧除CRC16采用小端传输外，其余数据均采用大端传输
        """
        if len(frame_bytes) < 8:
            return None, None, False
        
        # 解析长度域（大端序）
        length_val = struct.unpack('>H', frame_bytes[1:3])[0]
        
        # CRC16位置：Start(1) + Length(2) + length_val - CRC16自身(2)
        crc_pos = 3 + length_val - 2
        
        if crc_pos + 2 > len(frame_bytes):
            return None, None, False
        
        # 读取CRC16（小端序）
        crc_received = struct.unpack('<H', frame_bytes[crc_pos:crc_pos + 2])[0]
        
        # 计算CRC16：从Length（索引1）到UserData结束（索引crc_pos）
        crc_data = frame_bytes[1:crc_pos]
        crc_calculated = self.calculate_crc16(crc_data)
        
        return crc_received, crc_calculated, crc_received == crc_calculated

    def parse_to_table(self, frame_bytes: bytes) -> list:
        """解析为表格数据格式

        返回：[(字段名，原始值，解析值，说明, byte_start, byte_end), ...]
        """
        table_data = []

        try:
            result = self.parse(frame_bytes)
            if result.get("解析状态") != "成功":
                table_data.append(("错误", "-", "-", result.get("错误信息", "未知错误"), None, None))
                return table_data

            # 帧头
            self._add_field(table_data, "起始字符", "0x02", "0x02", "帧起始标志", 0, 0)

            # 长度域
            length_raw = result["长度域"]["原始值"]
            length_val = result["长度域"]["长度值"]
            self._add_field(table_data, "长度域", length_raw, str(length_val), "大端序，从Control到CRC16的字节数", 1, 2)

            # 控制域
            ctrl_raw = result["控制域"]["原始值"]
            ctrl_desc = result["控制域"]["说明"]
            self._add_field(table_data, "控制域", ctrl_raw, "", ctrl_desc, 3, 3)
            # 提取控制域字节值
            control_byte = int(ctrl_raw, 16)

            # 命令字
            cmd_raw = result["命令字"]["原始值"]
            cmd_name = result["命令字"]["名称"]
            self._add_field(table_data, "命令字", cmd_raw, f"0x{result['命令字']['命令值']:04X}", cmd_name, 4, 5)

            # 用户数据区
            user_data_offset = 6
            user_data = result.get("用户数据区", {})
            if user_data:
                # 计算用户数据区范围: 从Command(4,5)之后到CRC16之前
                # CRC16位置 = 3 + length - 2
                crc_pos = 3 + result["长度域"]["长度值"] - 2
                user_data_end = crc_pos - 1
                self._add_field(table_data, "用户数据区", "", "", "", user_data_offset, user_data_end)

                # 解析具体数据内容（传入控制域）
                self._parse_user_data_to_table(result["命令字"]["命令值"], user_data, table_data, user_data_offset, control_byte)

            # CRC16
            # Length域指的是从Control到CRC16（包含）的字节数
            crc_pos = 3 + result["长度域"]["长度值"] - 2
            if "校验和" in result:
                crc_raw = result["校验和"]["校验值"]
                crc_calc = result["校验和"]["计算值"]
                crc_result = result["校验和"]["校验结果"]
                self._add_field(table_data, "CRC16", crc_raw, crc_calc, crc_result, crc_pos, crc_pos + 1)
            else:
                self._add_field(table_data, "CRC16", "-", "-", "未计算", crc_pos, crc_pos + 1)

        except Exception as e:
            table_data.append(("解析错误", "-", "-", str(e), None, None))

        return table_data

    def _add_field(self, table_data: list, field_name: str, raw_value: str, parsed_value: str,
                   comment: str, byte_start: Optional[int] = None, byte_end: Optional[int] = None,
                   is_child: bool = False):
        """添加字段到表格"""
        prefix = "  " if is_child else ""
        full_name = f"{prefix}{field_name}"
        table_data.append((full_name, raw_value, parsed_value, comment, byte_start, byte_end))

    def _parse_ascii_string(self, data: bytes) -> str:
        """解析ASCII字符串（去掉填充的0x00）"""
        try:
            # 找到第一个0x00的位置
            null_pos = data.find(b'\x00')
            if null_pos >= 0:
                return data[:null_pos].decode('ascii', errors='replace')
            return data.decode('ascii', errors='replace')
        except:
            return data.hex(' ').upper()
    
    def _parse_ipv6_address(self, data: bytes) -> str:
        """解析IPv6地址（46字节格式）
        
        根据示例：[fe80:0:0:781d:ff:fe00:0]:61616
        数据结构：IPv6地址(39字节ASCII) + 端口号(2字节大端序) + 填充(5字节0x00)
        """
        try:
            # IPv6地址部分是ASCII格式，查找第一个0x00
            null_pos = data.find(b'\x00')
            if null_pos > 0:
                # 前null_pos字节是IPv6地址字符串
                ipv6_str = data[:null_pos].decode('ascii', errors='replace')
                return ipv6_str
            
            # 如果没有找到0x00，直接返回hex
            return data.hex(' ').upper()
        except:
            return data.hex(' ').upper()

    def _parse_user_data_to_table(self, command: int, user_data: dict, table_data: list, offset: int, control_byte: int = 0):
        """解析用户数据区到表格
        
        Args:
            command: 命令字
            user_data: 已解析的用户数据区字典
            table_data: 表格数据列表
            offset: 当前字节偏移量
            control_byte: 控制域字节（0xC0=模块→电表，0xC4=电表→模块）
        """
        sub_offset = offset

        if command == 0x1001:
            # 模块通用信息
            if "模块厂家代码" in user_data:
                val = user_data["模块厂家代码"]
                self._add_field(table_data, "  模块厂家代码", val["原始值"], val["名称"], "", sub_offset, sub_offset, is_child=True)
                sub_offset += 1

            if "模块类型" in user_data:
                val = user_data["模块类型"]
                self._add_field(table_data, "  模块类型", val["原始值"], val["名称"], "", sub_offset, sub_offset, is_child=True)
                sub_offset += 1

            if "硬件版本号" in user_data:
                val = user_data["硬件版本号"]
                self._add_field(table_data, "  硬件版本号", val["原始值"], val["解析值"], "", sub_offset, sub_offset + 7, is_child=True)
                sub_offset += 8

            if "硬件详细版本信息" in user_data:
                val = user_data["硬件详细版本信息"]
                self._add_field(table_data, "  硬件详细版本", val["原始值"], val["解析值"], "", sub_offset, sub_offset + 19, is_child=True)
                sub_offset += 20

            if "软件版本号" in user_data:
                val = user_data["软件版本号"]
                self._add_field(table_data, "  软件版本号", val["原始值"], val["解析值"], "", sub_offset, sub_offset + 7, is_child=True)
                sub_offset += 8

            if "软件详细版本号" in user_data:
                val = user_data["软件详细版本号"]
                self._add_field(table_data, "  软件详细版本", val["原始值"], val["解析值"], "", sub_offset, sub_offset + 19, is_child=True)
                sub_offset += 20

            if "模块序列号" in user_data:
                val = user_data["模块序列号"]
                self._add_field(table_data, "  模块序列号", val["原始值"], val["解析值"], "", sub_offset, sub_offset + 15, is_child=True)
                sub_offset += 16

        elif command == 0x2001:
            # 获取电表表号
            if "表号" in user_data:
                val = user_data["表号"]
                # 表号结构：0x09（类型，1字节）+ 长度（1字节）+ 表号内容
                # 所以表号长度字段占2字节（0x09 + 长度字节）
                self._add_field(table_data, "  表号长度", str(val.get("长度", "-")), str(val.get("长度", "-")) + " 字节", "", sub_offset, sub_offset + 1, is_child=True)
                sub_offset += 2  # 0x09类型字节 + 长度字节
                if "原始值" in val:
                    raw_len = len(val["原始值"].replace(" ", "")) // 2
                    self._add_field(table_data, "  表号内容", val["原始值"], val.get("解析值", ""), "", sub_offset, sub_offset + raw_len - 1, is_child=True)
                    sub_offset += raw_len

        elif command == 0x2002:
            # 心跳机制（通常无数据）
            self._add_field(table_data, "  心跳报文", "-", "无数据内容", "电表无需响应", sub_offset, sub_offset, is_child=True)

        elif command == 0x2003:
            # 模块信息传输
            if "模块在线状态" in user_data:
                val = user_data["模块在线状态"]
                self._add_field(table_data, "  模块在线状态", val["原始值"], val["名称"], "", sub_offset, sub_offset, is_child=True)
                sub_offset += 1

            if "HPLC_band" in user_data:
                val = user_data["HPLC_band"]
                band_info = self.HPLC_BAND_MAP.get(val.get("值", 0), {})
                desc = f"频段{val.get('值', '-')}"
                if band_info:
                    desc += f" ({band_info.get('范围', '')})"
                self._add_field(table_data, "  HPLC频段", val["原始值"], desc, band_info.get('载波编号', ''), sub_offset, sub_offset, is_child=True)
                sub_offset += 1

            if "HPLC_CCO_MAC_ADDR" in user_data:
                val = user_data["HPLC_CCO_MAC_ADDR"]
                self._add_field(table_data, "  CCO MAC地址", val["原始值"], val.get("解析值", ""), "最大16字节，右补0x00", sub_offset, sub_offset + 15, is_child=True)
                sub_offset += 16

        elif command == 0x2004:
            # 获取电表信息
            if "事件推送重试次数" in user_data:
                val = user_data["事件推送重试次数"]
                self._add_field(table_data, "  事件推送重试次数", val["原始值"], str(val.get("值", "-")), "失败后最大重试次数", sub_offset, sub_offset, is_child=True)
                sub_offset += 1

            if "事件推送重试延迟" in user_data:
                val = user_data["事件推送重试延迟"]
                self._add_field(table_data, "  事件推送重试延迟", val["原始值"], str(val.get("值", "-")) + " 秒", "重试间隔时间", sub_offset, sub_offset + 1, is_child=True)
                sub_offset += 2

            if "心跳周期" in user_data:
                val = user_data["心跳周期"]
                self._add_field(table_data, "  心跳周期", val["原始值"], str(val.get("值", "-")) + " 秒", "模块发送心跳间隔必须小于此值的一半", sub_offset, sub_offset + 1, is_child=True)
                sub_offset += 2

            if "功能控制字" in user_data:
                val = user_data["功能控制字"]
                func_val = val.get("值", 0)
                dlms_enabled = "使能（封装）" if (func_val & 0x8000) else "禁止（透传）"
                self._add_field(table_data, "  功能控制字", val["原始值"], f"0x{func_val:04X}", f"BIT15: DLMS封装={dlms_enabled}", sub_offset, sub_offset + 1, is_child=True)
                sub_offset += 2

        elif command in [0x1201, 0x1202]:
            # 数据推送/事件推送 - 根据控制域区分上行和下行
            if control_byte == 0xC0:
                # 模块→电表（下行）：只有1字节状态字
                if "状态" in user_data:
                    val = user_data["状态"]
                    self._add_field(table_data, "  状态字", val["原始值"], val["名称"], "", sub_offset, sub_offset, is_child=True)
                    sub_offset += 1
            elif control_byte == 0xC4:
                # 电表→模块（上行）：完整的数据推送结构
                if "推送的目标地址类型" in user_data:
                    val = user_data["推送的目标地址类型"]
                    self._add_field(table_data, "  推送目标地址类型", val["原始值"], val["说明"], "", sub_offset, sub_offset, is_child=True)
                    sub_offset += 1

                if "推送的目标地址" in user_data:
                    val = user_data["推送的目标地址"]
                    raw_len = len(val["原始值"].replace(" ", "")) // 2
                    self._add_field(table_data, "  推送目标地址", val["原始值"][:30] + "..." if raw_len > 15 else val["原始值"], val["解析值"], val["说明"], sub_offset, sub_offset + raw_len - 1, is_child=True)
                    sub_offset += raw_len

                if "推送延时时间" in user_data:
                    val = user_data["推送延时时间"]
                    self._add_field(table_data, "  推送延时时间", val["原始值"], val["说明"], "", sub_offset, sub_offset + 1, is_child=True)
                    sub_offset += 2

                if "透传的数据内容" in user_data:
                    val = user_data["透传的数据内容"]
                    raw_len = val["长度"]
                    self._add_field(table_data, "  透传数据内容", val["原始值"][:30] + "..." if raw_len > 15 else val["原始值"], f"共{raw_len}字节", val["说明"], sub_offset, sub_offset + raw_len - 1, is_child=True)

                    # 解析DLMS帧内容
                    dlms_bytes = bytes.fromhex(val["原始值"].replace(" ", ""))
                    dlms_table = self.dlms_parser.parse_to_table(dlms_bytes)
                    for dlms_field, dlms_raw, dlms_parsed, dlms_comment, dlms_start, dlms_end in dlms_table:
                        self._add_field(table_data, f"    {dlms_field}", dlms_raw, dlms_parsed, dlms_comment, sub_offset + dlms_start if dlms_start is not None else None, sub_offset + dlms_end if dlms_end is not None else None, is_child=True)

        elif command in [0x2003, 0x2102]:
            # 状态响应
            if "状态" in user_data:
                val = user_data["状态"]
                self._add_field(table_data, "  状态字", val["原始值"], val["名称"], "", sub_offset, sub_offset, is_child=True)
                sub_offset += 1

        else:
            # 通用解析（未知命令）
            if "原始数据" in user_data:
                raw_data = user_data["原始数据"]
                self._add_field(table_data, "  原始数据", raw_data, "", "", sub_offset, sub_offset + len(bytes.fromhex(raw_data.replace(" ", ""))) - 1, is_child=True)

    def parse(self, frame_bytes: bytes) -> Dict[str, Any]:
        """解析PLC RF协议帧"""
        result = {
            "原始数据": frame_bytes.hex(' ').upper(),
            "解析状态": "成功",
        }

        # 最小帧长度检查：Start(1) + Length(2) + Control(1) + Command(2) + CRC16(2) = 8字节
        if len(frame_bytes) < 8:
            result["解析状态"] = "失败"
            result["错误信息"] = f"帧长度过短：{len(frame_bytes)}字节，最小需要8字节"
            return result

        # 检查起始符
        if frame_bytes[0] != self.FRAME_START:
            result["解析状态"] = "失败"
            result["错误信息"] = f"起始符错误：0x{frame_bytes[0]:02X}，期望0x{self.FRAME_START:02X}"
            return result

        result["帧头"] = {"起始字符": f"0x{frame_bytes[0]:02X}"}

        # 解析长度域（大端序）
        length_val = struct.unpack('>H', frame_bytes[1:3])[0]
        result["长度域"] = {
            "原始值": f"0x{frame_bytes[1]:02X} {frame_bytes[2]:02X}",
            "长度值": length_val,
            "说明": f"大端序，从Control到CRC16共{length_val}字节",
        }

        # 验证帧长度
        expected_len = 3 + length_val  # Start(1) + Length(2) + Data(length_val)
        if len(frame_bytes) < expected_len:
            result["解析状态"] = "失败"
            result["错误信息"] = f"帧长度不匹配：声明{length_val}字节，实际数据区仅{len(frame_bytes) - 3}字节"
            return result

        # 解析控制域
        control_byte = frame_bytes[3]
        control_desc = self.CONTROL_MAP.get(control_byte, f"未知(0x{control_byte:02X})")
        result["控制域"] = {
            "原始值": f"0x{control_byte:02X}",
            "说明": control_desc,
        }

        # 解析命令字（大端序）
        command_val = struct.unpack('>H', frame_bytes[4:6])[0]
        command_name = self.COMMAND_MAP.get(command_val, f"未知命令(0x{command_val:04X})")
        result["命令字"] = {
            "原始值": f"0x{frame_bytes[4]:02X} {frame_bytes[5]:02X}",
            "命令值": command_val,
            "名称": command_name,
        }

        # 用户数据区（从Command之后到CRC16之前）
        # Length = Control(1) + Command(2) + UserData(N) + CRC16(2)
        user_data_len = length_val - 5  # Control(1) + Command(2) + CRC16(2) = 5
        if user_data_len > 0:
            user_data_bytes = frame_bytes[6:6 + user_data_len]
            result["用户数据区"] = self._parse_data_content(command_val, user_data_bytes, control_byte)
        else:
            result["用户数据区"] = {}

        # CRC16校验（小端序）
        # 根据4.md文档：CRC16计算范围从Length（包含）到UserData（包含），采用小端格式
        # Length域指的是从Control到CRC16（包含）的字节数
        # 所以CRC16在帧中的位置是：Start(1) + Length(2) + length_val - 2
        crc_pos = 3 + length_val - 2
        if crc_pos + 2 <= len(frame_bytes):
            crc_received = struct.unpack('<H', frame_bytes[crc_pos:crc_pos + 2])[0]
            # 计算CRC16：从Length（索引1）到UserData结束（索引crc_pos）
            crc_data = frame_bytes[1:crc_pos]
            crc_calculated = self.calculate_crc16(crc_data)

            result["校验和"] = {
                "校验值": f"0x{crc_received:04X}",
                "计算值": f"0x{crc_calculated:04X}",
                "校验结果": "✓ 正确" if crc_received == crc_calculated else "✗ 错误",
            }
        elif crc_pos < len(frame_bytes):
            # 只有1字节CRC，不完整
            result["校验和"] = {
                "校验值": "不完整",
                "计算值": "-",
                "校验结果": "✗ CRC数据不完整",
            }

        return result

    def _parse_data_content(self, command: int, data: bytes, control_byte: int = 0) -> Dict[str, Any]:
        """解析数据内容
        
        Args:
            command: 命令字
            data: 用户数据区字节
            control_byte: 控制域字节（0xC0=模块→电表，0xC4=电表→模块）
        """
        content = {"原始数据": data.hex(' ').upper()}

        if command == 0x1001:
            # 模块通用信息
            if len(data) >= 1:
                manufacturer = data[0]
                content["模块厂家代码"] = {
                    "原始值": f"0x{manufacturer:02X}",
                    "名称": self.MANUFACTURER_MAP.get(manufacturer, f"未知(0x{manufacturer:02X})"),
                }

            if len(data) >= 2:
                module_type = data[1]
                content["模块类型"] = {
                    "原始值": f"0x{module_type:02X}",
                    "名称": self.MODULE_TYPE_MAP.get(module_type, f"未知(0x{module_type:02X})"),
                }

            if len(data) >= 10:
                hw_version = data[2:10]
                content["硬件版本号"] = {
                    "原始值": hw_version.hex(' ').upper(),
                    "解析值": self._parse_ascii_string(hw_version),
                }

            if len(data) >= 30:
                hw_detail = data[10:30]
                content["硬件详细版本信息"] = {
                    "原始值": hw_detail.hex(' ').upper(),
                    "解析值": self._parse_ascii_string(hw_detail),
                }

            if len(data) >= 38:
                sw_version = data[30:38]
                content["软件版本号"] = {
                    "原始值": sw_version.hex(' ').upper(),
                    "解析值": self._parse_ascii_string(sw_version),
                }

            if len(data) >= 58:
                sw_detail = data[38:58]
                content["软件详细版本号"] = {
                    "原始值": sw_detail.hex(' ').upper(),
                    "解析值": self._parse_ascii_string(sw_detail),
                }

            if len(data) >= 74:
                serial = data[58:74]
                content["模块序列号"] = {
                    "原始值": serial.hex(' ').upper(),
                    "解析值": self._parse_ascii_string(serial),
                }

        elif command == 0x2001:
            # 获取电表表号
            if len(data) >= 2:
                if data[0] == 0x09:  # 固定值，代表数据类型
                    str_len = data[1]
                    meter_id = data[2:2 + str_len]
                    content["表号"] = {
                        "长度": str_len,
                        "原始值": meter_id.hex(' ').upper(),
                        "解析值": self._parse_ascii_string(meter_id),
                    }

        elif command == 0x2003:
            # 模块信息传输
            if len(data) >= 1:
                online_status = data[0]
                content["模块在线状态"] = {
                    "原始值": f"0x{online_status:02X}",
                    "值": online_status,
                    "名称": "在线" if online_status == 1 else "离线",
                }

            if len(data) >= 2:
                hplc_band = data[1]
                content["HPLC_band"] = {
                    "原始值": f"0x{hplc_band:02X}",
                    "值": hplc_band,
                }

            if len(data) >= 18:
                cco_mac = data[2:18]
                content["HPLC_CCO_MAC_ADDR"] = {
                    "原始值": cco_mac.hex(' ').upper(),
                    "解析值": self._parse_ascii_string(cco_mac),
                }

        elif command == 0x2004:
            # 获取电表信息
            offset = 0
            if len(data) >= offset + 1:
                retry_count = data[offset]
                content["事件推送重试次数"] = {
                    "原始值": f"0x{retry_count:02X}",
                    "值": retry_count,
                }
                offset += 1

            if len(data) >= offset + 2:
                retry_delay = struct.unpack('>H', data[offset:offset + 2])[0]
                content["事件推送重试延迟"] = {
                    "原始值": f"0x{data[offset]:02X} {data[offset + 1]:02X}",
                    "值": retry_delay,
                }
                offset += 2

            if len(data) >= offset + 2:
                heartbeat_period = struct.unpack('>H', data[offset:offset + 2])[0]
                content["心跳周期"] = {
                    "原始值": f"0x{data[offset]:02X} {data[offset + 1]:02X}",
                    "值": heartbeat_period,
                }
                offset += 2

            if len(data) >= offset + 2:
                func_ctrl = struct.unpack('>H', data[offset:offset + 2])[0]
                content["功能控制字"] = {
                    "原始值": f"0x{data[offset]:02X} {data[offset + 1]:02X}",
                    "值": func_ctrl,
                }
                offset += 2

        elif command in [0x1201, 0x1202]:
            # 数据推送/事件推送 - 根据控制域区分上行和下行
            if control_byte == 0xC0:
                # 模块→电表（下行）：只有1字节状态字
                # 根据4.md文档：02 00 06 C0 12 01 [状态] CRC16
                if len(data) >= 1:
                    status = data[0]
                    content["状态"] = {
                        "原始值": f"0x{status:02X}",
                        "值": status,
                        "名称": "推送成功" if status == 0x01 else "推送失败",
                    }
            elif control_byte == 0xC4:
                # 电表→模块（上行）：完整的数据推送结构
                if command == 0x1201:
                    # 数据推送 (DataNotification)
                    # 结构：目标地址类型(1) + 目标地址(48) + 推送延时(2) + DLMS数据(N)
                    offset = 0

                    # 推送的目标地址类型（1字节）
                    if len(data) >= offset + 1:
                        addr_type = data[offset]
                        # 根据4.md文档：0=IPv4, 1=IPv6, 2=SMS
                        type_map = {0x00: "IPv4", 0x01: "IPv6", 0x02: "SMS"}
                        content["推送的目标地址类型"] = {
                            "原始值": f"0x{addr_type:02X}",
                            "值": addr_type,
                            "说明": type_map.get(addr_type, f"未知(0x{addr_type:02X})"),
                        }
                        offset += 1

                    # 推送的目标地址（最大48字节）
                    if len(data) >= offset + 48:
                        addr_bytes = data[offset:offset + 48]
                        # 解析地址（去掉填充的0x00）
                        null_pos = addr_bytes.find(b'\x00')
                        if null_pos > 0:
                            addr_str = addr_bytes[:null_pos].decode('ascii', errors='replace')
                        else:
                            addr_str = addr_bytes.decode('ascii', errors='replace')
                        content["推送的目标地址"] = {
                            "原始值": addr_bytes.hex(' ').upper(),
                            "解析值": addr_str,
                            "说明": "最大48字节，右补0x00",
                        }
                        offset += 48

                    # 推送延时时间（2字节，大端序）
                    if len(data) >= offset + 2:
                        delay = struct.unpack('>H', data[offset:offset + 2])[0]
                        content["推送延时时间"] = {
                            "原始值": f"0x{data[offset]:02X} {data[offset+1]:02X}",
                            "值": delay,
                            "说明": f"{delay}秒" if delay > 0 else "无延时（立即推送）",
                        }
                        offset += 2

                    # 透传的数据内容（剩余字节）
                    if len(data) > offset:
                        dlms_data = data[offset:]
                        content["透传的数据内容"] = {
                            "原始值": dlms_data.hex(' ').upper(),
                            "长度": len(dlms_data),
                            "说明": "DLMS数据帧，将数据直接推送到指定的目标地址",
                        }
                elif command == 0x1202:
                    # 事件推送 (EventNotification)
                    # 结构：推送延时(2) + DLMS数据(N)
                    offset = 0

                    # 推送延时时间（2字节，大端序）
                    if len(data) >= offset + 2:
                        delay = struct.unpack('>H', data[offset:offset + 2])[0]
                        content["推送延时时间"] = {
                            "原始值": f"0x{data[offset]:02X} {data[offset+1]:02X}",
                            "值": delay,
                            "说明": f"{delay}秒" if delay > 0 else "无延时（立即推送）",
                        }
                        offset += 2

                    # 透传的数据内容（剩余字节）
                    if len(data) > offset:
                        dlms_data = data[offset:]
                        content["透传的数据内容"] = {
                            "原始值": dlms_data.hex(' ').upper(),
                            "长度": len(dlms_data),
                            "说明": "DLMS数据帧",
                        }

        else:
            # 其他命令的通用解析
            content["原始数据"] = data.hex(' ').upper()

        return content

    def verify(self, frame_bytes: bytes):
        """验证帧的协议一致性，返回 ValidationResult"""
        from validator.plc_rf_validator import PLCRFValidator
        validator = PLCRFValidator()
        return validator.verify(frame_bytes)
