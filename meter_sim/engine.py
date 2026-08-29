# -*- coding: utf-8 -*-
"""MeterSimEngine：698.45 请求帧 → 响应帧（纯逻辑，不依赖 Qt）。"""
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from . import dynamic_data as dyn
from .archive import Archive
from .link_layer import is_wildcard_sa, parse_header
from .response_builder import (
    DAR_OBJECT_UNDEFINED, assemble_link_frame, build_get_response_normal,
    build_get_response_normal_list, build_get_response_record,
    build_link_response, build_set_action_response, wrap_security_plain_mac,
)


@dataclass
class SimOptions:
    meter_count: int = 3            # 通配地址模拟表数量
    blacklist: List[str] = field(default_factory=list)   # SA 反转 hex 串
    whitelist: List[str] = field(default_factory=list)
    energy_increase: bool = False   # 正向有功电能随运行时间递增
    auto_freeze_time: bool = True   # 日/月/曲线冻结自动时标
    leak_window: Optional[Tuple[int, int]] = None  # 曲线漏点时段 (起分, 止分)
    mac_enabled: bool = True        # 明文回复附加 MAC
    meter_no_base: Optional[int] = None  # 通配表号起始（None 取档案 40020200）


# OAD 常量
OAD_CURRENT_TIME = bytes.fromhex("40000200")
OAD_COMM_ADDR = {bytes.fromhex(s) for s in ("40010200", "40020200", "202a0200")}
OAD_ENERGY_FWD = bytes.fromhex("00100200")


