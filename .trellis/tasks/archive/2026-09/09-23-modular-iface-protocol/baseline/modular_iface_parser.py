"""模组化终端功能模块接口协议解析器。

标准：Q/GDW 模组化终端功能模块接口协议（协议文档/12.模组化功能协议/）。

链路层帧：
    68H | 长度域L(2B, LE, bit0~11=数据域长度) | 控制域C(2B, LE)
    | 数据域(L) | FCS(2B, LE) | 16H
整帧长度 = L + 8。

FCS = CRC-16/PPP(x-25)：覆盖长度域+控制域+数据域（不含 68/16/FCS），
init=0xFFFF, xorout=0xF0B8（附录 A，与 698.45 同族）。

控制域低字节：bit7=DIR, bit6=PRM, bit5~0=控制码(00确认/01否认/02信息)；
高字节：帧序号 FID。

应用层 APDU（A-XDR CHOICE 标签）：
    1=LinkRequest  2=GetRequest  3=SetRequest  4=ReportNotification
    129=LinkResponse 130=GetResponse 131=SetResponse 132=ReportResponse
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    import crcmod
except ImportError:  # pragma: no cover
    crcmod = None

try:
    from dl_t698_45_axdr import AXDRCoder
except ImportError:  # pragma: no cover
    AXDRCoder = None

# ── 常量 ──────────────────────────────────────────────────────────

CTRL_FUNC_NAMES = {
    0x00: "确认帧",
    0x01: "否认帧",
    0x02: "信息帧",
}

DIR_PRM_MEANING = {
    (0, 0): "终端对功能模块上报的响应",
    (0, 1): "终端发起的请求",
    (1, 0): "功能模块发起的请求或上报",
    (1, 1): "功能模块对终端请求或通知的响应",
}

# APDU CHOICE 标签（A-XDR 选择标签，1 字节）
APDU_NAMES = {
    1: "LinkRequest 链路协商请求",
    2: "GetRequest 数据读取请求",
    3: "SetRequest 设置请求",
    4: "ReportNotification 上报通知",
    129: "LinkResponse 链路协商响应",
    130: "GetResponse 数据读取响应",
    131: "SetResponse 设置响应",
    132: "ReportResponse 上报通知响应",
}

# 通用 DT（DTA1=0）按 (dta2, dtb) 键（表23 / 附录C）
GENERIC_DT_NAMES = {
    (0, 0): "模块信息",
    (0, 1): "链路协商信息",
    (0, 2): "协议版本",
    (0, 3): "电源状态",
    (0, 4): "文件传输状态",
    (1, 0): "时钟",
    (2, 0): "硬件初始化",
    (2, 1): "参数初始化",
    (2, 2): "数据初始化",
    (2, 3): "文件传输",
}

# 附录C 模块信息 structure 固定 7 成员（A-XDR 依次命名）
MODULE_INFO_FIELDS = (
    "模块设备型号",
    "模块设备ID",
    "软件版本",
    "软件发布日期",
    "硬件版本",
    "硬件发布日期",
    "厂商编码",
)

POWER_STATE_NAMES = {0: "上电", 1: "掉电"}

DTA1_MODULE_NAMES = {
    0: "通用",
    1: "远程通信模块",
    2: "本地通信模块",
    3: "RS-485模块",
    4: "遥信脉冲模块",
    5: "CAN通信",
    6: "M-Bus模块",
    7: "控制模块",
    8: "模拟量采集",
    9: "回路状态巡检",
}

DTA2_RW = {
    0: "只读",
    1: "读/写",
    2: "只写",
}

# Get-Result / DAR 简表（通用错误码；模块专有见附录）
DAR_NAMES = {
    0: "成功",
    1: "硬件故障",
    2: "暂时故障",
    3: "拒绝读取",
    4: "类型不匹配",
    5: "对象不存在",
    6: "对象表忙",
    7: "对象不可写",
    8: "不定长数据超长",
    9: "数据过量",
    10: "参数过量",
    11: "内嵌数据类型不匹配",
    12: "其他原因",
    13: "DLMS安全",
    14: "引用仲裁失败",
    15: "拒绝配置",
    16: "不应答",
    17: "未定义",
    18: "调度失败",
    19: "目标对象不存在",
    20: "未知组地址",
    21: "与安全集合不匹配",
}

APDU_TYPE_NAMES = {
    "link_req": "链路协商请求",
    "get_req": "数据读取请求",
    "set_req": "设置请求",
    "report_ntf": "上报通知",
    "link_rsp": "链路协商响应",
    "get_rsp": "数据读取响应",
    "set_rsp": "设置响应",
    "report_rsp": "上报通知响应",
    "ack": "确认帧",
    "nak": "否认帧",
}

# 与 698 同族的 x-25（PPP FCS-16），附录 A
_fcs16 = None
if crcmod is not None:
    try:
        _fcs16 = crcmod.predefined.mkCrcFun("x-25")
    except ValueError:
        _fcs16 = None


def calc_fcs(payload: bytes) -> int:
    """FCS-16（附录 A / PPP）：覆盖 length+control+data，返回 16 位。"""
    if _fcs16 is not None:
        return _fcs16(payload)
    # 表驱动回退（fcstab 首若干项已见文档；完整表用 bit 算法）
    fcs = 0xFFFF
    for b in payload:
        fcs ^= b
        for _ in range(8):
            if fcs & 1:
                fcs = (fcs >> 1) ^ 0x8408
            else:
                fcs >>= 1
    return (fcs ^ 0xF0B8) & 0xFFFF


def data_total_len(data_bytes: bytes) -> int:
    """从长度域推算整帧长度（L=数据域字节数 → 整帧 = L+8）。"""
    if len(data_bytes) < 3:
        return 0
    if data_bytes[0] != 0x68:
        return 0
    l_val = data_bytes[1] | (data_bytes[2] << 8)
    data_len = l_val & 0x0FFF
    total = data_len + 8
    if total < 8 or total > 8192:
        return 0
    return total


def decode_dt(raw: bytes) -> Tuple[int, int, int, str]:
    """信息类标识 DT（2B LE）→ (DTA1, DTA2, DTB, 说明)。

    16 位：bit15~11=DTA1, bit10~8=DTA2, bit7~0=DTB；线上低字节在前。
    """
    if len(raw) < 2:
        return 0, 0, 0, "DT 长度不足"
    val = raw[0] | (raw[1] << 8)
    dta1 = (val >> 11) & 0x1F
    dta2 = (val >> 8) & 0x07
    dtb = val & 0xFF
    parts = [f"DTA1={dta1:X}H({DTA1_MODULE_NAMES.get(dta1, '保留')})"]
    parts.append(f"DTA2={dta2:X}H({DTA2_RW.get(dta2, '保留')})")
    # 通用信息类（表23）键为 (dta2, dtb)，仅 DTA1=0
    gname = GENERIC_DT_NAMES.get((dta2, dtb)) if dta1 == 0 else None
    if gname:
        parts.append(f"DTB={dtb:02X}H({gname})")
    else:
        parts.append(f"DTB={dtb:02X}H")
    return dta1, dta2, dtb, "，".join(parts)


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


class ModularIfaceParser:
    """模组化终端功能模块接口协议解析 → 表格行列表。

    返回与其它 parser 一致的 list[tuple] 行，供 GUI / 串口工具 format_parse_rows 使用。
    """

    name = "模组化接口"

    def parse(self, frame: bytes) -> List[tuple]:
        rows: List[tuple] = []
        data = bytes(frame)
        if len(data) < 8 or data[0] != 0x68:
            return self._rows(
                rows,
                ("起始字符", "-", "错误" if data else "-", "需要至少8字节且68H起头", 0, 0),
            )

        # 起始
        rows.append(("起始字符", "68", "68H", "帧起始标志", 0, 0))

        # 长度域
        l_raw = data[1] | (data[2] << 8)
        data_len = l_raw & 0x0FFF
        rows.append(
            (
                "长度域",
                f"{data[1]:02X} {data[2]:02X}",
                str(data_len),
                f"bit0~11=数据域{data_len}字节（整帧={data_len + 8}），LE，bit12~15保留",
                1,
                2,
            )
        )

        total = data_len + 8
        if len(data) < total:
            rows.append(
                (
                    "⚠ 帧不完整",
                    str(len(data)),
                    f"需要{total}字节",
                    f"长度域要求数据域{data_len}字节，整帧{total}",
                    0,
                    len(data) - 1,
                )
            )
            return self._rows(rows, None)

        # 控制域 2B
        c0, c1 = data[3], data[4]
        dir_bit = (c0 >> 7) & 1
        prm_bit = (c0 >> 6) & 1
        func = c0 & 0x3F
        fid = c1
        rows.append(
            (
                "控制域",
                f"{c0:02X} {c1:02X}",
                f"DIR={dir_bit} PRM={prm_bit} 控制码={func:02X}H FID={fid}",
                DIR_PRM_MEANING.get((dir_bit, prm_bit), ""),
                3,
                4,
            )
        )
        rows.append(
            (
                "  传输方向(DIR)",
                f"0x{c0:02X}",
                str(dir_bit),
                "0=终端发出，1=功能模块发出",
                3,
                3,
            )
        )
        rows.append(
            (
                "  启动标志(PRM)",
                f"0x{c0:02X}",
                str(prm_bit),
                "0=模块发起，1=终端发起",
                3,
                3,
            )
        )
        rows.append(
            (
                "  控制码",
                f"0x{func:02X}",
                CTRL_FUNC_NAMES.get(func, f"保留({func})"),
                "00H确认 01H否认 02H信息",
                3,
                3,
            )
        )
        rows.append(("  帧序号(FID)", f"0x{c1:02X}", str(fid), "循环0~255，响应与请求一致", 4, 4))

        # 数据域
        payload = data[5 : 5 + data_len]
        fcs_off = 5 + data_len
        fcs_wire = data[fcs_off] | (data[fcs_off + 1] << 8)
        fcs_calc = calc_fcs(data[1:fcs_off])
        rows.append(
            (
                "数据域",
                _hex(payload) if payload else "-",
                f"{data_len}字节",
                "",
                5,
                5 + data_len - 1 if data_len else 5,
            )
        )

        # FCS
        fcs_ok = fcs_wire == fcs_calc
        rows.append(
            (
                "帧校验(FCS)",
                f"{data[fcs_off]:02X} {data[fcs_off + 1]:02X}",
                f"0x{fcs_wire:04X}",
                f"期望0x{fcs_calc:04X} {'校验正确' if fcs_ok else '校验错误'}（CRC-16/PPP，覆盖L+C+Data）",
                fcs_off,
                fcs_off + 1,
            )
        )
        rows.append(("结束字符", f"{data[fcs_off + 2]:02X}", "16H", "帧结束标志", fcs_off + 2, fcs_off + 2))

        # 按控制码分派数据域
        if func == 0x00:
            pass  # 确认：无数据
        elif func == 0x01:
            if len(payload) >= 2:
                err = payload[0] | (payload[1] << 8)
                rows.append(
                    (
                        "错误信息码",
                        f"{payload[0]:02X} {payload[1]:02X}",
                        str(err),
                        "BIN 2字节",
                        5,
                        6,
                    )
                )
        elif func == 0x02:
            rows.extend(self._parse_apdu(payload, base=5))
        else:
            rows.append(("控制码", f"0x{func:02X}", "保留", "非确认/否认/信息", 3, 3))

        return self._rows(
            rows,
            {
                "valid": bool(fcs_ok) and data[0] == 0x68 and data[-1] == 0x16,
                "fcs_ok": fcs_ok,
            } if False else None,
        )

    def _rows(self, rows, _meta=None):
        return rows

    def parse_to_table(self, frame: bytes) -> List[tuple]:
        """GUI 兼容入口：返回表格行；并在首行附带摘要信息行由调用方组摘要。"""
        return self.parse(frame)

    def get_summary(self, frame: bytes) -> str:
        """批量/单帧摘要：方向 | 控制码 | APDU | DT。"""
        data = bytes(frame)
        if len(data) < 8 or data[0] != 0x68:
            return "无效帧"
        data_len = (data[1] | (data[2] << 8)) & 0x0FFF
        c0 = data[3]
        dir_bit = (c0 >> 7) & 1
        func = c0 & 0x3F
        fid = data[4]
        direction = "模块→终端" if dir_bit else "终端→模块"
        ctrl = CTRL_FUNC_NAMES.get(func, f"控制码{func:02X}H")
        parts = [f"{direction}", ctrl, f"FID={fid}"]
        payload = data[5 : 5 + data_len]
        if func == 0x02 and payload:
            apdu_tag = payload[0]
            apdu = APDU_NAMES.get(apdu_tag, f"APDU[{apdu_tag}]")
            parts.append(apdu)
            # Get/Set 的 DT
            if apdu_tag in (2, 3, 130, 131) and len(payload) >= 3:
                # GetRequest: tag + DT；GetResponse: tag + DT + result...
                # 对 GetRequest 标签后紧跟 DT
                dt_off = 1 if apdu_tag in (2, 3) else None
                if apdu_tag in (130, 131) or apdu_tag == 4:
                    dt_off = 1  # A-ResultNormal 先 DT
                if apdu_tag == 3:
                    dt_off = 1
                if dt_off is not None and len(payload) >= dt_off + 2:
                    if apdu_tag in (2, 3, 130, 131, 4):
                        _a, _b, _c, dt_desc = decode_dt(payload[dt_off : dt_off + 2])
                        parts.append(dt_desc)
            elif apdu_tag == 1 and len(payload) >= 3:
                ver = payload[1] | (payload[2] << 8)
                parts.append(f"版本={ver}")
            elif apdu_tag == 129 and len(payload) >= 3:
                ver = payload[1] | (payload[2] << 8)
                parts.append(f"版本={ver}")
        elif func == 0x01 and len(payload) >= 2:
            err = payload[0] | (payload[1] << 8)
            parts.append(f"错误码={err}")
        elif func == 0x00:
            parts.append("ACK")
        return " | ".join(parts)

    # ── APDU ──────────────────────────────────────────────────────

    def _parse_apdu(self, payload: bytes, base: int) -> List[tuple]:
        rows: List[tuple] = []
        if not payload:
            rows.append(("APDU", "-", "空", "信息帧无数据域", base, base))
            return rows
        tag = payload[0]
        name = APDU_NAMES.get(tag, f"未知APDU({tag})")
        rows.append(
            (
                "应用层数据单元(APDU)",
                f"0x{tag:02X}",
                name,
                "A-XDR CHOICE 标签",
                base,
                base,
            )
        )
        body = payload[1:]
        if tag == 1:
            rows.extend(self._parse_link_request(body, base + 1))
        elif tag == 2:
            rows.extend(self._parse_get_request(body, base + 1))
        elif tag == 3:
            rows.extend(self._parse_set_request(body, base + 1))
        elif tag == 4:
            rows.extend(self._parse_report_notification(body, base + 1))
        elif tag == 129:
            rows.extend(self._parse_link_response(body, base + 1))
        elif tag == 130:
            rows.extend(self._parse_get_response(body, base + 1))
        elif tag == 131:
            rows.extend(self._parse_set_response(body, base + 1))
        elif tag == 132:
            rows.extend(self._parse_report_response(body, base + 1))
        else:
            rows.append(
                (
                    "APDU数据",
                    _hex(body),
                    f"{len(body)}字节",
                    "未识别的 CHOICE 标签",
                    base + 1,
                    base + len(payload) - 1,
                )
            )
        return rows

    @staticmethod
    def _take_axdr_uint(data: bytes, off: int, n: int = 2) -> Tuple[Optional[int], int]:
        """读 A-XDR long-unsigned/unsigned（tag 0x12/0x11 + BER len + 大端值）。"""
        if off >= len(data):
            return None, 0
        tag = data[off]
        if tag not in (0x11, 0x12, 0x06):
            return None, 0
        if off + 1 >= len(data):
            return None, 0
        ln = data[off + 1]
        if ln == 0 or off + 2 + ln > len(data):
            return None, 0
        val = int.from_bytes(data[off + 2 : off + 2 + ln], "big")
        return val, 2 + ln

    @staticmethod
    def _take_axdr_string(data: bytes, off: int, tags=(0x0A, 0x09, 0x0C)) -> Tuple[Optional[bytes], int]:
        if off >= len(data) or data[off] not in tags:
            return None, 0
        if off + 1 >= len(data):
            return None, 0
        ln = data[off + 1]
        if off + 2 + ln > len(data):
            return None, 0
        return data[off + 2 : off + 2 + ln], 2 + ln

    def _parse_link_request(self, b: bytes, base: int) -> List[tuple]:
        rows = []
        off = 0
        ver, n = self._take_axdr_uint(b, off)
        if n:
            rows.append(("协议版本号", f"0x{ver:04X}" if ver is not None else "-", str(ver), "long-unsigned", base + off, base + off + n - 1))
            off += n
        model, n = self._take_axdr_string(b, off)
        if n and model is not None:
            rows.append(("终端设备型号", _hex(model), model.decode("ascii", "replace"), "visible-string", base + off, base + off + n - 1))
            off += n
        dev_id, n = self._take_axdr_string(b, off)
        if n and dev_id is not None:
            rows.append(("终端设备ID", _hex(dev_id), dev_id.decode("ascii", "replace"), "visible-string", base + off, base + off + n - 1))
            off += n
        max_tx, n = self._take_axdr_uint(b, off)
        if n:
            rows.append(("最大发送缓冲区", f"0x{max_tx:04X}" if max_tx is not None else "-", str(max_tx), "字节", base + off, base + off + n - 1))
            off += n
        max_rx, n = self._take_axdr_uint(b, off)
        if n:
            rows.append(("最大接收缓冲区", f"0x{max_rx:04X}" if max_rx is not None else "-", str(max_rx), "字节", base + off, base + off + n - 1))
            off += n
        win, n = self._take_axdr_uint(b, off, 1)
        if n:
            rows.append(("并发传输窗口数", f"0x{win:02X}" if win is not None else "-", str(win), "unsigned", base + off, base + off + n - 1))
            off += n
        if off < len(b):
            rows.append(("LinkRequest剩余", _hex(b[off:]), "", "未解析尾部", base + off, base + len(b) - 1))
        elif not rows:
            rows.append(("LinkRequest", _hex(b), "", "字段未按 A-XDR 解出", base, base + len(b) - 1))
        return rows

    def _parse_link_response(self, b: bytes, base: int) -> List[tuple]:
        rows = self._parse_link_request_fields(b, base, is_response=True)
        # 虚拟通道 SEQUENCE OF：追加剩余为原始
        return rows

    def _parse_link_request_fields(self, b: bytes, base: int, is_response: bool = False) -> List[tuple]:
        rows = []
        off = 0
        ver, n = self._take_axdr_uint(b, off)
        if n:
            rows.append(("协议版本号", f"0x{ver:04X}" if ver is not None else "-", str(ver), "", base, base + n - 1))
            off += n
        who = "功能模块设备型号" if is_response else "终端设备型号"
        model, n = self._take_axdr_string(b, off)
        if n and model is not None:
            rows.append((who, _hex(model), model.decode("ascii", "replace"), "", base + off, base + off + n - 1))
            off += n
        who = "功能模块设备ID" if is_response else "终端设备ID"
        dev_id, n = self._take_axdr_string(b, off)
        if n and dev_id is not None:
            rows.append((who, _hex(dev_id), dev_id.decode("ascii", "replace"), "", base + off, base + off + n - 1))
            off += n
        max_tx, n = self._take_axdr_uint(b, off)
        if n:
            rows.append(("最大发送缓冲区", str(max_tx), str(max_tx), "字节", base + off, base + off + n - 1))
            off += n
        max_rx, n = self._take_axdr_uint(b, off)
        if n:
            rows.append(("最大接收缓冲区", str(max_rx), str(max_rx), "字节", base + off, base + off + n - 1))
            off += n
        win, n = self._take_axdr_uint(b, off, 1)
        if n:
            rows.append(("并发传输窗口数", str(win), str(win), "", base + off, base + off + n - 1))
            off += n
        if off < len(b):
            if is_response:
                rows.append(
                    (
                        "虚拟通道工作模式",
                        _hex(b[off:]),
                        f"{len(b) - off}字节",
                        "SEQUENCE OF {接口类型, 功能配置}，见表18",
                        base + off,
                        base + len(b) - 1,
                    )
                )
            else:
                rows.append(("剩余", _hex(b[off:]), "", "", base + off, base + len(b) - 1))
        if not rows:
            rows.append(("字段", _hex(b), "", "A-XDR 字段未命中", base, base + max(0, len(b) - 1)))
        return rows

    def _parse_get_request(self, b: bytes, base: int) -> List[tuple]:
        rows = []
        if len(b) < 2:
            rows.append(("GetRequest", _hex(b), "数据不足", "需要信息类标识 DT(2B)", base, base + max(0, len(b) - 1)))
            return rows
        rows.append(self._dt_row(b[0:2], base, "信息类标识"))
        return rows

    def _parse_set_request(self, b: bytes, base: int) -> List[tuple]:
        rows = []
        if len(b) < 2:
            rows.append(("SetRequest", _hex(b), "数据不足", "需要 DT+Data", base, base + max(0, len(b) - 1)))
            return rows
        rows.append(self._dt_row(b[0:2], base, "信息类标识"))
        if len(b) > 2:
            rows.extend(self._decode_data_section(b[0:2], b[2:], base + 2, "数据(Data)"))
        return rows

    def _parse_report_notification(self, b: bytes, base: int) -> List[tuple]:
        rows = []
        if len(b) < 2:
            rows.append(("ReportNotification", _hex(b), "数据不足", "需要 DT+Data", base, base + max(0, len(b) - 1)))
            return rows
        rows.append(self._dt_row(b[0:2], base, "信息类标识"))
        if len(b) > 2:
            rows.extend(self._decode_data_section(b[0:2], b[2:], base + 2, "数据(Data)"))
        return rows

    def _parse_get_response(self, b: bytes, base: int) -> List[tuple]:
        rows = []
        if len(b) < 2:
            rows.append(("GetResponse", _hex(b), "数据不足", "需要 A-ResultNormal", base, base + max(0, len(b) - 1)))
            return rows
        rows.append(self._dt_row(b[0:2], base, "信息类标识"))
        # Get-Result CHOICE: [0] DAR tag=0x00? A-XDR context tag for [0] is 0x80 in BER;
        # 本项目 A-XDR 常用 0x00 空/或 context。看 698：choice 用 0/1 直接 tag。
        # 文档 Get-Result CHOICE { [0] DAR, [1] Data } —— A-XDR 选择标签 0 或 1 后跟内容。
        if len(b) >= 3:
            sel = b[2]
            if sel == 0 and len(b) >= 4:
                # DAR 可能为 enum (0x16) 或直接 unsigned
                if b[3] == 0x16 and len(b) >= 5:
                    dar = b[4]
                    rows.append(
                        (
                            "错误信息(DAR)",
                            f"0x{dar:02X}",
                            DAR_NAMES.get(dar, str(dar)),
                            "Get-Result=[0] DAR",
                            base + 2,
                            base + len(b) - 1,
                        )
                    )
                else:
                    rows.append(
                        (
                            "错误信息(DAR)",
                            _hex(b[3:]),
                            "",
                            "Get-Result=[0]",
                            base + 3,
                            base + len(b) - 1,
                        )
                    )
            elif sel == 1:
                rows.extend(
                    self._decode_data_section(b[0:2], b[3:], base + 3, "读取结果(Data)")
                )
            else:
                rows.extend(
                    self._decode_data_section(b[0:2], b[2:], base + 2, "读取结果")
                )
        return rows

    def _decode_data_section(
        self, dt_raw: bytes, data: bytes, base: int, label: str
    ) -> List[tuple]:
        """按信息类标识深度解码 Data：已知结构优先，失败回落通用 A-XDR。"""
        if not data:
            return [(label, "-", "空", "无数据域", base, base)]
        rows: List[tuple] = [
            (label, _hex(data), f"{len(data)}字节", "A-XDR Data", base, base + len(data) - 1)
        ]
        dta1, dta2, dtb, _ = decode_dt(dt_raw)
        if dta1 == 0 and dta2 == 0 and dtb == 0x00:
            rows.extend(self._decode_module_info(data, base))
            return rows
        if dta1 == 0 and dta2 == 0 and dtb == 0x02:
            ver, n = self._take_axdr_uint(data, 0)
            if n:
                rows.append(
                    ("协议版本", str(ver), str(ver), "long-unsigned", base, base + n - 1)
                )
                return rows
        if dta1 == 0 and dta2 == 0 and dtb == 0x03:
            if data and data[0] == 0x16 and len(data) >= 2:
                st = data[1]
                rows.append(
                    (
                        "电源状态",
                        f"0x{st:02X}",
                        POWER_STATE_NAMES.get(st, str(st)),
                        "enum",
                        base,
                        base + 1,
                    )
                )
                return rows
        rows.extend(self._decode_axdr_rows(data, base, "Data"))
        return rows

    def _decode_module_info(self, data: bytes, base: int) -> List[tuple]:
        """附录C DT=0000 模块信息 structure：型号/ID/软硬件版本与日期/厂商。

        手写按字段类型遍历（不整棵调 AXDR structure，避免 date 解码长度偏差导致越界）。
        date 约定：`1A 05 + 5字节`，5 字节按 A-XDR date 的 year(2B LE)+month+day+clock。
        """
        rows: List[tuple] = []
        pos = 0
        if data and data[0] == 0x02:
            if data[1] < 0x80:
                pos = 2
            elif data[1] == 0x80:
                pos = 2
            else:
                pos = 2 + (data[1] & 0x7F)

        def take_date(off: int) -> Tuple[Optional[str], int]:
            if off >= len(data) or data[off] != 0x1A:
                return None, 0
            if off + 1 >= len(data):
                return None, 0
            ln = data[off + 1]
            if ln < 0x80:
                need = 1 + 1 + ln
            else:
                nb = ln & 0x7F
                if off + 2 + nb > len(data):
                    return None, 0
                ln = int.from_bytes(data[off + 2 : off + 2 + nb], "big")
                need = 2 + nb + ln
                off_val = off + 2 + nb
            if ln < 0x80:
                off_val = off + 2
                payload = data[off_val : off_val + ln] if ln < 0x80 else b""
            else:
                payload = data[off_val : off_val + ln]
            if len(payload) < 5:
                return None, 0
            # year 2B LE + month + day + 周/时字段（与 698 date 解码一致）
            year = int.from_bytes(payload[0:2], "little")
            month, day = payload[2], payload[3]
            extra = payload[4]
            # 若 year 看起来像「年两位 0~99」而 high 字节=0，按 20xx 显示更直观
            date_s = f"{year}-{month:02d}-{day:02d}"
            if year < 100:
                date_s = f"{2000 + year:04d}-{month:02d}-{day:02d}"
            if extra not in (0, 0xFF) and 0 <= extra <= 6:
                date_s += f" 周{extra}"
            return date_s, need

        for name in MODULE_INFO_FIELDS:
            if pos >= len(data):
                break
            tag = data[pos]
            if tag in (0x0A, 0x09, 0x0C):
                raw, n = self._take_axdr_string(data, pos)
                if not n or raw is None:
                    rows.append((f"    {name}", _hex(data[pos:]), "字符串解码失败", "", base + pos, base + len(data) - 1))
                    break
                text = raw.decode("ascii", "replace")
                rows.append((f"    {name}", _hex(raw), text, "visible-string", base + pos, base + pos + n - 1))
                pos += n
                continue
            if tag == 0x06:
                # double-long-unsigned：06 + len + value
                if pos + 2 < len(data) and data[pos + 1] <= 4:
                    ln = data[pos + 1]
                    val = int.from_bytes(data[pos + 2 : pos + 2 + ln], "big") if ln else 0
                    n = 2 + ln
                    rows.append((f"    {name}", _hex(data[pos : pos + n]), str(val), "double-long-unsigned", base + pos, base + pos + n - 1))
                    pos += n
                    continue
            if tag == 0x12:
                ver, n = self._take_axdr_uint(data, pos)
                if n:
                    rows.append((f"    {name}", _hex(data[pos : pos + n]), str(ver), "long-unsigned", base + pos, base + pos + n - 1))
                    pos += n
                    continue
            if tag == 0x1A:
                ds, n = take_date(pos)
                if n and ds is not None:
                    rows.append((f"    {name}", _hex(data[pos : pos + n]), ds, "date", base + pos, base + pos + n - 1))
                    pos += n
                    continue
            # 未知标签：停
            rows.append((f"    {name}", _hex(data[pos:]), "未知标签", f"tag=0x{tag:02X}", base + pos, base + len(data) - 1))
            break
        if pos < len(data) and rows and "未知标签" not in str(rows[-1][3]):
            # 剩余（若还有字节且上面没报错）
            if not (rows and rows[-1][0] == "    模块信息剩余"):
                rem = data[pos:]
                if rem:
                    rows.append(("    模块信息剩余", _hex(rem), f"{len(rem)}字节", "", base + pos, base + len(data) - 1))
        return rows

    def _decode_axdr_rows(self, data: bytes, base: int, prefix: str) -> List[tuple]:
        if AXDRCoder is None:
            return []
        rows: List[tuple] = []
        try:
            item, consumed = AXDRCoder().decode(data, 0)
        except Exception as exc:
            return [
                (
                    f"{prefix}解码",
                    _hex(data),
                    f"失败: {exc}",
                    "A-XDR",
                    base,
                    base + max(0, len(data) - 1),
                )
            ]
        typ = str(item.get("类型") or item.get("tag_name") or "")
        raw = str(
            item.get("原始编码") or item.get("原始值") or data[:consumed].hex().upper()
        )
        if typ == "structure" and isinstance(item.get("解析值"), list):
            for i, mem in enumerate(item["解析值"]):
                mraw = str(mem.get("原始编码") or mem.get("原始值") or "")
                mval = mem.get("解析值")
                mtyp = str(mem.get("类型") or mem.get("tag_name") or "")
                if isinstance(mval, list) and mval and isinstance(mval[0], dict):
                    for j, sub in enumerate(mval):
                        rows.append(
                            (
                                f"    {prefix}.{i + 1}.{j + 1}",
                                str(sub.get("原始编码") or sub.get("原始值") or ""),
                                str(sub.get("解析值", "")),
                                str(sub.get("类型") or sub.get("tag_name") or ""),
                                base,
                                base + max(0, consumed - 1),
                            )
                        )
                else:
                    rows.append(
                        (
                            f"    {prefix}.{i + 1}",
                            mraw,
                            str(mval) if not isinstance(mval, list) else f"{len(mval)}项",
                            mtyp,
                            base,
                            base + max(0, consumed - 1),
                        )
                    )
        else:
            rows.append(
                (
                    prefix,
                    raw,
                    str(item.get("解析值", "")),
                    typ or "A-XDR",
                    base,
                    base + max(0, consumed - 1),
                )
            )
        if consumed < len(data):
            rows.append(
                (
                    f"{prefix}剩余",
                    _hex(data[consumed:]),
                    f"{len(data) - consumed}字节",
                    "未消费尾部",
                    base + consumed,
                    base + len(data) - 1,
                )
            )
        return rows

    def _parse_set_response(self, b: bytes, base: int) -> List[tuple]:
        rows = []
        if len(b) < 2:
            rows.append(("SetResponse", _hex(b), "数据不足", "需要 DT+DAR", base, base + max(0, len(b) - 1)))
            return rows
        rows.append(self._dt_row(b[0:2], base, "信息类标识"))
        if len(b) >= 3:
            if b[2] == 0x16 and len(b) >= 4:
                dar = b[3]
                rows.append(
                    (
                        "设置结果(DAR)",
                        f"0x{dar:02X}",
                        DAR_NAMES.get(dar, str(dar)),
                        "",
                        base + 2,
                        base + len(b) - 1,
                    )
                )
            else:
                rows.append(("设置结果", _hex(b[2:]), "", "DAR", base + 2, base + len(b) - 1))
        return rows

    def _parse_report_response(self, b: bytes, base: int) -> List[tuple]:
        if len(b) >= 2:
            return [self._dt_row(b[0:2], base, "对应上报信息类标识")]
        return [("ReportResponse", _hex(b), "数据不足", "需要 DT", base, base)]

    def _dt_row(self, raw: bytes, base: int, name: str) -> tuple:
        dta1, dta2, dtb, desc = decode_dt(raw)
        return (name, _hex(raw), f"0x{raw[0]:02X}{raw[1]:02X}", desc, base, base + 1)

    @staticmethod
    def is_frame(data: bytes) -> bool:
        if len(data) < 8 or data[0] != 0x68 or data[-1] != 0x16:
            return False
        need = data_total_len(data)
        return need > 0 and len(data) == need
