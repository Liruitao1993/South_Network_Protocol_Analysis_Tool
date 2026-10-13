# -*- coding: utf-8 -*-
"""协议9「仿照报文回填」：把一帧现成报文反解成组帧参数（纯逻辑，无 Qt）。

用途（GUI 组帧页「仿照报文 / 模板」折叠区）：把官方测试系统里拷来的一帧报文粘进来，
反解出**组帧表单需要的全部参数**，用户只改需要变的字段即可重新生成新帧。

分层策略（由输入决定，逐层向内，能填多少填多少）：

    ED..EE 封装  →  整帧 MPDU  →  FC / 物理块 / MAC 头 / MSDU  →  应用层帧  →  测试帧 BDU

**唯一基准是解析器**：字段取值由 ``CSGNewGenParser.parse_to_table`` 给的行决定
（不复制第二份字段定义）；用「偏移区间」区分 FC(0~15) / 物理块头(16~19) / MAC 及以内(≥20)，
从而同一标签（如 ``源TEI`` 在 FC 与 2.0 扩展里都出现）不会串味。

**保真由调用方用真实 GUI 组帧路径反证**：本模块只产出 :func:`empty_state` 结构的 ``state``
与兜底载荷；GUI 侧回填后立刻重组一次并与原帧逐字节对比，不一致时按「手工 HEX 保真」兜底
（见 ``csg_test_frame_gen_widget`` 的 ``_on_reverse_apply``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import batch_core
import csg_link_frame_gen as link
import csg_new_gen_frame_gen as fg
from csg_new_gen_parser import CSGNewGenParser

#: 解析表区域边界（MPDU 输入的字节偏移）
_FC_MAX = 15
_PB_HDR_MAX = 19

_STATE_VERSION = 1

#: 定界符类型 ↔ 组帧侧的帧类型名
_DELIM_TO_KIND = {link.DELIM_BEACON: "beacon", link.DELIM_SOF: "sof", link.DELIM_SACK: "sack"}

#: 输出层次（与 csg_test_frame_gen_widget._LAYER_OPTIONS 同源语义）
_OUTPUT_LAYERS = ("ed", "app", "bdu", "mpdu")


def empty_state() -> Dict[str, object]:
    """回填/模板共用的 state 骨架（GUI ``frame_state`` 与 ``apply_frame_state`` 同构）。"""
    return {
        "version": _STATE_VERSION,
        "frame": {
            "kind": "sof",
            "channel": "plc",
            "std_version": link.STD_VERSION_BPLC,
            "link_enabled": True,
            "output": "mpdu",
        },
        "link": {},
        "header": {},
        "ed": {},
        "mode": {},
    }


# ----------------------------------------------------------------------
# 取值辅助
# ----------------------------------------------------------------------
def _as_int(value) -> Optional[int]:
    """把解析表的「原始值/解析值」文本尽量转成整数（'0x1F' / '0b1010' / '55' → int）。"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    head = text.split()[0] if " " in text else text
    try:
        if head.lower().startswith("0x"):
            return int(head, 16)
        if head.lower().startswith("0b"):
            return int(head, 2)
        return int(head, 10)
    except ValueError:
        return None


