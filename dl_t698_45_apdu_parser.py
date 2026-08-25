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

    # DAR 错误码映射（文档表25 DAR::=ENUMERATED）
    DAR_MAP = {
        0: "成功", 1: "硬件失效", 2: "暂时失效", 3: "拒绝读写", 4: "对象未定义",
        5: "对象接口类不符合", 6: "对象不存在", 7: "类型不匹配", 8: "越界",
        9: "数据块不可用", 10: "分帧传输已取消", 11: "不处于分帧传输状态",
        12: "块写取消", 13: "不存在块写状态", 14: "数据块序号无效", 15: "未授权",
        16: "通信速率不能更改", 17: "年时区数超", 18: "日时段数超", 19: "费率数超",
        20: "安全认证不匹配", 21: "重复充值", 22: "验证失败", 23: "安全认证失败",
        24: "客户编号不匹配", 25: "充值次数错误", 26: "购电超囤积", 27: "地址异常",
        28: "对称解密错误", 29: "非对称解密错误", 30: "签名错误", 31: "电能表挂起",
        32: "时间标签无效", 33: "请求超时", 34: "ESAM的P1P2不正确", 35: "ESAM的LC错误",
        36: "比对失败", 255: "其它",
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
            # EBE0 通用数据冻结：按类别走专用解码（任务配置/数据读取/公共参数）
            if di.startswith("EBE0"):
                ebe0_result = self._decode_ebe0_data(di, data_dict)
                if ebe0_result is not None:
                    return ebe0_result
            from gdw_eb_di_fields import EB_DI_FIELDS
            schema = EB_DI_FIELDS.get(di)
            # 请求附加参数（1C 开头 = date_time_s 时间，如 EB030307 读取参数）优先走时间解码，
            # 响应/上报数据（时间+边沿+NTB 数组）走字段 schema
            dv = data_dict.get("解析值", "")
            if isinstance(dv, str):
                try:
                    raw_bytes = bytes.fromhex(dv)
                except (ValueError, TypeError):
                    raw_bytes = None
                if raw_bytes and len(raw_bytes) >= 8 and raw_bytes[0] == 0x1C:
                    try:
                        dt, _ = self.axdr.decode(raw_bytes)
                        return {"A-XDR类型": {"值": data_dict.get("tag_name", "octet-string"),
                                              "类型": f"0x{data_dict.get('tag', 0x09):02X}",
                                              "长度": 1},
                                "A-XDR长度": {"值": len(raw_bytes), "类型": "长度域", "长度": 1},
                                "数据时间": {"值": dt.get("解析值", dv),
                                            "类型": "date_time_s", "长度": 8}}
                    except Exception:
                        pass
            if not schema:
                # 无字段定义：展示 A-XDR 头（类型+长度）并保留原始 hex
                if isinstance(dv, str):
                    axdr_head = {}
                    tag = data_dict.get("tag")
                    tag_name = data_dict.get("tag_name", "")
                    if tag is not None:
                        axdr_head["A-XDR类型"] = {"值": tag_name,
                                                  "类型": f"0x{tag:02X}",
                                                  "长度": 1}
                    axdr_head["A-XDR长度"] = {"值": len(raw_bytes) if raw_bytes else 0,
                                              "类型": "长度域", "长度": 1}
                    axdr_head["原始数据"] = {"值": dv, "类型": "hex",
                                             "长度": len(raw_bytes) if raw_bytes else 0}
                    return axdr_head
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
            # 数据长度不足以覆盖固定头字段时回退 A-XDR 头 + 原始数据
            # （固定头 = 非 list 字段的总长度；数据不足时按 schema 解会截断错解）
            fixed_len = self._eb_fixed_len(fields)
            if fixed_len > 0 and len(data_bytes) < fixed_len:
                return {"A-XDR类型": {"值": data_dict.get("tag_name", "octet-string"),
                                      "类型": f"0x{data_dict.get('tag', 0x09):02X}",
                                      "长度": 1},
                        "A-XDR长度": {"值": len(data_bytes), "类型": "长度域", "长度": 1},
                        "原始数据": {"值": data_bytes.hex().upper(), "类型": "hex",
                                     "长度": len(data_bytes)}}
            return self._decode_eb_fields(fields, data_bytes)
        except Exception:
            return None

    def _eb_fixed_len(self, fields: list) -> int:
        """计算字段定义中非 list 字段的固定头长度（list 之后忽略）"""
        total = 0
        for f in fields:
            ftype = f.get("type", "hex")
            if ftype == "list":
                break
            if ftype.startswith("uint"):
                total += int(ftype[4:]) // 8
            elif ftype in ("bcd", "hex", "ascii"):
                total += f.get("length", 1)
            elif ftype == "bcd_time":
                total += f.get("length", 6)
            elif ftype in ("enum", "bs8"):
                total += 1
            else:
                return 0
        return total

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
                    raw_field = data[offset:offset + 1]
                    v = raw_field[0] if raw_field else 0
                    offset += 1
                    emap = f.get("enum_map", {})
                    result[name] = {"值": emap.get(v, f"{v}(未定义)"), "类型": "enum",
                                    "长度": 1, "原始值": raw_field.hex().upper()}
                elif ftype.startswith("uint"):
                    nbytes = int(ftype[4:]) // 8
                    raw_field = data[offset:offset + nbytes]
                    # 698 承载按「645 减33逆序」规则：多字节 uint 高位在前（大端）
                    v = int.from_bytes(raw_field, "big") if len(raw_field) == nbytes else 0
                    offset += nbytes
                    result[name] = {"值": v, "类型": ftype, "长度": nbytes,
                                    "原始值": raw_field.hex().upper()}
                elif ftype == "bcd":
                    n = f.get("length", 1)
                    raw = data[offset:offset + n]
                    offset += n
                    result[name] = {"值": raw.hex().upper(), "类型": "bcd", "长度": n,
                                    "原始值": raw.hex().upper()}
                elif ftype == "bcd_time":
                    n = f.get("length", 6)
                    raw = data[offset:offset + n]
                    offset += n
                    if len(raw) >= 6:
                        # YY MM DD hh mm ss (BCD 每字节两位十进制)
                        def _bcd(b):
                            return (b >> 4) * 10 + (b & 0x0F)
                        yy, mm, dd = _bcd(raw[0]), _bcd(raw[1]), _bcd(raw[2])
                        hh, mi, ss = _bcd(raw[3]), _bcd(raw[4]), _bcd(raw[5])
                        year = 2000 + yy if yy <= 99 else yy
                        try:
                            v = f"{year:04d}-{mm:02d}-{dd:02d} {hh:02d}:{mi:02d}:{ss:02d}"
                        except (ValueError, TypeError):
                            v = raw.hex().upper()
                    else:
                        v = raw.hex().upper()
                    result[name] = {"值": v, "类型": "bcd_time", "长度": n,
                                    "原始值": raw.hex().upper()}
                elif ftype == "ascii":
                    n = f.get("length", 1)
                    raw = data[offset:offset + n]
                    offset += n
                    result[name] = {"值": raw.decode("ascii", errors="replace").rstrip(),
                                    "类型": "ascii", "长度": n,
                                    "原始值": raw.hex().upper()}
                elif ftype == "hex":
                    n = f.get("length", 1)
                    raw_field = data[offset:offset + n]
                    result[name] = {"值": raw_field.hex().upper(),
                                    "类型": "hex", "长度": n,
                                    "原始值": raw_field.hex().upper()}
                    offset += n
                elif ftype == "bs8":
                    raw_field = data[offset:offset + 1]
                    v = raw_field[0] if raw_field else 0
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
                                    "类型": "bs8", "长度": 1,
                                    "原始值": raw_field.hex().upper()}
                elif ftype == "list":
                    # 每项固定长度（item_fields 均为定长）→ 按 item 长度切分
                    item_fields = f.get("item_fields", [])
                    item_len = self._eb_item_len(item_fields)
                    if item_len <= 0:
                        raw_field = data[offset:]
                        result[name] = {"值": raw_field.hex().upper(),
                                        "类型": "list", "长度": len(raw_field),
                                        "原始值": raw_field.hex().upper()}
                        offset = len(data)
                        continue
                    items = []
                    raw_items = []
                    while offset + item_len <= len(data):
                        raw_item = data[offset:offset + item_len]
                        items.append(self._decode_eb_fields(item_fields, raw_item))
                        raw_items.append(raw_item.hex().upper())
                        offset += item_len
                    result[name] = {"值": items, "类型": "list",
                                    "长度": len(items) * item_len,
                                    "原始值": raw_items}
                else:
                    result[name] = {"值": f"(未知类型 {ftype})", "类型": ftype, "长度": 0}
                    break
            except (IndexError, ValueError):
                raw_field = data[offset:]
                result[name + " (解析截断)"] = {"值": raw_field.hex().upper(),
                                                "类型": "hex", "长度": len(raw_field),
                                                "原始值": raw_field.hex().upper()}
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

    # ═══════════════════════════════════════════════════════════════
    # EBE0 通用数据冻结 专用解码
    # ═══════════════════════════════════════════════════════════════

    # EBE0 任务类型名称映射
    _EBE0_TASK_TYPE_MAP = {
        0x01: "数据冻结任务",
        0x02: "数据不一致比对任务",
        0x03: "数据区间越限判断任务",
        0x04: "数据幅值越限判断任务",
    }

    # EBE0 数据项格式字映射
    _EBE0_FORMAT_MAP = {
        0x00: "方式1：普通数据标识数据",
        0x01: "方式2：需进行时标修正",
        0x02: "方式3：需进行时标规整和修正",
        0x10: "方式4：给定明文APDU(698任务组)",
    }

    # 645 DI 大类 → 数据块名称映射（DI1=FF 时使用）
    # DI3_DI2 → 类别中文名
    _645_DI_BLOCK_MAP = {
        "0201": "电压",
        "0202": "电流",
        "0203": "有功功率",
        "0204": "无功功率",
        "0205": "视在功率",
        "0206": "功率因数",
        "0207": "频率",
        "0208": "相角",
        "0001": "正向有功总电能",
        "0002": "反向有功总电能",
        "0009": "正向无功总电能",
        "000A": "反向无功总电能",
    }

    # 常见扩展/厂家自定义 645 DI 补充表（标准字典未收录的常用项）
    _645_DI_EXTRA_MAP = {
        "0400010C": "日期、星期及时间",
    }

    def _get_645_di_name(self, di_code: str) -> Optional[str]:
        """获取 645 数据标识对应的名称，查不到返回 None

        支持 FF 数据块识别：
        - DI1=FF（第3字节） → 该 DI2 类全部数据组成的数据块
        - 其他位置 FF → 尝试基准项 + "（数据块）"
        """
        di_upper = di_code.upper()
        try:
            from dlt645_di_lookup import DLT645DILookup
            if not hasattr(self, "_dlt645_lookup"):
                self._dlt645_lookup = DLT645DILookup()
            info = self._dlt645_lookup.get_di_info(di_upper)
            if info:
                return info.get("name")

            # 查补充扩展表
            if di_upper in self._645_DI_EXTRA_MAP:
                return self._645_DI_EXTRA_MAP[di_upper]

            # 逐字节分析 FF 的位置
            if "FF" not in di_upper:
                return None
            b0, b1, b2, b3 = di_upper[0:2], di_upper[2:4], di_upper[4:6], di_upper[6:8]

            # DI1=FF (第3字节，索引2)：该 DI2 类数据块
            if b2 == "FF" and b3 != "FF":
                di3_di2 = b0 + b1
                category = self._645_DI_BLOCK_MAP.get(di3_di2)
                if category:
                    return f"{category}数据块"
                # 映射表没有的，用基准项推断
                trial = b0 + b1 + "01" + b3
                base_info = self._dlt645_lookup.get_di_info(trial)
                if base_info:
                    base_name = base_info.get("name", "")
                    # 去掉开头的相别/序号描述
                    for prefix in ("A相", "B相", "C相", "总", "费率1", "第1"):
                        if base_name.startswith(prefix):
                            suffix = base_name[len(prefix):]
                            if suffix:
                                return f"{suffix}数据块"
                    return f"{base_name}数据块"

            # 其他位置 FF：尝试替换为 01 找基准
            bytes_list = [b0, b1, b2, b3]
            ff_positions = [i for i, b in enumerate(bytes_list) if b == "FF"]
            for probe in ("01", "02", "00"):
                trial = "".join(probe if i in ff_positions else b
                                for i, b in enumerate(bytes_list))
                base_info = self._dlt645_lookup.get_di_info(trial)
                if base_info:
                    base_name = base_info.get("name", "")
                    return f"{base_name}（数据块）"
        except Exception:
            pass
        return None

    def _make_di_entry(self, di: str, label: str = "数据标识") -> Dict[str, Any]:
        """构造带名称的数据标识条目 dict（名称写入"说明"，同屏可见）"""
        name = self._get_645_di_name(di)
        desc = name if name else ""
        entry: Dict[str, Any] = {
            label: {"值": di, "类型": "hex", "长度": 4, "原始值": di,
                    "说明": name if name else ""}
        }
        return entry

    def _decode_ebe0_data(self, di: str, data_dict: Any) -> Optional[Dict[str, Any]]:
        """EBE0 通用数据冻结数据内容解码

        EBE0 数据通过 698 octet-string 承载，内部为 645 帧头 + 实际数据。
        645 帧头：操作者代码(4B BCD) + 密码(3B BCD) + PA(1B) = 8 字节

        按 DI 分类：
        - EBE0E0xx：公共参数类（走通用 EB_DI_FIELDS schema）
        - EBE001xx / EBE0xxxx 且 DI1=01：任务配置（通用头 + 专用参数 + 数据项列表）
        - EBE000xx / EBE0xxxx 且 DI1=00：数据读取响应/上报
        """
        try:
            dv = data_dict.get("解析值", "")
            if not isinstance(dv, str):
                return None
            try:
                raw_bytes = bytes.fromhex(dv)
            except (ValueError, TypeError):
                return None
            if not raw_bytes:
                return None

            # 分类：取 DI 的第 3 字节（DI1，从右数第3个，即索引2-3 hex字符）
            # DI = EBE0xxxx → 第3字节 = 0xE0 (公共参数) / 0x01 (任务配置) / 0x00 (数据读取)
            di_bytes = bytes.fromhex(di)
            di1 = di_bytes[2]  # 0-indexed: 0=DI3=EB, 1=DI2=E0, 2=DI1, 3=DI0

            # 尝试剥离 8 字节 645 帧头（操作者4B+密码3B+PA1B）
            # GET 响应/REPORT上报可能没有 8 字节前缀，SET 请求才有
            payload = raw_bytes
            frame_info = None
            if len(raw_bytes) >= 8:
                # 启发式判断：如果前 7 字节看起来像操作者+密码（常见值 11111111 + 000000），
                # 且第 8 字节 PA 为有效值（0x00~0x0F），则视为有 645 帧头
                pa_candidate = raw_bytes[7]
                if pa_candidate <= 0x0F:
                    op_code = raw_bytes[0:4].hex().upper()
                    password = raw_bytes[4:7].hex().upper()
                    # 常见值：操作者=11111111, 密码=000000
                    if op_code == "11111111" or password == "000000":
                        frame_info = {
                            "操作者代码": {"值": op_code, "类型": "bcd", "长度": 4,
                                         "原始值": op_code},
                            "密码": {"值": password, "类型": "bcd", "长度": 3,
                                     "原始值": password},
                            "PA权限等级": {"值": f"{pa_candidate}(0x{pa_candidate:02X})",
                                         "类型": "uint8", "长度": 1,
                                         "原始值": f"{pa_candidate:02X}"},
                        }
                        payload = raw_bytes[8:]

            result: Dict[str, Any] = {}

            if di1 == 0xE0:
                # 公共参数类：优先走 EB_DI_FIELDS schema
                from gdw_eb_di_fields import EB_DI_FIELDS
                schema = EB_DI_FIELDS.get(di)
                if schema:
                    fields = schema.get("fields", [])
                    fixed_len = self._eb_fixed_len(fields)
                    if fixed_len > 0 and len(payload) >= fixed_len:
                        result = self._decode_eb_fields(fields, payload)
                    else:
                        result = {"原始值": {"值": payload.hex().upper(), "类型": "hex", "长度": len(payload)}}
                else:
                    result = {"原始值": {"值": payload.hex().upper(), "类型": "hex", "长度": len(payload)}}

            elif di1 == 0x01:
                # 任务配置：通用头 + 专用参数（按任务类型分派）+ 数据项列表
                result = self._decode_ebe0_task_config(payload)

            else:
                # 其他类别暂按原始 hex 展示
                result = {"原始值": {"值": payload.hex().upper(), "类型": "hex", "长度": len(payload)}}

            if frame_info and result:
                result = {"645帧头": {"值": frame_info, "类型": "struct", "长度": 8},
                          **result}
            return result if result else None
        except Exception:
            return None

    def _decode_ebe0_task_config(self, data: bytes) -> Dict[str, Any]:
        """解码 EBE0 任务配置数据（去掉 645 帧头后的数据）

        通用头（11字节，大端）：
        - 任务类型(1B)
        - 任务周期(2B)：位域，Bit13~11单位 + Bit10~0数值
        - 读取延迟(1B)：秒
        - 数据存储次数(2B)
        - 返回数据预计长度(2B)
        - 任务功能标识(1B)
        - 任务允许执行次数(2B)

        专用参数（按任务类型）：
        - 01H 数据冻结：M1(1B) + M1×[格式字(1B)+内容长度(1B)+内容(LB)]
        - 02H 数据不一致：允许触发次数(2B)+M1(1B)+M1×DI(4B)+M2(1B)+M2×DI(4B)
        - 03H 区间越限：允许触发次数(2B)+判断DI(4B)+数值长度(1B)+边界数量(1B)+边界值+M3(1B)+M3×DI(4B)
        - 04H 幅值越限：允许触发次数(2B)+判断DI(4B)+数值长度(1B)+变化幅值(LB)+M3(1B)+M3×DI(4B)
        """
        result: Dict[str, Any] = {}
        offset = 0
        if len(data) < 11:
            return {"原始数据(长度不足)": {"值": data.hex().upper(), "类型": "hex", "长度": len(data)}}

        # --- 通用头 ---
        task_type = data[offset]
        tt_raw = data[offset:offset + 1].hex().upper()
        offset += 1
        result["任务类型"] = {
            "值": self._EBE0_TASK_TYPE_MAP.get(task_type, f"保留(0x{task_type:02X})"),
            "类型": "enum", "长度": 1, "原始值": tt_raw}

        cycle_raw = data[offset:offset + 2]
        cycle_val = int.from_bytes(cycle_raw, "big")
        offset += 2
        cycle_unit = (cycle_val >> 11) & 0x07
        cycle_num = cycle_val & 0x07FF
        unit_names = {0: "秒", 1: "分", 2: "小时", 3: "日"}
        unit_name = unit_names.get(cycle_unit, f"保留({cycle_unit})")
        result["任务周期"] = {
            "值": f"{cycle_num} {unit_name} (0x{cycle_val:04X})",
            "类型": "bitfield", "长度": 2, "原始值": cycle_raw.hex().upper()}

        delay = data[offset]
        delay_raw = data[offset:offset + 1].hex().upper()
        offset += 1
        result["读取延迟"] = {"值": f"{delay} 秒", "类型": "uint8", "长度": 1,
                             "原始值": delay_raw}

        store_raw = data[offset:offset + 2]
        store_count = int.from_bytes(store_raw, "big")
        offset += 2
        result["数据存储次数"] = {"值": store_count, "类型": "uint16", "长度": 2,
                                  "原始值": store_raw.hex().upper()}

        max_raw = data[offset:offset + 2]
        max_len = int.from_bytes(max_raw, "big")
        offset += 2
        result["返回数据预计长度"] = {"值": f"{max_len} 字节", "类型": "uint16", "长度": 2,
                                      "原始值": max_raw.hex().upper()}

        func_flag = data[offset]
        func_raw = data[offset:offset + 1].hex().upper()
        offset += 1
        result["任务功能标识"] = {
            "值": f"0x{func_flag:02X}",
            "类型": "bs8", "长度": 1, "原始值": func_raw}

        exec_raw = data[offset:offset + 1]
        exec_count = exec_raw[0] if exec_raw else 0
        offset += 1
        result["任务允许执行次数"] = {
            "值": "不限制(255)" if exec_count == 255 else str(exec_count),
            "类型": "uint8", "长度": 1, "原始值": exec_raw.hex().upper()}

        # --- 专用参数 ---
        if offset >= len(data):
            return result

        if task_type == 0x01:
            # 数据冻结任务专用参数
            special = self._decode_ebe0_freeze_special(data[offset:])
            result["专用参数(数据冻结)"] = {"值": special, "类型": "struct",
                                            "长度": len(data) - offset}
        elif task_type == 0x02:
            special = self._decode_ebe0_compare_special(data[offset:])
            result["专用参数(数据不一致)"] = {"值": special, "类型": "struct",
                                             "长度": len(data) - offset}
        elif task_type == 0x03:
            special = self._decode_ebe0_threshold_special(data[offset:], range_mode=True)
            result["专用参数(区间越限)"] = {"值": special, "类型": "struct",
                                           "长度": len(data) - offset}
        elif task_type == 0x04:
            special = self._decode_ebe0_threshold_special(data[offset:], range_mode=False)
            result["专用参数(幅值越限)"] = {"值": special, "类型": "struct",
                                           "长度": len(data) - offset}
        else:
            result["专用参数(原始)"] = {
                "值": data[offset:].hex().upper(),
                "类型": "hex", "长度": len(data) - offset}

        return result

    def _decode_ebe0_freeze_special(self, data: bytes) -> Dict[str, Any]:
        """数据冻结任务专用参数解码：M1 + M1×[格式字+内容长度+内容]"""
        result: Dict[str, Any] = {}
        offset = 0
        if len(data) < 1:
            return result
        m1_raw = data[offset:offset + 1]
        m1 = m1_raw[0] if m1_raw else 0
        offset += 1
        result["数据项个数M1"] = {"值": m1, "类型": "uint8", "长度": 1,
                                  "原始值": m1_raw.hex().upper()}

        items = []
        for i in range(m1):
            if offset + 2 > len(data):
                break
            fmt_raw = data[offset:offset + 1]
            fmt = fmt_raw[0] if fmt_raw else 0
            offset += 1
            len_raw = data[offset:offset + 1]
            data_len = len_raw[0] if len_raw else 0
            offset += 1
            if offset + data_len > len(data):
                content_hex = data[offset:].hex().upper()
                items.append({
                    f"数据项{i+1}": {
                        "值": {
                            "格式字": {"值": self._EBE0_FORMAT_MAP.get(fmt, f"0x{fmt:02X}"),
                                     "类型": "enum", "长度": 1,
                                     "原始值": fmt_raw.hex().upper()},
                            "内容长度": {"值": data_len, "类型": "uint8", "长度": 1,
                                         "原始值": len_raw.hex().upper()},
                            "参数内容(截断)": {"值": content_hex, "类型": "hex",
                                                "长度": len(data) - offset + 2,
                                                "原始值": content_hex},
                        },
                        "类型": "struct", "长度": len(data) - offset + 2
                    }
                })
                break
            content = data[offset:offset + data_len]
            offset += data_len

            # 解析参数内容：格式字 00/01/02 的前 4 字节为 645 数据标识
            content_info: Dict[str, Any] = {}
            if fmt in (0x00, 0x01, 0x02) and data_len >= 4:
                di = content[:4].hex().upper()
                di_entry = self._make_di_entry(di)
                content_info.update(di_entry)
                if data_len > 4:
                    extra = content[4:].hex().upper()
                    content_info["附加参数"] = {"值": extra, "类型": "hex", "长度": data_len - 4,
                                                "原始值": extra}
            elif fmt == 0x10:
                # 方式4：明文 APDU
                apdu_hex = content.hex().upper()
                content_info["明文APDU"] = {"值": apdu_hex, "类型": "hex", "长度": data_len,
                                            "原始值": apdu_hex}
            else:
                raw_all = content.hex().upper()
                content_info["参数内容"] = {"值": raw_all, "类型": "hex", "长度": data_len,
                                            "原始值": raw_all}

            items.append({
                f"数据项{i+1}": {
                    "值": {
                        "格式字": {"值": self._EBE0_FORMAT_MAP.get(fmt, f"0x{fmt:02X}"),
                                 "类型": "enum", "长度": 1,
                                 "原始值": fmt_raw.hex().upper()},
                        "内容长度": {"值": data_len, "类型": "uint8", "长度": 1,
                                     "原始值": len_raw.hex().upper()},
                        **content_info,
                    },
                    "类型": "struct", "长度": 2 + data_len
                }
            })
        result["数据项列表"] = {"值": items, "类型": "list", "长度": offset - 1}
        return result

    def _decode_ebe0_compare_special(self, data: bytes) -> Dict[str, Any]:
        """数据不一致比对任务专用参数解码"""
        result: Dict[str, Any] = {}
        offset = 0
        if len(data) < 3:
            return {"原始数据": {"值": data.hex().upper(), "类型": "hex", "长度": len(data)}}

        trigger_raw = data[offset:offset + 2]
        trigger_count = int.from_bytes(trigger_raw, "big")
        offset += 2
        result["任务允许触发次数"] = {"值": trigger_count, "类型": "uint16", "长度": 2,
                                    "原始值": trigger_raw.hex().upper()}

        m1_raw = data[offset:offset + 1]
        m1 = m1_raw[0] if m1_raw else 0
        offset += 1
        result["比对的数据标识个数M1"] = {"值": m1, "类型": "uint8", "长度": 1,
                                          "原始值": m1_raw.hex().upper()}

        compare_list = []
        for i in range(m1):
            if offset + 4 > len(data):
                break
            di_raw = data[offset:offset + 4]
            di = di_raw.hex().upper()
            offset += 4
            compare_list.append({f"比对数据标识{i+1}": {"值": di, "类型": "hex", "长度": 4,
                                                     "原始值": di},
                                 f"比对数据标识{i+1}名称": {"值": name, "类型": "string", "长度": 0}
                                 if (name := self._get_645_di_name(di)) else None})
        # 去掉 None 项
        compare_list = [{k: v for k, v in item.items() if v is not None} for item in compare_list]
        result["比对数据标识列表"] = {"值": compare_list, "类型": "list", "长度": m1 * 4}

        if offset < len(data):
            m2_raw = data[offset:offset + 1]
            m2 = m2_raw[0] if m2_raw else 0
            offset += 1
            result["自动读取的数据标识个数M2"] = {"值": m2, "类型": "uint8", "长度": 1,
                                                  "原始值": m2_raw.hex().upper()}
            auto_list = []
            for i in range(m2):
                if offset + 4 > len(data):
                    break
                di = data[offset:offset + 4].hex().upper()
                offset += 4
                item = {f"自动读取数据标识{i+1}": {"值": di, "类型": "hex", "长度": 4,
                                                  "原始值": di}}
                name = self._get_645_di_name(di)
                if name:
                    item[f"自动读取数据标识{i+1}名称"] = {"值": name, "类型": "string", "长度": 0}
                auto_list.append(item)
            result["自动读取数据标识列表"] = {"值": auto_list, "类型": "list", "长度": m2 * 4}

        return result
    def _decode_ebe0_threshold_special(self, data: bytes, range_mode: bool) -> Dict[str, Any]:
        """区间越限/幅值越限任务专用参数解码

        range_mode=True: 区间越限 - 有多个边界值
        range_mode=False: 幅值越限 - 只有一个变化幅值
        """
        result: Dict[str, Any] = {}
        offset = 0
        if len(data) < 7:
            return {"原始数据": {"值": data.hex().upper(), "类型": "hex", "长度": len(data)}}

        trigger_raw = data[offset:offset + 2]
        trigger_count = int.from_bytes(trigger_raw, "big")
        offset += 2
        result["任务允许触发次数"] = {"值": trigger_count, "类型": "uint16", "长度": 2,
                                    "原始值": trigger_raw.hex().upper()}

        judge_raw = data[offset:offset + 4]
        judge_di = judge_raw.hex().upper()
        offset += 4
        result["判断的数据标识"] = {"值": judge_di, "类型": "hex", "长度": 4,
                                    "原始值": judge_di}
        judge_name = self._get_645_di_name(judge_di)
        if judge_name:
            result["判断的数据标识名称"] = {"值": judge_name, "类型": "string", "长度": 0}

        vlen_raw = data[offset:offset + 1]
        val_len = vlen_raw[0] if vlen_raw else 0
        offset += 1
        result["判断的数值长度"] = {"值": f"{val_len} 字节", "类型": "uint8", "长度": 1,
                                   "原始值": vlen_raw.hex().upper()}

        if range_mode:
            # 区间越限：边界数量 + 边界值列表
            if offset >= len(data):
                return result
            bc_raw = data[offset:offset + 1]
            boundary_count = bc_raw[0] if bc_raw else 0
            offset += 1
            result["数据边界数量M2"] = {"值": boundary_count, "类型": "uint8", "长度": 1,
                                       "原始值": bc_raw.hex().upper()}

            boundaries = []
            for i in range(boundary_count):
                if offset + val_len > len(data):
                    break
                val_raw = data[offset:offset + val_len]
                val_hex = val_raw.hex().upper()
                offset += val_len
                boundaries.append({f"边界值{i+1}": {"值": val_hex, "类型": "hex",
                                                    "长度": val_len, "原始值": val_hex}})
            result["数据边界值列表"] = {"值": boundaries, "类型": "list",
                                       "长度": boundary_count * val_len}
        else:
            # 幅值越限：变化幅值
            if offset + val_len > len(data):
                return result
            amp_raw = data[offset:offset + val_len]
            amp = amp_raw.hex().upper()
            offset += val_len
            result["数据变化幅值"] = {"值": amp, "类型": "hex", "长度": val_len,
                                     "原始值": amp}

        # 自动读取的数据标识
        if offset < len(data):
            m3_raw = data[offset:offset + 1]
            m3 = m3_raw[0] if m3_raw else 0
            offset += 1
            result["自动读取的数据标识个数M3"] = {"值": m3, "类型": "uint8", "长度": 1,
                                                  "原始值": m3_raw.hex().upper()}
            auto_list = []
            for i in range(m3):
                if offset + 4 > len(data):
                    break
                circle_di = data[offset:offset + 4].hex().upper()
                offset += 4
                item = {f"自动读取数据标识{i+1}": {"值": circle_di, "类型": "hex",
                                                            "长度": 4, "原始值": circle_di}}
                name = self._get_645_di_name(circle_di)
                if name:
                    item[f"自动读取数据标识{i+1}名称"] = {"值": name, "类型": "string", "长度": 0}
                auto_list.append(item)
            result["自动读取数据标识列表"] = {"值": auto_list, "类型": "list", "长度": m3 * 4}

        return result

    def _decode_ebe0_read_response(self, data: bytes) -> Dict[str, Any]:
        """解码 EBE0 数据读取响应/上报数据（去掉 645 帧头后）

        表2 格式：
        - 任务类型(1B)
        - 响应结果(1B)：0=无数据, 1=正常, 2=超长只返回部分
        - 数据冻结开始时标(6B BCD)
        - 存储次数(2B)
        - 任务周期(2B)
        - 响应的冻结点数M1(1B)
        - 数据标识个数M2(1B)
        - M2 × [数据标识(4B) + 单个长度(1B) + M1个点数据(LB)]
        """
        result: Dict[str, Any] = {}
        offset = 0
        if len(data) < 13:
            return {"原始数据(长度不足)": {"值": data.hex().upper(), "类型": "hex", "长度": len(data)}}

        task_type = data[offset]
        offset += 1
        result["任务类型"] = {
            "值": self._EBE0_TASK_TYPE_MAP.get(task_type, f"保留(0x{task_type:02X})"),
            "类型": "enum", "长度": 1}

        resp_result = data[offset]
        offset += 1
        result_map = {0: "无数据(请求范围内无数据)", 1: "正常响应",
                      2: "超长(只返回部分数据)"}
        result["响应结果"] = {
            "值": result_map.get(resp_result, f"保留(0x{resp_result:02X})"),
            "类型": "enum", "长度": 1}

        if resp_result == 0:
            result["备注"] = {"值": "无后续数据", "类型": "string", "长度": 0}
            return result

        # 时标 6B BCD
        time_bytes = data[offset:offset + 6]
        offset += 6
        def _bcd(b): return (b >> 4) * 10 + (b & 0x0F)
        try:
            yy, mm, dd = _bcd(time_bytes[0]), _bcd(time_bytes[1]), _bcd(time_bytes[2])
            hh, mi, ss = _bcd(time_bytes[3]), _bcd(time_bytes[4]), _bcd(time_bytes[5])
            year = 2000 + yy if yy <= 99 else yy
            time_str = f"{year:04d}-{mm:02d}-{dd:02d} {hh:02d}:{mi:02d}:{ss:02d}"
        except (ValueError, IndexError):
            time_str = time_bytes.hex().upper()
        result["数据冻结开始时标"] = {"值": time_str, "类型": "bcd_time", "长度": 6}

        store_idx = int.from_bytes(data[offset:offset + 2], "big")
        offset += 2
        result["存储次数序号"] = {"值": store_idx, "类型": "uint16", "长度": 2}

        cycle_val = int.from_bytes(data[offset:offset + 2], "big")
        offset += 2
        cycle_unit = (cycle_val >> 11) & 0x07
        cycle_num = cycle_val & 0x07FF
        unit_names = {0: "秒", 1: "分", 2: "小时", 3: "日"}
        unit_name = unit_names.get(cycle_unit, f"保留({cycle_unit})")
        result["任务周期"] = {
            "值": f"{cycle_num} {unit_name} (0x{cycle_val:04X})",
            "类型": "bitfield", "长度": 2}

        m1 = data[offset]
        offset += 1
        result["响应的冻结点数M1"] = {"值": m1, "类型": "uint8", "长度": 1}

        if m1 == 0:
            return result

        m2 = data[offset]
        offset += 1
        result["数据标识个数M2"] = {"值": m2, "类型": "uint8", "长度": 1}

        di_list = []
        for i in range(m2):
            if offset + 5 > len(data):
                break
            di = data[offset:offset + 4].hex().upper()
            offset += 4
            single_len = data[offset]
            offset += 1

            # 读取 M1 个点的数据
            points = []
            for j in range(m1):
                if offset + single_len > len(data):
                    # 数据截断
                    remaining = data[offset:]
                    points.append({
                        f"第{j+1}点(截断)": {
                            "值": remaining.hex().upper(),
                            "类型": "hex", "长度": len(remaining)}
                    })
                    break
                point_data = data[offset:offset + single_len]
                offset += single_len

                # 698 数据类型：首字节为类型 tag
                if single_len >= 1 and point_data[0] == 0x00:
                    point_info = {"值": "NULL(无数据/读取失败)", "类型": "null", "长度": single_len}
                elif single_len >= 1 and point_data[0] != 0x00:
                    # 尝试 A-XDR 解码
                    try:
                        decoded, consumed = self.axdr.decode(point_data, 0)
                        val = decoded.get("解析值", point_data.hex().upper())
                        if isinstance(val, list):
                            val = f"[{', '.join(str(v) for v in val[:5])}...]" if len(val) > 5 else str(val)
                        tag = decoded.get("tag", point_data[0])
                        tag_name = decoded.get("tag_name", f"0x{tag:02X}")
                        point_info = {
                            "值": str(val),
                            "类型": f"A-XDR:{tag_name}",
                            "长度": single_len
                        }
                    except Exception:
                        point_info = {"值": point_data.hex().upper(),
                                      "类型": "hex", "长度": single_len}
                else:
                    point_info = {"值": point_data.hex().upper(),
                                  "类型": "hex", "长度": single_len}

                points.append({f"第{j+1}点": {"值": point_info,
                                            "类型": point_info["类型"],
                                            "长度": single_len}})

            di_entry = {"数据标识": {"值": di, "类型": "hex", "长度": 4}}
            di_name = self._get_645_di_name(di)
            if di_name:
                di_entry["数据标识名称"] = {"值": di_name, "类型": "string", "长度": 0}

            di_list.append({
                f"数据标识{i+1}": {
                    "值": {
                        **di_entry,
                        "单数据长度": {"值": single_len, "类型": "uint8", "长度": 1},
                        "数据点列表": {"值": points, "类型": "list",
                                     "长度": single_len * m1},
                    },
                    "类型": "struct", "长度": 4 + 1 + single_len * m1
                }
            })
        result["数据内容"] = {"值": di_list, "类型": "list", "长度": offset - 13}
        return result

    def _parse_axdr_items_or_single(self, data: bytes, offset: int) -> Tuple[list, int]:
        """兼容解析：数据个数前缀 + N×A-XDR，或直接单个 A-XDR

        福建简化698 的 ACTION-Response NormalList 每项 DAR 后可能带「数据个数」：
        `00`(DAR) + `01`(数据个数) + `09 81 81 ...`(octet-string)
        文档示例（无数据个数）为 `00`(DAR) + `09 ...`(直接 A-XDR)。

        先尝试「数据个数 N（1~64）+ N 个 A-XDR」，失败回退「单个 A-XDR」。

        Returns: (数据项列表, 新偏移)
        """
        try:
            n = data[offset]
            if 1 <= n <= 64 and offset + 1 < len(data):
                o = offset + 1
                items = []
                for _ in range(n):
                    d, c = self.axdr.decode(data, o)
                    items.append(d)
                    o += c
                if o <= len(data):
                    return items, o
        except Exception:
            pass
        d, c = self.axdr.decode(data, offset)
        return [d], offset + c

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

    def _parse_time_tag(self, data: bytes, offset: int, result: dict) -> int:
        """请求尾部 OPTIONAL TimeTag（00=无时间标签），存在则写入 result 并前进偏移"""
        if offset < len(data):
            time_tag = data[offset]
            offset += 1
            if time_tag == 0:
                result["时间标签"] = {"类型": "TimeTag", "原始值": "0x00", "解析值": 0, "说明": "无时间标签"}
            else:
                result["时间标签"] = {"类型": "TimeTag", "原始值": f"0x{time_tag:02X}", "解析值": time_tag, "说明": "有时间标签"}
        return offset

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

    def _decode_action_parameter(self, omd: Dict[str, Any], data: Any) -> Optional[Dict[str, str]]:
        """按 OMD（OI+方法标识）对 ACTION 方法参数做业务解码（安徽补充规约）"""
        try:
            if not isinstance(omd, dict) or data is None:
                return None
            pv = omd.get("解析值")
            if not isinstance(pv, dict):
                return None
            oi_str = pv.get("OI", "0x0000")
            method_id = pv.get("方法标识", 0)
            oi = int(oi_str, 16) if isinstance(oi_str, str) else int(oi_str)
            from dl_t698_45_data_decode import decode_action_parameter
            return decode_action_parameter(oi, method_id, data)
        except Exception:
            return None

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

    def _parse_get_result(self, data: bytes, offset: int) -> Tuple[dict, int]:
        """解析 Get-Result::=CHOICE { 错误信息[0] DAR, 数据[1] Data }（文档表54）

        Returns:
            ({"数据访问结果": {...}} 或 {"数据": {...}}, 新offset)
        """
        res_tag = data[offset]
        if res_tag == 0x01:
            # [1] Data：完整 A-XDR 数据
            d, consumed = self.axdr.decode(data, offset + 1)
            return {"数据": d}, offset + 1 + consumed
        if res_tag == 0x00:
            # [0] DAR：enum 裸值 1 字节
            dar_val = data[offset + 1] if offset + 1 < len(data) else 0
            return {"数据访问结果": {"类型": "DAR", "原始值": f"0x{dar_val:02X}",
                                    "解析值": dar_val,
                                    "说明": self.DAR_MAP.get(dar_val, f"未知DAR({dar_val})")}}, offset + 2
        # 无上下文标签的裸 DAR（部分实机实现）：字节值本身即错误码
        return {"数据访问结果": {"类型": "DAR", "原始值": f"0x{res_tag:02X}",
                                "解析值": res_tag,
                                "说明": self.DAR_MAP.get(res_tag, f"未知DAR({res_tag})")}}, offset + 1

    def _parse_get_request(self, data: bytes) -> dict:
        """GET-Request: choice { [1]Normal, [2]NormalList, [3]Record, [4]RecordList, [5]Next, [6]MD5 }（表45）"""
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
            offset = self._parse_time_tag(data, offset, result)

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
            # 时间标签 (可选)
            offset = self._parse_time_tag(data, offset, result)

        elif choice_tag == 0x03:
            result["子类型"] = "GetRequestRecord"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # OAD + RCSD（RCSD 复杂结构，保留原始数据展示）
            result["OAD"] = self._parse_oad_raw(data, offset)
            offset += 4
            if offset < len(data):
                result["RCSD"] = data[offset:].hex().upper()
            return result

        elif choice_tag == 0x04:
            result["子类型"] = "GetRequestRecordList"
            # PIID + OAD列表 + RCSD（结构复杂，保留原始数据）
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            count = data[offset]
            offset += 1
            oads = []
            for _ in range(count):
                oads.append(self._parse_oad_raw(data, offset))
                offset += 4
            result["OAD列表"] = oads
            if offset < len(data):
                result["RCSD"] = data[offset:].hex().upper()
            return result

        elif choice_tag == 0x05:
            result["子类型"] = "GetRequestNext"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # long-unsigned 块序号
            block, consumed = self.axdr.decode(data, offset)
            offset += consumed
            result["块序号"] = block

        elif choice_tag == 0x06:
            result["子类型"] = "GetRequestMD5"
            # PIID
            piid_byte = data[offset]
            offset += 1
            result["PIID"] = self._parse_piid(piid_byte)
            # OAD
            result["OAD"] = self._parse_oad_raw(data, offset)
            offset += 4

        return result

    def _parse_get_response(self, data: bytes) -> dict:
        """GET-Response: choice { [1]Normal, [2]NormalList, [3]Record, [4]RecordList, [5]Next, [23]SimplifyRecord }（表53）"""
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
            # Get-Result: { 错误信息[0] DAR, 数据[1] Data }（表54）
            if offset < len(data):
                gr, offset = self._parse_get_result(data, offset)
                result.update(gr)
                d = gr.get("数据")
                if d is not None:
                    # 业务解码
                    biz = self._decode_oad_business(result["OAD"], d)
                    if biz:
                        result["数据业务"] = biz

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
                    gr, offset = self._parse_get_result(data, offset)
                    item.update(gr)
                    d = gr.get("数据")
                    if d is not None:
                        # 业务解码
                        biz = self._decode_oad_business(item["OAD"], d)
                        if biz:
                            item["数据业务"] = biz
                items.append(item)
            result["列表"] = items

        elif choice_tag == 0x03:
            result["子类型"] = "GetResponseRecord"
            # PIID-ACD + OAD + RCSD + 响应数据（RCSD 复杂结构保留原始数据）
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            result["OAD"] = self._parse_oad_raw(data, offset)
            offset += 4
            if offset < len(data):
                result["RCSD及响应数据"] = data[offset:].hex().upper()

        elif choice_tag == 0x04:
            result["子类型"] = "GetResponseRecordList"
            # 结构复杂：PIID-ACD 后整体保留原始数据
            piid_byte = data[offset]
            offset += 1
            result["PIID-ACD"] = self._parse_piid(piid_byte, is_acd=True)
            if offset < len(data):
                result["记录数据"] = data[offset:].hex().upper()

        elif choice_tag == 0x05:
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

        elif choice_tag == 0x17:
            result["子类型"] = "GetResponseSimplifyRecord"
            if offset < len(data):
                result["精简记录数据"] = data[offset:].hex().upper()

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
            # 时间标签 (可选)
            offset = self._parse_time_tag(data, offset, result)

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
            # 时间标签 (可选)
            offset = self._parse_time_tag(data, offset, result)

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
                # DAR 为裸 enum 值（表25），非 A-XDR 完整编码
                dar_val = data[offset]
                offset += 1
                result["结果"] = self._enrich_dar({"类型": "DAR", "原始值": f"0x{dar_val:02X}",
                                                   "解析值": dar_val, "说明": ""})

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
                # 安徽补充规约：方法参数业务解码
                biz = self._decode_action_parameter(result["OMD"], param)
                if biz:
                    result["方法参数"] = biz
            # 时间标签 (可选)
            offset = self._parse_time_tag(data, offset, result)

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
                    # 安徽补充规约：方法参数业务解码
                    biz = self._decode_action_parameter(item["OMD"], d)
                    if biz:
                        item["方法参数"] = biz
                items.append(item)
            result["列表"] = items
            # 时间标签 (可选)
            offset = self._parse_time_tag(data, offset, result)

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
            # DAR 为裸 enum 值（表25），非 A-XDR 完整编码
            if offset < len(data):
                dar_val = data[offset]
                offset += 1
                result["结果"] = self._enrich_dar({"类型": "DAR", "原始值": f"0x{dar_val:02X}",
                                                   "解析值": dar_val, "说明": ""})
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
                    # 兼容：DAR 后可能带「数据个数」前缀（福建简化698）或直接 A-XDR
                    resps, consumed = self._parse_axdr_items_or_single(data, offset)
                    offset += consumed
                    if len(resps) == 1:
                        item["响应数据"] = resps[0]
                        eb_biz = self._decode_eb_data_content(item["OMD"], resps[0])
                        if eb_biz:
                            item["数据业务"] = eb_biz
                    else:
                        item["响应数据列表"] = resps
                        if resps:
                            eb_biz = self._decode_eb_data_content(item["OMD"], resps[0])
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
