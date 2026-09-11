"""pcap/pcapng 离线导入 → 批量解析文本（纯逻辑，无 Qt）。

现场常见交付物是抓包文件。把 TCP 负载重组后转成批量解析可粘贴的 hex 行，
再走既有 parse_batch / 按类型全选 / 时序图 / 导出。

- 经典 pcap（libpcap）：**纯标准库解析，零依赖**
- pcapng：优先纯实现简化块读取；失败时可选 scapy 兜底（Windows 下会修
  ProgramFiles 环境变量再 import，避免 scapy.arch.windows KeyError）
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional, Tuple


class PcapImportError(Exception):
    """pcap 导入失败（格式不支持 / 无 TCP / 无应用层数据）。"""


@dataclass
class PcapFrame:
    """一帧待写入批量输入框的应用层数据。"""

    timestamp: float
    flow_id: int
    direction: int  # 0=首次出现端点→对端，1=反向
    data: bytes
    source: str = "tcp"  # tcp_payload | plc2_business | plc2_full


@dataclass
class PcapImportResult:
    frames: List[PcapFrame] = field(default_factory=list)
    packet_count: int = 0
    tcp_packet_count: int = 0
    flow_count: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def frame_count(self) -> int:
        return len(self.frames)


@dataclass
class _TcpDatagram:
    timestamp: float
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    payload: bytes


def format_batch_text(
    frames: List[PcapFrame],
    *,
    include_header: bool = True,
    hex_sep: str = " ",
    max_frames: Optional[int] = None,
) -> str:
    """把帧列表转成批量解析输入文本（每帧一段可带时间戳注释行）。"""
    items = frames if max_frames is None else frames[:max_frames]
    lines: List[str] = []
    if include_header:
        lines.append(
            f"# pcap import: {len(items)} frame(s) at {datetime.now():%Y-%m-%d %H:%M:%S}"
        )
    for fr in items:
        ts = datetime.fromtimestamp(fr.timestamp).strftime("%H:%M:%S.%f")[:-3]
        direction = "→" if fr.direction == 0 else "←"
        flow = f"F{fr.flow_id:03d}"
        hex_str = hex_sep.join(f"{b:02X}" for b in fr.data)
        lines.append(f"{ts} {flow}{direction} [{fr.source}] {hex_str}")
    return "\n".join(lines)


def extract_ed_frames(stream: bytes) -> List[bytes]:
    """从字节流切出完整 ED..EF..EE 监控封装帧（保留包装，供协议9批量解析）。

    布局与 monitor.tcp_monitor.FlowBuffer 一致：
      ED + 帧长(2B LE) + ctrl1 + ctrl2 + EF + 数据域 + CS + EE
      帧长 = 数据域长度 + 4；总长 = 帧长 + 4
    """
    frames: List[bytes] = []
    i = 0
    n = len(stream)
    max_frame_len = 4096
    while i < n:
        if stream[i] != 0xED:
            i += 1
            continue
        if i + 6 > n:
            break
        frame_len = stream[i + 1] | (stream[i + 2] << 8)
        if frame_len < 4 or frame_len > max_frame_len:
            i += 1
            continue
        total = frame_len + 4
        if i + total > n:
            break
        if stream[i + 5] != 0xEF or stream[i + total - 1] != 0xEE:
            i += 1
            continue
        frames.append(bytes(stream[i : i + total]))
        i += total
    return frames


def extract_business_from_ed_frame(frame: bytes) -> Optional[bytes]:
    """从完整 ED 帧中取出业务帧（剥监控包装）；无业务返回 None。"""
    if len(frame) < 8 or frame[0] != 0xED:
        return None
    frame_len = frame[1] | (frame[2] << 8)
    if frame_len < 4:
        return None
    ctrl1, ctrl2 = frame[3], frame[4]
    data_start = 6
    data_len = frame_len - 4
    if data_start + data_len > len(frame) - 1:
        data_len = max(0, len(frame) - 1 - data_start)
    if ctrl1 == 0x00 and data_len >= 9:
        return frame[data_start + 9 : data_start + data_len]
    if ctrl1 == 0x00 and ctrl2 == 0x00:
        return None
    return frame[data_start : data_start + data_len]


def _ip_str(b: bytes) -> str:
    return ".".join(str(x) for x in b)


def _parse_ipv4_tcp(frame: bytes, ts: float) -> Optional[_TcpDatagram]:
    """以太网 II + IPv4 + TCP → 负载；非 TCP/无负载返回 None。"""
    if len(frame) < 14:
        return None
    ethertype = struct.unpack("!H", frame[12:14])[0]
    off = 14
    # VLAN 802.1Q
    if ethertype == 0x8100:
        if len(frame) < 18:
            return None
        ethertype = struct.unpack("!H", frame[16:18])[0]
        off = 18
    if ethertype != 0x0800:
        return None
    if len(frame) < off + 20:
        return None
    vihl = frame[off]
    version = vihl >> 4
    ihl = (vihl & 0x0F) * 4
    if version != 4 or ihl < 20:
        return None
    if frame[off + 9] != 6:  # TCP
        return None
    total_len = struct.unpack("!H", frame[off + 2 : off + 4])[0]
    src_ip = _ip_str(frame[off + 12 : off + 16])
    dst_ip = _ip_str(frame[off + 16 : off + 20])
    tcp_off = off + ihl
    if len(frame) < tcp_off + 20:
        return None
    src_port, dst_port = struct.unpack("!HH", frame[tcp_off : tcp_off + 4])
    data_off = ((frame[tcp_off + 12] >> 4) & 0x0F) * 4
    if data_off < 20:
        return None
    ip_end = off + total_len if total_len >= ihl else len(frame)
    payload = frame[tcp_off + data_off : ip_end]
    if not payload:
        return None
    return _TcpDatagram(ts, src_ip, src_port, dst_ip, dst_port, bytes(payload))


def read_classic_pcap(path: str) -> List[_TcpDatagram]:
    """纯标准库读 libpcap（.pcap）。linktype 1=Ethernet。"""
    with open(path, "rb") as f:
        head = f.read(24)
        if len(head) < 24:
            raise PcapImportError("pcap 文件过短（缺全局头）")
        magic = struct.unpack("<I", head[:4])[0]
        if magic == 0xA1B2C3D4:
            endian = "<"
            ns = False
        elif magic == 0xD4C3B2A1:
            endian = ">"
            ns = False
        elif magic == 0xA1B23C4D:
            endian = "<"
            ns = True
        elif magic == 0x4D3CB2A1:
            endian = ">"
            ns = True
        else:
            # pcapng 魔数 0x0A0D0D0A
            if magic in (0x0A0D0D0A, 0x0A0D0D0A):
                raise PcapImportError("PCAPNG")
            raise PcapImportError(
                f"无法识别的抓包魔数 0x{magic:08X}（非经典 pcap）"
            )
        linktype = struct.unpack(endian + "I", head[20:24])[0]
        if linktype not in (1, 0, 101, 12, 113, 276):
            # 1=Ethernet, 101=Raw IP, 113=Linux SLL 等尽量兼容；其他提示
            pass

        datagrams: List[_TcpDatagram] = []
        while True:
            ph = f.read(16)
            if len(ph) < 16:
                break
            ts_sec, ts_frac, incl_len, _orig = struct.unpack(endian + "IIII", ph)
            data = f.read(incl_len)
            if len(data) < incl_len:
                break
            ts = float(ts_sec) + (ts_frac / 1e9 if ns else ts_frac / 1e6)
            if linktype == 1:
                d = _parse_ipv4_tcp(data, ts)
            elif linktype in (101, 12):
                # Raw IP / loopback：无以太网头
                d = _parse_ipv4_tcp(b"\x00" * 12 + b"\x08\x00" + data, ts)
            else:
                # 尝试从偏移 0/14 解析
                d = _parse_ipv4_tcp(data, ts) or _parse_ipv4_tcp(
                    data[14:] if len(data) > 14 else b"", ts
                )
                if d is None and len(data) > 14:
                    # Linux SLL 常见 16 字节头
                    d = _parse_ipv4_tcp(data[16:] if len(data) > 16 else b"", ts)
            if d:
                datagrams.append(d)
        return datagrams


def _read_pcapng_scapy(path: str) -> List[_TcpDatagram]:
    """pcapng 兜底：修 Windows 环境变量后用 scapy 读。"""
    import os
    import sys

    if sys.platform == "win32":
        os.environ.setdefault(
            "ProgramFiles", os.environ.get("ProgramW6432", r"C:\Program Files")
        )
        os.environ.setdefault(
            "ProgramFiles(x86)", os.environ.get("ProgramW6432", r"C:\Program Files (x86)")
        )
    try:
        from scapy.layers.inet import IP, TCP  # noqa: PLC0415
        from scapy.utils import rdpcap  # noqa: PLC0415
    except Exception as exc:
        raise PcapImportError(
            f"读取 pcapng 需要 scapy（或改存为经典 .pcap）：{exc}"
        ) from exc

    try:
        packets = rdpcap(path)
    except Exception as exc:
        raise PcapImportError(f"读取 pcapng 失败：{exc}") from exc

    out: List[_TcpDatagram] = []
    for pkt in packets:
        if not (IP in pkt and TCP in pkt):
            continue
        ip = pkt[IP]
        tcp = pkt[TCP]
        payload = bytes(tcp.payload) if tcp.payload else b""
        if not payload:
            continue
        ts = float(getattr(pkt, "time", 0.0) or 0.0)
        out.append(
            _TcpDatagram(
                ts,
                str(ip.src),
                int(tcp.sport),
                str(ip.dst),
                int(tcp.dport),
                payload,
            )
        )
    return out


def read_tcp_datagrams(path: str) -> List[_TcpDatagram]:
    """按扩展名/魔数选择经典 pcap 或 pcapng 读取。"""
    with open(path, "rb") as f:
        magic4 = f.read(4)
    if magic4 == b"\x0a\x0d\x0d\x0a":
        return _read_pcapng_scapy(path)
    try:
        dgrams = read_classic_pcap(path)
    except PcapImportError as exc:
        if "PCAPNG" in str(exc):
            return _read_pcapng_scapy(path)
        raise
    return dgrams


def _frames_from_datagrams(
    datagrams: Iterable[_TcpDatagram],
    *,
    mode: str,
    min_payload: int,
) -> Tuple[List[PcapFrame], dict]:
    flow_index: dict = {}
    next_flow_id = 1
    dir_buf: dict = {}
    dir_ep: dict = {}
    frames: List[PcapFrame] = []

    for d in datagrams:
        a = (d.src_ip, d.src_port)
        b = (d.dst_ip, d.dst_port)
        key = (a, b) if a <= b else (b, a)
        if key not in flow_index:
            flow_index[key] = next_flow_id
            dir_ep[next_flow_id] = key[0]
            next_flow_id += 1
        flow_id = flow_index[key]
        direction = 0 if a == dir_ep[flow_id] else 1

        if mode == "tcp_payload":
            if len(d.payload) >= min_payload:
                frames.append(
                    PcapFrame(
                        d.timestamp, flow_id, direction, d.payload, source="tcp_payload"
                    )
                )
            continue

        if mode not in ("plc2_full", "plc2_business"):
            raise PcapImportError(f"未知 mode: {mode}")

        buf = dir_buf.setdefault((flow_id, direction), bytearray())
        buf.extend(d.payload)
        full_frames = extract_ed_frames(bytes(buf))
        consumed = _ed_stream_consumed(bytes(buf), full_frames)
        for fr in full_frames:
            if mode == "plc2_full":
                frames.append(
                    PcapFrame(d.timestamp, flow_id, direction, fr, source="plc2_full")
                )
            else:
                biz = extract_business_from_ed_frame(fr)
                if biz:
                    frames.append(
                        PcapFrame(
                            d.timestamp, flow_id, direction, biz, source="plc2_business"
                        )
                    )
        if consumed:
            del buf[:consumed]

    return frames, flow_index


def import_pcap(
    path: str,
    *,
    mode: str = "plc2_full",
    min_payload: int = 1,
    max_frames: Optional[int] = None,
) -> PcapImportResult:
    """从 pcap/pcapng 导入 TCP 应用层帧。

    mode:
      - plc2_full: 按 ED..EE 切出完整监控帧（适合协议 9 批量 + 时序图）
      - plc2_business: 同上再剥包装，只要业务帧
      - tcp_payload: 每个带 payload 的 TCP 段一行（通用兜底）
    """
    try:
        datagrams = read_tcp_datagrams(path)
    except PcapImportError:
        raise
    except OSError as exc:
        raise PcapImportError(f"打开文件失败：{exc}") from exc

    frames, flow_index = _frames_from_datagrams(
        datagrams, mode=mode, min_payload=min_payload
    )
    if max_frames is not None:
        frames = frames[:max_frames]

    result = PcapImportResult(
        frames=frames,
        packet_count=len(datagrams),
        tcp_packet_count=len(datagrams),
        flow_count=len(flow_index),
    )
    if result.tcp_packet_count == 0:
        result.notes.append("pcap 中未找到携带 payload 的 TCP 包")
    if result.frame_count == 0 and mode in ("plc2_full", "plc2_business"):
        result.notes.append(
            "未切出 ED..EE 监控帧：可能不是 PLC2 包装，或负载被截断；可改用「原始 TCP 负载」模式"
        )
    return result


def _ed_stream_consumed(stream: bytes, frames: List[bytes]) -> int:
    """按 extract_ed_frames 相同扫描规则，返回已消费前缀长度。"""
    i = 0
    n = len(stream)
    max_frame_len = 4096
    while i < n:
        if stream[i] != 0xED:
            i += 1
            continue
        if i + 6 > n:
            break
        frame_len = stream[i + 1] | (stream[i + 2] << 8)
        if frame_len < 4 or frame_len > max_frame_len:
            i += 1
            continue
        total = frame_len + 4
        if i + total > n:
            break
        if stream[i + 5] != 0xEF or stream[i + total - 1] != 0xEE:
            i += 1
            continue
        i += total
    return i


def summarize(result: PcapImportResult) -> str:
    parts = [
        f"包 {result.packet_count}",
        f"TCP payload {result.tcp_packet_count}",
        f"流 {result.flow_count}",
        f"帧 {result.frame_count}",
    ]
    if result.notes:
        parts.append("；".join(result.notes))
    return "，".join(parts)


def write_classic_pcap(path: str, packets: List[Tuple[float, bytes]]) -> None:
    """测试辅助：写小端微秒经典 pcap（linktype=Ethernet）。"""
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 0xFFFF, 1))
        for ts, data in packets:
            sec = int(ts)
            usec = int(round((ts - sec) * 1e6))
            f.write(struct.pack("<IIII", sec, usec, len(data), len(data)))
            f.write(data)


def build_eth_ipv4_tcp(
    payload: bytes,
    *,
    src_ip: str = "10.0.0.1",
    dst_ip: str = "10.0.0.2",
    sport: int = 1234,
    dport: int = 8080,
    reverse: bool = False,
) -> bytes:
    """测试辅助：拼一帧 Ethernet+IPv4+TCP 负载。"""
    if reverse:
        src_ip, dst_ip = dst_ip, src_ip
        sport, dport = dport, sport
    ip = bytearray(20)
    ip[0] = 0x45
    total = 20 + 20 + len(payload)
    struct.pack_into("!H", ip, 2, total)
    ip[8] = 64
    ip[9] = 6
    ip[12:16] = bytes(int(x) for x in src_ip.split("."))
    ip[16:20] = bytes(int(x) for x in dst_ip.split("."))
    # 简化：跳过 IP 头校验和（读 TCP 负载不校验）
    tcp = bytearray(20)
    struct.pack_into("!HH", tcp, 0, sport, dport)
    tcp[12] = 5 << 4  # data offset
    eth = struct.pack("!6s6sH", b"\xff" * 6, b"\x00\x11\x22\x33\x44\x55", 0x0800)
    return bytes(eth) + bytes(ip) + bytes(tcp) + payload


__all__ = [
    "PcapFrame",
    "PcapImportResult",
    "PcapImportError",
    "format_batch_text",
    "extract_ed_frames",
    "extract_business_from_ed_frame",
    "import_pcap",
    "read_classic_pcap",
    "read_tcp_datagrams",
    "summarize",
    "write_classic_pcap",
    "build_eth_ipv4_tcp",
]