def _raw_bytes(value) -> bytes:
    """「原始值」列的 HEX 文本 → bytes（'0A 00' / '0x1F' / '0b1010' → bytes）。"""
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    text = str(value).strip()
    if not text:
        return b""
    low = text.lower()
    if low.startswith("0x"):
        num = _as_int(text)
        if num is None:
            return b""
        width = max(1, (len(text) - 2 + 1) // 2)
        return num.to_bytes(width, "big")
    if low.startswith("0b"):
        num = _as_int(text)
        return b"" if num is None else bytes([num & 0xFF])
    compact = text.replace(":", "").replace("-", "").replace(" ", "")
    try:
        return bytes.fromhex(compact)
    except ValueError:
        return b""


def _raw_int_le(value) -> Optional[int]:
    """「原始值」按**小端**读成整数（帧长/序号/TEI 等多字节字段的线上序）。"""
    raw = _raw_bytes(value)
    return int.from_bytes(raw, "little") if raw else None


def _raw_int_be(value) -> Optional[int]:
    raw = _raw_bytes(value)
    return int.from_bytes(raw, "big") if raw else None


def _count_text(value) -> Optional[int]:
    """'35字节' / '126字节' → 35 / 126。"""
    if value is None:
        return None
    text = str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


class _Rows:
    """按「标签 + 偏移区间」取值的行访问器（同一标签在不同区域不串味）。

    ``buf`` 是解析表所对应的原始字节：**长字段**（MSDU 负载 / 物理块体 / B 表…）的
    「原始值」列会被解析器用 ``...`` 截断，必须按 ``偏移~结束偏移`` 从 ``buf`` 切，
    不能指望那列的文本。
    """

    def __init__(self, rows: Sequence[Sequence[object]], buf: bytes = b""):
        self.buf = buf
        self.rows = [tuple(r) + ("",) * max(0, 6 - len(tuple(r))) for r in rows]

    def _off(self, row) -> Optional[int]:
        try:
            return int(row[4])
        except (TypeError, ValueError):
            return None

    def _end(self, row) -> Optional[int]:
        try:
            return int(row[5])
        except (TypeError, ValueError):
            return None

    def find(self, label: str, lo: int = 0, hi: int = 1 << 30):
        """返回第一个「标签相同且偏移落在 [lo, hi]」的行。"""
        for row in self.rows:
            if str(row[0]).strip() != label:
                continue
            off = self._off(row)
            if off is None or lo <= off <= hi:
                return row
        return None

    def slice_of(self, label: str, lo: int = 0, hi: int = 1 << 30) -> bytes:
        """按偏移从 buf 切出该字段的字节；buf 不可用或偏移非法时退回「原始值」列。"""
        row = self.find(label, lo, hi)
        if row is None:
            return b""
        off, end = self._off(row), self._end(row)
        if self.buf and off is not None and end is not None and 0 <= off <= end < len(self.buf):
            return self.buf[off:end + 1]
        return _raw_bytes(row[1])

    def offset_of(self, label: str, lo: int = 0, hi: int = 1 << 30) -> Optional[int]:
        row = self.find(label, lo, hi)
        return None if row is None else self._off(row)

    def int_of(self, label: str, lo: int = 0, hi: int = 1 << 30) -> Optional[int]:
        row = self.find(label, lo, hi)
        if row is None:
            return None
        return _as_int(row[1]) if str(row[1]).strip().lower().startswith("0b") else (
            _as_int(row[2]) if _as_int(row[2]) is not None else _as_int(row[1])
        )

    def raw_int(self, label: str, lo: int = 0, hi: int = 1 << 30, endian: str = "little"):
        row = self.find(label, lo, hi)
        if row is None:
            return None
        return _raw_int_le(row[1]) if endian == "little" else _raw_int_be(row[1])

    def raw(self, label: str, lo: int = 0, hi: int = 1 << 30) -> bytes:
        row = self.find(label, lo, hi)
        return b"" if row is None else _raw_bytes(row[1])

    def text(self, label: str, lo: int = 0, hi: int = 1 << 30) -> str:
        row = self.find(label, lo, hi)
        return "" if row is None else str(row[2]).strip()

    def has(self, label: str, lo: int = 0, hi: int = 1 << 30) -> bool:
        return self.find(label, lo, hi) is not None


# ----------------------------------------------------------------------
# 输入层次识别
# ----------------------------------------------------------------------
@dataclass
class ReverseResult:
    """反解结果：``state`` 可直接交给 GUI 的 ``apply_frame_state``。"""

    ok: bool = False
    error: str = ""
    layer: str = ""                 # ed / mpdu / app
    wrapper: str = ""               # plc2 / gx（仅 ED 输入）
    input_hex: str = ""             # 规范化后的输入（去分隔符大写）
    state: Dict[str, object] = field(default_factory=empty_state)
    #: 兜底载荷（按原样复刻用）：key = "app"（应用层帧）/ "msdu"（MSDU 负载）
    payload: Dict[str, str] = field(default_factory=dict)
    #: 反解出的应用层帧 hex（用于保真校验与 2.0 扩展按偏移切片）
    app_hex: str = ""
    notes: List[str] = field(default_factory=list)
    #: 解析到但表单表达不了的字段（重建不一致时最可能的原因，给用户看）
    unmapped: List[str] = field(default_factory=list)


def detect_input_layer(data: bytes) -> Tuple[str, str, bytes]:
    """判定输入是 ED 封装 / 整帧 MPDU / 应用层帧，返回 (layer, wrapper, 内层字节)。"""
    if not data:
        return "", "", b""
    if data[0] == 0xED and len(data) >= 8:
        wrapper = batch_core.resolve_ed_wrapper(data, "auto", protocol_index=9)
        parts = batch_core._ed_frame_parts(data, wrapper)  # noqa: SLF001（同仓库共用）
        if parts is not None:
            hdr_len = parts["hdr_len"]
            inner = parts["data"][hdr_len:] if hdr_len else b""
            if inner:
                return "ed", wrapper, inner
    if (data[0] >> 3) & 1 == 1 and (data[0] & 0x07) <= 3:
        return "mpdu", "", data
    # 应用层帧最短 = 应用层头(12) + 测试帧 BDU 头(测试ID1 + 保留1 + 数据区长度2) = 16 字节；
    # 比这更短的一律判为无法识别（否则 2 字节的垃圾输入也会被当成应用层帧解析）
    return ("app", "", data) if len(data) >= 16 else ("", "", b"")


# ----------------------------------------------------------------------
# 各区域字段映射
# ----------------------------------------------------------------------
def _fill_fc(rows: _Rows, state: Dict[str, object], res: ReverseResult) -> None:
    """① FC 帧控制（字节 0~15）。"""
    kind = _DELIM_TO_KIND.get(rows.int_of("定界符类型", 0, _FC_MAX))
    if kind:
        state["frame"]["kind"] = kind
    std = rows.int_of("标准版本号", 0, _FC_MAX)
    if std in (link.STD_VERSION_BPLC, link.STD_VERSION_ISAC):
        state["frame"]["std_version"] = std
    channel = rows.text("通道判定", 0, _FC_MAX)
    if channel in ("plc", "hrf"):
        state["frame"]["channel"] = channel

    lk: Dict[str, object] = state["link"]
    for label, key in (
        ("接入指示", "access_indicator"),
        ("源TEI", "src_tei"),
        ("目的TEI", "dest_tei"),
        ("链路标识符", "link_id"),
        ("扩展载波映射表索引", "ext_cmt_index"),
        ("TEI过滤标志", "tei_filter"),
        ("重传标志", "retransmit"),
        ("符号数", "symbol_count"),
        ("流数", "streams"),
        ("PL频段标识", "pl_band"),
        ("TF扩展频段", "tf_ext_band"),
        ("Bitloading标识", "bitloading"),
        ("信标时间戳", "beacon_timestamp"),
        ("信标周期计数", "beacon_cycle"),
        ("相线", "beacon_phase"),
        ("接收结果", "sack_rx_result"),
        ("接收状态", "sack_rx_status"),
        ("接收物理块个数", "sack_rx_pb_count"),
        ("SNR类型", "sack_snr_type"),
    ):
        value = rows.int_of(label, 0, _FC_MAX)
        if value is not None:
            lk[key] = value

    # 帧长：FC 里存的是「10μs 单位」原值，必须读**原始值**（解析值已换算成 μs）
    frame_len = rows.raw_int("帧长", 0, _FC_MAX)
    if frame_len is not None:
        lk["frame_len_10us"] = frame_len

    # TF符号数：解析值已按 (值+1)×2 换算，回填要还原成配置值
    tf = rows.int_of("TF符号数", 0, _FC_MAX)
    if tf is not None:
        lk["tf_symbols_cfg"] = max(0, tf // 2 - 1)

    # SNID：低位在 FC 固定部分，高位在可变区域，拼成 5bit 完整值
    low = rows.int_of("短网络标识低位(SNID)", 0, _FC_MAX)
    high = rows.int_of("短网络标识高位", 0, _FC_MAX)
    if low is not None:
        lk["snid"] = (low & 0x0F) | ((high or 0) << 4)

    # SACK SNR 值：解析器按「4 字节大端 >> 2」读，原始值反算
    if rows.find("SNR评估信息", 0, _FC_MAX) is not None:
        word = rows.raw_int("SNR评估信息", 0, _FC_MAX, endian="big")
        if word is not None:
            lk["sack_snr_value"] = (word >> 2) & 0x1F
    return


def _fill_beacon_symbol_count(rows: _Rows, fc_bytes: bytes, state: Dict[str, object],
                              res: ReverseResult) -> None:
    """信标帧符号数的第 9 位：解析器读的是**版本号最高位**（已知分歧），按 FC 原始字节还原。

    组帧侧 ``_fill_fc_beacon`` 把符号数写成「字节11 全部 = 低8位」+「字节12 bit0 = 第9位」，
    而解析器把第 9 位取到了 bit103（= 版本号的最高位）——两边不可能同时满足。此处直接按
    **组帧侧口径**从原始 FC 还原，保证「回填→重建」与原帧一致；并记入 notes 说明。
    """
    if state["frame"]["kind"] != "beacon" or len(fc_bytes) < 13:
        return
    symbol_count = (fc_bytes[11] << 1) | (fc_bytes[12] & 0x01)
    state["link"]["symbol_count"] = symbol_count
    parsed = rows.int_of("符号数", 0, _FC_MAX)
    if parsed is not None and parsed != symbol_count:
        res.notes.append(
            f"信标符号数按 FC 原始位还原为 {symbol_count}（解析器读回 {parsed}；"
            "第 9 位与版本号最高位冲突，属已知分歧）")


def _fill_pb(rows: _Rows, state: Dict[str, object], res: ReverseResult) -> None:
    """② 物理块（头 16~19 字节 + 块体）。"""
    lk = state["link"]
    seq = rows.int_of("序列号", _FC_MAX + 1, _PB_HDR_MAX + 40)
    if seq is None:
        seq = rows.raw_int("序列号", _FC_MAX + 1, _PB_HDR_MAX + 40)
    if seq is not None:
        lk["pb_seq"] = seq
    agg = rows.int_of("聚合标志", _FC_MAX + 1, _PB_HDR_MAX + 40)
    if agg is not None:
        lk["pb_agg"] = agg
    # 物理块总大小 = 块体字节数 + 物理块头(4) + 保留(1) + PBCS(3)
    body = rows.find("物理块体", 0, 1 << 30) or rows.find("物理块体[0]", 0, 1 << 30)
    body_len = _count_text(body[2]) if body is not None else None
    if body_len:
        lk["pb_total"] = body_len + 8
    count = rows.int_of("物理块个数", 0, _FC_MAX + 40)
    if count:
        lk["pb_count"] = count


def _fill_mac(rows: _Rows, state: Dict[str, object], res: ReverseResult) -> None:
    """③ MAC 帧头 + ④ MSDU 头（偏移 ≥ 20）。载荷字节由 :func:`_app_frame_bytes` 负责。"""
    lk: Dict[str, object] = state["link"]
    for label, key in (
        ("帧头类型", "mac_hdr"),
        ("版本", "mac_version"),
        ("发送序号", "tx_seq"),
        ("重启次数", "reboot_count"),
        ("路由跳数", "hop_count"),
        ("广播方向", "bcast"),
        ("发送类型", "send_type"),
        ("发送次数限值", "max_send"),
        ("MSDU序列号", "msdu_seq"),
        ("VLAN标签", "vlan"),
        ("MSDU类型", "msdu_type"),
    ):
        value = rows.int_of(label, 20, 1 << 30)
        if value is None:
            value = rows.raw_int(label, 20, 1 << 30)
        if value is not None:
            lk[key] = value

    dest_mac = rows.text("目的MAC地址", 20, 1 << 30)
    if dest_mac:
        lk["dest_mac"] = dest_mac
    for label, key in (("原始目的地址", "msdu_dest_mac"), ("原始源地址", "msdu_src_mac")):
        mac = rows.text(label, 20, 1 << 30)
        if mac:
            lk[key] = mac

    # MAC 头的完整 SNID 比 FC 拼出来的更权威
    snid = rows.int_of("短网络标识(SNID)", 20, 1 << 30)
    if snid is not None:
        lk["snid"] = snid


def _app_frame_bytes(rows: _Rows, buf: bytes) -> bytes:
    """取出应用层帧字节（= MSDU **载荷**，组帧侧 ``msdu_payload`` 的口径）。

    「MSDU负载」行覆盖的是**整个 MSDU**（头 + 载荷），头长不固定，所以不能直接用它：
    用「报文端口号」行的起始偏移作为载荷起点（头长 = 端口偏移 − MSDU负载偏移），
    终点取 MSDU负载行的结束偏移。
    """
    msdu = rows.find("MSDU负载", 20, 1 << 30)
    if msdu is None or not buf:
        return b""
    port_off = rows.offset_of("报文端口号", 20, 1 << 30)
    try:
        end = int(msdu[5])
    except (TypeError, ValueError):
        return b""
    if port_off is None or not (0 <= port_off <= end < len(buf)):
        return rows.slice_of("MSDU负载", 20, 1 << 30)
    return buf[port_off:end + 1]


def _fill_app(rows: _Rows, state: Dict[str, object], res: ReverseResult,
              app_bytes: bytes, base: int) -> None:
    """应用层帧 + 测试帧 BDU。

    ``base``：应用层帧在解析表偏移空间里的起点（MPDU 输入时 = MAC/MSDU 之后，取 0 表示
    输入本身就是应用层帧、偏移即帧内偏移）。
    """
    lo, hi = base, base + 0x4000
    hdr: Dict[str, object] = state["header"]
    port = rows.int_of("报文端口号", lo, hi)
    if port is not None:
        hdr["port"] = port
    for label, key in (
        ("传输方向(D15)", "dir"),
        ("启动标志(D14)", "prm"),
        ("响应标识(D13)", "response"),
        ("任务优先级(D11~D8)", "priority"),
        ("帧类型域(D3~D0)", "frame_type"),
    ):
        value = rows.int_of(label, lo, hi)
        if value is not None:
            hdr[key] = value
    for label, key in (("应用版本号", "appver"), ("帧序号", "seq")):
        value = rows.int_of(label, lo, hi)
        if value is None:
            value = rows.raw_int(label, lo, hi)
        if value is not None:
            hdr[key] = value

    # 表单表达不了的常量：与默认口径不一致时记入 unmapped（重建会不一致的真实原因）
    msg_id = rows.raw_int("报文标识符", lo, hi)
    if msg_id is not None and msg_id != fg.MSG_ID_CCO_STA:
        res.unmapped.append(f"报文标识符=0x{msg_id:04X}（表单固定 0x{fg.MSG_ID_CCO_STA:04X}）")
    for label in ("保留", "业务扩展域标识位(D12)", "保留(D7~D4)"):
        value = rows.int_of(label, lo, hi)
        if value:
            res.unmapped.append(f"{label}={value}（表单固定 0）")
    service = rows.int_of("业务标识", lo, hi)
    if service is not None and service != fg.SERVICE_TEST_FRAME:
        res.unmapped.append(f"业务标识=0x{service:02X}（表单固定 0x{fg.SERVICE_TEST_FRAME:02X}）")

    _fill_mode(rows, state, res, app_bytes, lo, hi)


def _fill_mode(rows: _Rows, state: Dict[str, object], res: ReverseResult,
               app_bytes: bytes, lo: int, hi: int) -> None:
    """测试帧 BDU → 测试模式 + 模式参数。"""
    test_id = rows.int_of("测试ID", lo, hi)
    if test_id is None:
        return
    res.notes.append(f"测试ID = 0x{test_id:02X}")

    data_len = rows.int_of("数据区长度", lo, hi)
    if data_len is None:
        data_len = rows.raw_int("数据区长度", lo, hi)
    data = _slice_data_area(rows, app_bytes, data_len, res)
    if not data:
        return

    if test_id in (0x00, 0x01, 0x02):
        modes = [m for m in fg.test_modes() if m.test_id == test_id and m.ext_id is None]
        if modes:
            state["mode"] = {"key": modes[0].key, "params": {"band": data[0] & 0x0F}}
        return

    if test_id == 0x03:
        _fill_legacy(rows, state, res, data, lo, hi)
        return

    if test_id == 0x04:
        _fill_ext(rows, state, res, data, lo, hi)
        return

    res.unmapped.append(f"未知测试ID=0x{test_id:02X}")


def _slice_data_area(rows: _Rows, app_bytes: bytes, data_len: Optional[int],
                     res: ReverseResult) -> bytes:
    """测试数据区字节。

    应用层帧布局固定（端口1 + 标识符2 + 保留1 + 控制域2 + 业务标识1 + 版本1 + 序号2
    + 帧长2 + 测试ID1 + 保留1 + 数据区长度2 = 16 字节头），所以有 app_bytes 就直接切；
    「测试数据区」行的原始值对长数据也会被 ``...`` 截断，只在拿不到 app_bytes 时兜底。
    """
    if app_bytes and data_len and len(app_bytes) >= 16 + data_len:
        return app_bytes[16:16 + data_len]
    raw = rows.slice_of("测试数据区", 0, 1 << 30)
    if raw:
        return raw
    if app_bytes:
        # 数据区长度字段异常时，退化为「帧长字段声明的长度」再不行就取到帧尾
        declared = rows.raw_int("帧长", 0, 1 << 30)
        if declared and len(app_bytes) >= 16 + declared:
            return app_bytes[16:16 + declared]
    res.unmapped.append("无法定位测试数据区（应用层帧未取到或长度字段异常）")
    return b""


def _fill_legacy(rows: _Rows, state: Dict[str, object], res: ReverseResult,
                 data: bytes, lo: int, hi: int) -> None:
    """test_id=0x03：表61 原有扩展命令格式（1.0 测试）。"""
    if len(data) < 6:
        res.unmapped.append(f"1.0 测试数据区仅 {len(data)} 字节（表61 头需 6 字节）")
        return
    mode = data[1] >> 4
    params: Dict[str, object] = {
        "proto_version": data[0] & 0x3F,
        "header_len": ((data[0] >> 6) & 0x03) << 4 | (data[1] & 0x0F),
        "protocol_type": data[2] & 0x0F,
        "value": ((data[2] >> 4) & 0x0F) << 8 | data[3],
        "security_mode": data[4] & 0x0F,
        "phr_mcs": (data[4] >> 4) & 0x0F,
        "psdu_mcs": data[5] & 0x0F,
        "pb_size": (data[5] >> 4) & 0x0F,
    }
    # 报文头长度布局：字节1 低 4 位为 0 ⇒ 组帧侧用的是「解析器口径」（只写高 2 位）
    doc_len = ((data[0] >> 6) & 0x03) << 4 | (data[1] & 0x0F)
    if (data[1] & 0x0F) == 0:
        params["header_len_layout"] = "parser"
        params["header_len"] = (data[0] >> 6) & 0x03
    else:
        params["header_len_layout"] = "doc" if doc_len else "parser"

    candidates = [m for m in fg.test_modes()
                  if m.test_id == 0x03 and m.legacy_mode == mode]
    if not candidates:
        res.unmapped.append(f"表61 测试模式号 {mode} 无对应模式")
        return
    res.notes.append(f"表61 测试模式号 = {mode}（{candidates[0].name}）")
    state["mode"] = {"key": candidates[0].key, "params": params}
    # 表61 头之后是「转发数据」，表单无对应字段
    forward = data[6:]
    if forward:
        res.unmapped.append(f"表61 转发数据 {len(forward)} 字节（表单无字段，已按载荷保真）")


def _fill_ext(rows: _Rows, state: Dict[str, object], res: ReverseResult,
              data: bytes, lo: int, hi: int) -> None:
    """test_id=0x04：2.0 测试扩展（协商版本号1 + 文件长度1 + 扩展ID2 + 扩展数据）。"""
    if len(data) < 4:
        res.unmapped.append(f"2.0 测试数据区仅 {len(data)} 字节（需 ≥4）")
        return
    neg_version, file_len = data[0], data[1]
    ext_id = int.from_bytes(data[2:4], "little")
    ext_data = data[4:]
    if neg_version:
        res.unmapped.append(f"协商版本号={neg_version}（表单固定 0）")

    candidates = [m for m in fg.test_modes() if m.test_id == 0x04 and m.ext_id == ext_id]
    if not candidates:
        res.unmapped.append(f"扩展ID={ext_id} 无对应模式")
        return
    res.notes.append(f"扩展ID = {ext_id}（{candidates[0].name}）")
    params: Dict[str, object] = {}

    if ext_id == 0x0002 and len(ext_data) >= 12:
        params["src_tei"] = int.from_bytes(ext_data[0:2], "little")
        params["dst_tei"] = int.from_bytes(ext_data[2:4], "little")
        params["stream_count"] = ext_data[4]
        params["subcarrier_group"] = ext_data[5]
        params["cutoff_carrier"] = int.from_bytes(ext_data[6:8], "little")
        table_len = int.from_bytes(ext_data[8:10], "little")
        params["bps"] = int.from_bytes(ext_data[10:12], "little")
        table = ext_data[12:12 + table_len]
        params["bit_table"] = table
        if len(table) != table_len:
            res.unmapped.append(f"B表长度声明 {table_len}，实际 {len(table)} 字节")
    elif ext_id == 0x0003 and ext_data:
        params["mapping_mode"] = ext_data[0]
    elif ext_id == 0x0005 and ext_data:
        params["frame_type"] = ext_data[0] & 0x03
        frame_type = params["frame_type"]
        fc = ext_data[1:17]
        efc = ext_data[17:33]
        if len(fc) == 16:
            params["fc"] = fc
        need_efc = frame_type != 1
        if need_efc and len(efc) == 16:
            params["efc"] = efc
        elif need_efc:
            res.unmapped.append(f"OFDMA多用户 eFC 域仅 {len(efc)} 字节（需 16）")
    elif ext_id == 0x0006 and ext_data:
        params["ofdma_type"] = ext_data[0] & 0x01
        params["node_count"] = (ext_data[0] >> 1) & 0x07
    elif ext_id == 0x0007 and len(ext_data) >= 2:
        params["tei"] = ext_data[0] | ((ext_data[1] & 0x0F) << 8)
    elif ext_id == 0x0008 and ext_data:
        params["enable"] = ext_data[0] & 0x01
    elif ext_id == 0x0009 and ext_data:
        params["agg_count"] = ext_data[0]

    if file_len != len(ext_data):
        res.unmapped.append(f"文件长度={file_len} 与扩展数据长度 {len(ext_data)} 不一致")

    state["mode"] = {"key": candidates[0].key, "params": params}


def _fill_ed(data: bytes, wrapper: str, state: Dict[str, object],
             res: ReverseResult, inner: bytes) -> None:
    """⑤ ED 封装参数（PLC2.0 / 广西台体两种公共头）。"""
    parts = batch_core._ed_frame_parts(data, wrapper)  # noqa: SLF001（同仓库共用）
    if parts is None:
        return
    ed: Dict[str, object] = state["ed"]
    ed["enabled"] = True
    ed["wrapper"] = wrapper
    if parts["cs"] == 0xFF:
        ed["cs"] = "ff"
    elif parts["cs_ok"]:
        ed["cs"] = "sum"
    else:
        ed["cs"] = "ff"
        res.notes.append(f"ED 校验和 0x{parts['cs']:02X} 既非 0xFF 也非字节和，按 0xFF 回填")
    if parts["hdr_len"]:
        ed["channel"] = parts["ch"]
        ed["timestamp"] = parts["ts"]
        ed["pb_count"] = parts["pb_cnt"] or 1
        # 「物理块长度」填 0 = 自动（= 内层帧长）；只有不一致时才写实际值
        ed["pb_len"] = 0 if parts["pb_len"] == len(inner) else parts["pb_len"]


# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------
def reverse_frame(text_or_bytes) -> ReverseResult:
    """把一帧报文反解成组帧参数（state）。"""
    res = ReverseResult()
    if isinstance(text_or_bytes, (bytes, bytearray)):
        data = bytes(text_or_bytes)
    else:
        try:
            data = fg.hex_to_bytes(str(text_or_bytes or ""))
        except Exception as exc:  # noqa: BLE001 - 输入脏数据要给可读原因
            res.error = f"报文 HEX 无法解析：{exc}"
            return res
    if not data:
        res.error = "请先粘贴一帧报文（HEX）"
        return res

    res.input_hex = data.hex().upper()
    layer, wrapper, inner = detect_input_layer(data)
    if not inner:
        res.error = "报文过短或 ED 结构不完整，无法识别层次"
        return res
    res.layer = layer
    res.wrapper = wrapper
    # 输出层次跟着**粘贴进来的层次**走：这样回填后重建出来的字节与原帧同层次可逐字节对比
    res.state["frame"]["output"] = {"ed": "ed", "mpdu": "mpdu", "app": "app"}[layer]

    if layer == "ed":
        _fill_ed(data, wrapper, res.state, res, inner)
        res.notes.append(f"识别为 ED..EE 封装（{wrapper}），已剥离公共头")
        data = inner

    is_mpdu = (data[0] >> 3) & 1 == 1 and (data[0] & 0x07) <= 3
    parser = CSGNewGenParser()
    try:
        rows = _Rows(parser.parse_to_table(data, parse_level="auto" if is_mpdu else "app"), data)
    except Exception as exc:  # noqa: BLE001
        res.error = f"解析失败：{exc}"
        return res

    app_bytes = b""
    if is_mpdu:
        res.state["frame"]["link_enabled"] = True
        _fill_fc(rows, res.state, res)
        _fill_beacon_symbol_count(rows, data[:13], res.state, res)
        _fill_pb(rows, res.state, res)
        _fill_mac(rows, res.state, res)
        app_bytes = _app_frame_bytes(rows, data)
        if not app_bytes:
            # 聚合帧 / MAC 帧不完整时下钻不到应用层；链路层字段仍回填，载荷由保真兜底
            res.notes.append("未能下钻到应用层（聚合帧或 MAC 帧不完整），仅回填链路层")
        _fill_app(rows, res.state, res, app_bytes, 20)
    else:
        res.state["frame"]["link_enabled"] = False
        res.notes.append("输入未带链路层（接入指示/定界符不符），按应用层帧回填")
        app_bytes = data
        _fill_app(rows, res.state, res, app_bytes, 0)

    if app_bytes:
        res.app_hex = app_bytes.hex().upper()
        # 组帧侧「手工载荷」= MSDU 载荷 = 应用层帧，保真兜底就填这一项
        res.payload["msdu_payload"] = res.app_hex
    res.ok = True
    return res


def state_summary(state: Dict[str, object]) -> str:
    """给 GUI 提示行用的一句话摘要。"""
    frame = state.get("frame", {}) or {}
    kind = {"sof": "SOF", "beacon": "信标", "sack": "SACK"}.get(frame.get("kind"), "?")
    std = {link.STD_VERSION_BPLC: "BPLC", link.STD_VERSION_ISAC: "ISAC"}.get(
        frame.get("std_version"), "?")
    mode = state.get("mode", {}) or {}
    key = mode.get("key") or "（未识别测试模式）"
    spec = fg.mode_by_key(key) if mode.get("key") else None
    name = f"{spec.group}·{spec.name}" if spec else key
    link_part = "带链路层" if frame.get("link_enabled") else "仅应用层"
    return f"{kind} 帧 / {std} / {link_part} / {name}"
