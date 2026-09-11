"""pcap_import 纯逻辑测试（经典 pcap 零依赖，不依赖 scapy）。"""

import os
import tempfile

import _path_setup  # noqa: E402

from pcap_import import (  # noqa: E402
    PcapFrame,
    PcapImportError,
    build_eth_ipv4_tcp,
    extract_business_from_ed_frame,
    extract_ed_frames,
    format_batch_text,
    import_pcap,
    summarize,
    write_classic_pcap,
)


def _make_ed_frame(payload: bytes) -> bytes:
    """按 FlowBuffer 口径构造最小合法 ED 帧（ctrl1=0 数据报文，剥 9B 公共头后业务=payload）。"""
    data = bytes([0x01]) + bytes(4) + bytes([0x01, 0x00]) + bytes([len(payload) & 0xFF, 0]) + payload
    frame_len = 4 + len(data)  # 数据域长+4
    body = bytes([0x00, 0x01, 0xEF]) + data
    cs = (0xED + frame_len + (frame_len >> 8) + sum(body)) & 0xFF
    frame = bytes([0xED, frame_len & 0xFF, (frame_len >> 8) & 0xFF]) + body + bytes([cs, 0xEE])
    assert frame_len == len(body) + 1
    return frame


class _StubResult:
    def __init__(self, frames):
        self.frames = frames
        self.packet_count = 0
        self.tcp_packet_count = 0
        self.flow_count = 1
        self.notes = []

    @property
    def frame_count(self):
        return len(self.frames)


def test_extract_ed_frames_simple():
    biz = b"\x11\x01\x01\x00"
    fr = _make_ed_frame(biz)
    got = extract_ed_frames(b"\x00\x00" + fr + b"\xff" + fr)
    assert len(got) == 2
    assert got[0] == fr


def test_extract_business_from_ed():
    biz = b"\x19\x01\x20\x00"
    fr = _make_ed_frame(biz)
    assert extract_business_from_ed_frame(fr) == biz


def test_format_batch_text_header_and_hex():
    frames = [
        PcapFrame(1726000000.0, 1, 0, b"\xed\x01", source="plc2_full"),
        PcapFrame(1726000001.0, 1, 1, b"\xaa\xbb", source="plc2_full"),
    ]
    text = format_batch_text(frames)
    assert "# pcap import: 2 frame(s)" in text
    assert "F001→" in text and "F001←" in text
    assert "ED 01" in text
    assert "帧 2" in summarize(_StubResult(frames))


def test_import_classic_pcap_plc2_and_tcp():
    biz = b"\x11\x01\x01\x00"
    fr = _make_ed_frame(biz)
    pkt1 = build_eth_ipv4_tcp(fr, reverse=False)
    pkt2 = build_eth_ipv4_tcp(fr, reverse=True)
    fd, path = tempfile.mkstemp(suffix=".pcap")
    os.close(fd)
    try:
        write_classic_pcap(path, [(1726000000.0, pkt1), (1726000001.0, pkt2)])
        r = import_pcap(path, mode="plc2_full")
        assert r.packet_count == 2
        assert r.tcp_packet_count == 2
        assert r.flow_count == 1
        assert r.frame_count == 2
        text = format_batch_text(r.frames)
        assert "plc2_full" in text
        r2 = import_pcap(path, mode="tcp_payload")
        assert r2.frame_count == 2
        r3 = import_pcap(path, mode="plc2_business")
        assert r3.frame_count == 2
        assert all(f.data == biz for f in r3.frames)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_empty_tcp_note():
    # TCP 无 payload：只写 20B TCP 头 + 空 payload → build 仍会带 payload 长度0？
    # 手工写只有 IP 头无 TCP 的包会跳过；用 0 长度 payload 不经 build
    # 直接写一帧以太网 ARP（非 IP）确保 tcp_packet_count=0
    arp = b"\xff" * 6 + b"\x00\x11\x22\x33\x44\x55" + b"\x08\x06" + b"\x00" * 28
    fd, path = tempfile.mkstemp(suffix=".pcap")
    os.close(fd)
    try:
        write_classic_pcap(path, [(1.0, arp)])
        r = import_pcap(path, mode="plc2_full")
        assert r.frame_count == 0
        assert r.tcp_packet_count == 0
        assert any("TCP" in n for n in r.notes)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_bad_magic_raises():
    fd, path = tempfile.mkstemp(suffix=".pcap")
    os.write(fd, b"\x00\x01\x02\x03" + b"\x00" * 40)
    os.close(fd)
    try:
        try:
            import_pcap(path, mode="tcp_payload")
            raise AssertionError("expected PcapImportError")
        except PcapImportError as e:
            assert "魔数" in str(e) or "pcap" in str(e).lower()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    test_extract_ed_frames_simple()
    test_extract_business_from_ed()
    test_format_batch_text_header_and_hex()
    test_import_classic_pcap_plc2_and_tcp()
    test_empty_tcp_note()
    test_bad_magic_raises()
    print("pcap_import tests OK (stdlib classic pcap)")
