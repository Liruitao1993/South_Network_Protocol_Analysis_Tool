import json
import os

class DLT645Parser:
    """DLT645-2007 电表协议解析器"""

    @staticmethod
    def _load_di_map():
        """从 JSON 文件加载完整的 DI 映射表"""
        json_path = os.path.join(os.path.dirname(__file__), 'dlt645_di.json')

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('di_map', {})
        except Exception as e:
            print(f"加载 DLT645 DI 映射表失败: {e}")
            # 返回基本 DI 映射作为后备
            return {
                "00010000": {"name": "当前正向有功总电能", "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4},
                "00020000": {"name": "当前反向有功总电能", "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4},
            }

    @staticmethod
    def check_frame(data: bytes) -> bool:
        if len(data) < 12:
            return False
        if data[0] != 0x68 or data[7] != 0x68 or data[-1] != 0x16:
            return False
        cs = sum(data[0:-2]) & 0xFF
        return cs == data[-2]

    @staticmethod
    def parse(data: bytes) -> dict:
        result = {
            'valid': False,
            'protocol': 'DLT645-2007',
            'raw_hex': data.hex().upper(),
            'address': '',
            'control': 0,
            'control_desc': '',
            'data_length': 0,
            'data': b'',
            'di_code': '',
            'di_desc': '',
            'checksum': 0,
            'checksum_valid': False,
            'fields': []
        }

        # 加载 DI 映射表
        DI_MAP = DLT645Parser._load_di_map()

        if not DLT645Parser.check_frame(data):
            result['error'] = '无效的DLT645帧格式'
            return result

        result['valid'] = True
        result['address'] = data[1:7][::-1].hex().upper()
        result['control'] = data[8]
        result['data_length'] = data[9]
        # 数据域解码：每个字节减 0x33，使用 & 0xFF 确保结果在有效字节范围内
        result['data'] = bytes([(b - 0x33) & 0xFF for b in data[10:10+result['data_length']]])
        result['checksum'] = data[-2]
        result['checksum_valid'] = (sum(data[0:-2]) & 0xFF) == data[-2]

        # 解析数据标识DI(前4字节)
        if len(result['data']) >=4:
            di_val = int.from_bytes(result['data'][0:4], byteorder='little')
            di_code_str = f"{di_val:08X}"
            result['di_code'] = di_code_str
            # 从 JSON 加载的 DI_MAP 使用字符串键
            di_info = DI_MAP.get(di_code_str)
            if di_info:
                result['di_desc'] = di_info['name']
                result['di_unit'] = di_info.get('unit', '')
                result['di_data_type'] = di_info.get('data_type', '')
            else:
                result['di_desc'] = "未知数据标识"
                result['di_unit'] = ""
                result['di_data_type'] = ""

        ctrl = result['control']
        ctrl_desc = []
        ctrl_parsed_value = []

        # 解析 D7 方向位
        if ctrl & 0x80:
            ctrl_parsed_value.append("DIR=1(从站应答)")
            ctrl_desc.append('从站应答')
            func = ctrl & 0x1F
            if func == 0x11:
                ctrl_desc.append('读数据应答')
                ctrl_parsed_value.append("FUNC=11H(读数据应答)")
            elif func == 0x12:
                ctrl_desc.append('读后续数据应答')
                ctrl_parsed_value.append("FUNC=12H(读后续数据应答)")
            elif func == 0x14:
                ctrl_desc.append('写数据应答')
                ctrl_parsed_value.append("FUNC=14H(写数据应答)")
            elif func == 0x13:
                ctrl_desc.append('读地址应答')
                ctrl_parsed_value.append("FUNC=13H(读地址应答)")
            elif func == 0x15:
                ctrl_desc.append('写地址应答')
                ctrl_parsed_value.append("FUNC=15H(写地址应答)")
            elif func == 0x16:
                ctrl_desc.append('冻结命令应答')
                ctrl_parsed_value.append("FUNC=16H(冻结命令应答)")
            elif func == 0x17:
                ctrl_desc.append('更改速率应答')
                ctrl_parsed_value.append("FUNC=17H(更改速率应答)")

            # D5 后续帧标志
            if ctrl & 0x20:
                ctrl_desc.append('有后续帧')
                ctrl_parsed_value.append("D5=1(有后续帧)")
            else:
                ctrl_parsed_value.append("D5=0(无后续帧)")
        else:
            ctrl_parsed_value.append("DIR=0(主站请求)")
            ctrl_desc.append('主站请求')
            func = ctrl & 0x1F
            if func == 0x11:
                ctrl_desc.append('读数据')
                ctrl_parsed_value.append("FUNC=11H(读数据)")
            elif func == 0x12:
                ctrl_desc.append('读后续数据')
                ctrl_parsed_value.append("FUNC=12H(读后续数据)")
            elif func == 0x14:
                ctrl_desc.append('写数据')
                ctrl_parsed_value.append("FUNC=14H(写数据)")
            elif func == 0x13:
                ctrl_desc.append('读通信地址')
                ctrl_parsed_value.append("FUNC=13H(读通信地址)")
            elif func == 0x15:
                ctrl_desc.append('写通信地址')
                ctrl_parsed_value.append("FUNC=15H(写通信地址)")
            elif func == 0x16:
                ctrl_desc.append('冻结命令')
                ctrl_parsed_value.append("FUNC=16H(冻结命令)")
            elif func == 0x17:
                ctrl_desc.append('更改通信速率')
                ctrl_parsed_value.append("FUNC=17H(更改通信速率)")
            elif func == 0x08:
                ctrl_desc.append('广播校时')
                ctrl_parsed_value.append("FUNC=08H(广播校时)")

        result['control_desc'] = ' | '.join(ctrl_desc)
        result['control_parsed'] = '; '.join(ctrl_parsed_value)

        result['fields'] = [
            ('帧起始符 1', '68H', '起始符'),
            ('从站地址', result['address'], '表地址，BCD编码，低位在前'),
            ('帧起始符 2', '68H', '起始符'),
            ('控制码', f"{ctrl:02X}H", result['control_desc']),
            ('数据长度', f"{result['data_length']} 字节", '数据域字节数'),
        ]

        if len(result['data']) >=4:
            result['fields'].append(('数据标识 DI', result['di_code'], result['di_desc']))
            if len(result['data']) >4:
                result['fields'].append(('数据内容', result['data'][4:].hex().upper(), '实际数据值'))
        else:
            result['fields'].append(('数据域', result['data'].hex().upper(), '解码后数据（减33H）'))

        result['fields'].extend([
            ('校验和', f"{result['checksum']:02X}H", 'CS校验'),
            ('帧结束符', '16H', '结束符')
        ])

        return result

    def verify(self, frame_bytes: bytes):
        """验证帧的协议一致性，返回 ValidationResult"""
        from validator.dlt645_validator import DLT645Validator
        validator = DLT645Validator()
        return validator.verify(frame_bytes)
