"""DL/T 698.45 帧生成器"""

import struct
import crcmod.predefined
from typing import Dict, Any
from dl_t698_45_axdr import AXDRCoder


class DLT69845FrameGenerator:
    """698.45 帧生成器"""

    def __init__(self):
        self.crc16 = crcmod.predefined.Crc('x-25')
        self.axdr = AXDRCoder()

    def _calc_crc(self, data: bytes) -> bytes:
        crc = self.crc16.new(data)
        return struct.pack('<H', crc.crcValue)

    def _assemble_frame(self, sa: bytes, ca: int, control: int, apdu: bytes) -> bytes:
        """组装完整帧

        sa: 服务器地址 (包含地址特征字节)
        ca: 客户机地址 (1字节)
        control: 控制域
        apdu: APDU 字节
        """
        # 帧头: 控制域 + SA + CA
        header = bytes([control]) + sa + bytes([ca])

        # 长度域 L = L自身(2) + 控制域(1) + SA(len) + CA(1) + HCS(2) + APDU(len) + FCS(2)
        length = 2 + 1 + len(sa) + 1 + 2 + len(apdu) + 2
        length_bytes = struct.pack('<H', length & 0x3FFF)

        # HCS 覆盖范围: 长度域到地址域 (不含起始字符和HCS本身)
        hcs = self._calc_crc(length_bytes + header)

        # 链路用户数据 = APDU
        user_data = apdu

        # FCS 覆盖范围: 长度域到链路用户数据 (不含起始字符、结束字符和FCS本身)
        fcs_data = length_bytes + header + hcs + user_data
        fcs = self._calc_crc(fcs_data)

        # 组装完整帧
        frame = bytes([0x68]) + length_bytes + header + hcs + user_data + fcs + bytes([0x16])
        return frame

    def generate_link_request(self, sa: bytes, ca: int = 0, piid: int = 0,
                              req_type: int = 0, heartbeat: int = 0) -> bytes:
        """生成 LINK-Request 帧"""
        # APDU: 01 [PIID] [req_type] [heartbeat]
        apdu = bytes([0x01, piid, req_type]) + struct.pack('<H', heartbeat)
        # DIR=0, PRM=1, SC=0, func=1 (链路管理)
        control = 0x41  # 0100 0001
        return self._assemble_frame(sa, ca, control, apdu)

    def generate_link_response(self, sa: bytes, ca: int = 0, piid_acd: int = 0,
                               result: int = 0, heartbeat: int = 0) -> bytes:
        """生成 LINK-Response 帧"""
        apdu = bytes([0x81, piid_acd, result]) + struct.pack('<H', heartbeat)
        # DIR=1, PRM=1, SC=0, func=1
        control = 0xC1  # 1100 0001
        return self._assemble_frame(sa, ca, control, apdu)

    def generate_get_request_normal(self, sa: bytes, ca: int, piid: int,
                                    oad: bytes) -> bytes:
        """生成 GET-Request Normal 帧"""
        # APDU: 05 01 [PIID] [OAD]
        apdu = bytes([0x05, 0x01, piid]) + oad
        # DIR=0, PRM=1, SC=0, func=3 (用户数据)
        control = 0x43  # 0100 0011
        return self._assemble_frame(sa, ca, control, apdu)

    def generate_set_request_normal(self, sa: bytes, ca: int, piid: int,
                                    oad: bytes, data_bytes: bytes) -> bytes:
        """生成 SET-Request Normal 帧"""
        # APDU: 06 01 [PIID] [OAD] [Data]
        apdu = bytes([0x06, 0x01, piid]) + oad + data_bytes
        control = 0x43
        return self._assemble_frame(sa, ca, control, apdu)

    def generate_action_request_normal(self, sa: bytes, ca: int, piid: int,
                                       omd: bytes, param: bytes = None) -> bytes:
        """生成 ACTION-Request Normal 帧"""
        apdu = bytes([0x07, 0x01, piid]) + omd
        if param:
            apdu += param
        control = 0x43
        return self._assemble_frame(sa, ca, control, apdu)

    def generate_get_response_normal(self, sa: bytes, ca: int, piid_acd: int,
                                     oad: bytes, data_bytes: bytes,
                                     dar: int = 0) -> bytes:
        """生成 GET-Response Normal 帧"""
        # APDU: 85 01 [PIID-ACD] [OAD] [00=dar_ok] [Data]
        apdu = bytes([0x85, 0x01, piid_acd]) + oad + bytes([0x00]) + data_bytes
        # DIR=1, PRM=1, SC=0, func=3
        control = 0xC3  # 1100 0011
        return self._assemble_frame(sa, ca, control, apdu)

    # ─── 从 schema 构建 control ───
    @staticmethod
    def build_control(dir_bit: int = 0, prm_bit: int = 1,
                      seg_bit: int = 0, sc_bit: int = 0,
                      func_code: int = 3) -> int:
        """构建控制域字节

        dir_bit: D7 传输方向 (0=客户机→服务器, 1=服务器→客户机)
        prm_bit: D6 启动标志 (0=被动, 1=主动)
        seg_bit: D5 分帧标志 (0=完整APDU, 1=APDU片段)
        sc_bit:  D3 扰码标志 (0=不加扰码, 1=加扰码+0x33)
        func_code: D2~D0 功能码 (1=链路管理, 3=用户数据)
        """
        control = 0
        control |= (dir_bit & 0x01) << 7
        control |= (prm_bit & 0x01) << 6
        control |= (seg_bit & 0x01) << 5
        control |= (sc_bit & 0x01) << 3
        control |= (func_code & 0x07)
        return control

    # ─── 从 schema 动态生成帧 ───
    def generate_frame(self, apdu_type: str, sub_type: str,
                       field_values: Dict[str, Any],
                       sa: bytes = None, ca: int = 0,
                       dir_bit: int = 0, prm_bit: int = 1,
                       seg_bit: int = 0, sc_bit: int = 0,
                       func_code: int = 3) -> bytes:
        """根据 schema 动态生成帧

        apdu_type: APDU 类型名 (如 "GET-Request")
        sub_type:  子类型名 (如 "get_normal")
        field_values: 从 UI 收集的字段值 {字段名: 值}
        sa: 服务器地址 (含地址特征字节), 默认广播
        ca: 客户机地址
        """
        import struct as _struct

        if sa is None:
            sa = bytes([0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01])

        apdu_header = self._build_apdu_header(apdu_type, sub_type)

        # 构建 APDU body
        body = b""
        piid_val = 1
        oi_val = 0
        attr_val = 2
        data_bytes_val = b""

        for name, val in field_values.items():
            if name == "PIID":
                piid_val = int(val) & 0xFF
            elif name == "OI":
                oi_val = int(val) & 0xFFFF
            elif name == "属性标识":
                attr_val = int(val) & 0xFF
            elif name == "方法标识":
                attr_val = int(val) & 0xFF  # reuse same logic
            elif name == "数据内容":
                raw = str(val).replace(" ", "").strip()
                data_bytes_val = bytes.fromhex(raw) if raw else b""
            elif name == "参数":
                raw = str(val).replace(" ", "").strip()
                data_bytes_val = bytes.fromhex(raw) if raw else b""
            elif name == "请求类型":
                body += _struct.pack("B", int(val) & 0xFF)
            elif name == "心跳周期":
                body += _struct.pack("<H", int(val) & 0xFFFF)
            elif name == "期望安全参数":
                body += _struct.pack("B", int(val) & 0xFF)
            elif name == "客户机APDU最大长度":
                body += _struct.pack("<H", int(val) & 0xFFFF)
            elif name == "期望帧最大窗口尺寸":
                body += _struct.pack("B", int(val) & 0xFF)
            elif name == "期望帧最大帧长":
                body += _struct.pack("<H", int(val) & 0xFFFF)
            elif name == "期望超时时间":
                body += _struct.pack("<H", int(val) & 0xFFFF)
            elif name == "断开原因":
                body += _struct.pack("B", int(val) & 0xFF)
            elif name == "安全参数":
                raw = str(val).replace(" ", "").strip()
                body += bytes.fromhex(raw) if raw else b""
            elif name == "代理服务器地址(SA)":
                raw = str(val).replace(" ", "").strip()
                body += bytes.fromhex(raw) if raw else b""
            elif name == "代理客户机地址(CA)":
                body += _struct.pack("B", int(val) & 0xFF)
            elif name == "代理APDU":
                raw = str(val).replace(" ", "").strip()
                body += bytes.fromhex(raw) if raw else b""
            elif name == "OAD列表":
                raw = str(val).replace(" ", "").strip()
                body += bytes.fromhex(raw) if raw else b""

        # 根据 APDU 类型组装 body
        if apdu_type in ("GET-Request", "SET-Request", "ACTION-Request"):
            apdu_body = _struct.pack("B", piid_val)
            if apdu_type == "GET-Request" and sub_type == "get_normal_list":
                apdu_body += body  # OAD list already assembled
            else:
                # OAD = OI(2B, big) + 属性标识(1B, 低5位=属性号, 高3位=属性特征) + 元素索引(1B=0x00)
                oad = _struct.pack(">H", oi_val) + _struct.pack("B", attr_val & 0x1F) + b'\x00'
                apdu_body += oad
                if data_bytes_val:
                    apdu_body += data_bytes_val
            apdu = apdu_header + apdu_body
            # GET-Request Normal/Record/Signature 需要在 APDU 末尾加时间标签
            if apdu_type == "GET-Request" and sub_type in ("get_normal", "get_record", "get_normal_list"):
                apdu += b'\x00'  # 时间标签: 0x00 = 无时间标签
        elif apdu_type in ("LINK-Request",):
            apdu = apdu_header + _struct.pack("B", piid_val) + body
        elif apdu_type in ("CONNECT-Request", "RELEASE-Request",):
            apdu = apdu_header + _struct.pack("B", piid_val) + body
        elif apdu_type in ("PROXY-Request", "SECURITY-Request",):
            apdu = apdu_header + _struct.pack("B", piid_val) + body
        else:
            apdu = apdu_header + _struct.pack("B", piid_val) + body

        # 根据 APDU 类型决定 func_code
        if apdu_type == "LINK-Request":
            fc = 1  # 链路管理
        else:
            fc = 3  # 用户数据

        control = self.build_control(
            dir_bit=dir_bit, prm_bit=prm_bit,
            seg_bit=seg_bit, sc_bit=sc_bit,
            func_code=fc
        )
        return self._assemble_frame(sa, ca, control, apdu)

    def _build_apdu_header(self, apdu_type: str, sub_type: str) -> bytes:
        """构建 APDU 首部 (类型码 + 子类型码)"""
        type_map = {
            "LINK-Request": 0x01,
            "CONNECT-Request": 0x02,
            "RELEASE-Request": 0x03,
            "GET-Request": 0x05,
            "SET-Request": 0x06,
            "ACTION-Request": 0x07,
            "PROXY-Request": 0x09,
            "SECURITY-Request": 0x10,
        }
        sub_type_map = {
            "link_request": 0x00,
            "connect_request": 0x00,
            "release_request": 0x00,
            "get_normal": 0x01,
            "get_normal_list": 0x02,
            "get_record": 0x03,
            "get_record_list": 0x04,
            "get_next": 0x05,
            "set_normal": 0x01,
            "set_normal_list": 0x02,
            "action_normal": 0x01,
            "action_normal_list": 0x02,
            "proxy_request": 0x00,
            "security_request": 0x00,
        }
        t = type_map.get(apdu_type, 0x05)
        s = sub_type_map.get(sub_type, 0x01)
        if s == 0x00:
            return bytes([t])
        return bytes([t, s])

    def get_supported_commands(self):
        """返回所有支持的(apdu_type, sub_type, name)列表"""
        from dl_t698_45_frame_schema import DLT69845_FIELD_SCHEMA
        for key, schema in DLT69845_FIELD_SCHEMA.items():
            yield (key[0], key[1], schema["name"])
