"""DL/T 698.45 APDU 解析器"""

from typing import Dict, Any, Tuple, Optional
from dl_t698_45_axdr import AXDRCoder, get_tag_name
from dl_t698_45_oi_lookup import OILookup


class DLT69845APDUParser:
    """698.45 APDU 解析器"""

    # APDU 服务类型映射（首字节 -> 类型）
    APDU_TYPE_MAP = {
        0x01: ("LINK-Request", "预连接请求"),
        0x81: ("LINK-Response", "预连接响应"),
        0x02: ("CONNECT-Request", "建立应用连接请求"),
        0x82: ("CONNECT-Response", "建立应用连接响应"),
        0x03: ("RELEASE-Request", "断开应用连接请求"),
        0x83: ("RELEASE-Response", "断开应用连接响应"),
        0x84: ("RELEASE-Notification", "断开应用连接通知"),
        0x05: ("GET-Request", "读取请求"),
        0x85: ("GET-Response", "读取响应"),
        0x06: ("SET-Request", "设置请求"),
        0x86: ("SET-Response", "设置响应"),
        0x07: ("ACTION-Request", "操作请求"),
        0x87: ("ACTION-Response", "操作响应"),
        0x08: ("REPORT-Response", "上报应答"),
        0x88: ("REPORT-Notification", "上报通知"),
        0x09: ("PROXY-Request", "代理请求"),
        0x89: ("PROXY-Response", "代理响应"),
        0x45: ("COMPACT-GET-Request", "紧凑读取请求"),
        0xC5: ("COMPACT-GET-Response", "紧凑读取响应"),
        0x46: ("COMPACT-SET-Request", "紧凑设置请求"),
        0xC6: ("COMPACT-SET-Response", "紧凑设置响应"),
        0x49: ("COMPACT-PROXY-Request", "紧凑代理请求"),
        0xC9: ("COMPACT-PROXY-Response", "紧凑代理响应"),
        0x10: ("SECURITY-Request", "安全请求"),
        0x90: ("SECURITY-Response", "安全响应"),
        0x6E: ("ERROR-Response", "异常响应(Client)"),
        0xEE: ("ERROR-Response", "异常响应(Server)"),
    }

    # DAR 错误码映射
    DAR_MAP = {
        0: "成功",
        1: "硬件失效",
        2: "暂时失效",
        3: "拒绝读写",
        4: "对象未定义",
        5: "对象接口类不符合",
        6: "对象不存在",
        7: "类型不匹配",
        8: "越界",
        9: "数据块不可用",
        10: "分帧传输已取消",
        11: "不处于连接状态",
        12: "安全校验失败",
        13: "密码错",
        14: "通信地址错",
        15: "帧长度错",
        16: "帧格式错",
        17: "功能码错",
        18: "电表挂起",
        19: "时段设置错误",
        20: "剩余电量不足",
        21: "购电次数不一致",
        22: "户号错误",
        23: "充值次数错误",
        24: "密钥过期",
        25: "ESAM验证失败",
        26: "安全模块故障",
        27: "时间标签无效",
        28: "请求超时",
        29: "协商失败",
        30: "电能表挂起",
        31: "费率数超限",
    }

    def __init__(self, axdr_coder=None, oi_lookup=None):
        self.axdr = axdr_coder or AXDRCoder()
        self.oi_lookup = oi_lookup or OILookup()

    def parse(self, apdu_bytes: bytes) -> dict:
        """解析 APDU 字节"""
        if not apdu_bytes:
            return {"APDU类型": "空", "解析状态": "失败", "错误信息": "APDU为空"}

        first_byte = apdu_bytes[0]
        type_info = self.APDU_TYPE_MAP.get(first_byte, (f"未知(0x{first_byte:02X})", ""))
        type_name, type_desc = type_info

        result = {
            "APDU类型": type_name,
            "APDU说明": type_desc,
            "服务码": f"0x{first_byte:02X}",
            "原始数据": apdu_bytes.hex().upper(),
            "解析状态": "成功",
        }

        try:
            if first_byte == 0x01:
                result.update(self._parse_link_request(apdu_bytes))
            elif first_byte == 0x81:
                result.update(self._parse_link_response(apdu_bytes))
            elif first_byte == 0x05:
                result.update(self._parse_get_request(apdu_bytes))
            elif first_byte == 0x85:
                result.update(self._parse_get_response(apdu_bytes))
            elif first_byte == 0x06:
                result.update(self._parse_set_request(apdu_bytes))
            elif first_byte == 0x86:
                result.update(self._parse_set_response(apdu_bytes))
            elif first_byte == 0x07:
                result.update(self._parse_action_request(apdu_bytes))
            elif first_byte == 0x87:
                result.update(self._parse_action_response(apdu_bytes))
            elif first_byte == 0x08:
                result.update(self._parse_report_response(apdu_bytes))
            elif first_byte == 0x88:
                result.update(self._parse_report_notification(apdu_bytes))
            elif first_byte in (0x10, 0x90):
                result.update(self._parse_security(apdu_bytes, first_byte == 0x10))
            elif first_byte in (0x6E, 0xEE):
                result.update(self._parse_error_response(apdu_bytes))
            else:
                result["解析状态"] = "部分"
                result["说明"] = "该服务类型解析器尚未实现"
        except Exception as e:
            result["解析状态"] = "失败"
            result["错误信息"] = str(e)

        return result

    def _enrich_oad(self, oad_result: dict) -> dict:
        """为 OAD 解析结果添加语义说明"""
        pv = oad_result.get("解析值", {})
        oi_str = pv.get("OI", "")
        if oi_str.startswith("0x"):
            oi = int(oi_str, 16)
        else:
            oi = 0
        attr = pv.get("属性编号", 0)
        index = pv.get("元素索引", 0)
        desc = self.oi_lookup.get_oad_description(oi, attr, index)
        oad_result["语义说明"] = desc
        return oad_result

    def _enrich_omd(self, omd_result: dict) -> dict:
        """为 OMD 解析结果添加语义说明"""
        pv = omd_result.get("解析值", {})
        oi_str = pv.get("OI", "")
        if oi_str.startswith("0x"):
            oi = int(oi_str, 16)
        else:
            oi = 0
        method = pv.get("方法标识", 0)
        desc = self.oi_lookup.get_omd_description(oi, method)
        omd_result["语义说明"] = desc
        return omd_result

    def _enrich_dar(self, dar_result: dict) -> dict:
        """为 DAR 结果添加语义说明"""
        val = dar_result.get("解析值", 0)
        if isinstance(val, int):
            dar_result["DAR说明"] = self.DAR_MAP.get(val, f"未知DAR({val})")
        return dar_result

    def _parse_piid(self, byte: int, is_acd: bool = False) -> dict:
        """解析 PIID / PIID-ACD 原始字节"""
        acd = (byte >> 7) & 0x01
        seq = byte & 0x3F
        name = "PIID-ACD" if is_acd else "PIID"
        return {
            "类型": name,
            "原始值": f"0x{byte:02X}",
            "解析值": byte,
            "ACD": acd,
            "服务序号": seq,
            "说明": f"ACD={acd}, 序号={seq}",
        }

    def _parse_oad_raw(self, data: bytes, offset: int) -> dict:
        """解析原始字节 OAD (4字节: OI+attr+index)"""
        if offset + 4 > len(data):
            raise ValueError("OAD 数据不足")
        val = data[offset:offset + 4]
        oi = int.from_bytes(val[0:2], 'big')
        attr = val[2]
        attr_no = attr & 0x1F
        attr_feat = (attr >> 5) & 0x07
        index = val[3]
        index_desc = "全部" if index == 0 else str(index)
        result = {"类型": "OAD", "原始值": val.hex().upper(),
                "解析值": {"OI": f"0x{oi:04X}", "属性编号": attr_no, "属性特征": attr_feat, "元素索引": index},
                "说明": f"OI=0x{oi:04X}, 属性={attr_no}, 特征={attr_feat}, 索引={index_desc}"}
        return self._enrich_oad(result)

    def _parse_omd_raw(self, data: bytes, offset: int) -> dict:
        """解析原始字节 OMD (4字节: OI+method+mode)"""
        if offset + 4 > len(data):
            raise ValueError("OMD 数据不足")
        val = data[offset:offset + 4]
        oi = int.from_bytes(val[0:2], 'big')
        method = val[2]
        mode = val[3]
        result = {"类型": "OMD", "原始值": val.hex().upper(),
                "解析值": {"OI": f"0x{oi:04X}", "方法标识": method, "操作模式": mode},
                "说明": f"OI=0x{oi:04X}, 方法={method}, 模式={mode}"}
        return self._enrich_omd(result)

    # --- LINK 服务 ---

    def _parse_link_request(self, data: bytes) -> dict:
        """LINK-Request: 0x01 PIID 请求类型 心跳周期 时间标签"""
        offset = 1
        result = {}
        # PIID (unsigned)
        piid_byte = data[offset]
        offset += 1
        result["PIID"] = self._parse_piid(piid_byte)

        # 请求类型 (enum)
        req_type, consumed = self.axdr.decode(data, offset)
        offset += consumed
        req_type_map = {0: "登录", 1: "心跳", 2: "退出登录"}
        req_type["说明"] = req_type_map.get(req_type["解析值"], f"未知({req_type['解析值']})")
        result["请求类型"] = req_type

        # 心跳周期 (long-unsigned)
        heartbeat, consumed = self.axdr.decode(data, offset)
        offset += consumed
        result["心跳周期"] = heartbeat

        # 时间标签 (date_time_s, optional)
        if offset < len(data):
            time_tag, consumed = self.axdr.decode(data, offset)
            offset += consumed
            result["时间标签"] = time_tag

        return result

    def _parse_link_response(self, data: bytes) -> dict:
        """LINK-Response: 0x81 PIID-ACD 结果 心跳周期 时间标签"""
        offset = 1
        result = {}
        # PIID-ACD (unsigned)
        piid_byte = data[offset]
        offset += 1
        result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)

        # 结果 (enum)
        res, consumed = self.axdr.decode(data, offset)
        offset += consumed
        res_map = {0: "成功", 1: "地址不匹配", 2: "地址不存在"}
        res["说明"] = res_map.get(res["解析值"], f"未知({res['解析值']})")
        result["结果"] = res

        # 心跳周期 (long-unsigned)
        heartbeat, consumed = self.axdr.decode(data, offset)
        offset += consumed
        result["心跳周期"] = heartbeat

        # 时间标签 (optional)
        if offset < len(data):
            time_tag, consumed = self.axdr.decode(data, offset)
            offset += consumed
            result["时间标签"] = time_tag

        return result

    # --- GET 服务 ---

    def _parse_get_request(self, data: bytes) -> dict:
        """GET-Request: choice { Normal, NormalList, Next, MD5, Signature }"""
        offset = 1
        result = {}

        if offset >= len(data):
            raise ValueError("GET-Request 数据不足")
        choice_tag = data[offset]
        result["子类型码"] = f"0x{choice_tag:02X}"
        offset += 1

        if choice_tag == 0x01:
            result["子类型"] = "GetRequestNormal"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # OAD
            result["OAD"] = self._parse_oad_raw(data, offset)
            offset += 4
            # 时间标签 (可选)
            if offset < len(data):
                time_tag = data[offset]
                offset += 1
                if time_tag == 0:
                    result["时间标签"] = {"类型": "TimeTag", "原始值": "0x00", "解析值": 0, "说明": "无时间标签"}
                else:
                    result["时间标签"] = {"类型": "TimeTag", "原始值": f"0x{time_tag:02X}", "解析值": time_tag, "说明": "有时间标签"}

        elif choice_tag == 0x02:
            result["子类型"] = "GetRequestNormalList"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # SEQUENCE OF OAD (count + items)
            count = data[offset]
            offset += 1
            oads = []
            for _ in range(count):
                oads.append(self._parse_oad_raw(data, offset))
                offset += 4
            result["OAD列表"] = oads

        elif choice_tag == 0x03:
            result["子类型"] = "GetRequestNext"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # long-unsigned 块序号
            block, consumed = self.axdr.decode(data, offset)
            offset += consumed
            result["块序号"] = block

        elif choice_tag == 0x04:
            result["子类型"] = "GetRequestMD5"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # OAD
            result["OAD"] = self._parse_oad_raw(data, offset)
            offset += 4

        elif choice_tag == 0x05:
            result["子类型"] = "GetRequestSignature"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # OAD
            result["OAD"] = self._parse_oad_raw(data, offset)
            offset += 4

        return result

    def _parse_get_response(self, data: bytes) -> dict:
        """GET-Response: choice { Normal, NormalList, Next, MD5, Signature }"""
        offset = 1
        result = {}

        if offset >= len(data):
            raise ValueError("GET-Response 数据不足")
        choice_tag = data[offset]
        result["子类型码"] = f"0x{choice_tag:02X}"
        offset += 1

        if choice_tag == 0x01:
            result["子类型"] = "GetResponseNormal"
            # PIID-ACD
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            # OAD
            result["OAD"] = self._parse_oad_raw(data, offset)
            offset += 4
            # GetResult: Data or DAR
            if offset < len(data):
                res_tag = data[offset]
                if res_tag == 0x00:
                    result["数据访问结果"] = {"DAR": 0, "说明": "成功"}
                    offset += 1
                    # Data
                    d, consumed = self.axdr.decode(data, offset)
                    offset += consumed
                    result["数据"] = d
                else:
                    # DAR 错误码
                    dar, consumed = self.axdr.decode(data, offset)
                    offset += consumed
                    result["数据访问结果"] = self._enrich_dar(dar)

        elif choice_tag == 0x02:
            result["子类型"] = "GetResponseNormalList"
            # PIID-ACD
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            count = data[offset]
            offset += 1
            items = []
            for _ in range(count):
                item = {"OAD": self._parse_oad_raw(data, offset)}
                offset += 4
                if offset < len(data):
                    res_tag = data[offset]
                    if res_tag == 0x00:
                        item["数据访问结果"] = {"DAR": 0, "说明": "成功"}
                        offset += 1
                        d, consumed = self.axdr.decode(data, offset)
                        offset += consumed
                        item["数据"] = d
                    else:
                        dar, consumed = self.axdr.decode(data, offset)
                        offset += consumed
                        item["数据访问结果"] = self._enrich_dar(dar)
                items.append(item)
            result["列表"] = items

        elif choice_tag == 0x03:
            result["子类型"] = "GetResponseNext"
            # PIID-ACD
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            # 块序号
            block, consumed = self.axdr.decode(data, offset)
            offset += consumed
            result["块序号"] = block
            # Data
            if offset < len(data):
                d, consumed = self.axdr.decode(data, offset)
                offset += consumed
                result["数据"] = d

        return result

    # --- SET 服务 ---

    def _parse_set_request(self, data: bytes) -> dict:
        """SET-Request: choice { Normal, MD5, Signature }"""
        offset = 1
        result = {}
        if offset >= len(data):
            raise ValueError("SET-Request 数据不足")
        choice_tag = data[offset]
        result["子类型码"] = f"0x{choice_tag:02X}"
        offset += 1

        if choice_tag == 0x01:
            result["子类型"] = "SetRequestNormal"
            # PIID (unsigned)
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # OAD
            result["OAD"] = self._parse_oad_raw(data, offset)
            offset += 4
            # Data
            if offset < len(data):
                d, consumed = self.axdr.decode(data, offset)
                offset += consumed
                result["数据"] = d

        return result

    def _parse_set_response(self, data: bytes) -> dict:
        """SET-Response: choice { Normal, MD5, Signature }"""
        offset = 1
        result = {}
        if offset >= len(data):
            raise ValueError("SET-Response 数据不足")
        choice_tag = data[offset]
        result["子类型码"] = f"0x{choice_tag:02X}"
        offset += 1

        if choice_tag == 0x01:
            result["子类型"] = "SetResponseNormal"
            # PIID-ACD
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            # OAD
            result["OAD"] = self._parse_oad_raw(data, offset)
            offset += 4
            # DAR
            if offset < len(data):
                dar, consumed = self.axdr.decode(data, offset)
                offset += consumed
                result["结果"] = self._enrich_dar(dar)

        return result

    # --- ACTION 服务 ---

    def _parse_action_request(self, data: bytes) -> dict:
        """ACTION-Request: choice { Normal, MD5, Signature }"""
        offset = 1
        result = {}
        if offset >= len(data):
            raise ValueError("ACTION-Request 数据不足")
        choice_tag = data[offset]
        result["子类型码"] = f"0x{choice_tag:02X}"
        offset += 1

        if choice_tag == 0x01:
            result["子类型"] = "ActionRequestNormal"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # OMD
            result["OMD"] = self._parse_omd_raw(data, offset)
            offset += 4
            # 参数 (optional)
            if offset < len(data):
                param, consumed = self.axdr.decode(data, offset)
                offset += consumed
                result["参数"] = param

        return result

    def _parse_action_response(self, data: bytes) -> dict:
        """ACTION-Response: choice { Normal, MD5, Signature }"""
        offset = 1
        result = {}
        if offset >= len(data):
            raise ValueError("ACTION-Response 数据不足")
        choice_tag = data[offset]
        result["子类型码"] = f"0x{choice_tag:02X}"
        offset += 1

        if choice_tag == 0x01:
            result["子类型"] = "ActionResponseNormal"
            # PIID-ACD
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            # OMD
            result["OMD"] = self._parse_omd_raw(data, offset)
            offset += 4
            # DAR
            if offset < len(data):
                dar, consumed = self.axdr.decode(data, offset)
                offset += consumed
                result["结果"] = self._enrich_dar(dar)
            # 响应数据 (optional)
            if offset < len(data):
                resp, consumed = self.axdr.decode(data, offset)
                offset += consumed
                result["响应数据"] = resp

        return result

    # --- REPORT 服务 ---

    def _parse_report_response(self, data: bytes) -> dict:
        """REPORT-Response: choice { List, RecordList, TransData, ClientService, SimplifyRecord }"""
        offset = 1
        result = {}
        if offset >= len(data):
            raise ValueError("REPORT-Response 数据不足")
        choice_tag = data[offset]
        result["子类型码"] = f"0x{choice_tag:02X}"
        offset += 1

        # 尝试A-XDR解码PIID, 失败则回退到原始字节
        try:
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
        except Exception:
            if offset < len(data):
                result["PIID-ACD"] = {"类型": "unsigned", "原始值": f"0x{data[offset]:02X}",
                                       "解析值": data[offset], "说明": "PIID-ACD(原始字节)"}
                offset += 1

        if choice_tag == 0x01:
            result["子类型"] = "ReportResponseList"
            # SEQUENCE OF OAD
            oads = []
            while offset < len(data):
                try:
                    oads.append(self._parse_oad_raw(data, offset))
                    offset += 4
                except Exception:
                    break
            result["OAD列表"] = oads

        elif choice_tag == 0x02:
            result["子类型"] = "ReportResponseRecordList"
            oads = []
            while offset < len(data):
                try:
                    oads.append(self._parse_oad_raw(data, offset))
                    offset += 4
                except Exception:
                    break
            result["OAD列表"] = oads

        elif choice_tag == 0x03:
            result["子类型"] = "ReportResponseTransData"

        elif choice_tag == 0x04:
            result["子类型"] = "ReportResponseClientService"
            if offset < len(data):
                try:
                    svc_data, consumed = self.axdr.decode(data, offset)
                    offset += consumed
                    result["服务数据"] = svc_data
                except Exception as e:
                    result["服务数据解码错误"] = str(e)

        elif choice_tag == 0x06:
            result["子类型"] = "ReportResponseSimplifyRecord"
            if offset < len(data):
                try:
                    d, consumed = self.axdr.decode(data, offset)
                    offset += consumed
                    result["数据"] = d
                except Exception:
                    pass

        else:
            result["子类型"] = f"未知选择({choice_tag})"
            # 剩余数据作为原始字节保留
            if offset < len(data):
                result["剩余数据"] = data[offset:].hex().upper()

        return result

    def _parse_report_notification(self, data: bytes) -> dict:
        """REPORT-Notification: choice { Normal, Simplify, List }"""
        offset = 1
        result = {}
        if offset >= len(data):
            raise ValueError("REPORT-Notification 数据不足")
        choice_tag = data[offset]
        result["子类型码"] = f"0x{choice_tag:02X}"
        offset += 1

        if choice_tag == 0x01:
            result["子类型"] = "ReportNotificationNormal"
            # PIID-ACD
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            # Data (简化处理)
            if offset < len(data):
                d, consumed = self.axdr.decode(data, offset)
                offset += consumed
                result["数据"] = d

        elif choice_tag == 0x02:
            result["子类型"] = "ReportNotificationSimplify"
            items = []
            while offset < len(data):
                d, consumed = self.axdr.decode(data, offset)
                items.append(d)
                offset += consumed
            result["数据列表"] = items

        return result

    # --- SECURITY 服务 ---

    def _parse_security(self, data: bytes, is_request: bool) -> dict:
        """SECURITY-Request/Response

        结构(按原始字节,非A-XDR):
        - SecurityDataType (1字节): 0=明文,1=密文+MAC,2=密文,3=签名
        - 明文数据长度 (1字节)
        - 明文数据 (n字节)
        - SecurityRequestVerifyType (1字节): 0=验证码,1=随机数,2=随机数+数据MAC,3=安全标识
        - RN_len (1字节)
        - RN (n字节)
        """
        offset = 1
        result = {"解析状态": "成功"}

        if offset >= len(data):
            result["解析状态"] = "部分"
            result["说明"] = "安全类型数据不足"
            return result

        sec_type = data[offset]
        offset += 1
        sec_type_map = {
            0x00: "明文",
            0x01: "密文+MAC",
            0x02: "密文",
            0x03: "签名",
        }
        result["安全类型"] = {
            "原始值": f"0x{sec_type:02X}",
            "解析值": sec_type,
            "说明": sec_type_map.get(sec_type, f"未知({sec_type})")
        }

        # 明文数据
        if sec_type == 0x00 and offset < len(data):
            plain_len = data[offset]
            offset += 1
            result["明文数据长度"] = plain_len
            if plain_len > 0 and offset + plain_len <= len(data):
                plain_bytes = data[offset:offset + plain_len]
                plain_data = {
                    "原始值": plain_bytes.hex().upper(),
                    "长度": plain_len,
                    "说明": f"长度={plain_len}"
                }
                # 尝试解析明文数据中的嵌套APDU
                try:
                    nested = self.parse(plain_bytes)
                    if nested.get("解析状态") == "成功":
                        plain_data["嵌套APDU"] = nested
                except Exception:
                    pass
                result["明文数据"] = plain_data
                offset += plain_len

        # 密文数据(密文+MAC类型)
        if sec_type == 0x01 and offset < len(data):
            cipher_len = data[offset]
            offset += 1
            result["密文数据长度"] = cipher_len
            if cipher_len > 0 and offset + cipher_len <= len(data):
                result["密文数据"] = data[offset:offset + cipher_len].hex().upper()
                offset += cipher_len
            if offset < len(data):
                mac_len = data[offset]
                offset += 1
                result["MAC长度"] = mac_len
                if mac_len > 0 and offset + mac_len <= len(data):
                    result["MAC数据"] = data[offset:offset + mac_len].hex().upper()
                    offset += mac_len

        # 签名数据
        if sec_type == 0x03 and offset < len(data):
            sig_len = data[offset]
            offset += 1
            result["签名数据长度"] = sig_len
            if sig_len > 0 and offset + sig_len <= len(data):
                result["签名数据"] = data[offset:offset + sig_len].hex().upper()
                offset += sig_len

        # SecurityRequestVerifyType / SecurityResponseVerifyType
        if offset < len(data):
            verify_type = data[offset]
            offset += 1
            verify_map = {
                0x00: "验证码",
                0x01: "随机数",
                0x02: "随机数+数据MAC",
                0x03: "安全标识",
            }
            key = "SecurityRequestVerifyType" if is_request else "SecurityResponseVerifyType"
            result[key] = {
                "原始值": f"0x{verify_type:02X}",
                "解析值": verify_type,
                "说明": verify_map.get(verify_type, f"未知({verify_type})")
            }

        # RN_len + RN
        if offset < len(data):
            rn_len = data[offset]
            offset += 1
            result["RN长度"] = rn_len
            if rn_len > 0 and offset + rn_len <= len(data):
                rn_bytes = data[offset:offset + rn_len]
                result["RN"] = {
                    "原始值": rn_bytes.hex().upper(),
                    "长度": rn_len,
                    "说明": f"长度={rn_len}"
                }

        return result

    # --- ERROR 服务 ---

    def _parse_error_response(self, data: bytes) -> dict:
        """ERROR-Response"""
        offset = 1
        result = {}
        # PIID-ACD
        piid_byte = data[offset]
        offset += 1
        result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
        # DAR
        if offset < len(data):
            dar, consumed = self.axdr.decode(data, offset)
            offset += consumed
            result["数据访问结果"] = self._enrich_dar(dar)
        return result
