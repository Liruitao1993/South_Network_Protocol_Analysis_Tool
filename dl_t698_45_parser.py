"""DL/T 698.45 数据链路层帧解析器

帧格式: 68 L L C SA CA [HCS HCS] [APDU] [FCS FCS] 16
"""

import struct
from typing import Dict, Any, List, Optional, Tuple
import crcmod.predefined


class DLT69845Parser:
    """698.45 链路层帧解析器"""

    START_CHAR = 0x68
    END_CHAR = 0x16

    # 功能码映射
    FUNC_CODE_MAP = {
        0: "保留",
        1: "链路管理 (登录/心跳/退出)",
        2: "保留",
        3: "用户数据 (应用连接管理及数据交换)",
        4: "保留",
        5: "保留",
        6: "保留",
        7: "保留",
    }

    # DIR+PRM 组合映射
    DIR_PRM_MAP = {
        (0, 0): "客户机对服务器上报的响应",
        (0, 1): "客户机发起的请求",
        (1, 0): "服务器发起的上报",
        (1, 1): "服务器对客户机请求的响应",
    }

    def __init__(self):
        self.crc16 = crcmod.predefined.Crc('x-25')
        # 延迟导入 APDU 解析器，避免循环依赖
        self._apdu_parser = None

    @property
    def apdu_parser(self):
        if self._apdu_parser is None:
            from dl_t698_45_apdu_parser import DLT69845APDUParser
            self._apdu_parser = DLT69845APDUParser()
        return self._apdu_parser

    def _calc_crc(self, data: bytes) -> int:
        """计算 X-25 CRC16"""
        crc = self.crc16.new(data)
        return crc.crcValue

    def _parse_length(self, data: bytes, offset: int) -> Tuple[dict, int]:
        """解析长度域 L (2字节)

        Returns: (解析结果, 新偏移量)
        """
        if offset + 2 > len(data):
            raise ValueError("长度域数据不足")
        raw = data[offset:offset + 2]
        length_val = int.from_bytes(raw, 'little')
        unit = (length_val >> 14) & 0x01
        frame_data_len = length_val & 0x3FFF
        actual_len = frame_data_len * 1024 if unit else frame_data_len
        return {
            "原始字节": raw.hex().upper(),
            "长度值": actual_len,
            "单位": "千字节" if unit else "字节",
            "说明": f"bit0~13={frame_data_len}, bit14={unit}",
        }, offset + 2

    def _parse_control(self, byte: int) -> dict:
        """解析控制域 C (1字节)"""
        dir_bit = (byte >> 7) & 0x01
        prm_bit = (byte >> 6) & 0x01
        seg_bit = (byte >> 5) & 0x01
        sc_bit = (byte >> 3) & 0x01
        func_code = byte & 0x07
        return {
            "原始字节": f"0x{byte:02X}",
            "DIR": {"位": dir_bit, "说明": "传输方向", "解析": "客户机→服务器" if dir_bit == 0 else "服务器→客户机"},
            "PRM": {"位": prm_bit, "说明": "启动标志", "解析": "服务器发起" if prm_bit == 0 else "客户机发起"},
            "分帧标志": {"位": seg_bit, "说明": "分帧", "解析": "完整APDU" if seg_bit == 0 else "APDU片段"},
            "扰码标志": {"位": sc_bit, "说明": "扰码", "解析": "不加扰码" if sc_bit == 0 else "加扰码(+0x33)"},
            "功能码": {"值": func_code, "说明": self.FUNC_CODE_MAP.get(func_code, "保留")},
            "DIR+PRM": self.DIR_PRM_MAP.get((dir_bit, prm_bit), "未知"),
        }

    def _parse_address(self, data: bytes, offset: int) -> Tuple[dict, int]:
        """解析地址域 SA + CA

        SA = 地址特征(1B) + N字节地址
        CA = 1字节
        Returns: (解析结果, 新偏移量)
        """
        if offset >= len(data):
            raise ValueError("地址域数据不足")
        addr_feature = data[offset]
        addr_len = (addr_feature & 0x0F) + 1  # bit0~3: 0~15 -> 1~16字节
        logic_addr = (addr_feature >> 4) & 0x03
        addr_type = (addr_feature >> 6) & 0x03

        addr_type_map = {0: "单地址", 1: "通配地址", 2: "组地址", 3: "广播地址"}
        logic_desc = "无扩展逻辑地址"
        if logic_addr == 0:
            logic_desc = "逻辑地址0"
        elif logic_addr == 1:
            logic_desc = "逻辑地址1"
        elif logic_addr == 3:
            logic_desc = "有扩展逻辑地址(2~255)"

        # 广播地址固定1字节 = 0xAA
        if addr_type == 3:
            addr_len = 1

        sa_end = offset + 1 + addr_len
        if sa_end > len(data):
            raise ValueError("服务器地址数据不足")
        sa_bytes = data[offset + 1:sa_end]

        # CA
        ca_offset = sa_end
        if ca_offset >= len(data):
            raise ValueError("客户机地址数据不足")
        ca = data[ca_offset]

        sa_hex = sa_bytes.hex().upper()
        # 字节逆序后的十六进制（698.45地址传输规则：字节逆序）
        sa_reversed = sa_bytes[::-1].hex().upper()

        return {
            "地址特征": {
                "原始字节": f"0x{addr_feature:02X}",
                "地址长度": addr_len,
                "逻辑地址": logic_desc,
                "地址类型": addr_type_map.get(addr_type, "未知"),
            },
            "服务器地址SA": {
                "原始字节": sa_hex,
                "解析值": sa_reversed,
            },
            "客户机地址CA": {
                "原始字节": f"0x{ca:02X}",
                "值": ca,
                "说明": "不关注" if ca == 0 else f"客户机地址={ca}",
            },
        }, ca_offset + 1

    @staticmethod
    def _bcd_to_str(data: bytes) -> str:
        """将压缩BCD码转为字符串，AH/FH作为通配符"""
        chars = []
        for b in data:
            high = b >> 4
            low = b & 0x0F
            for nibble in (low, high):  # BCD: 低4位在前
                if nibble == 0x0A:
                    chars.append('A')
                elif nibble == 0x0F:
                    chars.append('F')
                else:
                    chars.append(str(nibble))
        # 去除前导零
        result = ''.join(chars)
        result = result.lstrip('0')
        return result if result else '0'

    def parse(self, frame_bytes: bytes) -> dict:
        """解析完整帧，返回嵌套字典

        Returns: {
            "帧头": {...},
            "长度域": {...},
            "控制域": {...},
            "地址域": {...},
            "帧头校验HCS": {...},
            "链路用户数据": {"原始字节": ..., "APDU": ...},
            "帧校验FCS": {...},
            "结束符": {...},
            "解析状态": "成功" / "失败",
            "错误信息": ...,
        }
        """
        result = {"解析状态": "成功", "原始数据": frame_bytes.hex().upper()}
        try:
            n = len(frame_bytes)
            if n < 8:
                raise ValueError(f"帧长度不足: {n} 字节")

            # 帧头
            if frame_bytes[0] != self.START_CHAR:
                raise ValueError(f"起始字符错误: 0x{frame_bytes[0]:02X}, 期望 0x68")
            result["帧头"] = {"起始字符": "0x68"}

            # 长度域
            length_info, offset = self._parse_length(frame_bytes, 1)
            result["长度域"] = length_info

            # 控制域
            ctrl = self._parse_control(frame_bytes[offset])
            result["控制域"] = ctrl
            ctrl_offset = offset
            offset += 1

            # 地址域
            addr, offset = self._parse_address(frame_bytes, offset)
            result["地址域"] = addr
            addr_end = offset

            # HCS (2字节)
            if offset + 2 > n:
                raise ValueError("HCS数据不足")
            hcs_raw = int.from_bytes(frame_bytes[offset:offset + 2], 'little')
            # HCS 覆盖范围: 长度域到地址域 (帧头部分, 不含起始字符和HCS本身)
            hcs_data = frame_bytes[1:addr_end]
            hcs_calc = self._calc_crc(hcs_data)
            hcs_ok = (hcs_raw == hcs_calc)
            result["帧头校验HCS"] = {
                "原始值": f"0x{hcs_raw:04X}",
                "计算值": f"0x{hcs_calc:04X}",
                "校验结果": "通过" if hcs_ok else "失败",
            }
            offset += 2

            # 链路用户数据 + FCS + 结束符
            remaining = n - offset - 3  # 减去 FCS(2) + 结束符(1)
            if remaining < 0:
                raise ValueError("链路用户数据不足")

            apdu_data = frame_bytes[offset:offset + remaining]
            result["链路用户数据"] = {
                "原始字节": apdu_data.hex().upper(),
                "长度": len(apdu_data),
            }
            offset += remaining

            # FCS
            fcs_raw = int.from_bytes(frame_bytes[offset:offset + 2], 'little')
            # FCS 覆盖范围: 长度域到链路用户数据 (整帧不含起始字符、结束字符和FCS本身)
            fcs_data = frame_bytes[1:offset]
            fcs_calc = self._calc_crc(fcs_data)
            fcs_ok = (fcs_raw == fcs_calc)
            result["帧校验FCS"] = {
                "原始值": f"0x{fcs_raw:04X}",
                "计算值": f"0x{fcs_calc:04X}",
                "校验结果": "通过" if fcs_ok else "失败",
            }
            offset += 2

            # 结束符
            if frame_bytes[offset] != self.END_CHAR:
                raise ValueError(f"结束字符错误: 0x{frame_bytes[offset]:02X}")
            result["结束符"] = {"结束字符": "0x16"}

            # 尝试解析 APDU
            if apdu_data:
                try:
                    apdu_result = self.apdu_parser.parse(apdu_data)
                    result["链路用户数据"]["APDU"] = apdu_result
                except Exception as e:
                    result["链路用户数据"]["APDU解析错误"] = str(e)

        except Exception as e:
            result["解析状态"] = "失败"
            result["错误信息"] = str(e)

        return result

    def parse_to_table(self, frame_bytes: bytes) -> list:
        """解析为 GUI 表格格式

        Returns: [(字段名, 原始值, 解析值, 说明, byte_start, byte_end), ...]
        """
        table_data = []
        result = self.parse(frame_bytes)
        n = len(frame_bytes)

        if result.get("解析状态") == "失败":
            table_data.append(("❌ 解析失败", "-", "-", result.get("错误信息", ""), None, None))
            table_data.append(("原始数据", result.get("原始数据", ""), "-", f"共{n}字节", None, None))
            return table_data

        # 帧头
        table_data.append(("起始字符", "0x68", "-", "帧起始标志", 0, 0))

        # 长度域
        ld = result["长度域"]
        table_data.append(("长度域", ld["原始字节"], str(ld["长度值"]),
                           f"{ld['说明']}, 单位={ld['单位']}", 1, 2))

        # 控制域
        ctrl = result["控制域"]
        table_data.append(("控制域", ctrl["原始字节"], "-", "", 3, 3))
        for k in ["DIR", "PRM", "分帧标志", "扰码标志", "功能码"]:
            v = ctrl[k]
            if k == "功能码":
                table_data.append((f"  {k}", str(v["值"]), v["说明"], "", 3, 3))
            else:
                table_data.append((f"  {k}", str(v["位"]), v["解析"], v["说明"], 3, 3))
        table_data.append(("  DIR+PRM", "-", ctrl["DIR+PRM"], "组合意义", 3, 3))

        # 地址域
        addr = result["地址域"]
        af = addr["地址特征"]
        table_data.append(("地址特征", af["原始字节"], "-",
                           f"长度={af['地址长度']}, {af['逻辑地址']}, {af['地址类型']}", 4, 4))
        sa = addr["服务器地址SA"]
        sa_len = len(sa["原始字节"].replace(" ", "")) // 2
        table_data.append(("服务器地址SA", sa["原始字节"], sa.get("解析值", "-"), f"{sa_len}字节", 5, 5 + sa_len - 1))
        ca = addr["客户机地址CA"]
        ca_pos = 5 + sa_len
        table_data.append(("客户机地址CA", ca["原始字节"], str(ca["值"]), ca["说明"], ca_pos, ca_pos))

        offset_after_addr = ca_pos + 1

        # HCS
        hcs = result["帧头校验HCS"]
        table_data.append(("帧头校验HCS", hcs["原始值"], hcs["计算值"], hcs["校验结果"],
                           offset_after_addr, offset_after_addr + 1))
        offset_after_addr += 2

        # 链路用户数据
        apdu = result["链路用户数据"]
        apdu_len = apdu["长度"]
        if apdu_len > 0:
            display = apdu["原始字节"][:64] + ("..." if apdu_len > 32 else "")
            table_data.append(("链路用户数据", display,
                               f"{apdu_len}字节", "APDU内容", offset_after_addr, offset_after_addr + apdu_len - 1))

            # APDU 详情
            apdu_result = apdu.get("APDU", {})
            if apdu_result:
                svc = apdu_result.get("APDU类型", "-")
                sub = apdu_result.get("子类型", "")
                status = apdu_result.get("解析状态", "-")
                status_desc = apdu_result.get("说明", "")
                table_data.append(("  APDU类型", apdu_result.get("服务码", "-"), svc, sub or status_desc or status, None, None))
                # 递归添加 APDU 字段 (即使解析状态不是成功也尝试显示)
                if apdu_result.get("解析状态") == "成功":
                    self._add_apdu_to_table(apdu_result, table_data, level=2)
                else:
                    # 显示原始数据或错误信息
                    err = apdu_result.get("错误信息", "")
                    if err:
                        table_data.append(("    解析错误", "-", err, "", None, None))
                    raw = apdu_result.get("原始数据", "")
                    if raw:
                        table_data.append(("    原始数据", raw[:64], f"{len(raw)//2}字节", "", None, None))
        offset_after_addr += apdu_len

        # FCS
        fcs = result["帧校验FCS"]
        table_data.append(("帧校验FCS", fcs["原始值"], fcs["计算值"], fcs["校验结果"],
                           offset_after_addr, offset_after_addr + 1))
        offset_after_addr += 2

        # 结束符
        table_data.append(("结束符", "0x16", "-", "帧结束标志", offset_after_addr, offset_after_addr))

        return table_data

    def _add_apdu_to_table(self, apdu_result: dict, table_data: list, level: int = 0):
        """递归添加 APDU 解析结果到表格"""
        indent = "  " * level
        skip_keys = {"APDU类型", "APDU说明", "服务码", "原始数据", "解析状态", "错误信息", "子类型码", "子类型", "tag", "tag_name"}

        for key, value in apdu_result.items():
            if key in skip_keys:
                continue
            if isinstance(value, dict):
                if "嵌套APDU" in value:
                    # 安全报文等包含嵌套APDU的数据：摘要显示一行，然后递归展开嵌套APDU
                    raw = value.get("原始值", "-")
                    length = value.get("长度", "-")
                    desc = f"长度={length}，包含嵌套APDU"
                    table_data.append((f"{indent}{key}", str(raw), f"{length}字节", desc, None, None))
                    self._add_apdu_to_table(value["嵌套APDU"], table_data, level + 1)
                elif "类型" in value and "解析值" in value:
                    # A-XDR 解码结果
                    raw = value.get("原始值", "-")
                    parsed = value.get("解析值", "-")
                    desc = value.get("说明", "")
                    semantic = value.get("语义说明", "")
                    if semantic:
                        desc = f"{desc} | {semantic}" if desc else semantic
                    if isinstance(parsed, dict):
                        parsed = str(parsed)
                    elif isinstance(parsed, list):
                        parsed = f"[{len(parsed)}项]"
                    table_data.append((f"{indent}{key}", str(raw), str(parsed), desc, None, None))
                elif "原始值" in value and "解析值" in value:
                    # 标准解码结果（安全类型、SecurityRequestVerifyType 等）横向显示为一行
                    raw = value.get("原始值", "-")
                    parsed = value.get("解析值", "-")
                    desc = value.get("说明", "")
                    if isinstance(parsed, dict):
                        parsed = str(parsed)
                    elif isinstance(parsed, list):
                        parsed = f"[{len(parsed)}项]"
                    table_data.append((f"{indent}{key}", str(raw), str(parsed), desc, None, None))
                elif "原始值" in value:
                    # 仅有原始值的数据（如 RN）横向显示为一行
                    raw = value.get("原始值", "-")
                    desc = value.get("说明", "")
                    table_data.append((f"{indent}{key}", str(raw), "-", desc, None, None))
                else:
                    table_data.append((f"{indent}{key}", "-", "-", "", None, None))
                    self._add_apdu_to_table(value, table_data, level + 1)
            elif isinstance(value, list):
                table_data.append((f"{indent}{key}", "-", f"[{len(value)}项]", "", None, None))
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        self._add_apdu_to_table(item, table_data, level + 1)
            else:
                table_data.append((f"{indent}{key}", str(value), "-", "", None, None))
