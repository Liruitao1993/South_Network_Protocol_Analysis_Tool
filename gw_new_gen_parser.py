# -*- coding: utf-8 -*-
"""国网新一代双模通信互联互通技术规范 解析器

协议标准: Q/GDW 双模通信互联互通技术规范
- 第4-2部分：数据链路层通信协议
- 第4-3部分：应用层通信协议

帧结构:
  MPDU = FC(16B) + [HCS(3B)] + [物理块] + [MSDU] + [FCS(4B)]
  FC   = 定界符类型 + 网络类型 + NID(16bit) + 保留 + 可变区域(68bit) + 版本号 + FCCS(24bit)
  MAC帧头 = 版本 + 源/目的TEI + 发送类型 + MSDU序列号 + MSDU类型 + MSDU长度 + ...
  应用层 = 报文端口号 + 报文ID(16bit) + 控制字 + 业务数据
"""
import re
from typing import List, Tuple, Any, Optional
from gw_new_gen_cmd_payloads import parse_command_payload


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

    def parse_to_table(self, frame_bytes: bytes, parse_level: str = "auto", **kwargs) -> List[Tuple]:
        """解析完整帧，返回表格数据

        Args:
            frame_bytes: 帧数据
            parse_level: 解析级别
                - "auto": 自动识别，完整解析 (FC + MAC + 应用层)
                - "fc_only": 仅解析帧控制(FC)字段
                - "fc_mac": 解析FC + MAC帧头（不含应用层）
                - "app": 仅解析应用层报文

        Returns:
            [(field, raw, parsed, comment, byte_start, byte_end, is_child), ...]
        """
        data = frame_bytes
        offset = 0

        if len(data) < 2:
            return [("❌ 解析失败", "", "", "帧数据过短，无法解析", None, None, False)]

        # ── 应用层模式：输入即为应用层报文，直接从偏移0解析 ──
        if parse_level == "app":
            return self._parse_application_layer(data, 0)

        result = []

        # ── MPDU 帧控制 (FC) ──
        fc_result = self._parse_fc(data, offset)
        result.extend(fc_result)
        offset = 16  # FC 固定16字节

        # ── 仅FC解析模式 ──
        if parse_level == "fc_only":
            return result

        # ── 寻找 MSDU ──
        # FC之后可能有HCS(3B)，然后是物理块，最后是MSDU
        if len(data) > offset:
            # FC+MAC模式：解析MAC帧头但不解析应用层
            if parse_level == "fc_mac":
                mac_result = self._parse_mac_header(data, offset)
                if mac_result:
                    result.extend(mac_result)
                return result

            # auto模式：完整解析
            msdu_result = self._parse_msdu_from_frame(data, offset)
            result.extend(msdu_result)

        return result

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

        # 字节1-2: 网络标识(NID) 16bit
        nid = (fc[1] << 8) | fc[2]
        result.append(("  网络标识(NID)", f"{fc[1]:02X} {fc[2]:02X}",
                        str(nid), f"0x{nid:04X} (1~65535)",
                        offset + 1, offset + 3, True))

        # 字节3: 保留
        result.append(("  保留", f"0x{fc[3]:02X}", "", "保留字段",
                        offset + 3, offset + 4, True))

        # 字节4-11: 可变区域 (68bit)
        vf = fc[4:12]
        vf_hex = " ".join(f"{b:02X}" for b in vf)
        result.append(("  可变区域(VF)", vf_hex, f"{len(vf)}字节", "68bit 可变区域",
                        offset + 4, offset + 12, True))

        # 字节12: 标准版本号(高4bit) + 保留(低4bit)
        b12 = fc[12]
        version = (b12 >> 4) & 0x0F
        ver_name = self.STANDARD_VERSIONS.get(version, f"保留({version})")
        result.append(("  标准版本号", f"0x{b12:02X} D[7:4]={version:04b}",
                        f"{version} ({ver_name})", f"版本: {ver_name}",
                        offset + 12, offset + 13, True))

        # 字节13-15: 帧控制校验序列(FCCS) 24bit CRC
        fccs = (fc[13] << 16) | (fc[14] << 8) | fc[15]
        result.append(("  FCCS校验序列", f"{fc[13]:02X} {fc[14]:02X} {fc[15]:02X}",
                        f"0x{fccs:06X}", "24bit CRC校验",
                        offset + 13, offset + 16, True))

        return result

    def _parse_msdu_from_frame(self, data: bytes, offset: int) -> List[Tuple]:
        """从帧数据中定位并解析MSDU"""
        result = []

        # 跳过可能的HCS(3字节)和物理块头，寻找MAC帧
        # 尝试在offset之后寻找MAC帧结构
        msdu_start = offset
        msdu_end = len(data)

        if msdu_start >= msdu_end:
            return result

        # 尝试解析MAC帧头
        mac_result = self._parse_mac_header(data, msdu_start)
        if mac_result:
            result.extend(mac_result)

            # 从MAC帧头获取方向（发送类型在字节2的高4位）
            direction = 0  # 默认下行
            if len(data) > msdu_start + 2:
                b2 = data[msdu_start + 2]
                send_type = (b2 >> 4) & 0x0F
                # send_type: 0=单播, 1=全网广播, 2=本地广播, 3=代理广播
                # 方向需要从其他字段判断，这里暂用默认值

            # 检查是否为应用层报文(MSDU类型=48)
            # 从MAC帧头中获取MSDU类型和长度
            if len(data) > msdu_start + 7:
                msdu_type = data[msdu_start + 7]  # MSDU类型在MAC帧头字节7
                if msdu_type == 48:  # 应用层报文
                    # MSDU从MAC帧头之后开始
                    mac_header_len = self._get_mac_header_length(data, msdu_start)
                    if mac_header_len > 0 and msdu_start + mac_header_len < msdu_end:
                        app_result = self._parse_application_layer(data, msdu_start + mac_header_len, direction)
                        result.extend(app_result)
        else:
            # 无法解析MAC帧头，尝试直接解析应用层
            app_result = self._parse_application_layer(data, msdu_start, 0)
            result.extend(app_result)

        return result

    def _parse_mac_header(self, data: bytes, offset: int) -> List[Tuple]:
        """解析标准MAC帧头"""
        result = []
        start = offset

        if len(data) < offset + 14:
            return result

        # 字节0: 版本(4bit) + 原始源TEI高4位(4bit)
        b0 = data[offset]
        version = b0 & 0x0F
        src_tei_high = (b0 >> 4) & 0x0F
        offset += 1

        # 字节1: 原始源TEI低8位
        src_tei = (src_tei_high << 8) | data[offset]
        offset += 1

        # 字节2: 原始目的TEI高4位(4bit) + 发送类型(4bit)
        b2 = data[offset]
        dst_tei_high = b2 & 0x0F
        send_type = (b2 >> 4) & 0x0F
        offset += 1

        # 字节3: 原始目的TEI低8位
        dst_tei = (dst_tei_high << 8) | data[offset]
        offset += 1

        result.append(("MAC帧头(固定域)", "", "", f"标准帧协议 版本={version}",
                        start, start + 14, False))
        result.append(("  版本", f"0x{b0:02X} D[3:0]={version:04b}",
                        str(version), "0=标准帧 1=单跳帧",
                        start, start + 1, True))
        result.append(("  原始源TEI", f"0x{src_tei:04X}",
                        str(src_tei), "最初产生MSDU的源终端TEI",
                        start, start + 2, True))
        result.append(("  原始目的TEI", f"0x{dst_tei:04X}",
                        str(dst_tei), "MSDU最终目的终端TEI",
                        start + 2, start + 4, True))

        send_name = self.SEND_TYPES.get(send_type, f"保留({send_type})")
        result.append(("  发送类型", f"D[7:4]={send_type:04b} ({send_name})",
                        str(send_type), send_name,
                        start + 3, start + 4, True))

        if len(data) < offset + 10:
            return result

        # 字节4-5: MSDU序列号 16bit
        msdu_seq = (data[offset] << 8) | data[offset + 1]
        offset += 2

        # 字节6: MSDU类型
        msdu_type = data[offset]
        msdu_type_name = self.MSDU_TYPES.get(msdu_type, f"保留({msdu_type})")
        offset += 1

        # 字节7-8: MSDU长度(11bit) + 重启次数(4bit) + 代理主路径标识(1bit)
        msdu_len_byte0 = data[offset]
        msdu_len_byte1 = data[offset + 1]
        msdu_len = (msdu_len_byte0 << 3) | ((msdu_len_byte1 >> 5) & 0x07)
        restart_cnt = (msdu_len_byte1 >> 1) & 0x0F
        proxy_flag = msdu_len_byte1 & 0x01
        offset += 2

        result.append(("  MSDU序列号", f"{msdu_seq:04X}", str(msdu_seq),
                        "递增序列号", start + 4, start + 6, True))
        result.append(("  MSDU类型", f"0x{msdu_type:02X} ({msdu_type_name})",
                        str(msdu_type), msdu_type_name,
                        start + 6, start + 7, True))
        result.append(("  MSDU长度", f"{msdu_len}字节", str(msdu_len),
                        f"MSDU载荷长度",
                        start + 7, start + 9, True))
        result.append(("  重启次数", f"{restart_cnt}", str(restart_cnt),
                        "站点重启次数(0-15)",
                        start + 8, start + 9, True))
        result.append(("  代理主路径", f"{proxy_flag}", str(proxy_flag),
                        "0=未启用 1=使用代理主路径",
                        start + 8, start + 9, True))

        if len(data) < offset + 6:
            return result

        # 字节9: 路由总跳数(4bit) + 路由剩余跳数(4bit)
        b9 = data[offset]
        total_hops = (b9 >> 4) & 0x0F
        remain_hops = b9 & 0x0F
        offset += 1

        # 字节10: 广播方向(2bit) + 路径修复(1bit) + MAC地址标志(1bit) + 发送帧序号高4位(4bit)
        b10 = data[offset]
        broadcast_dir = (b10 >> 6) & 0x03
        path_repair = (b10 >> 5) & 0x01
        mac_addr_flag = (b10 >> 4) & 0x01
        frame_seq_high = b10 & 0x0F
        offset += 1

        # 字节11: 发送帧序号低8位
        frame_seq = (frame_seq_high << 8) | data[offset]
        offset += 1

        # 字节12: 组网序列号
        net_seq = data[offset]
        offset += 1

        # 字节13: 保留
        offset += 1

        # 字节14: 链路标识符
        link_id = data[offset]
        link_name = self.LINK_ID_MAP.get(link_id, f"0x{link_id:02X}")
        offset += 1

        bd_name = self.BROADCAST_DIRS.get(broadcast_dir, f"保留({broadcast_dir})")
        result.append(("  路由总跳数", f"{total_hops}", str(total_hops), "", start + 9, start + 10, True))
        result.append(("  路由剩余跳数", f"{remain_hops}", str(remain_hops), "", start + 9, start + 10, True))
        result.append(("  广播方向", f"{broadcast_dir} ({bd_name})", str(broadcast_dir), bd_name,
                        start + 10, start + 11, True))
        result.append(("  路径修复标志", f"{path_repair}", str(path_repair), "0=未触发 1=已触发",
                        start + 10, start + 11, True))
        result.append(("  MAC地址标志", f"{mac_addr_flag}", str(mac_addr_flag), "0=未携带 1=携带MAC地址",
                        start + 10, start + 11, True))
        result.append(("  发送帧序号", f"0x{frame_seq:04X}", str(frame_seq), "用于统计成功率",
                        start + 10, start + 12, True))
        result.append(("  组网序列号", f"0x{net_seq:02X}", str(net_seq), "CCO重新组网后+1",
                        start + 12, start + 13, True))
        result.append(("  链路标识符", f"0x{link_id:02X} ({link_name})",
                        str(link_id), "优先级/业务分类",
                        start + 14, start + 15, True))

        # 如果携带MAC地址，解析源/目的MAC
        if mac_addr_flag and len(data) >= offset + 12:
            src_mac = data[offset:offset + 6]
            dst_mac = data[offset + 6:offset + 12]
            src_mac_str = ":".join(f"{b:02X}" for b in src_mac)
            dst_mac_str = ":".join(f"{b:02X}" for b in dst_mac)
            result.append(("  源MAC地址", src_mac_str, src_mac_str, "原始源站点MAC",
                            offset, offset + 6, True))
            result.append(("  目的MAC地址", dst_mac_str, dst_mac_str, "最终目的站点MAC",
                            offset + 6, offset + 12, True))
            offset += 12

        return result

    def _get_mac_header_length(self, data: bytes, offset: int) -> int:
        """计算MAC帧头长度（含可能的MAC地址）"""
        if len(data) < offset + 15:
            return 0
        # 基本长度15字节
        base_len = 15
        # 检查MAC地址标志(字节10, bit3)
        b10 = data[offset + 10]
        mac_addr_flag = (b10 >> 4) & 0x01
        if mac_addr_flag:
            base_len += 12  # 源+目的MAC各6字节
        return base_len

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
