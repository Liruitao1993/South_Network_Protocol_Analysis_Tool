# -*- coding: utf-8 -*-
"""DLT645 从站应答引擎（纯逻辑）。

输入：完整 645 帧（可含粘包多帧）
输出：0..n 个从站响应帧 bytes

支持：
- 读数据 C=11H：按 DI 查档案 → 正常应答 91H（DI+数据）；未知/无值 → 异常 D1H（ERR 无请求数据）
- 读通信地址 C=13H（DLT645-2007 §7.4，地址域 AA…AA、L=00）：正常应答 93H，
  数据域 = 6 字节表地址线上序（A0..A5，随帧 +33H 加扰）
- 写通信地址 C=15H（§7.5，地址域 AA…AA、数据域 = 新地址 6 字节）：应答 95H
  （地址域 = 新地址，L=00）并把自身地址改为新地址（经 on_address_written 回调同步 UI/档案）
- 广播校时 08H：无应答，静默接收（记 last_error 供日志）
- 其余功能码：异常应答 DnH（n=请求功能码，ERR 无请求数据）
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from dlt645_data_codec import encode_value
from dlt645_frame_gen import DLT645FrameGenerator, encode_addr, encode_di
from dlt645_parser import DLT645Parser

from .archive import DLT645Archive

# ERR：无请求数据 = bit1
ERR_NO_DATA = 0x02

# 读通信地址请求的 DI（数据域为空或无 DI 时特殊处理不在此列）
DI_METER_ADDR = "04000000"


def extract_645_frames(buf: bytes) -> List[Tuple[bytes, bytes]]:
    """从字节流切出完整 645 帧。返回 (frame, remainder) 列表语义：返回全部完整帧。"""
    frames: List[bytes] = []
    i = 0
    n = len(buf)
    while i < n:
        if buf[i] != 0x68:
            i += 1
            continue
        if i + 10 > n:
            break
        # 68 A0..A5 68 C L ...
        if buf[i + 7] != 0x68:
            i += 1
            continue
        length = buf[i + 9]
        total = 10 + length + 2  # 头10 + L + CS + 16
        if i + total > n:
            break
        if buf[i + total - 1] != 0x16:
            i += 1
            continue
        frames.append(bytes(buf[i : i + total]))
        i += total
    return frames


class DLT645MeterSim:
    """DLT645 从站模拟器。"""

    def __init__(
        self,
        address: str = "000000000000",
        archive: Optional[DLT645Archive] = None,
        generator: Optional[DLT645FrameGenerator] = None,
        parser: Optional[DLT645Parser] = None,
        on_address_written=None,
    ):
        self.address = address
        self.archive = archive or DLT645Archive()
        self.gen = generator or DLT645FrameGenerator()
        self.parser = parser or DLT645Parser()
        self.req_count = 0
        self.rsp_count = 0
        self.last_error: Optional[str] = None
        # 15H 写地址成功回调（参数：新地址显示序 hex 字符串）。串口线程内
        # 调用时回调方应经 Signal 跳回 GUI 线程。
        self.on_address_written = on_address_written

    def handle_frame(self, frame: bytes) -> List[bytes]:
        """处理一帧（或粘包多帧），返回响应帧列表。"""
        self.last_error = None
        frames = extract_645_frames(bytes(frame))
        if not frames:
            # 尝试整段当单帧（截断容错交给 parser）
            frames = [bytes(frame)]
        outs: List[bytes] = []
        for fr in frames:
            rsp = self._handle_one(fr)
            if rsp:
                outs.append(rsp)
        return outs

    def _handle_one(self, frame: bytes) -> Optional[bytes]:
        self.req_count += 1
        try:
            parsed = self.parser.parse(frame)
        except Exception as e:
            self.last_error = f"解析失败: {e}"
            return None
        if not parsed or not parsed.get("valid", True):
            # 尽力：仍尝试取 control / data
            pass

        ctrl = parsed.get("control")
        if ctrl is None:
            # 从 fields 或 control_parsed 旁路；parser 输出可能是 int 或 str
            ctrl = parsed.get("控制码")
        if isinstance(ctrl, str):
            try:
                ctrl = int(ctrl, 16) if "x" in ctrl.lower() else int(ctrl)
            except ValueError:
                ctrl = None
        if ctrl is None:
            self.last_error = "无法读取控制码"
            return self._error_response(frame, ERR_NO_DATA)

        func = ctrl & 0x1F
        direction_master = (ctrl & 0x80) == 0
        if not direction_master:
            # 收到从站帧：忽略
            self.last_error = "收到非主站帧，忽略"
            return None

        if func == 0x13:  # 读通信地址（§7.4）
            return self._read_address_response()
        if func == 0x15:  # 写通信地址（§7.5）
            return self._write_address_response(frame)
        if func == 0x08:  # 广播校时：从站不应答
            self.last_error = "广播校时 08H 已接收（无应答）"
            return None
        if func != 0x11:
            self.last_error = f"暂不支持功能码 0x{func:02X}"
            return self._error_response(frame, ERR_NO_DATA, func=func)

        di_code, data_bytes = self._split_read_data(parsed, frame)
        if not di_code:
            return self._error_response(frame, ERR_NO_DATA)

        di_wire = encode_di(di_code)
        value_str = self.archive.get(di_code)
        if value_str is None:
            # 未知 DI → 无请求数据异常
            return self._error_response(frame, ERR_NO_DATA, di_wire=di_wire)

        data_type = self._data_type_for(di_code)
        try:
            value_bytes = encode_value(value_str, data_type or "XXXXXX.XX")
        except Exception as e:
            self.last_error = f"编码值失败 DI={di_code}: {e}"
            return self._error_response(frame, ERR_NO_DATA, di_wire=di_wire)

        # 应答数据域 = DI + 值（均未加扰，交给 build_frame）
        payload = di_wire + value_bytes
        ctrl_out = self.gen.build_control(0x11, dir_bit=1, err=False)
        rsp = self.gen.build_frame(self.address, ctrl_out, payload)
        self.rsp_count += 1
        return rsp

    def _split_read_data(
        self, parsed: dict, frame: bytes
    ) -> Tuple[Optional[str], bytes]:
        """从解析结果或原始帧提取 DI 书写序 hex（8 位）。"""
        # parser 有时给 di_code
        di = parsed.get("di_code") or parsed.get("数据标识 DI")
        if isinstance(di, str) and len(di.replace(" ", "")) >= 8:
            s = di.replace(" ", "").upper()
            # 可能带括号说明
            s = s.split("(")[0].strip()
            if len(s) == 8:
                return s, bytes.fromhex(s)

        # 从原始帧取：位置 10..13 为 DI 线上序（低字节在前），+0x33 后存
        if len(frame) >= 14:
            wire = bytes(frame[10:14])
            # build_frame 对 data 加了 0x33，读请求 DI 也加扰
            raw = bytes((b - 0x33) & 0xFF for b in wire)
            di_text = raw[::-1].hex().upper()
            return di_text, raw
        return None, b""

    def _data_type_for(self, di_code: str) -> Optional[str]:
        try:
            from dlt645_di_lookup import get_dlt645_di_lookup

            lookup = get_dlt645_di_lookup()
            # 尝试 search / get
            for attr in ("get_info", "get", "lookup"):
                fn = getattr(lookup, attr, None)
                if callable(fn):
                    info = fn(di_code)
                    if isinstance(info, dict):
                        dt = info.get("data_type")
                        if dt:
                            return dt
                    if isinstance(info, (tuple, list)) and len(info) >= 4:
                        # (di_code, name, unit, data_type, ...)
                        if info[3]:
                            return info[3]
        except Exception:
            pass
        # 常见 DI 快表
        quick = {
            "00010000": "XXXXXX.XX",
            "00020000": "XXXXXX.XX",
            "02010100": "XXX.X",
            "02020100": "XXX.X",
            "02030100": "XXX.X",
            "02030101": "XX.XXX",
            "02040101": "XX.XXX",
            "02050101": "XX.XXX",
            "04000201": "hhmmss",
        }
        return quick.get(di_code)

    def _read_address_response(self) -> bytes:
        """13H → 93H：数据域 = 表地址 6 字节线上序（build_frame 统一 +33H）。"""
        payload = encode_addr(self.address)
        ctrl_out = self.gen.build_control(0x13, dir_bit=1, err=False)
        rsp = self.gen.build_frame(self.address, ctrl_out, payload)
        self.rsp_count += 1
        return rsp

    def _write_address_response(self, frame: bytes) -> bytes:
        """15H → 95H：数据域 = 新地址 6 字节；改自身地址并回调。"""
        length = frame[9] if len(frame) > 9 else 0
        if length != 6 or len(frame) < 16:
            self.last_error = f"写地址数据域长度非法 L={length:02X}"
            return self._error_response(frame, ERR_NO_DATA, func=0x15)
        wire = bytes((b - 0x33) & 0xFF for b in frame[10:16])  # 去加扰
        new_addr = wire[::-1].hex().upper()  # 线上低字节在前 → 显示序
        self.address = new_addr
        ctrl_out = self.gen.build_control(0x15, dir_bit=1, err=False)
        rsp = self.gen.build_frame(new_addr, ctrl_out, b"")
        self.rsp_count += 1
        if self.on_address_written is not None:
            try:
                self.on_address_written(new_addr)
            except Exception:
                pass
        return rsp

    def _error_response(
        self, request: bytes, err: int, di_wire: Optional[bytes] = None,
        func: int = 0x11,
    ) -> bytes:
        """异常应答 DnH（n=请求功能码，规约：异常帧功能码与请求一致）。

        数据域 = DI(若有) + ERR 字节（未加扰）。
        """
        if di_wire is None and len(request) >= 14:
            di_wire = bytes((b - 0x33) & 0xFF for b in request[10:14])
        payload = (di_wire or b"") + bytes([err & 0xFF])
        ctrl = self.gen.build_control(func, dir_bit=1, err=True)
        return self.gen.build_frame(self.address, ctrl, payload)
