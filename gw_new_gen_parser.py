# -*- coding: utf-8 -*-
"""国网新一代双模通信互联互通技术规范 解析器

协议标准: Q/GDW 双模通信互联互通技术规范
- 第4-2部分：数据链路层通信协议
- 第4-3部分：应用层通信协议

帧结构:
  MPDU = FC(16B) + PB(物理块)
  PB   = PBH(1B) + MAC帧头 + MSDU + [ICV(CRC-32)] + [填充] + [PBCS(CRC-24)]
  FC   = 定界符类型 + 网络类型 + NID(16bit) + 保留 + 可变区域(68bit) + 版本号 + FCCS(24bit)
         (FCCS 为 FC 自身的24bit CRC校验, 其后直接为 PB, 无独立 HCS)
  MAC帧头 = 版本 + 源/目的TEI + 发送类型 + MSDU序列号 + MSDU类型 + MSDU长度 + ...
  应用层 = 报文端口号 + 报文ID(16bit) + 控制字 + 业务数据
"""
import re
import zlib
from typing import List, Tuple, Any, Optional

try:
    import crcmod
    _CRC24_MPDU_FUN = crcmod.mkCrcFun(0x1800063, initCrc=0x000000, rev=True, xorOut=0x000000)
except ImportError:
    _CRC24_MPDU_FUN = None
from gw_new_gen_cmd_payloads import parse_command_payload
from gw_new_gen_mme_parser import parse_management_message, parse_singlehop_msdu