class MeterSimEngine:
    """虚拟表引擎。handle_frame 返回 0..n 个链路响应帧。"""

    def __init__(self, archive: Archive, options: Optional[SimOptions] = None):
        self.archive = archive
        self.options = options or SimOptions()
        self.start_time = time.time()
        self.logs: List[str] = []

    def _log(self, msg: str):
        self.logs.append(msg)

    # ── 数据查询 ──────────────────────────────────────────
    def _meter_no(self, archive_no: int, k: int) -> int:
        base = self.options.meter_no_base if self.options.meter_no_base is not None else archive_no
        return base + k

    def _archive_meter_no(self) -> int:
        item = self.archive.lookup_key("40020200") or self.archive.lookup_key("202a0200")
        if item:
            return dyn.meter_number_from_archive(item["data"])
        return 0

    def _fetch_data(self, oad: bytes, meter_no: int) -> Optional[bytes]:
        """按 OAD 取属性数据（动态优先，其次档案）。未知 OAD 返回 None。"""
        oi = oad[0:2].hex()
        attr, idx = oad[2], oad[3]
        # 当前日期时间
        if oad == OAD_CURRENT_TIME:
            return dyn.current_time_data()
        # 通信地址 / 表号
        if oad in OAD_COMM_ADDR:
            return dyn.comm_address_data(meter_no)
        # 正向有功电能递增
        if oad == OAD_ENERGY_FWD and self.options.energy_increase:
            item = self.archive.lookup_key("00100200")
            if item:
                elapsed = int(time.time() - self.start_time)
                return bytes.fromhex(
                    dyn.increase_energy(item["data"], elapsed))
        item = self.archive.lookup(oi, f"{attr:02x}", f"{idx:02x}")
        if item:
            try:
                return bytes.fromhex(item["data"])
            except ValueError:
                self._log(f"档案数据非法 hex: {item['key']}")
        return None

    # ── APDU 处理 ─────────────────────────────────────────
    def _handle_apdu(self, apdu: bytes, meter_no: int) -> Optional[bytes]:
        if len(apdu) < 2:
            return None
        svc = apdu[0]
        # 链接管理
        if svc in (0x01, 0x02):
            piid = apdu[1] if len(apdu) > 1 else 0
            self._log(f"链接请求 0x{svc:02X} → 链接响应")
            return build_link_response(0x80 | svc, piid)
        # GET
        if svc == 0x05 and len(apdu) >= 3:
            return self._handle_get(apdu, meter_no)
        # SET / ACTION：回成功 DAR（只读模拟，不改档案）
        if svc in (0x06, 0x07) and len(apdu) >= 3:
            detail, piid = apdu[1], apdu[2]
            oads = []
            if detail == 0x01 and len(apdu) >= 7:
                oads = [apdu[3:7]]
            elif detail == 0x02 and len(apdu) >= 4:
                count = apdu[3]
                oads = [apdu[4 + 4 * i:8 + 4 * i] for i in range(count)]
            name = "SET" if svc == 0x06 else "ACTION"
            self._log(f"{name} 请求 detail=0x{detail:02X} → 成功 DAR")
            return build_set_action_response(0x80 | svc, piid, oads)
        self._log(f"不支持的 APDU 服务 0x{svc:02X}，忽略")
        return None

    def _handle_get(self, apdu: bytes, meter_no: int) -> Optional[bytes]:
        detail, piid = apdu[1], apdu[2]
        # GetRequestNormal
        if detail == 0x01 and len(apdu) >= 7:
            oad = apdu[3:7]
            data = self._fetch_data(oad, meter_no)
            name = self._oad_name(oad)
            if data is None:
                self._log(f"GET Normal {oad.hex()}({name}) → 对象不存在")
                return build_get_response_normal(piid, oad, None,
                                                 DAR_OBJECT_UNDEFINED)
            self._log(f"GET Normal {oad.hex()}({name}) → 数据 {len(data)}B")
            return build_get_response_normal(piid, oad, data)
        # GetRequestNormalList
        if detail == 0x02 and len(apdu) >= 4:
            count = apdu[3]
            items = []
            for i in range(count):
                oad = apdu[4 + 4 * i:8 + 4 * i]
                data = self._fetch_data(oad, meter_no)
                if data is None:
                    items.append((oad, None, DAR_OBJECT_UNDEFINED))
                else:
                    items.append((oad, data, None))
            self._log(f"GET NormalList {count} 项")
            return build_get_response_normal_list(piid, items)
        # GetRequestRecord
        if detail == 0x03 and len(apdu) >= 8:
            return self._handle_get_record(apdu, piid, meter_no)
        self._log(f"GET detail=0x{detail:02X} 暂不支持")
        return None

    def _parse_rsd_rcsd(self, apdu: bytes) -> Tuple[Optional[bytes], List[bytes]]:
        """解析 Record 请求的 RSD/RCSD。返回 (RSD 时间戳 1c+7B 或 None, 列 OAD 列表)。"""
        selector = apdu[7]
        rsd_ts = None
        if selector == 0x01:
            # 01 + OAD(4) + 1c + 7B
            if len(apdu) >= 20 and apdu[13] == 0x1C:
                rsd_ts = apdu[13:20]
            rcsd = apdu[20:]
        elif selector == 0x02:
            # 01 + OAD(4) + 1c+7 + (间隔 TI 等) + 第二个时间 1c+7
            # 第二个时间锚点：apdu[29] 起（按开源 reMessage[8]）
            if len(apdu) >= 36 and apdu[29] == 0x1C:
                rsd_ts = apdu[29:36]
            rcsd = apdu[36:]
        elif selector == 0x09:
            rcsd = apdu[9:]
        else:
            rcsd = apdu[8:]
        # RCSD: count + CSD 序列
        cols: List[bytes] = []
        if rcsd:
            count = rcsd[0]
            p = 1
            for _ in range(count):
                if p + 5 > len(rcsd):
                    break
                if rcsd[p] == 0x00:  # CSD CHOICE OAD
                    cols.append(rcsd[p + 1:p + 5])
                    p += 5
                else:
                    break  # ROAD 等其他选择暂不支持
        return rsd_ts, cols

    def _handle_get_record(self, apdu: bytes, piid: int,
                           meter_no: int) -> Optional[bytes]:
        frozen_oad = apdu[3:7]          # 如 50 04 02 00
        frozen_oi = frozen_oad[0:2].hex()
        rsd_ts, cols = self._parse_rsd_rcsd(apdu)
        if not cols:
            self._log(f"GET Record {frozen_oad.hex()} 无可识别 RCSD 列")
            return build_get_response_record(piid, frozen_oad, [], None)
        # 漏点判定（曲线冻结 5002，按请求时间/当前时间）
        leak = False
        if frozen_oi == "5002" and self.options.leak_window:
            dt = datetime.now()
            if rsd_ts and len(rsd_ts) >= 7:
                try:
                    year = int.from_bytes(rsd_ts[1:3], "big")
                    dt = datetime(year, rsd_ts[3], rsd_ts[4],
                                  rsd_ts[5], rsd_ts[6])
                except (ValueError, IndexError):
                    pass
            leak = dyn.leak_in_window(self.options.leak_window, dt)
        col_data = []
        names = []
        for col in cols:
            item = self.archive.lookup(col[0:2].hex(),
                                       f"{col[2]:02x}", f"{col[3]:02x}",
                                       frozen=frozen_oi)
            if item:
                col_data.append(bytes.fromhex(item["data"]))
                names.append(item.get("name", col.hex()))
            else:
                col_data.append(b"")
        if leak:
            self._log(f"GET Record {frozen_oad.hex()} 漏点时段 → 0 行")
            return build_get_response_record(piid, frozen_oad, cols, None)
        # 自动冻结时标：RSD 带时间则前置到行数据（对齐开源 Daily_freeze）
        if self.options.auto_freeze_time and rsd_ts:
            col_data = [rsd_ts] + col_data
        self._log(f"GET Record {frozen_oad.hex()} {len(cols)} 列 "
                  f"({','.join(names[:3])}{'...' if len(names) > 3 else ''})")
        return build_get_response_record(piid, frozen_oad, cols, col_data)

    def _oad_name(self, oad: bytes) -> str:
        item = self.archive.lookup(oad[0:2].hex(), f"{oad[2]:02x}",
                                   f"{oad[3]:02x}")
        return item["name"] if item else "未知数据标识"

    # ── 帧入口 ────────────────────────────────────────────
    def handle_frame(self, frame: bytes) -> List[bytes]:
        """处理一个完整链路请求帧，返回 0..n 个响应链路帧。"""
        self.logs = []
        try:
            header = parse_header(frame)
        except Exception as e:  # 畸形帧
            self._log(f"帧头解析失败: {e}")
            return []
        apdu = header["apdu"]
        if not apdu:
            return []
        # 安全报文（10 00 明文）解封装
        secured = False
        if apdu[0] == 0x10 and len(apdu) > 3 and apdu[1] == 0x00:
            sec_len = apdu[2]
            inner = apdu[3:3 + sec_len]
            if not inner:
                return []
            apdu = inner
            secured = True
        # 名单过滤（用请求 SA 反转 hex 比对）
        sa_key = dyn.sa_body_reversed_hex(header["sa"])
        if any(k and k in sa_key for k in self.options.blacklist if k):
            self._log(f"黑名单地址命中，不回复: {sa_key}")
            return []
        if self.options.whitelist:
            if not any(k and k in sa_key for k in self.options.whitelist if k):
                self._log(f"白名单外地址，不回复: {sa_key}")
                return []
        archive_no = self._archive_meter_no()
        # 通配地址：多表序号响应
        if is_wildcard_sa(header):
            frames = []
            for k in range(max(1, self.options.meter_count)):
                resp_apdu = self._handle_apdu(apdu, self._meter_no(archive_no, k))
                if resp_apdu is None:
                    continue
                if secured and self.options.mac_enabled:
                    resp_apdu = wrap_security_plain_mac(resp_apdu)
                sa = dyn.wildcard_sa_bytes(self._meter_no(archive_no, k))
                frames.append(assemble_link_frame(sa, header["ca"], resp_apdu))
            self._log(f"通配地址 → {len(frames)} 块表响应")
            return frames
        # 单播
        meter_no = self._meter_no(archive_no, 0)
        resp_apdu = self._handle_apdu(apdu, meter_no)
        if resp_apdu is None:
            return []
        if secured and self.options.mac_enabled:
            resp_apdu = wrap_security_plain_mac(resp_apdu)
        return [assemble_link_frame(header["sa"], header["ca"], resp_apdu)]
