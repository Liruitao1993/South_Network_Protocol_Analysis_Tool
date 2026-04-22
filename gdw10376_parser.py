import json
import os
import struct
from typing import Dict, Any, Optional, Tuple, List
from gdw10376_tool import GDWControlField, COMM_TYPE_MAP, DIR_MAP, PRM_MAP


class GDW10376Parser:
    """国网集中器本地通信模块接口协议解析器 (Q/GDW 10376.2—2024)"""

    # AFN 定义
    AFN_MAP = {
        0x00: "确认/否认",
        0x01: "初始化",
        0x02: "数据转发",
        0x03: "查询数据",
        0x04: "链路接口检测",
        0x05: "控制命令",
        0x06: "主动上报",
        0x10: "路由查询",
        0x11: "路由设置",
        0x12: "重启/暂停/恢复控制",
        0x13: "路由数据转发",
        0x14: "路由数据抄读",
        0x15: "文件传输",
        0xF0: "内部调试",
        0xF1: "并发抄表",
    }

    # FN 定义 (AFN -> {Fn: 名称})
    FN_MAP = {
        0x00: {1: "确认", 2: "否认"},
        0x01: {1: "硬件初始化", 2: "参数区初始化", 3: "数据区初始化"},
        0x02: {1: "转发通信协议数据帧"},
        0x03: {
            1: "厂商代码和版本信息",
            2: "噪声值",
            3: "从节点侦听信息",
            4: "主节点地址",
            5: "主节点状态字和通信速率",
            6: "主节点干扰状态",
            7: "读取从节点监控最大超时时间",
            8: "查询无线通信参数",
            9: "查询从节点通信延时",
            10: "本地通信模块运行模式信息",
            11: "本地通信模块AFN索引",
            12: "查询CCO模块ID",
            16: "查询宽带载波通信参数",
            17: "查询无线频段",
            18: "查询本地通信信道加密参数",
            100: "查询场强门限",
        },
        0x04: {
            1: "发送测试",
            2: "从节点点名",
            3: "本地通信模块报文通信测试",
        },
        0x05: {
            1: "设置主节点地址",
            2: "允许从节点上报",
            3: "启动广播",
            4: "设置从节点监控最大超时时间",
            5: "设置无线通信参数",
            6: "允许/禁止台区识别",
            10: "串口速率配置",
            16: "设置宽带载波通信参数",
            17: "设置无线频段",
            18: "允许/禁止本地通信信道加密",
            20: "广播透传命令",
            100: "设置场强门限",
            101: "设置中心节点时间",
            200: "控制拒绝节点上报",
        },
        0x06: {
            1: "上报从节点信息",
            2: "上报抄读数据",
            3: "上报路由工况变动信息",
            4: "上报从节点信息及设备类型",
            5: "上报从节点事件",
        },
        0x10: {
            1: "从节点数量",
            2: "从节点信息",
            3: "指定从节点的上一级中继路由信息",
            4: "路由运行状态",
            5: "未抄读成功的从节点信息",
            6: "主动注册的从节点信息",
            7: "查询从节点模块ID信息",
            9: "查询网络规模",
            20: "查询双模网络拓扑信息",
            21: "查询网络拓扑信息",
            31: "查询相线信息",
            40: "流水线查询ID信息",
            100: "查询微功率无线网络规模",
            101: "查询微功率无线从节点信息",
            104: "查询升级后模块版本信息",
            111: "查询网络信息",
            112: "查询宽带载波芯片信息",
        },
        0x11: {
            1: "添加从节点",
            2: "删除从节点",
            3: "设置从节点固定中继路径",
            4: "设置路由工作模式",
            5: "激活从节点主动注册",
            6: "终止从节点主动注册",
            100: "设置网络规模",
            101: "启动网络维护进程",
            102: "启动组网",
        },
        0x12: {
            1: "重启",
            2: "暂停",
            3: "恢复",
        },
        0x13: {
            1: "监控从节点",
            2: "扩展监控从节点",
        },
        0x14: {
            1: "路由请求抄读内容",
            2: "路由请求集中器时钟",
            3: "请求依通信延时修正通信数据",
            4: "路由请求交采信息",
        },
        0x15: {
            1: "文件传输方式1",
        },
        0xF0: {},
        0xF1: {
            1: "集中器主动并发抄表",
            2: "集中器确认主动上报",
        },
    }

    def __init__(self, custom_config_path: str = "gdw_custom_afn.json"):
        """初始化解析器，加载自定义AFN+Fn定义

        Args:
            custom_config_path: 自定义AFN+Fn配置文件路径
        """
        self._custom_afn_map: Dict[int, str] = {}
        self._custom_fn_map: Dict[int, Dict[int, str]] = {}
        self._custom_config_path = custom_config_path
        self._load_custom_config()

    def _load_custom_config(self):
        """从JSON文件加载自定义AFN+Fn定义"""
        if not os.path.exists(self._custom_config_path):
            return
        try:
            with open(self._custom_config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Load custom AFN names
            for afn_hex, name in data.get("afn_map", {}).items():
                try:
                    afn = int(afn_hex, 16) if isinstance(afn_hex, str) and not afn_hex.isdigit() else int(afn_hex)
                    self._custom_afn_map[afn] = name
                except (ValueError, TypeError):
                    continue
            # Load custom Fn names
            for afn_hex, fn_dict in data.get("fn_map", {}).items():
                try:
                    afn = int(afn_hex, 16) if isinstance(afn_hex, str) and not afn_hex.isdigit() else int(afn_hex)
                    self._custom_fn_map[afn] = {}
                    for fn_str, name in fn_dict.items():
                        try:
                            fn = int(fn_str)
                            self._custom_fn_map[afn][fn] = name
                        except (ValueError, TypeError):
                            continue
                except (ValueError, TypeError):
                    continue
        except (json.JSONDecodeError, OSError):
            pass

    def get_afn_name(self, afn: int) -> str:
        """获取AFN名称（优先自定义，其次标准）"""
        return self._custom_afn_map.get(afn, self.AFN_MAP.get(afn, f"未知({afn:02X})"))

    def get_fn_name(self, afn: int, fn: int) -> str:
        """获取Fn名称（优先自定义，其次标准）"""
        custom_fn = self._custom_fn_map.get(afn, {}).get(fn)
        if custom_fn:
            return custom_fn
        return self.FN_MAP.get(afn, {}).get(fn, f"F{fn}")

    def add_custom_afn(self, afn: int, name: str):
        """添加自定义AFN名称"""
        self._custom_afn_map[afn] = name
        self._save_custom_config()

    def add_custom_fn(self, afn: int, fn: int, name: str):
        """添加自定义Fn名称"""
        if afn not in self._custom_fn_map:
            self._custom_fn_map[afn] = {}
        self._custom_fn_map[afn][fn] = name
        self._save_custom_config()

    def remove_custom_afn(self, afn: int):
        """删除自定义AFN"""
        if afn in self._custom_afn_map:
            del self._custom_afn_map[afn]
        self._save_custom_config()

    def remove_custom_fn(self, afn: int, fn: int):
        """删除自定义Fn"""
        if afn in self._custom_fn_map and fn in self._custom_fn_map[afn]:
            del self._custom_fn_map[afn][fn]
            if not self._custom_fn_map[afn]:
                del self._custom_fn_map[afn]
        self._save_custom_config()

    def _save_custom_config(self):
        """保存自定义AFN+Fn定义到JSON文件"""
        data = {
            "afn_map": {f"{afn:02X}": name for afn, name in self._custom_afn_map.items()},
            "fn_map": {f"{afn:02X}": {str(fn): name for fn, name in fn_dict.items()} for afn, fn_dict in self._custom_fn_map.items()}
        }
        try:
            with open(self._custom_config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def get_custom_entries(self) -> List[Tuple[int, str, int, str]]:
        """获取所有自定义AFN+Fn条目"""
        result = []
        for afn, fn_dict in self._custom_fn_map.items():
            afn_name = self._custom_afn_map.get(afn, self.AFN_MAP.get(afn, f"未知({afn:02X})"))
            for fn, fn_name in fn_dict.items():
                result.append((afn, afn_name, fn, fn_name))
        return result

    def parse_to_table(self, frame_bytes: bytes) -> list:
        """解析为表格数据格式

        返回：[(字段名，原始值，解析值，说明, byte_start, byte_end), ...]
        """
        table_data = []
        frame_len = len(frame_bytes)

        if frame_len < 8:
            table_data.append(("错误", "-", "-", "帧长度过短，至少8字节", None, None))
            return table_data

        offset = 0

        # 1. 起始字符 68H
        start_char = frame_bytes[offset]
        start_valid = start_char == 0x68
        table_data.append((
            "起始字符",
            f"0x{start_char:02X}",
            "68H" if start_valid else "错误",
            "帧起始标志" if start_valid else f"期望68H，实际0x{start_char:02X}",
            offset, offset
        ))
        offset += 1

        # 2. 长度域 L (2字节，小端序)
        if offset + 1 < frame_len:
            length_val = int.from_bytes(frame_bytes[offset:offset+2], 'little')
            table_data.append((
                "长度域",
                f"0x{frame_bytes[offset]:02X} {frame_bytes[offset+1]:02X}",
                str(length_val),
                f"用户数据长度={length_val-6}字节，小端序，2字节",
                offset, offset + 1
            ))
            offset += 2
        else:
            table_data.append(("长度域", "-", "-", "帧长度不足", offset, offset + 1))
            return table_data

        # 3. 控制域 C (1字节)
        if offset < frame_len:
            ctrl_byte = frame_bytes[offset]
            ctrl = GDWControlField.from_byte(ctrl_byte)
            table_data.append((
                "控制域",
                f"0x{ctrl_byte:02X}",
                "",
                "",
                offset, offset
            ))
            table_data.append((
                "  传输方向(DIR)",
                "-",
                str(ctrl.dir),
                DIR_MAP.get(ctrl.dir, "未知"),
                offset, offset
            ))
            table_data.append((
                "  启动标志(PRM)",
                "-",
                str(ctrl.prm),
                PRM_MAP.get(ctrl.prm, "未知"),
                offset, offset
            ))
            comm_type_name = COMM_TYPE_MAP.get(ctrl.comm_type, f"未知({ctrl.comm_type})")
            table_data.append((
                "  通信方式",
                "-",
                str(ctrl.comm_type),
                comm_type_name,
                offset, offset
            ))
            offset += 1
        else:
            table_data.append(("控制域", "-", "-", "帧长度不足", offset, offset))
            return table_data

        # 计算用户数据区长度和校验和位置
        user_data_len = length_val - 6
        cs_pos = 4 + user_data_len  # 校验和在用户数据区之后(起始1+长度2+控制1+用户数据user_data_len)
        end_pos = cs_pos + 1

        # 校验长度是否合理
        if length_val > frame_len:
            table_data.append(("错误", "-", "-", f"长度域指示帧总长{length_val}，实际仅{frame_len}字节", None, None))

        # 4. 信息域 R
        # 根据DIR判断上下行
        dir_val = ctrl.dir if 'ctrl' in dir() else 0
        # 重新获取dir（避免局部变量问题）
        dir_val = ctrl.dir

        info_domain_len = 6  # 上下行信息域均为6字节（下行:表4，上行:表5）
        info_end = min(offset + info_domain_len, frame_len)
        actual_info_len = info_end - offset

        if actual_info_len > 0:
            info_bytes = frame_bytes[offset:info_end]
            table_data.append((
                "信息域",
                ' '.join(f'{b:02X}' for b in info_bytes),
                "",
                f"{'下行' if dir_val == 0 else '上行'}报文信息域，{actual_info_len}字节",
                offset, info_end - 1
            ))

            # 解析信息域内容
            if dir_val == 0 and actual_info_len >= 5:
                # 下行信息域
                b0 = info_bytes[0]
                route_flag = b0 & 0x01
                sub_node_flag = (b0 >> 1) & 0x01
                comm_module_flag = (b0 >> 2) & 0x01
                conflict_detect = (b0 >> 3) & 0x01
                relay_level = (b0 >> 4) & 0x0F

                table_data.append(("  路由标识", "-", str(route_flag), "0=带路由/路由模式, 1=不带路由/旁路模式", offset, offset))
                table_data.append(("  附属节点标识", "-", str(sub_node_flag), "0=无附加节点, 1=有附加节点", offset, offset))
                table_data.append(("  通信模块标识", "-", str(comm_module_flag), "0=对主节点操作, 1=对从节点操作", offset, offset))
                table_data.append(("  冲突检测", "-", str(conflict_detect), "0=不进行, 1=要进行", offset, offset))
                table_data.append(("  中继级别", "-", str(relay_level), "0~15，0表示无中继", offset, offset))

                if actual_info_len >= 2:
                    b1 = info_bytes[1]
                    channel_id = b1 & 0x1F
                    fec_flag = (b1 >> 5) & 0x07
                    table_data.append(("  信道标识", "-", str(channel_id), "0~15，0表示不分信道", offset + 1, offset + 1))
                    table_data.append(("  纠错编码标识", "-", str(fec_flag), "0=未编码, 1=RS编码", offset + 1, offset + 1))

                if actual_info_len >= 3:
                    resp_bytes = info_bytes[2]
                    table_data.append(("  预计应答字节数", "-", str(resp_bytes), "0=默认延时", offset + 2, offset + 2))

                if actual_info_len >= 5:
                    rate_val = int.from_bytes(info_bytes[3:5], 'little')
                    rate_unit = (rate_val >> 15) & 0x01
                    rate = rate_val & 0x7FFF
                    table_data.append(("  通信速率", "-", str(rate), f"{'kbit/s' if rate_unit else 'bit/s'}，0=默认速率", offset + 3, offset + 4))

                if actual_info_len >= 6:
                    seq = info_bytes[5]
                    table_data.append(("  报文序列号", "-", str(seq), "0~255循环", offset + 5, offset + 5))

            elif dir_val == 1 and actual_info_len >= 6:
                # 上行信息域
                b0 = info_bytes[0]
                route_flag = b0 & 0x01
                comm_module_flag = (b0 >> 2) & 0x01
                relay_level = (b0 >> 4) & 0x0F

                table_data.append(("  路由标识", "-", str(route_flag), "0=带路由/路由模式, 1=不带路由/旁路模式", offset, offset))
                table_data.append(("  通信模块标识", "-", str(comm_module_flag), "0=对主节点操作, 1=对从节点操作", offset, offset))
                table_data.append(("  中继级别", "-", str(relay_level), "0~15，0表示无中继", offset, offset))

                if actual_info_len >= 2:
                    channel_id = info_bytes[1] & 0x0F
                    table_data.append(("  信道标识", "-", str(channel_id), "0~15，0表示不分信道", offset + 1, offset + 1))

                if actual_info_len >= 3:
                    phase_id = info_bytes[2] & 0x03
                    channel_feature = (info_bytes[2] >> 4) & 0x0F
                    table_data.append(("  实测相线标识", "-", str(phase_id), "0=不确定, 1~3=第1~3相", offset + 2, offset + 2))
                    table_data.append(("  电能表通道特征", "-", str(channel_feature), "1=单相单信道, 4=三相三信道", offset + 2, offset + 2))

                if actual_info_len >= 4:
                    signal_quality = info_bytes[3] & 0x0F
                    table_data.append(("  信号品质", "-", str(signal_quality), "0~15，0=无品质, 1=最低", offset + 3, offset + 3))

                if actual_info_len >= 5:
                    event_flag = info_bytes[4] & 0x01
                    table_data.append(("  事件标志", "-", str(event_flag), "0=无上报事件, 1=有上报事件", offset + 4, offset + 4))

                if actual_info_len >= 6:
                    seq = info_bytes[5]
                    table_data.append(("  报文序列号", "-", str(seq), "0~255循环", offset + 5, offset + 5))

            offset = info_end

        # 5. 地址域 A (仅当通信模块标识=1时存在)
        has_addr = False
        if 'comm_module_flag' in dir():
            # 从信息域解析结果中获取
            pass

        # 简化处理：如果还有足够字节，尝试解析地址域
        # 实际上需要根据信息域中的通信模块标识判断
        # 这里采用启发式：如果剩余字节足够包含AFN+DT+至少1字节数据+CS+16
        # 且长度看起来合理，则尝试解析地址域
        remaining_for_end = 4  # AFN(1) + DT(2) + CS(1) + 16(1) = 5? 不对，CS和16是帧尾部
        # 帧尾部 = CS(1) + 16(1) = 2字节
        # 应用数据域最小 = AFN(1) + DT(2) = 3字节
        # 所以用户数据区最小（无地址） = 信息域 + AFN + DT = info_len + 3
        # 有地址时 = info_len + 12 + 3 = info_len + 15

        # 重新计算：用户数据区 = 信息域 + [地址域] + 应用数据域
        # 应用数据域 = AFN + DT + 数据单元
        # 数据单元可能为空（查询命令）
        # 所以用户数据区至少 = info_len + 1(AFN) + 2(DT) = info_len + 3
        # 如果还有多余字节（超过info_len + 3 + 2尾部），可能包含地址域

        min_user_data_no_addr = info_domain_len + 1 + 2  # info + AFN + DT
        min_user_data_with_addr = info_domain_len + 12 + 1 + 2  # info + addr(6+6) + AFN + DT

        # 更好的方法：从长度域计算用户数据长度，然后分配
        # 用户数据区总长度 = user_data_len
        # 已消耗 = info_domain_len
        # 剩余 = user_data_len - info_domain_len
        # 如果剩余 >= 15 (12字节地址 + 3字节AFN+DT)，且帧总长允许，则有地址域
        # 地址域长度 = 12 + 6*relay_level

        addr_len = 0
        # 重新从信息域获取中继级别（使用局部变量）
        relay_level = 0
        if dir_val == 0 and actual_info_len >= 1:
            relay_level = (info_bytes[0] >> 4) & 0x0F
        elif dir_val == 1 and actual_info_len >= 1:
            relay_level = (info_bytes[0] >> 4) & 0x0F

        # 判断是否有地址域：通信模块标识=1时有地址域
        # 从信息域获取通信模块标识
        comm_module_flag = 0
        if actual_info_len >= 1:
            if dir_val == 0:
                comm_module_flag = (info_bytes[0] >> 2) & 0x01
            else:
                comm_module_flag = (info_bytes[0] >> 2) & 0x01

        if comm_module_flag == 1:
            addr_len = 12 + 6 * relay_level

        # 检查帧长度是否足够容纳地址域
        if addr_len > 0 and offset + addr_len + 3 <= cs_pos:
            addr_bytes = frame_bytes[offset:offset+addr_len]
            table_data.append((
                "地址域",
                ' '.join(f'{b:02X}' for b in addr_bytes),
                "",
                f"{'下行' if dir_val == 0 else '上行'}地址域，{addr_len}字节",
                offset, offset + addr_len - 1
            ))

            # 源地址 A1 (6字节BCD)
            a1 = addr_bytes[0:6]
            a1_str = self._format_addr(a1)
            table_data.append(("  源地址(A1)", a1_str, a1_str, "BCD编码，6字节", offset, offset + 5))

            # 中继地址 A2
            if relay_level > 0 and len(addr_bytes) >= 12:
                a2 = addr_bytes[6:6+6*relay_level]
                a2_str = self._format_addr(a2)
                table_data.append(("  中继地址(A2)", a2_str, a2_str, f"BCD编码，{6*relay_level}字节，中继级别={relay_level}", offset + 6, offset + 6 + 6 * relay_level - 1))

            # 目的地址 A3
            a3_start = 6 + 6 * relay_level
            if len(addr_bytes) >= a3_start + 6:
                a3 = addr_bytes[a3_start:a3_start+6]
                a3_str = self._format_addr(a3)
                table_data.append(("  目的地址(A3)", a3_str, a3_str, "BCD编码，6字节", offset + a3_start, offset + a3_start + 5))

            offset += addr_len

        # 6. 应用数据域
        if offset < cs_pos:
            # AFN
            afn = frame_bytes[offset]
            afn_name = self.get_afn_name(afn)
            table_data.append((
                "应用功能码(AFN)",
                f"0x{afn:02X}",
                str(afn),
                f"AFN={afn:02X}H {afn_name}",
                offset, offset
            ))
            offset += 1

            # DT (数据单元标识 = DT1 + DT2)
            if offset + 1 < cs_pos:
                dt1 = frame_bytes[offset]
                dt2 = frame_bytes[offset + 1]

                # 解析Fn
                fn_list = self._dt_to_fn(dt1, dt2)
                fn_desc_list = []
                for fn in fn_list:
                    fn_name = self.get_fn_name(afn, fn)
                    fn_desc_list.append(f"F{fn}={fn_name}")

                fn_desc = "; ".join(fn_desc_list) if fn_desc_list else f"DT1=0x{dt1:02X}, DT2=0x{dt2:02X}"

                table_data.append((
                    "数据单元标识(DT)",
                    f"0x{dt1:02X} 0x{dt2:02X}",
                    f"DT1={dt1}, DT2={dt2}",
                    fn_desc,
                    offset, offset + 1
                ))
                offset += 2

                # 数据单元
                data_len = cs_pos - offset
                if data_len > 0:
                    data_bytes = frame_bytes[offset:cs_pos]
                    table_data.append((
                        "数据单元",
                        ' '.join(f'{b:02X}' for b in data_bytes),
                        f"{data_len}字节",
                        "应用数据",
                        offset, cs_pos - 1
                    ))
                else:
                    data_bytes = b''

                # 尝试解析具体数据内容（根据AFN+Fn）
                self._parse_data_unit(afn, fn_list, data_bytes, table_data, offset, is_upstream=(dir_val == 1))
                offset = cs_pos

        # 7. 校验和 CS
        if cs_pos < frame_len:
            cs_actual = frame_bytes[cs_pos]
            # 计算校验和：控制域 + 用户数据区所有字节
            if cs_pos <= frame_len:
                cs_calc = sum(frame_bytes[3:cs_pos]) & 0xFF
                cs_valid = cs_actual == cs_calc
                table_data.append((
                    "校验和(CS)",
                    f"0x{cs_actual:02X}",
                    f"0x{cs_calc:02X}",
                    "校验正确" if cs_valid else f"校验错误(期望0x{cs_calc:02X})",
                    cs_pos, cs_pos
                ))
            else:
                table_data.append((
                    "校验和(CS)",
                    f"0x{cs_actual:02X}",
                    "-",
                    "无法计算（帧长度不足）",
                    cs_pos, cs_pos
                ))

        # 8. 结束字符 16H
        if end_pos < frame_len:
            end_char = frame_bytes[end_pos]
            end_valid = end_char == 0x16
            table_data.append((
                "结束字符",
                f"0x{end_char:02X}",
                "16H" if end_valid else "错误",
                "帧结束标志" if end_valid else f"期望16H，实际0x{end_char:02X}",
                end_pos, end_pos
            ))
        elif cs_pos + 1 == frame_len:
            # 帧刚好到CS结束，没有16H
            pass
        else:
            table_data.append((
                "结束字符",
                "缺失",
                "-",
                "帧缺少结束字符16H",
                None, None
            ))

        return table_data

    def _dt_to_fn(self, dt1: int, dt2: int) -> List[int]:
        """将DT1和DT2转换为Fn列表

        DT2是信息类组(0~31)，DT1的每一位对应一个Fn。
        D0~D7对应F(DT2*8+1)~F(DT2*8+8)
        """
        fn_list = []
        base = dt2 * 8
        for i in range(8):
            if dt1 & (1 << i):
                fn_list.append(base + i + 1)
        return fn_list

    def _format_addr(self, addr_bytes: bytes) -> str:
        """将地址字节格式化为逆序的十六进制字符串

        国网协议地址域采用低字节在前存储，显示时按字节逆序
        例如: [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC] -> 'BC9A78563412'
        """
        return ''.join(f'{b:02X}' for b in reversed(addr_bytes))

    def _parse_slave_node_info_2byte(self, info_bytes: bytes, prefix: str = "") -> List[Tuple[str, str, str, str, int, int]]:
        """解析2字节从节点信息格式（表78/80/85/87/101）
        
        返回: [(字段名, 原始值, 解析值, 说明, byte_start, byte_end), ...]
        """
        results = []
        b0, b1 = info_bytes[0], info_bytes[1]
        relay_level = b0 & 0x0F
        signal_quality = (b0 >> 4) & 0x0F
        phase_bits = b1 & 0x07
        proto_type = (b1 >> 3) & 0x07
        
        phases = []
        if phase_bits & 0x01: phases.append("A相")
        if phase_bits & 0x02: phases.append("B相")
        if phase_bits & 0x04: phases.append("C相")
        phase_str = ",".join(phases) if phases else "无"
        
        proto_map = {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}
        proto_str = proto_map.get(proto_type, f"保留({proto_type})")
        
        results.append((f"{prefix}中继级别", f"0x{b0:02X}", str(relay_level), "0~15, 0=无中继", 0, 0))
        results.append((f"{prefix}侦听信号品质", f"0x{b0:02X}", str(signal_quality), "0~15", 0, 0))
        results.append((f"{prefix}相位", f"0x{b1:02X}", phase_str, f"D8~D10=相位, 0x{b1:02X}", 1, 1))
        results.append((f"{prefix}通信协议类型", f"0x{b1:02X}", proto_str, f"D11~D13, 0x{proto_type:02X}", 1, 1))
        return results

    def _parse_topology_info_5byte(self, topo_bytes: bytes, is_dual_mode: bool = True, prefix: str = "") -> List[Tuple[str, str, str, str, int, int]]:
        """解析5字节网络拓扑信息格式（表92/94）
        
        is_dual_mode: True=双模拓扑(F20), False=单模拓扑(F21)
        返回: [(字段名, 原始值, 解析值, 说明, byte_start, byte_end), ...]
        """
        results = []
        node_id = int.from_bytes(topo_bytes[0:2], 'little') & 0x0FFF
        module_type = (topo_bytes[1] >> 4) & 0x0F
        proxy_id = int.from_bytes(topo_bytes[2:4], 'little') & 0x0FFF
        info_byte = topo_bytes[4]
        
        if is_dual_mode:
            mod_map = {0: "高速载波单模", 1: "高速载波+无线双模", 2: "无线单模"}
        else:
            mod_map = {}
        
        results.append((f"{prefix}节点标识(TEI)", f"0x{topo_bytes[0]:02X}{topo_bytes[1]:02X}", str(node_id), "D0~D11", 0, 1))
        if is_dual_mode:
            results.append((f"{prefix}模块类型", f"0x{module_type:02X}", mod_map.get(module_type, f"保留({module_type})"), "D12~D15", 1, 1))
        results.append((f"{prefix}代理节点标识(TEI)", f"0x{topo_bytes[2]:02X}{topo_bytes[3]:02X}", str(proxy_id), "", 2, 3))
        
        node_level = info_byte & 0x0F
        if is_dual_mode:
            role = (info_byte >> 4) & 0x07
            channel = (info_byte >> 7) & 0x01
            role_map = {0x0: "无效", 0x1: "STA(末梢)", 0x2: "PCO(代理)", 0x3: "保留", 0x4: "CCO(主节点)"}
            results.append((f"{prefix}节点层级", f"0x{info_byte:02X}", str(node_level), "D0~D3", 4, 4))
            results.append((f"{prefix}节点角色", f"0x{info_byte:02X}", role_map.get(role, f"保留({role})"), "D4~D6", 4, 4))
            results.append((f"{prefix}网络信道", f"0x{info_byte:02X}", "无线" if channel else "载波", "D7: 0=载波,1=无线", 4, 4))
        else:
            role = (info_byte >> 4) & 0x0F
            role_map = {0x0: "无效", 0x1: "STA(末梢)", 0x2: "PCO(代理)", 0x3: "保留", 0x4: "CCO(主节点)"}
            results.append((f"{prefix}节点层级", f"0x{info_byte:02X}", str(node_level), "D0~D3", 4, 4))
            results.append((f"{prefix}节点角色", f"0x{info_byte:02X}", role_map.get(role, f"保留({role})"), "D4~D7", 4, 4))
        
        return results

    def _parse_data_unit(self, afn: int, fn_list: List[int], data_bytes: bytes, table_data: list, base_offset: int, is_upstream: bool = False):
        """根据AFN和Fn解析数据单元内容"""
        offset = 0
        data_len = len(data_bytes)

        if not fn_list:
            return

        fn = fn_list[0]  # 简化处理，只解析第一个Fn

        # AFN=00H 确认/否认
        if afn == 0x00:
            if fn == 1 and data_len >= 4:  # F1: 确认
                status = data_bytes[0]
                channel_busy = []
                for i in range(7):
                    if status & (1 << i):
                        channel_busy.append(f"信道{i+1}忙")
                    else:
                        channel_busy.append(f"信道{i+1}闲")
                cmd_status = "已处理" if (status & 0x80) else "未处理"
                table_data.append(("  命令状态", f"0x{status:02X}", cmd_status, "D7=命令状态", base_offset, base_offset))
                table_data.append(("  信道状态", "-", ", ".join(channel_busy), "D0~D6=信道1~7状态", base_offset, base_offset))
                offset += 1
                if data_len >= 2:
                    err_status = data_bytes[1]
                    table_data.append(("  错误状态字1", f"0x{err_status:02X}", str(err_status), "", base_offset + 1, base_offset + 1))
                if data_len >= 4:
                    wait_time = int.from_bytes(data_bytes[2:4], 'little')
                    table_data.append(("  等待执行时间", f"0x{data_bytes[2]:02X}{data_bytes[3]:02X}", str(wait_time), "单位: s", base_offset + 2, base_offset + 3))

            elif fn == 2 and data_len >= 1:  # F2: 否认
                err = data_bytes[0]
                err_desc = self._get_deny_error_desc(err)
                table_data.append(("  错误状态字", f"0x{err:02X}", str(err), err_desc, base_offset, base_offset))

        # AFN=02H 数据转发
        elif afn == 0x02 and fn == 1 and data_len >= 2:
            proto_type = data_bytes[0]
            proto_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45"}
            msg_len = data_bytes[1]
            table_data.append(("  通信协议类型", f"0x{proto_type:02X}", str(proto_type), proto_map.get(proto_type, "保留"), base_offset, base_offset))
            table_data.append(("  报文长度", f"0x{msg_len:02X}", str(msg_len), "字节", base_offset + 1, base_offset + 1))
            if data_len >= 2 + msg_len:
                msg_content = data_bytes[2:2+msg_len]
                table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in msg_content), f"{msg_len}字节", "原始报文数据", base_offset + 2, base_offset + 1 + msg_len))

        # AFN=03H 查询数据 - 上行响应
        elif afn == 0x03:
            if fn == 1 and data_len >= 9:  # F1: 厂商代码和版本信息
                vendor = bytes(data_bytes[0:2]).decode('ascii', errors='replace')
                chip = bytes(data_bytes[2:4]).decode('ascii', errors='replace')
                day = data_bytes[4]
                month = data_bytes[5]
                year = data_bytes[6]
                ver = int.from_bytes(data_bytes[7:9], 'big')
                table_data.append(("  厂商代码", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", vendor, "ASCII", base_offset, base_offset + 1))
                table_data.append(("  芯片代码", f"0x{data_bytes[2]:02X}{data_bytes[3]:02X}", chip, "ASCII", base_offset + 2, base_offset + 3))
                table_data.append(("  版本日期", f"{day:02X}-{month:02X}-{year:02X}", f"20{year:02X}-{month:02X}-{day:02X}", "BCD编码", base_offset + 4, base_offset + 6))
                table_data.append(("  版本", f"0x{data_bytes[7]:02X}{data_bytes[8]:02X}", f"{ver}", "BCD编码", base_offset + 7, base_offset + 8))

            elif fn == 2 and data_len >= 1:  # F2: 噪声值
                noise = data_bytes[0] & 0x0F
                table_data.append(("  噪声强度", f"0x{data_bytes[0]:02X}", str(noise), "取值0~15", base_offset, base_offset))

            elif fn == 4 and data_len >= 6:  # F4: 主节点地址
                addr = self._format_addr(data_bytes[0:6])
                table_data.append(("  主节点地址", addr, addr, "BCD编码，6字节", base_offset, base_offset + 5))

            elif fn == 7 and data_len >= 1:  # F7: 读取从节点监控最大超时时间
                timeout = data_bytes[0]
                table_data.append(("  最大超时时间", f"0x{timeout:02X}", str(timeout), "单位: s", base_offset, base_offset))

            elif fn == 8 and data_len >= 2:  # F8: 查询无线通信参数
                table_data.append(("  无线信道组", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), "0~63", base_offset, base_offset))
                power_map = {0: "最高", 1: "次高", 2: "次低", 3: "最低"}
                table_data.append(("  发射功率", f"0x{data_bytes[1]:02X}", str(data_bytes[1]), power_map.get(data_bytes[1], "保留"), base_offset + 1, base_offset + 1))

            elif fn == 16 and data_len >= 1:  # F16: 查询宽带载波通信参数
                band_map = {0: "1.953~11.96MHz", 1: "2.441~5.615MHz", 2: "0.781~2.930MHz", 3: "1.758~2.930MHz"}
                table_data.append(("  宽带载波频段", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), band_map.get(data_bytes[0], "保留"), base_offset, base_offset))

            elif fn == 17 and data_len >= 3:  # F17: 查询无线频段 (上行)
                mod_map = {2: "500kHz", 3: "200kHz"}
                table_data.append(("  无线调制方式", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), mod_map.get(data_bytes[0], "保留"), base_offset, base_offset))
                table_data.append(("  无线信道编号", f"0x{data_bytes[1]:02X}", str(data_bytes[1]), "", base_offset + 1, base_offset + 1))
                table_data.append(("  信道协商使能", f"0x{data_bytes[2]:02X}", str(data_bytes[2]), "0=禁止, 1=允许", base_offset + 2, base_offset + 2))

            elif fn == 18 and data_len >= 6:  # F18: 查询本地通信信道加密参数
                enable_map = {0: "禁止加密", 1: "允许加密"}
                mode_map = {0: "兼容模式", 1: "强制模式"}
                algo_map = {0: "国密算法", 1: "国际算法CBC", 2: "国际算法GCM"}
                table_data.append(("  加密使能标识", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), enable_map.get(data_bytes[0], "保留"), base_offset, base_offset))
                table_data.append(("  加密模式", f"0x{data_bytes[1]:02X}", str(data_bytes[1]), mode_map.get(data_bytes[1], "保留"), base_offset + 1, base_offset + 1))
                table_data.append(("  加密算法类型", f"0x{data_bytes[2]:02X}", str(data_bytes[2]), algo_map.get(data_bytes[2], "保留"), base_offset + 2, base_offset + 2))
                period = int.from_bytes(data_bytes[3:5], 'little')
                table_data.append(("  密钥更新周期", f"0x{data_bytes[3]:02X}{data_bytes[4]:02X}", str(period), "单位: 10s", base_offset + 3, base_offset + 4))

            elif fn == 3 and data_len >= 2:  # F3: 从节点侦听信息 (上行)
                total = data_bytes[0]
                count = data_bytes[1]
                table_data.append(("  侦听到的从节点总数量", f"0x{total:02X}", str(total), "", base_offset, base_offset))
                table_data.append(("  本帧传输的从节点数量", f"0x{count:02X}", str(count), "", base_offset + 1, base_offset + 1))
                offset = 2
                for i in range(count):
                    if offset + 8 > data_len:
                        table_data.append((f"  从节点{i+1}", "-", "数据不足", f"需要8字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                        break
                    addr = self._format_addr(data_bytes[offset:offset+6])
                    table_data.append((f"  从节点{i+1}地址", addr, addr, "BCD编码", base_offset + offset, base_offset + offset + 5))
                    b0 = data_bytes[offset + 6]
                    quality = (b0 >> 4) & 0x0F
                    relay = b0 & 0x0F
                    table_data.append((f"  从节点{i+1}侦听信号品质", f"0x{b0:02X}", str(quality), "D4~D7", base_offset + offset + 6, base_offset + offset + 6))
                    table_data.append((f"  从节点{i+1}中继级别", f"0x{b0:02X}", str(relay), "D0~D3", base_offset + offset + 6, base_offset + offset + 6))
                    b1 = data_bytes[offset + 7]
                    listen_count = b1 & 0x1F
                    table_data.append((f"  从节点{i+1}侦听次数", f"0x{b1:02X}", str(listen_count), "D0~D4", base_offset + offset + 7, base_offset + offset + 7))
                    offset += 8

            elif fn == 5 and data_len >= 2:  # F5: 主节点状态字和通信速率 (上行)
                status = int.from_bytes(data_bytes[0:2], 'little')
                rate_count = status & 0x0F
                channel_feat = (status >> 4) & 0x03
                meter_mode = (status >> 6) & 0x03
                channel_count = (status >> 8) & 0x0F
                feat_map = {0: "微功率无线", 1: "单相供电单相传输", 2: "单相供电三相传输", 3: "三相供电三相传输"}
                mode_map = {0: "保留", 1: "集中器主导", 2: "路由主导", 3: "都支持"}
                table_data.append(("  状态字", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", f"速率数量={rate_count}, 信道特征={feat_map.get(channel_feat,'保留')}, 抄表模式={mode_map.get(meter_mode,'保留')}, 信道数={channel_count}", "", base_offset, base_offset + 1))
                offset = 2
                for i in range(rate_count):
                    if offset + 2 > data_len:
                        table_data.append((f"  通信速率{i+1}", "-", "数据不足", f"需要2字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                        break
                    rate_val = int.from_bytes(data_bytes[offset:offset+2], 'little') & 0x7FFF
                    unit_flag = (data_bytes[offset + 1] >> 7) & 0x01
                    unit_str = "kbit/s" if unit_flag else "bit/s"
                    table_data.append((f"  通信速率{i+1}", f"0x{data_bytes[offset]:02X}{data_bytes[offset+1]:02X}", f"{rate_val} {unit_str}", f"单位标识={'kbit/s' if unit_flag else 'bit/s'}", base_offset + offset, base_offset + offset + 1))
                    offset += 2

            elif fn == 6 and data_len >= 1:  # F6: 主节点干扰状态 (上行)
                status = data_bytes[0]
                table_data.append(("  干扰状态", f"0x{status:02X}", "有干扰" if status else "没有干扰", "0=无干扰, 1=有干扰", base_offset, base_offset))

            elif fn == 9 and data_len >= 4:  # F9: 通信延时相关广播通信时长 (上行)
                delay = int.from_bytes(data_bytes[0:2], 'little')
                proto_type = data_bytes[2]
                msg_len = data_bytes[3]
                proto_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45"}
                table_data.append(("  广播通信延迟时间", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(delay), "单位: s", base_offset, base_offset + 1))
                table_data.append(("  通信协议类型", f"0x{proto_type:02X}", str(proto_type), proto_map.get(proto_type, "保留"), base_offset + 2, base_offset + 2))
                table_data.append(("  报文长度", f"0x{msg_len:02X}", str(msg_len), "字节", base_offset + 3, base_offset + 3))
                if data_len >= 4 + msg_len:
                    content = data_bytes[4:4+msg_len]
                    table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 4, base_offset + 3 + msg_len))

            elif fn == 10 and data_len >= 39:  # F10: 本地通信模块运行模式信息 (上行)
                # 6字节模式字
                b0, b1, b2, b3, b4, b5 = data_bytes[0:6]
                comm_mode = b0 & 0x0F
                route_mgmt = (b0 >> 4) & 0x01
                slave_info_mode = (b0 >> 5) & 0x01
                meter_mode = (b0 >> 6) & 0x03
                comm_map = {1: "窄带电力线载波", 2: "宽带电力线载波", 3: "微功率无线", 4: "HPLC+HRF双模"}
                meter_map = {0: "保留", 1: "集中器主导", 2: "路由主导", 3: "都支持"}
                table_data.append(("  通信方式", f"0x{b0:02X}", comm_map.get(comm_mode, f"保留({comm_mode})"), "D0~D3", base_offset, base_offset))
                table_data.append(("  路由管理方式", f"0x{b0:02X}", "有路由" if route_mgmt else "无路由", "D4", base_offset, base_offset))
                table_data.append(("  从节点信息模式", f"0x{b0:02X}", "需要下发" if slave_info_mode else "不需要下发", "D5", base_offset, base_offset))
                table_data.append(("  周期抄表模式", f"0x{b0:02X}", meter_map.get(meter_mode, "保留"), "D6~D7", base_offset, base_offset))
                
                delay_support = b1 & 0x07
                fail_switch = (b1 >> 3) & 0x03
                broadcast_ack = (b1 >> 5) & 0x01
                broadcast_channel = (b1 >> 6) & 0x03
                delay_desc = []
                if delay_support & 0x01: delay_desc.append("广播")
                if delay_support & 0x02: delay_desc.append("监控")
                if delay_support & 0x04: delay_desc.append("主动抄表")
                table_data.append(("  传输延时参数支持", f"0x{b1:02X}", ",".join(delay_desc) if delay_desc else "不支持", "D0~D2", base_offset + 1, base_offset + 1))
                table_data.append(("  失败节点切换方式", f"0x{b1:02X}", f"自主切换={'是' if fail_switch&0x01 else '否'}, 集中器发起={'是' if fail_switch&0x02 else '否'}", "D3~D4", base_offset + 1, base_offset + 1))
                table_data.append(("  广播命令确认方式", f"0x{b1:02X}", "广播前确认" if broadcast_ack else "广播后确认", "D5", base_offset + 1, base_offset + 1))
                table_data.append(("  广播命令信道执行方式", f"0x{b1:02X}", "需信道标识" if broadcast_channel else "不需要", "D6~D7", base_offset + 1, base_offset + 1))
                
                table_data.append(("  可操作信道（组）数量", f"0x{b2:02X}", str(b2), "", base_offset + 2, base_offset + 2))
                
                rate_count = b3 & 0x0F
                table_data.append(("  速率数量", f"0x{b3:02X}", str(rate_count), "D0~D3", base_offset + 3, base_offset + 3))
                
                table_data.append(("  从节点监控最大超时时间", f"0x{b4:02X}", str(b4), "单位: s", base_offset + 4, base_offset + 4))
                
                broadcast_timeout = int.from_bytes(data_bytes[5:7], 'little')
                table_data.append(("  广播命令最大超时时间", f"0x{b5:02X}{data_bytes[6]:02X}", str(broadcast_timeout), "单位: s", base_offset + 5, base_offset + 6))
                
                max_len = int.from_bytes(data_bytes[7:9], 'little')
                table_data.append(("  最大支持的报文长度", f"0x{data_bytes[7]:02X}{data_bytes[8]:02X}", str(max_len), "字节", base_offset + 7, base_offset + 8))
                
                file_pkt_len = int.from_bytes(data_bytes[9:11], 'little')
                table_data.append(("  文件传输最大分包长度", f"0x{data_bytes[9]:02X}{data_bytes[10]:02X}", str(file_pkt_len), "字节", base_offset + 9, base_offset + 10))
                
                upgrade_wait = data_bytes[11]
                table_data.append(("  升级操作等待时间", f"0x{upgrade_wait:02X}", str(upgrade_wait), "单位: min", base_offset + 11, base_offset + 11))
                
                master_addr = self._format_addr(data_bytes[12:18])
                table_data.append(("  主节点地址", master_addr, master_addr, "BCD编码", base_offset + 12, base_offset + 17))
                
                max_slave = int.from_bytes(data_bytes[18:20], 'little')
                curr_slave = int.from_bytes(data_bytes[20:22], 'little')
                table_data.append(("  支持的最大从节点数量", f"0x{data_bytes[18]:02X}{data_bytes[19]:02X}", str(max_slave), "", base_offset + 18, base_offset + 19))
                table_data.append(("  当前从节点数量", f"0x{data_bytes[20]:02X}{data_bytes[21]:02X}", str(curr_slave), "", base_offset + 20, base_offset + 21))
                
                pub_date = f"{data_bytes[22]:02X}-{data_bytes[23]:02X}-{data_bytes[24]:02X}"
                table_data.append(("  协议发布日期", pub_date, f"20{data_bytes[24]:02X}-{data_bytes[23]:02X}-{data_bytes[22]:02X}", "BCD编码,YYMMDD", base_offset + 22, base_offset + 24))
                
                reg_date = f"{data_bytes[25]:02X}-{data_bytes[26]:02X}-{data_bytes[27]:02X}"
                table_data.append(("  协议最后备案日期", reg_date, f"20{data_bytes[27]:02X}-{data_bytes[26]:02X}-{data_bytes[25]:02X}", "BCD编码,YYMMDD", base_offset + 25, base_offset + 27))
                
                vendor = bytes(data_bytes[28:30]).decode('ascii', errors='replace')
                chip = bytes(data_bytes[30:32]).decode('ascii', errors='replace')
                day = data_bytes[32]
                month = data_bytes[33]
                year = data_bytes[34]
                ver = int.from_bytes(data_bytes[35:37], 'big')
                table_data.append(("  厂商代码", f"0x{data_bytes[28]:02X}{data_bytes[29]:02X}", vendor, "ASCII", base_offset + 28, base_offset + 29))
                table_data.append(("  芯片代码", f"0x{data_bytes[30]:02X}{data_bytes[31]:02X}", chip, "ASCII", base_offset + 30, base_offset + 31))
                table_data.append(("  版本日期", f"{day:02X}-{month:02X}-{year:02X}", f"20{year:02X}-{month:02X}-{day:02X}", "BCD编码", base_offset + 32, base_offset + 34))
                table_data.append(("  版本", f"0x{data_bytes[35]:02X}{data_bytes[36]:02X}", f"{ver}", "BCD编码", base_offset + 35, base_offset + 36))
                
                offset = 37
                for i in range(rate_count):
                    if offset + 2 > data_len:
                        table_data.append((f"  通信速率{i+1}", "-", "数据不足", f"需要2字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                        break
                    rate_val = int.from_bytes(data_bytes[offset:offset+2], 'little') & 0x7FFF
                    unit_flag = (data_bytes[offset + 1] >> 7) & 0x01
                    unit_str = "kbit/s" if unit_flag else "bit/s"
                    table_data.append((f"  通信速率{i+1}", f"0x{data_bytes[offset]:02X}{data_bytes[offset+1]:02X}", f"{rate_val} {unit_str}", f"单位标识={'kbit/s' if unit_flag else 'bit/s'}", base_offset + offset, base_offset + offset + 1))
                    offset += 2

            elif fn == 11 and data_len >= 33:  # F11: 本地通信模块AFN索引 (上行)
                afn_code = data_bytes[0]
                table_data.append(("  AFN功能码", f"0x{afn_code:02X}", str(afn_code), f"AFN={afn_code:02X}H", base_offset, base_offset))
                # 32字节, 256位, D0=F1, D1=F2, ...
                support_bytes = data_bytes[1:33]
                supported = []
                for byte_idx in range(32):
                    b = support_bytes[byte_idx]
                    for bit in range(8):
                        if b & (1 << bit):
                            fn_num = byte_idx * 8 + bit + 1
                            if fn_num <= 255:
                                supported.append(f"F{fn_num}")
                table_data.append(("  支持的数据单元", ' '.join(f'{b:02X}' for b in support_bytes), f"共{len(supported)}个", ", ".join(supported[:20]) + ("..." if len(supported) > 20 else ""), base_offset + 1, base_offset + 32))

            elif fn == 12 and data_len >= 4:  # F12: 查询CCO模块ID (上行)
                vendor = bytes(data_bytes[0:2]).decode('ascii', errors='replace')
                id_len = data_bytes[2]
                id_format = data_bytes[3]
                fmt_map = {0: "组合格式", 1: "BCD", 2: "BIN", 3: "ASCII"}
                table_data.append(("  模块厂商代码", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", vendor, "ASCII", base_offset, base_offset + 1))
                table_data.append(("  模块ID长度", f"0x{id_len:02X}", str(id_len), "字节, 最长50", base_offset + 2, base_offset + 2))
                table_data.append(("  模块ID格式", f"0x{id_format:02X}", fmt_map.get(id_format, f"保留({id_format})"), "", base_offset + 3, base_offset + 3))
                if data_len >= 4 + id_len:
                    id_data = data_bytes[4:4+id_len]
                    id_str = ' '.join(f'{b:02X}' for b in id_data)
                    table_data.append(("  模块ID号", id_str, f"{id_len}字节", f"格式={fmt_map.get(id_format, '保留')}", base_offset + 4, base_offset + 3 + id_len))
                else:
                    table_data.append(("  模块ID号", "-", "数据不足", f"需要{id_len}字节", base_offset + 4, base_offset + data_len - 1))

            elif fn == 100 and data_len >= 1:  # F100: 查询场强门限
                threshold = data_bytes[0]
                table_data.append(("  场强门限", f"0x{threshold:02X}", str(threshold), "取值50~120，默认96", base_offset, base_offset))

        # AFN=04H 链路接口检测
        elif afn == 0x04:
            if fn == 1 and data_len >= 1:  # F1: 发送测试
                duration = data_bytes[0]
                table_data.append(("  持续时间", f"0x{duration:02X}", str(duration), "单位: s, 0=停止发送", base_offset, base_offset))

            elif fn == 2:  # F2: 从节点点名
                table_data.append(("  说明", "-", "无数据单元", "从节点点名命令", base_offset, base_offset))

            elif fn == 3 and data_len >= 9:  # F3: 本地通信模块报文通信测试
                rate = data_bytes[0]
                addr = self._format_addr(data_bytes[1:7])
                proto_type = data_bytes[7]
                msg_len = data_bytes[8]
                proto_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45"}
                table_data.append(("  测试通信速率", f"0x{rate:02X}", str(rate), "0=默认速率", base_offset, base_offset))
                table_data.append(("  目标地址", addr, addr, "BCD编码, 6字节", base_offset + 1, base_offset + 6))
                table_data.append(("  通信协议类型", f"0x{proto_type:02X}", str(proto_type), proto_map.get(proto_type, "保留"), base_offset + 7, base_offset + 7))
                table_data.append(("  报文长度", f"0x{msg_len:02X}", str(msg_len), "字节", base_offset + 8, base_offset + 8))
                if data_len >= 9 + msg_len:
                    content = data_bytes[9:9+msg_len]
                    table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 9, base_offset + 8 + msg_len))

        # AFN=12H 路由控制类 (重启/暂停/恢复)
        elif afn == 0x12:
            if fn == 1:  # F1: 重启
                table_data.append(("  说明", "-", "无数据单元", "重启路由", base_offset, base_offset))
            elif fn == 2:  # F2: 暂停
                table_data.append(("  说明", "-", "无数据单元", "暂停路由", base_offset, base_offset))
            elif fn == 3:  # F3: 恢复
                table_data.append(("  说明", "-", "无数据单元", "恢复路由", base_offset, base_offset))

        # AFN=05H 控制命令 - 下行
        elif afn == 0x05:
            if fn == 1 and data_len >= 6:  # F1: 设置主节点地址
                addr = self._format_addr(data_bytes[0:6])
                table_data.append(("  主节点地址", addr, addr, "BCD编码，6字节", base_offset, base_offset + 5))

            elif fn == 2 and data_len >= 1:  # F2: 允许/禁止从节点上报
                status_map = {0: "禁止", 1: "允许"}
                table_data.append(("  事件上报状态标志", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), status_map.get(data_bytes[0], "保留"), base_offset, base_offset))

            elif fn == 3 and data_len >= 2:  # F3: 启动广播
                ctrl_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "相位识别功能"}
                msg_len = data_bytes[1]
                table_data.append(("  控制字", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), ctrl_map.get(data_bytes[0], "保留"), base_offset, base_offset))
                table_data.append(("  报文长度", f"0x{msg_len:02X}", str(msg_len), "字节", base_offset + 1, base_offset + 1))
                if data_len >= 2 + msg_len:
                    content = data_bytes[2:2+msg_len]
                    table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 2, base_offset + 1 + msg_len))

            elif fn == 4 and data_len >= 1:  # F4: 设置从节点监控最大超时时间
                table_data.append(("  最大超时时间", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), "单位: s", base_offset, base_offset))

            elif fn == 5 and data_len >= 2:  # F5: 设置无线通信参数
                table_data.append(("  无线信道组", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), "0~63, 254=自动, 255=保持", base_offset, base_offset))
                power_map = {0: "最高", 1: "次高", 2: "次低", 3: "最低"}
                table_data.append(("  发射功率", f"0x{data_bytes[1]:02X}", str(data_bytes[1]), power_map.get(data_bytes[1], "保留/保持"), base_offset + 1, base_offset + 1))

            elif fn == 6 and data_len >= 1:  # F6: 允许/禁止台区识别
                status_map = {0: "禁止", 1: "允许"}
                table_data.append(("  台区识别使能标志", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), status_map.get(data_bytes[0], "保留"), base_offset, base_offset))

            elif fn == 10 and data_len >= 1:  # F10: 串口速率配置
                rate_map = {0: "9600", 1: "19200", 2: "38400", 3: "57600", 4: "115200"}
                table_data.append(("  通信速率", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), f"{rate_map.get(data_bytes[0], '保留')} bit/s", base_offset, base_offset))

            elif fn == 16 and data_len >= 1:  # F16: 设置宽带载波通信参数
                band_map = {0: "1.953~11.96MHz", 1: "2.441~5.615MHz", 2: "0.781~2.930MHz", 3: "1.758~2.930MHz"}
                table_data.append(("  宽带载波频段", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), band_map.get(data_bytes[0], "保留"), base_offset, base_offset))

            elif fn == 17 and data_len >= 3:  # F17: 设置无线频段
                table_data.append(("  无线调制方式", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), "2=500kHz, 3=200kHz", base_offset, base_offset))
                table_data.append(("  无线信道编号", f"0x{data_bytes[1]:02X}", str(data_bytes[1]), "", base_offset + 1, base_offset + 1))
                table_data.append(("  信道协商使能", f"0x{data_bytes[2]:02X}", str(data_bytes[2]), "0=禁止, 1=允许", base_offset + 2, base_offset + 2))

            elif fn == 18 and data_len >= 6:  # F18: 允许/禁止本地通信信道加密
                enable_map = {0: "禁止加密", 1: "允许加密"}
                mode_map = {0: "兼容模式", 1: "强制模式"}
                algo_map = {0: "国密算法", 1: "国际算法CBC", 2: "国际算法GCM"}
                table_data.append(("  加密使能标识", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), enable_map.get(data_bytes[0], "保留"), base_offset, base_offset))
                table_data.append(("  加密模式", f"0x{data_bytes[1]:02X}", str(data_bytes[1]), mode_map.get(data_bytes[1], "保留"), base_offset + 1, base_offset + 1))
                table_data.append(("  加密算法类型", f"0x{data_bytes[2]:02X}", str(data_bytes[2]), algo_map.get(data_bytes[2], "保留"), base_offset + 2, base_offset + 2))
                period = int.from_bytes(data_bytes[3:5], 'little')
                table_data.append(("  密钥更新周期", f"0x{data_bytes[3]:02X}{data_bytes[4]:02X}", str(period), "单位: 10s, 0=缺省", base_offset + 3, base_offset + 4))

            elif fn == 20 and data_len >= 3:  # F20: 广播透传命令
                ctrl_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45"}
                msg_len = int.from_bytes(data_bytes[1:3], 'little')
                table_data.append(("  控制字", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), ctrl_map.get(data_bytes[0], "保留"), base_offset, base_offset))
                table_data.append(("  报文长度", f"0x{data_bytes[1]:02X}{data_bytes[2]:02X}", str(msg_len), "字节", base_offset + 1, base_offset + 2))
                if data_len >= 3 + msg_len:
                    content = data_bytes[3:3+msg_len]
                    table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 3, base_offset + 2 + msg_len))

            elif fn == 100 and data_len >= 1:  # F100: 设置场强门限
                table_data.append(("  场强门限", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), "取值50~120，默认96", base_offset, base_offset))

            elif fn == 101 and data_len >= 6:  # F101: 设置中心节点时间
                table_data.append(("  秒", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), "BCD", base_offset, base_offset))
                table_data.append(("  分", f"0x{data_bytes[1]:02X}", str(data_bytes[1]), "BCD", base_offset + 1, base_offset + 1))
                table_data.append(("  时", f"0x{data_bytes[2]:02X}", str(data_bytes[2]), "BCD", base_offset + 2, base_offset + 2))
                table_data.append(("  日", f"0x{data_bytes[3]:02X}", str(data_bytes[3]), "BCD", base_offset + 3, base_offset + 3))
                table_data.append(("  月", f"0x{data_bytes[4]:02X}", str(data_bytes[4]), "BCD", base_offset + 4, base_offset + 4))
                table_data.append(("  年", f"0x{data_bytes[5]:02X}", str(data_bytes[5]), "BCD", base_offset + 5, base_offset + 5))

            elif fn == 200 and data_len >= 1:  # F200: 控制拒绝节点上报
                status_map = {0: "禁止", 1: "允许"}
                table_data.append(("  拒绝节点上报标志", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), status_map.get(data_bytes[0], "保留"), base_offset, base_offset))

        # AFN=06H 主动上报
        elif afn == 0x06:
            if fn == 1 and data_len >= 1:  # F1: 上报从节点信息
                count = data_bytes[0]
                table_data.append(("  上报从节点数量", f"0x{count:02X}", str(count), "", base_offset, base_offset))
                offset = 1
                for i in range(count):
                    if offset + 9 > data_len:
                        break
                    addr = self._format_addr(data_bytes[offset:offset+6])
                    proto_type = data_bytes[offset+6]
                    seq = int.from_bytes(data_bytes[offset+7:offset+9], 'little')
                    table_data.append((f"  从节点{i+1}地址", addr, addr, "BCD", base_offset + offset, base_offset + offset + 5))
                    table_data.append((f"  从节点{i+1}协议类型", f"0x{proto_type:02X}", str(proto_type), "", base_offset + offset + 6, base_offset + offset + 6))
                    table_data.append((f"  从节点{i+1}序号", f"0x{data_bytes[offset+7]:02X}{data_bytes[offset+8]:02X}", str(seq), "", base_offset + offset + 7, base_offset + offset + 8))
                    offset += 9

            elif fn == 2 and data_len >= 6:  # F2: 上报抄读数据
                seq = int.from_bytes(data_bytes[0:2], 'little')
                proto_type = data_bytes[2]
                duration = int.from_bytes(data_bytes[3:5], 'little')
                msg_len = data_bytes[5]
                table_data.append(("  从节点序号", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(seq), "", base_offset, base_offset + 1))
                table_data.append(("  通信协议类型", f"0x{proto_type:02X}", str(proto_type), "", base_offset + 2, base_offset + 2))
                table_data.append(("  上行时长", f"0x{data_bytes[3]:02X}{data_bytes[4]:02X}", str(duration), "单位: s", base_offset + 3, base_offset + 4))
                table_data.append(("  报文长度", f"0x{msg_len:02X}", str(msg_len), "字节", base_offset + 5, base_offset + 5))
                if data_len >= 6 + msg_len:
                    content = data_bytes[6:6+msg_len]
                    table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 6, base_offset + 5 + msg_len))

            elif fn == 3 and data_len >= 1:  # F3: 上报路由工况变动信息
                change_map = {1: "抄表任务结束", 2: "搜表任务结束", 3: "台区识别任务结束"}
                table_data.append(("  路由工作任务变动类型", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), change_map.get(data_bytes[0], "保留"), base_offset, base_offset))

            elif fn == 4 and data_len >= 1:  # F4: 上报从节点信息及设备类型
                count = data_bytes[0]
                table_data.append(("  上报从节点数量", f"0x{count:02X}", str(count), "", base_offset, base_offset))
                offset = 1
                for i in range(count):
                    if offset + 12 > data_len:
                        table_data.append((f"  从节点{i+1}", "-", "数据不足", f"需要至少12字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                        break
                    addr = self._format_addr(data_bytes[offset:offset+6])
                    proto_type = data_bytes[offset+6]
                    seq = int.from_bytes(data_bytes[offset+7:offset+9], 'little')
                    dev_type = data_bytes[offset+9]
                    sub_total = data_bytes[offset+10]
                    sub_count = data_bytes[offset+11]
                    dev_map = {0x00: "采集器", 0x01: "电能表"}
                    proto_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45"}
                    table_data.append((f"  从节点{i+1}通信地址", addr, addr, "BCD", base_offset + offset, base_offset + offset + 5))
                    table_data.append((f"  从节点{i+1}协议类型", f"0x{proto_type:02X}", str(proto_type), proto_map.get(proto_type, "保留"), base_offset + offset + 6, base_offset + offset + 6))
                    table_data.append((f"  从节点{i+1}序号", f"0x{data_bytes[offset+7]:02X}{data_bytes[offset+8]:02X}", str(seq), "", base_offset + offset + 7, base_offset + offset + 8))
                    table_data.append((f"  从节点{i+1}设备类型", f"0x{dev_type:02X}", dev_map.get(dev_type, f"保留(0x{dev_type:02X})"), "", base_offset + offset + 9, base_offset + offset + 9))
                    table_data.append((f"  从节点{i+1}下接从节点总数量", f"0x{sub_total:02X}", str(sub_total), "M", base_offset + offset + 10, base_offset + offset + 10))
                    table_data.append((f"  从节点{i+1}本次传输数量", f"0x{sub_count:02X}", str(sub_count), "m", base_offset + offset + 11, base_offset + offset + 11))
                    offset += 12
                    for j in range(sub_count):
                        if offset + 7 > data_len:
                            table_data.append((f"    下接从节点{j+1}", "-", "数据不足", f"需要7字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                            break
                        sub_addr = self._format_addr(data_bytes[offset:offset+6])
                        sub_proto = data_bytes[offset+6]
                        table_data.append((f"    下接从节点{j+1}通信地址", sub_addr, sub_addr, "BCD", base_offset + offset, base_offset + offset + 5))
                        table_data.append((f"    下接从节点{j+1}协议类型", f"0x{sub_proto:02X}", str(sub_proto), proto_map.get(sub_proto, "保留"), base_offset + offset + 6, base_offset + offset + 6))
                        offset += 7

            elif fn == 5 and data_len >= 3:  # F5: 上报从节点事件
                dev_type_map = {0x00: "采集器", 0x01: "电能表", 0x02: "HPLC通信单元", 0x03: "窄带载波通信单元", 0x04: "微功率无线通信单元", 0x05: "微功率+HPLC通信单元", 0x06: "微功率+窄带通信单元"}
                proto_map = {0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45", 0x04: "停复电事件", 0x05: "台区改切拒绝节点上报"}
                table_data.append(("  从节点设备类型", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), dev_type_map.get(data_bytes[0], "保留"), base_offset, base_offset))
                table_data.append(("  通信协议类型", f"0x{data_bytes[1]:02X}", str(data_bytes[1]), proto_map.get(data_bytes[1], "保留"), base_offset + 1, base_offset + 1))
                msg_len = data_bytes[2]
                table_data.append(("  报文长度", f"0x{msg_len:02X}", str(msg_len), "字节", base_offset + 2, base_offset + 2))
                if data_len >= 3 + msg_len:
                    content = data_bytes[3:3+msg_len]
                    table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 3, base_offset + 2 + msg_len))

        # AFN=11H 路由设置类 (下行)
        elif afn == 0x11:
            if fn == 1 and data_len >= 1:  # F1: 添加从节点
                count = data_bytes[0]
                table_data.append(("  从节点数量", f"0x{count:02X}", str(count), "", base_offset, base_offset))
                offset = 1
                proto_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45"}
                for i in range(count):
                    if offset + 7 > data_len:
                        table_data.append((f"  从节点{i+1}", "-", "数据不足", f"需要7字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                        break
                    addr = self._format_addr(data_bytes[offset:offset+6])
                    proto_type = data_bytes[offset+6]
                    table_data.append((f"  从节点{i+1}地址", addr, addr, "BCD", base_offset + offset, base_offset + offset + 5))
                    table_data.append((f"  从节点{i+1}通信协议类型", f"0x{proto_type:02X}", str(proto_type), proto_map.get(proto_type, "保留"), base_offset + offset + 6, base_offset + offset + 6))
                    offset += 7

            elif fn == 2 and data_len >= 1:  # F2: 删除从节点
                count = data_bytes[0]
                table_data.append(("  从节点数量", f"0x{count:02X}", str(count), "", base_offset, base_offset))
                offset = 1
                for i in range(count):
                    if offset + 6 > data_len:
                        table_data.append((f"  从节点{i+1}", "-", "数据不足", f"需要6字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                        break
                    addr = self._format_addr(data_bytes[offset:offset+6])
                    table_data.append((f"  从节点{i+1}地址", addr, addr, "BCD", base_offset + offset, base_offset + offset + 5))
                    offset += 6

            elif fn == 3 and data_len >= 7:  # F3: 设置从节点固定中继路径
                addr = self._format_addr(data_bytes[0:6])
                table_data.append(("  从节点地址", addr, addr, "BCD", base_offset, base_offset + 5))
                relay_level = data_bytes[6]
                table_data.append(("  中继级别", f"0x{relay_level:02X}", str(relay_level), "0~15", base_offset + 6, base_offset + 6))
                offset = 7
                for i in range(relay_level):
                    if offset + 6 > data_len:
                        table_data.append((f"  第{i+1}级中继地址", "-", "数据不足", f"需要6字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                        break
                    raddr = self._format_addr(data_bytes[offset:offset+6])
                    table_data.append((f"  第{i+1}级中继从节点地址", raddr, raddr, "BCD", base_offset + offset, base_offset + offset + 5))
                    offset += 6

            elif fn == 4 and data_len >= 1:  # F4: 设置路由工作模式
                mode = data_bytes[0]
                work_state = mode & 0x01
                reg_allow = (mode >> 1) & 0x01
                fec = (mode >> 4) & 0x0F
                table_data.append(("  工作模式", f"0x{mode:02X}", f"状态={'学习' if work_state else '抄表'}, 注册={'允许' if reg_allow else '禁止'}, 纠错编码={fec}", "", base_offset, base_offset))
                offset = 1
                # 速率数量由前面的状态字决定？实际上这里是变长的
                # 文档: 工作模式(1B) + n×[速率单位标识+通信速率](2B)
                # 但n是多少？从文档看不明确，按剩余字节/2来解析
                rate_count = (data_len - 1) // 2
                for i in range(rate_count):
                    if offset + 2 > data_len:
                        break
                    rate_val = int.from_bytes(data_bytes[offset:offset+2], 'little') & 0x7FFF
                    unit_flag = (data_bytes[offset + 1] >> 7) & 0x01
                    unit_str = "kbit/s" if unit_flag else "bit/s"
                    table_data.append((f"  通信速率{i+1}", f"0x{data_bytes[offset]:02X}{data_bytes[offset+1]:02X}", f"{rate_val} {unit_str}", f"单位标识={'kbit/s' if unit_flag else 'bit/s'}", base_offset + offset, base_offset + offset + 1))
                    offset += 2

            elif fn == 5 and data_len >= 10:  # F5: 激活从节点主动注册
                start_time = ''.join(f'{b:02X}' for b in data_bytes[0:6])
                duration = int.from_bytes(data_bytes[6:8], 'little')
                retry = data_bytes[8]
                wait_slots = data_bytes[9]
                table_data.append(("  开始时间", start_time, f"20{data_bytes[5]:02X}-{data_bytes[4]:02X}-{data_bytes[3]:02X} {data_bytes[2]:02X}:{data_bytes[1]:02X}:{data_bytes[0]:02X}", "BCD编码, YYMMDDhhmmss", base_offset, base_offset + 5))
                table_data.append(("  持续时间", f"0x{data_bytes[6]:02X}{data_bytes[7]:02X}", str(duration), "单位: min", base_offset + 6, base_offset + 7))
                table_data.append(("  从节点重发次数", f"0x{retry:02X}", str(retry), "", base_offset + 8, base_offset + 8))
                table_data.append(("  随机等待时间片个数", f"0x{wait_slots:02X}", str(wait_slots), "时间片=150ms", base_offset + 9, base_offset + 9))

            elif fn == 100 and data_len >= 2:  # F100: 设置网络规模
                scale = int.from_bytes(data_bytes[0:2], 'little')
                table_data.append(("  网络规模", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(scale), "", base_offset, base_offset + 1))

        # AFN=13H 路由数据转发类
        elif afn == 0x13:
            if fn in (1, 2) and data_len >= 3:
                proto_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45"}
                if not is_upstream:
                    # 下行: 协议类型(1B) + 延时标志(1B) + 附属节点数量n + n×[地址(6B)] + 报文长度L + 报文内容
                    proto_type = data_bytes[0]
                    delay_flag = data_bytes[1]
                    sub_count = data_bytes[2]
                    table_data.append(("  通信协议类型", f"0x{proto_type:02X}", str(proto_type), proto_map.get(proto_type, "保留"), base_offset, base_offset))
                    table_data.append(("  通信延时相关性标志", f"0x{delay_flag:02X}", "与延时相关" if delay_flag == 0x01 else "与延时无关", "0=无关,1=相关", base_offset + 1, base_offset + 1))
                    table_data.append(("  从节点附属节点数量", f"0x{sub_count:02X}", str(sub_count), "", base_offset + 2, base_offset + 2))
                    offset = 3
                    for i in range(sub_count):
                        if offset + 6 > data_len:
                            table_data.append((f"  附属节点{i+1}", "-", "数据不足", f"需要6字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                            break
                        addr = self._format_addr(data_bytes[offset:offset+6])
                        table_data.append((f"  附属节点{i+1}地址", addr, addr, "BCD", base_offset + offset, base_offset + offset + 5))
                        offset += 6
                    if fn == 1 and data_len >= offset + 1:
                        msg_len = data_bytes[offset]
                        table_data.append(("  报文长度", f"0x{msg_len:02X}", str(msg_len), "字节", base_offset + offset, base_offset + offset))
                        if data_len >= offset + 1 + msg_len:
                            content = data_bytes[offset+1:offset+1+msg_len]
                            table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + offset + 1, base_offset + offset + msg_len))
                    elif fn == 2 and data_len >= offset + 2:
                        msg_len = int.from_bytes(data_bytes[offset:offset+2], 'little')
                        table_data.append(("  报文长度", f"0x{data_bytes[offset]:02X}{data_bytes[offset+1]:02X}", str(msg_len), "字节", base_offset + offset, base_offset + offset + 1))
                        if data_len >= offset + 2 + msg_len:
                            content = data_bytes[offset+2:offset+2+msg_len]
                            table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + offset + 2, base_offset + offset + 1 + msg_len))
                else:
                    # 上行: 上行时长(2B) + 协议类型(1B) + 报文长度L + 报文内容
                    duration = int.from_bytes(data_bytes[0:2], 'little')
                    proto_type = data_bytes[2]
                    table_data.append(("  当前报文本地通信上行时长", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(duration), "单位: s", base_offset, base_offset + 1))
                    table_data.append(("  通信协议类型", f"0x{proto_type:02X}", str(proto_type), proto_map.get(proto_type, "保留"), base_offset + 2, base_offset + 2))
                    if fn == 1 and data_len >= 4:
                        msg_len = data_bytes[3]
                        table_data.append(("  报文长度", f"0x{msg_len:02X}", str(msg_len), "字节", base_offset + 3, base_offset + 3))
                        if data_len >= 4 + msg_len:
                            content = data_bytes[4:4+msg_len]
                            table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 4, base_offset + 3 + msg_len))
                    elif fn == 2 and data_len >= 5:
                        msg_len = int.from_bytes(data_bytes[3:5], 'little')
                        table_data.append(("  报文长度", f"0x{data_bytes[3]:02X}{data_bytes[4]:02X}", str(msg_len), "字节", base_offset + 3, base_offset + 4))
                        if data_len >= 5 + msg_len:
                            content = data_bytes[5:5+msg_len]
                            table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 5, base_offset + 4 + msg_len))

        # AFN=14H 路由数据抄读类
        elif afn == 0x14:
            if fn == 1:
                if is_upstream and data_len >= 9:
                    phase = data_bytes[0]
                    phase_map = {0: "未知相", 1: "A相", 2: "B相", 3: "C相"}
                    addr = self._format_addr(data_bytes[1:7])
                    seq = int.from_bytes(data_bytes[7:9], 'little')
                    table_data.append(("  通信相位", f"0x{phase:02X}", phase_map.get(phase, "保留"), "0=未知,1~3=第1~3相", base_offset, base_offset))
                    table_data.append(("  从节点地址", addr, addr, "BCD", base_offset + 1, base_offset + 6))
                    table_data.append(("  从节点序号", f"0x{data_bytes[7]:02X}{data_bytes[8]:02X}", str(seq), "", base_offset + 7, base_offset + 8))
                elif not is_upstream and data_len >= 3:
                    flag = data_bytes[0]
                    flag_map = {0x00: "抄读失败", 0x01: "抄读成功", 0x02: "可以抄读"}
                    delay_flag = data_bytes[1]
                    data_len_field = data_bytes[2]
                    table_data.append(("  抄读标志", f"0x{flag:02X}", flag_map.get(flag, "保留"), "", base_offset, base_offset))
                    table_data.append(("  通信延时相关性标志", f"0x{delay_flag:02X}", "与延时相关" if delay_flag == 0x01 else "与延时无关", "", base_offset + 1, base_offset + 1))
                    table_data.append(("  路由请求数据长度", f"0x{data_len_field:02X}", str(data_len_field), "字节", base_offset + 2, base_offset + 2))
                    offset = 3
                    if data_len >= 3 + data_len_field:
                        content = data_bytes[3:3+data_len_field]
                        table_data.append(("  路由请求数据内容", ' '.join(f'{b:02X}' for b in content), f"{data_len_field}字节", "DL/T 645数据", base_offset + 3, base_offset + 2 + data_len_field))
                        offset = 3 + data_len_field
                    if data_len >= offset + 1:
                        sub_count = data_bytes[offset]
                        table_data.append(("  从节点附属节点数量", f"0x{sub_count:02X}", str(sub_count), "", base_offset + offset, base_offset + offset))
                        offset += 1
                        for i in range(sub_count):
                            if offset + 6 > data_len:
                                table_data.append((f"  附属节点{i+1}", "-", "数据不足", f"需要6字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                                break
                            addr = self._format_addr(data_bytes[offset:offset+6])
                            table_data.append((f"  附属节点{i+1}地址", addr, addr, "BCD", base_offset + offset, base_offset + offset + 5))
                            offset += 6

            elif fn == 2:
                if is_upstream:
                    table_data.append(("  说明", "-", "无数据单元", "路由请求集中器时钟上行", base_offset, base_offset))
                elif data_len >= 6:
                    table_data.append(("  秒", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), "BCD", base_offset, base_offset))
                    table_data.append(("  分", f"0x{data_bytes[1]:02X}", str(data_bytes[1]), "BCD", base_offset + 1, base_offset + 1))
                    table_data.append(("  时", f"0x{data_bytes[2]:02X}", str(data_bytes[2]), "BCD", base_offset + 2, base_offset + 2))
                    table_data.append(("  日", f"0x{data_bytes[3]:02X}", str(data_bytes[3]), "BCD", base_offset + 3, base_offset + 3))
                    table_data.append(("  月", f"0x{data_bytes[4]:02X}", str(data_bytes[4]), "BCD", base_offset + 4, base_offset + 4))
                    table_data.append(("  年(低字节)", f"0x{data_bytes[5]:02X}", str(data_bytes[5]), "BCD", base_offset + 5, base_offset + 5))

            elif fn == 3:
                if is_upstream and data_len >= 9:
                    addr = self._format_addr(data_bytes[0:6])
                    delay = int.from_bytes(data_bytes[6:8], 'little')
                    data_len_field = data_bytes[8]
                    table_data.append(("  从节点地址", addr, addr, "BCD", base_offset, base_offset + 5))
                    table_data.append(("  预计延迟时间", f"0x{data_bytes[6]:02X}{data_bytes[7]:02X}", str(delay), "单位: s", base_offset + 6, base_offset + 7))
                    table_data.append(("  抄读信息长度", f"0x{data_len_field:02X}", str(data_len_field), "字节", base_offset + 8, base_offset + 8))
                    if data_len >= 9 + data_len_field:
                        content = data_bytes[9:9+data_len_field]
                        table_data.append(("  抄读数据内容", ' '.join(f'{b:02X}' for b in content), f"{data_len_field}字节", "", base_offset + 9, base_offset + 8 + data_len_field))
                elif not is_upstream and data_len >= 1:
                    data_len_field = data_bytes[0]
                    table_data.append(("  数据长度", f"0x{data_len_field:02X}", str(data_len_field), "字节", base_offset, base_offset))
                    if data_len >= 1 + data_len_field:
                        content = data_bytes[1:1+data_len_field]
                        table_data.append(("  修正通信数据内容", ' '.join(f'{b:02X}' for b in content), f"{data_len_field}字节", "DL/T 645数据, 已按延迟时间修订", base_offset + 1, base_offset + data_len_field))

            elif fn == 4:
                if is_upstream and data_len >= 5:
                    item_type = data_bytes[0]
                    type_map = {1: "DL/T 645-2007", 2: "DL/T 698.45"}
                    item_id = ' '.join(f'{b:02X}' for b in data_bytes[1:5])
                    table_data.append(("  数据项类型", f"0x{item_type:02X}", type_map.get(item_type, f"保留({item_type})"), "", base_offset, base_offset))
                    table_data.append(("  交采数据项标识", item_id, item_id, "4字节", base_offset + 1, base_offset + 4))
                elif not is_upstream and data_len >= 5:
                    item_type = data_bytes[0]
                    type_map = {1: "DL/T 645-2007", 2: "DL/T 698.45"}
                    item_id = ' '.join(f'{b:02X}' for b in data_bytes[1:5])
                    table_data.append(("  数据项类型", f"0x{item_type:02X}", type_map.get(item_type, f"保留({item_type})"), "", base_offset, base_offset))
                    table_data.append(("  交采数据项标识", item_id, item_id, "4字节", base_offset + 1, base_offset + 4))
                    offset = 5
                    if data_len > offset:
                        content = data_bytes[offset:]
                        table_data.append(("  交采数据项内容", ' '.join(f'{b:02X}' for b in content), f"{len(content)}字节", "", base_offset + offset, base_offset + data_len - 1))

        # AFN=15H 文件传输类
        elif afn == 0x15:
            if fn == 1:
                if not is_upstream and data_len >= 9:
                    file_id = data_bytes[0]
                    attr = data_bytes[1]
                    cmd = data_bytes[2]
                    total_seg = int.from_bytes(data_bytes[3:5], 'little')
                    seg_id = int.from_bytes(data_bytes[5:9], 'little')
                    file_map = {0x00: "清除下装文件", 0x03: "本地通信模块升级文件", 0x07: "主节点和子节点模块升级", 0x08: "子节点模块升级"}
                    attr_map = {0x00: "起始帧/中间帧", 0x01: "结束帧"}
                    cmd_map = {0x00: "报文方式下装"}
                    table_data.append(("  文件标识", f"0x{file_id:02X}", file_map.get(file_id, f"保留({file_id})"), "", base_offset, base_offset))
                    table_data.append(("  文件属性", f"0x{attr:02X}", attr_map.get(attr, f"保留({attr})"), "", base_offset + 1, base_offset + 1))
                    table_data.append(("  文件指令", f"0x{cmd:02X}", cmd_map.get(cmd, f"保留({cmd})"), "", base_offset + 2, base_offset + 2))
                    table_data.append(("  总段数", f"0x{data_bytes[3]:02X}{data_bytes[4]:02X}", str(total_seg), "", base_offset + 3, base_offset + 4))
                    table_data.append(("  第i段标识", f"0x{data_bytes[5]:02X}{data_bytes[6]:02X}{data_bytes[7]:02X}{data_bytes[8]:02X}", str(seg_id), "i=0~n", base_offset + 5, base_offset + 8))
                    if data_len >= 11:
                        seg_len = int.from_bytes(data_bytes[9:11], 'little')
                        table_data.append(("  第i段数据长度", f"0x{data_bytes[9]:02X}{data_bytes[10]:02X}", str(seg_len), "字节", base_offset + 9, base_offset + 10))
                        if data_len >= 11 + seg_len:
                            file_data = data_bytes[11:11+seg_len]
                            table_data.append(("  文件数据", ' '.join(f'{b:02X}' for b in file_data), f"{seg_len}字节", "", base_offset + 11, base_offset + 10 + seg_len))
                elif is_upstream and data_len >= 4:
                    seg_id = int.from_bytes(data_bytes[0:4], 'little')
                    table_data.append(("  收到当前段标识", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}{data_bytes[2]:02X}{data_bytes[3]:02X}", str(seg_id), "0xFFFF=文件错误", base_offset, base_offset + 3))

        # AFN=10H 路由查询
        elif afn == 0x10:
            if fn == 1 and data_len >= 4:  # F1: 从节点数量 (上行)
                total = int.from_bytes(data_bytes[0:2], 'little')
                max_nodes = int.from_bytes(data_bytes[2:4], 'little')
                table_data.append(("  从节点总数量", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(total), "", base_offset, base_offset + 1))
                table_data.append(("  路由支持最大从节点数量", f"0x{data_bytes[2]:02X}{data_bytes[3]:02X}", str(max_nodes), "", base_offset + 2, base_offset + 3))

            elif fn in (2, 5, 6) and data_len >= 3:  # F2/F5/F6: 从节点信息
                if is_upstream and data_len >= 3:
                    # 上行: 从节点总数量(2B) + 本次应答数量n(1B) + n*[地址(6B)+信息(2B)]
                    total = int.from_bytes(data_bytes[0:2], 'little')
                    count = data_bytes[2]
                    table_data.append(("  从节点总数量", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(total), "", base_offset, base_offset + 1))
                    table_data.append(("  本次应答数量", f"0x{count:02X}", str(count), "", base_offset + 2, base_offset + 2))
                    offset = 3
                    for i in range(count):
                        if offset + 8 > data_len:
                            table_data.append((f"  从节点{i+1}", "-", "数据不足", f"需要8字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                            break
                        addr = self._format_addr(data_bytes[offset:offset+6])
                        table_data.append((f"  从节点{i+1}地址", addr, addr, "BCD编码", base_offset + offset, base_offset + offset + 5))
                        info_items = self._parse_slave_node_info_2byte(data_bytes[offset+6:offset+8], prefix=f"  从节点{i+1}")
                        for name, raw, val, desc, bs, be in info_items:
                            table_data.append((name, raw, val, desc, base_offset + offset + 6 + bs, base_offset + offset + 6 + be))
                        offset += 8
                else:
                    # 下行: 节点起始序号(2B) + 节点数量(1B)
                    start_seq = int.from_bytes(data_bytes[0:2], 'little')
                    count = data_bytes[2]
                    table_data.append(("  节点起始序号", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(start_seq), "", base_offset, base_offset + 1))
                    table_data.append(("  节点数量", f"0x{count:02X}", str(count), "", base_offset + 2, base_offset + 2))

            elif fn == 3 and data_len >= 6:  # F3: 指定从节点的上一级中继路由信息
                addr = self._format_addr(data_bytes[0:6])
                table_data.append(("  从节点地址", addr, addr, "BCD编码，6字节", base_offset, base_offset + 5))
                if is_upstream and data_len >= 7:
                    count = data_bytes[6]
                    table_data.append(("  提供路由的从节点数量", f"0x{count:02X}", str(count), "", base_offset + 6, base_offset + 6))
                    offset = 7
                    for i in range(count):
                        if offset + 8 > data_len:
                            table_data.append((f"  路由从节点{i+1}", "-", "数据不足", f"需要8字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                            break
                        raddr = self._format_addr(data_bytes[offset:offset+6])
                        table_data.append((f"  路由从节点{i+1}地址", raddr, raddr, "BCD编码", base_offset + offset, base_offset + offset + 5))
                        info_items = self._parse_slave_node_info_2byte(data_bytes[offset+6:offset+8], prefix=f"  路由从节点{i+1}")
                        for name, raw, val, desc, bs, be in info_items:
                            table_data.append((name, raw, val, desc, base_offset + offset + 6 + bs, base_offset + offset + 6 + be))
                        offset += 8

            elif fn == 4 and data_len >= 16:  # F4: 路由运行状态 (上行)
                status = data_bytes[0]
                route_done = status & 0x01
                working = (status >> 1) & 0x01
                event_flag = (status >> 2) & 0x01
                fec = (status >> 4) & 0x0F
                table_data.append(("  运行状态字", f"0x{status:02X}", f"路由完成={'是' if route_done else '否'}, 工作中={'是' if working else '否'}, 事件={'有' if event_flag else '无'}", f"纠错编码={fec}", base_offset, base_offset))
                
                total = int.from_bytes(data_bytes[1:3], 'little')
                copied = int.from_bytes(data_bytes[3:5], 'little')
                relay_copied = int.from_bytes(data_bytes[5:7], 'little')
                table_data.append(("  从节点总数量", f"0x{data_bytes[1]:02X}{data_bytes[2]:02X}", str(total), "", base_offset + 1, base_offset + 2))
                table_data.append(("  已抄从节点数量", f"0x{data_bytes[3]:02X}{data_bytes[4]:02X}", str(copied), "", base_offset + 3, base_offset + 4))
                table_data.append(("  中继抄到从节点数量", f"0x{data_bytes[5]:02X}{data_bytes[6]:02X}", str(relay_copied), "", base_offset + 5, base_offset + 6))
                
                switch = data_bytes[7]
                work_state = switch & 0x01
                reg_allow = (switch >> 2) & 0x01
                event_allow = (switch >> 3) & 0x01
                district_id = (switch >> 4) & 0x01
                curr_state = (switch >> 6) & 0x03
                state_map = {0: "抄表", 1: "报表", 2: "升级", 3: "其他"}
                table_data.append(("  工作开关", f"0x{switch:02X}", f"状态={state_map.get(curr_state,'未知')}, 学习={'是' if work_state else '抄表'}, 注册={'允许' if reg_allow else '禁止'}, 台区={'允许' if district_id else '禁止'}", "", base_offset + 7, base_offset + 7))
                
                rate = int.from_bytes(data_bytes[8:10], 'little')
                table_data.append(("  通信速率", f"0x{data_bytes[8]:02X}{data_bytes[9]:02X}", str(rate), "窄带载波速率, HPLC填0", base_offset + 8, base_offset + 9))
                
                for phase in range(1, 4):
                    lvl = data_bytes[9 + phase]
                    table_data.append((f"  第{phase}相中继级别", f"0x{lvl:02X}", str(lvl), "0~15, 0=无中继", base_offset + 9 + phase, base_offset + 9 + phase))
                
                step_map = {1: "初始", 2: "直抄", 3: "中继", 4: "监控", 5: "广播", 6: "广播召读电能表", 7: "读侦听信息", 8: "空闲"}
                for phase in range(1, 4):
                    step = data_bytes[12 + phase]
                    table_data.append((f"  第{phase}相工作步骤", f"0x{step:02X}", str(step), step_map.get(step, "备用"), base_offset + 12 + phase, base_offset + 12 + phase))

            elif fn == 7 and data_len >= 3:  # F7: 查询从节点ID信息
                if is_upstream and data_len >= 3:
                    total = int.from_bytes(data_bytes[0:2], 'little')
                    count = data_bytes[2]
                    table_data.append(("  从节点总数量", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(total), "", base_offset, base_offset + 1))
                    table_data.append(("  本次应答数量", f"0x{count:02X}", str(count), "", base_offset + 2, base_offset + 2))
                    offset = 3
                    for i in range(count):
                        if offset + 11 > data_len:
                            table_data.append((f"  从节点{i+1}", "-", "数据不足", f"需要至少11字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                            break
                        addr = self._format_addr(data_bytes[offset:offset+6])
                        table_data.append((f"  从节点{i+1}地址", addr, addr, "", base_offset + offset, base_offset + offset + 5))
                        node_type = data_bytes[offset + 6]
                        updated = (node_type >> 7) & 0x01
                        mod_type = node_type & 0x0F
                        mod_map = {0: "电能表模块", 1: "采集器模块", 15: "未知"}
                        table_data.append((f"  从节点{i+1}节点类型", f"0x{node_type:02X}", f"{mod_map.get(mod_type, '保留')}({'未更新' if updated else '已更新'})", "Bit7=更新标识", base_offset + offset + 6, base_offset + offset + 6))
                        vendor = bytes(data_bytes[offset+7:offset+9]).decode('ascii', errors='replace')
                        table_data.append((f"  从节点{i+1}模块厂商代码", f"0x{data_bytes[offset+7]:02X}{data_bytes[offset+8]:02X}", vendor, "ASCII", base_offset + offset + 7, base_offset + offset + 8))
                        id_len = data_bytes[offset + 9]
                        id_format = data_bytes[offset + 10]
                        fmt_map = {0: "组合格式", 1: "BCD", 2: "BIN", 3: "ASCII"}
                        table_data.append((f"  从节点{i+1}模块ID长度", f"0x{id_len:02X}", str(id_len), "字节", base_offset + offset + 9, base_offset + offset + 9))
                        table_data.append((f"  从节点{i+1}模块ID格式", f"0x{id_format:02X}", fmt_map.get(id_format, f"保留({id_format})"), "", base_offset + offset + 10, base_offset + offset + 10))
                        if data_len >= offset + 11 + id_len:
                            id_data = data_bytes[offset+11:offset+11+id_len]
                            id_str = ' '.join(f'{b:02X}' for b in id_data)
                            table_data.append((f"  从节点{i+1}模块ID号", id_str, f"{id_len}字节", f"格式={fmt_map.get(id_format, '保留')}", base_offset + offset + 11, base_offset + offset + 10 + id_len))
                            offset += 11 + id_len
                        else:
                            table_data.append((f"  从节点{i+1}模块ID号", "-", "数据不足", f"需要{id_len}字节", base_offset + offset + 11, base_offset + data_len - 1))
                            break
                else:
                    start_seq = int.from_bytes(data_bytes[0:2], 'little')
                    count = data_bytes[2]
                    table_data.append(("  节点起始序号", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(start_seq), "", base_offset, base_offset + 1))
                    table_data.append(("  节点数量", f"0x{count:02X}", str(count), "", base_offset + 2, base_offset + 2))

            elif fn == 9 and data_len >= 2:  # F9: 查询网络规模 (上行)
                scale = int.from_bytes(data_bytes[0:2], 'little')
                table_data.append(("  网络规模", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(scale), "HPLC网络节点数", base_offset, base_offset + 1))

            elif fn in (20, 21, 31, 112) and data_len >= 3:  # F20/F21/F31/F112: 拓扑/相线/芯片信息
                if is_upstream:
                    # 上行: 节点总数量(2B) + 节点起始序号(2B) + 本次应答数量n(1B) + n*[...]
                    total = int.from_bytes(data_bytes[0:2], 'little')
                    start_seq = int.from_bytes(data_bytes[2:4], 'little')
                    count = data_bytes[4]
                    table_data.append(("  节点总数量", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(total), "", base_offset, base_offset + 1))
                    table_data.append(("  节点起始序号", f"0x{data_bytes[2]:02X}{data_bytes[3]:02X}", str(start_seq), "", base_offset + 2, base_offset + 3))
                    table_data.append(("  本次应答数量", f"0x{count:02X}", str(count), "", base_offset + 4, base_offset + 4))
                    offset = 5
                    for i in range(count):
                        if fn in (20, 21):
                            # F20/F21: 地址(6B) + 拓扑信息(5B)
                            if offset + 11 > data_len:
                                table_data.append((f"  节点{i+1}", "-", "数据不足", f"需要11字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                                break
                            addr = self._format_addr(data_bytes[offset:offset+6])
                            table_data.append((f"  节点{i+1}地址", addr, addr, "", base_offset + offset, base_offset + offset + 5))
                            topo_items = self._parse_topology_info_5byte(data_bytes[offset+6:offset+11], is_dual_mode=(fn==20), prefix=f"  节点{i+1}")
                            for name, raw, val, desc, bs, be in topo_items:
                                table_data.append((name, raw, val, desc, base_offset + offset + 6 + bs, base_offset + offset + 6 + be))
                            offset += 11
                        elif fn == 31:
                            # F31: 地址(6B) + 相线信息(2B)
                            if offset + 8 > data_len:
                                table_data.append((f"  节点{i+1}", "-", "数据不足", f"需要8字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                                break
                            addr = self._format_addr(data_bytes[offset:offset+6])
                            table_data.append((f"  节点{i+1}地址", addr, addr, "", base_offset + offset, base_offset + offset + 5))
                            phase_info = int.from_bytes(data_bytes[offset+6:offset+8], 'little')
                            b0 = data_bytes[offset + 6]
                            b1 = data_bytes[offset + 7]
                            phases = []
                            if b0 & 0x01: phases.append("A相")
                            if b0 & 0x02: phases.append("B相")
                            if b0 & 0x04: phases.append("C相")
                            phase_str = ",".join(phases) if phases else "无/识别中"
                            meter_type = (b0 >> 3) & 0x01
                            line_err = (b0 >> 4) & 0x01
                            seq_type = (b0 >> 5) & 0x07
                            seq_map = {0: "ABC(正常)", 1: "ACB", 2: "BAC", 3: "BCA", 4: "CAB", 5: "CBA"}
                            table_data.append((f"  节点{i+1}相位信息", f"0x{b0:02X}", phase_str, "D0~D2=相位", base_offset + offset + 6, base_offset + offset + 6))
                            table_data.append((f"  节点{i+1}电能表类型", f"0x{b0:02X}", "三相表" if meter_type else "单相表", "D3", base_offset + offset + 6, base_offset + offset + 6))
                            table_data.append((f"  节点{i+1}线路异常", f"0x{b0:02X}", "异常" if line_err else "正常/不支持", "D4: 0=正常,1=异常", base_offset + offset + 6, base_offset + offset + 6))
                            table_data.append((f"  节点{i+1}相序类型", f"0x{b0:02X}", seq_map.get(seq_type, f"保留({seq_type})"), "D5~D7", base_offset + offset + 6, base_offset + offset + 6))
                            table_data.append((f"  节点{i+1}备用", f"0x{b1:02X}", str(b1), "Bit8~Bit15备用", base_offset + offset + 7, base_offset + offset + 7))
                            offset += 8
                        elif fn == 112:
                            # F112: 地址(6B) + 设备类型(1B) + 芯片ID(24B) + 软件版本(2B)
                            if offset + 33 > data_len:
                                table_data.append((f"  节点{i+1}", "-", "数据不足", f"需要33字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                                break
                            addr = self._format_addr(data_bytes[offset:offset+6])
                            table_data.append((f"  节点{i+1}地址", addr, addr, "", base_offset + offset, base_offset + offset + 5))
                            dev_type = data_bytes[offset + 6]
                            dev_map = {1: "抄控器", 2: "集中器本地通信单元", 3: "单相电能表通信单元", 4: "中继器", 5: "II型采集器", 6: "I型采集器", 7: "三相电能表通信单元"}
                            table_data.append((f"  节点{i+1}设备类型", f"0x{dev_type:02X}", dev_map.get(dev_type, f"保留({dev_type})"), "", base_offset + offset + 6, base_offset + offset + 6))
                            chip_id = data_bytes[offset+7:offset+31]
                            chip_str = ' '.join(f'{b:02X}' for b in chip_id)
                            # Parse chip ID details
                            chip_desc = f"类别=0x{chip_id[6]:02X}, 厂商=0x{chip_id[7]:02X}{chip_id[8]:02X}, 型号=0x{chip_id[9]:02X}{chip_id[10]:02X}"
                            table_data.append((f"  节点{i+1}芯片ID", chip_str, chip_desc, "24字节, 见表104", base_offset + offset + 7, base_offset + offset + 30))
                            sw_ver = int.from_bytes(data_bytes[offset+31:offset+33], 'big')
                            table_data.append((f"  节点{i+1}芯片软件版本", f"0x{data_bytes[offset+31]:02X}{data_bytes[offset+32]:02X}", f"{sw_ver}", "BCD编码", base_offset + offset + 31, base_offset + offset + 32))
                            offset += 33
                else:
                    # 下行: 节点起始序号(2B) + 节点数量(1B)
                    start_seq = int.from_bytes(data_bytes[0:2], 'little')
                    count = data_bytes[2]
                    table_data.append(("  节点起始序号", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(start_seq), "", base_offset, base_offset + 1))
                    table_data.append(("  节点数量", f"0x{count:02X}", str(count), f"最大支持{'64' if fn in (20,21,31) else '查询'}个", base_offset + 2, base_offset + 2))

            elif fn == 40 and data_len >= 1:  # F40: 流水线查询ID信息
                dev_type_map = {1: "抄控器", 2: "CCO", 3: "电能表通信单元", 4: "中继器", 5: "II型采集器", 6: "I型采集器", 7: "三相表通信单元"}
                id_type_map = {1: "芯片ID", 2: "模块ID"}
                if is_upstream and data_len >= 10:
                    table_data.append(("  设备类型", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), dev_type_map.get(data_bytes[0], "保留"), base_offset, base_offset))
                    addr = self._format_addr(data_bytes[1:7])
                    table_data.append(("  节点地址", addr, addr, "MAC地址倒序，6字节", base_offset + 1, base_offset + 6))
                    id_type = data_bytes[7]
                    id_len = data_bytes[8]
                    table_data.append(("  ID类型", f"0x{id_type:02X}", str(id_type), id_type_map.get(id_type, "保留"), base_offset + 7, base_offset + 7))
                    table_data.append(("  ID长度", f"0x{id_len:02X}", str(id_len), "字节", base_offset + 8, base_offset + 8))
                    if data_len >= 9 + id_len:
                        id_data = data_bytes[9:9+id_len]
                        id_str = ' '.join(f'{b:02X}' for b in id_data)
                        table_data.append(("  ID信息", id_str, f"{id_len}字节", "", base_offset + 9, base_offset + 8 + id_len))
                    else:
                        table_data.append(("  ID信息", "-", "数据不足", f"需要{id_len}字节", base_offset + 9, base_offset + data_len - 1))
                elif not is_upstream and data_len >= 8:
                    table_data.append(("  设备类型", f"0x{data_bytes[0]:02X}", str(data_bytes[0]), dev_type_map.get(data_bytes[0], "保留"), base_offset, base_offset))
                    addr = self._format_addr(data_bytes[1:7])
                    table_data.append(("  节点地址", addr, addr, "MAC地址倒序，6字节", base_offset + 1, base_offset + 6))
                    table_data.append(("  ID类型", f"0x{data_bytes[7]:02X}", str(data_bytes[7]), id_type_map.get(data_bytes[7], "保留"), base_offset + 7, base_offset + 7))

            elif fn == 100 and data_len >= 2:  # F100: 查询微功率无线网络规模 (上行)
                scale = int.from_bytes(data_bytes[0:2], 'little')
                table_data.append(("  网络规模", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(scale), "微功率无线网络节点数", base_offset, base_offset + 1))

            elif fn == 101 and data_len >= 3:  # F101: 查询微功率无线从节点信息
                if is_upstream and data_len >= 3:
                    total = int.from_bytes(data_bytes[0:2], 'little')
                    count = data_bytes[2]
                    table_data.append(("  从节点总数量", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(total), "", base_offset, base_offset + 1))
                    table_data.append(("  本次应答数量", f"0x{count:02X}", str(count), "", base_offset + 2, base_offset + 2))
                    offset = 3
                    for i in range(count):
                        if offset + 11 > data_len:
                            table_data.append((f"  从节点{i+1}", "-", "数据不足", f"需要11字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                            break
                        addr = self._format_addr(data_bytes[offset:offset+6])
                        table_data.append((f"  从节点{i+1}地址", addr, addr, "BCD编码", base_offset + offset, base_offset + offset + 5))
                        info_items = self._parse_slave_node_info_2byte(data_bytes[offset+6:offset+8], prefix=f"  从节点{i+1}")
                        for name, raw, val, desc, bs, be in info_items:
                            table_data.append((name, raw, val, desc, base_offset + offset + 6 + bs, base_offset + offset + 6 + be))
                        # 软件版本: boot(1B) + app(2B)
                        boot_ver = data_bytes[offset + 8]
                        app_ver = int.from_bytes(data_bytes[offset+9:offset+11], 'big')
                        table_data.append((f"  从节点{i+1}Bootloader版本", f"0x{boot_ver:02X}", str(boot_ver), "", base_offset + offset + 8, base_offset + offset + 8))
                        table_data.append((f"  从节点{i+1}应用程序版本", f"0x{data_bytes[offset+9]:02X}{data_bytes[offset+10]:02X}", f"{app_ver}", "BCD编码", base_offset + offset + 9, base_offset + offset + 10))
                        offset += 11
                else:
                    start_seq = int.from_bytes(data_bytes[0:2], 'little')
                    count = data_bytes[2]
                    table_data.append(("  节点起始序号", f"0x{data_bytes[0]:02X}{data_bytes[1]:02X}", str(start_seq), "", base_offset, base_offset + 1))
                    table_data.append(("  节点数量", f"0x{count:02X}", str(count), "", base_offset + 2, base_offset + 2))

            elif fn == 104:  # F104: 查询升级后模块版本信息
                if is_upstream and data_len >= 1:
                    table_data.append(("  说明", "-", "升级后模块版本信息", f"{data_len}字节数据", base_offset, base_offset + data_len - 1))
                elif not is_upstream:
                    table_data.append(("  说明", "-", "无数据单元", "查询升级后模块版本信息", base_offset, base_offset))

            elif fn == 111 and data_len >= 10:  # F111: 查询网络信息 (上行)
                n = data_bytes[0]
                nid = int.from_bytes(data_bytes[1:4], 'big')
                master_addr = self._format_addr(data_bytes[4:10])
                table_data.append(("  多网络节点总数量", f"0x{n:02X}", str(n), "邻居网络数", base_offset, base_offset))
                table_data.append(("  本节点网络标识号(NID)", f"0x{data_bytes[1]:02X}{data_bytes[2]:02X}{data_bytes[3]:02X}", str(nid), "3字节, 1~16777215", base_offset + 1, base_offset + 3))
                table_data.append(("  本节点主节点地址", master_addr, master_addr, "", base_offset + 4, base_offset + 9))
                offset = 10
                for i in range(n):
                    if offset + 3 > data_len:
                        table_data.append((f"  邻居节点{i+1}NID", "-", "数据不足", f"需要3字节,剩余{data_len-offset}", base_offset + offset, base_offset + data_len - 1))
                        break
                    neighbor_nid = int.from_bytes(data_bytes[offset:offset+3], 'big')
                    table_data.append((f"  邻居节点{i+1}网络标识号", f"0x{data_bytes[offset]:02X}{data_bytes[offset+1]:02X}{data_bytes[offset+2]:02X}", str(neighbor_nid), "", base_offset + offset, base_offset + offset + 2))
                    offset += 3

        # AFN=F1H 并发抄表
        elif afn == 0xF1:
            if fn in (1, 2):
                proto_map = {0x00: "透明传输", 0x01: "DL/T 645-1997", 0x02: "DL/T 645-2007", 0x03: "DL/T 698.45"}
                if not is_upstream and data_len >= 4:
                    # 下行: 规约类型(1B) + 保留(1B) + 报文长度L(2B) + 报文内容(L字节)
                    proto_type = data_bytes[0]
                    reserved = data_bytes[1]
                    msg_len = int.from_bytes(data_bytes[2:4], 'little')
                    table_data.append(("  规约类型", f"0x{proto_type:02X}", str(proto_type), proto_map.get(proto_type, "保留"), base_offset, base_offset))
                    table_data.append(("  保留", f"0x{reserved:02X}", str(reserved), "", base_offset + 1, base_offset + 1))
                    table_data.append(("  报文长度", f"0x{data_bytes[2]:02X}{data_bytes[3]:02X}", str(msg_len), "字节", base_offset + 2, base_offset + 3))
                    if data_len >= 4 + msg_len:
                        content = data_bytes[4:4+msg_len]
                        table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 4, base_offset + 3 + msg_len))
                    else:
                        table_data.append(("  报文内容", "-", "数据不足", f"需要{msg_len}字节,实际{data_len-4}", base_offset + 4, base_offset + data_len - 1))
                elif is_upstream and data_len >= 3:
                    # 上行: 规约类型(1B) + 报文长度L(2B) + 报文内容(L字节)
                    proto_type = data_bytes[0]
                    msg_len = int.from_bytes(data_bytes[1:3], 'little')
                    table_data.append(("  规约类型", f"0x{proto_type:02X}", str(proto_type), proto_map.get(proto_type, "保留"), base_offset, base_offset))
                    table_data.append(("  报文长度", f"0x{data_bytes[1]:02X}{data_bytes[2]:02X}", str(msg_len), "字节", base_offset + 1, base_offset + 2))
                    if msg_len == 0:
                        table_data.append(("  报文内容", "-", "抄表失败", "报文长度=0,链路层源地址为失败电能表地址", base_offset + 3, base_offset + data_len - 1))
                    elif data_len >= 3 + msg_len:
                        content = data_bytes[3:3+msg_len]
                        table_data.append(("  报文内容", ' '.join(f'{b:02X}' for b in content), f"{msg_len}字节", "原始报文数据", base_offset + 3, base_offset + 2 + msg_len))
                    else:
                        table_data.append(("  报文内容", "-", "数据不足", f"需要{msg_len}字节,实际{data_len-3}", base_offset + 3, base_offset + data_len - 1))

        # 未知AFN+Fn或自定义命令：显示数据单元为hex字符串
        if data_len > 0:
            # Check if this AFN+Fn was handled above
            handled = False
            for item in table_data:
                if item[0].startswith("  ") and not item[0].startswith("  邻居"):
                    # There are parsed sub-fields
                    if base_offset <= (item[4] or 0) <= base_offset + data_len - 1:
                        handled = True
                        break
            if not handled:
                hex_str = ' '.join(f'{b:02X}' for b in data_bytes)
                afn_name = self.get_afn_name(afn)
                fn_name = self.get_fn_name(afn, fn)
                table_data.append(("  用户数据(HEX)", hex_str, f"{data_len}字节", f"AFN={afn:02X}H({afn_name}) {fn_name} - 数据单元按HEX展示", base_offset, base_offset + data_len - 1))

    def _get_deny_error_desc(self, err: int) -> str:
        """获取否认错误状态字说明"""
        error_map = {
            0: "通信超时",
            1: "无效数据单元",
            2: "长度错",
            3: "校验错误",
            4: "信息类不存在",
            5: "格式错误",
            6: "表号重复",
            7: "表号不存在",
            8: "电能表应用层无应答",
            9: "主节点忙",
            10: "主节点不支持此命令",
            11: "从节点不应答",
            12: "从节点不在网内",
            109: "超过最大并发数",
            110: "超过单个帧最大允许的电能表协议报文条数",
            111: "正在抄读该表",
        }
        if 13 <= err <= 108:
            return "备用"
        if 112 <= err <= 255:
            return "备用"
        return error_map.get(err, "未知")

    def get_afn_fn_list(self) -> List[Tuple[int, str, int, str]]:
        """获取所有AFN+Fn组合列表，用于查询功能（包含自定义条目）

        返回: [(afn, afn_name, fn, fn_name), ...]
        """
        # Build merged maps (custom overrides standard)
        merged_afn = dict(self.AFN_MAP)
        merged_afn.update(self._custom_afn_map)
        merged_fn: Dict[int, Dict[int, str]] = {}
        for afn, fn_dict in self.FN_MAP.items():
            merged_fn[afn] = dict(fn_dict)
        for afn, fn_dict in self._custom_fn_map.items():
            if afn not in merged_fn:
                merged_fn[afn] = {}
            merged_fn[afn].update(fn_dict)

        # Collect all AFNs that have either a name or at least one Fn
        all_afns = set(merged_afn.keys()) | set(merged_fn.keys())
        result = []
        for afn in sorted(all_afns):
            afn_name = merged_afn.get(afn, f"扩展AFN({afn:02X}H)")
            for fn in sorted(merged_fn.get(afn, {}).keys()):
                fn_name = merged_fn[afn][fn]
                result.append((afn, afn_name, fn, fn_name))
        return result

    def search_afn_fn(self, keyword: str) -> List[Tuple[int, str, int, str]]:
        """根据关键词搜索AFN+Fn组合

        支持搜索AFN十六进制(如03H)、Fn编号(如F1)、中文关键词
        """
        keyword = keyword.strip().upper()
        if not keyword:
            return self.get_afn_fn_list()

        results = []
        for afn, afn_name, fn, fn_name in self.get_afn_fn_list():
            # 构建搜索文本
            afn_hex = f"{afn:02X}H"
            fn_str = f"F{fn}"
            search_text = f"{afn_hex} {afn_name} {fn_str} {fn_name}".upper()

            if keyword in search_text:
                results.append((afn, afn_name, fn, fn_name))

        return results
