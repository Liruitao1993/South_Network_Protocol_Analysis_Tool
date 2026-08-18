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
        # EB 数据标识（OI 高字节 0xEB）：按 OAD 4 字节原样查福建扩展协议名称
        eb_name = self._lookup_eb_di(oad_result)
        if eb_name:
            desc = f"{eb_name} ({desc})"
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
        # EB 数据标识（OI 高字节 0xEB）：按 OMD 4 字节原样查福建扩展协议名称
        eb_name = self._lookup_eb_di(omd_result)
        if eb_name:
            desc = f"{eb_name} ({desc})"
        omd_result["语义说明"] = desc
        return omd_result

    def _lookup_eb_di(self, oad_omd: dict) -> str:
        """按 OAD/OMD 4 字节原样查 EB 数据标识名称（福建本地通信模块扩展协议）

        OAD/OMD 原始值形如 'EB030110'，恰为 EB 数据标识 DI3DI2DI1DI0。
        仅当 OI 高字节为 0xEB 时按 EB 数据标识查询，否则返回空串。
        """
        try:
            pv = oad_omd.get("解析值", {})
            oi_str = pv.get("OI", "")
            if not oi_str.startswith("0x"):
                return ""
            oi = int(oi_str, 16)
            if (oi >> 8) != 0xEB:
                return ""
            raw = oad_omd.get("原始值", "")
            if len(raw) != 8:
                return ""
            from gdw_eb_di_lookup import get_eb_di_lookup
            info = get_eb_di_lookup().get(raw)
            if isinstance(info, dict):
                return info.get("名称", "")
        except Exception:
            pass
        return ""

    def _decode_eb_data_content(self, oad: dict, data_dict: Any) -> Optional[Dict[str, Any]]:
        """按 EB 数据标识字段定义解码数据内容（福建扩展协议 698 承载）

        Args:
            oad: OAD/OMD 解析结果（含 原始值 4 字节 hex）
            data_dict: A-XDR 解码结果（octet-string 等）

        Returns:
            {字段名: 解码值} 或 None（非 EB / 无字段定义 / 解码失败）
        """
        try:
            if not isinstance(oad, dict) or data_dict is None:
                return None
            raw = oad.get("原始值", "")
            if len(raw) != 8 or not raw.isalnum():
                return None
            di = raw.upper()
            if not di.startswith("EB"):
                return None
            from gdw_eb_di_fields import EB_DI_FIELDS
            schema = EB_DI_FIELDS.get(di)
            if not schema:
                # 无字段定义：尝试 date_time_s（1C 开头 7 字节 BIN 时间）或保留原始 hex
                dv = data_dict.get("解析值", "")
                if isinstance(dv, str):
                    try:
                        raw_bytes = bytes.fromhex(dv)
                    except (ValueError, TypeError):
                        raw_bytes = None
                    if raw_bytes and len(raw_bytes) >= 8 and raw_bytes[0] == 0x1C:
                        try:
                            dt, _ = self.axdr.decode(raw_bytes)
                            return {"数据时间": {"值": dt.get("解析值", dv),
                                                "类型": "date_time_s", "长度": 8}}
                        except Exception:
                            pass
                    return {"原始数据": {"值": dv, "类型": "hex",
                                         "长度": len(raw_bytes) if raw_bytes else 0}}
                return None
            fields = schema.get("fields", [])
            # 取数据字节：A-XDR octet-string 的 解析值 为 hex 字符串
            data_bytes = None
            dv = data_dict.get("解析值")
            if isinstance(dv, str):
                try:
                    data_bytes = bytes.fromhex(dv)
                except (ValueError, TypeError):
                    data_bytes = None
            elif isinstance(dv, list):
                # array/structure 解析值：逐项取 解析值 拼接
                data_bytes = b""
                for item in dv:
                    v = item.get("解析值") if isinstance(item, dict) else item
                    if isinstance(v, int):
                        data_bytes += v.to_bytes(max(1, (v.bit_length() + 7) // 8), "little")
                    elif isinstance(v, str):
                        try:
                            data_bytes += bytes.fromhex(v)
                        except (ValueError, TypeError):
                            pass
            if data_bytes is None:
                return None
            return self._decode_eb_fields(fields, data_bytes)
        except Exception:
            return None

    def _decode_eb_fields(self, fields: list, data: bytes) -> Dict[str, Any]:
        """按字段定义顺序解码数据字节

        字段类型: enum/uint8/16/24/32/bcd/bcd_time/ascii/hex/bs8/list
        返回: {字段名: {值, 类型, 长度}}（长度=字节数）
        """
        result: Dict[str, Any] = {}
        offset = 0
        for f in fields:
            ftype = f.get("type", "hex")
            name = f.get("name", "字段")
            try:
                if ftype == "enum":
                    v = data[offset]
                    offset += 1
                    emap = f.get("enum_map", {})
                    result[name] = {"值": emap.get(v, f"{v}(未定义)"), "类型": "enum", "长度": 1}
                elif ftype.startswith("uint"):
                    nbytes = int(ftype[4:]) // 8
                    # 698 承载按「645 减33逆序」规则：多字节 uint 高位在前（大端）
                    v = int.from_bytes(data[offset:offset + nbytes], "big")
                    offset += nbytes
                    result[name] = {"值": v, "类型": ftype, "长度": nbytes}
                elif ftype == "bcd":
                    n = f.get("length", 1)
                    raw = data[offset:offset + n].hex().upper()
                    offset += n
                    result[name] = {"值": raw, "类型": "bcd", "长度": n}
                elif ftype == "bcd_time":
                    n = f.get("length", 6)
                    raw = data[offset:offset + n]
                    offset += n
                    if len(raw) >= 6:
                        v = (f"{raw[0]:02X}{raw[1]:02X}{raw[2]:02X} "
                             f"{raw[3]:02X}{raw[4]:02X}{raw[5]:02X}")
                    else:
                        v = raw.hex().upper()
                    result[name] = {"值": v, "类型": "bcd_time", "长度": n}
                elif ftype == "ascii":
                    n = f.get("length", 1)
                    raw = data[offset:offset + n]
                    offset += n
                    result[name] = {"值": raw.decode("ascii", errors="replace").rstrip(),
                                    "类型": "ascii", "长度": n}
                elif ftype == "hex":
                    n = f.get("length", 1)
                    result[name] = {"值": data[offset:offset + n].hex().upper(),
                                    "类型": "hex", "长度": n}
                    offset += n
                elif ftype == "bs8":
                    v = data[offset]
                    offset += 1
                    bits = f.get("bits", {})
                    parts = []
                    for bname, bit in bits.items():
                        bitval = (v >> bit) & 0x01
                        benum = f.get("bit_enums", {}).get(bname, {})
                        if isinstance(benum, dict) and bitval in benum:
                            parts.append(f"{bname}:{benum[bitval]}")
                        else:
                            parts.append(f"{bname}:{bitval}")
                    result[name] = {"值": " | ".join(parts) if parts else hex(v),
                                    "类型": "bs8", "长度": 1}
                elif ftype == "list":
                    # 每项固定长度（item_fields 均为定长）→ 按 item 长度切分
                    item_fields = f.get("item_fields", [])
                    item_len = self._eb_item_len(item_fields)
                    if item_len <= 0:
                        result[name] = {"值": data[offset:].hex().upper(),
                                        "类型": "list", "长度": len(data) - offset}
                        offset = len(data)
                        continue
                    items = []
                    while offset + item_len <= len(data):
                        items.append(self._decode_eb_fields(item_fields, data[offset:offset + item_len]))
                        offset += item_len
                    result[name] = {"值": items, "类型": "list",
                                    "长度": len(items) * item_len}
                else:
                    result[name] = {"值": f"(未知类型 {ftype})", "类型": ftype, "长度": 0}
                    break
            except (IndexError, ValueError):
                result[name + " (解析截断)"] = {"值": data[offset:].hex().upper(),
                                                "类型": "hex", "长度": len(data) - offset}
                break
        return result

    def _eb_item_len(self, item_fields: list) -> int:
        """计算 list 单条 item 的固定长度（字节）"""
        total = 0
        for f in item_fields:
            ftype = f.get("type", "hex")
            if ftype.startswith("uint"):
                total += int(ftype[4:]) // 8
            elif ftype in ("bcd", "hex", "ascii"):
                total += f.get("length", 1)
            elif ftype == "bcd_time":
                total += f.get("length", 6)
            elif ftype in ("enum", "bs8"):
                total += 1
            else:
                return 0  # 未知/变长 → 无法定长切分
        return total

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

    def _decode_oad_business(self, oad: Dict[str, Any], data: Any) -> Optional[Dict[str, str]]:
        """按 OAD 对数据内容做业务解码（不破坏原始 A-XDR 结果）

        在结果中新增「数据业务」键：电能量→kWh 换算、分相电压/电流→A相/B相/C相、
        最大需量→值@时间、数据变量→单值换算。无匹配模板时返回 None。
        """
        try:
            if not isinstance(oad, dict) or data is None:
                return None
            pv = oad.get("解析值")
            if not isinstance(pv, dict):
                return None
            oi_str = pv.get("OI", "0x0000")
            attr_no = pv.get("属性编号", 0)
            oi = int(oi_str, 16) if isinstance(oi_str, str) else int(oi_str)
            from dl_t698_45_data_decode import decode_oad_data
            return decode_oad_data(oi, attr_no, data)
        except Exception:
            return None

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
                    # 业务解码
                    biz = self._decode_oad_business(result["OAD"], d)
                    if biz:
                        result["数据业务"] = biz
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
                        # 业务解码
                        biz = self._decode_oad_business(item["OAD"], d)
                        if biz:
                            item["数据业务"] = biz
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
                # 业务解码（下行设置参数同样给出业务值）
                biz = self._decode_oad_business(result["OAD"], d)
                if biz:
                    result["数据业务"] = biz
                else:
                    # EB 数据标识：按福建扩展协议字段定义解码
                    eb_biz = self._decode_eb_data_content(result["OAD"], d)
                    if eb_biz:
                        result["数据业务"] = eb_biz

        elif choice_tag == 0x02:
            result["子类型"] = "SetRequestNormalList"
            # PIID (unsigned)
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # count + SEQUENCE OF {OAD, Data}
            count = data[offset]
            offset += 1
            items = []
            for _ in range(count):
                item = {"OAD": self._parse_oad_raw(data, offset)}
                offset += 4
                if offset < len(data):
                    d, consumed = self.axdr.decode(data, offset)
                    offset += consumed
                    item["数据"] = d
                    biz = self._decode_oad_business(item["OAD"], d)
                    if biz:
                        item["数据业务"] = biz
                    else:
                        eb_biz = self._decode_eb_data_content(item["OAD"], d)
                        if eb_biz:
                            item["数据业务"] = eb_biz
                items.append(item)
            result["列表"] = items

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

        elif choice_tag == 0x02:
            result["子类型"] = "SetResponseNormalList"
            # PIID-ACD
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            # count + SEQUENCE OF {OAD, 结果}
            count = data[offset]
            offset += 1
            items = []
            for _ in range(count):
                item = {"OAD": self._parse_oad_raw(data, offset)}
                offset += 4
                if offset < len(data):
                    # DAR: 原始 1 字节（00=成功 / FF=否认 / 其他错误码）
                    dar_val = data[offset]
                    offset += 1
                    item["结果"] = self._enrich_dar({"类型": "unsigned", "原始值": f"0x{dar_val:02X}",
                                                     "解析值": dar_val, "说明": ""})
                items.append(item)
            result["列表"] = items

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

        elif choice_tag == 0x02:
            result["子类型"] = "ActionRequestNormalList"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # count + SEQUENCE OF {OMD, Data}
            count = data[offset]
            offset += 1
            items = []
            for _ in range(count):
                item = {"OMD": self._parse_omd_raw(data, offset)}
                offset += 4
                if offset < len(data):
                    d, consumed = self.axdr.decode(data, offset)
                    offset += consumed
                    item["参数"] = d
                    # EB 数据标识：按福建扩展协议字段定义解码
                    eb_biz = self._decode_eb_data_content(item["OMD"], d)
                    if eb_biz:
                        item["数据业务"] = eb_biz
                items.append(item)
            result["列表"] = items

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
                # EB 数据标识：按福建扩展协议字段定义解码
                eb_biz = self._decode_eb_data_content(result["OMD"], resp)
                if eb_biz:
                    result["数据业务"] = eb_biz

        elif choice_tag == 0x02:
            result["子类型"] = "ActionResponseNormalList"
            # PIID-ACD
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            # count + SEQUENCE OF {OMD, DAR, [响应数据]}
            count = data[offset]
            offset += 1
            items = []
            for _ in range(count):
                item = {"OMD": self._parse_omd_raw(data, offset)}
                offset += 4
                if offset < len(data):
                    # DAR: 原始 1 字节（00=成功 / FF=否认 / 其他错误码）
                    dar_val = data[offset]
                    offset += 1
                    item["结果"] = self._enrich_dar({"类型": "unsigned", "原始值": f"0x{dar_val:02X}",
                                                     "解析值": dar_val, "说明": ""})
                if offset < len(data):
                    resp, consumed = self.axdr.decode(data, offset)
                    offset += consumed
                    item["响应数据"] = resp
                    eb_biz = self._decode_eb_data_content(item["OMD"], resp)
                    if eb_biz:
                        item["数据业务"] = eb_biz
                items.append(item)
            result["列表"] = items

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
            # count + SEQUENCE OF {OAD, 结果}（福建简化698：PIID-ACD 后为对象个数）
            if offset >= len(data):
                return result
            count = data[offset]
            offset += 1
            items = []
            for _ in range(count):
                item = {}
                if offset + 4 > len(data):
                    break
                item["OAD"] = self._parse_oad_raw(data, offset)
                offset += 4
                # 结果 (1 字节: 00 成功 / 其他错误)
                if offset < len(data):
                    res = data[offset]
                    offset += 1
                    item["结果"] = self._enrich_dar({"类型": "unsigned", "原始值": f"0x{res:02X}",
                                                     "解析值": res, "说明": ""})
                items.append(item)
            if len(items) == 1:
                single = items[0]
                if "OAD" in single:
                    result["OAD"] = single["OAD"]
                if "结果" in single:
                    result["结果"] = single["结果"]
            result["列表"] = items

        elif choice_tag == 0x02:
            result["子类型"] = "ReportResponseRecordList"
            # 与 List 相同：count + SEQUENCE OF {OAD, 结果}
            if offset >= len(data):
                return result
            count = data[offset]
            offset += 1
            items = []
            for _ in range(count):
                item = {}
                if offset + 4 > len(data):
                    break
                item["OAD"] = self._parse_oad_raw(data, offset)
                offset += 4
                if offset < len(data):
                    res = data[offset]
                    offset += 1
                    item["结果"] = self._enrich_dar({"类型": "unsigned", "原始值": f"0x{res:02X}",
                                                     "解析值": res, "说明": ""})
                items.append(item)
            if len(items) == 1:
                single = items[0]
                if "OAD" in single:
                    result["OAD"] = single["OAD"]
                if "结果" in single:
                    result["结果"] = single["结果"]
            result["列表"] = items

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
            # count + SEQUENCE OF OAD（福建简化698：PIID-ACD 后为对象个数，OAD 连续排列）
            if offset >= len(data):
                return result
            count = data[offset]
            offset += 1
            oads = []
            for _ in range(count):
                if offset + 4 > len(data):
                    break
                oads.append(self._parse_oad_raw(data, offset))
                offset += 4
            result["OAD列表"] = oads
            # 数据个数标志（01，固定）
            data_flag = None
            if offset < len(data):
                data_flag = data[offset]
                offset += 1
            if data_flag is not None:
                result["数据个数"] = data_flag
            # Data
            if offset < len(data):
                d, consumed = self.axdr.decode(data, offset)
                offset += consumed
                result["数据"] = d
                # 业务解码（单 OAD 时按 OAD 解码）
                if oads:
                    biz = self._decode_oad_business(oads[0], d)
                    if biz:
                        result["数据业务"] = biz
                    else:
                        eb_biz = self._decode_eb_data_content(oads[0], d)
                        if eb_biz:
                            result["数据业务"] = eb_biz
            # 时间标签 (optional, 00 00)
            if offset + 1 < len(data):
                result["剩余数据"] = data[offset:].hex().upper()

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