class GWNewGenParser:
    """国网新一代双模通信互联互通协议解析器"""

    # ── 定界符类型 ─────────────────────────────────────────────
    DELIMITER_TYPES = {
        0: "信标帧",
        1: "SOF帧",
        2: "选择确认帧(SACK)",
        3: "网间协调帧",
    }

    # ── MSDU 类型 ──────────────────────────────────────────────
    MSDU_TYPES = {
        0: "网络管理消息",
        48: "应用层报文",
        49: "IP报文",
    }

    # ── 发送类型 ───────────────────────────────────────────────
    SEND_TYPES = {
        0: "单播",
        1: "全网广播",
        2: "本地广播",
        3: "代理广播",
    }

    # ── 广播方向 ───────────────────────────────────────────────
    BROADCAST_DIRS = {
        0: "双向广播",
        1: "下行广播(CCO→STA)",
        2: "上行广播(STA→CCO)",
    }

    # ── 应用层报文ID ──────────────────────────────────────────
    MSG_IDS = {
        0x0001: "终端主动抄表",
        0x0002: "路由主动抄表",
        0x0003: "终端主动并发抄表",
        0x0004: "校时",
        0x0005: "单相业务下发",
        0x0006: "通信测试",
        0x0008: "事件上报",
        0x0011: "查询从节点主动注册",
        0x0012: "启动从节点主动注册",
        0x0013: "停止从节点主动注册",
        0x0020: "确认/否认",
        0x0030: "开始升级",
        0x0031: "停止升级",
        0x0032: "传输文件数据",
        0x0033: "传输文件数据(单播转本地广播)",
        0x0034: "查询站点升级状态",
        0x0035: "执行升级",
        0x0036: "查询站点信息",
        0x0040: "抄控器CCO",
        0x0041: "抄控器数据透传串口转发",
        0x00A0: "鉴权安全",
        0x00A1: "台区户变关系识别",
        0x00A2: "查询ID信息",
        0x00A3: "精准校时",
        0x00A4: "配电信息上报",
        0x00E2: "分钟采集任务配置",
        0x00E3: "分钟采集任务数据读取",
        0x00E5: "多用户应用聚合帧",
    }

    # ── 报文端口号 ─────────────────────────────────────────────
    PORT_NAMES = {
        0x11: "抄表业务",
        0x12: "升级业务",
        0x1A: "鉴权安全",
    }

    # ── 规约类型 ───────────────────────────────────────────────
    PROTOCOL_TYPES = {
        0: "透明传输",
        1: "DL/T645—1997",
        2: "DL/T645—2007",
        3: "DL/T698.45",
    }

    # ── 标准版本号 ─────────────────────────────────────────────
    STANDARD_VERSIONS = {
        0: "HDC 1.0",
        1: "HDC 2.0",
    }

    # ── 链路标识符 ─────────────────────────────────────────────
    LINK_ID_MAP = {
        0x00: "管理",
        0x11: "高优先级数据",
        0x22: "普通数据",
    }

    # ── 单跳MAC帧头消息类型（HDC 2.0 / 4-2部分 表3） ────────────
    SINGLEHOP_MSG_TYPES = {
        0: "无线发现列表报文",
        1: "信道评估参数更新报文",
        2: "载波发现列表报文",
        128: "应用层报文",
        129: "IPV4报文",
    }

    # ── 单跳MAC帧头消息类型（HDC 1.0 旧版 / 12087.42-2020 表12） ─
    # 旧版仅定义: 0=发现列表消息, 1-127=保留, 128=应用层报文, 129=IPV4报文
    SINGLEHOP_MSG_TYPES_V1 = {
        0: "发现列表消息",
        128: "应用层报文",
        129: "IPV4报文",
    }

    def parse_to_table(self, frame_bytes: bytes, parse_level: str = "auto", **kwargs) -> List[Tuple]:
        """解析完整帧，返回表格数据

        Args:
            frame_bytes: 帧数据
            parse_level: 解析级别
                - "auto": 自动识别，完整解析 (FC + MAC + 应用层)
                - "fc_pb": 解析FC + 完整物理块PB (PBH 1B + MAC帧头 + MSDU)
                - "fc_only": 仅解析帧控制(FC)字段
                - "mac_only": 仅解析MAC帧（默认按SOF帧解析）
                - "pb_only": 仅解析物理块(PB)，需指定frame_type
                - "fc_mac": 解析FC + PB头(PBH 1B) + MAC帧头（不含应用层）
                - "app": 仅解析应用层报文
            frame_type: pb_only模式下的帧类型 (0=信标帧, 1=SOF帧, 2=ACK帧, 3=NET帧)

        Returns:
            [(field, raw, parsed, comment, byte_start, byte_end, is_child), ...]
        """
        data = frame_bytes
        offset = 0
        frame_type = kwargs.get('frame_type', None)
        # 标准版本号(0=HDC 1.0旧版, 1=HDC 2.0新一代)。FC模式下由字节12覆盖;
        # 无FC的模式(app/mac_only/pb_only)默认按HDC 2.0解析, 可由kwargs指定
        std_version = kwargs.get('std_version', 1)

        if len(data) < 2:
            return [("❌ 解析失败", "", "", "帧数据过短，无法解析", None, None, False)]

        # ── 直接网络管理消息：首字节即MMTYPE(2B大端) ──
        # 管理消息报文头(表42): MMTYPE(2B) + 保留(2B)。部分帧直接以管理消息输入。
        from gw_new_gen_mme_parser import MMETYPE_NAMES
        if len(data) >= 4 and ((data[0] << 8) | data[1]) in MMETYPE_NAMES:
            return self._parse_mgmt_if_direct(data, 0)

        # ── 应用层模式：输入即为应用层报文 ──
        if parse_level == "app":
            # 如果首字节是有效端口号，直接从偏移0解析
            known_ports = set(self.PORT_NAMES.keys())
            if len(data) >= 1 and data[0] in known_ports:
                return self._parse_application_layer(data, 0)
            # 若输入以MPDU FC帧头开头(可能带管理消息), 剥离FC后检测管理消息
            stripped, fc_off = self._strip_fc_prefix_if_present(data, [])
            if fc_off > 0:
                mm_result = self._parse_mgmt_if_direct(stripped, fc_off)
                if mm_result is not None:
                    return mm_result
                # 剥离FC后可能是PB+MAC或应用层, 交给后续逻辑
                data = stripped
            # 否则使用智能扫描定位应用层起始位置
            app_result = self._parse_msdu_from_frame(data, 0, std_version)
            if app_result:
                return app_result
            # 回退：强制从偏移0解析
            return self._parse_application_layer(data, 0)

        # ── 仅MAC帧模式：输入包含PB头+MAC帧头 ──
        if parse_level == "mac_only":
            result = []
            # 添加帧类型说明（默认SOF帧）
            result.append(("解析模式", "", "仅MAC帧", "默认按SOF帧结构解析", None, None, False))
            # 若输入以FC帧头开头(FCCS校验通过)或16字节前缀后为管理消息, 剥离FC
            data, fc_offset = self._strip_fc_prefix_if_present(data, result)
            # 剥离后若直接是网络管理消息(MMTYPE大端且保留字段为0), 直接按管理消息解析
            mm_result = self._parse_mgmt_if_direct(data, fc_offset)
            if mm_result is not None:
                result.extend(mm_result)
                return result
            # 先解析PB头，再解析MAC头
            pb_result = self._parse_pb_by_frame_type(data, 0, 1, std_version)  # 1=SOF帧
            if pb_result:
                # 剥离FC后行坐标整体偏移
                result.extend(self._shift_rows(pb_result, fc_offset))
            else:
                result.append(("❌ 解析失败", "", "", "MAC帧头解析失败，数据可能不完整", None, None, False))
            return result

        # ── 仅PB模式：输入即为物理块数据 ──
        if parse_level == "pb_only":
            result = []
            # 帧类型名称
            dt_names = {0: "信标帧", 1: "SOF帧", 2: "ACK帧(SACK)", 3: "NET帧"}
            dt_name = dt_names.get(frame_type, f"未知({frame_type})")
            result.append(("解析模式", "", f"仅PB - {dt_name}", f"帧类型={frame_type}", None, None, False))
            # 若输入以FC帧头开头(FCCS校验通过)或16字节前缀后为管理消息, 剥离FC
            data, fc_offset = self._strip_fc_prefix_if_present(data, result)
            # 剥离后若直接是网络管理消息(MMTYPE大端且保留字段为0), 直接按管理消息解析
            mm_result = self._parse_mgmt_if_direct(data, fc_offset)
            if mm_result is not None:
                result.extend(mm_result)
                return result
            # PB解析根据帧类型有所不同
            pb_result = self._parse_pb_by_frame_type(data, 0, frame_type, std_version)
            if pb_result:
                result.extend(self._shift_rows(pb_result, fc_offset))
            return result

        result = []

        # ── MPDU 帧控制 (FC) ──
        fc_result = self._parse_fc(data, offset)
        result.extend(fc_result)
        offset = 16  # FC 固定16字节

        # ── 仅FC解析模式 ──
        if parse_level == "fc_only":
            return result

        # ── 根据 FC 字节12 D[7:4] 标准版本号自动区分 HDC 1.0 / HDC 2.0 ──
        # 0=HDC 1.0(旧版双模) 1=HDC 2.0(新一代)。据此选择MAC帧头解析规则。
        std_version = (data[12] >> 4) & 0x0F if len(data) >= 13 else 1
        _ver_name = self.STANDARD_VERSIONS.get(std_version, f"保留({std_version})")
        result.append(("协议版本判定", f"FC[12] D[7:4]={std_version:04b}",
                        _ver_name, f"依据FC标准版本号自动选择 {_ver_name} 解析规则",
                        12, 13, False))

        # ── FC之后为 PB(物理块) = PBH(1B) + MAC帧头 + MSDU ──
        # FC 末3字节为 FCCS(FC自身校验), 其后直接为 PB, **无独立 HCS**
        if len(data) > offset:
            # FC+MAC模式：解析 PB头(PBH 1B) + MAC帧头（不含应用层MSDU）
            if parse_level == "fc_mac":
                fc_dt = data[0] & 0x07
                fc_src = fc_dst = -1
                if fc_dt == 1 and offset >= 7:
                    fc_src = data[4] | ((data[5] & 0x0F) << 8)
                    fc_dst = ((data[5] >> 4) & 0x0F) | (data[6] << 4)
                pbh_len, mac_off, _strong = self._locate_pbh_mac(
                    data, offset, fc_src, fc_dst)
                if mac_off < 0:
                    pbh_len, mac_off = 0, offset
                if pbh_len == 1:
                    result.append(self._pbh_row(data, offset))
                mac_result = self._parse_mac_header(data, mac_off, std_version)
                if mac_result:
                    result.extend(mac_result)
                return result

            # auto / fc_pb模式：完整解析 FC + PB(PBH 1B + MAC帧头 + MSDU)
            msdu_result = self._parse_msdu_from_frame(data, offset, std_version)
            result.extend(msdu_result)

        return result

    @staticmethod
    def _crc24_mpdu(data: bytes) -> int:
        """CRC-24: poly=0x1800063(反射), init=0, xorOut=0 (与南网csg解析器一致)

        用于FC帧头FCCS校验, 判定输入是否为完整MPDU帧。
        """
        if _CRC24_MPDU_FUN is not None:
            return _CRC24_MPDU_FUN(data)
        # 无crcmod时的等价实现(反射模式)
        crc = 0
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0x1800063
                else:
                    crc >>= 1
        return crc & 0xFFFFFF

    def _strip_fc_prefix_if_present(self, data: bytes, result: list) -> Tuple[bytes, int]:
        """若输入以MPDU帧控制(FC)头开头, 剥离16字节FC后返回(PB/MAC数据, 偏移)

        FC特征: 首字节 bit3=接入指示=1 且 bits0-2=定界符类型(0~3)。
        用于 mac_only/pb_only 解析级别: 用户可能直接粘贴完整MPDU帧。
        返回 (剥离后数据, 坐标偏移): 未剥离时偏移=0。
        """
        if len(data) >= 17:
            b0 = data[0]
            delimiter_type = b0 & 0x07
            # 剥离条件(任一):
            #  1. FCCS(前13字节CRC-24)校验通过 -> 确定性MPDU
            #  2. 16字节前缀后为网络管理消息(MMTYPE大端匹配且保留字段为0)
            if delimiter_type <= 3 and len(data) >= 16:
                after = data[16:]
                fcs_valid = False
                fcs_stored = int.from_bytes(data[13:16], 'little')
                fcs_calc = self._crc24_mpdu(data[:13])
                fcs_valid = (fcs_calc == fcs_stored)
                from gw_new_gen_mme_parser import MMETYPE_NAMES
                looks_like_mgmt = (
                    len(after) >= 4
                    and ((after[0] << 8) | after[1]) in MMETYPE_NAMES
                    and after[2] == 0 and after[3] == 0  # 保留字段必须为0
                )
                if fcs_valid or looks_like_mgmt:
                    fc_hex = ' '.join(f'{b:02X}' for b in data[:16])
                    result.append(("FC帧头", fc_hex, "16字节",
                                   "检测到MPDU帧控制头，自动剥离后解析PB/MAC",
                                   0, 15, False))
                    return data[16:], 16
        return data, 0

    def _parse_mgmt_if_direct(self, data: bytes, fc_offset: int):
        """若 data 以网络管理消息头(MMTYPE 2B大端)开头, 返回管理消息解析结果

        fc_offset: 已剥离的FC头字节数(0=未剥离), 用于行坐标对齐。
        返回解析行列表; 非管理消息返回 None。
        """
        from gw_new_gen_mme_parser import MMETYPE_NAMES
        if len(data) >= 4:
            mmtype = (data[0] << 8) | data[1]
            if mmtype in MMETYPE_NAMES:
                rows = parse_management_message(data, 0)
                if fc_offset:
                    rows = self._shift_rows(rows, fc_offset)
                return rows
        return None

    @staticmethod
    def _shift_rows(rows: list, offset: int) -> list:
        """将解析结果行的 byte_start/byte_end 整体偏移（剥离FC头后坐标对齐）"""
        if offset == 0:
            return rows
        shifted = []
        for row in rows:
            if len(row) >= 6 and row[4] is not None and row[5] is not None:
                s, e = row[4], row[5]
                if s >= 0 and e >= 0:
                    shifted_row = (row[0], row[1], row[2], row[3],
                                   s + offset, e + offset) + tuple(row[6:])
                    shifted.append(shifted_row)
                    continue
            shifted.append(row)
        return shifted

    def _parse_fc(self, data: bytes, offset: int) -> List[Tuple]:
        """解析MPDU帧控制(FC)字段 - 16字节"""
        result = []

        if len(data) < offset + 16:
            result.append(("帧控制(FC)", "", "", "FC字段不完整", None, None, False))
            return result

        fc = data[offset:offset + 16]
        fc_hex = " ".join(f"{b:02X}" for b in fc)

        # 总览
        result.append(("帧控制(FC)", fc_hex, f"{len(fc)}字节", "MPDU帧控制字段(16字节)",
                        offset, offset + 16, False))

        # 字节0: 定界符类型(3bit) + 网络类型(5bit)
        b0 = fc[0]
        dt = b0 & 0x07
        net_type = (b0 >> 3) & 0x1F
        dt_name = self.DELIMITER_TYPES.get(dt, f"保留({dt})")
        result.append(("  定界符类型", f"0x{b0:02X} D[2:0]={dt:03b}",
                        f"{dt} ({dt_name})", f"DT={dt}: {dt_name}",
                        offset, offset + 1, True))
        result.append(("  网络类型", f"D[7:3]={net_type:05b}",
                        str(net_type), "0=用电信息采集系统",
                        offset, offset + 1, True))

        # 字节1-2: 网络标识(NID) 16bit (小端: 低字节在前)
        nid = fc[1] | (fc[2] << 8)
        result.append(("  网络标识(NID)", f"{fc[1]:02X} {fc[2]:02X}",
                        str(nid), f"0x{nid:04X} (1~65535, 小端)",
                        offset + 1, offset + 3, True))

        # 字节3: 保留
        result.append(("  保留", f"0x{fc[3]:02X}", "", "保留字段",
                        offset + 3, offset + 4, True))

        # 字节4-11(+字节12低4位): 可变区域 (68bit)
        vf = fc[4:12]
        vf_hex = " ".join(f"{b:02X}" for b in vf)
        result.append(("  可变区域(VF)", vf_hex, f"{len(vf)}字节", "68bit 可变区域",
                        offset + 4, offset + 12, True))
        # 按定界符类型细分可变区域字段(表5/表7/表9/表14)
        result.extend(self._parse_fc_vf(fc, dt, offset))

        # 字节12: 标准版本号(高4bit) + 保留(低4bit)
        b12 = fc[12]
        version = (b12 >> 4) & 0x0F
        ver_name = self.STANDARD_VERSIONS.get(version, f"保留({version})")
        result.append(("  标准版本号", f"0x{b12:02X} D[7:4]={version:04b}",
                        f"{version} ({ver_name})", f"版本: {ver_name}",
                        offset + 12, offset + 13, True))

        # 字节13-15: 帧控制校验序列(FCCS) 24bit CRC (小端: 低字节在前)
        fccs = fc[13] | (fc[14] << 8) | (fc[15] << 16)
        result.append(("  FCCS校验序列", f"{fc[13]:02X} {fc[14]:02X} {fc[15]:02X}",
                        f"0x{fccs:06X}", "24bit CRC校验(小端)",
                        offset + 13, offset + 16, True))

        return result

    # ── 频段标识映射（4-2部分 表7/表9/表12） ─────────────────
    _FC_BANDS = {
        0: "1.953~11.96MHz", 1: "2.441~5.615MHz", 2: "0.781~2.930MHz", 3: "保留",
        4: "0.781~5.615MHz", 5: "0.781~11.96MHz", 6: "6.08~11.962MHz", 7: "保留",
    }

    def _parse_fc_vf(self, fc: bytes, dt: int, offset: int) -> List[Tuple]:
        """按定界符类型解析FC可变区域（字节4-11 + 字节12低4位，共68bit）

        dt=0: 信标帧(表5)  dt=1: SOF帧(数据帧表7/信道探测帧表9)
        dt=2: 选择确认帧(表14)  dt=3: 网间协调帧(表17)
        组合字段均为小端: 前字节=低位, 后字节=高位
        """
        rows = []
        b = fc
        bands = self._FC_BANDS

        def add(name, raw, parsed, desc, s, e):
            rows.append(("    " + name, raw, parsed, desc, offset + s, offset + e, True))

        if dt == 0:
            # ── 表5 信标帧 ──
            ts = b[4] | (b[5] << 8) | (b[6] << 16) | (b[7] << 24)
            add("信标时间戳", " ".join(f"{x:02X}" for x in b[4:8]), f"0x{ts:08X} ({ts})",
                "网络基准时间(小端)", 4, 8)
            src = b[8] | ((b[9] & 0x0F) << 8)
            add("源TEI", f"{b[8]:02X} {b[9]:02X}", str(src),
                "发送信标站点的TEI(12bit小端)", 8, 10)
            div = (b[9] >> 4) & 0x0F
            add("分集拷贝模式", f"{div}", str(div), "信标帧分集拷贝基本模式", 9, 10)
            sym = b[10] | ((b[11] & 0x01) << 8)
            add("符号数", f"{sym}", str(sym), "信标数据载荷OFDM符号数(9bit)", 10, 12)
            phase = (b[11] >> 1) & 0x03
            phase_name = {0: "未知相线", 1: "A相线", 2: "B相线", 3: "C相线"}[phase]
            add("相线", f"{phase}", phase_name, "信标发送目的相线", 11, 12)
            fch = (b[11] >> 3) & 0x03
            fch_name = {0: "短FCH", 1: "标准FCH", 2: "长FCH", 3: "保留"}[fch]
            add("FCH符号数", f"{fch}", fch_name, "帧控制符号长度", 11, 12)
        elif dt == 1:
            ftype = b[7] & 0x07
            src = b[4] | ((b[5] & 0x0F) << 8)
            dst = ((b[5] >> 4) & 0x0F) | (b[6] << 4)
            add("源TEI", f"{b[4]:02X} {b[5]:02X}", str(src),
                "源设备站点TEI(12bit小端)", 4, 6)
            add("目的TEI", f"{b[5]:02X} {b[6]:02X}", str(dst),
                "目的设备站点TEI(12bit小端)", 5, 7)
            ftype_names = {0: "数据帧", 1: "信道探测帧", 2: "OFDMA下行帧", 3: "TDA下行帧"}
            ft_name = ftype_names.get(ftype, f"保留({ftype})")
            add("帧类型", f"{ftype}", ft_name, "SOF帧子类型", 7, 8)
            if ftype == 0:
                # ── 表7 数据帧 ──
                tf_pos = (b[7] >> 3) & 0x03
                tf_pos_name = {0: "不携带TF", 1: "数据载荷之前", 2: "数据载荷之后"}.get(tf_pos, "保留")
                add("TF符号位置", f"{tf_pos}", tf_pos_name, "", 7, 8)
                tf_num = (b[7] >> 5) & 0x07
                tf_num_name = {1: "4", 2: "6", 3: "8", 4: "10", 5: "12"}.get(tf_num, "保留")
                add("TF符号数", f"{tf_num}", tf_num_name, "TF部分符号个数", 7, 8)
                fl = b[8] | ((b[9] & 0x0F) << 8)
                add("帧长(FL)", f"{fl}", str(fl), "数据帧占用信道时长(12bit小端)", 8, 10)
                fch = ((b[9] >> 7) & 0x01) | ((b[10] & 0x01) << 1)
                fch_name = {0: "短FCH", 1: "标准FCH", 2: "长FCH", 3: "保留"}[fch]
                add("FCH符号数", f"{fch}", fch_name, "帧控制符号长度", 9, 11)
                mod = (b[10] >> 1) & 0x01
                add("调制方式", f"{mod}", "动态加载模式" if mod else "分集拷贝模式",
                    "数据载荷调制方式标识", 10, 11)
                tmi = (b[10] >> 2) & 0x1F
                add("调制参数", f"{tmi}", str(tmi),
                    "分集拷贝:TMI编号 / 动态加载:物理块类型编号", 10, 11)
                pb = (((b[10] >> 7) & 0x01) | ((b[11] & 0x01) << 1)) + 1
                add("PB物理块个数", f"{pb}", f"{pb}个", "数据载荷物理块个数", 10, 12)
                bcast = (b[11] >> 1) & 0x01
                add("广播标志", f"{bcast}", "广播报文" if bcast else "非广播报文", "", 11, 12)
                add("加密标志", f"{(b[11] >> 2) & 0x01}", "", "链路层加密机制预留", 11, 12)
                retx = (b[11] >> 3) & 0x01
                add("重传标志", f"{retx}", "重传报文" if retx else "非重传报文", "", 11, 12)
                band = (b[11] >> 4) & 0x07
                add("频段标识", f"{band}", bands[band], "TF与数据载荷频段标识(3bit)", 11, 12)
                gain = ((b[11] >> 7) & 0x01) | ((b[12] & 0x07) << 1)
                add("数据载荷增益", f"{gain}", f"{1.0 + gain * 0.0625:.4f}",
                    "动态加载增益配置值", 11, 13)
            elif ftype == 1:
                # ── 表9 信道探测帧 ──
                grp = (b[7] >> 3) & 0x03
                grp_name = {0: "4个", 1: "6个", 2: "8个", 3: "12个"}[grp]
                add("子载波分组", f"{grp}", grp_name + "子载波一组", "信道探测反馈最小分组", 7, 8)
                tf_num = (b[7] >> 5) & 0x07
                tf_num_name = {1: "4", 2: "6", 3: "8", 4: "10", 5: "12"}.get(tf_num, "保留")
                add("TF符号数", f"{tf_num}", tf_num_name, "基于探测结果的数据帧TF符号长度", 7, 8)
                fl = b[8] | ((b[9] & 0x0F) << 8)
                add("帧长", f"{fl}", str(fl), "占用信道时长(12bit小端)", 8, 10)
                fch = (b[9] >> 4) & 0x03
                fch_name = {0: "短FCH", 1: "标准FCH", 2: "长FCH", 3: "保留"}[fch]
                add("FCH符号数", f"{fch}", fch_name, "帧控制符号长度", 9, 10)
                band = (((b[9] >> 6) & 0x03) | ((b[10] & 0x01) << 2)) & 0x07
                add("训练序列频段标识", f"{band}", bands[band], "探测占用频段(3bit)", 9, 11)
                probe_sym = (b[10] >> 1) & 0x7F
                add("探测序列符号数", f"{probe_sym}", f"{(probe_sym + 1) * 2}", "(配置值+1)*2", 10, 11)
                ext_dst = b[11] | ((b[12] & 0x0F) << 8)
                add("扩展目的TEI", f"{b[11]:02X}", str(ext_dst),
                    "信道探测扩展目的节点TEI(12bit小端)", 11, 13)
            else:
                add("可变区域原始数据", " ".join(f"{x:02X}" for x in b[7:13]),
                    ft_name, "OFDMA/TDA下行帧可变区域(表10/表12)", 7, 13)
        elif dt == 2:
            # ── 表14 选择确认帧(不反馈SNR) ──
            src = b[5] | ((b[6] & 0x0F) << 8)
            dst = ((b[6] >> 4) & 0x0F) | (b[7] << 4)
            add("源TEI", f"{b[5]:02X} {b[6]:02X}", str(src),
                "发送选择确认帧站点TEI(12bit小端)", 5, 7)
            add("目的TEI", f"{b[6]:02X} {b[7]:02X}", str(dst),
                "接收选择确认帧站点TEI(12bit小端)", 6, 8)
            remain_cnt = b[8] & 0x03
            add("剩余站点数", f"{remain_cnt}", str(remain_cnt), "待确认剩余站点数", 8, 9)
            add("站点负载", f"{b[10]}", str(b[10]), "源站点未发送缓存报文数量", 10, 11)
        else:
            # dt=3 网间协调帧(表17)及其他: 原始显示
            add("可变区域原始数据", " ".join(f"{x:02X}" for x in b[4:13]), "",
                "网间协调帧可变区域(表17)", 4, 13)
        return rows

    def _locate_msdu_icv(self, data: bytes, msdu_start: int) -> int:
        """用CRC-32定位MSDU末尾ICV(小端)的起始位置, 未找到返回-1

        ICV = crc32(MSDU), 小端存储, 紧随MSDU之后(4-2部分: 不含MAC帧头)
        """
        end_limit = min(len(data) - 3, msdu_start + 2000)
        for end in range(msdu_start + 8, end_limit):
            if zlib.crc32(data[msdu_start:end]) & 0xFFFFFFFF == \
                    int.from_bytes(data[end:end + 4], 'little'):
                return end
        return -1

    def _make_pb_tail_rows(self, data: bytes, icv_start: int) -> List[Tuple]:
        """生成MSDU之后的链路层行: ICV + 物理块填充 + PBCS(CRC-24)"""
        rows = []
        icv = data[icv_start:icv_start + 4]
        icv_val = int.from_bytes(icv, 'little')
        rows.append(("完整性校验(ICV)", " ".join(f"{x:02X}" for x in icv),
                      f"0x{icv_val:08X} 校验通过", "MSDU的CRC-32(小端, 不含MAC帧头)",
                      icv_start, icv_start + 4, False))
        tail_start = icv_start + 4
        remain = len(data) - tail_start
        if remain > 3:
            pad = data[tail_start:len(data) - 3]
            pad_hex = " ".join(f"{x:02X}" for x in pad[:16])
            if len(pad) > 16:
                pad_hex += " ..."
            rows.append(("物理块填充", pad_hex, f"{len(pad)}字节", "物理块填充字节",
                          tail_start, len(data) - 3, False))
            remain = 3
        if remain == 3:
            pbcs = data[len(data) - 3:]
            pbcs_val = int.from_bytes(pbcs, 'little')
            rows.append(("PBCS(CRC-24)", " ".join(f"{x:02X}" for x in pbcs),
                          f"0x{pbcs_val:06X}", "物理块校验序列(24bit CRC, 小端)",
                          len(data) - 3, len(data), False))
        elif remain > 0:
            tail = data[tail_start:]
            rows.append(("尾部数据", " ".join(f"{x:02X}" for x in tail),
                          f"{len(tail)}字节", "ICV之后的尾部字节",
                          tail_start, len(data), False))
        return rows

    def _pbh_row(self, data: bytes, off: int) -> Tuple:
        """生成物理块头(PBH, 1字节)行: D[5:0]=序列号 D6=帧起始 D7=帧结束"""
        pbh = data[off]
        return ("物理块头(PBH)", f"{pbh:02X}",
                f"序列号={pbh & 0x3F} 起始={(pbh >> 6) & 1} 结束={(pbh >> 7) & 1}",
                "SOF帧物理块头: D[5:0]=序列号 D6=帧起始 D7=帧结束",
                off, off + 1, False)

    def _locate_pbh_mac(self, data: bytes, fc_end: int,
                        fc_src: int, fc_dst: int) -> Tuple[int, int, bool]:
        """定位 FC 之后的 PB 结构: PBH(1B) + MAC帧头

        完整帧格式 = FC(16B) + PB(PBH 1B + MAC帧头 + MSDU)。
        FC 末3字节为 FCCS(FC自身校验), **无独立 HCS**。
        返回 (pbh_len, mac_off, strong):
          pbh_len ∈ {0,1}; mac_off<0 表示未找到有效MAC;
          strong 表示标准MAC的原始源/目的TEI与FC强匹配(SOF帧有效)。
        优先假设含1字节PBH(SOF标准形式), 其次无PBH。
        """
        data_end = len(data)
        weak_v0 = -1  # version==0(标准MAC) 弱候选的 pbh_len
        weak_v1 = -1  # version==1(单跳MAC) 弱候选的 pbh_len
        for pbh_len in (1, 0):
            mac_off = fc_end + pbh_len
            if mac_off + 4 > data_end:
                continue
            version = data[mac_off] & 0x0F
            if version == 0:
                src = ((data[mac_off] >> 4) & 0x0F) | (data[mac_off + 1] << 4)
                dst = data[mac_off + 2] | ((data[mac_off + 3] & 0x0F) << 8)
                if (fc_src >= 0 and src == fc_src) or (fc_dst >= 0 and dst == fc_dst):
                    return (pbh_len, mac_off, True)  # TEI强匹配
                if weak_v0 < 0:
                    weak_v0 = pbh_len
            elif version == 1 and weak_v1 < 0:
                weak_v1 = pbh_len
        # 优先级: 强匹配(已返回) > 标准MAC(version0) > 单跳MAC(version1)
        if weak_v0 >= 0:
            return (weak_v0, fc_end + weak_v0, False)
        if weak_v1 >= 0:
            return (weak_v1, fc_end + weak_v1, False)
        return (0, -1, False)

    def _parse_msdu_from_frame(self, data: bytes, offset: int, std_version: int = 1) -> List[Tuple]:
        """从帧数据中定位并解析MSDU

        完整帧格式: FC(16B) + PB(物理块), 物理块 = PBH(1B) + MAC帧头 + MSDU。
        FC 末3字节为 FCCS(FC自身校验序列), 其后直接为 PB, **无独立 HCS**。
        FC(16B) 之后的结构可能有多种形式：
          形式1: PBH(1B) + MAC帧头 + 应用层/网管消息 (SOF标准帧)
          形式2: MAC帧头 + 应用层 (无PBH)
          形式3: 直接应用层 (无PBH/无MAC帧头)
          形式4: PBH(1B) + 应用层 (无MAC帧头)
        使用多级验证定位应用层/MAC帧头起始位置。
        """
        result = []
        fc_end = offset  # FC结束位置 = 16
        data_end = len(data)

        if fc_end >= data_end:
            return result

        # FC 源/目的TEI(仅SOF帧dt=1可靠): 用于 MAC帧头定位的强校验
        fc_dt = data[0] & 0x07
        fc_src = fc_dst = -1
        if fc_dt == 1 and fc_end >= 7:
            fc_src = data[4] | ((data[5] & 0x0F) << 8)
            fc_dst = ((data[5] >> 4) & 0x0F) | (data[6] << 4)

        # ── 智能定位应用层起始位置 ──
        # 策略: 扫描并严格验证 (端口号 + 报文ID + 控制字 + 业务数据头)
        known_ports = set(self.PORT_NAMES.keys())  # {0x11, 0x12, 0x1A}
        known_msg_ids = set(self.MSG_IDS.keys())
        app_offset = -1

        scan_end = min(data_end - 4, fc_end + 60)  # 至少需要4字节应用层头
        for i in range(fc_end, scan_end):
            port = data[i]
            if port not in known_ports:
                continue
            # 需要至少 port(1) + msg_id(2) + control(1) + 业务数据(2)
            if i + 6 > data_end:
                continue
            msg_id = data[i + 1] | (data[i + 2] << 8)
            msg_base = msg_id & 0x0FFF
            if msg_base not in known_msg_ids and msg_id not in known_msg_ids:
                continue
            # ── 严格验证：控制字应为0 ──
            control = data[i + 3]
            if control != 0x00:
                continue
            # ── 严格验证：业务数据头 ──
            # 字节0: 协议版本(bits5:0)应为1, 报文头长度高2位(bits7:6)
            # 字节1: 报文头长度低4位(bits3:0) + 其他控制位
            biz_b0 = data[i + 4]
            biz_version = biz_b0 & 0x3F
            if biz_version != 1:
                continue
            hdr_len_high = (biz_b0 >> 6) & 0x03
            hdr_len_low = data[i + 5] & 0x0F
            # 报文头长度(6bit, 小端组合): 低2位在前, 高4位在后
            hdr_len = hdr_len_high | (hdr_len_low << 2)
            # 报文头长度应为合理值 (4~64)
            if hdr_len < 4 or hdr_len > 64:
                continue
            # ── 数据长度合理性检查（仅排除明显异常值） ──
            # 数据长度(8bit) = payload[3]低4位(高位) << 4 | payload[2]低4位(低位)
            # 最大值255，不再检查是否超出剩余字节（帧可能被截断）
            # 通过所有验证
            app_offset = i
            break

        if app_offset >= 0:
            # ── 解析 FC 与 应用层 之间的区域: PBH(1B) + MAC帧头 ──
            if app_offset > fc_end:
                gap = app_offset - fc_end
                # 完整帧: FC 之后为 PB(PBH 1B + MAC + MSDU), 先定位 PBH+MAC
                pbh_len, mac_off, _strong = self._locate_pbh_mac(
                    data, fc_end, fc_src, fc_dst)
                if gap == 1:
                    # 仅 1 字节: SOF帧物理块头(PBH) + 应用层(无MAC帧头)
                    # MAC帧头最少4字节, gap==1 时 FC 后不可能有MAC头, 0x00 必为 PBH
                    result.append(self._pbh_row(data, fc_end))
                elif 0 <= mac_off < app_offset:
                    if pbh_len == 1:
                        result.append(self._pbh_row(data, fc_end))
                    result.extend(self._parse_mac_header(data, mac_off, std_version))
                else:
                    gap_data = data[fc_end:app_offset]
                    gap_hex = " ".join(f"{b:02X}" for b in gap_data)
                    result.append(("链路层间隙数据", gap_hex, f"{gap}字节",
                                    "PBH/MAC帧头",
                                    fc_end, app_offset, False))

            # ── 解析应用层 ──
            direction = 0  # 默认下行
            # 用ICV(CRC-32)定位MSDU结束位置，截断应用层数据，避免ICV/填充/PBCS混入业务数据
            icv_start = self._locate_msdu_icv(data, app_offset)
            if icv_start > 0:
                app_result = self._parse_application_layer(data[:icv_start], app_offset, direction)
                result.extend(app_result)
                result.extend(self._make_pb_tail_rows(data, icv_start))
            else:
                app_result = self._parse_application_layer(data, app_offset, direction)
                result.extend(app_result)
        else:
            # 未找到应用层(如网管消息): 完整帧 FC + PB(PBH 1B + MAC + MSDU)
            # FC 末3字节为FCCS(FC自身校验), 其后直接为 PBH+MAC, 无独立HCS
            # ── FC后直接为网络管理消息(表42: MMTYPE 2B大端 + 保留2B) ──
            # 部分帧 FC 后无 PBH/MAC 头，直接承载管理消息(如无线信道冲突上报)
            from gw_new_gen_mme_parser import MMETYPE_NAMES
            if fc_end + 4 <= data_end:
                direct_mmtype = (data[fc_end] << 8) | data[fc_end + 1]
                if direct_mmtype in MMETYPE_NAMES:
                    result.extend(parse_management_message(
                        data[:data_end], fc_end))
                    return result
            pbh_len, mac_off, _strong = self._locate_pbh_mac(
                data, fc_end, fc_src, fc_dst)
            if mac_off < 0:
                pbh_len, mac_off = 0, fc_end  # 未找到时退化: MAC紧跟FC
            if pbh_len == 1:
                result.append(self._pbh_row(data, fc_end))
            msdu_start = mac_off

            mac_result = self._parse_mac_header(data, msdu_start, std_version)
            if mac_result:
                result.extend(mac_result)
                mac_header_len = self._get_mac_header_length(data, msdu_start)
                if mac_header_len > 0 and msdu_start + mac_header_len < data_end:
                    app_start = msdu_start + mac_header_len
                    app_port = data[app_start]
                    if app_port in known_ports:
                        app_result = self._parse_application_layer(data, app_start, 0)
                        result.extend(app_result)
                    else:
                        # 非应用层: 检查MSDU类型, 网络管理消息按表42/43解析
                        # MPDU尾部含FCS(4B), MSDU结尾按 data_end-4 估算
                        m_ver = data[msdu_start] & 0x0F
                        if m_ver == 1:
                            m_msdu_type = data[msdu_start + 1]
                            mme_result = parse_singlehop_msdu(
                                data[:max(app_start, data_end - 4)], app_start, m_msdu_type)
                            if mme_result:
                                result.extend(mme_result)
                        else:
                            m_msdu_type = data[msdu_start + 7] if msdu_start + 7 < data_end else -1
                            if m_msdu_type == 0:
                                mme_result = parse_management_message(
                                    data[:max(app_start, data_end - 4)], app_start)
                                if mme_result:
                                    result.extend(mme_result)
            else:
                # 无MAC帧头，尝试直接解析应用层
                if fc_end < data_end and data[fc_end] in known_ports:
                    app_result = self._parse_application_layer(data, fc_end, 0)
                    result.extend(app_result)

        return result

    def _parse_mac_header(self, data: bytes, offset: int, std_version: int = 1) -> List[Tuple]:
        """解析MAC帧头（按版本字段分发）

        依据《双模通信互联互通技术规范 第4-2部分》:
        - 字节0 D[3:0] = 版本: 0=标准帧协议(表2, 16字节) 1=单跳帧协议(表3, 4字节)
        - std_version: FC标准版本号 0=HDC 1.0 1=HDC 2.0, 决定部分字段语义
        """
        if len(data) < offset + 1:
            return []
        version = data[offset] & 0x0F
        if version == 1:
            return self._parse_mac_singlehop_header(data, offset, std_version)
        return self._parse_mac_std_header(data, offset, std_version)

    def _parse_mac_std_header(self, data: bytes, offset: int, std_version: int = 1) -> List[Tuple]:
        """解析标准MAC帧头（4-2部分 表2: 16字节固定域）

        MAC地址标志=1时，帧头后追加原始源MAC(6B)+原始目的MAC(6B)共12字节。
        位域规则: LSB-first位编号，跨字节字段小端序组合（低字节在前）。
        std_version: 0=HDC 1.0旧版(聚合帧标志/发送帧序号/链路标识符均为保留)
                     1=HDC 2.0新一代(启用上述3处新增字段)。
        """
        result = []
        start = offset

        # 固定头长度: 文档表2=16字节(字节14保留+字节15链路标识符);
        # 部分实际设备=15字节(无保留字节, 字节14链路标识符)。用ICV自动判别
        # guard 按最大 fixed=16 对齐（_detect_std_fixed_len 数据不足时默认返回16）
        if len(data) < offset + 16:
            return result

        fixed = self._detect_std_fixed_len(data, offset)

        b = data[offset:offset + fixed]
        version = b[0] & 0x0F
        src_tei = ((b[0] >> 4) & 0x0F) | (b[1] << 4)      # 12bit: 字节0高4位=低4位, 字节1=高8位
        dst_tei = b[2] | ((b[3] & 0x0F) << 8)             # 12bit: 字节2=低8位, 字节3低4位=高4位
        send_type = (b[3] >> 4) & 0x0F
        send_limit = b[4] & 0x1F
        agg_flag = (b[4] >> 5) & 0x01
        msdu_seq = b[5] | (b[6] << 8)                     # 16bit 小端
        msdu_type = b[7]
        msdu_len = b[8] | ((b[9] & 0x07) << 8)            # 11bit
        restart_cnt = (b[9] >> 3) & 0x0F
        proxy_flag = (b[9] >> 7) & 0x01
        total_hops = b[10] & 0x0F
        remain_hops = (b[10] >> 4) & 0x0F
        broadcast_dir = b[11] & 0x03
        path_repair = (b[11] >> 2) & 0x01
        mac_addr_flag = (b[11] >> 3) & 0x01
        frame_seq = ((b[11] >> 4) & 0x0F) | (b[12] << 4)  # 12bit
        net_seq = b[13]
        # fixed=16: 字节14保留, 字节15链路标识符; fixed=15: 字节14链路标识符
        link_id = b[fixed - 1]

        hdr_len = fixed + (12 if mac_addr_flag else 0)
        _ver_tag = self.STANDARD_VERSIONS.get(std_version, f"保留({std_version})")
        hdr_note = f"标准帧协议 版本={version} 共{hdr_len}字节 [{_ver_tag}]"
        if fixed == 15:
            hdr_note += " (固定头15字节, 无保留字节, ICV校验确认)"
        result.append(("MAC帧头(标准)", "", "", hdr_note,
                        start, start + hdr_len, False))
        result.append(("  版本", f"0x{b[0]:02X} D[3:0]={version:04b}",
                        str(version), "0=标准帧协议 1=单跳帧协议",
                        start, start + 1, True))
        result.append(("  原始源TEI", f"0x{src_tei:03X}",
                        str(src_tei), "最初产生MSDU的源终端TEI(12bit)",
                        start, start + 2, True))
        result.append(("  原始目的TEI", f"0x{dst_tei:03X}",
                        str(dst_tei), "MSDU最终目的终端TEI(12bit)",
                        start + 2, start + 4, True))

        send_name = self.SEND_TYPES.get(send_type, f"保留({send_type})")
        result.append(("  发送类型", f"D[7:4]={send_type:04b} ({send_name})",
                        str(send_type), send_name,
                        start + 3, start + 4, True))
        result.append(("  发送次数限值", str(send_limit), str(send_limit),
                        "报文最大发送次数(5bit)",
                        start + 4, start + 5, True))
        if std_version == 0:
            result.append(("  保留(D5)", str(agg_flag), "",
                            "HDC 1.0保留(HDC 2.0为聚合MAC帧标志)",
                            start + 4, start + 5, True))
        else:
            result.append(("  聚合MAC帧标志", str(agg_flag),
                            "聚合帧" if agg_flag else "非聚合帧",
                            "0=非聚合 1=聚合多个MAC帧",
                            start + 4, start + 5, True))
        result.append(("  MSDU序列号", f"0x{msdu_seq:04X}", str(msdu_seq),
                        "递增序列号(16bit小端)", start + 5, start + 7, True))
        msdu_type_name = self.MSDU_TYPES.get(msdu_type, f"保留({msdu_type})")
        result.append(("  MSDU类型", f"0x{msdu_type:02X} ({msdu_type_name})",
                        str(msdu_type), msdu_type_name,
                        start + 7, start + 8, True))
        result.append(("  MSDU长度", f"{msdu_len}字节", str(msdu_len),
                        "MSDU载荷长度(11bit)",
                        start + 8, start + 10, True))
        result.append(("  重启次数", f"{restart_cnt}", str(restart_cnt),
                        "站点重启次数(0-15)",
                        start + 9, start + 10, True))
        result.append(("  代理主路径", f"{proxy_flag}", str(proxy_flag),
                        "0=未启用 1=使用代理主路径",
                        start + 9, start + 10, True))

        bd_name = self.BROADCAST_DIRS.get(broadcast_dir, f"保留({broadcast_dir})")
        result.append(("  路由总跳数", f"{total_hops}", str(total_hops), "D[3:0]",
                        start + 10, start + 11, True))
        result.append(("  路由剩余跳数", f"{remain_hops}", str(remain_hops), "D[7:4]",
                        start + 10, start + 11, True))
        result.append(("  广播方向", f"D[1:0]={broadcast_dir:02b} ({bd_name})", str(broadcast_dir), bd_name,
                        start + 11, start + 12, True))
        result.append(("  路径修复标志", f"{path_repair}", str(path_repair), "0=未触发 1=已触发",
                        start + 11, start + 12, True))
        result.append(("  MAC地址标志", f"{mac_addr_flag}", str(mac_addr_flag), "0=未携带 1=帧头后携带MAC地址",
                        start + 11, start + 12, True))
        if std_version == 0:
            result.append(("  保留(帧序号位)", f"0x{frame_seq:03X}", "",
                            "HDC 1.0保留(HDC 2.0为发送帧序号)",
                            start + 11, start + 13, True))
        else:
            result.append(("  发送帧序号", f"0x{frame_seq:03X}", str(frame_seq),
                            "用于统计成功率(12bit)",
                            start + 11, start + 13, True))
        result.append(("  组网序列号", f"0x{net_seq:02X}", str(net_seq), "CCO重新组网后+1",
                        start + 13, start + 14, True))
        if std_version == 0:
            result.append(("  保留(链路标识位)", f"0x{link_id:02X}", "",
                            "HDC 1.0保留(HDC 2.0为链路标识符)",
                            start + fixed - 1, start + fixed, True))
        else:
            link_name = self.LINK_ID_MAP.get(link_id, f"0x{link_id:02X}")
            result.append(("  链路标识符", f"0x{link_id:02X} ({link_name})",
                            str(link_id), "0x00=管理 0x11=高优先级数据 0x22=普通数据",
                            start + fixed - 1, start + fixed, True))

        # MAC地址标志=1: 固定头之后=原始源MAC(6B)+原始目的MAC(6B)
        if mac_addr_flag and len(data) >= offset + fixed + 12:
            src_mac = data[offset + fixed:offset + fixed + 6]
            dst_mac = data[offset + fixed + 6:offset + fixed + 12]
            src_mac_str = " ".join(f"{x:02X}" for x in src_mac)
            dst_mac_str = " ".join(f"{x:02X}" for x in dst_mac)
            result.append(("  原始源MAC地址", src_mac_str, src_mac_str, "最初产生MSDU站点的MAC",
                            start + fixed, start + fixed + 6, True))
            result.append(("  原始目的MAC地址", dst_mac_str, dst_mac_str, "MSDU最终目的站点的MAC",
                            start + fixed + 6, start + fixed + 12, True))

        return result

    def _parse_mac_singlehop_header(self, data: bytes, offset: int, std_version: int = 1) -> List[Tuple]:
        """解析单跳MAC帧头（4-2部分 表3: 4字节）

        std_version: 0=HDC 1.0旧版(消息类型用旧表12, 字节3 D7为保留)
                     1=HDC 2.0新一代(消息类型用新表3, 字节3 D7为聚合MAC帧标志)。
        """
        result = []
        start = offset

        if len(data) < offset + 4:
            result.append(("❌ 单跳MAC帧头不完整", "", "", "单跳帧头需要4字节",
                            offset, len(data), False))
            return result

        b = data[offset:offset + 4]
        version = b[0] & 0x0F
        msg_type = b[1]
        msdu_len = b[2] | ((b[3] & 0x07) << 8)   # 11bit
        agg_flag = (b[3] >> 7) & 0x01

        msg_name = self.SINGLEHOP_MSG_TYPES.get(msg_type, f"保留({msg_type})")
        _ver_tag = self.STANDARD_VERSIONS.get(std_version, f"保留({std_version})")
        if std_version == 0:
            msg_name = self.SINGLEHOP_MSG_TYPES_V1.get(msg_type, f"保留({msg_type})")
            msg_note = "HDC 1.0: 0=发现列表消息 128=应用层报文 129=IPV4报文"
        else:
            msg_note = "HDC 2.0: 0=无线发现列表 1=信道评估参数更新 2=载波发现列表 128=应用层报文 129=IPV4报文"
        result.append(("MAC帧头(单跳)", "", "", f"单跳帧协议 版本={version} 4字节 [{_ver_tag}]",
                        start, start + 4, False))
        result.append(("  版本", f"0x{b[0]:02X} D[3:0]={version:04b}", str(version),
                        "0=标准帧协议 1=单跳帧协议",
                        start, start + 1, True))
        result.append(("  消息类型", f"0x{msg_type:02X} ({msg_name})", str(msg_type),
                        msg_note,
                        start + 1, start + 2, True))
        result.append(("  MSDU长度", f"{msdu_len}字节", str(msdu_len),
                        "MSDU载荷长度(11bit)",
                        start + 2, start + 4, True))
        if std_version == 0:
            result.append(("  保留(D7)", str(agg_flag), "",
                            "HDC 1.0保留(HDC 2.0为聚合MAC帧标志)",
                            start + 3, start + 4, True))
        else:
            result.append(("  聚合MAC帧标志", str(agg_flag),
                            "聚合帧" if agg_flag else "非聚合帧",
                            "0=非聚合 1=聚合多个MAC帧",
                            start + 3, start + 4, True))
        return result

    def _detect_std_fixed_len(self, data: bytes, offset: int) -> int:
        """检测标准MAC帧头固定部分长度

        文档表2定义16字节(字节14保留 + 字节15链路标识符);
        部分实际设备实现为15字节(无保留字节, 字节14链路标识符)。
        用ICV(仅MSDU的CRC-32)校验自动判别, 无法判别时默认16(文档值)。
        """
        if len(data) < offset + 16:
            return 16
        mac_addr_flag = (data[offset + 11] >> 3) & 0x01
        mac_len = 12 if mac_addr_flag else 0
        msdu_len = data[offset + 8] | ((data[offset + 9] & 0x07) << 8)
        if msdu_len > 0:
            for fixed in (15, 16):
                msdu_start = offset + fixed + mac_len
                icv_start = msdu_start + msdu_len
                if icv_start + 4 <= len(data):
                    icv = int.from_bytes(data[icv_start:icv_start + 4], 'little')
                    if zlib.crc32(data[msdu_start:icv_start]) & 0xFFFFFFFF == icv:
                        return fixed
        return 16

    def _get_mac_header_length(self, data: bytes, offset: int) -> int:
        """计算MAC帧头长度: 单跳=4字节; 标准=15/16字节(ICV判别,+MAC地址标志=1时12字节)"""
        if len(data) < offset + 1:
            return 0
        version = data[offset] & 0x0F
        if version == 1:
            return 4 if len(data) >= offset + 4 else 0
        if len(data) < offset + 15:
            return 0
        base_len = self._detect_std_fixed_len(data, offset)
        # MAC地址标志(字节11, bit3)
        if (data[offset + 11] >> 3) & 0x01:
            base_len += 12  # 源+目的MAC各6字节
        return base_len

    def _parse_pb_by_frame_type(self, data: bytes, offset: int, frame_type: int, std_version: int = 1) -> List[Tuple]:
        """根据帧类型解析物理块(PB)

        Args:
            data: PB数据
            offset: 起始偏移
            frame_type: 帧类型 (0=信标帧, 1=SOF帧, 2=ACK帧, 3=NET帧)
            std_version: FC标准版本号 0=HDC 1.0 1=HDC 2.0
        """
        result = []
        start = offset

        if len(data) < offset + 4:
            result.append(("❌ PB数据过短", "", "", "物理块数据不完整", None, None, False))
            return result

        # 帧类型名称
        type_names = {0: "信标帧(Beacon)", 1: "SOF帧", 2: "ACK帧(SACK)", 3: "NET帧"}
        type_name = type_names.get(frame_type, f"未知({frame_type})")

        result.append(("物理块(PB)", "", f"{type_name}", f"帧类型={frame_type}",
                        start, len(data), False))

        # ── 信标帧 (DT=0) ──
        if frame_type == 0:
            # 信标帧结构：信标类型(1B) + 信标序列号(1B) + NID(2B) + ...
            if len(data) >= offset + 4:
                beacon_type = data[offset]
                beacon_seq = data[offset + 1]
                nid = data[offset + 2] | (data[offset + 3] << 8)
                result.append(("  信标类型", f"0x{beacon_type:02X}", str(beacon_type),
                                "信标帧子类型", offset, offset + 1, True))
                result.append(("  信标序列号", f"0x{beacon_seq:02X}", str(beacon_seq),
                                "信标帧递增序列号", offset + 1, offset + 2, True))
                result.append(("  网络标识(NID)", f"0x{nid:04X}", str(nid),
                                "所属网络标识", offset + 2, offset + 4, True))
                offset += 4
                # 剩余数据作为信标内容
                if len(data) > offset:
                    remain = data[offset:]
                    result.append(("  信标内容", remain.hex().upper(), f"{len(remain)}字节",
                                    "信标帧载荷数据", offset, len(data), True))

        # ── SOF帧 (DT=1) ──
        elif frame_type == 1:
            # SOF帧物理块结构（4-2部分 表21）：
            #   物理块头(1B) + 物理块体(MAC帧头+MSDU+ICV+填充) + PBCS(3B, CRC-24)
            pbh = data[offset]
            pb_seq = pbh & 0x3F
            frame_start_flag = (pbh >> 6) & 0x01
            frame_end_flag = (pbh >> 7) & 0x01
            result.append(("  物理块头(PBH)", f"0x{pbh:02X}", f"序列号={pb_seq}",
                            "1字节: D[5:0]=序列号 D6=帧起始标志 D7=帧结束标志",
                            offset, offset + 1, True))
            result.append(("    PB序列号", f"D[5:0]={pb_seq:06b}", str(pb_seq),
                            "MPDU数据载荷中物理块序号", offset, offset + 1, True))
            result.append(("    帧起始标志", str(frame_start_flag),
                            "MAC帧第一个物理块" if frame_start_flag else "非第一个物理块",
                            "MAC帧分片后第一个物理块体=1", offset, offset + 1, True))
            result.append(("    帧结束标志", str(frame_end_flag),
                            "MAC帧最后一个物理块" if frame_end_flag else "非最后一个物理块",
                            "MAC帧分片后最后一个物理块体=1", offset, offset + 1, True))

            mac_offset = offset + 1

            # 解析MAC帧头（字节0版本字段判别标准/单跳）
            mac_len = self._get_mac_header_length(data, mac_offset)
            mac_result = self._parse_mac_header(data, mac_offset, std_version)
            if not mac_result:
                result.append(("  ⚠️ MAC头解析失败", "", "", "MAC帧头数据不完整",
                                mac_offset, len(data), True))
                return result
            result.extend(mac_result)

            if mac_len <= 0:
                return result

            # 从MAC帧头提取MSDU类型/长度
            version = data[mac_offset] & 0x0F
            if version == 1:
                msdu_type = data[mac_offset + 1]
                is_app = (msdu_type == 128)
                msdu_len = data[mac_offset + 2] | ((data[mac_offset + 3] & 0x07) << 8)
            else:
                msdu_type = data[mac_offset + 7]
                is_app = (msdu_type == 48)
                msdu_len = data[mac_offset + 8] | ((data[mac_offset + 9] & 0x07) << 8)

            msdu_start = mac_offset + mac_len
            if msdu_len > 0 and msdu_start < len(data):
                msdu_end = min(msdu_start + msdu_len, len(data))
                if is_app:
                    app_result = self._parse_application_layer(data[:msdu_end], msdu_start)
                    result.extend(app_result)
                elif version == 1:
                    # 单跳帧(表3): 消息类型0=无线发现列表 1=信道评估 2=载波发现列表 129=IPV4
                    mme_result = parse_singlehop_msdu(data[:msdu_end], msdu_start, msdu_type)
                    if mme_result:
                        result.extend(mme_result)
                    else:
                        msdu_data = data[msdu_start:msdu_end]
                        result.append(("  MSDU数据", " ".join(f"{x:02X}" for x in msdu_data),
                                        f"{len(msdu_data)}字节", f"单跳消息类型{msdu_type}",
                                        msdu_start, msdu_end, True))
                elif msdu_type == 0:
                    # 标准帧(表2): MSDU类型0=网络管理消息(表42/43 MMTYPE)
                    mme_result = parse_management_message(data[:msdu_end], msdu_start)
                    if mme_result:
                        result.extend(mme_result)
                    else:
                        msdu_data = data[msdu_start:msdu_end]
                        result.append(("  MSDU数据", " ".join(f"{x:02X}" for x in msdu_data),
                                        f"{len(msdu_data)}字节", "网络管理消息",
                                        msdu_start, msdu_end, True))
                else:
                    msdu_data = data[msdu_start:msdu_end]
                    type_name = "IP报文" if msdu_type == 49 else f"MSDU类型{msdu_type}"
                    result.append(("  MSDU数据", " ".join(f"{x:02X}" for x in msdu_data),
                                    f"{len(msdu_data)}字节", type_name,
                                    msdu_start, msdu_end, True))
                # ICV: MSDU完整性校验(CRC-32)，位于MSDU之后
                icv_start = msdu_start + msdu_len
                if icv_start + 4 <= len(data):
                    icv = data[icv_start:icv_start + 4]
                    icv_val = int.from_bytes(icv, 'little')
                    calc = zlib.crc32(data[msdu_start:icv_start]) & 0xFFFFFFFF
                    if calc == icv_val:
                        verify = "校验通过"
                    else:
                        verify = f"校验失败(计算值0x{calc:08X})"
                    result.append(("  完整性校验(ICV)", " ".join(f"{x:02X}" for x in icv),
                                    f"0x{icv_val:08X} {verify}", "MSDU的CRC-32(不含MAC帧头/MAC地址)",
                                    icv_start, icv_start + 4, True))
                    tail_start = icv_start + 4
                    if tail_start < len(data):
                        tail = data[tail_start:]
                        result.append(("  填充/PBCS", " ".join(f"{x:02X}" for x in tail),
                                        f"{len(tail)}字节", "物理块填充及PBCS(CRC-24)",
                                        tail_start, len(data), True))
            elif msdu_start < len(data):
                remain = data[msdu_start:]
                result.append(("  剩余数据", remain.hex().upper(), f"{len(remain)}字节",
                                "ICV/填充/PBCS", msdu_start, len(data), True))

        # ── ACK帧/SACK (DT=2) ──
        elif frame_type == 2:
            # SACK帧结构：确认类型(1B) + 确认TEI(2B) + 序列号列表
            if len(data) >= offset + 3:
                ack_type = data[offset]
                ack_tei = data[offset + 1] | (data[offset + 2] << 8)
                result.append(("  确认类型", f"0x{ack_type:02X}", str(ack_type),
                                "SACK确认类型", offset, offset + 1, True))
                result.append(("  确认TEI", f"0x{ack_tei:04X}", str(ack_tei),
                                "被确认的终端标识", offset + 1, offset + 3, True))
                offset += 3
                # 剩余为序列号列表
                if len(data) > offset:
                    seq_list = data[offset:]
                    result.append(("  序列号列表", seq_list.hex().upper(), f"{len(seq_list)}字节",
                                    "确认的MSDU序列号列表", offset, len(data), True))
            else:
                result.append(("  ⚠️ ACK帧数据不足", "", "", "ACK帧至少需要3字节",
                                offset, len(data), True))

        # ── NET帧 (DT=3) ──
        elif frame_type == 3:
            # 网间协调帧
            if len(data) >= offset + 4:
                net_type = data[offset]
                net_id = data[offset + 1] | (data[offset + 2] << 8)
                result.append(("  网间类型", f"0x{net_type:02X}", str(net_type),
                                "网间协调子类型", offset, offset + 1, True))
                result.append(("  网间标识", f"0x{net_id:04X}", str(net_id),
                                "相邻网络标识", offset + 1, offset + 3, True))
                offset += 3
                if len(data) > offset:
                    remain = data[offset:]
                    result.append(("  协调数据", remain.hex().upper(), f"{len(remain)}字节",
                                    "网间协调信息", offset, len(data), True))
            else:
                result.append(("  ⚠️ NET帧数据不足", "", "", "NET帧至少需要3字节",
                                offset, len(data), True))

        else:
            result.append(("  ⚠️ 未知帧类型", "", "", f"frame_type={frame_type} 无对应解析逻辑",
                            start, len(data), True))

        return result

    def _parse_application_layer(self, data: bytes, offset: int, direction: int = 0) -> List[Tuple]:
        """解析应用层报文

        Args:
            data: 完整帧数据
            offset: 应用层起始偏移
            direction: 方向 (0=下行, 1=上行)
                       当不确定时传0，特定报文ID会自动识别方向
        """
        result = []

        if len(data) < offset + 4:
            return result

        app_start = offset

        # 字节0: 报文端口号
        port = data[offset]
        port_name = self.PORT_NAMES.get(port, f"0x{port:02X}")
        offset += 1

        # 字节1-2: 报文ID 16bit (小端序)
        msg_id = data[offset] | (data[offset + 1] << 8)
        msg_name = self.MSG_IDS.get(msg_id, f"未知(0x{msg_id:04X})")
        # 报文ID高4位表示安全机制
        security = (msg_id >> 12) & 0x0F
        security_names = {
            0: "明文传输",
            1: "数据机密性保护",
            2: "数据完整性保护",
            3: "数据全面保护",
        }
        sec_name = security_names.get(security, f"保留({security})")
        offset += 2

        # 字节3: 报文控制字
        control = data[offset]
        offset += 1

        # 对于0x0011(注册)报文：下行头20字节,上行头36字节
        # 通过数据长度自动判断方向
        if direction == 0 and msg_id in (0x0011, 0x0012, 0x0013):
            payload_len = len(data) - offset
            if payload_len >= 36:
                direction = 1  # 上行
            elif payload_len <= 20:
                direction = 0  # 下行

        result.append(("应用层报文", "", "", f"端口={port_name} 报文ID={msg_name} {'上行' if direction else '下行'}",
                        app_start, len(data), False))
        result.append(("  报文端口号", f"0x{port:02X}", port_name, "业务端口",
                        app_start, app_start + 1, True))
        result.append(("  报文ID", f"0x{msg_id:04X}", msg_name,
                        f"安全机制: {sec_name}",
                        app_start + 1, app_start + 3, True))
        result.append(("  安全机制", f"D[15:12]={security:04b}", sec_name,
                        "0=明文 1=机密性 2=完整性 3=全面保护",
                        app_start + 1, app_start + 3, True))
        result.append(("  报文控制字", f"0x{control:02X}", str(control), "默认设置为0",
                        app_start + 3, app_start + 4, True))

        # 业务数据 - 使用 cmd_payloads 深度解析
        if offset < len(data):
            payload = data[offset:]
            # 调用 cmd_payloads 解析器
            payload_result = parse_command_payload(
                payload, msg_id, direction, port, offset
            )
            if payload_result:
                # 转换为 (field, raw, parsed, desc, start, end, is_child) 格式
                for name, raw, parsed, desc, start, end in payload_result:
                    result.append((f"  {name}", raw, parsed, desc, start, end, True))
            else:
                # 未知报文ID，输出原始数据
                payload_hex = " ".join(f"{b:02X}" for b in payload[:32])
                if len(payload) > 32:
                    payload_hex += " ..."
                result.append(("  业务数据(未解析)", payload_hex, f"{len(payload)}字节",
                               f"报文ID=0x{msg_id:04X} 暂不支持深度解析",
                               offset, len(data), True))

        return result

    def _parse_meter_read_payload(self, result: List, payload: bytes, offset: int, msg_id: int):
        """解析抄表报文业务数据"""
        if len(payload) < 8:
            return

        pos = offset

        # 协议版本号(6bit) + 报文头长度(6bit) + 标志位(4bit)
        b0 = payload[0]
        version = b0 & 0x3F
        header_len = ((b0 >> 6) & 0x03) | ((payload[1] & 0x0F) << 2) if len(payload) > 1 else 0
        result.append(("    协议版本号", f"{version}", str(version), "取值固定1",
                        pos, pos + 1, True))

        if len(payload) > 1:
            b1 = payload[1]
            retry_no_resp = (b1 >> 4) & 0x01
            retry_deny = (b1 >> 5) & 0x01
            max_retry = (b1 >> 6) & 0x03
            result.append(("    未应答重试标志", f"{retry_no_resp}", str(retry_no_resp),
                            "0=不重试 1=重试", pos + 1, pos + 2, True))
            result.append(("    否认重试标志", f"{retry_deny}", str(retry_deny),
                            "0=不重试 1=重试", pos + 1, pos + 2, True))
            result.append(("    最大重试次数", f"{max_retry}", str(max_retry),
                            "", pos + 1, pos + 2, True))

        if len(payload) > 2:
            # 规约类型(4bit) + 转发数据长度(12bit)
            proto_type = payload[2] & 0x0F
            data_len = ((payload[2] >> 4) & 0x0F) | (payload[3] << 4) if len(payload) > 3 else 0
            proto_name = self.PROTOCOL_TYPES.get(proto_type, f"保留({proto_type})")
            result.append(("    规约类型", f"{proto_type} ({proto_name})", str(proto_type),
                            "0=透明 1=DL645-97 2=DL645-07 3=DL698.45",
                            pos + 2, pos + 3, True))
            result.append(("    转发数据长度", f"{data_len}字节", str(data_len),
                            "CCO发送给STA的数据长度",
                            pos + 2, pos + 4, True))

    def _parse_confirm_payload(self, result: List, payload: bytes, offset: int):
        """解析确认/否认报文"""
        if len(payload) < 2:
            return
        pos = offset

        # 确认状态
        status = payload[0]
        status_map = {
            0: "成功",
            1: "失败",
            2: "不支持",
            3: "参数错误",
            4: "繁忙",
        }
        status_name = status_map.get(status, f"未知({status})")
        result.append(("    确认状态", f"0x{status:02X} ({status_name})", str(status),
                        "确认/否认状态码", pos, pos + 1, True))


def get_gw_new_gen_parser() -> GWNewGenParser:
    """获取解析器单例"""
    return GWNewGenParser()
