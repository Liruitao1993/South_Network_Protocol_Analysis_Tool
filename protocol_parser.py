import struct
from typing import Dict, Any, Optional, Tuple
from protocol_tool import ControlField
import ctypes


class ProtocolFrameParser:
    """南网协议帧解析器"""

    # AFN 定义（集中器 + 采集器 + 无线维护）
    AFN_MAP = {
        0x00: "确认/否认",
        0x01: "初始化模块",
        0x02: "管理任务",
        0x03: "读参数",
        0x04: "写参数",
        0x05: "上报信息",
        0x06: "请求信息",
        0x07: "传输文件",
        0x10: "维护命令（无线维护）",
        0x21: "管理电表（采集器）",
        0x22: "转发数据（采集器）",
        0x23: "读参数（采集器）",
        0x24: "传输文件（采集器）",
        0x25: "请求信息（采集器）",
        0x31: "管理映射表表计（采集器）",
        0xF0: "维护模块（厂家自定义）",
    }

    # DI3 映射
    DI3_MAP = {
        0xE8: "集中器与本地模块通信",
        0xEA: "采集器与本地模块通信"
    }

    # DI2 映射
    DI2_MAP = {
        0x00: "上下行均用，下行无数据内容",
        0x01: "上下行均用，数据内容格式一致",
        0x02: "仅下行用，上行为确认/否认报文",
        0x03: "仅下行用，带数据内容",
        0x04: "仅上行用，带数据内容",
        0x05: "仅上行用，下行为确认/否认报文",
        0x06: "上下行均用，上行无数据内容"
    }

    def parse_to_table(self, frame_bytes: bytes) -> list:
        """解析为表格数据格式（最多 2 级：父字段和子字段）

        返回：[(字段名，原始值，解析值，说明, byte_start, byte_end), ...]
        """
        table_data = []

        # 解析帧
        result = self.parse(frame_bytes)
        frame_len = len(frame_bytes)

        # 计算帧结构偏移量
        length_val = int.from_bytes(frame_bytes[1:3], 'little')
        user_data_len = length_val - 6
        cs_pos = 4 + user_data_len  # 校验和位置

        # 获取地址域标识
        add_flag = 0
        if "控制域" in result:
            ctrl = result["控制域"]
            if "地址域标识(ADD)" in ctrl:
                add_flag = ctrl["地址域标识(ADD)"]["值"]

        # 第 1 级：帧的各个组成部分
        for key, value in result.items():
            # 跳过辅助字段
            if key in ["原始数据", "解析状态", "错误信息"]:
                continue

            if isinstance(value, dict):
                if key == "帧头":
                    self._add_field(table_data, "起始字符", value.get("起始字符"), "", "帧起始标志", 0, 0)

                elif key == "长度域":
                    raw = value.get("原始字节", f"0x{value.get('长度值', 0):04X}" if value.get("长度值", 0) > 255 else f"0x{value.get('长度值', 0):02X}")
                    parsed = str(value.get("长度值", "-"))
                    comment = f"{value.get('说明', '')}, {value.get('字节序', '')}，{value.get('字节长度', '')}字节"
                    self._add_field(table_data, "长度域", raw, parsed, comment, 1, 2)

                elif key == "控制域":
                    raw = value.get("原始字节", "-")
                    self._add_field(table_data, "控制域", raw, "", "", 3, 3)
                    for subkey, subvalue in value.items():
                        if subkey == "原始字节":
                            continue
                        if isinstance(subvalue, dict):
                            val = subvalue.get("值", "-")
                            desc = subvalue.get("说明", "")
                            self._add_field(table_data, f"  {subkey.split('(')[0]}", "-", str(val), desc, 3, 3, is_child=True)

                elif key == "用户数据区":
                    self._parse_user_data_to_table(value, table_data, add_flag, cs_pos, frame_len)

                elif key == "校验和":
                    raw = value.get("校验值", "-")
                    parsed = value.get("计算值", "-")
                    result_val = value.get("校验结果", "-")
                    self._add_field(table_data, "校验和", raw, parsed, result_val, cs_pos, cs_pos)

                elif key == "结束符":
                    raw = value.get("结束字符", "-")
                    result_val = value.get("校验结果", "-")
                    self._add_field(table_data, "结束符", raw, "-", result_val, frame_len - 1, frame_len - 1)

        return table_data
    
    def _add_field(self, table_data: list, field_name: str, raw_value: str, parsed_value: str, comment: str, byte_start: Optional[int] = None, byte_end: Optional[int] = None, is_child: bool = False):
        """添加字段到表格

        byte_start/byte_end: 该字段在原始帧中的字节范围（包含两端），None 表示无对应字节
        """
        prefix = "  " if is_child else ""
        full_name = f"{prefix}{field_name}"
        table_data.append((full_name, raw_value, parsed_value, comment, byte_start, byte_end))
    
    @staticmethod
    def _estimate_byte_size(value: dict) -> int:
        """从解析字典的原始值推算字节长度，用于精准高亮"""
        raw = value.get("原始值", value.get("原始字节", ""))
        if not isinstance(raw, str):
            return 0
        clean = raw.replace("0x", "").replace("0X", "").replace(" ", "").replace("-", "")
        if clean and all(c in '0123456789abcdefABCDEF' for c in clean):
            return len(clean) // 2
        return 0

    def _parse_user_data_to_table(self, user_data: dict, table_data: list,
                                  add_flag: int, cs_pos: int, frame_len: int):
        """解析用户数据区到表格（最多 2 级），含字节偏移"""
        offset = 4  # 用户数据区在帧中的起始位置

        # 地址域
        if "地址域" in user_data:
            addr = user_data["地址域"]
            self._add_field(table_data, "地址域", "", "", "", offset, offset + 11)
            self._add_field(table_data, "  源地址", addr.get("源地址", "-"), "", "", offset, offset + 5, is_child=True)
            self._add_field(table_data, "  目的地址", addr.get("目的地址", "-"), "", "", offset + 6, offset + 11, is_child=True)
            offset += 12

        # 应用功能码 AFN
        afn_keys = [k for k in user_data.keys() if "AFN" in k]
        if afn_keys:
            afn_key = afn_keys[0]
            afn = user_data[afn_key]
            raw = str(afn.get("原始值", "-"))
            name = str(afn.get("名称", ""))
            self._add_field(table_data, "应用功能码 (AFN)", raw, "", name, offset, offset)
            offset += 1

        # 帧序列号 SEQ
        seq_keys = [k for k in user_data.keys() if "SEQ" in k]
        if seq_keys:
            seq_key = seq_keys[0]
            seq = user_data[seq_key]
            raw = str(seq.get("原始值", "-"))
            val = str(seq.get("十进制", "-"))
            self._add_field(table_data, "帧序列号 (SEQ)", raw, val, "", offset, offset)
            offset += 1

        # 数据标识 DI
        di_keys = [k for k in user_data.keys() if "(DI)" in k]
        if di_keys:
            di_key = di_keys[0]
            di = user_data[di_key]
            raw = str(di.get("原始值", "-"))
            val = str(di.get("整数值", "-"))
            desc = str(di.get("业务说明", ""))
            self._add_field(table_data, "数据标识 (DI)", raw, val, desc, offset, offset + 3)
            offset += 4

        # 数据标识内容 — 字节范围: offset 到 cs_pos-1
        data_end = cs_pos - 1
        has_bytes = offset <= data_end

        if "数据标识内容" in user_data:
            content = user_data["数据标识内容"]
            if isinstance(content, dict):
                rng = (offset, data_end) if has_bytes else (None, None)
                self._add_field(table_data, "数据标识内容", "", "", "", rng[0], rng[1])

                sub_offset = offset  # 子字段偏移跟踪
                _skip_keys = {"原始值", "十进制", "说明", "描述", "值", "整数值", "业务说明", "单位", "原始字节", "原始数据", "校验结果", "解析状态", "错误信息"}

                for key, value in content.items():
                    if isinstance(value, dict):
                        raw = str(value.get("原始值", value.get("原始字节", "-")))
                        val = str(value.get("十进制", value.get("说明", "-")))
                        desc = str(value.get("说明", "")) if isinstance(value.get("说明", ""), str) else ""

                        # 尝试从原始值推算字节长度，实现精准高亮
                        byte_size = self._estimate_byte_size(value)
                        if byte_size > 0 and sub_offset + byte_size - 1 <= data_end:
                            f_start, f_end = sub_offset, sub_offset + byte_size - 1
                            sub_offset += byte_size
                        else:
                            f_start, f_end = rng

                        self._add_field(table_data, f"  {key}", raw, val, desc, f_start, f_end, is_child=True)

                        # 显示dict中的子字段（如任务模式字的响应标识、优先级等）
                        for sub_key, sub_value in value.items():
                            if sub_key in _skip_keys:
                                continue
                            if isinstance(sub_value, str):
                                self._add_field(table_data, f"    {sub_key}", "-", sub_value, "", f_start, f_end, is_child=True)
                            elif isinstance(sub_value, dict):
                                sv = sub_value.get("说明", sub_value.get("值", str(sub_value)))
                                sd = sub_value.get("说明", "")
                                self._add_field(table_data, f"    {sub_key}", "-", str(sv), str(sd) if sd != sv else "", f_start, f_end, is_child=True)

                    elif isinstance(value, list):
                        # 列表字段（如从节点列表），使用父范围
                        self._add_field(table_data, f"  {key}", f"共{len(value)}项", "", "", rng[0], rng[1], is_child=True)
                        for item in value:
                            if isinstance(item, dict):
                                for ik, iv in item.items():
                                    if ik in _skip_keys:
                                        continue
                                    if isinstance(iv, dict):
                                        iraw = str(iv.get("原始值", iv.get("原始字节", "-")))
                                        ival = str(iv.get("十进制", iv.get("说明", "-")))
                                        idesc = str(iv.get("说明", "")) if isinstance(iv.get("说明", ""), str) else ""
                                        self._add_field(table_data, f"    {ik}", iraw, ival, idesc, rng[0], rng[1], is_child=True)
                                        # 显示dict子字段的子字段
                                        for sik, siv in iv.items():
                                            if sik in _skip_keys:
                                                continue
                                            if isinstance(siv, str):
                                                self._add_field(table_data, f"      {sik}", "-", siv, "", rng[0], rng[1], is_child=True)
                                            elif isinstance(siv, dict):
                                                ssv = siv.get("说明", siv.get("值", str(siv)))
                                                self._add_field(table_data, f"      {sik}", "-", str(ssv), "", rng[0], rng[1], is_child=True)
                                    else:
                                        self._add_field(table_data, f"    {ik}", str(iv), "", "", rng[0], rng[1], is_child=True)
                    else:
                        # 纯字符串/数值：尝试从hex字符串推算字节长度
                        str_val = str(value)
                        byte_size = 0
                        clean = str_val.replace(" ", "").replace("0x", "").replace("0X", "").replace("-", "")
                        if clean and all(c in '0123456789abcdefABCDEF' for c in clean):
                            byte_size = len(clean) // 2

                        if byte_size > 0 and sub_offset + byte_size - 1 <= data_end:
                            f_start, f_end = sub_offset, sub_offset + byte_size - 1
                            sub_offset += byte_size
                        else:
                            f_start, f_end = None, None

                        self._add_field(table_data, f"  {key}", str_val, "", "", f_start, f_end, is_child=True)
    
    def _get_di_key(self, user_data: dict) -> tuple:
        """获取 DI 的键"""
        if "数据标识 (DI)" not in user_data:
            return None
        
        di = user_data["数据标识 (DI)"]
        if "整数值" in di:
            di_int = int(di["整数值"], 16) if isinstance(di["整数值"], str) else di["整数值"]
            # 从 DI 组合映射中找到对应的键
            di3 = (di_int >> 24) & 0xFF
            di2 = (di_int >> 16) & 0xFF
            di1 = (di_int >> 8) & 0xFF
            di0 = di_int & 0xFF
            return (di3, di2, di1, di0)
        return None
    
    def _parse_data_content_to_table(self, di_key: tuple, content: dict, table_data: list):
        """解析数据标识内容到表格（第 2 级）"""
        self._add_field(table_data, "数据标识内容", "", "", "")
        
        # 遍历内容字段
        for key, value in content.items():
            if isinstance(value, dict):
                raw = value.get("原始值", "-")
                val = value.get("十进制", value.get("说明", "-"))
                desc = value.get("说明", "") if isinstance(value.get("说明", ""), str) else ""
                self._add_field(table_data, f"  {key}", raw, str(val), desc, is_child=True)
            else:
                # 简单值（如报文内容）
                self._add_field(table_data, f"  {key}", str(value), "", "", is_child=True)
    
    def _flatten_to_table(self, data: dict, table_data: list, indent: int = 0):
        """递归扁平化解析结果为表格数据"""
        prefix = "  " * indent
        
        for key, value in data.items():
            # 跳过辅助字段
            if key in ["原始值", "解析值", "说明", "描述", "值", "十进制", "名称", "原始字节", "校验结果", "整数值", "业务说明"]:
                continue
            
            if isinstance(value, dict):
                # 检查是否是结构化数据
                if self._is_structured(value):
                    # 提取值
                    raw = self._get_raw_value(value)
                    parsed = self._get_parsed_value(value)
                    comment = self._get_comment(value)
                    table_data.append((f"{prefix}{key}", raw, parsed, comment))
                else:
                    # 父节点 - 但对于某些特定字段，需要提取汇总信息
                    field_name = f"{prefix}{key}"
                    
                    # 特殊处理：长度域、控制域、校验和、结束符等
                    if key in ["长度域", "校验和", "结束符"]:
                        # 提取子字段的汇总信息
                        raw_val, parsed_val, comment_val = self._get_summary_for_parent(value)
                        table_data.append((field_name, raw_val, parsed_val, comment_val))
                        # 不再递归显示子字段（避免重复）
                    else:
                        # 普通父节点，只显示字段名
                        table_data.append((field_name, "", "", ""))
                        self._flatten_to_table(value, table_data, indent + 1)
            elif isinstance(value, list):
                table_data.append((f"{prefix}{key}", f"共{len(value)}项", "", ""))
                for item in value:
                    if isinstance(item, dict):
                        self._flatten_to_table(item, table_data, indent + 1)
                    else:
                        table_data.append((f"{prefix}  项", str(item), "", ""))
            else:
                # 简单值
                table_data.append((f"{prefix}{key}", str(value) if value is not None else "-", "", ""))
    
    def _get_summary_for_parent(self, data: dict) -> tuple:
        """为特定父节点提取汇总信息"""
        raw_value = "-"
        parsed_value = "-"
        comment = ""
        
        # 长度域的特殊处理
        if "原始数据" in data or "原始字节" in data:
            # 有原始数据/字节，提取
            raw_value = data.get("原始数据", data.get("原始字节", "-"))
        elif "长度值" in data:
            # 长度域：提取十六进制值
            length_val = data.get("长度值", "-")
            if isinstance(length_val, int):
                # 尝试找到原始字节
                if "原始字节" in data:
                    raw_value = data["原始字节"]
                else:
                    # 转换为十六进制
                    raw_value = f"0x{length_val:04X}" if length_val > 255 else f"0x{length_val:02X}"
            parsed_value = str(length_val)
        
        # 提取解析值
        if "解析值" in data:
            parsed_value = str(data["解析值"])
        elif "十进制" in data:
            parsed_value = str(data["十进制"])
        elif "长度值" in data and parsed_value == "-":
            parsed_value = str(data["长度值"])
        
        # 提取说明 - 组合多个子字段的说明
        comments = []
        if "说明" in data:
            comments.append(data["说明"])
        if "业务说明" in data:
            comments.append(data["业务说明"])
        if "校验结果" in data:
            comments.append(data["校验结果"])
        if "字节序" in data:
            comments.append(f"{data['字节序']}，{data.get('字节长度', '')}字节" if data.get('字节长度') else data['字节序'])
        
        comment = ", ".join(comments) if comments else ""
        
        return raw_value, parsed_value, comment
    
    def _is_structured(self, value: dict) -> bool:
        """判断是否是结构化数据"""
        structured_keys = ["原始值", "值", "原始字节", "十进制", "名称", "解析值", "整数值", "业务说明"]
        return any(k in value for k in structured_keys)
    
    def _get_raw_value(self, data: dict) -> str:
        """提取原始值"""
        if "原始值" in data:
            return str(data["原始值"])
        elif "原始字节" in data:
            return str(data["原始字节"])
        elif "值" in data:
            return str(data["值"])
        elif "整数值" in data:
            return str(data["整数值"])
        return "-"
    
    def _get_parsed_value(self, data: dict) -> str:
        """提取解析值"""
        if "解析值" in data:
            return str(data["解析值"])
        elif "十进制" in data:
            return str(data["十进制"])
        elif "名称" in data:
            return str(data["名称"])
        elif "整数值" in data:
            return str(data["整数值"])
        return "-"
    
    def _get_comment(self, data: dict) -> str:
        """提取说明"""
        if "说明" in data:
            return data["说明"]
        elif "描述" in data:
            return data["描述"]
        elif "业务说明" in data:
            return data["业务说明"]
        elif "校验结果" in data:
            return data["校验结果"]
        return ""

    # DI组合详细映射 (DI3:DI2:DI1:DI0 -> 业务说明)
    DI_COMBINATION_MAP = {
        # AFN=00H 确认/否认
        (0xE8, 0x01, 0x00, 0x01): "确认",
        (0xE8, 0x01, 0x00, 0x02): "否认",
        
        # AFN=01H 初始化模块
        (0xE8, 0x02, 0x01, 0x01): "复位硬件",
        (0xE8, 0x02, 0x01, 0x02): "初始化档案",
        (0xE8, 0x02, 0x01, 0x03): "初始化任务",
        
        # AFN=02H 管理任务
        (0xE8, 0x02, 0x02, 0x01): "添加任务",
        (0xE8, 0x02, 0x02, 0x02): "删除任务",
        (0xE8, 0x00, 0x02, 0x03): "查询未完成任务数",
        (0xE8, 0x03, 0x02, 0x04): "查询未完成任务列表",
        (0xE8, 0x04, 0x02, 0x04): "返回查询未完成任务列表",
        (0xE8, 0x03, 0x02, 0x05): "查询未完成任务详细信息",
        (0xE8, 0x04, 0x02, 0x05): "返回查询未完成任务详细信息",
        (0xE8, 0x00, 0x02, 0x06): "查询剩余可分配任务数",
        (0xE8, 0x02, 0x02, 0x07): "添加多播任务",
        (0xE8, 0x02, 0x02, 0x08): "启动任务",
        (0xE8, 0x02, 0x02, 0x09): "暂停任务",
        
        # AFN=03H 读参数
        (0xE8, 0x00, 0x03, 0x01): "查询厂商代码和版本信息",
        (0xE8, 0x00, 0x03, 0x02): "查询本地通信模块运行模式信息",
        (0xE8, 0x00, 0x03, 0x03): "查询主节点地址",
        (0xE8, 0x03, 0x03, 0x04): "查询通信延时时长",
        (0xE8, 0x04, 0x03, 0x04): "返回查询通信延时时长",
        (0xE8, 0x00, 0x03, 0x05): "查询从节点数量",
        (0xE8, 0x03, 0x03, 0x06): "查询从节点信息",
        (0xE8, 0x04, 0x03, 0x06): "返回查询从节点信息",
        (0xE8, 0x00, 0x03, 0x07): "查询从节点主动注册进度",
        (0xE8, 0x03, 0x03, 0x08): "查询从节点的父节点",
        (0xE8, 0x04, 0x03, 0x08): "返回查询从节点的父节点",
        (0xE8, 0x00, 0x03, 0x09): "查询映射表从节点数量",
        (0xE8, 0x03, 0x03, 0x0A): "查询从节点通信地址映射表",
        (0xE8, 0x04, 0x03, 0x0A): "返回查询从节点通信地址映射表",
        (0xE8, 0x00, 0x03, 0x0B): "查询任务建议超时时间",
        (0xE8, 0x03, 0x03, 0x0C): "查询从节点相位信息",
        (0xE8, 0x03, 0x03, 0x0D): "批量查询从节点相位信息",
        (0xE8, 0x03, 0x03, 0x0E): "查询表档案的台区识别结果",
        (0xE8, 0x03, 0x03, 0x0F): "查询多余节点的台区识别结果",
        
        # AFN=04H 写参数
        (0xE8, 0x02, 0x04, 0x01): "设置主节点地址",
        (0xE8, 0x02, 0x04, 0x02): "添加从节点",
        (0xE8, 0x02, 0x04, 0x03): "删除从节点",
        (0xE8, 0x02, 0x04, 0x04): "允许/禁止从节点上报",
        (0xE8, 0x02, 0x04, 0x05): "激活从节点主动注册",
        (0xE8, 0x02, 0x04, 0x06): "终止从节点主动注册",
        (0xE8, 0x02, 0x04, 0x07): "添加从节点通信地址映射表",
        
        # AFN=05H 上报信息
        (0xE8, 0x05, 0x05, 0x01): "上报任务数据",
        (0xE8, 0x05, 0x05, 0x02): "上报从节点事件",
        (0xE8, 0x05, 0x05, 0x03): "上报从节点信息",
        (0xE8, 0x05, 0x05, 0x04): "上报从节点主动注册结束",
        (0xE8, 0x05, 0x05, 0x05): "上报任务状态",
        
        # AFN=06H 请求信息
        (0xE8, 0x06, 0x06, 0x01): "请求集中器时间",
        
        # AFN=07H 传输文件
        (0xE8, 0x02, 0x07, 0x01): "启动文件传输",
        (0xE8, 0x02, 0x07, 0x02): "传输文件内容",
        (0xE8, 0x00, 0x07, 0x03): "查询文件信息",
        (0xE8, 0x00, 0x07, 0x04): "查询文件处理进度",
        (0xE8, 0x03, 0x07, 0x05): "查询文件传输失败节点",
        (0xE8, 0x04, 0x07, 0x05): "返回查询文件传输失败节点",

        # 厂商扩展 - 节点运行时长
        (0xE8, 0x03, 0x03, 0x66): "查询节点运行时长",
        (0xE8, 0x04, 0x03, 0x66): "返回查询节点运行时长",

        # 厂商扩展 - 多网络信息
        (0xE8, 0x00, 0x03, 0x91): "查询多网络信息",

        # 厂商扩展 - 白名单
        (0xE8, 0x00, 0x03, 0x93): "查询白名单生效信息",

        # 深化应用 - 模块资产信息（1-1.md）
        (0xE8, 0x03, 0x03, 0x13): "查询模块资产信息",
        (0xE8, 0x04, 0x03, 0x13): "返回查询模块资产信息",
        (0xE8, 0x03, 0x03, 0x14): "批量查询模块资产信息",
        (0xE8, 0x04, 0x03, 0x14): "批量返回查询模块资产信息",

        # 厂商扩展 - 宽带应用省份
        (0xE8, 0x00, 0xF0, 0xDF): "查询宽带应用省份",

        # 深化应用 - 台区识别（1-1.md）
        (0xE8, 0x03, 0x03, 0x10): "查询台区识别状态",
        (0xE8, 0x04, 0x03, 0x10): "返回查询台区识别状态",
        (0xE8, 0x04, 0x03, 0x0C): "返回查询从节点相位信息",
        (0xE8, 0x04, 0x03, 0x0D): "返回批量查询从节点相位信息",

        # 深化应用 - 台区识别写参数（1-1.md）
        (0xE8, 0x02, 0x04, 0x80): "启动台区识别",
        (0xE8, 0x02, 0x04, 0x81): "停止台区识别",

        # 深化应用 - 上报非本台区从节点信息（1-1.md）
        (0xE8, 0x05, 0x05, 0x80): "上报非本台区从节点信息",

        # 深化应用 - 交采数据（1-1.md）
        (0xE8, 0x03, 0x06, 0x02): "请求交采数据",
        (0xE8, 0x04, 0x06, 0x02): "返回请求交采数据",

        # 深化应用 - 批量查询厂商代码和版本信息（1-1.md）
        (0xE8, 0x03, 0x03, 0x12): "批量查询厂商代码和版本信息",
        (0xE8, 0x04, 0x03, 0x12): "批量返回查询厂商代码和版本信息",

        # ==================== 无线维护接口（AFN=10H）====================
        (0xE8, 0x03, 0x10, 0x10): "查询从节点邻居表",
        (0xE8, 0x04, 0x10, 0x10): "返回查询从节点邻居表",
        (0xE8, 0x03, 0x10, 0x11): "查询主节点状态",
        (0xE8, 0x04, 0x10, 0x11): "返回主节点状态",
        (0xE8, 0x03, 0x10, 0x12): "读取入网节点信息",
        (0xE8, 0x04, 0x10, 0x12): "返回入网节点信息",
        (0xE8, 0x03, 0x10, 0x13): "读取未入网节点信息",
        (0xE8, 0x04, 0x10, 0x13): "返回未入网节点信息",
        (0xE8, 0x02, 0x10, 0x14): "触发指定节点网络维护",
        (0xE8, 0x03, 0x10, 0x15): "请求切换通信速率和信道",
        (0xE8, 0x04, 0x10, 0x15): "响应切换通信速率和信道",
        (0xE8, 0x02, 0x10, 0x16): "恢复通信速率和信道",

        # ==================== 采集器接口（EA前缀）====================
        # 确认/否认（AFN=00H）
        (0xEA, 0x01, 0x00, 0x01): "确认（采集器）",
        (0xEA, 0x01, 0x00, 0x02): "否认（采集器）",

        # 管理电表（AFN=21H）
        (0xEA, 0x06, 0x21, 0x01): "请求表地址个数",
        (0xEA, 0x04, 0x21, 0x02): "请求表地址",
        (0xEA, 0x03, 0x21, 0x02): "返回表地址",
        (0xEA, 0x06, 0x21, 0x03): "请求采集器地址",
        (0xEA, 0x05, 0x21, 0x04): "电表探测列表",
        (0xEA, 0x06, 0x21, 0x05): "电表探测状态",
        (0xEA, 0x06, 0x21, 0x06): "请求采集器绑定地址（红外）",

        # 转发数据（AFN=22H）
        (0xEA, 0x04, 0x22, 0x01): "透传上行数据到采集器",
        (0xEA, 0x03, 0x22, 0x01): "透传上行数据到采集器应答",

        # 读参数（AFN=23H）
        (0xEA, 0x00, 0x23, 0x01): "查询厂商代码和版本信息（采集器）",

        # 传输文件（AFN=24H）
        (0xEA, 0x05, 0x24, 0x01): "启动文件传输（采集器）",
        (0xEA, 0x05, 0x24, 0x02): "传输文件内容（采集器）",
        (0xEA, 0x06, 0x24, 0x03): "请求文件信息（采集器）",
        (0xEA, 0x06, 0x24, 0x04): "请求文件处理进度（采集器）",

        # 管理映射表表计（AFN=31H）
        (0xEA, 0x06, 0x31, 0x01): "请求映射表通信地址个数",
        (0xEA, 0x04, 0x31, 0x02): "请求映射表通信地址",
        (0xEA, 0x03, 0x31, 0x02): "返回映射表通信地址",
        (0xEA, 0x05, 0x31, 0x04): "映射表探测列表",
        (0xEA, 0x06, 0x31, 0x05): "映射表探测状态",

        # 请求信息（AFN=25H）
        (0xEA, 0x06, 0x25, 0x01): "查询设备类型",
    }

    # 错误状态字定义
    ERROR_STATUS = {
        0x00: "通信超时",
        0x01: "无效数据标识内容",
        0x02: "长度错误",
        0x03: "校验错误",
        0x04: "数据标识编码不存在",
        0x05: "格式错误",
        0x06: "表号重复",
        0x07: "表号不存在",
        0x08: "电表应用层无应答",
        0x09: "主节点忙",
        0x0A: "主节点不支持此命令",
        0x0B: "从节点不应答",
        0x0C: "从节点不在网内",
        0x0D: "添加任务时剩余可分配任务数不足",
        0x0E: "上报任务数据时任务不存在",
        0x0F: "任务ID重复",
        0x10: "查询任务时模块没有此任务",
        0x11: "任务ID不存在",
        0xFF: "其他错误"
    }

    # 模块资产信息元素 ID（表 70）
    ASSET_INFO_ELEMENT = {
        0x00: {"名称": "厂商代码", "字节数": 2, "格式": "ASCII"},
        0x01: {"名称": "软件版本号（模块）", "字节数": 2, "格式": "BCD"},
        0x02: {"名称": "Bootloader 版本号", "字节数": 1, "格式": "BIN"},
        0x05: {"名称": "芯片厂商代码", "字节数": 2, "格式": "ASCII"},
        0x06: {"名称": "软件发布日期（模块）", "字节数": 3, "格式": "YYMMDD"},
        0x08: {"名称": "模块出厂通信地址", "字节数": 6, "格式": "BIN"},
        0x09: {"名称": "硬件版本号（模块）", "字节数": 2, "格式": "BCD"},
        0x0A: {"名称": "硬件发布日期（模块）", "字节数": 3, "格式": "YYMMDD"},
        0x0B: {"名称": "软件版本号（芯片）", "字节数": 2, "格式": "BCD"},
        0x0C: {"名称": "软件发布日期（芯片）", "字节数": 3, "格式": "YYMMDD"},
        0x0D: {"名称": "硬件版本号（芯片）", "字节数": 2, "格式": "BCD"},
        0x0E: {"名称": "硬件发布日期（芯片）", "字节数": 3, "格式": "YYMMDD"},
        0x0F: {"名称": "应用程序版本号", "字节数": 2, "格式": "BCD"},
        0x10: {"名称": "通信模块资产编码", "字节数": 24, "格式": "ASCII"},
    }

    # 自定义DI配置文件路径
    CUSTOM_DI_FILE = "custom_di.json"

    def __init__(self):
        self._load_custom_di()

    def _load_custom_di(self):
        """从 custom_di.json 加载用户自定义DI条目，合并到 DI_COMBINATION_MAP"""
        import json
        from pathlib import Path
        custom_file = Path(self.CUSTOM_DI_FILE)
        if custom_file.exists():
            try:
                with open(custom_file, 'r', encoding='utf-8') as f:
                    entries = json.load(f)
                for entry in entries:
                    key = (entry["di3"], entry["di2"], entry["di1"], entry["di0"])
                    if key not in self.DI_COMBINATION_MAP:
                        self.DI_COMBINATION_MAP[key] = entry["desc"]
            except Exception:
                pass

    @staticmethod
    def save_custom_di(entries: list):
        """保存自定义DI条目到 custom_di.json"""
        import json
        from pathlib import Path
        custom_file = Path(ProtocolFrameParser.CUSTOM_DI_FILE)
        with open(custom_file, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_custom_di_list() -> list:
        """读取 custom_di.json 返回列表"""
        import json
        from pathlib import Path
        custom_file = Path(ProtocolFrameParser.CUSTOM_DI_FILE)
        if custom_file.exists():
            try:
                with open(custom_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def parse(self, frame_bytes: bytes) -> Dict[str, Any]:
        """解析协议帧

        Args:
            frame_bytes: 原始帧数据

        Returns:
            JSON格式的解析结果
        """
        result = {
            "原始数据": frame_bytes.hex().upper(),
            "解析状态": "成功",
            "错误信息": None
        }

        try:
            # 基本长度检查
            if len(frame_bytes) < 8:
                raise ValueError("帧长度太短，最小长度为8字节")

            # 解析帧头
            pos = 0
            start_char = frame_bytes[pos]
            result["帧头"] = {
                "起始字符": f"0x{start_char:02X}",
                "说明": "帧起始标志"
            }

            if start_char != 0x68:
                result["帧头"]["警告"] = "起始字符不是0x68"

            pos += 1

            # 解析长度
            length = int.from_bytes(frame_bytes[pos:pos+2], 'little')
            result["长度域"] = {
                "长度值": length,
                "字节长度": 2,
                "字节序": "小端序",
                "说明": "用户数据区长度+6字节固定长度"
            }
            pos += 2

            # 解析控制域
            control_byte = frame_bytes[pos]
            control = self._parse_control_field(control_byte)
            result["控制域"] = control
            pos += 1

            # 计算用户数据区实际长度
            user_data_len = length - 6  # 减去6字节固定长度

            if len(frame_bytes) < pos + user_data_len + 2:  # +2 for CS and end
                raise ValueError(f"帧数据长度不足，期望至少{pos + user_data_len + 2}字节")

            # 解析用户数据区
            user_data = frame_bytes[pos:pos+user_data_len]
            result["用户数据区"] = self._parse_user_data(user_data, control)
            pos += user_data_len

            # 解析校验和
            cs = frame_bytes[pos]
            calculated_cs = self._calculate_checksum(frame_bytes[3:pos])
            result["校验和"] = {
                "校验值": f"0x{cs:02X}",
                "计算值": f"0x{calculated_cs:02X}",
                "校验结果": "通过" if cs == calculated_cs else "失败"
            }
            pos += 1

            # 解析结束符
            end_char = frame_bytes[pos]
            result["结束符"] = {
                "结束字符": f"0x{end_char:02X}",
                "校验结果": "正确" if end_char == 0x16 else "错误"
            }

        except Exception as e:
            result["解析状态"] = "失败"
            result["错误信息"] = str(e)

        return result

    def _parse_control_field(self, control_byte: int) -> Dict[str, Any]:
        """解析控制域"""
        dir_flag = (control_byte >> 7) & 0x01
        prm = (control_byte >> 6) & 0x01
        add = (control_byte >> 5) & 0x01
        ver = (control_byte >> 3) & 0x03
        reserved = control_byte & 0x07

        return {
            "原始字节": f"0x{control_byte:02X}",
            "传输方向(DIR)": {
                "值": dir_flag,
                "说明": "下行帧(集中器->模块)" if dir_flag == 0 else "上行帧(模块->集中器)"
            },
            "启动标志(PRM)": {
                "值": prm,
                "说明": "从动站" if prm == 0 else "启动站"
            },
            "地址域标识(ADD)": {
                "值": add,
                "说明": "不带地址域" if add == 0 else "带地址域"
            },
            "协议版本(VER)": {
                "值": ver,
                "说明": f"版本{ver}"
            },
            "保留位": reserved
        }

    def _parse_user_data(self, user_data: bytes, control: Dict[str, Any]) -> Dict[str, Any]:
        """解析用户数据区"""
        result = {
            "原始数据": user_data.hex().upper(),
            "长度": len(user_data)
        }

        if len(user_data) == 0:
            result["说明"] = "用户数据区为空"
            return result

        pos = 0

        # 解析地址域
        add = control["地址域标识(ADD)"]["值"]
        if add == 1 and len(user_data) >= 12:
            src_addr = user_data[pos:pos+6][::-1]
            dst_addr = user_data[pos+6:pos+12][::-1]
            result["地址域"] = {
                "源地址": src_addr.hex().upper(),
                "目的地址": dst_addr.hex().upper()
            }
            pos += 12

        # 解析AFN
        if len(user_data) > pos:
            afn = user_data[pos]
            afn_name = self.AFN_MAP.get(afn, f"未知AFN({afn:02X})")
            result["应用功能码(AFN)"] = {
                "原始值": f"0x{afn:02X}",
                "名称": afn_name
            }
            pos += 1

        # 解析序列号
        if len(user_data) > pos:
            seq = user_data[pos]
            result["帧序列号(SEQ)"] = {
                "原始值": f"0x{seq:02X}",
                "十进制": seq
            }
            pos += 1

        # 解析DI
        if len(user_data) >= pos + 4:
            di_bytes = user_data[pos:pos+4]
            di_value = int.from_bytes(di_bytes, 'little')
            di3, di2, di1, di0 = di_bytes[3], di_bytes[2], di_bytes[1], di_bytes[0]

            # 查找DI组合说明
            di_combination = (di3, di2, di1, di0)
            di_description = self.DI_COMBINATION_MAP.get(di_combination, None)

            result["数据标识(DI)"] = {
                "原始值": di_bytes.hex().upper(),
                "整数值": f"0x{di_value:08X}",
                "业务说明": di_description if di_description else f"未知DI组合({di3:02X}:{di2:02X}:{di1:02X}:{di0:02X})",
                "DI3": {
                    "值": f"0x{di3:02X}",
                    "说明": self.DI3_MAP.get(di3, f"未知({di3:02X})")
                },
                "DI2": {
                    "值": f"0x{di2:02X}",
                    "说明": self.DI2_MAP.get(di2, f"未知({di2:02X})")
                },
                "DI1(AFN)": f"0x{di1:02X}",
                "DI0(子类型)": f"0x{di0:02X}"
            }
            pos += 4

        # 剩余数据作为数据标识内容
        if len(user_data) > pos:
            data_content = user_data[pos:]
            # 根据DI组合解析数据内容
            parsed_content = self._parse_di_data_content(di_combination, data_content)
            result["数据标识内容"] = parsed_content

        return result

    # ==================== 数据内容解析方法 ====================

    def _parse_di_data_content(self, di_combination: Tuple[int, int, int, int], data_content: bytes) -> Dict[str, Any]:
        """根据DI组合解析数据内容"""
        parser = self._get_data_content_parser(di_combination)
        if parser:
            try:
                return parser(data_content)
            except Exception as e:
                return {
                    "解析状态": "失败",
                    "错误信息": str(e),
                    "原始数据": data_content.hex().upper()
                }
        return {
            "原始数据": data_content.hex().upper(),
            "长度": len(data_content),
            "说明": "暂无此DI类型的详细解析"
        }

    def _get_data_content_parser(self, di_combination: Tuple[int, int, int, int]):
        """获取DI组合对应的数据内容解析方法"""
        parsers = {
            # AFN=00H 确认/否认
            (0xE8, 0x01, 0x00, 0x01): self._parse_confirm_data,          # 确认
            (0xE8, 0x01, 0x00, 0x02): self._parse_deny_data,             # 否认

            # AFN=01H 初始化模块
            (0xE8, 0x02, 0x01, 0x01): self._parse_reset_hardware_data,   # 复位硬件
            (0xE8, 0x02, 0x01, 0x02): self._parse_init_archive_data,     # 初始化档案
            (0xE8, 0x02, 0x01, 0x03): self._parse_init_task_data,        # 初始化任务

            # AFN=02H 管理任务
            (0xE8, 0x02, 0x02, 0x01): self._parse_add_task_data,         # 添加任务
            (0xE8, 0x02, 0x02, 0x02): self._parse_delete_task_data,      # 删除任务
            (0xE8, 0x00, 0x02, 0x03): self._parse_query_incomplete_task_count_data,  # 查询未完成任务数
            (0xE8, 0x03, 0x02, 0x04): self._parse_query_incomplete_task_list_data,   # 查询未完成任务列表
            (0xE8, 0x04, 0x02, 0x04): self._parse_return_incomplete_task_list_data,  # 返回查询未完成任务列表
            (0xE8, 0x03, 0x02, 0x05): self._parse_query_task_detail_data,           # 查询未完成任务详细信息
            (0xE8, 0x04, 0x02, 0x05): self._parse_return_task_detail_data,          # 返回查询未完成任务详细信息
            (0xE8, 0x00, 0x02, 0x06): self._parse_query_remain_task_count_data,     # 查询剩余可分配任务数
            (0xE8, 0x02, 0x02, 0x07): self._parse_add_multicast_task_data,          # 添加多播任务
            (0xE8, 0x02, 0x02, 0x08): self._parse_start_task_data,       # 启动任务
            (0xE8, 0x02, 0x02, 0x09): self._parse_pause_task_data,       # 暂停任务

            # AFN=03H 读参数
            (0xE8, 0x00, 0x03, 0x01): self._parse_query_vendor_info_data,           # 查询厂商代码和版本信息
            (0xE8, 0x00, 0x03, 0x02): self._parse_query_run_mode_data,              # 查询本地通信模块运行模式信息
            (0xE8, 0x00, 0x03, 0x03): self._parse_query_master_node_addr_data,      # 查询主节点地址
            (0xE8, 0x03, 0x03, 0x04): self._parse_query_comm_delay_data,            # 查询通信延时时长
            (0xE8, 0x04, 0x03, 0x04): self._parse_return_comm_delay_data,           # 返回查询通信延时时长
            (0xE8, 0x00, 0x03, 0x05): self._parse_query_slave_node_count_data,      # 查询从节点数量
            (0xE8, 0x03, 0x03, 0x06): self._parse_query_slave_node_info_data,       # 查询从节点信息
            (0xE8, 0x04, 0x03, 0x06): self._parse_return_slave_node_info_data,      # 返回查询从节点信息
            (0xE8, 0x00, 0x03, 0x07): self._parse_query_reg_progress_data,          # 查询从节点主动注册进度
            (0xE8, 0x03, 0x03, 0x08): self._parse_query_slave_parent_data,          # 查询从节点的父节点
            (0xE8, 0x04, 0x03, 0x08): self._parse_return_slave_parent_data,         # 返回查询从节点的父节点
            (0xE8, 0x00, 0x03, 0x09): self._parse_query_mapping_node_count_data,    # 查询映射表从节点数量
            (0xE8, 0x03, 0x03, 0x0A): self._parse_query_mapping_table_data,         # 查询从节点通信地址映射表
            (0xE8, 0x04, 0x03, 0x0A): self._parse_return_mapping_table_data,        # 返回查询从节点通信地址映射表
            (0xE8, 0x00, 0x03, 0x0B): self._parse_query_task_timeout_data,          # 查询任务建议超时时间
            (0xE8, 0x03, 0x03, 0x0C): self._parse_query_slave_phase_data,           # 查询从节点相位信息
            (0xE8, 0x03, 0x03, 0x0D): self._parse_batch_query_phase_data,           # 批量查询从节点相位信息
            (0xE8, 0x03, 0x03, 0x0E): self._parse_query_region_identify_data,       # 查询表档案的台区识别结果
            (0xE8, 0x03, 0x03, 0x0F): self._parse_query_extra_node_region_data,     # 查询多余节点的台区识别结果

            # AFN=04H 写参数
            (0xE8, 0x02, 0x04, 0x01): self._parse_set_master_node_addr_data,       # 设置主节点地址
            (0xE8, 0x02, 0x04, 0x02): self._parse_add_slave_node_data,              # 添加从节点
            (0xE8, 0x02, 0x04, 0x03): self._parse_delete_slave_node_data,           # 删除从节点
            (0xE8, 0x02, 0x04, 0x04): self._parse_set_event_report_data,            # 允许/禁止从节点上报
            (0xE8, 0x02, 0x04, 0x05): self._parse_activate_slave_reg_data,          # 激活从节点主动注册
            (0xE8, 0x02, 0x04, 0x06): self._parse_terminate_slave_reg_data,         # 终止从节点主动注册
            (0xE8, 0x02, 0x04, 0x07): self._parse_add_mapping_table_data,           # 添加从节点通信地址映射表

            # AFN=05H 上报信息
            (0xE8, 0x05, 0x05, 0x01): self._parse_report_task_data,                 # 上报任务数据
            (0xE8, 0x05, 0x05, 0x02): self._parse_report_event_data,                # 上报从节点事件
            (0xE8, 0x05, 0x05, 0x03): self._parse_report_slave_node_info_data,      # 上报从节点信息
            (0xE8, 0x05, 0x05, 0x04): self._parse_report_reg_end_data,              # 上报从节点主动注册结束
            (0xE8, 0x05, 0x05, 0x05): self._parse_report_task_status_data,          # 上报任务状态

            # AFN=06H 请求信息
            (0xE8, 0x06, 0x06, 0x01): self._parse_request_time_data,                # 请求集中器时间

            # AFN=07H 传输文件
            (0xE8, 0x02, 0x07, 0x01): self._parse_start_file_transfer_data,         # 启动文件传输
            (0xE8, 0x02, 0x07, 0x02): self._parse_file_content_data,                # 传输文件内容
            (0xE8, 0x00, 0x07, 0x03): self._parse_query_file_info_data,             # 查询文件信息
            (0xE8, 0x00, 0x07, 0x04): self._parse_query_file_progress_data,         # 查询文件处理进度
            (0xE8, 0x03, 0x07, 0x05): self._parse_query_file_failed_nodes_data,     # 查询文件传输失败节点
            (0xE8, 0x04, 0x07, 0x05): self._parse_return_file_failed_nodes_data,    # 返回查询文件传输失败节点

            # 厂商扩展 - 节点运行时长
            (0xE8, 0x03, 0x03, 0x66): self._parse_query_node_runtime_data,          # 查询节点运行时长
            (0xE8, 0x04, 0x03, 0x66): self._parse_return_node_runtime_data,         # 返回查询节点运行时长

            # 厂商扩展 - 多网络信息
            (0xE8, 0x00, 0x03, 0x91): self._parse_query_multi_network_data,         # 查询多网络信息

            # 厂商扩展 - 白名单
            (0xE8, 0x00, 0x03, 0x93): self._parse_query_whitelist_data,             # 查询白名单生效信息

            # 深化应用 - 模块资产信息（1-1.md）
            (0xE8, 0x03, 0x03, 0x13): self._parse_query_asset_info_data,            # 查询模块资产信息
            (0xE8, 0x04, 0x03, 0x13): self._parse_return_asset_info_data,           # 返回查询模块资产信息
            (0xE8, 0x03, 0x03, 0x14): self._parse_batch_query_asset_info_data,      # 批量查询模块资产信息
            (0xE8, 0x04, 0x03, 0x14): self._parse_batch_return_asset_info_data,     # 批量返回查询模块资产信息

            # 厂商扩展 - 宽带应用省份
            (0xE8, 0x00, 0xF0, 0xDF): self._parse_query_broadband_province_data,   # 查询宽带应用省份

            # 深化应用 - 台区识别（1-1.md）
            (0xE8, 0x03, 0x03, 0x10): self._parse_query_region_status_data,       # 查询台区识别状态
            (0xE8, 0x04, 0x03, 0x10): self._parse_return_region_status_data,       # 返回查询台区识别状态
            (0xE8, 0x04, 0x03, 0x0C): self._parse_return_slave_phase_data,         # 返回查询从节点相位信息
            (0xE8, 0x04, 0x03, 0x0D): self._parse_return_batch_phase_data,         # 返回批量查询从节点相位信息

            # 深化应用 - 台区识别写参数（1-1.md）
            (0xE8, 0x02, 0x04, 0x80): self._parse_start_region_identify_data,     # 启动台区识别
            (0xE8, 0x02, 0x04, 0x81): self._parse_stop_region_identify_data,      # 停止台区识别

            # 深化应用 - 上报非本台区从节点信息（1-1.md）
            (0xE8, 0x05, 0x05, 0x80): self._parse_report_other_region_node_data,  # 上报非本台区从节点信息

            # 深化应用 - 交采数据（1-1.md）
            (0xE8, 0x03, 0x06, 0x02): self._parse_request_acquisition_data,       # 请求交采数据
            (0xE8, 0x04, 0x06, 0x02): self._parse_return_acquisition_data,        # 返回请求交采数据

            # 深化应用 - 批量查询厂商代码和版本信息（1-1.md）
            (0xE8, 0x03, 0x03, 0x12): self._parse_batch_query_vendor_info_data,   # 批量查询厂商代码和版本信息
            (0xE8, 0x04, 0x03, 0x12): self._parse_batch_return_vendor_info_data,  # 批量返回查询厂商代码和版本信息
        }
        return parsers.get(di_combination)

    # ==================== AFN=00H 确认/否认 ====================

    def _parse_confirm_data(self, data: bytes) -> Dict[str, Any]:
        """解析确认帧数据内容"""
        if len(data) < 2:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        wait_time = int.from_bytes(data[0:2], 'big')
        return {
            "等待时间": {
                "值": wait_time,
                "单位": "秒",
                "原始字节": data[0:2].hex().upper()
            }
        }

    def _parse_deny_data(self, data: bytes) -> Dict[str, Any]:
        """解析否认帧数据内容"""
        if len(data) < 1:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        error_code = data[0]
        return {
            "错误状态字": {
                "原始值": f"0x{error_code:02X}",
                "说明": self.ERROR_STATUS.get(error_code, "未知错误")
            }
        }

    # ==================== AFN=01H 初始化模块 ====================

    def _parse_reset_hardware_data(self, data: bytes) -> Dict[str, Any]:
        """解析复位硬件数据内容"""
        return {"说明": "复位硬件命令，无数据内容"}

    def _parse_init_archive_data(self, data: bytes) -> Dict[str, Any]:
        """解析初始化档案数据内容"""
        return {"说明": "初始化档案命令，无数据内容"}

    def _parse_init_task_data(self, data: bytes) -> Dict[str, Any]:
        """解析初始化任务数据内容"""
        return {"说明": "初始化任务命令，无数据内容"}

    # ==================== AFN=02H 管理任务 ====================

    def _parse_add_task_data(self, data: bytes) -> Dict[str, Any]:
        """解析添加任务数据内容（E8 02 02 01）

        格式：任务ID(2B BIN) + 任务模式字(1B BS) + 超时时间(2B BIN) + 报文长度(1B) + 报文内容(LB)
        任务模式字: D7=任务响应标识, D4~D3=保留, D2~D0=任务优先级
        """
        if len(data) < 6:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}

        task_id = int.from_bytes(data[0:2], 'little')
        mode = data[2]
        timeout = int.from_bytes(data[3:5], 'little')
        msg_len = data[5]

        resp_flag = (mode >> 7) & 0x01
        priority = mode & 0x07

        result = {
            "任务ID": {"原始值": data[0:2].hex().upper(), "十进制": task_id},
            "任务模式字": {
                "原始值": f"0x{mode:02X}",
                "任务响应标识": "需要数据返回" if resp_flag == 1 else "不需要数据返回",
                "任务优先级": f"{priority}（{'最高' if priority == 0 else '最低' if priority == 3 else str(priority)}）"
            },
            "超时时间": {"原始值": data[3:5].hex().upper(), "十进制": timeout, "单位": "秒"},
            "报文长度": {"原始值": f"0x{msg_len:02X}", "十进制": msg_len}
        }
        if len(data) >= 6 + msg_len:
            result["报文内容"] = data[6:6+msg_len].hex().upper()
        elif len(data) > 6:
            result["报文内容"] = data[6:].hex().upper()
        return result

    def _parse_delete_task_data(self, data: bytes) -> Dict[str, Any]:
        """解析删除任务数据内容"""
        if len(data) < 2:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        task_id = int.from_bytes(data[0:2], 'little')  # 任务 ID: 2 字节 (小端序)
        return {
            "任务ID": {
                "原始值": data[0:2].hex().upper(),
                "十进制": task_id
            }
        }

    def _parse_query_incomplete_task_count_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回未完成任务数（E8 00 02 03）
        下行查询：无数据；上行应答：2字节 BIN 小端
        """
        if len(data) < 2:
            return {"说明": "查询命令，无数据内容"}
        count = int.from_bytes(data[0:2], 'little')
        return {
            "未完成任务数": {"原始值": data[0:2].hex().upper(), "十进制": count}
        }

    def _parse_query_incomplete_task_list_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询未完成任务列表数据内容"""
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "起始序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')},
            "查询数量": {"原始值": f"0x{data[2]:02X}", "十进制": data[2]}
        }

    def _parse_return_incomplete_task_list_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询未完成任务列表数据内容"""
        if len(data) < 4:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        total_count = int.from_bytes(data[0:2], 'big')
        return_count = data[2]
        result = {
            "总任务数": {"原始值": data[0:2].hex().upper(), "十进制": total_count},
            "返回任务数": {"原始值": f"0x{data[2]:02X}", "十进制": return_count},
            "任务列表": []
        }
        pos = 3
        for i in range(return_count):
            if pos + 2 > len(data):
                break
            task_id = int.from_bytes(data[pos:pos+2], 'big')
            result["任务列表"].append({
                "序号": i + 1,
                "任务ID": {"原始值": data[pos:pos+2].hex().upper(), "十进制": task_id}
            })
            pos += 2
        return result

    def _parse_query_task_detail_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询未完成任务详细信息数据内容"""
        if len(data) < 2:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        task_id = int.from_bytes(data[0:2], 'little')  # 任务 ID: 2 字节 (小端序)
        return {
            "任务ID": {"原始值": data[0:2].hex().upper(), "十进制": task_id}
        }

    def _parse_return_task_detail_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询未完成任务详细信息（E8 04 02 05）

        格式：任务ID(2B) + 任务模式字(1B) + 任务目的地址个数(2B)
              + 任务目的地址(6B×n) + 报文长度(1B) + 报文内容(LB)
        """
        if len(data) < 5:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}

        task_id = int.from_bytes(data[0:2], 'little')
        mode = data[2]
        addr_count = int.from_bytes(data[3:5], 'little')

        resp_flag = (mode >> 7) & 0x01
        priority = mode & 0x07

        result = {
            "任务ID": {"原始值": data[0:2].hex().upper(), "十进制": task_id},
            "任务模式字": {
                "原始值": f"0x{mode:02X}",
                "任务响应标识": "需要数据返回" if resp_flag == 1 else "不需要数据返回",
                "任务优先级": str(priority)
            },
            "任务目的地址个数": {"原始值": data[3:5].hex().upper(), "十进制": addr_count}
        }

        pos = 5
        addrs = []
        for i in range(addr_count):
            if pos + 6 > len(data):
                break
            addrs.append({"序号": i + 1, "任务目的地址": data[pos:pos+6].hex().upper()})
            pos += 6
        result["任务目的地址列表"] = addrs

        if pos < len(data):
            msg_len = data[pos]
            result["报文长度"] = {"原始值": f"0x{msg_len:02X}", "十进制": msg_len}
            pos += 1
            if pos < len(data):
                end = min(pos + msg_len, len(data))
                result["报文内容"] = data[pos:end].hex().upper()

        return result

    def _parse_query_remain_task_count_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回剩余可分配任务数（E8 00 02 06）
        下行查询：无数据；上行应答：2字节 BIN 小端
        """
        if len(data) < 2:
            return {"说明": "查询命令，无数据内容"}
        count = int.from_bytes(data[0:2], 'little')
        return {
            "剩余可分配任务数": {"原始值": data[0:2].hex().upper(), "十进制": count}
        }

    def _parse_add_multicast_task_data(self, data: bytes) -> Dict[str, Any]:
        """解析添加多播任务数据内容（E8 02 02 07）

        格式：任务ID(2B) + 任务模式字(1B) + 从节点数量(2B)
              + 从节点地址(6B×n) + 超时时间(2B) + 报文长度(1B) + 报文内容(LB)
        注：从节点数量=0xFFFF表示向所有从模块传输，此时无从节点地址域
        """
        if len(data) < 5:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}

        task_id = int.from_bytes(data[0:2], 'little')
        mode = data[2]
        node_count = int.from_bytes(data[3:5], 'little')

        resp_flag = (mode >> 7) & 0x01
        priority = mode & 0x07

        result = {
            "任务ID": {"原始值": data[0:2].hex().upper(), "十进制": task_id},
            "任务模式字": {
                "原始值": f"0x{mode:02X}",
                "任务响应标识": "需要数据返回" if resp_flag == 1 else "不需要数据返回",
                "任务优先级": str(priority)
            },
            "从节点数量": {
                "原始值": data[3:5].hex().upper(),
                "十进制": node_count,
                "说明": "向所有从模块传输" if node_count == 0xFFFF else ""
            }
        }

        pos = 5
        if node_count != 0xFFFF:
            nodes = []
            for i in range(node_count):
                if pos + 6 > len(data):
                    break
                nodes.append({"序号": i + 1, "从节点地址": data[pos:pos+6].hex().upper()})
                pos += 6
            result["从节点列表"] = nodes

        # 超时时间
        if pos + 2 <= len(data):
            timeout = int.from_bytes(data[pos:pos+2], 'little')
            result["超时时间"] = {"原始值": data[pos:pos+2].hex().upper(), "十进制": timeout, "单位": "秒"}
            pos += 2

        # 报文长度 + 报文内容
        if pos < len(data):
            msg_len = data[pos]
            result["报文长度"] = {"原始值": f"0x{msg_len:02X}", "十进制": msg_len}
            pos += 1
            if pos < len(data):
                end = min(pos + msg_len, len(data))
                result["报文内容"] = data[pos:end].hex().upper()

        return result

    def _parse_start_task_data(self, data: bytes) -> Dict[str, Any]:
        """解析启动任务数据内容"""
        if len(data) < 2:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        task_id = int.from_bytes(data[0:2], 'little')  # 任务 ID: 2 字节 (小端序)
        return {
            "任务ID": {"原始值": data[0:2].hex().upper(), "十进制": task_id}
        }

    def _parse_pause_task_data(self, data: bytes) -> Dict[str, Any]:
        """解析暂停任务数据内容"""
        if len(data) < 2:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        task_id = int.from_bytes(data[0:2], 'little')  # 任务 ID: 2 字节 (小端序)
        return {
            "任务ID": {"原始值": data[0:2].hex().upper(), "十进制": task_id}
        }

    def _get_task_type_desc(self, task_type: int) -> str:
        """获取任务类型说明"""
        task_types = {
            0x01: "抄读电表数据",
            0x02: "抄读集中器数据",
            0x03: "控制命令",
            0x04: "参数设置",
            0x05: "其他任务"
        }
        return task_types.get(task_type, f"未知类型({task_type:02X})")

    def _get_task_cycle_desc(self, cycle: int) -> str:
        """获取任务周期说明"""
        cycles = {
            0x00: "单次执行",
            0x01: "每分钟执行",
            0x02: "每小时执行",
            0x03: "每天执行",
            0x04: "每周执行",
            0x05: "每月执行"
        }
        return cycles.get(cycle, f"未知周期({cycle:02X})")

    # ==================== AFN=03H 读参数 ====================

    def _parse_query_vendor_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回厂商代码和版本信息（E8 00 03 01）
        下行查询：无数据；上行应答：厂商代码(2B ASCII) + 芯片代码(2B ASCII) + 版本时间(3B YYMMDD) + 版本(2B BCD)
        """
        if len(data) < 9:
            return {"说明": "查询命令，无数据内容"}
        result = {"原始值": data.hex().upper()}
        try:
            result["厂商代码"] = data[0:2].decode('ascii')
            result["芯片代码"] = data[2:4].decode('ascii')
            result["版本时间"] = f"20{data[4]:02d}-{data[5]:02d}-{data[6]:02d}"
            result["版本号"] = data[7:9].hex().upper()
        except Exception:
            pass
        return result

    def _parse_query_run_mode_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询本地通信模块运行模式信息数据内容 (上行响应)
        
        根据 MD 文档，上行数据内容格式：
        - 本地通信模式字: 1字节 (BS)
        - 最大支持的协议报文长度: 2字节 (BIN, 小端序)
        - 文件传输支持的最大单包长度: 2字节 (BIN, 小端序)
        - 升级操作等待时间: 1字节 (BIN)
        - 主节点地址: 6字节 (BIN)
        - 支持的最大从节点数量: 2字节 (BIN, 小端序)
        - 当前从节点数量: 2字节 (BIN, 小端序)
        - 支持单次读写从节点信息的最大数量: 2字节 (BIN, 小端序)
        - 通信模块接口协议发布日期: 3字节 (YYMMDD)
        - 厂商代码和版本信息: 9字节
        """
        if len(data) == 0:
            return {"说明": "查询命令，无数据内容"}
            
        if len(data) < 30:
            return {"原始数据": data.hex().upper(), "说明": f"数据长度不足，期望30字节，实际{len(data)}字节"}
        
        pos = 0
        
        # 本地通信模式字
        mode_byte = data[pos]
        comm_way = (mode_byte >> 1) & 0x07
        ways = {1: "窄带电力线载波", 2: "宽带电力线载波", 3: "微功率无线", 
                4: "窄带+微功率无线", 5: "宽带+微功率无线"}
        result = {
            "本地通信模式字": {
                "原始值": f"0x{mode_byte:02X}",
                "通信方式": ways.get(comm_way, f"未知({comm_way})")
            }
        }
        pos += 1
        
        # 最大支持的协议报文长度
        max_len = int.from_bytes(data[pos:pos+2], 'little')
        result["最大支持的协议报文长度"] = {
            "原始值": data[pos:pos+2].hex().upper(),
            "十进制": max_len,
            "单位": "字节"
        }
        pos += 2
        
        # 文件传输支持的最大单包长度
        file_max_len = int.from_bytes(data[pos:pos+2], 'little')
        result["文件传输支持的最大单包长度"] = {
            "原始值": data[pos:pos+2].hex().upper(),
            "十进制": file_max_len,
            "单位": "字节"
        }
        pos += 2
        
        # 升级操作等待时间
        wait_time = data[pos]
        result["升级操作等待时间"] = {
            "原始值": f"0x{wait_time:02X}",
            "十进制": wait_time,
            "单位": "秒"
        }
        pos += 1
        
        # 主节点地址
        master_addr = data[pos:pos+6]
        result["主节点地址"] = {
            "原始值": master_addr.hex().upper()
        }
        pos += 6
        
        # 支持的最大从节点数量
        max_nodes = int.from_bytes(data[pos:pos+2], 'little')
        result["支持的最大从节点数量"] = {
            "原始值": data[pos:pos+2].hex().upper(),
            "十进制": max_nodes
        }
        pos += 2
        
        # 当前从节点数量
        curr_nodes = int.from_bytes(data[pos:pos+2], 'little')
        result["当前从节点数量"] = {
            "原始值": data[pos:pos+2].hex().upper(),
            "十进制": curr_nodes
        }
        pos += 2
        
        # 支持单次读写从节点信息的最大数量
        max_read_nodes = int.from_bytes(data[pos:pos+2], 'little')
        result["支持单次读写从节点信息的最大数量"] = {
            "原始值": data[pos:pos+2].hex().upper(),
            "十进制": max_read_nodes
        }
        pos += 2
        
        # 通信模块接口协议发布日期
        date_bytes = data[pos:pos+3]
        year = date_bytes[0]
        month = date_bytes[1]
        day = date_bytes[2]
        result["通信模块接口协议发布日期"] = {
            "原始值": date_bytes.hex().upper(),
            "日期": f"20{year:02d}-{month:02d}-{day:02d}"
        }
        pos += 3
        
        # 厂商代码和版本信息 (9字节)
        vendor_info = data[pos:pos+9]
        vendor_result = {"原始值": vendor_info.hex().upper()}
        if len(vendor_info) >= 9:
            try:
                vendor_code = vendor_info[0:2].decode('ascii')
                chip_code = vendor_info[2:4].decode('ascii')
                vendor_result["厂商代码"] = vendor_code
                vendor_result["芯片代码"] = chip_code
                vendor_result["版本日期"] = f"{vendor_info[4]:02d}{vendor_info[5]:02d}{vendor_info[6]:02d}"
                vendor_result["版本"] = f"{vendor_info[7]:02d}.{vendor_info[8]:02d}"
            except:
                pass
        result["厂商代码和版本信息"] = vendor_result
        
        return result

    def _parse_query_master_node_addr_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回主节点地址（E8 00 03 03）
        下行查询：无数据；上行应答：6字节 BIN
        """
        if len(data) < 6:
            return {"说明": "查询命令，无数据内容"}
        return {
            "主节点地址": {"原始值": data[0:6].hex().upper()}
        }

    def _parse_query_comm_delay_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询通信延时时长数据内容"""
        if len(data) < 6:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "目的地址": data[0:6].hex().upper()
        }

    def _parse_return_comm_delay_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询通信延时时长数据内容"""
        if len(data) < 8:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "目的地址": data[0:6].hex().upper(),
            "通信延时时长": {
                "原始值": data[6:8].hex().upper(),
                "十进制": int.from_bytes(data[6:8], 'big'),
                "单位": "毫秒"
            }
        }

    def _parse_query_slave_node_count_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回从节点数量数据内容（E8 00 03 05）

        下行（查询）：无数据内容
        上行（应答）：2字节 BIN 小端，从节点总数量
        """
        if len(data) < 2:
            return {"说明": "查询命令，无数据内容"}
        count = int.from_bytes(data[0:2], 'little')
        return {
            "从节点总数量": {"原始值": data[0:2].hex().upper(), "十进制": count}
        }

    def _parse_query_slave_node_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询从节点信息数据内容"""
        if len(data) < 2:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "从节点序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')}
        }

    def _parse_return_slave_node_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询从节点信息数据内容"""
        if len(data) < 14:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        result = {
            "从节点序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')},
            "从节点地址": data[2:8].hex().upper(),
            "从节点类型": {"原始值": f"0x{data[8]:02X}", "说明": self._get_slave_node_type_desc(data[8])},
            "从节点状态": {"原始值": f"0x{data[9]:02X}", "说明": self._get_slave_node_status_desc(data[9])},
            "信号强度": {"原始值": f"0x{data[10]:02X}", "十进制": data[10], "单位": "dBm"},
            "通信成功率": {"原始值": f"0x{data[11]:02X}", "十进制": data[11], "单位": "%"},
            "最后通信时间": data[12:14].hex().upper()
        }
        return result

    def _parse_query_reg_progress_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回从节点主动注册进度（E8 00 03 07）
        下行查询：无数据；上行应答：1字节 注册工作标示
        """
        if len(data) < 1:
            return {"说明": "查询命令，无数据内容"}
        flag = data[0]
        desc = "正在主动注册" if flag == 1 else "停止主动注册"
        return {
            "从节点主动注册工作标示": {"原始值": f"0x{flag:02X}", "十进制": flag, "说明": desc}
        }

    def _parse_query_slave_parent_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询从节点的父节点数据内容"""
        if len(data) < 2:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "从节点序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')}
        }

    def _parse_return_slave_parent_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询从节点的父节点数据内容"""
        if len(data) < 14:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        result = {
            "从节点序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')},
            "从节点地址": data[2:8].hex().upper(),
            "父节点地址": data[8:14].hex().upper()
        }
        return result

    def _parse_query_mapping_node_count_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回映射表从节点数量（E8 00 03 09）
        下行查询：无数据；上行应答：2字节 BIN 小端
        """
        if len(data) < 2:
            return {"说明": "查询命令，无数据内容"}
        count = int.from_bytes(data[0:2], 'little')
        return {
            "映射表从节点数量": {"原始值": data[0:2].hex().upper(), "十进制": count}
        }

    def _parse_query_mapping_table_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询从节点通信地址映射表数据内容"""
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "起始序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')},
            "查询数量": {"原始值": f"0x{data[2]:02X}", "十进制": data[2]}
        }

    def _parse_return_mapping_table_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询从节点通信地址映射表数据内容"""
        if len(data) < 4:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        total_count = int.from_bytes(data[0:2], 'big')
        return_count = data[2]
        result = {
            "总记录数": {"原始值": data[0:2].hex().upper(), "十进制": total_count},
            "返回记录数": {"原始值": f"0x{data[2]:02X}", "十进制": return_count},
            "映射表": []
        }
        pos = 3
        for i in range(return_count):
            if pos + 12 > len(data):
                break
            result["映射表"].append({
                "序号": i + 1,
                "从节点地址": data[pos:pos+6].hex().upper(),
                "通信地址": data[pos+6:pos+12].hex().upper()
            })
            pos += 12
        return result

    def _parse_query_task_timeout_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回任务建议超时时间（E8 00 03 0B）
        下行查询：无数据；上行应答：4×2字节 BIN 小端（优先级0~3的超时时间）
        """
        if len(data) < 8:
            return {"说明": "查询命令，无数据内容"}
        result = {}
        for i in range(4):
            offset = i * 2
            timeout = int.from_bytes(data[offset:offset+2], 'little')
            result[f"优先级{i}的任务建议超时时间"] = {
                "原始值": data[offset:offset+2].hex().upper(),
                "十进制": timeout,
                "单位": "秒"
            }
        return result

    def _parse_query_slave_phase_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询从节点相位信息数据内容（E8 03 03 0C）

        格式：本次查询从节点数量n(1B) + 从节点地址1(6B) + ... + 从节点地址n(6B)
        """
        if len(data) < 1:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        node_count = data[0]
        result = {
            "本次查询从节点数量": {"原始值": f"0x{node_count:02X}", "十进制": node_count}
        }
        pos = 1
        nodes = []
        for i in range(node_count):
            if pos + 6 > len(data):
                break
            nodes.append({
                "序号": i + 1,
                "从节点地址": data[pos:pos+6].hex().upper()
            })
            pos += 6
        result["从节点列表"] = nodes
        return result

    def _parse_batch_query_phase_data(self, data: bytes) -> Dict[str, Any]:
        """解析批量查询从节点相位信息数据内容"""
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "起始序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')},
            "查询数量": {"原始值": f"0x{data[2]:02X}", "十进制": data[2]}
        }

    def _parse_query_region_identify_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询表档案的台区识别结果数据内容"""
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "起始序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')},
            "查询数量": {"原始值": f"0x{data[2]:02X}", "十进制": data[2]}
        }

    def _parse_query_extra_node_region_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询多余节点的台区识别结果数据内容"""
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "起始序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')},
            "查询数量": {"原始值": f"0x{data[2]:02X}", "十进制": data[2]}
        }

    def _get_slave_node_type_desc(self, node_type: int) -> str:
        """获取从节点类型说明"""
        types = {
            0x01: "电能表",
            0x02: "采集器",
            0x03: "集中器",
            0x04: "中继器",
            0xFF: "未知类型"
        }
        return types.get(node_type, f"未知类型({node_type:02X})")

    def _get_slave_node_status_desc(self, status: int) -> str:
        """获取从节点状态说明"""
        statuses = {
            0x00: "离线",
            0x01: "在线",
            0x02: "通信异常",
            0x03: "未注册"
        }
        return statuses.get(status, f"未知状态({status:02X})")

    # ==================== AFN=04H 写参数 ====================

    def _parse_set_master_node_addr_data(self, data: bytes) -> Dict[str, Any]:
        """解析设置主节点地址数据内容（E8 02 04 01）"""
        if len(data) < 6:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "主节点地址": {"原始值": data[0:6].hex().upper()}
        }

    def _parse_add_slave_node_data(self, data: bytes) -> Dict[str, Any]:
        """解析添加从节点数据内容（E8 02 04 02）"""
        if len(data) < 1:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        node_count = data[0]
        result = {
            "从节点数量": {"原始值": f"0x{node_count:02X}", "十进制": node_count}
        }
        pos = 1
        nodes = []
        for i in range(node_count):
            if pos + 6 > len(data):
                break
            nodes.append({
                "序号": i + 1,
                "从节点地址": data[pos:pos+6].hex().upper()
            })
            pos += 6
        result["从节点列表"] = nodes
        return result

    def _parse_delete_slave_node_data(self, data: bytes) -> Dict[str, Any]:
        """解析删除从节点数据内容（E8 02 04 03）"""
        if len(data) < 1:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        node_count = data[0]
        result = {
            "从节点数量": {"原始值": f"0x{node_count:02X}", "十进制": node_count}
        }
        pos = 1
        nodes = []
        for i in range(node_count):
            if pos + 6 > len(data):
                break
            nodes.append({
                "序号": i + 1,
                "从节点地址": data[pos:pos+6].hex().upper()
            })
            pos += 6
        result["从节点列表"] = nodes
        return result

    def _parse_set_event_report_data(self, data: bytes) -> Dict[str, Any]:
        """解析允许/禁止从节点上报数据内容（E8 02 04 04）"""
        if len(data) < 1:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "事件上报状态标志": {"原始值": f"0x{data[0]:02X}", "说明": "允许上报" if data[0] == 0x01 else "禁止上报"}
        }

    def _parse_activate_slave_reg_data(self, data: bytes) -> Dict[str, Any]:
        """解析激活从节点主动注册数据内容（E8 02 04 05）"""
        return {"说明": "激活从节点主动注册命令，无数据内容"}

    def _parse_terminate_slave_reg_data(self, data: bytes) -> Dict[str, Any]:
        """解析终止从节点主动注册数据内容（E8 02 04 06）"""
        return {"说明": "终止从节点主动注册命令，无数据内容"}

    def _parse_add_mapping_table_data(self, data: bytes) -> Dict[str, Any]:
        """解析添加从节点通信地址映射表数据内容（E8 02 04 07）"""
        if len(data) < 1:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        node_count = data[0]
        result = {
            "本次添加从节点数量": {"原始值": f"0x{node_count:02X}", "十进制": node_count}
        }
        pos = 1
        records = []
        for i in range(node_count):
            if pos + 18 > len(data):
                break
            records.append({
                "序号": i + 1,
                "从节点通信地址": data[pos:pos+6].hex().upper(),
                "从节点表计地址": data[pos+6:pos+18].hex().upper()
            })
            pos += 18
        result["映射表"] = records
        return result

    # ==================== AFN=05H 上报信息 ====================

    def _parse_report_task_data(self, data: bytes) -> Dict[str, Any]:
        """解析上报任务数据数据内容"""
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
            
        # 任务 ID: 2 字节 (小端序)
        task_id = int.from_bytes(data[0:2], 'little')
        # 报文长度 L: 1 字节
        msg_len = data[2]
            
        result = {
            "任务 ID": {"原始值": data[0:2].hex().upper(), "十进制": task_id},
            "报文长度": {"原始值": f"0x{data[2]:02X}", "十进制": msg_len}
        }
            
        # 报文内容：L 字节
        if len(data) >= 3 + msg_len:
            result["报文内容"] = data[3:3+msg_len].hex().upper()
        else:
            result["报文内容"] = data[3:].hex().upper()
            
        return result

    def _parse_report_event_data(self, data: bytes) -> Dict[str, Any]:
        """解析上报从节点事件数据内容"""
        if len(data) < 9:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        result = {
            "从节点地址": data[0:6].hex().upper(),
            "事件类型": {"原始值": f"0x{data[6]:02X}", "说明": self._get_event_type_desc(data[6])},
            "事件数据长度": {"原始值": f"0x{data[7]:02X}", "十进制": data[7]}
        }
        event_len = data[7]
        if len(data) >= 8 + event_len:
            result["事件数据"] = data[8:8+event_len].hex().upper()
        else:
            result["事件数据"] = data[8:].hex().upper()
        return result

    def _get_event_type_desc(self, event_type: int) -> str:
        """获取事件类型说明"""
        events = {
            0x01: "上电事件",
            0x02: "掉电事件",
            0x03: "通信异常事件",
            0x04: "通信恢复事件",
            0x05: "数据异常事件",
            0x06: "参数变更事件",
            0x07: "告警事件",
            0x08: "故障事件"
        }
        return events.get(event_type, f"未知事件 ({event_type:02X})")
    
    # ==================== AFN=05H 上报信息 (续) ====================
    
    def _parse_report_slave_node_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析上报从节点信息数据内容"""
        if len(data) < 1:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        node_count = data[0]
        result = {
            "上报从节点数量": {"原始值": f"0x{node_count:02X}", "十进制": node_count},
            "从节点列表": []
        }
        pos = 1
        for i in range(node_count):
            if pos + 6 > len(data):
                break
            result["从节点列表"].append({
                "序号": i + 1,
                "从节点地址": data[pos:pos+6].hex().upper()
            })
            pos += 6
        if len(data) > pos:
            result["剩余数据"] = data[pos:].hex().upper()
        return result
    
    def _parse_report_reg_end_data(self, data: bytes) -> Dict[str, Any]:
        """解析上报从节点主动注册结束数据内容"""
        return {"说明": "从节点主动注册结束，无数据内容"}
    
    def _parse_report_task_status_data(self, data: bytes) -> Dict[str, Any]:
        """解析上报任务状态数据内容 (DI=E8:05:05:05)"""
        if len(data) < 9:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
            
        task_id = int.from_bytes(data[0:2], 'little')  # 任务 ID: 2 字节 (小端序)
        node_addr = data[2:8]  # 6 字节，从第 3 个字节开始
        task_status = data[8]
            
        # 任务状态说明
        status_desc = {
            0x00: "成功",
            0x01: "从节点无响应",
            0x02: "数据不合法",
            0xFF: "其他错误"
        }
            
        result = {
            "任务 ID": {
                "原始值": data[0:2].hex().upper(),
                "十进制": task_id
            },
            "从节点地址": {
                "原始值": node_addr.hex().upper(),
                "说明": "失败从节点的地址"
            },
            "任务状态": {
                "原始值": f"0x{task_status:02X}",
                "说明": status_desc.get(task_status, f"未知状态 ({task_status:02X})")
            }
        }
            
        if len(data) > 9:
            result["剩余数据"] = data[9:].hex().upper()
            
        return result

    # ==================== AFN=06H 请求信息 ====================

    @staticmethod
    def _bcd_to_str(b: int) -> str:
        """将1字节BCD编码转为字符串，如0x26 -> '26'"""
        return f"{(b >> 4) & 0x0F}{b & 0x0F}"

    def _parse_request_time_data(self, data: bytes) -> Dict[str, Any]:
        """解析请求/返回集中器时间数据内容（E8 06 06 01）

        上行（模块请求）：无数据内容
        下行（集中器应答）：6字节 BCD 时间（秒分时日月年）
        """
        if len(data) < 6:
            return {"说明": "请求时间命令，无数据内容"}

        sec = self._bcd_to_str(data[0])
        minute = self._bcd_to_str(data[1])
        hour = self._bcd_to_str(data[2])
        day = self._bcd_to_str(data[3])
        month = self._bcd_to_str(data[4])
        year = self._bcd_to_str(data[5])
        return {
            "当前时间-秒": {"原始值": f"0x{data[0]:02X}", "BCD": sec},
            "当前时间-分": {"原始值": f"0x{data[1]:02X}", "BCD": minute},
            "当前时间-时": {"原始值": f"0x{data[2]:02X}", "BCD": hour},
            "当前时间-日": {"原始值": f"0x{data[3]:02X}", "BCD": day},
            "当前时间-月": {"原始值": f"0x{data[4]:02X}", "BCD": month},
            "当前时间-年": {"原始值": f"0x{data[5]:02X}", "BCD": f"20{year}"},
            "时间": f"20{year}-{month}-{day} {hour}:{minute}:{sec}"
        }

    # ==================== AFN=07H 传输文件 ====================

    def _parse_start_file_transfer_data(self, data: bytes) -> Dict[str, Any]:
        """解析启动文件传输数据内容"""
        if len(data) < 16:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "文件类型": {"原始值": f"0x{data[0]:02X}", "说明": self._get_file_type_desc(data[0])},
            "文件ID": {"原始值": f"0x{data[1]:02X}", "十进制": data[1]},
            "目的地址": data[2:8].hex().upper(),
            "总段数": {"原始值": data[8:10].hex().upper(), "十进制": int.from_bytes(data[8:10], 'big')},
            "文件大小": {"原始值": data[10:14].hex().upper(), "十进制": int.from_bytes(data[10:14], 'big'), "单位": "字节"},
            "文件校验和": data[14:16].hex().upper(),
            "超时时间": {"原始值": f"0x{data[16]:02X}", "十进制": data[16], "单位": "秒"} if len(data) > 16 else None
        }

    def _parse_file_content_data(self, data: bytes) -> Dict[str, Any]:
        """解析传输文件内容数据内容"""
        if len(data) < 6:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        segment_no = int.from_bytes(data[0:2], 'big')
        segment_len = int.from_bytes(data[2:4], 'big')
        result = {
            "段序号": {"原始值": data[0:2].hex().upper(), "十进制": segment_no},
            "段长度": {"原始值": data[2:4].hex().upper(), "十进制": segment_len},
            "段数据": data[4:4+segment_len].hex().upper() if len(data) >= 4 + segment_len else data[4:].hex().upper()
        }
        if len(data) >= 4 + segment_len + 2:
            result["段校验和"] = data[4+segment_len:6+segment_len].hex().upper()
        return result

    def _parse_query_file_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回文件信息（E8 00 07 03）
        下行查询：无数据；上行应答：文件性质(1B) + 文件ID(1B) + 目的地址(6B) + 总段数(2B) + 文件大小(4B) + 总校验(2B) + 已接收段数(2B)
        """
        if len(data) < 18:
            return {"说明": "查询命令，无数据内容"}
        result = {
            "文件性质": {"原始值": f"0x{data[0]:02X}", "说明": self._get_file_nature_desc(data[0])},
            "文件ID": {"原始值": f"0x{data[1]:02X}", "十进制": data[1]},
            "目的地址": {"原始值": data[2:8].hex().upper()},
            "文件总段数": {"原始值": data[8:10].hex().upper(), "十进制": int.from_bytes(data[8:10], 'big')},
            "文件大小": {"原始值": data[10:14].hex().upper(), "十进制": int.from_bytes(data[10:14], 'big'), "单位": "字节"},
            "文件总校验": {"原始值": data[14:16].hex().upper()},
            "已成功接收文件段数": {"原始值": data[16:18].hex().upper(), "十进制": int.from_bytes(data[16:18], 'big')}
        }
        return result

    @staticmethod
    def _get_file_nature_desc(nature: int) -> str:
        """获取文件性质说明"""
        descs = {0: "清除下装文件", 1: "本地通信模块文件", 2: "从节点模块文件", 3: "采集器文件"}
        return descs.get(nature, f"未知({nature})")

    def _parse_query_file_progress_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询/返回文件处理进度（E8 00 07 04）
        下行查询：无数据；上行应答：文件处理进度(1B) + 处理未完成的文件ID(1B) + 失败的节点数量(2B)
        """
        if len(data) < 1:
            return {"说明": "查询命令，无数据内容"}
        progress = data[0]
        progress_map = {0: "全部成功，可接收新文件", 1: "正在处理", 2: "未全部成功，存在失败节点"}
        result = {
            "文件处理进度": {"原始值": f"0x{progress:02X}", "说明": progress_map.get(progress, f"未知({progress})")}
        }
        if len(data) >= 2:
            result["处理未完成的文件ID"] = {"原始值": f"0x{data[1]:02X}", "十进制": data[1]}
        if len(data) >= 4:
            result["失败的节点数量"] = {"原始值": data[2:4].hex().upper(), "十进制": int.from_bytes(data[2:4], 'big')}
        return result

    def _parse_query_file_failed_nodes_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询文件传输失败节点数据内容"""
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "起始序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')},
            "查询数量": {"原始值": f"0x{data[2]:02X}", "十进制": data[2]}
        }

    def _parse_return_file_failed_nodes_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询文件传输失败节点数据内容"""
        if len(data) < 4:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        total_count = int.from_bytes(data[0:2], 'big')
        return_count = data[2]
        result = {
            "总失败节点数": {"原始值": data[0:2].hex().upper(), "十进制": total_count},
            "返回节点数": {"原始值": f"0x{data[2]:02X}", "十进制": return_count},
            "失败节点列表": []
        }
        pos = 3
        for i in range(return_count):
            if pos + 7 > len(data):
                break
            result["失败节点列表"].append({
                "序号": i + 1,
                "从节点地址": data[pos:pos+6].hex().upper(),
                "失败原因": {"原始值": f"0x{data[pos+6]:02X}", "说明": self._get_file_fail_reason_desc(data[pos+6])}
            })
            pos += 7
        return result

    def _get_file_type_desc(self, file_type: int) -> str:
        """获取文件类型说明"""
        types = {
            0x01: "固件升级文件",
            0x02: "配置文件",
            0x03: "数据文件",
            0x04: "日志文件"
        }
        return types.get(file_type, f"未知类型({file_type:02X})")

    def _get_file_fail_reason_desc(self, reason: int) -> str:
        """获取文件传输失败原因说明"""
        reasons = {
            0x01: "存储空间不足",
            0x02: "校验错误",
            0x03: "写入失败",
            0x04: "超时",
            0x05: "不支持此文件类型",
            0x06: "文件过大",
            0x07: "正在处理其他文件"
        }
        return reasons.get(reason, f"未知原因({reason:02X})")

    # ==================== 厂商扩展 - 节点运行时长 ====================

    def _parse_query_node_runtime_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询节点运行时长数据内容（E8 03 03 66）- 下行查询"""
        if len(data) < 6:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "从节点地址": {"原始值": data[0:6].hex().upper()}
        }

    def _parse_return_node_runtime_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询节点运行时长数据内容（E8 04 03 66）- 上行应答"""
        if len(data) < 6:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        result = {
            "从节点地址": {"原始值": data[0:6].hex().upper()}
        }
        if len(data) > 6:
            runtime = int.from_bytes(data[6:10], 'little') if len(data) >= 10 else int.from_bytes(data[6:], 'little')
            result["运行时长"] = {"原始值": data[6:min(10, len(data))].hex().upper(), "十进制": runtime, "单位": "秒"}
        return result

    def _parse_query_multi_network_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询多网络信息数据内容（E8 00 03 91）- 下行查询，无数据域"""
        return {"说明": "查询多网络信息，无数据内容"}

    def _parse_query_whitelist_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询白名单生效信息数据内容（E8 00 03 93）- 下行查询，无数据域"""
        return {"说明": "查询白名单生效信息，无数据内容"}

    def _parse_query_broadband_province_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询宽带应用省份数据内容（E8 00 F0 DF）- 下行查询，无数据域"""
        return {"说明": "查询宽带应用省份，无数据内容"}

    # ==================== 深化应用 - 模块资产信息（1-1.md 表69~73）====================

    def _get_asset_element_name(self, element_id: int) -> str:
        """获取信息元素名称"""
        info = self.ASSET_INFO_ELEMENT.get(element_id)
        return info["名称"] if info else f"未知元素(0x{element_id:02X})"

    def _format_asset_value(self, element_id: int, raw: bytes) -> str:
        """格式化信息元素的值"""
        info = self.ASSET_INFO_ELEMENT.get(element_id)
        if not info:
            return raw.hex().upper()
        fmt = info["格式"]
        if fmt == "ASCII":
            try:
                return raw.decode('ascii')
            except Exception:
                return raw.hex().upper()
        elif fmt == "BCD":
            return raw.hex().upper()
        elif fmt == "YYMMDD":
            if len(raw) >= 3:
                return f"20{raw[0]:02d}-{raw[1]:02d}-{raw[2]:02d}"
            return raw.hex().upper()
        elif fmt == "BIN":
            if element_id == 0x08 and all(b == 0xFF for b in raw):
                return raw.hex().upper() + "（不支持或读取错误）"
            return raw.hex().upper()
        return raw.hex().upper()

    def _parse_query_asset_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询模块资产信息（E8 03 03 13）- 下行

        格式：节点地址(6B) + 信息列表元素数量n(1B) + 信息元素ID1(1B) ... IDn(1B)
        """
        if len(data) < 7:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        result = {
            "节点地址": {"原始值": data[0:6].hex().upper()}
        }
        elem_count = data[6]
        ids = []
        for i in range(elem_count):
            pos = 7 + i
            if pos >= len(data):
                break
            eid = data[pos]
            ids.append({
                "序号": i + 1,
                "信息元素ID": f"0x{eid:02X}",
                "名称": self._get_asset_element_name(eid)
            })
        result["信息列表元素数量"] = {"原始值": f"0x{elem_count:02X}", "十进制": elem_count}
        result["信息元素列表"] = ids
        return result

    def _parse_return_asset_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询模块资产信息（E8 04 03 13）- 上行

        格式：节点地址(6B) + [信息元素ID(1B) + 长度(1B) + 数据(变长)] * n
        """
        if len(data) < 6:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        result = {
            "节点地址": {"原始值": data[0:6].hex().upper()}
        }
        elements = []
        pos = 6
        idx = 0
        while pos + 2 <= len(data):
            eid = data[pos]
            length = data[pos + 1]
            pos += 2
            if pos + length > len(data):
                raw = data[pos:]
                pos = len(data)
            else:
                raw = data[pos:pos + length]
                pos += length
            elements.append({
                "序号": idx + 1,
                "信息元素ID": f"0x{eid:02X}",
                "名称": self._get_asset_element_name(eid),
                "数据长度": length,
                "数据值": self._format_asset_value(eid, raw),
                "原始值": raw.hex().upper()
            })
            idx += 1
        result["信息元素列表"] = elements
        return result

    def _parse_batch_query_asset_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析批量查询模块资产信息（E8 03 03 14）- 下行

        格式：节点起始序号m(2B) + 节点数量n(1B) + 信息元素ID(1B)
        """
        if len(data) < 4:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        eid = data[3]
        return {
            "节点起始序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'big')},
            "节点数量": {"原始值": f"0x{data[2]:02X}", "十进制": data[2]},
            "信息元素ID": {"原始值": f"0x{eid:02X}", "名称": self._get_asset_element_name(eid)}
        }

    def _parse_batch_return_asset_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析批量返回查询模块资产信息（E8 04 03 14）- 上行

        格式：本次应答从节点数量n(1B) + 信息元素ID(1B)
              + [从节点地址(6B) + 信息元素数据(变长，长度由元素ID确定)] * n
        """
        if len(data) < 2:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        node_count = data[0]
        eid = data[1]
        elem_info = self.ASSET_INFO_ELEMENT.get(eid)
        elem_len = elem_info["字节数"] if elem_info else 0

        result = {
            "本次应答从节点数量": {"原始值": f"0x{node_count:02X}", "十进制": node_count},
            "信息元素ID": {"原始值": f"0x{eid:02X}", "名称": self._get_asset_element_name(eid)}
        }
        nodes = []
        pos = 2
        for i in range(node_count):
            if pos + 6 > len(data):
                break
            addr = data[pos:pos + 6]
            pos += 6
            if elem_len > 0 and pos + elem_len <= len(data):
                raw = data[pos:pos + elem_len]
                pos += elem_len
            else:
                raw = data[pos:]
                pos = len(data)
            nodes.append({
                "序号": i + 1,
                "从节点地址": addr.hex().upper(),
                "数据值": self._format_asset_value(eid, raw),
                "原始值": raw.hex().upper()
            })
        result["从节点列表"] = nodes
        return result

    # ==================== 深化应用 - 台区识别（1-1.md）====================

    def _parse_query_region_status_data(self, data: bytes) -> Dict[str, Any]:
        """解析查询台区识别状态（E8 03 03 10）- 下行查询，无数据"""
        return {"说明": "查询命令，无数据内容"}

    def _parse_return_region_status_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询台区识别状态（E8 04 03 10）

        格式：台区识别状态(1B) + 剩余时长(2B) + 保留(1B)
        """
        if len(data) < 4:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        status = data[0]
        remain = int.from_bytes(data[1:3], 'little')
        status_desc = "识别中" if status == 1 else "未识别或识别完成或识别停止"
        remain_desc = "无效(0xFF)" if status == 0 and remain == 0xFFFF else f"{remain}分钟"
        result = {
            "台区识别状态": {"原始值": f"0x{status:02X}", "十进制": status, "说明": status_desc},
            "剩余时长": {"原始值": data[1:3].hex().upper(), "十进制": remain, "说明": remain_desc}
        }
        if len(data) > 3:
            result["保留"] = f"0x{data[3]:02X}"
        return result

    def _parse_start_region_identify_data(self, data: bytes) -> Dict[str, Any]:
        """解析启动台区识别（E8 02 04 80）

        格式：台区特征发送时长(2B) + 保留(1B)
        """
        if len(data) < 2:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        duration = int.from_bytes(data[0:2], 'little')
        duration_desc = "1440分钟" if duration == 0 else f"{duration}分钟"
        result = {
            "台区特征发送时长": {"原始值": data[0:2].hex().upper(), "十进制": duration, "说明": duration_desc}
        }
        if len(data) > 2:
            result["保留"] = f"0x{data[2]:02X}"
        return result

    def _parse_stop_region_identify_data(self, data: bytes) -> Dict[str, Any]:
        """解析停止台区识别（E8 02 04 81）- 无数据"""
        return {"说明": "停止台区识别命令，无数据内容"}

    def _parse_report_other_region_node_data(self, data: bytes) -> Dict[str, Any]:
        """解析上报非本台区从节点信息（E8 05 05 80）

        格式：从节点地址(6B) + 从节点设备类型(1B) + 采集器下接电表数量n(1B)
              + 应属台区主节点地址(6B) + 保留(2B)
              + [电表地址(6B)] * n（仅采集器类型时有效）
        """
        if len(data) < 16:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        node_addr = data[0:6]
        device_type = data[6]
        meter_count = data[7]
        region_addr = data[8:14]
        device_type_desc = "采集器" if device_type == 0x00 else "电表" if device_type == 0x01 else f"未知(0x{device_type:02X})"

        result = {
            "从节点地址": {"原始值": node_addr.hex().upper()},
            "从节点设备类型": {"原始值": f"0x{device_type:02X}", "说明": device_type_desc},
            "采集器下接电表数量": {"原始值": f"0x{meter_count:02X}", "十进制": meter_count},
            "应属台区主节点地址": {"原始值": region_addr.hex().upper()}
        }
        if len(data) >= 16:
            result["保留"] = data[14:16].hex().upper()

        # 当设备类型为采集器(0x00)时，解析电表地址列表
        pos = 16
        if device_type == 0x00 and meter_count > 0:
            meters = []
            for i in range(meter_count):
                if pos + 6 > len(data):
                    break
                meters.append({
                    "序号": i + 1,
                    "电表地址": data[pos:pos+6].hex().upper()
                })
                pos += 6
            result["电表地址列表"] = meters

        if pos < len(data):
            result["剩余数据"] = data[pos:].hex().upper()
        return result

    # ==================== 深化应用 - 交采数据（1-1.md）====================

    def _parse_request_acquisition_data(self, data: bytes) -> Dict[str, Any]:
        """解析请求交采数据（E8 03 06 02）

        格式：数据项类型(1B) + 交采数据项标识(4B) + 采集周期(1B) + 采集数量(1B)
        """
        if len(data) < 7:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        data_type = data[0]
        type_desc = "DL/T645-2007数据项标识" if data_type == 1 else f"保留({data_type})"
        return {
            "数据项类型": {"原始值": f"0x{data_type:02X}", "说明": type_desc},
            "交采数据项标识": {"原始值": data[1:5].hex().upper()},
            "采集周期": {"原始值": f"0x{data[5]:02X}", "十进制": data[5], "单位": "秒"},
            "采集数量": {"原始值": f"0x{data[6]:02X}", "十进制": data[6]}
        }

    def _parse_return_acquisition_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回请求交采数据（E8 04 06 02）

        格式：数据项类型(1B) + 交采数据项标识(4B) + 交采数据项内容(NB)
        """
        if len(data) < 5:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        data_type = data[0]
        type_desc = "DL/T645-2007数据项标识" if data_type == 1 else f"保留({data_type})"
        result = {
            "数据项类型": {"原始值": f"0x{data_type:02X}", "说明": type_desc},
            "交采数据项标识": {"原始值": data[1:5].hex().upper()}
        }
        if len(data) > 5:
            result["交采数据项内容"] = data[5:].hex().upper()
        return result

    # ==================== 深化应用 - 返回相位信息（1-1.md 表37/39/40）====================

    def _parse_phase_info(self, phase_bytes: bytes) -> Dict[str, Any]:
        """解析扩展的2字节相位信息（1-1.md 表40）

        字节1: 相序类型(D7-D5) + 相线特征(D4-D3) + 相线标识(D2-D1-D0)
        字节2: 模块类型(D7-D6) + 保留(D5-D3) + 规约类型(D2-D1-D0)
        """
        if len(phase_bytes) < 2:
            return {"原始值": phase_bytes.hex().upper(), "说明": "数据不足"}

        b1 = phase_bytes[0]
        b2 = phase_bytes[1]

        # 字节1解析
        phase_seq = (b1 >> 5) & 0x07
        phase_seq_map = {
            0: "三相表ABC(正常相序)", 1: "三相表ACB(逆相序)",
            2: "三相表BAC(逆相序)", 3: "三相表BCA(逆相序)",
            4: "三相表CAB(逆相序)", 5: "三相表CBA(逆相序)",
            6: "零火反接", 7: "保留"
        }
        line_feature = (b1 >> 3) & 0x03
        line_feature_map = {0: "支持相线识别", 1: "不支持相线识别", 2: "相线不确定"}
        line_flag = b1 & 0x07
        phases = []
        if line_flag & 0x01: phases.append("A相")
        if line_flag & 0x02: phases.append("B相")
        if line_flag & 0x04: phases.append("C相")
        line_flag_desc = ",".join(phases) if phases else "无"

        # 字节2解析
        module_type = (b2 >> 6) & 0x03
        module_type_map = {0: "未知", 1: "三相表", 2: "单相表"}
        proto_type = b2 & 0x07
        proto_type_map = {0: "未知规约", 1: "DLT/645-1997", 2: "DLT/645-2007", 3: "CJ/T188"}

        return {
            "原始值": phase_bytes.hex().upper(),
            "相序类型": phase_seq_map.get(phase_seq, f"保留({phase_seq})"),
            "相线特征": line_feature_map.get(line_feature, f"保留({line_feature})"),
            "相线标识": line_flag_desc,
            "模块类型": module_type_map.get(module_type, f"保留({module_type})"),
            "规约类型": proto_type_map.get(proto_type, f"保留({proto_type})")
        }

    def _parse_return_slave_phase_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回查询从节点相位信息（E8 04 03 0C）- 1-1.md 表37

        格式：本次应答从节点数量n(1B) + [从节点地址(6B) + 相位信息(2B)] * n
        """
        if len(data) < 1:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        node_count = data[0]
        result = {
            "本次应答的从节点数量": {"原始值": f"0x{node_count:02X}", "十进制": node_count},
            "从节点列表": []
        }
        pos = 1
        for i in range(node_count):
            if pos + 8 > len(data):
                break
            addr = data[pos:pos+6].hex().upper()
            phase = self._parse_phase_info(data[pos+6:pos+8])
            result["从节点列表"].append({
                "序号": i + 1,
                "从节点地址": addr,
                "相位信息": phase
            })
            pos += 8
        return result

    def _parse_return_batch_phase_data(self, data: bytes) -> Dict[str, Any]:
        """解析返回批量查询从节点相位信息（E8 04 03 0D）- 1-1.md 表39

        格式：从节点总数量(2B) + 本次应答从节点数量n(1B)
              + [从节点地址(6B) + 相位信息(2B)] * n
        """
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        total = int.from_bytes(data[0:2], 'little')
        node_count = data[2]
        result = {
            "从节点总数量": {"原始值": data[0:2].hex().upper(), "十进制": total},
            "本次应答的从节点数量": {"原始值": f"0x{node_count:02X}", "十进制": node_count},
            "从节点列表": []
        }
        pos = 3
        for i in range(node_count):
            if pos + 8 > len(data):
                break
            addr = data[pos:pos+6].hex().upper()
            phase = self._parse_phase_info(data[pos+6:pos+8])
            result["从节点列表"].append({
                "序号": i + 1,
                "从节点地址": addr,
                "相位信息": phase
            })
            pos += 8
        return result

    # ==================== 深化应用 - 批量查询厂商代码和版本信息（1-1.md）====================

    def _parse_batch_query_vendor_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析批量查询厂商代码和版本信息（E8 03 03 12）- 下行

        格式：节点起始序号m(2B) + 节点数量n(1B)
        """
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        return {
            "节点起始序号": {"原始值": data[0:2].hex().upper(), "十进制": int.from_bytes(data[0:2], 'little')},
            "节点数量": {"原始值": f"0x{data[2]:02X}", "十进制": data[2]}
        }

    def _parse_batch_return_vendor_info_data(self, data: bytes) -> Dict[str, Any]:
        """解析批量返回查询厂商代码和版本信息（E8 04 03 12）- 上行

        格式：节点总数量m(2B) + 本次应答从节点数量n(1B)
              + [节点地址(6B) + 节点信息(9B: 厂商代码2B + 芯片代码2B + 版本时间3B + 版本号2B)] * n
        """
        if len(data) < 3:
            return {"原始数据": data.hex().upper(), "说明": "数据长度不足"}
        total = int.from_bytes(data[0:2], 'little')
        node_count = data[2]
        result = {
            "节点总数量": {"原始值": data[0:2].hex().upper(), "十进制": total},
            "本次应答的从节点数量": {"原始值": f"0x{node_count:02X}", "十进制": node_count},
            "节点列表": []
        }
        pos = 3
        for i in range(node_count):
            if pos + 15 > len(data):
                break
            addr = data[pos:pos+6].hex().upper()
            info = data[pos+6:pos+15]
            vendor_info = {"原始值": info.hex().upper()}
            try:
                vendor_info["厂商代码"] = info[0:2].decode('ascii')
                vendor_info["芯片代码"] = info[2:4].decode('ascii')
                vendor_info["版本时间"] = f"20{info[4]:02d}-{info[5]:02d}-{info[6]:02d}"
                vendor_info["版本号"] = info[7:9].hex().upper()
            except Exception:
                pass
            result["节点列表"].append({
                "序号": i + 1,
                "节点地址": addr,
                "节点信息": vendor_info
            })
            pos += 15
        return result

    def _calculate_checksum(self, data: bytes) -> int:
        """计算校验和"""
        return sum(data) & 0xFF


