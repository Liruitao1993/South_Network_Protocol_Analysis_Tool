import json
import os
from typing import Tuple

from lme_info_entry_parser import parse_lme_dlt645, DI_STA_VERSION_SINGLE, DI_DUAL_ENTRY
from dlt645_data_codec import (
    FUNC_NAMES, decode_value, decode_err,
    split_write_request, split_change_password, split_clear_command,
)
from dlt645_pv_ext import merge_pv_di_map, is_pv_di, parse_pv_di

# LME自定义DI集合（手册《LME产品相关信息生产运维接口手册_V2.4》中走645框架的接口）
_LME_DI_CODES = (DI_STA_VERSION_SINGLE, DI_DUAL_ENTRY)

class DLT645Parser:
    """DLT645-2007 电表协议解析器"""

    @staticmethod
    def _load_di_map():
        """从 JSON 文件加载完整的 DI 映射表

        并入光伏协议转换单元 DL/T645-2007 扩展协议 DI（dlt645_pv_ext.PV_DI_MAP，
        单一来源；dlt645_di.json 是生成物，不写入扩展 DI）。
        """
        json_path = os.path.join(os.path.dirname(__file__), 'dlt645_di.json')

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return merge_pv_di_map(data.get('di_map', {}))
        except Exception as e:
            print(f"加载 DLT645 DI 映射表失败: {e}")
            # 返回基本 DI 映射作为后备
            return merge_pv_di_map({
                "00010000": {"name": "当前正向有功总电能", "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4},
                "00020000": {"name": "当前反向有功总电能", "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4},
            })

    @staticmethod
    def check_structure(data: bytes) -> Tuple[bool, str]:
        """结构判据（**不含** CS）：帧长 / 双 68H 起始符 / 16H 结束符

        返回 (是否通过, 中文原因)；通过时原因为空串。

        与「校验判据」分离的理由见 AGENTS.md §8 陷阱 23：校验和不符时帧内内容
        仍可完整解析，只应提示正确值，**不得**返回空白结果（用户报障场景）。
        同仓先例：protocol_parser.py 的南网解析器（照常解析 + 记录校验值/计算值/结果）。
        """
        if len(data) < 12:
            return False, f"帧长度不足 12 字节（实际 {len(data)} 字节）"
        if data[0] != 0x68 or data[7] != 0x68:
            bad = []
            if data[0] != 0x68:
                bad.append(f"第 1 字节应 68H（实际 {data[0]:02X}H）")
            if data[7] != 0x68:
                bad.append(f"第 8 字节应 68H（实际 {data[7]:02X}H）")
            return False, "帧起始符错误：" + "、".join(bad)
        if data[-1] != 0x16:
            return False, f"帧结束符错误：末字节应 16H（实际 {data[-1]:02X}H）"
        return True, ""

    @staticmethod
    def calc_checksum(data: bytes) -> int:
        """正确的校验和 CS = 起始符 68H 到数据域最后 1 字节的算术和 & 0xFF

        （DL/T645-2007 §6.2；单一来源：check_frame 与 parse 均调本方法，勿另写一份）
        """
        return sum(data[0:-2]) & 0xFF

    @staticmethod
    def check_frame(data: bytes) -> bool:
        """结构 + 校验全部通过（既有公开入口，语义不变）"""
        ok, _ = DLT645Parser.check_structure(data)
        return bool(ok) and DLT645Parser.calc_checksum(data) == data[-2]

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
            # 容错解析新增字段（1.23.22）：正确校验值 / 结构判据结果
            'checksum_expected': 0,
            'structure_valid': False,
            'structure_error': '',
            'fields': []
        }

        # 加载 DI 映射表
        DI_MAP = DLT645Parser._load_di_map()

        # ── 结构与校验判据拆分（AGENTS.md §8 陷阱 23）
        #    旧实现把「结构判据」（长度/双 68H/结束 16H）与「校验判据」（CS）混在
        #    check_frame 返回值里并提前 return ⇒ CS 写错时整张表为空，用户看不到任何内容。
        #    现在：长度 ≥12 一律继续完整解析，结构与校验结果分别记录 + 插入醒目提示行。
        #    参照同仓先例 protocol_parser.py（南网）：照常解析，只把失败标注出来。
        struct_ok, struct_err = DLT645Parser.check_structure(data)
        result['structure_valid'] = struct_ok
        result['structure_error'] = struct_err

        if len(data) < 12:
            # 连最短帧都不够，字段位置无法可靠定位：给出帧长说明 + 原始 hex（可接受的降级）
            result['error'] = (f"{struct_err}，无法定位完整字段"
                               "（DL/T645-2007 最短帧：68H + 地址(6B) + 68H + 控制码"
                               " + 数据长度 + CS + 16H = 12 字节）")
            result['fields'] = [
                ('❌ 帧长度不足', f"{len(data)} 字节",
                 'DL/T645-2007 最短帧：68H + 地址(6B) + 68H + 控制码 + 数据长度 + CS + 16H = 12 字节'),
                ('原始数据', data.hex().upper(), f"{len(data)} 字节"),
            ]
            return result

        result['address'] = data[1:7][::-1].hex().upper()
        result['control'] = data[8]
        result['data_length'] = data[9]
        # 校验数据域长度声明值与实际帧长度是否一致
        expected_total_len = 12 + result['data_length']  # 68+addr(6)+68+ctrl+len+data(N)+cs+16
        actual_data_len = len(data) - 12
        result['data_length_mismatch'] = actual_data_len != result['data_length']
        if result['data_length_mismatch']:
            result['error'] = (f"数据域长度不匹配：声明 {result['data_length']} 字节，"
                               f"实际 {actual_data_len} 字节（帧总长 {len(data)}，期望 {expected_total_len}）")
        # 数据域解码：每个字节减 0x33，使用 & 0xFF 确保结果在有效字节范围内
        # 即使长度不匹配也尽力解析实际存在的数据，方便用户排查
        actual_data_bytes = data[10:10 + min(result['data_length'], actual_data_len)] if actual_data_len > 0 else b''
        if actual_data_len < result['data_length']:
            # 声明比实际长：用实际有的数据解析
            result['data'] = bytes([(b - 0x33) & 0xFF for b in actual_data_bytes])
        else:
            # 声明比实际短：按声明长度解析（多余字节不处理）
            result['data'] = bytes([(b - 0x33) & 0xFF for b in data[10:10+result['data_length']]])
        result['checksum'] = data[-2]
        result['checksum_expected'] = DLT645Parser.calc_checksum(data)
        result['checksum_valid'] = result['checksum'] == result['checksum_expected']

        # 读通信地址应答(FUNC=0x13,从站)与写通信地址请求(FUNC=0x15,主站)
        # 数据域为6字节表地址（无数据标识DI）
        func_code = result['control'] & 0x1F
        addr_in_data = func_code in (0x13, 0x15) and len(result['data']) == 6
        if addr_in_data:
            result['address_in_data'] = result['data'][0:6][::-1].hex().upper()
        # 广播校时(FUNC=0x08)：数据域6字节为 ss mm hh DD MM 星期（BCD），无DI
        timing_in_data = func_code == 0x08 and len(result['data']) == 6
        # 异常应答(D6=1)：数据域仅1字节错误信息字ERR，无DI
        err_in_data = bool(result['control'] & 0x40) and len(result['data']) == 1
        no_di = addr_in_data or timing_in_data or err_in_data

        # 解析数据标识DI(前4字节)
        if len(result['data']) >= 4 and not no_di:
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
        func = ctrl & 0x1F
        func_name = FUNC_NAMES.get(func, f"未知功能码{func:02X}H")
        is_exception = bool(ctrl & 0x40)

        # 解析 D7 方向位
        if ctrl & 0x80:
            ctrl_parsed_value.append("DIR=1(从站应答)")
            ctrl_desc.append('从站应答')
            ctrl_desc.append(f"{func_name}应答" + ("（异常）" if is_exception else ""))
            ctrl_parsed_value.append(f"FUNC={func:02X}H({func_name}应答)")
            # D5 后续帧标志
            if ctrl & 0x20:
                ctrl_desc.append('有后续帧')
                ctrl_parsed_value.append("D5=1(有后续帧)")
            else:
                ctrl_parsed_value.append("D5=0(无后续帧)")
        else:
            ctrl_parsed_value.append("DIR=0(主站请求)")
            ctrl_desc.append('主站请求')
            ctrl_desc.append(func_name)
            ctrl_parsed_value.append(f"FUNC={func:02X}H({func_name})")

        # D6 异常应答标志
        if is_exception:
            ctrl_desc.append('异常应答')
            ctrl_parsed_value.append("D6=1(异常应答)")

        result['control_desc'] = ' | '.join(ctrl_desc)
        result['control_parsed'] = '; '.join(ctrl_parsed_value)

        # LME自定义接口（手册4.2/4.6/4.7）：按DI+控制码分派深度解析
        lme_rows = None
        if result['di_code'] in _LME_DI_CODES:
            try:
                lme_rows, lme_name = parse_lme_dlt645(result['di_code'], ctrl, result['data'])
                if lme_name:
                    result['di_desc'] = lme_name
            except Exception as e:
                lme_rows = [('  └ ⚠ LME解析异常', str(e), '已回退显示原始数据')]

        # 光伏协议转换单元 DL/T645-2007 扩展协议（附件1 §D.1 三张表）：按 DI 分派深度解析
        pv_rows = None
        if is_pv_di(result['di_code']):
            try:
                pv_rows, pv_name = parse_pv_di(result['di_code'], ctrl, result['data'])
                if pv_name:
                    result['di_desc'] = pv_name
            except Exception as e:
                pv_rows = [('  └ ⚠ 光伏扩展协议解析异常', str(e), '已回退显示原始数据')]

        result['fields'] = [
            ('帧起始符 1', '68H', '起始符'),
            ('从站地址', result['address'], '表地址，BCD编码，低位在前'),
            ('帧起始符 2', '68H', '起始符'),
            ('控制码', f"{ctrl:02X}H", result['control_desc']),
            ('数据长度', f"{result['data_length']} 字节", '数据域字节数'),
        ]

        if result.get('data_length_mismatch'):
            actual_data_len_display = len(data) - 12
            result['fields'].append((
                '⚠ 数据长度错误',
                f"声明{result['data_length']}B / 实际{actual_data_len_display}B",
                f"数据域长度声明值与实际帧内容不匹配（数据长度域应声明 {actual_data_len_display} 字节），"
                '解析结果可能不准确'
            ))

        # 结构与校验的醒目提示行（插在数据长度行之后、业务字段之前）
        if not struct_ok:
            result['fields'].append((
                '❌ 帧结构错误', '', struct_err,
                '按帧内假定位置继续解析；结构不符时字段归属可能不准，请核对原始报文'
            ))
        if not result['checksum_valid']:
            result['fields'].append((
                '⚠ 校验和错误', f"帧内 {result['checksum']:02X}H",
                f"应为 {result['checksum_expected']:02X}H",
                'CS = 起始符 68H 到数据域最后 1 字节的算术和 & 0xFF'
                f" = {result['checksum_expected']:02X}H；帧内值不符，"
                '以下字段仍按帧内实际内容解析'
            ))

        if err_in_data:
            # 异常应答：数据域仅 1 字节错误信息字 ERR
            err_raw = f"{result['data'][0]:02X}"
            result['fields'].append(
                ('错误信息字 ERR', err_raw, decode_err(result['data'][0:1]) or err_raw,
                 'D6=1 异常应答，错误码定义见DL/T645-2007附录C'))
        elif addr_in_data:
            # 读/写通信地址：数据域即6字节表地址（BCD低位在前，与地址域同序）
            addr_raw = ' '.join(f"{b:02X}" for b in result['data'][0:6])
            addr_desc = ('读通信地址应答，数据域为表地址' if func_code == 0x13
                         else '写通信地址请求，数据域为待写入表地址')
            result['fields'].append(
                ('通信地址（数据域）', addr_raw, result['address_in_data'],
                 f'{addr_desc}，BCD编码低位在前'))
        elif timing_in_data:
            # 广播校时：线序 ss mm hh DD MM YY（BCD）
            # 依据 DL/T645-2007 §7.6：数据域 YYMMDDhhmmss（年.月.日.时.分.秒），L=06H，
            # 帧格式表给出线序为 ss mm hh DD MM YY——**第 6 字节是年，不是星期**。
            def _bcd(b):
                return (b >> 4) * 10 + (b & 0x0F)
            td = result['data']
            time_text = (f"20{_bcd(td[5]):02d}-{_bcd(td[4]):02d}-{_bcd(td[3]):02d} "
                         f"{_bcd(td[2]):02d}:{_bcd(td[1]):02d}:{_bcd(td[0]):02d}")
            result['fields'].append(
                ('校时数据（数据域）', ' '.join(f"{b:02X}" for b in td[0:6]),
                 time_text, '广播校时，线序 ss mm hh DD MM YY，BCD编码'))
        elif func_code in (0x1A, 0x1B) and not (ctrl & 0x80):
            # 电表清零/事件清零请求：密码4B+操作者代码4B+操作对象4B，数据域无数据标识前缀
            result['fields'].append(
                ('命令数据域', result['data'].hex().upper(),
                 f"{FUNC_NAMES.get(func_code, '清零')}请求",
                 '密码PA P0P1P2 + 操作者代码C0~C3 + 操作对象标识'))
            result['fields'].extend(split_clear_command(result['data']))
        elif len(result['data']) >=4:
            result['fields'].append(('数据标识 DI', result['di_code'], result['di_desc']))
            body = result['data'][4:]
            if func_code == 0x0F:
                # 无线转发（透传）帧：数据域 = 数据标识(4B) + 透传数据(N)，L = 04H + N
                # （附件1 附录 I.3.3.1；主站请求 0FH / 从站应答 8FH 均走本分支）
                result['fields'].append((
                    '  └ 透传数据标识 DI', result['di_code'], result['di_desc'],
                    '无线转发(透传)帧：数据标识(D0~D3) + 透传数据(N0~Nm)，L = 04H + N（附录 I.3.3.1）'))
                result['fields'].append((
                    '  └ 透传数据', body.hex().upper(),
                    f'{len(body)} 字节' if body else '无（透传数据长度为 0）',
                    '无线通信模组经微功率无线信道转发的 DL/T645 报文数据'))
                if pv_rows is not None:
                    # 透传内容即扩展协议的 DI 数据块：二次展开
                    result['fields'].append((
                        '  └ ※ 透传内容按扩展协议展开', '', result['di_desc'],
                        '该 DI 命中光伏协议转换单元扩展协议表，展开其数据块'))
                    result['fields'].extend(pv_rows)
            elif lme_rows is not None:
                # LME自定义接口：逐字段深度解析
                result['fields'].extend(lme_rows)
                if body:
                    result['fields'].append(('数据内容(原始)', body.hex().upper(),
                                             '减33H后原始数据（备查）'))
            elif pv_rows is not None:
                # 光伏协议转换单元扩展协议：逐字段深度解析（契约同 LME 行列表）
                result['fields'].extend(pv_rows)
                if body:
                    result['fields'].append(('数据内容(原始)', body.hex().upper(),
                                             '减33H后原始数据（备查）'))
            elif (ctrl & 0x80) and func_code in (0x11, 0x12) and body:
                # 读数据应答：按DI的data_type解码数值
                decoded = decode_value(body, result.get('di_data_type', ''),
                                       result.get('di_unit', ''),
                                       result.get('di_desc', ''))
                fmt_desc = result.get('di_data_type', '')
                result['fields'].append((
                    '数据值', body.hex().upper(),
                    decoded if decoded else body.hex().upper(),
                    f"{result['di_desc']}；格式{fmt_desc or '未定'}"
                    + (f"；单位{result['di_unit']}" if result.get('di_unit') else '')
                    + ('' if decoded else '；按格式解码失败，显示原始hex')))
            elif not (ctrl & 0x80) and func_code == 0x14:
                # 写数据请求：DI + 密码4B + 操作者代码4B + 写入数据
                wr_rows = split_write_request(result['data'])
                if body and len(body) > 8:
                    payload = body[8:]
                    decoded = decode_value(payload, result.get('di_data_type', ''),
                                           result.get('di_unit', ''))
                    if decoded:
                        wr_rows[-1] = (wr_rows[-1][0], wr_rows[-1][1], decoded,
                                       wr_rows[-1][3] + f"；{result.get('di_data_type','')}")
                result['fields'].extend(wr_rows)
            elif not (ctrl & 0x80) and func_code == 0x18:
                # 修改密码请求：DI + 原密码组4B + 新密码组4B
                result['fields'].extend(split_change_password(result['data']))
            elif body:
                result['fields'].append(('数据内容', body.hex().upper(), '实际数据值'))
        else:
            result['fields'].append(('数据域', result['data'].hex().upper(), '解码后数据（减33H）'))

        # 校验和/结束符行：不符时同时给出「帧内值 + 应有的正确值」（合法帧文案与改动前一致）
        cs_desc = ('CS校验' if result['checksum_valid']
                   else f"应为 {result['checksum_expected']:02X}H（帧内值错误）")
        end_ok = data[-1] == 0x16
        result['fields'].extend([
            ('校验和', f"{result['checksum']:02X}H", cs_desc),
            ('帧结束符', f"{data[-1]:02X}H", '结束符' if end_ok else '结束符错误（应为 16H）')
        ])

        # ── valid 语义保持不变（R5）：结构 OK + 校验 OK + 长度相符 才为 True
        #    既有消费方（dlt645_sim/engine.py、dlt645_meter_sim_widget.py 等）按
        #    parsed['valid'] 判定帧是否可信，不得为了「容错解析」把 valid 放松。
        result['valid'] = bool(struct_ok and result['checksum_valid']
                               and not result['data_length_mismatch'])
        if not struct_ok:
            result['error'] = struct_err
        elif not result['checksum_valid']:
            result['error'] = (f"校验和错误，期望 0x{result['checksum_expected']:02X}，"
                               f"实际 0x{result['checksum']:02X}")

        return result

    def verify(self, frame_bytes: bytes):
        """验证帧的协议一致性，返回 ValidationResult"""
        from validator.dlt645_validator import DLT645Validator
        validator = DLT645Validator()
        return validator.verify(frame_bytes)
