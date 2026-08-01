# -*- coding: utf-8 -*-
"""监控包装解帧(96..16)功能验证（临时脚本）

包结构: 96H(1)+RSSI(1)+NTB(4,小端)+[LEN(12b)+协议类型(3b)+CHANNEL(1b)](2)+DATA(LEN)+CS(1)+16H(1)
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from monitor_widget import RealtimeMonitorWidget
from csg_new_gen_parser import CSGNewGenParser

app = QApplication([])


def make_wrap(data: bytes, rssi=0x30, ntb=0x11223344, proto=1, channel=0,
              bad_cs=False) -> bytes:
    """构造一个监控包装包"""
    n = len(data)
    b6 = n & 0xFF
    b7 = ((n >> 8) & 0x0F) | ((proto & 0x07) << 4) | ((channel & 0x01) << 7)
    head = bytes([0x96, rssi]) + ntb.to_bytes(4, "little") + bytes([b6, b7])
    body = head + bytes(data)
    cs = sum(body) & 0xFF
    if bad_cs:
        cs ^= 0xFF
    return body + bytes([cs, 0x16])


def summ(td):
    return f"字段:{len(td)}"


def new_widget():
    w = RealtimeMonitorWidget()
    w.set_protocol(CSGNewGenParser(), summ)
    assert w.deframe_chk.isChecked(), "解帧应默认开启"
    return w


# ---------- 场景1：用户提供的 44 字节真实报文（含前导垃圾 + 第2个有效包）----------
REAL = bytes.fromhex(
    "03 1F B7 CB 96 00 8A 07 DB 2D 67 18 02 AA 91 2A 6A 16 "
    "96 0B CF 40 B1 90 10 20 03 27 38 93 7D 00 71 16 6B 52 D9 79 03 0E 12 CE 1A 16"
    .replace(" ", "")
)
w = new_widget()
w._on_raw_data(REAL)
# 第一段(offset4的0x96)LEN=0x67|(8<<8)=2151>2048被判伪头跳过；仅第2个包有效
assert len(w._frames) == 1, f"应仅解出1个有效包, 实得{len(w._frames)}"
rec = w._frames[0]
meta = rec["meta"]
assert meta is not None, "应有监控包装meta"
assert meta["len"] == 16, f"LEN应为16: {meta['len']}"
assert meta["proto_type"] == 2, f"协议类型应为2(IEEE1901): {meta['proto_type']}"
assert meta["channel"] == 0, f"CHANNEL应为0(HPLC): {meta['channel']}"
assert meta["cs"] == 0x1A, f"CS应为0x1A: {meta['cs']:#x}"
assert meta["cs_ok"], "CS校验应通过"
expect_data = bytes.fromhex("032738937D0071166B52D979030E12CE")
assert rec["raw"] == expect_data, f"DATA提取错误: {rec['raw'].hex()}"
assert len(w._rx_buffer) == 0, "整包处理完缓冲应清空"
print("1 真实44字节报文：跳过伪头，正确解出第2个包 OK")
print("  DATA=", rec["raw"].hex().upper(), "摘要=", rec["summary"])

# ---------- 场景2：连帧（两个有效包一次性到达）----------
w = new_widget()
p1 = make_wrap(bytes([0xAA, 0xBB, 0xCC]), rssi=0x11, proto=1, channel=1)
p2 = make_wrap(bytes([0xDD, 0xEE]), rssi=0x22, proto=0, channel=0)
w._on_raw_data(p1 + p2)
assert len(w._frames) == 2, f"连帧应解出2个包: {len(w._frames)}"
assert w._frames[0]["raw"] == bytes([0xAA, 0xBB, 0xCC])
assert w._frames[0]["meta"]["channel"] == 1  # RF
assert w._frames[1]["raw"] == bytes([0xDD, 0xEE])
assert w._frames[1]["meta"]["proto_type"] == 0  # 国网HPLC
print("2 连帧一次到达：正确拆分2个包 OK")

# ---------- 场景3：DATA 内含 0x16（不应被误判为帧尾）----------
w = new_widget()
p = make_wrap(bytes([0x11, 0x16, 0x22, 0x16, 0x33]))
w._on_raw_data(p)
assert len(w._frames) == 1, "DATA含0x16不应导致拆分错误"
assert w._frames[0]["raw"] == bytes([0x11, 0x16, 0x22, 0x16, 0x33]), \
    f"DATA内0x16被误切: {w._frames[0]['raw'].hex()}"
print("3 DATA内含0x16：按LEN定界不误切 OK")

# ---------- 场景4：分片到达（半包 → 补齐）----------
w = new_widget()
p = make_wrap(bytes([0x01, 0x02, 0x03, 0x04]))
w._on_raw_data(p[:6])              # 只到一半包头
assert len(w._frames) == 0, "半包不应产生帧"
assert len(w._rx_buffer) == 6, "半包应留在缓冲"
w._on_raw_data(p[6:])              # 补齐剩余
assert len(w._frames) == 1, "补齐后应解出1包"
assert w._frames[0]["raw"] == bytes([0x01, 0x02, 0x03, 0x04])
assert len(w._rx_buffer) == 0, "整包处理后缓冲清空"
print("4 分片到达：半包缓存补齐后解出 OK")

# ---------- 场景5：CS 错误标记 ----------
w = new_widget()
p = make_wrap(bytes([0x55, 0x66]), bad_cs=True)
w._on_raw_data(p)
assert len(w._frames) == 1
rec = w._frames[0]
assert not rec["meta"]["cs_ok"], "错误CS应标记cs_ok=False"
assert not rec["ok"], "CS错误帧整体应标记不OK"
assert "CS✗" in rec["summary"], f"摘要应含CS错误标记: {rec['summary']}"
print("5 CS错误：正确标记 OK")

# ---------- 场景6：伪帧头（0x96但LEN超限/帧尾非16）后仍能恢复 ----------
w = new_widget()
garbage = bytes([0x96, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x0F])  # LEN=0xFFF=4095>2048
good = make_wrap(bytes([0x77, 0x88]))
w._on_raw_data(garbage + good)
assert len(w._frames) == 1, f"伪头后应恢复解出真包: {len(w._frames)}"
assert w._frames[0]["raw"] == bytes([0x77, 0x88])
print("6 伪帧头后恢复：跳过伪头解出真包 OK")

# ---------- 场景7：meta 详情行前置 ----------
w = new_widget()
w._on_raw_data(make_wrap(bytes([0x11, 0x01, 0x01, 0x00])))
td = w._frames[0]["table_data"]
labels = [row[0] for row in td[:8]]
assert "── 监控包装 ──" in labels[0], f"首行应为监控包装标题: {labels[0]}"
assert any("RSSI" in l for l in labels), "应含RSSI行"
assert any("CHANNEL" in l for l in labels), "应含CHANNEL行"
assert any("业务帧" in l for l in labels), "应含业务帧分隔行"
# meta 行不参与高亮（byte_start=None）
for row in td[:8]:
    assert row[4] is None, f"监控包装行不应高亮: {row[0]}"
print("7 详情前置监控包装信息行（不高亮）OK")

print("全部通过")
